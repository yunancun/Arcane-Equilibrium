//! Three-pipeline spawn helpers — Paper / Demo / Live pipelines construction
//! with crash-only isolation.
//! 三管線啟動輔助函數 — Paper / Demo / Live 管線構建 + crash-only 隔離。
//!
//! MODULE_NOTE (EN): Extracted from `main.rs` (G1-03 Wave 1) to bring the
//!   file under §九 1200-line hard limit. Each pipeline spawn (paper/demo/live)
//!   was ~120-240 lines of coupled `EventConsumerDeps` construction + spawn
//!   wrapper. Separating them here preserves identical semantics while letting
//!   `main.rs` focus on top-level orchestration (config load, channel wiring,
//!   shutdown sequence).
//!
//!   All three fns take a `PipelineSpawnContext` bundling 20+ shared refs so
//!   the call sites in `main.rs::async_main` remain single lines. Each fn
//!   returns a `tokio::task::JoinHandle<()>` (or `std::thread::JoinHandle` for
//!   live's dedicated OS thread) matching the pre-extraction shape exactly.
//!
//! MODULE_NOTE (中): 從 `main.rs` 抽出（G1-03 Wave 1），為將 main.rs 壓在
//!   §九 1200 行硬上限下。Paper / Demo / Live 三管線 spawn 各自 ~120-240 行
//!   高度耦合的 `EventConsumerDeps` 構建 + spawn 包裝。集中於此檔保留完全相同
//!   語義，讓 `main.rs` 專注於頂層編排（config 載入、通道接線、關機序列）。
//!
//!   三個函數皆接收 `PipelineSpawnContext`（打包 20+ 共享參考），保持 main.rs
//!   呼叫點為單行。各 fn 回傳 `tokio::task::JoinHandle<()>`（Live 為獨立 OS
//!   線程 `std::thread::JoinHandle<()>`），形狀與抽取前完全一致。

use crate::main_fanout::LiveEventSenderSlot;
use crate::run_pipeline_crash_only;
use crate::startup::ExchangePipelineBindings;
use openclaw_core::governance_core::LeaseTransitionSender;
use openclaw_engine::agent_spine::{config::AgentSpineMode, store::AgentSpineMsg};
use openclaw_engine::bybit_rest_client::{
    live_bybit_environment, BybitEnvironment, BybitRestClient,
};
use openclaw_engine::canary_writer::CanaryWriterHandle;
use openclaw_engine::config::{BudgetConfig, ConfigManager, ConfigStore};
use openclaw_engine::database::{
    DecisionContextMsg, DecisionFeatureMsg, ExitFeatureRow, MarketDataMsg, ShadowExitMsg,
    ShadowFillMsg, TradingMsg,
};
use openclaw_engine::edge_predictor::PerEnginePredictors;
use openclaw_engine::event_consumer::{run_event_consumer, EventConsumerDeps};
use openclaw_engine::feature_collector::FeatureSnapshot;
use openclaw_engine::instrument_info::InstrumentInfoCache;
use openclaw_engine::ipc_server::{LiveCmdSenderSlot, PerEngineRiskStores};
use openclaw_engine::linucb::LinUcbRuntime;
use openclaw_engine::news::NewsContextSnapshot;
use openclaw_engine::scanner::registry::SymbolRegistry;
use openclaw_engine::scanner::ScannerConfig;
use openclaw_engine::tick_pipeline::{EngineEvent, PipelineCommand, PipelineHealth, PipelineKind};
use openclaw_types::PriceEvent;
use std::sync::Arc;
use tokio::sync::{broadcast, mpsc, oneshot};
use tokio_util::sync::CancellationToken;
use tracing::{info, warn};

/// Shared references across all pipeline spawns.
/// 所有管線 spawn 共享的參考組合。
///
/// EN: Passed by `&` into each spawn fn to keep signatures short. All fields
///   are Arc-cloned inside the fns — no ownership transfer at call sites.
/// 中: 以 `&` 傳入每個 spawn fn 以保持簽名簡短；內部統一以 Arc clone，呼叫點
///   不發生所有權轉移。
pub(crate) struct PipelineSpawnContext<'a> {
    pub config: &'a Arc<ConfigManager>,
    pub cancel: &'a CancellationToken,
    pub instruments: &'a Option<Arc<InstrumentInfoCache>>,
    pub shared_client: &'a Option<Arc<BybitRestClient>>,
    pub risk_stores: &'a PerEngineRiskStores,
    pub budget_store: &'a Arc<ConfigStore<BudgetConfig>>,
    pub audit_pool: Option<sqlx::PgPool>,
    pub symbol_registry: &'a Arc<SymbolRegistry>,
    pub scanner_store: &'a Arc<ConfigStore<ScannerConfig>>,
    pub shared_linucb_runtime: &'a Arc<LinUcbRuntime>,
    pub shared_news_snapshot: &'a Arc<NewsContextSnapshot>,
    pub shared_last_tick_ms: &'a Arc<std::sync::atomic::AtomicU64>,
    pub canary_handle: &'a CanaryWriterHandle,
    pub per_engine_predictors: &'a Arc<PerEnginePredictors>,
    pub cross_engine_tx: &'a broadcast::Sender<EngineEvent>,
    pub global_exposure_usdt: &'a Arc<std::sync::atomic::AtomicU64>,
    pub has_live: bool,
    pub has_demo: bool,
}

/// Writer channel senders shared across pipelines.
/// 所有管線共用的 DB writer sender 組合。
pub(crate) struct WriterSenders {
    pub market_tx: Option<mpsc::Sender<MarketDataMsg>>,
    pub feature_tx: Option<mpsc::Sender<FeatureSnapshot>>,
    pub trading_tx: Option<mpsc::Sender<TradingMsg>>,
    pub context_tx: Option<mpsc::Sender<DecisionContextMsg>>,
    pub decision_feature_tx: Option<mpsc::Sender<DecisionFeatureMsg>>,
    pub shadow_fill_tx: Option<mpsc::Sender<ShadowFillMsg>>,
    pub exit_feature_tx: Option<mpsc::Sender<ExitFeatureRow>>,
    pub shadow_exit_tx: Option<mpsc::Sender<ShadowExitMsg>>,
    pub agent_spine_tx: Option<mpsc::Sender<AgentSpineMsg>>,
    pub agent_spine_mode: AgentSpineMode,
    pub lease_transition_tx: Option<LeaseTransitionSender>,
}

/// Paper pipeline spawn inputs.
/// Paper 管線 spawn 輸入。
pub(crate) struct PaperChannels {
    pub event_rx: mpsc::Receiver<Arc<PriceEvent>>,
    pub cmd_tx: mpsc::UnboundedSender<PipelineCommand>,
    pub cmd_rx: mpsc::UnboundedReceiver<PipelineCommand>,
    pub ready_tx: oneshot::Sender<()>,
    pub health: Arc<std::sync::atomic::AtomicU8>,
    pub risk_level: Arc<std::sync::atomic::AtomicU8>,
    pub positions_mirror: Arc<parking_lot::RwLock<std::collections::HashMap<String, bool>>>,
    pub initial_balance: f64,
}

