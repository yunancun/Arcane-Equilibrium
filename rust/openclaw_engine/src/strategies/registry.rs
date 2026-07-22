//! Strategy factory — single registration point for all 5 trading strategies.
//! 策略工廠 — 所有 5 個交易策略的唯一註冊點。
//!
//! MODULE_NOTE (EN): Owns `StrategyFactory`, the single place where concrete strategy
//!   instances are constructed. `create_all()` uses defaults; `create_for_engine(kind)`
//!   loads TOML via `load_strategy_params()`; `create_with_params(&cfg)` is the
//!   direct-injection path used by tests. Extracted from `strategies/mod.rs`
//!   (cluster C4c) so the parent module fits §九 2000-line hard cap. Zero logic /
//!   signature changes — every wiring statement is a verbatim move.
//! MODULE_NOTE (中): 持有 `StrategyFactory`，為所有策略實例的唯一建構點。
//!   `create_all()` 使用默認值；`create_for_engine(kind)` 經 `load_strategy_params()`
//!   讀取 TOML；`create_with_params(&cfg)` 為測試用直注參數路徑。
//!   從 `strategies/mod.rs` 抽出（cluster C4c），讓父模組符合 §九 2000 行硬上限；
//!   零邏輯/簽名變更，每行接線均逐字搬移。

use super::params::{
    default_bbb_oi_buffer_window_ms, default_bbb_oi_confluence_bonus, load_strategy_params,
    StrategyParams, StrategyParamsConfig,
};
use super::Strategy;
use super::{
    bb_breakout, bb_reversion, flash_dip_buy, funding_arb, funding_harvest, funding_short_v2,
    grid_helpers, grid_trading, liquidation_cascade_fade, ma_crossover,
};
use crate::config::risk_config::CloseMakerBackoffConfig;
use crate::tick_pipeline::PipelineKind;

