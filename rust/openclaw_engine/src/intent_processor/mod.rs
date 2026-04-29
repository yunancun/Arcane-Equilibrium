//! Intent Processor — H0 → Guardian → CostGate → Governance → OMS (R04-2).
//! 意圖處理器 — H0 → 守護者 → 成本門 → 治理 → OMS。
//!
//! MODULE_NOTE (EN): Processes trade intents through the governance pipeline:
//!   H0 gate → Guardian risk check → CostGate EV filter → Kelly sizing → OMS.
//!   Holds RiskConfig snapshot for per-tick limit enforcement.
//! MODULE_NOTE (中): 通過治理管線處理交易意圖：H0 門控 → Guardian 風控 →
//!   CostGate EV 過濾 → Kelly 倉位 → OMS。持有 RiskConfig 快照用於逐 tick 限制。

mod gates;
mod rejection_coding;
mod router;
#[cfg(test)]
mod tests;

use rejection_coding::RejectionCode;

use crate::config::risk_config::EdgePredictorFallback;
use crate::config::RiskConfig;
use crate::edge_predictor::{
    features::FeatureVectorV1,
    gate::{
        edge_predictor_gate, FallbackReason, GateInputs, PredictorGateOutcome, ShadowFillPayload,
    },
    EdgePredictorStore,
};
use crate::risk_checks::check_order_allowed;
use crate::tick_pipeline::{PipelineCommand, PipelineKind};
use openclaw_core::{
    execution::{self, FillResult},
    governance_core::{GovernanceCore, GovernanceProfile},
    guardian::{ExistingPosition, Guardian, PortfolioContext, TradeIntentCheck, Verdict},
};
use parking_lot::Mutex;
use rand::{rngs::SmallRng, SeedableRng};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::sync::mpsc::UnboundedSender;

use crate::paper_state::PaperState;

/// A trade intent from a strategy.
/// 來自策略的交易意圖。
///
/// EDGE-P3-1 A6: `confluence_score` / `persistence_elapsed_ms` are plumbed from
/// strategies that compute them (MA/BBR/BBB) into `feature_builder::build_feature_vector`
/// for the predictor gate. `None` means the strategy does not compute that feature
/// (Grid, FundingArb) — builder fills with 0.0 and the zero-default stays benign
/// behind `use_edge_predictor=false`. `#[serde(default)]` keeps cross-version IPC
/// deserialization working if a producer omits these keys.
/// EDGE-P3-1 A6：`confluence_score` / `persistence_elapsed_ms` 由 MA/BBR/BBB 策略
/// 塞入，供 feature_builder 讀取；Grid/FundingArb 填 `None` 由 builder 補 0。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderIntent {
    pub symbol: String,
    pub is_long: bool,
    pub qty: f64,
    pub confidence: f64,
    pub strategy: String,
    pub order_type: String, // "market" or "limit"
    pub limit_price: Option<f64>,
    /// Confluence score in [0, 65] at intent time; None when strategy has no
    /// confluence scoring (Grid / FundingArb). Fed to feature slot #9.
    #[serde(default)]
    pub confluence_score: Option<f32>,
    /// Milliseconds since signal onset (PersistenceTracker state), capped by
    /// caller to feature range [0, 3_600_000]; None when strategy has no
    /// persistence tracker. Fed to feature slot #10.
    #[serde(default)]
    pub persistence_elapsed_ms: Option<u64>,
    /// EDGE-P2-3 Phase 1a: optional TimeInForce for maker/limit orders.
    /// `None` means default (Market → no TIF; Limit → GTC at dispatch).
    /// Set to `Some(TimeInForce::PostOnly)` for maker-only entries.
    /// EDGE-P2-3 Phase 1a：maker/limit 可選 TIF。None 保留現行預設行為
    /// （Market 不帶 TIF；Limit 於派發層預設 GTC）。Maker-only 入場設 Some(PostOnly)。
    #[serde(default)]
    pub time_in_force: Option<crate::order_manager::TimeInForce>,
    /// EDGE-P2-3 Phase 1B-3.2: per-order maker-resting timeout (ms). Only
    /// populated when `time_in_force == Some(PostOnly)`. `None` means the
    /// event consumer falls back to its default (no special sweep). Caller
    /// MUST pass the strategy-configured value (already clamped by the
    /// factory to `[MAKER_LIMIT_TIMEOUT_MIN_MS, MAKER_LIMIT_TIMEOUT_MAX_MS]`).
    /// EDGE-P2-3 Phase 1B-3.2：每單 maker 掛單逾時（毫秒），僅在 PostOnly 時填。
    /// None → 消費端走預設行為（不特別 sweep）。呼叫方必須傳入策略配置值
    /// （已於工廠 clamp 到 [15s, 300s]）。
    #[serde(default)]
    pub maker_timeout_ms: Option<u64>,
}

/// Captured Guardian verdict for DB persistence (risk_verdicts table).
/// 捕獲的 Guardian 裁定，用於持久化到 risk_verdicts 表。
#[derive(Debug, Clone)]
pub struct VerdictInfo {
    /// "Approved", "Modified", or "Rejected" / 批准、修改或拒絕
    pub verdict: String,
    pub risk_score: f64,
    pub reasons: Vec<String>,
    pub modified_qty: Option<f64>,
}

impl VerdictInfo {
    /// P0-6 permanent fix: synthetic "Rejected" verdict for pre-Guardian gate
    /// rejections (cost_gate / qty_zero / risk_gate / duplicate_position / etc.).
    /// Callers lacking a real Guardian verdict use this so `persist_verdict`
    /// can still write the rejection reason into `trading.risk_verdicts`.
    /// P0-6 永久修復：前置 gate 拒絕時的 synthetic Rejected 裁定。
    pub(crate) fn rejected(reason: String) -> Self {
        Self {
            verdict: "Rejected".to_string(),
            risk_score: 0.0,
            reasons: vec![reason],
            modified_qty: None,
        }
    }
}

