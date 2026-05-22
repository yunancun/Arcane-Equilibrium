---
spec: M3 metric emitter Sprint 2 IMPL phase design
date: 2026-05-22
author: PA (Project Architect)
phase: Sprint 1B (early start design) → Sprint 2 (IMPL)
status: DESIGN-DRAFT
parent specs:
  - srv/docs/execution_plan/2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md
  - srv/docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md
  - srv/docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md
  - srv/docs/adr/0042-m3-health-monitoring.md
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_1a_zeta_pm_phase_3e_signoff.md
spike skeleton ref:
  - srv/rust/openclaw_engine/src/health/mod.rs (563 行；engine_runtime 1 domain + 5 stub `unimplemented!()`)
  - srv/rust/openclaw_engine/tests/m3_amp_cap_24h_fire.rs (269 行；AC-5.1 24h fire empirical)
  - srv/sql/migrations/V106__health_observations.sql (V106 schema land — 6 domain × 4 state hypertable)
scope: design only — 6 domain emitter trait + sampling frequency + 5-sample window aggregation + 4-state ladder + amp cap + write path; **不寫 IMPL code、不改 V106 schema、不修 ADR-0042 / M3 design spec、不 commit、不派下游 sub-agent**
non-scope:
  - cascade IMPL（Sprint 5 Tier 1）
  - alert routing IMPL（Sprint 7 Tier 2）
  - M11 replay divergence integration（Sprint 8）
  - M8 active trigger（Y2+）
  - Monthly Operator Review M3 panel（Sprint 8 A3 GUI）
---

# M3 metric emitter Sprint 2 IMPL phase design

## §0 TL;DR

- spike Track B 已完成 `engine_runtime` 1 domain + 4-state ladder + amp cap 24h Rust skeleton；Sprint 2 IMPL 把 stub 5 domain 補齊 + 5-sample window mean/sigma 聚合 + V106 row 真實寫入。
- 5 並行 Track（pipeline_throughput / database_pool / api_latency / strategy_quality / risk_envelope）；engine_runtime 在 spike Track B 完成不重做（Sprint 2 升級為 mean/sigma window aggregation + V106 writer 真實接線）。
- Phase chain：Phase 1 PA refine（12-18 hr）→ Phase 2 E1 IMPL × 5 並行（30-45 hr）→ Phase 3a/b/c/d/e（12-18 hr）= **60-80 hr 真實工時 + buffer 後 75-100 hr**。
- AC-1..7 對齊 spike scope spec §AC pattern：V106 row 真實寫入 / 4-state ladder 每 domain fire / amp cap 24h fire / cross-domain 不互擾 / production binary 0 mock time 滲透 / cargo + pytest baseline 不退 / binary footprint <50ms cold start。
- Sprint 2 dispatch readiness gate：**PENDING**（待 operator approve Sprint 1B 6 條 early IMPL routing + Phase 1 PA refine cross-check）。
- 治理硬邊界：Sprint 2 emitter **不**觸 cascade（halt strategy / 降 LAL Tier）；emitter 只 emit `HealthStateChangeEvent` 給 event bus，cascade subscribe + 執行延 Sprint 5。

---

## §1 Context

### 1.1 Sprint 1A-ζ Phase 3e PM sign-off carry-over

per PM Phase 3e §4.3 item 1：

> M3 metric emitter Sprint 2 IMPL early start（6 domain × 5 sample window mean/sigma；spike Track B 為 1 domain skeleton）
> Owner: E1 + E2 + E4 · Priority: P0 · 估時: 60-80 hr

per spike scope spec §1.6 / M3 design spec §11.1 / ADR-0042 Decision 3：

| 元素 | spike Track B 狀態 | Sprint 2 IMPL 範圍 |
|---|---|---|
| V106 schema land | DONE（V106__health_observations.sql land；6 domain × 4 state CHECK enforced） | 沿用，無 schema 改動 |
| 4-state ladder Rust enum | DONE（`HealthState` / `HealthDomain` + `from_str`/`as_str` round-trip） | 沿用，無 enum 改動 |
| `engine_runtime` 1 domain SM | DONE（band classify + dwell time OK→WARN 60s + amp cap 24h） | 升級 5-sample window mean/sigma 聚合 + V106 writer 真實接線 + Sprint 5 cascade reject log emit |
| 5 stub domain `unimplemented!()` | spike scope by-design fail-loud | Sprint 2 Track A/B/C/D/E 5 並行補齊 |
| metric emitter sampling task | spike 不接 runtime（test-only `observe_at` 注入 Instant） | Sprint 2 tokio task 每 30s/60s/5min 採樣 |
| V106 row INSERT writer | spike test 純 in-memory | Sprint 2 真實 sqlx INSERT；接 PgPool |

### 1.2 Sprint 2 IMPL 目標

per ADR-0042 + M3 design spec §11.1 Tier 1 active monitoring (Sprint 2 部分)：

1. **6 domain metric emitter 全 IMPL**：每 domain 一個 tokio task；採樣頻率 per M3 spec §2.1（30s / 60s / 5min 分層）
2. **5-sample rolling window mean/sigma 聚合**：對 numeric metric 計算 5 sample window 滑動 mean + sigma（兩 sample sigma fallback per Bessel correction），對 categorical metric（如 heartbeat alive）直接用 boolean。
3. **每 domain 獨立 4-state ladder SM**：6 個 `HealthStateMachine` 實例；system-level state = max(severity)；per ADR-0042 Decision 3 + M3 spec §3.4。
4. **amp cap 24h-suppression 全 domain 套用**：spike Track B 已 IMPL `try_transition_with_cap` 邏輯；Sprint 2 確保 5 個新 domain 共用同一 enforcement path。
5. **V106 row INSERT writer**：每次 state transition fire 寫 1 row；每 sample window emit 也選擇性寫 row（avg `metric_value` + `state` + `amplification_loop_24h_count`）。
6. **production binary 0 mock time 滲透**：`spike` feature flag 嚴守隔絕；Sprint 2 加 `metric_emitter` module 不依賴 `spike` feature。

### 1.3 與 spike Track B 的差別

| 維度 | spike Track B | Sprint 2 IMPL |
|---|---|---|
| Domain 數 | 1 (engine_runtime) + 5 stub | 6 全部 IMPL |
| Sample 入口 | test 注入 Instant via `observe_at` | runtime tokio task 30s/60s/5min cron |
| Window aggregation | 無（每 sample 直接 classify_band） | 5-sample rolling mean/sigma；band classify on aggregated value |
| V106 writer | in-memory only | sqlx INSERT 真實寫入；接 `PgPoolWrapper` |
| Sample source | test fixture struct field | procfs / sysctl / sqlx Pool stats / Bybit client metric / strategy event |
| Cascade trigger | 無 | emit `HealthStateChangeEvent` to event bus；不執行 cascade（Sprint 5 接） |
| Test path | `cargo test --features spike test_m3_amp_cap_24h_fire` | `cargo test` lib 單元 + `cargo test --features integration_pg` 整合（new feature） |

