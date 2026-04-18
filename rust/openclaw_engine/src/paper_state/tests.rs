//! Paper Trading State test bench — preserved from the pre-split monolithic
//! `paper_state.rs`; moved here intact during E5-P1-1 (2026-04-18).
//! 紙盤交易狀態測試台 — E5-P1-1 拆分時整段原樣移出自 paper_state.rs。
//!
//! MODULE_NOTE (EN): Co-located with `paper_state/mod.rs` so tests can reach
//!   pub(super) fields + private mirror helpers via `use super::*` without
//!   widening the module's public surface. Three oracle tests (suffixed with
//!   `*_bit_exact`) were added as forward-regression guards for
//!   MICRO-PROFIT-FIX-1 `entry_notional` accumulation and the weighted-avg
//!   entry-price formula: they use `f64::to_bits()` comparisons and MUST fail
//!   if the arithmetic order changes.
//! MODULE_NOTE (中): 與 paper_state/mod.rs 相鄰放置，讓測試能透過
//!   `use super::*` 直接存取 pub(super) 欄位與私有 mirror helper，不擴大
//!   模組對外的公開面。新增三個 `*_bit_exact` oracle 測試作為
//!   MICRO-PROFIT-FIX-1 累加 entry_notional / 加權平均進場價的算術防回歸
//!   護欄，使用 `f64::to_bits()` 比對——算術順序一變即 fail。

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
    let _ = initial_fee; // silence unused-variable warning (pre-split parity)
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
    assert_eq!(closed.len(), 2);
    // Both closes produce non-zero pnl — sizer-feeding regression check.
    // 兩筆平倉皆產生非零 pnl — sizer 餵入回歸檢查。
    assert!(closed.iter().all(|(_, p)| *p != 0.0));
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
        ("ZERO".to_string(), true, 0.0, 1.0, 0), // skipped (qty=0)
        ("BAD".to_string(), true, 1.0, -5.0, 0), // skipped (price<=0)
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
    let inserted = s.adopt_orphan("BTCUSDT", true, 0.2, 51_000.0, 1_700_000_000_000, None);
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
    seed_bybit_sync(
        &mut s,
        &[
            ("BTCUSDT", true, 0.01, 50000.0),
            ("ETHUSDT", false, 0.5, 3000.0),
        ],
    );
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
    seed_bybit_sync(
        &mut s,
        &[
            ("BTCUSDT", true, 0.01, 50000.0),
            ("SHIBUSDT", true, 1000000.0, 0.00001),
        ],
    );
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
    let result = s.triage_bybit_sync(&active, strategies, |_, qty| Some((qty * 5.0, 5.0)));

    assert_eq!(result.evicted.len(), 1);
    assert_eq!(result.dust_frozen.len(), 0);
    assert_eq!(s.position_count(), 0);
}

#[test]
fn triage_mixed_adopt_evict_dust_in_one_pass() {
    // 綜合場景：三個 bybit_sync 倉位，一個 adopt、一個正常 evict、一個 dust freeze。
    let mut s = PaperState::new(10_000.0);
    seed_bybit_sync(
        &mut s,
        &[
            ("BTCUSDT", true, 0.01, 50000.0),  // in universe → adopt
            ("SHIBUSDT", true, 100.0, 0.001),  // not in universe, normal evict
            ("PNUTUSDT", false, 3.0, 0.06644), // not in universe, dust freeze
        ],
    );

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
    assert_eq!(
        s.get_position("BTCUSDT").unwrap().owner_strategy,
        "ma_crossover"
    );
    assert_eq!(
        s.get_position("PNUTUSDT").unwrap().owner_strategy,
        "orphan_frozen"
    );
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
    assert_eq!(
        s.get_position("BTCUSDT").unwrap().owner_strategy,
        "ma_crossover"
    );
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

    let outcome =
        s.retriage_synthetic_owner("PNUTUSDT", 0.06644, true, "ma_crossover", Some(5.0));
    match outcome {
        RetriageOutcome::FrozenAsDust {
            was_downgraded,
            min_notional,
            ..
        } => {
            assert!(was_downgraded);
            assert!((min_notional - 5.0).abs() < 1e-9);
        }
        other => panic!("expected FrozenAsDust, got {:?}", other),
    }
    assert_eq!(
        s.get_position("PNUTUSDT").unwrap().owner_strategy,
        "orphan_frozen"
    );
}

