//! Strategist periodic configurator — Rust-side tokio background task (R3-1).
//! 策略師定時配置器 — Rust 側 tokio 後台任務。
//!
//! MODULE_NOTE (EN): Single-instance scheduler (R3-1 fix: moved from Python FastAPI to
//!   Rust engine — uvicorn --workers=4 would create 4 racing schedulers). Every 5 min:
//!   1) Query fills table for per-strategy×symbol metrics (R4-6, R5-3, R5-4)
//!   2) Rank top-10 pairs by absolute deviation from target (R2 H-5)
//!   3) IPC call to Python ai_service.sock → strategist_evaluate (judge_edge via Ollama)
//!   4) Validate response: param_ranges bounds + weight sum=65±0.1 + delta clamp
//!      (R3-4; clamp default ±50% from `RiskConfig.strategist.max_param_delta_pct`,
//!      operator-tunable since STRATEGIST-TUNE-TARGET-CONFIG-1, 2026-04-25)
//!   5) Apply via PipelineCommand::UpdateStrategyParams
//!   Exponential backoff on IPC failure: 5m→30m→60m→4h cap (R4-2).
//!   Fail-closed: any error → skip cycle, retain current params.
//! MODULE_NOTE (中): 單實例排程器（R3-1 修復：從 Python FastAPI 移至 Rust 引擎——
//!   uvicorn --workers=4 會創建 4 個競爭排程器）。每 5 分鐘：
//!   1) 查詢 fills 表獲取逐策略×symbol 指標
//!   2) 按偏差排名取 top-10
//!   3) IPC 調用 Python ai_service.sock → strategist_evaluate
//!   4) 驗證回應：param_ranges 範圍 + weight sum=65 + delta ≤±50%
//!   5) 通過 PipelineCommand::UpdateStrategyParams 應用
//!   IPC 失敗指數退避：5m→30m→60m→4h 上限。

mod cycle_counters;
mod evaluate;
mod persist;

/// Re-export `load_latest_applied_params` at the `strategist_scheduler::`
/// namespace so `main.rs` call sites remain unchanged after the split.
/// 從 `persist` 子模組 re-export `load_latest_applied_params`，讓 `main.rs`
/// 呼叫路徑 `strategist_scheduler::load_latest_applied_params` 拆檔後不變。
pub use cycle_counters::{CycleCounters, CycleCountersSnapshot, REJECT_REASONS};
#[cfg(test)]
use evaluate::rank_by_deviation;
pub use evaluate::PairMetrics;
pub use persist::load_latest_applied_params;

use crate::ai_service_client::AiServiceClient;
use crate::config::risk_config::RiskConfig;
use crate::config::store::ConfigStore;
use crate::ipc_server::{DemoCmdSenderSlot, LiveCmdSenderSlot};
use crate::strategies::ParamRange;
use crate::tick_pipeline::{PipelineCommand, PipelineKind};
use serde_json::Value;
use std::sync::atomic::AtomicU32;
use std::sync::Arc;
use tokio::sync::mpsc::UnboundedSender;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

/// Default fallback for `RiskConfig.strategist.max_param_delta_pct` when no
/// `ConfigStore<RiskConfig>` is wired into the scheduler (boot-edge cases /
/// existing direct-call test paths). W-AUDIT-7 F-strategist-cap aligns this
/// fallback with the current RiskConfig default and TOML source value (±50%).
/// 缺 RiskConfig store 時的 max_param_delta_pct 後備值；W-AUDIT-7 對齊目前 ±50% source 預設。
/// STRATEGIST-TUNE-TARGET-CONFIG-1（2026-04-25）：值權威落到
/// `RiskConfig.strategist.max_param_delta_pct`，本常量僅作為缺 store 時的備援。
pub const DEFAULT_MAX_PARAM_DELTA_PCT: f64 = 0.50;

