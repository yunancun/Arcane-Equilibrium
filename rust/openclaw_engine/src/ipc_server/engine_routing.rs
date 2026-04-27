//! Per-engine IPC routing primitives — `PerEngineRiskStores` (per-mode
//! `RiskConfig` ConfigStore bundle) + `EngineCommandChannels` (per-pipeline
//! `PipelineCommand` mpsc senders) + `extract_engine_tx` dispatcher helper.
//! 每引擎 IPC 路由原語 — `PerEngineRiskStores`（每模式 `RiskConfig`
//! ConfigStore 綑綁）+ `EngineCommandChannels`（每管線 `PipelineCommand`
//! mpsc 發送端）+ `extract_engine_tx` 分派輔助。
//!
//! MODULE_NOTE (EN): Centralises the "select the right pipeline by `engine`
//!   string" logic that LIVE-P2-1 (RiskConfig) and 3E-3 (command channels)
//!   added across the IPC handlers. Both bundles default unknown / missing
//!   engine names to `paper` (fail-safe). `extract_engine_tx` additionally
//!   falls back to the primary pipeline when no `engine` param is supplied,
//!   logging a debug hint so the migration to explicit engine routing can
//!   be observed in logs.
//! MODULE_NOTE (中)：集中 LIVE-P2-1（RiskConfig）與 3E-3（命令通道）在
//!   IPC handler 各處新增的「依 `engine` 字串選擇正確管線」邏輯。兩個綑綁都
//!   把未知/缺失的引擎名 default 到 `paper`（安全默認）。`extract_engine_tx`
//!   在缺 `engine` 參數時退到主要管線，並 debug log 一行提示，便於觀測
//!   遷移到明確 engine 路由的進度。
//!
//! Split out of `ipc_server/mod.rs` as part of G5-FUP-IPC-MOD-SPLIT (2026-04-26).
//! 於 G5-FUP-IPC-MOD-SPLIT（2026-04-26）從 `ipc_server/mod.rs` 拆出。

use crate::config::{ConfigStore, RiskConfig};
use crate::tick_pipeline::PipelineCommand;
use parking_lot::RwLock;
use std::sync::Arc;

/// Slot type for the live pipeline command sender. The
/// `LiveAuthWatcher` rotates the inner `Sender` on every authorization-
/// driven respawn / teardown.
///
/// 2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN: previously the
/// live cmd_tx was a boot-time-fixed `Option<UnboundedSender<...>>` —
/// fine when boot decided live spawn once, broken once mid-session
/// respawn became a thing. Slot pattern lets IPC handlers read the
/// latest sender per request via [`EngineCommandChannels::live_snapshot`].
///
/// `parking_lot::RwLock` is used (not `tokio::sync::RwLock`) so the
/// `LiveAuthWatcher`'s spawner callback — which is a synchronous closure
/// invoked from within an async context — can write the slot without
/// touching async machinery. Read sites (IPC handlers, fan-out) are also
/// trivially short, so the parking_lot RwLock pattern is safe in both
/// sync and async paths.
///
/// Live 管線命令 sender 的 slot 類型。`LiveAuthWatcher` 每次授權驅動的
/// respawn / teardown 都會輪替內層 Sender。Pre-2026-04-27 為 boot 時固定
/// 的 `Option<UnboundedSender<...>>` — boot 決定一次 live spawn 時可行，
/// 加入中途 respawn 後失準。Slot pattern 讓 IPC handler 每次請求讀最新
/// sender（經 [`EngineCommandChannels::live_snapshot`]）。
///
/// 採 `parking_lot::RwLock`（非 `tokio::sync::RwLock`）讓 watcher 的同步
/// spawner closure（在 async context 內被呼叫）可不繞 async 機械直接寫
/// slot。讀端（IPC handler、fan-out）臨界區極短，sync / async 路徑皆安全。
pub type LiveCmdSenderSlot = Arc<RwLock<Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>>>;

// ---------------------------------------------------------------------------
// LIVE-P2-1: Per-engine RiskConfig stores
// LIVE-P2-1：每個引擎模式的 RiskConfig stores
// ---------------------------------------------------------------------------

