//! Strategist periodic configurator — Rust-side tokio background task (R3-1).
//! 策略師定時配置器 — Rust 側 tokio 後台任務。
//!
//! MODULE_NOTE (EN): Single-instance scheduler (R3-1 fix: moved from Python FastAPI to
//!   Rust engine — uvicorn --workers=4 would create 4 racing schedulers). Every 5 min:
//!   1) Query fills table for per-strategy×symbol metrics (R4-6, R5-3, R5-4)
//!   2) Rank top-10 pairs by absolute deviation from target (R2 H-5)
//!   3) IPC call to Python ai_service.sock → strategist_evaluate (judge_edge via Ollama)
//!   4) Validate response: param_ranges bounds + weight sum=65±0.1 + delta clamp
//!      (R3-4; clamp default ±30% from `RiskConfig.strategist.max_param_delta_pct`,
//!      operator-tunable since STRATEGIST-TUNE-TARGET-CONFIG-1, 2026-04-25)
//!   5) Apply via PipelineCommand::UpdateStrategyParams
//!   Exponential backoff on IPC failure: 5m→30m→60m→4h cap (R4-2).
//!   Fail-closed: any error → skip cycle, retain current params.
//! MODULE_NOTE (中): 單實例排程器（R3-1 修復：從 Python FastAPI 移至 Rust 引擎——
//!   uvicorn --workers=4 會創建 4 個競爭排程器）。每 5 分鐘：
//!   1) 查詢 fills 表獲取逐策略×symbol 指標
//!   2) 按偏差排名取 top-10
//!   3) IPC 調用 Python ai_service.sock → strategist_evaluate
//!   4) 驗證回應：param_ranges 範圍 + weight sum=65 + delta ≤±30%
//!   5) 通過 PipelineCommand::UpdateStrategyParams 應用
//!   IPC 失敗指數退避：5m→30m→60m→4h 上限。

mod persist;

/// Re-export `load_latest_applied_params` at the `strategist_scheduler::`
/// namespace so `main.rs` call sites remain unchanged after the split.
/// 從 `persist` 子模組 re-export `load_latest_applied_params`，讓 `main.rs`
/// 呼叫路徑 `strategist_scheduler::load_latest_applied_params` 拆檔後不變。
pub use persist::load_latest_applied_params;

use crate::ai_service_client::AiServiceClient;
use crate::config::risk_config::RiskConfig;
use crate::config::store::ConfigStore;
use crate::strategies::ParamRange;
use crate::tick_pipeline::{PipelineCommand, PipelineKind};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::sync::atomic::{AtomicU32, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tokio::sync::mpsc::UnboundedSender;
use tokio_util::sync::CancellationToken;
use tracing::{debug, error, info, warn};

/// G3-11 STRATEGIST-CYCLE-OBSERVABILITY-1 (2026-04-25, MVP slice).
/// Thread-safe cycle counters: per-reason reject tally + apply count + last-ts.
/// Exposed via IPC (`get_strategist_cycle_metrics`) so the GUI can replace the
/// engine.log tail-parse fallback with a structured pull. Persistent DB sink
/// (`learning.strategist_cycle_events`) is **deliberately deferred** — see
/// TODO §G3-11 downgrade rationale: PERSIST-AUDIT-GAP-COUNTER-1 already gives
/// `strategist_applied_params` rows for cross-validation, and an in-memory
/// snapshot satisfies the 80% observability case without a new hypertable.
///
/// G3-11：執行緒安全的 cycle 計數器。reject 按 reason / apply 次數 / 最後時戳
/// 都暴露給 IPC。DB sink 故意延後（理由見 TODO 降級）。
#[derive(Debug, Default)]
pub struct CycleCounters {
    /// Total apply / 累計 apply 次數
    apply_count: AtomicU64,
    /// Total cycles attempted (regardless of outcome)
    /// 累計 cycle 嘗試次數（無論結果）
    cycle_count: AtomicU64,
    /// Last time `evaluate_cycle` finished (Ok or Err) in epoch-ms.
    /// 最後一次 evaluate_cycle 完成時的時戳（無論成敗）。
    last_cycle_ts_ms: AtomicU64,
    /// Last successful apply timestamp (epoch-ms). 0 if never applied.
    /// 最後一次成功 apply 的時戳；從未 apply 為 0。
    last_apply_ts_ms: AtomicU64,
    /// Per-reason reject tally. Reasons are short stable strings
    /// (`out_of_range`, `delta_exceeded`, `weight_sum`, `not_object`,
    /// `ipc_failed`, `apply_failed`).
    /// reject 按 reason 累計。reason 為短穩定字串。
    reject_by_reason: Mutex<HashMap<String, u64>>,
}

impl CycleCounters {
    pub fn new() -> Self {
        Self::default()
    }

    /// Record a rejected recommendation by reason.
    /// 按 reason 記錄一個被拒的建議。
    pub fn record_reject(&self, reason: &str) {
        let mut map = match self.reject_by_reason.lock() {
            Ok(g) => g,
            Err(p) => p.into_inner(), // poisoned — recover and continue
        };
        *map.entry(reason.to_string()).or_insert(0) += 1;
    }

    /// Record a successful apply (validated + sent through PipelineCommand).
    /// 記錄一次成功 apply。
    pub fn record_apply(&self, now_ms: u64) {
        self.apply_count.fetch_add(1, Ordering::Relaxed);
        self.last_apply_ts_ms.store(now_ms, Ordering::Relaxed);
    }

    /// Record cycle completion (Ok or Err) — updates `last_cycle_ts_ms` and
    /// the cycle counter. Called once per `evaluate_cycle` regardless of
    /// outcome so freshness checks (healthcheck `[16]`) work even when
    /// the AI service is down.
    /// 記錄 cycle 完成（無論成敗）— 健康檢查需要新鮮度即使 AI service 掛掉。
    pub fn record_cycle_finish(&self, now_ms: u64) {
        self.cycle_count.fetch_add(1, Ordering::Relaxed);
        self.last_cycle_ts_ms.store(now_ms, Ordering::Relaxed);
    }

    /// Snapshot the current counter state into a serializable struct.
    /// 把當前計數狀態快照成可序列化的 struct。
    pub fn snapshot(&self) -> CycleCountersSnapshot {
        let reject_map = match self.reject_by_reason.lock() {
            Ok(g) => g.clone(),
            Err(p) => p.into_inner().clone(),
        };
        CycleCountersSnapshot {
            apply_count: self.apply_count.load(Ordering::Relaxed),
            cycle_count: self.cycle_count.load(Ordering::Relaxed),
            last_cycle_ts_ms: self.last_cycle_ts_ms.load(Ordering::Relaxed),
            last_apply_ts_ms: self.last_apply_ts_ms.load(Ordering::Relaxed),
            reject_by_reason: reject_map,
        }
    }
}

/// Serializable snapshot of `CycleCounters` returned by IPC
/// `get_strategist_cycle_metrics`.
/// CycleCounters 的可序列化快照，回給 IPC `get_strategist_cycle_metrics`。
#[derive(Debug, Clone, Serialize, Deserialize, Default, PartialEq, Eq)]
pub struct CycleCountersSnapshot {
    pub apply_count: u64,
    pub cycle_count: u64,
    pub last_cycle_ts_ms: u64,
    pub last_apply_ts_ms: u64,
    pub reject_by_reason: HashMap<String, u64>,
}

/// Reject-reason short tags. Stable strings — used as JSON keys + healthcheck
/// matchers. Any new reason added in `validate_recommendation_with_reason`
/// MUST also be listed here so consumers know the universe.
/// reject reason 短標籤。穩定字串；新增 reason 也要更新此 list。
pub const REJECT_REASONS: &[&str] = &[
    "not_object",
    "out_of_range",
    "delta_exceeded",
    "weight_sum",
    "ipc_failed",
    "apply_failed",
];

/// Maximum pairs to evaluate per cycle (R2 H-5: top-10, not all 96).
/// 每輪評估的最大交易對數（R2 H-5：top-10，非全部 96）。
const MAX_EVALS_PER_CYCLE: usize = 10;

/// Default fallback for `RiskConfig.strategist.max_param_delta_pct` when no
/// `ConfigStore<RiskConfig>` is wired into the scheduler (boot-edge cases /
/// existing direct-call test paths). Mirrors the pre-config hardcoded
/// `MAX_PARAM_DELTA_PCT = 0.30` (R3-4 ±30%) so behaviour is bit-identical
/// when the store is absent.
/// 缺 RiskConfig store 時的 max_param_delta_pct 後備值；對齊原 R3-4 ±30% 硬編碼。
/// STRATEGIST-TUNE-TARGET-CONFIG-1（2026-04-25）：值權威落到
/// `RiskConfig.strategist.max_param_delta_pct`，本常量僅作為缺 store 時的備援。
pub const DEFAULT_MAX_PARAM_DELTA_PCT: f64 = 0.30;

/// Weight sum target for confluence weights (65-point scale).
/// 匯合權重目標總和（65 分制）。
const WEIGHT_SUM_TARGET: f64 = 65.0;

/// Weight sum tolerance / 權重總和容差
const WEIGHT_SUM_TOLERANCE: f64 = 0.1;

/// Minimum fills required for a pair to be evaluated (R5-4).
/// 交易對被評估所需的最少成交數（R5-4）。
const MIN_SAMPLE_COUNT: i64 = 30;

/// Normal cycle interval / 正常輪詢間隔
const NORMAL_INTERVAL: Duration = Duration::from_secs(300); // 5 min

/// Per-strategy×symbol aggregated metrics from fills table.
/// 來自 fills 表的逐策略×symbol 聚合指標。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PairMetrics {
    pub strategy_name: String,
    pub symbol: String,
    pub fill_count: i64,
    pub avg_pnl: f64,
    pub win_rate: f64,
}

