//! ADR-0048 Stock/ETF cash lane acceptance tests.
//!
//! These tests pin Phase 1 source-foundation contracts only. They must not
//! create an IBKR connector, secret slot, broker session, or runtime order path.

use std::cell::RefCell;
use std::collections::HashMap;
use std::path::PathBuf;

use openclaw_types::{
    evaluate_broker_operation, AssetLane, AuthorityScope, Broker, BrokerCapabilityRequest,
    BrokerEnvironment, BrokerOperation, IbkrPaperOrderLifecycleState, InstrumentKind,
    StockEtfDenialReason, StockEtfFeatureFlags, StockEtfGateInputs,
};

#[test]
fn taxonomy_serializes_as_closed_snake_case_contract() {
    assert_eq!(
        serde_json::to_string(&AssetLane::StockEtfCash).unwrap(),
        r#""stock_etf_cash""#
    );
    assert_eq!(AssetLane::default(), AssetLane::CryptoPerp);
    assert_eq!(AssetLane::StockEtfCash.to_string(), "stock_etf_cash");
    assert_eq!(Broker::Ibkr.to_string(), "ibkr");
    assert_eq!(BrokerEnvironment::ReadOnly.to_string(), "readonly");
    assert_eq!(InstrumentKind::CfdReserved.to_string(), "cfd_reserved");
}

#[test]
fn default_flags_keep_stock_etf_and_ibkr_off() {
    let flags = StockEtfFeatureFlags::default();
    assert!(!flags.stock_etf_lane_enabled);
    assert!(!flags.ibkr_readonly_enabled);
    assert!(!flags.ibkr_paper_enabled);
    assert_eq!(flags.asset_lane_default, AssetLane::CryptoPerp);
    assert!(flags.stock_etf_shadow_only);

    let readiness = flags.readiness();
    assert!(!readiness.readonly_ready);
    assert!(!readiness.paper_ready);
    assert!(readiness.live_denied);
    assert_eq!(
        readiness.denial_reasons,
        vec![
            StockEtfDenialReason::LaneDisabled,
            StockEtfDenialReason::BrokerDisabled,
            StockEtfDenialReason::ShadowOnly,
        ]
    );
}

#[test]
fn readiness_denial_reason_assertions_stay_exact() {
    let source = include_str!("stock_etf_lane_acceptance.rs");
    let prefix = source
        .split("fn readiness_denial_reason_assertions_stay_exact")
        .next()
        .expect("source guard anchor exists");

    assert!(
        !prefix.contains(".denial_reasons.contains("),
        "loose readiness denial reason assertion returned before source guard"
    );
}

#[test]
fn feature_flags_parse_from_lookup_without_env_side_effects() {
    let values = HashMap::from([
        ("OPENCLAW_STOCK_ETF_LANE_ENABLED", "1"),
        ("OPENCLAW_IBKR_READONLY_ENABLED", "true"),
        ("OPENCLAW_IBKR_PAPER_ENABLED", "0"),
        ("OPENCLAW_ASSET_LANE_DEFAULT", "crypto_perp"),
        ("OPENCLAW_STOCK_ETF_SHADOW_ONLY", "1"),
    ]);
    let flags =
        StockEtfFeatureFlags::from_lookup(|key| values.get(key).map(|value| (*value).to_string()))
            .expect("valid flags");

    assert!(flags.stock_etf_lane_enabled);
    assert!(flags.ibkr_readonly_enabled);
    assert!(!flags.ibkr_paper_enabled);
    assert_eq!(flags.asset_lane_default, AssetLane::CryptoPerp);
    assert!(flags.stock_etf_shadow_only);
}

