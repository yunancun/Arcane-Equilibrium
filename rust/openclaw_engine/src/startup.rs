//! Startup helpers — balance resolution, pipeline detection, replay mode,
//! config loading, private WS supervision, signal handling, banner.
//! 啟動輔助函數 — 餘額解析、管線偵測、回放模式、配置載入、
//! 私有 WS 監管、信號處理、啟動標語。

use openclaw_engine::account_manager::AccountManager;
use openclaw_engine::bybit_rest_client::{live_bybit_environment, BybitEnvironment, BybitRestClient};
use openclaw_engine::config::{
    load_toml_or_default, BudgetConfig, ConfigManager, ConfigStore, LearningConfig, RiskConfig,
};
use openclaw_engine::event_consumer::{ExchangeEvent, SYMBOLS};
use openclaw_engine::ipc_server::PerEngineRiskStores;
use openclaw_engine::strategies::{
    bb_breakout::BbBreakout, bb_reversion::BbReversion, grid_trading::GridTrading,
    ma_crossover::MaCrossover,
};
use openclaw_engine::tick_pipeline::{PipelineKind, TickPipeline};
use openclaw_types::PriceEvent;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{debug, error, info, warn};

/// Engine version from Cargo.toml / 引擎版本（來自 Cargo.toml）
pub(crate) const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Price event channel buffer size / 價格事件通道緩衝區大小
pub(crate) const EVENT_CHANNEL_SIZE: usize = 4096;

/// Read paper balance from env var.
/// 從環境變量讀取紙盤餘額。
pub(crate) fn paper_balance_from_env() -> Option<f64> {
    std::env::var("OPENCLAW_PAPER_BALANCE")
        .ok()
        .and_then(|s| s.parse::<f64>().ok())
        .filter(|&b| b > 0.0)
}

/// Read paper balance from `settings/paper_config.toml` → `initial_balance_usdt`.
/// 從 `settings/paper_config.toml` 讀取 `initial_balance_usdt`。
pub(crate) fn paper_balance_from_toml() -> Option<f64> {
    let base = std::env::var("OPENCLAW_BASE_DIR")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|_| std::path::PathBuf::from("."));
    let path = base.join("settings").join("paper_config.toml");
    let contents = std::fs::read_to_string(&path).ok()?;
    let table: toml::Table = toml::from_str(&contents).ok()?;
    let val = table.get("initial_balance_usdt")?.as_float()?;
    if val > 0.0 { Some(val) } else { None }
}

/// Fetch account balance from Bybit API only (no env/TOML fallback).
/// Used for primary engine (Live/Demo) and for demo-balance pre-init.
/// 僅從 Bybit API 讀取帳戶餘額（無 env/TOML 回退）。
/// 用於主引擎（Live/Demo）和 demo 餘額預初始化。
pub(crate) async fn fetch_exchange_balance(env: BybitEnvironment) -> f64 {
    // Env var override still respected for backward compat
    // 向後兼容仍尊重環境變數覆蓋
    if let Some(env_bal) = paper_balance_from_env() {
        info!(
            balance = format!("{:.2}", env_bal),
            "using OPENCLAW_PAPER_BALANCE env override / 使用環境變量覆蓋餘額"
        );
        return env_bal;
    }

    match BybitRestClient::new(env, None, None) {
        Ok(client) if client.has_credentials() => {
            let acct = AccountManager::new();
            match acct.refresh_balance(&client).await {
                Ok(_) => {
                    let bal = acct.usdt_wallet_balance();
                    if bal > 0.0 {
                        info!(
                            balance = format!("{:.2}", bal),
                            "fetched Bybit USDT balance / 已從 Bybit 讀取 USDT 餘額"
                        );
                        return bal;
                    }
                    warn!("Bybit USDT balance is 0, using default / USDT 餘額為 0，使用預設值");
                }
                Err(e) => {
                    warn!(error = %e, "failed to fetch Bybit balance, using default / 讀取餘額失敗");
                }
            }
        }
        Ok(_) => {
            info!("no Bybit API credentials — using default balance / 無 API 憑證，使用預設餘額");
        }
        Err(e) => {
            warn!(error = %e, "failed to create Bybit client / 創建 Bybit 客戶端失敗");
        }
    }

    let default = 10_000.0;
    info!(
        balance = format!("{:.2}", default),
        "using default balance / 使用預設餘額"
    );
    default
}

