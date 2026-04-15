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
use crate::persistence::DualStateWriter;
use crate::tick_pipeline::{PipelineCommand, TickPipeline};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use tracing::{info, warn};

/// EDGE-P3-1 Step 7e · sha256-hex of a raw operator token. The raw token is
/// never stored or logged; only the digest lands in the V014 audit payload.
/// EDGE-P3-1 Step 7e：operator_token 的 sha256-hex；原始 token 不入日誌。
fn hash_operator_token(token: &str) -> String {
    let mut h = Sha256::new();
    h.update(token.as_bytes());
    hex::encode(h.finalize())
}

/// EDGE-P3-1 Step 7e · Shared kill-switch body. Extracted so both the
/// production event_consumer/mod.rs interception path AND the in-process
/// `handle_paper_command` direct-dispatch path (used by unit tests) execute
/// the same logic without duplication.
///
/// Two-phase commit when `risk_store` is wired:
///   Stage 1 — build next RiskConfig with `edge_predictor.use_edge_predictor=false`
///             and `write_toml_atomic_fsynced()` it to disk. Disk-first
///             fail-abort: if the write errors we touch nothing in memory,
///             so the kill-switch is NOT silently lost across a crash.
///   Stage 2 — `ConfigStore::apply_patch()` swaps the new config in via
///             ArcSwap and bumps the version. Near-infallible (only poisoned
///             lock). Note: apply_patch will re-persist via the non-fsynced
///             writer on Operator source — redundant but harmless (same bytes).
///   Stage 3 — `EdgePredictorStore::clear_all()` empties the in-memory ONNX
///             slots. Even without Stage 1+2, this alone stops gate lookups
///             until next restart.
///
/// When `risk_store` is `None` the handler degrades to memory-only clear
/// (Stage 3 alone) and tags the audit row `persisted=false`.
///
/// V014 audit row fires forget-and-continue via `tokio::spawn`; only emitted
/// when `audit_pool.is_some()`, so unit tests can pass `None` without a
/// tokio runtime.
///
/// EDGE-P3-1 Step 7e：共用 kill-switch 實作。risk_store 已接線時為兩階段提交
/// （Stage 1 fsync TOML → Stage 2 ArcSwap → Stage 3 clear_all）；未接線時降
/// 級為 memory-only clear（Stage 3）。V014 審計 tokio::spawn fire-and-forget。
fn disable_edge_predictor_all_impl(
    operator_token: &str,
    reason: &str,
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
    db_mode: &'static str,
    audit_pool: Option<&sqlx::PgPool>,
) {
    // U1 authz: length-only check today; HMAC verification hook for later.
    // U1 授權：今日僅長度檢查，HMAC 驗證預留。
    if operator_token.len() < 32 {
        let _ = response_tx.send(Err(
            "operator_token too short (need >=32 chars) / operator_token 過短".into(),
        ));
        return;
    }

    let store = match pipeline.edge_predictor_store() {
        Some(s) => s.clone(),
        None => {
            let _ = response_tx.send(Err(
                "EdgePredictorStore not wired on this engine / 此引擎尚未注入 store".into(),
            ));
            return;
        }
    };

    // ── Stage 1 + 2: persist `use_edge_predictor=false`, then ArcSwap ──
    // Only when risk_store is wired. Absent store → memory-only fallback.
    // Stage 1：risk_store 已接線時先落盤，失敗立即中止且不觸及記憶體。
    let (persisted, persisted_version, stage2_err) = match pipeline.risk_store() {
        Some(risk_store) => {
            let persist_path = risk_store.persist_path().map(|p| p.to_path_buf());
            // Pre-compute the full next config so Stage 1 writes exactly what
            // Stage 2 will swap in. apply_patch repeats the mutation on its own
            // owned clone under the write lock for all-or-nothing semantics.
            // 預先計算 next：Stage 1 寫入的位元組 = Stage 2 即將 swap 的快照。
            let current = risk_store.load();
            let mut next = (*current).clone();
            next.edge_predictor.use_edge_predictor = false;
            if let Err(e) = next.validate() {
                let _ = response_tx.send(Err(format!(
                    "Stage 0 validate failed / 新配置驗證失敗: {e}"
                )));
                return;
            }
            // Stage 1: fsynced TOML write (disk-first fail-abort).
            if let Some(path) = persist_path.as_deref() {
                if let Err(e) =
                    crate::config::write_toml_atomic_fsynced(&next, path)
                {
                    let _ = response_tx.send(Err(format!(
                        "Stage 1 fsync write failed / Stage 1 fsync 寫入失敗: {e}"
                    )));
                    return;
                }
            }
            // Stage 2: ArcSwap apply_patch. Near-infallible (only lock poison).
            match risk_store.apply_patch(
                crate::config::PatchSource::Operator,
                |cfg| {
                    cfg.edge_predictor.use_edge_predictor = false;
                },
                |cfg| cfg.validate(),
            ) {
                Ok(outcome) => (persist_path.is_some(), Some(outcome.version), None),
                Err(e) => {
                    // Disk already has the new value — surface the mismatch
                    // clearly; next successful patch will re-align memory.
                    // 磁碟已是新值：清楚提示記憶體未同步，下次 patch 會自動對齊。
                    warn!(
                        error = %e,
                        "Stage 2 ArcSwap failed after Stage 1 persisted / Stage 1 已落盤但 Stage 2 ArcSwap 失敗"
                    );
                    (persist_path.is_some(), None, Some(e))
                }
            }
        }
        None => (false, None, None),
    };

    // ── Stage 3: memory-only clear of loaded ONNX slots ──
    let cleared = store.clear_all();
    info!(
        cleared,
        persisted,
        persisted_version,
        reason = %reason,
        "EdgePredictor DisableAll / 已禁用所有預測器"
    );

    // ── V014 audit row (fire-and-forget) ──
    if let Some(pool) = audit_pool {
        let pool = pool.clone();
        let token_hash = hash_operator_token(operator_token);
        let reason_owned = reason.to_string();
        let stage2_err_owned = stage2_err.clone();
        tokio::spawn(async move {
            let ts_ms = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_millis() as i64)
                .unwrap_or(0);
            let payload = serde_json::json!({
                "operator_token_hash": token_hash,
                "reason": reason_owned,
                "cleared_slots": cleared,
                "persisted": persisted,
                "engine_mode": db_mode,
                "stage2_error": stage2_err_owned,
            });
            let res = sqlx::query(
                "INSERT INTO observability.engine_events \
                 (ts_ms, event_type, source, config_name, old_version, new_version, payload) \
                 VALUES ($1, 'predictor_disabled_all', 'operator', 'risk_config', NULL, $2, $3)",
            )
            .bind(ts_ms)
            .bind(persisted_version.map(|v| v as i64))
            .bind(&payload)
            .execute(&pool)
            .await;
            if let Err(e) = res {
                warn!(error = %e, "V014 predictor_disabled_all audit insert failed / 審計寫入失敗");
            }
        });
    }

    let msg = if persisted {
        format!(
            "cleared {} predictor slots; use_edge_predictor persisted=false",
            cleared
        )
    } else {
        format!("cleared {} predictor slots (memory-only)", cleared)
    };
    let _ = response_tx.send(Ok(msg));
}

