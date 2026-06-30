//! Stock/ETF asset-lane audit event contracts for ADR-0048.
//!
//! These source-only validators define immutable event references for the
//! `stock_etf_cash` lane. They do not write audit rows, apply migrations,
//! contact IBKR, read secrets, or authorize paper/tiny-live/live execution.

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::stock_etf_lane::{
    AssetLane, Broker, BrokerEnvironment, BrokerOperation, StockEtfDenialReason,
};

pub const STOCK_ETF_ASSET_LANE_EVENTS_CONTRACT_ID: &str = "audit.asset_lane_events_v1";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfAssetLaneEventKind {
    Unknown,
    GateCheck,
    ReadinessStatus,
    LifecycleEventRef,
    MarketDataProvenanceRef,
    DqManifestRef,
    ScorecardInputRef,
    ScorecardDerivedRef,
    ReleasePacketRef,
    TinyLiveEligibilityRef,
    KillDisableCleanupRef,
}

impl Default for StockEtfAssetLaneEventKind {
    fn default() -> Self {
        Self::Unknown
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfAssetLaneEventV1 {
    pub schema_version: String,
    pub source_version: u32,
    pub event_id: String,
    pub event_kind: StockEtfAssetLaneEventKind,
    pub sequence_number: u64,
    pub genesis_event: bool,
    pub previous_event_hash: String,
    pub event_time_ms: u64,
    pub producer_commit: String,
    pub actor: String,
    pub source: String,
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub environment: BrokerEnvironment,
    pub operation: BrokerOperation,
    pub permission_scope: String,
    pub account_fingerprint_hash: String,
    pub session_fingerprint_hash: String,
    pub decision_id: String,
    pub order_intent_id: String,
    pub allowed: bool,
    pub denial_reason: Option<StockEtfDenialReason>,
    pub payload_hash: String,
    pub raw_artifact_hash: String,
    pub redacted_summary_hash: String,
    pub source_artifact_hash: String,
    pub input_artifact_hashes: Vec<String>,
    pub secret_content_serialized: bool,
    pub raw_payload_inlined: bool,
}

impl Default for StockEtfAssetLaneEventV1 {
    fn default() -> Self {
        Self {
            schema_version: STOCK_ETF_ASSET_LANE_EVENTS_CONTRACT_ID.to_string(),
            source_version: 0,
            event_id: String::new(),
            event_kind: StockEtfAssetLaneEventKind::Unknown,
            sequence_number: 0,
            genesis_event: false,
            previous_event_hash: String::new(),
            event_time_ms: 0,
            producer_commit: String::new(),
            actor: String::new(),
            source: String::new(),
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            environment: BrokerEnvironment::ReadOnly,
            operation: BrokerOperation::HealthRead,
            permission_scope: String::new(),
            account_fingerprint_hash: String::new(),
            session_fingerprint_hash: String::new(),
            decision_id: String::new(),
            order_intent_id: String::new(),
            allowed: false,
            denial_reason: None,
            payload_hash: String::new(),
            raw_artifact_hash: String::new(),
            redacted_summary_hash: String::new(),
            source_artifact_hash: String::new(),
            input_artifact_hashes: Vec::new(),
            secret_content_serialized: false,
            raw_payload_inlined: false,
        }
    }
}

impl StockEtfAssetLaneEventV1 {
    pub fn accepted_genesis_fixture() -> Self {
        Self {
            source_version: 1,
            event_id: "stock-etf-audit-event-0001".to_string(),
            event_kind: StockEtfAssetLaneEventKind::GateCheck,
            sequence_number: 1,
            genesis_event: true,
            previous_event_hash: String::new(),
            event_time_ms: 1_772_233_000_000,
            producer_commit: "2855d529".to_string(),
            actor: "PM".to_string(),
            source: "phase2_ibkr_external_surface_gate_v1".to_string(),
            operation: BrokerOperation::HealthRead,
            permission_scope: "readonly_gate_check".to_string(),
            account_fingerprint_hash: "1".repeat(64),
            session_fingerprint_hash: "2".repeat(64),
            decision_id: "decision-not-applicable".to_string(),
            order_intent_id: "order-not-applicable".to_string(),
            allowed: true,
            denial_reason: None,
            payload_hash: "3".repeat(64),
            raw_artifact_hash: "4".repeat(64),
            redacted_summary_hash: "5".repeat(64),
            source_artifact_hash: "6".repeat(64),
            input_artifact_hashes: vec!["7".repeat(64), "8".repeat(64)],
            secret_content_serialized: false,
            raw_payload_inlined: false,
            ..Self::default()
        }
    }

    pub fn accepted_chained_fixture() -> Self {
        Self {
            source_version: 1,
            event_id: "stock-etf-audit-event-0002".to_string(),
            event_kind: StockEtfAssetLaneEventKind::ScorecardInputRef,
            sequence_number: 2,
            genesis_event: false,
            previous_event_hash: "9".repeat(64),
            event_time_ms: 1_772_233_100_000,
            producer_commit: "2855d529".to_string(),
            actor: "PM".to_string(),
            source: "stock_etf_scorecard_inputs".to_string(),
            operation: BrokerOperation::ScorecardDerive,
            permission_scope: "derived_scorecard_input_reference".to_string(),
            account_fingerprint_hash: "a".repeat(64),
            session_fingerprint_hash: "b".repeat(64),
            decision_id: "decision-not-applicable".to_string(),
            order_intent_id: "order-not-applicable".to_string(),
            allowed: true,
            denial_reason: None,
            payload_hash: "c".repeat(64),
            raw_artifact_hash: "d".repeat(64),
            redacted_summary_hash: "e".repeat(64),
            source_artifact_hash: "f".repeat(64),
            input_artifact_hashes: vec!["1".repeat(64), "2".repeat(64)],
            secret_content_serialized: false,
            raw_payload_inlined: false,
            ..Self::default()
        }
    }

    pub fn validate(&self) -> StockEtfAssetLaneEventVerdict<StockEtfAssetLaneEventBlocker> {
        use StockEtfAssetLaneEventBlocker as Blocker;

        let mut blockers = Vec::new();
        if self.schema_version != STOCK_ETF_ASSET_LANE_EVENTS_CONTRACT_ID {
            blockers.push(Blocker::SchemaVersionMismatch);
        }
        if self.source_version != 1 {
            blockers.push(Blocker::SourceVersionMismatch);
        }
        if self.event_id.trim().is_empty() {
            blockers.push(Blocker::EventIdMissing);
        }
        if self.event_kind == StockEtfAssetLaneEventKind::Unknown {
            blockers.push(Blocker::EventKindUnknown);
        }
        if self.sequence_number == 0 {
            blockers.push(Blocker::SequenceNumberMissing);
        }
        if self.genesis_event {
            if self.sequence_number != 1 {
                blockers.push(Blocker::GenesisSequenceInvalid);
            }
            if !self.previous_event_hash.trim().is_empty() {
                blockers.push(Blocker::GenesisPreviousHashPresent);
            }
        } else if !is_sha256_hex(&self.previous_event_hash) {
            blockers.push(Blocker::PreviousEventHashInvalid);
        }
        if self.event_time_ms == 0 {
            blockers.push(Blocker::EventTimeMissing);
        }
        if self.producer_commit.trim().is_empty() {
            blockers.push(Blocker::ProducerCommitMissing);
        }
        if self.actor.trim().is_empty() {
            blockers.push(Blocker::ActorMissing);
        }
        if self.source.trim().is_empty() {
            blockers.push(Blocker::SourceMissing);
        }
        if self.asset_lane != AssetLane::StockEtfCash {
            blockers.push(Blocker::WrongAssetLane);
        }
        if self.broker != Broker::Ibkr {
            blockers.push(Blocker::WrongBroker);
        }
        if self.environment == BrokerEnvironment::LiveReservedDenied {
            blockers.push(Blocker::LiveEnvironmentDenied);
        }
        if self.permission_scope.trim().is_empty() {
            blockers.push(Blocker::PermissionScopeMissing);
        }
        if !is_sha256_hex(&self.account_fingerprint_hash) {
            blockers.push(Blocker::AccountFingerprintHashInvalid);
        }
        if !is_sha256_hex(&self.session_fingerprint_hash) {
            blockers.push(Blocker::SessionFingerprintHashInvalid);
        }
        if self.decision_id.trim().is_empty() {
            blockers.push(Blocker::DecisionIdMissing);
        }
        if self.order_intent_id.trim().is_empty() {
            blockers.push(Blocker::OrderIntentIdMissing);
        }
        if self.allowed && self.denial_reason.is_some() {
            blockers.push(Blocker::DenialReasonPresentOnAllowedEvent);
        }
        if !self.allowed && self.denial_reason.is_none() {
            blockers.push(Blocker::DenialReasonMissingOnDeniedEvent);
        }
        if !is_sha256_hex(&self.payload_hash) {
            blockers.push(Blocker::PayloadHashInvalid);
        }
        if !is_sha256_hex(&self.raw_artifact_hash) {
            blockers.push(Blocker::RawArtifactHashInvalid);
        }
        if !is_sha256_hex(&self.redacted_summary_hash) {
            blockers.push(Blocker::RedactedSummaryHashInvalid);
        }
        if !is_sha256_hex(&self.source_artifact_hash) {
            blockers.push(Blocker::SourceArtifactHashInvalid);
        }
        if self.input_artifact_hashes.is_empty() {
            blockers.push(Blocker::InputArtifactHashesMissing);
        }
        if self
            .input_artifact_hashes
            .iter()
            .any(|hash| !is_sha256_hex(hash))
        {
            blockers.push(Blocker::InputArtifactHashInvalid);
        }
        if self.secret_content_serialized {
            blockers.push(Blocker::SecretContentSerialized);
        }
        if self.raw_payload_inlined {
            blockers.push(Blocker::RawPayloadInlined);
        }

        StockEtfAssetLaneEventVerdict::new(blockers)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfAssetLaneEventVerdict<B> {
    pub accepted: bool,
    pub blockers: Vec<B>,
}

impl<B> StockEtfAssetLaneEventVerdict<B> {
    fn new(blockers: Vec<B>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfAssetLaneEventBlocker {
    SchemaVersionMismatch,
    SourceVersionMismatch,
    EventIdMissing,
    EventKindUnknown,
    SequenceNumberMissing,
    GenesisSequenceInvalid,
    GenesisPreviousHashPresent,
    PreviousEventHashInvalid,
    EventTimeMissing,
    ProducerCommitMissing,
    ActorMissing,
    SourceMissing,
    WrongAssetLane,
    WrongBroker,
    LiveEnvironmentDenied,
    PermissionScopeMissing,
    AccountFingerprintHashInvalid,
    SessionFingerprintHashInvalid,
    DecisionIdMissing,
    OrderIntentIdMissing,
    DenialReasonPresentOnAllowedEvent,
    DenialReasonMissingOnDeniedEvent,
    PayloadHashInvalid,
    RawArtifactHashInvalid,
    RedactedSummaryHashInvalid,
    SourceArtifactHashInvalid,
    InputArtifactHashesMissing,
    InputArtifactHashInvalid,
    SecretContentSerialized,
    RawPayloadInlined,
}
