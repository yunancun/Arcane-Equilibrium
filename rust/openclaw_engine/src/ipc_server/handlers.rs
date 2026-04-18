//! IPC method handler implementations — dispatched from mod.rs dispatch_request.
//! IPC 方法處理器實現 — 由 mod.rs 的 dispatch_request 分發。

use super::*;

// Config IPC helpers (handle_get_config, handle_patch_config) live in
// handlers_config.rs, declared as a sibling module in mod.rs.
// Config IPC 輔助（handle_get_config、handle_patch_config）在
// handlers_config.rs，作為 mod.rs 的兄弟模組聲明。

/// Get current engine state summary.
/// Reads system_mode from pipeline snapshot (set by Python GUI sync).
/// 獲取當前引擎狀態摘要。
/// 從 pipeline 快照讀取 system_mode（由 Python GUI 同步設置）。
pub(super) fn handle_get_state(
    id: serde_json::Value,
    config: &Arc<ConfigManager>,
    data_dir: &Arc<std::path::PathBuf>,
) -> JsonRpcResponse {
    let cfg = config.get();
    // ARCH-RC1 1C-1: risk display fields now sourced from RiskConfig::default()
    // placeholder; 1C-2 will replace with live ConfigStore<RiskConfig> snapshot.
    // ARCH-RC1 1C-1：風控展示欄位暫從 RiskConfig::default() 讀；1C-2 改真快照。
    let risk = crate::config::RiskConfig::default();
    // Read system_mode + trading_mode from pipeline snapshot (single read).
    // 從 pipeline 快照一次讀取 system_mode + trading_mode。
    let (system_mode, trading_mode) = {
        let path = data_dir.join("pipeline_snapshot.json");
        let parsed = std::fs::read_to_string(&path)
            .ok()
            .and_then(|c| serde_json::from_str::<serde_json::Value>(&c).ok());
        let sm = parsed
            .as_ref()
            .and_then(|v| {
                v.get("system_mode")
                    .and_then(|s| s.as_str().map(String::from))
            })
            .filter(|s| !s.is_empty())
            .unwrap_or_else(|| "live_reserved".to_string());
        let tm = parsed
            .as_ref()
            .and_then(|v| {
                v.get("trading_mode")
                    .and_then(|t| t.as_str().map(String::from))
            })
            .unwrap_or_else(|| "paper".to_string());
        (sm, tm)
    };
    let state = serde_json::json!({
        "status": "running",
        "system_mode": system_mode,
        "trading_mode": trading_mode,
        "max_open_positions": risk.limits.open_positions_max,
        "max_total_exposure_pct": risk.limits.total_exposure_max_pct,
        "ws_url": cfg.ws_url,
        "config_path": config.file_path().display().to_string(),
    });
    JsonRpcResponse::success(id, state)
}

/// Phase 4 (4-00): Return dashboard skeleton status aggregation.
/// Phase 4 (4-00): 返回儀表板骨架的狀態聚合。
///
/// Each Phase 4 module (Teacher / LinUCB / News / DL-3) reports a traffic-light
/// state. At skeleton stage all modules report "grey" (not started). Subsequent
/// sub-tasks (4-01 ... 4-21) will replace the stub with real status sources.
///
/// 各 Phase 4 模組（Teacher / LinUCB / News / DL-3）回報一個紅黃綠燈狀態。
/// 骨架階段全部回報 "grey"（未啟動）。後續子任務（4-01 ... 4-21）會將 stub
/// 替換為真實狀態源。
///
/// Schema:
///   {
///     "teacher": "grey" | "green" | "yellow" | "red",
///     "linucb":  "grey" | ...,
///     "news":    "grey" | ...,
///     "dl3":     "grey" | ...,
///     "last_update_ms": <unix-millis>
///   }
pub(super) fn handle_get_phase4_status(id: serde_json::Value) -> JsonRpcResponse {
    let now_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0);
    let payload = serde_json::json!({
        "teacher": "grey",
        "linucb":  "grey",
        "news":    "grey",
        "dl3":     "grey",
        "last_update_ms": now_ms,
    });
    JsonRpcResponse::success(id, payload)
}

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
pub(super) async fn handle_get_ai_budget_status(
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
pub(super) async fn handle_update_ai_budget_config(
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
pub(super) async fn handle_record_ai_usage(
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
    let request_id = params
        .get("request_id")
        .and_then(|v| v.as_str())
        .unwrap_or("py-sync");

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
            scope, provider, model, tokens_in, tokens_out, purpose, request_id,
        )
        .await
    {
        Ok(cost_usd) => {
            JsonRpcResponse::success(id, serde_json::json!({ "ok": true, "cost_usd": cost_usd }))
        }
        Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("record_usage failed: {e}")),
    }
}

