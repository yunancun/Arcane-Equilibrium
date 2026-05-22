---
spec: M3 metric emitter Sprint 2 Phase 2 E1 Dispatch Packet
date: 2026-05-22
author: PA (Project Architect)
status: READY-TO-DISPATCH
parent: docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md
spec D1/D2/D3 sign-off: operator 2026-05-22
phase chain: Phase 1 (本 packet) → Phase 2 E1 × 6 並行 Wave 1+2 → Phase 3a E2 × 6 並行 → Phase 3b E4 → Phase 3c QA → Phase 3d TW → Phase 3e PM sign-off
scope: 6 Track E1 dispatch packet 撰寫 + Wave 拆分 + Phase chain 路徑；非 IMPL；非 commit；非派下游 sub-agent
out-of-scope:
  - V### IMPL SQL（Sprint 2 emitter 不新增 V###；V106 schema 已 land）
  - Rust IMPL code（Phase 2 E1 工作）
  - cascade IMPL（Sprint 5；D3 Sprint 2 含 minimal reject log emit only）
  - alert routing（Sprint 7 Tier 2）
  - M11 replay divergence integration（Sprint 8）
---

# M3 metric emitter Sprint 2 Phase 2 E1 Dispatch Packet

## §0 TL;DR

per Sprint 1A-ζ Phase 1 PA refine pattern (`docs/execution_plan/2026-05-21--sprint_1a_zeta_3_e1_dispatch_packet.md`)：

- 6 Track 各 prerequisite check + dispatch packet（E1 prompt skeleton / AC sub-step / file path scope / 反模式 / Disconnect Recovery）
- Wave 1 (D0-D3)：Track A + B + C 3 並行；Track A 24h 內 land scaffold (trait + writer + event bus + observe_classified)
- Wave 2 (D3-D6)：Track D + E + F 3 並行；用 Wave 1 已 land scaffold
- Phase chain：本 packet (~2-3 hr) → Phase 2 E1 × 6 並行 (38-52 hr) → Phase 3a E2 × 6 並行 (10-15 hr) → Phase 3b E4 (4-6 hr) → Phase 3c QA (4-6 hr) → Phase 3d TW (2-3 hr) → Phase 3e PM (1-2 hr) = **70-104 hr 真實 + buffer 後 75-115 hr**

---

## §1 Pre-dispatch Common Prerequisite Check (PA Phase 1)

### 1.1 Spec D1/D2/D3 operator sign-off 已 land

| # | Decision | Verdict | 證據 |
|---|---|---|---|
| D1 | sysinfo crate adopted (a) | YES | parent spec §3 D1 |
| D2 | 並行 with Sprint 1B mid items | YES (operator override PA 推 single-thread) | parent spec §3 D2 |
| D3 | Sprint 5 cascade reject log emit minimal IMPL 包含於 Track A | YES (~2 hr E1 cost) | parent spec §3 D3 |

### 1.2 Sprint 1B mid 3 NEW carry-over file scope conflict

| Sprint 1B mid item | File scope | Sprint 2 Track 重疊 |
|---|---|---|
| PA-DRIFT-1 governance.audit_log alignment | `docs/execution_plan/*` / `sql/migrations/V###` audit_log | 0 overlap (Sprint 2 寫 learning.health_observations only) |
| PA-DRIFT-2 V103 file HARD BLOCKER | `sql/migrations/V103__*.sql` | 0 overlap (Sprint 2 不碰 V103) |
| E3-MED-2 sandbox_admin hypertable OWNER | sandbox PG GRANT + TimescaleDB hypertable owner | 時序依賴 (Phase 3c 起跑前必 closed) |

### 1.3 Sub-agent ceiling 預警

- Wave 1 dispatch 階段：Sprint 2 3 並行 + Sprint 1B mid 3 carry-over 並行峰值 = 6-7 sub-agent peak（嚴守 stagger 5min + 不接受第 4 個並行請求）
- Wave 2 dispatch 階段：Sprint 1B mid 預期已 DONE；Sprint 2 3 並行 = 4 sub-agent peak（healthy 餘量 3）

