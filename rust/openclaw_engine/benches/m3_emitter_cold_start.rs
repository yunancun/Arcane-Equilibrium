//! AC-7 m3 emitter cold start bench — first tick wall-clock < 50ms。
//!
//! MODULE_NOTE
//! 模塊用途：
//!   per docs/execution_plan/specs/2026-05-23--sprint5_wave1_4_3_2_ac7_m3_cold_start_bench.md
//!   §2.1 / §2.2 量測 `MetricEmitterScheduler::new + run` 進入「first tick」
//!   wall-clock 時間是否 < 50ms。對齊 m3_metric_emitter_sprint2_design_spec.md
//!   §AC-7 line 841 cold start budget 設計合約。
//!
//!   bench 與 production code path 完全隔離：走 MockEmitter（lightweight，0
//!   sysinfo / sqlx / WS / portfolio cache 真實構造）+ NotifyOnceWriter（mock
//!   writer），確保量測 scheduler 自身啟動成本 / spawn 排程開銷，而非真實
//!   emitter 採樣成本（後者由 production observe + Sprint 5 cascade 量測）。
//!
//! Harness style 與既有 benches/hot_path_baseline.rs +
//! benches/intent_processor_exposure.rs 對齊：plain `fn main()` + 手動
//! `Instant` 計時 + harness=false；0 criterion dev-dep。
//!
//! 執行方式：
//!   cargo bench -p openclaw_engine --bench m3_emitter_cold_start
//!
//! Compile-only：
//!   cargo bench -p openclaw_engine --bench m3_emitter_cold_start --no-run
//!
//! 量測語意：
//!   t0 = Instant::now()
//!   scheduler = MetricEmitterScheduler::new(...)      // build phase
//!   handle = tokio::spawn(scheduler.run(cancel))      // spawn phase
//!   notify.notified().await                           // wait first sample fire
//!   t1 = Instant::now()
//!   elapsed_ms = (t1 - t0).as_millis()                // 必 < 50ms
//!
//! 為什麼 notify_one() 而非 notify_waiters()：
//!   - 任一 emitter 首 row 寫完即視為「first tick」達標；6 emitter 同時 spawn
//!     後 tokio::time::interval 預設「立即 fire 首次 tick」，6 emitter 競賽
//!     誰先寫 row，`notify_one()` 給單一 waiter 喚醒即足夠語意。
//!   - notify_waiters() 是「喚醒所有當前 waiter」語意不對；此 bench 只一個
//!     waiter（main loop）。
//!
//! 為什麼固定 tokio worker_threads=2：
//!   - 跨平台一致：Mac aarch64 / Linux x86_64 default thread pool 大小不同
//!     （依機器 CPU 核心數），固定 2 threads 排除「核多 = 排程更快」platform
//!     bias，bench 量測是 scheduler 自身成本而非 thread pool 規模。
//!   - 2 threads 足以承載 main loop + 6 emitter loop spawn task；不會因
//!     undersubscribe 引入 starvation noise。

use std::sync::Arc;
use std::time::Instant;

use async_trait::async_trait;
use openclaw_engine::health::event_bus::HealthEventBus;
use openclaw_engine::health::metric_emitter::{
    DomainEmitter, MetricEmitterScheduler, MetricSample,
};
use openclaw_engine::health::writer::{HealthObservationRow, HealthObservationWriter};
use openclaw_engine::health::{HealthDomain, HealthState, M3Error};
use tokio_util::sync::CancellationToken;

/// 量測 iteration 數；100 次取 p50 + p99 + mean。
///
/// 為什麼 100 次：
///   - cold start 是 spawn + first tick 排程開銷量測，10 次太少（容易被首次
///     tokio runtime warm-up 噪音支配），1000 次過多（bench 跑 > 60s 影響 CI
///     週期）；100 次平衡。
const ITER: usize = 100;

/// AC-7 cold start budget：first tick wall-clock 必 < 50ms。
///
/// 為什麼 50ms：
///   - per m3_metric_emitter_sprint2_design_spec.md §AC-7 line 841 設計合約；
///     cold start 目標「scheduler spawn 後第一次 sample 不應顯著拖慢 engine
///     啟動序列」。Sprint 5 cascade 加 PG writer 後可能需重 assess 100ms
///     budget（per spec line 887）。
const BUDGET_MS: u128 = 50;

// ============================================================
// MockSample — bench 專用 sample（不接 production EngineRuntimeMetricRow）
// ============================================================

/// Mock metric sample；返回固定 numeric_value=1.0 + HealthOk band。
///
/// 為什麼 mock 不接 production EngineRuntimeMetricRow：
///   - bench 量測「scheduler 自身啟動成本」非「6 真實 emitter 採樣成本」；
///     production sysinfo / sqlx / WS 採樣成本是另一個量測對象（per spec §2.3
///     反模式 (b)）。
///   - mock sample 構造成本接近 0（一個 unit struct），確保量測 t1 - t0 純
///     反映 scheduler spawn + interval 排程開銷。
struct MockSample;

