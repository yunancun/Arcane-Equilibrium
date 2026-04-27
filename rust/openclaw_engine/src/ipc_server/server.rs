//! `IpcServer` struct + constructor + late-injection setters + `run()` accept
//! loop. The Unix-socket listen / per-connection spawn lives here; per-line
//! dispatch is in `dispatch.rs` and the per-connection auth handshake is in
//! `connection.rs`.
//! `IpcServer` 結構 + 建構式 + 延後注入 setter + `run()` accept 迴圈。
//! Unix socket listen / 每連線 spawn 在此檔；每行分派在 `dispatch.rs`，
//! 每連線認證握手在 `connection.rs`。
//!
//! MODULE_NOTE (EN): The IpcServer is constructed early in `main.rs` (before
//!   the DB pool, BudgetTracker, Teacher loop, audit pool, scanner registry,
//!   StrategistScheduler, or Live auth watcher exist) and the `*_slot()` /
//!   `set_*` setters are used to wire those subsystems in once they become
//!   available — see the docstrings on `slots.rs` for the rationale. The
//!   `run()` loop binds the configured Unix socket, applies 0o600
//!   permissions (I-02), and spawns one tokio task per accepted connection.
//!   Each task reads (cheap Arc clone) snapshots of every slot at connection
//!   time, so late-injected handles become visible to subsequent connections
//!   without an IPC restart.
//! MODULE_NOTE (中)：IpcServer 在 `main.rs` 早期就構造（早於 DB 池、
//!   BudgetTracker、Teacher loop、audit pool、scanner registry、
//!   StrategistScheduler、Live auth watcher），透過 `*_slot()` /
//!   `set_*` setter 在子系統就緒後接線 — 詳見 `slots.rs` docstring。
//!   `run()` 迴圈綁定設定中的 Unix socket、套 0o600 權限（I-02），
//!   為每個 accept 的連線 spawn 一個 tokio task。每個 task 在連線時讀取
//!   各 slot 的便宜 Arc clone 快照，所以延後注入的 handle 對後續連線可見，
//!   不需要重啟 IPC。
//!
//! Split out of `ipc_server/mod.rs` as part of G5-FUP-IPC-MOD-SPLIT (2026-04-26).
//! 於 G5-FUP-IPC-MOD-SPLIT（2026-04-26）從 `ipc_server/mod.rs` 拆出。

use super::connection::handle_connection;
use super::engine_routing::{EngineCommandChannels, LiveCmdSenderSlot};
use super::protocol::IpcError;
use super::slots::{
    AuditPoolSlot, BudgetTrackerSlot, CostEdgeAdvisorSlot, EdgeReloadSenderSlot, HStateCacheSlot,
    StrategistCountersSlot, TeacherLoopSlot,
};
use super::PerEngineRiskStores;
use crate::config::{BudgetConfig, ConfigManager, ConfigStore, LearningConfig};
use crate::h_state_cache::poller::InvalidationSender;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use tokio::net::UnixListener;
use tokio::sync::RwLock;
use tokio_util::sync::CancellationToken;
use tracing::{error, info, warn};