/// EDGE-P3-1 Step 7b · Plumbing-only reload handler. Validates the engine
/// whitelist, calls the stub loader (which always Errs pending ML-MIT #26),
/// and — only if the loader succeeds — swaps the returned predictor into the
/// per-engine `EdgePredictorStore`. Split out of the match arm so unit tests
/// can exercise the validation + stub behaviour without threading an entire
/// `TickPipeline` through a oneshot-send harness.
/// EDGE-P3-1 Step 7b · Plumbing 專用 handler：engine 白名單驗證 → 呼叫存根 loader
/// → 成功才熱換。拆出函式以便單元測試免 oneshot 迴圈即可驗行為。
pub(crate) fn handle_reload_edge_predictor(
    engine: &str,
    strategy: &str,
    path: &std::path::Path,
    pipeline: &mut TickPipeline,
) -> Result<String, String> {
    // Whitelist check — cheap + catches IPC-layer misrouting before we touch
    // the filesystem. Trimmed string match so whitespace-padded strings don't
    // pass silently (Python proxy could send stray \n when shelling out).
    // 白名單檢查（trim 避 Python proxy 殘留換行）。
    match engine.trim() {
        "paper" | "demo" | "live" => {}
        other => {
            return Err(format!(
                "invalid engine '{}' — must be paper|demo|live \
                 / engine 需為 paper|demo|live",
                other
            ));
        }
    }

    // Require a store before we even try to load — if bootstrap hasn't wired
    // one, a successful load would swap into /dev/null.
    // 未接線 store 則直接拒，避免 loader 成功卻熱換進空引用。
    let store = pipeline.edge_predictor_store().ok_or_else(|| {
        "EdgePredictorStore not wired on this engine — check main.rs \
         set_edge_predictor_store() / 此引擎尚未注入 EdgePredictorStore"
            .to_string()
    })?;

    // Stub loader today — unconditional Err until ML-MIT #26. We still go
    // through the call so the error shape is exercised end-to-end.
    // 今日存根：loader 恆返 Err，整條錯誤路徑仍被走過。
    let predictor = crate::edge_predictor::load_predictor_from_path(path)?;
    store.swap(strategy, predictor);

    tracing::info!(
        engine = %engine, strategy = %strategy, path = %path.display(),
        "EdgePredictor reloaded from disk / 已從磁碟熱換預測器"
    );
    Ok(format!(
        "reloaded predictor for {} on {} from {}",
        strategy,
        engine,
        path.display()
    ))
}

/// EDGE-P3-1 Step 7e · Production entry point for the operator kill-switch,
/// called from `event_consumer::mod.rs` after intercepting the variant.
/// EDGE-P3-1 Step 7e：mod.rs 攔截後的生產入口。
pub fn handle_disable_edge_predictor_all(
    operator_token: String,
    reason: String,
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
    db_mode: &'static str,
    audit_pool: Option<&sqlx::PgPool>,
) {
    disable_edge_predictor_all_impl(
        &operator_token,
        &reason,
        response_tx,
        pipeline,
        db_mode,
        audit_pool,
    );
}

