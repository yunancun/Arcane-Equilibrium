//! Demo-learning lane admission ledger records.
//!
//! This module turns a pure admission decision into an append-only learning
//! artifact. It performs no IO and grants no order authority; callers decide
//! where to write the serialized record.

use chrono::{DateTime, Utc};
use serde::Serialize;
use serde_json::{json, Value};

use crate::demo_learning_lane::{
    normalize_reject_reason_code, side_cell_key, AdmissionDecision, RejectEvent,
    ADAPTER_SCHEMA_VERSION,
};

pub const ADMISSION_LEDGER_RECORD_TYPE: &str = "probe_admission_decision";
pub const CAPTURE_ERROR_LEDGER_RECORD_TYPE: &str = "probe_capture_error";
pub const CAPTURE_ERROR_DECISION: &str = "ADMISSION_NOT_EVALUATED";
pub const ADMISSION_LEDGER_BOUNDARY: &str =
    "admission-ledger artifact only; no PG, Bybit, order, config, risk, auth, or runtime mutation";

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct AdmissionLedgerEvent {
    pub side_cell_key: String,
    pub strategy_name: String,
    pub symbol: String,
    pub side: String,
    pub reject_reason_code: String,
    pub engine_mode: String,
    pub ts_ms: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub context_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub signal_id: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct AdmissionLedgerRecord {
    pub schema_version: &'static str,
    pub record_type: &'static str,
    pub generated_at_utc: String,
    pub attempt_id: String,
    pub decision: String,
    pub allowed_to_submit_order: bool,
    pub side_cell_key: String,
    pub event: AdmissionLedgerEvent,
    pub runtime_state: Value,
    pub reason: String,
    pub boundary: &'static str,
}

impl AdmissionLedgerRecord {
    pub fn to_json_string(&self) -> Result<String, serde_json::Error> {
        serde_json::to_string(self)
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct CaptureErrorLedgerRecord {
    pub schema_version: &'static str,
    pub record_type: &'static str,
    pub generated_at_utc: String,
    pub attempt_id: String,
    pub decision: &'static str,
    pub allowed_to_submit_order: bool,
    pub side_cell_key: String,
    pub event: AdmissionLedgerEvent,
    pub runtime_state: Value,
    pub capture_error: String,
    pub reason: &'static str,
    pub boundary: &'static str,
}

impl CaptureErrorLedgerRecord {
    pub fn to_json_string(&self) -> Result<String, serde_json::Error> {
        serde_json::to_string(self)
    }
}

pub fn attempt_id_for_reject_event(event: &RejectEvent) -> String {
    if let Some(context_id) = non_empty(&event.context_id) {
        return context_id;
    }
    if let Some(signal_id) = non_empty(&event.signal_id) {
        return signal_id;
    }
    format!("{}|{}", event.side_cell_key(), event.ts_ms)
}

pub fn build_admission_ledger_record(
    decision: &AdmissionDecision,
    event: &RejectEvent,
    generated_at_utc: DateTime<Utc>,
) -> AdmissionLedgerRecord {
    let ledger_event = build_admission_ledger_event(event);
    let runtime_state = decision
        .runtime_state
        .as_ref()
        .and_then(|state| serde_json::to_value(state).ok())
        .unwrap_or_else(|| json!({}));

    AdmissionLedgerRecord {
        schema_version: ADAPTER_SCHEMA_VERSION,
        record_type: ADMISSION_LEDGER_RECORD_TYPE,
        generated_at_utc: generated_at_utc.to_rfc3339(),
        attempt_id: attempt_id_for_reject_event(event),
        decision: decision.decision.as_str().to_string(),
        allowed_to_submit_order: decision.allowed_to_submit_order,
        side_cell_key: decision.side_cell_key.clone(),
        event: ledger_event,
        runtime_state,
        reason: decision.reason.clone(),
        boundary: ADMISSION_LEDGER_BOUNDARY,
    }
}

pub fn build_capture_error_ledger_record(
    event: &RejectEvent,
    generated_at_utc: DateTime<Utc>,
    risk_state: &str,
    capture_error: &str,
) -> CaptureErrorLedgerRecord {
    let ledger_event = build_admission_ledger_event(event);
    CaptureErrorLedgerRecord {
        schema_version: ADAPTER_SCHEMA_VERSION,
        record_type: CAPTURE_ERROR_LEDGER_RECORD_TYPE,
        generated_at_utc: generated_at_utc.to_rfc3339(),
        attempt_id: attempt_id_for_reject_event(event),
        decision: CAPTURE_ERROR_DECISION,
        allowed_to_submit_order: false,
        side_cell_key: side_cell_key(&event.strategy_name, &event.symbol, &event.side),
        event: ledger_event,
        runtime_state: json!({
            "risk_state": risk_state.trim(),
        }),
        capture_error: capture_error.trim().to_string(),
        reason: "runtime_admission_evaluation_failed",
        boundary: ADMISSION_LEDGER_BOUNDARY,
    }
}

fn build_admission_ledger_event(event: &RejectEvent) -> AdmissionLedgerEvent {
    AdmissionLedgerEvent {
        side_cell_key: side_cell_key(&event.strategy_name, &event.symbol, &event.side),
        strategy_name: event.strategy_name.trim().to_string(),
        symbol: event.symbol.trim().to_ascii_uppercase(),
        side: event.side.trim().to_string(),
        reject_reason_code: normalize_reject_reason_code(&event.reject_reason_code),
        engine_mode: event.engine_mode.trim().to_ascii_lowercase(),
        ts_ms: event.ts_ms,
        context_id: non_empty(&event.context_id),
        signal_id: non_empty(&event.signal_id),
    }
}

fn non_empty(value: &Option<String>) -> Option<String> {
    value
        .as_deref()
        .map(str::trim)
        .filter(|trimmed| !trimmed.is_empty())
        .map(ToString::to_string)
}
