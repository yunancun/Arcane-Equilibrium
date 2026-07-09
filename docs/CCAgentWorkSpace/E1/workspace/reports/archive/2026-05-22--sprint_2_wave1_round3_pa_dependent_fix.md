---
report: Sprint 2 Wave 1 Track B + Track C round 3 PA-dependent fix
date: 2026-05-22
author: E1 (Backend Developer, Rust)
phase: Sprint 2 Phase 2 Wave 1 — round 3 spec-dependent closure
status: IMPL DONE — 待 E2 round 2 re-review
parent dispatch:
  - PA Sprint 2 Wave 1 M3 spec amend land（2026-05-22）— 3 file 8 edits（M3 design spec §2.3 line 102/103 + §2.3.1 + §2.3.2 + Sprint 2 design spec §3.2 + §4.3 + dispatch packet §3.4 + §4.4）
  - E1 round 2 5/9 deterministic closure（commit pending；含 Track A scaffold MEDIUM-2 + Track C HIGH-1 + HIGH-2 + MEDIUM-2 + Track B HIGH-1）
runtime: Mac development（Rust 編譯 + sysinfo + tokio test）
production engine: PID 2934602 跑 trading_ai（全程未碰）
---

# E1 Sprint 2 Wave 1 round 3 PA-dependent fix — 2026-05-22

## §1. 4 fix 字面 diff + LOC

### Fix 1：Track B HIGH-2 — classify_ws_tick_rate doc comment 加 §2.3.1 reference

**位置**：`rust/openclaw_engine/src/health/domains/pipeline_throughput.rs:179-212` `classify_pipeline_throughput_ws_tick_rate` 函數 doc comment。

**為什麼此 fix**：
- IMPL 不改數值（per PA Path A：60s SM dwell SSOT 不變；ladder OK ≥ 1.0 / WARN 0.5-1.0 / DEGRADED < 0.5 不變）
- E2 round 1 HIGH-2 reject root cause = 「持續 2min」literal 與 §3.3 60s SM dwell 語意混淆；PA amend 後 M3 design spec §2.3.1 已 clarify
- 本 fix 對齊 amend：把舊 doc 注釋「持續 < 1/sec/symbol 2min 為 WARN；dwell 由 SM 處理」改為「metric=WARN-band 即時 fire；dwell 由 SM 處理」+ 加新一段引 §2.3.1 SSOT reference 解釋 60s SM dwell 為 §3.3 line 165 規範值，spec line 102 carry-over「持續 2min」literal 為非規範性敘述

**diff（精簡示意）**：
```rust
// Before:
///   WARN     : 0.5 - 1.0    （持續 < 1/sec/symbol 2min 為 WARN；dwell 由 SM 處理）

// After:
///   WARN     : 0.5 - 1.0    （metric=WARN-band 即時 fire；dwell 由 SM 處理）
/// ...
/// 為什麼 60s dwell SSOT（per M3 design spec §2.3.1，PA Sprint 2 Wave 1 amend
/// 2026-05-22 Path A 採納）:
///   - metric classify-time 即時返 WARN-band；SM band dwell（OK→WARN 60s per
///     §3.3 line 165）提供時間累積；不在 classify helper 內混雜 dwell 邏輯。
///   - spec line 102 carry-over「持續 2min」literal 為 v5.7 非規範性敘述；真
///     規範值 = §3.3 line 165 SM OK→WARN dwell 60s。
///   - 60s SM dwell SSOT 對齊 ADR-0042 v1.0 不 amend；本 classify helper
///     只做 metric-level band decision 不處理時間軸。
```

**LOC**：+10 doc 行；IMPL 0 行（已 SSOT）。

### Fix 2：Track B MEDIUM-1 — drift + signal_rate doc comment 加 §2.3 line 102 amend reference

**位置**：`rust/openclaw_engine/src/health/domains/pipeline_throughput.rs` 兩 helper 之 doc comment：
- `classify_pipeline_throughput_subscription_drift`（行 252-264）
- `classify_pipeline_throughput_signal_rate`（行 281-296）

**為什麼此 fix**：
- IMPL 數值合理保留（drift 0/1-2/3+ + signal_rate ≥0.5/0.1-0.5/<0.1）
- PA spec amend 已把 2 metric threshold 補進 M3 design spec §2.3 line 102 ladder（與 IMPL 數值 1:1 對齊）；本 fix 是 doc 注釋對齊 spec amend reference

