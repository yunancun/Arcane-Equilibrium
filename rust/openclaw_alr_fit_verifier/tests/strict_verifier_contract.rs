use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use ed25519_dalek::{Signature, VerifyingKey};
use openclaw_alr_fit_verifier::{
    verify_unattested_phase_v1, BytesFieldV1, EvidenceBindingInputV1, KeyBindingInputV1,
    MetadataFieldV1, PhaseVerificationInputV1, SignatureJobInputV1, SignatureRoleV1,
    UnattestedVerificationOutputV1, UnattestedVerificationReceiptV1, VerificationErrorCodeV1,
    VerificationPhaseV1, VerifiedSignatureJobV1,
};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::panic::{catch_unwind, AssertUnwindSafe};

// Public synthetic vectors only. Generation uses RFC 8032 test-vector-1 seed
// 9d61...7f60 wrapped as RFC 8410 PKCS#8 DER, then OpenSSL 3.6.3:
//   openssl pkeyutl -sign -rawin -keyform DER -inkey <key.der> -in <preimage>
// Preimage is domain || NUL || u64be(len(material)) || material. The private
// seed is never a repository dependency or runtime key.
const PUBLIC_KEY: &str = "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo";
const REQUEST_MATERIAL: &[u8] = br#"{"request":"synthetic-v1"}"#;
const STATUS_MATERIAL: &[u8] = br#"{"response_kind":"STATUS","status_generation":1}"#;
const OUTER_MATERIAL: &[u8] = br#"{"outcome":"SUCCEEDED","response_kind":"TERMINAL"}"#;
const INNER_MATERIAL: &[u8] =
    br#"{"schema_version":"alr_challenger_fit_receipt_v1","status":"SUCCEEDED"}"#;

const REQUEST_SIGNATURE: &str =
    "vVpkt85syGv2bGscyIOg2C3WZCq09qATUnto_9fry7Z0keG38OLPH4UhCypATu_1hBR9QfRSuJbvVYRQGJ6BDg";
const STATUS_SIGNATURE: &str =
    "u6A14q4cGnURiA3jfPZqHPTyKVDu6drPf_7NHWw9WcoDYFBh8Pf0h1Ne2VRoNq7Az94UvEgTQIDtI7d7Z2CIAA";
const OUTER_SIGNATURE: &str =
    "GqCP4olvalDy64ZstHCbTpPkC17i5orYcTpRPmLIXIPUOxMKDnJPKu1f7GgscFU0M7Bo7gEDl50LZdV3_IZbDQ";
const INNER_SIGNATURE: &str =
    "zbeiHo9vHFpyIgzkU14LuqsRuoc9YG7eL1Ra5ge-D5XVmFyBmZZf1xzPj_VD0a_mdODF6SysjhXL82EwxGXVAA";

const REQUEST_SCALAR_PLUS_L_SIGNATURE: &str =
    "vVpkt85syGv2bGscyIOg2C3WZCq09qATUnto_9fry7ZhZdcUC0bid1u-As0eSM4KhRR9QfRSuJbvVYRQGJ6BHg";
const REQUEST_POINT_SIGN_FLIP_SIGNATURE: &str =
    "vVpkt85syGv2bGscyIOg2C3WZCq09qATUnto_9fryzZ0keG38OLPH4UhCypATu_1hBR9QfRSuJbvVYRQGJ6BDg";
const ZERO_KEY: &str = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
const IDENTITY_KEY: &str = "AQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
const NONCANONICAL_POINT_KEY: &str = "AgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
const ZERO_SIGNATURE: &str =
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";

const REQUEST_ENVELOPE: &[u8] = br#"{"envelope":"request-synthetic"}"#;
const STATUS_ENVELOPE: &[u8] = br#"{"envelope":"status-synthetic"}"#;
const OUTER_ENVELOPE: &[u8] = br#"{"envelope":"outer-synthetic"}"#;
const INNER_ENVELOPE: &[u8] = br#"{"envelope":"inner-synthetic"}"#;
const POLICY_BYTES: &[u8] = br#"{}"#;
const OVERLAY_BYTES: &[u8] = br#"{}"#;
const PROVIDER_DIGEST: &str = "1111111111111111111111111111111111111111111111111111111111111111";
const ADJUDICATED_AT: &str = "2026-07-12T18:58:46.000000Z";

const TOP_KEYS: &[&str] = &[
    "algorithm",
    "authority_counters",
    "authority_granted",
    "canonical_input_bytes_established",
    "capability_authenticity",
    "coordinator_eligible",
    "declared_phase",
    "durable_consumption_established",
    "envelope_payload_binding_established",
    "evidence_binding",
    "jobs",
    "model_training_performed_claim",
    "no_authority",
    "persistence_allowed",
    "platform_attested",
    "policy_overlay_adjudication_established",
    "schema_version",
    "semantic_phase_established",
    "signatures_valid",
    "training_allowed",
    "trusted_time_established",
    "verdict",
    "verification_primitive",
];

const EVIDENCE_KEYS: &[&str] = &[
    "adjudicated_at_claim",
    "issuer_id",
    "key_generation",
    "key_id",
    "key_status_overlay_bytes_len",
    "key_status_overlay_bytes_sha256",
    "provider_evidence_digest_sha256",
    "public_key_base64url",
    "public_key_bytes_sha256",
    "trust_policy_epoch",
    "trust_policy_id",
    "trust_policy_snapshot_bytes_len",
    "trust_policy_snapshot_bytes_sha256",
    "usage",
];

const JOB_KEYS: &[&str] = &[
    "domain",
    "envelope_bytes_len",
    "envelope_bytes_sha256",
    "job_kind",
    "preimage_bytes_len",
    "preimage_bytes_sha256",
    "signature_base64url",
    "signature_bytes_sha256",
    "signed_material_bytes_len",
    "signed_material_bytes_sha256",
    "strict_verification_result",
];

const NO_AUTHORITY_KEYS: &[&str] = &[
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

const AUTHORITY_COUNTER_KEYS: &[&str] = &[
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

fn key() -> KeyBindingInputV1<'static> {
    key_with("issuer.synthetic", "key.synthetic", 7, PUBLIC_KEY)
}

fn key_with<'a>(
    issuer_id: &'a str,
    key_id: &'a str,
    key_generation: u64,
    public_key_base64url: &'a str,
) -> KeyBindingInputV1<'a> {
    KeyBindingInputV1 {
        issuer_id,
        key_id,
        usage: "ALR_TRUSTED_FIT_HANDSHAKE_SIGNING",
        key_generation,
        public_key_base64url,
    }
}

fn evidence() -> EvidenceBindingInputV1<'static> {
    evidence_with(
        "policy.synthetic",
        11,
        POLICY_BYTES,
        OVERLAY_BYTES,
        PROVIDER_DIGEST,
        ADJUDICATED_AT,
    )
}

fn evidence_with<'a>(
    trust_policy_id: &'a str,
    trust_policy_epoch: u64,
    trust_policy_snapshot_bytes: &'a [u8],
    key_status_overlay_bytes: &'a [u8],
    provider_evidence_digest_sha256: &'a str,
    adjudicated_at_claim: &'a str,
) -> EvidenceBindingInputV1<'a> {
    EvidenceBindingInputV1 {
        trust_policy_id,
        trust_policy_epoch,
        trust_policy_snapshot_bytes,
        key_status_overlay_bytes,
        provider_evidence_digest_sha256,
        adjudicated_at_claim,
    }
}

fn request_job() -> SignatureJobInputV1<'static> {
    SignatureJobInputV1 {
        role: SignatureRoleV1::Request,
        envelope_bytes: REQUEST_ENVELOPE,
        signed_material_bytes: REQUEST_MATERIAL,
        signature_base64url: REQUEST_SIGNATURE,
    }
}

fn status_job() -> SignatureJobInputV1<'static> {
    SignatureJobInputV1 {
        role: SignatureRoleV1::SignedStatus,
        envelope_bytes: STATUS_ENVELOPE,
        signed_material_bytes: STATUS_MATERIAL,
        signature_base64url: STATUS_SIGNATURE,
    }
}

fn outer_job() -> SignatureJobInputV1<'static> {
    SignatureJobInputV1 {
        role: SignatureRoleV1::OuterTerminal,
        envelope_bytes: OUTER_ENVELOPE,
        signed_material_bytes: OUTER_MATERIAL,
        signature_base64url: OUTER_SIGNATURE,
    }
}

fn inner_job() -> SignatureJobInputV1<'static> {
    SignatureJobInputV1 {
        role: SignatureRoleV1::V159Inner,
        envelope_bytes: INNER_ENVELOPE,
        signed_material_bytes: INNER_MATERIAL,
        signature_base64url: INNER_SIGNATURE,
    }
}

fn jobs_for(phase: VerificationPhaseV1) -> Vec<SignatureJobInputV1<'static>> {
    match phase {
        VerificationPhaseV1::RequestOnly => vec![request_job()],
        VerificationPhaseV1::SignedStatus => vec![request_job(), status_job()],
        VerificationPhaseV1::TerminalSuccess => {
            vec![request_job(), outer_job(), inner_job()]
        }
        VerificationPhaseV1::TerminalNoInner => vec![request_job(), outer_job()],
    }
}

fn role_job_with<'a>(
    role: SignatureRoleV1,
    envelope_bytes: &'a [u8],
    signed_material_bytes: &'a [u8],
) -> SignatureJobInputV1<'a> {
    let signature_base64url = match role {
        SignatureRoleV1::Request => REQUEST_SIGNATURE,
        SignatureRoleV1::SignedStatus => STATUS_SIGNATURE,
        SignatureRoleV1::OuterTerminal => OUTER_SIGNATURE,
        SignatureRoleV1::V159Inner => INNER_SIGNATURE,
    };
    SignatureJobInputV1 {
        role,
        envelope_bytes,
        signed_material_bytes,
        signature_base64url,
    }
}

fn verify_role_bytes(
    role: SignatureRoleV1,
    envelope_bytes: &[u8],
    signed_material_bytes: &[u8],
) -> Result<UnattestedVerificationOutputV1, VerificationErrorCodeV1> {
    let changed = role_job_with(role, envelope_bytes, signed_material_bytes);
    let (phase, jobs) = match role {
        SignatureRoleV1::Request => (VerificationPhaseV1::RequestOnly, vec![changed]),
        SignatureRoleV1::SignedStatus => (
            VerificationPhaseV1::SignedStatus,
            vec![request_job(), changed],
        ),
        SignatureRoleV1::OuterTerminal => (
            VerificationPhaseV1::TerminalNoInner,
            vec![request_job(), changed],
        ),
        SignatureRoleV1::V159Inner => (
            VerificationPhaseV1::TerminalSuccess,
            vec![request_job(), outer_job(), changed],
        ),
    };
    verify_unattested_phase_v1(PhaseVerificationInputV1 {
        declared_phase: phase,
        key_binding: key(),
        evidence_binding: evidence(),
        jobs: &jobs,
    })
}

fn verify_evidence_bytes(
    policy: &[u8],
    overlay: &[u8],
) -> Result<UnattestedVerificationOutputV1, VerificationErrorCodeV1> {
    let jobs = [request_job()];
    verify_unattested_phase_v1(PhaseVerificationInputV1 {
        declared_phase: VerificationPhaseV1::RequestOnly,
        key_binding: key(),
        evidence_binding: evidence_with(
            "policy.synthetic",
            11,
            policy,
            overlay,
            PROVIDER_DIGEST,
            ADJUDICATED_AT,
        ),
        jobs: &jobs,
    })
}

fn verify_identifier_field(
    field: MetadataFieldV1,
    value: &str,
) -> Result<UnattestedVerificationOutputV1, VerificationErrorCodeV1> {
    let jobs = [request_job()];
    let key_binding = match field {
        MetadataFieldV1::IssuerId => key_with(value, "key.synthetic", 7, PUBLIC_KEY),
        MetadataFieldV1::KeyId => key_with("issuer.synthetic", value, 7, PUBLIC_KEY),
        MetadataFieldV1::TrustPolicyId => key(),
        _ => unreachable!("identifier helper accepts only identifier fields"),
    };
    let evidence_binding = if field == MetadataFieldV1::TrustPolicyId {
        evidence_with(
            value,
            11,
            POLICY_BYTES,
            OVERLAY_BYTES,
            PROVIDER_DIGEST,
            ADJUDICATED_AT,
        )
    } else {
        evidence()
    };
    verify_unattested_phase_v1(PhaseVerificationInputV1 {
        declared_phase: VerificationPhaseV1::RequestOnly,
        key_binding,
        evidence_binding,
        jobs: &jobs,
    })
}

fn verify_phase(
    phase: VerificationPhaseV1,
) -> openclaw_alr_fit_verifier::UnattestedVerificationOutputV1 {
    let jobs = jobs_for(phase);
    verify_unattested_phase_v1(PhaseVerificationInputV1 {
        declared_phase: phase,
        key_binding: key(),
        evidence_binding: evidence(),
        jobs: &jobs,
    })
    .expect("synthetic strict vector must verify")
}

fn object_keys(value: &Value) -> Vec<&str> {
    value
        .as_object()
        .expect("object")
        .keys()
        .map(String::as_str)
        .collect()
}

#[derive(Debug, Eq, PartialEq)]
struct OracleEvidence {
    adjudicated_at_claim: String,
    issuer_id: String,
    key_generation: u64,
    key_id: String,
    key_status_overlay_bytes_len: u64,
    key_status_overlay_bytes_sha256: String,
    provider_evidence_digest_sha256: String,
    public_key_base64url: String,
    public_key_bytes_sha256: String,
    trust_policy_epoch: u64,
    trust_policy_id: String,
    trust_policy_snapshot_bytes_len: u64,
    trust_policy_snapshot_bytes_sha256: String,
    usage: String,
}

#[derive(Debug, Eq, PartialEq)]
struct OracleJob {
    domain: String,
    envelope_bytes_len: u64,
    envelope_bytes_sha256: String,
    job_kind: String,
    preimage_bytes_len: u64,
    preimage_bytes_sha256: String,
    signature_base64url: String,
    signature_bytes_sha256: String,
    signed_material_bytes_len: u64,
    signed_material_bytes_sha256: String,
}

#[derive(Debug, Eq, PartialEq)]
struct OracleReceipt {
    declared_phase: String,
    evidence: OracleEvidence,
    jobs: Vec<OracleJob>,
}

fn oracle_safe_string(value: &str) -> bool {
    value.is_ascii()
        && !value
            .as_bytes()
            .iter()
            .any(|byte| *byte < 0x20 || matches!(*byte, b'"' | b'\\'))
}

fn oracle_string(object: &Map<String, Value>, key: &str) -> Option<String> {
    let value = object.get(key)?.as_str()?;
    oracle_safe_string(value).then(|| value.to_owned())
}

fn oracle_u64(object: &Map<String, Value>, key: &str) -> Option<u64> {
    let value = object.get(key)?;
    if value.is_boolean() {
        None
    } else {
        value.as_u64()
    }
}

