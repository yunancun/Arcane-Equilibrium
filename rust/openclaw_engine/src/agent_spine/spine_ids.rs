//! Agent Spine stable id helper（W-D MAG-083 P1-1）。
//!
//! 此 module 抽取 Agent Spine entry lineage 與 fill completion 共用的
//! stable_id 計算邏輯，集中為 `compute_spine_ids()` + `compute_filled_report_id()`
//! 兩個 helper。在抽取之前，三個 callsite 字面複製相同的 stable_id
//! 算法、相同的 prefix 字串（`"decision"` / `"plan"` / `"report"`）、
//! 相同的 parts 順序（engine_mode → signal_id / decision_id / order_plan_id →
//! verdict_id / "shadow_planned" suffix），任何一處漂移都會在
//! `agent.decision_objects` / `agent.decision_edges` 形成 silent id drift，
//! 進而打斷 W-C/MAG-083 audit chain 的 entry → fill 串接。
//!
//! 不變式 / Invariants：
//! - **相同輸入必出相同 id**：函式內部不引入 nonce / timestamp / process
//!   id 等非確定性因子；100 次連續呼叫必 byte-equal。
//! - **跨 callsite byte-equal**：`emit_entry_lineage` 與
//!   `tick_pipeline::on_tick::step_4_5_dispatch` 端用同一組
//!   `(engine_mode, signal_id, verdict_id)` 呼叫，產出的
//!   `decision_id` / `order_plan_id` / `stub_report_id` 必字節相等，
//!   PendingOrder.spine_* 才能與 entry stub 的 row 對齊；下游
//!   `emit_fill_completion_lineage` 由 stub `order_plan_id` 推導出的
//!   `filled_report_id` 也必跨 callsite byte-equal。
//! - **suffix 隔離**：stub report 用 `"shadow_planned"` suffix；
//!   fill completion 用 `"shadow_filled"` suffix，保證
//!   `idx_agent_decision_objects_object_type_idempotency_key` 不撞 row。
//!
//! 後續所有 Spine id 計算路徑必透過本 module 落地，禁止在新 callsite
//! 再次字面複製 `stable_id("decision"|"plan"|"report", &[…])` 邏輯。
//! 違反 = entry/fill audit chain silent drift 風險。

use super::events::stable_id;

/// Spine entry triplet：對應單一 entry intent 的 3 個 stable id。
///
/// 由 `compute_spine_ids()` 在 entry path 一次性算出，供
/// `emit_entry_lineage` 直接寫 entry stub row，以及
/// `step_4_5_dispatch` 端鏡射到 `OrderDispatchRequest.spine_*` /
/// `PendingOrder.spine_*` 欄位（再經 loop_exchange 在 fully_filled 時
/// 反查 fill 補完 lineage）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SpineIds {
    /// StrategistDecision 的 decision_id（`"decision:<hash>"`）。
    pub decision_id: String,
    /// ExecutionPlan 的 order_plan_id（`"plan:<hash>"`）。
    pub order_plan_id: String,
    /// 對應 entry stub `shadow_planned` row 的 execution_report_id
    /// （`"report:<hash>"`，suffix `"shadow_planned"`）。
    pub stub_report_id: String,
}

/// 計算 Agent Spine entry lineage 三個確定性 id（decision / plan / report）。
///
/// **必呼叫者**：
/// 1. `runtime_shadow::emit_entry_lineage()` — 寫入 entry stub row。
/// 2. `tick_pipeline::on_tick::step_4_5_dispatch` — 鏡射到
///    `OrderDispatchRequest.spine_*`，下游 `PendingOrder` 攜帶到
///    `loop_exchange` 端在 `fully_filled` 時呼叫
///    `emit_fill_completion_lineage`。
///
/// **不變式**：相同 `(engine_mode, signal_id, verdict_id)` 必出相同 3 個 id
/// （見本檔 module docstring 跨 callsite byte-equal 不變式）。
///
/// 參數順序與舊字面複製對齊（嚴禁變動），避免改動後造成 silent id drift：
/// - `decision_id = stable_id("decision", &[engine_mode, signal_id])`
/// - `order_plan_id = stable_id("plan", &[engine_mode, decision_id, verdict_id])`
/// - `stub_report_id = stable_id("report", &[engine_mode, order_plan_id, "shadow_planned"])`
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
    SpineIds {
        decision_id,
        order_plan_id,
        stub_report_id,
    }
}

/// 計算 fill completion 用 `filled_report_id`（`"shadow_filled"` suffix）。
///
/// 對應 `emit_fill_completion_lineage` 在 fully_filled 時寫一條新的
/// ExecutionReport row（status=`shadow_filled`），其 idempotency_key
/// 以 `shadow_execution_report_filled:` 前綴隔離 entry stub
/// （`shadow_execution_plan:`），同時 report id 用 `"shadow_filled"`
/// suffix 與 stub 的 `"shadow_planned"` suffix 區隔，避免 V064 schema
/// `idx_agent_decision_objects_object_type_idempotency_key` 唯一索引
/// 撞 row。
///
/// **不變式**：相同 `(engine_mode, order_plan_id)` 必出相同 id；
/// 任一 callsite 不可改 suffix 字串。
pub fn compute_filled_report_id(engine_mode: &str, order_plan_id: &str) -> String {
    stable_id(
        "report",
        &[engine_mode, order_plan_id, "shadow_filled"],
    )
}
