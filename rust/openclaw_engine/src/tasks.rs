//! Background task spawning — DB writers, fee refresh, instrument refresh,
//! news pipeline, teacher consumer loop, position reconciler.
//! 後台任務啟動 — DB 寫入器、費率刷新、品種規格刷新、
//! 新聞管線、Teacher consumer loop、持倉對帳器。

// E5-P1-5: generic tick-loop spawner extracted from the ~4 duplicated
//         tokio::spawn/interval/select! blocks in this file (orphan §九).
// E5-P1-5：本檔案 4+ 個重複 tokio::spawn/interval/select! 區塊抽出的通用 tick-loop spawner（§九 孤兒抽取）。
mod supervised_spawn;
use supervised_spawn::spawn_cancellable_interval;

use openclaw_engine::account_manager::AccountManager;
use openclaw_engine::bybit_rest_client::{BybitEnvironment, BybitRestClient};
use openclaw_engine::config::{ConfigManager, ConfigStore, LearningConfig};
use openclaw_engine::database::pool::DbPool;
use openclaw_engine::ipc_server::{AuditPoolSlot, BudgetTrackerSlot, TeacherLoopSlot};
use openclaw_engine::scanner::registry::SymbolRegistry;
use openclaw_engine::tick_pipeline::PipelineCommand;
use std::sync::Arc;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

/// Spawn periodic fee rate refresh (every 1h) + staleness monitor (alarm if >2h).
/// 啟動定期費率刷新（每 1h）和新鮮度監控（>2h 告警）。
pub(crate) fn spawn_fee_rate_tasks(
    acct: &Arc<AccountManager>,
    client: &Arc<BybitRestClient>,
    cancel: &CancellationToken,
) {
    // Periodic refresh: re-fetch fee rates hourly so the 2h cost-gate staleness
    // guard has room for one missed refresh before failing closed.
    // 每小時刷新費率；2h 成本門過期保護可容忍一次刷新失敗。
    // E5-P1-5 adoption: use shared spawn_cancellable_interval helper; cancel
    //                   log message preserved byte-for-byte.
    // E5-P1-5 採用：使用共享的 spawn_cancellable_interval；cancel log 完全保留。
    {
        let acct_refresh = Arc::clone(acct);
        let client_refresh = Arc::clone(client);
        let _ = spawn_cancellable_interval(
            "fee_rate_refresh",
            std::time::Duration::from_secs(3600),
            Some("fee_rate refresh task stopping (cancel) / 費率刷新任務停止"),
            cancel.clone(),
            move || {
                let acct = Arc::clone(&acct_refresh);
                let client = Arc::clone(&client_refresh);
                async move {
                    match acct.refresh_fee_rates(&*client, "linear").await {
                        Ok(count) => {
                            info!(symbols = count, "fee rates refreshed (1h) / 費率已刷新")
                        }
                        Err(e) => {
                            warn!(error = %e, "fee rate refresh failed / 費率刷新失敗")
                        }
                    }
                }
            },
        );
    }

    // Staleness monitor: alarm if fee rates haven't refreshed in >2h.
    // The exchange cost gate also rejects while stale; this log makes it visible.
    // 費率新鮮度監控：>2h 未刷新告警；exchange 成本門也會拒絕。
    {
        let acct_mon = Arc::clone(acct);
        let cancel_mon = cancel.clone();
        tokio::spawn(async move {
            let mut tick = tokio::time::interval(std::time::Duration::from_secs(15 * 60));
            tick.tick().await;
            loop {
                tokio::select! {
                    _ = cancel_mon.cancelled() => break,
                    _ = tick.tick() => {
                        let last = acct_mon.last_fee_refresh_ms();
                        if last == 0 { continue; }
                        let now = std::time::SystemTime::now()
                            .duration_since(std::time::UNIX_EPOCH)
                            .unwrap_or_default()
                            .as_millis() as u64;
                        let age_h = (now.saturating_sub(last)) as f64 / 3_600_000.0;
                        if age_h > 2.0 {
                            warn!(
                                age_hours = format!("{:.1}", age_h),
                                "fee rates STALE >2h — cost gate will fail closed / 費率過期，成本門將 fail-closed"
                            );
                        }
                    }
                }
            }
        });
    }
}

