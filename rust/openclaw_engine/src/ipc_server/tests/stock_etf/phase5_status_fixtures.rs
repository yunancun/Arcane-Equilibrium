//! Phase 5 Stock/ETF status IPC fixture tests.

use super::*;

#[tokio::test]
async fn stock_etf_launch_status_is_blocked_source_fixture_without_side_effects() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc":"2.0","method":"stock_etf.get_launch_status","params":{},"id":4813}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;

    assert!(resp.error.is_none());
    let result = resp.result.expect("stock_etf launch status result");
    assert_eq!(result["phase"], "phase5_launch_status_source_fixture");
    assert_eq!(result["asset_lane"], "stock_etf_cash");
    assert_eq!(result["broker"], "ibkr");
    assert_eq!(result["environment"], "paper_shadow");
    assert_eq!(result["launch_status_state"], "blocked");
    assert_eq!(result["phase3_started"], false);
    assert_eq!(result["phase5_started"], false);

    let release = &result["release_packet"];
    assert_eq!(
        release["expected_contract_id"],
        "stock_etf_release_packet_v1"
    );
    assert_eq!(release["accepted"], false);
    assert_eq!(release["paper_shadow_window_complete"], false);
    assert_eq!(release["engineering_shakedown_complete"], false);
    assert_eq!(release["role_report_count"], 0);
    assert_eq!(release["manifest_hash_count"], 0);
    assert_eq!(release["gui_screenshot_hash_count"], 0);
    assert_eq!(release["dq_manifest_hash_count"], 0);
    assert_eq!(release["scorecard_regeneration_hash_count"], 0);
    assert_eq!(release["secret_content_serialized"], false);
    assert_eq!(release["ibkr_live_or_tiny_live_authorized"], false);
    assert_eq!(release["sealed"], false);

    let runbook = &result["disable_cleanup_runbook"];
    assert_eq!(
        runbook["expected_runbook_id"],
        "stock_etf_kill_switch_and_disable_cleanup_runbook_v1"
    );
    assert_eq!(runbook["accepted"], false);
    assert_eq!(runbook["env_flag_count"], 0);
    assert_eq!(runbook["proof_count"], 0);
    assert_eq!(runbook["ibkr_contact_performed"], false);
    assert_eq!(runbook["connector_runtime_started"], false);
    assert_eq!(runbook["paper_order_routed"], false);
    assert_eq!(runbook["secret_slot_created"], false);
    assert_eq!(runbook["secret_content_serialized"], false);
    assert_eq!(runbook["destructive_db_cleanup_requested"], false);
    assert_eq!(runbook["db_delete_or_truncate_allowed"], false);
    assert_eq!(runbook["paper_shadow_launch_authorized"], false);
    assert_eq!(runbook["tiny_live_authorized"], false);
    assert_eq!(runbook["live_authorized"], false);

    let tiny_live = &result["tiny_live_adr_eligibility"];
    assert_eq!(
        tiny_live["expected_contract_id"],
        "tiny_live_adr_eligibility_v1"
    );
    assert_eq!(tiny_live["accepted"], false);
    assert_eq!(tiny_live["decision"], "not_eligible");
    assert_eq!(tiny_live["scorecard_derivation_hash_present"], false);
    assert_eq!(tiny_live["scorecard_verdict_hash_present"], false);
    assert_eq!(tiny_live["scorecard_manifest_hash_present"], false);
    assert_eq!(tiny_live["paper_shadow_reconciliation_hash_present"], false);
    assert_eq!(tiny_live["qa_review_hash_present"], false);
    assert_eq!(tiny_live["paper_shadow_window_complete"], false);
    assert_eq!(tiny_live["benchmark_relative_after_cost_lcb_bps"], 0);
    assert_eq!(tiny_live["independent_observation_count"], 0);
    assert_eq!(tiny_live["min_independent_observation_count"], 0);
    assert_eq!(tiny_live["conservative_cost_stress_lcb_bps"], 0);
    assert_eq!(tiny_live["paper_shadow_divergence_bps"], 0);
    assert_eq!(tiny_live["max_paper_shadow_divergence_bps"], 0);
    assert_eq!(tiny_live["qa_review_passed"], false);
    assert_eq!(tiny_live["secret_content_serialized"], false);
    assert_eq!(tiny_live["sealed"], false);

    assert_eq!(result["paper_shadow_launch_authorized"], false);
    assert_eq!(result["tiny_live_or_live_authorized"], false);
    assert_eq!(result["connector_runtime_started"], false);
    assert_eq!(result["scorecard_writer_started"], false);
    assert_eq!(result["db_apply_performed"], false);
    assert_eq!(result["evidence_clock_started"], false);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);
    assert_eq!(result["phase2"]["first_ibkr_contact_allowed"], false);
    assert_eq!(result["phase2"]["connector_enabled"], false);
}

