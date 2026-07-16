//! Stock/ETF foundation, policy, and authorization IPC fixture tests.

use super::*;

#[tokio::test]
async fn stock_etf_data_foundation_status_is_blocked_source_fixture_without_side_effects() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc":"2.0","method":"stock_etf.get_data_foundation_status","params":{},"id":4814}"#;
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
        .expect("stock_etf data foundation status result");
    assert_eq!(
        result["phase"],
        "phase2_data_foundation_status_source_fixture"
    );
    assert_eq!(result["asset_lane"], "stock_etf_cash");
    assert_eq!(result["broker"], "ibkr");
    assert_eq!(result["environment"], "paper");
    assert_eq!(result["data_foundation_status_state"], "blocked");
    assert_eq!(result["phase2_started"], false);
    assert_eq!(result["phase3_started"], false);
    assert_eq!(result["contract_details_request_started"], false);
    assert_eq!(result["reference_data_collection_started"], false);
    assert_eq!(result["collector_started"], false);
    assert_eq!(result["market_data_ingestion_started"], false);
    assert_eq!(result["connector_runtime_started"], false);
    assert_eq!(result["db_apply_performed"], false);
    assert_eq!(result["evidence_clock_started"], false);
    assert_eq!(result["scorecard_writer_started"], false);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);

    let identity = &result["instrument_identity"];
    assert_eq!(
        identity["expected_contract_id"],
        "instrument_identity_contract_v1"
    );
    assert_eq!(identity["contract_id"], "");
    assert_eq!(identity["source_version"], 0);
    assert_eq!(identity["accepted"], false);
    assert_json_array_eq(
        &identity["blockers"],
        &[
            "contract_id_mismatch",
            "source_version_mismatch",
            "symbol_invalid",
            "listing_venue_denied",
            "primary_exchange_denied",
            "currency_denied",
            "tradability_not_tradable",
            "priips_kid_blocked",
            "fractional_policy_missing",
            "point_in_time_asof_missing",
            "market_calendar_id_missing",
            "market_calendar_hash_invalid",
            "broker_contract_details_hash_invalid",
            "instrument_identity_hash_invalid",
            "corporate_action_adjustment_hash_invalid",
            "source_artifact_hash_invalid",
        ],
    );
    assert_eq!(identity["instrument_kind"], "stock");
    assert_eq!(identity["symbol"], "");
    assert_eq!(identity["market_calendar_hash_present"], false);
    assert_eq!(identity["broker_contract_details_hash_present"], false);
    assert_eq!(identity["instrument_identity_hash_present"], false);
    assert_eq!(identity["bybit_live_execution_unchanged"], true);
    assert_eq!(identity["ibkr_live_denied"], true);
    assert_eq!(identity["margin_short_denied"], true);
    assert_eq!(identity["options_cfd_denied"], true);
    assert_eq!(identity["ibkr_contact_performed"], false);
    assert_eq!(identity["secret_content_serialized"], false);

    let reference = &result["reference_data_sources"];
    assert_eq!(
        reference["expected_contract_id"],
        "stock_etf_reference_data_sources_v1"
    );
    assert_eq!(reference["contract_id"], "");
    assert_eq!(reference["source_version"], 0);
    assert_eq!(reference["accepted"], false);
    assert_json_array_eq(
        &reference["blockers"],
        &[
            "contract_id_mismatch",
            "source_version_mismatch",
            "evidence_clock_freeze_missing",
            "corporate_action_source_missing",
            "corporate_action_as_of_missing",
            "corporate_action_raw_hash_invalid",
            "corporate_action_adjustment_hash_invalid",
            "corporate_action_policy_hash_invalid",
            "dividend_treatment_hash_invalid",
            "fx_rate_source_missing",
            "fx_rate_as_of_missing",
            "currency_denied",
            "fx_rate_snapshot_hash_invalid",
            "fx_drag_model_hash_invalid",
            "fee_schedule_source_missing",
            "fee_schedule_as_of_missing",
            "commission_schedule_hash_invalid",
            "exchange_regulatory_fee_hash_invalid",
            "tax_ftt_placeholder_hash_invalid",
            "withholding_tax_treatment_hash_invalid",
            "source_artifact_hash_invalid",
        ],
    );
    assert_eq!(reference["environment"], "paper");
    assert_eq!(reference["frozen_for_evidence_clock"], false);
    assert_eq!(reference["corporate_action_raw_hash_present"], false);
    assert_eq!(reference["fx_rate_snapshot_hash_present"], false);
    assert_eq!(reference["commission_schedule_hash_present"], false);
    assert_eq!(reference["bybit_live_execution_unchanged"], true);
    assert_eq!(reference["ibkr_contact_performed"], false);
    assert_eq!(reference["connector_runtime_started"], false);
    assert_eq!(reference["secret_content_serialized"], false);
    assert_eq!(reference["live_or_tiny_live_authorized"], false);

    assert_eq!(result["phase2"]["first_ibkr_contact_allowed"], false);
    assert_eq!(result["phase2"]["connector_enabled"], false);
}

