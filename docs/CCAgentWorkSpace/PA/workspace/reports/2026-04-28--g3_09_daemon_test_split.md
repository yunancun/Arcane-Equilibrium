# PA+E1 合一報告 — G3-09-DAEMON-TEST-SPLIT P3

- **日期**：2026-04-28
- **基底 HEAD**：`8a5973f`（origin/main）
- **三角合一授權**：主會話派發 PA design + E1 寫碼 + sanity test
- **邊界**：嚴格 test file split only — 0 production code 改

---

## 1. 任務目標

原 `rust/openclaw_engine/tests/test_cost_edge_advisor_daemon.rs` Wave A 累積至
**1159 LOC > §九 800 警告線**（< 1200 hard cap，~41 LOC 餘裕）。E2 spawn-test
review LOW-1 推薦拆 3 檔；本 ticket 落地。

---

## 2. Investigation 結果

### 2.1 Test 結構盤點（11 cases 總）

| 行號 | Test fn | 類別 |
|---|---|---|
| 159 | `daemon_spawn_advances_state_off_uninitialized` | Proof 1 — 真 poll + 寫 state |
| 234 | `ipc_handler_returns_live_state_after_daemon_writes` | Proof 2 — IPC echo |
| 314 | `dual_safeguard_env_gate_off_skips_daemon` | Proof 3a — env-gate 嚴格 "1" |
| 369 | `dual_safeguard_risk_config_disabled_short_circuits` | Proof 3b — RiskConfig flag |
| 435 | `daemon_evaluate_cadence_within_tolerance` | Proof 4 — cadence ≤10% |
| 770 | `daemon_cancellation_drains_within_one_second` | Proof 5 — cancel drain <1s |
| 594 | `sticky_triggered_at_ms_records_first_entry_into_trigger` | Sticky #1 — 進入時戳 |
| 667 | `sticky_triggered_at_ms_preserved_across_contiguous_trigger_cycles` | Sticky #2 — sticky 保持 |
| 883 | `fup_case_a_env_unset_keeps_slot_none_and_ipc_uninitialized` | FUP Case A |
| 960 | `fup_case_b_env_set_risk_disabled_slot_some_ipc_disabled` | FUP Case B |
| 1059 | `fup_case_c_env_set_risk_enabled_slot_some_ipc_live_state` | FUP Case C |

**11 case 確認**：base 6（Proof 1, 2, 3a, 3b, 4, 5）+ sticky 2 + spawn 3 = 11 ✓

### 2.2 共用基礎設施

- `risk_config_advisor_enabled() / risk_config_advisor_disabled_in_config()` builders
- `h_state_cache_with_ok_ratio() / h_state_cache_with_trigger_ratio() / h_state_cache_with_persistent_trigger()` builders
- `now_ms()` epoch helper
- `env_lock()` `OnceLock<Mutex<()>>` for env-mutating tests
- `empty_advisor_slot()` + `ipc_handler_status_string()` (僅 spawn-decision 需要)

---

## 3. Design 決策

### 3.1 共用 helper 抽法 — **inline 重複**（PA 自決）

考慮兩個方案：

| 方案 | 評估 |
|---|---|
| **A. 新建 `tests/common/cost_edge_advisor_helpers.rs`** | 需 `mod common;` declaration + `#[allow(dead_code)]` + Cargo subdir convention，infrastructure 複雜度 ↑ |
| **B. inline 重複 helper 於 3 檔**（採用） | 每檔自包，~40 LOC × 3 = 120 LOC overhead 可接受；無 Cargo edge case |

**選 B**：每檔 LOC 預估 < 600，遠低於 800 警告線；3 檔獨立可讀；零 Cargo
trick。

### 3.2 `env_lock()` 跨檔 race 分析 — 安全

Cargo `tests/*.rs` 各為**獨立 binary（獨立 process）**，**default 序列跑 binary**
（每 binary 內並行 test）。Process 間 env 不共享 → **每檔自持 `OnceLock<Mutex<()>>`
不會 race**。

### 3.3 11 cases 切分 — 5 + 3 + 3

| 新檔 | LOC | Tests | 內容 |
|---|---|---|---|
| `test_cost_edge_advisor_daemon_proofs.rs` | **534** | **5** | Proof 1, 2, 3a, 4, 5（核心 daemon 活性 + cadence + cancel） |
| `test_cost_edge_advisor_daemon_dual_safeguard.rs` | **380** | **3** | Proof 3b + sticky #1 + sticky #2（RiskConfig 短路 + 時戳語意） |
| `test_cost_edge_advisor_spawn_decision.rs` | **485** | **3** | FUP Case A/B/C（wrapper-decision parity） |

