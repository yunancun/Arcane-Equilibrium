//! BB Breakout tunable parameters — struct definition, defaults, ranges, validation.
//! BB 突破可調參數 — 結構定義、預設值、參數範圍、驗證。
//!
//! MODULE_NOTE (EN): Holds `BbBreakoutParams` (Agent/TOML surface) + its
//!   `Default` + `StrategyParams` impls (ranges + validate). Split out from
//!   `mod.rs` so the strategy core can stay ≤ 800 soft warn. No runtime state
//!   lives here — only pure data + pure validation.
//! MODULE_NOTE (中): 放置 `BbBreakoutParams`（Agent/TOML 對外面）+ `Default` +
//!   `StrategyParams` 實作（ranges + validate）。從 `mod.rs` 拆出以保持核心 ≤ 800
//!   soft warn。此檔僅放純資料 + 純驗證，不含 runtime 狀態。

use super::super::confluence::ConfluenceConfig;
use super::super::{ParamRange, StrategyParams};
use serde::{Deserialize, Serialize};

/// Default bandwidth threshold to detect squeeze (壓縮帶寬閾值默認)
pub(super) const DEFAULT_SQUEEZE_BW: f64 = 0.03; // EDGE-P1-4: 0.02→0.03 (relax squeeze detection)
/// Default bandwidth threshold to detect expansion (擴張帶寬閾值默認)
pub(super) const DEFAULT_EXPANSION_BW: f64 = 0.04;
/// Default volume ratio threshold for breakout confirmation (成交量確認閾值默認)
pub(super) const DEFAULT_VOLUME_THRESHOLD: f64 = 1.2; // EDGE-P1-4: 1.5→1.2 (lower volume bar)

