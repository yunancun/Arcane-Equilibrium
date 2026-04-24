//! Startup helpers — balance resolution, pipeline detection, replay mode,
//! config loading, private WS supervision, signal handling, banner.
//! 啟動輔助函數 — 餘額解析、管線偵測、回放模式、配置載入、
//! 私有 WS 監管、信號處理、啟動標語。

use openclaw_engine::account_manager::AccountManager;
use openclaw_engine::bybit_rest_client::{BybitEnvironment, BybitRestClient};
use openclaw_engine::config::{
    load_toml_or_default, BudgetConfig, ConfigManager, ConfigStore, LearningConfig, RiskConfig,
};
use openclaw_engine::event_consumer::{ExchangeEvent, SYMBOLS};
use openclaw_engine::ipc_server::PerEngineRiskStores;
use openclaw_engine::live_authorization::AUTHORIZATION_FILENAME;
use openclaw_engine::restart_kind::{self, RestartKind};
use openclaw_engine::strategies::{
    bb_breakout::BbBreakout, bb_reversion::BbReversion, grid_trading::GridTrading,
    ma_crossover::MaCrossover,
};
use openclaw_engine::tick_pipeline::{PipelineKind, TickPipeline};
use openclaw_types::PriceEvent;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio::task::JoinHandle;
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
    if val > 0.0 {
        Some(val)
    } else {
        None
    }
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

// 3E-ARCH: detect_available_pipelines() and determine_primary_kind() removed.
// Pipeline availability is now determined by build_exchange_pipeline() returning Some/None.
// 管線可用性現由 build_exchange_pipeline() 返回 Some/None 決定。

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
            if paper.exists() {
                paper
            } else {
                base.join("risk_config.toml")
            }
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
    // MICRO-PROFIT-FIX-1 (2026-04-17): BudgetConfig gets a two-step load —
    // parse without validation, run sanitize_legacy_budget_config to clamp
    // out-of-range `cost_edge_max_ratio` (legacy snapshots may hold up to 100.0
    // while the new ceiling is 10.0), then validate. Ensures the engine does
    // not fail-closed on historical state after the range shrink.
    // MICRO-PROFIT-FIX-1：BudgetConfig 兩段載入——先不驗證地 parse，跑 sanitize
    // 遷移把舊 snapshot 超範圍的 cost_edge_max_ratio（可能是 100.0）clamp 回
    // default，再 validate。避免範圍縮窄後引擎因歷史值 fail-close 起不來。
    let mut budget: BudgetConfig = load_toml_or_default(&budget_path, |_c: &BudgetConfig| Ok(()))
        .map_err(|e| format!("budget config: {}", e))?;
    let rewritten =
        openclaw_engine::config::legacy_migration::sanitize_legacy_budget_config(&mut budget);
    if !rewritten.is_empty() {
        info!(
            fields = ?rewritten,
            "MICRO-PROFIT-FIX-1 BudgetConfig legacy fields clamped / 已清洗超範圍欄位"
        );
    }
    budget
        .validate()
        .map_err(|e| format!("budget config (post-sanitize): {}", e))?;

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

/// Per-exchange pipeline resources — one instance per Demo/Live pipeline.
/// 每條交易所管線的獨立資源（Demo/Live 各一份）。
pub(crate) struct ExchangePipelineBindings {
    pub env: BybitEnvironment,
    pub rest_client: Arc<BybitRestClient>,
    pub account_manager: Arc<AccountManager>,
    pub taker_fee: Option<f64>,
    pub initial_balance: f64,
    pub ws_bindings: PrivateWsBindings,
    pub risk_level: Arc<std::sync::atomic::AtomicU8>,
    pub health: Arc<std::sync::atomic::AtomicU8>,
    /// B-1 Phase 2: Snapshot of existing exchange positions captured at startup.
    /// Forwarded into EventConsumerDeps so paper_state can be seeded before the
    /// first market tick. Empty Vec on cold accounts or REST failure.
    /// B-1 Phase 2：啟動時抓取的交易所現存持倉快照，傳給 EventConsumerDeps，
    /// 讓 paper_state 在首個市場 tick 前就能與交易所側對齊。
    /// 帳戶為空或 REST 失敗時為空 Vec。
    pub seed_positions: Vec<(String, bool, f64, f64, u64)>,
}

