//! ADR-0048 Stock/ETF lane-scoped IPC acceptance tests.
//!
//! These tests validate the source-only Rust IPC contract matrix. They do not
//! start IPC, contact IBKR, inspect secrets, create connectors, submit paper
//! orders, or mutate existing Bybit behavior.

use std::path::PathBuf;

use openclaw_types::{
    AssetLane, AuthorityScope, Broker, BrokerOperation, StockEtfDenialReason,
    StockEtfLaneScopedIpcBlocker, StockEtfLaneScopedIpcContractV1, StockEtfLaneScopedIpcMethod,
    STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID, STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID,
    STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID, STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID,
    STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID, STOCK_ETF_RISK_POLICY_CONTRACT_ID,
    STOCK_ETF_SCOPED_AUTHORIZATION_CONTRACT_ID,
};

#[test]
fn default_lane_scoped_ipc_contract_blocks_all_authority() {
    let verdict = StockEtfLaneScopedIpcContractV1::default().validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict.blockers,
        StockEtfLaneScopedIpcBlocker::ContractIdMismatch
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfLaneScopedIpcBlocker::SourceVersionMismatch
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfLaneScopedIpcBlocker::WrongAssetLane
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfLaneScopedIpcBlocker::WrongBroker
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfLaneScopedIpcBlocker::RustAuthorityOwnerMissing
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfLaneScopedIpcBlocker::CommandMissing
    ));
}

#[test]
fn accepted_fixture_pins_stock_etf_method_matrix_without_runtime_authority() {
    let contract = StockEtfLaneScopedIpcContractV1::accepted_fixture();
    let verdict = contract.validate();

    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(contract.contract_id, STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID);
    assert_eq!(contract.source_version, 1);
    assert_eq!(contract.asset_lane, AssetLane::StockEtfCash);
    assert_eq!(contract.broker, Broker::Ibkr);
    assert!(contract.rust_authority_owner);
    assert!(contract.python_forward_only);
    assert!(contract.python_direct_broker_write_denied);
    assert!(contract.bybit_ipc_reuse_denied);
    assert!(contract.existing_bybit_paper_path_denied);
    assert!(contract.live_environment_denied);
    assert!(contract.bybit_live_execution_unchanged);
    assert!(!contract.ibkr_contact_performed);
    assert!(!contract.connector_runtime_started);
    assert!(!contract.secret_content_serialized);
    assert_eq!(contract.commands.len(), 8);

    let submit = contract
        .commands
        .iter()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::SubmitPaperOrder)
        .expect("submit method exists");
    assert_eq!(submit.operation, BrokerOperation::PaperOrderSubmit);
    assert_eq!(submit.authority_scope, AuthorityScope::PaperRehearsal);
    assert!(submit.effect_capable);
    assert!(submit.rust_owned);
    assert!(submit
        .required_gates
        .contains(&STOCK_ETF_SCOPED_AUTHORIZATION_CONTRACT_ID.to_string()));
    assert!(submit
        .required_gates
        .contains(&STOCK_ETF_RISK_POLICY_CONTRACT_ID.to_string()));
    assert!(submit
        .required_gates
        .contains(&STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID.to_string()));
    assert!(submit
        .required_request_fields
        .contains(&"decision_lease_id".to_string()));

    let preview = contract
        .commands
        .iter()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::PreviewPaperOrder)
        .expect("preview method exists");
    assert!(preview
        .required_gates
        .contains(&STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID.to_string()));
    assert!(preview
        .required_gates
        .contains(&STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID.to_string()));
    assert!(preview
        .required_gates
        .contains(&STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID.to_string()));

    let shadow = contract
        .commands
        .iter()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::EvaluateShadowSignal)
        .expect("shadow method exists");
    assert!(shadow
        .required_gates
        .contains(&STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID.to_string()));
    assert!(shadow
        .required_gates
        .contains(&STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID.to_string()));
    assert!(shadow
        .required_gates
        .contains(&STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID.to_string()));
}

#[test]
fn lane_scoped_ipc_requires_exact_contract_id_and_source_version() {
    let contract = StockEtfLaneScopedIpcContractV1 {
        contract_id: "lane_scoped_ipc_v1_fixture".to_string(),
        source_version: 2,
        ..StockEtfLaneScopedIpcContractV1::accepted_fixture()
    };
    let blockers = contract.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::ContractIdMismatch
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::SourceVersionMismatch
    ));
}