fn oracle_hex64(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn oracle_public_key_base64url(value: &str) -> bool {
    if value.len() != 43 {
        return false;
    }
    let mut decoded = [0_u8; 32];
    let mut encoded = [0_u8; 43];
    URL_SAFE_NO_PAD.decode_slice(value, &mut decoded) == Ok(32)
        && URL_SAFE_NO_PAD.encode_slice(decoded, &mut encoded) == Ok(43)
        && encoded.as_slice() == value.as_bytes()
}

fn oracle_signature_base64url(value: &str) -> bool {
    if value.len() != 86 {
        return false;
    }
    let mut decoded = [0_u8; 64];
    let mut encoded = [0_u8; 86];
    URL_SAFE_NO_PAD.decode_slice(value, &mut decoded) == Ok(64)
        && URL_SAFE_NO_PAD.encode_slice(decoded, &mut encoded) == Ok(86)
        && encoded.as_slice() == value.as_bytes()
}

fn oracle_identifier(value: &str) -> bool {
    let bytes = value.as_bytes();
    if bytes.is_empty()
        || bytes.len() > 128
        || !(bytes[0].is_ascii_lowercase() || bytes[0].is_ascii_digit())
    {
        return false;
    }
    bytes.iter().all(|byte| {
        byte.is_ascii_lowercase()
            || byte.is_ascii_digit()
            || matches!(*byte, b'_' | b'.' | b':' | b'-')
    })
}

fn oracle_decimal(bytes: &[u8]) -> Option<u32> {
    bytes.iter().try_fold(0_u32, |value, byte| {
        byte.is_ascii_digit()
            .then(|| value * 10 + u32::from(*byte - b'0'))
    })
}

fn oracle_timestamp(value: &str) -> bool {
    let bytes = value.as_bytes();
    if bytes.len() != 27
        || bytes[4] != b'-'
        || bytes[7] != b'-'
        || bytes[10] != b'T'
        || bytes[13] != b':'
        || bytes[16] != b':'
        || bytes[19] != b'.'
        || bytes[26] != b'Z'
        || !bytes[20..26].iter().all(u8::is_ascii_digit)
    {
        return false;
    }
    let Some(year) = oracle_decimal(&bytes[0..4]) else {
        return false;
    };
    let Some(month) = oracle_decimal(&bytes[5..7]) else {
        return false;
    };
    let Some(day) = oracle_decimal(&bytes[8..10]) else {
        return false;
    };
    let Some(hour) = oracle_decimal(&bytes[11..13]) else {
        return false;
    };
    let Some(minute) = oracle_decimal(&bytes[14..16]) else {
        return false;
    };
    let Some(second) = oracle_decimal(&bytes[17..19]) else {
        return false;
    };
    if year == 0 || !(1..=12).contains(&month) || hour > 23 || minute > 59 || second > 59 {
        return false;
    }
    let leap_year = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    let maximum_day = match month {
        2 if leap_year => 29,
        2 => 28,
        4 | 6 | 9 | 11 => 30,
        _ => 31,
    };
    (1..=maximum_day).contains(&day)
}

fn oracle_literal_string(object: &Map<String, Value>, key: &str, expected: &str) -> bool {
    object.get(key).and_then(Value::as_str) == Some(expected)
}

fn oracle_literal_bool(object: &Map<String, Value>, key: &str, expected: bool) -> bool {
    object.get(key).and_then(Value::as_bool) == Some(expected)
}

fn oracle_decode_evidence(value: &Value) -> Option<OracleEvidence> {
    let object = value.as_object()?;
    (object.keys().map(String::as_str).collect::<Vec<_>>() == EVIDENCE_KEYS).then_some(())?;
    let evidence = OracleEvidence {
        adjudicated_at_claim: oracle_string(object, "adjudicated_at_claim")?,
        issuer_id: oracle_string(object, "issuer_id")?,
        key_generation: oracle_u64(object, "key_generation")?,
        key_id: oracle_string(object, "key_id")?,
        key_status_overlay_bytes_len: oracle_u64(object, "key_status_overlay_bytes_len")?,
        key_status_overlay_bytes_sha256: oracle_string(object, "key_status_overlay_bytes_sha256")?,
        provider_evidence_digest_sha256: oracle_string(object, "provider_evidence_digest_sha256")?,
        public_key_base64url: oracle_string(object, "public_key_base64url")?,
        public_key_bytes_sha256: oracle_string(object, "public_key_bytes_sha256")?,
        trust_policy_epoch: oracle_u64(object, "trust_policy_epoch")?,
        trust_policy_id: oracle_string(object, "trust_policy_id")?,
        trust_policy_snapshot_bytes_len: oracle_u64(object, "trust_policy_snapshot_bytes_len")?,
        trust_policy_snapshot_bytes_sha256: oracle_string(
            object,
            "trust_policy_snapshot_bytes_sha256",
        )?,
        usage: oracle_string(object, "usage")?,
    };
    for digest in [
        &evidence.key_status_overlay_bytes_sha256,
        &evidence.provider_evidence_digest_sha256,
        &evidence.public_key_bytes_sha256,
        &evidence.trust_policy_snapshot_bytes_sha256,
    ] {
        oracle_hex64(digest).then_some(())?;
    }
    oracle_identifier(&evidence.issuer_id).then_some(())?;
    oracle_identifier(&evidence.key_id).then_some(())?;
    oracle_identifier(&evidence.trust_policy_id).then_some(())?;
    (evidence.usage == "ALR_TRUSTED_FIT_HANDSHAKE_SIGNING").then_some(())?;
    (1..=9_223_372_036_854_775_807)
        .contains(&evidence.key_generation)
        .then_some(())?;
    (1..=9_223_372_036_854_775_807)
        .contains(&evidence.trust_policy_epoch)
        .then_some(())?;
    (2..=1_048_576)
        .contains(&evidence.key_status_overlay_bytes_len)
        .then_some(())?;
    (2..=1_048_576)
        .contains(&evidence.trust_policy_snapshot_bytes_len)
        .then_some(())?;
    oracle_timestamp(&evidence.adjudicated_at_claim).then_some(())?;
    oracle_public_key_base64url(&evidence.public_key_base64url).then_some(())?;
    Some(evidence)
}

fn oracle_decode_job(value: &Value) -> Option<OracleJob> {
    let object = value.as_object()?;
    (object_keys(value) == JOB_KEYS).then_some(())?;
    oracle_literal_bool(object, "strict_verification_result", true).then_some(())?;
    let job = OracleJob {
        domain: oracle_string(object, "domain")?,
        envelope_bytes_len: oracle_u64(object, "envelope_bytes_len")?,
        envelope_bytes_sha256: oracle_string(object, "envelope_bytes_sha256")?,
        job_kind: oracle_string(object, "job_kind")?,
        preimage_bytes_len: oracle_u64(object, "preimage_bytes_len")?,
        preimage_bytes_sha256: oracle_string(object, "preimage_bytes_sha256")?,
        signature_base64url: oracle_string(object, "signature_base64url")?,
        signature_bytes_sha256: oracle_string(object, "signature_bytes_sha256")?,
        signed_material_bytes_len: oracle_u64(object, "signed_material_bytes_len")?,
        signed_material_bytes_sha256: oracle_string(object, "signed_material_bytes_sha256")?,
    };
    for digest in [
        &job.envelope_bytes_sha256,
        &job.preimage_bytes_sha256,
        &job.signature_bytes_sha256,
        &job.signed_material_bytes_sha256,
    ] {
        oracle_hex64(digest).then_some(())?;
    }
    oracle_signature_base64url(&job.signature_base64url).then_some(())?;
    let (expected_domain, maximum) = match job.job_kind.as_str() {
        "REQUEST" => ("ALR_TRUSTED_FIT_REQUEST_V1", 1_048_576_u64),
        "SIGNED_STATUS" | "OUTER_TERMINAL" => ("ALR_ISOLATED_FIT_TERMINAL_RECEIPT_V1", 2_097_152),
        "V159_INNER" => ("ALR_V159_INNER_FIT_RECEIPT_V1", 1_048_576),
        _ => return None,
    };
    (job.domain == expected_domain).then_some(())?;
    (1..=maximum)
        .contains(&job.envelope_bytes_len)
        .then_some(())?;
    (1..=maximum)
        .contains(&job.signed_material_bytes_len)
        .then_some(())?;
    let expected_preimage_length = u64::try_from(expected_domain.len())
        .ok()?
        .checked_add(9)?
        .checked_add(job.signed_material_bytes_len)?;
    (job.preimage_bytes_len == expected_preimage_length).then_some(())?;
    Some(job)
}

fn oracle_decode_value(value: &Value) -> Option<OracleReceipt> {
    let top = value.as_object()?;
    (top.keys().map(String::as_str).collect::<Vec<_>>() == TOP_KEYS).then_some(())?;
    for (key, expected) in [
        ("algorithm", "ed25519"),
        ("capability_authenticity", "SOURCE_ONLY_UNATTESTED"),
        ("model_training_performed_claim", "NOT_ESTABLISHED"),
        ("schema_version", "alr_fit_ed25519_verification_receipt_v1"),
        (
            "verdict",
            "STRICT_SIGNATURES_VALID_INPUT_BINDINGS_CAPABILITY_UNATTESTED",
        ),
        (
            "verification_primitive",
            "ed25519_dalek_2.2.0_verify_strict_zip215",
        ),
    ] {
        oracle_literal_string(top, key, expected).then_some(())?;
    }
    for key in [
        "authority_granted",
        "canonical_input_bytes_established",
        "coordinator_eligible",
        "durable_consumption_established",
        "envelope_payload_binding_established",
        "persistence_allowed",
        "platform_attested",
        "policy_overlay_adjudication_established",
        "semantic_phase_established",
        "training_allowed",
        "trusted_time_established",
    ] {
        oracle_literal_bool(top, key, false).then_some(())?;
    }
    oracle_literal_bool(top, "signatures_valid", true).then_some(())?;

    let no_authority = top.get("no_authority")?.as_object()?;
    (no_authority.keys().map(String::as_str).collect::<Vec<_>>() == NO_AUTHORITY_KEYS)
        .then_some(())?;
    no_authority
        .values()
        .all(|entry| entry.as_bool() == Some(false))
        .then_some(())?;
    let counters = top.get("authority_counters")?.as_object()?;
    (counters.keys().map(String::as_str).collect::<Vec<_>>() == AUTHORITY_COUNTER_KEYS)
        .then_some(())?;
    counters
        .values()
        .all(|entry| !entry.is_boolean() && entry.as_u64() == Some(0))
        .then_some(())?;

    let declared_phase = oracle_string(top, "declared_phase")?;
    let expected_roles: &[&str] = match declared_phase.as_str() {
        "REQUEST_ONLY" => &["REQUEST"],
        "SIGNED_STATUS" => &["REQUEST", "SIGNED_STATUS"],
        "TERMINAL_SUCCESS" => &["REQUEST", "OUTER_TERMINAL", "V159_INNER"],
        "TERMINAL_NO_INNER" => &["REQUEST", "OUTER_TERMINAL"],
        _ => return None,
    };
    let jobs = top
        .get("jobs")?
        .as_array()?
        .iter()
        .map(oracle_decode_job)
        .collect::<Option<Vec<_>>>()?;
    (jobs.len() == expected_roles.len()).then_some(())?;
    for (job, expected_role) in jobs.iter().zip(expected_roles) {
        (job.job_kind == *expected_role).then_some(())?;
        let expected_domain = match *expected_role {
            "REQUEST" => "ALR_TRUSTED_FIT_REQUEST_V1",
            "SIGNED_STATUS" | "OUTER_TERMINAL" => "ALR_ISOLATED_FIT_TERMINAL_RECEIPT_V1",
            "V159_INNER" => "ALR_V159_INNER_FIT_RECEIPT_V1",
            _ => return None,
        };
        (job.domain == expected_domain).then_some(())?;
    }
    let evidence = oracle_decode_evidence(top.get("evidence_binding")?)?;
    let mut raw_total = evidence
        .trust_policy_snapshot_bytes_len
        .checked_add(evidence.key_status_overlay_bytes_len)?;
    for job in &jobs {
        raw_total = raw_total
            .checked_add(job.envelope_bytes_len)?
            .checked_add(job.signed_material_bytes_len)?;
    }
    (raw_total <= 10_485_760).then_some(())?;
    Some(OracleReceipt {
        declared_phase,
        evidence,
        jobs,
    })
}

fn oracle_push_string(output: &mut String, value: &str) {
    assert!(oracle_safe_string(value));
    output.push('"');
    output.push_str(value);
    output.push('"');
}

fn oracle_push_u64(output: &mut String, value: u64) {
    output.push_str(&value.to_string());
}

fn oracle_encode_evidence(output: &mut String, evidence: &OracleEvidence) {
    output.push_str("\"adjudicated_at_claim\":");
    oracle_push_string(output, &evidence.adjudicated_at_claim);
    output.push_str(",\"issuer_id\":");
    oracle_push_string(output, &evidence.issuer_id);
    output.push_str(",\"key_generation\":");
    oracle_push_u64(output, evidence.key_generation);
    output.push_str(",\"key_id\":");
    oracle_push_string(output, &evidence.key_id);
    output.push_str(",\"key_status_overlay_bytes_len\":");
    oracle_push_u64(output, evidence.key_status_overlay_bytes_len);
    output.push_str(",\"key_status_overlay_bytes_sha256\":");
    oracle_push_string(output, &evidence.key_status_overlay_bytes_sha256);
    output.push_str(",\"provider_evidence_digest_sha256\":");
    oracle_push_string(output, &evidence.provider_evidence_digest_sha256);
    output.push_str(",\"public_key_base64url\":");
    oracle_push_string(output, &evidence.public_key_base64url);
    output.push_str(",\"public_key_bytes_sha256\":");
    oracle_push_string(output, &evidence.public_key_bytes_sha256);
    output.push_str(",\"trust_policy_epoch\":");
    oracle_push_u64(output, evidence.trust_policy_epoch);
    output.push_str(",\"trust_policy_id\":");
    oracle_push_string(output, &evidence.trust_policy_id);
    output.push_str(",\"trust_policy_snapshot_bytes_len\":");
    oracle_push_u64(output, evidence.trust_policy_snapshot_bytes_len);
    output.push_str(",\"trust_policy_snapshot_bytes_sha256\":");
    oracle_push_string(output, &evidence.trust_policy_snapshot_bytes_sha256);
    output.push_str(",\"usage\":");
    oracle_push_string(output, &evidence.usage);
}

fn oracle_encode_job(output: &mut String, job: &OracleJob) {
    output.push_str("{\"domain\":");
    oracle_push_string(output, &job.domain);
    output.push_str(",\"envelope_bytes_len\":");
    oracle_push_u64(output, job.envelope_bytes_len);
    output.push_str(",\"envelope_bytes_sha256\":");
    oracle_push_string(output, &job.envelope_bytes_sha256);
    output.push_str(",\"job_kind\":");
    oracle_push_string(output, &job.job_kind);
    output.push_str(",\"preimage_bytes_len\":");
    oracle_push_u64(output, job.preimage_bytes_len);
    output.push_str(",\"preimage_bytes_sha256\":");
    oracle_push_string(output, &job.preimage_bytes_sha256);
    output.push_str(",\"signature_base64url\":");
    oracle_push_string(output, &job.signature_base64url);
    output.push_str(",\"signature_bytes_sha256\":");
    oracle_push_string(output, &job.signature_bytes_sha256);
    output.push_str(",\"signed_material_bytes_len\":");
    oracle_push_u64(output, job.signed_material_bytes_len);
    output.push_str(",\"signed_material_bytes_sha256\":");
    oracle_push_string(output, &job.signed_material_bytes_sha256);
    output.push_str(",\"strict_verification_result\":true}");
}

fn oracle_encode_receipt(receipt: &OracleReceipt) -> Vec<u8> {
    let mut output = String::new();
    output.push_str("{\"algorithm\":\"ed25519\",\"authority_counters\":{");
    for (index, key) in AUTHORITY_COUNTER_KEYS.iter().enumerate() {
        if index != 0 {
            output.push(',');
        }
        oracle_push_string(&mut output, key);
        output.push_str(":0");
    }
    output.push_str("},\"authority_granted\":false,\"canonical_input_bytes_established\":false,\"capability_authenticity\":\"SOURCE_ONLY_UNATTESTED\",\"coordinator_eligible\":false,\"declared_phase\":");
    oracle_push_string(&mut output, &receipt.declared_phase);
    output.push_str(",\"durable_consumption_established\":false,\"envelope_payload_binding_established\":false,\"evidence_binding\":{");
    oracle_encode_evidence(&mut output, &receipt.evidence);
    output.push_str("},\"jobs\":[");
    for (index, job) in receipt.jobs.iter().enumerate() {
        if index != 0 {
            output.push(',');
        }
        oracle_encode_job(&mut output, job);
    }
    output.push_str("],\"model_training_performed_claim\":\"NOT_ESTABLISHED\",\"no_authority\":{");
    for (index, key) in NO_AUTHORITY_KEYS.iter().enumerate() {
        if index != 0 {
            output.push(',');
        }
        oracle_push_string(&mut output, key);
        output.push_str(":false");
    }
    output.push_str("},\"persistence_allowed\":false,\"platform_attested\":false,\"policy_overlay_adjudication_established\":false,\"schema_version\":\"alr_fit_ed25519_verification_receipt_v1\",\"semantic_phase_established\":false,\"signatures_valid\":true,\"training_allowed\":false,\"trusted_time_established\":false,\"verdict\":\"STRICT_SIGNATURES_VALID_INPUT_BINDINGS_CAPABILITY_UNATTESTED\",\"verification_primitive\":\"ed25519_dalek_2.2.0_verify_strict_zip215\"}");
    output.into_bytes()
}

fn receipt_oracle_bytes(bytes: &[u8]) -> Option<OracleReceipt> {
    bytes.is_ascii().then_some(())?;
    (!bytes.starts_with(&[0xef, 0xbb, 0xbf])).then_some(())?;
    let value: Value = serde_json::from_slice(bytes).ok()?;
    let receipt = oracle_decode_value(&value)?;
    (oracle_encode_receipt(&receipt) == bytes).then_some(receipt)
}

fn receipt_oracle(value: &Value) -> bool {
    oracle_decode_value(value).is_some()
}

#[test]
fn rfc8032_test_vector_one_passes_verify_strict() {
    const RFC_SIGNATURE: &str =
        "5VZDAMNgrHKQhuLMgG6CioSHfx645dl02HPgZSJJAVVfuIIVkKM7rMYeOXAc-bRr0lv18FlbviRlUUFDjnoQCw";
    let mut key_bytes = [0_u8; 32];
    let mut signature_bytes = [0_u8; 64];
    assert_eq!(
        URL_SAFE_NO_PAD.decode_slice(PUBLIC_KEY, &mut key_bytes),
        Ok(32)
    );
    assert_eq!(
        URL_SAFE_NO_PAD.decode_slice(RFC_SIGNATURE, &mut signature_bytes),
        Ok(64)
    );
    let key = VerifyingKey::from_bytes(&key_bytes).expect("RFC key");
    let signature = Signature::from_bytes(&signature_bytes);
    key.verify_strict(b"", &signature).expect("RFC signature");
}

fn independent_preimage(domain: &str, length: u64, material: &[u8]) -> Vec<u8> {
    let mut value = Vec::new();
    value.extend_from_slice(domain.as_bytes());
    value.push(0);
    value.extend_from_slice(&length.to_be_bytes());
    value.extend_from_slice(material);
    value
}

fn independent_strict_result(preimage: &[u8], signature_text: &str) -> bool {
    let mut key_bytes = [0_u8; 32];
    let mut signature_bytes = [0_u8; 64];
    assert_eq!(
        URL_SAFE_NO_PAD.decode_slice(PUBLIC_KEY, &mut key_bytes),
        Ok(32)
    );
    assert_eq!(
        URL_SAFE_NO_PAD.decode_slice(signature_text, &mut signature_bytes),
        Ok(64)
    );
    let key = VerifyingKey::from_bytes(&key_bytes).unwrap();
    let signature = Signature::from_bytes(&signature_bytes);
    key.verify_strict(preimage, &signature).is_ok()
}

#[test]
fn protocol_preimage_recipe_is_independently_fixed() {
    for (role, envelope, domain, material, signature) in [
        (
            SignatureRoleV1::Request,
            REQUEST_ENVELOPE,
            "ALR_TRUSTED_FIT_REQUEST_V1",
            REQUEST_MATERIAL,
            REQUEST_SIGNATURE,
        ),
        (
            SignatureRoleV1::SignedStatus,
            STATUS_ENVELOPE,
            "ALR_ISOLATED_FIT_TERMINAL_RECEIPT_V1",
            STATUS_MATERIAL,
            STATUS_SIGNATURE,
        ),
        (
            SignatureRoleV1::OuterTerminal,
            OUTER_ENVELOPE,
            "ALR_ISOLATED_FIT_TERMINAL_RECEIPT_V1",
            OUTER_MATERIAL,
            OUTER_SIGNATURE,
        ),
        (
            SignatureRoleV1::V159Inner,
            INNER_ENVELOPE,
            "ALR_V159_INNER_FIT_RECEIPT_V1",
            INNER_MATERIAL,
            INNER_SIGNATURE,
        ),
    ] {
        let length = material.len() as u64;
        let correct = independent_preimage(domain, length, material);
        assert!(independent_strict_result(&correct, signature));
        let output = verify_role_bytes(role, envelope, material).unwrap();
        let typed_job = output.receipt().jobs().last().unwrap();
        assert_eq!(typed_job.preimage_bytes_len(), correct.len());
        assert_eq!(
            typed_job.preimage_bytes_sha256(),
            &<[u8; 32]>::from(Sha256::digest(&correct))
        );
        assert_eq!(
            output.receipt_sha256(),
            &<[u8; 32]>::from(Sha256::digest(output.canonical_bytes()))
        );

        let mut missing_nul = domain.as_bytes().to_vec();
        missing_nul.extend_from_slice(&length.to_be_bytes());
        missing_nul.extend_from_slice(material);
        let mut nonzero_nul = correct.clone();
        nonzero_nul[domain.len()] = 1;
        let mut double_nul = domain.as_bytes().to_vec();
        double_nul.extend_from_slice(&[0, 0]);
        double_nul.extend_from_slice(&length.to_be_bytes());
        double_nul.extend_from_slice(material);
        let mut little_endian = domain.as_bytes().to_vec();
        little_endian.push(0);
        little_endian.extend_from_slice(&length.to_le_bytes());
        little_endian.extend_from_slice(material);
        let changed_material = [material, b"x"].concat();
        for malformed in [
            independent_preimage("WRONG_DOMAIN", length, material),
            missing_nul,
            nonzero_nul,
            double_nul,
            little_endian,
            independent_preimage(domain, length - 1, material),
            independent_preimage(domain, length + 1, material),
            independent_preimage(domain, 0, material),
            independent_preimage(domain, u64::MAX, material),
            independent_preimage(domain, changed_material.len() as u64, &changed_material),
        ] {
            assert!(!independent_strict_result(&malformed, signature));
        }
    }
}

#[test]
fn all_four_closed_phases_verify_and_emit_exact_ceiling() {
    for (phase, expected_name, expected_jobs) in [
        (VerificationPhaseV1::RequestOnly, "REQUEST_ONLY", 1_usize),
        (VerificationPhaseV1::SignedStatus, "SIGNED_STATUS", 2),
        (VerificationPhaseV1::TerminalSuccess, "TERMINAL_SUCCESS", 3),
        (VerificationPhaseV1::TerminalNoInner, "TERMINAL_NO_INNER", 2),
    ] {
        let output = verify_phase(phase);
        let receipt: Value = serde_json::from_slice(output.canonical_bytes()).unwrap();
        assert_eq!(receipt["declared_phase"], expected_name);
        assert_eq!(receipt["jobs"].as_array().unwrap().len(), expected_jobs);
        assert_eq!(
            receipt["schema_version"],
            "alr_fit_ed25519_verification_receipt_v1"
        );
        assert_eq!(receipt["algorithm"], "ed25519");
        assert_eq!(
            receipt["verdict"],
            "STRICT_SIGNATURES_VALID_INPUT_BINDINGS_CAPABILITY_UNATTESTED"
        );
        assert_eq!(receipt["capability_authenticity"], "SOURCE_ONLY_UNATTESTED");
        assert_eq!(receipt["model_training_performed_claim"], "NOT_ESTABLISHED");
        assert_eq!(receipt["signatures_valid"], true);
        for field in [
            "authority_granted",
            "canonical_input_bytes_established",
            "coordinator_eligible",
            "durable_consumption_established",
            "envelope_payload_binding_established",
            "persistence_allowed",
            "platform_attested",
            "policy_overlay_adjudication_established",
            "semantic_phase_established",
            "training_allowed",
            "trusted_time_established",
        ] {
            assert_eq!(receipt[field], false, "{field}");
        }
        assert!(receipt_oracle_bytes(output.canonical_bytes()).is_some());
    }
}

#[test]
fn receipt_bytes_are_exact_compact_ascii_repeatable_and_self_hashed() {
    let first = verify_phase(VerificationPhaseV1::TerminalSuccess);
    let second = verify_phase(VerificationPhaseV1::TerminalSuccess);
    assert_eq!(first.canonical_bytes(), second.canonical_bytes());
    assert_eq!(first.receipt_sha256(), second.receipt_sha256());
    assert!(first.canonical_bytes().len() <= 32_768);
    assert!(first.canonical_bytes().iter().all(u8::is_ascii));
    assert!(!first.canonical_bytes().contains(&b'\n'));
    assert!(!first.canonical_bytes().contains(&b'\r'));
    let parsed = receipt_oracle_bytes(first.canonical_bytes()).expect("fixed-schema receipt");
    assert_eq!(oracle_encode_receipt(&parsed), first.canonical_bytes());
    let digest: [u8; 32] = Sha256::digest(first.canonical_bytes()).into();
    assert_eq!(first.receipt_sha256(), &digest);
    assert_eq!(
        first.receipt().receipt_bytes_len(),
        first.canonical_bytes().len()
    );
    assert_eq!(first.receipt().receipt_sha256(), &digest);
}

fn digest_hex(digest: &[u8; 32]) -> String {
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

#[test]
fn fixed_schema_oracle_reencodes_all_four_receipts_byte_for_byte() {
    for phase in [
        VerificationPhaseV1::RequestOnly,
        VerificationPhaseV1::SignedStatus,
        VerificationPhaseV1::TerminalSuccess,
        VerificationPhaseV1::TerminalNoInner,
    ] {
        let output: UnattestedVerificationOutputV1 = verify_phase(phase);
        let receipt: &UnattestedVerificationReceiptV1 = output.receipt();
        let jobs: &[VerifiedSignatureJobV1] = receipt.jobs();
        let oracle = receipt_oracle_bytes(receipt.canonical_bytes()).unwrap();
        let input_jobs = jobs_for(phase);
        assert_eq!(receipt.declared_phase(), phase);
        assert_eq!(receipt.job_count(), jobs.len());
        assert_eq!(receipt.receipt_bytes_len(), receipt.canonical_bytes().len());
        assert_eq!(receipt.canonical_bytes(), output.canonical_bytes());
        assert_eq!(receipt.receipt_sha256(), output.receipt_sha256());
        assert_eq!(jobs.len(), oracle.jobs.len());
        assert_eq!(oracle.evidence.adjudicated_at_claim, ADJUDICATED_AT);
        assert_eq!(oracle.evidence.issuer_id, "issuer.synthetic");
        assert_eq!(oracle.evidence.key_generation, 7);
        assert_eq!(oracle.evidence.key_id, "key.synthetic");
        assert_eq!(
            oracle.evidence.key_status_overlay_bytes_len,
            OVERLAY_BYTES.len() as u64
        );
        assert_eq!(
            oracle.evidence.key_status_overlay_bytes_sha256,
            digest_hex(&Sha256::digest(OVERLAY_BYTES).into())
        );
        assert_eq!(
            oracle.evidence.provider_evidence_digest_sha256,
            PROVIDER_DIGEST
        );
        assert_eq!(oracle.evidence.public_key_base64url, PUBLIC_KEY);
        let mut public_key_bytes = [0_u8; 32];
        assert_eq!(
            URL_SAFE_NO_PAD.decode_slice(PUBLIC_KEY, &mut public_key_bytes),
            Ok(32)
        );
        assert_eq!(
            oracle.evidence.public_key_bytes_sha256,
            digest_hex(&Sha256::digest(public_key_bytes).into())
        );
        assert_eq!(oracle.evidence.trust_policy_epoch, 11);
        assert_eq!(oracle.evidence.trust_policy_id, "policy.synthetic");
        assert_eq!(
            oracle.evidence.trust_policy_snapshot_bytes_len,
            POLICY_BYTES.len() as u64
        );
        assert_eq!(
            oracle.evidence.trust_policy_snapshot_bytes_sha256,
            digest_hex(&Sha256::digest(POLICY_BYTES).into())
        );
        assert_eq!(oracle.evidence.usage, "ALR_TRUSTED_FIT_HANDSHAKE_SIGNING");

        for ((typed, expected), input_job) in jobs.iter().zip(&oracle.jobs).zip(&input_jobs) {
            let domain = match input_job.role {
                SignatureRoleV1::Request => "ALR_TRUSTED_FIT_REQUEST_V1",
                SignatureRoleV1::SignedStatus | SignatureRoleV1::OuterTerminal => {
                    "ALR_ISOLATED_FIT_TERMINAL_RECEIPT_V1"
                }
                SignatureRoleV1::V159Inner => "ALR_V159_INNER_FIT_RECEIPT_V1",
            };
            let preimage = independent_preimage(
                domain,
                input_job.signed_material_bytes.len() as u64,
                input_job.signed_material_bytes,
            );
            let mut signature_bytes = [0_u8; 64];
            assert_eq!(
                URL_SAFE_NO_PAD.decode_slice(input_job.signature_base64url, &mut signature_bytes),
                Ok(64)
            );
            assert_eq!(expected.job_kind, input_job.role.to_string());
            assert_eq!(expected.domain, domain);
            assert_eq!(
                expected.envelope_bytes_len,
                input_job.envelope_bytes.len() as u64
            );
            assert_eq!(
                expected.envelope_bytes_sha256,
                digest_hex(&Sha256::digest(input_job.envelope_bytes).into())
            );
            assert_eq!(
                expected.signed_material_bytes_len,
                input_job.signed_material_bytes.len() as u64
            );
            assert_eq!(
                expected.signed_material_bytes_sha256,
                digest_hex(&Sha256::digest(input_job.signed_material_bytes).into())
            );
            assert_eq!(expected.preimage_bytes_len, preimage.len() as u64);
            assert_eq!(
                expected.preimage_bytes_sha256,
                digest_hex(&Sha256::digest(&preimage).into())
            );
            assert_eq!(expected.signature_base64url, input_job.signature_base64url);
            assert_eq!(
                expected.signature_bytes_sha256,
                digest_hex(&Sha256::digest(signature_bytes).into())
            );
            assert_eq!(typed.job_kind().to_string(), expected.job_kind);
            assert_eq!(typed.domain(), expected.domain);
            assert_eq!(
                typed.envelope_bytes_len() as u64,
                expected.envelope_bytes_len
            );
            assert_eq!(
                digest_hex(typed.envelope_bytes_sha256()),
                expected.envelope_bytes_sha256
            );
            assert_eq!(
                typed.signed_material_bytes_len() as u64,
                expected.signed_material_bytes_len
            );
            assert_eq!(
                digest_hex(typed.signed_material_bytes_sha256()),
                expected.signed_material_bytes_sha256
            );
            assert_eq!(
                typed.preimage_bytes_len() as u64,
                expected.preimage_bytes_len
            );
            assert_eq!(
                digest_hex(typed.preimage_bytes_sha256()),
                expected.preimage_bytes_sha256
            );
            assert_eq!(typed.signature_base64url(), expected.signature_base64url);
            assert_eq!(
                digest_hex(typed.signature_bytes_sha256()),
                expected.signature_bytes_sha256
            );
            assert!(typed.strict_verification_result());
        }
    }
}

fn replace_once(value: &[u8], from: &str, to: &str) -> Vec<u8> {
    let text = std::str::from_utf8(value).unwrap();
    assert_eq!(text.matches(from).count(), 1, "from={from}");
    text.replacen(from, to, 1).into_bytes()
}

#[test]
fn fixed_schema_oracle_rejects_literal_type_and_grammar_mutants() {
    let output = verify_phase(VerificationPhaseV1::TerminalSuccess);
    let bytes = output.canonical_bytes();
    assert!(bytes.starts_with(b"{\"algorithm\":\"ed25519\",\"authority_counters\":{"));
    assert!(receipt_oracle_bytes(bytes).is_some());
    assert!(receipt_oracle_bytes(&replace_once(
        bytes,
        "\"algorithm\":\"ed25519\"",
        "\"algorithm\":\"Ed25519\"",
    ))
    .is_none());

    let baseline: Value = serde_json::from_slice(bytes).unwrap();
    for (key, replacement) in [
        ("algorithm", "ED25519"),
        ("capability_authenticity", "ATTESTED"),
        ("model_training_performed_claim", "PERFORMED"),
        ("schema_version", "other"),
        ("verdict", "VERIFIED"),
        ("verification_primitive", "ordinary_verify"),
        ("declared_phase", "SIGNED_STATUS"),
    ] {
        let mut mutant = baseline.clone();
        mutant[key] = Value::String(replacement.to_owned());
        assert!(oracle_decode_value(&mutant).is_none(), "key={key}");
        let mut wrong_type = baseline.clone();
        wrong_type[key] = Value::Null;
        assert!(oracle_decode_value(&wrong_type).is_none(), "key={key}");
    }
    for key in [
        "authority_granted",
        "canonical_input_bytes_established",
        "coordinator_eligible",
        "durable_consumption_established",
        "envelope_payload_binding_established",
        "persistence_allowed",
        "platform_attested",
        "policy_overlay_adjudication_established",
        "semantic_phase_established",
        "training_allowed",
        "trusted_time_established",
    ] {
        let mut mutant = baseline.clone();
        mutant[key] = Value::Bool(true);
        assert!(oracle_decode_value(&mutant).is_none(), "key={key}");
        let mut wrong_type = baseline.clone();
        wrong_type[key] = Value::Null;
        assert!(oracle_decode_value(&wrong_type).is_none(), "key={key}");
    }
    let mut signatures_false = baseline.clone();
    signatures_false["signatures_valid"] = Value::Bool(false);
    assert!(oracle_decode_value(&signatures_false).is_none());
    let mut signatures_wrong_type = baseline.clone();
    signatures_wrong_type["signatures_valid"] = Value::Null;
    assert!(oracle_decode_value(&signatures_wrong_type).is_none());
    let mut strict_false = baseline.clone();
    strict_false["jobs"][0]["strict_verification_result"] = Value::Bool(false);
    assert!(oracle_decode_value(&strict_false).is_none());
    let mut strict_wrong_type = baseline.clone();
    strict_wrong_type["jobs"][0]["strict_verification_result"] = Value::Null;
    assert!(oracle_decode_value(&strict_wrong_type).is_none());

    for key in [
        "adjudicated_at_claim",
        "issuer_id",
        "key_id",
        "key_status_overlay_bytes_sha256",
        "provider_evidence_digest_sha256",
        "public_key_base64url",
        "public_key_bytes_sha256",
        "trust_policy_id",
        "trust_policy_snapshot_bytes_sha256",
        "usage",
    ] {
        let mut mutant = baseline.clone();
        mutant["evidence_binding"][key] = Value::Null;
        assert!(oracle_decode_value(&mutant).is_none(), "key={key}");
    }
    for key in [
        "domain",
        "envelope_bytes_sha256",
        "job_kind",
        "preimage_bytes_sha256",
        "signature_base64url",
        "signature_bytes_sha256",
        "signed_material_bytes_sha256",
    ] {
        let mut mutant = baseline.clone();
        mutant["jobs"][0][key] = Value::Null;
        assert!(oracle_decode_value(&mutant).is_none(), "key={key}");
    }
    for (key, wrong_type) in [
        ("authority_counters", Value::Null),
        ("evidence_binding", Value::Array(Vec::new())),
        ("jobs", Value::Object(Map::new())),
        ("no_authority", Value::Null),
    ] {
        let mut mutant = baseline.clone();
        mutant[key] = wrong_type;
        assert!(oracle_decode_value(&mutant).is_none(), "key={key}");
    }
    let mut non_object_job = baseline.clone();
    non_object_job["jobs"][0] = Value::Null;
    assert!(oracle_decode_value(&non_object_job).is_none());

    for (key, invalid_value) in [
        ("adjudicated_at_claim", "2024-02-30T00:00:00.000000Z"),
        ("issuer_id", "INVALID"),
        ("key_id", "_invalid"),
        (
            "provider_evidence_digest_sha256",
            "A111111111111111111111111111111111111111111111111111111111111111",
        ),
        ("trust_policy_id", "invalid/path"),
        ("usage", "OTHER_USAGE"),
    ] {
        let mut mutant = baseline.clone();
        mutant["evidence_binding"][key] = Value::String(invalid_value.to_owned());
        assert!(oracle_decode_value(&mutant).is_none(), "key={key}");
    }
    for (key, invalid_value) in [
        ("key_generation", 0_u64),
        ("key_generation", 9_223_372_036_854_775_808),
        ("trust_policy_epoch", 0),
        ("trust_policy_epoch", 9_223_372_036_854_775_808),
        ("key_status_overlay_bytes_len", 1),
        ("key_status_overlay_bytes_len", 1_048_577),
        ("trust_policy_snapshot_bytes_len", 1),
        ("trust_policy_snapshot_bytes_len", 1_048_577),
    ] {
        let mut mutant = baseline.clone();
        mutant["evidence_binding"][key] = json!(invalid_value);
        assert!(oracle_decode_value(&mutant).is_none(), "key={key}");
    }
    for (job_index, maximum) in [(0_usize, 1_048_576_u64), (1, 2_097_152), (2, 1_048_576)] {
        for key in ["envelope_bytes_len", "signed_material_bytes_len"] {
            for invalid_value in [0_u64, maximum + 1] {
                let mut mutant = baseline.clone();
                mutant["jobs"][job_index][key] = json!(invalid_value);
                assert!(
                    oracle_decode_value(&mutant).is_none(),
                    "job={job_index}, key={key}"
                );
            }
        }
        let mut preimage_length = baseline.clone();
        preimage_length["jobs"][job_index]["preimage_bytes_len"] = json!(0);
        assert!(oracle_decode_value(&preimage_length).is_none());
    }

    for key in NO_AUTHORITY_KEYS {
        let mut mutant = baseline.clone();
        mutant["no_authority"][*key] = Value::Bool(true);
        assert!(oracle_decode_value(&mutant).is_none(), "key={key}");
        let mut wrong_type = baseline.clone();
        wrong_type["no_authority"][*key] = json!(0);
        assert!(oracle_decode_value(&wrong_type).is_none(), "key={key}");
    }
    for key in AUTHORITY_COUNTER_KEYS {
        let mut mutant = baseline.clone();
        mutant["authority_counters"][*key] = json!(1);
        assert!(oracle_decode_value(&mutant).is_none(), "key={key}");
        let mut wrong_type = baseline.clone();
        wrong_type["authority_counters"][*key] = Value::Bool(false);
        assert!(oracle_decode_value(&wrong_type).is_none(), "key={key}");
    }

    for (object_key, integer_key) in [
        ("evidence_binding", "key_generation"),
        ("evidence_binding", "key_status_overlay_bytes_len"),
        ("evidence_binding", "trust_policy_epoch"),
        ("evidence_binding", "trust_policy_snapshot_bytes_len"),
    ] {
        for value in [Value::Null, json!(-1), json!(1.5), Value::Bool(false)] {
            let mut mutant = baseline.clone();
            mutant[object_key][integer_key] = value;
            assert!(oracle_decode_value(&mutant).is_none(), "key={integer_key}");
        }
    }
    for integer_key in [
        "envelope_bytes_len",
        "preimage_bytes_len",
        "signed_material_bytes_len",
    ] {
        for value in [Value::Null, json!(-1), json!(1.5), Value::Bool(false)] {
            let mut mutant = baseline.clone();
            mutant["jobs"][0][integer_key] = value;
            assert!(oracle_decode_value(&mutant).is_none(), "key={integer_key}");
        }
    }

    for (object_key, removed_key) in [
        (None, "algorithm"),
        (Some("evidence_binding"), "issuer_id"),
        (Some("no_authority"), "trading_authority"),
        (Some("authority_counters"), "trading_action_count"),
    ] {
        let mut mutant = baseline.clone();
        let object = match object_key {
            Some(key) => mutant[key].as_object_mut().unwrap(),
            None => mutant.as_object_mut().unwrap(),
        };
        object.remove(removed_key);
        assert!(oracle_decode_value(&mutant).is_none());
    }
    let mut omitted_job_key = baseline.clone();
    omitted_job_key["jobs"][0]
        .as_object_mut()
        .unwrap()
        .remove("domain");
    assert!(oracle_decode_value(&omitted_job_key).is_none());
    for object_key in [
        None,
        Some("evidence_binding"),
        Some("no_authority"),
        Some("authority_counters"),
    ] {
        let mut mutant = baseline.clone();
        let object = match object_key {
            Some(key) => mutant[key].as_object_mut().unwrap(),
            None => mutant.as_object_mut().unwrap(),
        };
        object.insert("unknown".to_owned(), Value::Null);
        assert!(oracle_decode_value(&mutant).is_none());
    }
    let mut unknown_job_key = baseline.clone();
    unknown_job_key["jobs"][0]
        .as_object_mut()
        .unwrap()
        .insert("unknown".to_owned(), Value::Null);
    assert!(oracle_decode_value(&unknown_job_key).is_none());

    let mut swapped_jobs = baseline.clone();
    swapped_jobs["jobs"].as_array_mut().unwrap().swap(0, 1);
    assert!(oracle_decode_value(&swapped_jobs).is_none());
    let mut malformed_digest = baseline.clone();
    malformed_digest["jobs"][0]["envelope_bytes_sha256"] = Value::String("bad".into());
    assert!(oracle_decode_value(&malformed_digest).is_none());
    let mut malformed_public_key = baseline.clone();
    malformed_public_key["evidence_binding"]["public_key_base64url"] =
        Value::String("!".repeat(43));
    assert!(oracle_decode_value(&malformed_public_key).is_none());
    let mut malformed_signature = baseline.clone();
    malformed_signature["jobs"][0]["signature_base64url"] = Value::String("!".repeat(86));
    assert!(oracle_decode_value(&malformed_signature).is_none());

    let mut bom = vec![0xef, 0xbb, 0xbf];
    bom.extend_from_slice(bytes);
    for mutant in [
        bom,
        [b" ".as_slice(), bytes].concat(),
        [bytes, b"\n".as_slice()].concat(),
        replace_once(
            bytes,
            "\"algorithm\":\"ed25519\"",
            "\"algorithm\":\"ed\\u00325519\"",
        ),
        replace_once(
            bytes,
            "{\"algorithm\":\"ed25519\",",
            "{\"algorithm\":\"ed25519\",\"algorithm\":\"ed25519\",",
        ),
        replace_once(
            bytes,
            "\"adjudicated_at_claim\":\"2026-07-12T18:58:46.000000Z\",\"issuer_id\":\"issuer.synthetic\"",
            "\"issuer_id\":\"issuer.synthetic\",\"adjudicated_at_claim\":\"2026-07-12T18:58:46.000000Z\"",
        ),
        replace_once(bytes, "\"key_generation\":7", "\"key_generation\":null"),
        replace_once(bytes, "\"key_generation\":7", "\"key_generation\":1.0"),
        replace_once(bytes, "\"key_generation\":7", "\"key_generation\":-7"),
        replace_once(bytes, "\"key_generation\":7", "\"key_generation\":+7"),
        replace_once(bytes, "\"key_generation\":7", "\"key_generation\":07"),
        replace_once(
            bytes,
            "{\"algorithm\":\"ed25519\",",
            "{\"extension\":{},\"algorithm\":\"ed25519\",",
        ),
    ] {
        assert!(receipt_oracle_bytes(&mutant).is_none());
    }
}

#[test]
fn canonical_receipt_freezes_exact_nested_key_order_and_authority_types() {
    let output = verify_phase(VerificationPhaseV1::TerminalSuccess);
    let receipt: Value = serde_json::from_slice(output.canonical_bytes()).unwrap();
    assert_eq!(object_keys(&receipt), TOP_KEYS);
    assert_eq!(object_keys(&receipt["evidence_binding"]), EVIDENCE_KEYS);
    for job in receipt["jobs"].as_array().unwrap() {
        assert_eq!(object_keys(job), JOB_KEYS);
        assert_eq!(job["strict_verification_result"], true);
    }
    assert_eq!(object_keys(&receipt["no_authority"]), NO_AUTHORITY_KEYS);
    assert_eq!(
        object_keys(&receipt["authority_counters"]),
        AUTHORITY_COUNTER_KEYS
    );

    let mut omitted = receipt.clone();
    omitted.as_object_mut().unwrap().remove("authority_granted");
    assert!(!receipt_oracle(&omitted));

    let mut unknown = receipt.clone();
    unknown
        .as_object_mut()
        .unwrap()
        .insert("unknown".into(), Value::Bool(false));
    assert!(!receipt_oracle(&unknown));

    let mut true_authority = receipt.clone();
    true_authority["no_authority"]["trading_authority"] = Value::Bool(true);
    assert!(!receipt_oracle(&true_authority));

    let mut non_boolean_authority = receipt.clone();
    non_boolean_authority["no_authority"]["trading_authority"] = json!(0);
    assert!(!receipt_oracle(&non_boolean_authority));

    let mut nonzero_counter = receipt.clone();
    nonzero_counter["authority_counters"]["model_fit_count"] = json!(1);
    assert!(!receipt_oracle(&nonzero_counter));

    let mut boolean_counter = receipt;
    boolean_counter["authority_counters"]["model_fit_count"] = Value::Bool(false);
    assert!(!receipt_oracle(&boolean_counter));
}

#[test]
fn phase_shape_is_exact_indexed_and_never_sorted() {
    let missing = [request_job()];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::SignedStatus,
            key_binding: key(),
            evidence_binding: evidence(),
            jobs: &missing,
        }),
        Err(VerificationErrorCodeV1::PhaseShapeInvalid)
    );

    let reordered = [outer_job(), request_job(), inner_job()];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::TerminalSuccess,
            key_binding: key(),
            evidence_binding: evidence(),
            jobs: &reordered,
        }),
        Err(VerificationErrorCodeV1::PhaseShapeInvalid)
    );

    let duplicate = [request_job(), request_job()];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::TerminalNoInner,
            key_binding: key(),
            evidence_binding: evidence(),
            jobs: &duplicate,
        }),
        Err(VerificationErrorCodeV1::PhaseShapeInvalid)
    );
}