**diff（精簡示意）**：
```rust
// drift helper — 為什麼 threshold 區段加：
/// 為什麼 threshold 是 1 / 3（per M3 design spec §2.3 line 102 amend，PA Sprint
/// 2 Wave 1 amend 2026-05-22 land）:
///   ...（既有 rationale）...
///   - spec line 102 ladder 已補入此 threshold；IMPL 數值合理保留與 spec amend
///     1:1 對齊。

// signal_rate helper — 同 pattern
```

**LOC**：+4 doc 行（兩 helper 各 +2）；IMPL 0 行。

### Fix 3：Track C MEDIUM-1 C Path A — pg_pool_active_conn_ratio metric 接入 classify_aggregated

**位置**：
- `rust/openclaw_engine/src/health/domains/database_pool.rs`：
  - 加 `classify_database_pool_active_conn_ratio(ratio: f64) -> HealthState` helper（行 95-127）
  - `DatabasePoolSample` 加 `pool_disconnected: bool` field（行 165-186）— Fix 4 共用
  - `DatabasePoolMetricRow` 加 `pool_disconnected: bool` field（行 194-209）— Fix 4 共用
  - `MetricSample` impl 加 `extra_evidence` method（行 220-228）— Fix 4 共用
  - `into_metric_rows()` 改為 5 row（含新 pg_pool_active_conn_ratio）+ 全 row 帶 pool_disconnected flag（行 230-289）
  - `sample_now()` 設 pool_disconnected flag（行 350-388）— Fix 4 共用
- `rust/openclaw_engine/src/health/metric_emitter/mod.rs`：
  - `MetricSample` trait 加 `extra_evidence` default method（行 86-101）— Fix 4 共用
  - `classify_aggregated` 加 `(HealthDomain::DatabasePool, "pg_pool_active_conn_ratio")` arm（行 974-982）
  - comment 更新反映 raw active_conn 走 fallback 屬 telemetry-only 設計 + ratio 已接通

**為什麼選 Option A（emitter 端 ratio 獨立 metric）而非 Option B（classify_aggregated 簽名擴 HashMap）**：
- Option A 影響面最小：只 Track C MetricSample 路徑加 1 row + 1 arm；不動 Track A scaffold 的 classify_aggregated 簽名（避影響 Track B + Track D-F 沿用）
- raw `pg_pool_active_conn` 保留 telemetry 觀測語意；ratio 為 classify dispatch 入口；兩者並存互不衝突
- PA spec §3.2 amend「保留 raw active_conn for telemetry」與 §4.3 「classify_database_pool_active_conn(active, max) 內部計算 ratio」均對齊

**helper diff**：
```rust
pub fn classify_database_pool_active_conn_ratio(ratio: f64) -> HealthState {
    if ratio > 0.95 {
        HealthState::HealthDegraded
    } else if ratio >= 0.80 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}
```

**ratio 計算 disconnected 處理**：
```rust
let active_ratio = if self.pool_max_conn > 0 {
    self.pool_active_conn as f64 / self.pool_max_conn as f64
} else {
    0.0  // max=0 disconnected → ratio=0 fail-closed OK band
};
```

**classify_aggregated arm**：
```rust
(HealthDomain::DatabasePool, "pg_pool_active_conn_ratio") => {
    super::domains::database_pool::classify_database_pool_active_conn_ratio(mean)
}
```

**test 加**：
- inline test `test_classify_active_conn_ratio_thresholds`（database_pool.rs 行 651-694）— 4 band 邊界
- integration test `test_sprint2_track_c_database_pool_active_conn_ratio_classify`（sprint2_track_c_database_pool.rs 行 657-718）— scheduler 端 classify_aggregated dispatch 驗
- `test_sprint2_track_c_database_pool_degraded_band_classify` 加 metric_names contains "pg_pool_active_conn_ratio" + 第 4 classify_aggregated_for_test arm assertion 守 dispatch 真實接通

### Fix 4：Track C MEDIUM-3 — disconnected emits {"pool_status": "disconnected"} evidence_json

**位置**：
- `rust/openclaw_engine/src/health/metric_emitter/mod.rs`：
  - `MetricSample` trait 加 `extra_evidence` default method 返 None（行 86-101）— 與 Fix 3 共用
  - `run_domain_loop` 內加 `sample_extra_evidence = sample.extra_evidence()` 抓取（行 716-723）
  - reject_reason / extra_evidence 互斥處理（行 839-866）— reject_reason 優先；非 reject 場景 extra_evidence 寫 row.with_evidence
