use super::*;

pub(super) fn account_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let cash_ledger = BrokerAccountPortfolioCashLedgerV1::default();
    let cash_ledger_verdict = cash_ledger.validate();
    let session_attestation = IbkrSessionAttestationV1::default();
    let session_attestation_verdict = session_attestation.validate(0);
    let paper_attestation_policy = IbkrPaperAttestationPolicyV1::source_template();
    let paper_attestation_policy_verdict = paper_attestation_policy.validate();

    serde_json::json!({
        "phase": "phase2_account_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "environment": "paper_readonly",
        "account_status_state": "blocked",
        "phase2_started": false,
        "readonly_account_snapshot_started": false,
        "paper_account_snapshot_started": false,
        "account_snapshot_present": false,
        "portfolio_positions_snapshot_present": false,
        "cash_ledger_present": false,
        "paper_account_attestation_present": false,
        "session_attestation_present": false,
        "connector_runtime_started": false,
        "gateway_socket_open": false,
        "account_snapshot": {
            "expected_contract_id": BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID,
            "contract_id": cash_ledger.contract_id,
            "source_version": cash_ledger.source_version,
            "accepted": cash_ledger_verdict.accepted,
            "blockers": cash_ledger_verdict.blockers,
            "account_fingerprint_hash_present": !cash_ledger.account_fingerprint_hash.is_empty(),
            "account_snapshot_hash_present": !cash_ledger.account_snapshot_hash.is_empty(),
            "portfolio_positions_hash_present": !cash_ledger.portfolio_positions_hash.is_empty(),
            "currency": cash_ledger.currency,
            "cash_balance_minor_units": cash_ledger.cash_balance_minor_units,
            "buying_power_minor_units": cash_ledger.buying_power_minor_units,
            "as_of_ms": cash_ledger.as_of_ms,
            "source_report_hash_present": !cash_ledger.source_report_hash.is_empty(),
        },
        "session_attestation": {
            "expected_contract_id": IBKR_SESSION_ATTESTATION_CONTRACT_ID,
            "contract_id": session_attestation.contract_id,
            "source_version": session_attestation.source_version,
            "status": session_attestation.status,
            "accepted": session_attestation_verdict.attestation_accepted,
            "blockers": session_attestation_verdict.blockers,
            "account_fingerprint_present": !session_attestation.account_fingerprint.is_empty(),
            "account_fingerprint_is_live": session_attestation.account_fingerprint_is_live,
            "environment": session_attestation.environment,
            "host": session_attestation.host,
            "port": session_attestation.port,
            "process_identity_present": !session_attestation.process_identity.is_empty(),
            "gateway_mode": session_attestation.gateway_mode,
            "secret_slot_fingerprint_present": !session_attestation.secret_slot_fingerprint.is_empty(),
            "secret_slot_mode": session_attestation.secret_slot_mode,
            "secret_world_readable": session_attestation.secret_world_readable,
            "live_secret_absent_or_empty": session_attestation.live_secret_absent_or_empty,
            "env_var_credential_fallback_used": session_attestation.env_var_credential_fallback_used,
            "api_server_version_present": !session_attestation.api_server_version.is_empty(),
            "attested_at_ms": session_attestation.attested_at_ms,
            "expires_at_ms": session_attestation.expires_at_ms,
            "raw_artifact_hash_present": !session_attestation.raw_artifact_hash.is_empty(),
        },
        "paper_attestation_policy": {
            "expected_contract_id": IBKR_PAPER_ATTESTATION_CONTRACT_ID,
            "contract_id": paper_attestation_policy.contract_id,
            "source_version": paper_attestation_policy.source_version,
            "accepted": paper_attestation_policy_verdict.accepted,
            "blockers": paper_attestation_policy_verdict.blockers,
            "external_surface_gate_required": paper_attestation_policy.external_surface_gate_required,
            "session_attestation_required": paper_attestation_policy.session_attestation_required,
            "rust_lane_scoped_ipc_required": paper_attestation_policy.rust_lane_scoped_ipc_required,
            "decision_lease_required": paper_attestation_policy.decision_lease_required,
            "guardian_required": paper_attestation_policy.guardian_required,
            "paper_environment_only": paper_attestation_policy.paper_environment_only,
            "live_account_fingerprint_denied": paper_attestation_policy.live_account_fingerprint_denied,
            "margin_short_options_cfd_denied": paper_attestation_policy.margin_short_options_cfd_denied,
        },
        "phase2": phase2,
        "ibkr_live_enabled": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
        "db_apply_performed": false,
    })
}

