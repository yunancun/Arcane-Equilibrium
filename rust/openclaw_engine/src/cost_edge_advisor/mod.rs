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
use crate::database::pool::DbPool;
use crate::h_state_cache::HStateCache;
use parking_lot::RwLock;
use std::collections::VecDeque;
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

/// Phase B (G3-09 2026-04-28) down-sample interval — write at most one
/// cycle row per minute to `learning.cost_edge_advisor_log`. Transition
/// rows (status change) bypass this interval and INSERT immediately so
/// burst patterns are fully captured (PA RFC §2.5 + §6.1 R-B5).
/// Phase B down-sample 間隔 — 每分鐘最多寫一次 cycle row 到
/// `learning.cost_edge_advisor_log`；transition row（狀態變化）不受此
/// 限制，立即 INSERT 確保 burst 100% 紀錄（PA RFC §2.5 + §6.1 R-B5）。
pub const PHASE_B_INSERT_DOWNSAMPLE_MS: i64 = 60_000;

/// 24h rolling window in milliseconds — counter trim cutoff for
/// `evaluations_24h` and `triggers_24h`.
/// 24h rolling 視窗（毫秒）— `evaluations_24h` / `triggers_24h` 的修剪邊界。
pub const ROLLING_WINDOW_24H_MS: i64 = 86_400_000;

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

/// Phase B (G3-09 2026-04-28) rolling counters maintained inside the daemon
/// task scope. Lock-free, no shared state — pure VecDeque trim/push driven
/// by the daemon's own loop.
///
/// EN: `eval_timestamps` records every `evaluate()` cycle ts; on each push
///   we trim entries older than `now - ROLLING_WINDOW_24H_MS`. Same trim
///   pattern for `trigger_timestamps` (only entry transitions). The
///   `last_trigger_ms` is **not** trimmed — it is a "stickiest" timestamp
///   that survives Trigger exit so observation tools have a stable
///   "when did this last fire?" anchor (cf RFC §3.1).
///
/// 中：daemon task scope 內維護的 Phase B rolling 計數。lock-free 無共享 state
///   — VecDeque trim/push 由 daemon 自己驅動。`eval_timestamps` 記每次
///   `evaluate()` 的 ts，每 push 修剪 `now - ROLLING_WINDOW_24H_MS` 之前；
///   `trigger_timestamps` 同 pattern（只記 entry transition）。`last_trigger_ms`
///   **不**修剪 — 是 stickiest 時戳，Trigger 退出後仍保留，給觀察工具穩定的
///   「最後一次燒錢」錨點（RFC §3.1）。
struct EvalCounters {
    eval_timestamps: VecDeque<i64>,
    trigger_timestamps: VecDeque<i64>,
    last_trigger_ms: i64,
    daemon_start_ms: i64,
    last_insert_ms: i64,
}

impl EvalCounters {
    fn new(daemon_start_ms: i64) -> Self {
        Self {
            eval_timestamps: VecDeque::new(),
            trigger_timestamps: VecDeque::new(),
            last_trigger_ms: 0,
            daemon_start_ms,
            // `0` so the first cycle past the down-sample window writes a
            // baseline row instead of waiting 60s.
            // `0` 讓首次 cycle 超過 down-sample 窗時即寫 baseline，免等 60s。
            last_insert_ms: 0,
        }
    }

    /// Record a finished `evaluate()` cycle and trim 24h-stale entries.
    /// 記錄一次 `evaluate()` cycle 並修剪 24h 過期項目。
    fn record_cycle(&mut self, now_ms: i64) {
        self.eval_timestamps.push_back(now_ms);
        let cutoff = now_ms.saturating_sub(ROLLING_WINDOW_24H_MS);
        // Pop from front while front entry is older than cutoff. Loop
        // continues until empty or front >= cutoff (NOT just one pop —
        // a cycle gap could leave many stale entries waiting).
        // 從前端不斷 pop，直到空或 front >= cutoff（**非**只 pop 一次 —
        // cycle 間隙可能堆積多個 stale 項目）。
        while self
            .eval_timestamps
            .front()
            .is_some_and(|&ts| ts < cutoff)
        {
            self.eval_timestamps.pop_front();
        }
    }

