"""S2.1 ALR quiesce / evidence / static-guard SOURCE Adapter (AIML WP3).

把 S2.0(生產唯讀 observer bootstrap)接成一條「owner-scoped、可逆的 ALR runtime quiesce fence」的
SOURCE seam:一張 exact typed intent、一個**多訊號 ownership-confirmation predicate**(只 fence 一個
confirmed single owner,對 stale / ambiguous / window-violated 一律 fail-closed)、一個以該 unit **自身
生命週期 stop/start** 施加的可逆 fence(絕非 name/pattern kill)、一段 bounded observation-window 靜態
守恆取樣、以及**重用 S2.0 唯讀 observer** 蒐集 DB 端 quiesce 證據。這是 S2.1 的 **SOURCE_READY** 交付,
不是 EFFECT_DONE:真正對生產 ALR 的 fence 在有 ``S2.0@EFFECT_DONE`` 與一張 exact operator SSHSIG 之前
**恆 fail-closed**——回傳一個 typed ``EXTERNAL_VERIFICATION_PENDING`` result,**永不**假成功、**永不**
signal/kill 任何真實 process。

**誠實界線(CLAUDE 四 / Typed Authority Matrix)。** land 時不接觸 live ALR 的 ``/proc`` /
``systemctl`` / ``stop``。可拋棄叢集測試會真的 ``initdb`` 起一個丟棄式 cluster、真的取得/釋放/再取得
``pg_try_advisory_lock('alr_event_consumer_v1')`` 並以 S2.0 唯讀 observer 角色真觀察 ``pg_locks`` /
``pg_stat_activity`` / consumer-session relation(LOCAL_REPRODUCIBLE);host 端 inventory / fence 邏輯跑在
**模擬 /proc + 注入 system-level systemctl callable + 注入 fence_ops** 上(絕無真 process 被 signal)。真正的 live
``/proc`` / ``systemctl`` / system-level ``systemctl stop/start`` 一律 DEFERRED 給 S2.1 EFFECT session。九個
authority 恆 false;沒有任何 receipt 序列化機密(operator 私鑰既不在 Mac 也不在 trade-core;DSN 由
``LoadCredentialEncrypted``/``%d/pg-dsn`` 供給,路徑被記錄、內容永不)。canonical self-digest 只證完整性,不證誰執行、不證外部事實。

**Domain separation。** operator SSHSIG 沿用 S0.3/S1 既有信任根公鑰/指紋,但以**專屬 identity +
namespace**(``aiml-s2-quiesce-fence-operator-v1`` / ``arcane-equilibrium-aiml-s2-quiesce-fence``)達成
domain separation:一張以 S1 target-host / S2.0 observer namespace 簽的 permit 於此因 namespace/identity
不符被拒。applier != 獨立驗證者(role/node/process/capture 皆須相異)。

**O-1 effect 排序(SOURCE 不受影響,備註留給 EFFECT session)。** S1.6 最終 runtime 身分為
``content_addressed_fixed_path``(§8 的 ``/opt/arcane-equilibrium/aiml/runtimes/<digest>/bin/python3 -I -m …``,
非系統 Python、非 OCI);S2.1 EFFECT 的 fence apply 只能在 ALR unit 已被 S2.4 安裝且 S2.5 起跑之後演練(即
EFFECT fence sequences after S2.4 + S2.5)。
WP3 ``SOURCE_READY`` 以模擬 owner 交付,不受此排序影響。

**O-4 唯讀 relation 契約(參數化,非硬編第二特權路徑)。** intent 的 ``observed_relations`` 宣告 S2.1
經 S2.0 唯讀 observer 讀取的 relation 清單(含 ``learning.alr_consumer_events``);``consumer_session_relation``
必為其成員。S2.1 EFFECT session 的 S2.0 observer intent(operator packet)**必須** GRANT SELECT 於這些
relation,S2.1 才能在最小權限下讀 consumer-session 狀態。此處不硬編任何第二條特權 DB 路徑。

**O-5 flock 為佐證(非必要)訊號。** PG advisory lock(``alr_event_consumer_v1``)是**權威的**
at-most-one-owner 證明;flock 於 ``consumer.lock`` 僅作 corroborating 訊號,ownership predicate 不以其
為必要條件。

stdlib-first;``psycopg2`` 只在可拋棄叢集路徑由測試延遲匯入。唯讀消費 S2.0
(``generate_observer_grant_sql`` / ``observer_bootstrap_apply`` 等)/ component_effects(``_pg_ident``)/
S1 trusted-host(SSHSIG 信任根與驗證基元)/ 中央 validator(``canonical_digest`` /
``artifact_self_digest``);中央 validator 加性委派這四個 typed schema,**不注入** live ``route_task``
effect 節點或 closure effect 綁定(那要 S2.1 EFFECT session)。
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = Path(__file__).resolve()
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

# 唯讀消費:S1 target-host 的 SSHSIG 信任根與驗證基元;S2.0 唯讀 observer bootstrap 的 grant-set/apply/rollback;
# 中央 validator 的 canonical_digest / artifact_self_digest(component_effects 的 _pg_ident 引號已隨 _safe_ident
# 下沉至 inventory 下層,本上層不再直接依賴 ce)。
import agent_governance_aiml_trusted_host as trusted  # noqa: E402
import agent_governance_pg_observer_bootstrap as observer  # noqa: E402
import aiml_gate_receipt_validator as central_validator  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402

# ── S2.1 quiesce ownership/inventory/sampler 下層(拆分:讓 Codex P1 修正落地而不破 2000 行硬上限)──
# 本上層保留 schema 委派、SSHSIG 授權、四 artifact builder/validator、fence ops、apply 編排與 secret-armor;
# 下層 SSOT 提供 host/DB 唯讀讀取、inventory 組裝、ownership predicate 與靜態守恆取樣。以下 re-export 讓既有
# 公開 API / 測試沿用 ``q.<name>`` 存取不變(常量值一致 → intent_id / self_digest / frozen digest 不漂移)。
from agent_governance_alr_quiesce_inventory import (  # noqa: E402
    QuiesceFenceError,
    QuiesceHostReadError,
    DIGEST_RE,
    EVIDENCE_TTL_SECONDS,
    MAX_WINDOW_SAMPLES,
    WINDOW_STATUS_HELD,
    WINDOW_STATUS_VIOLATED,
    WINDOW_STATUS_UNDERSPECIFIED,
    UNIT_NAME,
    ADVISORY_LOCK_NAME,
    LISTEN_CHANNEL,
    DEFAULT_CONSUMER_SESSION_RELATION,
    ALR_CONNECTION_ROLE,
    SYSTEMD,
    QUIESCE_SHOW_PROPERTIES,
    ENV_DECLARED_KEYS,
    compute_owner_fingerprint,
    compute_stable_identity_fingerprint,
    read_db_quiesce,
    _consumer_session_status,
    _is_alr_longlived_cmdline,
    build_owner_inventory,
    _confirm_grade_signals_ok,
    _owner_verdict,
    confirm_alr_owner,
    _classify_static_guard,
    collect_static_guard_window,
)  # noqa: E402


ADAPTER_ID = "alr_quiesce_fence_adapter_v1"
OWNER_SESSION = "S2.1"

INTENT_SCHEMA_VERSION = "quiesce_intent_v1"
OBSERVATION_SCHEMA_VERSION = "quiesce_observation_v1"
RESULT_SCHEMA_VERSION = "quiesce_result_v1"
ROLLBACK_SCHEMA_VERSION = "quiesce_rollback_v1"

SCHEMA_DIR = ML_TRAINING_DIR / "schemas" / "aiml_gate_receipts"
INTENT_SCHEMA_PATH = SCHEMA_DIR / f"{INTENT_SCHEMA_VERSION}.schema.json"
OBSERVATION_SCHEMA_PATH = SCHEMA_DIR / f"{OBSERVATION_SCHEMA_VERSION}.schema.json"
RESULT_SCHEMA_PATH = SCHEMA_DIR / f"{RESULT_SCHEMA_VERSION}.schema.json"
ROLLBACK_SCHEMA_PATH = SCHEMA_DIR / f"{ROLLBACK_SCHEMA_VERSION}.schema.json"

HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
RELATION_RE = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$")

TARGET_CLASSES = frozenset({"disposable_local", "production"})
DISPOSABLE_TARGET_CLASS = "disposable_local"
PRODUCTION_TARGET_CLASS = "production"
EVIDENCE_CLASSES = frozenset({"LOCAL_REPRODUCIBLE", "STRUCTURAL_ONLY"})
RESULT_STATUSES = frozenset({
    "QUIESCED_STATIC_GUARDS_HELD",
    "EXTERNAL_VERIFICATION_PENDING",
    "STALE_OWNER_FAIL_CLOSED",
    "AMBIGUOUS_OWNER_REFUSED",
    "OBSERVATION_WINDOW_VIOLATED",
    "NOT_RESTORED",
    "FAILED",
})
# 非 pending 的「已進入 inventory」路徑(有效 SSHSIG 已驗過)才會產出的 status。
APPLIED_LANE_STATUSES = frozenset({
    "QUIESCED_STATIC_GUARDS_HELD",
    "STALE_OWNER_FAIL_CLOSED",
    "AMBIGUOUS_OWNER_REFUSED",
    "OBSERVATION_WINDOW_VIOLATED",
    "NOT_RESTORED",
    "FAILED",
})

TTL_CEILING_SECONDS = 3600
MIN_WINDOW_SECONDS = 1
# EVIDENCE_TTL_SECONDS / MAX_WINDOW_SAMPLES / WINDOW_STATUS_* 與被 fence 的唯一 owner 具體常量(UNIT_NAME /
# ADVISORY_LOCK_NAME / LISTEN_CHANNEL / DEFAULT_CONSUMER_SESSION_RELATION / ALR_CONNECTION_ROLE / SYSTEMD /
# QUIESCE_SHOW_PROPERTIES / ENV_DECLARED_KEYS 等)已下沉至 agent_governance_alr_quiesce_inventory,於上方 re-export。

# intent 若出現任一鍵即代表呼叫端試圖夾帶 raw 指令 / signal / pid 清單 / name-kill 面 → fail-closed。
FORBIDDEN_INTENT_KEYS = frozenset({
    "raw_command", "command", "cmd", "argv", "statements", "signal", "signals",
    "pid", "pid_list", "pids", "pkill", "kill", "kill_by_name", "kill_by_pattern",
    "pattern", "match", "sigterm", "sigkill", "force",
})

# ── operator SSHSIG 信任根(沿用 S0.3/S1 公鑰/指紋,專屬 identity + namespace 做 domain separation) ──
OPERATOR_AUTHORIZATION_SCHEMA_VERSION = "quiesce_fence_operator_authorization_v1"
OPERATOR_IDENTITY = "aiml-s2-quiesce-fence-operator-v1"
OPERATOR_FINGERPRINT = trusted.EXPECTED_S1_TARGET_HOST_SIGNER_FINGERPRINT
OPERATOR_PUBLIC_KEY = trusted.S1_TRUSTED_TARGET_HOST_PUBLIC_KEY
OPERATOR_ALGORITHM = trusted.EXECUTION_BUNDLE_ALGORITHM
OPERATOR_SIGNATURE_NAMESPACE = "arcane-equilibrium-aiml-s2-quiesce-fence"
MAX_AUTHORIZATION_TTL = timedelta(minutes=15)
AUTHORIZATION_FIELDS = frozenset({
    "schema_version", "signer_identity", "signer_fingerprint", "algorithm",
    "signature_namespace", "intent_id", "intent_digest", "source_head",
    "target_host", "applier_node_id", "postcheck_node_id",
    "issued_at", "expires_at", "authorization_digest",
})

# 機密掃描(沿用 S2.0 樣態:github token / credential 賦值 / auth header / postgres DSN 憑證形)。
SECRET_LIKE_RE = re.compile(
    r"(?:github_pat_|gh[pousr]_[A-Za-z0-9]{12,})"
    r"|(?:access[_-]?token|auth(?:orization)?|client[_-]?secret|password|"
    r"pgpassword|private[_-]?key)\s*[:=]"
    r"|(?:basic|bearer)\s+[A-Za-z0-9._~+/=-]{12,}"
    r"|postgres(?:ql)?://[^\s:/@]+:[^\s:/@]+@",
    re.IGNORECASE,
)


# QuiesceFenceError / QuiesceHostReadError 定義於 inventory 下層(上方 re-export);SecretLeakageError(secret-armor)
# 留在本上層,續以下層的 QuiesceFenceError 為基底。
class SecretLeakageError(QuiesceFenceError):
    """Raised when a would-be artifact field carries secret-like content."""


# --------------------------------------------------------------------------- #
# canonical digest helpers (reuse central validator; local bytes for SSHSIG)
# --------------------------------------------------------------------------- #
canonical_digest = central_validator.canonical_digest
artifact_self_digest = central_validator.artifact_self_digest


def canonical_bytes(value: Any) -> bytes:
    """Return the exact bytes the operator signs / the SSHSIG is verified against."""

    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def source_sha256() -> str:
    """Return the sha256 identity of this Adapter module source."""

    return _file_sha256(SOURCE_PATH)


@lru_cache(maxsize=None)
def _schema(path_str: str) -> dict[str, Any]:
    return json.loads(Path(path_str).read_text(encoding="utf-8"))


def _parse_time(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone is required")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _plus_seconds(iso: str, seconds: int) -> str:
    return _iso(_parse_time(iso) + timedelta(seconds=seconds))


def artifact_digest_excluding_self(artifact: dict[str, Any]) -> str:
    return canonical_digest({k: v for k, v in artifact.items() if k != "self_digest"})


def authorization_digest(value: dict[str, Any]) -> str:
    return canonical_digest({k: v for k, v in value.items() if k != "authorization_digest"})


# --------------------------------------------------------------------------- #
# secret scan (fail-closed) — mirrors S2.0 exactly
# --------------------------------------------------------------------------- #
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
        raise SecretLeakageError("quiesce payload carries secret-like content")


# operator_signature_pem 的 SSHSIG armor 標記列(去 armor 時據此剝除,取得純 body)。
_SSH_SIGNATURE_ARMOR_MARKERS = (
    "-----BEGIN SSH SIGNATURE-----",
    "-----END SSH SIGNATURE-----",
)


def _operator_signature_pem_body_is_strict_base64(value: Any) -> bool:
    """去 armor 後判斷 body 是否為嚴格標準 base64(鏡像 S2.0 FIX-10/FIX-11 的可證安全排除前提)。

    真 ``ssh-keygen -Y sign`` armor body 去 armor 後可 ``base64.b64decode(validate=True)``;可讀 plaintext
    憑證形(``password=…`` / ``pgpassword=…`` / ``bearer …`` / DSN)一律 decode 失敗。body 一旦被證為嚴格
    base64,即不可能夾帶可讀 plaintext 機密,故 ``_result_secret_scan_view`` 排除此欄位可證安全。非字串 /
    空 body / 不可 decode 一律回 False(fail-closed)。
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
    # build 期護欄:operator_signature_pem 若為非 None 字串,其 armor body 必為嚴格 base64,否則絕不 emit。
    if value is not None and not _operator_signature_pem_body_is_strict_base64(value):
        raise SecretLeakageError(
            "operator_signature_pem body is not strict base64 (possible non-signature payload)"
        )


