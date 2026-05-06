//! Per-strategy tunable parameter structs (TOML schema).
//! 各策略可調參數結構（TOML schema）。
//!
//! MODULE_NOTE (EN): Owns the 5 `*Params` structs (MaCrossover / BbReversion /
//!   BbBreakout / GridTrading / FundingArb) that back the per-section TOML config,
//!   plus their `Default` impls, `build_confluence_config` helpers, and the
//!   strategy-specific `default_*()` serde factories they reference. Split off
//!   from `params.rs` (cluster C4c) to keep each sibling under §九 800-line soft
//!   warn. Shared types — `ParamRange`, `StrategyParamsConfig`, the TOML loader,
//!   and the `StrategyParams` trait — remain in `params.rs`.
//! MODULE_NOTE (中): 持有 5 個 `*Params` 結構（MaCrossover / BbReversion / BbBreakout /
//!   GridTrading / FundingArb），對應各 section TOML 參數；含其 `Default` 實作、
//!   `build_confluence_config` helper 與結構專用的 `default_*()` serde 工廠。
//!   從 `params.rs` 切出（cluster C4c），讓各 sibling 落在 §九 800 行軟警告以下。
//!   共用型別（`ParamRange`、`StrategyParamsConfig`、TOML 載入器、`StrategyParams`
//!   trait）留在 `params.rs`。

use super::confluence;
use serde::{Deserialize, Serialize};

/// MaCrossover tunable parameters / MaCrossover 可調參數
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct MaCrossoverParams {
    #[serde(default = "default_true")]
    pub active: bool,
    #[serde(default = "default_ma_cooldown")]
    pub cooldown_ms: u64,
    #[serde(default = "default_adx")]
    pub adx_threshold: f64,
    #[serde(default = "default_true")]
    pub regime_filter_enabled: bool,
    #[serde(default = "default_higher_tf_alpha")]
    pub higher_tf_alpha: f64,
    #[serde(default = "default_conf_scale")]
    pub conf_scale: f64,
    /// QC-H1: Entry confidence base / 入場信心基礎值
    #[serde(default = "default_entry_conf_base_ma")]
    pub entry_conf_base: f64,
    /// QC-H1: Entry regime bonus ± / 入場市場狀態加分
    #[serde(default = "default_entry_regime_bonus")]
    pub entry_regime_bonus: f64,
    /// QC-H1: Exit confidence base / 出場信心基礎值
    #[serde(default = "default_exit_conf_base_ma")]
    pub exit_conf_base: f64,
    // ── G-SR-1 A0-c: Confluence TOML fields ──
    #[serde(default = "default_min_persistence_ms")]
    pub min_persistence_ms: u64,
    #[serde(default = "default_min_notional_usd")]
    pub min_notional_usd: f64,
    #[serde(default = "default_weight_adx_trend")]
    pub weight_adx: f64,
    #[serde(default = "default_weight_regime_trend")]
    pub weight_regime: f64,
    #[serde(default = "default_weight_volume_trend")]
    pub weight_volume: f64,
    #[serde(default = "default_weight_momentum_trend")]
    pub weight_momentum: f64,
    #[serde(default = "default_adx_floor")]
    pub adx_floor: f64,
    #[serde(default = "default_threshold_no_trade")]
    pub confluence_threshold_no_trade: f64,
    #[serde(default = "default_threshold_light")]
    pub confluence_threshold_light: f64,
    #[serde(default = "default_threshold_full")]
    pub confluence_threshold_full: f64,
    /// EDGE-P2-3 Phase 2+: emit PostOnly Limit entries (maker fee) instead of Market.
    /// EDGE-P2-3 Phase 2+：入場改發 PostOnly Limit（maker 費率）。
    #[serde(default = "default_use_maker_entry")]
    pub use_maker_entry: bool,
    /// EDGE-P2-3 Phase 2+: PostOnly limit placement offset from last_price (bps).
    #[serde(default = "default_maker_price_offset_bps")]
    pub maker_price_offset_bps: f64,
    /// EDGE-P2-3 Phase 2+: timeout (ms) for unfilled PostOnly Limit sweep.
    /// Default 45_000; runtime clamped to [15_000, 300_000].
    #[serde(default = "default_maker_limit_timeout_ms")]
    pub maker_limit_timeout_ms: u64,
    #[serde(default = "default_maker_price_buffer_ticks")]
    pub maker_price_buffer_ticks: u32,
    #[serde(default)]
    pub min_trend_snr: f64,
}

