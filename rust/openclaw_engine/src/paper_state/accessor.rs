//! Paper Trading accessors — pure getters + SEC-18 clamped setters.
//! 紙盤交易存取器 — 純讀取方法 + SEC-18 夾值的 setter。
//!
//! MODULE_NOTE (EN): Contains read-only accessors (balance, position count,
//!   drawdown, latest prices, API PnL, stop_config), SEC-18 risk-parameter
//!   setters that clamp malicious/buggy IPC values to safe bounds, plus the
//!   shared helpers that manipulate simple scalar fields (force_drawdown,
//!   charge_fee, set_entry_context_id/get_entry_context_id,
//!   set_positions_mirror/positions_mirror/proactive_mirror_insert,
//!   migrate_legacy_entry_notional). Split out of `paper_state.rs` in
//!   E5-P1-1 (2026-04-18) to isolate the read side from the heavier fill/close
//!   engine paths. Zero behaviour change — every function body copied byte-for-
//!   byte from the pre-split file; math preserved bit-exact (no reordering).
//! MODULE_NOTE (中): 包含純讀取存取器（balance、倉位計數、drawdown、最新價、API PnL、
//!   stop_config）、SEC-18 夾值 setter、以及操作簡單純量欄位的共享 helper
//!   （force_drawdown、charge_fee、entry_context_id getter/setter、
//!   positions_mirror 三件、migrate_legacy_entry_notional）。2026-04-18 E5-P1-1
//!   自 paper_state.rs 拆出，把讀取面與較重的 fill/close 引擎路徑隔離。零行為變更 —
//!   每個函式主體逐字複製自拆分前檔案，數學運算順序保留以維持 bit-exact。

use super::PaperState;
use openclaw_core::stop_manager::StopConfig;
use std::collections::HashMap;
use std::sync::Arc;

impl PaperState {
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
    pub fn stop_config(&self) -> &StopConfig {
        &self.stop_config
    }

    pub fn position_count(&self) -> usize {
        self.positions.len()
    }

    pub fn positions(&self) -> Vec<&super::containers::PaperPosition> {
        self.positions.values().collect()
    }

