//! P2-PORTFOLIO-RESTING-E5-BENCH（2026-05-18）：portfolio gate 熱路徑
//! latency bench。
//!
//! 動機：P1-PORTFOLIO-RESTING-EXPOSURE-1 把 resting maker pending 納入
//! effective notional 計算後，每呼一次 `compute_*` helper 就重建一份 per-symbol
//! HashMap netting；P2-PORTFOLIO-RESTING-ROUTER-CACHE 後 router Gate 2.7 改在
//! caller 端只算一次 netting，三個百分比靠 `_from_netting` 純算術復用。本
//! bench 量化兩條路徑的 p50/p99 latency 差距，作為 E5 hot-path 改動的證據。
//!
//! 執行方式：
//!   cargo bench -p openclaw_engine --bench intent_processor_exposure
//!
//! Compile-only：
//!   cargo bench -p openclaw_engine --bench intent_processor_exposure --no-run
//!
//! Harness style 與 `hot_path_baseline.rs` 對齊：plain `fn main()` + 手動
//! `Instant` 計時，避免引入 criterion dev-dep。

use std::hint::black_box;
use std::time::{Duration, Instant};

use openclaw_engine::intent_processor::IntentProcessor;
use openclaw_engine::order_manager::TimeInForce;
use openclaw_engine::paper_state::{PaperState, RestingLimitOrder};

const WARMUP_ITERS: usize = 200;
const MEASURE_ITERS: usize = 1_000;
const SYMBOL_COUNT: usize = 25;
const RESTING_PER_SYMBOL: usize = 3;

/// 為什麼挑 25 × 3：對齊 operator 25-symbol 上限（feedback_position_sizing）
/// 加上 1B-4.2 entry-side + close-side resting 同 symbol 並存的真實情境，
/// 模擬 close/entry/同向加倉混合，把 helper 的 HashMap 三段累加全 exercise。
fn make_resting(symbol: &str, is_long: bool, qty: f64, limit_price: f64) -> RestingLimitOrder {
    RestingLimitOrder {
        symbol: symbol.to_string(),
        is_long,
        qty,
        limit_price,
        time_in_force: TimeInForce::PostOnly,
        submit_ts_ms: 0,
        deadline_ms: u64::MAX,
        mid_price_at_submit: limit_price,
        order_link_id: format!("bench-{}-{}", symbol, if is_long { "L" } else { "S" }),
        context_id: "bench_ctx".to_string(),
        strategy: "bench_strategy".to_string(),
        funding_rate_at_submit: 0.0,
    }
}

/// 建立 25 symbols × 3 resting + 50% 對應 filled position 的 PaperState。
/// 命名以 BENCH00..BENCH24 數字化，避免任何 production symbol allowlist 干擾。
/// long/short / entry/close 混合：
///   - 偶數 symbol：long filled，第 1 筆 short resting（close-side）、
///                  第 2 筆 long resting（同向加倉 = entry-side）、
///                  第 3 筆 short resting（再一筆 close）。
///   - 奇數 symbol：無 filled，三筆 long resting（全 entry-side）。
/// 同 symbol 多筆 close-side 配 filled 帶出 Task 1 新增的 cap 路徑覆蓋。
fn build_pressured_state() -> PaperState {
    let mut state = PaperState::new(100_000.0);
    let mut all_resting = std::collections::HashMap::new();
    for i in 0..SYMBOL_COUNT {
        let symbol = format!("BENCH{:02}", i);
        let base_price = 1_000.0 + i as f64 * 37.0; // 1_000..1_888 範圍避開零價
        state.set_latest_price(&symbol, base_price);

        let mut queue = std::collections::VecDeque::new();
        if i.is_multiple_of(2) {
            // 偶數：long filled 0.5 × base_price ~ 500..944 USDT。
            state.import_positions(vec![(symbol.clone(), true, 0.5, base_price, 0)]);
            queue.push_back(make_resting(&symbol, false, 0.2, base_price));
            queue.push_back(make_resting(&symbol, true, 0.1, base_price));
            queue.push_back(make_resting(&symbol, false, 0.15, base_price));
        } else {
            for _ in 0..RESTING_PER_SYMBOL {
                queue.push_back(make_resting(&symbol, true, 0.05, base_price));
            }
        }
        all_resting.insert(symbol, queue);
    }
    // 一次 seed 所有 resting（避免 import_positions 反覆 clear 影響 queue）。
    state.seed_resting_limit_orders(all_resting);
    state
}

