// MODULE_NOTE
// 模塊用途：intent_processor portfolio gate「resting limit order 納入 effective
//   notional」單元測試（P1/P2-PORTFOLIO-RESTING-EXPOSURE-1）。從 tests.rs 平移而來
//   （tests.rs 行數超 2000 硬上限），比照本目錄既有 include!("tests_*.rs") 慣例拆出。
// 主要函數：make_resting_order / seed_resting 測試輔助 + test_p1/p2_portfolio_resting_* 系列。
// 依賴：由 tests.rs 經 include! 內聯進 ，沿用 super::* 與既有 fixture。
// 硬邊界：本檔禁止 include 以外的引用；測試邏輯與原 tests.rs 零變更。

// ─────────────────────────────────────────────────────────────────────────────
// P1-PORTFOLIO-RESTING-EXPOSURE-1：portfolio gate 在 effective notional 計算內
// 納入 paper_state.resting_limit_orders 的 unit tests。涵蓋四場景：
//   (1) entry-side resting only（無倉 + 同向 resting）→ 加進 effective notional
//   (2) close-side resting only（有倉 + 反向 resting）→ 從對立 filled 扣減
//   (3) entry + close 混合（多 symbol）→ 兩種規則並存
//   (4) 反向 resting 量 > filled qty → 扣減封頂於 filled，effective 不變負
// 另外加 (5) baseline regression（無 resting）防舊 SoT 行為改變。
// ─────────────────────────────────────────────────────────────────────────────

/// 測試輔助：用 `seed_resting_limit_orders` 直接灌入指定 symbol 的掛單；
/// 不走 `enqueue_resting_limit_order` 以免動到 maker_stats（與本層測試無關）。
#[cfg(test)]
fn make_resting_order(
    symbol: &str,
    is_long: bool,
    qty: f64,
    limit_price: f64,
) -> super::super::paper_state::RestingLimitOrder {
    super::super::paper_state::RestingLimitOrder {
        symbol: symbol.to_string(),
        is_long,
        qty,
        limit_price,
        time_in_force: crate::order_manager::TimeInForce::PostOnly,
        submit_ts_ms: 0,
        deadline_ms: u64::MAX,
        mid_price_at_submit: limit_price,
        order_link_id: format!("test-{}-{}", symbol, if is_long { "L" } else { "S" }),
        context_id: "test_ctx".to_string(),
        strategy: "test_strategy".to_string(),
        funding_rate_at_submit: 0.0,
    }
}

#[cfg(test)]
fn seed_resting<I: IntoIterator<Item = super::super::paper_state::RestingLimitOrder>>(
    state: &mut PaperState,
    orders: I,
) {
    use std::collections::{HashMap, VecDeque};
    let mut queues: HashMap<String, VecDeque<super::super::paper_state::RestingLimitOrder>> =
        HashMap::new();
    for o in orders {
        queues.entry(o.symbol.clone()).or_default().push_back(o);
    }
    state.seed_resting_limit_orders(queues);
}

#[test]
fn test_p1_portfolio_resting_baseline_no_resting_unchanged() {
    // 場景 (5)：無 resting 時行為與舊 SoT 完全等價 — 1 個 long 0.001 BTC × 50_000
    //          = 50 USDT notional → exposure_pct = 0.5%。
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    state.import_positions(vec![("BTC".into(), true, 0.001, 50_000.0, 0)]);

    let exp = IntentProcessor::compute_exposure_pct(&state);
    let corr = IntentProcessor::compute_correlated_exposure_pct(&state);
    let lev = IntentProcessor::compute_leverage(&state);

    // 50 / 10_000 * 100 = 0.5；long 邊 = 50，short 邊 = 0 → max = 50 → 0.5%。
    assert!((exp - 0.5).abs() < 1e-4, "exp={}", exp);
    assert!((corr - 0.5).abs() < 1e-4, "corr={}", corr);
    assert!((lev - 0.005).abs() < 1e-6, "lev={}", lev);
}