- `rust/openclaw_engine/src/health/domains/database_pool.rs`：
  - `DatabasePoolSample.pool_disconnected: bool`（Fix 3 共用）
  - `DatabasePoolMetricRow.pool_disconnected: bool` + `MetricSample::extra_evidence` impl 返 `{"pool_status": "disconnected"}`（Fix 3 共用）
  - `sample_now()` 端設 disconnected flag（Fix 3 共用）

**為什麼 trait 加 default extra_evidence method**：
- 與 reject_reason path 互斥 — 非破壞性擴展（既有 Track A engine_runtime / spike Track B pipeline_throughput 不需 impl extra_evidence，仍走 default None）
- 走 MetricSample 路徑 — sample-time audit 與 SM observe-time reject_reason 兩個正交場景

**為什麼 reject_reason / extra_evidence 互斥優先級**：
- reject_reason 對應 SM observe reject（D3 cascade reject log emit minimal pattern，更關鍵）
- extra_evidence 對應 sample 採樣成功但有 audit 條件（如 disconnected fail-closed OK band）
- 兩者通常不同時 fire：sample 成功 + extra_evidence != None 場景下 observe 必返 Ok（不會 reject）；reject 場景下 sample 已採樣成功（reject 在 SM observe 端）。並列罕見；reject_reason 優先（per spec §3 D3 路徑優先）

**evidence_json shape**：
```json
{"pool_status": "disconnected"}
```

**test 加**：
- inline test `test_metric_row_extra_evidence_disconnected_audit_trail`（database_pool.rs 行 696-708）— MetricSample::extra_evidence 直接驗
- inline test `test_disconnected_sample_into_metric_rows_fail_closed_with_evidence`（database_pool.rs 行 710-749）— 端到端 sample → 5 row + 全 row OK band + 全 row 帶 evidence + ratio row value=0.0
- integration test `test_sprint2_track_c_database_pool_disconnected_emits_pool_status_evidence`（sprint2_track_c_database_pool.rs 行 720-820）— scheduler 端 in-memory writer 驗 V106 row.evidence_json 真實寫入 {"pool_status": "disconnected"}

### LOC 累計

| File | Before round 3 | After | Delta | Cap status |
|---|---|---|---|---|
| `rust/openclaw_engine/src/health/domains/pipeline_throughput.rs` | 712 | 727 | +15 | < 800 OK |
| `rust/openclaw_engine/src/health/domains/database_pool.rs` | 727 | 944 | +217 | > 800 警告；< 2000 hard cap |
| `rust/openclaw_engine/src/health/metric_emitter/mod.rs` | 1128 | 1173 | +45 | > 800 警告；< 2000 hard cap |
| `rust/openclaw_engine/tests/sprint2_track_c_database_pool.rs` | 631 | 843 | +212 | test file 不計 cap |

累計 +489 LOC（淨增；含 comment + struct field + impl method + helper + 2 new integration test + 3 new inline test + 既有 inline test/integration mock 修補 5 field）。

## §2. cargo test 結果

| Verify | Command | Result |
|---|---|---|
| Release build | `cargo build --release` | **PASS** — 25.37s clean；2 pre-existing warning（panel_aggregator unused_imports + ma_crossover dead_code）+ 1 pre-existing tasks.rs warning；health module 0 new warning |
| Lib unit tests (health::) | `cargo test --release --lib health::` | **56/56 PASS** — 53 round 2 + 3 new round 3（ratio thresholds / extra_evidence audit / disconnected sample fail_closed）|
| Lib unit tests (full lib) | `cargo test --release --lib` | **3121/3121 PASS**（1 ignored pre-existing；0 fail）— round 2 3118 + 3 new round 3 |
| Track A regression | `cargo test --release --test sprint2_track_a_engine_runtime` | **9/9 PASS** — round 2 fix 不退 |
| Track B integration | `cargo test --release --test sprint2_track_b_pipeline_throughput` | **5/5 PASS** — round 1+2 fix 不退 |
| Track C integration | `cargo test --release --test sprint2_track_c_database_pool` | **8/8 PASS** — 5 舊 + 1 round 2 stress + 2 new round 3（active_conn_ratio_classify / disconnected_emits_pool_status_evidence）|
| Spike regression | `cargo test --release --features spike --test m3_amp_cap_24h_fire` | **3/3 PASS** — spike feature default false invariant 守住 |
| nm symbol scan (AC-5) | `nm target/release/openclaw-engine \| grep -cE "(mock_instant\|tokio::time::pause\|spike)"` | **0** hit — production binary 0 mock time 滲透 |