fn default_entry_conf_base_ma() -> f64 {
    0.45
}
fn default_entry_regime_bonus() -> f64 {
    0.15
}
fn default_exit_conf_base_ma() -> f64 {
    0.5
}
// G-SR-1 confluence defaults (shared) / 匯流默認值
fn default_min_persistence_ms() -> u64 {
    120_000
}
fn default_min_persistence_ms_breakout() -> u64 {
    60_000
}
fn default_min_notional_usd() -> f64 {
    10.0
}
fn default_weight_adx_trend() -> f64 {
    25.0
}
fn default_weight_regime_trend() -> f64 {
    20.0
}
fn default_weight_volume_trend() -> f64 {
    12.0
}
fn default_weight_momentum_trend() -> f64 {
    8.0
}
fn default_weight_adx_reversion() -> f64 {
    15.0
}
fn default_weight_regime_reversion() -> f64 {
    30.0
}
fn default_weight_volume_reversion() -> f64 {
    10.0
}
fn default_weight_momentum_reversion() -> f64 {
    10.0
}
fn default_adx_floor() -> f64 {
    8.0
}
fn default_threshold_no_trade() -> f64 {
    45.0
} // EDGE-P1-3: 35→45
fn default_threshold_light() -> f64 {
    52.0
} // EDGE-P1-3: 45→52
fn default_threshold_full() -> f64 {
    58.0
} // EDGE-P1-3: 55→58

impl MaCrossoverParams {
    /// Build ConfluenceConfig from TOML params (trend profile).
    /// 從 TOML 參數構建 ConfluenceConfig（趨勢配置）。
    pub fn build_confluence_config(&self) -> confluence::ConfluenceConfig {
        confluence::ConfluenceConfig {
            weight_adx: self.weight_adx,
            weight_regime: self.weight_regime,
            weight_volume: self.weight_volume,
            weight_momentum: self.weight_momentum,
            adx_floor: self.adx_floor,
            invert_adx: false,
            threshold_no_trade: self.confluence_threshold_no_trade,
            threshold_light: self.confluence_threshold_light,
            threshold_full: self.confluence_threshold_full,
            confluence_as_gate: true,
        }
    }
}

impl Default for MaCrossoverParams {
    fn default() -> Self {
        Self {
            active: true,
            cooldown_ms: 300_000,
            adx_threshold: 20.0,
            regime_filter_enabled: true,
            higher_tf_alpha: 0.003,
            conf_scale: 1.0,
            entry_conf_base: 0.45,
            entry_regime_bonus: 0.15,
            exit_conf_base: 0.5,
            min_persistence_ms: 120_000,
            min_notional_usd: 10.0,
            weight_adx: 25.0,
            weight_regime: 20.0,
            weight_volume: 12.0,
            weight_momentum: 8.0,
            adx_floor: 8.0,
            confluence_threshold_no_trade: 45.0,
            confluence_threshold_light: 52.0,
            confluence_threshold_full: 58.0,
            use_maker_entry: false,
            maker_price_offset_bps: 1.0,
            maker_limit_timeout_ms: 45_000,
            maker_price_buffer_ticks: 1,
            min_trend_snr: 0.0,
        }
    }
}

/// BbReversion tunable parameters / BbReversion 可調參數
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct BbReversionParams {
    #[serde(default = "default_true")]
    pub active: bool,
    #[serde(default = "default_bb_cooldown")]
    pub cooldown_ms: u64,
    #[serde(default)]
    pub use_limit: bool,
    #[serde(default = "default_limit_offset")]
    pub limit_offset_bps: f64,
    #[serde(default = "default_conf_scale")]
    pub conf_scale: f64,
    /// FIX-24: RSI oversold threshold (default 30) / RSI 超賣閾值
    #[serde(default = "default_rsi_oversold")]
    pub rsi_oversold: f64,
    /// FIX-24: RSI overbought threshold (default 70) / RSI 超買閾值
    #[serde(default = "default_rsi_overbought")]
    pub rsi_overbought: f64,
    /// QC-H3: Entry confidence base (default 0.6) / 入場信心基礎值
    #[serde(default = "default_entry_conf_base_bbr")]
    pub entry_conf_base: f64,
    /// QC-H3: Exit confidence base (default 0.55) / 出場信心基礎值
    #[serde(default = "default_exit_conf_base_bbr")]
    pub exit_conf_base: f64,
    /// QC-H3: Exit %B lower bound (default 0.2) / 出場 %B 下界
    #[serde(default = "default_exit_pctb_lower")]
    pub exit_pctb_lower: f64,
    /// QC-H3: Exit %B upper bound (default 0.8) / 出場 %B 上界
    #[serde(default = "default_exit_pctb_upper")]
    pub exit_pctb_upper: f64,
    /// QC-#7: Hurst regime boost for mean-reverting regime (default 0.1).
    /// QC-#7：均值回歸市場狀態信心加成。
    #[serde(default = "default_hurst_regime_boost")]
    pub hurst_regime_boost: f64,
    // ── G-SR-1 A0-c: Confluence TOML fields (reversion profile) ──
    #[serde(default = "default_min_persistence_ms")]
    pub min_persistence_ms: u64,
    #[serde(default = "default_min_notional_usd")]
    pub min_notional_usd: f64,
    #[serde(default = "default_weight_adx_reversion")]
    pub weight_adx: f64,
    #[serde(default = "default_weight_regime_reversion")]
    pub weight_regime: f64,
    #[serde(default = "default_weight_volume_reversion")]
    pub weight_volume: f64,
    #[serde(default = "default_weight_momentum_reversion")]
    pub weight_momentum: f64,
    #[serde(default = "default_adx_floor")]
    pub adx_floor: f64,
    #[serde(default = "default_true")]
    pub adx_inverted: bool,
    #[serde(default = "default_threshold_no_trade")]
    pub confluence_threshold_no_trade: f64,
    #[serde(default = "default_threshold_light")]
    pub confluence_threshold_light: f64,
    #[serde(default = "default_threshold_full")]
    pub confluence_threshold_full: f64,
}

