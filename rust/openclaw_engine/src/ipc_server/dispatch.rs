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
use super::method_registry::{method_spec, IpcSlotRequirement};
use super::protocol::{
    JsonRpcRequest, JsonRpcResponse, ERR_INTERNAL, ERR_INVALID_REQUEST, ERR_METHOD_NOT_FOUND,
};
use super::slots::{
    AccountManagerSlot, BudgetTrackerSlot, CostEdgeAdvisorSlot, HStateCacheSlot, TeacherLoopSlot,
};
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
    // G3-09 Phase A (2026-04-27): cost_edge_advisor slot. None when env=0
    // or pre-injection — IPC handler returns advisor_disabled payload.
    // G3-09 Phase A：cost_edge_advisor slot。None = env=0 / 未注入 → handler
    // 回 advisor_disabled payload。
    cost_edge_advisor_slot: &CostEdgeAdvisorSlot,
    // LG-2 T3 (2026-05-11): AccountManager slot 供 `query_fee_source` IPC route。
    // None = main_instruments 尚未注入 / 沒任何 exchange binding；handler 回
    // structured uninitialized payload，不爆 error。
    account_manager_slot: &AccountManagerSlot,
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

    // ── PHASE 0 AUTH-1：live-write capability token chokepoint（單一閘，唯一覆蓋全
    //    method 的點）──
    //
    // 為何在 `match method` 之前：grep 證實無單一 engine-resolution 函數所有 live-write
    // 都經過（extract_engine_tx 只服務 PipelineCommand、patch_risk_config 走 risk_stores.
    // select）；唯一覆蓋全 method 的點是 match 前。
    //
    // U-P0-3 engine-skew 釘死：下游 arm 解析 engine 有「兩條路」——
    //   (a) patch_risk_config / get_risk_config 走 `select(unwrap_or("paper"))`；
    //   (b) 其餘 11 個 LIVE_WRITE_METHODS 走 `extract_engine_tx`：engine 在場 → select(engine)，
    //       engine 缺席 → `primary()`（live > demo > paper）。
    // 若 gate 一律 `unwrap_or("paper")`，則「缺 engine 參數的 (b) 類 method」在 live-running
    // 引擎上會被 arm 路由到 LIVE，而 gate 判 paper → 繞過。故 gate 必須鏡像 arm：缺 engine
    // 時對 (b) 類用 `cmd_channels.primary_label()` 解出真實 effective engine。
    //
    // fail-closed：effective engine==live 且 method ∈ LIVE_WRITE_METHODS 時，缺/過期/重放/壞
    // token 一律拒（ERR_INVALID_REQUEST）+ 寫 V014 config_reject row。demo/paper 完全不變。
    // secret 撤除 = kill-switch fail-closed。
    {
        // (a) select-based methods 在缺 engine 時 default paper；(b) extract_engine_tx-based
        // methods 在缺 engine 時走 primary_label()。patch_risk_config 是唯一在 LIVE_WRITE_METHODS
        // 中走 select 的；其餘皆 extract_engine_tx。
        let engine_param = req.params.get("engine").and_then(|v| v.as_str());
        let engine: &str = match engine_param {
            Some(e) => e,
            None if method == "patch_risk_config" => "paper",
            None => cmd_channels.primary_label(),
        };
        if super::live_authz::requires_live_authz(engine, method) {
            // secret 與 IPC HMAC secret 分離檔（OPENCLAW_LIVE_PATCH_SECRET / *_FILE）。
            // None → "" → verify 必失敗（fail-closed kill-switch）。
            let secret =
                crate::secret_env::var_or_file("OPENCLAW_LIVE_PATCH_SECRET").unwrap_or_default();
            let now = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_secs() as i64)
                .unwrap_or(0);
            let ledger = super::live_authz::nonce_ledger();
            if let Err(reject) =
                super::live_authz::check_live_authz(method, &req.params, &secret, now, ledger)
            {
                let reason = reject.code();
                tracing::warn!(
                    ipc_method = method,
                    reject_reason = reason,
                    "live-write authz rejected (fail-closed) / live 寫入授權拒絕（fail-closed）"
                );
                // V014 config_reject 審計 row（fire-and-forget，鏡像 config_patch INSERT）。
                // 不記 token/nonce/secret 任何值（CLAUDE §十一）。source=direct_socket：
                // 到達此 chokepoint 的 live-write 必是繞過 Python 控制面的 socket client
                // （Python operator 路徑會先過 5-gate 再鑄 token）。
                if let Some(pool) = audit_pool.clone() {
                    let method_s = method.to_string();
                    let reason_s = reason.to_string();
                    tokio::spawn(async move {
                        let ts_ms = std::time::SystemTime::now()
                            .duration_since(std::time::UNIX_EPOCH)
                            .map(|d| d.as_millis() as i64)
                            .unwrap_or(0);
                        let payload = serde_json::json!({
                            "method": method_s,
                            "reject_reason": reason_s,
                            "engine": "live",
                        });
                        let res = sqlx::query(
                            "INSERT INTO observability.engine_events \
                             (ts_ms, event_type, source, config_name, old_version, new_version, payload) \
                             VALUES ($1, 'config_reject', 'direct_socket', 'risk/live', NULL, NULL, $2)",
                        )
                        .bind(ts_ms)
                        .bind(&payload)
                        .execute(&pool)
                        .await;
                        if let Err(e) = res {
                            tracing::warn!(error = %e, "V014 config_reject insert failed / V014 拒絕審計寫入失敗");
                        }
                    });
                }
                return JsonRpcResponse::error(
                    id,
                    ERR_INVALID_REQUEST,
                    format!("live_authz_rejected: {reason}"),
                );
            }
        }
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
            handle_paper_cmd(id, &tx, PipelineCommand::Pause, "paused")
        }
        "resume_paper" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_paper_cmd(id, &tx, PipelineCommand::Resume, "resumed")
        }
        "close_all_positions" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_paper_cmd(id, &tx, PipelineCommand::CloseAll, "close_all_sent")
        }
        "cancel_all_orders" => {
            // P1-03（cold audit pkg B）：帳戶範圍 cancel-all，鏡像 close_all_positions。
            // category 預設 linear（目前唯一範圍）；settle_coin 預設 USDT（帳戶範圍）。
            // Fire-and-forget（無 response_tx），由引擎 order authority 發 cancel-all。
            let category = req
                .params
                .get("category")
                .and_then(|v| v.as_str())
                .unwrap_or("linear")
                .to_string();
            let settle_coin = req
                .params
                .get("settle_coin")
                .and_then(|v| v.as_str())
                .unwrap_or("USDT")
                .to_string();
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_paper_cmd(
                id,
                &tx,
                PipelineCommand::CancelAllOrders {
                    category,
                    settle_coin,
                },
                "cancel_all_sent",
            )
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
                &tx,
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
                &tx,
                PipelineCommand::Reset {
                    new_balance: balance,
                },
                "reset_sent",
            )
        }
        // ── Phase 3b: Strategy parameter commands (Optuna → Rust) / 策略參數命令 ──
        "update_strategy_params" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_strategy_param_cmd(id, &tx, &req.params, StrategyParamOp::Update).await
        }
        "get_strategy_params" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_strategy_param_cmd(id, &tx, &req.params, StrategyParamOp::Get).await
        }
        "get_param_ranges" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_strategy_param_cmd(id, &tx, &req.params, StrategyParamOp::Ranges).await
        }
        "update_risk_config" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_update_risk_config(id, &tx, &req.params).await
        }
        // ARCH-RC1 1C-3-B: Rust-native risk runtime status + safe counter clear
        "get_risk_runtime_status" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_risk_runtime_status(id, &tx).await
        }
        "clear_consecutive_losses" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_clear_consecutive_losses(id, &tx).await
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
            handle_reset_drawdown_baseline(id, &tx).await
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
            handle_restore_exit_config_defaults(id, &tx).await
        }
        // DYNAMIC-RISK-1: Per-engine Sharpe-aware sizer status + toggle.
        // DYNAMIC-RISK-1：按引擎動態風險調整器狀態與切換。
        "get_dynamic_risk_status" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_get_dynamic_risk_status(id, &tx).await
        }
        "set_dynamic_risk_enabled" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_set_dynamic_risk_enabled(id, &tx, &req.params).await
        }
        // ARCH-RC1 1C-3-B-2: governor manual override (operator escalation/de-escalation)
        "force_governor_tier_tighter" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_force_governor_tighter(id, &tx, &req.params, audit_pool).await
        }
        "force_governor_tier_looser" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_force_governor_looser(id, &tx, &req.params, audit_pool).await
        }
        // ── SM Option-2 收斂 step (i)（2026-06-02）：治理 lease + 唯讀投影 ──
        // 封閉 governance_lease_bridge.py 的 half-wire（先前 Rust 無對應 arm →
        // ERR_METHOD_NOT_FOUND → Python fail-closed None）。全走 primary pipeline
        // 的 GovernanceCore（cmd round-trip + oneshot），dispatch 只 parse→送→等→format。
        // ADDITIVE / dormant：Python flag OPENCLAW_LEASE_PYTHON_IPC_ENABLED 打開前
        // 不主動呼叫；不碰 execution_authority / live_reserved / 5 道 live-auth gate。
        //
        // 3 個 lease method 的 request/response 契約與 lease_ipc_schema.py 完全一致
        // （E1 親驗：method 名 + param 鍵 + response 形狀）。4 個唯讀投影 method 的
        // 契約由 handlers/governance.rs 各 handler doc 定義，並行 Python work 對齊。
        "governance.acquire_lease" => handle_acquire_lease(id, cmd_channels, &req.params).await,
        "governance.release_lease" => handle_release_lease(id, cmd_channels, &req.params).await,
        "governance.get_lease" => handle_get_lease(id, cmd_channels, &req.params).await,
        "governance.is_authorized" => handle_is_authorized(id, cmd_channels).await,
        "governance.get_status" => handle_get_status(id, cmd_channels).await,
        "governance.list_leases" => handle_list_leases(id, cmd_channels).await,
        "governance.get_risk_state" => handle_get_risk_state(id, cmd_channels).await,
        "stock_etf.get_lane_status"
        | "stock_etf.get_readiness"
        | "stock_etf.get_evidence_status"
        | "stock_etf.get_universe_status"
        | "stock_etf.get_shadow_status"
        | "stock_etf.get_paper_status"
        | "stock_etf.preview_paper_order"
        | "stock_etf.submit_paper_order"
        | "stock_etf.cancel_paper_order"
        | "stock_etf.replace_paper_order"
        | "stock_etf.import_paper_fills"
        | "stock_etf.evaluate_shadow_signal" => {
            debug_assert_eq!(
                method_spec(method).map(|spec| spec.slot),
                Some(IpcSlotRequirement::None)
            );
            handle_stock_etf_ipc(id, method, &req.params)
        }
        // ARCH-RC1 1C-3-F: External paper-side order submission (shadow_decision_builder etc.)
        "submit_paper_order" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_submit_paper_order(id, &tx, &req.params).await
        }
        // Sprint 1B Earn Wave D: Python Earn tab → Rust IPC → owner task
        // IntentProcessor::process_earn_intent. This is intentionally separate
        // from submit_paper_order; Earn is an asset movement, not a trade order.
        "process_earn_intent" => {
            debug_assert_eq!(
                method_spec(method).map(|spec| spec.slot),
                Some(IpcSlotRequirement::None)
            );
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_process_earn_intent(id, &tx, &req.params).await
        }
        // RRC-1-E2: Strategy activate/pause / 策略啟停
        "set_strategy_active" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_set_strategy_active(id, &tx, &req.params).await
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
        "trigger_live_auth_recheck" => handle_trigger_live_auth_recheck(id, live_auth_recheck_tx),
        // ── F6 PH5-WIRE-1 RELOAD (2026-04-26) ──
        // Manual edge estimates reload trigger. Advisory fire-and-forget —
        // never returns JSON-RPC error; reports state via accepted/reason
        // payload (mirrors trigger_live_auth_recheck shape). Periodic 1h
        // daemon (env-gated) keeps reloading regardless.
        // F6 PH5-WIRE-1 RELOAD：手動觸發 edge 估計重載。Advisory fire-and-forget —
        // 絕不回 JSON-RPC error，以 accepted / reason payload 表達狀態
        // （對齊 trigger_live_auth_recheck shape）。週期 1h daemon（env-gated）
        // 不論手動觸發是否抵達都繼續運行。
        "reload_edge_estimates" => handle_reload_edge_estimates(id, edge_reload_sender),
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
        // ── G3-09 Phase A cost_edge_advisor (2026-04-27) ──
        // Single read-only IPC handler for advisor status. Gated by
        // `OPENCLAW_COST_EDGE_ADVISOR=1` (DEFAULT-OFF). When env-gate is off
        // the slot stays None and handler returns structured
        // `Uninitialized` payload (mirrors `gateway_disabled` shape).
        // G3-09 Phase A：cost_edge_advisor 唯讀 status IPC。受
        // `OPENCLAW_COST_EDGE_ADVISOR=1`（DEFAULT-OFF）控管。env-gate 關時
        // slot 為 None，handler 回 `Uninitialized` payload。
        "get_cost_edge_advisor_status" => {
            handle_get_cost_edge_advisor_status(id, cost_edge_advisor_slot).await
        }
        // ── LG-2 T3 (2026-05-11) query_fee_source ──
        // Read-only IPC handler；回 AccountManager.fee_source(symbol) 真值快照
        // 供 healthcheck [45] dual-source compare（Rust enum vs PG proxy 推斷）。
        // slot=None 時回 structured uninitialized payload；params 缺 symbol
        // 時回 invalid_params payload — 對齊 cost_edge_advisor / h_state pattern。
        "query_fee_source" => {
            debug_assert_eq!(
                method_spec(method).map(|spec| spec.slot),
                Some(IpcSlotRequirement::AccountManager)
            );
            handle_query_fee_source(id, &req.params, account_manager_slot).await
        }
        // ── P1-FILL-LINEAGE-MONITOR (2026-05-15) Agent Spine channel counters ──
        // Read-only observability route for healthcheck [55]. Exposes runtime_shadow
        // SPINE_CHANNEL_* counters; drop_total is initial try_send failures, not
        // final lineage loss.
        "get_agent_spine_channel_metrics" => {
            debug_assert_eq!(
                method_spec(method).map(|spec| spec.slot),
                Some(IpcSlotRequirement::None)
            );
            handle_get_agent_spine_channel_metrics(id).await
        }
        // ── Phase 2 demo→live 促升 — EDGE-ANCHORED criteria gate（唯讀）──
        // 唯讀 method：**不在** LIVE_WRITE_METHODS（live_authz.rs:50），故自動
        // token 豁免（不送 cmd / 不改 ConfigStore / 不改 EdgeEstimates，純讀
        // live edge snapshot + 跑純函數判定 + 回 verdict）。Python promote route
        // 在 5-gate 前以此閘廉價拒不合格促升（§2.2 順序 ④）。
        "evaluate_promotion_criteria" => handle_evaluate_promotion_criteria(id, &req.params),
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

