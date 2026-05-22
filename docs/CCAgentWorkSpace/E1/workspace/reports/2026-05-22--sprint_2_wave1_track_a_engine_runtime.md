---
report: Sprint 2 Phase 2 Wave 1 Track A — engine_runtime baseline 升級 + D3 cascade reject log minimal IMPL
date: 2026-05-22
author: E1 (Backend Developer, Rust)
phase: Sprint 2 Phase 2 Wave 1 Track A (scaffold owner — Track B/C/D/E/F 後續沿用)
status: IMPL DONE — awaiting E2 + A3 並行 adversarial review
parent dispatch:
  - docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md §2 Track A
  - docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md §3 D1/D2/D3 + §4 + §5 + §6
  - docs/adr/0042-m3-health-monitoring.md Decision 2 (4-state ladder) + Decision 3 (6 domain) + Decision 4 (amp cap)
runtime: Mac development (sysinfo cross-platform native Mac+Linux verified)
production engine: PID 2934602 跑 trading_ai (全程未碰)
---

# E1 Sprint 2 Wave 1 Track A — engine_runtime scaffold IMPL

## §1 Scaffold landed (Track B/C/D/E/F unblock condition)

per packet §1.7 Wave 1 scaffold contract，本 Track 已 land 全 7 scaffold item：

| Scaffold item | File path | LOC | 公開 API（Track B-F 沿用） |
|---|---|---|---|
| `DomainEmitter` trait + `MetricSample` trait | `rust/openclaw_engine/src/health/metric_emitter/mod.rs` | 964 (含 EngineRuntimeEmitter + 6 classify helper + 8 unit test) | `pub trait MetricSample` / `pub trait DomainEmitter` / `pub struct EngineRuntimeSample` / `pub struct EngineRuntimeMetricRow` / `pub fn classify_engine_runtime_*` × 4 |
| `RollingWindowAggregator` (5 sample Bessel sigma) | 同上 | 含上述 | `pub struct RollingWindowAggregator` / `new(metric_name)` / `push(value)` / `mean()` / `sigma()` / `current_window_size()` |
| `HealthObservationWriter` trait + V106 INSERT 接 PgPool | `rust/openclaw_engine/src/health/writer.rs` | 464 | `pub trait HealthObservationWriter` / `pub struct PgHealthObservationWriter::new(pool)` / `pub struct InMemoryHealthObservationWriter` / `pub struct HealthObservationRow` |
| event_bus emit pattern + `HealthStateChangeEvent` | `rust/openclaw_engine/src/health/event_bus.rs` | 202 | `pub struct HealthStateChangeEvent` / `pub struct HealthEventBus::new()` / `pub struct HealthEventSubscriber` |
| `observe_classified` SM 新入口 | `rust/openclaw_engine/src/health/mod.rs` (升級 718→990) | +272 (新增 observe_classified + try_dwell_then_transition + try_recovery_dwell + previous_state accessor + 5 new SM field) | `pub fn HealthStateMachine::observe_classified(band, anomaly_id, now)` / `previous_state()` / `state_entered_at()` / `domain()` |
| `sysinfo::System` 接 `EngineRuntimeSample` | `rust/openclaw_engine/src/health/metric_emitter/mod.rs` | 含上述 | `pub struct EngineRuntimeEmitter::new(pid, heartbeat_probe)` / `sample_now()` |
| D3 cascade reject log emit minimal | `rust/openclaw_engine/src/health/metric_emitter/mod.rs` `run_domain_loop` reject_reason 推斷 + `HealthObservationRow::with_evidence` | 含上述 (+27 行 reject branch) | scheduler 端內嵌；test 走 writer mock 模擬 emit V106 row evidence_json.reject_reason |

**Track A scaffold 總計新增 LOC: ~2280 行 (含 mod.rs 升級 + 三新 module + 1 integration test)；packet §1.7 估 ~500 LOC scaffold IMPL，超因含完整 ladder transition matrix + EngineRuntimeEmitter sysinfo 接線 + 8 unit test + 5 integration test。**

## §2 Cargo dep

```diff
# rust/Cargo.toml workspace.dependencies
+ sysinfo = "0.32"

# rust/openclaw_engine/Cargo.toml [dependencies]
+ sysinfo = { workspace = true }
```

