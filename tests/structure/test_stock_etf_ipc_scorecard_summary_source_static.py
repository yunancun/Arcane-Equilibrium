from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCORECARD_SUMMARY = (
    ROOT
    / "rust/openclaw_engine/src/ipc_server/handlers/stock_etf/status_summaries/scorecard.rs"
)
MAX_LINES = 500

REQUIRED_SURFACE_TOKENS = {
    "pub(super) fn scorecard_status_summary(phase2: serde_json::Value) -> serde_json::Value",
    "StockEtfScorecardInputBundleV1::default()",
    "input_bundle.validate()",
    "StockEtfScorecardDerivationV1::default()",
    "derivation.validate()",
    "StockEtfScorecardVerdictV1::default()",
    "verdict.validate()",
    "serde_json::Map::new()",
    "macro_rules! put_scorecard",
    '"phase": "phase3_scorecard_status_source_fixture"',
    '"asset_lane": AssetLane::StockEtfCash',
    '"broker": Broker::Ibkr',
    '"environment": "paper_shadow"',
    '"scorecard_status_state": "blocked"',
    '"phase2": phase2',
}
REQUIRED_TOP_LEVEL_DENIALS = {
    '"phase3_started": false',
    '"scorecard_writer_started": false',
    '"db_apply_performed": false',
    '"evidence_clock_started": false',
    '"paper_shadow_window_complete": false',
    '"ibkr_live_enabled": false',
    '"ibkr_call_performed": false',
    '"secret_slot_touched": false',
    '"order_routed": false',
    '"bybit_ipc_reused": false',
    '"live_or_tiny_live_authorized": false',
}
REQUIRED_INPUT_BUNDLE_KEYS = {
    '"readonly_probe_result_import_request_contract_id"',
    '"readonly_probe_result_import_request_hash_present"',
    '"market_data_provenance_contract_hash_present"',
    '"reference_data_sources_contract_hash_present"',
    '"risk_policy_contract_hash_present"',
    '"atomic_fact_input_hash_present"',
    '"source_commit_present"',
    '"scorecard_is_derived_only"',
    '"paper_and_shadow_fills_separate"',
    '"live_fill_claimed"',
    '"bybit_live_execution_unchanged"',
    '"ibkr_contact_performed"',
    '"connector_runtime_started"',
    '"broker_fill_import_performed"',
    '"scorecard_writer_started"',
    '"db_apply_performed"',
    '"evidence_clock_started"',
    '"secret_content_serialized"',
    '"live_or_tiny_live_authorized"',
}
REQUIRED_DERIVATION_KEYS = {
    "STOCK_ETF_SCORECARD_DERIVATION_CONTRACT_ID",
    '"derivation_run_id_present"',
    '"strategy_id_present"',
    '"universe_version_present"',
    '"benchmark_version_present"',
    '"as_of_date_present"',
    '"scorecard_input_bundle_hash_present"',
    '"paper_shadow_reconciliation_hash_present"',
    '"scorecard_verdict_hash_present"',
    '"output_artifact_hash_present"',
    '"derived_from_atomic_facts_only"',
    '"idempotent_replay_proven"',
    '"paper_and_shadow_fills_separate"',
    '"bybit_live_execution_unchanged"',
    '"ibkr_contact_performed"',
    '"connector_runtime_started"',
    '"broker_fill_import_performed"',
    '"shadow_fill_generated"',
    '"reconciliation_writer_started"',
    '"scorecard_writer_started"',
    '"db_apply_performed"',
    '"evidence_clock_started"',
    '"secret_content_serialized"',
    '"live_or_tiny_live_authorized"',
    '"sealed"',
}
REQUIRED_SCORECARD_KEYS = {
    "STOCK_ETF_SCORECARD_VERDICT_CONTRACT_ID",
    '"verdict_label"',
    '"scorecard_input_bundle_hash_present"',
    '"evidence_clock_manifest_hash_present"',
    '"dq_manifest_hash_present"',
    '"formula_appendix_hash_present"',
    '"statistical_preregistration_hash_present"',
    '"benchmark_version_hash_present"',
    '"cost_model_version_hash_present"',
    '"strategy_hypothesis_hash_present"',
    '"reference_data_sources_hash_present"',
    '"paper_shadow_reconciliation_hash_present"',
    '"scorecard_manifest_hash_present"',
    '"verdict_rationale_hash_present"',
    '"paper_shadow_window_trading_days"',
    '"min_window_trading_days"',
    '"independent_observation_count"',
    '"min_independent_observation_count"',
    '"gross_pnl_minor_units"',
    '"net_pnl_minor_units"',
    '"commission_minor_units"',
    '"spread_slippage_minor_units"',
    '"fx_drag_minor_units"',
    '"tax_drag_minor_units"',
    '"benchmark_excess_lcb_bps"',
    '"conservative_cost_stress_lcb_bps"',
    '"paper_shadow_divergence_bps"',
    '"max_paper_shadow_divergence_bps"',
    '"psr_bps"',
    '"min_psr_bps"',
    '"dsr_bps"',
    '"min_dsr_bps"',
    '"concentration_label_passed"',
    '"regime_label_passed"',
    '"breadth_label_passed"',
    '"freshness_label_passed"',
    '"survivorship_label_passed"',
    '"execution_realism_label_passed"',
    '"qc_review_hash_present"',
    '"mit_review_hash_present"',
    '"qa_review_hash_present"',
    '"qc_review_passed"',
    '"mit_review_passed"',
    '"qa_review_passed"',
    '"scorecard_is_derived_only"',
    '"paper_and_shadow_fills_separate"',
    '"live_fill_claimed"',
    '"bybit_live_execution_unchanged"',
    '"sealed"',
}
FORBIDDEN_RUNTIME_TOKENS = (
    "std::env",
    "env::var",
    "var_os",
    "vars_os",
    "std::fs",
    "std::path::Path",
    "File::open",
    "OpenOptions",
    "read_to_string",
    "read_to_end",
    "include_str!",
    "include_bytes!",
    "std::net",
    "TcpStream",
    "UdpSocket",
    "tokio::net",
    "reqwest",
    "hyper::",
    "ureq",
    "ib_insync",
    "ibapi",
    "IBApi",
    "std::time",
    "SystemTime",
    "Instant",
    "chrono",
    "Utc::now",
    "Local::now",
    "std::thread",
    "thread::spawn",
    "tokio::spawn",
    "tokio::task",
    "tokio::time",
    "sleep(",
    "std::process",
    "process::Command",
    "Command::new",
    ".spawn(",
    "BybitRestClient",
    "BybitPrivateWs",
    "bybit_rest_client::",
    "bybit_private_ws::",
    "order_manager::",
    "OrderManager",
    "CreateOrderRequest",
    "OrderResponse",
    "handle_submit_paper_order",
    ".place_order(",
    ".cancel_order(",
    ".replace_order(",
    ".modify_order(",
    ".create_order(",
)
FORBIDDEN_SECRET_MATERIAL_TOKENS = (
    "api_key",
    "api_secret",
    "password",
    "token =",
    "OPENCLAW_",
    "SecretString",
    "SecretVec",
    "keyring",
)