/// Resolve paper initial balance with unified priority (MAJOR-4):
///   1. `OPENCLAW_PAPER_BALANCE` env var (explicit operator override)
///   2. `settings/paper_config.toml` → `initial_balance_usdt` (GUI-configured)
///   3. Demo API balance (if Demo key exists)
///   4. Hardcoded default (10000.0)
///
/// 統一優先級解析紙盤初始餘額（MAJOR-4）：
///   1. 環境變數 > 2. TOML 配置 > 3. Demo API 餘額 > 4. 硬編碼默認值
pub(crate) async fn resolve_paper_initial_balance() -> f64 {
    const DEFAULT_BALANCE: f64 = 10_000.0;

    // 1. Env var override (highest priority)
    if let Some(env_bal) = paper_balance_from_env() {
        info!(
            balance = format!("{:.2}", env_bal),
            "paper balance: OPENCLAW_PAPER_BALANCE env override / 紙盤餘額：環境變量覆蓋"
        );
        return env_bal;
    }

    // 2. TOML config (GUI-configured via POST /api/v1/paper/config)
    if let Some(toml_bal) = paper_balance_from_toml() {
        info!(
            balance = format!("{:.2}", toml_bal),
            "paper balance: paper_config.toml / 紙盤餘額：TOML 配置"
        );
        return toml_bal;
    }

    // 3. Demo API balance
    match BybitRestClient::new(BybitEnvironment::Demo, None, None) {
        Ok(client) if client.has_credentials() => {
            let acct = AccountManager::new();
            if let Ok(_) = acct.refresh_balance(&client).await {
                let bal = acct.usdt_wallet_balance();
                if bal > 0.0 {
                    info!(
                        balance = format!("{:.2}", bal),
                        "paper balance: Demo API / 紙盤餘額：Demo API"
                    );
                    return bal;
                }
            }
        }
        _ => {}
    }

    // 4. Hardcoded default
    info!(
        balance = format!("{:.2}", DEFAULT_BALANCE),
        "paper balance: default / 紙盤餘額：默認值"
    );
    DEFAULT_BALANCE
}

/// 3E-10.1: Detect which pipelines should start based on API key availability.
/// Paper always starts. Demo starts if demo slot has credentials.
/// Live starts if live slot has credentials.
///
/// 3E-10.1：根據 API key 可用性決定啟動哪些管線。
/// Paper 始終啟動。Demo 在 demo 槽有憑證時啟動。
/// Live 在 live 槽有憑證時啟動。
pub(crate) fn detect_available_pipelines() -> (bool, bool) {
    let demo_available = BybitRestClient::new(BybitEnvironment::Demo, None, None)
        .map(|c| c.has_credentials())
        .unwrap_or(false);
    let live_available = BybitRestClient::new(live_bybit_environment(), None, None)
        .map(|c| c.has_credentials())
        .unwrap_or(false);
    (demo_available, live_available)
}

/// Determine the "primary" pipeline kind (3E-10.1 interim).
/// Priority: Live > Demo > Paper. Paper always runs alongside if primary is exchange.
/// In the future (Phase D), all three will be fully independent.
///
/// 決定"主"管線類型（3E-10.1 過渡方案）。
/// 優先級：Live > Demo > Paper。主管線為交易所時 Paper 始終並行。
pub(crate) fn determine_primary_kind() -> PipelineKind {
    let (demo_available, live_available) = detect_available_pipelines();
    if live_available {
        info!("live API key detected → primary=Live / 偵測到 live API key → 主管線=Live");
        PipelineKind::Live
    } else if demo_available {
        info!("demo API key detected → primary=Demo / 偵測到 demo API key → 主管線=Demo");
        PipelineKind::Demo
    } else {
        info!("no exchange API keys → primary=Paper / 無交易所 API key → 主管線=Paper");
        PipelineKind::Paper
    }
}