`sysinfo 0.32` MSRV 1.74，本機 rustc 1.95 對齊；跨平台原生 Mac+Linux（per `project_mac_deployment_target`）。Cargo.lock 自動更新 14 transitive dep（per packet §1.6 estimate）。

## §3 Cargo build + test result

| Verify | Command | Result |
|---|---|---|
| Release build (default, no spike) | `cargo build --release` | **PASS** — 24.6s clean build；2 pre-existing warning (panel_aggregator unused_imports + ma_crossover dead_code)，health module 0 warning |
| Lib unit tests (default) | `cargo test --release --lib health::` | **32/32 PASS** (含 spike Track B 舊 14 test + Sprint 2 18 new test：8 metric_emitter + 5 writer + 4 event_bus + 1 mod.rs new) |
| Lib unit tests (full lib) | `cargo test --release --lib` | **3096/3096 PASS** (1 ignored 為 pre-existing; 0 new fail) |
| Integration test Sprint 2 Track A | `cargo test --release --test sprint2_track_a_engine_runtime` | **5/5 PASS**：<br/>- `test_sprint2_ladder_engine_runtime`<br/>- `test_sprint2_track_a_cascade_reject_emit_fail_closed_ge_2`<br/>- `test_sprint2_track_a_cascade_reject_emit_same_anomaly_24h_suppress`<br/>- `test_sprint2_track_a_engine_runtime_row_count_ge_5`<br/>- `test_sprint2_track_a_spike_feature_not_active_in_default_build` |
| Spike regression | `cargo test --release --features spike --test m3_amp_cap_24h_fire` | **3/3 PASS**：spike Track B baseline 沿用無退化 |
| nm symbol scan (AC-5) | `nm target/release/openclaw-engine \| grep -E "(mock_instant\|tokio::time::pause\|spike)" \| wc -l` | **0 hit** ✓ — production binary 0 mock time 滲透 |
| strings scan | `strings target/release/openclaw-engine \| grep -E "(mock_instant\|spike)" \| wc -l` | **0 hit** ✓ |

## §4 AC verify

per packet §2.4 AC sub-step:

| AC# | Pass criteria | Result | Evidence |
|---|---|---|---|
| **AC-1** engine_runtime row | V106 30 min window engine_runtime row count ≥ 5 | **PASS (in-memory proxy)** — `test_sprint2_track_a_engine_runtime_row_count_ge_5` 走 mock emitter + 1s interval × 6s = 6+ tick × 6 metric ≥ 36 row 寫入 in-memory writer，遠超 ≥ 5 門檻 | Mac sandbox 不 connect Linux PG（per packet 容差）；real PG empirical 由 Phase 3c QA empirical 走 |
| **AC-2** 4-state ladder | OK→WARN dwell 60s + WARN→DEGRADED dwell 5min 真實 fire | **PASS** — `test_sprint2_ladder_engine_runtime`：<br/>- 採樣 base+0s/30s/60s 三次 → 60s 達標 OK→WARN fire (count=1)<br/>- 採樣 base+60s/300s/360s 三次 → 5min 達標 WARN→DEGRADED fire (count=2)<br/>- previous_state / current_state / amplification_loop_24h_count 全對齊 | direct SM 走 observe_classified；無需 spike feature mock clock |
| **AC-3** amp cap 沿用 | spike Track B 已 PASS；本 Track 沿用無退化 | **PASS** — `cargo test --release --features spike --test m3_amp_cap_24h_fire` 3/3 PASS (test_m3_amp_cap_24h_fire / test_amp_cap_different_anomaly_id_not_suppressed / test_stub_domains_fail_loud) | regression baseline 不退 |
| **AC-5** spike default false | `nm ... \| grep ... \| wc -l = 0` | **PASS** — nm 0 hit / strings 0 hit | release profile `strip = "symbols"` 仍保留外部 unresolved 符號可供 nm 掃描 (`_CCRandomGenerateBytes` etc. visible)；目標 spike/mock_instant/tokio::time::pause 全 0 hit |
| **D3 cascade reject** | ≥2 fail-closed + same anomaly 24h suppress 各 emit V106 row with evidence_json.reject_reason | **PASS (2/2)** — `test_sprint2_track_a_cascade_reject_emit_fail_closed_ge_2` 驗 `evidence_json.reject_reason="amp_cap_>=2_fail_closed"` + state 維持 current；`test_sprint2_track_a_cascade_reject_emit_same_anomaly_24h_suppress` 驗 `evidence_json.reject_reason="amp_cap_same_anomaly_24h_suppress"` + state 維持 current | scheduler 端 reject_reason 推斷邏輯內嵌於 `run_domain_loop` |

