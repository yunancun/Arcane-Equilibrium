//! Governance IPC handlers: operator governor escalate / de-escalate (with
//! V014 audit trail) and global system-mode broadcast across all active
//! engine pipelines.
//!
//! MODULE_NOTE (EN): Split out of `handlers.rs` in E5-P1-3. All three public
//!   handlers go through `pipeline_cmd_tx` / `EngineCommandChannels` and
//!   write a `V014 engine_events` audit row on the rejected path too — an
//!   operator probing guards without a paper-trail would violate principle
//!   #8 (every risk-touching action explainable + auditable). The private
//!   `spawn_governor_audit_row` helper is kept file-local.
//! MODULE_NOTE (中)：E5-P1-3 將 `handlers.rs` 按領域拆分後的「治理」桶。
//!   escalate / de-escalate / broadcast 三個 handler 覆蓋 governor 手動
//!   覆蓋與系統模式廣播；守衛拒絕路徑同樣寫 V014 審計行，符合原則 #8
//!   「每個風控觸發動作皆可解釋且可審計」。`spawn_governor_audit_row`
//!   為檔案內私有輔助。

use super::super::*;

/// ARCH-RC1 1C-3-B-2: Force governor toward more restrictive tier (operator
/// escalation). No 24h cooldown — operator can always be more careful.
/// Writes V014 audit row on success.
/// ARCH-RC1 1C-3-B-2：強制 governor 往更嚴方向（無冷卻 + V014 audit）。
pub(in crate::ipc_server) async fn handle_force_governor_tighter(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    params: &serde_json::Value,
    audit_pool: &Option<sqlx::PgPool>,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "paper command channel not configured")
        }
    };
    let target_tier = match params.get("target_tier").and_then(|v| v.as_str()) {
        Some(s) => s.to_string(),
        None => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing target_tier"),
    };
    let reason = match params.get("reason").and_then(|v| v.as_str()) {
        Some(s) => s.to_string(),
        None => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing reason"),
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::ForceGovernorTighter {
        target_tier: target_tier.clone(),
        reason: reason.clone(),
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    match tokio::time::timeout(std::time::Duration::from_secs(5), resp_rx).await {
        Ok(Ok(Ok(json_str))) => {
            // M-2 (ARCH-RC1 1C-3-D): success audit — payload carries the
            // operator's free-form reason directly (N-5 fix: no positional
            // argument confusion — caller owns the payload shape).
            // M-2：成功 audit；caller 自組 payload 避免位置參數錯位（N-5 修正）。
            spawn_governor_audit_row(
                audit_pool,
                "governor_escalate",
                serde_json::json!({
                    "result": "applied",
                    "target_tier": target_tier,
                    "reason": reason,
                    "engine_result": serde_json::from_str::<serde_json::Value>(&json_str)
                        .unwrap_or(serde_json::Value::Null),
                }),
            );
            match serde_json::from_str::<serde_json::Value>(&json_str) {
                Ok(v) => JsonRpcResponse::success(id, v),
                Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("parse: {e}")),
            }
        }
        Ok(Ok(Err(e))) => {
            // M-2: guard-rejected attempts MUST be audited — an operator
            // probing the step/direction guards without leaving a V014 row
            // would violate principle #8 (every risk-touching action
            // explainable + auditable).
            // M-2：被守衛拒絕也必須 audit，避免靜默探測。
            spawn_governor_audit_row(
                audit_pool,
                "governor_escalate_rejected",
                serde_json::json!({
                    "result": "rejected",
                    "target_tier": target_tier,
                    "reason": reason,
                    "error": e,
                }),
            );
            JsonRpcResponse::error(id, ERR_INVALID_REQUEST, e)
        }
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for event consumer"),
    }
}