/// Demo pipeline spawn inputs.
/// Demo 管線 spawn 輸入。
pub(crate) struct DemoChannels {
    pub bindings: ExchangePipelineBindings,
    pub slot_cancel: CancellationToken,
    pub event_rx: mpsc::Receiver<Arc<PriceEvent>>,
    pub cmd_tx: Option<mpsc::UnboundedSender<PipelineCommand>>,
    pub cmd_rx: Option<mpsc::UnboundedReceiver<PipelineCommand>>,
    pub ready_tx: Option<oneshot::Sender<()>>,
    pub positions_mirror: Arc<parking_lot::RwLock<std::collections::HashMap<String, bool>>>,
}

/// Live pipeline spawn inputs.
/// Live 管線 spawn 輸入。
pub(crate) struct LiveChannels {
    pub bindings: ExchangePipelineBindings,
    pub slot_cancel: CancellationToken,
    pub event_rx: mpsc::Receiver<Arc<PriceEvent>>,
    pub cmd_tx: Option<mpsc::UnboundedSender<PipelineCommand>>,
    pub cmd_rx: Option<mpsc::UnboundedReceiver<PipelineCommand>>,
    pub ready_tx: Option<oneshot::Sender<()>>,
    pub positions_mirror: Arc<parking_lot::RwLock<std::collections::HashMap<String, bool>>>,
}

fn reject_disabled_paper_command(cmd: PipelineCommand) {
    let reason = || {
        Err(
            "paper pipeline disabled: set OPENCLAW_ENABLE_PAPER=1 before sending paper commands"
                .to_string(),
        )
    };
    match cmd {
        PipelineCommand::ResetDrawdownBaseline { response_tx }
        | PipelineCommand::UpdateStrategyParams { response_tx, .. }
        | PipelineCommand::GetStrategyParams { response_tx, .. }
        | PipelineCommand::GetParamRanges { response_tx, .. }
        | PipelineCommand::SetStrategyActive { response_tx, .. }
        | PipelineCommand::GetRiskRuntimeStatus { response_tx }
        | PipelineCommand::ClearConsecutiveLosses { response_tx }
        | PipelineCommand::ForceGovernorTighter { response_tx, .. }
        | PipelineCommand::ForceGovernorLooser { response_tx, .. }
        | PipelineCommand::SubmitOrder { response_tx, .. }
        | PipelineCommand::ReconcilerEscalate { response_tx, .. }
        | PipelineCommand::ReconcilerDeEscalate { response_tx, .. }
        | PipelineCommand::SetSystemMode { response_tx, .. }
        | PipelineCommand::SetEdgePredictorShadow { response_tx, .. }
        | PipelineCommand::DisableEdgePredictorAll { response_tx, .. }
        | PipelineCommand::ReloadEdgePredictor { response_tx, .. }
        | PipelineCommand::GetDynamicRiskStatus { response_tx }
        | PipelineCommand::SetDynamicRiskEnabled { response_tx, .. } => {
            let _ = response_tx.send(reason());
        }
        PipelineCommand::UpdateRiskConfig { response_tx, .. } => {
            if let Some(tx) = response_tx {
                let _ = tx.send(reason());
            }
        }
        PipelineCommand::GetOpenPositionSymbols { response_tx } => {
            let _ = response_tx.send(std::collections::HashSet::new());
        }
        _ => {}
    }
}