#[test]
fn phase_shape_generated_mutation_matrix_is_panic_free_and_first() {
    let oversized = vec![b'x'; 10_485_761];
    let phases = [
        VerificationPhaseV1::RequestOnly,
        VerificationPhaseV1::SignedStatus,
        VerificationPhaseV1::TerminalSuccess,
        VerificationPhaseV1::TerminalNoInner,
    ];
    for phase in phases {
        let canonical = jobs_for(phase);
        let mut mutations: Vec<Vec<SignatureJobInputV1<'static>>> = Vec::new();
        for index in 0..canonical.len() {
            let mut deleted = canonical.clone();
            deleted.remove(index);
            mutations.push(deleted);

            let mut duplicated = canonical.clone();
            duplicated.insert(index, canonical[index]);
            mutations.push(duplicated);

            for replacement in [request_job(), status_job(), outer_job(), inner_job()] {
                if replacement.role != canonical[index].role {
                    let mut replaced = canonical.clone();
                    replaced[index] = replacement;
                    mutations.push(replaced);
                }
            }
        }
        for index in 0..=canonical.len() {
            for inserted_job in [request_job(), status_job(), outer_job(), inner_job()] {
                let mut inserted = canonical.clone();
                inserted.insert(index, inserted_job);
                mutations.push(inserted);
            }
        }
        for left in 0..canonical.len() {
            for right in (left + 1)..canonical.len() {
                let mut swapped = canonical.clone();
                swapped.swap(left, right);
                mutations.push(swapped);
            }
        }
        for other_phase in phases {
            if other_phase != phase {
                mutations.push(jobs_for(other_phase));
            }
        }

        for mutation in mutations {
            let raw_faults: Vec<SignatureJobInputV1<'_>> = mutation
                .iter()
                .enumerate()
                .map(|(index, job)| SignatureJobInputV1 {
                    role: job.role,
                    envelope_bytes: if index == 0 {
                        &oversized
                    } else {
                        job.envelope_bytes
                    },
                    signed_material_bytes: job.signed_material_bytes,
                    signature_base64url: "malformed",
                })
                .collect();
            let outcome = catch_unwind(AssertUnwindSafe(|| {
                verify_unattested_phase_v1(PhaseVerificationInputV1 {
                    declared_phase: phase,
                    key_binding: key_with("INVALID", "key.synthetic", 0, "bad"),
                    evidence_binding: evidence(),
                    jobs: &raw_faults,
                })
            }));
            assert!(outcome.is_ok());
            assert_eq!(
                outcome.unwrap(),
                Err(VerificationErrorCodeV1::PhaseShapeInvalid)
            );
        }
    }
}

