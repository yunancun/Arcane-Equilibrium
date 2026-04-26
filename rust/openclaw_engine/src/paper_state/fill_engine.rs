//! Paper Trading fill engine — apply_fill / close / reduce + DB restore + stops.
//! 紙盤交易成交引擎 — apply_fill / close / reduce + DB 還原 + 止損檢查。
//!
//! MODULE_NOTE (EN): Owns the mutating hot path: `apply_fill` (open /
//!   accumulate / close incl. MICRO-PROFIT-FIX-1 entry_notional semantics),
//!   `close_position`, `close_position_at_market`, `close_all_positions`,
//!   `reduce_position` (FIX-03 fast_track ReduceToHalf), `import_positions`
//!   (B-1 Phase 2 startup seed), `upsert_position_from_exchange` (B-1 Phase 2
//!   WS upsert with direction-flip best_price reset), `apply_restored_counters`
//!   + `restore_from_db` (QoL-1 per-engine counter restore), plus
//!   `update_best_prices` / `check_stops` trailing-stop heads. Every arithmetic
//!   order is copied verbatim from the pre-split source — crucial for
//!   bit-exact f64 preservation of PnL, entry_notional accumulation, and
//!   weighted-average entry price. MICRO-PROFIT-FIX-1 semantics (option 2
//!   entry_notional accumulate, no decrement on reduce) preserved.
//! MODULE_NOTE (中): 放狀態變動熱路徑：apply_fill（開 / 同向加 / 平，含
//!   MICRO-PROFIT-FIX-1 entry_notional 累加語義）、close_position、
//!   close_position_at_market、close_all_positions、reduce_position
//!   （FIX-03 fast_track ReduceToHalf）、import_positions（B-1 Phase 2 啟動種倉）、
//!   upsert_position_from_exchange（B-1 Phase 2，方向翻轉時重設 best_price）、
//!   apply_restored_counters + restore_from_db（QoL-1 per-engine counter 還原）、
//!   以及 update_best_prices / check_stops 跟蹤止損頭。每段算術順序逐字照抄自拆分前
//!   原始碼 — 對 PnL、entry_notional 累加、加權平均入場價的 f64 bit-exact 保留至關
//!   重要。MICRO-PROFIT-FIX-1 語義（option 2 累加、reduce 不減）保留。

use super::containers::PaperPosition;
use super::PaperState;
use openclaw_core::stop_manager::{self, PositionState, StopTrigger};

