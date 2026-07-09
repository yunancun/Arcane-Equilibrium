# E1-W-C-FIX-3 IMPL Report — Python [55] healthcheck value-realism upgrade

**日期**：2026-05-10 (Mac dev time 2026-05-11)
**Agent**：E1 (Backend Developer)
**Task SoT**：`srv/docs/CCAgentWorkSpace/PA/2026-05-10--w_c_caveat_fix_plan.md` §3 + §4 + §5 Task E1-W-C-FIX-3
**Trigger**：QA `2026-05-10--w_c_signoff_audit.md` CONDITIONAL_PASS caveat 2（174/174 ExecutionReport stub payload；[55] `bad_report_quality=0` 只查 key existence 不查 value-realism）
**Scope**：純 Python；`helper_scripts/db/passive_wait_healthcheck/checks_agent_spine.py` 加 `bad_report_value_quality` / `chains_with_real_fill_report` / `state_changes_24h` 三新指標 + 3 PASS gate + 對應 unit test

---

## 1. 修改檔案清單

| 檔 | line range（after edit） | 變更摘要 |
|---|---|---|
| `helper_scripts/db/passive_wait_healthcheck/checks_agent_spine.py` | line 33-41 / 64-72 / 109-258 / 261-287 / 359-460 | + 2 module constants（`_VALUE_QUALITY_CUTOFF_DEFAULT` / `_REAL_FILL_PARTIAL_RATIO`）；+ `_value_quality_cutoff_ts()` helper；`_complete_chain_counts()` SQL 加 2 select column + 2 LEFT JOIN（filled_report_edge / filled_report），返回 7-tuple；新 `_state_changes_count_24h()` helper；`check_55_*` unpack 7-tuple + state_changes + value_quality_cutoff_ts，加 3 PASS gate；detail message 加 3 新指標 + cutoff |
| `helper_scripts/db/test_agent_spine_healthcheck.py` | line 1-43 / 161-261 / 327-450 | isolation import（繞 package `__init__.py` pre-existing breakage）；既有 5 fixture 從 5-tuple → 7-tuple + 加 state_changes fetchone；3 新 case：`test_state_changes_empty_blocks_after_pass_path` / `test_bad_report_value_quality_blocks_with_cutoff` / `test_real_fill_propagation_partial_warns`；SQL contract test 加 grep `agent.decision_state_changes` + `fill_completion` |

---

## 2. 新增 LOC（中/英/code 三分類）

| 項 | LOC | 備註 |
|---|---|---|
| Production code (`checks_agent_spine.py`) | +112 | 18 module-level + 24 helper + 36 SQL 擴充 + 10 state_changes helper + 24 check_55 gate logic |
| Test code (`test_agent_spine_healthcheck.py`) | +142 | 11 import isolation + 16 既有 fixture 更新 + 115 三新 test case |
| **Total** | **+254** | |
| 中文注釋（純中文 block / inline） | ~38 LOC | 完全符合 CLAUDE.md §七 2026-05-05 governance（默認中文，無新英文-only block） |
| 英文 inline notes（既有保留） | 0 新增 | 既有 `BLE001` noqa / SQL English keyword 不算注釋 |

### 注釋語言驗證
`grep -nE '^[[:space:]]*#[[:space:]]*[A-Z]' checks_agent_spine.py | head -10` 無新增純英文長 block（既有 MODULE_NOTE 中英對照保留不動，符合「修改既有 bilingual 才移除英文」governance；本 IMPL 未動 MODULE_NOTE）。

---

## 3. pytest 結果

```
$ python3 -m pytest helper_scripts/db/test_agent_spine_healthcheck.py -v
============================== 14 passed in 0.03s ==============================
```

| 測試 | 既有 / 新加 | 結果 |
|---|---|---|
| `test_disabled_env_warns_with_mag082_readiness` | 既有 | PASS |
| `test_required_disabled_env_fails` | 既有 | PASS |
| `test_enabled_missing_table_warn_by_default` | 既有 | PASS |
| `test_enabled_empty_warn_by_default` | 既有 | PASS |
| `test_runtime_mode_shadow_enables_check` | 既有 | PASS |
| `test_required_empty_fails` | 既有 | PASS |
| `test_enabled_historical_but_no_recent_warns` | 既有 | PASS |
| `test_enabled_missing_core_type_warns` | 既有（fixture 升級）| PASS |
| `test_enabled_complete_core_without_report_warns` | 既有（fixture 升級）| PASS |
| `test_enabled_complete_lineage_passes` | 既有（fixture 升級 + 加 3 assertion）| PASS |
| `test_sql_contract_is_read_only` | 既有（fixture 升級 + 加 grep `state_changes` / `fill_completion`）| PASS |
| **`test_state_changes_empty_blocks_after_pass_path`** | **新加 (Caveat 1)** | **PASS** |
| **`test_bad_report_value_quality_blocks_with_cutoff`** | **新加 (Caveat 2)** | **PASS** |
| **`test_real_fill_propagation_partial_warns`** | **新加 (Caveat 2 partial gate)** | **PASS** |

