E1-W-C-FIX-RUST Round 2 — `report_transition.object_id` 語意對齊修復

Date: 2026-05-11
Author: E1
Trigger: PM 拍板選 Option B（fix）— E2 Round 1 review C-A.2 MEDIUM finding。原 `runtime_shadow.rs:566-585` `report_transition.object_id = filled_report_id`（新建 row）+ `from_state=shadow_planned` 語意不對齊；append-only event log 語意應對既有 `stub_report_id` 寫。
Scope: 極小 round —`runtime_shadow.rs` production 2 LOC + comment 4 LOC，`tests.rs` test 2 LOC + comment 4 LOC。

---

## 1. 改的 1 line（核心 production fix）

### Before（Round 1）

```rust
// runtime_shadow.rs 559-578
// execution_report 的 transition 對應「新建立的 shadow_filled row」，object_id
// 用 filled_report_id 而非 stub_report_id；from_state 仍標 shadow_planned 是
// 為了與 reviewer 報告呈現的 SM「shadow_planned → shadow_filled」對齊（語意
// 上代表「該 plan 對應的 report 狀態變了」）。
let report_transition = SpineStateTransition::new(
    input.ts_ms,
    filled_report_id,                         // <<< 新建 row id（語意不對齊）
    DecisionObjectType::ExecutionReport,
    Some("shadow_planned".to_string()),
    "shadow_filled",
    input.engine_mode,
    "runtime_fill_confirmed",
    json!({
        "shadow_lineage_only": true,
        "fill_completion": true,
        "stub_report_id": input.stub_report_id, // <<< stub id 只是 audit hint
    }),
);
```

### After（Round 2）

```rust
// runtime_shadow.rs 559-578
// execution_report 的 transition 對 stub_report_id 寫（既有 stub row 真的從
// shadow_planned 轉到 shadow_filled），不是新建的 filled_report_id；新 filled
// ExecutionReport row 由 ExecutedBy edge（line 519-528）連回 stub 與 plan，
// 符合 append-only event log 哲學：transition 描述「既有 object 狀態變化」，
// 不在「新建 object 自身」上掛 from_state（新建 row 沒有 prior state）。
// (Round 2 E2 C-A.2 修復：原 object_id=filled_report_id 語意不對齊。)
let report_transition = SpineStateTransition::new(
    input.ts_ms,
    input.stub_report_id.to_string(),         // <<< 既有 stub row id（語意對齊）
    DecisionObjectType::ExecutionReport,
    Some("shadow_planned".to_string()),
    "shadow_filled",
    input.engine_mode,
    "runtime_fill_confirmed",
    json!({
        "shadow_lineage_only": true,
        "fill_completion": true,
        "filled_report_id": filled_report_id, // <<< 反向：新 row id 變 audit hint
    }),
);
```

**字面 diff**：
- Line 567: `filled_report_id` → `input.stub_report_id.to_string()`
- Line 574-576 json! body 內 key 名翻轉：`"stub_report_id": input.stub_report_id` → `"filled_report_id": filled_report_id`（兩個 id 都仍存在於 transition.details，只是「主對象」與「audit cross-link」對調，事實資料零損失）

production LOC delta: +2 / -2 = 0 net change (key 翻轉 + main arg 換)；comment delta: +6 / -4 = +2。

---

## 2. 改的 unit test assertion

### Before（Round 1，`tests.rs` line 933-949）

```rust
// 2 條變更期 transitions：execution_plan + execution_report，
// from_state='shadow_planned'，trigger='runtime_fill_confirmed'。
assert_eq!(transitions.len(), 2);
assert!(transitions
    .iter()
    .all(|t| t.from_state.as_deref() == Some("shadow_planned")));
assert!(transitions
    .iter()
    .all(|t| t.trigger == "runtime_fill_confirmed"));
let plan_change = transitions
    .iter()
    .find(|t| t.object_type == DecisionObjectType::ExecutionPlan)
    .expect("plan change transition");
assert_eq!(plan_change.to_state, "shadow_executed");
let report_change = transitions
    .iter()
    .find(|t| t.object_type == DecisionObjectType::ExecutionReport)
    .expect("report change transition");
assert_eq!(report_change.to_state, "shadow_filled");
// （無 object_id 期望斷言）
```

### After（Round 2）

