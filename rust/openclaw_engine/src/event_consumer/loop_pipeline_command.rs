//! Arm E handler — IPC PipelineCommand 派遣，自 loop_handlers.rs 拆出
//! （EVENT-CONSUMER-SPLIT-2，2026-07-03；§九 2000 行治理）。

use std::sync::Arc;

use super::handlers;
use super::loop_handlers::LoopState;
use crate::persistence::DualStateWriter;
use crate::tick_pipeline::{EngineEvent, PipelineCommand, PipelineKind, TickPipeline};

// ─────────────────────────────────────────────────────────────────────────────
// Arm E: IPC paper command dispatch (async — delete_checkpoint().await).
// Arm E：IPC paper 命令派遣（async — delete_checkpoint().await）。
// ─────────────────────────────────────────────────────────────────────────────

/// Arm E handler: dispatch a `PipelineCommand` variant received over the IPC
/// pipeline. Two variants are intercepted at this level:
///   - `DisableEdgePredictorAll` — runs full EDGE-P3-1 Step 7e two-phase
///     commit + V014 audit via `handlers::handle_disable_edge_predictor_all`.
///   - `ResetDrawdownBaseline` — P1-5 A2 in-memory reset + awaited DB DELETE
///     on the checkpoint row so Python only sees success once the persisted
///     row is gone.
/// All other variants flow through `handlers::handle_paper_command`. After
/// command handling, governor risk level is synced to `shared_risk_level` and
/// a CircuitBreakerTripped event is broadcast to peer pipelines if the
/// current level is CircuitBreaker.
/// Arm E handler：派遣 IPC `PipelineCommand`。
///   - `DisableEdgePredictorAll` 走 EDGE-P3-1 Step 7e 兩階段 + V014 審計。
///   - `ResetDrawdownBaseline` 走 P1-5 A2 記憶體重置 + DB DELETE 同步 await。
///   - 其餘走 `handlers::handle_paper_command`。
///   命令處理後同步 governor 風控級別到 `shared_risk_level`；若當前級別為
///   CircuitBreaker，向對等管線廣播事件。
pub(super) async fn handle_pipeline_command(
    cmd: Option<PipelineCommand>,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
    state: &mut LoopState,
    audit_pool: Option<&sqlx::PgPool>,
    shared_risk_level: Option<&Arc<std::sync::atomic::AtomicU8>>,
    cross_engine_tx: Option<&tokio::sync::broadcast::Sender<EngineEvent>>,
    pipeline_kind: PipelineKind,
) {
    let Some(cmd) = cmd else {
        return;
    };
    // EDGE-P3-1 Step 7e: intercept the kill-switch variant so the
    // production path runs the full two-phase commit + V014 audit.
    // All other variants still flow through handle_paper_command.
    // EDGE-P3-1 Step 7e：截獲 kill-switch 變體，跑完整兩階段 + V014 審計；
    // 其餘變體仍走 handle_paper_command。
    match cmd {
        PipelineCommand::DisableEdgePredictorAll {
            operator_token,
            reason,
            response_tx,
        } => {
            let em_for_audit = pipeline.effective_engine_mode();
            handlers::handle_disable_edge_predictor_all(
                operator_token,
                reason,
                response_tx,
                pipeline,
                em_for_audit,
                audit_pool,
            );
        }
        // P1-5 A2: operator-driven drawdown baseline reset.
        // In-memory reset is synchronous; DB row DELETE is awaited
        // inline so Python receives confirmation only AFTER the
        // persisted checkpoint is gone (avoids "looks reset but
        // next restart resurrects old peak" race). If DB write
        // fails, respond Err but keep the in-memory reset — the
        // next writer cycle will try to UPSERT the NEW (= current
        // balance) peak, effectively re-pinning the baseline
        // somewhere safe.
        // P1-5 A2：operator 重置 drawdown 基準。記憶體同步重置、
        // DB DELETE 同步 await，讓 Python 在 row 真正刪除後才收到
        // 確認；DB 失敗時仍保留記憶體重置，下個寫入週期會把新
        // (=當前 balance) peak 重新 UPSERT。
        PipelineCommand::ResetDrawdownBaseline { response_tx } => {
            let em_for_reset = pipeline.effective_engine_mode().to_string();
            let peak_before = pipeline.paper_state.peak_balance();
            let balance_before = pipeline.paper_state.balance();
            pipeline.paper_state.reset_drawdown_baseline();
            let db_result = if let Some(pool) = audit_pool {
                crate::paper_state::checkpoint::delete_checkpoint(pool, &em_for_reset).await
            } else {
                Ok(())
            };
            let reply = match db_result {
                Ok(()) => {
                    tracing::info!(
                        engine_mode = %em_for_reset,
                        peak_before,
                        peak_after = pipeline.paper_state.peak_balance(),
                        balance = balance_before,
                        "P1-5 A2: drawdown baseline reset via IPC \
                         / 已通過 IPC 重置 drawdown 基準"
                    );
                    snapshot_writer.force_write(&pipeline.snapshot());
                    Ok(format!(
                        "reset engine_mode={em_for_reset} \
                         peak_before={peak_before:.2} \
                         peak_after={balance_before:.2}"
                    ))
                }
                Err(e) => {
                    tracing::warn!(
                        engine_mode = %em_for_reset,
                        error = %e,
                        "P1-5 A2: checkpoint DELETE failed (memory already reset) \
                         / checkpoint 刪除失敗（記憶體已重置）"
                    );
                    Err(format!("DB delete failed: {e}"))
                }
            };
            let _ = response_tx.send(reply);
        }
        // P1-03（cold audit pkg B）：cancel-all 須在 async 上下文做真實 REST 呼叫
        // （與 ResetDrawdownBaseline 同模式於此攔截），handle_paper_command 為同步無法
        // await。Paper 模式無 OrderManager → log only（與 handle_close_all paper 分支
        // 對齊）。為什麼不經 execution_authority 門控：cancel 風險遞減（不開新倉），且
        // authority revoke 後（Stop 流 Phase 1）仍須能清掃孤兒掛單。
        PipelineCommand::CancelAllOrders {
            category,
            settle_coin,
        } => {
            match pipeline.cancel_all_order_mgr() {
                None => {
                    // Paper 模式：無交易所客戶端，僅記錄（風險遞減 no-op）。
                    tracing::info!(
                        category = %category,
                        settle_coin = %settle_coin,
                        "IPC cancel_all_orders: no exchange client (paper) — log only \
                         / IPC cancel_all_orders：無交易所客戶端（紙盤）僅記錄"
                    );
                }
                Some(mgr) => {
                    let order_category = match category.as_str() {
                        "linear" => Some(crate::order_manager::OrderCategory::Linear),
                        "spot" => Some(crate::order_manager::OrderCategory::Spot),
                        "inverse" => Some(crate::order_manager::OrderCategory::Inverse),
                        // 未知 category fail-closed：不發未定義範圍的 cancel-all（None）。
                        _ => None,
                    };
                    match order_category {
                        None => {
                            tracing::warn!(
                                category = %category,
                                "IPC cancel_all_orders: unknown category — skipped fail-closed \
                                 / IPC cancel_all_orders：未知 category — fail-closed 跳過"
                            );
                        }
                        Some(order_category) => {
                            // 帳戶範圍 cancel-all（settleCoin），不 per-symbol 迴圈。
                            let settle = if settle_coin.is_empty() {
                                None
                            } else {
                                Some(settle_coin.as_str())
                            };
                            match mgr.cancel_all_scoped(order_category, None, settle).await {
                                Ok(cancelled) => {
                                    tracing::info!(
                                        category = %category,
                                        settle_coin = %settle_coin,
                                        count = cancelled.len(),
                                        "IPC cancel_all_orders dispatched via Rust authority \
                                         / IPC cancel_all_orders 經 Rust authority 派發"
                                    );
                                }
                                Err(e) => {
                                    // Fail-closed 記錄：cancel-all 失敗不重試（mutating 寫，對齊
                                    // CLAUDE.md §四 不加隱藏重試）；上層 Python Stop 流會 append
                                    // error 並維持 fail-closed posture。
                                    tracing::warn!(
                                        category = %category,
                                        settle_coin = %settle_coin,
                                        error = %e,
                                        "IPC cancel_all_orders failed (no retry) \
                                         / IPC cancel_all_orders 失敗（不重試）"
                                    );
                                }
                            }
                        }
                    }
                }
            }
        }
        // Sprint 1B Earn Wave D: asset movement intent must run in the async
        // owner task so IntentProcessor::process_earn_intent can await the
        // EarnRouter gates. This deliberately bypasses SubmitOrder/trading
        // order authority; Earn has its own capability + governance checks.
        PipelineCommand::ProcessEarnIntent {
            coin,
            product_id,
            amount_usdt,
            expected_apr_bps,
            rationale,
            actor_id,
            submitted_ts_ms,
            trace_id,
            response_tx,
        } => {
            handlers::handle_process_earn_intent(
                coin,
                product_id,
                amount_usdt,
                expected_apr_bps,
                rationale,
                actor_id,
                submitted_ts_ms,
                trace_id,
                response_tx,
                pipeline,
            )
            .await;
        }
        // P2-PACKET-C-C4-PIPELINE-WIRE：通知 fail-safe in-band 升級。handler 含 await
        // （exchange sync via stop channel + V114 audit emit），故在此 async 攔截，
        // 與 CancelAllOrders / ResetDrawdownBaseline 同模式（handle_paper_command 同步）。
        // owner task 內跑 SM-04 transition + ATR 注入鎖利 + 交易所雙軌 sync。
        PipelineCommand::NotificationFailsafeEscalate {
            reason,
            response_tx,
        } => {
            handlers::handle_notification_failsafe_escalate(
                reason,
                response_tx,
                pipeline,
                snapshot_writer,
                audit_pool,
            )
            .await;
        }
        other => {
            handlers::handle_paper_command_with_order_map(
                other,
                pipeline,
                snapshot_writer,
                &mut state.pending_orders,
                &mut state.order_id_to_link,
            );
        }
    }
    // Phase 6: sync governor risk level to shared atomic for reconciler.
    // Phase 6：同步 governor 風控級別到共享原子量供對帳器讀取。
    let current_level = pipeline.governance.risk.snapshot_level();
    if let Some(rl) = shared_risk_level {
        rl.store(current_level.value(), std::sync::atomic::Ordering::Relaxed);
    }

    // BLOCKER-2 D6: Broadcast CircuitBreaker event to peer pipelines.
    // BLOCKER-2 D6：向對等管線廣播熔斷事件。
    if current_level == openclaw_core::sm::risk_gov::RiskLevel::CircuitBreaker {
        if let Some(tx) = cross_engine_tx {
            let _ = tx.send(EngineEvent::CircuitBreakerTripped(pipeline_kind));
        }
    }
}
