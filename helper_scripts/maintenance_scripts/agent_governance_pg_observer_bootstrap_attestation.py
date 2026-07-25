"""S2.0 observer-bootstrap 的 operator 授權 + apply attestation 加密葉層(W0a 真實性強化)。

從 :mod:`agent_governance_pg_observer_bootstrap` 抽出的**行為守恆**葉模組(§10.4 helper decomposition):
承載 pre-approval operator SSHSIG 授權(``build_operator_authorization`` /
``validate_operator_authorization`` 等)與 post-apply trusted-host attestation
(``build_apply_attestation`` / ``validate_apply_attestation`` 等)兩條加密 seam,連同它們共用的
基元葉助手(canonical bytes/時間解析/digest 投影/SSHSIG armor body 嚴格 base64 護欄)與 domain-separated
信任根常量。

**葉層守則(no cycle)。** 本模組只依賴 stdlib + ``agent_governance_aiml_trusted_host``(SSHSIG 信任根與
驗證基元)+ ``aiml_gate_receipt_validator``(canonical_digest)+ ``agent_governance_schema``
(schema_subset_errors);**絕不**反向匯入主模組 ``agent_governance_pg_observer_bootstrap``。主模組單向
``from`` 本模組再匯出所有被搬移的公開符號,故既有呼叫端
``agent_governance_pg_observer_bootstrap.<symbol>`` 一律仍解析到同一物件。

**誠實界線不變。** 純移位、零語義變更:不接觸生產 PG/psql/network/broker;operator 私鑰既不在 Mac 也不在
trade-core;canonical self-digest 只證完整性,不證誰執行、不證外部事實。domain separation(專屬 identity +
namespace)與 §9.1 信任根綁定的所有語義與搬移前逐位元相同。
"""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

# 唯讀消費:S1 target-host 的 SSHSIG 信任根與驗證基元;中央 validator 的 canonical_digest;schema 子集驗證器。
import agent_governance_aiml_trusted_host as trusted  # noqa: E402
import aiml_gate_receipt_validator as central_validator  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402


# canonical digest helper(重用中央 validator;本地 bytes 供 SSHSIG 驗證/簽章)。
canonical_digest = central_validator.canonical_digest

SCHEMA_DIR = ML_TRAINING_DIR / "schemas" / "aiml_gate_receipts"


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEAD_RE = re.compile(r"^[0-9a-f]{40}$")

# 生產 APPLIED 唯一可接受的 evidence 等級:只有真 Linux host driver 能回傳(平台背書);
# 任何注入的 simulation/disposable driver 的 LOCAL_REPRODUCIBLE/STRUCTURAL_ONLY 皆不足以令
# production_apply_performed=true(見 _apply_production_observer_bootstrap 的 step 9 閘)。
PRODUCTION_APPLIED_EVIDENCE_CLASS = "PLATFORM_ATTESTED"

EVIDENCE_TTL_SECONDS = 900


# ── operator SSHSIG 信任根(沿用 S0.3/S1 公鑰/指紋,專屬 identity + namespace 做 domain separation) ──
OPERATOR_AUTHORIZATION_SCHEMA_VERSION = "pg_observer_bootstrap_operator_authorization_v1"
OPERATOR_IDENTITY = "aiml-s2-observer-bootstrap-operator-v1"
OPERATOR_FINGERPRINT = trusted.EXPECTED_S1_TARGET_HOST_SIGNER_FINGERPRINT
OPERATOR_PUBLIC_KEY = trusted.S1_TRUSTED_TARGET_HOST_PUBLIC_KEY
OPERATOR_ALGORITHM = trusted.EXECUTION_BUNDLE_ALGORITHM
OPERATOR_SIGNATURE_NAMESPACE = "arcane-equilibrium-aiml-s2-observer-bootstrap"
MAX_AUTHORIZATION_TTL = timedelta(minutes=15)
AUTHORIZATION_FIELDS = frozenset({
    "schema_version", "signer_identity", "signer_fingerprint", "algorithm",
    "signature_namespace", "intent_id", "intent_digest", "source_head",
    "target_host", "applier_node_id", "postcheck_node_id",
    "issued_at", "expires_at", "authorization_digest",
})