/// Spawn the Paper pipeline (opt-in via OPENCLAW_ENABLE_PAPER=1).
///
/// EN: When disabled (default), writes DISABLED markers to `paper_state.json`
///   + `pipeline_snapshot_paper.json` so GUI / IPC surfaces the state correctly
///   instead of stale balance, then spawns a minimal drain task consuming
///   event+cmd channels (scanner / phase4 / IPC still clone senders).
///   When enabled, builds full `EventConsumerDeps` and spawns via crash-only
///   wrapper — a panic broadcasts `EngineEvent::Crashed(Paper)` + triggers
///   engine-wide cancel (2026-04-14 zombie-fix parity).
///
/// 中: 禁用時（預設）寫 DISABLED 標記至 `paper_state.json`+`pipeline_snapshot_paper.json`
///   讓 GUI/IPC 顯示正確狀態（避免陳舊餘額），然後啟動最小 drain 任務消費
///   event+cmd 通道（scanner/phase4/IPC 仍 clone sender）。啟用時構建完整
///   `EventConsumerDeps` 並以 crash-only 包裝啟動 — panic 廣播
///   `EngineEvent::Crashed(Paper)` + 觸發全引擎 cancel（對齊 2026-04-14 殭屍修復）。
pub(crate) fn spawn_paper_pipeline(
    ctx: &PipelineSpawnContext<'_>,
    writers: &WriterSenders,
    paper: PaperChannels,
    live_bindings_opt: &Option<ExchangePipelineBindings>,
    demo_bindings_opt: &Option<ExchangePipelineBindings>,
) -> tokio::task::JoinHandle<()> {
    let paper_enabled = std::env::var("OPENCLAW_ENABLE_PAPER")
        .map(|v| v.trim() == "1")
        .unwrap_or(false);

    if !paper_enabled {
        info!(
            "paper pipeline DISABLED (default; set OPENCLAW_ENABLE_PAPER=1 to enable) / \
             Paper 管線已禁用（預設；設 OPENCLAW_ENABLE_PAPER=1 啟用）"
        );
        // Mark health as Disabled so GUI / IPC surfaces DISABLED rather than stale Running.
        // 健康狀態標記為 Disabled，GUI / IPC 顯示禁用而非陳舊的 Running。
        paper.health.store(
            PipelineHealth::Disabled as u8,
            std::sync::atomic::Ordering::Relaxed,
        );
        // Signal fan-out barrier so demo/live proceed without waiting for paper ready.
        // 通知扇出屏障 paper 已就緒（禁用也算就緒），demo/live 不必等待。
        let _ = paper.ready_tx.send(());

        // Write one-shot DISABLED markers so Python GUI / ipc_state_reader surface
        // the state correctly instead of reporting stale last-known balance:
        //   * paper_state.json — raw PaperState shape with disabled=true
        //   * pipeline_snapshot_paper.json — wraps paper_state, what GUI actually reads
        // 寫入 DISABLED 標記讓 Python GUI / ipc_state_reader 顯示正確狀態（避免陳舊餘額）：
        //   * paper_state.json — raw PaperState 形狀，附 disabled=true
        //   * pipeline_snapshot_paper.json — 包 paper_state，GUI 實際讀的檔
        {
            let data_dir =
                std::env::var("OPENCLAW_DATA_DIR").unwrap_or_else(|_| "/tmp/openclaw".to_string());
            let ts_ms = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_millis() as u64)
                .unwrap_or(0);
            let paper_state_marker = serde_json::json!({
                "disabled": true,
                "disabled_reason": "OPENCLAW_ENABLE_PAPER != 1",
                "disabled_since_ms": ts_ms,
                "balance": 0.0,
                "initial_balance": paper.initial_balance,
                "peak_balance": paper.initial_balance,
                "total_realized_pnl": 0.0,
                "total_fees": 0.0,
                "total_funding_pnl": 0.0,
                "trade_count": 0,
                "positions": [],
            });
            let snapshot_marker = serde_json::json!({
                "schema_version": 1,
                "written_at_ms": ts_ms,
                "trading_mode": "paper",
                "paper_paused": true,
                "paper_state": paper_state_marker,
                "disabled": true,
                "disabled_reason": "OPENCLAW_ENABLE_PAPER != 1",
                "positions": [],
                "recent_fills": [],
                "recent_intents": [],
            });
            if let Err(e) = std::fs::create_dir_all(&data_dir) {
                warn!(dir = %data_dir, error = %e, "failed to create data dir for paper disabled marker / 建立資料目錄失敗");
            }
            let write_marker = |filename: &str, value: &serde_json::Value| {
                let path = std::path::PathBuf::from(&data_dir).join(filename);
                match serde_json::to_string_pretty(value) {
                    Ok(json) => {
                        if let Err(e) = std::fs::write(&path, json) {
                            warn!(path = ?path, error = %e, "failed to write paper disabled marker / 寫入 paper 禁用標記失敗");
                        }
                    }
                    Err(e) => {
                        warn!(file = %filename, error = %e, "failed to serialize paper disabled marker / 序列化禁用標記失敗")
                    }
                }
            };
            write_marker("paper_state.json", &paper_state_marker);
            write_marker("pipeline_snapshot_paper.json", &snapshot_marker);
        }

        // Spawn minimal drain task: consume paper_event_rx + paper_cmd_rx so sender
        // clones held by scanner / phase4 / IPC don't back up an unbounded channel.
        // 啟動最小 drain 任務：消費事件與指令通道，避免 scanner / phase4 / IPC 的
        // sender clone 在無人消費時累積（paper_cmd 為 unbounded，更需 drain）。
        let drain_cancel = ctx.cancel.clone();
        let mut event_rx = paper.event_rx;
        let mut cmd_rx = paper.cmd_rx;
        return tokio::spawn(async move {
            loop {
                tokio::select! {
                    _ = drain_cancel.cancelled() => break,
                    evt = event_rx.recv() => {
                        if evt.is_none() { break; }
                    }
                    cmd = cmd_rx.recv() => {
                        match cmd {
                            Some(cmd) => reject_disabled_paper_command(cmd),
                            None => break,
                        }
                    }
                }
            }
            tracing::info!("paper drain task stopped / Paper drain 任務已停止");
        });
    }

    let paper_deps = EventConsumerDeps {
        pipeline_kind: PipelineKind::Paper,
        endpoint_env: None,
        event_rx: paper.event_rx,
        config: Arc::clone(ctx.config),
        cancel: ctx.cancel.clone(),
        initial_balance: paper.initial_balance,
        paper_initial_balance: None,
        taker_fee_rate: live_bindings_opt
            .as_ref()
            .and_then(|b| b.taker_fee)
            .or_else(|| demo_bindings_opt.as_ref().and_then(|b| b.taker_fee)),
        instruments: ctx.instruments.clone(),
        bootstrap_client: ctx.shared_client.clone(), // Paper uses shared REST for kline bootstrap
        shared_client: None,
        bybit_balance: None,
        api_pnl: None,
        pipeline_cmd_rx: Some(paper.cmd_rx),
        // EDGE-P3-1 #62: clone paper_cmd_tx for IntentProcessor's EmitShadowFill
        // dispatch. Paper is the only engine that can fire ε-greedy shadow
        // fills (pipeline_kind guard inside IntentProcessor), so this is the
        // one that matters; Demo/Live get their own sender for symmetry.
        // EDGE-P3-1 #62：clone paper_cmd_tx 給 IntentProcessor 發 EmitShadowFill。
        pipeline_cmd_tx: Some(paper.cmd_tx.clone()),
        // MARKET-KLINES-STALE-1 (2026-04-18): all pipelines clone market_tx.
        // Paper-only design (原 D19) caused kline DB write stall after
        // PAPER-DISABLE-1 defaulted paper off. market_writer.rs:180
        // ON CONFLICT dedup makes multi-producer safe.
        // MARKET-KLINES-STALE-1（2026-04-18）：所有 pipeline 共享 market_tx。
        // 原 D19 僅 Paper 寫入的設計在 PAPER-DISABLE-1 預設關 paper 後導致
        // kline DB 停寫；market_writer.rs:180 ON CONFLICT 去重，多 producer 安全。
        market_data_tx: writers.market_tx.clone(),
        feature_tx: writers.feature_tx.clone(),
        last_tick_ms: Some(Arc::clone(ctx.shared_last_tick_ms)),
        trading_tx: writers.trading_tx.clone(),
        context_tx: writers.context_tx.clone(),
        // EDGE-P3-1 Step 7a: wire training-store writer for paper engine.
        // EDGE-P3-1 Step 7a：接入 paper 引擎訓練資料 writer。
        decision_feature_tx: writers.decision_feature_tx.clone(),
        // EDGE-P3-1 Step 7c: wire shadow-fill writer for paper engine
        // (ε-greedy fills only ever originate here by gate guard).
        // EDGE-P3-1 Step 7c：接 paper 引擎 shadow-fill writer（ε-greedy 僅此處）。
        shadow_fill_tx: writers.shadow_fill_tx.clone(),
        // EXIT-FEATURES-TABLE-1: Paper engine wires exit_feature writer.
        // Must match demo/live (avoid MARKET-KLINES-STALE-1 D19 trap —
        // any single-engine wiring would drop exit labels on that engine).
        // EXIT-FEATURES-TABLE-1：Paper 接入退場特徵 writer。三引擎必須對齊，
        // 避免 MARKET-KLINES-STALE-1 D19 單引擎接線導致的寫入丟失覆轍。
        exit_feature_tx: writers.exit_feature_tx.clone(),
        // INFRA-PREBUILD-1 Part A (2026-04-23): Combine Layer exit-time
        // shadow observation. Same fan-out policy as exit_feature_tx
        // (all three engines share one writer). Dormant default.
        // INFRA-PREBUILD-1 A 部：Combine Layer 退場時刻 shadow 觀測；
        // 三引擎共享,預設 dormant（flag OFF → 0 emit）。
        shadow_exit_tx: writers.shadow_exit_tx.clone(),
        agent_spine_tx: writers.agent_spine_tx.clone(),
        agent_spine_mode: writers.agent_spine_mode,
        lease_transition_tx: writers.lease_transition_tx.clone(),
        exchange_event_rx: None,
        seed_positions: Vec::new(), // Paper has no exchange-side positions to seed
        account_manager: None,
        linucb_runtime: Some(Arc::clone(ctx.shared_linucb_runtime)),
        news_snapshot: Some(Arc::clone(ctx.shared_news_snapshot)),
        risk_store: Some(Arc::clone(&ctx.risk_stores.paper)),
        budget_store: Some(Arc::clone(ctx.budget_store)),
        audit_pool: ctx.audit_pool.clone(),
        symbol_registry: Some(Arc::clone(ctx.symbol_registry)),
        scanner_store: Some(Arc::clone(ctx.scanner_store)),
        shared_risk_level: Some(Arc::clone(&paper.risk_level)),
        is_primary: !ctx.has_live && !ctx.has_demo,
        ready_tx: Some(paper.ready_tx),
        global_exposure_usdt: None,
        cross_engine_tx: Some(ctx.cross_engine_tx.clone()),
        cross_engine_rx: Some(ctx.cross_engine_tx.subscribe()),
        pipeline_health: Some(Arc::clone(&paper.health)),
        canary_handle: ctx.canary_handle.clone(),
        edge_predictor_store: Some(Arc::clone(&ctx.per_engine_predictors.paper)),
        positions_mirror: Some(Arc::clone(&paper.positions_mirror)),
    };
    // Fix 3 (2026-04-14): wrap in crash-only layer so a paper task panic
    // is logged + broadcast + triggers engine-wide cancel (watchdog restart).
    // Previously naked tokio::spawn → task panic died silently, root cause
    // of 2026-04-14 engine zombie incident.
    // 修復 3：包進 crash-only 層，paper task panic 時記 log + 廣播 + 觸發
    // 全引擎 cancel（交 watchdog 重啟）。此前裸 tokio::spawn 導致 task panic
    // 靜默死亡，是 2026-04-14 引擎殭屍事故的根因。
    let h = tokio::spawn(run_pipeline_crash_only(
        PipelineKind::Paper,
        run_event_consumer(paper_deps),
        Arc::clone(&paper.health),
        ctx.cross_engine_tx.clone(),
        ctx.cancel.clone(),
    ));
    info!("paper pipeline spawned (crash-only) / Paper 管線已啟動（crash-only）");
    h
}