/// ARCH-RC1 1C-3-B-2: Force governor toward less restrictive tier (operator
/// de-escalation). Wraps the dangerous de-escalation path with reason enum +
/// 24h cooldown + V014 audit + per-batch lock-down rules. CB / MR cannot be
/// unlocked here — operator must edit TOML and restart.
/// ARCH-RC1 1C-3-B-2：強制 governor 降級（reason enum + 24h cooldown + audit）。
pub(in crate::ipc_server) async fn handle_force_governor_looser(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    params: &serde_json::Value,
    audit_pool: &Option<sqlx::PgPool>,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "paper command channel not configured")
        }
    };
    let target_tier = match params.get("target_tier").and_then(|v| v.as_str()) {
        Some(s) => s.to_string(),
        None => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing target_tier"),
    };
    let reason_code = match params.get("reason_code").and_then(|v| v.as_str()) {
        Some(s) => s.to_string(),
        None => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing reason_code"),
    };
    let notes = params
        .get("notes")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::ForceGovernorLooser {
        target_tier: target_tier.clone(),
        reason_code: reason_code.clone(),
        notes: notes.clone(),
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    match tokio::time::timeout(std::time::Duration::from_secs(5), resp_rx).await {
        Ok(Ok(Ok(json_str))) => {
            spawn_governor_audit_row(
                audit_pool,
                "governor_de_escalate",
                serde_json::json!({
                    "result": "applied",
                    "target_tier": target_tier,
                    "reason_code": reason_code,
                    "notes": notes,
                    "engine_result": serde_json::from_str::<serde_json::Value>(&json_str)
                        .unwrap_or(serde_json::Value::Null),
                }),
            );
            match serde_json::from_str::<serde_json::Value>(&json_str) {
                Ok(v) => JsonRpcResponse::success(id, v),
                Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("parse: {e}")),
            }
        }
        Ok(Ok(Err(e))) => {
            // M-2: Rejection audit — cooldown / whitelist / step / CB+MR
            // lockout all land here. Every probe attempt gets a V014 row.
            // M-2：4 個守衛拒絕路徑全部落到這裡，每次嘗試都有 audit 行。
            spawn_governor_audit_row(
                audit_pool,
                "governor_de_escalate_rejected",
                serde_json::json!({
                    "result": "rejected",
                    "target_tier": target_tier,
                    "reason_code": reason_code,
                    "notes": notes,
                    "error": e,
                }),
            );
            JsonRpcResponse::error(id, ERR_INVALID_REQUEST, e)
        }
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for event consumer"),
    }
}

/// Fire-and-forget V014 audit insert for governor override events.
/// Mirrors the pattern in handle_patch_config — failure logs WARN but never
/// blocks the IPC response. Caller owns the payload shape (N-5 fix: previously
/// this helper packed 5 positional string args into a fixed dict, causing the
/// escalate branch to record a literal "operator_escalation" in reason_code
/// and the operator's free-form text in notes — semantically wrong).
/// Caller-built `payload` must include `result` ("applied"|"rejected") and
/// any error string for rejection rows.
/// V014 audit row 寫入；caller 自組 payload shape（N-5 修正，避免位置錯位）。
fn spawn_governor_audit_row(
    audit_pool: &Option<sqlx::PgPool>,
    event_type: &str,
    payload: serde_json::Value,
) {
    let Some(pool) = audit_pool.clone() else {
        return;
    };
    let event_type = event_type.to_string();
    let ts_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0);
    tokio::spawn(async move {
        if let Err(e) = sqlx::query(
            "INSERT INTO observability.engine_events
             (ts_ms, event_type, source, config_name, old_version, new_version, payload)
             VALUES ($1, $2, $3, $4, NULL, NULL, $5)",
        )
        .bind(ts_ms)
        .bind(&event_type)
        .bind("operator")
        .bind("risk_governor")
        .bind(&payload)
        .execute(&pool)
        .await
        {
            tracing::warn!(error = %e, "V014 governor audit row insert failed (non-fatal)");
        }
    });
}

// ═══════════════════════════════════════════════════════════════════════════════
// SM Option-2 收斂 step (i)（2026-06-02）：治理 lease + 唯讀投影 IPC dispatch
// ═══════════════════════════════════════════════════════════════════════════════
//
// 為什麼這些 handler 走 `pipeline_cmd_tx` + oneshot round-trip：IPC server 沒有直接
// 的 `GovernanceCore` handle（per-pipeline GovernanceCore 由 tick actor 獨佔），故
// 鏡像既有 `handle_force_governor_tighter` 模式：解 JSON-RPC params → 構造
// PipelineCommand → 等 oneshot → format JSON 回覆。
//
// fail-CLOSED 規則（鏡像既有 governance handler）：
//   - cmd channel 未配置 / send 失敗 / oneshot dropped / timeout → JSON-RPC error
//     （ERR_INTERNAL）；tick-actor 回 Err(String) → JSON-RPC error（ERR_INVALID_REQUEST）。
//   - 絕不把任一錯誤路徑解讀為 permissive / empty-success。
//   - Python 端（governance_lease_bridge.py / governance_hub.py）收到 JSON-RPC error
//     後 fail-closed：acquire→None、release→False、is_authorized→False、
//     status→FROZEN+stale。
//
// 與 governance_lease_bridge.py / lease_ipc_schema.py 契約對齊（method 名 + param
// 鍵 + response 形狀，E1 親驗，見 dispatch arm 註釋）。
//
// ADDITIVE / dormant：dispatch arm 存在但 Python flag 打開前不主動呼叫；
// 不碰 execution_authority / live_reserved / 5 道 live-auth gate。

