//! IBKR **W4 connection-health 報告契約**（source-only,Rust 為 authority）。
//!
//! 本檔是 W4-1 交付的**契約層**：把 W3 已建的 session FSM label
//! （`IbkrTwsSessionStateV1`）+ pacing 觀測 + attestation 狀態投影成單一唯讀 health
//! 報告 shape,供 Rust IPC emitter 填值、Python normalizer 負空間校驗。**不開 socket、
//! 不啟 Gateway、不路由訂單、不讀 secret**；純資料 + 純函數（`validate()` 零副作用）。
//!
//! **W4 封頂語義**：inactive 引擎（permit stub 恆拒）下,health 的唯一誠實形態＝
//! `session_state=disconnected` / `halt_reason=envelope_required` / `session_active=false`
//! / attestation=`blocked` / entitlement=`pending` / 負空間安全束全 false /
//! `report_status=external_verification_pending`。此為**對 inactive session 的真實 FSM
//! 計算**,非 fake-success（AMD-2026-07-08-01 §Runtime Boundary）。
//!
//! **pacing 束的 `main_tokens_available` 是 telemetry 非 liveness 訊號**：一個從未使用
//! 的 governor 其 token bucket 為滿桶（初始桶量,設計 §8「唯一真派生值」）——非零屬誠實
//! inactive 基線,**不列入負空間 violation**。負空間校驗鎖定 pacing **活動計數**
//! （admitted/queue_depth/lines_in_use/strikes/rejected_*）與所有信任訊號,不鎖靜態容量。

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_gate::IbkrSessionAttestationStatus;
use crate::ibkr_tws_session_state::IbkrTwsSessionStateV1;

/// 契約 id（Python normalizer / cross-surface parity 對齊）。
pub const IBKR_CONNECTION_HEALTH_REPORT_CONTRACT_ID: &str = "ibkr_connection_health_report_v1";

/// W4 connection-health 報告的頂層狀態（枚舉;W4 唯一可產值＝
/// `ExternalVerificationPending`——inactive 引擎下對 FSM 的誠實計算,非 fake-success。
/// `Degraded` 保留給 IPC unavailable / 契約漂移的降級路徑（W4 emitter 不主動產））。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrConnectionHealthReportStatus {
    /// 外部驗證前置未滿足（inactive 引擎的誠實 health 形態;W4 唯一 emit 值）。
    ExternalVerificationPending,
    /// 降級（保留;normalizer 側 IPC unavailable 時可標,emitter 不主動產）。
    Degraded,
}

impl Default for IbkrConnectionHealthReportStatus {
    fn default() -> Self {
        Self::ExternalVerificationPending
    }
}

/// disconnected 態的停機原因投影（engine `HaltReason` → 契約枚舉;W4 恆 `EnvelopeRequired`）。
/// `NotHalted` = 非 disconnected 態（W4 結構性不可達,W5+ 才會出現）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrConnectionHealthHaltReasonV1 {
    /// 非 disconnected 態（無停機原因）。
    NotHalted,
    /// 初始未連線。
    Initial,
    /// permit 被拒（envelope 前置未滿足;production W8 前恆此路;INV-1）。
    EnvelopeRequired,
    /// session 級致命（不自動重試）。
    SessionFatal,
    /// 週日 ~1:00am ET 重認證窗（人工事務,永不自動重連）。
    WeeklyReauth,
    /// 重連預算耗盡。
    ReconnectBudgetExhausted,
    /// kill-switch / operator stop。
    Halted,
}

impl Default for IbkrConnectionHealthHaltReasonV1 {
    fn default() -> Self {
        // fail-closed 預設＝envelope_required（假定未活化,不假定已連）。
        Self::EnvelopeRequired
    }
}

/// entitlement 狀態（W6 才真派生;W4 佔位恆 `Pending`）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrConnectionHealthEntitlementStateV1 {
    /// 待決（W4 佔位;entitlement 邏輯 W6）。
    Pending,
    /// 已授（W6+;W4 結構性不可達）。
    Granted,
    /// 被拒（W6+;W4 結構性不可達）。
    Denied,
}

impl Default for IbkrConnectionHealthEntitlementStateV1 {
    fn default() -> Self {
        Self::Pending
    }
}

