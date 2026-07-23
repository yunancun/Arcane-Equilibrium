"""Disposable-cluster + temp-dir proof for the LR0B identity/ACL contract (S1.3).

Gated on ``shutil.which("initdb")`` (and ``psycopg2``).  When PG binaries are
present this ``initdb``-creates a throwaway, socket-only cluster (reusing the S1.1
*pattern*, not a shared helper), configured with ``password_encryption=
scram-sha-256`` and a local ``scram-sha-256`` ``pg_hba`` line, seeds the
per-component least-privilege roles, and proves the LOCAL_REPRODUCIBLE facts:

* the component PG roles are distinct and none is a superuser;
* a reader role (``aiml_serving``) is genuinely write-denied — real ``42501``;
* credential rotation of ``aiml_fit_evaluation`` genuinely rejects the *old*
  credential over the scram line — real ``28P01``;
* a real temp dir ``chmod 0700`` / ``stat`` has no group/world bits, and a
  ``0755`` dir is rejected by the contract's mode check.

Then it builds and validates a LOCAL_REPRODUCIBLE ``identity_acl_contract_receipt_v1``.
When the binaries are absent it SKIPS with a clear reason — never a false pass.
The cluster lives in a temp dir and is torn down in a finally.  Nothing is mocked
(a real ``postgres`` process emits the ``42501``/``28P01`` and the mode bits).
"""

from __future__ import annotations

import json
import os
import platform as platform_module
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

import agent_governance_identity_acl_contract as adapter  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402

INITDB = shutil.which("initdb")
PG_CTL = shutil.which("pg_ctl")
psycopg2 = pytest.importorskip("psycopg2", reason="psycopg2 driver is required")

pytestmark = pytest.mark.skipif(
    not (INITDB and PG_CTL),
    reason="initdb/pg_ctl are absent; disposable-cluster proof cannot run",
)

DATABASE = "postgres"
# 元件角色(least-privilege);aiml_fit_evaluation 是憑證輪換目標,aiml_serving 是讀者。
COMPONENT_ROLES = (
    "aiml_engine_scanner",
    "aiml_controller",
    "aiml_fit_evaluation",
    "aiml_serving",
    "aiml_deleter",
    "aiml_observer_ro",
)
SERVING_PW = "aiml-serving-cred-v0"
FIT_OLD_PW = "aiml-fit-cred-old-v0"
FIT_NEW_PW = "aiml-fit-cred-new-v1"
# 乾淨環境:啟動子進程一律不繼承 ambient PG* 路由;lc_messages=C 讓 server 訊息穩定英文。
CLEAN_SUBPROCESS_ENV = {
    "PATH": os.environ.get("PATH", ""),
    "LANG": "C",
    "LC_ALL": "C",
}


