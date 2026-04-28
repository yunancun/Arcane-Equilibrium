//! Pure evaluation function for cost_edge_advisor.
//! cost_edge_advisor 的純評估函式。
//!
//! MODULE_NOTE (EN): `evaluate()` is a pure fn — no I/O, no global state,
//!   deterministic mapping `(snapshot, cfg, is_stale, now_ms) → state`. The
//!   daemon (mod.rs) calls this every 10s + handles transition emit; the
//!   tests directly drive this fn through every state machine path.
//!
//!   Evaluation precedence (per PA RFC §4.2 line 305):
//!     1. `!cfg.enabled`  → Disabled                       (short-circuit)
//!     2. `is_stale`      → Stale (preserve prev ratio)    (fail-soft)
//!     3. `ratio = None`  → WarmUp (data_days < 3)         (fail-closed)
//!     4. `ratio NaN/Inf` → Anomaly                        (defensive)
//!     5. `ratio <= threshold` → Trigger                   (advisory hit)
//!     6. else            → OK
//!
//!   The Stale case deliberately echoes a `prev_ratio` so observability
//!   tools (healthcheck [22]) can report what the last known value was
//!   while annotating the staleness; this is purely advisory and does
//!   NOT influence trading.
//!
//!   The transition timestamp (`triggered_at_ms`) is owned by the daemon
//!   because evaluate() is pure and has no notion of "previous state".
//!   `evaluate()` always returns `triggered_at_ms = now_ms` for any Trigger
//!   state (correct for the first entry); the daemon then enforces sticky
//!   semantics (mod.rs ~L240) by **overwriting** the field with the
//!   previously stored `triggered_at_ms` on contiguous Trigger→Trigger
//!   cycles, leaving it as `now_ms` only on the entering transition.
//!   `triggered_at_ms` therefore reflects "when did this contiguous Trigger
//!   episode begin" — not "last time evaluate ran".
//!
//! MODULE_NOTE (中)：`evaluate()` 為純 fn — 無 I/O、無全域狀態，確定性映射
//!   `(snapshot, cfg, is_stale, now_ms) → state`。Daemon（mod.rs）每 10s
//!   呼叫並處理 transition emit；測試直接驅動本 fn 走遍 state machine。
//!
//!   Evaluation 優先序（PA RFC §4.2 line 305）：
//!     1. `!cfg.enabled`  → Disabled    （short-circuit）
//!     2. `is_stale`      → Stale       （fail-soft，保留 prev ratio）
//!     3. `ratio = None`  → WarmUp      （data_days < 3，fail-closed）
//!     4. `ratio NaN/Inf` → Anomaly     （防禦）
//!     5. `ratio <= threshold` → Trigger（advisory hit）
//!     6. else            → OK
//!
//!   Stale case 刻意 echo `prev_ratio`：observability（healthcheck [22]）可
//!   報「上次值＋現在 stale」；純 advisory，不影響交易。
//!
//!   `triggered_at_ms` 由 daemon 持有（pure fn 無 prev state 概念）。
//!   `evaluate()` 對任何 Trigger 狀態永遠回 `triggered_at_ms = now_ms`
//!   （首次進入時正確）；daemon 在 mod.rs 約 L240 強制 sticky 語意：
//!   contiguous Trigger→Trigger cycle 時 **覆寫**為前次儲存的
//!   `triggered_at_ms`，僅 entering transition 保留 `now_ms`。
//!   因此 `triggered_at_ms` 反映「此連續 Trigger 區段何時開始」而非
//!   「上次 evaluate 何時跑」。

use super::types::{CostEdgeAdvisorState, CostEdgeAdvisorStatus};
use crate::config::CostEdgeConfig;
use crate::h_state_cache::HStateSnapshot;