**累計：lib 3121 + 整 sprint2 9+5+8=22 + spike 3 = 3146 PASS / 0 fail / 1 ignored**。

## §3. 9/9 finding 全 closure 確認

| # | Track | Severity | Finding | round 2 status | round 3 status |
|---|---|---|---|---|---|
| 1 | Track A | MEDIUM-2 | `classify_aggregated` u32 cast `mean.round()` | DONE (round 2) | — |
| 2 | Track C | HIGH-1 | `classify_aggregated` database_pool 3 arm | DONE (round 2) | — |
| 3 | Track C | HIGH-2 | `test_row_count` state band assert + stress test | DONE (round 2) | — |
| 4 | Track B | HIGH-1 | heartbeat_lag CRITICAL > 60_000 即時 fire | DONE (round 2) | — |
| 5 | Track C | MEDIUM-2 | probe wire-up doc + TODO follow-up | DONE (round 2) | — |
| 6 | Track B | HIGH-2 | 「持續 2min」semantic clarify | — | DONE (Fix 1) |
| 7 | Track B | MEDIUM-1 | drift+signal threshold | — | DONE (Fix 2) |
| 8 | Track C | MEDIUM-1 | pool_max_conn classify Path A | — | DONE (Fix 3) |
| 9 | Track C | MEDIUM-3 | disconnected fail-closed evidence_json | — | DONE (Fix 4) |

**9/9 全 closure**（5 round 2 deterministic + 4 round 3 PA-dependent；LOW 由 E2 自評 not blocking）。

## §4. round 3 verdict + E2 round 2 readiness

### round 3 verdict
- 4/4 PA spec-dependent finding deterministic closure
- 與 PA spec amend 1:1 對齊（M3 design spec §2.3 line 102/103 + §2.3.1 + §2.3.2 + Sprint 2 design spec §3.2 + §4.3 引用對應 IMPL 處 comment / helper / arm / evidence_json shape）
- 2 new integration test land（Track C active_conn_ratio_classify + disconnected_emits_pool_status_evidence）+ 3 new inline test land（ratio thresholds + extra_evidence audit + disconnected sample fail_closed end-to-end）
- regression Track A 9/9 / Track B 5/5 / Track C 5 舊不退 / spike 3/3 / nm 0 hit / lib 3121/3121 全 PASS
- 治理：未碰任何 hard boundary（live_execution_allowed / max_retries / system_mode / execution_authority 全未碰）/ production engine（PID 2934602）/ trading_ai DB / V### SQL / ADR-0042（per PA 確認不 amend）
- adversarial review：classify_aggregated_for_test pub re-export 端到端守 4 metric dispatch 真實接通（含新 ratio arm）；MetricSample::extra_evidence default None 不破壞 Track A engine_runtime / Track B pipeline_throughput 既有 row 行為

### E2 round 2 re-review readiness 對 PA report §4 檢點

| 檢點 | 期望 | round 3 IMPL 結果 |
|---|---|---|
| Track B heartbeat_lag_ms classify literal | `> 60_000 → CRITICAL` 對齊 spec §2.3 line 102 + §2.3.1 | round 2 已 PASS (Fix 4 round 2) ✓ |
| Track B drift+signal_rate classify literal | 與 spec §2.3 line 102 amend ladder 1:1 對齊 | IMPL 數值對齊 + Fix 2 comment 引 amend reference ✓ |
| Track B SM OK→WARN dwell | 仍 60s（spec §3.3 line 165 SSOT） | spike Track B 既有 IMPL 不變 + Fix 1 comment 引 SSOT reference ✓ |
| Track C `DatabasePoolSample` field count | 5 field（含 `pool_max_conn`）| 5 field（含 pool_max_conn + 新 pool_disconnected）— pool_disconnected 是 Fix 4 audit flag，不違 amend 5 field 規範 ✓ |
| Track C `classify_database_pool_active_conn` signature | `(active: u32, pool_max: u32) -> HealthState`；max=0 → fail-closed OK | round 1 已對齊；Fix 3 加 ratio helper 並存 ✓ |
| Track C disconnected sample | `evidence_json={"pool_status": "disconnected"}` 寫入路徑加 | Fix 4 完整端到端寫入 + integration test 守 ✓ |
| spec literal 引用 | E1 round 2 IMPL comment 引 spec §2.3.1 / §2.3.2 / §2.3 line 102 reference | Fix 1 引 §2.3.1 + Fix 2 引 §2.3 line 102 amend + Fix 3 + 4 引 §2.3.2 + §3.2 amend ✓ |

