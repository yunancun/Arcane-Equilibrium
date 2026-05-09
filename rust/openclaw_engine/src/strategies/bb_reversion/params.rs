//! BB Reversion tunable params + StrategyParams impl + ConfluenceConfig builder.
//! BB 回歸策略可調參數 + StrategyParams 實作 + ConfluenceConfig 構建器。
//!
//! MODULE_NOTE (EN): Split from `bb_reversion.rs` (G5-05, §九 1200 line rule).
//!   Pure move — `BbReversionParams` struct, Default, StrategyParams impl, and
//!   `build_confluence_config()` helper. No logic changes.
//! MODULE_NOTE (中): 由 `bb_reversion.rs` 拆出（G5-05，§九 1200 行規則）。
//!   純搬移 — `BbReversionParams` 結構、Default、StrategyParams 實作與
//!   `build_confluence_config()` 輔助函式。無邏輯變更。

use super::super::confluence::ConfluenceConfig;
use super::super::{ParamRange, StrategyParams};
use serde::{Deserialize, Serialize};

/// Tunable parameters for BB Reversion strategy (Phase 3a).
/// BB 回歸策略的可調參數。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct BbReversionParams {
    pub cooldown_ms: u64,
    pub default_qty: f64,
    pub use_limit: bool,
    pub limit_offset_bps: f64,
    /// RSI oversold threshold for long entry / RSI 超賣閾值（做多入場）
    pub rsi_oversold: f64,
    /// RSI overbought threshold for short entry / RSI 超買閾值（做空入場）
    pub rsi_overbought: f64,
    /// QC-#7: Hurst regime confidence boost for mean-reverting regime (default 0.1).
    /// QC-#7：均值回歸市場狀態信心加成（默認 0.1）。
    pub hurst_regime_boost: f64,
    // ── G-SR-1 confluence + persistence fields (A0-c) ──
    /// Minimum signal persistence before entry (ms). / 入場前信號最小持續時間（ms）。
    pub min_persistence_ms: u64,
    /// Minimum order notional (USD). / 最小訂單名義值（USD）。
    pub min_notional_usd: f64,
    /// EDGE-P1-2: Minimum |funding_rate| to trigger directional boost (default 5 bps = 0.0005).
    /// EDGE-P1-2：觸發方向性加成的最低 |funding_rate|（默認 5 bps = 0.0005）。
    pub funding_rate_threshold: f64,
    /// EDGE-P1-2: Confidence boost when funding rate is extreme + aligned with signal (default 0.08).
    /// EDGE-P1-2：資金費率極端且與信號方向一致時的信心加成（默認 0.08）。
    pub funding_rate_boost: f64,
    /// Confluence weights + thresholds (reversion profile, inverted ADX).
    /// 匯流權重 + 閾值（回歸配置，反轉 ADX）。
    pub weight_adx: f64,
    pub weight_regime: f64,
    pub weight_volume: f64,
    pub weight_momentum: f64,
    pub adx_floor: f64,
    pub adx_inverted: bool,
    pub confluence_threshold_no_trade: f64,
    pub confluence_threshold_light: f64,
    pub confluence_threshold_full: f64,
    /// G7-09c Phase 1: ticks INSIDE the inside quote at which the BBO-aware
    /// PostOnly limit sits. Default 1 (one tick more passive than best_bid/ask).
    /// When BBO or tick_size are unavailable, limit entries are skipped instead
    /// of falling back to last_price. Bounded `[0, 10]` by `validate()`. Note: GAP-9 currently
    /// force-disables `use_limit` in the runtime ctor (paper engine has no
    /// limit-order matcher), so this field is plumbing-only until GAP-9 lifts.
    /// G7-09c Phase 1：BBO-aware PostOnly 限價離 inside quote 的 tick 數，預設 1。
    /// BBO 或 tick_size 不可得時跳過限價入場，不再 fallback 到 last_price。
    /// `validate()` 限 `[0, 10]`。
    /// 注意：GAP-9 在 runtime ctor 強制關閉 `use_limit`，本欄位現為埋線；GAP-9 解禁後生效。
    #[serde(default = "default_maker_price_buffer_ticks_bbr")]
    pub maker_price_buffer_ticks: u32,

    /// W-AUDIT-6d #6 (AMD-2026-05-09-02 §3 verdict "pair bb_reversion with MA
    /// confirmation")：reversion 入場必經 MA 趨勢方向確認 gate，預設 `true`。
    /// 語義：long entry（oversold reversion）必 `price < ma_value`；short entry
    /// （overbought reversion）必 `price > ma_value`。若 MA 不可得（warm-up 不足）
    /// 一律 fail-closed 不入場（§二 原則 6 失敗默認收縮）。
    /// `false` 僅用於 W-AUDIT-9 stage rollback 路徑（grade-down 時放寬 gate；不
    /// 用於日常 demo/live runtime — operator 不應主動關此 gate）。
    /// 配套 `ma_confirmation_kind` 選 SMA20/SMA50/EMA12/EMA26。
    /// W-AUDIT-6d #6: pair MA confirmation gate. Default true. False only used
    /// for W-AUDIT-9 stage rollback paths.
    #[serde(default = "default_require_ma_confirmation")]
    pub require_ma_confirmation: bool,

    /// W-AUDIT-6d #6 — MA 種類選擇，default `"sma_50"`（中期趨勢過濾，與 ma_crossover
    /// RC-02 用法對齊）。Validate 限 `{"sma_20", "sma_50", "ema_12", "ema_26"}`。
    /// W-AUDIT-6d #6: MA selection for confirmation gate. Default "sma_50".
    #[serde(default = "default_ma_confirmation_kind")]
    pub ma_confirmation_kind: String,
}

