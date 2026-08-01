"""Focused OPS routing tests for observation-only and effect lanes."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_routing import route_task  # noqa: E402


def _ops_nodes(route: dict) -> list[dict]:
    return [node for node in route["nodes"] if node.get("role") == "OPS"]


def test_read_only_service_review_uses_one_ops_observation() -> None:
    route = route_task(
        {
            "task_shape": "review",
            "surfaces": ["service"],
            "risk": "medium",
            "uncertainty": "low",
            "runtime_claim": False,
            "end_to_end_claim": False,
            "side_effect_class": "none",
            "task_prompt": "review the service source and configuration without effects",
            "dirty_scope": [],
            "claim_inputs": {},
        }
    )

    assert [node["id"] for node in _ops_nodes(route)] == ["ops_observation"]
    assert not any(node["kind"] == "effect_adapter" for node in route["nodes"])
    node_ids = {node["id"] for node in route["nodes"]}
    assert "ops_preflight" not in node_ids
    assert "ops_postcheck" not in node_ids


def test_effect_lane_keeps_ops_preflight_adapter_and_ops_postcheck() -> None:
    route = route_task(
        {
            "task_shape": "deploy",
            "surfaces": ["deploy", "service"],
            "risk": "high",
            "uncertainty": "low",
            "runtime_claim": True,
            "end_to_end_claim": False,
            "side_effect_class": "deploy",
            "task_prompt": "route one exact deploy effect through the guarded adapter",
            "dirty_scope": [],
            "claim_inputs": {},
        }
    )
    by_id = {node["id"]: node for node in route["nodes"]}

    assert [node["id"] for node in _ops_nodes(route)] == [
        "ops_preflight",
        "ops_postcheck",
    ]
    assert "ops_observation" not in by_id
    assert by_id["pm_deploy_approval"]["requires"] == ["ops_preflight"]
    assert by_id["deploy_adapter_v1"]["kind"] == "effect_adapter"
    assert by_id["deploy_adapter_v1"]["requires"] == ["pm_deploy_approval"]
    assert by_id["ops_postcheck"]["requires"] == ["deploy_adapter_v1"]


def test_unsupported_private_effect_cannot_be_downgraded_to_ops_observation() -> None:
    route = route_task(
        {
            "task_shape": "review",
            "surfaces": ["private_external_contact", "runtime_effect"],
            "risk": "high",
            "uncertainty": "low",
            "runtime_claim": True,
            "end_to_end_claim": False,
            "side_effect_class": "private_external_contact",
            "task_prompt": "reject private contact without an admitted adapter",
            "dirty_scope": [],
            "claim_inputs": {},
        }
    )
    by_id = {node["id"]: node for node in route["nodes"]}

    assert "external_effect_unsupported_v1" in by_id
    assert by_id["external_effect_unsupported_v1"]["kind"] == "unsupported_effect"
    assert by_id["external_effect_unsupported_v1"]["mandatory"] is True
    assert "ops_observation" not in by_id
    assert not any(node["kind"] == "effect_adapter" for node in route["nodes"])


def test_unsupported_broker_effect_remains_terminal_on_service_surface() -> None:
    route = route_task(
        {
            "task_shape": "review",
            "surfaces": ["ibkr", "private_external_contact", "service"],
            "risk": "high",
            "uncertainty": "low",
            "runtime_claim": True,
            "end_to_end_claim": False,
            "side_effect_class": "broker_probe",
            "task_prompt": "reject broker contact without an admitted adapter",
            "dirty_scope": [],
            "claim_inputs": {},
        }
    )
    by_id = {node["id"]: node for node in route["nodes"]}

    assert "broker_effect_unsupported_v1" in by_id
    assert by_id["broker_effect_unsupported_v1"]["kind"] == "unsupported_effect"
    assert by_id["pm_closure"]["requires"] == ["broker_effect_unsupported_v1"]
    assert "ops_observation" not in by_id