/// Build exchange pipeline bindings if credentials exist for the given environment.
/// Returns None if no API key found → that pipeline will not start.
///
/// PIPELINE-SLOT-1 Phase 2:
///   The `cancel` token passed in is the **slot-scoped child token** created
///   by `PipelineSlot::try_spawn`. Every `tokio::spawn` performed inside this
///   function watches that token so a slot-scoped teardown (auth revoke /
///   expiry) stops them without collateral damage to other slots (demo /
///   paper). Returns `(bindings, task_handles)` so the caller can hand the
///   handles to `SlotState::Spawned.task_handles` for deterministic join on
///   teardown.
///
/// 為指定環境構建交易所管線綁定（若有 API key）。
/// 若無 API key 則返回 None → 該管線不啟動。
///
/// PIPELINE-SLOT-1 Phase 2：傳入的 `cancel` 是 `PipelineSlot::try_spawn`
/// 建立的**槽位子 token**。本函式內每個 `tokio::spawn` 都監看該 token，
/// 於 slot-scoped teardown（授權撤銷/過期）時乾淨停止，不波及其他 slot。
/// 回傳 `(bindings, task_handles)`，讓呼叫者把 handle 放入
/// `SlotState::Spawned.task_handles` 以供 teardown 時確定性地 join。
pub(crate) async fn build_exchange_pipeline(
    kind: PipelineKind,
    env: BybitEnvironment,
    cancel: CancellationToken,
    cfg_snapshot: &openclaw_engine::config::EngineBootstrap,
) -> Option<(ExchangePipelineBindings, Vec<JoinHandle<()>>)> {
    // LIVE-GATE-BINDING-1 (2026-04-18): Enforce the signed Earned-Trust
    // authorization for the Live pipeline. Python writes a HMAC-signed
    // `authorization.json` on every renew/approve; Rust refuses to spawn
    // Live without a valid, unexpired, env-matching record. LiveDemo is
    // held to the same bar as Mainnet by design — the whole point of
    // LiveDemo is to exercise the Live gate code paths before real money.
    // LIVE-GATE-BINDING-1：Live 管線強制簽名授權。Python 在每次 renew/approve
    // 後 HMAC 簽名寫入 authorization.json；Rust 驗簽/未過期/env 匹配才啟動。
    // LiveDemo 與 Mainnet 同標準 — LiveDemo 的目的就是提前壓測 Live gate。
    if kind == PipelineKind::Live {
        use openclaw_engine::live_authorization::{auth_error_kind, load_and_verify};
        match load_and_verify(env) {
            Ok(auth) => {
                info!(
                    kind = %kind,
                    env = ?env,
                    tier = %auth.tier,
                    operator_id = %auth.operator_id,
                    expires_at_ms = auth.expires_at_ms,
                    env_allowed = ?auth.env_allowed,
                    "live authorization verified / live 授權已驗證"
                );
            }
            Err(e) => {
                warn!(
                    kind = %kind,
                    env = ?env,
                    error_kind = auth_error_kind(&e),
                    error = %e,
                    "LIVE PIPELINE REFUSED TO START — signed authorization check failed. \
                     Operator: approve via POST /api/v1/live/auth/renew (or renew-review). \
                     / Live 管線拒絕啟動 — 簽名授權檢查失敗。請經 /auth/renew 批准。"
                );
                return None;
            }
        }
    }

    let rest_client = match BybitRestClient::new(env, None, None) {
        Ok(c) if c.has_credentials() => c,
        Ok(_) => {
            info!(
                kind = %kind,
                "no API credentials for {kind} pipeline — skipped / 無 API 憑證，跳過 {kind} 管線"
            );
            return None;
        }
        Err(e) => {
            warn!(kind = %kind, error = %e, "Bybit client init failed for {kind} / Bybit 客戶端初始化失敗");
            return None;
        }
    };

    // NOTE: Credentials are cloned to String and moved into the WS reconnect closure.
    // They persist in memory for the lifetime of the pipeline (needed for WS reconnection).
    // Rust's default String::drop does not guarantee memory zeroing.
    // Acceptable tradeoff: the process address space is not shared, and credentials
    // are already present in the REST client. If defense-in-depth zeroing is needed
    // in the future, wrap with `secrecy::SecretString` (requires adding dependency).
    // 注意：憑證被複製為 String 並移入 WS 重連閉包。它們在管線生命週期內常駐記憶體
    // （WS 重連需要）。Rust 默認 String::drop 不保證記憶體清零。
    // 可接受的權衡：進程地址空間不共享，且憑證已存在於 REST 客戶端中。
    let (api_key, api_secret) = rest_client.credentials();
    let api_key = api_key.to_string();
    let api_secret = api_secret.to_string();
    let client_arc = Arc::new(rest_client);

    // DCP — Disconnected Cancel Protection / 斷連取消保護
    if cfg_snapshot.dcp_enabled {
        use openclaw_engine::platform_client::PlatformClient;
        let platform = PlatformClient::new(Arc::clone(&client_arc));
        match platform.set_dcp(cfg_snapshot.dcp_time_window).await {
            Ok(()) => {
                info!(kind = %kind, window = cfg_snapshot.dcp_time_window, "DCP enabled / DCP 已啟用")
            }
            Err(e) => {
                warn!(kind = %kind, error = %e, "DCP setup failed (non-fatal) / DCP 設定失敗")
            }
        }
    }

    // B-1 Phase 2: Always fetch existing positions at startup so paper_state can
    // be seeded with the exchange's view (before this fix, positions were only
    // queried when auto_add_margin was enabled, and even then only used for
    // /v5/position/set-auto-add-margin — never written into paper_state).
    // The captured snapshot is later forwarded via ExchangePipelineBindings.
    // B-1 Phase 2：啟動時無條件抓取現存持倉，讓 paper_state 可在首個市場 tick
    // 前對齊交易所側狀態（修復前只在 auto_add_margin 開啟時才抓，且只用於
    // 設定自動追保，從未寫進 paper_state）。
    // 抓到的快照之後透過 ExchangePipelineBindings 轉發給事件消費者。
    let mut seed_positions: Vec<(String, bool, f64, f64, u64)> = Vec::new();
    {
        use openclaw_engine::order_manager::OrderCategory;
        use openclaw_engine::position_manager::PositionManager;
        let pos_mgr = PositionManager::new(Arc::clone(&client_arc));
        match pos_mgr.get_positions(OrderCategory::Linear, None).await {
            Ok(positions) => {
                for pos in &positions {
                    if pos.size > 0.0 && pos.avg_price > 0.0 {
                        let is_long = pos.side.eq_ignore_ascii_case("Buy");
                        // Bybit updated_time is a millisecond string; fall back to 0 on parse failure.
                        // updated_time 為毫秒字串，解析失敗時退回 0。
                        let ts_ms: u64 = pos.updated_time.parse().unwrap_or(0);
                        seed_positions.push((
                            pos.symbol.clone(),
                            is_long,
                            pos.size,
                            pos.avg_price,
                            ts_ms,
                        ));
                        info!(
                            kind = %kind,
                            symbol = %pos.symbol,
                            side = %pos.side,
                            size = pos.size,
                            avg_price = pos.avg_price,
                            "startup position captured / 啟動時抓取既存持倉"
                        );
                    }
                }
                // Auto-add-margin (legacy behaviour, gated on config) — uses the
                // same fetch result so we don't double-call REST.
                // 自動追保（沿用舊行為，由 config 開關），重用同一次 REST 抓取結果。
                if cfg_snapshot.auto_add_margin {
                    for pos in &positions {
                        if pos.size > 0.0 {
                            match pos_mgr
                                .set_auto_add_margin(OrderCategory::Linear, &pos.symbol, 1, None)
                                .await
                            {
                                Ok(()) => info!(
                                    kind = %kind,
                                    symbol = %pos.symbol,
                                    "auto-margin enabled / 自動追保已啟用"
                                ),
                                Err(e) => warn!(
                                    kind = %kind,
                                    symbol = %pos.symbol,
                                    error = %e,
                                    "auto-margin failed / 自動追保失敗"
                                ),
                            }
                        }
                    }
                }
            }
            Err(e) => {
                warn!(
                    kind = %kind,
                    error = %e,
                    "startup position fetch failed (paper_state will start empty) \
                     / 啟動持倉抓取失敗（paper_state 將以空狀態啟動）"
                );
            }
        }
    }
    info!(
        kind = %kind,
        count = seed_positions.len(),
        "startup position seed prepared / 啟動持倉種子已準備"
    );

    // Fetch fee rates / 獲取費率
    let acct = Arc::new(AccountManager::new());
    let taker_fee = match acct.refresh_fee_rates(&*client_arc, "linear").await {
        Ok(count) => {
            let rate = acct.taker_fee("BTCUSDT");
            info!(kind = %kind, symbols = count, taker_rate = format!("{:.5}", rate), "fee rates loaded / 費率已加載");
            Some(rate)
        }
        Err(e) => {
            warn!(kind = %kind, error = %e, "fee rate fetch failed / 費率獲取失敗");
            None
        }
    };

    // BALANCE-REAL-1: Fetch initial balance with retry + hard-fail.
    // 3 attempts, exponential backoff 500ms / 1s / 2s. On final failure the
    // entire exchange pipeline refuses to start (build_exchange_pipeline
    // returns None) — demo/live MUST run on a real Bybit balance, never on a
    // hardcoded 10000 fallback. Paper is unaffected (paper_balance_from_*).
    // GUI consumes the missing pipeline as "N/A / 未連接".
    //
    // BALANCE-REAL-1：抓初始餘額帶 retry + 硬性失敗。
    // 3 次嘗試，指數退避 500ms / 1s / 2s。三次全失敗則整條交易所管線拒絕
    // 啟動（build_exchange_pipeline 返回 None）— demo/live 必須跑真實 Bybit
    // 餘額，絕不允許硬編碼 10000 fallback。Paper 不受影響。
    // GUI 把缺失的管線顯示為「N/A / 未連接」。
    const REST_BALANCE_RETRY_ATTEMPTS: u32 = 3;
    const REST_BALANCE_BACKOFF_MS: [u64; 3] = [500, 1000, 2000];
    let initial_balance = {
        let mut last_err: Option<String> = None;
        let mut got_balance: Option<f64> = None;
        for attempt in 1..=REST_BALANCE_RETRY_ATTEMPTS {
            match acct.refresh_balance(&*client_arc).await {
                Ok(_) => {
                    let bal = acct.usdt_wallet_balance();
                    if bal > 0.0 {
                        info!(
                            kind = %kind,
                            attempt,
                            balance = format!("{:.2}", bal),
                            "exchange balance fetched / 交易所餘額已獲取"
                        );
                        got_balance = Some(bal);
                        break;
                    } else {
                        last_err = Some("wallet returned 0 / 錢包返回 0".into());
                        warn!(
                            kind = %kind,
                            attempt,
                            "exchange balance is 0 / 交易所餘額為 0"
                        );
                    }
                }
                Err(e) => {
                    last_err = Some(e.to_string());
                    warn!(
                        kind = %kind,
                        attempt,
                        error = %e,
                        "exchange balance fetch attempt failed / 交易所餘額抓取嘗試失敗"
                    );
                }
            }
            if attempt < REST_BALANCE_RETRY_ATTEMPTS {
                let backoff = REST_BALANCE_BACKOFF_MS[(attempt - 1) as usize];
                tokio::time::sleep(std::time::Duration::from_millis(backoff)).await;
            }
        }
        match got_balance {
            Some(b) => b,
            None => {
                error!(
                    kind = %kind,
                    attempts = REST_BALANCE_RETRY_ATTEMPTS,
                    last_error = ?last_err,
                    "REST wallet-balance failed after all retries — pipeline REFUSES to start. \
                     No 10000 fallback. Operator: check network / API key / Bybit endpoint. \
                     / REST 餘額抓取多次失敗 — 該管線拒絕啟動。\
                     不再使用 10000 默認值。請檢查網路/API key/Bybit 端點。"
                );
                return None;
            }
        }
    };

    // Spawn Private WS supervisor (D21: per-engine isolation) / 啟動私有 WS 監管器
    //
    // PIPELINE-SLOT-1 Phase 2: `spawn_private_ws_supervisor` now returns the
    // two tokio JoinHandles it spawns (ws supervisor + listener) so we can
    // hand them back to the slot alongside the balance-refresh handle below.
    // PIPELINE-SLOT-1 Phase 2：`spawn_private_ws_supervisor` 現在回傳它 spawn
    // 的兩個 tokio JoinHandle（WS supervisor + listener），連同下面的
    // balance-refresh handle 一併交還給 slot。
    let label = match env {
        BybitEnvironment::Demo | BybitEnvironment::Testnet => "demo",
        BybitEnvironment::Mainnet | BybitEnvironment::LiveDemo => "live",
    };
    let (ws_bindings, mut task_handles) =
        spawn_private_ws_supervisor(api_key, api_secret, env, label, cancel.clone());

    // BALANCE-REAL-1: Seed reconcile Arc with the REST-fetched value so the
    // event_consumer reconcile path triggers from the very first tick — we do
    // not wait for the WS wallet topic (idle demo accounts may never push).
    // BALANCE-REAL-1：用 REST 抓到的值初始化對賬 Arc，event_consumer 對賬路徑
    // 從首個 tick 起即生效，不依賴 WS wallet topic 主動推送
    // （閒置 demo 帳戶可能永遠不推）。
    *ws_bindings.bybit_balance.write() = Some(initial_balance);

    // BALANCE-REAL-1: Spawn periodic REST balance refresh (5min).
    // Defends against silent WS — keeps `bybit_balance` Arc fresh so
    // event_consumer reconcile_balance_from_exchange always sees a recent
    // exchange-side number, not stale local-simulated drift.
    // BALANCE-REAL-1：啟動定期 REST 餘額對賬（5 分鐘）。
    // 防 WS 靜默 — 保持 `bybit_balance` Arc 新鮮，
    // event_consumer reconcile_balance_from_exchange 始終看到最新交易所側值。
    {
        let refresh_acct = Arc::clone(&acct);
        let refresh_client = Arc::clone(&client_arc);
        let refresh_arc = Arc::clone(&ws_bindings.bybit_balance);
        let refresh_cancel = cancel.clone();
        let refresh_kind = kind;
        // PIPELINE-SLOT-1 Phase 2: capture the balance-refresh handle so the
        // slot teardown awaits it instead of orphaning a detached task. Pre-
        // Phase-2 this was `tokio::spawn(...)` with the handle discarded —
        // harmless while engine-wide cancel always killed it, but not safe
        // once we can cancel the slot's child token independently.
        // PIPELINE-SLOT-1 Phase 2：捕獲 balance-refresh handle，避免 slot
        // teardown 時殘留 detached task。Phase 2 前這裡是 `tokio::spawn(...)`
        // 丟棄 handle — 引擎級 cancel 永遠會 kill 時無害，但能獨立 cancel
        // 子 token 後就不安全。
        let refresh_handle = tokio::spawn(async move {
            let mut interval = tokio::time::interval(std::time::Duration::from_secs(300));
            interval.tick().await; // skip first immediate tick
            loop {
                tokio::select! {
                    _ = refresh_cancel.cancelled() => {
                        debug!(kind = %refresh_kind, "periodic balance refresh task cancelled / 定期餘額對賬任務取消");
                        break;
                    }
                    _ = interval.tick() => {
                        match refresh_acct.refresh_balance(&*refresh_client).await {
                            Ok(_) => {
                                let bal = refresh_acct.usdt_wallet_balance();
                                if bal > 0.0 {
                                    *refresh_arc.write() = Some(bal);
                                    debug!(
                                        kind = %refresh_kind,
                                        balance = format!("{:.2}", bal),
                                        "periodic REST balance refresh / 定期 REST 餘額對賬"
                                    );
                                } else {
                                    warn!(
                                        kind = %refresh_kind,
                                        "periodic REST balance returned 0 — keeping previous value / 定期 REST 餘額返回 0，保留舊值"
                                    );
                                }
                            }
                            Err(e) => warn!(
                                kind = %refresh_kind,
                                error = %e,
                                "periodic REST balance refresh failed / 定期 REST 餘額對賬失敗"
                            ),
                        }
                    }
                }
            }
        });
        task_handles.push(refresh_handle);
    }

    let risk_level = Arc::new(std::sync::atomic::AtomicU8::new(
        openclaw_core::sm::risk_gov::RiskLevel::Normal.value(),
    ));
    let health = Arc::new(std::sync::atomic::AtomicU8::new(
        openclaw_engine::tick_pipeline::PipelineHealth::Running as u8,
    ));

    info!(kind = %kind, env = ?env, balance = format!("{:.2}", initial_balance),
        "exchange pipeline bindings built / 交易所管線綁定已構建");

    Some((
        ExchangePipelineBindings {
            env,
            rest_client: client_arc,
            account_manager: acct,
            taker_fee,
            initial_balance,
            ws_bindings,
            risk_level,
            health,
            seed_positions,
        },
        task_handles,
    ))
}

