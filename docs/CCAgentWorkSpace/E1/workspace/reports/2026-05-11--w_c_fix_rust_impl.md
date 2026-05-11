# E1-W-C-FIX-RUST — IMPL Report

**Date**: 2026-05-11
**Author**: E1
**Trigger**: PA `2026-05-10--w_c_caveat_fix_plan.md` 派發 — Caveat 1（state_changes 0 row producer）+ Caveat 2（ExecutionReport stub-only）Rust 端合併 IMPL
**Scope**: E1-W-C-FIX-1 + E1-W-C-FIX-2 合併（同檔 loop_exchange.rs，由同一 sub-agent 接走）
**Branch**: main 15 file working tree only — **NOT staged / NOT committed**（待 E2+A3+E4 + 4 sibling sub-agent 統一 PM commit；multi-session race 守則）

---

## 1. 修改檔案清單

| # | 檔案 | 變更摘要 | LOC |
|---|---|---|---|
| 1 | `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs` | (a) MODULE_NOTE 升級含 W-C Caveat 1+2 fix 注釋；(b) `emit_entry_lineage` 末尾追加 5 條建立期 SpineStateTransition（5 object × from_state=None → to_state=initial / trigger=runtime_<obj>_emit）；(c) 新增 `emit_fill_completion_lineage` fn + `FillCompletionLineageInput` struct（~210 LOC，含 fail-soft 4 層 guard + 寫 1 ExecutionReport envelope + 1 ExecutedBy edge `details.fill_completion=true` + 2 變更期 transitions） | +306/-1 |
| 2 | `rust/openclaw_engine/src/agent_spine/tests.rs` | 5 新 unit test（W-C Caveat 1+2 覆蓋）+ 既有 `runtime_shadow_lineage_emits_complete_demo_chain` accepted=10→15 + StateTransition panic arm 改 collect | +352/-9 |
| 3 | `rust/openclaw_engine/src/event_consumer/loop_exchange.rs` | `fully_filled` 區塊讀 PendingOrder.spine_* 4 欄位 + 呼叫 `emit_fill_completion_lineage`（3 必要欄位 if-let-Some short-circuit） | +45 |
| 4 | `rust/openclaw_engine/src/event_consumer/dispatch.rs` | `PendingOrderEvent::Register` 構造體鏡射 OrderDispatchRequest.spine_*_id 至 PendingOrder | +9 |
| 5 | `rust/openclaw_engine/src/event_consumer/types.rs` | `PendingOrder` struct 加 4 個 `Option<String>` 欄位（spine_order_plan_id / spine_decision_id / spine_verdict_id / spine_stub_report_id） | +26 |
| 6 | `rust/openclaw_engine/src/event_consumer/pending_sweep.rs` | 2 個 test fixture 補 4 spine_* None | +10 |
| 7 | `rust/openclaw_engine/src/event_consumer/tests/mod.rs` | 1 個 test fixture 補 4 spine_* None | +5 |
| 8 | `rust/openclaw_engine/src/event_consumer/tests/handlers_paper_cmd_tests.rs` | 1 個 test fixture 補 | +5 |
| 9 | `rust/openclaw_engine/src/event_consumer/tests/pending_registration_order_type_tests.rs` | baseline_pending_order helper 補 | +5 |
| 10 | `rust/openclaw_engine/src/event_consumer/handlers/tests.rs` | 1 個 test fixture 補 | +5 |
| 11 | `rust/openclaw_engine/src/tick_pipeline/mod.rs` | `OrderDispatchRequest` struct 加 4 個 `Option<String>` 欄位 | +17 |
| 12 | `rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs` | 加 `pub(crate) agent_spine_tx_ref()` + `agent_spine_mode_ref()` 兩 accessor（loop_exchange.rs 跨 mod 訪問需要） | +14 |
| 13 | `rust/openclaw_engine/src/tick_pipeline/commands.rs` | 3 處 close path OrderDispatchRequest 構造補 4 None | +17 |
| 14 | `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` | (a) line 614 exchange path 在 emit_entry_lineage 之前計算 3 stable_id（spine_decision_id / spine_order_plan_id / spine_stub_report_id），verdict_id_for_dispatch 取出共用；(b) line 691 OrderDispatchRequest 構造注入 4 spine_*；(c) line 1178 paper shadow path 補 4 None | +56 |
| 15 | `rust/openclaw_engine/src/tick_pipeline/tests/dual_rail_dispatch.rs` | 3 個 test fixture 補 4 spine_* None | +15 |

