//! AI budget IPC handlers: read status, upsert scope config, record external
//! (Layer 2) usage for the shared `BudgetTracker`.
//!
//! MODULE_NOTE (EN): Split out of `handlers.rs` in E5-P1-3. These handlers all
//!   operate on the late-injected `BudgetTrackerSlot`. Fail-soft when the slot
//!   is `None` (read paths return `{"status":"uninitialized"}`); fail-closed
//!   (-32603) on write paths so a missing tracker can never silently drop an
//!   upsert or a usage row.
//! MODULE_NOTE (中)：E5-P1-3 將 `handlers.rs` 按領域拆分後的「AI 預算」桶。
//!   三個 handler 都操作延後注入的 `BudgetTrackerSlot`；讀路徑槽位為 None 時
//!   fail-soft 回傳 uninitialized，寫路徑 fail-closed 回傳 -32603，避免
//!   tracker 缺失時靜默丟單。

use super::super::*;

/// Phase 4 (4-15): Return current AI budget status snapshot.
/// Phase 4 (4-15)：返回當前 AI 預算狀態快照。
///
/// EN: If the BudgetTracker slot is None (e.g., DB pool unavailable at boot), this
///     fail-soft returns `{"status":"uninitialized"}` so dashboards can render a grey
///     card without raising an IPC error. When the tracker is present, returns the
///     full JSON produced by `BudgetTracker::status_json()` (limits, usage, degrade
///     level, last refresh timestamp).
/// 中：若 BudgetTracker 槽位為 None（例如 DB 池在啟動時不可用），fail-soft 回傳
///     `{"status":"uninitialized"}`，儀表板可顯示灰燈而不報錯。當 tracker 存在時，
///     回傳 `BudgetTracker::status_json()` 產生的完整 JSON（額度、用量、降級等級、
///     最近刷新時戳）。
pub(in crate::ipc_server) async fn handle_get_ai_budget_status(
    id: serde_json::Value,
    slot: &BudgetTrackerSlot,
) -> JsonRpcResponse {
    let guard = slot.read().await;
    match guard.as_ref() {
        Some(tracker) => {
            let payload = tracker.status_json().await;
            JsonRpcResponse::success(id, payload)
        }
        None => JsonRpcResponse::success(
            id,
            serde_json::json!({
                "status": "uninitialized",
                "reason": "BudgetTracker not yet injected (DB pool unavailable at boot?)",
            }),
        ),
    }
}

/// Phase 4 (4-15): Upsert one AI budget scope and refresh the in-memory config.
/// Phase 4 (4-15)：upsert 單一 AI 預算 scope 並刷新記憶體中的配置。
///
/// EN: Params schema: `{ "scope": <str>, "monthly_usd": <f64>, "updated_by": <str?> }`.
///     Fail-closed: missing/invalid params → -32602; tracker not initialized → -32603;
///     DB write or refresh failure → -32603 with error message; never panics. Successful
///     write triggers `BudgetTracker::refresh_config()` so the new ceiling is enforced
///     on the very next LLM call.
/// 中：參數格式：`{ "scope": <str>, "monthly_usd": <f64>, "updated_by": <str?> }`。
///     fail-closed：缺失/無效參數 → -32602；tracker 未初始化 → -32603；
///     DB 寫入或刷新失敗 → -32603 並附錯誤訊息；絕不 panic。寫入成功後觸發
///     `BudgetTracker::refresh_config()`，新上限在下一次 LLM 調用即生效。
pub(in crate::ipc_server) async fn handle_update_ai_budget_config(
    id: serde_json::Value,
    params: &serde_json::Value,
    slot: &BudgetTrackerSlot,
) -> JsonRpcResponse {
    const ERR_INVALID_PARAMS: i64 = -32602;

    let scope = match params.get("scope").and_then(|v| v.as_str()) {
        Some(s) if !s.is_empty() => s.to_string(),
        _ => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_PARAMS,
                "missing or empty 'scope' (string)",
            );
        }
    };
    let monthly_usd = match params.get("monthly_usd").and_then(|v| v.as_f64()) {
        Some(v) if v.is_finite() && v >= 0.0 => v,
        _ => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_PARAMS,
                "missing or invalid 'monthly_usd' (must be finite f64 >= 0)",
            );
        }
    };
    let updated_by = params
        .get("updated_by")
        .and_then(|v| v.as_str())
        .unwrap_or("ipc")
        .to_string();

    let guard = slot.read().await;
    let tracker = match guard.as_ref() {
        Some(t) => Arc::clone(t),
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INTERNAL,
                "budget tracker not initialized (DB pool unavailable?)",
            );
        }
    };
    drop(guard);

    let pool = tracker.pool_handle();
    if let Err(e) =
        crate::ai_budget::config_io::upsert_scope(&pool, &scope, monthly_usd, &updated_by).await
    {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("upsert failed: {e}"));
    }
    if let Err(e) = tracker.refresh_config().await {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("refresh_config failed: {e}"));
    }

    JsonRpcResponse::success(
        id,
        serde_json::json!({
            "ok": true,
            "scope": scope,
            "monthly_usd": monthly_usd,
            "updated_by": updated_by,
        }),
    )
}