### 1.4 治理硬邊界（Sprint 2 IMPL 不可碰）

- **Cascade IMPL 不在 Sprint 2 範圍**（per spike scope spec §1.6 + M3 spec §11.1 Sprint 5 才接）。Sprint 2 只 emit event，**不**：halt strategy / 降 LAL Tier / disable auto-approve / send Slack alert。
- **HEALTH_CRITICAL action 不在 Sprint 2 範圍**（per ADR-0042 Decision 6 + 5-gate kill 既有 mechanism）。
- **Alert routing 不在 Sprint 2 範圍**（Sprint 7 Tier 2）。spike `spike_trigger.py` 範式僅用於 spike；Sprint 2 emitter 只 V106 audit row INSERT；不 emit Slack / SMS / Console badge。
- **M11 replay divergence integration 不在 Sprint 2 範圍**（Sprint 8）。
- **新 V### 不在 Sprint 2 範圍**。所有 row 寫 V106 既有 schema；不新增 `cascade_event_log` 表（per M3 spec §12.2 Sprint 5 由 MIT 決定是否合入 V106 或新 V###）。

---

## §2 6 Domain split — 5 Track (engine_runtime 沿用)

### 2.1 Domain × Track 對照

per ADR-0042 Decision 3 + M3 design spec §2.1：

| Domain | spike Track B | Sprint 2 Track | Owner | 估時 | Sample 頻率 | Sample 來源 |
|---|---|---|---|---|---|---|
| `engine_runtime` | ✅ DONE skeleton | **沿用 + V106 writer 升級** | E1 (Track A) | 4-6 hr | 30s | spike skeleton + `sysinfo` crate（Sprint 2 新引） / Mac sysctl fallback |
| `pipeline_throughput` | stub | **Track B** | E1 並行 | 6-8 hr | 30s | WS client tick rate + IPC roundtrip latency + IndicatorEngine signal rate |
| `database_pool` | stub | **Track C** | E1 並行 | 6-8 hr | 60s | `PgPool::size()` / `num_idle()` / writer queue depth + `psql -c "SELECT pg_database_size"` for disk |
| `api_latency` | stub | **Track D** | E1 並行 | 6-8 hr | 60s | `bybit_rest_client` p95 latency + retCode counter + WS dropout counter |
| `strategy_quality` | stub | **Track E** | E1 並行 | 8-12 hr | 5min | per-strategy decision_outcomes fills / lease grant rate / signal rate（per-strategy SM = 25 個 SM = 5 strategy × 5 symbol） |
| `risk_envelope` | stub | **Track F** | E1 並行 | 6-8 hr | 5min | portfolio cum_pnl_24h / max_dd / position count / correlation pairwise / top-1 concentration（共用 risk_config 既有 calculation） |

**Sprint 2 共 5 並行 Track（Track B-F）+ Track A 沿用**；wall-clock 3-4 days。

### 2.2 Domain 採樣頻率設計

per M3 spec §2.1：

| 採樣頻率 | Domain | Rationale |
|---|---|---|
| 30s | engine_runtime, pipeline_throughput | 進程級 + 管線級高頻 — WS reconnect / IPC 死鎖 ms 級偵測需要 |
| 60s | database_pool, api_latency | 寫入 backlog / Bybit rate-limit 分鐘級才有意義；避 high-frequency PG self-query overhead |
| 5min | strategy_quality, risk_envelope | 業務級活性慢動指標；strategy dormant > 60min 才升 WARN；portfolio dd 5min 採樣足夠 |

**5-sample rolling window 對齊**：
- 30s × 5 = 2.5min window
- 60s × 5 = 5min window
- 5min × 5 = 25min window

這對齊 M3 spec §3.3 dwell time 設計（OK→WARN 60s dwell 對應 30s × 2 sample；WARN→DEGRADED 5min dwell 對應 30s × 10 sample 或 60s × 5 sample）。

### 2.3 Track 邊界明示

| Track | 涵蓋 | 不涵蓋 |
|---|---|---|
| Track A (engine_runtime 沿用) | spike skeleton 真實接 sysinfo + V106 writer | cascade / alert routing |
| Track B (pipeline_throughput) | WS tick rate + IPC roundtrip + signal rate | WS reconnect 邏輯本身（已存在於 ws_client）；只觀測，不修復 |
| Track C (database_pool) | sqlx Pool stats + writer queue depth + disk usage | 修復寫入 backlog；只觀測 |
| Track D (api_latency) | Bybit REST p95 + retCode + WS dropout count | rate-limit 退避邏輯（已存在於 bybit_rest_client）；只觀測 |
| Track E (strategy_quality) | per-strategy SM 25 個實例 + dormant 計時 + fill rate ratio | M7 DECAY_ENFORCED 觸發（M3 spec §5.1 line 231 Sprint 5 才接） |
| Track F (risk_envelope) | portfolio 級聚合 metric | 5-gate kill threshold 同步（per M3 spec §17.3 D3 Sprint 5 Tier 1 IMPL 前 confirm） |

---

## §3 Emitter trait design

### 3.1 Trait 結構

per M3 spec §2 + spike skeleton 既有 `HealthDomain` enum + `HealthStateMachine`：

