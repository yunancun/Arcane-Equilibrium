//! BB Breakout Strategy V2 — Squeeze→Expansion + Volume + Donchian + ATR trailing stop + Regime exit.
//! BB 突破策略 V2 — 壓縮→擴張 + 成交量 + Donchian + ATR 追蹤止損 + Regime 出場。
//!
//! MODULE_NOTE (EN): Detects Bollinger Band squeeze→expansion with volume
//!   confirmation and Donchian channel breakout. ATR-based trailing stop for exits.
//! MODULE_NOTE (中): 檢測布林帶壓縮→擴張 + 成交量確認 + Donchian 通道突破。
//!   ATR 追蹤止損出場。

use std::collections::HashMap;

use super::common::{PerSymbolState, TrendCooldown};
use super::confluence::{self, ConfluenceConfig, PersistenceTracker};
use super::{ParamRange, Strategy, StrategyAction, StrategyParams};
use crate::intent_processor::OrderIntent;
use crate::tick_pipeline::TickContext;
use serde::{Deserialize, Serialize};
use tracing::info;

/// Tunable parameters for BB Breakout (Phase 3a).
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct BbBreakoutParams {
    pub cooldown_ms: u64,
    pub default_qty: f64,
    pub squeeze_bw: f64,
    pub expansion_bw: f64,
    pub volume_threshold: f64,
    pub trailing_stop_atr_mult: f64,
    /// FIX-26: Squeeze state expiry duration (ms). Default 30 min.
    /// FIX-26：壓縮狀態有效期（ms）。默認 30 分鐘。
    pub squeeze_expiry_ms: u64,
    // ── G-SR-1 confluence + persistence fields (A0-c) ──
    /// Minimum signal persistence before entry (ms). / 入場前信號最小持續時間（ms）。
    pub min_persistence_ms: u64,
    /// Minimum order notional (USD). / 最小訂單名義值（USD）。
    pub min_notional_usd: f64,
    /// Confluence as qty modifier only (not gate). / 匯流僅作為 qty 調整器（非門控）。
    pub confluence_as_gate: bool,
    /// Confluence weights + thresholds (breakout profile).
    pub weight_adx: f64,
    pub weight_regime: f64,
    pub weight_volume: f64,
    pub weight_momentum: f64,
    pub adx_floor: f64,
    pub confluence_threshold_no_trade: f64,
    pub confluence_threshold_light: f64,
    pub confluence_threshold_full: f64,
    // ── E5-P2-4: Previously hard-coded magic numbers lifted to config ──
    // ── E5-P2-4：原本 hard-coded 的魔術數字提升為 config 參數 ──
    /// Hurst trending regime entry confidence boost (default 0.1).
    /// Adds to entry confidence when Hurst regime == "trending".
    /// Hurst 趨勢狀態入場信心加成（默認 0.1）。當 Hurst regime == "trending" 時加到入場信心。
    pub hurst_regime_boost: f64,
    /// Exit confidence bonus for trailing stop hit (default 0.2).
    /// 追蹤止損觸發時的出場信心加成（默認 0.2）。
    pub exit_bonus_trailing_stop: f64,
    /// Exit confidence bonus for Hurst regime shift exit (default 0.1).
    /// Hurst regime 轉向出場時的信心加成（默認 0.1）。
    pub exit_bonus_regime_shift: f64,
    /// Exit confidence bonus for %B revert-to-middle exit (default 0.05).
    /// %B 回中軌出場時的信心加成（默認 0.05）。
    pub exit_bonus_pctb_revert: f64,
    /// Exit confidence penalty (magnitude, subtracted) for BW squeeze exit (default 0.05).
    /// BW 帶寬再壓縮出場時的信心扣減幅度（默認 0.05，實際套用時為減法）。
    pub exit_penalty_bw_squeeze: f64,
}

impl Default for BbBreakoutParams {
    fn default() -> Self {
        let cc = ConfluenceConfig::breakout();
        Self {
            cooldown_ms: 300_000,
            default_qty: 1e9,
            squeeze_bw: DEFAULT_SQUEEZE_BW,
            expansion_bw: DEFAULT_EXPANSION_BW,
            volume_threshold: DEFAULT_VOLUME_THRESHOLD,
            trailing_stop_atr_mult: 2.0,
            squeeze_expiry_ms: 2_700_000, // EDGE-P1-4: 30min→45min
            min_persistence_ms: 60_000,   // 1 min (triple gate already strict)
            min_notional_usd: 10.0,
            confluence_as_gate: false,
            weight_adx: cc.weight_adx,
            weight_regime: cc.weight_regime,
            weight_volume: cc.weight_volume,
            weight_momentum: cc.weight_momentum,
            adx_floor: cc.adx_floor,
            confluence_threshold_no_trade: cc.threshold_no_trade,
            confluence_threshold_light: cc.threshold_light,
            confluence_threshold_full: cc.threshold_full,
            // E5-P2-4: preserve exact pre-extraction values (bit-exact behaviour)
            // E5-P2-4：保留原始 hard-coded 值（維持 bit-exact 行為）
            hurst_regime_boost: 0.1,
            exit_bonus_trailing_stop: 0.2,
            exit_bonus_regime_shift: 0.1,
            exit_bonus_pctb_revert: 0.05,
            exit_penalty_bw_squeeze: 0.05,
        }
    }
}