#[test]
fn one_field_crypto_mutations_fail_closed() {
    let material_mutated = [SignatureJobInputV1 {
        role: SignatureRoleV1::Request,
        envelope_bytes: REQUEST_ENVELOPE,
        signed_material_bytes: br#"{"request":"mutated"}"#,
        signature_base64url: REQUEST_SIGNATURE,
    }];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::RequestOnly,
            key_binding: key(),
            evidence_binding: evidence(),
            jobs: &material_mutated,
        }),
        Err(VerificationErrorCodeV1::StrictSignatureInvalid(
            SignatureRoleV1::Request
        ))
    );

    for signature in [ZERO_SIGNATURE, STATUS_SIGNATURE] {
        let jobs = [SignatureJobInputV1 {
            role: SignatureRoleV1::Request,
            envelope_bytes: REQUEST_ENVELOPE,
            signed_material_bytes: REQUEST_MATERIAL,
            signature_base64url: signature,
        }];
        assert_eq!(
            verify_unattested_phase_v1(PhaseVerificationInputV1 {
                declared_phase: VerificationPhaseV1::RequestOnly,
                key_binding: key(),
                evidence_binding: evidence(),
                jobs: &jobs,
            }),
            Err(VerificationErrorCodeV1::StrictSignatureInvalid(
                SignatureRoleV1::Request
            ))
        );
    }
}

