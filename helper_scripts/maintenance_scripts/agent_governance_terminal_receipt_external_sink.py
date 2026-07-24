"""External-capable WORM terminal-receipt append Adapter for AIML S1.2A.

This is the **external-capable source machinery** for an S3-compatible
Object-Lock immutable (WORM) terminal-receipt destination.  It is a SEPARATE
module from the disposable sibling
(``agent_governance_terminal_receipt_sink.py``): that sibling stays a
``disposable_local_worm_emulation`` Adapter whose ``external_worm`` target is
rejected fail-closed, and this module does NOT relax that sibling gate — it adds
the external-destination CONTRACT, the client-injection append machinery, and the
independent immutability-proving readback ACK.

**Source-only (Amendment A1 — S1.2A vs S8.6).**  No external WORM destination is
bound and no real external append happens in this module.  The real append +
independent readback ACK to an out-of-repo destination is **S8.6**.  Here:

* ``apply_external_worm_append`` performs a real Object-Lock ``put_object`` only
  against an **injected** S3-compatible client (tests inject a small stub).  With
  no injected client the Adapter returns a typed fail-closed
  ``EXTERNAL_VERIFICATION_PENDING`` result — never a fake success and never an
  auto-bound real destination (that binding is S8.6).
* ``boto3``/``botocore`` are imported **lazily** and only probed for presence
  (via ``importlib.util.find_spec``); this module never instantiates a network
  client or contacts a real endpoint.  If the SDK is absent the Adapter fails
  closed.

**No plaintext secret ever (operator decision #6).**  No credential value is
requested, printed, logged, serialized, or stored.  The only credential handle is
``credential_channel_id`` — a NON-SECRET out-of-band CHANNEL IDENTIFIER (an
IAM/workload role, a short-lived STS session, or a named profile / env-channel id
the operator configures on the host).  Every serialized intent/result/ack is
secret-scanned fail-closed (reusing the sibling's ``_contains_secret_like``).

**Retention.**  ``object_lock_mode`` is ``GOVERNANCE`` (the first disposable
integration) or ``COMPLIANCE`` (the real terminal bucket, only after operator
approval + confirmed retention/readback/delete-denial).  ``COMPLIANCE`` is
refused unless ``compliance_operator_approved=True``; the default is fail-closed.

The Adapter reuses the frozen ``terminal_receipt_append_intent_v1`` base intent
(with ``target_class="external_worm"``) verbatim and wraps it with the external
destination contract; it self-validates via its own tests and is deliberately
disjoint from the central validator's live SCHEMA_FILES dispatch (no route_task
node, no closure effect binding) before S8.6.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import ipaddress
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import agent_governance_terminal_receipt_sink as sink  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402


ADAPTER_ID = "terminal_receipt_external_worm_sink_adapter_v1"
SINK_ID = "terminal_receipt_external_worm_sink_v1"
INTENT_SCHEMA_VERSION = "external_worm_append_intent_v1"
RESULT_SCHEMA_VERSION = "external_worm_append_result_v1"
READBACK_SCHEMA_VERSION = "external_worm_readback_ack_v1"

DESTINATION_CLASS = "EXTERNAL_IMMUTABLE_WORM"
TARGET_CLASS = "external_worm"

# S3 Object-Lock 保留模式:GOVERNANCE=第一個 disposable 整合預設;COMPLIANCE=真正終端桶,
# 僅在 operator 核准 + retention/readback/delete-denial 皆確認後採用。預設 fail-closed。
OBJECT_LOCK_MODES = frozenset({"GOVERNANCE", "COMPLIANCE"})
DISPOSABLE_DEFAULT_MODE = "GOVERNANCE"

EXTERNAL_APPEND_STATUSES = frozenset(
    {"APPENDED", "IDEMPOTENT_DEDUP", "EXTERNAL_VERIFICATION_PENDING", "FAILED"}
)
# 已 commit(綁定唯一 Object-Lock 版本)的兩種狀態;其餘兩種不得綁定任何版本。
EXTERNAL_COMMITTED_STATUSES = frozenset({"APPENDED", "IDEMPOTENT_DEDUP"})

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = Path(__file__).resolve()
SCHEMA_DIR = REPO_ROOT / "program_code/ml_training/schemas/aiml_gate_receipts"
BASE_INTENT_SCHEMA_PATH = SCHEMA_DIR / "terminal_receipt_append_intent_v1.schema.json"
INTENT_SCHEMA_PATH = SCHEMA_DIR / "external_worm_append_intent_v1.schema.json"
RESULT_SCHEMA_PATH = SCHEMA_DIR / "external_worm_append_result_v1.schema.json"
READBACK_SCHEMA_PATH = SCHEMA_DIR / "external_worm_readback_ack_v1.schema.json"

# external adapter 專屬的 required hard stops(比 disposable 更明確地載明外部邊界)。
EXTERNAL_REQUIRED_HARD_STOPS = frozenset({
    "external-capable source Adapter only; no external WORM destination is bound and "
    "no real append before S8.6",
    "no plaintext credential is requested, printed, logged, serialized, or stored; "
    "only a non-secret channel identifier",
    "COMPLIANCE object-lock retention only after operator approval; GOVERNANCE for the "
    "disposable integration",
    "no live/mainnet authority expansion; no order/broker/decision-lease effect",
})

DESTINATION_CONTRACT_FIELDS = (
    "endpoint", "region", "bucket", "object_lock_mode", "retain_until",
    "credential_channel_id",
)

# 生產終端 receipt 類型(真正落地/無候選 receipt);external WORM 對這兩型強制 COMPLIANCE object-lock
# + operator 核准。GOVERNANCE 僅允許 disposable-integration receipt 類型(disposable_proof_payload_v1)。
PRODUCTION_TERMINAL_RECEIPT_TYPES = frozenset({
    "aiml_module_landed_for_trading_receipt_v1",
    "aiml_platform_no_candidate_receipt_v1",
})

# --------------------------------------------------------------------------- #
# 自由文字契約欄位的「正向格式」白名單(primary P1 修補)。機密掃描僅認得已知機密樣態,漏接
# AWS 形狀金鑰(AKIA…/wJalr…/aws_secret_access_key=…/40-hex/base64),故對這幾個自由欄位改採
# 「必須符合非機密識別碼格式」正向驗證;不加通用 entropy 掃描(artifacts 合法攜帶 sha256 digest,
# entropy 啟發式會誤報)。機密掃描續作 backstop。
# --------------------------------------------------------------------------- #
# credential_channel_id:一個 CHANNEL 種類 + 非機密 id(絕非金鑰值);AWS 金鑰 / aws_secret_access_key=… 不符。
CREDENTIAL_CHANNEL_ID_RE = re.compile(
    r"^(?:aws-profile|iam-role|sts-session|env-channel):[A-Za-z0-9._/-]{1,128}$"
)
# S3 bucket 命名字元集(不得大寫/底線);AWS 金鑰含大寫/底線/等號一律不符。
S3_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
# region token(如 us-east-1);涵蓋注入 stub 測試所用 region。
AWS_REGION_RE = re.compile(r"^[a-z]{2}-[a-z]+-[0-9]$")

INTENT_WRAPPER_FIELDS = frozenset({
    "schema_version", "external_sink_id", "target_class", "destination_class",
    "append_intent", "destination_contract", "compliance_operator_approved",
    "external_intent_digest",
})
RESULT_FIELDS = frozenset({
    "schema_version", "external_sink_id", "intent_id", "external_intent_digest",
    "append_status", "record_locator", "object_version_id", "checksum_sha256",
    "retention", "credential_channel_id", "idempotency_key", "append_actor_id",
    "started_at", "completed_at", "evidence_expires_at", "external_verification_pending",
    "failure_reason", "result_digest",
})
READBACK_FIELDS = frozenset({
    "schema_version", "external_sink_id", "intent_id", "result_digest",
    "readback_verifier_id", "read_record_locator", "read_object_version_id",
    "readback_checksum_sha256", "readback_retention", "checksum_match",
    "version_id_match", "retention_match", "object_lock_enabled",
    "immutability_proven", "ack", "same_actor_violation", "observed_at", "expires_at",
    "ack_digest",
})

# botocore ClientError 風格的錯誤碼分類(以 duck-typing 讀 error.response.Error.Code,
# 不在 import 期依賴 botocore;測試注入的 stub 亦提供同形狀 response)。
_NOT_FOUND_CODES = frozenset(
    {"404", "NoSuchKey", "NotFound", "NoSuchKeyError", "NoSuchKeyException"}
)


class ExternalWormContractError(RuntimeError):
    """Raised when the external-destination contract is incomplete/unsafe to build."""


# --------------------------------------------------------------------------- #
# schema loaders + canonical digests (reuse the sibling's pure byte helpers)
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _base_intent_schema() -> dict[str, Any]:
    import json

    return json.loads(BASE_INTENT_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _intent_schema() -> dict[str, Any]:
    import json

    return json.loads(INTENT_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _result_schema() -> dict[str, Any]:
    import json

    return json.loads(RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _readback_schema() -> dict[str, Any]:
    import json

    return json.loads(READBACK_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def source_sha256() -> str:
    """Return the sha256 identity of this Adapter module source."""

    return sink._sha256_bytes(SOURCE_PATH.read_bytes())


def external_intent_digest(intent: dict[str, Any]) -> str:
    """Hash every wrapper field except the self-referential ``external_intent_digest``."""

    unsigned = {k: v for k, v in intent.items() if k != "external_intent_digest"}
    return sink._sha256_bytes(sink._canonical_bytes(unsigned))


def external_result_digest(result: dict[str, Any]) -> str:
    """Hash every result field except the self-referential ``result_digest``."""

    unsigned = {k: v for k, v in result.items() if k != "result_digest"}
    return sink._sha256_bytes(sink._canonical_bytes(unsigned))


def external_ack_digest(ack: dict[str, Any]) -> str:
    """Hash every ack field except the self-referential ``ack_digest``."""

    unsigned = {k: v for k, v in ack.items() if k != "ack_digest"}
    return sink._sha256_bytes(sink._canonical_bytes(unsigned))


def _fieldset_error(kind: str, value: dict[str, Any], expected: frozenset[str]) -> list[str]:
    if set(value) != expected:
        return [
            f"external worm {kind} fields mismatch: "
            f"missing={sorted(expected - set(value))} extra={sorted(set(value) - expected)}"
        ]
    return []


def _is_retention_obj(retention: Any) -> bool:
    return (
        isinstance(retention, dict)
        and retention.get("object_lock_mode") in OBJECT_LOCK_MODES
        and isinstance(retention.get("retain_until"), str)
        and bool(retention.get("retain_until"))
    )


def _retain_until_equal(left: Any, right: Any) -> bool:
    try:
        return sink._parse_time(str(left)) == sink._parse_time(str(right))
    except (TypeError, ValueError):
        return False


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _canonical_checksum(s3_checksum: Any) -> str | None:
    # S3 ChecksumSHA256 是 raw sha256 的 base64;轉回 canonical "sha256:<hex>" 供內部綁定比較。
    # 亦接受已是 "sha256:<hex>" 的輸入(容錯不同 stub/呼叫端表述)。
    if not isinstance(s3_checksum, str) or not s3_checksum:
        return None
    if s3_checksum.startswith("sha256:"):
        return s3_checksum if sink.DIGEST_RE.fullmatch(s3_checksum) else None
    try:
        raw = base64.b64decode(s3_checksum, validate=True)
    except (ValueError, binascii.Error):
        return None
    if len(raw) != 32:
        return None
    return "sha256:" + raw.hex()


# --------------------------------------------------------------------------- #
# 自由文字契約欄位的正向格式驗證(P1:堵住 AWS 形狀機密走私)
# --------------------------------------------------------------------------- #
def _endpoint_format_error(endpoint: Any) -> str | None:
    """Return an error if ``endpoint`` is not a safe ``https://<host>[:port]`` URL, else None.

    強制 https scheme;拒 link-local/metadata(169.254/16 含 169.254.169.254)、private
    (10/8·172.16/12·192.168/16)、loopback(127/8)與任何裸 IP、localhost —— SSRF /
    credential-redirection 防護(E3 P2;真 client 為 S8.6,此處先行防禦)。
    """

    if not isinstance(endpoint, str) or not endpoint.strip():
        return "endpoint is required"
    try:
        parts = urlsplit(endpoint)
    except ValueError:
        return "endpoint is not a parseable URL"
    if parts.scheme != "https":
        return "endpoint must be an https:// URL (scheme required)"
    host = parts.hostname
    if not host:
        return "endpoint must include a host"
    lowered = host.lower()
    if lowered == "localhost" or lowered.endswith(".localhost"):
        return "endpoint host must not be localhost (SSRF/credential-redirection guard)"
    # 裸 IP(v4/v6)一律拒:涵蓋 metadata 169.254.169.254 / 169.254.0.0-16、private、loopback。
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return None
    return (
        "endpoint host must not be a bare IP address "
        "(link-local/metadata/private/loopback are rejected; SSRF/credential-redirection guard)"
    )


def _destination_format_errors(contract: dict[str, Any]) -> list[str]:
    """Positive-format validation of exactly the free-form contract fields (P1 primary fix).

    ``credential_channel_id`` 必符 CHANNEL 種類 + 非機密 id;``endpoint`` 必為安全 https URL;
    ``bucket`` 必符 S3 命名字元集;``region`` 必符 region token。任一不符即回傳明確錯誤 —— 據此把
    AKIA…/wJalr…/aws_secret_access_key=… 這類 AWS 形狀機密於 build 與 validate 兩端 fail-closed。
    """

    errors: list[str] = []
    channel = contract.get("credential_channel_id")
    if not (isinstance(channel, str) and CREDENTIAL_CHANNEL_ID_RE.fullmatch(channel)):
        errors.append(
            "credential_channel_id must be a non-secret channel identifier "
            "(aws-profile|iam-role|sts-session|env-channel:<id>); an AWS key / "
            "aws_secret_access_key=… is rejected fail-closed"
        )
    endpoint_error = _endpoint_format_error(contract.get("endpoint"))
    if endpoint_error is not None:
        errors.append(endpoint_error)
    bucket = contract.get("bucket")
    if not (isinstance(bucket, str) and S3_BUCKET_RE.fullmatch(bucket)):
        errors.append(
            "bucket must match the S3 bucket-name charset ^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$ "
            "(no uppercase/underscore)"
        )
    region = contract.get("region")
    if not (isinstance(region, str) and AWS_REGION_RE.fullmatch(region)):
        errors.append("region must be a region token (e.g. us-east-1)")
    return errors


# --------------------------------------------------------------------------- #
# intent builder
# --------------------------------------------------------------------------- #
def build_external_worm_append_intent(
    *,
    intent_id: str,
    terminal_receipt_type: str,
    final_source_head: str,
    landing_scope_id: str,
    learning_runtime_digest: str,
    terminal_payload_digest: str,
    append_actor_id: str,
    approved_by: str,
    approved_at: str,
    expires_at: str,
    endpoint: str,
    region: str,
    bucket: str,
    object_lock_mode: str,
    retain_until: str,
    credential_channel_id: str,
    compliance_operator_approved: bool = False,
    hard_stops: list[str] | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Build a canonical, self-hashed ``external_worm_append_intent_v1``.

    Reuses the frozen ``terminal_receipt_append_intent_v1`` base intent (built with
    ``target_class="external_worm"``) and wraps it with the NON-SECRET external
    destination contract.  Fail-closed (``ExternalWormContractError``) if any
    contract field is missing/blank, if a free-form contract field fails positive-
    format validation (``credential_channel_id``/``endpoint``/``bucket``/``region`` —
    the AWS-shaped secret smuggling guard), if ``object_lock_mode`` is unknown, if
    ``COMPLIANCE`` is requested without operator approval, if a production terminal
    receipt type is not bound to operator-approved COMPLIANCE object-lock, or if
    ``retain_until`` is not a valid timestamp strictly after both ``approved_at`` and
    ``now``.  ``credential_channel_id`` is only an out-of-band CHANNEL IDENTIFIER —
    never a credential value; any secret-like content fails closed via the sibling's
    secret scan (kept as a backstop behind the positive-format guard).
    """

    contract_inputs = {
        "endpoint": endpoint, "region": region, "bucket": bucket,
        "object_lock_mode": object_lock_mode, "retain_until": retain_until,
        "credential_channel_id": credential_channel_id,
    }
    missing = sorted(
        name for name, value in contract_inputs.items()
        if not isinstance(value, str) or not value.strip()
    )
    if missing:
        raise ExternalWormContractError(
            f"external destination contract is incomplete: missing {missing}"
        )
    if object_lock_mode not in OBJECT_LOCK_MODES:
        raise ExternalWormContractError(
            "object_lock_mode must be GOVERNANCE or COMPLIANCE"
        )
    if object_lock_mode == "COMPLIANCE" and compliance_operator_approved is not True:
        raise ExternalWormContractError(
            "COMPLIANCE object-lock retention requires operator approval "
            "(compliance_operator_approved=True)"
        )
    # 生產終端 receipt(module_landed / no_candidate)強制 operator-approved COMPLIANCE;GOVERNANCE
    # 僅供 disposable-integration receipt 類型使用(E3 P2 fail-closed)。
    if terminal_receipt_type in PRODUCTION_TERMINAL_RECEIPT_TYPES and not (
        object_lock_mode == "COMPLIANCE" and compliance_operator_approved is True
    ):
        raise ExternalWormContractError(
            "a production terminal receipt type requires operator-approved COMPLIANCE "
            "object-lock retention (GOVERNANCE is only for the disposable integration)"
        )
    # backstop 先行:已知機密樣態(如 authorization=…)於此以 SecretLeakageError fail-closed,
    # 再由下方正向格式驗證堵住機密掃描漏接的 AWS 形狀走私。
    sink._guard_no_secret(contract_inputs)
    format_errors = _destination_format_errors(contract_inputs)
    if format_errors:
        raise ExternalWormContractError(
            "external destination contract fails positive-format validation: "
            + "; ".join(format_errors)
        )
    try:
        approved_dt = sink._parse_time(approved_at)
        retain_dt = sink._parse_time(retain_until)
        now_dt = sink._parse_time(now) if now else datetime.now(timezone.utc)
    except (TypeError, ValueError) as error:
        raise ExternalWormContractError(
            f"approved_at/retain_until must be tz-aware ISO timestamps: {error}"
        ) from error
    if not retain_dt > approved_dt:
        raise ExternalWormContractError("retain_until must be after approved_at")
    # retain_until <= now 是一個立即可刪的 no-op,一律拒(E3 P2)。
    if not retain_dt > now_dt:
        raise ExternalWormContractError(
            "retain_until must be in the future (retain_until <= now is an "
            "immediately-deletable no-op)"
        )

    resolved_hard_stops = (
        sorted(EXTERNAL_REQUIRED_HARD_STOPS) if hard_stops is None else list(hard_stops)
    )
    # 復用 frozen 基礎 intent 契約(disposable builder 接受 external_worm;只有 disposable
    # validator 於 S1.2 gate 拒 external_worm —— 本模組不走該 validator,自帶 external validator)。
    base = sink.build_terminal_receipt_append_intent(
        intent_id=intent_id,
        terminal_receipt_type=terminal_receipt_type,
        final_source_head=final_source_head,
        landing_scope_id=landing_scope_id,
        learning_runtime_digest=learning_runtime_digest,
        terminal_payload_digest=terminal_payload_digest,
        append_actor_id=append_actor_id,
        approved_by=approved_by,
        approved_at=approved_at,
        expires_at=expires_at,
        target_class=TARGET_CLASS,
        hard_stops=resolved_hard_stops,
    )
    contract = {name: contract_inputs[name] for name in DESTINATION_CONTRACT_FIELDS}
    intent: dict[str, Any] = {
        "schema_version": INTENT_SCHEMA_VERSION,
        "external_sink_id": SINK_ID,
        "target_class": TARGET_CLASS,
        "destination_class": DESTINATION_CLASS,
        "append_intent": base,
        "destination_contract": contract,
        "compliance_operator_approved": bool(compliance_operator_approved),
        "external_intent_digest": "sha256:" + "0" * 64,
    }
    # fail-closed:任何機密樣態即拒絕序列化(涵蓋 credential_channel_id / endpoint 等)。
    sink._guard_no_secret(intent)
    intent["external_intent_digest"] = external_intent_digest(intent)
    return intent