/// step (i) · 共用：取 primary pipeline 的 cmd tx（lease + 投影皆走 primary
/// pipeline 的 GovernanceCore，與 `set_system_mode` 取 primary 同理；read 為
/// per-pipeline 視圖，符合 3-config 獨立）。None → fail-closed error。
fn governance_primary_tx(
    cmd_channels: &EngineCommandChannels,
) -> Result<tokio::sync::mpsc::UnboundedSender<PipelineCommand>, JsonRpcResponseErrorParts> {
    cmd_channels.primary().ok_or(JsonRpcResponseErrorParts {
        code: ERR_INTERNAL,
        message: "no command channel configured (engine down) / 無命令通道（引擎未運行）"
            .to_string(),
    })
}

/// step (i) · 共用：等 oneshot 回覆並把 `Result<String, String>` 轉成
/// JSON-RPC 回覆。`json_str` 為 tick-actor 回的 JSON payload 字串；解析後原樣
/// 放入 result。所有錯誤路徑都 fail-closed 成 JSON-RPC error。
async fn await_governance_reply(
    id: serde_json::Value,
    resp_rx: tokio::sync::oneshot::Receiver<Result<String, String>>,
) -> JsonRpcResponse {
    match tokio::time::timeout(std::time::Duration::from_secs(5), resp_rx).await {
        Ok(Ok(Ok(json_str))) => match serde_json::from_str::<serde_json::Value>(&json_str) {
            Ok(v) => JsonRpcResponse::success(id, v),
            Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("parse reply: {e}")),
        },
        // tick-actor 回 Err(String)：fail-closed → JSON-RPC error（非 permissive）。
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INVALID_REQUEST, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for tick actor"),
    }
}

/// 內部用的 error 部件（避免在 `?` 早退時直接構造 JsonRpcResponse 需要 id）。
struct JsonRpcResponseErrorParts {
    code: i64,
    message: String,
}