impl StrategyParams for BbBreakoutParams {
    fn param_ranges() -> Vec<ParamRange> {
        vec![
            ParamRange {
                name: "cooldown_ms".into(),
                min: 60_000.0,
                max: 3_600_000.0,
                step: Some(60_000.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "squeeze_bw".into(),
                min: 0.005,
                max: 0.05,
                step: None,
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "expansion_bw".into(),
                min: 0.02,
                max: 0.1,
                step: None,
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "volume_threshold".into(),
                min: 1.0,
                max: 5.0,
                step: Some(0.1),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "trailing_stop_atr_mult".into(),
                min: 1.0,
                max: 5.0,
                step: Some(0.5),
                agent_adjustable: true,
                db_persisted: true,
            },
            // ── G-SR-1 S3: Confluence param ranges (R3-4: exempt from ±30% delta cap) ──
            // ── G-SR-1 S3：匯流參數範圍（R3-4：豁免 ±30% delta 上限）──
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
            ParamRange {
                name: "adx_floor".into(),
                min: 0.0,
                max: 30.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "confluence_threshold_no_trade".into(),
                min: 10.0,
                max: 55.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "confluence_threshold_light".into(),
                min: 20.0,
                max: 60.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "confluence_threshold_full".into(),
                min: 30.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "confluence_as_gate".into(),
                min: 0.0,
                max: 1.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "min_persistence_ms".into(),
                min: 0.0,
                max: 300_000.0,
                step: Some(10_000.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "min_notional_usd".into(),
                min: 1.0,
                max: 100.0,
                step: Some(1.0),
                agent_adjustable: false,
                db_persisted: true,
            },
        ]
    }

    fn validate(&self) -> Result<(), String> {
        if self.squeeze_bw >= self.expansion_bw {
            return Err("squeeze_bw must be < expansion_bw".into());
        }
        if self.volume_threshold < 1.0 {
            return Err("volume_threshold must be >= 1.0".into());
        }
        if self.trailing_stop_atr_mult < 0.5 {
            return Err("trailing_stop_atr_mult must be >= 0.5".into());
        }
        self.build_confluence_config().validate()?;
        // G-SR-1 S3: Threshold ordering / 閾值排序驗證
        if self.confluence_threshold_no_trade >= self.confluence_threshold_light
            || self.confluence_threshold_light >= self.confluence_threshold_full
        {
            return Err("confluence thresholds must be ordered: no_trade < light < full".into());
        }
        if self.min_notional_usd < 1.0 {
            return Err("min_notional_usd must be >= 1.0".into());
        }
        Ok(())
    }
}

impl BbBreakoutParams {
    /// Build ConfluenceConfig (breakout profile: qty modifier only, non-inverted ADX).
    /// 構建 ConfluenceConfig（突破配置：僅 qty 調整器，非反轉 ADX）。
    pub fn build_confluence_config(&self) -> ConfluenceConfig {
        ConfluenceConfig {
            weight_adx: self.weight_adx,
            weight_regime: self.weight_regime,
            weight_volume: self.weight_volume,
            weight_momentum: self.weight_momentum,
            adx_floor: self.adx_floor,
            invert_adx: false,
            threshold_no_trade: self.confluence_threshold_no_trade,
            threshold_light: self.confluence_threshold_light,
            threshold_full: self.confluence_threshold_full,
            confluence_as_gate: self.confluence_as_gate,
        }
    }
}

/// Default bandwidth threshold to detect squeeze (壓縮帶寬閾值默認)
const DEFAULT_SQUEEZE_BW: f64 = 0.03; // EDGE-P1-4: 0.02→0.03 (relax squeeze detection)
/// Default bandwidth threshold to detect expansion (擴張帶寬閾值默認)
const DEFAULT_EXPANSION_BW: f64 = 0.04;
/// Default volume ratio threshold for breakout confirmation (成交量確認閾值默認)
const DEFAULT_VOLUME_THRESHOLD: f64 = 1.2; // EDGE-P1-4: 1.5→1.2 (lower volume bar)

/// Per-symbol dynamic state for `BbBreakout`. All fields are independently
/// optional: absence of a squeeze, an entry-price, or a trailing-stop each have
/// distinct meanings from "no position". `Default` → all `None`, matching the
/// behaviour of the previous 4 parallel `HashMap`s.
/// `BbBreakout` 的逐 symbol 動態狀態；4 個欄位各自獨立可選，等價於原先 4 個平行
/// HashMap 的語意。`Default` = 全 `None`，對應「從未見過該 symbol」。
#[derive(Debug, Clone, Default)]
pub(crate) struct BbBreakoutPerSymbolState {
    /// Current position direction if open: `Some(true)` = long, `Some(false)` = short.
    /// 當前方向：Some(true)=多, Some(false)=空, None=空倉。
    pub position: Option<bool>,
    /// First timestamp squeeze was detected (FIX-26 expiry window anchor).
    /// FIX-26：首次偵測壓縮的時間戳（作為 squeeze_expiry_ms 的錨點）。
    pub squeeze_detected_ms: Option<u64>,
    /// Entry price at position open (for PnL/trail math).
    /// 開倉價（供 PnL/追蹤止損計算）。
    pub entry_price: Option<f64>,
    /// Current ATR trailing stop level.
    /// 當前 ATR 追蹤止損價位。
    pub trailing_stop: Option<f64>,
}

pub struct BbBreakout {
    active: bool,
    /// Per-symbol state (position/squeeze/entry_price/trailing_stop).
    /// 逐 symbol 狀態（持倉/壓縮/進場價/追蹤止損），以 PerSymbolState 統一容器承載。
    pub(crate) symbols: PerSymbolState<BbBreakoutPerSymbolState>,
    /// FIX-26: Max duration (ms) a squeeze remains valid. Default 30 min.
    /// FIX-26：壓縮狀態最長有效期（ms）。默認 30 分鐘。
    pub squeeze_expiry_ms: u64,
    /// Per-symbol cooldown tracking (was `last_trade_ms: HashMap<String, u64>`).
    /// 逐 symbol 冷卻追蹤（取代原 last_trade_ms HashMap）。
    pub(crate) cooldown: TrendCooldown,
    pub(crate) cooldown_ms: u64,
    default_qty: f64,
    /// ATR multiplier for trailing stop distance. Agent-adjustable (Phase 3a).
    /// ATR 追蹤止損距離乘數。Agent 可調（Phase 3a）。
    pub trailing_stop_atr_mult: f64,
    // RC-03: Configurable thresholds for Agent adjustability
    // RC-03：可配置閾值，供 Agent 動態調整
    /// Bandwidth below this = squeeze detected / 帶寬低於此值 = 偵測到壓縮
    pub squeeze_bw: f64,
    /// QC-H4: Entry confidence base (default 0.7). / 入場信心基礎值。
    pub(crate) entry_conf_base: f64,
    /// QC-H4: Exit confidence base (default 0.5). Exit reasons add offsets.
    /// QC-H4：出場信心基礎值。各出場原因加減偏移。
    pub(crate) exit_conf_base: f64,
    /// Bandwidth above this = expansion confirmed / 帶寬高於此值 = 確認擴張
    pub expansion_bw: f64,
    /// Minimum volume ratio for breakout entry / 突破入場最低成交量倍率
    pub volume_threshold: f64,
    // RC-04: Per-symbol previous state for rejection rollback / 每幣種拒絕回滾用的先前狀態
    //
    // Snapshot of the *entire* `BbBreakoutPerSymbolState` for the symbol at
    // tick entry; restored on rejection. `None` = symbol was unseen at snapshot.
    // 於 tick 進入時快照整個逐 symbol 狀態；拒絕時還原。None = 快照時該 symbol 不存在。
    prev_state: HashMap<String, Option<BbBreakoutPerSymbolState>>,
    prev_last_trade_ms: HashMap<String, u64>,
    /// CONF-D: Multiplier applied to emitted intent.confidence (default 1.0, range [0,2]).
    conf_scale: f64,
    // ── G-SR-1: Confluence scoring + persistence filter (A0-c, A1) ──
    pub confluence_config: ConfluenceConfig,
    persistence: PersistenceTracker,
    pub min_persistence_ms: u64,
    pub min_notional_usd: f64,
    // ── E5-P2-4: Config-driven exit confidence offsets + Hurst boost ──
    // ── E5-P2-4：config 驅動的出場信心偏移 + Hurst 加成 ──
    /// Hurst trending regime entry confidence boost. / Hurst 趨勢入場信心加成。
    pub(crate) hurst_regime_boost: f64,
    /// Trailing-stop exit confidence bonus. / 追蹤止損出場信心加成。
    pub(crate) exit_bonus_trailing_stop: f64,
    /// Regime-shift exit confidence bonus. / Regime 轉向出場信心加成。
    pub(crate) exit_bonus_regime_shift: f64,
    /// %B revert exit confidence bonus. / %B 回中軌出場信心加成。
    pub(crate) exit_bonus_pctb_revert: f64,
    /// BW squeeze exit confidence penalty (magnitude). / BW 再壓縮出場信心扣減幅度。
    pub(crate) exit_penalty_bw_squeeze: f64,
}

impl BbBreakout {
    pub fn new() -> Self {
        Self {
            active: true,
            symbols: PerSymbolState::new(),
            squeeze_expiry_ms: 2_700_000, // EDGE-P1-4: 45 minutes (was 30)
            cooldown: TrendCooldown::new(600_000),
            cooldown_ms: 600_000,
            default_qty: 1e9,
            trailing_stop_atr_mult: 2.0,
            squeeze_bw: DEFAULT_SQUEEZE_BW,
            expansion_bw: DEFAULT_EXPANSION_BW,
            volume_threshold: DEFAULT_VOLUME_THRESHOLD,
            entry_conf_base: 0.7,
            exit_conf_base: 0.5,
            prev_state: HashMap::new(),
            prev_last_trade_ms: HashMap::new(),
            conf_scale: 1.0,
            confluence_config: ConfluenceConfig::breakout(),
            persistence: PersistenceTracker::new(),
            min_persistence_ms: 60_000, // 1 min (triple gate already strict)
            min_notional_usd: 10.0,
            // E5-P2-4: preserve exact pre-extraction values (bit-exact behaviour)
            // E5-P2-4：保留原始值以確保行為 bit-exact
            hurst_regime_boost: 0.1,
            exit_bonus_trailing_stop: 0.2,
            exit_bonus_regime_shift: 0.1,
            exit_bonus_pctb_revert: 0.05,
            exit_penalty_bw_squeeze: 0.05,
        }
    }

    pub fn update_params(&mut self, params: BbBreakoutParams) -> Result<(), String> {
        params.validate()?;
        self.cooldown_ms = params.cooldown_ms;
        // Keep TrendCooldown duration in sync with param (hot-reloadable).
        // 保持 TrendCooldown 時長與參數同步（支援熱重載）。
        self.cooldown.set_duration(params.cooldown_ms);
        self.default_qty = params.default_qty;
        self.squeeze_bw = params.squeeze_bw;
        self.expansion_bw = params.expansion_bw;
        self.volume_threshold = params.volume_threshold;
        self.trailing_stop_atr_mult = params.trailing_stop_atr_mult;
        self.squeeze_expiry_ms = params.squeeze_expiry_ms;
        self.confluence_config = params.build_confluence_config();
        self.min_persistence_ms = params.min_persistence_ms;
        self.min_notional_usd = params.min_notional_usd;
        // E5-P2-4: hot-reload config-driven confidence offsets.
        // E5-P2-4：熱重載 config 驅動的信心偏移參數。
        self.hurst_regime_boost = params.hurst_regime_boost;
        self.exit_bonus_trailing_stop = params.exit_bonus_trailing_stop;
        self.exit_bonus_regime_shift = params.exit_bonus_regime_shift;
        self.exit_bonus_pctb_revert = params.exit_bonus_pctb_revert;
        self.exit_penalty_bw_squeeze = params.exit_penalty_bw_squeeze;
        info!(strategy = "bb_breakout", "params updated / 參數已更新");
        Ok(())
    }

    pub fn get_params(&self) -> BbBreakoutParams {
        BbBreakoutParams {
            cooldown_ms: self.cooldown_ms,
            default_qty: self.default_qty,
            squeeze_bw: self.squeeze_bw,
            expansion_bw: self.expansion_bw,
            volume_threshold: self.volume_threshold,
            trailing_stop_atr_mult: self.trailing_stop_atr_mult,
            squeeze_expiry_ms: self.squeeze_expiry_ms,
            min_persistence_ms: self.min_persistence_ms,
            min_notional_usd: self.min_notional_usd,
            confluence_as_gate: self.confluence_config.confluence_as_gate,
            weight_adx: self.confluence_config.weight_adx,
            weight_regime: self.confluence_config.weight_regime,
            weight_volume: self.confluence_config.weight_volume,
            weight_momentum: self.confluence_config.weight_momentum,
            adx_floor: self.confluence_config.adx_floor,
            confluence_threshold_no_trade: self.confluence_config.threshold_no_trade,
            confluence_threshold_light: self.confluence_config.threshold_light,
            confluence_threshold_full: self.confluence_config.threshold_full,
            // E5-P2-4: expose new fields for Agent `get_params_json` round-trip.
            // E5-P2-4：新增欄位供 Agent `get_params_json` 往返使用。
            hurst_regime_boost: self.hurst_regime_boost,
            exit_bonus_trailing_stop: self.exit_bonus_trailing_stop,
            exit_bonus_regime_shift: self.exit_bonus_regime_shift,
            exit_bonus_pctb_revert: self.exit_bonus_pctb_revert,
            exit_penalty_bw_squeeze: self.exit_penalty_bw_squeeze,
        }
    }

    // ── Per-symbol accessors (test-facing; also handy for observability) ──
    // 逐 symbol 存取器（供測試使用，外部觀察亦可調用）。

    /// Current position direction for `symbol` (None if flat or unseen).
    /// 該 symbol 當前持倉方向，平倉或未見則為 None。
    #[inline]
    pub fn position_of(&self, symbol: &str) -> Option<bool> {
        self.symbols.get(symbol).and_then(|s| s.position)
    }

    /// Recorded entry price for `symbol` (None if flat or unseen).
    /// 該 symbol 最近一次開倉價，平倉或未見則為 None。
    #[inline]
    pub fn entry_price_of(&self, symbol: &str) -> Option<f64> {
        self.symbols.get(symbol).and_then(|s| s.entry_price)
    }

    /// Current ATR trailing stop for `symbol` (None if flat / not yet set).
    /// 該 symbol 當前 ATR 追蹤止損價，平倉或尚未設定則為 None。
    #[inline]
    pub fn trailing_stop_of(&self, symbol: &str) -> Option<f64> {
        self.symbols.get(symbol).and_then(|s| s.trailing_stop)
    }

    /// True if `symbol` has a recorded squeeze-detection timestamp.
    /// 該 symbol 是否登記了壓縮起始時間戳。
    #[inline]
    pub fn has_squeeze(&self, symbol: &str) -> bool {
        self.symbols
            .get(symbol)
            .map(|s| s.squeeze_detected_ms.is_some())
            .unwrap_or(false)
    }
}

impl Strategy for BbBreakout {
    fn name(&self) -> &str {
        "bb_breakout"
    }
    fn is_active(&self) -> bool {
        self.active
    }
    fn set_active(&mut self, active: bool) {
        self.active = active;
    }

    /// Reset per-symbol position state on external close (risk-stop).
    /// Preserves `squeeze_detected_ms` (squeeze can continue across close).
    /// 外部平倉（風控止損）時重設該幣種內部狀態；`squeeze_detected_ms` 保留
    /// （壓縮狀態可跨越平倉延續）。
    fn on_external_close(&mut self, symbol: &str) {
        if let Some(st) = self.symbols.get_mut(symbol) {
            st.position = None;
            st.entry_price = None;
            st.trailing_stop = None;
        }
        self.persistence.clear(symbol);
    }

    /// RC-04: Revert per-symbol state on rejection. Snapshot is the full
    /// `BbBreakoutPerSymbolState` (or `None` if the symbol was unseen); restoring
    /// it exactly reproduces the pre-tick per-symbol state.
    /// RC-04：拒絕時還原該幣種整包逐 symbol 狀態快照（快照時若未見過 symbol 則為 None）。
    fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
        let sym = &intent.symbol;
        if let Some(prev) = self.prev_state.get(sym) {
            match prev {
                Some(prev_st) => {
                    self.symbols.insert(sym.to_string(), prev_st.clone());
                }
                None => {
                    self.symbols.remove(sym);
                }
            }
        }
        if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
            if ts == 0 {
                self.cooldown.clear(sym);
            } else {
                self.cooldown.record_signal(sym, ts);
            }
        }
    }