/// W4 connection-health 報告契約（四束 + 負空間安全束）。**Rust 為 authority**：Python
/// thin relay 永不解讀不加 authority。所有 operational/trust 欄在 W4 inactive 下恆為
/// 「blocked/false/pending/disconnected」,`main_tokens_available` 為唯一非零 telemetry。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrConnectionHealthReportV1 {
    pub contract_id: String,
    pub source_version: u32,

    // ---- session 束（投影 `TwsSessionManager` FSM）----
    pub session_state: IbkrTwsSessionStateV1,
    pub halt_reason: IbkrConnectionHealthHaltReasonV1,
    pub session_active: bool,
    pub reconnect_attempt: u32,

    // ---- pacing 束（投影 `PacingObservation`;`main_tokens_available`＝telemetry）----
    pub main_tokens_available: u64,
    pub queue_depth: u64,
    pub lines_in_use: u32,
    pub ib_pacing_strikes: u32,
    pub admitted: u64,
    pub rejected_order_verb: u64,
    pub rejected_queue_full: u64,
    pub rejected_timeout: u64,
    pub rejected_historical: u64,
    pub rejected_lines: u64,

    // ---- attestation 束 ----
    pub attestation_status: IbkrSessionAttestationStatus,
    pub account_fingerprint_is_live: bool,

    // ---- entitlement 束（W6 才真派生;W4 佔位）----
    pub entitlement_state: IbkrConnectionHealthEntitlementStateV1,
    pub pending_reason: String,

    // ---- 負空間安全束（恆 false;Python Layer-1 hard-safety 恆校驗）----
    pub ibkr_contact_performed: bool,
    pub secret_slot_touched: bool,
    pub gateway_socket_open: bool,
    pub order_routed: bool,
    pub bybit_ipc_reused: bool,
    pub ibkr_live_enabled: bool,

    // ---- 頂層狀態 ----
    pub report_status: IbkrConnectionHealthReportStatus,
}

impl Default for IbkrConnectionHealthReportV1 {
    /// fail-closed 預設（全 blocked/false/pending/disconnected;telemetry 欄零）。
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            session_state: IbkrTwsSessionStateV1::Disconnected,
            halt_reason: IbkrConnectionHealthHaltReasonV1::EnvelopeRequired,
            session_active: false,
            reconnect_attempt: 0,
            main_tokens_available: 0,
            queue_depth: 0,
            lines_in_use: 0,
            ib_pacing_strikes: 0,
            admitted: 0,
            rejected_order_verb: 0,
            rejected_queue_full: 0,
            rejected_timeout: 0,
            rejected_historical: 0,
            rejected_lines: 0,
            attestation_status: IbkrSessionAttestationStatus::Blocked,
            account_fingerprint_is_live: false,
            entitlement_state: IbkrConnectionHealthEntitlementStateV1::Pending,
            pending_reason: String::new(),
            ibkr_contact_performed: false,
            secret_slot_touched: false,
            gateway_socket_open: false,
            order_routed: false,
            bybit_ipc_reused: false,
            ibkr_live_enabled: false,
            report_status: IbkrConnectionHealthReportStatus::ExternalVerificationPending,
        }
    }
}

impl IbkrConnectionHealthReportV1 {
    /// inactive 引擎的**誠實** health 形態（W4 emitter 的目標投影;types acceptance 基線）。
    /// `main_tokens_available` 帶入預設 pacing 初始桶量占位（`main_bucket_baseline`;真值由
    /// engine emitter 從活 governor 派生,此處僅為 types fixture 的代表值,不參與負空間 violation）。
    pub fn inactive_fixture(main_bucket_baseline: u64) -> Self {
        Self {
            contract_id: IBKR_CONNECTION_HEALTH_REPORT_CONTRACT_ID.to_string(),
            source_version: 1,
            main_tokens_available: main_bucket_baseline,
            pending_reason: "external_verification_pending".to_string(),
            ..Self::default()
        }
    }

