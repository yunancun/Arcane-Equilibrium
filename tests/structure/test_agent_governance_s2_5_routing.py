"""Routing behavior for the S2.5 start-intent effect class (SOURCE lane).

Mirrors the sibling ``quiesce_fence`` / ``s2_4`` routing tests: it pins the WP5 registry
invariant that an ``s2_5_start_intent`` task routes ``... -> ops_preflight -> ops_postcheck``
with the effect-adapter nodes DELIBERATELY NOT injected (the real route_task effect nodes are
deferred to the S2.5 EFFECT session), the FORWARD-only surface-consistency rule
(runtime_effect/service surface + runtime_claim=true + high/critical risk), and the design §6
forbidden surfaces (pg/secret/deploy = install/PREPARE authority, broker surfaces always).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for _candidate in (HELPERS, ML_ROOT):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import agent_governance_routing as routing  # noqa: E402
import aiml_gate_receipt_s2_5 as s2_5_leaf  # noqa: E402


def _facts(**overrides):
    facts = {
        "task_shape": "audit",
        "surfaces": ["runtime_effect", "service"],
        "risk": "high",
        "uncertainty": "low",
        "runtime_claim": True,
        "end_to_end_claim": False,
        "side_effect_class": "s2_5_start_intent",
        "task_prompt": "S2.5 running-attestation start (source lane)",
        "dirty_scope": [],
        "claim_inputs": {},
    }
    facts.update(overrides)
    return facts


def test_route_s2_5_start_has_no_effect_adapter_and_ops_preflight_then_postcheck():
    route = routing.route_task(_facts())
    node_ids = [node["id"] for node in route["nodes"]]
    assert [node for node in route["nodes"] if node["kind"] == "effect_adapter"] == []
    # 兩個 s2_5 adapter id 都不得出現在 node_ids(EFFECT session 前不注入)。
    assert routing.S2_5_RUNTIME_START_ADAPTER_ID not in node_ids
    assert routing.S2_5_FINAL_ATTESTATION_ADAPTER_ID not in node_ids
    assert "ops_preflight" in node_ids and "ops_postcheck" in node_ids
    by_id = {node["id"]: node for node in route["nodes"]}
    assert by_id["ops_postcheck"]["requires"] == ["ops_preflight"]
    # 亦不得意外選中鄰接 adapter。
    assert routing.S2_4_INSTALL_ADAPTER_ID not in node_ids
    assert routing.QUIESCE_FENCE_ADAPTER_ID not in node_ids
    assert "deploy_adapter_v1" not in node_ids


def test_s2_5_adapter_ids_match_the_leaf_v3_matrix():
    matrix = s2_5_leaf.AIML_COMPONENT_EFFECT_CLASS_MATRIX_V3
    assert routing.S2_5_RUNTIME_START_ADAPTER_ID == (
        matrix["ENGINE_SCANNER_SERVICE_START"]["adapter_id"]
    )
    assert routing.S2_5_FINAL_ATTESTATION_ADAPTER_ID == (
        matrix["WATCHDOG_ROLLBACK_TEST"]["adapter_id"]
    )


def test_s2_5_start_requires_runtime_surface_claim_and_risk():
    for bad in (
        {"runtime_claim": False},
        {"surfaces": ["authority"]},
        {"risk": "low", "uncertainty": "low"},
    ):
        with pytest.raises(ValueError):
            routing.route_task(_facts(**bad))


@pytest.mark.parametrize("forbidden", ["pg", "secret", "deploy", "bybit", "ibkr"])
def test_s2_5_start_rejects_install_prepare_and_broker_surfaces(forbidden):
    # deploy 面在更早的通用規則就被拒(deploy surface 需 side_effect_class=deploy);
    # 其餘面由 s2_5 專屬 forbidden-surface 規則拒。兩路都必須是 ValueError。
    with pytest.raises(
        ValueError, match="must not carry|requires side_effect_class=deploy"
    ):
        routing.route_task(_facts(surfaces=["runtime_effect", "service", forbidden]))


def test_generic_runtime_surface_without_s2_5_effect_does_not_synthesize_it():
    route = routing.route_task({
        "task_shape": "audit", "surfaces": ["runtime_effect"], "risk": "high",
        "uncertainty": "low", "runtime_claim": True, "end_to_end_claim": False,
        "side_effect_class": "none", "task_prompt": "read-only runtime inspection",
        "dirty_scope": [], "claim_inputs": {},
    })
    node_ids = [node["id"] for node in route["nodes"]]
    assert routing.S2_5_RUNTIME_START_ADAPTER_ID not in node_ids
    assert [node for node in route["nodes"] if node["kind"] == "effect_adapter"] == []


def test_registry_carries_both_s2_5_adapters_authority_locked():
    registry = json.loads(
        (ROOT / ".codex" / "agent_registry_v1.json").read_text(encoding="utf-8")
    )
    adapters = registry["effect_adapters"]
    for adapter_id in (
        routing.S2_5_RUNTIME_START_ADAPTER_ID,
        routing.S2_5_FINAL_ATTESTATION_ADAPTER_ID,
    ):
        entry = adapters[adapter_id]
        assert entry["status"] == "AUTHORITY_LOCKED_PRODUCTION_CAPABLE"
        assert entry["owner_session"] == "S2.5"
        invariant = entry["invariant"]
        # invariant 關鍵子句(§6):fail-closed until / attestor 唯一鑰匙 / 常量 unit /
        # rollback / reset last / 九 authority false / EFFECT session 前不注入。
        for clause in (
            "fail-closed EXTERNAL_VERIFICATION_PENDING",
            "nine authorities stay false",
            "no route_task effect node or closure effect binding is injected before the S2.5 EFFECT session",
        ):
            assert clause in invariant, (adapter_id, clause)
    assert "rollback-to-disabled" in adapters[
        routing.S2_5_RUNTIME_START_ADAPTER_ID
    ]["invariant"]
    assert "LAST lifecycle operation" in adapters[
        routing.S2_5_FINAL_ATTESTATION_ADAPTER_ID
    ]["invariant"]