pub(super) fn reconciliation_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let lifecycle_event = BrokerLifecycleEventLogV1::default();
    let lifecycle_verdict = lifecycle_event.validate();
    let shadow_fill_model = StockShadowFillModelV1::default();
    let shadow_fill_verdict = shadow_fill_model.validate();
    let reconciliation = StockEtfPaperShadowReconciliationV1::default();
    let reconciliation_verdict = reconciliation.validate();
    let matching = serde_json::json!({
        "expected_lifecycle_contract_id": IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID,
        "lifecycle_contract_id": lifecycle_event.lifecycle_contract_id,
        "expected_event_log_contract_id": BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID,
        "event_log_contract_id": lifecycle_event.event_log_contract_id,
        "expected_shadow_contract_id": STOCK_SHADOW_FILL_MODEL_CONTRACT_ID,
        "shadow_contract_id": shadow_fill_model.contract_id,
        "expected_reconciliation_contract_id": STOCK_ETF_PAPER_SHADOW_RECONCILIATION_CONTRACT_ID,
        "reconciliation_contract_id": reconciliation.contract_id,
        "reconciliation_accepted": reconciliation_verdict.accepted,
        "reconciliation_blockers": reconciliation_verdict.blockers,
        "lifecycle_event_accepted": lifecycle_verdict.accepted,
        "shadow_fill_model_accepted": shadow_fill_verdict.accepted,
        "lifecycle_blockers": lifecycle_verdict.blockers,
        "shadow_blockers": shadow_fill_verdict.blockers,
        "append_only_event_ready": lifecycle_verdict.accepted,
        "paper_order_id_present": !lifecycle_event.order_local_id.is_empty(),
        "broker_order_id_present": !lifecycle_event.broker_order_id.is_empty(),
        "execution_id_present": !lifecycle_event.execution_id.is_empty(),
        "commission_report_id_present": !lifecycle_event.commission_report_id.is_empty(),
        "shadow_signal_id_present": !shadow_fill_model.signal_id.is_empty(),
        "shadow_fill_price_present": shadow_fill_model.conservative_fill_price_micros > 0,
        "paper_shadow_link_present": shadow_fill_model.broker_paper_fill_linked,
        "divergence_bps": 0,
        "divergence_threshold_bps": 0,
        "divergence_within_threshold": false,
        "unmatched_paper_fill_count": 0,
        "unmatched_shadow_fill_count": 0,
        "reconciliation_run_id_present": !lifecycle_event.reconciliation_run_id.is_empty(),
        "contract_reconciliation_run_id_present": !reconciliation.reconciliation_run_id.is_empty(),
        "paper_shadow_link_hash_present": !reconciliation.paper_shadow_link_hash.is_empty(),
        "paper_fill_imported": reconciliation.paper_fill_imported,
        "shadow_fill_synthetic": reconciliation.shadow_fill_synthetic,
        "raw_artifact_hash_present": !lifecycle_event.raw_artifact_hash.is_empty(),
        "redacted_summary_hash_present": !lifecycle_event.redacted_summary_hash.is_empty(),
        "reconciliation_writer_started": reconciliation.reconciliation_writer_started,
        "ibkr_contact_performed": reconciliation.ibkr_contact_performed,
        "connector_runtime_started": reconciliation.connector_runtime_started,
        "secret_content_serialized": reconciliation.secret_content_serialized,
        "fill_import_performed": reconciliation.fill_import_performed,
        "shadow_fill_generated": reconciliation.shadow_fill_generated,
    });

    serde_json::json!({
        "phase": "phase3_reconciliation_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "environment": "paper_shadow",
        "reconciliation_status_state": "blocked",
        "phase3_started": false,
        "paper_shadow_reconciliation_started": false,
        "paper_orders_ready": false,
        "paper_fills_ready": false,
        "shadow_fills_ready": false,
        "scorecard_writer_started": false,
        "db_apply_performed": false,
        "matching": matching,
        "phase2": phase2,
        "ibkr_live_enabled": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
    })
}

