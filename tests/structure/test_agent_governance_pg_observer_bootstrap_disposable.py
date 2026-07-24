"""Disposable-cluster (real SQLSTATE) proof for the S2.0 observer-bootstrap Adapter.

Gated on ``shutil.which("initdb")`` + ``psycopg2``.  When PG binaries are present this
``initdb``-creates a throwaway, socket-only, ``scram-sha-256`` cluster (reusing the
S1.1/S1.3/S1.5 *pattern*, not a shared helper) and proves nothing-mocked:

* idempotence — the apply -> rollback cycle returns the catalog to its exact baseline
  (pre == post) every time;
* partial-failure rollback — a mid-apply fault still rolls back to pre == post and the
  observer is gone;
* replay rejection — a stale ``now`` / expired TTL fails closed;
* denial proofs — a DISTINCT verifier connects (via a non-superuser assume role) AS the
  NOLOGIN observer and observes real ``42501`` (write + SET ROLE escalation), a harmless
  search_path reset, and a real ``28P01`` credential escalation;
* fail-closed without an operator SSHSIG — EXTERNAL_VERIFICATION_PENDING and NO observer
  is created;
* full APPLIED_ROLLED_BACK_EXACT receipt round-trip through the central validator + a
  forgery (flip a const-false boundary / swap a bound digest -> rejected) and the
  three-way closure binding.

Where PG binaries are absent the WHOLE module SKIPS honestly — never a false pass.  A
real ``postgres`` process emits the ``42501``/``28P01`` (nothing mocked); production PG
is never contacted.
"""

from __future__ import annotations

import copy
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
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_pg_observer_bootstrap as obs  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402

INITDB = shutil.which("initdb")
PG_CTL = shutil.which("pg_ctl")
psycopg2 = pytest.importorskip("psycopg2", reason="psycopg2 driver is required")

pytestmark = pytest.mark.skipif(
    not (INITDB and PG_CTL),
    reason="initdb/pg_ctl are absent; the disposable observer-bootstrap proof cannot run",
)

DB = "postgres"
SCHEMA = "aiml_s20"
TABLE = "fact"
OBSERVER = "aiml_s20_observer"
WRITER = "aiml_s20_writer"
ASSUME = "aiml_s20_assume"
ASSUME_PW = "aiml-s20-assume-cred-v0"
WRONG_PW = "aiml-s20-assume-cred-WRONG"

HEAD = "0123456789abcdef0123456789abcdef01234567"
CREATED = "2026-07-24T12:00:00+00:00"
NOW = "2026-07-24T12:01:00+00:00"
LATER = "2026-07-24T12:02:00+00:00"
STALE = "2026-07-24T13:30:00+00:00"  # 過期(created + 90min > 15min TTL)

CLEAN_SUBPROCESS_ENV = {"PATH": os.environ.get("PATH", ""), "LANG": "C", "LC_ALL": "C"}


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
    tmp = tempfile.mkdtemp(prefix="aiml_s20_")
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
        yield {"socket_dir": sock_dir, "database": DB}
    finally:
        if started or os.path.exists(os.path.join(data_dir, "postmaster.pid")):
            try:
                subprocess.run([PG_CTL, "-D", data_dir, "-m", "immediate", "stop"],
                               env=CLEAN_SUBPROCESS_ENV, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=30)
            except (OSError, subprocess.SubprocessError):
                pass
        shutil.rmtree(tmp, ignore_errors=True)


def _bootstrap(sock_dir):
    # schema/table + 一個 writer 角色(SET ROLE 升級目標)+ 一個非 superuser 的 assume login 角色
    # (供以「observer 身分」連線做拒絕證明)。observer 角色由被測 Adapter 自行 apply/rollback。
    connection = psycopg2.connect(host=sock_dir, dbname=DB, user="postgres", connect_timeout=10)
    try:
        connection.autocommit = True
        cur = connection.cursor()
        cur.execute(f"CREATE SCHEMA {SCHEMA}")
        cur.execute(f"CREATE TABLE {SCHEMA}.{TABLE}(id integer PRIMARY KEY, note text)")
        cur.execute(f"INSERT INTO {SCHEMA}.{TABLE} VALUES (1, 'seed')")
        cur.execute(f"CREATE ROLE {WRITER} NOLOGIN")
        cur.execute(f"CREATE ROLE {ASSUME} LOGIN NOSUPERUSER PASSWORD %s", (ASSUME_PW,))
        cur.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO {ASSUME}")
    finally:
        connection.close()


