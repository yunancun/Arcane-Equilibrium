//! PIPELINE-SLOT-1 Phase 1 — pipeline slot abstraction (plumbing only).
//! PIPELINE-SLOT-1 Phase 1 — 管線槽位抽象（僅接線，無新行為）。
//!
//! MODULE_NOTE (EN):
//!   Phase 1 is a pure structural refactor. It introduces the `PipelineSlot`
//!   type so the Phase 4 auth-watcher can tear down and respawn the Live
//!   pipeline in-process, without restarting the whole engine (the current
//!   re-verify loop in `main.rs` cancels the engine-wide token, killing
//!   demo/paper as collateral damage — see CLAUDE.md §三 "PIPELINE-SLOT-1"
//!   and Root Principle #7 "learning plane isolation from live plane").
//!
//!   Phase 1 scope:
//!     * Wrap the existing `build_exchange_pipeline()` call with
//!       `PipelineSlot::try_spawn()`. The construction logic itself is NOT
//!       changed — extract-and-call only. BALANCE-REAL-1 fail-closed,
//!       LIVE-GATE-BINDING-1 signature verification, DCP setup, private WS
//!       supervisor spawn, all stay exactly where they were.
//!     * `teardown()` is a stub that logs a warning and returns Ok(()) — the
//!       happy-path startup never calls it. Real teardown arrives in Phase 2.
//!     * `task_handles` is an empty Vec placeholder for Phase 2 (task handles
//!       for the downstream tokio::spawn calls that feed the pipeline live in
//!       `main.rs` and are not owned by the slot yet).
//!
//!   Non-goals for Phase 1:
//!     * No respawn logic, no auth-watcher refactor, no engine-wide cancel
//!       token narrowing. The current `auth_cancel` behaviour is preserved
//!       byte-identically — see `main.rs` around the 5-min re-verify ticker.
//!     * No change to `ExchangePipelineBindings`, no new fields.
//!
//! MODULE_NOTE (中):
//!   Phase 1 是純結構性重構。引入 `PipelineSlot` 類型，讓 Phase 4 的授權 watcher
//!   能夠在進程內獨立撤下並重建 Live 管線，不再整個引擎重啟（目前 `main.rs`
//!   的 5 分鐘重驗 loop 取消的是引擎級 token，會把 demo/paper 一起陪葬 —
//!   見 CLAUDE.md §三「PIPELINE-SLOT-1」與根原則 #7「learning 與 live 平面隔離」）。
//!
//!   Phase 1 範圍：
//!     * 用 `PipelineSlot::try_spawn()` 包裹既有的 `build_exchange_pipeline()`
//!       呼叫。構造邏輯**不動**，只做提取+呼叫。BALANCE-REAL-1 fail-closed、
//!       LIVE-GATE-BINDING-1 簽名驗證、DCP 設置、私有 WS 監管器啟動，全部原地
//!       不動。
//!     * `teardown()` 是 stub：記 warn 後回傳 Ok(())，happy path 啟動不會呼叫
//!       它。真正的 teardown 邏輯留到 Phase 2。
//!     * `task_handles` 是 Phase 2 的佔位 Vec（管線的下游 tokio::spawn 任務
//!       handle 目前仍由 `main.rs` 自己管，slot 尚未接手）。
//!
//!   Phase 1 非目標：
//!     * 不寫 respawn 邏輯、不動授權 watcher、不收窄引擎級 cancel token。
//!       目前 `auth_cancel` 行為逐字節保留 — 見 `main.rs` 5 分鐘重驗 ticker。
//!     * 不動 `ExchangePipelineBindings`，不加新欄位。

use crate::startup::{build_exchange_pipeline, ExchangePipelineBindings};
use openclaw_engine::bybit_rest_client::BybitEnvironment;
use openclaw_engine::config::EngineBootstrap;
use openclaw_engine::tick_pipeline::PipelineKind;
use tokio::task::JoinHandle;
use tokio_util::sync::CancellationToken;
use tracing::warn;

