//! PIPELINE-SLOT-1 Phase 3 — Live authorization watcher that drives
//! automatic re-spawn after operator renewal and immediate teardown on
//! invalidation, without killing Demo / Paper.
//!
//! PIPELINE-SLOT-1 Phase 3 — Live 授權 watcher：operator renew 後自動
//! respawn、授權失效時立即拆 Live，不殺 Demo / Paper。
//!
//! MODULE_NOTE (EN):
//!   Phase 2 added `PipelineSlot::teardown()` so an auth revocation tears
//!   down **only** the Live pipeline. But Phase 2 had no respawn path —
//!   once torn down, Live stayed down until full engine restart. The
//!   5-minute poll loop in `main.rs` only tore down; it never re-checked
//!   after a failure.
//!
//!   Phase 3 replaces that 5-min loop with a state-machine watcher that:
//!     (1) polls `load_and_verify` every 5 seconds,
//!     (2) respawns Live when authorization becomes valid (slot currently
//!         Empty) — gated by an exponential backoff so a persistently
//!         failing `build_exchange_pipeline` does not become a request storm,
//!     (3) tears down Live when authorization becomes invalid (slot
//!         currently Spawned) — teardown runs every time, never gated by
//!         backoff,
//!     (4) accepts a synchronous wake-up via IPC `trigger_live_auth_recheck`
//!         so Python's renew/revoke routes achieve ≤5s TTR without waiting
//!         for the next poll,
//!     (5) exits cleanly when the engine-wide shutdown token fires.
//!
//!   Demo / Paper slots are completely untouched by this watcher — it only
//!   ever observes and acts on the Live slot.
//!
//!   Design points:
//!     * 5-second poll interval. Phase 2 used 300s because only teardown
//!       needed detection latency; with respawn added, TTR after renewal
//!       matters too and the operator expects "Live comes back right away".
//!     * The IPC trigger is a `tokio::sync::mpsc::Receiver<()>` with a
//!       small bounded capacity (1). The IPC handler uses `try_send`; if
//!       the channel is full, the wake-up is coalesced (a decision cycle
//!       was already scheduled and hasn't fired yet). This is correct — a
//!       second wake-up in the same sub-5s window would just do the same
//!       recheck.
//!     * Backoff applies only to spawn attempts. Teardown runs immediately
//!       on any auth invalidation.
//!     * Config snapshot is refreshed on every attempted spawn via
//!       `ConfigManager::get()` — pay the ~5ns ArcSwap read each time so
//!       hot-reloaded config takes effect on the next respawn.
//!     * The watcher owns a `SpawnOp` trait object so tests can inject a
//!       mock that counts calls and returns deterministic errors without
//!       spinning a real exchange pipeline.
//!
//!   2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN fix:
//!     RCA found `pipeline_snapshot_live.json` had not been written in 8
//!     days because `(None, None)` boot match arm in `main.rs:1029` skipped
//!     `spawn_live_pipeline` whenever `authorization.json` was absent at
//!     boot. After operator renewed authorization mid-session the watcher
//!     called `slot_op.try_spawn` (which only spawns the WS supervisor /
//!     listener / balance-refresh tasks via `build_exchange_pipeline`), but
//!     never spawned the Live OS thread that runs `run_event_consumer`.
//!     That thread is the producer of `state_writer` / `snapshot_writer`
//!     / `trading.fills` etc., so 8 days of Live had zero `live_state.json`
//!     mtime updates and zero rows in `trading.fills` / `learning.exit_features`.
//!
//!     Fix: the watcher now optionally owns a `LivePipelineSpawner`
//!     callback (constructed in `main.rs` so the closure can capture all
//!     of `WriterSenders` / `PipelineSpawnContext` / `live_positions_mirror`
//!     etc.). On a successful `slot_op.try_spawn` the watcher invokes the
//!     callback with the `SpawnOutput { bindings, slot_cancel_token }` and
//!     the closure performs the missing `spawn_live_pipeline` work,
//!     returning the `std::thread::JoinHandle<()>` for the OS thread plus
//!     a fresh tokio command channel and event channel registered into the
//!     dynamic `live_cmd_slot` / `live_event_slot` (so fan-out + IPC route
//!     newly-routed commands and ticks at zero overhead between teardowns).
//!
//!     Without a spawner injected (unit tests, IPC-only configurations) the
//!     watcher behaves exactly as Phase 3 did — slot try_spawn alone — so
//!     existing tests still hold. With a spawner injected, the OS thread
//!     handle is captured into a shared slot the shutdown sequence reads.
//!
//! MODULE_NOTE (中):
//!   Phase 2 加入 `PipelineSlot::teardown()`，讓授權撤銷只拆 Live。但 Phase 2
//!   沒有 respawn 路徑 — 拆完後 Live 只能等整機重啟。main.rs 的 5 分鐘 loop
//!   只做 teardown，失敗後不再重檢。
//!
//!   Phase 3 用狀態機 watcher 取代該 5 分鐘 loop：
//!     (1) 每 5 秒呼叫 `load_and_verify` 輪詢；
//!     (2) 授權變有效且槽位空 → respawn，指數退避閘保護
//!         （避免持續失敗變請求風暴）；
//!     (3) 授權變無效且槽位 Spawned → teardown，teardown 不受退避閘限制，
//!         每次必立即跑；
//!     (4) 經 IPC `trigger_live_auth_recheck` 接收同步喚醒，讓 Python
//!         renew/revoke 路由無需等下個輪詢就拿到 ≤5s TTR；
//!     (5) 引擎級 shutdown token 觸發時乾淨退出。
//!
//!   Demo / Paper 槽位完全不碰 — watcher 只觀察並操作 Live 槽位。
//!
//!   設計要點：
//!     * 5 秒輪詢間隔。Phase 2 用 300s 是因為只需偵測 teardown 時機；
//!       加上 respawn 後，renew 後的 TTR 也重要，operator 期望「Live 立刻回來」。
//!     * IPC 觸發以 `tokio::sync::mpsc::Receiver<()>` 實作，容量 1。IPC
//!       handler 用 `try_send`；滿時合併喚醒（本來就排了 recheck）—
//!       sub-5s 窗口內第二次喚醒只會做同一次 recheck，合併正確。
//!     * 退避只對 spawn；teardown 立即跑。
//!     * 每次嘗試 spawn 都經 `ConfigManager::get()` 拿新快照
//!       （~5ns ArcSwap 讀），確保 hot-reload 配置次次 respawn 生效。
//!     * Watcher 持有 `SpawnOp` trait 物件，測試可注入計數/出錯的 mock，
//!       無需真實交易所管線。
//!
//!   2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN 修復：
//!     RCA 發現 `pipeline_snapshot_live.json` 已 8 天未更新 — boot 時
//!     `main.rs:1029` 的 `(None, None)` match arm 在 `authorization.json`
//!     不存在時跳過 `spawn_live_pipeline`。Operator 中途 renew 後 watcher
//!     雖呼叫 `slot_op.try_spawn`（只起 WS supervisor / listener /
//!     balance-refresh，經 `build_exchange_pipeline`），但**從未** spawn 跑
//!     `run_event_consumer` 的 Live OS 線程。該線程是 `state_writer` /
//!     `snapshot_writer` / `trading.fills` 等等的生產者，所以 8 天 Live
//!     `live_state.json` mtime 0 更新、`trading.fills` / `learning.exit_features`
//!     0 row。
//!
//!     修復：watcher 多帶一個可選 `LivePipelineSpawner` callback（於
//!     `main.rs` 構造，closure 可 capture `WriterSenders` /
//!     `PipelineSpawnContext` / `live_positions_mirror` 等）。`slot_op.try_spawn`
//!     成功後 watcher 把 `SpawnOutput { bindings, slot_cancel_token }` 交給
//!     callback，由 callback 補齊缺失的 `spawn_live_pipeline` 工作，回傳
//!     OS 線程的 `std::thread::JoinHandle<()>` + 新建 tokio 命令通道 +
//!     新建事件通道並寫入動態 `live_cmd_slot` / `live_event_slot`（fan-out
//!     + IPC 在 teardown 之間零負擔路由命令與 tick）。
//!
//!     未注入 spawner 時（單測、純 IPC 配置）watcher 行為完全等同 Phase 3 —
//!     僅 slot try_spawn — 既有測試不破。注入後 OS 線程 handle 會寫入共享
//!     slot 給 shutdown 序列讀取。