#[test]
fn feature_flag_lookup_uses_exact_non_secret_env_allowlist() {
    let seen = RefCell::new(Vec::new());
    let flags = StockEtfFeatureFlags::from_lookup(|key| {
        seen.borrow_mut().push(key.to_string());
        None
    })
    .expect("absent feature flags fall back to defaults");

    let expected = vec![
        "OPENCLAW_STOCK_ETF_LANE_ENABLED".to_string(),
        "OPENCLAW_IBKR_READONLY_ENABLED".to_string(),
        "OPENCLAW_IBKR_PAPER_ENABLED".to_string(),
        "OPENCLAW_ASSET_LANE_DEFAULT".to_string(),
        "OPENCLAW_STOCK_ETF_SHADOW_ONLY".to_string(),
    ];

    assert_eq!(seen.into_inner(), expected);
    assert_eq!(flags, StockEtfFeatureFlags::default());

    for key in expected {
        let lower = key.to_ascii_lowercase();
        assert!(!lower.contains("secret"));
        assert!(!lower.contains("token"));
        assert!(!lower.contains("password"));
        assert!(!lower.contains("account"));
        assert!(!lower.contains("key"));
    }
}

#[test]
fn ibkr_live_and_cfd_paths_are_typed_denials() {
    let flags = StockEtfFeatureFlags {
        stock_etf_lane_enabled: true,
        ibkr_readonly_enabled: true,
        ibkr_paper_enabled: true,
        stock_etf_shadow_only: false,
        ..StockEtfFeatureFlags::default()
    };
    let gates = StockEtfGateInputs {
        external_surface_gate_passed: true,
        session_attested: true,
        scoped_authorization_present: true,
        decision_lease_valid: true,
        guardian_allows: true,
        risk_config_hash_present: true,
        instrument_identity_hash_present: true,
        idempotency_key_present: true,
        cost_model_present: true,
        universe_match: true,
        credential_available: true,
        connector_available: true,
        ..StockEtfGateInputs::default()
    };

    let live = BrokerCapabilityRequest {
        operation: BrokerOperation::LiveOrderSubmit,
        ..BrokerCapabilityRequest::stock_etf_ibkr_paper(
            InstrumentKind::Stock,
            BrokerOperation::PaperOrderSubmit,
        )
    };
    assert_eq!(
        evaluate_broker_operation(live, &flags, &gates).denial_reason,
        Some(StockEtfDenialReason::IbkrLiveNotAuthorized)
    );

    let cfd = BrokerCapabilityRequest::stock_etf_ibkr_paper(
        InstrumentKind::CfdReserved,
        BrokerOperation::PaperOrderSubmit,
    );
    assert_eq!(
        evaluate_broker_operation(cfd, &flags, &gates).denial_reason,
        Some(StockEtfDenialReason::InstrumentKindDenied)
    );
}

#[test]
fn broker_capability_rejects_each_lane_broker_and_operation_gap_independently() {
    let flags = all_enabled_flags();
    let gates = all_green_gates();

    assert_single_blocker(
        BrokerCapabilityRequest {
            asset_lane: AssetLane::CryptoPerp,
            ..paper_submit_request(InstrumentKind::Stock)
        },
        &flags,
        &gates,
        StockEtfDenialReason::WrongAssetLane,
    );
    assert_single_blocker(
        BrokerCapabilityRequest {
            broker: Broker::Bybit,
            ..paper_submit_request(InstrumentKind::Stock)
        },
        &flags,
        &gates,
        StockEtfDenialReason::WrongBroker,
    );
    assert_single_blocker(
        BrokerCapabilityRequest {
            environment: BrokerEnvironment::LiveReservedDenied,
            ..paper_submit_request(InstrumentKind::Stock)
        },
        &flags,
        &gates,
        StockEtfDenialReason::LiveReservedDenied,
    );
    assert_single_blocker(
        BrokerCapabilityRequest {
            operation: BrokerOperation::LiveOrderSubmit,
            ..paper_submit_request(InstrumentKind::Stock)
        },
        &flags,
        &gates,
        StockEtfDenialReason::IbkrLiveNotAuthorized,
    );
    assert_single_blocker(
        BrokerCapabilityRequest {
            operation: BrokerOperation::MarginOrShort,
            ..paper_submit_request(InstrumentKind::Stock)
        },
        &flags,
        &gates,
        StockEtfDenialReason::StockEtfCashOnly,
    );
    assert_single_blocker(
        BrokerCapabilityRequest {
            operation: BrokerOperation::OptionsOrCfd,
            ..paper_submit_request(InstrumentKind::Stock)
        },
        &flags,
        &gates,
        StockEtfDenialReason::InstrumentKindDenied,
    );
    assert_single_blocker(
        BrokerCapabilityRequest {
            operation: BrokerOperation::TransferOrAccountWrite,
            ..paper_submit_request(InstrumentKind::Stock)
        },
        &flags,
        &gates,
        StockEtfDenialReason::AccountWriteDenied,
    );
    assert_single_blocker(
        paper_submit_request(InstrumentKind::CryptoPerp),
        &flags,
        &gates,
        StockEtfDenialReason::InstrumentKindDenied,
    );
}