/// Which logical pipeline this slot holds.
///
/// Mirrors [`PipelineKind`] semantically but kept separate so the slot type
/// can evolve (Phase 4 may add operator intent like "force-live-down") without
/// dragging [`PipelineKind`] along.
///
/// 槽位持有的邏輯管線類型。語意與 [`PipelineKind`] 對映，但刻意保持獨立，
/// 讓 slot 類型可獨立演進（Phase 4 可能加入 operator 意圖如「強制下 live」）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[allow(dead_code)] // Phase 1: Paper slot not yet wired (paper spawn still in main.rs)
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
/// Phase 1 never transitions to `Spawned.task_handles` with non-empty contents
/// — the downstream tokio::spawn calls remain in `main.rs`. The field exists
/// so the API shape matches Phase 2's eventual respawn needs.
///
/// 槽位內部狀態。Phase 1 永遠不會把 `Spawned.task_handles` 填入非空內容 —
/// 下游 tokio::spawn 仍留在 `main.rs`。此欄位只是對齊 Phase 2 的 API 形狀。
#[allow(dead_code)] // Phase 1: Spawned fields consumed by Phase 2 teardown+respawn
pub enum SlotState {
    Empty,
    Spawned {
        /// Per-slot cancel token. Phase 1 threads the engine-wide token
        /// through so behaviour stays identical; Phase 2 will narrow this
        /// to a child token so only this slot tears down on auth revoke.
        /// 本槽位的 cancel token。Phase 1 沿用引擎級 token 以保行為一致；
        /// Phase 2 會改為子 token，讓授權撤銷時只拆本槽位。
        cancel_token: CancellationToken,
        /// Future home of slot-owned task handles (Phase 2). Phase 1 is empty.
        /// Phase 2 將歸槽位管的任務 handle 清單。Phase 1 為空。
        task_handles: Vec<JoinHandle<()>>,
        /// Unix ms when the slot transitioned to Spawned.
        /// 槽位轉為 Spawned 的 unix 毫秒時戳。
        spawned_at_ms: i64,
    },
}

/// Inputs required to spawn a pipeline slot.
///
/// Phase 1 delegates straight to `build_exchange_pipeline`, so the fields
/// mirror that signature. `cfg_snapshot` is held by the caller and borrowed
/// across the `try_spawn` await — this matches the existing main.rs pattern
/// (see `let cfg_snapshot_pipelines = config.get();` then drop after both
/// calls).
///
/// 啟動槽位所需輸入。Phase 1 直接轉發給 `build_exchange_pipeline`，欄位與
/// 其簽名對映。`cfg_snapshot` 由呼叫者持有、跨 await 借用 — 這與 main.rs
/// 的既有模式一致。
pub struct SpawnConfig<'a> {
    pub kind: SlotKind,
    pub env: BybitEnvironment,
    pub cancel: CancellationToken,
    pub cfg_snapshot: &'a EngineBootstrap,
}

