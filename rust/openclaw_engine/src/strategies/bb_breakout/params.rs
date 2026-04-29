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

/// P1-11 (2): how the Donchian-channel breach condition combines with the
/// BB-core gates (squeeze / expansion / volume).
///
/// - `Hard` (default, bit-identical to baseline): price must breach Donchian
///   in the entry direction or the tick is hard-rejected (`return vec![]`).
/// - `Score`: breach adds `+donchian_score_bonus` to the confluence score;
///   miss subtracts the same. Entry path is NOT hard-rejected — downstream
///   confluence gate (`confluence_as_gate` + thresholds) decides. Softens the
///   5-AND chain documented in TODO §P1-11 (BB-BREAKOUT/REVERSION-DORMANT-1).
/// - `Off`: Donchian check skipped entirely (score unmodified). For A/B
///   measuring Donchian's contribution vs the 4-gate chain alone.
///
/// P1-11 (2)：Donchian 通道與 BB 核心三閘（壓縮/擴張/成交量）的結合方式。
/// - `Hard` 預設與基線 bit-identical：方向不突破即硬拒。
/// - `Score`：突破加 `+donchian_score_bonus` 到合流分；未突破扣同量。不硬拒，
///   由下游合流閘（`confluence_as_gate` + thresholds）最終仲裁。軟化 TODO
///   §P1-11 記錄的 5-AND chain，為 dormant 策略開放信號面。
/// - `Off`：完全跳過 Donchian 檢查（score 不改）。A/B 用於量化 Donchian 貢獻。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum DonchianMode {
    /// Hard AND gate (baseline, bit-identical). / 硬 AND 閘（基線，bit-identical）。
    #[default]
    Hard,
    /// Soft score contribution: breach = +bonus, miss = -bonus. / 軟評分貢獻。
    Score,
    /// Skip Donchian entirely. / 完全跳過 Donchian。
    Off,
}

/// P1-11 (3): A/B profile preset for BB Breakout thresholds. Consumers call
/// `BbBreakoutParams::for_profile(...)` to get a fully-populated params struct
/// with profile-adjusted bandwidth / volume / persistence gates, then feed it
/// through the normal `update_params` hot-reload path.
///
/// - `Conservative`: tightest squeeze + widest expansion gap + highest volume
///   + longest persistence — few signals, high-confidence breakouts.
/// - `Balanced` (default): current production defaults (EDGE-P1-4 tuned).
///   `for_profile(Balanced) == default()` — verified by test.
/// - `Aggressive`: loosest squeeze + narrow gap + lowest volume + shortest
///   persistence — many signals at lower confidence; paired with `Score`
///   DonchianMode is the recommended dormant-strategy rescue path.
///
/// Profile is NOT hot-reloadable in the strict sense — switching changes
/// strategy semantics, so A/B by swapping TOML + `restart_all.sh --rebuild`
/// (or via IPC `update_params` in demo only). The `for_profile` helper keeps
/// all non-profile fields at `Default` so operators can layer custom overrides
/// on top (e.g., `{ ..BbBreakoutParams::for_profile(Aggressive), volume_threshold: 1.10 }`).
///
/// P1-11 (3)：BB Breakout 閾值 A/B profile 預設。呼叫 `for_profile` 拿到已填滿
/// 的 params，餵進 `update_params` 熱重載。
/// - `Conservative`：最嚴 squeeze + 最寬 gap + 最高 volume + 最長 persistence，
///   信號稀少但高信心。
/// - `Balanced`（預設）：當前生產預設（EDGE-P1-4 調校後）。`for_profile(Balanced)
///   == default()`，測試固化。
/// - `Aggressive`：最鬆 squeeze + 窄 gap + 最低 volume + 最短 persistence，信號多
///   但信心低；建議搭配 `DonchianMode::Score` 作 dormant 策略救援組合。
//
// G2-06 (2026-04-26): strategy permanently disabled at TOML level (active=false).
// BbBreakoutProfile retained for future 5m timeframe RFC if PA approves.
// G2-06（2026-04-26）：策略已於 TOML 層永久 disable（active=false）。
// BbBreakoutProfile 保留為日後若 PA approve 升 5m timeframe 時可用。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum BbBreakoutProfile {
    /// Strict gates — few signals, high-confidence. / 嚴格門控，信號少但信心高。
    Conservative,
    /// Current production defaults (EDGE-P1-4 tuned). / 當前生產預設。
    #[default]
    Balanced,
    /// Loose gates — many signals, lower confidence. / 寬鬆門控，信號多但信心低。
    Aggressive,
}

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
    /// G7-09c Phase 1: ticks INSIDE the inside quote at which the BBO-aware
    /// PostOnly limit sits. Default 1 (one tick more passive than best_bid/ask).
    /// When BBO or tick_size are unavailable, maker entries are skipped instead
    /// of falling back to last_price. Bounded `[0, 10]` by `validate()`.
    /// G7-09c Phase 1：BBO-aware PostOnly 限價離 inside quote 的 tick 數，預設 1。
    /// BBO 或 tick_size 不可得時跳過 maker 入場，不再 fallback 到 last_price。
    /// `validate()` 限 `[0, 10]`。
    pub maker_price_buffer_ticks: u32,
    /// P1-11 (2): how Donchian breach combines with the BB-core 3-gate chain.
    /// Default `Hard` → bit-identical to baseline. `Score` softens to confluence
    /// contribution, `Off` disables Donchian check entirely.
    /// P1-11 (2)：Donchian 突破與 BB 核心三閘的結合方式。預設 `Hard` bit-identical；
    /// `Score` 軟化為合流評分貢獻，`Off` 完全跳過。
    pub donchian_mode: DonchianMode,
    /// P1-11 (2): score delta added on Donchian breach confirmation (subtracted
    /// on miss) when `donchian_mode == Score`. Default 0.15 — empirical starting
    /// point near the weight_* range (0-65 confluence score scale). Validated
    /// `[0.0, 0.5]` finite to match other bonus caps. Ignored under Hard / Off.
    /// P1-11 (2)：`Score` 模式下 Donchian 突破確認加 / 未突破扣的分數量；預設 0.15，
    /// validate `[0.0, 0.5]` finite。Hard / Off 模式下忽略。
    pub donchian_score_bonus: f64,
}

