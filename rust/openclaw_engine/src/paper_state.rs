//! Paper Trading State — position tracking + PnL (R04-7).
//! 紙盤交易狀態 — 持倉追蹤 + 損益。
//!
//! MODULE_NOTE (EN): Manages simulated positions, fills, balance, and PnL for
//!   paper/demo/live modes. apply_fill() updates positions; mark_to_market()
//!   computes unrealized PnL each tick. Thread-safe: sole-owner in TickPipeline.
//! MODULE_NOTE (中): 管理紙盤/Demo/Live 模式的模擬持倉、成交、餘額和損益。
//!   apply_fill() 更新持倉；mark_to_market() 每 tick 計算未實現損益。
//!   線程安全：TickPipeline 獨佔所有權。

use openclaw_core::stop_manager::{self, PositionState, StopConfig, StopTrigger};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;

/// A paper trading position.
/// 紙盤交易持倉。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PaperPosition {
    pub symbol: String,
    pub is_long: bool,
    pub qty: f64,
    pub entry_price: f64,
    pub best_price: f64,
    pub entry_fee: f64,
    pub entry_ts_ms: u64,
    pub unrealized_pnl: f64,
    /// EDGE-P3-1 R2: context_id of the entry that opened this position.
    /// Threaded to trading.fills.entry_context_id on close for ML training JOIN.
    /// Empty string when unknown (e.g., pre-V017 restored snapshots, orphan adopt).
    /// EDGE-P3-1 R2：開此倉的 entry 對應 context_id。平倉時透傳到
    /// trading.fills.entry_context_id，供 ML 訓練 JOIN。未知時為空串（如 pre-V017
    /// 還原的快照、orphan adopt）。
    #[serde(default)]
    pub entry_context_id: String,
    /// ORPHAN-ADOPT-1 Phase 2A: strategy name that originated this position.
    /// Strategy-driven fills write `intent.strategy` (e.g. "ma_crossover").
    /// Exchange-origin inserts (import_positions, WS upsert) write "bybit_sync".
    /// Adopted orphans write `ORPHAN_ADOPTED_STRATEGY` ("orphan_adopted").
    /// Same-direction accumulates preserve the first writer (first-write-wins)
    /// — rationale: original strategy owns the round-trip. Empty string only
    /// on pre-Phase-2A deserialized snapshots.
    /// ORPHAN-ADOPT-1 Phase 2A：倉位歸屬策略。策略驅動填單寫 intent.strategy；
    /// 交易所來源填單寫 "bybit_sync"；adopt 的孤兒寫 ORPHAN_ADOPTED_STRATEGY。
    /// 同向加倉保留首次寫入者（第一個持倉策略負責整個 round-trip）。
    /// 空字串僅於 Phase 2A 之前的舊快照反序列化時出現。
    #[serde(default)]
    pub owner_strategy: String,
    /// MICRO-PROFIT-FIX-1 (2026-04-17): cumulative entry notional — set on
    /// first open (`qty * entry_price`) and **accumulated** on same-direction
    /// fills (`entry_notional += fill_qty * fill_price`). NOT decremented on
    /// reductions, so it represents the peak accumulated entry notional and
    /// gives `fast_track` a stable baseline for the
    /// `ft_min_notional_ratio_of_entry` filter. Legacy snapshots lacking this
    /// field deserialise to `0.0` via `#[serde(default)]`; `PaperState::new`
    /// migrates them in-place to `qty * entry_price` on startup.
    /// MICRO-PROFIT-FIX-1：累積入場名目。首開 = qty × entry_price；同向加倉累加；
    /// 減倉不改。舊快照缺該欄位時反序列為 0.0，由 PaperState::new 啟動時補齊。
    #[serde(default)]
    pub entry_notional: f64,
}

/// DUST-EVICTION-GAP-1 / P1-8 FUP (2026-04-17): labels treated as "not owned by any real
/// strategy". Any position wearing one of these needs opportunistic re-triage on subsequent
/// ticks so conditions that prevented promotion at startup (notional below min, symbol
/// outside scanner universe) can unlock naturally without requiring restart or operator
/// action. `KNOWN_STRATEGY_NAMES` intentionally excludes these three so B1/B2 edge probes
/// don't self-reference; keep both lists in sync when adding new synthetic labels.
/// DUST-EVICTION-GAP-1 / P1-8 FUP：視為「無實策略擁有」的標籤。掛此標籤的持倉每 tick
/// 走機會性重分流，讓啟動時阻擋升級的條件（名義值過低 / 不在 scanner universe）自然
/// 解除，不需 operator 介入或重啟。與 KNOWN_STRATEGY_NAMES 互斥對稱。
pub const SYNTHETIC_OWNER_LABELS: &[&str] = &[
    "bybit_sync",
    crate::position_reconciler::orphan_handler::ORPHAN_ADOPTED_STRATEGY,
    crate::position_reconciler::orphan_handler::DUST_FROZEN_STRATEGY,
];

/// DUST-EVICTION-GAP-1 / P1-8 FUP (2026-04-17): outcome of a single per-tick re-triage call
/// for a position with a synthetic owner label. The caller (`tick_pipeline::on_tick`) uses
/// this to drive logging + (for `NeedsEviction`) `ipc_close_symbol` dispatch.
/// DUST-EVICTION-GAP-1 / P1-8 FUP：單次 tick-level synthetic-owner 重分流結果。
#[derive(Debug, Clone, PartialEq)]
pub enum RetriageOutcome {
    /// No synthetic position for this symbol, or already owned by a real strategy,
    /// or position not found. Fast path (the vast majority of tick calls).
    /// 無 synthetic 倉位 / 已被實策略擁有 / 無倉 — 熱路徑（絕大多數 tick 走此分支）。
    NoOp,
    /// `est_notional < min_notional` → label set (or kept) as `DUST_FROZEN_STRATEGY`.
    /// `was_downgraded = true` iff this tick actually flipped the label (for log dedup).
    /// `est_notional < min_notional` → 標籤設為（或保持）orphan_frozen。
    /// `was_downgraded=true` 表示本 tick 真正切換，用於日誌去重。
    FrozenAsDust {
        est_notional: f64,
        min_notional: f64,
        was_downgraded: bool,
    },
    /// Synthetic label → real strategy name (symbol in universe, notional OK).
    /// Caller should log the transition once.
    /// Synthetic 標籤 → 實策略（在 universe + 名義值足夠）。呼叫方需記一次轉換日誌。
    Promoted {
        from: String,
        to: String,
        est_notional: f64,
    },
    /// Symbol not in universe + notional OK → caller should dispatch CloseSymbol.
    /// Caller is responsible for time-based dedup to avoid spam on repeated retries.
    /// 不在 universe + 名義值足夠 → 呼叫方派 CloseSymbol，並負責時間去重。
    NeedsEviction {
        is_long: bool,
        qty: f64,
        est_notional: f64,
    },
}

/// P0-6 FIX: Result of startup bybit_sync position triage.
/// P0-6 修復：啟動 bybit_sync 持倉分流結果。
#[derive(Debug, Clone, Default)]
pub struct TriageOutcome {
    /// (symbol, assigned_strategy) — positions kept in paper_state under a real strategy.
    /// 被策略接管的持倉（保留在 paper_state）。
    pub adopted: Vec<(String, String)>,
    /// (symbol, is_long, qty) — positions removed from paper_state, need close dispatch.
    /// 從 paper_state 移除的持倉，需派發平倉。
    pub evicted: Vec<(String, bool, f64)>,
    /// DUST-EVICTION-GAP-1 / P1-8 (2026-04-17): (symbol, is_long, qty, est_notional, min_notional)
    /// — eviction candidates whose `qty * ref_price` is below the exchange min notional.
    /// Retained in paper_state with `owner_strategy = DUST_FROZEN_STRATEGY` so the
    /// position mirror still reflects exchange reality; NO close is dispatched (would be
    /// rejected anyway). Operator must clear on Bybit GUI before going truly live.
    /// DUST-EVICTION-GAP-1 / P1-8：被驅逐候選但名義值低於交易所最小值的持倉；保留於
    /// paper_state 並標記 DUST_FROZEN_STRATEGY，不派平倉；需 operator 手動清理。
    pub dust_frozen: Vec<(String, bool, f64, f64, f64)>,
}

/// Paper trading state manager.
/// 紙盤交易狀態管理器。
pub struct PaperState {
    _initial_balance: f64,
    balance: f64,
    peak_balance: f64,
    positions: HashMap<String, PaperPosition>,
    latest_prices: HashMap<String, f64>,
    /// Per-symbol 24h turnover for dynamic slippage calculation.
    /// 每交易對 24h 成交額，用於動態滑點計算。
    latest_turnovers: HashMap<String, f64>,
    total_realized_pnl: f64,
    total_fees: f64,
    trade_count: u32,
    stop_config: StopConfig,
    forced_drawdown: f64,
    /// Bybit Demo account real balance (Mode B: bybit_sync). None = custom mode.
    /// Bybit Demo 帳戶真實餘額（模式 B：bybit_sync）。None = 自設金額模式。
    bybit_sync_balance: Option<f64>,
    /// API-reported unrealized PnL per symbol (from WS position updates).
    /// API 報告的每交易對未實現損益（來自 WS 持倉更新）。
    api_unrealized_pnl: HashMap<String, f64>,
    /// ORPHAN-ADOPT-1 FUP: side-car mirror of `positions` exposing only
    /// `(symbol → is_long)` so external observers (position_reconciler's
    /// orphan handler) can cross-check whether the engine already owns a
    /// candidate Orphan BEFORE dispatching a close. Updated on every insert /
    /// remove / clear alongside `positions`. Production wires
    /// `set_positions_mirror()` right after construction so the reconciler
    /// shares the same handle.
    /// ORPHAN-ADOPT-1 FUP：`positions` 的側車鏡像，僅暴露 `(symbol → is_long)`。
    /// 對帳器孤兒處理器讀此鏡像，派發平倉前先確認引擎是否已持倉，
    /// 避免把引擎剛開的新倉誤判為 Orphan。每次 insert / remove / clear
    /// 都同步更新。生產路徑在 TickPipeline 構造後用 `set_positions_mirror()`
    /// 換成與對帳器共享的 handle。
    positions_mirror: Arc<parking_lot::RwLock<HashMap<String, bool>>>,
}

impl PaperState {
    pub fn new(initial_balance: f64) -> Self {
        Self {
            _initial_balance: initial_balance,
            balance: initial_balance,
            peak_balance: initial_balance,
            positions: HashMap::new(),
            latest_prices: HashMap::new(),
            latest_turnovers: HashMap::new(),
            total_realized_pnl: 0.0,
            total_fees: 0.0,
            trade_count: 0,
            stop_config: StopConfig::default(),
            forced_drawdown: 0.0,
            bybit_sync_balance: None,
            api_unrealized_pnl: HashMap::new(),
            positions_mirror: Arc::new(parking_lot::RwLock::new(HashMap::new())),
        }
    }

    /// ORPHAN-ADOPT-1 FUP: clone the current positions_mirror Arc handle.
    /// Reconciler uses the handle read-side to suppress false-positive Orphans.
    /// ORPHAN-ADOPT-1 FUP：克隆當前 positions_mirror 的 Arc handle。
    /// 對帳器以讀端抑制誤報的 Orphan。
    pub fn positions_mirror(&self) -> Arc<parking_lot::RwLock<HashMap<String, bool>>> {
        Arc::clone(&self.positions_mirror)
    }

    /// ORPHAN-ADOPT-1 FUP: replace the internal mirror handle with `mirror`,
    /// rehydrating it from the current `positions` map so the reconciler sees
    /// existing positions (e.g., after import_positions bootstrap). Must be
    /// called after construction and before the reconciler runs its first
    /// cycle. Idempotent in practice — subsequent `positions` mutations keep
    /// the shared handle in sync via the private helpers.
    /// ORPHAN-ADOPT-1 FUP：用 `mirror` 替換內部 handle 並從當前 `positions` 回填，
    /// 讓對帳器能看到引擎既有持倉（如 import_positions 啟動後）。應在 TickPipeline
    /// 構造後、對帳器首輪 cycle 前呼叫。後續 positions 變動由私有 helper 自動同步。
    pub fn set_positions_mirror(
        &mut self,
        mirror: Arc<parking_lot::RwLock<HashMap<String, bool>>>,
    ) {
        {
            let mut guard = mirror.write();
            guard.clear();
            for (sym, pos) in &self.positions {
                guard.insert(sym.clone(), pos.is_long);
            }
        }
        self.positions_mirror = mirror;
    }

    /// Private helper: insert a position AND mirror `(symbol → is_long)`.
    /// 私有 helper：同時寫入 positions 與 positions_mirror。
    fn positions_insert(&mut self, symbol: String, pos: PaperPosition) {
        self.positions_mirror
            .write()
            .insert(symbol.clone(), pos.is_long);
        self.positions.insert(symbol, pos);
    }

    /// Private helper: remove from both positions and mirror.
    /// 私有 helper：同步從 positions 與 mirror 移除。
    fn positions_remove(&mut self, symbol: &str) -> Option<PaperPosition> {
        self.positions_mirror.write().remove(symbol);
        self.positions.remove(symbol)
    }

    /// Private helper: clear both positions and mirror.
    /// 私有 helper：清空 positions 與 mirror。
    fn positions_clear(&mut self) {
        self.positions_mirror.write().clear();
        self.positions.clear();
    }