impl MetricSample for MockSample {
    fn metric_name(&self) -> &'static str {
        "cold_start_probe"
    }

    fn numeric_value(&self) -> f64 {
        1.0
    }

    fn classify_band(&self) -> HealthState {
        HealthState::HealthOk
    }
    // extra_evidence 走 trait default None；不需 override。
}

// ============================================================
// MockEmitter — lightweight emitter（避真實 sysinfo / sqlx 構造污染量測）
// ============================================================

/// Mock domain emitter；sample_interval_sec=1（最短合法值）+ sample() 返 1
/// MockSample。
///
/// 為什麼 sample_interval_sec=1：
///   - `tokio::time::interval` MissedTickBehavior::Delay default 下首次 tick
///     立即 fire；interval=1s 不影響 first tick 時序，但避「interval=0」
///     debug_assert 失敗（tokio 0.1+ 規約）。
///   - production 30s / 60s / 300s 在 cold start scenario 與 1s 等價：都是
///     「首次 tick 立即」+ 後續按 interval 排程；本 bench 只取首次，差異不在
///     量測範圍。
struct MockEmitter {
    domain: HealthDomain,
}

#[async_trait]
impl DomainEmitter for MockEmitter {
    fn domain(&self) -> HealthDomain {
        self.domain
    }

    fn sample_interval_sec(&self) -> u64 {
        1
    }

    async fn sample(&mut self) -> Result<Vec<Box<dyn MetricSample>>, M3Error> {
        Ok(vec![Box::new(MockSample) as Box<dyn MetricSample>])
    }
}

// ============================================================
// NotifyOnceWriter — mock writer，首次 row 寫入即 notify
// ============================================================

/// Mock writer：第一次 write_observation 被呼叫即 notify_one()，後續呼叫保持
/// Ok(())。
///
/// 為什麼 notify_one() 不 notify_waiters()：
///   - 本 bench 單一 waiter（main loop on `notified().await`），notify_one()
///     語意更精準；多 emitter 競賽寫 row 場景下，只需要任一 row 觸發 wake。
///   - notify_one() 多次呼叫只記「至多一個 wake permit」，後續無 waiter 也
///     不會 panic / 漏訊；正好符合「任一 emitter 首 row 即達標」語意。
///
/// 為什麼 Arc<tokio::sync::Notify>：
///   - 跨 task 共享 wake signal；spawn 出的 emitter loop 與 main loop 通訊。
///   - notify_one() 為 sync 方法，不需 await，writer 內呼叫成本可忽略。
struct NotifyOnceWriter {
    notify: Arc<tokio::sync::Notify>,
}

#[async_trait]
impl HealthObservationWriter for NotifyOnceWriter {
    async fn write_observation(&self, _row: HealthObservationRow) -> Result<(), M3Error> {
        // 任一 row 寫入即 wake main loop；不關心 row 內容。
        self.notify.notify_one();
        Ok(())
    }

    async fn write_sample_error(
        &self,
        _domain: HealthDomain,
        _metric_name: &str,
        _error: &M3Error,
        _engine_mode: &str,
    ) -> Result<(), M3Error> {
        // bench scenario 不走 sample error path（mock emitter sample() 永 Ok）；
        // 此 method 走 fallback no-op 保 trait 完整。
        Ok(())
    }
}

// ============================================================
// 統計輔助
// ============================================================

/// 取 sorted samples 的 percentile（pct ∈ [0.0, 1.0]）。
fn percentile_ms(sorted: &[u128], pct: f64) -> u128 {
    if sorted.is_empty() {
        return 0;
    }
    let idx = ((sorted.len() - 1) as f64 * pct).round() as usize;
    sorted[idx.min(sorted.len() - 1)]
}

// ============================================================
// Main bench
// ============================================================

