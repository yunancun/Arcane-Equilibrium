"""S2.4 §2.1/§10.5 #23(W2a)disposable-PG trace proof — real 42501, nothing mocked.

Gated on ``shutil.which("initdb")`` + ``psycopg2``(缺任一 → 整模組誠實 SKIP,絕不
假 pass;鏡 S2.0/S2.1 disposable 慣例、不共用 helper)。當 PG binaries 在場時:

* ``initdb`` 建一個 throwaway、socket-only、``scram-sha-256`` cluster,建庫
  ``trading_ai``,套用真 V030 + V151..V156 migrations(真 DDL,含 append-only
  REVOKE);
* 以 ``generate_engine_scanner_grant_sql(pg_acl_manifest_v1.json)`` 「恰好」授
  manifest 上的權限給 ``aiml_engine_scanner``(角色建立僅此測試持密;密碼絕不
  進 manifest/verdict/grant SQL);
* 以該受限角色跑「真 consumer SQL surface」:advisory lock 單例、LISTEN、
  consumer session lifecycle、真 ``drain_fresh_lane``(scanner capture writes:
  source/ingest/artifact/provenance/consumer events)、真 outcome-feedback 與
  candidate-proof backlog、真 health snapshot(collect+persist);
* 對 manifest 每一格 grant 跑 zero-row coverage probe(SELECT LIMIT 0 /
  INSERT..SELECT WHERE false)證明 intended statements 都成功;
* over-grant probes(DELETE/UPDATE retention 表、INSERT retention events、
  TRUNCATE、CREATE TABLE/SCHEMA/TEMP、SET ROLE)全部觀察到**真** ``42501``
  (insufficient_privilege;真 postgres 產生,production PG 永不接觸);
* W2 P1-A(§8.3/§10.5 #35):在 throwaway cluster 建立 admin-owned 的
  ``learning.alr_runtime_cluster_identity_v1``(source 樹尚無其 V### migration——該關聯
  屬 W6B PG migration,此處依 ``pg_topology_runtime_guard_v1`` /
  ``alr_consumer_resilience.CLUSTER_IDENTITY_COLUMNS`` 的封閉欄位契約建同形關聯並灌入
  本 cluster 真實觀測值),再以受限角色跑**真**在帶身分閘:相符即 MATCH、漂移即 typed
  permanent 失敗(→ exit 78),且對該關聯的 INSERT/UPDATE/DELETE/TRUNCATE 全數真 42501。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
PROGRAM_CODE = ROOT / "program_code"
for candidate in (HELPERS, ML_ROOT, PROGRAM_CODE):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_4_install as install  # noqa: E402
from ml_training import alr_event_consumer as consumer  # noqa: E402
from ml_training import alr_freshness_runtime as freshness  # noqa: E402
from ml_training.alr_consumer_repository import (  # noqa: E402
    new_session_id,
    start_consumer_session,
    stop_consumer_session,
)

INITDB = shutil.which("initdb")
PG_CTL = shutil.which("pg_ctl")
psycopg2 = pytest.importorskip("psycopg2", reason="psycopg2 driver is required")
from psycopg2.extras import RealDictCursor  # noqa: E402

pytestmark = pytest.mark.skipif(
    not (INITDB and PG_CTL),
    reason="initdb/pg_ctl are absent; the disposable engine-scanner ACL proof cannot run",
)

DB = "trading_ai"
ROLE = "aiml_engine_scanner"
ROLE_PW = "aiml-engine-scanner-disposable-cred-v0"
SOURCE_HEAD = "a" * 40

MANIFEST = json.loads(
    (ROOT / "program_code/ml_training/pg_acl_manifest_v1.json").read_text(
        encoding="utf-8"
    )
)
MIGRATIONS = (
    "sql/migrations/V030__scanner_snapshots.sql",
    "sql/migrations/V151__alr_persistence_foundation.sql",
    "sql/migrations/V152__alr_operational_artifacts.sql",
    "sql/migrations/V153__alr_outcome_feedback.sql",
    "sql/migrations/V154__alr_retention_guardian.sql",
    "sql/migrations/V155__alr_health_state.sql",
    "sql/migrations/V156__alr_consumer_freshness_state.sql",
)

CLEAN_SUBPROCESS_ENV = {"PATH": os.environ.get("PATH", ""), "LANG": "C", "LC_ALL": "C"}

# §8.2/§8.3 叢集身分列(W6B PG migration 的 source-面契約鏡像;欄位集合由
# ml_training.alr_consumer_resilience.CLUSTER_IDENTITY_COLUMNS 執法)。
RUNTIME_HOST = "127.0.0.1"
RUNTIME_PORT = 5432
BINDING_NONCE = "disposable-binding-nonce-v0"
_CLUSTER_IDENTITY_DDL = """
CREATE TABLE IF NOT EXISTS learning.alr_runtime_cluster_identity_v1 (
    system_identifier   text    NOT NULL,
    database_oid        integer NOT NULL,
    server_major_version integer NOT NULL,
    runtime_host        text    NOT NULL,
    runtime_port        integer NOT NULL,
    runtime_dbname      text    NOT NULL,
    binding_nonce       text    NOT NULL,
    singleton           boolean NOT NULL DEFAULT true UNIQUE CHECK (singleton)
)
"""


def _run(cmd, *, logfile, timeout):
    result = subprocess.run(
        cmd, env=CLEAN_SUBPROCESS_ENV, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=timeout,
    )
    if result.returncode != 0:
        detail = ""
        try:
            detail = Path(logfile).read_text(encoding="utf-8")[-800:]
        except OSError:
            pass
        raise RuntimeError(f"command failed rc={result.returncode}: {cmd[0]}\n{detail}")


@pytest.fixture(scope="module")
def cluster():
    tmp = tempfile.mkdtemp(prefix="aiml_s24_w2a_")
    data_dir = os.path.join(tmp, "data")
    sock_dir = os.path.join(tmp, "sock")
    logfile = os.path.join(tmp, "server.log")
    os.makedirs(sock_dir)
    started = False
    try:
        _run([INITDB, "-D", data_dir, "-U", "postgres", "--auth=trust", "-E", "UTF8", "-N"],
             logfile=logfile, timeout=90)
        with open(os.path.join(data_dir, "postgresql.auto.conf"), "a", encoding="utf-8") as handle:
            handle.write("\nlisten_addresses = ''\n")
            handle.write(f"unix_socket_directories = '{sock_dir}'\n")
            handle.write("fsync = off\n")
            handle.write("password_encryption = 'scram-sha-256'\n")
            handle.write("lc_messages = 'C'\n")
            handle.write("log_statement = 'none'\n")
            handle.write("log_min_duration_statement = -1\n")
        with open(os.path.join(data_dir, "pg_hba.conf"), "w", encoding="utf-8") as handle:
            handle.write("local   all   postgres   trust\n")
            handle.write("local   all   all        scram-sha-256\n")
        _run([PG_CTL, "-D", data_dir, "-l", logfile, "-w", "-t", "40", "start"],
             logfile=logfile, timeout=60)
        started = True
        _bootstrap(sock_dir)
        yield {"socket_dir": sock_dir}
    finally:
        if started or os.path.exists(os.path.join(data_dir, "postmaster.pid")):
            try:
                subprocess.run([PG_CTL, "-D", data_dir, "-m", "immediate", "stop"],
                               env=CLEAN_SUBPROCESS_ENV, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=30)
            except (OSError, subprocess.SubprocessError):
                pass
        shutil.rmtree(tmp, ignore_errors=True)


def _bootstrap(sock_dir: str) -> None:
    """建庫 + 真 migrations + 角色與「恰好 manifest」的 grants(manifest 之外零授權)。"""

    bootstrap = psycopg2.connect(host=sock_dir, dbname="postgres", user="postgres", connect_timeout=10)
    bootstrap.autocommit = True
    try:
        bootstrap.cursor().execute(f"CREATE DATABASE {DB}")
    finally:
        bootstrap.close()
    admin = _admin(sock_dir)
    try:
        cur = admin.cursor()
        cur.execute("CREATE SCHEMA IF NOT EXISTS trading")
        for rel in MIGRATIONS:
            cur.execute((ROOT / rel).read_text(encoding="utf-8"))
        # §8.2/§8.3(W2 P1-A):admin-owned、scanner-read-only 的叢集身分列。此關聯屬
        # W6B 的 PG migration(source 樹尚無 V### 檔),故 disposable cluster 在此
        # 依 pg_topology_runtime_guard_v1 / alr_consumer_resilience 宣告的封閉欄位契約
        # 建立同形關聯,並灌入「本 cluster 真實觀測值」(system_identifier/OID/版本)。
        cur.execute(_CLUSTER_IDENTITY_DDL)
        cur.execute(
            "INSERT INTO learning.alr_runtime_cluster_identity_v1 "
            "(system_identifier, database_oid, server_major_version, runtime_host, "
            "runtime_port, runtime_dbname, binding_nonce) SELECT "
            "(pg_control_system()).system_identifier::text, "
            "(SELECT oid FROM pg_database WHERE datname = current_database())::integer, "
            "current_setting('server_version_num')::integer / 10000, "
            "%s, %s, current_database(), %s",
            (RUNTIME_HOST, RUNTIME_PORT, BINDING_NONCE),
        )
        cur.execute(
            f'CREATE ROLE "{ROLE}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %s',
            (ROLE_PW,),
        )
        # P1-3:此處**不再**代為收回 PUBLIC 預設權限——closed_boundary.database_temp /
        # database_create = false 必須由 generate_engine_scanner_grant_sql 自己產出的
        # REVOKE ... FROM PUBLIC 讓其成真;fixture 預先代勞會遮住那個缺口(over-grant
        # probe 的 CREATE TEMP TABLE 42501 於是變成 fixture 的功勞,不是 apply 路徑的)。
        for statement in install.generate_engine_scanner_grant_sql(MANIFEST):
            cur.execute(statement)
    finally:
        admin.close()


def _admin(sock_dir: str):
    connection = psycopg2.connect(host=sock_dir, dbname=DB, user="postgres", connect_timeout=10)
    connection.autocommit = True
    return connection


def _role_connection(sock_dir: str, *, autocommit: bool = False):
    connection = psycopg2.connect(
        host=sock_dir, dbname=DB, user=ROLE, password=ROLE_PW,
        connect_timeout=10, cursor_factory=RealDictCursor,
    )
    connection.autocommit = autocommit
    return connection


def _seed_scanner_row(sock_dir: str, *, scan_id: str, ts_offset_seconds: int) -> None:
    admin = _admin(sock_dir)
    try:
        admin.cursor().execute(
            "INSERT INTO trading.scanner_snapshots "
            "(ts, scan_id, active_symbols, added, removed, rejected_count, "
            "scan_duration_ms, candidates, config) VALUES "
            "(now() + make_interval(secs => %s), %s, ARRAY['BTCUSDT'], "
            "ARRAY[]::text[], ARRAY[]::text[], 0, 5, "
            "'[{\"symbol\": \"BTCUSDT\"}]'::jsonb, '{}'::jsonb)",
            (ts_offset_seconds, scan_id),
        )
    finally:
        admin.close()


def _admin_count(sock_dir: str, table: str) -> int:
    admin = _admin(sock_dir)
    try:
        cur = admin.cursor()
        cur.execute(f"SELECT count(*) FROM {table}")
        return int(cur.fetchone()[0])
    finally:
        admin.close()


# --------------------------------------------------------------------------- #
# (1) 真 consumer SQL surface 以「恰好 manifest」權限全數成功
# --------------------------------------------------------------------------- #
def test_real_consumer_surface_succeeds_under_exact_manifest_grants(cluster):
    sock = cluster["socket_dir"]
    _seed_scanner_row(sock, scan_id="scan-0001", ts_offset_seconds=0)
    connection = _role_connection(sock)
    try:
        # advisory-lock 單例(pg_try_advisory_lock/hashtext;PUBLIC-default EXECUTE)。
        assert consumer.acquire_single_instance(connection) is True
        rival = _role_connection(sock)
        try:
            assert consumer.acquire_single_instance(rival) is False  # 真 busy 單例
        finally:
            rival.close()
        # LISTEN(session 能力,無表權限)。
        with connection.cursor() as cursor:
            cursor.execute(f"LISTEN {consumer.ALR_SCANNER_NOTIFY_CHANNEL}")
        connection.commit()
        # consumer session lifecycle + 真 fresh-lane capture(bootstrap 落地 seed row)。
        session_id = new_session_id()
        start_consumer_session(connection, session_id=session_id)
        first = freshness.drain_fresh_lane(connection, session_id=session_id, max_batch=8)
        assert set(first) >= {"rows_seen", "persisted", "duplicates"}
        # 第二 row → 真 contiguous catch-up(SELECT scanner + INSERT source/ingest/
        # artifact/provenance + LANE_CURSOR_ADVANCED consumer events)。
        _seed_scanner_row(sock, scan_id="scan-0002", ts_offset_seconds=60)
        second = freshness.drain_fresh_lane(connection, session_id=session_id, max_batch=8)
        assert second["rows_seen"] >= 1
        assert second["persisted"] >= 1
        # 真 outcome-feedback / candidate-proof backlog(空表 → 有界零結果,SQL 全跑)。
        feedback = consumer.process_outcome_feedback_backlog(connection, max_batch=8)
        assert feedback["feedback_persisted"] == 0
        proof = consumer.process_candidate_proof_repository_backlog(connection, max_batch=8)
        assert proof["candidate_proof_rows_written"] == 0
        # 真 health snapshot(讀遍 health 面 + INSERT artifact/health events)。
        health = consumer.process_health_snapshot(connection, source_head=SOURCE_HEAD)
        assert health["health_attempts"] == 1
        stop_consumer_session(connection, session_id=session_id)
        consumer.release_single_instance(connection)
    finally:
        connection.close()
    # capture writes 真的落地(superuser 獨立複核)。
    assert _admin_count(sock, "learning.alr_source_events") >= 2
    assert _admin_count(sock, "learning.alr_ingest_events") >= 2
    assert _admin_count(sock, "learning.alr_consumer_events") >= 3
    assert _admin_count(sock, "learning.alr_health_events") >= 1


# --------------------------------------------------------------------------- #
# (2) manifest 每一格 grant 都被 zero-row probe 證實可用(intended succeed)
# --------------------------------------------------------------------------- #
def test_every_manifest_grant_is_usable(cluster):
    sock = cluster["socket_dir"]
    connection = _role_connection(sock, autocommit=True)
    try:
        cur = connection.cursor()
        for entry in MANIFEST["tables"]:
            table = entry["name"]
            privileges = entry["privileges"]
            if "SELECT" in privileges:
                cur.execute(f"SELECT * FROM {table} LIMIT 0")
            if "INSERT" in privileges and "SELECT" in privileges:
                cur.execute(f"INSERT INTO {table} SELECT * FROM {table} WHERE false")
            # INSERT-only(alr_ingest_events)由 (1) 的真 drain 落地證明;此處不再
            # DEFAULT VALUES 触 NOT NULL 噪音。
    finally:
        connection.close()


# --------------------------------------------------------------------------- #
# (3) over-grant probes:每一條都觀察到真 42501
# --------------------------------------------------------------------------- #
_OVER_GRANT_PROBES = (
    ("retention_delete", "DELETE FROM learning.alr_derived_cache_entries"),
    (
        "retention_update",
        "UPDATE learning.alr_derived_cache_entries SET cache_state = 'ACTIVE'",
    ),
    (
        "retention_event_insert",
        "INSERT INTO learning.alr_retention_events "
        "SELECT * FROM learning.alr_retention_events WHERE false",
    ),
    ("source_delete", "DELETE FROM learning.alr_source_events"),
    ("source_truncate", "TRUNCATE learning.alr_source_events"),
    (
        "consumer_events_update",
        "UPDATE learning.alr_consumer_events SET error_code = NULL",
    ),
    ("schema_create_table", "CREATE TABLE learning.evil (id integer)"),
    ("database_create_schema", "CREATE SCHEMA evil_schema"),
    ("database_temp", "CREATE TEMP TABLE evil_tmp (id integer)"),
)


@pytest.mark.parametrize("name,statement", _OVER_GRANT_PROBES)
def test_over_grant_probe_is_denied_with_real_42501(cluster, name, statement):
    connection = _role_connection(cluster["socket_dir"], autocommit=True)
    try:
        with pytest.raises(psycopg2.Error) as denial:
            connection.cursor().execute(statement)
        assert denial.value.pgcode == "42501", (name, denial.value.pgcode)
    finally:
        connection.close()


def test_set_role_escalation_is_denied(cluster):
    connection = _role_connection(cluster["socket_dir"], autocommit=True)
    try:
        with pytest.raises(psycopg2.Error) as denial:
            connection.cursor().execute("SET ROLE postgres")
        assert denial.value.pgcode == "42501"
    finally:
        connection.close()


# --------------------------------------------------------------------------- #
# (4) 角色屬性封閉 + 密碼零序列化
# --------------------------------------------------------------------------- #
def test_role_attributes_are_closed(cluster):
    admin = _admin(cluster["socket_dir"])
    try:
        cur = admin.cursor()
        cur.execute(
            "SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication, "
            "rolbypassrls, rolinherit, rolconnlimit FROM pg_catalog.pg_roles "
            "WHERE rolname = %s",
            (ROLE,),
        )
        rolsuper, createrole, createdb, replication, bypassrls, inherit, connlimit = (
            cur.fetchone()
        )
        assert (rolsuper, createrole, createdb, replication, bypassrls, inherit) == (
            False, False, False, False, False, False,
        )
        assert connlimit == MANIFEST["role_attributes"]["connection_limit"]
        # 零 role membership(closed_boundary.role_memberships=false 的可執行面)。
        cur.execute(
            "SELECT count(*) FROM pg_catalog.pg_auth_members m "
            "JOIN pg_catalog.pg_roles r ON r.oid = m.member WHERE r.rolname = %s",
            (ROLE,),
        )
        assert int(cur.fetchone()[0]) == 0
    finally:
        admin.close()


def test_secret_never_serialized_into_manifest_grants_or_verdict(cluster):
    del cluster  # 佐證面不需連線;僅證密碼絕不進任何可持久化字面。
    assert ROLE_PW not in json.dumps(MANIFEST)
    assert all(ROLE_PW not in statement for statement in install.generate_engine_scanner_grant_sql(MANIFEST))
    verdict = install.derive_engine_scanner_privilege_split()
    assert ROLE_PW not in json.dumps(verdict)
    assert verdict["status"] == "PASS"


# --------------------------------------------------------------------------- #
# (5) §8.3(W2 P1-A)在帶叢集身分閘:真 SELECT 通過、真 42501 拒絕任何寫入
# --------------------------------------------------------------------------- #
def _observed_identity(sock_dir: str) -> dict:
    admin = _admin(sock_dir)
    try:
        cur = admin.cursor()
        cur.execute(
            "SELECT system_identifier, database_oid, server_major_version, "
            "runtime_host, runtime_port, runtime_dbname, binding_nonce "
            "FROM learning.alr_runtime_cluster_identity_v1"
        )
        row = cur.fetchone()
    finally:
        admin.close()
    return {
        "system_identifier": str(row[0]),
        "database_oid": int(row[1]),
        "server_major_version": int(row[2]),
        "runtime_host": str(row[3]),
        "runtime_port": int(row[4]),
        "runtime_dbname": str(row[5]),
        "binding_nonce": str(row[6]),
    }


def _write_guard(tmp_path, projection: dict, **overrides):
    from ml_training import alr_consumer_resilience as resilience
    from ml_training.aiml_gate_receipt_schema_core import resolve_facade

    guard = {
        "schema_version": "pg_topology_runtime_guard_v1",
        "guard_path": "/etc/arcane-equilibrium/aiml/engine-scanner/topology-runtime-guard.json",
        "cluster_identity_row_digest": resilience.cluster_identity_row_digest(projection),
        "plan_topology_digest": "sha256:" + "1" * 64,
        "runtime_endpoint": {
            "host": projection["runtime_host"],
            "port": projection["runtime_port"],
            "dbname": projection["runtime_dbname"],
        },
        "system_identifier": projection["system_identifier"],
        "database_oid": projection["database_oid"],
        "server_major_version": projection["server_major_version"],
        "binding_nonce": projection["binding_nonce"],
        "expected_topology_values_digest": "sha256:" + "2" * 64,
    }
    guard.update(overrides)
    guard["self_digest"] = resolve_facade().artifact_self_digest(guard)
    path = tmp_path / "topology-runtime-guard.json"
    path.write_text(json.dumps(guard, sort_keys=True), encoding="utf-8")
    os.chmod(path, 0o440)  # P2-4:guard 的 host 姿態契約(mode 恰 0440)
    return path


@pytest.fixture(autouse=True)
def _simulate_guard_host_ownership(monkeypatch):
    """P2-4:disposable cluster 跑在非 root 使用者下,以唯一縫模擬 guard 的佈署身分。"""
    from ml_training import alr_application_identity as app_identity

    monkeypatch.setattr(
        app_identity,
        "guard_host_identity",
        lambda st: (
            app_identity.TOPOLOGY_GUARD_REQUIRED_OWNER_UID,
            app_identity.TOPOLOGY_GUARD_REQUIRED_GROUP,
        ),
    )


def test_identity_gate_passes_against_the_real_cluster_row(cluster, tmp_path):
    """真 PG:受限角色以「恰好 manifest」的 SELECT 讀身分列並與 guard 逐欄比對。

    guard/身分列綁的是**宣告的 production endpoint**(127.0.0.1:5432/trading_ai);
    disposable cluster 走 unix socket,故此測試證的是「在帶身分比對可執行且權限足夠」,
    不宣稱 listener/proxy 拓樸(§8.3 明文:此非 host 行程檢視)。
    """
    from ml_training import alr_consumer_resilience as resilience

    projection = _observed_identity(cluster["socket_dir"])
    guard_path = _write_guard(tmp_path, projection)
    connection = _role_connection(cluster["socket_dir"])
    try:
        check = resilience.verify_connected_cluster_identity(
            connection,
            topology_guard_file=guard_path,
            dsn_identity={
                "host": projection["runtime_host"],
                "port": str(projection["runtime_port"]),
                "dbname": projection["runtime_dbname"],
                "user": ROLE,
            },
        )
    finally:
        connection.close()
    assert check["status"] == "MATCH"
    assert check["connected_user"] == ROLE
    assert check["connected_database"] == DB
    # P1-4:連線期錯誤分類的語言前提是**從真 server 讀來的**,不是宣告的。
    assert check["lc_messages"] == resilience.REQUIRED_LC_MESSAGES


def test_identity_gate_refuses_a_server_whose_messages_are_not_english(cluster, tmp_path):
    """P1-4(真 PG):server 的 lc_messages 一漂離 C,連線期 permanent 失敗就分類不出來。

    連線期失敗沒有 SQLSTATE(F1),唯一判別材料是被 lc_messages 在地化的 FATAL 文本;
    舊契約完全不綁該設定(只有本 fixture 恰好設了 C)。此處以真 cluster 把該角色的
    lc_messages 改掉,證明在帶身分閘會 typed permanent 拒絕(→ exit 78),而不是讓分類器
    靜默失效、讓常駐行程永遠重試。
    """
    from ml_training import alr_application_identity as app_identity
    from ml_training import alr_consumer_resilience as resilience

    projection = _observed_identity(cluster["socket_dir"])
    guard_path = _write_guard(tmp_path, projection)
    admin = _admin(cluster["socket_dir"])
    localized = None
    try:
        try:
            admin.cursor().execute(
                f"ALTER ROLE \"{ROLE}\" SET lc_messages = 'en_US.UTF-8'"
            )
        except psycopg2.Error as error:  # host 無該 locale:誠實 skip,絕不假 pass
            pytest.skip(f"host lacks the en_US.UTF-8 message locale: {error}")
        localized = _role_connection(cluster["socket_dir"])
        with pytest.raises(resilience.AlrRuntimeIdentityError) as failure:
            resilience.verify_connected_cluster_identity(
                localized, topology_guard_file=guard_path
            )
        assert str(failure.value) == "cluster_identity_lc_messages_mismatch"
        assert app_identity.is_permanent_pre_db_error(failure.value)
    finally:
        if localized is not None:
            localized.close()
        try:
            admin.cursor().execute(f"ALTER ROLE \"{ROLE}\" RESET lc_messages")
        finally:
            admin.close()


def test_identity_gate_refuses_a_drifted_cluster(cluster, tmp_path):
    from ml_training import alr_consumer_resilience as resilience

    projection = _observed_identity(cluster["socket_dir"])
    drifted = dict(projection)
    drifted["system_identifier"] = "1" + projection["system_identifier"][1:]
    guard_path = _write_guard(tmp_path, drifted)
    connection = _role_connection(cluster["socket_dir"])
    try:
        with pytest.raises(resilience.AlrRuntimeIdentityError) as failure:
            resilience.verify_connected_cluster_identity(
                connection, topology_guard_file=guard_path
            )
    finally:
        connection.close()
    assert "cluster_identity_" in str(failure.value)
    # §8.3:此類不符恆為 permanent → production main 以 exit 78 收場(不重試)。
    from ml_training import alr_application_identity as app_identity

    assert app_identity.is_permanent_pre_db_error(failure.value)


_IDENTITY_OVER_GRANT_PROBES = (
    ("identity_insert", "INSERT INTO learning.alr_runtime_cluster_identity_v1 "
     "SELECT * FROM learning.alr_runtime_cluster_identity_v1 WHERE false"),
    ("identity_update", "UPDATE learning.alr_runtime_cluster_identity_v1 "
     "SET binding_nonce = 'forged'"),
    ("identity_delete", "DELETE FROM learning.alr_runtime_cluster_identity_v1"),
    ("identity_truncate", "TRUNCATE learning.alr_runtime_cluster_identity_v1"),
)


@pytest.mark.parametrize("name,statement", _IDENTITY_OVER_GRANT_PROBES)
def test_cluster_identity_row_is_read_only_for_the_scanner(cluster, name, statement):
    connection = _role_connection(cluster["socket_dir"], autocommit=True)
    try:
        with pytest.raises(psycopg2.Error) as denial:
            connection.cursor().execute(statement)
        assert denial.value.pgcode == "42501", (name, denial.value.pgcode)
    finally:
        connection.close()


def test_manifest_lists_exactly_the_identity_relation_select_grant():
    entries = {entry["name"]: entry["privileges"] for entry in MANIFEST["tables"]}
    assert entries["learning.alr_runtime_cluster_identity_v1"] == ["SELECT"]
    functions = {entry["name"] for entry in MANIFEST["functions"]}
    assert {"pg_catalog.current_database", "pg_catalog.current_setting"} <= functions
