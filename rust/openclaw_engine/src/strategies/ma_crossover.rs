//! MA Crossover Strategy V2 — KAMA + ADX filter + Hurst regime filter + multi-TF confirmation.
//! MA 交叉策略 V2 — KAMA + ADX 過濾 + 赫斯特狀態過濾 + 多時間框架確認。

use super::Strategy;
use crate::intent_processor::OrderIntent;
use crate::tick_pipeline::TickContext;

pub struct MaCrossover {
    active: bool,
    position: Option<bool>,
    last_trade_ms: u64,
    cooldown_ms: u64,
    adx_threshold: f64,
    default_qty: f64,
    /// RC-01: Enable Hurst regime filter — skip entry in mean-reverting / random-walk markets.
    /// RC-01: 啟用赫斯特狀態過濾 — 在均值回歸/隨機漫步市場中跳過入場。
    regime_filter_enabled: bool,
    /// RC-02: Higher timeframe trend direction (None = no data yet).
    /// RC-02: 較高時間框架趨勢方向（None = 尚無數據）。
    higher_tf_trend: Option<bool>,
    /// RC-02: Slow EMA of sma_50 as proxy for 4h trend.
    /// RC-02: sma_50 的慢速 EMA，作為 4h 趨勢的替代指標。
    higher_tf_sma: Option<f64>,
    // RC-04: Previous state for rejection rollback / 拒絕回滾用的先前狀態
    prev_position: Option<bool>,
    prev_last_trade_ms: u64,
}

impl MaCrossover {
    pub fn new() -> Self {
        Self {
            active: true, position: None, last_trade_ms: 0,
            cooldown_ms: 300_000, adx_threshold: 20.0, default_qty: 1e9,
            regime_filter_enabled: true,
            higher_tf_trend: None,
            higher_tf_sma: None,
            prev_position: None, prev_last_trade_ms: 0,
        }
    }

    fn make_intent(&self, ctx: &TickContext, is_long: bool, conf: f64) -> OrderIntent {
        OrderIntent {
            symbol: ctx.symbol.clone(), is_long, qty: self.default_qty,
            confidence: conf, strategy: self.name().into(),
            order_type: "market".into(), limit_price: None,
        }
    }

    /// RC-01: Check if Hurst regime allows entry (only "trending" passes).
    /// RC-01: 檢查赫斯特狀態是否允許入場（僅 "trending" 通過）。
    fn regime_allows_entry(&self, ctx: &TickContext) -> bool {
        if !self.regime_filter_enabled {
            return true;
        }
        let ind = match &ctx.indicators { Some(i) => i, None => return true };
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
    fn update_higher_tf(&mut self, sma_50: f64) {
        const ALPHA: f64 = 0.003; // half-life ≈ 231 min ≈ 4h at 1m ticks
        let new_val = match self.higher_tf_sma {
            // First data point — initialize directly, no trend yet.
            // 第一個數據點 — 直接初始化，尚無趨勢。
            None => {
                self.higher_tf_sma = Some(sma_50);
                self.higher_tf_trend = None; // Need at least one update to determine trend.
                return;
            }
            Some(prev) => ALPHA * sma_50 + (1.0 - ALPHA) * prev,
        };
        self.higher_tf_sma = Some(new_val);
        self.higher_tf_trend = Some(sma_50 > new_val);
    }

    /// RC-02: Check if higher-TF trend aligns with the proposed entry direction.
    /// RC-02: 檢查較高時間框架趨勢是否與擬入場方向一致。
    fn higher_tf_allows_entry(&self, is_long: bool) -> bool {
        match self.higher_tf_trend {
            // No trend data yet — allow entry (cold-start safe).
            // 尚無趨勢數據 — 允許入場（冷啟動安全）。
            None => true,
            // Long requires bullish (true), short requires bearish (false).
            // 做多需要看漲（true），做空需要看跌（false）。
            Some(bullish) => bullish == is_long,
        }
    }
}

impl Strategy for MaCrossover {
    fn name(&self) -> &str { "ma_crossover" }
    fn is_active(&self) -> bool { self.active }

    /// RC-04: Revert position and last_trade_ms on rejection.
    /// RC-04：拒絕時回滾 position 和 last_trade_ms。
    fn on_rejection(&mut self, _intent: &OrderIntent, _reason: &str) {
        self.position = self.prev_position;
        self.last_trade_ms = self.prev_last_trade_ms;
    }

