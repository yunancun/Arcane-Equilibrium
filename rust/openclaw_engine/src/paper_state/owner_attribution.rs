//! Paper Trading owner attribution — symbol ↔ strategy tracking + synthetic
//! owner retriage (P1-8 FUP).
//! 紙盤交易歸屬 — symbol ↔ 策略追蹤 + synthetic owner 重分流（P1-8 FUP）。
//!
//! MODULE_NOTE (EN): Houses `SYNTHETIC_OWNER_LABELS`, the `RetriageOutcome`
//!   enum, `PaperState::adopt_orphan` (Phase 2A orphan adoption) and
//!   `PaperState::retriage_synthetic_owner` (P1-8 FUP tick-level retriage of
//!   bybit_sync / orphan_adopted / orphan_frozen labels). Split out of
//!   `paper_state.rs` in E5-P1-1 (2026-04-18) so attribution changes land in a
//!   single focused file. All behaviour is byte-for-byte preserved from the
//!   pre-split source; dust/notional gate conditions (strict `<`) and label
//!   flip ordering unchanged to keep logs + mirror semantics identical.
//! MODULE_NOTE (中): 放 SYNTHETIC_OWNER_LABELS、RetriageOutcome enum、
//!   adopt_orphan（Phase 2A 孤兒接管）與 retriage_synthetic_owner
//!   （P1-8 FUP tick-level synthetic owner 重分流）。2026-04-18 E5-P1-1 自
//!   paper_state.rs 拆出，讓歸屬變更集中於單一檔。行為完全保留：dust/notional
//!   門檻（嚴格 `<`）、標籤翻轉順序皆不變，確保日誌與 mirror 語義一致。

use super::PaperState;

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

impl PaperState {
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
            super::containers::PaperPosition {
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
}