```rust
// rust/openclaw_engine/src/health/metric_emitter/mod.rs (新 module)

/// 單一 metric 採樣值。每 domain 自行定義具體 metric struct（per §3.2 per-domain）。
pub trait MetricSample: Clone + Send + Sync + 'static {
    /// 對齊 V106 row column `metric_name`（per-domain CHECK enum）。
    fn metric_name(&self) -> &'static str;
    /// 數值化 metric_value（NUMERIC(18,8)）；非數值 metric 用枚舉 cast。
    fn numeric_value(&self) -> f64;
    /// 當前 sample 立即 classify band（不含 window aggregation；window aggregation
    /// 由 RollingWindowAggregator 集中處理）。
    fn classify_band(&self) -> HealthState;
}

/// Domain emitter trait：每 domain 一個 impl。
#[async_trait::async_trait]
pub trait DomainEmitter: Send + Sync {
    type Sample: MetricSample;

    fn domain(&self) -> HealthDomain;
    fn sample_interval_sec(&self) -> u64;  // 30 / 60 / 300

    /// 採樣入口；emitter 自身負責 OS / sqlx / IPC / event source 拉值。
    /// 失敗回 Err → caller 走 fail-closed（per ADR §六 失敗默認收縮）：
    /// 寫 V106 row state=HEALTH_OK with evidence_json={"sample_error": "..."}
    /// 不升 state，等下次 sample（per V106 spec §1.1 fail-closed 設計）。
    async fn sample(&mut self) -> Result<Self::Sample, M3Error>;
}

/// 5-sample 滑動窗口聚合器；對 numeric metric 計算 mean + sigma。
pub struct RollingWindowAggregator {
    samples: VecDeque<f64>,  // size <= 5
    metric_name: &'static str,
}

impl RollingWindowAggregator {
    pub fn new(metric_name: &'static str) -> Self;
    pub fn push(&mut self, value: f64);
    pub fn mean(&self) -> Option<f64>;
    pub fn sigma(&self) -> Option<f64>;  // n < 2 returns None
    pub fn current_window_size(&self) -> usize;
}

/// Sprint 2 metric emitter scheduler：每 30s/60s/5min tokio task。
pub struct MetricEmitterScheduler {
    domain_emitters: Vec<Box<dyn DomainEmitter<Sample = dyn MetricSample>>>,
    sm_by_domain: HashMap<HealthDomain, Arc<Mutex<HealthStateMachine>>>,
    aggregators: HashMap<(HealthDomain, &'static str), RollingWindowAggregator>,
    v106_writer: Arc<HealthObservationWriter>,
    event_bus: Arc<EventBus>,  // emit HealthStateChangeEvent (Sprint 5 subscribe)
}

impl MetricEmitterScheduler {
    pub async fn run(self, cancel_token: CancellationToken);
}
```

### 3.2 Per-domain Sample struct

**engine_runtime**（spike Track B 既有 `EngineRuntimeMetric` 升級）：

```rust
#[derive(Debug, Clone, Copy)]
pub struct EngineRuntimeSample {
    pub cpu_pct: f64,
    pub rss_mb: f64,
    pub heartbeat_alive: bool,
    pub open_fd_count: u32,        // new in Sprint 2
    pub thread_count: u32,         // new in Sprint 2
    pub uptime_sec: u64,           // new in Sprint 2
}
```

**pipeline_throughput**：

```rust
#[derive(Debug, Clone, Copy)]
pub struct PipelineThroughputSample {
    pub ws_tick_rate_per_sec: f64,
    pub ws_heartbeat_lag_ms: u32,
    pub ws_subscription_drift_count: u32,
    pub strategy_signal_rate_per_min: f64,
    pub ipc_roundtrip_ms_p99: f64,
}
```

**database_pool**：

```rust
#[derive(Debug, Clone, Copy)]
pub struct DatabasePoolSample {
    pub pg_writer_queue_depth: u32,
    pub pg_pool_active_conn: u32,
    pub pg_pool_wait_ms_p95: u32,
    pub disk_data_dir_used_pct: f64,
}
```

**api_latency**：

```rust
#[derive(Debug, Clone, Copy)]
pub struct ApiLatencySample {
    pub bybit_rest_success_rate_5min: f64,
    pub bybit_rest_p95_latency_ms: u32,
    pub bybit_rest_retcode_nonzero_count: u32,
    pub bybit_ws_dropout_count_5min: u32,
    pub bybit_ws_reconnect_count_5min: u32,
}
```

**strategy_quality**（per-strategy variant；每 sample 帶 strategy_name + symbol）：

```rust
#[derive(Debug, Clone)]
pub struct StrategyQualitySample {
    pub strategy_name: String,
    pub symbol: String,
    pub fill_rate_intent_ratio: f64,
    pub slippage_bps_p95: f64,
    pub decision_lease_grant_rate: f64,
    pub dormant_minutes: u32,
    pub signal_count_24h: u32,
}
```

**risk_envelope**：

```rust
#[derive(Debug, Clone, Copy)]
pub struct RiskEnvelopeSample {
    pub portfolio_cum_pnl_24h_usd: f64,
    pub portfolio_max_dd_pct: f64,
    pub position_count_active: u32,
    pub correlation_avg_pairwise: f64,
    pub concentration_top1_pct: f64,
}
```

### 3.3 為什麼 trait + 6 impl 而非 6 個獨立 module

| 設計選項 | 取捨 | PA 推薦 |
|---|---|---|
| (a) 1 trait + 6 impl（per §3.1） | DRY；scheduler 共用；測試 fixture 可 mock | **推薦** |
| (b) 6 個獨立 emitter module + scheduler 直接 dispatch | 顯式但 SchedulerImpl 重複 boilerplate；scheduler 必 case-match 6 domain | 不推薦 |
| (c) 1 個巨型 emitter struct（內含 6 domain）| 模塊邊界喪失；testing 困難 | 不推薦 |

選 (a)。

---

## §4 Sample / window / aggregation design

### 4.1 Sample loop tokio task

每 domain 一個 tokio task（per `sample_interval_sec`）：

```rust
async fn run_domain_loop<E: DomainEmitter>(
    mut emitter: E,
    sm: Arc<Mutex<HealthStateMachine>>,
    aggregators: HashMap<&'static str, RollingWindowAggregator>,
    v106_writer: Arc<HealthObservationWriter>,
    event_bus: Arc<EventBus>,
    cancel_token: CancellationToken,
) {
    let mut interval = tokio::time::interval(
        Duration::from_secs(emitter.sample_interval_sec())
    );
    interval.set_missed_tick_behavior(MissedTickBehavior::Delay);

    loop {
        tokio::select! {
            _ = interval.tick() => {
                let sample = match emitter.sample().await {
                    Ok(s) => s,
                    Err(e) => {
                        // fail-closed: 寫 V106 row state=OK + evidence_json sample_error
                        v106_writer.write_sample_error(emitter.domain(), &e).await;
                        continue;
                    }
                };

                // 1. push window
                let metric_name = sample.metric_name();
                let aggregator = aggregators.get_mut(metric_name).unwrap();
                aggregator.push(sample.numeric_value());

                // 2. classify band on aggregated value (mean if window full)
                let band = if aggregator.current_window_size() < 5 {
                    sample.classify_band()  // not enough samples; classify current
                } else {
                    // classify based on mean of 5-sample window
                    classify_band_from_mean(emitter.domain(), metric_name, aggregator.mean().unwrap())
                };

                // 3. SM observe + amp cap
                let mut sm_guard = sm.lock().await;
                let anomaly_id = format!("{}__{}", emitter.domain().as_str(), metric_name);
                let fire = sm_guard.observe_classified(
                    band,
                    &anomaly_id,
                    Instant::now(),
                ).unwrap_or(false);

                // 4. V106 row INSERT
                v106_writer.write_observation(HealthObservationRow {
                    domain: emitter.domain(),
                    metric_name,
                    state: sm_guard.current_state(),
                    state_prev: if fire { Some(sm_guard.previous_state()) } else { None },
                    metric_value: sample.numeric_value(),
                    amplification_loop_24h_count: sm_guard.amplification_loop_24h_count(),
                    engine_mode: current_engine_mode(),
                    ..Default::default()
                }).await;

                // 5. event bus (Sprint 5 cascade subscribe)
                if fire {
                    event_bus.publish(HealthStateChangeEvent {
                        transition_id: Uuid::new_v4(),
                        domain: emitter.domain(),
                        old_state: sm_guard.previous_state(),
                        new_state: sm_guard.current_state(),
                        timestamp: SystemTime::now(),
                        reason_summary: format!("{} crossed band on 5-sample mean", metric_name),
                    }).await;
                }
            }
            _ = cancel_token.cancelled() => break,
        }
    }
}
```