/// Tunable parameters for BB Breakout (Phase 3a).
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct BbBreakoutParams {
    pub cooldown_ms: u64,
    pub default_qty: f64,
    pub squeeze_bw: f64,
    pub expansion_bw: f64,
    pub volume_threshold: f64,
    pub trailing_stop_atr_mult: f64,
    /// FIX-26: Squeeze state expiry duration (ms). Default 30 min.
    /// FIX-26：壓縮狀態有效期（ms）。默認 30 分鐘。
    pub squeeze_expiry_ms: u64,
    // ── G-SR-1 confluence + persistence fields (A0-c) ──
    /// Minimum signal persistence before entry (ms). / 入場前信號最小持續時間（ms）。
    pub min_persistence_ms: u64,
    /// Minimum order notional (USD). / 最小訂單名義值（USD）。
    pub min_notional_usd: f64,
    /// Confluence as qty modifier only (not gate). / 匯流僅作為 qty 調整器（非門控）。
    pub confluence_as_gate: bool,
    /// Confluence weights + thresholds (breakout profile).
    pub weight_adx: f64,
    pub weight_regime: f64,
    pub weight_volume: f64,
    pub weight_momentum: f64,
    pub adx_floor: f64,
    pub confluence_threshold_no_trade: f64,
    pub confluence_threshold_light: f64,
    pub confluence_threshold_full: f64,
    // ── E5-P2-4: Previously hard-coded magic numbers lifted to config ──
    // ── E5-P2-4：原本 hard-coded 的魔術數字提升為 config 參數 ──
    /// Hurst trending regime entry confidence boost (default 0.1).
    /// Adds to entry confidence when Hurst regime == "trending".
    /// Hurst 趨勢狀態入場信心加成（默認 0.1）。當 Hurst regime == "trending" 時加到入場信心。
    pub hurst_regime_boost: f64,
    /// Exit confidence bonus for trailing stop hit (default 0.2).
    /// 追蹤止損觸發時的出場信心加成（默認 0.2）。
    pub exit_bonus_trailing_stop: f64,
    /// Exit confidence bonus for Hurst regime shift exit (default 0.1).
    /// Hurst regime 轉向出場時的信心加成（默認 0.1）。
    pub exit_bonus_regime_shift: f64,
    /// Exit confidence bonus for %B revert-to-middle exit (default 0.05).
    /// %B 回中軌出場時的信心加成（默認 0.05）。
    pub exit_bonus_pctb_revert: f64,
    /// Exit confidence penalty (magnitude, subtracted) for BW squeeze exit (default 0.05).
    /// BW 帶寬再壓縮出場時的信心扣減幅度（默認 0.05，實際套用時為減法）。
    pub exit_penalty_bw_squeeze: f64,
    // ── EDGE-P2-2: Open Interest confluence signal (experimental, default off) ──
    // ── EDGE-P2-2：OI 合流信號（實驗性，預設關閉） ──
    /// Master switch for OI confluence contribution. When `false`, strategy
    /// behaviour is bit-identical to the pre-EDGE-P2-2 baseline.
    /// OI 合流總開關；`false` 時策略行為與舊基線 bit-identical。
    pub enable_oi_signal: bool,
    /// Rolling window (ms) over which `oi_delta_pct` is measured.
    /// Typical 60_000 (~60s) — long enough to filter noise, short enough to
    /// capture pre-breakout positioning. Validated `[1_000, 600_000]` ms.
    /// OI 差分滾動窗口（ms）；典型 60_000，validate 要求 `[1_000, 600_000]`。
    pub oi_buffer_window_ms: u64,
    /// Bonus added/subtracted on the raw confluence score when OI confirms
    /// (add) or diverges from (subtract) the intended entry direction.
    /// Bounded within ±0.5 by `validate()` to cap influence.
    /// Score bands are `threshold_no_trade`(~30) → `light`(~40) → `full`(~45).
    /// Typical effective range 0.3-0.5 to move qty_pct by ≥5 pp; default 0.10
    /// is intentionally conservative for initial A/B without regime shocks.
    /// OI 合流加成（±）；validate 限制在 ±0.5 以控制影響幅度。
    /// 分數帶寬 no_trade(30)→light(40)→full(45)，典型有效區間 0.3-0.5 才能推動
    /// qty_pct ≥5 pp 改變；預設 0.10 偏保守，適合首次 A/B 不引入 regime 震盪。
    pub oi_confluence_bonus: f64,
    /// Minimum absolute `oi_delta_pct` magnitude required to apply the bonus.
    /// Below this threshold, OI modifier is a no-op (score passes through).
    /// Guards against WS snapshot quantisation noise (±1 contract → 1e-8 delta)
    /// being treated as a confirmation signal. Default 0.0 = pre-FUP behaviour
    /// (any non-zero delta triggers bonus). Validated in `[0.0, 0.5]`, finite.
    /// 觸發 bonus 所需的最小 `|oi_delta_pct|` 閾值；低於此值視為 no-op。
    /// 防止 WS 快照量化噪音（±1 張合約 ≈ 1e-8 delta）被誤判為確認信號。
    /// 預設 0.0 = pre-FUP 行為（任何非零 delta 即觸發）；validate `[0.0, 0.5]` finite。
    pub oi_min_delta_pct: f64,
    /// EDGE-P2-3 Phase 2+: emit PostOnly Limit entries to pay maker fees.
    /// Default `false` (root principle #6 — conservative cold-boot).
    /// EDGE-P2-3 Phase 2+：入場改發 PostOnly Limit 以支付 maker 費率；默認 false。
    pub use_maker_entry: bool,
    /// EDGE-P2-3 Phase 2+: bps offset from last_price for PostOnly limit placement.
    /// EDGE-P2-3 Phase 2+：PostOnly 限價偏移（bps）。
    pub maker_price_offset_bps: f64,
    /// EDGE-P2-3 Phase 2+: ms a resting PostOnly maker order may sit before the
    /// event_consumer sweep cancels it. Clamped to [15_000, 300_000] on assign.
    /// EDGE-P2-3 Phase 2+：PostOnly 掛單最長停留時間(毫秒)，寫入時 clamp。
    pub maker_limit_timeout_ms: u64,
}

impl Default for BbBreakoutParams {
    fn default() -> Self {
        let cc = ConfluenceConfig::breakout();
        Self {
            cooldown_ms: 300_000,
            default_qty: 1e9,
            squeeze_bw: DEFAULT_SQUEEZE_BW,
            expansion_bw: DEFAULT_EXPANSION_BW,
            volume_threshold: DEFAULT_VOLUME_THRESHOLD,
            trailing_stop_atr_mult: 2.0,
            squeeze_expiry_ms: 2_700_000, // EDGE-P1-4: 30min→45min
            min_persistence_ms: 60_000,   // 1 min (triple gate already strict)
            min_notional_usd: 10.0,
            confluence_as_gate: false,
            weight_adx: cc.weight_adx,
            weight_regime: cc.weight_regime,
            weight_volume: cc.weight_volume,
            weight_momentum: cc.weight_momentum,
            adx_floor: cc.adx_floor,
            confluence_threshold_no_trade: cc.threshold_no_trade,
            confluence_threshold_light: cc.threshold_light,
            confluence_threshold_full: cc.threshold_full,
            // E5-P2-4: preserve exact pre-extraction values (bit-exact behaviour)
            // E5-P2-4：保留原始 hard-coded 值（維持 bit-exact 行為）
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
            // EDGE-P2-2 FUP: min_delta default 0.0 preserves pre-FUP semantics
            // (any non-zero delta applies bonus). Operators can raise this to
            // filter WS quantisation noise without changing the flag default.
            // EDGE-P2-2 FUP：min_delta 預設 0.0 保留 pre-FUP 語義；operator 可調高過濾 WS 噪音。
            oi_min_delta_pct: 0.0,
            // EDGE-P2-3 Phase 2+: conservative cold-boot (root principle #6).
            // EDGE-P2-3 Phase 2+：冷啟動保守默認（根原則 #6）。
            use_maker_entry: false,
            maker_price_offset_bps: 1.0,
            maker_limit_timeout_ms: 45_000,
        }
    }
}