/// Phase 4.1: flip the Teacher consumer loop enabled flag (operator gate).
/// Phase 4.1：翻轉 Teacher consumer loop enabled 旗標（operator 閘）。
///
/// Params: { "enabled": bool }. Returns the new state. fail-soft if the loop
/// has not been wired (None slot) — returns `{"status":"uninitialized"}`.
/// 參數：{ "enabled": bool }。回傳新狀態。Loop 尚未接線（slot None）時
/// fail-soft 回傳 `{"status":"uninitialized"}`。
pub(super) async fn handle_set_teacher_loop_enabled(
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
pub(super) async fn handle_get_teacher_loop_status(
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

// ---------------------------------------------------------------------------
// Phase 3b: Strategy parameter IPC handlers / 策略參數 IPC 處理器
// ---------------------------------------------------------------------------

/// Strategy parameter operation type / 策略參數操作類型
pub(super) enum StrategyParamOp {
    Update,
    Get,
    Ranges,
}

/// Handle strategy parameter commands — sends oneshot request to event consumer.
/// 處理策略參數命令 — 發送 oneshot 請求到事件消費者。
pub(super) async fn handle_strategy_param_cmd(
    id: serde_json::Value,
    tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    params: &serde_json::Value,
    op: StrategyParamOp,
) -> JsonRpcResponse {
    let tx = match tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "paper command channel not configured")
        }
    };

    let strategy_name = match params.get("strategy_name").and_then(|v| v.as_str()) {
        Some(s) => s.to_string(),
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_REQUEST,
                "missing strategy_name parameter",
            )
        }
    };

    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();

    let cmd = match op {
        StrategyParamOp::Update => {
            let params_json = match params.get("params_json").and_then(|v| v.as_str()) {
                Some(s) => s.to_string(),
                None => {
                    // Also accept params_json as an object and serialize it
                    // 也接受 params_json 作為對象並序列化
                    match params.get("params_json") {
                        Some(v) if v.is_object() => serde_json::to_string(v).unwrap_or_default(),
                        _ => {
                            return JsonRpcResponse::error(
                                id,
                                ERR_INVALID_REQUEST,
                                "missing params_json parameter",
                            )
                        }
                    }
                }
            };
            PipelineCommand::UpdateStrategyParams {
                strategy_name,
                params_json,
                response_tx: resp_tx,
            }
        }
        StrategyParamOp::Get => PipelineCommand::GetStrategyParams {
            strategy_name,
            response_tx: resp_tx,
        },
        StrategyParamOp::Ranges => PipelineCommand::GetParamRanges {
            strategy_name,
            response_tx: resp_tx,
        },
    };

    if let Err(e) = tx.send(cmd) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }

    // Await response with timeout (5s) / 等待回應（5 秒超時）
    match tokio::time::timeout(std::time::Duration::from_secs(5), resp_rx).await {
        Ok(Ok(Ok(result))) => JsonRpcResponse::success(id, serde_json::json!({ "result": result })),
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INTERNAL, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for event consumer"),
    }
}

