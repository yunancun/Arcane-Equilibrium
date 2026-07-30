"""Routing behavior for the S2.0 observer-bootstrap effect class (SOURCE lane).

Mirrors the sibling ``target_host_probe`` routing tests: it pins the WP2 registry
invariant that a ``pg_observer_bootstrap`` source-lane task routes one
``ops_observation`` with the effect-adapter node DELIBERATELY NOT injected (the real
route_task effect node is deferred to the S2.0 EFFECT session), and the FORWARD-only
surface-consistency rule (pg/runtime_effect surface + runtime_claim=true + high/critical
risk).  This is the routing-side guarantee behind the "no effect node before the EFFECT
session" invariant that CC/E3 rely on; production apply stays fail-closed in source.
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
import agent_governance_pg_observer_bootstrap as obs  # noqa: E402


def _facts(**overrides):
    facts = {
        "task_shape": "audit",
        "surfaces": ["pg", "runtime_effect"],
        "risk": "high",
        "uncertainty": "low",
        "runtime_claim": True,
        "end_to_end_claim": False,
        "side_effect_class": "pg_observer_bootstrap",
        "task_prompt": "S2.0 production observer bootstrap (source lane)",
        "dirty_scope": [],
        "claim_inputs": {},
    }
    facts.update(overrides)
    return facts


def test_route_pg_observer_bootstrap_has_no_effect_adapter_and_one_ops_observation():
    route = routing.route_task(_facts())
    node_ids = [node["id"] for node in route["nodes"]]
    # 效果類已宣告 + 表面一致性已驗,但 WP2 SOURCE 波刻意 NOT 注入任何 effect adapter 節點。
    effect_nodes = [node for node in route["nodes"] if node["kind"] == "effect_adapter"]
    assert effect_nodes == []
    assert routing.PG_OBSERVER_BOOTSTRAP_ADAPTER_ID == obs.ADAPTER_ID
    assert routing.PG_OBSERVER_BOOTSTRAP_ADAPTER_ID not in node_ids
    # SOURCE lane 未 admitted effect adapter，故只需要一個唯讀 OPS observation。
    assert "ops_observation" in node_ids
    assert "ops_preflight" not in node_ids and "ops_postcheck" not in node_ids
    by_id = {node["id"]: node for node in route["nodes"]}
    assert by_id["ops_observation"]["role"] == "OPS"
    # 亦不得意外選中鄰接的 target-host / 通用 deploy / P0-B effect adapter。
    assert routing.TARGET_HOST_PROBE_ADAPTER_ID not in node_ids
    assert "deploy_adapter_v1" not in node_ids


def test_pg_observer_bootstrap_requires_pg_surface_claim_and_risk():
    # FORWARD-only 規則:少了 pg/runtime_effect 表面 / runtime_claim=true / 高risk 皆 fail-closed。
    for bad in (
        {"runtime_claim": False},
        {"surfaces": ["authority"]},
        {"risk": "low", "uncertainty": "low"},
    ):
        with pytest.raises(ValueError):
            routing.route_task(_facts(**bad))


def test_generic_pg_surface_without_observer_effect_does_not_synthesize_it():
    # 反向:裸 pg 表面(非 pg_observer_bootstrap 效果類)不得回歸出 observer-bootstrap 效果或 adapter。
    route = routing.route_task({
        "task_shape": "audit", "surfaces": ["pg"], "risk": "high", "uncertainty": "low",
        "runtime_claim": True, "end_to_end_claim": False, "side_effect_class": "none",
        "task_prompt": "read-only pg inspection", "dirty_scope": [], "claim_inputs": {},
    })
    node_ids = [node["id"] for node in route["nodes"]]
    assert routing.PG_OBSERVER_BOOTSTRAP_ADAPTER_ID not in node_ids
    assert [node for node in route["nodes"] if node["kind"] == "effect_adapter"] == []