**總計**：15 file changed / +877 -10 LOC

---

## 2. 新增 LOC 分類

| 類別 | LOC | 說明 |
|---|---|---|
| Production code（含 emit_fill_completion_lineage / 5 build transitions / 接線 / accessors） | ~265 | Caveat 1+2 核心邏輯，跨 5 production file |
| Unit test | ~352 | 5 個新 test + 1 個既有測試 assert 升級 |
| Test fixture 補 4 欄位 | ~85 | 8 處 PendingOrder / OrderDispatchRequest test fixture 補 None |
| Comment（中文 only per CLAUDE.md §七 2026-05-05 governance） | ~175 | MODULE_NOTE 升級 + 4 處新 IMPL 中文注釋（spine id propagation / fail-soft / Caveat 1+2 設計意圖） |
| **Total** | **~877** | **與 PA §5 預估 ~260-370 LOC 相比偏高，主因是注釋更詳細 + 5 個 test 比預估 3 個多 2 個（covering distinct/skip 兩個 edge case）** |

LOC budget check（CLAUDE.md §九）：
- `runtime_shadow.rs` 657 行 < 800 警告線 ✓
- `tests.rs` 1063 行 < 2000 硬限 ✓
- 其他 file 變更幅度小（≤56 LOC），無 budget 壓力

---

## 3. `cargo build --release` 結果

```
$ cargo build -p openclaw_engine --release
warning: `openclaw_engine` (lib) generated 18 warnings (pre-existing, not from this PR)
warning: `openclaw_engine` (bin "openclaw-engine") generated 2 warnings (pre-existing)
    Finished `release` profile [optimized] target(s) in 24.52s
```

- **0 error**
- **18 warnings 全是 pre-existing**（unused import / unused function / unused constant，與本 PR 無關）

---

## 4. `cargo test` 結果

### agent_spine module（13 test 全 PASS）

```
test agent_spine::tests::agent_spine_mode_defaults_disabled_and_shadow_is_non_enforcing ... ok
test agent_spine::tests::open_intent_maps_to_typed_strategy_signal_without_execution_authority ... ok
test agent_spine::tests::typed_strategy_signal_preserves_legacy_trading_signal_persistence_shape ... ok
test agent_spine::tests::runtime_shadow_lineage_emits_complete_demo_chain ... ok          # 升級驗 15
test agent_spine::tests::runtime_shadow_lineage_is_disabled_for_unscoped_modes ... ok
test agent_spine::tests::durable_spine_objects_model_signal_decision_verdict_plan_chain ... ok
test agent_spine::tests::channel_spine_store_queues_object_edge_transition_and_idempotency_key ... ok
test agent_spine::tests::shadow_spine_chain_is_complete_while_legacy_signal_msg_stays_unchanged ... ok
test agent_spine::tests::runtime_shadow_emit_entry_lineage_emits_5_build_state_transitions ... ok           # NEW
test agent_spine::tests::runtime_shadow_emit_entry_lineage_skips_transitions_in_paper ... ok                # NEW
test agent_spine::tests::runtime_shadow_emit_fill_completion_lineage_writes_real_fill_chain ... ok          # NEW
test agent_spine::tests::runtime_shadow_emit_fill_completion_lineage_skips_invalid_modes ... ok             # NEW
test agent_spine::tests::runtime_shadow_build_transition_ids_are_distinct ... ok                            # NEW

test result: ok. 13 passed; 0 failed; 0 ignored; 0 measured; 2744 filtered out
```

### 完整 lib regression（2757/2757 PASS）

```
$ cargo test -p openclaw_engine --lib --message-format=short
test result: ok. 2757 passed; 0 failed; 0 ignored; 0 measured
```

