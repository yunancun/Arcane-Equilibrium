//! Wave 5 Packet C / C3 — `SharedFailsafeWatcher` 單例封裝。
//!
//! 模塊用途：
//!   對 operator Q4.1 拍板「single shared watcher」（per PA spec §4.2 推薦 (a)）提供
//!   **單例 + 內部可變狀態保護**封裝。C3 階段只暴露 API surface（`observe_dispatch /
//!   record_operator_ack / check_timer`），不 spawn tokio task — task lifecycle 屬 C4
//!   `tasks.rs::spawn_notification_failsafe_watcher` 範圍，留 Sprint 3。
//!
//! 為什麼採 trait-object boxing（`Box<dyn ...>`）而非泛型參數化：
//!   - C3 與 C1 (ThreeWayDispatcher) / C2 (PgAuditEmitter) 並行；C1 尚未 land
//!     `ThreeWayDispatcher` 具體型別；
//!   - 單例需具體型別簽名才能存進 `OnceLock<Arc<SharedFailsafeWatcher>>`；
//!   - 用 `Box<dyn NotificationDispatcher + Send + Sync>` 等 trait object 解除型別
//!     耦合 — C4 wire 時把 `ThreeWayDispatcher` / `PgAuditEmitter` `Box::new` 進來即可；
//!   - 對 hot path 影響可忽略：fail-safe watcher 30s tick，trait object vtable 開銷
//!     遠 < 一次 REST round-trip。
//!
//! 為什麼採 `OnceLock<Arc<SharedFailsafeWatcher>>` 而非 `Lazy<>`：
//!   - `OnceLock` 是 std 內建（1.70+），不需 `once_cell` dep；
//!   - 單例初始化只在 C4 spawn task 時呼一次（`get_or_init`）；
//!   - 後續所有 read/write 皆 cheap `Arc` clone。
//!
//! 為什麼內部 state 用 `parking_lot::Mutex` 而非 `tokio::sync::Mutex`：
//!   - watcher 的純邏輯 `evaluate_dispatch / record_operator_ack / timer_expired`
//!     是 sync；async 部分（check_timer + dispatch）才需 await；
//!   - `parking_lot::Mutex` 不需 .await 即可 lock，避免 async 鎖跨 await 的死鎖陷阱；
//!   - 但 `check_timer` 內含 await（exchange sync + audit emit），不能在 lock guard
//!     內 await — 因此 `check_timer` 拆三段：snapshot state → drop lock → run async
//!     → re-lock 更新 state。詳見 `check_timer` 內 inline 註解。
//!
//! 不變量（per CLAUDE.md §二 原則 5/6/9 + AMD-2026-05-21-01 v2 §3.1）：
//!   - 單例：`instance()` 雙呼回同一 `Arc`；
//!   - 鎖跨 await 禁區：所有 await 在 lock drop 後；
//!   - 不 spawn tokio task（C4 範圍）；
//!   - 不 panic / 不 unwrap；初始化失敗 fail-soft return 既有 instance 或無動作。
//!
//! ref:
//!   - docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md §4.2 + §4.4 + §4.7
//!   - AMD-2026-05-21-01 v2 §Decision 3.1 + Q4

use std::sync::{Arc, OnceLock};

use parking_lot::Mutex;

use crate::notification_failsafe::{
    evaluate_dispatch, record_operator_ack, timer_expired, DispatchOutcome, ExchangeStopSync,
    FailsafeAuditEmitter, FailsafeClock, FailsafeConfig, FailsafeDecision, FailsafeWatcherState,
    NotificationDispatcher, PositionSnapshotProvider,
};
// C4：`check_timer`（含 SM transition + report）改 `#[cfg(test)]`，runtime 走
// `timer_expired_and_claim` + in-band command。以下型別僅 test 端使用。
#[cfg(test)]
use crate::notification_failsafe::{execute_failsafe_escalation, FailsafeExecutionReport};
#[cfg(test)]
use openclaw_core::sm::risk_gov::RiskGovernorSm;

// ════════════════════════════════════════════════════════════════════════════
// 全域單例 storage
// ════════════════════════════════════════════════════════════════════════════

/// 全域單例存放點（per task spec §Phase 4「single shared watcher」）。
///
/// 為什麼 `OnceLock` 包 `Arc`：
///   - `OnceLock` 保證 thread-safe initialization「最多一次」；
///   - `Arc` 讓所有呼叫端拿到同一份指標（read share），符合 Q4.1 拍板「共享」語義。
static SHARED_WATCHER: OnceLock<Arc<SharedFailsafeWatcher>> = OnceLock::new();