/// Exchange bindings produced by spawning a private WS supervisor.
/// 啟動私有 WS 監管器後產生的交易所綁定。
///
/// PIPELINE-SLOT-1 Phase 2:
///   The `_ws_handle` and `_listener_handle` fields that previously lived here
///   (prefixed `_` → kept alive only to prevent task drop) are now returned
///   separately by `spawn_private_ws_supervisor` so `build_exchange_pipeline`
///   can bundle them into a `Vec<JoinHandle<()>>` owned by the slot. This
///   lets `PipelineSlot::teardown()` await them deterministically on
///   live-scoped teardown. No runtime behaviour change on the happy path —
///   the handles are still tokio-spawned on the same runtime with the same
///   cancel-token wiring; we just own them at a different layer now.
///
/// PIPELINE-SLOT-1 Phase 2：
///   原本放在這裡的 `_ws_handle` 與 `_listener_handle`（以 `_` 前綴僅為防
///   drop）已改由 `spawn_private_ws_supervisor` 另外返回，讓
///   `build_exchange_pipeline` 可以把它們匯入一個歸槽位擁有的
///   `Vec<JoinHandle<()>>`，使 `PipelineSlot::teardown()` 能在 live-scoped
///   teardown 時確定性地 await。Happy path 無行為變動 — 任務仍在同個 runtime
///   spawn、cancel-token 接線一致，只是擁有權提高到 slot 層。
pub(crate) struct PrivateWsBindings {
    // BLOCKER-6 / D12: parking_lot::RwLock for non-poisoning cross-pipeline isolation.
    // BLOCKER-6 / D12：parking_lot::RwLock，不中毒 → 跨管線隔離。
    pub bybit_balance: Arc<parking_lot::RwLock<Option<f64>>>,
    pub api_pnl: Arc<parking_lot::RwLock<std::collections::HashMap<String, f64>>>,
    pub exchange_event_rx: mpsc::UnboundedReceiver<ExchangeEvent>,
}

