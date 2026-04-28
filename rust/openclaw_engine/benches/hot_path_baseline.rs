//! Hot-path baseline for `TickPipeline::on_tick`.
//! `cargo bench -p openclaw_engine --bench hot_path_baseline`

use std::hint::black_box;
use std::time::{Duration, Instant};

use openclaw_engine::strategies::{
    bb_breakout::BbBreakout, bb_reversion::BbReversion, grid_trading::GridTrading,
    ma_crossover::MaCrossover,
};
use openclaw_engine::tick_pipeline::TickPipeline;
use openclaw_types::PriceEvent;

const WARMUP_TICKS: usize = 1_000;
const MEASURE_TICKS: usize = 10_000;

fn make_event(symbol: &str, price: f64, ts_ms: u64) -> PriceEvent {
    PriceEvent::new(symbol.to_string(), price, ts_ms)
}

fn build_events(symbols: &[&str], count: usize, ts_offset: u64) -> Vec<PriceEvent> {
    let base_prices = [67_000.0, 2_050.0, 150.0, 0.53, 0.16];
    (0..count)
        .map(|i| {
            let sym_idx = i % symbols.len();
            let base = base_prices[sym_idx % base_prices.len()];
            let wobble = (i as f64 * 0.13).sin() * base * 0.003;
            make_event(
                symbols[sym_idx],
                base + wobble,
                ts_offset + i as u64 * 1_000,
            )
        })
        .collect()
}

fn build_pipeline(symbols: &[&str]) -> TickPipeline {
    let mut pipeline = TickPipeline::new(symbols);
    pipeline
        .grant_paper_auth()
        .expect("paper auth should grant");
    pipeline.orchestrator.register(Box::new(MaCrossover::new()));
    pipeline.orchestrator.register(Box::new(BbBreakout::new()));
    pipeline.orchestrator.register(Box::new(BbReversion::new()));
    pipeline
        .orchestrator
        .register(Box::new(GridTrading::new(60_000.0, 80_000.0)));
    pipeline
}

fn percentile(sorted: &[Duration], pct: f64) -> Duration {
    if sorted.is_empty() {
        return Duration::ZERO;
    }
    let idx = ((sorted.len() - 1) as f64 * pct).round() as usize;
    sorted[idx.min(sorted.len() - 1)]
}

fn micros(d: Duration) -> f64 {
    d.as_nanos() as f64 / 1_000.0
}

fn main() {
    let symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"];
    let warmup_events = build_events(&symbols, WARMUP_TICKS, 0);
    let measure_events = build_events(&symbols, MEASURE_TICKS, WARMUP_TICKS as u64 * 1_000);
    let mut pipeline = build_pipeline(&symbols);

    for event in &warmup_events {
        black_box(pipeline.on_tick(black_box(event)));
    }

    let mut per_tick = Vec::with_capacity(MEASURE_TICKS);
    let wall_start = Instant::now();
    for event in &measure_events {
        let tick_start = Instant::now();
        black_box(pipeline.on_tick(black_box(event)));
        per_tick.push(tick_start.elapsed());
    }
    let wall_elapsed = wall_start.elapsed();
    per_tick.sort_unstable();

    let avg_us = micros(wall_elapsed) / MEASURE_TICKS as f64;
    let p50_us = micros(percentile(&per_tick, 0.50));
    let p99_us = micros(percentile(&per_tick, 0.99));
    let max_us = per_tick.last().map(|d| micros(*d)).unwrap_or(0.0);

    assert_eq!(
        pipeline.stats.total_ticks,
        (WARMUP_TICKS + MEASURE_TICKS) as u64
    );
    println!(
        "hot_path_baseline ticks={} symbols={} avg_us={avg_us:.3} p50_us={p50_us:.3} p99_us={p99_us:.3} max_us={max_us:.3}",
        MEASURE_TICKS,
        symbols.len()
    );
}