// ===========================================================================
// Phase 2 demo→live 促升 — EDGE-ANCHORED criteria gate（唯讀 IPC handler）
// ===========================================================================

/// 延後注入的 EdgeEstimates snapshot 句柄，供
/// `handle_evaluate_promotion_criteria` 自查每 (strategy, symbol) cell。
///
/// 為何用 `OnceLock` 而非穿過 `dispatch_request` 已龐大的參數鏈：鏡像
/// `live_authz::nonce_ledger()`（同檔已立此先例，doc 明示二擇一）。
///
/// 注入的是 **live-grade** `EdgeEstimates` holder（`edge_estimates_live_demo.json`，
/// `EdgeEstimates::load_promotion_edge`），**與 scanner/demo cost_gate 的
/// `edge_estimates.json` holder 分離**（Fix 5，2026-06-17）。為何分離：scanner +
/// Phase 1 `with_edge_store` 讀 demo-grade 快照（`for_engine_mode("demo")`：寬 bar
/// PSR≥0.95/DSR≥0.90/oos_n≥30），但 demo→LIVE 促升 blast radius=25-sym live，必須用
/// live-grade bar（`for_engine_mode("live_demo")`：PSR≥0.975/DSR≥0.95/oos_n≥60/wf≥3），
/// producer 同時寫 `edge_estimates_live_demo.json`。promote 判定吃的是此 live-grade
/// 快照的 leak-free `validation_passed` OOS alpha + freshness（§2.4.B）。
/// 未注入（None）→ handler 回結構化 `criteria_engine_uninitialized` payload
/// （fail-soft，鏡像 cost_edge_advisor / account_manager slot 語意），**不報錯**；
/// route 視之為 Pending（無法判定即不促升，fail-closed）。
static PROMOTION_EDGE_SLOT: std::sync::OnceLock<
    Arc<parking_lot::RwLock<crate::edge_estimates::EdgeEstimates>>,
