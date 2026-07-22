"""Disposable real-lifecycle proof for the LR0C runtime choice probe (S1.6).

The ``temp_dir_artifact`` runtime probe (real ``os.replace`` pointer swaps: start via
``artifact_apply``, failure-recovery via ``artifact_apply_interrupted``, stop via
``artifact_rollback``) runs everywhere (pure stdlib) and is proven here with
``pre == post`` EXACT restoration + ``applied != pre`` + a DISTINCT verifier for BOTH
candidates.  The disposable PG-identity seam is ``shutil.which("initdb")``-gated: where
PG binaries are present it ``initdb``-creates a throwaway, socket-only cluster, seeds a
dedicated read-only role plus a writer role, and drives the S1.1 probe to observe a real
``42501`` role-escalation denial (nothing mocked); it binds a REAL
``pg_readonly_identity_receipt_v1`` self-digest.  Where PG binaries are absent the
PG-identity facet SKIPS honestly — never a false PASS — and the filesystem-lifecycle
tests still run.  The cluster lives in a temp dir and is torn down in a finally.

Evidence class: LOCAL_REPRODUCIBLE (a real child interpreter, real hashed trees, a real
``postgres`` process for the ``42501``).  It proves the lifecycle + disposable PG-identity
MECHANISM, not a target-host runtime (that is S2.5).
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

import agent_governance_runtime_choice_probe as rc  # noqa: E402
import agent_governance_component_effects as ce  # noqa: E402
import agent_governance_pg_readonly_identity as pg  # noqa: E402

INITDB = shutil.which("initdb")
PG_CTL = shutil.which("pg_ctl")

OBS = "2026-07-22T12:00:00+00:00"
FRESH = "2026-07-22T12:05:00+00:00"
COMPLETED = "2026-07-22T12:00:30+00:00"
OBSERVED = "2026-07-22T12:00:40+00:00"

RO_ROLE = "aiml_s16_ro"
WRITER_ROLE = "aiml_s16_writer"
DATABASE = "postgres"
CLEAN_SUBPROCESS_ENV = {"PATH": os.environ.get("PATH", ""), "LANG": "C", "LC_ALL": "C"}


# --------------------------------------------------------------------------- #
# filesystem-lifecycle proof (runs everywhere, no server) — the probe ACTUALLY RAN
# --------------------------------------------------------------------------- #
def test_disposable_lifecycle_actually_ran_exact_restoration(tmp_path):
    for candidate_id in (rc.CANDIDATE_OCI, rc.CANDIDATE_FIXED_PATH):
        block = rc.probe_candidate(
            candidate_id, str(tmp_path / candidate_id),
            started_at=OBS, completed_at=COMPLETED, observed_at=OBSERVED,
        )
        # pre == post 精確還原;lifecycle 真的跑過(applied != pre 由 S1.5 result builder 強制)。
        assert block["pre_state_digest"] == block["post_rollback_digest"]
        assert rc.DIGEST_RE.fullmatch(block["pre_state_digest"])
        assert block["apply_actor_node"] != block["postcheck_verifier_node"]
        assert block["evidence_class"] == "LOCAL_REPRODUCIBLE"


def test_start_failure_recovery_stop_transitions_are_real(tmp_path):
    # 直接驅動 S1.5 primitives,逐一觀察 start / failure-recovery / stop 的真實狀態轉換。
    root = str(tmp_path / "lifecycle")
    prior = ce.artifact_deploy_root_init(
        root, prior_bundle_files=rc._prior_bundle(rc.CANDIDATE_FIXED_PATH), unit_text=rc._UNIT_TEXT
    )
    pre = ce.artifact_state_digest(root)
    # FAILURE-RECOVERY:中斷式 apply 從不 swap 指標 → 先前世代仍 active(digest == pre)。
    interrupted = ce.artifact_apply_interrupted(
        root, new_bundle_files=rc._interrupted_bundle(rc.CANDIDATE_FIXED_PATH)
    )
    assert interrupted == pre
    # START:apply 改變 active 世代(applied != pre)。
    _new_hash, applied = ce.artifact_apply(root, new_bundle_files=rc._new_bundle(rc.CANDIDATE_FIXED_PATH))
    assert applied != pre
    # STOP:rollback 回先前內容 hash → 精確還原(post == pre)。
    post = ce.artifact_rollback(root, prior_hash=prior)
    assert post == pre


def test_complete_cleanup_seam_is_backed_by_real_teardown(tmp_path):
    # complete_cleanup seam 不得空宣稱:probe_candidate 於 postcheck 後真實拆除拋棄式佈署根。
    root = tmp_path / "cleanup_root"
    block = rc.probe_candidate(
        rc.CANDIDATE_FIXED_PATH, str(root),
        started_at=OBS, completed_at=COMPLETED, observed_at=OBSERVED,
    )
    # 探針返回後佈署根已消失(teardown+confirm 真的跑過),故 complete_cleanup 有實證背書。
    assert not root.exists()
    proven = {seam["seam_id"] for seam in block["disposable_seams_proven"]}
    assert "complete_cleanup" in proven


def test_complete_cleanup_gate_raises_when_teardown_unconfirmed(tmp_path, monkeypatch):
    # 若拆除未真的移除佈署根,_teardown_and_confirm 確認 path 仍在 → raise;seam 因此無法空宣稱。
    monkeypatch.setattr(rc.shutil, "rmtree", lambda path, ignore_errors=False: None)  # 佯裝拆除但實際沒刪
    with pytest.raises(rc.RuntimeChoiceProbeError):
        rc.probe_candidate(
            rc.CANDIDATE_FIXED_PATH, str(tmp_path / "stuck_root"),
            started_at=OBS, completed_at=COMPLETED, observed_at=OBSERVED,
        )


# --------------------------------------------------------------------------- #
# initdb-gated: real 42501 disposable PG-identity seam
# --------------------------------------------------------------------------- #
pg_required = pytest.mark.skipif(
    not (INITDB and PG_CTL),
    reason="initdb/pg_ctl are absent; the disposable PG-identity seam skips honestly",
)


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
    psycopg2 = pytest.importorskip("psycopg2", reason="psycopg2 driver is required")
    if not (INITDB and PG_CTL):
        pytest.skip("initdb/pg_ctl are absent")
    tmp = tempfile.mkdtemp(prefix="aiml_s16_pg_")
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
        _run(
            [PG_CTL, "-D", data_dir, "-l", logfile, "-w", "-t", "40", "start"],
            logfile=logfile, timeout=60,
        )
        started = True
        _bootstrap_roles(sock_dir, psycopg2)
        yield {"socket_dir": sock_dir, "database": DATABASE}
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


def _bootstrap_roles(sock_dir, psycopg2):
    # 拋棄叢集鷹架:一個唯讀角色(SET ROLE 提權目標=writer)+ 一個 writer 角色。
    connection = psycopg2.connect(host=sock_dir, dbname=DATABASE, user="postgres", connect_timeout=10)
    try:
        connection.autocommit = True
        cursor = connection.cursor()
        cursor.execute(f"CREATE ROLE {WRITER_ROLE} LOGIN")
        cursor.execute(f"CREATE ROLE {RO_ROLE} LOGIN")
        cursor.execute("CREATE SCHEMA aiml_s16_probe")
        cursor.execute("CREATE TABLE aiml_s16_probe.fact(id integer PRIMARY KEY, note text)")
        cursor.execute("INSERT INTO aiml_s16_probe.fact VALUES (1, 'seed')")
        cursor.execute(f"GRANT USAGE ON SCHEMA aiml_s16_probe TO {RO_ROLE}")
        cursor.execute(f"GRANT SELECT ON aiml_s16_probe.fact TO {RO_ROLE}")
    finally:
        connection.close()


@pytest.fixture(scope="module")
def s11_probe_result(disposable_cluster):
    params = pg.build_readonly_connection_params(
        endpoint_class="unix_socket_allowlisted",
        database=disposable_cluster["database"],
        role=RO_ROLE,
        socket_dir=disposable_cluster["socket_dir"],
    )
    return pg.run_readonly_probe(params, escalation_target_role=WRITER_ROLE)


@pg_required
def test_disposable_pg_identity_seam_observes_real_42501(disposable_cluster, s11_probe_result, tmp_path):
    escalation = s11_probe_result.role_escalation_denied
    # 真實 PostgreSQL 語意:唯讀身分 SET ROLE 到非成員角色 → 42501 insufficient_privilege。
    assert escalation["observed_sqlstate"] == "42501"
    assert escalation["verdict"] == "DENIED"
    pg_evidence = {"observed_sqlstate": escalation["observed_sqlstate"], "verdict": escalation["verdict"]}

    block = rc.probe_candidate(
        rc.CANDIDATE_FIXED_PATH, str(tmp_path / "pg_candidate"),
        started_at=OBS, completed_at=COMPLETED, observed_at=OBSERVED,
        pg_identity_evidence=pg_evidence,
    )
    proven = {seam["seam_id"]: seam for seam in block["disposable_seams_proven"]}
    assert "disposable_pg_identity" in proven
    assert proven["disposable_pg_identity"]["verdict"] == "DISPOSABLE_PROVEN"
    assert proven["disposable_pg_identity"]["evidence_class"] == "LOCAL_REPRODUCIBLE"
    # seam 綁定的 42501 evidence_digest 就是規範證據的 canonical digest(validator 據此核對非空宣稱)。
    assert proven["disposable_pg_identity"]["evidence_digest"] == rc._pg_identity_evidence_digest()


@pg_required
def test_pg_identity_evidence_rejects_a_non_42501(tmp_path):
    # 誠實守衛:非 42501 的 PG-identity 證據不得冒充 disposable_pg_identity seam。
    with pytest.raises(rc.RuntimeChoiceProbeError):
        rc.probe_candidate(
            rc.CANDIDATE_OCI, str(tmp_path / "bad_pg"),
            started_at=OBS, completed_at=COMPLETED, observed_at=OBSERVED,
            pg_identity_evidence={"observed_sqlstate": "25006", "verdict": "DENIED"},
        )


@pg_required
def test_end_to_end_choice_receipt_binds_real_s11_receipt_and_pg_seam(disposable_cluster, s11_probe_result, tmp_path):
    escalation = s11_probe_result.role_escalation_denied
    pg_evidence = {"observed_sqlstate": escalation["observed_sqlstate"], "verdict": escalation["verdict"]}

    probes = [
        rc.probe_candidate(
            candidate_id, str(tmp_path / f"e2e_{candidate_id}"),
            started_at=OBS, completed_at=COMPLETED, observed_at=OBSERVED,
            pg_identity_evidence=pg_evidence,
        )
        for candidate_id in (rc.CANDIDATE_OCI, rc.CANDIDATE_FIXED_PATH)
    ]

    # 綁定一張真實 S1.1 pg_readonly_identity_receipt_v1 的 self_digest。
    s11_receipt = pg.build_pg_readonly_identity_receipt(
        caller="E1:S1.6:disposable",
        platform={
            "os": "darwin" if sys.platform == "darwin" else "linux",
            "arch": platform_module.machine(),
            "postgres_version": s11_probe_result.server_version,
        },
        endpoint={
            "endpoint_class": "unix_socket_allowlisted",
            "socket_dir": disposable_cluster["socket_dir"],
            "loopback_host": None, "port": None,
        },
        database=disposable_cluster["database"], role=RO_ROLE, target_class="disposable_local",
        probe_result=s11_probe_result, observation_time=OBS, ttl_seconds=3600,
        evidence_class="LOCAL_REPRODUCIBLE",
    )
    assert s11_receipt["status"] == "PASS"

    receipt_a, receipt_b, comparison = rc._hermetic_s14_dependencies(OBS, str(tmp_path / "s14"))
    receipt = rc.build_learning_runtime_choice_receipt(
        caller="E1:S1.6:disposable", platform=rc.detect_platform(), target_class="disposable_local",
        candidate_probes=probes, runtime_candidate_receipt_a=receipt_a,
        runtime_candidate_receipt_b=receipt_b, runtime_candidate_comparison=comparison,
        effect_seams_ready_receipt_digest=rc._canonical_digest({"s1_5": "effect_seams_ready"}),
        pg_readonly_identity_receipt_digest=s11_receipt["self_digest"],
        observation_time=OBS, ttl_seconds=900,
    )
    assert receipt["status"] == "PASS"
    assert receipt["selection"]["final_choice"] == "content_addressed_fixed_path"
    assert receipt["selection"]["oci_selectable"] is False
    assert receipt["production_running_attested"] is False
    assert receipt["dependency_receipts"]["pg_readonly_identity_receipt_digest"] == s11_receipt["self_digest"]
    # 每候選 disposable_pg_identity seam 皆以真實 42501 為證。
    for block in receipt["candidate_probes"]:
        proven = {seam["seam_id"] for seam in block["disposable_seams_proven"]}
        assert "disposable_pg_identity" in proven
    assert rc.validate_learning_runtime_choice_receipt(receipt, require_success=True, now=FRESH) == []
    # 機密:序列化 receipt 不含任何憑證。
    assert "password" not in json.dumps(receipt).lower()
