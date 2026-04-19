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

use crate::pipeline_slot::{PipelineSlot, SlotKind, SpawnConfig, SpawnError, TeardownError};
use crate::spawn_backoff::SpawnBackoff;
use async_trait::async_trait;
use openclaw_engine::bybit_rest_client::BybitEnvironment;
use openclaw_engine::config::ConfigManager;
use openclaw_engine::live_authorization::{auth_error_kind, load_and_verify};
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
/// Watcher 所需的槽位操作（spawn / teardown / is_spawned）。抽成 trait
/// 讓單測注入計數與固定回應的 mock，不必啟動真實交易所管線（需 REST/WS
/// 客戶端與 Bybit endpoint）。生產實作在下方委派 `PipelineSlot`。
#[async_trait]
pub trait SpawnOp: Send + Sync {
    /// True iff the slot is currently `Spawned`.
    /// 槽位當前是否為 `Spawned`。
    fn is_spawned(&self) -> bool;

    /// Attempt to spawn the slot. Returns `Ok(true)` on success,
    /// `Ok(false)` on `build_exchange_pipeline` returning None (structured
    /// reason already logged inside), `Err` on programming errors
    /// (`AlreadySpawned`).
    ///
    /// 嘗試啟動槽位。成功 `Ok(true)`；`build_exchange_pipeline` 回 None 時
    /// `Ok(false)`（原因已結構化 log）；程式錯誤（`AlreadySpawned`）`Err`。
    async fn try_spawn(
        &self,
        cfg: &SpawnConfig<'_>,
    ) -> Result<bool, SpawnError>;

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
    ) -> Result<bool, SpawnError> {
        match PipelineSlot::try_spawn(self, cfg).await? {
            Some(_) => Ok(true),
            None => Ok(false),
        }
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

/// Live authorization watcher.
///
/// Holds the Live slot, the engine config manager (for fresh
/// `EngineBootstrap` snapshots on each respawn), the environment label,
/// the engine-wide shutdown token (for clean exit on SIGTERM), a
/// `SpawnBackoff` for spawn-attempt rate limiting, and an IPC trigger
/// receiver.
///
/// Live 授權 watcher。持有 Live 槽位、引擎配置管理器（每次 respawn
/// 取新 `EngineBootstrap` 快照）、環境標籤、引擎級 shutdown token
/// （SIGTERM 乾淨退出）、`SpawnBackoff`（限速 spawn 嘗試）、IPC
/// 觸發 receiver。
pub struct LiveAuthWatcher {
    slot_op: Arc<dyn SpawnOp>,
    config: Arc<ConfigManager>,
    env: BybitEnvironment,
    poll_interval: Duration,
    engine_shutdown: CancellationToken,
    backoff: SpawnBackoff,
    ipc_trigger: mpsc::Receiver<()>,
}

impl LiveAuthWatcher {
    /// Construct the watcher. Returns `(Self, IpcTriggerHandle)`; the
    /// handle is cloned into the IPC dispatcher.
    ///
    /// `config` is an `Arc<ConfigManager>` so the watcher can pull a
    /// fresh `EngineBootstrap` snapshot on every respawn attempt
    /// (hot-reload propagates into Live respawns).
    ///
    /// 建構 watcher。回傳 `(Self, IpcTriggerHandle)`；handle 由 IPC
    /// dispatcher clone。`config` 為 `Arc<ConfigManager>`，每次
    /// respawn 抓新 `EngineBootstrap` 快照（hot-reload 於下次 Live
    /// respawn 生效）。
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
            },
            IpcTriggerHandle { tx },
        )
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
            "LiveAuthWatcher started / Live 授權 watcher 已啟動"
        );

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
                    Ok(true) => {
                        self.backoff.reset();
                        info!(
                            tier = %auth.tier,
                            operator_id = %auth.operator_id,
                            expires_at_ms = auth.expires_at_ms,
                            "LiveAuthWatcher: Live slot respawned after auth became valid \
                             / 授權恢復，Live 槽位已 respawn"
                        );
                    }
                    Ok(false) => {
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
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use async_trait::async_trait;
    use openclaw_engine::live_authorization::{
        compute_signature, LiveAuthorization, SCHEMA_VERSION,
    };
    use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
    use std::sync::Mutex as StdMutex;

    const TEST_SECRET: &str = "phase3-test-ipc-secret-do-not-ship";

    // ── mock SpawnOp ──────────────────────────────────────────────────
    // Counts calls, flips is_spawned state, and returns user-scripted
    // outcomes. All methods are `Send + Sync` since the watcher's
    // `Arc<dyn SpawnOp>` field is erased behind a trait object.
    // 計 call 數、切換 is_spawned 狀態、回指定結果。所有方法 Send+Sync，
    // 配合 watcher 內的 `Arc<dyn SpawnOp>` trait 物件。

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    #[allow(dead_code)] // NotAvailable reserved for future scenarios; kept for symmetry.
    enum ScriptedSpawn {
        Ok,
        BuildReturnedNone,
        NotAvailable,
        AlreadySpawned,
    }

    struct MockSlotOp {
        spawned: AtomicBool,
        spawn_calls: AtomicUsize,
        teardown_calls: AtomicUsize,
        /// Scripted sequence consumed front-to-back on each spawn; once
        /// exhausted, the last entry repeats.
        /// 每次 spawn 由前往後消耗；耗盡後最後一項重複。
        script: StdMutex<Vec<ScriptedSpawn>>,
    }

    impl MockSlotOp {
        fn new(script: Vec<ScriptedSpawn>) -> Arc<Self> {
            Arc::new(Self {
                spawned: AtomicBool::new(false),
                spawn_calls: AtomicUsize::new(0),
                teardown_calls: AtomicUsize::new(0),
                script: StdMutex::new(script),
            })
        }
        fn next_outcome(&self) -> ScriptedSpawn {
            let mut guard = self.script.lock().unwrap();
            if guard.len() > 1 {
                guard.remove(0)
            } else {
                guard.first().copied().unwrap_or(ScriptedSpawn::Ok)
            }
        }
    }

    #[async_trait]
    impl SpawnOp for MockSlotOp {
        fn is_spawned(&self) -> bool {
            self.spawned.load(Ordering::SeqCst)
        }
        async fn try_spawn(
            &self,
            _cfg: &SpawnConfig<'_>,
        ) -> Result<bool, SpawnError> {
            self.spawn_calls.fetch_add(1, Ordering::SeqCst);
            match self.next_outcome() {
                ScriptedSpawn::Ok => {
                    self.spawned.store(true, Ordering::SeqCst);
                    Ok(true)
                }
                ScriptedSpawn::BuildReturnedNone => Ok(false),
                ScriptedSpawn::NotAvailable => Err(SpawnError::NotAvailable),
                ScriptedSpawn::AlreadySpawned => Err(SpawnError::AlreadySpawned),
            }
        }
        async fn teardown(&self) -> Result<(), TeardownError> {
            self.teardown_calls.fetch_add(1, Ordering::SeqCst);
            self.spawned.store(false, Ordering::SeqCst);
            Ok(())
        }
    }

    // ── auth file helper ─────────────────────────────────────────────
    fn fresh_auth(now_ms: u64, ttl_ms: u64) -> LiveAuthorization {
        let mut auth = LiveAuthorization {
            version: SCHEMA_VERSION,
            tier: "T0_ENTRY".into(),
            issued_at_ms: now_ms,
            expires_at_ms: now_ms + ttl_ms,
            operator_id: "watcher_test".into(),
            env_allowed: vec!["live_demo".into()],
            sig: String::new(),
        };
        auth.sig = compute_signature(&auth, TEST_SECRET);
        auth
    }

    /// Configure the process-wide env vars so `load_and_verify` reads
    /// the authorization file under `secrets_dir/live/authorization.json`.
    /// This is a test-only indirect — production reads the same env vars.
    ///
    /// **Env var contention**: many tests mutate `OPENCLAW_SECRETS_DIR` /
    /// `OPENCLAW_IPC_SECRET`; running watcher tests together (or with
    /// other live_authorization tests) under a single test binary risks
    /// interleaving. We serialize watcher tests via a mutex below.
    /// 許多測試改 `OPENCLAW_SECRETS_DIR` / `OPENCLAW_IPC_SECRET`；
    /// 同一 test binary 並行會交錯。下方 mutex 串行。
    fn set_test_env(secrets_dir: &std::path::Path) {
        std::env::set_var("OPENCLAW_SECRETS_DIR", secrets_dir);
        std::env::set_var("OPENCLAW_IPC_SECRET", TEST_SECRET);
    }
    fn clear_test_env() {
        std::env::remove_var("OPENCLAW_SECRETS_DIR");
        std::env::remove_var("OPENCLAW_IPC_SECRET");
    }

    // Serialize all watcher tests to avoid env-var contention between
    // parallel tests in the same binary.
    // 串行化所有 watcher 測試，避免同 binary 內並行爭 env var。
    static ENV_GUARD: StdMutex<()> = StdMutex::new(());

    fn drop_auth_file(secrets_dir: &std::path::Path, auth: &LiveAuthorization) {
        let live_dir = secrets_dir.join("live");
        std::fs::create_dir_all(&live_dir).unwrap();
        let path = live_dir.join("authorization.json");
        std::fs::write(path, serde_json::to_string_pretty(auth).unwrap()).unwrap();
    }

    fn remove_auth_file(secrets_dir: &std::path::Path) {
        let path = secrets_dir.join("live").join("authorization.json");
        let _ = std::fs::remove_file(path);
    }

    // Minimal ConfigManager for tests — just loads default EngineBootstrap.
    // 測試用最小 ConfigManager — 只載入預設 EngineBootstrap。
    fn test_config() -> Arc<ConfigManager> {
        // ConfigManager::load(None) falls back to default on missing file.
        Arc::new(ConfigManager::load(None).expect("load config (defaults ok)"))
    }

    fn now_ms() -> u64 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0)
    }

    // ── tests ────────────────────────────────────────────────────────

    #[tokio::test]
    async fn watcher_respawns_when_auth_becomes_valid() {
        let _guard = ENV_GUARD.lock().unwrap_or_else(|e| e.into_inner());
        let tmp = tempfile::tempdir().unwrap();
        set_test_env(tmp.path());
        let shutdown = CancellationToken::new();

        let mock = MockSlotOp::new(vec![ScriptedSpawn::Ok]);
        let (watcher, handle) = LiveAuthWatcher::with_params(
            Arc::clone(&mock) as Arc<dyn SpawnOp>,
            test_config(),
            BybitEnvironment::LiveDemo,
            shutdown.clone(),
            Duration::from_millis(50), // short poll for fast test
            Duration::from_millis(10),
            Duration::from_millis(100),
        );

        let watcher_task = tokio::spawn(watcher.run());

        // Slot is Empty and no auth exists — watcher stays idle.
        tokio::time::sleep(Duration::from_millis(80)).await;
        assert_eq!(mock.spawn_calls.load(Ordering::SeqCst), 0);

        // Drop a valid authorization file and poke the IPC trigger.
        let auth = fresh_auth(now_ms(), 3600_000);
        drop_auth_file(tmp.path(), &auth);
        let _ = handle.trigger();

        // Watcher should respawn on the trigger (fast-path, <50ms).
        // watcher 應以 IPC 快路徑 respawn（<50ms）。
        tokio::time::timeout(Duration::from_secs(2), async {
            while mock.spawn_calls.load(Ordering::SeqCst) == 0 {
                tokio::time::sleep(Duration::from_millis(5)).await;
            }
        })
        .await
        .expect("spawn must be attempted after trigger");

        assert!(mock.is_spawned(), "slot must be Spawned after successful spawn");

        shutdown.cancel();
        let _ = watcher_task.await;
        clear_test_env();
        remove_auth_file(tmp.path());
    }

    #[tokio::test]
    async fn watcher_tears_down_when_auth_invalidates() {
        let _guard = ENV_GUARD.lock().unwrap_or_else(|e| e.into_inner());
        let tmp = tempfile::tempdir().unwrap();
        set_test_env(tmp.path());
        let shutdown = CancellationToken::new();

        // Seed: valid auth on disk, slot already Spawned (simulate post-renewal).
        let auth = fresh_auth(now_ms(), 3600_000);
        drop_auth_file(tmp.path(), &auth);
        let mock = MockSlotOp::new(vec![ScriptedSpawn::Ok]);
        mock.spawned.store(true, Ordering::SeqCst);

        let (watcher, handle) = LiveAuthWatcher::with_params(
            Arc::clone(&mock) as Arc<dyn SpawnOp>,
            test_config(),
            BybitEnvironment::LiveDemo,
            shutdown.clone(),
            Duration::from_millis(50),
            Duration::from_millis(10),
            Duration::from_millis(100),
        );
        let watcher_task = tokio::spawn(watcher.run());

        // Yield so the watcher enters its loop. With valid auth + Spawned slot
        // this is the happy path; no actions expected.
        // 讓 watcher 進 loop。有效授權 + Spawned = 快樂路徑，無動作。
        tokio::time::sleep(Duration::from_millis(80)).await;
        assert_eq!(mock.teardown_calls.load(Ordering::SeqCst), 0);

        // Remove auth file (simulates operator revoke) + trigger.
        remove_auth_file(tmp.path());
        let _ = handle.trigger();

        tokio::time::timeout(Duration::from_secs(2), async {
            while mock.teardown_calls.load(Ordering::SeqCst) == 0 {
                tokio::time::sleep(Duration::from_millis(5)).await;
            }
        })
        .await
        .expect("teardown must be called after auth invalidates");

        assert!(!mock.is_spawned(), "slot must be Empty after teardown");

        shutdown.cancel();
        let _ = watcher_task.await;
        clear_test_env();
    }

    #[tokio::test]
    async fn watcher_respects_backoff_on_spawn_failure() {
        let _guard = ENV_GUARD.lock().unwrap_or_else(|e| e.into_inner());
        let tmp = tempfile::tempdir().unwrap();
        set_test_env(tmp.path());
        let shutdown = CancellationToken::new();

        // Auth valid, every spawn fails → backoff should throttle.
        // 授權有效，但每次 spawn 失敗 → 退避節流。
        let auth = fresh_auth(now_ms(), 3600_000);
        drop_auth_file(tmp.path(), &auth);
        let mock = MockSlotOp::new(vec![ScriptedSpawn::BuildReturnedNone]);

        // Poll every 10ms, base backoff 100ms, max 500ms. In 250ms we
        // expect 1 spawn (tick 0) + maybe 1 more after 100ms backoff
        // expires (tick ~100+) + another after another 200ms doubling
        // (tick ~300+). Certainly NOT 25 spawns (one per 10ms tick).
        // 10ms 一 tick，退避 base=100ms / max=500ms；250ms 內預期 1~2 次
        // spawn 嘗試，絕非 25 次（每 tick 一次）。
        let (watcher, handle) = LiveAuthWatcher::with_params(
            Arc::clone(&mock) as Arc<dyn SpawnOp>,
            test_config(),
            BybitEnvironment::LiveDemo,
            shutdown.clone(),
            Duration::from_millis(10),
            Duration::from_millis(100),
            Duration::from_millis(500),
        );
        let watcher_task = tokio::spawn(watcher.run());

        // Kick with IPC trigger + let the watcher ride for 250ms.
        let _ = handle.trigger();
        tokio::time::sleep(Duration::from_millis(250)).await;

        let calls = mock.spawn_calls.load(Ordering::SeqCst);
        assert!(
            calls >= 1,
            "watcher must attempt at least one spawn; got {calls}"
        );
        assert!(
            calls <= 5,
            "backoff must throttle spawn attempts — got {calls} in 250ms \
             (unthrottled would be ~25)"
        );

        shutdown.cancel();
        let _ = watcher_task.await;
        clear_test_env();
        remove_auth_file(tmp.path());
    }

    #[tokio::test]
    async fn watcher_breaks_on_engine_shutdown() {
        let _guard = ENV_GUARD.lock().unwrap_or_else(|e| e.into_inner());
        let tmp = tempfile::tempdir().unwrap();
        set_test_env(tmp.path());
        let shutdown = CancellationToken::new();

        let mock = MockSlotOp::new(vec![ScriptedSpawn::Ok]);
        let (watcher, _handle) = LiveAuthWatcher::with_params(
            Arc::clone(&mock) as Arc<dyn SpawnOp>,
            test_config(),
            BybitEnvironment::LiveDemo,
            shutdown.clone(),
            Duration::from_secs(60), // long poll — shouldn't matter
            Duration::from_secs(1),
            Duration::from_secs(60),
        );

        let watcher_task = tokio::spawn(watcher.run());

        // Cancel immediately.
        shutdown.cancel();

        tokio::time::timeout(Duration::from_secs(2), watcher_task)
            .await
            .expect("watcher must exit within 2s after shutdown")
            .expect("watcher task must not panic");
        clear_test_env();
    }

    #[tokio::test]
    async fn ipc_trigger_coalesces_when_full() {
        // Trigger twice in a row before the watcher consumes. First send
        // must succeed, second must return Ok(false) (coalesced) — not an
        // error. This exercises the `TrySendError::Full` arm.
        // 連發兩次 trigger。第一次成功；第二次 Ok(false) 合併 — 不是錯誤。
        let _guard = ENV_GUARD.lock().unwrap_or_else(|e| e.into_inner());
        let tmp = tempfile::tempdir().unwrap();
        set_test_env(tmp.path());
        let shutdown = CancellationToken::new();
        let mock = MockSlotOp::new(vec![ScriptedSpawn::Ok]);
        // Long poll so the receiver doesn't drain before we probe.
        // 長輪詢避免 receiver 先於 probe 消耗。
        let (_watcher, handle) = LiveAuthWatcher::with_params(
            Arc::clone(&mock) as Arc<dyn SpawnOp>,
            test_config(),
            BybitEnvironment::LiveDemo,
            shutdown.clone(),
            Duration::from_secs(60),
            Duration::from_secs(1),
            Duration::from_secs(60),
        );

        let first = handle.trigger().expect("first trigger must succeed");
        assert!(first, "first trigger must be accepted");
        let second = handle.trigger().expect("second trigger must be Ok (coalesced)");
        assert!(!second, "second trigger in a row must coalesce (Ok(false))");

        clear_test_env();
    }

    #[tokio::test]
    async fn ipc_trigger_errors_when_watcher_dropped() {
        // Drop the watcher (and its receiver) — next trigger must
        // return Err(()) so callers can log loudly.
        // drop watcher/receiver — 下次 trigger 回 Err(())，讓呼叫端大聲 log。
        let _guard = ENV_GUARD.lock().unwrap_or_else(|e| e.into_inner());
        let tmp = tempfile::tempdir().unwrap();
        set_test_env(tmp.path());
        let shutdown = CancellationToken::new();
        let mock = MockSlotOp::new(vec![ScriptedSpawn::Ok]);

        let (watcher, handle) = LiveAuthWatcher::with_params(
            Arc::clone(&mock) as Arc<dyn SpawnOp>,
            test_config(),
            BybitEnvironment::LiveDemo,
            shutdown.clone(),
            Duration::from_secs(60),
            Duration::from_secs(1),
            Duration::from_secs(60),
        );
        drop(watcher);

        // After drop, the Sender can observe Closed on try_send.
        // drop 後 Sender 的 try_send 可觀察到 Closed。
        let res = handle.trigger();
        assert_eq!(res, Err(()), "trigger after watcher drop must return Err");

        clear_test_env();
    }

    #[tokio::test]
    async fn spawn_output_already_spawned_treated_as_success() {
        // Scripted AlreadySpawned should be swallowed with debug log +
        // backoff reset. No teardown should fire on this path.
        // 腳本化 AlreadySpawned 應被 debug log 吞掉、重設退避，
        // 不觸發 teardown。
        let _guard = ENV_GUARD.lock().unwrap_or_else(|e| e.into_inner());
        let tmp = tempfile::tempdir().unwrap();
        set_test_env(tmp.path());
        let shutdown = CancellationToken::new();

        let auth = fresh_auth(now_ms(), 3600_000);
        drop_auth_file(tmp.path(), &auth);

        let mock = MockSlotOp::new(vec![ScriptedSpawn::AlreadySpawned]);
        let (watcher, handle) = LiveAuthWatcher::with_params(
            Arc::clone(&mock) as Arc<dyn SpawnOp>,
            test_config(),
            BybitEnvironment::LiveDemo,
            shutdown.clone(),
            Duration::from_millis(50),
            Duration::from_millis(10),
            Duration::from_millis(100),
        );
        let watcher_task = tokio::spawn(watcher.run());

        let _ = handle.trigger();
        tokio::time::timeout(Duration::from_secs(2), async {
            while mock.spawn_calls.load(Ordering::SeqCst) == 0 {
                tokio::time::sleep(Duration::from_millis(5)).await;
            }
        })
        .await
        .expect("spawn must be attempted");

        assert_eq!(mock.teardown_calls.load(Ordering::SeqCst), 0);
        shutdown.cancel();
        let _ = watcher_task.await;
        clear_test_env();
        remove_auth_file(tmp.path());
    }
}