#[test]
fn broker_capability_rejects_each_flag_gap_independently() {
    let gates = all_green_gates();

    assert_single_blocker(
        paper_submit_request(InstrumentKind::Stock),
        &StockEtfFeatureFlags::default(),
        &gates,
        StockEtfDenialReason::LaneDisabled,
    );
    assert_single_blocker(
        BrokerCapabilityRequest::stock_etf_ibkr_paper(
            InstrumentKind::Stock,
            BrokerOperation::HealthRead,
        ),
        &StockEtfFeatureFlags {
            stock_etf_lane_enabled: true,
            ibkr_readonly_enabled: false,
            ibkr_paper_enabled: true,
            stock_etf_shadow_only: false,
            ..StockEtfFeatureFlags::default()
        },
        &gates,
        StockEtfDenialReason::BrokerDisabled,
    );
    assert_single_blocker(
        paper_submit_request(InstrumentKind::Stock),
        &StockEtfFeatureFlags {
            stock_etf_lane_enabled: true,
            ibkr_readonly_enabled: true,
            ibkr_paper_enabled: false,
            stock_etf_shadow_only: false,
            ..StockEtfFeatureFlags::default()
        },
        &gates,
        StockEtfDenialReason::BrokerDisabled,
    );
    assert_single_blocker(
        paper_submit_request(InstrumentKind::Stock),
        &StockEtfFeatureFlags {
            stock_etf_lane_enabled: true,
            ibkr_readonly_enabled: true,
            ibkr_paper_enabled: true,
            stock_etf_shadow_only: true,
            ..StockEtfFeatureFlags::default()
        },
        &gates,
        StockEtfDenialReason::ShadowOnly,
    );
}