/// Spawn periodic instrument info refresh (every 4 hours).
/// R-05：定期刷新合約信息（每 4 小時）。
///
/// E5-P1-5 adoption: uses shared ``spawn_cancellable_interval``. Legacy
///                   behaviour kept byte-for-byte: silent cancel (no log line
///                   on shutdown) matches the prior ``_ = cancel.cancelled()
///                   => break`` arm.
/// E5-P1-5 採用：使用共享的 ``spawn_cancellable_interval``。舊行為完全保留：
///                cancel 時靜默退出（不 log），對應舊 ``break`` 分支。
pub(crate) fn spawn_instrument_refresh(
    icache: &Arc<openclaw_engine::instrument_info::InstrumentInfoCache>,
    client: &Arc<BybitRestClient>,
    cancel: &CancellationToken,
) {
    let refresh_cache = Arc::clone(icache);
    let refresh_client = Arc::clone(client);
    let _ = spawn_cancellable_interval(
        "instrument_refresh",
        std::time::Duration::from_secs(4 * 3600),
        None,
        cancel.clone(),
        move || {
            let cache = Arc::clone(&refresh_cache);
            let client = Arc::clone(&refresh_client);
            async move {
                match cache.refresh(&*client, "linear").await {
                    Ok(n) => info!(symbols = n, "instrument info refreshed / 品種規格已刷新"),
                    Err(e) => warn!(error = %e, "instrument refresh failed / 品種刷新失敗"),
                }
            }
        },
    );
}

/// Initialize BudgetTracker + audit pool and inject into IPC server slots.
/// 初始化 BudgetTracker + 審計 pool 並注入 IPC 服務器槽位。
pub(crate) async fn init_budget_and_audit(
    db_pool: &Arc<DbPool>,
    budget_tracker_slot: &BudgetTrackerSlot,
    audit_pool_slot: &AuditPoolSlot,
) {
    // ARCH-RC1 1C-2-E: inject audit pool into IPC server slot.
    // ARCH-RC1 1C-2-E：注入審計 pool 到 IPC server 槽位。
    if let Some(pg) = db_pool.get() {
        audit_pool_slot.write().await.replace(pg.clone());
        info!("ARCH-RC1 audit pool wired to IPC / 審計 pool 已接入 IPC");
    }

    if db_pool.is_available() {
        match openclaw_engine::ai_budget::BudgetTracker::new(Arc::clone(db_pool)).await {
            Ok(tracker) => {
                budget_tracker_slot.write().await.replace(Arc::new(tracker));
                info!("BudgetTracker initialized / AI 預算追蹤器已初始化");
            }
            Err(e) => {
                warn!(error = %e, "BudgetTracker init failed, AI budget enforcement disabled / 預算追蹤器初始化失敗");
            }
        }
    } else {
        warn!(
            "db_pool unavailable, BudgetTracker not started / db_pool 不可用，BudgetTracker 未啟動"
        );
    }
}