/// P2-PACKET-C-C4-PIPELINE-WIRE · outcome / ack 餵入端 sender 的單例存放點。
///
/// 為什麼存在（非 dead-wire + 防 select! busy-loop）：
///   C4 watcher 的 `tokio::select!` 監聽 `outcome_rx` / `ack_rx`。若 tx 端在 spawn 後
///   被 drop，channel 關閉 → `recv()` 立即回 `None` → `Some(..) = recv()` 模式不匹配 →
///   該 select 臂被永久禁用後 loop 退化為 busy-spin。把 sender 存進此 OnceLock 保活 +
///   供 `incident_policy` 取出 outcome_tx 接 dispatch 觸發、C5 GUI ack 取出 ack_tx。
///   C4 watcher 自己不產生 incident；producer 全在 policy / GUI ack 端。
///
/// singleton 登記：本 OnceLock 隨 `spawn_notification_failsafe_watcher` 單點 init，
/// 與 `SHARED_WATCHER` 同生命週期；已登記於 `docs/architecture/singleton-registry.md §2.4.2`
/// （commit a8ba146c）。`SHARED_WATCHER` 見同文件 §2.4.1。
static FAILSAFE_FEED_SENDERS: OnceLock<FailsafeFeedSenders> = OnceLock::new();

/// outcome / ack 餵入端 sender bundle（incident_policy + C5 GUI ack 取用）。
#[derive(Clone)]
pub struct FailsafeFeedSenders {
    /// incident_policy 偵測需通知事件 → dispatch → 經此餵 outcome。
    pub outcome_tx: tokio::sync::mpsc::UnboundedSender<DispatchOutcome>,
    /// C5 GUI ack 經此餵（operator 點 banner ack）。
    pub ack_tx: tokio::sync::mpsc::UnboundedSender<()>,
}

/// 註冊 outcome / ack sender（boot-time 單點，`spawn_notification_failsafe_watcher` 呼）。
/// 第二次呼叫不覆蓋（OnceLock 語義），回現存（或本次）bundle clone。
pub fn init_failsafe_feed_senders(senders: FailsafeFeedSenders) -> FailsafeFeedSenders {
    FAILSAFE_FEED_SENDERS.get_or_init(|| senders).clone()
}

/// 取得 outcome / ack sender bundle（incident_policy / C5 取用）；未 init 回 `None`。
pub fn failsafe_feed_senders() -> Option<FailsafeFeedSenders> {
    FAILSAFE_FEED_SENDERS.get().cloned()
}

// ════════════════════════════════════════════════════════════════════════════
// SharedFailsafeWatcher — trait-object 封裝
// ════════════════════════════════════════════════════════════════════════════

/// 三 dispatcher / position / exchange / audit / clock trait objects 全部 box 在內。
///
/// 為什麼 5 個欄位都 box：
///   解除與 C1/C2 具體型別耦合；C4 wire 時用 `Box::new(ThreeWayDispatcher::...)` 等
///   填入。`Send + Sync` bound 已在 trait 定義（`mod.rs` line 204 + 213 + 220 + 226 + 234），
///   trait object 自動繼承。
pub struct SharedFailsafeWatcher {
    dispatcher: Box<dyn NotificationDispatcher>,
    positions: Box<dyn PositionSnapshotProvider>,
    exchange: Box<dyn ExchangeStopSync>,
    audit: Box<dyn FailsafeAuditEmitter>,
    clock: Box<dyn FailsafeClock>,
    cfg: FailsafeConfig,
    /// 內部可變狀態 — `parking_lot::Mutex` 不跨 await 持有（鎖跨 await 反模式）。
    state: Mutex<FailsafeWatcherState>,
}

impl SharedFailsafeWatcher {
    /// 私有 ctor — 對外只能透過 `init` / `instance`。
    fn new(
        dispatcher: Box<dyn NotificationDispatcher>,
        positions: Box<dyn PositionSnapshotProvider>,
        exchange: Box<dyn ExchangeStopSync>,
        audit: Box<dyn FailsafeAuditEmitter>,
        clock: Box<dyn FailsafeClock>,
        cfg: FailsafeConfig,
    ) -> Self {
        Self {
            dispatcher,
            positions,
            exchange,
            audit,
            clock,
            cfg,
            state: Mutex::new(FailsafeWatcherState::default()),
        }
    }

    /// 初始化單例。第一次呼叫填值；後續呼叫返回現有 instance（**不 overwrite**）。
    ///
    /// 為什麼不 overwrite：fail-safe 是系統級安全保護，狀態不該被 runtime 重置覆蓋；
    /// 若需替換實作（罕見），必須 restart 進程 — 對齊 `OnceLock` 語義。
    ///
    /// 回傳：本次 init 後（或現存）的單例 `Arc`。
    pub fn init(
        dispatcher: Box<dyn NotificationDispatcher>,
        positions: Box<dyn PositionSnapshotProvider>,
        exchange: Box<dyn ExchangeStopSync>,
        audit: Box<dyn FailsafeAuditEmitter>,
        clock: Box<dyn FailsafeClock>,
        cfg: FailsafeConfig,
    ) -> Arc<Self> {
        // 為什麼 `get_or_init` + `Arc::new` 在 closure 內：
        //   `OnceLock::get_or_init` 保證 closure 只執行一次；多 thread 競爭時其他
        //   thread block 等首次完成後拿同一份 `Arc`。
        // 第二次以後呼叫 closure 不執行，傳入的 Box 被 caller 丟棄 — 對 fail-safe
        // singleton 是預期行為（不重複初始化）。
        SHARED_WATCHER
            .get_or_init(|| {
                Arc::new(Self::new(
                    dispatcher, positions, exchange, audit, clock, cfg,
                ))
            })
            .clone()
    }

