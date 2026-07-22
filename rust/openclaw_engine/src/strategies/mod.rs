//! Strategy modules — 5 trading strategies + shared helpers (R04-5, G-SR-1).
//! 策略模組 — 5 個交易策略 + 共享輔助模組。
//!
//! MODULE_NOTE (EN): Defines Strategy trait + StrategyAction enum; public parameter
//!   schema + StrategyFactory live in sibling files (`params.rs`, `registry.rs`).
//!   Sub-modules: ma_crossover, bb_breakout, bb_reversion, grid_trading, funding_arb,
//!   confluence (shared scoring/persistence), grid_helpers (extracted grid math).
//!   Post-split (cluster C4c) this `mod.rs` is ~150 lines, well under §九 2000-line cap.
//!   Re-exports below preserve every external import path (`crate::strategies::X`).
//! MODULE_NOTE (中): 定義 Strategy trait + StrategyAction 枚舉；參數 schema 與
//!   StrategyFactory 移至 sibling 檔案（`params.rs`、`registry.rs`）。
//!   子模組：ma_crossover、bb_breakout、bb_reversion、grid_trading、funding_arb、
//!   confluence（共享評分/持續性）、grid_helpers（提取的網格數學）。
//!   cluster C4c 切分後 `mod.rs` 僅 ~150 行，遠低於 §九 2000 行硬上限。
//!   下方 re-export 保持所有外部匯入路徑（`crate::strategies::X`）零改動。

pub mod bb_breakout;
pub mod bb_reversion;
pub mod common;
pub mod confluence;
// flash_dip_buy — flash-crash dip-buy demo pilot（sibling 策略；demo-only，
// flag-OFF + active=false 雙鎖預設）。daily cadence + PostOnly 靜態深價 maker entry +
// N=3 day-clustered hold exit。研究 ref: tail_dislocation_meanrev 26-survivor universe。
pub mod flash_dip_buy;
// Sprint N+1 W2 sub-task 2：BtcLeadLagPanel paper-only shadow log 共用 helper。
pub mod cross_asset;
pub mod funding_arb;
// C10 funding harvest — delta-neutral spot long + perp short matched notional。
// 與 funding_arb V2（ADR-0018 dormant）並列，為新策略 slot。Stage 1 Demo 限定 BTCUSDT。
pub mod funding_harvest;
// Sprint 2 Alpha Tournament Candidate #1 — funding_short_v2。
// short-only directional capture (funding > 30% annualized)；與 funding_arb V2
// (ADR-0018 dormant) + funding_harvest (delta-neutral) 並列為第三個 funding slot；
// Stage 1 Demo 限定 BTCUSDT / ETHUSDT。
pub mod funding_short_v2;
pub mod grid_helpers;
pub mod grid_trading;
// Sprint 2 Alpha Tournament Candidate #4 — liquidation_cascade_fade。
// 5min liquidation cluster mean-revert fade（per BB C6 PROOF PASS + W-AUDIT-8a C1
// LiquidationPulseAggregator + commit 0e8a8ae8 allLiquidation 訂閱）。
// Stage 1 Demo 限定 BTCUSDT / ETHUSDT。
pub mod liquidation_cascade_fade;
pub mod ma_crossover;
pub mod maker_rejection;

// ── C4c split: parameter schema + factory moved to siblings ──
// ── C4c 拆分：參數 schema + 工廠搬到 sibling ──
pub mod params;
pub mod registry;
pub mod strategy_params;
#[cfg(test)]
pub(crate) mod test_harness;

// Re-export public API surface so external call-sites keep using
// `crate::strategies::X` unchanged.
// 重新導出公用 API 表面，外部呼叫處 `crate::strategies::X` 完全不變。
pub use params::{
    load_strategy_params, load_strategy_params_from, BbBreakoutParams, BbReversionParams,
    FundingArbParams, FundingHarvestParams, GridTradingParams, MaCrossoverParams, ParamRange,
    StrategyParams, StrategyParamsConfig,
};
pub use registry::StrategyFactory;

use crate::intent_processor::OrderIntent;
use crate::strategies::maker_rejection::MakerRejectionCategory;
use crate::tick_pipeline::TickContext;
use openclaw_core::alpha_surface::{AlphaSourceTag, AlphaSurface};
use openclaw_core::execution::FillResult;

