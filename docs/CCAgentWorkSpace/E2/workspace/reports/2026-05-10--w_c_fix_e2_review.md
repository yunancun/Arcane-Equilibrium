# E2 Adversarial Code Review — W-C MAG-082 Caveat 1+2+3 Fix（Rust + Python 並行 IMPL）

**Date**: 2026-05-11
**Reviewer**: E2
**Scope**:
- E1-W-C-FIX-1+2 Rust 端 (`2026-05-11--w_c_fix_rust_impl.md`)：15 files / +877 LOC / 2757/2757 lib test PASS
- E1-W-C-FIX-3 Python 端 (`2026-05-10--w_c_fix_python_impl.md`)：2 files / +254 LOC / 14/14 pytest PASS
- 兩端 caveat C 跨語言 contract（`executed_by` edge + `details.fill_completion=true`）
- 上層 SoT：PA `2026-05-10--w_c_caveat_fix_plan.md` / QA `2026-05-10--w_c_signoff_audit.md` / governance `2026-05-08--w_c_lease_router_authorized.md`

---

## Executive Verdict

**APPROVE WITH CONDITIONS**

可派 E4 regression；但有 1 個 MEDIUM finding（C-A.2 report_transition object_id 語意）值得 operator/PM 決定要不要 round 2（語意層改進，不破 healthcheck gate），其餘 5 個 LOW finding 作為 advisory，無 BLOCKER 級對抗風險。

兩端 IMPL 整體質量高：
- 對抗審查 9 大向度（A.1-A.7 + B.1-B.5 + C）全結構通過
- 跨語言 fill_completion contract empirical 驗證對齊（Rust 寫 = Python SQL 讀，byte-equal）
- 0 觸碰 §四 5 hard gate / 2026-05-08 operator authorization Not Authorized 列表
- E1 自報數據與 E2 重跑一致（2757 PASS lib test / 14/14 pytest / Linux PG 22.54ms < 1s SLA）
- 跨平台 / 雙語注釋 / 文件大小 / except 吞異常 / SQL injection 全 clean

---

## A. Rust IMPL 對抗審查（A.1-A.7 全表）

### A.1 PA spec 對齊

| 點 | PA spec | IMPL 實際 | 結論 |
|---|---|---|---|
| Stage A 5 transitions 在 emit_entry_lineage 末尾 | 5 條 from_state=None → to_state=<initial> | 5 條 build_transitions[] forloop 寫入（runtime_shadow.rs:321-369）；object_type / to_state / trigger 完全對齊 PA §1.3 表 | ✓ PASS |
| Stage B 2 transitions 在 loop_exchange.rs fully_filled | execution_plan / execution_report 兩個 state change | emit_fill_completion_lineage 寫 2 transitions（runtime_shadow.rs:546-585）；plan: shadow_planned→shadow_executed；report: shadow_planned→shadow_filled；trigger=runtime_fill_confirmed | ✓ PASS 但 report_transition.object_id 用 filled_report_id（語意可議，見 C-A.2 finding） |
| partial fill 不寫 transition | by-design | emit_fill_completion_lineage 被 `if fully_filled` 包，外層 else 走 pending_sweep tighten path 不觸發；emit_fill_completion_lineage 內部 `filled_qty<=0` 雙重 guard | ✓ PASS（但缺 partial fill skip integration test，C-A.3） |
| Option α + Migration A：用既有 executed_by edge + details.fill_completion=true | 不新增 enum / migration | DecisionEdgeType::ExecutedBy 既有；details = `{"fill_completion": true}` JSON 標記；0 新 enum / 0 migration ✓ | ✓ PASS |
| emit_fill_completion_lineage 寫**新** ExecutionReport row | append-only event log | filled_report_id = stable_id("report", &[em, plan_id, "shadow_filled"])，與 stub 的 stable_id("report", &[em, plan_id, "shadow_planned"]) 字面不同 → UNIQUE INDEX 不撞 | ✓ PASS |
| Historical stub rows 不 backfill | Option α-a 推薦 | Rust 沒 INSERT/UPDATE historical row；Python `value_quality_cutoff_ts` 用 epoch 哨兵預設不過濾 + operator 設 deploy_ts 才啟動 cutoff | ✓ PASS |

### A.2 §四 硬邊界 + Operator authorization

