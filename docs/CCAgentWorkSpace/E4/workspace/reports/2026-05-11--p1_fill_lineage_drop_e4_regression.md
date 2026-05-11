# Wave 1.6 P1-FILL-LINEAGE-DROP — E4 pre-deploy regression gate

**Date**: 2026-05-11
**Auditor**: E4 (Test Engineer)
**Trigger**: PA dispatch Wave 1.6 Option F4 Spine Drop Fix pre-deploy gate；E1 IMPL DONE / E2 APPROVE WITH MINOR / E5 APPROVE WITH 3 P3；PM 已 land 4 commit-前 minor fix
**Scope**: 3 Rust files diff + 3 new unit test + 1 channel cap bump + Singleton table row
- `rust/openclaw_engine/src/tasks.rs:641-655` (cap 1024→8192)
- `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs:33-103, 580-660, 680-807` (counter + 4 callsite + retry helper)
- `rust/openclaw_engine/src/agent_spine/tests.rs:1247-1476` (3 new test)

---

## 0. Deploy readiness verdict

**READY ✅** — PM 可直接 commit + push + Linux deploy

7/7 acceptance section全綠（A.1-A.5 + B + C + D + E + F + G），0 unexpected。

---

## 1. A — Rust lib test regression（A.1-A.5）

### A.1 release profile

| 項 | 值 | Baseline | Delta |
|---|---|---|---|
| passed | **2810** | 2807 (pre-Wave 1.6) | +3 (new tests) ✅ |
| failed | **0** | 0 | 0 ✅ |
| ignored | 0 | 0 | 0 ✅ |
| runtime | 0.55s / 0.58s | ~0.5s | within noise ✅ |

連跑 2 次（first 0.58s second 0.55s），同綠，**non-flaky**。

### A.2 debug profile

| 項 | 值 |
|---|---|
| passed | **2810** |
| failed | **0** |
| runtime | 0.60s |

release vs debug profile **一致**。

### A.3 W-C P1-1 invariant tests

`cargo test --lib --release -p openclaw_engine -- spine_id`：

```
running 5 tests
test agent_spine::tests::spine_ids_filled_report_id_byte_equal_with_legacy_callsite ... ok
test agent_spine::tests::spine_ids_byte_equal_across_runtime_shadow_and_dispatch_callsites ... ok
test agent_spine::tests::spine_ids_boundary_inputs_preserve_id_format ... ok
test agent_spine::tests::spine_ids_compute_filled_report_id_is_deterministic_across_100_calls ... ok
test agent_spine::tests::spine_ids_compute_is_deterministic_across_100_calls ... ok

test result: ok. 5 passed; 0 failed
```

W-C 5 個 spine_ids byte-equal / deterministic invariant **全 PASS**。Wave 1.6 0 觸碰 spine_ids 邏輯 → 預期。

### A.4 Wave 1.6 3 個 new test（連跑 5 次 flaky check）

| Test | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 |
|---|---|---|---|---|---|
| `fill_completion_channel_full_increments_drop_counter` | ok | ok | ok | ok | ok |
| `fill_completion_burst_with_8192_cap_no_drop` | ok | ok | ok | ok | ok |
| `fill_completion_retry_succeeds_after_slot_released` | ok | ok | ok | ok | ok |

**5/5 PASS · 0 flaky**。retry test deadline 500ms 給 50ms×3 + 350ms scheduler jitter 足夠，連跑 5 次完成時間 0.05-0.06s 穩定。

### A.5 W-C 既有 runtime_shadow tests

`cargo test --lib --release -p openclaw_engine -- "runtime_shadow_emit_fill_completion_lineage_writes_real_fill_chain" "runtime_shadow_lineage_emits_complete_demo_chain" "runtime_shadow_emit_fill_completion_lineage_skips_invalid_modes"`：

```
test agent_spine::tests::runtime_shadow_emit_fill_completion_lineage_skips_invalid_modes ... ok
test agent_spine::tests::runtime_shadow_emit_fill_completion_lineage_writes_real_fill_chain ... ok
test agent_spine::tests::runtime_shadow_lineage_emits_complete_demo_chain ... ok
test result: ok. 3 passed; 0 failed
```

W-C 3 既有 test **全 PASS** — emit_fill_completion 改 retry helper 不破既有正確性。

**agent_spine module-wide**：21 / 21 PASS（含 3 new + 5 spine_id + 13 既有 module test）。

---

## 2. B — Python pytest

### B.1 helper_scripts/db/ （task spec 主要範圍）

`cd /Users/ncyu/Projects/TradeBot/srv && python3 -m pytest helper_scripts/db/ -v`：

```
============================= 320 passed in 0.27s ==============================
```

含 check_55 agent_spine_healthcheck 全 PASS（與 Caveat 2 + Wave 1.6 cross-language contract 相關）。

### B.2 tests/ broader sanity

`python3 -m pytest tests/ -q --tb=no`：

| 項 | 值 |
|---|---|
| passed | 253 |
| failed | 1 |
| skipped | 2 |

1 failure：`tests/structure/test_docs_readme_index_static.py::test_archive_top_level_files_are_all_indexed`