/// First-class strategy action: Open (new position, full governance) or Close (exit, lightweight path).
/// 策略一等公民動作：Open（新倉，完整治理管線）或 Close（平倉，輕量路徑）。
///
/// Close bypasses governance gates (Guardian, cost_gate, Kelly sizing, P1 cap) since closing
/// reduces risk rather than increasing it. Pipeline looks up actual is_long/qty from paper_state.
/// Close 繞過治理門禁（Guardian、cost_gate、Kelly sizing、P1 cap），因為平倉是降低風險而非增加風險。
/// 管線從 paper_state 查找實際的 is_long/qty。
#[derive(Debug, Clone)]
pub enum StrategyAction {
    /// New position — goes through full governance pipeline.
    /// 新倉 — 經過完整治理管線。
    Open(OrderIntent),
    /// Close existing position — lightweight path, bypasses governance gates.
    /// 平倉 — 輕量路徑，繞過治理門禁。
    Close {
        symbol: String,
        confidence: f64,
        reason: String,
    },
}

/// Strategy trait — implement for each trading strategy.
/// 策略 trait — 為每個交易策略實現。
/// Send required for tokio::spawn compatibility.
pub trait Strategy: Send {
    /// Strategy name for logging and attribution.
    /// 策略名稱用於日誌和歸因。
    fn name(&self) -> &str;

    /// Is this strategy currently active?
    /// 此策略當前是否活躍？
    fn is_active(&self) -> bool;

    /// RRC-1-E2: Set strategy active/paused state via IPC.
    /// RRC-1-E2：通過 IPC 設置策略活躍/暫停狀態。
    fn set_active(&mut self, active: bool);

    /// W-AUDIT-8a Phase A：聲明本策略消費的 alpha source tag 清單。
    /// 由 `Orchestrator` 用於 dispatch tracking metric `alpha_source_*_total`。
    /// 無 default impl：5 既存策略 explicit declare 強制 migration。
    fn declared_alpha_sources(&self) -> &[AlphaSourceTag];

    /// BB-OI-DECOUPLE-1：本策略是否「硬依賴」OI panel（不可得時必須 fail-closed
    /// 跳過整個 tick）。
    ///
    /// 為什麼是 default false：dispatch 端（step_4_5_dispatch.rs）原先對 bb_breakout
    /// 無條件 probe `oi_panel_delta_5m_pct`，Err 即 `continue` 跳過整 tick——但這與
    /// 策略自身的降級語意脫鉤（bb_breakout 在 `enable_oi_signal=false` 時 score 修飾
    /// 本就不參與 OI）。OI cohort（25）< scanner universe（40）導致落 cohort 外的幣
    /// 恆 `symbol_missing`，於是 OI 預設關閉時仍被整批跳過。
    ///
    /// 改以本 trait 方法讓「是否硬依賴 OI」回歸各策略自述：default false 確保其他
    /// 4 個策略零改動、dispatch 端不對它們 probe（非 cross-cutting）；只有 bb_breakout
    /// override 為 `self.enable_oi_signal`，使 dispatch 的 fail-closed probe 僅在
    /// 真正開啟 OI 信號時生效。
    fn requires_oi_panel(&self) -> bool {
        false
    }

    /// Process a tick and return strategy actions (Open or Close).
    /// 處理 tick 並返回策略動作（Open 或 Close）。
    /// W-AUDIT-8a Phase A：簽名升級 + `surface: &AlphaSurface<'_>`。Tier 1 仍由
    /// `ctx.indicators` 提供（向後相容）；策略未來消費 Tier 2-4 改走
    /// `surface.<field>`，`None` → fail-closed 跳過自身 alpha source。
    fn on_tick(
        &mut self,
        ctx: &TickContext<'_>,
        surface: &AlphaSurface<'_>,
    ) -> Vec<StrategyAction>;

    /// Called when an intent from this strategy was rejected by the governance pipeline.
    /// 當此策略的意圖被治理管線拒絕時調用。
    /// Default: no-op. Strategies that track internal position should override.
    /// 默認：無操作。跟蹤內部倉位的策略應覆蓋此方法。
    fn on_rejection(&mut self, _intent: &OrderIntent, _reason: &str) {
        // Default no-op / 默認無操作
    }

    /// Called when an order from this strategy was filled.
    /// 當此策略的訂單成交時調用。
    /// W7-5：策略應 override 此方法在真實 fill confirmed 後同步 self.positions
    /// 為 fill direction，作為 entry path eager mutate（intent emit 時已寫入）的
    /// fill-confirm safety net。Open 路徑時 callsite 在 step_4_5_dispatch.rs:925，
    /// paper_state.apply_fill 之前；Close 路徑不走 on_fill（走 on_close_confirmed）。
    fn on_fill(&mut self, _intent: &OrderIntent, _fill: &FillResult) {
        // Default no-op / 默認無操作
    }