pub(super) fn scorecard_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let input_bundle = StockEtfScorecardInputBundleV1::default();
    let input_bundle_verdict = input_bundle.validate();
    let derivation = StockEtfScorecardDerivationV1::default();
    let derivation_verdict = derivation.validate();
    let verdict = StockEtfScorecardVerdictV1::default();
    let scorecard_verdict = verdict.validate();
    let scorecard_input_bundle = serde_json::json!({
        "accepted": input_bundle_verdict.accepted,
        "blockers": input_bundle_verdict.blockers,
        "readonly_probe_result_import_request_contract_id": &input_bundle.readonly_probe_result_import_request_contract_id,
        "readonly_probe_result_import_request_hash_present": !input_bundle.readonly_probe_result_import_request_hash.is_empty(),
        "market_data_provenance_contract_hash_present": !input_bundle.market_data_provenance_contract_hash.is_empty(),
        "reference_data_sources_contract_hash_present": !input_bundle.reference_data_sources_contract_hash.is_empty(),
        "risk_policy_contract_hash_present": !input_bundle.risk_policy_contract_hash.is_empty(),
        "atomic_fact_input_hash_present": !input_bundle.atomic_fact_input_hash.is_empty(),
        "source_commit_present": !input_bundle.source_commit.is_empty(),
        "scorecard_is_derived_only": input_bundle.scorecard_is_derived_only,
        "paper_and_shadow_fills_separate": input_bundle.paper_and_shadow_fills_separate,
        "live_fill_claimed": input_bundle.live_fill_claimed,
        "bybit_live_execution_unchanged": input_bundle.bybit_live_execution_unchanged,
        "ibkr_contact_performed": input_bundle.ibkr_contact_performed,
        "connector_runtime_started": input_bundle.connector_runtime_started,
        "broker_fill_import_performed": input_bundle.broker_fill_import_performed,
        "scorecard_writer_started": input_bundle.scorecard_writer_started,
        "db_apply_performed": input_bundle.db_apply_performed,
        "evidence_clock_started": input_bundle.evidence_clock_started,
        "secret_content_serialized": input_bundle.secret_content_serialized,
        "live_or_tiny_live_authorized": input_bundle.live_or_tiny_live_authorized,
    });
    let derivation = serde_json::json!({
        "expected_contract_id": STOCK_ETF_SCORECARD_DERIVATION_CONTRACT_ID,
        "contract_id": &derivation.contract_id,
        "source_version": derivation.source_version,
        "accepted": derivation_verdict.accepted,
        "blockers": derivation_verdict.blockers,
        "derivation_run_id_present": !derivation.derivation_run_id.is_empty(),
        "strategy_id_present": !derivation.strategy_id.is_empty(),
        "universe_version_present": !derivation.universe_version.is_empty(),
        "benchmark_version_present": !derivation.benchmark_version.is_empty(),
        "as_of_date_present": !derivation.as_of_date.is_empty(),
        "scorecard_input_bundle_hash_present": !derivation.scorecard_input_bundle_hash.is_empty(),
        "paper_shadow_reconciliation_hash_present": !derivation.paper_shadow_reconciliation_hash.is_empty(),
        "scorecard_verdict_hash_present": !derivation.scorecard_verdict_hash.is_empty(),
        "output_artifact_hash_present": !derivation.output_artifact_hash.is_empty(),
        "derived_from_atomic_facts_only": derivation.derived_from_atomic_facts_only,
        "idempotent_replay_proven": derivation.idempotent_replay_proven,
        "paper_and_shadow_fills_separate": derivation.paper_and_shadow_fills_separate,
        "bybit_live_execution_unchanged": derivation.bybit_live_execution_unchanged,
        "ibkr_contact_performed": derivation.ibkr_contact_performed,
        "connector_runtime_started": derivation.connector_runtime_started,
        "broker_fill_import_performed": derivation.broker_fill_import_performed,
        "shadow_fill_generated": derivation.shadow_fill_generated,
        "reconciliation_writer_started": derivation.reconciliation_writer_started,
        "scorecard_writer_started": derivation.scorecard_writer_started,
        "db_apply_performed": derivation.db_apply_performed,
        "evidence_clock_started": derivation.evidence_clock_started,
        "secret_content_serialized": derivation.secret_content_serialized,
        "live_or_tiny_live_authorized": derivation.live_or_tiny_live_authorized,
        "sealed": derivation.sealed,
    });
    let mut scorecard = serde_json::Map::new();
    macro_rules! put_scorecard {
        ($key:literal, $value:expr) => {
            scorecard.insert($key.to_string(), serde_json::json!($value));
        };
    }
    put_scorecard!(
        "expected_contract_id",
        STOCK_ETF_SCORECARD_VERDICT_CONTRACT_ID
    );
    put_scorecard!("contract_id", &verdict.contract_id);
    put_scorecard!("source_version", verdict.source_version);
    put_scorecard!("accepted", scorecard_verdict.accepted);
    put_scorecard!("blockers", scorecard_verdict.blockers);
    put_scorecard!("verdict_label", verdict.verdict_label);
    put_scorecard!(
        "scorecard_input_bundle_hash_present",
        !verdict.scorecard_input_bundle_hash.is_empty()
    );
    put_scorecard!(
        "evidence_clock_manifest_hash_present",
        !verdict.evidence_clock_manifest_hash.is_empty()
    );
    put_scorecard!(
        "dq_manifest_hash_present",
        !verdict.dq_manifest_hash.is_empty()
    );
    put_scorecard!(
        "formula_appendix_hash_present",
        !verdict.formula_appendix_hash.is_empty()
    );
    put_scorecard!(
        "statistical_preregistration_hash_present",
        !verdict.statistical_preregistration_hash.is_empty()
    );
    put_scorecard!(
        "benchmark_version_hash_present",
        !verdict.benchmark_version_hash.is_empty()
    );
    put_scorecard!(
        "cost_model_version_hash_present",
        !verdict.cost_model_version_hash.is_empty()
    );
    put_scorecard!(
        "strategy_hypothesis_hash_present",
        !verdict.strategy_hypothesis_hash.is_empty()
    );
    put_scorecard!(
        "reference_data_sources_hash_present",
        !verdict.reference_data_sources_hash.is_empty()
    );
    put_scorecard!(
        "paper_shadow_reconciliation_hash_present",
        !verdict.paper_shadow_reconciliation_hash.is_empty()
    );
    put_scorecard!(
        "scorecard_manifest_hash_present",
        !verdict.scorecard_manifest_hash.is_empty()
    );
    put_scorecard!(
        "verdict_rationale_hash_present",
        !verdict.verdict_rationale_hash.is_empty()
    );
    put_scorecard!(
        "paper_shadow_window_trading_days",
        verdict.paper_shadow_window_trading_days
    );
    put_scorecard!("min_window_trading_days", verdict.min_window_trading_days);
    put_scorecard!(
        "independent_observation_count",
        verdict.independent_observation_count
    );
    put_scorecard!(
        "min_independent_observation_count",
        verdict.min_independent_observation_count
    );
    put_scorecard!("gross_pnl_minor_units", verdict.gross_pnl_minor_units);
    put_scorecard!("net_pnl_minor_units", verdict.net_pnl_minor_units);
    put_scorecard!("commission_minor_units", verdict.commission_minor_units);
    put_scorecard!(
        "spread_slippage_minor_units",
        verdict.spread_slippage_minor_units
    );
    put_scorecard!("fx_drag_minor_units", verdict.fx_drag_minor_units);
    put_scorecard!("tax_drag_minor_units", verdict.tax_drag_minor_units);
    put_scorecard!("benchmark_excess_lcb_bps", verdict.benchmark_excess_lcb_bps);
    put_scorecard!(
        "conservative_cost_stress_lcb_bps",
        verdict.conservative_cost_stress_lcb_bps
    );
    put_scorecard!(
        "paper_shadow_divergence_bps",
        verdict.paper_shadow_divergence_bps
    );
    put_scorecard!(
        "max_paper_shadow_divergence_bps",
        verdict.max_paper_shadow_divergence_bps
    );
    put_scorecard!("psr_bps", verdict.psr_bps);
    put_scorecard!("min_psr_bps", verdict.min_psr_bps);
    put_scorecard!("dsr_bps", verdict.dsr_bps);
    put_scorecard!("min_dsr_bps", verdict.min_dsr_bps);
    put_scorecard!(
        "concentration_label_passed",
        verdict.concentration_label_passed
    );
    put_scorecard!("regime_label_passed", verdict.regime_label_passed);
    put_scorecard!("breadth_label_passed", verdict.breadth_label_passed);
    put_scorecard!("freshness_label_passed", verdict.freshness_label_passed);
    put_scorecard!(
        "survivorship_label_passed",
        verdict.survivorship_label_passed
    );
    put_scorecard!(
        "execution_realism_label_passed",
        verdict.execution_realism_label_passed
    );
    put_scorecard!("qc_review_hash_present", !verdict.qc_review_hash.is_empty());
    put_scorecard!(
        "mit_review_hash_present",
        !verdict.mit_review_hash.is_empty()
    );
    put_scorecard!("qa_review_hash_present", !verdict.qa_review_hash.is_empty());
    put_scorecard!("qc_review_passed", verdict.qc_review_passed);
    put_scorecard!("mit_review_passed", verdict.mit_review_passed);
    put_scorecard!("qa_review_passed", verdict.qa_review_passed);
    put_scorecard!(
        "scorecard_is_derived_only",
        verdict.scorecard_is_derived_only
    );
    put_scorecard!(
        "paper_and_shadow_fills_separate",
        verdict.paper_and_shadow_fills_separate
    );
    put_scorecard!("live_fill_claimed", verdict.live_fill_claimed);
    put_scorecard!(
        "bybit_live_execution_unchanged",
        verdict.bybit_live_execution_unchanged
    );
    put_scorecard!("sealed", verdict.sealed);
    let scorecard = serde_json::Value::Object(scorecard);

    serde_json::json!({
        "phase": "phase3_scorecard_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "environment": "paper_shadow",
        "scorecard_status_state": "blocked",
        "phase3_started": false,
        "scorecard_writer_started": false,
        "db_apply_performed": false,
        "evidence_clock_started": false,
        "paper_shadow_window_complete": false,
        "scorecard_input_bundle": scorecard_input_bundle,
        "scorecard_derivation": derivation,
        "scorecard": scorecard,
        "phase2": phase2,
        "ibkr_live_enabled": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
        "live_or_tiny_live_authorized": false,
    })
}

