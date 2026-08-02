from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
ML_ROOT = ROOT / "program_code" / "ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2e_lw1_action_packet as action  # noqa: E402
import agent_governance_s2_5_recovery as recovery  # noqa: E402
import aiml_gate_receipt_s2_5_host_capture as host_capture  # noqa: E402
import aiml_gate_receipt_s2e_external_evidence as external  # noqa: E402
import aiml_gate_receipt_s2e_launch as launch  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "S2E LW1 Test")
    _git(repo, "config", "user.email", "s2e-lw1@example.invalid")
    (repo / "checkpoint.txt").write_text("LW1\n", encoding="ascii")
    _git(repo, "add", "checkpoint.txt")
    _git(repo, "commit", "-qm", "LW1 checkpoint")
    return repo


def _inventory(*, ready: bool = False) -> dict:
    path_status = "READY" if ready else "ABSENT"
    service_status = "READY" if ready else "NOT_CONFIGURED"
    return {
        "schema_version": action.INVENTORY_SCHEMA_VERSION,
        "host": "trade-core",
        "observed_at": "2026-08-02T03:54:12Z",
        "evidence_class": "UNAUTHENTICATED_READ_ONLY_OBSERVATION",
        "linux_source_head": "8" * 40,
        "linux_worktree_clean": True,
        "fixed_path_statuses": {
            path: path_status for path in action.EXPECTED_PATHS
        },
        "service_statuses": {
            item_id: service_status for item_id in action.EXPECTED_SERVICE_IDS
        },
        "runtime_units": [
            {
                "unit": "arcane-equilibrium-aiml-engine-scanner.service",
                "load_state": "not-found",
                "active_state": "inactive",
                "sub_state": "dead",
            },
            {
                "unit": "openclaw-learning.service",
                "load_state": "not-found",
                "active_state": "inactive",
                "sub_state": "dead",
            },
        ],
        "canonical_roots": [
            {"path": "/opt/arcane-equilibrium/aiml", "status": "ABSENT"},
            {"path": "/var/lib/arcane-equilibrium/aiml", "status": "ABSENT"},
        ],
    }


def test_code_owned_prerequisite_paths_equal_live_fixed_root_constants() -> None:
    expected = {
        str(launch.S2E_RECEIPT_TRUST_ROOT_PATH),
        str(external.EXTERNAL_WORM_PROVIDER_TRUST_ROOT_PATH),
        str(external.PREDECESSOR_REGISTRY_TRUST_ROOT_PATH),
        str(host_capture.RECOVERY_HOST_CAPTURE_TRUST_ROOT_PUBLIC_KEY_PATH),
        host_capture.HOST_CAPTURE_ATTESTOR_CAPABILITY_PATH,
        str(recovery.RECOVERY_AUTHORIZATION_TRUST_ROOT_PUBLIC_KEY_PATH),
        str(recovery.RECOVERY_ANCHOR_TRUST_ROOT_PUBLIC_KEY_PATH),
        str(recovery.RECOVERY_ANCHOR_READBACK_TRUST_ROOT_PUBLIC_KEY_PATH),
        str(recovery.RECOVERY_CONSUMPTION_TRUST_ROOT_PUBLIC_KEY_PATH),
        str(recovery.RECOVERY_ACTOR_CAPTURE_TRUST_ROOT_PUBLIC_KEY_PATH),
        str(recovery.RECOVERY_VERIFIER_CAPTURE_TRUST_ROOT_PUBLIC_KEY_PATH),
    }
    assert set(action.EXPECTED_PATHS) == expected
    assert len(action.EXPECTED_PATHS) == 11