/// Spawn the Phase 4.1 TeacherConsumerLoop (DEFAULT-OFF until E3 R6 audit PASS).
/// Phase 4.1：構造並 spawn TeacherConsumerLoop（預設關閉）。
pub(crate) async fn spawn_teacher_consumer_loop(
    db_pool: &Arc<DbPool>,
    budget_tracker_slot: &BudgetTrackerSlot,
    teacher_loop_slot: TeacherLoopSlot,
    pipeline_cmd_tx: tokio::sync::mpsc::UnboundedSender<PipelineCommand>,
    governance_wrapper: &Arc<openclaw_engine::claude_teacher::GovernanceCoreWrapper>,
) {
    if !db_pool.is_available() {
        warn!("Phase 4.1 consumer loop skipped: db_pool unavailable / db_pool 不可用，consumer loop 跳過");
        return;
    }

    let budget_opt = budget_tracker_slot.read().await.clone();
    let Some(budget) = budget_opt else {
        warn!("Phase 4.1 consumer loop skipped: BudgetTracker not initialized / 預算追蹤器未初始化，consumer loop 跳過");
        return;
    };

    use openclaw_engine::claude_teacher::{
        AnthropicClient, ClaudeTeacher, ConsumerLoopConfig, DirectiveApplier, GovernanceCheck,
        LlmClient, OutcomeTracker, PipelineCommandSink, StrategyIpcSink, TeacherConsumerLoop,
    };
    use std::sync::atomic::AtomicBool;

    let model = "claude-sonnet-4-5";
    let llm_client: Arc<dyn LlmClient + Send + Sync> = Arc::new(AnthropicClient::new(model));
    let teacher = Arc::new(ClaudeTeacher::new(
        llm_client,
        Some(Arc::clone(&budget)),
        Arc::clone(db_pool),
        model,
    ));
    let governance_for_applier: Arc<dyn GovernanceCheck> =
        Arc::clone(governance_wrapper) as Arc<dyn GovernanceCheck>;
    let ipc_sink: Arc<dyn StrategyIpcSink> = Arc::new(PipelineCommandSink::new(pipeline_cmd_tx));
    let applier = Arc::new(DirectiveApplier::new(
        governance_for_applier,
        Some(ipc_sink),
        Arc::clone(db_pool),
    ));
    let outcome_tracker = Arc::new(OutcomeTracker::new(Arc::clone(db_pool)));
    // Default-off until E3 R6 PASS. Operator flips via IPC.
    // E3 R6 通過前預設關閉。Operator 透過 IPC 翻開。
    let enabled = Arc::new(AtomicBool::new(false));
    let consumer_loop = Arc::new(TeacherConsumerLoop::new(
        teacher,
        applier,
        Some(outcome_tracker),
        ConsumerLoopConfig::production_defaults(),
        Arc::clone(&enabled),
    ));
    // Inject handles into IPC slot BEFORE spawn so the handlers see
    // them as soon as the loop is alive.
    // 在 spawn 前先把句柄注入 IPC 槽位，loop 一啟動 handler 就看得見。
    {
        use openclaw_engine::ipc_server::TeacherLoopHandles;
        let handles = TeacherLoopHandles {
            enabled: consumer_loop.enabled_handle(),
            status: consumer_loop.status(),
        };
        teacher_loop_slot.write().await.replace(handles);
    }
    let _consumer_handle = Arc::clone(&consumer_loop).spawn();
    info!(
        "Phase 4.1 TeacherConsumerLoop spawned + IPC handles injected (DEFAULT-OFF; flip via set_teacher_loop_enabled after E3 R6 PASS) / consumer loop 已啟動，IPC 句柄已注入（預設關閉）"
    );
}

