---
report: Sprint 2 Wave 2 Track D — api_latency emitter IMPL
date: 2026-05-22
author: E1 (Backend Developer, Rust)
phase: Sprint 2 Phase 2 Wave 2 Track D
status: IMPL DONE — 待 E2 round 1 review
parent dispatch:
  - PM Sprint 2 Wave 2 Track D dispatch（2026-05-22）— api_latency emitter scaffold reuse
  - PA Sprint 2 dispatch packet `docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md` §5 Track D
  - PA Sprint 2 design spec `docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md` §2.1 + §3.2 + §3.4 + §4.3 + AC-1a/AC-1b
runtime: Mac development（Rust 編譯 + sysinfo + tokio test）
production engine: 未碰
---

# E1 Sprint 2 Wave 2 Track D — api_latency emitter IMPL — 2026-05-22

## §1. 5 條完成回報

### 1.1 Scaffold reuse 8/8

| # | Scaffold item | Track D 使用 |
|---|---|---|
| 1 | `DomainEmitter` trait | `impl DomainEmitter for ApiLatencyEmitter`；domain() = ApiLatency / sample_interval_sec() = 60 / sample() 返 8 個 Box<dyn MetricSample> |
| 2 | `MetricSample` trait + `extra_evidence` default None | `impl MetricSample for ApiLatencyMetricRow`；extra_evidence 走 default None（api_latency 無 disconnected 類採樣 audit） |
| 3 | `RollingWindowAggregator`（Bessel sigma） | scheduler 端 lazy 加 metric_name = "rest_p50_ms" / "rest_p95_ms" / ... 8 個 aggregator；5-sample mean classify 走 `classify_aggregated` 端 |
| 4 | `HealthObservationWriter` trait + V106 INSERT | test 端用 `InMemoryHealthObservationWriter`；production 端走 PG writer（不在 Track D scope；main.rs Wave 2 後接） |
| 5 | `HealthEventBus` + `HealthStateChangeEvent` | scheduler 端在 SM fire 時 publish；Track D 不修 event bus |
| 6 | `observe_classified` API + 3 accessor + `is_anomaly_capped` + `last_transition_dwell_secs` | ladder test 直接呼 `sm.observe_classified` 走 OK→WARN（60s dwell）+ WARN→DEGRADED（5min dwell） |
| 7 | `infer_reject_reason` helper | Track D 不重複 emit D3 cascade reject（per scaffold reuse 8/8 第 6 條：D3 cascade reject 屬 Track A SSOT；Track D 走標準 path） |
| 8 | `MetricEmitterScheduler` + `EngineModeProvider` + `classify_aggregated` dispatch | scheduler 端 `classify_aggregated` 加 8 個 `(HealthDomain::ApiLatency, ...)` arm（per Track A round 2 fix `mean.round() as u32` cast pattern） |

**8/8 PASS** — 不重做 trait / writer / event_bus / observe_classified / amp cap。

### 1.2 api_latency.rs LOC + sample fields

| File | LOC | Status |
|---|---|---|
| `rust/openclaw_engine/src/health/domains/api_latency.rs` | 952 | 警告 > 800；< 2000 hard cap（含 8 classify helper + 8 inline unit test + StubSource + emitter struct + impl） |
| `rust/openclaw_engine/tests/sprint2_track_d_api_latency.rs` | 823 | test file 不計 cap |
| `rust/openclaw_engine/src/health/metric_emitter/mod.rs` | 1287（+114） | 警告 > 800；< 2000；新增 8 個 api_latency arm + comment |
| `rust/openclaw_engine/src/health/domains/mod.rs` | 54（並行 atomic edit；最終含 Track D + E + F 全 land） | 微 |

**ApiLatencySample 8 field**（per dispatch packet §5.1）:
| field | type | classify ladder | CRITICAL? |
|---|---|---|---|
| `rest_p50_ms` | u32 | OK<50 / WARN 50-200 / DEGRADED>200 | 無 |
| `rest_p95_ms` | u32 | OK<200 / WARN 200-500 / DEGRADED>500 | 無 |
| `rest_p99_ms` | u32 | OK<500 / WARN 500-1000 / DEGRADED 1000-2000 / CRITICAL>2000 | 有 |
| `ws_rtt_p50_ms` | u32 | OK<50 / WARN 50-150 / DEGRADED>150 | 無 |
| `ws_rtt_p99_ms` | u32 | OK<200 / WARN 200-500 / DEGRADED 500-1500 / CRITICAL>1500 | 有 |
| `ret_code_4xx_count` | u32 | OK 0-10 / WARN 11-50 / DEGRADED>50 | 無 |
| `ret_code_5xx_count` | u32 | OK 0 / WARN 1-5 / DEGRADED 6-20 / CRITICAL>20 | 有 |
| `ws_dropout_count` | u32 | OK 0 / WARN 1-2 / DEGRADED 3-5 / CRITICAL>5 | 有 |