### 1.4 V### 依賴

- V106__health_observations.sql 已 land (sprint 1A-ζ Track B closure)
- Sprint 2 emitter **不**新增 V###（per parent spec §1.4）；所有 row 寫 V106 既有 schema

### 1.5 Rust trait stub 沿用

- spike Track B 已 land `rust/openclaw_engine/src/health/mod.rs` (718 行 + spike test 269 行)
- `HealthState` enum + `HealthDomain` enum + `M3Error` + `HealthStateMachine` + `EngineRuntimeMetric` + `try_transition_with_cap` + `compute_window_stats` 全 land
- Sprint 2 Track A 升級：新增 `DomainEmitter` trait + `MetricSample` trait + `RollingWindowAggregator` + `HealthObservationWriter` trait + `MetricEmitterScheduler` + `observe_classified` SM 新入口 + D3 cascade reject emit

### 1.6 Cargo dep + sysinfo crate version pick

- workspace `rust/Cargo.toml` 加 `sysinfo = "0.32"` (latest stable as of 2026-05；Track A E1 IMPL 動工前 confirm crates.io 最新 stable 不破壞 MSRV)
- `rust/openclaw_engine/Cargo.toml` 加 `sysinfo = { workspace = true }`
- 0 其他新 dep（sqlx / tokio / chrono / uuid / serde 全 workspace 已有）

### 1.7 Wave 1 scaffold contract (Track A 必先 land)

| Scaffold item | Owner Track | 預估 LOC |
|---|---|---|
| `DomainEmitter` trait + `MetricSample` trait | Track A | ~50 LOC |
| `RollingWindowAggregator` (Bessel sigma) | Track A | ~70 LOC |
| `HealthObservationWriter` trait + V106 INSERT 接 PgPool | Track A | ~120 LOC |
| `event_bus` emit pattern + `HealthStateChangeEvent` | Track A | ~80 LOC |
| `observe_classified` SM 新入口 (參考 parent spec §5.2) | Track A | ~60 LOC |
| `sysinfo::System` 接 `EngineRuntimeSample` | Track A | ~80 LOC |
| D3 cascade reject log emit minimal | Track A | ~40 LOC |
| **Track A 升級總計** | **Track A** | **~500 LOC + V106 writer wire-up** |

Track B/C/D/E/F 用上述 scaffold；各 Track 不重做 trait + writer + event bus。

---

## §2 Track A: engine_runtime (基線升級;含 cascade reject log minimal IMPL per D3)

### 2.1 Prerequisite

- spike Track B 已 land `health/mod.rs` 718 行 baseline
- workspace `sysinfo = "0.32"` 加 dep
- V106 schema land + sandbox 可 INSERT

### 2.2 E1 prompt skeleton (PM 派 prompt 用)

**Subagent role**: E1 (Engineer 1; Rust 主)；high-risk IMPL per `feedback_impl_done_adversarial_review` Phase 3a E2 強制對抗 review

**Working branch**: `feature/sprint_2_track_a_engine_runtime`

**Working DB**: `trading_ai_sandbox`（sandbox 隔絕 production；per Sprint 1A-ζ Q1d/Q2 operator sign-off）

**Scope**:
1. workspace `rust/Cargo.toml` + `rust/openclaw_engine/Cargo.toml` 加 `sysinfo` dep
2. `rust/openclaw_engine/src/health/mod.rs` 升級為 sysinfo-backed `EngineRuntimeSample` + 6 metric (cpu_pct / rss_mb / heartbeat_alive / open_fd_count / thread_count / uptime_sec)
3. `rust/openclaw_engine/src/health/metric_emitter/mod.rs` 新增 module（per parent spec §3.1）：
   - `DomainEmitter` trait + `MetricSample` trait
   - `RollingWindowAggregator` (5 sample Bessel sigma)
   - `MetricEmitterScheduler` (tokio task)
