# E1 IMPL Report — W-D MAG-083 P1-1 stable_id helper 抽出 + cross-module invariant test

- **日期**：2026-05-11
- **責任 Agent**：E1（Backend Developer）
- **任務來源**：W-D MAG-083/084 sign-off §5 P1-1（PA audit `2026-05-11--w_d_mag083_pa_audit.md` + 主會話 dispatch）
- **基準 HEAD**：`388e04b2`（dispatch 起點）；session 起手 main `073b7fba`
- **完成判定**：5 個 cross-module invariant test 全 PASS + cargo lib test 2785 PASS（baseline 2780→+5 new, 0 regression）

---

## 1. 任務摘要

W-D MAG-083 PA audit 指出 `stable_id` 算法字面複製 3 處，從 E5 D-1 P2 升 P1，因為涉及未來 silent id drift 引發 audit chain 斷裂風險。本任務抽出共用 `compute_spine_ids()` helper + 改 3 處 callsite + 加 5 個 cross-module invariant test，確保 entry / fill lineage 跨 module byte-equal。

## 2. 真實「字面複製」清單（reality check）

dispatch 描述的「字面複製 3 處」實際對應如下（先 grep 才確認，不盲改）：

| 處 | 檔案 | 行號（pre-fix）| 算什麼 id |
|---|---|---|---|
| A | `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs` | 72-80 | entry triplet（decision_id / order_plan_id / report_id） |
| B | `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` | 638-660 | 鏡射 entry triplet（spine_decision_id / spine_order_plan_id / spine_stub_report_id），參數順序與 A 對齊 |
| C | `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs` | 454-461 | fill completion 用 filled_report_id（suffix `"shadow_filled"`） |

`stable_id()` 本身已是 helper（位於 `events.rs:395`），但**呼叫端的 prefix 字串 + parts 順序 + suffix 字面值字面複製**在 3 處跨 module 出現，任一處未來不同步即 silent drift。

dispatch §1 提到的「paper shadow path」實際不存在獨立 paper-only stable_id 構造（paper engine_mode 在 `emit_entry_lineage` 開頭已 `matches!(engine_mode, "demo" | "live_demo")` short-circuit），三處實為 entry triplet 在 emit_entry_lineage / step_4_5_dispatch + fill completion 在 emit_fill_completion_lineage。

## 3. 修改清單

### 3.1 新檔
- `rust/openclaw_engine/src/agent_spine/spine_ids.rs` —— 89 行；定義 `SpineIds` struct + `compute_spine_ids()` + `compute_filled_report_id()`；module docstring 三條不變式（deterministic / cross-callsite byte-equal / suffix 隔離）。

### 3.2 既檔修改

| 檔案 | 動作 | 行範圍（post-fix）|
|---|---|---|
| `rust/openclaw_engine/src/agent_spine/mod.rs` | 註冊 `pub mod spine_ids` | line 12 |
| `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs` | (1) import `compute_spine_ids` + `compute_filled_report_id`；(2) `emit_entry_lineage` 內 line 72-80 改用 helper destructure；(3) `emit_fill_completion_lineage` 內 line 454-461 改用 `compute_filled_report_id` | line 27 + 72-78 + 454-457 |
| `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` | line 638-660 三個 stable_id 字面呼叫改為單一 `compute_spine_ids` + destructure | line 638-660 |
| `rust/openclaw_engine/src/agent_spine/tests.rs` | 追加 5 個 invariant test（共 ~150 LOC，append at end） | line 1071-1244 |

### 3.3 byte-equal 保證

- helper 內部呼叫 `events::stable_id`，sha256 algorithm 字面不動。
- helper 的 prefix 字串（`"decision"` / `"plan"` / `"report"`）與 suffix 字串（`"shadow_planned"` / `"shadow_filled"`）與舊字面字串一致。
- parts 順序與 pre-fix 一致（A: `[engine_mode, signal_id]` → `[engine_mode, decision_id, verdict_id]` → `[engine_mode, order_plan_id, "shadow_planned"]`；C: `[engine_mode, order_plan_id, "shadow_filled"]`）。
- Test `spine_ids_byte_equal_across_runtime_shadow_and_dispatch_callsites` 直接重現 pre-fix 字面複製的 stable_id 三呼叫，與 helper 輸出 byte-equal 比對 PASS。

## 4. 關鍵 diff（最小 footprint，0 邏輯變動）

### 4.1 `runtime_shadow.rs` (line 72-80 → 72-78)

```diff
-    let decision_id = stable_id("decision", &[input.engine_mode, input.signal_id]);
-    let order_plan_id = stable_id(
-        "plan",
-        &[input.engine_mode, decision_id.as_str(), input.verdict_id],
-    );
-    let report_id = stable_id(
-        "report",
-        &[input.engine_mode, order_plan_id.as_str(), "shadow_planned"],
-    );
+    // W-D MAG-083 P1-1：抽出 compute_spine_ids() helper，集中三處字面複製。
+    // 不變式：相同 (engine_mode, signal_id, verdict_id) 必出相同 3 個 id；
+    // step_4_5_dispatch 端鏡射 callsite 與此處跨 module byte-equal。
+    let ids = compute_spine_ids(input.engine_mode, input.signal_id, input.verdict_id);
+    let decision_id = ids.decision_id;
+    let order_plan_id = ids.order_plan_id;
+    let report_id = ids.stub_report_id;
```

