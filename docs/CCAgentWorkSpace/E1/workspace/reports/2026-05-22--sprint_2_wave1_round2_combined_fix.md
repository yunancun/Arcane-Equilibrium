---
report: Sprint 2 Wave 1 Track A scaffold round 3 + Track B + Track C round 2 combined fix
date: 2026-05-22
author: E1 (Backend Developer, Rust)
phase: Sprint 2 Phase 2 Wave 1 — round 2 deterministic combined fix
status: IMPL DONE — awaiting E2 round 2 re-review
parent dispatch:
  - E2 round 1 Track B REJECT（HIGH-1 ladder + HIGH-2 持續 2min + MEDIUM-1 threshold + MEDIUM-2 + LOW）
  - E2 round 1 Track C REJECT（HIGH-1 classify_aggregated 漏 arm + HIGH-2 test 無 state band assert + MEDIUM-1 pool_max + MEDIUM-2 probe wire-up + MEDIUM-3 disconnected + LOW）
  - PA spec amend 並行（HIGH-2 dwell / MEDIUM-1 drift threshold / MEDIUM-1 C pool_max Path A/B / MEDIUM-3 disconnected Path A/B）
runtime: Mac development（sysinfo + Rust 編譯）
production engine: PID 2934602 跑 trading_ai（全程未碰）
---

# E1 Sprint 2 Wave 1 round 2 combined fix — 2026-05-22

## §1. 5 deterministic fix 完成

| # | Track | Severity | Finding | Fix status | LOC diff（淨增） |
|---|---|---|---|---|---|
| 1 | Track A | MEDIUM-2 | `classify_aggregated` u32 cast 用 `mean.round()` 取代 `as u32` truncate | DONE | +12（含 comment） |
| 2 | Track C | HIGH-1 | `classify_aggregated` 加 `database_pool` 3 match arm（pg_pool_active_conn 延 PA spec amend MEDIUM-1 C Path） | DONE | +28（含 comment + pub re-export） |
| 3 | Track C | HIGH-2 | `test_row_count` 加 `assert_eq!(row.state, HealthState::HealthOk)` + 新 stress test `test_sprint2_track_c_database_pool_degraded_band_classify` 守 HIGH-1 不退化 | DONE | +172 test LOC |
| 4 | Track B | HIGH-1 | `classify_pipeline_throughput_heartbeat_lag_ms` revert ladder 三段對齊 spec line 102 SSOT「WS dropout > 60s = CRITICAL」即時 fire | DONE | -8 helper / +12 test 對應 |
| 5 | Track C | MEDIUM-2 | `database_pool.rs` module-level doc 補 probe wire-up 警告 block；report 載明 TODO follow-up「W-XX-Y Wave 2 wire-up probe + healthcheck」 | DONE | +16 doc |

## §2. 字面 diff（per fix）

### Fix 1：Track A scaffold MEDIUM-2 mean.round() cast

**位置**：`rust/openclaw_engine/src/health/metric_emitter/mod.rs` `classify_aggregated` 內所有 u32 / u64 cast。

**Before**：
```rust
(HealthDomain::EngineRuntime, "open_fd_count") => {
    classify_engine_runtime_open_fd_count(mean as u32)
}
(HealthDomain::EngineRuntime, "thread_count") => {
    classify_engine_runtime_thread_count(mean as u32)
}
(HealthDomain::EngineRuntime, "uptime_sec") => {
    if (mean as u64) < 60 { HealthState::HealthWarn } else { HealthState::HealthOk }
}
(HealthDomain::PipelineThroughput, "ws_heartbeat_lag_ms") => {
    classify_pipeline_throughput_heartbeat_lag_ms(mean as u32)
}
(HealthDomain::PipelineThroughput, "ws_subscription_drift_count") => {
    classify_pipeline_throughput_subscription_drift(mean as u32)
}
```

**After**：5 處全改 `mean.round() as u32` / `mean.round() as u64`；每處加注釋說明「count 類 metric mean=2.8 round=3 為 DEGRADED；truncate=2 誤歸 WARN」。