## §5 Track A scaffold READY-FOR-WAVE-1 verdict

**Verdict: ✅ READY**。Wave 1 Track B/C 可開派；Wave 2 Track D/E/F 沿用同 scaffold。

### Track B/C (Wave 1) unblock conditions check

| Condition | Status | Public API export |
|---|---|---|
| DomainEmitter trait exported pub | ✅ | `openclaw_engine::health::metric_emitter::DomainEmitter` |
| MetricSample trait exported pub | ✅ | `openclaw_engine::health::metric_emitter::MetricSample` |
| RollingWindowAggregator exported pub | ✅ | `openclaw_engine::health::metric_emitter::RollingWindowAggregator` |
| HealthObservationWriter trait exported pub | ✅ | `openclaw_engine::health::writer::HealthObservationWriter` + `HealthObservationRow` + `InMemoryHealthObservationWriter` + `PgHealthObservationWriter` |
| event_bus emit interface stable | ✅ | `openclaw_engine::health::event_bus::HealthEventBus` + `HealthStateChangeEvent` + `HealthEventSubscriber` |
| HealthStateMachine `observe_classified` 新 API | ✅ | `HealthStateMachine::observe_classified(band, anomaly_id, now)` + `previous_state()` + `state_entered_at()` + `domain()` |
| MetricEmitterScheduler tokio task wrapper | ✅ | `MetricEmitterScheduler::new(emitters, writer, event_bus, engine_mode)` + `run(cancel_token)` |
| EngineModeProvider closure type | ✅ | `pub type EngineModeProvider = Arc<dyn Fn() -> String + Send + Sync>` |

### Track D/E/F (Wave 2) unblock conditions

同 Track B/C；Wave 2 接時 Wave 1 scaffold 已穩定（cross-Wave race mitigation per spec §4.3）。

## §6 治理對照

- **§六 Hard Boundaries**：未碰 `live_execution_allowed` / `execution_authority` / `system_mode` / production engine（PID 2934602）/ trading_ai production DB ✓
- **§七 Code And Docs Rules**：注釋全中文（新 module / SM 升級 / test 全中文）；spike Track B 既有中文注釋保留；無 bilingual block 引入 ✓
- **§八 Workflow**：E1 IMPL DONE → 等 E2 + A3 並行 adversarial review（per `feedback_impl_done_adversarial_review`：本 Track Wave 1 scaffold owner 高風險 IMPL）；不自行 commit ✓
- **§九 Code Structure Guardrails**：metric_emitter/mod.rs 964 LOC / mod.rs 990 LOC 觸 800 warning 但未過 2000 hard cap；scaffold owner 預期 LOC peak，Wave 2 後新 emitter 走 `health/domains/<domain>.rs` 拆分（per spec §3 D1 Track B-F 拆檔範式）✓
- **§Data, Migrations, And Validation**：Sprint 2 不新增 V###；V106 schema 19 column 沿用；packet §1.7 描述「27 column」與實際 schema drift 已 report 揭示，IMPL 以 schema 為事實 ✓
- **bilingual-comment-style**：新代碼注釋默認只寫中文（per `feedback_chinese_only_comments` 2026-05-05）✓
- **cross-platform**：sysinfo 0.32 跨平台 Mac+Linux 原生；唯一 platform-specific path `read_open_fd_count` 在 Mac 走 fallback 返 0 fail-closed，不破 cross-platform 部署 ✓
- **AC-5 production binary 0 mock time 滲透**：新 module (event_bus / writer / metric_emitter/mod.rs) 全程不引 `#[cfg(feature = "spike")]`；nm + strings 雙驗 0 hit ✓

## §7 不確定之處 / Carry-over