**為什麼 4 個 metric 有 CRITICAL band，4 個沒有**：
- p99 / 5xx / dropout 反映 outlier / venue fault / 持續斷線 — 即時 fail-closed cascade 預警語意（per ADR-0042 Decision 3）。
- p50 / p95 / p50 ws_rtt / 4xx 反映常態退化 — 不誤升 CRITICAL，由 5xx / p99 / dropout 三 metric 走 cascade gate 即足。
- 對齊 Track B `classify_pipeline_throughput_*` 同 pattern（heartbeat / ipc 走 CRITICAL；tick_rate / drift / signal 不走 CRITICAL）。

### 1.3 cargo test result（含 regression）

| Verify | Command | Result |
|---|---|---|
| Track D integration | `cargo test --release --test sprint2_track_d_api_latency` | **7/7 PASS**（ladder / cross_domain / row_count / spike_default_false / real_emitter / arm_wired / degraded_band_classify） |
| Track D inline unit | （由 lib::health tests 整體跑） | **9 個 inline tests** ：8 classify_thresholds（per metric ladder boundary 驗）+ 1 into_metric_rows 8 row + emitter 2 sample-path tests，全 PASS |
| Release build | `cargo build --release` | **PASS** — 40.73s clean；3 pre-existing warning + 1 binary warning；Track D 0 new warning |
| Lib unit tests (health::) | `cargo test --release --lib health::` | **87/87 PASS**（Wave 1 73 + Track D 9 + Track E inline + Track F inline；0 fail） |
| Track A regression | `cargo test --release --test sprint2_track_a_engine_runtime` | **9/9 PASS** — 不退 |
| Track B regression | `cargo test --release --test sprint2_track_b_pipeline_throughput` | **5/5 PASS** — 不退 |
| Track C regression | `cargo test --release --test sprint2_track_c_database_pool` | **8/8 PASS** — 不退 |
| Spike regression | `cargo test --release --features spike --test m3_amp_cap_24h_fire` | **3/3 PASS** — spike default false invariant 守住 |
| AC-5 nm symbol scan | `nm target/release/openclaw-engine \| grep -cE "(mock_instant\|tokio::time::pause\|spike)"` | **0** hit ✓ — production binary 0 mock time 滲透 |

**累計**：Track D 7 + lib 87 + Track A 9 + Track B 5 + Track C 8 + spike 3 = **119 PASS / 0 fail / 0 ignored**。

### 1.4 AC sub-step verify（per dispatch packet §5.4）

| AC | Pass criteria | Result |
|---|---|---|
| **AC-1a in-memory proxy** | cargo test in-memory writer mock fixture row count ≥ 5 | **PASS** — `test_sprint2_track_d_api_latency_row_count`：6s × 1s interval × 8 metric ≥ 48 row（assert ≥ 5 + ≥ 40 雙重守）；OK band sample row.state 全 OK；8 metric_name 全展開 |
| **AC-2 4-state ladder** | api_latency OK→WARN→DEGRADED ladder fire | **PASS** — `test_sprint2_ladder_api_latency`：OK→WARN dwell 60s fire（anomaly_id=`api_latency__rest_p99_ms`）+ WARN→DEGRADED dwell 5min fire（新 anomaly_id=`api_latency__ws_rtt_p99_ms` 避同 id cap）；amplification_loop_24h_count 1→2 |
| **AC-4 cross-domain** | api_latency DEGRADED 不影響 engine_runtime / pipeline_throughput / database_pool state | **PASS** — `test_sprint2_cross_domain_api_latency_independence`：api SM 升 DEGRADED 後 4 個 domain SM 各自獨立；engine/pipeline/database SM state 全 OK；cap count 全 0；domain accessor 各自獨立標籤 |
| **AC-5 spike default false** | `nm target/release/openclaw_engine` 0 hit | **PASS** — nm 0 hit + `test_sprint2_track_d_spike_feature_not_active_in_default_build` default build 跑通（emitter.domain()=ApiLatency / sample_interval=60s） |