**為什麼此 fix 不破壞既有 test**：
- 既有 unit test 注入 mean = integer 值（`30_000` / `0` 等），round 與 truncate 同值。
- 既有 integration test 注入 OK band sample 連續同值，mean = sample 值（整數），round 與 truncate 同值。
- Fix 解決的是「mean 在 ladder boundary 附近的小數 sample」場景（per dispatch range `[3,3,3,3,2]` mean=2.8 example）；既有 test 不觸 boundary，無回歸。

### Fix 2：Track C HIGH-1 classify_aggregated 加 database_pool 3 match arm

**位置**：`rust/openclaw_engine/src/health/metric_emitter/mod.rs` `classify_aggregated` `_ => HealthOk` 前。

**Before**：`pipeline_throughput` 5 arm 後直接 `_ => HealthOk`，**database_pool 全部 metric 被 fallback `_` catches 為 OK band** — production scheduler 走 5-sample mean 後 4 metric（active / wait / queue / disk）全 OK，永遠看不到 WARN/DEGRADED 升階。

**After**：加 3 個 `(HealthDomain::DatabasePool, ...)` arm：
```rust
(HealthDomain::DatabasePool, "pg_pool_wait_ms_p95") => {
    classify_database_pool_wait_ms_p95(mean.round() as u32)
}
(HealthDomain::DatabasePool, "pg_writer_queue_depth") => {
    classify_database_pool_writer_queue_depth(mean.round() as u32)
}
(HealthDomain::DatabasePool, "disk_data_dir_used_pct") => {
    classify_database_pool_disk_used_pct(mean)
}
```

**為什麼 `pg_pool_active_conn` 暫缺 arm（仍走 `_ => HealthOk`）**：
- `classify_database_pool_active_conn` 簽名為 `(active: u32, pool_max: u32)`；`classify_aggregated` 只有 `(domain, metric_name, mean)` 三參，缺 `pool_max` context。
- pool_max 注入路徑由 PA spec amend MEDIUM-1 C Path A/B 拍板後 E1 round 3 補（`scheduler::run_domain_loop` 端帶上下文 / 5th column / 或 emitter-level classify）。
- 本 round 不擅自插 placeholder 路徑（如 hardcode pool_max=10），避免引入第二個 silent failure；保留為 `_` fallback 待 PA 拍板。
- 風險可控：pg_pool_active_conn 一 metric 暫 OK band 不會誤升 cascade，且本 round 加的 3 個 helper 已守住 wait/queue/disk 真實升階 path。

**為什麼加 pub re-export `classify_aggregated_for_test`**：
- 集中 helper 仍維持 `fn` private 封裝（不洩漏 routing 細節）；integration test 需端到端驗 dispatch 真實接通 helper 而非走 fallback。
- 命名顯式 `_for_test` 表達意圖；production code path 仍走 private `classify_aggregated`。
- 附 `#[doc(hidden)]` 避免被 rustdoc 列為公開 API。

### Fix 3：Track C HIGH-2 test_row_count 加 state band assert + 新 stress test

**位置**：`rust/openclaw_engine/tests/sprint2_track_c_database_pool.rs`。

**A. `test_sprint2_track_c_database_pool_row_count` 加 state assert**：
```rust
for row in writer.snapshot() {
    assert_eq!(row.domain, HealthDomain::DatabasePool);
    assert_eq!(row.engine_mode, "demo", "Sprint 2 不寫 live");
    assert_eq!(
        row.state,
        HealthState::HealthOk,
        "OK-band sample 不應升階 SM state: metric={}",
        row.metric_name
    );
}
```