def test_absent_external_prerequisites_build_closed_blocked_packet(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    packet = action.build_s2e_lw1_operator_action_packet(
        repo_root=repo,
        inventory=_inventory(),
    )
    assert action.validate_s2e_lw1_operator_action_packet(
        packet, repo_root=repo
    ) == []
    assert packet["state"] == action.BLOCKED_STATE
    assert len(packet["prerequisites"]) == 14
    assert len(packet["blocked_prerequisite_ids"]) == 14
    assert packet["closure_projection"] == {
        "g0_state": "SOURCE_COMPLETE_RUNTIME_INDETERMINATE",
        "lw1_state": "BLOCKED_EXTERNAL_PREREQUISITES",
        "w0_genesis_receipt_issued": False,
        "lw1_wave_receipt_issued": False,
        "lw1_transition_gate_advance": False,
        "lw2_unlocked": False,
        "s2e_2b_2_closed": False,
        "s2_closed": False,
        "runtime_state": "UNVERIFIED_NOT_OBSERVED",
    }
    assert packet["packet_digest"] == action.packet_digest(packet)


def test_packet_never_contains_or_grants_secret_or_production_authority(
    tmp_path: Path,
) -> None:
    packet = action.build_s2e_lw1_operator_action_packet(
        repo_root=_repo(tmp_path),
        inventory=_inventory(),
    )
    serialized = json.dumps(packet, sort_keys=True).lower()
    assert "private key" not in serialized
    assert "access_key" not in serialized
    assert "secret_key" not in serialized
    assert packet["authority_boundaries"] == {
        "task_issued_authority_count": 0,
        "total_authority_count": 9,
        "admitted_production_effect_receipt_count": 0,
        "total_production_effect_receipt_count": 6,
        "production_runtime_effect_performed_by_task": False,
        "packet_execution_receipt_absent_within_task_scope": True,
        "production_deploy_restart_pg_broker_order_authorized": False,
    }


def test_all_ready_inventory_cannot_emit_a_blocked_packet(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="do not emit a blocked packet"):
        action.build_s2e_lw1_operator_action_packet(
            repo_root=_repo(tmp_path),
            inventory=_inventory(ready=True),
        )


@pytest.mark.parametrize("mutation", ("missing", "extra", "promoted"))
def test_inventory_set_and_evidence_class_are_closed(
    tmp_path: Path,
    mutation: str,
) -> None:
    inventory = _inventory()
    if mutation == "missing":
        inventory["fixed_path_statuses"].pop(next(iter(action.EXPECTED_PATHS)))
    elif mutation == "extra":
        inventory["fixed_path_statuses"]["/tmp/caller-root"] = "READY"
    else:
        inventory["evidence_class"] = "PLATFORM_OR_EXTERNAL_ATTESTED"
    with pytest.raises(ValueError):
        action.build_s2e_lw1_operator_action_packet(
            repo_root=_repo(tmp_path),
            inventory=inventory,
        )


def test_dirty_source_checkpoint_is_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "checkpoint.txt").write_text("dirty\n", encoding="ascii")
    with pytest.raises(ValueError, match="clean source checkpoint"):
        action.build_s2e_lw1_operator_action_packet(
            repo_root=repo,
            inventory=_inventory(),
        )


@pytest.mark.parametrize(
    "mutate,expected",
    (
        (
            lambda packet: packet["closure_projection"].update(
                lw2_unlocked=True
            ),
            "const False",
        ),
        (
            lambda packet: packet["authority_boundaries"].update(
                task_issued_authority_count=1
            ),
            "const 0",
        ),
        (
            lambda packet: packet["prerequisites"][0].update(
                secret_material_allowed=True
            ),
            "const False",
        ),
    ),
)
def test_schema_rejects_authority_and_secret_boundary_escalation(
    tmp_path: Path,
    mutate,
    expected: str,
) -> None:
    repo = _repo(tmp_path)
    packet = action.build_s2e_lw1_operator_action_packet(
        repo_root=repo,
        inventory=_inventory(),
    )
    mutate(packet)
    errors = action.validate_s2e_lw1_operator_action_packet(
        packet, repo_root=repo
    )
    assert any(expected in error for error in errors), errors


def test_digest_and_source_tree_tampering_fail_closed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    packet = action.build_s2e_lw1_operator_action_packet(
        repo_root=repo,
        inventory=_inventory(),
    )
    forged_digest = deepcopy(packet)
    forged_digest["next_action"] = "CALLER_CHOSEN"
    assert action.validate_s2e_lw1_operator_action_packet(
        forged_digest, repo_root=repo
    )
    forged_tree = deepcopy(packet)
    forged_tree["source_binding"]["implementation_checkpoint_tree"] = "0" * 40
    forged_tree["packet_digest"] = action.packet_digest(forged_tree)
    errors = action.validate_s2e_lw1_operator_action_packet(
        forged_tree, repo_root=repo
    )
    assert any("checkpoint tree differs" in error for error in errors), errors


def test_cli_build_and_validate_use_same_contract(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _repo(tmp_path)
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text(json.dumps(_inventory()), encoding="utf-8")
    assert action.main([
        "build",
        "--repo-root",
        str(repo),
        "--inventory",
        str(inventory_path),
    ]) == 0
    packet = json.loads(capsys.readouterr().out)
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    assert action.main([
        "validate",
        "--repo-root",
        str(repo),
        "--packet",
        str(packet_path),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "PASS",
        "errors": [],
    }
