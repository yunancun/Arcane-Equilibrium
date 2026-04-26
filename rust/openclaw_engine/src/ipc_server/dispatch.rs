//! JSON-RPC request dispatch + small utility handlers shared by every method
//! arm.
//! JSON-RPC 請求分派 + 各 method arm 共用的小型工具 handler。
//!
//! MODULE_NOTE (EN): `dispatch_request` is the central method router for the
//!   IPC server: it parses the wire JSON-RPC frame, validates the protocol
//!   version + method field, emits a per-engine audit log line (MAJOR-5),
//!   and forwards to the right handler. Handlers in this file are the few
//!   that stay self-contained (no DB / no IPC channel work) — `handle_ping`,
//!   `handle_get_build_capabilities`, `handle_reload_config`,
//!   `handle_snapshot_field`, `handle_paper_cmd`, and the
//!   `trigger_live_auth_recheck` fast-path. Every domain handler
//!   (risk / strategy / budget / teacher / governance / etc.) lives in its
//!   own sibling under `handlers/` and is invoked through the
//!   `super::handlers::*` re-export.
//! MODULE_NOTE (中)：`dispatch_request` 是 IPC 伺服器的中央 method 路由：
//!   解析線上 JSON-RPC 框架、驗證協定版本 + method 欄位、寫一行每引擎
//!   審計日誌（MAJOR-5），然後轉給對應 handler。本檔留下的 handler 是少
//!   數不依賴 DB / IPC 通道的工具型函式 — `handle_ping`、
//!   `handle_get_build_capabilities`、`handle_reload_config`、
//!   `handle_snapshot_field`、`handle_paper_cmd` 與
//!   `trigger_live_auth_recheck` 快路徑。每個 domain handler
//!   （risk / strategy / budget / teacher / governance / 等）住在
//!   `handlers/` 下各自的兄弟檔，透過 `super::handlers::*` 取用。
//!
//! Split out of `ipc_server/mod.rs` as part of G5-FUP-IPC-MOD-SPLIT (2026-04-26)
//! together with `connection.rs`. Hot-path semantics (patch_risk_config
//! deep-merge, EDGE-P1b 8 exit_* fields, update_risk_config) preserved
//! byte-identical — pure structural extraction.
//! 於 G5-FUP-IPC-MOD-SPLIT（2026-04-26）連同 `connection.rs` 從
//! `ipc_server/mod.rs` 拆出。Hot-path 語意（patch_risk_config 深合併、
//! EDGE-P1b 8 個 exit_* 欄位、update_risk_config）byte-identical 保留 —
//! 純結構抽取。

use super::engine_routing::{extract_engine_tx, EngineCommandChannels};
use super::handlers::*;
use super::handlers_config::{handle_get_config, handle_patch_config};
use super::protocol::{
    JsonRpcRequest, JsonRpcResponse, ERR_INTERNAL, ERR_INVALID_REQUEST, ERR_METHOD_NOT_FOUND,
};
use super::slots::{BudgetTrackerSlot, HStateCacheSlot, TeacherLoopSlot};
use super::PerEngineRiskStores;
use crate::config::{BudgetConfig, ConfigManager, ConfigStore, LearningConfig, RiskConfig};
use crate::h_state_cache::poller::InvalidationSender;
use crate::tick_pipeline::{PipelineCommand, PipelineSnapshot};
use std::path::{Path, PathBuf};
use std::sync::Arc;