#[test]
fn retriage_dust_stays_frozen_is_idempotent() {
    // orphan_frozen still dust → was_downgraded=false (no state change, no log).
    // orphan_frozen 仍是 dust → was_downgraded=false（無狀態變化、無日誌）。
    let mut s = PaperState::new(10_000.0);
    seed_bybit_sync(&mut s, &[("PNUTUSDT", true, 3.0, 0.06644)]);
    // Drop into dust first.
    let _ = s.retriage_synthetic_owner("PNUTUSDT", 0.06644, true, "ma_crossover", Some(5.0));
    assert_eq!(
        s.get_position("PNUTUSDT").unwrap().owner_strategy,
        "orphan_frozen"
    );

    // Second call — already frozen, should be idempotent no-op log-wise.
    // 第二次呼叫 — 已凍結，應為 idempotent、不重複發日誌。
    let outcome =
        s.retriage_synthetic_owner("PNUTUSDT", 0.06644, true, "ma_crossover", Some(5.0));
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
    assert_eq!(
        s.get_position("PNUTUSDT").unwrap().owner_strategy,
        "orphan_frozen"
    );

    // Price recovers — 100 × 0.08 = 8 > 5 min. In universe → promote.
    // 價格回升 → 8 > 5 → 升級。
    let outcome = s.retriage_synthetic_owner("PNUTUSDT", 0.08, true, "ma_crossover", Some(5.0));
    match outcome {
        RetriageOutcome::Promoted {
            from,
            to,
            est_notional,
        } => {
            assert_eq!(from, "orphan_frozen");
            assert_eq!(to, "ma_crossover");
            assert!((est_notional - 8.0).abs() < 1e-9);
        }
        other => panic!("expected Promoted, got {:?}", other),
    }
    assert_eq!(
        s.get_position("PNUTUSDT").unwrap().owner_strategy,
        "ma_crossover"
    );
}

#[test]
fn retriage_promotes_bybit_sync_directly_when_in_universe() {
    // Simulates the case where startup triage never ran (race / registry not ready yet)
    // and a bybit_sync-labelled position persists. Tick arrives with in_universe=true
    // and notional OK → immediate promotion without going through orphan_frozen first.
    // 模擬啟動 triage 未跑的情況；tick 到達即升級，不必先凍結。
    let mut s = PaperState::new(10_000.0);
    seed_bybit_sync(&mut s, &[("ETHUSDT", false, 0.5, 3000.0)]);

    let outcome =
        s.retriage_synthetic_owner("ETHUSDT", 3000.0, true, "ma_crossover", Some(5.0));
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
    assert_eq!(
        s.get_position("BTCUSDT").unwrap().owner_strategy,
        "orphan_adopted"
    );

    let outcome =
        s.retriage_synthetic_owner("BTCUSDT", 50000.0, true, "ma_crossover", Some(5.0));
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
        RetriageOutcome::NeedsEviction {
            is_long,
            qty,
            est_notional,
        } => {
            assert!(is_long);
            assert!((qty - 5.0).abs() < 1e-9);
            assert!((est_notional - 50.0).abs() < 1e-9);
        }
        other => panic!("expected NeedsEviction, got {:?}", other),
    }
    // Position kept as-is until caller dispatches close + exchange settles.
    // 呼叫方派 close + 交易所結算前，倉位保留現狀。
    assert_eq!(
        s.get_position("OLDUSDT").unwrap().owner_strategy,
        "bybit_sync"
    );
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
    assert_eq!(
        s.get_position("BTCUSDT").unwrap().owner_strategy,
        "bybit_sync"
    );
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
    let inserted = s.adopt_orphan("BTCUSDT", true, 0.01, 50000.0, 1000, Some("ma_crossover"));
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