/// Update risk config at runtime (GUI → Python → IPC → Rust engine).
/// 運行時更新風控配置。
/// Parse Option<Option<f64>> from JSON: absent=None, null=Some(None), number=Some(Some(x)).
/// 解析 JSON 中的 Option<Option<f64>>：不存在=None，null=Some(None)，數字=Some(Some(x))。
fn parse_opt_opt_f64(params: &serde_json::Value, key: &str) -> Option<Option<f64>> {
    match params.get(key) {
        None => None,                         // key absent = no change
        Some(v) if v.is_null() => Some(None), // key: null = disable
        Some(v) => v.as_f64().map(Some),      // key: 2.5 = enable with value
    }
}

pub(super) async fn handle_update_risk_config(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    params: &serde_json::Value,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "no paper command channel".to_string())
        }
    };

    // Parse all risk params / 解析所有風控參數
    let hard_stop_pct = params.get("hard_stop_pct").and_then(|v| v.as_f64());
    let p1_risk_pct = params.get("p1_risk_pct").and_then(|v| v.as_f64());
    let trailing_stop_pct = parse_opt_opt_f64(params, "trailing_stop_pct");
    let trailing_activation_pct = parse_opt_opt_f64(params, "trailing_activation_pct");
    let time_stop_hours = parse_opt_opt_f64(params, "time_stop_hours");
    let atr_multiplier = parse_opt_opt_f64(params, "atr_multiplier");
    let take_profit_pct = parse_opt_opt_f64(params, "take_profit_pct");
    let max_leverage = params.get("max_leverage").and_then(|v| v.as_f64());
    let max_drawdown_pct = params.get("max_drawdown_pct").and_then(|v| v.as_f64());
    let max_same_direction_positions = params
        .get("max_same_direction_positions")
        .and_then(|v| v.as_u64())
        .map(|v| v as usize);
    // RRC-1-A3: H0Gate shadow mode toggle / H0 門控影子模式切換
    let h0_shadow_mode = params.get("h0_shadow_mode").and_then(|v| v.as_bool());
    // PNL-7: agent-tunable dynamic-stop knobs / PNL-7：Agent 可調動態止損參數
    let dynamic_stop_base_ratio = params
        .get("dynamic_stop_base_ratio")
        .and_then(|v| v.as_f64());
    let dynamic_stop_cap_ratio = params
        .get("dynamic_stop_cap_ratio")
        .and_then(|v| v.as_f64());
    let trailing_min_rr_ratio = params.get("trailing_min_rr_ratio").and_then(|v| v.as_f64());
    // Session 12: cost-gate + regime + boot cooldown
    let cost_gate_min_confidence = params
        .get("cost_gate_min_confidence")
        .and_then(|v| v.as_f64());
    let cost_gate_k_base = params.get("cost_gate_k_base").and_then(|v| v.as_f64());
    let cost_gate_k_medium = params.get("cost_gate_k_medium").and_then(|v| v.as_f64());
    let cost_gate_k_small = params.get("cost_gate_k_small").and_then(|v| v.as_f64());
    let adx_trending_threshold = params
        .get("adx_trending_threshold")
        .and_then(|v| v.as_f64());
    let boot_cooldown_ms = params.get("boot_cooldown_ms").and_then(|v| v.as_u64());
    let signals_heartbeat_ms = params.get("signals_heartbeat_ms").and_then(|v| v.as_u64());

    // At least one param must be provided / 至少需要一個參數
    let has_any = hard_stop_pct.is_some()
        || p1_risk_pct.is_some()
        || trailing_stop_pct.is_some()
        || trailing_activation_pct.is_some()
        || time_stop_hours.is_some()
        || atr_multiplier.is_some()
        || take_profit_pct.is_some()
        || max_leverage.is_some()
        || max_drawdown_pct.is_some()
        || max_same_direction_positions.is_some()
        || h0_shadow_mode.is_some()
        || dynamic_stop_base_ratio.is_some()
        || dynamic_stop_cap_ratio.is_some()
        || trailing_min_rr_ratio.is_some()
        || cost_gate_min_confidence.is_some()
        || cost_gate_k_base.is_some()
        || cost_gate_k_medium.is_some()
        || cost_gate_k_small.is_some()
        || adx_trending_threshold.is_some()
        || boot_cooldown_ms.is_some()
        || signals_heartbeat_ms.is_some();
    if !has_any {
        return JsonRpcResponse::error(
            id,
            ERR_INVALID_REQUEST,
            "need at least one risk parameter".to_string(),
        );
    }

    let _ = tx.send(PipelineCommand::UpdateRiskConfig {
        hard_stop_pct,
        trailing_stop_pct,
        trailing_activation_pct,
        time_stop_hours,
        atr_multiplier,
        take_profit_pct,
        max_leverage,
        max_drawdown_pct,
        max_same_direction_positions,
        p1_risk_pct,
        h0_shadow_mode,
        dynamic_stop_base_ratio,
        dynamic_stop_cap_ratio,
        trailing_min_rr_ratio,
        cost_gate_min_confidence,
        cost_gate_k_base,
        cost_gate_k_medium,
        cost_gate_k_small,
        adx_trending_threshold,
        boot_cooldown_ms,
        signals_heartbeat_ms,
    });
    JsonRpcResponse::success(id, serde_json::json!({ "updated": true }))
}

