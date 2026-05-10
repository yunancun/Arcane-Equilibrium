# W4 RouterLeaseGuard Drop Test — Pre-write (Sprint N+1 D+0)

- 日期: 2026-05-10
- Agent: E4 (Test Engineer)
- Task type: pre-write IMPL (sign-off pending, NOT COMMITTED, NOT DEPLOYED)
- Dispatch ref: PM Sprint N+1 D+0 W4 預寫指示
- Design ref: `docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-10--w_audit_3b_runtime_smoke_test_design.md` §3
- Status: **PASS · awaiting PM 21:30 sign-off · D+1 W4 IMPL phase deploy**

## 1. 修改摘要

| 項目 | 內容 |
|---|---|
| File | `srv/rust/openclaw_engine/src/intent_processor/router.rs` |
| Lines added | +132 LOC (line 1037 之後新加 `#[cfg(test)] mod tests` block) |
| Test count | +1 unit test (含 2 sub-cases) |
| Business logic 改動 | 0 (RouterLeaseGuard impl / Drop 行為皆不動) |

## 2. 新 unit test 設計

**Test name**: `intent_processor::router::tests::test_router_lease_guard_drop_releases_active_lease_cancelled`

**位置選擇**: 在 `router.rs` 末尾加 `#[cfg(test)] mod tests`。原因：
- `RouterLeaseGuard` 是 module-private struct (`struct RouterLeaseGuard<'a>` line 22，無 `pub`)
- 既有 7 條 `tests_predictor_router.rs::router_gate_lease_tests` 透過 `super::*` 看不到 `RouterLeaseGuard`（在 `router` private module 內）
- 唯一 isolated unit test 寫法 = 在 `router.rs` 同 module 內加 `#[cfg(test)] mod tests`，透過 `super::*` 訪問 `RouterLeaseGuard` / `acquire_lease_for_gate_1_4`

**Sub-case 1: rejection path Drop release Cancelled**
1. `GovernanceCore::new()` + `grant_paper_authorization(None)` → auth effective
2. `acquire_lease_for_gate_1_4(intent, &gov, Production, "router_w4_drop_test", now_ms)` → `Ok(LeaseId::Active(_))`
3. Pre-drop assert: `gov.lease.lock().get_live().len() == 1` (lease in live set)
4. Wrap in scoped `RouterLeaseGuard::new(&gov, Some(lease))` — 模擬 router gate 取得 lease 後 downstream gate reject (no `consume()` called)
5. Scope 結束 → automatic Drop → `release_lease(LeaseOutcome::Cancelled)` 呼叫
6. Post-drop assert: `gov.lease.lock().get_live().len() == 0` (Active → Revoked, no leak)
7. Sanity assert: `gov.lease.lock().len() == 1` (lease object 保留作 audit trail)

**Sub-case 2: consume() 後 Drop 不釋放（caller / fill consumer 接管）**
1. 第二次 acquire (timestamp now_ms+1) → `Ok(LeaseId::Active(_))`
2. Pre-consume assert: `gov.lease.lock().get_live().len() == 1` (新 lease live)
3. Wrap in `RouterLeaseGuard::new(&gov, Some(lease2))` + `guard.consume()` → 取出 inner Active lease
4. `assert!(matches!(inner, Some(LeaseId::Active(_))))` — consume 必返回 Active lease 給 caller
5. Guard auto-drop (consume 已 take 走 lease) → Drop 看到 `self.lease.is_none()` → no-op
6. Post-consume assert: `gov.lease.lock().get_live().len() == 1` (lease 仍 live, caller 接管)

## 3. cargo test 結果

### Pristine baseline (git stash uncommitted)
```
test result: ok. 2640 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.56s
```

### W4 test 加入後 (含隔壁 uncommitted W7-2 bb_reversion +3 / ma_crossover +4 tests)
**Run 1**: 2645 passed / 3 failed (persistence flaky concurrent file writer race — pre-existing)
**Run 2**: 2648 passed / 0 failed
**Run 3**: 2648 passed / 0 failed

### W4 isolated test 單跑
```
test intent_processor::router::tests::test_router_lease_guard_drop_releases_active_lease_cancelled ... ok
test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 2647 filtered out; finished in 0.00s
```

### Persistence flaky 隔離跑
```
running 7 tests
test persistence::tests::test_audit_writer_append ... ok
test persistence::tests::test_dual_state_writer_no_compat ... ok
test persistence::tests::test_dual_state_writer_writes_both ... ok
... (all 7 pass)
test result: ok. 7 passed; 0 failed
```
**結論**：persistence flakiness 是 pre-existing concurrent tmp-file write race；與 W4 test (純 in-memory `GovernanceCore` + Mutex SM) 完全隔離。第 2/3 次全量跑兩遍同 2648 PASS 證實 W4 test 100% deterministic。

### W4 net delta
- Pristine baseline: 2640
- 隔壁 uncommitted (W7-2 wave bb_reversion + ma_crossover): +7
- W4 本任務: +1
- Final: **2648 passed / 0 failed**

## 4. cargo build 結果

```bash
cd /Users/ncyu/Projects/TradeBot/srv/rust && cargo build --release --bin openclaw-engine
```

