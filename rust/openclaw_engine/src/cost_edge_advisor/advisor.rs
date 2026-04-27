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
//!   The transition timestamp (`triggered_at_ms`) is computed by the
//!   caller (daemon) because evaluate() is pure and has no notion of
//!   "previous state" — the daemon owns that history. The daemon passes
//!   either `now_ms` (entering Trigger from non-Trigger) or the previous
//!   Trigger's timestamp (Trigger→Trigger sticky) as `transition_at_ms`
//!   into the Trigger constructor.
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
//!   `triggered_at_ms` 由 daemon 算（pure fn 無 prev state 概念，由 daemon
//!   持有歷史）；daemon 在進入 Trigger 時傳 `now_ms`，Trigger→Trigger sticky
//!   時傳前一次 Trigger 的時戳。

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
                // Daemon override: when this is the entering Trigger
                // transition, daemon will overwrite triggered_at_ms via
                // a follow-up `store_state` cycle. Pure fn cannot know;
                // we default to now_ms which is correct for fresh trigger.
                // Daemon 進入 Trigger 時會 overwrite triggered_at_ms；
                // pure fn 無法知，預設 now_ms（首次進 Trigger 即正確）。
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