/// Parse and dispatch a single JSON-RPC request line.
/// 解析並分發單條 JSON-RPC 請求。
#[allow(clippy::too_many_arguments)]
pub(crate) async fn dispatch_request(
    line: &str,
    config: &Arc<ConfigManager>,
    data_dir: &Arc<PathBuf>,
    cmd_channels: &EngineCommandChannels,
    budget_slot: &BudgetTrackerSlot,
    teacher_slot: &TeacherLoopSlot,
    risk_stores: &Option<PerEngineRiskStores>,
    learning_store: &Option<Arc<ConfigStore<LearningConfig>>>,
    budget_store: &Option<Arc<ConfigStore<BudgetConfig>>>,
    audit_pool: &Option<sqlx::PgPool>,
    scanner_registry: &Option<Arc<crate::scanner::registry::SymbolRegistry>>,
    strategist_counters: &Option<Arc<crate::strategist_scheduler::CycleCounters>>,
    live_auth_recheck_tx: &Option<tokio::sync::mpsc::Sender<()>>,
    h_state_cache: &HStateCacheSlot,
    h_state_invalidation_tx: &Option<InvalidationSender>,
    // F6 PH5-WIRE-1 RELOAD (2026-04-26): manual reload trigger sender.
    // None → IPC method `reload_edge_estimates` returns
    // `{"accepted": false, "reason": "reloader_disabled"}`.
    // F6：edge 重載手動 trigger sender。None 時 IPC method 回 reloader_disabled。
    edge_reload_sender: &Option<tokio::sync::mpsc::Sender<()>>,
) -> JsonRpcResponse {
    let req: JsonRpcRequest = match serde_json::from_str(line) {
        Ok(r) => r,
        Err(e) => {
            return JsonRpcResponse::error(
                serde_json::Value::Null,
                ERR_INVALID_REQUEST,
                format!("parse error: {e}"),
            );
        }
    };

    let id = req.id.clone().unwrap_or(serde_json::Value::Null);

    // Validate jsonrpc version / 驗證 jsonrpc 版本
    if req.jsonrpc.as_deref() != Some("2.0") {
        return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "jsonrpc must be \"2.0\"");
    }

    let method = match &req.method {
        Some(m) => m.as_str(),
        None => {
            return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing method field");
        }
    };

    // MAJOR-5: Per-engine IPC audit log — every routed request is traced with
    // method + target engine for post-hoc forensics.
    // MAJOR-5：每引擎 IPC 審計日誌 — 記錄 method + 目標引擎以供事後取證。
    {
        let target_engine = req
            .params
            .get("engine")
            .and_then(|v| v.as_str())
            .unwrap_or("(default)");
        tracing::info!(
            ipc_method = method,
            target_engine = target_engine,
            "ipc_audit: dispatching request / IPC 審計：分發請求"
        );
    }

    match method {
        "ping" => handle_ping(id),
        "get_build_capabilities" => handle_get_build_capabilities(id),
        "get_state" => handle_get_state(id, config, data_dir),
        "reload_config" => handle_reload_config(id, config),
        "get_paper_state" => {
            // Phase 4: optional `engine` param routes to per-mode snapshot.
            // Default "paper" for backward compatibility.
            // Phase 4：可選 `engine` 參數路由到每模式快照，默認 "paper" 向後兼容。
            let engine = req
                .params
                .get("engine")
                .and_then(|v| v.as_str())
                .unwrap_or("paper")
                .to_string();
            handle_snapshot_field(id, data_dir, move |s| {
                // Primary mode: return top-level paper_state (authoritative).
                // Secondary modes: look up mode_snapshots.
                // 主模式：返回頂層 paper_state（權威來源）。
                // 次級模式：查找 mode_snapshots。
                if let Some(mode_snap) = s.mode_snapshots.get(&engine) {
                    serde_json::to_value(&mode_snap.paper_state)
                } else if engine == s.pipeline_kind.db_mode() {
                    serde_json::to_value(&s.paper_state)
                } else {
                    // Requested mode not active — return null with metadata.
                    // 請求的模式未啟用 — 返回 null 帶元數據。
                    serde_json::to_value(serde_json::json!({
                        "error": "mode_not_active",
                        "requested": engine,
                        "active_modes": s.mode_snapshots.keys().collect::<Vec<_>>()
                    }))
                }
            })
        }
        "get_mode_snapshot" => {
            // Phase 4: Full ModeStateSnapshot for a specific engine mode.
            // Phase 4：特定引擎模式的完整 ModeStateSnapshot。
            let engine = req
                .params
                .get("engine")
                .and_then(|v| v.as_str())
                .unwrap_or("paper")
                .to_string();
            handle_snapshot_field(id, data_dir, move |s| {
                if let Some(mode_snap) = s.mode_snapshots.get(&engine) {
                    serde_json::to_value(mode_snap)
                } else {
                    serde_json::to_value(serde_json::json!({
                        "error": "mode_not_active",
                        "requested": engine,
                        "active_modes": s.mode_snapshots.keys().collect::<Vec<_>>()
                    }))
                }
            })
        }
        "get_active_modes" => {
            // Phase 4: List all active engine modes.
            // Phase 4：列出所有活躍引擎模式。
            handle_snapshot_field(id, data_dir, |s| {
                serde_json::to_value(s.mode_snapshots.keys().collect::<Vec<_>>())
            })
        }
        "get_latest_prices" => {
            handle_snapshot_field(id, data_dir, |s| serde_json::to_value(&s.latest_prices))
        }
        "get_tick_stats" => handle_snapshot_field(id, data_dir, |s| serde_json::to_value(&s.stats)),
        // ── Pipeline control commands / 管線控制命令 ──
        // 3E-3: Commands accept optional `engine` param ("paper"/"demo"/"live")
        // to route to the correct pipeline. Default: primary pipeline.
        // 3E-3：命令接受可選 `engine` 參數路由到正確管線，默認為主管線。
        "pause_paper" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_paper_cmd(id, tx, PipelineCommand::Pause, "paused")
        }
        "resume_paper" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_paper_cmd(id, tx, PipelineCommand::Resume, "resumed")
        }
        "close_all_positions" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_paper_cmd(id, tx, PipelineCommand::CloseAll, "close_all_sent")
        }
        "close_position" => {
            let symbol = req
                .params
                .get("symbol")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            if symbol.is_empty() {
                return JsonRpcResponse::error(
                    id,
                    ERR_INVALID_REQUEST,
                    "missing required param: symbol",
                );
            }
            // Optional hints: caller (Python GUI route) supplies exchange-side position info
            // so Rust can close orphan positions not tracked in paper_state.
            // 可選 hints：呼叫方（Python GUI 路由）提供交易所側倉位資訊，
            // 使 Rust 可平掉 paper_state 未追蹤的孤兒倉位。
            let hint_is_long = req.params.get("is_long").and_then(|v| v.as_bool());
            let hint_qty = req.params.get("qty").and_then(|v| v.as_f64());
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_paper_cmd(
                id,
                tx,
                PipelineCommand::CloseSymbol {
                    symbol,
                    hint_is_long,
                    hint_qty,
                },
                "close_position_sent",
            )
        }
        "reset_paper_state" => {
            let balance = req
                .params
                .get("new_balance")
                .and_then(|v| v.as_f64())
                .unwrap_or(10_000.0);
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_paper_cmd(
                id,
                tx,
                PipelineCommand::Reset {
                    new_balance: balance,
                },
                "reset_sent",
            )
        }
        // ── Phase 3b: Strategy parameter commands (Optuna → Rust) / 策略參數命令 ──
        "update_strategy_params" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_strategy_param_cmd(id, tx, &req.params, StrategyParamOp::Update).await
        }
        "get_strategy_params" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_strategy_param_cmd(id, tx, &req.params, StrategyParamOp::Get).await
        }
        "get_param_ranges" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_strategy_param_cmd(id, tx, &req.params, StrategyParamOp::Ranges).await
        }
        "update_risk_config" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_update_risk_config(id, tx, &req.params).await
        }
        // ARCH-RC1 1C-3-B: Rust-native risk runtime status + safe counter clear
        "get_risk_runtime_status" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_risk_runtime_status(id, tx).await
        }
        "clear_consecutive_losses" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_clear_consecutive_losses(id, tx).await
        }
        // P1-5 A2: operator-driven drawdown baseline reset — the in-memory
        // path + DB DELETE runs in event_consumer/mod.rs ResetDrawdownBaseline
        // interception. Python FastAPI route MUST front this with operator
        // auth + change_audit_log per Root Principle #8.
        // P1-5 A2：operator 手動重置 drawdown 基準。記憶體重置與 DB DELETE
        // 於 event_consumer/mod.rs 攔截執行；Python 路由須先驗 operator +
        // 寫 change_audit_log（根原則 #8）。
        "reset_drawdown_baseline" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_reset_drawdown_baseline(id, tx).await
        }
        // EDGE-P1b T3 (2026-04-26): emergency rollback for ExitConfig hot-patch.
        // Restores the 7 IPC-writable exit fields to ExitConfig::default()
        // baseline; stale_peak_ms + shadow_enabled remain TOML-only (see
        // handlers/risk.rs::handle_restore_exit_config_defaults docstring).
        // EDGE-P1b T3：ExitConfig hot-patch 緊急回滾；7 個 IPC 可寫 exit 欄位
        // 恢復為 ExitConfig::default() baseline；stale_peak_ms + shadow_enabled
        // 仍是 TOML-only（詳 handlers/risk.rs::handle_restore_exit_config_defaults docstring）。
        "restore_exit_config_defaults" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_restore_exit_config_defaults(id, tx).await
        }
        // DYNAMIC-RISK-1: Per-engine Sharpe-aware sizer status + toggle.
        // DYNAMIC-RISK-1：按引擎動態風險調整器狀態與切換。
        "get_dynamic_risk_status" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_get_dynamic_risk_status(id, tx).await
        }
        "set_dynamic_risk_enabled" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_set_dynamic_risk_enabled(id, tx, &req.params).await
        }
        // ARCH-RC1 1C-3-B-2: governor manual override (operator escalation/de-escalation)
        "force_governor_tier_tighter" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_force_governor_tighter(id, tx, &req.params, audit_pool).await
        }
        "force_governor_tier_looser" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_force_governor_looser(id, tx, &req.params, audit_pool).await
        }
        // ARCH-RC1 1C-3-F: External paper-side order submission (shadow_decision_builder etc.)
        "submit_paper_order" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_submit_paper_order(id, tx, &req.params).await
        }
        // RRC-1-E2: Strategy activate/pause / 策略啟停
        "set_strategy_active" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_set_strategy_active(id, tx, &req.params).await
        }
        // System mode sync from Python GUI / 從 Python GUI 同步系統模式
        // set_system_mode broadcasts to ALL pipelines (not engine-specific)
        // set_system_mode 廣播到所有管線（非引擎特定）
        "set_system_mode" => handle_set_system_mode_broadcast(id, cmd_channels, &req.params).await,
        // Phase 4 (4-00): Dashboard skeleton status aggregation / 儀表板骨架狀態聚合
        "get_phase4_status" => handle_get_phase4_status(id),
        // Phase 4 (4-15): AI budget status / config / AI 預算狀態與配置
        "get_ai_budget_status" => handle_get_ai_budget_status(id, budget_slot).await,
        "update_ai_budget_config" => {
            handle_update_ai_budget_config(id, &req.params, budget_slot).await
        }
        // FIX-57: External AI usage recording (Python Layer2 → Rust sync)
        "record_ai_usage" => handle_record_ai_usage(id, &req.params, budget_slot).await,
        // Phase 4.1: Teacher consumer loop control / Teacher consumer loop 控制
        "set_teacher_loop_enabled" => {
            handle_set_teacher_loop_enabled(id, &req.params, teacher_slot).await
        }
        "get_teacher_loop_status" => handle_get_teacher_loop_status(id, teacher_slot).await,
        // ── ARCH-RC1 1C-2-C / LIVE-P2-1: unified Config IPC endpoints ──
        // ── ARCH-RC1 1C-2-C / LIVE-P2-1：統一 Config IPC 端點 ──
        //
        // get_risk_config / patch_risk_config accept optional `engine` param:
        //   "paper" (default) | "demo" | "live"
        // Route to the corresponding PerEngineRiskStores slot.
        // get_risk_config / patch_risk_config 接受可選的 `engine` 參數路由到對應 store。
        "get_risk_config" => {
            let engine = req
                .params
                .get("engine")
                .and_then(|v| v.as_str())
                .unwrap_or("paper");
            let store: Option<Arc<ConfigStore<RiskConfig>>> =
                risk_stores.as_ref().map(|s| Arc::clone(s.select(engine)));
            handle_get_config(id, &store, &format!("risk/{engine}"))
        }
        "get_learning_config" => handle_get_config(id, learning_store, "learning"),
        "get_budget_config" => handle_get_config(id, budget_store, "budget"),
        "patch_risk_config" => {
            let engine = req
                .params
                .get("engine")
                .and_then(|v| v.as_str())
                .unwrap_or("paper");
            let store: Option<Arc<ConfigStore<RiskConfig>>> =
                risk_stores.as_ref().map(|s| Arc::clone(s.select(engine)));
            handle_patch_config(
                id,
                &store,
                &req.params,
                RiskConfig::validate,
                &format!("risk/{engine}"),
                audit_pool,
            )
        }
        "patch_learning_config" => handle_patch_config(
            id,
            learning_store,
            &req.params,
            LearningConfig::validate,
            "learning",
            audit_pool,
        ),
        "patch_budget_config" => handle_patch_config(
            id,
            budget_store,
            &req.params,
            BudgetConfig::validate,
            "budget",
            audit_pool,
        ),
        // ── Scanner observability (IPC-SCAN-1) ──
        "get_active_symbols" => handle_get_active_symbols(id, scanner_registry),
        "get_scanner_status" => handle_get_scanner_status(id, scanner_registry),
        // ── G3-11 STRATEGIST-CYCLE-OBSERVABILITY-1 (2026-04-25, MVP) ──
        // 取代 GUI footer engine.log tail-parse 的結構化拉取面。
        "get_strategist_cycle_metrics" => {
            handle_get_strategist_cycle_metrics(id, strategist_counters)
        }
        // ── PIPELINE-SLOT-1 Phase 3: Live auth watcher fast-path ──
        // PIPELINE-SLOT-1 Phase 3：Live 授權 watcher 快路徑喚醒
        "trigger_live_auth_recheck" => {
            handle_trigger_live_auth_recheck(id, live_auth_recheck_tx)
        }
        // ── F6 PH5-WIRE-1 RELOAD (2026-04-26) ──
        // Manual edge estimates reload trigger. Advisory fire-and-forget —
        // never returns JSON-RPC error; reports state via accepted/reason
        // payload (mirrors trigger_live_auth_recheck shape). Periodic 1h
        // daemon (env-gated) keeps reloading regardless.
        // F6 PH5-WIRE-1 RELOAD：手動觸發 edge 估計重載。Advisory fire-and-forget —
        // 絕不回 JSON-RPC error，以 accepted / reason payload 表達狀態
        // （對齊 trigger_live_auth_recheck shape）。週期 1h daemon（env-gated）
        // 不論手動觸發是否抵達都繼續運行。
        "reload_edge_estimates" => {
            handle_reload_edge_estimates(id, edge_reload_sender)
        }
        // ── G3-08 H State Gateway Phase 1 (2026-04-26) ──
        // Three reverse-IPC methods backed by `h_state_cache::HStateCache`,
        // gated by `OPENCLAW_H_STATE_GATEWAY=1` (DEFAULT-OFF). When the
        // env-gate is off, the cache slot stays None and all three
        // handlers return a structured `gateway_disabled` payload rather
        // than an error — Python callers render grey-state without raising.
        // 三個反向 IPC method，由 `h_state_cache::HStateCache` 支撐，受
        // `OPENCLAW_H_STATE_GATEWAY=1`（DEFAULT-OFF）控管。env-gate 關時
        // cache slot 保持 None，三 handler 回結構化 `gateway_disabled`
        // payload 而非 error — Python caller 顯示灰燈不 raise。
        "query_h_state_full" => handle_query_h_state_full(id, h_state_cache).await,
        "get_h_state_status" => handle_get_h_state_status(id, h_state_cache).await,
        "invalidate_h_state" => {
            handle_invalidate_h_state(id, &req.params, h_state_invalidation_tx).await
        }
        _ => JsonRpcResponse::error(
            id,
            ERR_METHOD_NOT_FOUND,
            format!("method not found: {method}"),
        ),
    }
}