    fn on_tick(&mut self, ctx: &TickContext) -> Vec<OrderIntent> {
        let ind = match &ctx.indicators { Some(i) => i, None => return vec![] };
        if self.last_trade_ms > 0 && ctx.timestamp_ms < self.last_trade_ms + self.cooldown_ms { return vec![]; }

        // ADX trend-strength gate (existing).
        // ADX 趨勢強度門檻（原有）。
        let adx = ind.adx.as_ref().map(|a| a.adx).unwrap_or(0.0);
        if adx < self.adx_threshold { return vec![]; }

        // RC-02: Update higher-TF proxy from sma_50 (do this every tick for EMA warmup).
        // RC-02: 從 sma_50 更新較高時間框架替代指標（每個 tick 更新以暖機 EMA）。
        if let Some(sma_50) = ind.sma_50 {
            self.update_higher_tf(sma_50);
        }

        let fast = ind.kama.as_ref().map(|k| k.kama).unwrap_or_else(|| ind.sma_20.unwrap_or(0.0));
        let slow = ind.sma_20.unwrap_or(0.0);
        if fast == 0.0 || slow == 0.0 { return vec![]; }

        let mut intents = Vec::new();

        // RC-04: Snapshot state before any mutation for rejection rollback.
        // RC-04：在任何變更前快照狀態，供拒絕回滾使用。
        self.prev_position = self.position;
        self.prev_last_trade_ms = self.last_trade_ms;

        match self.position {
            None => {
                // Entry path — apply RC-01 regime filter + RC-02 higher-TF confirmation.
                // 入場路徑 — 套用 RC-01 狀態過濾 + RC-02 較高時間框架確認。
                if !self.regime_allows_entry(ctx) {
                    return vec![];
                }

                if fast > slow {
                    if !self.higher_tf_allows_entry(true) { return vec![]; }
                    intents.push(self.make_intent(ctx, true, 0.6));
                    self.position = Some(true);
                    self.last_trade_ms = ctx.timestamp_ms;
                } else if fast < slow {
                    if !self.higher_tf_allows_entry(false) { return vec![]; }
                    intents.push(self.make_intent(ctx, false, 0.6));
                    self.position = Some(false);
                    self.last_trade_ms = ctx.timestamp_ms;
                }
            }
            Some(is_long) => {
                // Exit path — RC-01/RC-02 filters do NOT apply to exits.
                // 出場路徑 — RC-01/RC-02 過濾不適用於出場。
                if is_long && fast < slow {
                    intents.push(self.make_intent(ctx, false, 0.5));
                    self.position = None;
                    self.last_trade_ms = ctx.timestamp_ms;
                } else if !is_long && fast > slow {
                    intents.push(self.make_intent(ctx, true, 0.5));
                    self.position = None;
                    self.last_trade_ms = ctx.timestamp_ms;
                }
            }
        }
        intents
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use openclaw_core::indicators::{AdxResult, HurstResult, IndicatorSnapshot, KamaResult};

    /// Helper: build a TickContext with given indicator values.
    /// 輔助函數：用給定指標值構建 TickContext。
    fn ctx_with(sma: f64, kama: f64, adx: f64, ts: u64) -> TickContext {
        TickContext {
            symbol: "BTC".into(), price: 50000.0, timestamp_ms: ts,
            indicators: Some(IndicatorSnapshot {
                sma_20: Some(sma), kama: Some(KamaResult { kama, efficiency_ratio: 0.5 }),
                adx: Some(AdxResult { adx, plus_di: 25.0, minus_di: 15.0 }),
                ..Default::default()
            }),
            signals: vec![], h0_allowed: true,
        }
    }

    /// Helper: build a TickContext with Hurst regime data.
    /// 輔助函數：用赫斯特狀態數據構建 TickContext。
    fn ctx_with_hurst(sma: f64, kama: f64, adx: f64, ts: u64, regime: &str, hurst_val: f64) -> TickContext {
        TickContext {
            symbol: "BTC".into(), price: 50000.0, timestamp_ms: ts,
            indicators: Some(IndicatorSnapshot {
                sma_20: Some(sma), kama: Some(KamaResult { kama, efficiency_ratio: 0.5 }),
                adx: Some(AdxResult { adx, plus_di: 25.0, minus_di: 15.0 }),
                hurst: Some(HurstResult { hurst: hurst_val, regime: regime.to_string() }),
                ..Default::default()
            }),
            signals: vec![], h0_allowed: true,
        }
    }

    /// Helper: build a TickContext with sma_50 for higher-TF testing.
    /// 輔助函數：用 sma_50 構建 TickContext 以測試較高時間框架。
    fn ctx_with_sma50(sma_20: f64, kama: f64, adx: f64, ts: u64, sma_50: f64) -> TickContext {
        TickContext {
            symbol: "BTC".into(), price: 50000.0, timestamp_ms: ts,
            indicators: Some(IndicatorSnapshot {
                sma_20: Some(sma_20), sma_50: Some(sma_50),
                kama: Some(KamaResult { kama, efficiency_ratio: 0.5 }),
                adx: Some(AdxResult { adx, plus_di: 25.0, minus_di: 15.0 }),
                ..Default::default()
            }),
            signals: vec![], h0_allowed: true,
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Existing tests (must still pass) / 原有測試（必須繼續通過）
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_no_signal_low_adx() {
        let mut s = MaCrossover::new();
        assert!(s.on_tick(&ctx_with(100.0, 101.0, 15.0, 0)).is_empty());
    }

    #[test]
    fn test_long_entry() {
        let mut s = MaCrossover::new();
        let i = s.on_tick(&ctx_with(100.0, 101.0, 25.0, 0));
        assert_eq!(i.len(), 1);
        assert!(i[0].is_long);
    }

    #[test]
    fn test_exit_on_reverse() {
        let mut s = MaCrossover::new();
        s.on_tick(&ctx_with(100.0, 101.0, 25.0, 0));
        let i = s.on_tick(&ctx_with(101.0, 100.0, 25.0, 500_000));
        assert_eq!(i.len(), 1);
        assert!(!i[0].is_long);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // RC-01: Hurst regime filter tests / RC-01: 赫斯特狀態過濾測試
    // ═══════════════════════════════════════════════════════════════════════

    /// Entry blocked when Hurst regime is "mean_reverting" (H < 0.5).
    /// 赫斯特狀態為「均值回歸」時阻擋入場。
    #[test]
    fn test_regime_filter_blocks_mean_reverting() {
        let mut s = MaCrossover::new();
        // fast(kama=101) > slow(sma_20=100), ADX=25 → would normally enter long.
        // 快線 > 慢線, ADX 足夠 → 正常情況會做多入場。
        let ctx = ctx_with_hurst(100.0, 101.0, 25.0, 0, "mean_reverting", 0.35);
        let intents = s.on_tick(&ctx);
        assert!(intents.is_empty(), "Entry must be blocked in mean_reverting regime");
    }

    /// Entry allowed when Hurst regime is "trending" (H > 0.5).
    /// 赫斯特狀態為「趨勢」時允許入場。
    #[test]
    fn test_regime_filter_allows_trending() {
        let mut s = MaCrossover::new();
        let ctx = ctx_with_hurst(100.0, 101.0, 25.0, 0, "trending", 0.72);
        let intents = s.on_tick(&ctx);
        assert_eq!(intents.len(), 1, "Entry must be allowed in trending regime");
        assert!(intents[0].is_long);
    }

    /// Exit still works even in mean_reverting regime (position already open).
    /// 即使在均值回歸狀態下，已持有的倉位仍可出場。
    #[test]
    fn test_regime_filter_allows_exit() {
        let mut s = MaCrossover::new();
        // Step 1: Enter long in trending regime.
        // 步驟 1：在趨勢狀態下做多入場。
        let ctx_entry = ctx_with_hurst(100.0, 101.0, 25.0, 0, "trending", 0.72);
        let entry = s.on_tick(&ctx_entry);
        assert_eq!(entry.len(), 1, "Should enter long");

        // Step 2: Regime flips to mean_reverting, but crossover reverses → exit must work.
        // 步驟 2：狀態轉為均值回歸，但交叉反轉 → 出場必須有效。
        let ctx_exit = ctx_with_hurst(101.0, 100.0, 25.0, 500_000, "mean_reverting", 0.35);
        let exit = s.on_tick(&ctx_exit);
        assert_eq!(exit.len(), 1, "Exit must work even in mean_reverting regime");
        assert!(!exit[0].is_long);
    }

    /// Entry blocked when Hurst regime is "random_walk".
    /// 赫斯特狀態為「隨機漫步」時阻擋入場。
    #[test]
    fn test_regime_filter_blocks_random_walk() {
        let mut s = MaCrossover::new();
        let ctx = ctx_with_hurst(100.0, 101.0, 25.0, 0, "random_walk", 0.50);
        let intents = s.on_tick(&ctx);
        assert!(intents.is_empty(), "Entry must be blocked in random_walk regime");
    }

    /// Regime filter can be disabled via struct field.
    /// 狀態過濾可通過結構體字段禁用。
    #[test]
    fn test_regime_filter_disabled() {
        let mut s = MaCrossover::new();
        s.regime_filter_enabled = false;
        let ctx = ctx_with_hurst(100.0, 101.0, 25.0, 0, "mean_reverting", 0.35);
        let intents = s.on_tick(&ctx);
        assert_eq!(intents.len(), 1, "Entry allowed when regime filter is disabled");
    }

    // ═══════════════════════════════════════════════════════════════════════
    // RC-02: Multi-TF confirmation tests / RC-02: 多時間框架確認測試
    // ═══════════════════════════════════════════════════════════════════════

    /// Long entry blocked when higher-TF trend is bearish.
    /// 較高時間框架趨勢看跌時阻擋做多入場。
    #[test]
    fn test_higher_tf_blocks_misaligned() {
        let mut s = MaCrossover::new();
        // Warm up higher_tf_sma with a high value so sma_50 < higher_tf_sma → bearish trend.
        // 用高值暖機 higher_tf_sma，使 sma_50 < higher_tf_sma → 看跌趨勢。
        s.higher_tf_sma = Some(110.0);
        // After one tick, higher_tf_sma ≈ 0.01*100 + 0.99*110 = 109.9, sma_50=100 < 109.9 → bearish.
        // 一個 tick 後，higher_tf_sma ≈ 109.9，sma_50=100 < 109.9 → 看跌。
        let ctx = ctx_with_sma50(100.0, 101.0, 25.0, 0, 100.0);
        let intents = s.on_tick(&ctx);
        // fast(101) > slow(100) → would want to go long, but higher TF is bearish → blocked.
        // 快線 > 慢線 → 想做多，但較高 TF 看跌 → 阻擋。
        assert!(intents.is_empty(), "Long entry must be blocked when higher TF is bearish");
    }

    /// Long entry allowed when higher-TF trend is bullish.
    /// 較高時間框架趨勢看漲時允許做多入場。
    #[test]
    fn test_higher_tf_allows_aligned() {
        let mut s = MaCrossover::new();
        // Warm up higher_tf_sma with a low value so sma_50 > higher_tf_sma → bullish trend.
        // 用低值暖機 higher_tf_sma，使 sma_50 > higher_tf_sma → 看漲趨勢。
        s.higher_tf_sma = Some(90.0);
        // After one tick, higher_tf_sma ≈ 0.01*100 + 0.99*90 = 90.1, sma_50=100 > 90.1 → bullish.
        // 一個 tick 後，higher_tf_sma ≈ 90.1，sma_50=100 > 90.1 → 看漲。
        let ctx = ctx_with_sma50(100.0, 101.0, 25.0, 0, 100.0);
        let intents = s.on_tick(&ctx);
        assert_eq!(intents.len(), 1, "Long entry must be allowed when higher TF is bullish");
        assert!(intents[0].is_long);
    }

    /// Short entry blocked when higher-TF trend is bullish.
    /// 較高時間框架趨勢看漲時阻擋做空入場。
    #[test]
    fn test_higher_tf_blocks_short_when_bullish() {
        let mut s = MaCrossover::new();
        s.higher_tf_sma = Some(90.0);
        // sma_50=100 > 90.1 → bullish → short blocked.
        let ctx = ctx_with_sma50(101.0, 100.0, 25.0, 0, 100.0);
        let intents = s.on_tick(&ctx);
        assert!(intents.is_empty(), "Short entry must be blocked when higher TF is bullish");
    }

    /// Entry allowed when higher_tf_trend is None (cold start).
    /// higher_tf_trend 為 None 時允許入場（冷啟動）。
    #[test]
    fn test_higher_tf_cold_start_allows_entry() {
        let mut s = MaCrossover::new();
        // No sma_50 in context → higher_tf_trend stays None → entry allowed.
        // 上下文中無 sma_50 → higher_tf_trend 保持 None → 允許入場。
        let ctx = ctx_with(100.0, 101.0, 25.0, 0);
        let intents = s.on_tick(&ctx);
        assert_eq!(intents.len(), 1, "Entry must be allowed during cold start (no higher TF data)");
    }

    /// Exit works regardless of higher-TF trend direction.
    /// 無論較高時間框架趨勢方向如何，出場均有效。
    #[test]
    fn test_higher_tf_does_not_block_exit() {
        let mut s = MaCrossover::new();
        // Enter long with aligned higher TF.
        s.higher_tf_sma = Some(90.0);
        let ctx_entry = ctx_with_sma50(100.0, 101.0, 25.0, 0, 100.0);
        let entry = s.on_tick(&ctx_entry);
        assert_eq!(entry.len(), 1);

        // Now flip higher TF to bearish and reverse crossover → exit must still work.
        // 現在將較高 TF 翻轉為看跌並反轉交叉 → 出場仍必須有效。
        s.higher_tf_sma = Some(110.0);
        s.higher_tf_trend = Some(false);
        let ctx_exit = ctx_with_sma50(101.0, 100.0, 25.0, 500_000, 100.0);
        let exit = s.on_tick(&ctx_exit);
        assert_eq!(exit.len(), 1, "Exit must work regardless of higher TF trend");
    }
}