#[test]
fn test_p1_portfolio_resting_entry_only_added_to_long() {
    // 場景 (1)：無倉 + 1 個 long entry-side resting 0.002 BTC × 50_000 = 100 USDT。
    //          修前：filled 邊 = 0 → exposure = 0%（盲區）。
    //          修後：effective_long = 100 → exposure = 1%、correlated = 1%。
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    seed_resting(
        &mut state,
        vec![make_resting_order("BTC", true, 0.002, 50_000.0)],
    );

    let exp = IntentProcessor::compute_exposure_pct(&state);
    let corr = IntentProcessor::compute_correlated_exposure_pct(&state);

    // 100 / 10_000 * 100 = 1.0；long=100、short=0 → max=100 → 1.0%。
    assert!((exp - 1.0).abs() < 1e-4, "exp={}", exp);
    assert!((corr - 1.0).abs() < 1e-4, "corr={}", corr);
}

#[test]
fn test_p1_portfolio_resting_close_only_reduces_filled() {
    // 場景 (2)：long 0.004 BTC × 50_000 = 200 USDT filled + 1 個反向（short）
    //          close-side resting 0.002 × 50_000 = 100 USDT。
    //          修前：exposure = 2%（filled 200 / 10_000，close pending 未抵）。
    //          修後：effective_long = 200 - 100 = 100、effective_short = 0
    //                → exposure = 1.0%（生存原則：close pending 預期減倉，
    //                view 改為更接近未來實際 net position）。
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    state.import_positions(vec![("BTC".into(), true, 0.004, 50_000.0, 0)]);
    seed_resting(
        &mut state,
        vec![make_resting_order("BTC", false, 0.002, 50_000.0)],
    );

    let exp = IntentProcessor::compute_exposure_pct(&state);
    let corr = IntentProcessor::compute_correlated_exposure_pct(&state);

    // effective_long = 200 - 100 = 100、effective_short = 0
    // → exp = (100 + 0) / 10_000 * 100 = 1.0；corr = max(100, 0) / 10_000 * 100 = 1.0。
    assert!((exp - 1.0).abs() < 1e-4, "exp={}", exp);
    assert!((corr - 1.0).abs() < 1e-4, "corr={}", corr);
}

#[test]
fn test_p1_portfolio_resting_entry_plus_close_mixed_multi_symbol() {
    // 場景 (3)：兩 symbol 混合：
    //   BTC: long 0.004 × 50_000 = 200 filled，反向 close-side resting 0.002 × 50_000 = 100
    //        → effective_long(BTC) = 200 - 100 = 100、effective_short(BTC) = 0。
    //   ETH: 無倉 + 1 個 short entry-side resting 0.05 × 3000 = 150 USDT。
    //        → effective_long(ETH) = 0、effective_short(ETH) = 150。
    // 總和：effective_long = 100、effective_short = 150。
    //   exposure_pct       = (100 + 150) / 10_000 * 100 = 2.5。
    //   correlated_exposure = max(100, 150) / 10_000 * 100 = 1.5。
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    state.set_latest_price("ETH", 3_000.0);
    state.import_positions(vec![("BTC".into(), true, 0.004, 50_000.0, 0)]);
    seed_resting(
        &mut state,
        vec![
            make_resting_order("BTC", false, 0.002, 50_000.0),
            make_resting_order("ETH", false, 0.05, 3_000.0),
        ],
    );

    let exp = IntentProcessor::compute_exposure_pct(&state);
    let corr = IntentProcessor::compute_correlated_exposure_pct(&state);

    assert!((exp - 2.5).abs() < 1e-4, "exp={}", exp);
    assert!((corr - 1.5).abs() < 1e-4, "corr={}", corr);
}

#[test]
fn test_p1_portfolio_resting_close_reduces_capped_at_filled() {
    // 場景 (4)：long 0.001 BTC × 50_000 = 50 USDT filled + 反向 close-side
    //          resting 0.005 × 50_000 = 250 USDT（>> filled）。
    //          修後：扣減封頂於 filled → effective_long = 50 - 50 = 0、
    //                effective_short = 0（reduces 不會「翻面」變正向 short）。
    //                exposure = 0%、correlated = 0%。
    //          保證不會出現負值或符號錯誤。
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    state.import_positions(vec![("BTC".into(), true, 0.001, 50_000.0, 0)]);
    seed_resting(
        &mut state,
        vec![make_resting_order("BTC", false, 0.005, 50_000.0)],
    );

    let exp = IntentProcessor::compute_exposure_pct(&state);
    let corr = IntentProcessor::compute_correlated_exposure_pct(&state);

    assert!(exp >= 0.0 && exp < 1e-4, "exp={} should be ~0", exp);
    assert!(corr >= 0.0 && corr < 1e-4, "corr={} should be ~0", corr);
}

