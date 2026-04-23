//! BB Breakout Strategy V2 — Squeeze→Expansion + Volume + Donchian + ATR trailing stop + Regime exit.
//! BB 突破策略 V2 — 壓縮→擴張 + 成交量 + Donchian + ATR 追蹤止損 + Regime 出場。
//!
//! MODULE_NOTE (EN): Detects Bollinger Band squeeze→expansion with volume
//!   confirmation and Donchian channel breakout. ATR-based trailing stop for exits.
//! MODULE_NOTE (中): 檢測布林帶壓縮→擴張 + 成交量確認 + Donchian 通道突破。
//!   ATR 追蹤止損出場。

use std::collections::HashMap;

use super::common::{PerSymbolState, TrendCooldown};
use super::confluence::{self, ConfluenceConfig, PersistenceTracker};
use super::{ParamRange, Strategy, StrategyAction, StrategyParams};
use crate::intent_processor::OrderIntent;
use crate::order_manager::TimeInForce;
use crate::tick_pipeline::TickContext;
use serde::{Deserialize, Serialize};
use tracing::info;

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
    /// EDGE-P2-3 Phase 2+：PostOnly 掛單最長停留時間（毫秒），寫入時 clamp。
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

/// Default bandwidth threshold to detect squeeze (壓縮帶寬閾值默認)
const DEFAULT_SQUEEZE_BW: f64 = 0.03; // EDGE-P1-4: 0.02→0.03 (relax squeeze detection)
/// Default bandwidth threshold to detect expansion (擴張帶寬閾值默認)
const DEFAULT_EXPANSION_BW: f64 = 0.04;
/// Default volume ratio threshold for breakout confirmation (成交量確認閾值默認)
const DEFAULT_VOLUME_THRESHOLD: f64 = 1.2; // EDGE-P1-4: 1.5→1.2 (lower volume bar)

/// Per-symbol dynamic state for `BbBreakout`. All fields are independently
/// optional: absence of a squeeze, an entry-price, or a trailing-stop each have
/// distinct meanings from "no position". `Default` → all `None`, matching the
/// behaviour of the previous 4 parallel `HashMap`s.
/// `BbBreakout` 的逐 symbol 動態狀態；4 個欄位各自獨立可選，等價於原先 4 個平行
/// HashMap 的語意。`Default` = 全 `None`，對應「從未見過該 symbol」。
#[derive(Debug, Clone, Default)]
pub(crate) struct BbBreakoutPerSymbolState {
    /// Current position direction if open: `Some(true)` = long, `Some(false)` = short.
    /// 當前方向：Some(true)=多, Some(false)=空, None=空倉。
    pub position: Option<bool>,
    /// First timestamp squeeze was detected (FIX-26 expiry window anchor).
    /// FIX-26：首次偵測壓縮的時間戳（作為 squeeze_expiry_ms 的錨點）。
    pub squeeze_detected_ms: Option<u64>,
    /// Entry price at position open (for PnL/trail math).
    /// 開倉價（供 PnL/追蹤止損計算）。
    pub entry_price: Option<f64>,
    /// Current ATR trailing stop level.
    /// 當前 ATR 追蹤止損價位。
    pub trailing_stop: Option<f64>,
    /// EDGE-P2-2: rolling (ts_ms, open_interest) samples. Front = oldest,
    /// back = newest. Maintained by `on_tick`; only pushed when
    /// `ctx.open_interest` is `Some`. Window length is controlled by
    /// `BbBreakout.oi_buffer_window_ms`.
    /// EDGE-P2-2：滾動 (ts_ms, OI) 樣本；front=最舊、back=最新。
    /// 只在 `ctx.open_interest` 有值時追加；窗口長度由 `oi_buffer_window_ms` 控制。
    pub oi_buffer: std::collections::VecDeque<(u64, f64)>,
}

impl BbBreakoutPerSymbolState {
    /// EDGE-P2-2: compute the fractional change of open interest between the
    /// oldest and newest buffer samples. Returns `None` when:
    ///   * fewer than 2 samples,
    ///   * oldest sample ≤ 0.0 (guard against div-by-zero / non-positive OI).
    /// Formula: (newest - oldest) / oldest.
    /// EDGE-P2-2：以 buffer 最舊與最新樣本計算 OI 變化百分比；
    /// < 2 個樣本或最舊 ≤ 0 則回 `None`（避免除以零）。
    pub fn compute_oi_delta_pct(&self) -> Option<f64> {
        if self.oi_buffer.len() < 2 {
            return None;
        }
        let oldest = self.oi_buffer.front().map(|(_, oi)| *oi)?;
        let newest = self.oi_buffer.back().map(|(_, oi)| *oi)?;
        if oldest <= 0.0 {
            return None;
        }
        Some((newest - oldest) / oldest)
    }
}

pub struct BbBreakout {
    active: bool,
    /// Per-symbol state (position/squeeze/entry_price/trailing_stop).
    /// 逐 symbol 狀態（持倉/壓縮/進場價/追蹤止損），以 PerSymbolState 統一容器承載。
    pub(crate) symbols: PerSymbolState<BbBreakoutPerSymbolState>,
    /// FIX-26: Max duration (ms) a squeeze remains valid. Default 30 min.
    /// FIX-26：壓縮狀態最長有效期（ms）。默認 30 分鐘。
    pub squeeze_expiry_ms: u64,
    /// Per-symbol cooldown tracking (was `last_trade_ms: HashMap<String, u64>`).
    /// 逐 symbol 冷卻追蹤（取代原 last_trade_ms HashMap）。
    pub(crate) cooldown: TrendCooldown,
    pub(crate) cooldown_ms: u64,
    default_qty: f64,
    /// ATR multiplier for trailing stop distance. Agent-adjustable (Phase 3a).
    /// ATR 追蹤止損距離乘數。Agent 可調（Phase 3a）。
    pub trailing_stop_atr_mult: f64,
    // RC-03: Configurable thresholds for Agent adjustability
    // RC-03：可配置閾值，供 Agent 動態調整
    /// Bandwidth below this = squeeze detected / 帶寬低於此值 = 偵測到壓縮
    pub squeeze_bw: f64,
    /// QC-H4: Entry confidence base (default 0.7). / 入場信心基礎值。
    pub(crate) entry_conf_base: f64,
    /// QC-H4: Exit confidence base (default 0.5). Exit reasons add offsets.
    /// QC-H4：出場信心基礎值。各出場原因加減偏移。
    pub(crate) exit_conf_base: f64,
    /// Bandwidth above this = expansion confirmed / 帶寬高於此值 = 確認擴張
    pub expansion_bw: f64,
    /// Minimum volume ratio for breakout entry / 突破入場最低成交量倍率
    pub volume_threshold: f64,
    // RC-04: Per-symbol previous state for rejection rollback / 每幣種拒絕回滾用的先前狀態
    //
    // Snapshot of the *entire* `BbBreakoutPerSymbolState` for the symbol at
    // tick entry; restored on rejection. `None` = symbol was unseen at snapshot.
    // 於 tick 進入時快照整個逐 symbol 狀態；拒絕時還原。None = 快照時該 symbol 不存在。
    prev_state: HashMap<String, Option<BbBreakoutPerSymbolState>>,
    prev_last_trade_ms: HashMap<String, u64>,
    /// CONF-D: Multiplier applied to emitted intent.confidence (default 1.0, range [0,2]).
    conf_scale: f64,
    // ── G-SR-1: Confluence scoring + persistence filter (A0-c, A1) ──
    pub confluence_config: ConfluenceConfig,
    persistence: PersistenceTracker,
    pub min_persistence_ms: u64,
    pub min_notional_usd: f64,
    // ── E5-P2-4: Config-driven exit confidence offsets + Hurst boost ──
    // ── E5-P2-4：config 驅動的出場信心偏移 + Hurst 加成 ──
    /// Hurst trending regime entry confidence boost. / Hurst 趨勢入場信心加成。
    pub(crate) hurst_regime_boost: f64,
    /// Trailing-stop exit confidence bonus. / 追蹤止損出場信心加成。
    pub(crate) exit_bonus_trailing_stop: f64,
    /// Regime-shift exit confidence bonus. / Regime 轉向出場信心加成。
    pub(crate) exit_bonus_regime_shift: f64,
    /// %B revert exit confidence bonus. / %B 回中軌出場信心加成。
    pub(crate) exit_bonus_pctb_revert: f64,
    /// BW squeeze exit confidence penalty (magnitude). / BW 再壓縮出場信心扣減幅度。
    pub(crate) exit_penalty_bw_squeeze: f64,
    // ── EDGE-P2-2: Open Interest confluence signal ──
    // ── EDGE-P2-2：OI 合流信號 ──
    /// Master switch; false → signal disabled, no buffer mutation effects.
    /// 總開關；false → 信號禁用。
    pub(crate) enable_oi_signal: bool,
    /// Rolling OI buffer window (ms). / OI 差分窗口（ms）。
    pub(crate) oi_buffer_window_ms: u64,
    /// Bonus applied on confluence score on OI confirmation / subtracted on divergence.
    /// OI 合流加成（確認為加、背離為減）。
    pub(crate) oi_confluence_bonus: f64,
    /// EDGE-P2-2 FUP: min `|oi_delta_pct|` to trigger bonus (noise floor).
    /// EDGE-P2-2 FUP：觸發 bonus 的最小 `|oi_delta_pct|`（噪音地板）。
    pub(crate) oi_min_delta_pct: f64,
    // ── EDGE-P2-3 Phase 2+: PostOnly maker entry toggles ──
    // ── EDGE-P2-3 Phase 2+：PostOnly maker 入場開關 ──
    /// EDGE-P2-3 Phase 2+: emit PostOnly Limit entries instead of Market.
    /// Close path remains Market (entry-only scope). Default `false`.
    /// EDGE-P2-3 Phase 2+：入場發 PostOnly Limit；平倉維持 Market。
    pub(crate) use_maker_entry: bool,
    /// EDGE-P2-3 Phase 2+: bps offset from last_price for PostOnly limit placement.
    /// EDGE-P2-3 Phase 2+：PostOnly 限價相對 last_price 的 bps 偏移。
    pub(crate) maker_price_offset_bps: f64,
    /// EDGE-P2-3 Phase 2+: ms a resting PostOnly maker order may sit (clamped on assign).
    /// EDGE-P2-3 Phase 2+：PostOnly 掛單最長停留時間（毫秒；寫入時 clamp）。
    pub(crate) maker_limit_timeout_ms: u64,
}

