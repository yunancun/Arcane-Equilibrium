//! `FlashDipBuyParams` — TOML schema + `StrategyParams` impl + 純函式核心。
//!
//! MODULE_NOTE：
//!   模塊用途：flash-crash dip-buy demo pilot 的 TOML 載入結構、Optuna/Agent 可調
//!     參數聲明，以及策略本體（`mod.rs`）依賴的「無引擎依賴純函式」核心
//!     （E1-A）：dip level 計算、bounded demo near-touch limit 計算、UTC 日首 tick
//!     判定、N 日 hold 到期判定、固定名目 qty 計算。
//!   主要類/函數：FlashDipBuyParams、StrategyParams::param_ranges / validate、
//!     compute_dip_level / is_first_tick_of_utc_day / hold_expired / fixed_notional_qty。
//!   依賴：serde、super::ParamRange + StrategyParams trait（透過 `crate::strategies`）。
//!   硬邊界：
//!     - `active` 預設 false：demo-only pilot；env flag OFF + active=false 雙鎖
//!       fail-closed（對齊 funding_harvest / liquidation_cascade_fade 範式）。
//!     - `notional_frac` 上限 0.03（3% equity）：與 band-external RiskConfig
//!       `limits.flash_dip_buy_max_notional_pct_equity` cap 同義；validate() 拒
//!       > 0.03 或 <= 0，使 TOML 載入路徑也 fail-closed（cap 是真 backstop，但
//!       此處先擋住明顯誤配）。
//!     - `hold_days` 固定研究面板 N=3（day-clustered exit 對齊回測）。
//!     - `k_dip` 靜態深價深度（K=0.15 預設）：prior_close*(1-K) maker limit。
//!     - `allowed_symbols` = 研究面板 26 存活兩年大-cap（survivor universe）；
//!       pilot 自有 list，與 scanner_config.toml 的 25 不同用途。
//!   research ref:
//!     - srv/docs/CCAgentWorkSpace/Operator/2026-06-18--PA--flash-crash-dipbuy-demo-pilot-design.md
//!     - /tmp/openclaw/research/tail_dislocation_meanrev/extend_full.json
//!       (universe_composition.symbols, n=26, n_possibly_delisted=0)

use serde::{Deserialize, Serialize};

use crate::strategies::params::{ParamRange, StrategyParams};

// ──────────────────────────────────────────────────────────────────────────
// 預設常量：與研究面板 best survival-safe / 對齊 Q7 單 tranche 配置
// （K=0.15 / N=3 / C=3 / notional_frac=0.02）對齊
// ──────────────────────────────────────────────────────────────────────────

/// 靜態深價深度 K（prior_close*(1-K)）；Q7 單 tranche 預設 0.15。
pub const DEFAULT_K_DIP: f64 = 0.15;

/// hold 持有天數 N；研究面板 day-clustered exit 預設 3 日。
pub const DEFAULT_HOLD_DAYS: u32 = 3;

/// 並發上限 C（producer-side 軟層；硬層由 per_strategy.max_concurrent_positions 守）。
/// Q7 單 tranche 預設 3。
pub const DEFAULT_MAX_CONCURRENT: u32 = 3;

/// 固定名目佔 equity 比例（nf）；預設 0.02 = 2%。
///
/// 為什麼預設 0.02 而非研究面板的 0.2：研究面板的 notional_frac=0.2 是「無 stop +
/// survivor-biased universe」的樂觀上限；pilot 採保守 2%，且硬上限受 band-external
/// `limits.flash_dip_buy_max_notional_pct_equity`(<=3%) + 通用 P1 per_trade_risk_pct(2%)
/// + position_size_max_pct 三重夾擊。survival floor 記在通用 cap，不記在此欄。
pub const DEFAULT_NOTIONAL_FRAC: f64 = 0.02;

/// nf 硬上限（validate 拒 > 此值）；與 RiskConfig band-external cap 同義 3%。
pub const MAX_NOTIONAL_FRAC: f64 = 0.03;

/// Demo fill-discovery 模式：PostOnly BUY 掛在當前 last price 下方 `offset_bps`。
/// 預設 10bps，目標是產生 demo fill/fee/slippage 樣本，而不是繼續掛 15% 深價 no-touch。
pub const DEFAULT_NEAR_TOUCH_OFFSET_BPS: f64 = 10.0;

