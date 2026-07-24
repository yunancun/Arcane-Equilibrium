"""Test helper that produces a complete governed OPS command_capture_v2."""

from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path


def governed_ops_capture(root: Path, *, node_id: str = "ops_preflight") -> dict:
    from agent_governance_command_capture_v2 import capture_governed_command
    from agent_governance_context import capture_repository_baseline
    from agent_governance_execution import (
        compile_context,
        materialize_context_artifact,
    )
    from agent_governance_routing import route_task

    scope = [
        "helper_scripts/maintenance_scripts/"
        "agent_governance_target_host_observation.py",
    ]
    facts = {
        "task_shape": "review",
        "surfaces": ["operations"],
        "risk": "medium",
        "uncertainty": "low",
        "side_effect_class": "none",
        "objective": "capture one bounded target-host test reference",
        "scope": scope,
        "dirty_scope": [],
        "verification_scope": scope,
        "acceptance_criteria": ["one exact read-only command receipt"],
        "hard_stops": ["no runtime mutation"],
        "baseline": capture_repository_baseline(root=root),
        "direct_interfaces": ["target_host_governed_observation_v1"],
        "previous_failure": "structural capture is not closure evidence",
    }
    routed = route_task(facts)
    context = materialize_context_artifact(
        compile_context("OPS", routed["task_facts"], root=root)
    )
    return capture_governed_command(
        native_agent="OPS",
        node_id=node_id,
        context_artifact=context,
        argv=["git", "rev-parse", "--is-inside-work-tree"],
        root=root,
    )


def install_test_operator_profile(tmp_path: Path, monkeypatch) -> Path:
    import agent_governance_target_host_operator_authorization as auth

    private_key = tmp_path / "operator"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)],
        check=True,
    )
    parts = private_key.with_suffix(".pub").read_text(
        encoding="ascii"
    ).split()
    public_key = " ".join(parts[:2])
    fingerprint = subprocess.run(
        [
            "ssh-keygen",
            "-lf",
            str(private_key.with_suffix(".pub")),
            "-E",
            "sha256",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()[1]
    monkeypatch.setattr(auth, "OPERATOR_PUBLIC_KEY", public_key)
    monkeypatch.setattr(auth, "OPERATOR_FINGERPRINT", fingerprint)
    return private_key


def typed_intent(
    *,
    applier_node: str,
    postcheck_node: str,
    expected_host: str = "trade-core",
    throwaway_root: str = "/run/user/1000/aiml_s1fc_test",
    now: datetime | None = None,
) -> dict:
    import agent_governance_target_host_operator_authorization as auth

    issued = now or datetime.now(timezone.utc)
    intent = {
        "schema_version": "target_host_disposable_runtime_probe_intent_v1",
        "intent_id": "sha256:" + "4" * 64,
        "expected_host": expected_host,
        "non_root_uid": True,
        "user_scope_only": True,
        "candidate_ids": ["content_addressed_fixed_path"],
        "per_seam_argv": {
            "start_stop": ["python3", "-c", "import time; time.sleep(30)"],
        },
        "throwaway_root": throwaway_root,
        "ttl_seconds": 900,
        "risk": "high",
        "rollback": {
            "atomic_pointer_swap": "swap current->new",
            "teardown_reset_failed": "systemctl --user reset-failed",
            "rmtree": "rm -rf throwaway_root",
        },
        "applier_node_id": applier_node,
        "postcheck_node_id": postcheck_node,
        "created_at": issued.isoformat(),
        "expires_at": (issued + timedelta(minutes=15)).isoformat(),
    }
    intent["self_digest"] = auth.intent_digest(intent)
    return intent


def signed_observation_capture(
    root: Path,
    *,
    private_key: Path,
    intent: dict,
    source_head: str,
    mode: str,
    node_id: str,
    unit: str | None = None,
) -> dict:
    import agent_governance_command_capture_v2 as capmod
    import agent_governance_target_host_operator_authorization as auth
    import aiml_s1_closure_target_host_run as driver
    from agent_governance_command_replay import replay_contract_for
    from agent_governance_permissions import authorize_native_command

    permit = auth.build_operator_authorization(
        intent=intent,
        source_head=source_head,
    )
    message = private_key.parent / f"{mode}-{node_id}-permit.json"
    message.write_bytes(auth.canonical_bytes(permit))
    subprocess.run(
        [
            "ssh-keygen",
            "-Y",
            "sign",
            "-f",
            str(private_key),
            "-n",
            auth.OPERATOR_SIGNATURE_NAMESPACE,
            str(message),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    signature = message.with_suffix(".json.sig").read_bytes()
    teardown_root = (
        str(intent["throwaway_root"]) if mode == "postcheck" else None
    )
    argv = driver._target_host_observation_argv(
        mode=mode,
        intent=intent,
        authorization=permit,
        signature=signature,
        unit=unit,
        teardown_root=teardown_root,
    )
    capture = governed_ops_capture(root, node_id=node_id)
    command = shlex.join(argv)
    authorization = authorize_native_command(capture["native_agent"], command)
    capture.update({
        "argv": argv,
        "command": command,
        "authorization": authorization,
        "replay_contract": replay_contract_for(
            argv, authorization["policy_class"]
        ),
        "exit_code": 0,
        "timed_out": False,
        "result": "PASS",
    })
    issued = datetime.fromisoformat(
        str(intent["created_at"]).replace("Z", "+00:00")
    )
    capture["started_at"] = (issued + timedelta(minutes=1)).isoformat()
    capture["completed_at"] = (issued + timedelta(minutes=2)).isoformat()
    observation = (
        {
            "expected_host": intent["expected_host"],
            "observed_host": intent["expected_host"],
            "non_root_uid": True,
            "sudo_noprompt_present": False,
            "delegated_controllers": ["cpu", "memory", "pids"],
            "deferred_root_only_controllers": ["cpuset", "io"],
            "throwaway_root_under_runtime_dir": True,
        }
        if mode == "preflight"
        else {
            "unit_absent": True,
            "cgroup_gone": True,
            "temp_gone": True,
            "no_residue": True,
        }
    )
    payload = {
        "schema_version": "target_host_governed_observation_v1",
        "mode": mode,
        "source_head": source_head,
        "intent_digest": intent["self_digest"],
        "operator_authorization_digest": permit["authorization_digest"],
        "observation": observation,
    }
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    def output(data: bytes) -> dict:
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        return {
            "encoding": "utf-8",
            "preview_text": data.decode("utf-8"),
            "preview_base64": None,
            "preview_source_bytes": len(data),
            "bytes": len(data),
            "digest": digest,
            "replay_digest": digest,
            "truncated": False,
            "preview_redacted": False,
        }

    capture["stdout"] = output(raw)
    capture["stderr"] = output(b"")
    capture["record_digest"] = capmod._self_digest(capture)
    return capture