impl BbBreakout {
    pub fn new() -> Self {
        Self {
            active: true,
            symbols: PerSymbolState::new(),
            squeeze_expiry_ms: 2_700_000, // EDGE-P1-4: 45 minutes (was 30)
            cooldown: TrendCooldown::new(600_000),
            cooldown_ms: 600_000,
            default_qty: 1e9,
            trailing_stop_atr_mult: 2.0,
            squeeze_bw: DEFAULT_SQUEEZE_BW,
            expansion_bw: DEFAULT_EXPANSION_BW,
            volume_threshold: DEFAULT_VOLUME_THRESHOLD,
            entry_conf_base: 0.7,
            exit_conf_base: 0.5,
            prev_state: HashMap::new(),
            prev_last_trade_ms: HashMap::new(),
            conf_scale: 1.0,
            confluence_config: ConfluenceConfig::breakout(),
            persistence: PersistenceTracker::new(),
            min_persistence_ms: 60_000, // 1 min (triple gate already strict)
            min_notional_usd: 10.0,
            // E5-P2-4: preserve exact pre-extraction values (bit-exact behaviour)
            // E5-P2-4：保留原始值以確保行為 bit-exact
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
            // EDGE-P2-2 FUP: 0.0 → any non-zero delta applies bonus (pre-FUP).
            // EDGE-P2-2 FUP：0.0 = 任何非零 delta 即觸發（pre-FUP 行為）。
            oi_min_delta_pct: 0.0,
            // EDGE-P2-3 Phase 2+: conservative cold-boot (root principle #6).
            // EDGE-P2-3 Phase 2+：冷啟動保守默認（根原則 #6）。
            use_maker_entry: false,
            maker_price_offset_bps: 1.0,
            maker_limit_timeout_ms: 45_000,
        }
    }

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
        self.maker_limit_timeout_ms = super::grid_trading::clamp_maker_limit_timeout_ms(
            params.maker_limit_timeout_ms,
        );
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
        }
    }

    // ── Per-symbol accessors (test-facing; also handy for observability) ──
    // 逐 symbol 存取器（供測試使用，外部觀察亦可調用）。

    /// Current position direction for `symbol` (None if flat or unseen).
    /// 該 symbol 當前持倉方向，平倉或未見則為 None。
    #[inline]
    pub fn position_of(&self, symbol: &str) -> Option<bool> {
        self.symbols.get(symbol).and_then(|s| s.position)
    }

    /// Recorded entry price for `symbol` (None if flat or unseen).
    /// 該 symbol 最近一次開倉價，平倉或未見則為 None。
    #[inline]
    pub fn entry_price_of(&self, symbol: &str) -> Option<f64> {
        self.symbols.get(symbol).and_then(|s| s.entry_price)
    }

    /// Current ATR trailing stop for `symbol` (None if flat / not yet set).
    /// 該 symbol 當前 ATR 追蹤止損價，平倉或尚未設定則為 None。
    #[inline]
    pub fn trailing_stop_of(&self, symbol: &str) -> Option<f64> {
        self.symbols.get(symbol).and_then(|s| s.trailing_stop)
    }

    /// True if `symbol` has a recorded squeeze-detection timestamp.
    /// 該 symbol 是否登記了壓縮起始時間戳。
    #[inline]
    pub fn has_squeeze(&self, symbol: &str) -> bool {
        self.symbols
            .get(symbol)
            .map(|s| s.squeeze_detected_ms.is_some())
            .unwrap_or(false)
    }
}

impl Strategy for BbBreakout {
    fn name(&self) -> &str {
        "bb_breakout"
    }
    fn is_active(&self) -> bool {
        self.active
    }
    fn set_active(&mut self, active: bool) {
        self.active = active;
    }

    /// Reset per-symbol position state on external close (risk-stop).
    /// Preserves `squeeze_detected_ms` (squeeze can continue across close).
    /// 外部平倉（風控止損）時重設該幣種內部狀態；`squeeze_detected_ms` 保留
    /// （壓縮狀態可跨越平倉延續）。
    fn on_external_close(&mut self, symbol: &str) {
        if let Some(st) = self.symbols.get_mut(symbol) {
            st.position = None;
            st.entry_price = None;
            st.trailing_stop = None;
        }
        self.persistence.clear(symbol);
    }