### 4.2 5-sample rolling window — mean + sigma

對 numeric metric：

```rust
impl RollingWindowAggregator {
    pub fn new(metric_name: &'static str) -> Self {
        Self {
            samples: VecDeque::with_capacity(5),
            metric_name,
        }
    }

    pub fn push(&mut self, value: f64) {
        if self.samples.len() >= 5 {
            self.samples.pop_front();
        }
        self.samples.push_back(value);
    }

    pub fn mean(&self) -> Option<f64> {
        if self.samples.is_empty() {
            return None;
        }
        let sum: f64 = self.samples.iter().sum();
        Some(sum / self.samples.len() as f64)
    }

    /// Bessel-corrected sample sigma（n-1 denominator；n<2 returns None）。
    pub fn sigma(&self) -> Option<f64> {
        if self.samples.len() < 2 {
            return None;
        }
        let mean = self.mean().unwrap();
        let var: f64 = self.samples.iter()
            .map(|v| (v - mean).powi(2))
            .sum::<f64>() / (self.samples.len() - 1) as f64;
        Some(var.sqrt())
    }

    pub fn current_window_size(&self) -> usize {
        self.samples.len()
    }
}
```

**為什麼 Bessel correction（n-1）而非 population sigma（n）**：5-sample 是 sample（不是 population）；Bessel correction 是 sample variance 標準做法。

**為什麼不用 EWMA（exponentially weighted）**：M3 spec §3.3 dwell time 設計是「持續 60s WARN-band」非「指數衰減」；EWMA 跟 dwell time 語意不對齊。5-sample 簡單滑窗對齊 dwell time semantic。

### 4.3 Band classify on aggregated value

```rust
fn classify_band_from_mean(
    domain: HealthDomain,
    metric_name: &'static str,
    aggregated_value: f64,
) -> HealthState {
    match (domain, metric_name) {
        (HealthDomain::EngineRuntime, "cpu_pct") => {
            if aggregated_value < 50.0 { HealthState::HealthOk }
            else if aggregated_value < 80.0 { HealthState::HealthWarn }
            else { HealthState::HealthDegraded }
        }
        (HealthDomain::EngineRuntime, "rss_mb") => {
            if aggregated_value < 2048.0 { HealthState::HealthOk }
            else if aggregated_value < 4096.0 { HealthState::HealthWarn }
            else { HealthState::HealthDegraded }
        }
        // ... 其他 5 domain × multi-metric per ADR-0042 + M3 spec §2.3 + V106 schema
        _ => HealthState::HealthOk,  // unknown metric — fail-closed to OK
    }
}
```

**threshold 來源**：per M3 spec §4.2 + ADR-0042 Decision 4：threshold 由 V106 schema `regime_threshold_table` column 提供（30d block bootstrap 估計 + ArcSwap 熱更新）。Sprint 2 IMPL 先 hardcode threshold（per M3 spec §2.3 ladder 表），threshold dynamic update 延 Sprint 5 Tier 1。

**categorical metric**（如 `heartbeat_alive`）：直接 classify，跳過 window aggregation：
```rust
if !sample.heartbeat_alive { HealthState::HealthCritical }
```

### 4.4 Per-strategy SM variant（strategy_quality）

per M3 design spec §3.4：

```rust
pub struct StrategyQualityScheduler {
    per_strategy_sm: HashMap<(String, String), Arc<Mutex<HealthStateMachine>>>,  // (strategy, symbol)
    aggregate_sm: Arc<Mutex<HealthStateMachine>>,
    // ... 其他與 DomainEmitter 共用
}
```

System-level aggregate rule per M3 spec §3.4：
```
aggregate_state = if (degraded_count / total_count > 0.40) { HEALTH_DEGRADED } else { HEALTH_OK }
```

per-strategy SM 升 HEALTH_DEGRADED 不直接觸發 system-level cascade（per M3 spec §3.4）；emit `StrategyHealthEvent` 給 M7（Sprint 5 接），不直接降 LAL Tier（per ADR-0042 + M3 spec §7.2）。

---

## §5 4-state ladder transition rule — per domain

### 5.1 spike Track B `HealthStateMachine` 升級點

per spike skeleton `health/mod.rs` `try_transition_with_cap`：

**已 IMPL**（spike Track B）：
- OK → WARN dwell time 60s
- amp cap 24h-suppression（same anomaly_id 24h 內 max 1 fire）
- ≥2 fail-closed reject（per V106 spec §1.1 line 77）

**Sprint 2 必補**：
- WARN → DEGRADED 5min dwell time（per M3 spec §3.3）— `try_transition_with_cap` 內加 dwell check
- DEGRADED → CRITICAL 5min dwell time
- WARN → OK 15min recovery（per M3 spec §3.3）
- DEGRADED → WARN 30min recovery
- CRITICAL → DEGRADED 30min recovery + operator manual unlock（spike 不接 operator UI，Sprint 5 Tier 1 + Console GUI 才接）
- flap suppression 24h 內 3 次 lock 至 WARN（per M3 spec §3.3）

### 5.2 New API `observe_classified`

spike Track B 的 `observe` 內含 band classify；Sprint 2 將 classify 移到 emitter scheduler（per §4.1 step 2），SM 只負責 ladder transition 決策：