pub(super) fn launch_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let release_packet = StockEtfReleasePacketV1::default();
    let release_verdict = release_packet.validate();
    let disable_cleanup = StockEtfDisableCleanupRunbookV1::default();
    let disable_verdict = disable_cleanup.validate();
    let tiny_live = TinyLiveAdrEligibilityV1::default();
    let tiny_live_verdict = tiny_live.validate();

    serde_json::json!({
        "phase": "phase5_launch_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "environment": "paper_shadow",
        "launch_status_state": "blocked",
        "phase3_started": false,
        "phase5_started": false,
        "release_packet": {
            "expected_contract_id": STOCK_ETF_RELEASE_PACKET_CONTRACT_ID,
            "packet_id": release_packet.packet_id,
            "source_version": release_packet.source_version,
            "accepted": release_verdict.accepted,
            "blockers": release_verdict.blockers,
            "paper_shadow_window_complete": release_packet.paper_shadow_window_complete,
            "engineering_shakedown_complete": release_packet.engineering_shakedown_complete,
            "role_report_count": release_packet.role_report_paths.len(),
            "manifest_hash_count": release_packet.manifest_hashes.len(),
            "gui_screenshot_hash_count": release_packet.gui_screenshot_hashes.len(),
            "dq_manifest_hash_count": release_packet.dq_manifest_hashes.len(),
            "scorecard_regeneration_hash_count": release_packet.scorecard_regeneration_hashes.len(),
            "pg_migrations_declared": release_packet.pg_migration_evidence.migrations_declared,
            "pg_dry_run_log_hash_present": !release_packet.pg_migration_evidence.pg_dry_run_log_hash.is_empty(),
            "pg_double_apply_log_hash_present": !release_packet.pg_migration_evidence.pg_double_apply_log_hash.is_empty(),
            "redaction_fixture_hash_present": !release_packet.redaction_fixture_hash.is_empty(),
            "evidence_archive_pointer_present": !release_packet.evidence_archive_pointer.is_empty(),
            "evidence_archive_hash_present": !release_packet.evidence_archive_hash.is_empty(),
            "secret_content_serialized": release_packet.secret_content_serialized,
            "ibkr_live_or_tiny_live_authorized": release_packet.ibkr_live_or_tiny_live_authorized,
            "sealed": release_packet.sealed,
        },
        "disable_cleanup_runbook": {
            "expected_runbook_id": STOCK_ETF_DISABLE_CLEANUP_RUNBOOK_ID,
            "runbook_id": disable_cleanup.runbook_id,
            "source_version": disable_cleanup.source_version,
            "accepted": disable_verdict.accepted,
            "blockers": disable_verdict.blockers,
            "bybit_live_execution_unchanged": disable_cleanup.bybit_live_execution_unchanged,
            "env_flag_count": disable_cleanup.env_flags.len(),
            "proof_count": disable_cleanup.proofs.len(),
            "ibkr_contact_performed": disable_cleanup.ibkr_contact_performed,
            "connector_runtime_started": disable_cleanup.connector_runtime_started,
            "paper_order_routed": disable_cleanup.paper_order_routed,
            "secret_slot_created": disable_cleanup.secret_slot_created,
            "secret_content_serialized": disable_cleanup.secret_content_serialized,
            "destructive_db_cleanup_requested": disable_cleanup.destructive_db_cleanup_requested,
            "db_delete_or_truncate_allowed": disable_cleanup.db_delete_or_truncate_allowed,
            "paper_shadow_launch_authorized": disable_cleanup.paper_shadow_launch_authorized,
            "tiny_live_authorized": disable_cleanup.tiny_live_authorized,
            "live_authorized": disable_cleanup.live_authorized,
        },
        "tiny_live_adr_eligibility": {
            "expected_contract_id": STOCK_ETF_TINY_LIVE_ADR_ELIGIBILITY_CONTRACT_ID,
            "contract_id": tiny_live.contract_id,
            "source_version": tiny_live.source_version,
            "accepted": tiny_live_verdict.accepted,
            "blockers": tiny_live_verdict.blockers,
            "decision": tiny_live.decision,
            "scorecard_derivation_hash_present": !tiny_live.scorecard_derivation_hash.is_empty(),
            "scorecard_verdict_hash_present": !tiny_live.scorecard_verdict_hash.is_empty(),
            "scorecard_manifest_hash_present": !tiny_live.scorecard_manifest_hash.is_empty(),
            "paper_shadow_reconciliation_hash_present": !tiny_live.paper_shadow_reconciliation_hash.is_empty(),
            "dq_manifest_hash_present": !tiny_live.dq_manifest_hash.is_empty(),
            "statistical_preregistration_hash_present": !tiny_live.statistical_preregistration_hash.is_empty(),
            "qc_review_hash_present": !tiny_live.qc_review_hash.is_empty(),
            "mit_review_hash_present": !tiny_live.mit_review_hash.is_empty(),
            "qa_review_hash_present": !tiny_live.qa_review_hash.is_empty(),
            "paper_shadow_window_complete": tiny_live.paper_shadow_window_complete,
            "benchmark_relative_after_cost_lcb_bps": tiny_live.benchmark_relative_after_cost_lcb_bps,
            "independent_observation_count": tiny_live.independent_observation_count,
            "min_independent_observation_count": tiny_live.min_independent_observation_count,
            "conservative_cost_stress_lcb_bps": tiny_live.conservative_cost_stress_lcb_bps,
            "paper_shadow_divergence_bps": tiny_live.paper_shadow_divergence_bps,
            "max_paper_shadow_divergence_bps": tiny_live.max_paper_shadow_divergence_bps,
            "concentration_label_passed": tiny_live.concentration_label_passed,
            "regime_label_passed": tiny_live.regime_label_passed,
            "freshness_label_passed": tiny_live.freshness_label_passed,
            "qc_review_passed": tiny_live.qc_review_passed,
            "mit_review_passed": tiny_live.mit_review_passed,
            "qa_review_passed": tiny_live.qa_review_passed,
            "secret_content_serialized": tiny_live.secret_content_serialized,
            "sealed": tiny_live.sealed,
        },
        "phase2": phase2,
        "ibkr_live_enabled": false,
        "paper_shadow_launch_authorized": false,
        "tiny_live_or_live_authorized": false,
        "connector_runtime_started": false,
        "scorecard_writer_started": false,
        "db_apply_performed": false,
        "evidence_clock_started": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
    })
}

