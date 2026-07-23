"""Disposable-cluster proof for the LR0A PG read-only identity Adapter (S1.1).

Gated on ``shutil.which("initdb")`` (and ``psycopg2``). When PG binaries are
present this ``initdb``-creates a throwaway, socket-only cluster, seeds a
dedicated read-only role plus a separate writer role, drives the Adapter's real
``psycopg2`` probe, and asserts the three negative cases raise genuine PostgreSQL
SQLSTATEs. When the binaries are absent it SKIPS with a clear reason — never a
false pass. The cluster lives in a temp dir and is torn down in a finally.

Evidence class: LOCAL_REPRODUCIBLE (a real ``postgres`` process, nothing mocked).
It proves the Adapter mechanism, not production PG's roles/ACLs (S2.0-gated).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

import agent_governance_pg_readonly_identity as adapter  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402

import json  # noqa: E402

INITDB = shutil.which("initdb")
PG_CTL = shutil.which("pg_ctl")
psycopg2 = pytest.importorskip("psycopg2", reason="psycopg2 driver is required")

pytestmark = pytest.mark.skipif(
    not (INITDB and PG_CTL),
    reason="initdb/pg_ctl are absent; disposable-cluster proof cannot run",
)

RO_ROLE = "aiml_ro"
WRITER_ROLE = "aiml_writer"
DATABASE = "postgres"
# 乾淨環境:啟動子進程一律不繼承 ambient PG* 路由。
CLEAN_SUBPROCESS_ENV = {
    "PATH": os.environ.get("PATH", ""),
    "LANG": "C",
    "LC_ALL": "C",
}


def _run(cmd, *, logfile, timeout):
    # 以 DEVNULL 取代 PIPE,避免 daemon 化的 postgres 繼承 stdout 造成 communicate 死鎖。
    result = subprocess.run(
        cmd,
        env=CLEAN_SUBPROCESS_ENV,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = ""
        try:
            detail = Path(logfile).read_text(encoding="utf-8")[-800:]
        except OSError:
            pass
        raise RuntimeError(f"command failed rc={result.returncode}: {cmd[0]}\n{detail}")


@pytest.fixture(scope="module")
def disposable_cluster():
    tmp = tempfile.mkdtemp(prefix="aiml_ro_")
    data_dir = os.path.join(tmp, "data")
    sock_dir = os.path.join(tmp, "sock")
    logfile = os.path.join(tmp, "server.log")
    os.makedirs(sock_dir)
    started = False
    try:
        _run(
            [INITDB, "-D", data_dir, "-U", "postgres", "--auth=trust", "-E", "UTF8", "-N"],
            logfile=logfile,
            timeout=90,
        )
        # 以設定檔注入 socket-only 參數,避免無 shell 傳遞空字串引號的問題。
        with open(os.path.join(data_dir, "postgresql.auto.conf"), "a", encoding="utf-8") as handle:
            handle.write("\nlisten_addresses = ''\n")
            handle.write(f"unix_socket_directories = '{sock_dir}'\n")
            handle.write("fsync = off\n")
        _run(
            [PG_CTL, "-D", data_dir, "-l", logfile, "-w", "-t", "40", "start"],
            logfile=logfile,
            timeout=60,
        )
        started = True
        _bootstrap_roles(sock_dir)
        yield {"socket_dir": sock_dir, "database": DATABASE}
    finally:
        # 只要 postmaster.pid 還在就 best-effort 停機(不論 started 旗標),避免
        # 啟動後、started=True 前若拋錯而遺留孤兒 postgres 進程。
        pid_file = os.path.join(data_dir, "postmaster.pid")
        if started or os.path.exists(pid_file):
            try:
                subprocess.run(
                    [PG_CTL, "-D", data_dir, "-m", "immediate", "stop"],
                    env=CLEAN_SUBPROCESS_ENV,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=30,
                )
            except (OSError, subprocess.SubprocessError):
                pass
        shutil.rmtree(tmp, ignore_errors=True)


def _bootstrap_roles(sock_dir):
    # 以 superuser 建立專用唯讀角色 aiml_ro(只授 SELECT)與獨立寫入角色 aiml_writer
    # (作為 SET ROLE 提權的攻擊目標)。這屬於 disposable 叢集鷹架,非 repo migration。
    connection = psycopg2.connect(
        host=sock_dir, dbname=DATABASE, user="postgres", connect_timeout=10
    )
    try:
        connection.autocommit = True
        cursor = connection.cursor()
        cursor.execute(f"CREATE ROLE {WRITER_ROLE} LOGIN")
        cursor.execute(f"CREATE ROLE {RO_ROLE} LOGIN")
        cursor.execute("CREATE SCHEMA aiml_probe")
        cursor.execute("CREATE TABLE aiml_probe.fact(id integer PRIMARY KEY, note text)")
        cursor.execute("INSERT INTO aiml_probe.fact VALUES (1, 'seed')")
        cursor.execute(f"GRANT USAGE ON SCHEMA aiml_probe TO {RO_ROLE}")
        cursor.execute(f"GRANT SELECT ON aiml_probe.fact TO {RO_ROLE}")
        cursor.execute(f"GRANT INSERT ON aiml_probe.fact TO {WRITER_ROLE}")
    finally:
        connection.close()


@pytest.fixture(scope="module")
def probe_result(disposable_cluster):
    params = adapter.build_readonly_connection_params(
        endpoint_class="unix_socket_allowlisted",
        database=disposable_cluster["database"],
        role=RO_ROLE,
        socket_dir=disposable_cluster["socket_dir"],
    )
    return adapter.run_readonly_probe(params, escalation_target_role=WRITER_ROLE)


def test_session_is_pinned_read_only(probe_result):
    assert probe_result.role_name == RO_ROLE
    assert probe_result.session_read_only == "on"
    assert probe_result.session_search_path == "pg_catalog"


def test_dedicated_role_has_no_write_capable_attribute(probe_result):
    attributes = probe_result.role_attributes
    for attr in adapter.FORBIDDEN_ROLE_ATTRS:
        assert attributes[attr] is False, attr
    assert attributes["rolcanlogin"] is True


def test_real_write_denial_sqlstate(probe_result):
    # 真實 PostgreSQL 語意:唯讀交易寫入 -> 25006 read_only_sql_transaction。
    assert probe_result.write_denied["verdict"] == "DENIED"
    assert probe_result.write_denied["observed_sqlstate"] in adapter.DENIAL_SQLSTATES
    assert probe_result.write_denied["observed_sqlstate"] == "25006"


def test_real_role_escalation_denial_sqlstate(probe_result):
    # SET ROLE 到非成員角色 -> 42501 insufficient_privilege。
    assert probe_result.role_escalation_denied["verdict"] == "DENIED"
    assert probe_result.role_escalation_denied["observed_sqlstate"] == "42501"


def test_real_set_session_authorization_is_denied(disposable_cluster):
    # SET SESSION AUTHORIZATION 到別的角色需要 superuser;唯讀身分必須被拒(觀察到
    # 42501 insufficient_privilege)。_observe_denial 若未被拒會直接 raise(fail-closed)。
    params = adapter.build_readonly_connection_params(
        endpoint_class="unix_socket_allowlisted",
        database=disposable_cluster["database"],
        role=RO_ROLE,
        socket_dir=disposable_cluster["socket_dir"],
    )
    connection = psycopg2.connect(**params["connect_kwargs"])
    try:
        connection.autocommit = True
        cursor = connection.cursor()
        safe_role = '"' + WRITER_ROLE.replace('"', '""') + '"'
        sqlstate = adapter._observe_denial(
            cursor, f"SET SESSION AUTHORIZATION {safe_role}"
        )
        assert sqlstate in adapter.DENIAL_SQLSTATES
    finally:
        connection.close()


def test_real_search_path_cannot_be_persistently_hijacked(probe_result):
    # 持久 search_path 劫持(ALTER ROLE ... SET)必須被唯讀交易真正拒絕:
    # verdict==DENIED 且 SQLSTATE==25006(read_only_sql_transaction),不接受弱 PINNED。
    record = probe_result.search_path_pinned
    assert record["verdict"] == "DENIED"
    assert record["observed_sqlstate"] == "25006"
    assert record["effective_search_path"] == "pg_catalog"
    assert record["pinned"] is True


def test_disposable_receipt_is_passing_and_reproducible(disposable_cluster, probe_result):
    import platform as platform_module

    receipt = adapter.build_pg_readonly_identity_receipt(
        caller="E1:S1.1:disposable",
        platform={
            "os": "darwin" if sys.platform == "darwin" else "linux",
            "arch": platform_module.machine(),
            "postgres_version": probe_result.server_version,
        },
        endpoint={
            "endpoint_class": "unix_socket_allowlisted",
            "socket_dir": disposable_cluster["socket_dir"],
            "loopback_host": None,
            "port": None,
        },
        database=disposable_cluster["database"],
        role=RO_ROLE,
        target_class="disposable_local",
        probe_result=probe_result,
        observation_time="2026-07-22T12:00:00+00:00",
        ttl_seconds=3600,
        evidence_class="LOCAL_REPRODUCIBLE",
    )
    assert receipt["status"] == "PASS"
    assert receipt["target_class"] == "disposable_local"
    assert receipt["evidence_class"] == "LOCAL_REPRODUCIBLE"
    assert receipt["secret_scan"]["leaked"] is False
    # require_success 通過(freshness 用觀測後 5 分鐘的 now)。
    assert adapter.validate_pg_readonly_identity_receipt(
        receipt, require_success=True, now="2026-07-22T12:05:00+00:00"
    ) == []
    schema = json.loads(adapter.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema_subset_errors(receipt, schema, schema) == []
