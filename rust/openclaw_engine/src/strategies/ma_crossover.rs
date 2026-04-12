//! MA Crossover Strategy V2 — KAMA + ADX filter + Hurst regime filter + multi-TF confirmation.
//! MA 交叉策略 V2 — KAMA + ADX 過濾 + 赫斯特狀態過濾 + 多時間框架確認。
//!
//! MODULE_NOTE (EN): Fast/slow KAMA crossover with ADX trending filter, Hurst
//!   regime gating, and multi-timeframe confirmation for reduced false signals.
//! MODULE_NOTE (中): 快慢 KAMA 交叉 + ADX 趨勢過濾 + 赫斯特狀態門控 +
//!   多時間框架確認，減少假信號。

use std::collections::HashMap;

use super::{ParamRange, Strategy, StrategyAction, StrategyParams};
use crate::intent_processor::OrderIntent;
use crate::tick_pipeline::TickContext;
use serde::{Deserialize, Serialize};
use tracing::info;

/// Tunable parameters for MA Crossover strategy (Phase 3a AGT-1).
/// MA 交叉策略的可調參數。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MaCrossoverParams {
    pub cooldown_ms: u64,
    pub adx_threshold: f64,
    pub default_qty: f64,
    pub regime_filter_enabled: bool,
    pub higher_tf_alpha: f64,
}

impl Default for MaCrossoverParams {
    fn default() -> Self {
        Self {
            cooldown_ms: 300_000,
            adx_threshold: 20.0,
            default_qty: 1e9,
            regime_filter_enabled: true,
            higher_tf_alpha: 0.003,
        }
    }
}

impl StrategyParams for MaCrossoverParams {
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
                name: "adx_threshold".into(),
                min: 10.0,
                max: 50.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "default_qty".into(),
                min: 0.001,
                max: 1e12,
                step: None,
                agent_adjustable: false,
                db_persisted: true,
            },
            ParamRange {
                name: "regime_filter_enabled".into(),
                min: 0.0,
                max: 1.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "higher_tf_alpha".into(),
                min: 0.001,
                max: 0.05,
                step: None,
                agent_adjustable: true,
                db_persisted: true,
            },
        ]
    }

    fn validate(&self) -> Result<(), String> {
        if self.cooldown_ms < 60_000 {
            return Err("cooldown_ms must be >= 60s".into());
        }
        if self.adx_threshold < 5.0 || self.adx_threshold > 80.0 {
            return Err("adx_threshold must be in [5, 80]".into());
        }
        if self.higher_tf_alpha <= 0.0 || self.higher_tf_alpha > 0.1 {
            return Err("higher_tf_alpha must be in (0, 0.1]".into());
        }
        Ok(())
    }
}