| 項 | grep 結果 | 結論 |
|---|---|---|
| `live_execution_allowed` / `max_retries` / `OPENCLAW_ALLOW_MAINNET` / `live_reserved` / `api_key` / `api_secret` / `authorization.json` 新代碼觸碰 | `git diff HEAD | grep -E '^\+' | grep -E '<keywords>'` = 0 命中 | ✓ 0 觸碰 |
| `decision_lease_emitted` 仍是 `"shadow_bypass_lineage_only"` | 不動 lease 語意 | ✓ |
| Shadow mode runtime unchanged — paper engine 不寫 spine | emit_entry_lineage line 57 + emit_fill_completion_lineage line 445 都 `matches!(engine_mode, "demo" \| "live_demo")` filter | ✓ 兩處對齊；test `runtime_shadow_emit_entry_lineage_skips_transitions_in_paper` + `runtime_shadow_emit_fill_completion_lineage_skips_invalid_modes` paper case 雙驗 |
| 2026-05-08 operator authorization Not Authorized 列表（Mainnet / auth renew / executor unlock / strategy param change / scanner authority / MAG-083/084 sign-off / Stage 3/4 promotion）| 7 項全 cross-check | ✓ 0 觸犯 — 純 append shadow lineage row |
| 2026-05-08 operator authorization Allowed 列表（shadow spine lineage / bypass lease record / read-only healthcheck）| 3 項 cross-check | ✓ 本 fix 屬「補正 W-C 既允許 lineage write 完整性」授權範圍內 |

### A.3 Hot path / race / leakage / safety

| 項 | 結論 | 證據 |
|---|---|---|
| `try_send` 非阻塞 | ✓ | 7 處 `try_send` 全 mpsc 非阻塞，fail-soft warn drop（runtime_shadow.rs:367 + 539-540 + 561-565 + 583-587） |
| `transition_id` collision 防護 | ✓ | `SpineStateTransition::new` 內部以 `stable_id("transition", &[object_id, to_state, trigger, ts_ms])` 生成；test `runtime_shadow_build_transition_ids_are_distinct` 顯式驗 5 條 transition_id 全唯一 |
| mpsc channel pressure | ✓ | 5 build + 2 change = 7 msg / fully_filled fill；24h ~86 fill → ~600 msg/24h，遠低於 channel 容量 |
| 跨執行緒共享狀態 | ✓ | `agent_spine_tx` 是 `Option<&mpsc::Sender<AgentSpineMsg>>` borrowed reference；accessor `agent_spine_tx_ref()` 用 `pub(crate)` 限定 crate-internal，0 外洩 |
| `unsafe` 0 命中 | ✓ | `git diff HEAD | grep -E '^\+' | grep -E '\bunsafe\b'` = 0 |
| `unwrap()` / `expect()` production path | ✓ | grep 6 命中：5 個 test scope（不算）+ 1 個 production 是 `tx.expect("checked Some above")` line 458（前置 `if tx.is_none() return 0` guard，與既有 emit_entry_lineage line 63 byte-equal pattern） |
| `?` operator / `Result` 處理 | ✓ | serde 序列化失敗（line 503-512）`match` 顯式處理，`Err(err)` → warn + return 0，不 panic |

### A.4 caller wiring 真實接線

| 預期 | grep 命中 | 結論 |
|---|---|---|
| `grep -n 'AgentSpineMsg::StateTransition' rust/openclaw_engine/src/agent_spine/runtime_shadow.rs` ≥ 7 | 3 處 enum 構造，但 emit_entry_lineage 內 forloop 一處等效 5 條 + emit_fill_completion_lineage 2 條 inline = 7 transitions/fill | ✓ PASS（E1 Acceptance #3 自報 4 命中 `put_state_transition` 是對 trait method 計數，真實 emit 是經 `AgentSpineMsg::StateTransition(` enum；E1 自評說明清楚） |
| `grep -n 'emit_fill_completion_lineage' rust/openclaw_engine/src/event_consumer/loop_exchange.rs` ≥ 1 | 1 處 caller @ line 283 | ✓ PASS |
| `grep -n 'emit_fill_completion_lineage' rust/openclaw_engine/src/agent_spine/runtime_shadow.rs` ≥ 1 | 1 處 definition @ line 435 | ✓ PASS |
| partial fill 路徑不誤觸 emit_fill_completion_lineage | `if fully_filled` 區塊包；外層 `else if pending_sweep::tighten_postonly_entry_after_partial` 走 partial path | ✓ PASS（互斥靜態結構保證） |

