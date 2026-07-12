#![forbid(unsafe_code)]
#![deny(missing_debug_implementations)]

//! Isolated source-only strict Ed25519 verification for bounded ALR fit inputs.
//!
//! A successful result is deliberately unattested. It proves signature checks
//! and deterministic input identities only; it grants no runtime authority.

mod contract;
mod verifier;

pub use contract::{
    BytesFieldV1, EvidenceBindingInputV1, KeyBindingInputV1, MetadataFieldV1,
    PhaseVerificationInputV1, SignatureJobInputV1, SignatureRoleV1, UnattestedVerificationOutputV1,
    UnattestedVerificationReceiptV1, VerificationErrorCodeV1, VerificationPhaseV1,
    VerifiedSignatureJobV1,
};
pub use verifier::verify_unattested_phase_v1;