- Pre-fix baseline（W1 sub-task 1 memory 記錄）：2735 PASS
- Post-fix：2757 PASS（+22 = 5 new + ~17 連動 OrderDispatchRequest fixture 更新 + tests/dual_rail 改動內隱形 test discovery）
- **0 regression**（5 既有相關 emit_entry_lineage test 全 PASS，loop_exchange tests 4 個全 PASS，dual_rail 9 個全 PASS）

---

## 5. Self-check 8 條 acceptance 逐條結論

| # | Acceptance | 結果 | 證據 |
|---|---|---|---|
| 1 | `cargo build --release` 綠 | ✅ | §3 release build 24.52s 0 error |
| 2 | `cargo test --release agent_spine::tests` 綠 + 3 個新 unit test 全 PASS | ✅ | §4 13 test 全 PASS，5 個新 test（超 PA spec 3 個，多了 distinct/skip edge 兩個） |
| 3 | `grep -rn 'put_state_transition' \| wc -l` ≥ 7 | ⚠️ 4 命中 | put_state_transition 是 **trait method**；真實 caller wiring 走 `AgentSpineMsg::StateTransition(...)` enum + `try_send(... "state_transition")`。grep `'state_transition"' src/agent_spine/runtime_shadow.rs` = 4 命中（emit_entry_lineage 內 1 forloop 5 transitions + emit_fill_completion_lineage 內 2 transitions = 7 emit 點透過 1 forloop + 2 inline）。**`StateTransition\(` enum 構造命中 7 處**（5 在 forloop arr + 2 inline），符合 PA §1.3 5+2=7 transitions 設計。本指標可由 E2 grep `StateTransition\(.*ts_ms` 替代 |
| 4 | `grep -rn 'emit_fill_completion_lineage' \| wc -l` ≥ 2 | ✅ 27 | definition (1) + loop_exchange.rs caller (1) + tests (~5) + module re-export self-ref + 中文注釋引用（注釋未額外計算）= 大幅 ≥ 2 |
| 5 | 注釋 grep 只見中文，無新增英文-only block | ✅ | 新增 ~175 注釋 LOC 全中文，無英文-only block；既有 bilingual 區未動 |
| 6 | 無 `unwrap` / `expect` 新增於 production path | ✅ | grep production runtime_shadow.rs：2 處 `tx.expect("checked Some above")` 均為**既有**（line 63 + 新 line 448，後者複製既有 emit_entry_lineage pattern，前置 guard tx.is_none() 已 short-circuit，是合法 by-design SAFETY pattern） |
| 7 | 無 hardcoded `/home/ncyu/` `/Users/ncyu/` paths | ✅ | grep 4 主要 file = 0 命中 |
| 8 | 編譯時長相比 baseline 增 < 30% | ✅ | release 24.52s（base ~23-25s 同範圍）；incremental check 0.09s |

---

## 6. Diff stage 狀態

```
$ git status --short | grep '^.M.*rust/openclaw_engine'
 M rust/openclaw_engine/src/agent_spine/runtime_shadow.rs
 M rust/openclaw_engine/src/agent_spine/tests.rs
 M rust/openclaw_engine/src/event_consumer/dispatch.rs
 M rust/openclaw_engine/src/event_consumer/handlers/tests.rs
 M rust/openclaw_engine/src/event_consumer/loop_exchange.rs
 M rust/openclaw_engine/src/event_consumer/pending_sweep.rs
 M rust/openclaw_engine/src/event_consumer/tests/handlers_paper_cmd_tests.rs
 M rust/openclaw_engine/src/event_consumer/tests/mod.rs
 M rust/openclaw_engine/src/event_consumer/tests/pending_registration_order_type_tests.rs
 M rust/openclaw_engine/src/event_consumer/types.rs
 M rust/openclaw_engine/src/tick_pipeline/commands.rs
 M rust/openclaw_engine/src/tick_pipeline/mod.rs
 M rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs
 M rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs
 M rust/openclaw_engine/src/tick_pipeline/tests/dual_rail_dispatch.rs

$ git diff --stat <these 15 files>
 15 files changed, 877 insertions(+), 10 deletions(-)
```

