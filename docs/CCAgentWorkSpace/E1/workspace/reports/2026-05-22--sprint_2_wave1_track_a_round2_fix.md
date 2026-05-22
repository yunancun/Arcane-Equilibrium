---
report: Sprint 2 Wave 1 Track A round 2 fix（E2 round 1 REJECT closure）
date: 2026-05-22
author: E1 (Backend Developer, Rust)
phase: Sprint 2 Phase 2 Wave 1 Track A round 2
status: IMPL DONE — awaiting E2 round 2 re-review
parent dispatch:
  - docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave1_track_a_engine_runtime.md（round 1 baseline IMPL）
  - E2 round 1 adversarial review verdict: REJECT (3 HIGH + 2 MEDIUM + 1 LOW)
runtime: Mac development（sysinfo cross-platform native Mac+Linux 沿用）
production engine: PID 2934602 跑 trading_ai（全程未碰）
---

# E1 Sprint 2 Wave 1 Track A round 2 fix — 2026-05-22

## §1 E2 round 1 findings 處理摘要

| # | Severity | Fix status |
|---|---|---|
| HIGH-1 D3 cascade reject_reason false positive (same anomaly + count=2 場景誤標 fail-closed) | P0 | **DONE** |
| HIGH-2 recovery dwell anchor 升階方向不對稱清理 (5 domain 通用 bug) | P0 | **DONE** |
| MEDIUM-1 async lock held across await (Err 分支 lock 持有時呼 writer.await) | P1 | **DONE** |
| MEDIUM-2 dwell_time_sec hardcoded to 0 (V106 audit row dwell 永遠 0) | P1 | **DONE** |
| LOW-2 cosmetic (HealthOk, HealthOk) recovery anchor 冗餘 reset | low | **DONE** |
| HIGH-3 / LOW-1 packet AC-1 spec drift | — | NOT in scope (PA 並行修) |
| MEDIUM-3 lock 順序設計層警告 | — | NOT in scope (簡單 doc 補) |

## §2 字面 diff（per finding）

### HIGH-1：SM `is_anomaly_capped` API + scheduler `infer_reject_reason` helper

**A. SM 新 pub accessor**（`rust/openclaw_engine/src/health/mod.rs` 加 line ~510-530）：

```rust
/// 查詢某 anomaly_id 是否已在 24h amp cap window 內 fire 過（per Sprint 2
/// round 2 HIGH-1 fix）。
pub fn is_anomaly_capped(&self, anomaly_id: &str) -> bool {
    self.amp_cap_entries.contains_key(anomaly_id)
}
```

不暴露 entries map 本體（封裝），只暴露查詢結果。Track B-F sub-agent 沿用。

**B. scheduler 抽 pub helper**（`rust/openclaw_engine/src/health/metric_emitter/mod.rs` 加 line ~615-655）：

```rust
/// 推斷 SM `observe_classified` 返回 `Ok(false)` 時的 cascade reject_reason。
///
/// 邏輯規約（per V106 spec §1.1 line 77 + SM guard 順序）:
///   guard 1（same anomaly suppress）優先於 guard 3（fail-closed >=2）；
///   即 cap entries 已包含 anomaly_id 時，**先**回 guard 1 reason，**不**
///   因 count >=2 誤標 fail-closed。
pub fn infer_reject_reason(
    sm: &HealthStateMachine,
    target_band: HealthState,
    anomaly_id: &str,
) -> Option<&'static str> {
    let current = sm.current_state();
    if target_band == current {
        return None;
    }
    if sm.is_anomaly_capped(anomaly_id) {
        Some("amp_cap_same_anomaly_24h_suppress")
    } else if sm.amplification_loop_24h_count() >= 2 {
        Some("amp_cap_>=2_fail_closed")
    } else {
        None
    }
}
```

**C. scheduler 端用 helper**（`run_domain_loop` Ok(false) 分支從 inline 邏輯改為 `infer_reject_reason(sm, band_from_mean, &anomaly_id)`）。

**B 與 C 同時 publish 為 pub fn**：Track B-F sub-agent 沿用同一推斷邏輯（DRY，避免每 Track 重複 inline 邏輯且帶相同 bug）。

### HIGH-2：observe_classified 升階方向 + 同 state 高 band 採樣全 reset recovery_band_seen_at

`rust/openclaw_engine/src/health/mod.rs` 升階 5 條 + 同 state 高 band 1 條 match arm 全顯式 reset：