    /// Proactively insert (symbol, is_long) into the positions mirror WITHOUT
    /// touching the real `positions` map. Bridges the race window between
    /// OrderDispatchRequest send and WS Fill arrival: the reconciler reads the
    /// mirror and won't classify the pending open as an orphan.
    /// Cleared naturally when the Fill arrives (positions_insert overwrites)
    /// or when a CloseSymbol removes it.
    /// 主動寫入 mirror 但不動 positions，彌合下單→成交回報之間的空窗：
    /// 對帳器讀到 mirror 後不會誤判為 orphan。
    pub fn proactive_mirror_insert(&self, symbol: &str, is_long: bool) {
        self.positions_mirror
            .write()
            .insert(symbol.to_string(), is_long);
    }

    /// MICRO-PROFIT-FIX-1 startup migration: walk `positions` and for any entry
    /// whose `entry_notional == 0.0` (i.e. rehydrated from a pre-fix snapshot
    /// via `#[serde(default)]`), backfill it to `qty * entry_price`. Returns
    /// the number of positions touched. Idempotent: safe to call multiple
    /// times. Current startup flow has no paper_state-snapshot rehydration
    /// path (positions arrive via `import_positions` from Bybit REST which
    /// already seeds entry_notional), but this exists as defence-in-depth for
    /// any future JSON/IPC restore that does plain `serde_json::from_*`.
    /// MICRO-PROFIT-FIX-1 啟動遷移：掃 positions 把 entry_notional == 0.0
    /// （舊快照反序列後以 serde default 填 0）的條目補成 qty × entry_price。
    /// 冪等、可多次呼叫；當前啟動路徑無紙盤快照復原，本方法為未來 JSON/IPC
    /// restore 路徑預留的防禦性遷移。
    pub fn migrate_legacy_entry_notional(&mut self) -> usize {
        let mut migrated = 0_usize;
        for pos in self.positions.values_mut() {
            if pos.entry_notional <= 0.0 && pos.qty > 0.0 && pos.entry_price > 0.0 {
                pos.entry_notional = pos.qty * pos.entry_price;
                migrated += 1;
            }
        }
        migrated
    }

    pub fn balance(&self) -> f64 {
        self.balance
    }

    // SEC-18: Clamp risk-parameter setters so a hostile/buggy IPC caller cannot
    // disable stops, zero-out timeouts, or invert signs. Values outside the sane
    // operating envelope are silently coerced to the nearest bound.
    // SEC-18：對風控參數 setter 加上邊界，避免 IPC 惡意/錯誤調用關閉止損或倒轉符號。
    // 超出安全運行區間的值會被靜默夾到最近的邊界。

    /// Set hard stop loss percentage. / 設定硬止損百分比。
    pub fn set_hard_stop_pct(&mut self, pct: f64) {
        // Allow between 0.5% (very tight) and 50% (very loose). Reject NaN.
        let v = if pct.is_finite() {
            pct.clamp(0.5, 50.0)
        } else {
            2.0
        };
        self.stop_config.hard_stop_pct = v;
    }

    /// Set trailing stop percentage (None = disabled). / 設定跟蹤止損百分比。
    pub fn set_trailing_stop_pct(&mut self, pct: Option<f64>) {
        self.stop_config.trailing_stop_pct = pct.and_then(|v| {
            if v.is_finite() {
                Some(v.clamp(0.1, 50.0))
            } else {
                None
            }
        });
    }

    /// Set trailing stop activation threshold (None = default to trail_pct).
    /// Textbook trailing stop: "activation%=profit required before trail engages".
    /// 設定跟蹤止損啟動閾值（None 時預設等於 trailing_stop_pct）。
    pub fn set_trailing_activation_pct(&mut self, pct: Option<f64>) {
        self.stop_config.trailing_activation_pct = pct.and_then(|v| {
            if v.is_finite() {
                Some(v.clamp(0.0, 50.0))
            } else {
                None
            }
        });
    }

    /// Set time stop hours (None = disabled). / 設定超時止損小時數。
    pub fn set_time_stop_hours(&mut self, hours: Option<f64>) {
        self.stop_config.time_stop_hours = hours.and_then(|v| {
            if v.is_finite() {
                // Minimum 0.25h (15min) to avoid "instant timeout" weaponisation.
                Some(v.clamp(0.25, 720.0))
            } else {
                None
            }
        });
    }

    /// Set ATR multiplier (None = disabled). / 設定 ATR 乘數。
    pub fn set_atr_multiplier(&mut self, mult: Option<f64>) {
        self.stop_config.atr_multiplier = mult.and_then(|v| {
            if v.is_finite() {
                Some(v.clamp(0.1, 20.0))
            } else {
                None
            }
        });
    }

    /// Set take profit percentage (None = disabled). / 設定止盈百分比。
    pub fn set_take_profit_pct(&mut self, pct: Option<f64>) {
        self.stop_config.take_profit_pct = pct.and_then(|v| {
            if v.is_finite() {
                // Minimum 0.1% so "instant take profit" cannot be triggered.
                Some(v.clamp(0.1, 1000.0))
            } else {
                None
            }
        });
    }

    /// Get current stop config reference. / 獲取當前止損配置引用。
    pub fn stop_config(&self) -> &stop_manager::StopConfig {
        &self.stop_config
    }

    pub fn position_count(&self) -> usize {
        self.positions.len()
    }

    pub fn positions(&self) -> Vec<&PaperPosition> {
        self.positions.values().collect()
    }

    /// Get a specific position by symbol (for duplicate check).
    /// 按交易對獲取特定持倉（用於重複檢查）。
    pub fn get_position(&self, symbol: &str) -> Option<&PaperPosition> {
        self.positions.get(symbol)
    }

    /// EDGE-P3-1 R2: set entry_context_id on an existing position.
    /// Caller invokes after `apply_fill` opens a new position (realized_pnl == 0.0
    /// AND position did not previously exist). No-op if position does not exist
    /// or `context_id` is empty. Silently overwrites (caller is responsible for
    /// only calling on fresh opens — accumulate fills must not overwrite the
    /// original entry's id).
    /// EDGE-P3-1 R2：在現有倉位上設定 entry_context_id。僅在 apply_fill 開新倉後
    /// 呼叫（realized_pnl == 0.0 且此前無該倉位）。空串或無倉位時 no-op。
    pub fn set_entry_context_id(&mut self, symbol: &str, context_id: &str) {
        if context_id.is_empty() {
            return;
        }
        if let Some(pos) = self.positions.get_mut(symbol) {
            pos.entry_context_id = context_id.to_string();
        }
    }

    /// EDGE-P3-1 R2: read entry_context_id from an existing position.
    /// Returns `None` if position does not exist or entry_context_id is empty.
    /// Called by `emit_close_fill` to thread the opening entry's context_id
    /// into `trading.fills.entry_context_id` for ML training JOIN.
    /// EDGE-P3-1 R2：讀取現有倉位的 entry_context_id。空或無倉位時返回 None。
    pub fn get_entry_context_id(&self, symbol: &str) -> Option<&str> {
        self.positions
            .get(symbol)
            .filter(|p| !p.entry_context_id.is_empty())
            .map(|p| p.entry_context_id.as_str())
    }

    pub fn drawdown_pct(&self) -> f64 {
        if self.forced_drawdown > 0.0 {
            return self.forced_drawdown;
        }
        if self.peak_balance <= 0.0 {
            return 0.0;
        }
        (self.peak_balance - self.balance) / self.peak_balance * 100.0
    }

    pub fn latest_price(&self, symbol: &str) -> Option<f64> {
        self.latest_prices.get(symbol).copied()
    }

    pub fn set_latest_price(&mut self, symbol: &str, price: f64) {
        self.latest_prices.insert(symbol.to_string(), price);
    }

    /// Get latest 24h turnover for a symbol (for dynamic slippage).
    /// 獲取交易對最新 24h 成交額（用於動態滑點）。
    pub fn latest_turnover(&self, symbol: &str) -> Option<f64> {
        self.latest_turnovers.get(symbol).copied()
    }

    pub fn set_latest_turnover(&mut self, symbol: &str, turnover: f64) {
        self.latest_turnovers.insert(symbol.to_string(), turnover);
    }

    /// Set Bybit Demo sync balance (Mode B). Call with None to disable sync mode.
    /// 設定 Bybit Demo 同步餘額（模式 B）。傳 None 關閉同步模式。
    pub fn set_bybit_sync_balance(&mut self, balance: Option<f64>) {
        self.bybit_sync_balance = balance;
    }

    pub fn bybit_sync_balance(&self) -> Option<f64> {
        self.bybit_sync_balance
    }

    /// EXT-1: In exchange mode, correct local balance from exchange wallet balance.
    /// Only applies correction if drift exceeds threshold (avoids micro-corrections on every tick).
    /// EXT-1：交易所模式下，從交易所錢包餘額修正本地餘額。
    /// 僅在偏差超過閾值時修正（避免每個 tick 微修正）。
    pub fn reconcile_balance_from_exchange(&mut self, exchange_balance: f64) -> Option<f64> {
        let drift = (self.balance - exchange_balance).abs();
        let drift_pct = if self.balance > 0.0 {
            drift / self.balance * 100.0
        } else {
            0.0
        };
        // Only correct if drift > 0.1% (avoids float noise)
        if drift_pct > 0.1 {
            let old = self.balance;
            self.balance = exchange_balance;
            self.peak_balance = self.peak_balance.max(exchange_balance);
            Some(old)
        } else {
            None
        }
    }

    /// Set API-reported unrealized PnL for a symbol (from WS position updates).
    /// 設定 API 報告的未實現損益（來自 WS 持倉更新）。
    pub fn set_api_unrealized_pnl(&mut self, symbol: &str, pnl: f64) {
        self.api_unrealized_pnl.insert(symbol.to_string(), pnl);
    }

    pub fn api_unrealized_pnl(&self, symbol: &str) -> Option<f64> {
        self.api_unrealized_pnl.get(symbol).copied()
    }

    /// B-1 Phase 2: Seed paper_state positions from exchange snapshot at startup.
    /// Replaces the entire positions map with the supplied list. Use the tuple
    /// `(symbol, is_long, qty, entry_price, ts_ms)`. Items with qty <= 0.0 or
    /// non-finite price are silently dropped (matches Bybit "size=0" stale rows).
    /// Returns the count of positions actually inserted. The latest_prices map
    /// is also seeded so trailing/stop checks have a non-zero reference price
    /// before the first market tick arrives.
    /// B-1 Phase 2：啟動時用交易所快照種入 paper_state 持倉。
    /// 直接以傳入清單覆蓋整個 positions map。元組格式為
    /// (symbol, is_long, qty, entry_price, ts_ms)。qty <= 0.0 或價格非有限值
    /// 的條目會被靜默丟棄（對應 Bybit 回傳的 "size=0" 殘留行）。
    /// 回傳實際插入的持倉數。同時種入 latest_prices，避免首個市場 tick 抵達前
    /// 跟蹤/止損檢查讀到 0 參考價。
    pub fn import_positions(
        &mut self,
        positions: Vec<(String, bool, f64, f64, u64)>,
    ) -> usize {
        self.positions_clear();
        let mut inserted = 0_usize;
        for (symbol, is_long, qty, entry_price, ts_ms) in positions {
            if qty <= 0.0 || !qty.is_finite() || !entry_price.is_finite() || entry_price <= 0.0 {
                continue;
            }
            self.latest_prices
                .entry(symbol.clone())
                .or_insert(entry_price);
            self.positions_insert(
                symbol.clone(),
                PaperPosition {
                    symbol,
                    is_long,
                    qty,
                    entry_price,
                    best_price: entry_price,
                    entry_fee: 0.0, // exchange did not bill fees through us — leave 0
                    entry_ts_ms: ts_ms,
                    unrealized_pnl: 0.0,
                    entry_context_id: String::new(),
                    owner_strategy: "bybit_sync".to_string(),
                    entry_notional: qty * entry_price,
                },
            );
            inserted += 1;
        }
        inserted
    }