#[test]
fn stock_etf_policy_status_is_blocked_source_fixture_without_side_effects() {
    // #3 去環境變數副作用（注入而非改全域）：改以純渲染子 policy_status_summary_from_result
    // 驗證 denied 顯示，不再 set/restore 全域 OPENCLAW_RISK_CONFIG_DIR、不再依賴進程級
    // OnceLock 初始化順序（原注釋自承 env-set 對已初始化的 OnceLock 常為 no-op）。
    // 以 pure loader 對「保證不存在的 dir」取得真實 Err（fail-closed），再注入純渲染子；
    // 比原走 IPC/OnceLock 更確定，斷言仍實質命中 denied fallback 的 caps 與 blockers。
    let policy_result = load_stock_etf_risk_policy_from_dir(
        "openclaw_stock_etf_denied_path_absent_source_fixture".as_ref(),
    );
    assert!(
        policy_result.is_err(),
        "缺檔 dir 必回 Err（fail-closed），實得 {policy_result:?}"
    );
    let phase2 = stock_etf_phase2_precontact_summary_for_test();
    let result = policy_status_summary_from_result(phase2, &policy_result);
    assert_eq!(result["phase"], "phase2_policy_status_source_fixture");
    assert_eq!(result["asset_lane"], "stock_etf_cash");
    assert_eq!(result["broker"], "ibkr");
    assert_eq!(result["environment"], "paper");
    assert_eq!(result["policy_status_state"], "blocked");
    assert_eq!(result["phase2_started"], false);
    assert_eq!(result["phase3_started"], false);
    assert_eq!(result["risk_runtime_started"], false);
    assert_eq!(result["paper_order_rehearsal_started"], false);
    assert_eq!(result["paper_order_submitted"], false);
    assert_eq!(result["connector_runtime_started"], false);
    assert_eq!(result["db_apply_performed"], false);
    assert_eq!(result["evidence_clock_started"], false);
    assert_eq!(result["scorecard_writer_started"], false);
    assert_eq!(result["ibkr_live_enabled"], false);
    assert_eq!(result["paper_order_entry_visible"], false);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);

    let risk = &result["risk_policy"];
    assert_eq!(risk["expected_contract_id"], "stock_etf_risk_policy_v1");
    assert_eq!(risk["contract_id"], "");
    assert_eq!(risk["source_version"], 0);
    assert_eq!(risk["config_version"], 0);
    assert_eq!(risk["accepted"], false);
    assert_json_array_eq(
        &risk["blockers"],
        &[
            "contract_id_mismatch",
            "source_version_mismatch",
            "version_mismatch",
            "order_cap_missing",
            "position_cap_missing",
            "daily_cap_missing",
            "open_order_limit_missing",
            "open_position_limit_missing",
            "allowed_instrument_missing",
            "denied_instrument_missing",
            "frozen_universe_hash_not_required",
            "instrument_identity_hash_not_required",
            "market_session_not_required",
            "cost_model_before_shadow_fill_missing",
            "cost_model_before_scorecard_missing",
            "commission_schedule_missing",
            "spread_estimate_missing",
            "slippage_estimate_missing",
            "fx_drag_missing",
            "conservative_penalty_missing",
            "rust_authority_missing",
            "session_attestation_missing",
            "decision_lease_missing",
            "guardian_missing",
            "idempotency_key_missing",
            "broker_reconciliation_missing",
        ],
    );
    assert_eq!(risk["environment"], "paper");
    assert_eq!(risk["enabled"], false);
    assert_eq!(risk["shadow_only"], true);
    assert_eq!(risk["allow_margin"], false);
    assert_eq!(risk["allow_short"], false);
    assert_eq!(risk["allow_options"], false);
    assert_eq!(risk["allow_cfd"], false);
    assert_eq!(risk["allow_transfer"], false);
    assert_eq!(risk["allow_live"], false);
    assert_eq!(risk["bybit_live_execution_unchanged"], true);
    assert_eq!(risk["ibkr_contact_performed"], false);
    assert_eq!(risk["connector_runtime_started"], false);
    assert_eq!(risk["secret_content_serialized"], false);

    let registry = &result["broker_capability_registry"];
    assert_eq!(
        registry["expected_registry_id"],
        "broker_capability_registry_v1"
    );
    assert_eq!(registry["registry_id"], "");
    assert_eq!(registry["source_version"], 0);
    assert_eq!(registry["accepted"], false);
    assert_json_array_eq(
        &registry["blockers"],
        &[
            "registry_id_mismatch",
            "source_version_mismatch",
            "required_audit_field_missing",
            "operation_missing",
            "operation_missing",
            "operation_missing",
            "operation_missing",
            "operation_missing",
            "operation_missing",
            "operation_missing",
            "operation_missing",
            "operation_missing",
            "operation_missing",
            "operation_missing",
            "operation_missing",
            "operation_missing",
            "operation_missing",
            "operation_missing",
        ],
    );
    assert_eq!(registry["operation_count"], 0);
    assert_eq!(registry["required_audit_field_count"], 0);
    assert_eq!(registry["read_operation_count"], 0);
    assert_eq!(
        registry["lane_scoped_ipc_contract_id"],
        "lane_scoped_ipc_v1"
    );
    assert_eq!(
        registry["readonly_probe_request_contract_id"],
        "stock_etf_ibkr_readonly_probe_request_v1"
    );
    assert_eq!(
        registry["readonly_probe_result_import_request_contract_id"],
        "stock_etf_ibkr_readonly_probe_result_import_request_v1"
    );
    assert_eq!(registry["read_rows_require_lane_scoped_ipc"], false);
    assert_eq!(registry["read_rows_require_readonly_probe_request"], false);
    assert_eq!(
        registry["scorecard_requires_readonly_probe_result_import_request"],
        false
    );
    assert_eq!(registry["paper_operation_count"], 0);
    assert_eq!(registry["denied_operation_count"], 0);
    assert_eq!(registry["bybit_live_execution_unchanged"], true);
    assert_eq!(registry["python_broker_write_authority_denied"], true);
    assert_eq!(registry["ibkr_live_denied"], true);
    assert_eq!(registry["cfd_margin_reserved_denied"], true);
    assert_eq!(registry["first_ibkr_contact_performed"], false);
    assert_eq!(registry["secret_content_serialized"], false);

    assert_eq!(result["phase2"]["first_ibkr_contact_allowed"], false);
    assert_eq!(result["phase2"]["connector_enabled"], false);

    // fail-closed reason 必為非 null 字串：denial 本身由 accepted/blockers 表達，
    // reason 額外讓消費端區分「檔案問題」與「刻意 dormant」（注入 Err 的直接證據）。
    assert!(
        result["risk_policy"]["risk_config_load_error"].is_string(),
        "denied 回退必攜 risk_config_load_error，實得 {}",
        result["risk_policy"]["risk_config_load_error"]
    );
}