/// Spawn the Demo pipeline (conditional — if demo API key exists).
///
/// EN: Binds event consumer main loop to slot-scoped child cancel token (E2
///   BLOCKER #1 fix) — SIGTERM still cascades via parent→child. Wraps in
///   crash-only layer identical to paper.
/// 中: Event consumer 主迴圈綁槽位子 cancel token（E2 BLOCKER #1 修復），SIGTERM
///   仍經父→子連動。crash-only 包裝與 paper 相同。
pub(crate) fn spawn_demo_pipeline(
    ctx: &PipelineSpawnContext<'_>,
    writers: &WriterSenders,
    demo: DemoChannels,
) -> tokio::task::JoinHandle<()> {
    // B-1 Phase 2: capture seed_positions before move into deps below.
    // B-1 Phase 2：在 demo_b 被 move 進 deps 之前先取出 seed_positions。
    let demo_seed_positions = demo.bindings.seed_positions.clone();
    let demo_b = demo.bindings;
    let demo_deps = EventConsumerDeps {
        pipeline_kind: PipelineKind::Demo,
        endpoint_env: Some(BybitEnvironment::Demo),
        event_rx: demo.event_rx,
        config: Arc::clone(ctx.config),
        // PIPELINE-SLOT-1 Phase 2 (E2 BLOCKER #1): bind to slot-scoped
        // child, not engine-wide. SIGTERM still cascades via parent →
        // child; a Phase 3+ demo-scoped teardown would stop only Demo.
        // PIPELINE-SLOT-1 Phase 2（E2 BLOCKER #1）：綁定槽位子 token，
        // 非引擎級。SIGTERM 仍會經父→子連動；Phase 3+ 的 demo-scoped
        // teardown 屆時可只拆 Demo。
        cancel: demo.slot_cancel.clone(),
        initial_balance: demo_b.initial_balance,
        paper_initial_balance: None,
        taker_fee_rate: demo_b.taker_fee,
        instruments: ctx.instruments.clone(),
        bootstrap_client: Some(Arc::clone(&demo_b.rest_client)),
        shared_client: Some(Arc::clone(&demo_b.rest_client)),
        bybit_balance: Some(demo_b.ws_bindings.bybit_balance),
        api_pnl: Some(demo_b.ws_bindings.api_pnl),
        pipeline_cmd_rx: demo.cmd_rx,
        pipeline_cmd_tx: demo.cmd_tx.as_ref().cloned(),
        // MARKET-KLINES-STALE-1 (2026-04-18): all pipelines clone market_tx.
        // Paper-only design (原 D19) caused kline DB write stall after
        // PAPER-DISABLE-1 defaulted paper off. market_writer.rs:180
        // ON CONFLICT dedup makes multi-producer safe.
        // MARKET-KLINES-STALE-1（2026-04-18）：所有 pipeline 共享 market_tx。
        // 原 D19 僅 Paper 寫入的設計在 PAPER-DISABLE-1 預設關 paper 後導致
        // kline DB 停寫；market_writer.rs:180 ON CONFLICT 去重，多 producer 安全。
        market_data_tx: writers.market_tx.clone(),
        feature_tx: None,
        last_tick_ms: Some(Arc::clone(ctx.shared_last_tick_ms)),
        trading_tx: writers.trading_tx.clone(),
        context_tx: writers.context_tx.clone(),
        // EDGE-P3-1 Step 7a: wire training-store writer for demo engine.
        // EDGE-P3-1 Step 7a：接入 demo 引擎訓練資料 writer。
        decision_feature_tx: writers.decision_feature_tx.clone(),
        // EDGE-P3-1 Step 7c: wire shadow-fill writer for defense-in-depth
        // logging on demo (gate still guards against emission here).
        // EDGE-P3-1 Step 7c：demo 亦接 shadow-fill writer 作深度防禦日誌。
        shadow_fill_tx: writers.shadow_fill_tx.clone(),
        // EXIT-FEATURES-TABLE-1: Demo wires exit_feature writer (see Paper note).
        // EXIT-FEATURES-TABLE-1：Demo 接入退場特徵 writer（見 Paper 說明）。
        exit_feature_tx: writers.exit_feature_tx.clone(),
        // INFRA-PREBUILD-1 Part A (2026-04-23): Combine Layer exit-time
        // shadow observation. Same fan-out policy as exit_feature_tx
        // (all three engines share one writer). Dormant default.
        // INFRA-PREBUILD-1 A 部：Combine Layer 退場時刻 shadow 觀測；
        // 三引擎共享,預設 dormant（flag OFF → 0 emit）。
        shadow_exit_tx: writers.shadow_exit_tx.clone(),
        agent_spine_tx: writers.agent_spine_tx.clone(),
        agent_spine_mode: writers.agent_spine_mode,
        lease_transition_tx: writers.lease_transition_tx.clone(),
        exchange_event_rx: Some(demo_b.ws_bindings.exchange_event_rx),
        seed_positions: demo_seed_positions,
        account_manager: Some(demo_b.account_manager),
        linucb_runtime: Some(Arc::clone(ctx.shared_linucb_runtime)),
        news_snapshot: Some(Arc::clone(ctx.shared_news_snapshot)),
        risk_store: Some(Arc::clone(&ctx.risk_stores.demo)),
        budget_store: Some(Arc::clone(ctx.budget_store)),
        audit_pool: ctx.audit_pool.clone(),
        symbol_registry: Some(Arc::clone(ctx.symbol_registry)),
        scanner_store: Some(Arc::clone(ctx.scanner_store)),
        shared_risk_level: Some(Arc::clone(&demo_b.risk_level)),
        is_primary: !ctx.has_live,
        ready_tx: demo.ready_tx,
        global_exposure_usdt: Some(Arc::clone(ctx.global_exposure_usdt)),
        cross_engine_tx: Some(ctx.cross_engine_tx.clone()),
        cross_engine_rx: Some(ctx.cross_engine_tx.subscribe()),
        pipeline_health: Some(Arc::clone(&demo_b.health)),
        canary_handle: ctx.canary_handle.clone(),
        edge_predictor_store: Some(Arc::clone(&ctx.per_engine_predictors.demo)),
        positions_mirror: Some(Arc::clone(&demo.positions_mirror)),
    };
    // Fix 3 (2026-04-14): same crash-only wrapper as paper.
    // 修復 3：同 paper 的 crash-only 包裝。
    let h = tokio::spawn(run_pipeline_crash_only(
        PipelineKind::Demo,
        run_event_consumer(demo_deps),
        Arc::clone(&demo_b.health),
        ctx.cross_engine_tx.clone(),
        ctx.cancel.clone(),
    ));
    info!("demo pipeline spawned (crash-only) / Demo 管線已啟動（crash-only）");
    h
}