4. `rust/openclaw_engine/src/health/writer.rs` 新增 `HealthObservationWriter` trait + V106 INSERT 接 `PgPoolWrapper`
5. `rust/openclaw_engine/src/health/event_bus.rs` 新增 `HealthStateChangeEvent` + emit pattern（Sprint 5 cascade subscribe 預埋）
6. `HealthStateMachine::observe_classified()` 新 API (per parent spec §5.2 ladder transition matrix)
7. D3 cascade reject log emit minimal IMPL（per parent spec §3 D3）：
   - `try_transition_with_cap` `≥2 fail-closed reject` 場景 emit V106 row with `evidence_json={"reject_reason": "amp_cap_>=2_fail_closed"}`
   - `try_transition_with_cap` `same anomaly_id 24h cap` suppress 場景 emit V106 row with `evidence_json={"reject_reason": "amp_cap_same_anomaly_24h_suppress"}`
   - 不 emit Slack / Console badge；不 halt strategy / 降 LAL Tier
8. `tests/sprint2_track_a_engine_runtime.rs` 新增測試 (per AC sub-step §2.4)

### 2.3 File scope

- `rust/Cargo.toml`（workspace deps）
- `rust/openclaw_engine/Cargo.toml`（dep 引）
- `rust/openclaw_engine/src/health/mod.rs`（升級）
- `rust/openclaw_engine/src/health/metric_emitter/mod.rs`（新）
- `rust/openclaw_engine/src/health/writer.rs`（新）
- `rust/openclaw_engine/src/health/event_bus.rs`（新）
- `rust/openclaw_engine/tests/sprint2_track_a_engine_runtime.rs`（新）

### 2.4 AC sub-step

| AC# | Pass criteria | Verify |
|---|---|---|
| AC-1 engine_runtime | V106 30 min window engine_runtime row count ≥ 5 (5 sample × 30s = 2.5 min cycle) | SQL `SELECT COUNT(*) FROM learning.health_observations WHERE domain='engine_runtime' AND created_at > NOW() - INTERVAL '30 min'` ≥ 5 |
| AC-2 4-state ladder | engine_runtime OK→WARN dwell 60s + WARN→DEGRADED dwell 5min 真實 fire | `cargo test --release test_sprint2_ladder_engine_runtime` PASS |
| AC-3 amp cap | engine_runtime 24h-suppression empirical fire (spike Track B 已 PASS；本 Track 沿用) | `cargo test --release --features spike test_sprint2_amp_cap_engine_runtime` PASS |
| AC-5 spike default false | `nm target/release/openclaw_engine \| grep -E "(mock_instant\|tokio::time::pause\|spike)" \| wc -l` = 0 | `cargo build --release` (無 `--features spike`) + nm symbol scan |
| **D3 cascade reject** | `≥2 fail-closed reject` 場景 + `same anomaly_id 24h suppress` 場景 各 emit 1 V106 row with `evidence_json.reject_reason` | `cargo test --release test_sprint2_track_a_cascade_reject_emit` (2 sub-case) PASS |

### 2.5 反模式 (明示禁止)

- (a) 直接修 `health/mod.rs` `observe()` API（spike Track B 已 land；保 backward compat；新 API 走 `observe_classified()`）
- (b) `metric_emitter` module 引入 `spike` feature flag（per AC-5 production binary 0 mock time 滲透）
- (c) sysinfo crate 跨平台分支寫死 `cfg(target_os = "linux")` only（Mac 部署目標必須跑通）
- (d) D3 cascade reject emit 接 Slack / Console badge / halt strategy / 降 LAL Tier（Sprint 5/7/8 才接）
- (e) emit V106 row 寫 `state` 與 reject 場景不一致（reject 場景 `state` 維持當前；不變 transition）

### 2.6 估時

- E1 IMPL: **6-8 hr**（含 D3 ~2 hr cascade reject）
- E2 review estimate: 1-2 hr

### 2.7 Disconnect Recovery

- 接手 sub-agent 必跑 Sprint 1A-ζ spec §6.3.1 三連檢查（memory log / git log / TODO entry）
- 接手前 commit 鎖（commit-first 後再動代碼；per `project_multi_session_memory_race`）
- 中斷點重啟必驗 scaffold (trait + writer + event bus) commit SHA 已 land