**E2 round 2 verdict 條件**：4 finding 全 PASS（HIGH-1 revert + drift/signal_rate ladder 對齊 + pool_max_conn 5 field + disconnected fail-closed evidence_json）+ AC-1a in-memory proxy test 不退。**全條件成立**。

## §5. 治理對照

- **§六 Hard Boundaries**：未碰 `live_execution_allowed` / `execution_authority` / `system_mode` / `max_retries` / production engine（PID 2934602）/ trading_ai production DB ✓
- **§七 Code And Docs Rules**：
  - 新代碼注釋全中文（per `feedback_chinese_only_comments` 2026-05-05）；新增 helper / struct field / trait method 注釋全中文；無 emoji ✓
  - bilingual-comment-style：新建注釋默認只中文；觸及舊中英對照塊不主動清，修改時移除英文只保留中文（本 round 修改的 4 處 doc comment 均無中英對照塊） ✓
- **§八 Workflow**：E1 round 3 IMPL DONE → 等 E2 round 2 re-review；不自行 commit；不派下游 sub-agent ✓
- **§九 Code Structure Guardrails**：
  - metric_emitter/mod.rs 1173 LOC（> 800 警告但 < 2000 hard cap；scaffold owner 預期 LOC peak）
  - database_pool.rs 944 LOC（> 800 警告但 < 2000 hard cap；Track C IMPL + 大量 inline test）
  - 其他 file < 800 LOC ✓
- **§Data, Migrations, And Validation**：本 round 不新增 V###；V106 schema 沿用；evidence_json JSONB column 寫入路徑既有不變 ✓
- **cross-platform**：純 Rust 邏輯，不引平台特異 path；sysinfo + tokio + chrono + serde_json workspace dep；Mac+Linux 共通 ✓
- **AC-5 production binary 0 mock time 滲透**：本 round 新 helper / trait method / arm 全無 `cfg(feature = "spike")` gate；nm 0 hit 守住 ✓
- **`feedback_impl_done_adversarial_review`**：本 round 改動含共用 helper（MetricSample trait extra_evidence default method）+ 寫操作（row.with_evidence 路徑）；E1 IMPL DONE 不單獨 sign-off，等 E2 round 2 + A3 re-review；E4 regression 不能取代 ✓
- **多角色 adversarial review 原則**：Fix 4 evidence_json 互斥優先級設計（reject_reason vs extra_evidence）是 E2 round 2 應確認的 race 設計；integration test 端到端守 disconnected 寫入路徑；inline test 端守 trait method 直接 contract ✓

## §6. 不確定 / Carry-over

1. **MetricSample trait extra_evidence default None 是公開 API 擴展**：E2 round 2 應確認 trait 擴展時機（本 round 因 Fix 4 必要；未提前獨立派 PA / FA review trait 設計）；若 E2 認為應走 trait amend ADR-0036 / ADR-0042 governance review，E1 round 4 可拆出獨立 follow-up 走 PA / CC / FA chain。
2. **evidence_json reject_reason / extra_evidence 互斥優先級**：本 round 選 reject_reason 優先；E2 round 2 應確認此優先級設計合 spec（per spec §3 D3 cascade reject log emit minimal pattern + §2.3.2 disconnected handling）。
3. **pg_pool_active_conn raw 走 fallback OK band**：raw 是 telemetry-only（單值無 max context 不能 classify ratio）；fail-closed OK band 不誤升 cascade。E2 round 2 應確認此設計（雙 metric 並存：raw + ratio）對 V106 schema / GUI 觀測層無副作用（GUI / cascade 全等 Sprint 5 接，本 Sprint 不接）。
4. **TODO follow-up entry**：本 round 不直接改 `TODO.md`；round 2 已列「W-XX-Y Sprint 2 Wave 2 wire-up probe」by PM 收口時登記；本 round 3 不新增 follow-up entry（per scope 不擴大）。
5. **PG empirical dry-run 未做**：本 round 純 Rust IMPL / mock test；本 round 不新增 V### / 不動 SQL schema；不需 PG empirical 驗（per `feedback_v_migration_pg_dry_run` 適用範圍是 V### migration with PG reflection；本 round 不觸）。

