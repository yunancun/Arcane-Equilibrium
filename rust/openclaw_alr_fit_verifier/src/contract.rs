use core::fmt;

/// The closed verification phase declared by the caller.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum VerificationPhaseV1 {
    RequestOnly,
    SignedStatus,
    TerminalSuccess,
    TerminalNoInner,
}

impl VerificationPhaseV1 {
    pub(crate) const fn as_tag(self) -> &'static str {
        match self {
            Self::RequestOnly => "REQUEST_ONLY",
            Self::SignedStatus => "SIGNED_STATUS",
            Self::TerminalSuccess => "TERMINAL_SUCCESS",
            Self::TerminalNoInner => "TERMINAL_NO_INNER",
        }
    }
}

/// The closed role of one signature job within a declared phase.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SignatureRoleV1 {
    Request,
    SignedStatus,
    OuterTerminal,
    V159Inner,
}

impl SignatureRoleV1 {
    pub(crate) const fn as_tag(self) -> &'static str {
        match self {
            Self::Request => "REQUEST",
            Self::SignedStatus => "SIGNED_STATUS",
            Self::OuterTerminal => "OUTER_TERMINAL",
            Self::V159Inner => "V159_INNER",
        }
    }

    pub(crate) const fn domain(self) -> &'static str {
        match self {
            Self::Request => "ALR_TRUSTED_FIT_REQUEST_V1",
            Self::SignedStatus | Self::OuterTerminal => "ALR_ISOLATED_FIT_TERMINAL_RECEIPT_V1",
            Self::V159Inner => "ALR_V159_INNER_FIT_RECEIPT_V1",
        }
    }
}

impl fmt::Display for SignatureRoleV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_tag())
    }
}

/// A metadata field whose closed validation contract failed.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum MetadataFieldV1 {
    IssuerId,
    KeyId,
    Usage,
    KeyGeneration,
    TrustPolicyId,
    TrustPolicyEpoch,
    ProviderEvidenceDigestSha256,
    AdjudicatedAtClaim,
}

impl MetadataFieldV1 {
    const fn as_tag(self) -> &'static str {
        match self {
            Self::IssuerId => "ISSUER_ID",
            Self::KeyId => "KEY_ID",
            Self::Usage => "USAGE",
            Self::KeyGeneration => "KEY_GENERATION",
            Self::TrustPolicyId => "TRUST_POLICY_ID",
            Self::TrustPolicyEpoch => "TRUST_POLICY_EPOCH",
            Self::ProviderEvidenceDigestSha256 => "PROVIDER_EVIDENCE_DIGEST_SHA256",
            Self::AdjudicatedAtClaim => "ADJUDICATED_AT_CLAIM",
        }
    }
}

impl fmt::Display for MetadataFieldV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_tag())
    }
}

/// A byte field whose closed length contract failed.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum BytesFieldV1 {
    TrustPolicySnapshot,
    KeyStatusOverlay,
    RequestEnvelope,
    RequestSignedMaterial,
    SignedStatusEnvelope,
    SignedStatusSignedMaterial,
    OuterTerminalEnvelope,
    OuterTerminalSignedMaterial,
    V159InnerEnvelope,
    V159InnerSignedMaterial,
}

impl fmt::Display for BytesFieldV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::TrustPolicySnapshot => formatter.write_str("TRUST_POLICY_SNAPSHOT"),
            Self::KeyStatusOverlay => formatter.write_str("KEY_STATUS_OVERLAY"),
            Self::RequestEnvelope => formatter.write_str("REQUEST_ENVELOPE"),
            Self::RequestSignedMaterial => formatter.write_str("REQUEST_SIGNED_MATERIAL"),
            Self::SignedStatusEnvelope => formatter.write_str("SIGNED_STATUS_ENVELOPE"),
            Self::SignedStatusSignedMaterial => {
                formatter.write_str("SIGNED_STATUS_SIGNED_MATERIAL")
            }
            Self::OuterTerminalEnvelope => formatter.write_str("OUTER_TERMINAL_ENVELOPE"),
            Self::OuterTerminalSignedMaterial => {
                formatter.write_str("OUTER_TERMINAL_SIGNED_MATERIAL")
            }
            Self::V159InnerEnvelope => formatter.write_str("V159_INNER_ENVELOPE"),
            Self::V159InnerSignedMaterial => formatter.write_str("V159_INNER_SIGNED_MATERIAL"),
        }
    }
}

