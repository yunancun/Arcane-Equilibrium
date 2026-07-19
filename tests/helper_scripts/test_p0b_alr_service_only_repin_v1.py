from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).parents[2]
    / "helper_scripts/maintenance_scripts/p0b_alr_service_only_repin_v1.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("p0b_service_repin_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_failure_evidence(module, tmp_path, *, target, old, observed="2026-07-19T07:59:58Z", fingerprint=None):
    evidence = {
        "schema_version": module.FAILURE_EVIDENCE_SCHEMA,
        "observed_at_utc": observed,
        "target_host": "trade-core", "target_user_unit": module.UNIT_NAME,
        "old_head": old, "target_head": target,
        "invocation_id": "prior-invocation", "nrestarts": "18697",
        "fingerprint": fingerprint or module.CRASH_FINGERPRINT,
        "journal_slice_sha256": "9" * 64,
        "journal_cursor": "s=cursor;i=123",
    }
    evidence["observation_digest"] = module.canonical_digest(evidence)
    raw = (json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path = tmp_path / "failure-evidence.json"
    path.write_bytes(raw)
    path.chmod(0o600)
    return evidence, path, hashlib.sha256(raw).hexdigest()


def test_capture_facts_binds_exact_source_mismatch_crash_loop_and_projection(tmp_path) -> None:
    module = load_module()
    target = "7" * 40
    old = "2" * 40
    now = datetime(2026, 7, 19, 8, 0, tzinfo=timezone.utc)
    evidence, evidence_path, evidence_sha256 = write_failure_evidence(
        module, tmp_path, target=target, old=old,
    )

    class Runtime:
        def source_snapshot(self):
            return {"head": target, "origin_main": target, "remote_origin_main": target, "clean": True}

        def lane_snapshot(self):
            return {"cost": {"quiet": True}, "alpha": {"quiet": True}}

        def pin_snapshot(self, *, expected_head):
            assert expected_head == old
            return {"identity": {"sha256": "3" * 64, "ino": 31}, "payload": {"head": old}}

        def unit_snapshot(self, *, expected_head):
            assert expected_head == old
            return {"identity": {"sha256": "4" * 64, "ino": 41}, "raw": f"ALR_SOURCE_HEAD={old}\n".encode(), "head": old}

        def service_snapshot(self, *, require_active):
            assert require_active is None
            return {
                "ActiveState": "activating", "SubState": "auto-restart", "MainPID": "0",
                "NRestarts": "18698", "InvocationID": "abc", "ControlGroup": "/user.slice/alr",
                "ALRSourceHead": old,
            }

        def unit_lock_snapshot(self):
            return {"ino": 51}

        def lock_snapshot(self, _path, *, label):
            return {"ino": 61 if label == "cost" else 71}

        def protected_snapshot(self):
            return {
                "units": {"api": {"pid": "1"}},
                "user_unit_inventory": {
                    module.UNIT_NAME: {"fragment": {"sha256": "4" * 64}},
                    "openclaw-trading-api.service": {"fragment": {"sha256": "8" * 64}},
                },
                "engine": [],
            }

        def protected_snapshot_without_alr(self):
            value = self.protected_snapshot()
            del value["user_unit_inventory"][module.UNIT_NAME]
            return value

    facts = module.capture_facts(
        Runtime(), now=now, failure_evidence=evidence,
        failure_evidence_path=evidence_path,
        failure_evidence_sha256=evidence_sha256, old_head=old,
    )
    assert set(facts) == module.FACTS_FIELDS
    assert set(facts["crash_loop"]) == module.CRASH_LOOP_FIELDS
    assert facts["crash_loop"]["fingerprint"] == module.CRASH_FINGERPRINT
    assert facts["mutation_plan"] == list(module.MUTATION_PLAN)
    assert module.UNIT_NAME not in facts["protected_projection"]["user_unit_inventory"]
    assert facts["facts_digest"] == module.canonical_digest({
        key: value for key, value in facts.items() if key != "facts_digest"
    })


def legal_facts(module, tmp_path):
    target = "7" * 40
    old = "2" * 40
    evidence, evidence_path, evidence_sha256 = write_failure_evidence(
        module, tmp_path, target=target, old=old, observed="2026-07-19T07:58:58Z",
    )
    facts = {
        "schema_version": module.FACTS_SCHEMA,
        "captured_at_utc": "2026-07-19T07:59:00Z",
        "expires_at_utc": "2026-07-19T08:04:00Z",
        "target_host": "trade-core", "target_user_unit": module.UNIT_NAME,
        "target_head": target, "old_head": old,
        "source_snapshot": {"head": target, "origin_main": target, "remote_origin_main": target, "clean": True},
        "source_snapshot_digest": "",
        "old_pin": {"identity": {"sha256": "3" * 64}, "payload": {"head": old}},
        "old_unit": {"identity": {"sha256": "4" * 64}, "head": old},
        "proposed_unit_sha256": "5" * 64,
        "crash_loop": {
            "active_state": "activating", "sub_state": "auto-restart", "main_pid": "0",
            "nrestarts": "18698", "invocation_id": "abc", "control_group": "/user.slice/alr",
            "alr_source_head": old, "fingerprint": module.CRASH_FINGERPRINT,
            "fingerprint_observed_at_utc": "2026-07-19T07:58:58Z",
            "fingerprint_sha256": hashlib.sha256(module.CRASH_FINGERPRINT.encode()).hexdigest(),
            "evidence_path": str(evidence_path), "evidence_sha256": evidence_sha256,
            "evidence_digest": evidence["observation_digest"],
        },
        "lock_identities": {"cost": {"ino": 1}, "alpha": {"ino": 2}, "unit": {"ino": 3}},
        "protected_projection": {
            "stable": True,
            "user_unit_inventory": {
                "openclaw-trading-api.service": {"fragment": {"sha256": "8" * 64}},
            },
        },
        "protected_projection_digest": "",
        "receipt_destination": str(module.RECEIPT_DIR),
        "mutation_plan": list(module.MUTATION_PLAN), "failure_policy": module.FAILURE_POLICY,
        "boundaries": module.BOUNDARIES,
    }
    facts["source_snapshot_digest"] = module.canonical_digest(facts["source_snapshot"])
    facts["protected_projection_digest"] = module.canonical_digest(facts["protected_projection"])
    facts["facts_digest"] = module.canonical_digest(facts)
    raw = (json.dumps(facts, sort_keys=True, separators=(",", ":")) + "\n").encode()
    facts_path = tmp_path / "facts.json"
    facts_path.write_bytes(raw)
    facts_path.chmod(0o600)
    return facts, facts_path, hashlib.sha256(raw).hexdigest()


def legal_authorization(module, facts, facts_path, facts_sha256):
    authorization_id = "p0b-service-repin-20260719"
    receipt_path = module.RECEIPT_DIR / f"{authorization_id}.receipt.json"
    protocol_paths = module.receipt_protocol_paths(
        receipt_path, authorization_id=authorization_id,
    )
    protocol_path_digest = module.canonical_digest(
        module.receipt_protocol_path_bundle(
            receipt_path, authorization_id=authorization_id,
        )
    )
    value = {
        "schema_version": module.AUTHORIZATION_SCHEMA,
        "authorization_id": authorization_id,
        "approved_by": "PM/operator",
        "approved_at_utc": "2026-07-19T07:59:00Z",
        "expires_at_utc": "2026-07-19T08:03:00Z",
        "target_host": "trade-core", "target_user_unit": module.UNIT_NAME,
        "facts_path": str(facts_path), "facts_sha256": facts_sha256,
        "facts_digest": facts["facts_digest"], "target_head": facts["target_head"],
        "old_head": facts["old_head"], "source_snapshot_digest": facts["source_snapshot_digest"],
        "old_pin_digest": "sha256:" + facts["old_pin"]["identity"]["sha256"],
        "old_unit_digest": "sha256:" + facts["old_unit"]["identity"]["sha256"],
        "proposed_unit_sha256": facts["proposed_unit_sha256"],
        "crash_loop_digest": module.canonical_digest(facts["crash_loop"]),
        "lock_identities_digest": module.canonical_digest(facts["lock_identities"]),
        "protected_projection_digest": facts["protected_projection_digest"],
        "intent_path": str(module.RECEIPT_DIR / f"{authorization_id}.intent.json"),
        "receipt_path": str(receipt_path),
        "receipt_guard_path": str(protocol_paths["guard"]),
        "receipt_committed_marker_path": str(protocol_paths["committed"]),
        "receipt_quarantine_path": str(protocol_paths["quarantine"]),
        "receipt_protocol_path_digest": protocol_path_digest,
        "mutation_plan": list(module.MUTATION_PLAN), "failure_policy": module.FAILURE_POLICY,
        "typed_confirm": (
            f"p0b-alr-service-only-repin:trade-core:{facts['target_head']}:"
            f"{authorization_id}:{protocol_path_digest}"
        ),
    }
    value["authorization_digest"] = module.canonical_digest(value)
    return value


def test_authorization_is_exact_fresh_fact_bound_and_canonical(tmp_path) -> None:
    module = load_module()
    facts, facts_path, facts_sha256 = legal_facts(module, tmp_path)
    authorization = legal_authorization(module, facts, facts_path, facts_sha256)
    module.validate_authorization(
        authorization, facts=facts, facts_path=facts_path, facts_sha256=facts_sha256,
        now=datetime(2026, 7, 19, 8, 0, tzinfo=timezone.utc),
    )
    assert set(authorization) == module.AUTHORIZATION_FIELDS


@pytest.mark.parametrize(
    ("field", "traversal"),
    [
        ("receipt_guard_path", False),
        ("receipt_committed_marker_path", False),
        ("receipt_quarantine_path", False),
        ("receipt_guard_path", True),
        ("receipt_committed_marker_path", True),
        ("receipt_quarantine_path", True),
    ],
)
def test_fully_rehashed_alternate_receipt_protocol_paths_are_rejected(
    tmp_path, field, traversal,
) -> None:
    module = load_module()
    facts, facts_path, facts_sha256 = legal_facts(module, tmp_path)
    authorization = legal_authorization(module, facts, facts_path, facts_sha256)
    original = Path(authorization[field])
    authorization[field] = (
        f"{original.parent}/../{original.parent.name}/{original.name}"
        if traversal else str(original.with_name(f"alternate-{original.name}"))
    )
    attacker_bundle = {
        "schema_version": "p0b_alr_receipt_protocol_paths_v1",
        "receipt_path": authorization["receipt_path"],
        "guard_path": authorization["receipt_guard_path"],
        "committed_marker_path": authorization["receipt_committed_marker_path"],
        "quarantine_path": authorization["receipt_quarantine_path"],
    }
    attacker_digest = module.canonical_digest(attacker_bundle)
    authorization["receipt_protocol_path_digest"] = attacker_digest
    authorization["typed_confirm"] = (
        f"p0b-alr-service-only-repin:trade-core:{facts['target_head']}:"
        f"{authorization['authorization_id']}:{attacker_digest}"
    )
    authorization["authorization_digest"] = module.canonical_digest({
        key: value for key, value in authorization.items()
        if key != "authorization_digest"
    })
    with pytest.raises(module.ServiceRepinError, match="authorization_semantic_binding_invalid"):
        module.validate_authorization(
            authorization, facts=facts, facts_path=facts_path,
            facts_sha256=facts_sha256,
            now=datetime(2026, 7, 19, 8, 0, tzinfo=timezone.utc),
        )


@pytest.mark.parametrize("mutation", ["missing", "reordered"])
def test_pass_mutation_log_rejects_missing_or_reordered_protocol_action(mutation) -> None:
    module = load_module()
    actions = (
        list(module.MUTATION_PLAN[:7])
        + list(module.RECEIPT_COMMON_ACTIONS)
        + list(module.RECEIPT_SUCCESS_ACTIONS)
    )
    if mutation == "missing":
        actions.remove(module.RECEIPT_COMMON_ACTIONS[0])
    else:
        actions[-3], actions[-2] = actions[-2], actions[-3]
    with pytest.raises(
        module.ServiceRepinError,
        match="pass_mutation_log_not_exact_plan",
    ):
        module.validate_mutation_log(
            [{"action": action} for action in actions],
            status="APPLIED_POSTCHECK_PASS",
        )


@pytest.mark.parametrize("mutation", ["missing", "reordered"])
def test_rehashed_authorization_rejects_missing_or_reordered_protocol_action(
    tmp_path, mutation,
) -> None:
    module = load_module()
    facts, facts_path, facts_sha256 = legal_facts(module, tmp_path)
    authorization = legal_authorization(module, facts, facts_path, facts_sha256)
    if mutation == "missing":
        authorization["mutation_plan"].remove(module.RECEIPT_COMMON_ACTIONS[0])
    else:
        first = authorization["mutation_plan"].index(module.RECEIPT_COMMON_ACTIONS[0])
        second = authorization["mutation_plan"].index(module.RECEIPT_COMMON_ACTIONS[1])
        authorization["mutation_plan"][first], authorization["mutation_plan"][second] = (
            authorization["mutation_plan"][second],
            authorization["mutation_plan"][first],
        )
    authorization["authorization_digest"] = module.canonical_digest({
        key: value for key, value in authorization.items()
        if key != "authorization_digest"
    })
    with pytest.raises(module.ServiceRepinError, match="authorization_semantic_binding_invalid"):
        module.validate_authorization(
            authorization, facts=facts, facts_path=facts_path,
            facts_sha256=facts_sha256,
            now=datetime(2026, 7, 19, 8, 0, tzinfo=timezone.utc),
        )


@pytest.mark.parametrize("mutation", ["source", "receipt_destination", "crash_identity", "alr_in_projection"])
def test_fully_rehashed_facts_still_reject_semantic_authority_widening(tmp_path, mutation) -> None:
    module = load_module()
    facts, facts_path, _ = legal_facts(module, tmp_path)
    if mutation == "source":
        facts["source_snapshot"]["head"] = "f" * 40
        facts["source_snapshot_digest"] = module.canonical_digest(facts["source_snapshot"])
    elif mutation == "receipt_destination":
        facts["receipt_destination"] = "/tmp/widened"
    elif mutation == "crash_identity":
        facts["crash_loop"]["invocation_id"] = ""
    else:
        facts["protected_projection"]["user_unit_inventory"][module.UNIT_NAME] = {
            "forbidden": True
        }
        facts["protected_projection_digest"] = module.canonical_digest(facts["protected_projection"])
    facts["facts_digest"] = module.canonical_digest({
        key: value for key, value in facts.items() if key != "facts_digest"
    })
    raw = (json.dumps(facts, sort_keys=True, separators=(",", ":")) + "\n").encode()
    facts_path.write_bytes(raw)
    facts_sha256 = hashlib.sha256(raw).hexdigest()
    authorization = legal_authorization(module, facts, facts_path, facts_sha256)
    with pytest.raises(module.ServiceRepinError, match="facts_semantic_binding_invalid"):
        module.validate_authorization(
            authorization, facts=facts, facts_path=facts_path,
            facts_sha256=facts_sha256,
            now=datetime(2026, 7, 19, 8, 0, tzinfo=timezone.utc),
        )


class ApplyRuntime:
    def __init__(self, module, facts):
        self.m = module
        self.facts = facts
        self.events = []
        self.running = False
        self.pin_head = facts["old_head"]
        self.unit_head = facts["old_head"]
        self.persisted = {}
        self.fail_pin = False
        self.fail_compensation_stop = False
        self.stop_calls = 0
        self.dynamic_crash = False
        self.crash_reads = 0
        self.lock_held = False
        self.lane_calls = []
        self.job_calls = []
        self.receipt_persist_failure = None
        self.receipt_persist_calls = 0
        self.signals_blocked = False
        self.source = facts["source_snapshot"]
        self.protected = {
            "user_unit_inventory": {
                module.UNIT_NAME: {"fragment": {"sha256": facts["old_unit"]["identity"]["sha256"]}},
                "openclaw-trading-api.service": {"fragment": {"sha256": "8" * 64}},
            },
            "stable": True,
        }

    def source_snapshot(self):
        return self.source

    def lane_snapshot(self):
        self.lane_calls.append(self.lock_held)
        return {"cost": {"quiet": True}, "alpha": {"quiet": True}}

    def no_queued_job(self):
        self.job_calls.append(self.lock_held)
        return {"status": "NO_QUEUED_JOB"}

    def pin_snapshot(self, *, expected_head):
        assert self.pin_head == expected_head
        sha = self.facts["old_pin"]["identity"]["sha256"] if expected_head == self.facts["old_head"] else "9" * 64
        return {"identity": {"sha256": sha}, "payload": {"head": expected_head}}

    def unit_snapshot(self, *, expected_head):
        assert self.unit_head == expected_head
        sha = self.facts["old_unit"]["identity"]["sha256"] if expected_head == self.facts["old_head"] else self.facts["proposed_unit_sha256"]
        return {"identity": {"sha256": sha}, "head": expected_head, "raw": f"ALR_SOURCE_HEAD={expected_head}\n".encode()}

    def service_snapshot(self, *, require_active):
        if require_active is False:
            assert not self.running
            return {"ActiveState": "inactive", "SubState": "dead", "MainPID": "0", "ControlGroup": "/user.slice/alr", "ALRSourceHead": self.unit_head}
        if require_active is True:
            assert self.running
            return {"ActiveState": "active", "SubState": "running", "MainPID": "42", "ProcessStartTicks": "88", "NRestarts": "0", "InvocationID": "new", "ControlGroup": "/user.slice/alr", "ALRSourceHead": self.unit_head}
        self.crash_reads += 1
        return {
            "ActiveState": "activating", "SubState": "auto-restart", "MainPID": "0",
            "NRestarts": str(18700 + (self.crash_reads if self.dynamic_crash else 0)),
            "InvocationID": f"current-{self.crash_reads}" if self.dynamic_crash else "current",
            "ControlGroup": "/user.slice/alr",
            "ALRSourceHead": self.facts["old_head"],
        }

    def protected_snapshot(self):
        return self.protected

    def protected_snapshot_without_alr(self):
        value = json.loads(json.dumps(self.protected))
        value["user_unit_inventory"].pop(self.m.UNIT_NAME, None)
        return value

    @contextmanager
    def transaction_lock(self):
        self.events.append("lock:cost-alpha-unit")
        self.lock_held = True
        try:
            yield self.facts["lock_identities"]
        finally:
            self.lock_held = False

    def persist_path(self, path, payload):
        kind = payload.get("kind", "receipt")
        self.events.append(f"persist:{kind}")
        self.persisted[str(path)] = payload
        if kind == "receipt" and self.receipt_persist_failure is not None:
            self.receipt_persist_calls += 1
            if self.receipt_persist_failure == "collision":
                raise FileExistsError("partial_receipt_collision")
            raise OSError("parent_fsync_failed")
        if kind == "receipt":
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = (
                json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(fd, raw)
                os.fsync(fd)
            finally:
                os.close(fd)
        return {"path": str(path), "sha256": hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), "size": 1}

    def block_effect_signals(self):
        self.events.append("signals:block")
        self.signals_blocked = True
        return {"blocked": ["SIGHUP", "SIGINT", "SIGTERM"]}

    def stop_alr(self):
        assert self.signals_blocked is True
        self.events.append("stop")
        self.stop_calls += 1
        if self.fail_compensation_stop and self.stop_calls > 1:
            raise self.m.ServiceRepinError("compensation_stop_failed")
        self.running = False
        return {"action": "stop", "unit": self.m.UNIT_NAME}

    def prove_old_absent_twice(self, prior):
        self.events.append("prove-stopped")
        return [{"ordinal": 1}, {"ordinal": 2}]

    def advance_pin(self):
        self.events.append("pin")
        self.pin_head = self.facts["target_head"]
        if self.fail_pin:
            raise self.m.ServiceRepinError("ambiguous_pin_postcheck")
        return {"status": "APPLIED_POSTCHECK_PASS"}

    def atomic_unit_to_target(self):
        self.events.append("unit")
        self.unit_head = self.facts["target_head"]
        return b"old", {"identity": {"sha256": self.facts["proposed_unit_sha256"]}}

    def daemon_reload(self):
        self.events.append("reload")
        return {"action": "daemon-reload"}

    def reset_failed(self):
        self.events.append("reset")
        return {"action": "reset-failed", "unit": self.m.UNIT_NAME}

    def restart_alr(self):
        self.events.append("restart")
        self.running = True
        return {"action": "restart", "unit": self.m.UNIT_NAME}

    def wait_stable_target(self, *, prior):
        return self.service_snapshot(require_active=True)


def test_apply_persists_intent_before_exact_alr_only_mutations_and_success_receipt(tmp_path) -> None:
    module = load_module()
    module.RECEIPT_DIR = tmp_path / "transaction-receipts"
    module.RECEIPT_DIR.mkdir(parents=True)
    facts, facts_path, facts_sha256 = legal_facts(module, tmp_path)
    facts["proposed_unit_sha256"] = hashlib.sha256(
        f"ALR_SOURCE_HEAD={facts['target_head']}\n".encode()
    ).hexdigest()
    runtime = ApplyRuntime(module, facts)
    facts["protected_projection"] = module.protected_projection(runtime)
    facts["protected_projection_digest"] = module.canonical_digest(facts["protected_projection"])
    facts["facts_digest"] = module.canonical_digest({key: value for key, value in facts.items() if key != "facts_digest"})
    facts_path.write_bytes((json.dumps(facts, sort_keys=True, separators=(",", ":")) + "\n").encode())
    facts_sha256 = hashlib.sha256(facts_path.read_bytes()).hexdigest()
    authorization = legal_authorization(module, facts, facts_path, facts_sha256)
    transaction = module.ServiceOnlyRepinTransaction(
        runtime, authorization, facts, facts_path=facts_path, facts_sha256=facts_sha256,
        now=lambda: datetime(2026, 7, 19, 8, 0, tzinfo=timezone.utc),
    )
    result = transaction.apply()
    assert result["status"] == "APPLIED_POSTCHECK_PASS"
    assert set(result) == module.RECEIPT_FIELDS
    assert result["receipt_digest"] == module.canonical_digest({
        key: value for key, value in result.items() if key != "receipt_digest"
    })
    assert runtime.events == [
        "lock:cost-alpha-unit", "signals:block", "persist:intent", "stop",
        "prove-stopped", "pin",
        "unit", "reload", "reset", "restart", "persist:receipt",
    ]
    assert [entry["action"] for entry in result["mutations"]] == (
        list(module.MUTATION_PLAN[:7])
        + list(module.RECEIPT_COMMON_ACTIONS)
        + list(module.RECEIPT_SUCCESS_ACTIONS)
    )


def transaction_fixture(module, tmp_path, *, runtime_class=ApplyRuntime):
    default_receipt_dir = module.BASE.RECEIPT_DIR / "service-only-repin"
    if module.RECEIPT_DIR == default_receipt_dir:
        module.RECEIPT_DIR = tmp_path / "transaction-receipts"
    module.RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    facts, facts_path, _ = legal_facts(module, tmp_path)
    facts["proposed_unit_sha256"] = hashlib.sha256(
        f"ALR_SOURCE_HEAD={facts['target_head']}\n".encode()
    ).hexdigest()
    runtime = runtime_class(module, facts)
    facts["protected_projection"] = module.protected_projection(runtime)
    facts["protected_projection_digest"] = module.canonical_digest(facts["protected_projection"])
    facts["facts_digest"] = module.canonical_digest({key: value for key, value in facts.items() if key != "facts_digest"})
    facts_path.write_bytes((json.dumps(facts, sort_keys=True, separators=(",", ":")) + "\n").encode())
    facts_sha256 = hashlib.sha256(facts_path.read_bytes()).hexdigest()
    authorization = legal_authorization(module, facts, facts_path, facts_sha256)
    transaction = module.ServiceOnlyRepinTransaction(
        runtime, authorization, facts, facts_path=facts_path, facts_sha256=facts_sha256,
        now=lambda: datetime(2026, 7, 19, 8, 0, tzinfo=timezone.utc),
    )
    return runtime, transaction


def test_post_stop_failure_compensation_freezes_stopped_without_backpin_or_restart(tmp_path) -> None:
    module = load_module()
    runtime, transaction = transaction_fixture(module, tmp_path)
    runtime.fail_pin = True
    result = transaction.apply()
    assert result["status"] == "POST_STOP_FAILURE_STOPPED_VERIFIED"
    assert result["target_service"] is None
    assert result["final_postcheck"] is None
    assert result["stopped_proofs"] == [{"ordinal": 1}, {"ordinal": 2}]
    assert runtime.running is False
    assert runtime.events.count("stop") == 2
    assert "restart" not in runtime.events
    assert "backpin" not in runtime.events
    assert runtime.events[-2:] == ["prove-stopped", "persist:receipt"]


def test_locked_admission_accepts_new_invocation_and_monotonic_restart_count(tmp_path) -> None:
    module = load_module()
    runtime, transaction = transaction_fixture(module, tmp_path)
    runtime.dynamic_crash = True
    result = transaction.apply()
    assert result["status"] == "APPLIED_POSTCHECK_PASS"
    assert runtime.crash_reads == 2


def test_final_postcheck_rechecks_lanes_jobs_and_lock_identity_while_locked(tmp_path) -> None:
    module = load_module()
    runtime, transaction = transaction_fixture(module, tmp_path)
    result = transaction.apply()
    assert runtime.lane_calls == [False, True, True]
    assert runtime.job_calls == [False, True, True]
    assert result["final_postcheck"]["lane"] == {
        "cost": {"quiet": True}, "alpha": {"quiet": True}
    }
    assert result["final_postcheck"]["user_manager_jobs"] == {
        "status": "NO_QUEUED_JOB"
    }
    assert result["final_postcheck"]["lock_identities"] == transaction.facts["lock_identities"]


def test_effect_signals_are_blocked_before_stop_and_remain_blocked_through_receipt(tmp_path) -> None:
    module = load_module()
    runtime, transaction = transaction_fixture(module, tmp_path)
    result = transaction.apply()
    assert result["status"] == "APPLIED_POSTCHECK_PASS"
    assert runtime.events.index("signals:block") < runtime.events.index("stop")
    assert runtime.events.index("signals:block") < runtime.events.index("persist:receipt")
    assert runtime.signals_blocked is True


def test_protected_projection_never_queries_alr_reload_state_after_unit_write(
    monkeypatch, tmp_path
) -> None:
    module = load_module()
    api_fragment = tmp_path / "openclaw-trading-api.service"
    api_fragment.write_text("[Service]\nExecStart=/bin/true\n")
    metadata_calls = []

    def fake_metadata(path, *, include_hash):
        metadata_calls.append((Path(path), include_hash))
        return {"path": str(path), "include_hash": include_hash}

    monkeypatch.setattr(module.BASE, "metadata", fake_metadata)

    class Runtime:
        pin = type("Pin", (), {"auth_metadata": staticmethod(lambda: [{"auth": "same"}])})()

        def protected_snapshot(self):
            raise AssertionError("legacy projection queried ALR NeedDaemonReload=yes")

        def run(self, command, **_kwargs):
            if command == ["/usr/bin/crontab", "-l"]:
                return type("Result", (), {"stdout": "cost cron\nalpha cron\n"})()
            if "list-unit-files" in command:
                return type("Result", (), {"stdout": (
                    f"{module.UNIT_NAME} enabled\nopenclaw-trading-api.service enabled\n"
                )})()
            unit = command[3]
            assert unit != module.UNIT_NAME
            return type("Result", (), {"stdout": (
                "LoadState=loaded\nNeedDaemonReload=no\n"
                f"FragmentPath={api_fragment}\nDropInPaths=\n"
            )})()

        def crontab_consumers_from_text(self, raw):
            assert raw == "cost cron\nalpha cron\n"
            return {"cost": 1, "alpha": 1}

        def protected_unit_snapshot(self, name):
            return {"name": name, "stable": True}

        def protected_engine_processes(self):
            return []

        def no_queued_job(self):
            return {"status": "NO_QUEUED_JOB"}

    projection = module.protected_projection(Runtime())
    assert module.UNIT_NAME not in projection["user_unit_inventory"]
    assert set(projection["user_unit_inventory"]) == {"openclaw-trading-api.service"}
    assert projection["user_manager_jobs"] == {"status": "NO_QUEUED_JOB"}
    assert all(path != module.UNIT_PATH for path, _include_hash in metadata_calls)


def test_pre_stop_drift_creates_neither_intent_nor_receipt(tmp_path) -> None:
    module = load_module()
    runtime, transaction = transaction_fixture(module, tmp_path)
    runtime.source = {**runtime.source, "remote_origin_main": "f" * 40}
    try:
        transaction.apply()
    except module.ServiceRepinError as exc:
        assert str(exc) == "source_snapshot_drift"
    else:
        raise AssertionError("pre-stop source drift was accepted")
    assert runtime.persisted == {}
    assert runtime.events == []


@pytest.mark.parametrize(
    "path_property",
    [
        "receipt_guard_path",
        "receipt_committed_marker_path",
        "receipt_quarantine_path",
    ],
)
def test_receipt_protocol_path_collision_blocks_before_intent_or_effect(
    tmp_path, path_property,
) -> None:
    module = load_module()
    runtime, transaction = transaction_fixture(module, tmp_path)
    collision = getattr(transaction, path_property)
    collision.symlink_to(tmp_path / "dangling-target")
    with pytest.raises(module.ServiceRepinError, match="authorization_already_consumed"):
        transaction.apply()
    assert runtime.events == []
    assert runtime.persisted == {}


@pytest.mark.parametrize("mutation", ["tamper", "missing"])
def test_apply_reopens_external_failure_evidence_and_blocks_tamper_before_intent(tmp_path, mutation) -> None:
    module = load_module()
    runtime, transaction = transaction_fixture(module, tmp_path)
    evidence_path = Path(transaction.facts["crash_loop"]["evidence_path"])
    if mutation == "tamper":
        evidence_path.write_bytes(evidence_path.read_bytes() + b" ")
    else:
        evidence_path.unlink()
    with pytest.raises((module.ServiceRepinError, FileNotFoundError)):
        transaction.apply()
    assert runtime.persisted == {}
    assert runtime.events == []


@pytest.mark.parametrize("mutation", ["stale", "wrong_fingerprint"])
def test_failure_evidence_rejects_stale_or_wrong_fingerprint(tmp_path, mutation) -> None:
    module = load_module()
    evidence, _path, _sha = write_failure_evidence(
        module, tmp_path, target="7" * 40, old="2" * 40,
        observed="2026-07-19T07:50:00Z" if mutation == "stale" else "2026-07-19T07:59:58Z",
        fingerprint="different" if mutation == "wrong_fingerprint" else None,
    )
    with pytest.raises(module.ServiceRepinError, match="failure_evidence_semantic_invalid"):
        module.validate_failure_evidence(
            evidence, now=datetime(2026, 7, 19, 8, 0, tzinfo=timezone.utc),
            target_head="7" * 40, old_head="2" * 40,
        )


def test_unverified_compensation_never_claims_stopped(tmp_path) -> None:
    module = load_module()
    runtime, transaction = transaction_fixture(module, tmp_path)
    runtime.fail_pin = True
    runtime.fail_compensation_stop = True
    result = transaction.apply()
    assert result["status"] == "POST_STOP_STATE_UNVERIFIED"
    assert result["stopped_proofs"] is None
    assert "STOPPED_VERIFIED" not in result["status"]


@pytest.mark.parametrize("failure", ["collision", "parent_fsync"])
def test_post_stop_receipt_persist_failure_returns_unverified_without_escape(tmp_path, failure) -> None:
    module = load_module()
    runtime, transaction = transaction_fixture(module, tmp_path)
    runtime.receipt_persist_failure = failure
    result = transaction.apply()
    assert result["status"] == "POST_STOP_STATE_UNVERIFIED"
    assert result["stopped_proofs"] is None
    assert result["error_type"] == "ServiceRepinError"
    assert runtime.running is False
    assert runtime.receipt_persist_calls >= 1


def test_parent_fsync_failure_cannot_leave_authoritative_pass_receipt(
    monkeypatch, tmp_path
) -> None:
    module = load_module()
    receipt_dir = tmp_path / "receipts"
    monkeypatch.setattr(module, "RECEIPT_DIR", receipt_dir)

    class ParentFsyncFailureRuntime(ApplyRuntime):
        def persist_path(self, path, payload):
            kind = payload.get("kind", "receipt")
            if kind == "intent":
                return super().persist_path(path, payload)
            self.events.append("persist:receipt")
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = (
                json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(fd, raw)
                os.fsync(fd)
            finally:
                os.close(fd)
            if payload["status"] == "APPLIED_POSTCHECK_PASS":
                raise OSError("simulated_parent_directory_fsync_failure")
            return {
                "path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                "size": len(raw),
            }

    runtime, transaction = transaction_fixture(
        module, tmp_path, runtime_class=ParentFsyncFailureRuntime,
    )
    result = transaction.apply()
    assert result["status"] != "APPLIED_POSTCHECK_PASS"
    if transaction.receipt_path.exists():
        persisted = json.loads(transaction.receipt_path.read_text())
        assert persisted["status"] != "APPLIED_POSTCHECK_PASS"


@pytest.mark.parametrize("failed_directory_fsync_ordinal", [1, 2])
def test_receipt_protocol_parent_fsync_failure_never_returns_pass(
    monkeypatch, tmp_path, failed_directory_fsync_ordinal,
) -> None:
    module = load_module()
    runtime, transaction = transaction_fixture(module, tmp_path)
    real_fsync = module.os.fsync
    directory_calls = 0

    def fail_selected_directory_fsync(fd):
        nonlocal directory_calls
        if module.stat.S_ISDIR(os.fstat(fd).st_mode):
            directory_calls += 1
            if directory_calls == failed_directory_fsync_ordinal:
                raise OSError("simulated_receipt_protocol_parent_fsync_failure")
        return real_fsync(fd)

    monkeypatch.setattr(module.os, "fsync", fail_selected_directory_fsync)
    result = transaction.apply()
    assert result["status"] != "APPLIED_POSTCHECK_PASS"
    assert transaction.receipt_guard_path.exists()
    assert transaction.receipt_committed_marker_path.exists() is (
        failed_directory_fsync_ordinal == 2
    )
    persisted = json.loads(transaction.receipt_path.read_text())
    assert persisted["status"] != "APPLIED_POSTCHECK_PASS"
    if failed_directory_fsync_ordinal == 2:
        quarantined = json.loads(transaction.receipt_quarantine_path.read_text())
        assert quarantined["status"] == "APPLIED_POSTCHECK_PASS"


def test_validator_rejects_committed_marker_visible_before_parent_fsync(
    monkeypatch, tmp_path,
) -> None:
    module = load_module()
    runtime, transaction = transaction_fixture(module, tmp_path)
    real_fsync = module.os.fsync
    directory_calls = 0
    rejected_while_committed_visible = False

    def observe_committed_before_parent_fsync(fd):
        nonlocal directory_calls, rejected_while_committed_visible
        if module.stat.S_ISDIR(os.fstat(fd).st_mode):
            directory_calls += 1
            if directory_calls == 2:
                receipt_sha = hashlib.sha256(
                    transaction.receipt_path.read_bytes()
                ).hexdigest()
                try:
                    module.validate_authoritative_receipt(
                        transaction.receipt_path, expected_sha256=receipt_sha,
                    )
                except module.PersistentAmbiguousReceiptError:
                    rejected_while_committed_visible = True
        return real_fsync(fd)

    monkeypatch.setattr(module.os, "fsync", observe_committed_before_parent_fsync)
    result = transaction.apply()
    assert result["status"] == "APPLIED_POSTCHECK_PASS"
    assert rejected_while_committed_visible is True


def test_committed_parent_fsync_and_quarantine_failure_compensates_under_guard(
    monkeypatch, tmp_path,
) -> None:
    module = load_module()
    runtime, transaction = transaction_fixture(module, tmp_path)
    real_fsync = module.os.fsync
    real_rename = module.os.rename
    directory_calls = 0

    def fail_committed_parent_fsync(fd):
        nonlocal directory_calls
        if module.stat.S_ISDIR(os.fstat(fd).st_mode):
            directory_calls += 1
            if directory_calls == 2:
                raise OSError("simulated_committed_parent_fsync_failure")
        return real_fsync(fd)

    def fail_pass_quarantine(source, destination):
        if (
            Path(source) == transaction.receipt_path
            and Path(destination) == transaction.receipt_quarantine_path
        ):
            raise OSError("simulated_pass_quarantine_failure")
        return real_rename(source, destination)

    monkeypatch.setattr(module.os, "fsync", fail_committed_parent_fsync)
    monkeypatch.setattr(module.os, "rename", fail_pass_quarantine)
    result = transaction.apply()
    invalidation = next(
        entry["result"] for entry in result["mutations"]
        if entry["action"] == module.RECEIPT_FAILURE_ACTIONS[0]
    )
    assert result["status"] == "POST_STOP_STATE_UNVERIFIED"
    assert invalidation["closure_inadmissible"] is True
    assert transaction.receipt_guard_path.exists()
    assert transaction.receipt_committed_marker_path.exists()
    with pytest.raises(module.PersistentAmbiguousReceiptError):
        module.validate_authoritative_receipt(
            transaction.receipt_path,
            expected_sha256=hashlib.sha256(
                transaction.receipt_path.read_bytes()
            ).hexdigest(),
        )
    assert runtime.running is False
    assert runtime.stop_calls == 2


def test_guard_unlink_parent_fsync_failure_is_irreversible_pass(
    monkeypatch, tmp_path,
) -> None:
    module = load_module()
    runtime, transaction = transaction_fixture(module, tmp_path)
    real_fsync = module.os.fsync
    directory_calls = 0
    accepted_after_unlink = False

    def fail_unlink_parent_fsync(fd):
        nonlocal directory_calls, accepted_after_unlink
        if module.stat.S_ISDIR(os.fstat(fd).st_mode):
            directory_calls += 1
            if directory_calls == 3:
                receipt_sha = hashlib.sha256(
                    transaction.receipt_path.read_bytes()
                ).hexdigest()
                accepted_after_unlink = (
                    module.validate_authoritative_receipt(
                        transaction.receipt_path, expected_sha256=receipt_sha,
                    )["status"] == "APPLIED_POSTCHECK_PASS"
                )
                raise OSError("simulated_guard_unlink_parent_fsync_failure")
        return real_fsync(fd)

    monkeypatch.setattr(module.os, "fsync", fail_unlink_parent_fsync)
    result = transaction.apply()
    assert result["status"] == "APPLIED_POSTCHECK_PASS"
    assert accepted_after_unlink is True
    assert directory_calls == 3
    assert runtime.running is True
    assert runtime.stop_calls == 1
    assert not transaction.receipt_guard_path.exists()
    assert transaction.receipt_committed_marker_path.exists()


def test_accepted_visible_commit_is_never_rolled_back_or_compensated(
    monkeypatch, tmp_path,
) -> None:
    module = load_module()
    runtime, transaction = transaction_fixture(module, tmp_path)
    real_rename = module.os.rename
    rollback_calls = 0
    accepted_visible = False

    def committed_visible_then_raise(
        guard_path, *, committed_path, quarantine_path, marker,
    ):
        nonlocal accepted_visible
        assert not quarantine_path.exists()
        module._xcreate_durable_json(committed_path, marker)
        os.unlink(guard_path)
        receipt_sha = hashlib.sha256(transaction.receipt_path.read_bytes()).hexdigest()
        accepted_visible = (
            module.validate_authoritative_receipt(
                transaction.receipt_path, expected_sha256=receipt_sha,
            )["status"] == "APPLIED_POSTCHECK_PASS"
        )
        raise OSError("simulated_exception_after_acceptance_visible")

    def observe_rollback(source, destination):
        nonlocal rollback_calls
        if (
            Path(source) == transaction.receipt_committed_marker_path
            and Path(destination) == transaction.receipt_guard_path
        ):
            rollback_calls += 1
        return real_rename(source, destination)

    monkeypatch.setattr(
        module, "transition_receipt_guard_to_committed",
        committed_visible_then_raise,
    )
    monkeypatch.setattr(module.os, "rename", observe_rollback)
    result = transaction.apply()
    assert result["status"] == "APPLIED_POSTCHECK_PASS"
    assert accepted_visible is True
    assert rollback_calls == 0
    assert runtime.running is True
    assert runtime.stop_calls == 1
    assert not transaction.receipt_guard_path.exists()


@pytest.mark.parametrize(
    "ambiguity", ["guard", "quarantine", "missing_commit", "tampered_commit"],
)
def test_downstream_validator_rejects_ambiguous_pass_receipt(tmp_path, ambiguity) -> None:
    module = load_module()
    authorization_id = "p0b-validator-ambiguity"
    path = tmp_path / f"{authorization_id}.receipt.json"
    payload = {
        "schema_version": module.RECEIPT_SCHEMA,
        "status": "APPLIED_POSTCHECK_PASS",
        "authorization_id": authorization_id,
    }
    payload["receipt_digest"] = module.canonical_digest(payload)
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    protocol_paths = module.receipt_protocol_paths(
        path, authorization_id=authorization_id,
    )
    if ambiguity == "guard":
        protocol_paths["guard"].write_text("guard\n")
    elif ambiguity == "quarantine":
        protocol_paths["quarantine"].write_text("old pass\n")
    elif ambiguity == "tampered_commit":
        protocol_paths["committed"].write_text("tampered\n")
    with pytest.raises(
        module.PersistentAmbiguousReceiptError,
        match="authoritative_pass_receipt_",
    ):
        module.validate_authoritative_receipt(
            path, expected_sha256=hashlib.sha256(raw).hexdigest(),
        )


def test_validator_rejects_pass_during_persist_window_then_accepts_only_after_commit(
    monkeypatch, tmp_path
) -> None:
    module = load_module()
    receipt_dir = tmp_path / "protocol-receipts"
    monkeypatch.setattr(module, "RECEIPT_DIR", receipt_dir)

    class ConcurrentValidatorRuntime(ApplyRuntime):
        concurrent_rejected = False

        def persist_path(self, path, payload):
            if payload.get("kind") == "intent":
                return super().persist_path(path, payload)
            self.events.append("persist:receipt")
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = (
                json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(fd, raw)
                os.fsync(fd)
            finally:
                os.close(fd)
            if payload["status"] == "APPLIED_POSTCHECK_PASS":
                try:
                    module.validate_authoritative_receipt(
                        path, expected_sha256=hashlib.sha256(raw).hexdigest(),
                    )
                except module.PersistentAmbiguousReceiptError:
                    self.concurrent_rejected = True
            return {
                "path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                "size": len(raw),
            }

    runtime, transaction = transaction_fixture(
        module, tmp_path, runtime_class=ConcurrentValidatorRuntime,
    )
    result = transaction.apply()
    assert result["status"] == "APPLIED_POSTCHECK_PASS"
    assert runtime.concurrent_rejected is True
    persisted_sha = hashlib.sha256(transaction.receipt_path.read_bytes()).hexdigest()
    accepted = module.validate_authoritative_receipt(
        transaction.receipt_path, expected_sha256=persisted_sha,
    )
    assert accepted["status"] == "APPLIED_POSTCHECK_PASS"


def test_capture_facts_cli_xcreates_exact_canonical_artifact(monkeypatch, tmp_path, capsys) -> None:
    module = load_module()
    output = tmp_path / "captured-facts.json"
    payload = {"schema_version": module.FACTS_SCHEMA, "facts_digest": "sha256:" + "a" * 64}

    class CaptureRuntime:
        def __init__(self, *, discover):
            assert discover is True

        def persist_path(self, path, value):
            assert path == output
            raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
            path.write_bytes(raw)
            return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}

    monkeypatch.setattr(module, "Runtime", CaptureRuntime)
    monkeypatch.setattr(module.BASE, "OLD_HEAD", "2" * 40)
    monkeypatch.setattr(module, "capture_facts", lambda runtime, **kwargs: payload)
    _evidence, evidence_path, evidence_sha256 = write_failure_evidence(
        module, tmp_path, target="7" * 40, old="2" * 40,
    )
    assert module.main([
        "--capture-facts", "--facts-out", str(output),
        "--failure-evidence-json", str(evidence_path),
        "--failure-evidence-sha256", evidence_sha256,
    ]) == 0
    assert json.loads(capsys.readouterr().out) == payload
    assert output.read_bytes() == (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def test_apply_cli_loads_exact_authorization_and_bound_facts_hash(monkeypatch, tmp_path, capsys) -> None:
    module = load_module()
    facts, facts_path, facts_sha256 = legal_facts(module, tmp_path)
    authorization = legal_authorization(module, facts, facts_path, facts_sha256)
    authorization_path = tmp_path / "authorization.json"
    authorization_raw = (
        json.dumps(authorization, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    authorization_path.write_bytes(authorization_raw)
    authorization_path.chmod(0o600)
    authorization_sha256 = hashlib.sha256(authorization_raw).hexdigest()
    configured = {}

    def configure(**kwargs):
        configured.update(kwargs)

    class Runtime:
        def __init__(self):
            pass

    class Transaction:
        def __init__(self, runtime, observed_authorization, observed_facts, **kwargs):
            assert isinstance(runtime, Runtime)
            assert observed_authorization == authorization
            assert observed_facts == facts
            assert kwargs["facts_sha256"] == facts_sha256

        def apply(self):
            return {"status": "APPLIED_POSTCHECK_PASS"}

    monkeypatch.setattr(module.BASE, "configure_runtime_generation", configure)
    monkeypatch.setattr(module, "Runtime", Runtime)
    monkeypatch.setattr(module, "ServiceOnlyRepinTransaction", Transaction)
    assert module.main([
        "--apply", "--authorization-json", str(authorization_path),
        "--authorization-sha256", authorization_sha256,
    ]) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "APPLIED_POSTCHECK_PASS"}
    assert configured == {
        "target_head": facts["target_head"], "old_head": facts["old_head"],
        "old_pin_sha256": facts["old_pin"]["identity"]["sha256"],
        "old_unit_sha256": facts["old_unit"]["identity"]["sha256"],
    }
    with pytest.raises(module.ServiceRepinError, match="hash_mismatch"):
        module.read_bound_json(
            authorization_path, expected_sha256="f" * 64, label="authorization",
        )


@pytest.mark.parametrize("surface", ["authorization", "facts"])
def test_apply_cli_requires_private_authorization_and_facts(monkeypatch, tmp_path, surface) -> None:
    module = load_module()
    facts, facts_path, facts_sha256 = legal_facts(module, tmp_path)
    authorization = legal_authorization(module, facts, facts_path, facts_sha256)
    authorization_path = tmp_path / "authorization-private-check.json"
    raw = (json.dumps(authorization, sort_keys=True, separators=(",", ":")) + "\n").encode()
    authorization_path.write_bytes(raw)
    authorization_path.chmod(0o600)
    if surface == "authorization":
        authorization_path.chmod(0o644)
    else:
        facts_path.chmod(0o644)
    monkeypatch.setattr(
        module.BASE, "configure_runtime_generation",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("private check bypassed")),
    )
    with pytest.raises(module.ServiceRepinError, match="bound_file_identity_or_hash_mismatch"):
        module.main([
            "--apply", "--authorization-json", str(authorization_path),
            "--authorization-sha256", hashlib.sha256(raw).hexdigest(),
        ])


def test_read_bound_json_rejects_path_replacement_after_open(tmp_path) -> None:
    module = load_module()
    path = tmp_path / "bound.json"
    replacement = tmp_path / "replacement.json"
    raw = b'{"same":true}\n'
    path.write_bytes(raw)
    replacement.write_bytes(raw)
    path.chmod(0o600)
    replacement.chmod(0o600)

    def replace_after_open():
        replacement.replace(path)

    with pytest.raises(module.ServiceRepinError, match="identity_or_hash_mismatch"):
        module.read_bound_json(
            path, expected_sha256=hashlib.sha256(raw).hexdigest(), label="race",
            require_private=True, after_open=replace_after_open,
        )
