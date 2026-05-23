---
spec: Sprint 5+ Wave 1 §4.3.2 — AC-7 m3_emitter_cold_start cargo bench fixture
date: 2026-05-23
author: PA
parent: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--stage_a_to_e_overall_acceptance.md §8.5 item 2
parent_ac_source: srv/docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md §AC-7 (line 841)
risk_grade: 低
status: SPEC-DRAFT
---

# §1 範疇校正 + push back

operator prompt 對本 item 描述「Linux x86_64 Rust binding bit-perfect AC-7」**錯誤**，與 SSOT 不符：

| 名稱 | SSOT 出處 | 語意 | 狀態 |
|---|---|---|---|
| **Sprint 1B AC-7 cross-language fixture** | `2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md` §AC-7 + `2026-05-22--sprint_2_phase_3b_regression.md` §4.2 | Rust↔Python `compute_window_stats` mean/sigma 1e-4 容差（spike feature gate；subprocess + JSON marker） | **FULL PASS** Mac aarch64 5/5（commit `9cf0fe82`）；無 Linux x86_64 deploy 依賴 |
| **Sprint 2 AC-7 cold start bench**（本 spec 範疇）| `2026-05-22--m3_metric_emitter_sprint2_design_spec.md` §AC-7 line 841 | `MetricEmitterScheduler::new` + `run` first tick wall-clock < 50ms | **PENDING IMPL** — `benches/m3_emitter_cold_start.rs` 0 文件存在 |

§8.5 carry-over item 2 = **後者**（cold start bench）。本 spec 走 Sprint 2 AC-7 SSOT。

---

# §2 IMPL 範疇

新建 `rust/openclaw_engine/benches/m3_emitter_cold_start.rs` — plain `fn main()` + 手動 `Instant` 計時（對齊既有 `hot_path_baseline.rs` + `intent_processor_exposure.rs` 範式；**0 criterion dev-dep**）。

## §2.1 量測對象

`MetricEmitterScheduler::new(emitters, writer, event_bus, engine_mode_provider)` + `run(cancel_token)` 進入 **first tick** 的 wall-clock 時間。

per `health/metric_emitter/mod.rs` line 590-633：
- `new`：構造 6 emitter Vec + Arc clone
- `run`：spawn 6 tokio task（`run_domain_loop`） + interval tick 等
- **first tick = 第一個 emitter 的 `interval.tick()` 真實 fire** — 即 `sample()` 第一次被呼叫

## §2.2 量測語意

```
t0 = Instant::now()
scheduler = MetricEmitterScheduler::new(...)   // build phase
handle = tokio::spawn(scheduler.run(cancel))   // spawn phase
first_sample_signal.notified().await           // wait first sample fire
t1 = Instant::now()
elapsed_ms = (t1 - t0).as_millis()             // 必 < 50ms
```

實裝走 `Arc<tokio::sync::Notify>` 注入「測試專用 writer」，writer 收到第一 row 時 `notify_one()`。

## §2.3 6 emitter 構造

走 mock emitter（lightweight；不引 sysinfo / sqlx / WS / portfolio cache 真實構造避量測污染）：
- 6 個 `MockColdStartEmitter`，`sample_interval_sec()` 返 1（最短合法值）
- `sample()` 返 1 個 `MockMetricSample { name="cold_start_probe", value=1.0, band=HealthOk }`
- mock writer 收到 row 後 `notify.notify_one()`

理由：cold start budget 量測「scheduler 自身啟動成本」，**非** 6 個真實 emitter 採樣成本（後者由 production observe 量測；per spec line 887「Sprint 5 cascade 加 PG writer 後重 assess 100ms」）。

---

# §3 AC 矩陣（4 條）

| AC# | 描述 | 驗收方式 | Owner |
|---|---|---|---|
| **AC-1** | bench file 新建 + cargo bench 可跑 | `cd srv && cargo bench --bench m3_emitter_cold_start --no-run` clean | E1 / E4 |
| **AC-2** | first tick < 50ms（Mac aarch64 + Linux x86_64 均驗）| 跑 100 iter，mean + p99 < 50ms；Mac+Linux 各跑一次寫入 bench output | E4 |
| **AC-3** | 0 criterion dep 引入 | `cargo tree -p openclaw_engine \| grep criterion` 0 hit | E2 |
| **AC-4** | Cargo.toml `[[bench]]` entry 新增 | `grep "m3_emitter_cold_start" rust/openclaw_engine/Cargo.toml` ≥ 1 hit | E2 |

## §3.1 Linux x86_64 驗法

bench 跑 Mac aarch64 後，**復跑** Linux x86_64：
```
ssh trade-core "cd ~/TradeBot/srv && source ~/.cargo/env && cargo bench --bench m3_emitter_cold_start 2>&1 | tail -20"
```

per `feedback_restart_bind_host_default` + `project_dev_runtime_split` — Mac 是 dev，Linux 是 runtime；bench p99 容差語意「兩平台均應 < 50ms」（Linux x86_64 通常更快）。

---

# §4 副作用清單（PA 評估）

1. **不改動 production code path** — bench 走 mock writer + mock emitter，0 production binary 滲透
2. **0 criterion dev-dep** — 沿用既有 `benches/` plain main 範式，避新增 build 複雜度
3. **不涉 Spike feature gate** — bench 是 release/debug 通用 fixture，不需 spike feature
4. **0 GUI / API / DB 變更** — bench 是純 Rust performance 量測

## §4.1 硬邊界檢查（16 根原則）

| # | 原則 | 觸碰 | 證據 |
|---|---|---|---|
| 1-9 | trading hard rails | ✗ 不觸碰 | bench 0 production code path |
| 10 | 認知誠實 | ✓ 對齊 | mock writer 標記為 mock，bench output 明標 cold_start 語意 |
| 14 | 零外部成本可運行 | ✓ 對齊 | 0 dep 新增 |