/// Exhaustive closed error codes for the V1 verifier.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum VerificationErrorCodeV1 {
    PhaseShapeInvalid,
    LengthOverflow,
    AggregateInputTooLarge,
    MetadataInvalid(MetadataFieldV1),
    BytesLengthInvalid(BytesFieldV1),
    PublicKeyBase64UrlInvalid,
    PublicKeyPointInvalid,
    SignatureBase64UrlInvalid(SignatureRoleV1),
    StrictSignatureInvalid(SignatureRoleV1),
    CapacityAllocationFailed,
    ReceiptEncodingInvariant,
    ReceiptTooLarge,
}

impl fmt::Display for VerificationErrorCodeV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::PhaseShapeInvalid => formatter.write_str("PHASE_SHAPE_INVALID"),
            Self::LengthOverflow => formatter.write_str("LENGTH_OVERFLOW"),
            Self::AggregateInputTooLarge => formatter.write_str("AGGREGATE_INPUT_TOO_LARGE"),
            Self::MetadataInvalid(field) => {
                write!(formatter, "METADATA_INVALID:{}", field.as_tag())
            }
            Self::BytesLengthInvalid(field) => {
                write!(formatter, "BYTES_LENGTH_INVALID:{field}")
            }
            Self::PublicKeyBase64UrlInvalid => formatter.write_str("PUBLIC_KEY_BASE64URL_INVALID"),
            Self::PublicKeyPointInvalid => formatter.write_str("PUBLIC_KEY_POINT_INVALID"),
            Self::SignatureBase64UrlInvalid(role) => {
                write!(formatter, "SIGNATURE_BASE64URL_INVALID:{role}")
            }
            Self::StrictSignatureInvalid(role) => {
                write!(formatter, "STRICT_SIGNATURE_INVALID:{role}")
            }
            Self::CapacityAllocationFailed => formatter.write_str("CAPACITY_ALLOCATION_FAILED"),
            Self::ReceiptEncodingInvariant => formatter.write_str("RECEIPT_ENCODING_INVARIANT"),
            Self::ReceiptTooLarge => formatter.write_str("RECEIPT_TOO_LARGE"),
        }
    }
}

impl std::error::Error for VerificationErrorCodeV1 {}

/// Borrowed public-key identity and usage binding.
#[derive(Clone, Copy, Eq, PartialEq)]
pub struct KeyBindingInputV1<'a> {
    pub issuer_id: &'a str,
    pub key_id: &'a str,
    pub usage: &'a str,
    pub key_generation: u64,
    pub public_key_base64url: &'a str,
}

impl fmt::Debug for KeyBindingInputV1<'_> {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("KeyBindingInputV1")
            .field("issuer_id", &"<redacted>")
            .field("key_id", &"<redacted>")
            .field("usage", &"<redacted>")
            .field("key_generation", &"<redacted>")
            .field("public_key_base64url", &"<redacted>")
            .finish()
    }
}

/// Borrowed trust-policy and adjudication identity binding.
#[derive(Clone, Copy, Eq, PartialEq)]
pub struct EvidenceBindingInputV1<'a> {
    pub trust_policy_id: &'a str,
    pub trust_policy_epoch: u64,
    pub trust_policy_snapshot_bytes: &'a [u8],
    pub key_status_overlay_bytes: &'a [u8],
    pub provider_evidence_digest_sha256: &'a str,
    pub adjudicated_at_claim: &'a str,
}