fn default_entry_conf_base_bbr() -> f64 {
    0.6
}
fn default_exit_conf_base_bbr() -> f64 {
    0.55
}
fn default_exit_pctb_lower() -> f64 {
    0.2
}
fn default_exit_pctb_upper() -> f64 {
    0.8
}
fn default_hurst_regime_boost() -> f64 {
    0.1
}

impl BbReversionParams {
    pub fn build_confluence_config(&self) -> confluence::ConfluenceConfig {
        confluence::ConfluenceConfig {
            weight_adx: self.weight_adx,
            weight_regime: self.weight_regime,
            weight_volume: self.weight_volume,
            weight_momentum: self.weight_momentum,
            adx_floor: self.adx_floor,
            invert_adx: self.adx_inverted,
            threshold_no_trade: self.confluence_threshold_no_trade,
            threshold_light: self.confluence_threshold_light,
            threshold_full: self.confluence_threshold_full,
            confluence_as_gate: true,
        }
    }
}

impl Default for BbReversionParams {
    fn default() -> Self {
        Self {
            active: true,
            cooldown_ms: 600_000,
            use_limit: false,
            limit_offset_bps: 10.0,
            conf_scale: 1.0,
            rsi_oversold: 30.0,
            rsi_overbought: 70.0,
            entry_conf_base: 0.6,
            exit_conf_base: 0.55,
            exit_pctb_lower: 0.2,
            exit_pctb_upper: 0.8,
            hurst_regime_boost: 0.1,
            min_persistence_ms: 120_000,
            min_notional_usd: 10.0,
            weight_adx: 15.0,
            weight_regime: 30.0,
            weight_volume: 10.0,
            weight_momentum: 10.0,
            adx_floor: 8.0,
            adx_inverted: true,
            confluence_threshold_no_trade: 45.0,
            confluence_threshold_light: 52.0,
            confluence_threshold_full: 58.0,
        }
    }
}