// ---------------------------------------------------------------------------
// Small utility handlers kept alongside dispatch (used directly by dispatch_request)
// 與 dispatch 同檔的小型工具 handler（被 dispatch_request 直接使用）
// ---------------------------------------------------------------------------

/// Handle paper session command — send to event consumer via channel.
/// 處理紙盤 session 命令 — 通過通道發送到事件消費者。
fn handle_paper_cmd(
    id: serde_json::Value,
    tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    cmd: PipelineCommand,
    result_key: &str,
) -> JsonRpcResponse {
    match tx {
        Some(tx) => match tx.send(cmd) {
            Ok(()) => JsonRpcResponse::success(id, serde_json::json!({ result_key: true })),
            Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}")),
        },
        None => JsonRpcResponse::error(id, ERR_INTERNAL, "paper command channel not configured"),
    }
}

/// Handle ping → pong.
/// 處理 ping → pong。
fn handle_ping(id: serde_json::Value) -> JsonRpcResponse {
    JsonRpcResponse::success(id, serde_json::Value::String("pong".into()))
}

/// PIPELINE-SLOT-1 Phase 3: fast-path wake-up to the Live auth watcher.
///
/// Python's `/api/v1/live/auth/renew` (and revoke) routes call this
/// method fire-and-forget after `_write_signed_live_authorization()` /
/// `_delete_live_authorization_file()` so the watcher reacts in <100ms
/// rather than waiting up to 5s for the next poll tick.
///
/// Response shape (JSON object):
///   * `{"accepted": true}`  — wake-up accepted (watcher will recheck now)
///   * `{"accepted": false, "reason": "coalesced"}` — pending trigger
///     already queued; the existing wake-up will perform the recheck
///   * `{"accepted": false, "reason": "watcher_closed"}` — watcher
///     dropped its receiver (engine shutting down, or failed spawn); the
///     next full restart will rebind
///   * `{"accepted": false, "reason": "watcher_disabled"}` — engine
///     started without a Live pipeline (paper/demo-only build)
///
/// Never returns a JSON-RPC error: this is advisory, not authoritative.
/// The watcher's next poll still converges regardless.
///
/// PIPELINE-SLOT-1 Phase 3：Live 授權 watcher 快路徑喚醒。
///
/// Python `/api/v1/live/auth/renew`（與 revoke）路由於
/// `_write_signed_live_authorization()` /
/// `_delete_live_authorization_file()` 後 fire-and-forget 呼叫此 method，
/// 讓 watcher <100ms 反應，不必等最多 5s 下個 poll。
///
/// 回應（JSON object）：
///   * `{"accepted": true}` — 喚醒已接受，watcher 立刻 recheck
///   * `{"accepted": false, "reason": "coalesced"}` — 已有排隊 trigger
///   * `{"accepted": false, "reason": "watcher_closed"}` — watcher 已 drop receiver
///   * `{"accepted": false, "reason": "watcher_disabled"}` — 引擎無 Live 管線
///
/// 絕不回 JSON-RPC error：此為 advisory、非權威；watcher 下次 poll 仍會收斂。
fn handle_trigger_live_auth_recheck(
    id: serde_json::Value,
    live_auth_recheck_tx: &Option<tokio::sync::mpsc::Sender<()>>,
) -> JsonRpcResponse {
    let Some(tx) = live_auth_recheck_tx else {
        // No watcher wired (paper/demo-only engine) — return structured
        // "disabled" rather than an error, so Python callers can log-and-ignore.
        // 無 watcher 接線（僅 paper/demo 引擎）— 回結構化 disabled 而非錯誤，
        // 讓 Python 呼叫端 log-and-ignore。
        return JsonRpcResponse::success(
            id,
            serde_json::json!({
                "accepted": false,
                "reason": "watcher_disabled"
            }),
        );
    };
    match tx.try_send(()) {
        Ok(()) => JsonRpcResponse::success(
            id,
            serde_json::json!({
                "accepted": true
            }),
        ),
        Err(tokio::sync::mpsc::error::TrySendError::Full(_)) => JsonRpcResponse::success(
            id,
            serde_json::json!({
                "accepted": false,
                "reason": "coalesced"
            }),
        ),
        Err(tokio::sync::mpsc::error::TrySendError::Closed(_)) => JsonRpcResponse::success(
            id,
            serde_json::json!({
                "accepted": false,
                "reason": "watcher_closed"
            }),
        ),
    }
}