impl PairMetrics {
    /// Absolute deviation from target (higher = more in need of tuning).
    /// 與目標的絕對偏差（越高越需要調參）。
    pub fn deviation_score(&self) -> f64 {
        // Combine negative PnL and low win rate into a single score.
        // Win rate target = 0.5 (break-even), PnL target = 0.0.
        // 合併負 PnL 和低勝率為單一分數。
        let pnl_dev = self.avg_pnl.abs();
        let wr_dev = (self.win_rate - 0.5).abs() * 100.0; // scale to comparable range
        pnl_dev + wr_dev
    }
}

/// Strategist scheduler configuration / 策略師排程器配置
///
/// STRATEGIST-SCHED-CHANNEL-PAPER-ORPHAN-1 (2026-04-23):
///
/// 原設計（pre-fix）把 `paper_cmd_tx` 當 tuning target，PAPER-DISABLE-1
/// 之後 paper 預設不 spawn event_consumer，改由 `main.rs:1143-1157` 的
/// drain task 接管 paper_cmd_rx。drain task 收到 `GetStrategyParams` 命令
/// 只做 `if cmd.is_none() { break; }` 後直接丟棄 → 命令裡的 oneshot
/// `response_tx` 跟著 drop → scheduler `params_rx.await` 得 `RecvError`
/// → log spam 每 5 min 噴 "channel closed"。
///
/// Fix：scheduler 改為 demo-primary 語意（符合「Demo 階段完成測試 → 部署
/// Live」的 Phase 5+ 路線）：
///   - `tune_cmd_tx` + `tune_target`：scheduler 學習 + 應用的目標引擎，
///     當前恆為 Demo（`PipelineKind::Demo`）；若 main.rs 發現 demo 未綁定則
///     根本不 spawn scheduler（單行 log 退場，不走此結構）
///   - `promote_cmd_tx`：Live 促升目標 channel（Live 未綁 → None）；
///     配合 `promote_params_to_live()` method — **此 PR 不自動調用**，
///     Phase 5 IPC 觸發器 + 促升 criteria 接上即可使用
///   - SQL 加 `WHERE engine_mode = $tune_target.db_mode()` 對齊 tune 目標，
///     原跨引擎學習（paper+demo+live_demo 混）在 Phase 5 Live 架構下不再適用
///
/// STRATEGIST-SCHED-CHANNEL-PAPER-ORPHAN-1（2026-04-23）：
///
/// 原設計把 paper_cmd_tx 當 tune target，PAPER-DISABLE-1 後 drain task
/// 接管 → 丟棄命令 → oneshot response drop → "channel closed" 假報。
///
/// 修：scheduler demo-primary（符 Phase 5+ Demo→Live 促升路線）：
///   - tune_cmd_tx + tune_target 當前固定 Demo，main.rs 若 demo 未綁則
///     scheduler 整個不 spawn
///   - promote_cmd_tx 是 Live 促升 channel（本 PR 僅 stub `promote_params_to_live()`，
///     Phase 5 加 IPC 觸發器 + criteria）
///   - SQL 加 engine_mode filter 對齊 tune target
pub struct StrategistScheduler {
    /// AI service IPC client / AI 服務 IPC 客戶端
    ai_client: Arc<AiServiceClient>,
    /// Tuning-target pipeline command sender (Demo in the current design).
    /// 調諧目標引擎的管線命令發送器（當前設計恆為 Demo）。
    tune_cmd_tx: UnboundedSender<PipelineCommand>,
    /// Which engine this scheduler tunes. Must be Demo or Live — never Paper.
    /// 排程器調諧的引擎類型。只能是 Demo 或 Live，不接受 Paper。
    tune_target: PipelineKind,
    /// Optional Live-promotion command sender. `None` when Live engine is not
    /// bound (authorization.json unsigned). When `Some(_)`, enables
    /// `promote_params_to_live()` — not auto-invoked in this PR; Phase 5+ will
    /// wire the trigger and promotion criteria.
    /// Live 促升命令 channel。Live 引擎未綁（authorization.json 未簽）時為 None。
    /// 有值時啟用 `promote_params_to_live()` — 本 PR 不自動調用，Phase 5+ 接觸發器。
    promote_cmd_tx: Option<UnboundedSender<PipelineCommand>>,
    /// Database pool for fills query / 用於 fills 查詢的資料庫連接池
    db_pool: Arc<crate::database::pool::DbPool>,
    /// STRATEGIST-TUNE-TARGET-CONFIG-1 (2026-04-25): Optional RiskConfig store
    /// for hot-reading `strategist.max_param_delta_pct` per cycle. `None`
    /// keeps the scheduler on the `DEFAULT_MAX_PARAM_DELTA_PCT = 0.30` legacy
    /// fallback (boot-edge cases / direct-call tests). Production wires this
    /// via `StrategistScheduler::with_risk_store(...)` so the existing
    /// `Arc<ArcSwap<RiskConfig>>` deep-merge IPC path drives the clamp.
    /// STRATEGIST-TUNE-TARGET-CONFIG-1：可選 RiskConfig store；缺則走 0.30 legacy
    /// 後備（測試/啟動邊界），生產用 `with_risk_store` 接 IPC 熱重載。
    risk_store: Option<Arc<ConfigStore<RiskConfig>>>,
    /// Consecutive IPC failure counter for exponential backoff (R4-2).
    /// IPC 連續失敗計數器，用於指數退避。
    consecutive_failures: AtomicU32,
    /// G3-11 STRATEGIST-CYCLE-OBSERVABILITY-1: per-reason reject + apply
    /// counters exposed via IPC `get_strategist_cycle_metrics`. `Arc` so
    /// IPC handlers can hold a clone independent of scheduler ownership.
    /// G3-11：cycle 計數器；Arc 共享給 IPC handler。
    cycle_counters: Arc<CycleCounters>,
    /// Cancellation token for graceful shutdown / 優雅關閉的取消令牌
    cancel: CancellationToken,
}

impl StrategistScheduler {
    /// Create a new scheduler. Does NOT start the background task.
    /// 創建新排程器。不啟動後台任務。
    ///
    /// Contract: `tune_target` MUST be `PipelineKind::Demo` or
    /// `PipelineKind::Live`. Paper is rejected (paper is disabled-by-default
    /// per PAPER-DISABLE-1; tuning a drained engine is meaningless). Construction
    /// with `PipelineKind::Paper` panics to surface the mis-wiring loudly at
    /// startup rather than silently degrading.
    /// 契約：tune_target 只能是 Demo 或 Live。傳 Paper 直接 panic（paper 被 drain，
    /// 調它無意義）— 啟動時顯性失敗好過沈默降級。
    pub fn new(
        ai_client: Arc<AiServiceClient>,
        tune_cmd_tx: UnboundedSender<PipelineCommand>,
        tune_target: PipelineKind,
        promote_cmd_tx: Option<UnboundedSender<PipelineCommand>>,
        db_pool: Arc<crate::database::pool::DbPool>,
        cancel: CancellationToken,
    ) -> Self {
        assert!(
            matches!(tune_target, PipelineKind::Demo | PipelineKind::Live),
            "StrategistScheduler tune_target must be Demo or Live, got {:?} \
             / tune_target 只能是 Demo 或 Live，拒絕 {:?}",
            tune_target, tune_target,
        );
        Self {
            ai_client,
            tune_cmd_tx,
            tune_target,
            promote_cmd_tx,
            db_pool,
            risk_store: None,
            consecutive_failures: AtomicU32::new(0),
            cycle_counters: Arc::new(CycleCounters::new()),
            cancel,
        }
    }

    /// G3-11: expose the shared `CycleCounters` Arc so the IPC server can
    /// snapshot it without going through the pipeline command channel.
    /// G3-11：曝露 CycleCounters Arc 給 IPC server；不走 pipeline cmd channel。
    pub fn cycle_counters(&self) -> Arc<CycleCounters> {
        Arc::clone(&self.cycle_counters)
    }

    /// STRATEGIST-TUNE-TARGET-CONFIG-1 (2026-04-25): Builder-style attach a
    /// `ConfigStore<RiskConfig>` so the scheduler reads
    /// `strategist.max_param_delta_pct` from the live snapshot each cycle
    /// (hot-reloadable via IPC `patch_risk_config`). Without this call the
    /// scheduler falls back to `DEFAULT_MAX_PARAM_DELTA_PCT` (0.30, the
    /// previously hardcoded value) — preserving direct-call test paths
    /// without forcing every test to wire a store.
    /// STRATEGIST-TUNE-TARGET-CONFIG-1：builder-style 注入 RiskConfig store。
    /// 接線後 scheduler 每輪從 live snapshot 讀 max_param_delta_pct（IPC 熱重載）；
    /// 不接時走 0.30 後備保留現行測試路徑。
    pub fn with_risk_store(mut self, risk_store: Arc<ConfigStore<RiskConfig>>) -> Self {
        self.risk_store = Some(risk_store);
        self
    }