#[test]
fn strict_verification_rejects_scalar_point_and_weak_key_cases() {
    for signature in [
        REQUEST_SCALAR_PLUS_L_SIGNATURE,
        REQUEST_POINT_SIGN_FLIP_SIGNATURE,
    ] {
        let jobs = [SignatureJobInputV1 {
            role: SignatureRoleV1::Request,
            envelope_bytes: REQUEST_ENVELOPE,
            signed_material_bytes: REQUEST_MATERIAL,
            signature_base64url: signature,
        }];
        assert_eq!(
            verify_unattested_phase_v1(PhaseVerificationInputV1 {
                declared_phase: VerificationPhaseV1::RequestOnly,
                key_binding: key(),
                evidence_binding: evidence(),
                jobs: &jobs,
            }),
            Err(VerificationErrorCodeV1::StrictSignatureInvalid(
                SignatureRoleV1::Request
            ))
        );
    }

    for public_key in [ZERO_KEY, IDENTITY_KEY, NONCANONICAL_POINT_KEY] {
        let jobs = [request_job()];
        let result = verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::RequestOnly,
            key_binding: key_with("issuer.synthetic", "key.synthetic", 7, public_key),
            evidence_binding: evidence(),
            jobs: &jobs,
        });
        assert!(matches!(
            result,
            Err(VerificationErrorCodeV1::PublicKeyPointInvalid)
                | Err(VerificationErrorCodeV1::StrictSignatureInvalid(
                    SignatureRoleV1::Request
                ))
        ));
    }
}

#[test]
fn canonical_base64url_shapes_fail_before_crypto() {
    let jobs = [request_job()];
    for public_key in [
        "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo=",
        "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHUR!",
        "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHUR",
    ] {
        assert_eq!(
            verify_unattested_phase_v1(PhaseVerificationInputV1 {
                declared_phase: VerificationPhaseV1::RequestOnly,
                key_binding: key_with("issuer.synthetic", "key.synthetic", 7, public_key),
                evidence_binding: evidence(),
                jobs: &jobs,
            }),
            Err(VerificationErrorCodeV1::PublicKeyBase64UrlInvalid)
        );
    }

    for signature in [
        "vVpkt85syGv2bGscyIOg2C3WZCq09qATUnto_9fry7Z0keG38OLPH4UhCypATu_1hBR9QfRSuJbvVYRQGJ6BDg=",
        "vVpkt85syGv2bGscyIOg2C3WZCq09qATUnto_9fry7Z0keG38OLPH4UhCypATu_1hBR9QfRSuJbvVYRQGJ6BD!",
        "short",
    ] {
        let jobs = [SignatureJobInputV1 {
            role: SignatureRoleV1::Request,
            envelope_bytes: REQUEST_ENVELOPE,
            signed_material_bytes: REQUEST_MATERIAL,
            signature_base64url: signature,
        }];
        assert_eq!(
            verify_unattested_phase_v1(PhaseVerificationInputV1 {
                declared_phase: VerificationPhaseV1::RequestOnly,
                key_binding: key(),
                evidence_binding: evidence(),
                jobs: &jobs,
            }),
            Err(VerificationErrorCodeV1::SignatureBase64UrlInvalid(
                SignatureRoleV1::Request
            ))
        );
    }
}

#[test]
fn base64url_boundary_matrix_is_canonical_and_ordered() {
    let jobs = [request_job()];
    let mut noncanonical_key_tail = PUBLIC_KEY.to_owned();
    noncanonical_key_tail.pop();
    noncanonical_key_tail.push('p');
    let mut embedded_key_space = PUBLIC_KEY.to_owned();
    embedded_key_space.replace_range(10..11, " ");
    let invalid_keys = [
        PUBLIC_KEY[..42].to_owned(),
        format!("{PUBLIC_KEY}A"),
        format!("{PUBLIC_KEY}="),
        format!(" {}", PUBLIC_KEY),
        PUBLIC_KEY.replace('_', "/"),
        format!("{}!", &PUBLIC_KEY[..42]),
        format!("{}é", &PUBLIC_KEY[..42]),
        embedded_key_space,
        noncanonical_key_tail,
    ];
    for public_key in &invalid_keys {
        assert_eq!(
            verify_unattested_phase_v1(PhaseVerificationInputV1 {
                declared_phase: VerificationPhaseV1::RequestOnly,
                key_binding: key_with("issuer.synthetic", "key.synthetic", 7, public_key),
                evidence_binding: evidence(),
                jobs: &jobs,
            }),
            Err(VerificationErrorCodeV1::PublicKeyBase64UrlInvalid),
            "public_key={public_key:?}"
        );
    }
    let zero_key_result = verify_unattested_phase_v1(PhaseVerificationInputV1 {
        declared_phase: VerificationPhaseV1::RequestOnly,
        key_binding: key_with("issuer.synthetic", "key.synthetic", 7, ZERO_KEY),
        evidence_binding: evidence(),
        jobs: &jobs,
    });
    assert!(matches!(
        zero_key_result,
        Err(VerificationErrorCodeV1::PublicKeyPointInvalid)
            | Err(VerificationErrorCodeV1::StrictSignatureInvalid(
                SignatureRoleV1::Request
            ))
    ));

    let mut noncanonical_signature_tail = REQUEST_SIGNATURE.to_owned();
    noncanonical_signature_tail.pop();
    noncanonical_signature_tail.push('h');
    let mut embedded_signature_space = REQUEST_SIGNATURE.to_owned();
    embedded_signature_space.replace_range(10..11, " ");
    let invalid_signatures = [
        REQUEST_SIGNATURE[..85].to_owned(),
        format!("{REQUEST_SIGNATURE}A"),
        format!("{REQUEST_SIGNATURE}="),
        format!(" {REQUEST_SIGNATURE}"),
        REQUEST_SIGNATURE.replace('_', "/"),
        format!("{}!", &REQUEST_SIGNATURE[..85]),
        format!("{}é", &REQUEST_SIGNATURE[..85]),
        embedded_signature_space,
        noncanonical_signature_tail,
    ];
    for signature in &invalid_signatures {
        let malformed = [SignatureJobInputV1 {
            signature_base64url: signature,
            ..request_job()
        }];
        assert_eq!(
            verify_unattested_phase_v1(PhaseVerificationInputV1 {
                declared_phase: VerificationPhaseV1::RequestOnly,
                key_binding: key(),
                evidence_binding: evidence(),
                jobs: &malformed,
            }),
            Err(VerificationErrorCodeV1::SignatureBase64UrlInvalid(
                SignatureRoleV1::Request
            )),
            "signature={signature:?}"
        );
    }
    let zero_signature = [SignatureJobInputV1 {
        signature_base64url: ZERO_SIGNATURE,
        ..request_job()
    }];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::RequestOnly,
            key_binding: key(),
            evidence_binding: evidence(),
            jobs: &zero_signature,
        }),
        Err(VerificationErrorCodeV1::StrictSignatureInvalid(
            SignatureRoleV1::Request
        ))
    );

    let ordered_structure = [
        SignatureJobInputV1 {
            signature_base64url: ZERO_SIGNATURE,
            ..request_job()
        },
        SignatureJobInputV1 {
            signature_base64url: "short",
            ..status_job()
        },
    ];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::SignedStatus,
            key_binding: key(),
            evidence_binding: evidence(),
            jobs: &ordered_structure,
        }),
        Err(VerificationErrorCodeV1::SignatureBase64UrlInvalid(
            SignatureRoleV1::SignedStatus
        ))
    );
}

#[test]
fn envelope_and_evidence_only_mutations_change_receipt_identity_not_crypto() {
    let baseline = verify_phase(VerificationPhaseV1::RequestOnly);
    let envelope_jobs = [SignatureJobInputV1 {
        role: SignatureRoleV1::Request,
        envelope_bytes: br#"{"envelope":"request-mutated-only"}"#,
        signed_material_bytes: REQUEST_MATERIAL,
        signature_base64url: REQUEST_SIGNATURE,
    }];
    let envelope_mutated = verify_unattested_phase_v1(PhaseVerificationInputV1 {
        declared_phase: VerificationPhaseV1::RequestOnly,
        key_binding: key(),
        evidence_binding: evidence(),
        jobs: &envelope_jobs,
    })
    .unwrap();
    assert_ne!(baseline.receipt_sha256(), envelope_mutated.receipt_sha256());

    let policy = br#"{"policy":"mutated"}"#;
    let overlay = br#"{"overlay":"mutated"}"#;
    let jobs = [request_job()];
    let evidence_mutated = verify_unattested_phase_v1(PhaseVerificationInputV1 {
        declared_phase: VerificationPhaseV1::RequestOnly,
        key_binding: key_with("issuer.changed", "key.changed", 8, PUBLIC_KEY),
        evidence_binding: evidence_with(
            "policy.changed",
            12,
            policy,
            overlay,
            "2222222222222222222222222222222222222222222222222222222222222222",
            "2026-07-12T19:00:00.000000Z",
        ),
        jobs: &jobs,
    })
    .unwrap();
    assert_ne!(baseline.receipt_sha256(), evidence_mutated.receipt_sha256());
    let receipt: Value = serde_json::from_slice(evidence_mutated.canonical_bytes()).unwrap();
    assert_eq!(receipt["semantic_phase_established"], false);
    assert_eq!(receipt["platform_attested"], false);
    assert_eq!(receipt["coordinator_eligible"], false);
}

#[test]
fn shared_response_domain_can_verify_relabel_but_never_semantic_phase() {
    let jobs = [
        request_job(),
        SignatureJobInputV1 {
            role: SignatureRoleV1::OuterTerminal,
            envelope_bytes: STATUS_ENVELOPE,
            signed_material_bytes: STATUS_MATERIAL,
            signature_base64url: STATUS_SIGNATURE,
        },
    ];
    let output = verify_unattested_phase_v1(PhaseVerificationInputV1 {
        declared_phase: VerificationPhaseV1::TerminalNoInner,
        key_binding: key(),
        evidence_binding: evidence(),
        jobs: &jobs,
    })
    .expect("shared domain permits cryptographic relabel only");
    let receipt: Value = serde_json::from_slice(output.canonical_bytes()).unwrap();
    assert_eq!(receipt["jobs"][1]["job_kind"], "OUTER_TERMINAL");
    assert_eq!(receipt["semantic_phase_established"], false);
    assert_eq!(receipt["envelope_payload_binding_established"], false);
    assert_eq!(receipt["coordinator_eligible"], false);
}

#[test]
fn metadata_usage_timestamp_and_integer_bounds_are_closed() {
    let jobs = [request_job()];
    for (binding, field) in [
        (
            key_with("Issuer", "key.synthetic", 7, PUBLIC_KEY),
            MetadataFieldV1::IssuerId,
        ),
        (
            KeyBindingInputV1 {
                issuer_id: "issuer.synthetic",
                key_id: "key.synthetic",
                usage: "OTHER_USAGE",
                key_generation: 7,
                public_key_base64url: PUBLIC_KEY,
            },
            MetadataFieldV1::Usage,
        ),
        (
            key_with("issuer.synthetic", "key.synthetic", 0, PUBLIC_KEY),
            MetadataFieldV1::KeyGeneration,
        ),
    ] {
        assert_eq!(
            verify_unattested_phase_v1(PhaseVerificationInputV1 {
                declared_phase: VerificationPhaseV1::RequestOnly,
                key_binding: binding,
                evidence_binding: evidence(),
                jobs: &jobs,
            }),
            Err(VerificationErrorCodeV1::MetadataInvalid(field))
        );
    }

    for timestamp in [
        "2026-02-30T00:00:00.000000Z",
        "2026-07-12T24:00:00.000000Z",
        "2026-07-12T18:58:46Z",
    ] {
        assert_eq!(
            verify_unattested_phase_v1(PhaseVerificationInputV1 {
                declared_phase: VerificationPhaseV1::RequestOnly,
                key_binding: key(),
                evidence_binding: evidence_with(
                    "policy.synthetic",
                    11,
                    POLICY_BYTES,
                    OVERLAY_BYTES,
                    PROVIDER_DIGEST,
                    timestamp,
                ),
                jobs: &jobs,
            }),
            Err(VerificationErrorCodeV1::MetadataInvalid(
                MetadataFieldV1::AdjudicatedAtClaim
            ))
        );
    }
}

