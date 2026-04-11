//! Event consumer command handlers — extracted from `mod.rs` to keep the
//! main loop file under the 800-line warning threshold.
//! 事件消費者命令處理器 — 從 mod.rs 提取，以保持主循環檔案在 800 行警告線下。
//!
//! MODULE_NOTE (EN): These free functions take whatever subset of pipeline /
//!   bookkeeping state they need by mutable reference and execute one IPC
//!   command. They contain no async work — the parent `tokio::select!` arm
//!   simply forwards the parsed enum here. Splitting them out keeps the loop
//!   readable without restructuring loop state into a struct.
//! MODULE_NOTE (中): 這些自由函式接受所需的 pipeline / bookkeeping 狀態
//!   作為可變引用，執行單一 IPC 命令。父級 `tokio::select!` 分支將解析後的
//!   enum 轉發過來。

use super::types::PendingOrder;
use crate::persistence::StateWriter;
use crate::tick_pipeline::{PipelineCommand, TickPipeline};
use std::collections::HashMap;
use tracing::{info, warn};

/// Apply one PipelineCommand variant to the pipeline. Returns nothing —
/// command outcomes are reported via the optional response_tx oneshot inside
/// each variant.
/// 將一個 PipelineCommand 變體應用到管線；結果通過 oneshot 返回。
pub fn handle_paper_command(
    cmd: PipelineCommand,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut StateWriter,
    pending_orders: &mut HashMap<String, PendingOrder>,
) {
    match cmd {
        PipelineCommand::Pause => {
            pipeline.paper_paused = true;
            info!("paper trading PAUSED via IPC / 紙盤交易已通過 IPC 暫停");
            snapshot_writer.force_write(&pipeline.snapshot());
        }
        PipelineCommand::Resume => {
            pipeline.paper_paused = false;
            // F2 fix: clear session_halted on Resume / 恢復時清除會話暫停標誌
            pipeline.session_halted = false;
            info!("paper trading RESUMED via IPC / 紙盤交易已通過 IPC 恢復");
            snapshot_writer.force_write(&pipeline.snapshot());
        }
        PipelineCommand::CloseAll => {
            // Exchange mode (Demo/Live): dispatch reduce_only market orders via shadow channel.
            // Paper mode: clear paper_state directly.
            // 交易所模式（Demo/Live）：通過 shadow 通道發 reduce_only 市價單。
            // 紙盤模式：直接清除 paper_state。
            let count = pipeline.ipc_close_all();
            info!(count, "IPC close_all_positions / IPC 全部平倉");
            snapshot_writer.force_write(&pipeline.snapshot());
        }
        PipelineCommand::CloseSymbol { symbol, hint_is_long, hint_qty } => {
            // Exchange mode (Demo/Live): dispatch reduce_only market order via shadow channel.
            // Paper mode: close_position_at_market directly.
            // hint_is_long/hint_qty allow closing orphan exchange positions not in paper_state.
            // 交易所模式：發 reduce_only 市價單；紙盤模式：直接平倉。
            // hint 參數允許平掉 paper_state 沒有追蹤的交易所孤兒倉位。
            let found = pipeline.ipc_close_symbol(&symbol, hint_is_long, hint_qty);
            info!(symbol = symbol.as_str(), found, "IPC close_position / IPC 單倉平倉");
            snapshot_writer.force_write(&pipeline.snapshot());
        }
        PipelineCommand::Reset { new_balance } => {
            pipeline.paper_state = crate::paper_state::PaperState::new(new_balance);
            pipeline.stats = crate::tick_pipeline::TickStats::default();
            pipeline.paper_paused = false;
            // F2+F3 fix: clear halt + loss counters on reset / 重置時清除暫停+虧損計數
            pipeline.session_halted = false;
            pipeline.consecutive_losses.clear();
            // P2-4 fix: Clear pending_close_symbols on reset
            pipeline.clear_all_pending_close();
            pending_orders.clear();
            info!(
                balance = format!("{:.2}", new_balance),
                "IPC reset paper state / IPC 重置紙盤狀態"
            );
            snapshot_writer.force_write(&pipeline.snapshot());
        }
        // ── Phase 3b: Strategy parameter IPC commands / 策略參數 IPC 命令 ──
        PipelineCommand::UpdateStrategyParams {
            strategy_name,
            params_json,
            response_tx,
        } => {
            // CONF-D: pre-process params JSON — strip optional "conf_scale" key and
            // apply via Strategy::set_conf_scale, then forward the remaining JSON to
            // the strategy's typed update_params_json. If only conf_scale was sent,
            // skip the typed update entirely (empty object).
            // CONF-D：預處理 — 抽出 conf_scale 套用後再轉發剩餘 JSON。
            let (effective_json, conf_scale_opt): (String, Option<f64>) = match
                serde_json::from_str::<serde_json::Value>(&params_json)
            {
                Ok(serde_json::Value::Object(mut map)) => {
                    let cs = map.remove("conf_scale").and_then(|v| v.as_f64());
                    let stripped = serde_json::Value::Object(map);
                    (stripped.to_string(), cs)
                }
                _ => (params_json.clone(), None),
            };

            let result = match pipeline.orchestrator.find_strategy_mut(&strategy_name) {
                Some(strategy) => {
                    if let Some(scale) = conf_scale_opt {
                        strategy.set_conf_scale(scale);
                    }
                    // If the stripped JSON is just "{}" and we did set conf_scale,
                    // skip the typed update to avoid unnecessary churn / parse errors.
                    let need_typed_update = effective_json != "{}" || conf_scale_opt.is_none();
                    if need_typed_update {
                        match strategy.update_params_json(&effective_json) {
                            Ok(()) => {
                                info!(
                                    strategy = %strategy_name,
                                    conf_scale = ?conf_scale_opt,
                                    "strategy params updated via IPC / 策略參數已通過 IPC 更新"
                                );
                                snapshot_writer.force_write(&pipeline.snapshot());
                                Ok(format!("params updated for {}", strategy_name))
                            }
                            Err(e) => Err(format!("validation failed: {e}")),
                        }
                    } else {
                        info!(
                            strategy = %strategy_name,
                            conf_scale = ?conf_scale_opt,
                            "strategy conf_scale updated via IPC / 策略 conf_scale 已通過 IPC 更新"
                        );
                        snapshot_writer.force_write(&pipeline.snapshot());
                        Ok(format!("conf_scale updated for {}", strategy_name))
                    }
                }
                None => Err(format!("strategy not found: {strategy_name}")),
            };
            let _ = response_tx.send(result);
        }
        PipelineCommand::GetStrategyParams {
            strategy_name,
            response_tx,
        } => {
            let result = match pipeline.orchestrator.find_strategy_mut(&strategy_name) {
                Some(strategy) => Ok(strategy.get_params_json()),
                None => Err(format!("strategy not found: {strategy_name}")),
            };
            let _ = response_tx.send(result);
        }
        PipelineCommand::GetParamRanges {
            strategy_name,
            response_tx,
        } => {
            let result = match pipeline.orchestrator.find_strategy_mut(&strategy_name) {
                Some(strategy) => Ok(strategy.param_ranges_json()),
                None => Err(format!("strategy not found: {strategy_name}")),
            };
            let _ = response_tx.send(result);
        }
        // ── ARCH-RC1 1C-3-B: Risk runtime status + safe counter clear ──
        PipelineCommand::GetRiskRuntimeStatus { response_tx } => {
            let now_ms = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_millis() as u64)
                .unwrap_or(0);
            let snapshot = pipeline.risk_runtime_status_json(now_ms);
            let _ = response_tx.send(Ok(snapshot.to_string()));
        }
        PipelineCommand::ClearConsecutiveLosses { response_tx } => {
            let cleared = pipeline.consecutive_losses.len();
            pipeline.consecutive_losses.clear();
            info!(
                cleared_symbols = cleared,
                "consecutive losses cleared via IPC / 連虧計數器已通過 IPC 清除"
            );
            snapshot_writer.force_write(&pipeline.snapshot());
            let _ = response_tx.send(Ok(format!("cleared {cleared} symbol(s)")));
        }
        // ── ARCH-RC1 1C-3-B-2: Governor manual override (operator escalation) ──
        PipelineCommand::ForceGovernorTighter {
            target_tier,
            reason,
            response_tx,
        } => {
            let result = (|| -> Result<String, String> {
                let target = TickPipeline::parse_risk_level(&target_tier)?;
                let current = pipeline.governance.risk.snapshot_level();
                // Only one step at a time; only toward more restrictive
                // 一次只能往更嚴方向跳一級
                if (target.value() as i32) - (current.value() as i32) != 1 {
                    return Err(format!(
                        "tighter must be exactly one tier above current (current={}, target={})",
                        current, target
                    ));
                }
                pipeline
                    .governance
                    .risk
                    .escalate_to(
                        target,
                        &format!("operator_ipc: {reason}"),
                        openclaw_core::sm::risk_gov::RiskEvent::OperatorEscalation,
                    )
                    .map_err(|e| format!("escalate_to failed: {e}"))?;
                info!(from = %current, to = %target, reason = %reason,
                    "operator-driven governor escalation via IPC");
                snapshot_writer.force_write(&pipeline.snapshot());
                Ok(format!(
                    "{{\"from\":\"{current}\",\"to\":\"{target}\",\"reason\":\"{reason}\"}}"
                ))
            })();
            let _ = response_tx.send(result);
        }
        // ── ARCH-RC1 1C-3-B-2: Governor manual override (operator de-escalation) ──
        PipelineCommand::ForceGovernorLooser {
            target_tier,
            reason_code,
            notes,
            response_tx,
        } => {
            let result = (|| -> Result<String, String> {
                use openclaw_core::sm::risk_gov::RiskLevel;
                // 1. Reason code whitelist (IPC layer enforcement)
                if !TickPipeline::VALID_DE_ESCALATION_REASONS.contains(&reason_code.as_str()) {
                    return Err(format!(
                        "invalid reason_code; must be one of {:?}",
                        TickPipeline::VALID_DE_ESCALATION_REASONS
                    ));
                }
                let target = TickPipeline::parse_risk_level(&target_tier)?;
                let current = pipeline.governance.risk.snapshot_level();

                // 2. Hard lock: cannot unlock CircuitBreaker / ManualReview from IPC.
                //    Operator must edit TOML + restart (deliberate friction).
                // 2. 硬鎖：CB / MR 不能透過 IPC 解開。Operator 必須改 TOML 後重啟。
                if current >= RiskLevel::CircuitBreaker {
                    return Err(format!(
                        "{current} cannot be unlocked via IPC; edit TOML + restart"
                    ));
                }

                // 3. Exactly one step lower (no jumps)
                // 3. 一次只能降一級
                if (current.value() as i32) - (target.value() as i32) != 1 {
                    return Err(format!(
                        "looser must be exactly one tier below current (current={}, target={})",
                        current, target
                    ));
                }

                // 4. 24h IPC-layer cooldown
                // 4. IPC 層 24h 冷卻
                let now_ms = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .map(|d| d.as_millis() as u64)
                    .unwrap_or(0);
                if let Some(last) = pipeline.last_governor_de_escalation_ms() {
                    let elapsed = now_ms.saturating_sub(last);
                    if elapsed < TickPipeline::GOVERNOR_DE_ESCALATION_COOLDOWN_MS {
                        let remaining_ms =
                            TickPipeline::GOVERNOR_DE_ESCALATION_COOLDOWN_MS - elapsed;
                        return Err(format!(
                            "24h cooldown active; {remaining_ms}ms remaining before next manual de-escalation"
                        ));
                    }
                }

                // 5. Delegate to SM (will also enforce its own min_hold_time
                //    + lookup_rule allow-list as defence in depth).
                // 5. 委派給 SM（會同時觸發 SM 內建的 hold_time + lookup_rule 防線）。
                let combined_reason = if notes.is_empty() {
                    format!("operator_ipc:{reason_code}")
                } else {
                    format!("operator_ipc:{reason_code}: {notes}")
                };
                pipeline
                    .governance
                    .risk
                    .de_escalate_to(target, "operator_ipc", &combined_reason)
                    .map_err(|e| format!("de_escalate_to failed: {e}"))?;

                pipeline.set_last_governor_de_escalation_ms(Some(now_ms));
                info!(from = %current, to = %target, reason_code = %reason_code,
                    "operator-driven governor de-escalation via IPC");
                snapshot_writer.force_write(&pipeline.snapshot());
                Ok(format!(
                    "{{\"from\":\"{current}\",\"to\":\"{target}\",\"reason_code\":\"{reason_code}\"}}"
                ))
            })();
            let _ = response_tx.send(result);
        }
        // ── ARCH-RC1 1C-3-F: External paper-side order submission ──
        PipelineCommand::SubmitOrder {
            symbol,
            side,
            qty,
            order_type,
            limit_price,
            confidence,
            strategy,
            response_tx,
        } => {
            let result = (|| -> Result<String, String> {
                let is_long = match side.as_str() {
                    "Buy" | "buy" | "long" | "LONG" => true,
                    "Sell" | "sell" | "short" | "SHORT" => false,
                    other => return Err(format!("invalid side: {other}")),
                };
                let conf = if confidence > 0.0 { confidence } else { 1.0 };
                pipeline.submit_external_order(
                    &symbol,
                    is_long,
                    qty,
                    &order_type,
                    limit_price,
                    conf,
                    &strategy,
                )
            })();
            if result.is_ok() {
                snapshot_writer.force_write(&pipeline.snapshot());
            }
            let _ = response_tx.send(result);
        }
        // RRC-1-E2: Strategy activate/pause / 策略啟停
        PipelineCommand::SetStrategyActive {
            strategy_name,
            active,
            response_tx,
        } => {
            let result = pipeline
                .orchestrator
                .set_strategy_active(&strategy_name, active);
            if result.is_ok() {
                let state = if active { "ACTIVATED" } else { "PAUSED" };
                info!(
                    strategy = %strategy_name, state,
                    "strategy state changed via IPC / 策略狀態已通過 IPC 更改"
                );
                snapshot_writer.force_write(&pipeline.snapshot());
            }
            let _ = response_tx.send(result.map(|was| format!("was_active={was}")));
        }
        PipelineCommand::UpdateRiskConfig {
            hard_stop_pct,
            trailing_stop_pct,
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
        } => {
            // I-09: clamp all numeric setters to sane ranges before applying.
            // I-09：應用前將所有數值設定鉗制到合理範圍。
            // StopConfig fields / 止損配置
            if let Some(v) = hard_stop_pct {
                let v = v.clamp(0.0, 0.5);
                pipeline.paper_state.set_hard_stop_pct(v);
                info!(
                    hard_stop_pct = format!("{:.1}%", v),
                    "hard stop updated / 硬止損已更新"
                );
            }
            if let Some(v) = trailing_stop_pct {
                let v = v.map(|x| x.clamp(0.0, 0.5));
                pipeline.paper_state.set_trailing_stop_pct(v);
                info!(trailing = ?v, "trailing stop updated / 跟蹤止損已更新");
            }
            if let Some(v) = time_stop_hours {
                let v = v.map(|x| x.clamp(0.0, 24.0 * 30.0));
                pipeline.paper_state.set_time_stop_hours(v);
                info!(time_stop = ?v, "time stop updated / 超時止損已更新");
            }
            if let Some(v) = atr_multiplier {
                let v = v.map(|x| x.clamp(0.5, 10.0));
                pipeline.paper_state.set_atr_multiplier(v);
                info!(atr_mult = ?v, "ATR multiplier updated / ATR 乘數已更新");
            }
            if let Some(v) = take_profit_pct {
                let v = v.map(|x| x.clamp(0.0, 10.0));
                pipeline.paper_state.set_take_profit_pct(v);
                info!(take_profit = ?v, "take profit updated / 止盈已更新");
            }
            // GuardianConfig fields / 守護者配置
            let needs_guardian = max_leverage.is_some()
                || max_drawdown_pct.is_some()
                || max_same_direction_positions.is_some();
            if needs_guardian {
                let mut gc = pipeline.intent_processor.guardian_config().clone();
                if let Some(v) = max_leverage {
                    gc.max_leverage = v.clamp(1.0, 100.0);
                }
                if let Some(v) = max_drawdown_pct {
                    gc.max_drawdown_pct = v.clamp(0.0, 100.0);
                }
                if let Some(v) = max_same_direction_positions {
                    gc.max_same_direction_positions = v.clamp(1, 100);
                }
                pipeline.intent_processor.update_guardian_config(gc);
                info!("guardian config updated via IPC / 守護者配置已通過 IPC 更新");
            }
            // P1 risk cap / P1 風險上限
            if let Some(v) = p1_risk_pct {
                let v = v.clamp(0.0, 0.10);
                pipeline.intent_processor.set_p1_risk_pct(v);
                info!(
                    p1_risk_pct = format!("{:.2}%", v * 100.0),
                    "P1 risk cap updated / P1 上限已更新"
                );
            }
            // RRC-1-A3: H0 Gate shadow mode toggle / H0 門控影子模式切換
            if let Some(v) = h0_shadow_mode {
                pipeline.h0_gate.set_shadow_mode(v);
                info!(
                    shadow_mode = v,
                    "H0 gate shadow mode updated / H0 門控影子模式已更新"
                );
            }
            // PNL-7: agent-tunable dynamic-stop knobs (validated in patch fn)
            // PNL-7：Agent 可調的動態止損參數
            let changed = pipeline.intent_processor.patch_dynamic_stop_params(
                dynamic_stop_base_ratio,
                dynamic_stop_cap_ratio,
                trailing_min_rr_ratio,
            );
            if changed > 0 {
                info!(
                    changed,
                    base_ratio = ?dynamic_stop_base_ratio,
                    cap_ratio = ?dynamic_stop_cap_ratio,
                    trailing_min_rr_ratio = ?trailing_min_rr_ratio,
                    "dynamic-stop knobs updated / 動態止損參數已更新"
                );
            }
            // Session 12: cost-gate + regime tunables
            let cg_changed = pipeline.intent_processor.patch_cost_gate_params(
                cost_gate_min_confidence,
                cost_gate_k_base,
                cost_gate_k_medium,
                cost_gate_k_small,
                adx_trending_threshold,
            );
            if cg_changed > 0 {
                info!(
                    cg_changed,
                    min_conf = ?cost_gate_min_confidence,
                    k_base = ?cost_gate_k_base,
                    k_medium = ?cost_gate_k_medium,
                    k_small = ?cost_gate_k_small,
                    adx = ?adx_trending_threshold,
                    "cost-gate / regime params updated"
                );
            }
            // Session 12: PNL-3 boot cooldown via IPC
            if let Some(v) = boot_cooldown_ms {
                let applied = pipeline.set_boot_cooldown_ms(v);
                info!(boot_cooldown_ms = applied, "boot cooldown updated");
            }
            // DB-RUN-1: signals heartbeat
            if let Some(v) = signals_heartbeat_ms {
                let applied = pipeline.set_signals_heartbeat_ms(v);
                info!(signals_heartbeat_ms = applied, "signals heartbeat updated");
            }
            snapshot_writer.force_write(&pipeline.snapshot());
        }
        PipelineCommand::GetOpenPositionSymbols { response_tx } => {
            // Collect symbols with an active open position for scanner removal deferral.
            // 收集有活躍持倉的交易對，供掃描器移除延遲使用。
            let open_symbols: std::collections::HashSet<String> = pipeline
                .paper_state
                .positions()
                .into_iter()
                .map(|pos| pos.symbol.clone())
                .collect();
            let _ = response_tx.send(open_symbols);
        }
        PipelineCommand::AddMode {
            mode,
            balance,
            response_tx,
        } => {
            // Phase 3: Add secondary engine mode at runtime.
            // Phase 3：運行時添加次級引擎模式。
            pipeline.add_mode(mode, balance);
            snapshot_writer.force_write(&pipeline.snapshot());
            let _ = response_tx.send(Ok(format!("mode {} added with balance {:.2}", mode, balance)));
        }
        PipelineCommand::SwitchMode { mode, response_tx } => {
            // Phase 3: Switch primary trading mode with state swap.
            // Phase 3：切換主交易模式，附帶狀態切換。
            pipeline.set_trading_mode(mode);
            // Re-grant paper authorization for the new active mode's GovernanceCore.
            // Without this, the loaded ModeState may have uninitialized auth (created
            // before grant_paper_auth() ran at startup), causing governance_not_authorized.
            // 重新授予新活躍模式的 GovernanceCore 紙盤授權。
            // 不做此步驟，加載的 ModeState 可能包含未初始化授權（在 startup 的
            // grant_paper_auth() 之前創建），導致 governance_not_authorized。
            if let Err(e) = pipeline.grant_paper_auth() {
                warn!(error = %e, "SwitchMode: grant_paper_auth failed / 模式切換後紙盤授權失敗");
            } else {
                info!(new_mode = %mode, "SwitchMode: paper auth re-granted / 模式切換後紙盤授權已重新授予");
            }
            snapshot_writer.force_write(&pipeline.snapshot());
            let _ = response_tx.send(Ok(format!("switched to mode {}", mode)));
        }
        // ── Phase 6: Reconciler auto-contraction ──
        PipelineCommand::ReconcilerEscalate {
            target_tier,
            reason,
            response_tx,
        } => {
            let result = (|| -> Result<String, String> {
                let target = TickPipeline::parse_risk_level(&target_tier)?;
                let current = pipeline.governance.risk.snapshot_level();
                pipeline
                    .governance
                    .risk
                    .reconciler_escalate_to(target, &reason)
                    .map_err(|e| format!("reconciler_escalate_to failed: {e}"))?;
                info!(from = %current, to = %target, reason = %reason,
                    "reconciler auto-escalation (drift detected) / 對帳器自動升級（偵測到漂移）");
                snapshot_writer.force_write(&pipeline.snapshot());
                Ok(format!(
                    "{{\"from\":\"{current}\",\"to\":\"{target}\",\"reason\":\"{reason}\"}}"
                ))
            })();
            let _ = response_tx.send(result);
        }
        PipelineCommand::ReconcilerDeEscalate {
            target_tier,
            reason,
            response_tx,
        } => {
            let result = (|| -> Result<String, String> {
                let target = TickPipeline::parse_risk_level(&target_tier)?;
                let current = pipeline.governance.risk.snapshot_level();
                pipeline
                    .governance
                    .risk
                    .reconciler_de_escalate_to(target, &reason)
                    .map_err(|e| format!("reconciler_de_escalate_to failed: {e}"))?;
                info!(from = %current, to = %target, reason = %reason,
                    "reconciler auto-recovery (clean cycles met) / 對帳器自動恢復（乾淨週期達標）");
                snapshot_writer.force_write(&pipeline.snapshot());
                Ok(format!(
                    "{{\"from\":\"{current}\",\"to\":\"{target}\",\"reason\":\"{reason}\"}}"
                ))
            })();
            let _ = response_tx.send(result);
        }
        // Sync global system mode from Python GUI → engine.
        // 從 Python GUI 同步全局系統模式到引擎。
        PipelineCommand::SetSystemMode { mode, response_tx } => {
            let result = pipeline.set_system_mode(&mode);
            if result.is_ok() {
                snapshot_writer.force_write(&pipeline.snapshot());
            }
            let _ = response_tx.send(result);
        }
    }
}