    /// Called once during engine bootstrap after `paper_state.import_positions(...)`
    /// has seeded exchange positions. Strategies that maintain internal position
    /// state (`self.positions` / `self.net_inventory` / `self.symbols`) should
    /// override to filter `paper_state.positions()` by `pos.owner_strategy ==
    /// self.name()` and rebuild internal state, breaking cold-start desync where
    /// engine restart leaves `paper_state` populated (from `bybit_sync` snapshot)
    /// but `self.positions = HashMap::new()` (empty), causing entry-path eager
    /// re-emit on the very first tick (the W6 INXUSDT 11:34 hot-loop class).
    /// W7-5 part 2：bootstrap 階段於 `paper_state.import_positions` 之後呼叫一次，
    /// 5 策略應 override：以 `pos.owner_strategy == self.name()` 過濾 paper_state
    /// 倉位重建 self.positions / self.net_inventory / self.symbols，避免重啟後
    /// strategy 端為空、paper_state 已載入而 entry path 在第一個 tick 撞 router
    /// gate 1.5 duplicate_position 的 cold-start desync hot loop。
    /// `bybit_sync` / `orphan_adopted` owner 不對應任何策略 name，自然不被任何
    /// 策略 import（避免誤領 orphan）。
    fn import_positions(&mut self, _paper_state: &crate::paper_state::PaperState) {
        // Default no-op / 默認無操作
    }

    /// 當倉位被外部（風控止損/熔斷）而非本策略關閉時調用。
    /// 跟蹤內部倉位狀態或維護 spot-side ledger 的策略應覆蓋以保持同步。
    ///
    /// Sprint 1B audit Bug 1 fix（C10 HYBRID-BUG）：
    /// 簽名新增 `close_price` / `close_ts_ms` 兩參數，讓策略可以用真實 close fill
    /// price 結算 realized PnL（funding_harvest synthetic spot leg）。
    /// 既有 strategy override 不消費這兩參數時可命名 `_close_price` / `_close_ts_ms`
    /// 並保持 default no-op 行為（純編譯通過修，0 行為差）。
    /// 不變量：caller 必傳 close fill price + close ts；無 fill 確認的 path（例如
    /// exchange-mode dispatch-only 路徑、halt close-all fail-soft 路徑）走對稱
    /// fallback chain：`latest_price → entry_price → 0.0`（Round 2 finding 5/9 對齊
    /// step_6_risk_checks halt path 與 step_4_5_dispatch close path 實作）。
    /// 不直接 fallback 到 0.0，避免 funding_harvest synthetic ledger close(0.0) 產生
    /// 負巨額 PnL `(0 - entry_price) * qty`。
    fn on_external_close(&mut self, _symbol: &str, _close_price: f64, _close_ts_ms: u64) {
        // Default no-op / 默認無操作
    }

    /// 管線確認策略發出的 Close 已成功執行後調用。
    /// 延遲狀態變更直到確認平倉的策略應覆蓋；維護 synthetic ledger 的策略必須用
    /// `close_price` / `close_ts_ms` 結算真實 PnL（避免 entry_price fallback 造成
    /// PnL ≡ 0 觸發 Stage 0R replay drift > 5% 結構性永真，spec §4.1 line 765 demote）。
    ///
    /// Sprint 1B audit Bug 1 fix（C10 HYBRID-BUG）：簽名升級理由同 `on_external_close`。
    fn on_close_confirmed(&mut self, _symbol: &str, _close_price: f64, _close_ts_ms: u64) {
        // Default no-op / 默認無操作
    }

    /// Called when a strategy-emitted Close was skipped (no position found in paper_state).
    /// Strategies that eagerly mutated state should override to roll back.
    /// 策略發出的 Close 被跳過（paper_state 中未找到倉位）時調用。提前變更狀態的策略應覆蓋以回滾。
    fn on_close_skipped(&mut self, _symbol: &str) {
        // Default no-op / 默認無操作
    }

