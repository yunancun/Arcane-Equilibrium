# E2 Review — G3-09-DAEMON-TEST-SPLIT P3

- **日期**：2026-04-28
- **基底 HEAD**：`8a5973f`
- **對象**：主 repo working tree（unstaged + untracked），純 test split
- **Verdict**：**PASS to E4 · APPROVE_WITH_NIT**

---

## 1. 改動範圍盤點

### 1.1 In scope（本 ticket）

| 路徑 | 狀態 | LOC | 內容 |
|---|---|---|---|
| `rust/openclaw_engine/tests/test_cost_edge_advisor_daemon.rs` | **D**（git rm）| -1159 | 原檔，§九 800 警告線之上 |
| `rust/openclaw_engine/tests/test_cost_edge_advisor_daemon_proofs.rs` | **A**（new）| **534** | Proof 1, 2, 3a, 4, 5（5 cases） |
| `rust/openclaw_engine/tests/test_cost_edge_advisor_daemon_dual_safeguard.rs` | **A**（new）| **380** | Proof 3b + sticky #1 + sticky #2（3 cases） |
| `rust/openclaw_engine/tests/test_cost_edge_advisor_spawn_decision.rs` | **A**（new）| **485** | FUP Case A/B/C（3 cases） |

Net 行數：-1159 + 534 + 380 + 485 = **+240**（inline helper 重複 ~120 LOC + 3 套擴充 module-level docstring）。
Test 數：5 + 3 + 3 = **11**，與 base 6 + sticky 2 + spawn 3 = 11 完美對齊（**0 add / 0 remove**）。

### 1.2 Out of scope（unstaged 但與本 ticket 無關，不在 review 範圍）

| 路徑 | 狀態 | 隸屬 ticket |
|---|---|---|
| `rust/openclaw_engine/src/main.rs` | M（-68 lines） | `MAIN-RS-PRE-EXISTING-CLEANUP P2`（PA report 2026-04-28-main_rs_pre_existing_cleanup.md）|
| `rust/openclaw_engine/src/main_scanner_init.rs` | A（new module） | 同上 |
| `program_code/exchange_connectors/.../analyst_*.py` / `h_state_*.py` | M/A | G3-08 FUP MAF/HSQ split（PA reports 2026-04-28-g3_08_fup_*.md）|

PA 自報已點明這些是 sibling session work，git diff 確認 `src/cost_edge_advisor*.rs` + `src/cost_edge_advisor/` **0 diff** ✓。本 review **不涵蓋** out-of-scope 改動（將由各自 ticket 的 E2 chain 處理）。

---

## 2. 8 條 §九 checklist

| # | Item | 狀態 | 備註 |
|---|---|---|---|
| 1 | 改動範圍與 PA 方案一致 | ✓ | 5+3+3 切分、helper inline、env_lock 各檔自持，全 match PA §3 |
| 2 | 沒有 except:pass 或靜默吞異常 | N/A | Rust 無 Python except；test `expect()` on lock/join acceptable |
| 3 | 日誌使用 %s 格式 | N/A | 純 test，無 log emission |
| 4 | 新 API 端點 _require_operator_role | N/A | 無 API 改動 |
| 5 | except HTTPException 順序 | N/A | 無 HTTP |
| 6 | detail=str(e) | N/A | 無 HTTP |
| 7 | asyncio 路由無 blocking lock | N/A | tokio test 內 std::sync::Mutex 用於 env lock — 持有期 ms 級且僅 set_var/remove_var 包裹，未跨 await（lock guard 同步釋放後才進 async 操作）✓ |
| 8 | 無私有屬性穿透 | ✓ | 全用 public API（`CostEdgeAdvisor::new` / `spawn_cost_edge_advisor` / `is_advisor_env_enabled` / `ENV_ADVISOR_FLAG` / `CostEdgeAdvisorState` enum 等） |

---

## 3. OpenClaw 9 條 special checklist

| # | Item | 狀態 | 證據 |
|---|---|---|---|
| 1 | 跨平台合規（`/home/ncyu` `/Users/[^/]+`）| ✓ | grep 3 新檔 0 命中 |
| 2 | 雙語注釋（MODULE_NOTE / docstring）| ✓ | 3 檔均有 EN + 中 MODULE_NOTE，互相 cross-reference 其他 2 檔 + 列舉 own coverage |
| 3 | Rust unsafe 零容忍 | ✓ | grep `unsafe` 0 命中 |
| 4 | unwrap()/expect() 限不可恢復 | ✓ | 0 unwrap；5 處 expect 皆於 lock acquisition + task join，test 容忍範圍 |
| 5 | 跨語言 IPC schema 一致 | N/A | 純 Rust |
| 6 | Migration Guard A/B/C | N/A | 無 SQL |
| 7 | healthcheck 配對 | N/A | 無被動等待 TODO |
| 8 | Singleton 登記 §九 表 | N/A | 無新 singleton（env_lock OnceLock 為 per-binary test scope，非 cross-process runtime singleton） |
| 9 | 文件大小 800/1200 | ✓ | 534 / 380 / 485 — 三檔均 ≤ 800 警告線，餘裕 266/420/315 |
| - | Bybit API 改動先查字典 | N/A | 無 |