```
warning: function `reconciler_label_for_env` is never used
   --> openclaw_engine/src/tasks.rs:846:15
warning: `openclaw_engine` (bin "openclaw-engine") generated 2 warnings
    Finished `release` profile [optimized] target(s) in 38.56s
```

**PASS** (pre-existing warnings only，無新編譯錯誤)。

## 5. Mock 審查

| Test | Mock | OK? |
|---|---|---|
| `test_router_lease_guard_drop_releases_active_lease_cancelled` (sub-case 1+2) | 0 mock | ✓ 純真實 `GovernanceCore` + 真實 SM lease registry + 真實 `acquire_lease_for_gate_1_4` + 真實 `release_lease` |

**Mock 安全性 (per E4 §5.1-5.3)**：本 test 完全不 mock 任何業務邏輯（`GovernanceCore` / `DecisionLeaseSm` / SM transitions 全跑真實）；`RouterLeaseGuard::Drop` impl 真實執行 `governance.release_lease(&lease, LeaseOutcome::Cancelled)` → 真實 Active → Revoked SM transition；無外部 IO 需 mock（純 in-memory）。

## 6. 既有 9 case + Rust router_gate_lease_tests 不退化驗證

| 既有 case | 位置 | Run 2 結果 |
|---|---|---|
| 5 Python `test_executor_plan_v2.py` fail-closed cases | (Mac dev_disabled，Python pytest 不在本任務 scope) | N/A |
| 3 `test_executor_agent_unit.py` fail-closed cases | (同上) | N/A |
| 1 `test_executor_shadow_to_live_e2e.py::pre_init_ipc_failure_stays_fail_closed` | (同上) | N/A |
| Rust `intent_processor::tests::test_rejected_no_auth` | `tests.rs:88` | PASS (2648 全綠) |
| Rust `router_gate_lease_tests` 7 case (including Test 5/6 RouterLeaseGuard rejection) | `tests_predictor_router.rs:1067-1460` | PASS (2648 全綠) |

**結論**：既有 Rust 9 case 全 PASS；Python 9 case 因 Mac dev_disabled by design 不在本 cargo test scope（W4 IMPL phase D+1 deploy 後由 Linux runtime smoke 驗）。

## 7. Acceptance criteria 對照

| Criterion | Status |
|---|---|
| 1. Unit test land in `router.rs::tests` | ✓ +132 LOC |
| 2. cargo test --lib --release -p openclaw_engine PASS | ✓ Run 2/3 = 2648 / 0 |
| 3. 既有 9 case 不退化 | ✓ Rust 全 PASS；Python 待 D+1 runtime smoke |
| 4. cargo build --release --bin openclaw-engine PASS | ✓ |
| 5. Sign-off report 寫 | ✓ 本 report |

## 8. NOT COMMITTED / NOT DEPLOYED 標記

按 PM 任務指示：
- **NOT COMMITTED**：`router.rs` 改動仍 uncommitted (per `git status`)
- **NOT DEPLOYED**：未 ssh trade-core 觸發 restart_all
- **留 PM 21:30 sign-off + D+1 W4 IMPL phase deploy**

W4 sub-agent IMPL phase 收到此 report 即可：
1. 直接 commit `router.rs` 改動（已 PASS 全部 acceptance）
2. 跳過 D+1 重新設計階段（本 pre-write 已執行 design + IMPL + regression）
3. 寫 `helper_scripts/test_w_audit_3b_runtime_smoke.sh` (~80 LOC, design report §4 已給 pseudo-code)
4. ssh trade-core 跑 runtime smoke 收 4 invariant ([55] healthcheck `chains_with_lease ≥ 1` / `bad_report_quality = 0` / `chains_with_report ≥ 1` / `engine_alive=true 60s`)

## 9. 重要 finding

W4 task 提的「RouterLeaseGuard Drop release on rejection path 沒 assertion」**部分不準確**：
- Test 5 (`test_router_gate_on_production_drop_cancels_on_atr_zero`, line 1248-1286): 透過完整 `process_with_features` pipeline (ATR=0 觸發 SEC-11 fail-closed) 驗 `live=0` 證明 Drop release Cancelled
- Test 6 (`test_router_gate_exchange_path_lease_id_states`, line 1295-1380) sub-case 3: 透過完整 `process_gates_only_with_features` pipeline 驗 `live=0` 證明 Drop release on rejection (no leak)

**真正 unique gap** = 本 W4 isolated unit test 直接驗 RouterLeaseGuard struct-level RAII contract，**讓 Drop 行為脫離 pipeline 變動風險**：未來 tick_pipeline / cost_gate / SEC-11 路徑改動不會連帶污染 Drop 行為的迴歸偵測。這是真正補強 coverage 的價值。

## 10. E4 sign-off

**PASS** — W4 sub-agent IMPL phase 直接接，無需 D+1 重設計或重寫此 test。

關鍵檔案 (W4 IMPL D+1 必讀)：
- `srv/rust/openclaw_engine/src/intent_processor/router.rs` (本 report 加的 line 1037+ 新 `#[cfg(test)] mod tests` block)
- `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-10--w_audit_3b_runtime_smoke_test_design.md` (W4 完整 design)
- `srv/helper_scripts/db/passive_wait_healthcheck/checks_agent_spine.py` (lines 109-340 [55] SQL 來源, runtime smoke 直查 pattern)