    /// STRATEGIST-TUNE-TARGET-CONFIG-1: Snapshot the current `max_param_delta_pct`
    /// from the wired `RiskConfig` store, or fall back to `DEFAULT_MAX_PARAM_DELTA_PCT`
    /// when no store is wired. Hot-path safe (single ArcSwap load).
    /// STRATEGIST-TUNE-TARGET-CONFIG-1：從 risk_store 取當前 max_param_delta_pct，
    /// 缺 store 時走 0.30 後備。ArcSwap 無鎖讀取。
    fn current_max_param_delta_pct(&self) -> f64 {
        self.risk_store
            .as_ref()
            .map(|store| store.load().strategist.max_param_delta_pct)
            .unwrap_or(DEFAULT_MAX_PARAM_DELTA_PCT)
    }

    /// Tune target introspection (mainly for tests + status logging).
    /// tune target 讀取（主要給測試 + 狀態日誌用）。
    pub fn tune_target(&self) -> PipelineKind {
        self.tune_target
    }

    /// Whether a Live-promotion channel is wired. `false` when Live engine
    /// is not bound at startup (authorization.json unsigned).
    /// Live 促升 channel 是否接線。Live 引擎未綁時為 false。
    pub fn has_promote_channel(&self) -> bool {
        self.promote_cmd_tx.is_some()
    }

    /// Promote validated params from the tune target (Demo) to Live.
    /// 從 tune target（Demo）促升已驗證參數到 Live。
    ///
    /// **Not invoked internally in this PR.** Phase 5+ will wire:
    ///   - Promotion criteria (N consecutive stable demo applies + no drawdown breach)
    ///   - IPC trigger (operator `POST /api/v1/strategist/promote`)
    /// This method exists so that wiring becomes additive, not structural.
    ///
    /// Returns `Err` if:
    ///   - `promote_cmd_tx` is `None` (Live engine not bound)
    ///   - Send fails (Live engine's cmd channel closed — reports up)
    ///   - UpdateStrategyParams handler returns error (strategy unknown / invalid params)
    ///
    /// **本 PR 不會自動調用。** Phase 5+ 再補：
    ///   - 促升 criteria（N 輪穩定 demo 應用 + 無 drawdown 越界）
    ///   - IPC 觸發器（operator `POST /api/v1/strategist/promote`）
    /// 此方法存在是為了讓接線變成疊加而非重構。
    pub async fn promote_params_to_live(
        &self,
        strategy_name: &str,
        params_json: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let live_tx = self.promote_cmd_tx.as_ref().ok_or(
            "promote_params_to_live: Live engine not bound (promote_cmd_tx is None) \
             / promote_params_to_live：Live 引擎未綁定"
        )?;
        let (tx, rx) = tokio::sync::oneshot::channel();
        live_tx.send(PipelineCommand::UpdateStrategyParams {
            strategy_name: strategy_name.to_string(),
            params_json: params_json.to_string(),
            response_tx: tx,
        })?;
        rx.await??;
        info!(
            strategy = %strategy_name,
            from = ?self.tune_target,
            to = ?PipelineKind::Live,
            "strategist params promoted to Live / 策略師參數已促升至 Live",
        );
        Ok(())
    }