/// near-touch offset 的硬範圍：太小容易跨價/吃單，太大又回到 no-touch。
pub const MIN_NEAR_TOUCH_OFFSET_BPS: f64 = 1.0;
pub const MAX_NEAR_TOUCH_OFFSET_BPS: f64 = 50.0;

/// PostOnly maker 掛單逾時：日終撤單由 maker_timeout_ms 觸發既有 sweep。
/// 預設 6h（pilot daily cadence；on_tick 在 emit 時用「距 UTC 日終」精算覆寫）。
pub const DEFAULT_MAKER_TIMEOUT_MS: u64 = 6 * 60 * 60_000;

/// 一個 UTC 日的毫秒數。
pub const MS_PER_UTC_DAY: u64 = 86_400_000;

/// 研究面板 26 存活兩年大-cap survivor universe。
/// 來源：extend_full.json `universe_composition.symbols`（n=26, n_possibly_delisted=0），
/// 與 `overlap_validation`（全 730-bar 0-mismatch）逐一吻合。pilot 自有 list。
pub fn default_allowed_symbols() -> Vec<String> {
    [
        "ADAUSDT", "APTUSDT", "ARBUSDT", "ATOMUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "BTCUSDT",
        "DOGEUSDT", "DOTUSDT", "ETCUSDT", "ETHUSDT", "FILUSDT", "ICPUSDT", "INJUSDT", "LINKUSDT",
        "LTCUSDT", "NEARUSDT", "OPUSDT", "POLUSDT", "SOLUSDT", "SUIUSDT", "TONUSDT", "TRXUSDT",
        "UNIUSDT", "XRPUSDT",
    ]
    .iter()
    .map(|s| s.to_string())
    .collect()
}

// ──────────────────────────────────────────────────────────────────────────
// E1-A 純函式核心（無引擎依賴，獨立可測）
// ──────────────────────────────────────────────────────────────────────────

/// 計算靜態深價 maker limit 入場價 = prior_close*(1-k)。
///
/// 為什麼純函式：dip level 是入場核心數學，與引擎狀態無關，必須獨立可測，
/// 避免在 on_tick 內混入難測的 side-effect。
/// 不變量：prior_close 須 finite 且 > 0、k ∈ (0, 1)，否則回 None（呼叫端 fail-closed）。
pub fn compute_dip_level(prior_close: f64, k: f64) -> Option<f64> {
    if !prior_close.is_finite() || prior_close <= 0.0 {
        return None;
    }
    if !k.is_finite() || !(0.0..1.0).contains(&k) || k <= 0.0 {
        return None;
    }
    let level = prior_close * (1.0 - k);
    if level.is_finite() && level > 0.0 {
        Some(level)
    } else {
        None
    }
}

/// 計算 bounded demo near-touch PostOnly BUY limit。
///
/// 不變量：limit 必須嚴格低於當前 last price，避免策略主動跨價；offset 只允許
/// [1, 50]bps，讓 demo 探針靠近 touch 以收集 fill/fee/slippage，同時保留 maker
/// 邊界和小額風控。
pub fn compute_bounded_near_touch_limit(last_price: f64, offset_bps: f64) -> Option<f64> {
    if !last_price.is_finite() || last_price <= 0.0 {
        return None;
    }
    if !offset_bps.is_finite()
        || !(MIN_NEAR_TOUCH_OFFSET_BPS..=MAX_NEAR_TOUCH_OFFSET_BPS).contains(&offset_bps)
    {
        return None;
    }
    let level = last_price * (1.0 - offset_bps / 10_000.0);
    if level.is_finite() && level > 0.0 && level < last_price {
        Some(level)
    } else {
        None
    }
}

/// 判定 `now_ms`（wall-clock 毫秒）落在的 UTC 日是否嚴格晚於 `last_acted_day`。
///
/// 為什麼用「UTC 日索引嚴格大於」：daily cadence 只在「UTC 日首次見到的 tick」
/// 武裝入場，當日後續 tick no-op。`last_acted_day` 為上次武裝的 UTC 日索引
/// （`ms / 86_400_000`）；回傳 (是否首 tick, 當前 UTC 日索引)。
///
/// 不變量（折入 memory 2026-06-15 Fix-4 教訓）：呼叫端必須傳 **wall-clock** 毫秒
/// （`openclaw_core::now_ms()`），**禁** 傳 payload-ts（`event.ts_ms` 曾誤存 payload
/// 時間致 cadence 污染）。本純函式不取時鐘，時鐘來源由呼叫端負責。
/// `last_acted_day` 用 i64 且預設 -1（「從未行動」嚴格小於任何 UTC 日索引 >= 0）。
pub fn is_first_tick_of_utc_day(now_wall_ms: u64, last_acted_day: i64) -> (bool, i64) {
    let today = (now_wall_ms / MS_PER_UTC_DAY) as i64;
    (today > last_acted_day, today)
}