1. **packet §1 描述「INSERT 全 27 column」與 V106 schema 19 column 實際 drift**：本 IMPL 以 sql/migrations/V106 schema 為事實 land 19 column INSERT。packet 描述可能含「Sprint 5+ Y2 cascade 補充 8 column」未來假設（cascade_event_log / decay_count 等延伸 column）。**Operator action**: 若需擴 27 column 走新 V### EXTEND；本 Track 不修 V106。
2. **AC-1 真實 Linux PG empirical 走 Phase 3c QA**：Mac sandbox 不 connect Linux PG；本 Track AC-1 走 in-memory writer proxy。Phase 3c QA empirical SQL：`SELECT COUNT(*) FROM learning.health_observations WHERE domain='engine_runtime' AND created_at > NOW() - INTERVAL '30 min'` ≥ 5。**Operator action**：QA empirical 走 sandbox_admin via ssh trade-core（per `feedback_v_migration_pg_dry_run`）；engine main runtime 接 EngineRuntimeEmitter + MetricEmitterScheduler 後才能跑通真實 sample。
3. **engine main.rs 不接 EngineRuntimeEmitter + scheduler**：per packet「scaffold land 後 main.rs 接線 Wave 2 後或 Sprint 5 cascade IMPL 一併接」，本 Track 未動 `rust/openclaw_engine/src/main.rs`。Wave 1+2 全 Track 完成後 PM 派 E1 接線 task (estimate 2-4 hr)。
4. **read_open_fd_count Mac fallback 返 0 → fd 暴漲 Mac 端不報警**：sysinfo 0.32 沒提供 cross-platform open_fd API；Mac 部署目標時 fd leak 走 fail-closed OK band 不誤升級。**Operator action**：Mac 部署主要場景為 dev (per Mac=開發/Linux=Runtime memory)；production runtime 在 Linux trade-core，fd 走 procfs path 正常採樣。Sprint 5 cascade IMPL 可考慮升級 `procfs::Process::fd` Linux-specific 真實 fd count 路徑（with Mac fallback）。
5. **CRITICAL → 任何更低 state sticky**：Sprint 2 IMPL CRITICAL 進入後不支援自動 recovery（per spec §5.2 operator manual unlock 走 Sprint 5 Tier 1 + Console GUI）。**Operator action**：Sprint 5 接 operator unlock UI 後本 SM 加 manual unlock API。
6. **metric_emitter/mod.rs 964 LOC + mod.rs 990 LOC 觸 800 warning**：per CLAUDE.md §九 「Files over 800 lines require review attention」。本 module 為 scaffold owner 預期 LOC peak；Wave 2 後新 emitter (Track B/C/D/E/F) 走 `health/domains/<domain>.rs` 拆分（per spec §3 D1）。**Operator action**：Wave 1 Track B/C land 後 PM 評估是否拆分 EngineRuntimeEmitter 到 `health/domains/engine_runtime.rs`。
7. **D3 cascade reject test 走 writer 端 mock emit row 而非 SM private fire**：`try_transition_with_cap` private fn 不暴露 integration test crate；D3 sub-case (a)/(b) integration test 模擬 scheduler 端 reject_reason 推斷邏輯 + writer row emit。SM private fire 路徑覆蓋由 mod.rs `#[cfg(test)] mod tests` 內既有 spike test (`test_try_transition_fail_closed_reject_count_ge_2` / `test_try_transition_cap_suppress_same_anomaly_id_repeat`) 守住。**Operator action**：E2 adversarial review 確認此分工 OK；A3 review 確認 0 GUI 影響。
8. **engine_mode 採樣 closure 注入**：scheduler 接 `EngineModeProvider = Arc<dyn Fn() -> String + Send + Sync>`；test 注入固定 `"demo"`，production 接 `effective_engine_mode()` (main.rs:1044) 或類似 helper。Sprint 2 不寫 `live`（per packet §2.5 反模式 (d)）；real engine mode 由 caller 端決定。

## §8 Operator 下一步

