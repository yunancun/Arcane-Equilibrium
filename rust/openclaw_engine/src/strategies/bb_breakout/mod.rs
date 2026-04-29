//! BB Breakout Strategy V2 — Squeeze→Expansion + Volume + Donchian + ATR trailing stop + Regime exit.
//! BB 突破策略 V2 — 壓縮→擴張 + 成交量 + Donchian + ATR 追蹤止損 + Regime 出場。
//!
//! MODULE_NOTE (EN): Detects Bollinger Band squeeze→expansion with volume
//!   confirmation and Donchian channel breakout. ATR-based trailing stop for exits.
//!   Topical split (sibling files): `params.rs` (BbBreakoutParams + ranges +
//!   validate + build_confluence_config), `runtime_params.rs` (update_params /
//!   get_params hot-reload), `tests.rs` (core entry/exit + PostOnly), and
//!   `tests_oi.rs` (OI confluence + on_rejection regression). This file keeps
//!   the `BbBreakout` struct, ctor, per-symbol accessors, and the `Strategy`
//!   trait impl (on_tick core).
//! MODULE_NOTE (中): 檢測布林帶壓縮→擴張 + 成交量確認 + Donchian 通道突破。
//!   ATR 追蹤止損出場。按主題拆 sibling：`params.rs`（BbBreakoutParams + ranges
//!   + validate + build_confluence_config）、`runtime_params.rs`（update_params /
//!   get_params 熱重載）、`tests.rs`（核心入出場 + PostOnly）、`tests_oi.rs`
//!   （OI 合流 + on_rejection 回歸）。本檔僅保留 `BbBreakout` 結構、構造、逐
//!   symbol 存取器與 `Strategy` trait impl（on_tick 核心）。

use std::collections::HashMap;

use super::common::{compute_post_only_price, MakerPriceInputs, PerSymbolState, TrendCooldown};
use super::confluence::{self, ConfluenceConfig, PersistenceTracker};
use super::{Strategy, StrategyAction, StrategyParams};
use crate::intent_processor::OrderIntent;
use crate::order_manager::TimeInForce;
use crate::tick_pipeline::TickContext;

mod params;
mod runtime_params;

#[cfg(test)]
mod tests;
#[cfg(test)]
mod tests_oi;
#[cfg(test)]
mod tests_p1_11;