#[test]
fn lane_scoped_ipc_rejects_top_level_boundary_regressions() {
    let contract = StockEtfLaneScopedIpcContractV1 {
        contract_id: "wrong".to_string(),
        asset_lane: AssetLane::CryptoPerp,
        broker: Broker::Bybit,
        rust_authority_owner: false,
        python_forward_only: false,
        python_direct_broker_write_denied: false,
        bybit_ipc_reuse_denied: false,
        existing_bybit_paper_path_denied: false,
        live_environment_denied: false,
        bybit_live_execution_unchanged: false,
        ibkr_contact_performed: true,
        connector_runtime_started: true,
        secret_content_serialized: true,
        ..StockEtfLaneScopedIpcContractV1::accepted_fixture()
    };
    let blockers = contract.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::ContractIdMismatch
    ));
    assert!(has(&blockers, StockEtfLaneScopedIpcBlocker::WrongAssetLane));
    assert!(has(&blockers, StockEtfLaneScopedIpcBlocker::WrongBroker));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::PythonDirectBrokerWriteNotDenied
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::BybitIpcReuseNotDenied
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::ExistingBybitPaperPathNotDenied
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::LiveEnvironmentNotDenied
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::IbkrContactPerformed
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::ConnectorRuntimeStarted
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::SecretContentSerialized
    ));
}

#[test]
fn lane_scoped_ipc_requires_exact_command_coverage_once() {
    let mut contract = StockEtfLaneScopedIpcContractV1::accepted_fixture();
    let duplicate = contract.commands[0].clone();
    contract
        .commands
        .retain(|command| command.method != StockEtfLaneScopedIpcMethod::ImportPaperFills);
    contract.commands.push(duplicate);

    let blockers = contract.validate().blockers;

    assert!(has(&blockers, StockEtfLaneScopedIpcBlocker::CommandMissing));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::CommandDuplicated
    ));
}

#[test]
fn paper_effect_methods_require_gates_fields_denials_and_rust_ownership() {
    let mut contract = StockEtfLaneScopedIpcContractV1::accepted_fixture();
    let submit = contract
        .commands
        .iter_mut()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::SubmitPaperOrder)
        .expect("submit method");
    submit.operation = BrokerOperation::LiveOrderSubmit;
    submit.authority_scope = AuthorityScope::ReadOnly;
    submit.effect_capable = false;
    submit.rust_owned = false;
    submit.required_gates.clear();
    submit.required_request_fields.clear();
    submit
        .typed_denial_reasons
        .retain(|reason| *reason != StockEtfDenialReason::DecisionLeaseInvalid);

    let blockers = contract.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::CommandOperationMismatch
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::CommandAuthorityScopeMismatch
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::CommandEffectCapabilityMismatch
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::CommandRustOwnershipMismatch
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::CommandRequiredGateMissing
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::CommandRequestFieldMissing
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::CommandDenialReasonMissing
    ));
}

#[test]
fn denied_or_unknown_ipc_methods_cannot_clear_contract() {
    let mut contract = StockEtfLaneScopedIpcContractV1::accepted_fixture();
    let submit = contract
        .commands
        .iter_mut()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::SubmitPaperOrder)
        .expect("submit method");
    submit.method = StockEtfLaneScopedIpcMethod::BybitSubmitPaperOrderDenied;

    let blockers = contract.validate().blockers;

    assert!(has(&blockers, StockEtfLaneScopedIpcBlocker::CommandMissing));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::CommandMethodDenied
    ));
}

#[test]
fn blocked_template_is_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/stock_etf_lane_scoped_ipc.template.toml"),
    )
    .expect("read lane-scoped IPC template");
    let parsed: StockEtfLaneScopedIpcContractV1 =
        toml::from_str(&raw).expect("lane-scoped IPC template parses");

    assert_eq!(parsed.contract_id, "");
    assert_eq!(parsed.source_version, 0);
    assert_eq!(parsed.asset_lane, AssetLane::CryptoPerp);
    assert_eq!(parsed.broker, Broker::Bybit);
    assert!(!parsed.validate().accepted);
    assert!(!parsed.rust_authority_owner);
    assert!(!parsed.bybit_ipc_reuse_denied);
    assert!(!parsed.ibkr_contact_performed);
    assert!(!parsed.secret_content_serialized);

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}

fn has(blockers: &[StockEtfLaneScopedIpcBlocker], blocker: StockEtfLaneScopedIpcBlocker) -> bool {
    blockers.contains(&blocker)
}