### 4.2 `runtime_shadow.rs` (line 454-461 → 454-457)

```diff
-    let filled_report_id = stable_id(
-        "report",
-        &[
-            input.engine_mode,
-            input.order_plan_id,
-            "shadow_filled",
-        ],
-    );
+    // W-D MAG-083 P1-1：透過 compute_filled_report_id() helper 統一 suffix 字面值，
+    // 避免未來在他處再次字面複製 "shadow_filled" 字串造成 silent drift。
+    let filled_report_id = compute_filled_report_id(input.engine_mode, input.order_plan_id);
```

### 4.3 `step_4_5_dispatch.rs` (line 638-660)

```diff
-                                let spine_decision_id =
-                                    crate::agent_spine::events::stable_id(
-                                        "decision",
-                                        &[em, signal_id.as_str()],
-                                    );
-                                let spine_order_plan_id =
-                                    crate::agent_spine::events::stable_id(
-                                        "plan",
-                                        &[
-                                            em,
-                                            spine_decision_id.as_str(),
-                                            verdict_id_for_dispatch.as_str(),
-                                        ],
-                                    );
-                                let spine_stub_report_id =
-                                    crate::agent_spine::events::stable_id(
-                                        "report",
-                                        &[
-                                            em,
-                                            spine_order_plan_id.as_str(),
-                                            "shadow_planned",
-                                        ],
-                                    );
+                                // W-D MAG-083 P1-1（2026-05-11）：抽 helper 集中
+                                // 字面複製；不變式見 spine_ids.rs module docstring。
+                                let verdict_id_for_dispatch =
+                                    make_verdict_id(em, &intent.symbol, event.ts_ms);
+                                let spine_ids =
+                                    crate::agent_spine::spine_ids::compute_spine_ids(
+                                        em,
+                                        signal_id.as_str(),
+                                        verdict_id_for_dispatch.as_str(),
+                                    );
+                                let spine_decision_id = spine_ids.decision_id;
+                                let spine_order_plan_id = spine_ids.order_plan_id;
+                                let spine_stub_report_id = spine_ids.stub_report_id;
```

## 5. Cross-module invariant test 清單

5 個新 test 全部位於 `agent_spine/tests.rs:1072-1244`，分 3 大不變式：

| Test 名 | 不變式 | 結果 |
|---|---|---|
| `spine_ids_compute_is_deterministic_across_100_calls` | (a) 相同輸入跑 100 次 byte-equal | PASS |
| `spine_ids_compute_filled_report_id_is_deterministic_across_100_calls` | (a) 補充 filled report id | PASS |
| `spine_ids_byte_equal_across_runtime_shadow_and_dispatch_callsites` | (b) 三方 byte-equal：helper / legacy A / legacy B | PASS |
| `spine_ids_filled_report_id_byte_equal_with_legacy_callsite` | (b) 補充 filled vs stub suffix 區隔（V064 idempotency_key 唯一索引保護） | PASS |
| `spine_ids_boundary_inputs_preserve_id_format` | (c) 空字串 / 512-char / unicode / 不同 engine_mode 邊界 | PASS |

### 5.1 真實 cohort byte-equal 證據

`spine_ids_byte_equal_across_runtime_shadow_and_dispatch_callsites` 內模擬 3 個獨立 byte-equal 比對路徑：

1. **Helper 路徑**：`compute_spine_ids("demo", "sig-cohort-A-2002", "vrd-cohort-A-2002")`
2. **Legacy literal-copy path A**：mirror runtime_shadow.rs 抽取前的 3 次 `stable_id(...)` 字面呼叫
3. **Legacy literal-copy path B**：mirror step_4_5_dispatch.rs 抽取前的 3 次 `stable_id(...)` 字面呼叫

`assert_eq!` 三方 6 對比較（helper.decision_id == legacy_a.decision_id == legacy_b.decision_id，order_plan_id / report_id 同樣）+ legacy A vs legacy B 自比 3 對，共 9 個 assert 全 PASS。

`spine_ids_filled_report_id_byte_equal_with_legacy_callsite` 額外 assert `filled_report_id != stub_report_id`（V064 schema 唯一索引保護不變式）。

## 6. cargo test baseline delta

| 階段 | lib test 數 | 結果 |
|---|---|---|
| Pre-fix（git stash 後 main `073b7fba`）| 2780 | 0 fail |
| Post-fix（HEAD = 本 IMPL）| 2785 | 0 fail（+5 new spine_ids tests）|