/// W-AUDIT-6d #6 — MA pair confirmation 預設啟用（per AMD-2026-05-09-02 §3）。
fn default_require_ma_confirmation() -> bool {
    true
}

/// W-AUDIT-6d #6 — 預設 MA 種類為 SMA50（中期趨勢，與 ma_crossover RC-02 對齊）。
fn default_ma_confirmation_kind() -> String {
    "sma_50".to_string()
}

/// G7-09c Phase 1: default buffer = 1 tick (one tick inside the inside quote).
/// G7-09c Phase 1：預設 1 tick（退一 tick）。
fn default_maker_price_buffer_ticks_bbr() -> u32 {
    1
}

impl Default for BbReversionParams {
    fn default() -> Self {
        let cc = ConfluenceConfig::reversion();
        Self {
            cooldown_ms: 600_000,
            default_qty: 1e9,
            use_limit: false,
            limit_offset_bps: 10.0,
            rsi_oversold: 30.0,
            rsi_overbought: 70.0,
            hurst_regime_boost: 0.1,
            funding_rate_threshold: 0.0005,
            funding_rate_boost: 0.08,
            min_persistence_ms: 180_000,
            min_notional_usd: 10.0,
            weight_adx: cc.weight_adx,
            weight_regime: cc.weight_regime,
            weight_volume: cc.weight_volume,
            weight_momentum: cc.weight_momentum,
            adx_floor: cc.adx_floor,
            adx_inverted: true,
            confluence_threshold_no_trade: cc.threshold_no_trade,
            confluence_threshold_light: cc.threshold_light,
            confluence_threshold_full: cc.threshold_full,
            // G7-09c Phase 1: default 1 tick inside the inside quote.
            // G7-09c Phase 1：預設退一 tick。
            maker_price_buffer_ticks: 1,
            // W-AUDIT-6d #6 (AMD-2026-05-09-02 §3) — 預設啟用 MA pair confirmation。
            require_ma_confirmation: true,
            ma_confirmation_kind: "sma_50".to_string(),
        }
    }
}