/// Spawn the A2 NewsPipeline 60s scheduler.
/// A2：新聞管線 60s 排程器。
pub(crate) fn spawn_news_pipeline(
    db_pool: &Arc<DbPool>,
    learning_store: &Arc<ConfigStore<LearningConfig>>,
    cancel: &CancellationToken,
    shared_news_snapshot: &Arc<openclaw_engine::news::NewsContextSnapshot>,
    guardian_impl: Arc<openclaw_engine::news::GuardianHaltCheckImpl>,
) {
    use openclaw_engine::news::{
        CryptoPanicProvider, GuardianHaltCheck, LearningContextSink, LearningContextSinkImpl,
        NewsPipeline, NewsRouter, RssProvider,
    };
    use tokio::sync::RwLock;

    // Build providers: CryptoPanic (key from env, None = AuthMissing on fetch) + 2 RSS.
    // 建構 providers：CryptoPanic（env 取 key，None = fetch 時回 AuthMissing）+ 2 RSS。
    let cryptopanic_key = std::env::var("CRYPTOPANIC_API_KEY").ok();
    let providers: Vec<Box<dyn openclaw_engine::news::NewsProvider>> = vec![
        Box::new(CryptoPanicProvider::new(cryptopanic_key)),
        Box::new(RssProvider::cointelegraph()),
        Box::new(RssProvider::google_news_crypto()),
    ];

    // Build 4-09 triple-route NewsRouter (Guardian + Regime + Learning).
    // 建構 4-09 三路 NewsRouter（Guardian + Regime + Learning）。
    let learning_sink = Arc::new(LearningContextSinkImpl::new(Arc::clone(
        shared_news_snapshot,
    )));
    let regime_buffer = Arc::new(RwLock::new(
        openclaw_engine::news::RegimeNewsBuffer::default(),
    ));
    // G6-FUP-NEWS-HALT-DEDUP-1 (2026-04-25): retain the concrete Arc handle for
    // the periodic TTL expiry check below. The router needs `Arc<dyn ...>` so
    // we clone before the trait-object cast moves the original.
    // G6-FUP-NEWS-HALT-DEDUP-1：保留具體型別 Arc handle 給下方 TTL 檢查；
    // router 拿 trait-object Arc，先 clone 再轉型避免 move。
    let guardian_for_expiry: Arc<openclaw_engine::news::GuardianHaltCheckImpl> =
        Arc::clone(&guardian_impl);
    let router = Arc::new(NewsRouter::new(
        Some(guardian_impl as Arc<dyn GuardianHaltCheck>),
        regime_buffer,
        Some(learning_sink as Arc<dyn LearningContextSink>),
    ));

    // Build pipeline with router attached.
    // 建構帶 router 的 pipeline。
    let pipeline = Arc::new(NewsPipeline::new(providers, Arc::clone(db_pool)).with_router(router));

    let news_learning_store = Arc::clone(learning_store);
    let news_cancel = cancel.clone();
    tokio::spawn(async move {
        // 60s interval; skip first immediate tick (providers may not be ready).
        // 60 秒間隔；跳過首次立即 tick（providers 可能尚未就緒）。
        let mut interval = tokio::time::interval(std::time::Duration::from_secs(60));
        interval.tick().await; // skip first immediate tick
        loop {
            tokio::select! {
                _ = news_cancel.cancelled() => {
                    info!("A2 news pipeline scheduler stopping (cancel) / 新聞管線排程器停止");
                    break;
                }
                _ = interval.tick() => {
                    // G6-FUP-NEWS-HALT-DEDUP-1 (2026-04-25): TTL expiry check
                    // runs BEFORE provider fetch each tick. Decouples halt
                    // duration from headline_hash dedup window: even if the
                    // same severe headline keeps re-emitting (dedup-protected
                    // at pipeline level via `dedup.rs`), the halt atomic will
                    // self-clear once `now_ms - last_trigger > halt_ttl_ms`.
                    // Resolves the 2026-04-24 watchdog crashloop false-positive
                    // where session_halted=true persisted forever and tick
                    // pipeline appeared dead to watchdog.
                    // Independent of `news_pipeline_enabled` gate: even if
                    // news pipeline is disabled mid-halt, expiry should still
                    // fire so trading can resume.
                    // G6-FUP-NEWS-HALT-DEDUP-1：每 tick 跑 TTL 過期檢查，
                    // 同一嚴重 headline 不斷重發也能在 TTL 後自動清除 halt。
                    let wallclock_ms = std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)
                        .unwrap_or_default()
                        .as_millis() as u64;
                    guardian_for_expiry.check_and_clear_expired(wallclock_ms);

                    // Hot-reload gate: check LearningConfig each tick.
                    // 熱重載 gate：每 tick 檢查 LearningConfig。
                    let cfg = news_learning_store.load();
                    if !cfg.switches.news_pipeline_enabled {
                        debug!("news pipeline disabled by config, skipping / 新聞管線已被配置禁用，跳過");
                        continue;
                    }

                    let now_ms = std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)
                        .unwrap_or_default()
                        .as_millis() as i64;
                    match pipeline.run_once(now_ms).await {
                        Ok(items) => {
                            if !items.is_empty() {
                                info!(
                                    count = items.len(),
                                    "A2 news pipeline: new items processed / 新聞管線：新項目已處理"
                                );
                            }
                        }
                        Err(e) => {
                            warn!(error = %e, "A2 news pipeline run_once failed / 新聞管線 run_once 失敗");
                        }
                    }
                }
            }
        }
    });
    info!(
        "A2 news pipeline scheduler spawned (60s interval, gated by news_pipeline_enabled) / A2 新聞管線排程器已啟動"
    );
}