---

## 4. 對抗反問結果（核心：PA spec 修正 + race / leakage / shortcut）

### Q1：PA 對 spec「同 mutex instance」修正正確性？

**PA claim**：Cargo `tests/*.rs` = 獨立 binary process，env 跨 binary 不共享 → 各檔自持 `OnceLock<Mutex<()>>` 是 SAFE。

**E2 驗證**：
- Cargo 為每個 `tests/<name>.rs` 產獨立 test binary（confirmed：`target/release/deps/test_cost_edge_advisor_daemon_proofs-35acbd98c7fb63e8` / `_dual_safeguard-6cb4cea8b9649da0` / `_spawn_decision-cc8d93c8dab30c36` 三 hash 不同 executable）
- Cargo 預設**序列跑** test binary（除非 `--test-threads`），每 binary 內並行跑 `#[test]` fn — 故跨 binary 同 ENV 同時 mutate 不會發生
- 即便 Cargo 升級為並行跑 binary（如 `cargo nextest`），OS 層 env per-process 隔離，跨 process env 仍互不影響
- 結論：**PA 修正正確**。Spec 中「同 mutex instance」假設只對單 binary 內 multiple tests 有效，跨 binary 無意義
- 各檔內 `env_lock()` 序列化單 binary 內 env-mutating tests **仍有效**（proofs 內 Proof 3a + spawn_decision 內 Case A/B/C 都各自有 env_lock 守護） ✓

### Q2：dual_safeguard.rs 為何沒有 env_lock？

**E2 grep**：`grep -n set_var dual_safeguard.rs` → 0 命中。
- Proof 3b：用 RiskConfig flag (`cost_edge.enabled=false`) 短路，**不 mutate env**
- Sticky #1/#2：純 evaluate cycle 比對 timestamp，**不 mutate env**
- 結論：**設計正確**，無需 env_lock。3 testcases 完全無 env race 風險。

### Q3：「test 通過所以沒事」mock 了什麼？真實邏輯有跑嗎？

**E2 驗證**：3 檔均用 `tokio::test(flavor = "multi_thread", worker_threads = 2)` + 真實 `spawn_cost_edge_advisor` daemon + 真實 `HStateCache` snapshot store + 真實 cancel.cancel() drain — **0 mock**。Phase A unit tests 是 evaluate() pure fn 直驅；本整合測試 spawn 真 daemon 並 await poll cycles。✓

### Q4：「沒副作用」grep 結果？

**E2 verify**：
- `grep "test_cost_edge_advisor_daemon"` 排除新檔自身 docstring → 命中皆於 `docs/CCAgentWorkSpace/{PM,E4,E2}/workspace/reports/*.md` 歷史報告，不影響 build / test
- `git diff src/cost_edge_advisor*` empty → 0 production diff
- `cargo test --lib` 2308/0 與 PA 報告 spec 完美對齊（baseline 維持）✓

### Q5：「規格一致」PA 文件第幾行對應哪行 code？

| PA §3.3 切分宣告 | 實檔證據 |
|---|---|
| proofs.rs 5 cases (1, 2, 3a, 4, 5) | `grep async fn proofs.rs` → 5 fn name 對齊 |
| dual_safeguard.rs 3 cases (3b + sticky 2) | `grep async fn dual_safeguard.rs` → 3 fn name 對齊 |
| spawn_decision.rs 3 cases (A/B/C) | `grep async fn spawn_decision.rs` → 3 fn name 對齊 |
| 11 fn name 一字未改 | E4 memory 既有 baseline（11/0）grep stability 維持 ✓ |

### Q6：edge case — Cargo 改 build/test cache key 後新檔被誤算未跑？

3 個 cargo --test 命令各自直 emit `running N tests` + `N passed` PASS line — Cargo 確實找到 binary、編譯、執行、reported；非 0-test ghost pass。✓

---

## 5. Verify 自驗結果（Mac --release）