/// Apply one PipelineCommand variant to the pipeline. Returns nothing —
/// command outcomes are reported via the optional response_tx oneshot inside
/// each variant.
/// 將一個 PipelineCommand 變體應用到管線；結果通過 oneshot 返回。
pub fn handle_paper_command(
    cmd: PipelineCommand,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
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
            // ORPHAN-ADOPT-1 FUP: preserve the shared positions_mirror handle
            // across reset so the reconciler keeps observing the same Arc.
            // set_positions_mirror clears + rehydrates the shared map from the
            // (empty) positions of the freshly-constructed PaperState.
            // ORPHAN-ADOPT-1 FUP：reset 保留共享 positions_mirror handle，
            // 避免對帳器看到的 Arc 與引擎側分離。
            let shared_mirror = pipeline.paper_state.positions_mirror();
            pipeline.paper_state = crate::paper_state::PaperState::new(new_balance);
            pipeline.paper_state.set_positions_mirror(shared_mirror);
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
            if let Some(v) = trailing_activation_pct {
                // Activation is an absolute % of entry price (same family as trail/hard stop).
                // 啟動閾值與 trail/hard stop 同族：entry 的絕對百分比。
                let v = v.map(|x| x.clamp(0.0, 0.5));
                pipeline.paper_state.set_trailing_activation_pct(v);
                info!(trailing_activation = ?v, "trailing activation threshold updated / 跟蹤啟動閾值已更新");
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
        // 3E-3: AddMode and SwitchMode REMOVED — pipelines spawned at startup
        // with fixed PipelineKind. See EngineCommandChannels for per-pipeline routing.
        // 3E-3：AddMode 和 SwitchMode 已移除 — 管線啟動時固定 PipelineKind。
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
        // EDGE-P3-1 Stage 0 · Hot-swap a predictor for a single strategy.
        // Fails fast if no EdgePredictorStore has been wired onto the pipeline
        // yet — ML-MIT must not silently no-op on an uninitialised engine.
        // EDGE-P3-1 Stage 0 · 熱換單一策略的 predictor；未注入 store 時立即失敗，
        // 避免 ML-MIT 誤以為寫入了未初始化的引擎。
        PipelineCommand::SetEdgePredictorShadow {
            strategy,
            predictor,
            response_tx,
        } => {
            let result = match pipeline.edge_predictor_store() {
                Some(store) => {
                    store.swap(&strategy, predictor.into_arc());
                    info!(strategy = %strategy,
                        "EdgePredictor swapped / 已熱換預測器");
                    Ok(format!("swapped predictor for {}", strategy))
                }
                None => Err(
                    "EdgePredictorStore not wired on this engine — check main.rs \
                     set_edge_predictor_store() / 此引擎尚未注入 EdgePredictorStore".into(),
                ),
            };
            let _ = response_tx.send(result);
        }
        // EDGE-P3-1 Step 7b · Reload a predictor from an on-disk ONNX artifact.
        // Plumbing-only today: `load_predictor_from_path` is a stub that returns
        // Err("onnx_loader_not_wired") so the protocol shape is pinned but the
        // store is never actually mutated until ML-MIT #26 ships a real loader.
        // Defence-in-depth: validate `engine` against paper/demo/live whitelist
        // (primary routing lives in the IPC dispatcher; any misroute to a wrong
        // pipeline is a bug we'd rather see surface as an explicit Err here than
        // silently swap a predictor on the wrong engine).
        // EDGE-P3-1 Step 7b · 從磁碟熱重載 predictor；當前為 plumbing，loader 為存根。
        // engine 作白名單二次防禦。
        PipelineCommand::ReloadEdgePredictor {
            engine,
            strategy,
            path,
            response_tx,
        } => {
            let result = handle_reload_edge_predictor(&engine, &strategy, &path, pipeline);
            let _ = response_tx.send(result);
        }
        // EDGE-P3-1 Stage 0 · Operator kill-switch: clear every loaded model
        // so the cost gate immediately falls back to the JS shrinkage path.
        // EDGE-P3-1 Stage 0 · Operator kill-switch：清空所有已載入模型，cost gate
        // 立即回落 JS shrinkage。
        PipelineCommand::DisableEdgePredictorAll {
            operator_token,
            reason,
            response_tx,
        } => {
            // Production flow intercepts this variant in event_consumer/mod.rs
            // and calls handle_disable_edge_predictor_all with the live
            // db_mode + audit_pool so the V014 row is attributed correctly.
            // This arm stays reachable only for unit-test direct dispatch: we
            // tag the audit mode "paper" and pass no pool (tests skip audit).
            // 生產路徑在 mod.rs 攔截並傳入真實 db_mode/audit_pool；此分支
            // 僅供單元測試 — 標 "paper" 且不傳 pool（避免需要 tokio 執行時）。
            disable_edge_predictor_all_impl(
                &operator_token,
                &reason,
                response_tx,
                pipeline,
                "paper",
                None,
            );
        }
        // EDGE-P3-1 Step 7c · ε-greedy shadow-fill passthrough → writer channel.
        // Mirrors Step 7a pattern: `try_send` off the hot path, Full/Closed is a
        // best-effort drop. `engine_mode` is derived from the pipeline kind —
        // the predictor gate only emits on paper, but we still compute-and-send
        // so the writer's R5 second-line-of-defense (`engine_mode == "paper"`
        // CHECK) has the value to verify instead of guessing.
        // EDGE-P3-1 Step 7c · ε-greedy shadow-fill 轉發至 writer 通道。沿用 Step 7a
        // 模式：try_send 不阻塞熱路徑，Full/Closed best-effort 丟棄。engine_mode
        // 由 pipeline_kind 推導 — gate 僅於 paper 發射，但仍帶值交 writer R5 防線驗證。
        PipelineCommand::EmitShadowFill {
            context_id,
            strategy,
            symbol,
            side,
            features_jsonb,
            prediction_q10,
            prediction_q50,
            prediction_q90,
            cost_bps,
            ts_ms,
        } => {
            match pipeline.shadow_fill_db_tx() {
                Some(tx) => {
                    let msg = crate::database::ShadowFillMsg {
                        context_id: context_id.clone(),
                        ts_ms,
                        engine_mode: pipeline.pipeline_kind.db_mode().to_string(),
                        strategy_name: strategy,
                        symbol: symbol.clone(),
                        side,
                        features_jsonb,
                        predicted_q10: prediction_q10,
                        predicted_q50: prediction_q50,
                        predicted_q90: prediction_q90,
                        cost_bps_at_open: cost_bps,
                    };
                    if let Err(e) = tx.try_send(msg) {
                        tracing::warn!(
                            ctx_id = %context_id, symbol = %symbol, error = %e,
                            "shadow_fill IPC drop — writer channel full/closed \
                             / shadow-fill IPC 丟棄，writer 通道已滿/關閉"
                        );
                    }
                }
                None => {
                    info!(
                        ctx_id = %context_id, symbol = %symbol,
                        "shadow_fill IPC received but writer not wired (fail-soft skip) \
                         / shadow-fill IPC 收到但 writer 未接線（fail-soft 跳過）"
                    );
                }
            }
        }
        // EDGE-P3-1 Step 7a · Passthrough IPC → decision_feature writer channel.
        // External callers (Python backfill/replay tooling) inject training-
        // store rows through the same Rust-direct writer the IntentProcessor
        // producer uses. When the tx is not yet wired (bootstrap race or
        // intentional disable) we log-skip — fail-soft, no panic.
        // `try_send` keeps this off the hot path; Full/Closed drops count as
        // best-effort losses, matching the writer's own backpressure policy.
        // EDGE-P3-1 Step 7a · Passthrough IPC → decision_feature writer 通道。
        // 外部呼叫方走與 IntentProcessor producer 相同的 Rust 直寫路徑。tx 未接線時
        // log 跳過（fail-soft）；try_send 不阻塞熱路徑，Full/Closed drop 計為 best-effort。
        PipelineCommand::DecisionFeatureSnapshot {
            context_id,
            ts_ms,
            engine_mode,
            strategy,
            symbol,
            side,
            feature_schema_version,
            feature_schema_hash,
            feature_definition_hash,
            features_jsonb,
        } => {
            match pipeline.decision_feature_tx() {
                Some(tx) => {
                    let msg = crate::database::DecisionFeatureMsg {
                        context_id: context_id.clone(),
                        ts_ms,
                        engine_mode,
                        strategy_name: strategy,
                        symbol: symbol.clone(),
                        side,
                        feature_schema_version,
                        feature_schema_hash,
                        feature_definition_hash,
                        features_jsonb,
                    };
                    if let Err(e) = tx.try_send(msg) {
                        tracing::warn!(
                            ctx_id = %context_id, symbol = %symbol, error = %e,
                            "decision_feature IPC drop — writer channel full/closed \
                             / 決策特徵 IPC 丟棄，writer 通道已滿/關閉"
                        );
                    }
                }
                None => {
                    info!(
                        ctx_id = %context_id, symbol = %symbol,
                        "decision_feature IPC received but writer not wired (fail-soft skip) \
                         / 決策特徵 IPC 收到但 writer 未接線（fail-soft 跳過）"
                    );
                }
            }
        }
        // ORPHAN-ADOPT-1 Phase 2A · Adopt an exchange-reported orphan position
        // into paper_state. `paper_state.adopt_orphan` is idempotent; false
        // means the adoption was a no-op (same-direction position already
        // present) — safe to treat as success from the reconciler's POV
        // since the side-car mirror will now reflect the tracked position.
        // ORPHAN-ADOPT-1 Phase 2A · 接管交易所孤兒倉位至 paper_state；
        // adopt_orphan 冪等，false 表同向已存在 — 對 reconciler 視角視同成功。
        PipelineCommand::AdoptOrphan {
            symbol,
            is_long,
            qty,
            entry_price,
            ts_ms,
        } => {
            let inserted = pipeline
                .paper_state
                .adopt_orphan(&symbol, is_long, qty, entry_price, ts_ms);
            info!(
                symbol = symbol.as_str(),
                is_long,
                qty,
                entry_price,
                inserted,
                "IPC adopt_orphan / IPC 孤兒接管"
            );
            if inserted {
                snapshot_writer.force_write(&pipeline.snapshot());
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::persistence::StateWriter;
    use crate::tick_pipeline::TickPipeline;

    /// EN: Helper — build a DualStateWriter pointing at a temp directory.
    /// 中文: 輔助函式 — 建構指向暫存目錄的 DualStateWriter。
    fn make_writer(dir: &std::path::Path) -> DualStateWriter {
        let path = dir.join("test_snapshot.json");
        let primary = StateWriter::new(&path, 0); // interval=0 → always write
        DualStateWriter::new(primary, None)
    }

    // ── Pause / Resume / Reset ──

    /// EN: Pause sets paper_paused=true.
    /// 中文: Pause 設定 paper_paused=true。
    #[test]
    fn test_pause_sets_flag() {
        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();
        assert!(!pipeline.paper_paused);
        handle_paper_command(PipelineCommand::Pause, &mut pipeline, &mut writer, &mut pending);
        assert!(pipeline.paper_paused);
    }

    /// EN: Resume clears both paper_paused and session_halted.
    /// 中文: Resume 同時清除 paper_paused 和 session_halted。
    #[test]
    fn test_resume_clears_pause_and_halt() {
        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.paper_paused = true;
        pipeline.session_halted = true;
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();
        handle_paper_command(PipelineCommand::Resume, &mut pipeline, &mut writer, &mut pending);
        assert!(!pipeline.paper_paused);
        assert!(!pipeline.session_halted);
    }

    /// EN: Reset restores balance, clears paused+halted+consecutive_losses+pending.
    /// 中文: Reset 恢復餘額、清除暫停+中止+連虧+掛單。
    #[test]
    fn test_reset_clears_all_state() {
        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.paper_paused = true;
        pipeline.session_halted = true;
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();
        pending.insert("order1".to_string(), PendingOrder {
            order_link_id: "order1".into(),
            symbol: "BTCUSDT".into(),
            is_long: true,
            qty: 0.01,
            strategy: "test".into(),
            sent_ts_ms: 1000,
            cum_filled_qty: 0.0,
            is_close: false,
        });
        handle_paper_command(
            PipelineCommand::Reset { new_balance: 5000.0 },
            &mut pipeline, &mut writer, &mut pending,
        );
        assert!(!pipeline.paper_paused);
        assert!(!pipeline.session_halted);
        assert!(pending.is_empty());
        assert!((pipeline.paper_state.balance() - 5000.0).abs() < 1e-9);
    }

    // ── ClearConsecutiveLosses ──

    /// EN: ClearConsecutiveLosses empties the map and responds with count.
    /// 中文: ClearConsecutiveLosses 清空映射並回應清除數量。
    #[test]
    fn test_clear_consecutive_losses() {
        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.consecutive_losses.insert("BTCUSDT".to_string(), 3);
        pipeline.consecutive_losses.insert("ETHUSDT".to_string(), 5);
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();
        let (tx, rx) = tokio::sync::oneshot::channel();
        handle_paper_command(
            PipelineCommand::ClearConsecutiveLosses { response_tx: tx },
            &mut pipeline, &mut writer, &mut pending,
        );
        assert!(pipeline.consecutive_losses.is_empty());
        let resp = rx.blocking_recv().unwrap();
        assert!(resp.unwrap().contains("2 symbol"));
    }

    // ── GetOpenPositionSymbols ──

    /// EN: GetOpenPositionSymbols returns empty set when no positions.
    /// 中文: 無持倉時返回空集合。
    #[test]
    fn test_get_open_position_symbols_empty() {
        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();
        let (tx, rx) = tokio::sync::oneshot::channel();
        handle_paper_command(
            PipelineCommand::GetOpenPositionSymbols { response_tx: tx },
            &mut pipeline, &mut writer, &mut pending,
        );
        let symbols = rx.blocking_recv().unwrap();
        assert!(symbols.is_empty());
    }

    // ── UpdateStrategyParams: conf_scale extraction ──

    /// EN: UpdateStrategyParams with only conf_scale skips typed update.
    /// 中文: 僅含 conf_scale 時跳過類型化更新。
    #[test]
    fn test_conf_scale_extraction_logic() {
        // Test the JSON parsing logic directly (same as handler lines 89-98)
        let params_json = r#"{"conf_scale": 1.5}"#;
        let (effective_json, conf_scale_opt): (String, Option<f64>) = match
            serde_json::from_str::<serde_json::Value>(params_json)
        {
            Ok(serde_json::Value::Object(mut map)) => {
                let cs = map.remove("conf_scale").and_then(|v| v.as_f64());
                let stripped = serde_json::Value::Object(map);
                (stripped.to_string(), cs)
            }
            _ => (params_json.to_string(), None),
        };
        assert_eq!(effective_json, "{}");
        assert_eq!(conf_scale_opt, Some(1.5));
    }

    /// EN: UpdateStrategyParams with conf_scale + other fields preserves both.
    /// 中文: conf_scale + 其他欄位時兩者皆保留。
    #[test]
    fn test_conf_scale_mixed_with_other_params() {
        let params_json = r#"{"conf_scale": 2.0, "fast_period": 10}"#;
        let (effective_json, conf_scale_opt): (String, Option<f64>) = match
            serde_json::from_str::<serde_json::Value>(params_json)
        {
            Ok(serde_json::Value::Object(mut map)) => {
                let cs = map.remove("conf_scale").and_then(|v| v.as_f64());
                let stripped = serde_json::Value::Object(map);
                (stripped.to_string(), cs)
            }
            _ => (params_json.to_string(), None),
        };
        assert_eq!(conf_scale_opt, Some(2.0));
        let parsed: serde_json::Value = serde_json::from_str(&effective_json).unwrap();
        assert_eq!(parsed["fast_period"], 10);
        // conf_scale should be stripped
        assert!(parsed.get("conf_scale").is_none());
    }

    /// EN: Invalid JSON falls back to original string with None conf_scale.
    /// 中文: 無效 JSON 回退為原始字串，conf_scale 為 None。
    #[test]
    fn test_conf_scale_invalid_json_fallback() {
        let params_json = "not-json";
        let (effective_json, conf_scale_opt): (String, Option<f64>) = match
            serde_json::from_str::<serde_json::Value>(params_json)
        {
            Ok(serde_json::Value::Object(mut map)) => {
                let cs = map.remove("conf_scale").and_then(|v| v.as_f64());
                let stripped = serde_json::Value::Object(map);
                (stripped.to_string(), cs)
            }
            _ => (params_json.to_string(), None),
        };
        assert_eq!(effective_json, "not-json");
        assert!(conf_scale_opt.is_none());
    }

    // ── EDGE-P3-1 Stage 0 handlers ─────────────────────────────────────

    /// EN: SetEdgePredictorShadow returns Err when no store is wired.
    /// Protects ML-MIT from silently no-oping on an uninitialised engine.
    /// 中文: 未注入 store 時 SetEdgePredictorShadow 回 Err；避免 ML-MIT
    /// 以為熱換成功但其實無人接收。
    #[test]
    fn test_set_edge_predictor_shadow_fails_without_store() {
        use crate::edge_predictor::{BoxedEdgePredictor, null_backend::NullPredictor};

        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();

        let (tx, rx) = tokio::sync::oneshot::channel();
        let predictor: std::sync::Arc<dyn crate::edge_predictor::EdgePredictor + Send + Sync> =
            std::sync::Arc::new(NullPredictor::new());
        handle_paper_command(
            PipelineCommand::SetEdgePredictorShadow {
                strategy: "ma_crossover".into(),
                predictor: BoxedEdgePredictor::new(predictor),
                response_tx: tx,
            },
            &mut pipeline,
            &mut writer,
            &mut pending,
        );
        let result = rx.blocking_recv().unwrap();
        assert!(result.is_err(), "expected Err without wired store, got Ok");
        let msg = result.unwrap_err();
        assert!(msg.contains("not wired"), "err should mention not-wired: {}", msg);
    }

    /// EN: SetEdgePredictorShadow succeeds after store is wired; load_for
    /// returns the swapped predictor.
    /// 中文: 注入 store 後 SetEdgePredictorShadow 成功；load_for 返回剛熱換的 predictor。
    #[test]
    fn test_set_edge_predictor_shadow_succeeds_after_wire() {
        use crate::edge_predictor::{
            BoxedEdgePredictor, EdgePredictorStore, null_backend::NullPredictor,
        };

        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let store = std::sync::Arc::new(EdgePredictorStore::new());
        pipeline.set_edge_predictor_store(std::sync::Arc::clone(&store));
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();

        let (tx, rx) = tokio::sync::oneshot::channel();
        let predictor: std::sync::Arc<dyn crate::edge_predictor::EdgePredictor + Send + Sync> =
            std::sync::Arc::new(NullPredictor::new());
        handle_paper_command(
            PipelineCommand::SetEdgePredictorShadow {
                strategy: "ma_crossover".into(),
                predictor: BoxedEdgePredictor::new(predictor),
                response_tx: tx,
            },
            &mut pipeline,
            &mut writer,
            &mut pending,
        );
        let result = rx.blocking_recv().unwrap();
        assert!(result.is_ok(), "expected Ok, got {:?}", result);
        assert!(store.load_for("ma_crossover").is_some(),
            "predictor should be loaded after swap");
    }

    /// EN: DisableEdgePredictorAll clears every registered slot.
    /// 中文: DisableEdgePredictorAll 清空所有已註冊槽位。
    #[test]
    fn test_disable_edge_predictor_all_clears_slots() {
        use crate::edge_predictor::{EdgePredictorStore, null_backend::NullPredictor};

        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let store = std::sync::Arc::new(EdgePredictorStore::new());
        // Seed 3 strategies with live predictors / 預先載入 3 個策略。
        for s in ["ma_crossover", "bb_reversion", "grid_trading"] {
            let p: std::sync::Arc<dyn crate::edge_predictor::EdgePredictor + Send + Sync> =
                std::sync::Arc::new(NullPredictor::new());
            store.swap(s, p);
        }
        pipeline.set_edge_predictor_store(std::sync::Arc::clone(&store));
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();

        let (tx, rx) = tokio::sync::oneshot::channel();
        handle_paper_command(
            PipelineCommand::DisableEdgePredictorAll {
                operator_token: "test-token-12345678901234567890abcdef".into(),
                reason: "unit test".into(),
                response_tx: tx,
            },
            &mut pipeline,
            &mut writer,
            &mut pending,
        );
        let result = rx.blocking_recv().unwrap();
        assert!(result.is_ok());
        let msg = result.unwrap();
        assert!(msg.contains("cleared 3"), "msg should report cleared count: {}", msg);
        // All slots now return None on load_for / 所有槽位 load_for 返回 None。
        for s in ["ma_crossover", "bb_reversion", "grid_trading"] {
            assert!(store.load_for(s).is_none(), "slot {} still loaded", s);
        }
    }

    /// EDGE-P3-1 Step 7e · EN: operator_token shorter than 32 chars must
    ///   fail-closed with an explanatory error; no memory/disk side effects.
    /// EDGE-P3-1 Step 7e · 中文：operator_token < 32 必須 fail-closed，
    ///   無記憶體或磁碟副作用。
    #[test]
    fn test_handle_disable_edge_predictor_all_rejects_short_token() {
        use crate::edge_predictor::{EdgePredictorStore, null_backend::NullPredictor};

        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let store = std::sync::Arc::new(EdgePredictorStore::new());
        let p: std::sync::Arc<dyn crate::edge_predictor::EdgePredictor + Send + Sync> =
            std::sync::Arc::new(NullPredictor::new());
        store.swap("ma_crossover", p);
        pipeline.set_edge_predictor_store(std::sync::Arc::clone(&store));

        let (tx, rx) = tokio::sync::oneshot::channel();
        super::handle_disable_edge_predictor_all(
            "too-short".into(),
            "unit test short-token".into(),
            tx,
            &mut pipeline,
            "paper",
            None,
        );
        let result = rx.blocking_recv().unwrap();
        assert!(result.is_err(), "short token must be rejected");
        let err = result.unwrap_err();
        assert!(err.contains("too short"), "err msg: {}", err);
        // Slot untouched on reject / 拒絕時槽位不應被清。
        assert!(store.load_for("ma_crossover").is_some());
    }

    /// EDGE-P3-1 Step 7e · EN: when risk_store is NOT wired the handler
    ///   degrades to memory-only clear and reports "memory-only" in the
    ///   success message. No disk write attempted.
    /// EDGE-P3-1 Step 7e · 中文：risk_store 未接線時降級為 memory-only clear，
    ///   回應訊息含 "memory-only"；不嘗試寫磁碟。
    #[test]
    fn test_handle_disable_edge_predictor_all_memory_only_when_store_unwired() {
        use crate::edge_predictor::{EdgePredictorStore, null_backend::NullPredictor};

        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let store = std::sync::Arc::new(EdgePredictorStore::new());
        let p: std::sync::Arc<dyn crate::edge_predictor::EdgePredictor + Send + Sync> =
            std::sync::Arc::new(NullPredictor::new());
        store.swap("ma_crossover", p);
        pipeline.set_edge_predictor_store(std::sync::Arc::clone(&store));
        // Deliberately NOT calling pipeline.set_risk_store(...) so risk_store()
        // stays None → handler hits memory-only branch.

        let (tx, rx) = tokio::sync::oneshot::channel();
        super::handle_disable_edge_predictor_all(
            "test-token-12345678901234567890abcdef".into(),
            "unit test memory-only".into(),
            tx,
            &mut pipeline,
            "paper",
            None,
        );
        let result = rx.blocking_recv().unwrap();
        assert!(result.is_ok(), "got {:?}", result);
        let msg = result.unwrap();
        assert!(
            msg.contains("memory-only"),
            "msg should flag memory-only: {}",
            msg
        );
        assert!(store.load_for("ma_crossover").is_none());
    }

    /// EDGE-P3-1 Step 7e · EN: with a wired risk_store backed by a real TOML
    ///   persist path, Stage 1 must write `use_edge_predictor = false` to disk
    ///   and Stage 2 must bump the in-memory flag to false (ArcSwap).
    /// EDGE-P3-1 Step 7e · 中文：接線 risk_store + TOML 回寫路徑，Stage 1 必須
    ///   把 use_edge_predictor = false 寫入磁碟；Stage 2 記憶體內旗標也必須翻 false。
    #[test]
    fn test_handle_disable_edge_predictor_all_writes_toml_stage1() {
        use crate::config::{ConfigStore, RiskConfig};
        use crate::edge_predictor::{EdgePredictorStore, null_backend::NullPredictor};

        let tmp = tempfile::tempdir().unwrap();
        let path = tmp.path().join("risk.toml");

        // Start with use_edge_predictor=true so the test exercises an actual
        // flip. RiskConfig::default() has use=false, so patch the default up.
        // 以 true 起步，確保測試驗證真正的翻轉（預設為 false）。
        let mut cfg = RiskConfig::default();
        cfg.edge_predictor.use_edge_predictor = true;
        cfg.validate().expect("baseline must validate");
        let risk_store = std::sync::Arc::new(
            ConfigStore::new(cfg).with_toml_persist(path.clone()),
        );

        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.set_risk_store(std::sync::Arc::clone(&risk_store));
        let pred_store = std::sync::Arc::new(EdgePredictorStore::new());
        let p: std::sync::Arc<dyn crate::edge_predictor::EdgePredictor + Send + Sync> =
            std::sync::Arc::new(NullPredictor::new());
        pred_store.swap("ma_crossover", p);
        pipeline.set_edge_predictor_store(std::sync::Arc::clone(&pred_store));

        let (tx, rx) = tokio::sync::oneshot::channel();
        super::handle_disable_edge_predictor_all(
            "test-token-12345678901234567890abcdef".into(),
            "unit test stage1 toml".into(),
            tx,
            &mut pipeline,
            "paper",
            None, // no audit pool → test needs no tokio runtime
        );
        let result = rx.blocking_recv().unwrap();
        assert!(result.is_ok(), "got {:?}", result);
        let msg = result.unwrap();
        assert!(msg.contains("persisted=false"), "msg: {}", msg);

        // Stage 1 proof: disk contains the new flag.
        let body = std::fs::read_to_string(&path).expect("toml file written");
        assert!(
            body.contains("use_edge_predictor = false"),
            "TOML missing flipped flag:\n{}",
            body
        );

        // Stage 2 proof: in-memory snapshot reflects the flip.
        let in_mem = risk_store.load();
        assert!(
            !in_mem.edge_predictor.use_edge_predictor,
            "ArcSwap still reads stale true"
        );

        // Stage 3 proof: predictor slots are cleared.
        assert!(pred_store.load_for("ma_crossover").is_none());
    }

    // ═══════════════════════════════════════════════════════════════════
    // EDGE-P3-1 Step 7a: DecisionFeatureSnapshot passthrough tests.
    // EDGE-P3-1 Step 7a：決策特徵快照 IPC 透傳測試。
    // ═══════════════════════════════════════════════════════════════════

    fn make_decision_feature_cmd(ctx_id: &str) -> PipelineCommand {
        PipelineCommand::DecisionFeatureSnapshot {
            context_id: ctx_id.into(),
            ts_ms: 1_700_000_000_000,
            engine_mode: "paper".into(),
            strategy: "ma_crossover".into(),
            symbol: "BTCUSDT".into(),
            side: 1,
            feature_schema_version: "v1".into(),
            feature_schema_hash: "sha256:0011223344556677".into(),
            feature_definition_hash: "sha256:0011223344556677".into(),
            features_jsonb: r#"{"adx_1h":25.0,"side":1}"#.into(),
        }
    }

    /// EN: DecisionFeatureSnapshot with no writer wired is a silent fail-soft
    ///   skip — must not panic and leave the pipeline in a consistent state.
    /// 中文: writer 未接線時 DecisionFeatureSnapshot 必須 fail-soft 跳過，不 panic。
    #[test]
    fn test_decision_feature_snapshot_no_tx_is_nop() {
        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();
        // No decision_feature_tx wired — skip path.
        assert!(pipeline.decision_feature_tx().is_none());
        handle_paper_command(
            make_decision_feature_cmd("ctx-nowire"),
            &mut pipeline,
            &mut writer,
            &mut pending,
        );
        // Still no tx; still no panic.
        assert!(pipeline.decision_feature_tx().is_none());
    }

    /// EN: IPC passthrough forwards the payload verbatim into the writer channel.
    /// 中文: IPC 透傳原樣將載荷送入 writer 通道。
    #[test]
    fn test_decision_feature_snapshot_forwards_to_tx() {
        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();
        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::DecisionFeatureMsg>(16);
        pipeline.set_decision_feature_tx(tx);

        handle_paper_command(
            make_decision_feature_cmd("ctx-fwd-1"),
            &mut pipeline,
            &mut writer,
            &mut pending,
        );
        let msg = rx.try_recv().expect("writer should have received the forwarded msg");
        assert_eq!(msg.context_id, "ctx-fwd-1");
        assert_eq!(msg.strategy_name, "ma_crossover");
        assert_eq!(msg.symbol, "BTCUSDT");
        assert_eq!(msg.side, 1);
        assert_eq!(msg.engine_mode, "paper");
        assert_eq!(msg.feature_schema_version, "v1");
        assert!(msg.features_jsonb.contains("adx_1h"));
    }

    /// EN: Full writer-channel produces a best-effort drop (warn), not a panic.
    /// 中文: writer 通道滿時 best-effort drop（warn），不 panic。
    #[test]
    fn test_decision_feature_snapshot_full_channel_drops() {
        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();
        let (tx, rx) = tokio::sync::mpsc::channel::<crate::database::DecisionFeatureMsg>(1);
        // Keep rx alive so Closed isn't hit; fill the one slot.
        let _held_rx = rx;
        // First send fills the channel.
        tx.try_send(crate::database::DecisionFeatureMsg {
            context_id: "filler".into(),
            ts_ms: 1,
            engine_mode: "paper".into(),
            strategy_name: "x".into(),
            symbol: "Y".into(),
            side: 1,
            feature_schema_version: "v1".into(),
            feature_schema_hash: "h".into(),
            feature_definition_hash: "h".into(),
            features_jsonb: "{}".into(),
        })
        .unwrap();
        pipeline.set_decision_feature_tx(tx);

        // Full channel must not panic — handler warns + drops.
        handle_paper_command(
            make_decision_feature_cmd("ctx-drop"),
            &mut pipeline,
            &mut writer,
            &mut pending,
        );
    }

    /// EN: EmitShadowFill without a wired writer → fail-soft log; must not panic.
    /// 中文: EmitShadowFill 未接 writer 走 fail-soft log；不得 panic。
    #[test]
    fn test_emit_shadow_fill_does_not_panic() {
        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();

        handle_paper_command(
            PipelineCommand::EmitShadowFill {
                context_id: "ctx-1".into(),
                strategy: "ma_crossover".into(),
                symbol: "BTCUSDT".into(),
                side: 1,
                features_jsonb: "{}".into(),
                prediction_q10: -1.0,
                prediction_q50: 0.5,
                prediction_q90: 2.0,
                cost_bps: 5.5,
                ts_ms: 1_700_000_000_000,
            },
            &mut pipeline,
            &mut writer,
            &mut pending,
        );
        // No writer wired → fail-soft log path; no panic.
        // 未接 writer → fail-soft log 分支，不 panic。
    }

    // ── Step 7b ReloadEdgePredictor plumbing tests ─────────────────────────
    // ── Step 7b ReloadEdgePredictor 骨架測試 ───────────────────────────────

    /// EN: Invalid engine name is rejected before touching the filesystem.
    /// 中文: 非法 engine 名在碰磁碟前即拒。
    #[test]
    fn test_reload_edge_predictor_rejects_unknown_engine() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let out = super::handle_reload_edge_predictor(
            "mainnet",
            "ma_crossover",
            std::path::Path::new("/nonexistent"),
            &mut pipeline,
        );
        assert!(out.is_err());
        assert!(out.unwrap_err().contains("invalid engine"));
    }

    /// EN: Without a wired EdgePredictorStore, the handler errs before the
    /// stub loader runs — prevents silent success with no hot-swap target.
    /// 中文: 未注入 store 則在 loader 前即拒，避免熱換進空引用。
    #[test]
    fn test_reload_edge_predictor_requires_store() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let out = super::handle_reload_edge_predictor(
            "paper",
            "ma_crossover",
            std::path::Path::new("/nonexistent"),
            &mut pipeline,
        );
        assert!(out.is_err());
        assert!(out.unwrap_err().contains("EdgePredictorStore not wired"));
    }

    /// EN: With a store wired, the stub loader returns `onnx_loader_not_wired`
    /// and the handler surfaces that error unchanged — the protocol shape is
    /// pinned but no predictor actually swaps until ML-MIT #26 lands.
    /// 中文: 接了 store 後 stub loader 回 onnx_loader_not_wired，handler 透傳錯誤；
    /// 協定形狀已定，實際熱換等 ML-MIT #26。
    #[test]
    fn test_reload_edge_predictor_stub_loader_errs() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let store = std::sync::Arc::new(crate::edge_predictor::EdgePredictorStore::new());
        pipeline.set_edge_predictor_store(store.clone());
        // Use a temp file that DOES exist so we pass the first branch and hit
        // the permanent "awaiting ML-MIT #26" error — confirms we traverse the
        // full loader path, not just the path-missing early-return.
        // 用實存檔走完整 loader 路徑，命中 "awaiting ML-MIT #26" 錯誤。
        let tmp = tempfile::NamedTempFile::new().expect("tempfile");
        let out = super::handle_reload_edge_predictor(
            "paper",
            "ma_crossover",
            tmp.path(),
            &mut pipeline,
        );
        assert!(out.is_err());
        let err = out.unwrap_err();
        assert!(err.contains("onnx_loader_not_wired"), "got: {err}");
        assert!(err.contains("ML-MIT #26"), "got: {err}");
        // Confirm nothing got registered into the store.
        // 確認 store 未被寫入。
        assert_eq!(store.loaded_count(), 0);
    }

    /// EN: Engine whitelist trims whitespace so stray \n from a Python proxy
    /// doesn't fall through to the unknown-engine branch.
    /// 中文: engine 白名單 trim 空白，避 Python proxy 換行誤判。
    #[test]
    fn test_reload_edge_predictor_trims_engine_name() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let store = std::sync::Arc::new(crate::edge_predictor::EdgePredictorStore::new());
        pipeline.set_edge_predictor_store(store);
        let tmp = tempfile::NamedTempFile::new().expect("tempfile");
        let out = super::handle_reload_edge_predictor(
            "  paper\n",
            "ma_crossover",
            tmp.path(),
            &mut pipeline,
        );
        // Whitelist passes → loader stub → err with ML-MIT #26 (not "invalid engine").
        // 白名單通過 → loader 存根 → 錯誤含 ML-MIT #26（非 invalid engine）。
        let err = out.unwrap_err();
        assert!(err.contains("ML-MIT #26"), "got: {err}");
        assert!(!err.contains("invalid engine"), "trim failed: {err}");
    }
}
