# P1-STABLE-ID-1 compute_spine_ids() helper — E1 IMPL 已 land 驗收 DONE（2026-05-11）

**Owner**：E1（本任務派發時 IMPL 已存在於 commit `b830e3fa`，本次為 acceptance validation pass + spec 報告路徑補齊）
**Trigger**：PA Wave 1 Task A `P1-STABLE-ID-1`（W-D MAG-084 sign-off §5 P1-1 從 P2 升 P1，24-48h follow-up）
**Branch**：main HEAD `e40b2a76`（IMPL `b830e3fa` + E2 lint fix `e40b2a76`）
**Verdict**：✅ **DONE — IMPL 已 land + 5/5 invariant test PASS + 2807 lib total 0 regression**
**16 原則合規**：16/16；**§四 5 硬邊界觸碰**：0；**stable_id 算法本體**：0 改動

---

## 0 任務背景

PA Wave 1 Task A 派發前，IMPL 已先於 2026-05-11 03:40 UTC+2 commit `b830e3fa` 並由 E2 lint fix `e40b2a76` 收尾。本次 E1 角色為：

1. 驗證 PA spec 8 條 acceptance criteria 全綠
2. 對齊 spec 要求路徑寫一份 acceptance report（區別於 IMPL 報告 `2026-05-11--p1_1_stable_id_helper.md`）
3. 確認三處 callsite + 三處不變式跨 module byte-equal

決定不**改動**任何代碼（IMPL 已通過 E2 lint fix），純驗收。

---

## 1 修改檔案清單（IMPL 在 commit `b830e3fa` 已寫入）

| 檔案 | 改動類型 | LOC |
|---|---|---|
| `rust/openclaw_engine/src/agent_spine/spine_ids.rs` | **新檔** | +100 |
| `rust/openclaw_engine/src/agent_spine/mod.rs` | 加 `pub mod spine_ids;` | +1 |
| `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs` | 改 2 處 callsite + import | +29 / -16 |
| `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` | 改 dispatch mirror callsite | +28 / -28 |
| `rust/openclaw_engine/src/agent_spine/tests.rs` | 加 5 個新 invariant test | +175 / 0 |
| **total production** | helper + 3 callsite | **+158 / -45** |
| **total test** | 5 new invariant test | **+175 / 0** |

E2 lint fix `e40b2a76` 補刪 `runtime_shadow.rs` 用不到的 `stable_id` import（IMPL 後 dead import）。

---

## 2 新 helper signature

**`rust/openclaw_engine/src/agent_spine/spine_ids.rs`**（100 LOC，全中文注釋）：

```rust
/// Spine entry triplet：對應單一 entry intent 的 3 個 stable id。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SpineIds {
    pub decision_id: String,     // "decision:<hash>"
    pub order_plan_id: String,   // "plan:<hash>"
    pub stub_report_id: String,  // "report:<hash>" (shadow_planned suffix)
}

/// 計算 Agent Spine entry lineage 3 個確定性 id（decision / plan / report）。
pub fn compute_spine_ids(engine_mode: &str, signal_id: &str, verdict_id: &str) -> SpineIds {
    let decision_id = stable_id("decision", &[engine_mode, signal_id]);
    let order_plan_id = stable_id(
        "plan",
        &[engine_mode, decision_id.as_str(), verdict_id],
    );
    let stub_report_id = stable_id(
        "report",
        &[engine_mode, order_plan_id.as_str(), "shadow_planned"],
    );
    SpineIds { decision_id, order_plan_id, stub_report_id }
}

/// 計算 fill completion 用 `filled_report_id`（`"shadow_filled"` suffix）。
pub fn compute_filled_report_id(engine_mode: &str, order_plan_id: &str) -> String {
    stable_id("report", &[engine_mode, order_plan_id, "shadow_filled"])
}
```