**4/4 AC PASS**。

額外守 dispatch arm 不退化（per Track C HIGH-1 retro lesson）：
- `test_sprint2_classify_aggregated_api_latency_arm_wired`：直接呼 `classify_aggregated_for_test` 端到端驗 8 個 api_latency arm dispatch；8 DEGRADED + 4 CRITICAL band 注入；任一 arm 漏接 → 走 fallback OK → assert 失敗；本 round 全 PASS。
- `test_sprint2_track_d_api_latency_degraded_band_classify`：mock emitter 注入 4 DEGRADED + 4 CRITICAL band 走 scheduler → 8 metric 全展開 + classify_aggregated 4 個 CRITICAL band 守 helper 真實接通。

### 1.5 Track D closure verdict + E2 round 1 readiness

- **closure verdict**：DONE — 8 metric 全經 classify_aggregated dispatch（4 metric 含 CRITICAL band）+ ladder OK→WARN→DEGRADED 真實 fire + cross-domain 4 SM 獨立 + AC-5 spike 0 hit。
- **E2 round 1 readiness**：READY — Track D 改動 only / 不破 Wave 1 既有 / regression Track A 9/9 + Track B 5/5 + Track C 8/8 + spike 3/3 不退；nm 0 hit 守住 production binary 0 mock time 滲透。
- **adversarial review**：classify_aggregated_for_test pub re-export 端到端守 8 arm dispatch 真實接通；mock emitter degraded path 端到端驗 metric_name 展開不漏；對齊 Track C round 2 HIGH-2 fix pattern。

## §2. 修改清單（字面 diff 摘要）

| File | 性質 | 改動 |
|---|---|---|
| `rust/openclaw_engine/src/health/domains/api_latency.rs` | **新建** | 952 LOC：MODULE_NOTE / `ApiLatencySample` 8 field struct / `ApiLatencyMetricRow` MetricSample impl / 8 個 `classify_api_latency_*` helper / `ApiLatencySourceProbe` trait 8 method / `ApiLatencyEmitter` struct + impl DomainEmitter (sample_interval=60s) / 9 個 inline unit test（8 classify ladder + 8 row 展開 + 2 emitter sample path） |
| `rust/openclaw_engine/src/health/domains/mod.rs` | atomic edit | 加 `pub mod api_latency;` 一行 + module doc 對應 `api_latency` 子段 4 行（per packet §1.7 scaffold contract）；Track D + E + F 並行 atomic 已全部 land |
| `rust/openclaw_engine/src/health/metric_emitter/mod.rs` | atomic edit | classify_aggregated 加 8 個 `(HealthDomain::ApiLatency, ...)` arm（全走 `mean.round() as u32` cast per Track A round 2 fix；ret_code 4xx/5xx HTTP 標準語意預留 multi-venue per ADR-0040）；前置 comment block 解釋 HTTP 標準 vs Bybit-specific retCode |
| `rust/openclaw_engine/tests/sprint2_track_d_api_latency.rs` | **新建** | 823 LOC：MODULE_NOTE / StubSourceProbe（8 method）/ ladder test（OK→WARN dwell 60s + WARN→DEGRADED dwell 5min）/ cross-domain 4 SM 獨立 test / AC-1a in-memory proxy（6s × 1s mock；8 metric × 5+ tick ≥ 40 row）/ AC-5 spike default false / 端到端 real_emitter test / classify_aggregated arm wired 守 / degraded_band classify stress |

**不動 file**：
- `health/mod.rs` / `health/writer.rs` / `health/event_bus.rs` / `health/domains/pipeline_throughput.rs` / `health/domains/database_pool.rs`（Wave 1 既有）
- `sql/migrations/V106` / `main.rs` / ADR / spec / V###（per scope 不擴大）
- `bybit_rest_client.rs` / `bybit_private_ws.rs`（per packet §5.5 反模式 (a) emitter 只讀）

## §3. 治理對照

