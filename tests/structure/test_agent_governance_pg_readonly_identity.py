"""Hermetic structural tests for the LR0A PG read-only identity Adapter (S1.1).

No PostgreSQL server is started here; these exercise scrubbing, the SQL
allowlist, secret redaction, the builder/validator roundtrip and the fail-closed
rejections (production target, write-capable role, ttl bound, tamper). The real
denial SQLSTATEs are proven separately in the ``_disposable`` module.
"""

from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

import agent_governance_pg_readonly_identity as adapter  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402


SCHEMA_PATH = (
    ROOT
    / "program_code/ml_training/schemas/aiml_gate_receipts"
    / "pg_readonly_identity_receipt_v1.schema.json"
)
OBS = datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc).isoformat()
NOW = (datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=5)).isoformat()


def _clean_probe_result(**attr_overrides) -> adapter.ProbeResult:
    attrs = {
        "rolsuper": False,
        "rolcreaterole": False,
        "rolcreatedb": False,
        "rolcanlogin": True,
        "rolreplication": False,
        "rolbypassrls": False,
    }
    attrs.update(attr_overrides)
    role_rows = [[
        "aiml_ro",
        attrs["rolsuper"],
        attrs["rolcreaterole"],
        attrs["rolcreatedb"],
        attrs["rolcanlogin"],
        attrs["rolreplication"],
        attrs["rolbypassrls"],
    ]]
    session_rows = [["on", "pg_catalog", "aiml_ro"]]
    version_rows = [["PostgreSQL 16.14 (Homebrew)"]]
    queries = [
        adapter.build_query_record("pg_role_attributes_v1", role_rows),
        adapter.build_query_record("pg_session_readonly_state_v1", session_rows),
        adapter.build_query_record("pg_server_version_v1", version_rows),
    ]
    return adapter.ProbeResult(
        role_name="aiml_ro",
        role_attributes=attrs,
        server_version="16.14",
        session_read_only="on",
        session_search_path="pg_catalog",
        ambient_routing_scrubbed=adapter.ambient_routing_scrubbed_record(
            {"PGHOST": "h", "PGPASSWORD": "p", "PATH": "/bin"}
        ),
        queries=queries,
        write_denied={
            "attempted": "CREATE TEMP TABLE t(x int)",
            "expected_denial": True,
            "observed_sqlstate": "25006",
            "verdict": "DENIED",
        },
        role_escalation_denied={
            "attempted": 'SET ROLE "aiml_writer"',
            "expected_denial": True,
            "observed_sqlstate": "42501",
            "verdict": "DENIED",
        },
        search_path_pinned={
            "attempted": "ALTER ROLE current_user SET search_path TO public",
            "effective_search_path": "pg_catalog",
            "observed_sqlstate": "25006",
            "pinned": True,
            "verdict": "DENIED",
        },
    )


def _build(**overrides):
    params = dict(
        caller="E1:S1.1",
        platform={"os": "darwin", "arch": "arm64", "postgres_version": "16.14"},
        endpoint={
            "endpoint_class": "unix_socket_allowlisted",
            "socket_dir": "/tmp/aiml_sock",
            "loopback_host": None,
            "port": None,
        },
        database="postgres",
        role="aiml_ro",
        target_class="disposable_local",
        probe_result=_clean_probe_result(),
        observation_time=OBS,
        ttl_seconds=3600,
        evidence_class="LOCAL_REPRODUCIBLE",
    )
    params.update(overrides)
    return adapter.build_pg_readonly_identity_receipt(**params)