/// Spawn all DB writer tasks (market, feature, trading, context, REST pollers,
/// quality monitor, drift detector) + feature version init.
/// 啟動所有 DB 寫入器任務 + 特徵版本初始化。
///
/// Returns the sender halves for (market, feature, trading, context,
/// decision_feature, shadow_fill, exit_feature, shadow_exit) channels.
/// The caller uses these to wire into EventConsumerDeps.
/// 返回 (market, feature, trading, context, decision_feature, shadow_fill,
/// exit_feature, shadow_exit) 通道的發送端。
#[allow(clippy::type_complexity)]
pub(crate) async fn spawn_db_writers(
    db_pool: &Arc<DbPool>,
    config: &Arc<ConfigManager>,
    cancel: &CancellationToken,
    symbol_registry: &Arc<SymbolRegistry>,
    shared_client: &Option<Arc<BybitRestClient>>,
    shared_last_tick_ms: &Arc<std::sync::atomic::AtomicU64>,
) -> (
    Option<tokio::sync::mpsc::Sender<openclaw_engine::database::MarketDataMsg>>,
    Option<tokio::sync::mpsc::Sender<openclaw_engine::feature_collector::FeatureSnapshot>>,
    Option<tokio::sync::mpsc::Sender<openclaw_engine::database::TradingMsg>>,
    Option<tokio::sync::mpsc::Sender<openclaw_engine::database::DecisionContextMsg>>,
    Option<tokio::sync::mpsc::Sender<openclaw_engine::database::DecisionFeatureMsg>>,
    Option<tokio::sync::mpsc::Sender<openclaw_engine::database::ShadowFillMsg>>,
    Option<tokio::sync::mpsc::Sender<openclaw_engine::database::ExitFeatureRow>>,
    // INFRA-PREBUILD-1 Part A (2026-04-23): Combine Layer exit-time shadow
    // observations (Phase 2+ shadow_enabled toggle). Dormant by default.
    // INFRA-PREBUILD-1 A 部：Combine Layer 退場時刻 shadow 觀測通道。
    Option<tokio::sync::mpsc::Sender<openclaw_engine::database::ShadowExitMsg>>,
) {
    if !db_pool.is_available() {
        return (None, None, None, None, None, None, None, None);
    }

    // Market writer channel + task
    let (market_tx, market_rx) = tokio::sync::mpsc::channel(4096);
    {
        let mw_pool = Arc::clone(db_pool);
        let mw_config = Arc::clone(config);
        let mw_cancel = cancel.clone();
        tokio::spawn(openclaw_engine::database::market_writer::run_market_writer(
            market_rx, mw_pool, mw_config, mw_cancel,
        ));
    }

    // Feature writer channel + task
    let (feature_tx, feature_rx) = tokio::sync::mpsc::channel(2048);
    {
        let fw_pool = Arc::clone(db_pool);
        let fw_config = Arc::clone(config);
        let fw_cancel = cancel.clone();
        tokio::spawn(
            openclaw_engine::database::feature_writer::run_feature_writer(
                feature_rx, fw_pool, fw_config, fw_cancel,
            ),
        );
    }

    // Trading lifecycle writer channel + task
    let (trading_tx, trading_rx) = tokio::sync::mpsc::channel(4096);
    {
        let tw_pool = Arc::clone(db_pool);
        let tw_config = Arc::clone(config);
        let tw_cancel = cancel.clone();
        tokio::spawn(
            openclaw_engine::database::trading_writer::run_trading_writer(
                trading_rx, tw_pool, tw_config, tw_cancel,
            ),
        );
    }

    // Decision context writer channel + task
    let (context_tx, context_rx) = tokio::sync::mpsc::channel(1024);
    {
        let cw_pool = Arc::clone(db_pool);
        let cw_config = Arc::clone(config);
        let cw_cancel = cancel.clone();
        tokio::spawn(
            openclaw_engine::database::context_writer::run_context_writer(
                context_rx, cw_pool, cw_config, cw_cancel,
            ),
        );
    }

    // EDGE-P3-1 Step 7a: Decision feature writer channel + task.
    // Sized same as context_tx (1024) — one row per gate evaluation matches
    // the signal→intent cadence. IPC passthrough (`DecisionFeatureSnapshot`)
    // and IntentProcessor both publish here.
    // EDGE-P3-1 Step 7a：決策特徵 writer 通道 + 任務。容量與 context_tx 對齊（1024）；
    // IPC passthrough 與 IntentProcessor 共用此通道。
    let (decision_feature_tx, decision_feature_rx) = tokio::sync::mpsc::channel(1024);
    {
        let dfw_pool = Arc::clone(db_pool);
        let dfw_config = Arc::clone(config);
        let dfw_cancel = cancel.clone();
        tokio::spawn(
            openclaw_engine::database::decision_feature_writer::run_decision_feature_writer(
                decision_feature_rx,
                dfw_pool,
                dfw_config,
                dfw_cancel,
            ),
        );
    }

    // EDGE-P3-1 Step 7c: Shadow-fill writer channel + task. Sized at 1024 —
    // ε-greedy fills are rarer than decision-feature rows (only ~5% of rejected
    // intents by default), but sharing the cadence keeps backpressure behaviour
    // symmetric. Paper-only by gate guard + DB CHECK.
    // EDGE-P3-1 Step 7c：shadow-fill writer 通道 + 任務。容量 1024，與 decision
    // feature 對齊。gate + DB CHECK 保證 paper-only。
    let (shadow_fill_tx, shadow_fill_rx) = tokio::sync::mpsc::channel(1024);
    {
        let sf_pool = Arc::clone(db_pool);
        let sf_config = Arc::clone(config);
        let sf_cancel = cancel.clone();
        tokio::spawn(
            openclaw_engine::database::shadow_fill_writer::run_shadow_fill_writer(
                shadow_fill_rx,
                sf_pool,
                sf_config,
                sf_cancel,
            ),
        );
    }

    // EXIT-FEATURES-TABLE-1: Exit feature writer channel + task. Sized 1024 —
    // one row per position exit (rare relative to decision features), matches
    // realistic exit cadence across all engines. Paper/Demo/Live all share this
    // writer (paper_state close path emits regardless of pipeline kind).
    // EXIT-FEATURES-TABLE-1：退場特徵 writer 通道 + 任務。容量 1024；
    // Paper/Demo/Live 三引擎的 paper_state close path 皆寫入。
    let (exit_feature_tx, exit_feature_rx) = tokio::sync::mpsc::channel(1024);
    {
        let ef_pool = Arc::clone(db_pool);
        let ef_config = Arc::clone(config);
        let ef_cancel = cancel.clone();
        tokio::spawn(
            openclaw_engine::database::exit_feature_writer::run_exit_feature_writer(
                exit_feature_rx,
                ef_pool,
                ef_config,
                ef_cancel,
            ),
        );
    }

    // INFRA-PREBUILD-1 Part A (2026-04-23): Shadow exit writer channel + task.
    // Combine Layer Phase 2+ shadow mode — fires one row per close fill when
    // `RiskConfig.exit.shadow_enabled=true`. Sized 512 (half of exit_features);
    // shadow rows are a subset (only closes that pass Combine Layer evaluation).
    // Shares writer infra with sibling writers. Dormant by default (default
    // shadow_enabled=false → zero emits).
    // INFRA-PREBUILD-1 A 部：Combine Layer 退場時刻 shadow writer 通道 + 任務。
    // 容量 512；僅當 shadow_enabled=true 才發射（預設 false，dormant）。
    let (shadow_exit_tx, shadow_exit_rx) = tokio::sync::mpsc::channel(512);
    {
        let se_pool = Arc::clone(db_pool);
        let se_config = Arc::clone(config);
        let se_cancel = cancel.clone();
        tokio::spawn(
            openclaw_engine::database::shadow_exit_writer::run_shadow_exit_writer(
                shadow_exit_rx,
                se_pool,
                se_config,
                se_cancel,
            ),
        );
    }

    // F-4 fix: Spawn REST pollers for funding/OI/LSR
    // F-4 修復：啟動 funding/OI/LSR REST 輪詢器
    if let Some(ref client) = shared_client {
        let poll_symbols = symbol_registry.snapshot();
        openclaw_engine::database::rest_poller::spawn_rest_pollers(
            Arc::clone(client),
            market_tx.clone(),
            poll_symbols,
            cancel.clone(),
        );
    }

    // F-5 fix: Spawn data quality monitor
    // F-5 修復：啟動數據質量監控器
    {
        let qm_pool = Arc::clone(db_pool);
        let qm_tick = Arc::clone(shared_last_tick_ms);
        let qm_symbols: Vec<String> = symbol_registry.snapshot();
        let qm_cancel = cancel.clone();
        tokio::spawn(
            openclaw_engine::database::quality_writer::run_quality_monitor(
                qm_pool, qm_tick, qm_symbols, qm_cancel,
            ),
        );
    }

    // G3 1-13/14: Spawn drift detector (PSI + ADWIN)
    // G3 1-13/14：啟動漂移檢測器（PSI + ADWIN）
    {
        let dd_pool = Arc::clone(db_pool);
        let dd_config = Arc::clone(config);
        let dd_cancel = cancel.clone();
        tokio::spawn(
            openclaw_engine::database::drift_detector::run_drift_detector(
                dd_pool, dd_config, dd_cancel,
            ),
        );
    }

    // G3 1-16: Feature version init — insert v1.0 row on startup if PG available
    // G3 1-16：特徵版本初始化 — 啟動時插入 v1.0 行
    if let Some(pg) = db_pool.get() {
        let _ = sqlx::query(
            "INSERT INTO features.versions (version, description, is_active) \
             VALUES ('v1.0', 'Phase 1 initial: 34-dim IndicatorSnapshot', true) \
             ON CONFLICT (version) DO NOTHING",
        )
        .execute(pg)
        .await;
        info!("feature version v1.0 registered / 特徵版本 v1.0 已註冊");
    }

    (
        Some(market_tx),
        Some(feature_tx),
        Some(trading_tx),
        Some(context_tx),
        Some(decision_feature_tx),
        Some(shadow_fill_tx),
        Some(exit_feature_tx),
        Some(shadow_exit_tx),
    )
}