/// BbBreakout tunable parameters / BbBreakout 可調參數
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct BbBreakoutParams {
    #[serde(default = "default_true")]
    pub active: bool,
    #[serde(default = "default_bb_cooldown")]
    pub cooldown_ms: u64,
    #[serde(default = "default_squeeze_bw")]
    pub squeeze_bw: f64,
    #[serde(default = "default_expansion_bw")]
    pub expansion_bw: f64,
    #[serde(default = "default_volume_threshold")]
    pub volume_threshold: f64,
    #[serde(default = "default_trailing_atr")]
    pub trailing_stop_atr_mult: f64,
    #[serde(default = "default_conf_scale")]
    pub conf_scale: f64,
    /// FIX-26: Squeeze state expiry (ms). Default 30 min / 壓縮狀態有效期
    #[serde(default = "default_squeeze_expiry")]
    pub squeeze_expiry_ms: u64,
    /// QC-H4: Entry confidence base (default 0.7) / 入場信心基礎值
    #[serde(default = "default_entry_conf_base_bbb")]
    pub entry_conf_base: f64,
    /// QC-H4: Exit confidence base (default 0.5). Exit reasons add offsets.
    /// QC-H4：出場信心基礎值。各出場原因加減偏移。
    #[serde(default = "default_exit_conf_base_bbb")]
    pub exit_conf_base: f64,
    // ── E5-P2-4: Hurst boost + per-reason exit confidence offsets (config-driven) ──
    // ── E5-P2-4：Hurst 加成 + 各出場原因的信心偏移（改由 config 控制） ──
    /// Hurst trending regime entry confidence boost (default 0.1).
    /// Hurst 趨勢狀態入場信心加成（默認 0.1）。
    #[serde(default = "default_bbb_hurst_regime_boost")]
    pub hurst_regime_boost: f64,
    /// Exit confidence bonus when trailing stop triggers (default 0.2).
    /// 追蹤止損觸發時的出場信心加成（默認 0.2）。
    #[serde(default = "default_bbb_exit_bonus_trailing_stop")]
    pub exit_bonus_trailing_stop: f64,
    /// Exit confidence bonus when Hurst regime shifts (default 0.1).
    /// Hurst regime 轉向時的出場信心加成（默認 0.1）。
    #[serde(default = "default_bbb_exit_bonus_regime_shift")]
    pub exit_bonus_regime_shift: f64,
    /// Exit confidence bonus when %B reverts to middle band (default 0.05).
    /// %B 回到中軌時的出場信心加成（默認 0.05）。
    #[serde(default = "default_bbb_exit_bonus_pctb_revert")]
    pub exit_bonus_pctb_revert: f64,
    /// Exit confidence penalty (magnitude) when BW re-squeezes (default 0.05).
    /// 帶寬再壓縮時的出場信心扣減幅度（默認 0.05）。
    #[serde(default = "default_bbb_exit_penalty_bw_squeeze")]
    pub exit_penalty_bw_squeeze: f64,
    // ── EDGE-P2-2: Open Interest confluence signal (experimental, default off) ──
    // ── EDGE-P2-2：OI 合流信號（實驗性,預設關） ──
    /// Master switch for OI confluence contribution. Default `false` →
    /// strategy is bit-identical to pre-EDGE-P2-2 baseline.
    /// OI 合流總開關；預設 false → 與舊基線 bit-identical。
    #[serde(default)]
    pub enable_oi_signal: bool,
    /// Rolling window (ms) for OI-delta computation. Default 60_000 (~60s).
    /// OI 差分滾動窗口（ms）；默認 60_000。
    #[serde(default = "default_bbb_oi_buffer_window_ms")]
    pub oi_buffer_window_ms: u64,
    /// ±bonus on confluence score on OI confirmation / divergence.
    /// Default 0.10; validated ≤ 0.5 in magnitude.
    /// OI 合流加成（±）；默認 0.10，validate 限制 ≤ 0.5。
    #[serde(default = "default_bbb_oi_confluence_bonus")]
    pub oi_confluence_bonus: f64,
    /// Minimum `|oi_delta_pct|` to apply the bonus — noise floor.
    /// Default 0.0 keeps pre-FUP behaviour (any non-zero delta triggers).
    /// 觸發 bonus 所需最小 `|oi_delta_pct|`（噪音地板）；預設 0.0 = pre-FUP 行為。
    #[serde(default)]
    pub oi_min_delta_pct: f64,
    // ── G-SR-1 A0-c: Confluence TOML fields (breakout profile) ──
    #[serde(default = "default_min_persistence_ms_breakout")]
    pub min_persistence_ms: u64,
    #[serde(default = "default_min_notional_usd")]
    pub min_notional_usd: f64,
    #[serde(default = "default_weight_adx_trend")]
    pub weight_adx: f64,
    #[serde(default = "default_weight_regime_trend")]
    pub weight_regime: f64,
    #[serde(default = "default_weight_volume_trend")]
    pub weight_volume: f64,
    #[serde(default = "default_weight_momentum_trend")]
    pub weight_momentum: f64,
    #[serde(default = "default_adx_floor")]
    pub adx_floor: f64,
    /// Breakout uses confluence as qty modifier, not gate (default false).
    /// Breakout 使用 confluence 作為倉位修正器而非門檻（默認 false）。
    #[serde(default)]
    pub confluence_as_gate: bool,
    #[serde(default = "default_threshold_no_trade")]
    pub confluence_threshold_no_trade: f64,
    #[serde(default = "default_threshold_light")]
    pub confluence_threshold_light: f64,
    #[serde(default = "default_threshold_full")]
    pub confluence_threshold_full: f64,
    /// EDGE-P2-3 Phase 2+: emit PostOnly Limit entries (maker fee) instead of Market.
    /// Default `false`; per-env TOML enables.
    /// EDGE-P2-3 Phase 2+：入場改發 PostOnly Limit（maker 費率）；默認 false。
    #[serde(default = "default_use_maker_entry")]
    pub use_maker_entry: bool,
    /// EDGE-P2-3 Phase 2+: PostOnly limit placement offset from last_price (bps).
    /// EDGE-P2-3 Phase 2+：PostOnly 限價相對 last_price 的 bps 偏移。
    #[serde(default = "default_maker_price_offset_bps")]
    pub maker_price_offset_bps: f64,
    /// EDGE-P2-3 Phase 2+: timeout (ms) for unfilled PostOnly Limit sweep.
    /// Default 45_000; runtime clamped to [15_000, 300_000].
    /// EDGE-P2-3 Phase 2+：PostOnly 掛單逾時毫秒；運行時 clamp [15_000, 300_000]。
    #[serde(default = "default_maker_limit_timeout_ms")]
    pub maker_limit_timeout_ms: u64,
    #[serde(default = "default_maker_price_buffer_ticks")]
    pub maker_price_buffer_ticks: u32,
}

