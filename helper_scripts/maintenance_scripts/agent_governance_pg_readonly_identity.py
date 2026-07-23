"""Disposable-cluster PostgreSQL read-only identity Adapter for AIML LR0A (S1.1).

This Adapter proves, against a throwaway local PostgreSQL cluster, that a
dedicated read-only role connected over an allowlisted unix socket (or an
explicitly authenticated loopback identity) can run a fixed catalog/``SELECT``
allowlist and is denied every write / role-escalation / search-path-hijack
attempt.  It emits one canonical, self-hashed ``pg_readonly_identity_receipt_v1``.

S1.1 is ``DISPOSABLE_ONLY``: production PG is rejected fail-closed, direct
``psql`` stays denied (this Adapter uses ``psycopg2`` over the socket and never
shells out), and no migration/writer is ever created by the Adapter.  The
Adapter self-validates its own receipt and registers no routable node.  (Note:
S1.2 subsequently added ``pg_readonly_identity_receipt_v1`` to the central
validator's ``SCHEMA_FILES`` so the central gate DELEGATES to this Adapter's own
validator with mandatory ``now`` freshness — recognition wiring only, still no
routable/closure node.)
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from agent_governance_schema import schema_subset_errors


ADAPTER_ID = "pg_readonly_identity_adapter_v1"
RECEIPT_SCHEMA_VERSION = "pg_readonly_identity_receipt_v1"

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = Path(__file__).resolve()
SCHEMA_PATH = (
    REPO_ROOT
    / "program_code/ml_training/schemas/aiml_gate_receipts"
    / "pg_readonly_identity_receipt_v1.schema.json"
)

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SQLSTATE_RE = re.compile(r"^[0-9A-Z]{5}$")

ENDPOINT_CLASSES = frozenset({"unix_socket_allowlisted", "authenticated_loopback"})
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})
TARGET_CLASSES = frozenset({"disposable_local", "production"})
# S1.1 只接受 disposable_local;production 一律 fail-closed 拒絕。
S1_TARGET_CLASS = "disposable_local"
EVIDENCE_CLASSES = frozenset({"LOCAL_REPRODUCIBLE", "STRUCTURAL_ONLY"})
PLATFORM_OS = frozenset({"darwin", "linux"})

# RO 角色的禁用屬性:任一為 true 即非唯讀角色。
FORBIDDEN_ROLE_ATTRS = (
    "rolsuper",
    "rolcreaterole",
    "rolcreatedb",
    "rolbypassrls",
    "rolreplication",
)
ROLE_ATTR_KEYS = FORBIDDEN_ROLE_ATTRS + ("rolcanlogin",)
# 拒絕類 SQLSTATE:25006=read_only_sql_transaction、42501=insufficient_privilege。
# 這兩碼皆由真實 disposable server 於本機經驗證觀察到(見 disposable 測試)。
DENIAL_SQLSTATES = frozenset({"25006", "42501"})
PINNED_SEARCH_PATH = "pg_catalog"
TTL_CEILING_SECONDS = 3600
# 連線層硬性釘住唯讀交易與 search_path,任何 session 內重設對 allowlist 查詢無害
# (全部 schema-qualified 或內建函式)。
READONLY_CONNECTION_OPTIONS = (
    "-c default_transaction_read_only=on -c search_path=pg_catalog"
)

# 唯一可執行的 SQL:以穩定 query_id 為鍵,catalog/SELECT only,無自由文字路徑。
ALLOWED_QUERIES: dict[str, str] = {
    "pg_role_attributes_v1": (
        "SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolcanlogin, "
        "rolreplication, rolbypassrls FROM pg_catalog.pg_roles "
        "WHERE rolname = current_user"
    ),
    "pg_session_readonly_state_v1": (
        "SELECT current_setting('transaction_read_only'), "
        "current_setting('search_path'), current_user"
    ),
    "pg_server_version_v1": "SELECT version()",
}

# 需中和的 ambient 路由面(以及任何其他 PG* 前綴鍵)。
PG_ROUTING_ENV_KEYS = (
    "PGHOST",
    "PGHOSTADDR",
    "PGPORT",
    "PGDATABASE",
    "PGUSER",
    "PGPASSWORD",
    "PGPASSFILE",
    "PGSERVICE",
    "PGSERVICEFILE",
    "PGSYSCONFDIR",
    "PGOPTIONS",
    "PGSSLMODE",
    "PGREQUIRESSL",
    "PGCLIENTENCODING",
    "PGCONNECT_TIMEOUT",
)
# 以隔離值重新賦予(而非繼承)的三個鍵:PGSYSCONFDIR 指向空目錄、PGSERVICEFILE 與
# PGPASSFILE 各指向隔離目錄內不存在的檔案,藉此中和 system/user psqlrc、
# pg_service.conf 與 ~/.pgpass(HOME 仍保留,故必須顯式改寫 PGPASSFILE 才能真正切斷
# libpq 對 ~/.pgpass 的回退)。
PG_ISOLATED_ENV_KEYS = ("PGSYSCONFDIR", "PGSERVICEFILE", "PGPASSFILE")
# clean env 只允許從來源環境帶入這些非 PG 路由鍵。
ENV_ALLOWLIST = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "HOME", "TMPDIR")

# 對序列化 receipt 做的機密掃描;沿用 aiml_gate_receipt_validator.GITHUB_SECRET_LIKE_RE
# 風格,額外加入 PGPASSWORD / password= / postgres(ql)://user:pass@ 形態。
PG_SECRET_LIKE_RE = re.compile(
    r"(?:github_pat_|gh[pousr]_[A-Za-z0-9]{12,})"
    r"|(?:access[_-]?token|auth(?:orization)?|client[_-]?secret|password|"
    r"pgpassword|private[_-]?key)\s*[:=]"
    r"|(?:basic|bearer)\s+[A-Za-z0-9._~+/=-]{12,}"
    r"|postgres(?:ql)?://[^\s:/@]+:[^\s:/@]+@",
    re.IGNORECASE,
)
SECRET_PATTERNS_CHECKED = (
    "auth_scheme_token",
    "credential_assignment",
    "github_token",
    "postgres_dsn_credentials",
)

RECEIPT_FIELDS = frozenset({
    "schema_version",
    "adapter_id",
    "status",
    "caller",
    "platform",
    "target_class",
    "evidence_class",
    "endpoint",
    "database",
    "role",
    "session_read_only",
    "ambient_routing_scrubbed",
    "queries",
    "result_digest",
    "negative_cases",
    "source_sha256",
    "schema_sha256",
    "secret_scan",
    "observation_time",
    "expires_at",
    "ttl_seconds",
    "failure_reason",
    "self_digest",
})


class SecretLeakageError(RuntimeError):
    """Raised when a would-be receipt field carries secret-like content.

    Fail-closed: the Adapter refuses to serialize any receipt (even a FAIL one)
    that would leak a credential, rather than emit it with the secret bound.
    """


class ReadOnlyProbeError(RuntimeError):
    """Raised when a negative probe did not observe its required denial.

    A write, role escalation, or persistent search-path hijack that is NOT
    denied means the target cluster is not actually read-only; the Adapter
    refuses to certify anything against it.
    """


# --------------------------------------------------------------------------- #
# canonical digest helpers (mirror agent_governance_effects.py)
# --------------------------------------------------------------------------- #
def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone is required")
    return parsed


@lru_cache(maxsize=1)
def _receipt_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def source_sha256() -> str:
    """Return the sha256 identity of this Adapter module source."""

    return _file_sha256(SOURCE_PATH)


@lru_cache(maxsize=1)
def schema_sha256() -> str:
    """Return the sha256 identity of the receipt schema file."""

    return _file_sha256(SCHEMA_PATH)


def receipt_digest(receipt: dict[str, Any]) -> str:
    """Hash every receipt field except the self-digest."""

    unsigned = {key: value for key, value in receipt.items() if key != "self_digest"}
    return _sha256_bytes(_canonical_bytes(unsigned))


# --------------------------------------------------------------------------- #
# query allowlist
# --------------------------------------------------------------------------- #
def resolve_allowed_query(query_id: str) -> str:
    """Return the exact allowlisted SQL for ``query_id`` or raise.

    There is no free-text path: caller-supplied SQL can never be executed.
    """

    if not isinstance(query_id, str) or query_id not in ALLOWED_QUERIES:
        raise ValueError(f"query_id is not allowlisted: {query_id!r}")
    return ALLOWED_QUERIES[query_id]


def allowed_query_digest(query_id: str) -> str:
    """Return the sha256 of the exact allowlisted SQL text for binding."""

    return _sha256_bytes(resolve_allowed_query(query_id).encode("utf-8"))


def build_query_record(query_id: str, rows: list) -> dict[str, Any]:
    """Build one bound query-result record from executed allowlisted rows."""

    normalized = [list(row) for row in rows]
    return {
        "query_id": query_id,
        "query_sha256": allowed_query_digest(query_id),
        "row_count": len(normalized),
        "result_digest": _sha256_bytes(_canonical_bytes(normalized)),
    }


def _overall_result_digest(query_records: list[dict[str, Any]]) -> str:
    ordered = sorted(query_records, key=lambda record: record["query_id"])
    projection = [
        {
            "query_id": record["query_id"],
            "query_sha256": record["query_sha256"],
            "row_count": record["row_count"],
            "result_digest": record["result_digest"],
        }
        for record in ordered
    ]
    return _sha256_bytes(_canonical_bytes(projection))


# --------------------------------------------------------------------------- #
# ambient PG* / psqlrc scrubbing
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _psqlrc_isolation_dir() -> str:
    # 每個進程建立一個空目錄供 PGSYSCONFDIR 隔離用;空目錄內無 psqlrc/pg_service.conf。
    # lru_cache 保證每進程只建一次;註冊 atexit 於進程結束時清除,避免空目錄永久累積。
    path = tempfile.mkdtemp(prefix="aiml_pg_confdir_")
    atexit.register(shutil.rmtree, path, ignore_errors=True)
    return path


def _is_pg_env_key(key: str) -> bool:
    return key.upper().startswith("PG") or key in PG_ROUTING_ENV_KEYS


def scrub_pg_environment(
    base_env: dict[str, str] | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Build a minimal clean connection env from scratch (never inherit PG routing).

    Returns ``(clean_env, dropped_env_keys)``.  Only ``ENV_ALLOWLIST`` keys are
    carried over from ``base_env``; every ambient ``PG*`` routing key is dropped.
    ``PGSYSCONFDIR`` is re-pointed at an empty isolation dir and ``PGSERVICEFILE``
    /``PGPASSFILE`` at non-existent files inside it, neutralizing system/user
    ``psqlrc``, ``pg_service.conf`` and (because ``HOME`` is preserved)
    ``~/.pgpass``.
    """

    source = dict(os.environ if base_env is None else base_env)
    clean = {key: source[key] for key in ENV_ALLOWLIST if key in source}
    isolation = _psqlrc_isolation_dir()
    # 正向隔離:即使來源沒有這些鍵,也主動指向空/不存在路徑。PGPASSFILE 必須顯式改寫,
    # 否則 libpq 會因 HOME 仍在而回退讀取 ~/.pgpass。
    clean["PGSYSCONFDIR"] = isolation
    clean["PGSERVICEFILE"] = os.path.join(isolation, "aiml_absent_pg_service.conf")
    clean["PGPASSFILE"] = os.path.join(isolation, "aiml_absent.pgpass")
    dropped = sorted(key for key in source if _is_pg_env_key(key))
    return clean, dropped