pub(super) fn disable_cleanup_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let runbook = StockEtfDisableCleanupRunbookV1::accepted_fixture();
    let verdict = runbook.validate();
    let env_flags: Vec<serde_json::Value> = runbook
        .env_flags
        .iter()
        .map(|flag| {
            serde_json::json!({
                "name": flag.name,
                "expected_value": flag.expected_value,
                "observed_value": flag.observed_value,
                "evidence_hash_present": !flag.evidence_hash.is_empty(),
            })
        })
        .collect();
    let proofs: Vec<serde_json::Value> = runbook
        .proofs
        .iter()
        .map(|proof| {
            serde_json::json!({
                "kind": proof.kind,
                "verified": proof.verified,
                "evidence_hash_present": !proof.evidence_hash.is_empty(),
                "grants_runtime_authority": proof.grants_runtime_authority,
                "destructive_cleanup_claimed": proof.destructive_cleanup_claimed,
            })
        })
        .collect();

    serde_json::json!({
        "phase": "phase5_disable_cleanup_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "environment": "paper_shadow",
        "disable_cleanup_status_state": "source_ready_runtime_blocked",
        "phase3_started": false,
        "phase5_started": false,
        "collector_stop_requested": false,
        "gui_disable_requested": false,
        "evidence_archive_requested": false,
        "db_cleanup_requested": false,
        "runbook": {
            "expected_runbook_id": STOCK_ETF_DISABLE_CLEANUP_RUNBOOK_ID,
            "runbook_id": runbook.runbook_id,
            "source_version": runbook.source_version,
            "accepted": verdict.accepted,
            "blockers": verdict.blockers,
            "source_artifact_hash_present": !runbook.source_artifact_hash.is_empty(),
            "bybit_live_execution_unchanged": runbook.bybit_live_execution_unchanged,
            "env_flag_count": runbook.env_flags.len(),
            "proof_count": runbook.proofs.len(),
            "env_flags": env_flags,
            "proofs": proofs,
            "ibkr_contact_performed": runbook.ibkr_contact_performed,
            "connector_runtime_started": runbook.connector_runtime_started,
            "paper_order_routed": runbook.paper_order_routed,
            "secret_slot_created": runbook.secret_slot_created,
            "secret_content_serialized": runbook.secret_content_serialized,
            "destructive_db_cleanup_requested": runbook.destructive_db_cleanup_requested,
            "db_delete_or_truncate_allowed": runbook.db_delete_or_truncate_allowed,
            "paper_shadow_launch_authorized": runbook.paper_shadow_launch_authorized,
            "tiny_live_authorized": runbook.tiny_live_authorized,
            "live_authorized": runbook.live_authorized,
        },
        "phase2": phase2,
        "ibkr_live_enabled": false,
        "paper_shadow_launch_authorized": false,
        "tiny_live_or_live_authorized": false,
        "connector_runtime_started": false,
        "scorecard_writer_started": false,
        "db_apply_performed": false,
        "evidence_clock_started": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
    })
}

pub(super) fn release_packet_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let packet = StockEtfReleasePacketV1::accepted_fixture();
    let verdict = packet.validate();
    let manifest_hashes: Vec<serde_json::Value> = packet
        .manifest_hashes
        .iter()
        .map(|entry| {
            serde_json::json!({
                "label": entry.label,
                "hash_present": !entry.sha256.is_empty(),
            })
        })
        .collect();
    let kill = &packet.kill_disable_cleanup_proof;
    let kill_disable_cleanup_proof = serde_json::json!({
        "stock_etf_lane_enabled_false": kill.stock_etf_lane_enabled_false,
        "ibkr_readonly_enabled_false": kill.ibkr_readonly_enabled_false,
        "ibkr_paper_enabled_false": kill.ibkr_paper_enabled_false,
        "stock_etf_shadow_only_true": kill.stock_etf_shadow_only_true,
        "collector_stopped": kill.collector_stopped,
        "gui_stock_views_disabled_or_hidden": kill.gui_stock_views_disabled_or_hidden,
        "live_secret_absence_proven": kill.live_secret_absence_proven,
        "evidence_archive_forward_only": kill.evidence_archive_forward_only,
        "destructive_db_cleanup_requested": kill.destructive_db_cleanup_requested,
        "proof_hash_present": !kill.proof_hash.is_empty(),
    });
    let release_packet = serde_json::json!({
        "expected_contract_id": STOCK_ETF_RELEASE_PACKET_CONTRACT_ID,
        "packet_id": &packet.packet_id,
        "source_version": packet.source_version,
        "accepted": verdict.accepted,
        "blockers": &verdict.blockers,
        "adr_path": &packet.adr_path,
        "amd_path": &packet.amd_path,
        "spec_path": &packet.spec_path,
        "source_commit_present": !packet.source_commit.is_empty(),
        "created_at_ms": packet.created_at_ms,
        "reviewer_role_count": packet.reviewer_roles.len(),
        "reviewer_roles": &packet.reviewer_roles,
        "role_report_count": packet.role_report_paths.len(),
        "e2_log_hash_present": !packet.e2_log_hash.is_empty(),
        "e3_redaction_log_hash_present": !packet.e3_redaction_log_hash.is_empty(),
        "e4_log_hash_present": !packet.e4_log_hash.is_empty(),
        "qa_log_hash_present": !packet.qa_log_hash.is_empty(),
        "manifest_hash_count": packet.manifest_hashes.len(),
        "manifest_hashes": manifest_hashes,
        "pg_migrations_declared": packet.pg_migration_evidence.migrations_declared,
        "pg_migration_manifest_hash_present": !packet.pg_migration_evidence.migration_manifest_hash.is_empty(),
        "pg_dry_run_log_hash_present": !packet.pg_migration_evidence.pg_dry_run_log_hash.is_empty(),
        "pg_double_apply_log_hash_present": !packet.pg_migration_evidence.pg_double_apply_log_hash.is_empty(),
        "redaction_fixture_hash_present": !packet.redaction_fixture_hash.is_empty(),
        "gui_screenshot_hash_count": packet.gui_screenshot_hashes.len(),
        "dq_manifest_hash_count": packet.dq_manifest_hashes.len(),
        "scorecard_regeneration_hash_count": packet.scorecard_regeneration_hashes.len(),
        "evidence_archive_pointer_present": !packet.evidence_archive_pointer.is_empty(),
        "evidence_archive_hash_present": !packet.evidence_archive_hash.is_empty(),
        "paper_shadow_window_complete": packet.paper_shadow_window_complete,
        "engineering_shakedown_complete": packet.engineering_shakedown_complete,
        "secret_content_serialized": packet.secret_content_serialized,
        "ibkr_live_or_tiny_live_authorized": packet.ibkr_live_or_tiny_live_authorized,
        "sealed": packet.sealed,
        "kill_disable_cleanup_proof": kill_disable_cleanup_proof,
    });

    serde_json::json!({
        "phase": "phase5_release_packet_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "environment": "paper_shadow",
        "release_packet_status_state": "source_ready_runtime_blocked",
        "phase3_started": false,
        "phase5_started": false,
        "release_packet": release_packet,
        "phase2": phase2,
        "ibkr_live_enabled": false,
        "paper_shadow_launch_authorized": false,
        "tiny_live_or_live_authorized": false,
        "connector_runtime_started": false,
        "scorecard_writer_started": false,
        "db_apply_performed": false,
        "evidence_clock_started": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
    })
}

