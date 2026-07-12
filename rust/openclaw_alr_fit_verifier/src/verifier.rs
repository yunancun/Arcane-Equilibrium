use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use ed25519_dalek::{Signature, VerifyingKey};
use sha2::{Digest, Sha256};

use crate::contract::{
    BytesFieldV1, EvidenceBindingInputV1, MetadataFieldV1, PhaseVerificationInputV1,
    SignatureJobInputV1, SignatureRoleV1, UnattestedVerificationOutputV1,
    UnattestedVerificationReceiptV1, VerificationErrorCodeV1, VerificationPhaseV1,
    VerifiedSignatureJobV1,
};

const EXPECTED_USAGE: &str = "ALR_TRUSTED_FIT_HANDSHAKE_SIGNING";
const MAX_REQUEST_OR_INNER_FIELD_BYTES: usize = 1_048_576;
const MAX_STATUS_OR_OUTER_FIELD_BYTES: usize = 2_097_152;
const MAX_POLICY_FIELD_BYTES: usize = 1_048_576;
const MAX_AGGREGATE_INPUT_BYTES: usize = 10_485_760;
const MAX_RECEIPT_BYTES: usize = 32_768;
const MAX_SIGNED_JOBS: usize = 3;
const MAX_SIGNED_INTEGER: u64 = 9_223_372_036_854_775_807;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum AllocationSiteV1 {
    Preimage(SignatureRoleV1),
    VerifiedJobs,
    SignatureText(SignatureRoleV1),
    ReceiptBytes,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct VerificationFaultsV1 {
    #[cfg(test)]
    allocation_failure: Option<AllocationSiteV1>,
    #[cfg(test)]
    force_receipt_invariant: bool,
    #[cfg(test)]
    force_receipt_cap: bool,
}

impl VerificationFaultsV1 {
    const NONE: Self = Self {
        #[cfg(test)]
        allocation_failure: None,
        #[cfg(test)]
        force_receipt_invariant: false,
        #[cfg(test)]
        force_receipt_cap: false,
    };

    #[cfg(test)]
    const fn fail_allocation(allocation_failure: AllocationSiteV1) -> Self {
        Self {
            allocation_failure: Some(allocation_failure),
            force_receipt_invariant: false,
            force_receipt_cap: false,
        }
    }

    #[cfg(test)]
    const fn force_receipt_invariant() -> Self {
        Self {
            allocation_failure: None,
            force_receipt_invariant: true,
            force_receipt_cap: false,
        }
    }

    #[cfg(test)]
    const fn force_receipt_cap() -> Self {
        Self {
            allocation_failure: None,
            force_receipt_invariant: false,
            force_receipt_cap: true,
        }
    }

    fn fails_allocation(self, site: AllocationSiteV1) -> bool {
        #[cfg(test)]
        {
            matches!(self.allocation_failure, Some(candidate) if candidate == site)
        }
        #[cfg(not(test))]
        {
            let _ = site;
            false
        }
    }

    const fn forces_receipt_invariant(self) -> bool {
        #[cfg(test)]
        {
            self.force_receipt_invariant
        }
        #[cfg(not(test))]
        {
            false
        }
    }

    const fn forces_receipt_cap(self) -> bool {
        #[cfg(test)]
        {
            self.force_receipt_cap
        }
        #[cfg(not(test))]
        {
            false
        }
    }
}

const AUTHORITY_COUNTER_KEYS: [&str; 17] = [
    "cost_gate_change_count",
    "database_write_count",
    "decision_lease_count",
    "direct_parameter_change_count",
    "exchange_contact_count",
    "guardian_action_count",
    "latest_pointer_update_count",
    "live_or_mainnet_action_count",
    "model_fit_count",
    "order_or_probe_count",
    "proof_claim_count",
    "protected_evidence_delete_count",
    "risk_config_change_count",
    "runtime_mutation_count",
    "serving_or_promotion_count",
    "symlink_update_count",
    "trading_action_count",
];

const NO_AUTHORITY_KEYS: [&str; 17] = [
    "cost_gate_authority",
    "database_write_authority",
    "decision_lease_authority",
    "direct_parameter_authority",
    "exchange_authority",
    "guardian_authority",
    "latest_authority",
    "live_or_mainnet_authority",
    "order_or_probe_authority",
    "promotion_authority",
    "proof_authority",
    "protected_evidence_delete_authority",
    "risk_config_authority",
    "runtime_mutation_authority",
    "serving_authority",
    "symlink_authority",
    "trading_authority",
];

/// Verify one exact closed phase and return only a source-level unattested receipt.
pub fn verify_unattested_phase_v1(
    input: PhaseVerificationInputV1<'_>,
) -> Result<UnattestedVerificationOutputV1, VerificationErrorCodeV1> {
    verify_unattested_phase_v1_with_faults(input, VerificationFaultsV1::NONE)
}

fn verify_unattested_phase_v1_with_faults(
    input: PhaseVerificationInputV1<'_>,
    faults: VerificationFaultsV1,
) -> Result<UnattestedVerificationOutputV1, VerificationErrorCodeV1> {
    validate_phase_shape(input.declared_phase, input.jobs)?;
    validate_aggregate_bound(&input)?;
    validate_metadata(&input)?;
    validate_byte_bounds(&input)?;

    let (public_key, public_key_bytes) = decode_public_key(input.key_binding.public_key_base64url)?;
    let signature_bytes = decode_signatures(input.jobs)?;

    let mut verified_parts: [Option<VerifiedJobPartsV1>; MAX_SIGNED_JOBS] = [None, None, None];
    for (index, job) in input.jobs.iter().enumerate() {
        let domain = job.role.domain();
        let preimage = build_preimage(domain, job.signed_material_bytes, job.role, faults)?;
        let preimage_sha256 = sha256(&preimage);
        let preimage_bytes_len = preimage.len();
        let signature = Signature::from_bytes(&signature_bytes[index]);
        public_key
            .verify_strict(&preimage, &signature)
            .map_err(|_| VerificationErrorCodeV1::StrictSignatureInvalid(job.role))?;
        drop(preimage);

        verified_parts[index] = Some(VerifiedJobPartsV1 {
            job_kind: job.role,
            envelope_bytes_len: job.envelope_bytes.len(),
            envelope_sha256: sha256(job.envelope_bytes),
            signed_material_bytes_len: job.signed_material_bytes.len(),
            signed_material_sha256: sha256(job.signed_material_bytes),
            preimage_bytes_len,
            preimage_sha256,
            signature_bytes_sha256: sha256(&signature_bytes[index]),
        });
    }

    if faults.fails_allocation(AllocationSiteV1::VerifiedJobs) {
        return Err(VerificationErrorCodeV1::CapacityAllocationFailed);
    }
    let mut verified_jobs = Vec::new();
    verified_jobs
        .try_reserve_exact(input.jobs.len())
        .map_err(|_| VerificationErrorCodeV1::CapacityAllocationFailed)?;
    for (index, input_job) in input.jobs.iter().enumerate() {
        let parts = verified_parts[index]
            .take()
            .ok_or(VerificationErrorCodeV1::ReceiptEncodingInvariant)?;
        if faults.fails_allocation(AllocationSiteV1::SignatureText(input_job.role)) {
            return Err(VerificationErrorCodeV1::CapacityAllocationFailed);
        }
        let mut signature_base64url = String::new();
        signature_base64url
            .try_reserve_exact(input_job.signature_base64url.len())
            .map_err(|_| VerificationErrorCodeV1::CapacityAllocationFailed)?;
        signature_base64url.push_str(input_job.signature_base64url);
        verified_jobs.push(VerifiedSignatureJobV1::from_verified_parts(
            parts.job_kind,
            parts.envelope_bytes_len,
            parts.envelope_sha256,
            parts.signed_material_bytes_len,
            parts.signed_material_sha256,
            parts.preimage_bytes_len,
            parts.preimage_sha256,
            signature_base64url,
            parts.signature_bytes_sha256,
        ));
    }

    let canonical_bytes = encode_receipt(&input, &public_key_bytes, &verified_jobs, faults)?;
    let receipt_sha256 = sha256(&canonical_bytes);
    let receipt = UnattestedVerificationReceiptV1::from_verified_parts(
        input.declared_phase,
        verified_jobs,
        canonical_bytes,
        receipt_sha256,
    );
    Ok(UnattestedVerificationOutputV1::from_receipt(receipt))
}

fn validate_phase_shape(
    phase: VerificationPhaseV1,
    jobs: &[SignatureJobInputV1<'_>],
) -> Result<(), VerificationErrorCodeV1> {
    let expected: &[SignatureRoleV1] = match phase {
        VerificationPhaseV1::RequestOnly => &[SignatureRoleV1::Request],
        VerificationPhaseV1::SignedStatus => {
            &[SignatureRoleV1::Request, SignatureRoleV1::SignedStatus]
        }
        VerificationPhaseV1::TerminalSuccess => &[
            SignatureRoleV1::Request,
            SignatureRoleV1::OuterTerminal,
            SignatureRoleV1::V159Inner,
        ],
        VerificationPhaseV1::TerminalNoInner => {
            &[SignatureRoleV1::Request, SignatureRoleV1::OuterTerminal]
        }
    };
    if jobs.len() != expected.len()
        || jobs
            .iter()
            .zip(expected.iter())
            .any(|(job, role)| job.role != *role)
    {
        return Err(VerificationErrorCodeV1::PhaseShapeInvalid);
    }
    Ok(())
}

fn validate_aggregate_bound(
    input: &PhaseVerificationInputV1<'_>,
) -> Result<(), VerificationErrorCodeV1> {
    checked_raw_slice_sum(
        [
            input.evidence_binding.trust_policy_snapshot_bytes.len(),
            input.evidence_binding.key_status_overlay_bytes.len(),
        ]
        .into_iter()
        .chain(
            input
                .jobs
                .iter()
                .flat_map(|job| [job.envelope_bytes.len(), job.signed_material_bytes.len()]),
        ),
    )?;
    Ok(())
}

fn checked_raw_slice_sum(
    lengths: impl IntoIterator<Item = usize>,
) -> Result<usize, VerificationErrorCodeV1> {
    let mut total = 0_usize;
    for length in lengths {
        total = total
            .checked_add(length)
            .ok_or(VerificationErrorCodeV1::LengthOverflow)?;
    }
    if total > MAX_AGGREGATE_INPUT_BYTES {
        return Err(VerificationErrorCodeV1::AggregateInputTooLarge);
    }
    Ok(total)
}

fn validate_metadata(input: &PhaseVerificationInputV1<'_>) -> Result<(), VerificationErrorCodeV1> {
    if !valid_identifier(input.key_binding.issuer_id) {
        return Err(VerificationErrorCodeV1::MetadataInvalid(
            MetadataFieldV1::IssuerId,
        ));
    }
    if !valid_identifier(input.key_binding.key_id) {
        return Err(VerificationErrorCodeV1::MetadataInvalid(
            MetadataFieldV1::KeyId,
        ));
    }
    if input.key_binding.usage != EXPECTED_USAGE {
        return Err(VerificationErrorCodeV1::MetadataInvalid(
            MetadataFieldV1::Usage,
        ));
    }
    if !(1..=MAX_SIGNED_INTEGER).contains(&input.key_binding.key_generation) {
        return Err(VerificationErrorCodeV1::MetadataInvalid(
            MetadataFieldV1::KeyGeneration,
        ));
    }
    if !valid_identifier(input.evidence_binding.trust_policy_id) {
        return Err(VerificationErrorCodeV1::MetadataInvalid(
            MetadataFieldV1::TrustPolicyId,
        ));
    }
    if !(1..=MAX_SIGNED_INTEGER).contains(&input.evidence_binding.trust_policy_epoch) {
        return Err(VerificationErrorCodeV1::MetadataInvalid(
            MetadataFieldV1::TrustPolicyEpoch,
        ));
    }
    if !valid_lower_hex_64(input.evidence_binding.provider_evidence_digest_sha256) {
        return Err(VerificationErrorCodeV1::MetadataInvalid(
            MetadataFieldV1::ProviderEvidenceDigestSha256,
        ));
    }
    if !valid_timestamp(input.evidence_binding.adjudicated_at_claim) {
        return Err(VerificationErrorCodeV1::MetadataInvalid(
            MetadataFieldV1::AdjudicatedAtClaim,
        ));
    }
    Ok(())
}

fn validate_byte_bounds(
    input: &PhaseVerificationInputV1<'_>,
) -> Result<(), VerificationErrorCodeV1> {
    let policy_length = input.evidence_binding.trust_policy_snapshot_bytes.len();
    if !(2..=MAX_POLICY_FIELD_BYTES).contains(&policy_length) {
        return Err(VerificationErrorCodeV1::BytesLengthInvalid(
            BytesFieldV1::TrustPolicySnapshot,
        ));
    }
    let overlay_length = input.evidence_binding.key_status_overlay_bytes.len();
    if !(2..=MAX_POLICY_FIELD_BYTES).contains(&overlay_length) {
        return Err(VerificationErrorCodeV1::BytesLengthInvalid(
            BytesFieldV1::KeyStatusOverlay,
        ));
    }
    for job in input.jobs {
        let (maximum, envelope_field, signed_material_field) = role_byte_contract(job.role);
        if !(1..=maximum).contains(&job.envelope_bytes.len()) {
            return Err(VerificationErrorCodeV1::BytesLengthInvalid(envelope_field));
        }
        if !(1..=maximum).contains(&job.signed_material_bytes.len()) {
            return Err(VerificationErrorCodeV1::BytesLengthInvalid(
                signed_material_field,
            ));
        }
    }
    Ok(())
}

const fn role_byte_contract(role: SignatureRoleV1) -> (usize, BytesFieldV1, BytesFieldV1) {
    match role {
        SignatureRoleV1::Request => (
            MAX_REQUEST_OR_INNER_FIELD_BYTES,
            BytesFieldV1::RequestEnvelope,
            BytesFieldV1::RequestSignedMaterial,
        ),
        SignatureRoleV1::SignedStatus => (
            MAX_STATUS_OR_OUTER_FIELD_BYTES,
            BytesFieldV1::SignedStatusEnvelope,
            BytesFieldV1::SignedStatusSignedMaterial,
        ),
        SignatureRoleV1::OuterTerminal => (
            MAX_STATUS_OR_OUTER_FIELD_BYTES,
            BytesFieldV1::OuterTerminalEnvelope,
            BytesFieldV1::OuterTerminalSignedMaterial,
        ),
        SignatureRoleV1::V159Inner => (
            MAX_REQUEST_OR_INNER_FIELD_BYTES,
            BytesFieldV1::V159InnerEnvelope,
            BytesFieldV1::V159InnerSignedMaterial,
        ),
    }
}

fn valid_identifier(value: &str) -> bool {
    let bytes = value.as_bytes();
    if bytes.is_empty() || bytes.len() > 128 || !is_lower_alphanumeric(bytes[0]) {
        return false;
    }
    bytes
        .iter()
        .copied()
        .all(|byte| is_lower_alphanumeric(byte) || matches!(byte, b'_' | b'.' | b':' | b'-'))
}

const fn is_lower_alphanumeric(byte: u8) -> bool {
    byte.is_ascii_lowercase() || byte.is_ascii_digit()
}

fn valid_lower_hex_64(value: &str) -> bool {
    value.len() == 64
        && value
            .as_bytes()
            .iter()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(byte))
}

fn valid_timestamp(value: &str) -> bool {
    let bytes = value.as_bytes();
    if bytes.len() != 27
        || bytes[4] != b'-'
        || bytes[7] != b'-'
        || bytes[10] != b'T'
        || bytes[13] != b':'
        || bytes[16] != b':'
        || bytes[19] != b'.'
        || bytes[26] != b'Z'
    {
        return false;
    }
    for index in [
        0_usize, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18, 20, 21, 22, 23, 24, 25,
    ] {
        if !bytes[index].is_ascii_digit() {
            return false;
        }
    }
    let year = decimal(&bytes[0..4]);
    let month = decimal(&bytes[5..7]);
    let day = decimal(&bytes[8..10]);
    let hour = decimal(&bytes[11..13]);
    let minute = decimal(&bytes[14..16]);
    let second = decimal(&bytes[17..19]);
    if year == 0 || !(1..=12).contains(&month) || hour > 23 || minute > 59 || second > 59 {
        return false;
    }
    let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    let maximum_day = match month {
        2 if leap => 29,
        2 => 28,
        4 | 6 | 9 | 11 => 30,
        _ => 31,
    };
    (1..=maximum_day).contains(&day)
}

fn decimal(bytes: &[u8]) -> u32 {
    bytes
        .iter()
        .fold(0_u32, |value, byte| value * 10 + u32::from(byte - b'0'))
}

fn decode_public_key(encoded: &str) -> Result<(VerifyingKey, [u8; 32]), VerificationErrorCodeV1> {
    if encoded.len() != 43 {
        return Err(VerificationErrorCodeV1::PublicKeyBase64UrlInvalid);
    }
    let mut bytes = [0_u8; 32];
    if URL_SAFE_NO_PAD.decode_slice(encoded, &mut bytes) != Ok(32) {
        return Err(VerificationErrorCodeV1::PublicKeyBase64UrlInvalid);
    }
    let mut canonical = [0_u8; 43];
    if URL_SAFE_NO_PAD.encode_slice(bytes, &mut canonical) != Ok(43)
        || canonical.as_slice() != encoded.as_bytes()
    {
        return Err(VerificationErrorCodeV1::PublicKeyBase64UrlInvalid);
    }
    let key = VerifyingKey::from_bytes(&bytes)
        .map_err(|_| VerificationErrorCodeV1::PublicKeyPointInvalid)?;
    Ok((key, bytes))
}

fn decode_signatures(
    jobs: &[SignatureJobInputV1<'_>],
) -> Result<[[u8; 64]; MAX_SIGNED_JOBS], VerificationErrorCodeV1> {
    let mut decoded = [[0_u8; 64]; MAX_SIGNED_JOBS];
    for (index, job) in jobs.iter().enumerate() {
        if job.signature_base64url.len() != 86
            || URL_SAFE_NO_PAD.decode_slice(job.signature_base64url, &mut decoded[index]) != Ok(64)
        {
            return Err(VerificationErrorCodeV1::SignatureBase64UrlInvalid(job.role));
        }
        let mut canonical = [0_u8; 86];
        if URL_SAFE_NO_PAD.encode_slice(decoded[index], &mut canonical) != Ok(86)
            || canonical.as_slice() != job.signature_base64url.as_bytes()
        {
            return Err(VerificationErrorCodeV1::SignatureBase64UrlInvalid(job.role));
        }
    }
    Ok(decoded)
}

fn checked_preimage_capacity(
    domain_length: usize,
    material_length: usize,
) -> Result<usize, VerificationErrorCodeV1> {
    domain_length
        .checked_add(1)
        .and_then(|value| value.checked_add(8))
        .and_then(|value| value.checked_add(material_length))
        .ok_or(VerificationErrorCodeV1::LengthOverflow)
}

fn build_preimage(
    domain: &str,
    material: &[u8],
    role: SignatureRoleV1,
    faults: VerificationFaultsV1,
) -> Result<Vec<u8>, VerificationErrorCodeV1> {
    let material_length =
        u64::try_from(material.len()).map_err(|_| VerificationErrorCodeV1::LengthOverflow)?;
    let capacity = checked_preimage_capacity(domain.len(), material.len())?;
    if faults.fails_allocation(AllocationSiteV1::Preimage(role)) {
        return Err(VerificationErrorCodeV1::CapacityAllocationFailed);
    }
    let mut preimage = Vec::new();
    preimage
        .try_reserve_exact(capacity)
        .map_err(|_| VerificationErrorCodeV1::CapacityAllocationFailed)?;
    preimage.extend_from_slice(domain.as_bytes());
    preimage.push(0);
    preimage.extend_from_slice(&material_length.to_be_bytes());
    preimage.extend_from_slice(material);
    if preimage.len() != capacity {
        return Err(VerificationErrorCodeV1::LengthOverflow);
    }
    Ok(preimage)
}

fn sha256(value: &[u8]) -> [u8; 32] {
    Sha256::digest(value).into()
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct VerifiedJobPartsV1 {
    job_kind: SignatureRoleV1,
    envelope_bytes_len: usize,
    envelope_sha256: [u8; 32],
    signed_material_bytes_len: usize,
    signed_material_sha256: [u8; 32],
    preimage_bytes_len: usize,
    preimage_sha256: [u8; 32],
    signature_bytes_sha256: [u8; 32],
}

fn encode_receipt(
    input: &PhaseVerificationInputV1<'_>,
    public_key_bytes: &[u8; 32],
    jobs: &[VerifiedSignatureJobV1],
    faults: VerificationFaultsV1,
) -> Result<Vec<u8>, VerificationErrorCodeV1> {
    let mut measuring = ReceiptSink::measuring();
    write_receipt(&mut measuring, input, public_key_bytes, jobs)?;
    let expected_length = measuring.len();
    if faults.fails_allocation(AllocationSiteV1::ReceiptBytes) {
        return Err(VerificationErrorCodeV1::CapacityAllocationFailed);
    }

    let mut writing = ReceiptSink::writing(expected_length)?;
    write_receipt(&mut writing, input, public_key_bytes, jobs)?;
    let bytes = writing.finish(expected_length)?;
    if faults.forces_receipt_invariant() {
        return Err(VerificationErrorCodeV1::ReceiptEncodingInvariant);
    }
    let cap_length = if faults.forces_receipt_cap() {
        MAX_RECEIPT_BYTES
            .checked_add(1)
            .ok_or(VerificationErrorCodeV1::LengthOverflow)?
    } else {
        bytes.len()
    };
    enforce_receipt_cap(cap_length)?;
    Ok(bytes)
}

fn write_receipt(
    sink: &mut ReceiptSink,
    input: &PhaseVerificationInputV1<'_>,
    public_key_bytes: &[u8; 32],
    jobs: &[VerifiedSignatureJobV1],
) -> Result<(), VerificationErrorCodeV1> {
    sink.push(b"{\"algorithm\":\"ed25519\",\"authority_counters\":{")?;
    for (index, key) in AUTHORITY_COUNTER_KEYS.iter().enumerate() {
        if index != 0 {
            sink.push(b",")?;
        }
        sink.push_quoted(key)?;
        sink.push(b":0")?;
    }
    sink.push(b"},\"authority_granted\":false,\"canonical_input_bytes_established\":false,\"capability_authenticity\":\"SOURCE_ONLY_UNATTESTED\",\"coordinator_eligible\":false,\"declared_phase\":")?;
    sink.push_quoted(input.declared_phase.as_tag())?;
    sink.push(b",\"durable_consumption_established\":false,\"envelope_payload_binding_established\":false,\"evidence_binding\":{")?;
    write_evidence(sink, input, public_key_bytes)?;
    sink.push(b"},\"jobs\":[")?;
    for (index, job) in jobs.iter().enumerate() {
        if index != 0 {
            sink.push(b",")?;
        }
        write_job(sink, job)?;
    }
    sink.push(b"],\"model_training_performed_claim\":\"NOT_ESTABLISHED\",\"no_authority\":{")?;
    for (index, key) in NO_AUTHORITY_KEYS.iter().enumerate() {
        if index != 0 {
            sink.push(b",")?;
        }
        sink.push_quoted(key)?;
        sink.push(b":false")?;
    }
    sink.push(b"},\"persistence_allowed\":false,\"platform_attested\":false,\"policy_overlay_adjudication_established\":false,\"schema_version\":\"alr_fit_ed25519_verification_receipt_v1\",\"semantic_phase_established\":false,\"signatures_valid\":true,\"training_allowed\":false,\"trusted_time_established\":false,\"verdict\":\"STRICT_SIGNATURES_VALID_INPUT_BINDINGS_CAPABILITY_UNATTESTED\",\"verification_primitive\":\"ed25519_dalek_2.2.0_verify_strict_zip215\"}")?;
    Ok(())
}

fn write_evidence(
    sink: &mut ReceiptSink,
    input: &PhaseVerificationInputV1<'_>,
    public_key_bytes: &[u8; 32],
) -> Result<(), VerificationErrorCodeV1> {
    let key = input.key_binding;
    let evidence: EvidenceBindingInputV1<'_> = input.evidence_binding;
    sink.push(b"\"adjudicated_at_claim\":")?;
    sink.push_quoted(evidence.adjudicated_at_claim)?;
    sink.push(b",\"issuer_id\":")?;
    sink.push_quoted(key.issuer_id)?;
    sink.push(b",\"key_generation\":")?;
    sink.push_u64(key.key_generation)?;
    sink.push(b",\"key_id\":")?;
    sink.push_quoted(key.key_id)?;
    sink.push(b",\"key_status_overlay_bytes_len\":")?;
    sink.push_usize(evidence.key_status_overlay_bytes.len())?;
    sink.push(b",\"key_status_overlay_bytes_sha256\":")?;
    sink.push_digest(&sha256(evidence.key_status_overlay_bytes))?;
    sink.push(b",\"provider_evidence_digest_sha256\":")?;
    sink.push_quoted(evidence.provider_evidence_digest_sha256)?;
    sink.push(b",\"public_key_base64url\":")?;
    sink.push_quoted(key.public_key_base64url)?;
    sink.push(b",\"public_key_bytes_sha256\":")?;
    sink.push_digest(&sha256(public_key_bytes))?;
    sink.push(b",\"trust_policy_epoch\":")?;
    sink.push_u64(evidence.trust_policy_epoch)?;
    sink.push(b",\"trust_policy_id\":")?;
    sink.push_quoted(evidence.trust_policy_id)?;
    sink.push(b",\"trust_policy_snapshot_bytes_len\":")?;
    sink.push_usize(evidence.trust_policy_snapshot_bytes.len())?;
    sink.push(b",\"trust_policy_snapshot_bytes_sha256\":")?;
    sink.push_digest(&sha256(evidence.trust_policy_snapshot_bytes))?;
    sink.push(b",\"usage\":")?;
    sink.push_quoted(key.usage)?;
    Ok(())
}

fn write_job(
    sink: &mut ReceiptSink,
    job: &VerifiedSignatureJobV1,
) -> Result<(), VerificationErrorCodeV1> {
    sink.push(b"{\"domain\":")?;
    sink.push_quoted(job.domain())?;
    sink.push(b",\"envelope_bytes_len\":")?;
    sink.push_usize(job.envelope_bytes_len())?;
    sink.push(b",\"envelope_bytes_sha256\":")?;
    sink.push_digest(job.envelope_bytes_sha256())?;
    sink.push(b",\"job_kind\":")?;
    sink.push_quoted(job.job_kind().as_tag())?;
    sink.push(b",\"preimage_bytes_len\":")?;
    sink.push_usize(job.preimage_bytes_len())?;
    sink.push(b",\"preimage_bytes_sha256\":")?;
    sink.push_digest(job.preimage_bytes_sha256())?;
    sink.push(b",\"signature_base64url\":")?;
    sink.push_quoted(job.signature_base64url())?;
    sink.push(b",\"signature_bytes_sha256\":")?;
    sink.push_digest(job.signature_bytes_sha256())?;
    sink.push(b",\"signed_material_bytes_len\":")?;
    sink.push_usize(job.signed_material_bytes_len())?;
    sink.push(b",\"signed_material_bytes_sha256\":")?;
    sink.push_digest(job.signed_material_bytes_sha256())?;
    sink.push(b",\"strict_verification_result\":true}")?;
    Ok(())
}

fn enforce_receipt_cap(length: usize) -> Result<(), VerificationErrorCodeV1> {
    if length > MAX_RECEIPT_BYTES {
        return Err(VerificationErrorCodeV1::ReceiptTooLarge);
    }
    Ok(())
}

struct ReceiptSink {
    bytes: Option<Vec<u8>>,
    length: usize,
}

impl ReceiptSink {
    const fn measuring() -> Self {
        Self {
            bytes: None,
            length: 0,
        }
    }

    fn writing(capacity: usize) -> Result<Self, VerificationErrorCodeV1> {
        let mut bytes = Vec::new();
        bytes
            .try_reserve_exact(capacity)
            .map_err(|_| VerificationErrorCodeV1::CapacityAllocationFailed)?;
        Ok(Self {
            bytes: Some(bytes),
            length: 0,
        })
    }

    const fn len(&self) -> usize {
        self.length
    }

    fn push(&mut self, value: &[u8]) -> Result<(), VerificationErrorCodeV1> {
        let next = self
            .length
            .checked_add(value.len())
            .ok_or(VerificationErrorCodeV1::LengthOverflow)?;
        if let Some(bytes) = self.bytes.as_mut() {
            if next > bytes.capacity() {
                return Err(VerificationErrorCodeV1::ReceiptEncodingInvariant);
            }
            bytes.extend_from_slice(value);
        }
        self.length = next;
        Ok(())
    }

    fn push_quoted(&mut self, value: &str) -> Result<(), VerificationErrorCodeV1> {
        self.push(b"\"")?;
        self.push(value.as_bytes())?;
        self.push(b"\"")
    }

    fn push_usize(&mut self, value: usize) -> Result<(), VerificationErrorCodeV1> {
        let value = u64::try_from(value).map_err(|_| VerificationErrorCodeV1::LengthOverflow)?;
        self.push_u64(value)
    }

    fn push_u64(&mut self, mut value: u64) -> Result<(), VerificationErrorCodeV1> {
        let mut buffer = [0_u8; 20];
        let mut cursor = buffer.len();
        loop {
            cursor -= 1;
            buffer[cursor] = b'0' + (value % 10) as u8;
            value /= 10;
            if value == 0 {
                break;
            }
        }
        self.push(&buffer[cursor..])
    }

    fn push_digest(&mut self, digest: &[u8; 32]) -> Result<(), VerificationErrorCodeV1> {
        const HEX: &[u8; 16] = b"0123456789abcdef";
        let mut encoded = [0_u8; 64];
        for (index, byte) in digest.iter().copied().enumerate() {
            encoded[index * 2] = HEX[usize::from(byte >> 4)];
            encoded[index * 2 + 1] = HEX[usize::from(byte & 0x0f)];
        }
        self.push(b"\"")?;
        self.push(&encoded)?;
        self.push(b"\"")
    }

    fn finish(mut self, expected_length: usize) -> Result<Vec<u8>, VerificationErrorCodeV1> {
        let bytes = self
            .bytes
            .take()
            .ok_or(VerificationErrorCodeV1::ReceiptEncodingInvariant)?;
        if self.length != expected_length
            || bytes.len() != expected_length
            || !bytes.iter().all(u8::is_ascii)
        {
            return Err(VerificationErrorCodeV1::ReceiptEncodingInvariant);
        }
        Ok(bytes)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const TEST_PUBLIC_KEY: &str = "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo";
    const TEST_MATERIAL: &[u8] = br#"{"request":"synthetic-v1"}"#;
    const TEST_SIGNATURE: &str =
        "vVpkt85syGv2bGscyIOg2C3WZCq09qATUnto_9fry7Z0keG38OLPH4UhCypATu_1hBR9QfRSuJbvVYRQGJ6BDg";

    fn test_input<'a>(jobs: &'a [SignatureJobInputV1<'a>]) -> PhaseVerificationInputV1<'a> {
        PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::RequestOnly,
            key_binding: crate::contract::KeyBindingInputV1 {
                issuer_id: "issuer.synthetic",
                key_id: "key.synthetic",
                usage: EXPECTED_USAGE,
                key_generation: 7,
                public_key_base64url: TEST_PUBLIC_KEY,
            },
            evidence_binding: crate::contract::EvidenceBindingInputV1 {
                trust_policy_id: "policy.synthetic",
                trust_policy_epoch: 11,
                trust_policy_snapshot_bytes: b"{}",
                key_status_overlay_bytes: b"{}",
                provider_evidence_digest_sha256:
                    "1111111111111111111111111111111111111111111111111111111111111111",
                adjudicated_at_claim: "2026-07-12T18:58:46.000000Z",
            },
            jobs,
        }
    }

    fn test_job(material: &[u8]) -> SignatureJobInputV1<'_> {
        SignatureJobInputV1 {
            role: SignatureRoleV1::Request,
            envelope_bytes: br#"{"envelope":"request-synthetic"}"#,
            signed_material_bytes: material,
            signature_base64url: TEST_SIGNATURE,
        }
    }

    #[test]
    fn checked_raw_slice_sum_overflow_precedes_cap() {
        assert_eq!(
            checked_raw_slice_sum([usize::MAX, 1]),
            Err(VerificationErrorCodeV1::LengthOverflow)
        );
        assert_eq!(
            checked_raw_slice_sum([MAX_AGGREGATE_INPUT_BYTES, 1]),
            Err(VerificationErrorCodeV1::AggregateInputTooLarge)
        );
    }

    #[test]
    fn preimage_checked_length_and_forced_allocation_errors_are_closed() {
        assert_eq!(
            checked_preimage_capacity(usize::MAX, 1),
            Err(VerificationErrorCodeV1::LengthOverflow)
        );
        let jobs = [test_job(TEST_MATERIAL)];
        assert_eq!(
            verify_unattested_phase_v1_with_faults(
                test_input(&jobs),
                VerificationFaultsV1::fail_allocation(AllocationSiteV1::Preimage(
                    SignatureRoleV1::Request,
                )),
            ),
            Err(VerificationErrorCodeV1::CapacityAllocationFailed)
        );
    }

    #[test]
    fn verified_job_and_receipt_forced_allocation_errors_are_closed() {
        let jobs = [test_job(TEST_MATERIAL)];
        for site in [
            AllocationSiteV1::VerifiedJobs,
            AllocationSiteV1::SignatureText(SignatureRoleV1::Request),
            AllocationSiteV1::ReceiptBytes,
        ] {
            assert_eq!(
                verify_unattested_phase_v1_with_faults(
                    test_input(&jobs),
                    VerificationFaultsV1::fail_allocation(site),
                ),
                Err(VerificationErrorCodeV1::CapacityAllocationFailed)
            );
        }
    }

    #[test]
    fn valid_strict_vectors_reach_forced_receipt_failures_only_after_crypto() {
        let valid_jobs = [test_job(TEST_MATERIAL)];
        for (faults, expected) in [
            (
                VerificationFaultsV1::force_receipt_invariant(),
                VerificationErrorCodeV1::ReceiptEncodingInvariant,
            ),
            (
                VerificationFaultsV1::force_receipt_cap(),
                VerificationErrorCodeV1::ReceiptTooLarge,
            ),
        ] {
            assert_eq!(
                verify_unattested_phase_v1_with_faults(test_input(&valid_jobs), faults),
                Err(expected)
            );
        }

        let invalid_jobs = [test_job(b"changed")];
        assert_eq!(
            verify_unattested_phase_v1_with_faults(
                test_input(&invalid_jobs),
                VerificationFaultsV1::force_receipt_invariant(),
            ),
            Err(VerificationErrorCodeV1::StrictSignatureInvalid(
                SignatureRoleV1::Request
            ))
        );
    }

    #[test]
    fn receipt_sink_precedence_and_exact_32768_byte_cap_are_closed() {
        let mut overflow = ReceiptSink {
            bytes: None,
            length: usize::MAX,
        };
        assert_eq!(
            overflow.push(b"x"),
            Err(VerificationErrorCodeV1::LengthOverflow)
        );

        let mut exact = ReceiptSink {
            bytes: None,
            length: MAX_RECEIPT_BYTES - 1,
        };
        assert_eq!(exact.push(b"x"), Ok(()));
        assert_eq!(exact.len(), 32_768);
        assert_eq!(enforce_receipt_cap(exact.len()), Ok(()));
        assert_eq!(exact.push(b"x"), Ok(()));
        assert_eq!(
            enforce_receipt_cap(exact.len()),
            Err(VerificationErrorCodeV1::ReceiptTooLarge)
        );

        assert!(matches!(
            ReceiptSink::writing(usize::MAX),
            Err(VerificationErrorCodeV1::CapacityAllocationFailed)
        ));
        let mut sink = ReceiptSink {
            bytes: Some(Vec::new()),
            length: 0,
        };
        assert_eq!(
            sink.push(b"x"),
            Err(VerificationErrorCodeV1::ReceiptEncodingInvariant)
        );

        let jobs = [test_job(TEST_MATERIAL)];
        assert_eq!(
            verify_unattested_phase_v1_with_faults(
                test_input(&jobs),
                VerificationFaultsV1 {
                    allocation_failure: Some(AllocationSiteV1::ReceiptBytes),
                    force_receipt_invariant: true,
                    force_receipt_cap: true,
                },
            ),
            Err(VerificationErrorCodeV1::CapacityAllocationFailed)
        );
        assert_eq!(
            verify_unattested_phase_v1_with_faults(
                test_input(&jobs),
                VerificationFaultsV1 {
                    allocation_failure: None,
                    force_receipt_invariant: true,
                    force_receipt_cap: true,
                },
            ),
            Err(VerificationErrorCodeV1::ReceiptEncodingInvariant)
        );
    }
}