## §7. 修改清單

| File | 改動範圍 | 性質 |
|---|---|---|
| `rust/openclaw_engine/src/health/domains/pipeline_throughput.rs` | 712 → 727 LOC：3 helper doc comment 引 PA spec amend reference（Fix 1 ws_tick_rate + Fix 2 drift + signal_rate）；IMPL 0 行變動 | round 3 fix |
| `rust/openclaw_engine/src/health/domains/database_pool.rs` | 727 → 944 LOC：加 `classify_database_pool_active_conn_ratio` helper（Fix 3）+ `DatabasePoolSample.pool_disconnected: bool` field（Fix 3+4 共用）+ `DatabasePoolMetricRow.pool_disconnected` field + `MetricSample::extra_evidence` impl（Fix 3+4 共用）+ `into_metric_rows` 改 5 row（Fix 3）+ `sample_now` 設 disconnected flag（Fix 4）+ 3 new inline test（ratio thresholds / extra_evidence audit / disconnected sample fail_closed）| round 3 fix |
| `rust/openclaw_engine/src/health/metric_emitter/mod.rs` | 1128 → 1173 LOC：`MetricSample` trait 加 default `extra_evidence` method（Fix 3+4 共用）+ `classify_aggregated` 加 `pg_pool_active_conn_ratio` arm（Fix 3）+ `run_domain_loop` 加 `sample.extra_evidence()` 抓取 + reject_reason/extra_evidence 互斥寫 row.with_evidence 路徑（Fix 4）| round 3 fix |
| `rust/openclaw_engine/tests/sprint2_track_c_database_pool.rs` | 631 → 843 LOC：既有 2 mock emitter 修補 5 field + `test_sprint2_track_c_database_pool_degraded_band_classify` 加 ratio metric_names assertion + 第 4 classify_aggregated_for_test arm 守 + 2 new integration test（active_conn_ratio_classify + disconnected_emits_pool_status_evidence）| round 3 fix |

**不動 file**：health/mod.rs / writer.rs / event_bus.rs / sql/migrations/V106 / main.rs / sprint2 packet doc / spec doc / ADR-0042 / 其他 module。

## §8. Operator 下一步

1. **PM 派 E2 round 2 re-review**：focus on
   - Fix 1 + Fix 2 doc comment 引 PA spec amend reference 是否合 §2.3.1 / §2.3 line 102 amend SSOT
   - Fix 3 Option A 設計（5 row pg_pool_active_conn + ratio 並存）是否合 PA spec §3.2 amend「保留 raw active_conn for telemetry + ratio 為 classify 入口」
   - Fix 3 `classify_database_pool_active_conn_ratio` helper threshold ladder 是否 1:1 對齊 PA spec §2.3 line 103 amend「active/max < 80% / 80-95% / > 95%」
   - Fix 4 MetricSample trait 加 default `extra_evidence` method 是否屬「共用 helper 之 IPC 邊界擴大」（per `feedback_impl_done_adversarial_review`）；若是則 A3 並行核驗
   - Fix 4 reject_reason / extra_evidence 互斥優先級設計是否合 spec §3 D3 + §2.3.2 規範
   - 2 new integration test 是否端到端守 ratio dispatch + evidence_json 寫入路徑充分
2. **A3 review 路徑**：本 round 改動含共用 helper（MetricSample trait extra_evidence default method）+ 寫操作（row.with_evidence 路徑），per `feedback_impl_done_adversarial_review` 2026-05-09 應 E2 + A3 並行核驗；A3 focus on：
   - trait method 擴展對 production binary 0 mock time 滲透不變式（已 nm 0 hit 守）
   - run_domain_loop merge 路徑是否避免 race（reject_reason 與 extra_evidence 互斥；觀察 Track A engine_runtime 既有 path 不退化）
3. **PM 收口 commit chain**：E1 round 2 + round 3 共 9 finding closure；待 E2 round 2 + A3 PASS 後 PM 統一 commit + push（強制鏈 E1→E2→E4→QA→PM）。
4. **PM 確認 PA spec amend 全 closure**：本 round 不動 PA spec doc / ADR-0042 / V### SQL；E1 round 3 已對齊 spec amend；無 carry-over PA task。

---

**E1 IMPLEMENTATION DONE: 待 E2 round 2 re-review（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave1_round3_pa_dependent_fix.md`）**