**總計 14/14 PASS**（11 既有 + 3 新加；3 既有 fixture upgraded retain PASS）。

---

## 4. SQL query Linux PG empirical < 1s 確認

```
$ ssh trade-core "python3 ... check_55_agent_decision_spine_lineage(cur)"
status=WARN
elapsed_ms=22.54
msg=agent decision spine state-changes empty; MAG-082 readiness=BLOCKED_STATE_CHANGES_EMPTY
    window=1440m modes=demo,live_demo
    objects=860/2560 edges=688/2048 idempotency=172/512
    types=strategy_signal=172,strategist_decision=172,guardian_verdict=172,
          execution_plan=172,execution_report=172
    chains=172 chains_with_idempotency=172 chains_with_lease=172
    chains_with_report=172 bad_report_quality=0 bad_report_value_quality=0
    chains_with_real_fill_report=0 state_changes_24h=0
    value_quality_cutoff=1970-01-01T00:00:00+00
```

| 項 | 值 | 結論 |
|---|---|---|
| End-to-end check_55 elapsed | **22.54 ms** | **遠 < 1s SLA** |
| 內含 query | 3× to_regclass + 3× aggregate_counts + 1× type_counts + 1× complete_chain_counts (8 join) + 1× state_changes_count_24h | 全跑共 8 SQL |
| W-C 真實狀態揭露 | state_changes_24h=0 觸發新 BLOCKED_STATE_CHANGES_EMPTY | Caveat 1 正確命中 |
| 預設 cutoff 哨兵 | 1970-01-01 → bad_report_value_quality=0 + chains_with_real_fill_report=0（Rust FIX-2 未部署 0 row real-fill）| 符合 PA §2.4 推薦 a：歷史 stub 不過濾，Rust 上線後 operator 設 deploy_ts 才啟動 cutoff |

EXPLAIN ANALYZE 樣本（單獨 _complete_chain_counts SQL，1440 min window）：
```
$ psql -f /tmp/check55_test.sql
Time: 14.121 ms (complete_chain_counts with new joins)
Time: 1.000 ms (state_changes count)
```

---

## 5. Self-check 8 條 acceptance 逐條結論

| # | Acceptance | 結論 |
|---|---|---|
| 1 | `python -m py_compile checks_agent_spine.py` 綠 | **PASS** (py_compile OK) |
| 2 | `pytest test_agent_spine_healthcheck.py -v` 綠（既有 + 3 新）| **PASS** (14/14 PASS) |
| 3 | 新 SQL Linux PG < 1s | **PASS** (22.54 ms end-to-end，遠 < 1s) |
| 4 | 注釋 grep 只見中文，無新增英文-only block | **PASS** (新加 ~38 LOC 注釋全中文；既有 MODULE_NOTE 中英對照保留不動) |
| 5 | 既有 PASS state（`LINEAGE_READY_NOT_WINDOW_PASS`）不變，只是 detail 多 3 field | **PASS** (新指標附加至 detail；PASS message 不變；新 gate 在既有 4 gate 後追加，不破既有判定) |
| 6 | 既有 FAIL conditions 順序不變（新條件加在 `bad_report_quality > 0` 後同層）| **PASS** (新 3 gate 順序：state_changes_empty → bad_value_quality → real_fill_partial，全在既有 4 gate 之後同層) |
| 7 | 無 hardcoded `/home/ncyu/` `/Users/ncyu/` paths | **PASS** (`grep -nE '(/home/ncyu\|/Users/ncyu)' ...` 0 命中) |
| 8 | function 行數增 < 50 LOC（純 metric add，不改邏輯框架）| **PARTIAL** (`check_55_*` 本體增 ~30 LOC；`_complete_chain_counts` SQL 增 ~50 LOC； `_state_changes_count_24h` 新 helper ~14 LOC；module constants ~7 LOC；合計 ~100 LOC 略超 50；理由：必要的 SQL extension + state_changes 第二 helper —— 不可省。E2 review 確認是否接受) |

---

## 6. Diff stage 狀態（git diff --stat；不 commit）

```
 .../passive_wait_healthcheck/checks_agent_spine.py | 122 ++++++++++++++-
 helper_scripts/db/test_agent_spine_healthcheck.py  | 156 +++++++++++++++++++-
 2 files changed, 266 insertions(+), 12 deletions(-)
```

**未 commit**（per spec：等 E2 review + E4 regression PASS 後 PM 統一 commit + push；當前 working tree 還有平行 Rust FIX-1+FIX-2 + W1 panel_aggregator + W2 IMPL 等 wave WIP，PM holistic commit）。

---

## 7. Caveat / risk / E2 特別查的點