/// Result of intent processing.
/// 意圖處理結果。
#[derive(Debug, Clone)]
pub struct IntentResult {
    pub submitted: bool,
    pub rejected_reason: Option<String>,
    pub fill: Option<FillResult>,
    /// Guardian verdict for DB persistence; None if rejected before guardian check.
    /// Guardian 裁定供 DB 持久化；在 Guardian 前被拒時為 None。
    pub verdict_info: Option<VerdictInfo>,
    /// FUP-8 Phase 2: qty after Kelly+P1 sizing; 0.0 on rejection.
    /// Exposed so paper `persist_intent` can write the real sized qty into
    /// trading.intents.details (was 1e9 sentinel before Phase 2). Matches the
    /// pre-rounding `fill.fill_qty` on success.
    /// FUP-8 Phase 2：Kelly+P1 sizing 後的數量；拒絕路徑為 0.0。
    /// 暴露此欄位讓 paper `persist_intent` 寫入真實 sized qty（Phase 2 前為 1e9 sentinel）；
    /// 成功路徑下等同 `fill.fill_qty` 取整前。
    pub approved_qty: f64,
    /// EDGE-P2-3 Phase 1B-4.2: Paper-only handoff when router classifies a
    /// PostOnly limit intent as "accepted but waiting to fill". Router builds
    /// the draft using gate-approved qty + paper_state mid-price snapshot +
    /// caller-supplied context_id + now_ms; caller (`on_tick`) is responsible
    /// for `paper_state.enqueue_resting_limit_order(draft)` since router only
    /// holds `&PaperState` (immutable). `Some(_)` implies `submitted=true`
    /// and `fill=None` — the "accepted pending" shape. Market intents and
    /// all non-paper paths leave this `None`.
    /// EDGE-P2-3 Phase 1B-4.2：紙盤專用 PostOnly「已接受、等成交」交接。
    /// router 以 gate 通過的 qty、paper_state mid、caller context_id、now_ms
    /// 組成 draft；caller（on_tick）負責 enqueue（router 僅持唯讀借用）。
    /// `Some(_)` 蘊含 `submitted=true` 且 `fill=None`（「接受待成交」形狀）。
    /// 市價意圖與所有非紙盤路徑此欄位為 None。
    pub resting_order: Option<crate::paper_state::RestingLimitOrder>,
    /// EDGE-P2-3 Phase 1B-5: set by router when the MakerKpi gate downgraded
    /// a PostOnly intent to market execution because the symbol's fill rate
    /// / net-edge KPI is Degraded. Caller (`on_tick`) calls
    /// `paper_state.record_maker_degraded_fallback(symbol)` and logs — the
    /// market fill still happens on the normal path. `None` means "no gate
    /// action" (either market intent, Healthy/Cold gate, or exchange path).
    /// EDGE-P2-3 Phase 1B-5：router 因 MakerKpi gate 判定 Degraded 而將 PostOnly
    /// 降級為市價時填入 Some(symbol)。caller（on_tick）記 counter + warn，
    /// 市價成交仍走正常路徑。None = 無 gate 動作。
    pub maker_degraded_fallback: Option<String>,
}

impl IntentResult {
    /// P0-6 permanent fix: build a rejected IntentResult with synthetic
    /// `verdict_info` so `persist_verdict` records the reason in DB.
    pub(crate) fn rejected(reason: String) -> Self {
        let vi = VerdictInfo::rejected(reason.clone());
        Self {
            submitted: false,
            rejected_reason: Some(reason),
            fill: None,
            verdict_info: Some(vi),
            approved_qty: 0.0,
            resting_order: None,
            maker_degraded_fallback: None,
        }
    }
}

/// EXT-1: Result of gate-only processing for exchange mode.
/// EXT-1：交易所模式下僅門禁處理的結果。
#[derive(Debug, Clone)]
pub struct ExchangeGateResult {
    /// Whether the intent passed all gates / 意圖是否通過所有門禁
    pub approved: bool,
    /// Rejection reason if not approved / 未通過時的拒絕原因
    pub rejected_reason: Option<String>,
    /// Gate-approved quantity after Kelly sizing + P1 cap / 門禁批准的數量（Kelly + P1 上限後）
    pub approved_qty: f64,
    /// Guardian verdict for DB persistence; None if rejected before guardian check.
    /// Guardian 裁定供 DB 持久化；在 Guardian 前被拒時為 None。
    pub verdict_info: Option<VerdictInfo>,
}

impl ExchangeGateResult {
    /// P0-6 permanent fix: see `IntentResult::rejected`.
    pub(crate) fn rejected(reason: String) -> Self {
        let vi = VerdictInfo::rejected(reason.clone());
        Self {
            approved: false,
            rejected_reason: Some(reason),
            approved_qty: 0.0,
            verdict_info: Some(vi),
        }
    }
}

/// Intent processor with guardian checks.
/// 帶守護者檢查的意圖處理器。
/// Default P1 risk cap (3% of balance per trade).
/// 默認 P1 風險上限（每筆交易餘額的 3%）。
const DEFAULT_P1_RISK_PCT: f64 = 0.03;

/// Bybit USDT perp default taker fee (0.055%) — fallback when API rate not available.
/// Bybit USDT 永續合約默認 taker 費率，API 未提供時的回退值。
const DEFAULT_TAKER_FEE_RATE: f64 = 0.00055;

/// Bybit USDT perp default maker fee (0.02%) — fallback when API rate not available.
/// Matches `account_manager::DEFAULT_MAKER_FEE` so cold-boot cost estimates agree
/// with the AccountManager path once Bybit API rates arrive.
/// Bybit USDT 永續默認 maker 費率，API 未提供時的回退值；與 AccountManager 常量對齊。
const DEFAULT_MAKER_FEE_RATE: f64 = 0.0002;

/// G7-07: Default slippage rate fallback when volume data is unavailable, used
/// only by `lookup_slippage_default()` test helper / legacy callers that don't
/// have a `&RiskConfig` handy. Runtime slippage now flows through
/// `RiskConfig.slippage.lookup_rate(volume_24h)` so operators can hot-reload
/// the tier table from `risk_config*.toml`.
/// G7-07：默認滑點率回退；僅供 test helper / 無 RiskConfig 的舊 caller 使用。
/// 運行時滑點現由 `RiskConfig.slippage.lookup_rate(volume_24h)` 提供，可
/// 從 `risk_config*.toml` 熱重載 tier 表。
pub(crate) const DEFAULT_SLIPPAGE_RATE: f64 = 0.0005;

/// Maximum age for API-fetched fee rates before exchange cost gates fail closed.
/// API 費率最大可接受年齡；超過後 exchange 成本門 fail-closed。
pub(crate) const MAX_FEE_RATE_STALENESS_MS: u64 = 2 * 60 * 60 * 1000;

/// G7-07: Look up slippage using the live `SlippageConfig` (TOML-backed).
/// Pre-G7-07 callers used a free `lookup_slippage(volume_24h)` reading the
/// hardcoded `SLIPPAGE_TIERS`. Now the tier table lives in
/// `risk.slippage.tiers` and lookup goes through this thin wrapper to keep
/// call-site diff minimal while making the table runtime-tunable.
/// G7-07：經由 `SlippageConfig`（TOML 支援）查滑點。原 free fn 讀
/// hardcoded `SLIPPAGE_TIERS`；現 tier 表存於 `risk.slippage.tiers`，
/// 透過 thin wrapper 維持 call-site diff 最小。
fn lookup_slippage(config: &crate::config::SlippageConfig, volume_24h: f64) -> f64 {
    config.lookup_rate(volume_24h)
}

/// G7-07 test/helper: legacy free-function lookup using default tiers. Kept so
/// pre-G7-07 unit tests and any rare caller without a `RiskConfig` handle can
/// still resolve a tier rate without constructing a config snapshot.
/// G7-07 test/helper：用 default tiers 查滑點，供原始單測與少數無
/// RiskConfig handle 的 caller 使用，免於額外構造 config snapshot。
#[cfg(test)]
pub(crate) fn lookup_slippage_default(volume_24h: f64) -> f64 {
    crate::config::SlippageConfig::default().lookup_rate(volume_24h)
}