/// F-09 MODEL-TIER-EXTRACTION (2026-05-16, WP-04 follow-up)：缺 RiskConfig store
/// 時 `model_tier` 的後備值。與 `StrategistConfig::default()` / 三份
/// `risk_config_{paper,demo,live}.toml` 的 `[strategist] model_tier` source
/// default 對齊（"l1_9b"）。同時與 Python `ai_service_dispatch.py`
/// `_handle_strategist` 的 `params.get("model_tier", "l1_9b")` default 對齊，
/// 保留 backward compat。
/// F-09：缺 store 時 model_tier 後備，與 source default / Python default 對齊。
pub const DEFAULT_STRATEGIST_MODEL_TIER: &str = "l1_9b";

/// Weight sum target for confluence weights (65-point scale).
/// 匯合權重目標總和（65 分制）。
const WEIGHT_SUM_TARGET: f64 = 65.0;

/// Weight sum tolerance / 權重總和容差
const WEIGHT_SUM_TOLERANCE: f64 = 0.1;

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
///   - `promote_cmd_tx` / slot：Live 促升目標 channel（Live 未綁 → None）；
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
///   - promote_cmd_tx / slot 是 Live 促升 channel（本 PR 僅 stub `promote_params_to_live()`，
///     Phase 5 加 IPC 觸發器 + criteria）
///   - SQL 加 engine_mode filter 對齊 tune target
pub struct StrategistScheduler {
    /// AI service IPC client / AI 服務 IPC 客戶端
    ai_client: Arc<AiServiceClient>,
    /// Tuning-target pipeline command sender (Demo in the current design).
    /// 調諧目標引擎的管線命令發送器（當前設計恆為 Demo）。
    ///
    /// WP-13-LEFTOVER-1 (2026-05-16, FA-P1-11 補修)：原為 boot-time 值捕獲，
    /// 若 demo pipeline 之後 restart（目前無 watcher 但保留可能性），scheduler
    /// 將持續對舊 channel 發送、handler 跟著 drop oneshot response → 每 5 分
    /// 鐘噴「channel closed」假警，且學習迴圈失效。對齊 `promote_cmd_*` slot
    /// pattern：`tune_cmd_slot` 提供 watcher 輪替路徑，`tune_cmd_tx` 保留為
    /// fallback（測試 / 直接呼叫 / 啟動瞬間 slot 為 None）。
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
    /// Dynamic Live-promotion sender slot. Production wires this so promotion
    /// follows LiveAuthWatcher respawn/teardown instead of a boot-time sender.
    /// 動態 Live 促升 sender slot；生產路徑用它跟隨 LiveAuthWatcher 輪替。
    promote_cmd_slot: Option<LiveCmdSenderSlot>,
    /// WP-13-LEFTOVER-1 (2026-05-16)：tune-target 管線（Demo）的 sender slot。
    /// 生產路徑由 `main.rs` 注入既有 `demo_cmd_slot`（WP-13 已建）；scheduler
    /// 每 5 min 從 slot 讀快照，避免 pipeline restart 後對舊 channel 發送。
    /// 缺則退回 owned `tune_cmd_tx`（測試 / 直接呼叫保留原語意）。
    tune_cmd_slot: Option<DemoCmdSenderSlot>,
    /// Database pool for fills query / 用於 fills 查詢的資料庫連接池
    db_pool: Arc<crate::database::pool::DbPool>,
    /// STRATEGIST-TUNE-TARGET-CONFIG-1 (2026-04-25): Optional RiskConfig store
    /// for hot-reading `strategist.max_param_delta_pct` per cycle. `None`
    /// keeps the scheduler on the `DEFAULT_MAX_PARAM_DELTA_PCT = 0.50` source
    /// fallback (boot-edge cases / direct-call tests). Production wires this
    /// via `StrategistScheduler::with_risk_store(...)` so the existing
    /// `Arc<ArcSwap<RiskConfig>>` deep-merge IPC path drives the clamp.
    /// STRATEGIST-TUNE-TARGET-CONFIG-1：可選 RiskConfig store；缺則走 0.50 source
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
            tune_target,
            tune_target,
        );
        Self {
            ai_client,
            tune_cmd_tx,
            tune_target,
            promote_cmd_tx,
            promote_cmd_slot: None,
            tune_cmd_slot: None,
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
    /// scheduler falls back to `DEFAULT_MAX_PARAM_DELTA_PCT` (0.50) —
    /// preserving direct-call test paths
    /// without forcing every test to wire a store.
    /// STRATEGIST-TUNE-TARGET-CONFIG-1：builder-style 注入 RiskConfig store。
    /// 接線後 scheduler 每輪從 live snapshot 讀 max_param_delta_pct（IPC 熱重載）；
    /// 不接時走 0.50 後備保留現行測試路徑。
    pub fn with_risk_store(mut self, risk_store: Arc<ConfigStore<RiskConfig>>) -> Self {
        self.risk_store = Some(risk_store);
        self
    }

    /// Attach a watcher-rotated Live command sender slot for promotions.
    /// Production uses this to avoid dispatching into a stale boot-time Live
    /// command sender after authorization-driven respawn.
    /// 接入 watcher 輪替的 Live command sender slot，避免授權驅動 respawn 後仍
    /// 發送到啟動時舊 sender。
    pub fn with_promote_cmd_slot(mut self, promote_cmd_slot: LiveCmdSenderSlot) -> Self {
        self.promote_cmd_slot = Some(promote_cmd_slot);
        self
    }

    /// WP-13-LEFTOVER-1 (2026-05-16, FA-P1-11 補修)：接入 tune-target（Demo）
    /// 的命令 sender slot。生產路徑接 main.rs 既有 `demo_cmd_slot`（WP-13
    /// reconciler 同源），scheduler 每輪 fetch_current_params / apply_params
    /// 透過 [`tune_cmd_snapshot`] 取最新 sender，避免 boot-time 值捕獲過時。
    /// 對齊 `with_promote_cmd_slot` builder pattern。
    pub fn with_tune_cmd_slot(mut self, tune_cmd_slot: DemoCmdSenderSlot) -> Self {
        self.tune_cmd_slot = Some(tune_cmd_slot);
        self
    }

    /// STRATEGIST-TUNE-TARGET-CONFIG-1: Snapshot the current `max_param_delta_pct`
    /// from the wired `RiskConfig` store, or fall back to `DEFAULT_MAX_PARAM_DELTA_PCT`
    /// when no store is wired. Hot-path safe (single ArcSwap load).
    /// STRATEGIST-TUNE-TARGET-CONFIG-1：從 risk_store 取當前 max_param_delta_pct，
    /// 缺 store 時走 0.50 後備。ArcSwap 無鎖讀取。
    fn current_max_param_delta_pct(&self) -> f64 {
        self.risk_store
            .as_ref()
            .map(|store| store.load().strategist.max_param_delta_pct)
            .unwrap_or(DEFAULT_MAX_PARAM_DELTA_PCT)
    }

    /// F-09 MODEL-TIER-EXTRACTION (2026-05-16, WP-04 follow-up)：從 risk_store
    /// 取當前 `strategist.model_tier` 快照；缺 store 時走 [`DEFAULT_STRATEGIST_MODEL_TIER`]
    /// 後備（測試 / 啟動瞬間 / 直接 IPC 呼叫保留現行語意）。pattern 同
    /// `current_max_param_delta_pct`。ArcSwap 無鎖讀取，hot-path 安全。
    /// 本 helper 只負責 **static tier 提取**；future dynamic routing（依 decision
    /// complexity 切換 27B / L1.5 / L2）留 P2-F-09b ticket，會在 caller 層再加
    /// routing logic 包這個 snapshot。
    fn current_model_tier(&self) -> String {
        self.risk_store
            .as_ref()
            .map(|store| store.load().strategist.model_tier.clone())
            .unwrap_or_else(|| DEFAULT_STRATEGIST_MODEL_TIER.to_string())
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
        self.promote_cmd_snapshot().is_some()
    }

    fn promote_cmd_snapshot(&self) -> Option<UnboundedSender<PipelineCommand>> {
        if let Some(slot) = &self.promote_cmd_slot {
            if let Some(guard) = slot.try_read() {
                if let Some(tx) = guard.as_ref() {
                    return Some(tx.clone());
                }
            } else {
                debug!(
                    "StrategistScheduler::promote_cmd_snapshot: live slot read contention \
                     / live slot 讀取爭用"
                );
            }
        }
        self.promote_cmd_tx.clone()
    }

    /// WP-13-LEFTOVER-1 (2026-05-16)：讀 tune-target（Demo）sender 快照。
    /// 優先讀 `tune_cmd_slot`（main.rs 注入的 `demo_cmd_slot`），slot try_read
    /// 爭用或 slot 未接時退回 owned `tune_cmd_tx`。回 `Some(UnboundedSender)`
    /// （`Arc`-backed，clone 廉價）。pattern 同 `promote_cmd_snapshot`。
    pub(crate) fn tune_cmd_snapshot(&self) -> UnboundedSender<PipelineCommand> {
        if let Some(slot) = &self.tune_cmd_slot {
            if let Some(guard) = slot.try_read() {
                if let Some(tx) = guard.as_ref() {
                    return tx.clone();
                }
            } else {
                debug!(
                    "StrategistScheduler::tune_cmd_snapshot: demo slot read contention \
                     / demo slot 讀取爭用，退回 owned tune_cmd_tx"
                );
            }
        }
        // Fallback：slot 未接（測試 / 啟動瞬間）或 try_read 爭用，沿用 owned
        // boot-time sender。owned `tune_cmd_tx` 永遠存在（new() 必填），故無
        // Option 包裝。
        self.tune_cmd_tx.clone()
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
    ///   - no Live promote sender is currently available (Live engine not bound)
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
        let live_tx = self.promote_cmd_snapshot().ok_or(
            "promote_params_to_live: Live engine not bound (promote command sender unavailable) \
             / promote_params_to_live：Live 引擎未綁定",
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
}

/// Validate a Strategist recommendation against param ranges, weight sum, and delta cap.
/// 根據參數範圍、權重總和和 delta 上限驗證策略師建議。
///
/// R3-4: Weight params (weight_adx, weight_regime, weight_volume, weight_momentum)
/// are exempt from the delta cap — the weight_sum=65 validation is sufficient.
/// R3-4：權重參數免除 delta 上限 — weight_sum=65 驗證已足夠。
///
/// STRATEGIST-TUNE-TARGET-CONFIG-1 (2026-04-25): `max_delta_pct` is now a
/// caller-supplied parameter (was the hardcoded `MAX_PARAM_DELTA_PCT`
/// constant). Production callers route the live `RiskConfig.strategist
/// .max_param_delta_pct` snapshot here so the clamp is IPC-hot-reloadable;
/// direct-call tests pass `DEFAULT_MAX_PARAM_DELTA_PCT` or whatever value the
/// test pins. Values are expected to satisfy `0 < max_delta_pct < 1` per
/// `StrategistConfig::validate()`; out-of-range values still function (the
/// gate just becomes either always-reject or always-accept), but the config
/// validate path is supposed to have failed earlier so misconfigured TOML
/// can't reach this fn at runtime.
/// STRATEGIST-TUNE-TARGET-CONFIG-1：max_delta_pct 改為呼叫端傳入；生產接 RiskConfig
/// live snapshot（IPC 熱重載），測試傳 DEFAULT 或被釘的值。
pub fn validate_recommendation(
    recommendation: &Value,
    current_params: &Value,
    param_ranges: &[ParamRange],
    max_delta_pct: f64,
) -> bool {
    validate_recommendation_with_reason(recommendation, current_params, param_ranges, max_delta_pct)
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

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests;