/// Spawn the Live pipeline on a dedicated OS thread with catch_unwind (D17).
///
/// EN: Live gets its own tokio runtime (4 worker threads) to isolate bursty
///   market-data work from paper/demo. A panic inside the live runtime is
///   caught, logged, broadcast as `EngineEvent::Crashed(Live)`, and triggers
///   engine-wide cancel (crash-only parity). Clean authorization revoke
///   uses a different path (`LiveAuthWatcher` → `live_slot.teardown()`) that
///   only cancels the slot-scoped child token.
/// 中: Live 有獨立 tokio runtime（4 worker threads）隔離突發行情工作，與
///   paper/demo 分離。Runtime 內 panic 經 catch_unwind 捕獲 + log + 廣播
///   `EngineEvent::Crashed(Live)` + 觸發全引擎 cancel（crash-only 對齊）。
///   乾淨的授權撤銷走另一路（`LiveAuthWatcher` → `live_slot.teardown()`），
///   僅取消槽位子 token。
pub(crate) fn spawn_live_pipeline(
    ctx: &PipelineSpawnContext<'_>,
    writers: &WriterSenders,
    live: LiveChannels,
) -> std::thread::JoinHandle<()> {
    // B-1 Phase 2: capture seed_positions before move into deps below.
    // B-1 Phase 2：在 live_b 被 move 進 deps 之前先取出 seed_positions。
    let live_seed_positions = live.bindings.seed_positions.clone();
    let live_b = live.bindings;
    let live_deps = EventConsumerDeps {
        pipeline_kind: PipelineKind::Live,
        endpoint_env: Some(live_bybit_environment()),
        event_rx: live.event_rx,
        config: Arc::clone(ctx.config),
        // PIPELINE-SLOT-1 Phase 2 (E2 BLOCKER #1 fix): bind the event
        // consumer main loop to the slot-scoped child token, not the
        // engine-wide `cancel`. Before this fix, the event consumer
        // watched only the engine-wide token — `live_slot.teardown()`
        // would cancel WS supervisor / listener / balance refresh but
        // leave the Live event consumer running with a cloned
        // `Arc<BybitRestClient>`, still processing fan-out market events
        // and still **dispatching orders**. Teardown was skin-deep.
        //
        // With the child token bound here, `teardown()` cancels the
        // child → the `_ = cancel.cancelled() => break` arm in
        // `event_consumer/mod.rs::run_event_consumer` (around line 755)
        // fires → the consumer exits its main loop → rest_client Arc
        // drops → no further order dispatch. SIGTERM still works via
        // parent→child cascade (tokio-util CancellationToken contract).
        //
        // PIPELINE-SLOT-1 Phase 2（E2 BLOCKER #1 修復）：把 event consumer
        // 主迴圈綁到槽位子 token，而非引擎級 `cancel`。修復前 event
        // consumer 僅監看引擎級 token — `live_slot.teardown()` 會拆
        // WS supervisor / listener / balance refresh，但 Live event
        // consumer 仍在跑（持有 `Arc<BybitRestClient>` clone）、仍處理
        // fan-out 市場事件、仍**下單**。此為皮毛式 teardown。
        //
        // 綁定子 token 後：`teardown()` 取消子 → event_consumer 主迴圈
        // 的 `_ = cancel.cancelled() => break` 觸發（約 mod.rs:755）→
        // consumer 退出、rest_client Arc drop → 不再下單。SIGTERM 仍
        // 經父→子連動（tokio-util CancellationToken 契約）正常作用。
        cancel: live.slot_cancel.clone(),
        initial_balance: live_b.initial_balance,
        paper_initial_balance: None,
        taker_fee_rate: live_b.taker_fee,
        instruments: ctx.instruments.clone(),
        bootstrap_client: Some(Arc::clone(&live_b.rest_client)),
        shared_client: Some(Arc::clone(&live_b.rest_client)),
        bybit_balance: Some(live_b.ws_bindings.bybit_balance),
        api_pnl: Some(live_b.ws_bindings.api_pnl),
        pipeline_cmd_rx: live.cmd_rx,
        pipeline_cmd_tx: live.cmd_tx.as_ref().cloned(),
        // MARKET-KLINES-STALE-1 (2026-04-18): all pipelines clone market_tx.
        // Paper-only design (原 D19) caused kline DB write stall after
        // PAPER-DISABLE-1 defaulted paper off. market_writer.rs:180
        // ON CONFLICT dedup makes multi-producer safe.
        // MARKET-KLINES-STALE-1（2026-04-18）：所有 pipeline 共享 market_tx。
        // 原 D19 僅 Paper 寫入的設計在 PAPER-DISABLE-1 預設關 paper 後導致
        // kline DB 停寫；market_writer.rs:180 ON CONFLICT 去重，多 producer 安全。
        market_data_tx: writers.market_tx.clone(),
        feature_tx: None,
        last_tick_ms: Some(Arc::clone(ctx.shared_last_tick_ms)),
        trading_tx: writers.trading_tx.clone(),
        context_tx: writers.context_tx.clone(),
        // EDGE-P3-1 Step 7a: wire training-store writer for live engine.
        // EDGE-P3-1 Step 7a：接入 live 引擎訓練資料 writer。
        decision_feature_tx: writers.decision_feature_tx.clone(),
        // EDGE-P3-1 Step 7c: wire shadow-fill writer for defense-in-depth
        // logging on live (gate still guards against emission here).
        // EDGE-P3-1 Step 7c：live 亦接 shadow-fill writer 作深度防禦日誌。
        shadow_fill_tx: writers.shadow_fill_tx.clone(),
        // EXIT-FEATURES-TABLE-1: Live wires exit_feature writer (see Paper note).
        // EXIT-FEATURES-TABLE-1：Live 接入退場特徵 writer（見 Paper 說明）。
        exit_feature_tx: writers.exit_feature_tx.clone(),
        // INFRA-PREBUILD-1 Part A (2026-04-23): Combine Layer exit-time
        // shadow observation. Same fan-out policy as exit_feature_tx
        // (all three engines share one writer). Dormant default.
        // INFRA-PREBUILD-1 A 部：Combine Layer 退場時刻 shadow 觀測；
        // 三引擎共享,預設 dormant（flag OFF → 0 emit）。
        shadow_exit_tx: writers.shadow_exit_tx.clone(),
        agent_spine_tx: writers.agent_spine_tx.clone(),
        agent_spine_mode: writers.agent_spine_mode,
        lease_transition_tx: writers.lease_transition_tx.clone(),
        exchange_event_rx: Some(live_b.ws_bindings.exchange_event_rx),
        seed_positions: live_seed_positions,
        account_manager: Some(live_b.account_manager),
        linucb_runtime: Some(Arc::clone(ctx.shared_linucb_runtime)),
        news_snapshot: Some(Arc::clone(ctx.shared_news_snapshot)),
        risk_store: Some(Arc::clone(&ctx.risk_stores.live)),
        budget_store: Some(Arc::clone(ctx.budget_store)),
        audit_pool: ctx.audit_pool.clone(),
        symbol_registry: Some(Arc::clone(ctx.symbol_registry)),
        scanner_store: Some(Arc::clone(ctx.scanner_store)),
        shared_risk_level: Some(Arc::clone(&live_b.risk_level)),
        is_primary: true,
        ready_tx: live.ready_tx,
        global_exposure_usdt: Some(Arc::clone(ctx.global_exposure_usdt)),
        cross_engine_tx: Some(ctx.cross_engine_tx.clone()),
        cross_engine_rx: Some(ctx.cross_engine_tx.subscribe()),
        pipeline_health: Some(Arc::clone(&live_b.health)),
        canary_handle: ctx.canary_handle.clone(),
        edge_predictor_store: Some(Arc::clone(&ctx.per_engine_predictors.live)),
        positions_mirror: Some(Arc::clone(&live.positions_mirror)),
    };

    // D17: Live runs on dedicated OS thread with catch_unwind for panic isolation.
    // D17：Live 在獨立 OS 線程運行，catch_unwind 隔離 panic。
    //
    // PIPELINE-SLOT-1 Phase 2/3: `live_cancel` is the **slot-scoped child
    // token** returned by `live_slot.try_spawn()` — already guaranteed
    // Some by the outer match arm (E2 MAJOR #2 fix: Option-pair refactor
    // eliminated the Phase 2 `.expect()` previously present here).
    // Before Phase 2 this was `cancel.clone()` (engine-wide). The switch
    // lets the Phase 3 `LiveAuthWatcher` tear down the Live pipeline alone
    // (cancelling this child) without killing demo/paper. The crash-only
    // Fix 3 (2026-04-14) parity is preserved via `engine_wide_cancel`
    // below: a Live panic still cancels the engine-wide token as before.
    //
    // PIPELINE-SLOT-1 Phase 2/3：`live_cancel` 是 `live_slot.try_spawn()`
    // 回傳的**槽位子 token** — 由外層 match arm 保證 Some（E2 MAJOR #2
    // 修復：Option-pair 重構消除原有的 `.expect()`）。Phase 2 前為
    // `cancel.clone()`（引擎級）。換成子 token 後，Phase 3 `LiveAuthWatcher`
    // 可以只拆 Live（取消本子 token）而不波及 demo/paper。Fix 3（2026-04-14）的
    // crash-only 對齊藉由下方 `engine_wide_cancel` 保留：Live panic
    // 依舊取消引擎級 token。
    let live_cancel = live.slot_cancel.clone();
    // `engine_wide_cancel` is the parent token; only the panic handler
    // uses it (crash-only parity). Clean auth-revoke teardown uses the
    // child token instead (via `LiveAuthWatcher` → `live_slot.teardown()`).
    // `engine_wide_cancel` 為父 token；僅 panic handler 使用（crash-only 對齊）。
    // 乾淨的授權撤銷 teardown 走子 token（經 `LiveAuthWatcher` → `live_slot.teardown()`）。
    let engine_wide_cancel = ctx.cancel.clone();
    let live_crash_tx = ctx.cross_engine_tx.clone();
    let live_health_ref = Arc::clone(&live_b.health);
    let thread_handle = std::thread::Builder::new()
        .name("oc-live-rt".into())
        .spawn(move || {
            // worker_threads(4): bumped from 2 (2026-04-11) after observing
            // 1808 "live pipeline lagging, tick dropped" warnings in a single
            // session. Live runs WS reader + tick consumer + dispatch task +
            // reconciler poller + private WS auth/heartbeat concurrently;
            // 2 workers serialized them too tightly and the bounded tick
            // channel overflowed under bursty market data. 4 workers gives
            // headroom while keeping Live's runtime isolated from main
            // (paper/demo + scanner + everything else still on default rt).
            // worker_threads(4)：2026-04-11 從 2 提升 — 一個 session 觀察到
            // 1808 條 "live pipeline lagging, tick dropped" 警告。Live 同時跑
            // WS reader + tick consumer + 派發任務 + reconciler poller + 私有
            // WS auth/heartbeat，2 workers 串行化過緊導致 bounded tick 通道
            // 在突發行情下溢出。4 workers 留出餘裕，仍保持 Live runtime 與
            // 主 runtime（paper/demo + scanner 等）的隔離。
            let live_rt = tokio::runtime::Builder::new_multi_thread()
                .worker_threads(4)
                .enable_all()
                .thread_name("oc-live")
                .build()
                .expect("failed to build live runtime / 構建 live runtime 失敗");
            let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                live_rt.block_on(async {
                    run_event_consumer(live_deps).await;
                    live_cancel.cancelled().await;
                });
            }));
            if let Err(panic_info) = result {
                let msg = panic_info
                    .downcast_ref::<&str>()
                    .copied()
                    .or_else(|| panic_info.downcast_ref::<String>().map(|s| s.as_str()))
                    .unwrap_or("unknown panic");
                tracing::error!(
                    target: "openclaw_engine::panic",
                    kind = "live",
                    panic = msg,
                    "live pipeline PANICKED (crash-only) — broadcasting Crashed + cancelling engine / \
                     Live 管線 panic（crash-only）— 廣播 Crashed + 取消引擎"
                );
                live_health_ref.store(
                    PipelineHealth::Down as u8,
                    std::sync::atomic::Ordering::Relaxed,
                );
                let _ = live_crash_tx
                    .send(EngineEvent::Crashed(PipelineKind::Live));
                // Fix 3 (2026-04-14): Live now also triggers engine-wide
                // cancel to force crash-only semantics parity with
                // paper/demo. A Live panic previously left paper/demo
                // running — operator intent is all-or-nothing: if Live
                // cannot execute trades, we must not keep paper/demo
                // pretending to learn against stale state.
                //
                // PIPELINE-SLOT-1 Phase 2/3: we must cancel the **engine-
                // wide** token here, not the slot-scoped child — Fix 3's
                // crash-only invariant takes the engine down. (A clean
                // authorization revocation takes a different path: see
                // `LiveAuthWatcher` spawned earlier, which calls
                // `live_slot.teardown()` to cancel the child only.)
                //
                // 修復 3：Live 也觸發全引擎 cancel 以與 paper/demo 的 crash-only
                // 語義對齊。Live panic 以前會讓 paper/demo 繼續跑 — operator
                // 意圖是全有或全無：Live 無法下單時 paper/demo 不應繼續在
                // 陳舊狀態上「假裝學習」。
                //
                // PIPELINE-SLOT-1 Phase 2/3：此處必須取消**引擎級** token
                // 而非槽位子 token — Fix 3 的 crash-only 不變式要求整機下去。
                // 乾淨的授權撤銷走另一條路：見前方 spawn 的 `LiveAuthWatcher`，
                // 呼叫 `live_slot.teardown()` 只取消子 token。
                engine_wide_cancel.cancel();
            }
        })
        .expect("failed to spawn live thread / 啟動 live 線程失敗");

    info!("live pipeline spawned (dedicated OS thread) / Live 管線已啟動（獨立 OS 線程）");
    thread_handle
}