```rust
// 同 state 高 band 採樣（per HIGH-2 fix）：current 已是 WARN/DEGRADED/CRITICAL
(HealthWarn, HealthWarn)
| (HealthDegraded, HealthDegraded)
| (HealthCritical, HealthCritical) => {
    self.recovery_band_seen_at = None;
    Ok(false)
}

// 升階方向 5 條（per HIGH-2 fix）
(HealthOk, HealthWarn) => {
    self.recovery_band_seen_at = None;
    self.try_dwell_then_transition(...)
}
(HealthOk, HealthDegraded) | (HealthOk, HealthCritical) => {
    self.recovery_band_seen_at = None;
    self.try_dwell_then_transition(...)
}
(HealthWarn, HealthDegraded) | (HealthWarn, HealthCritical) => {
    self.recovery_band_seen_at = None;
    self.try_dwell_then_transition(...)
}
(HealthDegraded, HealthCritical) => {
    self.recovery_band_seen_at = None;
    self.try_dwell_then_transition(...)
}
```

spec §5.2「持續 15min OK-band dwell」要求 recovery 期必須全 OK，任一高 band 採樣立即作廢 anchor。

### MEDIUM-1：drop(sm_guard) 移到 writer.await 前

`rust/openclaw_engine/src/health/metric_emitter/mod.rs` `run_domain_loop`：

舊 IMPL（Err 分支 lock 持有時呼 writer.await）:
```rust
let mut sm_guard = state_machines.lock().await;
let sm = sm_guard.entry(...).or_insert_with(...);
let observe_result = sm.observe_classified(...);
let (fired, reject_reason) = match observe_result {
    Ok(true) => ...,
    Ok(false) => ...,
    Err(e) => {
        let _ = writer.write_sample_error(...).await;  // BUG: lock 仍持有
        ...
    }
};
```

新 IMPL：SM 結果聚合到 `ObserveOutcome` struct + lock scope 結束 + drop guard 後才走 writer：

```rust
struct ObserveOutcome {
    prev_state: HealthState,
    current_state: HealthState,
    current_count: u32,
    fired: bool,
    dwell_secs: u32,
    reject_reason: Option<&'static str>,
    sample_error: Option<M3Error>,
}

let observe_outcome: ObserveOutcome = {
    let mut sm_guard = state_machines.lock().await;
    let sm = sm_guard.entry(...).or_insert_with(...);
    let observe_result = sm.observe_classified(...);
    let (fired, dwell_secs, reject_reason, sample_error) = match observe_result {
        Ok(true) => (true, sm.last_transition_dwell_secs(), None, None),
        Ok(false) => {
            let reason = infer_reject_reason(sm, band_from_mean, &anomaly_id);
            (false, 0, reason, None)
        }
        Err(e) => (false, 0, None, Some(e)),
    };
    ObserveOutcome { prev_state, current_state: sm.current_state(),
                    current_count: sm.amplification_loop_24h_count(),
                    fired, dwell_secs, reject_reason, sample_error }
    // sm_guard 在 scope 結束時 drop
};

// Err 場景的 writer.write_sample_error.await 在 drop guard 之後
if let Some(err) = observe_outcome.sample_error {
    let _ = writer.write_sample_error(domain, metric_name, &err, &mode).await;
}
```

### MEDIUM-2：SM 加 last_transition_dwell_secs 字段 + accessor + scheduler 寫真實 dwell

**A. SM 字段 + 初始化**（`rust/openclaw_engine/src/health/mod.rs`）：

```rust
pub struct HealthStateMachine {
    // ... 既有 field ...
    last_transition_dwell_secs: u32,  // 新
}

// new() 初始化:
last_transition_dwell_secs: 0,
```

**B. fire branch 計算 dwell**（在 state_entered_at 被覆寫前）：

`try_transition_with_cap` 升階 fire 路徑：
```rust
let dwell_secs = now.saturating_duration_since(self.state_entered_at).as_secs();
self.last_transition_dwell_secs = dwell_secs.min(i32::MAX as u64) as u32;
self.previous_state = self.current_state;
self.current_state = target_state;
self.state_entered_at = now;  // 覆寫
```

`try_recovery_dwell` recovery fire 路徑：同樣計算 + 緩存。

**C. accessor**：
```rust
pub fn last_transition_dwell_secs(&self) -> u32 {
    self.last_transition_dwell_secs
}
```