    fn on_tick(&mut self, ctx: &TickContext<'_>) -> Vec<StrategyAction> {
        let ind = match ctx.indicators {
            Some(i) => i,
            None => return vec![],
        };
        let bb = match &ind.bollinger {
            Some(b) => b,
            None => return vec![],
        };
        let vol_ratio = ind.volume_ratio.unwrap_or(1.0);

        // RC-04: Snapshot per-symbol state before any mutation for rejection rollback.
        // Whole-struct snapshot = exact pre-tick state (or None if unseen).
        // RC-04：於任何變更前快照該 symbol 整包狀態（None = 本 tick 之前未見）。
        let sym = ctx.symbol;
        self.prev_state
            .insert(sym.to_string(), self.symbols.get(sym).cloned());
        let last_ms = self.cooldown.last_ms(sym).unwrap_or(0);
        self.prev_last_trade_ms.insert(sym.to_string(), last_ms);

        if bb.bandwidth < self.squeeze_bw {
            // FIX-26: Only record first detection time; don't reset on continued squeeze.
            // FIX-26：只記錄首次偵測，持續壓縮不重置。
            let st = self.symbols.get_or_init(sym);
            if st.squeeze_detected_ms.is_none() {
                st.squeeze_detected_ms = Some(ctx.timestamp_ms);
            }
        }
        if !self.cooldown.is_cooled_down(sym, ctx.timestamp_ms) {
            return vec![];
        }

        let mut intents = Vec::new();
        let current_position = self.symbols.get(sym).and_then(|s| s.position);
        match current_position {
            None => {
                // FIX-26: Check squeeze exists AND hasn't expired.
                let in_squeeze = self
                    .symbols
                    .get(sym)
                    .and_then(|s| s.squeeze_detected_ms)
                    .map(|ts| ctx.timestamp_ms < ts + self.squeeze_expiry_ms)
                    .unwrap_or(false);
                if in_squeeze
                    && bb.bandwidth > self.expansion_bw
                    && vol_ratio >= self.volume_threshold
                {
                    let is_long = bb.percent_b > 1.0;
                    let is_short = bb.percent_b < 0.0;

                    // A3: Donchian confirmation — price must also breach Donchian channel
                    // A3：Donchian 确认 — 价格需同时突破 Donchian 通道
                    if let Some(dc) = &ind.donchian {
                        if is_long && ctx.price < dc.upper {
                            return vec![];
                        }
                        if is_short && ctx.price > dc.lower {
                            return vec![];
                        }
                    }

                    if is_long || is_short {
                        // A1: Persistence filter — triple gate signal must hold.
                        // A1：持續性過濾 — 三重門控信號必須持續。
                        let signal = Some(is_long);
                        if !self.persistence.check(
                            sym,
                            signal,
                            ctx.timestamp_ms,
                            self.min_persistence_ms,
                            false,
                        ) {
                            return intents;
                        }

                        // A4: Hurst regime boost — trending regime boosts breakout confidence
                        // A4：Hurst 趋势状态 — 趋势型市场提升突破信心
                        // E5-P2-4: magnitude now config-driven (was hard-coded 0.1).
                        // E5-P2-4：加成幅度改由 config 控制（原 hard-coded 0.1）。
                        let hurst_boost: f64 = match &ind.hurst {
                            Some(h) if h.regime == "trending" => self.hurst_regime_boost,
                            _ => 0.0,
                        };

                        // A2: Confluence scoring — qty modifier only for breakout.
                        // A2：匯流評分 — 突破策略僅作為 qty 調整器。
                        let score = confluence::compute_score(
                            &self.confluence_config,
                            true,
                            ind.adx.as_ref().map(|a| a.adx),
                            ind.hurst
                                .as_ref()
                                .map(|h| h.regime.as_str())
                                .unwrap_or("uncertain"),
                            ind.volume_ratio,
                            ind.rsi_14,
                            is_long,
                        );
                        let qty_pct = confluence::score_to_qty_pct(score, &self.confluence_config);
                        // confluence_as_gate=false: always trade if triple gate passed,
                        // but scale qty. qty_pct=0 only blocks if confluence_as_gate=true.
                        let effective_pct = if self.confluence_config.confluence_as_gate {
                            qty_pct
                        } else {
                            qty_pct.max(0.10) // minimum 10% qty for breakout
                        };
                        let qty = self.default_qty * effective_pct;
                        if qty * ctx.price < self.min_notional_usd {
                            return intents;
                        }

                        let raw_conf = (self.entry_conf_base + hurst_boost).min(1.0);
                        // EDGE-P3-1 A6: plumb decision-time confluence + persistence
                        // onto the intent for the predictor gate feature vector.
                        // EDGE-P3-1 A6：把決策時的 confluence/persistence 寫入 intent。
                        let confluence_score = score.map(|s| s as f32);
                        let persistence_elapsed_ms =
                            self.persistence.elapsed_ms(sym, ctx.timestamp_ms);
                        intents.push(StrategyAction::Open(OrderIntent {
                            symbol: ctx.symbol.to_string(),
                            is_long,
                            qty,
                            confidence: crate::tick_pipeline::on_tick_helpers::clamp_confidence(
                                raw_conf * self.conf_scale,
                            ),
                            strategy: self.name().into(),
                            order_type: "market".into(),
                            limit_price: None,
                            confluence_score,
                            persistence_elapsed_ms,
                        }));
                        // Commit per-symbol state in a single get_or_init call
                        // to avoid four separate HashMap lookups.
                        // 單次 get_or_init 寫入所有欄位，避免多次查找。
                        let st = self.symbols.get_or_init(sym);
                        st.position = Some(is_long);
                        st.squeeze_detected_ms = None;
                        self.cooldown.record_signal(sym, ctx.timestamp_ms);
                        // V2: Record entry price and initialize trailing stop per-symbol
                        st.entry_price = Some(ctx.price);
                        if let Some(atr_res) = &ind.atr_14 {
                            let dist = atr_res.atr * self.trailing_stop_atr_mult;
                            let stop = if is_long {
                                ctx.price - dist
                            } else {
                                ctx.price + dist
                            };
                            st.trailing_stop = Some(stop);
                        }
                    }
                }
            }
            Some(is_long) => {
                let mut exit_reason: Option<&str> = None;
                // QC-H4: exit_conf_base configurable (was hardcoded 0.5)
                let mut exit_confidence = self.exit_conf_base;

                // V2: ATR trailing stop — Chandelier exit, 2×ATR from peak.
                // V2：ATR 追蹤止損 — Chandelier 出場，峰值 2×ATR。
                if let Some(atr_res) = &ind.atr_14 {
                    let stop_distance = atr_res.atr * self.trailing_stop_atr_mult;
                    // Note: ratchet-only update (long = monotonically increasing stop,
                    // short = monotonically decreasing stop); preserved bit-exact.
                    // 備註：止損單向棘輪（多頭只升、空頭只降），保持 bit-exact 行為。
                    let st = self.symbols.get_or_init(sym);
                    let cur_stop = st.trailing_stop;
                    // E5-P2-4: trailing-stop bonus now config-driven (was 0.2).
                    // E5-P2-4：追蹤止損加成改由 config 控制（原 0.2）。
                    if is_long {
                        let new_stop = ctx.price - stop_distance;
                        if cur_stop.is_none() || new_stop > cur_stop.unwrap() {
                            st.trailing_stop = Some(new_stop);
                        }
                        if ctx.price <= st.trailing_stop.unwrap_or(0.0) {
                            exit_reason = Some("trailing_stop");
                            exit_confidence = self.exit_conf_base + self.exit_bonus_trailing_stop;
                        }
                    } else {
                        let new_stop = ctx.price + stop_distance;
                        if cur_stop.is_none() || new_stop < cur_stop.unwrap() {
                            st.trailing_stop = Some(new_stop);
                        }
                        if ctx.price >= st.trailing_stop.unwrap_or(f64::MAX) {
                            exit_reason = Some("trailing_stop");
                            exit_confidence = self.exit_conf_base + self.exit_bonus_trailing_stop;
                        }
                    }
                }

                // V2: Regime exit — Hurst drops from trending to mean_reverting/random_walk.
                // V2：Regime 出場 — Hurst 從趨勢轉為均值回歸/隨機漫步。
                // E5-P2-4: regime_shift bonus now config-driven (was 0.1).
                // E5-P2-4：regime 轉向加成改由 config 控制（原 0.1）。
                if exit_reason.is_none() {
                    if let Some(h) = &ind.hurst {
                        if h.regime == "mean_reverting" || h.regime == "random_walk" {
                            exit_reason = Some("regime_shift");
                            exit_confidence = self.exit_conf_base + self.exit_bonus_regime_shift;
                        }
                    }
                }

                // %B revert to mid: failed breakout — price returned to BB middle.
                // %B 回中軌：突破失敗 — 價格回到 BB 中間。
                // E5-P2-4: pctb_revert bonus / bw_squeeze penalty now config-driven
                // (was 0.05 / -0.05 hard-coded).
                // E5-P2-4：%B 回中軌加成與帶寬再壓縮扣減改由 config 控制（原 0.05 / -0.05）。
                if exit_reason.is_none() {
                    if bb.percent_b >= 0.2 && bb.percent_b <= 0.8 {
                        exit_reason = Some("pctb_revert");
                        exit_confidence = self.exit_conf_base + self.exit_bonus_pctb_revert;
                    } else if bb.bandwidth < self.squeeze_bw {
                        // BW squeeze: volatility collapsed / 帶寬壓縮：波動塌陷
                        exit_reason = Some("bw_squeeze");
                        exit_confidence = self.exit_conf_base - self.exit_penalty_bw_squeeze;
                    }
                }

                if let Some(reason) = exit_reason {
                    intents.push(StrategyAction::Close {
                        symbol: ctx.symbol.to_string(),
                        confidence: crate::tick_pipeline::on_tick_helpers::clamp_confidence(
                            exit_confidence * self.conf_scale,
                        ),
                        reason: reason.into(),
                    });
                    // V2: Reset per-symbol trailing stop state on exit; squeeze
                    // tracking is preserved (same semantics as pre-refactor).
                    // V2：出場時重置 position/entry_price/trailing_stop，squeeze 追蹤保留。
                    if let Some(st) = self.symbols.get_mut(sym) {
                        st.position = None;
                        st.entry_price = None;
                        st.trailing_stop = None;
                    }
                    self.cooldown.record_signal(sym, ctx.timestamp_ms);
                }
            }
        }
        intents
    }