def _result_secret_scan_view(result: dict[str, Any]) -> dict[str, Any]:
    # operator_signature_pem 是**公開的** SSHSIG(非機密);其 body 由上方 strict-base64 護欄把關,故此處
    # 一致地把它排除在 secret 掃描之外,避免對合法 receipt 造成 flaky false-positive(對稱於 S2.0)。
    return {k: v for k, v in result.items() if k != "operator_signature_pem"}


# --------------------------------------------------------------------------- #
# owner-scoped reversible fence / un-fence (§4 — the unit's OWN lifecycle only)
# --------------------------------------------------------------------------- #
def owner_scoped_fence(fence_ops: Any) -> None:
    """Fence = the confirmed unit's OWN system-level ``systemctl stop`` (owner-scoped, zero collateral).

    NEVER a name/pattern kill, NEVER ``kill <pid>``.  In the SOURCE lane ``fence_ops`` is an injected
    simulated-owner handle whose ``stop()`` flips the injected systemctl state to inactive and releases
    the throwaway advisory lock; no real process is signalled.
    """

    # F2(EFFECT 契約備註):EFFECT 注入的 ``fence_ops.stop()`` 必為**阻塞式** system-level ``systemctl stop``(回傳前
    # unit 已真正 inactive/dead,靜態守恆窗才觀察得到排空狀態)。
    fence_ops.stop()


def owner_scoped_unfence(fence_ops: Any) -> bool:
    """Un-fence = the unit's OWN system-level ``systemctl start``.  Returns whether the start call succeeded.

    Every quiesce path attempts un-fence (even on failure) so the runtime is never left fenced by this
    seam.  A failed start (raises) is recorded as an honest NOT_RESTORED, never masked.
    """

    try:
        fence_ops.start()
    except Exception:  # noqa: BLE001 - a failed un-fence is an honest NOT_RESTORED, not a crash
        return False
    return True