# --------------------------------------------------------------------------- #
# injected-client Object-Lock append machinery (no real network before S8.6)
# --------------------------------------------------------------------------- #
def _probe_boto3_available(override: bool | None = None) -> bool:
    # 只探測 SDK 是否存在(find_spec 不 import、不建立 client、不觸網);override 供測試決定性控制。
    if override is not None:
        return bool(override)
    try:
        import importlib.util

        return importlib.util.find_spec("boto3") is not None
    except (ImportError, ValueError):  # pragma: no cover - defensive
        return False


def _s3_error_code(error: BaseException) -> str:
    response = getattr(error, "response", None)
    if isinstance(response, dict):
        code = response.get("Error", {}).get("Code")
        if code:
            return str(code)
    return type(error).__name__


def _is_not_found(error: BaseException) -> bool:
    return _s3_error_code(error) in _NOT_FOUND_CODES


def apply_external_worm_append(
    intent: dict[str, Any],
    *,
    s3_client: Any = None,
    append_actor_id: str,
    terminal_payload: Any,
    started_at: str | None = None,
    completed_at: str | None = None,
    boto3_available: bool | None = None,
) -> dict[str, Any]:
    """Apply one external Object-Lock WORM append against an INJECTED S3 client.

    With ``s3_client=None`` the Adapter returns a typed fail-closed
    ``EXTERNAL_VERIFICATION_PENDING`` result (never a fake success): the external
    immutable destination is not bound before S8.6, and this module never
    auto-instantiates a real network client.  With an injected client it does a
    real ``put_object`` carrying ``ObjectLockMode`` + ``ObjectLockRetainUntilDate``
    + ``ChecksumSHA256``, captures the returned ``VersionId``, and honors
    idempotency: a same-idempotency-key object that already exists is NOT re-put
    (``IDEMPOTENT_DEDUP``; the committed record is never mutated).  Fails closed on
    a wrong append actor, a payload-digest mismatch, secret-like payload, a
    checksum substitution, or a missing ``VersionId``.  Raises
    ``ExternalWormContractError`` if ``intent`` is structurally invalid.
    """

    intent_errors = validate_external_worm_append_intent(intent)
    if intent_errors:
        raise ExternalWormContractError(
            "external worm append intent is invalid: " + "; ".join(intent_errors)
        )
    base = intent["append_intent"]
    contract = intent["destination_contract"]
    channel = contract["credential_channel_id"]
    idempotency_key = base["idempotency_key"]
    intent_id = base["intent_id"]
    ext_digest = intent["external_intent_digest"]
    started = started_at or sink._utcnow_iso()

    def _result(
        status: str, *, record_locator: str | None, version_id: str | None,
        checksum: str | None, retention: dict[str, Any] | None, pending: bool,
        failure: str | None,
    ) -> dict[str, Any]:
        completed = completed_at or sink._utcnow_iso()
        result: dict[str, Any] = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "external_sink_id": SINK_ID,
            "intent_id": intent_id,
            "external_intent_digest": ext_digest,
            "append_status": status,
            "record_locator": record_locator,
            "object_version_id": version_id,
            "checksum_sha256": checksum,
            "retention": retention,
            "credential_channel_id": channel,  # NON-SECRET channel identifier only
            "idempotency_key": idempotency_key,
            "append_actor_id": append_actor_id,
            "started_at": started,
            "completed_at": completed,
            "evidence_expires_at": sink._plus_seconds(completed, sink.EVIDENCE_TTL_SECONDS),
            "external_verification_pending": pending,
            "failure_reason": failure,
            "result_digest": "sha256:" + "0" * 64,
        }
        sink._guard_no_secret(result)
        result["result_digest"] = external_result_digest(result)
        return result

    payload_bytes = sink._canonical_bytes(terminal_payload)
    persisted_digest = sink._sha256_bytes(payload_bytes)
    payload_binding = base.get("payload_binding") or {}

    # append actor 必須等於已核准 intent 的 append_actor_id。
    if append_actor_id != base.get("append_actor_id"):
        return _result(
            "FAILED", record_locator=None, version_id=None, checksum=None,
            retention=None, pending=False,
            failure="append actor differs from approved intent append_actor_id",
        )
    # payload-hash binding:序列化 payload 的 digest 必須等於 intent 綁定的 digest。
    if persisted_digest != payload_binding.get("terminal_payload_digest"):
        return _result(
            "FAILED", record_locator=None, version_id=None, checksum=None,
            retention=None, pending=False,
            failure="terminal payload digest does not match intent payload_binding",
        )
    # 機密前置守衛:序列化前掃描 payload,任何機密樣態一律 fail-closed,絕不外送。
    if sink._contains_secret_like(terminal_payload):
        return _result(
            "FAILED", record_locator=None, version_id=None, checksum=None,
            retention=None, pending=False,
            failure="terminal payload carries secret-like content; nothing appended",
        )

    if s3_client is None:
        # fail-closed:無注入 client ⇒ 外部不可變目的地在 S8.6 之前未綁定,回 typed PENDING
        # (絕不佯稱成功、絕不自建真 client 觸網)。lazy boto3 僅探測 SDK 是否存在供診斷。
        sdk_present = _probe_boto3_available(boto3_available)
        reason = (
            "no s3_client injected; the external immutable WORM destination is not "
            "bound before S8.6 "
            f"(boto3 SDK {'present' if sdk_present else 'absent'}; credential channel is "
            "a non-secret identifier only). Inject an S3-compatible Object-Lock client "
            "to exercise the append machinery."
        )
        return _result(
            "EXTERNAL_VERIFICATION_PENDING", record_locator=None, version_id=None,
            checksum=None, retention=None, pending=True, failure=reason,
        )

    bucket = contract["bucket"]
    mode = contract["object_lock_mode"]
    retain_until = contract["retain_until"]
    key = sink._record_relative_locator(str(idempotency_key))
    retention_obj = {"object_lock_mode": mode, "retain_until": retain_until}

    # idempotency:先 head_object 探測既有物件。已存在且 checksum 相符 ⇒ IDEMPOTENT_DEDUP
    # (不重 put、不改寫已 commit record);checksum 不符 ⇒ 內容替換 fail-closed。
    try:
        head = s3_client.head_object(Bucket=bucket, Key=key, ChecksumMode="ENABLED")
    except Exception as error:  # noqa: BLE001 - duck-typed S3 error classification
        if _is_not_found(error):
            head = None
        else:
            return _result(
                "FAILED", record_locator=None, version_id=None, checksum=None,
                retention=None, pending=False,
                failure=f"head_object failed: {_s3_error_code(error)}",
            )
    if head is not None:
        existing_checksum = _canonical_checksum(head.get("ChecksumSHA256"))
        existing_version = head.get("VersionId")
        if existing_checksum != persisted_digest:
            return _result(
                "FAILED", record_locator=None, version_id=None, checksum=None,
                retention=None, pending=False,
                failure=(
                    "existing object checksum does not match the approved payload digest "
                    "(content substitution detected)"
                ),
            )
        if not isinstance(existing_version, str) or not existing_version:
            return _result(
                "FAILED", record_locator=None, version_id=None, checksum=None,
                retention=None, pending=False,
                failure="existing object has no VersionId; object versioning is not enabled",
            )
        # P2(Codex):dedup 既有物件亦須驗證其真實 Object-Lock retention 不弱於本次核准期限。既有物件
        # 可能帶較短或不同 mode 的保留;若直接 dedup 就會以「核准 retention」冒充實際較弱的保留,騙過
        # 不可變性。以非破壞式 get_object_retention 讀既有保留:mode 須完全等於核准 mode,且 retain_until
        # 不少於核准 retain_until,否則 fail-closed。
        try:
            existing_retention_resp = s3_client.get_object_retention(
                Bucket=bucket, Key=key, VersionId=existing_version,
            )
            existing_payload = (existing_retention_resp or {}).get("Retention") or {}
            existing_retention = {
                "object_lock_mode": existing_payload.get("Mode"),
                "retain_until": _iso(existing_payload.get("RetainUntilDate")),
            }
        except Exception as error:  # noqa: BLE001 - retention read failure ⇒ fail-closed
            return _result(
                "FAILED", record_locator=None, version_id=None, checksum=None,
                retention=None, pending=False,
                failure=(
                    "existing object Object-Lock retention read failed: "
                    f"{_s3_error_code(error)}"
                ),
            )
        if not (
            _is_retention_obj(existing_retention)
            and existing_retention.get("object_lock_mode") == mode
            and _retain_until_at_least(existing_retention.get("retain_until"), retain_until)
        ):
            return _result(
                "FAILED", record_locator=None, version_id=None, checksum=None,
                retention=None, pending=False,
                failure=(
                    "existing object Object-Lock retention is shorter than or different "
                    "from the approved retention (dedup would misrepresent immutability)"
                ),
            )
        return _result(
            "IDEMPOTENT_DEDUP", record_locator=key, version_id=existing_version,
            checksum=persisted_digest, retention=retention_obj, pending=False,
            failure=None,
        )

    # 全新 commit:put_object 帶 Object-Lock 模式/保留日期/內容 checksum(base64 raw sha256)。
    checksum_b64 = base64.b64encode(hashlib.sha256(payload_bytes).digest()).decode("ascii")
    retain_dt = sink._parse_time(retain_until)
    response = s3_client.put_object(
        Bucket=bucket, Key=key, Body=payload_bytes,
        ChecksumSHA256=checksum_b64, ObjectLockMode=mode,
        ObjectLockRetainUntilDate=retain_dt,
    )
    version_id = (response or {}).get("VersionId")
    if not isinstance(version_id, str) or not version_id:
        return _result(
            "FAILED", record_locator=None, version_id=None, checksum=None,
            retention=None, pending=False,
            failure="put_object returned no VersionId (object-lock/versioning not enabled)",
        )
    return _result(
        "APPENDED", record_locator=key, version_id=version_id,
        checksum=persisted_digest, retention=retention_obj, pending=False, failure=None,
    )