# ── W0a apply-time trusted-host attestation(post-apply 平台背書;沿用 §9.1 信任根公鑰/指紋,以**專屬
#    attestor identity + namespace** 與 pre-approval operator authorization 做 domain separation) ──
# operator authorization 是**簽在 apply 之前**的 exact intent pre-approval;apply attestation 則是
# **apply 之後**綁定實觀的 applied_grant_set_digest + 真 trusted_host_time 的 post-apply 證據(只有 apply
# 跑完才可知)。若共用一個 namespace,一張 pre-approval SSHSIG 可被當作 attestation 重放;ssh-keygen -Y
# verify 綁 namespace,故專屬 namespace 令兩件簽章不可互換,同時共用同一把實體信任根鑰(即 §9.1 pattern)。
APPLY_ATTESTATION_SCHEMA_VERSION = "pg_observer_bootstrap_apply_attestation_v1"
ATTESTOR_IDENTITY = "aiml-s2-observer-bootstrap-attestor-v1"
ATTESTOR_FINGERPRINT = trusted.EXPECTED_S1_TARGET_HOST_SIGNER_FINGERPRINT
ATTESTOR_PUBLIC_KEY = trusted.S1_TRUSTED_TARGET_HOST_PUBLIC_KEY
ATTESTOR_ALGORITHM = trusted.EXECUTION_BUNDLE_ALGORITHM
APPLY_ATTESTATION_NAMESPACE = "arcane-equilibrium-aiml-s2-observer-bootstrap-apply"
MAX_APPLY_ATTESTATION_TTL = timedelta(minutes=15)
ATTESTATION_FIELDS = frozenset({
    "schema_version", "attestor_identity", "attestor_fingerprint", "algorithm",
    "signature_namespace", "intent_id", "intent_digest", "source_head", "target_host",
    "applier_node_id", "postcheck_node_id", "applied_grant_set_digest", "reobserved_digest",
    "evidence_class", "trusted_host_time", "attestation_expires_at", "attestation_digest",
})
APPLY_ATTESTATION_SCHEMA_PATH = SCHEMA_DIR / f"{APPLY_ATTESTATION_SCHEMA_VERSION}.schema.json"


class PgObserverBootstrapError(RuntimeError):
    """Base for a would-be observer artifact that cannot be safely emitted (fail-closed)."""


class SecretLeakageError(PgObserverBootstrapError):
    """Raised when a would-be artifact field carries secret-like content."""


# 機密掃描(沿用 S1.1/S1.3/S1.5 樣態:github token / credential 賦值 / auth header / postgres DSN 憑證形)。
SECRET_LIKE_RE = re.compile(
    r"(?:github_pat_|gh[pousr]_[A-Za-z0-9]{12,})"
    r"|(?:access[_-]?token|auth(?:orization)?|client[_-]?secret|password|"
    r"pgpassword|private[_-]?key)\s*[:=]"
    r"|(?:basic|bearer)\s+[A-Za-z0-9._~+/=-]{12,}"
    r"|postgres(?:ql)?://[^\s:/@]+:[^\s:/@]+@",
    re.IGNORECASE,
)


def _contains_secret_like(value: Any) -> bool:
    if isinstance(value, str):
        return SECRET_LIKE_RE.search(value) is not None
    if isinstance(value, list):
        return any(_contains_secret_like(item) for item in value)
    if isinstance(value, dict):
        return any(
            _contains_secret_like(key) or _contains_secret_like(item)
            for key, item in value.items()
        )
    return False


def _guard_no_secret(payload: Any) -> None:
    if _contains_secret_like(payload):
        raise SecretLeakageError("observer-bootstrap payload carries secret-like content")


def canonical_bytes(value: Any) -> bytes:
    """Return the exact bytes the operator signs / the SSHSIG is verified against."""

    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


@lru_cache(maxsize=None)
def _schema(path_str: str) -> dict[str, Any]:
    return json.loads(Path(path_str).read_text(encoding="utf-8"))