    /// **負空間校驗**（零副作用;types-level Layer-1+2 for inactive）：inactive 引擎下唯一可
    /// 接受形態是「全 blocked/false/pending/disconnected + envelope_required + pacing 活動零」。
    /// 任何 operational/trust 欄被 populate ＝ blocker（與 Python normalizer 負空間逐位元同構）。
    /// **不校驗 `main_tokens_available`**（telemetry,非 liveness——見模組註解）。
    pub fn validate(&self) -> IbkrConnectionHealthVerdict {
        use IbkrConnectionHealthBlocker as B;
        let mut blockers = Vec::new();

        if self.contract_id != IBKR_CONNECTION_HEALTH_REPORT_CONTRACT_ID {
            blockers.push(B::ContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(B::SourceVersionMismatch);
        }

        // session 束：inactive 恆 Disconnected(EnvelopeRequired) 且非 active。
        if self.session_state != IbkrTwsSessionStateV1::Disconnected {
            blockers.push(B::SessionNotDisconnected);
        }
        if self.halt_reason != IbkrConnectionHealthHaltReasonV1::EnvelopeRequired {
            blockers.push(B::HaltReasonNotEnvelopeRequired);
        }
        if self.session_active {
            blockers.push(B::SessionActive);
        }
        if self.reconnect_attempt != 0 {
            blockers.push(B::ReconnectAttemptNonZero);
        }

        // pacing 束：活動計數恆零（`main_tokens_available` 為 telemetry,不校驗）。
        if self.queue_depth != 0
            || self.lines_in_use != 0
            || self.ib_pacing_strikes != 0
            || self.admitted != 0
            || self.rejected_order_verb != 0
            || self.rejected_queue_full != 0
            || self.rejected_timeout != 0
            || self.rejected_historical != 0
            || self.rejected_lines != 0
        {
            blockers.push(B::PacingActivityPresent);
        }

        // attestation / entitlement 束：恆 blocked / pending / 非 live。
        if self.attestation_status != IbkrSessionAttestationStatus::Blocked {
            blockers.push(B::AttestationNotBlocked);
        }
        if self.account_fingerprint_is_live {
            blockers.push(B::AccountFingerprintLive);
        }
        if self.entitlement_state != IbkrConnectionHealthEntitlementStateV1::Pending {
            blockers.push(B::EntitlementNotPending);
        }

        // 負空間安全束：恆 false。
        if self.ibkr_contact_performed {
            blockers.push(B::IbkrContactPerformed);
        }
        if self.secret_slot_touched {
            blockers.push(B::SecretSlotTouched);
        }
        if self.gateway_socket_open {
            blockers.push(B::GatewaySocketOpen);
        }
        if self.order_routed {
            blockers.push(B::OrderRouted);
        }
        if self.bybit_ipc_reused {
            blockers.push(B::BybitIpcReused);
        }
        if self.ibkr_live_enabled {
            blockers.push(B::IbkrLiveEnabled);
        }

        // 頂層狀態：W4 唯一可接受＝external_verification_pending。
        if self.report_status != IbkrConnectionHealthReportStatus::ExternalVerificationPending {
            blockers.push(B::ReportStatusNotPending);
        }

        IbkrConnectionHealthVerdict::new(blockers)
    }
}

/// 負空間校驗裁決。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrConnectionHealthVerdict {
    pub accepted: bool,
    pub blockers: Vec<IbkrConnectionHealthBlocker>,
}