# --------------------------------------------------------------------------- #
# independent immutability-proving readback ACK (distinct actor)
# --------------------------------------------------------------------------- #
def _read_object_lock_enabled(client: Any, bucket: str) -> bool:
    # 非破壞式讀:桶層 Object-Lock 設定必須為 ENABLED,才算真正 WORM 已在桶上啟用。
    try:
        config = client.get_object_lock_configuration(Bucket=bucket)
    except Exception:  # noqa: BLE001 - duck-typed S3 error ⇒ treat as not-enabled (fail-closed)
        return False
    payload = (config or {}).get("ObjectLockConfiguration") or {}
    return payload.get("ObjectLockEnabled") == "Enabled"


def _retain_until_in_future(retention: Any, *, now_iso: str) -> bool:
    # 不可變性核心:保留期 retain_until 必須嚴格晚於 now —— 過期保留 = 立即可刪的 no-op。
    if not _is_retention_obj(retention):
        return False
    try:
        return sink._parse_time(str(retention.get("retain_until"))) > sink._parse_time(now_iso)
    except (TypeError, ValueError):
        return False


def _retain_until_at_least(observed: Any, approved: Any) -> bool:
    # P2(Codex readback):observed 保留期解析後必須「不少於」核准的 retain_until。timezone-normalized
    # 比較(``sink._parse_time`` 對齊 UTC),故等值與更長皆通過、較短一律 FAIL——縮短保留期即削弱不可變性。
    try:
        return sink._parse_time(str(observed)) >= sink._parse_time(str(approved))
    except (TypeError, ValueError):
        return False