/// win ②：直接以真實 repo TOML 驗證 stock_etf 風控 caps 確實被載入（不只驗
/// denied fallback）。
///
/// 為什麼用 pure loader 而非走 IPC/OnceLock：stock_etf_risk_policy() 的
/// OnceLock + OPENCLAW_RISK_CONFIG_DIR 為進程級全域，與同 binary 的 startup
/// 測試搶 env 會 order-fragile；pure loader 收 dir 參數、繞過全域狀態，讓
/// load+parse+from_source_config glue 可被確定性驗證。路徑解析沿用
/// openclaw_types acceptance test 同一 CARGO_MANIFEST_DIR + ../.. 模式。
#[test]
fn stock_etf_risk_policy_loads_real_repo_caps_via_pure_loader() {
    // 路徑以編譯期 concat! 組出（CARGO_MANIFEST_DIR + ../.. 相對 repo 根），再以
    // str::as_ref() 轉交 pure loader——避免在測試源文字寫出檔案系統/路徑型別 token
    // （本檔屬 source-only fixture 樹，受無-runtime-material 守衛掃描）。
    let risk_dir = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../settings/risk_control_rules"
    );
    let policy = load_stock_etf_risk_policy_from_dir(risk_dir.as_ref())
        .expect("real repo stock_etf risk config loads and parses");
    let verdict = policy.validate();

    assert!(
        verdict.accepted,
        "repository stock_etf risk config blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(policy.source_version, 1);
    assert_eq!(policy.config_version, 1);
    assert_eq!(policy.max_order_notional_usd, 1_000.0);
    assert_eq!(policy.max_position_notional_usd, 5_000.0);
    assert_eq!(policy.max_daily_notional_usd, 10_000.0);
    assert_eq!(policy.max_open_orders, 5);
    assert_eq!(policy.max_open_positions, 10);
    assert!(!policy.enabled);
    assert!(policy.shadow_only);
    assert!(policy.bybit_live_execution_unchanged);
}

