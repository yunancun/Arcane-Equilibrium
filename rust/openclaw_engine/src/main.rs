//! OpenClaw Engine entry point — tokio runtime, signal handling, startup/shutdown (R01-2).
//! OpenClaw 引擎入口 — tokio 運行時、信號處理、啟動/關閉序列。
//!
//! MODULE_NOTE (EN): Sets up multi-thread tokio runtime for IPC + WS + background tasks.
//!   SIGHUP triggers config hot-reload. SIGTERM/SIGINT triggers graceful shutdown.
//!   Event consumer feeds PriceEvents into TickPipeline for paper trading.
//! MODULE_NOTE (中): 設置多線程 tokio 運行時用於 IPC + WS + 後台任務。
//!   SIGHUP 觸發配置熱加載。SIGTERM/SIGINT 觸發優雅關閉。
//!   事件消費者將 PriceEvent 送入 TickPipeline 進行紙盤交易。

use openclaw_engine::account_manager::AccountManager;
use openclaw_engine::bybit_rest_client::{live_bybit_environment, BybitEnvironment, BybitRestClient};
use openclaw_engine::config::{
    load_toml_or_default, BudgetConfig, ConfigManager, ConfigStore, LearningConfig, RiskConfig,
};
use openclaw_engine::event_consumer::SYMBOLS;
use openclaw_engine::ipc_server::{IpcServer, PerEngineRiskStores};
use openclaw_engine::market_data_client::MarketDataClient;
use openclaw_engine::scanner::ScannerConfig;
use openclaw_engine::scanner::registry::SymbolRegistry;
use openclaw_engine::scanner::runner::ScannerRunner;
use openclaw_engine::strategies::{
    bb_breakout::BbBreakout, bb_reversion::BbReversion, grid_trading::GridTrading,
    ma_crossover::MaCrossover,
};
use openclaw_engine::tick_pipeline::{PipelineKind, TickPipeline};
use openclaw_engine::ws_client::WsClient;
use openclaw_types::PriceEvent;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{debug, error, info, warn};

/// Engine version from Cargo.toml / 引擎版本（來自 Cargo.toml）
const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Price event channel buffer size / 價格事件通道緩衝區大小
const EVENT_CHANNEL_SIZE: usize = 4096;

// SYMBOLS moved to event_consumer.rs (Phase 1 Day 0-A extraction)
// STATUS_INTERVAL_SECS moved to event_consumer.rs

/// Read paper balance from env var.
/// 從環境變量讀取紙盤餘額。
fn paper_balance_from_env() -> Option<f64> {
    std::env::var("OPENCLAW_PAPER_BALANCE")
        .ok()
        .and_then(|s| s.parse::<f64>().ok())
        .filter(|&b| b > 0.0)
}

