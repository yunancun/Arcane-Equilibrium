//! Stock/ETF Phase 2 pre-contact source-only summaries.

use openclaw_types::{
    IbkrExternalSurfaceGateV1, IbkrPhase2PolicyBundleV1, NonBybitApiAllowlistV1,
    STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID,
    STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID,
};

pub(super) fn phase2_precontact_summary() -> serde_json::Value {
    let api_allowlist = NonBybitApiAllowlistV1::accepted_fixture();
    let api_allowlist_verdict = api_allowlist.validate();
    let policy_bundle = IbkrPhase2PolicyBundleV1::source_template();
    let policy_verdict = policy_bundle.validate();
    let policy_flags = policy_bundle.gate_prerequisite_flags();
    let gate = IbkrExternalSurfaceGateV1 {
        api_allowlist_present: api_allowlist_verdict.accepted,
        redaction_suite_passed: policy_flags.redaction_suite_passed,
        rate_limit_policy_present: policy_flags.rate_limit_policy_present,
        audit_event_policy_present: policy_flags.audit_event_policy_present,
        paper_attestation_contract_present: policy_flags.paper_attestation_contract_present,
        python_no_write_guard_present: policy_flags.python_no_write_guard_present,
        ibkr_call_performed: false,
        ..IbkrExternalSurfaceGateV1::default()
    };
    let gate_verdict = gate.validate();

    serde_json::json!({
        "external_surface_gate": {
            "status": gate.status,
            "ibkr_contact_allowed": gate_verdict.ibkr_contact_allowed,
            "blockers": gate_verdict.blockers,
            "ibkr_call_performed": gate.ibkr_call_performed,
        },
        "api_allowlist": {
            "contract_id": api_allowlist.contract_id,
            "source_version": api_allowlist.source_version,
            "accepted": api_allowlist_verdict.accepted,
            "blockers": api_allowlist_verdict.blockers,
            "read_actions": api_allowlist.read_actions.clone(),
            "read_action_count": api_allowlist.read_actions.len(),
            "paper_write_actions": api_allowlist.paper_write_actions.clone(),
            "paper_write_action_count": api_allowlist.paper_write_actions.len(),
            "denied_actions": api_allowlist.denied_actions.clone(),
            "denied_action_count": api_allowlist.denied_actions.len(),
            "ibkr_contact_performed": api_allowlist.ibkr_contact_performed,
            "secret_content_serialized": api_allowlist.secret_content_serialized,
            "bybit_live_execution_protected": api_allowlist.bybit_live_execution_protected,
        },
        "policy_prerequisites": {
            "bundle_accepted": policy_verdict.accepted,
            "blockers": policy_verdict.blockers,
            "flags": policy_flags,
        },
        "readonly_probe_request": readonly_probe_request_summary(),
        "readonly_probe_result_import_request": readonly_probe_result_import_request_summary(),
        "immutable_pass_artifact_present": false,
        "first_ibkr_contact_allowed": false,
        "connector_enabled": false,
        "secret_slot_touched": false,
        "order_routed": false,
    })
}

fn readonly_probe_request_summary() -> serde_json::Value {
    serde_json::json!({
        "contract_id": STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID,
        "source_version": 1,
        "request_artifact_present": false,
        "request_validated": false,
        "accepted_for_contact": false,
        "status": "blocked_no_request_artifact",
        "blockers": ["phase2_gate_not_accepted", "probe_request_artifact_missing"],
        "ibkr_contact_performed": false,
        "connector_runtime_started": false,
        "secret_content_serialized": false,
        "order_routed": false,
        "paper_order_submitted": false,
        "db_apply_performed": false,
        "evidence_clock_started": false,
        "bybit_path_reused": false,
        "live_or_tiny_live_authorized": false,
    })
}

fn readonly_probe_result_import_request_summary() -> serde_json::Value {
    serde_json::json!({
        "contract_id": STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID,
        "source_version": 1,
        "request_artifact_present": false,
        "request_validated": false,
        "accepted_for_import": false,
        "status": "blocked_no_result_import_request_artifact",
        "blockers": ["phase2_gate_not_accepted", "probe_result_import_request_artifact_missing"],
        "ibkr_contact_performed": false,
        "connector_runtime_started": false,
        "secret_content_serialized": false,
        "result_import_performed": false,
        "evidence_writer_started": false,
        "scorecard_writer_started": false,
        "db_apply_performed": false,
        "order_routed": false,
        "paper_order_submitted": false,
        "bybit_path_reused": false,
        "live_or_tiny_live_authorized": false,
    })
}

pub(super) fn connector_skeleton_summary() -> serde_json::Value {
    serde_json::json!({
        "surface_id": "ibkr_stock_etf_readonly_connector_skeleton_v1",
        "accepted": false,
        "status": "blocked_source_only",
        "blockers": ["phase2_gate_not_accepted"],
        "network_contact_performed": false,
        "secret_content_loaded": false,
        "paper_channel_exposed": false,
        "live_channel_exposed": false,
        "order_write_method_present": false,
        "bybit_path_reused": false,
    })
}
