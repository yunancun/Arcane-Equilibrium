"""Routing behavior for the S2.1 quiesce-fence effect class (SOURCE lane).

Mirrors the sibling ``pg_observer_bootstrap`` / ``target_host_probe`` routing tests: it pins the WP3
registry invariant that a ``quiesce_fence`` source-lane task routes one ``ops_observation`` with the
effect-adapter node DELIBERATELY NOT injected (the real route_task effect node is deferred to the S2.1
EFFECT session), and the FORWARD-only surface-consistency rule (runtime_effect/service surface +
runtime_claim=true + high/critical risk).  This is the routing-side guarantee behind the "no effect node
before the EFFECT session" invariant; the production/live fence stays fail-closed in source.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_routing as routing  # noqa: E402
import agent_governance_alr_quiesce_fence as q  # noqa: E402


def _facts(**overrides):
    facts = {
        "task_shape": "audit",
        "surfaces": ["runtime_effect", "service"],
        "risk": "high",
        "uncertainty": "low",
        "runtime_claim": True,
        "end_to_end_claim": False,
        "side_effect_class": "quiesce_fence",
        "task_prompt": "S2.1 ALR quiesce fence (source lane)",
        "dirty_scope": [],
        "claim_inputs": {},
    }
    facts.update(overrides)
    return facts


def test_route_quiesce_fence_has_no_effect_adapter_and_one_ops_observation():
    route = routing.route_task(_facts())
    node_ids = [node["id"] for node in route["nodes"]]
    effect_nodes = [node for node in route["nodes"] if node["kind"] == "effect_adapter"]
    assert effect_nodes == []
    assert routing.QUIESCE_FENCE_ADAPTER_ID == q.ADAPTER_ID
    assert routing.QUIESCE_FENCE_ADAPTER_ID not in node_ids
    assert "ops_observation" in node_ids
    assert "ops_preflight" not in node_ids and "ops_postcheck" not in node_ids
    by_id = {node["id"]: node for node in route["nodes"]}
    assert by_id["ops_observation"]["role"] == "OPS"
    # 亦不得意外選中鄰接的 pg-observer / target-host / 通用 deploy / P0-B effect adapter。
    assert routing.PG_OBSERVER_BOOTSTRAP_ADAPTER_ID not in node_ids
    assert routing.TARGET_HOST_PROBE_ADAPTER_ID not in node_ids
    assert "deploy_adapter_v1" not in node_ids


def test_quiesce_fence_requires_runtime_surface_claim_and_risk():
    for bad in (
        {"runtime_claim": False},
        {"surfaces": ["authority"]},
        {"risk": "low", "uncertainty": "low"},
    ):
        with pytest.raises(ValueError):
            routing.route_task(_facts(**bad))


def test_generic_runtime_surface_without_quiesce_effect_does_not_synthesize_it():
    route = routing.route_task({
        "task_shape": "audit", "surfaces": ["runtime_effect"], "risk": "high", "uncertainty": "low",
        "runtime_claim": True, "end_to_end_claim": False, "side_effect_class": "none",
        "task_prompt": "read-only runtime inspection", "dirty_scope": [], "claim_inputs": {},
    })
    node_ids = [node["id"] for node in route["nodes"]]
    assert routing.QUIESCE_FENCE_ADAPTER_ID not in node_ids
    assert [node for node in route["nodes"] if node["kind"] == "effect_adapter"] == []