// ──────────────────────────────────────────────────────────────────────────
// LiveSpawnBundle + build_live_pipeline_spawner
// BLOCKER-1 (E2 round-2, 2026-04-27): extracted from main.rs::async_main
// to bring main.rs under the 1200-line hard cap (CLAUDE.md §九).
// The spawner closure captures ~19 Arcs; grouping them in a struct keeps
// the function signature short (one bundle arg) while retaining the same
// semantics as the inline closure in main.rs before this refactor.
//
// BLOCKER-1（E2 round-2，2026-04-27）：從 main.rs::async_main 抽出，
// 讓 main.rs 回到 §九 1200 行硬上限以內。spawner closure 捕獲 ~19 個 Arc；
// 打包進 struct 讓 fn 簽名精簡（單一 bundle 參數），語意完全不變。
// ──────────────────────────────────────────────────────────────────────────

/// Arc bundle captured by the live pipeline spawner closure.
/// Extracted from `main.rs::async_main` (BLOCKER-1, E2 round-2, 2026-04-27).
///
/// `live_cmd_slot` and `live_event_slot` are populated by the spawner on each
/// successful respawn so fan-out and IPC observe the fresh senders
/// without engine restart.
///
/// Live pipeline spawner closure 捕獲的 Arc bundle。
/// 從 `main.rs::async_main` 抽出（BLOCKER-1，E2 round-2，2026-04-27）。
/// `live_cmd_slot` / `live_event_slot` 由 spawner 於每次成功 respawn 後
/// 填入，讓 fan-out 和 IPC 無需重啟就能觀察到新 sender。
pub(crate) struct LiveSpawnBundle {
    pub config: Arc<ConfigManager>,
    pub cancel: CancellationToken,
    pub instruments: Option<Arc<InstrumentInfoCache>>,
    pub shared_client: Option<Arc<BybitRestClient>>,
    pub risk_stores: PerEngineRiskStores,
    pub budget_store: Arc<ConfigStore<BudgetConfig>>,
    pub audit_pool: Option<sqlx::PgPool>,
    pub symbol_registry: Arc<SymbolRegistry>,
    pub scanner_store: Arc<ConfigStore<ScannerConfig>>,
    pub shared_linucb_runtime: Arc<LinUcbRuntime>,
    pub shared_news_snapshot: Arc<openclaw_engine::news::NewsContextSnapshot>,
    pub shared_last_tick_ms: Arc<std::sync::atomic::AtomicU64>,
    pub canary_handle: CanaryWriterHandle,
    pub per_engine_predictors: Arc<PerEnginePredictors>,
    pub cross_engine_tx: broadcast::Sender<EngineEvent>,
    pub global_exposure_usdt: Arc<std::sync::atomic::AtomicU64>,
    pub live_positions_mirror: Arc<parking_lot::RwLock<std::collections::HashMap<String, bool>>>,
    pub live_cmd_slot: LiveCmdSenderSlot,
    pub live_event_slot: LiveEventSenderSlot,
    pub has_demo: bool,
    // Writer channel senders — cloned into each respawn cycle.
    // 寫入 channel sender — 每次 respawn 週期各 clone 一份。
    pub market_tx: Option<mpsc::Sender<MarketDataMsg>>,
    pub feature_tx: Option<mpsc::Sender<FeatureSnapshot>>,
    pub trading_tx: Option<mpsc::Sender<TradingMsg>>,
    pub context_tx: Option<mpsc::Sender<DecisionContextMsg>>,
    pub decision_feature_tx: Option<mpsc::Sender<DecisionFeatureMsg>>,
    pub shadow_fill_tx: Option<mpsc::Sender<ShadowFillMsg>>,
    pub exit_feature_tx: Option<mpsc::Sender<ExitFeatureRow>>,
    pub shadow_exit_tx: Option<mpsc::Sender<ShadowExitMsg>>,
    pub agent_spine_tx: Option<mpsc::Sender<AgentSpineMsg>>,
    pub agent_spine_mode: AgentSpineMode,
    pub lease_transition_tx: Option<LeaseTransitionSender>,
}