/// Unix domain socket IPC server.
/// Unix 域套接字 IPC 服務器。
pub struct IpcServer {
    config: Arc<ConfigManager>,
    cancel: CancellationToken,
    /// Data directory for reading pipeline snapshot files (R06-A).
    /// 數據目錄，用於讀取管線快照文件。
    data_dir: Arc<PathBuf>,
    /// 3E-3: Per-pipeline command channels — routes commands to Paper/Demo/Live pipelines.
    /// 3E-3：每管線命令通道 — 將命令路由到 Paper/Demo/Live 管線。
    cmd_channels: EngineCommandChannels,
    /// Phase 4 (4-15): Late-injected AI BudgetTracker slot.
    /// Phase 4 (4-15)：延後注入的 AI BudgetTracker 槽位。
    budget_tracker: BudgetTrackerSlot,
    /// Phase 4.1: Late-injected Teacher consumer loop handles.
    /// Phase 4.1：延後注入的 Teacher consumer loop 句柄。
    teacher_loop: TeacherLoopSlot,
    /// ARCH-RC1 1C-2-C / LIVE-P2-1: per-engine RiskConfig stores + unified Config stores.
    /// ARCH-RC1 1C-2-C / LIVE-P2-1：每引擎 RiskConfig stores + 統一 Config stores。
    risk_stores: Option<PerEngineRiskStores>,
    learning_store: Option<Arc<ConfigStore<LearningConfig>>>,
    budget_store: Option<Arc<ConfigStore<BudgetConfig>>>,
    /// ARCH-RC1 1C-2-E: late-injected slot for the V014 audit pool.
    /// ARCH-RC1 1C-2-E：V014 審計 pool 延後注入槽位。
    audit_pool: AuditPoolSlot,
    /// Scanner IPC: SymbolRegistry for get_active_symbols / get_scanner_status.
    /// 掃描器 IPC：SymbolRegistry 供 get_active_symbols / get_scanner_status 使用。
    scanner_registry: Option<Arc<crate::scanner::registry::SymbolRegistry>>,
    /// G3-11 STRATEGIST-CYCLE-OBSERVABILITY-1 (2026-04-25): shared
    /// late-injected `CycleCounters` slot from `StrategistScheduler`.
    /// IPC server detaches before scheduler spawn → must be a slot type so
    /// `main.rs` can write the counters Arc post-detach via
    /// `IpcServer::strategist_counters_slot()`.
    /// G3-11：scheduler `CycleCounters` slot；IPC server detach 後由 main.rs 寫入。
    strategist_counters: StrategistCountersSlot,
    /// PIPELINE-SLOT-1 Phase 3: fast-path wake-up to the Live auth watcher.
    /// Set in main.rs via [`IpcServer::set_live_auth_recheck_sender`] after
    /// `LiveAuthWatcher::new` returns its trigger handle. `None` when the
    /// engine is running without a Live pipeline (paper/demo-only build).
    ///
    /// PIPELINE-SLOT-1 Phase 3：Live 授權 watcher 的快路徑喚醒端。於
    /// main.rs `LiveAuthWatcher::new` 回傳 handle 後透過
    /// [`IpcServer::set_live_auth_recheck_sender`] 設定。無 Live 管線時
    /// 為 `None`。
    live_auth_recheck_tx: Option<tokio::sync::mpsc::Sender<()>>,
    /// G3-08 H State Gateway Phase 1 (2026-04-26): late-injected slot for
    /// the Rust-side cache of Python H1-H5 + 5-Agent state. Stays None
    /// when `OPENCLAW_H_STATE_GATEWAY=1` is not set (DEFAULT-OFF).
    /// G3-08 H State Gateway Phase 1：Python H1-H5 + 5-Agent state 的
    /// Rust 端 cache slot。`OPENCLAW_H_STATE_GATEWAY=1` 未設時保持 None
    /// （DEFAULT-OFF）。
    h_state_cache: HStateCacheSlot,
    /// G3-08 H State Gateway Phase 1: invalidation channel sender. Set by
    /// main_boot_tasks at the same time the cache + poller are spawned;
    /// stays None when env-gate is off.
    /// G3-08 H State Gateway Phase 1：invalidation channel sender。在
    /// main_boot_tasks spawn cache + poller 時一起 set；env-gate 關時為 None。
    h_state_invalidation_tx: Option<InvalidationSender>,
    /// F6 PH5-WIRE-1 RELOAD (2026-04-26): late-injected slot for edge
    /// estimates reloader's manual-trigger sender. Stays None when reloader
    /// daemon is not spawned (env=0 or no pipelines bound). The
    /// `reload_edge_estimates` IPC handler reads this slot per connection
    /// and reports `reloader_disabled` when None, otherwise advisory
    /// `try_send` shape (`accepted` / `coalesced` / `reloader_closed`).
    /// F6 PH5-WIRE-1 RELOAD：edge 重載 daemon manual trigger sender 延後
    /// 注入 slot。daemon 未 spawn 時保持 None；IPC handler 讀此 slot，
    /// None 時回 `reloader_disabled`，否則走 `try_send` advisory shape。
    edge_reload_sender: EdgeReloadSenderSlot,
    /// G3-09 Phase A (2026-04-27): late-injected slot for the cost_edge_advisor
    /// `Arc<CostEdgeAdvisor>`. Stays None when env-gate
    /// `OPENCLAW_COST_EDGE_ADVISOR=1` is not set (DEFAULT-OFF).
    /// G3-09 Phase A：cost_edge_advisor slot；env-gate 未設時保持 None。
    cost_edge_advisor: CostEdgeAdvisorSlot,
}