pub struct IntentProcessor {
    guardian: Guardian,
    /// Legacy single-rate fallback (None = use hardcoded default).
    /// Preferred path: read per-symbol from `account_manager` (live API source).
    /// 舊版單費率回退（None = 用常量）。優先路徑：從 account_manager 讀取 per-symbol 真實費率。
    taker_fee_rate: Option<f64>,
    /// Live per-symbol fee rates from Bybit `/v5/account/fee-rate`.
    /// Bybit API 動態 per-symbol 費率（每小時刷新）。
    account_manager: Option<std::sync::Arc<crate::account_manager::AccountManager>>,
    /// Phase 2b: Kelly sizing config (None = disabled, passthrough).
    /// Phase 2b：Kelly 倉位配置（None = 禁用，直通）。
    kelly_config: Option<crate::ml::kelly_sizer::KellyConfig>,
    /// Phase 2b: Per-symbol trade stats for Kelly calculation.
    /// Phase 2b：每交易對的交易統計，用於 Kelly 計算。
    trade_stats: std::collections::HashMap<String, crate::ml::kelly_sizer::TradeStats>,
    /// P1 risk cap percentage (configurable, default 3%).
    /// P1 風險上限百分比（可配置，默認 3%）。
    p1_risk_pct: f64,
    /// RRC-1-B4: Risk config for check_order_allowed Gate 0 (ARCH-RC1 unified).
    /// RRC-1-B4：風控配置，用於 Gate 0 訂單准入檢查。
    risk_config: RiskConfig,
    /// RRC-1-B2: Daily start balance for daily loss tracking (reset at UTC midnight).
    /// RRC-1-B2：每日起始餘額，用於日損追蹤（UTC 午夜重置）。
    daily_start_balance: f64,
    /// RRC-1-B2: UTC day number of last reset (days since epoch).
    /// RRC-1-B2：上次重置的 UTC 天數（自 epoch 起的天數）。
    daily_reset_day: u64,
    /// W-3: Optional LinUCB runtime — read-only, never affects gates / sizing /
    /// fills. Phase 5 will hook reward feedback through this same handle.
    /// W-3：可選的 LinUCB 運行時 — 唯讀，不影響任何 gate / sizing / fill。
    /// Phase 5 將通過此 handle 接 reward feedback。
    linucb: Option<std::sync::Arc<crate::linucb::LinUcbRuntime>>,
    /// W-3: Last LinUCB selection (set after gates pass; consumed by downstream
    /// DecisionContextMsg producer if it reads from intent_processor instead of
    /// computing inline).
    /// W-3：最近一次 LinUCB 選擇（gate 通過後設定；下游 DecisionContextMsg
    /// producer 若選擇從 intent_processor 讀則使用此欄位）。
    last_arm_selection: Option<crate::linucb::ArmSelection>,
    /// PH5-WIRE-1: Shrunk JS realized-edge estimates per (strategy, symbol).
    /// Loaded at startup from settings/edge_estimates.json; refreshed via set_edge_estimates().
    /// PH5-WIRE-1：每 (策略, 幣種) JS 收縮實現邊際估計。啟動時加載，可通過 set_edge_estimates() 刷新。
    edge_estimates: crate::edge_estimates::EdgeEstimates,
    /// BLOCKER-3 D15: Shared cross-engine global exposure (USDT × 100 for AtomicU64 precision).
    /// Updated by exchange pipelines (Demo/Live); Paper is excluded.
    /// BLOCKER-3 D15：跨引擎全局曝險（USDT × 100 存入 AtomicU64 以保留精度）。
    /// 由交易所管線（Demo/Live）更新；Paper 排除。
    global_exposure_usdt: Option<std::sync::Arc<std::sync::atomic::AtomicU64>>,
    /// FIX-28: Account leverage for risk checks. Paper=1.0, exchange=actual.
    /// FIX-28：帳戶槓桿用於風控檢查。Paper=1.0，交易所=實際值。
    account_leverage: f64,
    /// EDGE-P3-1 A4: Per-engine ML edge predictor store (None → gate skipped,
    /// falls through to legacy JS shrinkage gate). Wired by engine bootstrap
    /// via `set_edge_predictor_store`.
    /// EDGE-P3-1 A4：逐引擎 ML edge predictor store（None → 跳過 gate 回退 JS
    /// shrinkage）。由引擎啟動時經 `set_edge_predictor_store` 注入。
    edge_predictor_store: Option<Arc<EdgePredictorStore>>,
    /// EDGE-P3-1 A4: Pipeline kind — only Paper engine runs ε-greedy branch.
    /// EDGE-P3-1 A4：管線種類——僅 Paper 走 ε-greedy 分支。
    pipeline_kind: PipelineKind,
    /// Bybit endpoint this processor's pipeline is bound to. Used together with
    /// `pipeline_kind` to resolve the DB engine_mode tag via
    /// `mode_state::effective_engine_mode`. Set by
    /// `TickPipeline::set_endpoint_env` at bootstrap.
    /// Bybit 端點綁定，與 pipeline_kind 一併透過
    /// `mode_state::effective_engine_mode` 解析 DB engine_mode 標籤。
    endpoint_env: Option<crate::bybit_rest_client::BybitEnvironment>,
    /// EDGE-P3-1 A4: Deterministic SmallRng seeded per-engine (spec §7.3 F9).
    /// Interior mutability because gate evaluation happens via `&self`.
    /// EDGE-P3-1 A4：按引擎 seed 的 SmallRng（spec §7.3 F9）。
    /// interior mutability 以支援 `&self` 呼叫 gate。
    predictor_rng: Mutex<SmallRng>,
    /// EDGE-P3-1 A4: Pipeline command channel for `EmitShadowFill` dispatch.
    /// None → shadow fills dropped (fail-soft; predictor gate still runs).
    /// EDGE-P3-1 A4：PipelineCommand 發送通道用於 `EmitShadowFill`。None 時丟棄
    /// shadow fill（fail-soft；gate 仍運作）。
    shadow_fill_tx: Option<UnboundedSender<PipelineCommand>>,
    /// EDGE-P3-1 Step 7a: Direct DB channel for decision feature snapshots.
    /// Emitted at the top of `evaluate_predictor_gate` whenever a real
    /// `FeatureVectorV1` + non-empty `context_id` is available, regardless of
    /// whether the predictor is enabled — training data collection starts
    /// immediately in Stage 0 while the gate still short-circuits to the
    /// legacy shrinkage path.
    /// None → emission no-op (fail-soft; trading unaffected).
    /// EDGE-P3-1 Step 7a：決策特徵 DB 直寫通道。只要拿到真實 `FeatureVectorV1` +
    /// 非空 context_id，於 `evaluate_predictor_gate` 頂端即發射，無論 predictor
    /// 是否啟用 — Stage 0 即刻採集訓練資料；None 時發射為 no-op（fail-soft）。
    decision_feature_tx: Option<tokio::sync::mpsc::Sender<crate::database::DecisionFeatureMsg>>,
    /// EDGE-P2-3 Phase 1B-5: owned snapshot of `MakerKpiConfig` consulted by the
    /// router's PostOnly KPI gate (Degraded → silent market fallback). Mirrors
    /// the `risk_config` ownership pattern: TickPipeline pushes the latest
    /// `ConfigStore<MakerKpiConfig>` snapshot through `update_maker_kpi_config`
    /// whenever `sync_maker_kpi_config_if_changed` detects a version bump.
    /// Defaults to `MakerKpiConfig::default()` so tests and unwired bootstraps
    /// stay bit-identical to the pre-hot-reload commit.
    /// EDGE-P2-3 Phase 1B-5：router KPI gate 查詢用的 owned MakerKpiConfig 快照。
    /// 與 `risk_config` 同模式：TickPipeline 於偵測到版本升版時透過
    /// `update_maker_kpi_config` 推入最新快照；預設 `MakerKpiConfig::default()`
    /// 保持測試與未接線路徑的 bit-identical。
    maker_kpi_config: crate::paper_state::MakerKpiConfig,
}