# --------------------------------------------------------------------------- #
# environment scrubbing
# --------------------------------------------------------------------------- #
def test_scrub_drops_every_pg_routing_key_but_keeps_allowlist():
    base = {
        "PGHOST": "prod-db",
        "PGHOSTADDR": "10.0.0.1",
        "PGPORT": "5432",
        "PGDATABASE": "prod",
        "PGUSER": "admin",
        "PGPASSWORD": "hunter2",
        "PGPASSFILE": "/root/.pgpass",
        "PGSERVICE": "prod-service",
        "PGSERVICEFILE": "/etc/pg_service.conf",
        "PGSYSCONFDIR": "/etc/postgresql",
        "PGOPTIONS": "-c search_path=evil",
        "PGSSLMODE": "require",
        "PGCLIENTENCODING": "LATIN1",
        "PGCONNECT_TIMEOUT": "1",
        "PATH": "/usr/bin",
        "HOME": "/home/agent",
    }
    clean, dropped = adapter.scrub_pg_environment(base)
    # 沒有任何路由鍵殘留(PGSYSCONFDIR/PGSERVICEFILE/PGPASSFILE 被以隔離值覆蓋,不指向 base)。
    routing = [
        "PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD",
        "PGSERVICE", "PGOPTIONS", "PGSSLMODE", "PGCLIENTENCODING",
        "PGCONNECT_TIMEOUT",
    ]
    assert all(key not in clean for key in routing)
    assert clean["PATH"] == "/usr/bin"
    assert clean["HOME"] == "/home/agent"
    # PGSYSCONFDIR/PGSERVICEFILE/PGPASSFILE 指向隔離空目錄內不存在的路徑,而非 base 的值。
    assert clean["PGSYSCONFDIR"] != "/etc/postgresql"
    assert clean["PGSERVICEFILE"] != "/etc/pg_service.conf"
    assert clean["PGSERVICEFILE"].startswith(clean["PGSYSCONFDIR"])
    assert not Path(clean["PGSERVICEFILE"]).exists()
    # PGPASSFILE 必須被顯式改寫進隔離目錄,否則 libpq 會因 HOME 仍在而回退讀 ~/.pgpass。
    assert clean["PGPASSFILE"] != "/root/.pgpass"
    assert clean["PGPASSFILE"].startswith(clean["PGSYSCONFDIR"])
    assert not Path(clean["PGPASSFILE"]).exists()
    assert "PGHOST" in dropped and "PGPASSWORD" in dropped and "PGPASSFILE" in dropped
    assert dropped == sorted(dropped)


def test_scrub_never_inherits_process_environment(monkeypatch):
    monkeypatch.setenv("PGHOST", "leaky-host")
    monkeypatch.setenv("PGPASSWORD", "leaky-secret")
    clean, dropped = adapter.scrub_pg_environment()
    assert "PGHOST" not in clean
    assert "PGPASSWORD" not in clean
    assert "PGHOST" in dropped and "PGPASSWORD" in dropped


def test_scrub_drops_non_enumerated_libpq_var():
    # 未列名的 PG* 變數(如 PGAPPNAME/PGCHANNELBINDING)也必須被 catch-all 掃掉。
    base = {"PGAPPNAME": "sneaky", "PGCHANNELBINDING": "require", "PATH": "/bin"}
    clean, dropped = adapter.scrub_pg_environment(base)
    assert "PGAPPNAME" not in clean
    assert "PGCHANNELBINDING" not in clean
    assert "PGAPPNAME" in dropped and "PGCHANNELBINDING" in dropped


def test_ambient_record_flags_are_all_true():
    record = adapter.ambient_routing_scrubbed_record({"PGHOST": "x", "PATH": "/bin"})
    assert record["psqlrc_neutralized"] is True
    assert record["service_file_neutralized"] is True
    assert record["pgsysconfdir_isolated"] is True
    assert record["effective_env_has_no_pg_routing"] is True
    assert record["dropped_env_keys"] == ["PGHOST"]


# --------------------------------------------------------------------------- #
# SQL allowlist (no free-text path)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("query_id", sorted(adapter.ALLOWED_QUERIES))
def test_resolve_allowed_query_returns_exact_catalog_sql(query_id):
    sql = adapter.resolve_allowed_query(query_id)
    assert sql == adapter.ALLOWED_QUERIES[query_id]
    # allowlist 全為 catalog/SELECT,不含任何寫入或 DDL。
    assert sql.upper().startswith("SELECT")


@pytest.mark.parametrize(
    "raw",
    [
        "DROP TABLE pg_roles",
        "SELECT 1",
        "pg_role_attributes_v1; DROP TABLE x",
        "unknown_query_id",
        "",
        None,
    ],
)
def test_resolve_allowed_query_rejects_raw_or_unknown_sql(raw):
    with pytest.raises(ValueError):
        adapter.resolve_allowed_query(raw)