fn default_entry_conf_base_bbb() -> f64 {
    0.7
}
fn default_exit_conf_base_bbb() -> f64 {
    0.5
}

// E5-P2-4: BB Breakout config-driven confidence offsets (extracted from code magic numbers).
// E5-P2-4：BB Breakout config 驅動的信心偏移（從 code 裡的魔術數字提升為 config）。
fn default_bbb_hurst_regime_boost() -> f64 {
    0.1
}
fn default_bbb_exit_bonus_trailing_stop() -> f64 {
    0.2
}
fn default_bbb_exit_bonus_regime_shift() -> f64 {
    0.1
}
fn default_bbb_exit_bonus_pctb_revert() -> f64 {
    0.05
}
fn default_bbb_exit_penalty_bw_squeeze() -> f64 {
    0.05
}

// EDGE-P2-2: OI signal default factories (explicit so `serde(default)` hits them).
// EDGE-P2-2：OI 信號預設值工廠（顯式函數以配合 `serde(default)`）。
// Exposed to `registry.rs` (factory fallback path) — keep `pub(super)`.
// 暴露給 `registry.rs`（工廠 fallback 路徑）— 保持 `pub(super)`。
pub(super) fn default_bbb_oi_buffer_window_ms() -> u64 {
    60_000
}
pub(super) fn default_bbb_oi_confluence_bonus() -> f64 {
    0.10
}

impl BbBreakoutParams {
    /// Mirror of `bb_breakout::BbBreakoutParams::validate()` OI rules.
    /// Called from `StrategyFactory::create_with_params` because the TOML
    /// path bypasses the runtime `validate()` (E2 FUP #4).
    /// 鏡射 runtime 的 OI 校驗規則，於工廠路徑手動呼叫（TOML 直達不走 runtime validate）。
    pub fn validate_oi(&self) -> Result<(), String> {
        if self.oi_buffer_window_ms < 1_000 || self.oi_buffer_window_ms > 600_000 {
            return Err(format!(
                "oi_buffer_window_ms={} must be within [1000, 600000]",
                self.oi_buffer_window_ms
            ));
        }
        if !self.oi_confluence_bonus.is_finite() || self.oi_confluence_bonus.abs() > 0.5 {
            return Err(format!(
                "oi_confluence_bonus={} must be finite and |value| <= 0.5",
                self.oi_confluence_bonus
            ));
        }
        if !self.oi_min_delta_pct.is_finite()
            || self.oi_min_delta_pct < 0.0
            || self.oi_min_delta_pct > 0.5
        {
            return Err(format!(
                "oi_min_delta_pct={} must be finite and within [0.0, 0.5]",
                self.oi_min_delta_pct
            ));
        }
        Ok(())
    }