    /// EDGE-P2-3 Phase 1B-3 (FIX-G7-09C-PHASE2-WIRE-1B3): exchange-side
    /// rejection reached this strategy. Distinct from `on_rejection`
    /// (which is the *governance* pipeline saying "no") — this is Bybit
    /// itself rejecting an order after structural acceptance, classified by
    /// `MakerRejectionCategory`. Strategies should arm a per-symbol cooldown
    /// so the same maker order does not get re-emitted in the next tick
    /// while the book / account-level cause is still live.
    /// Default no-op for strategies that do not yet implement maker-aware
    /// retry control; PostOnly maker entries (G7-09c Phase 1) make this
    /// callback meaningful for `grid_trading` first.
    /// `category` is the classified Bybit reject reason (`PostOnlyCross`,
    /// `TooManyPending`, `FokCancel`, `SelfCancel`, `Other(raw)`); strategy
    /// may inspect to decide cooldown duration / suppression strategy.
    /// EDGE-P2-3 Phase 1B-3：交易所端拒絕傳到本策略。與 `on_rejection`（治理
    /// 管線拒絕）不同，這是 Bybit 在結構接受後拒絕下單，已分類為
    /// `MakerRejectionCategory`。策略應設定該 symbol 的冷卻時間，避免下一
    /// tick 重發同一 maker 單。預設 no-op；PostOnly 入場（G7-09c Phase 1）
    /// 讓本 callback 對 `grid_trading` 首先有意義。
    fn on_post_only_rejected(
        &mut self,
        _symbol: &str,
        _ts_ms: i64,
        _category: &MakerRejectionCategory,
    ) {
        // Default no-op / 預設無操作
    }

    // ── Phase 3a: Runtime parameter tuning API (AGT-1) ──
    // Phase 3a：運行時參數調參 API

    /// Update strategy parameters from JSON. Returns Err if invalid.
    /// 從 JSON 更新策略參數。無效時返回 Err。
    fn update_params_json(&mut self, _json: &str) -> Result<(), String> {
        Err("update_params not implemented for this strategy".into())
    }

    /// Get current parameters as JSON string.
    /// 獲取當前參數的 JSON 字符串。
    fn get_params_json(&self) -> String {
        "{}".into()
    }

    /// Get tunable parameter ranges as JSON string.
    /// 獲取可調參數範圍的 JSON 字符串。
    fn param_ranges_json(&self) -> String {
        "[]".into()
    }

    // ── CONF-D: per-strategy confidence scaling exposed via update_strategy_params ──
    // CONF-D：通過 update_strategy_params 暴露的逐策略 confidence 縮放因子

    /// CONF-D: Read the current confidence scale (default 1.0).
    /// Strategies multiply every emitted intent.confidence by this value
    /// before pushing to the intent stream. Range [0.0, 2.0]; >1.0 amplifies,
    /// <1.0 dampens, 0.0 effectively mutes the strategy without disabling it.
    /// CONF-D：讀取當前 confidence 縮放因子（默認 1.0）。
    /// 策略在發出 intent 前將其 confidence 乘以此值。範圍 [0, 2]。
    fn conf_scale(&self) -> f64 {
        1.0
    }

    /// CONF-D: Set confidence scale. Out-of-range values are clamped to [0.0, 2.0].
    /// Default no-op for strategies that opt out (their conf_scale stays 1.0).
    /// CONF-D：設定 confidence 縮放因子，越界自動 clamp 到 [0, 2]。
    fn set_conf_scale(&mut self, _scale: f64) {
        // Default no-op / 預設無操作
    }

    /// FLASH-DIP-PILOT (2026-06-18): boot-time prior daily close seed。
    /// 為什麼是 trait 方法：on_tick 無 KlineManager 存取；flash_dip_buy 的入場價
    /// 依賴「前一完整 UTC 日收盤」（leak-free），由 bootstrap 在 1d REST seed 後
    /// 讀 KlineManager 1d buffer 注入。default no-op：其他 5 策略不消費 daily close
    /// （零行為差）。
    fn seed_prior_close(&mut self, _symbol: &str, _prior_close: f64) {
        // Default no-op / 預設無操作
    }

    /// FLASH-DIP-PILOT (2026-06-24)：啟動時恢復未成交 Working order。
    /// Pending PostOnly orders 不屬於 PaperState position，所以 restart 後必須
    /// 另外恢復，避免 producer-side max_concurrent 低估並重複掛單。
    fn seed_pending_entry(&mut self, _symbol: &str, _expiry_ms: u64) {
        // Default no-op / 預設無操作
    }
}

// ── Tests moved verbatim to sibling `tests.rs` to keep mod.rs lean ──
// ── 測試逐字搬到 sibling `tests.rs`，維持 mod.rs 精簡 ──
#[cfg(test)]
mod tests;

// ── E4 cross-strategy holistic integration test (P0 Option A-Lite post-merge) ──
// ── E4 跨策略 holistic 整合測試（P0 Option A-Lite post-merge）──
// 補充 5 個 E1 sibling acceptance test 之外的「多策略同 symbol 視角」覆蓋。
// 對應 PA report §5.3 cross-strategy integration 設計初衷。
#[cfg(test)]
mod cross_strategy_attribution_integrity;