/// ARCH-RC1 1C-3-B: Get Rust-native risk runtime status snapshot.
/// Routes the call through the paper command channel so the response is
/// built from live `TickPipeline` state owned by the event consumer task.
/// ARCH-RC1 1C-3-B：獲取 Rust 原生風控運行時狀態快照。
pub(super) async fn handle_risk_runtime_status(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "paper command channel not configured")
        }
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::GetRiskRuntimeStatus {
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    match tokio::time::timeout(std::time::Duration::from_secs(5), resp_rx).await {
        Ok(Ok(Ok(json_str))) => match serde_json::from_str::<serde_json::Value>(&json_str) {
            Ok(v) => JsonRpcResponse::success(id, v),
            Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("parse status: {e}")),
        },
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INTERNAL, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for event consumer"),
    }
}

/// DYNAMIC-RISK-1: Per-engine Sharpe-aware sizer status snapshot.
/// Routes the call through the selected engine's command channel (same
/// `extract_engine_tx` path as every other per-engine RPC).
/// DYNAMIC-RISK-1：按引擎取動態風險調整器狀態快照。
pub(super) async fn handle_get_dynamic_risk_status(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INTERNAL,
                "engine command channel not configured",
            )
        }
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::GetDynamicRiskStatus {
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    match tokio::time::timeout(std::time::Duration::from_secs(5), resp_rx).await {
        Ok(Ok(Ok(json_str))) => match serde_json::from_str::<serde_json::Value>(&json_str) {
            Ok(v) => JsonRpcResponse::success(id, v),
            Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("parse status: {e}")),
        },
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INTERNAL, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for event consumer"),
    }
}

/// DYNAMIC-RISK-1: Runtime toggle of the per-engine sizer.
/// Transient override — the next TOML hot-reload restores the file's intent.
/// DYNAMIC-RISK-1：運行時切換；下次 TOML 熱重載會還原。
pub(super) async fn handle_set_dynamic_risk_enabled(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    params: &serde_json::Value,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INTERNAL,
                "engine command channel not configured",
            )
        }
    };
    let enabled = match params.get("enabled").and_then(|v| v.as_bool()) {
        Some(v) => v,
        None => {
            return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing or non-bool `enabled`")
        }
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::SetDynamicRiskEnabled {
        enabled,
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    match tokio::time::timeout(std::time::Duration::from_secs(5), resp_rx).await {
        Ok(Ok(Ok(msg))) => JsonRpcResponse::success(id, serde_json::json!({ "result": msg })),
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INTERNAL, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for event consumer"),
    }
}

/// ARCH-RC1 1C-3-B: Clear per-symbol consecutive-loss counters (safe reset,
/// does NOT touch RiskGovernor tier — for governor override see 1C-3-B-2).
/// ARCH-RC1 1C-3-B：清除 per-symbol 連虧計數器（安全重置，不影響 governor tier）。
pub(super) async fn handle_clear_consecutive_losses(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "paper command channel not configured")
        }
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::ClearConsecutiveLosses {
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    match tokio::time::timeout(std::time::Duration::from_secs(5), resp_rx).await {
        Ok(Ok(Ok(msg))) => JsonRpcResponse::success(id, serde_json::json!({ "result": msg })),
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INTERNAL, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for event consumer"),
    }
}

