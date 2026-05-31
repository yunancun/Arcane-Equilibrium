//! P2-PACKET-C-C4-PIPELINE-WIRE — 通知 fail-safe in-band wire 端到端測試。
//!
//! 模塊用途（C4 spec §5.2「真 wire 證明」，非偽 prod）：
//!   證明「watcher timer 到期 → claim → in-band PipelineCommand → owner task handler →
//!   SM-04 Defensive transition → active lock-profit 鎖利 → 交易所雙軌 sync → report」
//!   整鏈真接上、非 dead-wire。不引入 testcontainers PG（Mac 開發環境）：audit 路徑用
//!   `audit_pool=None`（fail-soft noop），其餘鏈路全真實。
//!
//! C4 後續接上 incident trigger 後，本檔同時保留 watcher seam 測與真 producer path
//! 測：`incident_policy` dispatch → outcome feed → watcher timer claim → in-band command
//! handler → SM-04 Defensive。
//!
//! ref:
//!   - docs/execution_plan/specs/2026-05-29--packet-c-c4-pipeline-wire-spec.md §5.2
//!   - handlers/notification_failsafe_escalate.rs::handle_notification_failsafe_escalate
//!   - providers/single_watcher.rs::timer_expired_and_claim

use super::{make_test_writer, seed_atr_klines};
use crate::notification_failsafe::incident_policy::{
    report_incident_with_test_watcher, IncidentClass, IncidentDispatchMode, IncidentPolicyResult,
};
use crate::notification_failsafe::providers::single_watcher::{
    FailsafeFeedSenders, NoopAuditEmitter, NoopExchangeStopSync, NoopPositionProvider,
    SharedFailsafeWatcher,
};
use crate::notification_failsafe::{DispatchOutcome, FailsafeConfig, FailsafeDecision};
use crate::tick_pipeline::{PipelineCommand, PipelineKind, StopRequest, TickPipeline};
use openclaw_core::sm::risk_gov::RiskLevel;

/// 建一個 Demo 模式 pipeline（fail-safe 對 demo/live 升級；paper 結構性排除）。
fn make_demo_pipeline() -> TickPipeline {
    TickPipeline::with_kind(&["BTCUSDT", "ETHUSDT"], 10_000.0, PipelineKind::Demo)
}

/// C4-d 主測：owner task in-band handler 端到端 — Demo 倉位 + ATR → SM-04 升級 +
/// 鎖利 StopRequest 經既有雙軌通道發出 + report transition Normal→Defensive。
#[tokio::test]
async fn e2e_c4_failsafe_inband_escalate_demo() {
    let mut p = make_demo_pipeline();
    let mut w = make_test_writer();

    // 捕獲 owner task 經 stop channel 發出的交易所 conditional SL（雙軌 sync 證明）。
    let (stop_tx, mut stop_rx) = tokio::sync::mpsc::unbounded_channel::<StopRequest>();
    p.set_stop_channel(stop_tx);

    // 開一個多頭倉（demo 真值，paper_state.positions() 可見）。
    p.paper_state.set_latest_price("BTCUSDT", 50_000.0);
    p.paper_state
        .apply_fill("BTCUSDT", true, 0.01, 50_000.0, 0.0, 0, "external_test");
    assert!(
        p.paper_state.get_position("BTCUSDT").is_some(),
        "test setup: position opened"
    );

    // 種入 1m K 線供 owner handler 算絕對 ATR14（>= 15 closed bars）。
    seed_atr_klines(&mut p, "BTCUSDT", 50_000.0, 500.0);

    // 升級前 baseline = Normal。
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Normal);

    // 直接呼 owner task in-band handler（loop_handlers 攔截後實際呼叫的同一函數）。
    let (tx, rx) = tokio::sync::oneshot::channel();
    crate::event_consumer::handlers::handle_notification_failsafe_escalate(
        "notification_3way_fail_1h_timeout".to_string(),
        tx,
        &mut p,
        &mut w,
        None, // audit_pool=None → fail-soft noop（不接 PG，Mac 開發環境）。
    )
    .await;
    let report_json = rx.await.expect("handler responded").expect("report ok");

    // 1) SM-04 transition Normal → Defensive。
    assert_eq!(
        p.governance.risk.snapshot_level(),
        RiskLevel::Defensive,
        "fail-safe in-band escalate 必把 demo SM 升到 Defensive"
    );

    // 2) report 反映 transition。
    let report: serde_json::Value = serde_json::from_str(&report_json).expect("report json");
    assert_eq!(report["from_level"], "NORMAL");
    assert_eq!(report["to_level"], "DEFENSIVE");
    assert_eq!(report["transition_succeeded"], true);
    assert!(
        report["adjustments_count"].as_u64().unwrap() >= 1,
        "有 ATR 的倉應生成至少 1 個鎖利 StopAdjustment"
    );

    // 3) 交易所雙軌 sync：stop channel 收到鎖利 StopRequest（demo 走真實 sync 路徑）。
    let stop_req = stop_rx
        .try_recv()
        .expect("owner handler 應發 StopRequest 到雙軌通道");
    assert_eq!(stop_req.symbol, "BTCUSDT");
    assert!(stop_req.is_long, "多頭倉 StopRequest is_long=true");
    // 鎖利公式 Buy: new_sl = entry + atr × 0.5 = 50000 + 500×0.5 = 50250 > entry。
    assert!(
        stop_req.stop_loss > 50_000.0,
        "Buy 倉鎖利 SL 應拉到 entry 上方（鎖住 unrealized）"
    );
}