/// F6 PH5-WIRE-1 RELOAD (2026-04-26): manual fast-path wake-up to the
/// edge estimates reloader daemon.
///
/// Operator GUI / Python `edge_estimator_scheduler` post-write hook calls
/// this method fire-and-forget after refreshing
/// `settings/edge_estimates*.json` so engine reloads in <1s rather than
/// waiting up to 1h for the periodic interval tick.
///
/// Response shape (JSON object):
///   * `{"accepted": true}` — wake-up accepted (daemon will fan out
///     `PipelineCommand::ReloadEdgeEstimates` to all bound pipelines)
///   * `{"accepted": false, "reason": "coalesced"}` — pending trigger
///     already queued in buffer-1 channel; existing wake-up will reload
///   * `{"accepted": false, "reason": "reloader_closed"}` — daemon
///     dropped its receiver (engine shutting down or daemon panicked)
///   * `{"accepted": false, "reason": "reloader_disabled"}` — engine
///     started without `OPENCLAW_EDGE_RELOAD=1` (DEFAULT-OFF) or no
///     pipeline cmd_tx was bound at spawn time
///
/// Never returns a JSON-RPC error: this is advisory. Periodic 1h tick
/// still converges regardless. Mirrors `handle_trigger_live_auth_recheck`
/// shape (PIPELINE-SLOT-1 Phase 3).
///
/// F6 PH5-WIRE-1 RELOAD：edge 估計 reloader daemon 手動快路徑喚醒。
///
/// 回應（JSON object）：
///   * `{"accepted": true}` — 喚醒已接受
///   * `{"accepted": false, "reason": "coalesced"}` — buffer-1 已有排隊 trigger
///   * `{"accepted": false, "reason": "reloader_closed"}` — daemon 已 drop receiver
///   * `{"accepted": false, "reason": "reloader_disabled"}` — env=0 或 daemon 未 spawn
///
/// 絕不回 JSON-RPC error：advisory，週期 1h tick 不論手動 trigger 抵達都收斂。
fn handle_reload_edge_estimates(
    id: serde_json::Value,
    edge_reload_sender: &Option<tokio::sync::mpsc::Sender<()>>,
) -> JsonRpcResponse {
    let Some(tx) = edge_reload_sender else {
        return JsonRpcResponse::success(
            id,
            serde_json::json!({
                "accepted": false,
                "reason": "reloader_disabled"
            }),
        );
    };
    match tx.try_send(()) {
        Ok(()) => JsonRpcResponse::success(
            id,
            serde_json::json!({
                "accepted": true
            }),
        ),
        Err(tokio::sync::mpsc::error::TrySendError::Full(_)) => JsonRpcResponse::success(
            id,
            serde_json::json!({
                "accepted": false,
                "reason": "coalesced"
            }),
        ),
        Err(tokio::sync::mpsc::error::TrySendError::Closed(_)) => JsonRpcResponse::success(
            id,
            serde_json::json!({
                "accepted": false,
                "reason": "reloader_closed"
            }),
        ),
    }
}