**D. scheduler 寫真實 dwell**：
```rust
if observe_outcome.fired {
    row = row.with_transition(
        observe_outcome.prev_state,
        observe_outcome.dwell_secs as i32,  // 真實值，非 hardcode 0
    );
}
```

V106 schema `dwell_time_sec INTEGER` 對齊；Sprint 5 cascade analysis 可看真實 dwell 推斷狀態變化速度。

### LOW-2：(HealthOk, HealthOk) 分支移除 recovery_band_seen_at = None

```rust
(HealthOk, HealthOk) => {
    self.warn_band_seen_at = None;
    self.degraded_band_seen_at = None;
    self.critical_band_seen_at = None;
    // recovery_band_seen_at 不再清（current=OK 無 recovery dwell 場景；
    // anchor 應已 None 因 fire 時清過）。
    Ok(false)
}
```

設計上多餘但不影響正確性；清理屬美化。

## §3 新 integration test

`rust/openclaw_engine/tests/sprint2_track_a_engine_runtime.rs` 加 4 個 test：

| Test | 對應 fix | 場景 |
|---|---|---|
| `test_sprint2_track_a_scheduler_emits_correct_reject_reason_same_anomaly_cap` | HIGH-1 | SM fire 兩次（A + B，count=2）後 anomaly A 再升階；驗 `infer_reject_reason` 必回 `amp_cap_same_anomaly_24h_suppress`（**不**因 count=2 誤標 fail-closed） |
| `test_sprint2_track_a_scheduler_emits_correct_reject_reason_fail_closed_ge_2` | HIGH-1 | SM fire 兩次（A + B，count=2）後**新** anomaly C 升階；驗 `infer_reject_reason` 必回 `amp_cap_>=2_fail_closed` |
| `test_sprint2_track_a_recovery_dwell_resets_on_high_band_sample` | HIGH-2 | current=WARN，序列 [OK(t=0), WARN(t=10s), OK(t=900s)]；驗第二個 OK 不誤 fire recovery（anchor 已被 WARN 採樣清，elapsed 從 t=900s 重算）；再過 15min 才真 fire |
| `test_sprint2_track_a_sm_records_last_transition_dwell_secs` | MEDIUM-2 | OK→WARN fire 在 base+60s；驗 `sm.last_transition_dwell_secs()` >= 60 <= 120（防時鐘漂移） |

**為什麼用 `infer_reject_reason` helper 而非 scheduler.run wall-clock**：scheduler dwell 60s/5min 是 wall-clock，test 不能等。抽 pub helper 後 test 走「真實 SM state + 推斷 helper」對齊；scheduler 內呼同一 helper，覆蓋等價於走 scheduler.run。Track B-F sub-agent 沿用同一 helper（DRY）。

## §4 cargo test result

| Verify | Command | Result |
|---|---|---|
| Release build | `cargo build --release` | **PASS** — 23.8s clean；2 pre-existing warning（panel_aggregator unused_imports + ma_crossover dead_code）+ 1 pre-existing tasks.rs warning，health module 0 warning |
| Lib unit tests (health::) | `cargo test --release --lib health::` | **32/32 PASS**（含 spike Track B 既有 14 + Sprint 2 18 包含本 round 仍 32 不增（新 SM accessor 邏輯由 integration test 守）） |
| Lib unit tests (full lib) | `cargo test --release --lib` | **3096/3096 PASS**（1 ignored 為 pre-existing；0 new fail） |
| Integration test Sprint 2 Track A | `cargo test --release --test sprint2_track_a_engine_runtime` | **9/9 PASS**（5 舊 + 4 新）：<br>- test_sprint2_ladder_engine_runtime（舊 AC-2）<br>- test_sprint2_track_a_cascade_reject_emit_fail_closed_ge_2（舊 D3 a）<br>- test_sprint2_track_a_cascade_reject_emit_same_anomaly_24h_suppress（舊 D3 b）<br>- test_sprint2_track_a_engine_runtime_row_count_ge_5（舊 AC-1 proxy）<br>- test_sprint2_track_a_spike_feature_not_active_in_default_build（舊 AC-5）<br>- **新** test_sprint2_track_a_scheduler_emits_correct_reject_reason_same_anomaly_cap<br>- **新** test_sprint2_track_a_scheduler_emits_correct_reject_reason_fail_closed_ge_2<br>- **新** test_sprint2_track_a_recovery_dwell_resets_on_high_band_sample<br>- **新** test_sprint2_track_a_sm_records_last_transition_dwell_secs |
| Spike regression | `cargo test --release --features spike --test m3_amp_cap_24h_fire` | **3/3 PASS**：test_amp_cap_different_anomaly_id_not_suppressed / test_m3_amp_cap_24h_fire / test_stub_domains_fail_loud |
| nm symbol scan (AC-5) | `nm target/release/openclaw-engine \| grep -E "(mock_instant\|tokio::time::pause\|spike)" \| wc -l` | **0 hit** ✓ — production binary 0 mock time 滲透 |