def _parse_time(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone is required")
    return parsed.astimezone(timezone.utc)


def _plus_seconds(iso: str, seconds: int) -> str:
    return (_parse_time(iso) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def intent_self_digest(intent: dict[str, Any]) -> str:
    return canonical_digest({k: v for k, v in intent.items() if k != "self_digest"})


def authorization_digest(value: dict[str, Any]) -> str:
    return canonical_digest({k: v for k, v in value.items() if k != "authorization_digest"})


def apply_attestation_digest(value: dict[str, Any]) -> str:
    return canonical_digest({k: v for k, v in value.items() if k != "attestation_digest"})


# operator_signature_pem 的 SSHSIG armor 標記列(去 armor 時據此剝除,取得純 body)。
_SSH_SIGNATURE_ARMOR_MARKERS = (
    "-----BEGIN SSH SIGNATURE-----",
    "-----END SSH SIGNATURE-----",
)


def _operator_signature_pem_body_is_strict_base64(value: str) -> bool:
    """去 armor(剝除 BEGIN/END 標記列 + 所有換行、串接)後,判斷 body 是否為嚴格標準 base64。

    真正的 ``ssh-keygen -Y sign`` armor body 去 armor 後是合法標準 base64,
    ``base64.b64decode(body, validate=True)`` 成功;plaintext 憑證形一律 decode 失敗:
    ``password=hunter2`` / ``pgpassword=…`` 的 ``=`` 落在字串中段=非法 padding(Non-base64 digit),
    ``bearer\\nAAAA…`` 去 armor 後長度不可解(Incorrect padding),armor-wrapped DSN 亦含非 base64 字元。
    FIX-10(E2 P2):body 一旦被證明是嚴格 base64,就不可能夾帶可讀的 plaintext ``password=`` /
    ``pgpassword=`` / ``bearer …`` / DSN 機密,故 ``_result_secret_scan_view`` 排除此欄位可證安全。
    非字串 / 空 body / 不可 decode 一律回 False(fail-closed)。
    """

    if not isinstance(value, str):
        return False
    body = "".join(
        line for line in value.split("\n") if line not in _SSH_SIGNATURE_ARMOR_MARKERS
    )
    if not body:
        return False
    try:
        base64.b64decode(body, validate=True)
    except (binascii.Error, ValueError):
        return False
    return True


def _guard_operator_signature_pem_body(value: Any) -> None:
    # FIX-10(E2 P2)build 期護欄:APPLIED result 的 operator_signature_pem 若為非 None 字串,其 armor body
    # 必為嚴格 base64,否則絕不 emit(fail-closed)。與 validate 期同一判準對稱,確保 build 永遠不會產出
    # 「armor 外殼合法但 body 夾帶可讀 plaintext」的簽章欄位。
    if value is not None and not _operator_signature_pem_body_is_strict_base64(value):
        raise SecretLeakageError(
            "operator_signature_pem body is not strict base64 (possible non-signature payload)"
        )


def _guard_apply_attestation_signature_pem_body(value: Any) -> None:
    # W0a(§4):與 operator_signature_pem 對稱——apply_attestation_signature_pem 若為非 None 字串,其 armor
    # body 必為嚴格 base64,否則 build 期絕不 emit(fail-closed),確保公開簽章欄位不夾帶可讀 plaintext 機密。
    if value is not None and not _operator_signature_pem_body_is_strict_base64(value):
        raise SecretLeakageError(
            "apply_attestation_signature_pem body is not strict base64 (possible non-signature payload)"
        )


# --------------------------------------------------------------------------- #
# operator SSHSIG authorization (reuse the S1 pattern; NEW namespace + identity)
# --------------------------------------------------------------------------- #
def build_operator_authorization(*, intent: dict[str, Any], source_head: str) -> dict[str, Any]:
    """Project one exact typed observer intent into the bytes the operator signs."""

    if not isinstance(intent, dict):
        raise PgObserverBootstrapError("operator authorization intent must be an object")
    if not HEAD_RE.fullmatch(str(source_head)):
        raise PgObserverBootstrapError("operator authorization source_head must be exact 40-hex")
    for field in ("intent_id", "self_digest", "target_host", "applier_node_id", "postcheck_node_id", "created_at", "expires_at"):
        if not intent.get(field):
            raise PgObserverBootstrapError(f"operator authorization intent lacks required field {field}")
    if not DIGEST_RE.fullmatch(str(intent["intent_id"])):
        raise PgObserverBootstrapError("operator authorization intent_id must be a sha256 digest")
    if intent["self_digest"] != intent_self_digest(intent):
        raise PgObserverBootstrapError("operator authorization intent self_digest does not match its bytes")
    issued = _parse_time(intent["created_at"])
    intent_expiry = _parse_time(intent["expires_at"])
    expires = min(intent_expiry, issued + MAX_AUTHORIZATION_TTL)
    if expires <= issued:
        raise PgObserverBootstrapError("operator authorization intent interval is invalid")
    authorization: dict[str, Any] = {
        "schema_version": OPERATOR_AUTHORIZATION_SCHEMA_VERSION,
        "signer_identity": OPERATOR_IDENTITY,
        "signer_fingerprint": OPERATOR_FINGERPRINT,
        "algorithm": OPERATOR_ALGORITHM,
        "signature_namespace": OPERATOR_SIGNATURE_NAMESPACE,
        "intent_id": intent["intent_id"],
        "intent_digest": intent["self_digest"],
        "source_head": source_head,
        "target_host": intent["target_host"],
        "applier_node_id": intent["applier_node_id"],
        "postcheck_node_id": intent["postcheck_node_id"],
        "issued_at": issued.isoformat().replace("+00:00", "Z"),
        "expires_at": expires.isoformat().replace("+00:00", "Z"),
    }
    authorization["authorization_digest"] = authorization_digest(authorization)
    return authorization


def validate_operator_authorization(
    authorization: Any,
    signature: Any,
    *,
    intent: dict[str, Any],
    source_head: str,
    now: str,
) -> list[str]:
    """Validate structure, exact-intent bindings, time window, trust root, and SSHSIG."""

    errors: list[str] = []
    if not isinstance(authorization, dict):
        return ["operator authorization must be an object"]
    if not isinstance(signature, (bytes, bytearray)):
        errors.append("operator authorization signature must be raw SSHSIG bytes")
        signature = b""
    if set(authorization) != AUTHORIZATION_FIELDS:
        return ["operator authorization fields do not match the exact contract"]
    if authorization.get("schema_version") != OPERATOR_AUTHORIZATION_SCHEMA_VERSION:
        errors.append("operator authorization schema_version is invalid")
    for field, expected in (
        ("signer_identity", OPERATOR_IDENTITY),
        ("signer_fingerprint", OPERATOR_FINGERPRINT),
        ("algorithm", OPERATOR_ALGORITHM),
        ("signature_namespace", OPERATOR_SIGNATURE_NAMESPACE),
    ):
        if authorization.get(field) != expected:
            errors.append(f"operator authorization {field} is invalid")
    if authorization.get("authorization_digest") != authorization_digest(authorization):
        errors.append("operator authorization digest mismatch")
    if not HEAD_RE.fullmatch(str(source_head)):
        errors.append("operator authorization expected source head is invalid")
    if authorization.get("source_head") != source_head:
        errors.append("operator authorization source head differs from the effect")
    if not isinstance(intent, dict):
        errors.append("operator authorization exact intent is missing")
        intent = {}
    elif intent.get("self_digest") != intent_self_digest(intent):
        errors.append("operator authorization exact intent self_digest is invalid")
    for auth_field, intent_field in (
        ("intent_id", "intent_id"),
        ("intent_digest", "self_digest"),
        ("target_host", "target_host"),
        ("applier_node_id", "applier_node_id"),
        ("postcheck_node_id", "postcheck_node_id"),
    ):
        if authorization.get(auth_field) != intent.get(intent_field):
            errors.append(f"operator authorization {auth_field} differs from the exact intent")
    try:
        issued = _parse_time(authorization["issued_at"])
        expires = _parse_time(authorization["expires_at"])
        current = _parse_time(now)
        intent_created = _parse_time(intent["created_at"])
        intent_expires = _parse_time(intent["expires_at"])
        if issued != intent_created:
            errors.append("operator authorization issued_at differs from intent created_at")
        if not issued <= current < expires:
            errors.append("operator authorization is not currently valid")
        if expires > intent_expires:
            errors.append("operator authorization outlives its exact intent")
        if expires - issued > MAX_AUTHORIZATION_TTL:
            errors.append("operator authorization TTL exceeds fifteen minutes")
    except (KeyError, TypeError, ValueError):
        errors.append("operator authorization timestamps are invalid")
    try:
        actual_fingerprint = trusted.ssh_public_key_fingerprint(OPERATOR_PUBLIC_KEY)
    except ValueError:
        actual_fingerprint = ""
    if not hmac.compare_digest(actual_fingerprint, OPERATOR_FINGERPRINT):
        errors.append("operator authorization trust-root fingerprint mismatch")
    if not trusted._verify_ssh_signature(
        canonical_bytes(authorization),
        bytes(signature),
        public_key=OPERATOR_PUBLIC_KEY,
        identity=OPERATOR_IDENTITY,
        namespace=OPERATOR_SIGNATURE_NAMESPACE,
    ):
        errors.append("operator authorization SSH signature is invalid")
    return errors


def _operator_authorization_is_valid(
    authorization: Any, signature: Any, *, intent: dict[str, Any], source_head: str, now: str
) -> tuple[bool, str]:
    if not isinstance(authorization, dict) or not isinstance(signature, (bytes, bytearray)):
        return False, "operator SSHSIG is absent (an exact signed intent is required)"
    errors = validate_operator_authorization(
        authorization, signature, intent=intent, source_head=source_head, now=now
    )
    if errors:
        return False, "operator SSHSIG invalid: " + "; ".join(errors[:2])
    return True, ""


def operator_authorization_binding_errors(
    authorization: Any, *, intent_id: Any, intent_digest: Any, source_head: Any
) -> list[str]:
    """STRUCTURAL-only operator_authorization binding for an emitted APPLIED receipt.

    誠實界線(**只證完整性,不證真偽**):此處只驗「精確欄位契約 + domain-separation 常量 +
    authorization_digest 完整性 + 三個 intent 綁定(intent_id/intent_digest/source_head 等於 receipt)」。
    它**刻意不**做 SSHSIG 密碼學再驗(``_verify_ssh_signature``)也不做 trust-root 指紋/平台背書——
    真正對 operator 公鑰的 SSHSIG 再驗 + platform attestation 屬 S2.0 EFFECT session。可拋棄 APPLIED
    receipt 由**每測試臨時**金鑰簽章(非固定信任根),離線密碼學再驗在設計上不可行,故此結構綁定
    只把 ``{"totally":"bogus"}`` 及任何 intent 不符的授權擋掉,絕不宣稱已認證是誰簽的。
    """

    if not isinstance(authorization, dict):
        return ["operator authorization must be a well-formed object"]
    if set(authorization) != AUTHORIZATION_FIELDS:
        return ["operator authorization fields do not match the exact contract"]
    errors: list[str] = []
    for field, expected in (
        ("schema_version", OPERATOR_AUTHORIZATION_SCHEMA_VERSION),
        ("signer_identity", OPERATOR_IDENTITY),
        ("algorithm", OPERATOR_ALGORITHM),
        ("signature_namespace", OPERATOR_SIGNATURE_NAMESPACE),
    ):
        if authorization.get(field) != expected:
            errors.append(f"operator authorization {field} is invalid")
    if authorization.get("authorization_digest") != authorization_digest(authorization):
        errors.append("operator authorization digest mismatch")
    for auth_field, expected in (
        ("intent_id", intent_id),
        ("intent_digest", intent_digest),
        ("source_head", source_head),
    ):
        if authorization.get(auth_field) != expected:
            errors.append(f"operator authorization {auth_field} is not bound to the result")
    return errors


# --------------------------------------------------------------------------- #
# W0a apply-time trusted-host attestation (T1 + T2 + T5) — the real APPLIED unlock
# --------------------------------------------------------------------------- #
def build_apply_attestation(
    *,
    intent: dict[str, Any],
    applied_grant_set_digest: str,
    reobserved_digest: str,
    trusted_host_time: str,
    ttl_seconds: int = EVIDENCE_TTL_SECONDS,
) -> dict[str, Any]:
    """Project the canonical ``pg_observer_bootstrap_apply_attestation_v1`` object to sign.

    Analogue of :func:`build_operator_authorization` but **post-apply**: it binds the applied
    catalog digest and the DISTINCT verifier's ``reobserved_digest`` (== applied, T2 at build) and
    a trusted-host-signed ``trusted_host_time`` (T5 anchor).  The caller signs
    ``canonical_bytes(attestation)`` under the observer-bootstrap-apply namespace with the §9.1
    trust-root private key (off Mac/trade-core).
    """

    if not isinstance(intent, dict):
        raise PgObserverBootstrapError("apply attestation intent must be an object")
    for field in ("intent_id", "self_digest", "source_head", "target_host", "applier_node_id", "postcheck_node_id"):
        if not intent.get(field):
            raise PgObserverBootstrapError(f"apply attestation intent lacks required field {field}")
    if not DIGEST_RE.fullmatch(str(applied_grant_set_digest)):
        raise PgObserverBootstrapError("apply attestation applied_grant_set_digest must be a sha256 digest")
    if not DIGEST_RE.fullmatch(str(reobserved_digest)):
        raise PgObserverBootstrapError("apply attestation reobserved_digest must be a sha256 digest")
    if reobserved_digest != applied_grant_set_digest:
        raise PgObserverBootstrapError(
            "apply attestation reobserved_digest must equal applied_grant_set_digest (T2 at build)"
        )
    trusted_time = _parse_time(trusted_host_time)
    expires = trusted_time + timedelta(seconds=ttl_seconds)
    attestation: dict[str, Any] = {
        "schema_version": APPLY_ATTESTATION_SCHEMA_VERSION,
        "attestor_identity": ATTESTOR_IDENTITY,
        "attestor_fingerprint": ATTESTOR_FINGERPRINT,
        "algorithm": ATTESTOR_ALGORITHM,
        "signature_namespace": APPLY_ATTESTATION_NAMESPACE,
        "intent_id": intent["intent_id"],
        "intent_digest": intent["self_digest"],
        "source_head": intent["source_head"],
        "target_host": intent["target_host"],
        "applier_node_id": intent["applier_node_id"],
        "postcheck_node_id": intent["postcheck_node_id"],
        "applied_grant_set_digest": applied_grant_set_digest,
        "reobserved_digest": reobserved_digest,
        "evidence_class": PRODUCTION_APPLIED_EVIDENCE_CLASS,
        "trusted_host_time": trusted_time.isoformat().replace("+00:00", "Z"),
        "attestation_expires_at": expires.isoformat().replace("+00:00", "Z"),
    }
    attestation["attestation_digest"] = apply_attestation_digest(attestation)
    _guard_no_secret(attestation)
    return attestation


def validate_apply_attestation(
    attestation: Any,
    signature: Any,
    *,
    intent: dict[str, Any],
    operator_authorization: Any,
    applied_grant_set_digest: str,
) -> list[str]:
    """Apply-time crypto gate that unlocks ``APPLIED`` (returns ``[]`` iff all hold).

    Maps to the P1 findings:
      * structure + exact-field contract + domain-separation consts + attestation_digest (T1);
      * exact-intent binding of id/digest/source_head/target_host/applier/postcheck (T1);
      * ``reobserved_digest == applied_grant_set_digest == <runtime applied>`` (T2);
      * §9.1 trust-root fingerprint binding + real SSHSIG over ``canonical_bytes(attestation)`` (T1);
      * freshness derived from the **signed** ``trusted_host_time`` (inside the intent AND the
        operator-authorization windows, and within a bounded attestation TTL) — NEVER the caller
        ``now``, so a replayed expired intent with a historical caller ``now`` fails because the
        signed apply time is past expiry (T5).

    A bare ``evidence_class`` attribute is no longer sufficient; only a valid signed attestation is.
    """

    if not isinstance(attestation, dict):
        return ["apply attestation must be an object"]
    if not isinstance(signature, (bytes, bytearray)):
        return ["apply attestation signature must be raw SSHSIG bytes"]
    if set(attestation) != ATTESTATION_FIELDS:
        return ["apply attestation fields do not match the exact contract"]
    errors: list[str] = []
    schema = _schema(str(APPLY_ATTESTATION_SCHEMA_PATH))
    errors.extend(
        f"apply attestation schema violation: {error}"
        for error in schema_subset_errors(attestation, schema, schema)
    )
    for field, expected in (
        ("schema_version", APPLY_ATTESTATION_SCHEMA_VERSION),
        ("attestor_identity", ATTESTOR_IDENTITY),
        ("attestor_fingerprint", ATTESTOR_FINGERPRINT),
        ("algorithm", ATTESTOR_ALGORITHM),
        ("signature_namespace", APPLY_ATTESTATION_NAMESPACE),
        ("evidence_class", PRODUCTION_APPLIED_EVIDENCE_CLASS),
    ):
        if attestation.get(field) != expected:
            errors.append(f"apply attestation {field} is invalid")
    if attestation.get("attestation_digest") != apply_attestation_digest(attestation):
        errors.append("apply attestation digest mismatch")
    # T1 scope — exact intent binding.
    if not isinstance(intent, dict):
        errors.append("apply attestation exact intent is missing")
        intent = {}
    elif intent.get("self_digest") != intent_self_digest(intent):
        errors.append("apply attestation exact intent self_digest is invalid")
    for att_field, intent_field in (
        ("intent_id", "intent_id"),
        ("intent_digest", "self_digest"),
        ("source_head", "source_head"),
        ("target_host", "target_host"),
        ("applier_node_id", "applier_node_id"),
        ("postcheck_node_id", "postcheck_node_id"),
    ):
        if attestation.get(att_field) != intent.get(intent_field):
            errors.append(f"apply attestation {att_field} differs from the exact intent")
    # T2 — the verifier's reobserved digest must equal the applied catalog digest AND the runtime applied.
    if not DIGEST_RE.fullmatch(str(applied_grant_set_digest or "")):
        errors.append("apply attestation runtime applied digest is invalid")
    if not (attestation.get("reobserved_digest") == attestation.get("applied_grant_set_digest") == applied_grant_set_digest):
        errors.append(
            "apply attestation reobserved_digest must equal applied_grant_set_digest and the runtime applied digest (T2)"
        )
    # T1 — trust-root fingerprint binding + real SSHSIG verification (the real gate, not evidence_class).
    try:
        actual_fingerprint = trusted.ssh_public_key_fingerprint(ATTESTOR_PUBLIC_KEY)
    except ValueError:
        actual_fingerprint = ""
    if not hmac.compare_digest(actual_fingerprint, ATTESTOR_FINGERPRINT):
        errors.append("apply attestation trust-root fingerprint mismatch")
    if not trusted._verify_ssh_signature(
        canonical_bytes(attestation),
        bytes(signature),
        public_key=ATTESTOR_PUBLIC_KEY,
        identity=ATTESTOR_IDENTITY,
        namespace=APPLY_ATTESTATION_NAMESPACE,
    ):
        errors.append("apply attestation SSH signature is invalid")
    # T5 — freshness from the SIGNED trusted_host_time only (never the caller now).
    try:
        trusted_time = _parse_time(attestation["trusted_host_time"])
        attestation_expires = _parse_time(attestation["attestation_expires_at"])
        intent_created = _parse_time(intent["created_at"])
        intent_expires = _parse_time(intent["expires_at"])
        if not intent_created <= trusted_time < intent_expires:
            errors.append("apply attestation trusted_host_time is outside the intent window")
        if isinstance(operator_authorization, dict):
            auth_issued = _parse_time(operator_authorization["issued_at"])
            auth_expires = _parse_time(operator_authorization["expires_at"])
            if not auth_issued <= trusted_time < auth_expires:
                errors.append("apply attestation trusted_host_time is outside the operator-authorization window")
        else:
            errors.append("apply attestation requires the pre-approval operator authorization window")
        if not trusted_time < attestation_expires:
            errors.append("apply attestation trusted_host_time must precede attestation_expires_at")
        if attestation_expires - trusted_time > MAX_APPLY_ATTESTATION_TTL:
            errors.append("apply attestation TTL exceeds its ceiling")
    except (KeyError, TypeError, ValueError):
        errors.append("apply attestation timestamps are invalid")
    return errors


def _apply_attestation_binding_errors(
    attestation: Any,
    signature_pem: Any,
    *,
    intent_id: Any,
    intent_digest: Any,
    source_head: Any,
    applied_grant_set_digest: Any,
    operator_authorization: Any,
) -> list[str]:
    """STRUCTURAL-only apply-attestation binding for an emitted APPLIED receipt (fork F1 Option A).

    誠實界線(**只證完整性 + trust-root 綁定,不做離線 SSHSIG 密碼學再驗**,與 operator 授權綁定同姿態):
    驗「精確欄位契約 + domain-separation 常量 + attestation_digest 完整性 + intent/applied 綁定(T2)+
    trusted_host_time 落在**內嵌** operator_authorization 窗 [issued_at, expires_at)(離線 T5)+ 有界 TTL」。
    因 ``build_operator_authorization`` clamp expires=min(intent_expiry, issued+15m) 且 issued==intent.created_at,
    op-auth 窗是 intent 窗的子集,故此離線 T5 檢查足夠,無需把 intent 時間帶進 result。真正的 SSHSIG 再驗 +
    平台背書屬 apply 期(``validate_apply_attestation``)/ S2.0 EFFECT session,不在離線中央閘做子程序密碼學。
    """

    if not isinstance(attestation, dict):
        return ["apply attestation must be a well-formed object"]
    if set(attestation) != ATTESTATION_FIELDS:
        return ["apply attestation fields do not match the exact contract"]
    errors: list[str] = []
    schema = _schema(str(APPLY_ATTESTATION_SCHEMA_PATH))
    errors.extend(
        f"apply attestation schema violation: {error}"
        for error in schema_subset_errors(attestation, schema, schema)
    )
    for field, expected in (
        ("schema_version", APPLY_ATTESTATION_SCHEMA_VERSION),
        ("attestor_identity", ATTESTOR_IDENTITY),
        ("algorithm", ATTESTOR_ALGORITHM),
        ("signature_namespace", APPLY_ATTESTATION_NAMESPACE),
        ("evidence_class", PRODUCTION_APPLIED_EVIDENCE_CLASS),
    ):
        if attestation.get(field) != expected:
            errors.append(f"apply attestation {field} is invalid")
    if attestation.get("attestation_digest") != apply_attestation_digest(attestation):
        errors.append("apply attestation digest mismatch")
    for att_field, expected in (
        ("intent_id", intent_id),
        ("intent_digest", intent_digest),
        ("source_head", source_head),
    ):
        if attestation.get(att_field) != expected:
            errors.append(f"apply attestation {att_field} is not bound to the result")
    if not (attestation.get("reobserved_digest") == attestation.get("applied_grant_set_digest") == applied_grant_set_digest):
        errors.append(
            "apply attestation reobserved_digest must equal applied_grant_set_digest and the result applied digest (T2)"
        )
    # 離線 T5:trusted_host_time 落在內嵌 operator_authorization 窗內 + 有界 attestation TTL。
    if not isinstance(operator_authorization, dict):
        errors.append("apply attestation requires the embedded operator authorization window")
    else:
        try:
            trusted_time = _parse_time(attestation["trusted_host_time"])
            attestation_expires = _parse_time(attestation["attestation_expires_at"])
            auth_issued = _parse_time(operator_authorization["issued_at"])
            auth_expires = _parse_time(operator_authorization["expires_at"])
            if not auth_issued <= trusted_time < auth_expires:
                errors.append("apply attestation trusted_host_time is outside the operator-authorization window")
            if not trusted_time < attestation_expires:
                errors.append("apply attestation trusted_host_time must precede attestation_expires_at")
            if attestation_expires - trusted_time > MAX_APPLY_ATTESTATION_TTL:
                errors.append("apply attestation TTL exceeds its ceiling")
        except (KeyError, TypeError, ValueError):
            errors.append("apply attestation timestamps are invalid")
    return errors