/// Spawn position reconciler with Phase 6 auto-contraction action layer.
/// Phase 6：spawn 持倉對帳器（含自動降級動作層）。
pub(crate) fn spawn_position_reconciler(
    shared_client: &Arc<BybitRestClient>,
    db_pool: &Arc<DbPool>,
    cancel: &CancellationToken,
    reconciler_cmd_tx: tokio::sync::mpsc::UnboundedSender<PipelineCommand>,
    shared_instruments: &Option<Arc<openclaw_engine::instrument_info::InstrumentInfoCache>>,
    shared_risk_level: &Arc<std::sync::atomic::AtomicU8>,
    bybit_env: BybitEnvironment,
    orphan_handler_config: Option<openclaw_engine::position_reconciler::OrphanHandlerConfig>,
) {
    let cmd_tx_provider: openclaw_engine::position_reconciler::ReconcilerCommandTxProvider =
        Arc::new(move || Some(reconciler_cmd_tx.clone()));
    spawn_position_reconciler_with_cmd_provider(
        shared_client,
        db_pool,
        cancel,
        cmd_tx_provider,
        shared_instruments,
        shared_risk_level,
        bybit_env,
        orphan_handler_config,
    );
}

/// Spawn position reconciler with a per-dispatch command sender provider.
/// Live uses this variant so the reconciler follows LiveAuthWatcher respawns.
/// 使用每次分發前取 snapshot 的 command sender provider 啟動對帳器；Live 以此
/// 跟隨 LiveAuthWatcher respawn 後的新 sender。
pub(crate) fn spawn_position_reconciler_with_cmd_provider(
    shared_client: &Arc<BybitRestClient>,
    db_pool: &Arc<DbPool>,
    cancel: &CancellationToken,
    reconciler_cmd_tx_provider: openclaw_engine::position_reconciler::ReconcilerCommandTxProvider,
    shared_instruments: &Option<Arc<openclaw_engine::instrument_info::InstrumentInfoCache>>,
    shared_risk_level: &Arc<std::sync::atomic::AtomicU8>,
    bybit_env: BybitEnvironment,
    orphan_handler_config: Option<openclaw_engine::position_reconciler::OrphanHandlerConfig>,
) {
    use openclaw_engine::position_manager::PositionManager;
    use openclaw_engine::position_reconciler::run_position_reconciler;

    let pos_mgr = Arc::new(PositionManager::new(Arc::clone(shared_client)));
    let reconciler_audit_pool = db_pool.get().cloned();
    let reconciler_cancel = cancel.clone();
    let reconciler_instruments = shared_instruments.clone();
    // Phase 6: closure reads current risk level from shared atomic.
    // Phase 6：閉包從共享原子量讀取當前風控級別。
    let reconciler_risk_level = Arc::clone(shared_risk_level);
    let get_risk_level = move || -> openclaw_core::sm::risk_gov::RiskLevel {
        let val = reconciler_risk_level.load(std::sync::atomic::Ordering::Relaxed);
        match val {
            0 => openclaw_core::sm::risk_gov::RiskLevel::Normal,
            1 => openclaw_core::sm::risk_gov::RiskLevel::Cautious,
            2 => openclaw_core::sm::risk_gov::RiskLevel::Reduced,
            3 => openclaw_core::sm::risk_gov::RiskLevel::Defensive,
            4 => openclaw_core::sm::risk_gov::RiskLevel::CircuitBreaker,
            5 => openclaw_core::sm::risk_gov::RiskLevel::ManualReview,
            // Fail-safe: unknown u8 → most restrictive level (QC audit fix).
            _ => openclaw_core::sm::risk_gov::RiskLevel::ManualReview,
        }
    };
    // 3E D23: derive engine label from bybit_env for reconciler V014 audit.
    // 3E D23：從 bybit_env 派生引擎標籤，用於對帳器 V014 審計。
    let reconciler_label = match bybit_env {
        BybitEnvironment::Demo | BybitEnvironment::Testnet => "demo".to_string(),
        BybitEnvironment::Mainnet | BybitEnvironment::LiveDemo => "live".to_string(),
    };
    tokio::spawn(run_position_reconciler(
        pos_mgr,
        reconciler_audit_pool,
        reconciler_cancel,
        reconciler_cmd_tx_provider,
        reconciler_instruments,
        get_risk_level,
        reconciler_label,
        orphan_handler_config,
    ));
    info!("position_reconciler task spawned (Phase 6 auto-contraction) / 持倉對帳器任務已啟動（Phase 6 自動降級）");
}