| 命令 | 結果 |
|---|---|
| `cargo test --release -p openclaw_engine --test test_cost_edge_advisor_daemon_proofs` | **5 passed; 0 failed**（2.09s）✓ |
| `cargo test --release -p openclaw_engine --test test_cost_edge_advisor_daemon_dual_safeguard` | **3 passed; 0 failed**（0.34s）✓ |
| `cargo test --release -p openclaw_engine --test test_cost_edge_advisor_spawn_decision` | **3 passed; 0 failed**（0.23s）✓ |
| `cargo test --release -p openclaw_engine --test test_cost_edge_advisor_persistence` | **2 passed; 0 failed**（0.00s）— baseline ✓ |
| Daemon test sum | **11/0**（5+3+3）— base 6 + sticky 2 + spawn 3 = 11 ✓ |
| `cargo test --release -p openclaw_engine --lib` | **2308 passed; 0 failed**（0.56s）— PA 報告對齊 ✓ |
| 舊檔 `tests/test_cost_edge_advisor_daemon.rs` 存在? | **否**（git rm + working tree absent）✓ |
| 跨平台 grep | 0 命中 ✓ |
| `unsafe` / `unwrap` | 0 命中 ✓ |

---

## 6. Findings

| 嚴重性 | 位置 | 描述 | 修法 |
|---|---|---|---|
| LOW (informational) | 3 新檔 inline helper 重複 ~120 LOC | PA 自決採 inline 而非 `tests/common/mod.rs`；理由（§3.1）合理 — 3 檔遠低 800 + 0 Cargo subdir trick + 三檔獨立可讀。**未來若加第 4-5 個 daemon test binary，建議重評抽 common 模組**（PA 教訓 §7 已記） | 不需修，僅 informational |

**0 CRITICAL / 0 HIGH / 0 MEDIUM / 1 LOW（informational only）**。

---

## 7. PA spec 修正認可

PA 教訓 §7 第一條糾正 spec 隱含「同 mutex instance」假設：

> Cargo `tests/*.rs` 獨立 binary 的 env race 邊界 — 跨 binary process 間 env 不共享，`OnceLock<Mutex<()>>` 各檔自持是安全的（無需共用 mutex instance）。這糾正了任務 spec 中「同 mutex instance 防 race」的隱含假設 — 對單 binary 內 parallel test 為真，跨 binary 無意義。

**E2 認可此修正**。佐證：
1. Cargo 文件明示 integration tests under `tests/` 各為獨立 crate / binary
2. OS 層 env 為 per-process state（POSIX `environ` / Windows `GetEnvironmentVariable`）
3. 實測 3 binary executable hash 不同（target/release/deps/）
4. PA 設計每檔自持 OnceLock 在單 binary 內仍序列化 env-mutating tests，雙層保險（跨檔 process-isolation + 檔內 mutex）正確

PA 應將此 lesson 沉澱至 memory（已寫入 PA report §7 教訓區）。

---

## 8. 結論

**PASS to E4 · APPROVE_WITH_NIT (1 LOW informational)**

- 11/0 測試數 unchanged，5+3+3 切分對齊 PA spec
- 3 檔均 ≤ 800 LOC（534/380/485，餘裕 266/420/315）
- 0 production code diff in `src/cost_edge_advisor*`
- §九 8/8 + OpenClaw 9 條 9/9 全綠
- PA spec 修正（env mutex per-binary 假設）正確且可佐證
- 對抗反問 6 條全 PASS（mock=0 / production grep clean / regression spec 對齊 / cargo binary 真執行）
- 1 LOC informational（inline helper 重複，PA 自決理由充分，閾值守則已沉澱 §7 教訓）

**E4 下一步**：
1. ssh trade-core Linux 端跑 3 cargo --test + lib 確認 11/0 + 2308/0 跨平台一致
2. 確認 commit packaging：3 新檔 + 1 git rm 必須打包進 single commit（避免 daemon test 路徑暫時 missing 的 grep 誤導）

---

## Appendix · 命令證據

```text
$ wc -l rust/openclaw_engine/tests/test_cost_edge_advisor_daemon_*.rs
   534 ..._daemon_proofs.rs
   380 ..._daemon_dual_safeguard.rs
$ wc -l rust/openclaw_engine/tests/test_cost_edge_advisor_spawn_decision.rs
   485

$ git diff --stat HEAD -- rust/openclaw_engine/
 rust/openclaw_engine/src/main.rs                   |   84 +-     (out-of-scope, separate ticket)
 .../tests/test_cost_edge_advisor_daemon.rs         | 1159 --------------------

$ cargo test --release -p openclaw_engine --test test_cost_edge_advisor_daemon_proofs
test result: ok. 5 passed; 0 failed; 0 ignored

$ cargo test --release -p openclaw_engine --test test_cost_edge_advisor_daemon_dual_safeguard
test result: ok. 3 passed; 0 failed; 0 ignored

$ cargo test --release -p openclaw_engine --test test_cost_edge_advisor_spawn_decision
test result: ok. 3 passed; 0 failed; 0 ignored

$ cargo test --release -p openclaw_engine --lib
test result: ok. 2308 passed; 0 failed; 0 ignored
```