/// 判定 N 日 hold 是否已到期（now - entry >= N 日）。
///
/// 為什麼用 wall-clock + entry_ts：hold 從 `PaperPosition.entry_ts_ms` 起算；
/// 但 Bybit demo snapshot 的 entry_ts 不可靠（見 mod.rs Q2 caveat），故策略另持
/// 自有 entry_ts checkpoint。本純函式只做時間差比較，時鐘來源由呼叫端負責。
/// 不變量：now < entry（時鐘倒退/壞 entry）→ false（不平倉，fail-safe 保守）。
pub fn hold_expired(now_wall_ms: u64, entry_ts_ms: u64, hold_days: u32) -> bool {
    if now_wall_ms < entry_ts_ms {
        return false;
    }
    let hold_ms = (hold_days as u64).saturating_mul(MS_PER_UTC_DAY);
    now_wall_ms - entry_ts_ms >= hold_ms
}

/// 固定名目 sizing：qty = (equity * notional_frac) / price。
///
/// 為什麼固定名目而非 stop-anchored：研究面板顯示 stop-anchored sizing 在 falling-knife
/// 尾部放大 death-spiral；固定名目減弱此效應（survival-safe variant §改良）。
/// 不變量：equity/price 須 finite 且 > 0、notional_frac ∈ (0, MAX_NOTIONAL_FRAC]，
/// 否則回 None（呼叫端 fail-closed）。注意：本函式只算「策略目標 qty」，真正的
/// survival floor 由 gate stack 的通用 P1(2%)/position_size + band-external cap 強制，
/// 策略目標 qty 只會被 min() 夾小、永不放寬。
pub fn fixed_notional_qty(equity: f64, notional_frac: f64, price: f64) -> Option<f64> {
    if !equity.is_finite() || equity <= 0.0 {
        return None;
    }
    if !price.is_finite() || price <= 0.0 {
        return None;
    }
    if !notional_frac.is_finite() || notional_frac <= 0.0 || notional_frac > MAX_NOTIONAL_FRAC {
        return None;
    }
    let qty = (equity * notional_frac) / price;
    if qty.is_finite() && qty > 0.0 {
        Some(qty)
    } else {
        None
    }
}

// ──────────────────────────────────────────────────────────────────────────
// FlashDipBuyParams（TOML schema + Optuna search 表面）
// ──────────────────────────────────────────────────────────────────────────

/// flash_dip_buy demo pilot 策略的 TOML / IPC schema。
///
/// 透過 `StrategyParamsConfig.flash_dip_buy` 接線到 `strategy_params_demo.toml`
/// `[flash_dip_buy]` block（pilot 為 demo-only，paper/live TOML 不含此 block）。
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct FlashDipBuyParams {
    /// 啟用開關；fail-closed 默認 false（+ env flag 雙鎖）。
    pub active: bool,

    /// 靜態深價深度 K（prior_close*(1-K)）。
    pub k_dip: f64,

    /// hold 持有天數 N（day-clustered exit）。
    pub hold_days: u32,

    /// 並發上限 C（producer-side 軟層；硬層 = per_strategy.max_concurrent_positions）。
    pub max_concurrent: u32,

    /// 固定名目佔 equity 比例（nf）；硬上限 MAX_NOTIONAL_FRAC=0.03。
    pub notional_frac: f64,

    /// Demo bounded fill-discovery：用 near-touch PostOnly 代替 15% 深價 no-touch。
    pub bounded_demo_near_touch: bool,

    /// near-touch 掛單距當前 last price 的 bps offset。
    pub near_touch_offset_bps: f64,

    /// 研究面板 26 survivor universe（pilot 自有 list）。
    pub allowed_symbols: Vec<String>,
}

