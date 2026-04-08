//! Intent Processor — H0 → Guardian → CostGate → Governance → OMS (R04-2).
//! 意圖處理器 — H0 → 守護者 → 成本門 → 治理 → OMS。
//!
//! Processes trade intents through the governance pipeline.
//! 通過治理管線處理交易意圖。

use openclaw_core::{
    execution::{self, FillResult},
    governance_core::GovernanceCore,
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

/// Result of intent processing.
/// 意圖處理結果。
#[derive(Debug, Clone)]
pub struct IntentResult {
    pub submitted: bool,
    pub rejected_reason: Option<String>,
    pub fill: Option<FillResult>,
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
}

/// Intent processor with guardian checks.
/// 帶守護者檢查的意圖處理器。
/// Default P1 risk cap (2% of balance per trade).
/// 默認 P1 風險上限（每筆交易餘額的 2%）。
const DEFAULT_P1_RISK_PCT: f64 = 0.02;

/// Bybit USDT perp default taker fee (0.055%) — fallback when API rate not available.
/// Bybit USDT 永續合約默認 taker 費率，API 未提供時的回退值。
const DEFAULT_TAKER_FEE_RATE: f64 = 0.00055;

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

    /// Process a single intent through the full governance pipeline.
    /// 通過完整治理管線處理單個意圖。
    pub fn process(
        &self,
        intent: &OrderIntent,
        governance: &GovernanceCore,
        paper_state: &PaperState,
        atr: f64,
    ) -> IntentResult {
        // Gate 1: Governance authorization check (fail-closed)
        if !governance.is_authorized() {
            return IntentResult {
                submitted: false,
                rejected_reason: Some("governance_not_authorized".into()),
                fill: None,
            };
        }

        // Gate 1.5: Reject same-direction duplicate (prevent fee drain)
        // 拒絕同方向重複開倉（防止手續費消耗）
        if let Some(existing) = paper_state.get_position(&intent.symbol) {
            if existing.is_long == intent.is_long {
                return IntentResult {
                    submitted: false,
                    rejected_reason: Some(format!(
                        "duplicate_position: {} already {} {}",
                        intent.symbol,
                        if existing.is_long { "LONG" } else { "SHORT" },
                        existing.qty,
                    )),
                    fill: None,
                };
            }
        }

        // Gate 2: Guardian 4-check
        let positions: Vec<ExistingPosition> = paper_state
            .positions()
            .iter()
            .map(|p| ExistingPosition {
                symbol: p.symbol.clone(),
                side: if p.is_long {
                    "Buy".into()
                } else {
                    "Sell".into()
                },
            })
            .collect();

        let ctx = PortfolioContext {
            drawdown_pct: paper_state.drawdown_pct(),
            positions,
        };

        let check = TradeIntentCheck {
            symbol: intent.symbol.clone(),
            side: if intent.is_long {
                "Buy".into()
            } else {
                "Sell".into()
            },
            leverage: 1.0, // paper = 1x
            qty: intent.qty,
        };

        let guardian_result = self.guardian.review(&check, &ctx);

        match guardian_result.verdict {
            Verdict::Rejected => {
                return IntentResult {
                    submitted: false,
                    rejected_reason: Some(format!(
                        "guardian_rejected: {:?}",
                        guardian_result.reasons
                    )),
                    fill: None,
                };
            }
            Verdict::Modified => {
                // Use modified qty if available
                // 如果有修改後的數量，使用修改後的
            }
            Verdict::Approved => {}
        }

        // ─── Gate 2.5: Kelly position sizing (Phase 2b) ─���─
        // Kelly 倉位計算（Phase 2b）
        let price = paper_state.latest_price(&intent.symbol).unwrap_or(0.0);
        let balance = paper_state.balance();
        let guardian_qty = guardian_result.modified_qty.unwrap_or(intent.qty);

        let kelly_qty = if let Some(ref kelly_cfg) = self.kelly_config {
            let stats = self
                .trade_stats
                .get(&intent.symbol)
                .cloned()
                .unwrap_or_default();
            // GAP-4: real ATR% from on_tick atr param (raw price units → fraction).
            // GAP-4：從 on_tick 傳入的真實 atr 計算 ATR% (價格單位轉小數)。
            let atr_pct = if price > 0.0 && atr > 0.0 {
                atr / price
            } else {
                0.0
            };
            crate::ml::kelly_sizer::compute_kelly_qty(
                kelly_cfg,
                &stats,
                balance,
                price,
                atr_pct,
                guardian_qty,
            )
        } else {
            guardian_qty
        };

        // ─── Gate 2.6: P1 hard cap = 2% of balance / price ───
        // P1 硬上限 = 餘額的 2% / 價格（不可超越的安全上限）
        let p1_max_qty = if price > 0.0 {
            balance * self.p1_risk_pct / price
        } else {
            kelly_qty
        };
        let final_qty = kelly_qty.min(p1_max_qty);

        // ─── PNL-1: Reject qty=0 ghost positions ───
        // 拒絕 qty=0 幽靈倉（小餘額被取整為 0 時必須阻止開倉）
        if !(final_qty > 0.0) {
            return IntentResult {
                submitted: false,
                rejected_reason: Some(format!(
                    "qty_zero: final_qty={:.8} (kelly={:.8}, p1_cap={:.8}, balance=${:.2}, price=${:.2})",
                    final_qty, kelly_qty, p1_max_qty, balance, price,
                )),
                fill: None,
            };
        }

        // ─── Gate 2.7: Order admission risk check (RRC-1-B1) ───
        // 訂單准入風控檢查：日損/槓桿/持倉大小/曝險/相關曝險
        // Runs after P1 sizing so single-position-pct check uses final_qty.
        // 在 P1 調整後運行，以便單一持倉百分比檢查使用最終數量。
        {
            let is_reducing = paper_state
                .get_position(&intent.symbol)
                .map(|p| p.is_long != intent.is_long)
                .unwrap_or(false);
            let exposure_pct = Self::compute_exposure_pct(paper_state);
            let daily_loss = self.daily_loss_pct(balance);
            let check_result = check_order_allowed(
                final_qty,
                price,
                balance,
                exposure_pct,
                0.0, // correlated_exposure_pct — Phase C wiring
                1.0, // leverage — paper = 1x
                daily_loss,
                is_reducing,
                &self.risk_config,
            );
            if !check_result.allowed {
                return IntentResult {
                    submitted: false,
                    rejected_reason: Some(format!("risk_gate: {}", check_result.reason)),
                    fill: None,
                };
            }
        }

        // ─── Gate 3: Cost gate — PH5-WIRE-1 mode-aware (paper/demo = exploration) ───
        // 成本門控：PH5-WIRE-1 模式感知（paper/demo = 探索模式）
        {
            let min_confidence = self.risk_config.cost_gate.min_confidence;
            if intent.confidence < min_confidence {
                return IntentResult {
                    submitted: false,
                    rejected_reason: Some(format!(
                        "cost_gate: confidence {:.2} < min {:.2}",
                        intent.confidence, min_confidence,
                    )),
                    fill: None,
                };
            }
            // SEC-11: ATR=0 → fail-closed (cold-start by PNL-3 boot cooldown; runtime ATR=0 = indicator failure).
            // SEC-11：ATR=0 失敗關閉（冷啟動由 PNL-3 保護；運行時 ATR=0 = 指標故障）。
            if !(atr > 0.0) {
                tracing::warn!(symbol = %intent.symbol,
                    "cost_gate fail-closed: ATR unavailable (SEC-11) / 成本門禁因 ATR 不可用拒絕");
                return IntentResult {
                    submitted: false,
                    rejected_reason: Some("cost_gate: ATR unavailable (fail-closed, SEC-11)".into()),
                    fill: None,
                };
            }
            if let Some(r) = self.cost_gate_paper(&intent.strategy, &intent.symbol,
                                                   atr, intent.confidence, final_qty, price) {
                return r;
            }
        }

        // Gate 4: Execute fill (paper mode)
        // NOTE: order_type and limit_price fields are currently IGNORED. All orders execute as
        // immediate market fills. Limit order execution (hold until price reaches limit_price)
        // will be implemented in Phase 2 when the Paper Engine gains an order book simulator.
        // 注意：order_type 和 limit_price 欄位當前被忽略。所有訂單均以即時市價成交。
        // 限價單執行（持有直到價格觸及 limit_price）將在 Phase 2 Paper Engine 獲得訂單簿模擬器後實現。
        let turnover = paper_state
            .latest_turnover(&intent.symbol)
            .unwrap_or(100_000_000.0);
        // Use live per-symbol fee rate (AccountManager → legacy → constant fallback).
        let fill = execution::execute_market_fill_with_rate(
            paper_state.latest_price(&intent.symbol).unwrap_or(0.0),
            final_qty,
            intent.is_long,
            turnover,
            self.fee_rate(&intent.symbol),
        );

        IntentResult {
            submitted: true,
            rejected_reason: None,
            fill: Some(fill),
        }
    }

    /// EXT-1: Process intent through governance gates only (no simulated execution).
    /// Returns ExchangeGateResult with approved_qty for exchange-mode order dispatch.
    /// EXT-1：僅通過治理門禁處理意圖（不模擬執行）。
    pub fn process_gates_only(
        &self,
        intent: &OrderIntent,
        governance: &GovernanceCore,
        paper_state: &PaperState,
        atr: f64,
    ) -> ExchangeGateResult {
        // Gate 1: Governance authorization
        if !governance.is_authorized() {
            return ExchangeGateResult {
                approved: false,
                rejected_reason: Some("governance_not_authorized".into()),
                approved_qty: 0.0,
            };
        }
        // Gate 1.5: Reject same-direction duplicate
        if let Some(existing) = paper_state.get_position(&intent.symbol) {
            if existing.is_long == intent.is_long {
                return ExchangeGateResult {
                    approved: false,
                    rejected_reason: Some(format!(
                        "duplicate_position: {} already {} {}",
                        intent.symbol,
                        if existing.is_long { "LONG" } else { "SHORT" },
                        existing.qty,
                    )),
                    approved_qty: 0.0,
                };
            }
        }
        // Gate 2: Guardian 4-check
        let positions: Vec<ExistingPosition> = paper_state
            .positions()
            .iter()
            .map(|p| ExistingPosition {
                symbol: p.symbol.clone(),
                side: if p.is_long {
                    "Buy".into()
                } else {
                    "Sell".into()
                },
            })
            .collect();
        let ctx = PortfolioContext {
            drawdown_pct: paper_state.drawdown_pct(),
            positions,
        };
        let check = TradeIntentCheck {
            symbol: intent.symbol.clone(),
            side: if intent.is_long {
                "Buy".into()
            } else {
                "Sell".into()
            },
            leverage: 1.0,
            qty: intent.qty,
        };
        let guardian_result = self.guardian.review(&check, &ctx);
        if let Verdict::Rejected = guardian_result.verdict {
            return ExchangeGateResult {
                approved: false,
                rejected_reason: Some(format!("guardian_rejected: {:?}", guardian_result.reasons)),
                approved_qty: 0.0,
            };
        }
        // Gate 2.5: Kelly position sizing
        let price = paper_state.latest_price(&intent.symbol).unwrap_or(0.0);
        let balance = paper_state.balance();
        let guardian_qty = guardian_result.modified_qty.unwrap_or(intent.qty);
        let kelly_qty = if let Some(ref kelly_cfg) = self.kelly_config {
            let stats = self
                .trade_stats
                .get(&intent.symbol)
                .cloned()
                .unwrap_or_default();
            // GAP-4: real ATR% from on_tick atr param.
            let atr_pct = if price > 0.0 && atr > 0.0 {
                atr / price
            } else {
                0.0
            };
            crate::ml::kelly_sizer::compute_kelly_qty(
                kelly_cfg,
                &stats,
                balance,
                price,
                atr_pct,
                guardian_qty,
            )
        } else {
            guardian_qty
        };
        // Gate 2.6: P1 hard cap
        let p1_max_qty = if price > 0.0 {
            balance * self.p1_risk_pct / price
        } else {
            kelly_qty
        };
        let final_qty = kelly_qty.min(p1_max_qty);

        // ─── PNL-1: Reject qty=0 ghost positions ───
        // 拒絕 qty=0 幽靈倉（小餘額被取整為 0 時必須阻止開倉）
        if !(final_qty > 0.0) {
            return ExchangeGateResult {
                approved: false,
                rejected_reason: Some(format!(
                    "qty_zero: final_qty={:.8} (kelly={:.8}, p1_cap={:.8}, balance=${:.2}, price=${:.2})",
                    final_qty, kelly_qty, p1_max_qty, balance, price,
                )),
                approved_qty: 0.0,
            };
        }

        // ─── Gate 2.7: Order admission risk check (RRC-1-B1) ───
        // 訂單准入風控檢查：日損/槓桿/持倉大小/曝險/相關曝險
        // Runs after P1 sizing so single-position-pct check uses final_qty.
        // 在 P1 調整後運行，以便單一持倉百分比檢查使用最終數量。
        {
            let is_reducing = paper_state
                .get_position(&intent.symbol)
                .map(|p| p.is_long != intent.is_long)
                .unwrap_or(false);
            let exposure_pct = Self::compute_exposure_pct(paper_state);
            let daily_loss = self.daily_loss_pct(balance);
            let check_result = check_order_allowed(
                final_qty,
                price,
                balance,
                exposure_pct,
                0.0, // correlated_exposure_pct — Phase C wiring
                1.0, // leverage — paper = 1x
                daily_loss,
                is_reducing,
                &self.risk_config,
            );
            if !check_result.allowed {
                return ExchangeGateResult {
                    approved: false,
                    rejected_reason: Some(format!("risk_gate: {}", check_result.reason)),
                    approved_qty: 0.0,
                };
            }
        }

        // ─── Gate 3: Cost gate — PH5-WIRE-1 live mode (fail-closed without positive estimate) ───
        // 成本門控：PH5-WIRE-1 live 模式（無正估計則失敗關閉，原則 #5 生存 > 利潤）
        {
            let min_confidence = self.risk_config.cost_gate.min_confidence;
            if intent.confidence < min_confidence {
                return ExchangeGateResult {
                    approved: false,
                    rejected_reason: Some(format!(
                        "cost_gate: confidence {:.2} < min {:.2}",
                        intent.confidence, min_confidence,
                    )),
                    approved_qty: 0.0,
                };
            }
            // SEC-11: ATR=0 → fail-closed.
            if !(atr > 0.0) {
                tracing::warn!(symbol = %intent.symbol,
                    "cost_gate fail-closed: ATR unavailable (SEC-11) / 成本門禁因 ATR 不可用拒絕");
                return ExchangeGateResult {
                    approved: false,
                    rejected_reason: Some("cost_gate: ATR unavailable (fail-closed, SEC-11)".into()),
                    approved_qty: 0.0,
                };
            }
            let fee_rate = self.fee_rate(&intent.symbol);
            if let Some(r) = self.cost_gate_live(&intent.strategy, &intent.symbol, fee_rate) {
                return r;
            }
        }

        ExchangeGateResult {
            approved: true,
            rejected_reason: None,
            approved_qty: final_qty,
        }
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

    /// PH5-WIRE-1: Paper/demo mode cost gate helper.
    /// Positive JS estimate → check EV vs fee (block if below).
    /// Negative JS estimate → exploration mode (allow + log; need data to improve estimates).
    /// No estimate (cold-start) → ATR×conf×0.2 fallback.
    /// Returns Some(rejected) on block, None on pass.
    /// PH5-WIRE-1：Paper/demo 模式成本門。
    /// 正估計 → EV 與 fee 比較；負估計 → 探索模式（允許+記錄）；無估計 → ATR×0.2 回退。
    fn cost_gate_paper(
        &self,
        strategy: &str,
        symbol: &str,
        atr: f64,
        conf: f64,
        qty: f64,
        price: f64,
    ) -> Option<IntentResult> {
        let fee_rate = self.fee_rate(symbol);
        let fee_bps = 2.0 * fee_rate * 10_000.0; // round-trip fee in bps
        match self.edge_estimates.get(strategy, symbol) {
            Some(bps) if bps > 0.0 => {
                // Positive JS estimate: use it as EV signal
                // 正 JS 估計：作為 EV 信號
                if bps < fee_bps {
                    return Some(IntentResult {
                        submitted: false,
                        rejected_reason: Some(format!(
                            "cost_gate(JS): shrunk_edge={:.2}bps < fee={:.2}bps",
                            bps, fee_bps,
                        )),
                        fill: None,
                    });
                }
                tracing::debug!(strategy, symbol, shrunk_edge_bps = bps,
                    "cost_gate(JS): positive edge — allowed / 正 edge 允許通過");
                None
            }
            Some(bps) => {
                // Negative JS estimate: exploration mode — allow to accumulate data.
                // Circular dependency: blocking here = no new data = estimates never improve.
                // 負 JS 估計：探索模式——允許以積累數據。
                // 循環依賴：攔截 = 無新數據 = 估計永遠不改善。
                tracing::info!(strategy, symbol, estimated_edge_bps = bps,
                    "cost_gate(JS): negative estimate — exploration mode / 負估計探索模式");
                None
            }
            None => {
                // Cold start: no JS estimate — ATR×conf×0.2 fallback (PH5-WIRE-0).
                // 冷啟動：無 JS 估計 — ATR×conf×0.2 回退（PH5-WIRE-0）。
                const DAMP: f64 = 0.2;
                let ev = atr * conf * qty * DAMP;
                let notional = qty * price;
                let rt_fee = notional * 2.0 * fee_rate;
                let k = self.cost_gate_k(notional).max(self.risk_config.cost_gate.k_base);
                if ev < k * rt_fee {
                    return Some(IntentResult {
                        submitted: false,
                        rejected_reason: Some(format!(
                            "cost_gate(ATR cold-start): EV ${ev:.4} < {k:.1}× fee ${rt_fee:.4} \
                             (atr={atr:.6}, conf={conf:.2}, damp={DAMP})",
                        )),
                        fill: None,
                    });
                }
                None
            }
        }
    }

    /// PH5-WIRE-1: Live mode cost gate — strictly requires positive JS estimate.
    /// Negative or missing estimate → fail-closed (root principle #5: survival > profit).
    /// Returns Some(rejected) on block, None on pass.
    /// PH5-WIRE-1：Live 模式成本門——嚴格要求正 JS 估計。
    /// 負/無估計 → 失敗關閉（根原則 #5：生存 > 利潤）。
    fn cost_gate_live(
        &self,
        strategy: &str,
        symbol: &str,
        fee_rate: f64,
    ) -> Option<ExchangeGateResult> {
        let fee_bps = 2.0 * fee_rate * 10_000.0;
        match self.edge_estimates.get(strategy, symbol) {
            Some(bps) if bps > 0.0 => {
                if bps < fee_bps {
                    return Some(ExchangeGateResult {
                        approved: false,
                        rejected_reason: Some(format!(
                            "cost_gate(JS-live): shrunk={:.2}bps < fee={:.2}bps", bps, fee_bps,
                        )),
                        approved_qty: 0.0,
                    });
                }
                None // pass
            }
            Some(bps) => Some(ExchangeGateResult {
                approved: false,
                rejected_reason: Some(format!(
                    "cost_gate(JS-live): estimated={:.2}bps < 0 — fail-closed / 負估計失敗關閉",
                    bps,
                )),
                approved_qty: 0.0,
            }),
            None => Some(ExchangeGateResult {
                approved: false,
                rejected_reason: Some(
                    "cost_gate(JS-live): no edge estimate — fail-closed (cold-start) / 無估計失敗關閉".into(),
                ),
                approved_qty: 0.0,
            }),
        }
    }

    /// PNL-5: Cost-gate k multiplier scaled by notional size, reading
    /// k_small / k_medium / k_base from RiskManagerConfig (Session 12 cleanup).
    /// PNL-5：成本門 k 倍率隨 notional 規模調整，三檔 k 從 config 讀取。
    fn cost_gate_k(&self, notional: f64) -> f64 {
        if notional < 50.0 {
            self.risk_config.cost_gate.k_small
        } else if notional < 200.0 {
            self.risk_config.cost_gate.k_medium
        } else {
            self.risk_config.cost_gate.k_base
        }
    }
}

impl Default for IntentProcessor {
    fn default() -> Self {
        Self::new()
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_intent_processor_linucb_optional_no_panic_when_unset() {
        // EN: Default constructor leaves linucb=None; select_arm_after_gates
        //     must return None without panicking.
        // 中文：預設未設 linucb 時，select_arm_after_gates 不可 panic，回 None。
        let mut ip = IntentProcessor::new();
        let ctx = vec![0.5; crate::linucb::CONTEXT_DIM_V1];
        assert!(ip
            .select_arm_after_gates("trending", "ma_crossover", &ctx)
            .is_none());
        assert!(ip.last_arm_selection().is_none());
    }

    #[test]
    fn test_intent_processor_linucb_select_called_after_gates_pass() {
        // EN: With a real LinUcbRuntime injected, select_arm_after_gates returns
        //     a valid selection and stores it as last_arm_selection.
        // 中文：注入真實 LinUcbRuntime 後，select_arm_after_gates 返回合法
        //     selection 並存入 last_arm_selection。
        let mut ip = IntentProcessor::new();
        ip.set_linucb_runtime(crate::linucb::LinUcbRuntime::cold_start_v1_15());
        let ctx = vec![0.5; crate::linucb::CONTEXT_DIM_V1];
        let sel = ip
            .select_arm_after_gates("trending", "ma_crossover", &ctx)
            .expect("arm exists");
        assert_eq!(sel.arm_id, "trending__ma_crossover");
        assert_eq!(ip.last_arm_selection().map(|s| s.arm_id.clone()),
                   Some("trending__ma_crossover".to_string()));
    }

    fn make_intent(symbol: &str, is_long: bool) -> OrderIntent {
        OrderIntent {
            symbol: symbol.into(),
            is_long,
            qty: 0.01,
            confidence: 0.7,
            strategy: "test".into(),
            order_type: "market".into(),
            limit_price: None,
        }
    }

    #[test]
    fn test_rejected_no_auth() {
        let proc = IntentProcessor::new();
        let gov = GovernanceCore::new(); // no auth
        let state = PaperState::new(10_000.0);
        let result = proc.process(&make_intent("BTC", true), &gov, &state, 500.0);
        assert!(!result.submitted);
        assert!(result.rejected_reason.unwrap().contains("governance"));
    }

    #[test]
    fn test_approved_with_auth() {
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(10_000.0);
        state.set_latest_price("BTC", 50000.0);
        // PH5-WIRE-0: ATR=2000 so EV=2000×0.7×0.004×0.2=$1.12 >> k×fee=1.5×$0.22=$0.33
        // (ATR raised from 500 to clear the 0.2 cold-start dampening factor)
        let result = proc.process(&make_intent("BTC", true), &gov, &state, 2000.0);
        assert!(result.submitted);
        assert!(result.fill.is_some());
    }

    #[test]
    fn test_position_sizing_caps_qty() {
        // P1 cap: 2% of 10,000 / 50,000 = 0.004 BTC
        // Intent qty 0.01 should be reduced to 0.004.
        // P1 上限：10,000 * 2% / 50,000 = 0.004 BTC；意圖 qty 0.01 縮小為 0.004。
        // PH5-WIRE-0: ATR=2000 so EV=2000×0.7×0.004×0.2=$1.12 >> k×fee=$0.33
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(10_000.0);
        state.set_latest_price("BTC", 50_000.0);
        let intent = make_intent("BTC", true); // qty=0.01
        let result = proc.process(&intent, &gov, &state, 2000.0);
        assert!(result.submitted);
        let fill = result.fill.unwrap();
        // fill.fill_qty should be 0.004 (= 10000 * 0.02 / 50000), not 0.01
        assert!(
            (fill.fill_qty - 0.004).abs() < 1e-9,
            "Expected qty ~0.004 from P1 sizing, got {}",
            fill.fill_qty
        );
    }

    #[test]
    fn test_position_sizing_tiny_balance() {
        // With tiny balance, P1 calc gives very small qty — no artificial floor.
        // 餘額極小時，P1 計算給出極小 qty — 無人為下限。
        // PH5-WIRE-0: need ATR=2000 to clear cost_gate with dampening 0.2 at tiny notional.
        // final_qty=0.00004, notional=$2 → k=3.0, fee=$0.0022, need EV=2000×0.7×0.00004×0.2=$0.0112>$0.0066
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(100.0); // tiny balance
        state.set_latest_price("BTC", 50_000.0);
        let intent = make_intent("BTC", true); // qty=0.01
        let result = proc.process(&intent, &gov, &state, 2000.0);
        assert!(result.submitted);
        let fill = result.fill.unwrap();
        // P1 calc: 100 * 0.02 / 50000 = 0.00004 — used directly, no MIN_QTY floor.
        assert!(
            (fill.fill_qty - 0.00004).abs() < 1e-9,
            "Expected P1-sized qty 0.00004, got {}",
            fill.fill_qty
        );
    }

    #[test]
    fn test_position_sizing_small_intent_unchanged() {
        // If intent.qty < P1 cap, intent.qty is used (sizing never increases).
        // 如果 intent.qty < P1 上限，使用 intent.qty（sizing 只會縮小）。
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(1_000_000.0); // large balance
        state.set_latest_price("ETH", 3_000.0);
        // P1 cap: 1,000,000 * 0.02 / 3000 = 6.67; intent qty=0.01 is smaller
        let intent = make_intent("ETH", true); // qty=0.01
        let result = proc.process(&intent, &gov, &state, 500.0);
        assert!(result.submitted);
        let fill = result.fill.unwrap();
        assert!(
            (fill.fill_qty - 0.01).abs() < 1e-9,
            "Expected intent qty 0.01 (under P1 cap), got {}",
            fill.fill_qty
        );
    }

    #[test]
    fn test_guardian_drawdown_rejection() {
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(10_000.0);
        state.set_latest_price("BTC", 50000.0);
        // Simulate high drawdown
        state.force_drawdown(20.0);
        let result = proc.process(&make_intent("BTC", true), &gov, &state, 500.0);
        assert!(!result.submitted);
    }

    #[test]
    fn test_cost_gate_rejects_low_confidence() {
        // Confidence below 0.15 → always rejected regardless of ATR
        // 信心低於 0.15 → 無論 ATR 如何都拒絕
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(10_000.0);
        state.set_latest_price("ETH", 2000.0);
        let intent = OrderIntent {
            symbol: "ETH".into(),
            is_long: true,
            qty: 0.01,
            confidence: 0.10,
            strategy: "test".into(),
            order_type: "market".into(),
            limit_price: None,
        };
        let result = proc.process(&intent, &gov, &state, 10.0);
        assert!(!result.submitted);
        assert!(result
            .rejected_reason
            .unwrap()
            .contains("cost_gate: confidence"));
    }

    #[test]
    fn test_cost_gate_rejects_low_ev() {
        // Low ATR + moderate confidence → EV < fee threshold → rejected
        // 低 ATR + 中等信心 → EV < 手續費門檻 → 拒絕
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(10_000.0);
        state.set_latest_price("BTC", 67000.0);
        let intent = OrderIntent {
            symbol: "BTC".into(),
            is_long: true,
            qty: 0.001,
            confidence: 0.30,
            strategy: "test".into(),
            order_type: "market".into(),
            limit_price: None,
        };
        // ATR=20 (very compressed for BTC), notional=$67 → rt_fee=$0.074 → EV=20×0.3×0.001=$0.006
        // PH5-WIRE-1: no JS estimate (cold-start) → ATR fallback → "cost_gate(ATR cold-start): EV"
        let result = proc.process(&intent, &gov, &state, 20.0);
        assert!(!result.submitted);
        assert!(result.rejected_reason.unwrap().contains("cost_gate(ATR cold-start)"));
    }

    #[test]
    fn test_sec11_cost_gate_fail_closed_on_zero_atr() {
        // SEC-11: ATR=0 must reject (fail-closed), not bypass the gate.
        // SEC-11：ATR=0 必須拒絕（fail-closed），不可繞過。
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(10_000.0);
        state.set_latest_price("BTC", 67000.0);
        let intent = OrderIntent {
            symbol: "BTC".into(),
            is_long: true,
            qty: 0.001,
            confidence: 0.50,
            strategy: "test".into(),
            order_type: "market".into(),
            limit_price: None,
        };
        // ATR=0 (indicator unavailable) — would have been waved through pre-SEC-11
        let result = proc.process(&intent, &gov, &state, 0.0);
        assert!(!result.submitted, "ATR=0 must fail-closed");
        assert!(result
            .rejected_reason
            .unwrap()
            .contains("ATR unavailable"));

        // Same on the exchange-mode path
        let gate = proc.process_gates_only(&intent, &gov, &state, 0.0);
        assert!(!gate.approved, "ATR=0 must fail-closed in gates_only too");
        assert!(gate.rejected_reason.unwrap().contains("ATR unavailable"));
    }

    #[test]
    fn test_process_gates_only_cost_gate_rejects_low_ev() {
        // I-01: process_gates_only must enforce Gate 3 cost gate like process().
        // I-01：process_gates_only 必須像 process() 一樣執行 Gate 3 成本門控。
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(10_000.0);
        state.set_latest_price("BTC", 67000.0);
        let intent = OrderIntent {
            symbol: "BTC".into(),
            is_long: true,
            qty: 0.001,
            confidence: 0.30,
            strategy: "test".into(),
            order_type: "market".into(),
            limit_price: None,
        };
        // ATR=20 compressed → EV << fee → reject
        let result = proc.process_gates_only(&intent, &gov, &state, 20.0);
        assert!(!result.approved);
        assert!(result.rejected_reason.unwrap().contains("cost_gate"));
    }

    #[test]
    fn test_cost_gate_accepts_good_ev() {
        // High ATR + high confidence → EV >> fee → accepted.
        // 高 ATR + 高信心 → EV >> 手續費 → 接受。
        // PH5-WIRE-0 (cold-start 0.2 dampening):
        //   ATR=5.0, EV=5.0×0.7×0.2×0.2=$0.14, notional=$16 → k=3.0, rt_fee=$0.018 → k×fee=$0.053
        //   EV=$0.14 >> $0.053 ✓  (ATR raised from 1.5 to clear the 0.2 dampening at k=3.0)
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(10_000.0);
        state.set_latest_price("SOL", 80.0);
        let intent = OrderIntent {
            symbol: "SOL".into(),
            is_long: true,
            qty: 0.2,
            confidence: 0.7,
            strategy: "test".into(),
            order_type: "market".into(),
            limit_price: None,
        };
        let result = proc.process(&intent, &gov, &state, 5.0);
        assert!(result.submitted);
    }

    #[test]
    fn test_pnl5_cost_gate_k_tiers() {
        // PNL-5: k=3.0 below $50, k=2.0 below $200, k=1.5 otherwise (defaults).
        let proc = IntentProcessor::new();
        assert_eq!(proc.cost_gate_k(20.0), 3.0);
        assert_eq!(proc.cost_gate_k(49.99), 3.0);
        assert_eq!(proc.cost_gate_k(50.0), 2.0);
        assert_eq!(proc.cost_gate_k(199.99), 2.0);
        assert_eq!(proc.cost_gate_k(200.0), 1.5);
        assert_eq!(proc.cost_gate_k(10_000.0), 1.5);
    }

    #[test]
    fn test_pnl5_small_notional_tightens_cost_gate() {
        // PNL-5: A trade that passed the old k=1.5 gate now fails under k=3.0
        // because notional ~ $20 falls into the smallest tier.
        // PNL-5：在 $20 notional 級別，原本通過 k=1.5 的單現在 k=3.0 應被攔截。
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(1_000.0); // $1k balance
        state.set_latest_price("SOL", 80.0);
        // qty 0.005 → notional $0.40 → tier <$50 → k=3.0
        // EV = atr(0.5) * conf(0.4) * 0.005 = 0.001
        // fee = 0.4 * 2 * 0.00055 = 0.00044
        // 1.5 * fee = 0.00066 (would pass), 3.0 * fee = 0.00132 (fails)
        let intent = OrderIntent {
            symbol: "SOL".into(),
            is_long: true,
            qty: 0.005,
            confidence: 0.4,
            strategy: "test".into(),
            order_type: "market".into(),
            limit_price: None,
        };
        let result = proc.process(&intent, &gov, &state, 0.5);
        assert!(!result.submitted, "PNL-5: expected reject under tightened k");
        assert!(result.rejected_reason.unwrap().contains("3.0× fee"));
    }

    #[test]
    fn test_pnl1_rejects_qty_zero_process() {
        // PNL-1: When P1 sizing produces final_qty=0 (e.g. balance=0), reject.
        // PNL-1：P1 sizing 產生 final_qty=0 時拒絕（餘額=0 等情況）
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(0.0); // zero balance → p1_max_qty=0
        state.set_latest_price("BTC", 50_000.0);
        let intent = make_intent("BTC", true);
        let result = proc.process(&intent, &gov, &state, 500.0);
        assert!(!result.submitted);
        let reason = result.rejected_reason.unwrap();
        assert!(reason.starts_with("qty_zero:"), "got: {}", reason);
    }

    #[test]
    fn test_pnl1_rejects_qty_zero_gates_only() {
        // PNL-1 (exchange path): same guard in process_gates_only.
        // PNL-1（exchange 路徑）：process_gates_only 同一守衛
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(0.0);
        state.set_latest_price("BTC", 50_000.0);
        let intent = make_intent("BTC", true);
        let result = proc.process_gates_only(&intent, &gov, &state, 500.0);
        assert!(!result.approved);
        assert_eq!(result.approved_qty, 0.0);
        assert!(result.rejected_reason.unwrap().starts_with("qty_zero:"));
    }
}