fn percentile(sorted: &[Duration], pct: f64) -> Duration {
    if sorted.is_empty() {
        return Duration::ZERO;
    }
    let idx = ((sorted.len() - 1) as f64 * pct).round() as usize;
    sorted[idx.min(sorted.len() - 1)]
}

fn nanos(d: Duration) -> f64 {
    d.as_nanos() as f64
}

/// Bench scenario A：單呼 `compute_effective_long_short_notional`，建立 1 份
/// HashMap netting。對應 P1 落地後、未做 P2 caller cache 之前的舊熱路徑單呼
/// 成本基線。
fn bench_single_netting(state: &PaperState) -> Vec<Duration> {
    let mut samples = Vec::with_capacity(MEASURE_ITERS);
    for _ in 0..WARMUP_ITERS {
        black_box(IntentProcessor::compute_effective_long_short_notional(
            black_box(state),
        ));
    }
    for _ in 0..MEASURE_ITERS {
        let t0 = Instant::now();
        let r = IntentProcessor::compute_effective_long_short_notional(black_box(state));
        let elapsed = t0.elapsed();
        black_box(r);
        samples.push(elapsed);
    }
    samples.sort_unstable();
    samples
}

/// Bench scenario B：P2 caller cache 後的 hot path — 一次 netting + 三個
/// `_from_netting` 純算術。對 router Gate 2.7 cluster 是 end-to-end 真值。
fn bench_cached_three_pcts(state: &PaperState) -> Vec<Duration> {
    let mut samples = Vec::with_capacity(MEASURE_ITERS);
    for _ in 0..WARMUP_ITERS {
        let (eff_long, eff_short) =
            IntentProcessor::compute_effective_long_short_notional(black_box(state));
        let balance = state.balance();
        black_box(IntentProcessor::compute_exposure_pct_from_netting(
            eff_long, eff_short, balance,
        ));
        black_box(IntentProcessor::compute_correlated_exposure_pct_from_netting(
            eff_long, eff_short, balance,
        ));
        black_box(IntentProcessor::compute_leverage_from_netting(
            eff_long, eff_short, balance,
        ));
    }
    for _ in 0..MEASURE_ITERS {
        let t0 = Instant::now();
        let (eff_long, eff_short) =
            IntentProcessor::compute_effective_long_short_notional(black_box(state));
        let balance = state.balance();
        let a = IntentProcessor::compute_exposure_pct_from_netting(eff_long, eff_short, balance);
        let b = IntentProcessor::compute_correlated_exposure_pct_from_netting(
            eff_long, eff_short, balance,
        );
        let c = IntentProcessor::compute_leverage_from_netting(eff_long, eff_short, balance);
        let elapsed = t0.elapsed();
        black_box((a, b, c));
        samples.push(elapsed);
    }
    samples.sort_unstable();
    samples
}

fn report(label: &str, samples: &[Duration]) {
    let p50 = percentile(samples, 0.50);
    let p99 = percentile(samples, 0.99);
    let max = samples.last().copied().unwrap_or(Duration::ZERO);
    println!(
        "{label} iters={} p50_ns={:.0} p99_ns={:.0} max_ns={:.0}",
        samples.len(),
        nanos(p50),
        nanos(p99),
        nanos(max),
    );
}

fn main() {
    let state = build_pressured_state();
    let samples_a = bench_single_netting(&state);
    let samples_b = bench_cached_three_pcts(&state);
    println!(
        "intent_processor_exposure symbols={} resting_per_symbol={}",
        SYMBOL_COUNT, RESTING_PER_SYMBOL
    );
    report("single_netting", &samples_a);
    report("cached_three_pcts", &samples_b);
}