    /// Run the scheduler forever (until cancelled). Spawn via tokio::spawn.
    /// 永久運行排程器（直到取消）。通過 tokio::spawn 啟動。
    pub async fn run_forever(self: Arc<Self>) {
        info!(
            tune_target = ?self.tune_target,
            has_promote_channel = self.has_promote_channel(),
            "StrategistScheduler started (5-min cycle) / 策略師排程器已啟動（5 分鐘週期）",
        );

        loop {
            tokio::select! {
                _ = self.cancel.cancelled() => {
                    info!("StrategistScheduler cancelled / 策略師排程器已取消");
                    return;
                }
                _ = tokio::time::sleep(self.current_interval()) => {
                    // Run evaluation cycle / 執行評估週期
                }
            }

            match self.evaluate_cycle().await {
                Ok(evaluated) => {
                    self.consecutive_failures.store(0, Ordering::Relaxed);
                    debug!(
                        pairs_evaluated = evaluated,
                        "StrategistScheduler cycle complete / 評估週期完成"
                    );
                }
                Err(e) => {
                    let fails = self.consecutive_failures.fetch_add(1, Ordering::Relaxed) + 1;
                    error!(
                        consecutive_failures = fails,
                        error = %e,
                        "StrategistScheduler cycle failed / 評估週期失敗"
                    );
                }
            }

            // G3-11: stamp `last_cycle_ts_ms` on every iteration (Ok or Err)
            // so healthcheck `[16] strategist_cycle_fresh` can detect a wedged
            // scheduler even when AI service is down.
            // G3-11：每輪（無論成敗）更新 last_cycle_ts_ms 給 healthcheck 觀察。
            let now_ms = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_millis() as u64)
                .unwrap_or(0);
            self.cycle_counters.record_cycle_finish(now_ms);
        }
    }

    /// Compute current sleep interval with exponential backoff (R4-2).
    /// 計算當前睡眠間隔（含指數退避）。
    fn current_interval(&self) -> Duration {
        let fails = self.consecutive_failures.load(Ordering::Relaxed);
        match fails {
            0 => NORMAL_INTERVAL,             // 5 min
            1 => Duration::from_secs(1_800),  // 30 min
            2 => Duration::from_secs(3_600),  // 60 min
            _ => Duration::from_secs(14_400), // 4h cap
        }
    }

    /// Single evaluation cycle: gather metrics → rank → evaluate → validate → apply.
    /// 單次評估週期：收集指標 → 排名 → 評估 → 驗證 → 應用。
    async fn evaluate_cycle(&self) -> Result<usize, Box<dyn std::error::Error + Send + Sync>> {
        // 1. Gather per-strategy×symbol metrics via DB query (R4-6, R5-3, R5-4)
        // 1. 通過 DB 查詢收集逐策略×symbol 指標
        let metrics = self.gather_strategy_metrics().await?;
        if metrics.is_empty() {
            debug!("no strategy metrics available (DB empty or unavailable) / 無策略指標");
            return Ok(0);
        }

        // 2. Rank by deviation and select top-N pairs (R2 H-5)
        // 2. 按偏差排名並選取 top-N 交易對
        let top_pairs = rank_by_deviation(&metrics);

        // 3. For each pair: fetch current params → IPC with context → validate → apply
        // 3. 對每個交易對：獲取當前參數 → 帶上下文 IPC → 驗證 → 應用
        let mut applied = 0usize;
        for pair in top_pairs.iter().take(MAX_EVALS_PER_CYCLE) {
            // 3a. Fetch current params + ranges BEFORE IPC (B3: context for Python AI)
            // 3a. IPC 前獲取當前參數 + 範圍（B3：為 Python AI 提供上下文）
            let (current_json, ranges_json) =
                match self.fetch_current_params(&pair.strategy_name).await {
                    Ok(v) => v,
                    Err(e) => {
                        warn!(
                            strategy = %pair.strategy_name,
                            error = %e,
                            "fetch_current_params failed, skipping pair / 獲取參數失敗，跳過"
                        );
                        continue;
                    }
                };

            // 3b. Serialize ranges for Python (B3: param_ranges in IPC payload)
            // 3b. 為 Python 序列化範圍（B3：IPC 負載中的 param_ranges）
            let ranges_value: Value =
                serde_json::to_value(&ranges_json).unwrap_or_else(|_| Value::Array(vec![]));

            let params = serde_json::json!({
                "intel": {
                    "symbol": pair.symbol,
                    "strategy": pair.strategy_name,
                    "win_rate": pair.win_rate,
                    "avg_pnl": pair.avg_pnl,
                    "fill_count": pair.fill_count,
                },
                "model_tier": "l1_9b",
                "current_params": current_json,
                "param_ranges": ranges_value,
            });

            let response = match self.ai_client.request("strategist_evaluate", params).await {
                Some(r) => r,
                None => {
                    // IPC failure — counted as cycle failure
                    // IPC 失敗 — 計為週期失敗
                    self.cycle_counters.record_reject("ipc_failed");
                    return Err("AI service IPC failed for strategist_evaluate".into());
                }
            };

            // 4. Validate recommendation against ranges, delta, weight sum.
            //    STRATEGIST-TUNE-TARGET-CONFIG-1: delta cap pulled from the
            //    RiskConfig store snapshot (or 0.30 fallback when no store wired).
            //    G3-11: every reject path tags a stable reason → CycleCounters
            //    `reject_by_reason` map → IPC `get_strategist_cycle_metrics`.
            // 4. 根據範圍、delta、權重總和驗證建議；delta cap 從 RiskConfig 取（缺 store=0.30）。
            //    G3-11：每條拒絕路徑都打 stable reason tag 到 CycleCounters。
            let max_delta_pct = self.current_max_param_delta_pct();
            match validate_recommendation_with_reason(
                &response,
                &current_json,
                &ranges_json,
                max_delta_pct,
            ) {
                Ok(()) => {
                // 5. Apply via PipelineCommand
                // 5. 通過 PipelineCommand 應用
                if let Err(e) = self.apply_params(&pair.strategy_name, &response).await {
                    warn!(
                        strategy = %pair.strategy_name,
                        error = %e,
                        "param apply failed / 參數應用失敗"
                    );
                    self.cycle_counters.record_reject("apply_failed");
                } else {
                    info!(
                        strategy = %pair.strategy_name,
                        symbol = %pair.symbol,
                        "strategist params applied / 策略師參數已應用"
                    );
                    applied += 1;
                    let now_ms = std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)
                        .map(|d| d.as_millis() as u64)
                        .unwrap_or(0);
                    self.cycle_counters.record_apply(now_ms);

                    // STRATEGIST-PARAMS-PERSIST-1 (2026-04-23): write audit row
                    // so engine restart restores tuned params instead of reverting
                    // to TOML baseline. Fail-soft: DB error → warn log + continue
                    // (tuning cycle still succeeded in-memory).
                    // STRATEGIST-PARAMS-PERSIST-1：寫 audit row，engine restart
                    // 恢復調諧參數而非 TOML baseline。Fail-soft：DB 錯誤僅 warn log，
                    // 不影響內存 tuning cycle。
                    if let Err(e) = self
                        .persist_applied_params(
                            &pair.strategy_name,
                            &current_json,
                            &response,
                            "top_deviation_pair",
                        )
                        .await
                    {
                        warn!(
                            strategy = %pair.strategy_name,
                            error = %e,
                            "persist_applied_params failed (fail-soft) / 持久化失敗（容錯跳過）"
                        );
                    }
                }
                }
                Err(reason) => {
                    debug!(
                        strategy = %pair.strategy_name,
                        symbol = %pair.symbol,
                        reason = reason,
                        "recommendation rejected by validation / 建議被驗證拒絕"
                    );
                    self.cycle_counters.record_reject(reason);
                }
            }
        }

        Ok(applied)
    }

    /// Query fills table for per-strategy×symbol aggregated metrics (R4-6, R5-3, R5-4).
    /// 查詢 fills 表獲取逐策略×symbol 聚合指標。
    async fn gather_strategy_metrics(
        &self,
    ) -> Result<Vec<PairMetrics>, Box<dyn std::error::Error + Send + Sync>> {
        let pool = match self.db_pool.get() {
            Some(p) => p,
            None => {
                debug!("DB pool unavailable — skipping metrics / DB 連接池不可用");
                return Ok(vec![]);
            }
        };

        // R5-3: column names are ts, strategy_name (not created_at, strategy)
        // R5-4: HAVING count(*) >= 30 — skip low-fill pairs
        // STRATEGIST-SCHED-CLOSE-FILTER-1 (2026-04-23 EDGE-DIAG-1 RCA byproduct):
        // `trading.fills.strategy_name` mixes entry strategies
        // (grid_trading / ma_crossover / bb_* / funding_arb) with close-path
        // reasons (`risk_close:*` / `strategy_close:*` / `ipc_close*`). Pre-fix
        // the scheduler took the unfiltered DISTINCT set and called
        // `fetch_current_params(strategy=<entire reason string>)` for each →
        // `channel closed` error spam in engine.log every 5 min, masking real
        // failures. Three NOT LIKE prefixes cover all known close paths
        // (risk_checks.rs format!("risk_close:{}",) / strategy emit
        // `strategy_close:{tag}` / IPC close handler `ipc_close_symbol` /
        // `ipc_close:{tag}`).
        //
        // STRATEGIST-SCHED-CHANNEL-PAPER-ORPHAN-1 (2026-04-23): additional
        // `engine_mode = $2` filter aligns metrics source with `tune_target`.
        // Pre-fix the SQL was cross-engine (paper + demo + live_demo + live
        // mixed), which was incoherent in the Phase 5+ "Demo trains, Live
        // receives promoted params" architecture — if scheduler tunes Demo
        // engine, it should learn from Demo fills only (otherwise live_demo
        // behaviour pollutes demo tuning signal). Paper is tolerated in the
        // filter as a value even though the enum rejects it in `new()` — the
        // `db_mode()` string goes through as-is with no special-casing.
        // R5-3：列名為 ts, strategy_name（非 created_at, strategy）
        // R5-4：HAVING count(*) >= 30 — 跳過低成交對
        // STRATEGIST-SCHED-CLOSE-FILTER-1（EDGE-DIAG-1 副產品 2026-04-23）：
        // `trading.fills.strategy_name` 混合入場策略與三類 close-path reasons；
        // 修復前 scheduler 把整段 reason 當策略名 IPC 致每 5min 噴 channel-closed
        // WARN，掩蓋真正失敗。三條 NOT LIKE 涵蓋已知 close prefix。
        //
        // STRATEGIST-SCHED-CHANNEL-PAPER-ORPHAN-1（2026-04-23）：新增
        // `engine_mode = $2` filter 對齊 tune_target。原跨引擎 SQL 在
        // 「Demo 訓練、Live 受促升」架構下不合理 — 調 Demo 就該只學 Demo。
        //
        // FA-1 (2026-04-23 review follow-up): Live tune path NOT yet supported.
        // `PipelineKind::Live.db_mode() == "live"` but real LiveDemo fills write
        // `engine_mode = "live_demo"` (see memory/project_engine_mode_tag_live_demo.md
        // + mode_state.rs::effective_engine_mode). A single-value `= $2` filter
        // would silently miss 95%+ of Live-endpoint fills. Phase 5+
        // STRATEGIST-TUNE-TARGET-CONFIG-1 must widen this to
        // `engine_mode IN ('live','live_demo','live_testnet')` when enabling
        // Live tune. Until then, fail-fast at first real use (Demo only).
        // FA-1：Live tune 路徑尚未支援。db_mode() 回 "live" 但真 LiveDemo fills
        // 的 engine_mode = "live_demo"；單值 filter 會靜默丟 95%+ 資料。
        // Phase 5+ STRATEGIST-TUNE-TARGET-CONFIG-1 必須擴為 IN 多值。
        debug_assert!(
            matches!(self.tune_target, PipelineKind::Demo),
            "STRATEGIST-SCHED gather_strategy_metrics: Live tune_target not yet \
             supported — SQL filter must widen to multi-mode IN before enabling \
             (see STRATEGIST-TUNE-TARGET-CONFIG-1 in TODO.md). Got tune_target={:?}",
            self.tune_target,
        );
        let tune_mode = self.tune_target.db_mode();
        let rows = sqlx::query_as::<_, PairMetricsRow>(
            r#"
            SELECT
                strategy_name,
                symbol,
                count(*)::bigint AS fill_count,
                coalesce(avg(realized_pnl), 0.0)::float8 AS avg_pnl,
                coalesce(
                    sum(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::float8
                    / nullif(count(*), 0)::float8,
                    0.0
                ) AS win_rate
            FROM trading.fills
            WHERE ts > now() - interval '7 days'
              AND engine_mode = $2
              AND strategy_name IS NOT NULL
              AND strategy_name NOT LIKE 'risk_close:%'
              AND strategy_name NOT LIKE 'strategy_close:%'
              AND strategy_name NOT LIKE 'ipc_close%'
            GROUP BY strategy_name, symbol
            HAVING count(*) >= $1
            ORDER BY avg_pnl ASC
            "#,
        )
        .bind(MIN_SAMPLE_COUNT)
        .bind(tune_mode)
        .fetch_all(pool)
        .await?;

        Ok(rows
            .into_iter()
            .map(|r| PairMetrics {
                strategy_name: r.strategy_name,
                symbol: r.symbol,
                fill_count: r.fill_count,
                avg_pnl: r.avg_pnl,
                win_rate: r.win_rate,
            })
            .collect())
    }

    /// Fetch current params + ranges for a strategy via PipelineCommand.
    /// 通過 PipelineCommand 獲取策略的當前參數和範圍。
    async fn fetch_current_params(
        &self,
        strategy_name: &str,
    ) -> Result<(Value, Vec<ParamRange>), Box<dyn std::error::Error + Send + Sync>> {
        // Get current params / 獲取當前參數
        let (params_tx, params_rx) = tokio::sync::oneshot::channel();
        self.tune_cmd_tx.send(PipelineCommand::GetStrategyParams {
            strategy_name: strategy_name.to_string(),
            response_tx: params_tx,
        })?;
        let params_str = params_rx.await??;
        let current: Value = serde_json::from_str(&params_str)?;

        // Get param ranges / 獲取參數範圍
        let (ranges_tx, ranges_rx) = tokio::sync::oneshot::channel();
        self.tune_cmd_tx.send(PipelineCommand::GetParamRanges {
            strategy_name: strategy_name.to_string(),
            response_tx: ranges_tx,
        })?;
        let ranges_str = ranges_rx.await??;
        let ranges: Vec<ParamRange> = serde_json::from_str(&ranges_str)?;

        Ok((current, ranges))
    }

    /// Apply validated params via PipelineCommand::UpdateStrategyParams.
    /// 通過 PipelineCommand::UpdateStrategyParams 應用已驗證的參數。
    async fn apply_params(
        &self,
        strategy_name: &str,
        recommendation: &Value,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let params_json = serde_json::to_string(recommendation)?;
        let (tx, rx) = tokio::sync::oneshot::channel();
        self.tune_cmd_tx.send(PipelineCommand::UpdateStrategyParams {
            strategy_name: strategy_name.to_string(),
            params_json,
            response_tx: tx,
        })?;
        rx.await??;
        Ok(())
    }

}