1. **PM 派 A3 (GUI) + E2 (Rust review) 並行 adversarial review** per `feedback_impl_done_adversarial_review`；本 Track Wave 1 唯一 scaffold owner 高風險 IMPL，自評 IMPL DONE 不接受單獨 sign-off。
2. **A3 預期 verdict：0 GUI 改動** — Sprint 2 emitter 0 GUI 改動（Console badge 走 Sprint 8 A3 monthly review panel；emitter 只寫 V106 audit row 不繞 GUI）。
3. **E2 review focus**：
   - SM `observe_classified` ladder transition matrix 7-case 完整性（同 state 4-case + 升階 4-case + recovery 3-case + CRITICAL sticky 3-case）
   - DomainEmitter / MetricSample trait `dyn-incompatible` (associated type) 設計 → Vec<Box<dyn MetricSample>> 結構正確性
   - D3 cascade reject_reason 推斷邏輯 (`prev_count >= 2 AND cur_count == prev_count`) 在 same-anomaly-24h-cap-then-rep-fire-attempt 場景的正確性
   - sysinfo Process::tasks() Mac 返 0 vs Linux thread map 的 cross-platform 行為一致性
   - V106 row sqlx INSERT 19 column binding 全對齊（type cast `$N::NUMERIC(18,8)` 路徑）
4. **E4 regression**：本 Track 0 改 既有 Python 路徑 / 0 改 既有 Rust hot path；E4 跑 `cargo test --workspace --release` + `pytest tests/` 確認 baseline 不退。
5. **Wave 1 Track B/C 派發 readiness**：等 E2/A3 review PASS 後 PM 開派 Track B + Track C (T+0min/T+5min stagger)，dispatch packet 含 SHA hint 等 Track A scaffold commit。
6. **Phase 3c QA empirical AC-1 SQL query** (per packet)：QA via ssh trade-core sandbox_admin (per `feedback_v_migration_pg_dry_run`) 跑：
   ```sql
   SELECT COUNT(*) FROM learning.health_observations
   WHERE domain='engine_runtime' AND created_at > NOW() - INTERVAL '30 min';
   -- expect ≥ 5 once engine main 接 EngineRuntimeEmitter + scheduler 並運行 5+ sample interval
   ```
   engine main.rs 接 scheduler 接線後才能跑此 SQL；本 Track scaffold 階段不接 main.rs。

## §9 修改清單

| File | 改動範圍 | 性質 |
|---|---|---|
| `rust/Cargo.toml` | +6 行 workspace.dependencies `sysinfo = "0.32"` + 注釋 | dep add |
| `rust/openclaw_engine/Cargo.toml` | +3 行 [dependencies] `sysinfo = { workspace = true }` + 注釋 | dep add |
| `rust/Cargo.lock` | sysinfo 0.32 + 14 transitive | auto-update |
| `rust/openclaw_engine/src/health/mod.rs` | 718 → 990 LOC：MODULE_NOTE 升級 + `pub mod event_bus/metric_emitter/writer` 3 加 + `M3Error::SampleError`/`WriterError` 2 variant + `HealthState/HealthDomain` derive `Serialize, Deserialize` + SM 5 new field (`previous_state` / `degraded_band_seen_at` / `critical_band_seen_at` / `recovery_band_seen_at`) + accessor 3 (`previous_state()` / `state_entered_at()` / `domain()`) + `observe_classified` 新 API 含 7-case ladder transition matrix + `try_dwell_then_transition` + `try_recovery_dwell` + `BandKind` enum + previous_state 寫入 fire/recovery 兩 path | 升級 (含 backward compat) |
| `rust/openclaw_engine/src/health/event_bus.rs` | 新 202 LOC：`HealthStateChangeEvent` + `HealthEventBus` + `HealthEventSubscriber` + 4 unit test | 新 module |
| `rust/openclaw_engine/src/health/writer.rs` | 新 464 LOC：`HealthObservationRow` (19 column 對齊 V106) + builder methods (with_transition/with_evidence/with_threshold/with_symbol/with_strategy) + `HealthObservationWriter` trait + `PgHealthObservationWriter` + `InMemoryHealthObservationWriter` + 5 unit test | 新 module |
| `rust/openclaw_engine/src/health/metric_emitter/mod.rs` | 新 964 LOC：`MetricSample` trait + `DomainEmitter` trait + `RollingWindowAggregator` + `EngineRuntimeSample` + `EngineRuntimeMetricRow` + 4 classify helpers + `EngineRuntimeEmitter` (sysinfo-backed) + `read_open_fd_count` cross-platform helper + `EngineModeProvider` type + `MetricEmitterScheduler` + `run_domain_loop` 含 D3 cascade reject log emit minimal IMPL + `classify_aggregated` helper + 8 unit test | 新 module |
| `rust/openclaw_engine/tests/sprint2_track_a_engine_runtime.rs` | 新 378 LOC：5 integration test（AC-1 / AC-2 / D3 ×2 / AC-5 spike feature not active）| 新 test |