**B. 新 stress test `test_sprint2_track_c_database_pool_degraded_band_classify`**：
- mock emitter 注入 DEGRADED-band sample：`pool_active=18/20, wait=900ms, queue=8000, disk=92%`。
- scheduler 跑 7s (interval=1s)，5-sample rolling window 滿後 mean = sample 值。
- 4 metric_name 必展開（不漏 metric）。
- **核心 HIGH-1 守**：直接呼 `classify_aggregated_for_test` 對 3 個 dispatched arm（wait/queue/disk）：
  ```rust
  assert_eq!(
      classify_aggregated_for_test(HealthDomain::DatabasePool, "pg_pool_wait_ms_p95", 900.0),
      HealthState::HealthDegraded,
      "classify_aggregated database_pool::pg_pool_wait_ms_p95 arm 必走 helper（HIGH-1 退化守）"
  );
  // 同樣對 pg_writer_queue_depth + disk_data_dir_used_pct
  ```
- 若 HIGH-1 退化（database_pool arm 被刪 / 被 fallback `_` catches），3 個 assert 至少 1 個必失敗 → 守 HIGH-1 不退化。

**為什麼不直接 assert row.state 為 DEGRADED**：
- SM 端 OK→DEGRADED dwell 5min（per spec §5.2），integration test 7s 不可等。
- SM observe_classified 採 DEGRADED-band sample 時返 `Ok(false)` + 設立 anchor；row.state 寫 SM 當前 state（仍 OK，dwell 未達）。
- 改用「classify_aggregated 直接呼 + helper 返 DEGRADED」端到端守 HIGH-1 dispatch 真實接通 — 等價於 production observation path 但不需 wall-clock dwell。
- SM dwell 邏輯由 `test_sprint2_ladder_database_pool` + Track A 4 個 round 2 fix test 守（SM 共用邏輯）。

### Fix 4：Track B HIGH-1 heartbeat_lag ladder revert 三段對齊 spec SSOT

**位置**：`rust/openclaw_engine/src/health/domains/pipeline_throughput.rs` `classify_pipeline_throughput_heartbeat_lag_ms`。

**Before（round 1 IMPL — spec drift）**：
```rust
pub fn classify_pipeline_throughput_heartbeat_lag_ms(value: u32) -> HealthState {
    if value > 120_000 { HealthState::HealthCritical }
    else if value > 60_000 { HealthState::HealthDegraded }
    else if value > 30_000 { HealthState::HealthWarn }
    else { HealthState::HealthOk }
}
```
unilaterally 將 spec CRITICAL > 60s 改為 DEGRADED 60-120s + CRITICAL > 120s。

**After（revert 對齊 spec line 102 SSOT）**：
```rust
pub fn classify_pipeline_throughput_heartbeat_lag_ms(value: u32) -> HealthState {
    if value > 60_000 { HealthState::HealthCritical }
    else if value > 30_000 { HealthState::HealthWarn }
    else { HealthState::HealthOk }
}
```

**為什麼選三段而非保留四段含 DEGRADED**：
- spec line 102 SSOT 明文「WS dropout > 60s OR ipc p99 > 50ms」= CRITICAL，無中段 DEGRADED 設計。
- 三段最 simplest、行為差異最小；避「為防誤觸 CRITICAL 自由設計 DEGRADED 中段」這種 dwell 與 classify 雙重保護混淆 spec 語意的設計。
- 短暫網路抖動由 SM 5-sample rolling mean 平滑 + dwell（OK→WARN 60s / WARN→CRITICAL dwell per spec §5.2）守住；classify 端不重複設計。

**配套**：`classify_pipeline_throughput_heartbeat_lag_ms` unit test 更新 4 個 assertion（60_000 邊界 → WARN / 60_001 + 90_000 + 120_000 + 150_000 → CRITICAL）。

### Fix 5：Track C MEDIUM-2 probe wire-up doc + TODO 載明

**位置**：`rust/openclaw_engine/src/health/domains/database_pool.rs` module-level doc 「硬邊界」block 後加「警告 — probe 注入式設計」段。