/// Rank pairs by deviation score, descending (worst-performing first).
/// 按偏差分數降序排名（表現最差的優先）。
fn rank_by_deviation(metrics: &[PairMetrics]) -> Vec<&PairMetrics> {
    let mut ranked: Vec<&PairMetrics> = metrics.iter().collect();
    ranked.sort_by(|a, b| {
        b.deviation_score()
            .partial_cmp(&a.deviation_score())
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    ranked
}

/// Validate a Strategist recommendation against param ranges, weight sum, and delta cap.
/// 根據參數範圍、權重總和和 delta 上限驗證策略師建議。
///
/// R3-4: Weight params (weight_adx, weight_regime, weight_volume, weight_momentum)
/// are exempt from the delta cap — the weight_sum=65 validation is sufficient.
/// R3-4：權重參數免除 delta 上限 — weight_sum=65 驗證已足夠。
///
/// STRATEGIST-TUNE-TARGET-CONFIG-1 (2026-04-25): `max_delta_pct` is now a
/// caller-supplied parameter (was the hardcoded `MAX_PARAM_DELTA_PCT = 0.30`
/// constant). Production callers route the live `RiskConfig.strategist
/// .max_param_delta_pct` snapshot here so the clamp is IPC-hot-reloadable;
/// direct-call tests pass the legacy `0.30` (or whatever value the test
/// pins). Values are expected to satisfy `0 < max_delta_pct < 1` per
/// `StrategistConfig::validate()`; out-of-range values still function (the
/// gate just becomes either always-reject or always-accept), but the config
/// validate path is supposed to have failed earlier so misconfigured TOML
/// can't reach this fn at runtime.
/// STRATEGIST-TUNE-TARGET-CONFIG-1：max_delta_pct 改為呼叫端傳入；生產接 RiskConfig
/// live snapshot（IPC 熱重載），測試傳 0.30 或被釘的值。
pub fn validate_recommendation(
    recommendation: &Value,
    current_params: &Value,
    param_ranges: &[ParamRange],
    max_delta_pct: f64,
) -> bool {
    validate_recommendation_with_reason(
        recommendation,
        current_params,
        param_ranges,
        max_delta_pct,
    )
    .is_ok()
}

/// G3-11: validate variant returning the structured reject reason for
/// CycleCounters tally. Reasons are stable short strings (see
/// `REJECT_REASONS`). The boolean wrapper above keeps the legacy direct-call
/// test signature stable.
/// G3-11：返回結構化 reject reason 的驗證版本。reason 為穩定短字串。
pub fn validate_recommendation_with_reason(
    recommendation: &Value,
    current_params: &Value,
    param_ranges: &[ParamRange],
    max_delta_pct: f64,
) -> Result<(), &'static str> {
    let rec_obj = match recommendation.as_object() {
        Some(o) => o,
        None => {
            warn!("recommendation is not a JSON object / 建議不是 JSON 物件");
            return Err("not_object");
        }
    };

    // Weight params exempt from delta cap (R3-4)
    // 權重參數免除 delta 上限
    let weight_param_names: &[&str] = &[
        "weight_adx",
        "weight_regime",
        "weight_volume",
        "weight_momentum",
    ];

    // Track weight sum for validation / 追蹤權重總和以驗證
    let mut weight_sum: f64 = 0.0;
    let mut has_weight_params = false;

    for range in param_ranges {
        if !range.agent_adjustable {
            continue;
        }
        let name = &range.name;
        let new_val = match rec_obj.get(name).and_then(|v| v.as_f64()) {
            Some(v) => v,
            None => continue, // param not in recommendation — keep current / 未在建議中 — 保留當前
        };

        // Range check / 範圍檢查
        if new_val < range.min || new_val > range.max {
            warn!(
                param = %name,
                value = new_val,
                min = range.min,
                max = range.max,
                "recommendation out of range / 建議超出範圍"
            );
            return Err("out_of_range");
        }

        // Delta check (weight params exempt — R3-4)
        // Delta 檢查（權重參數免除）
        let is_weight = weight_param_names.contains(&name.as_str());
        if is_weight {
            weight_sum += new_val;
            has_weight_params = true;
        } else if let Some(cur_val) = current_params.get(name).and_then(|v| v.as_f64()) {
            if cur_val.abs() > f64::EPSILON {
                let delta_pct = ((new_val - cur_val) / cur_val).abs();
                if delta_pct > max_delta_pct {
                    warn!(
                        param = %name,
                        current = cur_val,
                        proposed = new_val,
                        delta_pct = format!("{:.1}%", delta_pct * 100.0),
                        cap_pct = format!("{:.1}%", max_delta_pct * 100.0),
                        "delta exceeds configured cap (RiskConfig.strategist.max_param_delta_pct) \
                         / delta 超過配置上限"
                    );
                    return Err("delta_exceeded");
                }
            }
        }
    }

    // Weight sum check: must equal 65 ± 0.1 (if any weight params present)
    // 權重總和檢查：必須等於 65 ± 0.1（如果有權重參數）
    if has_weight_params && (weight_sum - WEIGHT_SUM_TARGET).abs() > WEIGHT_SUM_TOLERANCE {
        warn!(
            weight_sum,
            target = WEIGHT_SUM_TARGET,
            "weight sum out of tolerance / 權重總和超出容差"
        );
        return Err("weight_sum");
    }

    Ok(())
}

/// sqlx row type for fills aggregation query.
/// fills 聚合查詢的 sqlx 行類型。
#[derive(sqlx::FromRow)]
struct PairMetricsRow {
    strategy_name: String,
    symbol: String,
    fill_count: i64,
    avg_pnl: f64,
    win_rate: f64,
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pair_metrics_deviation_score() {
        let m = PairMetrics {
            strategy_name: "ma_crossover".into(),
            symbol: "BTCUSDT".into(),
            fill_count: 100,
            avg_pnl: -0.5,
            win_rate: 0.3,
        };
        // pnl_dev = 0.5, wr_dev = |0.3-0.5|*100 = 20.0
        let score = m.deviation_score();
        assert!((score - 20.5).abs() < 0.01);
    }

    #[test]
    fn test_rank_by_deviation() {
        let metrics = vec![
            PairMetrics {
                strategy_name: "a".into(),
                symbol: "BTC".into(),
                fill_count: 50,
                avg_pnl: -0.1,
                win_rate: 0.48,
            },
            PairMetrics {
                strategy_name: "b".into(),
                symbol: "ETH".into(),
                fill_count: 50,
                avg_pnl: -2.0,
                win_rate: 0.2,
            },
        ];
        let ranked = rank_by_deviation(&metrics);
        assert_eq!(ranked[0].strategy_name, "b"); // worse deviation
    }

    #[test]
    fn test_validate_recommendation_passes_valid() {
        let rec = serde_json::json!({
            "cooldown_ms": 55000.0,
            "adx_threshold": 22.0,
        });
        let current = serde_json::json!({
            "cooldown_ms": 50000.0,
            "adx_threshold": 20.0,
        });
        let ranges = vec![
            ParamRange {
                name: "cooldown_ms".into(),
                min: 10000.0,
                max: 120000.0,
                step: Some(1000.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "adx_threshold".into(),
                min: 10.0,
                max: 40.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
        ];
        assert!(validate_recommendation(&rec, &current, &ranges, DEFAULT_MAX_PARAM_DELTA_PCT));
    }

    #[test]
    fn test_validate_recommendation_rejects_out_of_range() {
        let rec = serde_json::json!({
            "cooldown_ms": 200000.0,  // above max 120000
        });
        let current = serde_json::json!({
            "cooldown_ms": 50000.0,
        });
        let ranges = vec![ParamRange {
            name: "cooldown_ms".into(),
            min: 10000.0,
            max: 120000.0,
            step: Some(1000.0),
            agent_adjustable: true,
            db_persisted: true,
        }];
        assert!(!validate_recommendation(&rec, &current, &ranges, DEFAULT_MAX_PARAM_DELTA_PCT));
    }

    #[test]
    fn test_validate_recommendation_rejects_excessive_delta() {
        let rec = serde_json::json!({
            "cooldown_ms": 100000.0,  // +100% from 50000 > ±30%
        });
        let current = serde_json::json!({
            "cooldown_ms": 50000.0,
        });
        let ranges = vec![ParamRange {
            name: "cooldown_ms".into(),
            min: 10000.0,
            max: 120000.0,
            step: Some(1000.0),
            agent_adjustable: true,
            db_persisted: true,
        }];
        assert!(!validate_recommendation(&rec, &current, &ranges, DEFAULT_MAX_PARAM_DELTA_PCT));
    }

    #[test]
    fn test_validate_recommendation_weight_params_exempt_from_delta() {
        // Weight params can change by any amount as long as sum = 65
        // 權重參數可以任意變化，只要總和 = 65
        let rec = serde_json::json!({
            "weight_adx": 30.0,      // was 25, +20% (would fail non-weight delta)
            "weight_regime": 15.0,   // was 20, -25%
            "weight_volume": 12.0,
            "weight_momentum": 8.0,  // sum = 65
        });
        let current = serde_json::json!({
            "weight_adx": 25.0,
            "weight_regime": 20.0,
            "weight_volume": 12.0,
            "weight_momentum": 8.0,
        });
        let ranges = vec![
            ParamRange {
                name: "weight_adx".into(),
                min: 0.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "weight_regime".into(),
                min: 0.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "weight_volume".into(),
                min: 0.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "weight_momentum".into(),
                min: 0.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
        ];
        assert!(validate_recommendation(&rec, &current, &ranges, DEFAULT_MAX_PARAM_DELTA_PCT));
    }

    #[test]
    fn test_validate_recommendation_rejects_bad_weight_sum() {
        let rec = serde_json::json!({
            "weight_adx": 30.0,
            "weight_regime": 20.0,
            "weight_volume": 12.0,
            "weight_momentum": 8.0,  // sum = 70, not 65
        });
        let current = serde_json::json!({});
        let ranges = vec![
            ParamRange {
                name: "weight_adx".into(),
                min: 0.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "weight_regime".into(),
                min: 0.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "weight_volume".into(),
                min: 0.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "weight_momentum".into(),
                min: 0.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
        ];
        assert!(!validate_recommendation(&rec, &current, &ranges, DEFAULT_MAX_PARAM_DELTA_PCT));
    }

    #[test]
    fn test_validate_recommendation_non_adjustable_skipped() {
        // Non-adjustable params in recommendation should be ignored
        // 不可調參數在建議中應被忽略
        let rec = serde_json::json!({
            "active": true,  // not agent_adjustable
            "cooldown_ms": 55000.0,
        });
        let current = serde_json::json!({
            "active": true,
            "cooldown_ms": 50000.0,
        });
        let ranges = vec![
            ParamRange {
                name: "active".into(),
                min: 0.0,
                max: 1.0,
                step: Some(1.0),
                agent_adjustable: false,
                db_persisted: false,
            },
            ParamRange {
                name: "cooldown_ms".into(),
                min: 10000.0,
                max: 120000.0,
                step: Some(1000.0),
                agent_adjustable: true,
                db_persisted: true,
            },
        ];
        assert!(validate_recommendation(&rec, &current, &ranges, DEFAULT_MAX_PARAM_DELTA_PCT));
    }

    #[test]
    fn test_validate_empty_recommendation_passes() {
        // Empty recommendation = no changes = valid
        let rec = serde_json::json!({});
        let current = serde_json::json!({});
        let ranges = vec![ParamRange {
            name: "cooldown_ms".into(),
            min: 10000.0,
            max: 120000.0,
            step: Some(1000.0),
            agent_adjustable: true,
            db_persisted: true,
        }];
        assert!(validate_recommendation(&rec, &current, &ranges, DEFAULT_MAX_PARAM_DELTA_PCT));
    }

    #[test]
    fn test_backoff_intervals() {
        // Verify the backoff intervals are correct
        // 驗證退避間隔正確
        let ai = Arc::new(AiServiceClient::new());
        let (tx, _rx) = tokio::sync::mpsc::unbounded_channel();
        let pool = Arc::new(crate::database::pool::DbPool::disconnected());
        let cancel = CancellationToken::new();
        let sched = StrategistScheduler::new(
            ai,
            tx,
            PipelineKind::Demo,
            None,
            pool,
            cancel,
        );

        assert_eq!(sched.current_interval(), Duration::from_secs(300));
        sched.consecutive_failures.store(1, Ordering::Relaxed);
        assert_eq!(sched.current_interval(), Duration::from_secs(1_800));
        sched.consecutive_failures.store(2, Ordering::Relaxed);
        assert_eq!(sched.current_interval(), Duration::from_secs(3_600));
        sched.consecutive_failures.store(5, Ordering::Relaxed);
        assert_eq!(sched.current_interval(), Duration::from_secs(14_400));
    }

    // ═══════════════════════════════════════════════════════════════════
    // STRATEGIST-SCHED-CHANNEL-PAPER-ORPHAN-1 regression tests (2026-04-23).
    // Verify:
    //   1. ctor rejects Paper tune_target (panics)
    //   2. ctor accepts Demo / Live
    //   3. tune_target() + has_promote_channel() getters
    //   4. promote_params_to_live returns Err when no promote channel
    //   5. promote_params_to_live sends on the promote channel + awaits response
    // STRATEGIST-SCHED-CHANNEL-PAPER-ORPHAN-1 回歸測試（2026-04-23）。
    // ═══════════════════════════════════════════════════════════════════

    fn mk_deps() -> (
        Arc<AiServiceClient>,
        Arc<crate::database::pool::DbPool>,
        CancellationToken,
    ) {
        (
            Arc::new(AiServiceClient::new()),
            Arc::new(crate::database::pool::DbPool::disconnected()),
            CancellationToken::new(),
        )
    }

    #[test]
    #[should_panic(expected = "tune_target must be Demo or Live")]
    fn test_new_rejects_paper_tune_target() {
        // Paper is drained-and-dropped (PAPER-DISABLE-1) — tuning it is the
        // exact bug we're fixing, so the ctor panics defensively.
        // Paper 是 PAPER-DISABLE-1 後的 drained engine，調它正是 bug 來源，
        // ctor 防禦性 panic 拒絕。
        let (ai, pool, cancel) = mk_deps();
        let (tx, _rx) = tokio::sync::mpsc::unbounded_channel();
        let _ = StrategistScheduler::new(
            ai,
            tx,
            PipelineKind::Paper,
            None,
            pool,
            cancel,
        );
    }

    #[test]
    fn test_new_accepts_demo_without_promote_channel() {
        // Canonical current deployment: Demo tune, no Live promote channel
        // (authorization.json unsigned).
        // 標準部署：Demo tune，Live 未接（authorization.json 未簽）。
        let (ai, pool, cancel) = mk_deps();
        let (tx, _rx) = tokio::sync::mpsc::unbounded_channel();
        let sched = StrategistScheduler::new(
            ai,
            tx,
            PipelineKind::Demo,
            None,
            pool,
            cancel,
        );
        assert_eq!(sched.tune_target(), PipelineKind::Demo);
        assert!(!sched.has_promote_channel());
    }

    #[test]
    fn test_new_accepts_demo_with_live_promote_channel() {
        // Phase 5+ deployment: Demo tune, Live promote wired (auth signed).
        // Phase 5+ 部署：Demo tune，Live 促升已接線（authorization 已簽）。
        let (ai, pool, cancel) = mk_deps();
        let (tune_tx, _tune_rx) = tokio::sync::mpsc::unbounded_channel();
        let (live_tx, _live_rx) = tokio::sync::mpsc::unbounded_channel();
        let sched = StrategistScheduler::new(
            ai,
            tune_tx,
            PipelineKind::Demo,
            Some(live_tx),
            pool,
            cancel,
        );
        assert_eq!(sched.tune_target(), PipelineKind::Demo);
        assert!(sched.has_promote_channel());
    }

    #[tokio::test]
    async fn test_promote_params_to_live_err_when_no_channel() {
        // has_promote_channel() == false → promote is unavailable; return Err
        // without panicking / blocking.
        // 無促升 channel 時應回 Err，不 panic、不 block。
        let (ai, pool, cancel) = mk_deps();
        let (tune_tx, _tune_rx) = tokio::sync::mpsc::unbounded_channel();
        let sched = StrategistScheduler::new(
            ai,
            tune_tx,
            PipelineKind::Demo,
            None,
            pool,
            cancel,
        );
        let result = sched
            .promote_params_to_live("grid_trading", r#"{"cooldown_ms":60000}"#)
            .await;
        assert!(result.is_err());
        let msg = format!("{}", result.unwrap_err());
        assert!(
            msg.contains("Live engine not bound"),
            "expected 'Live engine not bound' in error, got: {}",
            msg,
        );
    }

    #[tokio::test]
    async fn test_promote_params_to_live_sends_and_awaits_response() {
        // With a promote channel wired, verify:
        //   (a) the exact command shape delivered (UpdateStrategyParams with
        //       strategy_name + params_json matching inputs)
        //   (b) the method awaits the oneshot response and returns Ok on Ok(_)
        // 接線後驗證：(a) 命令形狀正確 (b) 等待 oneshot 回應後回 Ok。
        let (ai, pool, cancel) = mk_deps();
        let (tune_tx, _tune_rx) = tokio::sync::mpsc::unbounded_channel();
        let (live_tx, mut live_rx) =
            tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
        let sched = StrategistScheduler::new(
            ai,
            tune_tx,
            PipelineKind::Demo,
            Some(live_tx),
            pool,
            cancel,
        );

        // Spawn a stub handler that responds with Ok("ok") to any
        // UpdateStrategyParams command on the Live channel.
        // 啟動 stub handler 對 Live channel 上的 UpdateStrategyParams 回 Ok。
        let handler = tokio::spawn(async move {
            let mut seen_strategy: Option<String> = None;
            let mut seen_params: Option<String> = None;
            if let Some(cmd) = live_rx.recv().await {
                if let PipelineCommand::UpdateStrategyParams {
                    strategy_name,
                    params_json,
                    response_tx,
                } = cmd
                {
                    seen_strategy = Some(strategy_name);
                    seen_params = Some(params_json);
                    let _ = response_tx.send(Ok("ok".to_string()));
                }
            }
            (seen_strategy, seen_params)
        });

        let result = sched
            .promote_params_to_live("ma_crossover", r#"{"adx_threshold":22}"#)
            .await;
        assert!(result.is_ok(), "expected Ok, got: {:?}", result.err());

        let (seen_strategy, seen_params) = handler.await.expect("handler panicked");
        assert_eq!(seen_strategy.as_deref(), Some("ma_crossover"));
        assert_eq!(seen_params.as_deref(), Some(r#"{"adx_threshold":22}"#));
    }

    // E4-4 audit follow-up (2026-04-23): 釘 `PipelineKind::Demo.db_mode()`
    // 返回值恆為 `"demo"`（與 `trading.fills.engine_mode` 欄位的 snake_case
    // 慣例對齊）。若將來 enum 變成 PascalCase / 改 serde rename 導致回 "Demo"，
    // `gather_strategy_metrics` SQL `engine_mode = $2` 會永不命中任何列，
    // scheduler 靜默空跑而無任何錯誤。1 行 regression test 可擋此無聲故障。
    // E4-4 audit FUP：pin db_mode 返回值，防 snake_case 漂移致 SQL 空跑。
    #[test]
    fn test_pipeline_kind_db_mode_demo_is_lowercase_snake() {
        assert_eq!(PipelineKind::Demo.db_mode(), "demo",
            "SQL filter in gather_strategy_metrics depends on db_mode() \
             returning lowercase 'demo' — see STRATEGIST-SCHED-CHANNEL-PAPER-ORPHAN-1");
        // For completeness — these are the currently expected values for all
        // three variants; if anyone changes db_mode() this test trips too.
        // 完整性：另兩個 variant 也 pin。任何人動 db_mode() 都會紅。
        assert_eq!(PipelineKind::Paper.db_mode(), "paper");
        assert_eq!(PipelineKind::Live.db_mode(), "live");
    }

    #[tokio::test]
    async fn test_promote_params_to_live_err_on_handler_failure() {
        // Handler returns Err → promote_params_to_live propagates it.
        // Handler 回 Err → promote 應傳播。
        let (ai, pool, cancel) = mk_deps();
        let (tune_tx, _tune_rx) = tokio::sync::mpsc::unbounded_channel();
        let (live_tx, mut live_rx) =
            tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
        let sched = StrategistScheduler::new(
            ai,
            tune_tx,
            PipelineKind::Demo,
            Some(live_tx),
            pool,
            cancel,
        );

        tokio::spawn(async move {
            if let Some(cmd) = live_rx.recv().await {
                if let PipelineCommand::UpdateStrategyParams { response_tx, .. } = cmd {
                    let _ = response_tx.send(Err("strategy unknown".to_string()));
                }
            }
        });

        let result = sched
            .promote_params_to_live("unknown_strategy", "{}")
            .await;
        assert!(result.is_err());
    }

    // ═══════════════════════════════════════════════════════════════════
    // STRATEGIST-TUNE-TARGET-CONFIG-1 (2026-04-25): e2e behaviour test for
    // the configurable delta clamp. Wires a `ConfigStore<RiskConfig>`,
    // mutates `strategist.max_param_delta_pct` via `swap()`, and re-runs
    // `validate_recommendation` through the scheduler's
    // `current_max_param_delta_pct()` snapshot path. Ensures:
    //   - cfg=0.10 → reject a +15% delta (would have passed under 0.30)
    //   - cfg=0.50 → accept a +40% delta (would have failed under 0.30)
    // This is the integration check the prompt explicitly requires
    // ("不要省 e2e behavior 驗證").
    // STRATEGIST-TUNE-TARGET-CONFIG-1 e2e：把 max_param_delta_pct 改 0.10
    // 餵 +15% 須拒；改 0.50 餵 +40% 須收。驗證 schema → snapshot → validator
    // 整鏈通暢。
    // ═══════════════════════════════════════════════════════════════════

    #[test]
    fn test_param_delta_clamp_uses_config_value() {
        use crate::config::risk_config::RiskConfig;
        use crate::config::store::ConfigStore;
        use std::sync::Arc;

        // Helper to build a fresh scheduler with a wired RiskConfig store.
        // 工廠函式：建立帶 RiskConfig store 的 scheduler。
        let make_sched = |max_delta_pct: f64| {
            let mut rc = RiskConfig::default();
            rc.strategist.max_param_delta_pct = max_delta_pct;
            assert!(rc.validate().is_ok(), "test config must validate");
            let store = Arc::new(ConfigStore::new(rc));

            let (ai, pool, cancel) = mk_deps();
            let (tx, _rx) = tokio::sync::mpsc::unbounded_channel();
            StrategistScheduler::new(ai, tx, PipelineKind::Demo, None, pool, cancel)
                .with_risk_store(store)
        };

        // The single agent_adjustable param is `cooldown_ms`. Range is wide
        // enough that out-of-range never triggers — the only gate that
        // changes verdict between cfg values is the delta clamp.
        // 單一 agent_adjustable 參數 cooldown_ms；範圍寬到 out-of-range 不會
        // 觸發，唯有 delta clamp 隨 cfg 變動而切換結果。
        let ranges = vec![ParamRange {
            name: "cooldown_ms".into(),
            min: 1_000.0,
            max: 1_000_000.0,
            step: Some(1_000.0),
            agent_adjustable: true,
            db_persisted: true,
        }];

        // Scenario 1: clamp = 0.10, recommend +15% delta → REJECT.
        // 情境 1：clamp=0.10 拒 +15% delta（在 0.30 預設下原本會通過）。
        let sched_tight = make_sched(0.10);
        let snapshot_tight = sched_tight.current_max_param_delta_pct();
        assert!(
            (snapshot_tight - 0.10).abs() < 1e-12,
            "scheduler must read 0.10 from wired RiskConfig (got {})",
            snapshot_tight
        );

        let current = serde_json::json!({"cooldown_ms": 50_000.0});
        let rec_15pct = serde_json::json!({"cooldown_ms": 57_500.0}); // +15%
        let pass_15pct_at_010 = validate_recommendation(
            &rec_15pct,
            &current,
            &ranges,
            snapshot_tight,
        );
        assert!(
            !pass_15pct_at_010,
            "+15% delta must be REJECTED when max_param_delta_pct=0.10 \
             (would have passed at default 0.30 — proves clamp config-driven)"
        );

        // Sanity: same +15% delta must PASS at the legacy 0.30 default,
        // proving scenario 1 actually depends on the configured value
        // (not some unrelated gate).
        // 健全性：同一 +15% 在 0.30 預設下必通過，證明場景 1 拒絕的確由 clamp 驅動。
        let pass_15pct_at_default = validate_recommendation(
            &rec_15pct,
            &current,
            &ranges,
            DEFAULT_MAX_PARAM_DELTA_PCT,
        );
        assert!(
            pass_15pct_at_default,
            "+15% delta must PASS at legacy 0.30 (clamp difference must be observable)"
        );

        // Scenario 2: clamp = 0.50, recommend +40% delta → ACCEPT.
        // 情境 2：clamp=0.50 收 +40% delta（在 0.30 預設下原本會被拒）。
        let sched_loose = make_sched(0.50);
        let snapshot_loose = sched_loose.current_max_param_delta_pct();
        assert!(
            (snapshot_loose - 0.50).abs() < 1e-12,
            "scheduler must read 0.50 from wired RiskConfig (got {})",
            snapshot_loose
        );

        let rec_40pct = serde_json::json!({"cooldown_ms": 70_000.0}); // +40%
        let pass_40pct_at_050 = validate_recommendation(
            &rec_40pct,
            &current,
            &ranges,
            snapshot_loose,
        );
        assert!(
            pass_40pct_at_050,
            "+40% delta must be ACCEPTED when max_param_delta_pct=0.50 \
             (would have failed at default 0.30 — proves clamp config-driven)"
        );

        // Symmetric sanity: same +40% must FAIL at the legacy 0.30, so
        // scenario 2 acceptance is genuinely caused by the relaxed clamp.
        // 對稱健全性：+40% 在 0.30 預設下必拒，證明場景 2 通過確由 clamp 放寬驅動。
        let pass_40pct_at_default = validate_recommendation(
            &rec_40pct,
            &current,
            &ranges,
            DEFAULT_MAX_PARAM_DELTA_PCT,
        );
        assert!(
            !pass_40pct_at_default,
            "+40% delta must FAIL at legacy 0.30 (clamp difference must be observable)"
        );

        // Final scenario: scheduler with NO risk_store wired falls back to
        // DEFAULT_MAX_PARAM_DELTA_PCT (0.30) — the previously hardcoded
        // value. Ensures backward compatibility for direct-call tests /
        // boot-edge cases.
        // 最後場景：未接 risk_store 時走 0.30 後備（保留原硬編碼行為）。
        let (ai, pool, cancel) = mk_deps();
        let (tx, _rx) = tokio::sync::mpsc::unbounded_channel();
        let sched_no_store =
            StrategistScheduler::new(ai, tx, PipelineKind::Demo, None, pool, cancel);
        let snapshot_no_store = sched_no_store.current_max_param_delta_pct();
        assert!(
            (snapshot_no_store - DEFAULT_MAX_PARAM_DELTA_PCT).abs() < 1e-12,
            "no-store scheduler must fall back to DEFAULT_MAX_PARAM_DELTA_PCT (0.30)"
        );
    }

    #[test]
    fn test_param_delta_clamp_hot_reload_via_config_store_replace() {
        // Companion to the e2e test: verify that replacing the wired
        // ConfigStore via `replace()` (the same write API the IPC
        // `patch_risk_config` deep-merge path uses) flips the snapshot
        // mid-flight. Confirms hot-reload works end-to-end without engine
        // restart.
        // 補充：驗證 ConfigStore.replace()（IPC patch_risk_config 寫入路徑同款 API）
        // 即時反映；證明 clamp 真的能熱重載，無須重啟。
        use crate::config::risk_config::RiskConfig;
        use crate::config::store::{ConfigStore, PatchSource};
        use std::sync::Arc;

        let mut rc = RiskConfig::default();
        rc.strategist.max_param_delta_pct = 0.30;
        let store = Arc::new(ConfigStore::new(rc));

        let (ai, pool, cancel) = mk_deps();
        let (tx, _rx) = tokio::sync::mpsc::unbounded_channel();
        let sched = StrategistScheduler::new(ai, tx, PipelineKind::Demo, None, pool, cancel)
            .with_risk_store(Arc::clone(&store));

        assert!(
            (sched.current_max_param_delta_pct() - 0.30).abs() < 1e-12,
            "initial snapshot must be 0.30"
        );

        // Replace with a tighter clamp — simulates IPC patch_risk_config
        // landing through the deep-merge path.
        // 熱替換為較緊 clamp — 模擬 IPC patch_risk_config deep-merge 落入。
        let mut new_rc = RiskConfig::default();
        new_rc.strategist.max_param_delta_pct = 0.15;
        store
            .replace(new_rc, PatchSource::Operator)
            .expect("replace must succeed");

        assert!(
            (sched.current_max_param_delta_pct() - 0.15).abs() < 1e-12,
            "post-replace snapshot must reflect 0.15 (ArcSwap hot-reload visible to scheduler)"
        );
    }

    // ── G3-11 STRATEGIST-CYCLE-OBSERVABILITY-1 / CycleCounters tests ──
    //
    // Test matrix:
    //   1. record_apply / record_reject / record_cycle_finish basic semantics
    //   2. snapshot reflects the live counter values
    //   3. concurrent record_reject across N threads tallies correctly
    //   4. validate_recommendation_with_reason returns each stable reason
    //   5. REJECT_REASONS list covers every error string emitted

    #[test]
    fn test_cycle_counters_record_apply_and_snapshot() {
        let c = CycleCounters::new();
        c.record_apply(1_700_000_000_000);
        c.record_apply(1_700_000_001_000);
        let snap = c.snapshot();
        assert_eq!(snap.apply_count, 2);
        assert_eq!(snap.last_apply_ts_ms, 1_700_000_001_000);
        assert_eq!(snap.cycle_count, 0);
        assert!(snap.reject_by_reason.is_empty());
    }

    #[test]
    fn test_cycle_counters_record_reject_per_reason() {
        let c = CycleCounters::new();
        c.record_reject("out_of_range");
        c.record_reject("out_of_range");
        c.record_reject("delta_exceeded");
        c.record_reject("ipc_failed");
        let snap = c.snapshot();
        assert_eq!(snap.apply_count, 0);
        assert_eq!(snap.reject_by_reason.get("out_of_range").copied(), Some(2));
        assert_eq!(snap.reject_by_reason.get("delta_exceeded").copied(), Some(1));
        assert_eq!(snap.reject_by_reason.get("ipc_failed").copied(), Some(1));
        assert_eq!(snap.reject_by_reason.get("weight_sum").copied(), None);
    }

    #[test]
    fn test_cycle_counters_record_cycle_finish_freshness() {
        let c = CycleCounters::new();
        c.record_cycle_finish(1_700_000_000_000);
        c.record_cycle_finish(1_700_000_000_500);
        let snap = c.snapshot();
        assert_eq!(snap.cycle_count, 2);
        assert_eq!(snap.last_cycle_ts_ms, 1_700_000_000_500);
        // Freshness path is independent of apply path (healthcheck [16] reads cycle ts).
        // 即使從未 apply，cycle_finish 仍可前進 — healthcheck [16] 用此判活。
        assert_eq!(snap.last_apply_ts_ms, 0);
    }

    #[test]
    fn test_cycle_counters_concurrent_record_reject() {
        // Spawn N threads × M increments → assert tally consistency.
        // Catches the obvious mutex-lost-update + atomic ordering races.
        // N 線程 × M 次累加 — 抓 mutex / atomic 更新遺失。
        let c = Arc::new(CycleCounters::new());
        let n_threads = 8;
        let increments_per_thread = 250;
        let mut handles = Vec::new();
        for t in 0..n_threads {
            let c2 = Arc::clone(&c);
            handles.push(std::thread::spawn(move || {
                for _ in 0..increments_per_thread {
                    // Two reasons, alternating per thread parity, exercises
                    // the HashMap entry-or-insert path under contention.
                    if t % 2 == 0 {
                        c2.record_reject("out_of_range");
                    } else {
                        c2.record_reject("delta_exceeded");
                    }
                    c2.record_apply(1_000);
                }
            }));
        }
        for h in handles {
            h.join().unwrap();
        }
        let snap = c.snapshot();
        let total = (n_threads * increments_per_thread) as u64;
        assert_eq!(snap.apply_count, total, "apply_count must tally exactly");
        let reject_total: u64 = snap.reject_by_reason.values().sum();
        assert_eq!(reject_total, total, "reject sum must tally exactly");
        // Half-half split per parity rule above.
        assert_eq!(
            snap.reject_by_reason.get("out_of_range").copied(),
            Some(total / 2)
        );
        assert_eq!(
            snap.reject_by_reason.get("delta_exceeded").copied(),
            Some(total / 2)
        );
    }

    #[test]
    fn test_validate_recommendation_with_reason_returns_each_reason() {
        // not_object
        let ranges: Vec<ParamRange> = vec![];
        assert_eq!(
            validate_recommendation_with_reason(
                &serde_json::json!("scalar"),
                &serde_json::json!({}),
                &ranges,
                0.30,
            ),
            Err("not_object")
        );

        // out_of_range
        let ranges_or = vec![ParamRange {
            name: "cooldown_ms".into(),
            min: 10000.0,
            max: 120000.0,
            step: Some(1000.0),
            agent_adjustable: true,
            db_persisted: true,
        }];
        assert_eq!(
            validate_recommendation_with_reason(
                &serde_json::json!({"cooldown_ms": 999_999.0}),
                &serde_json::json!({"cooldown_ms": 50000.0}),
                &ranges_or,
                0.30,
            ),
            Err("out_of_range")
        );

        // delta_exceeded
        assert_eq!(
            validate_recommendation_with_reason(
                &serde_json::json!({"cooldown_ms": 100_000.0}),
                &serde_json::json!({"cooldown_ms": 50_000.0}),
                &ranges_or,
                0.30,
            ),
            Err("delta_exceeded")
        );

        // weight_sum
        let ranges_w = vec![
            ParamRange {
                name: "weight_adx".into(),
                min: 0.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "weight_regime".into(),
                min: 0.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
        ];
        assert_eq!(
            validate_recommendation_with_reason(
                &serde_json::json!({"weight_adx": 10.0, "weight_regime": 10.0}),
                &serde_json::json!({}),
                &ranges_w,
                0.30,
            ),
            Err("weight_sum")
        );
    }

    #[test]
    fn test_reject_reasons_list_covers_validate_branches() {
        // Sanity guard: every reason emitted by the validator (and the runtime
        // counters in evaluate_cycle) is enumerated in REJECT_REASONS so
        // documentation + healthcheck matchers stay in sync.
        // 完整性守護：list 必含所有 reason，避免新增分支忘記登記。
        for r in &[
            "not_object",
            "out_of_range",
            "delta_exceeded",
            "weight_sum",
            "ipc_failed",
            "apply_failed",
        ] {
            assert!(
                REJECT_REASONS.contains(r),
                "REJECT_REASONS missing reason `{r}`"
            );
        }
    }
}
