"""S2.0 production PG observer-bootstrap SOURCE Adapter (AIML WP2).

把 S1.1(唯讀身分證明)/ S1.3(最小權限契約)/ S1.5(可拋棄 role/ACL apply+rollback)接成
一條「生產唯讀 observer 角色 bootstrap」的 SOURCE seam:一張 exact typed intent、一組**結構化
allowlist**(絕非呼叫端 raw SQL)產出的最小唯讀 observer grant set、一個 applier、與一位**相異**
獨立驗證者的唯讀證明,外加精確 REVOKE/DROP rollback。這是 S2.0 的 **SOURCE_READY** 交付,不是
EFFECT_DONE:真正對生產 PG 的 apply 在有一張 exact operator SSHSIG 之前**恆 fail-closed**——回傳
一個 typed ``EXTERNAL_VERIFICATION_PENDING`` result,**永不**假成功。

**誠實界線(CLAUDE 四 / Typed Authority Matrix)。** land 時不接觸任何生產 PG/psql/network/broker。
可拋棄叢集測試(S1.1/S1.3/S1.5 同一 pattern)會真的 ``initdb`` 起一個丟棄式 cluster、真跑
``CREATE ROLE``/``GRANT``/``REVOKE``/``DROP`` 並真觀察 ``42501``/``28P01``(LOCAL_REPRODUCIBLE);
真正的生產 socket 一律 DEFERRED 給 S2.0 EFFECT session。九個 authority 恆 false;沒有任何 receipt
序列化機密(operator 私鑰既不在 Mac 也不在 trade-core;只帶非機密的 signer identity/fingerprint/
namespace 與**公開的** SSHSIG bytes)。canonical self-digest 只證完整性,不證誰執行、不證外部事實。

**Domain separation。** operator SSHSIG 沿用 S0.3/S1 既有信任根公鑰/指紋,但以**專屬 identity +
namespace**(``aiml-s2-observer-bootstrap-operator-v1`` / ``arcane-equilibrium-aiml-s2-observer-bootstrap``)
達成 domain separation:一張以 S1 target-host namespace 簽的 permit 於此因 namespace/identity 不符
被拒(反之亦然)。applier != 獨立驗證者(role/node/process/capture 皆須相異)。

stdlib-first;``psycopg2`` 只在可拋棄叢集路徑延遲匯入。唯讀消費 S1.1(``_pg_ident`` 等)/S1.3
(最小權限常量、憑證拒絕碼、``resolve_credential_denial_sqlstate``)/S1.5(``pg_role_acl_state_digest``);
中央 validator 加性委派這四個 typed schema,**不注入** live ``route_task`` effect 節點或 closure
effect 綁定(那要 S2.0 EFFECT session)。
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

# 唯讀消費:S1.5 的 PG 識別碼引號 + role/ACL catalog 投影;S1.3 的最小權限常量/憑證拒絕碼;
# S1 target-host 的 SSHSIG 信任根與驗證基元;中央 validator 的 canonical_digest / artifact_self_digest。
import agent_governance_component_effects as ce  # noqa: E402
import agent_governance_identity_acl_contract as acl  # noqa: E402
import agent_governance_aiml_trusted_host as trusted  # noqa: E402
import aiml_gate_receipt_validator as central_validator  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402


ADAPTER_ID = "pg_observer_bootstrap_adapter_v1"
OWNER_SESSION = "S2.0"

INTENT_SCHEMA_VERSION = "pg_observer_bootstrap_intent_v1"
RESULT_SCHEMA_VERSION = "pg_observer_bootstrap_result_v1"
POSTCHECK_SCHEMA_VERSION = "pg_observer_bootstrap_postcheck_v1"
ROLLBACK_SCHEMA_VERSION = "pg_observer_bootstrap_rollback_v1"

SCHEMA_DIR = ML_TRAINING_DIR / "schemas" / "aiml_gate_receipts"
INTENT_SCHEMA_PATH = SCHEMA_DIR / f"{INTENT_SCHEMA_VERSION}.schema.json"
RESULT_SCHEMA_PATH = SCHEMA_DIR / f"{RESULT_SCHEMA_VERSION}.schema.json"
POSTCHECK_SCHEMA_PATH = SCHEMA_DIR / f"{POSTCHECK_SCHEMA_VERSION}.schema.json"
ROLLBACK_SCHEMA_PATH = SCHEMA_DIR / f"{ROLLBACK_SCHEMA_VERSION}.schema.json"

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
SQLSTATE_RE = re.compile(r"^[0-9A-Z]{5}$")

TARGET_CLASSES = frozenset({"disposable_local", "production"})
DISPOSABLE_TARGET_CLASS = "disposable_local"
PRODUCTION_TARGET_CLASS = "production"
EVIDENCE_CLASSES = frozenset({"LOCAL_REPRODUCIBLE", "STRUCTURAL_ONLY"})
RESULT_STATUSES = frozenset({
    "APPLIED_ROLLED_BACK_EXACT",
    "ROLLED_BACK_INTERRUPTED",
    "NOT_RESTORED_FAILED",
    "EXTERNAL_VERIFICATION_PENDING",
    "FAILED",
})
TTL_CEILING_SECONDS = 3600
EVIDENCE_TTL_SECONDS = 900

# 唯一可選的結構化 grant set(enum key,非 raw SQL);任何更寬的 selector 一律 fail-closed。
OBSERVER_GRANT_SET_SELECTOR = "observer_read_only_v1"
# observer 走 peer/ident 本地認證,絕不吃密碼(no password ingress);scram/loopback 密碼型一律拒。
OBSERVER_AUTH_METHODS = frozenset({"pg_hba_ident_local", "pg_hba_peer_local"})
# CREATE ROLE 顯式全禁用屬性:所有 S1.3 FORBIDDEN_ROLE_ATTRS 對應的 NO* 皆在,且 NOLOGIN。
_ROLE_ATTRIBUTE_CLAUSE = (
    "NOLOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB NOREPLICATION NOBYPASSRLS"
)
# 連線層釘死唯讀交易 + pg_catalog search_path(session 內重設對 schema-qualified 查詢無害)。
CONNECTION_OPTIONS = "-c default_transaction_read_only=on -c search_path=pg_catalog"
# 任一鍵出現在 intent 即代表呼叫端試圖夾帶 raw SQL / 授權升級 / 寫入權 / 成員資格 → fail-closed。
FORBIDDEN_INTENT_KEYS = frozenset({
    "raw_sql", "sql", "statements", "privileges", "extra_privileges",
    "with_grant_option", "grant_option", "role_membership", "member_of",
    "grantor", "writer", "writer_role", "superuser", "is_superuser",
    "login", "password", "migration", "alter_system",
})
# 觀察端寫入拒絕碼(42501)、憑證升級拒絕碼(28P01/28000)——重用 S1.3 常量(EXERCISED,非僅 import)。
WRITE_DENIAL_SQLSTATES = acl.READER_WRITE_DENIAL_SQLSTATES  # {"42501"}
CREDENTIAL_DENIAL_SQLSTATES = acl.CREDENTIAL_DENIAL_SQLSTATES  # {"28P01","28000"}
# SET ROLE 升級拒絕同屬 insufficient_privilege(42501)。
SET_ROLE_DENIAL_SQLSTATES = frozenset({"42501", "0LP01", "42P01"})
# uid/role label 不得命名的特權身分 token(鏡像 S1.3 ``_PRIVILEGED_IDENTITY_TOKENS``)。
_PRIVILEGED_IDENTITY_TOKENS = ("root", "superuser", "sudo", "wheel", "admin")

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

# 機密掃描(沿用 S1.1/S1.3/S1.5 樣態:github token / credential 賦值 / auth header / postgres DSN 憑證形)。
SECRET_LIKE_RE = re.compile(
    r"(?:github_pat_|gh[pousr]_[A-Za-z0-9]{12,})"
    r"|(?:access[_-]?token|auth(?:orization)?|client[_-]?secret|password|"
    r"pgpassword|private[_-]?key)\s*[:=]"
    r"|(?:basic|bearer)\s+[A-Za-z0-9._~+/=-]{12,}"
    r"|postgres(?:ql)?://[^\s:/@]+:[^\s:/@]+@",
    re.IGNORECASE,
)
SECRET_PATTERNS_CHECKED = (
    "auth_scheme_token", "credential_assignment", "github_token", "postgres_dsn_credentials",
)


class PgObserverBootstrapError(RuntimeError):
    """Base for a would-be observer artifact that cannot be safely emitted (fail-closed)."""


class SecretLeakageError(PgObserverBootstrapError):
    """Raised when a would-be artifact field carries secret-like content."""


class PgObserverReadOnlyError(PgObserverBootstrapError):
    """Raised when a negative probe did not observe its required denial (not truly read-only)."""


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


def _plus_seconds(iso: str, seconds: int) -> str:
    return (_parse_time(iso) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def intent_self_digest(intent: dict[str, Any]) -> str:
    return canonical_digest({k: v for k, v in intent.items() if k != "self_digest"})


def authorization_digest(value: dict[str, Any]) -> str:
    return canonical_digest({k: v for k, v in value.items() if k != "authorization_digest"})


# --------------------------------------------------------------------------- #
# secret scan (fail-closed)
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
        raise SecretLeakageError("observer-bootstrap payload carries secret-like content")


def _result_secret_scan_view(result: dict[str, Any]) -> dict[str, Any]:
    # operator_signature_pem 是**公開的** SSHSIG(非機密):其 base64 body 理論上可能以 "auth=" padding
    # 收尾而誤觸 secret 正則。它是受控欄位(來自 operator 簽章 bytes),故 build 與 validate 一致地
    # 把它排除在 secret 掃描之外,避免對合法 receipt 造成 flaky false-positive 拒絕。
    # FIX-7(E2 P3):result schema 對 operator_signature_pem 釘死完整 SSHSIG armor pattern
    # (header+body+END footer);DSN 子形(含 ':'/'@' 等非 body-charset 字元)在 schema 階段即被 pattern 拒。
    # FIX-10(E2 P2 更正):**僅** armor pattern 不足以令此排除安全——其 body charset [A-Za-z0-9+/=\n] 仍
    # 允許可讀 plaintext(如 "password=hunter2"/"pgpassword=…"/"bearer …"),而這些正是 SECRET_LIKE_RE 認得、
    # 卻因本排除而不被掃到的形。故 build 與 validate 皆額外要求 operator_signature_pem 的 armor body 必為
    # 嚴格標準 base64(見 _operator_signature_pem_body_is_strict_base64);FIX-11(E2 P2 根因)更把 validate
    # 側此檢查移出 APPLIED 分支、對任何非 None 字串**無條件**生效(不再僅限 APPLIED;build 兩條路徑本就以
    # _guard_operator_signature_pem_body 對稱把關)。嚴格 base64 一旦成立,所有可讀 plaintext 機密形
    # (credential_assignment / auth_scheme_token / DSN)在結構上皆不可能搭載
    # ——唯一能搭載的是 base64-**編碼**後的 bytes(非可讀 plaintext,落在既有離線捏造邊界內,非 plaintext
    # 序列化通道),故此 secret-scan 排除**可證安全**,絕非放行機密的破口。
    return {k: v for k, v in result.items() if k != "operator_signature_pem"}


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


def _names_privileged_identity(label: Any) -> bool:
    # 鏡像 S1.3:label 命名 root/superuser/sudo/wheel/admin 一律視為特權身分(即使宣稱 NOLOGIN)。
    if not isinstance(label, str):
        return False
    lowered = label.lower()
    return any(token in lowered for token in _PRIVILEGED_IDENTITY_TOKENS)


def _safe_ident(name: Any) -> str:
    # 重用 S1.5 ``_pg_ident`` 白名單(^[a-z_][a-z0-9_]*$),把 ComponentEffectError 轉為本模組錯誤。
    try:
        return ce._pg_ident(name)
    except ce.ComponentEffectError as exc:  # noqa: PERF203
        raise PgObserverBootstrapError(f"unsafe SQL identifier: {name!r}") from exc


# --------------------------------------------------------------------------- #
# structured grant-set allowlist (enum-selected; NEVER caller raw SQL)
# --------------------------------------------------------------------------- #
def generate_observer_grant_sql(intent: Any) -> dict[str, Any]:
    """Project ONE exact minimal read-only observer grant set from a STRUCTURED intent.

    Fail-closed by construction: the only admissible ``grant_set_selector`` is
    ``observer_read_only_v1``; identifiers pass the S1.5 ``_pg_ident`` allowlist;
    the role/schema/relation labels must not name a privileged identity; auth is
    peer/ident local (no password ingress).  Any caller raw SQL, migration,
    writer/superuser role, role membership, ``WITH GRANT OPTION`` or other
    over-grant marker key is REJECTED (raises).  The returned SQL is exactly:
    ``CREATE ROLE <obs> NOLOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB NOREPLICATION
    NOBYPASSRLS`` + ``GRANT USAGE ON SCHEMA <observed>`` + ``GRANT SELECT`` on
    exactly the observed relations, with the connection pinned read-only /
    pg_catalog.
    """

    if not isinstance(intent, dict):
        raise PgObserverBootstrapError("observer intent must be an object")
    if intent.get("grant_set_selector") != OBSERVER_GRANT_SET_SELECTOR:
        raise PgObserverBootstrapError(
            f"grant_set_selector must be {OBSERVER_GRANT_SET_SELECTOR!r}; "
            "no broader / caller-defined grant set is admissible"
        )
    forbidden = sorted(FORBIDDEN_INTENT_KEYS & set(intent))
    if forbidden:
        raise PgObserverBootstrapError(
            "observer intent carries forbidden over-grant / raw-SQL keys: " + ", ".join(forbidden)
        )
    if intent.get("auth_mapping") not in OBSERVER_AUTH_METHODS:
        raise PgObserverBootstrapError(
            "observer auth_mapping must be peer/ident local "
            f"(one of {sorted(OBSERVER_AUTH_METHODS)}); no password ingress"
        )
    role = intent.get("observer_role")
    schema = intent.get("observed_schema")
    relations = intent.get("observed_relations")
    if not isinstance(relations, list) or not relations:
        raise PgObserverBootstrapError("observer intent must observe at least one relation")
    for label in (role, schema, *relations):
        _safe_ident(label)
        if _names_privileged_identity(label):
            raise PgObserverBootstrapError(f"observer identifier names a privileged identity: {label!r}")

    role_q = _safe_ident(role)
    schema_q = _safe_ident(schema)
    grant_select = [
        f"GRANT SELECT ON {schema_q}.{_safe_ident(rel)} TO {role_q}" for rel in relations
    ]
    revoke = [f"REVOKE ALL ON {schema_q}.{_safe_ident(rel)} FROM {role_q}" for rel in relations]
    revoke.append(f"REVOKE ALL ON SCHEMA {schema_q} FROM {role_q}")
    grant_set = {
        "grant_set_selector": OBSERVER_GRANT_SET_SELECTOR,
        "role": role,
        "schema": schema,
        "relations": list(relations),
        "auth_mapping": intent.get("auth_mapping"),
        "create_role": f"CREATE ROLE {role_q} {_ROLE_ATTRIBUTE_CLAUSE}",
        "grant_usage": f"GRANT USAGE ON SCHEMA {schema_q} TO {role_q}",
        "grant_select": grant_select,
        "revoke": revoke,
        "drop_role": f"DROP ROLE IF EXISTS {role_q}",
        "connection_options": CONNECTION_OPTIONS,
    }
    _guard_no_secret(grant_set)
    return grant_set


def grant_set_digest(grant_set: dict[str, Any]) -> str:
    return canonical_digest(grant_set)


# --------------------------------------------------------------------------- #
# real structured SQL operators (disposable cluster; reuse S1.5 _pg_ident/state_digest)
# --------------------------------------------------------------------------- #
def observer_role_acl_state_digest(cursor: Any, *, role: str, schema: str, relations: list[str]) -> str:
    """Digest the observer role + its per-relation grant catalog projection.

    Reuses S1.5 ``pg_role_acl_state_digest`` per relation (a real catalog read); an
    absent role yields a stable "absent" projection, so pre(absent) != applied(present)
    and post(absent after rollback) == pre.
    """

    per_relation = {
        rel: ce.pg_role_acl_state_digest(cursor, role=role, schema=schema, table=rel)
        for rel in sorted(relations)
    }
    return canonical_digest({"role": role, "schema": schema, "relations": per_relation})


def observer_bootstrap_apply(
    cursor: Any, *, grant_set: dict[str, Any], on_step: Callable[[str], None] | None = None
) -> None:
    """Real CREATE ROLE (all forbidden attrs absent) + GRANT USAGE + GRANT SELECT apply.

    ``on_step`` is a test-only hook (mirrors S1.5's fail-closed toggles): it is called
    after each committed step so a disposable test can inject a mid-apply failure and
    prove the rollback restores pre == post.
    """

    cursor.execute(grant_set["create_role"])
    if on_step is not None:
        on_step("create_role")
    cursor.execute(grant_set["grant_usage"])
    if on_step is not None:
        on_step("grant_usage")
    for index, statement in enumerate(grant_set["grant_select"]):
        cursor.execute(statement)
        if on_step is not None:
            on_step(f"grant_select:{index}")


def observer_role_present(cursor: Any, *, role: str) -> bool:
    """Real catalog read: does the observer role already exist in ``pg_roles``?"""

    cursor.execute("SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = %s", (role,))
    return cursor.fetchone() is not None


def observer_bootstrap_rollback(cursor: Any, *, grant_set: dict[str, Any]) -> None:
    """Real REVOKE ALL + DROP ROLE rollback; partial-failure safe (role-existence guarded)."""

    if not observer_role_present(cursor, role=grant_set["role"]):
        return  # CREATE ROLE never committed; nothing to roll back
    for statement in grant_set["revoke"]:
        cursor.execute(statement)
    cursor.execute(grant_set["drop_role"])


# --------------------------------------------------------------------------- #
# read-only denial probes (distinct verifier connects AS the observer)
# --------------------------------------------------------------------------- #
def _rollback_quietly(cursor: Any) -> None:
    connection = getattr(cursor, "connection", None)
    if connection is not None:
        try:
            connection.rollback()
        except Exception:  # pragma: no cover - best effort  # noqa: BLE001
            pass


def _observe_denial(cursor: Any, sql: str) -> str:
    # 執行預期會被拒絕的敘述;回傳觀察到的 SQLSTATE,未被拒即致命(refuse)。
    try:
        cursor.execute(sql)
    except Exception as exc:  # noqa: BLE001 - psycopg2.Error carries pgcode
        pgcode = getattr(exc, "pgcode", None)
        _rollback_quietly(cursor)
        if pgcode is None:
            raise
        return str(pgcode)
    _rollback_quietly(cursor)
    raise PgObserverReadOnlyError(f"expected denial but statement succeeded: {sql}")


def probe_observer_write_denied(cursor: Any, *, schema: str, relation: str) -> dict[str, Any]:
    """Attempt a write as the observer; require an insufficient-privilege denial (42501)."""

    attempted = f"DELETE FROM {_safe_ident(schema)}.{_safe_ident(relation)}"
    return {"attempted": attempted, "observed_sqlstate": _observe_denial(cursor, attempted), "verdict": "DENIED"}


def probe_observer_set_role_denied(cursor: Any, *, target_role: str) -> dict[str, Any]:
    """Attempt SET ROLE to a writer/superuser; require an escalation denial (42501)."""

    attempted = f"SET ROLE {_safe_ident(target_role)}"
    return {"attempted": attempted, "observed_sqlstate": _observe_denial(cursor, attempted), "verdict": "DENIED"}


def probe_observer_search_path_reset_harmless(
    cursor: Any, *, schema: str, relation: str
) -> dict[str, Any]:
    """Reset the session search_path (allowed, harmless) and confirm a qualified read still works.

    Unlike a persistent hijack, a session-local ``SET search_path`` is harmless: every
    allowlisted read is schema-qualified, so the observer cannot escalate by moving the
    search_path.  Records the effective search_path after the reset as evidence.
    """

    cursor.execute("SET search_path TO public")
    cursor.execute(f"SELECT 1 FROM {_safe_ident(schema)}.{_safe_ident(relation)} LIMIT 1")
    cursor.fetchall()
    cursor.execute("SELECT current_setting('search_path')")
    effective = cursor.fetchone()[0]
    return {
        "attempted": "SET search_path TO public",
        "effective_search_path": str(effective),
        "harmless": True,
        "queries_schema_qualified": True,
    }


def probe_credential_escalation_denied(
    connect_with_bad_credential: Callable[[], Any],
    *,
    attempted: str = "connect_with_escalated_credential",
) -> dict[str, Any]:
    """Attempt a connection with an escalated/invalid credential; require 28P01/28000."""

    try:
        connection = connect_with_bad_credential()
    except Exception as exc:  # noqa: BLE001 - any driver error is the denial
        sqlstate = acl.resolve_credential_denial_sqlstate(getattr(exc, "pgcode", None), str(exc))
        if sqlstate not in CREDENTIAL_DENIAL_SQLSTATES:
            raise PgObserverReadOnlyError(
                "credential escalation was not denied with invalid-authorization (28P01/28000)"
            ) from exc
        return {"attempted": attempted, "observed_sqlstate": sqlstate, "verdict": "DENIED"}
    try:
        connection.close()
    except Exception:  # pragma: no cover - best effort  # noqa: BLE001
        pass
    raise PgObserverReadOnlyError("escalated credential connected; the observer is not fail-closed")


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
# intent builder + validator
# --------------------------------------------------------------------------- #
def build_pg_observer_bootstrap_intent(
    *,
    target_class: str,
    target_host: str,
    database: str,
    observer_role: str,
    observed_schema: str,
    observed_relations: list[str],
    socket_dir: str | None = None,
    loopback_host: str | None = None,
    port: int | None = None,
    endpoint_class: str = "unix_socket_allowlisted",
    auth_mapping: str = "pg_hba_ident_local",
    applier_node_id: str,
    postcheck_node_id: str,
    created_at: str,
    ttl_seconds: int,
    source_head: str,
    intent_id: str | None = None,
) -> dict[str, Any]:
    """Build one canonical, self-hashed ``pg_observer_bootstrap_intent_v1``."""

    if target_class not in TARGET_CLASSES:
        raise PgObserverBootstrapError(f"unrecognized target_class: {target_class!r}")
    if auth_mapping not in OBSERVER_AUTH_METHODS:
        raise PgObserverBootstrapError("auth_mapping must be peer/ident local (no password ingress)")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not (1 <= ttl_seconds <= TTL_CEILING_SECONDS):
        raise PgObserverBootstrapError(f"ttl_seconds must be within [1, {TTL_CEILING_SECONDS}]")
    if applier_node_id == postcheck_node_id:
        raise PgObserverBootstrapError("applier_node_id must differ from postcheck_node_id (applier != verifier)")
    if not HEAD_RE.fullmatch(str(source_head)):
        raise PgObserverBootstrapError("source_head must be a 40-hex commit id")
    created = _parse_time(created_at)
    expires = created + timedelta(seconds=ttl_seconds)
    endpoint = {
        "endpoint_class": endpoint_class,
        "socket_dir": socket_dir,
        "loopback_host": loopback_host,
        "port": port,
    }
    intent: dict[str, Any] = {
        "schema_version": INTENT_SCHEMA_VERSION,
        "intent_id": intent_id or canonical_digest({
            "observer_role": observer_role, "database": database, "target_host": target_host,
            "created_at": created.isoformat(), "source_head": source_head,
        }),
        "target_class": target_class,
        "target_host": target_host,
        "endpoint": endpoint,
        "database": database,
        "observer_role": observer_role,
        "auth_mapping": auth_mapping,
        "observed_schema": observed_schema,
        "observed_relations": list(observed_relations),
        "grant_set_selector": OBSERVER_GRANT_SET_SELECTOR,
        "ttl_seconds": ttl_seconds,
        "applier_node_id": applier_node_id,
        "postcheck_node_id": postcheck_node_id,
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "expires_at": expires.isoformat().replace("+00:00", "Z"),
        "source_head": source_head,
    }
    # 建構期即跑一次結構化 allowlist,任何 over-grant / raw SQL 立即 fail-closed。
    generate_observer_grant_sql(intent)
    _guard_no_secret(intent)
    intent["self_digest"] = intent_self_digest(intent)
    return intent


def validate_pg_observer_bootstrap_intent(intent: Any, *, now: str | None = None) -> list[str]:
    """Validate intent structure/integrity + the grant-set allowlist + time window."""

    if not isinstance(intent, dict):
        return ["observer bootstrap intent must be an object"]
    schema = _schema(str(INTENT_SCHEMA_PATH))
    errors = [
        f"observer bootstrap intent schema violation: {error}"
        for error in schema_subset_errors(intent, schema, schema)
    ]
    if errors:
        return errors
    if intent.get("applier_node_id") == intent.get("postcheck_node_id"):
        errors.append("observer bootstrap intent applier_node_id must differ from postcheck_node_id")
    try:
        generate_observer_grant_sql(intent)
    except PgObserverBootstrapError as exc:
        errors.append(f"observer bootstrap intent grant set is inadmissible: {exc}")
    if _contains_secret_like(intent):
        errors.append("observer bootstrap intent carries secret-like content")
    if intent.get("self_digest") != intent_self_digest(intent):
        errors.append("observer bootstrap intent self_digest does not match canonical intent")
    try:
        created = _parse_time(intent["created_at"])
        expires = _parse_time(intent["expires_at"])
        if expires <= created:
            errors.append("observer bootstrap intent created_at must precede expires_at")
        if expires - created > timedelta(seconds=TTL_CEILING_SECONDS):
            errors.append("observer bootstrap intent TTL exceeds its ceiling")
        if now is not None:
            current = _parse_time(now)
            if not created <= current < expires:
                errors.append("observer bootstrap intent is outside its validity window")
    except (KeyError, TypeError, ValueError):
        errors.append("observer bootstrap intent timestamps are invalid")
    return errors


# --------------------------------------------------------------------------- #
# rollback record builder + validator
# --------------------------------------------------------------------------- #
def build_pg_observer_bootstrap_rollback(
    *,
    intent: dict[str, Any],
    grant_set: dict[str, Any],
    pre_state_digest: str,
    post_state_digest: str,
    observer_absent: bool,
    observed_at: str,
    ttl_seconds: int = EVIDENCE_TTL_SECONDS,
) -> dict[str, Any]:
    """Build one canonical ``pg_observer_bootstrap_rollback_v1`` (exact restoration crux)."""

    restored_exact = pre_state_digest == post_state_digest
    status = "RESTORED_EXACT" if (restored_exact and observer_absent) else "NOT_RESTORED"
    observed = _parse_time(observed_at)
    rollback: dict[str, Any] = {
        "schema_version": ROLLBACK_SCHEMA_VERSION,
        "status": status,
        "intent_id": intent["intent_id"],
        "observer_role": intent["observer_role"],
        "database": intent["database"],
        "host": intent["target_host"],
        "pre_state_digest": pre_state_digest,
        "post_state_digest": post_state_digest,
        "revoke_statements": list(grant_set["revoke"]),
        "drop_statement": grant_set["drop_role"],
        "restored_exact": restored_exact,
        "observer_absent": bool(observer_absent),
        "observed_at": observed.isoformat().replace("+00:00", "Z"),
        "expires_at": (observed + timedelta(seconds=ttl_seconds)).isoformat().replace("+00:00", "Z"),
    }
    _guard_no_secret(rollback)
    rollback["self_digest"] = artifact_self_digest(rollback)
    return rollback


def validate_pg_observer_bootstrap_rollback(rollback: Any, *, now: str | None = None) -> list[str]:
    if not isinstance(rollback, dict):
        return ["observer bootstrap rollback must be an object"]
    schema = _schema(str(ROLLBACK_SCHEMA_PATH))
    errors = [
        f"observer bootstrap rollback schema violation: {error}"
        for error in schema_subset_errors(rollback, schema, schema)
    ]
    if errors:
        return errors
    exact = rollback.get("pre_state_digest") == rollback.get("post_state_digest")
    if rollback.get("status") == "RESTORED_EXACT":
        if not exact:
            errors.append("RESTORED_EXACT requires pre_state_digest == post_state_digest")
        if rollback.get("restored_exact") is not True or rollback.get("observer_absent") is not True:
            errors.append("RESTORED_EXACT requires restored_exact and observer_absent to be true")
    else:
        if exact and rollback.get("observer_absent") is True:
            errors.append("NOT_RESTORED contradicts an exact restoration with an absent observer")
    if _contains_secret_like(rollback):
        errors.append("observer bootstrap rollback carries secret-like content")
    if rollback.get("self_digest") != artifact_self_digest(rollback):
        errors.append("observer bootstrap rollback self_digest is invalid")
    try:
        observed = _parse_time(rollback["observed_at"])
        expires = _parse_time(rollback["expires_at"])
        if not observed < expires:
            errors.append("observer bootstrap rollback observed_at must precede expires_at")
        if now is not None and not observed <= _parse_time(now) < expires:
            errors.append("observer bootstrap rollback is not fresh")
    except (KeyError, TypeError, ValueError):
        errors.append("observer bootstrap rollback timestamps are invalid")
    return errors


# --------------------------------------------------------------------------- #
# independent postcheck builder + validator
# --------------------------------------------------------------------------- #
def _denial_ok(record: Any, allowed: frozenset[str]) -> bool:
    return (
        isinstance(record, dict)
        and record.get("verdict") == "DENIED"
        and SQLSTATE_RE.fullmatch(str(record.get("observed_sqlstate", "")))
        and str(record.get("observed_sqlstate")) in allowed
    )


def build_pg_observer_bootstrap_postcheck(
    *,
    intent: dict[str, Any],
    verifier_node: str,
    applier_node: str,
    reobserved_post_rollback_digest: str,
    read_only_proof: dict[str, Any],
    verifier_capture_digest: str,
    observed_at: str,
    ttl_seconds: int = EVIDENCE_TTL_SECONDS,
) -> dict[str, Any]:
    """Build the independent-verifier ``pg_observer_bootstrap_postcheck_v1``.

    Fail-closed: raises unless the observer's own read-only proof observed every
    required denial (write -> 42501, escalation denied, credential-escalation ->
    28P01/28000) and the search-path reset was harmless.  ``verifier_node`` must
    differ from ``applier_node`` (applier != independent verifier).
    """

    if verifier_node == applier_node:
        raise PgObserverBootstrapError("independent verifier node must differ from the applier node")
    if not DIGEST_RE.fullmatch(str(verifier_capture_digest)):
        raise PgObserverBootstrapError("verifier_capture_digest must be a sha256 digest")
    write = read_only_proof.get("write_denied") if isinstance(read_only_proof, dict) else None
    set_role = read_only_proof.get("set_role_denied") if isinstance(read_only_proof, dict) else None
    search_path = read_only_proof.get("search_path_reset_harmless") if isinstance(read_only_proof, dict) else None
    credential = read_only_proof.get("credential_escalation_denied") if isinstance(read_only_proof, dict) else None
    if not _denial_ok(write, WRITE_DENIAL_SQLSTATES):
        raise PgObserverReadOnlyError("observer write was not denied with insufficient_privilege 42501")
    if not _denial_ok(set_role, SET_ROLE_DENIAL_SQLSTATES):
        raise PgObserverReadOnlyError("observer SET ROLE escalation was not denied")
    if not _denial_ok(credential, CREDENTIAL_DENIAL_SQLSTATES):
        raise PgObserverReadOnlyError("credential escalation was not denied with 28P01/28000")
    if not (isinstance(search_path, dict) and search_path.get("harmless") is True
            and search_path.get("queries_schema_qualified") is True):
        raise PgObserverReadOnlyError("search-path reset was not proven harmless")

    observed = _parse_time(observed_at)
    postcheck: dict[str, Any] = {
        "schema_version": POSTCHECK_SCHEMA_VERSION,
        "status": "PASS",
        "verifier_node": verifier_node,
        "applier_node": applier_node,
        "intent_id": intent["intent_id"],
        "intent_digest": intent["self_digest"],
        "observer_role": intent["observer_role"],
        "database": intent["database"],
        "host": intent["target_host"],
        "source_head": intent["source_head"],
        "reobserved_post_rollback_digest": reobserved_post_rollback_digest,
        "restoration_confirmed": True,
        "read_only_proof": {
            "write_denied": {
                "attempted": str(write["attempted"]),
                "observed_sqlstate": str(write["observed_sqlstate"]),
                "verdict": "DENIED",
            },
            "set_role_denied": {
                "attempted": str(set_role["attempted"]),
                "observed_sqlstate": str(set_role["observed_sqlstate"]),
                "verdict": "DENIED",
            },
            "search_path_reset_harmless": {
                "attempted": str(search_path["attempted"]),
                "effective_search_path": str(search_path["effective_search_path"]),
                "harmless": True,
                "queries_schema_qualified": True,
            },
            "credential_escalation_denied": {
                "attempted": str(credential["attempted"]),
                "observed_sqlstate": str(credential["observed_sqlstate"]),
                "verdict": "DENIED",
            },
        },
        "verifier_capture_digest": verifier_capture_digest,
        "observed_at": observed.isoformat().replace("+00:00", "Z"),
        "expires_at": (observed + timedelta(seconds=ttl_seconds)).isoformat().replace("+00:00", "Z"),
    }
    _guard_no_secret(postcheck)
    postcheck["self_digest"] = artifact_self_digest(postcheck)
    return postcheck


def validate_pg_observer_bootstrap_postcheck(
    postcheck: Any, *, result: dict[str, Any] | None = None, now: str | None = None
) -> list[str]:
    if not isinstance(postcheck, dict):
        return ["observer bootstrap postcheck must be an object"]
    schema = _schema(str(POSTCHECK_SCHEMA_PATH))
    errors = [
        f"observer bootstrap postcheck schema violation: {error}"
        for error in schema_subset_errors(postcheck, schema, schema)
    ]
    if errors:
        return errors
    if postcheck.get("verifier_node") == postcheck.get("applier_node"):
        errors.append("observer bootstrap postcheck verifier_node must differ from applier_node")
    proof = postcheck.get("read_only_proof", {})
    if postcheck.get("status") == "PASS":
        if not _denial_ok(proof.get("write_denied"), WRITE_DENIAL_SQLSTATES):
            errors.append("PASS postcheck requires the observer write to be denied 42501")
        if not _denial_ok(proof.get("set_role_denied"), SET_ROLE_DENIAL_SQLSTATES):
            errors.append("PASS postcheck requires SET ROLE escalation denied")
        if not _denial_ok(proof.get("credential_escalation_denied"), CREDENTIAL_DENIAL_SQLSTATES):
            errors.append("PASS postcheck requires credential escalation denied 28P01/28000")
        if postcheck.get("restoration_confirmed") is not True:
            errors.append("PASS postcheck requires restoration_confirmed")
    if _contains_secret_like(postcheck):
        errors.append("observer bootstrap postcheck carries secret-like content")
    if postcheck.get("self_digest") != artifact_self_digest(postcheck):
        errors.append("observer bootstrap postcheck self_digest is invalid")
    if isinstance(result, dict):
        if postcheck.get("intent_id") != result.get("intent_id"):
            errors.append("observer bootstrap postcheck intent_id is not bound to the result")
        if postcheck.get("applier_node") != result.get("apply_actor_node"):
            errors.append("observer bootstrap postcheck applier_node is not the result apply actor")
        if postcheck.get("verifier_node") != result.get("independent_verifier_node"):
            errors.append("observer bootstrap postcheck verifier_node is not the result verifier")
    try:
        observed = _parse_time(postcheck["observed_at"])
        expires = _parse_time(postcheck["expires_at"])
        if not observed < expires:
            errors.append("observer bootstrap postcheck observed_at must precede expires_at")
        if now is not None and not observed <= _parse_time(now) < expires:
            errors.append("observer bootstrap postcheck is not fresh")
    except (KeyError, TypeError, ValueError):
        errors.append("observer bootstrap postcheck timestamps are invalid")
    return errors


# --------------------------------------------------------------------------- #
# result builder + validator (+ the fail-closed pending result)
# --------------------------------------------------------------------------- #
def _redact_endpoint(endpoint: Any) -> dict[str, Any]:
    endpoint = endpoint if isinstance(endpoint, dict) else {}
    return {
        "endpoint_class": endpoint.get("endpoint_class"),
        "socket_dir": endpoint.get("socket_dir"),
        "loopback_host": endpoint.get("loopback_host"),
        "port": endpoint.get("port"),
    }


def _base_result(intent: dict[str, Any], grant_set: dict[str, Any], *, apply_actor_node: str) -> dict[str, Any]:
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "adapter_id": ADAPTER_ID,
        "intent_id": intent["intent_id"],
        "intent_digest": intent["self_digest"],
        "target_class": intent["target_class"],
        "target_host": intent["target_host"],
        "endpoint": _redact_endpoint(intent.get("endpoint")),
        "database": intent["database"],
        "observer_role": intent["observer_role"],
        "auth_mapping": intent["auth_mapping"],
        "observed_schema": intent["observed_schema"],
        "observed_relations": list(intent["observed_relations"]),
        "grant_set_selector": OBSERVER_GRANT_SET_SELECTOR,
        "grant_set_digest": grant_set_digest(grant_set),
        "apply_actor_node": apply_actor_node,
        "independent_verifier_node": intent["postcheck_node_id"],
        "source_head": intent["source_head"],
        "boundary": {
            "production_apply_performed": False,
            "production_running_attested": False,
            "load_verified": False,
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
    """Build the typed ``EXTERNAL_VERIFICATION_PENDING`` result — never a fake success."""

    grant_set = generate_observer_grant_sql(intent)
    result = _base_result(intent, grant_set, apply_actor_node=apply_actor_node or intent["applier_node_id"])
    result.update({
        "status": "EXTERNAL_VERIFICATION_PENDING",
        "pre_state_digest": None,
        "applied_grant_set_digest": None,
        "independent_postcheck": None,
        "rollback_record": None,
        "operator_authorization": None,
        "operator_signature_pem": None,
        "evidence_class": "STRUCTURAL_ONLY",
        "started_at": _parse_time(now).isoformat().replace("+00:00", "Z"),
        "completed_at": _parse_time(now).isoformat().replace("+00:00", "Z"),
        "evidence_expires_at": _plus_seconds(now, ttl_seconds),
        "ttl_seconds": ttl_seconds,
        "failure_reason": reason,
    })
    _guard_no_secret(result)
    result["self_digest"] = artifact_self_digest(result)
    return result


def build_pg_observer_bootstrap_result(
    *,
    intent: dict[str, Any],
    grant_set: dict[str, Any],
    status: str,
    pre_state_digest: str,
    applied_grant_set_digest: str | None,
    postcheck: dict[str, Any] | None,
    rollback_record: dict[str, Any] | None,
    operator_authorization: dict[str, Any],
    operator_signature: bytes,
    apply_actor_node: str,
    started_at: str,
    completed_at: str,
    failure_reason: str | None = None,
    ttl_seconds: int = EVIDENCE_TTL_SECONDS,
) -> dict[str, Any]:
    """Build a canonical ``pg_observer_bootstrap_result_v1`` for a real disposable apply."""

    if status not in {"APPLIED_ROLLED_BACK_EXACT", "ROLLED_BACK_INTERRUPTED", "NOT_RESTORED_FAILED", "FAILED"}:
        raise PgObserverBootstrapError(f"unrecognized applied result status: {status!r}")
    if intent.get("target_class") != DISPOSABLE_TARGET_CLASS:
        raise PgObserverBootstrapError("a real applied result is only emitted for a disposable_local target")
    if status == "APPLIED_ROLLED_BACK_EXACT":
        if not isinstance(postcheck, dict) or not isinstance(rollback_record, dict):
            raise PgObserverBootstrapError("APPLIED_ROLLED_BACK_EXACT requires an embedded postcheck and rollback record")
        if rollback_record.get("post_state_digest") != pre_state_digest:
            raise PgObserverBootstrapError("APPLIED_ROLLED_BACK_EXACT requires rollback post == pre (exact restoration)")
        if applied_grant_set_digest is None or applied_grant_set_digest == pre_state_digest:
            raise PgObserverBootstrapError("APPLIED_ROLLED_BACK_EXACT requires the apply to change catalog state")
    result = _base_result(intent, grant_set, apply_actor_node=apply_actor_node)
    completed = _parse_time(completed_at)
    result.update({
        "status": status,
        "pre_state_digest": pre_state_digest,
        "applied_grant_set_digest": applied_grant_set_digest,
        "independent_postcheck": postcheck,
        "rollback_record": rollback_record,
        "operator_authorization": operator_authorization,
        "operator_signature_pem": bytes(operator_signature).decode("ascii"),
        "evidence_class": "LOCAL_REPRODUCIBLE" if status == "APPLIED_ROLLED_BACK_EXACT" else "STRUCTURAL_ONLY",
        "started_at": _parse_time(started_at).isoformat().replace("+00:00", "Z"),
        "completed_at": completed.isoformat().replace("+00:00", "Z"),
        "evidence_expires_at": (completed + timedelta(seconds=ttl_seconds)).isoformat().replace("+00:00", "Z"),
        "ttl_seconds": ttl_seconds,
        "failure_reason": None if status == "APPLIED_ROLLED_BACK_EXACT" else (
            failure_reason or "observer apply did not complete an exact rollback"
        ),
    })
    # SSHSIG bytes 為公開簽章(非機密);掃描整份 result(排除公開簽章欄位)確保沒有 DSN/密碼被夾帶。
    # FIX-10(E2 P2):公開簽章欄位另以 strict-base64 body 護欄把關,確保 build 不會 emit 一份 armor 外殼
    # 合法但 body 夾帶可讀 plaintext 的簽章;其餘欄位再走(排除該欄的)secret 掃描,確保無 DSN/密碼夾帶。
    _guard_operator_signature_pem_body(result.get("operator_signature_pem"))
    _guard_no_secret(_result_secret_scan_view(result))
    result["self_digest"] = artifact_self_digest(result)
    return result


def validate_pg_observer_bootstrap_result(result: Any, *, now: str | None = None) -> list[str]:
    if not isinstance(result, dict):
        return ["observer bootstrap result must be an object"]
    schema = _schema(str(RESULT_SCHEMA_PATH))
    errors = [
        f"observer bootstrap result schema violation: {error}"
        for error in schema_subset_errors(result, schema, schema)
    ]
    if errors:
        return errors
    status = result.get("status")
    if result.get("apply_actor_node") == result.get("independent_verifier_node"):
        errors.append("observer bootstrap result apply actor must differ from the independent verifier")
    # 邊界恆 false(九 authority、生產施加、running attested、load verified)。
    boundary = result.get("boundary", {})
    if boundary.get("nine_authorities_false") is not True or boundary.get("production_apply_performed") is not False:
        errors.append("observer bootstrap result boundary must keep production apply off and nine authorities false")
    if status == "EXTERNAL_VERIFICATION_PENDING":
        if result.get("independent_postcheck") is not None or result.get("rollback_record") is not None:
            errors.append("EXTERNAL_VERIFICATION_PENDING must not embed a postcheck or rollback record")
        if not (isinstance(result.get("failure_reason"), str) and result.get("failure_reason")):
            errors.append("EXTERNAL_VERIFICATION_PENDING requires a failure_reason")
    elif status == "APPLIED_ROLLED_BACK_EXACT":
        if result.get("target_class") != DISPOSABLE_TARGET_CLASS:
            errors.append("APPLIED_ROLLED_BACK_EXACT requires a disposable_local target")
        if result.get("evidence_class") != "LOCAL_REPRODUCIBLE":
            errors.append("APPLIED_ROLLED_BACK_EXACT requires LOCAL_REPRODUCIBLE evidence")
        errors.extend(validate_pg_observer_bootstrap_postcheck(result.get("independent_postcheck"), result=result, now=now))
        errors.extend(validate_pg_observer_bootstrap_rollback(result.get("rollback_record"), now=now))
        rollback = result.get("rollback_record") or {}
        if rollback.get("post_state_digest") != result.get("pre_state_digest"):
            errors.append("APPLIED_ROLLED_BACK_EXACT requires rollback post_state == result pre_state")
        if rollback.get("status") != "RESTORED_EXACT":
            errors.append("APPLIED_ROLLED_BACK_EXACT requires a RESTORED_EXACT rollback")
        postcheck = result.get("independent_postcheck") or {}
        if postcheck.get("reobserved_post_rollback_digest") != result.get("pre_state_digest"):
            errors.append("postcheck reobserved digest must equal the restored (pre == post) baseline")
        # FIX-5(E2 P2):APPLIED receipt 的 operator_authorization 必須是「結構良好 + 精確 intent 綁定」
        # 的物件(重用 AUTHORIZATION_FIELDS 契約),把 {"totally":"bogus"} 及任何 intent 不符的授權擋掉。
        # 這是**結構完整性**綁定,不是密碼學認證——真 SSHSIG 再驗留給 S2.0 EFFECT session(見 helper 註)。
        errors.extend(operator_authorization_binding_errors(
            result.get("operator_authorization"),
            intent_id=result.get("intent_id"),
            intent_digest=result.get("intent_digest"),
            source_head=result.get("source_head"),
        ))
    # grant_set_digest 必可由 intent 的結構化 allowlist 獨立重算。
    intent_shape = {
        "grant_set_selector": result.get("grant_set_selector"),
        "observer_role": result.get("observer_role"),
        "observed_schema": result.get("observed_schema"),
        "observed_relations": result.get("observed_relations"),
        "auth_mapping": result.get("auth_mapping"),
    }
    try:
        recomputed = grant_set_digest(generate_observer_grant_sql(intent_shape))
        if result.get("grant_set_digest") != recomputed:
            errors.append("observer bootstrap result grant_set_digest does not bind the structured allowlist")
    except PgObserverBootstrapError:
        errors.append("observer bootstrap result grant set is inadmissible")
    # FIX-11(E2 P2 根因收口):operator_signature_pem 的 strict-base64 body 護欄必須**無條件**對任何
    # 非 None 字串生效,不限 APPLIED status。FIX-10 誤把它置於 APPLIED_ROLLED_BACK_EXACT elif 內,
    # 使其餘 status(EXTERNAL_VERIFICATION_PENDING / FAILED / ROLLED_BACK_INTERRUPTED / NOT_RESTORED_FAILED)
    # 的偽造 receipt 能於此欄搭載可讀 plaintext 機密(如 "password=hunter2" / "pgpassword=…"):該欄被
    # _result_secret_scan_view 排除於下方 secret 掃描之外,central validator 又純委派(無獨立掃描)→ 機密
    # 會被序列化過中央閘。此處把檢查移出所有 status 分支,與 build 兩條路徑的 _guard_operator_signature_pem_body
    # (build 期 1144/1382)對稱,令任何 status/path 皆不可能於此欄搭載可讀 plaintext。None → isinstance False
    # → 跳過(PENDING 的 None 路徑不受影響)。此無條件檢查正是令下方 secret-scan 排除該欄位得以**可證安全**者。
    signature_pem = result.get("operator_signature_pem")
    if isinstance(signature_pem, str) and not _operator_signature_pem_body_is_strict_base64(signature_pem):
        errors.append(
            "operator_signature_pem body is not strict base64 (possible non-signature payload)"
        )
    if _contains_secret_like(_result_secret_scan_view(result)):
        errors.append("observer bootstrap result carries secret-like content")
    if result.get("self_digest") != artifact_self_digest(result):
        errors.append("observer bootstrap result self_digest is invalid")
    try:
        started = _parse_time(result["started_at"])
        expires = _parse_time(result["evidence_expires_at"])
        if not started <= expires:
            errors.append("observer bootstrap result started_at must precede evidence_expires_at")
        if now is not None and not started <= _parse_time(now) < expires:
            errors.append("observer bootstrap result evidence is not fresh")
    except (KeyError, TypeError, ValueError):
        errors.append("observer bootstrap result timestamps are invalid")
    return errors


# --------------------------------------------------------------------------- #
# the applier (production stays fail-closed until an exact operator SSHSIG)
# --------------------------------------------------------------------------- #
def apply_observer_bootstrap(
    intent: Any,
    operator_authorization: Any = None,
    signature: Any = None,
    *,
    now: str,
    source_head: str,
    disposable: Any = None,
    postcheck: dict[str, Any] | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
    apply_fault: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Intent-derived observer-bootstrap applier — production apply stays fail-closed.

    Returns a typed ``pg_observer_bootstrap_result_v1``.  Without a VALID operator
    SSHSIG over the exact intent+source_head it returns ``EXTERNAL_VERIFICATION_PENDING``
    (NEVER a success).  A ``production`` target ALSO returns
    ``EXTERNAL_VERIFICATION_PENDING`` in this WP2 source lane: the real production
    socket / apply is the S2.0 EFFECT session (no production PG contact here).  For a
    ``disposable_local`` target with a valid SSHSIG and an injected throwaway-cluster
    connection it runs the REAL structured SQL (apply -> rollback, exact restoration)
    and embeds the distinct verifier's ``postcheck``.  ``apply_fault`` is a test-only
    hook to inject a mid-apply failure (partial-failure rollback proof).
    """

    # FIX-6(E2 P3):先只驗「結構/整合/allowlist/TTL 上限」(now=None,**不含**當前有效窗)——
    # genuine malformed / invalid-structure intent 一律 raise(硬契約錯誤)。
    structural_errors = validate_pg_observer_bootstrap_intent(intent)
    if structural_errors:
        raise PgObserverBootstrapError("observer bootstrap intent is inadmissible: " + "; ".join(structural_errors[:3]))
    if not HEAD_RE.fullmatch(str(source_head)) or intent.get("source_head") != source_head:
        raise PgObserverBootstrapError("source_head must be a 40-hex id equal to the intent source head")
    apply_actor_node = intent["applier_node_id"]
    started_at = started_at or now
    completed_at = completed_at or now
    # FIX-6(E2 P3):結構有效但落在「當前有效窗」之外(例如 expired TTL / not-yet-valid)→ 依 PENDING
    # 合約 fail-closed(typed EXTERNAL_VERIFICATION_PENDING,非 raise)。此處刻意與上方 malformed-raise
    # 分離:now=None 只擋結構,now=now 只多擋有效窗,故不會把 malformed 與 stale-window 混為一談。
    # FIX-9(E2 #3):governance 供給的 now 若本身 malformed(無法 parse),window validator 會把它歸為
    # 非空錯誤而落入 build_pending_result,其內 _parse_time(now) 會逸出**裸 ValueError**。此處把該路徑
    # 唯一的 ValueError 來源(malformed now)比照 malformed-intent 硬合約轉為 typed PgObserverBootstrapError
    # (fail-closed);不讓未分類例外逸出,也不冒充「outside validity window」的 stale-window pending。
    # 註:此點之後才可能被走到的其他 build_pending_result 呼叫,皆以「now 已可 parse」為前提(malformed
    # now 必先在此被攔),故不需重複包裹。
    try:
        if validate_pg_observer_bootstrap_intent(intent, now=now):
            return build_pending_result(
                intent,
                reason="observer bootstrap intent is outside its current validity window (expired or not-yet-valid)",
                now=now,
                apply_actor_node=apply_actor_node,
            )
    except ValueError as exc:
        raise PgObserverBootstrapError(f"observer bootstrap now is malformed: {now!r}") from exc

    valid, reason = _operator_authorization_is_valid(
        operator_authorization, signature, intent=intent, source_head=source_head, now=now
    )
    if not valid:
        return build_pending_result(intent, reason=reason, now=now, apply_actor_node=apply_actor_node)
    if intent["target_class"] == PRODUCTION_TARGET_CLASS or disposable is None:
        # SOURCE 界線:即使已授權,WP2 也絕不開生產 socket;真 apply 屬 S2.0 EFFECT session。
        return build_pending_result(
            intent,
            reason=(
                "production observer apply is deferred to the S2.0 EFFECT session; "
                "the WP2 source lane makes no production PG socket"
            ),
            now=now,
            apply_actor_node=apply_actor_node,
        )

    # disposable_local + 有效 SSHSIG + 注入的丟棄式叢集連線 → 真實結構化 SQL。
    grant_set = generate_observer_grant_sql(intent)
    role, schema, relations = intent["observer_role"], intent["observed_schema"], intent["observed_relations"]
    cursor = disposable.cursor()
    pre = observer_role_acl_state_digest(cursor, role=role, schema=schema, relations=relations)
    # FIX-1(OPS F1):角色若「本來就存在」→ 在任何 DDL 之前 fail-closed。existence-guarded rollback
    # 無法分辨「本次 CREATE 的角色」與「原本就有的角色」;若貿然 apply→42710(duplicate_object)→
    # rollback,會把這個既存(非本次建立)的角色連同其權限一併 DROP。故此處在 apply 前就拒絕,
    # 絕不進入 apply/rollback,回傳 typed fail-closed pending(既存角色必存活)。
    if observer_role_present(cursor, role=role):
        return build_pending_result(
            intent,
            reason=(
                "observer role already exists; refusing to create or drop a pre-existing role"
            ),
            now=now,
            apply_actor_node=apply_actor_node,
        )
    apply_ok = True
    applied: str | None = None
    interruption: str | None = None
    try:
        observer_bootstrap_apply(cursor, grant_set=grant_set, on_step=apply_fault)
        applied = observer_role_acl_state_digest(cursor, role=role, schema=schema, relations=relations)
    except Exception as exc:  # noqa: BLE001 - a mid-apply failure must still roll back
        apply_ok = False
        interruption = f"observer apply interrupted before completion: {exc}"
    observer_bootstrap_rollback(cursor, grant_set=grant_set)
    post = observer_role_acl_state_digest(cursor, role=role, schema=schema, relations=relations)
    observer_absent = post == pre

    rollback_record = build_pg_observer_bootstrap_rollback(
        intent=intent, grant_set=grant_set, pre_state_digest=pre,
        post_state_digest=post, observer_absent=observer_absent, observed_at=completed_at,
    )
    if apply_ok and post == pre and applied is not None and applied != pre:
        if not isinstance(postcheck, dict):
            raise PgObserverBootstrapError(
                "a disposable exact apply requires the distinct verifier's postcheck to embed"
            )
        if postcheck.get("applier_node") != apply_actor_node:
            raise PgObserverBootstrapError("embedded postcheck applier_node must equal the applier node")
        return build_pg_observer_bootstrap_result(
            intent=intent, grant_set=grant_set, status="APPLIED_ROLLED_BACK_EXACT",
            pre_state_digest=pre, applied_grant_set_digest=applied, postcheck=postcheck,
            rollback_record=rollback_record, operator_authorization=operator_authorization,
            operator_signature=bytes(signature), apply_actor_node=apply_actor_node,
            started_at=started_at, completed_at=completed_at,
        )
    # 部分失敗但已還原(observer 已消失,post == pre):誠實回報 ROLLED_BACK_INTERRUPTED(不假成功)。
    status = "ROLLED_BACK_INTERRUPTED" if (post == pre and observer_absent) else "NOT_RESTORED_FAILED"
    result = _base_result(intent, grant_set, apply_actor_node=apply_actor_node)
    completed = _parse_time(completed_at)
    result.update({
        "status": status,
        "pre_state_digest": pre,
        "applied_grant_set_digest": applied,
        "independent_postcheck": None,
        "rollback_record": rollback_record,
        "operator_authorization": operator_authorization,
        "operator_signature_pem": bytes(signature).decode("ascii"),
        "evidence_class": "STRUCTURAL_ONLY",
        "started_at": _parse_time(started_at).isoformat().replace("+00:00", "Z"),
        "completed_at": completed.isoformat().replace("+00:00", "Z"),
        "evidence_expires_at": (completed + timedelta(seconds=EVIDENCE_TTL_SECONDS)).isoformat().replace("+00:00", "Z"),
        "ttl_seconds": EVIDENCE_TTL_SECONDS,
        "failure_reason": interruption or "observer apply did not complete an exact rollback",
    })
    # FIX-10(E2 P2):非精確路徑同樣先過 strict-base64 body 護欄再走 secret 掃描(build 永不 emit 一份
    # body 非 base64 的簽章欄位)。
    _guard_operator_signature_pem_body(result.get("operator_signature_pem"))
    _guard_no_secret(_result_secret_scan_view(result))
    result["self_digest"] = artifact_self_digest(result)
    return result


# --------------------------------------------------------------------------- #
# closure binding (source-only; mirrors validate_target_host_effect_binding)
# --------------------------------------------------------------------------- #
def validate_pg_observer_bootstrap_binding(
    packet: dict[str, Any],
    route: dict[str, Any],
    fragments_by_node: dict[str, dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]],
    valid_receipts: dict[str, dict[str, Any]],
) -> list[str]:
    """Closure admission for one observer-bootstrap effect: intent + OPS preflight + result
    + independent postcheck bound to the verifier's OWN governed command_capture_v2.

    SOURCE-only: this predicate is NOT wired into the live ``validate_deploy_effect_binding``
    dispatch and no ``route_task`` effect node is injected before the S2.0 EFFECT session;
    it exists so that session's closure can admit the exact three-way (result verifier
    capture digest == ops_postcheck capture digest == verifier command_capture_v2
    record_digest) cross-check with applier != verifier.
    """

    errors: list[str] = []
    matching = [
        (evidence_id, receipt) for evidence_id, receipt in valid_receipts.items()
        if isinstance(receipt, dict) and receipt.get("adapter_id") == ADAPTER_ID
    ]
    if len(matching) != 1:
        return ["observer bootstrap closure PASS requires exactly one observer-bootstrap effect receipt"]
    receipt_id, receipt = matching[0]

    effect_nodes = [
        node for node in route.get("nodes", [])
        if node.get("kind") == "effect_adapter" and node.get("mandatory")
    ]
    if not any(node.get("id") == ADAPTER_ID for node in effect_nodes):
        errors.append("observer bootstrap effect receipt is not routed to the exact adapter node")
    if receipt.get("status") != "APPLIED_ROLLED_BACK_EXACT":
        errors.append("observer bootstrap closure PASS requires an APPLIED_ROLLED_BACK_EXACT receipt")
    else:
        # FIX-5(E2 P2):APPLIED closure receipt 的 operator_authorization 必須結構良好且精確綁定其 intent
        # (結構完整性,不是密碼學認證——真 SSHSIG 再驗留給 S2.0 EFFECT session,見 helper 誠實界線註)。
        errors.extend(operator_authorization_binding_errors(
            receipt.get("operator_authorization"),
            intent_id=receipt.get("intent_id"),
            intent_digest=receipt.get("intent_digest"),
            source_head=receipt.get("source_head"),
        ))

    # 精確 intent 授權(claim_evidence,digest 綁定)。
    intent_source = f"{INTENT_SCHEMA_VERSION}:{receipt.get('intent_id')}"
    intent_refs = [
        ref for ref in packet.get("authority_refs", [])
        if ref.get("class") == "claim_evidence" and ref.get("source") == intent_source
    ]
    if len(intent_refs) != 1 or intent_refs[0].get("digest") != receipt.get("intent_digest"):
        errors.append("observer bootstrap effect receipt lacks exact intent authority")
    # OPS preflight fragment 必存在(intent + OPS preflight + result + independent postcheck)。
    if not fragments_by_node.get("ops_preflight"):
        errors.append("observer bootstrap closure requires an OPS preflight fragment")

    # 內嵌的獨立 postcheck:verifier != applier,且帶一個 bound verifier_capture_digest。
    postcheck = receipt.get("independent_postcheck") if isinstance(receipt.get("independent_postcheck"), dict) else None
    applier_node = receipt.get("apply_actor_node")
    receipt_verifier_digest = postcheck.get("verifier_capture_digest") if isinstance(postcheck, dict) else None
    verifier_capture_ev: dict[str, Any] | None = None
    if postcheck is None:
        errors.append("observer bootstrap closure requires the receipt's embedded independent postcheck")
    else:
        errors.extend(validate_pg_observer_bootstrap_postcheck(postcheck, result=receipt))
        if postcheck.get("verifier_node") == applier_node:
            errors.append("observer bootstrap postcheck verifier must differ from the applier node")
        if not DIGEST_RE.fullmatch(str(receipt_verifier_digest or "")):
            errors.append("observer bootstrap postcheck lacks a bound verifier_capture_digest")

    # 第三份 evidence:獨立驗證者自己的 governed command_capture_v2(在 ops_postcheck fragment)。
    # 三方交叉:effect receipt 內嵌 postcheck 的 verifier_capture_digest == 該 evidence digest ==
    # 內嵌 command_capture_v2 的 record_digest;capturer node/role 與 applier 相異(applier != verifier)。
    fragment = fragments_by_node.get("ops_postcheck", {})
    cap_refs = [
        evidence_by_id[ref] for ref in fragment.get("evidence_refs", [])
        if ref in evidence_by_id
        and evidence_by_id[ref].get("scope") == "runtime"
        and evidence_by_id[ref].get("source") == "ops_postcheck"
        and evidence_by_id[ref].get("kind") == "command_capture_v2"
    ]
    if len(cap_refs) != 1:
        errors.append("observer bootstrap closure requires exactly one verifier command_capture_v2 in ops_postcheck")
    elif DIGEST_RE.fullmatch(str(receipt_verifier_digest or "")):
        verifier_capture_ev = cap_refs[0]
        if verifier_capture_ev.get("digest") != receipt_verifier_digest:
            errors.append("observer bootstrap verifier capture digest is not the three-way-bound digest")
        capture = verifier_capture_ev.get("artifact")
        if isinstance(capture, dict) and str(capture.get("record_digest")) != str(receipt_verifier_digest):
            errors.append("observer bootstrap verifier command_capture_v2 record_digest is not the bound digest")
        if isinstance(capture, dict) and capture.get("node_id") == applier_node:
            errors.append("observer bootstrap verifier capture node must differ from the applier node")

    # acceptance PASS 必同時綁 effect receipt + verifier capture 兩份 evidence id。
    required_ids = {receipt_id}
    if verifier_capture_ev is not None:
        required_ids.add(verifier_capture_ev.get("id"))
    accepted = (
        postcheck is not None and verifier_capture_ev is not None
        and any(
            item.get("status") == "PASS" and required_ids.issubset(set(item.get("evidence_refs", [])))
            for item in packet.get("acceptance", [])
        )
    )
    if not accepted:
        errors.append(
            "observer bootstrap passed acceptance must bind the effect receipt + verifier command capture"
        )
    return errors