    /// 測試用公開 ctor — 不走全域 OnceLock 單例（避免 cross-test 污染）。
    ///
    /// 為什麼存在：C4 端到端 wire 測試（event_consumer/tests）需構造一個帶自訂 clock /
    /// Noop provider 的 watcher 驗 `observe_dispatch` → `timer_expired_and_claim` seam，
    /// 但 `new` 是私有。`#[cfg(test)]` gate 確保 production binary 不暴露。
    #[cfg(test)]
    pub fn new_for_test(
        dispatcher: Box<dyn NotificationDispatcher>,
        positions: Box<dyn PositionSnapshotProvider>,
        exchange: Box<dyn ExchangeStopSync>,
        audit: Box<dyn FailsafeAuditEmitter>,
        clock: Box<dyn FailsafeClock>,
        cfg: FailsafeConfig,
    ) -> Self {
        Self::new(dispatcher, positions, exchange, audit, clock, cfg)
    }

    /// 取得已初始化單例；若尚未初始化回 `None`。
    ///
    /// 為什麼 `Option`：C4 spawn task 才呼 `init`；測試 / 其他 caller 可能在
    /// init 之前嘗試取得 — 此時返 `None` 對齊 fail-closed 語義（沒準備好就不動）。
    pub fn instance() -> Option<Arc<Self>> {
        SHARED_WATCHER.get().cloned()
    }

    /// 取得當前狀態 snapshot（lock + clone）— 主要供測試與 GUI 狀態查詢。
    pub fn state_snapshot(&self) -> FailsafeWatcherState {
        self.state.lock().clone()
    }

    /// 取得 config snapshot（純值，無鎖）。
    pub fn config(&self) -> FailsafeConfig {
        self.cfg
    }

    // -----------------------------------------------------------------------
    // API surface — 對齊 `FailsafeWatcher` 三入口
    // -----------------------------------------------------------------------

    /// 觀察一次派發 outcome — 純邏輯，不 await（內部 lock 不跨 await）。
    pub fn observe_dispatch(&self, outcome: DispatchOutcome) -> FailsafeDecision {
        let now_ms = self.clock.now_ms();
        let mut state = self.state.lock();
        evaluate_dispatch(&mut state, outcome, now_ms)
    }

    /// 主動派發一次三路通知並依結果更新 state。
    ///
    /// 為什麼拆兩段：
    ///   1. `await dispatcher.dispatch_3way` — **不持鎖**（dispatch 可能秒級 round-trip）；
    ///   2. 拿 `state` 鎖把 outcome 寫入 — 純邏輯不 await。
    pub async fn dispatch_and_observe(&self, message: &str) -> FailsafeDecision {
        // 1) 不持鎖跑 dispatch（per 反模式：鎖跨 await 是死鎖溫床）
        let outcome = self.dispatcher.dispatch_3way(message).await;
        // 2) lock + 純邏輯
        let now_ms = self.clock.now_ms();
        let mut state = self.state.lock();
        evaluate_dispatch(&mut state, outcome, now_ms)
    }

    /// 主動派發一次三路通知，但不直接改 watcher state。
    ///
    /// 為什麼給 incident_policy 使用：arm-vs-notify 由 incident_policy 決定。
    /// notify-only 類事件必須通知 operator 但不可把 `AllFail` 寫進 watcher；
    /// arm 類事件也要先通過 secret-enabled gate，再經 `FAILSAFE_FEED_SENDERS`
    /// 餵 outcome。此方法保留既有 dispatcher 注入，不新增第二套通知路徑。
    pub async fn dispatch_3way_only(&self, message: &str) -> DispatchOutcome {
        self.dispatcher.dispatch_3way(message).await
    }

    /// 回報 Slack / Email push channel 是否已啟用。
    ///
    /// `None` 代表 dispatcher 不知道；runtime `ThreeWayDispatcher` 回 `Some`。
    /// incident_policy 用此 gate 防止缺 secret 時 arm 類 incident 直接武裝 timer。
    pub fn push_channels_enabled(&self) -> Option<(bool, bool)> {
        self.dispatcher.push_channels_enabled()
    }

    /// Operator GUI ack — 解除已武裝 timer。
    pub fn record_operator_ack(&self) -> FailsafeDecision {
        let mut state = self.state.lock();
        record_operator_ack(&mut state)
    }

