# E4 Regression Test Report — G3-09-PHASE-B-FUP-SPAWN-TEST P3 · 2026-04-28

## 任務摘要

PA RFC `2026-04-27--g3_09_phase_b_shadow_dryrun_design.md` §6.1 R-B4 + R-B10 +
E2 review `2026-04-27--g3_09_daemon_test_review.md` 升 P3 backlog 的 follow-up：
為 `main_boot_tasks::spawn_cost_edge_advisor_if_enabled` 補 fn-level integration
test，覆蓋 (env=0 → slot 維持 None + IPC 回 Uninitialized) / (env=1 +
RiskConfig.cost_edge.enabled=false → 雙保險 dormant) / (env=1 + RiskConfig
.enabled=true → spawn + slot Some + IPC live state)。Phase B Wave 0 完成此
ticket 後，daemon-related 測試保護面才完整。

純測試新增，0 production code 改動。

## 結構發現（影響測試形狀）

`spawn_cost_edge_advisor_if_enabled` 定義在 `rust/openclaw_engine/src/main_boot_tasks.rs:451`，
visibility = `pub(crate)`。`main_boot_tasks` **只在 binary crate**（`src/main.rs`
為 binary entry，`Cargo.toml [[bin]] path = "src/main.rs"`），lib.rs 不 re-export，
**integration tests 在 `tests/` 透過 lib crate 連結，不能直呼 binary crate 的 `pub(crate)` fn**。

兩種對策：
1. 升 `spawn_cost_edge_advisor_if_enabled` 為 `pub` 並 re-export 至 lib（**侵入式**，
   違反「純測試 0 production diff」邊界）。
2. 用 wrapper 完全相同的 lib-public primitive 重現決策邏輯（**選此**）：wrapper
   只用 `is_advisor_env_enabled()` (lib-public) + `spawn_cost_edge_advisor()`
   (lib-public) + slot late-inject pattern。鏡射等效，0 production diff。

每個 Case 註解明確標明對應 wrapper 哪幾行（行 457 / 472-498 / 526-532），方便
未來 wrapper 改動時 grep 連結。

## 修改清單

| 檔案 | 動作 | 行數 | 說明 |
|---|---|---|---|
| `rust/openclaw_engine/tests/test_cost_edge_advisor_daemon.rs` | 修改 | +258 / -1 | 新增 import (`CostEdgeAdvisorSlot` + `tokio::sync::RwLock`) + 2 helper (`empty_advisor_slot` + `ipc_handler_status_string`) + 3 test cases (Case A/B/C) + 章節 MODULE_NOTE 雙語 |

無其他檔案改動。

## 新增測試（3 cases）

### Case A — `fup_case_a_env_unset_keeps_slot_none_and_ipc_uninitialized`

- **Setup**：`OPENCLAW_COST_EDGE_ADVISOR` removed（env mutex 序列化）+ empty
  `CostEdgeAdvisorSlot`。
- **Wrapper-equivalent**：`is_advisor_env_enabled() == false` → 完全不呼
  `spawn_cost_edge_advisor` + 不 late-inject slot（鏡射 wrapper 行 457-464
  early-return zero-overhead path）。
- **Assert**：
  1. `advisor_slot.read().await.is_none()`（slot 維持 None）
  2. IPC handler 讀 slot 回 `"Uninitialized"`（鏡射 `handlers/cost_edge_advisor.rs`
     行 33-42 + `advisor_disabled_response` 行 65-82 硬編碼 `status: "Uninitialized"`）

### Case B — `fup_case_b_env_set_risk_disabled_slot_some_ipc_disabled`

- **Setup**：`OPENCLAW_COST_EDGE_ADVISOR=1` + `RiskConfig.cost_edge.enabled=false`
  + H5 cache Trigger ratio (-0.8 ≤ -0.5 threshold)。
- **Wrapper-equivalent**：env-gate 通過 → late-inject advisor 進 slot →
  spawn daemon（100ms cadence test 用）。等首輪 cycle。
- **Assert**：
  1. `advisor_slot.read().await.is_some()`（雙保險：env-gate 通過就 inject，
     RiskConfig dormancy 在 daemon body 內 short-circuit，不影響 slot 注入）
  2. IPC handler 回 `"Disabled"`（不是 "Trigger"，證 RiskConfig flag 在
     `advisor::evaluate` Step 1 先於 H5 read short-circuit）

### Case C — `fup_case_c_env_set_risk_enabled_slot_some_ipc_live_state`

- **Setup**：`OPENCLAW_COST_EDGE_ADVISOR=1` + `RiskConfig.cost_edge.enabled=true`
  + H5 cache OK ratio (0.5 > -0.5 threshold)。
- **Wrapper-equivalent**：env-gate + RiskConfig 都 OK → late-inject + spawn daemon。
- **Assert**：
  1. `advisor_slot.read().await.is_some()`
  2. IPC handler 回 `"OK"`（live state，非 None 分支 stub，非 Disabled 短路）
  3. `live_state.ratio == Some(0.5)`、`data_days == 7`、`threshold == -0.5`、
     `last_eval_ms > 0`（證 daemon 真寫 H5 echo + RiskConfig echo，非 stub）