#[test]
fn test_p1_portfolio_resting_same_direction_resting_is_entry_not_close() {
    // 場景 (1)' boundary：同 symbol 同向 resting 視為 entry-side（加倉，
    // 不是 close）。long 0.001 × 50_000 = 50 filled + 同向 long resting
    // 0.002 × 50_000 = 100 → effective_long = 150、effective_short = 0。
    // exposure = 1.5%、correlated = 1.5%。
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    state.import_positions(vec![("BTC".into(), true, 0.001, 50_000.0, 0)]);
    seed_resting(
        &mut state,
        vec![make_resting_order("BTC", true, 0.002, 50_000.0)],
    );

    let exp = IntentProcessor::compute_exposure_pct(&state);
    let corr = IntentProcessor::compute_correlated_exposure_pct(&state);

    assert!((exp - 1.5).abs() < 1e-4, "exp={}", exp);
    assert!((corr - 1.5).abs() < 1e-4, "corr={}", corr);
}

#[test]
fn test_p1_portfolio_resting_finite_guards_filter_bad_inputs() {
    // 防禦性：qty<=0 / non-finite limit_price 應被靜默過濾，不污染累計值。
    // long filled 0.001 × 50_000 = 50；3 個垃圾 resting（qty=0、qty=NaN、price=0）
    // 全跳過 → effective 與 baseline 相同。
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    state.import_positions(vec![("BTC".into(), true, 0.001, 50_000.0, 0)]);
    seed_resting(
        &mut state,
        vec![
            make_resting_order("BTC", true, 0.0, 50_000.0),
            make_resting_order("BTC", true, f64::NAN, 50_000.0),
            make_resting_order("BTC", true, 0.001, 0.0),
        ],
    );

    let exp = IntentProcessor::compute_exposure_pct(&state);
    let corr = IntentProcessor::compute_correlated_exposure_pct(&state);
    assert!((exp - 0.5).abs() < 1e-4, "exp={}", exp);
    assert!((corr - 0.5).abs() < 1e-4, "corr={}", corr);
}

#[test]
fn test_resting_entry_qty_correlated_pair_blocks_oversize() {
    // P1-PORTFOLIO-RESTING-EXPOSURE-1 end-to-end gate integration test
    // （per dispatch §「Task 3」第三個 test，補既有 7 個 helper-level unit
    // test 沒有覆蓋的「compute_correlated_exposure_pct → check_order_allowed
    // → Reject」全 chain 行為）：
    //
    // 場景：兩 symbol 同方向 entry-side resting maker pending（all crypto
    // highly correlated），「correlated_pair」portfolio 暴露面剛好觸碰
    // correlated_exposure_max_pct（default 60%）→ 任何 oversize new entry
    // 都應被 risk_checks::check_order_allowed 拒絕。
    //
    //   balance = 10_000 USDT
    //   filled long BTC 0.04 × 50_000 = 2_000 USDT（long bucket = 2_000）
    //   entry-side long ETH resting 1.0 × 4_000 = 4_000 USDT
    //     → effective_long = 2_000 + 4_000 = 6_000
    //     → correlated_exposure_pct = 6_000 / 10_000 × 100 = 60.0
    //
    // 修前回歸 baseline（A3 verify report §2）：portfolio gate 對
    // resting 完全 invisible → long bucket 只有 BTC filled 2_000 →
    // correlated = 20% → check_order_allowed 永遠 allow → systemic
    // under-estimate，新 entry 漏網風險超標。
    //
    // 修後不變式（per CLAUDE.md §二 原則 5/6/16）：portfolio gate 把
    // entry-side resting 計入 effective notional → correlated ≥ 60%
    // → 任何 oversize new entry 被 Reject「correlated exposure ≥
    // limit」reason 字串，避免新單把多 symbol pair 推到超 limit 的
    // 同方向集中暴露面。
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    state.set_latest_price("ETH", 4_000.0);
    state.import_positions(vec![("BTC".into(), true, 0.04, 50_000.0, 0)]);
    seed_resting(
        &mut state,
        vec![make_resting_order("ETH", true, 1.0, 4_000.0)],
    );

    // 先用 helper 確認 effective notional + correlated_exposure_pct 落在預期值，
    // 避免 check_order_allowed 因 limit 邏輯內部別的 gate（leverage / position size）
    // 提前拒絕而誤判 root cause。
    let (eff_long, eff_short) = IntentProcessor::compute_effective_long_short_notional(&state);
    assert!(
        (eff_long - 6_000.0).abs() < 1e-4 && eff_short.abs() < 1e-4,
        "effective notional should be (6000, 0), got ({}, {})",
        eff_long,
        eff_short,
    );
    let corr = IntentProcessor::compute_correlated_exposure_pct(&state);
    assert!(
        (corr - 60.0).abs() < 1e-4,
        "correlated_exposure_pct should sit at the 60% cap, got {}",
        corr,
    );

    // 模擬一筆 small new long entry intent（ETH 0.001 × 4_000 = 4 USDT）。
    // 量很小所以 position_size / leverage / daily_loss 全 PASS，必然落在
    // correlated_exposure_pct ≥ 60 這條 reject 規則上。
    let cfg = RiskConfig::default();
    let check = crate::risk_checks::check_order_allowed(
        0.001,
        4_000.0,
        state.balance(),
        IntentProcessor::compute_exposure_pct(&state),
        corr,
        IntentProcessor::compute_leverage(&state),
        0.0,
        false, // is_reducing=false：新開倉走完整 gate
        &cfg,
    );
    assert!(
        !check.allowed,
        "oversize new entry should be blocked by correlated exposure cap; \
         reason={}",
        check.reason,
    );
    assert!(
        check.reason.contains("correlated exposure"),
        "reject reason should pinpoint correlated_exposure_pct gate, got '{}'",
        check.reason,
    );
}