/// Parse replay CLI arguments from std::env::args().
/// 從命令行參數解析 replay 模式選項。
pub(crate) struct ReplayArgs {
    pub enabled: bool,
    pub input_path: Option<String>,
    pub output_path: Option<String>,
}

pub(crate) fn parse_replay_args() -> ReplayArgs {
    let args: Vec<String> = std::env::args().collect();
    let mut replay = ReplayArgs {
        enabled: false,
        input_path: None,
        output_path: None,
    };
    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--replay-mode" => replay.enabled = true,
            "--replay-input" => {
                i += 1;
                if i < args.len() {
                    replay.input_path = Some(args[i].clone());
                }
            }
            "--replay-output" => {
                i += 1;
                if i < args.len() {
                    replay.output_path = Some(args[i].clone());
                }
            }
            _ => {} // ignore unknown args / 忽略未知參數
        }
        i += 1;
    }
    replay
}

/// ARCH-RC1 1C-2-A / LIVE-P2-1: Load per-engine RiskConfig (paper/demo/live) +
/// LearningConfig + BudgetConfig from their TOML files, wrapping each in an
/// `Arc<ConfigStore<T>>`. Per-engine risk paths resolve to:
///   `settings/risk_control_rules/risk_config_{paper|demo|live}.toml`
/// Individual env vars override each path:
///   OPENCLAW_RISK_CONFIG_PAPER / _DEMO / _LIVE
///   OPENCLAW_LEARNING_CONFIG / OPENCLAW_BUDGET_CONFIG
///
/// ARCH-RC1 1C-2-A / LIVE-P2-1：從 TOML 載入三個引擎 RiskConfig（paper/demo/live）
/// 及 LearningConfig + BudgetConfig，各自包入 Arc<ConfigStore>。
/// 每個引擎的風控路徑可用對應環境變數覆蓋。
#[allow(clippy::type_complexity)]
pub(crate) fn load_unified_configs() -> Result<
    (
        PerEngineRiskStores,
        Arc<ConfigStore<LearningConfig>>,
        Arc<ConfigStore<BudgetConfig>>,
    ),
    String,
