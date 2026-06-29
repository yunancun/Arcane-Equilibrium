//! Immutable IBKR Phase 2 external-surface gate artifact contract.
//!
//! This module validates the artifact shape required before first IBKR contact.
//! It performs no file I/O, no secret lookup, no socket I/O, and no broker order
//! routing.

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_gate::{IbkrExternalSurfaceGateV1, IBKR_PHASE2_ADR, IBKR_PHASE2_AMD};
use crate::ibkr_phase2_policies::IbkrPhase2GatePrerequisiteFlags;
use crate::ibkr_phase2_runtime::{IbkrApiSessionTopologyV1, IbkrSecretSlotContractV1};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrPhase2GateArtifactV1 {
    pub artifact_id: String,
    pub adr: String,
    pub amd: String,
    pub source_commit: String,
    pub created_at_ms: u64,
    pub immutable_storage_path: String,
    pub reviewer_roles: Vec<String>,
    pub sealed: bool,
    pub gate: IbkrExternalSurfaceGateV1,
    pub policy_flags: IbkrPhase2GatePrerequisiteFlags,
    pub secret_slot_contract: IbkrSecretSlotContractV1,
    pub api_session_topology: IbkrApiSessionTopologyV1,
    pub raw_artifact_hash: String,
    pub redacted_summary_hash: String,
    pub supersedes_artifact_id: Option<String>,
}

impl Default for IbkrPhase2GateArtifactV1 {
    fn default() -> Self {
        Self {
            artifact_id: String::new(),
            adr: IBKR_PHASE2_ADR.to_string(),
            amd: IBKR_PHASE2_AMD.to_string(),
            source_commit: String::new(),
            created_at_ms: 0,
            immutable_storage_path: String::new(),
            reviewer_roles: Vec::new(),
            sealed: false,
            gate: IbkrExternalSurfaceGateV1::default(),
            policy_flags: IbkrPhase2GatePrerequisiteFlags {
                redaction_suite_passed: false,
                rate_limit_policy_present: false,
                audit_event_policy_present: false,
                paper_attestation_contract_present: false,
                python_no_write_guard_present: false,
            },
            secret_slot_contract: IbkrSecretSlotContractV1::default(),
            api_session_topology: IbkrApiSessionTopologyV1::default(),
            raw_artifact_hash: String::new(),
            redacted_summary_hash: String::new(),
            supersedes_artifact_id: None,
        }
    }
}

impl IbkrPhase2GateArtifactV1 {
    pub fn validate(&self) -> IbkrPhase2GateArtifactVerdict {
        use IbkrPhase2GateArtifactBlocker as Blocker;

        let mut blockers = Vec::new();
        if self.artifact_id.trim().is_empty() {
            blockers.push(Blocker::ArtifactIdMissing);
        }
        if self.adr != IBKR_PHASE2_ADR {
            blockers.push(Blocker::AdrMismatch);
        }
        if self.amd != IBKR_PHASE2_AMD {
            blockers.push(Blocker::AmdMismatch);
        }
        if self.source_commit.trim().is_empty() {
            blockers.push(Blocker::SourceCommitMissing);
        }
        if self.created_at_ms == 0 {
            blockers.push(Blocker::CreatedAtMissing);
        }
        if self.immutable_storage_path.trim().is_empty() {
            blockers.push(Blocker::ImmutableStoragePathMissing);
        }
        if !self.sealed {
            blockers.push(Blocker::ArtifactNotSealed);
        }
        if !contains_role(&self.reviewer_roles, "PM") {
            blockers.push(Blocker::PmReviewerMissing);
        }
        if !contains_role(&self.reviewer_roles, "Operator") {
            blockers.push(Blocker::OperatorReviewerMissing);
        }
        if !is_sha256_hex(&self.raw_artifact_hash) {
            blockers.push(Blocker::RawArtifactHashInvalid);
        }
        if !is_sha256_hex(&self.redacted_summary_hash) {
            blockers.push(Blocker::RedactedSummaryHashInvalid);
        }
        if !self.gate.validate().ibkr_contact_allowed {
            blockers.push(Blocker::ExternalSurfaceGateRejected);
        }
        if self.gate.ibkr_call_performed {
            blockers.push(Blocker::IbkrCallAlreadyPerformed);
        }
        if !all_policy_flags_true(self.policy_flags) {
            blockers.push(Blocker::PolicyPrerequisiteFlagsRejected);
        }
        if !gate_flags_match_artifact(self) {
            blockers.push(Blocker::PolicyGateFlagMismatch);
        }
        let secret_verdict = self.secret_slot_contract.validate();
        if !secret_verdict.accepted {
            blockers.push(Blocker::SecretSlotContractRejected);
        }
        let topology_verdict = self.api_session_topology.validate();
        if !topology_verdict.accepted {
            blockers.push(Blocker::ApiSessionTopologyRejected);
        }
        if !runtime_contracts_match_gate(self, secret_verdict.accepted, topology_verdict.accepted) {
            blockers.push(Blocker::RuntimeGateFlagMismatch);
        }

        IbkrPhase2GateArtifactVerdict {
            ibkr_contact_allowed: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrPhase2GateArtifactVerdict {
    pub ibkr_contact_allowed: bool,
    pub blockers: Vec<IbkrPhase2GateArtifactBlocker>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrPhase2GateArtifactBlocker {
    ArtifactIdMissing,
    AdrMismatch,
    AmdMismatch,
    SourceCommitMissing,
    CreatedAtMissing,
    ImmutableStoragePathMissing,
    ArtifactNotSealed,
    PmReviewerMissing,
    OperatorReviewerMissing,
    RawArtifactHashInvalid,
    RedactedSummaryHashInvalid,
    ExternalSurfaceGateRejected,
    IbkrCallAlreadyPerformed,
    PolicyPrerequisiteFlagsRejected,
    PolicyGateFlagMismatch,
    SecretSlotContractRejected,
    ApiSessionTopologyRejected,
    RuntimeGateFlagMismatch,
}

pub fn is_sha256_hex(value: &str) -> bool {
    let bytes = value.as_bytes();
    bytes.len() == 64
        && bytes
            .iter()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(b))
}

fn contains_role(roles: &[String], expected: &str) -> bool {
    roles.iter().any(|role| role == expected)
}

fn all_policy_flags_true(flags: IbkrPhase2GatePrerequisiteFlags) -> bool {
    flags.redaction_suite_passed
        && flags.rate_limit_policy_present
        && flags.audit_event_policy_present
        && flags.paper_attestation_contract_present
        && flags.python_no_write_guard_present
}

fn gate_flags_match_artifact(artifact: &IbkrPhase2GateArtifactV1) -> bool {
    artifact.gate.redaction_suite_passed == artifact.policy_flags.redaction_suite_passed
        && artifact.gate.rate_limit_policy_present
            == artifact.policy_flags.rate_limit_policy_present
        && artifact.gate.audit_event_policy_present
            == artifact.policy_flags.audit_event_policy_present
        && artifact.gate.paper_attestation_contract_present
            == artifact.policy_flags.paper_attestation_contract_present
        && artifact.gate.python_no_write_guard_present
            == artifact.policy_flags.python_no_write_guard_present
}

fn runtime_contracts_match_gate(
    artifact: &IbkrPhase2GateArtifactV1,
    secret_accepted: bool,
    topology_accepted: bool,
) -> bool {
    artifact.gate.secret_contract_present == secret_accepted
        && artifact.gate.live_secret_absent_or_empty
            == artifact.secret_slot_contract.live_secret_absent_or_empty
        && topology_accepted
}
