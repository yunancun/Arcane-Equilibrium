"""Always-run offline/structural tests for the S2.1 ALR quiesce-fence SOURCE Adapter.

These need NO PostgreSQL and NO real host: they exercise the multi-signal ownership predicate
(CONFIRMED / STALE / AMBIGUOUS verdicts on synthetic inventories), the intent/pending-result/observation/
rollback build+validate round-trips and forgeries, the operator-SSHSIG domain separation (throwaway test
key + monkeypatch), the central-validator delegation, the forbidden name/pattern/pid kill-surface rejection,
and the guardrails the task pins: the frozen classifier digest stays byte-unchanged and PROGRAM_SCHEMA_PATHS
is untouched.  The REAL confirm -> fence -> static-guard window -> un-fence proof against a throwaway PG
advisory lock lives in the disposable sibling; the production/live fence is fail-closed here.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from datetime import datetime, timedelta
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
import aiml_gate_receipt_validator as validator  # noqa: E402

HEAD = "0123456789abcdef0123456789abcdef01234567"
OTHER_HEAD = "fedcba9876543210fedcba9876543210fedcba98"
CREATED = "2026-07-24T12:00:00+00:00"
NOW = "2026-07-24T12:01:00+00:00"
LATER = "2026-07-24T12:02:00+00:00"
FROZEN_CLASSIFIER = (
    "sha256:1cf8c021b066ceeb364e968add074d263cb28d63db421fdc40620e9904d0ddbc"
)
CAP = "sha256:" + "e" * 64

FRAG = "/home/x/.config/systemd/user/openclaw-alr-shadow.service"
FLOCK = "/run/user/1000/alr-shadow/consumer.lock"
CG = "/user.slice/user-1000.slice/user@1000.service/app.slice/openclaw-alr-shadow.service"
CMDLINE = [
    "/usr/bin/python3", "-m", "ml_training.alr_event_consumer",
    "--dsn-file", "/home/x/.config/openclaw/alr-shadow.dsn", "--lock-file", FLOCK, "--max-batch", "32",
]
ENVIRON = {
    "ALR_SOURCE_HEAD": HEAD, "PYTHONPATH": "/srv/BybitOpenClaw/srv/program_code",
    "ALR_EXPECTED_LEARNING_RUNTIME_DIGEST_V2": "sha256:" + "9" * 64,
}
ENV_HASH = q.canonical_digest({k: ENVIRON[k] for k in q.ENV_DECLARED_KEYS if k in ENVIRON})
CMDLINE_DIGEST = q.canonical_digest(CMDLINE)
RUNTIME_DIGEST = "sha256:" + "9" * 64

OWNER_FP = q.compute_owner_fingerprint(
    main_pid=4242, process_start_ticks="998877", boot_id="boot-1", control_group=CG,
    env_hash=ENV_HASH, invocation_id="inv-1", cmdline_digest=CMDLINE_DIGEST,
    runtime_digest=RUNTIME_DIGEST, flock_path=FLOCK,
)
STABLE_FP = q.compute_stable_identity_fingerprint(
    control_group=CG, env_hash=ENV_HASH, cmdline_digest=CMDLINE_DIGEST, runtime_digest=RUNTIME_DIGEST,
)


def _intent(target_class="disposable_local", **overrides):
    kwargs = dict(
        target_class=target_class, target_host="trade-core", unit_fragment_path=FRAG,
        expected_owner_fingerprint=OWNER_FP, flock_path=FLOCK,
        observed_relations=["learning.alr_consumer_events"],
        observation_window={"duration_seconds": 5, "min_samples": 2, "sample_interval_seconds": 5},
        applier_node_id="quiesce_apply", postcheck_node_id="quiesce_verify",
        created_at=CREATED, ttl_seconds=900, source_head=HEAD,
    )
    kwargs.update(overrides)
    return q.build_quiesce_intent(**kwargs)


def _install_operator_profile(tmp_path, monkeypatch):
    private_key = tmp_path / "operator"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)], check=True)
    parts = private_key.with_suffix(".pub").read_text(encoding="ascii").split()
    public_key = " ".join(parts[:2])
    fingerprint = subprocess.run(
        ["ssh-keygen", "-lf", str(private_key.with_suffix(".pub")), "-E", "sha256"],
        check=True, capture_output=True, text=True,
    ).stdout.split()[1]
    monkeypatch.setattr(q, "OPERATOR_PUBLIC_KEY", public_key)
    monkeypatch.setattr(q, "OPERATOR_FINGERPRINT", fingerprint)
    return private_key


_SIGN_SEQ = [0]


def _sign(private_key, intent, source_head, *, namespace=None):
    authorization = q.build_operator_authorization(intent=intent, source_head=source_head)
    _SIGN_SEQ[0] += 1
    message = private_key.parent / f"permit-{_SIGN_SEQ[0]}.json"
    message.write_bytes(q.canonical_bytes(authorization))
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", str(private_key), "-n",
         namespace or q.OPERATOR_SIGNATURE_NAMESPACE, str(message)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    signature = message.with_suffix(".json.sig").read_bytes()
    return authorization, signature


# --------------------------------------------------------------------------- #
# synthetic inventory / observation fixtures (no host, no PG)
# --------------------------------------------------------------------------- #
def _host_inventory(*, main_pid=4242, start_ticks="998877", invocation="inv-1", n_restarts=0,
                    active="active", sub="running", control_group=CG, env_hash=ENV_HASH,
                    cmdline_digest=CMDLINE_DIGEST, runtime_digest=RUNTIME_DIGEST):
    return {
        "owner": {"uid": 1000, "unit": q.UNIT_NAME},
        "process": {
            "main_pid": main_pid, "process_start_ticks": start_ticks,
            "boot_id": "boot-1", "cmdline_digest": cmdline_digest,
        },
        "unit": {
            "load_state": "loaded", "active_state": active, "sub_state": sub,
            "fragment_path": FRAG, "drop_in_paths": "", "need_daemon_reload": "no",
        },
        "cgroup": {"control_group": control_group},
        "env_hash": env_hash,
        "runtime_digest": runtime_digest,
        "restart_policy": {"restart": "on-failure", "restart_usec": "5s", "timeout_stop_usec": "30s"},
        "watchdog": {"watchdog_usec": "0", "n_restarts": n_restarts, "invocation_id": invocation},
        "queue": {
            "listen_channel": q.LISTEN_CHANNEL, "advisory_lock_name": q.ADVISORY_LOCK_NAME,
            "flock_path": FLOCK, "flock_held": True,
        },
    }


def _db(*, held, count, backend, status, drained=True):
    return {
        "advisory_lock_held": held, "advisory_lock_holder_count": count,
        "backend_present": backend, "consumer_session_status": status, "listen_backlog_drained": drained,
    }


def _cred():
    return {
        "dsn_file_path": "/home/x/.config/openclaw/alr-shadow.dsn", "dsn_mode": "0600",
        "dsn_owner_uid": 1000, "world_readable": False, "plaintext_ingress": False,
        "unit_hardening": {
            "no_new_privileges": "yes", "protect_system": "full",
            "private_tmp": "yes", "restrict_address_families": "AF_UNIX AF_INET",
        },
    }


def _confirmed_inventory(**over):
    inv = {
        "host_inventory": _host_inventory(),
        "db_quiesce": _db(held=True, count=1, backend=True, status="OPEN"),
        "credential_exposure": _cred(),
        "candidate_count": 1,
        # FIX-C2:唯一 ALR 候選 PID == unit MainPID(4242)且 MainPID cmdline 為 exact ALR invocation。
        "candidate_pids": [4242],
        "main_pid_invocation_ok": True,
        "advisory_holder_pid": 31337,
        "advisory_holder_usename": q.ALR_CONNECTION_ROLE,
        "main_pid": 4242,
        "proc_present": True,
        "unit_active": True,
        "cgroup_match": True,
        "fragment_path_match": True,
        "scope_conflict": False,
        "owner_fingerprint": OWNER_FP,
        "stable_identity_fingerprint": STABLE_FP,
    }
    inv.update(over)
    return inv


def _observation(phase, verdict, *, candidate_count, host_inventory, db_quiesce, observed_at=NOW,
                 owner_fingerprint=OWNER_FP):
    return q.build_quiesce_observation(
        phase=phase, verdict=verdict, candidate_count=candidate_count, owner_fingerprint=owner_fingerprint,
        host_inventory=host_inventory, db_quiesce=db_quiesce, credential_exposure=_cred(),
        applier_node="quiesce_apply", verifier_node="quiesce_verify", verifier_capture_digest=CAP,
        observed_at=observed_at,
    )


def _quiesced_result(intent, *, authorization, signature):
    pre = _observation("PRE_FENCE_INVENTORY", "CONFIRMED_SINGLE_OWNER", candidate_count=1,
                       host_inventory=_host_inventory(), db_quiesce=_db(held=True, count=1, backend=True, status="OPEN"))
    window = [
        _observation("IN_WINDOW_STATIC_GUARD", "STATIC_GUARDS_HELD", candidate_count=0,
                     host_inventory=_host_inventory(main_pid=0, start_ticks=None, invocation="", active="inactive", sub="dead"),
                     db_quiesce=_db(held=False, count=0, backend=False, status="STOPPED"), observed_at=NOW),
        # 第二個樣本的 observed_at 距首樣本 >= duration_seconds(5s):滿足 FIX-W3-1d 的 window-adequacy 再驗跨度。
        _observation("IN_WINDOW_STATIC_GUARD", "STATIC_GUARDS_HELD", candidate_count=0,
                     host_inventory=_host_inventory(main_pid=0, start_ticks=None, invocation="", active="inactive", sub="dead"),
                     db_quiesce=_db(held=False, count=0, backend=False, status="STOPPED"),
                     observed_at="2026-07-24T12:01:05+00:00"),
    ]
    post = _observation("POST_UNFENCE_RESTORATION", "RESTORED_HEALTHY", candidate_count=1,
                        host_inventory=_host_inventory(main_pid=5555, start_ticks="1002003", invocation="inv-2"),
                        db_quiesce=_db(held=True, count=1, backend=True, status="OPEN"),
                        owner_fingerprint="sha256:" + "7" * 64)
    rollback = q.build_quiesce_rollback(
        intent=intent, pre_fence_stable_fingerprint=STABLE_FP, post_unfence_stable_fingerprint=STABLE_FP,
        owner_healthy=True, observed_at=NOW,
    )
    return q.build_quiesce_fence_result(
        intent=intent, status="QUIESCED_STATIC_GUARDS_HELD", owner_fingerprint=OWNER_FP,
        pre_fence_observation=pre, window_samples=window, post_unfence_observation=post,
        rollback_record=rollback, operator_authorization=authorization, operator_signature=signature,
        apply_actor_node="quiesce_apply", started_at=NOW, completed_at=NOW, evidence_class="LOCAL_REPRODUCIBLE",
    )


# --------------------------------------------------------------------------- #
# intent + forbidden kill-surface
# --------------------------------------------------------------------------- #
def test_intent_round_trip_and_central_delegation():
    intent = _intent()
    assert q.validate_quiesce_fence_intent(intent, now=NOW) == []
    assert validator.validate_aiml_artifact(intent, now=NOW) == []
    # O-4:consumer_session_relation 是宣告的 observed_relations 成員。
    assert intent["consumer_session_relation"] in intent["observed_relations"]


@pytest.mark.parametrize("bad_key", ["pkill", "kill_by_name", "kill_by_pattern", "signal", "pid_list", "pattern", "sigkill"])
def test_intent_rejects_raw_kill_surface(bad_key):
    intent = _intent()
    forged = copy.deepcopy(intent)
    forged[bad_key] = "alr_event_consumer"
    errors = q.validate_quiesce_fence_intent(forged, now=NOW)
    assert any("forbidden raw-command / signal / kill keys" in e for e in errors)


def test_intent_rejects_consumer_relation_not_in_observed():
    with pytest.raises(q.QuiesceFenceError):
        _intent(observed_relations=["learning.other_table"], consumer_session_relation="learning.alr_consumer_events")


def test_intent_rejects_non_qualified_relation():
    with pytest.raises(q.QuiesceFenceError):
        _intent(observed_relations=["alr_consumer_events"], consumer_session_relation="alr_consumer_events")


def test_intent_rejects_cadence_outliving_window():
    # FIX-C4(Codex :1177):duration=1s / min_samples=512 / interval=3600s ⇒ 湊足取樣需 ~511 小時(遠超 TTL)。
    # build 期即拒。
    with pytest.raises(q.QuiesceFenceError):
        _intent(observation_window={"duration_seconds": 1, "min_samples": 512, "sample_interval_seconds": 3600})
    # validator defense-in-depth:偽造一份繞過 build 的 intent 仍被擋。
    forged = copy.deepcopy(_intent())
    forged["observation_window"] = {"duration_seconds": 1, "min_samples": 512, "sample_interval_seconds": 3600}
    forged["self_digest"] = q.artifact_digest_excluding_self(forged)
    assert any("cadence" in e for e in q.validate_quiesce_fence_intent(forged, now=NOW))
    assert validator.validate_aiml_artifact(forged, now=NOW)
    # 邊界:(min_samples-1)*interval == duration 剛好允許(合法節奏)。
    assert q.validate_quiesce_fence_intent(
        _intent(observation_window={"duration_seconds": 10, "min_samples": 3, "sample_interval_seconds": 5}), now=NOW
    ) == []


def test_intent_rejects_hold_window_exceeding_authorization_ttl():
    # FIX-C4-TTL(E2+OPS must-fix-before-EFFECT):fence 最壞持有窗 = duration_seconds + 一步取樣節奏,必須可證地
    # <= min(ttl_seconds, MAX_AUTHORIZATION_TTL=900s)。{duration:3600, min_samples:2, interval:3600, ttl:3600} 通過
    # cadence guard((2-1)*3600=3600<=3600),但 3600+3600=7200 > 900(operator 簽署天花板)且 > 3600(ttl)→ build 期即拒。
    with pytest.raises(q.QuiesceFenceError):
        _intent(
            observation_window={"duration_seconds": 3600, "min_samples": 2, "sample_interval_seconds": 3600},
            ttl_seconds=3600,
        )
    # validator defense-in-depth:偽造一份繞過 build 的內部自洽 intent(ttl_seconds 與 expires_at 一致)仍被擋。
    forged = copy.deepcopy(_intent())
    forged["ttl_seconds"] = 3600
    forged["expires_at"] = q._plus_seconds(forged["created_at"], 3600)
    forged["observation_window"] = {"duration_seconds": 3600, "min_samples": 2, "sample_interval_seconds": 3600}
    forged["self_digest"] = q.artifact_digest_excluding_self(forged)
    assert any("worst-case hold" in e for e in q.validate_quiesce_fence_intent(forged, now=NOW))
    assert validator.validate_aiml_artifact(forged, now=NOW)
    # 邊界:duration+interval == min(ttl_seconds, 900) 剛好允許({895,2,5}:895+5=900<=900,cadence (2-1)*5=5<=895)。
    assert q.validate_quiesce_fence_intent(
        _intent(observation_window={"duration_seconds": 895, "min_samples": 2, "sample_interval_seconds": 5}), now=NOW
    ) == []


# --------------------------------------------------------------------------- #
# ownership predicate verdicts (pure logic, no host / no PG)
# --------------------------------------------------------------------------- #
def test_confirm_single_owner_happy():
    obs = q.confirm_alr_owner(
        _confirmed_inventory(), expected_fingerprint=OWNER_FP, applier_node="quiesce_apply",
        verifier_node="quiesce_verify", verifier_capture_digest=CAP, observed_at=NOW,
    )
    assert obs["verdict"] == "CONFIRMED_SINGLE_OWNER"
    assert obs["candidate_count"] == 1
    assert q.validate_quiesce_observation(obs, now=LATER) == []
    assert validator.validate_aiml_artifact(obs, now=LATER) == []


@pytest.mark.parametrize("mutation", [
    {"proc_present": False},
    {"unit_active": False},
    {"db_quiesce": _db(held=False, count=0, backend=False, status="ABSENT")},
    {"main_pid": 0},
    {"owner_fingerprint": "sha256:" + "1" * 64},          # 期望 owner != live owner → gone
    {"advisory_holder_usename": "postgres"},              # lock holder 非 alr_shadow 身分 → 不 confirm
    {"db_quiesce": _db(held=True, count=1, backend=True, status="STOPPED")},  # session 非 OPEN
    # FIX-C2:唯一候選 PID != unit MainPID(wrapper MainPID + 脫離的 consumer 持鎖)→ 不 confirm → STALE
    {"candidate_pids": [9999]},
    # FIX-C2:MainPID 自身 cmdline 非 exact ALR invocation(wrapper)→ 不 confirm → STALE
    {"main_pid_invocation_ok": False},
])
def test_stale_owner_fails_closed(mutation):
    inv = _confirmed_inventory(**mutation)
    obs = q.confirm_alr_owner(
        inv, expected_fingerprint=OWNER_FP, applier_node="quiesce_apply", verifier_node="quiesce_verify",
        verifier_capture_digest=CAP, observed_at=NOW,
    )
    assert obs["verdict"] == "STALE_OWNER"


@pytest.mark.parametrize("mutation", [
    {"candidate_count": 2},                                                    # 兩個 ALR host 候選
    {"db_quiesce": _db(held=True, count=2, backend=True, status="OPEN")},      # 兩個 advisory holder(防禦性)
    {"scope_conflict": True},                                                  # 另有 active .scope 匹配
])
def test_ambiguous_multiple_owners_refuses(mutation):
    inv = _confirmed_inventory(**mutation)
    obs = q.confirm_alr_owner(
        inv, expected_fingerprint=OWNER_FP, applier_node="quiesce_apply", verifier_node="quiesce_verify",
        verifier_capture_digest=CAP, observed_at=NOW,
    )
    assert obs["verdict"] == "AMBIGUOUS_MULTIPLE_OWNERS"


# --------------------------------------------------------------------------- #
# FIX-C1 (Codex :414): _is_alr_longlived_cmdline requires the EXACT deployed invocation
# --------------------------------------------------------------------------- #
_DSN = "/home/x/.config/openclaw/alr-shadow.dsn"
_DEPLOYED = [
    "/usr/bin/python3", "-m", "ml_training.alr_event_consumer",
    "--dsn-file", _DSN, "--lock-file", FLOCK, "--max-batch", "32",
]


def test_is_alr_longlived_cmdline_accepts_only_exact_deployed_invocation():
    # 精確部署形 → candidate。
    assert q._is_alr_longlived_cmdline(_DEPLOYED, expected_dsn_file=_DSN, expected_lock_file=FLOCK) is True
    # 任務指定的偽形:非 allowlist 解譯器 basename + 錯 dsn/lock 值 + 多餘 --evil → NOT a candidate。
    evil = [
        "python3-debug", "-m", "ml_training.alr_event_consumer",
        "--dsn-file", "/tmp/other.dsn", "--lock-file", "/tmp/other.lock", "--max-batch", "999", "--evil",
    ]
    assert q._is_alr_longlived_cmdline(evil, expected_dsn_file=_DSN, expected_lock_file=FLOCK) is False


@pytest.mark.parametrize("cmdline", [
    ["/usr/bin/python3-debug", "-m", "ml_training.alr_event_consumer",
     "--dsn-file", _DSN, "--lock-file", FLOCK, "--max-batch", "32"],          # basename 非 allowlist(非 startswith)
    ["/usr/bin/python3", "-m", "ml_training.alr_event_consumer",
     "--dsn-file", "/tmp/other.dsn", "--lock-file", FLOCK, "--max-batch", "32"],  # --dsn-file 值不符
    ["/usr/bin/python3", "-m", "ml_training.alr_event_consumer",
     "--dsn-file", _DSN, "--lock-file", "/tmp/other.lock", "--max-batch", "32"],  # --lock-file 值不符
    ["/usr/bin/python3", "-m", "ml_training.alr_event_consumer",
     "--dsn-file", _DSN, "--lock-file", FLOCK, "--max-batch", "0"],            # max-batch 非 bounded(< 1)
    ["/usr/bin/python3", "-m", "ml_training.alr_event_consumer",
     "--dsn-file", _DSN, "--lock-file", FLOCK, "--max-batch", "99999"],        # max-batch 超出 ceiling
    ["/usr/bin/python3", "-m", "ml_training.alr_event_consumer",
     "--dsn-file", _DSN, "--lock-file", FLOCK, "--max-batch", "32", "--extra", "x"],  # 多餘/未知參數
    ["/usr/bin/python3", "-m", "ml_training.other_module",
     "--dsn-file", _DSN, "--lock-file", FLOCK, "--max-batch", "32"],           # 模組不符
])
def test_is_alr_longlived_cmdline_rejects_single_deviation(cmdline):
    assert q._is_alr_longlived_cmdline(cmdline, expected_dsn_file=_DSN, expected_lock_file=FLOCK) is False


# --------------------------------------------------------------------------- #
# FIX-C2 (Codex :779): the confirmed owner's candidate PID must equal the unit MainPID
# --------------------------------------------------------------------------- #
def test_wrapper_mainpid_with_detached_consumer_is_stale_not_confirmed():
    # wrapper 佔住 unit MainPID(4242,自身 cmdline 非 ALR),真正持鎖的 ALR consumer 脫離在 pid 9999:
    # candidate_count 仍為 1、advisory holder 仍是 alr_shadow,但候選 PID(9999)!= MainPID(4242)且 MainPID
    # cmdline 非 exact ALR invocation → 絕不 CONFIRMED(否則 systemctl --user stop 停 wrapper、脫離的 consumer 續跑)。
    inv = _confirmed_inventory(candidate_pids=[9999], main_pid_invocation_ok=False)
    obs = q.confirm_alr_owner(
        inv, expected_fingerprint=OWNER_FP, applier_node="quiesce_apply", verifier_node="quiesce_verify",
        verifier_capture_digest=CAP, observed_at=NOW,
    )
    assert obs["verdict"] == "STALE_OWNER"
    # 反面:候選 PID == MainPID 且 invocation exact → 回到 CONFIRMED。
    assert q._owner_verdict(_confirmed_inventory(), expected_fingerprint=OWNER_FP) == "CONFIRMED_SINGLE_OWNER"


# --------------------------------------------------------------------------- #
# fail-closed pending — no fake success, no kill
# --------------------------------------------------------------------------- #
def test_apply_without_sshsig_is_pending_never_success():
    result = q.apply_quiesce_fence(_intent(), None, None, now=NOW, source_head=HEAD)
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert result["boundary"]["nine_authorities_false"] is True
    assert result["boundary"]["production_fence_performed"] is False
    assert result["boundary"]["live_alr_owner_fenced"] is False
    assert result["pre_fence_observation"] is None and result["rollback_record"] is None
    assert result["window_samples"] == []
    assert validator.validate_aiml_artifact(result, now=LATER) == []


def test_production_apply_with_valid_sshsig_still_pending(tmp_path, monkeypatch):
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent(target_class="production")
    authorization, signature = _sign(private_key, intent, HEAD)
    assert q.validate_operator_authorization(authorization, signature, intent=intent, source_head=HEAD, now=NOW) == []
    result = q.apply_quiesce_fence(intent, authorization, signature, now=NOW, source_head=HEAD)
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert "S2.1 EFFECT session" in result["failure_reason"]
    assert "S2.4" in result["failure_reason"] and "S2.5" in result["failure_reason"]


def test_disposable_valid_sshsig_but_no_injected_probes_is_pending(tmp_path, monkeypatch):
    # 已授權,但缺注入 host_probe/fence_ops/db_observer/clock → SOURCE lane 恆 pending(絕不接觸 live host)。
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent()
    authorization, signature = _sign(private_key, intent, HEAD)
    result = q.apply_quiesce_fence(intent, authorization, signature, now=NOW, source_head=HEAD)
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert "no live /proc/systemctl" in result["failure_reason"]


def test_stale_window_intent_is_pending_not_raise():
    intent = _intent()
    stale = "2026-07-24T13:30:00+00:00"
    result = q.apply_quiesce_fence(intent, None, None, now=stale, source_head=HEAD)
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert "validity window" in result["failure_reason"]
    assert validator.validate_aiml_artifact(result, now=stale) == []


def test_malformed_intent_still_raises_not_pending():
    bad = copy.deepcopy(_intent())
    bad["observed_relations"] = []
    with pytest.raises(q.QuiesceFenceError):
        q.apply_quiesce_fence(bad, None, None, now=NOW, source_head=HEAD)


def test_malformed_now_raises_typed_error_not_bare_valueerror():
    intent = _intent()
    for bad_now in ("not-a-timestamp", "2026-13-40T99:99:99", ""):
        with pytest.raises(q.QuiesceFenceError):
            q.apply_quiesce_fence(intent, None, None, now=bad_now, source_head=HEAD)


# --------------------------------------------------------------------------- #
# operator SSHSIG — domain separation + tamper
# --------------------------------------------------------------------------- #
def test_operator_authorization_valid_and_domain_separated(tmp_path, monkeypatch):
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent()
    authorization, signature = _sign(private_key, intent, HEAD)
    assert q.OPERATOR_SIGNATURE_NAMESPACE == "arcane-equilibrium-aiml-s2-quiesce-fence"
    assert q.OPERATOR_IDENTITY == "aiml-s2-quiesce-fence-operator-v1"
    assert q.validate_operator_authorization(authorization, signature, intent=intent, source_head=HEAD, now=NOW) == []
    # 以 S2.0 observer namespace 簽的相同 permit 在 S2.1 quiesce profile 下因 namespace 不符被拒。
    _auth2, wrong_ns_sig = _sign(private_key, intent, HEAD, namespace="arcane-equilibrium-aiml-s2-observer-bootstrap")
    errors = q.validate_operator_authorization(authorization, wrong_ns_sig, intent=intent, source_head=HEAD, now=NOW)
    assert any("SSH signature is invalid" in e for e in errors)


def test_operator_authorization_rejects_wrong_source_head_and_expiry(tmp_path, monkeypatch):
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent()
    authorization, signature = _sign(private_key, intent, HEAD)
    assert q.validate_operator_authorization(authorization, signature, intent=intent, source_head=OTHER_HEAD, now=NOW)
    stale = (datetime.fromisoformat(CREATED) + timedelta(minutes=30)).isoformat()
    assert q.validate_operator_authorization(authorization, signature, intent=intent, source_head=HEAD, now=stale)


# --------------------------------------------------------------------------- #
# observation / rollback / result build + forgery
# --------------------------------------------------------------------------- #
def test_observation_rejects_applier_equals_verifier():
    with pytest.raises(q.QuiesceFenceError):
        q.build_quiesce_observation(
            phase="PRE_FENCE_INVENTORY", verdict="CONFIRMED_SINGLE_OWNER", candidate_count=1,
            owner_fingerprint=OWNER_FP, host_inventory=_host_inventory(),
            db_quiesce=_db(held=True, count=1, backend=True, status="OPEN"), credential_exposure=_cred(),
            applier_node="same", verifier_node="same", verifier_capture_digest=CAP, observed_at=NOW,
        )


def test_observation_confirmed_requires_single_candidate():
    forged = _observation("PRE_FENCE_INVENTORY", "CONFIRMED_SINGLE_OWNER", candidate_count=2,
                          host_inventory=_host_inventory(), db_quiesce=_db(held=True, count=1, backend=True, status="OPEN"))
    forged["self_digest"] = q.artifact_self_digest(forged)
    assert q.validate_quiesce_observation(forged, now=LATER)
    assert validator.validate_aiml_artifact(forged, now=LATER)


def test_observation_static_guards_held_rejects_still_held_lock():
    # forgery:宣稱 STATIC_GUARDS_HELD 但 advisory lock 仍 held → schema allOf + module 皆拒。
    forged = _observation("IN_WINDOW_STATIC_GUARD", "STATIC_GUARDS_HELD", candidate_count=0,
                          host_inventory=_host_inventory(main_pid=0, start_ticks=None, invocation="", active="inactive", sub="dead"),
                          db_quiesce=_db(held=True, count=1, backend=True, status="OPEN"))
    forged["self_digest"] = q.artifact_self_digest(forged)
    errors = q.validate_quiesce_observation(forged, now=LATER)
    assert errors
    assert validator.validate_aiml_artifact(forged, now=LATER)


def test_rollback_stable_identity_restoration_crux():
    intent = _intent()
    restored = q.build_quiesce_rollback(
        intent=intent, pre_fence_stable_fingerprint=STABLE_FP, post_unfence_stable_fingerprint=STABLE_FP,
        owner_healthy=True, observed_at=NOW,
    )
    assert restored["status"] == "RESTORED"
    assert q.validate_quiesce_rollback(restored, now=LATER) == []
    assert validator.validate_aiml_artifact(restored, now=LATER) == []
    # 非精確 stable 還原(pre != post)不能宣稱 RESTORED。
    not_restored = q.build_quiesce_rollback(
        intent=intent, pre_fence_stable_fingerprint=STABLE_FP, post_unfence_stable_fingerprint="sha256:" + "0" * 64,
        owner_healthy=False, observed_at=NOW,
    )
    assert not_restored["status"] == "NOT_RESTORED"
    # forgery:把 NOT_RESTORED 竄改為 RESTORED(pre != post)+ 重簽 → 仍被拒。
    forged = copy.deepcopy(not_restored)
    forged["status"] = "RESTORED"
    forged["restored_exact"] = True
    forged["owner_healthy"] = True
    forged["self_digest"] = q.artifact_self_digest(forged)
    assert q.validate_quiesce_rollback(forged, now=LATER)


def test_quiesced_result_round_trip(tmp_path, monkeypatch):
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent()
    authorization, signature = _sign(private_key, intent, HEAD)
    result = _quiesced_result(intent, authorization=authorization, signature=signature)
    assert result["status"] == "QUIESCED_STATIC_GUARDS_HELD"
    assert result["evidence_class"] == "LOCAL_REPRODUCIBLE"
    assert result["boundary"] == {
        "production_fence_performed": False, "production_running_attested": False,
        "live_alr_owner_fenced": False, "nine_authorities_false": True,
    }
    assert q.validate_quiesce_fence_result(result, now=LATER) == []
    assert validator.validate_aiml_artifact(result, now=LATER) == []


def test_quiesced_result_forgery_flip_boundary_rejected(tmp_path, monkeypatch):
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent()
    authorization, signature = _sign(private_key, intent, HEAD)
    result = _quiesced_result(intent, authorization=authorization, signature=signature)
    forged = copy.deepcopy(result)
    forged["boundary"]["nine_authorities_false"] = False
    forged["self_digest"] = q.artifact_self_digest(forged)
    assert q.validate_quiesce_fence_result(forged, now=LATER)
    assert validator.validate_aiml_artifact(forged, now=LATER)


def test_quiesced_result_forgery_window_sample_not_held_rejected(tmp_path, monkeypatch):
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent()
    authorization, signature = _sign(private_key, intent, HEAD)
    result = _quiesced_result(intent, authorization=authorization, signature=signature)
    forged = copy.deepcopy(result)
    forged["window_samples"][1]["verdict"] = "RESTART_DETECTED"
    forged["window_samples"][1]["self_digest"] = q.artifact_self_digest(forged["window_samples"][1])
    forged["self_digest"] = q.artifact_self_digest(forged)
    assert any("every in-window sample to hold" in e for e in q.validate_quiesce_fence_result(forged, now=LATER))


def test_quiesced_result_rejects_bogus_operator_authorization(tmp_path, monkeypatch):
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent()
    authorization, signature = _sign(private_key, intent, HEAD)
    result = _quiesced_result(intent, authorization=authorization, signature=signature)
    forged = copy.deepcopy(result)
    forged["operator_authorization"] = {"totally": "bogus"}
    forged["self_digest"] = q.artifact_self_digest(forged)
    assert any("fields do not match the exact contract" in e for e in q.validate_quiesce_fence_result(forged, now=LATER))


# --------------------------------------------------------------------------- #
# operator_signature_pem strict-base64 body (mirror S2.0 FIX-10/11)
# --------------------------------------------------------------------------- #
_PLAINTEXT_SECRET_PEM = "-----BEGIN SSH SIGNATURE-----\npassword=hunter2\n-----END SSH SIGNATURE-----\n"
_VALID_B64_ARMOR = "-----BEGIN SSH SIGNATURE-----\nU1NIU0lHAAAAAQ==\n-----END SSH SIGNATURE-----\n"


def test_operator_signature_pem_body_strict_base64_helper(tmp_path, monkeypatch):
    assert q._operator_signature_pem_body_is_strict_base64(_VALID_B64_ARMOR) is True
    assert q._operator_signature_pem_body_is_strict_base64(_PLAINTEXT_SECRET_PEM) is False
    assert q._operator_signature_pem_body_is_strict_base64(None) is False
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    _auth, real_sig = _sign(private_key, _intent(), HEAD)
    assert q._operator_signature_pem_body_is_strict_base64(real_sig.decode("ascii")) is True


def test_result_validator_rejects_plaintext_secret_pem_body(tmp_path, monkeypatch):
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent()
    authorization, signature = _sign(private_key, intent, HEAD)
    result = _quiesced_result(intent, authorization=authorization, signature=signature)
    forged = copy.deepcopy(result)
    forged["operator_signature_pem"] = _PLAINTEXT_SECRET_PEM
    forged["self_digest"] = q.artifact_self_digest(forged)
    errors = q.validate_quiesce_fence_result(forged, now=LATER)
    assert any("operator_signature_pem body is not strict base64" in e for e in errors)
    assert validator.validate_aiml_artifact(forged, now=LATER)
    # secret 掃描排除此欄位(對稱 S2.0),故唯一守門者正是 strict-base64 檢查。
    assert q._contains_secret_like(q._result_secret_scan_view(forged)) is False


def test_build_result_refuses_plaintext_secret_pem_body(tmp_path, monkeypatch):
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent()
    authorization, _sig = _sign(private_key, intent, HEAD)
    with pytest.raises(q.SecretLeakageError):
        _quiesced_result(intent, authorization=authorization, signature=_PLAINTEXT_SECRET_PEM.encode("ascii"))


# --------------------------------------------------------------------------- #
# guardrails pinned by the task
# --------------------------------------------------------------------------- #
def test_frozen_classifier_digest_unchanged():
    assert validator.aiml_effect_classifier_digest() == FROZEN_CLASSIFIER


def test_program_schema_paths_untouched_and_schema_files_registered():
    for name in ("quiesce_intent_v1", "quiesce_observation_v1", "quiesce_result_v1", "quiesce_rollback_v1"):
        assert name in validator.SCHEMA_FILES
        schema_path = f"program_code/ml_training/schemas/aiml_gate_receipts/{name}.schema.json"
        assert schema_path not in validator.PROGRAM_SCHEMA_PATHS
    assert len(validator.PROGRAM_SCHEMA_PATHS) == 7


def test_no_secret_serialized_and_credential_exposure_const_false():
    result = q.apply_quiesce_fence(_intent(), None, None, now=NOW, source_head=HEAD)
    blob = json.dumps(result)
    assert "password" not in blob.lower()
    assert q._contains_secret_like(result) is False
    # credential_exposure world_readable / plaintext_ingress 恆 const false(在觀察建構器)。
    obs = _observation("PRE_FENCE_INVENTORY", "CONFIRMED_SINGLE_OWNER", candidate_count=1,
                       host_inventory=_host_inventory(), db_quiesce=_db(held=True, count=1, backend=True, status="OPEN"))
    assert obs["credential_exposure"]["world_readable"] is False
    assert obs["credential_exposure"]["plaintext_ingress"] is False
    forged = copy.deepcopy(obs)
    forged["credential_exposure"]["world_readable"] = True
    forged["self_digest"] = q.artifact_self_digest(forged)
    assert q.validate_quiesce_observation(forged, now=LATER)


def test_central_delegation_requires_now_for_freshness():
    intent = _intent()
    assert any("requires now" in e for e in validator.validate_aiml_artifact(intent))


# --------------------------------------------------------------------------- #
# FIX-W3-1(b/c): static-guard window sampler — cadence, three-valued status, spin-guard
# --------------------------------------------------------------------------- #
class _CoupledClock:
    """注入式單調時鐘 + sleep:``sleep(n)`` 前進 n 秒;``clock()`` 只讀不自動前進(確定性,無真 time.sleep)。"""

    def __init__(self, start=0.0):
        self.now = float(start)
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += float(seconds)


_BASELINE = {"n_restarts": 0, "invocation_id": ""}


def _window_inventory(*, active="inactive", n_restarts=0, invocation="", held=False,
                      count=0, backend=False, status="STOPPED", drained=True):
    # collect_static_guard_window / _classify_static_guard 只讀取 inventory 的這幾個鍵(不必是完整 build_owner_inventory 輸出)。
    return {
        "host_inventory": _host_inventory(main_pid=0, start_ticks=None, invocation=invocation,
                                          n_restarts=n_restarts, active=active, sub="dead"),
        "db_quiesce": _db(held=held, count=count, backend=backend, status=status, drained=drained),
        "credential_exposure": _cred(),
        "candidate_count": 0,
        "owner_fingerprint": OWNER_FP,
    }


def _collect(monkeypatch, provider, *, window=None, clock=None, sleep=None, base=NOW):
    if not callable(provider):
        fixed = provider
        provider = lambda *a, **k: fixed  # noqa: E731 - 每次取樣回同一份 inventory
    # 拆分後 collect_static_guard_window 在 inventory 下層,build_owner_inventory 於該模組命名空間解析 → patch qi。
    monkeypatch.setattr(qi, "build_owner_inventory", provider)
    intent = _intent(observation_window=window or {"duration_seconds": 5, "min_samples": 2, "sample_interval_seconds": 5})
    return q.collect_static_guard_window(
        None, None, intent=intent, baseline=_BASELINE, applier_node="quiesce_apply",
        verifier_node="quiesce_verify", verifier_capture_digest=CAP, clock=clock,
        observed_at_base=base, sleep=sleep,
    )


def test_classify_static_guard_verdicts():
    assert q._classify_static_guard(_window_inventory(), _BASELINE) == "STATIC_GUARDS_HELD"
    assert q._classify_static_guard(_window_inventory(active="active"), _BASELINE) == "RESTART_DETECTED"
    assert q._classify_static_guard(_window_inventory(n_restarts=1), _BASELINE) == "RESTART_DETECTED"
    assert q._classify_static_guard(_window_inventory(invocation="inv-x"), _BASELINE) == "RESTART_DETECTED"
    assert q._classify_static_guard(
        _window_inventory(held=True, count=1, backend=True, status="OPEN"), _BASELINE
    ) == "QUEUE_NOT_DRAINED"
    # FIX-W3-2:UNCLEAN_RECOVERY 終端不算乾淨排空 → QUEUE_NOT_DRAINED(不會被讀成 STOPPED/held)。
    assert q._classify_static_guard(_window_inventory(status="UNCLEAN_RECOVERY"), _BASELINE) == "QUEUE_NOT_DRAINED"


def test_collect_window_held_realizes_cadence(monkeypatch):
    clock = _CoupledClock()
    samples, status = _collect(monkeypatch, _window_inventory(), clock=clock, sleep=clock.sleep)
    assert status == q.WINDOW_STATUS_HELD
    assert len(samples) == 2
    assert all(s["verdict"] == "STATIC_GUARDS_HELD" for s in samples)
    # FIX-W3-1b:兩樣本之間確實消費 sample_interval_seconds;observed_at 反映真實經過時間(跨度 5s == duration)。
    assert clock.sleeps == [5]
    assert q._observation_span_seconds(samples) == 5


def test_collect_window_non_advancing_clock_is_underspecified_not_violated(monkeypatch):
    # 非前進時鐘 + no-op sleep:全 held 但永達不到 duration → 撞 MAX 上限 → UNDERSPECIFIED(非 VIOLATED),絕不 spin。
    monkeypatch.setattr(qi, "MAX_WINDOW_SAMPLES", 4)
    samples, status = _collect(monkeypatch, _window_inventory(), clock=lambda: 0.0, sleep=None)
    assert status == q.WINDOW_STATUS_UNDERSPECIFIED
    assert len(samples) == 4  # 撞上限即止,不會無限取樣
    assert all(s["verdict"] == "STATIC_GUARDS_HELD" for s in samples)


def test_collect_window_too_short_span_is_underspecified(monkeypatch):
    monkeypatch.setattr(qi, "MAX_WINDOW_SAMPLES", 3)
    clock = _CoupledClock()
    # FIX-C4-TTL 使 duration+interval > min(ttl_seconds, 900) 的窗於 intent build 即被拒,故 duration 壓在
    # 界內({800,2,1}:800+1=801<=900)但仍 >> 注入時鐘的真實跨度(~2s)→ 撞 MAX 上限、span << duration → UNDERSPECIFIED。
    samples, status = _collect(
        monkeypatch, _window_inventory(), clock=clock, sleep=clock.sleep,
        window={"duration_seconds": 800, "min_samples": 2, "sample_interval_seconds": 1},
    )
    assert status == q.WINDOW_STATUS_UNDERSPECIFIED  # 跨度 << duration
    assert len(samples) == 3


def test_collect_window_too_few_samples_is_underspecified(monkeypatch):
    monkeypatch.setattr(qi, "MAX_WINDOW_SAMPLES", 3)
    clock = _CoupledClock()
    # FIX-C4 使 (min_samples-1)*interval > duration 的窗於 intent build 即被拒,故改用**合法節奏**({100,5,1}:
    # (5-1)*1=4<=100)但把 MAX 壓到 3 < min_samples(5):撞 MAX 上限前永遠湊不到 min_samples → UNDERSPECIFIED。
    samples, status = _collect(
        monkeypatch, _window_inventory(), clock=clock, sleep=clock.sleep,
        window={"duration_seconds": 100, "min_samples": 5, "sample_interval_seconds": 1},
    )
    assert status == q.WINDOW_STATUS_UNDERSPECIFIED  # min_samples(5) > MAX(3):永遠湊不到 min_samples
    assert len(samples) == 3


def test_collect_window_queue_not_drained_sample_is_violation(monkeypatch):
    clock = _CoupledClock()
    samples, status = _collect(
        monkeypatch, _window_inventory(held=True, count=1, backend=True, status="OPEN"),
        clock=clock, sleep=clock.sleep,
    )
    assert status == q.WINDOW_STATUS_VIOLATED  # 帶一個真 non-held 樣本
    assert len(samples) == 1 and samples[0]["verdict"] == "QUEUE_NOT_DRAINED"


def test_collect_window_restart_midwindow_is_violation(monkeypatch):
    clock = _CoupledClock()
    seq = [_window_inventory(), _window_inventory(active="active")]  # 第二樣本 supervening restart
    samples, status = _collect(
        monkeypatch, lambda *a, **k: seq.pop(0), clock=clock, sleep=clock.sleep,
        window={"duration_seconds": 10, "min_samples": 3, "sample_interval_seconds": 5},
    )
    assert status == q.WINDOW_STATUS_VIOLATED
    assert samples[-1]["verdict"] == "RESTART_DETECTED"


# --------------------------------------------------------------------------- #
# FIX-W3-1(d): validator window-adequacy defense-in-depth on a forged QUIESCED
# --------------------------------------------------------------------------- #
def test_validator_rejects_quiesced_forged_below_claimed_min_samples(tmp_path, monkeypatch):
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent()
    authorization, signature = _sign(private_key, intent, HEAD)
    result = _quiesced_result(intent, authorization=authorization, signature=signature)
    assert q.validate_quiesce_fence_result(result, now=LATER) == []
    # 竄改:把 result 宣稱的 observation_window.min_samples 抬到 3(> 實際 2 個 in-window 樣本)+ 重簽外層。
    forged = copy.deepcopy(result)
    forged["observation_window"]["min_samples"] = 3
    forged["self_digest"] = q.artifact_self_digest(forged)
    assert any("below the window min_samples" in e for e in q.validate_quiesce_fence_result(forged, now=LATER))
    assert validator.validate_aiml_artifact(forged, now=LATER)


def test_validator_rejects_quiesced_forged_span_below_duration(tmp_path, monkeypatch):
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent()
    authorization, signature = _sign(private_key, intent, HEAD)
    result = _quiesced_result(intent, authorization=authorization, signature=signature)
    # 竄改:把兩個 in-window 樣本 observed_at 收攏到同一刻(span 0 < duration 5)+ 逐一重簽 → 跨度再驗擋下。
    forged = copy.deepcopy(result)
    for sample in forged["window_samples"]:
        sample["observed_at"] = NOW
        sample["self_digest"] = q.artifact_self_digest(sample)
    forged["self_digest"] = q.artifact_self_digest(forged)
    assert any("span is below the window duration_seconds" in e
               for e in q.validate_quiesce_fence_result(forged, now=LATER))
    assert validator.validate_aiml_artifact(forged, now=LATER)


# --------------------------------------------------------------------------- #
# FIX-W3-2: UNCLEAN_RECOVERY terminal maps to a distinct non-STOPPED status
# --------------------------------------------------------------------------- #
class _ScriptedCursor:
    def __init__(self, rows):
        self._rows = list(rows)
        self._last = None

    def execute(self, sql, params=None):
        self._last = self._rows.pop(0)

    def fetchone(self):
        return self._last


def test_consumer_session_status_unclean_recovery_is_distinct_non_stopped():
    # 序列:open-count=0(非 OPEN)→ all-count=1(非 ABSENT)→ latest terminal = UNCLEAN_RECOVERY。
    unclean = q._consumer_session_status(
        _ScriptedCursor([(0,), (1,), ("UNCLEAN_RECOVERY",)]), schema="learning", relation="alr_consumer_events"
    )
    assert unclean == "UNCLEAN_RECOVERY" and unclean != "STOPPED"
    # 只有顯式 SESSION_STOPPED 才算乾淨停止。
    assert q._consumer_session_status(
        _ScriptedCursor([(0,), (1,), ("SESSION_STOPPED",)]), schema="learning", relation="alr_consumer_events"
    ) == "STOPPED"
    assert q._consumer_session_status(
        _ScriptedCursor([(0,), (1,), ("SESSION_FAILED",)]), schema="learning", relation="alr_consumer_events"
    ) == "FAILED"


# --------------------------------------------------------------------------- #
# FIX-W3-5: consumer_session_relation must not target a system-catalog schema
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("relation", ["pg_catalog.pg_locks", "pg_toast.pg_toast_1", "information_schema.tables"])
def test_build_intent_rejects_system_catalog_consumer_relation(relation):
    with pytest.raises(q.QuiesceFenceError):
        _intent(observed_relations=[relation], consumer_session_relation=relation)


def test_validate_intent_rejects_system_catalog_consumer_relation():
    intent = _intent()
    forged = copy.deepcopy(intent)
    forged["observed_relations"] = ["pg_catalog.pg_locks"]
    forged["consumer_session_relation"] = "pg_catalog.pg_locks"
    forged["self_digest"] = q.artifact_digest_excluding_self(forged)
    assert any("system-catalog schema" in e for e in q.validate_quiesce_fence_intent(forged, now=NOW))