pub struct MaCrossover {
    active: bool,
    /// Per-symbol position tracking: symbol → is_long direction.
    /// 每幣種獨立持倉追蹤：symbol → 多空方向。
    positions: HashMap<String, bool>,
    /// Per-symbol last trade timestamp for cooldown.
    /// 每幣種最後交易時間戳（用於冷卻）。
    last_trade_ms: HashMap<String, u64>,
    pub(crate) cooldown_ms: u64,
    pub(crate) adx_threshold: f64,
    default_qty: f64,
    /// RC-01: Enable Hurst regime filter — skip entry in mean-reverting / random-walk markets.
    /// RC-01: 啟用赫斯特狀態過濾 — 在均值回歸/隨機漫步市場中跳過入場。
    pub(crate) regime_filter_enabled: bool,
    /// RC-02: Per-symbol higher timeframe trend direction.
    /// RC-02: 每幣種較高時間框架趨勢方向。
    higher_tf_trend: HashMap<String, bool>,
    /// RC-02: Per-symbol slow EMA of sma_50 as proxy for 4h trend.
    /// RC-02: 每幣種 sma_50 的慢速 EMA，作為 4h 趨勢的替代指標。
    higher_tf_sma: HashMap<String, f64>,
    /// Higher-TF EMA smoothing alpha. Default 0.003 = ~231min half-life ≈ 4h at 1m ticks.
    /// Agent can tune this parameter. Will be replaced by real multi-TF klines in Phase 1.
    /// 較高時間框架 EMA 平滑 alpha。默認 0.003 = ~231 分鐘半衰期 ≈ 1 分鐘 tick 下約 4 小時。
    /// Agent 可調整此參數。Phase 1 將改用真實多時間框架 K 線替代。
    pub higher_tf_alpha: f64,
    /// QC-H1: Entry confidence base (default 0.45). / 入場信心基礎值。
    pub(crate) entry_conf_base: f64,
    /// QC-H1: Entry regime bonus ±(default 0.15): trending +, mean_reverting −.
    /// QC-H1：入場市場狀態加分 ±（默認 0.15）：趨勢 +，均值回歸 −。
    pub(crate) entry_regime_bonus: f64,
    /// QC-H1: Exit confidence base (default 0.5). / 出場信心基礎值。
    pub(crate) exit_conf_base: f64,
    // RC-04: Per-symbol previous state for rejection rollback / 每幣種拒絕回滾用的先前狀態
    prev_position: HashMap<String, Option<bool>>,
    prev_last_trade_ms: HashMap<String, u64>,
    /// CONF-D: Multiplier applied to emitted intent.confidence (default 1.0, range [0,2]).
    /// CONF-D：發出 intent.confidence 的乘數（默認 1.0，範圍 [0,2]）。
    conf_scale: f64,
}

impl MaCrossover {
    pub fn new() -> Self {
        Self {
            active: true,
            positions: HashMap::new(),
            last_trade_ms: HashMap::new(),
            cooldown_ms: 300_000,
            adx_threshold: 20.0,
            default_qty: 1e9,
            regime_filter_enabled: true,
            higher_tf_trend: HashMap::new(),
            higher_tf_sma: HashMap::new(),
            higher_tf_alpha: 0.003,
            entry_conf_base: 0.45,
            entry_regime_bonus: 0.15,
            exit_conf_base: 0.5,
            prev_position: HashMap::new(),
            prev_last_trade_ms: HashMap::new(),
            conf_scale: 1.0,
        }
    }