```rust
impl HealthStateMachine {
    /// Sprint 2 入口：caller 已 classify band，SM 純走 ladder transition。
    pub fn observe_classified(
        &mut self,
        band: HealthState,
        anomaly_id: &str,
        now: Instant,
    ) -> Result<bool, M3Error> {
        self.domain.require_implemented()?;

        // 24h amp cap retain（同 spike Track B）
        let day = Duration::from_secs(24 * 3600);
        self.amp_cap_entries
            .retain(|_, entry| now.duration_since(entry.first_triggered_at) <= day);
        self.amplification_loop_24h_count = self.amp_cap_entries.len() as u32;

        // 完整 ladder transition matrix（Sprint 2 補齊 7 transition）
        let result = match (self.current_state, band) {
            // 升階 4 條
            (OK, WARN) | (OK, DEGRADED) | (OK, CRITICAL) => self.try_upgrade_with_dwell(WARN, anomaly_id, now, Duration::from_secs(60)),
            (WARN, DEGRADED) | (WARN, CRITICAL) => self.try_upgrade_with_dwell(DEGRADED, anomaly_id, now, Duration::from_secs(300)),
            (DEGRADED, CRITICAL) => self.try_upgrade_with_dwell(CRITICAL, anomaly_id, now, Duration::from_secs(300)),
            // 降階 3 條（recovery dwell）
            (WARN, OK) => self.try_recovery_with_dwell(OK, now, Duration::from_secs(900)),  // 15min
            (DEGRADED, OK) | (DEGRADED, WARN) => self.try_recovery_with_dwell(WARN, now, Duration::from_secs(1800)),  // 30min
            (CRITICAL, _) => Ok(false),  // CRITICAL 只能 manual unlock（Sprint 5 Tier 1 + Console GUI）
            // 同 state 不 fire
            _ => Ok(false),
        };

        result
    }

    fn try_upgrade_with_dwell(&mut self, target: HealthState, anomaly_id: &str, now: Instant, dwell: Duration) -> Result<bool, M3Error>;
    fn try_recovery_with_dwell(&mut self, target: HealthState, now: Instant, dwell: Duration) -> Result<bool, M3Error>;
}
```

**backward compat**：spike Track B `observe(metric, anomaly_id)` API 保留（test 仍跑通）；spike test `m3_amp_cap_24h_fire.rs` 不需改。

### 5.3 Cross-domain coordination

per ADR-0042 Decision 3 + M3 spec §3.2 line 128：「system-level state = max(per-domain state)」

```rust
pub fn aggregate_system_state(per_domain_states: &HashMap<HealthDomain, HealthState>) -> HealthState {
    per_domain_states.values()
        .max_by_key(|s| s.severity_value())
        .copied()
        .unwrap_or(HealthState::HealthOk)
}
```

**Sprint 2 IMPL 不 emit system-level state row**；只 emit per-domain row（V106 schema 設計上每 row 都是 per-domain；system-level 是 read-time aggregation by query）。

---

## §6 amp cap per domain

### 6.1 共用 enforcement（不重做）

spike Track B `try_transition_with_cap` 邏輯：
1. Same `anomaly_id` 在 24h cap window 內已 fire → suppress
2. `current_state == target_state` → not a fire
3. `amplification_loop_24h_count >= 2` → fail-closed reject

Sprint 2 6 domain 共用同一 `HealthStateMachine` impl；amp cap 自動繼承。

### 6.2 anomaly_id 命名規約

per spike Track B test：`anomaly_id = format!("{}__{}", domain, metric_name)`

Sprint 2 規約：

| Domain | anomaly_id 例 |
|---|---|
| engine_runtime | `engine_runtime__cpu_pct` / `engine_runtime__rss_mb` |
| pipeline_throughput | `pipeline_throughput__ws_tick_rate_per_sec` / `pipeline_throughput__ipc_roundtrip_ms_p99` |
| database_pool | `database_pool__pg_writer_queue_depth` / `database_pool__pg_pool_wait_ms_p95` |
| api_latency | `api_latency__bybit_rest_success_rate_5min` / `api_latency__bybit_ws_dropout_count_5min` |
| strategy_quality | `strategy_quality__<strategy>__<symbol>__fill_rate_intent_ratio` |
| risk_envelope | `risk_envelope__portfolio_max_dd_pct` / `risk_envelope__concentration_top1_pct` |

每 metric 一個獨立 cap window；同一 domain 不同 metric 不互 cap。

### 6.3 Cross-domain amp cap 不耦合

per M3 spec §6.1 反向 attack mitigation：

```
M8 emit anomaly A → M3 HEALTH_DEGRADED domain X → cascade halt → 觸發 metric 變化
  → M8 emit anomaly B (因 metric 變化) → M3 HEALTH_CRITICAL domain Y → cascade more
```

Sprint 2 amp cap 是 per-anomaly_id (per ADR-0042 Decision 4) — 不同 anomaly_id 獨立計數；同一 domain 不同 metric 也獨立計數。

**但**：Sprint 2 emitter **不**：
- 接收 M8 anomaly event（Y2+ active trigger 才接，per ADR-0042 Decision 2 + M3 spec §11.3）
- 觸發 cascade halt（Sprint 5 才接）

Sprint 2 amp cap 主要功能 = 觀測層去重（避同 metric 持續 fire spam V106 row 5400 row/day）。

---

## §7 AC-1..7

per spike scope spec §4 AC pattern：

| AC# | 描述 | 驗收方式 | Sign-off owner |
|---|---|---|---|
| **AC-1** | V106 6 domain row 真實寫入 — 每 domain 跑 5 sample window 後 emit row（≥1 row per domain per 25min cycle）| `psql -c "SELECT domain, COUNT(*) FROM learning.health_observations WHERE created_at > NOW() - INTERVAL '30 min' GROUP BY domain"` 必 6 row（每 domain count ≥ 1） | QA |
| **AC-2** | 4-state ladder transition fire test — 每 domain 走完 OK → WARN → DEGRADED 至少一次 | `cargo test --release test_sprint2_ladder_<domain>` × 6（每 domain 一個 test）| E4 |
| **AC-3** | amp cap 24h-suppression empirical fire — 至少 2 domain（engine_runtime 沿用 spike + 任 1 新 domain）24h 內第二 fire 真實 suppress | `cargo test --release --features spike test_sprint2_amp_cap_<domain>` × 2；走 mock Instant 跳 24h | E4 + QA |
| **AC-4** | cross-domain coordination 不 conflict — domain A 升 DEGRADED 不影響 domain B 的 state | `cargo test --release test_sprint2_cross_domain_independence`；inject domain A spike + domain B 正常 metric → SM 各自獨立 | E4 |
| **AC-5** | production binary 0 mock time 滲透 — `cargo build --release`（無 `--features spike`）binary `nm` symbol scan 不含 `mock_instant` / `tokio::time::pause` / `spike::*` | `nm target/release/openclaw_engine \| grep -E "(mock_instant\|tokio::time::pause\|spike)" \| wc -l` = 0 | E2 + E4 |
| **AC-6** | cargo test --workspace --release pass + pytest baseline 不退 — Sprint 1A-ζ Phase 3b E4 regression baseline 不退 | `cd srv && cargo test --workspace --release` + `pytest tests/` 0 new fail（28 pre-existing fail per E4 Phase 3b ignored）| E4 |
| **AC-7** | M3 metric emitter binary footprint < 50ms cold start — emitter scheduler `MetricEmitterScheduler::new` + `run` 進入 first tick < 50ms wall-clock | `cargo bench --bench m3_emitter_cold_start` 或 `tokio_console`-style instrumentation | E2 + QA |