/// ARCH-RC1 1C-3-F: External paper-side order submission. Drives the same
/// IntentProcessor pipeline strategies use (Guardian / Kelly / P1 cap / risk
/// gate / cost gate). On success returns the JSON envelope produced by
/// `TickPipeline::submit_external_order`.
/// ARCH-RC1 1C-3-F：外部紙盤訂單入口 — 與策略走同一條 IntentProcessor 管線。
pub(super) async fn handle_submit_paper_order(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    params: &serde_json::Value,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "paper command channel not configured")
        }
    };
    let symbol = match params.get("symbol").and_then(|v| v.as_str()) {
        Some(s) if !s.is_empty() => s.to_string(),
        _ => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing symbol"),
    };
    let side = match params.get("side").and_then(|v| v.as_str()) {
        Some(s) if !s.is_empty() => s.to_string(),
        _ => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing side"),
    };
    let qty = match params.get("qty").and_then(|v| v.as_f64()) {
        Some(q) if q > 0.0 => q,
        _ => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing/invalid qty"),
    };
    let order_type = params
        .get("order_type")
        .and_then(|v| v.as_str())
        .unwrap_or("market")
        .to_string();
    let limit_price = params.get("limit_price").and_then(|v| v.as_f64());
    let confidence = params
        .get("confidence")
        .and_then(|v| v.as_f64())
        .unwrap_or(1.0);
    let strategy = params
        .get("strategy")
        .and_then(|v| v.as_str())
        .unwrap_or("external")
        .to_string();

    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::SubmitOrder {
        symbol,
        side,
        qty,
        order_type,
        limit_price,
        confidence,
        strategy,
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    match tokio::time::timeout(std::time::Duration::from_secs(5), resp_rx).await {
        Ok(Ok(Ok(json_str))) => match serde_json::from_str::<serde_json::Value>(&json_str) {
            Ok(v) => JsonRpcResponse::success(id, v),
            Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("parse envelope: {e}")),
        },
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INVALID_REQUEST, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for event consumer"),
    }
}