/// Spawn a per-pipeline private WS supervisor + ExecutionListener.
/// Returns exchange bindings for the pipeline's EventConsumerDeps plus the
/// two tokio task handles (ws supervisor + listener), so the caller can
/// hand them to `PipelineSlot` for deterministic teardown.
///
/// 為每管線啟動私有 WS 監管器 + 執行監聽器。
/// 返回管線 EventConsumerDeps 所需的交易所綁定，以及 ws supervisor 與
/// listener 的 tokio 任務 handle，方便呼叫者交給 `PipelineSlot` 以確定性地
/// 撤下。
pub(crate) fn spawn_private_ws_supervisor(
    api_key: String,
    api_secret: String,
    env: BybitEnvironment,
    label: &str,
    cancel: CancellationToken,
) -> (PrivateWsBindings, Vec<JoinHandle<()>>) {
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

    // on_position_update → track API unrealized PnL + forward delta to event consumer.
    // 持倉更新回調：更新 api_pnl 的同時把 delta 也轉發給事件消費者，
    // 讓 paper_state.upsert_position_from_exchange() 能與交易所側保持一致。
    let pnl_ref = Arc::clone(&api_pnl);
    let lbl_pos = label.to_string();
    let pos_tx = exchange_event_tx.clone();
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
        // B-1 Phase 2: forward to event consumer for paper_state upsert.
        // Channel send is best-effort — drop on backpressure rather than block the WS thread.
        // B-1 Phase 2：轉發給事件消費者以便 upsert paper_state。
        // 通道發送為盡力而為，背壓時直接丟棄以免阻塞 WS 執行緒。
        let _ = pos_tx.send(ExchangeEvent::PositionUpdate(pos));
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

    // C-WIRING: extract stats Arc BEFORE listener is moved into its spawn, so
    // the status-JSON writer can read live counters.
    // 取 stats Arc（必須在 listener 被 spawn 搬走前完成）以供 status JSON writer 使用。
    let stats_arc = listener.stats_arc();

    // Spawn listener task / 啟動監聽器任務
    let listener_handle = tokio::spawn(async move {
        let mut listener = listener;
        listener.run().await;
    });

    // C-WIRING: spawn status-JSON writer to replace the Python
    // `bybit_private_ws_listener.py` that previously produced the
    // `bybit_private_ws_listener_status_latest.json` file consumed by
    // `readonly_observer_pipeline/{build_ws_runtime_facts,runtime_state_
    // resolver,observer_acceptance_check}.py`. Only for Demo / LiveDemo to
    // match the Python listener's scope (it ran against a demo API key;
    // Paper has no real private WS and Mainnet live isn't active yet).
    //
    // 啟動 status JSON writer 取代 Python listener；僅對 Demo/LiveDemo 啟動以
    // 對齊 Python 原本的 scope（paper 無真實私有 WS；Mainnet live 尚未啟用）。
    let status_writer_handle: Option<JoinHandle<()>> =
        if matches!(env, BybitEnvironment::Demo | BybitEnvironment::LiveDemo) {
            use openclaw_engine::bybit_private_ws_status_writer::{
                run_private_ws_status_writer, WriterConfig,
            };
            let ws_url = env.private_ws_url().to_string();
            let topics: Vec<String> = env
                .private_ws_topics()
                .iter()
                .map(|s| (*s).to_string())
                .collect();
            let cfg = WriterConfig::from_env(label.to_string(), ws_url, topics);
            let stats_for_writer = Arc::clone(&stats_arc);
            let cancel_for_writer = cancel.clone();
            let handle = tokio::spawn(async move {
                run_private_ws_status_writer(stats_for_writer, cfg, cancel_for_writer).await;
            });
            info!(
                engine = label,
                "Private WS status-JSON writer spawned / 私有 WS status JSON writer 已啟動"
            );
            Some(handle)
        } else {
            None
        };

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

    info!(
        engine = label,
        "Private WS + ExecutionListener started / 私有 WS + 執行監聽器已啟動"
    );
    let bindings = PrivateWsBindings {
        bybit_balance,
        api_pnl,
        exchange_event_rx,
    };
    // Order here is intentional but not semantically required (teardown awaits
    // all in sequence). Keep [ws_handle, listener_handle, status_writer?] so
    // logs during teardown report the supervisor shutting down first, then
    // the listener, then the writer (the writer's final running=false write
    // uses the stale stats but that's fine — it just means observers see
    // the terminal state).
    // 順序有意為之但不影響語義（teardown 會依序 await 全部）。保留
    // [ws_handle, listener_handle, status_writer?]，teardown log 先打
    // supervisor → listener → writer；writer 的最後 running=false 寫入使用最新
    // stats 快照，observer 會看到終止狀態。
    let mut handles = vec![ws_handle, listener_handle];
    if let Some(h) = status_writer_handle {
        handles.push(h);
    }
    (bindings, handles)
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

/// PIPELINE-SLOT-1 Phase 1: resolve the `settings/` directory using the same
/// convention as `paper_balance_from_toml` — `OPENCLAW_BASE_DIR/settings`,
/// falling back to `./settings` when the env var is unset. Cross-platform:
/// `PathBuf` handles separators correctly on macOS / Linux.
///
/// PIPELINE-SLOT-1 Phase 1：用與 `paper_balance_from_toml` 同一套約定解析
/// `settings/` 目錄 — 優先 `OPENCLAW_BASE_DIR/settings`，env var 未設時
/// 回退 `./settings`。跨平台（macOS / Linux）。
pub(crate) fn resolve_settings_dir() -> PathBuf {
    let base = std::env::var("OPENCLAW_BASE_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("."));
    base.join("settings")
}

/// PIPELINE-SLOT-1 Phase 1: resolve the Bybit `live/` secret slot path using
/// the same rule as `live_authorization::authorization_path` — prefer
/// `OPENCLAW_SECRETS_DIR`, fall back to `$HOME/BybitOpenClaw/secrets/secret_files/bybit`.
/// Returns None if neither env var nor HOME is available (rare — platform
/// without a user profile).
///
/// PIPELINE-SLOT-1 Phase 1：以 `live_authorization::authorization_path` 相同
/// 規則解析 Bybit `live/` secret slot 路徑 — 優先 `OPENCLAW_SECRETS_DIR`，
/// 否則 `$HOME/BybitOpenClaw/secrets/secret_files/bybit`。兩者皆無回傳 None。
pub(crate) fn resolve_live_secret_slot() -> Option<PathBuf> {
    let base = if let Ok(dir) = std::env::var("OPENCLAW_SECRETS_DIR") {
        PathBuf::from(dir)
    } else {
        let home = std::env::var("HOME")
            .or_else(|_| std::env::var("USERPROFILE"))
            .ok()?;
        PathBuf::from(home)
            .join("BybitOpenClaw")
            .join("secrets")
            .join("secret_files")
            .join("bybit")
    };
    Some(base.join("live"))
}

/// PIPELINE-SLOT-1 Phase 1: detect the sentinel written by `restart_all.sh`
/// and, on Manual restart, clear `authorization.json` so the Live pipeline
/// is forced to re-acquire operator approval on every code/config push.
///
/// Rationale: `restart_all.sh` is the operator-intent path — code changes,
/// config edits, or a deliberate bounce. Forcing re-auth here closes a
/// subtle window where an operator could push a security-relevant engine
/// change without re-consenting to Live. Crashes / watchdog bounces /
/// systemd auto-restarts do NOT run the script and therefore do NOT clear
/// the authorization — that is the correct behaviour: the engine should
/// come back on an already-approved session if it simply died.
///
/// The whole flow is best-effort: if the sentinel is unreadable, the file
/// cannot be removed, or HOME is unresolvable, we log and continue. Startup
/// MUST not be blocked by any of these.
///
/// PIPELINE-SLOT-1 Phase 1：偵測 `restart_all.sh` 寫的 sentinel，Manual 重啟
/// 時清空 `authorization.json`，強迫 Live 管線每次 code/config 推送後重新
/// 取得 operator 批准。
///
/// 理由：`restart_all.sh` = operator 意圖（改碼、改 config、主動重啟）。此處
/// 強迫 re-auth 關閉了「operator 推送安全相關改動卻不重新授權」的細微窗口。
/// 崩潰 / watchdog 拉起 / systemd 自動重啟**不**跑 shell，也**不**清授權 —
/// 這是正確行為：引擎只是死了一下，應該回到已批准 session。
///
/// 整個流程 best-effort：sentinel 讀不到、檔案刪不掉、HOME 解不到，都只
/// log 不阻塞啟動。
pub(crate) fn consume_restart_sentinel_and_clear_live_auth_if_manual() -> RestartKind {
    let settings_dir = resolve_settings_dir();
    let kind = restart_kind::detect_and_consume(&settings_dir);
    tracing::info!(
        kind = ?kind,
        settings_dir = %settings_dir.display(),
        "startup: restart kind detected / 偵測重啟類型"
    );

    if matches!(kind, RestartKind::Manual) {
        match resolve_live_secret_slot() {
            Some(live_dir) => {
                let auth_path = live_dir.join(AUTHORIZATION_FILENAME);
                match std::fs::remove_file(&auth_path) {
                    Ok(_) => tracing::info!(
                        path = %auth_path.display(),
                        "manual restart: cleared authorization.json — operator must renew via GUI \
                         / 手動重啟：已清空 authorization.json，operator 須經 GUI 重新批准"
                    ),
                    Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                        tracing::info!(
                            path = %auth_path.display(),
                            "manual restart: authorization.json already absent (nothing to clear) \
                             / 手動重啟：authorization.json 本就不存在"
                        );
                    }
                    Err(e) => tracing::warn!(
                        path = %auth_path.display(),
                        error = %e,
                        "manual restart: failed to clear authorization.json (continuing) \
                         / 手動重啟：清空 authorization.json 失敗（繼續啟動）"
                    ),
                }
            }
            None => {
                tracing::warn!(
                    "manual restart: cannot resolve live secret slot — neither \
                     OPENCLAW_SECRETS_DIR nor HOME/USERPROFILE set \
                     / 手動重啟：無法解析 live secret slot（env var 都未設）"
                );
            }
        }
    }

    kind
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

// ── FIX-16: startup.rs tests ──
#[cfg(test)]
mod tests {
    use super::*;

    /// FIX-16b: Verify VERSION is valid semver (not just non-empty).
    /// 驗證 VERSION 符合語義版本格式。
    #[test]
    fn test_version_is_valid_semver() {
        let parts: Vec<&str> = VERSION.split('.').collect();
        assert!(
            parts.len() >= 2,
            "VERSION must have at least major.minor: {VERSION}"
        );
        for (i, part) in parts.iter().take(3).enumerate() {
            // Strip any pre-release suffix from the last part (e.g., "3-rc1")
            let numeric = part.split('-').next().unwrap();
            assert!(
                numeric.parse::<u32>().is_ok(),
                "VERSION part {i} must be numeric, got '{part}' in {VERSION}"
            );
        }
    }

    /// FIX-16b: Verify paper_balance_from_env parses valid values and rejects invalid ones.
    /// 驗證 env 解析：有效數字→Some / 無效→None / 負數→None / 零→None。
    #[test]
    fn test_paper_balance_from_env_valid_and_invalid() {
        let prev = std::env::var("OPENCLAW_PAPER_BALANCE").ok();

        // Valid
        std::env::set_var("OPENCLAW_PAPER_BALANCE", "5000.0");
        assert_eq!(paper_balance_from_env(), Some(5000.0));

        // Invalid string
        std::env::set_var("OPENCLAW_PAPER_BALANCE", "not_a_number");
        assert_eq!(paper_balance_from_env(), None);

        // Negative (filter b > 0.0)
        std::env::set_var("OPENCLAW_PAPER_BALANCE", "-100.0");
        assert_eq!(paper_balance_from_env(), None);

        // Zero (filter b > 0.0)
        std::env::set_var("OPENCLAW_PAPER_BALANCE", "0.0");
        assert_eq!(paper_balance_from_env(), None);

        // Restore
        if let Some(v) = prev {
            std::env::set_var("OPENCLAW_PAPER_BALANCE", v);
        } else {
            std::env::remove_var("OPENCLAW_PAPER_BALANCE");
        }
    }

    /// FIX-16: paper_balance_from_env returns None when env var absent.
    /// 環境變量不存在時返回 None。
    #[test]
    fn test_paper_balance_from_env_missing() {
        // Temporarily remove the env var if set
        let prev = std::env::var("OPENCLAW_PAPER_BALANCE").ok();
        std::env::remove_var("OPENCLAW_PAPER_BALANCE");
        assert!(paper_balance_from_env().is_none());
        // Restore
        if let Some(v) = prev {
            std::env::set_var("OPENCLAW_PAPER_BALANCE", v);
        }
    }

    /// FIX-16: paper_balance_from_toml returns None when file missing.
    /// TOML 文件缺失時返回 None（不 panic）。
    #[test]
    fn test_paper_balance_from_toml_missing_file() {
        let prev = std::env::var("OPENCLAW_BASE_DIR").ok();
        std::env::set_var("OPENCLAW_BASE_DIR", "/tmp/openclaw_nonexistent_test_dir");
        assert!(paper_balance_from_toml().is_none());
        if let Some(v) = prev {
            std::env::set_var("OPENCLAW_BASE_DIR", v);
        } else {
            std::env::remove_var("OPENCLAW_BASE_DIR");
        }
    }

    /// FIX-16: load_unified_configs succeeds with default TOML fallbacks.
    /// 使用默認 TOML 回退時 load_unified_configs 不 panic。
    #[test]
    fn test_load_unified_configs_defaults() {
        // Point to a non-existent directory so all configs fall back to defaults.
        let prev = std::env::var("OPENCLAW_RISK_CONFIG_DIR").ok();
        std::env::set_var("OPENCLAW_RISK_CONFIG_DIR", "/tmp/openclaw_nodir_test");
        let result = load_unified_configs();
        assert!(
            result.is_ok(),
            "load_unified_configs must succeed with defaults: {:?}",
            result.err()
        );
        let (risk_stores, learning_store, budget_store) = result.unwrap();
        // All stores should have version 0 (initial load)
        assert!(risk_stores.paper.version() <= 1);
        assert!(risk_stores.demo.version() <= 1);
        assert!(risk_stores.live.version() <= 1);
        assert!(learning_store.version() <= 1);
        assert!(budget_store.version() <= 1);
        // Restore
        if let Some(v) = prev {
            std::env::set_var("OPENCLAW_RISK_CONFIG_DIR", v);
        } else {
            std::env::remove_var("OPENCLAW_RISK_CONFIG_DIR");
        }
    }
}