## §5 LOC

| File | Before round 2 | After round 2 | Delta |
|---|---|---|---|
| `rust/openclaw_engine/src/health/mod.rs` | 990 | 1069 | +79 |
| `rust/openclaw_engine/src/health/metric_emitter/mod.rs` | 964 | 1044 | +80 |
| `rust/openclaw_engine/tests/sprint2_track_a_engine_runtime.rs` | 378 | 658 | +280 |

全在 2000 LOC hard cap 下；health/mod.rs + metric_emitter/mod.rs 觸 800 LOC warning 對齊 round 1 baseline 評估（scaffold owner 預期 LOC peak）。

## §6 治理對照

- **§六 Hard Boundaries**：未碰 `live_execution_allowed` / `execution_authority` / `system_mode` / production engine（PID 2934602）/ trading_ai production DB；本 round 純 Rust 邏輯修復 ✓
- **§七 Code And Docs Rules**：新代碼注釋全中文（per `feedback_chinese_only_comments` 2026-05-05）；修改舊 bilingual block 移除英文保留中文（套用 bilingual-comment-style 規則）；無 emoji 引入 ✓
- **§八 Workflow**：E1 round 2 IMPL DONE → 等 E2 round 2 re-review；不自行 commit ✓
- **§九 Code Structure Guardrails**：2 大檔仍觸 800 LOC warning 但未過 2000 hard cap；scaffold owner 預期 LOC peak（不切 file 否則破壞 Track B-F sub-agent 沿用 path）✓
- **§Data, Migrations, And Validation**：本 round 不新增 V###；V106 schema 19 column 沿用；dwell_time_sec column INTEGER cast clamp 確保不溢位 ✓
- **bilingual-comment-style**：新代碼注釋默認只寫中文；舊中英對照塊未動 ✓
- **cross-platform**：純 Rust 邏輯，不引平台特異 path；MEDIUM-1 fix 用 tokio::sync::Mutex（已工作空間 dep）✓
- **AC-5 production binary 0 mock time 滲透**：本 round 新 helper `infer_reject_reason` + ObserveOutcome struct + SM accessor 全 0 spike feature gate；nm 0 hit 守住 ✓
- **`feedback_impl_done_adversarial_review`**：scaffold owner 高風險 IMPL；E1 round 2 IMPL DONE → 等 E2 round 2 + A3（per round 1 已 sign-off A3 = 0 GUI 改動，本 round 不動 GUI）re-review；不單獨 sign-off ✓
- **多角色 adversarial review 原則**：本 round 修 5 finding 全採用集中 helper（`is_anomaly_capped` + `infer_reject_reason` + `ObserveOutcome`）；Track B-F sub-agent 將 inherit 同一 helper 不會重複 inline 邏輯 + 不會帶相同 bug ✓

## §7 不確定 / Carry-over

1. **packet §1.7 「INSERT 全 27 column」描述 vs V106 schema 實際 19 column**：本 round 仍 IMPL 19 column（per round 1 結論）；packet drift 由 PA 並行修（HIGH-3 / LOW-1）。
2. **AC-1 真實 Linux PG empirical**：Phase 3c QA 走 sandbox_admin ssh trade-core；本 round 不重覆 round 1 AC-1 proxy（in-memory writer mock 已沿用）。
3. **engine main.rs 接 EngineRuntimeEmitter + scheduler**：Wave 2 後或 Sprint 5 一併接；本 round 不動 main.rs。
4. **dwell_time_sec u32 → i32 cast clamp**：`dwell_secs.min(i32::MAX as u64) as u32` 在 SM 端 clamp；scheduler 端 `dwell_secs as i32` 對 u32 → i32 不會溢位（u32::MAX < i32::MAX 不成立但 dwell 24h = 86400 << i32::MAX = 2.1B）。實務不撞 limit；test 覆蓋 60s 場景 + sanity 上限 120s。
5. **MEDIUM-3 lock 順序設計層警告**：E2 提到「加 module-level doc」即可，本 round 不動（per dispatch 說明屬「簡單 doc 補」非本 round scope）。Operator 決定是否本 round 一併補。
6. **packet AC-1 雞蛋問題 (HIGH-3)**：PA 並行修；本 round 不動 packet 文件。