/// EDGE-P3-1 A4: Result of predictor-gate evaluation, translated to caller action.
/// EDGE-P3-1 A4：predictor gate 評估結果，已翻譯為 caller 動作。
#[derive(Debug, Clone)]
pub(super) enum PredictorAction {
    /// No-op — predictor disabled or no store; continue to legacy JS gate.
    /// 無動作 — predictor 禁用或無 store；繼續走 JS gate。
    UseLegacyGate,
    /// Predictor accepted (shadow_mode=false); skip legacy JS gate, continue pipeline.
    /// Predictor 接受（shadow_mode=false）；跳過 JS gate 繼續管線。
    SkipLegacyGate,
    /// Predictor rejected (hard reject OR ε-greedy fired OR fail-closed fallback).
    /// Predictor 拒絕（硬拒絕 / ε-greedy / fail-closed 回退）。
    Reject(String),
}

impl IntentProcessor {
    pub fn new() -> Self {
        Self {
            guardian: Guardian::default(),
            taker_fee_rate: None,
            account_manager: None,
            kelly_config: None,
            trade_stats: std::collections::HashMap::new(),
            p1_risk_pct: DEFAULT_P1_RISK_PCT,
            risk_config: RiskConfig::default(),
            daily_start_balance: 0.0,
            daily_reset_day: 0,
            linucb: None,
            last_arm_selection: None,
            edge_estimates: crate::edge_estimates::EdgeEstimates::empty(),
            global_exposure_usdt: None,
            account_leverage: 1.0,
            edge_predictor_store: None,
            pipeline_kind: PipelineKind::Paper,
            endpoint_env: None,
            // Tests get a fixed seed; production overrides via `set_predictor_rng_seed`.
            predictor_rng: Mutex::new(SmallRng::seed_from_u64(0)),
            shadow_fill_tx: None,
            decision_feature_tx: None,
            maker_kpi_config: crate::paper_state::MakerKpiConfig::default(),
        }
    }

    /// Create with an API-fetched taker fee rate.
    /// 使用 API 動態費率創建。
    pub fn with_fee_rate(rate: f64) -> Self {
        Self {
            guardian: Guardian::default(),
            taker_fee_rate: Some(rate),
            account_manager: None,
            kelly_config: None,
            trade_stats: std::collections::HashMap::new(),
            p1_risk_pct: DEFAULT_P1_RISK_PCT,
            risk_config: RiskConfig::default(),
            daily_start_balance: 0.0,
            daily_reset_day: 0,
            linucb: None,
            last_arm_selection: None,
            edge_estimates: crate::edge_estimates::EdgeEstimates::empty(),
            global_exposure_usdt: None,
            account_leverage: 1.0,
            edge_predictor_store: None,
            pipeline_kind: PipelineKind::Paper,
            endpoint_env: None,
            predictor_rng: Mutex::new(SmallRng::seed_from_u64(0)),
            shadow_fill_tx: None,
            decision_feature_tx: None,
            maker_kpi_config: crate::paper_state::MakerKpiConfig::default(),
        }
    }

    /// FIX-28: Set account leverage for exchange pipelines (Demo/Live).
    /// FIX-28：為交易所管線設定帳戶槓桿。
    pub fn set_account_leverage(&mut self, leverage: f64) {
        self.account_leverage = leverage.max(1.0);
    }

    /// BLOCKER-3 D15: Wire shared global exposure atomic for cross-engine notional cap.
    /// BLOCKER-3 D15：接入跨引擎全局曝險原子量，用於全局名目上限檢查。
    pub fn set_global_exposure(&mut self, exposure: std::sync::Arc<std::sync::atomic::AtomicU64>) {
        self.global_exposure_usdt = Some(exposure);
    }

    /// BLOCKER-3 D15: Check if adding `order_notional_usdt` would breach the global cap.
    /// Returns None if no cap is configured or no shared atomic wired. Returns Some(reason) if blocked.
    /// BLOCKER-3 D15：檢查新增 order_notional_usdt 是否超出全局上限。
    /// 無上限或無共享原子量時返回 None。被阻擋時返回 Some(reason)。
    fn check_global_notional_cap(&self, order_notional_usdt: f64) -> Option<String> {
        let cap = self.risk_config.limits.global_notional_cap_usdt;
        if cap <= 0.0 {
            return None; // disabled
        }
        let exposure_arc = self.global_exposure_usdt.as_ref()?;
        let current_cents = exposure_arc.load(std::sync::atomic::Ordering::Relaxed);
        let current_usdt = current_cents as f64 / 100.0;
        let projected = current_usdt + order_notional_usdt;
        if projected > cap {
            Some(
                RejectionCode::GlobalNotionalCap {
                    projected,
                    cap,
                    current: current_usdt,
                }
                .format(),
            )
        } else {
            None
        }
    }

    /// EXIT-FEATURES-TABLE-1: Read-only accessor for the currently loaded
    /// shrunk-edge table. Used by `emit_close_fill` to stamp the `est_net_bps`
    /// feature onto `learning.exit_features` — the same table the cost_gate
    /// reads for pre-open gating, kept as a single source of truth so train-
    /// time labels and runtime gates never drift.
    /// EXIT-FEATURES-TABLE-1：當前 JS 收縮邊際表的唯讀取用器；emit_close_fill
    /// 以此填 `learning.exit_features.est_net_bps`，與 cost_gate 開倉前讀的
    /// 同一張表為單一來源，確保訓練標籤與執行時 gate 永不漂移。
    pub fn edge_estimates(&self) -> &crate::edge_estimates::EdgeEstimates {
        &self.edge_estimates
    }

    /// PH5-WIRE-1: Inject / refresh JS shrunk edge estimates.
    /// Called at startup and optionally via IPC reload trigger.
    /// PH5-WIRE-1：注入/刷新 JS 收縮邊際估計。啟動時調用，可通過 IPC 觸發刷新。
    pub fn set_edge_estimates(&mut self, estimates: crate::edge_estimates::EdgeEstimates) {
        let n = estimates.n_cells();
        let gm = estimates.grand_mean_bps();
        self.edge_estimates = estimates;
        tracing::info!(
            n_cells = n,
            grand_mean_bps = gm,
            "PH5-WIRE-1: edge estimates injected / 邊際估計已注入"
        );
    }

    /// W-3: Plug in a LinUCB runtime (read-only). When set, callers may invoke
    /// `select_arm_after_gates` after gate approval to record the arm picked
    /// for the current intent without changing any decision logic.
    /// W-3：注入 LinUCB 運行時（唯讀）。設定後 caller 可在 gate 通過後呼叫
    /// `select_arm_after_gates` 記錄當前 intent 對應的 arm，不改變任何決策邏輯。
    pub fn set_linucb_runtime(&mut self, rt: std::sync::Arc<crate::linucb::LinUcbRuntime>) {
        self.linucb = Some(rt);
    }

    /// W-3: After gates pass, record the LinUCB arm selection for the given
    /// regime + strategy + context. Fail-soft (logs warn, returns None on miss).
    /// W-3：gate 通過後記錄當前 regime+strategy+context 對應的 LinUCB arm。
    /// Fail-soft（miss 時 log warn 並返回 None）。
    pub fn select_arm_after_gates(
        &mut self,
        regime: &str,
        strategy: &str,
        context: &[f64],
    ) -> Option<crate::linucb::ArmSelection> {
        let rt = self.linucb.as_ref()?;
        let sel = rt.select_for_intent(regime, strategy, context);
        if sel.is_none() {
            tracing::warn!(
                regime = %regime,
                strategy = %strategy,
                "linucb arm not found in intent_processor select"
            );
        }
        self.last_arm_selection = sel.clone();
        sel
    }