**Verdict: PRE-EXISTING, NOT INTRODUCED BY WAVE 1.6**

- 失敗訊息：`docs/archive/2026-05-09--claude_md_section5_pre_alpha_surface.md` 未在 `docs/README.md` index
- 該 archive 檔案 git commit `c13c811e` (2026-05-09 W-AUDIT-8a Alpha Surface Foundation spec phase) 建立
- Wave 1.6 git diff **0 touch** `docs/archive/` 或 `docs/README.md`（驗 `git diff --stat docs/archive/ docs/README.md` = empty）
- 此為 docs index 維護 debt，不歸 Wave 1.6；PM 後續開單清

---

## 3. C — Mock 不掩蓋邏輯審查

3 個新 unit test mock 審查：

| Test | Mock 內容 | 真實邏輯保留 | OK? |
|---|---|---|---|
| `fill_completion_channel_full_increments_drop_counter` | 0 mock；用真 tokio mpsc cap=1 + 真 prefill 占滿 + 真 emit_fill_completion | 真 emit_fill_completion 內 4 個 try_send_with_background_retry / 真 SpineObjectEnvelope::from_strategy_signal 構造 / 真 counter fetch_add | ✅ |
| `fill_completion_burst_with_8192_cap_no_drop` | 0 mock；用真 tokio mpsc cap=8192 + 真 100 iter × emit_fill_completion + 真 rx.try_recv 計數 | 真 emit_fill_completion 內 4 個 try_send_with_background_retry × 100 iter；真 channel queue state | ✅ |
| `fill_completion_retry_succeeds_after_slot_released` | 0 mock；用真 tokio mpsc cap=4 + 真 prefill + 真 emit_fill_completion + 真 drain + 真 tokio::spawn + 真 tokio::time::sleep | 真 spawn 4 retry task / 真 50ms tick wake / 真 rx.recv() | ✅ |

**驗證**：
- `grep -iE "mock|fake|stub|patch"` 在 3 new test 範圍 = **0 testing framework keyword** hit（唯一 `stub_*` 是業務 schema 的 `stub_report_id` 字段名，非測試 stub）
- 0 `Mock`/`MagicMock`/`patch`/`mocker.patch` 
- 真實 tokio runtime + 真實 channel semantics + 真實業務邏輯 (emit_fill_completion / strategy_signal / SpineObjectEnvelope)

**Mock 邊界**：channel cap 控制 (1/4/8192) + rx 不消費控制 — **都是合法 IO 邊界 control**，不掩蓋業務邏輯。

**結論**：3 個新 test 是真實 invariant 驗，**非 happy-path mock-pass**。

---

## 4. D — Cross-language consistency

W-C `executed_by` + `fill_completion=true` contract 完整保留：

### Rust 端（runtime_shadow.rs:558-562）

```rust
DecisionEdgeType::ExecutedBy,
...
"contract": "runtime_plan_to_filled_report",
"shadow_lineage_only": true,
"fill_completion": true,
```

### Python 端（helper_scripts/db/passive_wait_healthcheck/checks_agent_spine.py）

```
line 141: # real-fill row 由新 edge filter 抓: edge_type='executed_by' AND details->>'fill_completion'='true'
line 234: AND (filled_report_edge.details->>'fill_completion')::boolean IS TRUE
```

**結論**：Rust ↔ Python contract 對齊不破。Wave 1.6 0 觸碰 spine schema / contract / edge_type / fill_completion 標記，純改 channel 傳輸層。

---

## 5. E — Hot path SLA sanity

### emit_entry_lineage（**tick hot path**）

驗證 entry path **未** 使用 retry helper：

```bash
awk '/^pub fn emit_entry_lineage/{flag=1} /^pub fn emit_fill_completion_lineage/{flag=0} flag' runtime_shadow.rs \
  | grep -c "try_send_with_background_retry"
# = 0

awk '/^pub fn emit_entry_lineage/{flag=1} /^pub fn emit_fill_completion_lineage/{flag=0} flag' runtime_shadow.rs \
  | grep -c "try_send"
# = 5（含 1 個 helper fn 名 reference + 4 個 callsite）
```

**Confirm**：entry path 4 個 callsite（line 351/354/356/433）**全用 sync `try_send`**，**0 spawn / 0 sleep / 0 mutex**。Hot path SLA 嚴格守住。

### Cargo test runtime baseline

- A.1 first run: 0.58s / 2810 test
- A.1 second run: 0.55s / 2810 test
- A.2 debug run: 0.60s / 2810 test

無顯著退化（baseline 同範圍）。3 × 50ms sleep 在 tokio::spawn 內，tokio worker 不會 starvation；3 new test 連跑 5 次 0.05-0.06s 穩定。

**結論**：SLA sanity PASS。E5 perf report 主審 < 30ns hot path 增量 + 0% tick SLA impact 與 E4 觀察一致。

---

## 6. F — Governance compliance final check

