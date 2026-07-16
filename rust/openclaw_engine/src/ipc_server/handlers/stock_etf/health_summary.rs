//! Stock/ETF **W4 connection-health** source-only emitter。
//!
//! **W3 移交邊界（設計 §5）**：本 emitter 的 production caller 只到 **`TwsSessionManager`**
//! （讀 `ipc_state()`+`pacing_observation()`+`reconnect_attempt()`+`state()`）——manager 用其
//! 自持 envelope-required permit stub,`attempt_connect(0)` 恆停 `Disconnected(EnvelopeRequired)`,
//! **FSM 停 Disconnected(EnvelopeRequired),零 socket**。此為 session/pacing 模塊的**首個
//! production caller**（把 `ibkr_tws_session`/`ibkr_tws_pacing` 移出 DCE);driver 面
//! （transport factory 注入 / serve-loop / framed 出站）**不被引用** → 維持 production-DCE
//! （manager 不引用 driver,故構造 manager 不把 driver 拉出 DCE;driver-absence nm 審計驗證）。
//!
//! **inactive 引擎的誠實 health,非 fake-success**：對 inactive session 的真實 FSM 計算,回
//! `external_verification_pending` 形態（AMD-2026-07-08-01 §Runtime Boundary）。零真接觸/零
//! secret/零 order。`main_tokens_available` 為唯一真派生非零值（滿桶 telemetry,非 liveness）。

use openclaw_types::{
    AssetLane, Broker, IbkrConnectionHealthEntitlementStateV1, IbkrConnectionHealthHaltReasonV1,
    IbkrConnectionHealthReportStatus, IbkrConnectionHealthReportV1, IbkrSessionAttestationStatus,
    IbkrTwsSessionStateV1, IBKR_CONNECTION_HEALTH_REPORT_CONTRACT_ID,
};

use crate::ibkr_tws_session::{HaltReason, SessionState, TwsSessionConfig, TwsSessionManager};

/// W4 connection-health IPC 出口（dispatch `stock_etf.get_connection_health` 呼叫）。
/// 構 ephemeral inactive manager 撞 permit 一次,投影 FSM/pacing 態 + 附 phase2 束
/// （normalizer 由 `phase2.external_surface_gate.status` 派生 lineage）。
pub(super) fn connection_health_summary(phase2: serde_json::Value) -> serde_json::Value {
    let report = inactive_connection_health_report();

    // report 契約欄為 authority——序列化後併入顯示面 metadata + phase2 束
    // （報告欄名/值＝cross-surface parity 的鎖定源,Python normalizer 逐欄對齊）。
    let mut obj = serde_json::to_value(&report)
        .ok()
        .and_then(|value| value.as_object().cloned())
        .unwrap_or_default();

    obj.insert(
        "phase".to_string(),
        serde_json::json!("phase2_connection_health_source_fixture"),
    );
    obj.insert(
        "asset_lane".to_string(),
        serde_json::json!(AssetLane::StockEtfCash),
    );
    obj.insert("broker".to_string(), serde_json::json!(Broker::Ibkr));
    obj.insert(
        "environment".to_string(),
        serde_json::json!("paper_readonly"),
    );
    obj.insert(
        "connection_health_status_state".to_string(),
        serde_json::json!("external_verification_pending"),
    );
    // 負空間安全束的顯式 db_apply_performed（與其餘 status method 對稱;Python Layer-1 恆校驗）。
    obj.insert("db_apply_performed".to_string(), serde_json::json!(false));
    obj.insert("phase2".to_string(), phase2);

    serde_json::Value::Object(obj)
}

/// 構 ephemeral inactive `TwsSessionManager`,撞 permit stub 一次（零 socket）,投影其態。
fn inactive_connection_health_report() -> IbkrConnectionHealthReportV1 {
    let mut manager = TwsSessionManager::new(TwsSessionConfig::default());
    // permit stub 恆拒 → FSM 停 `Disconnected(EnvelopeRequired)`(inactive 引擎的誠實態)。
    let _ = manager.attempt_connect(0);

    let observation = manager.pacing_observation();
    let session_state = manager.ipc_state();
    // session_active＝socket 已建立且就緒/劣化態（inactive 恆 Disconnected → false）。
    let session_active = matches!(
        session_state,
        IbkrTwsSessionStateV1::Ready | IbkrTwsSessionStateV1::Degraded
    );
    let halt_reason = match manager.state() {
        SessionState::Disconnected { reason } => project_halt_reason(*reason),
        _ => IbkrConnectionHealthHaltReasonV1::NotHalted,
    };

    IbkrConnectionHealthReportV1 {
        contract_id: IBKR_CONNECTION_HEALTH_REPORT_CONTRACT_ID.to_string(),
        source_version: 1,
        session_state,
        halt_reason,
        session_active,
        reconnect_attempt: manager.reconnect_attempt(),
        main_tokens_available: observation.main_tokens_available,
        queue_depth: observation.queue_depth as u64,
        lines_in_use: observation.lines_in_use,
        ib_pacing_strikes: observation.ib_pacing_strikes,
        admitted: observation.admitted,
        rejected_order_verb: observation.rejected_order_verb,
        rejected_queue_full: observation.rejected_queue_full,
        rejected_timeout: observation.rejected_timeout,
        rejected_historical: observation.rejected_historical,
        rejected_lines: observation.rejected_lines,
        // attestation / entitlement：W5+/W6 才真派生;W4 恆 blocked / pending / 非 live。
        attestation_status: IbkrSessionAttestationStatus::Blocked,
        account_fingerprint_is_live: false,
        entitlement_state: IbkrConnectionHealthEntitlementStateV1::Pending,
        pending_reason: "external_verification_pending".to_string(),
        // 負空間安全束：恆 false（inactive 引擎零接觸/零 socket/零 secret/零 order）。
        ibkr_contact_performed: false,
        secret_slot_touched: false,
        gateway_socket_open: false,
        order_routed: false,
        bybit_ipc_reused: false,
        ibkr_live_enabled: false,
        report_status: IbkrConnectionHealthReportStatus::ExternalVerificationPending,
    }
}

/// engine-private `HaltReason` → 契約枚舉投影（W4 inactive 恆 `EnvelopeRequired`）。
fn project_halt_reason(reason: HaltReason) -> IbkrConnectionHealthHaltReasonV1 {
    match reason {
        HaltReason::Initial => IbkrConnectionHealthHaltReasonV1::Initial,
        HaltReason::EnvelopeRequired => IbkrConnectionHealthHaltReasonV1::EnvelopeRequired,
        HaltReason::SessionFatal(_) => IbkrConnectionHealthHaltReasonV1::SessionFatal,
        HaltReason::WeeklyReauth => IbkrConnectionHealthHaltReasonV1::WeeklyReauth,
        HaltReason::ReconnectBudgetExhausted => {
            IbkrConnectionHealthHaltReasonV1::ReconnectBudgetExhausted
        }
        HaltReason::Halted => IbkrConnectionHealthHaltReasonV1::Halted,
    }
}
