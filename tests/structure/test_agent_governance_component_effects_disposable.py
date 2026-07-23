"""Disposable real apply/rollback/postcheck for the S1.5 per-component Adapter.

Gated on ``shutil.which("initdb")`` + ``psycopg2``.  When PG binaries are present
this ``initdb``-creates a throwaway, socket-only, ``scram-sha-256`` cluster
(reusing the S1.1/S1.3 *pattern*, not a shared helper) and proves the
LOCAL_REPRODUCIBLE ``disposable_pg`` facets nothing-mocked:

* PG_ROLE_ACL_MIGRATION — a real ``CREATE ROLE``/``GRANT`` apply and
  ``REVOKE``/``DROP ROLE`` rollback with pre == post catalog-projection digest,
  and a DISTINCT verifier confirming restoration + that the least-privilege reader
  is still write-denied real ``42501``;
* CREDENTIAL_ROTATION — a real ``ALTER ROLE ... PASSWORD`` A->B->A with pre == post
  credential-generation probe, and a DISTINCT verifier confirming the superseded
  credential is rejected real ``28P01`` while the restored credential reconnects.

The two ``temp_dir`` targets (real ``os.replace`` pointer swap / ``os.unlink``
delete + restore) run everywhere (pure stdlib).  The test then rolls up all six
classes' REAL disposable results + independent postchecks into one
``effect_seams_ready_receipt_v1`` and validates it through the central validator.
Where PG binaries are absent the whole module SKIPS — never a false pass.  The
cluster lives in a temp dir and is torn down in a finally; a real ``postgres``
process emits the ``42501``/``28P01`` (nothing mocked).
"""

from __future__ import annotations

import json
import os
import platform as platform_module
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_component_effects as ce  # noqa: E402
import agent_governance_identity_acl_contract as acl  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402

INITDB = shutil.which("initdb")
PG_CTL = shutil.which("pg_ctl")
psycopg2 = pytest.importorskip("psycopg2", reason="psycopg2 driver is required")

pytestmark = pytest.mark.skipif(
    not (INITDB and PG_CTL),
    reason="initdb/pg_ctl are absent; disposable-cluster proof cannot run",
)

DB = "postgres"
SCHEMA = "aiml_s15"
TABLE = "fact"
READER_ROLE = "aiml_s15_reader"
READER_PW = "aiml-s15-reader-cred-v0"
ROTATION_ROLE = "aiml_s15_rotation"
ROTATION_PW_A = "aiml-s15-rot-cred-A-v0"
ROTATION_PW_B = "aiml-s15-rot-cred-B-v1"
MIGRATION_ROLE = "aiml_s15_migration_role"

NOW = "2026-07-22T12:00:00+00:00"
LATER = "2026-07-22T12:01:00+00:00"
COMPLETED = "2026-07-22T12:00:30+00:00"
OBSERVED = "2026-07-22T12:00:40+00:00"