def _admin(sock):
    connection = psycopg2.connect(host=sock, dbname=DB, user="postgres", connect_timeout=10)
    connection.autocommit = True
    return connection


def _intent(target_class="disposable_local", sock="/var/run/postgresql"):
    return obs.build_pg_observer_bootstrap_intent(
        target_class=target_class, target_host="trade-core", database=DB,
        observer_role=OBSERVER, observed_schema=SCHEMA, observed_relations=[TABLE],
        socket_dir=sock, auth_mapping="pg_hba_ident_local",
        applier_node_id="observer_apply_actor", postcheck_node_id="observer_ops_postcheck",
        created_at=CREATED, ttl_seconds=900, source_head=HEAD,
    )


def _install_operator_profile(tmp_path, monkeypatch):
    private_key = tmp_path / "operator"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)], check=True)
    public_key = " ".join(private_key.with_suffix(".pub").read_text(encoding="ascii").split()[:2])
    fingerprint = subprocess.run(
        ["ssh-keygen", "-lf", str(private_key.with_suffix(".pub")), "-E", "sha256"],
        check=True, capture_output=True, text=True,
    ).stdout.split()[1]
    monkeypatch.setattr(obs, "OPERATOR_PUBLIC_KEY", public_key)
    monkeypatch.setattr(obs, "OPERATOR_FINGERPRINT", fingerprint)
    return private_key


def _sign(private_key, intent, source_head):
    authorization = obs.build_operator_authorization(intent=intent, source_head=source_head)
    message = private_key.parent / "observer-permit.json"
    message.write_bytes(obs.canonical_bytes(authorization))
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", str(private_key), "-n",
         obs.OPERATOR_SIGNATURE_NAMESPACE, str(message)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return authorization, message.with_suffix(".json.sig").read_bytes()


def _observer_exists(sock):
    connection = _admin(sock)
    try:
        cur = connection.cursor()
        cur.execute("SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = %s", (OBSERVER,))
        return cur.fetchone() is not None
    finally:
        connection.close()


def _build_verifier_postcheck(sock, intent, grant_set, *, capture_digest):
    """Distinct verifier independently re-derives the observer, observes the real denials, rolls back."""

    verifier = _admin(sock)
    try:
        cur = verifier.cursor()
        obs.observer_bootstrap_apply(cur, grant_set=grant_set)
        cur.execute(f'GRANT "{OBSERVER}" TO "{ASSUME}"')
        session = psycopg2.connect(host=sock, dbname=DB, user=ASSUME, password=ASSUME_PW, connect_timeout=10)
        session.autocommit = True
        try:
            scur = session.cursor()
            scur.execute(f'SET ROLE "{OBSERVER}"')
            write = obs.probe_observer_write_denied(scur, schema=SCHEMA, relation=TABLE)
            set_role = obs.probe_observer_set_role_denied(scur, target_role=WRITER)
            search = obs.probe_observer_search_path_reset_harmless(scur, schema=SCHEMA, relation=TABLE)
        finally:
            session.close()
        cred = obs.probe_credential_escalation_denied(
            lambda: psycopg2.connect(host=sock, dbname=DB, user=ASSUME, password=WRONG_PW, connect_timeout=10)
        )
        cur.execute(f'REVOKE "{OBSERVER}" FROM "{ASSUME}"')
        obs.observer_bootstrap_rollback(cur, grant_set=grant_set)
        reobserved = obs.observer_role_acl_state_digest(cur, role=OBSERVER, schema=SCHEMA, relations=[TABLE])
    finally:
        verifier.close()
    proof = {
        "write_denied": write, "set_role_denied": set_role,
        "search_path_reset_harmless": search, "credential_escalation_denied": cred,
    }
    postcheck = obs.build_pg_observer_bootstrap_postcheck(
        intent=intent, verifier_node=intent["postcheck_node_id"], applier_node=intent["applier_node_id"],
        reobserved_post_rollback_digest=reobserved, read_only_proof=proof,
        verifier_capture_digest=capture_digest, observed_at=NOW,
    )
    return postcheck, proof


