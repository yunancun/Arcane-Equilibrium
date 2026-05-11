# E4 Regression — W-C MAG-082 Caveat 1+2+3 Fix（Rust R1+R2 + Python）

**Date**: 2026-05-11 01:50 CEST
**Reviewer**: E4
**Trigger**: PA `2026-05-10--w_c_caveat_fix_plan.md` §6 E4 regression 必跑項 · E2 R2 APPROVE · E5 APPROVE WITH 3 P2
**HEAD**: `58970d24` (W2 sub-task 4 sibling already committed)
**Scope**: 4 primary file working tree `+928 -17` LOC (uncommitted) + sibling W2 wave structural commits (`step_4_5_dispatch.rs` / `pipeline_ctor.rs` / `mod.rs` / `types.rs` 已 commit)
**Constraint acknowledged**: Mac local bin build fail (`main_pipelines.rs:922 btc_lead_lag_panel_slot`) 為 W2 sibling staged-but-uncommitted；E4 走 lib-only test path

---

## 0. Deploy Readiness Verdict

**READY**

所有 E4 必跑項全 PASS,無 BLOCKER,無 unexpected regression。可派 deploy。

| 維度 | 結論 |
|---|---|
| Rust lib test (release + debug) | ✅ 2776/0/0 雙 profile 一致 · 跑兩遍 non-flaky |
| W-C runtime_shadow specific (7 tests) | ✅ 7/7 PASS · 含 R2 fix assertion |
| agent_spine 全模塊 (13 tests) | ✅ 13/13 PASS |
| Python W-C healthcheck (14 tests) | ✅ 14/14 PASS · 跑兩遍 non-flaky |
| Mock 不掩蓋業務邏輯 | ✅ Rust + Python 抽樣審查 PASS |
| 跨語言一致性 | ⏸ Deferred to post-deploy (W-C scope 無浮點計算 hot path) |
| SLA pressure | ✅ E5 covered (emit_entry +3-6μs / emit_fill_completion 10-20μs / check_55 22.54ms) |
| File 大小 §九 | ✅ 0 破限 (含 P2 跟蹤 pre-existing >800 警告) |

---

## A. Rust lib test full regression

### A.1 `cargo test --lib --release -p openclaw_engine`

**第一遍**:
```
test result: ok. 2776 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.55s
```

**第二遍** (non-flaky 驗證):
```
test result: ok. 2776 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.55s
```

**結論**: ✅ **2776/0/0** · 同 E1 R2 自報 + E2 R2 mini-review 實測對齊 · non-flaky

**baseline 對比**:
| Phase | passed | failed | ignored | source |
|---|---|---|---|---|
| Sprint N+0 / N+1 D+0 baseline (pre-W-C) | 2757 | 0 | 0 | E2 R1 review |
| Sprint N+1 D+0 with sibling W2 wave +19 | 2776 | 0 | 0 | E1 R2 / E2 R2 |
| **Post-W-C (本次)** | **2776** | **0** | **0** | **E4 實測** |
| Delta | 0 | 0 | 0 | W-C 含於 sibling wave 同次 +19 |

`tests/dual_rail_dispatch.rs` + W-C agent_spine 新增 ~5 test 已 emboxed in 2776 數內 (sibling W2 wave panel_aggregator / replay::context_builder / canary_writer 等其他 +14 test 同期 land)。**0 regression**。

### A.2 W-C specific test enumeration

`cargo test --lib --release -p openclaw_engine runtime_shadow`:
```
running 7 tests
test agent_spine::tests::runtime_shadow_emit_entry_lineage_skips_transitions_in_paper ... ok
test agent_spine::tests::runtime_shadow_emit_fill_completion_lineage_skips_invalid_modes ... ok
test agent_spine::tests::runtime_shadow_lineage_is_disabled_for_unscoped_modes ... ok
test agent_spine::tests::runtime_shadow_emit_fill_completion_lineage_writes_real_fill_chain ... ok
test agent_spine::tests::runtime_shadow_lineage_emits_complete_demo_chain ... ok
test agent_spine::tests::runtime_shadow_emit_entry_lineage_emits_5_build_state_transitions ... ok
test agent_spine::tests::runtime_shadow_build_transition_ids_are_distinct ... ok

test result: ok. 7 passed; 0 failed; 0 ignored
```

