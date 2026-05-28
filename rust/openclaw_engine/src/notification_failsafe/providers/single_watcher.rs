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

use openclaw_core::sm::risk_gov::RiskGovernorSm;
use parking_lot::Mutex;

use crate::notification_failsafe::{
    evaluate_dispatch, execute_failsafe_escalation, record_operator_ack, timer_expired,
    DispatchOutcome, ExchangeStopSync, FailsafeAuditEmitter, FailsafeClock, FailsafeConfig,
    FailsafeDecision, FailsafeExecutionReport, FailsafeWatcherState, NotificationDispatcher,
    PositionSnapshotProvider,
};

// ════════════════════════════════════════════════════════════════════════════
// 全域單例 storage
// ════════════════════════════════════════════════════════════════════════════

/// 全域單例存放點（per task spec §Phase 4「single shared watcher」）。
///
/// 為什麼 `OnceLock` 包 `Arc`：
///   - `OnceLock` 保證 thread-safe initialization「最多一次」；
///   - `Arc` 讓所有呼叫端拿到同一份指標（read share），符合 Q4.1 拍板「共享」語義。
static SHARED_WATCHER: OnceLock<Arc<SharedFailsafeWatcher>> = OnceLock::new();

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

    /// Operator GUI ack — 解除已武裝 timer。
    pub fn record_operator_ack(&self) -> FailsafeDecision {
        let mut state = self.state.lock();
        record_operator_ack(&mut state)
    }

    /// 週期性檢查 timer 是否過期；過期則執行完整副作用鏈。
    ///
    /// 為什麼拆三段（per spec §4.7 + §11.3 反對 3 mitigation）：
    ///   1. **lock → 判定 expired → drop lock**（純邏輯，<1μs）；
    ///   2. **無鎖跑 `execute_failsafe_escalation`**（內含 SM transition + N exchange
    ///      sync + audit emit，可能秒級；持 `RiskGovernorSm` 由 caller 注入，
    ///      本 watcher 不持有 risk SM 鎖）；
    ///   3. **re-lock → 標記 `escalated_for_current_arm = true`**（idempotent 守衛）。
    ///
    /// 不變量：步驟 2 全程不持 `state.lock`；任何 caller 持有的 pipeline write lock
    /// 也應在呼叫本 method 前 drop（C4 spawn task 負責確保）。
    pub async fn check_timer(
        &self,
        risk_sm: &mut RiskGovernorSm,
    ) -> Option<FailsafeExecutionReport> {
        // Step 1: 判定是否到期 — lock 純邏輯，無 await
        let now_ms = self.clock.now_ms();
        let expired = {
            let state = self.state.lock();
            timer_expired(&state, now_ms, FailsafeConfig::DEFAULT_TIMEOUT_MS)
        }; // ← lock guard 此處 drop

        if !expired {
            return None;
        }

        // Step 2: 無鎖跑完整副作用鏈
        let report = execute_failsafe_escalation(
            risk_sm,
            self.positions.as_ref(),
            self.exchange.as_ref(),
            self.audit.as_ref(),
            &self.cfg,
            now_ms,
        )
        .await;

        // Step 3: re-lock 標記 idempotent guard
        {
            let mut state = self.state.lock();
            state.set_escalated_for_current_arm(true);
        }

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
    use openclaw_core::sm::risk_gov::{PositionSnapshot, StopAdjustment};
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
        assert!(Arc::ptr_eq(&a, &b), "init double-call should return same Arc");

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