#[test]
fn broker_capability_rejects_each_gate_gap_independently() {
    let flags = all_enabled_flags();

    assert_single_blocker(
        BrokerCapabilityRequest::stock_etf_ibkr_paper(
            InstrumentKind::Stock,
            BrokerOperation::HealthRead,
        ),
        &flags,
        &StockEtfGateInputs {
            external_surface_gate_passed: false,
            ..all_green_gates()
        },
        StockEtfDenialReason::AuthorizationInvalid,
    );
    assert_single_blocker(
        BrokerCapabilityRequest::stock_etf_ibkr_paper(
            InstrumentKind::Stock,
            BrokerOperation::ShadowSignalEmit,
        ),
        &flags,
        &StockEtfGateInputs {
            cost_model_present: false,
            ..all_green_gates()
        },
        StockEtfDenialReason::CostModelMissing,
    );
    assert_single_blocker(
        BrokerCapabilityRequest::stock_etf_ibkr_paper(
            InstrumentKind::Stock,
            BrokerOperation::ShadowSignalEmit,
        ),
        &flags,
        &StockEtfGateInputs {
            universe_match: false,
            ..all_green_gates()
        },
        StockEtfDenialReason::UniverseMismatch,
    );
    assert_single_blocker(
        paper_submit_request(InstrumentKind::Stock),
        &flags,
        &StockEtfGateInputs {
            market_open: false,
            ..all_green_gates()
        },
        StockEtfDenialReason::MarketClosed,
    );
    assert_single_blocker(
        paper_submit_request(InstrumentKind::Stock),
        &flags,
        &StockEtfGateInputs {
            credential_available: false,
            ..all_green_gates()
        },
        StockEtfDenialReason::CredentialUnavailable,
    );
    assert_single_blocker(
        paper_submit_request(InstrumentKind::Stock),
        &flags,
        &StockEtfGateInputs {
            connector_available: false,
            ..all_green_gates()
        },
        StockEtfDenialReason::ConnectorUnavailable,
    );
    assert_single_blocker(
        paper_submit_request(InstrumentKind::Stock),
        &flags,
        &StockEtfGateInputs {
            session_attested: false,
            ..all_green_gates()
        },
        StockEtfDenialReason::AuthorizationInvalid,
    );
    assert_single_blocker(
        paper_submit_request(InstrumentKind::Stock),
        &flags,
        &StockEtfGateInputs {
            scoped_authorization_present: false,
            ..all_green_gates()
        },
        StockEtfDenialReason::AuthorizationInvalid,
    );
    assert_single_blocker(
        paper_submit_request(InstrumentKind::Stock),
        &flags,
        &StockEtfGateInputs {
            risk_config_hash_present: false,
            ..all_green_gates()
        },
        StockEtfDenialReason::AuthorizationInvalid,
    );
    assert_single_blocker(
        paper_submit_request(InstrumentKind::Stock),
        &flags,
        &StockEtfGateInputs {
            instrument_identity_hash_present: false,
            ..all_green_gates()
        },
        StockEtfDenialReason::AuthorizationInvalid,
    );
    assert_single_blocker(
        paper_submit_request(InstrumentKind::Stock),
        &flags,
        &StockEtfGateInputs {
            idempotency_key_present: false,
            ..all_green_gates()
        },
        StockEtfDenialReason::AuthorizationInvalid,
    );
    assert_single_blocker(
        paper_submit_request(InstrumentKind::Stock),
        &flags,
        &StockEtfGateInputs {
            decision_lease_valid: false,
            ..all_green_gates()
        },
        StockEtfDenialReason::DecisionLeaseInvalid,
    );
    assert_single_blocker(
        paper_submit_request(InstrumentKind::Stock),
        &flags,
        &StockEtfGateInputs {
            guardian_allows: false,
            ..all_green_gates()
        },
        StockEtfDenialReason::GuardianDenied,
    );
}

#[test]
fn broker_capability_allows_only_read_shadow_or_paper_when_all_gates_pass() {
    let flags = all_enabled_flags();
    let gates = all_green_gates();

    for operation in [
        BrokerOperation::HealthRead,
        BrokerOperation::PaperOrderFillImport,
        BrokerOperation::ScorecardDerive,
    ] {
        let decision = evaluate_broker_operation(
            BrokerCapabilityRequest::stock_etf_ibkr_paper(InstrumentKind::Stock, operation),
            &flags,
            &gates,
        );
        assert!(decision.allowed);
        assert_eq!(decision.authority_scope, AuthorityScope::ReadOnly);
        assert_eq!(decision.denial_reason, None);
    }

    let shadow = evaluate_broker_operation(
        BrokerCapabilityRequest::stock_etf_ibkr_paper(
            InstrumentKind::Stock,
            BrokerOperation::ShadowSignalEmit,
        ),
        &flags,
        &gates,
    );
    assert!(shadow.allowed);
    assert_eq!(shadow.authority_scope, AuthorityScope::ShadowOnly);
    assert_eq!(shadow.denial_reason, None);

    let paper =
        evaluate_broker_operation(paper_submit_request(InstrumentKind::Etf), &flags, &gates);
    assert!(paper.allowed);
    assert_eq!(paper.authority_scope, AuthorityScope::PaperRehearsal);
    assert_eq!(paper.denial_reason, None);
}