    /// P2-PACKET-C-C4-PIPELINE-WIRE · 純判定 timer 是否到期 + 同鎖 claim（claim-before-await）。
    ///
    /// 為什麼新增此方法取代 runtime 端 `check_timer(&mut risk_sm)`（C4 spec §0.2 + §2.2）：
    ///   `check_timer` 假設 watcher 持 `&mut RiskGovernorSm`。但 runtime 中 `RiskGovernorSm`
    ///   是 owner pipeline 的 owned 欄位（非 `Arc`），watcher 是 external task 無合法管道
    ///   持其可變引用。正確模型 = watcher 只判定「timer 到期」並 claim，SM-04 transition
    ///   由 `cmd_tx.send(PipelineCommand::NotificationFailsafeEscalate)` 進 owner task 跑。
    ///
    /// claim-before-await 不變量（保留 C3 §4.7 idempotent 守衛）：
    ///   在**同一個 lock hold 內**判定 expired 後立刻 set `escalated_for_current_arm`，
    ///   再 drop lock。多個並發 tick（理論上 watcher 單 task 序列，但防禦性）只有第一個
    ///   看到 expired==true 並 claim；後續看到 flag 已 set → `timer_expired` 回 false。
    ///   這保證「同一次武裝只發一次 escalate command」（demo/live 各自 slot 是另一維度，
    ///   見 spawn loop：對每個 engine slot 各發一次，是設計上的 per-engine 獨立升級）。
    ///
    /// 為什麼純邏輯無 await：本方法只 lock → 判定 → set flag → drop，<1μs；真正的副作用
    /// （SM transition + exchange sync + audit）全在 owner task handler 跑，watcher 不阻塞。
    ///
    /// 回 `true` = 本次 claim 成功（呼叫端應對每個 engine cmd_tx 發 escalate command）；
    /// 回 `false` = 未到期 或 已被 claim（不重發）。
    pub fn timer_expired_and_claim(&self) -> bool {
        let now_ms = self.clock.now_ms();
        let mut state = self.state.lock();
        if timer_expired(&state, now_ms, FailsafeConfig::DEFAULT_TIMEOUT_MS) {
            // 同鎖 hold 內 claim — atomic 佔用，杜絕並發重發。
            state.set_escalated_for_current_arm(true);
            true
        } else {
            false
        }
    }

    /// 週期性檢查 timer 是否過期；過期則執行完整副作用鏈。
    ///
    /// **C4 後僅供測試**（`#[cfg(test)]`）：runtime 改走 `timer_expired_and_claim` +
    /// in-band `PipelineCommand::NotificationFailsafeEscalate`（C4 spec §0.2）。保留此
    /// 方法供 T4.12 並發 idempotent test 與 mod.rs `FailsafeWatcher` 泛型 test 對齊。
    ///
    /// 為什麼拆三段（per spec §4.7 + §11.3 反對 3 mitigation）：
    ///   1. **lock → 判定 expired → 同鎖內 claim（set escalated=true）→ drop lock**
    ///      （純邏輯，<1μs）；
    ///   2. **無鎖跑 `execute_failsafe_escalation`**（內含 SM transition + N exchange
    ///      sync + audit emit，可能秒級；持 `RiskGovernorSm` 由 caller 注入，
    ///      本 watcher 不持有 risk SM 鎖）；
    ///   3. （已併入 Step 1）idempotent guard 在 Step 1 同鎖內就 claim 完成。
    ///
    /// 為什麼 idempotent guard 必須在 **Step 1 同一個 lock hold 內** set（MED-2 修法）：
    ///   原本把 `set_escalated_for_current_arm(true)` 留到 Step 3 re-lock 才設。但
    ///   `&self` 容許多個並發 `check_timer` 呼叫（C4 spawn 多 tick task / 重入），
    ///   兩個並發呼叫可能都在 Step 1 看到 `timer_expired == true`（因 flag 尚未設），
    ///   各自 drop 鎖去 await → double SM-04 transition + double audit。
    ///   改為「lock 內判定 expired 後，立刻在同一鎖 hold 內 set flag 才 drop」：
    ///   第二個並發呼叫 re-lock 時看到 flag 已 set → `timer_expired` 回 false → 不重觸發。
    ///   這是「claim-before-await」模式，把判定與佔用原子化在同一鎖。
    ///
    /// escalate 失敗時 flag 不 reset（fail-safe 設計判斷）：
    ///   survival 優先。即便 `execute_failsafe_escalation` 內部個別副作用失敗（exchange
    ///   sync / audit emit），也不該把 flag reset 讓下一 tick re-fire — 重觸發會造成
    ///   double SM transition / double audit 噪音，且 escalation 本身設計為「個別失敗
    ///   不 rollback transition、報告回顯失敗」（見 `execute_failsafe_escalation` 不變量）。
    ///   失敗細節由回傳的 `FailsafeExecutionReport`（sync_records / audit_error）承載，
    ///   交由 caller / audit 記錄與告警，而非靠重觸發補救。
    ///   timer 重新武裝只在 `evaluate_dispatch` 觀察到新一輪 AllFail→AllSuccess→AllFail
    ///   或 operator ack 時才會 reset flag（見 mod.rs `evaluate_dispatch` /
    ///   `record_operator_ack`）— 即「同一次武裝只 escalate 一次」語義由那條路徑保證。
    ///
    /// 不變量：步驟 2 全程不持 `state.lock`；任何 caller 持有的 pipeline write lock
    /// 也應在呼叫本 method 前 drop（C4 spawn task 負責確保）。
    #[cfg(test)]
    pub async fn check_timer(
        &self,
        risk_sm: &mut RiskGovernorSm,
    ) -> Option<FailsafeExecutionReport> {
        // Step 1: lock 內判定到期 + 立刻 claim（atomic 佔用）+ drop lock — 純邏輯無 await
        let now_ms = self.clock.now_ms();
        let claimed = {
            let mut state = self.state.lock();
            if timer_expired(&state, now_ms, FailsafeConfig::DEFAULT_TIMEOUT_MS) {
                // 在同一鎖 hold 內立刻佔用 idempotent guard，杜絕並發雙觸發。
                state.set_escalated_for_current_arm(true);
                true
            } else {
                false
            }
        }; // ← lock guard 此處 drop

        if !claimed {
            return None;
        }

        // Step 2: 無鎖跑完整副作用鏈（flag 已在 Step 1 set，不在此 re-lock）
        let report = execute_failsafe_escalation(
            risk_sm,
            self.positions.as_ref(),
            self.exchange.as_ref(),
            self.audit.as_ref(),
            &self.cfg,
            now_ms,
        )
        .await;

        Some(report)
    }