pub(super) fn paper_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let lifecycle_event = BrokerLifecycleEventLogV1::default();
    let lifecycle_verdict = lifecycle_event.validate();
    let lifecycle_event_summary = serde_json::json!({
        "expected_lifecycle_contract_id": IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID,
        "lifecycle_contract_id": lifecycle_event.lifecycle_contract_id,
        "expected_event_log_contract_id": BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID,
        "event_log_contract_id": lifecycle_event.event_log_contract_id,
        "expected_request_contract_id": STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID,
        "request_contract_id": lifecycle_event.request_contract_id,
        "source_version": lifecycle_event.source_version,
        "accepted": lifecycle_verdict.accepted,
        "blockers": lifecycle_verdict.blockers,
        "operation": lifecycle_event.operation,
        "previous_state": lifecycle_event.previous_state,
        "next_state": lifecycle_event.next_state,
        "allowed": lifecycle_event.allowed,
        "denial_reason": lifecycle_event.denial_reason,
        "event_id_present": !lifecycle_event.event_id.is_empty(),
        "event_sequence": lifecycle_event.event_sequence,
        "event_sequence_present": lifecycle_event.event_sequence > 0,
        "genesis_event": lifecycle_event.genesis_event,
        "event_time_ms": lifecycle_event.event_time_ms,
        "previous_event_hash_present": !lifecycle_event.previous_event_hash.is_empty(),
        "event_hash_present": !lifecycle_event.event_hash.is_empty(),
        "request_envelope_hash_present": !lifecycle_event.request_envelope_hash.is_empty(),
        "stale_state_policy": lifecycle_event.stale_state_policy,
        "stale_state_policy_present": lifecycle_event.stale_state_policy.is_some(),
        "order_local_id_present": !lifecycle_event.order_local_id.is_empty(),
        "idempotency_key_present": !lifecycle_event.idempotency_key.is_empty(),
        "broker_order_id_present": !lifecycle_event.broker_order_id.is_empty(),
        "execution_id_present": !lifecycle_event.execution_id.is_empty(),
        "commission_report_id_present": !lifecycle_event.commission_report_id.is_empty(),
        "reconciliation_run_id_present": !lifecycle_event.reconciliation_run_id.is_empty(),
        "raw_artifact_hash_present": !lifecycle_event.raw_artifact_hash.is_empty(),
        "redacted_summary_hash_present": !lifecycle_event.redacted_summary_hash.is_empty(),
    });
    let reconstructability_summary = serde_json::json!({
        "append_only_event_ready": lifecycle_verdict.accepted,
        "event_hash_chain_ready": lifecycle_verdict.accepted,
        "request_envelope_linked": lifecycle_verdict.accepted,
        "stale_state_policy_present": lifecycle_event.stale_state_policy.is_some(),
        "broker_order_id_present": !lifecycle_event.broker_order_id.is_empty(),
        "execution_id_present": !lifecycle_event.execution_id.is_empty(),
        "commission_report_id_present": !lifecycle_event.commission_report_id.is_empty(),
        "raw_artifact_hash_present": !lifecycle_event.raw_artifact_hash.is_empty(),
        "redacted_summary_hash_present": !lifecycle_event.redacted_summary_hash.is_empty(),
        "restart_recovery_required": false,
        "manual_review_required": false,
    });

    serde_json::json!({
        "phase": "phase2_paper_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "environment": BrokerEnvironment::Paper,
        "paper_status_state": "blocked",
        "phase2_started": false,
        "paper_lifecycle_started": false,
        "paper_order_submitted": false,
        "paper_fill_imported": false,
        "paper_reconciliation_started": false,
        "paper_account_snapshot_present": false,
        "broker_paper_attestation_present": false,
        "lifecycle_event": lifecycle_event_summary,
        "reconstructability": reconstructability_summary,
        "phase2": phase2,
        "ibkr_live_enabled": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
        "db_apply_performed": false,
    })
}