```rust
//! 警告 ── probe 注入式設計：未接線 Wave 2 main.rs 前的 production 行為
//!   `WriterQueueProbe` + `PoolWaitP95Probe` 走 caller 注入 closure：
//!     - Wave 1 IMPL 不在 main.rs 接 emitter（per Track A §7 carry-over，Wave 2
//!       後或 Sprint 5 cascade IMPL 才接）。
//!     - 在 Wave 2 wire-up 前若 production 已啟用 DatabasePoolEmitter，caller
//!       端必須注入 placeholder closure；emitter 不能假設 probe 已接 source。
//!     - 配合 Sprint 2 round 2 Track C MEDIUM-2 fix：未接 source 時 caller 端
//!       傳 `Arc::new(|| 0_u32)` 並於 V106 row evidence_json 標記
//!       `probe_not_wired`（或 main.rs 接線時 emitter 整體不 schedule）。
//!     - 若 probe 永遠回 0，scheduler 端 5-sample mean = 0，必走 OK band
//!       不會誤升 WARN/DEGRADED — 風險是「永遠看不到 backlog 真實升階」
//!       而非「誤觸 cascade」。
//!   後續 wire-up 由 TODO follow-up entry「W-XX-Y Sprint 2 Wave 2 wire-up
//!   writer_queue_depth probe + pool_wait_p95 probe（per `docs/agents/
//!   todo-maintenance.md` 被動等待 NDay 守則）」追蹤。
```

**TODO follow-up（PM 收口端登記）**：
> W-XX-Y Sprint 2 Wave 2 wire-up writer_queue_depth probe + pool_wait_p95 probe
>
> - 依賴：main.rs 接 `MetricEmitterScheduler` + 各 emitter 接線；待 Sprint 5 cascade IMPL 或 Wave 2 主路徑統一接線。
> - healthcheck：當 main.rs 接 `DatabasePoolEmitter` 後，於健康面板（M3 GUI）顯示 `database_pool.{writer_queue_depth, pool_wait_ms_p95}` 之 5-sample mean。若連續 30min 採樣 mean 仍為 0（極端罕見且 production 必有 backlog），記 evidence 「probe 仍未接 source（mean=0 stuck）」並升 WARN log。
> - 對齊 `docs/agents/todo-maintenance.md` 被動等待 NDay 守則：N=14 day 內 main.rs 必須接線或記 carry-over 證據。

（本 E1 不直接改 `TODO.md`；上述 entry 由 PM 在 sign-off + commit 階段登記至 `srv/TODO.md` 並 ack `docs/agents/todo-maintenance.md` healthcheck section。）

## §3. cargo test 結果

| Verify | Command | Result |
|---|---|---|
| Release build | `cargo build --release` | **PASS** — 25.47s clean；2 pre-existing warning（panel_aggregator unused_imports + ma_crossover dead_code）+ 1 pre-existing tasks.rs warning；health module 0 new warning |
| Lib unit tests (health::) | `cargo test --release --lib health::` | **53/53 PASS** — Track A 32 + Track B 7 + Track C 11 + ev_bus + writer + sm domain |
| Lib unit tests (full lib) | `cargo test --release --lib` | **3118/3118 PASS**（1 ignored pre-existing；0 new fail）— pre-existing 3096 + 22 new health::domains unit tests |
| Track A regression | `cargo test --release --test sprint2_track_a_engine_runtime` | **9/9 PASS** — 5 舊 + 4 新（reject_reason same_anomaly_cap / fail_closed_ge_2 / recovery_dwell_reset / sm_records_dwell）全 PASS |
| Track B integration | `cargo test --release --test sprint2_track_b_pipeline_throughput` | **5/5 PASS**（含 ladder / cross_domain / row_count / spike_feature / real_emitter_through_scheduler） |
| Track C integration | `cargo test --release --test sprint2_track_c_database_pool` | **6/6 PASS** — 5 舊 + 1 新 `test_sprint2_track_c_database_pool_degraded_band_classify` 全 PASS；test_sprint2_track_c_database_pool_row_count 新 state band assert PASS |
| Spike regression | `cargo test --release --features spike --test m3_amp_cap_24h_fire` | **3/3 PASS**：test_amp_cap_different_anomaly_id_not_suppressed / test_m3_amp_cap_24h_fire / test_stub_domains_fail_loud |
| nm symbol scan (AC-5) | `nm target/release/openclaw-engine \| grep -cE "(mock_instant\|tokio::time::pause\|spike)"` | **0** hit ✓ — production binary 0 mock time 滲透 |

**累計：lib 3118 + 整 sprint2 9+5+6=20 + spike 3 = 3141 PASS / 0 fail / 1 ignored**。

## §4. LOC

| File | Before round 2 combined | After | Delta | Cap status |
|---|---|---|---|---|
| `rust/openclaw_engine/src/health/metric_emitter/mod.rs` | 1069 | 1128 | +59 | 警告 (>800)；hard cap 2000 安全 |
| `rust/openclaw_engine/src/health/domains/pipeline_throughput.rs` | 702 | 712 | +10 | < 800 |
| `rust/openclaw_engine/src/health/domains/database_pool.rs` | 712 | 727 | +15 | < 800 |
| `rust/openclaw_engine/tests/sprint2_track_c_database_pool.rs` | 414 | 631 | +217 | test file 不計 cap |
| `rust/openclaw_engine/tests/sprint2_track_b_pipeline_throughput.rs` | 511 | 511 | 0 | unchanged |

5 file 累計 +301 LOC（淨增；含 comment 與 test）。

## §5. PA spec amend dependent 4 條 carry-over

| # | Track | Severity | Finding | 等待 PA |
|---|---|---|---|---|
| 1 | Track B | HIGH-2 | dwell「持續 2min」對齊 spec § 5.2 vs per-domain dwell 設計 | PA spec amend 拍板 60s / 2min / per-domain dwell threshold |
| 2 | Track B | MEDIUM-1 | drift / signal threshold（ws_subscription_drift_count + strategy_signal_rate_per_min） | PA spec amend 新 threshold（如 0/1/3 vs 0/2/5；0.5/0.1 vs 1.0/0.5） |
| 3 | Track C | MEDIUM-1 | pool_max_conn classify_aggregated 注入 Path | PA 拍板 Path A（scheduler 端帶 5th column context）vs Path B（emitter-level classify after sample）|
| 4 | Track C | MEDIUM-3 | disconnected DbPool fail-closed 詳細語意 | PA 拍板 Path A（disconnected sample skip）vs Path B（disconnected sample 標 evidence + 全 OK band）|

E1 round 3 對 4 條 spec-dependent finding 之 follow-up：
- 收到 PA spec amend 後 ≤ 2 hr 完成 4 條 IMPL（含對應 unit test）。
- `pg_pool_active_conn` arm 待 PA Path A 拍板後在 `classify_aggregated` 加；Path B 則改 emitter-level classify 後在 `into_metric_rows` 端帶 final band（會破現有 scaffold pattern，需更大改動）。

## §6. 治理對照

- **§六 Hard Boundaries**：未碰 `live_execution_allowed` / `execution_authority` / `system_mode` / production engine（PID 2934602）/ trading_ai production DB；本 round 純 Rust 邏輯 + test 修復 ✓
- **§七 Code And Docs Rules**：
  - 新代碼注釋全中文（per `feedback_chinese_only_comments` 2026-05-05）；修改舊 bilingual block 移除英文保留中文 ✓
  - 無 emoji 引入 ✓
  - bilingual-comment-style：新建注釋默認只中文；舊中英對照塊不主動清，修改時移除英文只保留中文 ✓
- **§八 Workflow**：E1 round 2 IMPL DONE → 等 E2 round 2 re-review；不自行 commit；不派下游 sub-agent ✓
- **§九 Code Structure Guardrails**：
  - metric_emitter/mod.rs 1128 LOC（> 800 警告但 < 2000 hard cap；scaffold owner 預期 LOC peak，不切 file 否則破壞 Track B-F sub-agent 沿用 path）✓
  - 其他 file 全 < 800 LOC ✓
- **§Data, Migrations, And Validation**：本 round 不新增 V###；V106 schema 沿用；dwell_time_sec INTEGER cast 沿用 Track A round 2 clamp ✓
- **cross-platform**：純 Rust 邏輯，不引平台特異 path；sysinfo + tokio + chrono workspace dep；Mac+Linux 共通 ✓
- **AC-5 production binary 0 mock time 滲透**：本 round 新 `classify_aggregated_for_test` pub re-export 為 `#[doc(hidden)]`，無 `cfg(feature = "spike")` gate；nm 0 hit 守住 ✓
- **`feedback_impl_done_adversarial_review`**：scaffold owner + Track B + Track C 共 5 fix；E1 IMPL DONE 不單獨 sign-off，等 E2 round 2 + A3 re-review；E4 regression 不能取代 ✓
- **多角色 adversarial review 原則**：Fix 2 引入 `classify_aggregated_for_test` pub re-export 為 HIGH-1 不退化 守，避「PR 後 dispatch arm 被回退也測不出」之 regression 盲區；Track C Fix 3 新 stress test 直接呼此 helper 是 adversarial 守的具體落實 ✓