### AC-1 verify SQL detail

```sql
SELECT
  domain,
  COUNT(*) AS row_count,
  MAX(observed_at) AS latest_at,
  COUNT(DISTINCT state) AS state_variety
FROM learning.health_observations
WHERE created_at > NOW() - INTERVAL '30 minutes'
  AND engine_mode IN ('paper', 'demo', 'live_demo')  -- spike 階段不寫 live
GROUP BY domain
ORDER BY domain;
-- expect: 6 row（6 domain），每 row count ≥ 5（5-sample window × 6 sample = 30 sample），latest_at < NOW() - INTERVAL '6 minutes'（5min sample 容差）
```

### AC-2 ladder transition test pattern

```rust
#[test]
fn test_sprint2_ladder_engine_runtime() {
    let mut sm = HealthStateMachine::new(HealthDomain::EngineRuntime);
    let now = Instant::now();
    let id = "engine_runtime__cpu_pct";

    // Step 1: OK → WARN (dwell 60s)
    for i in 0..2 {
        sm.observe_classified(HealthState::HealthWarn, id, now + Duration::from_secs(30 * i)).unwrap();
    }
    sm.observe_classified(HealthState::HealthWarn, id, now + Duration::from_secs(60)).unwrap();
    assert_eq!(sm.current_state(), HealthState::HealthWarn);

    // Step 2: WARN → DEGRADED (dwell 5min；同 anomaly_id 受 cap 約束，需新 anomaly_id 或 24h reset)
    let id2 = "engine_runtime__rss_mb";  // 新 anomaly_id 避 cap
    for i in 0..10 {
        sm.observe_classified(HealthState::HealthDegraded, id2, now + Duration::from_secs(60 + 30 * i)).unwrap();
    }
    sm.observe_classified(HealthState::HealthDegraded, id2, now + Duration::from_secs(60 + 5 * 60 + 1)).unwrap();
    assert_eq!(sm.current_state(), HealthState::HealthDegraded);
}
```

### AC-7 binary footprint rationale

per ARCH-04 budget（per spike scope spec §1.6 cold start budget 引用）：M3 emitter 不應拖累 engine cold start；50ms 是 Sprint 2 first IMPL budget（Sprint 5 cascade 加 PostgreSQL writer 後可能升 100ms，到時 reassess）。

---

## §8 Phase chain effort estimate

per Sprint 1A-ζ Phase 0/1/2/3 pattern + spike scope spec §6.1：

### 8.1 Phase 1 — PA refine + 5 dispatch packet

| # | Item | Owner | 估時 |
|---|---|---|---|
| P1-1 | 本 spec cross-check ADR-0042 / M3 design spec / V106 schema 三層對齊 — 確保 Sprint 2 IMPL 不違背任何治理邊界 | PA | 2 hr |
| P1-2 | 5 Track 各 spike feature flag scope 確認 — 確保 production binary 不滲透 mock time（per AC-5）| PA | 2 hr |
| P1-3 | 5 Track sysinfo / sqlx Pool / Bybit client / strategy event 拉值點 確認 — 確保 6 domain 各自 sample 來源真實存在 | PA | 3 hr |
| P1-4 | 5 個 E1 dispatch packet（Track B/C/D/E/F；Track A 沿用）— 含 AC + 必讀 + 反模式 + Disconnect Recovery | PA | 5-8 hr |
| P1-5 | event_bus 接 cascade subscribe schema review — 確保 Sprint 5 cascade IMPL 能 subscribe 而不卡 Sprint 2 emitter | PA | 2 hr |
| P1-6 | per-strategy SM 25 instance memory footprint 評估 — 5 strategy × 5 symbol × `HealthStateMachine` size = ~5KB；25 instance = 125KB；可接受 | PA | 1 hr |

**Phase 1 工時：12-18 hr**

### 8.2 Phase 2 — E1 IMPL × 5 並行

| Track | Domain | E1 Owner | 估時 | Sequential within track |
|---|---|---|---|---|
| Track A | engine_runtime (沿用升級) | E1 (rust E1) | 4-6 hr | sysinfo dep + V106 writer + Sprint 5 reject log emit |
| Track B | pipeline_throughput | E1 並行 | 6-8 hr | WS client stats hook + IPC roundtrip metric + signal rate emitter + SM + V106 writer |
| Track C | database_pool | E1 並行 | 6-8 hr | sqlx Pool stats hook + writer queue depth + disk usage helper + SM + V106 writer |
| Track D | api_latency | E1 並行 | 6-8 hr | bybit_rest_client p95 latency emitter + retCode counter + WS dropout counter + SM + V106 writer |
| Track E | strategy_quality | E1 並行 | 8-12 hr | per-strategy SM 25 instance + dormant 計時 + fill_rate ratio query + 5min sample loop |
| Track F | risk_envelope | E1 並行 | 6-8 hr | portfolio calculation 共用 risk_config + correlation pairwise + top-1 concentration + SM + V106 writer |

**Phase 2 工時：36-50 hr 並行；wall-clock 3-4 days**

per `feedback_subagent_first` + `feedback_fetch_before_dispatch`：5 並行 + Track A sequential 升級 = 6 sub-agent 總（5 並行 + Track A single）；不撞 7 sub-agent ceiling。

### 8.3 Phase 3a/b/c/d/e — review + regression + empirical + report + sign-off

per `feedback_impl_done_adversarial_review` 強制：

| # | Item | Owner | 估時 |
|---|---|---|---|
| P3a-1 | E2 對抗 review × 6 domain（spike skeleton 升級 + 5 new domain）並行 | E2 × 5（並行 sub-agent）| 10-15 hr 並行 |
| P3a-2 | A3 GUI review — 確認 Sprint 2 IMPL 0 GUI 改動（Console badge 走 Sprint 8 A3 monthly review panel）— skip 若 PA Phase 1 確認 0 GUI | A3 | 1 hr |
| P3b-1 | E4 regression（pytest baseline 不退 + cargo test --workspace --release pass）| E4 | 4-6 hr |
| P3b-2 | E4 cross-language fixture 升級 — Sprint 1B AC-7 H-18 fixture harness 全套（Rust binding 落地）若 Sprint 1B 已 land，本 Sprint 2 不重做 | E4 | conditional 0 or 4 hr |
| P3c-1 | QA empirical verify — AC-1 SQL query / AC-2 ladder fire test / AC-3 amp cap fire / AC-4 cross-domain independence / AC-5 binary nm scan / AC-7 cold start measure | QA | 4-6 hr |
| P3d-1 | TW Sprint 2 Acceptance Report — 6 domain emitter PASS/FAIL + carry-over + Lessons Learned | TW | 2-3 hr |
| P3e-1 | PM sign-off + Sprint 5 cascade IMPL 派發 readiness gate verdict | PM | 1-2 hr |

