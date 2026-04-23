//! BB Breakout runtime param hot-reload + snapshot.
//! BB 突破 runtime 參數熱重載 + 回吐。
//!
//! MODULE_NOTE (EN): Inherent `impl BbBreakout` for `update_params` /
//!   `get_params`. Split from `mod.rs` so the strategy core stays ≤ 800 soft
//!   warn. Rust allows inherent impl blocks to live across files in the same
//!   module path; this file compiles into the same `BbBreakout` type.
//! MODULE_NOTE (中): 提供 `impl BbBreakout` 的 update_params / get_params 熱重載
//!   與回吐邏輯。從 `mod.rs` 拆出以保持核心 ≤ 800 soft warn；Rust 允許 inherent
//!   impl 跨檔，本檔編譯進同一個 `BbBreakout` 型別。

use super::super::StrategyParams;
use super::params::BbBreakoutParams;
use super::BbBreakout;
use tracing::info;

impl BbBreakout {
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
        // EDGE-P2-2: hot-reload OI signal knobs. Buffers are retained so a flip
        // from true→false→true doesn't lose signal continuity on next enable.
        // EDGE-P2-2：熱重載 OI 信號開關；buffer 不清空（true→false→true 切換連續性保留）。
        self.enable_oi_signal = params.enable_oi_signal;
        self.oi_buffer_window_ms = params.oi_buffer_window_ms;
        self.oi_confluence_bonus = params.oi_confluence_bonus;
        // EDGE-P2-2 FUP: hot-reload the min-delta noise floor. Retained samples
        // outside the new window are evicted lazily on the next tick.
        // EDGE-P2-2 FUP：熱重載 min_delta 噪音地板；舊樣本下次 tick 懶淘汰。
        self.oi_min_delta_pct = params.oi_min_delta_pct;
        // EDGE-P2-3 Phase 2+: hot-reload PostOnly entry toggles.
        // EDGE-P2-3 Phase 2+：熱重載 PostOnly 入場參數。
        self.use_maker_entry = params.use_maker_entry;
        self.maker_price_offset_bps = params.maker_price_offset_bps;
        // Clamp at assignment so runtime values always satisfy the invariant.
        // 於寫入時 clamp，運行時值恆在區間內。
        self.maker_limit_timeout_ms = super::super::grid_trading::clamp_maker_limit_timeout_ms(
            params.maker_limit_timeout_ms,
        );
        // P1-11 (2): hot-reload Donchian mode + score bonus. Mode flip takes
        // effect on the next tick (no stale state — evaluated fresh each tick).
        // Score bonus change propagates immediately under Score mode.
        // P1-11 (2)：熱重載 Donchian 模式 + 評分加成；模式切換下一 tick 生效（每 tick
        // fresh 評估）；Score 模式下分數改動立即生效。
        self.donchian_mode = params.donchian_mode;
        self.donchian_score_bonus = params.donchian_score_bonus;
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
            // EDGE-P2-2: echo OI signal params.
            // EDGE-P2-2：回傳 OI 信號參數。
            enable_oi_signal: self.enable_oi_signal,
            oi_buffer_window_ms: self.oi_buffer_window_ms,
            oi_confluence_bonus: self.oi_confluence_bonus,
            // EDGE-P2-2 FUP: echo min-delta threshold for Agent round-trip.
            // EDGE-P2-2 FUP：回傳 min_delta 噪音地板供 Agent 往返。
            oi_min_delta_pct: self.oi_min_delta_pct,
            // EDGE-P2-3 Phase 2+: PostOnly maker entry fields round-trip.
            // EDGE-P2-3 Phase 2+：PostOnly maker 入場欄位往返。
            use_maker_entry: self.use_maker_entry,
            maker_price_offset_bps: self.maker_price_offset_bps,
            maker_limit_timeout_ms: self.maker_limit_timeout_ms,
            // P1-11 (2): echo Donchian mode + score bonus for Agent round-trip.
            // P1-11 (2)：回傳 Donchian 模式 + 評分加成供 Agent 往返。
            donchian_mode: self.donchian_mode,
            donchian_score_bonus: self.donchian_score_bonus,
        }
    }
}