### Caveat A — Acceptance #8（function LOC 略超 50）
prompt 寫「function 行數增 < 50 LOC」；實際 module 增 ~112 LOC（含 helper / constant / SQL extension）。`check_55_*` 函數本體 + body 增 ~30 LOC（語意 gate）但 `_complete_chain_counts` SQL 內部增 ~50 LOC（不可省）。**請 E2 確認是否接受**——這是純 metric extension，無邏輯框架改動。

### Caveat B — Real-fill propagation 50% gate threshold（PA push back-ready）
PA `2026-05-10--w_c_caveat_fix_plan.md` §3.3 推導為 50%（24h trading.fills 86 / chains 174 ≈ 49.4%）；user prompt 默認假設為 90%。本 IMPL 採用 PA 50%（spec authority）。E2 確認 PA spec authority over prompt fallback。

### Caveat C — Real-fill query 用 `executed_by + details.fill_completion=true` 而非 trading.fills cross-table join
PA §2.2 Option α + Migration A 推薦：用既有 `executed_by` edge type + JSON details 標記，不需新 enum / V### migration。本 IMPL 採此設計（避免 spine writer 跨表 cross-table transaction，符合 Spine append-only event log 哲學）。但這條 query 依賴 Rust E1-W-C-FIX-2 真有寫 `details.fill_completion=true` 的 edge — 若 Rust IMPL 改用其他 edge_type 命名（例：新 `executed_by_filled`），則本 IMPL 需配合改 SQL。

**E2 必查**：Rust E1-W-C-FIX-2 IMPL DONE 後對齊 edge_type + details key 是否與本 SQL 一致。如不一致，本 IMPL 必同步改。

### Caveat D — `_state_changes_count_24h` 用獨立 query（不和 `_complete_chain_counts` 同 SQL）
PA §3.2 建議獨立 helper「避免 query 過長」；本 IMPL 接此設計。代價：多一次 PG round-trip（但 1ms 級，遠 < SLA）。不合併也有好處：state_changes 是 Caveat 1 而非 Caveat 2，語意分離方便 E5 後續優化（如 PA §3.5 後續門檻 ≥ 5×complete_chains 可改本 helper 不動主 query）。

### Caveat E — package `__init__.py` pre-existing breakage 用 isolation import 繞行
W1 panel_aggregator wave 預先在 `runner.py` 加 `from .checks_derived import check_panel_freshness`，但 `checks_derived.py` 對應函數尚未 land；package import 全鏈失敗（pre-existing not caused by my IMPL，git blame confirmed）。Test 改用 `importlib.util.spec_from_file_location()` 直接 load `checks_agent_spine.py` 避開 `__init__.py` — 這是**test SoT 防衛**，不應被隔壁 wave WIP 影響 unit test 健全。

**E2 確認**：isolation import 是否接受？或改要求 commit 等 W1 wave land 後再跑 test？建議接受（unit test 必須能 standalone PASS）。

### Risk F — 環境變數 cutoff env var 哨兵
新 `OPENCLAW_AGENT_SPINE_VALUE_QUALITY_CUTOFF_TS` 預設 `1970-01-01T00:00:00+00`（epoch）等同不過濾，這樣未設 env 時 PASS condition 仍能算到 historical row 不會 silently 略過。Operator 部署 Rust FIX-2 後設 deploy_ts ISO8601 字串才啟動實際過濾。**反模式警示**：如預設 `now()` 會讓所有歷史 row 被排除，metric 永遠 0，gate 失效。E2 review 必確認 default 哨兵語意。

---

## 8. 後續對齊（PA §5 並行序列圖）

| 階段 | 工件 | 狀態 |
|---|---|---|
| D+0 09:00-12:00 | E1-W-C-FIX-3 IMPL DONE | **完成（本報告）** |
| D+0 09:00-15:00 | E1-W-C-FIX-1+2 IMPL DONE（Rust）| 待平行 E1 sub-agent 確認 |
| D+0 14:00 | E2 code review + E4 regression | **PA 派發中** |
| D+0 17:00 | sign-off + deploy（restart_all --rebuild --keep-auth）| 待 |
| D+0 17:30 | post-deploy 短窗 verify（PA §4.3 對抗 SQL）| 待 |
| D+0 18:00 | QA re-audit + W-D dispatch | 待 |

---

## 9. 不確定之處（請 PA / E2 / operator 裁定）

1. **Acceptance #8 function LOC 50 cap**：實際增 ~112 LOC（含 SQL extension），略超原 50 限。是否接受？
2. **PA Option α 對 Rust E1-W-C-FIX-2 的隱性依賴**：本 IMPL SQL 依賴 Rust 寫 edge_type='executed_by' + details.fill_completion=true；Rust IMPL DONE 後必對齊驗證。如 Rust 改用新 enum，本 IMPL 必同步改 SQL。
3. **package `__init__.py` pre-existing breakage**：test 用 isolation import 繞行。E2 接受或要求等 W1 wave fix？

---

**Report path**: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w_c_fix_python_impl.md`

**E1 IMPLEMENTATION DONE: 待 E2 審查**