| 項目 | 狀態 |
|---|---|
| **§六 Hard Boundaries** | 未碰 `live_execution_allowed` / `execution_authority` / `system_mode` / `max_retries` / production engine / trading_ai DB / V### SQL |
| **§七 Code And Docs Rules** | 新代碼注釋全中文（per `feedback_chinese_only_comments` 2026-05-05）；新 module MODULE_NOTE 完整（用途 / 主要類函數 / 依賴 / 硬邊界 4 段）；無 emoji；bilingual-comment-style：新建注釋默認只中文 |
| **§八 Workflow** | E1 IMPL DONE → 等 E2 round 1 review；不自行 commit；不派下游 sub-agent |
| **§九 Code Structure Guardrails** | api_latency.rs 952 LOC > 800 警告但 < 2000 hard cap；metric_emitter/mod.rs 1287 LOC > 800 警告但 < 2000（scaffold owner 預期 LOC peak）；test file 不計 cap |
| **§Data, Migrations, And Validation** | 本 Track 不新增 V###；V106 schema 沿用；evidence_json 走 default None（api_latency 無 disconnected 類採樣 audit）；不觸 PG dry-run（純 Rust IMPL + mock test） |
| **cross-platform** | 純 Rust 邏輯，不引平台特異 path；trait probe 注入避平台分支；Mac+Linux 共通；不寫 `cfg(target_os = "linux")` |
| **AC-5 production binary 0 mock time 滲透** | nm 0 hit 守住；本 Track 0 spike feature gate；reject_reason / extra_evidence 走 default None 不破壞既有 scaffold 互斥優先級設計 |
| **`feedback_impl_done_adversarial_review`** | 本 Track 改動 = 1 新 file（952 LOC）+ 1 新 test（823 LOC）+ classify_aggregated 加 8 arm + mod.rs 加 1 line + 4 行 doc；屬「共用 helper 之 IPC 邊界擴大」邊緣場景（classify_aggregated 在 scheduler 內部 dispatch；不對外開新公開 API）；E2 round 1 review 應確認 |
| **多角色 adversarial review 原則** | 新增 `test_sprint2_classify_aggregated_api_latency_arm_wired` 端到端守 8 arm dispatch；對齊 Track C round 2 HIGH-2 + Track E/F 同 pattern；任一 arm 退化 → assert 失敗 |
| **反模式對齊（per packet §5.5）** | (a) 未修 bybit_rest_client / bybit_private_ws 既有邏輯 ✓ / (b) sample_interval=60 走 spec §2.1 不寫死 30 ✓ / (c) 沿用 Track A scaffold 8/8 ✓ / (d) ret_code 用 HTTP 標準語意（4xx/5xx）預留 multi-venue per ADR-0040 ✓ / (e) 不引 V### / spike / 跨進程 IPC ✓ / (f) emit V106 row 不寫 live (Sprint 2 走 paper/demo/live_demo only) ✓ |

## §4. 不確定 / Carry-over