    /// Get a specific position by symbol (for duplicate check).
    /// 按交易對獲取特定持倉（用於重複檢查）。
    pub fn get_position(&self, symbol: &str) -> Option<&super::containers::PaperPosition> {
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

    /// EXIT-FEATURES-TABLE-1: capture a stable snapshot of the exit-relevant
    /// fields of a position **before** close / reduce mutations run. Returns
    /// `None` when no position exists for the symbol. The snapshot is value-
    /// typed (no lifetime on `self`) so the caller can hold it across a
    /// subsequent `&mut self` close call.
    /// EXIT-FEATURES-TABLE-1：在 close / reduce 之前捕獲倉位退場相關欄位的穩定
    /// 快照；無倉位時回 None。快照為純值型別（不綁 self 生命週期），可跨
    /// 後續 `&mut self` close 呼叫持有。
    pub fn position_exit_snapshot(
        &self,
        symbol: &str,
    ) -> Option<super::containers::PositionExitSnapshot> {
        self.positions
            .get(symbol)
            .map(super::containers::PositionExitSnapshot::from_position)
    }

    /// P1-5 A2: read current peak balance — driver for `drawdown_pct()`.
    /// Persisted to `trading.paper_state_checkpoint` every state writer cycle
    /// and restored on engine startup so drawdown continuity survives a crash
    /// or operator restart. Reset only by IPC `reset_drawdown_baseline`.
    /// P1-5 A2：讀取當前 peak_balance — drawdown_pct 計算來源。
    /// 每狀態寫入週期持久化到 trading.paper_state_checkpoint、重啟時還原。
    pub fn peak_balance(&self) -> f64 {
        self.peak_balance
    }

    /// P1-5 A2: read current session start timestamp (ms since Unix epoch).
    /// Initialised in `new()` via `openclaw_core::now_ms()`, overwritten by
    /// checkpoint restore, reset by `reset_drawdown_baseline()`.
    /// P1-5 A2：讀取當前 session 起始時刻；restore 時由 DB 還原，
    /// reset_drawdown_baseline 時更新為現在。
    pub fn session_start_ts_ms(&self) -> u64 {
        self.session_start_ts_ms
    }

    /// P1-5 A2: restore `peak_balance` + `session_start_ts_ms` from a
    /// previously-persisted checkpoint row. ONLY invoked by the boot-time
    /// restore path (`paper_state_restore::restore_paper_counters`) — NOT
    /// exposed over IPC. Letting an IPC caller clobber `peak_balance` at
    /// runtime would bypass the drawdown circuit-breaker that Root Principle
    /// #5 (生存>利潤) depends on. `peak` is clamped to `max(peak, balance)`
    /// so a corrupted row can't artificially *lower* the peak below the
    /// current live balance. A non-finite `peak` leaves state untouched.
    /// P1-5 A2：從 checkpoint 還原 peak_balance 與 session_start_ts_ms。
    /// 僅供啟動時 restore 路徑使用，不暴露給 IPC——否則會繞過 Drawdown
    /// 斷路器（違反根原則 #5）。peak 採 `max(stored, current)` 保留雙方
    /// 較高者：(a) checkpoint 儲存時 peak 高於 restore_from_db 計算出的
    /// restored_balance → 保留 checkpoint 值，避免重啟洗歷史 peak；
    /// (b) 崩潰後 fills 回放又推高 balance → 保留更高的 self.peak_balance。
    /// 非有限值或負值不會反向降低現值。
    pub(crate) fn restore_checkpoint(&mut self, peak: f64, session_start_ts_ms: u64) {
        if !peak.is_finite() {
            return;
        }
        // max(stored, current): honor whichever peak reflects the higher
        // historical equity. `apply_restored_counters` already ran before this
        // call and bumped `peak_balance` to at least `restored_balance`; a
        // negative / poisoned row is absorbed by the max (since the existing
        // peak is always ≥ 0 after `new()`).
        // 採 max(stored, current)：apply_restored_counters 已先抬升
        // peak_balance 至少到 restored_balance，負值/損毀 row 會被 max 吸收。
        self.peak_balance = peak.max(self.peak_balance);
        self.session_start_ts_ms = session_start_ts_ms;
    }

    /// P1-5 A2: operator-driven drawdown baseline reset.
    /// Sets `peak_balance = balance` (drawdown_pct → 0) and starts a fresh
    /// `session_start_ts_ms`. ONLY legitimate caller is the IPC handler for
    /// `reset_drawdown_baseline` — the Python FastAPI route behind it writes a
    /// `change_audit_log` entry per Root Principle #8. Callers MUST also
    /// DELETE the `trading.paper_state_checkpoint` row so the next engine
    /// restart doesn't resurrect the old peak. `forced_drawdown` is cleared
    /// too so a test-set override doesn't survive the reset.
    /// P1-5 A2：operator 手動重置 drawdown 基準點。僅供 IPC handler 呼叫；
    /// Python 路由會同時寫 change_audit_log（根原則 #8）。呼叫者必須同時
    /// 刪除 trading.paper_state_checkpoint 對應 row，避免下次重啟被舊 peak
    /// 復活。forced_drawdown 一併清除。
    pub fn reset_drawdown_baseline(&mut self) {
        self.peak_balance = self.balance;
        self.session_start_ts_ms = openclaw_core::now_ms();
        self.forced_drawdown = 0.0;
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

    /// EDGE-P2-3 Phase 1B-4.3: most recent funding rate for `symbol`, as a
    /// decimal fraction (0.0001 = 1 bps per 8h). Router stamps this onto
    /// `RestingLimitOrder.funding_rate_at_submit` at maker-order enqueue so
    /// the sweep's funding-drag guard (#3) can refuse touch-equal fills when
    /// funding is strongly adverse to the maker side. Returns `None` until
    /// the first `PriceEvent.funding_rate` lands for this symbol.
    /// EDGE-P2-3 Phase 1B-4.3：symbol 最新資金費率（decimal；0.0001 = 8h 1 bps）。
    /// Router 於 maker enqueue 時讀入 `RestingLimitOrder.funding_rate_at_submit`，
    /// sweep 的 funding drag guard (#3) 以此判斷是否拒絕「碰觸」成交。symbol
    /// 首筆 `PriceEvent.funding_rate` 到達前回 None。
    pub fn latest_funding_rate(&self, symbol: &str) -> Option<f64> {
        self.funding_rates.get(symbol).copied()
    }

    /// EDGE-P2-3 Phase 1B-4.3: setter called by `on_tick` on every
    /// `PriceEvent.funding_rate = Some(_)`. Unconditional overwrite — the
    /// latest rate is always the authoritative value for router stamping.
    /// EDGE-P2-3 Phase 1B-4.3：`on_tick` 在每次 `PriceEvent.funding_rate` 非
    /// None 時呼叫的 setter。無條件覆寫 —— 最新值即權威值。
    pub fn set_latest_funding_rate(&mut self, symbol: &str, rate: f64) {
        self.funding_rates.insert(symbol.to_string(), rate);
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
}