#[test]
fn test_p2_portfolio_resting_multi_close_summed_capped_at_filled() {
    // P2-PORTFOLIO-RESTING-TEST-COVERAGE（2026-05-18）：A3 WARN-2「多個 close-side
    // resting 累加後 > filled qty 時，扣減仍應封頂於 filled」的不變式 explicit
    // regression。既有 `test_p1_portfolio_resting_close_reduces_capped_at_filled`
    // 只覆蓋「單筆 close 超過 filled」，本測試補「同 symbol 多筆 close-side
    // resting 累加超過 filled」場景。
    //
    //   balance = 10_000 USDT
    //   filled long BTC 0.001 × 50_000 = 50 USDT
    //   反向 close-side resting 兩筆：
    //     - short 0.002 × 50_000 = 100 USDT
    //     - short 0.001 × 50_000 =  50 USDT
    //   summed close = 150 USDT >> filled long = 50 USDT
    //   → red_short_capped = min(150, 50).max(0) = 50（封頂於 filled）
    //   → effective_long = 50 - 50 = 0、effective_short = 0
    //   → exposure_pct = 0%、correlated_exposure_pct = 0%
    //
    // 修前 A3 風險：若 cap 邏輯誤把 summed close 視為「翻面 short」，會出現
    // effective_short > 0；本測試 explicit 鎖住「不翻面」不變式。
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    state.import_positions(vec![("BTC".into(), true, 0.001, 50_000.0, 0)]);
    seed_resting(
        &mut state,
        vec![
            make_resting_order("BTC", false, 0.002, 50_000.0),
            make_resting_order("BTC", false, 0.001, 50_000.0),
        ],
    );

    let (eff_long, eff_short) = IntentProcessor::compute_effective_long_short_notional(&state);
    assert!(
        eff_long.abs() < 1e-4 && eff_short.abs() < 1e-4,
        "summed close-side resting (150) should cap at filled (50); \
         expected (0, 0), got ({}, {})",
        eff_long,
        eff_short,
    );
    let exp = IntentProcessor::compute_exposure_pct(&state);
    let corr = IntentProcessor::compute_correlated_exposure_pct(&state);
    assert!(exp >= 0.0 && exp < 1e-4, "exp={} should be ~0", exp);
    assert!(corr >= 0.0 && corr < 1e-4, "corr={} should be ~0", corr);
}