---

## §3 Track B: pipeline_throughput

### 3.1 Prerequisite

- Wave 1 Track A scaffold 已 land (trait + writer + event bus + observe_classified API)
- 既有 `ws_client` / `IndicatorEngine` / IPC pipeline 真實存在於 engine（per parent spec §2.1 sample 來源真實）

### 3.2 E1 prompt skeleton

**Working branch**: `feature/sprint_2_track_b_pipeline_throughput`

**Scope**:
1. `rust/openclaw_engine/src/health/domains/pipeline_throughput.rs` 新（per parent spec §2.1 + §3.2）
2. `PipelineThroughputSample` struct (per parent spec §3.2)
3. impl `DomainEmitter` for `PipelineThroughputEmitter`
4. 接 `ws_client` 已存在的 tick_rate / heartbeat_lag / subscription_drift hook
5. 接 `IPC` roundtrip metric（既有 IPC 已寫 latency 計時）
6. 接 `IndicatorEngine` signal rate metric
7. `tests/sprint2_track_b_pipeline_throughput.rs`

### 3.3 File scope

- `rust/openclaw_engine/src/health/domains/pipeline_throughput.rs`（新）
- `rust/openclaw_engine/src/health/domains/mod.rs`（新 / 加 pub mod pipeline_throughput）
- `rust/openclaw_engine/tests/sprint2_track_b_pipeline_throughput.rs`（新）

### 3.4 AC sub-step

| AC# | Pass criteria |
|---|---|
| AC-1 pipeline_throughput | V106 30 min window pipeline_throughput row count ≥ 5 |
| AC-2 4-state ladder | OK→WARN→DEGRADED ladder fire test PASS |
| AC-4 cross-domain | pipeline_throughput DEGRADED 不影響 engine_runtime state |
| AC-5 spike default false | production binary 不滲透 mock time |

### 3.5 反模式

- (a) 修 ws_client / IndicatorEngine 既有邏輯（emitter 只讀，不修）
- (b) 寫死採樣 30s interval（用 parent spec §2.1 sample_interval_sec()=30）
- (c) 同 sample 走多 metric_name（per anomaly_id 規約 §6.2 一 metric 一 anomaly_id）

### 3.6 估時

- E1 IMPL: 6-8 hr
- E2 review: 1-2 hr

---

## §4 Track C: database_pool

### 4.1 Prerequisite

- Wave 1 Track A scaffold land
- 既有 `sqlx::PgPool` instance 在 engine main runtime path 可 access

### 4.2 E1 prompt skeleton

**Working branch**: `feature/sprint_2_track_c_database_pool`

**Scope**:
1. `rust/openclaw_engine/src/health/domains/database_pool.rs` 新
2. `DatabasePoolSample` struct (per parent spec §3.2)
3. impl `DomainEmitter` for `DatabasePoolEmitter`
4. 接 `PgPool::size()` / `num_idle()`
5. 寫入 writer queue depth hook（既有 writer pipeline 已有 metric）
6. `psql -c "SELECT pg_database_size('trading_ai')"` 取 disk usage（或 procfs 取 data dir）
7. `tests/sprint2_track_c_database_pool.rs`

### 4.3 File scope

- `rust/openclaw_engine/src/health/domains/database_pool.rs`（新）
- `rust/openclaw_engine/tests/sprint2_track_c_database_pool.rs`（新）

### 4.4 AC sub-step

| AC# | Pass criteria |
|---|---|
| AC-1 database_pool | V106 30 min window database_pool row count ≥ 3 (60s × 5 = 5 min cycle) |
| AC-2 4-state ladder | OK→WARN→DEGRADED ladder fire test PASS |
| AC-4 cross-domain | database_pool DEGRADED 不影響其他 5 domain state |
| AC-5 spike default false | production binary 不滲透 mock time |

### 4.5 反模式