/// EDGE-P3-1 Step 7b: report compile-time build-feature flags to Python probes.
/// Python's `engine_capabilities` endpoint needs the live flag value rather
/// than a static declaration because the Rust engine and Python server are
/// built separately — without this, a production engine compiled with ort
/// would still show `reload_edge_predictor=false` at the probe layer.
///
/// EDGE-P3-1 Step 7b：回報 build-feature 旗標給 Python probe。Rust 引擎與
/// Python 服務器分別 build，故 Python 必須用實時值而非靜態宣告；否則 ort
/// build 也會在 probe 層顯示 `reload_edge_predictor=false`。
fn handle_get_build_capabilities(id: serde_json::Value) -> JsonRpcResponse {
    let edge_predictor_ort = cfg!(feature = "edge_predictor_ort");
    JsonRpcResponse::success(
        id,
        serde_json::json!({
            "edge_predictor_ort": edge_predictor_ort,
            "reload_edge_predictor": edge_predictor_ort,
        }),
    )
}

/// Reload engine config (hot params only).
/// 重載引擎配置（僅熱參數）。
fn handle_reload_config(id: serde_json::Value, config: &Arc<ConfigManager>) -> JsonRpcResponse {
    match config.reload() {
        Ok(()) => JsonRpcResponse::success(
            id,
            serde_json::json!({"reloaded": true, "path": config.file_path().display().to_string()}),
        ),
        Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("reload failed: {e}")),
    }
}

/// Read pipeline_snapshot.json and extract a field (R06-A helper — DRY for 3 handlers).
/// 讀取 pipeline_snapshot.json 並提取欄位（R06-A 輔助函數 — 三個 handler 共用）。
fn handle_snapshot_field<F>(id: serde_json::Value, data_dir: &Path, extract: F) -> JsonRpcResponse
where
    F: FnOnce(&PipelineSnapshot) -> Result<serde_json::Value, serde_json::Error>,
{
    let path = data_dir.join("pipeline_snapshot.json");
    let content = match std::fs::read_to_string(&path) {
        Ok(c) => c,
        Err(e) => {
            return JsonRpcResponse::error(
                id,
                ERR_INTERNAL,
                format!("snapshot file not available: {e} / 快照文件不可用：{e}"),
            );
        }
    };
    let snapshot: PipelineSnapshot = match serde_json::from_str(&content) {
        Ok(s) => s,
        Err(e) => {
            return JsonRpcResponse::error(
                id,
                ERR_INTERNAL,
                format!("snapshot parse error: {e} / 快照解析錯誤：{e}"),
            );
        }
    };
    match extract(&snapshot) {
        Ok(v) => JsonRpcResponse::success(id, v),
        Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("serialize error: {e}")),
    }
}