/// Pure evaluation of advisor state from inputs.
///
/// EN: This fn has no awareness of the previous state — it produces the
///   "should-be" state given the current snapshot + config + staleness +
///   timestamp. The daemon (mod.rs) wraps this with transition tracking
///   (Trigger entering vs sticky timestamp).
///
///   `prev_ratio` is supplied for the Stale path so the returned state can
///   echo the last known ratio without forcing the daemon to read its own
///   `state` lock (which would create a write-after-read pattern). Pass
///   `None` if no prior ratio is available.
///
/// 中：本 fn 不知 prev state — 給定 snapshot + cfg + staleness + 時戳產出
///   「應為」state。Daemon（mod.rs）外包 transition tracking（首次進
///   Trigger vs sticky timestamp）。
///
///   `prev_ratio` 為 Stale path 而設，避免 daemon 為了 echo 上次 ratio 而
///   read 自己的 state lock（變成 write-after-read pattern）。無前值則傳
///   `None`。
pub fn evaluate(
    snapshot: &HStateSnapshot,
    cfg: &CostEdgeConfig,
    is_stale: bool,
    now_ms: i64,
) -> CostEdgeAdvisorState {
    // Step 1: short-circuit on disabled (skip H state read — saves cycle).
    // Step 1：disabled 短路（跳過 H state 讀取，省 cycle）。
    if !cfg.enabled {
        return CostEdgeAdvisorState::disabled(cfg.trigger_threshold, now_ms);
    }

    // Step 2: stale → fail-soft, preserve last known ratio.
    // Step 2：stale → fail-soft，保留上次 ratio。
    if is_stale {
        return CostEdgeAdvisorState::stale(
            snapshot.h5.cost_edge_ratio,
            cfg.trigger_threshold,
            now_ms,
        );
    }

    let ratio_opt = snapshot.h5.cost_edge_ratio;
    let data_days = snapshot.h5.data_days;
    let threshold = cfg.trigger_threshold;

    match ratio_opt {
        // Step 3: ratio=None → WarmUp (data_days < ADAPTIVE_MIN_DAYS=3).
        // Step 3：ratio=None → WarmUp（樣本不足）。
        None => CostEdgeAdvisorState::warm_up(threshold, data_days, now_ms),
        // Step 4: NaN/Inf defensive guard.
        // Step 4：NaN/Inf 防禦守衛。
        Some(r) if !r.is_finite() => CostEdgeAdvisorState::anomaly(r, threshold, now_ms),
        // Step 5: ratio <= threshold → Trigger.
        // Step 5：ratio <= threshold → Trigger。
        Some(r) if r <= threshold => {
            CostEdgeAdvisorState::trigger(
                r,
                threshold,
                data_days,
                snapshot.h5.ai_spend_7d_usd,
                snapshot.h5.paper_pnl_7d_usd,
                now_ms,
                // Daemon override (sticky semantics, mod.rs ~L240):
                //   - On non-Trigger → Trigger transition the daemon keeps
                //     this `now_ms` value (correct fresh entry timestamp).
                //   - On contiguous Trigger → Trigger cycles the daemon
                //     overwrites this with the previously stored
                //     `triggered_at_ms` so the entry timestamp survives
                //     repeated evaluate() calls.
                // Pure fn has no notion of "previous status", so it always
                // returns `now_ms`; the daemon owns the sticky history.
                // Daemon override（sticky 語意，mod.rs 約 L240）：
                //   - non-Trigger → Trigger 進入時 daemon 沿用本 `now_ms`
                //     （正確的首次進入時戳）。
                //   - 連續 Trigger → Trigger cycle 時 daemon 用前一次儲存的
                //     `triggered_at_ms` 覆寫，使進入時戳不被反覆 evaluate()
                //     蓋掉。
                // Pure fn 無 prev status 概念，故永遠回 `now_ms`；sticky 歷史
                // 由 daemon 持有。
                now_ms,
            )
        }
        // Step 6: ratio > threshold → OK.
        // Step 6：ratio > threshold → OK。
        Some(r) => CostEdgeAdvisorState::ok(
            r,
            threshold,
            data_days,
            snapshot.h5.ai_spend_7d_usd,
            snapshot.h5.paper_pnl_7d_usd,
            now_ms,
        ),
    }
}

/// Helper: classify the next status without producing a full state. Used by
/// transition-tracking logic in the daemon when it only needs to know
/// whether a state change occurred.
/// 輔助：只算下一個 status 不產完整 state。Daemon transition tracking 只需
/// 知狀態是否變化時用。
pub fn next_status(
    snapshot: &HStateSnapshot,
    cfg: &CostEdgeConfig,
    is_stale: bool,
) -> CostEdgeAdvisorStatus {
    if !cfg.enabled {
        return CostEdgeAdvisorStatus::Disabled;
    }
    if is_stale {
        return CostEdgeAdvisorStatus::Stale;
    }
    match snapshot.h5.cost_edge_ratio {
        None => CostEdgeAdvisorStatus::WarmUp,
        Some(r) if !r.is_finite() => CostEdgeAdvisorStatus::Anomaly,
        Some(r) if r <= cfg.trigger_threshold => CostEdgeAdvisorStatus::Trigger,
        Some(_) => CostEdgeAdvisorStatus::Ok,
    }
}
