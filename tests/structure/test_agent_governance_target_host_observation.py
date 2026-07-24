"""P1 negatives for governed target-host preflight/postcheck captures."""

from __future__ import annotations

import copy
import hashlib
import json
import shlex
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

import aiml_s1_closure_target_host_run as driver  # noqa: E402
from agent_governance_permissions import authorize_command  # noqa: E402


HEAD = "a" * 40
INTENT = {
    "self_digest": "sha256:" + "1" * 64,
    "throwaway_root": "/run/user/1000/aiml_s1fc_test",
}
PERMIT = {"authorization_digest": "sha256:" + "2" * 64}
SIGNATURE = b"operator-signature"
UNIT = "aiml-probeB-absent-123.scope"


def _capture(mode: str, observation: dict) -> dict:
    argv = driver._target_host_observation_argv(
        mode=mode,
        intent=INTENT,
        authorization=PERMIT,
        signature=SIGNATURE,
        unit=UNIT if mode == "postcheck" else None,
        teardown_root=(
            INTENT["throwaway_root"] if mode == "postcheck" else None
        ),
    )
    payload = {
        "schema_version": "target_host_governed_observation_v1",
        "mode": mode,
        "source_head": HEAD,
        "intent_digest": INTENT["self_digest"],
        "operator_authorization_digest": PERMIT["authorization_digest"],
        "observation": observation,
    }
    stdout = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    raw = stdout.encode("utf-8")
    return {
        "argv": argv,
        "result": "PASS",
        "exit_code": 0,
        "stdout": {
            "encoding": "utf-8",
            "preview_text": stdout,
            "truncated": False,
            "bytes": len(raw),
            "digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
        },
    }


def _parse(monkeypatch, capture: dict, *, mode: str) -> dict:
    monkeypatch.setattr(
        driver.capmod,
        "validate_governed_command_capture",
        lambda *_args, **_kwargs: [],
    )
    return driver._captured_target_host_observation(
        capture,
        mode=mode,
        source_head=HEAD,
        intent=INTENT,
        authorization=PERMIT,
        signature=SIGNATURE,
        unit=UNIT if mode == "postcheck" else None,
        teardown_root=(
            INTENT["throwaway_root"] if mode == "postcheck" else None
        ),
    )


def test_postcheck_residue_is_derived_from_exact_captured_stdout(
    monkeypatch,
) -> None:
    observation = {
        "unit_absent": True,
        "cgroup_gone": True,
        "temp_gone": True,
        "no_residue": True,
    }
    assert _parse(
        monkeypatch,
        _capture("postcheck", observation),
        mode="postcheck",
    ) == observation


def test_forged_clean_residue_on_an_unrelated_capture_is_rejected(
    monkeypatch,
) -> None:
    forged = _capture("postcheck", {
        "unit_absent": True,
        "cgroup_gone": True,
        "temp_gone": True,
        "no_residue": True,
    })
    forged["argv"] = ["git", "rev-parse", "--is-inside-work-tree"]
    with pytest.raises(SystemExit, match="exact observer invocation"):
        _parse(monkeypatch, forged, mode="postcheck")


def test_truncated_postcheck_output_is_rejected(monkeypatch) -> None:
    truncated = _capture("postcheck", {"no_residue": True})
    truncated["stdout"]["truncated"] = True
    with pytest.raises(SystemExit, match="complete exact stdout"):
        _parse(monkeypatch, truncated, mode="postcheck")


def test_only_ops_may_run_the_exact_operator_authorized_observer() -> None:
    argv = driver._target_host_observation_argv(
        mode="postcheck",
        intent=INTENT,
        authorization=PERMIT,
        signature=SIGNATURE,
        unit=UNIT,
        teardown_root=INTENT["throwaway_root"],
    )
    command = shlex.join(argv)
    assert authorize_command(
        "OPS",
        command,
        node_class="verification",
        effective_permission="read_only",
    )["allowed"] is True
    assert authorize_command(
        "E2",
        command,
        node_class="verification",
        effective_permission="read_only",
    )["allowed"] is False
    tampered = copy.deepcopy(argv)
    tampered[-1] = "/run/user/1000/../outside"
    assert authorize_command(
        "OPS",
        shlex.join(tampered),
        node_class="verification",
        effective_permission="read_only",
    )["allowed"] is False