- (a) PG self-query 高頻（60s sample interval 不可寫死 30s 高頻）
- (b) Pool size 改動 emitter 邏輯（emitter 只觀測）
- (c) disk usage helper Linux-only `cfg(target_os = "linux")`（Mac 部署目標必須跑通）

### 4.6 估時

- E1 IMPL: 6-8 hr
- E2 review: 1-2 hr

---

## §5 Track D: api_latency

### 5.1 Prerequisite

- Wave 1 Track A scaffold land
- 既有 `bybit_rest_client` + `bybit_ws_client` 有 p95 latency / retCode counter / WS dropout counter hook

### 5.2 E1 prompt skeleton

**Working branch**: `feature/sprint_2_track_d_api_latency`

**Scope**:
1. `rust/openclaw_engine/src/health/domains/api_latency.rs` 新
2. `ApiLatencySample` struct (per parent spec §3.2)
3. impl `DomainEmitter` for `ApiLatencyEmitter`
4. 接 `bybit_rest_client` 已存在 p95 latency / retCode counter hook
5. 接 `bybit_ws_client` dropout / reconnect counter
6. `tests/sprint2_track_d_api_latency.rs`

### 5.3 File scope

- `rust/openclaw_engine/src/health/domains/api_latency.rs`（新）
- `rust/openclaw_engine/tests/sprint2_track_d_api_latency.rs`（新）

### 5.4 AC sub-step

| AC# | Pass criteria |
|---|---|
| AC-1 api_latency | V106 30 min window api_latency row count ≥ 3 (60s × 5 = 5 min cycle) |
| AC-2 4-state ladder | OK→WARN→DEGRADED ladder fire test PASS |
| AC-4 cross-domain | api_latency DEGRADED 不影響其他 5 domain state |
| AC-5 spike default false | production binary 不滲透 mock time |

### 5.5 反模式

- (a) emit retCode != 0 觸發 fail-closed retry（per CLAUDE.md hard boundary：「不增 hidden retry path for trading effects」；emitter 只觀測）
- (b) WS dropout 觸發 reconnect 邏輯（既有 ws_client 已處理；emitter 只觀測）

### 5.6 估時

- E1 IMPL: 6-8 hr
- E2 review: 1-2 hr

---

## §6 Track E: strategy_quality (最高工時 8-12 hr)

### 6.1 Prerequisite

- Wave 1 Track A scaffold land
- 既有 5 strategy × 5 symbol = 25 active config 在 engine runtime
- per-strategy fill / signal / lease grant rate hook 既有

### 6.2 E1 prompt skeleton

**Working branch**: `feature/sprint_2_track_e_strategy_quality`

**Scope**:
1. `rust/openclaw_engine/src/health/domains/strategy_quality.rs` 新
2. `StrategyQualitySample` struct (per parent spec §3.2)
3. impl `DomainEmitter` for `StrategyQualityEmitter`
4. **per-strategy SM 25 instance**（per parent spec §4.4）：
   - `HashMap<(String, String), Arc<Mutex<HealthStateMachine>>>` (strategy × symbol)
   - aggregate SM with rule `degraded_count / total_count > 0.40 → DEGRADED`
5. 接 `decision_outcomes` fill / lease grant rate query
6. 接 dormant 計時 hook（既有 first-detection deadlock 教訓 retain；per `project_first_detection_deadlock_pattern`）
7. **不**接 M7 DECAY_ENFORCED 觸發（per parent spec §2.3；Sprint 5 才接）
8. `tests/sprint2_track_e_strategy_quality.rs`

### 6.3 File scope

- `rust/openclaw_engine/src/health/domains/strategy_quality.rs`（新）
- `rust/openclaw_engine/tests/sprint2_track_e_strategy_quality.rs`（新）

### 6.4 AC sub-step

| AC# | Pass criteria |
|---|---|
| AC-1 strategy_quality | V106 30 min window strategy_quality row count ≥ 1 per strategy × symbol pair (5min × 5 = 25 min cycle；30min 容差) |
| AC-2 4-state ladder | per-strategy OK→WARN→DEGRADED + aggregate rule 0.40 threshold fire test PASS |
| AC-4 cross-domain | strategy_quality (per-strategy) DEGRADED 不影響其他 5 domain；aggregate DEGRADED 不直接降 LAL Tier |
| AC-5 spike default false | production binary 不滲透 mock time |