### A.5 Test 覆蓋

| Test | E1 自報 PASS | E2 重跑 PASS | 結論 |
|---|---|---|---|
| `runtime_shadow_emit_entry_lineage_emits_5_build_state_transitions` | ✓ | ✓ | 5 build transitions（object_type / to_state / trigger 全對） |
| `runtime_shadow_emit_entry_lineage_skips_transitions_in_paper` | ✓ | ✓ | paper engine_mode 0 emit |
| `runtime_shadow_emit_fill_completion_lineage_writes_real_fill_chain` | ✓ | ✓ | 1 envelope + 1 edge + 2 transitions = 4 accepted |
| `runtime_shadow_emit_fill_completion_lineage_skips_invalid_modes` | ✓ | ✓ | paper / disabled / tx=None / qty<=0 / NaN 5 case |
| `runtime_shadow_build_transition_ids_are_distinct` | ✓ | ✓ | 5 transition_id 全唯一（hash collision 防護） |
| 既有 `runtime_shadow_lineage_emits_complete_demo_chain` accepted=10→15 | ✓ | ✓ | 升級正確（5 obj + 4 edge + 1 idem + 5 transition = 15） |
| cargo test --lib --release 全套 | 2757 PASS | **E2 重跑：2757 passed; 0 failed; 0 ignored** | ✓ 0 regression |
| event_consumer subset | - | **E2 重跑：156 passed; 0 failed** | ✓ |
| tick_pipeline subset | - | **E2 重跑：166 passed; 0 failed** | ✓ |

PA §4.2 期望 8 test：Rust 5 + Python 3 = 8 ✓ 數量達成；但 PA §4.2 列的 `loop_exchange::handle_exchange_event_emits_fill_completion_on_fully_filled` 和 `does_not_emit_on_partial_fill` 2 個 integration test 沒寫（C-A.3 finding，LOW）。

### A.6 跨平台 + 注釋規範

| 項 | 結論 |
|---|---|
| `grep -E '(/home/ncyu|/Users/[^/]+)' <Rust diff>` 新增 LOC | 0 命中 ✓ |
| 注釋默認中文（CLAUDE.md §七 2026-05-05）| 新增 ~175 LOC 注釋全中文 ✓；既有英文 MODULE_NOTE 未動（governance 規則「修改既有 block 才移除英文」）|
| 800/2000 行限制 | runtime_shadow.rs 657 < 800 ✓；tests.rs 1063 警告 (≥800) 但 < 2000 ✓；step_4_5_dispatch.rs 1557 警告 (≥800) 但 < 2000 ✓（pre-existing baseline，本 PR +56）；commands.rs 1365 / mod.rs 1188 同（pre-existing） |

### A.7 sibling sub-agent isolation

| 項 | 結論 |
|---|---|
| Rust E1 自報「不接觸 W1/W2/Python WIP」| ✓ Rust diff 涉 15 files 全在 `rust/openclaw_engine/{agent_spine,event_consumer,tick_pipeline}/*`；無 panel_aggregator / main.rs / ipc_server/runtime_init 等 sibling wave 範圍 |
| Python E1 改的檔不被 Rust 改 | ✓ `checks_agent_spine.py` 和 `test_agent_spine_healthcheck.py` 純 Python E1 範圍 |
| `ipc_server/slots.rs` modified | git status 顯示 `slots.rs` modified — 經 grep 確認屬 **W2 sub-task 4 E1-δ (BtcLeadLagPanelSlot)**，**不在** W-C IMPL 範圍。PM holistic commit 時會打包；E2 確認 build 仍綠（cargo build --release 0 error），不破 build |

---

## B. Python IMPL 對抗審查（B.1-B.5 全表）

### B.1 PA spec 對齊

