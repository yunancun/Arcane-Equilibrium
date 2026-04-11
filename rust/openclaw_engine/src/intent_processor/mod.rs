//! Intent Processor — H0 → Guardian → CostGate → Governance → OMS (R04-2).
//! 意圖處理器 — H0 → 守護者 → 成本門 → 治理 → OMS。
//!
//! MODULE_NOTE (EN): Processes trade intents through the governance pipeline:
//!   H0 gate → Guardian risk check → CostGate EV filter → Kelly sizing → OMS.
//!   Holds RiskConfig snapshot for per-tick limit enforcement.
//! MODULE_NOTE (中): 通過治理管線處理交易意圖：H0 門控 → Guardian 風控 →
//!   CostGate EV 過濾 → Kelly 倉位 → OMS。持有 RiskConfig 快照用於逐 tick 限制。

mod gates;
mod router;
#[cfg(test)]
mod tests;

use openclaw_core::{
    execution::{self, FillResult},
    governance_core::{GovernanceCore, GovernanceProfile},
    guardian::{ExistingPosition, Guardian, PortfolioContext, TradeIntentCheck, Verdict},
};
use crate::config::RiskConfig;
use crate::risk_checks::check_order_allowed;
use serde::{Deserialize, Serialize};

use crate::paper_state::PaperState;

/// A trade intent from a strategy.
/// 來自策略的交易意圖。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderIntent {
    pub symbol: String,
    pub is_long: bool,
    pub qty: f64,
    pub confidence: f64,
    pub strategy: String,
    pub order_type: String, // "market" or "limit"
    pub limit_price: Option<f64>,
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

/// Intent processor with guardian checks.
/// 帶守護者檢查的意圖處理器。
/// Default P1 risk cap (2% of balance per trade).
/// 默認 P1 風險上限（每筆交易餘額的 2%）。
const DEFAULT_P1_RISK_PCT: f64 = 0.02;

/// Bybit USDT perp default taker fee (0.055%) — fallback when API rate not available.
/// Bybit USDT 永續合約默認 taker 費率，API 未提供時的回退值。
const DEFAULT_TAKER_FEE_RATE: f64 = 0.00055;

/// Default slippage rate when volume data is unavailable (5 bps).
/// 無成交量數據時的默認滑點率（5 bps）。
const DEFAULT_SLIPPAGE_RATE: f64 = 0.0005;

/// Slippage tiers by 24h USD turnover — mirrors Python cost_gate.py SLIPPAGE_TIERS.
/// 按 24h 成交額分級的滑點 — 對齊 Python cost_gate.py。
/// (min_turnover_usd, slippage_rate)
const SLIPPAGE_TIERS: [(f64, f64); 5] = [
    (1_000_000_000.0, 0.0001),  // >$1B: 1 bps (BTC/ETH)
    (100_000_000.0,   0.0002),  // >$100M: 2 bps
    (10_000_000.0,    0.0005),  // >$10M: 5 bps
    (1_000_000.0,     0.0015),  // >$1M: 15 bps
    (0.0,             0.0030),  // <$1M: 30 bps (illiquid alts)
];

/// Look up slippage rate by 24h volume tier (mirrors Python _lookup_slippage).
/// 根據 24h 成交量查找滑點率（對齊 Python 版本）。
fn lookup_slippage(volume_24h: f64) -> f64 {
    if volume_24h <= 0.0 {
        return DEFAULT_SLIPPAGE_RATE;
    }
    for &(threshold, rate) in &SLIPPAGE_TIERS {
        if volume_24h >= threshold {
            return rate;
        }
    }
    DEFAULT_SLIPPAGE_RATE
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
    /// P1 risk cap percentage (configurable, default 2%).
    /// P1 風險上限百分比（可配置，默認 2%）。
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
        }
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
            Some(format!(
                "global_notional_cap: projected {:.2} USDT > cap {:.2} USDT (current {:.2})",
                projected, cap, current_usdt
            ))
        } else {
            None
        }
    }

    /// PH5-WIRE-1: Inject / refresh JS shrunk edge estimates.
    /// Called at startup and optionally via IPC reload trigger.
    /// PH5-WIRE-1：注入/刷新 JS 收縮邊際估計。啟動時調用，可通過 IPC 觸發刷新。
    pub fn set_edge_estimates(&mut self, estimates: crate::edge_estimates::EdgeEstimates) {
        let n = estimates.n_cells();
        let gm = estimates.grand_mean_bps();
        self.edge_estimates = estimates;
        tracing::info!(n_cells = n, grand_mean_bps = gm,
            "PH5-WIRE-1: edge estimates injected / 邊際估計已注入");
    }

    /// W-3: Plug in a LinUCB runtime (read-only). When set, callers may invoke
    /// `select_arm_after_gates` after gate approval to record the arm picked
    /// for the current intent without changing any decision logic.
    /// W-3：注入 LinUCB 運行時（唯讀）。設定後 caller 可在 gate 通過後呼叫
    /// `select_arm_after_gates` 記錄當前 intent 對應的 arm，不改變任何決策邏輯。
    pub fn set_linucb_runtime(
        &mut self,
        rt: std::sync::Arc<crate::linucb::LinUcbRuntime>,
    ) {
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

    /// Set P1 risk cap percentage (e.g. 0.02 = 2%, 0.05 = 5%).
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
}

impl Default for IntentProcessor {
    fn default() -> Self {
        Self::new()
    }
}