pub use params::{BbBreakoutParams, BbBreakoutProfile, DonchianMode};
use params::{DEFAULT_EXPANSION_BW, DEFAULT_SQUEEZE_BW, DEFAULT_VOLUME_THRESHOLD};

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
    /// 逐 symbol 冷卻追蹤(取代原 last_trade_ms HashMap)。
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
    /// G7-09c Phase 1: ticks INSIDE the inside quote for BBO-aware PostOnly.
    /// See `BbBreakoutParams::maker_price_buffer_ticks` for semantics.
    /// G7-09c Phase 1：BBO-aware PostOnly buffer，語義見 params。
    pub(crate) maker_price_buffer_ticks: u32,
    // ── P1-11 (2): Donchian mode + score bonus ──
    // ── P1-11 (2)：Donchian 模式 + 評分加成 ──
    /// How Donchian breach combines with the BB-core 3-gate chain. Default
    /// `Hard` = bit-identical baseline (hard AND). See `DonchianMode` doc.
    /// Donchian 突破與 BB 核心三閘的結合方式；預設 `Hard` bit-identical。
    pub(crate) donchian_mode: DonchianMode,
    /// Score delta applied on Donchian breach / miss under `Score` mode.
    /// `Score` 模式下 Donchian 突破 / 未突破時的評分增減量。
    pub(crate) donchian_score_bonus: f64,
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
            // G7-09c Phase 1: default 1 tick inside the inside quote.
            // G7-09c Phase 1：預設退一 tick。
            maker_price_buffer_ticks: 1,
            // P1-11 (2): Hard preserves bit-identical pre-P1-11 behaviour.
            // P1-11 (2)：`Hard` 保留 pre-P1-11 bit-identical 行為。
            donchian_mode: DonchianMode::Hard,
            donchian_score_bonus: 0.15,
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
    /// Preserves `squeeze_detected_ms` (squeeze record is preserved across
    /// close — rationale: the squeeze regime can continue observing the same
    /// market condition).
    ///
    /// FIX-26-DEADLOCK-1 note (2026-04-24): post-fix, `squeeze_detected_ms`
    /// is auto-cleared in `on_tick` when it has expired (see line ~346+).
    /// So the preservation across close is now bounded by the 45-min expiry
    /// window rather than being indefinite. This is the intended semantic
    /// — external close no longer creates a permanent-dormant hole.
    ///
    /// 外部平倉（風控止損）時重設該幣種內部狀態；`squeeze_detected_ms` 保留
    /// （壓縮狀態可跨越平倉延續）。FIX-26-DEADLOCK-1（2026-04-24）修復後，
    /// squeeze_detected_ms 在過期時會由 on_tick 自動清除，跨平倉保留現受
    /// 45min expiry 窗口約束（而非原本無限保留）。
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

        // P1-11 FIX-26-DEADLOCK-1 (2026-04-24): the original FIX-26 guard
        // `is_none()` makes `squeeze_detected_ms` a record of the FIRST squeeze
        // in a given squeeze regime — intentional. But the ONLY clear paths
        // are (a) entry emission at line ~636 and (b) `on_external_close`
        // explicitly preserves it (line 282-284 docstring). There is no
        // expiry-based auto-clear.
        //
        // Consequence: if a symbol registers a squeeze at T and the subsequent
        // 45-min expiry window passes WITHOUT an entry (all expansion/vol/%B/
        // Donchian gates failing to align), the stale timestamp persists
        // forever. Every future `is_none()` check sees Some(T_stale), no new
        // recording happens, and `in_squeeze` (checked at line ~440) stays
        // false because ctx.timestamp_ms >= T_stale + expiry. **Permanent
        // dormancy for that symbol**.
        //
        // This was discovered by 2026-04-24 offline sweep (P1-11 (1)): under
        // FIX-26 parity, 14d × 5 symbols × 64 threshold combos yielded n≤4
        // entries per combo — 5-6× below a naive "signal-rate" estimate. The
        // sweep's 0-entry majority corresponds to symbols stuck post-first-
        // expiry.
        //
        // Fix: clear the stored timestamp when it has expired, BEFORE the
        // `is_none()` guard. This restores the "next new squeeze re-registers"
        // behaviour that FIX-26's author almost certainly intended. Keeping
        // the `is_none()` guard preserves FIX-26's "record first, not last"
        // semantic within an active squeeze window; the expiry clear runs
        // OUTSIDE that window.
        //
        // P1-11 FIX-26-DEADLOCK-1（2026-04-24）：原 FIX-26 只在入場時清 squeeze_detected_ms，
        // 若首次 squeeze 窗口（45min）內無入場，時間戳永久卡住 → 該 symbol 進入永久
        // 休眠。bb_breakout 14d 0 fills 真正根因之一。修：在 is_none() guard 前先
        // auto-clear 過期時間戳，允許下一次新 squeeze 重新登記；FIX-26 「只記首次」語義
        // 在每個 squeeze 窗口內仍保留。
        if let Some(st) = self.symbols.get_mut(sym) {
            if let Some(stored_ts) = st.squeeze_detected_ms {
                if ctx.timestamp_ms >= stored_ts.saturating_add(self.squeeze_expiry_ms) {
                    st.squeeze_detected_ms = None;
                }
            }
        }
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
                // FIX-26-DEADLOCK-1 audit (2026-04-24): use saturating_add to
                // match the auto-clear at line ~410 — the original `ts +
                // self.squeeze_expiry_ms` is a naked add that panics in debug
                // and wraps in release on u64 overflow. Practical risk for
                // epoch-ms timestamps in u64 is essentially nil (~580M years
                // headroom) but internal asymmetry (clear path saturating,
                // check path naked) is the kind of inconsistency that bites
                // when someone later moves to u32 / nanosecond / synthetic ts.
                // FIX-26-DEADLOCK-1 audit：與 line ~410 auto-clear 對齊用 saturating_add，
                // 避免 release 下 wrap → in_squeeze 永真的 degenerate。
                let in_squeeze = self
                    .symbols
                    .get(sym)
                    .and_then(|s| s.squeeze_detected_ms)
                    .map(|ts| ctx.timestamp_ms < ts.saturating_add(self.squeeze_expiry_ms))
                    .unwrap_or(false);
                if in_squeeze
                    && bb.bandwidth > self.expansion_bw
                    && vol_ratio >= self.volume_threshold
                {
                    let is_long = bb.percent_b > 1.0;
                    let is_short = bb.percent_b < 0.0;

                    // A3 / P1-11 (2): Donchian confirmation gate, now mode-aware.
                    // - `Hard` (baseline): price must breach Donchian in entry
                    //   direction or hard-reject (bit-identical to pre-P1-11).
                    // - `Score`: breach adds +donchian_score_bonus to the score
                    //   (applied after compute_score below); miss subtracts the
                    //   same. Entry proceeds regardless — downstream confluence
                    //   gate decides via `confluence_as_gate` + thresholds.
                    // - `Off`: skip Donchian entirely; score delta = 0.
                    // Missing `ind.donchian` indicator data (e.g., warm-up)
                    // yields score delta 0 regardless of mode — same semantics
                    // as the original Hard path (which also silently passed
                    // through when `dc` was None).
                    //
                    // A3 / P1-11 (2)：Donchian 確認門，mode-aware。
                    // - `Hard`（基線）：方向未突破即硬拒（pre-P1-11 bit-identical）。
                    // - `Score`：突破 +donchian_score_bonus / 未突破扣同量（於下方 compute_score
                    //   後套用）；入場繼續，由合流閘仲裁。
                    // - `Off`：完全跳過。
                    // `ind.donchian` 缺值（暖機期）→ score delta=0；與原 Hard 路徑 None 放行一致。
                    let donchian_score_delta: f64 = match (self.donchian_mode, &ind.donchian) {
                        (DonchianMode::Hard, Some(dc)) => {
                            if is_long && ctx.price < dc.upper {
                                return vec![];
                            }
                            if is_short && ctx.price > dc.lower {
                                return vec![];
                            }
                            0.0
                        }
                        (DonchianMode::Score, Some(dc)) => {
                            let breach = (is_long && ctx.price >= dc.upper)
                                || (is_short && ctx.price <= dc.lower);
                            if breach {
                                self.donchian_score_bonus
                            } else {
                                -self.donchian_score_bonus
                            }
                        }
                        (DonchianMode::Off, _) | (_, None) => 0.0,
                    };

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

                        // A4: Hurst regime boost — Persistent regime boosts breakout confidence
                        // A4：Hurst 趋势状态 — Persistent 状态提升突破信心
                        // E5-P2-4: magnitude now config-driven (was hard-coded 0.1).
                        // E5-P2-4：加成幅度改由 config 控制（原 hard-coded 0.1）。
                        // G7-03 Phase B: legacy "trending" string → typed `RegimeLabel`
                        //   via `from_legacy_str`. Phase B's per-symbol hysteresis
                        //   stabilizes the regime label upstream in step 1+2 so this
                        //   match sees a *stabilized* label when `hurst.enabled = true`,
                        //   bit-identical instantaneous label when disabled.
                        // G7-03 Phase B：legacy 字串透過 from_legacy_str 轉 typed enum；
                        //   啟用 hurst 時上游已套滯回，stale flip 受 lag 保護。
                        let hurst_boost: f64 = match &ind.hurst {
                            Some(h)
                                if crate::regime::RegimeLabel::from_legacy_str(&h.regime)
                                    == crate::regime::RegimeLabel::Persistent =>
                            {
                                self.hurst_regime_boost
                            }
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
                            let delta_opt =
                                self.symbols.get(sym).and_then(|s| s.compute_oi_delta_pct());
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
                        // P1-11 (2): apply Donchian score delta (0.0 under Hard /
                        // Off / missing-data paths, +/-donchian_score_bonus under
                        // Score mode). Applied after OI so both modifiers stack
                        // additively on the base confluence score; `score=None`
                        // path (confluence disabled upstream) stays None — we
                        // don't fabricate a score from Donchian alone.
                        // P1-11 (2)：套用 Donchian 評分增減；Hard/Off/缺資料 → 0.0。
                        // OI 之後套用，兩修飾器加性疊加；score=None（上游停用）保持 None。
                        let score = score.map(|s| s + donchian_score_delta);
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
                        // EDGE-P2-3 Phase 2+ + G7-09c Phase 1: resolve entry order shape.
                        // G7-09c Phase 1 replaces legacy `last_price ± offset_bps` (RCA
                        // `7f0e793` showed 100% PostOnly reject from crossing the book) with
                        // strictly passive BBO-aware price; if no safe maker price exists, skip
                        // the entry and keep squeeze state alive for the next valid tick.
                        // EDGE-P2-3 Phase 2+ + G7-09c Phase 1：以 BBO-aware 嚴格被動價取代
                        // 舊 `last_price ± offset_bps`（RCA 顯示舊算法 100% PostOnly 拒絕）；
                        // 無安全 maker 價時跳過本次入場並保留 squeeze state 供下一 tick。
                        let (order_type, limit_price, time_in_force, maker_timeout_ms) =
                            if self.use_maker_entry {
                                let inputs = MakerPriceInputs {
                                    last_price: ctx.price,
                                    best_bid: ctx.best_bid,
                                    best_ask: ctx.best_ask,
                                    tick_size: ctx.tick_size,
                                };
                                let Some(limit) = compute_post_only_price(
                                    is_long,
                                    inputs,
                                    self.maker_price_offset_bps,
                                    self.maker_price_buffer_ticks,
                                    "bb_breakout",
                                    ctx.symbol,
                                ) else {
                                    return intents;
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

                // V2: Regime exit — Hurst drops from Persistent to AntiPersistent/Random.
                // V2：Regime 出場 — Hurst 從 Persistent 轉為 AntiPersistent/Random。
                // E5-P2-4: regime_shift bonus now config-driven (was 0.1).
                // E5-P2-4：regime 轉向加成改由 config 控制（原 0.1）。
                // G7-03 Phase B: typed match — anything not Persistent is a shift trigger.
                //   `from_legacy_str` maps unknown strings → Random (legacy-safe).
                // G7-03 Phase B：typed match — 非 Persistent 即視為 shift 觸發；
                //   from_legacy_str 將未知字串映射為 Random（legacy-safe）。
                if exit_reason.is_none() {
                    if let Some(h) = &ind.hurst {
                        let label = crate::regime::RegimeLabel::from_legacy_str(&h.regime);
                        if label == crate::regime::RegimeLabel::AntiPersistent
                            || label == crate::regime::RegimeLabel::Random
                        {
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