    /// W-3: Read the most recent LinUCB selection (consumed by downstream
    /// DecisionContextMsg producers if they choose to pull from here).
    /// W-3：讀最近一次 LinUCB 選擇（下游 DecisionContextMsg producer 可選用）。
    pub fn last_arm_selection(&self) -> Option<&crate::linucb::ArmSelection> {
        self.last_arm_selection.as_ref()
    }

    /// Set P1 risk cap percentage (e.g. 0.03 = 3%, 0.05 = 5%).
    /// 設定 P1 風險上限百分比。
    pub fn set_p1_risk_pct(&mut self, pct: f64) {
        self.p1_risk_pct = pct.clamp(0.001, 0.20); // Min 0.1%, max 20%
    }

    /// Get Guardian config for read-modify-write updates.
    /// 獲取守護者配置用於讀取-修改-寫回更新。
    pub fn guardian_config(&self) -> &openclaw_core::guardian::GuardianConfig {
        self.guardian.config()
    }

    /// Update Guardian config at runtime. / 運行時更新守護者配置。
    pub fn update_guardian_config(&mut self, config: openclaw_core::guardian::GuardianConfig) {
        self.guardian.update_config(config);
    }

    /// Phase 2b: Set Kelly sizing config.
    /// Phase 2b：設定 Kelly 倉位配置。
    pub fn set_kelly_config(&mut self, config: crate::ml::kelly_sizer::KellyConfig) {
        self.kelly_config = Some(config);
    }

    /// RRC-1-B4: Update risk config at runtime (ARCH-RC1).
    /// Also pulls the per-trade risk cap out of `limits.per_trade_risk_pct`
    /// and pushes it through the existing clamped setter so Gate 2.6 sees the
    /// patched value on the next tick (single source of truth = ConfigStore).
    /// RRC-1-B4：運行時更新風控配置；同時把 limits.per_trade_risk_pct 透過既有
    /// 帶 clamp 的 setter 灌進去，讓 Gate 2.6 在下一個 tick 看到新值。
    pub fn update_risk_config(&mut self, config: RiskConfig) {
        let new_p1 = config.limits.per_trade_risk_pct;
        self.risk_config = config;
        self.set_p1_risk_pct(new_p1);
    }

    /// RRC-1-B4: Read-only access to risk config.
    /// RRC-1-B4：風控配置的唯讀訪問。
    pub fn risk_config(&self) -> &RiskConfig {
        &self.risk_config
    }

    /// EDGE-P2-3 Phase 1B-5: Push a fresh MakerKpiConfig snapshot (called by
    /// TickPipeline's `sync_maker_kpi_config_if_changed` on store version bump).
    /// The router reads this snapshot inside `process_with_features` when
    /// evaluating the PostOnly KPI gate, so the next intent routed after a
    /// patch lands already sees the new thresholds without a restart.
    /// EDGE-P2-3 Phase 1B-5：推入最新 MakerKpiConfig 快照；由 TickPipeline 在
    /// store 升版時呼叫。router 在 `process_with_features` 裡評估 PostOnly KPI
    /// gate 時讀此快照，patch 落地後下一筆意圖即見新門檻、無需重啟。
    pub fn update_maker_kpi_config(&mut self, config: crate::paper_state::MakerKpiConfig) {
        self.maker_kpi_config = config;
    }

    /// EDGE-P2-3 Phase 1B-5: Read-only access to the live MakerKpiConfig
    /// snapshot consulted by the router KPI gate.
    /// EDGE-P2-3 Phase 1B-5：router KPI gate 使用的 MakerKpiConfig 唯讀存取。
    pub fn maker_kpi_config(&self) -> &crate::paper_state::MakerKpiConfig {
        &self.maker_kpi_config
    }

    /// PNL-7: Patch the dynamic-stop / RR tunables in-place. Each Some(v) is
    /// validated and applied; None leaves the field untouched. Returns the
    /// number of fields actually changed (for IPC ack).
    /// PNL-7：原地更新動態止損 / RR 三個可調參數，逐個驗證後生效。
    pub fn patch_dynamic_stop_params(
        &mut self,
        base_ratio: Option<f64>,
        cap_ratio: Option<f64>,
        trailing_min_rr_ratio: Option<f64>,
    ) -> u32 {
        let mut changed = 0;
        if let Some(v) = base_ratio {
            if v.is_finite() && (0.05..=1.0).contains(&v) {
                self.risk_config.dynamic_stop.base_ratio = v;
                changed += 1;
            }
        }
        if let Some(v) = cap_ratio {
            if v.is_finite() && (0.1..=1.0).contains(&v) {
                self.risk_config.dynamic_stop.cap_ratio = v;
                changed += 1;
            }
        }
        if let Some(v) = trailing_min_rr_ratio {
            if v.is_finite() && (0.0..=2.0).contains(&v) {
                self.risk_config.dynamic_stop.trailing_min_rr = v;
                changed += 1;
            }
        }
        changed
    }

    /// Session 12: Patch cost-gate + regime tunables in-place with validation.
    /// Each Some(v) is range-checked; invalid values silently dropped.
    /// Session 12：原地更新成本門 + regime 三類參數，逐個範圍校驗。
    pub fn patch_cost_gate_params(
        &mut self,
        min_confidence: Option<f64>,
        k_base: Option<f64>,
        k_medium: Option<f64>,
        k_small: Option<f64>,
        adx_trending_threshold: Option<f64>,
    ) -> u32 {
        let mut changed = 0;
        if let Some(v) = min_confidence {
            if v.is_finite() && (0.0..=1.0).contains(&v) {
                self.risk_config.cost_gate.min_confidence = v;
                changed += 1;
            }
        }
        if let Some(v) = k_base {
            if v.is_finite() && (0.5..=10.0).contains(&v) {
                self.risk_config.cost_gate.k_base = v;
                changed += 1;
            }
        }
        if let Some(v) = k_medium {
            if v.is_finite() && (0.5..=20.0).contains(&v) {
                self.risk_config.cost_gate.k_medium = v;
                changed += 1;
            }
        }
        if let Some(v) = k_small {
            if v.is_finite() && (0.5..=50.0).contains(&v) {
                self.risk_config.cost_gate.k_small = v;
                changed += 1;
            }
        }
        if let Some(v) = adx_trending_threshold {
            if v.is_finite() && (0.0..=100.0).contains(&v) {
                self.risk_config.cost_gate.adx_trending = v;
                changed += 1;
            }
        }
        changed
    }

    /// RRC-1-B2: Update daily start balance (called on each tick, resets at UTC midnight).
    /// RRC-1-B2：更新每日起始餘額（每 tick 調用，UTC 午夜重置）。
    pub fn maybe_reset_daily_balance(&mut self, balance: f64, ts_ms: u64) {
        let day = ts_ms / 86_400_000; // UTC day number / UTC 天數
        if day != self.daily_reset_day {
            self.daily_start_balance = balance;
            self.daily_reset_day = day;
        }
    }

    /// RRC-1-B2: Compute current daily loss percentage (internal).
    /// RRC-1-B2：計算當前日損百分比（內部）。
    fn daily_loss_pct(&self, current_balance: f64) -> f64 {
        if self.daily_start_balance <= 0.0 {
            return 0.0;
        }
        let loss = self.daily_start_balance - current_balance;
        if loss <= 0.0 {
            0.0
        } else {
            loss / self.daily_start_balance * 100.0
        }
    }