## §7. 不確定 / Carry-over

1. **`pg_pool_active_conn` arm 暫缺**：等 PA spec amend MEDIUM-1 C Path 拍板後 E1 round 3 補。本 round `_ => HealthOk` fallback catches 該 metric 屬「已知 limited functionality」；E2 round 2 應確認此延遲是否可接受。
2. **新 stress test `test_sprint2_track_c_database_pool_degraded_band_classify` 不直接 assert row.state DEGRADED**：用 `classify_aggregated_for_test` 端到端守 dispatch 真實接通而非走 fallback；adversarial 等價於 production observation path。Operator 若希望 wall-clock dwell 5min 真升階 test，需 spike feature mock clock 或縮 dwell to 1s for test（破 Track A SM 設計），均不建議。
3. **Track B HIGH-1 三段選擇**：本 round 選「OK / WARN / CRITICAL 三段」對齊 spec SSOT；保留四段（含 DEGRADED 中段）也是可選。Operator 若希望保留四段，需 E1 round 3 修為四段（dispatch 第二選項），對應 unit test 同步更新。
4. **probe wire-up TODO follow-up**：本 E1 不直接改 `TODO.md`；entry 由 PM 在 sign-off + commit 階段登記。`docs/agents/todo-maintenance.md` 被動等待 NDay 守則需配 healthcheck（mean=0 stuck 30min 升 WARN log）— 此 healthcheck IMPL 由 Wave 2 main.rs wire-up 一併接，本 round 不接。
5. **TODO healthcheck IMPL 位置**：暫定接於健康面板（M3 GUI）顯示；具體 endpoint + 邏輯由 Wave 2 確定。