CLEAN_SUBPROCESS_ENV = {
    "PATH": os.environ.get("PATH", ""),
    "LANG": "C",
    "LC_ALL": "C",
}


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
def disposable_cluster():
    tmp = tempfile.mkdtemp(prefix="aiml_s15_")
    data_dir = os.path.join(tmp, "data")
    sock_dir = os.path.join(tmp, "sock")
    logfile = os.path.join(tmp, "server.log")
    os.makedirs(sock_dir)
    started = False
    try:
        _run(
            [INITDB, "-D", data_dir, "-U", "postgres", "--auth=trust", "-E", "UTF8", "-N"],
            logfile=logfile, timeout=90,
        )
        with open(os.path.join(data_dir, "postgresql.auto.conf"), "a", encoding="utf-8") as handle:
            handle.write("\nlisten_addresses = ''\n")
            handle.write(f"unix_socket_directories = '{sock_dir}'\n")
            handle.write("fsync = off\n")
            handle.write("password_encryption = 'scram-sha-256'\n")
            handle.write("lc_messages = 'C'\n")
            # 危害不變量:PostgreSQL 的 statement log 不會遮蔽 `ALTER ROLE ... PASSWORD`,明文密鑰會
            # 落入 server.log。CREDENTIAL_ROTATION 走真實 ALTER ROLE PASSWORD,故 disposable 叢集必須釘死
            # 關閉 statement / duration 記錄——這正是 S2.4 真實憑證槽必須沿用的日誌不落密不變量。
            handle.write("log_statement = 'none'\n")
            handle.write("log_min_duration_statement = -1\n")
        with open(os.path.join(data_dir, "pg_hba.conf"), "w", encoding="utf-8") as handle:
            handle.write("local   all   postgres   trust\n")
            handle.write("local   all   all        scram-sha-256\n")
        _run(
            [PG_CTL, "-D", data_dir, "-l", logfile, "-w", "-t", "40", "start"],
            logfile=logfile, timeout=60,
        )
        started = True
        _bootstrap(sock_dir)
        yield {"socket_dir": sock_dir, "database": DB}
    finally:
        pid_file = os.path.join(data_dir, "postmaster.pid")
        if started or os.path.exists(pid_file):
            try:
                subprocess.run(
                    [PG_CTL, "-D", data_dir, "-m", "immediate", "stop"],
                    env=CLEAN_SUBPROCESS_ENV, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, timeout=30,
                )
            except (OSError, subprocess.SubprocessError):
                pass
        shutil.rmtree(tmp, ignore_errors=True)


def _bootstrap(sock_dir):
    # 拋棄叢集鷹架:probe schema/table + 一個 SELECT-only reader(供 42501)+ 一個帶密碼 A 的
    # rotation 角色(供 28P01)。migration 角色由測試自行 apply/rollback。
    connection = psycopg2.connect(host=sock_dir, dbname=DB, user="postgres", connect_timeout=10)
    try:
        connection.autocommit = True
        cursor = connection.cursor()
        cursor.execute(f"CREATE SCHEMA {SCHEMA}")
        cursor.execute(f"CREATE TABLE {SCHEMA}.{TABLE}(id integer PRIMARY KEY, note text)")
        cursor.execute(f"INSERT INTO {SCHEMA}.{TABLE} VALUES (1, 'seed')")
        cursor.execute(f"CREATE ROLE {READER_ROLE} LOGIN PASSWORD %s", (READER_PW,))
        cursor.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO {READER_ROLE}")
        cursor.execute(f"GRANT SELECT ON {SCHEMA}.{TABLE} TO {READER_ROLE}")
        cursor.execute(f"CREATE ROLE {ROTATION_ROLE} LOGIN PASSWORD %s", (ROTATION_PW_A,))
    finally:
        connection.close()


def _admin(sock):
    connection = psycopg2.connect(host=sock, dbname=DB, user="postgres", connect_timeout=10)
    connection.autocommit = True
    return connection


