//! PIPELINE-SLOT-1 Phase 2 — pipeline slot abstraction + live-scoped teardown.
//! PIPELINE-SLOT-1 Phase 2 — 管線槽位抽象 + live-scoped teardown。
//!
//! MODULE_NOTE (EN):
//!   Phase 2 wires the slot up so a revoked / expired / tampered live
//!   authorization tears down **only** the Live pipeline, leaving Demo and
//!   Paper uninterrupted. The 5-min auth re-verify loop in `main.rs`
//!   previously cancelled the engine-wide token on failure — a blunt tool
//!   that killed everything. Phase 2 swaps that for `live_slot.teardown()`,
//!   which cancels a slot-scoped child token and joins every tokio task the
//!   slot owns.
//!
//!   Token hierarchy introduced in this phase:
//!
//!     engine_shutdown_token (engine-wide `cancel`, cancelled on SIGTERM)
//!        ├── live_slot.cancel_token   (child — teardown cancels this only)
//!        ├── demo_slot.cancel_token   (child — future-proofed, never torn
//!        │                             down mid-session in Phase 2)
//!        └── paper_slot.cancel_token  (child — same as demo)
//!
//!   Cancelling a child does NOT cancel the parent (tokio-util contract),
//!   so tearing down the Live slot does not signal the engine to exit.
//!   Cancelling the parent DOES cancel all children, so SIGTERM still
//!   cascades to every slot's tasks cleanly.
//!
//!   Crash-only parity (Fix 3, 2026-04-14) is preserved: a Live **panic**
//!   on the dedicated OS thread still calls `engine_cancel.cancel()` to
//!   kill paper/demo as collateral — Phase 2 narrows only the authorization
//!   revocation path, not the panic path. Rationale: a panicked pipeline
//!   may leave shared state (positions, reconciler baselines) inconsistent;
//!   an authorization revocation is a clean operator-intent event with no
//!   such concern.
//!
//!   Phase 2 scope:
//!     * Real `PipelineSlot::teardown()` — cancels slot-scoped child token,
//!       awaits every captured tokio JoinHandle, transitions Spawned→Empty.
//!     * `build_exchange_pipeline` returns `(bindings, Vec<JoinHandle<()>>)`
//!       so the slot captures every task it spawns (ws supervisor, listener,
//!       periodic REST balance refresh). No more fire-and-forget tasks.
//!     * `SpawnConfig` now carries `parent_shutdown_token` (renamed from
//!       `cancel` for clarity); `try_spawn` derives a child token from it.
//!     * `try_spawn` returns `(bindings, slot_child_token)` so `main.rs`
//!       can route the child token into the Live OS thread's `live_cancel`
//!       (replacing the old engine-wide clone on that path).
//!
//!   Non-goals for Phase 2:
//!     * No respawn logic — once torn down, Live stays down until next full
//!       engine restart. Phase 3 adds an auth watcher to respawn on renew.
//!     * Demo / Paper are NOT torn down mid-session by any call path in
//!       Phase 2. Their slots carry child tokens only for future consistency;
//!       no `teardown()` call-site wires them.
//!
//! MODULE_NOTE (中):
//!   Phase 2 完成槽位接線：授權被撤銷 / 過期 / 篡改時**只**拆 Live 管線，
//!   Demo 與 Paper 不中斷。原 `main.rs` 的 5 分鐘重驗 loop 在失敗時取消引擎級
//!   token — 粗暴一鍋端。Phase 2 改為呼叫 `live_slot.teardown()`：只取消
//!   槽位子 token 並 join 槽位擁有的所有 tokio 任務。
//!
//!   Phase 2 導入的 token 層次：
//!
//!     engine_shutdown_token（引擎級 `cancel`，SIGTERM 觸發）
//!        ├── live_slot.cancel_token   （子 — teardown 只拆這個）
//!        ├── demo_slot.cancel_token   （子 — 為未來一致性，Phase 2 不拆）
//!        └── paper_slot.cancel_token  （子 — 同 demo）
//!
//!   取消子 token **不會**取消父 token（tokio-util 契約），所以拆 Live slot
//!   不會讓引擎退出；取消父 token 會波及所有子 token，SIGTERM 仍能乾淨連帶
//!   所有 slot 任務。
//!
//!   Crash-only 對齊（Fix 3，2026-04-14）保留：Live 在獨立 OS 線程上**panic**
//!   時仍呼叫 `engine_cancel.cancel()` 讓 paper/demo 陪葬 — Phase 2 只收窄
//!   授權撤銷路徑，不動 panic 路徑。理由：panic 管線可能讓共享狀態
//!   （倉位、對帳基線）進入不一致；授權撤銷是乾淨的 operator 意圖，沒有
//!   這層顧慮。
//!
//!   Phase 2 範圍：
//!     * 真正的 `PipelineSlot::teardown()` — 取消槽位子 token、await 所有
//!       捕獲的 tokio JoinHandle、狀態 Spawned→Empty。
//!     * `build_exchange_pipeline` 回傳 `(bindings, Vec<JoinHandle<()>>)`，
//!       槽位因此能捕獲它 spawn 的每一個任務（ws supervisor、listener、
//!       定期 REST 餘額刷新）— 不再有 fire-and-forget 任務。
//!     * `SpawnConfig` 改帶 `parent_shutdown_token`（原 `cancel` 改名以明意）；
//!       `try_spawn` 從它派生子 token。
//!     * `try_spawn` 回傳 `(bindings, slot_child_token)`，讓 `main.rs` 把
//!       子 token 送進 Live OS 線程的 `live_cancel`（取代舊的引擎級 clone）。
//!
//!   Phase 2 非目標：
//!     * 不寫 respawn — 拆完後 Live 保持 down，直到下一次整機重啟。Phase 3
//!       會補上授權 watcher 在 renew 時自動 respawn。
//!     * Phase 2 內任何呼叫路徑都不會拆 Demo / Paper。它們的槽位帶子 token
//!       僅為未來一致性，沒有任何 `teardown()` 呼叫點接線到它們。

