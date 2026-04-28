//! Scanner D4 boot-time pre-init (extracted from main.rs).
//! 掃描器 D4 啟動期前置初始化（從 main.rs 抽出）。
//!
//! MODULE_NOTE (EN): Sibling module to `main_boot_tasks` / `main_pipelines`
//!   etc. Holds the scanner pre-init block that previously lived inline at
//!   the top of `async_main`:
//!     1. Resolve `scanner_config.toml` path (env-overridable).
//!     2. Load + validate ``ScannerConfig`` (fail-soft → defaults on err).
//!     3. Construct ``ConfigStore<ScannerConfig>`` with TOML persist.
//!     4. Build ``SymbolRegistry`` seeded with pinned symbols.
//!     5. Load per-symbol ``EdgeEstimates`` for scanner scorer.
//!     6. Set up the persistent ScannerRunner→WsClient relay channel +
//!        spawn a tokio relay task that forwards topic changes to the
//!        current WsClient sender (rotated on each WS supervisor restart).
//!
//!   Pure refactor — 0 production behavior change. Splits to bring `main.rs`
//!   under §九 1200-line hard cap (1210 → ~1153) per MAIN-RS-PRE-EXISTING-
//!   CLEANUP P2 (E2 PB1 retroactive review of Wave E `cost_edge_advisor_boot`
//!   split). Sibling-module pattern (NOT `scanner::boot`) keeps the scanner
//!   library crate free of boot-time tokio spawn deps.
//!
//! MODULE_NOTE (中): `main_boot_tasks` / `main_pipelines` 等的 sibling 模組。
//!   原本內嵌於 `async_main` 頂端的 scanner 前置初始化區塊：
//!     1. 解析 `scanner_config.toml` 路徑（可由 env 覆寫）。
//!     2. 載入 + 驗證 ``ScannerConfig``（fail-soft，錯誤→預設）。
//!     3. 構建 ``ConfigStore<ScannerConfig>``（含 TOML persist）。
//!     4. 以 pinned symbols 為種子構建 ``SymbolRegistry``。
//!     5. 載入 per-symbol ``EdgeEstimates`` 供 scanner scorer。
//!     6. 設置 ScannerRunner→WsClient 持久 relay 通道 + spawn tokio relay
//!        task，將 topic 變更轉發到當前 WsClient sender（WS supervisor 每次
//!        重啟時輪替）。
//!
//!   純 location refactor — 0 production behavior 變化。為將 `main.rs` 壓在
//!   §九 1200 行硬上限以下（1210 → ~1153），執行 MAIN-RS-PRE-EXISTING-
//!   CLEANUP P2（針對 Wave E `cost_edge_advisor_boot` split 的 E2 PB1
//!   retroactive review）。Sibling 模組 pattern（**不**放 `scanner::boot`）
//!   讓 scanner library crate 不沾啟動期 tokio spawn 依賴。

use openclaw_engine::config::{load_toml_or_default, ConfigStore};
use openclaw_engine::scanner::registry::SymbolRegistry;
use openclaw_engine::scanner::ScannerConfig;
use parking_lot::RwLock as ParkingRwLock;
use std::sync::Arc;
use tracing::{info, warn};

/// Bundle returned by `init_scanner` to the caller in `main.rs::async_main`.
/// `init_scanner` 回傳給 `main.rs::async_main` 的 bundle。
///
/// EN: All four fields are required downstream — `scanner_store` for IPC
///   set_scanner_registry + ScannerRunner construction; `symbol_registry`
///   for ScannerRunner + position reconcilers + WS supervisor;
///   `edge_estimates` for ScannerRunner scorer + position reconcilers;
///   `ws_topic_change_tx` is fed to ScannerRunner so it can request topic
///   subscribe/unsubscribe via the relay task spawned inside this fn;
///   `current_ws_client_tx` is the relay slot that the WS supervisor
///   writes its current sender into on every restart.
///
/// 中：四個欄位下游都必需 — `scanner_store` 給 IPC set_scanner_registry +
///   ScannerRunner 構建；`symbol_registry` 給 ScannerRunner + position
///   reconciler + WS supervisor；`edge_estimates` 給 ScannerRunner scorer +
///   position reconciler；`ws_topic_change_tx` 餵給 ScannerRunner 用於請求
///   topic 訂閱/取消（轉發由本 fn spawn 的 relay task 完成）；
///   `current_ws_client_tx` 是 relay slot，WS supervisor 每次重啟把當前
///   sender 寫入此 slot。
pub(crate) struct ScannerInitBundle {
    pub scanner_store: Arc<ConfigStore<ScannerConfig>>,
    pub symbol_registry: Arc<SymbolRegistry>,
    pub edge_estimates: Arc<ParkingRwLock<openclaw_engine::edge_estimates::EdgeEstimates>>,
    pub ws_topic_change_tx:
        tokio::sync::mpsc::UnboundedSender<openclaw_engine::ws_client::WsTopicChange>,
    pub current_ws_client_tx: Arc<
        tokio::sync::Mutex<
            Option<tokio::sync::mpsc::UnboundedSender<openclaw_engine::ws_client::WsTopicChange>>,
        >,
    >,
}

/// Run the scanner pre-init block + spawn the persistent relay task.
/// 執行 scanner 前置初始化 + spawn 持久 relay task。
///
/// EN: Must be called inside the tokio runtime (relay task uses `tokio::spawn`).
///   Fail-soft: scanner config load errors fall back to ``ScannerConfig::default()``
///   so engine startup never blocks on a malformed scanner_config.toml.
///   Edge estimates load is also fail-soft (returns empty estimates on error,
///   handled inside ``EdgeEstimates::load_from_env_or_default``).
///
/// 中：必須在 tokio runtime 內呼叫（relay task 用 `tokio::spawn`）。
///   Fail-soft：scanner config 載入失敗 → fallback 到 ``ScannerConfig::default()``，
///   引擎啟動絕不會被壞掉的 scanner_config.toml 阻塞。Edge estimates 載入也是
///   fail-soft（錯誤 → 空 estimates，由 ``EdgeEstimates::load_from_env_or_default``
///   內部處理）。
pub(crate) fn init_scanner() -> ScannerInitBundle {
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

    // Scanner D4: Load EdgeEstimates for scanner scorer.
    // 掃描器 D4：為掃描器評分器加載邊際估計。
    let scanner_edge_estimates = {
        let base = std::env::var("OPENCLAW_BASE_DIR")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|_| std::path::PathBuf::from("."));
        let estimates =
            openclaw_engine::edge_estimates::EdgeEstimates::load_from_env_or_default(&base);
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
                    tracing::debug!("[scanner relay] WsClient not ready — topic change dropped, will retry on next scan");
                }
            }
        });
    }

    ScannerInitBundle {
        scanner_store,
        symbol_registry,
        edge_estimates: scanner_edge_estimates,
        ws_topic_change_tx: scanner_ws_tx,
        current_ws_client_tx,
    }
}