| 項 | 狀態 | Evidence |
|---|---|---|
| `runtime_shadow.rs` LOC | **843** (P2 tracked, non-blocking) | 超 800 警告線 43；< 2000 hard cap；E1+E2+E5 一致 P2 split ticket（P2-RUNTIME-SHADOW-SPLIT）；不阻 merge |
| `tests.rs` LOC | **1476** (P2 tracked, non-blocking) | pre-existing exception；本 PR +231 LOC；P2 ticket 留 W-D wave 後拆 sibling |
| `tasks.rs` LOC | **978** (pre-existing baseline) | 本 PR 淨 +11 LOC（cap 1024→8192 + 中文注釋）；pre-existing >800 framework |
| 3 個 `SPINE_CHANNEL_*` counter | **已加 CLAUDE.md §九 Singleton 表 1 row** | grep `SPINE_CHANNEL` in CLAUDE.md = 1 hit；含 PM E2 MEDIUM-2 fix 後語意警告 |
| 注釋中文政策 | **PASS** | 純英文 ≥40 char 注釋為日期/代碼引用片段，無實質純英文長段；新加 ~50 LOC 注釋全含中文成分 |
| 跨平台路徑 | **PASS** | `grep -E '/home/ncyu\|/Users/[^/]+'` 在 3 改檔 = 0 hit |
| unsafe / unwrap 新增 | **PASS** | E2 §5 已驗，diff +addition 0 hit；既存 expect/unwrap 都是 pre-fix safe pattern |
| SQL migration Guard | **N/A** | Wave 1.6 0 schema change |
| Wave 1.6 改動範圍 | **僅 3 Rust 檔 + meta-doc** | `git diff --stat` 顯示 437 insertions / 6 deletions 限於 3 Rust 檔；meta-doc + 5 new report 屬 governance artifact |

---

## 7. G — Deploy readiness verdict

| Section | Verdict |
|---|---|
| A.1 release lib test 2810/0 (2 runs same) | ✅ PASS |
| A.2 debug lib test 2810/0 | ✅ PASS |
| A.3 W-C spine_ids invariant 5/5 | ✅ PASS |
| A.4 Wave 1.6 3 new test 5 連跑 0 flaky | ✅ PASS |
| A.5 W-C 既有 runtime_shadow 3/3 | ✅ PASS |
| B Python pytest helper_scripts/db 320/0 | ✅ PASS |
| B' Python pytest tests/ broader (1 docs index pre-existing) | ✅ PASS (pre-existing not Wave 1.6) |
| C Mock 不掩蓋邏輯 | ✅ PASS |
| D Cross-language consistency | ✅ PASS |
| E Hot path SLA sanity | ✅ PASS |
| F Governance compliance | ✅ PASS (3 P2 tracked, non-blocking) |

**G Verdict: READY · PM 可 commit + push + Linux deploy**

---

## 8. 任一 unexpected

**0 unexpected。**

唯一邊際發現：runtime_shadow.rs LOC **843** vs E1 self-report **828**（差 +15）。源自 PM commit-前 land E2 MEDIUM-2 drop_total 語意警告注釋擴充（line 38-66 + line 71-82 module 頂部詳細 SAFETY/Semantic doc）；屬 PM Sign-off process 補件，**不破 governance**（仍 < 2000 hard cap）。E2 + E5 + E4 三角共識 P2 split ticket（P2-RUNTIME-SHADOW-SPLIT）走後續清。

---

## 9. PM commit + deploy 後 24h 監測 SLO（給 PM 參考，E4 不負責執行）

per E1+E2+E5 cross-consensus + QA RCA §D.7：

| 觀察項 | 預期值 | 觸發條件 |
|---|---|---|
| `[55]` chains_with_real_fill_report | 由 80-86% 升至 >99% | 24h post-deploy steady-state |
| `spine_channel_drop_total` delta | < 10 / 10min（典型 burst window）| 持續 > 50/10min = 升級 wave 2 |
| `spine_channel_retry_success_total` delta | > `drop_total` delta（retry 救援工作中）| retry_success/drop_total ratio < 0.5 = 結構性 burst > cap |
| `spine_channel_retry_fail_total` delta | < 1 / hour | 持續 > 1/hour = 8192 cap 不夠，必升 32K / unbounded |
| `[40]` realized edge (avg_net) | 不退化 | 與 N+0 baseline +8.75 bps 對比 |

---

## 10. Cross-references

- QA RCA: `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-11--p1_rca_1_orphan_er_investigation.md`
- E1 IMPL: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_fill_lineage_drop_fix.md`
- E2 review: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-11--p1_fill_lineage_drop_e2_review.md`
- E5 perf: `srv/docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-11--p1_fill_lineage_drop_e5_perf.md`
- This report: `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-11--p1_fill_lineage_drop_e4_regression.md`
- 修改 source 路徑：
  - `rust/openclaw_engine/src/tasks.rs:641-655`（cap 1024→8192）
  - `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs:33-103`（counter + accessor）
  - `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs:580-660`（emit_fill_completion 接 retry helper）
  - `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs:680-807`（try_send + try_send_with_background_retry）
  - `rust/openclaw_engine/src/agent_spine/tests.rs:1247-1476`（3 new test）

---

**E4 REGRESSION DONE: PASS · deploy READY · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-11--p1_fill_lineage_drop_e4_regression.md`**