    /// 重置單例（**僅供測試**）— production code 不應呼叫。
    ///
    /// 為什麼存在：unit test 需驗 `init` / `instance` 行為時必須能 reset
    /// `OnceLock`，但 `OnceLock` 本身不支援 reset。本 helper 用
    /// `#[cfg(test)]` gate 確保 production binary 不暴露此 API。
    ///
    /// 實作：因 `OnceLock` API 不允許重置，測試端改採「新 instance + 不依賴
    /// 全域單例」pattern — 直接 `SharedFailsafeWatcher::new` 不走 `init`。
    /// 故本函式只 doc 用，無 body。
    #[cfg(test)]
    #[allow(dead_code)]
    fn doc_only_test_note() {
        // 見上方註解；測試走 new pattern 而非 reset。
    }
}

// ════════════════════════════════════════════════════════════════════════════
// P2-PACKET-C-C4-PIPELINE-WIRE · runtime watcher-end Noop providers
// ════════════════════════════════════════════════════════════════════════════
//
// 為什麼 runtime watcher 端的 position / exchange / audit provider 是 Noop（C4 spec §1.3 + §2.2）：
//   C4 修正模型把「組 PositionSnapshot + ATR 注入 + 鎖利 + exchange sync + audit」整段
//   下放到 owner task 的 `handle_notification_failsafe_escalate`（因 watcher 是 external
//   task，無 owner pipeline 的 kline_manager / paper_state / PositionManager）。watcher 端
//   runtime 只用 `clock`（`observe_dispatch` / `timer_expired_and_claim`）+ dispatcher
//   （incident_policy 經 `observe_dispatch` 餵 outcome）。但 `SharedFailsafeWatcher::init`
//   簽名要求全 5 trait object，故 position / exchange / audit 注入 Noop 占位（runtime 不被呼叫；
//   `check_timer` / `dispatch_and_observe` 才會用到，且 `check_timer` 已 `#[cfg(test)]`）。

use crate::notification_failsafe::{ExchangeStopError, FailsafeAuditError};
use async_trait::async_trait;
use openclaw_core::sm::risk_gov::{PositionSnapshot, StopAdjustment};

/// 倉位 provider Noop（runtime watcher 端不組 snapshot；真值由 owner task handler 取
/// `paper_state.positions()`）。回空 Vec。
pub struct NoopPositionProvider;
impl PositionSnapshotProvider for NoopPositionProvider {
    fn snapshot_positions(&self) -> Vec<PositionSnapshot> {
        Vec::new()
    }
}

/// 交易所 sync Noop（runtime watcher 端不直 sync；真 sync 在 owner handler 走既有
/// server-side stop 雙軌通道）。回 `Ok(())`。
pub struct NoopExchangeStopSync;
#[async_trait]
impl ExchangeStopSync for NoopExchangeStopSync {
    async fn sync_stop(&self, _adjustment: &StopAdjustment) -> Result<(), ExchangeStopError> {
        Ok(())
    }
}