impl IpcServer {
    /// Create a new IPC server instance.
    /// 創建新的 IPC 服務器實例。
    pub fn new(
        config: Arc<ConfigManager>,
        cancel: CancellationToken,
        data_dir: impl Into<String>,
        cmd_channels: EngineCommandChannels,
    ) -> Self {
        Self {
            config,
            cancel,
            data_dir: Arc::new(PathBuf::from(data_dir.into())),
            cmd_channels,
            budget_tracker: Arc::new(RwLock::new(None)),
            teacher_loop: Arc::new(RwLock::new(None)),
            risk_stores: None,
            learning_store: None,
            budget_store: None,
            audit_pool: Arc::new(RwLock::new(None)),
            scanner_registry: None,
            strategist_counters: Arc::new(RwLock::new(None)),
            live_auth_recheck_tx: None,
            h_state_cache: Arc::new(RwLock::new(None)),
            h_state_invalidation_tx: None,
            edge_reload_sender: Arc::new(RwLock::new(None)),
            cost_edge_advisor: Arc::new(RwLock::new(None)),
        }
    }

    /// G3-09 Phase A (2026-04-27): get a clone of the
    /// `CostEdgeAdvisorSlot` for late injection from
    /// `main_boot_tasks::spawn_cost_edge_advisor_if_enabled`. Mirrors the
    /// `h_state_cache_slot` G3-08 pattern — env-gate is checked at spawn
    /// time, IPC handler reads slot per connection.
    /// G3-09 Phase A：取 advisor slot handle 給 main_boot_tasks 在 env-gate 通過後注入。
    pub fn cost_edge_advisor_slot(&self) -> CostEdgeAdvisorSlot {
        Arc::clone(&self.cost_edge_advisor)
    }

    /// F6 PH5-WIRE-1 RELOAD (2026-04-26): get a clone of the edge reload
    /// sender slot for late injection from main.rs once
    /// `spawn_edge_estimates_reloader_if_enabled` returns its sender handle.
    /// Mirrors `h_state_cache_slot` / `audit_pool_slot` accessor pattern.
    /// F6 PH5-WIRE-1 RELOAD：取得 edge 重載 sender slot handle，供 main.rs
    /// 在 `spawn_edge_estimates_reloader_if_enabled` 回傳 sender 後 late inject。
    /// 對齊 `h_state_cache_slot` / `audit_pool_slot` 取 handle pattern。
    pub fn edge_reload_sender_slot(&self) -> EdgeReloadSenderSlot {
        Arc::clone(&self.edge_reload_sender)
    }

    /// G3-08 H State Gateway Phase 1 (2026-04-26): get a clone of the
    /// `HStateCacheSlot` for late injection from
    /// `main_boot_tasks::spawn_h_state_poller_if_enabled`. Mirrors the
    /// `budget_tracker_slot` / `teacher_loop_slot` / `audit_pool_slot`
    /// pattern.
    /// G3-08：取 cache slot handle 給 main_boot_tasks 在 env-gate 通過後注入。
    pub fn h_state_cache_slot(&self) -> HStateCacheSlot {
        Arc::clone(&self.h_state_cache)
    }