/// C4-d watcher seam 測：`observe_dispatch(AllFail)` 武裝 → 推進時鐘過 timeout →
/// `timer_expired_and_claim()` 回 true 恰一次（claim-before-await idempotent）。
/// 證明 watcher 端「outcome → timer → claim」這半邊真接上（command send 由 spawn loop
/// 對 cmd_tx slot 完成，spawn loop 已在 main_boot_tasks wire；此處驗判定+claim 不變量）。
#[tokio::test]
async fn e2e_c4_watcher_allfail_arms_then_claims_once() {
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::sync::Arc;

    // Arc-backed clock 讓 observe 武裝後仍能推進。
    struct ArcClock(Arc<AtomicU64>);
    impl crate::notification_failsafe::FailsafeClock for ArcClock {
        fn now_ms(&self) -> u64 {
            self.0.load(Ordering::SeqCst)
        }
    }
    struct NoopDispatcher;
    #[async_trait::async_trait]
    impl crate::notification_failsafe::NotificationDispatcher for NoopDispatcher {
        async fn dispatch_3way(&self, _m: &str) -> DispatchOutcome {
            DispatchOutcome::AllSuccess
        }
    }

    let clock = Arc::new(AtomicU64::new(0));
    let watcher = Arc::new(SharedFailsafeWatcher::new_for_test(
        Box::new(NoopDispatcher),
        Box::new(crate::notification_failsafe::providers::single_watcher::NoopPositionProvider),
        Box::new(crate::notification_failsafe::providers::single_watcher::NoopExchangeStopSync),
        Box::new(crate::notification_failsafe::providers::single_watcher::NoopAuditEmitter),
        Box::new(ArcClock(clock.clone())),
        FailsafeConfig::default(),
    ));

    // 1) AllFail 武裝 timer（模擬 incident_policy 餵 outcome）。
    let decision = watcher.observe_dispatch(DispatchOutcome::AllFail);
    assert!(matches!(decision, FailsafeDecision::TimerArmed { .. }));

    // 2) 未到期 → claim 回 false（不誤升）。
    assert!(
        !watcher.timer_expired_and_claim(),
        "未過 1h timeout 不得 claim（防誤升 Defensive 平倉）"
    );

    // 3) 推進過 1h timeout → claim 回 true 恰一次。
    clock.store(FailsafeConfig::DEFAULT_TIMEOUT_MS + 1, Ordering::SeqCst);
    assert!(
        watcher.timer_expired_and_claim(),
        "過 timeout 後首次 claim 成功"
    );
    // 4) 再 claim 回 false（claim-before-await：同一武裝只發一次 escalate command）。
    assert!(
        !watcher.timer_expired_and_claim(),
        "同一武裝第二次 claim 必 false（防漏升/重發雙保險）"
    );

    // 5) operator ack 解除後重新武裝可再 claim（驗武裝週期語義）。
    watcher.record_operator_ack();
    let re = watcher.observe_dispatch(DispatchOutcome::AllFail);
    assert!(matches!(re, FailsafeDecision::TimerArmed { .. }));
    clock.store(FailsafeConfig::DEFAULT_TIMEOUT_MS * 3, Ordering::SeqCst);
    assert!(
        watcher.timer_expired_and_claim(),
        "新一輪武裝到期後可再 claim"
    );
}