/// step (i) · `governance.acquire_lease` dispatch。
///
/// 契約對齊 lease_ipc_schema.build_acquire_request_params（method
/// `governance.acquire_lease`；params 鍵 `intent_id`/`scope`/`ttl_ms`/`profile`/
/// `source_stage`）與 parse_acquire_response（response `{lease_id, outcome}`，
/// outcome ∈ {"Active","Bypass"}）。
pub(in crate::ipc_server) async fn handle_acquire_lease(
    id: serde_json::Value,
    cmd_channels: &EngineCommandChannels,
    params: &serde_json::Value,
) -> JsonRpcResponse {
    let tx = match governance_primary_tx(cmd_channels) {
        Ok(tx) => tx,
        Err(e) => return JsonRpcResponse::error(id, e.code, e.message),
    };
    let intent_id = match params.get("intent_id").and_then(|v| v.as_str()) {
        Some(s) if !s.is_empty() => s.to_string(),
        _ => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing/empty intent_id"),
    };
    let scope = match params.get("scope").and_then(|v| v.as_str()) {
        Some(s) if !s.is_empty() => s.to_string(),
        _ => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing/empty scope"),
    };
    // ttl_ms 為 u32；超界由 GovernanceCore::acquire_lease fail-closed 拒絕
    // （InvalidTtl，單一真實來源 = Rust spec）。此處只驗存在 + u32 範圍。
    let ttl_ms = match params.get("ttl_ms").and_then(|v| v.as_u64()) {
        Some(n) if n <= u32::MAX as u64 => n as u32,
        _ => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing/invalid ttl_ms"),
    };
    let profile = match params.get("profile").and_then(|v| v.as_str()) {
        Some(s) if !s.is_empty() => s.to_string(),
        _ => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing/empty profile"),
    };
    // source_stage 為遙測標籤，缺省給空字串（不致命）。
    let source_stage = params
        .get("source_stage")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::AcquireLease {
        intent_id,
        scope,
        ttl_ms,
        profile,
        source_stage,
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    await_governance_reply(id, resp_rx).await
}

/// step (i) · `governance.release_lease` dispatch。
///
/// 契約對齊 lease_ipc_schema.build_release_request_params（method
/// `governance.release_lease`；params 鍵 `lease_id`/`outcome`，outcome ∈
/// {"Consumed","Failed","Cancelled"}）與 parse_release_response（response
/// `{ok: true}`）。
pub(in crate::ipc_server) async fn handle_release_lease(
    id: serde_json::Value,
    cmd_channels: &EngineCommandChannels,
    params: &serde_json::Value,
) -> JsonRpcResponse {
    let tx = match governance_primary_tx(cmd_channels) {
        Ok(tx) => tx,
        Err(e) => return JsonRpcResponse::error(id, e.code, e.message),
    };
    let lease_id = match params.get("lease_id").and_then(|v| v.as_str()) {
        Some(s) if !s.is_empty() => s.to_string(),
        _ => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing/empty lease_id"),
    };
    let outcome = match params.get("outcome").and_then(|v| v.as_str()) {
        Some(s) if !s.is_empty() => s.to_string(),
        _ => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing/empty outcome"),
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::ReleaseLease {
        lease_id,
        outcome,
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    await_governance_reply(id, resp_rx).await
}

/// step (i) · `governance.get_lease` dispatch。
///
/// 契約對齊 lease_ipc_schema.build_get_request_params（method
/// `governance.get_lease`；params 鍵 `lease_id`）與 parse_get_response（response
/// = 序列化 LeaseObject，含 `lease_id` 欄位；not found → JSON-RPC error → Python None）。
pub(in crate::ipc_server) async fn handle_get_lease(
    id: serde_json::Value,
    cmd_channels: &EngineCommandChannels,
    params: &serde_json::Value,
) -> JsonRpcResponse {
    let tx = match governance_primary_tx(cmd_channels) {
        Ok(tx) => tx,
        Err(e) => return JsonRpcResponse::error(id, e.code, e.message),
    };
    let lease_id = match params.get("lease_id").and_then(|v| v.as_str()) {
        Some(s) if !s.is_empty() => s.to_string(),
        _ => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing/empty lease_id"),
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::GetLease {
        lease_id,
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    await_governance_reply(id, resp_rx).await
}

/// step (i) · `governance.is_authorized` 唯讀投影 dispatch。
///
/// 新定義契約（並行 Python work 須對齊）：
///   - method：`governance.is_authorized`
///   - params：`{}`（無）
///   - response：`{"authorized": bool}`
///   - fail-closed：任一 IPC error → Python 端回 False（deny），絕不回 True。
pub(in crate::ipc_server) async fn handle_is_authorized(
    id: serde_json::Value,
    cmd_channels: &EngineCommandChannels,
) -> JsonRpcResponse {
    let tx = match governance_primary_tx(cmd_channels) {
        Ok(tx) => tx,
        Err(e) => return JsonRpcResponse::error(id, e.code, e.message),
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::IsAuthorized {
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    await_governance_reply(id, resp_rx).await
}

/// step (i) · `governance.get_status` 唯讀投影 dispatch。
///
/// 新定義契約（並行 Python work 須對齊）：
///   - method：`governance.get_status`
///   - params：`{}`（無）
///   - response：`{enabled: bool, mode: "NORMAL"|"RESTRICTED"|"FROZEN"|
///     "MANUAL_REVIEW", risk_level: "NORMAL"|...|"MANUAL_REVIEW",
///     auth_effective_count: int, auth_pending_approval: int,
///     lease_live_count: int, oms_active_count: int}`
///   - fail-closed：IPC error → Python 投影為 mode=FROZEN + stale=true，絕不 NORMAL。
pub(in crate::ipc_server) async fn handle_get_status(
    id: serde_json::Value,
    cmd_channels: &EngineCommandChannels,
) -> JsonRpcResponse {
    let tx = match governance_primary_tx(cmd_channels) {
        Ok(tx) => tx,
        Err(e) => return JsonRpcResponse::error(id, e.code, e.message),
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::GetGovStatus {
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    await_governance_reply(id, resp_rx).await
}

/// step (i) · `governance.list_leases` 唯讀投影 dispatch。
///
/// 新定義契約（並行 Python work 須對齊）：
///   - method：`governance.list_leases`
///   - params：`{}`（無）
///   - response：`[LeaseObject, ...]`（serde array；空集合回 `[]`）
///   - fail-closed：IPC error → Python 回空列表 + stale 標記（不偽造 lease）。
pub(in crate::ipc_server) async fn handle_list_leases(
    id: serde_json::Value,
    cmd_channels: &EngineCommandChannels,
) -> JsonRpcResponse {
    let tx = match governance_primary_tx(cmd_channels) {
        Ok(tx) => tx,
        Err(e) => return JsonRpcResponse::error(id, e.code, e.message),
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::ListLeases {
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    await_governance_reply(id, resp_rx).await
}

/// step (i) · `governance.get_risk_state` 唯讀投影 dispatch。
///
/// 新定義契約（並行 Python work 須對齊）：
///   - method：`governance.get_risk_state`
///   - params：`{}`（無）
///   - response：`{level: str, level_value: int, level_entered_at_ms: int,
///     held_ms: int, consecutive_escalations: int, version: int,
///     constraints: {new_entries_allowed, position_size_multiplier, reduce_only,
///     active_de_risking, emergency_stops, requires_operator},
///     transitions_tail: [TransitionRecord, ...] (最近 ≤8 筆)}`
///   - fail-closed：IPC error → Python 投影 risk≥CAUTIOUS sentinel + stale=true。
pub(in crate::ipc_server) async fn handle_get_risk_state(
    id: serde_json::Value,
    cmd_channels: &EngineCommandChannels,
) -> JsonRpcResponse {
    let tx = match governance_primary_tx(cmd_channels) {
        Ok(tx) => tx,
        Err(e) => return JsonRpcResponse::error(id, e.code, e.message),
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::GetRiskState {
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    await_governance_reply(id, resp_rx).await
}

// 3E-3: handle_add_engine_mode and handle_switch_engine_mode REMOVED.
// In 3E-ARCH, pipelines are spawned at startup with fixed PipelineKind.
// Dynamic mode switching is replaced by per-pipeline command routing.
// 3E-3：handle_add_engine_mode 和 handle_switch_engine_mode 已移除。
// 3E-ARCH 下管線在啟動時以固定 PipelineKind 啟動，動態模式切換被管線路由取代。

/// 3E-3: Broadcast system mode to ALL active pipelines.
/// SetSystemMode is global — every pipeline must see the same system mode.
/// Sends to primary first (waits for response), then fire-and-forget to others.
/// 3E-3：廣播系統模式到所有活躍管線。SetSystemMode 是全局的。
/// 先發送到主管線（等待回應），再 fire-and-forget 發送到其他管線。
pub(in crate::ipc_server) async fn handle_set_system_mode_broadcast(
    id: serde_json::Value,
    cmd_channels: &EngineCommandChannels,
    params: &serde_json::Value,
) -> JsonRpcResponse {
    let mode = match params.get("mode").and_then(|v| v.as_str()) {
        Some(m) => m.to_string(),
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_REQUEST,
                "missing required param: mode (live_reserved/demo_reserved/shadow_only/observe_only/design_only)".to_string(),
            )
        }
    };
    // Send to primary pipeline (with response channel for confirmation)
    let primary_tx = cmd_channels.primary();
    let tx = match primary_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INTERNAL,
                "no command channel configured".to_string(),
            )
        }
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    let _ = tx.send(PipelineCommand::SetSystemMode {
        mode: mode.clone(),
        response_tx: resp_tx,
    });
    // Fire-and-forget to other pipelines (they don't need response channels for broadcast)
    // 向其他管線 fire-and-forget（廣播不需要回應通道）
    //
    // 2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN: read live via
    // `live_snapshot()` (slot-aware) so a `LiveAuthWatcher`-rotated sender
    // is reached. paper / demo remain owned-Option access — they never
    // respawn mid-session.
    // 2026-04-27：live 經 `live_snapshot()`（slot-aware）讀取，
    // 取到 watcher 輪替的 sender；paper / demo 仍 owned-Option。
    let primary_label = cmd_channels.primary_label();
    let live_snapshot = cmd_channels.live_snapshot();
    for (label, owned_ch) in [
        ("paper", cmd_channels.paper.clone()),
        ("demo", cmd_channels.demo.clone()),
        ("live", live_snapshot.clone()),
    ] {
        // Skip the primary (already sent above) and None channels
        // 跳過主管線（已發送）和 None 通道
        if label == primary_label {
            continue;
        }
        if let Some(tx) = owned_ch {
            let (other_resp_tx, _other_resp_rx) = tokio::sync::oneshot::channel();
            let _ = tx.send(PipelineCommand::SetSystemMode {
                mode: mode.clone(),
                response_tx: other_resp_tx,
            });
            tracing::debug!(
                engine = label,
                "set_system_mode broadcast sent / 系統模式廣播已發送"
            );
        }
    }
    match tokio::time::timeout(std::time::Duration::from_secs(3), resp_rx).await {
        Ok(Ok(Ok(msg))) => {
            JsonRpcResponse::success(id, serde_json::json!({ "ok": true, "detail": msg }))
        }
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INTERNAL, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "channel closed".to_string()),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout".to_string()),
    }
}