def test_allowed_query_digest_binds_exact_text():
    for query_id, sql in adapter.ALLOWED_QUERIES.items():
        expected = adapter._sha256_bytes(sql.encode("utf-8"))
        assert adapter.allowed_query_digest(query_id) == expected


# --------------------------------------------------------------------------- #
# connection params (socket-only / authenticated loopback)
# --------------------------------------------------------------------------- #
def test_connection_params_accept_unix_socket():
    params = adapter.build_readonly_connection_params(
        endpoint_class="unix_socket_allowlisted",
        database="postgres",
        role="aiml_ro",
        socket_dir="/var/run/aiml_sock",
    )
    assert params["connect_kwargs"]["host"] == "/var/run/aiml_sock"
    assert (
        params["connect_kwargs"]["options"]
        == "-c default_transaction_read_only=on -c search_path=pg_catalog"
    )
    assert params["endpoint"]["allowlisted"] is True
    assert "PGHOST" not in params["clean_env"]


def test_authenticated_loopback_without_bound_auth_is_rejected():
    # FIX(P2):authenticated_loopback 未綁定認證方式即 fail-closed —— 不得對外宣稱 authenticated
    # 卻無任何 password/client-cert/credential-provider(scrub 已移除 PGPASSWORD/passfile)。
    with pytest.raises(ValueError, match="requires an explicitly bound auth_method"):
        adapter.build_readonly_connection_params(
            endpoint_class="authenticated_loopback",
            database="postgres", role="aiml_ro",
            loopback_host="127.0.0.1", port=5432,
        )
    # 綁定 auth_method 但缺 credential_provider 亦拒(無法真正供密)。
    with pytest.raises(ValueError, match="credential_provider"):
        adapter.build_readonly_connection_params(
            endpoint_class="authenticated_loopback",
            database="postgres", role="aiml_ro",
            loopback_host="127.0.0.1", port=5432, auth_method="scram-sha-256",
        )


def test_authenticated_loopback_with_bound_auth_keeps_secret_out_of_receipt():
    # 綁定 auth_method + credential-provider callable → 可選;密鑰只進 connect_kwargs(連線用),
    # 不進 auth_method 標籤 / redact fingerprint / 回傳 metadata。
    params = adapter.build_readonly_connection_params(
        endpoint_class="authenticated_loopback",
        database="postgres", role="aiml_ro",
        loopback_host="127.0.0.1", port=5432,
        auth_method="scram-sha-256",
        credential_provider=lambda: "loopback-secret-never-in-receipt",
    )
    assert params["connect_kwargs"]["host"] == "127.0.0.1"
    assert params["connect_kwargs"]["port"] == 5432
    assert params["connect_kwargs"]["password"] == "loopback-secret-never-in-receipt"
    assert params["auth_method"] == "scram-sha-256"
    fingerprint = adapter.redact_connection_fingerprint(params)
    assert "password" not in fingerprint
    assert "loopback-secret-never-in-receipt" not in json.dumps(fingerprint)