/// Bundles three RiskConfig stores — one per PipelineKind — so IPC routing and
/// TickPipeline wiring can select the correct store without scattering
/// individual Option<Arc<...>> fields across every function signature.
///
/// 將三個 RiskConfig stores 捆綁為一個結構體（每個 PipelineKind 一個），
/// 使 IPC 路由與 TickPipeline 接線可以選擇正確 store，
/// 而不需在每個函數簽名中分散獨立的 Option<Arc<...>> 字段。
#[derive(Clone)]
pub struct PerEngineRiskStores {
    /// Paper-only mode (no exchange connection) — liberal limits for strategy validation.
    /// 純 paper 模式（無交易所連接）— 寬鬆限制，用於策略驗證。
    pub paper: Arc<ConfigStore<RiskConfig>>,
    /// Demo mode (Bybit Demo exchange, simulated margin) — same as paper by default.
    /// Demo 模式（Bybit Demo 交易所，模擬保證金）— 默認與 paper 相同。
    pub demo: Arc<ConfigStore<RiskConfig>>,
    /// Live mode (real money, Mainnet) — tighter defaults, operator must relax before go-live.
    /// 實盤模式（真實資金，主網）— 更保守的默認值，Operator 需主動放寬才能上線。
    pub live: Arc<ConfigStore<RiskConfig>>,
}

impl PerEngineRiskStores {
    /// Select the store matching the given engine name string.
    /// Unknown names fall through to `paper` (fail-safe default).
    /// 按引擎名稱字符串選擇 store。未知名稱回退到 `paper`（安全默認）。
    pub fn select(&self, engine: &str) -> &Arc<ConfigStore<RiskConfig>> {
        match engine {
            "demo" => &self.demo,
            "live" => &self.live,
            _ => &self.paper, // "paper" or unknown → paper (fail-safe)
        }
    }
}

// ---------------------------------------------------------------------------
// 3E-3: Per-pipeline command channel routing
// 3E-3：每管線命令通道路由
// ---------------------------------------------------------------------------

/// Routes IPC commands to the correct pipeline's command channel.
/// In 3E-ARCH, each pipeline (Paper/Demo/Live) has its own command channel.
/// IPC handlers extract the `engine` param and select the correct sender.
///
/// 將 IPC 命令路由到正確管線的命令通道。
/// 3E-ARCH 下每個管線有獨立命令通道，IPC handler 按 `engine` 參數選擇。
///
/// 2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN: `live` is now a slot
/// rotated by the `LiveAuthWatcher`. The original `Option<...>` was kept
/// for the test-side `Default` impl (the slot defaults to `None` on
/// `Default::default()` — same observable behaviour as the pre-fix `None`).
///
/// 2026-04-27：`live` 改為 slot 由 `LiveAuthWatcher` 輪替。`Default::default()`
/// 下 slot 預設 `None`，與修復前 `None` 行為等同（測試端不需修改）。
#[derive(Clone, Default)]
pub struct EngineCommandChannels {
    pub paper: Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    pub demo: Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    /// Pre-2026-04-27 owned sender, retained for backward-compatible
    /// test instantiation. Production wiring uses `live_slot` below.
    /// 修復前 owned sender，保留以兼容測試端構造；生產接線改用 `live_slot`。
    pub live: Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    /// 2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN: dynamic live
    /// sender slot rotated by `LiveAuthWatcher` on respawn / teardown.
    /// `None` when no slot is wired (tests / paper-only configurations).
    /// `select("live")` and `primary()` prefer this slot's snapshot when
    /// it contains `Some(_)`, falling back to the owned `live` field
    /// otherwise.
    /// 2026-04-27：`LiveAuthWatcher` 在 respawn / teardown 輪替的動態 live
    /// sender slot。未接線（測試 / 純 paper）時為 `None`。`select("live")`
    /// 與 `primary()` 優先讀此 slot 的快照（Some 時）；否則退回 owned
    /// `live` 欄位。
    pub live_slot: Option<LiveCmdSenderSlot>,
}

impl EngineCommandChannels {
    /// Read a snapshot of the live sender. Prefers `live_slot` (the
    /// watcher-rotated slot), falls back to the owned `live` field for
    /// tests / configurations that did not wire a slot.
    ///
    /// Note: this clones the inner `UnboundedSender` (cheap — a tokio
    /// `UnboundedSender` is `Arc`-backed). Returns `None` when neither
    /// source has a sender.
    ///
    /// 讀 live sender 快照。優先讀 `live_slot`（watcher 輪替的 slot），
    /// 未接線時退回 owned `live` 欄位。Clone 內層 `UnboundedSender`
    /// （tokio 為 `Arc`-backed，廉價）。皆無時回 `None`。
    pub fn live_snapshot(&self) -> Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>> {
        if let Some(slot) = &self.live_slot {
            // try_read avoids blocking the IPC dispatch thread on a writer
            // contention (watcher writer holds the lock for ~1 µs during
            // respawn / teardown). On contention we fall back to the
            // owned `live` field — slot snapshot is best-effort, but the
            // `live` clone is also fresh in the rare race window.
            //
            // try_read 避免 IPC dispatch 在 writer 爭用時阻塞（watcher 寫
            // 期間 ~1 µs）。爭用時退回 owned `live` 欄位 — slot snapshot
            // 為盡力，但該 race 窗口極短，owned `live` 的 clone 仍 fresh。
            if let Some(guard) = slot.try_read() {
                if let Some(tx) = guard.as_ref() {
                    return Some(tx.clone());
                }
            } else {
                tracing::debug!(
                    "EngineCommandChannels::live_snapshot: live_slot try_read contention, \
                     owned live = None → returning None \
                     / live_slot try_read 爭用，owned live = None → 回 None"
                );
            }
        }
        self.live.clone()
    }