impl StrategyParams for BbReversionParams {
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
                name: "default_qty".into(),
                min: 0.001,
                max: 1e12,
                step: None,
                agent_adjustable: false,
                db_persisted: true,
            },
            // GAP-9: use_limit / limit_offset_bps removed from agent-tunable
            // ranges. Paper engine has no order-book sim and silently degrades
            // limit→market, so enabling these would corrupt PnL accounting.
            // Re-add when paper engine grows a real limit-order matcher.
            // GAP-9：use_limit/limit_offset_bps 從可調列表移除（paper 無撮合）。
            ParamRange {
                name: "rsi_oversold".into(),
                min: 5.0,
                max: 45.0,
                step: Some(5.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "rsi_overbought".into(),
                min: 55.0,
                max: 95.0,
                step: Some(5.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "hurst_regime_boost".into(),
                min: 0.0,
                max: 0.3,
                step: Some(0.05),
                agent_adjustable: true,
                db_persisted: true,
            },
            // ── EDGE-P1-2: Funding rate signal params ──
            ParamRange {
                name: "funding_rate_threshold".into(),
                min: 0.0001,
                max: 0.005,
                step: Some(0.0001),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "funding_rate_boost".into(),
                min: 0.0,
                max: 0.2,
                step: Some(0.01),
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
            // W-AUDIT-6d #6 (AMD-2026-05-09-02 §3) — MA pair confirmation 是治理層
            // 強制 gate；agent 不可自關（agent_adjustable=false），W-AUDIT-9 stage
            // rollback 路徑或 operator 顯式批准才能切換。db_persisted=true 留歷史。
            ParamRange {
                name: "require_ma_confirmation".into(),
                min: 0.0,
                max: 1.0,
                step: Some(1.0),
                agent_adjustable: false,
                db_persisted: true,
            },
        ]
    }

    fn validate(&self) -> Result<(), String> {
        if self.cooldown_ms < 60_000 {
            return Err("cooldown_ms must be >= 60s".into());
        }
        if self.limit_offset_bps < 0.0 || self.limit_offset_bps > 200.0 {
            return Err("limit_offset_bps must be in [0, 200]".into());
        }
        if self.rsi_oversold < 5.0 || self.rsi_oversold > 45.0 {
            return Err("rsi_oversold must be in [5, 45]".into());
        }
        if self.rsi_overbought < 55.0 || self.rsi_overbought > 95.0 {
            return Err("rsi_overbought must be in [55, 95]".into());
        }
        if self.hurst_regime_boost < 0.0 || self.hurst_regime_boost > 0.3 {
            return Err("hurst_regime_boost must be in [0, 0.3]".into());
        }
        if self.funding_rate_threshold < 0.0001 || self.funding_rate_threshold > 0.005 {
            return Err("funding_rate_threshold must be in [0.0001, 0.005]".into());
        }
        if self.funding_rate_boost < 0.0 || self.funding_rate_boost > 0.2 {
            return Err("funding_rate_boost must be in [0, 0.2]".into());
        }
        // G-SR-1: Validate confluence weight sum = 65 / 驗證匯流權重總和 = 65
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
        // G7-09c Phase 1: bound BBO buffer (see field doc).
        // G7-09c Phase 1：限定 BBO buffer，防 IPC 寫入過大。
        if self.maker_price_buffer_ticks > 10 {
            return Err("maker_price_buffer_ticks must be <= 10".into());
        }
        // W-AUDIT-6d #6 (AMD-2026-05-09-02 §3) — MA confirmation kind whitelist。
        // 對齊 IndicatorSnapshot 的 sma_20 / sma_50 / ema_12 / ema_26 字段；
        // 其他值（含拼寫錯誤）拒絕，避免 silent fall-through 到「無 MA gate」。
        match self.ma_confirmation_kind.as_str() {
            "sma_20" | "sma_50" | "ema_12" | "ema_26" => {}
            other => {
                return Err(format!(
                    "ma_confirmation_kind must be one of \
                     {{sma_20, sma_50, ema_12, ema_26}}, got '{other}'"
                ));
            }
        }
        Ok(())
    }
}

impl BbReversionParams {
    /// Build ConfluenceConfig from flat params (reversion profile, inverted ADX).
    /// 從扁平參數構建 ConfluenceConfig（回歸配置，反轉 ADX）。
    pub fn build_confluence_config(&self) -> ConfluenceConfig {
        ConfluenceConfig {
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