> = std::sync::OnceLock::new();

/// boot 期注入 EdgeEstimates snapshot 句柄（整合 seam 呼叫一次）。
/// 為何回 bool：`OnceLock::set` 僅首次成功；重複注入回 false（已就緒，no-op）。
///
/// 接線（E1-C 整合 seam，2026-06-17；Fix 5 重接線）：`main.rs` boot 期以
/// `ipc_server::set_promotion_edge_slot`（facade re-export）注入由
/// `EdgeEstimates::load_promotion_edge` 載入的 **live-grade**
/// `edge_estimates_live_demo.json` holder——**獨立**於 scanner 的 demo holder。
/// pub 因 binary crate `openclaw-engine` 經 facade 取用此 lib 內部 setter。
pub fn set_promotion_edge_slot(
    edge: Arc<parking_lot::RwLock<crate::edge_estimates::EdgeEstimates>>,
) -> bool {
    PROMOTION_EDGE_SLOT.set(edge).is_ok()
}

/// cost-wall fallback 常數（Fix 6/7）：對齊 `risk_config_live.toml [slippage]` SSOT。
/// route（Option A）永遠送真值，這些是 defensive-only fallback；測試
/// `promotion_criteria_cost_wall_fallbacks_match_live_ssot` 斷言它們 == live TOML 值，
/// 防 silent drift（即使 route 漏送，cost wall 不會比 live cost_gate 寬鬆）。
const PROMOTION_FALLBACK_SAFETY_MULTIPLIER: f64 = 1.3;
const PROMOTION_FALLBACK_WIN_RATE_FLOOR: f64 = 0.3;
/// fee_bps 缺 → +INF（fail-closed：任何 cell 不清成本牆）。route 永遠送真值。
const PROMOTION_FALLBACK_FEE_BPS: f64 = f64::INFINITY;