use crate::main_fanout::LiveEventSenderSlot;
use crate::pipeline_slot::{PipelineSlot, SlotKind, SpawnConfig, SpawnError, SpawnOutput, TeardownError};
use crate::spawn_backoff::SpawnBackoff;
use async_trait::async_trait;
use openclaw_engine::bybit_rest_client::BybitEnvironment;
use openclaw_engine::config::ConfigManager;
use openclaw_engine::ipc_server::LiveCmdSenderSlot;
use openclaw_engine::live_authorization::{auth_error_kind, load_and_verify};
use parking_lot::Mutex as ParkingMutex;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

/// Default watcher poll interval. Chosen to give ≤5s TTR on both respawn
/// (post-renewal) and teardown (on revoke) paths. The 5-min pre-Phase-3
/// value was only acceptable when teardown was the only action; with
/// respawn, operator expectations tighten.
///
/// 預設 watcher 輪詢間隔。在 respawn（renew 後）與 teardown（revoke 後）
/// 兩條路徑都給出 ≤5s TTR。Phase 3 前的 5 分鐘只在「只做 teardown」情境
/// 可接受，加上 respawn 後 operator 期望更緊。
pub const DEFAULT_POLL_INTERVAL: Duration = Duration::from_secs(5);

/// Default base backoff after a spawn failure.
/// Spawn 失敗後預設基礎退避。
pub const DEFAULT_BACKOFF_BASE: Duration = Duration::from_secs(1);

/// Default cap on spawn backoff. After ~6 consecutive failures the gate
/// stabilises here (1→2→4→8→16→32→60, capped).
///
/// 預設 spawn 退避上限。大約 6 次連續失敗後穩定於此（1→2→4→8→16→32→60，飽和）。
pub const DEFAULT_BACKOFF_MAX: Duration = Duration::from_secs(60);

/// Capacity of the IPC trigger channel. `1` is enough — a pending trigger
/// already forces a recheck, so a second trigger within the same poll
/// window coalesces correctly.
///
/// IPC 觸發通道容量。`1` 足夠 — 已排程的 trigger 本就會 recheck，同窗口
/// 第二次 trigger 合併即可。
pub const IPC_TRIGGER_CAPACITY: usize = 1;

/// Spawn / teardown / is_spawned operations the watcher needs from its
/// slot. Factored into a trait so unit tests can inject a mock that
/// counts invocations and returns deterministic outcomes without spinning
/// a real exchange pipeline (which requires REST/WS clients + Bybit
/// endpoints).
///
/// The production implementation below delegates to `PipelineSlot`.
///
/// 2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN: `try_spawn` now
/// returns `Option<SpawnOutput>` instead of `bool` so the watcher can
/// hand the bindings + slot child token to the optional pipeline spawner
/// callback. `Ok(None)` keeps the same semantics as the previous
/// `Ok(false)`: `build_exchange_pipeline` returned None.
///
/// Watcher 所需的槽位操作（spawn / teardown / is_spawned）。抽成 trait
/// 讓單測注入計數與固定回應的 mock，不必啟動真實交易所管線（需 REST/WS
/// 客戶端與 Bybit endpoint）。生產實作在下方委派 `PipelineSlot`。
///
/// 2026-04-27 修復：`try_spawn` 從回 `bool` 改回 `Option<SpawnOutput>`，
/// watcher 能把 bindings + 子 token 交給可選 spawner callback。`Ok(None)`
/// 沿用之前 `Ok(false)` 語意：`build_exchange_pipeline` 回 None。
#[async_trait]
pub trait SpawnOp: Send + Sync {
    /// True iff the slot is currently `Spawned`.
    /// 槽位當前是否為 `Spawned`。
    fn is_spawned(&self) -> bool;