> {
    use std::path::PathBuf;

    let base = std::env::var("OPENCLAW_RISK_CONFIG_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("settings/risk_control_rules"));

    // LIVE-P2-1: Per-engine risk config paths with env var overrides.
    // LIVE-P2-1：每引擎風控配置路徑，可通過環境變量覆蓋。
    let risk_path_paper = std::env::var("OPENCLAW_RISK_CONFIG_PAPER")
        .map(PathBuf::from)
        .unwrap_or_else(|_| {
            // Legacy fallback: if risk_config_paper.toml absent, use risk_config.toml.
            // 舊版回退：若 risk_config_paper.toml 不存在，使用 risk_config.toml。
            let paper = base.join("risk_config_paper.toml");
            if paper.exists() { paper } else { base.join("risk_config.toml") }
        });
    let risk_path_demo = std::env::var("OPENCLAW_RISK_CONFIG_DEMO")
        .map(PathBuf::from)
        .unwrap_or_else(|_| base.join("risk_config_demo.toml"));
    let risk_path_live = std::env::var("OPENCLAW_RISK_CONFIG_LIVE")
        .map(PathBuf::from)
        .unwrap_or_else(|_| base.join("risk_config_live.toml"));

    let learning_path = std::env::var("OPENCLAW_LEARNING_CONFIG")
        .map(PathBuf::from)
        .unwrap_or_else(|_| base.join("learning_config.toml"));
    let budget_path = std::env::var("OPENCLAW_BUDGET_CONFIG")
        .map(PathBuf::from)
        .unwrap_or_else(|_| base.join("budget_config.toml"));

    info!(
        risk_paper = %risk_path_paper.display(),
        risk_demo = %risk_path_demo.display(),
        risk_live = %risk_path_live.display(),
        learning = %learning_path.display(),
        budget = %budget_path.display(),
        "loading ARCH-RC1 / LIVE-P2-1 per-engine configs / 載入每引擎 Config"
    );

    // ARCH-RC1 1C-2-D: one-shot legacy operator_risk_config.json → TOML migration
    // (targets paper config path as the canonical migration destination).
    // ARCH-RC1 1C-2-D：舊 JSON → TOML 一次性遷移（遷移目標為 paper 路徑）。
    match openclaw_engine::config::legacy_migration::migrate_legacy_risk_json_if_needed(&base) {
        Ok(openclaw_engine::config::legacy_migration::MigrationOutcome::Migrated(p)) => {
            info!(path = %p.display(), "legacy risk JSON migrated to TOML / 舊風控 JSON 已遷移");
        }
        Ok(_) => {}
        Err(e) => {
            tracing::warn!(error = %e, "legacy risk JSON migration failed (continuing with defaults) / 舊 JSON 遷移失敗（用 default 繼續）");
        }
    }

    let risk_paper: RiskConfig =
        load_toml_or_default(&risk_path_paper, |c: &RiskConfig| c.validate())
            .map_err(|e| format!("risk_paper config: {}", e))?;
    let risk_demo: RiskConfig =
        load_toml_or_default(&risk_path_demo, |c: &RiskConfig| c.validate())
            .map_err(|e| format!("risk_demo config: {}", e))?;
    let risk_live: RiskConfig =
        load_toml_or_default(&risk_path_live, |c: &RiskConfig| c.validate())
            .map_err(|e| format!("risk_live config: {}", e))?;
    let learning: LearningConfig =
        load_toml_or_default(&learning_path, |c: &LearningConfig| c.validate())
            .map_err(|e| format!("learning config: {}", e))?;
    let budget: BudgetConfig =
        load_toml_or_default(&budget_path, |c: &BudgetConfig| c.validate())
            .map_err(|e| format!("budget config: {}", e))?;

    info!(
        paper_version = risk_paper.meta.version,
        demo_version = risk_demo.meta.version,
        live_version = risk_live.meta.version,
        learning_version = learning.meta.version,
        budget_version = budget.meta.version,
        "LIVE-P2-1 per-engine risk configs loaded / 每引擎風控配置已載入"
    );

    // CFG-PERSIST-1: wire each store to atomic TOML write-back so operator
    // patches survive engine restart.
    // CFG-PERSIST-1：每個 store 接上原子 TOML 回寫，operator 補丁可跨重啟。
    let risk_stores = PerEngineRiskStores {
        paper: Arc::new(ConfigStore::new(risk_paper).with_toml_persist(risk_path_paper)),
        demo: Arc::new(ConfigStore::new(risk_demo).with_toml_persist(risk_path_demo)),
        live: Arc::new(ConfigStore::new(risk_live).with_toml_persist(risk_path_live)),
    };
    Ok((
        risk_stores,
        Arc::new(ConfigStore::new(learning).with_toml_persist(learning_path)),
        Arc::new(ConfigStore::new(budget).with_toml_persist(budget_path)),
    ))
}

/// Run the engine in replay mode: read historical ticks from JSONL,
/// process through TickPipeline, write CanaryRecords to output JSONL.
/// No WS connection, no IPC, no paper auth needed.
/// 回放模式：從 JSONL 讀取歷史 tick，通過 TickPipeline 處理，
/// 將 CanaryRecord 寫入輸出 JSONL。無需 WS 連線、IPC 或紙盤授權。
pub(crate) fn run_replay_mode(args: ReplayArgs) {
    use std::io::{BufRead, BufWriter, Write};

    let input_path = args.input_path.unwrap_or_else(|| {
        error!("--replay-input is required / --replay-input 為必填參數");
        std::process::exit(1);
    });
    let output_path = args.output_path.unwrap_or_else(|| {
        error!("--replay-output is required / --replay-output 為必填參數");
        std::process::exit(1);
    });

    info!(
        input = %input_path,
        output = %output_path,
        "replay: reading ticks / 回放：讀取 tick 數據"
    );

    // ------------------------------------------------------------------
    // 1. Build pipeline with same strategies as live mode
    //    構建與即時模式相同策略的管線
    // ------------------------------------------------------------------
    let mut pipeline = TickPipeline::new(SYMBOLS);

    // Register strategies (identical to live mode) / 註冊策略（與即時模式一致）
    pipeline.orchestrator.register(Box::new(MaCrossover::new()));
    pipeline.orchestrator.register(Box::new(BbReversion::new()));
    pipeline.orchestrator.register(Box::new(BbBreakout::new()));
    pipeline
        .orchestrator
        .register(Box::new(GridTrading::new_adaptive()));

    // Grant paper authorization / 授予紙盤授權
    match pipeline.grant_paper_auth() {
        Ok(()) => info!("replay: paper authorization granted / 回放：紙盤授權已授予"),
        Err(e) => {
            error!(error = %e, "replay: failed to grant paper auth / 回放：紙盤授權失敗");
            std::process::exit(1);
        }
    }

    let strategies = pipeline.orchestrator.active_strategy_names().join(", ");
    info!(
        strategies = %strategies,
        "replay: pipeline ready / 回放：管線就緒"
    );

    // ------------------------------------------------------------------
    // 2. Read input JSONL and process each tick
    //    讀取輸入 JSONL 並處理每個 tick
    // ------------------------------------------------------------------
    let in_file = match std::fs::File::open(&input_path) {
        Ok(f) => f,
        Err(e) => {
            error!(error = %e, path = %input_path, "replay: cannot open input / 回放：無法打開輸入文件");
            std::process::exit(1);
        }
    };
    let reader = std::io::BufReader::new(in_file);

    let out_file = match std::fs::File::create(&output_path) {
        Ok(f) => f,
        Err(e) => {
            error!(error = %e, path = %output_path, "replay: cannot create output / 回放：無法創建輸出文件");
            std::process::exit(1);
        }
    };
    let mut writer = BufWriter::new(out_file);

    let mut tick_count: u64 = 0;
    let mut record_count: u64 = 0;
    let start = std::time::Instant::now();

    for line_result in reader.lines() {
        let line = match line_result {
            Ok(l) => l,
            Err(e) => {
                warn!(error = %e, "replay: skipping unreadable line / 回放：跳過無法讀取的行");
                continue;
            }
        };
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        // Parse line as PriceEvent (format matches synthesize_ticks output)
        // 將行解析為 PriceEvent（格式匹配 synthesize_ticks 輸出）
        let event: PriceEvent = match serde_json::from_str(trimmed) {
            Ok(ev) => ev,
            Err(e) => {
                warn!(
                    error = %e,
                    line_num = tick_count + 1,
                    "replay: skipping unparseable tick / 回放：跳過無法解析的 tick"
                );
                continue;
            }
        };

        tick_count += 1;

        // Feed through pipeline / 送入管線處理
        if let Some(record) = pipeline.feed_replay_tick(&event) {
            if let Ok(json) = serde_json::to_string(&record) {
                let _ = writeln!(writer, "{}", json);
                record_count += 1;
            }
        }

        // Progress log every 10000 ticks / 每 10000 個 tick 記錄進度
        if tick_count % 10_000 == 0 {
            info!(
                ticks = tick_count,
                records = record_count,
                "replay: progress / 回放：進度"
            );
        }
    }

    // Flush output / 刷新輸出
    let _ = writer.flush();

    let elapsed = start.elapsed();
    info!(
        ticks = tick_count,
        records = record_count,
        elapsed_ms = elapsed.as_millis() as u64,
        fills = pipeline.stats.total_fills,
        intents = pipeline.stats.total_intents,
        output = %output_path,
        "replay complete / 回放完成"
    );
}

/// Exchange bindings produced by spawning a private WS supervisor.
/// 啟動私有 WS 監管器後產生的交易所綁定。
pub(crate) struct PrivateWsBindings {
    // BLOCKER-6 / D12: parking_lot::RwLock for non-poisoning cross-pipeline isolation.
    // BLOCKER-6 / D12：parking_lot::RwLock，不中毒 → 跨管線隔離。
    pub bybit_balance: Arc<parking_lot::RwLock<Option<f64>>>,
    pub api_pnl: Arc<parking_lot::RwLock<std::collections::HashMap<String, f64>>>,
    pub exchange_event_rx: mpsc::UnboundedReceiver<ExchangeEvent>,
    pub _ws_handle: tokio::task::JoinHandle<()>,
    pub _listener_handle: tokio::task::JoinHandle<()>,
}

/// Spawn a per-pipeline private WS supervisor + ExecutionListener.
/// Returns exchange bindings for the pipeline's EventConsumerDeps.
/// 為每管線啟動私有 WS 監管器 + 執行監聽器。
/// 返回管線 EventConsumerDeps 所需的交易所綁定。
pub(crate) fn spawn_private_ws_supervisor(
    api_key: String,
    api_secret: String,
    env: BybitEnvironment,
    label: &str,
    cancel: CancellationToken,
) -> PrivateWsBindings {
    use openclaw_engine::bybit_private_ws::BybitPrivateWs;
    use openclaw_engine::execution_listener::ExecutionListener;
    use parking_lot::RwLock;

    let (priv_tx, priv_rx) = mpsc::channel(512);
    let (exchange_event_tx, exchange_event_rx) = mpsc::unbounded_channel::<ExchangeEvent>();

    // Shared state updated by callbacks / 回調更新的共享狀態
    let bybit_balance: Arc<RwLock<Option<f64>>> = Arc::new(RwLock::new(None));
    let api_pnl: Arc<RwLock<std::collections::HashMap<String, f64>>> =
        Arc::new(RwLock::new(std::collections::HashMap::new()));

    let mut listener = ExecutionListener::new(priv_rx);

    // on_balance_update → track Bybit sync balance / 餘額更新回調
    let bal_ref = Arc::clone(&bybit_balance);
    let lbl_bal = label.to_string();
    listener.set_on_balance_update(move |wallet| {
        for coin_update in &wallet.coin {
            if coin_update.coin.eq_ignore_ascii_case("USDT") {
                if let Ok(bal) = coin_update.wallet_balance.parse::<f64>() {
                    // BLOCKER-6: parking_lot RwLock — write() returns guard directly.
                    // BLOCKER-6：parking_lot RwLock — write() 直接回傳 guard。
                    *bal_ref.write() = Some(bal);
                    info!(
                        engine = %lbl_bal,
                        equity = %coin_update.equity,
                        balance = %coin_update.wallet_balance,
                        "WS wallet update (USDT) / WS 錢包更新"
                    );
                }
                break;
            }
        }
    });

    // on_position_update → track API unrealized PnL / 持倉更新回調
    let pnl_ref = Arc::clone(&api_pnl);
    let lbl_pos = label.to_string();
    listener.set_on_position_update(move |pos| {
        if let Ok(pnl) = pos.unrealised_pnl.parse::<f64>() {
            // BLOCKER-6: parking_lot RwLock — write() returns guard directly.
            // BLOCKER-6：parking_lot RwLock — write() 直接回傳 guard。
            pnl_ref.write().insert(pos.symbol.clone(), pnl);
        }
        debug!(
            engine = %lbl_pos,
            symbol = %pos.symbol,
            side = %pos.side,
            size = %pos.size,
            pnl = %pos.unrealised_pnl,
            "WS position update / WS 持倉更新"
        );
    });

    // on_fill → log execution + forward to event consumer / 成交回調
    let fill_tx = exchange_event_tx.clone();
    let lbl_fill = label.to_string();
    listener.set_on_fill(move |exec| {
        info!(
            engine = %lbl_fill,
            exec_id = %exec.exec_id,
            symbol = %exec.symbol,
            side = %exec.side,
            qty = %exec.exec_qty,
            price = %exec.exec_price,
            fee = %exec.exec_fee,
            "WS fill / WS 成交"
        );
        let _ = fill_tx.send(ExchangeEvent::Fill(exec));
    });

    // on_order_update → log + forward / 訂單更新回調
    let order_tx = exchange_event_tx.clone();
    let lbl_ord = label.to_string();
    listener.set_on_order_update(move |order| {
        debug!(
            engine = %lbl_ord,
            order_id = %order.order_id,
            symbol = %order.symbol,
            status = %order.order_status,
            link_id = %order.order_link_id,
            "WS order update / WS 訂單更新"
        );
        let _ = order_tx.send(ExchangeEvent::OrderUpdate(order));
    });

    // DCP/Disconnected events / DCP/斷連事件
    let dcp_tx = exchange_event_tx.clone();
    listener.set_on_dcp(move || {
        let _ = dcp_tx.send(ExchangeEvent::DcpTriggered);
    });
    let disc_tx = exchange_event_tx;
    listener.set_on_disconnect(move || {
        let _ = disc_tx.send(ExchangeEvent::Disconnected);
    });

    // Spawn listener task / 啟動監聽器任務
    let listener_handle = tokio::spawn(async move {
        let mut listener = listener;
        listener.run().await;
    });

    // RE-2: Supervisor wrapper — restarts on unexpected exit
    // RE-2：監管器包裝 — 意外退出時自動重啟
    let lbl_sv = label.to_string();
    let sv_cancel = cancel.clone();
    let ws_handle = tokio::spawn(async move {
        let mut supervisor_attempt: u32 = 0;
        loop {
            if sv_cancel.is_cancelled() {
                break;
            }
            let priv_ws = BybitPrivateWs::new(
                api_key.clone(),
                api_secret.clone(),
                env,
                sv_cancel.clone(),
                priv_tx.clone(),
            );
            priv_ws.run().await;
            if sv_cancel.is_cancelled() {
                break;
            }
            supervisor_attempt = supervisor_attempt.saturating_add(1);
            let delay_ms = std::cmp::min(
                5000_u64.saturating_mul(2_u64.saturating_pow(supervisor_attempt.min(4))),
                60_000,
            );
            warn!(
                engine = %lbl_sv,
                delay_ms = delay_ms,
                attempt = supervisor_attempt,
                "Private WS supervisor restarting / 私有 WS 監管器重啟"
            );
            tokio::select! {
                _ = sv_cancel.cancelled() => break,
                _ = tokio::time::sleep(std::time::Duration::from_millis(delay_ms)) => {},
            }
        }
    });

    info!(engine = label, "Private WS + ExecutionListener started / 私有 WS + 執行監聽器已啟動");
    PrivateWsBindings {
        bybit_balance,
        api_pnl,
        exchange_event_rx,
        _ws_handle: ws_handle,
        _listener_handle: listener_handle,
    }
}

/// Listen for OS signals: SIGHUP → reload, SIGTERM/SIGINT → shutdown.
/// 監聽 OS 信號：SIGHUP → 重載，SIGTERM/SIGINT → 關閉。
pub(crate) async fn signal_loop(config: &Arc<ConfigManager>, cancel: &CancellationToken) {
    // Platform-specific signal handling / 平台特定信號處理
    #[cfg(unix)]
    {
        use tokio::signal::unix::{signal, SignalKind};
        let mut sighup =
            signal(SignalKind::hangup()).expect("failed to register SIGHUP / 註冊 SIGHUP 失敗");
        let mut sigterm = signal(SignalKind::terminate())
            .expect("failed to register SIGTERM / 註冊 SIGTERM 失敗");

        loop {
            tokio::select! {
                _ = sighup.recv() => {
                    info!("SIGHUP received — reloading config / 收到 SIGHUP — 重載配置");
                    match config.reload() {
                        Ok(()) => info!("config reloaded successfully / 配置重載成功"),
                        Err(e) => error!(error = %e, "config reload failed / 配置重載失敗"),
                    }
                }
                _ = sigterm.recv() => {
                    info!("SIGTERM received — shutting down / 收到 SIGTERM — 開始關閉");
                    break;
                }
                _ = tokio::signal::ctrl_c() => {
                    info!("SIGINT received — shutting down / 收到 SIGINT — 開始關閉");
                    break;
                }
                _ = cancel.cancelled() => {
                    break;
                }
            }
        }
    }

    // Non-Unix fallback (Windows/other) / 非 Unix 回退
    #[cfg(not(unix))]
    {
        tokio::select! {
            _ = tokio::signal::ctrl_c() => {
                info!("ctrl-c received — shutting down / 收到 ctrl-c — 開始關閉");
            }
            _ = cancel.cancelled() => {}
        }
    }
}

/// Print startup banner.
/// 打印啟動標語。
pub(crate) fn print_banner() {
    info!("==============================================");
    info!("  OpenClaw Engine v{}", VERSION);
    info!("  Mode: Live_Ready | Execution: operator-gated");
    info!("  Bybit V5 Linear — Rust Trading Engine");
    info!("==============================================");
}