    /// Record an entry into Trigger (non-Trigger → Trigger transition only).
    /// 記錄一次進入 Trigger（僅 non-Trigger → Trigger transition）。
    fn record_trigger_entry(&mut self, now_ms: i64) {
        self.trigger_timestamps.push_back(now_ms);
        self.last_trigger_ms = now_ms;
        let cutoff = now_ms.saturating_sub(ROLLING_WINDOW_24H_MS);
        while self
            .trigger_timestamps
            .front()
            .is_some_and(|&ts| ts < cutoff)
        {
            self.trigger_timestamps.pop_front();
        }
    }

    fn evaluations_24h(&self) -> u64 {
        self.eval_timestamps.len() as u64
    }

    fn triggers_24h(&self) -> u64 {
        self.trigger_timestamps.len() as u64
    }
}

/// Build the `cost_edge_advisor_log` INSERT row payload from a state +
/// transition context. Pure fn so unit tests can drive it without a daemon.
///
/// EN: `transition_from` is `Some(prev_status_str)` only when status changed
///   this cycle; otherwise `None` (down-sampled cycle row). Phase tag is
///   pinned to `"B_shadow"` per RFC §3.2 — Phase C will write `"C_gated"`.
///
/// 中：`transition_from` 僅在 cycle 內 status 變化時為 `Some(prev_status_str)`，
///   否則為 `None`（down-sampled cycle row）。Phase 標籤固定 `"B_shadow"`
///   （RFC §3.2），Phase C 會寫 `"C_gated"`。
#[derive(Debug, Clone)]
pub(crate) struct CostEdgeAdvisorLogRow {
    pub ts_ms: i64,
    pub engine_mode: String,
    pub status: String,
    pub ratio: Option<f64>,
    pub threshold: f64,
    pub data_days: i32,
    pub ai_spend_7d_usd: f64,
    pub paper_pnl_7d_usd: f64,
    pub is_stale: bool,
    pub phase: String,
    pub transition_from: Option<String>,
}

impl CostEdgeAdvisorLogRow {
    pub(crate) fn build(
        state: &CostEdgeAdvisorState,
        engine_mode: &str,
        is_stale: bool,
        transition_from: Option<&CostEdgeAdvisorStatus>,
    ) -> Self {
        Self {
            ts_ms: state.last_eval_ms,
            engine_mode: engine_mode.to_string(),
            status: state.status.as_str().to_string(),
            ratio: state.ratio,
            threshold: state.threshold,
            // `data_days` is u32 in the snapshot but the SQL column is INTEGER
            // (i32). Saturating cast keeps the daemon panic-free if a future
            // bug pushed an out-of-i32 value.
            // `data_days` 在 snapshot 是 u32，SQL 欄位是 INTEGER (i32)，用
            // saturating cast 防未來 bug 把超 i32 的值塞進來時 daemon panic。
            data_days: state.data_days.min(i32::MAX as u32) as i32,
            ai_spend_7d_usd: state.ai_spend_7d_usd,
            paper_pnl_7d_usd: state.paper_pnl_7d_usd,
            is_stale,
            phase: "B_shadow".to_string(),
            transition_from: transition_from.map(|s| s.as_str().to_string()),
        }
    }
}