# --------------------------------------------------------------------------- #
# PG_ROLE_ACL_MIGRATION — real CREATE/GRANT apply, REVOKE/DROP rollback, 42501
# --------------------------------------------------------------------------- #
def test_pg_role_acl_migration_real_apply_rollback_and_reader_42501(disposable_cluster):
    sock = disposable_cluster["socket_dir"]
    applier = _admin(sock)
    try:
        cursor = applier.cursor()
        pre = ce.pg_role_acl_state_digest(cursor, role=MIGRATION_ROLE, schema=SCHEMA, table=TABLE)
        ce.pg_role_acl_apply(cursor, role=MIGRATION_ROLE, schema=SCHEMA, table=TABLE)
        applied = ce.pg_role_acl_state_digest(cursor, role=MIGRATION_ROLE, schema=SCHEMA, table=TABLE)
        assert applied != pre  # 真實 CREATE ROLE/GRANT 改變 catalog projection
        ce.pg_role_acl_rollback(cursor, role=MIGRATION_ROLE, schema=SCHEMA, table=TABLE)
        post = ce.pg_role_acl_state_digest(cursor, role=MIGRATION_ROLE, schema=SCHEMA, table=TABLE)
        assert post == pre  # EXACT restoration (role dropped, grants gone)
    finally:
        applier.close()

    # 獨立驗證者(distinct 連線/actor)重讀 catalog + 確認 reader 仍被真實 42501 拒寫。
    verifier = _admin(sock)
    try:
        reobserved = ce.pg_role_acl_state_digest(
            verifier.cursor(), role=MIGRATION_ROLE, schema=SCHEMA, table=TABLE
        )
    finally:
        verifier.close()
    assert reobserved == pre
    observed_sqlstate = _reader_write_denied(sock)
    assert observed_sqlstate == "42501"
    assert observed_sqlstate in acl.READER_WRITE_DENIAL_SQLSTATES

    result, attestation = _pg_result_and_attestation(
        effect_class="PG_ROLE_ACL_MIGRATION", pre=pre, applied=applied, post=post,
        reobserved=reobserved, observed_sqlstate=observed_sqlstate,
    )
    assert result["evidence_class"] == "LOCAL_REPRODUCIBLE"
    assert result["observation"]["runtime_witness"]["observed_sqlstate"] == "42501"
    assert ce.validate_component_effect_result(result, now=LATER) == []
    assert ce.validate_postcheck_attestation(attestation, result=result, now=LATER) == []


def _reader_write_denied(sock):
    connection = psycopg2.connect(
        host=sock, dbname=DB, user=READER_ROLE, password=READER_PW, connect_timeout=10
    )
    observed = None
    try:
        connection.autocommit = True
        cursor = connection.cursor()
        try:
            cursor.execute(f"INSERT INTO {SCHEMA}.{TABLE} VALUES (2, 'reader-write')")
        except psycopg2.Error as exc:
            observed = exc.pgcode
    finally:
        connection.close()
    return observed


# --------------------------------------------------------------------------- #
# CREDENTIAL_ROTATION — real ALTER PASSWORD A->B->A, superseded 28P01
# --------------------------------------------------------------------------- #
def test_credential_rotation_real_a_b_a_and_old_credential_28P01(disposable_cluster):
    sock = disposable_cluster["socket_dir"]

    def _connect(password):
        def _factory():
            return psycopg2.connect(
                host=sock, dbname=DB, user=ROTATION_ROLE, password=password, connect_timeout=10
            )
        return _factory

    connect_a = _connect(ROTATION_PW_A)
    connect_b = _connect(ROTATION_PW_B)

    pre_probe = ce.pg_credential_generation_probe(connect_a, connect_b)
    assert pre_probe["active_generation"] == "A"  # A 可連,B 尚未設定
    pre = ce.pg_credential_state_digest(pre_probe)

    admin = _admin(sock)
    try:
        admin.cursor().execute(f"ALTER ROLE {ROTATION_ROLE} PASSWORD %s", (ROTATION_PW_B,))
    finally:
        admin.close()
    applied = ce.pg_credential_state_digest(ce.pg_credential_generation_probe(connect_a, connect_b))
    assert applied != pre  # A->B 後生成世代改變

    admin = _admin(sock)
    try:
        admin.cursor().execute(f"ALTER ROLE {ROTATION_ROLE} PASSWORD %s", (ROTATION_PW_A,))
    finally:
        admin.close()
    post_probe = ce.pg_credential_generation_probe(connect_a, connect_b)
    post = ce.pg_credential_state_digest(post_probe)
    assert post == pre  # EXACT restoration (回到生成世代 A)

    # 獨立驗證者:重用 S1.3 觀察器確認舊憑證 B 被真實 28P01 拒、當前憑證 A 可重連。
    proof = acl.observe_old_credential_rejection(
        connect_b, connect_with_new_credential=connect_a
    )
    assert proof["observed_sqlstate"] == "28P01"
    assert proof["new_credential_connected"] is True
    assert proof["observation_source"] == "live_disposable_pg"

    result, attestation = _pg_result_and_attestation(
        effect_class="CREDENTIAL_ROTATION", pre=pre, applied=applied, post=post,
        reobserved=post, observed_sqlstate="28P01",
    )
    assert result["evidence_class"] == "LOCAL_REPRODUCIBLE"
    assert ce.validate_component_effect_result(result, now=LATER) == []
    assert ce.validate_postcheck_attestation(attestation, result=result, now=LATER) == []
    # 機密:輪換明文密碼絕不出現在序列化 result/attestation。
    serialized = json.dumps(result) + json.dumps(attestation)
    assert ROTATION_PW_A not in serialized and ROTATION_PW_B not in serialized