/// ARCH-RC1 1C-3-B-2: Force governor toward more restrictive tier (operator
/// escalation). No 24h cooldown — operator can always be more careful.
/// Writes V014 audit row on success.
/// ARCH-RC1 1C-3-B-2：強制 governor 往更嚴方向（無冷卻 + V014 audit）。
pub(super) async fn handle_force_governor_tighter(
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
pub(super) async fn handle_force_governor_looser(
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

/// RRC-1-E2: Set strategy active/paused via IPC / 通過 IPC 設置策略啟停。
pub(super) async fn handle_set_strategy_active(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    params: &serde_json::Value,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "no paper command channel".to_string())
        }
    };
    let name = match params.get("strategy_name").and_then(|v| v.as_str()) {
        Some(n) => n.to_string(),
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_REQUEST,
                "missing strategy_name".to_string(),
            )
        }
    };
    let active = match params.get("active").and_then(|v| v.as_bool()) {
        Some(a) => a,
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_REQUEST,
                "missing active (bool)".to_string(),
            )
        }
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    let _ = tx.send(PipelineCommand::SetStrategyActive {
        strategy_name: name,
        active,
        response_tx: resp_tx,
    });
    match tokio::time::timeout(std::time::Duration::from_secs(3), resp_rx).await {
        Ok(Ok(Ok(msg))) => {
            JsonRpcResponse::success(id, serde_json::json!({ "ok": true, "detail": msg }))
        }
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INTERNAL, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "channel closed".to_string()),
        Err(_) => {
            JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for engine".to_string())
        }
    }
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
pub(super) async fn handle_set_system_mode_broadcast(
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

// Config IPC helpers (handle_get_config, handle_patch_config) moved to handlers_config.rs.
// Config IPC 輔助（handle_get_config、handle_patch_config）已移至 handlers_config.rs。

// ---------------------------------------------------------------------------
// Scanner observability handlers (IPC-SCAN-1) / 掃描器可觀測性處理器
// ---------------------------------------------------------------------------

/// IPC-SCAN-1a: Return the current active symbol universe.
/// Fail-soft: returns {"status":"uninitialized"} if scanner not wired.
/// IPC-SCAN-1a：返回當前活躍交易對 universe。
/// Fail-soft：掃描器未接線時返回 {"status":"uninitialized"}。
pub(super) fn handle_get_active_symbols(
    id: serde_json::Value,
    registry: &Option<Arc<crate::scanner::registry::SymbolRegistry>>,
) -> JsonRpcResponse {
    let Some(reg) = registry else {
        return JsonRpcResponse::success(
            id,
            serde_json::json!({"status": "uninitialized", "symbols": [], "count": 0}),
        );
    };
    let symbols = reg.snapshot();
    let pinned: Vec<&String> = symbols.iter().filter(|s| reg.is_pinned(s)).collect();
    let dynamic: Vec<&String> = symbols.iter().filter(|s| !reg.is_pinned(s)).collect();
    JsonRpcResponse::success(
        id,
        serde_json::json!({
            "status": "ok",
            "symbols": symbols,
            "count": symbols.len(),
            "pinned": pinned,
            "dynamic": dynamic,
        }),
    )
}

/// IPC-SCAN-1b: Return full scanner status — active universe + last scan summary.
/// Fail-soft: returns {"status":"uninitialized"} if scanner not wired.
/// IPC-SCAN-1b：返回完整掃描器狀態 — 活躍 universe + 最後掃描摘要。
/// Fail-soft：掃描器未接線時返回 {"status":"uninitialized"}。
pub(super) fn handle_get_scanner_status(
    id: serde_json::Value,
    registry: &Option<Arc<crate::scanner::registry::SymbolRegistry>>,
) -> JsonRpcResponse {
    let Some(reg) = registry else {
        return JsonRpcResponse::success(id, serde_json::json!({"status": "uninitialized"}));
    };
    let symbols = reg.snapshot();
    let pinned: Vec<&String> = symbols.iter().filter(|s| reg.is_pinned(s)).collect();
    let dynamic: Vec<&String> = symbols.iter().filter(|s| !reg.is_pinned(s)).collect();

    let last_scan_json = match reg.last_scan() {
        None => serde_json::json!(null),
        Some(scan) => {
            // Top 10 candidates with key fields for GUI display / 前 10 候選供 GUI 顯示
            let top_candidates: Vec<serde_json::Value> = scan
                .candidates
                .iter()
                .take(10)
                .map(|c| {
                    serde_json::json!({
                        "symbol": c.symbol,
                        "final_score": (c.final_score * 10.0).round() / 10.0,
                        "best_strategy": format!("{:?}", c.best_strategy),
                        "sector": c.sector,
                        "edge_bonus": c.edge_bonus,
                        "edge_n": c.edge_n,
                    })
                })
                .collect();
            serde_json::json!({
                "scan_ts_ms": scan.scan_ts_ms,
                "duration_ms": scan.scan_duration_ms,
                "added": scan.added,
                "removed": scan.removed,
                "rejected_count": scan.rejected_count,
                "top_candidates": top_candidates,
            })
        }
    };

    JsonRpcResponse::success(
        id,
        serde_json::json!({
            "status": "ok",
            "active_symbols": symbols,
            "active_count": symbols.len(),
            "pinned": pinned,
            "dynamic": dynamic,
            "last_scan": last_scan_json,
        }),
    )
}