#[tokio::test]
async fn stock_etf_release_packet_status_is_display_only_source_fixture() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req =
        r#"{"jsonrpc":"2.0","method":"stock_etf.get_release_packet_status","params":{},"id":4818}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;

    assert!(resp.error.is_none());
    let result = resp.result.expect("stock_etf release packet status result");
    assert_eq!(
        result["phase"],
        "phase5_release_packet_status_source_fixture"
    );
    assert_eq!(result["asset_lane"], "stock_etf_cash");
    assert_eq!(result["broker"], "ibkr");
    assert_eq!(result["environment"], "paper_shadow");
    assert_eq!(
        result["release_packet_status_state"],
        "source_ready_runtime_blocked"
    );
    assert_eq!(result["phase3_started"], false);
    assert_eq!(result["phase5_started"], false);

    let release = &result["release_packet"];
    assert_eq!(
        release["expected_contract_id"],
        "stock_etf_release_packet_v1"
    );
    assert_eq!(release["packet_id"], "stock_etf_release_packet_v1");
    assert_eq!(release["source_version"], 1);
    assert_eq!(release["accepted"], true);
    assert_json_array_eq(&release["blockers"], &[]);
    assert_eq!(release["source_commit_present"], true);
    assert_eq!(release["reviewer_role_count"], 8);
    assert_eq!(release["role_report_count"], 2);
    assert_eq!(release["e2_log_hash_present"], true);
    assert_eq!(release["e3_redaction_log_hash_present"], true);
    assert_eq!(release["e4_log_hash_present"], true);
    assert_eq!(release["qa_log_hash_present"], true);
    assert_eq!(release["manifest_hash_count"], 2);
    assert_eq!(
        release["manifest_hashes"],
        serde_json::json!([
            {
                "label": "release_manifest",
                "hash_present": true,
            },
            {
                "label": "artifact_manifest",
                "hash_present": true,
            },
        ])
    );
    assert_eq!(release["pg_migrations_declared"], false);
    assert_eq!(release["pg_dry_run_log_hash_present"], false);
    assert_eq!(release["pg_double_apply_log_hash_present"], false);
    assert_eq!(release["redaction_fixture_hash_present"], true);
    assert_eq!(release["gui_screenshot_hash_count"], 1);
    assert_eq!(release["dq_manifest_hash_count"], 1);
    assert_eq!(release["scorecard_regeneration_hash_count"], 1);
    assert_eq!(release["evidence_archive_pointer_present"], true);
    assert_eq!(release["evidence_archive_hash_present"], true);
    assert_eq!(release["paper_shadow_window_complete"], true);
    assert_eq!(release["engineering_shakedown_complete"], true);
    assert_eq!(release["secret_content_serialized"], false);
    assert_eq!(release["ibkr_live_or_tiny_live_authorized"], false);
    assert_eq!(release["sealed"], true);

    let kill = &release["kill_disable_cleanup_proof"];
    assert_eq!(kill["stock_etf_lane_enabled_false"], true);
    assert_eq!(kill["ibkr_readonly_enabled_false"], true);
    assert_eq!(kill["ibkr_paper_enabled_false"], true);
    assert_eq!(kill["stock_etf_shadow_only_true"], true);
    assert_eq!(kill["collector_stopped"], true);
    assert_eq!(kill["gui_stock_views_disabled_or_hidden"], true);
    assert_eq!(kill["live_secret_absence_proven"], true);
    assert_eq!(kill["evidence_archive_forward_only"], true);
    assert_eq!(kill["destructive_db_cleanup_requested"], false);
    assert_eq!(kill["proof_hash_present"], true);

    assert_eq!(result["paper_shadow_launch_authorized"], false);
    assert_eq!(result["tiny_live_or_live_authorized"], false);
    assert_eq!(result["connector_runtime_started"], false);
    assert_eq!(result["scorecard_writer_started"], false);
    assert_eq!(result["db_apply_performed"], false);
    assert_eq!(result["evidence_clock_started"], false);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);
    assert_eq!(result["phase2"]["first_ibkr_contact_allowed"], false);
    assert_eq!(result["phase2"]["connector_enabled"], false);
}