def _source() -> str:
    return SCORECARD_SUMMARY.read_text(encoding="utf-8")


def test_stock_etf_ipc_scorecard_summary_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_ipc_scorecard_summary_source_keeps_display_only_surface() -> None:
    source = _source()

    for token in REQUIRED_SURFACE_TOKENS:
        assert token in source
    for token in REQUIRED_TOP_LEVEL_DENIALS:
        assert token in source

    assert '"scorecard_input_bundle": scorecard_input_bundle' in source
    assert '"scorecard_derivation": derivation' in source
    assert '"scorecard": scorecard' in source


def test_stock_etf_ipc_scorecard_summary_source_keeps_input_bundle_lineage() -> None:
    source = _source()

    for token in REQUIRED_INPUT_BUNDLE_KEYS:
        assert token in source

    assert "&input_bundle.readonly_probe_result_import_request_contract_id" in source
    assert "!input_bundle.readonly_probe_result_import_request_hash.is_empty()" in source
    assert "!input_bundle.market_data_provenance_contract_hash.is_empty()" in source
    assert "!input_bundle.reference_data_sources_contract_hash.is_empty()" in source
    assert "!input_bundle.risk_policy_contract_hash.is_empty()" in source
    assert "!input_bundle.atomic_fact_input_hash.is_empty()" in source


def test_stock_etf_ipc_scorecard_summary_source_keeps_derivation_and_verdict_lineage() -> None:
    source = _source()

    for token in REQUIRED_DERIVATION_KEYS:
        assert token in source
    for token in REQUIRED_SCORECARD_KEYS:
        assert token in source

    assert "let scorecard = serde_json::Value::Object(scorecard);" in source
    assert "!derivation.output_artifact_hash.is_empty()" in source
    assert "!verdict.verdict_rationale_hash.is_empty()" in source
    assert "verdict.execution_realism_label_passed" in source


def test_stock_etf_ipc_scorecard_summary_source_has_no_runtime_secret_order_or_bybit_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{SCORECARD_SUMMARY}: contains forbidden token {token!r}")

    assert violations == []