**Phase 3 工時：22-33 hr**

### 8.4 Total Sprint 2 budget

```
Phase 1 PA refine:    12-18 hr (single-thread)
Phase 2 E1 × 5 並行:  36-50 hr (3-4 days wall-clock)
Phase 3a E2 × 5 並行: 10-15 hr (1 day wall-clock)
Phase 3a A3:          1 hr (skip if 0 GUI)
Phase 3b E4:          4-6 hr
Phase 3b E4 H-18:     conditional 0-4 hr
Phase 3c QA:          4-6 hr
Phase 3d TW:          2-3 hr
Phase 3e PM:          1-2 hr
─────────────────────
Real workload:        70-104 hr 真實
With buffer:          75-115 hr 含 buffer + scope expansion 餘量
Wall-clock:           1-1.5 week (D0-D7)
```

**對比 PM Phase 3e §4.3 估時 60-80 hr**：PA design 估時 70-104 hr 真實，含 5 Track 並行 E1 + 完整 Phase 3 chain；PM 估時偏低（可能未 buffer Phase 3 review chain）。**PA 推薦調整 Sprint 2 budget 為 75-100 hr**（含 buffer + Phase 1/3 完整 chain）。

### 8.5 Sequential dependency within Phase 2

per spike scope spec §3.2 Sequential constraint pattern：

```
Phase 2 Track 順序：
  Track A 升級先（spike skeleton 已存，V106 writer 是 5 並行 Track 共用 dep）
    └─ Track A 完成 V106 writer + event bus 接線 後
       Track B/C/D/E/F 5 並行（共用 V106 writer + event bus）

Cross-Track constraint:
  V106 writer trait 必先 land (Track A 升級) → 5 並行 Track 才能寫
  event bus emit pattern 必先 land (Track A 升級) → 5 並行 Track 才能 publish
  HealthStateMachine `observe_classified` 新 API 必先 land (Track A 升級) → 5 並行 Track 才能呼叫
```

**Wall-clock 順序**：
- D0: Phase 1 PA refine (12-18 hr / single-thread)
- D1: Track A 升級（4-6 hr / 含 V106 writer trait + event bus emit pattern + `observe_classified` API）
- D1.5 - D4: Track B/C/D/E/F 5 並行（36-50 hr 並行 / 3-4 days）
- D5: Phase 3a E2 × 5 並行 review (10-15 hr / 1 day)
- D6: Phase 3b E4 + Phase 3c QA（4-6 + 4-6 hr / 0.5 + 0.5 day）
- D7: Phase 3d TW + Phase 3e PM sign-off（2-3 + 1-2 hr / 0.5 day）

**合計 wall-clock：1-1.5 week**

---

## §9 Dispatch readiness gate

### 9.1 Gate status：**PENDING**

理由：
1. **Sprint 1B 6 條 early IMPL 整體 routing 未經 operator approve**（per PM Phase 3e §4.3 列為 candidate 但未派發）
2. **Phase 1 PA refine 6 條 cross-check 未跑**（本 spec land 後才能跑 Phase 1）
3. **Sprint 1A-ε P1 7 條 carry-over 應先收口**（per PM Phase 3e §4.2；sandbox_admin role / 5 PA spec literal patch / TW docs index sweep / V107 §4.2 對齊 / Sprint 5 cascade reject log emit / NEW-QA-1/2/3）— 否則 Sprint 2 Phase 1 cross-check 會撞 spec literal drift

### 9.2 OPEN 條件

以下全部滿足才開派 Sprint 2 IMPL：

- [ ] operator approve PM Phase 3e §4.3 Sprint 1B 6 條 early IMPL 整體派發（含 Item 1 M3 metric emitter Sprint 2 IMPL）
- [ ] Sprint 1A-ε P1 carry-over 7 條 land（per Phase 3e §4.2；含 sandbox_admin / 5 spec patch / docs index / V107 §4.2 註腳 / Sprint 5 reject log emit ticket）
- [ ] 本 spec PA Phase 1 refine 12-18 hr DONE（含 ADR / M3 spec / V106 schema 三層對齊驗 + 5 Track dispatch packet）
- [ ] 5 Track 之間 cross-dep 確認（V106 writer trait + event bus + `observe_classified` API 必 Track A 先 land；5 並行 Track 不撞 race）
- [ ] sandbox_admin role 創建（per Sprint 1A-ε P1 item 1）— 否則 AC-1 SQL query 跑不通

### 9.3 NEEDS_OPERATOR

以下 3 決策需 operator 顯式 sign-off：

| # | Decision | Options | PA 推薦 |
|---|---|---|---|
| **D1** | sysinfo crate 引入 vs 自寫 procfs/sysctl helper（per Track A 升級）| (a) sysinfo crate ~80kb / Mac+Linux 跨平台原生支援 / 14 transitive dep (b) 自寫 procfs (Linux) + sysctl (Mac) ~200 行 / 0 new dep / 平台分支 cfg(target_os) | **(a) sysinfo**：跨平台原生 + Mac 部署目標（per `project_mac_deployment_target` memory）；14 transitive dep 可接受（已有 `tokio` workspace 帶 100+ dep） |
| **D2** | Sprint 2 IMPL 是否並行 Sprint 1B 其他 5 條 early IMPL（per PM Phase 3e §4.3 item 1-6）| (a) Sprint 2 IMPL single-thread（不並行 1B 其他）— 嚴守 7 sub-agent ceiling；wall-clock +1-1.5 week (b) Sprint 2 IMPL 與 1B 其他並行 — 5+5+5+QA+TW+PM = 18 sub-agent；遠超 7 ceiling | **(a) single-thread Sprint 2 within 1B**：Sprint 2 IMPL 已是 5 Track 並行 + Phase 3a E2 × 5 並行 = 共 6 sub-agent peak；不能再疊其他 1B item；其他 5 條（M11 V107 re-apply / 28 pytest fail / AC-7 H-18 / Sprint 5 cascade reject / M11 dedup c5）走 Sprint 2 之前或之後串 |
| **D3** | Sprint 2 IMPL 是否預先包含 Sprint 5 cascade reject log emit（per PM Phase 3e §4.3 item 5）| (a) Sprint 2 IMPL 只 emit `HealthStateChangeEvent` 給 event bus，cascade subscribe + reject log emit 留 Sprint 5（per M3 spec §11.1）(b) Sprint 2 IMPL 含 reject log emit minimal IMPL（V106 row write fail-closed `≥2` reject 場景留 audit trail）| **(b) Sprint 2 含 minimal reject log**：spike Track B E2 round 1 LOW-2 + Track B round 2 1 new LOW 已 catch 此 gap；Sprint 2 補 `≥2` reject 場景的 V106 row INSERT（state 維持 + `evidence_json={"reject_reason": "amp_cap_>=2_fail_closed"}`）；不接 Slack alert / Console badge（Sprint 7 + 8 才接）。極小 IMPL cost (~2 hr E1) + 避免 Sprint 5 才補的 audit gap。|