/// Fire-and-forget INSERT into `learning.cost_edge_advisor_log`.
///
/// EN: Spawned as `tokio::spawn(async move {...})` so the caller (daemon
///   loop) does NOT await DB I/O — pool exhaustion / DB latency cannot
///   stall the 10s evaluate cadence (RFC §6.1 R-B1 + R-B7 mitigation).
///   On error we `warn!` only; rate-limiting via the down-sample interval
///   keeps log spam bounded to ≤1/min for cycle rows.
///
/// 中：包在 `tokio::spawn(async move {...})` 內 fire-and-forget；daemon
///   loop **不** await DB I/O — pool 飽和 / DB 慢無法拖累 10s evaluate
///   cadence（RFC §6.1 R-B1 + R-B7 緩解）。失敗只 `warn!`；down-sample 限速
///   讓 log spam 固定 ≤1/min（cycle row）。
async fn insert_advisor_log_row(pool: sqlx::PgPool, row: CostEdgeAdvisorLogRow) {
    let res = sqlx::query(
        "INSERT INTO learning.cost_edge_advisor_log \
         (ts_ms, engine_mode, status, ratio, threshold, data_days, \
          ai_spend_7d_usd, paper_pnl_7d_usd, is_stale, phase, transition_from) \
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) \
         ON CONFLICT (ts_ms, engine_mode) DO NOTHING",
    )
    .bind(row.ts_ms)
    .bind(&row.engine_mode)
    .bind(&row.status)
    .bind(row.ratio)
    .bind(row.threshold)
    .bind(row.data_days)
    .bind(row.ai_spend_7d_usd)
    .bind(row.paper_pnl_7d_usd)
    .bind(row.is_stale)
    .bind(&row.phase)
    .bind(row.transition_from.as_deref())
    .execute(&pool)
    .await;
    if let Err(e) = res {
        // Down-sample limits cycle-row spam to ≤1/min; transition rows are
        // rare. Worst-case spam = 1 warn per minute under sustained DB outage.
        // Down-sample 限 cycle row spam ≤1/min；transition row 罕見。
        // DB 持續異常時最壞 1 warn/分。
        warn!(
            error = %e,
            engine_mode = %row.engine_mode,
            status = %row.status,
            "cost_edge_advisor_log INSERT failed (Phase B observability) / \
             cost_edge_advisor_log INSERT 失敗（Phase B 觀測）"
        );
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
    // Phase B (G3-09 2026-04-28) backwards-compat shim — delegates to the
    // richer `spawn_cost_edge_advisor_with_persistence` with persistence
    // disabled. Keeps the 11 existing Phase A daemon integration tests
    // green without modification (they pass 5 args; this preserves the
    // original 5-arg spawn shape).
    // Phase B 向後相容 shim — 委派至 `spawn_cost_edge_advisor_with_persistence`
    // 並關閉 persistence。讓 11 個 Phase A daemon 整合測試（傳 5 個 arg）
    // 保留原 spawn 形狀無須修改即可繼續綠。
    spawn_cost_edge_advisor_with_persistence(
        advisor,
        h_state_cache,
        risk_config,
        poll_interval,
        cancel,
        // No DB pool → INSERT path skipped; counters still maintained
        // for IPC observability.
        // 無 DB pool → INSERT 跳過；counter 仍維護供 IPC 觀測。
        None,
        // engine_mode unused when pool is None; default to "demo" for
        // structured-log consistency in test runs.
        // pool 為 None 時 engine_mode 無用；測試 log 一致性預設 "demo"。
        "demo".to_string(),
    )
}

/// Spawn the cost_edge_advisor daemon with optional Phase B DB persistence.
///
/// EN: Phase B-aware variant of `spawn_cost_edge_advisor`. When `db_pool`
///   resolves to a live `PgPool`, the daemon writes evaluate snapshots to
///   `learning.cost_edge_advisor_log` (down-sampled 1/min for cycle rows;
///   transition rows bypass the down-sample). When pool is `None` or the
///   inner `DbPool` reports `is_available()=false`, INSERT path is silently
///   skipped — daemon still maintains in-memory counters for IPC.
///
///   `engine_mode` is bound at spawn time (`paper` / `demo` / `live` /
///   `live_demo`) and stamped into every INSERT row; advisor is per-engine
///   so this never changes mid-run (RFC §6.1 R-B9).
///
///   The Phase B counter rolling window (`evaluations_24h` / `triggers_24h`)
///   is in-memory only — engine restart resets it. Use the DB log for
///   absolute liveness assertions; use IPC counters for "what just happened
///   in the last day" diagnostics.
///
/// 中：`spawn_cost_edge_advisor` 的 Phase B 變體。`db_pool` 解析到活的
///   `PgPool` 時 daemon 寫 evaluate snapshot 到 `learning.cost_edge_advisor_log`
///   （cycle row 1/min down-sample；transition row 不 down-sample）。pool 為
///   `None` 或內 `DbPool.is_available()=false` 時靜默跳過 INSERT，daemon 仍
///   維護記憶體 counter 供 IPC。
///
///   `engine_mode` 在 spawn 時綁定（`paper`/`demo`/`live`/`live_demo`），
///   每筆 INSERT row 蓋章；advisor 是 per-engine 故 mid-run 不會變
///   （RFC §6.1 R-B9）。
///
///   Phase B counter rolling 視窗（`evaluations_24h`/`triggers_24h`）是
///   in-memory only — engine restart 重置。絕對 liveness 看 DB log；
///   「最近一天發生什麼」看 IPC counter。
pub fn spawn_cost_edge_advisor_with_persistence(
    advisor: Arc<CostEdgeAdvisor>,
    h_state_cache: Arc<HStateCache>,
    risk_config: Arc<ConfigStore<RiskConfig>>,
    poll_interval: Duration,
    cancel: CancellationToken,
    db_pool: Option<Arc<DbPool>>,
    engine_mode: String,
) -> JoinHandle<()> {
    tokio::spawn(async move {
        let daemon_start_ms = unix_now_ms();
        info!(
            poll_interval_ms = poll_interval.as_millis() as u64,
            db_persistence = db_pool.is_some(),
            engine_mode = %engine_mode,
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

        // Phase B (G3-09 2026-04-28) rolling counters + down-sample tracking.
        // All in-memory — engine restart resets to 0 and starts a fresh
        // observation window (use DB log for absolute liveness).
        // Phase B rolling 計數 + down-sample 追蹤。全 in-memory，engine restart
        // 重置 0 並開新觀察窗（絕對 liveness 看 DB log）。
        let mut counters = EvalCounters::new(daemon_start_ms);

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

                    // Phase B: bookkeeping after sticky resolved + before
                    // log emit / persist. record_cycle on every cycle;
                    // record_trigger_entry only on entering transitions.
                    // Phase B：sticky 解析後、log emit / persist 前簿記。
                    // record_cycle 每 cycle；record_trigger_entry 只記入
                    // transition。
                    let now_ms = new_state.last_eval_ms;
                    counters.record_cycle(now_ms);
                    let entered_trigger = matches!(
                        (&prev_status, &new_state.status),
                        (s, CostEdgeAdvisorStatus::Trigger)
                            if !matches!(s, CostEdgeAdvisorStatus::Trigger)
                    );
                    if entered_trigger {
                        counters.record_trigger_entry(now_ms);
                    }

                    // Stamp Phase B observability fields onto the state
                    // before storing — IPC handler reads these directly.
                    // 寫入 Phase B observability 欄位後再 store — IPC handler
                    // 直接讀。
                    new_state.evaluations_24h = counters.evaluations_24h();
                    new_state.triggers_24h = counters.triggers_24h();
                    new_state.last_trigger_ms = counters.last_trigger_ms;
                    new_state.dryrun_observation_window_ms =
                        now_ms.saturating_sub(counters.daemon_start_ms);

                    // Decide whether to write a row to learning.cost_edge_advisor_log.
                    // Transition rows ALWAYS write (no down-sample); cycle
                    // rows write at most every PHASE_B_INSERT_DOWNSAMPLE_MS.
                    // Phase B 寫入 learning.cost_edge_advisor_log 判斷：
                    // transition row 永遠寫（不 down-sample）；cycle row 至多每
                    // PHASE_B_INSERT_DOWNSAMPLE_MS 寫一次。
                    let is_transition = new_state.status != prev_status;
                    let should_insert = is_transition
                        || (now_ms.saturating_sub(counters.last_insert_ms)
                            >= PHASE_B_INSERT_DOWNSAMPLE_MS);
                    if should_insert {
                        if let Some(pool_arc) = db_pool.as_ref() {
                            if let Some(pg) = pool_arc.get() {
                                let row = CostEdgeAdvisorLogRow::build(
                                    &new_state,
                                    &engine_mode,
                                    is_stale,
                                    if is_transition { Some(&prev_status) } else { None },
                                );
                                let pg = pg.clone();
                                tokio::spawn(insert_advisor_log_row(pg, row));
                            }
                            // pool_arc.get() == None → DB writes disabled
                            // (paper-only / config); silently skip.
                            // pool_arc.get() == None → DB 寫入 disabled
                            // （paper 模式 / config）；靜默跳過。
                        }
                        counters.last_insert_ms = now_ms;
                    }

                    // Emit transition log on any status change. Trigger
                    // events get a richer warn-level log carrying ratio +
                    // threshold + 7d window context.
                    // 狀態變化時 emit transition log；Trigger 額外 warn-level
                    // 帶 ratio + threshold + 7d window context。
                    if is_transition {
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
                                    triggers_24h = counters.triggers_24h(),
                                    // Phase tag advanced to "B_shadow" with
                                    // Phase B Wave 1 land (RFC §3.2).
                                    // Phase 標籤隨 Phase B Wave 1 推進到 "B_shadow"。
                                    phase = "B_shadow",
                                    "cost_edge_advisor TRIGGER (Phase B observation only — \
                                     no trade impact) / cost_edge_advisor 觸發 \
                                     （Phase B 純觀察，不影響交易）"
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