| 點 | PA spec | IMPL 實際 | 結論 |
|---|---|---|---|
| `bad_report_value_quality` 計數 | filter cutoff 後 + (filled_qty<=0 或 liquidity_role 非 maker/taker) | line 203-209 SQL 計數對齊；用 `count(DISTINCT filled_report.object_id)` | ✓ PASS |
| `_state_changes_count_24h` 獨立 helper | PA §3.2「避免 query 過長」推薦獨立 | line 261-279 新獨立函數 + check_55_* line 382 額外 call | ✓ PASS |
| 50% real-fill ratio gate | PA §3.3 推導 49.4%（86/174）→ 50% | line 41 `_REAL_FILL_PARTIAL_RATIO = 0.5`；line 411 `complete_chains * 0.5` | ✓ PASS（採 PA spec，不採 prompt 默認 90%） |
| `OPENCLAW_AGENT_SPINE_VALUE_QUALITY_CUTOFF_TS` 預設 epoch | 哨兵不過濾 | line 36 `_VALUE_QUALITY_CUTOFF_DEFAULT = "1970-01-01T00:00:00+00"` + line 68-72 helper 讀取 + fallback | ✓ PASS |
| message format 加 3 new field | PA §3.4 | line 393-402 detail message append 3 新 field + cutoff timestamp | ✓ PASS |

### B.2 Caveat C cross-language contract（empirical 驗證，最關鍵）

| 項 | Rust 寫 | Python SQL 讀 | byte-equal |
|---|---|---|---|
| edge_type 序列化 | `DecisionEdgeType::ExecutedBy` → `"executed_by"`（events.rs:58 enum impl） | `edge_type='executed_by'`（checks_agent_spine.py:233） | ✓ identical |
| details JSON key | `"fill_completion": true`（runtime_shadow.rs:527,547,572 三處） | `(details->>'fill_completion')::boolean IS TRUE`（checks_agent_spine.py:234） | ✓ snake_case identical |
| 值類型 | `serde_json::Value::Bool(true)` | `::boolean IS TRUE` | ✓ JSON boolean → PG boolean 對齊 |
| Edge 方向 | `from_object_id = order_plan_id` / `to_object_id = filled_report_id`（runtime_shadow.rs:518-521） | `filled_report_edge.from_object_id = c.order_plan_id` / `filled_report.object_id = filled_report_edge.to_object_id`（checks_agent_spine.py:232-238） | ✓ |
| object_type | `DecisionObjectType::ExecutionReport` → `"execution_report"` | `filled_report.object_type = 'execution_report'`（checks_agent_spine.py:237） | ✓ |
| engine_mode constraint | `input.engine_mode` 必 `'demo' \| 'live_demo'`（runtime_shadow.rs:445 filter） | `filled_report.engine_mode = c.engine_mode` JOIN（checks_agent_spine.py:238）；engine_mode 來自 ANY(modes) param | ✓ 不衝突 |

**Caveat C 跨語言契約 empirical 驗證 PASS** — Rust write & Python SQL read byte-equal aligned。

### B.3 SQL safety

| 項 | 結論 |
|---|---|
| Parameterized query | ✓ 全用 `%s` placeholders（line 184/250-258/275-283 三處 cur.execute），無 string concat |
| `(payload->>'filled_qty')::numeric` 對 NULL payload | ✓ `payload->>'filled_qty'` 不存在 key 返 NULL → `NULL::numeric` 是 NULL → `NULL <= 0` 是 NULL → FILTER 子句不為 TRUE → 不計（fail-soft 默認） |
| JOIN 結果不爆量 | ✓ 174 chains × 1-2 edges per chain × 174 stub reports = manageable；EXPLAIN ANALYZE 14ms < 1s SLA |
| Linux PG empirical | ✓ 22.54ms end-to-end < 1s（E1 自報 + 含 8 SQL round-trip） |

### B.4 test coverage

| 項 | 結論 |
|---|---|
| 3 new test mock 真實 behavior | ✓ 用 5-tuple→7-tuple fixture + state_changes (n,) fetchone 對齊新 SQL return shape；test_state_changes_empty_blocks_after_pass_path / test_bad_report_value_quality_blocks_with_cutoff / test_real_fill_propagation_partial_warns 三 case 各驗對應 gate |
| 既有 11 test 升級後 PASS | ✓ test_enabled_complete_lineage_passes / test_sql_contract_is_read_only fixture 從 5-tuple 升 7-tuple 並加 state_changes mock；assertion 加 3 新 field 驗 |
| `test_sql_contract_is_read_only` 不誤加 INSERT/UPDATE/DELETE | ✓ line 311-314 仍 `assertNotIn("INSERT ")` / `assertNotIn("UPDATE ")` / `assertNotIn("DELETE ")`；line 295-296 加 2 新 grep 驗 `agent.decision_state_changes` + `fill_completion` 在 SQL 內 |
| isolation import 不掩蓋真 import bug | ✓ E2 重跑 `python3 -c "from helper_scripts.db.passive_wait_healthcheck import runner"` 確認 pre-existing `ImportError: cannot import name 'check_panel_freshness'` 真實存在（W1 panel_aggregator wave WIP 留下）；isolation import 是合理 workaround，不掩蓋本 IMPL bug |
| 14/14 pytest PASS | ✓ E2 重跑 `pytest -v` 全 PASS 0.02s |