def _run(cmd, *, logfile, timeout):
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
    tmp = tempfile.mkdtemp(prefix="aiml_acl_")
    data_dir = os.path.join(tmp, "data")
    sock_dir = os.path.join(tmp, "sock")
    logfile = os.path.join(tmp, "server.log")
    os.makedirs(sock_dir)
    started = False
    try:
        # --auth=trust 供 superuser bootstrap;之後以自寫 pg_hba 把元件角色改成 scram。
        _run(
            [INITDB, "-D", data_dir, "-U", "postgres", "--auth=trust", "-E", "UTF8", "-N"],
            logfile=logfile,
            timeout=90,
        )
        with open(os.path.join(data_dir, "postgresql.auto.conf"), "a", encoding="utf-8") as handle:
            handle.write("\nlisten_addresses = ''\n")
            handle.write(f"unix_socket_directories = '{sock_dir}'\n")
            handle.write("fsync = off\n")
            handle.write("password_encryption = 'scram-sha-256'\n")
            handle.write("lc_messages = 'C'\n")
        # pg_hba:superuser 走 trust 供 bootstrap,其餘一律 scram-sha-256 本地認證。
        with open(os.path.join(data_dir, "pg_hba.conf"), "w", encoding="utf-8") as handle:
            handle.write("local   all   postgres   trust\n")
            handle.write("local   all   all        scram-sha-256\n")
        _run(
            [PG_CTL, "-D", data_dir, "-l", logfile, "-w", "-t", "40", "start"],
            logfile=logfile,
            timeout=60,
        )
        started = True
        _bootstrap_roles(sock_dir)
        yield {"socket_dir": sock_dir, "database": DATABASE}
    finally:
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
    # 以 superuser(trust)建立每元件專用最小權限角色。屬 disposable 叢集鷹架,非 repo migration。
    connection = psycopg2.connect(host=sock_dir, dbname=DATABASE, user="postgres", connect_timeout=10)
    try:
        connection.autocommit = True
        cursor = connection.cursor()
        cursor.execute("CREATE ROLE aiml_engine_scanner LOGIN")
        cursor.execute("CREATE ROLE aiml_controller LOGIN")
        cursor.execute("CREATE ROLE aiml_fit_evaluation LOGIN PASSWORD %s", (FIT_OLD_PW,))
        cursor.execute("CREATE ROLE aiml_serving LOGIN PASSWORD %s", (SERVING_PW,))
        cursor.execute("CREATE ROLE aiml_deleter LOGIN")
        cursor.execute("CREATE ROLE aiml_observer_ro LOGIN")
        cursor.execute("CREATE SCHEMA aiml_probe")
        cursor.execute("CREATE TABLE aiml_probe.fact(id integer PRIMARY KEY, note text)")
        cursor.execute("INSERT INTO aiml_probe.fact VALUES (1, 'seed')")
        # readers:只授 USAGE + SELECT(no writer-for-reader)。
        for reader in ("aiml_serving", "aiml_observer_ro"):
            cursor.execute(f"GRANT USAGE ON SCHEMA aiml_probe TO {reader}")
            cursor.execute(f"GRANT SELECT ON aiml_probe.fact TO {reader}")
        # writers/deleter:各自最小寫入權,證明是互異的最小權限類。
        cursor.execute("GRANT USAGE ON SCHEMA aiml_probe TO aiml_engine_scanner")
        cursor.execute("GRANT INSERT ON aiml_probe.fact TO aiml_engine_scanner")
        cursor.execute("GRANT USAGE ON SCHEMA aiml_probe TO aiml_deleter")
        cursor.execute("GRANT DELETE ON aiml_probe.fact TO aiml_deleter")
    finally:
        connection.close()


@pytest.fixture(scope="module")
def rotation_proof(disposable_cluster):
    # 真實憑證輪換:ALTER aiml_fit_evaluation 密碼 old→new,new 可連、old 被拒(28P01)。
    sock = disposable_cluster["socket_dir"]
    admin = psycopg2.connect(host=sock, dbname=DATABASE, user="postgres", connect_timeout=10)
    try:
        admin.autocommit = True
        admin.cursor().execute("ALTER ROLE aiml_fit_evaluation PASSWORD %s", (FIT_NEW_PW,))
    finally:
        admin.close()

    def _connect_with_new_credential():
        return psycopg2.connect(
            host=sock, dbname=DATABASE, user="aiml_fit_evaluation", password=FIT_NEW_PW, connect_timeout=10
        )

    def _connect_with_old_credential():
        return psycopg2.connect(
            host=sock, dbname=DATABASE, user="aiml_fit_evaluation", password=FIT_OLD_PW, connect_timeout=10
        )

    # new-connects 前置條件已移入可重用函式:new 必須先連上(證明 infra 有效 / role 存在),
    # old 才可被認證為輪換掉的舊憑證。
    proof = adapter.observe_old_credential_rejection(
        _connect_with_old_credential, connect_with_new_credential=_connect_with_new_credential
    )
    # (item #6)指紋只綁非機密槽位身分 + generation,絕不對真實密碼取雜湊(S2.4 可安全沿用)。
    return {
        "proof": proof,
        "old_fingerprint": adapter.credential_slot_fingerprint("aiml_pg_credential_slot", "old"),
        "new_fingerprint": adapter.credential_slot_fingerprint("aiml_pg_credential_slot", "new"),
    }