/// Spawn the periodic decision outcome backfill task (FIX-34).
/// Computes 1m/5m/1h/4h/24h return windows from market.klines and writes
/// to trading.decision_outcomes. Runs every 5 minutes.
/// FIX-34：啟動定期決策結果回填任務。
/// 從 market.klines 計算 1m/5m/1h/4h/24h 回報窗口，寫入 trading.decision_outcomes。
/// 每 5 分鐘運行。
pub(crate) fn spawn_outcome_backfiller(db_pool: &Arc<DbPool>, cancel: &CancellationToken) {
    let pool = Arc::clone(db_pool);
    let cancel = cancel.clone();
    tokio::spawn(openclaw_engine::database::outcome_backfiller::run_backfill_loop(pool, cancel));
    info!("outcome backfill task spawned (FIX-34, 5min interval) / 結果回填任務已啟動");
}

/// EN: Map a u8 atomic value to RiskLevel enum (fail-safe to ManualReview).
///     Extracted from spawn_position_reconciler for testability.
/// 中文: 將 u8 原子值映射到 RiskLevel 枚舉（未知值安全回退至 ManualReview）。
///       從 spawn_position_reconciler 提取以便測試。
pub(crate) fn risk_level_from_u8(val: u8) -> openclaw_core::sm::risk_gov::RiskLevel {
    use openclaw_core::sm::risk_gov::RiskLevel;
    match val {
        0 => RiskLevel::Normal,
        1 => RiskLevel::Cautious,
        2 => RiskLevel::Reduced,
        3 => RiskLevel::Defensive,
        4 => RiskLevel::CircuitBreaker,
        5 => RiskLevel::ManualReview,
        _ => RiskLevel::ManualReview, // fail-safe
    }
}

