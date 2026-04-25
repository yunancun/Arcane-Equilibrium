//! MaCrossover impl — signal/intent helpers + filter primitives.
//! MaCrossover impl — 信號/intent 輔助函數 + 過濾原語。
//!
//! MODULE_NOTE (EN): Split out of `strategies/ma_crossover.rs` by E5-P2-4c
//!   (2026-04-23) to honour CLAUDE.md §九 1200-line hard cap. Contains the
//!   private helpers used by the `Strategy::on_tick` loop: `make_intent` /
//!   `make_intent_with_qty` (order emission), `regime_allows_entry` (RC-01
//!   Hurst gate), `update_higher_tf` + `higher_tf_allows_entry` (RC-02 multi-
//!   timeframe proxy), confidence builders, `compute_trend_adjusted_cooldown`
//!   (A2) and `compute_exit_persistence_ms` (A1).
//! MODULE_NOTE (中)：E5-P2-4c（2026-04-23）由 `strategies/ma_crossover.rs` 拆出。
//!   本檔含 `on_tick` 使用的私有輔助函數：`make_intent` / `make_intent_with_qty`
//!   （訂單發出）、`regime_allows_entry`（RC-01 赫斯特門）、`update_higher_tf` +
//!   `higher_tf_allows_entry`（RC-02 多時間框架代理）、信心計算、
//!   `compute_trend_adjusted_cooldown`（A2）及 `compute_exit_persistence_ms`（A1）。

use crate::intent_processor::OrderIntent;
use crate::order_manager::TimeInForce;
use crate::strategies::common::{compute_post_only_price, MakerPriceInputs};
use crate::strategies::Strategy;
use crate::tick_pipeline::TickContext;

use super::{ConfidenceBuilder, MaCrossover};

impl MaCrossover {
    pub(super) fn make_intent(
        &self,
        ctx: &TickContext<'_>,
        is_long: bool,
        conf: f64,
    ) -> OrderIntent {
        self.make_intent_with_qty(ctx, is_long, conf, self.default_qty, None, None)
    }

    /// Build intent with explicit qty (used by confluence-scaled entries).
    /// 使用顯式 qty 構建 intent（用於匯流調整後的入場）。
    ///
    /// EDGE-P3-1 A6: `confluence_score` is the raw compute_score result [0, 65]
    /// (None on cold-start fallback); `persistence_elapsed_ms` is ms since signal
    /// onset. Exits pass None/None — features are decision-time only.
    /// EDGE-P3-1 A6：confluence_score 為原始分數，persistence_elapsed_ms 為信號經時；
    /// 出場路徑傳 None。
    pub(super) fn make_intent_with_qty(
        &self,
        ctx: &TickContext<'_>,
        is_long: bool,
        conf: f64,
        qty: f64,
        confluence_score: Option<f32>,
        persistence_elapsed_ms: Option<u64>,
    ) -> OrderIntent {
        let scaled =
            crate::tick_pipeline::on_tick_helpers::clamp_confidence(conf * self.conf_scale);
        // EDGE-P2-3 Phase 2+ + G7-09c Phase 1: resolve entry order shape
        // (Market vs PostOnly Limit). G7-09c Phase 1 replaces legacy
        // `last_price ± offset_bps` (RCA `7f0e793` showed 100% PostOnly reject)
        // with strictly passive BBO-aware price; helper falls back to legacy
        // when BBO/tick_size unavailable.
        // EDGE-P2-3 Phase 2+ + G7-09c Phase 1：決定入場單型；G7-09c 以 BBO-aware
        // 嚴格被動價取代舊 `last_price ± offset_bps`，BBO 不可得時 helper fallback。
        let (order_type, limit_price, time_in_force, maker_timeout_ms) =
            if self.use_maker_entry {
                let inputs = MakerPriceInputs {
                    last_price: ctx.price,
                    best_bid: ctx.best_bid,
                    best_ask: ctx.best_ask,
                    tick_size: ctx.tick_size,
                };
                let limit = compute_post_only_price(
                    is_long,
                    inputs,
                    self.maker_price_offset_bps,
                    self.maker_price_buffer_ticks,
                    "ma_crossover",
                    ctx.symbol,
                );
                (
                    "limit".to_string(),
                    Some(limit),
                    Some(TimeInForce::PostOnly),
                    Some(self.maker_limit_timeout_ms),
                )
            } else {
                ("market".to_string(), None, None, None)
            };
        OrderIntent {
            symbol: ctx.symbol.to_string(),
            is_long,
            qty,
            confidence: scaled,
            strategy: self.name().into(),
            order_type,
            limit_price,
            confluence_score,
            persistence_elapsed_ms,
            time_in_force,
            maker_timeout_ms,
        }
    }