#[test]
fn metadata_identifier_boundary_matrix_is_exact() {
    let baseline = verify_phase(VerificationPhaseV1::RequestOnly);
    let valid_values = [
        "a".to_owned(),
        "0".to_owned(),
        "a0b9".to_owned(),
        "0_.:-a9".to_owned(),
        "a_.:-".to_owned(),
        "a".repeat(128),
    ];
    let invalid_values = [
        "".to_owned(),
        "a".repeat(129),
        "_first".to_owned(),
        ".first".to_owned(),
        ":first".to_owned(),
        "-first".to_owned(),
        "Upper".to_owned(),
        "a/b".to_owned(),
        "a b".to_owned(),
        "a\"b".to_owned(),
        "a\\b".to_owned(),
        "a\0b".to_owned(),
        "aé".to_owned(),
    ];
    for field in [
        MetadataFieldV1::IssuerId,
        MetadataFieldV1::KeyId,
        MetadataFieldV1::TrustPolicyId,
    ] {
        for value in &valid_values {
            let output = verify_identifier_field(field, value).unwrap();
            assert_ne!(baseline.receipt_sha256(), output.receipt_sha256());
        }
        for value in &invalid_values {
            assert_eq!(
                verify_identifier_field(field, value),
                Err(VerificationErrorCodeV1::MetadataInvalid(field)),
                "field={field:?}, value={value:?}"
            );
        }
    }
}

#[test]
fn metadata_literal_integer_digest_and_time_boundary_matrix_is_exact() {
    let jobs = [request_job()];
    for usage in [
        "",
        "OTHER_USAGE",
        "ALR_TRUSTED_FIT_HANDSHAKE_SIGNING_EXTRA",
        "ALR_TRUSTED_FIT_HANDSHAKE_SIGNING\0",
        "alr_trusted_fit_handshake_signing",
    ] {
        assert_eq!(
            verify_unattested_phase_v1(PhaseVerificationInputV1 {
                declared_phase: VerificationPhaseV1::RequestOnly,
                key_binding: KeyBindingInputV1 {
                    issuer_id: "issuer.synthetic",
                    key_id: "key.synthetic",
                    usage,
                    key_generation: 7,
                    public_key_base64url: PUBLIC_KEY,
                },
                evidence_binding: evidence(),
                jobs: &jobs,
            }),
            Err(VerificationErrorCodeV1::MetadataInvalid(
                MetadataFieldV1::Usage
            ))
        );
    }
    for (generation, expected) in [
        (
            0,
            Err(VerificationErrorCodeV1::MetadataInvalid(
                MetadataFieldV1::KeyGeneration,
            )),
        ),
        (1, Ok(())),
        (9_223_372_036_854_775_807, Ok(())),
        (
            9_223_372_036_854_775_808,
            Err(VerificationErrorCodeV1::MetadataInvalid(
                MetadataFieldV1::KeyGeneration,
            )),
        ),
        (
            u64::MAX,
            Err(VerificationErrorCodeV1::MetadataInvalid(
                MetadataFieldV1::KeyGeneration,
            )),
        ),
    ] {
        let actual = verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::RequestOnly,
            key_binding: key_with("issuer.synthetic", "key.synthetic", generation, PUBLIC_KEY),
            evidence_binding: evidence(),
            jobs: &jobs,
        })
        .map(|_| ());
        assert_eq!(actual, expected);
    }
    for (epoch, expected) in [
        (
            0,
            Err(VerificationErrorCodeV1::MetadataInvalid(
                MetadataFieldV1::TrustPolicyEpoch,
            )),
        ),
        (1, Ok(())),
        (9_223_372_036_854_775_807, Ok(())),
        (
            9_223_372_036_854_775_808,
            Err(VerificationErrorCodeV1::MetadataInvalid(
                MetadataFieldV1::TrustPolicyEpoch,
            )),
        ),
        (
            u64::MAX,
            Err(VerificationErrorCodeV1::MetadataInvalid(
                MetadataFieldV1::TrustPolicyEpoch,
            )),
        ),
    ] {
        let actual = verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::RequestOnly,
            key_binding: key(),
            evidence_binding: evidence_with(
                "policy.synthetic",
                epoch,
                POLICY_BYTES,
                OVERLAY_BYTES,
                PROVIDER_DIGEST,
                ADJUDICATED_AT,
            ),
            jobs: &jobs,
        })
        .map(|_| ());
        assert_eq!(actual, expected);
    }

    let invalid_digests = [
        "1".repeat(63),
        "1".repeat(65),
        format!("{}A", "1".repeat(63)),
        format!("{}g", "1".repeat(63)),
        format!("{} ", "1".repeat(63)),
        format!("{}é", "1".repeat(62)),
    ];
    for digest in &invalid_digests {
        assert_eq!(
            verify_unattested_phase_v1(PhaseVerificationInputV1 {
                declared_phase: VerificationPhaseV1::RequestOnly,
                key_binding: key(),
                evidence_binding: evidence_with(
                    "policy.synthetic",
                    11,
                    POLICY_BYTES,
                    OVERLAY_BYTES,
                    digest,
                    ADJUDICATED_AT,
                ),
                jobs: &jobs,
            }),
            Err(VerificationErrorCodeV1::MetadataInvalid(
                MetadataFieldV1::ProviderEvidenceDigestSha256
            ))
        );
    }
    let alternate_valid_digest = "abcdef0123456789".repeat(4);
    assert!(verify_unattested_phase_v1(PhaseVerificationInputV1 {
        declared_phase: VerificationPhaseV1::RequestOnly,
        key_binding: key(),
        evidence_binding: evidence_with(
            "policy.synthetic",
            11,
            POLICY_BYTES,
            OVERLAY_BYTES,
            &alternate_valid_digest,
            ADJUDICATED_AT,
        ),
        jobs: &jobs,
    })
    .is_ok());

    for timestamp in [
        "0001-01-01T00:00:00.000000Z",
        "2000-02-29T00:00:00.000000Z",
        "2024-02-29T23:59:59.999999Z",
        "2100-02-28T00:00:00.000000Z",
        "9999-12-31T23:59:59.999999Z",
    ] {
        assert!(verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::RequestOnly,
            key_binding: key(),
            evidence_binding: evidence_with(
                "policy.synthetic",
                11,
                POLICY_BYTES,
                OVERLAY_BYTES,
                PROVIDER_DIGEST,
                timestamp,
            ),
            jobs: &jobs,
        })
        .is_ok());
    }
    for timestamp in [
        "0000-01-01T00:00:00.000000Z",
        "2023-02-29T00:00:00.000000Z",
        "1900-02-29T00:00:00.000000Z",
        "2100-02-29T00:00:00.000000Z",
        "2024-00-01T00:00:00.000000Z",
        "2024-13-01T00:00:00.000000Z",
        "2024-01-00T00:00:00.000000Z",
        "2024-01-32T00:00:00.000000Z",
        "2024-04-31T00:00:00.000000Z",
        "2024-06-31T00:00:00.000000Z",
        "2024-09-31T00:00:00.000000Z",
        "2024-11-31T00:00:00.000000Z",
        "2024-01-01T24:00:00.000000Z",
        "2024-01-01T00:60:00.000000Z",
        "2024-01-01T00:00:60.000000Z",
        "2024-01-01T00:00:00.00000Z",
        "2024-01-01T00:00:00.0000000Z",
        "2024-01-01T00:00:00.000000z",
        "2024-01-01T00:00:00.000000+00:00",
        "2024/01-01T00:00:00.000000Z",
        "2024-01-01 00:00:00.000000Z",
        "2024-01-01T00-00:00.000000Z",
        "20x4-01-01T00:00:00.000000Z",
        "2024-01-01T00:00:00.00000éZ",
    ] {
        assert_eq!(
            verify_unattested_phase_v1(PhaseVerificationInputV1 {
                declared_phase: VerificationPhaseV1::RequestOnly,
                key_binding: key(),
                evidence_binding: evidence_with(
                    "policy.synthetic",
                    11,
                    POLICY_BYTES,
                    OVERLAY_BYTES,
                    PROVIDER_DIGEST,
                    timestamp,
                ),
                jobs: &jobs,
            }),
            Err(VerificationErrorCodeV1::MetadataInvalid(
                MetadataFieldV1::AdjudicatedAtClaim
            ))
        );
    }
}

#[test]
fn aggregate_precedes_individual_bounds_then_metadata_and_crypto() {
    let one_mib = vec![b'a'; 1_048_576];
    let one_mib_plus_one = vec![b'a'; 1_048_577];
    let two_mib = vec![b'b'; 2_097_152];
    let policy = vec![b'{'; 1_048_576];
    let overlay = vec![b'}'; 1_048_576];
    let jobs = [
        SignatureJobInputV1 {
            role: SignatureRoleV1::Request,
            envelope_bytes: &one_mib_plus_one,
            signed_material_bytes: &one_mib,
            signature_base64url: REQUEST_SIGNATURE,
        },
        SignatureJobInputV1 {
            role: SignatureRoleV1::OuterTerminal,
            envelope_bytes: &two_mib,
            signed_material_bytes: &two_mib,
            signature_base64url: OUTER_SIGNATURE,
        },
        SignatureJobInputV1 {
            role: SignatureRoleV1::V159Inner,
            envelope_bytes: &one_mib,
            signed_material_bytes: &one_mib,
            signature_base64url: INNER_SIGNATURE,
        },
    ];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::TerminalSuccess,
            key_binding: key_with("Issuer", "key.synthetic", 7, "bad"),
            evidence_binding: evidence_with(
                "policy.synthetic",
                11,
                &policy,
                &overlay,
                PROVIDER_DIGEST,
                ADJUDICATED_AT,
            ),
            jobs: &jobs,
        }),
        Err(VerificationErrorCodeV1::AggregateInputTooLarge)
    );

    let jobs = [SignatureJobInputV1 {
        role: SignatureRoleV1::Request,
        envelope_bytes: &one_mib_plus_one,
        signed_material_bytes: REQUEST_MATERIAL,
        signature_base64url: REQUEST_SIGNATURE,
    }];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::RequestOnly,
            key_binding: key_with("Issuer", "key.synthetic", 7, "bad"),
            evidence_binding: evidence(),
            jobs: &jobs,
        }),
        Err(VerificationErrorCodeV1::MetadataInvalid(
            MetadataFieldV1::IssuerId
        ))
    );

    let jobs = [request_job()];
    let oversized_policy = vec![b'x'; 1_048_577];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::RequestOnly,
            key_binding: key(),
            evidence_binding: evidence_with(
                "policy.synthetic",
                11,
                &oversized_policy,
                OVERLAY_BYTES,
                PROVIDER_DIGEST,
                ADJUDICATED_AT,
            ),
            jobs: &jobs,
        }),
        Err(VerificationErrorCodeV1::BytesLengthInvalid(
            BytesFieldV1::TrustPolicySnapshot
        ))
    );
}

#[test]
fn byte_field_boundary_matrix_uses_exact_ten_variants() {
    let one = [b'x'];
    let two = [b'{', b'}'];
    let one_mib = vec![b'x'; 1_048_576];
    let one_mib_plus_one = vec![b'x'; 1_048_577];
    assert_eq!(
        verify_evidence_bytes(&one, OVERLAY_BYTES),
        Err(VerificationErrorCodeV1::BytesLengthInvalid(
            BytesFieldV1::TrustPolicySnapshot
        ))
    );
    assert!(verify_evidence_bytes(&two, OVERLAY_BYTES).is_ok());
    assert!(verify_evidence_bytes(&one_mib, OVERLAY_BYTES).is_ok());
    assert_eq!(
        verify_evidence_bytes(&one_mib_plus_one, OVERLAY_BYTES),
        Err(VerificationErrorCodeV1::BytesLengthInvalid(
            BytesFieldV1::TrustPolicySnapshot
        ))
    );
    assert_eq!(
        verify_evidence_bytes(POLICY_BYTES, &one),
        Err(VerificationErrorCodeV1::BytesLengthInvalid(
            BytesFieldV1::KeyStatusOverlay
        ))
    );
    assert!(verify_evidence_bytes(POLICY_BYTES, &two).is_ok());
    assert!(verify_evidence_bytes(POLICY_BYTES, &one_mib).is_ok());
    assert_eq!(
        verify_evidence_bytes(POLICY_BYTES, &one_mib_plus_one),
        Err(VerificationErrorCodeV1::BytesLengthInvalid(
            BytesFieldV1::KeyStatusOverlay
        ))
    );

    for (role, maximum, envelope_field, material_field, original_material) in [
        (
            SignatureRoleV1::Request,
            1_048_576,
            BytesFieldV1::RequestEnvelope,
            BytesFieldV1::RequestSignedMaterial,
            REQUEST_MATERIAL,
        ),
        (
            SignatureRoleV1::SignedStatus,
            2_097_152,
            BytesFieldV1::SignedStatusEnvelope,
            BytesFieldV1::SignedStatusSignedMaterial,
            STATUS_MATERIAL,
        ),
        (
            SignatureRoleV1::OuterTerminal,
            2_097_152,
            BytesFieldV1::OuterTerminalEnvelope,
            BytesFieldV1::OuterTerminalSignedMaterial,
            OUTER_MATERIAL,
        ),
        (
            SignatureRoleV1::V159Inner,
            1_048_576,
            BytesFieldV1::V159InnerEnvelope,
            BytesFieldV1::V159InnerSignedMaterial,
            INNER_MATERIAL,
        ),
    ] {
        let maximum_bytes = vec![b'e'; maximum];
        let oversized_bytes = vec![b'e'; maximum + 1];
        assert_eq!(
            verify_role_bytes(role, b"", original_material),
            Err(VerificationErrorCodeV1::BytesLengthInvalid(envelope_field))
        );
        assert!(verify_role_bytes(role, &one, original_material).is_ok());
        assert!(verify_role_bytes(role, &maximum_bytes, original_material).is_ok());
        assert_eq!(
            verify_role_bytes(role, &oversized_bytes, original_material),
            Err(VerificationErrorCodeV1::BytesLengthInvalid(envelope_field))
        );

        let original_envelope = match role {
            SignatureRoleV1::Request => REQUEST_ENVELOPE,
            SignatureRoleV1::SignedStatus => STATUS_ENVELOPE,
            SignatureRoleV1::OuterTerminal => OUTER_ENVELOPE,
            SignatureRoleV1::V159Inner => INNER_ENVELOPE,
        };
        assert_eq!(
            verify_role_bytes(role, original_envelope, b""),
            Err(VerificationErrorCodeV1::BytesLengthInvalid(material_field))
        );
        assert_eq!(
            verify_role_bytes(role, original_envelope, &one),
            Err(VerificationErrorCodeV1::StrictSignatureInvalid(role))
        );
        assert_eq!(
            verify_role_bytes(role, original_envelope, &maximum_bytes),
            Err(VerificationErrorCodeV1::StrictSignatureInvalid(role))
        );
        assert_eq!(
            verify_role_bytes(role, original_envelope, &oversized_bytes),
            Err(VerificationErrorCodeV1::BytesLengthInvalid(material_field))
        );
    }
}

