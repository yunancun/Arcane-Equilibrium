//! Paper Trading dust / orphan-frozen triage gate (P0-6 + DUST-EVICTION-GAP-1 / P1-8).
//! 紙盤交易 dust / orphan-frozen 分流閘（P0-6 + DUST-EVICTION-GAP-1 / P1-8）。
//!
//! MODULE_NOTE (EN): Houses the `TriageOutcome` result struct and the
//!   `PaperState::triage_bybit_sync` method that runs at startup after
//!   `import_positions()` + `set_positions_mirror()`. Each bybit_sync position
//!   is assigned to one of three buckets: adopted (in scanner universe),
//!   evicted (not in universe, notional ≥ min), or dust-frozen (not in
//!   universe, notional < min — retained in paper_state with
//!   `owner_strategy = DUST_FROZEN_STRATEGY`, no close dispatched). The
//!   `dust_frozen` counter MUST be preserved across refactors (it's wired into
//!   the startup log + operator-visible reconciler diagnostics). Split out of
//!   `paper_state.rs` in E5-P1-1 (2026-04-18) as an orphan (§九 file-structure
//!   rule): isolated decision-tree logic with a dedicated test bench.
//! MODULE_NOTE (中): 存放 TriageOutcome 結果結構與 PaperState::triage_bybit_sync
//!   方法，啟動時於 import_positions() + set_positions_mirror() 後執行。每個
//!   bybit_sync 倉位被分到三桶之一：adopted（於 scanner universe）、evicted（不在
//!   universe、名義值 ≥ min）、dust_frozen（不在 universe、名義值 < min — 留於
//!   paper_state 並標記 DUST_FROZEN_STRATEGY、不派 close）。dust_frozen 計數器必須
//!   跨重構保留（啟動 log 與 operator 可見的對帳診斷有接線）。2026-04-18 E5-P1-1
//!   自 paper_state.rs 拆為 orphan（§九）：隔離的決策樹邏輯配獨立測試台。

use super::PaperState;

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

impl PaperState {
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
                    outcome.adopted.push((symbol, strategy.to_string()));
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
                    outcome
                        .dust_frozen
                        .push((symbol, is_long, qty, est_notional, min_notional));
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
}