---

## §10 §二 16 根原則合規確認

per `srv/docs/decisions/DOC-01_..._V2.md` §5.1-§5.16（DOC-01 V2 為真 SSOT）+ 16-root-principles-checklist skill：

| # | 原則 | 是否相容 | Sprint 2 IMPL 對應 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | M3 emitter 不創 order 寫入口；V106 row INSERT 走既有 `HealthObservationWriter` |
| 2 | 讀寫分離 | ✅ | emitter 只讀 metric + 寫 V106 audit row；不寫 trading state |
| 3 | AI ≠ 命令 | ✅ | M3 emitter 不涉 AI；state 計算純規則；event emit 不繞 Decision Lease |
| **4** | **策略不繞風控** | ✅ | M3 emitter 不創新 lease 旁路；event bus emit 不繞 Guardian；cascade 走 Sprint 5 才接，依然走 5-gate kill mechanism |
| 5 | 生存 > 利潤 | ✅ | fail-closed default：sample error → 寫 V106 state=OK + evidence_json sample_error；不假設 metric OK |
| 6 | 失敗默認收縮 | ✅ | amp cap `≥2` fail-closed reject；sample error fail-closed；event emit fail-soft（emit 失敗不阻 V106 write） |
| 7 | 學習 ≠ live | ✅ | M3 emitter 只寫 V106 audit row；不寫 live trading state |
| 8 | 交易可解釋 | ✅ | V106 row 含 metric_name / state / state_prev / dwell_time_sec / amplification_loop_24h_count / evidence_json — audit reconstruct 可行 |
| 9 | 雙重防線 | ✅ | M3 emitter 不替代 5-gate kill 或 Bybit conditional order；只增 operational degradation 觀測層 |
| 10 | 事實 / 推論 / 假設 | ✅ | metric 數值 = 事實；state classify = 推論（per threshold）；amp cap 設計 = 假設待 Sprint 5 cascade IMPL 驗 |
| 11 | P0/P1 內自主 | ✅ | M3 emitter SM 自主升降 state；不擴 P0/P1 邊界 |
| 12 | evidence-based | ✅ | 5-sample window + Bessel sigma 對齊 statistical 標準；threshold 走 30d block bootstrap（per ADR-0042 + V106 spec）|
| **13** | **cost 感知** | ✅ | sampling 30s/60s/5min 分層；不在 trading hot path；M3 IPC overhead 估計 <1MB RSS / <0.5% CPU |
| 14 | 零外部成本 | ✅ | sysinfo crate / sqlx / Bybit client 全 self-hosted；無 vendor 依賴 |
| 15 | 多 agent 形式化 | ✅ | 5 並行 E1 + 5 並行 E2 + 1 E4 + 1 QA + 1 TW + 1 PM 走形式化 chain；event bus emit pattern 為 M7 / Sprint 5 cascade / Sprint 8 GUI 預埋接口 |
| **16** | **portfolio > 孤立** | ✅ | `risk_envelope` domain 是 portfolio-level 聚合（cum_pnl / dd / correlation / concentration）；對齊原則 16 |

**0 BLOCKER；0 硬邊界觸碰；Approve READY pending Phase 1 PA refine + operator sign-off Sprint 1B 派發**。

---

## §11 Cross-References

- **Sprint 1A-ζ Phase 3e PM sign-off**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_1a_zeta_pm_phase_3e_signoff.md` §4.3 item 1
- **M3 design spec**：`docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md`（648 行）
- **V106 schema spec**：`docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md`（1087 行）
- **V106 SQL migration**：`sql/migrations/V106__health_observations.sql`（land）
- **ADR-0042 M3 health monitoring**：`docs/adr/0042-m3-health-monitoring.md`（7 decision + 16 原則合規）
- **spike Track B IMPL**：`rust/openclaw_engine/src/health/mod.rs`（563 行 skeleton）+ `tests/m3_amp_cap_24h_fire.rs`（269 行 AC-5.1 fire test）
- **spike scope spec**：`docs/execution_plan/2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md`（spike AC pattern + Phase chain 範式）
- **ADR-0036 M8 anomaly**：`docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md`（amp cap signature source；Y2+ active trigger 才接）
- **ADR-0034 M1 LAL**：`docs/adr/0034-decision-lease-layered-approval-lal.md`（M3 HEALTH_DEGRADED → LAL Tier 降階；Sprint 5 才接）
- **`feedback_cross_platform` memory**：sysinfo Mac+Linux 跨平台原生支援；Mac 部署目標永遠 ready
- **`feedback_subagent_first` + `feedback_fetch_before_dispatch` memory**：5 並行 Track + Track A 升級 = 6 sub-agent peak；不撞 7 ceiling
- **`project_first_detection_deadlock_pattern` memory**：M3 state lock 機制必有過期條件；spike Track B 已 IMPL retain 24h；Sprint 2 沿用
- **`feedback_no_dead_params` memory**：M3 所有 threshold 必真實被 healthcheck 使用 + V106 audit row 真實 INSERT；不允許 placeholder threshold 不接入 SM
- **PM Phase 3e §4.3 item 5**：Sprint 5 cascade IMPL 補 ≥ 2 reject direct unit test 覆蓋（spike Track B E2 round 1 LOW-2 + Track B round 2 1 new LOW；本 Sprint 2 §9.3 D3 收 minimal scope）

---

**END M3 metric emitter Sprint 2 IMPL phase design**

*OpenClaw / Arcane Equilibrium — Sprint 2 IMPL design only — 5 並行 Track (pipeline_throughput / database_pool / api_latency / strategy_quality / risk_envelope) + Track A 沿用 (engine_runtime spike skeleton 升級) — 5-sample rolling window mean/sigma + Bessel sigma + 4-state ladder + amp cap 24h-suppression + V106 row INSERT writer — 0 IMPL code / 0 V### change / 0 ADR amend / 0 commit*