/// FIX-57: Record external AI usage (Python Layer2 → Rust BudgetTracker sync).
/// FIX-57：記錄外部 AI 用量（Python Layer2 → Rust BudgetTracker 同步）。
///
/// Params: { "scope": str, "provider": str, "model": str,
///           "tokens_in": u32, "tokens_out": u32,
///           "purpose": str?, "request_id": str? }
/// Returns: { "ok": true, "cost_usd": f64 } or error.
/// 參數與回傳如上。fail-closed：tracker 未初始化或 DB 寫入失敗時回傳錯誤。
pub(in crate::ipc_server) async fn handle_record_ai_usage(
    id: serde_json::Value,
    params: &serde_json::Value,
    slot: &BudgetTrackerSlot,
) -> JsonRpcResponse {
    const ERR_INVALID_PARAMS: i64 = -32602;

    let scope = match params.get("scope").and_then(|v| v.as_str()) {
        Some(s) if !s.is_empty() => s,
        _ => return JsonRpcResponse::error(id, ERR_INVALID_PARAMS, "missing 'scope'"),
    };
    let provider = match params.get("provider").and_then(|v| v.as_str()) {
        Some(s) if !s.is_empty() => s,
        _ => return JsonRpcResponse::error(id, ERR_INVALID_PARAMS, "missing 'provider'"),
    };
    let model = match params.get("model").and_then(|v| v.as_str()) {
        Some(s) if !s.is_empty() => s,
        _ => return JsonRpcResponse::error(id, ERR_INVALID_PARAMS, "missing 'model'"),
    };
    let tokens_in = params
        .get("tokens_in")
        .and_then(|v| v.as_u64())
        .unwrap_or(0) as u32;
    let tokens_out = params
        .get("tokens_out")
        .and_then(|v| v.as_u64())
        .unwrap_or(0) as u32;
    let purpose = params
        .get("purpose")
        .and_then(|v| v.as_str())
        .unwrap_or("layer2_external");

    // E5-FN-2 Plan N: Python callers SHOULD pass a deterministic
    // `(request_id, event_time_ms)` tuple so Layer 2 retries collapse at the
    // hypertable PK. Backward-compat: if either is missing, mint a fresh one
    // locally (same as pre-Plan N — the caller simply loses dedup coverage for
    // its own retries). A literal `"py-sync"` default would collide across all
    // Python callers under the PK, so we always mint when omitted.
    // E5-FN-2 Plan N：Python caller 應傳入確定性
    // `(request_id, event_time_ms)` tuple，Layer 2 重試才能在 hypertable PK
    // 合併。向後相容：任一缺失即本地鑄造（等同 Plan N 前；caller 自行失去
    // 重試去重）。固定 `"py-sync"` 會讓所有 Python caller 在 PK 上碰撞，
    // 故缺失時一律重新鑄造。
    let supplied_request_id = params
        .get("request_id")
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string());
    let supplied_event_time_ms = params.get("event_time_ms").and_then(|v| v.as_i64());
    let (request_id, event_time_ms) = match (supplied_request_id, supplied_event_time_ms) {
        (Some(rid), Some(ts)) => (rid, ts),
        _ => crate::ai_budget::make_request_id(scope),
    };

    let guard = slot.read().await;
    let tracker = match guard.as_ref() {
        Some(t) => Arc::clone(t),
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INTERNAL,
                "budget tracker not initialized (DB pool unavailable?)",
            );
        }
    };
    drop(guard);

    match tracker
        .record_usage(
            scope,
            provider,
            model,
            tokens_in,
            tokens_out,
            purpose,
            &request_id,
            event_time_ms,
        )
        .await
    {
        Ok(cost_usd) => JsonRpcResponse::success(
            id,
            serde_json::json!({
                "ok": true,
                "cost_usd": cost_usd,
                "request_id": request_id,
                "event_time_ms": event_time_ms,
            }),
        ),
        Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("record_usage failed: {e}")),
    }
}