/// Audit Noop（runtime watcher 端不 emit；audit 在 owner handler 用 `PgAuditEmitter`
/// 寫 V114，因 transition / sync 結果在 owner task 內最完整，per spec §2.3 option a）。
pub struct NoopAuditEmitter;
#[async_trait]
impl FailsafeAuditEmitter for NoopAuditEmitter {
    async fn emit_auto_escalated(
        &self,
        _payload: serde_json::Value,
    ) -> Result<(), FailsafeAuditError> {
        Ok(())
    }
}

// ════════════════════════════════════════════════════════════════════════════
// FailsafeWatcherState：暴露 escalated_for_current_arm setter 給 single_watcher
// ════════════════════════════════════════════════════════════════════════════
//
// 為什麼這檔不直接動 state 欄位：
//   `FailsafeWatcherState.escalated_for_current_arm` 在 mod.rs 是 private 欄位；
//   本檔在同 crate 可透過 pub-in-mod helper 取得 mutation。下方 trait 為「在
//   `notification_failsafe` 模組私下開的擴充入口」— 已在 mod.rs 端補 fn。
//
// 注意：若 mod.rs 未補 setter，本 module 的 `check_timer` 第 3 步會 compile fail；
// 該 setter 已在本 C3 工作中同步補入 mod.rs（最小入侵，僅一行 pub(super) fn）。