pub(super) fn shadow_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let shadow_fill_model = StockShadowFillModelV1::default();
    let shadow_fill_verdict = shadow_fill_model.validate();
    let strategy_hypothesis = StockEtfStrategyHypothesisV1 {
        asset_lane: AssetLane::StockEtfCash,
        broker: Broker::Ibkr,
        no_options_cfd_margin_short: true,
        paper_shadow_only: true,
        bybit_live_execution_unchanged: true,
        ibkr_live_denied: true,
        ..StockEtfStrategyHypothesisV1::default()
    };
    let strategy_hypothesis_verdict = strategy_hypothesis.validate();

    serde_json::json!({
        "phase": "phase3_shadow_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "environment": BrokerEnvironment::Shadow,
        "shadow_status_state": "blocked",
        "phase3_started": false,
        "shadow_fill_model": {
            "expected_contract_id": STOCK_SHADOW_FILL_MODEL_CONTRACT_ID,
            "contract_id": shadow_fill_model.contract_id,
            "source_version": shadow_fill_model.source_version,
            "accepted": shadow_fill_verdict.accepted,
            "blockers": shadow_fill_verdict.blockers,
            "signal_id": shadow_fill_model.signal_id,
            "side": shadow_fill_model.side,
            "intended_notional_minor_units": shadow_fill_model.intended_notional_minor_units,
            "market_session_id": shadow_fill_model.market_session_id,
            "quote_or_bar_source_hash_present": !shadow_fill_model.quote_or_bar_source_hash.is_empty(),
            "conservative_fill_price_micros": shadow_fill_model.conservative_fill_price_micros,
            "spread_bps": shadow_fill_model.spread_bps,
            "slippage_bps": shadow_fill_model.slippage_bps,
            "cost_bps": shadow_fill_model.cost_bps,
            "rejection_reason": shadow_fill_model.rejection_reason,
            "synthetic_shadow": shadow_fill_model.synthetic_shadow,
            "broker_paper_fill_linked": shadow_fill_model.broker_paper_fill_linked,
            "live_fill_linked": shadow_fill_model.live_fill_linked,
        },
        "strategy_hypothesis": {
            "expected_contract_id": STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID,
            "contract_id": strategy_hypothesis.contract_id,
            "source_version": strategy_hypothesis.source_version,
            "accepted": strategy_hypothesis_verdict.accepted,
            "blockers": strategy_hypothesis_verdict.blockers,
            "hypothesis_id": strategy_hypothesis.hypothesis_id,
            "hypothesis_version": strategy_hypothesis.hypothesis_version,
            "strategy_family": strategy_hypothesis.strategy_family,
            "primary_timeframe": strategy_hypothesis.primary_timeframe,
            "instrument_scope": strategy_hypothesis.instrument_scope,
            "paper_shadow_only": strategy_hypothesis.paper_shadow_only,
            "profitability_claimed": strategy_hypothesis.profitability_claimed,
            "live_or_tiny_live_authority_claimed": strategy_hypothesis.live_or_tiny_live_authority_claimed,
            "bybit_live_execution_unchanged": strategy_hypothesis.bybit_live_execution_unchanged,
            "ibkr_live_denied": strategy_hypothesis.ibkr_live_denied,
            "ibkr_contact_performed": strategy_hypothesis.ibkr_contact_performed,
            "secret_content_serialized": strategy_hypothesis.secret_content_serialized,
        },
        "phase2": phase2,
        "shadow_collector_started": false,
        "shadow_signal_emitted": false,
        "shadow_fill_generated": false,
        "scorecard_writer_started": false,
        "db_apply_performed": false,
        "ibkr_live_enabled": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
    })
}

pub(super) fn universe_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let universe = StockEtfPitUniverseV1 {
        asset_lane: AssetLane::StockEtfCash,
        broker: Broker::Ibkr,
        bybit_live_execution_unchanged: true,
        ibkr_live_denied: true,
        ..StockEtfPitUniverseV1::default()
    };
    let universe_verdict = universe.validate();
    let constituents: Vec<serde_json::Value> = universe
        .constituents
        .iter()
        .take(10)
        .map(|constituent| {
            serde_json::json!({
                "symbol": constituent.symbol,
                "instrument_kind": constituent.instrument_kind,
                "listing_venue": constituent.listing_venue,
                "primary_exchange": constituent.primary_exchange,
                "currency": constituent.currency,
                "tradability_status": constituent.tradability_status,
                "priips_kid_status": constituent.priips_kid_status,
                "included": constituent.included,
            })
        })
        .collect();

    serde_json::json!({
        "phase": "phase3_universe_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "environment": BrokerEnvironment::Paper,
        "universe_status_state": "blocked",
        "phase3_started": false,
        "universe": {
            "expected_contract_id": STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID,
            "contract_id": universe.contract_id,
            "source_version": universe.source_version,
            "accepted": universe_verdict.accepted,
            "blockers": universe_verdict.blockers,
            "universe_id": universe.universe_id,
            "universe_version": universe.universe_version,
            "universe_hash_present": !universe.universe_hash.is_empty(),
            "point_in_time_asof_ms": universe.point_in_time_asof_ms,
            "effective_from_ms": universe.effective_from_ms,
            "effective_to_ms": universe.effective_to_ms,
            "constituent_count": universe.constituent_count,
            "max_constituents": universe.max_constituents,
            "sample_constituents": constituents,
            "frozen_for_evidence_clock": universe.frozen_for_evidence_clock,
            "survivorship_bias_controls_present": universe.survivorship_bias_controls_present,
            "bybit_live_execution_unchanged": universe.bybit_live_execution_unchanged,
            "ibkr_live_denied": universe.ibkr_live_denied,
            "ibkr_contact_performed": universe.ibkr_contact_performed,
            "secret_content_serialized": universe.secret_content_serialized,
        },
        "phase2": phase2,
        "collector_started": false,
        "market_data_ingestion_started": false,
        "db_apply_performed": false,
        "ibkr_live_enabled": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
    })
}