### 6.5 反模式

- (a) per-strategy SM 升 DEGRADED 直接降 LAL Tier（per parent spec §4.4；Sprint 5 才接）
- (b) emit `StrategyHealthEvent` 給 M7（Sprint 5 才接）
- (c) 25 instance 共用同一 amp_cap_entries HashMap（每 instance 獨立 cap window per `anomaly_id`）
- (d) dormant 計時無過期 auto-clear（per `project_first_detection_deadlock_pattern` 教訓；retain 24h cap window）

### 6.6 估時

- E1 IMPL: **8-12 hr**（最高工時 due to 25 instance + per-strategy aggregate rule + dormant 邏輯）
- E2 review: 2-3 hr

---

## §7 Track F: risk_envelope

### 7.1 Prerequisite

- Wave 1 Track A scaffold land
- 既有 risk_config TOML 載入 + portfolio cum_pnl / dd / correlation / concentration calculation 在 engine

### 7.2 E1 prompt skeleton

**Working branch**: `feature/sprint_2_track_f_risk_envelope`

**Scope**:
1. `rust/openclaw_engine/src/health/domains/risk_envelope.rs` 新
2. `RiskEnvelopeSample` struct (per parent spec §3.2)
3. impl `DomainEmitter` for `RiskEnvelopeEmitter`
4. 共用 `risk_config` 既有 calculation（不重做 portfolio calc）
5. 接 correlation pairwise + top-1 concentration helper
6. **不**同步 5-gate kill threshold（per parent spec §2.3；Sprint 5 Tier 1 IMPL 前 confirm）
7. `tests/sprint2_track_f_risk_envelope.rs`

### 7.3 File scope

- `rust/openclaw_engine/src/health/domains/risk_envelope.rs`（新）
- `rust/openclaw_engine/tests/sprint2_track_f_risk_envelope.rs`（新）

### 7.4 AC sub-step

| AC# | Pass criteria |
|---|---|
| AC-1 risk_envelope | V106 30 min window risk_envelope row count ≥ 1 (5min × 5 = 25 min cycle；30min 容差) |
| AC-2 4-state ladder | portfolio dd / correlation / concentration OK→WARN→DEGRADED fire test PASS |
| AC-4 cross-domain | risk_envelope DEGRADED 不影響其他 5 domain；不觸 5-gate kill |
| AC-5 spike default false | production binary 不滲透 mock time |
| AC-7 portfolio 原則 | risk_envelope 是 portfolio-level 聚合，對齊 16 根原則 #16 |

### 7.5 反模式

- (a) risk_envelope emitter 改 risk_config TOML 載入 / portfolio calculation（emitter 只觀測；既有 calc 是 SSOT）
- (b) emit DEGRADED 觸 5-gate kill 行為（per parent spec §2.3；Sprint 5 才同步）
- (c) correlation calc 跑高頻（5min sample interval；不可寫死 30s）

### 7.6 估時

- E1 IMPL: 6-8 hr
- E2 review: 1-2 hr

---

## §8 Wave 拆分 + Phase chain

### 8.1 Wave 拆分 (per D2 並行 ceiling)

per parent spec §4.2 + §4.3：

| Wave | Track | Wall-clock | 並行 sub-agent peak | Sprint 1B mid 並行峰值 | Total peak |
|---|---|---|---|---|---|
| **Wave 1** | Track A + B + C | D0-D3 (3 day) | 3 + PM | 0-3 (PA-DRIFT-1/2 + E3-MED-2) | **6-7 sub-agent** |
| **Wave 2** | Track D + E + F | D3-D6 (3 day) | 3 + PM | 0 (Sprint 1B mid 預期已 DONE) | **4 sub-agent** |