fn main() {
    // 為什麼固定 multi_thread + worker_threads=2：
    //   - 跨平台一致避免 default 全核差異污染量測（per spec §7 重點 3）。
    //   - 2 thread 足以承載 main loop + emitter spawn task；不過量也不饑餓。
    let rt = tokio::runtime::Builder::new_multi_thread()
        .worker_threads(2)
        .enable_all()
        .build()
        .expect("tokio runtime build");

    let mut samples_ms: Vec<u128> = Vec::with_capacity(ITER);

    for _ in 0..ITER {
        let elapsed = rt.block_on(async {
            // ----------------------------------------
            // t0 = scheduler 構造前
            // ----------------------------------------
            let t0 = Instant::now();

            // 為什麼每 iter 重建 notify + writer + event_bus：
            //   - cold start 量測語意是「全新 scheduler 從 zero state 到 first
            //     tick」；iter 間共享會把 warm cache 污染給後續 iter，量測偏
            //     向暖啟動而非冷啟動。
            //   - notify wake permit 不跨 iter 殘留（每 iter 新建 Notify
            //     instance）。
            let notify = Arc::new(tokio::sync::Notify::new());
            let writer: Arc<dyn HealthObservationWriter> = Arc::new(NotifyOnceWriter {
                notify: Arc::clone(&notify),
            });
            let event_bus = Arc::new(HealthEventBus::new());

            // 為什麼 6 emitter 對齊 production 6 domain：
            //   - 6 emitter spawn 是 production scheduler 真實負載；少於 6 會
            //     低估 spawn 排程成本。
            //   - 每 emitter 走 MockEmitter（domain 不同但 sample 行為一致），
            //     scheduler 內部 per-domain SM + aggregator HashMap 各自 lazy
            //     建立的成本同樣被量測。
            let emitters: Vec<Box<dyn DomainEmitter>> = (0..6)
                .map(|i| {
                    let domain = match i {
                        0 => HealthDomain::EngineRuntime,
                        1 => HealthDomain::PipelineThroughput,
                        2 => HealthDomain::DatabasePool,
                        3 => HealthDomain::ApiLatency,
                        4 => HealthDomain::StrategyQuality,
                        _ => HealthDomain::RiskEnvelope,
                    };
                    Box::new(MockEmitter { domain }) as Box<dyn DomainEmitter>
                })
                .collect();

            // 為什麼 engine_mode 固定 "paper"：
            //   - per V106 schema CHECK constraint 4 值之一；"paper" 為 bench
            //     最低權限 mode，0 production binary 滲透。
            //   - 不走 "replay" 否則 OBSERVE-4 guard 立即 Err 跳出（per spec
            //     line 595），bench 失去意義。
            //   - to_string() 必須返 String 而非 &str（per
            //     EngineModeProvider = Arc<dyn Fn() -> String + Send + Sync>
            //     簽名）。
            let scheduler = MetricEmitterScheduler::new(
                emitters,
                writer,
                event_bus,
                Arc::new(|| "paper".to_string()),
            );

            let cancel = CancellationToken::new();
            let cancel_for_task = cancel.clone();

            // ----------------------------------------
            // scheduler.run 為 consuming method（self by value）；spawn 走 move
            // ----------------------------------------
            let handle = tokio::spawn(async move {
                // bench scenario 不關心 run 返回 Err；cancel 後正常結束亦 Ok。
                let _ = scheduler.run(cancel_for_task).await;
            });

            // ----------------------------------------
            // 等待第一個 row 寫入觸發 notify
            // ----------------------------------------
            // 為什麼直接 notified().await 不加 timeout：
            //   - bench 預期 < 50ms；若 hang 反映嚴重 regression 應該被看見
            //     (CI 端 cargo bench timeout 會兜底，本 bench 不額外加 layer)。
            //   - 加 tokio::time::timeout 引入額外 select! / Sleep future
            //     構造成本污染量測。
            notify.notified().await;

            let t1 = Instant::now();

            // ----------------------------------------
            // cleanup：cancel + 等 emitter loop 結束
            // ----------------------------------------
            cancel.cancel();
            // 不關心 handle.await 結果；只確保 task 不洩漏到下個 iter。
            let _ = handle.await;

            (t1 - t0).as_millis()
        });
        samples_ms.push(elapsed);
    }

    samples_ms.sort();
    let p50 = percentile_ms(&samples_ms, 0.50);
    let p99 = percentile_ms(&samples_ms, 0.99);
    let mean: u128 = samples_ms.iter().sum::<u128>() / ITER as u128;
    let max = samples_ms.last().copied().unwrap_or(0);

    println!(
        "m3_emitter_cold_start iters={ITER} \
         mean_ms={mean} p50_ms={p50} p99_ms={p99} max_ms={max} \
         budget_ms={BUDGET_MS}"
    );

    // p99 < budget 為 hard assert；mean 與 p50 純報告觀測。
    // 為什麼 assert p99 而非 max：
    //   - max 易受系統 GC / kernel jitter 單次 spike 干擾，p99 對 100 iter
    //     是更穩 SLO 邊界。
    //   - 對齊 hot_path_baseline.rs / intent_processor_exposure.rs report
    //     範式（彼等只 print 不 assert，本 bench 因 AC-7 為 hard budget 而
    //     assert）。
    assert!(
        p99 < BUDGET_MS,
        "AC-7 violation: p99 {p99}ms 超 budget {BUDGET_MS}ms（mean={mean}ms max={max}ms）"
    );
}