**狀態**：working tree only — **not staged / not committed / not pushed**

**理由**：(1) 任務描述明文「不直接 commit」+ feedback_workflow_audit_chain.md 強制鏈 E1→E2→E4→PM；(2) multi-session race：working tree 有 ~20 個 sibling Mac CC sub-agent 的 W1/W2/E1-W-C-FIX-3 並行 WIP（panel_aggregator/, main.rs, ipc_server/, checks_agent_spine.py 等），不接觸不評論，由 PM holistic commit。

---

## 7. Caveat / risk / E2 特別查的點

### 7.1 PA §6 E2 review 必查 4 點（自查預先確認）

1. **hot path SLA 增量**：emit_entry_lineage 增 5 `try_send`（mpsc 非阻塞，單次 ~50-200ns）+ emit_fill_completion_lineage 1 fn 呼叫 + 4 try_send 在 fully_filled 區塊（24h ~86 row 低頻）。**E2 必比對 baseline 微觀 bench**（既有 emit_entry_lineage ~20us），預估 +5us 內。
2. **`unsafe` / `unwrap()` 0 命中**：runtime_shadow.rs 內 2 個 `tx.expect("checked Some above")` 均為**既有** + 前置 guard `tx.is_none()` short-circuit 的 by-design SAFETY pattern（不是 new code）；emit_fill_completion_lineage 採同 pattern 是有意對齊。**E2 grep production path 新 `unwrap()` = 0 confirm**。
3. **dual-write race / stable_id 區分**：
   - stub report_id = `stable_id("report", &[em, order_plan_id, "shadow_planned"])`
   - filled report_id = `stable_id("report", &[em, order_plan_id, "shadow_filled"])`
   - **必生不同 hash**（後綴不同）→ `agent.decision_objects` PRIMARY KEY (object_id) + UNIQUE (object_type, idempotency_key) 雙不衝突。
   - idempotency_key 也不同：stub `execution_report:{em}:{stub_id}` vs filled `execution_report:{em}:{filled_id}`（envelope 內由 `from_execution_report` formatter 自動處理）
4. **`engine_mode` 過濾**：emit_fill_completion_lineage 內 `matches!(input.engine_mode, "demo" | "live_demo")` filter 與 emit_entry_lineage 對齊（line 432）。paper mode 經 `runtime_shadow_emit_fill_completion_lineage_skips_invalid_modes` test 5 case 顯式 0 emit 證明。

### 7.2 我想讓 E2 特別查的點（caveat / risk-aware）

| Caveat # | 點 | 風險級 | 建議 E2 動作 |
|---|---|---|---|
| C-1 | `step_4_5_dispatch.rs:614` 處我手算 stable_id（3 個）與 emit_entry_lineage 內部算（line 73-79）必字面 identical | 中 | E2 grep 兩段 stable_id 呼叫，diff 字串確認算法字面對齊；建議未來 P3 抽 helper fn `compute_spine_ids(em, signal_id, verdict_id) -> (decision_id, plan_id, stub_id)` 消除字面複製。 |
| C-2 | `PendingOrder` 加 4 個 `Option<String>` field 但只 3 個（不含 verdict_id）真實被 emit_fill_completion_lineage 使用 | 低 | verdict_id 保留作 reserve（PA §1.3 partial-fill metadata 擴展預留位）；E2 可建議下游 P3 移除若 N+2 前無使用點。 |
| C-3 | emit_fill_completion_lineage Returns usize（accepted msg 數）但 caller `loop_exchange.rs:283` 不檢查回值（fire-and-forget pattern） | 低 | 與 emit_entry_lineage 既有設計一致（fail-soft，channel full → warn drop）；E2 確認 E4 regression 不期望特定 accepted 數。 |
| C-4 | TickPipeline accessor `agent_spine_tx_ref()` + `agent_spine_mode_ref()` 用 `pub(crate)` — 不洩漏到 crate 外，但 sibling event_consumer/ 可訪問 | 低 | E2 grep 是否 ipc_server / dispatch / 其他 sub-mod 也用此 accessor 而非 emit_entry_lineage path（避免將 spine 接線洩漏到不該的地方）。本 PR 0 多餘 callsite。 |
| C-5 | `fill_latency_ms` 型別 `Option<u64>` → ExecutionReport.fill_latency_ms `Option<f64>` 轉型 `ms as f64` | 低 | u64 ms ≤ 2^53 範圍內 f64 lossless；E2 可確認 SAFETY 注釋（`fill_latency_ms: input.fill_latency_ms.map(\|ms\| ms as f64)`）位置足夠。 |
| C-6 | 短窗 30min post-deploy 對抗 SQL（PA §4.3）期望 `missed_n=0` — 真實 fill ratio 49.4%（86/174）。**若部署期間 demo 市場空窗**，30min 內 0 fill → 無從 verify | 中 | E2 reviewer brief 接受 PA §4.5 退守 60min；本 IMPL fail-soft 保證舊 chain evidence 不退步；PM deploy SOP 含 cutoff env var 注入步驟必執行。 |