    fn update_params_json(&mut self, json: &str) -> Result<(), String> {
        let p: BbBreakoutParams = serde_json::from_str(json).map_err(|e| e.to_string())?;
        self.update_params(p)
    }
    fn get_params_json(&self) -> String {
        serde_json::to_string(&self.get_params()).unwrap_or_default()
    }
    fn param_ranges_json(&self) -> String {
        serde_json::to_string(&BbBreakoutParams::param_ranges()).unwrap_or_default()
    }
    fn conf_scale(&self) -> f64 {
        self.conf_scale
    }
    fn set_conf_scale(&mut self, scale: f64) {
        self.conf_scale = scale.clamp(0.0, 2.0);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use openclaw_core::indicators::{AtrResult, BollingerResult, HurstResult, IndicatorSnapshot};

    // P-08: Test helpers use Box::leak for owned indicator data (fine for tests).
    fn ctx(bw: f64, pct_b: f64, vol: f64, ts: u64) -> TickContext<'static> {
        ctx_ext(bw, pct_b, vol, ts, 50000.0, None, None)
    }

    /// Extended context builder with price, ATR, and Hurst overrides.
    /// 擴展上下文建構器，支持自訂價格、ATR、Hurst。
    fn ctx_ext(
        bw: f64,
        pct_b: f64,
        vol: f64,
        ts: u64,
        price: f64,
        atr: Option<AtrResult>,
        hurst: Option<HurstResult>,
    ) -> TickContext<'static> {
        let ind = Box::leak(Box::new(IndicatorSnapshot {
            bollinger: Some(BollingerResult {
                upper: 51000.0,
                middle: 50000.0,
                lower: 49000.0,
                bandwidth: bw,
                percent_b: pct_b,
            }),
            volume_ratio: Some(vol),
            atr_14: atr,
            hurst,
            ..Default::default()
        }));
        TickContext {
            symbol: "BTC",
            price,
            timestamp_ms: ts,
            indicators: Some(ind),
            signals: &[],
            h0_allowed: true,
            funding_rate: None,
            index_price: None,
        }
    }

    #[test]
    fn test_squeeze_then_breakout() {
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0));
        let i = s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Open(intent) => assert!(intent.is_long),
            other => panic!("expected Open, got {:?}", other),
        }
    }

    #[test]
    fn test_no_breakout_without_squeeze() {
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        assert!(s.on_tick(&ctx(0.05, 1.1, 2.0, 0)).is_empty());
    }

    #[test]
    fn test_entry_price_recorded() {
        // After entry, entry_price should be set / 入場後 entry_price 應被設置
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
        s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000)); // breakout long
        assert_eq!(s.entry_price_of("BTC"), Some(50000.0));
        assert!(s.trailing_stop_of("BTC").is_none()); // no ATR data, no trailing stop yet
    }

    #[test]
    fn test_atr_trailing_stop_long_exit() {
        // Long position: price drops below trailing stop -> exit
        // 做多倉位：價格跌破追蹤止損 -> 出場
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        let atr = || {
            Some(AtrResult {
                atr: 500.0,
                atr_percent: 0.01,
            })
        };

        // Enter long
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
        s.on_tick(&ctx_ext(0.05, 1.1, 2.0, 700_000, 50000.0, atr(), None)); // breakout
        assert_eq!(s.position_of("BTC"), Some(true));
        // trailing_stop = 50000 - 500*2 = 49000
        assert_eq!(s.trailing_stop_of("BTC"), Some(49000.0));

        // Price rises -> trailing stop ratchets up, no exit
        // 價格上漲 -> 追蹤止損上移，不出場
        let i = s.on_tick(&ctx_ext(0.05, 1.2, 2.0, 1_400_000, 52000.0, atr(), None));
        assert!(i.is_empty()); // still in trend
        assert_eq!(s.trailing_stop_of("BTC"), Some(51000.0)); // 52000 - 1000

        // Price drops to trailing stop -> exit
        // 價格跌至追蹤止損 -> 出場
        let i = s.on_tick(&ctx_ext(0.05, 0.9, 2.0, 2_100_000, 51000.0, atr(), None));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Close {
                reason, confidence, ..
            } => {
                assert_eq!(reason, "trailing_stop");
                assert!((*confidence - 0.7).abs() < 1e-9);
            }
            other => panic!("expected Close, got {:?}", other),
        }
        assert!(s.position_of("BTC").is_none());
        assert!(s.entry_price_of("BTC").is_none());
        assert!(s.trailing_stop_of("BTC").is_none());
    }

    #[test]
    fn test_atr_trailing_stop_short_exit() {
        // Short position: price rises above trailing stop -> exit
        // 做空倉位：價格漲破追蹤止損 -> 出場
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        let atr = || {
            Some(AtrResult {
                atr: 500.0,
                atr_percent: 0.01,
            })
        };

        // Enter short
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
        s.on_tick(&ctx_ext(0.05, -0.1, 2.0, 700_000, 50000.0, atr(), None)); // breakout short
        assert_eq!(s.position_of("BTC"), Some(false));
        // trailing_stop = 50000 + 500*2 = 51000
        assert_eq!(s.trailing_stop_of("BTC"), Some(51000.0));

        // Price drops -> trailing stop ratchets down
        let i = s.on_tick(&ctx_ext(0.05, -0.2, 2.0, 1_400_000, 48000.0, atr(), None));
        assert!(i.is_empty());
        assert_eq!(s.trailing_stop_of("BTC"), Some(49000.0)); // 48000 + 1000

        // Price rises to trailing stop -> exit
        let i = s.on_tick(&ctx_ext(0.05, 0.1, 2.0, 2_100_000, 49000.0, atr(), None));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Close { reason, .. } => assert_eq!(reason, "trailing_stop"),
            other => panic!("expected Close, got {:?}", other),
        }
    }

    #[test]
    fn test_regime_exit() {
        // Exit when regime changes to mean_reverting / 當 regime 變為均值回歸時出場
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        let trending = || {
            Some(HurstResult {
                hurst: 0.7,
                regime: "trending".into(),
            })
        };
        let ranging = || {
            Some(HurstResult {
                hurst: 0.4,
                regime: "mean_reverting".into(),
            })
        };

        // Enter long (with trending regime boost)
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
        let i = s.on_tick(&ctx_ext(0.05, 1.1, 2.0, 700_000, 50000.0, None, trending()));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Open(intent) => {
                assert!((intent.confidence - 0.8).abs() < 1e-9); // 0.7 + 0.1 hurst boost
            }
            other => panic!("expected Open, got {:?}", other),
        }
        assert_eq!(s.position_of("BTC"), Some(true));

        // Regime shifts to mean_reverting -> exit
        let i = s.on_tick(&ctx_ext(
            0.05,
            1.1,
            2.0,
            1_400_000,
            51000.0,
            None,
            ranging(),
        ));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Close {
                reason, confidence, ..
            } => {
                assert_eq!(reason, "regime_shift");
                assert!((*confidence - 0.6).abs() < 1e-9);
            }
            other => panic!("expected Close, got {:?}", other),
        }
        assert!(s.position_of("BTC").is_none());
    }

    #[test]
    fn test_configurable_volume_threshold() {
        // RC-03: Custom volume threshold — higher threshold blocks low-volume breakouts
        // RC-03：自訂成交量閾值 — 較高閾值阻擋低量突破
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        s.volume_threshold = 3.0; // require 3x volume instead of default 1.5x
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
                                            // vol=2.0 passes default (1.5) but fails custom (3.0)
                                            // vol=2.0 通過默認閾值(1.5)但不通過自訂閾值(3.0)
        let i = s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000));
        assert!(i.is_empty(), "volume 2.0 should not pass threshold 3.0");

        // vol=3.5 passes custom threshold / vol=3.5 通過自訂閾值
        let i = s.on_tick(&ctx(0.05, 1.1, 3.5, 700_000));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Open(intent) => assert!(intent.is_long),
            other => panic!("expected Open, got {:?}", other),
        }
    }

    #[test]
    fn test_configurable_squeeze_expansion_bw() {
        // RC-03: Custom squeeze/expansion bandwidth thresholds
        // RC-03：自訂壓縮/擴張帶寬閾值
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        s.squeeze_bw = 0.03; // wider squeeze detection / 更寬的壓縮偵測
        s.expansion_bw = 0.06; // require stronger expansion / 要求更強擴張

        // bw=0.025 triggers squeeze with custom threshold (< 0.03)
        s.on_tick(&ctx(0.025, 0.5, 1.0, 0));
        assert!(s.has_squeeze("BTC"));

        // bw=0.05 is expansion for default (> 0.04) but NOT for custom (< 0.06)
        let i = s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000));
        assert!(i.is_empty(), "bw 0.05 should not pass expansion_bw 0.06");

        // bw=0.07 passes custom expansion threshold / 通過自訂擴張閾值
        let i = s.on_tick(&ctx(0.07, 1.1, 2.0, 700_000));
        assert_eq!(i.len(), 1);
    }

    #[test]
    fn test_bb_brk_param_ranges() {
        assert!(!BbBreakoutParams::param_ranges().is_empty());
    }
    #[test]
    fn test_bb_brk_validate() {
        assert!(BbBreakoutParams::default().validate().is_ok());
        assert!(BbBreakoutParams {
            squeeze_bw: 0.05,
            expansion_bw: 0.04,
            ..Default::default()
        }
        .validate()
        .is_err());
    }
    #[test]
    fn test_bb_brk_update() {
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        assert!(s
            .update_params(BbBreakoutParams {
                trailing_stop_atr_mult: 3.0,
                ..Default::default()
            })
            .is_ok());
        assert!((s.get_params().trailing_stop_atr_mult - 3.0).abs() < 0.01);
    }

    #[test]
    fn test_pctb_revert_exit() {
        // Failed breakout: %B returns to mid-band [0.2, 0.8] → exit with pctb_revert
        // 突破失敗：%B 回到中間帶 [0.2, 0.8] → 以 pctb_revert 出場
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
                                  // Enter long (no ATR, no Hurst — only pctb/bw exits active)
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
        s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000)); // breakout long
        assert_eq!(s.position_of("BTC"), Some(true));

        // %B reverts to 0.5 (mid-band) → should trigger pctb_revert exit
        let i = s.on_tick(&ctx(0.05, 0.5, 2.0, 1_400_000));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Close {
                reason, confidence, ..
            } => {
                assert_eq!(reason, "pctb_revert");
                // 0.55 * conf_scale(1.0) = 0.55
                assert!((*confidence - 0.55).abs() < 1e-9);
            }
            other => panic!("expected Close(pctb_revert), got {:?}", other),
        }
        assert!(s.position_of("BTC").is_none());
    }

    #[test]
    fn test_bw_squeeze_exit() {
        // Volatility collapse: bandwidth drops below squeeze_bw while %B still extreme → bw_squeeze
        // 波動塌陷：帶寬低於壓縮閾值且 %B 仍在極端 → bw_squeeze
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
                                  // Enter long
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
        s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000)); // breakout long
        assert_eq!(s.position_of("BTC"), Some(true));

        // %B still extreme (1.1, outside [0.2,0.8]) but bandwidth collapsed below squeeze_bw (0.02)
        // → pctb_revert doesn't trigger, but bw_squeeze does
        let i = s.on_tick(&ctx(0.015, 1.1, 2.0, 1_400_000));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Close {
                reason, confidence, ..
            } => {
                assert_eq!(reason, "bw_squeeze");
                // 0.45 * conf_scale(1.0) = 0.45
                assert!((*confidence - 0.45).abs() < 1e-9);
            }
            other => panic!("expected Close(bw_squeeze), got {:?}", other),
        }
        assert!(s.position_of("BTC").is_none());
    }

    // ── G-SR-1 S3+S4: param_ranges + validation tests ──

    #[test]
    fn test_bbb_param_ranges_count() {
        let ranges = BbBreakoutParams::param_ranges();
        // 5 original + 11 confluence (includes confluence_as_gate) = 16
        assert_eq!(
            ranges.len(),
            16,
            "expected 16 param ranges, got {}",
            ranges.len()
        );
    }

    #[test]
    fn test_bbb_param_ranges_has_confluence_as_gate() {
        let ranges = BbBreakoutParams::param_ranges();
        let names: Vec<&str> = ranges.iter().map(|r| r.name.as_str()).collect();
        assert!(
            names.contains(&"confluence_as_gate"),
            "BBB must expose confluence_as_gate"
        );
    }

    #[test]
    fn test_bbb_param_ranges_confluence_names() {
        let ranges = BbBreakoutParams::param_ranges();
        let names: Vec<&str> = ranges.iter().map(|r| r.name.as_str()).collect();
        for expected in &[
            "weight_adx",
            "weight_regime",
            "weight_volume",
            "weight_momentum",
            "adx_floor",
            "confluence_threshold_no_trade",
            "confluence_threshold_light",
            "confluence_threshold_full",
            "confluence_as_gate",
            "min_persistence_ms",
            "min_notional_usd",
        ] {
            assert!(names.contains(expected), "missing param range: {expected}");
        }
    }

    #[test]
    fn test_bbb_validate_default_ok() {
        assert!(BbBreakoutParams::default().validate().is_ok());
    }

    #[test]
    fn test_bbb_validate_bad_weight_sum() {
        let mut p = BbBreakoutParams::default();
        p.weight_adx = 0.0; // sum = 0+20+12+8 = 40 ≠ 65
        assert!(p.validate().is_err());
    }

    #[test]
    fn test_bbb_validate_bad_threshold_order() {
        let mut p = BbBreakoutParams::default();
        p.confluence_threshold_no_trade = 60.0; // > light (45)
        assert!(p.validate().is_err());
    }

    // ── E5-P2-4: bit-exact defaults for newly config-driven magic numbers ──
    // ── E5-P2-4：新增 config 欄位的預設值需與原 hard-coded 一致（bit-exact） ──

    #[test]
    fn test_e5_p2_4_bbb_params_defaults_match_prior_hardcoded() {
        // Defaults must equal the literals previously embedded in the strategy body
        // so downstream numerical outputs are byte-identical when TOML omits them.
        // 默認值需等於原先硬編碼的字面量，以保證 TOML 未覆寫時輸出位元相等。
        let p = BbBreakoutParams::default();
        assert!(
            (p.hurst_regime_boost - 0.1).abs() < f64::EPSILON,
            "hurst_regime_boost default must be 0.1 (bit-exact)"
        );
        assert!(
            (p.exit_bonus_trailing_stop - 0.2).abs() < f64::EPSILON,
            "exit_bonus_trailing_stop default must be 0.2 (bit-exact)"
        );
        assert!(
            (p.exit_bonus_regime_shift - 0.1).abs() < f64::EPSILON,
            "exit_bonus_regime_shift default must be 0.1 (bit-exact)"
        );
        assert!(
            (p.exit_bonus_pctb_revert - 0.05).abs() < f64::EPSILON,
            "exit_bonus_pctb_revert default must be 0.05 (bit-exact)"
        );
        assert!(
            (p.exit_penalty_bw_squeeze - 0.05).abs() < f64::EPSILON,
            "exit_penalty_bw_squeeze default must be 0.05 (bit-exact)"
        );
    }

    #[test]
    fn test_e5_p2_4_runtime_new_matches_params_default() {
        // BbBreakout::new() must seed the runtime fields with the same literals
        // as BbBreakoutParams::default() — enforces a single source of truth.
        // BbBreakout::new() 初始化值需與 BbBreakoutParams::default() 同源（單一事實來源）。
        let s = BbBreakout::new();
        let d = BbBreakoutParams::default();
        assert!((s.hurst_regime_boost - d.hurst_regime_boost).abs() < f64::EPSILON);
        assert!((s.exit_bonus_trailing_stop - d.exit_bonus_trailing_stop).abs() < f64::EPSILON);
        assert!((s.exit_bonus_regime_shift - d.exit_bonus_regime_shift).abs() < f64::EPSILON);
        assert!((s.exit_bonus_pctb_revert - d.exit_bonus_pctb_revert).abs() < f64::EPSILON);
        assert!((s.exit_penalty_bw_squeeze - d.exit_penalty_bw_squeeze).abs() < f64::EPSILON);
    }

    #[test]
    fn test_e5_p2_4_update_params_hot_reloads_offsets() {
        // update_params must propagate new field values to the live runtime
        // (hot-reload contract — ConfigStore / ArcSwap compatibility).
        // update_params 需將新欄位熱重載到運行時（與 ConfigStore/ArcSwap 契約一致）。
        let mut s = BbBreakout::new();
        let mut p = BbBreakoutParams::default();
        p.hurst_regime_boost = 0.17;
        p.exit_bonus_trailing_stop = 0.25;
        p.exit_bonus_regime_shift = 0.12;
        p.exit_bonus_pctb_revert = 0.07;
        p.exit_penalty_bw_squeeze = 0.08;
        s.update_params(p.clone()).expect("valid params");
        assert!((s.hurst_regime_boost - 0.17).abs() < f64::EPSILON);
        assert!((s.exit_bonus_trailing_stop - 0.25).abs() < f64::EPSILON);
        assert!((s.exit_bonus_regime_shift - 0.12).abs() < f64::EPSILON);
        assert!((s.exit_bonus_pctb_revert - 0.07).abs() < f64::EPSILON);
        assert!((s.exit_penalty_bw_squeeze - 0.08).abs() < f64::EPSILON);
        // Round-trip get_params must expose the freshly hot-reloaded values.
        // get_params 需回吐熱重載後的新值。
        let back = s.get_params();
        assert!((back.hurst_regime_boost - 0.17).abs() < f64::EPSILON);
        assert!((back.exit_bonus_trailing_stop - 0.25).abs() < f64::EPSILON);
    }
}