**Wave 1 stagger 5min dispatch**：
- T+0min 派 Track A
- T+5min 派 Track B
- T+10min 派 Track C
- Track A 24h 內 commit scaffold 後 Track B/C 才能用 trait + writer + event bus

**Wave 2 stagger 5min dispatch**：
- T+0min 派 Track D
- T+5min 派 Track E (最高工時 8-12 hr)
- T+10min 派 Track F

### 8.2 Phase chain

per Sprint 1A-ζ Phase chain pattern：

| Phase | Item | Owner | 估時 |
|---|---|---|---|
| Phase 1 | 本 packet (PA single-thread) | PA | ~2-3 hr |
| Phase 2 Wave 1 | Track A + B + C 3 並行 | E1 × 3 | 18-24 hr 並行 (wall-clock 3 day) |
| Phase 2 Wave 2 | Track D + E + F 3 並行 | E1 × 3 | 20-28 hr 並行 (wall-clock 3 day) |
| Phase 3a Wave 1 review | E2 × 3 並行 (Track A/B/C) | E2 × 3 | 4-6 hr 並行 (wall-clock 1 day) |
| Phase 3a Wave 2 review | E2 × 3 並行 (Track D/E/F) | E2 × 3 | 4-6 hr 並行 (wall-clock 1 day) |
| Phase 3b E4 regression | cargo test --workspace + pytest baseline | E4 single | 4-6 hr |
| Phase 3c QA empirical | AC-1..7 driver + V106 SQL query | QA single | 4-6 hr (需 E3-MED-2 已 closed) |
| Phase 3d TW Acceptance | Sprint 2 Acceptance Report | TW single | 2-3 hr |
| Phase 3e PM sign-off | Verdict + Sprint 5 cascade readiness | PM single | 1-2 hr |

**Total wall-clock：1-1.5 week（D0-D10）**

### 8.3 Cross-Wave constraint

per Sprint 1A-ζ spec §3.2 sequential constraint 範式：

```
Wave 1 Track A 升級先 land 24h 內 commit scaffold (trait + writer + event bus + observe_classified)
  ↓
Wave 1 Track B/C dispatch packet 含 SHA hint 等 Track A scaffold commit
  ↓
Wave 1 Track A/B/C IMPL DONE + E2 review × 3 並行 review PASS
  ↓
Wave 2 Track D/E/F dispatch (Wave 1 scaffold 已穩定)
  ↓
Wave 2 Track D/E/F IMPL DONE + E2 review × 3 並行 review PASS
  ↓
Phase 3b E4 regression single-thread
  ↓
Phase 3c QA empirical (需 E3-MED-2 closed)
  ↓
Phase 3d TW + Phase 3e PM
```

---

## §9 Common 反模式 (6 Track 通用禁忌)

per Sprint 1A-ζ Phase 2 spec §1.8 + §3.7 共用反模式：

- (a) 跨 Track 共用 file scope 寫入（per parent spec §4.1 cross-domain coordination；Wave 1 內每 Track 獨立 file 路徑）
- (b) feature flag `spike` 滲透 production binary（per AC-5）
- (c) sysinfo / sqlx / Bybit client / strategy event 接點寫 mock data（per `feedback_no_dead_params`）
- (d) emit V106 row 寫 `engine_mode='live'`（per Sprint 2 stage = paper/demo/live_demo only；live 走 Sprint 4 first Live）
- (e) cross-Track race（Wave 1 內 stagger 5min dispatch；Wave 2 用 Wave 1 scaffold 不重做 trait）
- (f) 派 sub-agent 前不 `git fetch` + `git branch -r | grep sprint_2`（per `feedback_fetch_before_dispatch`）
- (g) 多 session memory race 接手不跑三連檢查（per `project_multi_session_memory_race`）
- (h) E1 IMPL DONE 自評不走 A3+E2 對抗 review（per `feedback_impl_done_adversarial_review`；本 Sprint 2 emitter 0 GUI 改動 → A3 skip；E2 必 review）

---

## §10 必讀文件清單

### 10.1 Sprint 2 parent spec