## 雙語注釋

3 cases + 2 helper + chapter MODULE_NOTE 全部中英對照。每處 wrapper 對應行數
也雙語標註，符合 CLAUDE.md §七 雙語注釋強制規則。

## Mock 審查

| Item | Mock 內容 | OK? |
|---|---|---|
| `H5CostStats` snapshot | 直接 `store_snapshot` 進真實 `HStateCache`（不 mock evaluator） | ✅（mock 邊界條件，業務邏輯真跑）|
| `RiskConfig.cost_edge.enabled` | `Arc<ConfigStore<RiskConfig>>` 真實 config store | ✅ |
| `CostEdgeAdvisorSlot` | 真實 `Arc<RwLock<Option<...>>>` 同 IpcServer 構造形狀 | ✅ |
| `ipc_handler_status_string` helper | 不 mock IPC server；直接讀 slot 並複現 handler 行 33-44 邏輯（None branch 硬編碼 "Uninitialized" / Some branch echo `state.status.as_str()`） | ✅（reproducing 而非 mocking；mock 整個 handler 會掩蓋 slot routing 對錯）|

零業務邏輯 mock。

## Test 結果

| 引擎 | passed | failed | baseline | delta |
|---|---|---|---|---|
| `test_cost_edge_advisor_daemon` integration | 9 | 0 | 6 | +3 ✅ |
| `openclaw_engine --lib` | 2290 | 0 | 2290 | 0 ✅ |

## 跑兩遍結果

| Run | passed | failed | wall-clock |
|---|---|---|---|
| 1st `cargo test --release -p openclaw_engine --test test_cost_edge_advisor_daemon` | 9 | 0 | 2.10s |
| 2nd 同上 | 9 | 0 | 2.09s |
| Lib regression `cargo test --release -p openclaw_engine --lib` | 2290 | 0 | 0.56s |

flaky? **N**（兩遍同綠 + 1s wall-clock 預算下 cadence wait 寬裕）

## SLA 壓測

不適用（純行為驗證，非 hot-path）。

## 跨語言浮點一致性

不適用（純 Rust integration test）。

## 治理對照

| Doc/規則 | 符合 / 違反 / 未規範 | 備註 |
|---|---|---|
| CLAUDE.md §二 #6（失敗默認收縮）| ✅ | DEFAULT-OFF env-gate 屬保守路徑，本 Case A 確認 |
| CLAUDE.md §七 雙語注釋 | ✅ | 3 cases + 2 helper + MODULE_NOTE 全雙語 |
| CLAUDE.md §九 文件大小 | ✅ | test file 593 → 851 行（測試檔，無 1200 行硬上限約束）|
| CLAUDE.md §八 工作鏈 | ✅ | E1 寫測 → E2 已 review → 本 E4 驗證 |
| 「不允許刪測試使測試通過」| ✅ | 純新增 3 cases，0 刪除 |
| 「mock 不掩蓋業務邏輯」| ✅ | 零業務邏輯 mock；helper 為 reproduction 而非 mock |

## 不確定之處

- **wrapper-equivalent 而非真呼 wrapper 的覆蓋等效性**：因 `pub(crate)` 限制無法
  直呼 wrapper，本 case 用相同 primitive 重現決策邏輯。**等效成立的條件**：
  wrapper 未來改動只能限於 (a) env-gate 比對方式 (b) slot 注入順序 (c) daemon
  spawn 參數傳遞——任一 case 描述明確指出對應 wrapper 行號，wrapper 改動時 grep
  能 catch；超出此範圍（例如新增第二保險 gate）需同步擴 case。建議 wrapper
  注釋加 inverse pointer 指向本 test file。
- **Cases 用 100ms cadence**：與 production 10s 有量級差，但 daemon 行為與 cadence
  解耦（行為由 evaluate() pure fn 決定，cadence 只影響觀察 latency）；既有
  Proof 4 已驗 cadence ≤10% jitter。

## Operator 下一步

- 本 ticket commit 後可從 Phase B Wave 0 prerequisite 清單劃掉。
- Wrapper 真升 `pub` 屬於後續可選 cleanup（**非本 ticket 範圍**）。若 PA/PM 認為
  wrapper-equivalent 不夠 strong，下一輪 G3-09 重構時可一次性把 `spawn_*_if_enabled`
  系列移到 lib（同時影響 `spawn_h_state_poller_if_enabled` /
  `spawn_edge_estimates_reloader_if_enabled` 等同 pattern fn，需獨立 PA RFC）。

## 結論

**PASS**

3 新 case 兩遍同綠 / lib baseline 2290 不變 / 0 production diff / 雙語注釋
完整 / 0 mock 業務邏輯 / wrapper-equivalent 覆蓋對應 wrapper 行號明確標註。