    /// Attempt to spawn the slot. Returns `Ok(Some(out))` on success
    /// (caller owns the bindings + slot-scoped child token to thread
    /// further), `Ok(None)` on `build_exchange_pipeline` returning None
    /// (structured reason already logged inside), `Err` on programming
    /// errors (`AlreadySpawned`).
    ///
    /// 嘗試啟動槽位。成功 `Ok(Some(out))`（呼叫端取走 bindings + 槽位子
    /// token 串下去）；`build_exchange_pipeline` 回 None 時 `Ok(None)`；
    /// 程式錯誤（`AlreadySpawned`）`Err`。
    async fn try_spawn(
        &self,
        cfg: &SpawnConfig<'_>,
    ) -> Result<Option<SpawnOutput>, SpawnError>;

    /// Teardown the slot. Idempotent on `Empty`.
    /// 拆槽位。對 `Empty` 為 no-op。
    async fn teardown(&self) -> Result<(), TeardownError>;
}

#[async_trait]
impl SpawnOp for PipelineSlot {
    fn is_spawned(&self) -> bool {
        PipelineSlot::is_spawned(self)
    }

    async fn try_spawn(
        &self,
        cfg: &SpawnConfig<'_>,
    ) -> Result<Option<SpawnOutput>, SpawnError> {
        PipelineSlot::try_spawn(self, cfg).await
    }

    async fn teardown(&self) -> Result<(), TeardownError> {
        PipelineSlot::teardown(self).await
    }
}

/// Handle returned from [`LiveAuthWatcher::new`] for the IPC layer to
/// invoke a synchronous recheck. Cloned into the IPC dispatcher (stored
/// on the server struct, NOT a module-level singleton) so the handler
/// thread can wake the watcher on `trigger_live_auth_recheck` requests.
///
/// `LiveAuthWatcher::new` 回傳的句柄，IPC 層用以觸發同步 recheck。
/// Clone 進 IPC dispatcher（存在 server 結構上，**不**是模組級 singleton），
/// 讓 handler 執行緒能在收到 `trigger_live_auth_recheck` 時喚醒 watcher。
#[derive(Clone)]
pub struct IpcTriggerHandle {
    tx: mpsc::Sender<()>,
}

impl IpcTriggerHandle {
    /// Best-effort wake-up. Returns `Ok(true)` on accepted wake-up,
    /// `Ok(false)` if the channel is full (coalesced — the existing
    /// pending wake-up will recheck), `Err(())` if the watcher has
    /// dropped the receiver.
    ///
    /// Called from IPC handler context (non-async). Uses `try_send` so
    /// it never blocks the IPC dispatch loop.
    ///
    /// 盡力喚醒。成功 `Ok(true)`；通道滿 `Ok(false)`（已有排隊喚醒將
    /// recheck，合併）；watcher 已 drop receiver `Err(())`。
    ///
    /// 於 IPC handler（同步）呼叫。用 `try_send` 永不阻塞 IPC dispatch。
    #[allow(dead_code)] // Public API: used by tests + future callers who prefer the status-enum surface over raw Sender
    pub fn trigger(&self) -> Result<bool, ()> {
        match self.tx.try_send(()) {
            Ok(()) => Ok(true),
            Err(mpsc::error::TrySendError::Full(_)) => Ok(false),
            Err(mpsc::error::TrySendError::Closed(_)) => Err(()),
        }
    }

    /// Clone the inner `Sender<()>` for callers that need the raw type
    /// (e.g. the `ipc_server` library module, which lives outside the
    /// binary-local `live_auth_watcher` module and therefore cannot name
    /// `IpcTriggerHandle` directly).
    ///
    /// Clone 內部 `Sender<()>`，供無法命名 `IpcTriggerHandle` 的呼叫端
    /// （例如 `ipc_server` 庫模組 — 位於 binary-local `live_auth_watcher`
    /// 模組之外）。
    pub fn sender(&self) -> mpsc::Sender<()> {
        self.tx.clone()
    }
}

/// Handle to the OS thread the spawner callback most recently produced.
/// Shared between the watcher (writer) and the shutdown sequence (reader)
/// so the engine-wide shutdown can `.join()` the live runtime thread
/// instead of orphaning it. `parking_lot::Mutex` is used because the
/// spawner callback (synchronous closure) writes the slot, and shutdown
/// reads the slot at engine-stop time — both are extremely short
/// critical sections.
///
/// 最近一次 spawner callback 產出的 OS 線程 handle。watcher 寫、shutdown
/// 序列讀，讓 engine-wide shutdown 可 `.join()` Live runtime thread 而非
/// 任其孤兒。`parking_lot::Mutex`：spawner callback（同步 closure）寫、
/// shutdown 引擎停止時讀，臨界區極短。
pub type LiveThreadHandleSlot = Arc<ParkingMutex<Option<std::thread::JoinHandle<()>>>>;

/// Result type returned by a [`LivePipelineSpawner`] invocation.
///
/// `Ok(handle)` = spawner produced a viable Live OS thread; the watcher
/// stores the handle for the shutdown sequence to join.
///
/// `Err(reason)` = spawner refused (e.g. fan-out / IPC slot was None at
/// the time of invocation, indicating a programming error in main.rs).
/// Treated as a spawn failure and engages the watcher backoff.
///
/// `LivePipelineSpawner` 回傳。`Ok(handle)` = spawner 成功，watcher 存 handle
/// 供 shutdown 序列 join。`Err(reason)` = spawner 拒絕（例如 fan-out / IPC
/// slot 該時為 None，main.rs 接線 bug），watcher 視為 spawn 失敗 + 啟動退避。
pub type LivePipelineSpawnResult = Result<std::thread::JoinHandle<()>, String>;