    /// G3-08 H State Gateway Phase 1 (2026-04-26): wire the invalidation
    /// channel sender so the `invalidate_h_state` IPC method can push
    /// hints to the poller. Call after the poller is spawned (paired with
    /// `h_state_cache_slot()` injection).
    /// G3-08：接入 invalidation channel sender，讓 `invalidate_h_state`
    /// IPC method 可推 hint 給 poller。在 poller spawn 後呼叫
    ///（與 cache slot 注入配對）。
    pub fn set_h_state_invalidation_sender(&mut self, tx: InvalidationSender) {
        self.h_state_invalidation_tx = Some(tx);
    }

    /// G3-11: get a clone of the `CycleCounters` slot for late injection
    /// from main.rs once the StrategistScheduler is spawned. Mirrors the
    /// `budget_tracker_slot` / `teacher_loop_slot` / `audit_pool_slot`
    /// pattern. Caller does
    /// `slot.write().await.replace(scheduler.cycle_counters())`.
    /// G3-11：取得 CycleCounters slot handle 給 main.rs scheduler spawn 後注入。
    pub fn strategist_counters_slot(&self) -> StrategistCountersSlot {
        Arc::clone(&self.strategist_counters)
    }

    /// PIPELINE-SLOT-1 Phase 3: wire the Live auth watcher's trigger
    /// sender so the `trigger_live_auth_recheck` IPC method can wake the
    /// watcher for sub-5s respawn / teardown TTR on operator renew/revoke.
    ///
    /// Call after `LiveAuthWatcher::new(...)` returns in main.rs, before
    /// `ipc_server.run()` starts accepting connections. Absent wiring is
    /// not an error — the IPC method will respond with a structured
    /// `watcher_disabled` status.
    ///
    /// PIPELINE-SLOT-1 Phase 3：接入 Live 授權 watcher 的 trigger sender，
    /// 讓 `trigger_live_auth_recheck` IPC method 在 operator renew/revoke
    /// 時 sub-5s 喚醒 watcher 完成 respawn / teardown。
    ///
    /// main.rs 中 `LiveAuthWatcher::new(...)` 回傳後、`ipc_server.run()`
    /// 開始接受連線前呼叫。未接線非錯誤 — IPC method 會回結構化
    /// `watcher_disabled` 狀態。
    pub fn set_live_auth_recheck_sender(&mut self, tx: tokio::sync::mpsc::Sender<()>) {
        self.live_auth_recheck_tx = Some(tx);
    }

    /// 2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN: wire the live
    /// command sender slot. The `LiveAuthWatcher` writes the latest live
    /// `UnboundedSender<PipelineCommand>` into this slot on every
    /// authorization-driven respawn / clears it on teardown. IPC handlers
    /// read a per-request snapshot via `EngineCommandChannels::live_snapshot()`.
    ///
    /// Call after `IpcServer::new(... cmd_channels ...)` (which sees an
    /// empty slot) and before `ipc_server.run()` starts accepting
    /// connections. Idempotent — re-wiring is a no-op given Arc identity
    /// equality.
    ///
    /// 2026-04-27：接入 live 命令 sender slot。`LiveAuthWatcher` 在每次
    /// 授權驅動的 respawn 寫入最新 live `UnboundedSender<PipelineCommand>`、
    /// 在 teardown 清空。IPC handler 經 `EngineCommandChannels::live_snapshot()`
    /// 讀取每請求快照。
    ///
    /// 在 `IpcServer::new(... cmd_channels ...)`（空 slot）之後、
    /// `ipc_server.run()` 接受連線之前呼叫。冪等 — 重複接線基於 Arc 身份相等
    /// 為 no-op。
    pub fn set_live_cmd_sender_slot(&mut self, slot: LiveCmdSenderSlot) {
        self.cmd_channels.live_slot = Some(slot);
    }