無 BLOCKER；A 級合規。

---

# §5 LOC + 工時估算

| Item | LOC | 估時 |
|---|---|---|
| `benches/m3_emitter_cold_start.rs` 新檔 | ~150 LOC（含 MockEmitter + MockWriter + main loop） | 2-3 hr E1 |
| `Cargo.toml` `[[bench]]` entry 新增 | 4 LOC | 5 min E1 |
| Mac+Linux 各 1 次跑 bench + output 記錄 | 0 LOC | 30 min E4 |
| **Total** | **~155 LOC** | **3-4 hr** |

---

# §6 E1 IMPL 指示

## §6.1 文件清單

- `rust/openclaw_engine/benches/m3_emitter_cold_start.rs`（新檔）
- `rust/openclaw_engine/Cargo.toml`（+ `[[bench]]` entry）

## §6.2 MockEmitter 範本

```rust
//! AC-7 m3 emitter cold start bench — first tick wall-clock < 50ms。
//!
//! 跑：cargo bench -p openclaw_engine --bench m3_emitter_cold_start
//! Compile only：cargo bench --bench m3_emitter_cold_start --no-run

use std::sync::Arc;
use std::time::Instant;

use async_trait::async_trait;
use openclaw_engine::health::metric_emitter::{
    DomainEmitter, MetricEmitterScheduler, MetricSample,
};
use openclaw_engine::health::{HealthDomain, HealthState, M3Error};
use openclaw_engine::health::event_bus::HealthEventBus;
use openclaw_engine::health::writer::HealthObservationWriter;
use tokio_util::sync::CancellationToken;

const ITER: usize = 100;
const BUDGET_MS: u128 = 50;

struct MockSample;
impl MetricSample for MockSample {
    fn metric_name(&self) -> &'static str { "cold_start_probe" }
    fn numeric_value(&self) -> f64 { 1.0 }
    fn classify_band(&self) -> HealthState { HealthState::HealthOk }
}

struct MockEmitter { domain: HealthDomain }
#[async_trait]
impl DomainEmitter for MockEmitter {
    fn domain(&self) -> HealthDomain { self.domain }
    fn sample_interval_sec(&self) -> u64 { 1 }
    async fn sample(&mut self) -> Result<Vec<Box<dyn MetricSample>>, M3Error> {
        Ok(vec![Box::new(MockSample)])
    }
}

struct NotifyOnceWriter { notify: Arc<tokio::sync::Notify> }
#[async_trait::async_trait]
impl HealthObservationWriter for NotifyOnceWriter {
    async fn write_observation(&self, _row: openclaw_engine::health::writer::HealthObservationRow) -> Result<(), M3Error> {
        self.notify.notify_one();
        Ok(())
    }
    async fn write_sample_error(&self, _domain: HealthDomain, _err: &M3Error, _engine_mode: &str) -> Result<(), M3Error> {
        Ok(())
    }
}

fn main() {
    let rt = tokio::runtime::Builder::new_multi_thread()
        .worker_threads(2)
        .enable_all()
        .build()
        .unwrap();

    let mut samples_ms = Vec::with_capacity(ITER);
    for _ in 0..ITER {
        let elapsed = rt.block_on(async {
            let t0 = Instant::now();
            let notify = Arc::new(tokio::sync::Notify::new());
            let writer = Arc::new(NotifyOnceWriter { notify: Arc::clone(&notify) });
            let event_bus = Arc::new(HealthEventBus::new());
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
            let scheduler = MetricEmitterScheduler::new(
                emitters, writer, event_bus, Arc::new(|| "paper"),
            );
            let cancel = CancellationToken::new();
            let cancel_for_task = cancel.clone();
            let handle = tokio::spawn(async move {
                let _ = scheduler.run(cancel_for_task).await;
            });
            notify.notified().await;
            let t1 = Instant::now();
            cancel.cancel();
            let _ = handle.await;
            (t1 - t0).as_millis()
        });
        samples_ms.push(elapsed);
    }

    samples_ms.sort();
    let p50 = samples_ms[ITER / 2];
    let p99 = samples_ms[(ITER * 99) / 100];
    let mean = samples_ms.iter().sum::<u128>() / ITER as u128;
    println!("m3_emitter_cold_start mean={mean}ms p50={p50}ms p99={p99}ms budget={BUDGET_MS}ms");
    assert!(p99 < BUDGET_MS, "p99 {p99}ms 超 budget {BUDGET_MS}ms");
}
```

## §6.3 Cargo.toml entry

```toml
[[bench]]
name = "m3_emitter_cold_start"
harness = false
```

---

# §7 E2 重點審查 3 條

1. **bench 計時邊界**：`t0` 必在 scheduler `new` 前；`t1` 必在 writer notify 收到後（即第一 row 寫完）。avoid race：`tokio::spawn` 返回後立即 `notified().await`
2. **mock writer 不漏 notify**：6 emitter spawn 順序 + interval 1s tick — 確認 mock writer 在「任一 emitter 第一 sample」即 notify（避免錯算成 6 sample 全完）。實裝走 `notify_one()` 而非 `notify_waiters()`，semantically 任一 emitter 首 sample 即收
3. **Mac vs Linux 一致性**：兩平台 p99 < 50ms；若 Linux 端 fail Mac PASS，懷疑 tokio scheduler 平台差異或 mpsc channel 排程；走 `tokio::runtime::Builder` `worker_threads=2` 固定避免 default 全核差異

---

# §8 Dispatch readiness

**READY** — 0 前置阻塞；E1 IMPL 可立即派；風險 低（純 bench fixture，0 production code 滲透）。
