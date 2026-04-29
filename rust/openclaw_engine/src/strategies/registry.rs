//! Strategy factory — single registration point for all 5 trading strategies.
//! 策略工廠 — 所有 5 個交易策略的唯一註冊點。
//!
//! MODULE_NOTE (EN): Owns `StrategyFactory`, the single place where concrete strategy
//!   instances are constructed. `create_all()` uses defaults; `create_for_engine(kind)`
//!   loads TOML via `load_strategy_params()`; `create_with_params(&cfg)` is the
//!   direct-injection path used by tests. Extracted from `strategies/mod.rs`
//!   (cluster C4c) so the parent module fits §九 1200-line hard cap. Zero logic /
//!   signature changes — every wiring statement is a verbatim move.
//! MODULE_NOTE (中): 持有 `StrategyFactory`，為所有策略實例的唯一建構點。
//!   `create_all()` 使用默認值；`create_for_engine(kind)` 經 `load_strategy_params()`
//!   讀取 TOML；`create_with_params(&cfg)` 為測試用直注參數路徑。
//!   從 `strategies/mod.rs` 抽出（cluster C4c），讓父模組符合 §九 1200 行硬上限；
//!   零邏輯/簽名變更，每行接線均逐字搬移。

use super::params::{
    default_bbb_oi_buffer_window_ms, default_bbb_oi_confluence_bonus, load_strategy_params,
    StrategyParamsConfig,
};
use super::Strategy;
use super::{bb_breakout, bb_reversion, funding_arb, grid_helpers, grid_trading, ma_crossover};
use crate::tick_pipeline::PipelineKind;

// ═══════════════════════════════════════════════════════════════════════════════
// 3E-9: StrategyFactory — single registration point for all strategies.
// 3E-9：策略工廠 — 所有策略的唯一註冊點。
// ═══════════════════════════════════════════════════════════════════════════════

/// Strategy factory — single registration point. Add/remove strategies here ONLY.
/// Pipeline code calls `create_all()` or `create_for_engine()` instead of hard-coding.
/// 策略工廠 — 唯一註冊點。新增/移除策略只改這裡。
/// 管線代碼調用 `create_all()` 或 `create_for_engine()` 而非硬編碼。
pub struct StrategyFactory;

impl StrategyFactory {
    /// Create all strategies with default parameters (backward compat).
    /// 以默認參數創建所有策略（向後兼容）。
    pub fn create_all() -> Vec<Box<dyn Strategy>> {
        Self::create_with_params(&StrategyParamsConfig::default())
    }

    /// Create strategies for a specific engine, loading params from TOML.
    /// 為特定引擎創建策略，從 TOML 加載參數。
    pub fn create_for_engine(kind: PipelineKind) -> Vec<Box<dyn Strategy>> {
        let params = load_strategy_params(kind);
        Self::create_with_params(&params)
    }