// ─── E5-P1-1 oracle tests (2026-04-18): bit-exact preservation ─────────
// ─── E5-P1-1 oracle 測試：bit-exact f64 保留證據 ─────────────────────────

/// Oracle: `apply_fill` close-branch PnL must equal the pre-split formula
/// bit-for-bit. Since we did not reorder any operations, the result is
/// `(fill_price - entry_price) * close_qty` for a long — compare via
/// `to_bits()` not `abs()` to catch any silent reordering a future refactor
/// might introduce.
/// Oracle：apply_fill close 分支的 PnL 必須與拆分前公式 bit-for-bit 相等。
/// 沒有重排運算，long 時為 (fill_price - entry_price) * close_qty —
/// 用 to_bits() 比，不用 abs()，任何未來重構的靜默重排都會被抓到。
#[test]
fn oracle_apply_fill_close_long_pnl_bit_exact() {
    let mut s = PaperState::new(10_000.0);
    s.apply_fill("BTC", true, 0.1, 50_000.0, 0.0, 0, "test");
    // Record baseline balance AFTER open (open doesn't write realized_pnl).
    let before_close = s.total_realized_pnl();
    assert_eq!(before_close.to_bits(), 0.0_f64.to_bits());

    // Oracle PnL: (51_000.0 - 50_000.0) * 0.1 — the pre-split formula verbatim.
    let oracle_pnl = (51_000.0_f64 - 50_000.0_f64) * 0.1_f64;
    s.apply_fill("BTC", false, 0.1, 51_000.0, 0.0, 1000, "test");
    assert_eq!(
        s.total_realized_pnl().to_bits(),
        oracle_pnl.to_bits(),
        "close-branch PnL must be bit-exact to pre-split formula"
    );
}

/// Oracle: `entry_notional` accumulate path must match
/// `entry_notional + qty*fill_price` to the bit. Any FMA fusion or
/// reordering would break this; sticking with plain `+=` keeps it safe.
/// Oracle：entry_notional 累加必須與 entry_notional + qty*fill_price bit 一致。
#[test]
fn oracle_entry_notional_accumulate_bit_exact() {
    let mut s = PaperState::new(10_000.0);
    s.apply_fill("BTC", true, 0.1, 50_000.0, 0.0, 0, "test");
    let initial_en = s.get_position("BTC").unwrap().entry_notional;
    let expected = initial_en + 0.1_f64 * 52_000.0_f64;
    s.apply_fill("BTC", true, 0.1, 52_000.0, 0.0, 1000, "test");
    let after = s.get_position("BTC").unwrap().entry_notional;
    assert_eq!(
        after.to_bits(),
        expected.to_bits(),
        "entry_notional accumulate must be bit-exact to pre-split `+= qty*fill_price`"
    );
}

/// Oracle: weighted-average entry price formula preserved bit-for-bit.
/// avg = (old_entry * old_qty + fill_price * qty) / new_qty
/// Oracle：加權平均入場價公式保留 bit-for-bit。
#[test]
fn oracle_weighted_avg_entry_price_bit_exact() {
    let mut s = PaperState::new(10_000.0);
    s.apply_fill("BTC", true, 0.1, 50_000.0, 0.0, 0, "test");
    let oracle_avg =
        (50_000.0_f64 * 0.1_f64 + 52_000.0_f64 * 0.1_f64) / (0.1_f64 + 0.1_f64);
    s.apply_fill("BTC", true, 0.1, 52_000.0, 0.0, 1000, "test");
    let pos = s.get_position("BTC").unwrap();
    assert_eq!(
        pos.entry_price.to_bits(),
        oracle_avg.to_bits(),
        "weighted-avg entry_price must be bit-exact"
    );
}