/// EDGE-ANCHORED criteria gate（唯讀）。
///
/// 為什麼純唯讀 + fail-closed：促升的唯一可辯護證據 = leak-free 的 OOS alpha
/// 顯著性（`edge_estimates.validation_passed` 鏈）+ 清 live 成本牆，不是 demo PnL
/// （多頭 regime 下正 PnL 是 down-beta 假陽性）。handler **只讀** edge snapshot，
/// 跑 `strategist_scheduler::evaluate_promotion_criteria` 純函數，回 verdict——
/// 不送任何 cmd、不改 ConfigStore、不改 EdgeEstimates。
///
/// 契約（route 傳入 / engine 自查 的分工 — **Option A**，E1 2026-06-17 釘死）：
///   - route 傳入（Python async route 有 DB + 可讀 TOML，是唯一能算 boundary 的層）：
///       `strategy`、`active_symbols`（route 解析
///       `strategy_params_live.allowed_symbols ∩ scanner_config.pinned_symbols`；
///       未設 allowed_symbols → 空陣列 → criteria `Reject("no_active_symbols")`）、
///       soak/fills metric（`demo_soak_wall_clock_ms` / `ms_since_last_param_change`
///       / `attributable_demo_fills`）、`demo_boundary_violation_count`
///       （route 比對 demo soak 窗 realized drawdown vs LIVE 12%/7% envelope，§2.4.D）、
///       `attribution_chain_ok_ratio`（option）、live cost-model 參數
///       （`fee_bps_round_trip` / `cost_gate_safety_multiplier` /
///       `cost_gate_win_rate_floor` 讀 `risk_config_live.toml [slippage]` SSOT）、
///       `edge_ttl_secs`（freshness TTL，同 SSOT）、`tuned_param_names`（promote diff）。
///   - engine 自查（freshness/runtime_field 一致性必須在引擎記憶體內判定）：
///       對每個 `active_symbol` 從 `PROMOTION_EDGE_SLOT` 的 **live-grade** EdgeEstimates
///       snapshot `get_cell(strategy, symbol)` 取 per-cell 數據 + 算 snapshot freshness。
///       此 slot 注入的是 `edge_estimates_live_demo.json`（`for_engine_mode("live_demo")`：
///       PSR≥0.975/DSR≥0.95/oos_n≥60/wf≥3），**非** scanner 的 demo-grade
///       `edge_estimates.json`——故 `validation_passed` 攜帶 **live-grade** 顯著性語意
///       （Fix 5，避免 25-sym live 促升決策建在 demo bar 上）。
///
/// 為何 active_symbols 由 route 傳而非 engine 自查：active-symbol 解析需讀兩份 TOML
/// （strategy_params_live + scanner_config），且 boundary 需查 demo realized drawdown
/// （DB query）——這兩者在 sync IPC handler 內不可達（無 DB pool、無 config reader），
/// route（async + DB + tomllib）是唯一能算齊的層。engine 端只保留「必須與 live
/// cost_gate 看同一記憶體 snapshot」的 edge cell 自查。
///
/// 回應 payload：`{ verdict, tag, reason, strategy, active_count,
///   edge_estimates_fresh, per_cell:[{symbol, present, ...}] }`（route 用 per_cell +
///   active_count + edge_estimates_fresh 組裝 audit `criteria_input_json`）。
fn handle_evaluate_promotion_criteria(
    id: serde_json::Value,
    params: &serde_json::Value,
) -> JsonRpcResponse {
    use crate::strategist_scheduler::{
        evaluate_promotion_criteria, ActiveCellEdge, PromotionCriteriaInput,
    };

    // ── 解析 route 傳入欄（缺必要欄 → fail-closed invalid_request）──
    let strategy = match params.get("strategy").and_then(|v| v.as_str()) {
        Some(s) if !s.is_empty() => s,
        _ => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_REQUEST,
                "evaluate_promotion_criteria: missing/empty 'strategy'",
            );
        }
    };
    let active_symbols: Vec<String> = match params.get("active_symbols").and_then(|v| v.as_array())
    {
        Some(arr) => arr
            .iter()
            .filter_map(|v| v.as_str().map(|s| s.to_string()))
            .collect(),
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_REQUEST,
                "evaluate_promotion_criteria: missing 'active_symbols' array",
            );
        }
    };
    // 數值/布林 metric（缺 → fail-closed 保守值，使判定傾向 Pending/Reject 而非誤過）。
    let demo_soak_wall_clock_ms = params
        .get("demo_soak_wall_clock_ms")
        .and_then(|v| v.as_i64())
        .unwrap_or(0);
    let ms_since_last_param_change = params
        .get("ms_since_last_param_change")
        .and_then(|v| v.as_i64())
        .unwrap_or(0);
    let attributable_demo_fills = params
        .get("attributable_demo_fills")
        .and_then(|v| v.as_i64())
        .unwrap_or(0);
    // boundary 缺 → 1（保守：視為曾越界 → Reject），不可缺欄即誤判 0 越界。
    let demo_boundary_violation_count = params
        .get("demo_boundary_violation_count")
        .and_then(|v| v.as_i64())
        .unwrap_or(1);
    let attribution_chain_ok_ratio = params
        .get("attribution_chain_ok_ratio")
        .and_then(|v| v.as_f64());
    let fee_bps_round_trip = params
        .get("fee_bps_round_trip")
        .and_then(|v| v.as_f64())
        .unwrap_or(PROMOTION_FALLBACK_FEE_BPS); // 缺 → 無限成本牆 → 任何 cell 不過（fail-closed）
                                                // fallback 對齊 risk_config_live.toml SSOT（Fix 6/7）：safety_multiplier=1.3 /
                                                // win_rate_floor=0.3，與 [slippage] live 值一致。route 在 Option A 下永遠送真值
                                                // （見下方契約），這些 fallback 是 defensive-only：若 route 漏送某欄，cost wall 仍以
                                                // live SSOT buffer 量測，不會比 live cost_gate 寬鬆（避免 silent drift）。
    let cost_gate_safety_multiplier = params
        .get("cost_gate_safety_multiplier")
        .and_then(|v| v.as_f64())
        .unwrap_or(PROMOTION_FALLBACK_SAFETY_MULTIPLIER);
    let cost_gate_win_rate_floor = params
        .get("cost_gate_win_rate_floor")
        .and_then(|v| v.as_f64())
        .unwrap_or(PROMOTION_FALLBACK_WIN_RATE_FLOOR);
    let edge_ttl_secs = params
        .get("edge_ttl_secs")
        .and_then(|v| v.as_i64())
        .unwrap_or(0);
    let tuned_param_names: Vec<String> = params
        .get("tuned_param_names")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect()
        })
        .unwrap_or_default();

    // ── engine 自查 live edge snapshot（slot 未注入 → fail-soft uninitialized）──
    let Some(edge_arc) = PROMOTION_EDGE_SLOT.get() else {
        return JsonRpcResponse::success(
            id,
            serde_json::json!({
                "status": "criteria_engine_uninitialized",
                "verdict": "pending",
                "tag": "pending",
                "reason": "criteria_engine_uninitialized",
            }),
        );
    };
    let now_secs = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0);

    // read-lock（sync，parking_lot）：取 snapshot freshness + per-cell 數據後即釋放。
    let (edge_estimates_fresh, active_cells) = {
        let guard = edge_arc.read();
        let fresh = guard.is_fresh(now_secs, edge_ttl_secs);
        let cells: Vec<ActiveCellEdge> = active_symbols
            .iter()
            .map(|sym| match guard.get_cell(strategy, sym) {
                Some(cell) => ActiveCellEdge {
                    symbol: sym.clone(),
                    present: true,
                    validation_passed: cell.validation_passed,
                    validation_reason: cell.validation_reason.clone(),
                    from_runtime_field: cell.from_runtime_field,
                    shrunk_bps: cell.shrunk_bps,
                    win_rate: cell.win_rate,
                    n_trades: cell.n_trades,
                },
                None => ActiveCellEdge {
                    symbol: sym.clone(),
                    present: false,
                    validation_passed: false,
                    validation_reason: "cell_absent".to_string(),
                    from_runtime_field: false,
                    shrunk_bps: 0.0,
                    win_rate: 0.0,
                    n_trades: 0,
                },
            })
            .collect();
        (fresh, cells)
    };

    let input = PromotionCriteriaInput {
        active_cells: active_cells.clone(),
        demo_soak_wall_clock_ms,
        ms_since_last_param_change,
        attributable_demo_fills,
        demo_boundary_violation_count,
        attribution_chain_ok_ratio,
        fee_bps_round_trip,
        cost_gate_safety_multiplier,
        cost_gate_win_rate_floor,
        edge_estimates_fresh,
        tuned_param_names,
    };
    let verdict = evaluate_promotion_criteria(&input);

    // per_cell snapshot 回給 route 寫進 audit `criteria_input_json`（edge-anchored 證據）。
    let per_cell: Vec<serde_json::Value> = active_cells
        .iter()
        .map(|c| {
            serde_json::json!({
                "symbol": c.symbol,
                "present": c.present,
                "validation_passed": c.validation_passed,
                "validation_reason": c.validation_reason,
                "from_runtime_field": c.from_runtime_field,
                "shrunk_bps": c.shrunk_bps,
                "win_rate": c.win_rate,
                "n_trades": c.n_trades,
            })
        })
        .collect();

    JsonRpcResponse::success(
        id,
        serde_json::json!({
            "verdict": verdict.tag(),
            "tag": verdict.tag(),
            "reason": verdict.reason(),
            "strategy": strategy,
            "active_count": active_cells.len(),
            "edge_estimates_fresh": edge_estimates_fresh,
            "per_cell": per_cell,
        }),
    )
}