use crate::startup::{build_exchange_pipeline, ExchangePipelineBindings};
use openclaw_engine::bybit_rest_client::BybitEnvironment;
use openclaw_engine::config::EngineBootstrap;
use openclaw_engine::tick_pipeline::PipelineKind;
use tokio::task::JoinHandle;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

/// Which logical pipeline this slot holds.
///
/// Mirrors [`PipelineKind`] semantically but kept separate so the slot type
/// can evolve (Phase 4 may add operator intent like "force-live-down") without
/// dragging [`PipelineKind`] along.
///
/// 槽位持有的邏輯管線類型。語意與 [`PipelineKind`] 對映，但刻意保持獨立，
/// 讓 slot 類型可獨立演進（Phase 4 可能加入 operator 意圖如「強制下 live」）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[allow(dead_code)] // Phase 2: Paper slot not yet wired (paper spawn still in main.rs)
pub enum SlotKind {
    Live,
    Demo,
    Paper,
}

impl SlotKind {
    /// Convert to the existing [`PipelineKind`] used by `build_exchange_pipeline`.
    /// 轉為 `build_exchange_pipeline` 使用的既有 [`PipelineKind`]。
    pub fn to_pipeline_kind(self) -> PipelineKind {
        match self {
            SlotKind::Live => PipelineKind::Live,
            SlotKind::Demo => PipelineKind::Demo,
            SlotKind::Paper => PipelineKind::Paper,
        }
    }
}

/// Internal state of a [`PipelineSlot`].
///
/// `Spawned.cancel_token` is a **child** of the engine-wide shutdown token
/// (Phase 2). `Spawned.task_handles` holds every tokio JoinHandle the slot
/// owns so [`PipelineSlot::teardown`] can await them deterministically
/// (no orphan tasks).
///
/// 槽位內部狀態。`Spawned.cancel_token` 是引擎級 shutdown token 的**子 token**
/// （Phase 2）。`Spawned.task_handles` 持有槽位擁有的所有 tokio JoinHandle，
/// 讓 [`PipelineSlot::teardown`] 可確定性 await（無孤兒任務）。
#[allow(dead_code)] // Phase 2: Spawned fields consumed by teardown + Phase 3 respawn
pub enum SlotState {
    Empty,
    Spawned {
        /// Slot-scoped cancel token (child of engine-wide shutdown).
        /// Cancelling this tears down only this slot's pipeline tasks.
        /// 槽位子 cancel token（引擎級 shutdown 的子）。取消只拆本槽位任務。
        cancel_token: CancellationToken,
        /// All tokio task handles the slot owns — private WS supervisor,
        /// execution listener, periodic REST balance refresh. `teardown`
        /// cancels `cancel_token` then awaits every handle in order.
        /// 槽位擁有的所有 tokio task handle — 私有 WS supervisor、執行 listener、
        /// 定期 REST 餘額刷新。`teardown` 先 cancel `cancel_token`，再依序 await。
        task_handles: Vec<JoinHandle<()>>,
        /// Unix ms when the slot transitioned to Spawned.
        /// 槽位轉為 Spawned 的 unix 毫秒時戳。
        spawned_at_ms: i64,
    },
}

/// Inputs required to spawn a pipeline slot.
///
/// `cfg_snapshot` is held by the caller and borrowed across the `try_spawn`
/// await — this matches the existing main.rs pattern (see
/// `let cfg_snapshot_pipelines = config.get();`).
///
/// `parent_shutdown_token` is the **engine-wide** cancel token; `try_spawn`
/// derives a slot-scoped child token from it so teardown can target only
/// this slot. Phase 1 called this field `cancel` — renamed in Phase 2 for
/// clarity.
///
/// 啟動槽位所需輸入。`cfg_snapshot` 由呼叫者持有、跨 await 借用。
/// `parent_shutdown_token` 是**引擎級** cancel token；`try_spawn` 會從它
/// 派生槽位子 token，讓 teardown 只針對本槽位。Phase 1 叫 `cancel`，
/// Phase 2 為意義清晰改名。
pub struct SpawnConfig<'a> {
    pub kind: SlotKind,
    pub env: BybitEnvironment,
    pub parent_shutdown_token: CancellationToken,
    pub cfg_snapshot: &'a EngineBootstrap,
    /// LG-2 T2 (2026-05-11)：per-env RiskConfig.pricing 配置（owned clone
    /// 避免跨 await 借用問題）。傳入 build_exchange_pipeline 後對 Live
    /// (Mainnet + LiveDemo) 路徑執行 pricing binding 三項斷言；Demo / Paper
    /// 不消費此欄位。建構端從對應 `risk_stores.{live,demo,paper}.load()
    /// .pricing.clone().unwrap_or_default()` 取得。
    pub pricing_config: openclaw_types::PricingConfig,
}