#[tokio::test]
async fn stock_etf_disable_cleanup_status_is_display_only_source_fixture() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc":"2.0","method":"stock_etf.get_disable_cleanup_status","params":{},"id":4817}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;

    assert!(resp.error.is_none());
    let result = resp
        .result
        .expect("stock_etf disable cleanup status result");
    assert_eq!(
        result["phase"],
        "phase5_disable_cleanup_status_source_fixture"
    );
    assert_eq!(result["asset_lane"], "stock_etf_cash");
    assert_eq!(result["broker"], "ibkr");
    assert_eq!(result["environment"], "paper_shadow");
    assert_eq!(
        result["disable_cleanup_status_state"],
        "source_ready_runtime_blocked"
    );
    assert_eq!(result["phase3_started"], false);
    assert_eq!(result["phase5_started"], false);
    assert_eq!(result["collector_stop_requested"], false);
    assert_eq!(result["gui_disable_requested"], false);
    assert_eq!(result["evidence_archive_requested"], false);
    assert_eq!(result["db_cleanup_requested"], false);

    let runbook = &result["runbook"];
    assert_eq!(
        runbook["expected_runbook_id"],
        "stock_etf_kill_switch_and_disable_cleanup_runbook_v1"
    );
    assert_eq!(
        runbook["runbook_id"],
        "stock_etf_kill_switch_and_disable_cleanup_runbook_v1"
    );
    assert_eq!(runbook["source_version"], 1);
    assert_eq!(runbook["accepted"], true);
    assert_json_array_eq(&runbook["blockers"], &[]);
    assert_eq!(runbook["source_artifact_hash_present"], true);
    assert_eq!(runbook["bybit_live_execution_unchanged"], true);
    assert_eq!(runbook["env_flag_count"], 4);
    assert_eq!(runbook["proof_count"], 7);
    assert_eq!(
        runbook["env_flags"],
        serde_json::json!([
            {
                "name": "OPENCLAW_STOCK_ETF_LANE_ENABLED",
                "expected_value": "0",
                "observed_value": "0",
                "evidence_hash_present": true,
            },
            {
                "name": "OPENCLAW_IBKR_READONLY_ENABLED",
                "expected_value": "0",
                "observed_value": "0",
                "evidence_hash_present": true,
            },
            {
                "name": "OPENCLAW_IBKR_PAPER_ENABLED",
                "expected_value": "0",
                "observed_value": "0",
                "evidence_hash_present": true,
            },
            {
                "name": "OPENCLAW_STOCK_ETF_SHADOW_ONLY",
                "expected_value": "1",
                "observed_value": "1",
                "evidence_hash_present": true,
            },
        ])
    );
    assert_eq!(
        runbook["proofs"],
        serde_json::json!([
            {
                "kind": "collector_stopped",
                "verified": true,
                "evidence_hash_present": true,
                "grants_runtime_authority": false,
                "destructive_cleanup_claimed": false,
            },
            {
                "kind": "gui_stock_views_disabled_or_hidden",
                "verified": true,
                "evidence_hash_present": true,
                "grants_runtime_authority": false,
                "destructive_cleanup_claimed": false,
            },
            {
                "kind": "live_secret_absence_proven",
                "verified": true,
                "evidence_hash_present": true,
                "grants_runtime_authority": false,
                "destructive_cleanup_claimed": false,
            },
            {
                "kind": "evidence_archive_forward_only",
                "verified": true,
                "evidence_hash_present": true,
                "grants_runtime_authority": false,
                "destructive_cleanup_claimed": false,
            },
            {
                "kind": "db_forward_only_retention_preserved",
                "verified": true,
                "evidence_hash_present": true,
                "grants_runtime_authority": false,
                "destructive_cleanup_claimed": false,
            },
            {
                "kind": "append_only_audit_preserved",
                "verified": true,
                "evidence_hash_present": true,
                "grants_runtime_authority": false,
                "destructive_cleanup_claimed": false,
            },
            {
                "kind": "bybit_live_execution_unchanged",
                "verified": true,
                "evidence_hash_present": true,
                "grants_runtime_authority": false,
                "destructive_cleanup_claimed": false,
            },
        ])
    );
    assert_eq!(runbook["ibkr_contact_performed"], false);
    assert_eq!(runbook["connector_runtime_started"], false);
    assert_eq!(runbook["paper_order_routed"], false);
    assert_eq!(runbook["secret_slot_created"], false);
    assert_eq!(runbook["secret_content_serialized"], false);
    assert_eq!(runbook["destructive_db_cleanup_requested"], false);
    assert_eq!(runbook["db_delete_or_truncate_allowed"], false);
    assert_eq!(runbook["paper_shadow_launch_authorized"], false);
    assert_eq!(runbook["tiny_live_authorized"], false);
    assert_eq!(runbook["live_authorized"], false);

    assert_eq!(result["paper_shadow_launch_authorized"], false);
    assert_eq!(result["tiny_live_or_live_authorized"], false);
    assert_eq!(result["connector_runtime_started"], false);
    assert_eq!(result["scorecard_writer_started"], false);
    assert_eq!(result["db_apply_performed"], false);
    assert_eq!(result["evidence_clock_started"], false);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);
    assert_eq!(result["phase2"]["first_ibkr_contact_allowed"], false);
    assert_eq!(result["phase2"]["connector_enabled"], false);
}