    /// P0-6 FIX: Triage bybit_sync positions after startup import.
    /// Positions whose symbol is in `active_symbols` are adopted under the first
    /// matching strategy name. Positions NOT in the active universe would be evicted
    /// (removed from paper_state + mirror) and returned for close dispatch — UNLESS
    /// `dust_check(symbol, qty)` returns `Some((est_notional, min_notional))` where
    /// `est_notional < min_notional`, in which case the position is retained with
    /// `owner_strategy = DUST_FROZEN_STRATEGY` and NO close is dispatched (see
    /// DUST-EVICTION-GAP-1 / P1-8, 2026-04-17). Must be called AFTER `import_positions()`
    /// + `set_positions_mirror()`.
    ///
    /// `dust_check` contract:
    ///   - Return `None` → caller has no instrument info / no ref price → evict normally
    ///   - Return `Some((est_notional, min_notional))` where `est_notional >= min_notional`
    ///     → evict normally (close will succeed)
    ///   - Return `Some((est_notional, min_notional))` where `est_notional < min_notional`
    ///     → freeze as dust (close would be rejected by exchange anyway)
    ///
    /// P0-6 修復：啟動後對 bybit_sync 持倉分流。在活躍集合內 → 指派策略接管；
    /// 不在集合內 → 正常驅逐並派平倉，除非 dust_check 判定 est_notional < min_notional
    /// （DUST-EVICTION-GAP-1 / P1-8）則保留並標記 DUST_FROZEN_STRATEGY、不派平倉。
    pub fn triage_bybit_sync<F>(
        &mut self,
        active_symbols: &[String],
        strategy_names: &[&str],
        dust_check: F,
    ) -> TriageOutcome
    where
        F: Fn(&str, f64) -> Option<(f64, f64)>,
    {
        let mut outcome = TriageOutcome::default();

        let bybit_sync_symbols: Vec<String> = self
            .positions
            .values()
            .filter(|p| p.owner_strategy == "bybit_sync")
            .map(|p| p.symbol.clone())
            .collect();

        if bybit_sync_symbols.is_empty() {
            return outcome;
        }

        for symbol in bybit_sync_symbols {
            let in_universe = active_symbols.iter().any(|s| s == &symbol);
            if in_universe && !strategy_names.is_empty() {
                let strategy = strategy_names[0];
                if let Some(pos) = self.positions.get_mut(&symbol) {
                    pos.owner_strategy = strategy.to_string();
                    outcome
                        .adopted
                        .push((symbol, strategy.to_string()));
                }
                continue;
            }

            // Eviction path — first check whether dispatch would be rejected by
            // the exchange's min-notional gate. If so, freeze in place instead of
            // silently dropping from paper_state.
            // 驅逐路徑 — 先檢查 dispatch 是否會被交易所 min-notional 擋下。會被擋
            // 則就地凍結，不無聲從 paper_state 移除。
            let (is_long, qty) = match self.positions.get(&symbol) {
                Some(p) => (p.is_long, p.qty),
                None => continue,
            };
            if let Some((est_notional, min_notional)) = dust_check(&symbol, qty) {
                if est_notional < min_notional {
                    if let Some(pos) = self.positions.get_mut(&symbol) {
                        pos.owner_strategy =
                            crate::position_reconciler::orphan_handler::DUST_FROZEN_STRATEGY
                                .to_string();
                    }
                    outcome.dust_frozen.push((
                        symbol,
                        is_long,
                        qty,
                        est_notional,
                        min_notional,
                    ));
                    continue;
                }
            }
            if let Some(pos) = self.positions_remove(&symbol) {
                outcome
                    .evicted
                    .push((pos.symbol.clone(), pos.is_long, pos.qty));
            }
        }
        outcome
    }

    /// DUST-EVICTION-GAP-1 / P1-8 FUP (2026-04-17): per-tick opportunistic re-triage for a
    /// single symbol carrying a `SYNTHETIC_OWNER_LABELS` owner. Runs the exact same decision
    /// tree as startup `triage_bybit_sync` but at tick cadence, so conditions that blocked
    /// promotion/eviction at boot (notional below min, symbol outside scanner universe) can
    /// unlock naturally when price moves or scanner rotates — no restart or operator action
    /// required (§原則 #11 Agent 最大自主權).
    ///
    /// Covers all three synthetic labels in one pass:
    ///   - `bybit_sync`     — startup triage missed (race / registry not ready yet)
    ///   - `orphan_adopted` — Phase 2A adopted without positive edge; upgrade when conditions allow
    ///   - `orphan_frozen`  — P1-8 dust; upgrade when notional rises above min
    ///
    /// Positions owned by a real strategy (any name NOT in `SYNTHETIC_OWNER_LABELS`) are
    /// deliberately NOT touched — strategy lifecycle (SL/TP/close signals) stays authoritative.
    ///
    /// `min_notional = None` is treated as "no dust gate" (e.g., instrument cache empty in
    /// tests): dust-freeze branch is skipped; promotion/eviction still apply based on universe.
    ///
    /// DUST-EVICTION-GAP-1 / P1-8 FUP：單 symbol tick-level 機會性重分流。與啟動 triage
    /// 同一決策樹，但於 tick 節奏執行；啟動時阻擋升級的條件（名義值低 / 不在 universe）
    /// 自然解除時不需重啟或 operator 介入（§原則 #11）。
    /// 覆蓋三種 synthetic labels（bybit_sync / orphan_adopted / orphan_frozen）。
    /// 實策略擁有的倉位刻意不動，由策略自行管理生命週期。
    pub fn retriage_synthetic_owner(
        &mut self,
        symbol: &str,
        tick_price: f64,
        in_universe: bool,
        target_strategy: &str,
        min_notional: Option<f64>,
    ) -> RetriageOutcome {
        if tick_price <= 0.0 || !tick_price.is_finite() {
            return RetriageOutcome::NoOp;
        }
        let (is_long, qty, current_label) = match self.positions.get(symbol) {
            Some(p) => (p.is_long, p.qty, p.owner_strategy.clone()),
            None => return RetriageOutcome::NoOp,
        };
        if !SYNTHETIC_OWNER_LABELS.iter().any(|l| *l == current_label) {
            return RetriageOutcome::NoOp;
        }
        if qty <= 0.0 {
            return RetriageOutcome::NoOp;
        }

        let est_notional = qty * tick_price;

        // Dust branch — only when caller supplied a min_notional and we fall below it.
        // Dust 分支 — 僅當呼叫方提供 min_notional 且名義值低於門檻。
        if let Some(minn) = min_notional {
            if minn > 0.0 && est_notional < minn {
                let was_downgraded = current_label
                    != crate::position_reconciler::orphan_handler::DUST_FROZEN_STRATEGY;
                if was_downgraded {
                    if let Some(pos) = self.positions.get_mut(symbol) {
                        pos.owner_strategy =
                            crate::position_reconciler::orphan_handler::DUST_FROZEN_STRATEGY
                                .to_string();
                    }
                }
                return RetriageOutcome::FrozenAsDust {
                    est_notional,
                    min_notional: minn,
                    was_downgraded,
                };
            }
        }

        // Promote / evict branch — notional OK.
        // 升級 / 驅逐分支 — 名義值足夠。
        if in_universe && !target_strategy.is_empty() {
            if let Some(pos) = self.positions.get_mut(symbol) {
                pos.owner_strategy = target_strategy.to_string();
            }
            RetriageOutcome::Promoted {
                from: current_label,
                to: target_strategy.to_string(),
                est_notional,
            }
        } else {
            RetriageOutcome::NeedsEviction {
                is_long,
                qty,
                est_notional,
            }
        }
    }

    /// ORPHAN-ADOPT-1 Phase 2A: Adopt an exchange-reported orphan position into
    /// PaperState so StopManager + evaluate_actions treat it as any other open
    /// position. When `owner` is `None`, falls back to `ORPHAN_ADOPTED_STRATEGY`;
    /// when `Some(name)`, the position is attributed to a real strategy (P0-6:
    /// lets the triggering strategy own lifecycle + PnL attribution).
    ///
    /// Idempotent: if a same-direction (symbol, is_long) is already tracked —
    /// which should be rare because the reconciler consults the side-car mirror
    /// before classifying orphans — this is a no-op that returns false. A
    /// direction flip is NOT handled here on purpose; `upsert_position_from_exchange`
    /// owns flip semantics via the WS event stream.
    ///
    /// Returns true iff a new PaperPosition was actually inserted. `latest_prices`
    /// is seeded with `entry_price` so StopManager has an immediate reference tick.
    /// ORPHAN-ADOPT-1 Phase 2A：將交易所回報的孤兒倉位接管進 PaperState。
    /// owner 為 None 時用 ORPHAN_ADOPTED_STRATEGY，Some 時歸屬真實策略
    /// （P0-6：讓觸發策略負責生命週期 + PnL 歸因）。
    /// 冪等：同向 (symbol, is_long) 已存在時為 no-op；方向翻轉由 ws upsert 負責。
    pub fn adopt_orphan(
        &mut self,
        symbol: &str,
        is_long: bool,
        qty: f64,
        entry_price: f64,
        ts_ms: u64,
        owner: Option<&str>,
    ) -> bool {
        if qty <= 0.0 || !qty.is_finite() || entry_price <= 0.0 || !entry_price.is_finite() {
            return false;
        }
        if let Some(existing) = self.positions.get(symbol) {
            if existing.is_long == is_long {
                return false;
            }
        }
        let owner_strategy = owner
            .unwrap_or(crate::position_reconciler::orphan_handler::ORPHAN_ADOPTED_STRATEGY)
            .to_string();
        self.latest_prices
            .entry(symbol.to_string())
            .or_insert(entry_price);
        self.positions_insert(
            symbol.to_string(),
            PaperPosition {
                symbol: symbol.to_string(),
                is_long,
                qty,
                entry_price,
                best_price: entry_price,
                entry_fee: 0.0,
                entry_ts_ms: ts_ms,
                unrealized_pnl: 0.0,
                entry_context_id: String::new(),
                owner_strategy,
                entry_notional: qty * entry_price,
            },
        );
        true
    }

    /// B-1 Phase 2: Apply a runtime PositionUpdate from the exchange WS to paper_state.
    /// `size == 0` removes the entry (the exchange just reported a flat position).
    /// `size > 0` upserts using the latest avg entry price reported by the exchange;
    /// existing entries are updated in place so trailing-stop best_price is preserved
    /// when only size/avg_price changed.
    /// Returns true if anything was changed.
    /// B-1 Phase 2：將交易所 WS 推送的 PositionUpdate 應用到 paper_state。
    /// size == 0 表示交易所側已平倉，移除條目。size > 0 則 upsert：若條目存在
    /// 則就地更新（保留 best_price，避免重設跟蹤止損），否則新建。
    /// 任何狀態變動都回傳 true。
    pub fn upsert_position_from_exchange(
        &mut self,
        symbol: &str,
        is_long: bool,
        size: f64,
        avg_price: f64,
        ts_ms: u64,
    ) -> bool {
        if !size.is_finite() || size < 0.0 {
            return false;
        }
        if size == 0.0 {
            return self.positions_remove(symbol).is_some();
        }
        if !avg_price.is_finite() || avg_price <= 0.0 {
            return false;
        }
        match self.positions.get_mut(symbol) {
            Some(pos) => {
                // Capture old direction BEFORE mutating, so the flip-detection
                // comparison still has something meaningful to compare against.
                // 在改寫前先記下舊方向，方向翻轉的判斷才會正確。
                let direction_flipped = pos.is_long != is_long;
                pos.is_long = is_long;
                pos.qty = size;
                pos.entry_price = avg_price;
                // Reset best_price only if direction flipped (different position).
                // Same-direction upsert preserves best_price so trailing-stop tracking
                // does not reset on every WS heartbeat.
                // 方向翻轉視為新倉，best_price 重置；同向僅尺寸/均價變動則保留，
                // 避免每次 WS 心跳重置跟蹤止損狀態。
                if direction_flipped {
                    pos.best_price = avg_price;
                    pos.entry_ts_ms = ts_ms;
                    pos.entry_fee = 0.0;
                    // MICRO-PROFIT-FIX-1: direction flip = brand-new position, reset entry_notional.
                    // MICRO-PROFIT-FIX-1：方向翻轉視為新倉，重設 entry_notional。
                    pos.entry_notional = size * avg_price;
                }
                // Mirror: keep `(symbol → is_long)` in sync (covers direction flip).
                // 鏡像：同步 is_long（覆蓋方向翻轉）。
                self.positions_mirror
                    .write()
                    .insert(symbol.to_string(), is_long);
                true
            }
            None => {
                self.positions_insert(
                    symbol.to_string(),
                    PaperPosition {
                        symbol: symbol.to_string(),
                        is_long,
                        qty: size,
                        entry_price: avg_price,
                        best_price: avg_price,
                        entry_fee: 0.0,
                        entry_ts_ms: ts_ms,
                        unrealized_pnl: 0.0,
                        entry_context_id: String::new(),
                        owner_strategy: "bybit_sync".to_string(),
                        entry_notional: size * avg_price,
                    },
                );
                true
            }
        }
    }

    /// Get hard stop percentage from config (for server-side stop calc).
    /// 從配置獲取硬止損百分比（用於伺服器端止損計算）。
    pub fn stop_config_pct(&self) -> f64 {
        self.stop_config.hard_stop_pct
    }

    /// For testing: force a specific drawdown percentage.
    /// 用於測試：強制特定回撤百分比。
    pub fn force_drawdown(&mut self, pct: f64) {
        self.forced_drawdown = pct;
    }

    /// Read total cumulative fees charged to the paper account (open + close).
    /// 讀取累計手續費（含開倉與平倉）。
    pub fn total_fees(&self) -> f64 {
        self.total_fees
    }

    /// Read total cumulative realized PnL (only non-zero on close fills).
    /// 讀取累計已實現損益（僅平倉成交貢獻）。
    pub fn total_realized_pnl(&self) -> f64 {
        self.total_realized_pnl
    }

    /// Read total round-trip count (= number of close fills applied).
    /// 讀取完成的 round-trip 數（= 已套用的平倉成交數）。
    pub fn trade_count(&self) -> u32 {
        self.trade_count
    }