1. `docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md`（本 packet parent；含 §3 D1/D2/D3 + §4 IMPL plan adjust + §1-§10 design body）
2. `docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md`（648 行；含 §2.1 sample 頻率 + §3.3 dwell time + §6 amplification logic）
3. `docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md`（1087 行；schema column 清單 + Guard A/B/C）
4. `docs/adr/0042-m3-health-monitoring.md`（7 Decision 尤其 Decision 4 amplification cap）

### 10.2 Sprint 1A-ζ baseline ref

5. `docs/execution_plan/2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md`（spike scope + AC pattern + Phase chain 範式 + §6.3.1 multi-session race SOP）
6. `docs/execution_plan/2026-05-21--sprint_1a_zeta_3_e1_dispatch_packet.md`（本 packet 範本來源）
7. `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_1a_zeta_pm_phase_3e_signoff.md` §4.3 (Sprint 1B 6 條 routing)

### 10.3 Rust baseline ref

8. `rust/openclaw_engine/src/health/mod.rs`（718 行 spike skeleton；Sprint 2 Track A 升級基線）
9. `rust/openclaw_engine/tests/m3_amp_cap_24h_fire.rs`（269 行 AC-5.1 fire test；Sprint 2 Track A 沿用）
10. `rust/openclaw_engine/Cargo.toml`（spike feature + features 既有結構）
11. `rust/Cargo.toml`（workspace deps；sysinfo 加入點）

### 10.4 Memory ref

- `feedback_subagent_first` + `feedback_fetch_before_dispatch`（sub-agent ceiling + race mitigation）
- `feedback_impl_done_adversarial_review`（IMPL DONE 強制 A3+E2 對抗 review）
- `feedback_chinese_only_comments`（注釋默認中文）
- `feedback_cross_platform`（sysinfo Mac+Linux 跨平台原生支援）
- `project_first_detection_deadlock_pattern`（Track E dormant 計時 retain 24h cap window）
- `project_multi_session_memory_race`（commit-first / 不認識改動禁 revert）
- `project_mac_deployment_target`（Apple Silicon Mac 部署目標永遠 ready）

---

## §11 Disconnect Recovery Protocol (per Sprint 1A-ζ §6.3.1)

每 Track 接手 sub-agent 必跑：

```bash
# 1. memory log 檢查
ls -la ~/.claude/projects/-Users-ncyu-Projects-TradeBot/memory/ | head -5
grep -l "sprint_2" ~/.claude/projects/-Users-ncyu-Projects-TradeBot/memory/*.md

# 2. git log 檢查
git log --oneline --since="2 days ago" --all | head -10
git log --oneline feature/sprint_2_track_<a|b|c|d|e|f>* 2>&1 | head -5

# 3. TODO entry 檢查
grep -c "sprint_2" /Users/ncyu/Projects/TradeBot/srv/TODO.md
```

任一檢查發現前任工作 → 接手必走 commit-first / 不認識改動禁 revert。

---

## §12 Sign-off path

```
本 packet land (PA Phase 1 DONE)
  ↓
PM 拍 sign-off Sprint 2 派發 readiness
  ↓
PM 派 Wave 1 Track A E1 (T+0min)
PM 派 Wave 1 Track B E1 (T+5min)
PM 派 Wave 1 Track C E1 (T+10min)
  ↓
Wave 1 IMPL DONE + E2 review × 3 並行 PASS
  ↓
PM 派 Wave 2 Track D E1 (T+0min)
PM 派 Wave 2 Track E E1 (T+5min;最高工時 8-12 hr)
PM 派 Wave 2 Track F E1 (T+10min)
  ↓
Wave 2 IMPL DONE + E2 review × 3 並行 PASS
  ↓
Phase 3b E4 → Phase 3c QA → Phase 3d TW → Phase 3e PM
  ↓
Sprint 5 cascade IMPL 派發 readiness gate verdict
```

---

**END M3 metric emitter Sprint 2 Phase 2 E1 Dispatch Packet**

**PA DESIGN DONE**: dispatch packet path: `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md`