    /// Phase 3a: Update tunable parameters (does not reset state).
    /// Phase 3a：更新可調參數（不重置狀態）。
    pub fn update_params(&mut self, params: MaCrossoverParams) -> Result<(), String> {
        params.validate()?;
        self.cooldown_ms = params.cooldown_ms;
        self.adx_threshold = params.adx_threshold;
        self.default_qty = params.default_qty;
        self.regime_filter_enabled = params.regime_filter_enabled;
        self.higher_tf_alpha = params.higher_tf_alpha;
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
        }
    }

    fn make_intent(&self, ctx: &TickContext, is_long: bool, conf: f64) -> OrderIntent {
        // CONF-D: scale and clamp the emitted confidence into [0, 1].
        // CONF-D：套用 conf_scale 後 clamp 到 [0, 1]。
        let scaled = (conf * self.conf_scale).clamp(0.0, 1.0);
        OrderIntent {
            symbol: ctx.symbol.clone(),
            is_long,
            qty: self.default_qty,
            confidence: scaled,
            strategy: self.name().into(),
            order_type: "market".into(),
            limit_price: None,
        }
    }

    /// RC-01: Check if Hurst regime allows entry (only "trending" passes).
    /// RC-01: 檢查赫斯特狀態是否允許入場（僅 "trending" 通過）。
    fn regime_allows_entry(&self, ctx: &TickContext) -> bool {
        if !self.regime_filter_enabled {
            return true;
        }
        let ind = match &ctx.indicators {
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
    fn update_higher_tf(&mut self, symbol: &str, sma_50: f64) {
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
        self.higher_tf_trend.insert(symbol.to_string(), sma_50 > new_val);
    }

    /// Dynamic confidence: ADX excess + Hurst regime fit.
    /// 動態信心：ADX 超額 + Hurst regime 契合度。
    /// trending regime + 高 ADX → 高 conf；mean_reverting regime → 懲罰。
    fn compute_entry_confidence(&self, adx: f64, regime: Option<&str>) -> f64 {
        // QC-H1: base, regime_bonus configurable (was hardcoded 0.45 / 0.15)
        let base = self.entry_conf_base;
        // adx_threshold default 25 → bonus from 0 at threshold to +0.25 at adx=50
        let adx_bonus = ((adx - self.adx_threshold).max(0.0) / 100.0).min(0.25);
        let regime_bonus = match regime {
            Some("trending") => self.entry_regime_bonus,
            Some("mean_reverting") => -self.entry_regime_bonus,
            _ => 0.0,
        };
        (base + adx_bonus + regime_bonus).clamp(0.2, 0.9)
    }

    /// Exit confidence: cross-back is a real signal but weaker than fresh entry.
    /// 出場信心：反向交叉是真信號但弱於新入場。
    fn compute_exit_confidence(&self, adx: f64) -> f64 {
        // QC-H1: base configurable (was hardcoded 0.5)
        let base = self.exit_conf_base;
        let adx_bonus = ((adx - self.adx_threshold).max(0.0) / 100.0).min(0.2);
        (base + adx_bonus).clamp(0.4, 0.8)
    }

    /// RC-02: Check if higher-TF trend aligns with the proposed entry direction.
    /// RC-02: 檢查較高時間框架趨勢是否與擬入場方向一致。
    fn higher_tf_allows_entry(&self, symbol: &str, is_long: bool) -> bool {
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

impl Strategy for MaCrossover {
    fn name(&self) -> &str {
        "ma_crossover"
    }
    fn is_active(&self) -> bool {
        self.active
    }
    fn set_active(&mut self, active: bool) {
        self.active = active;
    }

    /// RC-04: Revert per-symbol position and last_trade_ms on rejection.
    /// RC-04：拒絕時回滾該幣種的 position 和 last_trade_ms。
    fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
        let sym = &intent.symbol;
        if let Some(prev) = self.prev_position.get(sym) {
            match prev {
                Some(b) => { self.positions.insert(sym.clone(), *b); }
                None => { self.positions.remove(sym); }
            }
        }
        if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
            if ts == 0 { self.last_trade_ms.remove(sym); } else { self.last_trade_ms.insert(sym.clone(), ts); }
        }
    }

    /// Reset internal position for the closed symbol (risk-stop).
    /// 外部平倉（風控止損）時重設該幣種的內部倉位狀態。
    fn on_external_close(&mut self, symbol: &str) {
        self.positions.remove(symbol);
    }

    fn on_tick(&mut self, ctx: &TickContext) -> Vec<StrategyAction> {
        let ind = match &ctx.indicators {
            Some(i) => i,
            None => return vec![],
        };
        let last_ms = self.last_trade_ms.get(&ctx.symbol).copied().unwrap_or(0);
        if last_ms > 0 && ctx.timestamp_ms < last_ms + self.cooldown_ms {
            return vec![];
        }

        // ADX trend-strength gate (existing).
        // ADX 趨勢強度門檻（原有）。
        let adx = ind.adx.as_ref().map(|a| a.adx).unwrap_or(0.0);
        if adx < self.adx_threshold {
            return vec![];
        }

        // RC-02: Update per-symbol higher-TF proxy from sma_50 (every tick for EMA warmup).
        // RC-02: 從 sma_50 更新該幣種的較高時間框架替代指標（每個 tick 更新以暖機 EMA）。
        if let Some(sma_50) = ind.sma_50 {
            self.update_higher_tf(&ctx.symbol, sma_50);
        }

        let fast = match ind.kama.as_ref() {
            Some(k) => k.kama,
            None => {
                // QC-#2: Log KAMA fallback — strategy silently degrades to SMA vs SMA (never crosses).
                // QC-#2：記錄 KAMA 退化 — 策略靜默退化為 SMA vs SMA（永不交叉）。
                tracing::debug!(
                    symbol = %ctx.symbol,
                    "KAMA unavailable, falling back to SMA(20) / KAMA 不可用，退化為 SMA(20)"
                );
                ind.sma_20.unwrap_or(0.0)
            }
        };
        let slow = ind.sma_20.unwrap_or(0.0);
        if fast == 0.0 || slow == 0.0 {
            return vec![];
        }

        let mut intents = Vec::new();

        // RC-04: Snapshot per-symbol state before any mutation for rejection rollback.
        // RC-04：在任何變更前快照該幣種狀態，供拒絕回滾使用。
        self.prev_position.insert(ctx.symbol.clone(), self.positions.get(&ctx.symbol).copied());
        self.prev_last_trade_ms.insert(ctx.symbol.clone(), last_ms);

        match self.positions.get(&ctx.symbol).copied() {
            None => {
                // Entry path — apply RC-01 regime filter + RC-02 higher-TF confirmation.
                // 入場路徑 — 套用 RC-01 狀態過濾 + RC-02 較高時間框架確認。
                if !self.regime_allows_entry(ctx) {
                    return vec![];
                }

                let regime = ind.hurst.as_ref().map(|h| h.regime.as_str());
                let entry_conf = self.compute_entry_confidence(adx, regime);
                if fast > slow {
                    if !self.higher_tf_allows_entry(&ctx.symbol, true) {
                        return vec![];
                    }
                    intents.push(StrategyAction::Open(self.make_intent(ctx, true, entry_conf)));
                    self.positions.insert(ctx.symbol.clone(), true);
                    self.last_trade_ms.insert(ctx.symbol.clone(), ctx.timestamp_ms);
                } else if fast < slow {
                    if !self.higher_tf_allows_entry(&ctx.symbol, false) {
                        return vec![];
                    }
                    intents.push(StrategyAction::Open(self.make_intent(ctx, false, entry_conf)));
                    self.positions.insert(ctx.symbol.clone(), false);
                    self.last_trade_ms.insert(ctx.symbol.clone(), ctx.timestamp_ms);
                }
            }
            Some(is_long) => {
                // Exit path — RC-01/RC-02 filters do NOT apply to exits.
                // KAMA crosses back through SMA20 = trend reversal (Kaufman).
                // Exit urgency > entry selectivity: no ADX/regime/higher-TF filter on exit.
                // 出場路徑 — KAMA 回穿 SMA20 = 趨勢反轉。出場不套用入場過濾器。
                let exit_conf = self.compute_exit_confidence(adx);
                if is_long && fast < slow {
                    intents.push(StrategyAction::Close {
                        symbol: ctx.symbol.clone(),
                        confidence: exit_conf,
                        reason: "ma_reverse_cross".into(),
                    });
                    self.positions.remove(&ctx.symbol);
                    self.last_trade_ms.insert(ctx.symbol.clone(), ctx.timestamp_ms);
                } else if !is_long && fast > slow {
                    intents.push(StrategyAction::Close {
                        symbol: ctx.symbol.clone(),
                        confidence: exit_conf,
                        reason: "ma_reverse_cross".into(),
                    });
                    self.positions.remove(&ctx.symbol);
                    self.last_trade_ms.insert(ctx.symbol.clone(), ctx.timestamp_ms);
                }
            }
        }
        intents
    }

    fn update_params_json(&mut self, json: &str) -> Result<(), String> {
        let params: MaCrossoverParams = serde_json::from_str(json).map_err(|e| e.to_string())?;
        self.update_params(params)
    }

    fn get_params_json(&self) -> String {
        serde_json::to_string(&self.get_params()).unwrap_or_default()
    }

    fn param_ranges_json(&self) -> String {
        serde_json::to_string(&MaCrossoverParams::param_ranges()).unwrap_or_default()
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
    use openclaw_core::indicators::{AdxResult, HurstResult, IndicatorSnapshot, KamaResult};

    /// Helper: build a TickContext with given indicator values.
    /// 輔助函數：用給定指標值構建 TickContext。
    fn ctx_with(sma: f64, kama: f64, adx: f64, ts: u64) -> TickContext {
        TickContext {
            symbol: "BTC".into(),
            price: 50000.0,
            timestamp_ms: ts,
            indicators: Some(IndicatorSnapshot {
                sma_20: Some(sma),
                kama: Some(KamaResult {
                    kama,
                    efficiency_ratio: 0.5,
                }),
                adx: Some(AdxResult {
                    adx,
                    plus_di: 25.0,
                    minus_di: 15.0,
                }),
                ..Default::default()
            }),
            signals: vec![],
            h0_allowed: true,
        }
    }

    /// Helper: build a TickContext with Hurst regime data.
    /// 輔助函數：用赫斯特狀態數據構建 TickContext。
    fn ctx_with_hurst(
        sma: f64,
        kama: f64,
        adx: f64,
        ts: u64,
        regime: &str,
        hurst_val: f64,
    ) -> TickContext {
        TickContext {
            symbol: "BTC".into(),
            price: 50000.0,
            timestamp_ms: ts,
            indicators: Some(IndicatorSnapshot {
                sma_20: Some(sma),
                kama: Some(KamaResult {
                    kama,
                    efficiency_ratio: 0.5,
                }),
                adx: Some(AdxResult {
                    adx,
                    plus_di: 25.0,
                    minus_di: 15.0,
                }),
                hurst: Some(HurstResult {
                    hurst: hurst_val,
                    regime: regime.to_string(),
                }),
                ..Default::default()
            }),
            signals: vec![],
            h0_allowed: true,
        }
    }

    /// Helper: build a TickContext with sma_50 for higher-TF testing.
    /// 輔助函數：用 sma_50 構建 TickContext 以測試較高時間框架。
    fn ctx_with_sma50(sma_20: f64, kama: f64, adx: f64, ts: u64, sma_50: f64) -> TickContext {
        TickContext {
            symbol: "BTC".into(),
            price: 50000.0,
            timestamp_ms: ts,
            indicators: Some(IndicatorSnapshot {
                sma_20: Some(sma_20),
                sma_50: Some(sma_50),
                kama: Some(KamaResult {
                    kama,
                    efficiency_ratio: 0.5,
                }),
                adx: Some(AdxResult {
                    adx,
                    plus_di: 25.0,
                    minus_di: 15.0,
                }),
                ..Default::default()
            }),
            signals: vec![],
            h0_allowed: true,
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
        match &i[0] {
            StrategyAction::Open(intent) => assert!(intent.is_long),
            other => panic!("expected StrategyAction::Open, got {:?}", other),
        }
    }

    #[test]
    fn test_exit_on_reverse() {
        let mut s = MaCrossover::new();
        s.on_tick(&ctx_with(100.0, 101.0, 25.0, 0));
        let i = s.on_tick(&ctx_with(101.0, 100.0, 25.0, 500_000));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Close { symbol, reason, .. } => {
                assert_eq!(symbol, "BTC");
                assert_eq!(reason, "ma_reverse_cross");
            }
            other => panic!("expected StrategyAction::Close, got {:?}", other),
        }
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
        assert!(
            intents.is_empty(),
            "Entry must be blocked in mean_reverting regime"
        );
    }

    /// Entry allowed when Hurst regime is "trending" (H > 0.5).
    /// 赫斯特狀態為「趨勢」時允許入場。
    #[test]
    fn test_regime_filter_allows_trending() {
        let mut s = MaCrossover::new();
        let ctx = ctx_with_hurst(100.0, 101.0, 25.0, 0, "trending", 0.72);
        let intents = s.on_tick(&ctx);
        assert_eq!(intents.len(), 1, "Entry must be allowed in trending regime");
        match &intents[0] {
            StrategyAction::Open(intent) => assert!(intent.is_long),
            other => panic!("expected StrategyAction::Open, got {:?}", other),
        }
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
        assert_eq!(
            exit.len(),
            1,
            "Exit must work even in mean_reverting regime"
        );
        match &exit[0] {
            StrategyAction::Close { reason, .. } => assert_eq!(reason, "ma_reverse_cross"),
            other => panic!("expected StrategyAction::Close, got {:?}", other),
        }
    }

    /// Entry blocked when Hurst regime is "random_walk".
    /// 赫斯特狀態為「隨機漫步」時阻擋入場。
    #[test]
    fn test_regime_filter_blocks_random_walk() {
        let mut s = MaCrossover::new();
        let ctx = ctx_with_hurst(100.0, 101.0, 25.0, 0, "random_walk", 0.50);
        let intents = s.on_tick(&ctx);
        assert!(
            intents.is_empty(),
            "Entry must be blocked in random_walk regime"
        );
    }

    /// Regime filter can be disabled via struct field.
    /// 狀態過濾可通過結構體字段禁用。
    #[test]
    fn test_regime_filter_disabled() {
        let mut s = MaCrossover::new();
        s.regime_filter_enabled = false;
        let ctx = ctx_with_hurst(100.0, 101.0, 25.0, 0, "mean_reverting", 0.35);
        let intents = s.on_tick(&ctx);
        assert_eq!(
            intents.len(),
            1,
            "Entry allowed when regime filter is disabled"
        );
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
        s.higher_tf_sma.insert("BTC".into(), 110.0);
        // After one tick, higher_tf_sma ≈ 0.01*100 + 0.99*110 = 109.9, sma_50=100 < 109.9 → bearish.
        // 一個 tick 後，higher_tf_sma ≈ 109.9，sma_50=100 < 109.9 → 看跌。
        let ctx = ctx_with_sma50(100.0, 101.0, 25.0, 0, 100.0);
        let intents = s.on_tick(&ctx);
        // fast(101) > slow(100) → would want to go long, but higher TF is bearish → blocked.
        // 快線 > 慢線 → 想做多，但較高 TF 看跌 → 阻擋。
        assert!(
            intents.is_empty(),
            "Long entry must be blocked when higher TF is bearish"
        );
    }

    /// Long entry allowed when higher-TF trend is bullish.
    /// 較高時間框架趨勢看漲時允許做多入場。
    #[test]
    fn test_higher_tf_allows_aligned() {
        let mut s = MaCrossover::new();
        // Warm up higher_tf_sma with a low value so sma_50 > higher_tf_sma → bullish trend.
        // 用低值暖機 higher_tf_sma，使 sma_50 > higher_tf_sma → 看漲趨勢。
        s.higher_tf_sma.insert("BTC".into(), 90.0);
        // After one tick, higher_tf_sma ≈ 0.01*100 + 0.99*90 = 90.1, sma_50=100 > 90.1 → bullish.
        // 一個 tick 後，higher_tf_sma ≈ 90.1，sma_50=100 > 90.1 → 看漲。
        let ctx = ctx_with_sma50(100.0, 101.0, 25.0, 0, 100.0);
        let intents = s.on_tick(&ctx);
        assert_eq!(
            intents.len(),
            1,
            "Long entry must be allowed when higher TF is bullish"
        );
        match &intents[0] {
            StrategyAction::Open(intent) => assert!(intent.is_long),
            other => panic!("expected StrategyAction::Open, got {:?}", other),
        }
    }

    /// Short entry blocked when higher-TF trend is bullish.
    /// 較高時間框架趨勢看漲時阻擋做空入場。
    #[test]
    fn test_higher_tf_blocks_short_when_bullish() {
        let mut s = MaCrossover::new();
        s.higher_tf_sma.insert("BTC".into(), 90.0);
        // sma_50=100 > 90.1 → bullish → short blocked.
        let ctx = ctx_with_sma50(101.0, 100.0, 25.0, 0, 100.0);
        let intents = s.on_tick(&ctx);
        assert!(
            intents.is_empty(),
            "Short entry must be blocked when higher TF is bullish"
        );
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
        assert_eq!(
            intents.len(),
            1,
            "Entry must be allowed during cold start (no higher TF data)"
        );
    }

    /// Exit works regardless of higher-TF trend direction.
    /// 無論較高時間框架趨勢方向如何，出場均有效。
    #[test]
    fn test_higher_tf_does_not_block_exit() {
        let mut s = MaCrossover::new();
        // Enter long with aligned higher TF.
        s.higher_tf_sma.insert("BTC".into(), 90.0);
        let ctx_entry = ctx_with_sma50(100.0, 101.0, 25.0, 0, 100.0);
        let entry = s.on_tick(&ctx_entry);
        assert_eq!(entry.len(), 1);

        // Now flip higher TF to bearish and reverse crossover → exit must still work.
        // 現在將較高 TF 翻轉為看跌並反轉交叉 → 出場仍必須有效。
        s.higher_tf_sma.insert("BTC".into(), 110.0);
        s.higher_tf_trend.insert("BTC".into(), false);
        let ctx_exit = ctx_with_sma50(101.0, 100.0, 25.0, 500_000, 100.0);
        let exit = s.on_tick(&ctx_exit);
        assert_eq!(
            exit.len(),
            1,
            "Exit must work regardless of higher TF trend"
        );
    }

    // ── Phase 3a: StrategyParams tests ──

    #[test]
    fn test_param_ranges_non_empty() {
        let ranges = MaCrossoverParams::param_ranges();
        assert!(!ranges.is_empty());
        assert!(ranges.iter().any(|r| r.name == "adx_threshold"));
    }

    #[test]
    fn test_validate_pass() {
        let p = MaCrossoverParams::default();
        assert!(p.validate().is_ok());
    }

    #[test]
    fn test_validate_fail() {
        let p = MaCrossoverParams {
            cooldown_ms: 1000,
            ..Default::default()
        }; // too low
        assert!(p.validate().is_err());
    }

    #[test]
    fn test_update_and_get_roundtrip() {
        let mut s = MaCrossover::new();
        let new_params = MaCrossoverParams {
            adx_threshold: 35.0,
            ..Default::default()
        };
        assert!(s.update_params(new_params).is_ok());
        let got = s.get_params();
        assert!((got.adx_threshold - 35.0).abs() < 1e-10);
    }

    #[test]
    fn test_json_roundtrip() {
        let mut s = MaCrossover::new();
        let json = r#"{"cooldown_ms":600000,"adx_threshold":25.0,"default_qty":1000000000.0,"regime_filter_enabled":true,"higher_tf_alpha":0.005}"#;
        assert!(s.update_params_json(json).is_ok());
        let out = s.get_params_json();
        assert!(out.contains("25.0") || out.contains("25"));
    }

    #[test]
    fn test_conf_scale_clamps_to_range() {
        // CONF-D: set_conf_scale must clamp to [0, 2].
        let mut s = MaCrossover::new();
        s.set_conf_scale(3.0);
        assert!((s.conf_scale() - 2.0).abs() < 1e-10);
        s.set_conf_scale(-1.0);
        assert!((s.conf_scale() - 0.0).abs() < 1e-10);
        s.set_conf_scale(1.5);
        assert!((s.conf_scale() - 1.5).abs() < 1e-10);
    }

    #[test]
    fn test_conf_scale_applied_to_emit() {
        // CONF-D: emitted confidence == raw * conf_scale, clamped to [0, 1].
        use crate::tick_pipeline::TickContext;
        let ctx = TickContext {
            symbol: "BTCUSDT".into(),
            price: 50000.0,
            timestamp_ms: 0,
            indicators: None,
            signals: vec![],
            h0_allowed: true,
        };
        let mut s = MaCrossover::new();
        s.set_conf_scale(0.5);
        let intent = s.make_intent(&ctx, true, 0.8);
        assert!((intent.confidence - 0.4).abs() < 1e-10);

        s.set_conf_scale(2.0);
        let intent = s.make_intent(&ctx, true, 0.9);
        assert!((intent.confidence - 1.0).abs() < 1e-10); // clamped
    }
}