#[test]
fn raw_slice_aggregate_cap_is_exact_and_text_is_excluded() {
    let policy = vec![b'p'; 1_048_576];
    let overlay = vec![b'o'; 1_048_576];
    let request_envelope = vec![b'e'; 1_048_576];
    let request_material = vec![b'r'; 1_048_576];
    let outer_envelope = vec![b'e'; 2_097_152];
    let outer_material = vec![b't'; 2_097_152];
    let inner_envelope = vec![b'e'; 1_048_576];
    let inner_material = vec![b'i'; 1_048_576];
    let identifier = "a".repeat(128);
    let jobs = [
        role_job_with(
            SignatureRoleV1::Request,
            &request_envelope,
            &request_material,
        ),
        role_job_with(
            SignatureRoleV1::OuterTerminal,
            &outer_envelope,
            &outer_material,
        ),
        role_job_with(SignatureRoleV1::V159Inner, &inner_envelope, &inner_material),
    ];
    let exact_cap = verify_unattested_phase_v1(PhaseVerificationInputV1 {
        declared_phase: VerificationPhaseV1::TerminalSuccess,
        key_binding: key_with(
            &identifier,
            &identifier,
            9_223_372_036_854_775_807,
            PUBLIC_KEY,
        ),
        evidence_binding: evidence_with(
            &identifier,
            9_223_372_036_854_775_807,
            &policy,
            &overlay,
            PROVIDER_DIGEST,
            ADJUDICATED_AT,
        ),
        jobs: &jobs,
    });
    assert_eq!(
        exact_cap,
        Err(VerificationErrorCodeV1::StrictSignatureInvalid(
            SignatureRoleV1::Request
        ))
    );

    let oversized_outer_envelope = vec![b'e'; 2_097_153];
    let oversized_jobs = [
        role_job_with(
            SignatureRoleV1::Request,
            &request_envelope,
            &request_material,
        ),
        role_job_with(
            SignatureRoleV1::OuterTerminal,
            &oversized_outer_envelope,
            &outer_material,
        ),
        role_job_with(SignatureRoleV1::V159Inner, &inner_envelope, &inner_material),
    ];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::TerminalSuccess,
            key_binding: key_with("INVALID", "key.synthetic", 7, "bad"),
            evidence_binding: evidence_with(
                "policy.synthetic",
                11,
                &policy,
                &overlay,
                PROVIDER_DIGEST,
                ADJUDICATED_AT,
            ),
            jobs: &oversized_jobs,
        }),
        Err(VerificationErrorCodeV1::AggregateInputTooLarge)
    );
}

#[test]
fn adjacent_first_error_precedence_matrix_is_total() {
    let request = [request_job()];
    let invalid_all = verify_unattested_phase_v1(PhaseVerificationInputV1 {
        declared_phase: VerificationPhaseV1::RequestOnly,
        key_binding: KeyBindingInputV1 {
            issuer_id: "INVALID",
            key_id: "INVALID",
            usage: "INVALID",
            key_generation: 0,
            public_key_base64url: "bad",
        },
        evidence_binding: evidence_with("INVALID", 0, b"", b"", "bad", "bad"),
        jobs: &request,
    });
    assert_eq!(
        invalid_all,
        Err(VerificationErrorCodeV1::MetadataInvalid(
            MetadataFieldV1::IssuerId
        ))
    );

    for (key_binding, evidence_binding, expected) in [
        (
            KeyBindingInputV1 {
                issuer_id: "issuer.synthetic",
                key_id: "INVALID",
                usage: "INVALID",
                key_generation: 0,
                public_key_base64url: "bad",
            },
            evidence_with("INVALID", 0, b"", b"", "bad", "bad"),
            MetadataFieldV1::KeyId,
        ),
        (
            KeyBindingInputV1 {
                issuer_id: "issuer.synthetic",
                key_id: "key.synthetic",
                usage: "INVALID",
                key_generation: 0,
                public_key_base64url: "bad",
            },
            evidence_with("INVALID", 0, b"", b"", "bad", "bad"),
            MetadataFieldV1::Usage,
        ),
        (
            KeyBindingInputV1 {
                issuer_id: "issuer.synthetic",
                key_id: "key.synthetic",
                usage: "ALR_TRUSTED_FIT_HANDSHAKE_SIGNING",
                key_generation: 0,
                public_key_base64url: "bad",
            },
            evidence_with("INVALID", 0, b"", b"", "bad", "bad"),
            MetadataFieldV1::KeyGeneration,
        ),
        (
            key_with("issuer.synthetic", "key.synthetic", 7, "bad"),
            evidence_with("INVALID", 0, b"", b"", "bad", "bad"),
            MetadataFieldV1::TrustPolicyId,
        ),
        (
            key_with("issuer.synthetic", "key.synthetic", 7, "bad"),
            evidence_with("policy.synthetic", 0, b"", b"", "bad", "bad"),
            MetadataFieldV1::TrustPolicyEpoch,
        ),
        (
            key_with("issuer.synthetic", "key.synthetic", 7, "bad"),
            evidence_with("policy.synthetic", 11, b"", b"", "bad", "bad"),
            MetadataFieldV1::ProviderEvidenceDigestSha256,
        ),
        (
            key_with("issuer.synthetic", "key.synthetic", 7, "bad"),
            evidence_with("policy.synthetic", 11, b"", b"", PROVIDER_DIGEST, "bad"),
            MetadataFieldV1::AdjudicatedAtClaim,
        ),
    ] {
        assert_eq!(
            verify_unattested_phase_v1(PhaseVerificationInputV1 {
                declared_phase: VerificationPhaseV1::RequestOnly,
                key_binding,
                evidence_binding,
                jobs: &request,
            }),
            Err(VerificationErrorCodeV1::MetadataInvalid(expected))
        );
    }

    let empty_request = [SignatureJobInputV1 {
        envelope_bytes: b"",
        signed_material_bytes: b"",
        ..request_job()
    }];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::RequestOnly,
            key_binding: key_with("issuer.synthetic", "key.synthetic", 7, "bad"),
            evidence_binding: evidence_with(
                "policy.synthetic",
                11,
                b"",
                b"",
                PROVIDER_DIGEST,
                ADJUDICATED_AT,
            ),
            jobs: &empty_request,
        }),
        Err(VerificationErrorCodeV1::BytesLengthInvalid(
            BytesFieldV1::TrustPolicySnapshot
        ))
    );
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::RequestOnly,
            key_binding: key_with("issuer.synthetic", "key.synthetic", 7, "bad"),
            evidence_binding: evidence_with(
                "policy.synthetic",
                11,
                POLICY_BYTES,
                b"",
                PROVIDER_DIGEST,
                ADJUDICATED_AT,
            ),
            jobs: &empty_request,
        }),
        Err(VerificationErrorCodeV1::BytesLengthInvalid(
            BytesFieldV1::KeyStatusOverlay
        ))
    );
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::RequestOnly,
            key_binding: key_with("issuer.synthetic", "key.synthetic", 7, "bad"),
            evidence_binding: evidence(),
            jobs: &empty_request,
        }),
        Err(VerificationErrorCodeV1::BytesLengthInvalid(
            BytesFieldV1::RequestEnvelope
        ))
    );
    let empty_request_material = [SignatureJobInputV1 {
        signed_material_bytes: b"",
        ..request_job()
    }];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::RequestOnly,
            key_binding: key_with("issuer.synthetic", "key.synthetic", 7, "bad"),
            evidence_binding: evidence(),
            jobs: &empty_request_material,
        }),
        Err(VerificationErrorCodeV1::BytesLengthInvalid(
            BytesFieldV1::RequestSignedMaterial
        ))
    );

    for (phase, jobs, expected) in [
        (
            VerificationPhaseV1::SignedStatus,
            vec![
                request_job(),
                SignatureJobInputV1 {
                    envelope_bytes: b"",
                    signed_material_bytes: b"",
                    ..status_job()
                },
            ],
            BytesFieldV1::SignedStatusEnvelope,
        ),
        (
            VerificationPhaseV1::SignedStatus,
            vec![
                request_job(),
                SignatureJobInputV1 {
                    signed_material_bytes: b"",
                    ..status_job()
                },
            ],
            BytesFieldV1::SignedStatusSignedMaterial,
        ),
        (
            VerificationPhaseV1::TerminalNoInner,
            vec![
                request_job(),
                SignatureJobInputV1 {
                    envelope_bytes: b"",
                    signed_material_bytes: b"",
                    ..outer_job()
                },
            ],
            BytesFieldV1::OuterTerminalEnvelope,
        ),
        (
            VerificationPhaseV1::TerminalNoInner,
            vec![
                request_job(),
                SignatureJobInputV1 {
                    signed_material_bytes: b"",
                    ..outer_job()
                },
            ],
            BytesFieldV1::OuterTerminalSignedMaterial,
        ),
        (
            VerificationPhaseV1::TerminalSuccess,
            vec![
                request_job(),
                outer_job(),
                SignatureJobInputV1 {
                    envelope_bytes: b"",
                    signed_material_bytes: b"",
                    ..inner_job()
                },
            ],
            BytesFieldV1::V159InnerEnvelope,
        ),
        (
            VerificationPhaseV1::TerminalSuccess,
            vec![
                request_job(),
                outer_job(),
                SignatureJobInputV1 {
                    signed_material_bytes: b"",
                    ..inner_job()
                },
            ],
            BytesFieldV1::V159InnerSignedMaterial,
        ),
    ] {
        assert_eq!(
            verify_unattested_phase_v1(PhaseVerificationInputV1 {
                declared_phase: phase,
                key_binding: key_with("issuer.synthetic", "key.synthetic", 7, "bad"),
                evidence_binding: evidence(),
                jobs: &jobs,
            }),
            Err(VerificationErrorCodeV1::BytesLengthInvalid(expected))
        );
    }

    let request_before_status = [
        SignatureJobInputV1 {
            signed_material_bytes: b"",
            ..request_job()
        },
        SignatureJobInputV1 {
            envelope_bytes: b"",
            ..status_job()
        },
    ];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::SignedStatus,
            key_binding: key(),
            evidence_binding: evidence(),
            jobs: &request_before_status,
        }),
        Err(VerificationErrorCodeV1::BytesLengthInvalid(
            BytesFieldV1::RequestSignedMaterial
        ))
    );
    let request_before_outer = [
        SignatureJobInputV1 {
            signed_material_bytes: b"",
            ..request_job()
        },
        SignatureJobInputV1 {
            envelope_bytes: b"",
            ..outer_job()
        },
    ];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::TerminalNoInner,
            key_binding: key(),
            evidence_binding: evidence(),
            jobs: &request_before_outer,
        }),
        Err(VerificationErrorCodeV1::BytesLengthInvalid(
            BytesFieldV1::RequestSignedMaterial
        ))
    );
    let outer_before_inner = [
        request_job(),
        SignatureJobInputV1 {
            signed_material_bytes: b"",
            ..outer_job()
        },
        SignatureJobInputV1 {
            envelope_bytes: b"",
            ..inner_job()
        },
    ];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::TerminalSuccess,
            key_binding: key(),
            evidence_binding: evidence(),
            jobs: &outer_before_inner,
        }),
        Err(VerificationErrorCodeV1::BytesLengthInvalid(
            BytesFieldV1::OuterTerminalSignedMaterial
        ))
    );

    let malformed_signature = [SignatureJobInputV1 {
        signature_base64url: "short",
        ..request_job()
    }];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::RequestOnly,
            key_binding: key_with("issuer.synthetic", "key.synthetic", 7, "bad"),
            evidence_binding: evidence(),
            jobs: &malformed_signature,
        }),
        Err(VerificationErrorCodeV1::PublicKeyBase64UrlInvalid)
    );
    let point_then_signature = [SignatureJobInputV1 {
        signature_base64url: "short",
        ..request_job()
    }];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::RequestOnly,
            key_binding: key_with(
                "issuer.synthetic",
                "key.synthetic",
                7,
                NONCANONICAL_POINT_KEY,
            ),
            evidence_binding: evidence(),
            jobs: &point_then_signature,
        }),
        Err(VerificationErrorCodeV1::PublicKeyPointInvalid)
    );
    let request_structure_before_status = [
        SignatureJobInputV1 {
            signature_base64url: "short",
            ..request_job()
        },
        SignatureJobInputV1 {
            signature_base64url: "short",
            ..status_job()
        },
    ];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::SignedStatus,
            key_binding: key(),
            evidence_binding: evidence(),
            jobs: &request_structure_before_status,
        }),
        Err(VerificationErrorCodeV1::SignatureBase64UrlInvalid(
            SignatureRoleV1::Request
        ))
    );
    let request_structure_before_outer = [
        SignatureJobInputV1 {
            signature_base64url: "short",
            ..request_job()
        },
        SignatureJobInputV1 {
            signature_base64url: "short",
            ..outer_job()
        },
    ];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::TerminalNoInner,
            key_binding: key(),
            evidence_binding: evidence(),
            jobs: &request_structure_before_outer,
        }),
        Err(VerificationErrorCodeV1::SignatureBase64UrlInvalid(
            SignatureRoleV1::Request
        ))
    );
    let outer_structure_before_inner = [
        request_job(),
        SignatureJobInputV1 {
            signature_base64url: "short",
            ..outer_job()
        },
        SignatureJobInputV1 {
            signature_base64url: "short",
            ..inner_job()
        },
    ];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::TerminalSuccess,
            key_binding: key(),
            evidence_binding: evidence(),
            jobs: &outer_structure_before_inner,
        }),
        Err(VerificationErrorCodeV1::SignatureBase64UrlInvalid(
            SignatureRoleV1::OuterTerminal
        ))
    );
    let later_status_structure_before_request_crypto = [
        SignatureJobInputV1 {
            signature_base64url: ZERO_SIGNATURE,
            ..request_job()
        },
        SignatureJobInputV1 {
            signature_base64url: "short",
            ..status_job()
        },
    ];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::SignedStatus,
            key_binding: key(),
            evidence_binding: evidence(),
            jobs: &later_status_structure_before_request_crypto,
        }),
        Err(VerificationErrorCodeV1::SignatureBase64UrlInvalid(
            SignatureRoleV1::SignedStatus
        ))
    );
    let later_outer_structure_before_request_crypto = [
        SignatureJobInputV1 {
            signature_base64url: ZERO_SIGNATURE,
            ..request_job()
        },
        SignatureJobInputV1 {
            signature_base64url: "short",
            ..outer_job()
        },
    ];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::TerminalNoInner,
            key_binding: key(),
            evidence_binding: evidence(),
            jobs: &later_outer_structure_before_request_crypto,
        }),
        Err(VerificationErrorCodeV1::SignatureBase64UrlInvalid(
            SignatureRoleV1::OuterTerminal
        ))
    );
    let later_inner_structure_before_outer_crypto = [
        request_job(),
        SignatureJobInputV1 {
            signature_base64url: ZERO_SIGNATURE,
            ..outer_job()
        },
        SignatureJobInputV1 {
            signature_base64url: "short",
            ..inner_job()
        },
    ];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::TerminalSuccess,
            key_binding: key(),
            evidence_binding: evidence(),
            jobs: &later_inner_structure_before_outer_crypto,
        }),
        Err(VerificationErrorCodeV1::SignatureBase64UrlInvalid(
            SignatureRoleV1::V159Inner
        ))
    );
    let strict_order = [
        SignatureJobInputV1 {
            signature_base64url: ZERO_SIGNATURE,
            ..request_job()
        },
        SignatureJobInputV1 {
            signature_base64url: ZERO_SIGNATURE,
            ..status_job()
        },
    ];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::SignedStatus,
            key_binding: key(),
            evidence_binding: evidence(),
            jobs: &strict_order,
        }),
        Err(VerificationErrorCodeV1::StrictSignatureInvalid(
            SignatureRoleV1::Request
        ))
    );
    let request_before_outer_strict = [
        SignatureJobInputV1 {
            signature_base64url: ZERO_SIGNATURE,
            ..request_job()
        },
        SignatureJobInputV1 {
            signature_base64url: ZERO_SIGNATURE,
            ..outer_job()
        },
    ];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::TerminalNoInner,
            key_binding: key(),
            evidence_binding: evidence(),
            jobs: &request_before_outer_strict,
        }),
        Err(VerificationErrorCodeV1::StrictSignatureInvalid(
            SignatureRoleV1::Request
        ))
    );
    let outer_before_inner_strict = [
        request_job(),
        SignatureJobInputV1 {
            signature_base64url: ZERO_SIGNATURE,
            ..outer_job()
        },
        SignatureJobInputV1 {
            signature_base64url: ZERO_SIGNATURE,
            ..inner_job()
        },
    ];
    assert_eq!(
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::TerminalSuccess,
            key_binding: key(),
            evidence_binding: evidence(),
            jobs: &outer_before_inner_strict,
        }),
        Err(VerificationErrorCodeV1::StrictSignatureInvalid(
            SignatureRoleV1::OuterTerminal
        ))
    );
}