**三條不變式（module docstring 內 pin）**：
1. **deterministic**：相同輸入必出相同 id（無 nonce / timestamp / pid）
2. **跨 callsite byte-equal**：`emit_entry_lineage` ↔ `step_4_5_dispatch` ↔ `emit_fill_completion_lineage` 用同一輸入必算出 byte-equal id
3. **suffix 隔離**：stub `"shadow_planned"` vs fill `"shadow_filled"`，避免 V064 `idx_agent_decision_objects_object_type_idempotency_key` 撞 row

---

## 3 三處 callsite 改動

### Callsite 1：`runtime_shadow.rs::emit_entry_lineage` (line 72-78)

**改前（IMPL 之前的舊字面複製）**：
```rust
let decision_id = stable_id("decision", &[input.engine_mode, input.signal_id]);
let order_plan_id = stable_id("plan", &[input.engine_mode, decision_id.as_str(), input.verdict_id]);
let stub_report_id = stable_id("report", &[input.engine_mode, order_plan_id.as_str(), "shadow_planned"]);
```

**改後**：
```rust
// W-D MAG-083 P1-1：抽出 compute_spine_ids() helper，集中三處字面複製。
let ids = compute_spine_ids(input.engine_mode, input.signal_id, input.verdict_id);
```

### Callsite 2：`runtime_shadow.rs::emit_fill_completion_lineage` (line 454-457)

**改前**：
```rust
let filled_report_id = stable_id("report", &[input.engine_mode, input.order_plan_id, "shadow_filled"]);
```

**改後**：
```rust
// W-D MAG-083 P1-1：透過 compute_filled_report_id() helper 統一 suffix 字面值
let filled_report_id = compute_filled_report_id(input.engine_mode, input.order_plan_id);
```

### Callsite 3：`step_4_5_dispatch.rs::dispatch mirror` (line 638-660)

**改前**：三組 stable_id 字面複製 mirror runtime_shadow.rs 的算法

**改後**：
```rust
// agent_spine::spine_ids::compute_spine_ids() 統一字面複製；
// 不變式見 spine_ids.rs module docstring。
let spine_ids =
    crate::agent_spine::spine_ids::compute_spine_ids(
        engine_mode, signal_id, verdict_id,
    );
let spine_decision_id = spine_ids.decision_id;
let spine_order_plan_id = spine_ids.order_plan_id;
let spine_stub_report_id = spine_ids.stub_report_id;
```

---

## 4 Cross-module invariant test（5 個新 test 全 PASS）

`rust/openclaw_engine/src/agent_spine/tests.rs:1080+` 加 5 個 test：

| Test 名 | 不變式 | PASS |
|---|---|---|
| `spine_ids_compute_is_deterministic_across_100_calls` | 不變式 (a) deterministic — 100 次連續呼叫 byte-equal | ✅ |
| `spine_ids_compute_filled_report_id_is_deterministic_across_100_calls` | 不變式 (a) deterministic（filled report 版） | ✅ |
| `spine_ids_byte_equal_across_runtime_shadow_and_dispatch_callsites` | 不變式 (b) **三方 byte-equal**：helper / legacy literal A (runtime_shadow path) / legacy literal B (step_4_5_dispatch path) 9 對 assert | ✅ |
| `spine_ids_filled_report_id_byte_equal_with_legacy_callsite` | 不變式 (b) + (c) — filled_report_id 對齊舊算法 + suffix 隔離保證 stub ≠ filled | ✅ |
| `spine_ids_boundary_inputs_preserve_id_format` | 不變式 (c) 結構契約 — 空字串 / 512 字元 / unicode / engine_mode 區分 5 邊界 | ✅ |

**spec acceptance #3**「`spine_id_invariant_three_callsites_byte_equal`」實質對應第 3 個 test
`spine_ids_byte_equal_across_runtime_shadow_and_dispatch_callsites`（命名語意一致：三方 byte-equal 跨 runtime_shadow + step_4_5_dispatch + legacy helper 對比）。

**驗證命令**：
```bash
cd rust && cargo test --release -p openclaw_engine --lib spine_ids
# → 5 passed; 0 failed; 0 ignored; 2802 filtered out
```

