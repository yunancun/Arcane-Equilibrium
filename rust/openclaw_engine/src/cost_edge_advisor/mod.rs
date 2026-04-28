//! G3-09 cost_edge_advisor — Phase A advisory-only AI cost awareness module.
//! G3-09 cost_edge_advisor — Phase A 純 advisory AI 成本感知模組。
//!
//! MODULE_NOTE (EN): Lifts CLAUDE.md §二 原則 #13「AI 資源成本感知 — 每次 AI
//!   調用計費，cost_edge_ratio ≥ 0.8 → 建議關倉」into Rust hot-path with a
//!   single-responsibility module that is **strictly read-only** to all
//!   trading state. Advisor reads `h_state_cache.snapshot().h5.cost_edge_ratio`
//!   every 10s, evaluates against a configurable threshold, and emits
//!   structured audit events on status transitions. The advisor does NOT:
//!     - reject any intent (Phase B/C scope, deferred)
//!     - close any position (CLAUDE.md §二 #5 生存>利潤 反向防線)
//!     - modify any config (read-only on RiskConfig)
//!
//!   Phase A integration points (per PA RFC `2026-04-26--g3_09_cost_edge_ratio_design.md`):
//!     1. `main_boot_tasks::spawn_cost_edge_advisor_if_enabled` — env-gate +
//!        RiskConfig flag dual safeguard (per §9.1-9.2 of RFC).
//!     2. IPC handler `get_cost_edge_advisor_status` — exposes status snapshot
//!        for healthcheck [22] + GUI consumption.
//!     3. Audit emit via fire-and-forget `observability.engine_events` insert
//!        on Trigger transition + StatusChange (mirrors handlers_config.rs
//!        config_patch audit pattern; no separate AuditEvent enum exists).
//!
//!   Status state machine (per types.rs CostEdgeAdvisorStatus):
//!
//!     Uninitialized ─env=1+enabled=true─▶ WarmUp ─data_days≥3─▶ OK ─ratio↘─▶ Trigger
//!           ▲                                                       ▲   │
//!           │                                                       └───┘
//!           env=0  ◀──────── Disabled ◀── enabled=false ──┐
//!                                                          │
//!     Stale ◀── h_state_cache.is_stale() == true ──────────┤
//!                                                          │
//!     Anomaly ◀── ratio is NaN/Inf ─────────────────────────┘
//!
//!   Crash resilience: advisor daemon polls H state cache; on Python crash the
//!   cache stays at last-good snapshot but `is_stale()` flips true → advisor
//!   enters Stale state (no false trigger). On Rust restart the advisor
//!   re-spawns from default state (Uninitialized → ... fresh state machine).
//!
//!   Hot-path performance: evaluate() is pure fn O(1) — single h_state_cache
//!   snapshot clone (shared `Arc<HStateSnapshot>` ~50 fields, ≤1μs) +
//!   threshold compare. Daemon cycle every 10s = 6 evals/min, negligible CPU.
//!
//! MODULE_NOTE (中)：把 CLAUDE.md §二 原則 #13 「AI 成本感知」升為 Rust
//!   hot-path 一級模組。Single-responsibility 設計：對所有交易狀態**唯讀**。
//!   Advisor 每 10s 讀 H5 snapshot、比對閾值、狀態變化時 emit 結構化 audit。
//!   Advisor **不**：reject 任何 intent（Phase B/C）/ close 任何倉位
//!   （CLAUDE.md §二 #5 生存>利潤 反向防線）/ 改任何 config（對 RiskConfig
//!   唯讀）。
//!
//!   Phase A 整合點（PA RFC `2026-04-26--g3_09_cost_edge_ratio_design.md`）：
//!     1. `main_boot_tasks::spawn_cost_edge_advisor_if_enabled` — env-gate +
//!        RiskConfig flag 雙保險（RFC §9.1-9.2）。
//!     2. IPC handler `get_cost_edge_advisor_status` — 暴露 status snapshot 給
//!        healthcheck [22] + GUI。
//!     3. Audit emit 走 fire-and-forget `observability.engine_events` insert
//!        （對齊 handlers_config.rs config_patch audit pattern；codebase 無
//!        統一 AuditEvent enum）。
//!
//!   崩潰韌性：Python crash → H state cache 維持 last-good snapshot 但
//!   `is_stale()` 為 true → advisor 進 Stale（不誤 trigger）。Rust 重啟 →
//!   advisor 從 Uninitialized 重建狀態機。
//!
//!   Hot-path 效能：evaluate() 純 fn O(1)，每 10s 6 次 eval/min CPU 可忽略。