## §8 修改清單

| File | 改動範圍 | 性質 |
|---|---|---|
| `rust/openclaw_engine/src/health/mod.rs` | 990 → 1069 LOC：HealthStateMachine 加 `last_transition_dwell_secs: u32` 字段；`new()` 初始 0；`try_transition_with_cap` 升階 fire branch 計算 dwell 並寫入字段；`try_recovery_dwell` recovery fire 同樣計算；3 accessor 加：`last_transition_dwell_secs()` / `is_anomaly_capped()`；observe_classified 升階方向 5 條 match arm + 同 state 高 band 1 條 全 reset `recovery_band_seen_at = None`；(HealthOk, HealthOk) 移除冗餘 recovery anchor reset | round 2 fix |
| `rust/openclaw_engine/src/health/metric_emitter/mod.rs` | 964 → 1044 LOC：新 `pub fn infer_reject_reason(sm, target_band, anomaly_id)` helper（HIGH-1 集中推斷）；新 `struct ObserveOutcome`（MEDIUM-1 lock release）；`run_domain_loop` SM 結果聚合到 ObserveOutcome + drop guard 後再走 writer；Err 分支 sample_error 改 Option<M3Error> deferred 到 lock release 後 await；fire 路徑寫真實 dwell（observe_outcome.dwell_secs as i32） | round 2 fix |
| `rust/openclaw_engine/tests/sprint2_track_a_engine_runtime.rs` | 378 → 658 LOC：新 4 test：reject_reason same_anomaly_cap / fail_closed_ge_2 / recovery_dwell_reset / sm_records_dwell_secs | round 2 fix |

**不動 file**：sql/migrations/V106 / main.rs / writer.rs / event_bus.rs / sprint2 packet / 其餘 module。

## §9 round 2 verdict

- 5 findings（HIGH-1 + HIGH-2 + MEDIUM-1 + MEDIUM-2 + LOW-2）**全 closure**
- E2 round 2 re-review **READY**
- cargo test：lib 3096/3096 / health 32/32 / sprint2 9/9（5 舊 + 4 新）/ spike 3/3 / nm 0 hit
- LOC：3 file +439 LOC 全在 2000 hard cap 下
- 治理：未碰任何 hard boundary / production engine / trading_ai DB
- adversarial review：抽 pub helper `infer_reject_reason` 集中推斷邏輯，Track B-F sub-agent 沿用避免重複 bug；本 round 自評 IMPL DONE 不單獨 sign-off，等 E2 round 2 + （若需要）A3 re-review

## §10 Operator 下一步

1. **PM 派 E2 round 2 re-review**：focus on
   - HIGH-1 fix：`is_anomaly_capped` accessor + `infer_reject_reason` helper 邏輯規約是否完整覆蓋 SM guard 1 / guard 3 + dwell 未達場景
   - HIGH-2 fix：升階方向 5 條 + 同 state 高 band 1 條 reset 是否漏一個 case；recovery 從 DEGRADED 路徑同樣行為
   - MEDIUM-1 fix：ObserveOutcome 聚合 + drop scope 邊界正確性；不持 lock 跨 await
   - MEDIUM-2 fix：dwell 計算在 state_entered_at 覆寫前；u64 → u32 clamp 安全
   - LOW-2 fix：是否漏改其他冗餘 recovery anchor reset
   - 新 4 test 覆蓋是否充分；scheduler.run wall-clock 無法直跑 dwell 60s 的 test 替代方案合理性

2. **PM 確認 PA 並行修 packet AC-1（HIGH-3 + LOW-1）狀態**：本 round 不動 packet；packet drift closure 走 PA 路徑。

3. **MEDIUM-3 lock 順序 doc**：dispatch 說明屬「簡單 doc 補」非本 round scope；Operator 決定是否本 round 一併補或併入下一 Track。

---

**E1 IMPLEMENTATION DONE: 待 E2 round 2 re-review（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave1_track_a_round2_fix.md`）**