# --------------------------------------------------------------------------- #
# (4) denial proofs — real 42501 / SET ROLE / search_path / 28P01
# --------------------------------------------------------------------------- #
def test_denial_proofs_distinct_verifier_as_observer(cluster):
    sock = cluster["socket_dir"]
    intent = _intent(sock=sock)
    grant_set = obs.generate_observer_grant_sql(intent)
    postcheck, proof = _build_verifier_postcheck(sock, intent, grant_set, capture_digest="sha256:" + "e" * 64)
    assert proof["write_denied"]["observed_sqlstate"] == "42501"
    assert proof["set_role_denied"]["observed_sqlstate"] == "42501"
    assert proof["credential_escalation_denied"]["observed_sqlstate"] in obs.CREDENTIAL_DENIAL_SQLSTATES
    assert proof["search_path_reset_harmless"]["harmless"] is True
    assert postcheck["status"] == "PASS"
    assert obs.validate_pg_observer_bootstrap_postcheck(postcheck, now=LATER) == []
    assert validator.validate_aiml_artifact(postcheck, now=LATER) == []
    assert not _observer_exists(sock)  # verifier rolled its own observer back


# --------------------------------------------------------------------------- #
# (1) idempotence — apply/rollback cycle returns to the exact baseline
# --------------------------------------------------------------------------- #
def test_idempotent_apply_rollback_cycle(cluster):
    sock = cluster["socket_dir"]
    intent = _intent(sock=sock)
    grant_set = obs.generate_observer_grant_sql(intent)
    admin = _admin(sock)
    try:
        cur = admin.cursor()
        digests = []
        for _ in range(2):
            pre = obs.observer_role_acl_state_digest(cur, role=OBSERVER, schema=SCHEMA, relations=[TABLE])
            obs.observer_bootstrap_apply(cur, grant_set=grant_set)
            applied = obs.observer_role_acl_state_digest(cur, role=OBSERVER, schema=SCHEMA, relations=[TABLE])
            obs.observer_bootstrap_rollback(cur, grant_set=grant_set)
            post = obs.observer_role_acl_state_digest(cur, role=OBSERVER, schema=SCHEMA, relations=[TABLE])
            assert applied != pre  # real CREATE ROLE/GRANT changed the catalog projection
            assert post == pre     # exact restoration
            digests.append(pre)
        assert digests[0] == digests[1]  # the cycle is idempotent across runs
    finally:
        admin.close()
    assert not _observer_exists(sock)


# --------------------------------------------------------------------------- #
# (2) partial-failure rollback — mid-apply fault still restores pre == post
# --------------------------------------------------------------------------- #
def test_partial_failure_rollback(cluster, tmp_path, monkeypatch):
    sock = cluster["socket_dir"]
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent(sock=sock)
    authorization, signature = _sign(private_key, intent, HEAD)

    def _fault(step):
        if step == "grant_usage":
            raise RuntimeError("injected mid-apply failure")

    admin = _admin(sock)
    try:
        result = obs.apply_observer_bootstrap(
            intent, authorization, signature, now=NOW, source_head=HEAD,
            disposable=admin, apply_fault=_fault,
        )
    finally:
        admin.close()
    assert result["status"] == "ROLLED_BACK_INTERRUPTED"
    assert result["rollback_record"]["status"] == "RESTORED_EXACT"
    assert result["pre_state_digest"] == result["rollback_record"]["post_state_digest"]
    assert not _observer_exists(sock)  # the partially-created observer is gone
    assert obs.validate_pg_observer_bootstrap_result(result, now=LATER) == []


# --------------------------------------------------------------------------- #
# (5) fail-closed without SSHSIG — pending, NO observer created
# --------------------------------------------------------------------------- #
def test_disposable_without_sshsig_is_pending_no_side_effect(cluster):
    sock = cluster["socket_dir"]
    intent = _intent(sock=sock)
    admin = _admin(sock)
    try:
        result = obs.apply_observer_bootstrap(intent, None, None, now=NOW, source_head=HEAD, disposable=admin)
    finally:
        admin.close()
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert not _observer_exists(sock)  # no SSHSIG -> no apply, no side effect


# --------------------------------------------------------------------------- #
# (3) replay rejection — stale now / expired TTL fails closed
# --------------------------------------------------------------------------- #
def test_replay_stale_now_fails_closed(cluster, tmp_path, monkeypatch):
    sock = cluster["socket_dir"]
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent(sock=sock)
    authorization, signature = _sign(private_key, intent, HEAD)
    # 過期 TTL:授權/意圖皆已逾期。
    assert obs.validate_operator_authorization(authorization, signature, intent=intent, source_head=HEAD, now=STALE)
    admin = _admin(sock)
    try:
        with pytest.raises(obs.PgObserverBootstrapError):
            obs.apply_observer_bootstrap(intent, authorization, signature, now=STALE, source_head=HEAD, disposable=admin)
    finally:
        admin.close()
    assert not _observer_exists(sock)