/// Callback invoked after a successful `slot_op.try_spawn` to perform the
/// rest of the Live boot path that the slot abstraction itself does NOT
/// cover — most importantly the OS thread that runs `run_event_consumer`
/// (which is the producer of `state_writer` / `snapshot_writer` / the
/// `trading.fills` writer). The watcher does not know how to construct
/// `EventConsumerDeps` (~24 fields of writers, shared clients, predictors,
/// etc.) so the closure is constructed in `main.rs::async_main` where all
/// those `Arc`s are already in scope.
///
/// The callback is `Send + Sync` because the watcher runs on a tokio
/// task and may be moved across worker threads. Fn (not FnMut / FnOnce)
/// lets us invoke it on every successful respawn.
///
/// `slot_op.try_spawn` 成功後呼叫的 callback，補齊 slot 抽象**不**涵蓋的
/// 其餘 Live 啟動路徑 — 重點是跑 `run_event_consumer` 的 OS 線程
/// （`state_writer` / `snapshot_writer` / `trading.fills` 寫入器的生產者）。
/// watcher 不知如何構造 `EventConsumerDeps`（~24 個 writer / 共享 client /
/// predictor 等欄位），因此 closure 構造於 `main.rs::async_main` — 那邊所有
/// `Arc` 都在 scope 內。
///
/// `Send + Sync` 因 watcher 跑在 tokio task，可能跨 worker thread 搬。
/// Fn（非 FnMut / FnOnce）讓我們每次成功 respawn 都能呼叫。
pub type LivePipelineSpawner = Arc<dyn Fn(SpawnOutput) -> LivePipelineSpawnResult + Send + Sync>;

/// Live authorization watcher.
///
/// Holds the Live slot, the engine config manager (for fresh
/// `EngineBootstrap` snapshots on each respawn), the environment label,
/// the engine-wide shutdown token (for clean exit on SIGTERM), a
/// `SpawnBackoff` for spawn-attempt rate limiting, and an IPC trigger
/// receiver.
///
/// 2026-04-27: optional `pipeline_spawner` + `thread_handle_slot` for
/// the LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN fix. When `pipeline_spawner`
/// is None the watcher behaves exactly as Phase 3 did (slot try_spawn /
/// teardown only); when Some, every successful slot try_spawn is followed
/// by a callback invocation that produces the OS thread running
/// `run_event_consumer` and the handle is captured into
/// `thread_handle_slot` for the shutdown sequence.
///
/// Live 授權 watcher。持有 Live 槽位、引擎配置管理器（每次 respawn
/// 取新 `EngineBootstrap` 快照）、環境標籤、引擎級 shutdown token
/// （SIGTERM 乾淨退出）、`SpawnBackoff`（限速 spawn 嘗試）、IPC
/// 觸發 receiver。
///
/// 2026-04-27：`pipeline_spawner` + `thread_handle_slot` 為
/// LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN 修復新增。`pipeline_spawner`
/// 為 None 時 watcher 行為完全等同 Phase 3（只 slot try_spawn / teardown）；
/// Some 時每次成功 try_spawn 後呼叫 callback 產出跑 `run_event_consumer`
/// 的 OS 線程，handle 寫入 `thread_handle_slot` 供 shutdown 序列 join。
pub struct LiveAuthWatcher {
    slot_op: Arc<dyn SpawnOp>,
    config: Arc<ConfigManager>,
    env: BybitEnvironment,
    poll_interval: Duration,
    engine_shutdown: CancellationToken,
    backoff: SpawnBackoff,
    ipc_trigger: mpsc::Receiver<()>,
    /// Optional callback for the second half of the Live boot path
    /// (LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN, 2026-04-27). None in unit
    /// tests + IPC-only configurations.
    /// 可選 callback；單測 + 純 IPC 配置時為 None。
    pipeline_spawner: Option<LivePipelineSpawner>,
    /// Slot the watcher writes the latest OS thread handle into, so the
    /// shutdown sequence can join it. None in unit tests where the spawner
    /// callback is also None.
    /// 寫入最近 OS 線程 handle 的 slot；shutdown 序列讀取後 join。單測
    /// 無 spawner 時亦為 None。
    thread_handle_slot: Option<LiveThreadHandleSlot>,
    /// BLOCKER-2 (2026-04-27): live_cmd_slot and live_event_slot are cleared
    /// on teardown so the governance broadcast loop and fan-out do not deliver
    /// commands / ticks to a dead pipeline after a mid-session teardown.
    /// None in unit tests (slots are owned by main.rs in production).
    ///
    /// BLOCKER-2（2026-04-27）：teardown 時清空兩個 slot，防止 governance
    /// broadcast 迴圈和 fan-out 在 teardown 後仍往死管線投命令 / tick。
    /// 單測中為 None（生產中由 main.rs 擁有）。
    live_cmd_slot: Option<LiveCmdSenderSlot>,
    live_event_slot: Option<LiveEventSenderSlot>,
}

impl LiveAuthWatcher {
    /// Construct the watcher. Returns `(Self, IpcTriggerHandle)`; the
    /// handle is cloned into the IPC dispatcher.
    ///
    /// `config` is an `Arc<ConfigManager>` so the watcher can pull a
    /// fresh `EngineBootstrap` snapshot on every respawn attempt
    /// (hot-reload propagates into Live respawns).
    ///
    /// Pre-2026-04-27 callers (no event-consumer spawner) keep this
    /// signature; new callers use [`Self::with_pipeline_spawner`].
    ///
    /// 建構 watcher。回傳 `(Self, IpcTriggerHandle)`；handle 由 IPC
    /// dispatcher clone。`config` 為 `Arc<ConfigManager>`，每次
    /// respawn 抓新 `EngineBootstrap` 快照（hot-reload 於下次 Live
    /// respawn 生效）。
    ///
    /// 2026-04-27 前的呼叫端（無 event-consumer spawner）沿用此簽名；
    /// 新呼叫端使用 [`Self::with_pipeline_spawner`]。
    #[allow(dead_code)] // Public API: kept for tests + pre-2026-04-27 callers
    pub fn new(
        slot_op: Arc<dyn SpawnOp>,
        config: Arc<ConfigManager>,
        env: BybitEnvironment,
        engine_shutdown: CancellationToken,
    ) -> (Self, IpcTriggerHandle) {
        Self::with_params(
            slot_op,
            config,
            env,
            engine_shutdown,
            DEFAULT_POLL_INTERVAL,
            DEFAULT_BACKOFF_BASE,
            DEFAULT_BACKOFF_MAX,
        )
    }