pub(super) fn evidence_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let market_data_provenance = StockMarketDataProvenanceV1::default();
    let market_data_verdict = market_data_provenance.validate();
    let collector_run = StockEtfCollectorRunV1::default();
    let collector_run_verdict = collector_run.validate();
    let evidence_clock_day = StockEtfEvidenceClockDayV1::default();
    let evidence_clock_verdict = evidence_clock_day.validate();
    let frozen_inputs_verdict = evidence_clock_day.frozen_inputs.validate();
    let dq_shape_verdict = evidence_clock_day.dq_manifest.validates_shape();

    serde_json::json!({
        "phase": "phase3_evidence_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "environment": BrokerEnvironment::Paper,
        "evidence_status_state": "blocked",
        "phase3_started": false,
        "market_data_provenance": {
            "expected_contract_id": STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID,
            "contract_id": market_data_provenance.contract_id,
            "source_version": market_data_provenance.source_version,
            "accepted": market_data_verdict.accepted,
            "blockers": market_data_verdict.blockers,
            "ibkr_contact_performed": market_data_provenance.ibkr_contact_performed,
            "connector_runtime_started": market_data_provenance.connector_runtime_started,
            "secret_content_serialized": market_data_provenance.secret_content_serialized,
            "live_or_tiny_live_authorized": market_data_provenance.live_or_tiny_live_authorized,
        },
        "collector_run": {
            "expected_contract_id": STOCK_ETF_COLLECTOR_RUN_CONTRACT_ID,
            "contract_id": collector_run.contract_id,
            "source_version": collector_run.source_version,
            "accepted": collector_run_verdict.accepted,
            "blockers": collector_run_verdict.blockers,
            "collector_run_id": collector_run.collector_run_id,
            "trading_day": collector_run.trading_day,
            "expected_trading_sessions": collector_run.expected_trading_sessions,
            "completed_trading_sessions": collector_run.completed_trading_sessions,
            "pit_universe_contract_hash_present": !collector_run.pit_universe_contract_hash.is_empty(),
            "market_data_provenance_contract_hash_present": !collector_run.market_data_provenance_contract_hash.is_empty(),
            "reference_data_sources_contract_hash_present": !collector_run.reference_data_sources_contract_hash.is_empty(),
            "storage_capacity_contract_hash_present": !collector_run.storage_capacity_contract_hash.is_empty(),
            "gap_report_hash_present": !collector_run.gap_report_hash.is_empty(),
            "dq_manifest_hash_present": !collector_run.dq_manifest_hash.is_empty(),
            "replay_manifest_hash_present": !collector_run.replay_manifest_hash.is_empty(),
            "source_artifact_hash_present": !collector_run.source_artifact_hash.is_empty(),
            "bybit_live_execution_unchanged": collector_run.bybit_live_execution_unchanged,
            "ibkr_contact_performed": collector_run.ibkr_contact_performed,
            "connector_runtime_started": collector_run.connector_runtime_started,
            "market_data_ingestion_started": collector_run.market_data_ingestion_started,
            "evidence_writer_started": collector_run.evidence_writer_started,
            "scorecard_writer_started": collector_run.scorecard_writer_started,
            "db_apply_performed": collector_run.db_apply_performed,
            "secret_content_serialized": collector_run.secret_content_serialized,
            "live_or_tiny_live_authorized": collector_run.live_or_tiny_live_authorized,
        },
        "evidence_clock": {
            "expected_contract_id": STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID,
            "contract_id": evidence_clock_day.contract_id,
            "source_version": evidence_clock_day.source_version,
            "status": evidence_clock_day.status,
            "accepted": evidence_clock_verdict.accepted,
            "blockers": evidence_clock_verdict.blockers,
            "checker_contacted_ibkr": evidence_clock_day.checker_contacted_ibkr,
            "checker_started_connector_runtime": evidence_clock_day.checker_started_connector_runtime,
            "checker_started_evidence_clock": evidence_clock_day.checker_started_evidence_clock,
            "checker_wrote_scorecard": evidence_clock_day.checker_wrote_scorecard,
            "checker_applied_db": evidence_clock_day.checker_applied_db,
            "secret_content_serialized": evidence_clock_day.secret_content_serialized,
            "live_or_tiny_live_authorized": evidence_clock_day.live_or_tiny_live_authorized,
            "ibkr_readonly_paper_connector_green_5d": evidence_clock_day.ibkr_readonly_paper_connector_green_5d,
            "shadow_collector_green_5d": evidence_clock_day.shadow_collector_green_5d,
        },
        "frozen_inputs": {
            "accepted": frozen_inputs_verdict.accepted,
            "blockers": frozen_inputs_verdict.blockers,
            "universe_hash_present": !evidence_clock_day.frozen_inputs.universe_hash.is_empty(),
            "benchmark_hash_present": !evidence_clock_day.frozen_inputs.benchmark_hash.is_empty(),
            "cost_model_hash_present": !evidence_clock_day.frozen_inputs.cost_model_hash.is_empty(),
            "strategy_hypothesis_hash_present": !evidence_clock_day.frozen_inputs.strategy_hypothesis_hash.is_empty(),
            "reference_data_sources_contract_hash_present": !evidence_clock_day.frozen_inputs.reference_data_sources_contract_hash.is_empty(),
            "paper_shadow_divergence_threshold_hash_present": !evidence_clock_day.frozen_inputs.paper_shadow_divergence_threshold_hash.is_empty(),
            "gui_evidence_view_available": evidence_clock_day.frozen_inputs.gui_evidence_view_available,
            "daily_scorecard_regeneration_passed": evidence_clock_day.frozen_inputs.daily_scorecard_regeneration_passed,
        },
        "dq_manifest": {
            "expected_contract_id": STOCK_ETF_DQ_MANIFEST_CONTRACT_ID,
            "contract_id": evidence_clock_day.dq_manifest.contract_id,
            "source_version": evidence_clock_day.dq_manifest.source_version,
            "shape_accepted": dq_shape_verdict.accepted,
            "shape_blockers": dq_shape_verdict.blockers,
            "passes_day_quality": evidence_clock_day.dq_manifest.passes_day_quality(),
            "collector_run_id": evidence_clock_day.dq_manifest.collector_run_id,
            "trading_day": evidence_clock_day.dq_manifest.trading_day,
            "market_data_provenance_contract_hash_present": !evidence_clock_day.dq_manifest.market_data_provenance_contract_hash.is_empty(),
            "source_artifact_hash_present": !evidence_clock_day.dq_manifest.source_artifact_hash.is_empty(),
            "bybit_live_execution_unchanged": evidence_clock_day.dq_manifest.bybit_live_execution_unchanged,
            "ibkr_contact_performed": evidence_clock_day.dq_manifest.ibkr_contact_performed,
            "connector_runtime_started": evidence_clock_day.dq_manifest.connector_runtime_started,
            "market_data_ingestion_started": evidence_clock_day.dq_manifest.market_data_ingestion_started,
            "dq_writer_started": evidence_clock_day.dq_manifest.dq_writer_started,
            "evidence_clock_started": evidence_clock_day.dq_manifest.evidence_clock_started,
            "scorecard_writer_started": evidence_clock_day.dq_manifest.scorecard_writer_started,
            "db_apply_performed": evidence_clock_day.dq_manifest.db_apply_performed,
            "secret_content_serialized": evidence_clock_day.dq_manifest.secret_content_serialized,
            "live_or_tiny_live_authorized": evidence_clock_day.dq_manifest.live_or_tiny_live_authorized,
            "calendar_aware_coverage_bps": evidence_clock_day.dq_manifest.calendar_aware_coverage_bps,
            "symbol_completeness_bps": evidence_clock_day.dq_manifest.symbol_completeness_bps,
            "latency_dq_passed": evidence_clock_day.dq_manifest.latency_dq_passed,
            "market_data_provenance_accepted": evidence_clock_day.dq_manifest.market_data_provenance_accepted,
            "scorecard_regeneration_passed": evidence_clock_day.dq_manifest.scorecard_regeneration_passed,
        },
        "scorecard": {
            "writer_started": evidence_clock_day.checker_wrote_scorecard,
            "db_apply_performed": evidence_clock_day.checker_applied_db,
            "daily_scorecard_regeneration_passed": evidence_clock_day.frozen_inputs.daily_scorecard_regeneration_passed,
        },
        "phase2": phase2,
        "ibkr_live_enabled": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
    })
}