/// P1-11 (3) helper: build a `BbBreakoutParams` with profile-adjusted gate
/// thresholds. All non-profile fields use `Default`. Consumers can layer
/// overrides with struct-update syntax:
/// `{ ..BbBreakoutParams::for_profile(Aggressive), volume_threshold: 1.10 }`.
///
/// P1-11 (3) 輔助：回傳帶 profile 閾值的 `BbBreakoutParams`；非 profile 欄位走
/// `Default`。可用 struct-update 語法疊加 operator 自訂：
/// `{ ..BbBreakoutParams::for_profile(Aggressive), volume_threshold: 1.10 }`。
impl BbBreakoutParams {
    pub fn for_profile(profile: BbBreakoutProfile) -> Self {
        match profile {
            // Conservative: narrow squeeze, wide expansion gap, high volume
            // bar, long persistence hold. Signal count expected 30-50% below
            // Balanced baseline; suitable when Guardian / AI cost budget is
            // tight and only clearest breakouts should fire.
            // 嚴格 Conservative：窄 squeeze + 寬擴張 gap + 高 volume + 長 persistence。
            BbBreakoutProfile::Conservative => Self {
                squeeze_bw: 0.02,
                expansion_bw: 0.05,
                volume_threshold: 1.5,
                min_persistence_ms: 120_000, // 2 min
                ..Self::default()
            },
            // Balanced: bit-identical to current production default. Test
            // `test_profile_balanced_equals_default` pins this invariant.
            // 預設 Balanced：與 Default bit-identical；測試 `test_profile_balanced_equals_default` 固化。
            BbBreakoutProfile::Balanced => Self::default(),
            // Aggressive: loose squeeze (easier to qualify), narrow expansion
            // gap (easier to cross), lower volume bar, short persistence. Paired
            // with DonchianMode::Score is the recommended dormant-rescue combo
            // per TODO §P1-11 (2)+(3). Still respects `squeeze_bw < expansion_bw`
            // invariant to pass validate().
            // 寬鬆 Aggressive：鬆 squeeze + 窄 gap + 低 volume + 短 persistence；
            // 建議與 `DonchianMode::Score` 組合 — §P1-11 (2)+(3) 救援路徑。
            BbBreakoutProfile::Aggressive => Self {
                squeeze_bw: 0.035,
                expansion_bw: 0.040,
                volume_threshold: 1.05,
                min_persistence_ms: 30_000, // 30s
                ..Self::default()
            },
        }
    }
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
            // G7-09c Phase 1: default 1 tick inside the inside quote.
            // G7-09c Phase 1：預設退一 tick。
            maker_price_buffer_ticks: 1,
            // P1-11 (2): Hard default preserves bit-identical pre-P1-11 behaviour.
            // Operators flip to Score / Off explicitly when A/B testing.
            // P1-11 (2)：`Hard` 預設保留 pre-P1-11 bit-identical；operator A/B 時顯式切換。
            donchian_mode: DonchianMode::Hard,
            donchian_score_bonus: 0.15,
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
            // P1-11 (2): donchian_score_bonus param range. donchian_mode is
            // enum-typed and doesn't fit the numeric ParamRange surface — it's
            // hot-reloaded via update_params but not Agent-tunable through
            // the numeric slider UI; ChangeConfig TOML is the operator path.
            // P1-11 (2)：donchian_score_bonus 數值 range；donchian_mode 為 enum
            // 不走 numeric slider，operator 改 TOML + IPC update_params 切換。
            ParamRange {
                name: "donchian_score_bonus".into(),
                min: 0.0,
                max: 0.5,
                step: Some(0.01),
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
        // P1-11 (2): donchian_score_bonus bounded to match other score
        // contributors (±0.5) so a hostile IPC write cannot swamp the
        // confluence decision. donchian_mode is enum-typed and self-validating.
        // P1-11 (2)：donchian_score_bonus 上限 0.5 對齊其他貢獻者，防 IPC 惡意
        // 寫入壓倒合流判決；donchian_mode 為 enum type 自身 validate。
        if !self.donchian_score_bonus.is_finite()
            || self.donchian_score_bonus < 0.0
            || self.donchian_score_bonus > 0.5
        {
            return Err("donchian_score_bonus must be finite and within [0.0, 0.5]".into());
        }
        // G7-09c Phase 1: bound BBO buffer (see params doc).
        // G7-09c Phase 1：限定 BBO buffer，防 IPC 寫入過大。
        if self.maker_price_buffer_ticks > 10 {
            return Err("maker_price_buffer_ticks must be <= 10".into());
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