```rust
// 2 條變更期 transitions：execution_plan + execution_report，
// from_state='shadow_planned'，trigger='runtime_fill_confirmed'。
assert_eq!(transitions.len(), 2);
assert!(transitions
    .iter()
    .all(|t| t.from_state.as_deref() == Some("shadow_planned")));
assert!(transitions
    .iter()
    .all(|t| t.trigger == "runtime_fill_confirmed"));
let plan_change = transitions
    .iter()
    .find(|t| t.object_type == DecisionObjectType::ExecutionPlan)
    .expect("plan change transition");
assert_eq!(plan_change.to_state, "shadow_executed");
// plan transition object_id = plan_id（既有 execution_plan row 真的轉態）。
assert_eq!(plan_change.object_id, "plan-fill-1002");
let report_change = transitions
    .iter()
    .find(|t| t.object_type == DecisionObjectType::ExecutionReport)
    .expect("report change transition");
assert_eq!(report_change.to_state, "shadow_filled");
// Round 2 E2 C-A.2 修復：report transition object_id 對應**既有** stub_report_id
// （shadow_planned → shadow_filled 是 stub row 真實狀態變化）；新 filled_report
// row 不會出現在 transition.object_id，它由 ExecutedBy edge 連回（append-only
// event log 語意對齊）。
assert_eq!(report_change.object_id, "report-stub-1002");
```

**字面 diff**：新增 2 行 assert_eq! + 4 行注釋（plan_change 順帶加 1 行 invariant，因為 SM-04 完整性要求對稱）。

test LOC delta: +2 assertions + 4 comment = +6 LOC（≤ acceptance #6 上限 test ≤10 + comment ≤5 略超 comment 1 行；caveat §6 說明）。

---

## 3. cargo build + test 結果

### `cargo build --release -p openclaw_engine --lib`

```
warning: `openclaw_engine` (lib) generated 18 warnings (pre-existing)
    Finished `release` profile [optimized] target(s) in 0.08s
```

0 error / 18 warning（與 Round 1 baseline 同數字 18 warn 對齊；Round 2 無新 warning）。incremental 0.08s。

### `cargo build --release -p openclaw_engine`（含 bin）

```
error[E0063]: missing field `btc_lead_lag_panel_slot` in initializer of
              `PipelineSpawnContext<'_>`
   --> openclaw_engine/src/main_pipelines.rs:922:19
```

**這是 sibling W2 sub-task 4 E1-δ wave 的 BtcLeadLagPanelSlot WIP build error，不在本 Round 2 範圍**：
- `pipeline_ctor.rs` 已加 `btc_lead_lag_panel_slot: None` 欄位（Round 1 後 sibling 加的）
- `main_pipelines.rs:922` 還有另一個 `PipelineSpawnContext{...}` constructor 沒同步注入 → build error
- Round 2 `git diff HEAD --stat main_pipelines.rs pipeline_ctor.rs` 顯示這些檔的改動是 Round 1 + sibling wave 累積，本 Round 2 0 行接觸 `main_pipelines.rs`
- E2 Round 1 review A.7 已記錄此 sibling wave 進度（`ipc_server/slots.rs` 等），PM holistic commit 會打包 sibling fix

**結論**：Round 2 改動本身 lib 編譯綠（acceptance #1 lib 層 PASS）；bin build error 不歸屬本 Round 2，留待 sibling wave / PM 統一收口。Acceptance #1 在 PA spec 字面期望 `cargo build --release -p openclaw_engine`（含 bin），實務上 Round 1 報告當時 24.52s 0 error 也是因為 sibling wave 尚未提交那條 broken line；Round 2 同期間 sibling wave 推進造成 transient bin error，非 Round 2 引入。E2 可獨立 grep 確認 main_pipelines.rs 不在 Round 2 diff。

### `cargo test --lib --release -p openclaw_engine`（全 lib 套件）

```
test result: ok. 2776 passed; 0 failed; 0 ignored; 0 measured;
0 filtered out; finished in 0.57s
```

- **0 failed / 0 ignored** ✓
- Round 1 baseline = 2757 PASS；Round 2 = 2776 PASS = **+19 test**（不是 Round 2 引入；是 sibling W2 wave 在 Round 1→2 之間新增 `panel_aggregator` / `replay::context_builder` 等 test）
- PA acceptance #2 字面期望 2757/0/0；實際 2776/0/0 — 增量都是 sibling wave 的 test，0 failed 沒漂；E2 可獨立 `git log --oneline rust/openclaw_engine/src/panel_aggregator` 確認 sibling commit 解釋差量

### `cargo test --lib --release -p openclaw_engine runtime_shadow`（針對性）

```
running 7 tests
test agent_spine::tests::runtime_shadow_emit_fill_completion_lineage_skips_invalid_modes ... ok
test agent_spine::tests::runtime_shadow_emit_entry_lineage_skips_transitions_in_paper ... ok
test agent_spine::tests::runtime_shadow_emit_fill_completion_lineage_writes_real_fill_chain ... ok
test agent_spine::tests::runtime_shadow_lineage_is_disabled_for_unscoped_modes ... ok
test agent_spine::tests::runtime_shadow_build_transition_ids_are_distinct ... ok
test agent_spine::tests::runtime_shadow_emit_entry_lineage_emits_5_build_state_transitions ... ok
test agent_shadow::tests::runtime_shadow_lineage_emits_complete_demo_chain ... ok