impl StrategyParams for BbBreakoutParams {
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
                name: "squeeze_bw".into(),
                min: 0.005,
                max: 0.05,
                step: None,
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "expansion_bw".into(),
                min: 0.02,
                max: 0.1,
                step: None,
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "volume_threshold".into(),
                min: 1.0,
                max: 5.0,
                step: Some(0.1),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "trailing_stop_atr_mult".into(),
                min: 1.0,
                max: 5.0,
                step: Some(0.5),
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
                name: "confluence_as_gate".into(),
                min: 0.0,
                max: 1.0,
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
            // EDGE-P2-2: Open Interest confluence signal parameters.
            // EDGE-P2-2：OI 合流信號參數。
            ParamRange {
                name: "enable_oi_signal".into(),
                min: 0.0,
                max: 1.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "oi_buffer_window_ms".into(),
                min: 1_000.0,
                max: 600_000.0,
                step: Some(1_000.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "oi_confluence_bonus".into(),
                min: -0.5,
                max: 0.5,
                step: Some(0.01),
                agent_adjustable: true,
                db_persisted: true,
            },
            // EDGE-P2-2 FUP: minimum delta threshold to apply bonus.
            // EDGE-P2-2 FUP：觸發 bonus 的最小 delta 閾值。
            ParamRange {
                name: "oi_min_delta_pct".into(),
                min: 0.0,
                max: 0.5,
                step: Some(0.001),
                agent_adjustable: true,
                db_persisted: true,
            },
        ]
    }

    fn validate(&self) -> Result<(), String> {
        if self.squeeze_bw >= self.expansion_bw {
            return Err("squeeze_bw must be < expansion_bw".into());
        }
        if self.volume_threshold < 1.0 {
            return Err("volume_threshold must be >= 1.0".into());
        }
        if self.trailing_stop_atr_mult < 0.5 {
            return Err("trailing_stop_atr_mult must be >= 0.5".into());
        }
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
        // EDGE-P2-2: OI signal parameter validation.
        // - Window must be within `[1_000, 600_000]` ms. Lower bound blocks
        //   sub-second windows dominated by WS jitter; upper bound (matches
        //   `param_ranges.max`) prevents a hostile IPC write from requesting
        //   `u64::MAX`, which combined with a high-frequency ticker stream
        //   would let `oi_buffer` grow without bound (no element cap).
        // - Bonus must be finite and magnitude <= 0.5 to bound score influence.
        // - Min-delta threshold must be finite, non-negative, and <= 0.5.
        // EDGE-P2-2：OI 信號參數驗證。
        // - 窗口 `[1_000, 600_000]`：下限擋亞秒窗口 jitter，上限擋 IPC 惡意寫入
        //   `u64::MAX` 導致 buffer 無界成長（VecDeque 無元素上限）。
        // - bonus finite 且 |·| ≤ 0.5；min_delta finite 且 `[0.0, 0.5]`。
        if self.oi_buffer_window_ms < 1_000 || self.oi_buffer_window_ms > 600_000 {
            return Err("oi_buffer_window_ms must be within [1000, 600000]".into());
        }
        if !self.oi_confluence_bonus.is_finite() || self.oi_confluence_bonus.abs() > 0.5 {
            return Err("oi_confluence_bonus must be finite and within ±0.5".into());
        }
        if !self.oi_min_delta_pct.is_finite()
            || self.oi_min_delta_pct < 0.0
            || self.oi_min_delta_pct > 0.5
        {
            return Err("oi_min_delta_pct must be finite and within [0.0, 0.5]".into());
        }
        Ok(())
    }
}

impl BbBreakoutParams {
    /// Build ConfluenceConfig (breakout profile: qty modifier only, non-inverted ADX).
    /// 構建 ConfluenceConfig（突破配置：僅 qty 調整器，非反轉 ADX）。
    pub fn build_confluence_config(&self) -> ConfluenceConfig {
        ConfluenceConfig {
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