/// Successful spawn output — exchange-pipeline bindings + slot-scoped child
/// token. Caller threads the child token into the Live OS thread's
/// `live_cancel` so the event consumer exits on slot teardown.
///
/// 成功 spawn 的輸出 — 交易所管線綁定 + 槽位子 token。呼叫端把子 token 傳入
/// Live OS 線程的 `live_cancel`，讓 event consumer 於 slot teardown 時退出。
pub struct SpawnOutput {
    pub bindings: ExchangePipelineBindings,
    /// Child of `SpawnConfig.parent_shutdown_token`. Clone as needed.
    /// `SpawnConfig.parent_shutdown_token` 的子。需要時 clone。
    pub slot_cancel_token: CancellationToken,
}

/// Error variants surfaced by [`PipelineSlot::try_spawn`].
///
/// [`SpawnError::NotAvailable`] mirrors Phase 1: `build_exchange_pipeline`
/// returned `None`, and the inner function already logged structured fields
/// (missing credentials, LIVE-GATE-BINDING-1 rejection, BALANCE-REAL-1
/// exhaustion, etc.). Re-wrapping here would double-log.
///
/// [`SpawnError::NotAvailable`] 沿用 Phase 1：`build_exchange_pipeline`
/// 回傳 `None`，原因已由內部結構化 log 記錄。此處 re-wrap 會造成雙重 log。
#[derive(Debug)]
#[allow(dead_code)] // Phase 2: AlreadySpawned/NotAvailable consumed by call sites + tests
pub enum SpawnError {
    /// A prior `try_spawn` already succeeded; caller must `teardown` first.
    /// 先前的 `try_spawn` 已成功，呼叫端須先 `teardown`。
    AlreadySpawned,
    /// `build_exchange_pipeline` returned `None`. Inner log has the reason.
    /// `build_exchange_pipeline` 回傳 `None`，原因在內部 log。
    NotAvailable,
}

impl std::fmt::Display for SpawnError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::AlreadySpawned => write!(
                f,
                "pipeline slot already spawned; teardown required before re-spawn \
                 / 槽位已啟動，須先 teardown 才能重啟"
            ),
            Self::NotAvailable => write!(
                f,
                "pipeline slot unavailable — see inner log for reason \
                 (missing credentials / authorization rejected / balance fetch failed) \
                 / 槽位不可用 — 原因見內部 log（憑證缺失/授權拒絕/餘額抓取失敗）"
            ),
        }
    }
}

impl std::error::Error for SpawnError {}

/// Error variants surfaced by [`PipelineSlot::teardown`].
///
/// Phase 2 teardown is fail-soft: task join errors are logged and swallowed,
/// not propagated — one task refusing to exit must not block engine-wide
/// shutdown or the next respawn. Variants are reserved for situations we
/// may want to surface to the caller later (timeout, explicit abort), but
/// are not constructed in Phase 2.
///
/// Phase 2 teardown 為 fail-soft：任務 join 錯誤 log 後吞掉，不往上拋 —
/// 單一任務拒絕退出不得阻塞引擎關閉或下次 respawn。此 enum 的變體保留給
/// 未來可能想回報上游的情境（timeout、明確 abort），Phase 2 不建構。
#[derive(Debug)]
#[allow(dead_code)] // Phase 2: reserved for Phase 3+ (timeout, explicit abort)
pub enum TeardownError {
    /// Placeholder reserved for future variants. Never constructed in Phase 2.
    /// 未來變體佔位。Phase 2 不建構。
    #[allow(dead_code)]
    Reserved,
}

impl std::fmt::Display for TeardownError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Reserved => write!(
                f,
                "teardown error reserved for future use / teardown 錯誤保留給未來使用"
            ),
        }
    }
}

impl std::error::Error for TeardownError {}

/// Slot holding a possibly-spawned pipeline.
///
/// Phase 2 invariant: a `PipelineSlot` starts `Empty`, transitions to
/// `Spawned` via `try_spawn()`, and (for the Live slot) may transition
/// back to `Empty` via `teardown()` on authorization revocation. Phase 2
/// does NOT re-spawn after teardown — that is Phase 3's scope.
///
/// 持有（可能已啟動的）管線的槽位。Phase 2 不變式：啟動時 `Empty`，透過
/// `try_spawn()` 轉為 `Spawned`，（Live 槽位）可透過 `teardown()` 在授權
/// 撤銷時轉回 `Empty`。Phase 2 **不** respawn — 歸 Phase 3。
#[allow(dead_code)] // Phase 2: kind consumed by tests + Phase 3 respawn logic
pub struct PipelineSlot {
    kind: SlotKind,
    // parking_lot::Mutex: no poisoning, no await across guard. We drop the
    // guard before any `.await` in try_spawn/teardown.
    // parking_lot::Mutex：不中毒、guard 不跨 await。try_spawn/teardown 在
    // `.await` 前都會釋放 guard。
    state: parking_lot::Mutex<SlotState>,
}