    /// RC-04: Revert per-symbol state on rejection. Snapshot is the full
    /// `BbBreakoutPerSymbolState` (or `None` if the symbol was unseen); restoring
    /// it exactly reproduces the pre-tick per-symbol state.
    ///
    /// EDGE-P2-2 FUP (E2 finding #2): `oi_buffer` is a market-observation
    /// series, not a strategy decision state. Rolling it back on rejection
    /// would discard the OI sample pushed earlier this tick, and under a high
    /// rejection rate (budget/风控) this systematically starves the delta
    /// estimator. We therefore preserve the live `oi_buffer` across rollback:
    /// - `prev_st = Some(...)`: clone prev_st but overwrite its oi_buffer with
    ///   the current live buffer (carry the new sample forward).
    /// - `prev_st = None`: symbol was unseen pre-tick. If a sample was just
    ///   pushed, seed a fresh Default state with only the oi_buffer populated
    ///   so trading state stays "unseen" but market observation survives.
    ///
    /// EDGE-P2-2 FUP（E2 #2）：`oi_buffer` 是市場觀察序列不是策略決策狀態，
    /// 若一起回滾，在高拒絕率下會系統性餓死 delta 估計。故保留活 buffer：
    /// prev=Some → 克隆 prev_st 但覆寫 oi_buffer；prev=None 且有新樣本 → 創建只
    /// 含 oi_buffer 的 Default 狀態（trading state 保持 unseen，OI 觀察續存）。
    fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
        let sym = &intent.symbol;
        // Snapshot the current (live) OI buffer so rollback of trading state
        // does not discard the sample pushed earlier this tick.
        // 先取當前活 OI buffer 快照，以免 rollback 丟掉本 tick push 的新樣本。
        let live_oi_buffer = self
            .symbols
            .get(sym)
            .map(|s| s.oi_buffer.clone())
            .unwrap_or_default();
        if let Some(prev) = self.prev_state.get(sym) {
            match prev {
                Some(prev_st) => {
                    let mut restored = prev_st.clone();
                    restored.oi_buffer = live_oi_buffer;
                    self.symbols.insert(sym.to_string(), restored);
                }
                None => {
                    if live_oi_buffer.is_empty() {
                        self.symbols.remove(sym);
                    } else {
                        let mut fresh = BbBreakoutPerSymbolState::default();
                        fresh.oi_buffer = live_oi_buffer;
                        self.symbols.insert(sym.to_string(), fresh);
                    }
                }
            }
        }
        if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
            if ts == 0 {
                self.cooldown.clear(sym);
            } else {
                self.cooldown.record_signal(sym, ts);
            }
        }
    }

    fn on_tick(&mut self, ctx: &TickContext<'_>) -> Vec<StrategyAction> {
        let ind = match ctx.indicators {
            Some(i) => i,
            None => return vec![],
        };
        let bb = match &ind.bollinger {
            Some(b) => b,
            None => return vec![],
        };
        let vol_ratio = ind.volume_ratio.unwrap_or(1.0);

        // RC-04: Snapshot per-symbol state before any mutation for rejection rollback.
        // Whole-struct snapshot = exact pre-tick state (or None if unseen).
        // RC-04：於任何變更前快照該 symbol 整包狀態（None = 本 tick 之前未見）。
        let sym = ctx.symbol;
        self.prev_state
            .insert(sym.to_string(), self.symbols.get(sym).cloned());
        let last_ms = self.cooldown.last_ms(sym).unwrap_or(0);
        self.prev_last_trade_ms.insert(sym.to_string(), last_ms);

        if bb.bandwidth < self.squeeze_bw {
            // FIX-26: Only record first detection time; don't reset on continued squeeze.
            // FIX-26：只記錄首次偵測，持續壓縮不重置。
            let st = self.symbols.get_or_init(sym);
            if st.squeeze_detected_ms.is_none() {
                st.squeeze_detected_ms = Some(ctx.timestamp_ms);
            }
        }
        // EDGE-P2-2: Maintain per-symbol OI buffer regardless of flag, so the
        // buffer is warm whenever the flag gets flipped on via hot-reload.
        // We only populate when ctx.open_interest is Some; front-evict by window.
        // Always DEBUG-log the derived delta for operator observability.
        //
        // EDGE-P2-2 FUP (E2 finding #1 + #6): `ctx.open_interest` is the
        // pipeline's latest cached OI — every tick carries it, even non-ticker
        // events (trades/orderbook) replaying the same value under new
        // timestamps. Without dedup, 10 Hz trade + 0.2 Hz ticker yields a
        // buffer that's ≥95% same-OI/different-ts samples, silently shrinking
        // the real time coverage of `oi_buffer_window_ms`. We therefore skip
        // push when (a) ts is not strictly newer than back (monotonic guard,
        // E2 #6 cross-stream regression) OR (b) OI value equals back's OI
        // (dedup, E2 #1). Eviction still runs unconditionally so stale samples
        // age out even on a ticker-less symbol.
        // EDGE-P2-2：無論 flag 是否啟用都維護 OI buffer，hot-reload 開啟時立即可用。
        // FUP：`ctx.open_interest` 是 pipeline 最新快取，每個 tick（含 trade/orderbook）
        //   都會攜帶同一 OI 值不同時間戳，未去重時 10Hz trade+0.2Hz ticker 會讓 buffer
        //   95% 是重複樣本，窗口實際覆蓋遠小於 `oi_buffer_window_ms`。因此：
        //   (a) 非嚴格新 ts（E2 #6 跨流倒流）或 (b) OI 值未變（E2 #1 去重）皆 skip push。
        //   淘汰邏輯永遠執行，空 tick 也能讓舊樣本過期。
        if let Some(oi) = ctx.open_interest {
            let window = self.oi_buffer_window_ms;
            let st = self.symbols.get_or_init(sym);
            let should_push = match st.oi_buffer.back() {
                None => true,
                Some(&(back_ts, back_oi)) => {
                    ctx.timestamp_ms > back_ts && (oi - back_oi).abs() > f64::EPSILON
                }
            };
            if should_push {
                st.oi_buffer.push_back((ctx.timestamp_ms, oi));
            }
            while let Some(&(front_ts, _)) = st.oi_buffer.front() {
                // Use saturating_sub to avoid underflow when timestamps regress.
                // 用 saturating_sub 防時間戳倒流造成 underflow。
                if ctx.timestamp_ms.saturating_sub(front_ts) > window {
                    st.oi_buffer.pop_front();
                } else {
                    break;
                }
            }
            if let Some(d) = st.compute_oi_delta_pct() {
                tracing::debug!(
                    target: "bb_breakout.oi",
                    strategy = "bb_breakout",
                    symbol = %sym,
                    oi_delta_pct = d,
                    oi_buffer_len = st.oi_buffer.len(),
                    enabled = self.enable_oi_signal,
                    "OI delta computed / OI 差分已計算"
                );
            }
        }
        if !self.cooldown.is_cooled_down(sym, ctx.timestamp_ms) {
            return vec![];
        }

        let mut intents = Vec::new();
        let current_position = self.symbols.get(sym).and_then(|s| s.position);
        match current_position {
            None => {
                // FIX-26: Check squeeze exists AND hasn't expired.
                let in_squeeze = self
                    .symbols
                    .get(sym)
                    .and_then(|s| s.squeeze_detected_ms)
                    .map(|ts| ctx.timestamp_ms < ts + self.squeeze_expiry_ms)
                    .unwrap_or(false);
                if in_squeeze
                    && bb.bandwidth > self.expansion_bw
                    && vol_ratio >= self.volume_threshold
                {
                    let is_long = bb.percent_b > 1.0;
                    let is_short = bb.percent_b < 0.0;

                    // A3: Donchian confirmation — price must also breach Donchian channel
                    // A3：Donchian 确认 — 价格需同时突破 Donchian 通道
                    if let Some(dc) = &ind.donchian {
                        if is_long && ctx.price < dc.upper {
                            return vec![];
                        }
                        if is_short && ctx.price > dc.lower {
                            return vec![];
                        }
                    }

                    if is_long || is_short {
                        // A1: Persistence filter — triple gate signal must hold.
                        // A1：持續性過濾 — 三重門控信號必須持續。
                        let signal = Some(is_long);
                        if !self.persistence.check(
                            sym,
                            signal,
                            ctx.timestamp_ms,
                            self.min_persistence_ms,
                            false,
                        ) {
                            return intents;
                        }

                        // A4: Hurst regime boost — trending regime boosts breakout confidence
                        // A4：Hurst 趋势状态 — 趋势型市场提升突破信心
                        // E5-P2-4: magnitude now config-driven (was hard-coded 0.1).
                        // E5-P2-4：加成幅度改由 config 控制（原 hard-coded 0.1）。
                        let hurst_boost: f64 = match &ind.hurst {
                            Some(h) if h.regime == "trending" => self.hurst_regime_boost,
                            _ => 0.0,
                        };

                        // A2: Confluence scoring — qty modifier only for breakout.
                        // A2：匯流評分 — 突破策略僅作為 qty 調整器。
                        let score = confluence::compute_score(
                            &self.confluence_config,
                            true,
                            ind.adx.as_ref().map(|a| a.adx),
                            ind.hurst
                                .as_ref()
                                .map(|h| h.regime.as_str())
                                .unwrap_or("uncertain"),
                            ind.volume_ratio,
                            ind.rsi_14,
                            is_long,
                        );
                        // EDGE-P2-2: OI confluence modifier.
                        // When `enable_oi_signal=false`, `score` is untouched (bit-exact).
                        // When enabled + buffer has a valid delta, add bonus on confirmation
                        // (rising OI + long, falling OI + short) or subtract on divergence.
                        // `compute_score` may return `None` (confluence disabled upstream);
                        // in that case we do not fabricate a score from OI alone — the
                        // downstream `score_to_qty_pct` handles `None` as "no modifier".
                        //
                        // EDGE-P2-2 FUP (E2 finding #3): require `|d| > oi_min_delta_pct`
                        // to apply the bonus. Default threshold is 0.0, which preserves
                        // pre-FUP semantics (any non-zero delta triggers). Raising this
                        // filters WS snapshot quantisation noise (±1 contract → ~1e-8
                        // delta) from being treated as a confirmation signal.
                        // EDGE-P2-2：OI 合流修飾器。flag=false 時 score 完全不變（bit-exact）。
                        // 開啟且 buffer 有有效 delta 時：方向一致加 bonus，背離則扣 bonus。
                        // score=None（上游合流停用）時不憑 OI 偽造 score。
                        // FUP：需 `|d| > oi_min_delta_pct` 才套 bonus；預設 0.0 保留 pre-FUP 行為。
                        let score = if self.enable_oi_signal {
                            let delta_opt = self
                                .symbols
                                .get(sym)
                                .and_then(|s| s.compute_oi_delta_pct());
                            match (score, delta_opt) {
                                (Some(s), Some(d)) if d.abs() > self.oi_min_delta_pct => {
                                    let confirms = (d > 0.0 && is_long) || (d < 0.0 && !is_long);
                                    let adj = if confirms {
                                        self.oi_confluence_bonus
                                    } else {
                                        -self.oi_confluence_bonus
                                    };
                                    Some(s + adj)
                                }
                                _ => score,
                            }
                        } else {
                            score
                        };
                        let qty_pct = confluence::score_to_qty_pct(score, &self.confluence_config);
                        // confluence_as_gate=false: always trade if triple gate passed,
                        // but scale qty. qty_pct=0 only blocks if confluence_as_gate=true.
                        let effective_pct = if self.confluence_config.confluence_as_gate {
                            qty_pct
                        } else {
                            qty_pct.max(0.10) // minimum 10% qty for breakout
                        };
                        let qty = self.default_qty * effective_pct;
                        if qty * ctx.price < self.min_notional_usd {
                            return intents;
                        }

                        let raw_conf = (self.entry_conf_base + hurst_boost).min(1.0);
                        // EDGE-P3-1 A6: plumb decision-time confluence + persistence
                        // onto the intent for the predictor gate feature vector.
                        // EDGE-P3-1 A6：把決策時的 confluence/persistence 寫入 intent。
                        let confluence_score = score.map(|s| s as f32);
                        let persistence_elapsed_ms =
                            self.persistence.elapsed_ms(sym, ctx.timestamp_ms);
                        // EDGE-P2-3 Phase 2+: resolve entry order shape (Market vs PostOnly Limit).
                        // Only new-open intents go maker; close path below stays Market (scope guard).
                        // BUY offset below last_price; SELL offset above — PostOnly always rests passively.
                        // EDGE-P2-3 Phase 2+：決定入場單型（Market 或 PostOnly Limit）。
                        // 僅新開倉走 maker；平倉保持 Market。BUY 掛 last 下方、SELL 掛上方。
                        let (order_type, limit_price, time_in_force, maker_timeout_ms) =
                            if self.use_maker_entry {
                                let offset = self.maker_price_offset_bps / 10_000.0;
                                let limit = if is_long {
                                    ctx.price * (1.0 - offset)
                                } else {
                                    ctx.price * (1.0 + offset)
                                };
                                (
                                    "limit".to_string(),
                                    Some(limit),
                                    Some(TimeInForce::PostOnly),
                                    Some(self.maker_limit_timeout_ms),
                                )
                            } else {
                                ("market".to_string(), None, None, None)
                            };
                        intents.push(StrategyAction::Open(OrderIntent {
                            symbol: ctx.symbol.to_string(),
                            is_long,
                            qty,
                            confidence: crate::tick_pipeline::on_tick_helpers::clamp_confidence(
                                raw_conf * self.conf_scale,
                            ),
                            strategy: self.name().into(),
                            order_type,
                            limit_price,
                            confluence_score,
                            persistence_elapsed_ms,
                            time_in_force,
                            maker_timeout_ms,
                        }));
                        // Commit per-symbol state in a single get_or_init call
                        // to avoid four separate HashMap lookups.
                        // 單次 get_or_init 寫入所有欄位，避免多次查找。
                        let st = self.symbols.get_or_init(sym);
                        st.position = Some(is_long);
                        st.squeeze_detected_ms = None;
                        self.cooldown.record_signal(sym, ctx.timestamp_ms);
                        // V2: Record entry price and initialize trailing stop per-symbol
                        st.entry_price = Some(ctx.price);
                        if let Some(atr_res) = &ind.atr_14 {
                            let dist = atr_res.atr * self.trailing_stop_atr_mult;
                            let stop = if is_long {
                                ctx.price - dist
                            } else {
                                ctx.price + dist
                            };
                            st.trailing_stop = Some(stop);
                        }
                    }
                }
            }
            Some(is_long) => {
                let mut exit_reason: Option<&str> = None;
                // QC-H4: exit_conf_base configurable (was hardcoded 0.5)
                let mut exit_confidence = self.exit_conf_base;

                // V2: ATR trailing stop — Chandelier exit, 2×ATR from peak.
                // V2：ATR 追蹤止損 — Chandelier 出場，峰值 2×ATR。
                if let Some(atr_res) = &ind.atr_14 {
                    let stop_distance = atr_res.atr * self.trailing_stop_atr_mult;
                    // Note: ratchet-only update (long = monotonically increasing stop,
                    // short = monotonically decreasing stop); preserved bit-exact.
                    // 備註：止損單向棘輪（多頭只升、空頭只降），保持 bit-exact 行為。
                    let st = self.symbols.get_or_init(sym);
                    let cur_stop = st.trailing_stop;
                    // E5-P2-4: trailing-stop bonus now config-driven (was 0.2).
                    // E5-P2-4：追蹤止損加成改由 config 控制（原 0.2）。
                    if is_long {
                        let new_stop = ctx.price - stop_distance;
                        if cur_stop.is_none() || new_stop > cur_stop.unwrap() {
                            st.trailing_stop = Some(new_stop);
                        }
                        if ctx.price <= st.trailing_stop.unwrap_or(0.0) {
                            exit_reason = Some("trailing_stop");
                            exit_confidence = self.exit_conf_base + self.exit_bonus_trailing_stop;
                        }
                    } else {
                        let new_stop = ctx.price + stop_distance;
                        if cur_stop.is_none() || new_stop < cur_stop.unwrap() {
                            st.trailing_stop = Some(new_stop);
                        }
                        if ctx.price >= st.trailing_stop.unwrap_or(f64::MAX) {
                            exit_reason = Some("trailing_stop");
                            exit_confidence = self.exit_conf_base + self.exit_bonus_trailing_stop;
                        }
                    }
                }

                // V2: Regime exit — Hurst drops from trending to mean_reverting/random_walk.
                // V2：Regime 出場 — Hurst 從趨勢轉為均值回歸/隨機漫步。
                // E5-P2-4: regime_shift bonus now config-driven (was 0.1).
                // E5-P2-4：regime 轉向加成改由 config 控制（原 0.1）。
                if exit_reason.is_none() {
                    if let Some(h) = &ind.hurst {
                        if h.regime == "mean_reverting" || h.regime == "random_walk" {
                            exit_reason = Some("regime_shift");
                            exit_confidence = self.exit_conf_base + self.exit_bonus_regime_shift;
                        }
                    }
                }

                // %B revert to mid: failed breakout — price returned to BB middle.
                // %B 回中軌：突破失敗 — 價格回到 BB 中間。
                // E5-P2-4: pctb_revert bonus / bw_squeeze penalty now config-driven
                // (was 0.05 / -0.05 hard-coded).
                // E5-P2-4：%B 回中軌加成與帶寬再壓縮扣減改由 config 控制（原 0.05 / -0.05）。
                if exit_reason.is_none() {
                    if bb.percent_b >= 0.2 && bb.percent_b <= 0.8 {
                        exit_reason = Some("pctb_revert");
                        exit_confidence = self.exit_conf_base + self.exit_bonus_pctb_revert;
                    } else if bb.bandwidth < self.squeeze_bw {
                        // BW squeeze: volatility collapsed / 帶寬壓縮：波動塌陷
                        exit_reason = Some("bw_squeeze");
                        exit_confidence = self.exit_conf_base - self.exit_penalty_bw_squeeze;
                    }
                }

                if let Some(reason) = exit_reason {
                    intents.push(StrategyAction::Close {
                        symbol: ctx.symbol.to_string(),
                        confidence: crate::tick_pipeline::on_tick_helpers::clamp_confidence(
                            exit_confidence * self.conf_scale,
                        ),
                        reason: reason.into(),
                    });
                    // V2: Reset per-symbol trailing stop state on exit; squeeze
                    // tracking is preserved (same semantics as pre-refactor).
                    // V2：出場時重置 position/entry_price/trailing_stop，squeeze 追蹤保留。
                    if let Some(st) = self.symbols.get_mut(sym) {
                        st.position = None;
                        st.entry_price = None;
                        st.trailing_stop = None;
                    }
                    self.cooldown.record_signal(sym, ctx.timestamp_ms);
                }
            }
        }
        intents
    }

    fn update_params_json(&mut self, json: &str) -> Result<(), String> {
        let p: BbBreakoutParams = serde_json::from_str(json).map_err(|e| e.to_string())?;
        self.update_params(p)
    }
    fn get_params_json(&self) -> String {
        serde_json::to_string(&self.get_params()).unwrap_or_default()
    }
    fn param_ranges_json(&self) -> String {
        serde_json::to_string(&BbBreakoutParams::param_ranges()).unwrap_or_default()
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
    use openclaw_core::indicators::{AtrResult, BollingerResult, HurstResult, IndicatorSnapshot};

    // P-08: Test helpers use Box::leak for owned indicator data (fine for tests).
    fn ctx(bw: f64, pct_b: f64, vol: f64, ts: u64) -> TickContext<'static> {
        ctx_ext(bw, pct_b, vol, ts, 50000.0, None, None)
    }

    /// Extended context builder with price, ATR, and Hurst overrides.
    /// 擴展上下文建構器，支持自訂價格、ATR、Hurst。
    fn ctx_ext(
        bw: f64,
        pct_b: f64,
        vol: f64,
        ts: u64,
        price: f64,
        atr: Option<AtrResult>,
        hurst: Option<HurstResult>,
    ) -> TickContext<'static> {
        let ind = Box::leak(Box::new(IndicatorSnapshot {
            bollinger: Some(BollingerResult {
                upper: 51000.0,
                middle: 50000.0,
                lower: 49000.0,
                bandwidth: bw,
                percent_b: pct_b,
            }),
            volume_ratio: Some(vol),
            atr_14: atr,
            hurst,
            ..Default::default()
        }));
        TickContext {
            symbol: "BTC",
            price,
            timestamp_ms: ts,
            indicators: Some(ind),
            signals: &[],
            h0_allowed: true,
            funding_rate: None,
            index_price: None,
            open_interest: None,
        }
    }

    #[test]
    fn test_squeeze_then_breakout() {
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0));
        let i = s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Open(intent) => assert!(intent.is_long),
            other => panic!("expected Open, got {:?}", other),
        }
    }

    #[test]
    fn test_no_breakout_without_squeeze() {
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        assert!(s.on_tick(&ctx(0.05, 1.1, 2.0, 0)).is_empty());
    }

    #[test]
    fn test_entry_price_recorded() {
        // After entry, entry_price should be set / 入場後 entry_price 應被設置
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
        s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000)); // breakout long
        assert_eq!(s.entry_price_of("BTC"), Some(50000.0));
        assert!(s.trailing_stop_of("BTC").is_none()); // no ATR data, no trailing stop yet
    }

    #[test]
    fn test_atr_trailing_stop_long_exit() {
        // Long position: price drops below trailing stop -> exit
        // 做多倉位：價格跌破追蹤止損 -> 出場
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        let atr = || {
            Some(AtrResult {
                atr: 500.0,
                atr_percent: 0.01,
            })
        };

        // Enter long
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
        s.on_tick(&ctx_ext(0.05, 1.1, 2.0, 700_000, 50000.0, atr(), None)); // breakout
        assert_eq!(s.position_of("BTC"), Some(true));
        // trailing_stop = 50000 - 500*2 = 49000
        assert_eq!(s.trailing_stop_of("BTC"), Some(49000.0));

        // Price rises -> trailing stop ratchets up, no exit
        // 價格上漲 -> 追蹤止損上移，不出場
        let i = s.on_tick(&ctx_ext(0.05, 1.2, 2.0, 1_400_000, 52000.0, atr(), None));
        assert!(i.is_empty()); // still in trend
        assert_eq!(s.trailing_stop_of("BTC"), Some(51000.0)); // 52000 - 1000

        // Price drops to trailing stop -> exit
        // 價格跌至追蹤止損 -> 出場
        let i = s.on_tick(&ctx_ext(0.05, 0.9, 2.0, 2_100_000, 51000.0, atr(), None));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Close {
                reason, confidence, ..
            } => {
                assert_eq!(reason, "trailing_stop");
                assert!((*confidence - 0.7).abs() < 1e-9);
            }
            other => panic!("expected Close, got {:?}", other),
        }
        assert!(s.position_of("BTC").is_none());
        assert!(s.entry_price_of("BTC").is_none());
        assert!(s.trailing_stop_of("BTC").is_none());
    }

    #[test]
    fn test_atr_trailing_stop_short_exit() {
        // Short position: price rises above trailing stop -> exit
        // 做空倉位：價格漲破追蹤止損 -> 出場
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        let atr = || {
            Some(AtrResult {
                atr: 500.0,
                atr_percent: 0.01,
            })
        };

        // Enter short
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
        s.on_tick(&ctx_ext(0.05, -0.1, 2.0, 700_000, 50000.0, atr(), None)); // breakout short
        assert_eq!(s.position_of("BTC"), Some(false));
        // trailing_stop = 50000 + 500*2 = 51000
        assert_eq!(s.trailing_stop_of("BTC"), Some(51000.0));

        // Price drops -> trailing stop ratchets down
        let i = s.on_tick(&ctx_ext(0.05, -0.2, 2.0, 1_400_000, 48000.0, atr(), None));
        assert!(i.is_empty());
        assert_eq!(s.trailing_stop_of("BTC"), Some(49000.0)); // 48000 + 1000

        // Price rises to trailing stop -> exit
        let i = s.on_tick(&ctx_ext(0.05, 0.1, 2.0, 2_100_000, 49000.0, atr(), None));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Close { reason, .. } => assert_eq!(reason, "trailing_stop"),
            other => panic!("expected Close, got {:?}", other),
        }
    }

    #[test]
    fn test_regime_exit() {
        // Exit when regime changes to mean_reverting / 當 regime 變為均值回歸時出場
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        let trending = || {
            Some(HurstResult {
                hurst: 0.7,
                regime: "trending".into(),
            })
        };
        let ranging = || {
            Some(HurstResult {
                hurst: 0.4,
                regime: "mean_reverting".into(),
            })
        };

        // Enter long (with trending regime boost)
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
        let i = s.on_tick(&ctx_ext(0.05, 1.1, 2.0, 700_000, 50000.0, None, trending()));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Open(intent) => {
                assert!((intent.confidence - 0.8).abs() < 1e-9); // 0.7 + 0.1 hurst boost
            }
            other => panic!("expected Open, got {:?}", other),
        }
        assert_eq!(s.position_of("BTC"), Some(true));

        // Regime shifts to mean_reverting -> exit
        let i = s.on_tick(&ctx_ext(
            0.05,
            1.1,
            2.0,
            1_400_000,
            51000.0,
            None,
            ranging(),
        ));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Close {
                reason, confidence, ..
            } => {
                assert_eq!(reason, "regime_shift");
                assert!((*confidence - 0.6).abs() < 1e-9);
            }
            other => panic!("expected Close, got {:?}", other),
        }
        assert!(s.position_of("BTC").is_none());
    }

    #[test]
    fn test_configurable_volume_threshold() {
        // RC-03: Custom volume threshold — higher threshold blocks low-volume breakouts
        // RC-03：自訂成交量閾值 — 較高閾值阻擋低量突破
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        s.volume_threshold = 3.0; // require 3x volume instead of default 1.5x
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
                                            // vol=2.0 passes default (1.5) but fails custom (3.0)
                                            // vol=2.0 通過默認閾值(1.5)但不通過自訂閾值(3.0)
        let i = s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000));
        assert!(i.is_empty(), "volume 2.0 should not pass threshold 3.0");

        // vol=3.5 passes custom threshold / vol=3.5 通過自訂閾值
        let i = s.on_tick(&ctx(0.05, 1.1, 3.5, 700_000));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Open(intent) => assert!(intent.is_long),
            other => panic!("expected Open, got {:?}", other),
        }
    }

    #[test]
    fn test_configurable_squeeze_expansion_bw() {
        // RC-03: Custom squeeze/expansion bandwidth thresholds
        // RC-03：自訂壓縮/擴張帶寬閾值
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        s.squeeze_bw = 0.03; // wider squeeze detection / 更寬的壓縮偵測
        s.expansion_bw = 0.06; // require stronger expansion / 要求更強擴張

        // bw=0.025 triggers squeeze with custom threshold (< 0.03)
        s.on_tick(&ctx(0.025, 0.5, 1.0, 0));
        assert!(s.has_squeeze("BTC"));

        // bw=0.05 is expansion for default (> 0.04) but NOT for custom (< 0.06)
        let i = s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000));
        assert!(i.is_empty(), "bw 0.05 should not pass expansion_bw 0.06");

        // bw=0.07 passes custom expansion threshold / 通過自訂擴張閾值
        let i = s.on_tick(&ctx(0.07, 1.1, 2.0, 700_000));
        assert_eq!(i.len(), 1);
    }

    #[test]
    fn test_bb_brk_param_ranges() {
        assert!(!BbBreakoutParams::param_ranges().is_empty());
    }
    #[test]
    fn test_bb_brk_validate() {
        assert!(BbBreakoutParams::default().validate().is_ok());
        assert!(BbBreakoutParams {
            squeeze_bw: 0.05,
            expansion_bw: 0.04,
            ..Default::default()
        }
        .validate()
        .is_err());
    }
    #[test]
    fn test_bb_brk_update() {
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        assert!(s
            .update_params(BbBreakoutParams {
                trailing_stop_atr_mult: 3.0,
                ..Default::default()
            })
            .is_ok());
        assert!((s.get_params().trailing_stop_atr_mult - 3.0).abs() < 0.01);
    }

    #[test]
    fn test_pctb_revert_exit() {
        // Failed breakout: %B returns to mid-band [0.2, 0.8] → exit with pctb_revert
        // 突破失敗：%B 回到中間帶 [0.2, 0.8] → 以 pctb_revert 出場
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
                                  // Enter long (no ATR, no Hurst — only pctb/bw exits active)
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
        s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000)); // breakout long
        assert_eq!(s.position_of("BTC"), Some(true));

        // %B reverts to 0.5 (mid-band) → should trigger pctb_revert exit
        let i = s.on_tick(&ctx(0.05, 0.5, 2.0, 1_400_000));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Close {
                reason, confidence, ..
            } => {
                assert_eq!(reason, "pctb_revert");
                // 0.55 * conf_scale(1.0) = 0.55
                assert!((*confidence - 0.55).abs() < 1e-9);
            }
            other => panic!("expected Close(pctb_revert), got {:?}", other),
        }
        assert!(s.position_of("BTC").is_none());
    }

    #[test]
    fn test_bw_squeeze_exit() {
        // Volatility collapse: bandwidth drops below squeeze_bw while %B still extreme → bw_squeeze
        // 波動塌陷：帶寬低於壓縮閾值且 %B 仍在極端 → bw_squeeze
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
                                  // Enter long
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
        s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000)); // breakout long
        assert_eq!(s.position_of("BTC"), Some(true));

        // %B still extreme (1.1, outside [0.2,0.8]) but bandwidth collapsed below squeeze_bw (0.02)
        // → pctb_revert doesn't trigger, but bw_squeeze does
        let i = s.on_tick(&ctx(0.015, 1.1, 2.0, 1_400_000));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Close {
                reason, confidence, ..
            } => {
                assert_eq!(reason, "bw_squeeze");
                // 0.45 * conf_scale(1.0) = 0.45
                assert!((*confidence - 0.45).abs() < 1e-9);
            }
            other => panic!("expected Close(bw_squeeze), got {:?}", other),
        }
        assert!(s.position_of("BTC").is_none());
    }

    // ── G-SR-1 S3+S4: param_ranges + validation tests ──

    #[test]
    fn test_bbb_param_ranges_count() {
        let ranges = BbBreakoutParams::param_ranges();
        // 5 original + 11 confluence (includes confluence_as_gate) + 4 EDGE-P2-2 OI
        // (enable_oi_signal + oi_buffer_window_ms + oi_confluence_bonus + oi_min_delta_pct) = 20
        // EDGE-P2-2 FUP：oi_min_delta_pct 是 noise floor，需作為 agent-tunable ParamRange 暴露。
        assert_eq!(
            ranges.len(),
            20,
            "expected 20 param ranges, got {}",
            ranges.len()
        );
    }

    #[test]
    fn test_bbb_param_ranges_has_confluence_as_gate() {
        let ranges = BbBreakoutParams::param_ranges();
        let names: Vec<&str> = ranges.iter().map(|r| r.name.as_str()).collect();
        assert!(
            names.contains(&"confluence_as_gate"),
            "BBB must expose confluence_as_gate"
        );
    }

    #[test]
    fn test_bbb_param_ranges_confluence_names() {
        let ranges = BbBreakoutParams::param_ranges();
        let names: Vec<&str> = ranges.iter().map(|r| r.name.as_str()).collect();
        for expected in &[
            "weight_adx",
            "weight_regime",
            "weight_volume",
            "weight_momentum",
            "adx_floor",
            "confluence_threshold_no_trade",
            "confluence_threshold_light",
            "confluence_threshold_full",
            "confluence_as_gate",
            "min_persistence_ms",
            "min_notional_usd",
        ] {
            assert!(names.contains(expected), "missing param range: {expected}");
        }
    }

    #[test]
    fn test_bbb_validate_default_ok() {
        assert!(BbBreakoutParams::default().validate().is_ok());
    }

    #[test]
    fn test_bbb_validate_bad_weight_sum() {
        let mut p = BbBreakoutParams::default();
        p.weight_adx = 0.0; // sum = 0+20+12+8 = 40 ≠ 65
        assert!(p.validate().is_err());
    }

    #[test]
    fn test_bbb_validate_bad_threshold_order() {
        let mut p = BbBreakoutParams::default();
        p.confluence_threshold_no_trade = 60.0; // > light (45)
        assert!(p.validate().is_err());
    }

    // ── E5-P2-4: bit-exact defaults for newly config-driven magic numbers ──
    // ── E5-P2-4：新增 config 欄位的預設值需與原 hard-coded 一致（bit-exact） ──

    #[test]
    fn test_e5_p2_4_bbb_params_defaults_match_prior_hardcoded() {
        // Defaults must equal the literals previously embedded in the strategy body
        // so downstream numerical outputs are byte-identical when TOML omits them.
        // 默認值需等於原先硬編碼的字面量，以保證 TOML 未覆寫時輸出位元相等。
        let p = BbBreakoutParams::default();
        assert!(
            (p.hurst_regime_boost - 0.1).abs() < f64::EPSILON,
            "hurst_regime_boost default must be 0.1 (bit-exact)"
        );
        assert!(
            (p.exit_bonus_trailing_stop - 0.2).abs() < f64::EPSILON,
            "exit_bonus_trailing_stop default must be 0.2 (bit-exact)"
        );
        assert!(
            (p.exit_bonus_regime_shift - 0.1).abs() < f64::EPSILON,
            "exit_bonus_regime_shift default must be 0.1 (bit-exact)"
        );
        assert!(
            (p.exit_bonus_pctb_revert - 0.05).abs() < f64::EPSILON,
            "exit_bonus_pctb_revert default must be 0.05 (bit-exact)"
        );
        assert!(
            (p.exit_penalty_bw_squeeze - 0.05).abs() < f64::EPSILON,
            "exit_penalty_bw_squeeze default must be 0.05 (bit-exact)"
        );
    }

    #[test]
    fn test_e5_p2_4_runtime_new_matches_params_default() {
        // BbBreakout::new() must seed the runtime fields with the same literals
        // as BbBreakoutParams::default() — enforces a single source of truth.
        // BbBreakout::new() 初始化值需與 BbBreakoutParams::default() 同源（單一事實來源）。
        let s = BbBreakout::new();
        let d = BbBreakoutParams::default();
        assert!((s.hurst_regime_boost - d.hurst_regime_boost).abs() < f64::EPSILON);
        assert!((s.exit_bonus_trailing_stop - d.exit_bonus_trailing_stop).abs() < f64::EPSILON);
        assert!((s.exit_bonus_regime_shift - d.exit_bonus_regime_shift).abs() < f64::EPSILON);
        assert!((s.exit_bonus_pctb_revert - d.exit_bonus_pctb_revert).abs() < f64::EPSILON);
        assert!((s.exit_penalty_bw_squeeze - d.exit_penalty_bw_squeeze).abs() < f64::EPSILON);
    }

    #[test]
    fn test_e5_p2_4_update_params_hot_reloads_offsets() {
        // update_params must propagate new field values to the live runtime
        // (hot-reload contract — ConfigStore / ArcSwap compatibility).
        // update_params 需將新欄位熱重載到運行時（與 ConfigStore/ArcSwap 契約一致）。
        let mut s = BbBreakout::new();
        let mut p = BbBreakoutParams::default();
        p.hurst_regime_boost = 0.17;
        p.exit_bonus_trailing_stop = 0.25;
        p.exit_bonus_regime_shift = 0.12;
        p.exit_bonus_pctb_revert = 0.07;
        p.exit_penalty_bw_squeeze = 0.08;
        s.update_params(p.clone()).expect("valid params");
        assert!((s.hurst_regime_boost - 0.17).abs() < f64::EPSILON);
        assert!((s.exit_bonus_trailing_stop - 0.25).abs() < f64::EPSILON);
        assert!((s.exit_bonus_regime_shift - 0.12).abs() < f64::EPSILON);
        assert!((s.exit_bonus_pctb_revert - 0.07).abs() < f64::EPSILON);
        assert!((s.exit_penalty_bw_squeeze - 0.08).abs() < f64::EPSILON);
        // Round-trip get_params must expose the freshly hot-reloaded values.
        // get_params 需回吐熱重載後的新值。
        let back = s.get_params();
        assert!((back.hurst_regime_boost - 0.17).abs() < f64::EPSILON);
        assert!((back.exit_bonus_trailing_stop - 0.25).abs() < f64::EPSILON);
    }

    /// EDGE-P2-2 FUP: update_params must hot-reload the 3 OI fields
    /// (`enable_oi_signal` / `oi_buffer_window_ms` / `oi_confluence_bonus`) and
    /// get_params must echo the mutated values — mirrors the
    /// `test_e5_p2_4_update_params_hot_reloads_offsets` contract.
    /// EDGE-P2-2 FUP：update_params 需熱重載 OI 三欄位；get_params 回吐新值。
    #[test]
    fn test_oi_params_update_hot_reloads() {
        let mut s = BbBreakout::new();
        // Baseline defaults — document the pre-EDGE-P2-2 bit-identical floor.
        // 預設值—記錄 pre-EDGE-P2-2 bit-identical 基線。
        assert!(!s.enable_oi_signal, "default enable_oi_signal must be false");
        assert_eq!(
            s.oi_buffer_window_ms, 60_000,
            "default oi_buffer_window_ms must be 60_000"
        );
        assert!(
            (s.oi_confluence_bonus - 0.10).abs() < f64::EPSILON,
            "default oi_confluence_bonus must be 0.10"
        );

        let mut p = BbBreakoutParams::default();
        p.enable_oi_signal = true;
        p.oi_buffer_window_ms = 30_000;
        p.oi_confluence_bonus = 0.25;
        s.update_params(p.clone()).expect("valid OI params");

        // Runtime fields reflect the hot-reloaded values.
        // 運行時欄位反映熱重載後的值。
        assert!(s.enable_oi_signal, "flag must hot-reload to true");
        assert_eq!(s.oi_buffer_window_ms, 30_000, "window ms must hot-reload");
        assert!((s.oi_confluence_bonus - 0.25).abs() < f64::EPSILON);

        // get_params round-trip echoes the mutated values.
        // get_params 回吐後須等同變更值。
        let back = s.get_params();
        assert!(back.enable_oi_signal);
        assert_eq!(back.oi_buffer_window_ms, 30_000);
        assert!((back.oi_confluence_bonus - 0.25).abs() < f64::EPSILON);
    }

    /// EDGE-P2-2 FUP: JSON round-trip — serialize → mutate → update_params_json
    /// must apply the 3 OI fields to the live runtime (ConfigStore Agent path).
    /// EDGE-P2-2 FUP：JSON 往返 — 序列化→修改→update_params_json 熱重載 OI 三欄位。
    #[test]
    fn test_oi_params_json_round_trip() {
        use crate::strategies::Strategy;

        let mut s = BbBreakout::new();
        // Serialize defaults.
        let json_v0 = s.get_params_json();
        assert!(
            !json_v0.is_empty(),
            "get_params_json must emit non-empty string"
        );

        // Deserialize, mutate OI fields, re-serialize.
        let mut p: BbBreakoutParams =
            serde_json::from_str(&json_v0).expect("default params must deserialize");
        p.enable_oi_signal = true;
        p.oi_buffer_window_ms = 15_000;
        p.oi_confluence_bonus = 0.33;
        let json_v1 = serde_json::to_string(&p).expect("params must serialize");

        // Apply via the Strategy-trait JSON path.
        s.update_params_json(&json_v1)
            .expect("valid JSON params must hot-reload");

        // Runtime reflects the mutated JSON values.
        assert!(s.enable_oi_signal);
        assert_eq!(s.oi_buffer_window_ms, 15_000);
        assert!((s.oi_confluence_bonus - 0.33).abs() < f64::EPSILON);

        // And round-trip back through get_params_json.
        let json_v2 = s.get_params_json();
        let back: BbBreakoutParams =
            serde_json::from_str(&json_v2).expect("round-trip JSON must deserialize");
        assert!(back.enable_oi_signal);
        assert_eq!(back.oi_buffer_window_ms, 15_000);
        assert!((back.oi_confluence_bonus - 0.33).abs() < f64::EPSILON);
    }

    // ════════════════════════════════════════════════════════════════════════
    // EDGE-P2-2: Open Interest (OI) confluence signal tests
    // EDGE-P2-2：OI 合流信號單元測試
    // ════════════════════════════════════════════════════════════════════════

    use openclaw_core::indicators::{AdxResult, DonchianResult, IndicatorSnapshot as IS};

    /// Build a context with custom OI value (kept separate from `ctx_ext` to
    /// preserve bit-identical behaviour for all non-OI callers).
    /// 建立帶 OI 的 context；與 `ctx_ext` 分開避免改動既有調用點的位元等價性。
    fn ctx_oi(
        bw: f64,
        pct_b: f64,
        vol: f64,
        ts: u64,
        price: f64,
        open_interest: Option<f64>,
    ) -> TickContext<'static> {
        let ind = Box::leak(Box::new(IS {
            bollinger: Some(BollingerResult {
                upper: 51000.0,
                middle: 50000.0,
                lower: 49000.0,
                bandwidth: bw,
                percent_b: pct_b,
            }),
            volume_ratio: Some(vol),
            ..Default::default()
        }));
        TickContext {
            symbol: "BTC",
            price,
            timestamp_ms: ts,
            indicators: Some(ind),
            signals: &[],
            h0_allowed: true,
            funding_rate: None,
            index_price: None,
            open_interest,
        }
    }

    /// Full-indicator context for end-to-end confluence testing (ADX + Donchian +
    /// volume). Simulates a clean breakout setup with OI override.
    /// 完整指標 context（ADX + Donchian + volume）用於端到端 confluence 測試。
    fn ctx_full_entry(
        bw: f64,
        pct_b: f64,
        vol: f64,
        ts: u64,
        price: f64,
        open_interest: Option<f64>,
    ) -> TickContext<'static> {
        let ind = Box::leak(Box::new(IS {
            bollinger: Some(BollingerResult {
                upper: 51000.0,
                middle: 50000.0,
                lower: 49000.0,
                bandwidth: bw,
                percent_b: pct_b,
            }),
            volume_ratio: Some(vol),
            adx: Some(AdxResult {
                adx: 30.0,
                plus_di: 25.0,
                minus_di: 15.0,
            }),
            rsi_14: Some(55.0),
            donchian: Some(DonchianResult {
                upper: 50500.0,
                lower: 49500.0,
                middle: 50000.0,
                width: 1000.0,
            }),
            ..Default::default()
        }));
        TickContext {
            symbol: "BTC",
            price,
            timestamp_ms: ts,
            indicators: Some(ind),
            signals: &[],
            h0_allowed: true,
            funding_rate: None,
            index_price: None,
            open_interest,
        }
    }

    /// Helper: direct-construct a per-symbol state populated with OI samples.
    /// 輔助：直接構造帶 OI 樣本的 per-symbol 狀態。
    fn state_with_oi(samples: &[(u64, f64)]) -> BbBreakoutPerSymbolState {
        let mut st = BbBreakoutPerSymbolState::default();
        for (ts, oi) in samples {
            st.oi_buffer.push_back((*ts, *oi));
        }
        st
    }

    /// TEST 1: oi_buffer fills on every ticker event carrying OI and evicts
    /// samples older than the configured window (saturating_sub guards regress).
    /// 測試 1：每個帶 OI 的 ticker 入隊，超出窗口者從前端淘汰。
    #[test]
    fn test_oi_buffer_fills_and_evicts() {
        let mut s = BbBreakout::new();
        s.oi_buffer_window_ms = 60_000; // 60s rolling window
        // Feed 10 samples every 12s → span = 108s > 60s window.
        // 每 12s 入一筆，共 10 筆，跨 108s > 60s 窗口。
        for i in 0..10u64 {
            let ts = i * 12_000;
            // Use squeeze-neutral bandwidth; this exercises the buffer path only.
            // 用普通帶寬只驗 buffer 路徑。
            s.on_tick(&ctx_oi(0.03, 0.5, 1.0, ts, 50000.0, Some(100.0 + i as f64)));
        }
        let st = s.symbols.get("BTC").expect("symbol tracked");
        // Newest ts = 108_000; anything older than (108_000 - 60_000) = 48_000 evicted.
        // 最新 108_000；< 48_000 者淘汰 → 保留 ts ≥ 48_000 共 5 筆 (48,60,72,84,96,108) = 6 筆。
        for (ts, _) in st.oi_buffer.iter() {
            assert!(*ts >= 48_000, "sample ts {ts} should have been evicted");
        }
        assert!(st.oi_buffer.len() <= 10, "must not exceed push count");
        assert!(
            st.oi_buffer.len() >= 2,
            "window should retain at least newest + one previous sample"
        );
    }

    /// TEST 2: basic (newest - oldest)/oldest delta = 10% when oi goes 100→110.
    /// 測試 2：基本差分 100→110 = +10%。
    #[test]
    fn test_oi_delta_pct_basic() {
        let st = state_with_oi(&[(0, 100.0), (30_000, 105.0), (60_000, 110.0)]);
        let d = st.compute_oi_delta_pct().expect("delta available");
        assert!((d - 0.10).abs() < 1e-12, "expected +0.10, got {d}");
    }

    /// TEST 3: single sample → None (cannot compute delta).
    /// 測試 3：單一樣本 → None（無法計算差分）。
    #[test]
    fn test_oi_delta_pct_insufficient_samples() {
        let st = state_with_oi(&[(0, 100.0)]);
        assert!(st.compute_oi_delta_pct().is_none());
        // And empty buffer also None.
        // 空 buffer 亦應 None。
        let empty = BbBreakoutPerSymbolState::default();
        assert!(empty.compute_oi_delta_pct().is_none());
    }

    /// TEST 4: oldest == 0 → None (guard against div-by-zero; no panic).
    /// 測試 4：oldest == 0 → None（防除以零，不 panic）。
    #[test]
    fn test_oi_delta_pct_zero_guard() {
        let st = state_with_oi(&[(0, 0.0), (30_000, 50.0)]);
        assert!(st.compute_oi_delta_pct().is_none());
        // Negative oldest also rejected (unusual but defensive).
        // 負數 oldest 亦拒絕（防守式檢查）。
        let st_neg = state_with_oi(&[(0, -5.0), (30_000, 50.0)]);
        assert!(st_neg.compute_oi_delta_pct().is_none());
    }

    /// TEST 5: flag=false → bit-identical behaviour to pre-EDGE-P2-2 baseline.
    /// Run two strategy instances (one with OI feeds, one without) and assert
    /// the emitted intent confluence_score is identical when flag is disabled.
    /// 測試 5：flag=false → 與舊基線 bit-identical。
    #[test]
    fn test_confluence_bonus_disabled_by_default() {
        let mut baseline = BbBreakout::new();
        baseline.min_persistence_ms = 0;
        assert!(!baseline.enable_oi_signal, "default must be OFF");

        let mut with_oi = BbBreakout::new();
        with_oi.min_persistence_ms = 0;
        assert!(!with_oi.enable_oi_signal, "default must be OFF");

        // Seed squeeze on both.
        // 雙方都先進入壓縮。
        baseline.on_tick(&ctx_full_entry(0.01, 0.5, 1.0, 0, 50000.0, None));
        with_oi.on_tick(&ctx_full_entry(0.01, 0.5, 1.0, 0, 50000.0, Some(100.0)));

        // Feed mid-tick with OI climb (only affects buffer, not score, because flag=false).
        // 中途加入 OI 上升樣本（flag=false 時不應影響 score）。
        with_oi.on_tick(&ctx_full_entry(0.02, 0.5, 1.0, 300_000, 50000.0, Some(110.0)));

        // Breakout tick (long).
        // 突破 tick（多頭）。
        let i_baseline = baseline.on_tick(&ctx_full_entry(0.05, 1.1, 2.0, 700_000, 51000.0, None));
        let i_oi = with_oi.on_tick(&ctx_full_entry(
            0.05,
            1.1,
            2.0,
            700_000,
            51000.0,
            Some(120.0),
        ));
        assert_eq!(i_baseline.len(), 1);
        assert_eq!(i_oi.len(), 1);
        let (sb, so) = match (&i_baseline[0], &i_oi[0]) {
            (StrategyAction::Open(a), StrategyAction::Open(b)) => {
                (a.confluence_score, b.confluence_score)
            }
            _ => panic!("expected Open intents"),
        };
        // Bit-identical (both Some or both None; if Some, equal bits).
        // bit-identical：同為 Some 且 bits 相等，或同為 None。
        match (sb, so) {
            (Some(a), Some(b)) => assert_eq!(
                a.to_bits(),
                b.to_bits(),
                "confluence_score must be bit-identical when flag=false"
            ),
            (None, None) => {}
            other => panic!("confluence_score mismatch: {:?}", other),
        }
    }

    /// TEST 6: flag=on + rising OI + bullish signal → confluence_score shifted
    /// up by exactly `oi_confluence_bonus` relative to the same tick sequence
    /// with OI held constant.
    /// 測試 6：flag=on + OI 上升 + 多頭 → confluence_score 較 OI 無變化者高 +bonus。
    #[test]
    fn test_confluence_bonus_applied_when_flag_on() {
        // Two instances: both OI-enabled, one with OI rising, one flat.
        // 兩個實例：都啟用 OI，一個 OI 上升、一個持平。
        let mut rising = BbBreakout::new();
        rising.min_persistence_ms = 0;
        rising.enable_oi_signal = true;
        rising.oi_confluence_bonus = 0.10;
        rising.oi_buffer_window_ms = 600_000;

        let mut flat = BbBreakout::new();
        flat.min_persistence_ms = 0;
        flat.enable_oi_signal = true;
        flat.oi_confluence_bonus = 0.10;
        flat.oi_buffer_window_ms = 600_000;

        // Squeeze tick (same OI base on both).
        // 壓縮 tick（兩者 OI 相同基準）。
        rising.on_tick(&ctx_full_entry(0.01, 0.5, 1.0, 0, 50000.0, Some(100.0)));
        flat.on_tick(&ctx_full_entry(0.01, 0.5, 1.0, 0, 50000.0, Some(100.0)));
        // Mid tick — rising climbs, flat holds.
        // 中段：rising 上升，flat 不變。
        rising.on_tick(&ctx_full_entry(0.02, 0.5, 1.0, 300_000, 50000.0, Some(110.0)));
        flat.on_tick(&ctx_full_entry(0.02, 0.5, 1.0, 300_000, 50000.0, Some(100.0)));
        // Breakout long on both.
        // 突破多頭。
        let i_rising = rising.on_tick(&ctx_full_entry(
            0.05,
            1.1,
            2.0,
            700_000,
            51000.0,
            Some(120.0),
        ));
        let i_flat = flat.on_tick(&ctx_full_entry(
            0.05,
            1.1,
            2.0,
            700_000,
            51000.0,
            Some(100.0),
        ));
        assert_eq!(i_rising.len(), 1);
        assert_eq!(i_flat.len(), 1);
        let (sr, sf) = match (&i_rising[0], &i_flat[0]) {
            (StrategyAction::Open(a), StrategyAction::Open(b)) => (
                a.confluence_score.expect("score present"),
                b.confluence_score.expect("score present"),
            ),
            _ => panic!("expected Open intents"),
        };
        let diff = sr - sf;
        // Rising OI confirms long → bonus applied; flat → no bonus.
        // OI 上升確認多頭加 bonus；OI 不變（delta=0）不加；差異 ≈ bonus。
        // NOTE: confluence_score is stored as f32 in OrderIntent (EDGE-P3-1 A6),
        // so tolerance is relaxed to accommodate single-precision cast error.
        // 備註：OrderIntent.confluence_score 為 f32，放寬容差以容納 f32 cast 誤差。
        assert!(
            (diff - 0.10).abs() < 1e-4,
            "expected confluence_score diff ≈ +0.10, got {diff}"
        );
    }

    /// TEST 7: flag=on + falling OI + bullish signal (divergence) → score
    /// shifted DOWN by `oi_confluence_bonus` vs the flat-OI control.
    /// 測試 7：flag=on + OI 下降 + 多頭（背離）→ confluence_score 較對照組低 -bonus。
    #[test]
    fn test_confluence_penalty_on_divergence() {
        let mut falling = BbBreakout::new();
        falling.min_persistence_ms = 0;
        falling.enable_oi_signal = true;
        falling.oi_confluence_bonus = 0.10;
        falling.oi_buffer_window_ms = 600_000;

        let mut flat = BbBreakout::new();
        flat.min_persistence_ms = 0;
        flat.enable_oi_signal = true;
        flat.oi_confluence_bonus = 0.10;
        flat.oi_buffer_window_ms = 600_000;

        // Squeeze baseline.
        falling.on_tick(&ctx_full_entry(0.01, 0.5, 1.0, 0, 50000.0, Some(100.0)));
        flat.on_tick(&ctx_full_entry(0.01, 0.5, 1.0, 0, 50000.0, Some(100.0)));
        // Mid: falling drops, flat holds.
        falling.on_tick(&ctx_full_entry(0.02, 0.5, 1.0, 300_000, 50000.0, Some(95.0)));
        flat.on_tick(&ctx_full_entry(0.02, 0.5, 1.0, 300_000, 50000.0, Some(100.0)));
        // Breakout long on both.
        let i_falling = falling.on_tick(&ctx_full_entry(
            0.05,
            1.1,
            2.0,
            700_000,
            51000.0,
            Some(90.0),
        ));
        let i_flat = flat.on_tick(&ctx_full_entry(
            0.05,
            1.1,
            2.0,
            700_000,
            51000.0,
            Some(100.0),
        ));
        let (sfall, sflat) = match (&i_falling[0], &i_flat[0]) {
            (StrategyAction::Open(a), StrategyAction::Open(b)) => (
                a.confluence_score.expect("score present"),
                b.confluence_score.expect("score present"),
            ),
            _ => panic!("expected Open intents"),
        };
        let diff = sfall - sflat;
        // Falling OI + long = divergence → -bonus; flat delta=0 → no change.
        // OI 下降 + 多頭 = 背離扣 bonus；flat delta=0 不變；差異 ≈ -bonus。
        // f32 cast tolerance as above.
        assert!(
            (diff - (-0.10)).abs() < 1e-4,
            "expected confluence_score diff ≈ -0.10, got {diff}"
        );
    }

    /// TEST 8: validate() rejects out-of-range OI parameters.
    /// 測試 8：validate() 拒絕超出範圍的 OI 參數。
    #[test]
    fn test_oi_params_validation() {
        let mut p = BbBreakoutParams::default();
        // Window too short.
        // 窗口太短。
        p.oi_buffer_window_ms = 500;
        assert!(p.validate().is_err(), "window < 1000ms must fail");
        p.oi_buffer_window_ms = 60_000;
        // Bonus out of bounds.
        // bonus 超界。
        p.oi_confluence_bonus = 0.6;
        assert!(p.validate().is_err(), "|bonus| > 0.5 must fail");
        p.oi_confluence_bonus = f64::NAN;
        assert!(p.validate().is_err(), "NaN bonus must fail");
        p.oi_confluence_bonus = 0.10;
        assert!(p.validate().is_ok(), "defaults must pass");
    }

    // ════════════════════════════════════════════════════════════════════════
    // EDGE-P2-2 FUP (E2 findings #1 #2 #3 #5 #6): regression tests
    // EDGE-P2-2 FUP（E2 #1 #2 #3 #5 #6）：回歸測試
    // ════════════════════════════════════════════════════════════════════════

    fn make_open_intent(symbol: &str) -> OrderIntent {
        OrderIntent {
            symbol: symbol.into(),
            is_long: true,
            qty: 0.01,
            confidence: 0.6,
            strategy: "bb_breakout".into(),
            order_type: "market".into(),
            limit_price: None,
            confluence_score: None,
            persistence_elapsed_ms: None,
            time_in_force: None,
            maker_timeout_ms: None,
        }
    }

    /// FUP #1: identical OI values must dedup so trade-tick replays don't
    /// dilute the rolling window (change-of-state semantics).
    /// FUP #1：相同 OI 值必須 dedup，避免 trade-tick 重播稀釋窗口。
    #[test]
    fn test_oi_buffer_deduplicates_same_value() {
        let mut s = BbBreakout::new();
        s.oi_buffer_window_ms = 60_000;
        s.on_tick(&ctx_oi(0.03, 0.5, 1.0, 0, 50000.0, Some(100.0)));
        s.on_tick(&ctx_oi(0.03, 0.5, 1.0, 1_000, 50000.0, Some(100.0)));
        s.on_tick(&ctx_oi(0.03, 0.5, 1.0, 2_000, 50000.0, Some(100.0)));
        let st = s.symbols.get("BTC").expect("symbol tracked");
        assert_eq!(
            st.oi_buffer.len(),
            1,
            "repeated identical OI values must be deduped; got {}",
            st.oi_buffer.len()
        );
        // A genuine change should push a new sample.
        // 真實變動必須入隊。
        s.on_tick(&ctx_oi(0.03, 0.5, 1.0, 3_000, 50000.0, Some(100.0001)));
        let st = s.symbols.get("BTC").unwrap();
        assert_eq!(st.oi_buffer.len(), 2, "change-of-state must append");
    }

    /// FUP #6: out-of-order or regressed timestamps (cross-stream interleave)
    /// must be rejected — strict monotonic push guard.
    /// FUP #6：亂序 / 回溯 ts（跨 stream 交錯）必須被拒絕，嚴格單調入隊。
    #[test]
    fn test_oi_buffer_skips_ts_regression() {
        let mut s = BbBreakout::new();
        s.oi_buffer_window_ms = 60_000;
        s.on_tick(&ctx_oi(0.03, 0.5, 1.0, 10_000, 50000.0, Some(100.0)));
        // Stale sample with older ts → must be dropped even though OI changed.
        // 舊 ts（即使 OI 變動）必須丟棄。
        s.on_tick(&ctx_oi(0.03, 0.5, 1.0, 5_000, 50000.0, Some(95.0)));
        // Equal ts → must also drop (strict >).
        // 相同 ts → 也丟（嚴格 >）。
        s.on_tick(&ctx_oi(0.03, 0.5, 1.0, 10_000, 50000.0, Some(105.0)));
        let st = s.symbols.get("BTC").expect("symbol tracked");
        assert_eq!(st.oi_buffer.len(), 1, "ts regressions must not push");
        let (ts, oi) = *st.oi_buffer.back().unwrap();
        assert_eq!(ts, 10_000);
        assert!((oi - 100.0).abs() < f64::EPSILON);
    }

    /// FUP #2: `on_rejection` must preserve the live `oi_buffer` (market
    /// observation) while rolling back trading-state fields.
    /// FUP #2：on_rejection 僅回滾策略狀態，oi_buffer（市場觀察）必須保留。
    #[test]
    fn test_on_rejection_preserves_oi_buffer() {
        use crate::strategies::Strategy;

        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0;
        s.oi_buffer_window_ms = 600_000;
        // Seed squeeze → OI sample #1.
        s.on_tick(&ctx_full_entry(0.01, 0.5, 1.0, 0, 50000.0, Some(100.0)));
        // Mid tick → OI sample #2 (change of state pushes).
        s.on_tick(&ctx_full_entry(0.02, 0.5, 1.0, 10_000, 50000.0, Some(105.0)));
        // Breakout tick → emits Open intent + stashes prev_state snapshot.
        let actions = s.on_tick(&ctx_full_entry(
            0.05,
            1.1,
            2.0,
            20_000,
            51000.0,
            Some(110.0),
        ));
        assert!(
            matches!(actions.first(), Some(StrategyAction::Open(_))),
            "expected Open intent on breakout tick"
        );
        let buf_len_before = s.symbols.get("BTC").unwrap().oi_buffer.len();
        assert!(buf_len_before >= 2, "buffer must have samples");

        // Reject → trading state rolls back; oi_buffer must NOT.
        // 拒絕 → 交易狀態回滾；oi_buffer 不能丟。
        let intent = make_open_intent("BTC");
        s.on_rejection(&intent, "test rejection");

        let buf_after = &s.symbols.get("BTC").expect("symbol still tracked").oi_buffer;
        assert_eq!(
            buf_after.len(),
            buf_len_before,
            "oi_buffer must be preserved across rollback (market observation, not strategy state)"
        );
        // Values/ts must be byte-identical.
        let back = *buf_after.back().unwrap();
        assert_eq!(back.0, 20_000);
        assert!((back.1 - 110.0).abs() < f64::EPSILON);
    }

    /// FUP #3 (noise floor) + FUP #2 (buffer preserved) — if
    /// `|oi_delta_pct| <= oi_min_delta_pct`, bonus must NOT apply and the
    /// score equals the flat-OI control bit-for-bit (when both paths are at
    /// the same suppression regime).
    /// FUP #3：|oi_delta_pct| ≤ noise floor 時 bonus 不施加，與 flat 對照組相同。
    #[test]
    fn test_oi_min_delta_pct_below_threshold_no_effect() {
        let mut guarded = BbBreakout::new();
        guarded.min_persistence_ms = 0;
        guarded.enable_oi_signal = true;
        guarded.oi_confluence_bonus = 0.10;
        guarded.oi_buffer_window_ms = 600_000;
        // Noise floor 5% — OI must change by more than 5% to contribute.
        // 噪音地板 5% — OI 必須 >5% 變動才貢獻 bonus。
        guarded.oi_min_delta_pct = 0.05;

        let mut flat = BbBreakout::new();
        flat.min_persistence_ms = 0;
        flat.enable_oi_signal = true;
        flat.oi_confluence_bonus = 0.10;
        flat.oi_buffer_window_ms = 600_000;
        flat.oi_min_delta_pct = 0.05;

        // Squeeze baseline.
        guarded.on_tick(&ctx_full_entry(0.01, 0.5, 1.0, 0, 50000.0, Some(100.0)));
        flat.on_tick(&ctx_full_entry(0.01, 0.5, 1.0, 0, 50000.0, Some(100.0)));
        // Mid-tick: guarded rises 2% (< floor); flat stays.
        // 中段：guarded 上升 2%（< 地板）；flat 不動。
        guarded.on_tick(&ctx_full_entry(0.02, 0.5, 1.0, 300_000, 50000.0, Some(102.0)));
        flat.on_tick(&ctx_full_entry(0.02, 0.5, 1.0, 300_000, 50000.0, Some(100.0)));
        // Breakout long.
        let i_g = guarded.on_tick(&ctx_full_entry(
            0.05,
            1.1,
            2.0,
            700_000,
            51000.0,
            Some(102.0),
        ));
        let i_f = flat.on_tick(&ctx_full_entry(
            0.05,
            1.1,
            2.0,
            700_000,
            51000.0,
            Some(100.0),
        ));
        let (sg, sf) = match (&i_g[0], &i_f[0]) {
            (StrategyAction::Open(a), StrategyAction::Open(b)) => (
                a.confluence_score.expect("score present"),
                b.confluence_score.expect("score present"),
            ),
            _ => panic!("expected Open intents"),
        };
        // Below floor → bonus suppressed → equal to flat control (f32 bit-identical).
        // 低於地板 → bonus 被壓制 → 與 flat 相等（f32 bit-identical）。
        assert_eq!(
            sg.to_bits(),
            sf.to_bits(),
            "below noise floor, score must match flat control exactly"
        );
    }

    /// FUP #5: validate() must reject `oi_buffer_window_ms` above upper bound
    /// (600_000 ms / 10 min) — prevents memory blow-up scenarios.
    /// FUP #5：validate() 須拒絕 window > 600_000ms（防記憶體膨脹）。
    #[test]
    fn test_oi_window_upper_bound_validation() {
        let mut p = BbBreakoutParams::default();
        p.oi_buffer_window_ms = 600_001;
        assert!(
            p.validate().is_err(),
            "window > 600_000ms must fail"
        );
        p.oi_buffer_window_ms = 600_000;
        assert!(p.validate().is_ok(), "exact upper bound must pass");
    }

    /// FUP #3: validate() must enforce `oi_min_delta_pct` ∈ [0.0, 0.5] and
    /// reject NaN/Inf.
    /// FUP #3：validate() 須強制 oi_min_delta_pct 在 [0.0, 0.5] 且非 NaN/Inf。
    #[test]
    fn test_oi_min_delta_pct_validation() {
        let mut p = BbBreakoutParams::default();
        p.oi_min_delta_pct = -0.01;
        assert!(p.validate().is_err(), "negative floor must fail");
        p.oi_min_delta_pct = 0.51;
        assert!(p.validate().is_err(), "floor > 0.5 must fail");
        p.oi_min_delta_pct = f64::NAN;
        assert!(p.validate().is_err(), "NaN floor must fail");
        p.oi_min_delta_pct = 0.0;
        assert!(p.validate().is_ok(), "0.0 (default) must pass");
        p.oi_min_delta_pct = 0.5;
        assert!(p.validate().is_ok(), "0.5 upper bound must pass");
    }

    // ── EDGE-P2-3 Phase 2+: PostOnly maker entry tests ──
    // ── EDGE-P2-3 Phase 2+：PostOnly maker 入場測試 ──

    /// When `use_maker_entry=false` (default), the entry intent keeps the legacy
    /// Market shape: order_type="market", limit_price=None, TIF=None, maker_timeout_ms=None.
    /// Byte-identical to pre-Phase-2+ behaviour.
    /// 當 use_maker_entry=false（默認）時，入場意圖維持原本 Market 形態；與 Phase 2+ 之前 byte-identical。
    #[test]
    fn test_bb_breakout_market_entry_when_maker_disabled() {
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0; // disable persistence gate for unit test
        assert!(!s.use_maker_entry, "use_maker_entry must default to false");
        // Squeeze then expansion long breakout (mirrors test_squeeze_then_breakout).
        // 先壓縮再擴張多頭突破（與 test_squeeze_then_breakout 同模式）。
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0));
        let i = s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Open(intent) => {
                assert_eq!(intent.order_type, "market");
                assert!(intent.limit_price.is_none());
                assert!(intent.time_in_force.is_none());
                assert!(intent.maker_timeout_ms.is_none());
            }
            other => panic!("expected Open, got {:?}", other),
        }
    }

    /// Long breakout with maker enabled emits PostOnly Limit below last_price.
    /// Offset 2 bps → limit = price * (1 - 2/10_000). Bit-exact.
    /// 多頭突破且 maker 啟用 → PostOnly Limit 掛在 last_price 下方（2 bps）。
    #[test]
    fn test_bb_breakout_buy_postonly_below_last_price() {
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0;
        s.use_maker_entry = true;
        s.maker_price_offset_bps = 2.0; // 2 bps for bit-exact math check
        s.maker_limit_timeout_ms = 45_000;
        // Long setup: pctb=1.1 > 1.0 -> is_long
        // 多頭設置：pctb=1.1 > 1.0 → is_long
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0));
        let i = s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Open(intent) => {
                assert!(intent.is_long);
                assert_eq!(intent.order_type, "limit");
                assert_eq!(intent.time_in_force, Some(TimeInForce::PostOnly));
                assert_eq!(intent.maker_timeout_ms, Some(45_000));
                let lp = intent.limit_price.expect("limit_price set");
                let expected = 50000.0 * (1.0 - 2.0 / 10_000.0);
                assert!(
                    (lp - expected).abs() < 1e-9,
                    "buy PostOnly must be below last_price: got {lp}, expected {expected}"
                );
                assert!(lp < 50000.0, "buy limit must rest below last_price");
            }
            other => panic!("expected Open, got {:?}", other),
        }
    }

    /// Short breakout with maker enabled emits PostOnly Limit above last_price.
    /// 空頭突破且 maker 啟用 → PostOnly Limit 掛在 last_price 上方。
    #[test]
    fn test_bb_breakout_sell_postonly_above_last_price() {
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0;
        s.use_maker_entry = true;
        s.maker_price_offset_bps = 2.0; // 2 bps
        s.maker_limit_timeout_ms = 45_000;
        // Short setup: pctb=-0.1 < 0.0 -> is_short
        // 空頭設置：pctb=-0.1 < 0.0 → is_short
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0));
        let i = s.on_tick(&ctx(0.05, -0.1, 2.0, 700_000));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Open(intent) => {
                assert!(!intent.is_long);
                assert_eq!(intent.order_type, "limit");
                assert_eq!(intent.time_in_force, Some(TimeInForce::PostOnly));
                assert_eq!(intent.maker_timeout_ms, Some(45_000));
                let lp = intent.limit_price.expect("limit_price set");
                let expected = 50000.0 * (1.0 + 2.0 / 10_000.0);
                assert!(
                    (lp - expected).abs() < 1e-9,
                    "sell PostOnly must be above last_price: got {lp}, expected {expected}"
                );
                assert!(lp > 50000.0, "sell limit must rest above last_price");
            }
            other => panic!("expected Open, got {:?}", other),
        }
    }

    /// update_params round-trips maker fields for Agent IPC hot-reload, and the
    /// maker_limit_timeout_ms clamp invariant [15_000, 300_000] is enforced at
    /// assignment. Tests both extremes (1_000 → 15_000, 500_000 → 300_000).
    /// update_params 回吐 maker 欄位供 Agent IPC 熱重載；maker_limit_timeout_ms 寫入時
    /// clamp 至 [15_000, 300_000]；驗證兩端（1_000→15_000、500_000→300_000）。
    #[test]
    fn test_bb_breakout_update_params_roundtrips_maker_fields() {
        let mut s = BbBreakout::new();
        let mut p = s.get_params();
        assert!(!p.use_maker_entry, "default must be false");
        // In-band round-trip: flag + offset + in-range timeout.
        // 在有效區間內的往返：旗標 + offset + timeout。
        p.use_maker_entry = true;
        p.maker_price_offset_bps = 3.0;
        p.maker_limit_timeout_ms = 60_000;
        s.update_params(p.clone()).expect("valid params");
        let back = s.get_params();
        assert!(back.use_maker_entry);
        assert!((back.maker_price_offset_bps - 3.0).abs() < 1e-9);
        assert_eq!(back.maker_limit_timeout_ms, 60_000);
        // Runtime fields reflect the update.
        // 運行時欄位亦已更新。
        assert!(s.use_maker_entry);
        assert!((s.maker_price_offset_bps - 3.0).abs() < 1e-9);
        assert_eq!(s.maker_limit_timeout_ms, 60_000);

        // Upper-bound clamp: 500_000 → 300_000.
        // 上限 clamp：500_000 → 300_000。
        let mut p_hi = s.get_params();
        p_hi.maker_limit_timeout_ms = 500_000;
        s.update_params(p_hi).expect("valid params");
        assert_eq!(s.get_params().maker_limit_timeout_ms, 300_000);

        // Lower-bound clamp: 1_000 → 15_000.
        // 下限 clamp：1_000 → 15_000。
        let mut p_lo = s.get_params();
        p_lo.maker_limit_timeout_ms = 1_000;
        s.update_params(p_lo).expect("valid params");
        assert_eq!(s.get_params().maker_limit_timeout_ms, 15_000);
    }
}