    /// QoL-1: Apply aggregated counters previously computed from `trading.fills`.
    /// Pure helper (no DB I/O) so unit tests can exercise restore semantics without
    /// depending on a live Postgres. Adjusts balance by `realized_pnl_sum - fees_sum`
    /// so that `balance` reflects the same trajectory as if every historical fill had
    /// been replayed through `apply_fill()`, and bumps `peak_balance` to match.
    /// `trade_count` is saturating-cast to `u32`; negative values from a malformed
    /// `COUNT(*)` cast are clamped to 0.
    /// QoL-1：套用自 `trading.fills` 聚合得出的累計指標。
    /// 純函數（無 DB I/O），方便單元測試驗證語義。同步調整 balance
    /// （加上 realized_pnl_sum，扣除 fees_sum），讓餘額軌跡與逐筆重放
    /// `apply_fill()` 等價，並更新 peak_balance。trade_count 飽和轉 u32，
    /// 遇到異常負值夾到 0。
    pub fn apply_restored_counters(
        &mut self,
        total_fees_sum: f64,
        total_realized_pnl_sum: f64,
        trade_count_i64: i64,
    ) {
        // Guard against NaN / non-finite DB rows — leave state untouched.
        // 防護非有限 DB 回傳 — 保持狀態不變。
        if !total_fees_sum.is_finite() || !total_realized_pnl_sum.is_finite() {
            return;
        }
        self.total_fees = total_fees_sum.max(0.0);
        self.total_realized_pnl = total_realized_pnl_sum;
        self.trade_count = if trade_count_i64 < 0 {
            0
        } else if trade_count_i64 > u32::MAX as i64 {
            u32::MAX
        } else {
            trade_count_i64 as u32
        };
        // Balance reflects initial_balance + realized_pnl - fees so the paper
        // account shows the same equity curve as if every historical fill had
        // been replayed through apply_fill(). peak_balance rises accordingly
        // so drawdown_pct starts at 0 right after restore (we have no history
        // of intra-run peaks to reconstruct).
        // 餘額 = 初始 + 已實現 - 手續費，讓啟動後的權益曲線與逐筆重放
        // apply_fill() 等價。peak_balance 同步抬升，避免剛還原就出現虛假回撤。
        let restored_balance = self._initial_balance + self.total_realized_pnl - self.total_fees;
        self.balance = restored_balance;
        self.peak_balance = self.peak_balance.max(restored_balance);
    }

    /// QoL-1: Restore cumulative counters from `trading.fills` aggregated per
    /// `engine_mode` (paper / demo / live). Each engine's counters are isolated
    /// via the `engine_mode = $1` filter, matching the writer side.
    ///
    /// Aggregation contract (matches `apply_fill()` semantics):
    ///   * `total_fees`         = SUM(fee)                     — every fill bills a fee
    ///   * `total_realized_pnl` = SUM(realized_pnl)            — opens write 0, closes write non-zero
    ///   * `trade_count`        = COUNT(*) WHERE realized_pnl <> 0 — round-trips only
    ///
    /// Fail-soft: DB errors propagate to the caller but state is NOT mutated,
    /// so a cold-start restore failure leaves the engine with the same
    /// zero-initialised counters it had before. Caller must log + continue.
    ///
    /// QoL-1：按 `engine_mode`（paper/demo/live）從 `trading.fills` 聚合恢復累計指標。
    /// 三引擎並行時各自獨立，透過 `engine_mode = $1` 過濾。語義與 `apply_fill()` 對齊：
    ///   * `total_fees` = SUM(fee) — 所有成交（含開倉/平倉）都收費
    ///   * `total_realized_pnl` = SUM(realized_pnl) — 開倉 0、平倉非 0，直接求和等價
    ///   * `trade_count` = COUNT(*) WHERE realized_pnl <> 0 — 僅 round-trip
    /// Fail-soft：DB 錯誤向上拋但 `&mut self` 不修改，呼叫端紀錄 warning 後繼續啟動。
    pub async fn restore_from_db(
        &mut self,
        pool: &sqlx::PgPool,
        engine_mode: &str,
    ) -> Result<(), sqlx::Error> {
        // Cast to fixed-width float/int types to avoid sqlx type-negotiation
        // surprises on real/numeric columns. COALESCE folds empty result-set to 0.
        // 強制轉型 float8 / bigint 避免 real/numeric 推斷麻煩；COALESCE 讓空表結果為 0。
        let row: (f64, f64, i64) = sqlx::query_as(
            "SELECT \
                 COALESCE(SUM(fee), 0)::float8          AS total_fees, \
                 COALESCE(SUM(realized_pnl), 0)::float8 AS total_realized_pnl, \
                 COALESCE(COUNT(*) FILTER (WHERE realized_pnl <> 0), 0)::bigint \
                     AS trade_count \
             FROM trading.fills \
             WHERE engine_mode = $1",
        )
        .bind(engine_mode)
        .fetch_one(pool)
        .await?;

        self.apply_restored_counters(row.0, row.1, row.2);
        Ok(())
    }

    /// PNL-FIX-2: Charge a standalone fee against the paper account.
    /// Used by `emit_close_fill` so risk/strategy/fast_track closes — which all
    /// route through the synchronous `close_position()` path (no fee param) —
    /// still bill the same maker/taker fee a real close would incur.
    /// `apply_fill` already bills its own fee on the open path; this helper is
    /// strictly for the close-only paths.
    /// PNL-FIX-2：對紙盤帳戶單獨計入一筆費用。
    /// 風控/策略/fast_track 平倉走的是同步 `close_position()` 路徑，原本不收費。
    /// 開倉路徑由 `apply_fill` 自行收費，本 helper 僅供 close-only 路徑使用。
    pub fn charge_fee(&mut self, fee: f64) {
        if fee <= 0.0 || !fee.is_finite() {
            return;
        }
        self.balance -= fee;
        self.total_fees += fee;
    }

    /// Apply a fill to paper state.
    /// 在紙盤狀態上應用成交。
    /// Apply a fill and return the realized PnL (0.0 for opens/accumulates, non-zero for closes).
    /// 應用成交並返回已實現損益（開倉/加倉返回 0.0，平倉返回非零值）。
    pub fn apply_fill(
        &mut self,
        symbol: &str,
        is_long: bool,
        qty: f64,
        fill_price: f64,
        fee: f64,
        ts_ms: u64,
        owner_strategy: &str,
    ) -> f64 {
        // Guard: reject zero-qty fills (prevents ghost positions)
        // 防護：拒絕零數量成交（防止幽靈持倉）
        if qty <= 0.0 || fill_price <= 0.0 {
            return 0.0;
        }
        self.balance -= fee;
        self.total_fees += fee;
        self.set_latest_price(symbol, fill_price);

        if let Some(pos) = self.positions.get(symbol) {
            if pos.is_long != is_long {
                // Closing position (opposite direction)
                // 平倉（反方向）
                let close_qty = pos.qty.min(qty);
                let pnl = if pos.is_long {
                    (fill_price - pos.entry_price) * close_qty
                } else {
                    (pos.entry_price - fill_price) * close_qty
                };
                self.balance += pnl;
                self.total_realized_pnl += pnl;
                self.trade_count += 1;
                // P0-1 fix: Only remove position if fully closed; reduce qty on partial close
                // P0-1 修復：僅在完全平倉時移除持倉；部分平倉時減少數量
                let remaining = pos.qty - close_qty;
                if remaining > 1e-12 {
                    let mut updated = pos.clone();
                    updated.qty = remaining;
                    self.positions_insert(symbol.to_string(), updated);
                } else {
                    self.positions_remove(symbol);
                }
                self.peak_balance = self.peak_balance.max(self.balance);
                return pnl;
            } else {
                // Same direction — accumulate (weighted average entry price)
                // 同方向 — 累加（加權平均入場價）
                let old_qty = pos.qty;
                let old_entry = pos.entry_price;
                let new_qty = old_qty + qty;
                let avg_entry = (old_entry * old_qty + fill_price * qty) / new_qty;
                let mut updated = pos.clone();
                updated.qty = new_qty;
                updated.entry_price = avg_entry;
                updated.entry_fee += fee;
                // MICRO-PROFIT-FIX-1 (option 2, accumulate): same-direction adds
                // grow entry_notional by this fill's notional. Reductions leave
                // it alone, so ft_min_notional_ratio_of_entry compares against
                // the peak accumulated entry — not a shrinking baseline.
                // MICRO-PROFIT-FIX-1（選項 2，累加）：同向加倉累加 entry_notional。
                // 減倉不動，讓 ft_min_notional_ratio_of_entry 以累積峰值為基準。
                updated.entry_notional += qty * fill_price;
                self.positions_insert(symbol.to_string(), updated);
                return 0.0;
            }
        }

        // Opening new position (no existing position for this symbol)
        // 開新倉（此交易對無現有持倉）
        self.positions_insert(
            symbol.to_string(),
            PaperPosition {
                symbol: symbol.to_string(),
                is_long,
                qty,
                entry_price: fill_price,
                best_price: fill_price,
                entry_fee: fee,
                entry_ts_ms: ts_ms,
                unrealized_pnl: 0.0,
                entry_context_id: String::new(),
                owner_strategy: owner_strategy.to_string(),
                entry_notional: qty * fill_price,
            },
        );
        0.0 // Opening position — no realized PnL / 開倉無已實現損益
    }

    /// Close a position at market price. Returns realized PnL on close,
    /// None if no position existed for the symbol. (DB-RUN-3: caller should
    /// emit a TradingMsg::Fill with the returned PnL so trading.fills records
    /// non-zero realized_pnl for risk/stop-driven closes.)
    /// 以市場價平倉，返回已實現損益（None=無持倉）。DB-RUN-3：呼叫端應依此 PnL
    /// 發送 TradingMsg::Fill，避免風控/止損平倉的 realized_pnl 落為 0。
    pub fn close_position(&mut self, symbol: &str, price: f64, _ts_ms: u64) -> Option<f64> {
        if let Some(pos) = self.positions_remove(symbol) {
            let pnl = if pos.is_long {
                (price - pos.entry_price) * pos.qty
            } else {
                (pos.entry_price - price) * pos.qty
            };
            self.balance += pnl;
            self.total_realized_pnl += pnl;
            self.trade_count += 1;
            self.peak_balance = self.peak_balance.max(self.balance);
            Some(pnl)
        } else {
            None
        }
    }

    /// Reduce a position by `reduce_qty` at `price`. If reduce_qty >= position qty,
    /// closes the entire position. Returns realized PnL for the reduced portion.
    /// FIX-03: Used by fast_track ReduceToHalf.
    /// 按 reduce_qty 減倉。若 reduce_qty >= 持倉量則全平。返回減倉部分的已實現損益。
    pub fn reduce_position(&mut self, symbol: &str, reduce_qty: f64, price: f64) -> f64 {
        if let Some(pos) = self.positions.get_mut(symbol) {
            let actual_reduce = reduce_qty.min(pos.qty);
            let pnl = if pos.is_long {
                (price - pos.entry_price) * actual_reduce
            } else {
                (pos.entry_price - price) * actual_reduce
            };
            self.balance += pnl;
            self.total_realized_pnl += pnl;
            pos.qty -= actual_reduce;
            if pos.qty < 1e-12 {
                // Fully closed / 全部平倉
                self.positions_remove(symbol);
                self.trade_count += 1;
            }
            self.peak_balance = self.peak_balance.max(self.balance);
            pnl
        } else {
            0.0
        }
    }

    /// Close a single position at current market price (falls back to entry price if no live
    /// price available). Returns realized PnL or None if no position exists for the symbol.
    /// 以當前市場價平掉單一持倉（無市場價時回退入場價），返回已實現損益或 None。
    pub fn close_position_at_market(&mut self, symbol: &str) -> Option<f64> {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0);
        let price = self.latest_prices.get(symbol).copied().unwrap_or_else(|| {
            // Fallback to entry price if no live market price / 無市場價時回退到入場價
            self.positions
                .get(symbol)
                .map(|p| p.entry_price)
                .unwrap_or(0.0)
        });
        self.close_position(symbol, price, now)
    }

    /// Close all open positions at their latest market price.
    /// Returns the number of positions closed.
    /// 以最新市場價平掉所有持倉，返回已平倉數量。
    pub fn close_all_positions(&mut self) -> usize {
        let symbols: Vec<String> = self.positions.keys().cloned().collect();
        let mut closed = 0;
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0);
        for symbol in &symbols {
            let price = self.latest_prices.get(symbol).copied().unwrap_or_else(|| {
                // Fallback to entry price if no market price available
                // 無市場價時回退到入場價
                self.positions
                    .get(symbol)
                    .map(|p| p.entry_price)
                    .unwrap_or(0.0)
            });
            self.close_position(symbol, price, now);
            closed += 1;
        }
        closed
    }

    /// Check stops on all positions using per-symbol latest prices.
    /// 使用每個交易對的最新價格檢查所有持倉的止損。
    /// RRC-1-C1: Update best_price for all positions (trailing stop tracking).
    /// RRC-1-C1：更新所有持倉的最佳價格（跟蹤止損追蹤）。
    pub fn update_best_prices(&mut self) {
        let latest = self.latest_prices.clone();
        for (symbol, pos) in &mut self.positions {
            if let Some(&sym_price) = latest.get(symbol.as_str()) {
                let mut ps = PositionState {
                    entry_price: pos.entry_price,
                    best_price: pos.best_price,
                    is_long: pos.is_long,
                    entry_ts_ms: pos.entry_ts_ms,
                };
                stop_manager::update_best_price(&mut ps, sym_price);
                pos.best_price = ps.best_price;
            }
        }
    }

    pub fn check_stops(&mut self, _price: f64, now_ms: u64) -> Vec<(String, StopTrigger)> {
        let mut triggers = Vec::new();
        let latest = self.latest_prices.clone();
        for (symbol, pos) in &mut self.positions {
            let sym_price = match latest.get(symbol.as_str()) {
                Some(&p) => p,
                None => continue, // no price yet for this symbol
            };
            let mut ps = PositionState {
                entry_price: pos.entry_price,
                best_price: pos.best_price,
                is_long: pos.is_long,
                entry_ts_ms: pos.entry_ts_ms,
            };
            stop_manager::update_best_price(&mut ps, sym_price);
            pos.best_price = ps.best_price;

            if let Some(trigger) =
                stop_manager::check_stops(&self.stop_config, &ps, sym_price, now_ms)
            {
                triggers.push((symbol.clone(), trigger));
            }
        }
        triggers
    }

    /// Export state for persistence (with real-time unrealized PnL).
    /// 導出狀態用於持久化（含即時未實現損益）。
    pub fn export_state(&self) -> PaperStateSnapshot {
        let positions: Vec<PositionSnapshot> = self
            .positions
            .values()
            .map(|pos| {
                // Compute real unrealized PnL using latest price for this symbol (QC fix).
                // 使用該交易對最新價格計算真實未實現損益。
                let current_price = self
                    .latest_prices
                    .get(&pos.symbol)
                    .copied()
                    .unwrap_or(pos.entry_price);
                let unrealized_pnl = if pos.is_long {
                    (current_price - pos.entry_price) * pos.qty
                } else {
                    (pos.entry_price - current_price) * pos.qty
                };
                PositionSnapshot {
                    position: PaperPosition {
                        unrealized_pnl,
                        ..pos.clone()
                    },
                    api_pnl: self.api_unrealized_pnl.get(&pos.symbol).copied(),
                }
            })
            .collect();
        PaperStateSnapshot {
            balance: self.balance,
            initial_balance: self._initial_balance,
            peak_balance: self.peak_balance,
            total_realized_pnl: self.total_realized_pnl,
            total_fees: self.total_fees,
            trade_count: self.trade_count,
            positions,
            bybit_sync_balance: self.bybit_sync_balance,
        }
    }
}