def ambient_routing_scrubbed_record(
    base_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the receipt's ``ambient_routing_scrubbed`` evidence block."""

    _clean, dropped = scrub_pg_environment(base_env)
    return {
        "dropped_env_keys": dropped,
        "psqlrc_neutralized": True,
        "service_file_neutralized": True,
        "pgsysconfdir_isolated": True,
        "effective_env_has_no_pg_routing": True,
    }


# --------------------------------------------------------------------------- #
# endpoint / connection params
# --------------------------------------------------------------------------- #
def _normalize_endpoint(
    *,
    endpoint_class: str,
    socket_dir: str | None,
    loopback_host: str | None,
    port: int | None,
) -> dict[str, Any]:
    # socket-only 或 authenticated loopback,其他 host 形態一律 fail-closed。
    if endpoint_class not in ENDPOINT_CLASSES:
        raise ValueError(f"endpoint_class is not allowlisted: {endpoint_class!r}")
    if isinstance(port, bool) or (port is not None and not isinstance(port, int)):
        raise ValueError("port must be an integer or null")
    if port is not None and not (1 <= port <= 65535):
        raise ValueError("port is outside the valid range")
    if endpoint_class == "unix_socket_allowlisted":
        if not isinstance(socket_dir, str) or not socket_dir.startswith("/"):
            raise ValueError("unix socket endpoint requires an absolute socket_dir")
        if loopback_host is not None:
            raise ValueError("unix socket endpoint cannot carry a loopback_host")
    else:  # authenticated_loopback
        if loopback_host not in LOOPBACK_HOSTS:
            raise ValueError("loopback endpoint requires host 127.0.0.1 or ::1")
        if socket_dir is not None:
            raise ValueError("loopback endpoint cannot carry a socket_dir")
        if not isinstance(port, int):
            raise ValueError("loopback endpoint requires an explicit port")
    return {
        "endpoint_class": endpoint_class,
        "socket_dir": socket_dir,
        "loopback_host": loopback_host,
        "port": port,
        "allowlisted": True,
    }


def build_readonly_connection_params(
    *,
    endpoint_class: str,
    database: str,
    role: str,
    socket_dir: str | None = None,
    loopback_host: str | None = None,
    port: int | None = None,
    base_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Assemble psycopg2 connect kwargs enforcing socket-only/authenticated loopback.

    Pins ``default_transaction_read_only=on`` + ``search_path=pg_catalog`` at the
    connection and carries the scrubbed clean env.  Any other host form is
    rejected fail-closed by ``_normalize_endpoint``.
    """

    if not isinstance(database, str) or not database:
        raise ValueError("database is required")
    if not isinstance(role, str) or not role:
        raise ValueError("role is required")
    endpoint = _normalize_endpoint(
        endpoint_class=endpoint_class,
        socket_dir=socket_dir,
        loopback_host=loopback_host,
        port=port,
    )
    clean_env, dropped = scrub_pg_environment(base_env)
    host = socket_dir if endpoint_class == "unix_socket_allowlisted" else loopback_host
    connect_kwargs: dict[str, Any] = {
        "host": host,
        "dbname": database,
        "user": role,
        "options": READONLY_CONNECTION_OPTIONS,
        "connect_timeout": 10,
    }
    if port is not None:
        connect_kwargs["port"] = port
    return {
        "endpoint_class": endpoint_class,
        "socket_dir": socket_dir,
        "loopback_host": loopback_host,
        "port": port,
        "database": database,
        "role": role,
        "endpoint": endpoint,
        "connect_kwargs": connect_kwargs,
        "clean_env": clean_env,
        "dropped_env_keys": dropped,
    }


def redact_connection_fingerprint(params: dict[str, Any]) -> dict[str, Any]:
    """Emit a non-secret endpoint fingerprint; never copies password/DSN secrets."""

    # 只白名單這些非機密欄位;即使 params 帶有 password/dsn 也不會被帶出。
    return {
        "endpoint_class": params.get("endpoint_class"),
        "socket_dir": params.get("socket_dir"),
        "loopback_host": params.get("loopback_host"),
        "port": params.get("port"),
        "database": params.get("database"),
        "role": params.get("role"),
    }


# --------------------------------------------------------------------------- #
# secret scan
# --------------------------------------------------------------------------- #
def _contains_secret_like(value: Any) -> bool:
    if isinstance(value, str):
        return PG_SECRET_LIKE_RE.search(value) is not None
    if isinstance(value, list):
        return any(_contains_secret_like(item) for item in value)
    if isinstance(value, dict):
        return any(
            _contains_secret_like(key) or _contains_secret_like(item)
            for key, item in value.items()
        )
    return False


def _guard_no_secret(payload: Any) -> None:
    # fail-closed:任何機密樣態即拒絕序列化,絕不發出帶密的 receipt。
    if _contains_secret_like(payload):
        raise SecretLeakageError("receipt payload carries secret-like content")


# --------------------------------------------------------------------------- #
# probe result contract + negative probes
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ProbeResult:
    """Structured outcome of one disposable read-only probe run."""

    role_name: str
    role_attributes: dict[str, bool]
    server_version: str
    session_read_only: str
    session_search_path: str
    ambient_routing_scrubbed: dict[str, Any]
    queries: list[dict[str, Any]] = field(default_factory=list)
    write_denied: dict[str, Any] = field(default_factory=dict)
    role_escalation_denied: dict[str, Any] = field(default_factory=dict)
    search_path_pinned: dict[str, Any] = field(default_factory=dict)


def _observe_denial(cur, sql: str) -> str:
    # 執行預期會被拒絕的敘述;回傳觀察到的 SQLSTATE,未被拒則視為致命(refuse)。
    try:
        cur.execute(sql)
    except Exception as exc:  # psycopg2.Error 帶 pgcode  # noqa: BLE001
        pgcode = getattr(exc, "pgcode", None)
        if pgcode is None:
            raise
        _rollback_quietly(cur)
        return str(pgcode)
    _rollback_quietly(cur)
    raise ReadOnlyProbeError(f"expected denial but statement succeeded: {sql}")


def _rollback_quietly(cur) -> None:
    connection = getattr(cur, "connection", None)
    if connection is not None:
        try:
            connection.rollback()
        except Exception:  # pragma: no cover - rollback best effort  # noqa: BLE001
            pass


def probe_write_denied(cur) -> dict[str, Any]:
    """Attempt a write; require a denial-class SQLSTATE."""

    attempted = "CREATE TEMP TABLE _aiml_ro_write_probe (probe integer)"
    return {
        "attempted": attempted,
        "expected_denial": True,
        "observed_sqlstate": _observe_denial(cur, attempted),
        "verdict": "DENIED",
    }


def probe_role_escalation_denied(cur, *, target_role: str) -> dict[str, Any]:
    """Attempt ``SET ROLE`` to a writer/superuser; require a denial-class SQLSTATE."""

    # target_role 由 fixture 指定,經 quote_ident 風格處理避免注入。
    safe_role = '"' + str(target_role).replace('"', '""') + '"'
    attempted = f"SET ROLE {safe_role}"
    return {
        "attempted": attempted,
        "expected_denial": True,
        "observed_sqlstate": _observe_denial(cur, attempted),
        "verdict": "DENIED",
    }


def probe_search_path_pinned(cur) -> dict[str, Any]:
    """Attempt a persistent search-path hijack; require a real read-only-txn DENIAL.

    ``ALTER ROLE current_user SET search_path`` 從不改變「當前 session」,故僅檢查
    effective==pg_catalog 只是驗證連線層的 pin,證明不了持久劫持被擋。此探針因此要求
    觀察到真正的拒絕:該 ALTER 會寫 catalog(pg_db_role_setting),於唯讀交易被拒
    (25006 read_only_sql_transaction)。``_observe_denial`` 在敘述未被拒時直接 raise,
    故 verdict 必為 DENIED 才會回傳。effective_search_path 仍一併記錄以佐證連線層 pin。
    """

    attempted = (
        "ALTER ROLE current_user SET search_path TO public, information_schema"
    )
    observed_sqlstate = _observe_denial(cur, attempted)
    cur.execute("SELECT current_setting('search_path')")
    effective = cur.fetchone()[0]
    return {
        "attempted": attempted,
        "effective_search_path": effective,
        "observed_sqlstate": observed_sqlstate,
        "pinned": True,
        "verdict": "DENIED",
    }


def run_readonly_probe(
    conn_params: dict[str, Any],
    *,
    escalation_target_role: str,
    base_env: dict[str, str] | None = None,
) -> ProbeResult:  # pragma: no cover - driven only by the disposable-cluster fixture
    """Open the RO connection with psycopg2, run the allowlist + three negatives.

    Never shells out to ``psql``.  The live branch is exercised only by the
    ``initdb``-gated disposable-cluster test; where PG binaries are absent that
    test skips, so this path stays uncovered in server-less CI.
    """

    import psycopg2  # 延遲匯入,讓 structural 測試無需驅動即可載入本模組。

    clean_env = conn_params["clean_env"]
    connect_kwargs = conn_params["connect_kwargs"]
    previous_env = dict(os.environ)
    try:
        # 連線期間以 clean env 取代 os.environ,確保 libpq 讀不到 ambient PG* 路由。
        os.environ.clear()
        os.environ.update(clean_env)
        connection = psycopg2.connect(**connect_kwargs)
    finally:
        os.environ.clear()
        os.environ.update(previous_env)

    try:
        connection.autocommit = True
        cur = connection.cursor()

        role_rows = _run_allowlisted(cur, "pg_role_attributes_v1")
        session_rows = _run_allowlisted(cur, "pg_session_readonly_state_v1")
        version_rows = _run_allowlisted(cur, "pg_server_version_v1")

        role_row = role_rows[0]
        role_attributes = {
            "rolsuper": bool(role_row[1]),
            "rolcreaterole": bool(role_row[2]),
            "rolcreatedb": bool(role_row[3]),
            "rolcanlogin": bool(role_row[4]),
            "rolreplication": bool(role_row[5]),
            "rolbypassrls": bool(role_row[6]),
        }
        session_read_only, session_search_path, _user = session_rows[0]
        server_version = _parse_server_version(version_rows[0][0])

        queries = [
            build_query_record("pg_role_attributes_v1", role_rows),
            build_query_record("pg_session_readonly_state_v1", session_rows),
            build_query_record("pg_server_version_v1", version_rows),
        ]
        return ProbeResult(
            role_name=str(role_row[0]),
            role_attributes=role_attributes,
            server_version=server_version,
            session_read_only=str(session_read_only),
            session_search_path=str(session_search_path),
            ambient_routing_scrubbed=ambient_routing_scrubbed_record(base_env),
            queries=queries,
            write_denied=probe_write_denied(cur),
            role_escalation_denied=probe_role_escalation_denied(
                cur, target_role=escalation_target_role
            ),
            search_path_pinned=probe_search_path_pinned(cur),
        )
    finally:
        connection.close()


def _run_allowlisted(cur, query_id: str) -> list:  # pragma: no cover - live path
    cur.execute(resolve_allowed_query(query_id))
    return [list(row) for row in cur.fetchall()]


def _parse_server_version(version_text: str) -> str:  # pragma: no cover - live path
    match = re.search(r"PostgreSQL (\d+(?:\.\d+)?)", str(version_text))
    return match.group(1) if match else str(version_text).split()[0]


# --------------------------------------------------------------------------- #
# receipt builder
# --------------------------------------------------------------------------- #
def _validate_platform(platform: Any) -> dict[str, Any]:
    if (
        not isinstance(platform, dict)
        or platform.get("os") not in PLATFORM_OS
        or not isinstance(platform.get("arch"), str)
        or not platform.get("arch")
        or not isinstance(platform.get("postgres_version"), str)
        or not platform.get("postgres_version")
    ):
        raise ValueError("platform must bind os(darwin|linux)/arch/postgres_version")
    return {
        "os": platform["os"],
        "arch": platform["arch"],
        "postgres_version": platform["postgres_version"],
    }


def _negative_case(record: Any, *, kind: str) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ReadOnlyProbeError(f"{kind} probe record is missing")
    if kind == "search_path_pinned":
        verdict = record.get("verdict")
        effective = record.get("effective_search_path")
        sqlstate = str(record.get("observed_sqlstate", ""))
        # 持久劫持必須觀察到真正的拒絕(DENIED + denial-class SQLSTATE);舊的
        # PINNED-可接受路徑證明不了持久劫持被擋,已移除。
        if verdict != "DENIED" or sqlstate not in DENIAL_SQLSTATES:
            raise ReadOnlyProbeError(
                "search_path probe did not observe a denial-class SQLSTATE"
            )
        if not isinstance(effective, str) or not effective:
            raise ReadOnlyProbeError("search_path probe lacks an effective value")
        return {
            "attempted": str(record.get("attempted", "")),
            "effective_search_path": effective,
            "observed_sqlstate": sqlstate,
            "pinned": True,
            "verdict": "DENIED",
        }
    sqlstate = str(record.get("observed_sqlstate", ""))
    if record.get("verdict") != "DENIED" or sqlstate not in DENIAL_SQLSTATES:
        raise ReadOnlyProbeError(f"{kind} probe did not observe a denial-class SQLSTATE")
    return {
        "attempted": str(record.get("attempted", "")),
        "expected_denial": True,
        "observed_sqlstate": sqlstate,
        "verdict": "DENIED",
    }


def build_pg_readonly_identity_receipt(
    *,
    caller: str,
    platform: dict[str, Any],
    endpoint: dict[str, Any],
    database: str,
    role: str,
    target_class: str,
    probe_result: ProbeResult,
    observation_time: str,
    ttl_seconds: int,
    evidence_class: str,
) -> dict[str, Any]:
    """Build the canonical, self-hashed ``pg_readonly_identity_receipt_v1``.

    ``status="PASS"`` iff ALL hold: ``target_class==disposable_local``;
    ``evidence_class==LOCAL_REPRODUCIBLE``; every forbidden role attribute is
    false and the role can log in; every allowlisted query executed; the session
    ``transaction_read_only`` is ``on``; the write probe was denied with
    ``25006`` (read_only_sql_transaction, NOT a mere ``42501`` privilege denial);
    the persistent ``search_path`` hijack was DENIED with ``25006``; and the
    effective search_path is pinned to ``pg_catalog``.  Integrity/environment
    violations that cannot be safely serialized (secret detected, a negative
    probe that did not observe its denial, non-allowlisted endpoint, ttl out of
    ``[1, 3600]``) raise instead of emitting a receipt.  Otherwise
    ``status="FAIL"`` with a non-empty ``failure_reason``.
    """

    if not isinstance(caller, str) or not caller:
        raise ValueError("caller is required")
    if not isinstance(database, str) or not database:
        raise ValueError("database is required")
    if not isinstance(role, str) or not role:
        raise ValueError("role is required")
    if target_class not in TARGET_CLASSES:
        raise ValueError(f"target_class is not recognized: {target_class!r}")
    if evidence_class not in EVIDENCE_CLASSES:
        raise ValueError(f"evidence_class is not recognized: {evidence_class!r}")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
        raise ValueError("ttl_seconds must be an integer")
    if not (1 <= ttl_seconds <= TTL_CEILING_SECONDS):
        raise ValueError(f"ttl_seconds must be within [1, {TTL_CEILING_SECONDS}]")
    if not isinstance(probe_result, ProbeResult):
        raise ValueError("probe_result must be a ProbeResult")
    if probe_result.role_name != role:
        raise ValueError("probe_result role does not match the requested role")

    platform_block = _validate_platform(platform)
    observed = _parse_time(observation_time)
    expires = observed + timedelta(seconds=ttl_seconds)

    endpoint_block = _normalize_endpoint(
        endpoint_class=endpoint.get("endpoint_class"),
        socket_dir=endpoint.get("socket_dir"),
        loopback_host=endpoint.get("loopback_host"),
        port=endpoint.get("port"),
    )
    ambient = _ambient_block(probe_result.ambient_routing_scrubbed)

    # 三個 negative probe:若未觀察到必需的拒絕/釘住即 raise(不可序列化)。
    negative_cases = {
        "write_denied": _negative_case(probe_result.write_denied, kind="write_denied"),
        "role_escalation_denied": _negative_case(
            probe_result.role_escalation_denied, kind="role_escalation_denied"
        ),
        "search_path_pinned": _negative_case(
            probe_result.search_path_pinned, kind="search_path_pinned"
        ),
    }

    query_records = _normalize_queries(probe_result.queries)
    result_digest = _overall_result_digest(query_records)

    attributes = {key: bool(probe_result.role_attributes.get(key)) for key in ROLE_ATTR_KEYS}
    forbidden_true = [attr for attr in FORBIDDEN_ROLE_ATTRS if attributes[attr]]
    is_read_only = not forbidden_true and attributes["rolcanlogin"]
    # session 的 transaction_read_only 必為 on 才算真正被連線層釘住(不僅 search_path)。
    session_read_only = str(probe_result.session_read_only)

    reasons: list[str] = []
    if target_class != S1_TARGET_CLASS:
        reasons.append("target_class is not disposable_local (S1.1 is disposable-only)")
    if evidence_class != "LOCAL_REPRODUCIBLE":
        reasons.append("evidence_class is not LOCAL_REPRODUCIBLE")
    if forbidden_true:
        reasons.append("role holds write-capable attributes: " + ",".join(forbidden_true))
    if not attributes["rolcanlogin"]:
        reasons.append("dedicated read-only role must be able to log in")
    executed = {record["query_id"] for record in query_records}
    if executed != set(ALLOWED_QUERIES):
        reasons.append("not every allowlisted query executed")
    if session_read_only != "on":
        reasons.append("session transaction_read_only is not on")
    # 寫入拒絕必須是唯讀交易碼(25006),不接受純權限碼(42501)充當唯讀證明。
    if negative_cases["write_denied"]["observed_sqlstate"] != "25006":
        reasons.append("write denial is not a read_only_sql_transaction (25006)")
    # 持久 search_path 劫持必須被真正拒絕(DENIED),且為唯讀交易碼(25006)。
    if negative_cases["search_path_pinned"]["verdict"] != "DENIED":
        reasons.append("persistent search_path hijack was not denied")
    if negative_cases["search_path_pinned"]["observed_sqlstate"] != "25006":
        reasons.append("search_path denial is not a read_only_sql_transaction (25006)")
    if negative_cases["search_path_pinned"]["effective_search_path"] != PINNED_SEARCH_PATH:
        reasons.append("effective search_path is not pinned to pg_catalog")

    status = "PASS" if not reasons else "FAIL"
    failure_reason = None if status == "PASS" else "; ".join(reasons)

    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "adapter_id": ADAPTER_ID,
        "status": status,
        "caller": caller,
        "platform": platform_block,
        "target_class": target_class,
        "evidence_class": evidence_class,
        "endpoint": endpoint_block,
        "database": database,
        "role": {
            "name": role,
            "attributes": attributes,
            "is_read_only": is_read_only,
        },
        "session_read_only": session_read_only,
        "ambient_routing_scrubbed": ambient,
        "queries": query_records,
        "result_digest": result_digest,
        "negative_cases": negative_cases,
        "source_sha256": source_sha256(),
        "schema_sha256": schema_sha256(),
        "secret_scan": {
            "patterns_checked": list(SECRET_PATTERNS_CHECKED),
            "leaked": False,
        },
        "observation_time": observed.isoformat(),
        "expires_at": expires.isoformat(),
        "ttl_seconds": ttl_seconds,
        "failure_reason": failure_reason,
    }
    # 在計算 self_digest 前掃描整個 receipt(排除 secret_scan/self_digest 自身)。
    _guard_no_secret({k: v for k, v in receipt.items() if k != "secret_scan"})
    receipt["self_digest"] = receipt_digest(receipt)
    return receipt


def _ambient_block(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("ambient_routing_scrubbed evidence is required")
    dropped = record.get("dropped_env_keys")
    if not isinstance(dropped, list) or any(not isinstance(k, str) for k in dropped):
        raise ValueError("ambient_routing_scrubbed dropped_env_keys is invalid")
    for flag in (
        "psqlrc_neutralized",
        "service_file_neutralized",
        "pgsysconfdir_isolated",
        "effective_env_has_no_pg_routing",
    ):
        if record.get(flag) is not True:
            raise ValueError(f"ambient_routing_scrubbed.{flag} must be true")
    return {
        "dropped_env_keys": sorted(dropped),
        "psqlrc_neutralized": True,
        "service_file_neutralized": True,
        "pgsysconfdir_isolated": True,
        "effective_env_has_no_pg_routing": True,
    }


def _normalize_queries(queries: Any) -> list[dict[str, Any]]:
    if not isinstance(queries, list) or not queries:
        raise ValueError("probe_result.queries must be a non-empty list")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in queries:
        if not isinstance(record, dict):
            raise ValueError("query record must be an object")
        query_id = record.get("query_id")
        if query_id not in ALLOWED_QUERIES:
            raise ValueError(f"query record is not allowlisted: {query_id!r}")
        if query_id in seen:
            raise ValueError(f"duplicate query record: {query_id!r}")
        seen.add(query_id)
        # query_sha256 必須等於 allowlist 精確 SQL 的雜湊,不接受外部塞入的雜湊。
        if record.get("query_sha256") != allowed_query_digest(query_id):
            raise ValueError(f"query_sha256 does not bind the allowlisted SQL: {query_id}")
        row_count = record.get("row_count")
        if isinstance(row_count, bool) or not isinstance(row_count, int) or row_count < 0:
            raise ValueError("query record row_count is invalid")
        if not DIGEST_RE.fullmatch(str(record.get("result_digest", ""))):
            raise ValueError("query record result_digest is invalid")
        records.append({
            "query_id": query_id,
            "query_sha256": record["query_sha256"],
            "row_count": row_count,
            "result_digest": record["result_digest"],
        })
    return records


# --------------------------------------------------------------------------- #
# receipt validator (structural + integrity; not execution authenticity)
# --------------------------------------------------------------------------- #
def validate_pg_readonly_identity_receipt(
    receipt: Any,
    *,
    require_success: bool = False,
    now: str | None = None,
) -> list[str]:
    """Validate receipt structure/integrity and the S1.1 disposable-only gate.

    Mirrors ``validate_effect_receipt``: schema subset, exact field-set, const
    identity, digest regexes, allowlist binding, RO-role facts, session
    read-only pin, three genuine negative denial records, secret-free
    serialization, TTL/time ordering and ``self_digest`` re-derivation.
    ``target_class`` must be ``disposable_local`` at the S1.1 gate;
    ``production`` is rejected fail-closed.

    Internal temporal consistency (``observation_time < expires_at``,
    ``expires_at == observation_time + ttl``, ttl within ``[1, 3600]``) is
    ALWAYS enforced.  Freshness (``observation_time <= now < expires_at``) is
    only checked when ``now`` is supplied; consumers such as the S1.2 central
    validator MUST pass ``now`` so an expired receipt is rejected.
    """

    if not isinstance(receipt, dict):
        return ["pg readonly identity receipt must be an object"]
    schema = _receipt_schema()
    errors = [
        f"pg readonly identity receipt schema violation: {error}"
        for error in schema_subset_errors(receipt, schema, schema)
    ]
    if set(receipt) != RECEIPT_FIELDS:
        errors.append(
            "pg readonly identity receipt fields mismatch: "
            f"missing={sorted(RECEIPT_FIELDS - set(receipt))} "
            f"extra={sorted(set(receipt) - RECEIPT_FIELDS)}"
        )
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        errors.append("pg readonly identity receipt schema_version is invalid")
    if receipt.get("adapter_id") != ADAPTER_ID:
        errors.append("pg readonly identity receipt adapter_id is invalid")
    if receipt.get("status") not in {"PASS", "FAIL"}:
        errors.append("pg readonly identity receipt status is invalid")
    if receipt.get("target_class") != S1_TARGET_CLASS:
        errors.append(
            "pg readonly identity receipt target_class must be disposable_local "
            "(production is rejected at the S1.1 gate)"
        )
    for field_name in ("source_sha256", "schema_sha256", "result_digest", "self_digest"):
        if not DIGEST_RE.fullmatch(str(receipt.get(field_name, ""))):
            errors.append(f"pg readonly identity receipt {field_name} is invalid")
    # source/schema digests 必須綁定當前模組與 schema 位元(可獨立重算)。
    if receipt.get("source_sha256") != source_sha256():
        errors.append("pg readonly identity receipt source_sha256 does not bind this module")
    if receipt.get("schema_sha256") != schema_sha256():
        errors.append("pg readonly identity receipt schema_sha256 does not bind the schema")

    errors.extend(_validate_queries(receipt.get("queries")))
    errors.extend(_validate_role(receipt.get("role")))
    errors.extend(_validate_negative_cases(receipt.get("negative_cases")))
    errors.extend(_validate_ambient(receipt.get("ambient_routing_scrubbed")))
    errors.extend(_validate_secret_scan(receipt))
    errors.extend(_validate_times(receipt, now=now))

    session_read_only = receipt.get("session_read_only")
    if session_read_only not in {"on", "off"}:
        errors.append("pg readonly identity receipt session_read_only must be on or off")

    status = receipt.get("status")
    failure_reason = receipt.get("failure_reason")
    if status == "PASS":
        if receipt.get("evidence_class") != "LOCAL_REPRODUCIBLE":
            errors.append("PASS receipt requires evidence_class LOCAL_REPRODUCIBLE")
        if failure_reason is not None:
            errors.append("PASS receipt cannot carry a failure_reason")
        role = receipt.get("role")
        if isinstance(role, dict) and role.get("is_read_only") is not True:
            errors.append("PASS receipt requires a read-only role")
        # PASS 必須真正證明唯讀 pin:session 唯讀、寫入拒絕碼與持久 search_path 劫持
        # 拒絕碼皆為 25006(read_only_sql_transaction),而非僅權限碼 42501。
        if session_read_only != "on":
            errors.append("PASS receipt requires session_read_only to be on")
        negative = receipt.get("negative_cases")
        if isinstance(negative, dict):
            write_case = negative.get("write_denied")
            if isinstance(write_case, dict) and write_case.get("observed_sqlstate") != "25006":
                errors.append(
                    "PASS receipt requires write denial SQLSTATE 25006 (read_only_sql_transaction)"
                )
            search_case = negative.get("search_path_pinned")
            if isinstance(search_case, dict):
                if search_case.get("verdict") != "DENIED":
                    errors.append("PASS receipt requires search_path verdict DENIED")
                if search_case.get("observed_sqlstate") != "25006":
                    errors.append("PASS receipt requires search_path denial SQLSTATE 25006")
    else:
        if not isinstance(failure_reason, str) or not failure_reason.strip():
            errors.append("FAIL receipt requires a non-empty failure_reason")

    # result_digest 必須等於以 queries 重算的正規雜湊(可獨立重算)。
    queries = receipt.get("queries")
    if isinstance(queries, list) and all(isinstance(record, dict) for record in queries):
        try:
            recomputed = _overall_result_digest(queries)
        except (KeyError, TypeError, ValueError):
            recomputed = None
        if recomputed is not None and receipt.get("result_digest") != recomputed:
            errors.append("pg readonly identity result_digest does not bind the query results")

    if require_success and status != "PASS":
        errors.append("pg readonly identity receipt does not prove a passing identity")
    if receipt.get("self_digest") != receipt_digest(receipt):
        errors.append("pg readonly identity receipt self_digest does not match canonical receipt")
    return errors


def _validate_queries(queries: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(queries, list) or not queries:
        return ["pg readonly identity receipt queries are missing"]
    seen: set[str] = set()
    for record in queries:
        if not isinstance(record, dict):
            errors.append("pg readonly identity query record is invalid")
            continue
        query_id = record.get("query_id")
        if query_id not in ALLOWED_QUERIES:
            errors.append(f"pg readonly identity query is not allowlisted: {query_id!r}")
            continue
        if query_id in seen:
            errors.append(f"pg readonly identity duplicate query record: {query_id}")
        seen.add(query_id)
        if record.get("query_sha256") != allowed_query_digest(query_id):
            errors.append(f"pg readonly identity query_sha256 mismatch: {query_id}")
    if seen != set(ALLOWED_QUERIES):
        errors.append("pg readonly identity receipt did not execute the full allowlist")
    return errors


def _validate_role(role: Any) -> list[str]:
    if not isinstance(role, dict):
        return ["pg readonly identity receipt role is invalid"]
    errors: list[str] = []
    attributes = role.get("attributes")
    if not isinstance(attributes, dict):
        return ["pg readonly identity receipt role attributes are invalid"]
    forbidden_true = [
        attr for attr in FORBIDDEN_ROLE_ATTRS if attributes.get(attr) is True
    ]
    if forbidden_true:
        errors.append(
            "pg readonly identity role holds write-capable attributes: "
            + ",".join(sorted(forbidden_true))
        )
    if attributes.get("rolcanlogin") is not True:
        errors.append("pg readonly identity role must be able to log in")
    expected_read_only = not forbidden_true and attributes.get("rolcanlogin") is True
    if role.get("is_read_only") is not expected_read_only:
        errors.append("pg readonly identity role is_read_only is inconsistent with attributes")
    return errors


def _validate_negative_cases(negative_cases: Any) -> list[str]:
    if not isinstance(negative_cases, dict):
        return ["pg readonly identity receipt negative_cases are missing"]
    errors: list[str] = []
    for kind in ("write_denied", "role_escalation_denied"):
        record = negative_cases.get(kind)
        if not isinstance(record, dict):
            errors.append(f"pg readonly identity {kind} record is missing")
            continue
        if record.get("verdict") != "DENIED":
            errors.append(f"pg readonly identity {kind} verdict must be DENIED")
        sqlstate = str(record.get("observed_sqlstate", ""))
        if not SQLSTATE_RE.fullmatch(sqlstate) or sqlstate not in DENIAL_SQLSTATES:
            errors.append(f"pg readonly identity {kind} SQLSTATE is not denial-class")
        if record.get("expected_denial") is not True:
            errors.append(f"pg readonly identity {kind} must expect a denial")
    search_path = negative_cases.get("search_path_pinned")
    if not isinstance(search_path, dict):
        errors.append("pg readonly identity search_path_pinned record is missing")
    else:
        if search_path.get("verdict") != "DENIED":
            errors.append("pg readonly identity search_path verdict must be DENIED")
        sp_sqlstate = str(search_path.get("observed_sqlstate", ""))
        if not SQLSTATE_RE.fullmatch(sp_sqlstate) or sp_sqlstate not in DENIAL_SQLSTATES:
            errors.append("pg readonly identity search_path SQLSTATE is not denial-class")
        if search_path.get("pinned") is not True:
            errors.append("pg readonly identity search_path must be pinned")
        if search_path.get("effective_search_path") != PINNED_SEARCH_PATH:
            errors.append("pg readonly identity effective search_path is not pg_catalog")
    return errors


def _validate_ambient(ambient: Any) -> list[str]:
    if not isinstance(ambient, dict):
        return ["pg readonly identity receipt ambient_routing_scrubbed is missing"]
    errors: list[str] = []
    for flag in (
        "psqlrc_neutralized",
        "service_file_neutralized",
        "pgsysconfdir_isolated",
        "effective_env_has_no_pg_routing",
    ):
        if ambient.get(flag) is not True:
            errors.append(f"pg readonly identity ambient_routing_scrubbed.{flag} must be true")
    dropped = ambient.get("dropped_env_keys")
    if not isinstance(dropped, list) or dropped != sorted(dropped):
        errors.append("pg readonly identity dropped_env_keys must be sorted")
    return errors


def _validate_secret_scan(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    secret_scan = receipt.get("secret_scan")
    if not isinstance(secret_scan, dict):
        return ["pg readonly identity receipt secret_scan is missing"]
    if secret_scan.get("leaked") is not False:
        errors.append("pg readonly identity secret_scan must report leaked=false")
    if list(secret_scan.get("patterns_checked", [])) != list(SECRET_PATTERNS_CHECKED):
        errors.append("pg readonly identity secret_scan patterns are not the exact contract")
    # 對整份 receipt(排除 secret_scan)重掃一次,任何機密殘留即報錯(防禦內建)。
    if _contains_secret_like({k: v for k, v in receipt.items() if k != "secret_scan"}):
        errors.append("pg readonly identity receipt carries secret-like content")
    return errors


def _validate_times(receipt: dict[str, Any], *, now: str | None) -> list[str]:
    errors: list[str] = []
    ttl_seconds = receipt.get("ttl_seconds")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
        return ["pg readonly identity receipt ttl_seconds is invalid"]
    if not (1 <= ttl_seconds <= TTL_CEILING_SECONDS):
        errors.append(f"pg readonly identity ttl_seconds must be within [1, {TTL_CEILING_SECONDS}]")
    try:
        observed = _parse_time(str(receipt.get("observation_time", "")))
        expires = _parse_time(str(receipt.get("expires_at", "")))
        if expires != observed + timedelta(seconds=ttl_seconds):
            errors.append("pg readonly identity expires_at does not equal observation_time + ttl")
        if not observed < expires:
            errors.append("pg readonly identity observation_time must precede expires_at")
        if now is not None:
            current = _parse_time(now)
            if not observed <= current < expires:
                errors.append("pg readonly identity receipt is not fresh")
    except (TypeError, ValueError):
        errors.append("pg readonly identity receipt timestamps are invalid")
    return errors