impl PaperState {
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
    pub fn import_positions(&mut self, positions: Vec<(String, bool, f64, f64, u64)>) -> usize {
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
                    max_favorable_pnl_pct: 0.0,
                    peak_reached_ts_ms: ts_ms as i64,
                },
            );
            inserted += 1;
        }
        inserted
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
                        max_favorable_pnl_pct: 0.0,
                        peak_reached_ts_ms: ts_ms as i64,
                    },
                );
                true
            }
        }
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
    /// `apply_fill()` 等價，並更新 peak_balance。trade_count 飽和轉 u32,
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
                // EVICT-ON-DUST T2a (PA §1.2.1): opposite-direction partial
                // close may have left a sub-floor residue (funding tick
                // reducing 0.05 → 7e-13 was the STRKUSDT case). `fill_price`
                // is the freshest market price for this symbol (we just set
                // it via `set_latest_price` above), so use it as the notional
                // ref. Falls through to no-op when the position was already
                // removed by the `remaining <= 1e-12` branch above.
                // EVICT-ON-DUST T2a：反向部分平倉殘餘檢查；fill_price 即剛 set
                // 的最新價，作 notional 計算參考。完全平倉路徑 already-removed
                // → no-op。
                self.evict_if_dust(symbol, fill_price, "apply_fill_opposite_residue");
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
                // EVICT-ON-DUST T2b (PA §1.2.1): same-direction accumulate is
                // notional-additive (qty + qty * fill_price both grow), so a
                // sub-floor result is mathematically only possible when the
                // pre-existing position was already dust AND the added qty is
                // also dust-scale — extremely rare but covered for symmetry
                // with T2a. Idempotent on non-dust positions (no-op).
                // EVICT-ON-DUST T2b：同向加倉是名目相加（qty 增 + qty × price 增），
                // 結果落 floor 之下需「先 dust + 加上的 qty 也 dust」極罕見；為與
                // T2a 對稱保留檢查；非 dust 倉位等同 no-op。
                self.evict_if_dust(symbol, fill_price, "apply_fill_same_dir_accumulate");
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
                max_favorable_pnl_pct: 0.0,
                peak_reached_ts_ms: ts_ms as i64,
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
    ///
    /// EVICT-ON-DUST T1 (PA §1.2.1): post-mutation `evict_if_dust(symbol, price)`
    /// runs immediately after the reduce/close path settles balance/PnL. This
    /// catches the canonical STRKUSDT-class spiral failure mode — repeated
    /// halvings on an already-dust position that step_0's pre-spawn gate missed.
    /// EVICT-ON-DUST T1：reduce/close 完成 balance/PnL 結算後立刻 evict_if_dust。
    /// 封住 STRKUSDT 級 dust 螺旋（step_0 pre-spawn gate 漏掉的反覆 halving）。
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
            // EVICT-ON-DUST T1 (PA §1.2.1): runs after fully-closed branch
            // (no-op on already-removed) and after partial-reduce branch
            // (catches sub-floor residue post-halving).
            // EVICT-ON-DUST T1：完全平倉路徑 no-op；部分減倉殘餘 → 即時 evict。
            self.evict_if_dust(symbol, price, "reduce_position");
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
    /// Returns (symbol, realized_pnl) for each closed position so the caller
    /// can forward them to the dynamic risk sizer. `.len()` gives the count
    /// for legacy call sites. DYNAMIC-RISK-1 BUG-1 fix.
    /// 以最新市場價平掉所有持倉，返回 (symbol, 實現 PnL)；caller 可把 PnL 餵給
    /// 動態風險調整器。用 `.len()` 取得舊的 count 語義。DYNAMIC-RISK-1 BUG-1。
    pub fn close_all_positions(&mut self) -> Vec<(String, f64)> {
        let symbols: Vec<String> = self.positions.keys().cloned().collect();
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0);
        let mut results = Vec::with_capacity(symbols.len());
        for symbol in &symbols {
            let price = self.latest_prices.get(symbol).copied().unwrap_or_else(|| {
                // Fallback to entry price if no market price available
                // 無市場價時回退到入場價
                self.positions
                    .get(symbol)
                    .map(|p| p.entry_price)
                    .unwrap_or(0.0)
            });
            if let Some(pnl) = self.close_position(symbol, price, now) {
                results.push((symbol.clone(), pnl));
            }
        }
        results
    }

    /// Check stops on all positions using per-symbol latest prices.
    /// 使用每個交易對的最新價格檢查所有持倉的止損。
    /// RRC-1-C1: Update best_price for all positions (trailing stop tracking).
    /// RRC-1-C1：更新所有持倉的最佳價格（跟蹤止損追蹤）。
    /// EXIT-FEATURES-TABLE-1: also refresh `max_favorable_pnl_pct` +
    /// `peak_reached_ts_ms` under the same loop — both fields are derived
    /// from (current mark price, entry price, side), so piggybacking here
    /// costs nothing and guarantees peak tracking stays in lock-step with
    /// trailing-stop best_price updates (invoked once per tick by on_tick).
    /// EXIT-FEATURES-TABLE-1：同一迴圈內同步刷新 max_favorable_pnl_pct 與
    /// peak_reached_ts_ms；兩者皆由 (mark, entry, side) 決定，搭車更新無成本，
    /// 並確保峰值追蹤與 best_price 同步（on_tick 每 tick 呼叫一次）。
    pub fn update_best_prices(&mut self) {
        self.update_best_prices_at(0);
    }

    /// EXIT-FEATURES-TABLE-1: variant that stamps `peak_reached_ts_ms` with
    /// the tick's wall-clock ms. `ts_ms=0` preserves legacy callers' behaviour
    /// (the stamp only advances when a new favorable high is recorded, so a
    /// 0 input when no high is set is a no-op anyway). Prefer `_at(ts)` from
    /// `on_tick` so exit_features.time_since_peak_ms is accurate.
    /// EXIT-FEATURES-TABLE-1：傳入 tick 時戳的版本。`ts_ms=0` 保留舊呼叫語義
    /// （只有創新高才蓋時戳，無新高時 0 等於 no-op）。on_tick 應傳真實 ts。
    pub fn update_best_prices_at(&mut self, ts_ms: i64) {
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
                // EXIT-FEATURES-TABLE-1: refresh max favorable peak inline.
                // No-op if a real ts_ms isn't provided (legacy callers).
                if ts_ms > 0 {
                    pos.refresh_max_favorable(sym_price, ts_ms);
                }
            }
        }
    }

    // ─────────────────────────────────────────────────────────────────────
    // EVICT-ON-DUST runtime path (F3 / 2026-04-26)
    // PA design `2026-04-26--three_p0_fixes_design.md` §1.
    // ─────────────────────────────────────────────────────────────────────

    /// EVICT-ON-DUST single-symbol gate. Returns the evicted USD notional if
    /// the position's current notional (`qty * latest_price`) is below
    /// `self.dust_floor_usd`; otherwise `None`. Idempotent (no-op if no
    /// position for `symbol`). Caller is expected to invoke immediately
    /// after a `reduce_position` / `apply_fill` mutation that may have left
    /// a sub-floor residue (T1 / T2 triggers).
    ///
    /// Reads `self.dust_floor_usd` (mirror of
    /// `RiskConfig.limits.ft_dust_qty_floor_usd` set via `set_dust_floor_usd`
    /// at TickPipeline ctor + on every RiskConfig version bump) so callers
    /// do not need to thread the floor through their signatures.
    ///
    /// Fail-closed:
    ///   * `self.dust_floor_usd <= 0.0` (gate disabled) → returns `None`
    ///   * `latest_price <= 0.0` or non-finite (stale tick) → returns `None`
    ///   * Position absent → returns `None`
    ///
    /// Audit side-effect: emits a structured `tracing::warn!` line and
    /// **does NOT write trading.fills** (ML training-data hygiene per PA
    /// §1.2.5). Per-engine counter `dust_evictions_total` is incremented.
    ///
    /// EVICT-ON-DUST 單 symbol 閘：當 `qty × latest_price < self.dust_floor_usd`
    /// 時就地驅逐並回傳被驅逐 USD 名目；否則 None。冪等。reduce / apply_fill
    /// 後置呼叫（T1 / T2）。fail-closed：floor<=0 / 價格非有限 / 倉位缺失
    /// → 全 no-op。寫 `tracing::warn!` audit + 累計計數，**不寫 trading.fills**。
    pub(crate) fn evict_if_dust(
        &mut self,
        symbol: &str,
        latest_price: f64,
        trigger_point: &'static str,
    ) -> Option<f64> {
        let dust_floor_usd = self.dust_floor_usd;
        if dust_floor_usd <= 0.0 || !dust_floor_usd.is_finite() {
            return None;
        }
        if latest_price <= 0.0 || !latest_price.is_finite() {
            return None;
        }
        let pos = self.positions.get(symbol)?;
        let notional = pos.qty * latest_price;
        if !notional.is_finite() || notional >= dust_floor_usd {
            return None;
        }
        // Capture before remove() so audit fields read truthful values.
        // 在 remove 前先讀取，audit 才能拿到正確值。
        let evicted_qty = pos.qty;
        let evicted_is_long = pos.is_long;
        let evicted_owner = pos.owner_strategy.clone();
        self.positions_remove(symbol);
        self.dust_evictions_total = self.dust_evictions_total.saturating_add(1);
        tracing::warn!(
            symbol = %symbol,
            evicted_notional_usd = notional,
            dust_floor_usd,
            trigger_point,
            qty = evicted_qty,
            is_long = evicted_is_long,
            owner_strategy = %evicted_owner,
            "EVICT-ON-DUST: phantom dust position evicted (no trading.fills row) \
             / 殭屍 dust 倉位已驅逐（不寫 trading.fills）"
        );
        Some(notional)
    }

    /// EVICT-ON-DUST sweep: scan every position and evict any whose
    /// `qty * latest_price` is below `self.dust_floor_usd`. Returns the
    /// count of positions evicted. Used by T3 (boot reaper, post-migrate
    /// one-shot) and T4 (loop_handlers.rs status arm reaper, ~30 s cadence).
    /// The latest per-symbol price is read from `latest_prices`; a position
    /// with no observed market price falls back to `entry_price` so the
    /// boot reaper (which runs before the first market tick) can still
    /// discharge legacy dust.
    ///
    /// **Performance**: O(N) over `positions`; called twice per minute at
    /// most (T4 status interval is 30 s). MUST NOT be called from the
    /// per-tick hot path — E2 should grep callsites and reject any
    /// tick-rate invocation (PA §1.5 review point #2).
    ///
    /// EVICT-ON-DUST 全掃描：對所有倉位算名目，低於 floor 即驅逐，回傳驅逐數。
    /// T3 + T4 共用。價格優先讀 latest_prices；無市場價回退 entry_price。
    /// **性能限定**：O(N)，禁 per-tick hot path 呼叫。
    pub fn evict_all_dust(&mut self, trigger_point: &'static str) -> usize {
        let dust_floor_usd = self.dust_floor_usd;
        if dust_floor_usd <= 0.0 || !dust_floor_usd.is_finite() {
            return 0;
        }
        // Materialize candidates first so we don't mutate while iterating.
        // 先物化候選 → 再 mutate；避免 HashMap 邊讀邊改 alias 衝突。
        let candidates: Vec<(String, f64, f64, bool, String)> = self
            .positions
            .values()
            .filter_map(|p| {
                let price = self
                    .latest_prices
                    .get(&p.symbol)
                    .copied()
                    .unwrap_or(p.entry_price);
                if price <= 0.0 || !price.is_finite() {
                    return None;
                }
                let notional = p.qty * price;
                if !notional.is_finite() || notional >= dust_floor_usd {
                    return None;
                }
                Some((
                    p.symbol.clone(),
                    notional,
                    p.qty,
                    p.is_long,
                    p.owner_strategy.clone(),
                ))
            })
            .collect();
        let count = candidates.len();
        for (symbol, notional, qty, is_long, owner) in candidates {
            tracing::warn!(
                symbol = %symbol,
                evicted_notional_usd = notional,
                dust_floor_usd,
                trigger_point,
                qty,
                is_long,
                owner_strategy = %owner,
                "EVICT-ON-DUST sweep: phantom dust position evicted (no trading.fills row) \
                 / 殭屍 dust sweep 驅逐（不寫 trading.fills）"
            );
            self.positions_remove(&symbol);
            self.dust_evictions_total = self.dust_evictions_total.saturating_add(1);
        }
        count
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
}