def test_component_roles_are_distinct_and_non_superuser(disposable_cluster):
    sock = disposable_cluster["socket_dir"]
    connection = psycopg2.connect(host=sock, dbname=DATABASE, user="postgres", connect_timeout=10)
    try:
        connection.autocommit = True
        cursor = connection.cursor()
        cursor.execute(
            "SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolreplication "
            "FROM pg_catalog.pg_roles WHERE rolname = ANY(%s)",
            (list(COMPONENT_ROLES),),
        )
        rows = cursor.fetchall()
    finally:
        connection.close()
    found = {row[0] for row in rows}
    assert found == set(COMPONENT_ROLES), f"missing roles: {set(COMPONENT_ROLES) - found}"
    # 每個元件角色皆非 superuser 且禁用屬性全 false(least-privilege / 互異)。
    for name, rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolreplication in rows:
        assert rolsuper is False, f"{name} is superuser"
        assert not any((rolcreaterole, rolcreatedb, rolbypassrls, rolreplication)), name


def test_reader_role_write_denial_is_real_42501(disposable_cluster):
    # 讀者角色(scram 連線)嘗試寫入被授 SELECT-only 的表 → 真實 42501 insufficient_privilege。
    sock = disposable_cluster["socket_dir"]
    connection = psycopg2.connect(
        host=sock, dbname=DATABASE, user="aiml_serving", password=SERVING_PW, connect_timeout=10
    )
    observed = None
    try:
        connection.autocommit = True
        cursor = connection.cursor()
        try:
            cursor.execute("INSERT INTO aiml_probe.fact VALUES (2, 'reader-write')")
        except psycopg2.Error as exc:
            observed = exc.pgcode
    finally:
        connection.close()
    assert observed == "42501", f"expected 42501 reader write denial, got {observed!r}"
    assert observed in adapter.READER_WRITE_DENIAL_SQLSTATES


def test_credential_rotation_old_credential_rejection_is_real_28P01(rotation_proof):
    # 輪換後以「舊」憑證重連 → 真實 28P01 invalid_password(over scram local line);
    # 且是真正 old-vs-new(新憑證先連上=live 見證),非缺 role / peer 誤判。
    proof = rotation_proof["proof"]
    assert proof["verdict"] == "DENIED"
    assert proof["observed_sqlstate"] == "28P01"
    assert proof["observed_sqlstate"] in adapter.CREDENTIAL_DENIAL_SQLSTATES
    assert proof["observation_source"] == "live_disposable_pg"
    assert proof["new_credential_connected"] is True


def test_missing_role_over_scram_is_not_accepted_on_real_cluster(disposable_cluster):
    # E3 實證關切:真實 disposable PG 上,缺席 role 走 scram 也回 28P01 "password authentication
    # failed"(避免 user 列舉),與輪換掉的舊憑證無法區分。new-connects 前置條件即用來消歧:
    # 缺 role 時新憑證亦連不上 → 拒絕認證為 old-credential 拒絕(不再誤判)。
    sock = disposable_cluster["socket_dir"]

    def _connect_missing_new():
        return psycopg2.connect(
            host=sock, dbname=DATABASE, user="aiml_absent_role", password="new-x", connect_timeout=10
        )

    def _connect_missing_old():
        return psycopg2.connect(
            host=sock, dbname=DATABASE, user="aiml_absent_role", password="old-y", connect_timeout=10
        )

    with pytest.raises(adapter.LeastPrivilegeError) as excinfo:
        adapter.observe_old_credential_rejection(
            _connect_missing_old, connect_with_new_credential=_connect_missing_new
        )
    assert "new credential did not connect" in str(excinfo.value)