/// Build the `LivePipelineSpawner` closure from a `LiveSpawnBundle`.
///
/// Returns an `Arc<dyn Fn(SpawnOutput) -> LivePipelineSpawnResult + Send + Sync>`.
/// Invoked by `LiveAuthWatcher` on every successful `slot_op.try_spawn`:
///   * Builds fresh tokio cmd / event channels for this respawn cycle.
///   * Writes new senders into `live_cmd_slot` / `live_event_slot` so
///     fan-out + IPC + governance observe the rotation immediately.
///   * Calls `spawn_live_pipeline` to boot the OS thread running
///     `run_event_consumer` (state_writer / snapshot_writer / fills).
///   * Returns the OS thread `JoinHandle` so shutdown can `.join()`.
///
/// Without this callback the pipeline is half-spawned: WS tasks are up but
/// no OS thread consumes events → snapshots never refresh → 8-day silent
/// regression (LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN, 2026-04-27).
///
/// BLOCKER-1 extraction: this fn was an inline closure in main.rs before
/// 2026-04-27. Moved here to stay under the §九 1200-line hard cap.
///
/// Live pipeline spawner closure 構造器。
///
/// 回傳 `Arc<dyn Fn(SpawnOutput) -> LivePipelineSpawnResult + Send + Sync>`。
/// 由 `LiveAuthWatcher` 在每次 `slot_op.try_spawn` 成功後呼叫：
///   * 為此 respawn 週期建立新 tokio cmd / event 通道。
///   * 新 sender 寫入 `live_cmd_slot` / `live_event_slot`，
///     fan-out + IPC + governance 立即觀察到輪換。
///   * 呼叫 `spawn_live_pipeline` 啟動跑 `run_event_consumer` 的 OS 線程
///     （state_writer / snapshot_writer / fills 生產者）。
///   * 回傳 OS 線程 `JoinHandle` 供 shutdown 序列 `.join()`。
///
/// BLOCKER-1 抽取：2026-04-27 前為 main.rs 的 inline closure；
/// 移至此處以符合 §九 1200 行硬上限。
pub(crate) fn build_live_pipeline_spawner(
    b: LiveSpawnBundle,
) -> crate::live_auth_watcher::LivePipelineSpawner {
    // All fields are cloned cheaply (Arc / clone of primitive), so
    // constructing the closure is ~1 µs.
    // 所有欄位 Arc clone / 基本型別 copy，closure 構造 ~1 µs。
    let config_c = b.config;
    let cancel_c = b.cancel;
    let instruments_c = b.instruments;
    let shared_client_c = b.shared_client;
    let risk_stores_c = b.risk_stores;
    let budget_store_c = b.budget_store;
    let audit_pool_c = b.audit_pool;
    let symbol_registry_c = b.symbol_registry;
    let scanner_store_c = b.scanner_store;
    let linucb_c = b.shared_linucb_runtime;
    let news_c = b.shared_news_snapshot;
    let last_tick_ms_c = b.shared_last_tick_ms;
    let canary_c = b.canary_handle;
    let per_engine_predictors_c = b.per_engine_predictors;
    let cross_engine_tx_c = b.cross_engine_tx;
    let global_exposure_c = b.global_exposure_usdt;
    let positions_mirror_c = b.live_positions_mirror;
    let live_cmd_slot_c = b.live_cmd_slot;
    let live_event_slot_c = b.live_event_slot;
    let has_demo = b.has_demo;
    let writers_c_market = b.market_tx;
    let writers_c_feature = b.feature_tx;
    let writers_c_trading = b.trading_tx;
    let writers_c_context = b.context_tx;
    let writers_c_decision_feature = b.decision_feature_tx;
    let writers_c_shadow_fill = b.shadow_fill_tx;
    let writers_c_exit_feature = b.exit_feature_tx;
    let writers_c_shadow_exit = b.shadow_exit_tx;
    let writers_c_agent_spine = b.agent_spine_tx;
    let writers_c_agent_spine_mode = b.agent_spine_mode;
    let writers_c_lease_transition = b.lease_transition_tx;

    Arc::new(move |spawn_output: crate::pipeline_slot::SpawnOutput| -> crate::live_auth_watcher::LivePipelineSpawnResult {
        // Build fresh channels for this spawn cycle.
        // 為本輪 spawn 建立新通道。
        let (new_cmd_tx, new_cmd_rx) = tokio::sync::mpsc::unbounded_channel();
        let (new_event_tx, new_event_rx) = mpsc::channel::<Arc<PriceEvent>>(1024);
        let (new_ready_tx, _new_ready_rx) = tokio::sync::oneshot::channel::<()>();

        // Write fresh senders into slots so fan-out / IPC / scanner / phase4 /
        // set_system_mode observe the new pair on the next read (~1 µs write).
        // 寫入 slot 讓 fan-out / IPC / scanner / phase4 / set_system_mode
        // 下次讀取見到新 pair（~1 µs 寫鎖）。
        *live_cmd_slot_c.write() = Some(new_cmd_tx.clone());
        *live_event_slot_c.write() = Some(new_event_tx);

        let writers = WriterSenders {
            market_tx: writers_c_market.clone(),
            feature_tx: writers_c_feature.clone(),
            trading_tx: writers_c_trading.clone(),
            context_tx: writers_c_context.clone(),
            decision_feature_tx: writers_c_decision_feature.clone(),
            shadow_fill_tx: writers_c_shadow_fill.clone(),
            exit_feature_tx: writers_c_exit_feature.clone(),
            shadow_exit_tx: writers_c_shadow_exit.clone(),
            agent_spine_tx: writers_c_agent_spine.clone(),
            agent_spine_mode: writers_c_agent_spine_mode,
            lease_transition_tx: writers_c_lease_transition.clone(),
        };
        let ctx = PipelineSpawnContext {
            config: &config_c,
            cancel: &cancel_c,
            instruments: &instruments_c,
            shared_client: &shared_client_c,
            risk_stores: &risk_stores_c,
            budget_store: &budget_store_c,
            audit_pool: audit_pool_c.clone(),
            symbol_registry: &symbol_registry_c,
            scanner_store: &scanner_store_c,
            shared_linucb_runtime: &linucb_c,
            shared_news_snapshot: &news_c,
            shared_last_tick_ms: &last_tick_ms_c,
            canary_handle: &canary_c,
            per_engine_predictors: &per_engine_predictors_c,
            cross_engine_tx: &cross_engine_tx_c,
            global_exposure_usdt: &global_exposure_c,
            has_live: true,
            has_demo,
        };
        let live_channels = LiveChannels {
            bindings: spawn_output.bindings,
            slot_cancel: spawn_output.slot_cancel_token,
            event_rx: new_event_rx,
            cmd_tx: Some(new_cmd_tx),
            cmd_rx: Some(new_cmd_rx),
            ready_tx: Some(new_ready_tx),
            positions_mirror: Arc::clone(&positions_mirror_c),
        };
        let thread_handle = spawn_live_pipeline(&ctx, &writers, live_channels);
        Ok(thread_handle)
    })
}