    /// Select the command sender for the given engine name.
    /// Falls back to paper for unknown names (fail-safe).
    ///
    /// 2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN: returns an
    /// `Option<UnboundedSender>` instead of `&Option<...>` so the live
    /// arm can read a fresh snapshot from `live_slot` per-call. Paper /
    /// Demo are owned `Option<UnboundedSender>` and clone cheaply
    /// (`Arc`-backed), so the change is uniform across arms.
    ///
    /// 按引擎名選擇命令發送端。未知名稱回退到 paper（安全默認）。
    /// 2026-04-27：回 `Option<UnboundedSender>`（owned）以利 live arm
    /// 每次讀 `live_slot` 快照；paper / demo 為 `Arc`-backed，clone 廉價，
    /// 三 arm 行為對齊。
    pub fn select(
        &self,
        engine: &str,
    ) -> Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>> {
        match engine {
            "demo" => self.demo.clone(),
            "live" => self.live_snapshot(),
            _ => self.paper.clone(), // "paper" or unknown → paper (fail-safe)
        }
    }

    /// Return the primary (first available) sender for commands that
    /// don't specify an engine param. Priority: live > demo > paper.
    /// 返回主要（第一個可用）sender，供未指定 engine 的命令使用。
    pub fn primary(&self) -> Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>> {
        if let Some(tx) = self.live_snapshot() {
            return Some(tx);
        }
        if let Some(tx) = &self.demo {
            return Some(tx.clone());
        }
        self.paper.clone()
    }

    /// Return the label of the primary engine ("live" / "demo" / "paper").
    ///
    /// 2026-04-27: read the live slot snapshot (not the owned field) for
    /// label semantics. When `live_slot` is wired but currently empty
    /// (mid-teardown), `live` will also be empty (boot leaves owned
    /// `live` as None when slot wiring is in use), so the fall-through
    /// to demo / paper is correct.
    ///
    /// 返回主引擎的標籤。2026-04-27：讀 live slot snapshot（非 owned 欄位）。
    /// `live_slot` 接線但目前空（teardown 中）時 owned `live` 也為 None
    /// （boot 在採用 slot 時不再寫入 owned `live`），退回 demo / paper 正確。
    pub fn primary_label(&self) -> &'static str {
        if self.live_snapshot().is_some() {
            "live"
        } else if self.demo.is_some() {
            "demo"
        } else {
            "paper"
        }
    }
}

/// 3E-3: Extract the `engine` param from request params and select the
/// matching pipeline command sender. Falls back to primary if missing.
/// 3E-3：從請求參數提取 `engine` 並選擇對應管線命令發送端，缺失時回退到主管線。
///
/// 2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN: returns owned
/// `Option<UnboundedSender>` (cheap `Arc` clone) so the live arm can read
/// a fresh `live_slot` snapshot per request. Lifetime annotation on
/// `channels` removed — the helper no longer borrows from `channels`
/// across the return.
///
/// 2026-04-27：回 owned `Option<UnboundedSender>`（廉價 `Arc` clone），
/// live arm 每請求讀 `live_slot` 快照。`channels` 生命週期註記移除 —
/// helper 不再跨返回值 borrow。
pub(crate) fn extract_engine_tx(
    params: &serde_json::Value,
    channels: &EngineCommandChannels,
) -> Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>> {
    match params.get("engine").and_then(|v| v.as_str()) {
        Some(engine) => channels.select(engine),
        None => {
            tracing::debug!(
                "ipc: no 'engine' param — routing to primary pipeline \
                 (add explicit engine param for deterministic routing) \
                 / ipc：無 'engine' 參數 — 路由到主管線（建議加入明確 engine 參數）"
            );
            channels.primary()
        }
    }
}