### B.5 注釋規範 + 跨平台

| 項 | 結論 |
|---|---|
| 新增 ~38 LOC 注釋全中文 | ✓ E2 grep `^[[:space:]]*#[[:space:]]*[A-Z]` 在新加區塊 0 命中純英文 |
| hardcoded user path | ✓ 0 命中 |

---

## C. Findings 列表

| # | 嚴重性 | 位置 | 描述 | 建議修法 |
|---|---|---|---|---|
| C-A.1 | LOW | `runtime_shadow.rs:69,72,77` + `step_4_5_dispatch.rs:614-642` | `stable_id` 計算字面複製（同算式跑兩次）。E1 自報已標 C-1 caveat。當前字面對齊 100%；風險是未來改動可能 drift | P3：抽 helper `fn compute_spine_ids(em, signal_id, verdict_id) -> (decision_id, plan_id, stub_report_id)` 共用，消除字面複製 |
| **C-A.2** | **MEDIUM** | `runtime_shadow.rs:566-585` | `report_transition.object_id = filled_report_id`（新建 row）而非 stub_report_id；from_state=`shadow_planned` 對「新建 row」而言語意不嚴格（filled_report 從未經過 shadow_planned，它是新建一條 shadow_filled row）；E1 自己已注釋承認此 design choice。**不破** [55] healthcheck gate（state_changes_24h 只算 count(*)），但對 MAG-083 reviewer 解讀「per-object SM lifecycle」可能混淆 | **建議改 report_transition 的 object_id 為 stub_report_id**（語意：「stub report 對應的狀態變了 shadow_planned → shadow_filled」更貼近 SM 語意）；或保留現設計但在 reviewer brief 中明寫該語意；operator/PM 裁定接受 design choice 還是 round 2 |
| C-A.3 | LOW | `tests.rs` 缺 `loop_exchange::handle_exchange_event_emits_fill_completion_on_fully_filled` + `does_not_emit_on_partial_fill` 2 integration test | PA §4.2 期望 8 test，IMPL 給 5 test；Rust 端 integration test 用 mock pipeline 成本高，靜態代碼結構 `if fully_filled { emit_fill_completion_lineage } else if pending_sweep::tighten ... }` 保證互斥 | P3：補 integration test，或在 reviewer brief 內明確聲明「靜態互斥+雙 guard 雙重保險」 |
| C-A.4 | LOW | `runtime_shadow.rs:470` | `fill_latency_ms: input.fill_latency_ms.map(\|ms\| ms as f64)` u64→f64 SAFETY 注釋未明寫範圍守則 | P3：注釋升級寫明「u64 ms ≤ 2^53 mantissa lossless 範圍」 |
| C-A.5 | LOW | `commands.rs` 1365 / `mod.rs` 1188 / `step_4_5_dispatch.rs` 1557 三檔已 ≥ 800 警告線 | CLAUDE.md §九「800 行警告 + E2 必須標記」；pre-existing baseline > 800，本 PR 增量 +56/+17/+17 LOC | Advisory：E2 標 ⚠️ 但按 pre-existing baseline exception clause 容忍，不阻 sign-off |
| C-B.1 | LOW | `test_agent_spine_healthcheck.py:1-43` | `isolation import` workaround 繞 `__init__.py` ImportError — workaround 合理，但長期建議 W1 wave land 後撤回，否則 test 漸偏離 production import chain | Advisory：W1 panel_aggregator wave land 後撤回 isolation import；同 PR 不阻 sign-off |
| C-B.2 | LOW | `checks_agent_spine.py:8` function LOC 略超 50 | E1 自評 Acceptance #8 PARTIAL（增 ~112 LOC > 50 prompt 默認）；理由：必要的 SQL extension + state_changes 第二 helper | Accept：PA §3 spec 本就要求 SQL 加 2 column + 2 LEFT JOIN，純 metric extension 邏輯框架未改；E2 接受該 caveat |

---

## D. 對抗反問 + 答案