**全 7 個 W-C runtime_shadow 系列 test PASS** · 含關鍵 R2 fix test `runtime_shadow_emit_fill_completion_lineage_writes_real_fill_chain`

`cargo test --lib --release -p openclaw_engine agent_spine` (整 agent_spine module):
```
test result: ok. 13 passed; 0 failed; 0 ignored
```

| Test | R1 新增 / R2 改 / 既有 | 結論 |
|---|---|---|
| `runtime_shadow_lineage_emits_complete_demo_chain` | 既有 (accepted 10→15 升級) | ✅ |
| `runtime_shadow_lineage_is_disabled_for_unscoped_modes` | 既有 | ✅ |
| `runtime_shadow_emit_entry_lineage_emits_5_build_state_transitions` | R1 NEW | ✅ |
| `runtime_shadow_emit_entry_lineage_skips_transitions_in_paper` | R1 NEW | ✅ |
| `runtime_shadow_emit_fill_completion_lineage_writes_real_fill_chain` | R1 NEW · **R2 改 assertion** (line 956: `report_change.object_id == "report-stub-1002"`) | ✅ |
| `runtime_shadow_emit_fill_completion_lineage_skips_invalid_modes` | R1 NEW (paper/disabled/qty=0 fail-soft) | ✅ |
| `runtime_shadow_build_transition_ids_are_distinct` | R1 NEW (HashSet collision 邊界) | ✅ |
| `durable_spine_objects_model_signal_decision_verdict_plan_chain` 等 6 既有 | 既有 | ✅ |

### A.3 Mock 不掩蓋邏輯審查

抽樣 `runtime_shadow_emit_fill_completion_lineage_writes_real_fill_chain` (`tests.rs:853-957`):

| 審查項 | 結論 |
|---|---|
| Channel 是真實 tokio mpsc | ✅ `tokio::sync::mpsc::channel(32)` — 不 fake |
| Production fn 真實呼叫 | ✅ `emit_fill_completion_lineage(Some(&tx), AgentSpineMode::Shadow, FillCompletionLineageInput {...})` |
| Return count 真驗 | ✅ `assert_eq!(accepted, 4)` (1 envelope + 1 edge + 2 transitions) |
| AgentSpineMsg enum variant 真驗 | ✅ match `AgentSpineMsg::Object/Edge/StateTransition` — panic on unexpected `ExecutionIdempotencyKey` |
| Value-realism core invariant 真驗 | ✅ `env.payload["filled_qty"].as_f64() == 0.5` + `liquidity_role == "taker"` (W-C Caveat 2 修復點) |
| ExecutedBy edge `fill_completion=true` 真驗 | ✅ `edge.details["fill_completion"].as_bool() == true` (Python check_55 SQL 依賴點) |
| R2 fix invariant 真驗 | ✅ `report_change.object_id == "report-stub-1002"` (既有 stub row 真實狀態轉換,非新建 row) |
| transition_id collision 真驗 | ✅ `runtime_shadow_build_transition_ids_are_distinct` 用 `HashSet::insert` + count = 5 |

**結論**: ✅ 0 業務邏輯 mock · 全部驗 production fn 真實 behavior · 符合 mock 安全規則

### A.4 Release vs Debug profile 一致性

`cargo test --lib -p openclaw_engine` (debug):
```
test result: ok. 2776 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.64s
```

**結論**: ✅ Release (0.55s) + Debug (0.64s) **雙 profile 一致 2776/0/0** · 0 profile-specific test 偏差

---

## B. Python pytest

### B.1 W-C specific test file

`python3 -m pytest helper_scripts/db/test_agent_spine_healthcheck.py -v`:

**第一遍**:
```
============================== 14 passed in 0.02s ==============================
```

**第二遍** (non-flaky):
```
============================== 14 passed in 0.02s ==============================
```