# --------------------------------------------------------------------------- #
# (7) full APPLIED receipt round-trip + forgery + closure binding
# --------------------------------------------------------------------------- #
def test_applied_exact_receipt_round_trip_and_forgery(cluster, tmp_path, monkeypatch):
    sock = cluster["socket_dir"]
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent(sock=sock)
    authorization, signature = _sign(private_key, intent, HEAD)
    grant_set = obs.generate_observer_grant_sql(intent)
    capture_digest = "sha256:" + "e" * 64
    postcheck, _proof = _build_verifier_postcheck(sock, intent, grant_set, capture_digest=capture_digest)

    admin = _admin(sock)
    try:
        result = obs.apply_observer_bootstrap(
            intent, authorization, signature, now=NOW, source_head=HEAD,
            disposable=admin, postcheck=postcheck,
        )
    finally:
        admin.close()

    assert result["status"] == "APPLIED_ROLLED_BACK_EXACT"
    assert result["evidence_class"] == "LOCAL_REPRODUCIBLE"
    assert result["boundary"] == {
        "production_apply_performed": False, "production_running_attested": False,
        "load_verified": False, "nine_authorities_false": True,
    }
    assert result["pre_state_digest"] == result["independent_postcheck"]["reobserved_post_rollback_digest"]
    assert obs.validate_pg_observer_bootstrap_result(result, now=LATER) == []
    assert validator.validate_aiml_artifact(result, now=LATER) == []
    # 機密:operator 私鑰/密碼絕不序列化(SSHSIG 為公開簽章)。
    assert ASSUME_PW not in json.dumps(result)
    assert not _observer_exists(sock)

    # forgery A:翻 const-false boundary + 重簽外層 → 仍被拒。
    forged = copy.deepcopy(result)
    forged["boundary"]["nine_authorities_false"] = False
    forged["self_digest"] = obs.artifact_self_digest(forged)
    assert validator.validate_aiml_artifact(forged, now=LATER)
    # forgery B:抽換 cross-bound 的 pre_state_digest(破壞 rollback post == pre 綁定)+ 重簽外層 → 仍被拒。
    forged_b = copy.deepcopy(result)
    forged_b["pre_state_digest"] = "sha256:" + "0" * 64
    forged_b["self_digest"] = obs.artifact_self_digest(forged_b)
    assert validator.validate_aiml_artifact(forged_b, now=LATER)
    # forgery C:竄改內嵌 postcheck 的 write denial SQLSTATE(破壞 postcheck self_digest + PASS 拒絕碼)+ 重簽外層 → 仍被拒。
    forged_c = copy.deepcopy(result)
    forged_c["independent_postcheck"]["read_only_proof"]["write_denied"]["observed_sqlstate"] = "00000"
    forged_c["self_digest"] = obs.artifact_self_digest(forged_c)
    assert validator.validate_aiml_artifact(forged_c, now=LATER)

    # 三方 closure binding:effect receipt + verifier command_capture_v2(digest==record_digest==bound)。
    capture = {"schema_version": "command_capture_v2", "node_id": "observer_ops_postcheck", "record_digest": capture_digest}
    evidence_by_id = {
        "ev-receipt": None,
        "ev-cap": {"id": "ev-cap", "scope": "runtime", "source": "ops_postcheck",
                   "kind": "command_capture_v2", "digest": capture_digest, "artifact": capture},
    }
    route = {"nodes": [{"id": obs.ADAPTER_ID, "kind": "effect_adapter", "mandatory": True}]}
    fragments = {"ops_preflight": {"evidence_refs": []}, "ops_postcheck": {"evidence_refs": ["ev-cap"]}}
    packet = {
        "authority_refs": [{"class": "claim_evidence", "source": f"{obs.INTENT_SCHEMA_VERSION}:{intent['intent_id']}",
                            "digest": intent["self_digest"]}],
        "acceptance": [{"status": "PASS", "evidence_refs": ["ev-receipt", "ev-cap"]}],
    }
    assert obs.validate_pg_observer_bootstrap_binding(
        packet, route, fragments, evidence_by_id, {"ev-receipt": result}
    ) == []
    # closure 反例:三方 digest 不一致(capture digest 改動)→ 被拒。
    evidence_by_id["ev-cap"]["digest"] = "sha256:" + "1" * 64
    assert obs.validate_pg_observer_bootstrap_binding(
        packet, route, fragments, evidence_by_id, {"ev-receipt": result}
    )