#[test]
fn paper_order_denies_before_any_connector_when_default_off() {
    let decision = evaluate_broker_operation(
        BrokerCapabilityRequest::stock_etf_ibkr_paper(
            InstrumentKind::Stock,
            BrokerOperation::PaperOrderSubmit,
        ),
        &StockEtfFeatureFlags::default(),
        &StockEtfGateInputs::default(),
    );
    assert!(!decision.allowed);
    assert_eq!(
        decision.denial_reason,
        Some(StockEtfDenialReason::LaneDisabled)
    );
}

#[test]
fn paper_order_requires_all_phase2_style_gates_even_when_flags_on() {
    let flags = StockEtfFeatureFlags {
        stock_etf_lane_enabled: true,
        ibkr_readonly_enabled: true,
        ibkr_paper_enabled: true,
        stock_etf_shadow_only: false,
        ..StockEtfFeatureFlags::default()
    };
    let request = BrokerCapabilityRequest::stock_etf_ibkr_paper(
        InstrumentKind::Etf,
        BrokerOperation::PaperOrderSubmit,
    );
    let decision = evaluate_broker_operation(request, &flags, &StockEtfGateInputs::default());
    assert!(!decision.allowed);
    assert_eq!(
        decision.denial_reason,
        Some(StockEtfDenialReason::CredentialUnavailable)
    );
}

#[test]
fn broker_operation_authority_taxonomy_keeps_fill_import_readonly_and_orders_separate() {
    for operation in [
        BrokerOperation::HealthRead,
        BrokerOperation::AccountSnapshotRead,
        BrokerOperation::MarketDataRead,
        BrokerOperation::ContractDetailsRead,
        BrokerOperation::PaperOrderFillImport,
        BrokerOperation::ScorecardDerive,
    ] {
        assert!(operation.is_read(), "{operation:?} must stay read-only");
        assert!(
            !operation.is_paper_write(),
            "{operation:?} must not be a paper write"
        );
        assert!(!operation.is_shadow(), "{operation:?} must not be shadow");
        assert_eq!(operation.authority_scope(), AuthorityScope::ReadOnly);
    }

    for operation in [
        BrokerOperation::PaperOrderSubmit,
        BrokerOperation::PaperOrderCancel,
        BrokerOperation::PaperOrderReplace,
    ] {
        assert!(!operation.is_read(), "{operation:?} must not be read-only");
        assert!(
            operation.is_paper_write(),
            "{operation:?} must stay a paper write"
        );
        assert!(!operation.is_shadow(), "{operation:?} must not be shadow");
        assert_eq!(operation.authority_scope(), AuthorityScope::PaperRehearsal);
    }

    for operation in [
        BrokerOperation::ShadowSignalEmit,
        BrokerOperation::ShadowFillReconstruct,
    ] {
        assert!(!operation.is_read(), "{operation:?} must not be read-only");
        assert!(
            !operation.is_paper_write(),
            "{operation:?} must not be a paper write"
        );
        assert!(operation.is_shadow(), "{operation:?} must stay shadow");
        assert_eq!(operation.authority_scope(), AuthorityScope::ShadowOnly);
    }

    for operation in [
        BrokerOperation::LiveOrderSubmit,
        BrokerOperation::MarginOrShort,
        BrokerOperation::OptionsOrCfd,
        BrokerOperation::TransferOrAccountWrite,
    ] {
        assert!(!operation.is_read(), "{operation:?} must not be read-only");
        assert!(
            !operation.is_paper_write(),
            "{operation:?} must not be a paper write"
        );
        assert!(!operation.is_shadow(), "{operation:?} must not be shadow");
        assert_eq!(operation.authority_scope(), AuthorityScope::Denied);
    }
}

fn assert_single_blocker(
    request: BrokerCapabilityRequest,
    flags: &StockEtfFeatureFlags,
    gates: &StockEtfGateInputs,
    expected: StockEtfDenialReason,
) {
    let decision = evaluate_broker_operation(request, flags, gates);

    assert!(!decision.allowed);
    assert_eq!(decision.authority_scope, AuthorityScope::Denied);
    assert_eq!(decision.denial_reason, Some(expected));
}