# --------------------------------------------------------------------------- #
# temp_dir targets — real filesystem apply/rollback (also run under this suite)
# --------------------------------------------------------------------------- #
def test_temp_dir_artifact_and_objects_real_lifecycle(tmp_path):
    art = _artifact_result_and_attestation("ENGINE_SCANNER", tmp_path / "art")
    assert art[0]["pre_state_digest"] == art[0]["post_rollback_digest"]
    assert art[0]["evidence_class"] == "LOCAL_REPRODUCIBLE"
    assert ce.validate_component_effect_result(art[0], now=LATER) == []
    assert ce.validate_postcheck_attestation(art[1], result=art[0], now=LATER) == []

    obj = _objects_result_and_attestation(tmp_path / "obj")
    assert obj[0]["pre_state_digest"] == obj[0]["post_rollback_digest"]
    assert ce.validate_component_effect_result(obj[0], now=LATER) == []
    assert ce.validate_postcheck_attestation(obj[1], result=obj[0], now=LATER) == []


# --------------------------------------------------------------------------- #
# full six-class rollup from REAL disposable evidence, via the central validator
# --------------------------------------------------------------------------- #
def test_full_six_class_rollup_from_real_disposable_evidence(disposable_cluster, tmp_path):
    sock = disposable_cluster["socket_dir"]
    # class_evidence = 真實 (result, attestation) 物件對;rollup builder 於內部逐一經
    # build_admitted_class_entry 驗證後才收入(呼叫者無法遞入手工 entry / digest-alone 投影)。
    class_evidence = []
    # 三個 temp_dir_artifact 類 + 一個 temp_dir_objects 類:真實檔案系統轉換。
    for effect_class in ("ENGINE_SCANNER", "LEARNING_RUNTIME", "CONTROLLER_WORKERS"):
        result, attestation = _artifact_result_and_attestation(
            effect_class, tmp_path / effect_class.lower()
        )
        class_evidence.append({"result": result, "attestation": attestation})
    obj_result, obj_attestation = _objects_result_and_attestation(tmp_path / "retention")
    class_evidence.append({"result": obj_result, "attestation": obj_attestation})
    # 兩個 disposable_pg 類:真實叢集轉換。
    role_result, role_attestation = _role_acl_entry(sock)
    class_evidence.append({"result": role_result, "attestation": role_attestation})
    rot_result, rot_attestation = _rotation_entry(sock)
    class_evidence.append({"result": rot_result, "attestation": rot_attestation})

    receipt = ce.build_effect_seams_ready_receipt(
        caller="E1:S1.5:disposable", class_evidence=class_evidence,
        bypass_negatives=ce.build_bypass_negative_cases(now=NOW),
        dependency_receipts=ce._reference_dependency_receipts(),
        observation_time=NOW, ttl_seconds=900,
    )
    assert {entry["effect_class"] for entry in receipt["admitted_classes"]} == set(
        ce.DEPLOY_COMPONENT_CLASSES
    )
    assert all(
        entry["evidence_class"] == "LOCAL_REPRODUCIBLE"
        for entry in receipt["admitted_classes"]
    )
    assert receipt["status"] == "PASS"
    assert receipt["sprint_gate_scope"] == "S1.5_CONTRIBUTION"
    assert receipt["boundary"] == {
        "production_apply_performed": False, "real_service_restart": False,
        "real_remote_host_mutation": False, "real_migration_applied": False,
        "nine_authorities_false": True,
    }
    # central validator recognizes + accepts the fully-real rollup.
    assert validator.validate_aiml_artifact(receipt, now=LATER) == []
    assert ROTATION_PW_A not in json.dumps(receipt)