/// Error variants surfaced by [`PipelineSlot::try_spawn`].
///
/// Phase 1 collapses most "build returned None" outcomes into
/// [`SpawnError::NotAvailable`] to preserve the existing log semantics from
/// `build_exchange_pipeline` — the inner function has already emitted the
/// precise reason (missing credentials, LIVE-GATE-BINDING-1 rejection,
/// BALANCE-REAL-1 exhaustion, etc.) with structured fields. Re-wrapping would
/// just double-log.
///
/// Phase 1 把 `build_exchange_pipeline` 回傳 `None` 的多種情境全部歸類為
/// [`SpawnError::NotAvailable`]，保留既有 log 語義 — 內部函式已用結構化欄位
/// 打出精確原因（憑證缺失、LIVE-GATE-BINDING-1 拒絕、BALANCE-REAL-1 耗盡
/// 等），再 wrap 一次會造成雙重 log。
#[derive(Debug)]
#[allow(dead_code)] // Phase 1: AlreadySpawned/NotAvailable are API surface used by tests + Phase 2
pub enum SpawnError {
    /// A prior `try_spawn` already succeeded; caller must `teardown` first.
    /// Phase 1 happy path never hits this — we spawn once at startup.
    /// 先前的 `try_spawn` 已成功，呼叫端須先 `teardown`。Phase 1 happy path 不會碰到。
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
/// Phase 1 teardown is a stub so this enum currently has no non-unit variants.
/// Reserved for Phase 2 (timeout, task join error, etc.).
///
/// `teardown` 錯誤面。Phase 1 是 stub 故暫無非單元變體，保留給 Phase 2
/// （timeout、task join 錯誤等）。
#[derive(Debug)]
#[allow(dead_code)] // Phase 1 stub; real variants land in Phase 2
pub enum TeardownError {
    /// Placeholder — never constructed in Phase 1. Exists so `Result<_, TeardownError>`
    /// is the stable API shape.
    /// Phase 1 不會建構，只為讓 `Result<_, TeardownError>` 成為穩定 API 形狀。
    #[allow(dead_code)]
    NotImplemented,
}

impl std::fmt::Display for TeardownError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::NotImplemented => write!(
                f,
                "teardown not yet implemented (Phase 2) / teardown 尚未實作（Phase 2）"
            ),
        }
    }
}

impl std::error::Error for TeardownError {}

/// Slot holding a possibly-spawned pipeline.
///
/// Phase 1 invariant: a `PipelineSlot` starts `Empty`, transitions at most
/// once to `Spawned` via `try_spawn()`, and never returns to `Empty` for the
/// lifetime of the engine process (teardown stub does not actually transition
/// state). Phase 2 will add real teardown + respawn.
///
/// 持有（可能已啟動的）管線的槽位。Phase 1 不變式：啟動時 `Empty`，至多
/// 透過 `try_spawn()` 轉一次 `Spawned`，整個引擎生命週期內不會再回到 `Empty`
/// （teardown stub 不真的改變狀態）。Phase 2 會補上真正的 teardown + respawn。
#[allow(dead_code)] // Phase 1: kind is consumed by Phase 2 respawn logic
pub struct PipelineSlot {
    kind: SlotKind,
    // parking_lot::Mutex: no poisoning, no await across guard. Phase 1 does
    // not hold the guard across the `.await` in try_spawn — we drop-before-await.
    // parking_lot::Mutex：不中毒、guard 不跨 await。Phase 1 在 try_spawn 的
    // `.await` 前就釋放 guard。
    state: parking_lot::Mutex<SlotState>,
}