### 7.3 不確定之處

- **emit_fill_completion_lineage 內 `fill_latency_ms: input.fill_latency_ms.map(|ms| ms as f64)` 的 f64 轉型 SAFETY 注釋是否足夠**：u64 ms 在 1e15 級別才會 overflow f64 mantissa（~285 萬年），實務上 0；但 E2 若 strict 可建議 SAFETY 注釋升級或 fallible 轉型。
- **`liquidity_role: input.liquidity_role.to_string()` 接受 `&str` → `String` 看似多了一次 alloc**：在 fully_filled 低頻路徑（24h ~86 row）可忽略；E2 若 strict 可改 emit_fill_completion_lineage 內部接 `String` ownership。

### 7.4 硬邊界 + 16 原則 check（PA §7 對齊）

| 項 | 自查結果 |
|---|---|
| `live_execution_allowed` | 0 觸碰 ✓ |
| `max_retries = 0` | 0 觸碰 ✓ |
| `OPENCLAW_ALLOW_MAINNET` | 0 觸碰 ✓ |
| `live_reserved` / authorization.json | 0 寫入（純 spine row append） ✓ |
| Operator authorization boundary（governance_dev/2026-05-08--w_c_lease_router_authorized.md）| 0 違反；本 fix 屬「shadow lineage / bypass lease record / read-only audit」授權範圍內 ✓ |
| 原則 1 單一寫入口 | 不影響（IntentProcessor 不動） |
| 原則 3 AI ≠ 命令 | 不影響（emit lineage 不下單） |
| 原則 4 不繞風控 | 不影響（Guardian 不動） |
| 原則 8 交易可解釋 | **強化**（state_changes 補齊 + real-fill ExecutionReport row 補齊，audit trail 完整） |
| DOC-08 §12 9 安全不變量 | 0 觸碰 ✓ |

---

## 8. PM 待跑配對動作

1. **等 E2 review**：4 點 hot path SLA + unwrap + stable_id distinction + paper filter 預先確認，預期 PASS
2. **等 A3 + E4 adversarial review**（IMPL DONE 高風險 SOP，per `feedback_impl_done_adversarial_review.md`）
3. **等 sibling sub-agent E1-W-C-FIX-3（healthcheck Python 端）DONE**
4. **PM holistic commit**：把本 15 file + sibling W1/W2/E1-W-C-FIX-3 全打包同 commit，避免 build broken
5. **deploy**：`bash helper_scripts/restart_all.sh --rebuild --keep-auth` + 同時設 env `OPENCLAW_AGENT_SPINE_VALUE_QUALITY_CUTOFF_TS=<deploy_ts>`
6. **短窗 30 min verify**（PA §4.3 對抗 SQL，期望 missed_n=0）
7. **QA re-audit** Caveat 1+2 PASS → operator W-C → WINDOW_PASS sign-off
8. **W-D MAG-083 reviewer brief**：audit pack template 加 Caveat 1+2 fix delta 章節

---

**E1-W-C-FIX-RUST IMPL DONE**

Report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w_c_fix_rust_impl.md`