    /// Scanner IPC: wire the SymbolRegistry so get_active_symbols / get_scanner_status work.
    /// Must be called before run(). symbol_registry is available in main.rs before IPC spawn.
    /// 掃描器 IPC：接入 SymbolRegistry，使 get_active_symbols / get_scanner_status 生效。
    /// 必須在 run() 前調用。symbol_registry 在 main.rs 中在 IPC spawn 前已可用。
    pub fn set_scanner_registry(
        &mut self,
        registry: Arc<crate::scanner::registry::SymbolRegistry>,
    ) {
        self.scanner_registry = Some(registry);
    }

    /// ARCH-RC1 1C-2-E: get a clone of the audit pool slot for late injection
    /// from main.rs once the DB pool is ready.
    /// ARCH-RC1 1C-2-E：取得審計 pool 槽位句柄供 main.rs 在 DB pool 就緒後注入。
    pub fn audit_pool_slot(&self) -> AuditPoolSlot {
        Arc::clone(&self.audit_pool)
    }

    /// ARCH-RC1 1C-2-C / LIVE-P2-1: wire per-engine RiskConfig stores + unified Config stores.
    /// ARCH-RC1 1C-2-C / LIVE-P2-1：接入每引擎 RiskConfig stores + 統一 Config stores。
    ///
    /// `risk` bundles paper/demo/live stores; IPC routes to the correct one via the
    /// `engine` param in `get_risk_config` / `patch_risk_config` (default: "paper").
    /// `risk` 捆綁三個 stores；IPC 通過請求的 `engine` 字段路由（默認 "paper"）。
    pub fn set_config_stores(
        &mut self,
        risk: PerEngineRiskStores,
        learning: Arc<ConfigStore<LearningConfig>>,
        budget: Arc<ConfigStore<BudgetConfig>>,
    ) {
        self.risk_stores = Some(risk);
        self.learning_store = Some(learning);
        self.budget_store = Some(budget);
    }

    /// Phase 4.1: Get a clone of the Teacher loop slot for late injection.
    /// Phase 4.1：取得 Teacher loop 槽位的複製句柄供延後注入。
    pub fn teacher_loop_slot(&self) -> TeacherLoopSlot {
        Arc::clone(&self.teacher_loop)
    }

    /// Phase 4 (4-15): Get a clone of the BudgetTracker slot for late injection.
    /// Phase 4 (4-15)：取得 BudgetTracker 槽位的複製句柄供延後注入使用。
    ///
    /// Callers in main.rs construct the BudgetTracker after the DB pool is ready,
    /// then write it into this slot via `slot.write().await.replace(tracker)`.
    /// main.rs 在 DB pool 就緒後構造 BudgetTracker，再透過
    /// `slot.write().await.replace(tracker)` 寫入此槽位。
    pub fn budget_tracker_slot(&self) -> BudgetTrackerSlot {
        Arc::clone(&self.budget_tracker)
    }

