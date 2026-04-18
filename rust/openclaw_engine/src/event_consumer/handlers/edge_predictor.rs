//! Edge-predictor + learning-pipeline IPC command handlers
//! (SetEdgePredictorShadow / ReloadEdgePredictor / DisableEdgePredictorAll /
//! EmitShadowFill / DecisionFeatureSnapshot). Contains the EDGE-P3-1 Step 7e
//! two-phase kill-switch implementation plus the V014 audit row.
//! Extracted from the legacy monolith as part of E5-P1-3.
//!
//! Edge-predictor 與學習管線 IPC 命令處理器 — E5-P1-3 從 handlers.rs 拆出，
//! 包含 EDGE-P3-1 Step 7e 兩階段 kill-switch 與 V014 審計列。
//!
//! MODULE_NOTE (EN): The disable-all kill-switch's two-phase commit
//!   (disk-first fsync → ArcSwap → clear_all) is preserved bit-for-bit.
//!   Tests in `handlers/tests.rs` call `super::handle_disable_edge_predictor_all`
//!   and `super::handle_reload_edge_predictor`, both re-exported from
//!   `handlers::` via `pub use`.
//! MODULE_NOTE (中): Disable-all 的兩階段提交（先 fsync 落盤 → ArcSwap →
//!   clear_all）與拆分前完全一致；單元測試透過 `handlers::` 再出口存取。

use crate::tick_pipeline::TickPipeline;
use sha2::{Digest, Sha256};
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
                if let Err(e) = crate::config::write_toml_atomic_fsynced(&next, path) {
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

/// EDGE-P3-1 Stage 0 · EN: Hot-swap a predictor for a single strategy.
///   Fails fast if no `EdgePredictorStore` has been wired onto the pipeline
///   yet — ML-MIT must not silently no-op on an uninitialised engine.
/// EDGE-P3-1 Stage 0 · 中文：熱換單一策略的 predictor；未注入 store 時立即
///   失敗，避免誤以為寫入了未初始化的引擎。
pub(super) fn handle_set_edge_predictor_shadow(
    strategy: String,
    predictor: crate::edge_predictor::BoxedEdgePredictor,
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
) {
    let result = match pipeline.edge_predictor_store() {
        Some(store) => {
            store.swap(&strategy, predictor.into_arc());
            info!(strategy = %strategy,
                "EdgePredictor swapped / 已熱換預測器");
            Ok(format!("swapped predictor for {}", strategy))
        }
        None => Err(
            "EdgePredictorStore not wired on this engine — check main.rs \
             set_edge_predictor_store() / 此引擎尚未注入 EdgePredictorStore"
                .into(),
        ),
    };
    let _ = response_tx.send(result);
}

/// EDGE-P3-1 Stage 0 · EN: In-process direct-dispatch path for the kill-switch
///   used only by unit tests. Production path intercepts the variant in
///   `event_consumer/mod.rs` and calls `handle_disable_edge_predictor_all`
///   with the real `db_mode` + `audit_pool`.
/// EDGE-P3-1 Stage 0 · 中文：單元測試用直接派發路徑；生產路徑在 mod.rs 攔截
///   並傳入真實 db_mode / audit_pool。
pub(super) fn handle_disable_edge_predictor_all_local(
    operator_token: String,
    reason: String,
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
) {
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

/// EDGE-P3-1 Step 7c · EN: ε-greedy shadow-fill passthrough into the
///   writer channel. Mirrors Step 7a: `try_send` off the hot path;
///   Full/Closed is a best-effort drop. `engine_mode` is derived from the
///   pipeline kind so the writer's R5 second-line-of-defence check can
///   verify it explicitly.
/// EDGE-P3-1 Step 7c · 中文：ε-greedy shadow-fill 轉發至 writer 通道；
///   沿用 Step 7a 模式，try_send 不阻塞熱路徑；engine_mode 由 pipeline_kind
///   推導供 writer R5 防線驗證。
#[allow(clippy::too_many_arguments)]
pub(super) fn handle_emit_shadow_fill(
    context_id: String,
    strategy: String,
    symbol: String,
    side: i8,
    features_jsonb: String,
    prediction_q10: f32,
    prediction_q50: f32,
    prediction_q90: f32,
    cost_bps: f64,
    ts_ms: u64,
    pipeline: &mut TickPipeline,
) {
    match pipeline.shadow_fill_db_tx() {
        Some(tx) => {
            let msg = crate::database::ShadowFillMsg {
                context_id: context_id.clone(),
                ts_ms,
                engine_mode: pipeline.effective_engine_mode().to_string(),
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

/// EDGE-P3-1 Step 7a · EN: Passthrough IPC → decision_feature writer channel.
///   External callers (Python backfill/replay tooling) inject training-
///   store rows through the same Rust-direct writer the IntentProcessor
///   producer uses. Fail-soft when tx is not wired; `try_send` keeps this off
///   the hot path.
/// EDGE-P3-1 Step 7a · 中文：Passthrough IPC → decision_feature writer 通道；
///   tx 未接線時 fail-soft 跳過；try_send 不阻塞熱路徑。
#[allow(clippy::too_many_arguments)]
pub(super) fn handle_decision_feature_snapshot(
    context_id: String,
    ts_ms: u64,
    engine_mode: String,
    strategy: String,
    symbol: String,
    side: i8,
    feature_schema_version: String,
    feature_schema_hash: String,
    feature_definition_hash: String,
    features_jsonb: String,
    pipeline: &mut TickPipeline,
) {
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

