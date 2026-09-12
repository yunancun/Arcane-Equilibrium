"""Workflow repair keeps complementary review without incidental economics work."""

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "helper_scripts" / "maintenance_scripts"))
from agent_governance_routing import route_task  # noqa: E402


def _route(*surfaces: str) -> dict:
    return route_task({
        "task_shape": "fix", "surfaces": ["python", *surfaces],
        "risk": "low", "uncertainty": "low", "side_effect_class": "repo_write",
        "objective": "Repair peer-review finding handling",
        "scope": ["review.py"], "dirty_scope": ["review.py"],
        "task_prompt": "Repair peer-review finding handling",
        "acceptance_criteria": ["Review findings remain bounded"],
        "hard_stops": ["No new prerequisites"],
    })


@pytest.mark.parametrize("surface", ["agent_workflow", "multi_agent"])
def test_workflow_only_repair_keeps_two_complementary_reviews(surface: str) -> None:
    route = _route(surface)
    nodes = {node["id"]: node for node in route["nodes"]}

    assert "ai_economics_review" not in nodes
    assert nodes["independent_review"]["role"] == "E2"
    assert nodes["regression"]["role"] == "E4"
    assert nodes["regression"]["requires"] == ["independent_review"]
    assert not {"security_gate", "constitutional_gate", "operations_review"} & nodes.keys()
    assert route["task_execution_control"]["automatic_wakeup_admitted"] is False
    assert any(item["role"] == "AI-E" and item["reason"] for item in route["skipped"])


@pytest.mark.parametrize("surface", ["ai", "llm", "full_audit", "model_routing", "consumption"])
def test_explicit_economics_or_audit_surface_retains_its_review(surface: str) -> None:
    route = _route("agent_workflow", surface)
    assert any(
        node["id"] == "ai_economics_review" and node["role"] == "AI-E"
        for node in route["nodes"]
    )