    /// Create strategies with explicit params (for testing / direct config).
    /// 使用明確參數創建策略（用於測試 / 直接配置）。
    pub fn create_with_params(p: &StrategyParamsConfig) -> Vec<Box<dyn Strategy>> {
        let mut strategies: Vec<Box<dyn Strategy>> = Vec::new();

        // MaCrossover
        let mut mac = ma_crossover::MaCrossover::new();
        mac.cooldown_ms = p.ma_crossover.cooldown_ms;
        mac.adx_threshold = p.ma_crossover.adx_threshold;
        mac.regime_filter_enabled = p.ma_crossover.regime_filter_enabled;
        mac.higher_tf_alpha = p.ma_crossover.higher_tf_alpha;
        mac.entry_conf_base = p.ma_crossover.entry_conf_base;
        mac.entry_regime_bonus = p.ma_crossover.entry_regime_bonus;
        mac.exit_conf_base = p.ma_crossover.exit_conf_base;
        // G-SR-1 A0-c: Wire confluence params from TOML.
        // G-SR-1 A0-c：從 TOML 接線匯流參數。
        mac.min_persistence_ms = p.ma_crossover.min_persistence_ms;
        mac.min_notional_usd = p.ma_crossover.min_notional_usd;
        mac.confluence_config = p.ma_crossover.build_confluence_config();
        // EDGE-P2-3 Phase 2+: wire maker-entry params from TOML.
        // EDGE-P2-3 Phase 2+：從 TOML 接線 PostOnly 入場參數。
        mac.use_maker_entry = p.ma_crossover.use_maker_entry;
        mac.maker_price_offset_bps = p.ma_crossover.maker_price_offset_bps;
        mac.maker_limit_timeout_ms =
            grid_trading::clamp_maker_limit_timeout_ms(p.ma_crossover.maker_limit_timeout_ms);
        mac.set_conf_scale(p.ma_crossover.conf_scale);
        mac.set_active(p.ma_crossover.active);
        strategies.push(Box::new(mac));

        // BbReversion
        let mut bbr = bb_reversion::BbReversion::new();
        bbr.cooldown_ms = p.bb_reversion.cooldown_ms;
        bbr.use_limit = p.bb_reversion.use_limit;
        bbr.limit_offset_bps = p.bb_reversion.limit_offset_bps;
        bbr.rsi_oversold = p.bb_reversion.rsi_oversold;
        bbr.rsi_overbought = p.bb_reversion.rsi_overbought;
        bbr.entry_conf_base = p.bb_reversion.entry_conf_base;
        bbr.exit_conf_base = p.bb_reversion.exit_conf_base;
        bbr.exit_pctb_lower = p.bb_reversion.exit_pctb_lower;
        bbr.exit_pctb_upper = p.bb_reversion.exit_pctb_upper;
        bbr.hurst_regime_boost = p.bb_reversion.hurst_regime_boost;
        // G-SR-1 A0-c: Wire confluence params from TOML.
        bbr.min_persistence_ms = p.bb_reversion.min_persistence_ms;
        bbr.min_notional_usd = p.bb_reversion.min_notional_usd;
        bbr.confluence_config = p.bb_reversion.build_confluence_config();
        bbr.set_conf_scale(p.bb_reversion.conf_scale);
        bbr.set_active(p.bb_reversion.active);
        strategies.push(Box::new(bbr));

        // BbBreakout
        let mut bbb = bb_breakout::BbBreakout::new();
        bbb.cooldown_ms = p.bb_breakout.cooldown_ms;
        bbb.squeeze_bw = p.bb_breakout.squeeze_bw;
        bbb.expansion_bw = p.bb_breakout.expansion_bw;
        bbb.volume_threshold = p.bb_breakout.volume_threshold;
        bbb.trailing_stop_atr_mult = p.bb_breakout.trailing_stop_atr_mult;
        bbb.squeeze_expiry_ms = p.bb_breakout.squeeze_expiry_ms;
        bbb.entry_conf_base = p.bb_breakout.entry_conf_base;
        bbb.exit_conf_base = p.bb_breakout.exit_conf_base;
        // E5-P2-4: wire new config-driven confidence offsets from TOML.
        // E5-P2-4：從 TOML 接線新增的 config 驅動信心偏移參數。
        bbb.hurst_regime_boost = p.bb_breakout.hurst_regime_boost;
        bbb.exit_bonus_trailing_stop = p.bb_breakout.exit_bonus_trailing_stop;
        bbb.exit_bonus_regime_shift = p.bb_breakout.exit_bonus_regime_shift;
        bbb.exit_bonus_pctb_revert = p.bb_breakout.exit_bonus_pctb_revert;
        bbb.exit_penalty_bw_squeeze = p.bb_breakout.exit_penalty_bw_squeeze;
        // EDGE-P2-2: wire OI signal params from TOML (hot-reloadable via ConfigStore).
        // EDGE-P2-2：從 TOML 接線 OI 信號參數（經 ConfigStore 熱重載）。
        // E2 FUP #4: TOML path bypasses runtime `validate()`. Call mirror helper so
        // malformed values in live/demo/paper TOML fall back to defaults instead of
        // silently poisoning the strategy.
        // E2 FUP #4：TOML 啟動路徑不走 runtime validate，呼叫 mirror helper；
        // 若值非法則回退到默認，避免靜默注入壞參數。
        let (oi_window, oi_bonus, oi_min_delta) = match p.bb_breakout.validate_oi() {
            Ok(()) => (
                p.bb_breakout.oi_buffer_window_ms,
                p.bb_breakout.oi_confluence_bonus,
                p.bb_breakout.oi_min_delta_pct,
            ),
            Err(e) => {
                tracing::warn!(
                    strategy = "bb_breakout",
                    error = %e,
                    "BbBreakoutParams OI fields failed validation, falling back to defaults"
                );
                (
                    default_bbb_oi_buffer_window_ms(),
                    default_bbb_oi_confluence_bonus(),
                    0.0,
                )
            }
        };
        bbb.enable_oi_signal = p.bb_breakout.enable_oi_signal;
        bbb.oi_buffer_window_ms = oi_window;
        bbb.oi_confluence_bonus = oi_bonus;
        bbb.oi_min_delta_pct = oi_min_delta;
        // G-SR-1 A0-c: Wire confluence params from TOML.
        bbb.min_persistence_ms = p.bb_breakout.min_persistence_ms;
        bbb.min_notional_usd = p.bb_breakout.min_notional_usd;
        bbb.confluence_config = p.bb_breakout.build_confluence_config();
        // EDGE-P2-3 Phase 2+: wire maker-entry params from TOML.
        // EDGE-P2-3 Phase 2+：從 TOML 接線 PostOnly 入場參數。
        bbb.use_maker_entry = p.bb_breakout.use_maker_entry;
        bbb.maker_price_offset_bps = p.bb_breakout.maker_price_offset_bps;
        // Clamp at assignment (same invariant as grid_trading).
        // 於寫入時 clamp（與 grid_trading 相同不變量）。
        bbb.maker_limit_timeout_ms =
            grid_trading::clamp_maker_limit_timeout_ms(p.bb_breakout.maker_limit_timeout_ms);
        bbb.set_conf_scale(p.bb_breakout.conf_scale);
        bbb.set_active(p.bb_breakout.active);
        strategies.push(Box::new(bbb));

        // GridTrading
        let spacing = match p.grid_trading.spacing_mode.as_str() {
            "geometric" => grid_helpers::GridSpacingMode::Geometric,
            _ => grid_helpers::GridSpacingMode::Linear,
        };
        let mut gt = grid_trading::GridTrading::new_adaptive_with_mode(spacing);
        // E5-P2-4: grid cooldown_ms now reachable from TOML (was unreachable before).
        // E5-P2-4：grid cooldown_ms 現可由 TOML 控制（原本 unreachable）。
        gt.cooldown_ms = p.grid_trading.cooldown_ms;
        gt.health_check_interval = p.grid_trading.health_check_interval as usize;
        gt.max_out_of_range = p.grid_trading.max_out_of_range as usize;
        gt.grid_count = p.grid_trading.grid_levels; // RG-3: wire TOML grid_levels → runtime grid_count
        gt.adaptive_range_pct = p.grid_trading.adaptive_range_pct;
        gt.reject_backoff_ms = p.grid_trading.reject_backoff_ms;
        gt.ou_update_interval = p.grid_trading.ou_update_interval;
        gt.adx_low_threshold = p.grid_trading.adx_low_threshold;
        gt.adx_high_threshold = p.grid_trading.adx_high_threshold;
        gt.max_cooldown_boost = p.grid_trading.max_cooldown_boost;
        // EDGE-P2-3 Phase 1a: wire maker-entry params from TOML.
        gt.use_maker_entry = p.grid_trading.use_maker_entry;
        gt.maker_price_offset_bps = p.grid_trading.maker_price_offset_bps;
        // EDGE-P2-3 Phase 1B-3.1: wire PostOnly Limit timeout (clamp [15s, 300s]).
        // EDGE-P2-3 Phase 1B-3.1：PostOnly Limit 逾時 clamp 到 [15s, 300s]。
        gt.maker_limit_timeout_ms =
            grid_trading::clamp_maker_limit_timeout_ms(p.grid_trading.maker_limit_timeout_ms);
        gt.set_conf_scale(p.grid_trading.conf_scale);
        gt.set_active(p.grid_trading.active);
        strategies.push(Box::new(gt));

        // FundingArb (OC-5: active when TOML sets active=true)
        // OC-5：TOML 設定 active=true 時啟用
        let mut fa = funding_arb::FundingArb::new();
        fa.cooldown_ms = p.funding_arb.cooldown_ms;
        fa.total_cost_bps = p.funding_arb.total_cost_bps;
        fa.expected_periods = p.funding_arb.expected_periods;
        fa.funding_threshold = p.funding_arb.funding_threshold;
        fa.max_basis_pct = p.funding_arb.max_basis_pct;
        fa.max_hold_ms = p.funding_arb.max_hold_ms;
        fa.entry_basis_ratio = p.funding_arb.entry_basis_ratio;
        fa.set_active(p.funding_arb.active);
        strategies.push(Box::new(fa));

        strategies
    }
}