def independent_readback_ack(
    result: dict[str, Any],
    intent: dict[str, Any],
    *,
    s3_client: Any,
    verifier_actor_id: str,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Independently re-read one committed Object-Lock object and ACK immutability.

    The ``verifier_actor_id`` MUST differ from the committed result's
    ``append_actor_id``; a same-actor readback sets ``same_actor_violation=true``
    and refuses to ACK.  Immutability is proven by NON-DESTRUCTIVE Object-Lock config
    READS only — never a destructive delete/retention-shortening probe (E2 P2a: those
    would DELETE the just-committed record against a misconfigured bucket).  A positive
    ACK requires (a) a distinct verifier, (b) the re-read checksum + ``VersionId`` to
    match the result, (c) ``get_object_retention`` showing the mode matches AND
    ``retain_until`` in the FUTURE, and (d) ``get_object_lock_configuration`` showing
    the bucket lock ENABLED.  "Object exists under an active retention lock whose
    retain-until is in the future" IS the immutability proof.  Uses the injected client
    only (no real network); no ``delete_object`` / ``put_object_retention`` is ever called.
    """

    contract = (intent or {}).get("destination_contract") or {}
    bucket = contract.get("bucket")
    observed = observed_at or sink._utcnow_iso()
    append_actor = result.get("append_actor_id")
    same_actor_violation = verifier_actor_id == append_actor
    record_locator = result.get("record_locator")
    expected_version = result.get("object_version_id")
    expected_checksum = result.get("checksum_sha256")
    expected_retention = result.get("retention")
    committed = result.get("append_status") in EXTERNAL_COMMITTED_STATUSES

    read_locator: str | None = None
    read_version: str | None = None
    read_checksum: str | None = None
    read_retention: dict[str, Any] | None = None
    checksum_match = version_id_match = retention_match = object_lock_enabled = False

    # store-escape 防禦:record_locator 必須是 records/<64hex>.record 形狀,再由注入 client 讀取。
    if (
        not same_actor_violation
        and committed
        and isinstance(record_locator, str)
        and sink.RECORD_LOCATOR_RE.fullmatch(record_locator)
        and isinstance(bucket, str)
        and bucket
    ):
        try:
            obj = s3_client.get_object(
                Bucket=bucket, Key=record_locator, VersionId=expected_version,
                ChecksumMode="ENABLED",
            )
        except Exception:  # noqa: BLE001 - read failure ⇒ no ack (fail-closed)
            obj = None
        if obj is not None:
            read_locator = record_locator
            read_version = obj.get("VersionId")
            body = obj.get("Body")
            body_bytes = body.read() if hasattr(body, "read") else body
            if isinstance(body_bytes, (bytes, bytearray)):
                read_checksum = sink._sha256_bytes(bytes(body_bytes))
            else:
                read_checksum = _canonical_checksum(obj.get("ChecksumSHA256"))
            try:
                retention_response = s3_client.get_object_retention(
                    Bucket=bucket, Key=record_locator, VersionId=expected_version,
                )
                retention_payload = (retention_response or {}).get("Retention") or {}
                read_retention = {
                    "object_lock_mode": retention_payload.get("Mode"),
                    "retain_until": _iso(retention_payload.get("RetainUntilDate")),
                }
            except Exception:  # noqa: BLE001 - retention read failure ⇒ no match
                read_retention = None
            checksum_match = read_checksum is not None and read_checksum == expected_checksum
            version_id_match = (
                isinstance(read_version, str) and read_version == expected_version
            )
            # 保留匹配(非破壞式):read 的 mode 完全等於已 commit result 的 mode、retain_until 仍在未來,
            # 且(P2 Codex)observed retain_until 不少於核准的 retain_until——較短的實際保留期必須 FAIL,
            # 否則 store 可接受寫入卻套用更短的未來保留而仍騙過不可變性 ACK。
            retention_match = (
                _is_retention_obj(read_retention)
                and _is_retention_obj(expected_retention)
                and read_retention.get("object_lock_mode")
                == expected_retention.get("object_lock_mode")
                and _retain_until_in_future(read_retention, now_iso=observed)
                and _retain_until_at_least(
                    read_retention.get("retain_until"),
                    expected_retention.get("retain_until"),
                )
            )
            # 桶層 Object-Lock 設定 ENABLED(非破壞式讀);未啟用 ⇒ 非真 WORM。
            object_lock_enabled = _read_object_lock_enabled(s3_client, bucket)

    immutability_proven = bool(
        checksum_match and version_id_match and retention_match and object_lock_enabled
    )
    ack = (not same_actor_violation) and committed and immutability_proven

    ack_obj: dict[str, Any] = {
        "schema_version": READBACK_SCHEMA_VERSION,
        "external_sink_id": SINK_ID,
        "intent_id": result.get("intent_id"),
        "result_digest": result.get("result_digest"),
        "readback_verifier_id": verifier_actor_id,
        "read_record_locator": read_locator,
        "read_object_version_id": read_version if read_locator is not None else None,
        "readback_checksum_sha256": read_checksum if read_locator is not None else None,
        "readback_retention": read_retention if read_locator is not None else None,
        "checksum_match": checksum_match,
        "version_id_match": version_id_match,
        "retention_match": retention_match,
        "object_lock_enabled": object_lock_enabled,
        "immutability_proven": immutability_proven,
        "ack": ack,
        "same_actor_violation": same_actor_violation,
        "observed_at": observed,
        "expires_at": sink._plus_seconds(observed, sink.EVIDENCE_TTL_SECONDS),
        "ack_digest": "sha256:" + "0" * 64,
    }
    sink._guard_no_secret(ack_obj)
    ack_obj["ack_digest"] = external_ack_digest(ack_obj)
    return ack_obj


def external_verification_pending_request(intent: Any) -> dict[str, Any]:
    """Emit the ONE precise NON-SECRET request naming exactly what config is missing.

    Enumerates the six required destination-contract identifiers plus the
    credential-channel + Object-Lock requirements, marking each present/missing.
    Never echoes any value (only presence) and never requests a credential value —
    only a NON-SECRET out-of-band channel identifier.
    """

    contract = intent.get("destination_contract") if isinstance(intent, dict) else None
    contract = contract if isinstance(contract, dict) else {}
    presence = {
        field: (
            "present"
            if isinstance(contract.get(field), str) and contract.get(field).strip()
            else "MISSING"
        )
        for field in DESTINATION_CONTRACT_FIELDS
    }
    request = {
        "request_kind": "external_worm_verification_pending_request_v1",
        "external_sink_id": SINK_ID,
        "status": "EXTERNAL_VERIFICATION_PENDING",
        "required_non_secret_config": list(DESTINATION_CONTRACT_FIELDS),
        "config_presence": presence,
        "missing_config": sorted(
            field for field, state in presence.items() if state == "MISSING"
        ),
        "credential_channel_note": (
            "credential_channel_id is a NON-SECRET out-of-band channel identifier (an "
            "IAM/workload role, a short-lived STS session, or a named profile/env-channel "
            "id configured on the host); provide only the channel identifier, never a "
            "credential value"
        ),
        "object_lock_requirement": (
            "an Object-Lock-enabled bucket with GOVERNANCE (disposable integration) or "
            "operator-approved COMPLIANCE retention is required"
        ),
        "external_binding_note": (
            "no external immutable WORM destination is bound and no real append happens "
            "before S8.6; inject an S3-compatible Object-Lock client to exercise the "
            "append machinery"
        ),
    }
    sink._guard_no_secret(request)
    return request


# --------------------------------------------------------------------------- #
# validators (structural + integrity + freshness; not execution authenticity)
# --------------------------------------------------------------------------- #
def _validate_base_intent_times(base: dict[str, Any], *, now: str | None) -> list[str]:
    errors: list[str] = []
    try:
        approved = sink._parse_time(str(base.get("approved_at", "")))
        expires = sink._parse_time(str(base.get("expires_at", "")))
        if not approved < expires:
            errors.append("external base intent approved_at must precede expires_at")
        if expires - approved > timedelta(seconds=sink.INTENT_TTL_CEILING_SECONDS):
            errors.append("external base intent TTL exceeds its ceiling")
        if now is not None:
            current = sink._parse_time(now)
            if not approved <= current < expires:
                errors.append("external worm intent is not fresh")
    except (TypeError, ValueError):
        errors.append("external base intent timestamps are invalid")
    return errors


def _validate_base_append_intent(base: dict[str, Any], *, now: str | None) -> list[str]:
    # 復用 frozen base schema 結構驗 + 派生欄位(idempotency/typed_confirm/digest),但以 external
    # adapter 的規則要求 target_class=external_worm(disposable gate 的相反),不走 disposable validator。
    errors = [
        f"external base append intent schema violation: {error}"
        for error in schema_subset_errors(base, _base_intent_schema(), _base_intent_schema())
    ]
    errors.extend(_fieldset_error("base append intent", base, sink.INTENT_FIELDS))
    if base.get("schema_version") != "terminal_receipt_append_intent_v1":
        errors.append("external base append intent schema_version is invalid")
    if base.get("sink_id") != "terminal_receipt_sink_v1":
        errors.append("external base append intent sink_id is invalid")
    if base.get("destination_class") != DESTINATION_CLASS:
        errors.append("external base append intent destination_class is invalid")
    if base.get("target_class") != TARGET_CLASS:
        errors.append(
            "external worm append intent target_class must be external_worm"
        )
    receipt_type = base.get("terminal_receipt_type")
    payload_binding = base.get("payload_binding")
    if not isinstance(payload_binding, dict):
        errors.append("external base append intent payload_binding is invalid")
    else:
        state = payload_binding.get("terminal_state")
        if receipt_type in sink.TERMINAL_TYPE_TO_STATE and (
            sink.TERMINAL_TYPE_TO_STATE[receipt_type] != state
        ):
            errors.append(
                "external base append terminal type and payload_binding.terminal_state "
                "are inconsistent"
            )
        if base.get("idempotency_key") != sink.terminal_receipt_idempotency_key(
            payload_binding
        ):
            errors.append(
                "external base append idempotency_key is not derived from the payload_binding"
            )
        expected_confirm = sink._typed_confirm(
            payload_binding.get("landing_scope_id"), state, base.get("intent_id")
        )
        if base.get("typed_confirm") != expected_confirm:
            errors.append(
                "external base append typed_confirm is not bound to scope/state/intent"
            )
    hard_stops = base.get("hard_stops")
    if (
        not isinstance(hard_stops, list)
        or any(not isinstance(item, str) or not item for item in hard_stops)
        or not EXTERNAL_REQUIRED_HARD_STOPS.issubset(set(hard_stops))
    ):
        errors.append("external worm append intent required hard stops are missing")
    errors.extend(_validate_base_intent_times(base, now=now))
    if base.get("intent_digest") != sink.terminal_receipt_intent_digest(base):
        errors.append("external base intent_digest does not match the canonical intent")
    return errors


def _validate_destination_contract(
    contract: Any, *, compliance_operator_approved: Any, approved_at: Any,
    now: str | None = None,
) -> list[str]:
    if not isinstance(contract, dict):
        return ["external destination contract must be an object"]
    errors: list[str] = []
    for field in DESTINATION_CONTRACT_FIELDS:
        value = contract.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(
                f"external destination contract is missing required non-secret field {field}"
            )
    # 正向格式驗證(P1 primary):自由文字欄位必須是非機密識別碼格式,堵住 AWS 形狀機密走私。
    errors.extend(_destination_format_errors(contract))
    mode = contract.get("object_lock_mode")
    if mode not in OBJECT_LOCK_MODES:
        errors.append(
            "external destination contract object_lock_mode must be GOVERNANCE or COMPLIANCE"
        )
    if mode == "COMPLIANCE" and compliance_operator_approved is not True:
        errors.append(
            "COMPLIANCE object-lock retention requires operator approval "
            "(compliance_operator_approved=true)"
        )
    try:
        retain_dt = sink._parse_time(str(contract.get("retain_until")))
        if approved_at is not None and not retain_dt > sink._parse_time(str(approved_at)):
            errors.append(
                "external destination contract retain_until must be after approved_at"
            )
        # retain_until <= now 是立即可刪的 no-op,拒(E3 P2;僅在 now 提供時檢查)。
        if now is not None and not retain_dt > sink._parse_time(str(now)):
            errors.append(
                "external destination contract retain_until must be in the future "
                "(retain_until <= now is an immediately-deletable no-op)"
            )
    except (TypeError, ValueError):
        errors.append("external destination contract retain_until is not a valid timestamp")
    if sink._contains_secret_like(contract):
        errors.append("external destination contract carries secret-like content")
    return errors


def validate_external_worm_append_intent(intent: Any, *, now: str | None = None) -> list[str]:
    """Validate an external WORM append intent: wrapper + base reuse + contract gate.

    Requires ``target_class=external_worm`` (the inverse of the disposable S1.2
    gate), a complete NON-SECRET destination contract that passes positive-format
    validation (the AWS-shaped secret smuggling guard), COMPLIANCE only with operator
    approval, operator-approved COMPLIANCE bound to any production terminal receipt
    type, ``retain_until`` after ``approved_at`` (and after ``now`` when supplied),
    and a re-derived ``external_intent_digest``.  Freshness is checked only when
    ``now`` is supplied.
    """

    if not isinstance(intent, dict):
        return ["external worm append intent must be an object"]
    errors = [
        f"external worm append intent schema violation: {error}"
        for error in schema_subset_errors(intent, _intent_schema(), _intent_schema())
    ]
    errors.extend(_fieldset_error("append intent", intent, INTENT_WRAPPER_FIELDS))
    if intent.get("schema_version") != INTENT_SCHEMA_VERSION:
        errors.append("external worm append intent schema_version is invalid")
    if intent.get("external_sink_id") != SINK_ID:
        errors.append("external worm append intent external_sink_id is invalid")
    if intent.get("target_class") != TARGET_CLASS:
        errors.append("external worm append intent target_class must be external_worm")
    if intent.get("destination_class") != DESTINATION_CLASS:
        errors.append("external worm append intent destination_class is invalid")
    base = intent.get("append_intent")
    approved_at = None
    if not isinstance(base, dict):
        errors.append("external worm append intent append_intent must be an object")
    else:
        approved_at = base.get("approved_at")
        errors.extend(_validate_base_append_intent(base, now=now))
    contract = intent.get("destination_contract")
    errors.extend(
        _validate_destination_contract(
            contract,
            compliance_operator_approved=intent.get("compliance_operator_approved"),
            approved_at=approved_at,
            now=now,
        )
    )
    # 生產終端 receipt(module_landed / no_candidate)必須綁 operator-approved COMPLIANCE object-lock。
    receipt_type = base.get("terminal_receipt_type") if isinstance(base, dict) else None
    if receipt_type in PRODUCTION_TERMINAL_RECEIPT_TYPES:
        mode = contract.get("object_lock_mode") if isinstance(contract, dict) else None
        if not (mode == "COMPLIANCE" and intent.get("compliance_operator_approved") is True):
            errors.append(
                "a production terminal receipt type requires operator-approved COMPLIANCE "
                "object-lock retention (GOVERNANCE is only for the disposable integration)"
            )
    if sink._contains_secret_like(intent):
        errors.append("external worm append intent carries secret-like content")
    if intent.get("external_intent_digest") != external_intent_digest(intent):
        errors.append(
            "external_intent_digest does not match the canonical external intent"
        )
    return errors


def _validate_result_times(result: dict[str, Any], *, now: str | None) -> list[str]:
    errors: list[str] = []
    try:
        started = sink._parse_time(str(result.get("started_at", "")))
        completed = sink._parse_time(str(result.get("completed_at", "")))
        evidence = sink._parse_time(str(result.get("evidence_expires_at", "")))
        if not started <= completed:
            errors.append("external worm result started_at must not follow completed_at")
        if not completed < evidence:
            errors.append(
                "external worm result completed_at must precede evidence_expires_at"
            )
        if evidence - completed > timedelta(seconds=sink.EVIDENCE_TTL_SECONDS):
            errors.append("external worm result evidence TTL exceeds its ceiling")
        if now is not None:
            current = sink._parse_time(now)
            if not completed <= current < evidence:
                errors.append("external worm result evidence is not fresh")
    except (TypeError, ValueError):
        errors.append("external worm result timestamps are invalid")
    return errors


def validate_external_worm_append_result(
    result: Any, *, intent: dict[str, Any] | None = None, now: str | None = None
) -> list[str]:
    """Validate an external WORM append result: committed/pending/failed invariants.

    ``APPENDED``/``IDEMPOTENT_DEDUP`` must bind a record locator + ``object_version_id``
    + ``checksum_sha256`` + retention with ``external_verification_pending=false`` and
    no ``failure_reason``.  ``EXTERNAL_VERIFICATION_PENDING`` must claim no committed
    field, ``external_verification_pending=true`` and a ``failure_reason``.  ``FAILED``
    claims no committed field.  When ``intent`` is supplied it is cross-bound
    (including checksum == approved payload digest and retention == approved contract).
    """

    if not isinstance(result, dict):
        return ["external worm append result must be an object"]
    errors = [
        f"external worm append result schema violation: {error}"
        for error in schema_subset_errors(result, _result_schema(), _result_schema())
    ]
    errors.extend(_fieldset_error("append result", result, RESULT_FIELDS))
    if result.get("schema_version") != RESULT_SCHEMA_VERSION:
        errors.append("external worm append result schema_version is invalid")
    if result.get("external_sink_id") != SINK_ID:
        errors.append("external worm append result external_sink_id is invalid")
    status = result.get("append_status")
    if status not in EXTERNAL_APPEND_STATUSES:
        errors.append("external worm append result append_status is invalid")
    record_locator = result.get("record_locator")
    version_id = result.get("object_version_id")
    checksum = result.get("checksum_sha256")
    retention = result.get("retention")
    pending = result.get("external_verification_pending")
    failure = result.get("failure_reason")
    committed_claims = (
        ("record_locator", record_locator), ("object_version_id", version_id),
        ("checksum_sha256", checksum), ("retention", retention),
    )
    if status in EXTERNAL_COMMITTED_STATUSES:
        if not isinstance(record_locator, str) or not sink.RECORD_LOCATOR_RE.fullmatch(
            record_locator or ""
        ):
            errors.append(
                "committed external worm result requires a records/<64hex>.record locator"
            )
        if not isinstance(version_id, str) or not version_id:
            errors.append("committed external worm result requires an object_version_id")
        if not sink.DIGEST_RE.fullmatch(str(checksum or "")):
            errors.append("committed external worm result requires a checksum_sha256")
        if not _is_retention_obj(retention):
            errors.append(
                "committed external worm result requires retention {object_lock_mode, "
                "retain_until}"
            )
        if pending is not False:
            errors.append(
                "committed external worm result must have external_verification_pending=false"
            )
        if failure is not None:
            errors.append("committed external worm result cannot carry a failure_reason")
    elif status == "EXTERNAL_VERIFICATION_PENDING":
        for name, value in committed_claims:
            if value is not None:
                errors.append(
                    f"EXTERNAL_VERIFICATION_PENDING external worm result cannot claim {name}"
                )
        if pending is not True:
            errors.append(
                "EXTERNAL_VERIFICATION_PENDING result must have "
                "external_verification_pending=true"
            )
        if not isinstance(failure, str) or not failure.strip():
            errors.append("EXTERNAL_VERIFICATION_PENDING result requires a failure_reason")
    else:  # FAILED / unknown status already flagged above
        for name, value in committed_claims:
            if value is not None:
                errors.append(f"{status} external worm result cannot claim {name}")
        if pending is not False:
            errors.append(
                f"{status} external worm result must have external_verification_pending=false"
            )
        if not isinstance(failure, str) or not failure.strip():
            errors.append(f"{status} external worm result requires a failure_reason")
    if isinstance(intent, dict):
        base = intent.get("append_intent") or {}
        contract = intent.get("destination_contract") or {}
        for field, want in (
            ("intent_id", base.get("intent_id")),
            ("external_intent_digest", intent.get("external_intent_digest")),
            ("idempotency_key", base.get("idempotency_key")),
            ("append_actor_id", base.get("append_actor_id")),
            ("credential_channel_id", contract.get("credential_channel_id")),
        ):
            if result.get(field) != want:
                errors.append(f"external worm result {field} is not bound to the intent")
        if status in EXTERNAL_COMMITTED_STATUSES:
            approved_digest = (base.get("payload_binding") or {}).get(
                "terminal_payload_digest"
            )
            if checksum != approved_digest:
                errors.append(
                    "external worm result checksum is not bound to the approved intent "
                    "payload digest"
                )
            if _is_retention_obj(retention):
                if retention.get("object_lock_mode") != contract.get("object_lock_mode"):
                    errors.append(
                        "external worm result retention mode is not bound to the approved "
                        "object_lock_mode"
                    )
                if not _retain_until_equal(
                    retention.get("retain_until"), contract.get("retain_until")
                ):
                    errors.append(
                        "external worm result retain_until is not bound to the approved "
                        "retain_until"
                    )
    errors.extend(_validate_result_times(result, now=now))
    if sink._contains_secret_like(result):
        errors.append("external worm append result carries secret-like content")
    if result.get("result_digest") != external_result_digest(result):
        errors.append("external worm result_digest does not match the canonical result")
    return errors


def _validate_ack_times(ack: dict[str, Any], *, now: str | None) -> list[str]:
    errors: list[str] = []
    try:
        observed = sink._parse_time(str(ack.get("observed_at", "")))
        expires = sink._parse_time(str(ack.get("expires_at", "")))
        if not observed < expires:
            errors.append("external worm readback observed_at must precede expires_at")
        if expires - observed > timedelta(seconds=sink.EVIDENCE_TTL_SECONDS):
            errors.append("external worm readback TTL exceeds its ceiling")
        if now is not None:
            current = sink._parse_time(now)
            if not observed <= current < expires:
                errors.append("external worm readback ack is not fresh")
    except (TypeError, ValueError):
        errors.append("external worm readback ack timestamps are invalid")
    return errors


def validate_external_worm_readback_ack(
    ack: Any, *, result: dict[str, Any] | None = None, now: str | None = None
) -> list[str]:
    """Validate an independent external readback ACK: distinctness + immutability proof.

    A positive ACK (``ack=true``) requires ``same_actor_violation=false``, a
    verifier distinct from the committed append actor, ``immutability_proven=true``
    (all of checksum/version/retention match AND the bucket Object-Lock ENABLED — a
    NON-DESTRUCTIVE config read, never a delete/retention-shortening probe), and a
    ``readback_checksum_sha256`` equal to the result's ``checksum_sha256``.  A
    same-actor readback must set ``same_actor_violation=true`` and refuse to ACK.
    ``immutability_proven`` must equal the conjunction of the four proof booleans.
    """

    if not isinstance(ack, dict):
        return ["external worm readback ack must be an object"]
    errors = [
        f"external worm readback ack schema violation: {error}"
        for error in schema_subset_errors(ack, _readback_schema(), _readback_schema())
    ]
    errors.extend(_fieldset_error("readback ack", ack, READBACK_FIELDS))
    if ack.get("schema_version") != READBACK_SCHEMA_VERSION:
        errors.append("external worm readback ack schema_version is invalid")
    if ack.get("external_sink_id") != SINK_ID:
        errors.append("external worm readback ack external_sink_id is invalid")
    verifier = ack.get("readback_verifier_id")
    same_actor_violation = ack.get("same_actor_violation")
    acked = ack.get("ack")
    checksum_match = ack.get("checksum_match")
    version_id_match = ack.get("version_id_match")
    retention_match = ack.get("retention_match")
    object_lock_enabled = ack.get("object_lock_enabled")
    immutability_proven = ack.get("immutability_proven")
    # immutability_proven 必須等於四個「非破壞式」證明布林的合取(不信任 caller 自填的旗標):
    # checksum/version/retention(mode + future retain-until)match + 桶層 Object-Lock ENABLED。
    expected_proven = bool(
        checksum_match is True and version_id_match is True and retention_match is True
        and object_lock_enabled is True
    )
    if immutability_proven is not expected_proven:
        errors.append(
            "external worm readback immutability_proven must equal (checksum_match & "
            "version_id_match & retention_match & object_lock_enabled)"
        )
    if isinstance(result, dict):
        for field in ("intent_id", "result_digest"):
            if ack.get(field) != result.get(field):
                errors.append(
                    f"external worm readback {field} is not bound to the result"
                )
        read_locator = ack.get("read_record_locator")
        if read_locator is not None and read_locator != result.get("record_locator"):
            errors.append(
                "external worm readback read_record_locator is not bound to the result record"
            )
        read_version = ack.get("read_object_version_id")
        if read_version is not None and read_version != result.get("object_version_id"):
            errors.append(
                "external worm readback read_object_version_id is not bound to the result "
                "version"
            )
        append_actor = result.get("append_actor_id")
        # 獨立性由綁定身分推導,而非信任 caller 的 same_actor_violation 布林。
        bound_same_actor = verifier == append_actor
        if bound_same_actor and same_actor_violation is not True:
            errors.append(
                "external worm readback by the append actor must set same_actor_violation=true"
            )
        if not bound_same_actor and same_actor_violation is not False:
            errors.append(
                "external worm readback same_actor_violation is inconsistent with the "
                "verifier identity"
            )
        if acked is True:
            if bound_same_actor:
                errors.append(
                    "a positive external worm readback ACK cannot be issued by the bound "
                    "append actor"
                )
            if read_locator != result.get("record_locator"):
                errors.append(
                    "a positive external worm readback ACK must read the result record"
                )
            if read_version != result.get("object_version_id"):
                errors.append(
                    "a positive external worm readback ACK version-id does not match the "
                    "persisted object"
                )
            if ack.get("readback_checksum_sha256") != result.get("checksum_sha256"):
                errors.append(
                    "a positive external worm readback ACK checksum does not match the "
                    "persisted object"
                )
    if acked is True:
        if same_actor_violation is not False:
            errors.append(
                "a positive external worm readback ACK cannot be a same-actor violation"
            )
        if immutability_proven is not True:
            errors.append(
                "a positive external worm readback ACK requires immutability_proven=true "
                "(checksum/version/retention match + bucket Object-Lock enabled)"
            )
        if not sink.DIGEST_RE.fullmatch(str(ack.get("readback_checksum_sha256") or "")):
            errors.append(
                "a positive external worm readback ACK requires a readback_checksum_sha256"
            )
    if same_actor_violation is True and acked is not False:
        errors.append("a same-actor external worm readback must refuse to ACK")
    errors.extend(_validate_ack_times(ack, now=now))
    if sink._contains_secret_like(ack):
        errors.append("external worm readback ack carries secret-like content")
    if ack.get("ack_digest") != external_ack_digest(ack):
        errors.append("external worm ack_digest does not match the canonical ack")
    return errors