/// C4-e 真 producer path：incident_policy 產生 AllFail → outcome feed → watcher claim →
/// in-band PipelineCommand handler → Demo SM-04 Defensive + stop sync。
#[tokio::test]
async fn e2e_c4_incident_policy_allfail_to_defensive_demo() {
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::sync::Arc;

    struct ArcClock(Arc<AtomicU64>);
    impl crate::notification_failsafe::FailsafeClock for ArcClock {
        fn now_ms(&self) -> u64 {
            self.0.load(Ordering::SeqCst)
        }
    }

    struct AllFailDispatcher;
    #[async_trait::async_trait]
    impl crate::notification_failsafe::NotificationDispatcher for AllFailDispatcher {
        async fn dispatch_3way(&self, _message: &str) -> DispatchOutcome {
            DispatchOutcome::AllFail
        }

        fn push_channels_enabled(&self) -> Option<(bool, bool)> {
            Some((true, true))
        }
    }

    let clock = Arc::new(AtomicU64::new(1_000));
    let watcher = SharedFailsafeWatcher::new_for_test(
        Box::new(AllFailDispatcher),
        Box::new(NoopPositionProvider),
        Box::new(NoopExchangeStopSync),
        Box::new(NoopAuditEmitter),
        Box::new(ArcClock(Arc::clone(&clock))),
        FailsafeConfig::default(),
    );
    let (outcome_tx, mut outcome_rx) = tokio::sync::mpsc::unbounded_channel();
    let (ack_tx, _ack_rx) = tokio::sync::mpsc::unbounded_channel();
    let senders = FailsafeFeedSenders { outcome_tx, ack_tx };

    let result = report_incident_with_test_watcher(
        IncidentClass::BybitFailClosed,
        "retCode fail-closed acceptance path".to_string(),
        1_000,
        &watcher,
        Some(senders),
    )
    .await;
    assert!(matches!(
        result,
        IncidentPolicyResult::Dispatched {
            class: IncidentClass::BybitFailClosed,
            mode: IncidentDispatchMode::ArmTimer,
            outcome: DispatchOutcome::AllFail,
            fed_to_watcher: true
        }
    ));

    let outcome = outcome_rx
        .recv()
        .await
        .expect("producer fed watcher outcome");
    assert!(matches!(
        watcher.observe_dispatch(outcome),
        FailsafeDecision::TimerArmed { .. }
    ));
    clock.store(
        1_000 + FailsafeConfig::DEFAULT_TIMEOUT_MS + 1,
        Ordering::SeqCst,
    );
    assert!(watcher.timer_expired_and_claim(), "watcher timer claims");

    let mut p = make_demo_pipeline();
    let mut w = make_test_writer();
    let (stop_tx, mut stop_rx) = tokio::sync::mpsc::unbounded_channel::<StopRequest>();
    p.set_stop_channel(stop_tx);
    p.paper_state.set_latest_price("BTCUSDT", 50_000.0);
    p.paper_state
        .apply_fill("BTCUSDT", true, 0.01, 50_000.0, 0.0, 0, "external_test");
    seed_atr_klines(&mut p, "BTCUSDT", 50_000.0, 500.0);
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Normal);

    let (response_tx, response_rx) = tokio::sync::oneshot::channel();
    let cmd = PipelineCommand::NotificationFailsafeEscalate {
        reason: "notification_3way_fail_1h_timeout".to_string(),
        response_tx,
    };
    let PipelineCommand::NotificationFailsafeEscalate {
        reason,
        response_tx,
    } = cmd
    else {
        unreachable!("test constructs the fail-safe command variant");
    };
    crate::event_consumer::handlers::handle_notification_failsafe_escalate(
        reason,
        response_tx,
        &mut p,
        &mut w,
        None,
    )
    .await;

    response_rx
        .await
        .expect("handler responded")
        .expect("report ok");
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Defensive);
    let stop_req = stop_rx
        .try_recv()
        .expect("Defensive escalation should sync a lock-profit stop");
    assert_eq!(stop_req.symbol, "BTCUSDT");
    assert!(stop_req.stop_loss > 50_000.0);
}

/// C4-d paper noop 對抗測：paper 模式 owner handler 跑 SM-04 但**不發 StopRequest**
/// （engine_mode short-circuit defense-in-depth；結構上 watcher 也不對 paper 發 command）。
#[tokio::test]
async fn e2e_c4_paper_skips_exchange_sync() {
    let mut p = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Paper);
    let mut w = make_test_writer();

    let (stop_tx, mut stop_rx) = tokio::sync::mpsc::unbounded_channel::<StopRequest>();
    p.set_stop_channel(stop_tx);
    p.paper_state.set_latest_price("BTCUSDT", 50_000.0);
    p.paper_state
        .apply_fill("BTCUSDT", true, 0.01, 50_000.0, 0.0, 0, "external_test");
    seed_atr_klines(&mut p, "BTCUSDT", 50_000.0, 500.0);

    let (tx, rx) = tokio::sync::oneshot::channel();
    crate::event_consumer::handlers::handle_notification_failsafe_escalate(
        "notification_3way_fail_1h_timeout".to_string(),
        tx,
        &mut p,
        &mut w,
        None,
    )
    .await;
    let _ = rx.await.expect("handler responded").expect("report ok");

    // 本地 SM-04 仍升（fail-safe 不因 paper 跳過保命升級）。
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Defensive);
    // 但**不打交易所** — paper engine_mode short-circuit。
    assert!(
        stop_rx.try_recv().is_err(),
        "paper 模式不得發 StopRequest 打交易所 endpoint（paper noop defense）"
    );
}