use crate::config::{ConfigStore, RiskConfig};
use crate::h_state_cache::HStateCache;
use parking_lot::RwLock;
use std::sync::Arc;
use std::time::Duration;
use tokio::task::JoinHandle;
use tokio_util::sync::CancellationToken;
use tracing::{info, warn};

pub mod advisor;
pub mod types;

#[cfg(test)]
mod tests;

pub use types::{CostEdgeAdvisorState, CostEdgeAdvisorStatus};

/// Env var that gates cost_edge_advisor (PA RFC §9.1).
/// Strict-equality comparison with `"1"` — any other value (including
/// `"true"` / `"yes"` / unset) keeps advisor off (DEFAULT-OFF). Mirrors
/// G3-08 `OPENCLAW_H_STATE_GATEWAY` pattern.
/// 控管 cost_edge_advisor 的環境變數（PA RFC §9.1）。與 `"1"` 嚴格相等比對；
/// 其他值（`"true"`、`"yes"`、未設）皆視為關閉（DEFAULT-OFF），對齊 G3-08
/// `OPENCLAW_H_STATE_GATEWAY` pattern。
pub const ENV_ADVISOR_FLAG: &str = "OPENCLAW_COST_EDGE_ADVISOR";

/// Default poll interval — 10s (matches H state cache poller cadence per
/// PA RFC §11 line 913 high-risk warning #1: must align with H state poll
/// to avoid race on rapid invalidation).
/// 預設 poll 間隔 10s（對齊 H state cache poller 節奏，PA RFC §11 line 913
/// 高風險警告 #1：必須與 H state poll 節奏對齊以避免 invalidation 競態）。
pub const DEFAULT_POLL_INTERVAL: Duration = Duration::from_secs(10);

/// Check whether the cost_edge_advisor env-gate is enabled.
/// Strict comparison with `"1"`. Any other value keeps advisor off.
/// 檢查 cost_edge_advisor env-gate 是否啟用（嚴格 `"1"` 比較）。
pub fn is_advisor_env_enabled() -> bool {
    std::env::var(ENV_ADVISOR_FLAG).as_deref() == Ok("1")
}

/// Unix epoch milliseconds — local utility (mirrors `h_state_cache::unix_now_ms`).
/// Unix 紀元毫秒 — 本模組工具（鏡射 `h_state_cache::unix_now_ms`）。
pub(crate) fn unix_now_ms() -> i64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0)
}

/// Cost-edge advisor — wraps the latest evaluated state under `RwLock`.
///
/// EN: The advisor's only mutable state is its current `CostEdgeAdvisorState`
///   (status / ratio / threshold / data_days / timestamps). Daemon writes
///   on every poll cycle; IPC handler + healthcheck read concurrently.
///   `parking_lot::RwLock` chosen over `tokio::RwLock` because the critical
///   section is purely synchronous (state struct clone) — no .await inside.
///
/// 中: Advisor 唯一可變狀態是當前 `CostEdgeAdvisorState`（status / ratio /
///   threshold / data_days / timestamps）。Daemon 每輪 poll 寫入；IPC
///   handler 與 healthcheck 並行讀。用 `parking_lot::RwLock` 而非
///   `tokio::RwLock` 因 critical section 純同步（state struct clone），無
///   .await。
pub struct CostEdgeAdvisor {
    state: RwLock<CostEdgeAdvisorState>,
}

impl CostEdgeAdvisor {
    /// Build a fresh advisor in `Uninitialized` state. Used by daemon spawn
    /// and tests.
    /// 建立 `Uninitialized` 狀態的全新 advisor。Daemon spawn 與測試共用。
    pub fn new() -> Self {
        Self {
            state: RwLock::new(CostEdgeAdvisorState::uninitialized()),
        }
    }

    /// Build an advisor wrapped in `Arc` for daemon + IPC handler sharing.
    /// 建立包在 `Arc` 內的 advisor，給 daemon 與 IPC handler 共享。
    pub fn new_arc() -> Arc<Self> {
        Arc::new(Self::new())
    }