impl fmt::Debug for EvidenceBindingInputV1<'_> {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("EvidenceBindingInputV1")
            .field("trust_policy_id", &"<redacted>")
            .field("trust_policy_epoch", &"<redacted>")
            .field(
                "trust_policy_snapshot_bytes_len",
                &self.trust_policy_snapshot_bytes.len(),
            )
            .field(
                "key_status_overlay_bytes_len",
                &self.key_status_overlay_bytes.len(),
            )
            .field("provider_evidence_digest_sha256", &"<redacted>")
            .field("adjudicated_at_claim", &"<redacted>")
            .finish()
    }
}

/// One exact ordered borrowed signature job.
#[derive(Clone, Copy, Eq, PartialEq)]
pub struct SignatureJobInputV1<'a> {
    pub role: SignatureRoleV1,
    pub envelope_bytes: &'a [u8],
    pub signed_material_bytes: &'a [u8],
    pub signature_base64url: &'a str,
}

impl fmt::Debug for SignatureJobInputV1<'_> {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("SignatureJobInputV1")
            .field("role", &self.role)
            .field("envelope_bytes_len", &self.envelope_bytes.len())
            .field(
                "signed_material_bytes_len",
                &self.signed_material_bytes.len(),
            )
            .field("signature_base64url", &"<redacted>")
            .finish()
    }
}

/// Complete input to the single V1 public verification Interface.
#[derive(Clone, Copy, Eq, PartialEq)]
pub struct PhaseVerificationInputV1<'a> {
    pub declared_phase: VerificationPhaseV1,
    pub key_binding: KeyBindingInputV1<'a>,
    pub evidence_binding: EvidenceBindingInputV1<'a>,
    pub jobs: &'a [SignatureJobInputV1<'a>],
}

impl fmt::Debug for PhaseVerificationInputV1<'_> {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("PhaseVerificationInputV1")
            .field("declared_phase", &self.declared_phase)
            .field("key_binding", &self.key_binding)
            .field("evidence_binding", &self.evidence_binding)
            .field("jobs_len", &self.jobs.len())
            .field("jobs", &"<redacted>")
            .finish()
    }
}

/// One strictly verified signature job owned by a successful receipt.
#[derive(Eq, PartialEq)]
pub struct VerifiedSignatureJobV1 {
    job_kind: SignatureRoleV1,
    envelope_bytes_len: usize,
    envelope_bytes_sha256: [u8; 32],
    signed_material_bytes_len: usize,
    signed_material_bytes_sha256: [u8; 32],
    preimage_bytes_len: usize,
    preimage_bytes_sha256: [u8; 32],
    signature_base64url: String,
    signature_bytes_sha256: [u8; 32],
}

impl VerifiedSignatureJobV1 {
    #[allow(clippy::too_many_arguments)]
    pub(crate) fn from_verified_parts(
        job_kind: SignatureRoleV1,
        envelope_bytes_len: usize,
        envelope_bytes_sha256: [u8; 32],
        signed_material_bytes_len: usize,
        signed_material_bytes_sha256: [u8; 32],
        preimage_bytes_len: usize,
        preimage_bytes_sha256: [u8; 32],
        signature_base64url: String,
        signature_bytes_sha256: [u8; 32],
    ) -> Self {
        Self {
            job_kind,
            envelope_bytes_len,
            envelope_bytes_sha256,
            signed_material_bytes_len,
            signed_material_bytes_sha256,
            preimage_bytes_len,
            preimage_bytes_sha256,
            signature_base64url,
            signature_bytes_sha256,
        }
    }

    pub const fn job_kind(&self) -> SignatureRoleV1 {
        self.job_kind
    }

    pub const fn domain(&self) -> &'static str {
        self.job_kind.domain()
    }

    pub const fn envelope_bytes_len(&self) -> usize {
        self.envelope_bytes_len
    }

    pub const fn envelope_bytes_sha256(&self) -> &[u8; 32] {
        &self.envelope_bytes_sha256
    }

    pub const fn signed_material_bytes_len(&self) -> usize {
        self.signed_material_bytes_len
    }

    pub const fn signed_material_bytes_sha256(&self) -> &[u8; 32] {
        &self.signed_material_bytes_sha256
    }

    pub const fn preimage_bytes_len(&self) -> usize {
        self.preimage_bytes_len
    }

    pub const fn preimage_bytes_sha256(&self) -> &[u8; 32] {
        &self.preimage_bytes_sha256
    }

    pub fn signature_base64url(&self) -> &str {
        &self.signature_base64url
    }

    pub const fn signature_bytes_sha256(&self) -> &[u8; 32] {
        &self.signature_bytes_sha256
    }

    pub const fn strict_verification_result(&self) -> bool {
        true
    }
}

