# E1 Sprint 1B early IMPL #5 — Sprint 5 cascade reject ≥ 2 unit test 覆蓋

Date: 2026-05-22
Owner: E1 (Sprint 1B #5 — Sprint 5 cascade reject branch direct unit test)
Status: IMPL DONE — pending E2 review

Dispatch source: PM Sprint 1B early IMPL #5（per Sprint 1A-ζ Phase 3a E2 round 1 Track B LOW-2 + round 2 1 new LOW + PM Phase 3e §4.3 item 5）

Parent dependency: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_1a_zeta_track_b_m3_health_v106_impl_round2.md` §4.2 三 guard 設計
ADR ref: `srv/docs/adr/0042-m3-health-monitoring.md` Decision 4（1 anomaly = 1 state change/24h）

## 1. Pre-state existing test 覆蓋盤點

### 1.1 既有 `health/mod.rs` unit test（cfg test mod, 13 個 health 相關）

| Test | 覆蓋 try_transition_with_cap 哪個 branch |
|---|---|
| `test_health_state_as_str_round_trip` | 無 — HealthState 字串往返 |
| `test_health_state_unknown_literal` | 無 — 解析錯 |
| `test_health_domain_as_str_round_trip` | 無 — HealthDomain 字串往返 |
| `test_health_domain_unknown_literal` | 無 — 解析錯 |
| `test_health_domain_require_implemented_spike_scope` | 無 — spike scope guard |
| `test_health_state_severity_ordering` | 無 — severity_value 偏序 |
| `test_engine_runtime_metric_classify_band` | 無 — classify_band 4 band |
| `test_state_machine_starts_ok` | 無 — new() 初始 |
| `test_state_machine_stub_domain_rejects` | 無 — observe() spike scope DomainNotImplemented |
| `test_try_transition_no_fire_when_current_eq_target` | **Guard 2**（current == target → no fire）|
| `test_compute_window_stats_*` (3 個) | 無 — AC-7 fixture |

### 1.2 既有 spike integration test（`tests/m3_amp_cap_24h_fire.rs`, 3 個）

| Test | 覆蓋 try_transition_with_cap 哪個 branch |
|---|---|
| `test_m3_amp_cap_24h_fire` | **真實 fire happy path**（4 step：fire OK→WARN / 24h+1s 過期 reset / cap suppress / WARN 短路 observe_at 不進 transition fn） |
| `test_amp_cap_different_anomaly_id_not_suppressed` | observe_at 路徑下不同 anomaly_id 第 2 次走 `(HealthWarn, _)` 短路 — **不進 transition fn 也不命中 cap suppress** |
| `test_stub_domains_fail_loud` | observe() 5 stub domain |

### 1.3 Coverage gap 結論（per E2 LOW-2 + round 2 new LOW）

`try_transition_with_cap` 共 3 個 reject branch，既有測試覆蓋盤點：

| Guard | 邏輯 | 既有覆蓋 | Gap |
|---|---|---|---|
| Guard 1 | 同 anomaly_id 已 in cap → suppress | observe_at 路徑下 spike scope 因 `(HealthWarn, _)` 短路根本不進此 fn → **無直接覆蓋** | **YES** |
| Guard 2 | current == target → no fire 不 insert | `test_try_transition_no_fire_when_current_eq_target`（round 2 land）| 已 cover |
| Guard 3 | `amplification_loop_24h_count >= 2` → fail-closed reject | observe_at 路徑下 spike scope 永遠衝不到 count=2（WARN 短路）→ **無覆蓋** | **YES** |

Sprint 5 cascade IMPL 落地後將補 WARN→DEGRADED 5min dwell 等路徑，guard 1 / guard 3 才有 observe_at 整合路徑可走；spike scope 階段必須直接單測 transition fn 才能 cover。本 sprint 1B 提前補的 ≥ 2 reject branch direct unit test 是 Sprint 5 cascade IMPL 的 acceptance guard — Sprint 5 IMPL 上線後若 break 此邊界，這 2 個 test 會直接 fail。

## 2. 新增 unit test 兩個

修改檔：`srv/rust/openclaw_engine/src/health/mod.rs`（單檔 EDIT，只在 `#[cfg(test)] mod tests` 內加 test，0 業務邏輯改動）

### 2.1 Test 1: `test_try_transition_fail_closed_reject_count_ge_2`（Guard 3 覆蓋）

位置：`health/mod.rs:603-641`（39 LOC including comment + assertions）

語意：
- step 1：fire OK→WARN, anomaly_id "spike_a"（success, count=1）
- step 2：直接呼 transition fn fire WARN→DEGRADED, anomaly_id "spike_b"（success, count=2）— 繞 observe_at 的 `(HealthWarn, _)` 短路
- step 3：第 3 次 fire 用新 anomaly_id "spike_c" + target=HealthCritical（避開 guard 1 + guard 2）→ 唯一觸發 guard 3 reject path
- 校驗：reject 後 `count == 2`（不增）/ `amp_cap_entry_count == 2`（不 insert 新 entry）/ `current_state == HealthDegraded`（不前進到 Critical）

### 2.2 Test 2: `test_try_transition_cap_suppress_same_anomaly_id_repeat`（Guard 1 覆蓋）

位置：`health/mod.rs:643-678`（36 LOC including comment + assertions）

語意：
- step 1：fire OK→WARN, anomaly_id "engine_cpu_spike"（success, count=1）
- step 2：同 anomaly_id "engine_cpu_spike" 嘗試 fire WARN→DEGRADED（target != current 確保不被 guard 2 短路）→ 唯一觸發 guard 1 `contains_key` reject path
- 校驗：suppress 後 `count == 1` / `amp_cap_entry_count == 1` / `current_state == HealthWarn`

### 2.3 為什麼直接呼 private fn 而非走 observe_at

兩個 test 都直接呼 `sm.try_transition_with_cap(...)` 而非 `sm.observe(metric, id)` 或 `sm.observe_at(metric, id, now)`。原因：

per `health/mod.rs:364`：
```rust
(HealthState::HealthWarn, _) => Ok(false),
```

spike scope observe_at 在 current=WARN 一律返 false 不進 transition fn（WARN→DEGRADED 5min dwell 屬 Sprint 5 cascade IMPL 範圍）。所以：
- Guard 1（same anomaly_id repeat）在 spike scope 階段透過 observe_at 路徑無法觸發 — 任何 fire 後 current=WARN, 後續同 id observe_at 都 WARN-短路返 false（沒進 transition fn）
- Guard 3（count ≥ 2）同理：spike scope 永遠衝不到 count=2

直接單測 transition fn 是 spike scope 階段覆蓋 guard 1/3 reject branch 的**唯一**辦法。`try_transition_with_cap` 是同 module 內的 private fn，cfg test mod 可直接呼。

Sprint 5 cascade IMPL 補 WARN→DEGRADED 5min dwell 後，observe_at 整合路徑也可走 guard 1/3 — 屆時這 2 個 unit test 仍守 transition fn 端嚴格邊界，不會 break。

## 3. cargo test result

### 3.1 新 test PASS

```
$ cargo test --release --lib test_try_transition_fail_closed_reject_count_ge_2
test health::tests::test_try_transition_fail_closed_reject_count_ge_2 ... ok
test result: ok. 1 passed; 0 failed

$ cargo test --release --lib test_try_transition_cap_suppress_same_anomaly_id_repeat
test health::tests::test_try_transition_cap_suppress_same_anomaly_id_repeat ... ok
test result: ok. 1 passed; 0 failed
```

### 3.2 try_transition 系列（3 個 test，2 個 new + 1 個 round 2 既有）

```
$ cargo test --release --lib test_try_transition
test health::tests::test_try_transition_cap_suppress_same_anomaly_id_repeat ... ok
test health::tests::test_try_transition_no_fire_when_current_eq_target ... ok
test health::tests::test_try_transition_fail_closed_reject_count_ge_2 ... ok
test result: ok. 3 passed; 0 failed
```

### 3.3 health lib full regression（24 pass）

```
$ cargo test --release --lib health
test result: ok. 24 passed; 0 failed; 0 ignored; 0 measured
```

baseline round 2 是 22 pass（13 health + 9 其他 health 相關 — kpi_gate / canary / d6_pipeline 等）；本 round 加 2 new test 後 → **24 pass**，0 退化。

### 3.4 spike integration test 不退（3 pass）

```
$ cargo test --release --features spike --test m3_amp_cap_24h_fire
test test_amp_cap_different_anomaly_id_not_suppressed ... ok
test test_m3_amp_cap_24h_fire ... ok
test test_stub_domains_fail_loud ... ok
test result: ok. 3 passed; 0 failed
```

### 3.5 cargo check 無新 warning

```
$ cargo check --release --lib
warning: unused import: `super::LEAD_WINDOW_SECS_MAIN`   # pre-existing, 非 health
warning: method `make_intent` is never used              # pre-existing, 非 health
warning: `openclaw_engine` (lib) generated 2 warnings
```

2 個都是 pre-existing 與 health module 無關 warning。本 round 0 新 warning。

## 4. E2 LOW-2 + round 2 新 LOW closure 對照

| Finding | 來源 | Status |
|---|---|---|
| Sprint 5 cascade reject branch 缺直接 unit test 覆蓋 | E2 round 1 Track B LOW-2 | ✅ CLOSED — Test 1 + Test 2 直接 cover guard 1 + guard 3 |
| Sprint 5 cascade IMPL 接 fail-closed log emit 時, transition fn 端嚴格邊界缺 acceptance guard | E2 round 2 1 new LOW | ✅ CLOSED — 2 new test 形成 transition fn 端 acceptance guard, Sprint 5 IMPL 若 break 邊界會 fail |

Sprint 5 cascade IMPL 落地時：
- WARN→DEGRADED 5min dwell IMPL 後，observe_at 整合路徑會走 guard 1（same anomaly_id 24h cap）+ guard 3（count ≥ 2）
- 真實 emit fail-closed log + HEALTH_WARN row 進 `learning.health_observations`
- LAL Tier 降階 trigger (per V112 + ADR-0042 Decision 6)

本 spring 1B 補的 2 個 direct unit test 守住 transition fn 端嚴格邊界，Sprint 5 IMPL 接時若改 guard 順序 / 取消某 guard / 改 cap_entry 計數方式 → 這 2 個 test 立即 fail，形成回歸保險。

## 5. 修改檔案清單

| 檔 | 變動 | 影響 LOC |
|---|---|---|
| `srv/rust/openclaw_engine/src/health/mod.rs` | EDIT — 在 `#[cfg(test)] mod tests` 內新增 2 個 test fn（test_try_transition_fail_closed_reject_count_ge_2 + test_try_transition_cap_suppress_same_anomaly_id_repeat），0 業務邏輯改動 | +75 LOC |

無其他檔案改動。

## 6. Verdict

- **PASS** — 2 new test PASS / 既有 22 health regression 不退（升至 24 pass）/ spike integration 3 pass 不退 / 0 新 warning
- Sprint 1B early IMPL #5 任務目標達成: ≥ 2 reject direct unit test 覆蓋 ✅
- E2 round 1 LOW-2 + round 2 new LOW closure ready
- 0 業務邏輯改動 — 純測試覆蓋補強, 符合 PM 禁忌「不改 try_transition_with_cap 業務邏輯」

## 7. Operator 下一步

| Action | Owner | Priority |
|---|---|---|
| E2 review 本 round（對 2 new unit test 設計 + 對 reject branch 覆蓋完整性） | E2 (sub-agent) | P0 |
| E4 regression（cargo test --workspace + cargo check --release）走完正常流程 | E4 | P1 (待 E2 PASS) |
| Sprint 5 cascade IMPL 落地時，沿用 2 個 unit test 作 acceptance guard，並補 observe_at 整合測試 | Sprint 5 IMPL owner | P3 (未來 sprint) |

## 8. 不確定之處 / Push back

### 8.1 反模式驗 — 2 new test 不依賴 spike feature

`try_transition_with_cap` 是 `health/mod.rs` 內 private fn，`#[cfg(test)] mod tests` 可直接呼。0 spike feature 依賴；cargo test --release --lib（無 features）即可跑。

`amp_cap_entry_count()` helper 雖然標 `#[cfg(any(test, feature = "spike"))]`，但 cfg test 已涵蓋當前 test mod 編譯需求 — 0 額外 feature flag 配置。

### 8.2 Test 1 step 2 「直接呼 transition fn 繞 observe_at WARN 短路」是 spike scope 限制

per round 2 §4.2 + observe_at line 364 `(HealthWarn, _) => Ok(false)`，spike scope 不 IMPL WARN→DEGRADED dwell。所以 Test 1 step 2 要衝 count=2 必須直接呼 transition fn 而非走 observe_at — 這是 spike scope 設計限制不是 test design 妥協。Sprint 5 cascade IMPL 後可補一個對應 observe_at 整合測試（不刪本 unit test）。

### 8.3 不變的反模式邊界

per dispatch packet §2.7(c)：
- cascade gate cap + LAL Tier 降階 + 真實 fail-closed log emit 屬 Sprint 5 Tier 1 IMPL，本 unit test 只校驗 state machine 層 return false + count/entry/state 一致性
- 0 IPC / DB / writer 整合測（writer 端寫 health_observations row 是 Sprint 1B 後續任務 + Sprint 5 cascade）

---
END Report — E1 Sprint 1B early IMPL #5 — Sprint 5 cascade reject ≥ 2 unit test 覆蓋 DONE pending E2 review.