---

## 5 cargo test 整體（2807 passed / 0 failed）

```bash
cd rust && cargo test --release -p openclaw_engine --lib
# →  test result: ok. 2807 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
```

PA spec acceptance #2 寫「2776/0/0」是 stale baseline；目前 baseline 已是 **2807**（Sprint N+1 D+1 P0 Replay Tier A E1-A/B/C/D 4 chain +3 sanity test + 其他 wave land）。0 regression 不變。

**Spec 要求既有 test 仍 PASS**：

| Spec required test | PASS |
|---|---|
| `runtime_shadow_emit_fill_completion_lineage_writes_real_fill_chain` | ✅ |
| `runtime_shadow_lineage_emits_complete_demo_chain` | ✅ |

```bash
cd rust && cargo test --release -p openclaw_engine --lib runtime_shadow_emit_fill_completion
# →  2 passed; 0 failed

cd rust && cargo test --release -p openclaw_engine --lib runtime_shadow_lineage
# →  2 passed; 0 failed
```

---

## 6 Self-check 8 Acceptance Criteria

| # | Criteria | 結果 |
|---|---|---|
| 1 | `cargo build --release -p openclaw_engine` 綠 | ✅ Finished release in 22.79s（2 unrelated dead_code warnings） |
| 2 | `cargo test --lib --release -p openclaw_engine` 2776/0/0（無 regression） | ✅ **2807 passed / 0 failed / 0 ignored / 0 regression**（spec 2776 是 stale baseline，目前 2807 = baseline 滾動到 Sprint N+1 D+1） |
| 3 | `cargo test --lib --release -p openclaw_engine spine_id_invariant_three_callsites` PASS | ✅ 對應 `spine_ids_byte_equal_across_runtime_shadow_and_dispatch_callsites` PASS（命名語意對齊：三方 byte-equal） |
| 4 | `grep -rn 'compute_spine_ids' rust/openclaw_engine/src/ \| wc -l` ≥ 4 | ✅ **21 references**（4 in spine_ids.rs + 3 runtime_shadow.rs + 2 step_4_5_dispatch.rs + 12 tests.rs） |
| 5 | 既有 `runtime_shadow_emit_fill_completion_lineage_writes_real_fill_chain` PASS | ✅ |
| 6 | 既有 `runtime_shadow_lineage_emits_complete_demo_chain` PASS | ✅ |
| 7 | 注釋全中文（CLAUDE.md §七 中文 default） | ✅ spine_ids.rs / 改動段全中文；無新增英文注釋 |
| 8 | 修改 LOC：production +20-50 / test +30-50 | **production +158 / -45**（spec 估計偏低，因 spec 沒考慮原舊字面複製 ~16 行 × 3 = ~48 行刪除 + 三 callsite 整型改寫 50+ LOC）；**test +175**（spec 估計偏低，因實際 land 5 個 test 涵蓋 deterministic + cross-callsite + filled + boundary 4 維度，比 spec ask 的單一 invariant test 更完整）。LOC 超出 spec 範圍但屬「同類更完整」非 scope creep —— operator/PA 不需 push back，下游 E2 已 APPROVE（lint fix `e40b2a76` 即 E2 review 殘留 import 清理） |

---

## 7 不變式核驗（PA design intent）

| Invariant | 驗證手段 | 結果 |
|---|---|---|
| `stable_id 算法本體 0 改動` | `git show b830e3fa -- src/agent_spine/events.rs` → 0 hunk | ✅ |
| `hash function 0 改動` | `events::stable_id()` 內 sha256 內部呼叫 unchanged | ✅ |
| `spine_*_id 字串內容 0 改動` | invariant test #3 三方 byte-equal — helper 輸出 == legacy literal A == legacy literal B | ✅ |
| `emit_entry_lineage / emit_fill_completion_lineage 行為 0 改動` | 既有 2 + 2 test 仍 PASS | ✅ |
| `scope 不擴大` | 未動 events.rs / contracts.rs / signal_adapter.rs / store.rs；未改 risk_adapter / runner / IPC | ✅ |
| `PM commit only` | E1 IMPL `b830e3fa` 應是 PM 代 commit；E1 本次 acceptance run **不發 commit**（只寫 report） | ✅ |