## §8. 修改清單

| File | 改動範圍 | 性質 |
|---|---|---|
| `rust/openclaw_engine/src/health/metric_emitter/mod.rs` | 1069 → 1128 LOC：`classify_aggregated` 5 處 mean cast 改 `mean.round() as u32`/`as u64`（Fix 1）+ 加 3 個 `(HealthDomain::DatabasePool, ...)` arm（Fix 2）+ 加 `pub fn classify_aggregated_for_test` #[doc(hidden)] wrapper（Fix 3 守 HIGH-1 不退化） | round 2 fix |
| `rust/openclaw_engine/src/health/domains/pipeline_throughput.rs` | 702 → 712 LOC：`classify_pipeline_throughput_heartbeat_lag_ms` 三段對齊 spec SSOT（Fix 4 revert spec drift）+ unit test 對應 4 assertion 更新 | round 2 fix |
| `rust/openclaw_engine/src/health/domains/database_pool.rs` | 712 → 727 LOC：module-level doc 加「警告 — probe 注入式設計」block（Fix 5） | round 2 fix |
| `rust/openclaw_engine/tests/sprint2_track_c_database_pool.rs` | 414 → 631 LOC：`test_sprint2_track_c_database_pool_row_count` 加 `assert_eq!(row.state, HealthOk)`（Fix 3a）+ 新 stress test `test_sprint2_track_c_database_pool_degraded_band_classify` 守 HIGH-1 不退化（Fix 3b） | round 2 fix |
| `rust/openclaw_engine/tests/sprint2_track_b_pipeline_throughput.rs` | 沿用 round 1（unchanged） | n/a |