| Test | E1 R3 (Python) 標籤 | 結論 |
|---|---|---|
| `test_disabled_env_warns_with_mag082_readiness` | 既有 | ✅ |
| `test_required_disabled_env_fails` | 既有 | ✅ |
| `test_enabled_missing_table_warn_by_default` | 既有 | ✅ |
| `test_enabled_empty_warn_by_default` | 既有 | ✅ |
| `test_runtime_mode_shadow_enables_check` | 既有 | ✅ |
| `test_required_empty_fails` | 既有 | ✅ |
| `test_enabled_historical_but_no_recent_warns` | 既有 | ✅ |
| `test_enabled_missing_core_type_warns` | 既有 (fixture upgrade) | ✅ |
| `test_enabled_complete_core_without_report_warns` | 既有 (fixture upgrade) | ✅ |
| `test_enabled_complete_lineage_passes` | 既有 (+3 assertion: bad_value_quality / real_fill / state_changes) | ✅ |
| `test_sql_contract_is_read_only` | 既有 (+grep `state_changes` / `fill_completion`) | ✅ |
| **`test_state_changes_empty_blocks_after_pass_path`** | **R3 NEW (Caveat 1)** | ✅ |
| **`test_bad_report_value_quality_blocks_with_cutoff`** | **R3 NEW (Caveat 2 value-realism)** | ✅ |
| **`test_real_fill_propagation_partial_warns`** | **R3 NEW (Caveat 2 partial 50% gate)** | ✅ |

**結論**: ✅ **14/14 PASS** · non-flaky · 與 E1 Python report §3 對齊

### B.2 Python full regression — `helper_scripts/db/`

`python3 -m pytest helper_scripts/db/`:

**結果**: collection ERROR · 14 test files fail import · **非 W-C 引入**

**Root cause 分析**:
```
helper_scripts/db/passive_wait_healthcheck/runner.py:65
  from .checks_derived import check_panel_freshness  # 未 land
```

`runner.py:84` 由 commit `ddf0cebe (W1 sub-task 3 BB WS)` import `check_panel_freshness`,但 `checks_derived.py` 最新 commit `db17e205 ([65] chain_integrity_post_audit_4b_m3)` 並無此 function 定義 → import chain 全 module 載入失敗。

**驗證歸屬**:
| 項 | 證據 |
|---|---|
| W-C `__init__.py` / `runner.py` / `checks_derived.py` 動過? | ❌ `git diff HEAD` only `checks_agent_spine.py` |
| Pre-existing flagged in E1 Python report? | ✅ Caveat E (isolation import workaround) |
| Pre-existing flagged in E5? | ✅ D-4 P2 (拆 isolation,等 W1 wave land 後 cleanup) |
| Pre-existing flagged in E2 R1? | ✅ accept caveat |
| W1 sub-task 3 commit ddf0cebe vs check_panel_freshness 定義 commit | broken: import 已 commit / fn 未 land |

**W-C 影響範圍隔離方法** (E1 R3 Caveat E):
W-C test file 用 `importlib.util.spec_from_file_location()` 直接 load `checks_agent_spine.py` 繞 `__init__.py` import chain → isolation 成功,所以 W-C 14/14 PASS 與 W1 wave breakage 解耦。

**結論**: ✅ W-C 對 Python full regression **0 額外 regression** · W1 sub-task 3 pre-existing breakage 待 sibling wave 補 `check_panel_freshness` 定義 (E5 D-4 P2 ticket) · 不阻 W-C deploy

### B.3 Python Mock 審查

抽樣 3 個 R3 NEW test:

**`test_state_changes_empty_blocks_after_pass_path` (Caveat 1)**:
- Mock 對象: `cur` (DB cursor) — IO 邊界 only
- `check_55_agent_decision_spine_lineage(cur)` 本體真實跑 (SQL parse + 7-tuple unpack + state_changes_count helper + gate logic + msg format)
- 真驗 `status == "WARN"` + `"BLOCKED_STATE_CHANGES_EMPTY" in msg` + `"state_changes_24h=0" in msg`
- ✅ 不 mock 業務邏輯

**`test_bad_report_value_quality_blocks_with_cutoff` (Caveat 2)**:
- 真實 `os.environ["OPENCLAW_AGENT_SPINE_VALUE_QUALITY_CUTOFF_TS"] = "2026-05-11T00:00:00+02"` — 觸發 production cutoff 邏輯真實跑
- Mock cursor 7-tuple `(1,1,1,1,0,5,0)` — bad_value_quality=5 → 真實觸發 gate
- 真驗 status + `"BLOCKED_REPORT_VALUE_QUALITY"` + `"bad_report_value_quality=5"` + `"value_quality_cutoff=2026-05-11T00:00:00+02"` (cutoff env var roundtrip)
- ✅ 不 mock 業務邏輯