| Q | 答 |
|---|---|
| 你說「2757/2757 lib test PASS」— 真實跑了嗎？ | E2 在 Mac 重跑 `cargo test --lib --release -p openclaw_engine`：2757 passed; 0 failed; 0 ignored. confirmed 100% 對齊 E1 自報。 |
| 你說「14/14 pytest PASS」— 真實跑了嗎？ | E2 在 Mac 重跑 `pytest -v helper_scripts/db/test_agent_spine_healthcheck.py`：14 passed in 0.02s. confirmed 100% 對齊 E1 自報。 |
| 你說「無 unsafe / unwrap」— grep 結果？ | git diff HEAD 新增 LOC grep `unsafe` = 0 命中；`unwrap()` 5 命中全在 test scope；`expect()` 1 命中 production 是 `tx.expect("checked Some above")` line 458，前置 `if tx.is_none() return 0` guard，與既有 emit_entry_lineage line 63 byte-equal pattern。 |
| 你說「Caveat C 跨語言對齊」— empirical 驗證？ | Rust events.rs:58 `ExecutedBy => "executed_by"` byte-equal Python SQL line 233 `edge_type='executed_by'`；Rust 3 處 `"fill_completion": true` JSON 寫入 byte-equal Python SQL line 234 `(details->>'fill_completion')::boolean IS TRUE`。 |
| 你說「engine_mode 過濾」— two-side 對齊？ | emit_entry_lineage line 57 `matches!(input.engine_mode, "demo" \| "live_demo")` + emit_fill_completion_lineage line 445 byte-equal 同 filter。Test `runtime_shadow_emit_fill_completion_lineage_skips_invalid_modes` paper case 顯式驗 r=0 + rx.try_recv().is_err()。 |
| 你說「stub_report_id != filled_report_id 字面唯一」— hash collision 風險？ | stub: `stable_id("report", &[em, plan_id, "shadow_planned"])`；filled: `stable_id("report", &[em, plan_id, "shadow_filled"])`。第三個 input 不同，SHA-256 based hash 必不同。idempotency_key formatter line 245-248 嵌入 execution_report_id，UNIQUE INDEX (object_type, idempotency_key) 不撞。 |
| 你說「step_4_5_dispatch.rs 重算 stable_id 對齊 runtime_shadow.rs」— 字面驗證？ | runtime_shadow.rs:72-80 三條 stable_id 算式：`["decision",[em,signal_id]]` / `["plan",[em,decision_id,verdict_id]]` / `["report",[em,plan_id,"shadow_planned"]]`；step_4_5_dispatch.rs:619-642 三條同算式 byte-equal。verdict_id 在 step_4_5_dispatch 用 `verdict_id_for_dispatch = make_verdict_id(em, symbol, ts_ms)` 計算後**同一 String 值**注入 emit_entry_lineage 的 input.verdict_id，無計算差。 |
| 你說「sibling wave isolation」— git status 為何有 slots.rs？ | `ipc_server/slots.rs` modified 屬 W2 sub-task 4 E1-δ BtcLeadLagPanelSlot IMPL（grep diff 顯示），不在 W-C 範圍；本 IMPL 不接觸。PM holistic commit 時打包；cargo build --release 0 error 不破 build。 |
| 你說「§四 0 觸碰」— 7 項 grep？ | `live_execution_allowed` / `max_retries` / `OPENCLAW_ALLOW_MAINNET` / `live_reserved` / `api_key` / `api_secret` / `authorization.json` 在 git diff 新增 LOC 全 0 命中。 |
| 你說「Operator authorization Not Authorized 列表 0 觸犯」— 7 項 cross-check？ | (1) No true Mainnet：本 fix 不觸 OPENCLAW_ALLOW_MAINNET (2) No live auth renew：不寫 authorization.json (3) No Executor unlock：純 append spine row 不下單 (4) No strategy/risk param change：不動 risk_config / strategy_params (5) No scanner authority：不動 scanner_config.toml (6) No MAG-083/084 sign-off：不在 PR 範圍 (7) No Stage 3/4 promotion：不動 SM-04 ladder。 |
| 你說「report_transition object_id 設計正確」？ | **不完全**。E1 IMPL 用 filled_report_id（新建 row），語意是「該 plan 對應的 report 狀態變了」但執行對象是新 row；嚴格 SM 語意應對 stub_report_id 寫 transition（既有 row state 真變了）。標 MEDIUM C-A.2，operator/PM 裁定。 |
| 你說「partial fill 不誤觸 emit_fill_completion_lineage」— grep + integration test？ | `if fully_filled { ... }` 靜態包；emit_fill_completion_lineage 內 `filled_qty<=0 \|\| !is_finite` 雙重 guard；test `runtime_shadow_emit_fill_completion_lineage_skips_invalid_modes` 顯式 qty=0.0 + NaN case 驗 r=0。**缺 loop_exchange 端 integration test**（C-A.3 LOW），但靜態結構保證互斥。 |