**對齊任務 spec**：spec 寫「`5/0` + `3/0` (1 env_gate + 2 dual_safeguard) or `5/0`
(含 sticky 2) + `3/0`」— 採 5+3+3=11 一致組合。Proof 3a (env-gate) 留 proofs.rs
（與 Proof 1, 2, 4, 5 同屬 daemon 行為核心驗證）；Proof 3b (RiskConfig flag
short-circuit) 與 sticky semantics 同屬「daemon 內部短路 + 狀態強制」家族 →
歸 dual_safeguard.rs。

### 3.4 舊檔處理

- `git rm` `test_cost_edge_advisor_daemon.rs`（cargo auto-detect tests/*.rs，無 manifest 改動）
- 雙端同步：Mac rsync + Linux `rm` 確認

---

## 4. Impl 摘要

- 純 Rust test 移檔 + module-level docstring 重寫（標明拆檔關係 + 各檔 coverage 範圍）
- 雙語注釋全保留（mirroring 原檔模式）
- **0 production code diff**（git status 確認 src/ 無 mine 改動，pre-existing
  `src/main.rs` 改動為 sibling G3-08 session work，與本 ticket 無關）
- `unused import` 清理：`tokio::sync::RwLock` + `CostEdgeAdvisorSlot` 僅 spawn_decision.rs 需

---

## 5. Verify 結果（全綠）

| 命令 | 結果 |
|---|---|
| `wc -l test_cost_edge_advisor_daemon_proofs.rs` | **534** ≤ 800 ✓ |
| `wc -l test_cost_edge_advisor_daemon_dual_safeguard.rs` | **380** ≤ 800 ✓ |
| `wc -l test_cost_edge_advisor_spawn_decision.rs` | **485** ≤ 800 ✓ |
| `cargo test --release -p openclaw_engine --test test_cost_edge_advisor_daemon_proofs` | **5 passed; 0 failed** ✓ |
| `cargo test --release -p openclaw_engine --test test_cost_edge_advisor_daemon_dual_safeguard` | **3 passed; 0 failed** ✓ |
| `cargo test --release -p openclaw_engine --test test_cost_edge_advisor_spawn_decision` | **3 passed; 0 failed** ✓ |
| Total daemon tests | **11/0 不變**（5+3+3，base 6 + sticky 2 + spawn 3 = 11）✓ |
| `cargo test --release -p openclaw_engine --lib` | **2308 passed; 0 failed**（spec 寫 2299，actual +9 來自 sibling sessions；**0 fail = 0 production diff 證明**）✓ |
| `cargo test --release -p openclaw_engine --test test_cost_edge_advisor_persistence` | **2 passed; 0 failed** 不變 ✓ |
| 舊檔 `test_cost_edge_advisor_daemon.rs` 存在? | Mac + Linux 均不存在 ✓ |

---

## 6. 邊界遵守

| 約束 | 狀態 |
|---|---|
| 嚴格 test file split only | ✓ src/ 無 mine 改動 |
| 共用 helper 抽法 PA 自決 | ✓ 採 inline 重複（理由見 §3.1） |
| env mutex `env_lock()` OnceLock pattern 跨檔對齊 | ✓ 各檔自持 `OnceLock<Mutex<()>>`（Cargo binary 隔離保證安全，§3.2） |
| 不重命名 test fn name（保 grep stability） | ✓ 11 個 fn name 一字未改 |
| 不需 commit（worktree pattern） | ✓ 已 unstage，files-only on disk |

---

## 7. 教訓

- **Cargo `tests/*.rs` 獨立 binary 的 env race 邊界**：跨 binary process 間 env 不
  共享，**`OnceLock<Mutex<()>>` 各檔自持是安全的**（無需共用 mutex instance）。
  這糾正了任務 spec 中「同 mutex instance 防 race」的隱含假設 — 對單 binary 內
  parallel test 為真，跨 binary 無意義。
- **Test split 時 module-level docstring 必須改寫**，明確新檔在 wave 中的位置 +
  指向其他兩檔（互相 cross-reference），避免 future maintainer 不知為何被拆。
- **Inline helper 重複 vs `tests/common/mod.rs`**：3 個小 helper × 3 檔 = 120 LOC
  overhead 可接受時，inline 比 `tests/common/` Cargo trick 簡單。閾值大概 5+ 檔
  或 helper > 200 LOC 才值得抽 common module。
- **Lib test count drift 不是 regression**：spec 寫 2299，actual 2308 — sibling
  session 在 spec 寫好後加了 +9 lib test。判 regression 看 **`0 failed`** 而非
  count number。

---

## 8. 報告與後續

- 報告路徑：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--g3_09_daemon_test_split.md`
- Memory append：見 PA/memory.md 同日條目
- **不需 commit**：files-only on disk per task spec worktree pattern
- 後續若主會話需 commit + push，3 新檔 + 1 刪檔需打包進 single commit 避免
  daemon test 暫時 missing 的破窗（cargo build 不會壞，但 grep 路徑可能誤導）