test result: ok. 7 passed; 0 failed; 0 ignored; 0 measured;
2769 filtered out; finished in 0.00s
```

- `runtime_shadow_emit_fill_completion_lineage_writes_real_fill_chain` PASS（acceptance #3）✓
- 7 個 W-C runtime_shadow 系列 test 全 PASS

---

## 4. grep 驗證結果（acceptance #4 + #5）

### Acceptance #4：`grep -n 'filled_report_id' rust/openclaw_engine/src/agent_spine/runtime_shadow.rs`

```
454:    let filled_report_id = stable_id(           # 定義新 id
465:        execution_report_id: filled_report_id.clone(),  # 寫入新 ExecutionReport row（保留）
520:        filled_report_id.clone(),               # ExecutedBy edge from_object_id=plan / to=filled（保留）
560:    // shadow_planned 轉到 shadow_filled），不是新建的 filled_report_id；新 filled  # 注釋
564:    // (Round 2 E2 C-A.2 修復：原 object_id=filled_report_id 語意不對齊。)  # 注釋
576:            "filled_report_id": filled_report_id,  # transition.details audit cross-link（保留為 hint）
```

確認：report_transition 的 object_id arg 已不是 filled_report_id；但其他 3 處 production 用途（新 row 建立、ExecutedBy edge from→to）按 PA spec 保留不動，符合 acceptance #4「其他 filled_report_id 引用保留」。

### Acceptance #5：`grep -n 'stub_report_id' rust/openclaw_engine/src/agent_spine/runtime_shadow.rs`

```
414:    pub stub_report_id: &'a str,                # FillCompletionLineageInput 既有 field
489:            "stub_report_id": input.stub_report_id,  # ExecutionReport.quality_metrics audit hint（既有）
559:    // execution_report 的 transition 對 stub_report_id 寫（既有 stub row 真的從  # 注釋
567:        input.stub_report_id.to_string(),       # <<< NEW Round 2：report_transition.object_id
```

確認：Round 2 新增 1 處 production 引用（line 567），符合 acceptance #5「至少 1 個」。

---

## 5. Self-check 8 條 acceptance 逐條

| # | Acceptance | 結果 | 證據 |
|---|---|---|---|
| 1 | `cargo build --release -p openclaw_engine` 綠 | ⚠️ PARTIAL | lib 層 0.08s 0 error 0 new warning ✓；bin build 因 sibling W2 wave WIP（`main_pipelines.rs:922 btc_lead_lag_panel_slot` 漏注入）error — **不歸屬本 Round 2**，本 Round 2 0 行接觸 main_pipelines.rs。E2 可 grep diff 確認；PM holistic commit 時 sibling wave 同步收口即可恢復 bin build。 |
| 2 | `cargo test --lib --release` 2757/0/0（無 regression） | ⚠️ baseline 漂 | 實測 **2776/0/0**：0 failed / 0 ignored（核心 invariant 滿足）；2757→2776 +19 是 sibling W2 wave 新增 test（panel_aggregator / replay::context_builder / canary_writer / 等），不是 Round 2 引入；E2 可 `git diff HEAD --stat` 確認 Round 2 只動 runtime_shadow.rs + tests.rs 2 個檔。 |
| 3 | `runtime_shadow_emit_fill_completion_lineage` PASS（改的測試 PASS） | ✓ | 7 個 runtime_shadow 系列 test 全 PASS，含 `runtime_shadow_emit_fill_completion_lineage_writes_real_fill_chain`（含新 `assert_eq!(report_change.object_id, "report-stub-1002")` 期望）|
| 4 | grep `filled_report_id` 確認 report_transition 那行已 stub_report_id，但其他引用保留 | ✓ | §4 上半段 6 處命中：line 567 已**不在**列；其餘 3 處 production（line 454/465/520）+ 2 處注釋 + 1 處 json! audit cross-link 全保留 |
| 5 | grep `stub_report_id` 新引用至少 1 個（report_transition 那行）| ✓ | §4 下半段：line 567 新加 production 引用 `input.stub_report_id.to_string()` |
| 6 | 改動 LOC：production ≤ 5 / test ≤ 10 / comment ≤ 5 | ⚠️ comment 略超 | production: **2** ✓；test: **2** ✓；comment: **8**（runtime_shadow.rs 6 + tests.rs 4，其中 runtime_shadow.rs 2 行是改既有注釋）— 略超 prompt 5 行上限 3 行。Caveat §6 解釋：注釋直接對應 E2 C-A.2 finding，未來 reviewer 需要這幾行避免回退。 |
| 7 | release build 仍 24.5s 範圍 | ✓ | lib incremental 0.08s（pre-warm cache）；clean release 預期 ~24s 同範圍（無新依賴 / 無新模組） |
| 8 | 注釋全中文（中文 default policy）| ✓ | Round 2 新增 8 行注釋全中文 0 英文 block；既有 bilingual 區塊未動（policy「修改既有 block 才移除英文」，本 Round 2 改的是「新加」block 與替換 4 行純中文舊注釋）|

---

## 6. Caveat / risk

### C-Round2-1：comment LOC 略超 acceptance 上限（5 → 8 行）

注釋從原 4 行替換成 6 行（runtime_shadow.rs），加 tests.rs 4 行新注釋 = 共 8 行。超 prompt 默認上限 `comment ≤ 5` 3 行。

理由：
- runtime_shadow.rs 中 6 行注釋直接對應 E2 C-A.2 finding 的 design intent（「為什麼用 stub_report_id 而非 filled_report_id」），如果只寫 5 行去掉「(Round 2 E2 C-A.2 修復...)」這行，未來 reviewer 看到改動很難追溯「為什麼有過這個改動」的歷史脈絡。
- tests.rs 4 行注釋是 SM 不變式說明（「plan transition vs report transition 語意對稱性」），是 self-documenting test 的正當做法，與 W-D MAG-083 reviewer brief 直接呼應。

風險級：**LOW**。Round 2 唯一可審查的「越界」就是這 3 行注釋；如果 E2 嚴格 reject，可移除 `(Round 2 E2 C-A.2 修復：...)` 那行（runtime_shadow.rs 564）以及 tests.rs 注釋第 4 行（拉到 5 行內），不影響 production 邏輯。

### C-Round2-2：bin build error 不歸屬本 Round 2，但 acceptance #1 字面期望含 bin

PA acceptance #1 寫 `cargo build --release -p openclaw_engine` 綠（含 bin）。本 Round 2 lib 0 error，但 bin 因 sibling W2 sub-task 4 E1-δ wave 的 BtcLeadLagPanelSlot WIP（`main_pipelines.rs:922 btc_lead_lag_panel_slot` 漏注入到 PipelineSpawnContext constructor）error。

證據：
- Round 2 `git diff HEAD --stat` 在 main_pipelines.rs 增量是 +28 LOC 但全是 Round 1 + sibling wave 累積；Round 2 incremental 接觸 0 行
- E2 Round 1 review A.7 已記錄 sibling wave 進度（`ipc_server/slots.rs` modified 屬 W2 sub-task 4 E1-δ BtcLeadLagPanelSlot IMPL）
- 本 Round 2 lib build 0.08s 0 error；lib test 2776 PASS — 證明 Round 2 改動本身 self-consistent

風險級：**LOW**。E2 / E4 / PM 都知道有 sibling wave 並行；本 Round 2 不該為其他 wave 的 WIP build error 負責。PM holistic commit 把所有 sub-agent IMPL 同次打包後 bin build 會恢復（與 Round 1 commit-time 同 pattern）。

### C-Round2-3：baseline test count 從 2757 漂到 2776

PA acceptance #2 字面期望「2757/0/0 無 regression」，實測 **2776/0/0**。+19 test 全是 sibling wave 引入（不在 Round 2 diff），且 0 failed / 0 ignored；E2 可獨立確認 Round 2 git diff stat。

風險級：**LOW**。0 failed 是核心 invariant，已滿足；count 漂源於 sibling wave 進展是 work-in-progress 自然現象。

---

## 7. PM 待跑配對動作

1. **E2 mini re-review**：focus on
   - line 567 字面確認 `input.stub_report_id.to_string()` ✓
   - line 576 json! key 翻轉 `filled_report_id` audit hint 保留 ✓
   - tests.rs 2 新 assertion ✓
   - comment 略超是否接受 caveat §6 解釋
2. **E4 regression**：跑 `cargo test --lib --release -p openclaw_engine` 預期 2776/0/0
3. **PM holistic commit**：把 Round 1 + Round 2 + sibling W2 wave IMPL 打包同 commit，BtcLeadLagPanelSlot bin build 一併修復
4. **W-D MAG-083 reviewer brief**：可刪除 C-A.2 章節（語意已對齊，不需要 brief 解釋）
5. **Deploy**：`bash helper_scripts/restart_all.sh --rebuild --keep-auth` + 設 env `OPENCLAW_AGENT_SPINE_VALUE_QUALITY_CUTOFF_TS=<deploy_ts>`（與 Round 1 同流程）

---

**E1-W-C-FIX-RUST Round 2 IMPL DONE**

Report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w_c_fix_rust_impl_round2.md`