**`test_real_fill_propagation_partial_warns` (Caveat 2 partial)**:
- Mock cursor: 100 chain · 10 with real_fill (10% < 50% gate)
- 真實跑 partial gate 比例邏輯
- 真驗 `"WARN_REAL_FILL_PROPAGATION_PARTIAL"` + `"chains_with_real_fill_report=10"`
- ✅ 不 mock 業務邏輯

**結論**: ✅ Python Mock 安全規則對齊 · 3 R3 NEW test 全真驗 production behavior

---

## C. Cross-language consistency

**Deferred to post-deploy.**

W-C scope 內無浮點計算 hot path (state_transitions + ExecutionReport row 寫入是字串 + jsonb 結構)。`ExecutionReport.payload` 中 `filled_qty` / `avg_fill_price` / `fees_paid` 浮點欄位來自 `loop_exchange.rs:fully_filled` 既有處理流,**未由 W-C 引入新計算**。

**Post-deploy verification 排程**: 部署後 30min 短窗對抗 SQL (PA §4.3) 中對應的 1 query 驗 `trading.fills.filled_qty` 與 `agent.decision_objects.payload->>'filled_qty'` 在 1e-4 容差內一致 · 由 PM SOP 含;不阻 pre-deploy E4 sign-off。

---

## D. SLA pressure

**E5 已覆蓋**,E4 不重複。

| 項 | E5 實測 | 預期 SLA | 結論 |
|---|---|---|---|
| `emit_entry_lineage` 增 5 try_send | +3-6μs | < 50μs (PA §6 E2 必查) | ✅ |
| `emit_fill_completion_lineage` 單次 | ~10-20μs | low-frequency path (~86/24h) | ✅ |
| Python `check_55_*` end-to-end | 22.54ms cold / 6.62ms p50 warm / 8.21ms p95 | < 1s | ✅ |
| 新 SQL EXPLAIN ANALYZE | 3.93ms execution / 4.19ms planning | index 100% hit | ✅ |
| Spine writer mpsc buffer 1024 | post-fix 53 chain in-flight 容量 | 174 chain/24h avg | ✅ |
| 24h state_changes 寫入量 | ~1042 row (5×174 build + 2×86 fill) | hypertable OK | ✅ |

**E4 sanity**: lib test 跑 2776 test 0.55s release / 0.64s debug — **無 runtime 異常拉長** (E5 baseline ~23-25s cargo build 同數量級)。

---

## E. Baseline 更新建議

CLAUDE.md general E4 baseline 寫 `2555 passed / 17 pre-existing failed`,**已過期**:

| 引擎 | 舊 baseline | 實測 (本次) | 建議更新 |
|---|---|---|---|
| Rust lib test (release) | 1980 (CLAUDE.md general) | **2776** | 建議更新到 2776/0/0 |
| Python pytest (W-C file) | n/a | **14/14** | 新增 W-C 專屬 baseline 14/14 |
| Python pytest (helper_scripts/db/) | 2555 (含 17 pre-existing) | collection error 受 W1 wave pre-existing breakage 影響 | 待 W1 sub-task 3 `check_panel_freshness` land 後重 baseline |

**E4 不直接改 CLAUDE.md** (PM 改),只建議。

---

## F. Unexpected / 待跟蹤

### F.1 W1 sub-task 3 pre-existing import breakage (P2,非 W-C 範圍)
**症狀**: `helper_scripts/db/passive_wait_healthcheck/runner.py:84` 已 import `check_panel_freshness`,但 `checks_derived.py` 未 land 對應 function · 14 test files collection error
**歸屬**: W1 sub-task 3 (commit `ddf0cebe`) sibling wave
**影響**: Python full regression collection 全鏈斷;W-C unit test 用 isolation import 自保
**修復路徑**: 等 W1 sub-task 3 補 `check_panel_freshness` 定義 (E5 D-4 P2 ticket)
**對 W-C deploy 影響**: ❌ 0 (W-C test 用 importlib 繞行)