/// EN: Derive reconciler engine label from BybitEnvironment.
/// 中文: 從 BybitEnvironment 派生對帳器引擎標籤。
pub(crate) fn reconciler_label_for_env(env: BybitEnvironment) -> &'static str {
    match env {
        BybitEnvironment::Demo | BybitEnvironment::Testnet => "demo",
        BybitEnvironment::Mainnet | BybitEnvironment::LiveDemo => "live",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use openclaw_core::sm::risk_gov::RiskLevel;

    // ── risk_level_from_u8 ──

    /// EN: All 6 valid u8 values map to correct RiskLevel.
    /// 中文: 所有 6 個有效 u8 值映射到正確的 RiskLevel。
    #[test]
    fn test_risk_level_all_valid_mappings() {
        assert_eq!(risk_level_from_u8(0), RiskLevel::Normal);
        assert_eq!(risk_level_from_u8(1), RiskLevel::Cautious);
        assert_eq!(risk_level_from_u8(2), RiskLevel::Reduced);
        assert_eq!(risk_level_from_u8(3), RiskLevel::Defensive);
        assert_eq!(risk_level_from_u8(4), RiskLevel::CircuitBreaker);
        assert_eq!(risk_level_from_u8(5), RiskLevel::ManualReview);
    }

    /// EN: Unknown u8 values fail-safe to ManualReview (most restrictive).
    /// 中文: 未知 u8 值安全回退至 ManualReview（最嚴格）。
    #[test]
    fn test_risk_level_unknown_failsafe() {
        assert_eq!(risk_level_from_u8(6), RiskLevel::ManualReview);
        assert_eq!(risk_level_from_u8(100), RiskLevel::ManualReview);
        assert_eq!(risk_level_from_u8(255), RiskLevel::ManualReview);
    }

    // ── reconciler_label_for_env ──

    /// EN: Demo and Testnet map to "demo".
    /// 中文: Demo 和 Testnet 映射到 "demo"。
    #[test]
    fn test_reconciler_label_demo_variants() {
        assert_eq!(reconciler_label_for_env(BybitEnvironment::Demo), "demo");
        assert_eq!(reconciler_label_for_env(BybitEnvironment::Testnet), "demo");
    }

    /// EN: Mainnet and LiveDemo map to "live".
    /// 中文: Mainnet 和 LiveDemo 映射到 "live"。
    #[test]
    fn test_reconciler_label_live_variants() {
        assert_eq!(reconciler_label_for_env(BybitEnvironment::Mainnet), "live");
        assert_eq!(reconciler_label_for_env(BybitEnvironment::LiveDemo), "live");
    }
}