    /// RRC-1-C2: Public accessor for daily loss percentage (used by tick_pipeline Step 6).
    /// RRC-1-C2：日損百分比公開訪問器（用於 tick_pipeline 步驟 6）。
    pub fn daily_loss_pct_pub(&self, current_balance: f64) -> f64 {
        self.daily_loss_pct(current_balance)
    }

    /// RRC-1-B3: Compute total exposure percentage from positions.
    /// RRC-1-B3：從持倉計算總曝險百分比。
    fn compute_exposure_pct(paper_state: &PaperState) -> f64 {
        let balance = paper_state.balance();
        if balance <= 0.0 {
            return 0.0;
        }
        let total_notional: f64 = paper_state
            .positions()
            .iter()
            .map(|p| {
                let price = paper_state.latest_price(&p.symbol).unwrap_or(p.entry_price);
                p.qty * price
            })
            .sum();
        (total_notional / balance * 100.0).min(999.0)
    }

    /// RG-2: Compute actual account leverage from positions (total_notional / balance).
    /// Replaces hardcoded 1.0 — leverage check now triggers correctly.
    /// RG-2：從持倉計算實際帳戶槓桿（總名義值 / 餘額），替代硬編碼 1.0。
    fn compute_leverage(paper_state: &PaperState) -> f64 {
        Self::compute_exposure_pct(paper_state) / 100.0
    }

    /// FIX-05: Compute correlated exposure — max(long_notional, short_notional) / balance.
    /// All crypto is highly correlated, so same-direction positions compound risk.
    /// FIX-05：計算相關曝險 — max(多頭名義值, 空頭名義值) / 餘額。
    /// 加密貨幣高度相關，同方向持倉風險疊加。
    fn compute_correlated_exposure_pct(paper_state: &PaperState) -> f64 {
        let balance = paper_state.balance();
        if balance <= 0.0 {
            return 0.0;
        }
        let mut long_notional = 0.0_f64;
        let mut short_notional = 0.0_f64;
        for p in paper_state.positions() {
            let price = paper_state.latest_price(&p.symbol).unwrap_or(p.entry_price);
            let notional = p.qty * price;
            if p.is_long {
                long_notional += notional;
            } else {
                short_notional += notional;
            }
        }
        (long_notional.max(short_notional) / balance * 100.0).min(999.0)
    }

    /// Phase 2b: Record a closed trade for Kelly stats.
    /// Phase 2b：記錄已平倉交易用於 Kelly 統計。
    pub fn record_trade(&mut self, symbol: &str, pnl: f64) {
        self.trade_stats
            .entry(symbol.to_string())
            .or_default()
            .record(pnl);
    }

    /// Set dynamic fee rate post-creation (for hot-reload).
    /// 創建後設定動態費率（用於熱重載）。
    pub fn set_fee_rate(&mut self, rate: f64) {
        self.taker_fee_rate = Some(rate);
    }

    /// Set live AccountManager for per-symbol API-fetched fee rates.
    /// 設置 AccountManager 用於 per-symbol 真實費率。
    pub fn set_account_manager(
        &mut self,
        am: std::sync::Arc<crate::account_manager::AccountManager>,
    ) {
        self.account_manager = Some(am);
    }

    pub(crate) fn fee_rate_staleness_rejection(&self, now_ms: u64) -> Option<String> {
        let am = self.account_manager.as_ref()?;
        let last = am.last_fee_refresh_ms();
        if last == 0 {
            return Some("cost_gate: fee rates unavailable (cold boot, fail-closed)".to_string());
        }
        let now = if now_ms > 0 {
            now_ms
        } else {
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis() as u64
        };
        let age_ms = now.saturating_sub(last);
        if age_ms > MAX_FEE_RATE_STALENESS_MS {
            // Bybit demo endpoints do not support `/v5/account/fee-rate`.
            // Once conservative defaults exist in cache, treat that explicit
            // model as usable instead of freezing Demo/LiveDemo on timestamp
            // age; mainnet remains strict.
            if matches!(
                self.endpoint_env,
                Some(
                    crate::bybit_rest_client::BybitEnvironment::Demo
                        | crate::bybit_rest_client::BybitEnvironment::LiveDemo
                )
            ) && am.fee_rate_count() > 0
            {
                return None;
            }

            Some(format!(
                "cost_gate: fee rates stale age_ms={} > max_ms={} (fail-closed)",
                age_ms, MAX_FEE_RATE_STALENESS_MS
            ))
        } else {
            None
        }
    }

    /// EDGE-P3-1 A4: Wire the per-engine EdgePredictorStore. None → gate skipped.
    /// EDGE-P3-1 A4：注入逐引擎 EdgePredictorStore。None → 跳過 gate。
    pub fn set_edge_predictor_store(&mut self, store: Arc<EdgePredictorStore>) {
        self.edge_predictor_store = Some(store);
    }

    /// EDGE-P3-1 A4: Set the pipeline kind (Paper uniquely runs ε-greedy branch).
    /// EDGE-P3-1 A4：設定管線種類（僅 Paper 跑 ε-greedy 分支）。
    pub fn set_pipeline_kind(&mut self, kind: PipelineKind) {
        self.pipeline_kind = kind;
    }

    /// Bind this processor to a concrete Bybit endpoint so DB writes
    /// (decision_feature snapshots, shadow-fill rows) tag with the
    /// endpoint-aware engine_mode. Called by `TickPipeline::set_endpoint_env`.
    /// 綁定 Bybit 端點；DB 寫入使用 endpoint-aware engine_mode。
    pub fn set_endpoint_env(&mut self, env: crate::bybit_rest_client::BybitEnvironment) {
        self.endpoint_env = Some(env);
    }