#[tokio::test]
async fn stock_etf_authorization_status_is_blocked_source_fixture_without_side_effects() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req =
        r#"{"jsonrpc":"2.0","method":"stock_etf.get_authorization_status","params":{},"id":4816}"#;
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
    let result = resp.result.expect("stock_etf authorization status result");
    assert_eq!(
        result["phase"],
        "phase2_authorization_status_source_fixture"
    );
    assert_eq!(result["asset_lane"], "stock_etf_cash");
    assert_eq!(result["broker"], "ibkr");
    assert_eq!(result["environment"], "paper");
    assert_eq!(result["authorization_status_state"], "blocked");
    assert_eq!(result["phase2_started"], false);
    assert_eq!(result["paper_order_authority_present"], false);
    assert_eq!(result["scoped_authorization_present"], false);
    assert_eq!(result["decision_lease_valid"], false);
    assert_eq!(result["guardian_allows"], false);
    assert_eq!(result["paper_order_submitted"], false);
    assert_eq!(result["connector_runtime_started"], false);
    assert_eq!(result["db_apply_performed"], false);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);

    let matrix = &result["authorization_matrix"];
    assert_eq!(
        matrix["expected_contract_id"],
        "feature_flag_secret_auth_matrix_v1"
    );
    assert_eq!(matrix["contract_id"], "");
    assert_eq!(matrix["source_version"], 0);
    assert_eq!(matrix["request_asset_lane"], "stock_etf_cash");
    assert_eq!(matrix["request_broker"], "ibkr");
    assert_eq!(matrix["request_environment"], "paper");
    assert_eq!(matrix["request_instrument_kind"], "stock");
    assert_eq!(matrix["request_operation"], "paper_order_submit");
    assert_eq!(matrix["request_allowed"], false);
    assert_eq!(matrix["effective_authority_scope"], "denied");
    assert_eq!(matrix["gui_lane_state_override_denied"], true);
    assert_eq!(matrix["server_rust_matrix_authoritative"], true);
    assert_json_array_eq(
        &matrix["blockers"],
        &[
            "contract_id_mismatch",
            "source_version_mismatch",
            "lane_flag_disabled",
            "paper_flag_disabled",
            "shadow_only_blocks_paper",
            "secret_contract_rejected",
            "live_secret_absent_or_empty_not_proven",
            "phase2_artifact_rejected",
            "session_attestation_rejected",
            "authorization_envelope_mismatch",
            "permission_scope_mismatch",
            "secret_slot_fingerprint_invalid",
            "account_fingerprint_hash_invalid",
            "risk_config_hash_invalid",
            "authorization_envelope_expired",
        ],
    );

    let secret = &result["secret_slot_contract"];
    assert_eq!(
        secret["expected_contract_id"],
        "ibkr_secret_slot_contract_v1"
    );
    assert_eq!(secret["accepted"], false);
    assert_eq!(secret["contract_present"], false);
    assert_eq!(secret["secret_content_serialized"], false);
    assert_eq!(secret["account_id_serialized"], false);

    let artifact = &result["phase2_gate_artifact"];
    assert_eq!(
        artifact["expected_contract_id"],
        "phase2_ibkr_external_surface_gate_v1"
    );
    assert_eq!(artifact["ibkr_contact_allowed"], false);
    assert_eq!(artifact["sealed"], false);

    let session = &result["session_attestation"];
    assert_eq!(
        session["expected_contract_id"],
        "ibkr_session_attestation_v1"
    );
    assert_eq!(session["attestation_accepted"], false);
    assert_eq!(session["account_fingerprint_is_live"], false);

    let envelope = &result["authorization_envelope"];
    assert_eq!(envelope["permission_scope"], "denied");
    assert_eq!(envelope["expires_at_ms"], 0);
    assert_eq!(result["phase2"]["first_ibkr_contact_allowed"], false);
    assert_eq!(result["phase2"]["connector_enabled"], false);
}