---

## E. Conditions（APPROVE WITH CONDITIONS）

無 BLOCKER 級 condition。建議 operator/PM 對 **C-A.2 MEDIUM** 做以下 1 選 1 裁定：

**選項 A（推薦，operator 1 分鐘決定）**：接受當前 design choice
- 在 reviewer brief 內明寫「report_transition 用 filled_report_id 表示『該 plan 對應的 report 狀態變了』」設計語意
- W-D MAG-083 audit pack template 預設章節說明
- 風險：MAG-083 reviewer 可能仍困惑；但 [55] healthcheck gate 不破

**選項 B（小 round 2 修法，1-2 hr E1 工作）**：改 report_transition.object_id 為 stub_report_id
- 修改 runtime_shadow.rs line 568 `filled_report_id` → `input.stub_report_id.to_string()`
- 改 test `runtime_shadow_emit_fill_completion_lineage_writes_real_fill_chain` 期望 transition.object_id == stub_report_id（而非 filled_report_id）
- 風險：低；純語意層改進；report envelope object_id 不變

**E2 推薦 A**（不阻 deploy；reviewer brief 章節即可化解）。但 operator 若想嚴格 SM 語意，B 可接受小延誤。

---

## F. Direct fix applied

無。E2 對抗審查只發現 1 MEDIUM 級語意層 finding 待 operator 裁定（非業務邏輯錯誤），其餘全 LOW advisory。不執行直接修。

---

## G. Issues returned to E1

無。本輪 verdict APPROVE WITH CONDITIONS，E1 不需要再動 code（除非 operator 選 C-A.2 選項 B）。

---

## H. 最大的 1 個 concern

**C-A.2：`report_transition.object_id = filled_report_id` 語意嚴格性**

當前 IMPL：
```rust
let report_transition = SpineStateTransition::new(
    input.ts_ms,
    filled_report_id,                 // 新建 row 的 id
    DecisionObjectType::ExecutionReport,
    Some("shadow_planned".to_string()),  // 但這 row 從未經過 shadow_planned
    "shadow_filled",
    ...
);
```

問題：filled_report 是**新建** row，from_state=shadow_planned 對「該 row 自身」而言不成立（新 row 沒有「之前狀態」）。語意嚴格層面應是 **stub_report_id** 的 transition（stub row 確實從 shadow_planned 變到 shadow_filled — 但這在 append-only event log 哲學下又跟 Option α-A「新 row 不改舊 row」對著幹）。

對 W-D MAG-083 reviewer 的影響：reviewer 解讀「per-object SM lifecycle」時可能看到 filled_report.object_id 對應 transition 但 from_state=shadow_planned，會問「該 object 真的經過 shadow_planned 嗎？」答：沒有，是新建。

對 [55] healthcheck 的影響：state_changes_24h 只算 count(*)，不檢查 object_id ↔ object_type 一致性 → 不破 gate。

是否值得 round 2：operator/PM 1 分鐘決策。option A（接受 + reviewer brief 說明）或 option B（改 object_id = stub_report_id，1-2 hr E1 修）。

---

## Cross-References

- PA 方案：`docs/CCAgentWorkSpace/PA/2026-05-10--w_c_caveat_fix_plan.md`
- QA caveat audit：`docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-10--w_c_signoff_audit.md`
- Operator authorization：`docs/governance_dev/2026-05-08--w_c_lease_router_authorized.md`
- E1 Rust IMPL：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w_c_fix_rust_impl.md`
- E1 Python IMPL：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w_c_fix_python_impl.md`
- V064 schema：`sql/migrations/V064__agent_spine_decision_store.sql`
- CLAUDE.md §四 / §七 / §八 / §九

---

**E2 REVIEW DONE: APPROVE WITH CONDITIONS · report path: srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-10--w_c_fix_e2_review.md**