/// FLASH-DIP-PILOT 啟用 env flag。fail-closed：unset / 非 "1" → 永不註冊。
/// 三合一 gate：env flag set AND TOML active=true AND kind == Demo。
pub const FLASH_DIP_PILOT_ENABLED_ENV: &str = "OPENCLAW_FLASH_DIP_PILOT_ENABLED";

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
    ///
    /// OOS-9 wiring：`close_maker` 為 operator 的 RiskConfig `[close_maker_backoff]`
    /// 段（由 caller 從已載入的 `risk_store` snapshot 取，見 bootstrap）。傳
    /// `Some(cfg)` 令 grid 的 close-maker 退避 runtime state 用 operator TOML 值；
    /// `None`（隔離場景 / 無 risk_store）→ grid 保留 default（bit-identical）。
    /// 為何值由 caller 傳入而非此處重讀磁碟：避免第二個 RiskConfig 讀取源，值
    /// 與熱重載 `risk_store` 首快照同源（close-maker state 不熱重載，啟動一次凍結）。
    pub fn create_for_engine(
        kind: PipelineKind,
        close_maker: Option<&CloseMakerBackoffConfig>,
    ) -> Vec<Box<dyn Strategy>> {
        let params = load_strategy_params(kind);
        let mut strategies = Self::create_with_params_and_close_maker(&params, close_maker);

        // ── FLASH-DIP-PILOT kind-aware demo-gate（CC 條件 4 / E3 MED-1）──
        // 為什麼 gate 落 create_for_engine（kind-aware）而非 create_with_params
        // （kind-blind，亦被 create_all / replay_runner 用）：pilot 結構性只能在
        // Demo pipeline 出現；Paper / Live factory 路徑永不建構此策略，使 Live
        // 5-gate 零修改即排除（IPC set_strategy_active("flash_dip_buy") 在 Live 回
        // "strategy not found"）。
        // 三合一 fail-closed gate：(a) env flag set AND (b) TOML active=true AND
        // (c) kind == Demo。任一不滿足 → 不註冊（flag-OFF 預設）。
        let flag_on = std::env::var(FLASH_DIP_PILOT_ENABLED_ENV).as_deref() == Ok("1");
        if kind == PipelineKind::Demo && flag_on && params.flash_dip_buy.active {
            // TOML validate（fail-closed：壞參數不註冊，不污染 pilot）。
            match params.flash_dip_buy.validate() {
                Ok(()) => {
                    let mut fdb = flash_dip_buy::FlashDipBuy::new();
                    fdb.k_dip = params.flash_dip_buy.k_dip;
                    fdb.hold_days = params.flash_dip_buy.hold_days;
                    fdb.max_concurrent = params.flash_dip_buy.max_concurrent;
                    fdb.notional_frac = params.flash_dip_buy.notional_frac;
                    fdb.allowed_symbols = params.flash_dip_buy.allowed_symbols.clone();
                    fdb.set_active(true);
                    strategies.push(Box::new(fdb));
                    tracing::info!(
                        strategy = "flash_dip_buy",
                        kind = %kind,
                        "FLASH-DIP-PILOT registered (Demo + flag + active) / 已註冊（demo-only pilot）"
                    );
                }
                Err(e) => tracing::warn!(
                    strategy = "flash_dip_buy",
                    error = %e,
                    "FLASH-DIP-PILOT params invalid — NOT registered (fail-closed) / 參數非法，不註冊"
                ),
            }
        }

        strategies
    }

    /// Create strategies with explicit params (for testing / direct config).
    /// 使用明確參數創建策略（用於測試 / 直接配置）。
    ///
    /// close-maker 退避 state 用 default（bit-identical）。operator 的
    /// RiskConfig `[close_maker_backoff]` 只在 `create_for_engine` 的 production
    /// 路徑注入；此 kind-blind 直注參數路徑（測試 / replay / create_all）刻意保留
    /// default，避免依賴磁碟 RiskConfig。
    pub fn create_with_params(p: &StrategyParamsConfig) -> Vec<Box<dyn Strategy>> {
        Self::create_with_params_and_close_maker(p, None)
    }

    /// OOS-9 wiring：與 `create_with_params` 同，但額外注入 operator 的
    /// close-maker 退避 config 到 grid_trading。`close_maker = None` 時 grid 保留
    /// default（bit-identical）；`Some(cfg)` 時 grid `close_maker_backoff` runtime
    /// state 改用 TOML `[close_maker_backoff]` 值。
    ///
    /// 為什麼此參數是 grid-only：目前僅 grid_trading 持有 `CloseMakerBackoffState`
    /// runtime state（close-maker TooManyPending 動態退避）；其餘策略不消費此段。
    fn create_with_params_and_close_maker(
        p: &StrategyParamsConfig,
        close_maker: Option<&CloseMakerBackoffConfig>,
    ) -> Vec<Box<dyn Strategy>> {
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
        mac.maker_price_buffer_ticks = p.ma_crossover.maker_price_buffer_ticks.min(10);
        mac.min_trend_snr = if p.ma_crossover.min_trend_snr.is_finite() {
            p.ma_crossover.min_trend_snr.clamp(0.0, 10.0)
        } else {
            0.0
        };
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
        bbb.signal_timeframe = match p.bb_breakout.validate_signal_timeframe() {
            Ok(()) => p.bb_breakout.signal_timeframe.clone(),
            Err(e) => {
                tracing::warn!(
                    strategy = "bb_breakout",
                    error = %e,
                    "BbBreakoutParams signal_timeframe failed validation, falling back to 1m"
                );
                "1m".to_string()
            }
        };
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
        bbb.maker_price_buffer_ticks = p.bb_breakout.maker_price_buffer_ticks.min(10);
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
        gt.maker_price_buffer_ticks = p.grid_trading.maker_price_buffer_ticks.min(10);
        gt.reject_cooldown_ms = p.grid_trading.reject_cooldown_ms.clamp(5_000, 600_000);
        gt.blocked_symbols = p
            .grid_trading
            .blocked_symbols
            .iter()
            .map(|s| s.trim().to_ascii_uppercase())
            .filter(|s| !s.is_empty())
            .collect();
        gt.min_grid_step_bps = if p.grid_trading.min_grid_step_bps.is_finite() {
            p.grid_trading.min_grid_step_bps.clamp(0.0, 200.0)
        } else {
            0.0
        };
        gt.cost_floor_multiplier = if p.grid_trading.cost_floor_multiplier.is_finite() {
            p.grid_trading.cost_floor_multiplier.clamp(1.0, 5.0)
        } else {
            1.0
        };
        gt.churn_breaker_enabled = p.grid_trading.churn_breaker_enabled;
        gt.churn_breaker_window_ms = p
            .grid_trading
            .churn_breaker_window_ms
            .clamp(60_000, 86_400_000);
        gt.churn_breaker_close_count = p.grid_trading.churn_breaker_close_count.clamp(2, 20);
        gt.churn_breaker_cooldown_ms = p
            .grid_trading
            .churn_breaker_cooldown_ms
            .clamp(300_000, 86_400_000);
        gt.set_conf_scale(p.grid_trading.conf_scale);
        gt.set_active(p.grid_trading.active);
        // OOS-9 wiring：注入 operator 的 RiskConfig `[close_maker_backoff]` 值，
        // 令 TOML 六常數（backoff_initial/max/reset + cascade window/symbols/pause）
        // 真流入 grid 的 close-maker 退避 runtime state。`None`（測試 / replay /
        // create_all）→ 保留 `new()` default，行為 bit-identical。
        if let Some(cfg) = close_maker {
            gt.apply_close_maker_backoff_config(cfg);
        }
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

        // C10 FundingHarvest — delta-neutral spot long + perp short matched notional。
        // Sprint 1B Pending 3.1 Stage 1 Demo strategy (BTCUSDT only, $100 cap)。
        // 與 funding_arb V2 (ADR-0018 dormant) 並列；預設 active=false，
        // Stage 0R replay preflight PASS + operator IPC active=true 才啟。
        let mut fh = funding_harvest::FundingHarvest::new();
        fh.cooldown_ms = p.funding_harvest.cooldown_ms;
        fh.allowed_symbols = p.funding_harvest.allowed_symbols.clone();
        fh.funding_threshold_annualized = p.funding_harvest.funding_threshold_annualized;
        fh.funding_exit_annualized = p.funding_harvest.funding_exit_annualized;
        fh.max_basis_pct = p.funding_harvest.max_basis_pct;
        fh.entry_basis_ratio = p.funding_harvest.entry_basis_ratio;
        fh.max_hold_ms = p.funding_harvest.max_hold_ms;
        fh.total_cost_bps = p.funding_harvest.total_cost_bps;
        fh.expected_periods = p.funding_harvest.expected_periods;
        fh.rebalance_check_ms = p.funding_harvest.rebalance_check_ms;
        fh.delta_drift_threshold = p.funding_harvest.delta_drift_threshold;
        fh.position_cap_usd = p.funding_harvest.position_cap_usd;
        fh.set_active(p.funding_harvest.active);
        strategies.push(Box::new(fh));

        // Sprint 2 Alpha Tournament Candidate #1 — FundingShortV2。
        // funding > 30% annualized + short-only hard enforcement directional capture。
        // 與 funding_arb V2 (ADR-0018 dormant) + funding_harvest (delta-neutral) 並列；
        // 不繞 V2 dormant 結論。Stage 1 Demo 限定 BTCUSDT / ETHUSDT。
        // 預設 active=false：5-gate auto path inheritance + operator IPC 顯式 true 才啟。
        let mut fsv2 = funding_short_v2::FundingShortV2::new();
        // cooldown TrendCooldown 為 sub-module private state；TOML active=true
        // 時走 update_params_json/update_params 路徑會 set_duration；初始 cooldown_ms
        // 由 new() default 已對齊 spec §3.1。
        fsv2.cooldown_ms = p.funding_short_v2.cooldown_ms;
        fsv2.allowed_symbols = p.funding_short_v2.allowed_symbols.clone();
        fsv2.funding_threshold_annualized = p.funding_short_v2.funding_threshold_annualized;
        fsv2.funding_exit_annualized = p.funding_short_v2.funding_exit_annualized;
        fsv2.max_basis_pct = p.funding_short_v2.max_basis_pct;
        fsv2.entry_basis_ratio = p.funding_short_v2.entry_basis_ratio;
        fsv2.max_hold_ms = p.funding_short_v2.max_hold_ms;
        fsv2.total_cost_bps = p.funding_short_v2.total_cost_bps;
        fsv2.expected_periods = p.funding_short_v2.expected_periods;
        fsv2.set_active(p.funding_short_v2.active);
        strategies.push(Box::new(fsv2));

        // Sprint 2 Alpha Tournament Candidate #4 — LiquidationCascadeFade。
        // 5min liquidation cluster > per-symbol threshold (BTC $500k / ETH $300k) +
        // fade against dominant cascade side mean-revert (60min hold)。
        // 依賴 surface.liquidation_pulse (W-AUDIT-8a C1 LiquidationPulseAggregator +
        // commit 0e8a8ae8 allLiquidation WS subscription)。
        // 預設 active=false：5-gate auto path inheritance + operator IPC 顯式 true 才啟。
        let mut lcf = liquidation_cascade_fade::LiquidationCascadeFade::new();
        // 同 funding_short_v2 / funding_harvest 範式：cooldown 為 private state；
        // IPC update_params 才走 set_duration；初始 cooldown_ms 由 new() default 對齊 spec。
        lcf.cooldown_ms = p.liquidation_cascade_fade.cooldown_ms;
        lcf.allowed_symbols = p.liquidation_cascade_fade.allowed_symbols.clone();
        lcf.default_threshold_usd = p.liquidation_cascade_fade.default_threshold_usd;
        // per-symbol threshold map 從 TOML 重建（BTC + ETH 兩 key；非-cohort 走 default）。
        lcf.per_symbol_threshold.clear();
        lcf.per_symbol_threshold.insert(
            "BTCUSDT".to_string(),
            p.liquidation_cascade_fade.btc_threshold_usd,
        );
        lcf.per_symbol_threshold.insert(
            "ETHUSDT".to_string(),
            p.liquidation_cascade_fade.eth_threshold_usd,
        );
        lcf.min_events = p.liquidation_cascade_fade.min_events;
        lcf.max_hold_ms = p.liquidation_cascade_fade.max_hold_ms;
        lcf.take_profit_pct = p.liquidation_cascade_fade.take_profit_pct;
        lcf.reverse_cascade_ratio = p.liquidation_cascade_fade.reverse_cascade_ratio;
        lcf.set_active(p.liquidation_cascade_fade.active);
        strategies.push(Box::new(lcf));

        strategies
    }
}