    /// Tunable constructor — exposed for tests and future config wiring.
    /// 可調構造 — 供測試與未來 config 接線。
    #[allow(dead_code)] // Public API: heavily used in unit tests; kept for binary callers that need timer overrides
    pub fn with_params(
        slot_op: Arc<dyn SpawnOp>,
        config: Arc<ConfigManager>,
        env: BybitEnvironment,
        engine_shutdown: CancellationToken,
        poll_interval: Duration,
        backoff_base: Duration,
        backoff_max: Duration,
    ) -> (Self, IpcTriggerHandle) {
        let (tx, rx) = mpsc::channel::<()>(IPC_TRIGGER_CAPACITY);
        (
            Self {
                slot_op,
                config,
                env,
                poll_interval,
                engine_shutdown,
                backoff: SpawnBackoff::new(backoff_base, backoff_max),
                ipc_trigger: rx,
                pipeline_spawner: None,
                thread_handle_slot: None,
                live_cmd_slot: None,
                live_event_slot: None,
            },
            IpcTriggerHandle { tx },
        )
    }

    /// Construct the watcher with a `LivePipelineSpawner` callback so the
    /// watcher drives the **full** Live boot path on respawn, not just
    /// `slot_op.try_spawn`. Without the callback the OS thread that runs
    /// `run_event_consumer` is never spawned (LIVE-AUTH-WATCHER-EVENT-
    /// CONSUMER-SPAWN, 2026-04-27).
    ///
    /// `thread_handle_slot` is populated by the watcher every time the
    /// spawner returns `Ok(handle)`; the engine-wide shutdown sequence
    /// reads it to join the OS thread cleanly.
    ///
    /// Wraps [`Self::with_params`] for the timer + backoff knobs.
    ///
    /// 帶 `LivePipelineSpawner` callback 構造 watcher，讓 watcher 驅動
    /// **完整**的 Live 啟動路徑 — 不僅 `slot_op.try_spawn`。沒有 callback
    /// 時 `run_event_consumer` 的 OS 線程從未被 spawn（2026-04-27 修復）。
    ///
    /// `thread_handle_slot` 由 watcher 在 spawner 回 `Ok(handle)` 後寫入；
    /// engine-wide shutdown 序列讀取並 join OS 線程。
    ///
    /// 包覆 [`Self::with_params`] 提供 timer + backoff 旋鈕。
    #[allow(clippy::too_many_arguments)]
    #[allow(dead_code)] // Public API: prod uses `from_parts` (two-stage); kept as a one-shot convenience constructor
    pub fn with_pipeline_spawner(
        slot_op: Arc<dyn SpawnOp>,
        config: Arc<ConfigManager>,
        env: BybitEnvironment,
        engine_shutdown: CancellationToken,
        pipeline_spawner: LivePipelineSpawner,
        thread_handle_slot: LiveThreadHandleSlot,
    ) -> (Self, IpcTriggerHandle) {
        let (mut w, h) = Self::with_params(
            slot_op,
            config,
            env,
            engine_shutdown,
            DEFAULT_POLL_INTERVAL,
            DEFAULT_BACKOFF_BASE,
            DEFAULT_BACKOFF_MAX,
        );
        w.pipeline_spawner = Some(pipeline_spawner);
        w.thread_handle_slot = Some(thread_handle_slot);
        (w, h)
    }

    /// 2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN: pre-create the
    /// IPC trigger handle so `main.rs` can wire the IPC server before all
    /// the Arc dependencies needed by the spawner closure (writers,
    /// instruments, etc.) are constructed. Returns the trigger handle
    /// + the matching receiver to be threaded into a later
    /// [`Self::from_parts`] call.
    ///
    /// Without this two-stage construction, watcher creation must happen
    /// before IPC server detaches (so `set_live_auth_recheck_sender` can
    /// land before `ipc_server.run()` accepts connections), but the
    /// spawner closure can only be built after writers / db pool / etc.
    /// have been created — which is post-IPC. The two-stage path
    /// resolves the chicken-and-egg.
    ///
    /// 2026-04-27 修復：分兩階段構造 watcher。先建 IPC trigger handle 讓
    /// `main.rs` 在 IPC server 接受連線前接線；spawner closure 等待 writers /
    /// db_pool / 等等構造完才能組裝。後階段透過 [`Self::from_parts`] 完成。
    pub fn pre_create_trigger() -> (IpcTriggerHandle, mpsc::Receiver<()>) {
        let (tx, rx) = mpsc::channel::<()>(IPC_TRIGGER_CAPACITY);
        (IpcTriggerHandle { tx }, rx)
    }

    /// 2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN: assemble a fully-
    /// configured watcher from a previously-extracted IPC trigger receiver
    /// (see [`Self::pre_create_trigger`]) plus the spawner callback,
    /// shared thread-handle slot, and the dynamic live cmd/event sender
    /// slots so that teardown can clear them (BLOCKER-2).
    ///
    /// `live_cmd_slot` and `live_event_slot` are cleared during
    /// [`decide_once`]'s teardown arm so the governance broadcast loop
    /// (`set_system_mode`) and the fan-out loop do not deliver commands /
    /// ticks to a dead pipeline after teardown. Without clearing, stale
    /// senders accumulate until the next respawn overwrites them, causing
    /// silent command loss in the ~seconds between teardown and respawn.
    ///
    /// 2026-04-27 修復：搭配 [`Self::pre_create_trigger`] 的後階段構造。
    /// 接 receiver + spawner closure + 共享 thread-handle slot +
    /// live_cmd_slot / live_event_slot（teardown 時清空，BLOCKER-2）。
    /// teardown arm 清空兩個 slot，防止 governance broadcast 迴圈和
    /// fan-out 在 teardown 後仍往死管線投命令 / tick。
    /// `main.rs` 在 writers / Arc bundle 就緒後使用。
    #[allow(clippy::too_many_arguments)]
    pub fn from_parts(
        slot_op: Arc<dyn SpawnOp>,
        config: Arc<ConfigManager>,
        env: BybitEnvironment,
        engine_shutdown: CancellationToken,
        ipc_trigger: mpsc::Receiver<()>,
        pipeline_spawner: Option<LivePipelineSpawner>,
        thread_handle_slot: Option<LiveThreadHandleSlot>,
        live_cmd_slot: Option<LiveCmdSenderSlot>,
        live_event_slot: Option<LiveEventSenderSlot>,
    ) -> Self {
        Self {
            slot_op,
            config,
            env,
            poll_interval: DEFAULT_POLL_INTERVAL,
            engine_shutdown,
            backoff: SpawnBackoff::new(DEFAULT_BACKOFF_BASE, DEFAULT_BACKOFF_MAX),
            ipc_trigger,
            pipeline_spawner,
            thread_handle_slot,
            live_cmd_slot,
            live_event_slot,
        }
    }