#[allow(dead_code)] // Phase 2: kind/is_spawned consumed by tests + Phase 3 respawn path
impl PipelineSlot {
    /// Construct an empty slot of the given kind.
    /// 建構指定 kind 的空槽位。
    pub fn new_empty(kind: SlotKind) -> Self {
        Self {
            kind,
            state: parking_lot::Mutex::new(SlotState::Empty),
        }
    }

    /// Kind of this slot.
    /// 本槽位 kind。
    pub fn kind(&self) -> SlotKind {
        self.kind
    }

    /// True iff state is `Spawned`.
    /// 僅當狀態為 `Spawned` 時回傳 true。
    pub fn is_spawned(&self) -> bool {
        matches!(*self.state.lock(), SlotState::Spawned { .. })
    }

    /// Attempt to spawn the underlying exchange-pipeline bindings.
    ///
    /// Phase 2 behaviour:
    ///   1. Refuse if already `Spawned` (caller must `teardown()` first).
    ///   2. Create a **child** cancel token under `cfg.parent_shutdown_token`
    ///      so slot-scoped teardown cancels only this slot's tasks.
    ///   3. Delegate to [`build_exchange_pipeline`], which spawns the
    ///      private WS supervisor, execution listener, and periodic REST
    ///      balance-refresh tasks — all watching the child token — and
    ///      returns their `JoinHandle`s for the slot to own.
    ///   4. On success transition `Empty → Spawned` and store the child
    ///      token + handles; return `Some(SpawnOutput)` with bindings +
    ///      cloned child token for the caller to thread further (e.g.
    ///      Live OS thread's `live_cancel`).
    ///
    /// Lock order: acquires `self.state` synchronously at two points —
    /// (1) entry check (drops before the await on `build_exchange_pipeline`)
    /// (2) state transition after await. No other locks are held across
    /// either critical section.
    ///
    /// Phase 2 行為：
    ///   1. 若已 `Spawned` 直接拒絕（呼叫端須先 `teardown()`）。
    ///   2. 在 `cfg.parent_shutdown_token` 下建立**子** cancel token，讓
    ///      slot-scoped teardown 只取消本槽位任務。
    ///   3. 委派 [`build_exchange_pipeline`]：spawn 私有 WS supervisor、
    ///      執行 listener、定期 REST 餘額刷新 — 全部監看子 token — 並把
    ///      它們的 `JoinHandle` 交還槽位擁有。
    ///   4. 成功則 `Empty → Spawned`，存入子 token + handles；回傳
    ///      `Some(SpawnOutput)`（bindings + 子 token clone）讓呼叫端再
    ///      串下去（例如 Live OS 線程的 `live_cancel`）。
    ///
    /// 鎖序：`self.state` 在兩處同步取得 —（1）入口檢查（await 前釋放），
    /// （2）await 後狀態轉換。兩段臨界區都不跨其他鎖。
    pub async fn try_spawn<'a>(
        &self,
        cfg: &SpawnConfig<'a>,
    ) -> Result<Option<SpawnOutput>, SpawnError> {
        // Defensive: reject re-spawn on an already-Spawned slot.
        {
            let state = self.state.lock();
            if matches!(*state, SlotState::Spawned { .. }) {
                return Err(SpawnError::AlreadySpawned);
            }
            // guard drops here before the .await below — parking_lot::Mutex
            // is not Send across an await anyway, so this is enforced by the
            // compiler as well.
        }

        // Create slot-scoped child token. Cancelling the parent (SIGTERM)
        // cascades to this child; cancelling this child does NOT cascade up.
        // 建立槽位子 token。取消父 token（SIGTERM）會連帶此子；取消此子
        // **不會**回傳到父 token。
        let slot_cancel_token = cfg.parent_shutdown_token.child_token();

        // Delegate construction. `build_exchange_pipeline` already logs
        // structured reasons on None outcomes and returns the Vec of handles
        // for the tokio tasks it spawns internally.
        let built = build_exchange_pipeline(
            cfg.kind.to_pipeline_kind(),
            cfg.env,
            slot_cancel_token.clone(),
            cfg.cfg_snapshot,
            // LG-2 T2 (2026-05-11)：clone 給 build_exchange_pipeline，owned 避免
            // 跨 await 的生命週期糾結（SpawnConfig 是 borrowed ref，本欄位 owned）。
            cfg.pricing_config.clone(),
        )
        .await;

        match built {
            Some((bindings, task_handles)) => {
                // Unix ms timestamp; fall back to 0 on clock-before-epoch
                // (can't happen on sane systems, but avoid unwrap).
                // 失敗時用 0 (不可能發生)，避免 unwrap。
                let spawned_at_ms = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .map(|d| d.as_millis() as i64)
                    .unwrap_or(0);
                *self.state.lock() = SlotState::Spawned {
                    cancel_token: slot_cancel_token.clone(),
                    task_handles,
                    spawned_at_ms,
                };
                info!(
                    kind = ?self.kind,
                    spawned_at_ms,
                    "PipelineSlot spawned (child cancel token wired) \
                     / 槽位已啟動（子 cancel token 已接線）"
                );
                Ok(Some(SpawnOutput {
                    bindings,
                    slot_cancel_token,
                }))
            }
            None => {
                // State stays Empty — inner log already explained why. The
                // child token we created just now drops here and gets GC'd;
                // it was never observed by anyone so no cleanup needed.
                // 狀態留在 Empty — 內部 log 已說明原因。剛建的子 token 在此
                // drop，未被任何對象觀察，無需清理。
                Ok(None)
            }
        }
    }

    /// Teardown the slot: cancel the slot-scoped child token and await every
    /// tokio task the slot owns. Idempotent — calling on `Empty` returns
    /// `Ok(())` silently. Fail-soft — individual task join errors are logged
    /// but not propagated (one stuck task must not block engine shutdown
    /// or the next respawn).
    ///
    /// Phase 2 semantics:
    ///   * Cancelling the slot's child token does NOT cascade up to the
    ///     engine-wide token (tokio-util CancellationToken contract), so
    ///     demo / paper / any other engine-wide consumers keep running.
    ///   * After `teardown()` returns `Ok(())`, `is_spawned()` is `false`.
    ///     Phase 2 does NOT re-spawn — Live stays down until the engine is
    ///     restarted. Phase 3 will add an auth watcher that drives respawn.
    ///
    /// Lock discipline: `parking_lot::MutexGuard` is `!Send`, so we can NOT
    /// hold it across the `.await` loop that joins task handles. We use
    /// `std::mem::replace` to atomically swap out the `Spawned` variant
    /// under a short synchronous critical section, then drop the guard
    /// BEFORE any `.await`.
    ///
    /// Teardown 槽位：取消槽位子 token，await 槽位擁有的所有 tokio 任務。
    /// 冪等 — 對 `Empty` 呼叫會靜默回傳 `Ok(())`。Fail-soft — 個別任務
    /// join 錯誤 log 後吞掉（不讓卡住的任務阻塞引擎關閉或下次 respawn）。
    ///
    /// Phase 2 語義：
    ///   * 取消槽位子 token **不會**回傳到引擎級 token（tokio-util
    ///     CancellationToken 契約），demo / paper / 其他引擎級消費者照跑。
    ///   * `teardown()` 回 `Ok(())` 後 `is_spawned()` 為 `false`。Phase 2
    ///     **不** respawn — Live 保持 down 直到整機重啟。Phase 3 會加授權
    ///     watcher 驅動 respawn。
    ///
    /// 鎖紀律：`parking_lot::MutexGuard` 是 `!Send`，不可跨 `.await`。
    /// 先用 `std::mem::replace` 在短同步臨界區原子換出 `Spawned` 變體，
    /// 再 drop guard，最後才跑 `.await` join loop。
    pub async fn teardown(&self) -> Result<(), TeardownError> {
        // Swap state → Empty synchronously; extract the token + handles.
        // 同步將 state 換成 Empty；取出 token + handles。
        let (cancel_token, task_handles, kind) = {
            let mut guard = self.state.lock();
            match std::mem::replace(&mut *guard, SlotState::Empty) {
                SlotState::Empty => {
                    // Already empty — nothing to do. Silent Ok.
                    // 已經是空 — 無事可做。靜默 Ok。
                    return Ok(());
                }
                SlotState::Spawned {
                    cancel_token,
                    task_handles,
                    ..
                } => (cancel_token, task_handles, self.kind),
            }
            // guard drops here (end of scope) — we must NOT hold it across
            // the .await below.
        };

        let handle_count = task_handles.len();
        info!(
            kind = ?kind,
            handle_count,
            "PipelineSlot::teardown: cancelling child token + awaiting tasks \
             / 取消子 token 並 await 任務"
        );

        // Cancel the child token first so every task's select! arm on
        // `cancel.cancelled()` fires. Tasks that hang after cancellation
        // get logged below but do not block engine-wide shutdown.
        // 先取消子 token，讓所有任務的 `cancel.cancelled()` select 分支觸發。
        // 取消後仍卡住的任務會在下面記 log，但不阻塞引擎整體關閉。
        cancel_token.cancel();

        // Await each handle in sequence. Sequential > concurrent here: we
        // want deterministic log ordering on teardown, and the join cost
        // of 3 short-lived tasks is negligible.
        // 依序 await。順序 > 並發：要 teardown log 順序穩定，且 3 個短命
        // 任務的 join 成本可忽略。
        for (idx, handle) in task_handles.into_iter().enumerate() {
            match handle.await {
                Ok(()) => debug!(
                    kind = ?kind,
                    idx,
                    "PipelineSlot::teardown: task joined cleanly / 任務乾淨 join"
                ),
                Err(e) if e.is_cancelled() => debug!(
                    kind = ?kind,
                    idx,
                    "PipelineSlot::teardown: task was already cancelled / 任務已被取消"
                ),
                Err(e) => warn!(
                    kind = ?kind,
                    idx,
                    error = %e,
                    "PipelineSlot::teardown: task join failed (swallowed, fail-soft) \
                     / 任務 join 失敗（吞掉，fail-soft）"
                ),
            }
        }

        info!(
            kind = ?kind,
            "PipelineSlot::teardown complete / teardown 完成"
        );
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::sync::Arc;

    #[test]
    fn new_empty_reports_not_spawned() {
        let slot = PipelineSlot::new_empty(SlotKind::Live);
        assert!(!slot.is_spawned());
        // Internal state is Empty.
        let state = slot.state.lock();
        assert!(matches!(*state, SlotState::Empty));
    }

    #[test]
    fn kind_preserved() {
        for k in [SlotKind::Live, SlotKind::Demo, SlotKind::Paper] {
            let slot = PipelineSlot::new_empty(k);
            assert_eq!(slot.kind(), k);
        }
    }

    #[tokio::test]
    async fn teardown_on_empty_is_noop() {
        let slot = PipelineSlot::new_empty(SlotKind::Demo);
        // Must be Ok and not flip the state.
        slot.teardown().await.expect("teardown on empty must be Ok");
        assert!(!slot.is_spawned());
    }

    #[test]
    fn slotkind_maps_to_pipeline_kind() {
        assert_eq!(SlotKind::Live.to_pipeline_kind(), PipelineKind::Live);
        assert_eq!(SlotKind::Demo.to_pipeline_kind(), PipelineKind::Demo);
        assert_eq!(SlotKind::Paper.to_pipeline_kind(), PipelineKind::Paper);
    }

    #[test]
    fn spawn_error_display_contains_bilingual_hint() {
        let s_already = format!("{}", SpawnError::AlreadySpawned);
        assert!(s_already.contains("already spawned"));
        assert!(s_already.contains("teardown"));
        let s_none = format!("{}", SpawnError::NotAvailable);
        assert!(s_none.contains("inner log"));
    }

    // ── Phase 2: teardown behaviour ────────────────────────────────────
    //
    // These tests exercise `teardown()` without spinning up a real exchange
    // pipeline. We hand-craft a `SlotState::Spawned` using a synthetic child
    // cancel token and tokio tasks that respect it, so we can verify the
    // cancel + join mechanics in isolation.
    //
    // 這幾個測試不啟動真實交易所管線，用人工構造的 `SlotState::Spawned`
    // （自製子 cancel token 與尊重它的 tokio 任務）驗證 cancel + join 機制。

    /// Helper: spawn a tokio task that loops until its cancel token fires,
    /// setting an atomic flag on exit. Returns the JoinHandle.
    /// 工具：spawn 一個 loop 直到 cancel token 觸發的 tokio 任務，退出時
    /// 設 atomic 旗標。回傳 JoinHandle。
    fn spawn_watcher_task(token: CancellationToken, exited: Arc<AtomicBool>) -> JoinHandle<()> {
        tokio::spawn(async move {
            token.cancelled().await;
            exited.store(true, Ordering::SeqCst);
        })
    }

    /// Helper: build a `Spawned` state around a freshly-made child token +
    /// user-supplied handles, and stuff it into the slot. Keeps the child
    /// token so the caller can assert on it.
    /// 工具：用新建的子 token + 使用者提供的 handles 建 `Spawned` 並塞入 slot；
    /// 同時把子 token 還給呼叫者以便斷言。
    fn install_spawned(
        slot: &PipelineSlot,
        parent: &CancellationToken,
        handles: Vec<JoinHandle<()>>,
    ) -> CancellationToken {
        let child = parent.child_token();
        *slot.state.lock() = SlotState::Spawned {
            cancel_token: child.clone(),
            task_handles: handles,
            spawned_at_ms: 0,
        };
        child
    }

    /// Phase 2: teardown must cancel the slot's child token so tasks
    /// watching it exit within a short timeout.
    /// Phase 2：teardown 必須取消槽位子 token，讓監看它的任務在短時限內退出。
    #[tokio::test]
    async fn teardown_cancels_child_token() {
        let slot = PipelineSlot::new_empty(SlotKind::Live);
        let parent = CancellationToken::new();
        let exited = Arc::new(AtomicBool::new(false));

        // Install a Spawned state with one watcher task.
        // 安裝一個有 1 個 watcher 任務的 Spawned 狀態。
        let child = parent.child_token();
        let handle = spawn_watcher_task(child.clone(), Arc::clone(&exited));
        *slot.state.lock() = SlotState::Spawned {
            cancel_token: child.clone(),
            task_handles: vec![handle],
            spawned_at_ms: 0,
        };

        // Teardown with a generous timeout so a CI hang is caught as a
        // test failure rather than a hang forever.
        // 加 timeout：CI 卡住時 test 失敗而非無限等。
        tokio::time::timeout(std::time::Duration::from_secs(2), slot.teardown())
            .await
            .expect("teardown must complete within 2s")
            .expect("teardown must be Ok");

        assert!(
            exited.load(Ordering::SeqCst),
            "watcher task must have observed cancel"
        );
        assert!(!slot.is_spawned(), "state must be Empty after teardown");
        assert!(child.is_cancelled(), "child token must be cancelled");
        assert!(!parent.is_cancelled(), "parent token must NOT be cancelled");
    }

    /// Phase 2: teardown must await every task_handle — no orphaned tasks.
    /// Phase 2：teardown 必須 await 每個 task_handle — 不留孤兒任務。
    #[tokio::test]
    async fn teardown_awaits_task_handles() {
        let slot = PipelineSlot::new_empty(SlotKind::Live);
        let parent = CancellationToken::new();
        let child = parent.child_token();

        let flags: Vec<Arc<AtomicBool>> =
            (0..3).map(|_| Arc::new(AtomicBool::new(false))).collect();
        let handles: Vec<JoinHandle<()>> = flags
            .iter()
            .map(|f| spawn_watcher_task(child.clone(), Arc::clone(f)))
            .collect();

        *slot.state.lock() = SlotState::Spawned {
            cancel_token: child.clone(),
            task_handles: handles,
            spawned_at_ms: 0,
        };

        tokio::time::timeout(std::time::Duration::from_secs(2), slot.teardown())
            .await
            .expect("teardown must complete within 2s")
            .expect("teardown must be Ok");

        for (i, f) in flags.iter().enumerate() {
            assert!(
                f.load(Ordering::SeqCst),
                "task {} must have exited (no orphans allowed)",
                i
            );
        }
        assert!(!slot.is_spawned());
    }

    /// Phase 2: teardown is idempotent — second call on now-Empty state
    /// returns Ok(()) silently.
    /// Phase 2：teardown 冪等 — 對已 Empty 的狀態再呼叫回 `Ok(())`。
    #[tokio::test]
    async fn teardown_idempotent() {
        let slot = PipelineSlot::new_empty(SlotKind::Live);
        let parent = CancellationToken::new();
        let exited = Arc::new(AtomicBool::new(false));
        let child = parent.child_token();
        let handle = spawn_watcher_task(child.clone(), Arc::clone(&exited));
        *slot.state.lock() = SlotState::Spawned {
            cancel_token: child,
            task_handles: vec![handle],
            spawned_at_ms: 0,
        };

        // First call: real teardown.
        slot.teardown().await.expect("first teardown must be Ok");
        assert!(!slot.is_spawned());

        // Second call: slot is Empty → Ok without side effects.
        slot.teardown().await.expect("second teardown must be Ok");
        assert!(!slot.is_spawned());
    }

    /// Phase 2: parent cancel cascades to child (sanity check on the
    /// tokio-util CancellationToken contract we rely on).
    /// Phase 2：父 cancel 會波及子（對我們依賴的 tokio-util CancellationToken
    /// 契約做 sanity check）。
    #[tokio::test]
    async fn parent_cancel_cascades_to_slot() {
        let slot = PipelineSlot::new_empty(SlotKind::Demo);
        let parent = CancellationToken::new();
        let exited = Arc::new(AtomicBool::new(false));
        let child = install_spawned(
            &slot,
            &parent,
            vec![spawn_watcher_task(
                parent.child_token(), // bonus: watches its own direct child too
                Arc::clone(&exited),
            )],
        );

        parent.cancel();

        // Await briefly to let the watcher task propagate.
        tokio::time::timeout(std::time::Duration::from_millis(200), async {
            while !child.is_cancelled() {
                tokio::task::yield_now().await;
            }
        })
        .await
        .expect("parent cancel must propagate to child within 200ms");

        assert!(child.is_cancelled(), "child must be cancelled by parent");
    }

    /// Phase 2: cancelling a child (via teardown) does NOT cancel the parent
    /// — this is the core safety property that keeps demo/paper alive on
    /// Live-only teardown.
    /// Phase 2：透過 teardown 取消子 token 不會取消父 token — 這是確保
    /// demo/paper 在 Live-only teardown 時存活的核心安全屬性。
    #[tokio::test]
    async fn child_cancel_does_not_cancel_parent() {
        let slot = PipelineSlot::new_empty(SlotKind::Live);
        let parent = CancellationToken::new();
        let exited = Arc::new(AtomicBool::new(false));
        let child = parent.child_token();
        let handle = spawn_watcher_task(child.clone(), Arc::clone(&exited));
        *slot.state.lock() = SlotState::Spawned {
            cancel_token: child.clone(),
            task_handles: vec![handle],
            spawned_at_ms: 0,
        };

        slot.teardown().await.expect("teardown must be Ok");

        assert!(child.is_cancelled(), "child must be cancelled");
        assert!(
            !parent.is_cancelled(),
            "parent must NOT be cancelled by child teardown (safety invariant)"
        );
    }

    /// Phase 2: `SpawnOutput.slot_cancel_token` clones independently — the
    /// caller can hold its own clone for threading into the Live OS thread
    /// without needing to peek into `SlotState::Spawned`.
    /// Phase 2：`SpawnOutput.slot_cancel_token` 可獨立 clone — 呼叫端能持有
    /// 自己那份用以串進 Live OS 線程，無需窺探 `SlotState::Spawned`。
    #[test]
    fn spawn_output_clones_share_cancellation() {
        let parent = CancellationToken::new();
        let child = parent.child_token();
        let clone_a = child.clone();
        let clone_b = child.clone();
        clone_a.cancel();
        assert!(
            clone_b.is_cancelled(),
            "sibling clone must observe cancellation"
        );
        assert!(child.is_cancelled());
        assert!(!parent.is_cancelled());
    }

    /// Phase 2 (E2 BLOCKER #1 fix): a **third party** (e.g. the Live event
    /// consumer main loop holding a clone of the slot-scoped child token
    /// via `EventConsumerDeps.cancel`) must exit when `teardown()` is called
    /// — even when the engine-wide parent token stays alive.
    ///
    /// This is the core guarantee that turns "skin-deep teardown" into
    /// "complete teardown": pre-Phase-2-fix the event consumer watched the
    /// engine-wide token, so `teardown()` left it running and still
    /// dispatching orders. Post-fix, the consumer watches the slot-scoped
    /// child, so `teardown()` propagates into its `select!` loop.
    ///
    /// We simulate the event consumer with a task that does exactly what
    /// `event_consumer/mod.rs::run_event_consumer` does at line ~755:
    ///     `tokio::select! { _ = cancel.cancelled() => break, ... }`
    ///
    /// Phase 2（E2 BLOCKER #1 修復）：**第三方**（例如 Live event consumer
    /// 主迴圈透過 `EventConsumerDeps.cancel` 持有槽位子 token 的 clone）必須
    /// 在 `teardown()` 被呼叫時退出 — 即便引擎級父 token 仍存活。
    ///
    /// 這是把「皮毛式 teardown」變成「完整 teardown」的核心保證：修復前
    /// event consumer 監看引擎級 token，`teardown()` 讓它繼續跑、繼續下單。
    /// 修復後監看槽位子 token，`teardown()` 會傳播到它的 `select!` 迴圈。
    ///
    /// 此測試模擬 event consumer — 複製 `event_consumer/mod.rs::run_event_consumer`
    /// 約 755 行處的行為：`tokio::select! { _ = cancel.cancelled() => break, ... }`。
    #[tokio::test]
    async fn teardown_propagates_to_third_party_event_consumer_sim() {
        let slot = PipelineSlot::new_empty(SlotKind::Live);
        let engine_wide = CancellationToken::new();
        let child = engine_wide.child_token();

        // Install a Spawned state whose owned-task watches the child token
        // (models WS supervisor / listener / balance refresh).
        // 安裝 Spawned 狀態，其擁有的任務監看子 token（模擬 WS supervisor
        // / listener / 餘額刷新）。
        let ws_task_exited = Arc::new(AtomicBool::new(false));
        let ws_handle = spawn_watcher_task(child.clone(), Arc::clone(&ws_task_exited));
        *slot.state.lock() = SlotState::Spawned {
            cancel_token: child.clone(),
            task_handles: vec![ws_handle],
            spawned_at_ms: 0,
        };

        // Simulate the Live event consumer main loop (a *separate* task,
        // NOT owned by the slot — mirrors how `run_event_consumer` is
        // spawned on the live OS thread / by `tokio::spawn`). It holds its
        // own clone of the child token — exactly what the BLOCKER #1 fix
        // wires into `live_deps.cancel` / `demo_deps.cancel`.
        //
        // 模擬 Live event consumer 主迴圈 — 是**獨立**任務，不歸 slot 擁有
        // （對應 `run_event_consumer` 跑在 live OS 線程 / 由 `tokio::spawn`
        // 起）。它持有自己那份子 token clone — 這正是 BLOCKER #1 修復接線
        // 進 `live_deps.cancel` / `demo_deps.cancel` 的那個。
        let consumer_cancel = child.clone();
        let consumer_loop_iterations = Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let consumer_loop_iterations_clone = Arc::clone(&consumer_loop_iterations);
        let consumer_exited = Arc::new(AtomicBool::new(false));
        let consumer_exited_clone = Arc::clone(&consumer_exited);
        let consumer_handle = tokio::spawn(async move {
            loop {
                tokio::select! {
                    _ = consumer_cancel.cancelled() => {
                        consumer_exited_clone.store(true, Ordering::SeqCst);
                        break;
                    }
                    _ = tokio::time::sleep(std::time::Duration::from_millis(5)) => {
                        consumer_loop_iterations_clone.fetch_add(1, Ordering::SeqCst);
                    }
                }
            }
        });

        // Let the consumer spin a bit so we prove it was actually alive
        // before teardown.
        // 讓 consumer 先轉幾圈，證明 teardown 前它確實活著。
        tokio::time::sleep(std::time::Duration::from_millis(30)).await;
        let iters_before = consumer_loop_iterations.load(Ordering::SeqCst);
        assert!(
            iters_before >= 1,
            "consumer sim must have spun at least once before teardown"
        );

        // Teardown the slot. Expected:
        //   * slot's child token is cancelled
        //   * ws_task (owned by slot) joins cleanly
        //   * *consumer* (third party, same child-token clone) ALSO exits
        //   * engine-wide parent token stays alive (demo/paper safety)
        // 拆掉 slot。預期：槽位子 token 被取消；槽位擁有的 ws_task 乾淨 join；
        // 第三方 consumer（同一子 token clone）**也**退出；引擎級父 token
        // 仍存活（demo/paper 安全）。
        tokio::time::timeout(std::time::Duration::from_secs(2), slot.teardown())
            .await
            .expect("teardown must complete within 2s")
            .expect("teardown must be Ok");

        // Allow the consumer a brief window to observe cancellation and exit.
        // 給 consumer 一點時間觀察取消並退出。
        tokio::time::timeout(std::time::Duration::from_secs(2), consumer_handle)
            .await
            .expect("consumer must exit within 2s after teardown")
            .expect("consumer must exit cleanly");

        assert!(
            ws_task_exited.load(Ordering::SeqCst),
            "slot-owned task must have observed cancel"
        );
        assert!(
            consumer_exited.load(Ordering::SeqCst),
            "third-party event consumer sim must have exited (BLOCKER #1 fix)"
        );
        assert!(child.is_cancelled(), "child token must be cancelled");
        assert!(
            !engine_wide.is_cancelled(),
            "engine-wide parent must stay alive — this is the core live-only teardown property"
        );
    }
}
