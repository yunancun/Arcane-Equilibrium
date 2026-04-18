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
    let primary_label = cmd_channels.primary_label();
    for (label, ch) in [
        ("paper", &cmd_channels.paper),
        ("demo", &cmd_channels.demo),
        ("live", &cmd_channels.live),
    ] {
        // Skip the primary (already sent above) and None channels
        // 跳過主管線（已發送）和 None 通道
        if label == primary_label {
            continue;
        }
        if let Some(tx) = ch {
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