# --------------------------------------------------------------------------- #
# operator SSHSIG authorization (reuse the S1 pattern; NEW namespace + identity)
# --------------------------------------------------------------------------- #
def build_operator_authorization(*, intent: dict[str, Any], source_head: str) -> dict[str, Any]:
    """Project one exact typed quiesce intent into the bytes the operator signs."""

    if not isinstance(intent, dict):
        raise QuiesceFenceError("operator authorization intent must be an object")
    if not HEAD_RE.fullmatch(str(source_head)):
        raise QuiesceFenceError("operator authorization source_head must be exact 40-hex")
    for field in ("intent_id", "self_digest", "target_host", "applier_node_id", "postcheck_node_id", "created_at", "expires_at"):
        if not intent.get(field):
            raise QuiesceFenceError(f"operator authorization intent lacks required field {field}")
    if not DIGEST_RE.fullmatch(str(intent["intent_id"])):
        raise QuiesceFenceError("operator authorization intent_id must be a sha256 digest")
    if intent["self_digest"] != artifact_digest_excluding_self(intent):
        raise QuiesceFenceError("operator authorization intent self_digest does not match its bytes")
    issued = _parse_time(intent["created_at"])
    intent_expiry = _parse_time(intent["expires_at"])
    expires = min(intent_expiry, issued + MAX_AUTHORIZATION_TTL)
    if expires <= issued:
        raise QuiesceFenceError("operator authorization intent interval is invalid")
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
        "issued_at": _iso(issued),
        "expires_at": _iso(expires),
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
    """Validate structure, exact-intent bindings, time window, trust root, and SSHSIG (domain-separated)."""

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
    elif intent.get("self_digest") != artifact_digest_excluding_self(intent):
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
    """STRUCTURAL-only operator_authorization binding for an emitted QUIESCED receipt.

    誠實界線(**只證完整性,不證真偽**):此處只驗「精確欄位契約 + domain-separation 常量 +
    authorization_digest 完整性 + 三個 intent 綁定」。**刻意不**做 SSHSIG 密碼學再驗——真正對 operator
    公鑰的再驗 + platform attestation 屬 S2.1 EFFECT session。可拋棄 receipt 由每測試臨時金鑰簽(非固定
    信任根),離線密碼學再驗不可行,故此結構綁定只把 bogus / intent 不符的授權擋掉,絕不宣稱已認證誰簽。
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
# intent builder + validator
# --------------------------------------------------------------------------- #
def _is_system_catalog_schema(relation: str) -> bool:
    # FIX-W3-5(深度防禦):consumer_session_relation 是唯一被參數化的 DB-read 目標,即便在簽名 intent 下也絕不允許把它
    # 瞄準 pg_catalog/pg_toast/pg_temp_*/information_schema 等 catalog 表(今日已由 observer 最小權限+SSHSIG 綁定緩解)。
    schema = str(relation).split(".", 1)[0]
    return schema.startswith("pg_") or schema == "information_schema"


def build_quiesce_intent(
    *,
    target_class: str,
    target_host: str,
    unit_fragment_path: str,
    expected_owner_fingerprint: str,
    flock_path: str,
    observed_relations: list[str],
    consumer_session_relation: str = DEFAULT_CONSUMER_SESSION_RELATION,
    observation_window: dict[str, int],
    applier_node_id: str,
    postcheck_node_id: str,
    created_at: str,
    ttl_seconds: int,
    source_head: str,
    intent_id: str | None = None,
) -> dict[str, Any]:
    """Build one canonical, self-hashed ``quiesce_intent_v1``."""

    if target_class not in TARGET_CLASSES:
        raise QuiesceFenceError(f"unrecognized target_class: {target_class!r}")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not (1 <= ttl_seconds <= TTL_CEILING_SECONDS):
        raise QuiesceFenceError(f"ttl_seconds must be within [1, {TTL_CEILING_SECONDS}]")
    if applier_node_id == postcheck_node_id:
        raise QuiesceFenceError("applier_node_id must differ from postcheck_node_id (applier != verifier)")
    if not HEAD_RE.fullmatch(str(source_head)):
        raise QuiesceFenceError("source_head must be a 40-hex commit id")
    if not isinstance(observed_relations, list) or not observed_relations:
        raise QuiesceFenceError("intent must declare at least one observed relation")
    for relation in (*observed_relations, consumer_session_relation):
        if not RELATION_RE.fullmatch(str(relation)):
            raise QuiesceFenceError(f"observed relation must be schema-qualified pg identifiers: {relation!r}")
    if consumer_session_relation not in observed_relations:
        # O-4:consumer_session_relation 必為宣告的 observed_relations 成員(S2.0 observer 必 GRANT SELECT 它)。
        raise QuiesceFenceError("consumer_session_relation must be a member of observed_relations")
    if _is_system_catalog_schema(consumer_session_relation):
        # FIX-W3-5:DB-read 目標不得瞄準系統/catalog schema(pg_*/information_schema)。
        raise QuiesceFenceError("consumer_session_relation must not target a system-catalog schema (pg_*/information_schema)")
    if not isinstance(observation_window, dict):
        raise QuiesceFenceError("observation_window must be an object")
    duration = observation_window.get("duration_seconds")
    min_samples = observation_window.get("min_samples")
    interval = observation_window.get("sample_interval_seconds")
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in (duration, min_samples, interval)):
        raise QuiesceFenceError("observation_window values must be integers")
    if not (MIN_WINDOW_SECONDS <= duration <= TTL_CEILING_SECONDS):
        raise QuiesceFenceError(f"observation_window duration must be within [{MIN_WINDOW_SECONDS}, {TTL_CEILING_SECONDS}]")
    if min_samples < 2:
        raise QuiesceFenceError("observation_window min_samples must be >= 2")
    if interval < 1:
        raise QuiesceFenceError("observation_window sample_interval_seconds must be >= 1")
    # FIX-C4(Codex :1177):取樣節奏不得超出宣告窗——(min_samples-1)*sample_interval_seconds > duration_seconds
    # 表示湊足 min_samples 就必然把 fence 持有超出 duration(甚至遠超 TTL,如 (512-1)*3600s 對 1s 窗 ≈ 511 小時);build 期即拒。
    if (min_samples - 1) * interval > duration:
        raise QuiesceFenceError(
            "observation_window cadence (min_samples-1)*sample_interval_seconds must not exceed duration_seconds"
        )
    # FIX-C4-TTL(E2+OPS must-fix-before-EFFECT):把 fence-hold 窗綁到 operator 簽署窗。fence 最壞持有時間為
    # duration + 一個取樣節奏步(collect_static_guard_window 的硬截止 hard_deadline_seconds);此值必須可證地在
    # 「intent 有效窗(ttl_seconds)」與「operator 簽署的 ≤15 分鐘授權窗(MAX_AUTHORIZATION_TTL=900s)」兩者之內
    # 釋放。否則一張 15 分鐘授權的 fence 可能物理上持續 4-8× 於其簽署窗之外(applier 只在頂端驗一次有效性,窗中
    # 不再驗)→ build 期即拒。
    max_authorization_ttl_seconds = int(MAX_AUTHORIZATION_TTL.total_seconds())
    if duration + interval > ttl_seconds or duration + interval > max_authorization_ttl_seconds:
        raise QuiesceFenceError(
            "observation_window worst-case hold (duration_seconds + sample_interval_seconds) must not exceed "
            f"ttl_seconds nor the operator authorization ceiling ({max_authorization_ttl_seconds}s)"
        )
    created = _parse_time(created_at)
    expires = created + timedelta(seconds=ttl_seconds)
    intent: dict[str, Any] = {
        "schema_version": INTENT_SCHEMA_VERSION,
        "intent_id": intent_id or canonical_digest({
            "unit": UNIT_NAME, "target_host": target_host, "expected_owner_fingerprint": expected_owner_fingerprint,
            "created_at": created.isoformat(), "source_head": source_head,
        }),
        "target_class": target_class,
        "target_host": target_host,
        "unit_name": UNIT_NAME,
        "unit_fragment_path": unit_fragment_path,
        "expected_owner_fingerprint": expected_owner_fingerprint,
        "advisory_lock_name": ADVISORY_LOCK_NAME,
        "flock_path": flock_path,
        "listen_channel": LISTEN_CHANNEL,
        "observed_relations": list(observed_relations),
        "consumer_session_relation": consumer_session_relation,
        "observation_window": {
            "duration_seconds": duration,
            "min_samples": min_samples,
            "sample_interval_seconds": interval,
        },
        "ttl_seconds": ttl_seconds,
        "applier_node_id": applier_node_id,
        "postcheck_node_id": postcheck_node_id,
        "created_at": _iso(created),
        "expires_at": _iso(expires),
        "source_head": source_head,
    }
    _guard_no_secret(intent)
    intent["self_digest"] = artifact_digest_excluding_self(intent)
    return intent


def validate_quiesce_fence_intent(intent: Any, *, now: str | None = None) -> list[str]:
    """Validate intent structure/integrity + the forbidden-key allowlist + O-4 membership + time window."""

    if not isinstance(intent, dict):
        return ["quiesce intent must be an object"]
    forbidden = sorted(FORBIDDEN_INTENT_KEYS & set(intent))
    if forbidden:
        return ["quiesce intent carries forbidden raw-command / signal / kill keys: " + ", ".join(forbidden)]
    schema = _schema(str(INTENT_SCHEMA_PATH))
    errors = [
        f"quiesce intent schema violation: {error}"
        for error in schema_subset_errors(intent, schema, schema)
    ]
    if errors:
        return errors
    if intent.get("applier_node_id") == intent.get("postcheck_node_id"):
        errors.append("quiesce intent applier_node_id must differ from postcheck_node_id")
    if intent.get("consumer_session_relation") not in intent.get("observed_relations", []):
        errors.append("quiesce intent consumer_session_relation must be a declared observed relation")
    if _is_system_catalog_schema(str(intent.get("consumer_session_relation", ""))):
        # FIX-W3-5:即使 schema/簽名皆合法,DB-read 目標也不得為系統/catalog schema。
        errors.append("quiesce intent consumer_session_relation must not target a system-catalog schema")
    # FIX-C4(Codex :1177):取樣節奏不得超出宣告窗(defense-in-depth,擋繞過 build 的偽造 intent)。
    _ow = intent.get("observation_window") if isinstance(intent.get("observation_window"), dict) else {}
    _d, _ms, _iv = _ow.get("duration_seconds"), _ow.get("min_samples"), _ow.get("sample_interval_seconds")
    if (
        all(isinstance(v, int) and not isinstance(v, bool) for v in (_d, _ms, _iv))
        and (_ms - 1) * _iv > _d
    ):
        errors.append(
            "quiesce intent observation_window cadence (min_samples-1)*sample_interval_seconds exceeds duration_seconds"
        )
    # FIX-C4-TTL(E2+OPS must-fix,defense-in-depth):fence 最壞持有窗(duration + 一步取樣節奏)必須 <= ttl_seconds
    # 且 <= MAX_AUTHORIZATION_TTL(900s),保證在 intent 有效窗與 operator ≤15 分鐘簽署窗內釋放(擋繞過 build 的偽造 intent)。
    _ttl = intent.get("ttl_seconds")
    _max_auth_ttl = int(MAX_AUTHORIZATION_TTL.total_seconds())
    if (
        all(isinstance(v, int) and not isinstance(v, bool) for v in (_d, _iv, _ttl))
        and (_d + _iv > _ttl or _d + _iv > _max_auth_ttl)
    ):
        errors.append(
            "quiesce intent observation_window worst-case hold (duration_seconds + sample_interval_seconds) "
            f"exceeds ttl_seconds or the operator authorization ceiling ({_max_auth_ttl}s)"
        )
    if _contains_secret_like(intent):
        errors.append("quiesce intent carries secret-like content")
    if intent.get("self_digest") != artifact_digest_excluding_self(intent):
        errors.append("quiesce intent self_digest does not match canonical intent")
    try:
        created = _parse_time(intent["created_at"])
        expires = _parse_time(intent["expires_at"])
        if expires <= created:
            errors.append("quiesce intent created_at must precede expires_at")
        if expires - created > timedelta(seconds=TTL_CEILING_SECONDS):
            errors.append("quiesce intent TTL exceeds its ceiling")
        if now is not None:
            current = _parse_time(now)
            if not created <= current < expires:
                errors.append("quiesce intent is outside its validity window")
    except (KeyError, TypeError, ValueError):
        errors.append("quiesce intent timestamps are invalid")
    return errors


# --------------------------------------------------------------------------- #
# observation builder + validator
# --------------------------------------------------------------------------- #
def build_quiesce_observation(
    *,
    phase: str,
    verdict: str,
    candidate_count: int,
    owner_fingerprint: str,
    host_inventory: dict[str, Any],
    db_quiesce: dict[str, Any],
    credential_exposure: dict[str, Any],
    applier_node: str,
    verifier_node: str,
    verifier_capture_digest: str,
    observed_at: str,
    ttl_seconds: int = EVIDENCE_TTL_SECONDS,
) -> dict[str, Any]:
    """Build one canonical ``quiesce_observation_v1`` (evidence sample)."""

    if verifier_node == applier_node:
        raise QuiesceFenceError("observation verifier_node must differ from applier_node")
    if not DIGEST_RE.fullmatch(str(verifier_capture_digest)):
        raise QuiesceFenceError("observation verifier_capture_digest must be a sha256 digest")
    observed = _parse_time(observed_at)
    observation: dict[str, Any] = {
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "phase": phase,
        "verdict": verdict,
        "candidate_count": int(candidate_count),
        "owner_fingerprint": owner_fingerprint,
        "host_inventory": host_inventory,
        "db_quiesce": db_quiesce,
        "credential_exposure": credential_exposure,
        "applier_node": applier_node,
        "verifier_node": verifier_node,
        "verifier_capture_digest": verifier_capture_digest,
        "observed_at": _iso(observed),
        "expires_at": _iso(observed + timedelta(seconds=ttl_seconds)),
    }
    _guard_no_secret(observation)
    observation["self_digest"] = artifact_self_digest(observation)
    return observation


def validate_quiesce_observation(observation: Any, *, now: str | None = None) -> list[str]:
    if not isinstance(observation, dict):
        return ["quiesce observation must be an object"]
    schema = _schema(str(OBSERVATION_SCHEMA_PATH))
    errors = [
        f"quiesce observation schema violation: {error}"
        for error in schema_subset_errors(observation, schema, schema)
    ]
    if errors:
        return errors
    if observation.get("verifier_node") == observation.get("applier_node"):
        errors.append("quiesce observation verifier_node must differ from applier_node")
    # §3/§5 不變量的模組層再驗(schema allOf 已擋大部分;此處補跨欄位語意)。
    verdict = observation.get("verdict")
    db = observation.get("db_quiesce", {})
    if verdict == "CONFIRMED_SINGLE_OWNER" and observation.get("candidate_count") != 1:
        errors.append("CONFIRMED_SINGLE_OWNER requires candidate_count == 1")
    if verdict == "STATIC_GUARDS_HELD" and not (
        db.get("advisory_lock_held") is False
        and db.get("consumer_session_status") == "STOPPED"
        and db.get("backend_present") is False
        and db.get("listen_backlog_drained") is True
    ):
        errors.append("STATIC_GUARDS_HELD requires a drained queue (lock free, no backend, session STOPPED)")
    if verdict == "RESTORED_HEALTHY" and not (
        db.get("advisory_lock_held") is True and db.get("advisory_lock_holder_count") == 1
    ):
        errors.append("RESTORED_HEALTHY requires the advisory lock re-held by exactly one backend")
    if _contains_secret_like(observation):
        errors.append("quiesce observation carries secret-like content")
    if observation.get("self_digest") != artifact_self_digest(observation):
        errors.append("quiesce observation self_digest is invalid")
    try:
        observed = _parse_time(observation["observed_at"])
        expires = _parse_time(observation["expires_at"])
        if not observed < expires:
            errors.append("quiesce observation observed_at must precede expires_at")
        if now is not None and not observed <= _parse_time(now) < expires:
            errors.append("quiesce observation is not fresh")
    except (KeyError, TypeError, ValueError):
        errors.append("quiesce observation timestamps are invalid")
    return errors


# --------------------------------------------------------------------------- #
# rollback record builder + validator (§4 stable-identity restoration crux)
# --------------------------------------------------------------------------- #
def build_quiesce_rollback(
    *,
    intent: dict[str, Any],
    pre_fence_stable_fingerprint: str,
    post_unfence_stable_fingerprint: str,
    owner_healthy: bool,
    observed_at: str,
    ttl_seconds: int = EVIDENCE_TTL_SECONDS,
) -> dict[str, Any]:
    """Build one canonical ``quiesce_rollback_v1`` (stable-identity pre == post restoration crux)."""

    restored_exact = pre_fence_stable_fingerprint == post_unfence_stable_fingerprint
    status = "RESTORED" if (restored_exact and owner_healthy) else "NOT_RESTORED"
    observed = _parse_time(observed_at)
    rollback: dict[str, Any] = {
        "schema_version": ROLLBACK_SCHEMA_VERSION,
        "status": status,
        "intent_id": intent["intent_id"],
        "unit_name": UNIT_NAME,
        "pre_fence_owner_fingerprint": pre_fence_stable_fingerprint,
        "post_unfence_owner_fingerprint": post_unfence_stable_fingerprint,
        "unfence_operation": {"kind": "systemd_system_start", "unit": UNIT_NAME},
        "restored_exact": restored_exact,
        "owner_healthy": bool(owner_healthy),
        "observed_at": _iso(observed),
        "expires_at": _iso(observed + timedelta(seconds=ttl_seconds)),
    }
    _guard_no_secret(rollback)
    rollback["self_digest"] = artifact_self_digest(rollback)
    return rollback


def validate_quiesce_rollback(rollback: Any, *, now: str | None = None) -> list[str]:
    if not isinstance(rollback, dict):
        return ["quiesce rollback must be an object"]
    schema = _schema(str(ROLLBACK_SCHEMA_PATH))
    errors = [
        f"quiesce rollback schema violation: {error}"
        for error in schema_subset_errors(rollback, schema, schema)
    ]
    if errors:
        return errors
    exact = rollback.get("pre_fence_owner_fingerprint") == rollback.get("post_unfence_owner_fingerprint")
    if rollback.get("status") == "RESTORED":
        if not exact:
            errors.append("RESTORED requires the stable-identity pre == post fingerprint")
        if rollback.get("restored_exact") is not True or rollback.get("owner_healthy") is not True:
            errors.append("RESTORED requires restored_exact and owner_healthy to be true")
    else:
        if exact and rollback.get("owner_healthy") is True:
            errors.append("NOT_RESTORED contradicts an exact + healthy restoration")
    if rollback.get("self_digest") != artifact_self_digest(rollback):
        errors.append("quiesce rollback self_digest is invalid")
    try:
        observed = _parse_time(rollback["observed_at"])
        expires = _parse_time(rollback["expires_at"])
        if not observed < expires:
            errors.append("quiesce rollback observed_at must precede expires_at")
        if now is not None and not observed <= _parse_time(now) < expires:
            errors.append("quiesce rollback is not fresh")
    except (KeyError, TypeError, ValueError):
        errors.append("quiesce rollback timestamps are invalid")
    return errors


# --------------------------------------------------------------------------- #
# result builder + validator (+ the fail-closed pending result)
# --------------------------------------------------------------------------- #
def _base_result(intent: dict[str, Any], *, apply_actor_node: str) -> dict[str, Any]:
    window = intent["observation_window"]
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "adapter_id": ADAPTER_ID,
        "intent_id": intent["intent_id"],
        "intent_digest": intent["self_digest"],
        "target_class": intent["target_class"],
        "target_host": intent["target_host"],
        "unit_name": intent["unit_name"],
        "apply_actor_node": apply_actor_node,
        "independent_verifier_node": intent["postcheck_node_id"],
        "source_head": intent["source_head"],
        # FIX-W3-1(d):把綁定 intent 的觀察窗投影進 result,讓中央閘離線再驗 window adequacy(擋 forged/underspecified QUIESCED)。
        "observation_window": {
            "duration_seconds": int(window["duration_seconds"]),
            "min_samples": int(window["min_samples"]),
            "sample_interval_seconds": int(window["sample_interval_seconds"]),
        },
        "boundary": {
            "production_fence_performed": False,
            "production_running_attested": False,
            "live_alr_owner_fenced": False,
            "nine_authorities_false": True,
        },
    }


def build_pending_result(
    intent: dict[str, Any],
    *,
    reason: str,
    now: str,
    apply_actor_node: str | None = None,
    ttl_seconds: int = EVIDENCE_TTL_SECONDS,
) -> dict[str, Any]:
    """Build the typed ``EXTERNAL_VERIFICATION_PENDING`` result — never a fake success, never a kill."""

    result = _base_result(intent, apply_actor_node=apply_actor_node or intent["applier_node_id"])
    result.update({
        "status": "EXTERNAL_VERIFICATION_PENDING",
        "owner_fingerprint": None,
        "pre_fence_observation": None,
        "window_samples": [],
        "post_unfence_observation": None,
        "rollback_record": None,
        "operator_authorization": None,
        "operator_signature_pem": None,
        "evidence_class": "STRUCTURAL_ONLY",
        "started_at": _iso(_parse_time(now)),
        "completed_at": _iso(_parse_time(now)),
        "evidence_expires_at": _plus_seconds(now, ttl_seconds),
        "ttl_seconds": ttl_seconds,
        "failure_reason": reason,
    })
    _guard_no_secret(result)
    result["self_digest"] = artifact_self_digest(result)
    return result


def build_quiesce_fence_result(
    *,
    intent: dict[str, Any],
    status: str,
    owner_fingerprint: str | None,
    pre_fence_observation: dict[str, Any] | None,
    window_samples: list[dict[str, Any]],
    post_unfence_observation: dict[str, Any] | None,
    rollback_record: dict[str, Any] | None,
    operator_authorization: dict[str, Any],
    operator_signature: bytes,
    apply_actor_node: str,
    started_at: str,
    completed_at: str,
    evidence_class: str = "STRUCTURAL_ONLY",
    failure_reason: str | None = None,
    ttl_seconds: int = EVIDENCE_TTL_SECONDS,
) -> dict[str, Any]:
    """Build a canonical ``quiesce_result_v1`` for a disposable simulated-owner apply lane."""

    if status not in APPLIED_LANE_STATUSES:
        raise QuiesceFenceError(f"unrecognized applied-lane result status: {status!r}")
    if intent.get("target_class") != DISPOSABLE_TARGET_CLASS:
        raise QuiesceFenceError("an applied-lane result is only emitted for a disposable_local target")
    if status == "QUIESCED_STATIC_GUARDS_HELD":
        if evidence_class != "LOCAL_REPRODUCIBLE":
            raise QuiesceFenceError("QUIESCED_STATIC_GUARDS_HELD requires LOCAL_REPRODUCIBLE evidence")
        if not (isinstance(pre_fence_observation, dict) and isinstance(post_unfence_observation, dict)
                and isinstance(rollback_record, dict) and window_samples):
            raise QuiesceFenceError("QUIESCED_STATIC_GUARDS_HELD requires pre/window/post observations + rollback")
    result = _base_result(intent, apply_actor_node=apply_actor_node)
    completed = _parse_time(completed_at)
    result.update({
        "status": status,
        "owner_fingerprint": owner_fingerprint,
        "pre_fence_observation": pre_fence_observation,
        "window_samples": list(window_samples),
        "post_unfence_observation": post_unfence_observation,
        "rollback_record": rollback_record,
        "operator_authorization": operator_authorization,
        "operator_signature_pem": bytes(operator_signature).decode("ascii"),
        "evidence_class": evidence_class,
        "started_at": _iso(_parse_time(started_at)),
        "completed_at": _iso(completed),
        "evidence_expires_at": _iso(completed + timedelta(seconds=ttl_seconds)),
        "ttl_seconds": ttl_seconds,
        "failure_reason": None if status == "QUIESCED_STATIC_GUARDS_HELD" else (
            failure_reason or "quiesce cycle did not complete a confirmed -> fenced -> held -> restored path"
        ),
    })
    _guard_operator_signature_pem_body(result.get("operator_signature_pem"))
    _guard_no_secret(_result_secret_scan_view(result))
    result["self_digest"] = artifact_self_digest(result)
    return result


def _validate_embedded_observation(
    observation: Any, *, phase: str, allowed_verdicts: frozenset[str], now: str | None, label: str
) -> list[str]:
    errors = validate_quiesce_observation(observation, now=now)
    if errors:
        return [f"{label}: {error}" for error in errors]
    if not isinstance(observation, dict):
        return [f"{label}: must be an object"]
    if observation.get("phase") != phase:
        errors.append(f"{label} phase must be {phase}")
    if observation.get("verdict") not in allowed_verdicts:
        errors.append(f"{label} verdict is not admissible for {phase}")
    return errors


def _observation_span_seconds(samples: list[dict[str, Any]]) -> float:
    # 樣本 observed_at 的 max-min 秒數(不可解析 / 空 → -1;供 FIX-W3-1d 跨度再驗)。
    try:
        times = [_parse_time(s["observed_at"]) for s in samples if isinstance(s, dict)]
    except (KeyError, TypeError, ValueError):
        return -1.0
    return (max(times) - min(times)).total_seconds() if times else -1.0


def validate_quiesce_fence_result(result: Any, *, now: str | None = None) -> list[str]:
    if not isinstance(result, dict):
        return ["quiesce result must be an object"]
    schema = _schema(str(RESULT_SCHEMA_PATH))
    errors = [
        f"quiesce result schema violation: {error}"
        for error in schema_subset_errors(result, schema, schema)
    ]
    if errors:
        return errors
    status = result.get("status")
    if result.get("apply_actor_node") == result.get("independent_verifier_node"):
        errors.append("quiesce result apply actor must differ from the independent verifier")
    boundary = result.get("boundary", {})
    if (
        boundary.get("nine_authorities_false") is not True
        or boundary.get("production_fence_performed") is not False
        or boundary.get("live_alr_owner_fenced") is not False
    ):
        errors.append("quiesce result boundary must keep production/live fence off and nine authorities false")

    pre = result.get("pre_fence_observation")
    window = result.get("window_samples") or []
    post = result.get("post_unfence_observation")
    rollback = result.get("rollback_record")

    if status == "EXTERNAL_VERIFICATION_PENDING":
        if pre is not None or post is not None or rollback is not None or window:
            errors.append("EXTERNAL_VERIFICATION_PENDING must not embed observations or a rollback record")
        if not (isinstance(result.get("failure_reason"), str) and result.get("failure_reason")):
            errors.append("EXTERNAL_VERIFICATION_PENDING requires a failure_reason")
    else:
        # 已進入 inventory 的路徑一律帶一份 pre-fence observation + 一份精確 intent 綁定的 operator authorization。
        errors.extend(operator_authorization_binding_errors(
            result.get("operator_authorization"),
            intent_id=result.get("intent_id"),
            intent_digest=result.get("intent_digest"),
            source_head=result.get("source_head"),
        ))
        if status in {"STALE_OWNER_FAIL_CLOSED", "AMBIGUOUS_OWNER_REFUSED"}:
            expected = "STALE_OWNER" if status == "STALE_OWNER_FAIL_CLOSED" else "AMBIGUOUS_MULTIPLE_OWNERS"
            errors.extend(_validate_embedded_observation(
                pre, phase="PRE_FENCE_INVENTORY", allowed_verdicts=frozenset({expected}), now=now,
                label="pre_fence_observation",
            ))
            if window or post is not None or rollback is not None:
                errors.append(f"{status} must not fence: window/post/rollback must be empty")
        elif status in {"QUIESCED_STATIC_GUARDS_HELD", "OBSERVATION_WINDOW_VIOLATED", "NOT_RESTORED"}:
            errors.extend(_validate_embedded_observation(
                pre, phase="PRE_FENCE_INVENTORY", allowed_verdicts=frozenset({"CONFIRMED_SINGLE_OWNER"}),
                now=now, label="pre_fence_observation",
            ))
            if not window:
                errors.append(f"{status} requires at least one in-window sample")
            for index, sample in enumerate(window):
                errors.extend(_validate_embedded_observation(
                    sample, phase="IN_WINDOW_STATIC_GUARD",
                    allowed_verdicts=frozenset({"STATIC_GUARDS_HELD", "RESTART_DETECTED", "QUEUE_NOT_DRAINED"}),
                    now=now, label=f"window_samples[{index}]",
                ))
            errors.extend(_validate_embedded_observation(
                post, phase="POST_UNFENCE_RESTORATION",
                allowed_verdicts=frozenset({"RESTORED_HEALTHY", "NOT_RESTORED"}), now=now,
                label="post_unfence_observation",
            ))
            errors.extend(validate_quiesce_rollback(rollback, now=now))
            held = [s for s in window if isinstance(s, dict) and s.get("verdict") == "STATIC_GUARDS_HELD"]
            if status == "QUIESCED_STATIC_GUARDS_HELD":
                if len(held) != len(window):
                    errors.append("QUIESCED_STATIC_GUARDS_HELD requires every in-window sample to hold")
                # FIX-W3-1(d):window adequacy 再驗——in-window 樣本數 >= min_samples 且跨度 >= duration_seconds(擋 forged/underspecified QUIESCED)。
                ow = result.get("observation_window") if isinstance(result.get("observation_window"), dict) else {}
                in_window = [s for s in window if isinstance(s, dict) and s.get("phase") == "IN_WINDOW_STATIC_GUARD"]
                min_samples = ow.get("min_samples")
                duration = ow.get("duration_seconds")
                if isinstance(min_samples, int) and len(in_window) < min_samples:
                    errors.append("QUIESCED_STATIC_GUARDS_HELD in-window sample count is below the window min_samples")
                if isinstance(duration, int) and _observation_span_seconds(in_window) < duration:
                    errors.append("QUIESCED_STATIC_GUARDS_HELD in-window sample span is below the window duration_seconds")
                if isinstance(post, dict) and post.get("verdict") != "RESTORED_HEALTHY":
                    errors.append("QUIESCED_STATIC_GUARDS_HELD requires a RESTORED_HEALTHY post-unfence observation")
                if isinstance(rollback, dict) and rollback.get("status") != "RESTORED":
                    errors.append("QUIESCED_STATIC_GUARDS_HELD requires a RESTORED rollback record")
                if isinstance(pre, dict) and result.get("owner_fingerprint") != pre.get("owner_fingerprint"):
                    errors.append("QUIESCED_STATIC_GUARDS_HELD owner_fingerprint must bind the pre-fence owner")
                if result.get("evidence_class") != "LOCAL_REPRODUCIBLE" or result.get("target_class") != DISPOSABLE_TARGET_CLASS:
                    errors.append("QUIESCED_STATIC_GUARDS_HELD requires a LOCAL_REPRODUCIBLE disposable proof")
            elif status == "OBSERVATION_WINDOW_VIOLATED":
                if not any(isinstance(s, dict) and s.get("verdict") != "STATIC_GUARDS_HELD" for s in window):
                    errors.append("OBSERVATION_WINDOW_VIOLATED requires at least one non-held in-window sample")
            elif status == "NOT_RESTORED":
                if isinstance(rollback, dict) and rollback.get("status") != "NOT_RESTORED":
                    errors.append("NOT_RESTORED requires a NOT_RESTORED rollback record")
                if isinstance(post, dict) and post.get("verdict") != "NOT_RESTORED":
                    errors.append("NOT_RESTORED requires a NOT_RESTORED post-unfence observation")
        elif status == "FAILED":
            # FAILED(已 fenced+finally 已嘗試 un-fence,FIX-W3-1a/c):必帶 honest failure_reason,pre 若在場則再驗;
            # window/post/rollback 由外層 self_digest+secret 掃描兜底整合性。
            if not (isinstance(result.get("failure_reason"), str) and result.get("failure_reason")):
                errors.append("FAILED requires a failure_reason")
            if pre is not None:
                errors.extend(_validate_embedded_observation(
                    pre, phase="PRE_FENCE_INVENTORY",
                    allowed_verdicts=frozenset({"CONFIRMED_SINGLE_OWNER"}), now=now, label="pre_fence_observation",
                ))

    # operator_signature_pem 的 strict-base64 body 護欄:對任何非 None 字串**無條件**生效(不限 status)。
    signature_pem = result.get("operator_signature_pem")
    if isinstance(signature_pem, str) and not _operator_signature_pem_body_is_strict_base64(signature_pem):
        errors.append("operator_signature_pem body is not strict base64 (possible non-signature payload)")
    if _contains_secret_like(_result_secret_scan_view(result)):
        errors.append("quiesce result carries secret-like content")
    if result.get("self_digest") != artifact_self_digest(result):
        errors.append("quiesce result self_digest is invalid")
    try:
        started = _parse_time(result["started_at"])
        expires = _parse_time(result["evidence_expires_at"])
        if not started <= expires:
            errors.append("quiesce result started_at must precede evidence_expires_at")
        if now is not None and not started <= _parse_time(now) < expires:
            errors.append("quiesce result evidence is not fresh")
    except (KeyError, TypeError, ValueError):
        errors.append("quiesce result timestamps are invalid")
    return errors


# --------------------------------------------------------------------------- #
# the applier (production/live fence stays fail-closed until S2.0@EFFECT_DONE + SSHSIG)
# --------------------------------------------------------------------------- #
def apply_quiesce_fence(
    intent: Any,
    operator_authorization: Any = None,
    signature: Any = None,
    *,
    now: str,
    source_head: str,
    host_probe: Any = None,
    fence_ops: Any = None,
    db_observer: Any = None,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    verifier_capture_digest: str | None = None,
    apply_actor_node: str | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
    runtime_digest_resolver: Callable[[Any, dict[str, str]], str | None] | None = None,
) -> dict[str, Any]:
    """Intent-derived quiesce-fence applier — the production/live fence stays fail-closed.

    Returns a typed ``quiesce_result_v1``.  Without a VALID operator SSHSIG over the exact intent +
    source_head it returns ``EXTERNAL_VERIFICATION_PENDING`` (NEVER a success, NEVER a kill).  A
    ``production`` target — OR any absent injected probe/fence/observer — ALSO returns
    ``EXTERNAL_VERIFICATION_PENDING`` in this WP3 source lane: the real ``/proc``/``systemctl`` reads and
    the real system-level ``systemctl stop/start`` are the S2.1 EFFECT session (sequenced after S2.4 installs +
    S2.5 starts the unit).  For a ``disposable_local`` target with a valid SSHSIG and injected
    simulated-owner probes it runs the REAL (simulated) confirm -> fence -> static-guard window ->
    un-fence cycle against a throwaway advisory lock observed AS the S2.0 read-only observer.
    """

    structural_errors = validate_quiesce_fence_intent(intent)
    if structural_errors:
        raise QuiesceFenceError("quiesce intent is inadmissible: " + "; ".join(structural_errors[:3]))
    if not HEAD_RE.fullmatch(str(source_head)) or intent.get("source_head") != source_head:
        raise QuiesceFenceError("source_head must be a 40-hex id equal to the intent source head")
    apply_actor_node = apply_actor_node or intent["applier_node_id"]
    started_at = started_at or now
    completed_at = completed_at or now
    # 結構有效但落在當前有效窗之外(expired / not-yet-valid)→ 依 PENDING 合約 fail-closed(非 raise);
    # governance 供給的 now 若 malformed(無法 parse)→ 比照 malformed-intent 硬合約轉 typed 錯誤(不逸出裸 ValueError)。
    try:
        if validate_quiesce_fence_intent(intent, now=now):
            return build_pending_result(
                intent,
                reason="quiesce intent is outside its current validity window (expired or not-yet-valid)",
                now=now, apply_actor_node=apply_actor_node,
            )
    except ValueError as exc:
        raise QuiesceFenceError(f"quiesce now is malformed: {now!r}") from exc

    valid, reason = _operator_authorization_is_valid(
        operator_authorization, signature, intent=intent, source_head=source_head, now=now
    )
    if not valid:
        return build_pending_result(intent, reason=reason, now=now, apply_actor_node=apply_actor_node)

    if (
        intent["target_class"] == PRODUCTION_TARGET_CLASS
        or host_probe is None or fence_ops is None or db_observer is None or clock is None
    ):
        # SOURCE 界線:即使已授權,WP3 也絕不接觸 live /proc/systemctl、絕不 stop/start 真 process;
        # 真 fence 屬 S2.1 EFFECT session(需 S2.0@EFFECT_DONE + operator SSHSIG,且排在 S2.4 安裝 + S2.5 起跑之後)。
        return build_pending_result(
            intent,
            reason=(
                "production quiesce fence is deferred to the S2.1 EFFECT session; it fences a live owner only "
                "after S2.0@EFFECT_DONE plus an exact operator SSHSIG, and the EFFECT fence sequences after "
                "S2.4 (unit installed) + S2.5 (running); the WP3 source lane makes no live /proc/systemctl "
                "contact and signals no process"
            ),
            now=now, apply_actor_node=apply_actor_node,
        )

    if not DIGEST_RE.fullmatch(str(verifier_capture_digest or "")):
        raise QuiesceFenceError("a disposable quiesce cycle requires the verifier's bound capture digest")
    verifier_node = intent["postcheck_node_id"]
    # F2(EFFECT 契約備註):此單一 observer cursor 被 pre/window/post 重用;EFFECT 注入的 observer 連線必 ``autocommit=True``,
    # 否則某次 mid-window read 出錯的失敗交易會 poison 後續讀取(SOURCE lane 可拋棄叢集測試已以 autocommit 連線滿足)。
    cursor = db_observer.cursor()

    pre_inventory = build_owner_inventory(
        host_probe, cursor, intent=intent, runtime_digest_resolver=runtime_digest_resolver,
    )
    pre_observation = confirm_alr_owner(
        pre_inventory, expected_fingerprint=intent["expected_owner_fingerprint"],
        applier_node=apply_actor_node, verifier_node=verifier_node,
        verifier_capture_digest=verifier_capture_digest, observed_at=started_at,
    )
    verdict = pre_observation["verdict"]

    if verdict == "STALE_OWNER":
        return build_quiesce_fence_result(
            intent=intent, status="STALE_OWNER_FAIL_CLOSED", owner_fingerprint=pre_inventory["owner_fingerprint"],
            pre_fence_observation=pre_observation, window_samples=[], post_unfence_observation=None,
            rollback_record=None, operator_authorization=operator_authorization,
            operator_signature=bytes(signature), apply_actor_node=apply_actor_node,
            started_at=started_at, completed_at=completed_at,
            failure_reason="expected owner is not cleanly present (gone / drift); no fence attempted",
        )
    if verdict == "AMBIGUOUS_MULTIPLE_OWNERS":
        return build_quiesce_fence_result(
            intent=intent, status="AMBIGUOUS_OWNER_REFUSED", owner_fingerprint=pre_inventory["owner_fingerprint"],
            pre_fence_observation=pre_observation, window_samples=[], post_unfence_observation=None,
            rollback_record=None, operator_authorization=operator_authorization,
            operator_signature=bytes(signature), apply_actor_node=apply_actor_node,
            started_at=started_at, completed_at=completed_at,
            failure_reason="multiple ownership candidates; refusing to guess (no fence attempted)",
        )

    # CONFIRMED_SINGLE_OWNER:fence 一經發起(即使 stop/window 拋錯)就必在 finally 嘗試 un-fence(FIX-W3-1a),絕不留 fenced/down。
    baseline = {"n_restarts": pre_inventory["host_inventory"]["watchdog"]["n_restarts"], "invocation_id": ""}
    fence_initiated = False
    start_ok = False
    window_samples: list[dict[str, Any]] = []
    window_status = WINDOW_STATUS_UNDERSPECIFIED
    window_error: Exception | None = None
    try:
        fence_initiated = True
        owner_scoped_fence(fence_ops)
        window_samples, window_status = collect_static_guard_window(
            host_probe, cursor, intent=intent, baseline=baseline, applier_node=apply_actor_node,
            verifier_node=verifier_node, verifier_capture_digest=verifier_capture_digest,
            clock=clock, observed_at_base=started_at, sleep=sleep,
            runtime_digest_resolver=runtime_digest_resolver,
        )
    except Exception as exc:  # noqa: BLE001 - stop/window 拋錯改走 typed FAILED,絕不逸出裸例外、絕不留 fenced
        window_error = exc
    finally:
        if fence_initiated:
            start_ok = owner_scoped_unfence(fence_ops)

    if window_error is not None:
        # 例外路徑:un-fence 已在 finally 嘗試(start_ok 已記錄);回傳 typed FAILED(非裸例外、非假成功)。
        return build_quiesce_fence_result(
            intent=intent, status="FAILED", owner_fingerprint=pre_inventory["owner_fingerprint"],
            pre_fence_observation=pre_observation, window_samples=window_samples,
            post_unfence_observation=None, rollback_record=None,
            operator_authorization=operator_authorization, operator_signature=bytes(signature),
            apply_actor_node=apply_actor_node, started_at=started_at, completed_at=completed_at,
            failure_reason=(f"quiesce static-guard window raised after fence "
                            f"({type(window_error).__name__}); un-fence attempted (start_ok={start_ok})"),
        )

    post_inventory = build_owner_inventory(
        host_probe, cursor, intent=intent, runtime_digest_resolver=runtime_digest_resolver,
    )
    # FIX-C3(Codex :1836):un-fence 後以與 pre-fence 同級的 confirm-grade 不變量復核 owner 全訊號
    # (advisory holder=aiml_engine_scanner / consumer-session OPEN / fragment/cgroup match / 唯一候選 PID==MainPID /
    # MainPID cmdline exact / 單一 backend / unit active),搭配 restart 後鑄新身分預期(新 PID/InvocationID,
    # 故以 stable-identity fingerprint 判 pre==post);任一未滿足即 NOT_RESTORED,而非把「unit 起來了」當成已還原。
    post_healthy = bool(start_ok) and _confirm_grade_signals_ok(post_inventory)
    stable_restored = (
        pre_inventory["stable_identity_fingerprint"] == post_inventory["stable_identity_fingerprint"]
    )
    restored = post_healthy and stable_restored
    post_observation = build_quiesce_observation(
        phase="POST_UNFENCE_RESTORATION",
        verdict="RESTORED_HEALTHY" if restored else "NOT_RESTORED",
        candidate_count=int(post_inventory["candidate_count"]),
        owner_fingerprint=post_inventory["owner_fingerprint"],
        host_inventory=post_inventory["host_inventory"], db_quiesce=post_inventory["db_quiesce"],
        credential_exposure=post_inventory["credential_exposure"],
        applier_node=apply_actor_node, verifier_node=verifier_node,
        verifier_capture_digest=verifier_capture_digest, observed_at=completed_at,
    )
    rollback_record = build_quiesce_rollback(
        intent=intent, pre_fence_stable_fingerprint=pre_inventory["stable_identity_fingerprint"],
        post_unfence_stable_fingerprint=post_inventory["stable_identity_fingerprint"],
        owner_healthy=post_healthy, observed_at=completed_at,
    )

    if window_status == WINDOW_STATUS_VIOLATED:
        # 帶一個真 non-held 樣本(restart supervened / queue not drained)→ OBSERVATION_WINDOW_VIOLATED。
        status = "OBSERVATION_WINDOW_VIOLATED"
        failure_reason = "a static-guard window sample was not held (a restart supervened or the queue was not drained)"
        evidence_class = "STRUCTURAL_ONLY"
    elif window_status == WINDOW_STATUS_UNDERSPECIFIED:
        # FIX-W3-1c:全 held 但窗不足 → typed FAILED(非 OBSERVATION_WINDOW_VIOLATED,後者 validator 要求 >=1 non-held 樣本)。
        status = "FAILED"
        failure_reason = (
            "static-guard window underspecified or its elapsed time exceeded the declared window deadline "
            "(too few samples / span shorter than duration / hit the spin ceiling / elapsed beyond "
            "duration_seconds plus one cadence step); not an observation-window violation"
        )
        evidence_class = "STRUCTURAL_ONLY"
    elif rollback_record["status"] == "NOT_RESTORED":
        status = "NOT_RESTORED"
        failure_reason = "un-fence did not restore the owner to a healthy stable identity"
        evidence_class = "STRUCTURAL_ONLY"
    else:
        status = "QUIESCED_STATIC_GUARDS_HELD"
        failure_reason = None
        evidence_class = "LOCAL_REPRODUCIBLE"

    return build_quiesce_fence_result(
        intent=intent, status=status, owner_fingerprint=pre_inventory["owner_fingerprint"],
        pre_fence_observation=pre_observation, window_samples=window_samples,
        post_unfence_observation=post_observation, rollback_record=rollback_record,
        operator_authorization=operator_authorization, operator_signature=bytes(signature),
        apply_actor_node=apply_actor_node, started_at=started_at, completed_at=completed_at,
        evidence_class=evidence_class, failure_reason=failure_reason,
    )


# --------------------------------------------------------------------------- #
# closure binding (source-only; NOT wired into the live dispatch; mirrors S2.0)
# --------------------------------------------------------------------------- #
def validate_quiesce_fence_binding(
    packet: dict[str, Any],
    route: dict[str, Any],
    fragments_by_node: dict[str, dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]],
    valid_receipts: dict[str, dict[str, Any]],
) -> list[str]:
    """Closure admission for one quiesce-fence effect: intent + OPS preflight + result + the embedded
    independent post-unfence observation bound to the verifier's OWN governed command_capture_v2.

    NEW-P2-B(S2E.1 更新):本謂詞**已**接入 live dispatch —— ``agent_governance_effects`` 的 S2 分派
    委派 ``agent_governance_s2_effect_binding``,後者對 ``S2_1_DRILL`` 一律先呼叫本謂詞
    (``_DELEGATED_STEP_BINDINGS``,委派不是取代),且 ``route_task`` 在 S2 effect selector 命中時已注入
    該 adapter 節點。舊註「SOURCE-only / 不接 live dispatch / 無 route 節點」自本波起為假,故改寫。
    仍為真的界線:``QUIESCED_STATIC_GUARDS_HELD`` 被 result schema 釘成 disposable_local/
    LOCAL_REPRODUCIBLE 且 boundary 無條件 production_fence_performed=false,S2 closure sibling 因此把
    S2.1 標成 ``closure_pass_blocked_reason``(今日無可 closure-PASS 的成功頂點)。本謂詞存在的理由不變:
    讓 S2.1 EFFECT session 的 closure 能核 exact 三方(result post-unfence verifier_capture_digest ==
    ops_postcheck capture digest == verifier command_capture_v2 record_digest)並要求 applier != verifier。
    """

    errors: list[str] = []
    matching = [
        (evidence_id, receipt) for evidence_id, receipt in valid_receipts.items()
        if isinstance(receipt, dict) and receipt.get("adapter_id") == ADAPTER_ID
    ]
    if len(matching) != 1:
        return ["quiesce fence closure PASS requires exactly one quiesce-fence effect receipt"]
    receipt_id, receipt = matching[0]

    effect_nodes = [
        node for node in route.get("nodes", [])
        if node.get("kind") == "effect_adapter" and node.get("mandatory")
    ]
    if not any(node.get("id") == ADAPTER_ID for node in effect_nodes):
        errors.append("quiesce fence effect receipt is not routed to the exact adapter node")
    if receipt.get("status") != "QUIESCED_STATIC_GUARDS_HELD":
        errors.append("quiesce fence closure PASS requires a QUIESCED_STATIC_GUARDS_HELD receipt")
    else:
        errors.extend(operator_authorization_binding_errors(
            receipt.get("operator_authorization"),
            intent_id=receipt.get("intent_id"),
            intent_digest=receipt.get("intent_digest"),
            source_head=receipt.get("source_head"),
        ))

    intent_source = f"{INTENT_SCHEMA_VERSION}:{receipt.get('intent_id')}"
    intent_refs = [
        ref for ref in packet.get("authority_refs", [])
        if ref.get("class") == "claim_evidence" and ref.get("source") == intent_source
    ]
    if len(intent_refs) != 1 or intent_refs[0].get("digest") != receipt.get("intent_digest"):
        errors.append("quiesce fence effect receipt lacks exact intent authority")
    if not fragments_by_node.get("ops_preflight"):
        errors.append("quiesce fence closure requires an OPS preflight fragment")

    # 內嵌的獨立 post-unfence observation:verifier != applier,且帶一個 bound verifier_capture_digest。
    post = receipt.get("post_unfence_observation") if isinstance(receipt.get("post_unfence_observation"), dict) else None
    applier_node = receipt.get("apply_actor_node")
    receipt_verifier_digest = post.get("verifier_capture_digest") if isinstance(post, dict) else None
    verifier_capture_ev: dict[str, Any] | None = None
    if post is None:
        errors.append("quiesce fence closure requires the receipt's embedded post-unfence observation")
    else:
        errors.extend(validate_quiesce_observation(post))
        if post.get("verifier_node") == applier_node:
            errors.append("quiesce fence post-unfence verifier must differ from the applier node")
        if not DIGEST_RE.fullmatch(str(receipt_verifier_digest or "")):
            errors.append("quiesce fence post-unfence observation lacks a bound verifier_capture_digest")

    fragment = fragments_by_node.get("ops_postcheck", {})
    cap_refs = [
        evidence_by_id[ref] for ref in fragment.get("evidence_refs", [])
        if ref in evidence_by_id
        and evidence_by_id[ref].get("scope") == "runtime"
        and evidence_by_id[ref].get("source") == "ops_postcheck"
        and evidence_by_id[ref].get("kind") == "command_capture_v2"
    ]
    verifier_capture_record_ok = False
    if len(cap_refs) != 1:
        errors.append("quiesce fence closure requires exactly one verifier command_capture_v2 in ops_postcheck")
    elif DIGEST_RE.fullmatch(str(receipt_verifier_digest or "")):
        verifier_capture_ev = cap_refs[0]
        outer_digest_ok = verifier_capture_ev.get("digest") == receipt_verifier_digest
        if not outer_digest_ok:
            errors.append("quiesce fence verifier capture digest is not the three-way-bound digest")
        capture = verifier_capture_ev.get("artifact")
        if not isinstance(capture, dict):
            errors.append("quiesce fence verifier command_capture_v2 artifact must be a well-formed record")
        else:
            record_digest_ok = str(capture.get("record_digest")) == str(receipt_verifier_digest)
            node_distinct = capture.get("node_id") != applier_node
            if not record_digest_ok:
                errors.append("quiesce fence verifier command_capture_v2 record_digest is not the bound digest")
            if not node_distinct:
                errors.append("quiesce fence verifier capture node must differ from the applier node")
            verifier_capture_record_ok = outer_digest_ok and record_digest_ok and node_distinct

    required_ids = {receipt_id}
    if verifier_capture_ev is not None:
        required_ids.add(verifier_capture_ev.get("id"))
    accepted = (
        post is not None and verifier_capture_record_ok
        and any(
            item.get("status") == "PASS" and required_ids.issubset(set(item.get("evidence_refs", [])))
            for item in packet.get("acceptance", [])
        )
    )
    if not accepted:
        errors.append(
            "quiesce fence passed acceptance must bind the effect receipt + verifier command capture"
        )
    return errors