def test_env_mutation_window_is_serialized_across_threads():
    # FIX(P2):_connect_under_clean_env 以 module-level lock 序列化 os.environ 窗口。三條並行
    # 「探針」各帶不同 marker;critical section 內只應看見自己的 marker(無交錯污染),窗口結束後還原。
    import threading
    import time

    baseline_path = os.environ.get("PATH", "")
    seen: dict[str, str | None] = {}

    def _probe(tag: str) -> None:
        clean_env = {"AIML_PROBE_MARKER": tag, "PATH": baseline_path}

        def _connect() -> str | None:
            time.sleep(0.02)  # 拉長 critical section,無 lock 時極易交錯
            return os.environ.get("AIML_PROBE_MARKER")

        seen[tag] = adapter._connect_under_clean_env(clean_env, _connect)

    threads = [threading.Thread(target=_probe, args=(tag,)) for tag in ("A", "B", "C")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    # 每條探針在 critical section 內只看到自己的 marker(序列化 → 無交錯污染)。
    assert seen == {"A": "A", "B": "B", "C": "C"}
    # 窗口結束後 os.environ 一律還原:無殘留 marker、PATH 未被污染。
    assert "AIML_PROBE_MARKER" not in os.environ
    assert os.environ.get("PATH", "") == baseline_path


@pytest.mark.parametrize(
    "kwargs",
    [
        {"endpoint_class": "tcp_public", "socket_dir": "/s"},
        {"endpoint_class": "unix_socket_allowlisted", "socket_dir": "relative/path"},
        {"endpoint_class": "unix_socket_allowlisted", "loopback_host": "127.0.0.1"},
        {"endpoint_class": "authenticated_loopback", "loopback_host": "8.8.8.8", "port": 5432},
        {"endpoint_class": "authenticated_loopback", "loopback_host": "127.0.0.1"},
    ],
)
def test_connection_params_reject_non_allowlisted_endpoints(kwargs):
    with pytest.raises(ValueError):
        adapter.build_readonly_connection_params(
            database="postgres", role="aiml_ro", **kwargs
        )


# --------------------------------------------------------------------------- #
# secret redaction / scan
# --------------------------------------------------------------------------- #
def test_redact_fingerprint_never_carries_password_or_dsn():
    fingerprint = adapter.redact_connection_fingerprint({
        "endpoint_class": "unix_socket_allowlisted",
        "socket_dir": "/s",
        "database": "postgres",
        "role": "aiml_ro",
        "password": "topsecretpassword",
        # DSN 於 runtime 在 "@" 處拼接,避免公開倉庫 secret scanner 對測試夾具誤報(runtime 值不變)
        "dsn": "postgresql://u:topsecretpassword" + "@h:5432/db",
    })
    assert "password" not in fingerprint
    assert "dsn" not in fingerprint
    assert not adapter._contains_secret_like(fingerprint)


def test_builder_refuses_to_serialize_an_injected_secret():
    with pytest.raises(adapter.SecretLeakageError):
        _build(caller="PGPASSWORD=hunter2supersecret")


def test_builder_refuses_dsn_credentials_in_bound_field():
    with pytest.raises(adapter.SecretLeakageError):
        # 同上,DSN 於 runtime 在 "@" 處拼接以避開靜態 secret scanner 誤報
        _build(database="postgresql://user:realsecretpw" + "@host:5432/db")


def test_secret_guard_detects_github_token_family():
    # GitHub token 形態(github_pat_ / ghp_ 等)必須被機密守衛偵測。
    assert adapter._contains_secret_like("github_pat_" + "A" * 22)
    assert adapter._contains_secret_like("ghp_" + "B" * 20)
    with pytest.raises(adapter.SecretLeakageError):
        _build(caller="ghp_" + "C" * 20)


def test_secret_guard_detects_auth_header_family():
    # Authorization header(Bearer / Basic)形態必須被機密守衛偵測。
    assert adapter._contains_secret_like("Bearer abcdef0123456789xyz")
    assert adapter._contains_secret_like("Basic dXNlcjpwYXNzd29yZA==")
    with pytest.raises(adapter.SecretLeakageError):
        _build(caller="authorization: Bearer abcdef0123456789xyz")


# --------------------------------------------------------------------------- #
# builder -> validator PASS roundtrip
# --------------------------------------------------------------------------- #
def test_pass_receipt_roundtrips_through_validator_and_schema():
    receipt = _build()
    assert receipt["status"] == "PASS"
    assert receipt["target_class"] == "disposable_local"
    assert receipt["evidence_class"] == "LOCAL_REPRODUCIBLE"
    assert receipt["failure_reason"] is None
    assert set(receipt) == adapter.RECEIPT_FIELDS
    assert adapter.validate_pg_readonly_identity_receipt(
        receipt, require_success=True, now=NOW
    ) == []
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema_subset_errors(receipt, schema, schema) == []


def test_pass_receipt_binds_source_and_schema_and_result_digests():
    receipt = _build()
    assert receipt["source_sha256"] == adapter.source_sha256()
    assert receipt["schema_sha256"] == adapter.schema_sha256()
    assert receipt["result_digest"] == adapter._overall_result_digest(receipt["queries"])
    assert receipt["self_digest"] == adapter.receipt_digest(receipt)


def test_ttl_and_time_ordering_are_bound():
    receipt = _build(ttl_seconds=1800)
    observed = datetime.fromisoformat(receipt["observation_time"])
    expires = datetime.fromisoformat(receipt["expires_at"])
    assert (expires - observed) == timedelta(seconds=1800)
    # 過期後(now >= expires)validator 判為不新鮮。
    stale_now = (expires + timedelta(seconds=1)).isoformat()
    errors = adapter.validate_pg_readonly_identity_receipt(receipt, now=stale_now)
    assert any("fresh" in error for error in errors)


def test_internal_temporal_consistency_enforced_without_now():
    # 內部時間一致性(expires == observed + ttl)即使不提供 now 也必須被強制檢查。
    receipt = _build(ttl_seconds=1800)
    tampered = deepcopy(receipt)
    observed = datetime.fromisoformat(tampered["observation_time"])
    tampered["expires_at"] = (observed + timedelta(seconds=1801)).isoformat()
    tampered["self_digest"] = adapter.receipt_digest(tampered)
    errors = adapter.validate_pg_readonly_identity_receipt(tampered, now=None)
    assert any("expires_at does not equal" in error for error in errors)


def test_tampered_field_breaks_self_digest():
    receipt = _build()
    tampered = deepcopy(receipt)
    tampered["caller"] = "someone-else"
    errors = adapter.validate_pg_readonly_identity_receipt(tampered)
    assert any("self_digest" in error for error in errors)


def test_validator_rejects_mismatched_source_sha256():
    # 即便重算 self_digest,錯誤的 source_sha256 仍必須被獨立重算擋下。
    receipt = _build()
    tampered = deepcopy(receipt)
    tampered["source_sha256"] = "sha256:" + "0" * 64
    tampered["self_digest"] = adapter.receipt_digest(tampered)
    errors = adapter.validate_pg_readonly_identity_receipt(tampered)
    assert any("source_sha256 does not bind" in error for error in errors)


def test_validator_rejects_mismatched_schema_sha256():
    # 即便重算 self_digest,錯誤的 schema_sha256 仍必須被獨立重算擋下。
    receipt = _build()
    tampered = deepcopy(receipt)
    tampered["schema_sha256"] = "sha256:" + "0" * 64
    tampered["self_digest"] = adapter.receipt_digest(tampered)
    errors = adapter.validate_pg_readonly_identity_receipt(tampered)
    assert any("schema_sha256 does not bind" in error for error in errors)


# --------------------------------------------------------------------------- #
# fail-closed policy verdicts (emit an honest FAIL receipt)
# --------------------------------------------------------------------------- #
def test_production_target_is_rejected_fail_closed():
    receipt = _build(target_class="production")
    assert receipt["status"] == "FAIL"
    assert receipt["failure_reason"]
    errors = adapter.validate_pg_readonly_identity_receipt(receipt)
    assert any("disposable_local" in error for error in errors)
    # 即便硬塞 status=PASS 也無法通過 schema/validator(production 永不 PASS)。
    forged = deepcopy(receipt)
    forged["status"] = "PASS"
    forged["failure_reason"] = None
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema_subset_errors(forged, schema, schema) != []


def test_write_capable_role_is_rejected():
    receipt = _build(probe_result=_clean_probe_result(rolsuper=True))
    assert receipt["status"] == "FAIL"
    assert receipt["role"]["is_read_only"] is False
    errors = adapter.validate_pg_readonly_identity_receipt(receipt)
    assert any("write-capable" in error for error in errors)


def test_non_login_role_is_rejected():
    receipt = _build(probe_result=_clean_probe_result(rolcanlogin=False))
    assert receipt["status"] == "FAIL"
    errors = adapter.validate_pg_readonly_identity_receipt(receipt)
    assert any("log in" in error for error in errors)


def test_structural_only_evidence_cannot_pass():
    receipt = _build(evidence_class="STRUCTURAL_ONLY")
    assert receipt["status"] == "FAIL"
    assert adapter.validate_pg_readonly_identity_receipt(receipt, require_success=True)


# --------------------------------------------------------------------------- #
# fail-closed integrity violations (refuse to emit)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ttl", [0, -1, 3601, 7200, True, 1.5])
def test_ttl_outside_bound_refuses_to_build(ttl):
    with pytest.raises(ValueError):
        _build(ttl_seconds=ttl)


def test_write_probe_without_denial_refuses_to_build():
    probe = _clean_probe_result()
    object.__setattr__(
        probe,
        "write_denied",
        {"attempted": "x", "expected_denial": True, "observed_sqlstate": "00000", "verdict": "DENIED"},
    )
    with pytest.raises(adapter.ReadOnlyProbeError):
        _build(probe_result=probe)


def test_role_probe_without_denial_refuses_to_build():
    probe = _clean_probe_result()
    object.__setattr__(
        probe,
        "role_escalation_denied",
        {"attempted": "SET ROLE w", "expected_denial": True, "observed_sqlstate": "25006", "verdict": "NOT_DENIED"},
    )
    with pytest.raises(adapter.ReadOnlyProbeError):
        _build(probe_result=probe)


def test_search_path_neither_pinned_nor_denied_refuses_to_build():
    probe = _clean_probe_result()
    object.__setattr__(
        probe,
        "search_path_pinned",
        {"attempted": "SET search_path TO evil", "effective_search_path": "evil", "pinned": True, "verdict": "OPEN"},
    )
    with pytest.raises(adapter.ReadOnlyProbeError):
        _build(probe_result=probe)


def test_probe_role_mismatch_refuses_to_build():
    with pytest.raises(ValueError):
        _build(role="different_role")


# --------------------------------------------------------------------------- #
# read-only pin contract (MUST-FIX 1): a PASS must genuinely prove the RO pin
# --------------------------------------------------------------------------- #
def test_pinned_search_path_no_longer_builds():
    # 舊漏洞:search_path verdict=PINNED 曾被視為可接受;現在(僅連線層 pin、未觀察到
    # 真正拒絕)必須 refuse-to-build。
    probe = _clean_probe_result()
    object.__setattr__(
        probe,
        "search_path_pinned",
        {
            "attempted": "x",
            "effective_search_path": "pg_catalog",
            "observed_sqlstate": "25006",
            "pinned": True,
            "verdict": "PINNED",
        },
    )
    with pytest.raises(adapter.ReadOnlyProbeError):
        _build(probe_result=probe)


def test_privilege_only_write_denial_is_not_a_pass():
    # write 拒絕若僅是權限碼 42501(而非唯讀交易碼 25006),必須是 FAIL 而非 PASS。
    probe = _clean_probe_result()
    object.__setattr__(
        probe,
        "write_denied",
        {"attempted": "x", "expected_denial": True, "observed_sqlstate": "42501", "verdict": "DENIED"},
    )
    receipt = _build(probe_result=probe)
    assert receipt["status"] == "FAIL"
    assert "25006" in receipt["failure_reason"]
    assert adapter.validate_pg_readonly_identity_receipt(receipt, require_success=True)


def test_session_not_read_only_is_not_a_pass():
    # session transaction_read_only 非 on 時必須 FAIL(session_read_only 已綁進 receipt)。
    probe = _clean_probe_result()
    object.__setattr__(probe, "session_read_only", "off")
    receipt = _build(probe_result=probe)
    assert receipt["status"] == "FAIL"
    assert receipt["session_read_only"] == "off"
    assert "transaction_read_only" in receipt["failure_reason"]
    assert adapter.validate_pg_readonly_identity_receipt(receipt, require_success=True)


# --------------------------------------------------------------------------- #
# validator catches an embedded secret even when leaked flag lies
# --------------------------------------------------------------------------- #
def test_validator_rescans_for_embedded_secret():
    receipt = _build()
    poisoned = deepcopy(receipt)
    poisoned["caller"] = "password=leakedsecretvalue"
    poisoned["self_digest"] = adapter.receipt_digest(poisoned)
    errors = adapter.validate_pg_readonly_identity_receipt(poisoned)
    assert any("secret-like" in error for error in errors)


def test_adapter_id_and_schema_version_are_constants():
    assert adapter.ADAPTER_ID == "pg_readonly_identity_adapter_v1"
    assert adapter.RECEIPT_SCHEMA_VERSION == "pg_readonly_identity_receipt_v1"
    assert adapter.TTL_CEILING_SECONDS == 3600