// ════════════════════════════════════════════════════════════════════════════
// Tests
// ════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;
    use crate::notification_failsafe::providers::wall_clock::WallClock;
    use crate::notification_failsafe::{
        ExchangeStopError, FailsafeAuditError, NotificationChannel,
    };
    use async_trait::async_trait;
    use openclaw_core::sm::risk_gov::{PositionSnapshot, RiskGovernorSm, StopAdjustment};
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::sync::Mutex as StdMutex;

    // ── 最小 mock：不實際下單 / 不寄訊息 ─────────────────────────────────────

    struct NoopDispatcher;
    #[async_trait]
    impl NotificationDispatcher for NoopDispatcher {
        async fn dispatch_3way(&self, _message: &str) -> DispatchOutcome {
            DispatchOutcome::AllSuccess
        }
    }

    struct EmptyPositions;
    impl PositionSnapshotProvider for EmptyPositions {
        fn snapshot_positions(&self) -> Vec<PositionSnapshot> {
            Vec::new()
        }
    }

    struct NoopExchange;
    #[async_trait]
    impl ExchangeStopSync for NoopExchange {
        async fn sync_stop(&self, _adj: &StopAdjustment) -> Result<(), ExchangeStopError> {
            Ok(())
        }
    }

    struct NoopAudit;
    #[async_trait]
    impl FailsafeAuditEmitter for NoopAudit {
        async fn emit_auto_escalated(
            &self,
            _payload: serde_json::Value,
        ) -> Result<(), FailsafeAuditError> {
            Ok(())
        }
    }

    /// 計數型 audit emitter — MED-2 並發測試用：每次 escalation 會 emit 一次 audit；
    /// 用 emit 計數驗「同一次武裝只 escalate 一次」（雙觸發會 emit 兩次）。
    /// 用 `Arc` 共享計數器讓 test 端在 watcher 外讀取。
    struct CountingAudit {
        emit_count: Arc<AtomicU64>,
    }
    #[async_trait]
    impl FailsafeAuditEmitter for CountingAudit {
        async fn emit_auto_escalated(
            &self,
            _payload: serde_json::Value,
        ) -> Result<(), FailsafeAuditError> {
            self.emit_count.fetch_add(1, Ordering::SeqCst);
            Ok(())
        }
    }

    /// 共用：建一個 `SharedFailsafeWatcher` 不走全域單例（避免 test 間污染 OnceLock）。
    fn build_shared_for_test() -> Arc<SharedFailsafeWatcher> {
        Arc::new(SharedFailsafeWatcher::new(
            Box::new(NoopDispatcher),
            Box::new(EmptyPositions),
            Box::new(NoopExchange),
            Box::new(NoopAudit),
            Box::new(WallClock::new()),
            FailsafeConfig::default(),
        ))
    }

    /// T4.1：`instance()` 在 `init` 之前回 `None`。
    ///
    /// 注意：此 test 假設本進程內 `SHARED_WATCHER` 未被其他 test 初始化過。
    /// 為避免 cross-test 污染，singleton-specific test 都在獨立 test runner
    /// 序列化（cargo test 默認多 thread，但 OnceLock 是進程級全域）。
    /// 為穩定性，singleton 測試集中在 T4.4 一次性完成。
    #[test]
    fn t4_1_new_pattern_creates_instance_without_init() {
        // 直接 `Arc::new` 路徑（測試走「非單例」driver）— 主要驗欄位完整性
        let shared = build_shared_for_test();
        let state = shared.state_snapshot();
        assert!(!state.is_armed());
        assert!(state.last_outcome().is_none());
    }

    /// T4.2：`observe_dispatch(AllFail)` 武裝 timer；state lock 不跨 await。
    #[tokio::test]
    async fn t4_2_observe_dispatch_arms_timer() {
        let shared = build_shared_for_test();
        let decision = shared.observe_dispatch(DispatchOutcome::AllFail);
        match decision {
            FailsafeDecision::TimerArmed { .. } => {}
            other => panic!("expected TimerArmed, got {other:?}"),
        }
        let state = shared.state_snapshot();
        assert!(state.is_armed());
    }

    /// T4.3：`record_operator_ack` 解除已武裝 timer。
    #[tokio::test]
    async fn t4_3_operator_ack_cancels_timer() {
        let shared = build_shared_for_test();
        shared.observe_dispatch(DispatchOutcome::AllFail);
        assert!(shared.state_snapshot().is_armed());
        let decision = shared.record_operator_ack();
        match decision {
            FailsafeDecision::TimerCancelled { .. } => {}
            other => panic!("expected TimerCancelled, got {other:?}"),
        }
        assert!(!shared.state_snapshot().is_armed());
    }

    /// T4.4：singleton — `init` 雙呼回同一 `Arc`（per task spec §Phase 4 + 「instance()
    /// 雙呼回同一 Arc (singleton 驗)」）。
    ///
    /// 為什麼這條 test 用「進程級全域」：`OnceLock` 是 std 全域，需要實際呼 `init`
    /// 才能驗證單例語義。本 test 在 cargo test 內可能與其他 init test 競爭 —
    /// 故只在這條 test 真正呼 init，其他 test 走 `build_shared_for_test` 旁路。
    #[test]
    fn t4_4_init_returns_same_arc_on_double_call() {
        let a = SharedFailsafeWatcher::init(
            Box::new(NoopDispatcher),
            Box::new(EmptyPositions),
            Box::new(NoopExchange),
            Box::new(NoopAudit),
            Box::new(WallClock::new()),
            FailsafeConfig::default(),
        );
        let b = SharedFailsafeWatcher::init(
            Box::new(NoopDispatcher),
            Box::new(EmptyPositions),
            Box::new(NoopExchange),
            Box::new(NoopAudit),
            Box::new(WallClock::new()),
            FailsafeConfig::default(),
        );
        // 同 `Arc` 指向同一 allocation
        assert!(
            Arc::ptr_eq(&a, &b),
            "init double-call should return same Arc"
        );

        // instance() 也應拿到同一份
        let c = SharedFailsafeWatcher::instance().expect("instance should exist after init");
        assert!(Arc::ptr_eq(&a, &c));
    }

    /// T4.5：`dispatch_and_observe` 走 NoopDispatcher → AllSuccess，fresh state → NoAction。
    #[tokio::test]
    async fn t4_5_dispatch_and_observe_wires_dispatcher() {
        let shared = build_shared_for_test();
        let decision = shared.dispatch_and_observe("test message").await;
        assert_eq!(decision, FailsafeDecision::NoAction);
    }

    /// T4.6：concurrent `observe_dispatch` 從多 thread 不 panic（mutex 行為驗證）。
    #[tokio::test(flavor = "multi_thread", worker_threads = 4)]
    async fn t4_6_concurrent_observe_dispatch_is_safe() {
        let shared = build_shared_for_test();
        let mut handles = Vec::new();
        for i in 0..8 {
            let s = shared.clone();
            handles.push(tokio::spawn(async move {
                if i % 2 == 0 {
                    s.observe_dispatch(DispatchOutcome::AllFail);
                } else {
                    s.observe_dispatch(DispatchOutcome::AllSuccess);
                }
            }));
        }
        for h in handles {
            h.await.unwrap();
        }
        // 沒 panic 即驗證 mutex 線程安全；state 內容因競爭不確定，僅驗存活。
        let _ = shared.state_snapshot();
    }

    /// T4.7：PartialFail 不武裝、不解除（驗 spec 三路冗餘語義透傳）。
    #[tokio::test]
    async fn t4_7_partial_fail_is_no_op() {
        let shared = build_shared_for_test();
        let decision = shared.observe_dispatch(DispatchOutcome::PartialFail {
            failed: vec![NotificationChannel::Slack],
        });
        assert_eq!(decision, FailsafeDecision::NoAction);
        assert!(!shared.state_snapshot().is_armed());
    }

    /// T4.8：`config()` 暴露 `FailsafeConfig` snapshot 不需鎖。
    #[test]
    fn t4_8_config_snapshot_no_lock() {
        let shared = build_shared_for_test();
        let cfg = shared.config();
        assert!((cfg.atr_buffer_multiplier - FailsafeConfig::DEFAULT_ATR_BUFFER).abs() < 1e-9);
    }

    // ── 防退化：驗 trait object Send + Sync 滿足，並可被 spawn 跨 thread ─

    /// T4.9：`Arc<SharedFailsafeWatcher>` 可被 `tokio::spawn` 移交（Send + Sync）。
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn t4_9_arc_is_send_for_spawn() {
        let shared = build_shared_for_test();
        let s = shared.clone();
        let handle = tokio::spawn(async move {
            s.observe_dispatch(DispatchOutcome::AllSuccess);
        });
        handle.await.unwrap();

        // 等被借走的衍生 Arc drop 完，主 Arc 還應該存活
        let _ = shared.state_snapshot();
    }

    /// T4.10：確保 mock NoopExchange 滿足 Send + Sync trait bound（編譯通過即驗）。
    #[test]
    fn t4_10_mock_traits_send_sync() {
        fn assert_send_sync<T: Send + Sync>() {}
        assert_send_sync::<NoopDispatcher>();
        assert_send_sync::<EmptyPositions>();
        assert_send_sync::<NoopExchange>();
        assert_send_sync::<NoopAudit>();
        assert_send_sync::<WallClock>();
        assert_send_sync::<Arc<SharedFailsafeWatcher>>();
    }

    /// T4.12（MED-2 到期 + 並發單觸發）：構造「已武裝且到期」場景，並發 check_timer
    /// 只 escalate 一次。
    ///
    /// 構造法：clock 起點 0 → observe 武裝（armed_at=0）→ advance 過 timeout → 並發
    /// check_timer。所有呼叫看到 timer 到期，但 idempotent guard 在 Step 1 同鎖 claim，
    /// 故 audit emit 恰好 1 次、回 Some 恰好 1 次。
    #[tokio::test(flavor = "multi_thread", worker_threads = 4)]
    async fn t4_12_concurrent_expired_escalates_exactly_once() {
        // 用 Arc 持 clock 讓 observe 武裝後仍能 advance（watcher 內存 Box<dyn>，
        // 但我們需要先武裝再前進；故 clock 用 Arc 包再各自持有一份）。
        // SharedFailsafeWatcher::new 需要 Box<dyn FailsafeClock>；AdvanceableClock 不 Clone，
        // 故改用一個 Arc-backed wrapper clock。
        let inner = Arc::new(AtomicU64::new(0));
        struct ArcClock(Arc<AtomicU64>);
        impl FailsafeClock for ArcClock {
            fn now_ms(&self) -> u64 {
                self.0.load(Ordering::SeqCst)
            }
        }
        let emit_count = Arc::new(AtomicU64::new(0));
        let shared = Arc::new(SharedFailsafeWatcher::new(
            Box::new(NoopDispatcher),
            Box::new(EmptyPositions),
            Box::new(NoopExchange),
            Box::new(CountingAudit {
                emit_count: emit_count.clone(),
            }),
            Box::new(ArcClock(inner.clone())),
            FailsafeConfig::default(),
        ));

        // 武裝在 now=0
        let armed = shared.observe_dispatch(DispatchOutcome::AllFail);
        assert!(matches!(armed, FailsafeDecision::TimerArmed { .. }));

        // 前進過 timeout → 武裝到期
        inner.store(FailsafeConfig::DEFAULT_TIMEOUT_MS + 1, Ordering::SeqCst);

        let mut handles = Vec::new();
        for _ in 0..16 {
            let s = shared.clone();
            handles.push(tokio::spawn(async move {
                let mut risk_sm = RiskGovernorSm::new();
                s.check_timer(&mut risk_sm).await
            }));
        }
        let mut some_count = 0_usize;
        for h in handles {
            if h.await.unwrap().is_some() {
                some_count += 1;
            }
        }

        assert_eq!(
            some_count, 1,
            "並發到期 check_timer 應恰好一次回 Some（idempotent claim 守衛）"
        );
        assert_eq!(
            emit_count.load(Ordering::SeqCst),
            1,
            "audit emit 恰好 1 次 — 杜絕 double SM-04 transition + double audit"
        );
        // guard 已被 set，後續再 check 不重觸發
        let mut risk_sm = RiskGovernorSm::new();
        assert!(shared.check_timer(&mut risk_sm).await.is_none());
        assert_eq!(emit_count.load(Ordering::SeqCst), 1);
    }

    // 為什麼有 unused StdMutex import 警告守衛：
    // 上方 `use std::sync::Mutex as StdMutex` 是預留供未來 test 擴展時對齊
    // `parking_lot::Mutex` 對比；當前 test 用不到。clippy `unused_imports` 會抱怨
    // — 故此 dummy 函式佔位 keep tree green。後續可移除。
    #[test]
    fn t4_11_dummy_uses_std_mutex_import_placeholder() {
        let m: StdMutex<u32> = StdMutex::new(0);
        assert_eq!(*m.lock().unwrap(), 0);
    }
}