def test_socket_dir_acl_mode_is_private_and_world_readable_rejected(tmp_path):
    # 真實 chmod 0700 + stat:無 group/world 位;0755 目錄被契約模式檢查拒絕。
    private_dir = tmp_path / "engine_scanner_sock"
    private_dir.mkdir()
    os.chmod(private_dir, 0o700)
    mode_bits = stat.S_IMODE(os.stat(private_dir).st_mode)
    assert mode_bits & 0o077 == 0
    private_label = "0" + oct(mode_bits)[2:].rjust(3, "0")
    assert adapter._mode_is_private(private_label) is True

    world_dir = tmp_path / "world_readable_sock"
    world_dir.mkdir()
    os.chmod(world_dir, 0o755)
    world_bits = stat.S_IMODE(os.stat(world_dir).st_mode)
    assert world_bits & 0o077 != 0
    world_label = "0" + oct(world_bits)[2:].rjust(3, "0")
    assert adapter._mode_is_private(world_label) is False


def test_disposable_receipt_is_passing_and_reproducible(disposable_cluster, rotation_proof, tmp_path):
    # 以真實觀察組出 LOCAL_REPRODUCIBLE 契約 receipt,且天花板由真實 live 見證背書(非自由 label):
    # 真實 chmod 0700/stat 的 socket mode + 真實 28P01 old-vs-new rotation + 觀察到的 42501 reader 拒寫。
    sock_dir = tmp_path / "engine_scanner_sock"
    sock_dir.mkdir()
    os.chmod(sock_dir, 0o700)
    observed_mode = "0" + oct(stat.S_IMODE(os.stat(sock_dir).st_mode))[2:].rjust(3, "0")

    contract = adapter.canonical_identity_acl_contract(
        old_credential_rejection_proof=rotation_proof["proof"],
        old_fingerprint=rotation_proof["old_fingerprint"],
        new_fingerprint=rotation_proof["new_fingerprint"],
        observed_socket_mode=observed_mode,
        pg_role_write_denial_observed=True,
    )
    receipt = adapter.build_identity_acl_contract_receipt(
        caller="E1:S1.3:disposable",
        platform={
            "os": "darwin" if sys.platform == "darwin" else "linux",
            "arch": platform_module.machine(),
            "postgres_version": "16",
        },
        target_class="disposable_local",
        contract=contract,
        observation_time="2026-07-22T12:00:00+00:00",
        ttl_seconds=3600,
        evidence_class="LOCAL_REPRODUCIBLE",
    )
    assert receipt["status"] == "PASS"
    assert receipt["target_class"] == "disposable_local"
    assert receipt["evidence_class"] == "LOCAL_REPRODUCIBLE"
    assert receipt["secret_scan"]["leaked"] is False
    # LOCAL_REPRODUCIBLE 天花板由真實見證背書(rotation live + socket 真實 chmod/stat)。
    proof = receipt["secret_lifecycle"]["rotation"]["old_credential_rejection_proof"]
    assert proof["observed_sqlstate"] == "28P01"
    assert proof["observation_source"] == "live_disposable_pg"
    assert proof["new_credential_connected"] is True
    assert all(row["mode_source"] == "live_chmod_stat" for row in receipt["socket_dir_acl"])
    assert adapter._has_live_disposable_witness(receipt) is True
    # 機密掃描:輪換用的明文密碼絕不出現在 receipt(只有非機密 slot-id sha256 fingerprint)。
    serialized = json.dumps(receipt)
    assert FIT_OLD_PW not in serialized and FIT_NEW_PW not in serialized and SERVING_PW not in serialized
    assert adapter.validate_identity_acl_contract_receipt(
        receipt, require_success=True, now="2026-07-22T12:05:00+00:00"
    ) == []
    schema = json.loads(adapter.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema_subset_errors(receipt, schema, schema) == []