fn assert_closed_no_unwind<F>(expected: VerificationErrorCodeV1, operation: F)
where
    F: FnOnce() -> Result<UnattestedVerificationOutputV1, VerificationErrorCodeV1>,
{
    let outcome = catch_unwind(AssertUnwindSafe(operation));
    assert!(outcome.is_ok());
    assert_eq!(outcome.unwrap(), Err(expected));
}

#[test]
fn malformed_input_matrix_never_unwinds() {
    let empty_jobs = [];
    assert_closed_no_unwind(VerificationErrorCodeV1::PhaseShapeInvalid, || {
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::RequestOnly,
            key_binding: key(),
            evidence_binding: evidence(),
            jobs: &empty_jobs,
        })
    });
    let extra_jobs = [request_job(), status_job()];
    assert_closed_no_unwind(VerificationErrorCodeV1::PhaseShapeInvalid, || {
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::RequestOnly,
            key_binding: key(),
            evidence_binding: evidence(),
            jobs: &extra_jobs,
        })
    });

    let oversized = vec![0_u8; 10_485_761];
    let aggregate_job = [SignatureJobInputV1 {
        envelope_bytes: &oversized,
        ..request_job()
    }];
    assert_closed_no_unwind(VerificationErrorCodeV1::AggregateInputTooLarge, || {
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::RequestOnly,
            key_binding: key(),
            evidence_binding: evidence(),
            jobs: &aggregate_job,
        })
    });

    let jobs = [request_job()];
    assert_closed_no_unwind(
        VerificationErrorCodeV1::MetadataInvalid(MetadataFieldV1::IssuerId),
        || {
            verify_unattested_phase_v1(PhaseVerificationInputV1 {
                declared_phase: VerificationPhaseV1::RequestOnly,
                key_binding: key_with("issuer\0é", "key.synthetic", 7, PUBLIC_KEY),
                evidence_binding: evidence(),
                jobs: &jobs,
            })
        },
    );
    assert_closed_no_unwind(
        VerificationErrorCodeV1::BytesLengthInvalid(BytesFieldV1::RequestEnvelope),
        || verify_role_bytes(SignatureRoleV1::Request, b"", REQUEST_MATERIAL),
    );
    assert_closed_no_unwind(VerificationErrorCodeV1::PublicKeyBase64UrlInvalid, || {
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::RequestOnly,
            key_binding: key_with("issuer.synthetic", "key.synthetic", 7, "é"),
            evidence_binding: evidence(),
            jobs: &jobs,
        })
    });
    assert_closed_no_unwind(VerificationErrorCodeV1::PublicKeyPointInvalid, || {
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::RequestOnly,
            key_binding: key_with(
                "issuer.synthetic",
                "key.synthetic",
                7,
                NONCANONICAL_POINT_KEY,
            ),
            evidence_binding: evidence(),
            jobs: &jobs,
        })
    });
    let malformed_signature = [SignatureJobInputV1 {
        signature_base64url: "\0é",
        ..request_job()
    }];
    assert_closed_no_unwind(
        VerificationErrorCodeV1::SignatureBase64UrlInvalid(SignatureRoleV1::Request),
        || {
            verify_unattested_phase_v1(PhaseVerificationInputV1 {
                declared_phase: VerificationPhaseV1::RequestOnly,
                key_binding: key(),
                evidence_binding: evidence(),
                jobs: &malformed_signature,
            })
        },
    );
    let binary_material = [0_u8, 0xff, 0x80, b'\n', b'\0'];
    assert_closed_no_unwind(
        VerificationErrorCodeV1::StrictSignatureInvalid(SignatureRoleV1::Request),
        || verify_role_bytes(SignatureRoleV1::Request, &[0, 0xff, 0x80], &binary_material),
    );

    let binary_envelope = [0_u8, 0xff, 0x80, b'\n', b'\0'];
    let binary_policy = [0xff, 0x80];
    let binary_overlay = [0_u8, 0xff, b'\n'];
    let binary_job = [SignatureJobInputV1 {
        envelope_bytes: &binary_envelope,
        ..request_job()
    }];
    let binary_outcome = catch_unwind(AssertUnwindSafe(|| {
        verify_unattested_phase_v1(PhaseVerificationInputV1 {
            declared_phase: VerificationPhaseV1::RequestOnly,
            key_binding: key(),
            evidence_binding: evidence_with(
                "policy.synthetic",
                11,
                &binary_policy,
                &binary_overlay,
                PROVIDER_DIGEST,
                ADJUDICATED_AT,
            ),
            jobs: &binary_job,
        })
    }));
    assert!(binary_outcome.is_ok());
    assert!(binary_outcome.unwrap().is_ok());
}

#[test]
fn all_public_debug_display_paths_redact_raw_and_numeric_sentinels() {
    let sentinel_envelope = b"LEAK_ENVELOPE_SENTINEL";
    let sentinel_material = b"LEAK_MATERIAL_SENTINEL";
    let sentinel_policy = b"LEAK_POLICY_SENTINEL";
    let sentinel_overlay = b"LEAK_OVERLAY_SENTINEL";
    let jobs = [SignatureJobInputV1 {
        role: SignatureRoleV1::Request,
        envelope_bytes: sentinel_envelope,
        signed_material_bytes: sentinel_material,
        signature_base64url: "LEAK_SIGNATURE_SENTINEL",
    }];
    let input = PhaseVerificationInputV1 {
        declared_phase: VerificationPhaseV1::RequestOnly,
        key_binding: key_with(
            "secret.issuer.sentinel",
            "secret.key.sentinel",
            8_765_432_101,
            "LEAK_PUBLIC_KEY_SENTINEL",
        ),
        evidence_binding: evidence_with(
            "secret.policy.sentinel",
            7_654_321_011,
            sentinel_policy,
            sentinel_overlay,
            "LEAK_PROVIDER_SENTINEL",
            "LEAK_TIME_SENTINEL",
        ),
        jobs: &jobs,
    };
    for rendered in [
        format!("{:?}", input.key_binding),
        format!("{:?}", input.evidence_binding),
        format!("{:?}", jobs[0]),
        format!("{input:?}"),
    ] {
        for sentinel in [
            "LEAK_ENVELOPE_SENTINEL",
            "LEAK_MATERIAL_SENTINEL",
            "LEAK_POLICY_SENTINEL",
            "LEAK_OVERLAY_SENTINEL",
            "LEAK_SIGNATURE_SENTINEL",
            "LEAK_PUBLIC_KEY_SENTINEL",
            "secret.issuer.sentinel",
            "secret.key.sentinel",
            "secret.policy.sentinel",
            "LEAK_PROVIDER_SENTINEL",
            "LEAK_TIME_SENTINEL",
            "8765432101",
            "7654321011",
        ] {
            assert!(!rendered.contains(sentinel), "{sentinel}");
        }
        assert!(rendered.contains("<redacted>"));
    }

    let output = verify_phase(VerificationPhaseV1::RequestOnly);
    let output_debug = format!("{output:?}");
    for raw in [
        PUBLIC_KEY,
        REQUEST_SIGNATURE,
        "issuer.synthetic",
        "synthetic-v1",
    ] {
        assert!(!output_debug.contains(raw));
    }
    let receipt_debug = format!("{:?}", output.receipt());
    let typed_job_debug = format!("{:?}", &output.receipt().jobs()[0]);
    let parsed = receipt_oracle_bytes(output.canonical_bytes()).unwrap();
    for raw in [
        PUBLIC_KEY,
        REQUEST_SIGNATURE,
        "issuer.synthetic",
        "synthetic-v1",
        &parsed.jobs[0].envelope_bytes_sha256,
        &parsed.jobs[0].signature_bytes_sha256,
    ] {
        assert!(!receipt_debug.contains(raw));
        assert!(!typed_job_debug.contains(raw));
    }
    assert!(typed_job_debug.contains("Request"));
    assert!(typed_job_debug.contains("envelope_bytes_len"));
    assert!(typed_job_debug.contains("<redacted>"));

    let error = VerificationErrorCodeV1::SignatureBase64UrlInvalid(SignatureRoleV1::Request);
    assert_eq!(format!("{error}"), "SIGNATURE_BASE64URL_INVALID:REQUEST");
    assert!(!format!("{error:?}").contains(REQUEST_SIGNATURE));

    for role in [
        SignatureRoleV1::Request,
        SignatureRoleV1::SignedStatus,
        SignatureRoleV1::OuterTerminal,
        SignatureRoleV1::V159Inner,
    ] {
        let debug = format!("{role:?}");
        let display = format!("{role}");
        assert!(!debug.contains("SENTINEL"));
        assert!(!display.contains("SENTINEL"));
    }
    for field in [
        MetadataFieldV1::IssuerId,
        MetadataFieldV1::KeyId,
        MetadataFieldV1::Usage,
        MetadataFieldV1::KeyGeneration,
        MetadataFieldV1::TrustPolicyId,
        MetadataFieldV1::TrustPolicyEpoch,
        MetadataFieldV1::ProviderEvidenceDigestSha256,
        MetadataFieldV1::AdjudicatedAtClaim,
    ] {
        let debug = format!("{field:?}");
        let display = format!("{field}");
        assert!(!debug.contains("SENTINEL"));
        assert!(!display.contains("SENTINEL"));
    }
    for error in [
        VerificationErrorCodeV1::PhaseShapeInvalid,
        VerificationErrorCodeV1::LengthOverflow,
        VerificationErrorCodeV1::AggregateInputTooLarge,
        VerificationErrorCodeV1::MetadataInvalid(MetadataFieldV1::IssuerId),
        VerificationErrorCodeV1::BytesLengthInvalid(BytesFieldV1::RequestEnvelope),
        VerificationErrorCodeV1::PublicKeyBase64UrlInvalid,
        VerificationErrorCodeV1::PublicKeyPointInvalid,
        VerificationErrorCodeV1::SignatureBase64UrlInvalid(SignatureRoleV1::Request),
        VerificationErrorCodeV1::StrictSignatureInvalid(SignatureRoleV1::Request),
        VerificationErrorCodeV1::CapacityAllocationFailed,
        VerificationErrorCodeV1::ReceiptEncodingInvariant,
        VerificationErrorCodeV1::ReceiptTooLarge,
    ] {
        let debug = format!("{error:?}");
        let display = format!("{error}");
        for sentinel in [
            "LEAK_ENVELOPE_SENTINEL",
            "LEAK_MATERIAL_SENTINEL",
            "LEAK_POLICY_SENTINEL",
            "LEAK_OVERLAY_SENTINEL",
            "LEAK_SIGNATURE_SENTINEL",
            "LEAK_PUBLIC_KEY_SENTINEL",
            "8765432101",
            "7654321011",
        ] {
            assert!(!debug.contains(sentinel));
            assert!(!display.contains(sentinel));
        }
    }
}

#[test]
fn exact_ten_byte_field_display_tags_are_fixed() {
    for (field, expected) in [
        (BytesFieldV1::TrustPolicySnapshot, "TRUST_POLICY_SNAPSHOT"),
        (BytesFieldV1::KeyStatusOverlay, "KEY_STATUS_OVERLAY"),
        (BytesFieldV1::RequestEnvelope, "REQUEST_ENVELOPE"),
        (
            BytesFieldV1::RequestSignedMaterial,
            "REQUEST_SIGNED_MATERIAL",
        ),
        (BytesFieldV1::SignedStatusEnvelope, "SIGNED_STATUS_ENVELOPE"),
        (
            BytesFieldV1::SignedStatusSignedMaterial,
            "SIGNED_STATUS_SIGNED_MATERIAL",
        ),
        (
            BytesFieldV1::OuterTerminalEnvelope,
            "OUTER_TERMINAL_ENVELOPE",
        ),
        (
            BytesFieldV1::OuterTerminalSignedMaterial,
            "OUTER_TERMINAL_SIGNED_MATERIAL",
        ),
        (BytesFieldV1::V159InnerEnvelope, "V159_INNER_ENVELOPE"),
        (
            BytesFieldV1::V159InnerSignedMaterial,
            "V159_INNER_SIGNED_MATERIAL",
        ),
    ] {
        assert_eq!(format!("{field}"), expected);
        assert!(!format!("{field:?}").contains("SENTINEL"));
    }
}

#[test]
fn no_public_input_can_smuggle_a_preimage_or_success_boolean() {
    let output = verify_phase(VerificationPhaseV1::RequestOnly);
    let receipt: Value = serde_json::from_slice(output.canonical_bytes()).unwrap();
    let evidence = receipt["evidence_binding"].as_object().unwrap();
    assert!(!evidence.contains_key("caller_preimage"));
    assert!(!evidence.contains_key("caller_receipt_digest"));
    assert!(!evidence.contains_key("platform_attested"));
    assert!(!evidence.contains_key("training_allowed"));
    assert!(!receipt
        .as_object()
        .unwrap()
        .contains_key("source_trust_tier"));
    assert_eq!(
        receipt["verification_primitive"],
        "ed25519_dalek_2.2.0_verify_strict_zip215"
    );
}

#[test]
fn evidence_object_is_exact_and_hashes_decoded_key_and_raw_snapshots() {
    let output = verify_phase(VerificationPhaseV1::RequestOnly);
    let receipt: Value = serde_json::from_slice(output.canonical_bytes()).unwrap();
    let evidence = &receipt["evidence_binding"];
    assert_eq!(evidence["issuer_id"], "issuer.synthetic");
    assert_eq!(evidence["key_generation"], 7);
    assert_eq!(evidence["trust_policy_epoch"], 11);
    assert_eq!(
        evidence["public_key_bytes_sha256"],
        "21fe31dfa154a261626bf854046fd2271b7bed4b6abe45aa58877ef47f9721b9"
    );
    assert_eq!(evidence["trust_policy_snapshot_bytes_len"], 2);
    assert_eq!(evidence["key_status_overlay_bytes_len"], 2);
    assert_eq!(evidence["usage"], "ALR_TRUSTED_FIT_HANDSHAKE_SIGNING");
}

#[test]
fn job_hashes_and_domains_match_independent_vector_recipe() {
    let output = verify_phase(VerificationPhaseV1::TerminalSuccess);
    let receipt: Value = serde_json::from_slice(output.canonical_bytes()).unwrap();
    let jobs = receipt["jobs"].as_array().unwrap();
    assert_eq!(jobs[0]["domain"], "ALR_TRUSTED_FIT_REQUEST_V1");
    assert_eq!(
        jobs[0]["preimage_bytes_sha256"],
        "783284c06317c4e5173b3cba358b2df509f0c19c591ad2d4fe4f6b623cba43cc"
    );
    assert_eq!(
        jobs[0]["signature_bytes_sha256"],
        "48e7cc9d1c603fb090d139bd38a1a1ad2ed52e4ee0bf5dd6be42952384ef0554"
    );
    assert_eq!(jobs[1]["domain"], "ALR_ISOLATED_FIT_TERMINAL_RECEIPT_V1");
    assert_eq!(
        jobs[1]["preimage_bytes_sha256"],
        "a31e2c1ef8d8b0a96323a1d65a01b8c5eb747d850dce7e5e1a1cd5787f15e73b"
    );
    assert_eq!(jobs[2]["domain"], "ALR_V159_INNER_FIT_RECEIPT_V1");
    assert_eq!(
        jobs[2]["preimage_bytes_sha256"],
        "6a9e93ed391984979d577745facedfe22b8b6e9d7a8f5d6f98543254e44c889e"
    );
}