**不動 file**：health/mod.rs / writer.rs / event_bus.rs / sql/migrations/V106 / main.rs / sprint2 packet / spec doc / 其餘 module。

## §9. round 2 combined verdict

- 5/9 finding deterministic closure（HIGH-1×2 + HIGH-2 + MEDIUM-2×2 → 5/5；不含 LOW 由 E2 自評 not blocking）
- 4/9 PA spec-dependent finding carry-over（Track B HIGH-2 + MEDIUM-1 + Track C MEDIUM-1 + MEDIUM-3）→ E1 round 3 待 PA amend land 後跟進
- cargo build + test：lib 3118/3118 / health 53/53 / Track A 9/9 / Track B 5/5 / Track C 6/6（5 舊 + 1 新）/ spike 3/3 / nm 0 hit
- LOC：5 file +301 LOC 全在 2000 hard cap 下；metric_emitter/mod.rs 觸 800 警告（scaffold owner 預期 LOC peak）
- 治理：未碰任何 hard boundary / production engine / trading_ai DB / spec doc / ADR-0042 / V### SQL
- adversarial review：Fix 2 + Fix 3 加入 `classify_aggregated_for_test` pub re-export 端到端守 HIGH-1 不退化；Track B-F sub-agent 沿用此 helper 可同樣守 dispatch 不退化（DRY）
- E2 round 2 re-review **READY**；A3 review（per `feedback_impl_done_adversarial_review`）若 GUI / IPC / 寫操作 / 共用 helper 涉及則並行派發；本 round 不動 GUI / IPC，A3 為「0 GUI 改動」結案沿用 round 1 sign-off

## §10. Operator 下一步

1. **PM 派 E2 round 2 re-review**：focus on
   - Fix 1 ladder boundary `mean.round()` 5 處 cast：是否漏一 cast 點；既有 test 注入整數值無 boundary 觸發是否合理
   - Fix 2 `classify_aggregated` 3 arm dispatch + `pg_pool_active_conn` 暫缺路徑：`_ => HealthOk` 對該 metric 是否會在 production 觸 silent failure（pool 飽和升級不會 catch）
   - Fix 3 新 stress test + `classify_aggregated_for_test` pub re-export 是否合 adversarial 守 dispatch；是否需更強 assert（如 row.state DEGRADED via spike clock）
   - Fix 4 三段 ladder vs 四段含 DEGRADED 中段：Operator + E2 共同確認 spec line 102 SSOT「WS dropout > 60s = CRITICAL」嚴格對齊
   - Fix 5 probe wire-up doc + TODO follow-up healthcheck 設計：N=14 day 是否合理；mean=0 stuck 30min 是否充分
2. **PM 收口 TODO entry**：本 E1 report §2 Fix 5 內列明 entry 內容；待 PM commit 階段登記至 `srv/TODO.md`。
3. **PM 確認 PA spec amend 4 條進度**：本 round 不動 PA spec doc / ADR-0042 / V### SQL；E1 round 3 待 PA amend land 後跟進。
4. **A3 review 路徑**：本 round 不動 GUI / IPC / 寫操作；A3 沿用 round 1 sign-off「0 GUI 改動」；若 E2 round 2 認定 `classify_aggregated_for_test` pub re-export 為「共用 helper 之 IPC 邊界擴大」，則並行派 A3 + E2 對抗性核驗（per `feedback_impl_done_adversarial_review` 2026-05-09）。

---

**E1 IMPLEMENTATION DONE: 待 E2 round 2 re-review（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave1_round2_combined_fix.md`）**