impl IbkrConnectionHealthVerdict {
    pub fn new(blockers: Vec<IbkrConnectionHealthBlocker>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

/// 負空間 blocker（typed）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrConnectionHealthBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    SessionNotDisconnected,
    HaltReasonNotEnvelopeRequired,
    SessionActive,
    ReconnectAttemptNonZero,
    PacingActivityPresent,
    AttestationNotBlocked,
    AccountFingerprintLive,
    EntitlementNotPending,
    IbkrContactPerformed,
    SecretSlotTouched,
    GatewaySocketOpen,
    OrderRouted,
    BybitIpcReused,
    IbkrLiveEnabled,
    ReportStatusNotPending,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn inactive_fixture_is_accepted_negative_space() {
        // inactive 引擎的誠實 health 形態：負空間校驗通過（零 blocker）。
        let report = IbkrConnectionHealthReportV1::inactive_fixture(50);
        let verdict = report.validate();
        assert!(verdict.accepted, "inactive fixture 應通過負空間校驗");
        assert!(verdict.blockers.is_empty());
        // 契約 taxonomy 檢查。
        assert_eq!(
            report.contract_id,
            IBKR_CONNECTION_HEALTH_REPORT_CONTRACT_ID
        );
        assert_eq!(report.source_version, 1);
        assert_eq!(report.session_state, IbkrTwsSessionStateV1::Disconnected);
        assert_eq!(
            report.halt_reason,
            IbkrConnectionHealthHaltReasonV1::EnvelopeRequired
        );
        assert!(!report.session_active);
        assert_eq!(report.reconnect_attempt, 0);
        assert_eq!(
            report.attestation_status,
            IbkrSessionAttestationStatus::Blocked
        );
        assert!(!report.account_fingerprint_is_live);
        assert_eq!(
            report.entitlement_state,
            IbkrConnectionHealthEntitlementStateV1::Pending
        );
        assert_eq!(
            report.report_status,
            IbkrConnectionHealthReportStatus::ExternalVerificationPending
        );
    }

    #[test]
    fn main_tokens_available_is_telemetry_not_a_blocker() {
        // main_tokens_available 為滿桶初始值（telemetry）——非零不觸 blocker（設計 §8）。
        let report = IbkrConnectionHealthReportV1::inactive_fixture(50);
        assert_eq!(report.main_tokens_available, 50);
        assert!(
            report.validate().accepted,
            "滿桶 telemetry 不得判為 violation"
        );
        // 極端值仍不觸 blocker。
        let big = IbkrConnectionHealthReportV1::inactive_fixture(u64::MAX);
        assert!(big.validate().accepted);
    }

    #[test]
    fn populated_operational_values_are_blockers() {
        // 逐一注入 operational/trust 真值 → 逐一 blocker（負空間逐位元）。
        let mut report = IbkrConnectionHealthReportV1::inactive_fixture(50);
        report.session_state = IbkrTwsSessionStateV1::Ready;
        report.halt_reason = IbkrConnectionHealthHaltReasonV1::NotHalted;
        report.session_active = true;
        report.reconnect_attempt = 3;
        report.admitted = 7;
        report.ib_pacing_strikes = 2;
        report.attestation_status = IbkrSessionAttestationStatus::PaperAttested;
        report.account_fingerprint_is_live = true;
        report.entitlement_state = IbkrConnectionHealthEntitlementStateV1::Granted;
        report.ibkr_contact_performed = true;
        report.secret_slot_touched = true;
        report.gateway_socket_open = true;
        report.order_routed = true;
        report.bybit_ipc_reused = true;
        report.ibkr_live_enabled = true;
        report.report_status = IbkrConnectionHealthReportStatus::Degraded;

        let verdict = report.validate();
        assert!(!verdict.accepted);
        use IbkrConnectionHealthBlocker as B;
        for expected in [
            B::SessionNotDisconnected,
            B::HaltReasonNotEnvelopeRequired,
            B::SessionActive,
            B::ReconnectAttemptNonZero,
            B::PacingActivityPresent,
            B::AttestationNotBlocked,
            B::AccountFingerprintLive,
            B::EntitlementNotPending,
            B::IbkrContactPerformed,
            B::SecretSlotTouched,
            B::GatewaySocketOpen,
            B::OrderRouted,
            B::BybitIpcReused,
            B::IbkrLiveEnabled,
            B::ReportStatusNotPending,
        ] {
            assert!(
                verdict.blockers.contains(&expected),
                "缺 blocker {expected:?}"
            );
        }
    }

    #[test]
    fn serde_roundtrip_snake_case_stable() {
        let report = IbkrConnectionHealthReportV1::inactive_fixture(50);
        let json = serde_json::to_value(&report).unwrap();
        assert_eq!(json["session_state"], "disconnected");
        assert_eq!(json["halt_reason"], "envelope_required");
        // IbkrSessionAttestationStatus 為 SCREAMING_SNAKE_CASE（沿用既有 attestation 契約）。
        assert_eq!(json["attestation_status"], "BLOCKED");
        assert_eq!(json["entitlement_state"], "pending");
        assert_eq!(json["report_status"], "external_verification_pending");
        let back: IbkrConnectionHealthReportV1 = serde_json::from_value(json).unwrap();
        assert_eq!(back, report);
    }

    #[test]
    fn default_is_fail_closed() {
        let report = IbkrConnectionHealthReportV1::default();
        assert_eq!(report.session_state, IbkrTwsSessionStateV1::Disconnected);
        assert!(!report.session_active);
        assert_eq!(
            report.attestation_status,
            IbkrSessionAttestationStatus::Blocked
        );
        // default contract_id 空 → 校驗不通過（fail-closed:須顯式 fixture）。
        assert!(!report.validate().accepted);
    }
}