    /// DB engine_mode tag for this processor (endpoint-aware). Mirrors
    /// `TickPipeline::effective_engine_mode`.
    /// 本處理器的 DB engine_mode 標籤（endpoint 感知）。
    #[inline]
    pub fn effective_engine_mode(&self) -> &'static str {
        crate::mode_state::effective_engine_mode(self.pipeline_kind, self.endpoint_env)
    }

    /// EDGE-P3-1 A4: Seed the predictor RNG (spec §7.3 F9 — `seed_for_engine(...)`).
    /// EDGE-P3-1 A4：seed predictor RNG（spec §7.3 F9）。
    pub fn set_predictor_rng_seed(&mut self, seed: u64) {
        self.predictor_rng = Mutex::new(SmallRng::seed_from_u64(seed));
    }

    /// EDGE-P3-1 A4: Read the current pipeline kind this processor was built
    /// for (what `GateInputs.engine_kind` reports into the predictor gate).
    /// Exposed for bootstrap regression tests that verify `TickPipeline::with_kind`
    /// forwards the kind correctly — production callers should not need it.
    /// EDGE-P3-1 A4：讀取目前 pipeline kind（gate 用於判斷是否走 ε-greedy 分支）。
    pub fn pipeline_kind(&self) -> PipelineKind {
        self.pipeline_kind
    }

    /// Test-only accessor: lock the predictor RNG so regression tests can draw
    /// bits off two differently-seeded processors and verify the streams
    /// diverge. Production callers consume the RNG exclusively through the
    /// gate inside `evaluate_predictor_gate`.
    /// 僅測試用：鎖預測器 RNG 供回歸測試比較兩條獨立 seed 的抽樣流。
    #[cfg(test)]
    pub fn predictor_rng_lock_for_tests(&self) -> parking_lot::MutexGuard<'_, SmallRng> {
        self.predictor_rng.lock()
    }

    /// EDGE-P3-1 A4: Inject a PipelineCommand sender for `EmitShadowFill` dispatch.
    /// EDGE-P3-1 A4：注入 PipelineCommand 發送通道用於 `EmitShadowFill`。
    pub fn set_shadow_fill_tx(&mut self, tx: UnboundedSender<PipelineCommand>) {
        self.shadow_fill_tx = Some(tx);
    }

    /// EDGE-P3-1 Step 7a: Inject the `DecisionFeatureMsg` writer channel so
    /// `evaluate_predictor_gate` can emit one training-store row per call.
    /// None → emission no-op (fail-soft; trading unaffected).
    /// EDGE-P3-1 Step 7a：注入 `DecisionFeatureMsg` writer 通道，供每次 gate 評估
    /// 寫入一列訓練資料。None 時發射 no-op（fail-soft，不影響交易）。
    pub fn set_decision_feature_tx(
        &mut self,
        tx: tokio::sync::mpsc::Sender<crate::database::DecisionFeatureMsg>,
    ) {
        self.decision_feature_tx = Some(tx);
    }

    /// EDGE-P3-1 A4: Evaluate the predictor gate for an intent. Returns a
    /// `PredictorAction` the caller uses to decide whether to skip/continue/reject.
    /// Emits `EmitShadowFill` when gate returns ε-greedy ShadowFill and a tx is wired.
    ///
    /// Policy (spec §7.3 · §7.4):
    /// - `!cfg.use_edge_predictor || store=None || features=None` → UseLegacyGate.
    /// - `cfg.shadow_mode=true` → always UseLegacyGate (Stage 3 observation).
    /// - Outcome=Accept → SkipLegacyGate (predictor decides).
    /// - Outcome=Reject/RejectAdd → Reject.
    /// - Outcome=ShadowFill → emit IPC, Reject("epsilon_greedy_exploration").
    /// - Outcome=Fallback(reason) → Shrinkage config: UseLegacyGate;
    ///   FailClosed config: Reject("predictor_fallback_fail_closed:<metric>").
    ///
    /// EDGE-P3-1 A4：評估預測器 gate 並翻譯為 caller 動作。
    pub(super) fn evaluate_predictor_gate(
        &self,
        intent: &OrderIntent,
        paper_state: &PaperState,
        features: Option<&FeatureVectorV1>,
        context_id: &str,
        now_ms: u64,
        cost_bps: f64,
    ) -> PredictorAction {
        // EDGE-P3-1 Step 7a: Emit a decision-feature training snapshot at the
        // TOP of the gate — before the `use_edge_predictor` short-circuit — so
        // that training data collection begins in Stage 0 while the predictor
        // stays disabled and the gate short-circuits to legacy shrinkage.
        // Only fires with a real FeatureVectorV1 + non-empty context_id; no-op
        // otherwise. `edge_label_backfill.py` populates labels on close.
        // EDGE-P3-1 Step 7a：在 `use_edge_predictor` 短路檢查之前於 gate 頂端
        // 發射訓練特徵快照，使 Stage 0 即刻採集資料（此時 predictor 仍禁用且
        // gate 走 legacy shrinkage）。僅在 features Some + context_id 非空時發射；
        // close 時由 `edge_label_backfill.py` 回填 label。
        if !context_id.is_empty() {
            if let Some(feats) = features {
                self.emit_decision_feature_snapshot(intent, feats, context_id, now_ms);
            }
        }

        let cfg = &self.risk_config.edge_predictor;
        if !cfg.use_edge_predictor {
            return PredictorAction::UseLegacyGate;
        }
        let store = match self.edge_predictor_store.as_ref() {
            Some(s) => s,
            None => return PredictorAction::UseLegacyGate,
        };
        let features = match features {
            Some(f) => f,
            None => return PredictorAction::UseLegacyGate,
        };

        // is_add: intent side matches existing position → would add to it. Used by
        // `require_q10_positive_for_adds` (gate ignores when flag is off).
        // is_add：意圖方向與現有持倉相同視為加倉。
        let is_add = paper_state
            .get_position(&intent.symbol)
            .map(|p| p.is_long == intent.is_long)
            .unwrap_or(false);

        let inputs = GateInputs {
            engine_kind: self.pipeline_kind,
            strategy: &intent.strategy,
            symbol: &intent.symbol,
            context_id,
            cost_bps,
            is_add_to_existing: is_add,
            now_ms,
        };

        let outcome = {
            let mut rng = self.predictor_rng.lock();
            edge_predictor_gate(
                &inputs,
                features,
                store.as_ref(),
                &mut *rng,
                cfg,
                // EDGE-P3-1 A5: serialize full 17-dim vector for shadow-fill
                // JSONB payload. Lazy closure — cost only paid on ε-greedy branch.
                // EDGE-P3-1 A5：lazy 序列化完整 17 維 feature；僅 ε-greedy 分支付代價。
                || features.to_jsonb(),
            )
        };

        if cfg.shadow_mode {
            tracing::debug!(
                strategy = %intent.strategy, symbol = %intent.symbol,
                ?outcome, "edge_predictor: shadow_mode — observation, JS gate decides / shadow 模式觀察"
            );
            return PredictorAction::UseLegacyGate;
        }

        match outcome {
            PredictorGateOutcome::Accept => PredictorAction::SkipLegacyGate,
            PredictorGateOutcome::Reject(reason) => PredictorAction::Reject(reason),
            PredictorGateOutcome::RejectAdd(reason) => PredictorAction::Reject(reason),
            PredictorGateOutcome::ShadowFill(payload) => {
                self.emit_shadow_fill(payload);
                PredictorAction::Reject(
                    "predictor_epsilon_greedy_exploration: paper shadow-fill dispatched".into(),
                )
            }
            PredictorGateOutcome::Fallback(reason) => self.apply_fallback(reason),
        }
    }

    /// EDGE-P3-1 A4: Emit an `EmitShadowFill` IPC command; drops fail-soft on
    /// missing tx or closed channel.
    /// EDGE-P3-1 A4：發送 `EmitShadowFill` IPC；tx 缺失/關閉則 fail-soft 丟棄。
    fn emit_shadow_fill(&self, payload: ShadowFillPayload) {
        let tx = match self.shadow_fill_tx.as_ref() {
            Some(t) => t,
            None => {
                tracing::warn!(
                    strategy = %payload.strategy, symbol = %payload.symbol,
                    "edge_predictor: ShadowFill dropped — no tx wired / 無 tx 丟棄 shadow fill"
                );
                return;
            }
        };
        let cmd = PipelineCommand::EmitShadowFill {
            context_id: payload.context_id,
            strategy: payload.strategy,
            symbol: payload.symbol,
            side: payload.side,
            features_jsonb: payload.features_jsonb,
            prediction_q10: payload.prediction_q10,
            prediction_q50: payload.prediction_q50,
            prediction_q90: payload.prediction_q90,
            cost_bps: payload.cost_bps,
            ts_ms: payload.ts_ms,
        };
        if let Err(e) = tx.send(cmd) {
            tracing::warn!(err = %e,
                "edge_predictor: EmitShadowFill send failed / 發送失敗");
        }
    }

    /// EDGE-P3-1 Step 7a: Push one `DecisionFeatureMsg` to the writer task.
    /// Called from the top of `evaluate_predictor_gate`, before the
    /// `use_edge_predictor` short-circuit, so training data is collected in
    /// Stage 0 while the gate stays on the legacy shrinkage path. Uses
    /// `try_send` to keep the intent loop off the DB backpressure path:
    /// writer-channel full → best-effort drop + warn, matching the writer's
    /// own resilience policy. Silent no-op when tx is not wired.
    /// EDGE-P3-1 Step 7a：向 writer 任務推送一條 `DecisionFeatureMsg`。於
    /// `evaluate_predictor_gate` 頂端呼叫 — 早於 `use_edge_predictor` 短路，
    /// Stage 0 即採集訓練資料；`try_send` 避免意圖循環被 DB 背壓阻塞，
    /// 通道滿 → best-effort drop + warn。tx 未接線時靜默 no-op。
    fn emit_decision_feature_snapshot(
        &self,
        intent: &OrderIntent,
        features: &FeatureVectorV1,
        context_id: &str,
        now_ms: u64,
    ) {
        let tx = match self.decision_feature_tx.as_ref() {
            Some(t) => t,
            None => return, // fail-soft no-op
        };
        // Skip obviously invalid timestamps to match DB-RUN-6 rejection policy
        // at the writer side — avoids emitting rows the writer will drop anyway.
        // 與 writer DB-RUN-6 對齊：無效時間戳不發射，節省通道容量。
        if now_ms == 0 {
            tracing::warn!(
                ctx_id = %context_id, symbol = %intent.symbol,
                "decision_feature snapshot skipped: now_ms=0 / 時間戳 0，跳過"
            );
            return;
        }

        let msg = crate::database::DecisionFeatureMsg {
            context_id: context_id.to_string(),
            ts_ms: now_ms,
            engine_mode: self.effective_engine_mode().to_string(),
            strategy_name: intent.strategy.clone(),
            symbol: intent.symbol.clone(),
            side: if intent.is_long { 1 } else { -1 },
            feature_schema_version: crate::edge_predictor::features::FEATURE_SCHEMA_VERSION
                .to_string(),
            feature_schema_hash: crate::edge_predictor::features::feature_schema_hash().to_string(),
            feature_definition_hash: crate::edge_predictor::features::feature_definition_hash()
                .to_string(),
            features_jsonb: features.to_jsonb(),
        };

        if let Err(e) = tx.try_send(msg) {
            tracing::warn!(
                ctx_id = %context_id, symbol = %intent.symbol, error = %e,
                "decision_feature snapshot drop — writer channel full/closed \
                 / 特徵快照丟棄，writer 通道已滿/關閉"
            );
        }
    }

    /// EDGE-P3-1 A4 · spec §7.4: apply first-level Fallback policy.
    /// Shrinkage → UseLegacyGate; FailClosed → Reject with metric-name suffix.
    /// EDGE-P3-1 A4 · §7.4：第一級 Fallback 策略。
    fn apply_fallback(&self, reason: FallbackReason) -> PredictorAction {
        let metric = reason.metric_name();
        match self.risk_config.edge_predictor.fallback_on_error {
            EdgePredictorFallback::Shrinkage => {
                tracing::info!(
                    fallback_reason = metric,
                    "edge_predictor: fallback → shrinkage gate / 回退 JS shrinkage"
                );
                PredictorAction::UseLegacyGate
            }
            EdgePredictorFallback::FailClosed => {
                tracing::warn!(
                    fallback_reason = metric,
                    "edge_predictor: fail-closed rejection / fail-closed 拒絕"
                );
                PredictorAction::Reject(format!("predictor_fallback_fail_closed:{}", metric))
            }
        }
    }

    /// Effective taker fee rate for a symbol. Resolution order:
    ///   1. Live `AccountManager.taker_fee(symbol)` (Bybit API, refreshed hourly)
    ///   2. Legacy single-rate fallback (`taker_fee_rate`)
    ///   3. `DEFAULT_TAKER_FEE_RATE` constant (cold-boot before API responds)
    /// 有效 taker 費率（per-symbol）。優先序：API → legacy → 常量。
    pub fn fee_rate(&self, symbol: &str) -> f64 {
        if let Some(ref am) = self.account_manager {
            return am.taker_fee(symbol);
        }
        self.taker_fee_rate.unwrap_or(DEFAULT_TAKER_FEE_RATE)
    }

    /// Effective maker fee rate for a symbol. Resolution order:
    ///   1. Live `AccountManager.maker_fee(symbol)` (Bybit API, refreshed hourly)
    ///   2. `DEFAULT_MAKER_FEE_RATE` constant (cold-boot before API responds)
    /// EDGE-P2-3 Phase 1a: Separate maker path from taker so cost estimates
    /// for PostOnly/Limit entries reflect the ~5× lower fee.
    /// 有效 maker 費率（per-symbol）：API → 常量。
    pub fn maker_fee_rate(&self, symbol: &str) -> f64 {
        if let Some(ref am) = self.account_manager {
            return am.maker_fee(symbol);
        }
        DEFAULT_MAKER_FEE_RATE
    }

    /// Pick maker vs taker fee based on the intent's TimeInForce. PostOnly
    /// means the order will only rest on book (maker); anything else pays taker.
    /// EDGE-P2-3 Phase 1a：依 TIF 選擇 maker/taker 費率。PostOnly→maker，其餘→taker。
    pub fn fee_rate_for_intent(&self, symbol: &str, intent: &OrderIntent) -> f64 {
        self.fee_rate_for_tif(symbol, intent.time_in_force)
    }

    /// Estimate slippage for cost gates. PostOnly maker orders rest on the book,
    /// so do not add the taker-style turnover slippage tier on top of maker
    /// fees; maker execution quality is tracked separately by MakerKpi.
    /// 成本門滑點估計。PostOnly maker 掛單不再疊加 taker-style turnover 滑點；
    /// maker 執作品質由 MakerKpi 另行監控。
    pub(crate) fn slippage_rate_for_intent(&self, intent: &OrderIntent, volume_24h: f64) -> f64 {
        self.slippage_rate_for_tif(intent.time_in_force, volume_24h)
    }

    pub(crate) fn slippage_rate_for_tif(
        &self,
        tif: Option<crate::order_manager::TimeInForce>,
        volume_24h: f64,
    ) -> f64 {
        if matches!(tif, Some(crate::order_manager::TimeInForce::PostOnly)) {
            0.0
        } else {
            lookup_slippage(&self.risk_config.slippage, volume_24h)
        }
    }

    /// Pick maker vs taker fee from a raw TimeInForce. Used on the fill path
    /// (`event_consumer/loop_handlers.rs`) where only `&PendingOrder` is
    /// available, not `&OrderIntent`. `None` falls back to taker: a Bybit Fill
    /// event can arrive before OrderUpdate has populated `order_id_to_link`,
    /// so matched_key lookup may fail and TIF is unknown — degrading to
    /// current pre-fix behaviour is safe (accounts fee at taker rate, which
    /// is the more conservative estimate for PnL).
    /// FIX-FEE-POSTONLY-1 (G7-09)：從原始 TIF 選費率；fill 路徑 race
    /// (Fill 先於 OrderUpdate) → TIF=None → taker 保本。
    pub fn fee_rate_for_tif(
        &self,
        symbol: &str,
        tif: Option<crate::order_manager::TimeInForce>,
    ) -> f64 {
        if matches!(tif, Some(crate::order_manager::TimeInForce::PostOnly)) {
            self.maker_fee_rate(symbol)
        } else {
            self.fee_rate(symbol)
        }
    }
}

impl Default for IntentProcessor {
    fn default() -> Self {
        Self::new()
    }
}
