//! Claude Teacher consumer-loop IPC handlers: flip the enabled flag and read
//! status counters. Both handlers operate on the late-injected
//! `TeacherLoopSlot`.
//!
//! MODULE_NOTE (EN): Split out of `handlers.rs` in E5-P1-3. When the slot is
//!   None the loop has not been wired yet and handlers fail-soft with
//!   `{"status":"uninitialized"}`.
//! MODULE_NOTE (中)：E5-P1-3 將 `handlers.rs` 按領域拆分後的「Teacher loop」桶。
//!   槽位為 None 時 fail-soft 回傳 uninitialized。

use super::super::*;

/// Phase 4.1: flip the Teacher consumer loop enabled flag (operator gate).
/// Phase 4.1：翻轉 Teacher consumer loop enabled 旗標（operator 閘）。
///
/// Params: { "enabled": bool }. Returns the new state. fail-soft if the loop
/// has not been wired (None slot) — returns `{"status":"uninitialized"}`.
/// 參數：{ "enabled": bool }。回傳新狀態。Loop 尚未接線（slot None）時
/// fail-soft 回傳 `{"status":"uninitialized"}`。
pub(in crate::ipc_server) async fn handle_set_teacher_loop_enabled(
    id: serde_json::Value,
    params: &serde_json::Value,
    slot: &TeacherLoopSlot,
) -> JsonRpcResponse {
    let enabled = match params.get("enabled").and_then(|v| v.as_bool()) {
        Some(b) => b,
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_REQUEST,
                "missing or non-boolean 'enabled' field",
            );
        }
    };
    let guard = slot.read().await;
    let handles = match guard.as_ref() {
        Some(h) => h,
        None => {
            return JsonRpcResponse::success(id, serde_json::json!({"status": "uninitialized"}));
        }
    };
    handles.enabled.store(enabled, Ordering::Relaxed);
    info!(
        enabled,
        "teacher consumer loop enabled flag set via IPC / 透過 IPC 設定 enabled 旗標"
    );
    JsonRpcResponse::success(id, serde_json::json!({"ok": true, "enabled": enabled}))
}

/// Phase 4.1: snapshot the Teacher consumer loop status counters.
/// Phase 4.1：快照 Teacher consumer loop 狀態計數。
///
/// Returns cycles_attempted / directives_applied / directives_vetoed /
/// cycles_errored / last_cycle_ms / enabled. fail-soft if not wired.
/// 回傳上述欄位。未接線時 fail-soft。
pub(in crate::ipc_server) async fn handle_get_teacher_loop_status(
    id: serde_json::Value,
    slot: &TeacherLoopSlot,
) -> JsonRpcResponse {
    let guard = slot.read().await;
    let handles = match guard.as_ref() {
        Some(h) => h,
        None => {
            return JsonRpcResponse::success(id, serde_json::json!({"status": "uninitialized"}));
        }
    };
    let (attempted, applied, vetoed, errored) = handles.status.snapshot();
    let last_cycle_ms = handles.status.last_cycle_ms.load(Ordering::Relaxed);
    let enabled = handles.enabled.load(Ordering::Relaxed);
    JsonRpcResponse::success(
        id,
        serde_json::json!({
            "status": "ok",
            "enabled": enabled,
            "cycles_attempted": attempted,
            "directives_applied": applied,
            "directives_vetoed": vetoed,
            "cycles_errored": errored,
            "last_cycle_ms": last_cycle_ms,
        }),
    )
}
