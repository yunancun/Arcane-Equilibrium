//! Unit tests for the event_consumer handlers facade.
//! 事件消費者 handlers facade 的單元測試。
//!
//! MODULE_NOTE (EN): Moved verbatim from the pre-split handlers.rs as part
//!   of E5-P1-3. `super::*` resolves to the dispatch facade, so
//!   `handle_paper_command`, `handle_disable_edge_predictor_all`, and
//!   `handle_reload_edge_predictor` are all in scope via their re-exports.
//! MODULE_NOTE (中): E5-P1-3 機械搬遷；super::* 指向 handlers facade，
//!   保證所有舊呼叫路徑不變。

use super::*;
use crate::event_consumer::types::PendingOrder;
use crate::persistence::{DualStateWriter, StateWriter};
use crate::tick_pipeline::{PipelineCommand, TickPipeline};
use std::collections::HashMap;

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
    handle_paper_command(
        PipelineCommand::Pause,
        &mut pipeline,
        &mut writer,
        &mut pending,
    );
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
    handle_paper_command(
        PipelineCommand::Resume,
        &mut pipeline,
        &mut writer,
        &mut pending,
    );
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
    pending.insert(
        "order1".to_string(),
        PendingOrder {
            order_link_id: "order1".into(),
            symbol: "BTCUSDT".into(),
            is_long: true,
            qty: 0.01,
            strategy: "test".into(),
            sent_ts_ms: 1000,
            cum_filled_qty: 0.0,
            is_close: false,
            // FILL-CONTEXT-LINKAGE-1: empty id preserves pre-fix behaviour.
            // FILL-CONTEXT-LINKAGE-1：空字串保持修前行為。
            context_id: String::new(),
            order_type: "market".into(),
            time_in_force: None,
            maker_timeout_ms: None,
            reference_price: None,
            reference_ts_ms: None,
            reference_source: None,
            cancel_requested_ts_ms: None,
        },
    );
    handle_paper_command(
        PipelineCommand::Reset {
            new_balance: 5000.0,
        },
        &mut pipeline,
        &mut writer,
        &mut pending,
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
        &mut pipeline,
        &mut writer,
        &mut pending,
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
        &mut pipeline,
        &mut writer,
        &mut pending,
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
    let (effective_json, conf_scale_opt): (String, Option<f64>) =
        match serde_json::from_str::<serde_json::Value>(params_json) {
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
    let (effective_json, conf_scale_opt): (String, Option<f64>) =
        match serde_json::from_str::<serde_json::Value>(params_json) {
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
    let (effective_json, conf_scale_opt): (String, Option<f64>) =
        match serde_json::from_str::<serde_json::Value>(params_json) {
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

/// EN: Mixed payload must be atomic — if typed validation fails, `conf_scale`
/// must not be partially applied.
/// 中文：混合 payload 必須原子化——類型化驗證失敗時不得只套用 `conf_scale`。
#[test]
fn test_conf_scale_not_partially_applied_when_typed_validation_fails() {
    let dir = tempfile::tempdir().unwrap();
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    for strategy in crate::strategies::StrategyFactory::create_all() {
        pipeline.orchestrator.register(strategy);
    }
    let mut writer = make_writer(dir.path());
    let mut pending = HashMap::new();

    let before = pipeline
        .orchestrator
        .find_strategy_mut("ma_crossover")
        .expect("ma_crossover present")
        .conf_scale();
    assert!((before - 1.0).abs() < 1e-10);

    let (tx, rx) = tokio::sync::oneshot::channel();
    handle_paper_command(
        PipelineCommand::UpdateStrategyParams {
            strategy_name: "ma_crossover".into(),
            params_json: r#"{"conf_scale":2.5,"cooldown_ms":"bad_type"}"#.into(),
            response_tx: tx,
        },
        &mut pipeline,
        &mut writer,
        &mut pending,
    );
    let resp = rx.blocking_recv().unwrap();
    let err = resp.expect_err("typed validation must fail");
    assert!(
        err.contains("validation failed"),
        "unexpected error payload: {err}"
    );

    let after = pipeline
        .orchestrator
        .find_strategy_mut("ma_crossover")
        .expect("ma_crossover present")
        .conf_scale();
    assert!(
        (after - before).abs() < 1e-10,
        "conf_scale must remain unchanged on typed validation failure"
    );
}

/// EN: Partial UpdateStrategyParams must merge onto the current params instead
/// of deserializing missing fields from defaults.
/// 中文：partial 參數更新必須覆蓋到當前參數上，不能讓缺失欄位回 default。
#[test]
fn test_update_strategy_params_partial_merge_preserves_grid_maker_fields() {
    let dir = tempfile::tempdir().unwrap();
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    for strategy in crate::strategies::StrategyFactory::create_all() {
        pipeline.orchestrator.register(strategy);
    }
    let mut writer = make_writer(dir.path());
    let mut pending = HashMap::new();

    let current_json = pipeline
        .orchestrator
        .find_strategy_mut("grid_trading")
        .expect("grid_trading present")
        .get_params_json();
    let mut current: serde_json::Value =
        serde_json::from_str(&current_json).expect("grid params JSON");
    current["use_maker_entry"] = serde_json::Value::Bool(true);
    current["maker_price_offset_bps"] = serde_json::json!(2.0);
    current["maker_limit_timeout_ms"] = serde_json::json!(45_000);
    current["cooldown_ms"] = serde_json::json!(180_000);

    let (tx1, rx1) = tokio::sync::oneshot::channel();
    handle_paper_command(
        PipelineCommand::UpdateStrategyParams {
            strategy_name: "grid_trading".into(),
            params_json: current.to_string(),
            response_tx: tx1,
        },
        &mut pipeline,
        &mut writer,
        &mut pending,
    );
    rx1.blocking_recv()
        .expect("response sent")
        .expect("full update succeeds");

    let (tx2, rx2) = tokio::sync::oneshot::channel();
    handle_paper_command(
        PipelineCommand::UpdateStrategyParams {
            strategy_name: "grid_trading".into(),
            params_json: r#"{"cooldown_ms":240000}"#.into(),
            response_tx: tx2,
        },
        &mut pipeline,
        &mut writer,
        &mut pending,
    );
    rx2.blocking_recv()
        .expect("response sent")
        .expect("partial update succeeds");

    let after_json = pipeline
        .orchestrator
        .find_strategy_mut("grid_trading")
        .expect("grid_trading present")
        .get_params_json();
    let after: serde_json::Value = serde_json::from_str(&after_json).expect("grid params JSON");

    assert_eq!(after["cooldown_ms"], serde_json::json!(240_000));
    assert_eq!(after["use_maker_entry"], serde_json::Value::Bool(true));
    assert_eq!(after["maker_price_offset_bps"], serde_json::json!(2.0));
    assert_eq!(after["maker_limit_timeout_ms"], serde_json::json!(45_000));
}

// ── EDGE-P3-1 Stage 0 handlers ─────────────────────────────────────

/// EN: SetEdgePredictorShadow returns Err when no store is wired.
/// Protects ML-MIT from silently no-oping on an uninitialised engine.
/// 中文: 未注入 store 時 SetEdgePredictorShadow 回 Err；避免 ML-MIT
/// 以為熱換成功但其實無人接收。
#[test]
fn test_set_edge_predictor_shadow_fails_without_store() {
    use crate::edge_predictor::{null_backend::NullPredictor, BoxedEdgePredictor};

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
    assert!(
        msg.contains("not wired"),
        "err should mention not-wired: {}",
        msg
    );
}

/// EN: SetEdgePredictorShadow succeeds after store is wired; load_for
/// returns the swapped predictor.
/// 中文: 注入 store 後 SetEdgePredictorShadow 成功；load_for 返回剛熱換的 predictor。
#[test]
fn test_set_edge_predictor_shadow_succeeds_after_wire() {
    use crate::edge_predictor::{
        null_backend::NullPredictor, BoxedEdgePredictor, EdgePredictorStore,
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
    assert!(
        store.load_for("ma_crossover").is_some(),
        "predictor should be loaded after swap"
    );
}

/// EN: DisableEdgePredictorAll clears every registered slot.
/// 中文: DisableEdgePredictorAll 清空所有已註冊槽位。
#[test]
fn test_disable_edge_predictor_all_clears_slots() {
    use crate::edge_predictor::{null_backend::NullPredictor, EdgePredictorStore};

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
    assert!(
        msg.contains("cleared 3"),
        "msg should report cleared count: {}",
        msg
    );
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
    use crate::edge_predictor::{null_backend::NullPredictor, EdgePredictorStore};

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
    use crate::edge_predictor::{null_backend::NullPredictor, EdgePredictorStore};

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
    use crate::edge_predictor::{null_backend::NullPredictor, EdgePredictorStore};

    let tmp = tempfile::tempdir().unwrap();
    let path = tmp.path().join("risk.toml");

    // Start with use_edge_predictor=true so the test exercises an actual
    // flip. RiskConfig::default() has use=false, so patch the default up.
    // 以 true 起步，確保測試驗證真正的翻轉（預設為 false）。
    let mut cfg = RiskConfig::default();
    cfg.edge_predictor.use_edge_predictor = true;
    cfg.validate().expect("baseline must validate");
    let risk_store = std::sync::Arc::new(ConfigStore::new(cfg).with_toml_persist(path.clone()));

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
    let msg = rx
        .try_recv()
        .expect("writer should have received the forwarded msg");
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

/// EN: With a store wired, the loader errors before a predictor can swap
/// — the protocol shape is pinned but no predictor is registered. Under
/// the default build the stub loader errs with `onnx_loader_not_wired`;
/// under `edge_predictor_ort` the real loader errs because the tempfile's
/// random name doesn't match the `..._q50_..._<date>.onnx` convention,
/// which proves the dispatch traverses the full loader path.
/// 中文: 接了 store 後 loader 回錯誤，store 未被寫入；default build 為 stub
/// `onnx_loader_not_wired`；ort build 則因檔名無 `_q50_` 標記而拒。
#[test]
fn test_reload_edge_predictor_stub_loader_errs() {
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    let store = std::sync::Arc::new(crate::edge_predictor::EdgePredictorStore::new());
    pipeline.set_edge_predictor_store(store.clone());
    // Use a temp file that DOES exist so we pass the first branch and hit
    // the loader. Under the default build that's the permanent
    // "awaiting ML-MIT #26" error; under the ort build the real loader
    // refuses because the random tempfile name has no `_q50_` marker.
    // 用實存檔走完整 loader 路徑。default build → "ML-MIT #26"；
    // ort build → 檔名缺 `_q50_` 標記。
    let tmp = tempfile::NamedTempFile::new().expect("tempfile");
    let out =
        super::handle_reload_edge_predictor("paper", "ma_crossover", tmp.path(), &mut pipeline);
    let err = out.expect_err("loader must err on unconventional tempfile path");
    #[cfg(not(feature = "edge_predictor_ort"))]
    {
        assert!(err.contains("onnx_loader_not_wired"), "got: {err}");
        assert!(err.contains("edge_predictor_ort"), "got: {err}");
    }
    #[cfg(feature = "edge_predictor_ort")]
    {
        assert!(err.contains("_q50_"), "got: {err}");
    }
    // Confirm nothing got registered into the store — invariant across backends.
    // 跨後端不變：store 未被寫入。
    assert_eq!(store.loaded_count(), 0);
}

/// EN: Engine whitelist trims whitespace so stray \n from a Python proxy
/// doesn't fall through to the unknown-engine branch. The loader itself
/// errs after trimming (stub → "ML-MIT #26"; ort → "_q50_" marker),
/// which proves the whitelist stage accepted the trimmed name.
/// 中文: engine 白名單 trim 空白（避 Python proxy 換行誤判）；loader 在 trim
/// 後才出錯（stub → "ML-MIT #26"；ort → "_q50_" 標記）— 表白名單通過。
#[test]
fn test_reload_edge_predictor_trims_engine_name() {
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    let store = std::sync::Arc::new(crate::edge_predictor::EdgePredictorStore::new());
    pipeline.set_edge_predictor_store(store);
    let tmp = tempfile::NamedTempFile::new().expect("tempfile");
    let out =
        super::handle_reload_edge_predictor("  paper\n", "ma_crossover", tmp.path(), &mut pipeline);
    let err = out.expect_err("loader path must be reached after whitelist trim");
    assert!(!err.contains("invalid engine"), "trim failed: {err}");
    #[cfg(not(feature = "edge_predictor_ort"))]
    assert!(err.contains("onnx_loader_not_wired"), "got: {err}");
    #[cfg(feature = "edge_predictor_ort")]
    assert!(err.contains("_q50_"), "got: {err}");
}