- **無 regression**：2780 pre-fix → 2785 post-fix；新增 5 = 5 invariant test；既有 test 0 失敗 / 0 ignored。
- **dispatch §5 寫的 baseline 2695**：屬 Sprint N+1 D+0 EXECUTION snapshot 過時值，主因是 D+0 後 W-D / W-C / runtime_shadow / W-AUDIT-9 等多個 wave land 累積；以 git stash 即時測量為準。
- cargo check（`--tests` lib + bin + 21 integration test crates）全 PASS，0 新 warning。

## 7. 治理對照

- **跨平台合規**（CLAUDE.md §七）：純 Rust 改動 / 無 user-home 硬編碼 / 無 OS 差異。
- **雙語/中文注釋**（CLAUDE.md §七 2026-05-05 governance change）：新代碼注釋以中文為主，技術術語保留英文（`stable_id` / `sha256` / `byte-equal` / `helper` / `invariant`）；既有英文 module docstring 維持不變。
- **§九 LOC 限制**：runtime_shadow.rs（pre-fix 558 → post-fix 555，-3）；step_4_5_dispatch.rs（pre-fix ~1820 → post-fix ~1804，-16）；spine_ids.rs 89 LOC（新檔）；tests.rs（pre-fix 1070 → post-fix 1244，+174 純 test 不入 prod LOC budget）。**0 檔超 2000 cap**。
- **§七 SQL guard / 被動等待 healthcheck / Sign-off git status clean / V### PG dry-run**：本任務不涉及 SQL / migration / passive wait，N/A。
- **不變式硬邊界**（CLAUDE.md §四）：未碰 `max_retries` / `live_execution_allowed` / `execution_authority` / `system_mode` / authorization 路徑。本任務僅重構 stable_id 邏輯字面複製，0 邏輯變動。

## 8. 不確定之處 / Caveats

1. **dispatch §1 提到的「paper shadow path」**：實際 codebase 無獨立 paper-only stable_id callsite（paper engine_mode 在 emit_entry_lineage 開頭即 short-circuit）。本任務以 `emit_fill_completion_lineage` 內 `filled_report_id` 作為第 3 處解讀，與 dispatch §2-§4 描述「entry triplet + fill completion」邏輯一致。如 PA 原意指另一未浮現的 path，請 reviewer 在 E2 階段指出。
2. **dispatch §5 baseline 2695**：本實作以 git stash 即時測量 2780 為 ground truth（D+0 後多 wave land 累積；2785 post-fix 反映 +5 new test，0 regression）。
3. **未來 PendingOrder.spine_** mirror chain**：dispatch.rs / pending_sweep.rs / commands.rs 等 callsite 直接 assign `Option<String>`，無 stable_id 構造，故不需改。但若未來再有新 callsite 構造 spine id，必須走 `compute_spine_ids()` helper（spine_ids.rs module docstring 明文要求）。
4. **byte-equal 保證**：透過內部 `events::stable_id` 不動 + prefix/suffix 字串字面一致 + parts 順序對齊，pre/post-fix 對相同輸入產出 byte-equal id。test 5.1 已 assert，但這是「白盒對等性」非「對既有資料庫 row hash 重算」；如需 production data 端對等性 audit 由 E4 跑 PG cross-join 補。

## 9. Operator 下一步

1. E2 代碼審查（聚焦：helper API 命名 / SpineIds struct 是否需 Builder / 跨 module byte-equal proof 強度 / 是否要 propagate helper 到 events.rs:280 + 334 的 edge_id / transition_id 路徑）。
2. E4 回歸測試（pytest sibling 不變；只跑 Rust cargo test 即可，本任務無 Python 改動）。
3. PM 確認 byte-equal 證據是否需要再增 PG 端「對歷史 row hash 重算」驗證（可選；PA audit 不要求，本任務不擴大 scope）。
4. PM 收尾統一 commit + push。

## 10. 完成判定回報摘要

1. **helper 抽出位置**：`rust/openclaw_engine/src/agent_spine/spine_ids.rs`（新檔 89 LOC）。
2. **三處 callsite 改動**：
   - `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs:72-78`（entry triplet）
   - `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs:454-457`（fill completion）
   - `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs:638-660`（dispatch mirror）
3. **cross-module invariant test 數 + PASS**：5 個新 test 全 PASS（`agent_spine::tests::spine_ids_*`）。
4. **cargo test baseline delta**：pre-fix lib 2780 PASS → post-fix lib 2785 PASS（+5 new test, 0 regression）。
5. **byte-equal 證據**：(a) deterministic 100 次 PASS；(b) helper vs legacy A vs legacy B 三方 byte-equal 9 對 assert PASS；(c) filled vs stub suffix 區隔 1 對 assert PASS；(d) boundary inputs（空 / 512-char / unicode / cross-engine_mode）格式不變 PASS。
6. **commit hash + push 狀態**：待 PM 統一 commit（CLAUDE.md §七 強制鏈 E1→E2→E4→QA→PM）。本任務嚴守 E1 不直接 commit，待 E2 審查 → E4 回歸通過。
7. **三端同步**：待 PM commit 後 Linux 端 `git pull --ff-only origin main`。