    /// Drive the state machine until `engine_shutdown` fires. This is
    /// `async` and expects to be `tokio::spawn`'d by `main.rs`.
    ///
    /// 驅動狀態機直到 `engine_shutdown` 觸發。`async`，預期由 `main.rs`
    /// `tokio::spawn`。
    pub async fn run(mut self) {
        info!(
            env = ?self.env,
            poll_interval_secs = self.poll_interval.as_secs(),
            has_pipeline_spawner = self.pipeline_spawner.is_some(),
            "LiveAuthWatcher started / Live 授權 watcher 已啟動"
        );

        // 2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN: drive one
        // immediate decision cycle on entry so a Live boot with valid
        // authorization spawns the pipeline without waiting for the first
        // 5s poll tick. Without this fast-path, the 8-day silent regression
        // would persist for the first 5s after engine restart even after
        // the fix.
        // 啟動時立即跑一次決策，讓有效授權的 Live boot 不必等首個 5s 輪詢。
        // 否則修復後 engine 重啟仍會殘留 5s 死期。
        self.decide_once().await;

        loop {
            // Wait for either the engine to shut down, an IPC trigger to
            // fire, or the poll interval to elapse. select! gives us the
            // canonical "fast-path IPC + fallback poll + shutdown" story
            // without needing a dedicated ticker struct.
            //
            // 等待三者其一：引擎關機、IPC 觸發、輪詢間隔到。select! 提供
            // 標準「快路徑 IPC + 慢路徑輪詢 + 關機」語意，不需另起 ticker。
            tokio::select! {
                _ = self.engine_shutdown.cancelled() => {
                    info!(
                        "LiveAuthWatcher stopped (engine shutdown) / \
                         Live 授權 watcher 已停止（引擎關閉）"
                    );
                    return;
                }
                trigger = self.ipc_trigger.recv() => {
                    match trigger {
                        Some(()) => {
                            debug!(
                                "LiveAuthWatcher: IPC trigger received, rechecking auth \
                                 / 收到 IPC 觸發，立即重檢授權"
                            );
                        }
                        None => {
                            // All senders dropped. This is an unusual state — the
                            // IPC handler should hold a Sender clone for the
                            // engine lifetime. Treat as "IPC fast-path disabled"
                            // and fall back to pure polling: continue the loop
                            // but only the timer arm will fire now.
                            //
                            // 所有 sender 被 drop。異常狀態 — IPC handler 應在
                            // 引擎生命週期內持有 clone。視為「IPC 快路徑失能」並
                            // 退回純輪詢：繼續 loop，之後只有 timer 分支會觸發。
                            warn!(
                                "LiveAuthWatcher: IPC trigger channel closed — \
                                 continuing with poll-only / IPC 觸發通道關閉，改為純輪詢"
                            );
                            // Fall through to a pure poll loop below so we
                            // still drive respawn/teardown on schedule.
                            self.run_poll_only().await;
                            return;
                        }
                    }
                }
                _ = tokio::time::sleep(self.poll_interval) => {
                    debug!(
                        "LiveAuthWatcher: poll tick / 輪詢到期"
                    );
                }
            }

            self.decide_once().await;
        }
    }

    /// Fallback loop used after the IPC trigger channel closes unexpectedly.
    /// Pure polling, no fast-path wake-up. Runs until engine shutdown.
    ///
    /// IPC 觸發通道異常關閉後的備援 loop。純輪詢，無快路徑喚醒。跑到引擎
    /// 關機。
    async fn run_poll_only(mut self) {
        loop {
            tokio::select! {
                _ = self.engine_shutdown.cancelled() => {
                    info!(
                        "LiveAuthWatcher (poll-only fallback) stopped (engine shutdown) \
                         / Live 授權 watcher（純輪詢備援）已停止（引擎關閉）"
                    );
                    return;
                }
                _ = tokio::time::sleep(self.poll_interval) => {}
            }
            self.decide_once().await;
        }
    }