#[cfg(test)]
mod promotion_criteria_dispatch_tests {
    use super::{
        PROMOTION_FALLBACK_FEE_BPS, PROMOTION_FALLBACK_SAFETY_MULTIPLIER,
        PROMOTION_FALLBACK_WIN_RATE_FLOOR,
    };

    /// Fix 6/7：cost-wall fallback 常數必須 == `risk_config_live.toml [slippage]` SSOT。
    ///
    /// 為什麼 bite：route（Option A）永遠送真 cost 參數，但若未來 route regress 漏送，
    /// handler fallback 接管——此時 fallback 必須與 live cost_gate 用的同一 buffer
    /// （safety_multiplier=1.3 / win_rate_floor=0.3），否則促升閘會以比 live 更寬鬆的
    /// 成本牆放行（silent drift，承 QC adversarial MEDIUM finding）。fee_bps 缺 → +INF
    /// （fail-closed）。本測試 parse live TOML，drift 即紅。
    #[test]
    fn promotion_criteria_cost_wall_fallbacks_match_live_ssot() {
        // include_str! 自編譯期嵌入 live TOML（CARGO_MANIFEST_DIR 相對路徑，跨平台）。
        let toml_src = include_str!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../settings/risk_control_rules/risk_config_live.toml"
        ));
        let parsed: toml::Value = toml::from_str(toml_src).expect("live risk_config TOML parses");
        let slippage = parsed
            .get("slippage")
            .expect("risk_config_live.toml has [slippage]");
        let live_mult = slippage
            .get("cost_gate_safety_multiplier")
            .and_then(|v| v.as_float())
            .expect("[slippage].cost_gate_safety_multiplier is a float");
        let live_floor = slippage
            .get("cost_gate_win_rate_floor")
            .and_then(|v| v.as_float())
            .expect("[slippage].cost_gate_win_rate_floor is a float");

        assert_eq!(
            PROMOTION_FALLBACK_SAFETY_MULTIPLIER, live_mult,
            "cost-wall safety_multiplier fallback drifted from live SSOT"
        );
        assert_eq!(
            PROMOTION_FALLBACK_WIN_RATE_FLOOR, live_floor,
            "cost-wall win_rate_floor fallback drifted from live SSOT"
        );
        // fee_bps fallback 必為 +INF（fail-closed）。
        assert!(
            PROMOTION_FALLBACK_FEE_BPS.is_infinite() && PROMOTION_FALLBACK_FEE_BPS > 0.0,
            "fee_bps fallback must be +INFINITY (fail-closed)"
        );
    }
}