    /// Start listening. This function runs until cancellation.
    /// 開始監聽。此函數運行直到取消。
    pub async fn run(&self) -> Result<(), IpcError> {
        let cfg = self.config.get();
        let socket_path = &cfg.ipc_socket_path;

        // Ensure parent directory exists / 確保父目錄存在
        if let Some(parent) = Path::new(socket_path).parent() {
            tokio::fs::create_dir_all(parent).await.map_err(|e| {
                IpcError::Setup(format!(
                    "failed to create socket dir '{}': {}",
                    parent.display(),
                    e
                ))
            })?;
        }

        // Remove stale socket if exists / 移除過時的套接字文件
        if Path::new(socket_path).exists() {
            info!(path = socket_path, "removing stale socket / 移除過時套接字");
            tokio::fs::remove_file(socket_path)
                .await
                .map_err(|e| IpcError::Setup(format!("failed to remove stale socket: {e}")))?;
        }

        let listener = UnixListener::bind(socket_path)
            .map_err(|e| IpcError::Setup(format!("failed to bind socket '{socket_path}': {e}")))?;

        // I-02: restrict socket to owner (0o600) to prevent unauthorized IPC access.
        // I-02：將套接字限制為所有者可讀寫（0o600），防止未授權 IPC 訪問。
        {
            use std::os::unix::fs::PermissionsExt;
            if let Err(e) =
                std::fs::set_permissions(socket_path, std::fs::Permissions::from_mode(0o600))
            {
                warn!(path = socket_path, error = %e, "failed to set socket mode 0o600 / 設定套接字權限失敗");
            }
        }

        info!(
            path = socket_path,
            "IPC server listening / IPC 服務器已啟動"
        );

        loop {
            tokio::select! {
                _ = self.cancel.cancelled() => {
                    info!("IPC server shutting down / IPC 服務器正在關閉");
                    break;
                }
                accept_result = listener.accept() => {
                    match accept_result {
                        Ok((stream, _addr)) => {
                            let config = Arc::clone(&self.config);
                            let cancel = self.cancel.clone();
                            let data_dir = Arc::clone(&self.data_dir);
                            let cmd_channels = self.cmd_channels.clone();
                            let budget_slot = Arc::clone(&self.budget_tracker);
                            let teacher_slot = Arc::clone(&self.teacher_loop);
                            let risk_stores = self.risk_stores.clone();
                            let learning_store = self.learning_store.clone();
                            let budget_store = self.budget_store.clone();
                            let audit_pool = self.audit_pool.read().await.clone();
                            let scanner_reg = self.scanner_registry.clone();
                            // G3-11: read the slot once per connection — Arc clone is cheap;
                            // late-injected counters become visible automatically without
                            // requiring an IPC server restart.
                            // G3-11：每連線讀一次 slot；scheduler 後綁的 counters 自動可見，
                            // IPC server 不需重啟。
                            let strategist_counters =
                                self.strategist_counters.read().await.clone();
                            let live_auth_recheck_tx = self.live_auth_recheck_tx.clone();
                            // G3-08: clone Arc handle to the H State cache slot —
                            // each connection sees late-injected cache automatically
                            // without requiring an IPC restart (mirrors strategist
                            // counters / budget tracker / teacher loop patterns).
                            // G3-08：複製 H State cache slot 的 Arc handle。
                            // 每連線自動看到延後注入的 cache，不需重啟 IPC。
                            let h_state_cache = Arc::clone(&self.h_state_cache);
                            let h_state_invalidation_tx = self.h_state_invalidation_tx.clone();
                            // F6 PH5-WIRE-1 RELOAD: read slot once at accept time.
                            // Late-injected sender becomes visible to subsequent
                            // connections without IPC restart.
                            // F6：每連線在 accept 時讀一次 slot；late-injected sender
                            // 對後續連線自動可見、IPC 不需重啟。
                            let edge_reload_sender =
                                self.edge_reload_sender.read().await.clone();
                            // G3-09 Phase A: clone Arc handle to advisor slot —
                            // each connection sees late-injected advisor automatically
                            // without IPC restart (same pattern as h_state_cache).
                            // G3-09 Phase A：複製 advisor slot Arc handle，每連線
                            // 自動看到 late-injected advisor 不需重啟 IPC。
                            let cost_edge_advisor_slot = Arc::clone(&self.cost_edge_advisor);
                            tokio::spawn(async move {
                                handle_connection(stream, config, cancel, data_dir, cmd_channels, budget_slot, teacher_slot, risk_stores, learning_store, budget_store, audit_pool, scanner_reg, strategist_counters, live_auth_recheck_tx, h_state_cache, h_state_invalidation_tx, edge_reload_sender, cost_edge_advisor_slot).await;
                            });
                        }
                        Err(e) => {
                            error!(error = %e, "failed to accept connection / 接受連接失敗");
                        }
                    }
                }
            }
        }

        // Clean up socket file / 清理套接字文件
        let _ = tokio::fs::remove_file(socket_path).await;
        info!(path = socket_path, "IPC socket removed / IPC 套接字已移除");
        Ok(())
    }
}