#[allow(dead_code)] // Phase 1: kind/is_spawned/teardown consumed by Phase 2 respawn path + tests
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
    /// Phase 1 behaviour: delegates directly to
    /// [`build_exchange_pipeline`](crate::startup::build_exchange_pipeline).
    /// All fail-closed semantics (LIVE-GATE-BINDING-1 signature verify,
    /// BALANCE-REAL-1 3-attempt retry, DCP setup, private WS supervisor
    /// spawn) happen inside that function unchanged. On success the slot
    /// transitions `Empty → Spawned` and the freshly built bindings are
    /// returned for the caller to wire into downstream fan-out + tick
    /// pipeline spawns (which still live in `main.rs` for Phase 1).
    ///
    /// Lock order: acquires `self.state` synchronously at two points —
    /// (1) entry check (drops before the await on `build_exchange_pipeline`)
    /// (2) state transition after await. No other locks are held across
    /// either critical section. Callers must not hold a lock on any other
    /// slot's `state` while awaiting this future.
    ///
    /// Phase 1 行為：直接轉發給 [`build_exchange_pipeline`]。所有 fail-closed
    /// 語義（LIVE-GATE-BINDING-1 簽名驗證、BALANCE-REAL-1 3 次重試、DCP
    /// 設置、私有 WS 監管器啟動）都在該函式內不變地發生。成功則槽位
    /// `Empty → Spawned`，回傳新建的 bindings 給呼叫者接到下游扇出與 tick
    /// 管線啟動（Phase 1 仍住在 `main.rs`）。
    ///
    /// 鎖序：`self.state` 在兩處同步取得 —（1）入口檢查（await 前釋放），
    /// （2）await 後狀態轉換。兩段臨界區都不跨其他鎖。呼叫端不得在持有其他
    /// 槽位 `state` lock 的情況下 await 本 future。
    pub async fn try_spawn<'a>(
        &self,
        cfg: &SpawnConfig<'a>,
    ) -> Result<Option<ExchangePipelineBindings>, SpawnError> {
        // Defensive: reject re-spawn on an already-Spawned slot. Phase 1 call
        // sites spawn exactly once at startup so this branch is unreachable
        // in the happy path, but the invariant lets Phase 2 catch misuse.
        {
            let state = self.state.lock();
            if matches!(*state, SlotState::Spawned { .. }) {
                return Err(SpawnError::AlreadySpawned);
            }
            // guard drops here before the .await below — parking_lot::Mutex
            // is not Send across an await anyway, so this is enforced by the
            // compiler as well.
        }

        // Delegate construction. `build_exchange_pipeline` already logs
        // structured reasons on None outcomes.
        let bindings = build_exchange_pipeline(
            cfg.kind.to_pipeline_kind(),
            cfg.env,
            cfg.cancel.clone(),
            cfg.cfg_snapshot,
        )
        .await;

        match bindings {
            Some(b) => {
                // Unix ms timestamp; fall back to 0 on clock-before-epoch
                // (can't happen on sane systems, but avoid unwrap).
                // 失敗時用 0 (不可能發生)，避免 unwrap。
                let spawned_at_ms = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .map(|d| d.as_millis() as i64)
                    .unwrap_or(0);
                *self.state.lock() = SlotState::Spawned {
                    cancel_token: cfg.cancel.clone(),
                    task_handles: Vec::new(), // Phase 2 will populate
                    spawned_at_ms,
                };
                Ok(Some(b))
            }
            None => {
                // State stays Empty — inner log already explained why.
                // 狀態留在 Empty — 內部 log 已說明原因。
                Ok(None)
            }
        }
    }

    /// Teardown stub (Phase 1).
    ///
    /// Phase 1 happy path never calls this; it exists so Phase 2 can drop in
    /// real cancel+join logic without changing the public API. If the slot
    /// is already `Empty`, returns Ok silently. If `Spawned`, logs a warning
    /// and still returns Ok without actually cancelling the token or joining
    /// any tasks — that is deliberately delegated to Phase 2 alongside the
    /// auth-watcher refactor, so Phase 1 cannot accidentally introduce a
    /// teardown path the downstream tick-pipeline spawn code does not yet
    /// handle.
    ///
    /// Phase 1 的 stub。Happy path 不會呼叫；留著讓 Phase 2 能在不改 API 的
    /// 前提下塞入真正的 cancel+join 邏輯。`Empty` 時靜默回傳 Ok；`Spawned`
    /// 時只 warn 後回 Ok，刻意不真 cancel — 避免 Phase 1 不小心觸發下游 tick
    /// 管線尚未處理的 teardown 路徑。
    pub async fn teardown(&self) -> Result<(), TeardownError> {
        let is_spawned = matches!(*self.state.lock(), SlotState::Spawned { .. });
        if is_spawned {
            warn!(
                kind = ?self.kind,
                "PipelineSlot::teardown called but Phase 1 is a no-op — state remains Spawned. \
                 Real teardown lands in Phase 2 alongside auth-watcher refactor. \
                 / Phase 1 teardown 為 no-op，狀態維持 Spawned；真實 teardown 於 Phase 2 上線。"
            );
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

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
}
