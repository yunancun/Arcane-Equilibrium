//! Accepted Stock/ETF paper order request fixtures.

use crate::stock_etf_lane::{
    AssetLane, AuthorityScope, Broker, BrokerEnvironment, BrokerOperation, InstrumentKind,
};
use crate::stock_etf_lane_scoped_ipc::StockEtfLaneScopedIpcMethod;
use crate::stock_etf_scorecard_inputs::StockEtfOrderSide;

use super::{
    StockEtfLimitPricePolicy, StockEtfPaperOrderRequestEnvelopeV1, StockEtfPaperOrderType,
    StockEtfPaperTimeInForce, STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID,
};

impl StockEtfPaperOrderRequestEnvelopeV1 {
    pub fn accepted_preview_fixture() -> Self {
        Self {
            contract_id: STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            environment: BrokerEnvironment::Paper,
            request_method: StockEtfLaneScopedIpcMethod::PreviewPaperOrder,
            operation: BrokerOperation::PaperOrderSubmit,
            authority_scope: AuthorityScope::ReadOnly,
            request_id: "preview_request_0001".to_string(),
            account_fingerprint_hash: "1".repeat(64),
            risk_config_hash: "2".repeat(64),
            instrument_identity_hash: "3".repeat(64),
            cost_model_version_hash: "4".repeat(64),
            pit_universe_contract_hash: "5".repeat(64),
            source_artifact_hash: "6".repeat(64),
            symbol: "SPY".to_string(),
            instrument_kind: Some(InstrumentKind::Etf),
            side: Some(StockEtfOrderSide::Buy),
            order_type: Some(StockEtfPaperOrderType::Limit),
            quantity_decimal: "10".to_string(),
            limit_price_policy: Some(StockEtfLimitPricePolicy::RequiredForLimitOrder),
            limit_price_decimal: "450.25".to_string(),
            time_in_force: Some(StockEtfPaperTimeInForce::Day),
            ..Self::default()
        }
    }

    pub fn accepted_submit_fixture() -> Self {
        Self {
            request_method: StockEtfLaneScopedIpcMethod::SubmitPaperOrder,
            authority_scope: AuthorityScope::PaperRehearsal,
            effect_capable: true,
            request_id: "submit_request_0001".to_string(),
            session_attestation_hash: "7".repeat(64),
            scoped_authorization_hash: "8".repeat(64),
            decision_lease_id: "decision_lease_0001".to_string(),
            guardian_state_hash: "9".repeat(64),
            lifecycle_contract_hash: "a".repeat(64),
            broker_capability_registry_hash: "b".repeat(64),
            audit_event_id: "audit_event_0001".to_string(),
            cost_model_version_hash: String::new(),
            pit_universe_contract_hash: String::new(),
            source_artifact_hash: String::new(),
            order_local_id: "local_order_0001".to_string(),
            idempotency_key: "idem_0001".to_string(),
            ..Self::accepted_preview_fixture()
        }
    }

    pub fn accepted_cancel_fixture() -> Self {
        Self {
            contract_id: STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            environment: BrokerEnvironment::Paper,
            request_method: StockEtfLaneScopedIpcMethod::CancelPaperOrder,
            operation: BrokerOperation::PaperOrderCancel,
            authority_scope: AuthorityScope::PaperRehearsal,
            effect_capable: true,
            request_id: "cancel_request_0001".to_string(),
            account_fingerprint_hash: "1".repeat(64),
            session_attestation_hash: "7".repeat(64),
            scoped_authorization_hash: "8".repeat(64),
            decision_lease_id: "decision_lease_0001".to_string(),
            guardian_state_hash: "9".repeat(64),
            lifecycle_contract_hash: "a".repeat(64),
            broker_capability_registry_hash: "b".repeat(64),
            audit_event_id: "audit_event_0002".to_string(),
            order_local_id: "local_order_0001".to_string(),
            idempotency_key: "cancel_idem_0001".to_string(),
            broker_order_id: "paper_broker_order_0001".to_string(),
            cancel_reason: "risk_or_operator_rehearsal".to_string(),
            ..Self::default()
        }
    }

    pub fn accepted_replace_fixture() -> Self {
        Self {
            request_method: StockEtfLaneScopedIpcMethod::ReplacePaperOrder,
            operation: BrokerOperation::PaperOrderReplace,
            request_id: "replace_request_0001".to_string(),
            audit_event_id: "audit_event_0003".to_string(),
            symbol: "SPY".to_string(),
            instrument_identity_hash: "3".repeat(64),
            side: Some(StockEtfOrderSide::Buy),
            replacement_idempotency_key: "replace_idem_0001".to_string(),
            replacement_quantity_decimal: "12".to_string(),
            replacement_limit_price_policy: Some(StockEtfLimitPricePolicy::RequiredForLimitOrder),
            replacement_limit_price_decimal: "451.10".to_string(),
            replacement_time_in_force: Some(StockEtfPaperTimeInForce::Day),
            replace_reason: "paper_rehearsal_price_or_size_update".to_string(),
            idempotency_key: String::new(),
            cancel_reason: String::new(),
            ..Self::accepted_cancel_fixture()
        }
    }
}
