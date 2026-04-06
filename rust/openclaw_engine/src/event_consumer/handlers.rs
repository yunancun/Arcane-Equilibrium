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
use crate::tick_pipeline::{PaperSessionCommand, TickPipeline};
use std::collections::HashMap;
use tracing::info;

/// Apply one PaperSessionCommand variant to the pipeline. Returns nothing —
/// command outcomes are reported via the optional response_tx oneshot inside
/// each variant.
/// 將一個 PaperSessionCommand 變體應用到管線；結果通過 oneshot 返回。
pub(super) fn handle_paper_command(
    cmd: PaperSessionCommand,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut StateWriter,
    pending_orders: &mut HashMap<String, PendingOrder>,
) {
    match cmd {
        PaperSessionCommand::Pause => {
            pipeline.paper_paused = true;
            info!("paper trading PAUSED via IPC / 紙盤交易已通過 IPC 暫停");
            snapshot_writer.force_write(&pipeline.snapshot());
        }
        PaperSessionCommand::Resume => {
            pipeline.paper_paused = false;
            // F2 fix: clear session_halted on Resume / 恢復時清除會話暫停標誌
            pipeline.session_halted = false;
            info!("paper trading RESUMED via IPC / 紙盤交易已通過 IPC 恢復");
            snapshot_writer.force_write(&pipeline.snapshot());
        }
        PaperSessionCommand::CloseAll => {
            let closed = pipeline.paper_state.close_all_positions();
            info!(closed = closed, "IPC close_all_positions / IPC 全部平倉");
            snapshot_writer.force_write(&pipeline.snapshot());
        }
        PaperSessionCommand::Reset { new_balance } => {
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
        PaperSessionCommand::UpdateStrategyParams {
            strategy_name,
            params_json,
            response_tx,
        } => {
            let result = match pipeline.orchestrator.find_strategy_mut(&strategy_name) {
                Some(strategy) => match strategy.update_params_json(&params_json) {
                    Ok(()) => {
                        info!(
                            strategy = %strategy_name,
                            "strategy params updated via IPC / 策略參數已通過 IPC 更新"
                        );
                        snapshot_writer.force_write(&pipeline.snapshot());
                        Ok(format!("params updated for {}", strategy_name))
                    }
                    Err(e) => Err(format!("validation failed: {e}")),
                },
                None => Err(format!("strategy not found: {strategy_name}")),
            };
            let _ = response_tx.send(result);
        }
        PaperSessionCommand::GetStrategyParams {
            strategy_name,
            response_tx,
        } => {
            let result = match pipeline.orchestrator.find_strategy_mut(&strategy_name) {
                Some(strategy) => Ok(strategy.get_params_json()),
                None => Err(format!("strategy not found: {strategy_name}")),
            };
            let _ = response_tx.send(result);
        }
        PaperSessionCommand::GetParamRanges {
            strategy_name,
            response_tx,
        } => {
            let result = match pipeline.orchestrator.find_strategy_mut(&strategy_name) {
                Some(strategy) => Ok(strategy.param_ranges_json()),
                None => Err(format!("strategy not found: {strategy_name}")),
            };
            let _ = response_tx.send(result);
        }
        // RRC-1-E2: Strategy activate/pause / 策略啟停
        PaperSessionCommand::SetStrategyActive {
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
        PaperSessionCommand::UpdateRiskConfig {
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
            snapshot_writer.force_write(&pipeline.snapshot());
        }
    }
}
