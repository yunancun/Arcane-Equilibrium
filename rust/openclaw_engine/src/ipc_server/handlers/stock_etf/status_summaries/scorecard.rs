use super::*;

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