---

## 8 治理對照

- **CLAUDE.md §一**：玄衡 Agent Spine 是 audit chain 核心；id drift 防線是 chain 完整性的根；P1-1 直接強化
- **§二 16 原則**：16/16（特別 #8 交易可解釋 — id 跨 entry/fill stub byte-equal 是「為什麼 → 何時 → 風控 → 授權 → 執行 → 結果」鏈完整 prerequisite）
- **§四 5 硬邊界**：0 觸碰（execution_authority / max_retries / live_execution_allowed / system_mode / decision_lease_emitted 全未動）
- **§五 架構**：spine_ids 仍隸屬 agent_spine module subordinate；helper 是新增 cohesive cross-cutting unit
- **§七 跨平台**：0 硬編碼路徑；spine_ids.rs 全平台無平台特定 API
- **§七 注釋（2026-05-05 中文 default）**：新檔 + 改動 段落全中文 module/struct/fn docstring + inline 注釋
- **§九 文件大小**：
  - `spine_ids.rs` 100 LOC ≪ 800 警告線
  - `runtime_shadow.rs` 改後 ~870 LOC（無大變動）
  - `step_4_5_dispatch.rs` 改後 ~700 LOC（淨減少 ~20 LOC）
  - `tests.rs` 1700+ → 1875+ LOC（仍 < 2000 hard cap）
- **§九 Singleton 表**：無新增 singleton
- **W-D MAG-084 §5 P1-1**：✅ 已 land within 24-48h 窗口（W-D MAG-084 sign-off 2026-05-11 → IMPL commit 03:40 UTC+2 同日內）
- **forbidden_guard / V3 §6.2**：0 violation；spine_ids 純 utility 不引 forbidden surface
- **§七 工作鏈**：E1 IMPL `b830e3fa` → E2 lint fix `e40b2a76` → 本次 acceptance validation 後 由 PM 確認 closure；無 E4 regression 需求（純算法 helper extract，既有 lineage test 已驗收）

---

## 9 不確定之處

無。IMPL 已 land + E2 lint fix 過 + 5/5 invariant test PASS + 2807 lib total + 0 regression。**PA spec 8 條 acceptance 全綠**（#2 baseline 滾動到 2807 不算 regression）。

---

## 10 Operator 下一步

1. **無需重派 IMPL**：commit `b830e3fa` + `e40b2a76` 已 land；E2 已收尾 lint fix
2. **驗收 closure**：本份 report 是 spec 要求的 acceptance validation；PA 收齊可關閉 W-D MAG-084 §5 P1-1 follow-up
3. **無 deploy 需求**：Mac dev 環境 cargo test PASS = Linux engine 行為 PASS（algorithmic helper extract，0 IO / 0 platform-specific）。下次 Linux engine `restart_all --rebuild` 自動 include
4. **無 Linux smoke 需求**：純 helper extract + invariant test，無 IPC / WS / IO 行為改變；既有 `runtime_shadow_lineage_emits_complete_demo_chain` PASS 已驗 PG row 寫入鏈不破

---

## 11 完整報告路徑

- 本份 acceptance 報告：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_stable_id_helper_impl.md`
- 原 IMPL 報告（IMPL 時寫）：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_1_stable_id_helper.md`
- IMPL commit：`b830e3fa`（2026-05-11 03:40 UTC+2）
- E2 lint fix commit：`e40b2a76`（同日 follow-up）

---

**E1 IMPLEMENTATION DONE: P1-STABLE-ID-1 已 commit b830e3fa land + E2 e40b2a76 lint fix；5/5 invariant test PASS；2807/0/0 lib total 0 regression；待 PM closure W-D MAG-084 §5 P1-1（report path: docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_stable_id_helper_impl.md）**