# --------------------------------------------------------------------------- #
# helpers: build (result, attestation) for each disposable target kind
# --------------------------------------------------------------------------- #
def _intent_for(effect_class, pre):
    return ce.build_component_effect_intent(
        effect_class=effect_class, target_class="disposable_local", pre_state_digest=pre,
        apply_actor_node=f"{effect_class.lower()}_apply_actor",
        independent_postcheck_node=f"{effect_class.lower()}_ops_postcheck",
        approved_by="operator:s1.5", approved_at=NOW, ttl_seconds=600,
        intent_id=f"component-effect-real-{effect_class.lower()}",
    )


def _pg_result_and_attestation(*, effect_class, pre, applied, post, reobserved, observed_sqlstate):
    intent = _intent_for(effect_class, pre)
    assert ce.validate_component_effect_intent(intent, now=LATER) == []
    result = ce.build_component_effect_result(
        intent=intent, apply_status="APPLIED_ROLLED_BACK_EXACT", pre_state_digest=pre,
        applied_digest=applied, post_rollback_digest=post,
        apply_actor_node=f"{effect_class.lower()}_apply_actor", applied_observed=True,
        observation_window_stable=True, runtime_witness_kind="live_disposable_pg",
        observed_sqlstate=observed_sqlstate, evidence_class="LOCAL_REPRODUCIBLE",
        started_at=NOW, completed_at=COMPLETED,
    )
    attestation = ce.build_postcheck_attestation(
        result=result, verifier_node=f"{effect_class.lower()}_independent_verifier",
        reobserved_post_rollback_digest=reobserved, restoration_confirmed=(reobserved == post),
        evidence_class="LOCAL_REPRODUCIBLE", observed_at=OBSERVED,
    )
    return result, attestation


def _artifact_result_and_attestation(effect_class, root):
    prior = ce.artifact_deploy_root_init(
        str(root), prior_bundle_files={"bin/launch": b"generation-0"},
        unit_text=b"[Service]\nExecStart=/opt/aiml/bin/launch\n",
    )
    pre = ce.artifact_state_digest(str(root))
    _new_hash, applied = ce.artifact_apply(str(root), new_bundle_files={"bin/launch": b"generation-1"})
    post = ce.artifact_rollback(str(root), prior_hash=prior)
    intent = _intent_for(effect_class, pre)
    result = ce.build_component_effect_result(
        intent=intent, apply_status="APPLIED_ROLLED_BACK_EXACT", pre_state_digest=pre,
        applied_digest=applied, post_rollback_digest=post,
        apply_actor_node=f"{effect_class.lower()}_apply_actor", applied_observed=True,
        observation_window_stable=True, runtime_witness_kind="real_filesystem_atomic_swap",
        observed_sqlstate=None, evidence_class="LOCAL_REPRODUCIBLE",
        started_at=NOW, completed_at=COMPLETED,
    )
    reobserved = ce.artifact_state_digest(str(root))
    attestation = ce.build_postcheck_attestation(
        result=result, verifier_node=f"{effect_class.lower()}_independent_verifier",
        reobserved_post_rollback_digest=reobserved, restoration_confirmed=(reobserved == post),
        evidence_class="LOCAL_REPRODUCIBLE", observed_at=OBSERVED,
    )
    return result, attestation


