//! ADR-0048 Stock/ETF GUI lane contract acceptance tests.
//!
//! These tests validate source-only GUI boundary artifacts. They do not serve
//! pages, contact IBKR, read secrets, route orders, or authorize lane selection.

use std::path::PathBuf;

use openclaw_types::{
    AssetLane, StockEtfGuiLaneBlocker, StockEtfGuiLaneContractV1, STOCK_ETF_GUI_LANE_CONTRACT_ID,
    STOCK_ETF_GUI_READINESS_ENDPOINT,
};

#[test]
fn default_gui_lane_contract_blocks_gui_authority() {
    let verdict = StockEtfGuiLaneContractV1::default().validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::ContractIdMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::SourceVersionMismatch));
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::StockEtfTabMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::ReadinessEndpointMismatch));
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::DisplayOnlyMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::ClientLaneStateTrusted));
}

#[test]
fn accepted_fixture_is_display_only_get_only_and_crypto_default() {
    let contract = StockEtfGuiLaneContractV1::accepted_fixture();
    let verdict = contract.validate();

    assert!(verdict.accepted);
    assert!(verdict.blockers.is_empty());
    assert_eq!(contract.contract_id, STOCK_ETF_GUI_LANE_CONTRACT_ID);
    assert_eq!(contract.source_version, 1);
    assert_eq!(contract.default_asset_lane, AssetLane::CryptoPerp);
    assert_eq!(
        contract.readiness_endpoint,
        STOCK_ETF_GUI_READINESS_ENDPOINT
    );
    assert!(contract.readiness_endpoint_get_only);
    assert!(contract.display_only);
    assert!(!contract.ibkr_contact_performed);
}

#[test]
fn gui_lane_contract_requires_exact_contract_id_and_source_version() {
    let contract = StockEtfGuiLaneContractV1 {
        contract_id: "gui_lane_contract_v1_fixture".to_string(),
        source_version: 2,
        ..StockEtfGuiLaneContractV1::accepted_fixture()
    };
    let verdict = contract.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::ContractIdMismatch));
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::SourceVersionMismatch));
}

#[test]
fn client_lane_state_sources_cannot_authorize() {
    let mut contract = StockEtfGuiLaneContractV1::accepted_fixture();
    contract.client_lane_state_untrusted = false;
    contract.local_storage_authority_denied = false;
    contract.query_param_authority_denied = false;
    contract.hidden_field_authority_denied = false;

    let verdict = contract.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::ClientLaneStateTrusted));
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::LocalStorageAuthorityNotDenied));
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::QueryParamAuthorityNotDenied));
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::HiddenFieldAuthorityNotDenied));
}

#[test]
fn effect_capable_gui_surfaces_are_rejected() {
    let mut contract = StockEtfGuiLaneContractV1::accepted_fixture();
    contract.no_post_routes = false;
    contract.no_order_widgets = false;
    contract.no_secret_widgets = false;
    contract.no_ibkr_contact_on_render = false;
    contract.paper_order_entry_hidden = false;
    contract.ibkr_contact_performed = true;
    contract.secret_content_serialized = true;

    let verdict = contract.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::PostRoutePresent));
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::OrderWidgetPresent));
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::SecretWidgetPresent));
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::IbkrContactPerformed));
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::SecretContentSerialized));
}

#[test]
fn route_cache_auth_and_crypto_regression_evidence_are_required() {
    let mut contract = StockEtfGuiLaneContractV1::accepted_fixture();
    contract.route_cache_partition_required = false;
    contract.auth_partition_required = false;
    contract.stale_cache_cross_lane_denied = false;
    contract.crypto_tabs_regression_passed = false;
    contract.decision_lease_risk_regression_passed = false;
    contract.route_test_hash.clear();
    contract.crypto_regression_hash.clear();

    let verdict = contract.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::RouteCachePartitionMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::AuthPartitionMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::CryptoTabsRegressionMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::DecisionLeaseRiskRegressionMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::RouteTestHashInvalid));
}

#[test]
fn denied_effect_operations_are_required() {
    let mut contract = StockEtfGuiLaneContractV1::accepted_fixture();
    contract.denied_effect_operations = vec!["ibkr_tiny_live".to_string()];

    let verdict = contract.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::LiveOrderDenialMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::SecretSlotDenialMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfGuiLaneBlocker::PreGateContactDenialMissing));
}

#[test]
fn blocked_template_is_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/stock_etf_gui_lane_contract.template.toml"),
    )
    .expect("read GUI lane contract template");
    let parsed: StockEtfGuiLaneContractV1 =
        toml::from_str(&raw).expect("GUI lane contract template parses");

    assert_eq!(parsed.default_asset_lane, AssetLane::CryptoPerp);
    assert_eq!(parsed.source_version, 0);
    assert_eq!(parsed.readiness_endpoint, STOCK_ETF_GUI_READINESS_ENDPOINT);
    assert!(!parsed.ibkr_contact_performed);
    assert!(!parsed.secret_content_serialized);
    assert!(!parsed.validate().accepted);

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}