impl Default for FlashDipBuyParams {
    fn default() -> Self {
        Self {
            active: false,
            k_dip: DEFAULT_K_DIP,
            hold_days: DEFAULT_HOLD_DAYS,
            max_concurrent: DEFAULT_MAX_CONCURRENT,
            notional_frac: DEFAULT_NOTIONAL_FRAC,
            bounded_demo_near_touch: true,
            near_touch_offset_bps: DEFAULT_NEAR_TOUCH_OFFSET_BPS,
            allowed_symbols: default_allowed_symbols(),
        }
    }
}

impl StrategyParams for FlashDipBuyParams {
    /// Optuna / Agent 可調參數範圍宣告。
    /// `active` / `allowed_symbols` 為控制表面，不入 search space。
    fn param_ranges() -> Vec<ParamRange> {
        vec![
            ParamRange {
                name: "k_dip".into(),
                min: 0.05,
                max: 0.30,
                step: Some(0.01),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "hold_days".into(),
                min: 1.0,
                max: 7.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "max_concurrent".into(),
                min: 1.0,
                max: 10.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "notional_frac".into(),
                min: 0.005,
                // search 上限即硬上限 0.03（band-external cap 同義）。
                max: MAX_NOTIONAL_FRAC,
                step: Some(0.005),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "near_touch_offset_bps".into(),
                min: MIN_NEAR_TOUCH_OFFSET_BPS,
                max: MAX_NEAR_TOUCH_OFFSET_BPS,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
        ]
    }

    /// 全範圍校驗 + 業務不變量校驗。
    /// 為什麼 fail-closed：TOML 載入 / IPC patch 路徑必須在 strategy 接收前擋住
    /// NaN / Inf / 越界 nf；尤其 notional_frac 不可 > 0.03（與 band-external
    /// survival cap 同義，雙層防 widen）。
    fn validate(&self) -> Result<(), String> {
        if !self.k_dip.is_finite() || !(0.05..=0.30).contains(&self.k_dip) {
            return Err(format!("k_dip={} must be in [0.05, 0.30]", self.k_dip));
        }
        if !(1..=7).contains(&self.hold_days) {
            return Err(format!("hold_days={} must be in [1, 7]", self.hold_days));
        }
        if !(1..=10).contains(&self.max_concurrent) {
            return Err(format!(
                "max_concurrent={} must be in [1, 10]",
                self.max_concurrent
            ));
        }
        if !self.notional_frac.is_finite()
            || self.notional_frac <= 0.0
            || self.notional_frac > MAX_NOTIONAL_FRAC
        {
            return Err(format!(
                "notional_frac={} must be in (0, {MAX_NOTIONAL_FRAC}]",
                self.notional_frac
            ));
        }
        if self.allowed_symbols.is_empty() {
            return Err("allowed_symbols must not be empty".into());
        }
        if !self.near_touch_offset_bps.is_finite()
            || !(MIN_NEAR_TOUCH_OFFSET_BPS..=MAX_NEAR_TOUCH_OFFSET_BPS)
                .contains(&self.near_touch_offset_bps)
        {
            return Err(format!(
                "near_touch_offset_bps={} must be in [{MIN_NEAR_TOUCH_OFFSET_BPS}, {MAX_NEAR_TOUCH_OFFSET_BPS}]",
                self.near_touch_offset_bps
            ));
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // ── 純函式：compute_dip_level ──

    #[test]
    fn dip_level_basic_math() {
        // prior_close 100, K=0.15 → 85。
        let lvl = compute_dip_level(100.0, 0.15).unwrap();
        assert!((lvl - 85.0).abs() < 1e-9);
        // K=0.20 → 80。
        assert!((compute_dip_level(100.0, 0.20).unwrap() - 80.0).abs() < 1e-9);
    }

    #[test]
    fn dip_level_rejects_bad_inputs() {
        assert!(compute_dip_level(0.0, 0.15).is_none());
        assert!(compute_dip_level(-100.0, 0.15).is_none());
        assert!(compute_dip_level(f64::NAN, 0.15).is_none());
        assert!(compute_dip_level(100.0, 0.0).is_none());
        assert!(compute_dip_level(100.0, 1.0).is_none()); // k>=1 → level<=0
        assert!(compute_dip_level(100.0, -0.1).is_none());
        assert!(compute_dip_level(100.0, f64::INFINITY).is_none());
    }

    #[test]
    fn bounded_near_touch_limit_basic_math() {
        // last 59000, offset 10bps → 58941，且嚴格低於 last。
        let lvl = compute_bounded_near_touch_limit(59_000.0, 10.0).unwrap();
        assert!((lvl - 58_941.0).abs() < 1e-9);
        assert!(lvl < 59_000.0);
    }

    #[test]
    fn bounded_near_touch_rejects_bad_inputs() {
        assert!(compute_bounded_near_touch_limit(0.0, 10.0).is_none());
        assert!(compute_bounded_near_touch_limit(-1.0, 10.0).is_none());
        assert!(compute_bounded_near_touch_limit(f64::NAN, 10.0).is_none());
        assert!(compute_bounded_near_touch_limit(100.0, 0.5).is_none());
        assert!(compute_bounded_near_touch_limit(100.0, 100.0).is_none());
        assert!(compute_bounded_near_touch_limit(100.0, f64::NAN).is_none());
    }

    // ── 純函式：is_first_tick_of_utc_day（UTC 日邊界 edge）──

    #[test]
    fn first_tick_of_day_strict_greater() {
        // last_acted = -1（從未行動）→ 任何日皆首 tick。
        let (first, day) = is_first_tick_of_utc_day(0, -1);
        assert!(first);
        assert_eq!(day, 0);
        // 同日後續 tick：last_acted = day → no-op。
        let (first2, day2) = is_first_tick_of_utc_day(MS_PER_UTC_DAY + 1, 0);
        // MS_PER_UTC_DAY+1 → day 1 > 0 → 首 tick。
        assert!(first2);
        assert_eq!(day2, 1);
        // 嚴格大於：同日 index 不觸發。
        let (first3, _) = is_first_tick_of_utc_day(MS_PER_UTC_DAY + 999, 1);
        assert!(!first3);
    }

    #[test]
    fn first_tick_utc_midnight_boundary() {
        // 1970-01-02 00:00:00.000 UTC = MS_PER_UTC_DAY → day 1。
        let (_, day) = is_first_tick_of_utc_day(MS_PER_UTC_DAY, -1);
        assert_eq!(day, 1);
        // 1970-01-01 23:59:59.999 UTC → 仍 day 0。
        let (_, day0) = is_first_tick_of_utc_day(MS_PER_UTC_DAY - 1, -1);
        assert_eq!(day0, 0);
        // 跨午夜：last_acted=0（昨日已動）, now 進入 day 1 首 tick。
        let (first, day1) = is_first_tick_of_utc_day(MS_PER_UTC_DAY, 0);
        assert!(first);
        assert_eq!(day1, 1);
    }

    #[test]
    fn first_tick_restart_same_day_no_double_arm() {
        // 重啟日：last_acted 已是今日 index（從 checkpoint 還原）→ 不重複武裝。
        let today = 20_000_i64; // 任意 UTC 日索引
        let now = (today as u64) * MS_PER_UTC_DAY + 12 * 60 * 60_000; // 當日中午
        let (first, day) = is_first_tick_of_utc_day(now, today);
        assert!(!first);
        assert_eq!(day, today);
    }

    // ── 純函式：hold_expired ──

    #[test]
    fn hold_expired_exact_and_boundary() {
        let entry = 1_000_000_u64;
        // N=3 日；剛好 3 日 → 到期（>=）。
        assert!(hold_expired(entry + 3 * MS_PER_UTC_DAY, entry, 3));
        // 差 1ms 未滿 3 日 → 未到期。
        assert!(!hold_expired(entry + 3 * MS_PER_UTC_DAY - 1, entry, 3));
        // 超過 → 到期。
        assert!(hold_expired(entry + 5 * MS_PER_UTC_DAY, entry, 3));
    }

    #[test]
    fn hold_expired_clock_regression_failsafe() {
        // now < entry（時鐘倒退/壞 entry）→ 不平倉（保守 fail-safe）。
        assert!(!hold_expired(500, 1000, 3));
    }

    // ── 純函式：fixed_notional_qty ──

    #[test]
    fn fixed_notional_qty_basic() {
        // equity 10000, nf 0.02, price 100 → notional 200 → qty 2。
        let q = fixed_notional_qty(10_000.0, 0.02, 100.0).unwrap();
        assert!((q - 2.0).abs() < 1e-9);
    }

    #[test]
    fn fixed_notional_qty_rejects_bad_inputs() {
        assert!(fixed_notional_qty(0.0, 0.02, 100.0).is_none());
        assert!(fixed_notional_qty(10_000.0, 0.02, 0.0).is_none());
        assert!(fixed_notional_qty(10_000.0, 0.0, 100.0).is_none());
        // nf > 0.03 硬上限 → reject（防 widen）。
        assert!(fixed_notional_qty(10_000.0, 0.05, 100.0).is_none());
        assert!(fixed_notional_qty(f64::NAN, 0.02, 100.0).is_none());
        assert!(fixed_notional_qty(10_000.0, f64::NAN, 100.0).is_none());
    }

    // ── params validate ──

    #[test]
    fn default_params_validate() {
        let p = FlashDipBuyParams::default();
        assert!(p.validate().is_ok());
        assert!(!p.active);
        assert_eq!(p.allowed_symbols.len(), 26);
        assert!((p.k_dip - 0.15).abs() < 1e-9);
        assert_eq!(p.hold_days, 3);
        assert_eq!(p.max_concurrent, 3);
        assert!((p.notional_frac - 0.02).abs() < 1e-9);
        assert!(p.bounded_demo_near_touch);
        assert!((p.near_touch_offset_bps - DEFAULT_NEAR_TOUCH_OFFSET_BPS).abs() < 1e-9);
    }

    #[test]
    fn rejects_notional_frac_over_cap() {
        let p = FlashDipBuyParams {
            notional_frac: 0.05, // > 0.03 hard cap
            ..Default::default()
        };
        assert!(p.validate().is_err());
        let p2 = FlashDipBuyParams {
            notional_frac: 0.0,
            ..Default::default()
        };
        assert!(p2.validate().is_err());
        // 邊界 0.03 恰好通過。
        let p3 = FlashDipBuyParams {
            notional_frac: 0.03,
            ..Default::default()
        };
        assert!(p3.validate().is_ok());
    }

    #[test]
    fn rejects_out_of_range_k_and_hold() {
        assert!(FlashDipBuyParams {
            k_dip: 0.01,
            ..Default::default()
        }
        .validate()
        .is_err());
        assert!(FlashDipBuyParams {
            k_dip: 0.5,
            ..Default::default()
        }
        .validate()
        .is_err());
        assert!(FlashDipBuyParams {
            hold_days: 0,
            ..Default::default()
        }
        .validate()
        .is_err());
        assert!(FlashDipBuyParams {
            hold_days: 99,
            ..Default::default()
        }
        .validate()
        .is_err());
    }

    #[test]
    fn rejects_empty_allowed_symbols() {
        let p = FlashDipBuyParams {
            allowed_symbols: vec![],
            ..Default::default()
        };
        assert!(p.validate().is_err());
    }

    #[test]
    fn rejects_near_touch_offset_out_of_range() {
        assert!(FlashDipBuyParams {
            near_touch_offset_bps: 0.5,
            ..Default::default()
        }
        .validate()
        .is_err());
        assert!(FlashDipBuyParams {
            near_touch_offset_bps: 51.0,
            ..Default::default()
        }
        .validate()
        .is_err());
        assert!(FlashDipBuyParams {
            near_touch_offset_bps: 10.0,
            ..Default::default()
        }
        .validate()
        .is_ok());
    }

    #[test]
    fn param_ranges_well_formed() {
        let ranges = FlashDipBuyParams::param_ranges();
        let names: std::collections::HashSet<_> = ranges.iter().map(|r| r.name.as_str()).collect();
        for required in [
            "k_dip",
            "hold_days",
            "max_concurrent",
            "notional_frac",
            "near_touch_offset_bps",
        ] {
            assert!(names.contains(required), "missing param: {required}");
        }
        // 控制表面不入 search space。
        assert!(!names.contains("active"));
        assert!(!names.contains("allowed_symbols"));
        // notional_frac search 上限 == 硬上限（防 search 提出 > cap 的值）。
        let nf = ranges.iter().find(|r| r.name == "notional_frac").unwrap();
        assert!((nf.max - MAX_NOTIONAL_FRAC).abs() < 1e-12);
    }

    #[test]
    fn allowed_symbols_match_research_universe() {
        // 26 survivor universe 完整性（extend_full.json universe_composition）。
        let syms = default_allowed_symbols();
        assert_eq!(syms.len(), 26);
        // 抽查代表性 symbol。
        for s in [
            "BTCUSDT", "ETHUSDT", "POLUSDT", "SUIUSDT", "TONUSDT", "INJUSDT",
        ] {
            assert!(
                syms.contains(&s.to_string()),
                "missing survivor symbol: {s}"
            );
        }
    }
}