fn paper_submit_request(instrument_kind: InstrumentKind) -> BrokerCapabilityRequest {
    BrokerCapabilityRequest::stock_etf_ibkr_paper(
        instrument_kind,
        BrokerOperation::PaperOrderSubmit,
    )
}

fn all_enabled_flags() -> StockEtfFeatureFlags {
    StockEtfFeatureFlags {
        stock_etf_lane_enabled: true,
        ibkr_readonly_enabled: true,
        ibkr_paper_enabled: true,
        stock_etf_shadow_only: false,
        ..StockEtfFeatureFlags::default()
    }
}

fn all_green_gates() -> StockEtfGateInputs {
    StockEtfGateInputs {
        external_surface_gate_passed: true,
        session_attested: true,
        scoped_authorization_present: true,
        decision_lease_valid: true,
        guardian_allows: true,
        risk_config_hash_present: true,
        instrument_identity_hash_present: true,
        idempotency_key_present: true,
        market_open: true,
        cost_model_present: true,
        universe_match: true,
        credential_available: true,
        connector_available: true,
    }
}

#[test]
fn lifecycle_terminal_states_are_explicit() {
    assert!(!IbkrPaperOrderLifecycleState::LocalIntentCreated.is_terminal());
    assert!(!IbkrPaperOrderLifecycleState::StateUnknown.is_terminal());
    assert!(IbkrPaperOrderLifecycleState::Filled.is_terminal());
    assert!(IbkrPaperOrderLifecycleState::Cancelled.is_terminal());
    assert!(IbkrPaperOrderLifecycleState::Rejected.is_terminal());
    assert!(IbkrPaperOrderLifecycleState::Inactive.is_terminal());
    assert!(IbkrPaperOrderLifecycleState::ManualReviewRequired.is_terminal());
}

#[test]
fn source_controlled_configs_are_default_off_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let lane_raw =
        std::fs::read_to_string(srv_root.join("settings/asset_lanes/stock_etf_cash.toml"))
            .expect("read stock_etf lane config");
    let broker_raw = std::fs::read_to_string(srv_root.join("settings/broker/ibkr_paper.toml"))
        .expect("read ibkr broker config");
    let risk_raw = std::fs::read_to_string(
        srv_root.join("settings/risk_control_rules/risk_config_stock_etf_paper.toml"),
    )
    .expect("read stock_etf risk config");

    let lane: toml::Value = toml::from_str(&lane_raw).expect("lane toml parses");
    let broker: toml::Value = toml::from_str(&broker_raw).expect("broker toml parses");
    let risk: toml::Value = toml::from_str(&risk_raw).expect("risk toml parses");

    assert_eq!(lane["lane"]["enabled"].as_bool(), Some(false));
    assert_eq!(lane["lane"]["live_enabled"].as_bool(), Some(false));
    assert_eq!(
        lane["flags"]["OPENCLAW_ASSET_LANE_DEFAULT"].as_str(),
        Some("crypto_perp")
    );
    assert_eq!(broker["broker"]["connector_enabled"].as_bool(), Some(false));
    assert_eq!(
        broker["broker"]["external_contact_enabled"].as_bool(),
        Some(false)
    );
    assert_eq!(
        broker["broker"]["live_order_enabled"].as_bool(),
        Some(false)
    );
    assert_eq!(risk["limits"]["allow_margin"].as_bool(), Some(false));
    assert_eq!(risk["limits"]["allow_short"].as_bool(), Some(false));
    assert_eq!(risk["limits"]["allow_options"].as_bool(), Some(false));
    assert_eq!(risk["limits"]["allow_cfd"].as_bool(), Some(false));
    assert_eq!(risk["limits"]["allow_live"].as_bool(), Some(false));

    for raw in [lane_raw, broker_raw, risk_raw] {
        let lower = raw.to_ascii_lowercase();
        assert!(!lower.contains("api_key ="));
        assert!(!lower.contains("api_secret ="));
        assert!(!lower.contains("account_id ="));
    }
}
