"""Disposable-cluster + simulated-owner proof for the S2.1 ALR quiesce-fence Adapter.

Gated on ``shutil.which("initdb")`` + ``psycopg2``.  When PG binaries are present this ``initdb``-creates a
throwaway, socket-only cluster and proves nothing-mocked for the DB-side quiesce evidence: a real
``pg_try_advisory_lock('alr_event_consumer_v1')`` is acquired by an ``aiml_engine_scanner`` backend and observed
**held -> free -> re-held** through a genuine read-only ``pg_locks`` / ``pg_stat_activity`` /
``learning.alr_consumer_events`` read AS the reused S2.0 observer role.  The host-side ownership /
static-guard / fence logic runs against a SIMULATED ``/proc`` + an INJECTED ``systemctl`` + an INJECTED
``fence_ops`` (no live process is ever signalled).  The five operator scenarios (stale / double / rollback
failure / observation-window failure / happy) plus a full QUIESCED receipt round-trip + forgery + the
three-way closure binding run here.

Where PG binaries are absent the WHOLE module SKIPS honestly — never a false pass.  Production PG / the live
ALR ``/proc`` / ``systemctl`` are never contacted.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_alr_quiesce_fence as q  # noqa: E402
import agent_governance_alr_quiesce_inventory as qi  # noqa: E402
import agent_governance_pg_observer_bootstrap as observer  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402

INITDB = shutil.which("initdb")
PG_CTL = shutil.which("pg_ctl")
psycopg2 = pytest.importorskip("psycopg2", reason="psycopg2 driver is required")

pytestmark = pytest.mark.skipif(
    not (INITDB and PG_CTL),
    reason="initdb/pg_ctl are absent; the disposable quiesce-fence proof cannot run",
)

DB = "postgres"
OBSERVER_ROLE = "aiml_s21_observer"
ASSUME_ROLE = "aiml_s21_assume"
SESSION_SCHEMA = "learning"
SESSION_TABLE = "alr_consumer_events"
SESSION_RELATION = f"{SESSION_SCHEMA}.{SESSION_TABLE}"

HEAD = "0123456789abcdef0123456789abcdef01234567"
CREATED = "2026-07-24T12:00:00+00:00"
NOW = "2026-07-24T12:01:00+00:00"
LATER = "2026-07-24T12:02:00+00:00"
CAP = "sha256:" + "e" * 64

# S2.4 §8 system-unit shape: system-level fragment, resolved /run credential + lock paths, content-addressed
# interpreter under the sealed runtimes root + ``-I``, system-slice cgroup, the three §8 Environment= keys.
FRAG = "/etc/systemd/system/arcane-equilibrium-aiml-engine-scanner.service"
FLOCK = "/run/arcane-equilibrium/aiml-engine-scanner/consumer.lock"
_DSN = "/run/credentials/arcane-equilibrium-aiml-engine-scanner.service/pg-dsn"
INTERP = "/opt/arcane-equilibrium/aiml/runtimes/" + "b" * 64 + "/bin/python3"
CG = "/system.slice/arcane-equilibrium-aiml-engine-scanner.service"
SCANNER_UID = 4001  # 非 root 的 engine-scanner uid(§8;fixture value)
CMDLINE = [
    INTERP, "-I", "-m", "ml_training.alr_event_consumer",
    "--dsn-file", _DSN, "--lock-file", FLOCK, "--max-batch", "32",
]
ENVIRON = {
    "ALR_SOURCE_HEAD": HEAD,
    "ALR_EXPECTED_LEARNING_RUNTIME_DIGEST": "sha256:" + "9" * 64,
    "ALR_EXPECTED_COMPATIBILITY_RECEIPT": "sha256:" + "c" * 64,
}
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
    tmp = tempfile.mkdtemp(prefix="aiml_s21_")
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
            handle.write("lc_messages = 'C'\n")
            handle.write("log_statement = 'none'\n")
        with open(os.path.join(data_dir, "pg_hba.conf"), "w", encoding="utf-8") as handle:
            handle.write("local   all   all   trust\n")
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


def _connect(sock, user="postgres"):
    connection = psycopg2.connect(host=sock, dbname=DB, user=user, connect_timeout=10)
    connection.autocommit = True
    return connection


def _bootstrap(sock):
    connection = _connect(sock)
    try:
        cur = connection.cursor()
        cur.execute(f"CREATE SCHEMA {SESSION_SCHEMA}")
        cur.execute(
            f"CREATE TABLE {SESSION_RELATION} ("
            "event_id uuid PRIMARY KEY, session_id uuid, event_kind text, "
            "recorded_at timestamptz NOT NULL DEFAULT clock_timestamp())"
        )
        # ALR 連線身分:advisory lock 的 holder backend(usename 綁回 §3 訊號 #7)。
        cur.execute(f"CREATE ROLE {q.ALR_CONNECTION_ROLE} LOGIN")
        # 重用 S2.0 唯讀 observer grant set 建 observer 角色(O-4:GRANT SELECT on 宣告的 consumer-session relation)。
        grant_set = observer.generate_observer_grant_sql({
            "grant_set_selector": "observer_read_only_v1", "observer_role": OBSERVER_ROLE,
            "observed_schema": SESSION_SCHEMA, "observed_relations": [SESSION_TABLE],
            "auth_mapping": "pg_hba_ident_local",
        })
        observer.observer_bootstrap_apply(cur, grant_set=grant_set)
        cur.execute(f"CREATE ROLE {ASSUME_ROLE} LOGIN")
        cur.execute(f'GRANT "{OBSERVER_ROLE}" TO "{ASSUME_ROLE}"')
    finally:
        connection.close()


def _observer_connection(sock):
    # 以 assume 登入後 SET ROLE observer + 釘死唯讀 session:所有 DB 端證據皆 AS the S2.0 read-only observer 讀。
    connection = psycopg2.connect(host=sock, dbname=DB, user=ASSUME_ROLE, connect_timeout=10)
    connection.autocommit = True
    cur = connection.cursor()
    cur.execute(f'SET ROLE "{OBSERVER_ROLE}"')
    cur.execute("SET default_transaction_read_only = on")
    return connection


# --------------------------------------------------------------------------- #
# simulated ALR owner: acts as BOTH host_probe (run/proc_root/dsn_stat/flock_held)
# AND fence_ops (stop/start).  Manages a temp /proc tree + a real advisory lock.
# --------------------------------------------------------------------------- #
class SimulatedOwner:
    def __init__(self, proc_root, sock, *, main_pid=4242, start_ticks="998877"):
        self.proc_root = Path(proc_root)
        self.sock = sock
        self.pid = main_pid
        self.start_ticks = start_ticks
        self.invocation = "inv-1"
        self.n_restarts = 0
        self.state = "running"
        self.stop_calls = 0
        self.start_calls = 0
        self.start_should_fail = False
        self.stop_causes_restart = False
        self.raise_during_window = False       # FIX-W3-1a:fence 後第一個 window host read 拋錯
        self._window_read_should_raise = False
        self.drift_stable_on_start = False     # E4 gap #2:un-fence 成功但 stable identity 漂移
        self.suppress_session_on_unfence = False  # FIX-C3:un-fence 使 unit 起來但 consumer-session 未回 OPEN
        self.max_batch = "32"                  # --max-batch 值;drift 改此值以漂移 cmdline_digest(仍是合法 ALR cmdline)
        self.session_id = None
        self._admin = _connect(sock)
        self._owner_conn = _connect(sock, user=q.ALR_CONNECTION_ROLE)
        # cluster 為 module-scoped、consumer-session ledger 共享:每個 owner 起始先清空,確保本測試的 session
        # 狀態(OPEN/STOPPED)不被前一測試遺留的未閉合 session 污染(否則 window 的 queue-drained 判斷失準)。
        self._admin.cursor().execute(f"TRUNCATE {SESSION_RELATION}")
        (self.proc_root / "sys" / "kernel" / "random").mkdir(parents=True, exist_ok=True)
        (self.proc_root / "sys" / "kernel" / "random" / "boot_id").write_text(
            "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8"
        )
        self._materialize(self.pid)
        self._acquire_lock()
        self._record_session("SESSION_STARTED", new=True)

    # -- lifecycle (fence_ops interface) ------------------------------------ #
    def stop(self):
        self.stop_calls += 1
        if self.raise_during_window:
            # fence 完成後,讓第一個 window 取樣的 host read(systemctl show)拋錯(模擬 mid-window host/DB 讀取失敗)。
            self._window_read_should_raise = True
        if self.stop_causes_restart:
            # scenario #4:一個 supervening restart 贏了 stop 的競賽(NRestarts++ / new InvocationID)。
            self.n_restarts += 1
            self.invocation = "inv-restarted"
            self.state = "restarted"
            return
        self._release_lock()
        self._remove_proc(self.pid)
        self._record_session("SESSION_STOPPED")
        self.state = "fenced"

    def start(self):
        self.start_calls += 1
        if self.start_should_fail:
            raise RuntimeError("injected system-level systemctl start failure")
        if self.drift_stable_on_start:
            # un-fence 本身成功、owner 又健康在跑,但 stable-identity 訊號(cmdline_digest)漂移 → pre != post。
            self.max_batch = "64"
        self.pid += 1313
        self.invocation = "inv-2"
        self.state = "running"
        self._materialize(self.pid)
        self._acquire_lock()
        if not self.suppress_session_on_unfence:
            # FIX-C3:預設 un-fence 記一筆 SESSION_STARTED(consumer-session 回 OPEN);抑制時故意不記,
            # 讓 post-unfence 的 consumer_session_status 停在 STOPPED(unit 起來、lock 重持,但 owner 訊號未全復)。
            self._record_session("SESSION_STARTED", new=True)

    # -- host_probe interface ----------------------------------------------- #
    def run(self, argv):
        if self._window_read_should_raise:
            raise RuntimeError("injected mid-window host read failure")
        if argv[:3] == [q.SYSTEMD, "show", q.UNIT_NAME]:
            return self._show_dump()
        if argv[:2] == [q.SYSTEMD, "list-units"]:
            return ""  # 無 active .scope 匹配(double-owner 以第二個 /proc 候選表達)
        raise AssertionError(f"unexpected systemctl argv: {argv}")

    def dsn_stat(self):
        return {
            "dsn_file_path": _DSN,
            "dsn_mode": "0600", "dsn_owner_uid": SCANNER_UID, "world_readable": False,
        }

    def flock_held(self):
        return self.state != "fenced"

    # -- internals ---------------------------------------------------------- #
    def _show_dump(self):
        if self.state == "fenced":
            props = {"LoadState": "loaded", "ActiveState": "inactive", "SubState": "dead",
                     "MainPID": "0", "InvocationID": "", "NRestarts": str(self.n_restarts),
                     "ControlGroup": ""}
        else:
            props = {"LoadState": "loaded", "ActiveState": "active", "SubState": "running",
                     "MainPID": str(self.pid), "InvocationID": self.invocation,
                     "NRestarts": str(self.n_restarts), "ControlGroup": CG}
        props.update({
            "FragmentPath": FRAG, "DropInPaths": "", "NeedDaemonReload": "no",
            "Environment": " ".join(f"{k}={v}" for k, v in ENVIRON.items()),
            "Restart": "on-failure", "RestartUSec": "5s", "TimeoutStopUSec": "30s",
            "WatchdogUSec": "0", "NoNewPrivileges": "yes", "ProtectSystem": "full",
            "PrivateTmp": "yes", "RestrictAddressFamilies": "AF_UNIX AF_INET",
        })
        return "\n".join(f"{key}={props[key]}" for key in q.QUIESCE_SHOW_PROPERTIES)

    def _materialize(self, pid):
        directory = self.proc_root / str(pid)
        directory.mkdir(parents=True, exist_ok=True)
        rest = ["S"] + ["0"] * 30
        rest[19] = self.start_ticks  # /proc/<pid>/stat field 22 (starttime) = token index 19 after ") "
        (directory / "stat").write_text(f"{pid} (python3) " + " ".join(rest) + "\n", encoding="utf-8")
        cmdline = list(CMDLINE)
        cmdline[-1] = self.max_batch  # --max-batch 值(drift 改此值以漂移 stable identity,仍是合法 ALR cmdline)
        (directory / "cmdline").write_bytes(b"\x00".join(a.encode() for a in cmdline) + b"\x00")
        (directory / "environ").write_bytes(
            b"\x00".join(f"{k}={v}".encode() for k, v in ENVIRON.items()) + b"\x00"
        )
        (directory / "cgroup").write_text(f"0::{CG}\n", encoding="utf-8")

    def add_second_candidate(self, pid):
        # scenario #2:第二個攜 ALR 長壽命 cmdline 的 /proc 候選(candidate_count == 2 → AMBIGUOUS)。
        self._materialize(pid)

    def _remove_proc(self, pid):
        shutil.rmtree(self.proc_root / str(pid), ignore_errors=True)

    def _acquire_lock(self):
        cur = self._owner_conn.cursor()
        cur.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (q.ADVISORY_LOCK_NAME,))
        assert cur.fetchone()[0] is True

    def _release_lock(self):
        cur = self._owner_conn.cursor()
        cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (q.ADVISORY_LOCK_NAME,))

    def free_lock_and_gone(self):
        # scenario #1:owner 已消失——釋放 advisory lock、移除 /proc、記 STOPPED(expected owner is gone)。
        self._release_lock()
        self._remove_proc(self.pid)
        self._record_session("SESSION_STOPPED")
        self.state = "fenced"

    def _record_session(self, kind, *, new=False):
        if new:
            self.session_id = str(uuid.uuid4())
        cur = self._admin.cursor()
        cur.execute(
            f"INSERT INTO {SESSION_RELATION}(event_id, session_id, event_kind) VALUES (%s::uuid, %s::uuid, %s)",
            (str(uuid.uuid4()), self.session_id, kind),
        )

    def close(self):
        for connection in (self._owner_conn, self._admin):
            try:
                connection.close()
            except Exception:  # pragma: no cover - best effort  # noqa: BLE001
                pass


def _stepping_clock(step=5.0):
    state = {"t": -step}

    def _clock():
        state["t"] += step
        return state["t"]

    return _clock


def _install_operator_profile(tmp_path, monkeypatch):
    private_key = tmp_path / "operator"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)], check=True)
    public_key = " ".join(private_key.with_suffix(".pub").read_text(encoding="ascii").split()[:2])
    fingerprint = subprocess.run(
        ["ssh-keygen", "-lf", str(private_key.with_suffix(".pub")), "-E", "sha256"],
        check=True, capture_output=True, text=True,
    ).stdout.split()[1]
    monkeypatch.setattr(q, "OPERATOR_PUBLIC_KEY", public_key)
    monkeypatch.setattr(q, "OPERATOR_FINGERPRINT", fingerprint)
    return private_key


_SIGN_SEQ = [0]


def _sign(private_key, intent, source_head):
    authorization = q.build_operator_authorization(intent=intent, source_head=source_head)
    _SIGN_SEQ[0] += 1
    message = private_key.parent / f"quiesce-permit-{_SIGN_SEQ[0]}.json"
    message.write_bytes(q.canonical_bytes(authorization))
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", str(private_key), "-n", q.OPERATOR_SIGNATURE_NAMESPACE, str(message)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return authorization, message.with_suffix(".json.sig").read_bytes()


def _intent(expected_fingerprint, *, target_class="disposable_local", window=None):
    return q.build_quiesce_intent(
        target_class=target_class, target_host="trade-core", unit_fragment_path=FRAG,
        expected_owner_fingerprint=expected_fingerprint, flock_path=FLOCK,
        observed_relations=[SESSION_RELATION], consumer_session_relation=SESSION_RELATION,
        observation_window=window or {"duration_seconds": 5, "min_samples": 2, "sample_interval_seconds": 5},
        applier_node_id="quiesce_apply", postcheck_node_id="quiesce_verify",
        created_at=CREATED, ttl_seconds=900, source_head=HEAD,
    )


def _expected_fingerprint(owner, observer_conn):
    # build_owner_inventory 的第二引數是**cursor**(apply 內部以 db_observer.cursor() 供給);此處自建一個。
    probe = _intent("sha256:" + "0" * 64)
    inventory = q.build_owner_inventory(owner, observer_conn.cursor(), intent=probe)
    return inventory["owner_fingerprint"], inventory


@pytest.fixture
def owner(cluster, tmp_path):
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    simulated = SimulatedOwner(proc_root, cluster["socket_dir"])
    try:
        yield simulated
    finally:
        simulated.close()


# --------------------------------------------------------------------------- #
# (5) happy path — confirmed -> fenced -> window held -> un-fenced -> pre==post
# --------------------------------------------------------------------------- #
def test_happy_confirmed_apply_fence_observe_unfence(owner, cluster, tmp_path, monkeypatch):
    observer_conn = _observer_connection(cluster["socket_dir"])
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    expected, pre_inv = _expected_fingerprint(owner, observer_conn)
    assert pre_inv["db_quiesce"]["advisory_lock_held"] is True  # advisory lock HELD before fence
    assert pre_inv["advisory_holder_usename"] == q.ALR_CONNECTION_ROLE
    intent = _intent(expected)
    authorization, signature = _sign(private_key, intent, HEAD)

    result = q.apply_quiesce_fence(
        intent, authorization, signature, now=NOW, source_head=HEAD,
        host_probe=owner, fence_ops=owner, db_observer=observer_conn, clock=_stepping_clock(),
        verifier_capture_digest=CAP,
    )
    assert result["status"] == "QUIESCED_STATIC_GUARDS_HELD"
    assert result["evidence_class"] == "LOCAL_REPRODUCIBLE"
    assert result["boundary"] == {
        "production_fence_performed": False, "production_running_attested": False,
        "live_alr_owner_fenced": False, "nine_authorities_false": True,
    }
    # real advisory-lock lifecycle observed AS the S2.0 observer: HELD (pre) -> FREE (window) -> RE-HELD (post)
    assert result["pre_fence_observation"]["db_quiesce"]["advisory_lock_held"] is True
    assert all(s["db_quiesce"]["advisory_lock_held"] is False for s in result["window_samples"])
    assert all(s["db_quiesce"]["consumer_session_status"] == "STOPPED" for s in result["window_samples"])
    assert result["post_unfence_observation"]["db_quiesce"]["advisory_lock_held"] is True
    assert result["post_unfence_observation"]["verdict"] == "RESTORED_HEALTHY"
    assert result["rollback_record"]["status"] == "RESTORED"
    assert result["rollback_record"]["pre_fence_owner_fingerprint"] == result["rollback_record"]["post_unfence_owner_fingerprint"]
    assert owner.stop_calls == 1 and owner.start_calls == 1
    assert q.validate_quiesce_fence_result(result, now=LATER) == []
    assert validator.validate_aiml_artifact(result, now=LATER) == []
    # no operator secret / DSN content serialized
    assert "password" not in json.dumps(result).lower()
    observer_conn.close()

    # three-way closure binding (source-only): receipt + verifier command_capture_v2 in ops_postcheck.
    capture = {"schema_version": "command_capture_v2", "node_id": "quiesce_verify", "record_digest": CAP}
    evidence_by_id = {
        "ev-receipt": None,
        "ev-cap": {"id": "ev-cap", "scope": "runtime", "source": "ops_postcheck",
                   "kind": "command_capture_v2", "digest": CAP, "artifact": capture},
    }
    route = {"nodes": [{"id": q.ADAPTER_ID, "kind": "effect_adapter", "mandatory": True}]}
    fragments = {"ops_preflight": {"evidence_refs": []}, "ops_postcheck": {"evidence_refs": ["ev-cap"]}}
    packet = {
        "authority_refs": [{"class": "claim_evidence", "source": f"{q.INTENT_SCHEMA_VERSION}:{intent['intent_id']}",
                            "digest": intent["self_digest"]}],
        "acceptance": [{"status": "PASS", "evidence_refs": ["ev-receipt", "ev-cap"]}],
    }
    assert q.validate_quiesce_fence_binding(packet, route, fragments, evidence_by_id, {"ev-receipt": result}) == []
    # closure negative:三方 digest 不一致 → 被拒。
    evidence_by_id["ev-cap"]["digest"] = "sha256:" + "1" * 64
    assert q.validate_quiesce_fence_binding(packet, route, fragments, evidence_by_id, {"ev-receipt": result})


# --------------------------------------------------------------------------- #
# (1) stale owner — expected owner gone -> fail-closed, NO fence attempted
# --------------------------------------------------------------------------- #
def test_stale_owner_fails_closed_no_fence(owner, cluster, tmp_path, monkeypatch):
    observer_conn = _observer_connection(cluster["socket_dir"])
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    expected, _inv = _expected_fingerprint(owner, observer_conn)
    intent = _intent(expected)
    authorization, signature = _sign(private_key, intent, HEAD)
    # owner 消失:釋放 advisory lock + 移除 /proc(expected fingerprint 現在名一個 gone 的 owner)。
    owner.free_lock_and_gone()
    result = q.apply_quiesce_fence(
        intent, authorization, signature, now=NOW, source_head=HEAD,
        host_probe=owner, fence_ops=owner, db_observer=observer_conn, clock=_stepping_clock(),
        verifier_capture_digest=CAP,
    )
    assert result["status"] == "STALE_OWNER_FAIL_CLOSED"
    assert result["pre_fence_observation"]["verdict"] == "STALE_OWNER"
    assert result["window_samples"] == []
    assert result["rollback_record"] is None
    assert owner.stop_calls == 0  # 絕不 fence 一個 gone/不確定的 owner
    assert q.validate_quiesce_fence_result(result, now=LATER) == []
    assert validator.validate_aiml_artifact(result, now=LATER) == []
    observer_conn.close()


# --------------------------------------------------------------------------- #
# (2) double owner — two ALR candidates -> refuse, no guess, NO fence
# --------------------------------------------------------------------------- #
def test_double_owner_refused_no_fence(owner, cluster, tmp_path, monkeypatch):
    observer_conn = _observer_connection(cluster["socket_dir"])
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    expected, _inv = _expected_fingerprint(owner, observer_conn)
    intent = _intent(expected)
    authorization, signature = _sign(private_key, intent, HEAD)
    owner.add_second_candidate(owner.pid + 7)  # 第二個 ALR-cmdline /proc 候選 → candidate_count == 2
    result = q.apply_quiesce_fence(
        intent, authorization, signature, now=NOW, source_head=HEAD,
        host_probe=owner, fence_ops=owner, db_observer=observer_conn, clock=_stepping_clock(),
        verifier_capture_digest=CAP,
    )
    assert result["status"] == "AMBIGUOUS_OWNER_REFUSED"
    assert result["pre_fence_observation"]["verdict"] == "AMBIGUOUS_MULTIPLE_OWNERS"
    assert result["pre_fence_observation"]["candidate_count"] == 2
    assert owner.stop_calls == 0
    assert q.validate_quiesce_fence_result(result, now=LATER) == []
    assert validator.validate_aiml_artifact(result, now=LATER) == []
    observer_conn.close()


# --------------------------------------------------------------------------- #
# (3) rollback failure — un-fence fails -> typed NOT_RESTORED (no fake success)
# --------------------------------------------------------------------------- #
def test_rollback_failure_not_restored(owner, cluster, tmp_path, monkeypatch):
    observer_conn = _observer_connection(cluster["socket_dir"])
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    expected, _inv = _expected_fingerprint(owner, observer_conn)
    intent = _intent(expected)
    authorization, signature = _sign(private_key, intent, HEAD)
    owner.start_should_fail = True  # un-fence 會失敗
    result = q.apply_quiesce_fence(
        intent, authorization, signature, now=NOW, source_head=HEAD,
        host_probe=owner, fence_ops=owner, db_observer=observer_conn, clock=_stepping_clock(),
        verifier_capture_digest=CAP,
    )
    assert result["status"] == "NOT_RESTORED"
    assert result["rollback_record"]["status"] == "NOT_RESTORED"
    assert result["post_unfence_observation"]["verdict"] == "NOT_RESTORED"
    # owner 未回到健康的 stable identity(un-fence 失敗)→ stable pre != post
    assert result["rollback_record"]["pre_fence_owner_fingerprint"] != result["rollback_record"]["post_unfence_owner_fingerprint"]
    assert owner.stop_calls == 1 and owner.start_calls == 1  # 仍嘗試了 un-fence
    assert q.validate_quiesce_fence_result(result, now=LATER) == []
    assert validator.validate_aiml_artifact(result, now=LATER) == []
    observer_conn.close()


# --------------------------------------------------------------------------- #
# (4) observation-window failure — a supervening restart -> fail-closed, un-fence attempted
# --------------------------------------------------------------------------- #
def test_observation_window_violated(owner, cluster, tmp_path, monkeypatch):
    observer_conn = _observer_connection(cluster["socket_dir"])
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    expected, _inv = _expected_fingerprint(owner, observer_conn)
    intent = _intent(expected)
    authorization, signature = _sign(private_key, intent, HEAD)
    owner.stop_causes_restart = True  # fence 後一個 supervening restart(new InvocationID / NRestarts++)
    result = q.apply_quiesce_fence(
        intent, authorization, signature, now=NOW, source_head=HEAD,
        host_probe=owner, fence_ops=owner, db_observer=observer_conn, clock=_stepping_clock(),
        verifier_capture_digest=CAP,
    )
    assert result["status"] == "OBSERVATION_WINDOW_VIOLATED"
    assert any(s["verdict"] == "RESTART_DETECTED" for s in result["window_samples"])
    assert result["rollback_record"] is not None  # un-fence 仍被嘗試(rollback record present)
    assert owner.stop_calls == 1 and owner.start_calls == 1
    assert q.validate_quiesce_fence_result(result, now=LATER) == []
    assert validator.validate_aiml_artifact(result, now=LATER) == []
    observer_conn.close()


# --------------------------------------------------------------------------- #
# fail-closed without SSHSIG — pending, no fence, no side effect
# --------------------------------------------------------------------------- #
def test_disposable_without_sshsig_is_pending_no_fence(owner, cluster):
    observer_conn = _observer_connection(cluster["socket_dir"])
    expected, _inv = _expected_fingerprint(owner, observer_conn)
    intent = _intent(expected)
    result = q.apply_quiesce_fence(
        intent, None, None, now=NOW, source_head=HEAD,
        host_probe=owner, fence_ops=owner, db_observer=observer_conn, clock=_stepping_clock(),
        verifier_capture_digest=CAP,
    )
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert owner.stop_calls == 0  # 無 SSHSIG → 無 fence，無 side effect
    observer_conn.close()


# --------------------------------------------------------------------------- #
# forgery on a REAL QUIESCED receipt (mirrors S2.0 forgery discipline)
# --------------------------------------------------------------------------- #
def test_quiesced_receipt_forgery_rejected(owner, cluster, tmp_path, monkeypatch):
    observer_conn = _observer_connection(cluster["socket_dir"])
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    expected, _inv = _expected_fingerprint(owner, observer_conn)
    intent = _intent(expected)
    authorization, signature = _sign(private_key, intent, HEAD)
    result = q.apply_quiesce_fence(
        intent, authorization, signature, now=NOW, source_head=HEAD,
        host_probe=owner, fence_ops=owner, db_observer=observer_conn, clock=_stepping_clock(),
        verifier_capture_digest=CAP,
    )
    assert result["status"] == "QUIESCED_STATIC_GUARDS_HELD"
    observer_conn.close()

    # forgery A:翻 const-false boundary + 重簽外層 → 仍被拒。
    forged_a = copy.deepcopy(result)
    forged_a["boundary"]["live_alr_owner_fenced"] = True
    forged_a["self_digest"] = q.artifact_self_digest(forged_a)
    assert validator.validate_aiml_artifact(forged_a, now=LATER)
    # forgery B:把內嵌 window sample 竄改為宣稱 HELD 但 advisory lock 仍 held(破壞 self_digest + allOf)+ 重簽外層。
    forged_b = copy.deepcopy(result)
    forged_b["window_samples"][0]["db_quiesce"]["advisory_lock_held"] = True
    forged_b["self_digest"] = q.artifact_self_digest(forged_b)
    assert validator.validate_aiml_artifact(forged_b, now=LATER)
    # forgery C:把 rollback 竄改為 RESTORED 但 stable pre != post + 重簽外層 → 仍被拒。
    forged_c = copy.deepcopy(result)
    forged_c["rollback_record"]["post_unfence_owner_fingerprint"] = "sha256:" + "0" * 64
    forged_c["rollback_record"]["self_digest"] = q.artifact_self_digest(forged_c["rollback_record"])
    forged_c["self_digest"] = q.artifact_self_digest(forged_c)
    assert validator.validate_aiml_artifact(forged_c, now=LATER)
    # forgery D:armor 外殼合法但 body 夾帶可讀 plaintext 機密 → strict-base64 body 檢查擋下。
    forged_d = copy.deepcopy(result)
    forged_d["operator_signature_pem"] = "-----BEGIN SSH SIGNATURE-----\npassword=hunter2\n-----END SSH SIGNATURE-----\n"
    forged_d["self_digest"] = q.artifact_self_digest(forged_d)
    assert any("operator_signature_pem body is not strict base64" in e
               for e in q.validate_quiesce_fence_result(forged_d, now=LATER))
    assert validator.validate_aiml_artifact(forged_d, now=LATER)


# --------------------------------------------------------------------------- #
# (6) FIX-W3-1a — a mid-window read raises AFTER fence -> typed FAILED, un-fence attempted
# --------------------------------------------------------------------------- #
def test_window_raise_after_fence_is_failed_and_unfence_attempted(owner, cluster, tmp_path, monkeypatch):
    observer_conn = _observer_connection(cluster["socket_dir"])
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    expected, _inv = _expected_fingerprint(owner, observer_conn)
    intent = _intent(expected)
    authorization, signature = _sign(private_key, intent, HEAD)
    owner.raise_during_window = True  # fence 後第一個 window host read 拋錯
    result = q.apply_quiesce_fence(
        intent, authorization, signature, now=NOW, source_head=HEAD,
        host_probe=owner, fence_ops=owner, db_observer=observer_conn, clock=_stepping_clock(),
        verifier_capture_digest=CAP,
    )
    assert result["status"] == "FAILED"
    assert "un-fence attempted" in result["failure_reason"]
    # fence 一經發起就必在 finally 嘗試 un-fence:絕不把 ALR 留在 fenced/down 而無 typed 結果。
    assert owner.stop_calls == 1 and owner.start_calls == 1
    assert result["post_unfence_observation"] is None and result["rollback_record"] is None
    assert q.validate_quiesce_fence_result(result, now=LATER) == []
    assert validator.validate_aiml_artifact(result, now=LATER) == []
    observer_conn.close()


# --------------------------------------------------------------------------- #
# (7) FIX-W3-1c — an underspecified window (non-advancing clock) -> typed FAILED (not VIOLATED)
# --------------------------------------------------------------------------- #
def test_underspecified_window_is_failed_not_violated(owner, cluster, tmp_path, monkeypatch):
    observer_conn = _observer_connection(cluster["socket_dir"])
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    expected, _inv = _expected_fingerprint(owner, observer_conn)
    intent = _intent(expected)
    authorization, signature = _sign(private_key, intent, HEAD)
    monkeypatch.setattr(qi, "MAX_WINDOW_SAMPLES", 3)  # 非前進時鐘快速撞上限(sampler 於 inventory 下層讀此常量)
    result = q.apply_quiesce_fence(
        intent, authorization, signature, now=NOW, source_head=HEAD,
        host_probe=owner, fence_ops=owner, db_observer=observer_conn,
        clock=lambda: 0.0,  # 非前進時鐘 → 永達不到 duration → underspecified(非 VIOLATED)
        verifier_capture_digest=CAP,
    )
    assert result["status"] == "FAILED"
    assert "underspecified" in result["failure_reason"]
    # 全 held(無真 non-held 樣本)→ 這正是 UNDERSPECIFIED 有別於 OBSERVATION_WINDOW_VIOLATED 之處。
    assert result["window_samples"]
    assert all(s["verdict"] == "STATIC_GUARDS_HELD" for s in result["window_samples"])
    assert owner.stop_calls == 1 and owner.start_calls == 1  # un-fence 仍嘗試
    assert q.validate_quiesce_fence_result(result, now=LATER) == []
    assert validator.validate_aiml_artifact(result, now=LATER) == []
    observer_conn.close()


# --------------------------------------------------------------------------- #
# (8) E4 gap #2 — un-fence SUCCEEDS but stable identity drifted -> typed NOT_RESTORED
# --------------------------------------------------------------------------- #
def test_unfence_succeeds_but_drifted_identity_is_not_restored(owner, cluster, tmp_path, monkeypatch):
    observer_conn = _observer_connection(cluster["socket_dir"])
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    expected, _inv = _expected_fingerprint(owner, observer_conn)
    intent = _intent(expected)
    authorization, signature = _sign(private_key, intent, HEAD)
    owner.drift_stable_on_start = True  # un-fence 成功(owner 又健康)但 cmdline_digest 漂移
    result = q.apply_quiesce_fence(
        intent, authorization, signature, now=NOW, source_head=HEAD,
        host_probe=owner, fence_ops=owner, db_observer=observer_conn, clock=_stepping_clock(),
        verifier_capture_digest=CAP,
    )
    assert result["status"] == "NOT_RESTORED"
    assert result["post_unfence_observation"]["verdict"] == "NOT_RESTORED"
    assert result["rollback_record"]["status"] == "NOT_RESTORED"
    assert owner.start_calls == 1  # un-fence 本身成功(start 被呼叫且未拋錯)
    # 但 stable pre != post(cmdline_digest 漂移)→ 誠實 NOT_RESTORED,非假成功。
    assert (result["rollback_record"]["pre_fence_owner_fingerprint"]
            != result["rollback_record"]["post_unfence_owner_fingerprint"])
    assert q.validate_quiesce_fence_result(result, now=LATER) == []
    assert validator.validate_aiml_artifact(result, now=LATER) == []
    observer_conn.close()


# --------------------------------------------------------------------------- #
# (9) FIX-C3 (Codex :1836) — un-fence brings the unit up but an owner signal is missing
#     (consumer-session not OPEN) -> typed NOT_RESTORED, NOT a fake QUIESCED
# --------------------------------------------------------------------------- #
def test_unfence_active_but_session_not_open_is_not_restored(owner, cluster, tmp_path, monkeypatch):
    observer_conn = _observer_connection(cluster["socket_dir"])
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    expected, _inv = _expected_fingerprint(owner, observer_conn)
    intent = _intent(expected)
    authorization, signature = _sign(private_key, intent, HEAD)
    # un-fence 使 unit 起來、advisory lock 由 aiml_engine_scanner 重持、候選 PID==MainPID,但 consumer-session 未回 OPEN。
    owner.suppress_session_on_unfence = True
    result = q.apply_quiesce_fence(
        intent, authorization, signature, now=NOW, source_head=HEAD,
        host_probe=owner, fence_ops=owner, db_observer=observer_conn, clock=_stepping_clock(),
        verifier_capture_digest=CAP,
    )
    # 舊 post_healthy 只看 unit_active + lock + holder + candidate → 會誤判 QUIESCED;FIX-C3 的 confirm-grade
    # 復核發現 consumer_session_status != OPEN → 誠實 NOT_RESTORED。
    assert result["status"] == "NOT_RESTORED"
    assert result["post_unfence_observation"]["verdict"] == "NOT_RESTORED"
    assert result["rollback_record"]["status"] == "NOT_RESTORED"
    assert owner.start_calls == 1  # un-fence 本身成功(start 未拋錯、unit active、lock 重持)
    assert result["post_unfence_observation"]["db_quiesce"]["advisory_lock_held"] is True
    assert result["post_unfence_observation"]["db_quiesce"]["consumer_session_status"] != "OPEN"
    assert q.validate_quiesce_fence_result(result, now=LATER) == []
    assert validator.validate_aiml_artifact(result, now=LATER) == []
    observer_conn.close()


# --------------------------------------------------------------------------- #
# (10) FIX-C4 (Codex :1177) — injected clock jumps past the declared-window deadline
#      before completing -> typed FAILED (bounded), un-fence attempted
# --------------------------------------------------------------------------- #
def _jump_clock(steps):
    seq = list(steps)

    def _clock():
        return float(seq.pop(0)) if len(seq) > 1 else float(seq[0])

    return _clock


def test_window_elapsed_beyond_deadline_is_failed_and_unfence_attempted(owner, cluster, tmp_path, monkeypatch):
    observer_conn = _observer_connection(cluster["socket_dir"])
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    expected, _inv = _expected_fingerprint(owner, observer_conn)
    intent = _intent(expected)  # window {5,2,5} → 硬截止 = duration+interval = 10s
    authorization, signature = _sign(private_key, intent, HEAD)
    # 注入時鐘第二次取樣就跨過宣告窗上限(0 → 100000s),min_samples 尚未湊足 → 硬截止 → typed FAILED、絕不 HELD。
    result = q.apply_quiesce_fence(
        intent, authorization, signature, now=NOW, source_head=HEAD,
        host_probe=owner, fence_ops=owner, db_observer=observer_conn,
        clock=_jump_clock([0.0, 100000.0]), verifier_capture_digest=CAP,
    )
    assert result["status"] == "FAILED"
    assert "deadline" in result["failure_reason"]
    assert owner.stop_calls == 1 and owner.start_calls == 1  # fence 一經發起就在 finally 嘗試 un-fence
    assert result["window_samples"]  # 至少取到第一個 held 樣本(elapsed 0)
    assert q.validate_quiesce_fence_result(result, now=LATER) == []
    assert validator.validate_aiml_artifact(result, now=LATER) == []
    observer_conn.close()