    /// RC-01: Check if Hurst regime allows entry (only "trending" passes).
    /// RC-01: 檢查赫斯特狀態是否允許入場（僅 "trending" 通過）。
    pub(super) fn regime_allows_entry(&self, ctx: &TickContext<'_>) -> bool {
        if !self.regime_filter_enabled {
            return true;
        }
        let ind = match ctx.indicators {
            Some(i) => i,
            None => return true,
        };
        match &ind.hurst {
            // No Hurst data — don't block (cold-start safe).
            // 無赫斯特數據 — 不阻擋（冷啟動安全）。
            None => true,
            Some(hr) => hr.regime == "trending",
        }
    }

    /// RC-02: Update higher-TF SMA and trend using EMA of sma_50.
    /// Alpha=0.003 gives half-life ~231 min ≈ 4h on 1m ticks (ln2/0.003=231).
    /// RC-02: 使用 sma_50 的 EMA 更新較高時間框架 SMA 及趨勢。
    /// Alpha=0.003 在 1 分鐘 tick 上半衰期 ~231 分鐘 ≈ 4 小時。
    pub(super) fn update_higher_tf(&mut self, symbol: &str, sma_50: f64) {
        let alpha = self.higher_tf_alpha;
        let new_val = match self.higher_tf_sma.get(symbol) {
            // First data point — initialize directly, no trend yet.
            // 第一個數據點 — 直接初始化，尚無趨勢。
            None => {
                self.higher_tf_sma.insert(symbol.to_string(), sma_50);
                self.higher_tf_trend.remove(symbol); // Need at least one update to determine trend.
                return;
            }
            Some(&prev) => alpha * sma_50 + (1.0 - alpha) * prev,
        };
        self.higher_tf_sma.insert(symbol.to_string(), new_val);
        self.higher_tf_trend
            .insert(symbol.to_string(), sma_50 > new_val);
    }

    /// Dynamic confidence: ADX excess + Hurst regime fit.
    /// 動態信心：ADX 超額 + Hurst regime 契合度。
    /// trending regime + 高 ADX → 高 conf；mean_reverting regime → 懲罰。
    ///
    /// E1-P0-2: Delegates to `ConfidenceBuilder`. Bit-exact equivalence with
    /// the pre-extraction formula is covered by
    /// `ConfidenceBuilder::tests::test_bit_exact_matches_pre_extraction_trending`
    /// (same base / adx_threshold / regime_bonus / 100.0 / 0.25 / 0.2 / 0.9).
    /// E1-P0-2：委派給 `ConfidenceBuilder`，位元精確對齊已於共享模組單測驗證。
    pub(super) fn compute_entry_confidence(&self, adx: f64, regime: Option<&str>) -> f64 {
        ConfidenceBuilder::new(self.entry_conf_base, self.adx_threshold, self.entry_regime_bonus)
            .compute(adx, regime)
    }

    /// Exit confidence: cross-back is a real signal but weaker than fresh entry.
    /// 出場信心：反向交叉是真信號但弱於新入場。
    pub(super) fn compute_exit_confidence(&self, adx: f64) -> f64 {
        // QC-H1: base configurable (was hardcoded 0.5)
        let base = self.exit_conf_base;
        let adx_bonus = ((adx - self.adx_threshold).max(0.0) / 100.0).min(0.2);
        (base + adx_bonus).clamp(0.4, 0.8)
    }