    /// Build ConfluenceConfig from TOML params (breakout profile: qty modifier, not gate).
    /// 從 TOML 參數構建 ConfluenceConfig（突破配置：倉位修正器,非門檻）。
    pub fn build_confluence_config(&self) -> confluence::ConfluenceConfig {
        confluence::ConfluenceConfig {
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

impl Default for BbBreakoutParams {
    fn default() -> Self {
        Self {
            active: true,
            cooldown_ms: 600_000,
            squeeze_bw: 0.02,
            expansion_bw: 0.04,
            volume_threshold: 1.5,
            trailing_stop_atr_mult: 2.0,
            conf_scale: 1.0,
            squeeze_expiry_ms: 1_800_000,
            entry_conf_base: 0.7,
            exit_conf_base: 0.5,
            // E5-P2-4: defaults match pre-extraction hard-coded values.
            // E5-P2-4：默認值與原先硬編碼數值一致。
            hurst_regime_boost: 0.1,
            exit_bonus_trailing_stop: 0.2,
            exit_bonus_regime_shift: 0.1,
            exit_bonus_pctb_revert: 0.05,
            exit_penalty_bw_squeeze: 0.05,
            // EDGE-P2-2: OI signal defaults OFF → bit-identical to baseline.
            // EDGE-P2-2：OI 信號預設 OFF → 與基線 bit-identical。
            enable_oi_signal: false,
            oi_buffer_window_ms: 60_000,
            oi_confluence_bonus: 0.10,
            oi_min_delta_pct: 0.0,
            min_persistence_ms: 60_000,
            min_notional_usd: 10.0,
            weight_adx: 25.0,
            weight_regime: 20.0,
            weight_volume: 12.0,
            weight_momentum: 8.0,
            adx_floor: 8.0,
            confluence_as_gate: false,
            confluence_threshold_no_trade: 45.0,
            confluence_threshold_light: 52.0,
            confluence_threshold_full: 58.0,
            // EDGE-P2-3 Phase 2+: conservative cold-boot defaults (root principle #6).
            // EDGE-P2-3 Phase 2+：冷啟動保守默認（根原則 #6）。
            use_maker_entry: false,
            maker_price_offset_bps: 1.0,
            maker_limit_timeout_ms: 45_000,
            maker_price_buffer_ticks: 1,
        }
    }
}

/// GridTrading tunable parameters / GridTrading 可調參數
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct GridTradingParams {
    #[serde(default = "default_true")]
    pub active: bool,
    /// E5-P2-4: Per-symbol cooldown between grid triggers (ms). Default 60_000 (= 60s).
    /// Previously unreachable from TOML — runtime value locked to the
    /// `new_adaptive_with_mode` constructor literal. Now config-driven and
    /// hot-reloadable via the factory.
    /// E5-P2-4：每 symbol 網格觸發冷卻（ms，默認 60_000 = 60 秒）。
    /// 原本無法由 TOML 觸及（運行時鎖死在 `new_adaptive_with_mode` constructor literal），
    /// 現改由 config 控制並透過工廠支援熱重載。
    #[serde(default = "default_grid_cooldown_ms")]
    pub cooldown_ms: u64,
    /// Grid count per symbol. Wired to GridTrading.grid_count via factory (RG-3 fix).
    /// 每幣種網格數量。通過工廠函數接線到 GridTrading.grid_count（RG-3 修復）。
    #[serde(default = "default_grid_levels")]
    pub grid_levels: usize,
    #[serde(default = "default_spacing_mode")]
    pub spacing_mode: String,
    #[serde(default = "default_health_check_interval")]
    pub health_check_interval: u64,
    #[serde(default = "default_max_out_of_range")]
    pub max_out_of_range: u64,
    #[serde(default = "default_conf_scale")]
    pub conf_scale: f64,
    /// QC-H7: Adaptive range ±% (default 0.10 = ±10%) / 自適應範圍
    #[serde(default = "default_adaptive_range_pct")]
    pub adaptive_range_pct: f64,
    /// QC-H8: Reject backoff ms (default 30000) / 拒絕退避時長
    #[serde(default = "default_reject_backoff_ms")]
    pub reject_backoff_ms: u64,
    /// QC-H9: OU model recalc interval in ticks (default 50) / OU 重算間隔
    #[serde(default = "default_ou_update_interval")]
    pub ou_update_interval: usize,
    // ── G-SR-1 A3: Trend-adaptive cooldown ──
    /// ADX low threshold for cooldown scaling (default 20). / ADX 冷卻縮放下閾值。
    #[serde(default = "default_adx_low_threshold")]
    pub adx_low_threshold: f64,
    /// ADX high threshold for cooldown scaling (default 50). / ADX 冷卻縮放上閾值。
    #[serde(default = "default_adx_high_threshold")]
    pub adx_high_threshold: f64,
    /// Max cooldown boost factor (default 5.0, range 1x–6x). / 最大冷卻倍率加成。
    #[serde(default = "default_max_cooldown_boost")]
    pub max_cooldown_boost: f64,
    /// EDGE-P2-3 Phase 1a: emit PostOnly Limit entries (maker fee) instead of Market.
    /// Default `false` (conservative). Per-env TOML enables.
    /// EDGE-P2-3 Phase 1a：入場改發 PostOnly Limit（maker 費率）；默認 false，由各環境 TOML 啟用。
    #[serde(default = "default_use_maker_entry")]
    pub use_maker_entry: bool,
    /// EDGE-P2-3 Phase 1a: PostOnly limit placement offset from last_price in bps.
    /// EDGE-P2-3 Phase 1a：PostOnly 限價相對 last_price 的 bps 偏移。
    #[serde(default = "default_maker_price_offset_bps")]
    pub maker_price_offset_bps: f64,
    /// EDGE-P2-3 Phase 1B-3: timeout (ms) after which an unfilled PostOnly
    /// Limit entry should be swept (cancel-by-link-id + rebuild). Default
    /// 45_000 ms (45s). Clamped at runtime to [15_000, 300_000].
    /// EDGE-P2-3 Phase 1B-3：未成交 PostOnly Limit 入場的清理逾時(毫秒)。
    /// 默認 45_000 ms；運行時 clamp 到 [15_000, 300_000]。
    #[serde(default = "default_maker_limit_timeout_ms")]
    pub maker_limit_timeout_ms: u64,
    #[serde(default = "default_maker_price_buffer_ticks")]
    pub maker_price_buffer_ticks: u32,
    #[serde(default = "default_grid_reject_cooldown_ms")]
    pub reject_cooldown_ms: u64,
    #[serde(default)]
    pub blocked_symbols: Vec<String>,
    #[serde(default)]
    pub min_grid_step_bps: f64,
    #[serde(default = "default_grid_cost_floor_multiplier")]
    pub cost_floor_multiplier: f64,
    #[serde(default = "default_grid_churn_breaker_enabled")]
    pub churn_breaker_enabled: bool,
    #[serde(default = "default_grid_churn_breaker_window_ms")]
    pub churn_breaker_window_ms: u64,
    #[serde(default = "default_grid_churn_breaker_close_count")]
    pub churn_breaker_close_count: usize,
    #[serde(default = "default_grid_churn_breaker_cooldown_ms")]
    pub churn_breaker_cooldown_ms: u64,
}

fn default_adaptive_range_pct() -> f64 {
    0.10
}
fn default_reject_backoff_ms() -> u64 {
    30_000
}
fn default_ou_update_interval() -> usize {
    50
}
fn default_adx_low_threshold() -> f64 {
    20.0
}
fn default_adx_high_threshold() -> f64 {
    50.0
}
fn default_max_cooldown_boost() -> f64 {
    5.0
}
fn default_use_maker_entry() -> bool {
    false
}
fn default_maker_price_offset_bps() -> f64 {
    1.0
}
fn default_maker_limit_timeout_ms() -> u64 {
    45_000
}
fn default_maker_price_buffer_ticks() -> u32 {
    1
}
fn default_grid_reject_cooldown_ms() -> u64 {
    60_000
}
fn default_grid_cost_floor_multiplier() -> f64 {
    1.0
}
fn default_grid_churn_breaker_enabled() -> bool {
    true
}
fn default_grid_churn_breaker_window_ms() -> u64 {
    3_600_000
}
fn default_grid_churn_breaker_close_count() -> usize {
    3
}
fn default_grid_churn_breaker_cooldown_ms() -> u64 {
    21_600_000
}

impl Default for GridTradingParams {
    fn default() -> Self {
        Self {
            active: true,
            // E5-P2-4: matches new_adaptive_with_mode constructor literal.
            // E5-P2-4：與 new_adaptive_with_mode constructor literal 一致。
            cooldown_ms: 60_000,
            grid_levels: 10,
            spacing_mode: "linear".into(),
            health_check_interval: 200,
            max_out_of_range: 50,
            conf_scale: 1.0,
            adaptive_range_pct: 0.10,
            reject_backoff_ms: 30_000,
            ou_update_interval: 50,
            adx_low_threshold: 20.0,
            adx_high_threshold: 50.0,
            max_cooldown_boost: 5.0,
            use_maker_entry: false,
            maker_price_offset_bps: 1.0,
            maker_limit_timeout_ms: 45_000,
            maker_price_buffer_ticks: 1,
            reject_cooldown_ms: 60_000,
            blocked_symbols: Vec::new(),
            min_grid_step_bps: 0.0,
            cost_floor_multiplier: 1.0,
            churn_breaker_enabled: true,
            churn_breaker_window_ms: 3_600_000,
            churn_breaker_close_count: 3,
            churn_breaker_cooldown_ms: 21_600_000,
        }
    }
}

/// FundingArb tunable parameters / FundingArb 可調參數
/// OC-5: Funding rate capture via TickContext.funding_rate + index_price.
/// OC-5：通過 TickContext.funding_rate + index_price 進行資金費率捕獲。
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct FundingArbParams {
    /// Default false: set active=true in TOML when ready to trade.
    /// 預設 false：在 TOML 中設定 active=true 以啟用交易。
    #[serde(default)]
    pub active: bool,
    #[serde(default = "default_funding_cooldown")]
    pub cooldown_ms: u64,
    /// QC-H10: Total round-trip cost in BPS (perp+spot+slippage). Default 34.
    /// QC-H10：往返總成本（基點，永續+現貨+滑點）。默認 34。
    #[serde(default = "default_fa_total_cost_bps")]
    pub total_cost_bps: f64,
    /// QC-H10: Expected funding periods for cost amortization. Default 3.
    /// QC-H10：成本攤銷用的預期資金費率週期。默認 3。
    #[serde(default = "default_fa_expected_periods")]
    pub expected_periods: f64,
    /// QC-H10: Minimum |funding_rate| to enter (default 5 bps = 0.0005).
    /// QC-H10：入場最低 |資金費率|（默認 5 bps = 0.0005）。
    #[serde(default = "default_fa_funding_threshold")]
    pub funding_threshold: f64,
    /// QC-H10: Max basis risk % to hold (default 0.5%).
    /// QC-H10：最大基差風險百分比（默認 0.5%）。
    #[serde(default = "default_fa_max_basis_pct")]
    pub max_basis_pct: f64,
    /// QC-H10: Max hold time in ms (default 72h).
    /// QC-H10：最大持有時間（毫秒，默認 72 小時）。
    #[serde(default = "default_fa_max_hold_ms")]
    pub max_hold_ms: u64,
    /// Entry basis = max_basis_pct * entry_basis_ratio; hysteresis buffer (default 0.8).
    /// 入場基差 = max_basis_pct * entry_basis_ratio；遲滯緩衝（默認 0.8）。
    #[serde(default = "default_fa_entry_basis_ratio")]
    pub entry_basis_ratio: f64,
}

fn default_fa_total_cost_bps() -> f64 {
    34.0
}
fn default_fa_expected_periods() -> f64 {
    3.0
}
fn default_fa_funding_threshold() -> f64 {
    0.0005
}
fn default_fa_max_basis_pct() -> f64 {
    0.5
}
fn default_fa_max_hold_ms() -> u64 {
    72 * 3_600_000
}
fn default_fa_entry_basis_ratio() -> f64 {
    0.8
}

impl Default for FundingArbParams {
    fn default() -> Self {
        Self {
            active: false,
            cooldown_ms: 3_600_000,
            total_cost_bps: 34.0,
            expected_periods: 3.0,
            funding_threshold: 0.0005,
            max_basis_pct: 0.5,
            max_hold_ms: 72 * 3_600_000,
            entry_basis_ratio: 0.8,
        }
    }
}

// Serde default helpers / Serde 默認值輔助函數
fn default_true() -> bool {
    true
}
fn default_ma_cooldown() -> u64 {
    300_000
}
fn default_bb_cooldown() -> u64 {
    600_000
}
fn default_adx() -> f64 {
    20.0
}
fn default_higher_tf_alpha() -> f64 {
    0.003
}
fn default_conf_scale() -> f64 {
    1.0
}
fn default_squeeze_bw() -> f64 {
    0.02
}
fn default_expansion_bw() -> f64 {
    0.04
}
fn default_volume_threshold() -> f64 {
    1.5
}
fn default_trailing_atr() -> f64 {
    2.0
}
fn default_squeeze_expiry() -> u64 {
    1_800_000
}
fn default_limit_offset() -> f64 {
    10.0
}
fn default_rsi_oversold() -> f64 {
    30.0
}
fn default_rsi_overbought() -> f64 {
    70.0
}
fn default_funding_cooldown() -> u64 {
    3_600_000
}
fn default_grid_levels() -> usize {
    10
}
fn default_spacing_mode() -> String {
    "linear".into()
}
fn default_health_check_interval() -> u64 {
    200
}
fn default_max_out_of_range() -> u64 {
    50
}
// E5-P2-4: GridTrading cooldown_ms default — matches `new_adaptive_with_mode`
// constructor literal to preserve bit-exact behaviour when TOML omits the field.
// E5-P2-4：GridTrading cooldown_ms 默認值與 `new_adaptive_with_mode` constructor
// literal 一致，確保 TOML 未指定時行為 bit-exact。
fn default_grid_cooldown_ms() -> u64 {
    60_000
}