**總計：1 升級 + 3 新 module + 1 integration test = ~2280 LOC 新增**

### 不動 / 無關 file

- `sql/migrations/V106__health_observations.sql`（schema 不動）
- `rust/openclaw_engine/src/main.rs`（main runtime 接線走 Wave 2 後或 Sprint 5 cascade IMPL 一併接）
- `rust/openclaw_engine/src/lib.rs`（`pub mod health` 既有，新 sub-module 透過 `health/mod.rs` 內 `pub mod` 暴露）
- 其餘 88 個 module（panel_aggregator / governance / strategies / 等）
- production engine（PID 2934602 跑 trading_ai 全程未碰）
- trading_ai production DB（全程未碰）

## §10 風險 / 副作用識別

| 副作用候選 | 驗證結果 |
|---|---|
| `observe()` API 破壞 spike Track B test | ❌ 無影響 — `tests/m3_amp_cap_24h_fire.rs` 3/3 PASS (release `cargo test --features spike --test m3_amp_cap_24h_fire`) |
| `HealthStateMachine::new()` field 改 break 既有 callers | ❌ 無影響 — `new()` signature 不變；新 field 全 internal init；既有 callers (spike test) 不需改 |
| `HealthState` derive `Serialize+Deserialize` 改 PG round-trip | ❌ 無影響 — V106 row 字串 round-trip 仍走 `as_str()` / `from_str()`；serde JSON `"HealthOk"` 僅 event_bus broadcast 用 |
| sysinfo 0.32 拉新 transitive dep | ✅ 14 dep new (per Cargo.lock auto-update)；workspace 全 build PASS；無 conflict |
| metric_emitter module 引入 `cfg(feature = "spike")` | ❌ 0 spike feature gate (per AC-5 nm 0 hit) |
| sysinfo cross-platform 寫死 `cfg(target_os = "linux")` | ❌ 唯一 cfg gate 在 `read_open_fd_count` helper（Linux procfs / Mac fallback 返 0）；其餘 sysinfo API 全 cross-platform |
| 改動 production engine state / DB | ❌ 0 production touched |

## §11 完成回報

1. **Scaffold module + LOC summary**：4 new file (`event_bus.rs` 202 / `writer.rs` 464 / `metric_emitter/mod.rs` 964 / `tests/sprint2_track_a_engine_runtime.rs` 378) + 1 upgrade (`health/mod.rs` 718→990) = **~2280 LOC 新增**
2. **Cargo dep**：`sysinfo = "0.32"` 加 workspace.dependencies + `sysinfo = { workspace = true }` 加 openclaw_engine [dependencies]；`cargo build --release` PASS（24.6s clean）
3. **cargo test PASS list**：
   - `cargo test --release --lib health::` 32/32 PASS
   - `cargo test --release --lib` 3096/3096 PASS (1 pre-existing ignored / 0 new fail)
   - `cargo test --release --test sprint2_track_a_engine_runtime` 5/5 PASS (含 D3 cascade reject 2 sub-case + ladder + AC-1 proxy + AC-5 spike not active)
   - `cargo test --release --features spike --test m3_amp_cap_24h_fire` 3/3 PASS (regression)
4. **AC-1..5 + D3 verify result**：AC-1 in-memory proxy PASS / AC-2 ladder fire PASS / AC-3 spike regression PASS / AC-5 nm 0 hit PASS / D3 cascade reject 2 sub-case PASS
5. **Track A scaffold READY-FOR-WAVE-1 verdict**：**READY**。Track B/C/D/E/F unblock conditions check 8/8 PASS（DomainEmitter / MetricSample / RollingWindowAggregator / HealthObservationWriter / event_bus / observe_classified / MetricEmitterScheduler / EngineModeProvider 全 pub export）

---

**E1 IMPLEMENTATION DONE: 待 A3 + E2 並行 adversarial review（per `feedback_impl_done_adversarial_review` Wave 1 scaffold owner 高風險 IMPL）**

**Report path**: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave1_track_a_engine_runtime.md`