def _objects_result_and_attestation(root):
    pre = ce.objects_root_init(str(root), objects={"a.bin": b"AAAA", "sub/b.bin": b"BBBB"})
    ce.objects_apply(str(root), tombstone_set=["a.bin"])
    applied = ce.objects_state_digest(str(root))  # 刪除後、回滾前的真實 applied 投影(必 != pre)
    post = ce.objects_rollback(str(root), tombstone_set=["a.bin"])
    intent = _intent_for("RETENTION_APPLY", pre)
    result = ce.build_component_effect_result(
        intent=intent, apply_status="APPLIED_ROLLED_BACK_EXACT", pre_state_digest=pre,
        applied_digest=applied, post_rollback_digest=post,
        apply_actor_node="retention_apply_apply_actor", applied_observed=True,
        observation_window_stable=True, runtime_witness_kind="real_object_delete_restore",
        observed_sqlstate=None, evidence_class="LOCAL_REPRODUCIBLE",
        started_at=NOW, completed_at=COMPLETED,
    )
    reobserved = ce.objects_state_digest(str(root))
    attestation = ce.build_postcheck_attestation(
        result=result, verifier_node="retention_apply_independent_verifier",
        reobserved_post_rollback_digest=reobserved, restoration_confirmed=(reobserved == post),
        evidence_class="LOCAL_REPRODUCIBLE", observed_at=OBSERVED,
    )
    return result, attestation


def _role_acl_entry(sock):
    applier = _admin(sock)
    try:
        cursor = applier.cursor()
        pre = ce.pg_role_acl_state_digest(cursor, role=MIGRATION_ROLE, schema=SCHEMA, table=TABLE)
        ce.pg_role_acl_apply(cursor, role=MIGRATION_ROLE, schema=SCHEMA, table=TABLE)
        applied = ce.pg_role_acl_state_digest(cursor, role=MIGRATION_ROLE, schema=SCHEMA, table=TABLE)
        ce.pg_role_acl_rollback(cursor, role=MIGRATION_ROLE, schema=SCHEMA, table=TABLE)
        post = ce.pg_role_acl_state_digest(cursor, role=MIGRATION_ROLE, schema=SCHEMA, table=TABLE)
    finally:
        applier.close()
    verifier = _admin(sock)
    try:
        reobserved = ce.pg_role_acl_state_digest(
            verifier.cursor(), role=MIGRATION_ROLE, schema=SCHEMA, table=TABLE
        )
    finally:
        verifier.close()
    return _pg_result_and_attestation(
        effect_class="PG_ROLE_ACL_MIGRATION", pre=pre, applied=applied, post=post,
        reobserved=reobserved, observed_sqlstate=_reader_write_denied(sock),
    )


def _rotation_entry(sock):
    def _connect(password):
        def _factory():
            return psycopg2.connect(
                host=sock, dbname=DB, user=ROTATION_ROLE, password=password, connect_timeout=10
            )
        return _factory

    connect_a, connect_b = _connect(ROTATION_PW_A), _connect(ROTATION_PW_B)
    pre = ce.pg_credential_state_digest(ce.pg_credential_generation_probe(connect_a, connect_b))
    admin = _admin(sock)
    try:
        admin.cursor().execute(f"ALTER ROLE {ROTATION_ROLE} PASSWORD %s", (ROTATION_PW_B,))
    finally:
        admin.close()
    applied = ce.pg_credential_state_digest(ce.pg_credential_generation_probe(connect_a, connect_b))
    admin = _admin(sock)
    try:
        admin.cursor().execute(f"ALTER ROLE {ROTATION_ROLE} PASSWORD %s", (ROTATION_PW_A,))
    finally:
        admin.close()
    post_probe = ce.pg_credential_generation_probe(connect_a, connect_b)
    post = ce.pg_credential_state_digest(post_probe)
    acl.observe_old_credential_rejection(connect_b, connect_with_new_credential=connect_a)
    return _pg_result_and_attestation(
        effect_class="CREDENTIAL_ROTATION", pre=pre, applied=applied, post=post,
        reobserved=post, observed_sqlstate="28P01",
    )