1. **ret_code 4xx/5xx 對映由 caller 端負責**：emitter trait `current_ret_code_4xx_count()` / `current_ret_code_5xx_count()` 期望 caller 在 bybit_rest_client wrapper 端把 Bybit retCode 對映到 HTTP class（per ADR-0040 multi-venue gate 預留）。本 Track 不寫對映邏輯；main.rs Wave 2 後接 source probe 時補對映表（Bybit `retCode != 0` + ret_code IN client fault → 4xx；BybitApiError::Business 屬 venue fault → 5xx；具體規約待 BB review）。E2 round 1 應確認此設計合 packet §5.5 反模式 (d) multi-venue gate。
2. **WS RTT probe 接線**：bybit_private_ws 既有 reconnect 邏輯有 ping/pong instrumentation 但無 p50/p99 histogram；main.rs Wave 2 後接 source probe 時 caller 端需在 ws_client wrapper 加 latency histogram（per packet §5.5 反模式 (b) 不擴大此 round IMPL；Sprint 5 cascade IMPL 才接觀測層）。
3. **classify ladder threshold 硬編碼**：per spec §4.3「Sprint 2 先 hardcode；Sprint 5 ArcSwap 熱更新」；本 Track 對齊 Track A/B/C 同 pattern。E2 round 1 應確認 8 個 threshold（特別是 CRITICAL band：rest_p99>2000ms / ws_rtt_p99>1500ms / ret_5xx>20 / dropout>5）合 spec §2.3 ladder + ADR-0042 Decision 3 cascade gate 設計。
4. **classify_aggregated_for_test pub re-export 沿用 Track C round 2 設計**：本 Track 新增 8 arm test 走 `classify_aggregated_for_test` 端到端守 dispatch 真實接通；不改 wrapper 簽名。E2 round 1 應確認此 pub re-export 不破壞 Track A 既有「集中 helper 仍維持 private」契約（per Track C round 2 HIGH-1 fix）。
5. **api_latency.rs 952 LOC 超 800 警告**：8 metric × per-metric 完整 doc comment（rationale + ladder + 為什麼 CRITICAL / 為什麼不 CRITICAL）+ 8 inline unit test（per metric ladder boundary 驗）導致 LOC 較高。E2 round 1 應確認 LOC peak 是否需切 file（建議 不切 — 8 helper / 1 sample / 1 emitter struct 集中在同 module 利於 audit；對比 database_pool.rs 944 LOC 同等規模）。
6. **`reject_reason` 與 `extra_evidence` 互斥優先級**：本 Track 不接 D3 cascade reject path（Track A 既有）；本 Track 不寫 evidence_json extra（api_latency 無 disconnected 類採樣 audit）；reject_reason / extra_evidence 互斥處理由 scheduler 端 Track A round 3 fix 路徑覆蓋。E2 round 1 應確認本 Track 不破此互斥契約。
7. **PG empirical dry-run 未做**：本 round 純 Rust IMPL / mock test；本 round 不新增 V### / 不動 SQL schema；不需 PG empirical 驗（per `feedback_v_migration_pg_dry_run` 適用範圍是 V### migration with PG reflection；本 round 不觸）。AC-1b real PG empirical 由 Phase 3c QA 走（前置 = main.rs scheduler 接線完成）。
8. **並行 atomic edit race**：Wave 2 Track D + E + F 並行 atomic edit `domains/mod.rs` 加 `pub mod` 條目 + classify_aggregated arm；本 Track 初次 cargo build 因 Track E `strategy_quality.rs` source 尚未 land 而失敗（mod 條目已聲明，source 未到）；等 Track E sub-agent commit 後 lib build 恢復；Track D test 全 PASS。E2 round 1 應確認此 race 屬正常並行 atomic edit 模式（per spec §4.3 「stagger 5min dispatch」 mitigation）。

## §5. Operator 下一步

1. **PM 派 E2 round 1 review**：focus on
   - 8 metric ladder threshold 是否合 M3 design spec §2.3 + ADR-0042 Decision 3 cascade gate（特別 CRITICAL band：rest_p99>2000ms / ws_rtt_p99>1500ms / ret_5xx>20 / dropout>5）
   - HTTP 4xx/5xx 標準語意對映 multi-venue 設計（per ADR-0040 packet §5.5 反模式 (d)）；BB 端是否需 review caller 端對映表設計
   - `classify_aggregated_for_test` 端到端守 8 arm 是否充分（對齊 Track C round 2 HIGH-2 fix pattern）
   - api_latency.rs 952 LOC 是否需切 file（不切 vs 切 8 helper 至 sub-module）
   - 反模式 (a)-(f) 6 條對齊是否完整
2. **A3 review 路徑**：本 Track 不動 GUI / IPC / 寫操作；A3 沿用「0 GUI 改動」結案；若 E2 round 1 認定 classify_aggregated 8 arm 擴增屬「共用 helper 之邊界擴大」，可派 A3 對抗性核驗（per `feedback_impl_done_adversarial_review` 2026-05-09）；本 Track 不主動派下游。
3. **Track D + Track E + Track F closure 同步**：Wave 2 3 並行；E2 review × 3 並行（per spec §4.3）；PM 收口 commit chain 等 Wave 2 整 3 Track E2 review 全 PASS 後 PM 統一 commit + push（強制鏈 E1→E2→E4→QA→PM）。
4. **PM 確認 PA spec amend 全 closure**：本 Track 不動 PA spec doc / ADR-0042 / V### SQL；E1 round 1 對齊 spec §2.1 + §3.2 + §3.4 + §4.3 + AC-1a/AC-1b；無 carry-over PA task。
5. **BB review 預警**：Track D 採樣含 Bybit retCode → HTTP class 對映（caller 端責任；本 Track 不寫對映表）；BB 端應在 caller 端對映表階段參與 review，本 round 不阻 E2 review。

---

**E1 IMPLEMENTATION DONE: 待 E2 round 1 review（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave2_track_d_api_latency.md`）**