/// Per-position snapshot with optional API PnL for comparison (M5 fix).
/// 每倉位快照，含可選 API PnL 對比（M5 修復）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PositionSnapshot {
    #[serde(flatten)]
    pub position: PaperPosition,
    /// API-reported unrealized PnL (from Bybit WS position updates).
    /// API 報告的未實現損益（來自 Bybit WS 持倉更新）。
    #[serde(skip_serializing_if = "Option::is_none")]
    pub api_pnl: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PaperStateSnapshot {
    pub balance: f64,
    /// The balance the engine was initialized with (never changes after startup).
    /// 引擎啟動時的初始餘額（啟動後永不改變）。
    pub initial_balance: f64,
    pub peak_balance: f64,
    pub total_realized_pnl: f64,
    pub total_fees: f64,
    pub trade_count: u32,
    pub positions: Vec<PositionSnapshot>,
    /// Bybit Demo sync balance for comparison (None = custom mode).
    /// Bybit Demo 同步餘額用於對比（None = 自設金額模式）。
    #[serde(skip_serializing_if = "Option::is_none")]
    pub bybit_sync_balance: Option<f64>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_initial_state() {
        let s = PaperState::new(10000.0);
        assert_eq!(s.balance(), 10000.0);
        assert_eq!(s.position_count(), 0);
        assert_eq!(s.drawdown_pct(), 0.0);
    }

    #[test]
    fn test_open_and_close_long() {
        let mut s = PaperState::new(10000.0);
        s.apply_fill("BTC", true, 0.1, 50000.0, 2.75, 0, "test");
        assert_eq!(s.position_count(), 1);

        s.close_position("BTC", 51000.0, 1000);
        assert_eq!(s.position_count(), 0);
        // PnL: (51000-50000) * 0.1 = 100 - 2.75 fee = 97.25
        assert!((s.balance() - 10097.25).abs() < 0.01);
    }

    #[test]
    fn test_open_and_close_short() {
        let mut s = PaperState::new(10000.0);
        s.apply_fill("BTC", false, 0.1, 50000.0, 2.75, 0, "test");
        s.close_position("BTC", 49000.0, 1000);
        // PnL: (50000-49000) * 0.1 = 100 - 2.75 fee
        assert!((s.balance() - 10097.25).abs() < 0.01);
    }

    #[test]
    fn test_drawdown() {
        let mut s = PaperState::new(10000.0);
        s.apply_fill("BTC", true, 0.1, 50000.0, 0.0, 0, "test");
        s.close_position("BTC", 45000.0, 1000);
        // Loss: (45000-50000) * 0.1 = -500
        assert!(s.drawdown_pct() > 0.0);
    }

    #[test]
    fn test_stop_check() {
        let mut s = PaperState::new(10000.0);
        s.apply_fill("BTC", true, 0.1, 50000.0, 0.0, 0, "test");
        s.set_latest_price("BTC", 46000.0); // per-symbol price for stop check
        let triggers = s.check_stops(46000.0, 1000);
        assert_eq!(triggers.len(), 1); // hard stop at 5%
    }

    #[test]
    fn test_latest_price() {
        let mut s = PaperState::new(10000.0);
        s.set_latest_price("BTC", 50000.0);
        assert_eq!(s.latest_price("BTC"), Some(50000.0));
        assert_eq!(s.latest_price("ETH"), None);
    }

    #[test]
    fn test_export_state() {
        let s = PaperState::new(10000.0);
        let snap = s.export_state();
        assert_eq!(snap.balance, 10000.0);
        assert!(snap.positions.is_empty());
    }

    #[test]
    fn test_same_direction_accumulates() {
        // Same-direction fills should accumulate qty with weighted avg entry.
        // 同方向成交應累加 qty 並加權平均入場價。
        let mut s = PaperState::new(10000.0);
        s.apply_fill("BTC", true, 0.1, 50000.0, 1.0, 0, "test"); // buy 0.1 @ 50000
        s.apply_fill("BTC", true, 0.1, 52000.0, 1.0, 1000, "test"); // buy 0.1 @ 52000
        assert_eq!(s.position_count(), 1);
        let pos = s.get_position("BTC").unwrap();
        assert!((pos.qty - 0.2).abs() < 1e-10); // 0.1 + 0.1
        assert!((pos.entry_price - 51000.0).abs() < 0.01); // avg(50000, 52000)
    }

    #[test]
    fn test_same_direction_does_not_reset_entry() {
        // Verify same-direction fill doesn't replace position (old bug: insert overwrites).
        // 驗證同方向成交不會覆蓋持倉（舊 bug：insert 直接替換）。
        let mut s = PaperState::new(10000.0);
        s.apply_fill("BTC", false, 0.05, 60000.0, 0.5, 0, "test");
        let initial_fee = s.get_position("BTC").unwrap().entry_fee;
        s.apply_fill("BTC", false, 0.05, 61000.0, 0.5, 1000, "test");
        let pos = s.get_position("BTC").unwrap();
        assert!((pos.qty - 0.10).abs() < 1e-10);
        assert!((pos.entry_price - 60500.0).abs() < 0.01);
        assert!((pos.entry_fee - 1.0).abs() < 1e-10); // accumulated fees
    }

    #[test]
    fn test_opposite_direction_closes() {
        // Opposite direction fill closes the position with PnL.
        // 反方向成交平倉並計算 PnL。
        let mut s = PaperState::new(10000.0);
        s.apply_fill("BTC", true, 0.1, 50000.0, 0.0, 0, "test");
        s.apply_fill("BTC", false, 0.1, 51000.0, 0.0, 1000, "test"); // close
        assert_eq!(s.position_count(), 0);
        assert!((s.total_realized_pnl - 100.0).abs() < 0.01); // (51000-50000)*0.1
    }

    #[test]
    fn test_close_all_positions() {
        // close_all_positions should close every open position at latest price.
        // close_all_positions 應以最新價格平掉所有持倉。
        let mut s = PaperState::new(10000.0);
        s.apply_fill("BTC", true, 0.1, 50000.0, 0.0, 0, "test");
        s.apply_fill("ETH", false, 1.0, 3000.0, 0.0, 0, "test");
        s.set_latest_price("BTC", 51000.0);
        s.set_latest_price("ETH", 2900.0);
        assert_eq!(s.position_count(), 2);

        let closed = s.close_all_positions();
        assert_eq!(closed, 2);
        assert_eq!(s.position_count(), 0);
        // BTC PnL: (51000-50000)*0.1 = 100, ETH PnL: (3000-2900)*1.0 = 100
        assert!((s.balance() - 10200.0).abs() < 0.01);
    }

    #[test]
    fn test_get_position() {
        let mut s = PaperState::new(10000.0);
        assert!(s.get_position("BTC").is_none());
        s.apply_fill("BTC", true, 0.1, 50000.0, 0.0, 0, "test");
        assert!(s.get_position("BTC").is_some());
        assert!(s.get_position("ETH").is_none());
    }

    #[test]
    fn test_import_positions_seeds_state() {
        // B-1 Phase 2: import_positions replaces the map and seeds latest_prices.
        // B-1 Phase 2：import_positions 覆蓋持倉並種入 latest_prices。
        let mut s = PaperState::new(10000.0);
        // Pre-existing position should be wiped by import_positions.
        // 既有持倉應被 import_positions 清掉。
        s.apply_fill("STALE", true, 1.0, 10.0, 0.0, 0, "test");
        let inserted = s.import_positions(vec![
            ("BTCUSDT".to_string(), true, 0.5, 50_000.0, 1_000),
            ("ETHUSDT".to_string(), false, 2.0, 3_000.0, 1_001),
            ("ZERO".to_string(), true, 0.0, 1.0, 0),       // skipped (qty=0)
            ("BAD".to_string(), true, 1.0, -5.0, 0),       // skipped (price<=0)
        ]);
        assert_eq!(inserted, 2);
        assert_eq!(s.position_count(), 2);
        assert!(s.get_position("STALE").is_none());

        let btc = s.get_position("BTCUSDT").unwrap();
        assert!(btc.is_long);
        assert!((btc.qty - 0.5).abs() < 1e-12);
        assert!((btc.entry_price - 50_000.0).abs() < 1e-9);
        assert_eq!(s.latest_price("BTCUSDT"), Some(50_000.0));

        let eth = s.get_position("ETHUSDT").unwrap();
        assert!(!eth.is_long);
        assert!((eth.qty - 2.0).abs() < 1e-12);
    }

    // ---------------------------------------------------------------
    // ORPHAN-ADOPT-1 Phase 2A: adopt_orphan semantics
    // ORPHAN-ADOPT-1 Phase 2A：adopt_orphan 語義測試
    // ---------------------------------------------------------------

    /// adopt_orphan inserts a new position with owner_strategy = "orphan_adopted",
    /// seeds latest_prices, and syncs the positions_mirror side-car.
    /// adopt_orphan 插入 owner_strategy="orphan_adopted" 的新倉位，
    /// 種入 latest_prices 並同步 positions_mirror。
    #[test]
    fn test_adopt_orphan_inserts_and_mirrors() {
        let mut s = PaperState::new(10_000.0);
        let mirror = s.positions_mirror();
        assert!(mirror.read().is_empty());

        let inserted = s.adopt_orphan("BTCUSDT", true, 0.1, 50_000.0, 1_700_000_000_000, None);
        assert!(inserted);

        let pos = s.get_position("BTCUSDT").expect("position must be present");
        assert!(pos.is_long);
        assert!((pos.qty - 0.1).abs() < 1e-12);
        assert!((pos.entry_price - 50_000.0).abs() < 1e-9);
        assert!((pos.best_price - 50_000.0).abs() < 1e-9);
        assert_eq!(
            pos.owner_strategy,
            crate::position_reconciler::orphan_handler::ORPHAN_ADOPTED_STRATEGY
        );
        assert_eq!(s.latest_price("BTCUSDT"), Some(50_000.0));
        assert_eq!(mirror.read().get("BTCUSDT"), Some(&true));
    }

    /// adopt_orphan is a no-op when the same-direction position is already
    /// tracked (idempotent — mirror should already have suppressed the orphan).
    /// adopt_orphan 對同向已存在的倉位為 no-op（冪等）。
    #[test]
    fn test_adopt_orphan_idempotent_same_direction() {
        let mut s = PaperState::new(10_000.0);
        s.apply_fill("BTCUSDT", true, 0.1, 50_000.0, 0.0, 1_000, "ma_crossover");
        // Pre-adopt state: ma_crossover owns it.
        // 預 adopt 狀態：ma_crossover 擁有。
        assert_eq!(
            s.get_position("BTCUSDT").unwrap().owner_strategy,
            "ma_crossover"
        );
        let inserted =
            s.adopt_orphan("BTCUSDT", true, 0.2, 51_000.0, 1_700_000_000_000, None);
        assert!(!inserted, "same-direction adopt must be no-op");
        // Original owner preserved — no strategy overwrite.
        // 原 owner 保留，沒有被覆寫。
        let pos = s.get_position("BTCUSDT").unwrap();
        assert_eq!(pos.owner_strategy, "ma_crossover");
        assert!((pos.qty - 0.1).abs() < 1e-12);
    }

    /// adopt_orphan rejects invalid qty / entry_price.
    /// adopt_orphan 拒絕無效 qty / entry_price。
    #[test]
    fn test_adopt_orphan_rejects_invalid_inputs() {
        let mut s = PaperState::new(10_000.0);
        assert!(!s.adopt_orphan("X", true, 0.0, 100.0, 0, None));
        assert!(!s.adopt_orphan("X", true, -1.0, 100.0, 0, None));
        assert!(!s.adopt_orphan("X", true, f64::NAN, 100.0, 0, None));
        assert!(!s.adopt_orphan("X", true, 1.0, 0.0, 0, None));
        assert!(!s.adopt_orphan("X", true, 1.0, -5.0, 0, None));
        assert!(!s.adopt_orphan("X", true, 1.0, f64::NAN, 0, None));
        assert!(s.get_position("X").is_none());
    }

    // ---------------------------------------------------------------
    // QoL-1: restore_from_db semantics
    // QoL-1：restore_from_db 語義測試
    // ---------------------------------------------------------------

    /// Empty DB (all zeros) must leave counters at 0 and balance untouched.
    /// 空表聚合結果為 0 — 計數器與餘額保持不變。
    #[test]
    fn test_restore_counters_empty_db_leaves_state_zero() {
        let mut s = PaperState::new(10_000.0);
        s.apply_restored_counters(0.0, 0.0, 0);
        assert!((s.total_fees() - 0.0).abs() < 1e-12);
        assert!((s.total_realized_pnl() - 0.0).abs() < 1e-12);
        assert_eq!(s.trade_count(), 0);
        // balance = initial + 0 - 0
        assert!((s.balance() - 10_000.0).abs() < 1e-9);
    }

    /// Closes only: realized_pnl non-zero, trade_count = number of closes,
    /// balance reflects pnl - fees.
    /// 全為 close fill：realized_pnl 非零、trade_count = 平倉數，餘額 = pnl - fees。
    #[test]
    fn test_restore_counters_close_fills_aggregate_correctly() {
        let mut s = PaperState::new(10_000.0);
        // Simulate 3 round-trips: +$120, -$40, +$85 gross; fees $1.5+$1.2+$1.8 = $4.5.
        // 模擬 3 個 round-trip：毛 PnL +$120, -$40, +$85；手續費共 $4.5。
        s.apply_restored_counters(4.5, 120.0 - 40.0 + 85.0, 3);
        assert!((s.total_fees() - 4.5).abs() < 1e-9);
        assert!((s.total_realized_pnl() - 165.0).abs() < 1e-9);
        assert_eq!(s.trade_count(), 3);
        // balance = 10000 + 165 - 4.5 = 10160.5
        assert!((s.balance() - 10_160.5).abs() < 1e-6);
        // peak_balance must climb to match (not stay at 10_000 initial).
        // peak_balance 必須跟著抬升。
        assert!((s.peak_balance - 10_160.5).abs() < 1e-6);
    }

    /// Open-only fills: realized_pnl sum = 0 (opens write 0), trade_count = 0,
    /// but fees still accumulate on every fill.
    /// 全為 open fill：SUM(realized_pnl)=0、trade_count=0，手續費仍累計。
    #[test]
    fn test_restore_counters_open_only_fills_zero_trade_count() {
        let mut s = PaperState::new(10_000.0);
        // 5 opens × $1 fee each, no closes yet.
        // 5 筆開倉 × $1 手續費，尚未平倉。
        s.apply_restored_counters(5.0, 0.0, 0);
        assert!((s.total_fees() - 5.0).abs() < 1e-9);
        assert!((s.total_realized_pnl() - 0.0).abs() < 1e-12);
        assert_eq!(s.trade_count(), 0);
        // balance = 10_000 - 5.0
        assert!((s.balance() - 9_995.0).abs() < 1e-9);
    }

    /// Net-negative realized PnL (losing streak) must drive balance below initial
    /// but peak_balance stays at initial since restored balance < initial.
    /// 累計虧損時餘額低於初始；peak_balance 保持初始值（不會被拉低）。
    #[test]
    fn test_restore_counters_net_negative_keeps_peak_at_initial() {
        let mut s = PaperState::new(10_000.0);
        s.apply_restored_counters(20.0, -500.0, 10);
        assert!((s.total_fees() - 20.0).abs() < 1e-9);
        assert!((s.total_realized_pnl() + 500.0).abs() < 1e-9);
        assert_eq!(s.trade_count(), 10);
        assert!((s.balance() - 9_480.0).abs() < 1e-6);
        // peak stays at initial 10_000 (restored balance 9_480 < 10_000).
        // peak 保留初始 10_000（還原後餘額 9_480 < 10_000）。
        assert!((s.peak_balance - 10_000.0).abs() < 1e-9);
    }

    /// Non-finite aggregate values must be rejected — state stays unchanged.
    /// 非有限聚合值應被拒絕，狀態保持不變。
    #[test]
    fn test_restore_counters_non_finite_rejected() {
        let mut s = PaperState::new(10_000.0);
        // Pre-load some baseline then try to clobber with NaN — should stay baseline.
        // 先載入基線，再嘗試以 NaN 覆蓋 — 應保持基線。
        s.apply_restored_counters(3.0, 50.0, 2);
        let baseline_balance = s.balance();
        s.apply_restored_counters(f64::NAN, 10.0, 5);
        assert!((s.balance() - baseline_balance).abs() < 1e-12);
        assert_eq!(s.trade_count(), 2);
        s.apply_restored_counters(1.0, f64::INFINITY, 5);
        assert!((s.balance() - baseline_balance).abs() < 1e-12);
        assert_eq!(s.trade_count(), 2);
    }

    /// Negative trade_count (malformed row) clamps to 0.
    /// 負 trade_count 夾到 0（防護異常回傳）。
    #[test]
    fn test_restore_counters_negative_trade_count_clamps_to_zero() {
        let mut s = PaperState::new(10_000.0);
        s.apply_restored_counters(1.0, 0.0, -42);
        assert_eq!(s.trade_count(), 0);
    }

    /// Restoring twice replaces (does not accumulate) so multiple calls are idempotent
    /// given the same aggregate input.
    /// 重複呼叫應覆蓋而非累加，保證冪等。
    #[test]
    fn test_restore_counters_idempotent_same_input() {
        let mut s = PaperState::new(10_000.0);
        s.apply_restored_counters(4.5, 165.0, 3);
        let first_balance = s.balance();
        let first_trade_count = s.trade_count();
        s.apply_restored_counters(4.5, 165.0, 3);
        assert!((s.balance() - first_balance).abs() < 1e-12);
        assert_eq!(s.trade_count(), first_trade_count);
    }

    /// Documents the three-engine isolation expectation: `restore_from_db` filters
    /// on `engine_mode`, so calling it with "paper" must never pull in demo/live
    /// rows. Pure-helper test covers the apply-side; the SQL WHERE clause is
    /// asserted by reviewers since sqlx needs a live Postgres for a full round-trip.
    /// 三引擎隔離：`restore_from_db` 以 `engine_mode` 過濾，呼叫 "paper" 絕不會
    /// 帶回 demo/live 行。純函數測試驗證 apply 端；SQL WHERE 子句由 reviewer 驗證
    /// （完整 round-trip 需要真實 Postgres）。
    #[test]
    fn test_restore_counters_three_engines_independent_values() {
        // Each engine has its own PaperState + its own per-engine aggregate row.
        // 每條引擎擁有獨立 PaperState 與對應聚合行。
        let mut paper = PaperState::new(10_000.0);
        let mut demo = PaperState::new(25_000.0);
        let mut live = PaperState::new(5_000.0);

        paper.apply_restored_counters(10.0, 300.0, 12);
        demo.apply_restored_counters(2.0, -50.0, 4);
        live.apply_restored_counters(0.0, 0.0, 0);

        assert_eq!(paper.trade_count(), 12);
        assert_eq!(demo.trade_count(), 4);
        assert_eq!(live.trade_count(), 0);
        assert!((paper.total_realized_pnl() - 300.0).abs() < 1e-9);
        assert!((demo.total_realized_pnl() + 50.0).abs() < 1e-9);
        assert!((live.total_realized_pnl() - 0.0).abs() < 1e-12);
        // No cross-talk between engines — each carries its own initial balance forward.
        // 引擎間無串擾，各自攜帶自己的初始餘額。
        assert!((paper.balance() - (10_000.0 + 300.0 - 10.0)).abs() < 1e-6);
        assert!((demo.balance() - (25_000.0 - 50.0 - 2.0)).abs() < 1e-6);
        assert!((live.balance() - 5_000.0).abs() < 1e-9);
    }

    #[test]
    fn test_upsert_position_from_exchange_handles_size_zero() {
        // size==0 → remove (Bybit just reported a flat position).
        // size > 0 → upsert (preserve best_price if direction unchanged).
        // size==0 → 移除（交易所剛回報該倉已平）。
        // size > 0 → upsert（同向時保留 best_price）。
        let mut s = PaperState::new(10000.0);

        // 1. Insert via upsert (no prior position).
        assert!(s.upsert_position_from_exchange("BTCUSDT", true, 0.5, 50_000.0, 100));
        assert_eq!(s.position_count(), 1);

        // 2. Mutate best_price via market move + update_best_prices.
        s.set_latest_price("BTCUSDT", 51_000.0);
        s.update_best_prices();
        let best_after_move = s.get_position("BTCUSDT").unwrap().best_price;
        assert!((best_after_move - 51_000.0).abs() < 1e-9);

        // 3. Same-direction upsert with new avg_price → best_price preserved.
        assert!(s.upsert_position_from_exchange("BTCUSDT", true, 1.0, 50_500.0, 200));
        let pos = s.get_position("BTCUSDT").unwrap();
        assert!((pos.qty - 1.0).abs() < 1e-12);
        assert!((pos.entry_price - 50_500.0).abs() < 1e-9);
        assert!((pos.best_price - 51_000.0).abs() < 1e-9); // preserved

        // 4. Size==0 removes the entry.
        assert!(s.upsert_position_from_exchange("BTCUSDT", true, 0.0, 50_000.0, 300));
        assert_eq!(s.position_count(), 0);

        // 5. Size==0 on non-existent symbol → no-op false.
        assert!(!s.upsert_position_from_exchange("NOPE", true, 0.0, 0.0, 0));

        // 6. Direction flip resets best_price.
        s.upsert_position_from_exchange("ETHUSDT", true, 1.0, 3_000.0, 100);
        s.set_latest_price("ETHUSDT", 3_100.0);
        s.update_best_prices();
        s.upsert_position_from_exchange("ETHUSDT", false, 1.0, 3_050.0, 200);
        let eth = s.get_position("ETHUSDT").unwrap();
        assert!(!eth.is_long);
        assert!((eth.best_price - 3_050.0).abs() < 1e-9); // reset on flip
    }

    // ─── EDGE-P3-1 entry_context_id threading regressions ───────────────────
    // EDGE-P3-1 entry_context_id 串接回歸測試

    #[test]
    fn test_entry_context_id_default_empty_on_open() {
        // Fresh apply_fill opens position with empty entry_context_id until setter stamps it.
        // 新開倉 entry_context_id 預設為空，直到 setter 標記。
        let mut s = PaperState::new(10_000.0);
        s.apply_fill("BTC", true, 0.1, 50_000.0, 1.0, 0, "test");
        assert_eq!(s.get_entry_context_id("BTC"), None);
    }

    #[test]
    fn test_set_entry_context_id_on_fresh_open() {
        // Setter stamps the id and getter reads it back.
        // setter 寫入後 getter 能讀回。
        let mut s = PaperState::new(10_000.0);
        s.apply_fill("BTC", true, 0.1, 50_000.0, 1.0, 0, "test");
        s.set_entry_context_id("BTC", "ctx-abc-123");
        assert_eq!(s.get_entry_context_id("BTC"), Some("ctx-abc-123"));
    }

    #[test]
    fn test_set_entry_context_id_ignores_empty() {
        // Empty strings are no-ops so accumulate fills can't wipe a stamped id.
        // 空字串 setter 視為 no-op，累倉路徑不會擦掉既有 id。
        let mut s = PaperState::new(10_000.0);
        s.apply_fill("BTC", true, 0.1, 50_000.0, 1.0, 0, "test");
        s.set_entry_context_id("BTC", "ctx-orig");
        s.set_entry_context_id("BTC", "");
        assert_eq!(s.get_entry_context_id("BTC"), Some("ctx-orig"));
    }

    #[test]
    fn test_entry_context_id_survives_accumulate() {
        // Same-direction top-up must NOT reset entry_context_id — downstream labels hinge on first open.
        // 同方向加倉不得重設 entry_context_id — 下游標籤以首次開倉為錨。
        let mut s = PaperState::new(10_000.0);
        s.apply_fill("BTC", true, 0.1, 50_000.0, 1.0, 0, "test");
        s.set_entry_context_id("BTC", "ctx-first-open");
        s.apply_fill("BTC", true, 0.1, 52_000.0, 1.0, 1000, "test");
        assert_eq!(s.get_entry_context_id("BTC"), Some("ctx-first-open"));
    }

    #[test]
    fn test_entry_context_id_cleared_after_close() {
        // close_position removes the entry → getter returns None.
        // close_position 移除條目 → getter 回傳 None。
        let mut s = PaperState::new(10_000.0);
        s.apply_fill("BTC", true, 0.1, 50_000.0, 1.0, 0, "test");
        s.set_entry_context_id("BTC", "ctx-before-close");
        assert_eq!(s.get_entry_context_id("BTC"), Some("ctx-before-close"));
        s.close_position("BTC", 51_000.0, 1000);
        assert_eq!(s.get_entry_context_id("BTC"), None);
    }

    #[test]
    fn test_entry_context_id_partial_close_preserves_id() {
        // Partial close (opposite qty < position qty) retains the stamped id on the surviving leg.
        // 部分平倉（反向 qty < 持倉 qty）保留倖存腿上的 id。
        let mut s = PaperState::new(10_000.0);
        s.apply_fill("BTC", true, 0.2, 50_000.0, 2.0, 0, "test");
        s.set_entry_context_id("BTC", "ctx-original");
        s.apply_fill("BTC", false, 0.1, 51_000.0, 1.0, 1000, "test"); // half close
        assert!(s.get_position("BTC").is_some());
        assert_eq!(s.get_entry_context_id("BTC"), Some("ctx-original"));
    }

    #[test]
    fn test_pre_v017_snapshot_deserializes_with_empty_entry_context_id() {
        // Backward compat: snapshots written before V017 migration have no
        // entry_context_id field. `#[serde(default)]` must fill it with "".
        // 向後相容：V017 前寫入的快照沒有 entry_context_id 欄位，`#[serde(default)]`
        // 應填為空字串。
        let legacy_json = r#"{
            "symbol": "BTC",
            "is_long": true,
            "qty": 0.1,
            "entry_price": 50000.0,
            "best_price": 50000.0,
            "entry_fee": 1.0,
            "entry_ts_ms": 0,
            "unrealized_pnl": 0.0
        }"#;
        let pos: PaperPosition = serde_json::from_str(legacy_json)
            .expect("legacy snapshot must deserialize with serde(default)");
        assert_eq!(pos.entry_context_id, "");
        assert_eq!(pos.symbol, "BTC");
        assert!(pos.is_long);
    }

    #[test]
    fn test_setter_on_missing_symbol_is_noop() {
        // Setter on a symbol with no position is a silent no-op (fail-soft).
        // 對無持倉的 symbol 呼叫 setter 為靜默 no-op（fail-soft）。
        let mut s = PaperState::new(10_000.0);
        s.set_entry_context_id("NOPE", "ctx-ghost");
        assert_eq!(s.get_entry_context_id("NOPE"), None);
        assert_eq!(s.position_count(), 0);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // P0-6 triage_bybit_sync tests / P0-6 分流測試
    // ═══════════════════════════════════════════════════════════════════════

    fn seed_bybit_sync(s: &mut PaperState, positions: &[(&str, bool, f64, f64)]) {
        let tuples: Vec<(String, bool, f64, f64, u64)> = positions
            .iter()
            .map(|(sym, long, qty, px)| (sym.to_string(), *long, *qty, *px, 1000))
            .collect();
        s.import_positions(tuples);
    }

    #[test]
    fn triage_adopts_in_universe_positions() {
        let mut s = PaperState::new(10_000.0);
        seed_bybit_sync(&mut s, &[
            ("BTCUSDT", true, 0.01, 50000.0),
            ("ETHUSDT", false, 0.5, 3000.0),
        ]);
        assert_eq!(s.position_count(), 2);

        let active = vec!["BTCUSDT".into(), "ETHUSDT".into(), "SOLUSDT".into()];
        let strategies = &["ma_crossover", "bb_reversion"];
        let result = s.triage_bybit_sync(&active, strategies, |_, _| None);

        assert_eq!(result.adopted.len(), 2);
        assert_eq!(result.evicted.len(), 0);
        assert_eq!(s.position_count(), 2);

        let btc = s.get_position("BTCUSDT").unwrap();
        assert_eq!(btc.owner_strategy, "ma_crossover");
        let eth = s.get_position("ETHUSDT").unwrap();
        assert_eq!(eth.owner_strategy, "ma_crossover");
    }

    #[test]
    fn triage_evicts_not_in_universe_positions() {
        let mut s = PaperState::new(10_000.0);
        seed_bybit_sync(&mut s, &[
            ("BTCUSDT", true, 0.01, 50000.0),
            ("SHIBUSDT", true, 1000000.0, 0.00001),
        ]);
        assert_eq!(s.position_count(), 2);

        let active = vec!["BTCUSDT".into()];
        let strategies = &["ma_crossover"];
        let result = s.triage_bybit_sync(&active, strategies, |_, _| None);

        assert_eq!(result.adopted.len(), 1);
        assert_eq!(result.evicted.len(), 1);
        assert_eq!(s.position_count(), 1);

        assert_eq!(result.evicted[0].0, "SHIBUSDT");
        assert!(result.evicted[0].1); // is_long
        assert!((result.evicted[0].2 - 1000000.0).abs() < 0.1);
    }

    #[test]
    fn triage_no_strategies_evicts_all() {
        let mut s = PaperState::new(10_000.0);
        seed_bybit_sync(&mut s, &[("BTCUSDT", true, 0.01, 50000.0)]);

        let active = vec!["BTCUSDT".into()];
        let empty: &[&str] = &[];
        let result = s.triage_bybit_sync(&active, empty, |_, _| None);

        assert_eq!(result.adopted.len(), 0);
        assert_eq!(result.evicted.len(), 1);
        assert_eq!(s.position_count(), 0);
    }

    #[test]
    fn triage_skips_non_bybit_sync_positions() {
        let mut s = PaperState::new(10_000.0);
        s.apply_fill("BTCUSDT", true, 0.01, 50000.0, 0.0, 0, "ma_crossover");

        let active = vec!["BTCUSDT".into()];
        let strategies = &["ma_crossover"];
        let result = s.triage_bybit_sync(&active, strategies, |_, _| None);

        assert_eq!(result.adopted.len(), 0);
        assert_eq!(result.evicted.len(), 0);
        assert_eq!(s.position_count(), 1);
    }

    #[test]
    fn triage_empty_positions_is_noop() {
        let mut s = PaperState::new(10_000.0);
        let active = vec!["BTCUSDT".into()];
        let strategies = &["ma_crossover"];
        let result = s.triage_bybit_sync(&active, strategies, |_, _| None);

        assert_eq!(result.adopted.len(), 0);
        assert_eq!(result.evicted.len(), 0);
    }

    #[test]
    fn triage_evicted_removed_from_mirror() {
        let mut s = PaperState::new(10_000.0);
        seed_bybit_sync(&mut s, &[("SHIBUSDT", true, 100.0, 0.001)]);
        assert!(s.positions_mirror.read().contains_key("SHIBUSDT"));

        let active: Vec<String> = vec![];
        let strategies = &["ma_crossover"];
        let _ = s.triage_bybit_sync(&active, strategies, |_, _| None);

        assert!(!s.positions_mirror.read().contains_key("SHIBUSDT"));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // DUST-EVICTION-GAP-1 / P1-8 tests (2026-04-17)
    // DUST-EVICTION-GAP-1 / P1-8 測試：evict 候選但名義值低於 min_notional 時凍結
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn triage_dust_candidate_is_frozen_not_evicted() {
        // PNUTUSDT 3.0 × $0.06644 = $0.199 < min_notional=$5 → freeze, NO evict.
        // 覆蓋 P0-6 18:55:57Z 現場的 bug：dust 倉位被 engine 清掉但交易所仍持有。
        let mut s = PaperState::new(10_000.0);
        seed_bybit_sync(&mut s, &[("PNUTUSDT", true, 3.0, 0.06644)]);

        let active: Vec<String> = vec![]; // not in universe → eviction candidate
        let strategies = &["ma_crossover"];
        let result = s.triage_bybit_sync(&active, strategies, |sym, qty| {
            if sym == "PNUTUSDT" {
                Some((qty * 0.06644, 5.0))
            } else {
                None
            }
        });

        assert_eq!(result.adopted.len(), 0);
        assert_eq!(result.evicted.len(), 0);
        assert_eq!(result.dust_frozen.len(), 1);

        // Position retained, owner_strategy flipped to orphan_frozen.
        // 倉位保留，owner_strategy 改為 orphan_frozen。
        assert_eq!(s.position_count(), 1);
        let pos = s.get_position("PNUTUSDT").expect("dust position retained");
        assert_eq!(pos.owner_strategy, "orphan_frozen");
        // Mirror still has the symbol — engine/exchange stay in sync.
        // Mirror 仍包含 symbol — engine/exchange 保持同步。
        assert!(s.positions_mirror.read().contains_key("PNUTUSDT"));

        let (sym, is_long, qty, est, minn) = &result.dust_frozen[0];
        assert_eq!(sym, "PNUTUSDT");
        assert!(*is_long);
        assert!((*qty - 3.0).abs() < 1e-9);
        assert!((*est - 0.19932).abs() < 1e-4);
        assert!((*minn - 5.0).abs() < 1e-9);
    }

    #[test]
    fn triage_normal_evict_when_notional_above_min() {
        // SHIBUSDT 100 × $0.001 = $0.1 BUT dust_check returns ($20, $5) → evict path.
        // Even though real SHIB qty=100 × $0.001 looks tiny, if caller reports
        // est_notional ≥ min_notional, we MUST evict normally (close will succeed).
        // 若 caller 回報 est_notional ≥ min_notional 則走正常驅逐，不凍結。
        let mut s = PaperState::new(10_000.0);
        seed_bybit_sync(&mut s, &[("SHIBUSDT", true, 100.0, 0.001)]);

        let active: Vec<String> = vec![];
        let strategies = &["ma_crossover"];
        let result = s.triage_bybit_sync(&active, strategies, |_, _| Some((20.0, 5.0)));

        assert_eq!(result.evicted.len(), 1);
        assert_eq!(result.dust_frozen.len(), 0);
        assert_eq!(s.position_count(), 0);
    }

    #[test]
    fn triage_evict_when_dust_check_returns_none() {
        // dust_check=None (no instrument spec / no ref price) → evict as before.
        // Preserves legacy behaviour when instrument_cache is empty (tests / headless).
        // dust_check=None 時沿用舊行為正常驅逐（instrument_cache 空時相容路徑）。
        let mut s = PaperState::new(10_000.0);
        seed_bybit_sync(&mut s, &[("XXXUSDT", false, 0.5, 100.0)]);

        let active: Vec<String> = vec![];
        let strategies = &["ma_crossover"];
        let result = s.triage_bybit_sync(&active, strategies, |_, _| None);

        assert_eq!(result.evicted.len(), 1);
        assert_eq!(result.dust_frozen.len(), 0);
        assert_eq!(s.position_count(), 0);
    }

    #[test]
    fn triage_equal_to_min_notional_evicts_not_freezes() {
        // est_notional == min_notional is NOT dust (dispatch uses `<` strict).
        // Keep the boundary identical to event_consumer/dispatch.rs:76 `est_notional < min_notional`.
        // 邊界與 dispatch.rs 嚴格小於對齊，等值時正常驅逐。
        let mut s = PaperState::new(10_000.0);
        seed_bybit_sync(&mut s, &[("EDGEUSDT", true, 1.0, 5.0)]);

        let active: Vec<String> = vec![];
        let strategies = &["ma_crossover"];
        let result = s.triage_bybit_sync(&active, strategies, |_, qty| {
            Some((qty * 5.0, 5.0))
        });

        assert_eq!(result.evicted.len(), 1);
        assert_eq!(result.dust_frozen.len(), 0);
        assert_eq!(s.position_count(), 0);
    }

    #[test]
    fn triage_mixed_adopt_evict_dust_in_one_pass() {
        // 綜合場景：三個 bybit_sync 倉位，一個 adopt、一個正常 evict、一個 dust freeze。
        let mut s = PaperState::new(10_000.0);
        seed_bybit_sync(&mut s, &[
            ("BTCUSDT", true, 0.01, 50000.0),       // in universe → adopt
            ("SHIBUSDT", true, 100.0, 0.001),        // not in universe, normal evict
            ("PNUTUSDT", false, 3.0, 0.06644),       // not in universe, dust freeze
        ]);

        let active: Vec<String> = vec!["BTCUSDT".into()];
        let strategies = &["ma_crossover"];
        let result = s.triage_bybit_sync(&active, strategies, |sym, qty| {
            match sym {
                "SHIBUSDT" => Some((qty * 0.001 * 1000.0, 5.0)), // 100.0 > 5.0 → evict
                "PNUTUSDT" => Some((qty * 0.06644, 5.0)),        // 0.199 < 5.0 → freeze
                _ => None,
            }
        });

        assert_eq!(result.adopted.len(), 1);
        assert_eq!(result.evicted.len(), 1);
        assert_eq!(result.dust_frozen.len(), 1);
        assert_eq!(s.position_count(), 2); // BTC adopted + PNUT frozen
        assert_eq!(s.get_position("BTCUSDT").unwrap().owner_strategy, "ma_crossover");
        assert_eq!(s.get_position("PNUTUSDT").unwrap().owner_strategy, "orphan_frozen");
        assert!(s.get_position("SHIBUSDT").is_none());
    }

    // ═══════════════════════════════════════════════════════════════════════
    // DUST-EVICTION-GAP-1 / P1-8 FUP retriage_synthetic_owner tests (2026-04-17)
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn retriage_noop_for_real_strategy_owner() {
        // Real strategy label → always NoOp; strategy manages its own lifecycle.
        // 實策略標籤 → 恆 NoOp；策略自行管理生命週期。
        let mut s = PaperState::new(10_000.0);
        s.apply_fill("BTCUSDT", true, 0.01, 50000.0, 0.0, 0, "ma_crossover");

        let outcome = s.retriage_synthetic_owner(
            "BTCUSDT",
            10.0, // deliberate dust-level price — should NOT demote real strategy
            true,
            "ma_crossover",
            Some(5.0),
        );
        assert_eq!(outcome, RetriageOutcome::NoOp);
        assert_eq!(s.get_position("BTCUSDT").unwrap().owner_strategy, "ma_crossover");
    }

    #[test]
    fn retriage_noop_when_symbol_has_no_position() {
        let mut s = PaperState::new(10_000.0);
        let outcome = s.retriage_synthetic_owner("NONEUSDT", 1.0, true, "ma_crossover", Some(5.0));
        assert_eq!(outcome, RetriageOutcome::NoOp);
    }

    #[test]
    fn retriage_dust_freezes_bybit_sync_position() {
        // bybit_sync + in universe + notional < min → label flipped to orphan_frozen,
        // was_downgraded=true, no promotion, no eviction.
        // bybit_sync + notional 低於 min → 降級為 orphan_frozen。
        let mut s = PaperState::new(10_000.0);
        seed_bybit_sync(&mut s, &[("PNUTUSDT", true, 3.0, 0.06644)]);

        let outcome = s.retriage_synthetic_owner(
            "PNUTUSDT", 0.06644, true, "ma_crossover", Some(5.0),
        );
        match outcome {
            RetriageOutcome::FrozenAsDust { was_downgraded, min_notional, .. } => {
                assert!(was_downgraded);
                assert!((min_notional - 5.0).abs() < 1e-9);
            }
            other => panic!("expected FrozenAsDust, got {:?}", other),
        }
        assert_eq!(s.get_position("PNUTUSDT").unwrap().owner_strategy, "orphan_frozen");
    }

    #[test]
    fn retriage_dust_stays_frozen_is_idempotent() {
        // orphan_frozen still dust → was_downgraded=false (no state change, no log).
        // orphan_frozen 仍是 dust → was_downgraded=false（無狀態變化、無日誌）。
        let mut s = PaperState::new(10_000.0);
        seed_bybit_sync(&mut s, &[("PNUTUSDT", true, 3.0, 0.06644)]);
        // Drop into dust first.
        let _ = s.retriage_synthetic_owner("PNUTUSDT", 0.06644, true, "ma_crossover", Some(5.0));
        assert_eq!(s.get_position("PNUTUSDT").unwrap().owner_strategy, "orphan_frozen");

        // Second call — already frozen, should be idempotent no-op log-wise.
        // 第二次呼叫 — 已凍結，應為 idempotent、不重複發日誌。
        let outcome = s.retriage_synthetic_owner("PNUTUSDT", 0.06644, true, "ma_crossover", Some(5.0));
        match outcome {
            RetriageOutcome::FrozenAsDust { was_downgraded, .. } => {
                assert!(!was_downgraded);
            }
            other => panic!("expected idempotent FrozenAsDust, got {:?}", other),
        }
    }

    #[test]
    fn retriage_promotes_orphan_frozen_when_price_recovers() {
        // orphan_frozen + price rises so notional ≥ min + in universe → Promoted.
        // 核心修復：Live session 不需重啟即自動接管。
        let mut s = PaperState::new(10_000.0);
        // Seed as bybit_sync then manually demote to orphan_frozen (simulate startup triage output).
        seed_bybit_sync(&mut s, &[("PNUTUSDT", true, 100.0, 0.06644)]);
        let _ = s.retriage_synthetic_owner("PNUTUSDT", 0.04, true, "ma_crossover", Some(5.0));
        assert_eq!(s.get_position("PNUTUSDT").unwrap().owner_strategy, "orphan_frozen");

        // Price recovers — 100 × 0.08 = 8 > 5 min. In universe → promote.
        // 價格回升 → 8 > 5 → 升級。
        let outcome = s.retriage_synthetic_owner("PNUTUSDT", 0.08, true, "ma_crossover", Some(5.0));
        match outcome {
            RetriageOutcome::Promoted { from, to, est_notional } => {
                assert_eq!(from, "orphan_frozen");
                assert_eq!(to, "ma_crossover");
                assert!((est_notional - 8.0).abs() < 1e-9);
            }
            other => panic!("expected Promoted, got {:?}", other),
        }
        assert_eq!(s.get_position("PNUTUSDT").unwrap().owner_strategy, "ma_crossover");
    }

    #[test]
    fn retriage_promotes_bybit_sync_directly_when_in_universe() {
        // Simulates the case where startup triage never ran (race / registry not ready yet)
        // and a bybit_sync-labelled position persists. Tick arrives with in_universe=true
        // and notional OK → immediate promotion without going through orphan_frozen first.
        // 模擬啟動 triage 未跑的情況；tick 到達即升級，不必先凍結。
        let mut s = PaperState::new(10_000.0);
        seed_bybit_sync(&mut s, &[("ETHUSDT", false, 0.5, 3000.0)]);

        let outcome = s.retriage_synthetic_owner("ETHUSDT", 3000.0, true, "ma_crossover", Some(5.0));
        match outcome {
            RetriageOutcome::Promoted { from, to, .. } => {
                assert_eq!(from, "bybit_sync");
                assert_eq!(to, "ma_crossover");
            }
            other => panic!("expected Promoted, got {:?}", other),
        }
    }

    #[test]
    fn retriage_promotes_orphan_adopted_when_in_universe() {
        // orphan_adopted (Phase 2A fallback when no strategy had positive edge) should
        // also auto-upgrade when conditions allow, not stay stuck forever.
        // orphan_adopted 也應在條件滿足時自動升級。
        let mut s = PaperState::new(10_000.0);
        assert!(s.adopt_orphan("BTCUSDT", true, 0.01, 50000.0, 1000, None));
        assert_eq!(s.get_position("BTCUSDT").unwrap().owner_strategy, "orphan_adopted");

        let outcome = s.retriage_synthetic_owner("BTCUSDT", 50000.0, true, "ma_crossover", Some(5.0));
        match outcome {
            RetriageOutcome::Promoted { from, to, .. } => {
                assert_eq!(from, "orphan_adopted");
                assert_eq!(to, "ma_crossover");
            }
            other => panic!("expected Promoted, got {:?}", other),
        }
    }

    #[test]
    fn retriage_needs_eviction_when_not_in_universe_and_notional_ok() {
        // synthetic + NOT in universe + notional OK → NeedsEviction (caller dispatches).
        // Label is NOT changed — keeps state deterministic until close settles.
        // synthetic + 不在 universe + 名義值足夠 → NeedsEviction（呼叫方派平倉）。
        let mut s = PaperState::new(10_000.0);
        seed_bybit_sync(&mut s, &[("OLDUSDT", true, 5.0, 10.0)]);

        let outcome = s.retriage_synthetic_owner("OLDUSDT", 10.0, false, "ma_crossover", Some(5.0));
        match outcome {
            RetriageOutcome::NeedsEviction { is_long, qty, est_notional } => {
                assert!(is_long);
                assert!((qty - 5.0).abs() < 1e-9);
                assert!((est_notional - 50.0).abs() < 1e-9);
            }
            other => panic!("expected NeedsEviction, got {:?}", other),
        }
        // Position kept as-is until caller dispatches close + exchange settles.
        // 呼叫方派 close + 交易所結算前，倉位保留現狀。
        assert_eq!(s.get_position("OLDUSDT").unwrap().owner_strategy, "bybit_sync");
    }

    #[test]
    fn retriage_zero_or_invalid_price_is_noop() {
        // Guard against startup/race window ticks with price=0 or NaN.
        // 防範啟動競態窗口的 price=0 / NaN tick。
        let mut s = PaperState::new(10_000.0);
        seed_bybit_sync(&mut s, &[("BTCUSDT", true, 0.01, 50000.0)]);

        assert_eq!(
            s.retriage_synthetic_owner("BTCUSDT", 0.0, true, "ma_crossover", Some(5.0)),
            RetriageOutcome::NoOp
        );
        assert_eq!(
            s.retriage_synthetic_owner("BTCUSDT", f64::NAN, true, "ma_crossover", Some(5.0)),
            RetriageOutcome::NoOp
        );
        assert_eq!(
            s.retriage_synthetic_owner("BTCUSDT", -1.0, true, "ma_crossover", Some(5.0)),
            RetriageOutcome::NoOp
        );
        assert_eq!(s.get_position("BTCUSDT").unwrap().owner_strategy, "bybit_sync");
    }

    #[test]
    fn retriage_no_min_notional_skips_dust_gate() {
        // min_notional=None (instrument cache empty / test harness) → dust gate skipped;
        // promotion/eviction branch still applies.
        // min_notional=None → 跳 dust 門；升級/驅逐仍生效。
        let mut s = PaperState::new(10_000.0);
        seed_bybit_sync(&mut s, &[("PNUTUSDT", true, 3.0, 0.06644)]);

        let outcome = s.retriage_synthetic_owner("PNUTUSDT", 0.06644, true, "ma_crossover", None);
        match outcome {
            RetriageOutcome::Promoted { from, to, .. } => {
                assert_eq!(from, "bybit_sync");
                assert_eq!(to, "ma_crossover");
            }
            other => panic!("expected Promoted (no dust gate), got {:?}", other),
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // P0-6 adopt_orphan owner_strategy tests / P0-6 adopt_orphan 歸屬測試
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn adopt_orphan_default_owner() {
        let mut s = PaperState::new(10_000.0);
        let inserted = s.adopt_orphan("BTCUSDT", true, 0.01, 50000.0, 1000, None);
        assert!(inserted);
        let pos = s.get_position("BTCUSDT").unwrap();
        assert_eq!(pos.owner_strategy, "orphan_adopted");
    }

    #[test]
    fn adopt_orphan_custom_owner() {
        let mut s = PaperState::new(10_000.0);
        let inserted =
            s.adopt_orphan("BTCUSDT", true, 0.01, 50000.0, 1000, Some("ma_crossover"));
        assert!(inserted);
        let pos = s.get_position("BTCUSDT").unwrap();
        assert_eq!(pos.owner_strategy, "ma_crossover");
    }

    #[test]
    fn adopt_orphan_idempotent_same_direction() {
        let mut s = PaperState::new(10_000.0);
        assert!(s.adopt_orphan("BTCUSDT", true, 0.01, 50000.0, 1000, None));
        assert!(!s.adopt_orphan("BTCUSDT", true, 0.02, 51000.0, 2000, Some("bb_reversion")));
        let pos = s.get_position("BTCUSDT").unwrap();
        assert_eq!(pos.owner_strategy, "orphan_adopted");
        assert!((pos.qty - 0.01).abs() < 1e-10);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // MICRO-PROFIT-FIX-1: PaperPosition.entry_notional semantics
    // MICRO-PROFIT-FIX-1：PaperPosition.entry_notional 語義測試
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_entry_notional_set_on_open() {
        // 開新倉時 entry_notional = qty × fill_price。
        let mut s = PaperState::new(10_000.0);
        s.apply_fill("BTC", true, 0.1, 50_000.0, 1.0, 0, "test");
        let pos = s.get_position("BTC").unwrap();
        assert!(
            (pos.entry_notional - 5_000.0).abs() < 1e-6,
            "entry_notional should be 0.1 * 50000 = 5000, got {}",
            pos.entry_notional
        );
    }

    #[test]
    fn test_entry_notional_accumulates_on_same_direction_fill() {
        // 同向加倉：entry_notional += fill_qty × fill_price（option 2 累加語義）。
        let mut s = PaperState::new(10_000.0);
        s.apply_fill("BTC", true, 0.1, 50_000.0, 1.0, 0, "test"); // +5000
        s.apply_fill("BTC", true, 0.1, 52_000.0, 1.0, 1000, "test"); // +5200
        let pos = s.get_position("BTC").unwrap();
        let expected = 0.1 * 50_000.0 + 0.1 * 52_000.0;
        assert!(
            (pos.entry_notional - expected).abs() < 1e-6,
            "entry_notional should accumulate to {}, got {}",
            expected,
            pos.entry_notional
        );
    }

    #[test]
    fn test_entry_notional_unchanged_on_reduce() {
        // reduce_position 不改 entry_notional，保留 halve 基準。
        let mut s = PaperState::new(10_000.0);
        s.apply_fill("BTC", true, 0.2, 50_000.0, 1.0, 0, "test"); // entry_notional = 10000
        s.set_latest_price("BTC", 51_000.0);
        let _ = s.reduce_position("BTC", 0.1, 51_000.0); // halve to 0.1
        let pos = s.get_position("BTC").unwrap();
        assert!(
            (pos.qty - 0.1).abs() < 1e-10,
            "qty should reduce to 0.1, got {}",
            pos.qty
        );
        assert!(
            (pos.entry_notional - 10_000.0).abs() < 1e-6,
            "entry_notional should stay at 10000 (peak baseline), got {}",
            pos.entry_notional
        );
    }

    #[test]
    fn test_entry_notional_migration_fills_zero_with_qty_times_price() {
        // 遷移：既存 positions 中 entry_notional == 0.0 會補成 qty × entry_price。
        // 用 import_positions 種倉，然後手動清零（模擬舊快照 serde default）。
        let mut s = PaperState::new(10_000.0);
        s.import_positions(vec![
            ("BTC".to_string(), true, 0.1, 50_000.0, 0),
            ("ETH".to_string(), false, 1.0, 3_000.0, 0),
        ]);
        // 假裝是從舊 snapshot 反序列化：手動把 entry_notional 清零。
        // Simulate legacy snapshot rehydration by zeroing entry_notional.
        for pos in s.positions.values_mut() {
            pos.entry_notional = 0.0;
        }
        let migrated = s.migrate_legacy_entry_notional();
        assert_eq!(migrated, 2);
        let btc = s.get_position("BTC").unwrap();
        let eth = s.get_position("ETH").unwrap();
        assert!((btc.entry_notional - 5_000.0).abs() < 1e-6);
        assert!((eth.entry_notional - 3_000.0).abs() < 1e-6);
        // 冪等：再跑一次 migrated == 0。
        assert_eq!(s.migrate_legacy_entry_notional(), 0);
    }
}