    /// A2: Trend-adaptive cooldown — in trending markets, extend cooldown to
    /// avoid re-entering too quickly after a close only to get whipsawed by the
    /// very trend that drove the reverse cross. Formula mirrors
    /// `grid_trading::compute_trend_adjusted_cooldown` but derives the ADX
    /// upper bound from the single `adx_threshold` parameter instead of
    /// carrying a separate `adx_high_threshold`.
    ///
    /// Upper bound = `adx_threshold × 2.5` (matches grid_trading's 20→50
    /// default). Hurst bound = 0.50→0.75. 60/40 ADX/Hurst blend.
    /// multiplier = 1 + trend_score × max_cooldown_boost, clamped via
    /// input bounds.
    ///
    /// A2：趨勢自適應冷卻。趨勢市場下延長冷卻，避免剛平又被同趨勢打回。
    /// 公式與 grid_trading A3 一致，但 ADX 上界由 `adx_threshold × 2.5` 推導。
    pub(super) fn compute_trend_adjusted_cooldown(
        &self,
        snap: Option<&openclaw_core::indicators::IndicatorSnapshot>,
    ) -> u64 {
        let Some(ind) = snap else {
            return self.cooldown_ms;
        };

        let adx_val = ind.adx.as_ref().map(|a| a.adx).unwrap_or(0.0);
        let hurst_val = ind.hurst.as_ref().map(|h| h.hurst).unwrap_or(0.5);

        // ADX factor: adx_threshold → adx_threshold*2.5 maps to 0 → 1.
        // `adx_threshold * 1.5` is the width (upper − lower) of that range.
        // ADX 因子：adx_threshold 到 adx_threshold*2.5 線性映射為 0 到 1。
        let adx_range = self.adx_threshold * 1.5;
        let adx_factor = if adx_range > 0.0 {
            ((adx_val - self.adx_threshold) / adx_range).clamp(0.0, 1.0)
        } else {
            0.0
        };

        // Hurst factor: 0.50 → 0.75 maps to 0 → 1.
        // Hurst 因子：0.50 到 0.75 映射為 0 到 1。
        let hurst_factor = ((hurst_val - 0.50) / 0.25).clamp(0.0, 1.0);

        // 60/40 blend — ADX reacts faster than Hurst. / 60/40 混合：ADX 反應快於 Hurst。
        let trend_score = 0.6 * adx_factor + 0.4 * hurst_factor;

        let multiplier = 1.0 + (trend_score * self.max_cooldown_boost);
        (self.cooldown_ms as f64 * multiplier) as u64
    }

    /// A1: ER-scaled exit persistence window (ms).
    /// ER→1 (clean trend) → window→0 → reverse cross exits immediately.
    /// ER→0 (choppy) → window→min_persistence_ms → near-entry-level confirmation.
    /// A1：KAMA 效率比驅動的出場持續性窗口（ms）。
    pub(super) fn compute_exit_persistence_ms(&self, efficiency_ratio: f64) -> u64 {
        let er = efficiency_ratio.clamp(0.0, 1.0);
        (self.min_persistence_ms as f64 * (1.0 - er)).max(0.0) as u64
    }

    /// RC-02: Check if higher-TF trend aligns with the proposed entry direction.
    /// RC-02: 檢查較高時間框架趨勢是否與擬入場方向一致。
    pub(super) fn higher_tf_allows_entry(&self, symbol: &str, is_long: bool) -> bool {
        match self.higher_tf_trend.get(symbol) {
            // No trend data yet — allow entry (cold-start safe).
            // 尚無趨勢數據 — 允許入場（冷啟動安全）。
            None => true,
            // Long requires bullish (true), short requires bearish (false).
            // 做多需要看漲（true），做空需要看跌（false）。
            Some(&bullish) => bullish == is_long,
        }
    }
}