impl fmt::Debug for VerifiedSignatureJobV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("VerifiedSignatureJobV1")
            .field("job_kind", &self.job_kind)
            .field("envelope_bytes_len", &self.envelope_bytes_len)
            .field("signed_material_bytes_len", &self.signed_material_bytes_len)
            .field("preimage_bytes_len", &self.preimage_bytes_len)
            .field("signature_base64url", &"<redacted>")
            .finish()
    }
}

/// Deterministic canonical receipt owned by a successful source-only check.
#[derive(Eq, PartialEq)]
pub struct UnattestedVerificationReceiptV1 {
    declared_phase: VerificationPhaseV1,
    jobs: Vec<VerifiedSignatureJobV1>,
    canonical_bytes: Vec<u8>,
    receipt_sha256: [u8; 32],
}

impl UnattestedVerificationReceiptV1 {
    pub(crate) fn from_verified_parts(
        declared_phase: VerificationPhaseV1,
        jobs: Vec<VerifiedSignatureJobV1>,
        canonical_bytes: Vec<u8>,
        receipt_sha256: [u8; 32],
    ) -> Self {
        Self {
            declared_phase,
            jobs,
            canonical_bytes,
            receipt_sha256,
        }
    }

    pub const fn declared_phase(&self) -> VerificationPhaseV1 {
        self.declared_phase
    }

    pub fn jobs(&self) -> &[VerifiedSignatureJobV1] {
        &self.jobs
    }

    pub fn job_count(&self) -> usize {
        self.jobs.len()
    }

    pub fn canonical_bytes(&self) -> &[u8] {
        &self.canonical_bytes
    }

    pub fn receipt_bytes_len(&self) -> usize {
        self.canonical_bytes.len()
    }

    pub fn receipt_sha256(&self) -> &[u8; 32] {
        &self.receipt_sha256
    }
}

impl fmt::Debug for UnattestedVerificationReceiptV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("UnattestedVerificationReceiptV1")
            .field("declared_phase", &self.declared_phase)
            .field("job_count", &self.jobs.len())
            .field("receipt_bytes_len", &self.canonical_bytes.len())
            .field("receipt_sha256", &DigestDebug(&self.receipt_sha256))
            .finish()
    }
}

/// Successful source-only output with no caller-forgeable success fields.
#[derive(Eq, PartialEq)]
pub struct UnattestedVerificationOutputV1 {
    receipt: UnattestedVerificationReceiptV1,
}

impl UnattestedVerificationOutputV1 {
    pub(crate) fn from_receipt(receipt: UnattestedVerificationReceiptV1) -> Self {
        Self { receipt }
    }

    pub fn canonical_bytes(&self) -> &[u8] {
        self.receipt.canonical_bytes()
    }

    pub fn receipt_sha256(&self) -> &[u8; 32] {
        self.receipt.receipt_sha256()
    }

    pub fn receipt(&self) -> &UnattestedVerificationReceiptV1 {
        &self.receipt
    }
}

impl fmt::Debug for UnattestedVerificationOutputV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("UnattestedVerificationOutputV1")
            .field("declared_phase", &self.receipt.declared_phase())
            .field("job_count", &self.receipt.job_count())
            .field("receipt_bytes_len", &self.receipt.receipt_bytes_len())
            .field(
                "receipt_sha256",
                &DigestDebug(self.receipt.receipt_sha256()),
            )
            .finish()
    }
}

struct DigestDebug<'a>(&'a [u8; 32]);

impl fmt::Debug for DigestDebug<'_> {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        for byte in self.0 {
            write!(formatter, "{byte:02x}")?;
        }
        Ok(())
    }
}
