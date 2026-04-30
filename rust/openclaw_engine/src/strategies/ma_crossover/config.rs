//! MaCrossover impl — parameter update / getter wiring.
//! MaCrossover impl — 參數更新 / 取用器接線。
//!
//! MODULE_NOTE (EN): Split out of `strategies/ma_crossover.rs` by E5-P2-4c
//!   (2026-04-23) to honour CLAUDE.md §九 1200-line hard cap. Contains the
//!   `update_params` / `get_params` helpers that bridge `MaCrossoverParams` ↔
//!   struct fields (trait adapter methods `update_params_json` /
//!   `get_params_json` / `param_ranges_json` live in `strategy_impl.rs`).
//! MODULE_NOTE (中)：E5-P2-4c（2026-04-23）由 `strategies/ma_crossover.rs` 拆出，
//!   依 §九 1200 行硬上限。本檔含 `update_params` / `get_params`
//!   將 `MaCrossoverParams` 橋接到 struct 欄位；trait 層 JSON 適配器
//!   （`update_params_json` / `get_params_json` / `param_ranges_json`）見
//!   `strategy_impl.rs`。

use tracing::info;

use crate::strategies::StrategyParams;

use super::{MaCrossover, MaCrossoverParams};

impl MaCrossover {
    /// Phase 3a: Update tunable parameters (does not reset state).
    /// Phase 3a：更新可調參數（不重置狀態）。
    pub fn update_params(&mut self, params: MaCrossoverParams) -> Result<(), String> {
        params.validate()?;
        self.cooldown_ms = params.cooldown_ms;
        // E1-P0-2: Keep TrendCooldown's base duration in sync. The per-tick
        // `set_duration(effective)` call will overwrite this with the trend-
        // adjusted value, but holding the base in the struct preserves the
        // old invariant where `cooldown_ms` is the authoritative baseline.
        // E1-P0-2：TrendCooldown 基礎值同步；每 tick 仍會用有效值覆蓋。
        self.cooldown.set_duration(params.cooldown_ms);
        self.adx_threshold = params.adx_threshold;
        self.default_qty = params.default_qty;
        self.regime_filter_enabled = params.regime_filter_enabled;
        self.higher_tf_alpha = params.higher_tf_alpha;
        // R4-7: Rebuild ConfluenceConfig from updated params (cheap struct copy).
        // R4-7：從更新的參數重建 ConfluenceConfig（廉價結構體拷貝）。
        self.confluence_config = params.build_confluence_config();
        self.min_persistence_ms = params.min_persistence_ms;
        self.min_notional_usd = params.min_notional_usd;
        self.max_cooldown_boost = params.max_cooldown_boost;
        // EDGE-P2-3 Phase 2+: hot-reload PostOnly entry toggles.
        // EDGE-P2-3 Phase 2+：熱重載 PostOnly 入場參數。
        self.use_maker_entry = params.use_maker_entry;
        self.maker_price_offset_bps = params.maker_price_offset_bps;
        // Clamp at assignment so runtime values satisfy invariant.
        // 於寫入時 clamp，運行時值恆在區間內。
        self.maker_limit_timeout_ms = crate::strategies::grid_trading::clamp_maker_limit_timeout_ms(
            params.maker_limit_timeout_ms,
        );
        // G7-09c Phase 1: hot-reload BBO buffer (validate() bounds [0, 10]).
        // G7-09c Phase 1：熱重載 BBO buffer（validate 範圍 [0, 10]）。
        self.maker_price_buffer_ticks = params.maker_price_buffer_ticks;
        self.min_trend_snr = params.min_trend_snr;
        info!(strategy = "ma_crossover", "params updated / 參數已更新");
        Ok(())
    }

    /// Phase 3a: Get current tunable parameters.
    /// Phase 3a：獲取當前可調參數。
    pub fn get_params(&self) -> MaCrossoverParams {
        MaCrossoverParams {
            cooldown_ms: self.cooldown_ms,
            adx_threshold: self.adx_threshold,
            default_qty: self.default_qty,
            regime_filter_enabled: self.regime_filter_enabled,
            higher_tf_alpha: self.higher_tf_alpha,
            min_persistence_ms: self.min_persistence_ms,
            min_notional_usd: self.min_notional_usd,
            weight_adx: self.confluence_config.weight_adx,
            weight_regime: self.confluence_config.weight_regime,
            weight_volume: self.confluence_config.weight_volume,
            weight_momentum: self.confluence_config.weight_momentum,
            adx_floor: self.confluence_config.adx_floor,
            confluence_threshold_no_trade: self.confluence_config.threshold_no_trade,
            confluence_threshold_light: self.confluence_config.threshold_light,
            confluence_threshold_full: self.confluence_config.threshold_full,
            max_cooldown_boost: self.max_cooldown_boost,
            use_maker_entry: self.use_maker_entry,
            maker_price_offset_bps: self.maker_price_offset_bps,
            maker_limit_timeout_ms: self.maker_limit_timeout_ms,
            // G7-09c Phase 1: round-trip BBO buffer for IPC consumers.
            // G7-09c Phase 1：BBO buffer 經 IPC 來回。
            maker_price_buffer_ticks: self.maker_price_buffer_ticks,
            min_trend_snr: self.min_trend_snr,
        }
    }
}