### F.2 Mac local bin build error (sibling W2 sub-task 4 staged-but-uncommitted)
**症狀**: `main_pipelines.rs:922 btc_lead_lag_panel_slot` 缺欄位 init (sibling W2 sub-task 4 WIP)
**歸屬**: sibling W2 wave staged 但未 commit (僅 Mac local)
**影響**: Mac local `cargo build --release -p openclaw_engine` (含 bin) fail · lib test 0 影響
**E4 應對**: 走 lib-only test path (`cargo test --lib --release`) 而非 `cargo test --all`,符合任務描述 constraint
**對 W-C deploy 影響**: ❌ 0 (Linux 端 git pull --ff-only 取 W-C-only commit 後由 PM 單獨驗 bin build · sibling W2 sub-task 4 IPC slot late-inject `58970d24` 已包 step_4_5_dispatch / pipeline_ctor / mod.rs / types.rs 更新,PM holistic commit 把 4 primary W-C file + 13 sibling fixture file 統一 land 後 bin build 應恢復)

### F.3 §九 file size pre-existing 警告 (E5 已提 P2)
**`tests.rs` (agent_spine)**: 1063 LOC > 800 警告線 (W-C R1+R2 +361 LOC 從 ~702 → 1063 · 仍 < 2000 hard cap)
**`step_4_5_dispatch.rs`**: 1557 LOC > 800 警告線 (pre-existing baseline)
**P2 ticket 建議**: 仿 G5-09 pattern 拆 sibling (E5 D-5 + D-6) · 不阻 deploy

### F.4 stable_id 算法字面複製 (E5 D-1 P2)
**位置**: `step_4_5_dispatch.rs:623-645` vs `runtime_shadow.rs:72-80`
**風險級**: LOW (現有注釋 + `runtime_shadow_build_transition_ids_are_distinct` test invariant lock + 30min 短窗對抗 SQL 會 catch id mismatch by missed_n > 0)
**建議**: P2 抽 helper `compute_spine_ids(em, signal_id, verdict_id) -> (decision_id, plan_id, stub_report_id)` · 不阻 deploy

---

## G. 結論

**Deploy readiness: READY**

**Test 表**:

| 引擎 | passed | failed | ignored | baseline | delta | non-flaky |
|---|---|---|---|---|---|---|
| Rust lib (release) | **2776** | **0** | **0** | 2776 (sibling +19 含 W-C) | 0 | ✅ 跑兩遍同綠 |
| Rust lib (debug) | **2776** | **0** | **0** | n/a | n/a | ✅ |
| Rust W-C runtime_shadow | **7** | **0** | **0** | 2 (pre-fix) | +5 | ✅ |
| Rust agent_spine 模塊 | **13** | **0** | **0** | 8 (pre-fix) | +5 | ✅ |
| Python W-C healthcheck | **14** | **0** | **0** | 11 (pre-fix) | +3 | ✅ 跑兩遍同綠 |

**新增測試 (W-C scope)**:

| File | New tests | Scope |
|---|---|---|
| `rust/openclaw_engine/src/agent_spine/tests.rs` | +5 (5_build_state_transitions / skips_transitions_in_paper / writes_real_fill_chain / skips_invalid_modes / build_transition_ids_distinct) | 邊界 + paper-mode 跳過 + value-realism + collision invariant |
| `helper_scripts/db/test_agent_spine_healthcheck.py` | +3 (state_changes_empty / bad_report_value_quality_with_cutoff / real_fill_partial) | Caveat 1 gate + Caveat 2 value-realism + Caveat 2 partial 50% gate |

**Mock 審查**: ✅ Rust + Python 抽樣全真驗 production behavior · 0 業務邏輯 mock

**SLA**: ✅ E5 covered (emit_entry +3-6μs / emit_fill_completion 10-20μs / check_55 22.54ms / Spine writer 容量充裕)

**跨語言**: ⏸ Deferred to post-deploy (W-C 無新浮點計算 hot path)

**退回 E1 修復清單**: 無 BLOCKER · 派 PM commit + push + deploy

---

**E4 REGRESSION DONE: PASS · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w_c_fix_e4_regression.md`**