    /// One decision cycle: check current auth, inspect slot state, and
    /// either respawn (gated by backoff), teardown (always immediate),
    /// or idle. Extracted so the timer + IPC arms both share the same
    /// body.
    ///
    /// 單次決策：檢查當前授權 + 槽位狀態，選 respawn（經退避閘）、
    /// teardown（立即）、或 idle。抽出共用 timer + IPC 兩個分支。
    async fn decide_once(&mut self) {
        let current_auth = load_and_verify(self.env);
        let slot_spawned = self.slot_op.is_spawned();

        match (slot_spawned, current_auth) {
            // Both down → idle, waiting for operator to renew.
            // 兩者皆 down → idle，等 operator renew。
            (false, Err(e)) => {
                debug!(
                    error_kind = auth_error_kind(&e),
                    error = %e,
                    "LiveAuthWatcher: slot Empty + auth invalid → idle \
                     / 槽空 + 授權無效 → idle"
                );
            }
            // Both up → happy path, log at debug.
            // 兩者皆上 → 快樂路徑，debug log。
            (true, Ok(auth)) => {
                debug!(
                    tier = %auth.tier,
                    operator_id = %auth.operator_id,
                    expires_at_ms = auth.expires_at_ms,
                    "LiveAuthWatcher: slot Spawned + auth valid → no-op \
                     / 槽 Spawned + 授權有效 → 無事"
                );
            }
            // Auth valid, slot Empty → try respawn.
            // 授權有效，槽空 → 嘗試 respawn。
            (false, Ok(auth)) => {
                if !self.backoff.is_ready() {
                    debug!(
                        tier = %auth.tier,
                        "LiveAuthWatcher: respawn gated by backoff (recent failure) \
                         / respawn 被退避閘擋住（近期失敗）"
                    );
                    return;
                }
                let cfg_snapshot = self.config.get();
                let spawn_cfg = SpawnConfig {
                    kind: SlotKind::Live,
                    env: self.env,
                    parent_shutdown_token: self.engine_shutdown.clone(),
                    cfg_snapshot: &cfg_snapshot,
                };
                match self.slot_op.try_spawn(&spawn_cfg).await {
                    Ok(Some(spawn_output)) => {
                        // 2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN:
                        // The slot has spawned WS supervisor / listener /
                        // balance-refresh tasks. Now invoke the optional
                        // pipeline spawner callback to spawn the OS thread
                        // running `run_event_consumer` (which is the
                        // producer of state_writer / snapshot_writer /
                        // trading.fills writer). Without this callback the
                        // pipeline is half-spawned: WS reads land in a
                        // channel nobody consumes, snapshots never refresh.
                        //
                        // 2026-04-27 修復：slot 已 spawn WS supervisor /
                        // listener / 餘額刷新任務。現在呼叫可選 pipeline
                        // spawner callback 產出跑 `run_event_consumer` 的
                        // OS 線程（state_writer / snapshot_writer /
                        // trading.fills 寫入器的生產者）。沒有此 callback
                        // 時管線是半成品 — WS 收到的資料進無人消費的通道，
                        // snapshot 永不更新。
                        match (&self.pipeline_spawner, &self.thread_handle_slot) {
                            (Some(spawner), Some(handle_slot)) => {
                                match spawner(spawn_output) {
                                    Ok(thread_handle) => {
                                        // Capture handle into shared slot
                                        // for shutdown sequence to join.
                                        // 寫入 shutdown 序列要 join 的 slot。
                                        *handle_slot.lock() = Some(thread_handle);
                                        self.backoff.reset();
                                        info!(
                                            tier = %auth.tier,
                                            operator_id = %auth.operator_id,
                                            expires_at_ms = auth.expires_at_ms,
                                            "LiveAuthWatcher: Live slot + event_consumer thread respawned \
                                             after auth became valid \
                                             / 授權恢復，Live 槽位 + event_consumer 線程已 respawn"
                                        );
                                    }
                                    Err(reason) => {
                                        // Spawner refused. The slot is
                                        // currently Spawned (slot_op did
                                        // accept the spawn) but the OS
                                        // thread is missing — engage backoff
                                        // and tear down the slot to avoid
                                        // a half-spawned state. The next
                                        // decide_once will see slot Empty
                                        // and try again under backoff.
                                        //
                                        // Spawner 拒絕。slot 已 Spawned 但
                                        // OS 線程缺失 — 啟動退避並 teardown
                                        // 槽位避免半成品狀態。下次
                                        // decide_once 看到 Empty 會於退避
                                        // 後重試。
                                        self.backoff.record_failure();
                                        warn!(
                                            reason = %reason,
                                            delay_until_ready_ms = self.backoff.current_delay_ms(),
                                            "LiveAuthWatcher: pipeline spawner refused after slot spawn \
                                             — tearing down slot to avoid half-spawned state \
                                             / pipeline spawner 拒絕，teardown 避免半成品"
                                        );
                                        if let Err(te) = self.slot_op.teardown().await {
                                            warn!(
                                                error = %te,
                                                "LiveAuthWatcher: teardown after spawner refusal returned \
                                                 error (fail-soft) / spawner 拒絕後 teardown 出錯（fail-soft）"
                                            );
                                        }
                                    }
                                }
                            }
                            (None, _) | (_, None) => {
                                // No spawner injected — fall back to Phase 3
                                // behaviour (slot try_spawn alone). This is
                                // the unit-test path and stays correct.
                                // 無 spawner — 退回 Phase 3 行為（單測路徑）。
                                self.backoff.reset();
                                info!(
                                    tier = %auth.tier,
                                    operator_id = %auth.operator_id,
                                    expires_at_ms = auth.expires_at_ms,
                                    "LiveAuthWatcher: Live slot respawned after auth became valid \
                                     (no pipeline spawner injected) \
                                     / 授權恢復，Live 槽位已 respawn（未注入 spawner）"
                                );
                            }
                        }
                    }
                    Ok(None) => {
                        // `build_exchange_pipeline` returned None — the inner
                        // call already structured-logged the reason (missing
                        // credentials, REST init failure, etc.). Treat as a
                        // spawn failure for backoff purposes so we don't
                        // hammer Bybit at 5s cadence when the real problem
                        // is lower-level.
                        //
                        // `build_exchange_pipeline` 回 None — 內部已 log
                        // 原因。對退避邏輯視為 spawn 失敗，避免在較底層問題
                        // 存在時以 5s 頻率敲 Bybit。
                        self.backoff.record_failure();
                        warn!(
                            delay_until_ready_ms = self.backoff.current_delay_ms(),
                            "LiveAuthWatcher: respawn attempt failed (build returned None), \
                             backoff engaged / respawn 失敗（build 回 None），退避閘啟動"
                        );
                    }
                    Err(SpawnError::AlreadySpawned) => {
                        // Race: between our is_spawned() check and try_spawn()
                        // a concurrent caller spawned the slot. is_spawned()
                        // will be true next tick; treat as success for backoff.
                        //
                        // 競爭：is_spawned() 與 try_spawn() 之間有並發呼叫
                        // 已 spawn。下次 tick 即 true；對退避視為成功。
                        debug!(
                            "LiveAuthWatcher: try_spawn raced with another spawner \
                             (AlreadySpawned) — treating as success / try_spawn 與他者
                             並發 (AlreadySpawned) — 視為成功"
                        );
                        self.backoff.reset();
                    }
                    Err(SpawnError::NotAvailable) => {
                        // Phase 2 contract: NotAvailable ≡ None from
                        // build_exchange_pipeline. Keep identical behaviour.
                        // Phase 2 契約：NotAvailable ≡ build 的 None，同處理。
                        self.backoff.record_failure();
                        warn!(
                            delay_until_ready_ms = self.backoff.current_delay_ms(),
                            "LiveAuthWatcher: respawn attempt NotAvailable, backoff engaged \
                             / respawn NotAvailable，退避閘啟動"
                        );
                    }
                }
            }
            // Auth invalid, slot Spawned → teardown immediately (never gated).
            // 授權無效，槽 Spawned → 立即 teardown（絕不經退避閘）。
            (true, Err(e)) => {
                warn!(
                    env = ?self.env,
                    error_kind = auth_error_kind(&e),
                    error = %e,
                    "LIVE AUTHORIZATION INVALIDATED MID-SESSION — tearing down Live slot \
                     only (demo/paper continue). Operator: renew via \
                     /api/v1/live/auth/renew. / Live 授權中途失效 — 僅拆 Live 槽位 \
                     （demo/paper 繼續）。"
                );
                if let Err(te) = self.slot_op.teardown().await {
                    warn!(
                        error = %te,
                        "LiveAuthWatcher: teardown returned error (fail-soft) \
                         / teardown 回錯（fail-soft）"
                    );
                }
                // 2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN: take
                // the previously-stored OS thread handle and join it on a
                // detached blocking task so we don't block the watcher
                // event loop. The slot teardown above already cancelled
                // the slot-scoped child token, which the
                // `run_event_consumer` main loop watches via
                // `live_deps.cancel`, so the thread will exit shortly.
                // We must not skip the join — orphaning a Live OS thread
                // means a future respawn could end up with two OS threads
                // both owning a `live_rt`.
                //
                // 2026-04-27 修復：取出先前存的 OS 線程 handle 並於分離 blocking
                // 任務上 join，避免阻塞 watcher event loop。slot teardown 已取消
                // 子 token，`run_event_consumer` 主迴圈經 `live_deps.cancel`
                // 監看會盡快退出。不能跳過 join — 否則 Live OS 線程變孤兒，
                // 下次 respawn 可能造成兩條都擁有 `live_rt` 的 OS 線程並存。
                if let Some(slot) = &self.thread_handle_slot {
                    let maybe_handle = slot.lock().take();
                    if let Some(h) = maybe_handle {
                        tokio::task::spawn_blocking(move || {
                            if let Err(e) = h.join() {
                                let msg = e
                                    .downcast_ref::<&str>()
                                    .copied()
                                    .or_else(|| e.downcast_ref::<String>().map(|s| s.as_str()))
                                    .unwrap_or("unknown panic");
                                warn!(
                                    panic = msg,
                                    "LiveAuthWatcher: prior Live OS thread join panicked (fail-soft) \
                                     / 先前 Live OS 線程 join panic（fail-soft）"
                                );
                            }
                        });
                    }
                }
                // BLOCKER-2 (2026-04-27): clear the live cmd and event sender
                // slots after teardown so:
                // (a) `set_system_mode` governance broadcast does not
                //     fire-and-forget into a dead live tx after teardown — the
                //     Sender is now `None` so `live_snapshot()` returns None
                //     and the broadcast silently skips live (expected behaviour
                //     during the gap between teardown and respawn).
                // (b) fan-out no longer delivers ticks to the orphaned receiver
                //     channel — the live event slot is None until the next
                //     successful respawn populates it again.
                //
                // Invariant / 不變量: both slots are cleared atomically under
                // the parking_lot write lock (~1 µs). The spawner closure
                // overwrites them on the next successful respawn so no manual
                // "restore" is needed.
                //
                // BLOCKER-2（2026-04-27）：teardown 後清空 live cmd + event slot：
                // (a) governance broadcast `set_system_mode` 不再往死管線投命令
                //     — `live_snapshot()` 回 None，broadcast 靜默跳過 live（符合
                //     teardown 與 respawn 之間的預期行為）。
                // (b) fan-out 不再往孤兒 receiver 投 tick — event slot 為 None
                //     直到下次 respawn 填入。
                //
                // 不變量：兩個 slot 各自在 parking_lot 寫鎖下原子清空（~1 µs）。
                // spawner closure 下次成功 respawn 時覆寫，無需手動「恢復」。
                if let Some(cmd_slot) = &self.live_cmd_slot {
                    *cmd_slot.write() = None;
                    debug!(
                        "LiveAuthWatcher: live_cmd_slot cleared after teardown \
                         / teardown 後已清空 live_cmd_slot"
                    );
                }
                if let Some(event_slot) = &self.live_event_slot {
                    *event_slot.write() = None;
                    debug!(
                        "LiveAuthWatcher: live_event_slot cleared after teardown \
                         / teardown 後已清空 live_event_slot"
                    );
                }

                // Reset backoff so the next respawn attempt (after operator
                // renews) is not gated by failures from a previous cycle.
                // 重設退避，讓 operator renew 後 respawn 不受前一週期失敗影響。
                self.backoff.reset();
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Tests / 測試
// BLOCKER-1 (E2 round-2, 2026-04-27): tests extracted to
// `live_auth_watcher_tests.rs` to bring this file under the 1200-line
// hard cap (CLAUDE.md §九). The #[cfg(test)] module declaration below
// re-exports the file so `cargo test --bin openclaw-engine` sees all tests.
//
// BLOCKER-1（E2 round-2，2026-04-27）：測試抽到 `live_auth_watcher_tests.rs`，
// 讓本檔回到 1200 行硬上限以內（CLAUDE.md §九）。下方 #[cfg(test)] mod
// 宣告讓 `cargo test --bin openclaw-engine` 仍能看到所有測試。
// ---------------------------------------------------------------------------

#[cfg(test)]
#[path = "live_auth_watcher_tests.rs"]
mod tests;