/// Read paper balance from `settings/paper_config.toml` → `initial_balance_usdt`.
/// 從 `settings/paper_config.toml` 讀取 `initial_balance_usdt`。
fn paper_balance_from_toml() -> Option<f64> {
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
async fn fetch_exchange_balance(env: BybitEnvironment) -> f64 {
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
async fn resolve_paper_initial_balance() -> f64 {
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
fn detect_available_pipelines() -> (bool, bool) {
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
fn determine_primary_kind() -> PipelineKind {
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
struct ReplayArgs {
    enabled: bool,
    input_path: Option<String>,
    output_path: Option<String>,
}

fn parse_replay_args() -> ReplayArgs {
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

fn main() {
    // ------------------------------------------------------------------
    // 0. Install rustls crypto provider / 安裝 rustls 加密提供者
    // ------------------------------------------------------------------
    rustls::crypto::ring::default_provider()
        .install_default()
        .expect("failed to install rustls crypto provider");

    // ------------------------------------------------------------------
    // 1. Initialize tracing / 初始化日誌追蹤
    // ------------------------------------------------------------------
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .with_target(true)
        .with_thread_ids(true)
        .init();

    print_banner();

    // ------------------------------------------------------------------
    // 1b. Check for replay mode / 檢查是否為回放模式
    // ------------------------------------------------------------------
    let replay_args = parse_replay_args();
    if replay_args.enabled {
        info!("replay mode activated / 回放模式已啟用");
        run_replay_mode(replay_args);
        return;
    }

    // ------------------------------------------------------------------
    // 2. Load engine bootstrap config (EngineBootstrap from engine.toml)
    //    加載引擎啟動配置
    // ------------------------------------------------------------------
    let config = match ConfigManager::load(None) {
        Ok(c) => Arc::new(c),
        Err(e) => {
            error!(error = %e, "failed to load config / 配置加載失敗");
            std::process::exit(1);
        }
    };

    // ------------------------------------------------------------------
    // 2b. ARCH-RC1 1C-2: Load 3 unified Configs and wrap in ConfigStores.
    //     TOML paths configurable via env overrides; fall back to settings/.
    //     ARCH-RC1 1C-2：載入 3 個統一 Config 並包入 ConfigStore。
    //     TOML 路徑可用環境變數覆蓋，否則使用 settings/。
    // ------------------------------------------------------------------
    let (risk_stores, learning_store, budget_store) = match load_unified_configs() {
        Ok(s) => s,
        Err(e) => {
            error!(error = %e, "failed to load unified configs / 統一配置加載失敗");
            std::process::exit(1);
        }
    };
    // learning_store is consumed by the A2 news pipeline scheduler (hot-reload gate).
    // learning_store 由 A2 新聞管線排程器使用（熱重載 gate）。
    let _learning_store_held = Arc::clone(&learning_store);

    // ------------------------------------------------------------------
    // 3. Build multi-thread runtime / 構建多線程運行時
    // ------------------------------------------------------------------
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .thread_name("oc-engine")
        .build()
        .expect("failed to build tokio runtime / 構建 tokio 運行時失敗");

    runtime.block_on(async_main(
        config,
        risk_stores,
        learning_store,
        budget_store,
    ));
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
fn load_unified_configs() -> Result<
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
fn run_replay_mode(args: ReplayArgs) {
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

/// Async entry point running inside the multi-thread runtime.
/// 在多線程運行時內執行的異步入口。
async fn async_main(
    config: Arc<ConfigManager>,
    risk_stores: PerEngineRiskStores,
    learning_store: Arc<ConfigStore<LearningConfig>>,
    budget_store: Arc<ConfigStore<BudgetConfig>>,
) {
    let cancel = CancellationToken::new();

    // ------------------------------------------------------------------
    // Scanner D4: Load ScannerConfig + build SymbolRegistry
    // 掃描器 D4：加載 ScannerConfig + 構建 SymbolRegistry
    // ------------------------------------------------------------------
    let scanner_config_path = {
        let base = std::env::var("OPENCLAW_RISK_CONFIG_DIR")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|_| std::path::PathBuf::from("settings/risk_control_rules"));
        std::env::var("OPENCLAW_SCANNER_CONFIG")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|_| base.join("scanner_config.toml"))
    };
    let scanner_cfg: ScannerConfig =
        load_toml_or_default(&scanner_config_path, |c: &ScannerConfig| c.validate())
            .unwrap_or_else(|e| {
                warn!(error = %e, "scanner config load failed, using defaults / 掃描器配置加載失敗，使用默認值");
                ScannerConfig::default()
            });
    info!(
        max_symbols = scanner_cfg.universe.max_symbols,
        pinned = ?scanner_cfg.universe.pinned_symbols,
        interval_secs = scanner_cfg.scheduling.scan_interval_secs,
        "scanner config loaded / 掃描器配置已加載"
    );
    let scanner_store: Arc<ConfigStore<ScannerConfig>> =
        Arc::new(ConfigStore::new(scanner_cfg).with_toml_persist(scanner_config_path));
    let pinned_syms = scanner_store.load().universe.pinned_symbols.clone();
    let symbol_registry = Arc::new(SymbolRegistry::new(
        pinned_syms.clone(), // initial_symbols = pinned (pre-scanner state)
        pinned_syms,         // pinned (never removed by anti-churn)
    ));

    // Scanner D4: Load EdgeEstimates for scanner scorer (separate from intent_processor copy).
    // 掃描器 D4：為掃描器評分器加載邊際估計（與 intent_processor 副本分離）。
    let scanner_edge_estimates = {
        let base = std::env::var("OPENCLAW_BASE_DIR")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|_| std::path::PathBuf::from("."));
        let estimates = openclaw_engine::edge_estimates::EdgeEstimates::load_from_env_or_default(&base);
        Arc::new(parking_lot::RwLock::new(estimates))
    };

    // Scanner D4: Relay channel — ScannerRunner sends to a persistent channel;
    // a relay task forwards to the current WsClient's sender (refreshed on each restart).
    // 掃描器 D4：中繼通道 — ScannerRunner 發送到持久通道；
    // 中繼任務將消息轉發到當前 WsClient 的發送端（每次重啟時刷新）。
    let (scanner_ws_tx, mut scanner_ws_rx) =
        tokio::sync::mpsc::unbounded_channel::<openclaw_engine::ws_client::WsTopicChange>();
    let current_ws_client_tx: Arc<
        tokio::sync::Mutex<
            Option<tokio::sync::mpsc::UnboundedSender<openclaw_engine::ws_client::WsTopicChange>>,
        >,
    > = Arc::new(tokio::sync::Mutex::new(None));
    {
        let relay_arc = Arc::clone(&current_ws_client_tx);
        tokio::spawn(async move {
            while let Some(change) = scanner_ws_rx.recv().await {
                let guard = relay_arc.lock().await;
                if let Some(tx) = guard.as_ref() {
                    let _ = tx.send(change);
                } else {
                    // m-1 fix: log when WsClient not ready; next scan cycle resubscribes via snapshot.
                    // m-1 修復：WsClient 未就緒時記錄日誌；下次掃描週期通過 snapshot 重新訂閱。
                    tracing::debug!("[scanner relay] WsClient not ready — topic change dropped, will retry on next scan");
                }
            }
        });
    }

    // NOTE: initial_balance is fetched after bybit_env is determined below (line ~653).
    // 注意：initial_balance 在下方 bybit_env 計算後讀取，確保使用正確的帳戶。

    // ------------------------------------------------------------------
    // Price event channel / 價格事件通道
    // ------------------------------------------------------------------
    let (event_tx, event_rx) = mpsc::channel::<PriceEvent>(EVENT_CHANNEL_SIZE);

    // ------------------------------------------------------------------
    // Start IPC server / 啟動 IPC 服務器
    // ------------------------------------------------------------------
    // IPC server data_dir for file-based state reads (R06-A)
    // IPC 服務器數據目錄，用於基於文件的狀態讀取
    let ipc_data_dir =
        std::env::var("OPENCLAW_DATA_DIR").unwrap_or_else(|_| "/tmp/openclaw".into());
    // Primary pipeline command channel: IPC → event consumer
    // 主管線命令通道：IPC → 事件消費者
    let (primary_cmd_tx, pipeline_cmd_rx) = tokio::sync::mpsc::unbounded_channel();
    // Clone the command sender for the Phase 4.1 Teacher consumer loop wiring below.
    // 為下方 Phase 4.1 Teacher consumer loop 接線預先複製 command sender。
    let phase4_consumer_cmd_tx = primary_cmd_tx.clone();
    // Scanner D4: clone pipeline_cmd_tx for ScannerRunner (queries GetOpenPositionSymbols).
    // 掃描器 D4：為 ScannerRunner 複製 pipeline_cmd_tx（查詢 GetOpenPositionSymbols）。
    let scanner_pipeline_cmd_tx = primary_cmd_tx.clone();
    // Phase 6: clone pipeline_cmd_tx for reconciler auto-contraction commands.
    // Phase 6：為對帳器自動降級命令複製 pipeline_cmd_tx。
    let reconciler_cmd_tx = primary_cmd_tx.clone();
    // Phase 6: shared atomic for reconciler to read current risk level without IPC.
    // The event_consumer handler writes to this on every governor state change.
    // Phase 6：共享原子量供對帳器無 IPC 讀取當前風控級別。
    let shared_risk_level = Arc::new(std::sync::atomic::AtomicU8::new(
        openclaw_core::sm::risk_gov::RiskLevel::Normal.value(),
    ));
    // 3E-3: Paper-alongside command channel (created here, wired into IPC + deps below)
    // 3E-3：Paper 伴隨管線命令通道（此處創建，下方接入 IPC + deps）
    let (pipeline_cmd_tx_paper, pipeline_cmd_rx_paper) = tokio::sync::mpsc::unbounded_channel();
    let mut ipc_server = IpcServer::new(
        Arc::clone(&config),
        cancel.clone(),
        ipc_data_dir,
        {
            // 3E-10.1: Build EngineCommandChannels based on API key detection.
            // Paper always; Demo if demo key exists; Live if live key exists.
            // 3E-10.1：根據 API key 偵測構建 EngineCommandChannels。
            use openclaw_engine::ipc_server::EngineCommandChannels;
            let ipc_primary_kind = determine_primary_kind();
            let mut channels = EngineCommandChannels::default();
            match ipc_primary_kind.db_mode() {
                "paper" => {
                    channels.paper = Some(primary_cmd_tx.clone());
                }
                "demo" => {
                    channels.demo = Some(primary_cmd_tx.clone());
                    channels.paper = Some(pipeline_cmd_tx_paper.clone());
                }
                "live" => {
                    channels.live = Some(primary_cmd_tx.clone());
                    channels.paper = Some(pipeline_cmd_tx_paper.clone());
                }
                _ => {
                    channels.paper = Some(primary_cmd_tx.clone());
                }
            }
            channels
        },
    );
    // ARCH-RC1 1C-2-C / LIVE-P2-1: wire per-engine risk stores + unified Config stores into IPC.
    // ARCH-RC1 1C-2-C / LIVE-P2-1：將每引擎 risk stores + 統一 Config stores 接入 IPC。
    ipc_server.set_config_stores(
        risk_stores.clone(),
        Arc::clone(&learning_store),
        Arc::clone(&budget_store),
    );
    // IPC-SCAN-1: wire SymbolRegistry for scanner observability endpoints.
    // IPC-SCAN-1：接入 SymbolRegistry 供掃描器可觀測性端點使用。
    ipc_server.set_scanner_registry(Arc::clone(&symbol_registry));
    // Phase 4 (4-15): Grab the BudgetTracker slot handle before moving the server into
    // the spawn task; main will write the tracker into this slot once db_pool is ready.
    // Phase 4 (4-15)：在把 server 移入 spawn task 前先拿到 BudgetTracker 槽位句柄；
    // 主函數會在 db_pool 就緒後將 tracker 寫入此槽位。
    let budget_tracker_slot = ipc_server.budget_tracker_slot();
    // Phase 4.1: same pattern for the Teacher consumer loop handles.
    // Phase 4.1：同樣模式拿 Teacher consumer loop 句柄槽位。
    let teacher_loop_slot = ipc_server.teacher_loop_slot();
    // ARCH-RC1 1C-2-E: grab audit pool slot for late injection after db_pool is up.
    // ARCH-RC1 1C-2-E：取得審計 pool 槽位，待 db_pool 就緒後注入。
    let audit_pool_slot = ipc_server.audit_pool_slot();
    let ipc_handle = tokio::spawn(async move {
        if let Err(e) = ipc_server.run().await {
            error!(error = %e, "IPC server error / IPC 服務器錯誤");
        }
    });

    // ------------------------------------------------------------------
    // Bybit API integration — DCP, auto-margin, fee rates (Items 2/7/8)
    // Bybit API 整合 — 斷連保護、自動追加保證金、動態費率
    // ------------------------------------------------------------------
    let mut api_taker_fee: Option<f64> = None;
    let mut api_credentials: Option<(String, String)> = None;
    let mut shared_client: Option<Arc<BybitRestClient>> = None;
    let mut shared_instruments: Option<Arc<openclaw_engine::instrument_info::InstrumentInfoCache>> =
        None;
    let mut shared_account_manager: Option<Arc<AccountManager>> = None;
    let cfg_snapshot = config.get();
    // 3E-10.1: Derive Bybit environment from API key detection (replaces trading_mode).
    // Live key → live_bybit_environment(); else Demo.
    // 3E-10.1：從 API key 偵測派生 Bybit 環境（取代 trading_mode）。
    let primary_kind_early = determine_primary_kind();
    let bybit_env = match primary_kind_early {
        PipelineKind::Live => live_bybit_environment(),
        PipelineKind::Demo | PipelineKind::Paper => BybitEnvironment::Demo,
    };

    // Fetch initial balance for the primary exchange environment.
    // 為主交易所環境讀取初始餘額。
    let initial_balance = fetch_exchange_balance(bybit_env).await;

    // MAJOR-4: Paper balance uses unified priority (env > TOML > Demo API > default).
    // When primary is Live, paper needs its own balance (not the live balance).
    // When primary is Paper/Demo, paper_initial_balance=None → uses initial_balance.
    // MAJOR-4：紙盤餘額使用統一優先級（環境變數 > TOML > Demo API > 默認值）。
    let paper_initial_balance: Option<f64> = if primary_kind_early == PipelineKind::Live {
        Some(resolve_paper_initial_balance().await)
    } else {
        None
    };

    if let Ok(rest_client) = BybitRestClient::new(bybit_env, None, None) {
        if rest_client.has_credentials() {
            let (key, secret) = rest_client.credentials();
            api_credentials = Some((key.to_string(), secret.to_string()));
            let client_arc = Arc::new(rest_client);
            shared_client = Some(Arc::clone(&client_arc));

            // R-05: Load instrument info cache (lot sizes, tick sizes, min notional)
            // R-05：加載合約信息緩存（步長、tick 精度、最小名義值）
            let instrument_cache =
                Arc::new(openclaw_engine::instrument_info::InstrumentInfoCache::new());
            match instrument_cache.refresh(&*client_arc, "linear").await {
                Ok(count) => {
                    shared_instruments = Some(Arc::clone(&instrument_cache));
                    info!(symbols = count, "instrument info loaded / 品種規格已加載");
                }
                Err(e) => warn!(error = %e, "instrument info fetch failed / 品種規格加載失敗"),
            }

            // Item 8: DCP — Disconnected Cancel Protection
            // 項目 8：DCP — 斷連取消保護
            if cfg_snapshot.dcp_enabled {
                use openclaw_engine::platform_client::PlatformClient;
                let platform = PlatformClient::new(Arc::clone(&client_arc));
                match platform.set_dcp(cfg_snapshot.dcp_time_window).await {
                    Ok(()) => info!(
                        window = cfg_snapshot.dcp_time_window,
                        "DCP enabled / DCP 已啟用"
                    ),
                    Err(e) => {
                        warn!(error = %e, "DCP setup failed (non-fatal) / DCP 設定失敗（非致命）")
                    }
                }
            }

            // Item 7: Auto-add-margin for existing positions
            // 項目 7：為現有倉位啟用自動追加保證金
            if cfg_snapshot.auto_add_margin {
                use openclaw_engine::order_manager::OrderCategory;
                use openclaw_engine::position_manager::PositionManager;
                let pos_mgr = PositionManager::new(Arc::clone(&client_arc));
                match pos_mgr.get_positions(OrderCategory::Linear, None).await {
                    Ok(positions) => {
                        for pos in &positions {
                            if pos.size > 0.0 {
                                match pos_mgr
                                    .set_auto_add_margin(
                                        OrderCategory::Linear,
                                        &pos.symbol,
                                        1,
                                        None,
                                    )
                                    .await
                                {
                                    Ok(()) => {
                                        info!(symbol = %pos.symbol, "auto-margin enabled / 自動追保已啟用")
                                    }
                                    Err(e) => {
                                        warn!(symbol = %pos.symbol, error = %e, "auto-margin failed / 自動追保失敗")
                                    }
                                }
                            }
                        }
                    }
                    Err(e) => {
                        warn!(error = %e, "failed to query positions for auto-margin / 查詢倉位失敗")
                    }
                }
            }

            // Item 2: Fetch dynamic per-symbol fee rates and keep AccountManager
            // alive so the engine can do live per-symbol lookups + periodic refresh.
            // 項目 2：拉取 per-symbol 動態費率，保活 AccountManager 用於後續查詢/刷新。
            let acct = Arc::new(AccountManager::new());
            match acct.refresh_fee_rates(&*client_arc, "linear").await {
                Ok(count) => {
                    let rate = acct.taker_fee("BTCUSDT");
                    api_taker_fee = Some(rate);
                    info!(
                        symbols = count,
                        taker_rate = format!("{:.5}", rate),
                        "fee rates loaded / 費率已加載"
                    );
                }
                Err(e) => {
                    warn!(error = %e, "fee rate fetch failed, using defaults / 費率獲取失敗，使用默認值")
                }
            }
            shared_account_manager = Some(Arc::clone(&acct));

            // Periodic refresh: re-fetch fee rates every 6h to track VIP-tier changes.
            // VIP tier moves are rare (≪daily) so 6h is plenty; cancel-aware so
            // shutdown unwinds cleanly. Staleness monitor below will alarm if
            // refresh task dies or API is unreachable for >12h.
            // 每 6 小時刷新費率，追蹤 VIP 變動；接 cancel token 優雅退出。
            {
                let acct_refresh = Arc::clone(&acct);
                let client_refresh = Arc::clone(&client_arc);
                let cancel_refresh = cancel.clone();
                tokio::spawn(async move {
                    let mut tick =
                        tokio::time::interval(std::time::Duration::from_secs(6 * 3600));
                    tick.tick().await; // skip first immediate tick
                    loop {
                        tokio::select! {
                            _ = cancel_refresh.cancelled() => {
                                info!("fee_rate refresh task stopping (cancel) / 費率刷新任務停止");
                                break;
                            }
                            _ = tick.tick() => {
                                match acct_refresh
                                    .refresh_fee_rates(&*client_refresh, "linear")
                                    .await
                                {
                                    Ok(count) => info!(
                                        symbols = count,
                                        "fee rates refreshed (6h) / 費率已刷新"
                                    ),
                                    Err(e) => {
                                        warn!(error = %e, "fee rate refresh failed / 費率刷新失敗")
                                    }
                                }
                            }
                        }
                    }
                });
            }

            // Staleness monitor: alarm if fee rates haven't refreshed in >12h
            // (refresh task dead or persistent API failure).
            // 費率新鮮度監控：>12h 未刷新告警（refresh task 掛了或 API 持續失敗）。
            {
                let acct_mon = Arc::clone(&acct);
                let cancel_mon = cancel.clone();
                tokio::spawn(async move {
                    let mut tick =
                        tokio::time::interval(std::time::Duration::from_secs(15 * 60));
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
                                if age_h > 12.0 {
                                    warn!(
                                        age_hours = format!("{:.1}", age_h),
                                        "fee rates STALE >12h — refresh task may be dead / 費率過期"
                                    );
                                }
                            }
                        }
                    }
                });
            }
        } else {
            info!(
                "no Bybit credentials — skipping DCP/margin/fee setup / 無 API 憑證，跳過 API 設定"
            );
        }
    } else {
        info!(
            "Bybit client init failed — skipping API setup / Bybit 客戶端初始化失敗，跳過 API 設定"
        );
    }

    // ------------------------------------------------------------------
    // R-05: Periodic instrument info refresh (every 4 hours)
    // R-05：定期刷新合約信息（每 4 小時）
    // ------------------------------------------------------------------
    if let (Some(ref icache), Some(ref client)) = (&shared_instruments, &shared_client) {
        let refresh_cache = Arc::clone(icache);
        let refresh_client = Arc::clone(client);
        let refresh_cancel = cancel.clone();
        tokio::spawn(async move {
            let mut interval = tokio::time::interval(std::time::Duration::from_secs(4 * 3600));
            interval.tick().await; // skip immediate first tick
            loop {
                tokio::select! {
                    _ = refresh_cancel.cancelled() => break,
                    _ = interval.tick() => {
                        match refresh_cache.refresh(&*refresh_client, "linear").await {
                            Ok(n) => info!(symbols = n, "instrument info refreshed / 品種規格已刷新"),
                            Err(e) => warn!(error = %e, "instrument refresh failed / 品種刷新失敗"),
                        }
                    }
                }
            }
        });
    }

    // ------------------------------------------------------------------
    // Scanner D4: Spawn ScannerRunner (requires market REST client)
    // 掃描器 D4：啟動 ScannerRunner（需要市場 REST 客戶端）
    // ------------------------------------------------------------------
    if let Some(ref client) = shared_client {
        let market_client = Arc::new(MarketDataClient::new(Arc::clone(client)));
        let runner = ScannerRunner::new(
            Arc::clone(&symbol_registry),
            market_client,
            Arc::clone(&scanner_edge_estimates),
            Arc::clone(&scanner_store),
            scanner_ws_tx,
            scanner_pipeline_cmd_tx,
            cancel.clone(),
        );
        tokio::spawn(runner.run());
        info!("ScannerRunner spawned / 掃描器已啟動");
    } else {
        warn!("ScannerRunner skipped: no REST client (pinned symbols only) / 掃描器跳過：無 REST 客戶端（僅固定交易對）");
    }

    // ------------------------------------------------------------------
    // Start WS client — subscribe to all symbols (with extended topics if configured)
    // 啟動 WebSocket 客戶端 — 訂閱所有交易對（含擴展 topic）
    // ------------------------------------------------------------------
    // Build subscription list from registry snapshot (initially pinned symbols only;
    // scanner will add more via WsTopicChange::Subscribe as it runs).
    // 從注冊表快照構建訂閱列表（初始僅固定交易對；掃描器運行後通過 WsTopicChange::Subscribe 添加更多）。
    let ws_subscriptions: Vec<String> = if cfg_snapshot.enable_extended_ws {
        let mut topics = Vec::new();
        for sym in symbol_registry.snapshot() {
            // GAP: extended_subscription_list collapsed into full_subscription_list
            // 2026-04-06 — broken topics permanently removed.
            for topic in openclaw_engine::multi_interval_ws::full_subscription_list(&sym) {
                topics.push(topic);
            }
        }
        info!(
            topics_per_symbol = 10,
            "extended WS subscriptions / 擴展 WS 訂閱"
        );
        topics
    } else {
        let mut topics = Vec::new();
        for sym in symbol_registry.snapshot() {
            topics.push(format!("kline.1.{sym}"));
            topics.push(format!("publicTrade.{sym}"));
        }
        topics
    };

    // RE-2: Supervisor wrapper — restarts WS on unexpected exit.
    // Scanner D4: On each restart, rebuild topic list from registry snapshot so
    // scanner-added symbols survive WsClient restarts. Also refresh the relay channel
    // so ScannerRunner's WsTopicChange messages reach the new WsClient.
    // RE-2：監管器包裝 — WS 意外退出時自動重啟。
    // 掃描器 D4：每次重啟時從注冊表快照重建主題列表，掃描器添加的交易對可跨重啟存活。
    // 同時刷新中繼通道，確保 ScannerRunner 的 WsTopicChange 消息到達新的 WsClient。
    let ws_handle = {
        let ws_config = Arc::clone(&config);
        let ws_cancel = cancel.clone();
        let initial_topics = ws_subscriptions.clone();
        let registry_for_supervisor = Arc::clone(&symbol_registry);
        let relay_for_supervisor = Arc::clone(&current_ws_client_tx);
        let extended_ws = cfg_snapshot.enable_extended_ws;
        tokio::spawn(async move {
            let mut supervisor_attempt: u32 = 0;
            loop {
                if ws_cancel.is_cancelled() {
                    break;
                }

                // On restart (attempt > 0), rebuild topics from current registry snapshot
                // so scanner-added symbols are re-subscribed. First attempt uses the
                // pre-built list (which was already from registry.snapshot()).
                // 重啟時（attempt > 0），從注冊表快照重建主題列表。首次使用預建列表。
                let topics: Vec<String> = if supervisor_attempt == 0 {
                    initial_topics.clone()
                } else if extended_ws {
                    registry_for_supervisor.snapshot().into_iter().flat_map(|sym| {
                        openclaw_engine::multi_interval_ws::full_subscription_list(&sym)
                    }).collect()
                } else {
                    registry_for_supervisor.snapshot().into_iter().flat_map(|sym| {
                        vec![format!("kline.1.{sym}"), format!("publicTrade.{sym}")]
                    }).collect()
                };

                let mut ws_client =
                    WsClient::new(Arc::clone(&ws_config), event_tx.clone(), ws_cancel.clone());
                for topic in &topics {
                    ws_client.subscribe(topic.clone());
                }
                // Wire scanner relay: create fresh channel, update shared Arc so relay task
                // forwards to this new WsClient.
                // 接線掃描器中繼：創建新通道，更新共享 Arc 使中繼任務轉發到新 WsClient。
                let inner_tx = ws_client.with_topic_change_channel();
                *relay_for_supervisor.lock().await = Some(inner_tx);

                ws_client.run().await;

                // Channel is now dead — clear it so relay drops messages cleanly.
                // 通道已失效 — 清除它，使中繼任務乾淨地丟棄消息。
                *relay_for_supervisor.lock().await = None;

                // If cancelled, exit cleanly / 如果已取消，正常退出
                if ws_cancel.is_cancelled() {
                    break;
                }

                // Unexpected exit — supervisor restart with backoff
                // 意外退出 — 監管器退避重啟
                supervisor_attempt = supervisor_attempt.saturating_add(1);
                let delay_ms = std::cmp::min(
                    5000_u64.saturating_mul(2_u64.saturating_pow(supervisor_attempt.min(4))),
                    60_000,
                );
                warn!(
                    delay_ms = delay_ms,
                    attempt = supervisor_attempt,
                    "WS supervisor restarting / WS 監管器重啟"
                );
                tokio::select! {
                    _ = ws_cancel.cancelled() => break,
                    _ = tokio::time::sleep(std::time::Duration::from_millis(delay_ms)) => {},
                }
            }
        })
    };

    // ------------------------------------------------------------------
    // 3E D21: Per-pipeline private WS supervisor — extracted into helper.
    // Each exchange-connected pipeline (Demo/Live) gets its own BybitPrivateWs
    // + ExecutionListener. Paper pipelines have no private WS.
    //
    // 3E D21：每管線私有 WS 監管器 — 提取為輔助函數。
    // 每個交易所管線（Demo/Live）獲得自己的 BybitPrivateWs + ExecutionListener。
    // Paper 管線無私有 WS。
    // ------------------------------------------------------------------

    /// Exchange bindings produced by spawning a private WS supervisor.
    /// 啟動私有 WS 監管器後產生的交易所綁定。
    struct PrivateWsBindings {
        // BLOCKER-6 / D12: parking_lot::RwLock for non-poisoning cross-pipeline isolation.
        // BLOCKER-6 / D12：parking_lot::RwLock，不中毒 → 跨管線隔離。
        bybit_balance: Arc<parking_lot::RwLock<Option<f64>>>,
        api_pnl: Arc<parking_lot::RwLock<std::collections::HashMap<String, f64>>>,
        exchange_event_rx: mpsc::UnboundedReceiver<openclaw_engine::event_consumer::ExchangeEvent>,
        _ws_handle: tokio::task::JoinHandle<()>,
        _listener_handle: tokio::task::JoinHandle<()>,
    }

    /// Spawn a per-pipeline private WS supervisor + ExecutionListener.
    /// Returns exchange bindings for the pipeline's EventConsumerDeps.
    /// 為每管線啟動私有 WS 監管器 + 執行監聽器。
    /// 返回管線 EventConsumerDeps 所需的交易所綁定。
    fn spawn_private_ws_supervisor(
        api_key: String,
        api_secret: String,
        env: BybitEnvironment,
        label: &str,
        cancel: CancellationToken,
    ) -> PrivateWsBindings {
        use openclaw_engine::bybit_private_ws::BybitPrivateWs;
        use openclaw_engine::event_consumer::ExchangeEvent;
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

    // Spawn private WS for the primary exchange pipeline (if credentials exist).
    // Paper pipelines have no private WS.
    // 為主交易所管線啟動私有 WS（如有憑證）。Paper 管線無私有 WS。
    let primary_ws_bindings: Option<PrivateWsBindings> =
        if let Some((api_key, api_secret)) = api_credentials {
            Some(spawn_private_ws_supervisor(
                api_key,
                api_secret,
                bybit_env,
                match bybit_env {
                    BybitEnvironment::Demo | BybitEnvironment::Testnet => "demo",
                    BybitEnvironment::Mainnet | BybitEnvironment::LiveDemo => "live",
                },
                cancel.clone(),
            ))
        } else {
            info!("no credentials — Private WS skipped / 無憑證，跳過私有 WS");
            None
        };

    // Extract exchange bindings for EventConsumerDeps / 提取交易所綁定
    let (shared_bybit_balance, shared_api_pnl, shared_exchange_event_rx) = match primary_ws_bindings
    {
        Some(bindings) => (
            Some(Arc::clone(&bindings.bybit_balance)),
            Some(Arc::clone(&bindings.api_pnl)),
            Some(bindings.exchange_event_rx),
        ),
        None => (None, None, None),
    };

    // ------------------------------------------------------------------
    // Event consumer — feeds into TickPipeline for paper trading
    // 事件消費者 — 送入 TickPipeline 進行紙盤交易
    // (Phase 1 Day 0-A: extracted to event_consumer.rs)
    // ------------------------------------------------------------------
    // ------------------------------------------------------------------
    // Phase 1: Database pool + writer tasks
    // Phase 1：資料��連接池 + 寫入器任務
    // ------------------------------------------------------------------
    let cfg_snap_db = config.get();
    let db_pool =
        Arc::new(openclaw_engine::database::pool::DbPool::connect(&cfg_snap_db.database).await);

    // Phase 4 (4-15): Initialize the AI BudgetTracker now that db_pool is ready and
    // inject it into the IPC server slot. If init fails, the slot stays None and
    // get_ai_budget_status fail-soft returns "uninitialized".
    // Phase 4 (4-15)：db_pool 就緒後初始化 AI BudgetTracker，並注入 IPC server 槽位。
    // 若初始化失敗，槽位保持 None，get_ai_budget_status fail-soft 回傳 "uninitialized"。
    // ARCH-RC1 1C-2-E: inject audit pool into IPC server slot so patch_*_config
    // can write V014 engine_events rows. PgPool is internally Arc so cheap to clone.
    // ARCH-RC1 1C-2-E：注入審計 pool 到 IPC server 槽位，讓 patch_*_config
    // 可寫 V014 engine_events。PgPool 內部即 Arc，clone 成本低。
    if let Some(pg) = db_pool.get() {
        audit_pool_slot.write().await.replace(pg.clone());
        info!("ARCH-RC1 audit pool wired to IPC / 審計 pool 已接入 IPC");
    }

    if db_pool.is_available() {
        match openclaw_engine::ai_budget::BudgetTracker::new(Arc::clone(&db_pool)).await {
            Ok(tracker) => {
                budget_tracker_slot.write().await.replace(Arc::new(tracker));
                info!("BudgetTracker initialized / AI 預算追蹤器已初始化");
            }
            Err(e) => {
                warn!(error = %e, "BudgetTracker init failed, AI budget enforcement disabled / 預算追蹤器初始化失敗");
            }
        }
    } else {
        warn!("db_pool unavailable, BudgetTracker not started / db_pool 不可用，BudgetTracker 未啟動");
    }

    // ------------------------------------------------------------------
    // Phase 4 W-3/W-4: Construct LinUCB runtime + news context snapshot.
    // These are shared resources plumbed to TickPipeline via EventConsumerDeps,
    // and to the future News producer loop via the snapshot handle.
    // Phase 4 W-3/W-4：構造 LinUCB runtime + 新聞 context 快照。
    // 這些共享資源透過 EventConsumerDeps 接入 TickPipeline，並透過快照句柄
    // 供未來的 News producer loop 使用。
    // ------------------------------------------------------------------
    let shared_linucb_runtime = Arc::new(
        openclaw_engine::linucb::LinUcbRuntime::cold_start_v1_15(),
    );
    info!(
        active_version = shared_linucb_runtime.arm_space_version(),
        feature_schema_hash = shared_linucb_runtime.feature_schema_hash(),
        "LinUcbRuntime cold-started / LinUCB runtime 冷啟動"
    );

    let shared_news_snapshot = Arc::new(
        openclaw_engine::news::NewsContextSnapshot::new(),
    );
    info!(
        "NewsContextSnapshot constructed (default severity 0.0) / 新聞 context 快照已建立"
    );

    // ------------------------------------------------------------------
    // Phase 4 W-1/W-2: Shared governance halted handle + guardian impl.
    // GovernanceCoreWrapper and GuardianHaltCheckImpl share the same
    // Arc<AtomicBool> so news-triggered halts are immediately visible to
    // the Teacher DirectiveApplier (single source of truth, no double-write).
    // The DirectiveApplier itself is not constructed here yet — it has no
    // live invoker (Claude API pull loop is a follow-up task); the wrappers
    // exist ready for that task to plug in.
    // Phase 4 W-1/W-2：共享 governance halted 句柄 + guardian impl。
    // GovernanceCoreWrapper 與 GuardianHaltCheckImpl 共享同一個
    // Arc<AtomicBool>，使新聞觸發的 halt 對 Teacher DirectiveApplier 立即可見
    // （單一真相源，無雙寫）。DirectiveApplier 本身尚未在此構造 —— 還沒有
    // live invoker（Claude API 拉取 loop 是後續任務）；wrapper 已就位供該
    // 任務直接插入。
    let governance_wrapper = Arc::new(
        openclaw_engine::claude_teacher::GovernanceCoreWrapper::with_defaults(vec![
            "ma_crossover".to_string(),
            "bb_reversion".to_string(),
            "bb_breakout".to_string(),
            "grid_trading".to_string(),
            "funding_arb".to_string(),
        ]),
    );
    let shared_halted_handle = governance_wrapper.halted_handle();
    let guardian_impl = Arc::new(
        openclaw_engine::news::GuardianHaltCheckImpl::new(Arc::clone(&shared_halted_handle)),
    );
    info!(
        "Phase 4 governance+guardian wrappers constructed (sharing halted atomic) / W-1/W-2 wrappers 已構造"
    );
    // Guardian impl is consumed by the A2 news pipeline scheduler below.
    // Guardian impl 由下方 A2 新聞 pipeline 排程器使用。
    let phase4_guardian_impl = guardian_impl;

    // ------------------------------------------------------------------
    // Phase 4.1: Construct + spawn TeacherConsumerLoop (DEFAULT-OFF).
    // The loop ticks at the configured interval but skips all work until
    // operator flips the enabled flag via IPC AFTER E3 R6 audit PASSes.
    // Loop skipped entirely if BudgetTracker / db_pool is unavailable.
    //
    // Phase 4.1：構造並 spawn TeacherConsumerLoop（**預設關閉**）。
    // Loop 按設定間隔 tick，但在 operator 透過 IPC 翻開 enabled 旗標
    // （E3 R6 審計通過後）之前跳過所有工作。BudgetTracker 或 db_pool
    // 不可用時整個 loop 跳過構造。
    // ------------------------------------------------------------------
    if db_pool.is_available() {
        let budget_opt = budget_tracker_slot.read().await.clone();
        if let Some(budget) = budget_opt {
            use openclaw_engine::claude_teacher::{
                AnthropicClient, ClaudeTeacher, ConsumerLoopConfig, DirectiveApplier,
                GovernanceCheck, LlmClient, OutcomeTracker, PipelineCommandSink,
                StrategyIpcSink, TeacherConsumerLoop,
            };
            use std::sync::atomic::AtomicBool;
            let model = "claude-sonnet-4-5";
            let llm_client: Arc<dyn LlmClient + Send + Sync> =
                Arc::new(AnthropicClient::new(model));
            let teacher = Arc::new(ClaudeTeacher::new(
                llm_client,
                Some(Arc::clone(&budget)),
                Arc::clone(&db_pool),
                model,
            ));
            let governance_for_applier: Arc<dyn GovernanceCheck> =
                Arc::clone(&governance_wrapper) as Arc<dyn GovernanceCheck>;
            let ipc_sink: Arc<dyn StrategyIpcSink> =
                Arc::new(PipelineCommandSink::new(phase4_consumer_cmd_tx));
            let applier = Arc::new(DirectiveApplier::new(
                governance_for_applier,
                Some(ipc_sink),
                Arc::clone(&db_pool),
            ));
            let outcome_tracker = Arc::new(OutcomeTracker::new(Arc::clone(&db_pool)));
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
        } else {
            warn!("Phase 4.1 consumer loop skipped: BudgetTracker not initialized / 預算追蹤器未初始化，consumer loop 跳過");
        }
    } else {
        warn!("Phase 4.1 consumer loop skipped: db_pool unavailable / db_pool 不可用，consumer loop 跳過");
    }
    // Hold the governance wrapper alive (cloned into the applier above when
    // db_pool is available; this binding ensures it lives for the rest of main).
    // 保持 governance wrapper 存活（db_pool 可用時已被 clone 進 applier，
    // 此 binding 確保它在 main 餘下時間都存活）。
    let _phase4_governance_wrapper = governance_wrapper;

    // ------------------------------------------------------------------
    // A2: NewsPipeline 60s scheduler — periodic news fetch → dedup → score → persist.
    // Gated by LearningConfig.switches.news_pipeline_enabled (hot-reloadable).
    // Providers: CryptoPanic (free tier, 28min self-throttle) + 2 RSS feeds.
    // Router: Guardian halt check + regime buffer + learning context sink.
    //
    // A2：新聞管線 60s 排程器 — 定期拉取新聞 → 去重 → 評分 → 寫入。
    // 受 LearningConfig.switches.news_pipeline_enabled 控制（可熱重載）。
    // Providers：CryptoPanic（免費版，28min 自限流）+ 2 個 RSS feed。
    // Router：Guardian halt check + regime buffer + learning context sink。
    // ------------------------------------------------------------------
    {
        use openclaw_engine::news::{
            CryptoPanicProvider, GuardianHaltCheck, LearningContextSink,
            LearningContextSinkImpl, NewsPipeline, NewsRouter, RssProvider,
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
        let learning_sink = Arc::new(LearningContextSinkImpl::new(
            Arc::clone(&shared_news_snapshot),
        ));
        let regime_buffer = Arc::new(RwLock::new(
            openclaw_engine::news::RegimeNewsBuffer::default(),
        ));
        let router = Arc::new(NewsRouter::new(
            Some(phase4_guardian_impl as Arc<dyn GuardianHaltCheck>),
            regime_buffer,
            Some(learning_sink as Arc<dyn LearningContextSink>),
        ));

        // Build pipeline with router attached.
        // 建構帶 router 的 pipeline。
        let pipeline = Arc::new(
            NewsPipeline::new(providers, Arc::clone(&db_pool)).with_router(router),
        );

        let news_learning_store = Arc::clone(&learning_store);
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

    let (market_tx, market_rx) = if db_pool.is_available() {
        let (tx, rx) = tokio::sync::mpsc::channel(4096);
        (Some(tx), Some(rx))
    } else {
        (None, None)
    };
    let (feature_tx, feature_rx) = if db_pool.is_available() {
        let (tx, rx) = tokio::sync::mpsc::channel(2048);
        (Some(tx), Some(rx))
    } else {
        (None, None)
    };

    // Spawn market writer task / 啟���市場數據寫入器任務
    if let Some(mrx) = market_rx {
        let mw_pool = Arc::clone(&db_pool);
        let mw_config = Arc::clone(&config);
        let mw_cancel = cancel.clone();
        tokio::spawn(openclaw_engine::database::market_writer::run_market_writer(
            mrx, mw_pool, mw_config, mw_cancel,
        ));
    }

    // Spawn feature writer task / 啟動特徵寫入器任務
    if let Some(frx) = feature_rx {
        let fw_pool = Arc::clone(&db_pool);
        let fw_config = Arc::clone(&config);
        let fw_cancel = cancel.clone();
        tokio::spawn(
            openclaw_engine::database::feature_writer::run_feature_writer(
                frx, fw_pool, fw_config, fw_cancel,
            ),
        );
    }

    // Phase 2a: Trading lifecycle channel + writer task
    // Phase 2a：交易生命週期通道 + 寫入器任務
    let (trading_tx, trading_rx) = if db_pool.is_available() {
        let (tx, rx) = tokio::sync::mpsc::channel(4096);
        (Some(tx), Some(rx))
    } else {
        (None, None)
    };
    if let Some(trx) = trading_rx {
        let tw_pool = Arc::clone(&db_pool);
        let tw_config = Arc::clone(&config);
        let tw_cancel = cancel.clone();
        tokio::spawn(
            openclaw_engine::database::trading_writer::run_trading_writer(
                trx, tw_pool, tw_config, tw_cancel,
            ),
        );
    }

    // Phase 2a: Decision context channel + writer task
    let (context_tx, context_rx) = if db_pool.is_available() {
        let (tx, rx) = tokio::sync::mpsc::channel(1024);
        (Some(tx), Some(rx))
    } else {
        (None, None)
    };
    if let Some(crx) = context_rx {
        let cw_pool = Arc::clone(&db_pool);
        let cw_config = Arc::clone(&config);
        let cw_cancel = cancel.clone();
        tokio::spawn(
            openclaw_engine::database::context_writer::run_context_writer(
                crx, cw_pool, cw_config, cw_cancel,
            ),
        );
    }

    // F-4 fix: Spawn REST pollers for funding/OI/LSR (requires API client + market channel)
    // F-4 修復：啟動 funding/OI/LSR REST 輪詢器
    // Scanner D4 / m-3 fix: pass registry snapshot so pollers cover all active symbols.
    // 掃描器 D4 / m-3 修復：傳注冊表快照，使輪詢器覆蓋所有活躍交易對。
    if let (Some(ref client), Some(ref mtx)) = (&shared_client, &market_tx) {
        let poll_symbols = symbol_registry.snapshot();
        openclaw_engine::database::rest_poller::spawn_rest_pollers(
            Arc::clone(client),
            mtx.clone(),
            poll_symbols,
            cancel.clone(),
        );
    }

    // F-5 fix: Spawn data quality monitor (uses shared last_tick_ms counter)
    // F-5 修復：啟動數據質量監控器
    let shared_last_tick_ms = Arc::new(std::sync::atomic::AtomicU64::new(0));
    if db_pool.is_available() {
        let qm_pool = Arc::clone(&db_pool);
        let qm_tick = Arc::clone(&shared_last_tick_ms);
        // Scanner D4: use registry snapshot for quality monitor symbols.
        // 掃描器 D4：使用注冊表快照作為質量監控器的交易對列表。
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
    if db_pool.is_available() {
        let dd_pool = Arc::clone(&db_pool);
        let dd_config = Arc::clone(&config);
        let dd_cancel = cancel.clone();
        tokio::spawn(
            openclaw_engine::database::drift_detector::run_drift_detector(
                dd_pool, dd_config, dd_cancel,
            ),
        );
    }

    // G3 1-16: Feature version init — insert v1.0 row on startup if PG available
    // G3 1-16：特徵版本初始化 — 啟動時插入 v1.0 行
    if db_pool.is_available() {
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
    }

    // ------------------------------------------------------------------
    // Phase 6: spawn position reconciler with auto-contraction action layer.
    // Gated on Some(shared_client) — paper-only / no-REST runs skip entirely.
    // Phase 6：spawn 持倉對帳器（含自動降級動作層）。需要 shared_client。
    if let Some(client) = shared_client.as_ref() {
        use openclaw_engine::position_manager::PositionManager;
        use openclaw_engine::position_reconciler::run_position_reconciler;
        let pos_mgr = Arc::new(PositionManager::new(Arc::clone(client)));
        let reconciler_audit_pool = db_pool.get().cloned();
        let reconciler_cancel = cancel.clone();
        let reconciler_instruments = shared_instruments.clone();
        // Phase 6: closure reads current risk level from shared atomic.
        // Phase 6：閉包從共享原子量讀取當前風控級別。
        let reconciler_risk_level = Arc::clone(&shared_risk_level);
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
            reconciler_cmd_tx,
            reconciler_instruments,
            get_risk_level,
            reconciler_label,
        ));
        info!("position_reconciler task spawned (Phase 6 auto-contraction) / 持倉對帳器任務已啟動（Phase 6 自動降級）");
    } else {
        info!("position_reconciler skipped (no REST client) / 持倉對帳器跳過（無 REST 客戶端）");
    }

    // ------------------------------------------------------------------
    // 3E-2b-α: Multi-pipeline spawn skeleton + bounded fan-out
    // 3E-2b-α：多管線 spawn 骨架 + 有界扇出
    //
    // Paper pipeline always spawns. Demo/Live spawn conditionally based on
    // API key detection (determine_primary_kind).
    // Each pipeline gets its own event_rx (from fan-out), pipeline_cmd channel,
    // and risk_level atomic. DB writer channels are shared across all pipelines.
    //
    // Paper 管線始終啟動。Demo/Live 根據 API key 偵測條件啟動。
    // 每管線獨立 event_rx（扇出）、pipeline_cmd 通道、
    // risk_level 原子量。DB writer 通道跨管線共享。
    // ------------------------------------------------------------------
    use openclaw_engine::event_consumer::{run_event_consumer, EventConsumerDeps};

    // 3E-10.2: Determine primary pipeline from API key detection.
    // Paper always runs. The "primary" pipeline (Demo or Live) gets exchange
    // bindings (private WS, bybit client, account manager). Paper gets None.
    // 3E-10.2：從 API key 偵測決定主管線。Paper 始終運行。
    // "主要"管線（Demo 或 Live）獲得交易所綁定。Paper 獲得 None。
    let primary_kind = determine_primary_kind();
    // In PaperOnly mode, only Paper runs (it IS the primary).
    // In Demo/Live mode, Paper runs alongside the primary exchange-connected pipeline.
    // PaperOnly 模式下只有 Paper 運行（它就是主管線）。
    // Demo/Live 模式下 Paper 與主交易所管線並行。
    let spawn_paper_alongside = primary_kind != PipelineKind::Paper;

    // ------------------------------------------------------------------
    // 3E D10/D20: Bounded fan-out — one WS source, N pipeline receivers.
    // Arc<PriceEvent> avoids deep-cloning HashMap metadata per pipeline.
    // 有界扇出 — 一個 WS 源，N 個管線接收端。
    // Arc<PriceEvent> 避免每管線深拷貝 HashMap metadata。
    // ------------------------------------------------------------------
    // Primary pipeline channel (1024 for Paper/Demo, 512 for Live)
    let primary_buf = if primary_kind == PipelineKind::Live { 512 } else { 1024 };
    let (primary_event_tx, primary_event_rx) = mpsc::channel::<Arc<PriceEvent>>(primary_buf);
    // Paper-alongside channel (only if Paper runs separately from primary)
    let paper_alongside_channel: Option<(
        mpsc::Sender<Arc<PriceEvent>>,
        mpsc::Receiver<Arc<PriceEvent>>,
    )> = if spawn_paper_alongside {
        Some(mpsc::channel(1024))
    } else {
        None
    };

    // Fan-out task: read from single event_rx, broadcast Arc-wrapped events
    // 扇出任務：從單一 event_rx 讀取，廣播 Arc 包裝的事件
    {
        let primary_tx = primary_event_tx;
        let paper_tx = paper_alongside_channel
            .as_ref()
            .map(|(tx, _)| tx.clone());
        let fan_cancel = cancel.clone();
        tokio::spawn(async move {
            let mut event_rx = event_rx;
            loop {
                tokio::select! {
                    _ = fan_cancel.cancelled() => break,
                    evt = event_rx.recv() => {
                        match evt {
                            Some(price_event) => {
                                let arc_event = Arc::new(price_event);
                                // Primary pipeline — lag detection with try_send
                                if primary_tx.try_send(Arc::clone(&arc_event)).is_err() {
                                    tracing::warn!(
                                        kind = %primary_kind,
                                        "fan-out: primary pipeline lagging, tick dropped / 主管線延遲，tick 已丟棄"
                                    );
                                }
                                // Paper-alongside pipeline
                                if let Some(ref ptx) = paper_tx {
                                    if ptx.try_send(arc_event).is_err() {
                                        tracing::debug!(
                                            "fan-out: paper pipeline lagging, tick dropped / Paper 管線延遲，tick 已丟棄"
                                        );
                                    }
                                }
                            }
                            None => break, // WS channel closed
                        }
                    }
                }
            }
            tracing::info!("fan-out task stopped / 扇出任務已停止");
        });
    }

    // ------------------------------------------------------------------
    // Per-pipeline command channels + risk level atomics
    // 每管線命令通道 + 風控級別原子量
    // ------------------------------------------------------------------
    // 3E-3: Primary pipeline uses pipeline_cmd_rx (IPC wired via EngineCommandChannels).
    // Paper-alongside uses pipeline_cmd_rx_paper (IPC wired above).
    // 3E-3：主管線使用 pipeline_cmd_rx（IPC 通過 EngineCommandChannels 接線）。
    // Paper 伴隨管線使用 pipeline_cmd_rx_paper（上方已接入 IPC）。
    let pipeline_cmd_rx_paper_opt: Option<mpsc::UnboundedReceiver<openclaw_engine::tick_pipeline::PipelineCommand>> =
        if spawn_paper_alongside {
            Some(pipeline_cmd_rx_paper)
        } else {
            None
        };
    // Paper-alongside risk level atomic (separate from primary)
    let paper_risk_level: Option<Arc<std::sync::atomic::AtomicU8>> = if spawn_paper_alongside {
        Some(Arc::new(std::sync::atomic::AtomicU8::new(
            openclaw_core::sm::risk_gov::RiskLevel::Normal.value(),
        )))
    } else {
        None
    };

    // ------------------------------------------------------------------
    // Spawn primary pipeline (Demo/Live with exchange bindings, or Paper if PaperOnly)
    // 啟動主管線（Demo/Live 帶交易所綁定，或 PaperOnly 時為 Paper）
    // ------------------------------------------------------------------
    let event_handle = {
        let deps = EventConsumerDeps {
            pipeline_kind: primary_kind,
            event_rx: primary_event_rx,
            config: Arc::clone(&config),
            cancel: cancel.clone(),
            initial_balance,
            paper_initial_balance,
            taker_fee_rate: api_taker_fee,
            instruments: shared_instruments.clone(),
            bootstrap_client: shared_client.as_ref().map(Arc::clone),
            shared_client: shared_client.clone(),
            bybit_balance: shared_bybit_balance,
            api_pnl: shared_api_pnl,
            pipeline_cmd_rx: Some(pipeline_cmd_rx),
            // 3E-10.5: Only Paper writes market_data/features to DB (dedup).
            // Demo/Live skip these to avoid duplicate rows.
            // 3E-10.5：僅 Paper 寫入 market_data/features（去重）。
            market_data_tx: if primary_kind == PipelineKind::Paper { market_tx.clone() } else { None },
            feature_tx: if primary_kind == PipelineKind::Paper { feature_tx.clone() } else { None },
            last_tick_ms: Some(Arc::clone(&shared_last_tick_ms)),
            trading_tx: trading_tx.clone(),
            context_tx: context_tx.clone(),
            exchange_event_rx: shared_exchange_event_rx,
            account_manager: shared_account_manager.clone(),
            linucb_runtime: Some(Arc::clone(&shared_linucb_runtime)),
            news_snapshot: Some(Arc::clone(&shared_news_snapshot)),
            risk_store: {
                let store = match primary_kind {
                    PipelineKind::Live => Arc::clone(&risk_stores.live),
                    PipelineKind::Demo => Arc::clone(&risk_stores.demo),
                    PipelineKind::Paper => Arc::clone(&risk_stores.paper),
                };
                Some(store)
            },
            budget_store: Some(Arc::clone(&budget_store)),
            audit_pool: db_pool.get().cloned(),
            symbol_registry: Some(Arc::clone(&symbol_registry)),
            scanner_store: Some(Arc::clone(&scanner_store)),
            shared_risk_level: Some(Arc::clone(&shared_risk_level)),
            is_primary: true,
        };
        tokio::spawn(run_event_consumer(deps))
    };
    info!(kind = %primary_kind, "primary pipeline spawned / 主管線已啟動");

    // ------------------------------------------------------------------
    // Spawn Paper-alongside pipeline (when primary is Demo or Live)
    // 啟動 Paper 伴隨管線（當主管線為 Demo 或 Live 時）
    // ------------------------------------------------------------------
    let _paper_handle = if spawn_paper_alongside {
        let (_, paper_event_rx) = paper_alongside_channel.unwrap();
        let pipeline_cmd_rx_paper = pipeline_cmd_rx_paper_opt.unwrap();
        let paper_rl = paper_risk_level.unwrap();
        // Paper uses demo balance for initial_balance (mirrors demo account)
        // Paper 使用 demo 餘額作為初始餘額（映射 demo 帳號）
        let paper_balance = paper_initial_balance.unwrap_or(initial_balance);
        let deps = EventConsumerDeps {
            pipeline_kind: PipelineKind::Paper,
            event_rx: paper_event_rx,
            config: Arc::clone(&config),
            cancel: cancel.clone(),
            initial_balance: paper_balance,
            paper_initial_balance: None,
            taker_fee_rate: api_taker_fee,
            instruments: shared_instruments.clone(),
            // Paper has no exchange bindings / Paper 無交易所綁定
            bootstrap_client: None,
            shared_client: None,
            bybit_balance: None,
            api_pnl: None,
            pipeline_cmd_rx: Some(pipeline_cmd_rx_paper),
            // Shared DB writer channels / 共享 DB 寫入通道
            market_data_tx: market_tx,
            feature_tx,
            last_tick_ms: Some(Arc::clone(&shared_last_tick_ms)),
            trading_tx,
            context_tx,
            // No exchange events for paper / Paper 無交易所事件
            exchange_event_rx: None,
            account_manager: None,
            linucb_runtime: Some(Arc::clone(&shared_linucb_runtime)),
            news_snapshot: Some(Arc::clone(&shared_news_snapshot)),
            risk_store: Some(Arc::clone(&risk_stores.paper)),
            budget_store: Some(Arc::clone(&budget_store)),
            audit_pool: db_pool.get().cloned(),
            symbol_registry: Some(Arc::clone(&symbol_registry)),
            scanner_store: Some(Arc::clone(&scanner_store)),
            shared_risk_level: Some(paper_rl),
            is_primary: false,
        };
        let h = tokio::spawn(run_event_consumer(deps));
        info!("paper-alongside pipeline spawned / Paper 伴隨管線已啟動");
        Some(h)
    } else {
        None
    };

    info!(version = VERSION, "engine started / 引擎已啟動");

    // ------------------------------------------------------------------
    // Signal handling / 信號處理
    // ------------------------------------------------------------------
    signal_loop(&config, &cancel).await;

    // ------------------------------------------------------------------
    // Shutdown sequence / 關閉序列
    // ------------------------------------------------------------------
    info!("initiating shutdown / 開始關閉序列");

    // 1. Cancel all tasks / 取消所有任務
    cancel.cancel();

    // 2. Wait for tasks to finish (with timeout) / 等待任務完成（帶超時）
    let shutdown_timeout = tokio::time::Duration::from_secs(10);
    let _ = tokio::time::timeout(shutdown_timeout, async {
        let _ = ws_handle.await;
        let _ = ipc_handle.await;
        let _ = event_handle.await;
        // 3E: Await paper-alongside handle if present / 等待 Paper 伴隨管線
        if let Some(ph) = _paper_handle {
            let _ = ph.await;
        }
        // Private WS handles are dropped here — supervisor tasks receive cancel
        // and exit on their own via the CancellationToken.
        // 私有 WS 句柄在此丟棄 — 監管器任務通過 CancellationToken 自行退出。
    })
    .await;

    // 3. Clean up socket file / 清理套接字文件
    let socket_path = &config.get().ipc_socket_path;
    if std::path::Path::new(socket_path).exists() {
        let _ = tokio::fs::remove_file(socket_path).await;
        info!(
            path = socket_path,
            "socket file cleaned up / 套接字文件已清理"
        );
    }

    info!(version = VERSION, "engine stopped / 引擎已停止");
}

/// Listen for OS signals: SIGHUP → reload, SIGTERM/SIGINT → shutdown.
/// 監聽 OS 信號：SIGHUP → 重載，SIGTERM/SIGINT → 關閉。
async fn signal_loop(config: &Arc<ConfigManager>, cancel: &CancellationToken) {
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
fn print_banner() {
    info!("==============================================");
    info!("  OpenClaw Engine v{}", VERSION);
    info!("  Mode: Live_Ready | Execution: operator-gated");
    info!("  Bybit V5 Linear — Rust Trading Engine");
    info!("==============================================");
}