    /// Read a clone of the current state. Holds the read lock briefly.
    /// 讀當前 state 的 clone（短暫持 read lock）。
    pub fn state(&self) -> CostEdgeAdvisorState {
        self.state.read().clone()
    }

    /// Atomically replace the current state. Daemon-only call site.
    /// 原子替換當前 state（僅 daemon 呼叫）。
    pub fn store_state(&self, new_state: CostEdgeAdvisorState) {
        *self.state.write() = new_state;
    }
}

impl Default for CostEdgeAdvisor {
    fn default() -> Self {
        Self::new()
    }
}

/// Spawn the cost_edge_advisor daemon.
///
/// EN: Reads the latest H state snapshot every `poll_interval` (default 10s),
///   evaluates the threshold via `advisor::evaluate`, and emits a status
///   transition log + audit hint when the status changes. Audit DB INSERT is
///   delegated to the caller (Phase A ships without audit pool wiring; the
///   transition log carries enough info for E4 regression).
///
///   Daemon ownership: returns `JoinHandle<()>`; caller is responsible for
///   `await`-ing it on shutdown (paired with `cancel.cancel()`). The daemon
///   task is cancellation-safe — every loop iteration races
///   `cancel.cancelled()` against `tokio::time::sleep`, ensuring sub-second
///   shutdown latency.
///
/// 中：每 `poll_interval`（預設 10s）讀 H state snapshot、用 `advisor::evaluate`
///   比對閾值、狀態變化時 emit transition log + audit hint。Audit DB INSERT
///   交由 caller 處理（Phase A 不接 audit pool；transition log 已含 E4
///   regression 所需資訊）。
///
///   Daemon 擁有權：回 `JoinHandle<()>`，caller 負責 shutdown 時 `await`
///   （搭配 `cancel.cancel()`）。Cancellation-safe：每輪 race
///   `cancel.cancelled()` 與 `sleep`，sub-second shutdown latency。
pub fn spawn_cost_edge_advisor(
    advisor: Arc<CostEdgeAdvisor>,
    h_state_cache: Arc<HStateCache>,
    risk_config: Arc<ConfigStore<RiskConfig>>,
    poll_interval: Duration,
    cancel: CancellationToken,
) -> JoinHandle<()> {
    tokio::spawn(async move {
        info!(
            poll_interval_ms = poll_interval.as_millis() as u64,
            "cost_edge_advisor daemon started / cost_edge_advisor 守護進程已啟動"
        );

        let mut prev_status = CostEdgeAdvisorStatus::Uninitialized;
        // Sticky timestamp of the *current* contiguous Trigger run. `0` when
        // we are not currently in Trigger. Set to `now_ms` on the OK→Trigger
        // (or any non-Trigger → Trigger) transition, preserved across
        // subsequent Trigger→Trigger evaluate cycles, cleared on
        // Trigger→non-Trigger transition. Pure-fn `evaluate()` cannot know
        // the previous status — the daemon owns this history (see
        // advisor.rs §"`triggered_at_ms`" docstring).
        // 當前連續 Trigger 區段的 sticky 時戳。非 Trigger 時為 `0`；
        // 任意 non-Trigger → Trigger 時設為 `now_ms`，後續 Trigger→Trigger
        // 評估保留不變，Trigger → non-Trigger 時清零。Pure fn 無 prev
        // status 概念，由 daemon 持有此歷史（見 advisor.rs §triggered_at_ms
        // docstring）。
        let mut sticky_triggered_at_ms: i64 = 0;

        loop {
            tokio::select! {
                _ = cancel.cancelled() => {
                    info!("cost_edge_advisor daemon shutting down / cost_edge_advisor 關閉中");
                    break;
                }
                _ = tokio::time::sleep(poll_interval) => {
                    // Lock-free ArcSwap load; cheap on hot path.
                    // Lock-free ArcSwap load；hot path 便宜。
                    let cfg_arc = risk_config.load();
                    let cfg = &cfg_arc.cost_edge;
                    let snapshot = h_state_cache.snapshot();
                    let is_stale = h_state_cache.is_stale();

                    let mut new_state = advisor::evaluate(&snapshot, cfg, is_stale, unix_now_ms());

                    // Sticky `triggered_at_ms` enforcement (G3-09-PHASE-B-FUP
                    // 2026-04-28). `evaluate()` is pure and always returns
                    // `triggered_at_ms = now_ms` for any Trigger state — that
                    // is correct for the *first* Trigger but would
                    // overwrite the entry timestamp on every subsequent
                    // Trigger→Trigger cycle. Phase B observation, dedup
                    // analytics, and the `last_trigger_ms` rolling counter
                    // all rely on the sticky semantics ("when did this
                    // Trigger episode begin"), so the daemon overrides
                    // `triggered_at_ms` here to preserve the original
                    // entry timestamp across contiguous Trigger cycles.
                    // Sticky `triggered_at_ms` 強制（G3-09-PHASE-B-FUP，
                    // 2026-04-28）。`evaluate()` 為 pure fn，Trigger 永遠回
                    // `triggered_at_ms = now_ms` — 首次進 Trigger 正確，但連續
                    // Trigger→Trigger 會每 cycle 蓋掉「進入時間」。Phase B
                    // observation / dedup analytics / `last_trigger_ms` rolling
                    // counter 全依賴 sticky 語意（「此 Trigger 區段何時開始」），
                    // daemon 在此覆寫 `triggered_at_ms` 保留 contiguous Trigger
                    // 區段的原始進入時戳。
                    match (&prev_status, &new_state.status) {
                        // Continuing Trigger run — preserve original entry timestamp.
                        // 持續 Trigger 區段 — 保留原進入時戳。
                        (CostEdgeAdvisorStatus::Trigger, CostEdgeAdvisorStatus::Trigger) => {
                            new_state.triggered_at_ms = sticky_triggered_at_ms;
                        }
                        // Entering Trigger from any other state — record entry timestamp.
                        // 從其他狀態進入 Trigger — 記錄進入時戳。
                        (_, CostEdgeAdvisorStatus::Trigger) => {
                            sticky_triggered_at_ms = new_state.triggered_at_ms;
                        }
                        // Leaving Trigger — clear sticky timestamp so the next entry
                        // captures a fresh `now_ms` (state factories already set
                        // `triggered_at_ms = 0` for non-Trigger variants).
                        // 離開 Trigger — 清零 sticky；下次進入會抓新 `now_ms`
                        // （state factory 對 non-Trigger 變體已預設 0）。
                        (CostEdgeAdvisorStatus::Trigger, _) => {
                            sticky_triggered_at_ms = 0;
                        }
                        // Non-Trigger → non-Trigger — no-op for sticky timestamp.
                        // 非 Trigger → 非 Trigger — sticky 不動。
                        _ => {}
                    }

                    // Emit transition log on any status change. Trigger
                    // events get a richer warn-level log carrying ratio +
                    // threshold + 7d window context.
                    // 狀態變化時 emit transition log；Trigger 額外 warn-level
                    // 帶 ratio + threshold + 7d window context。
                    if new_state.status != prev_status {
                        match &new_state.status {
                            CostEdgeAdvisorStatus::Trigger => {
                                warn!(
                                    prev = ?prev_status,
                                    new = ?new_state.status,
                                    ratio = new_state.ratio.unwrap_or(f64::NAN),
                                    threshold = cfg.trigger_threshold,
                                    data_days = new_state.data_days,
                                    ai_spend_7d_usd = new_state.ai_spend_7d_usd,
                                    paper_pnl_7d_usd = new_state.paper_pnl_7d_usd,
                                    triggered_at_ms = new_state.triggered_at_ms,
                                    phase = "A_advisory",
                                    "cost_edge_advisor TRIGGER (Phase A advisory only — \
                                     no trade impact) / cost_edge_advisor 觸發 \
                                     （Phase A 純 advisory，不影響交易）"
                                );
                            }
                            _ => {
                                info!(
                                    prev = ?prev_status,
                                    new = ?new_state.status,
                                    ratio = ?new_state.ratio,
                                    "cost_edge_advisor status transition / \
                                     cost_edge_advisor 狀態轉換"
                                );
                            }
                        }
                    }

                    prev_status = new_state.status;
                    advisor.store_state(new_state);
                }
            }
        }
    })
}
