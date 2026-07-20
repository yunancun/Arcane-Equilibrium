"""Reachability tests for typed conditional Context packs."""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_execution import (  # noqa: E402
    capture_repository_baseline,
    compile_context,
    materialize_context_artifact,
    validate_context_artifact,
)
from agent_governance_execution import context_plan_digest  # noqa: E402
from agent_governance_registry import load_registry, validate_registry  # noqa: E402


def _facts(**overrides):
    facts = {
        "task_shape": "review",
        "surfaces": ["comments"],
        "risk": "low",
        "uncertainty": "low",
        "side_effect_class": "none",
        "objective": "review one stable source-only interface",
        "scope": ["AGENTS.md"],
        "dirty_scope": ["AGENTS.md"],
        "acceptance_criteria": ["the admitted role can start without fake evidence"],
        "hard_stops": ["no runtime or external effect"],
        "baseline": capture_repository_baseline(),
        "direct_interfaces": ["context_reachability_probe_v1"],
        "previous_failure": "descriptive virtual sources blocked every dispatch",
    }
    facts.update(overrides)
    return facts


def test_narrow_stable_pm_does_not_preload_active_state() -> None:
    plan = compile_context("PM", _facts())
    assert "TODO.md" not in [source["source"] for source in plan["sources"]]
    assert plan["unresolved_sources"] == []
    assert plan["budget"]["pass_allowed"] is True


@pytest.mark.parametrize(
    ("role", "surfaces", "expected_debt"),
    [
        ("PM", ["multi_agent"], set()), ("PA", ["architecture"], set()),
        ("FA", ["functional"], set()), ("CC", ["governance"], set()),
        ("E1", ["python"], set()), ("E1a", ["gui"], set()),
        ("E2", ["python"], set()), ("E3", ["security"], set()),
        ("E4", ["acceptance"], set()), ("E5", ["performance"], set()),
        ("QA", ["functional"], set()), ("QC", ["quant"], set()),
        ("MIT", ["ml"], set()), ("AI-E", ["consumption"], set()),
        ("BB", ["bybit"], {"official Bybit source when freshness matters"}),
        ("IB", ["ibkr"], {"official IBKR source when freshness matters"}),
        ("OPS", ["operations"], {"runtime observation"}),
        ("A3", ["visual"], {"viewport/accessibility evidence"}),
        ("R4", ["docs"], set()), ("TW", ["docs"], set()),
    ],
)
def test_every_registry_role_has_a_spawnable_representative_source_task(
    role: str, surfaces: list[str], expected_debt: set[str],
) -> None:
    plan = compile_context(
        role,
        _facts(
            surfaces=surfaces,
            risk="medium",
            uncertainty="medium",
            objective=f"run the representative source-only {role} review",
        ),
    )
    assert set(plan["evidence_debt"]) == expected_debt, (
        role, plan["evidence_debt"],
    )
    assert plan["budget"]["call_allowed"] is True, (
        role, plan["budget"],
    )
    assert plan["budget"]["claim_pass_eligible"] is (not expected_debt)


@pytest.mark.parametrize(
    ("role", "overrides", "required_sources"),
    [
        (
            "OPS",
            {"surfaces": ["runtime"], "runtime_claim": True},
            {"runtime observation"},
        ),
        (
            "QA",
            {"surfaces": ["runtime"], "end_to_end_claim": True},
            {"runtime observation", "business outcome observation"},
        ),
        (
            "BB",
            {"surfaces": ["bybit"]},
            {"official Bybit source when freshness matters"},
        ),
        (
            "IB",
            {"surfaces": ["ibkr"]},
            {"official IBKR source when freshness matters"},
        ),
        (
            "QC",
            {
                "surfaces": ["public_web_read"],
                "side_effect_class": "public_web_read",
            },
            {"external policy observation"},
        ),
    ],
)
def test_claim_required_runtime_external_and_broker_evidence_stays_fail_closed(
    role: str, overrides: dict, required_sources: set[str],
) -> None:
    plan = compile_context(role, _facts(risk="high", **overrides))
    assert required_sources <= set(plan["unresolved_sources"])
    assert required_sources <= set(plan["evidence_debt"])
    assert plan["budget"]["call_allowed"] is True
    assert plan["budget"]["claim_pass_eligible"] is False
    assert plan["budget"]["pass_allowed"] is True
    assert {item["source"] for item in plan["acquisition_plan"]} >= required_sources


def test_caller_producer_label_cannot_self_attest_required_runtime_evidence() -> None:
    plan = compile_context(
        "OPS",
        _facts(
            risk="high",
            surfaces=["runtime"],
            runtime_claim=True,
            evidence_state={
                "runtime observation": {
                    "producer": "caller_claimed_runtime_producer_v1",
                }
            },
        ),
    )
    runtime = next(
        source for source in plan["sources"]
        if source["source"] == "runtime observation"
    )
    assert runtime["status"] == "unbacked_evidence_state"
    assert "runtime observation" in plan["unresolved_sources"]


def test_local_inventory_context_is_admissible_through_public_artifact_validator() -> None:
    facts = _facts(
        risk="high", surfaces=["architecture"],
        objective="admit deterministic local architecture inventories",
    )
    artifact = materialize_context_artifact(compile_context("PA", facts))
    result = validate_context_artifact(artifact, expected_task_facts=facts)
    assert result["errors"] == []


def test_context_required_when_rejects_unknown_surface_typo() -> None:
    registry = deepcopy(load_registry())
    registry["context_packs"]["active_state"][0]["required_when"]["surfaces_any"].append(
        "runtiem"
    )
    assert any("unknown surface" in error for error in validate_registry(registry, ROOT))


def test_full_profit_and_incident_context_activate_bounded_current_todo() -> None:
    for surface in ("full_audit", "profit_diagnosis", "incident_rca"):
        plan = compile_context(
            "PM",
            _facts(
                surfaces=[surface],
                risk="medium" if surface != "full_audit" else "unknown",
                uncertainty="low",
            ),
        )
        todo = next(
            source for source in plan["sources"]
            if source["source"] == "TODO.md#AI/ML 一分鐘派發看板"
        )
        assert todo["planned_tokens"] < todo["full_file_token_estimate"]


def test_high_cardinality_interface_inventory_is_bounded_and_spawnable() -> None:
    plan = compile_context(
        "E5",
        _facts(
            surfaces=["performance"],
            risk="medium",
            uncertainty="medium",
            direct_interfaces=["test"],
            objective="profile the broad test interface without preloading its full grep corpus",
        ),
    )
    callers = next(source for source in plan["sources"] if source["source"] == "direct callers")
    tests = next(
        source for source in plan["sources"]
        if source["source"] == "focused acceptance tests"
    )
    assert callers["content"]["match_count"] > len(callers["content"]["matches"])
    assert tests["content"]["match_count"] > len(tests["content"]["matches"])
    assert len(callers["content"]["matches"]) <= 64
    assert len(tests["content"]["matches"]) <= 64
    assert plan["budget"]["compiler_estimated_input_tokens"] < 24_000
    assert plan["budget"]["call_allowed"] is True


def test_standard_review_band_avoids_a_more_expensive_duplicate_context_split() -> None:
    facts = _facts(
        surfaces=["performance"], risk="medium", uncertainty="medium",
        direct_interfaces=["context"],
        objective="review the real Context interface without duplicating core and callers",
    )
    base_plan = compile_context("E5", facts)
    base_budget = base_plan["budget"]
    reserve_end = (
        base_budget["target_context_tokens"]
        + base_budget["quality_reserve_context_tokens"]
    )
    required_padding = max(
        0, 4 * (reserve_end + 1 - base_budget["estimated_tokens"]),
    )
    plan = None
    for extra_bytes in range(required_padding, required_padding + 8_193, 512):
        candidate = compile_context(
            "E5", {
                **facts,
                "task_prompt": "Review the bound Context interface. " + "x" * extra_bytes,
            },
        )
        candidate_budget = candidate["budget"]
        if (
            reserve_end < candidate_budget["estimated_tokens"]
            < candidate_budget["max_context_tokens_per_call"]
        ):
            plan = candidate
            break
    assert plan is not None, (
        "bounded deterministic padding could not reach the reviewed band",
        base_budget,
    )
    budget = plan["budget"]
    assert (
        budget["target_context_tokens"]
        + budget["quality_reserve_context_tokens"]
    ) == reserve_end
    assert reserve_end < budget["estimated_tokens"] < budget["max_context_tokens_per_call"]
    assert budget["action"] == "review_required"
    assert budget["review_required"] is True
    assert "avoids duplicate" in budget["review_rationale"]
    assert budget["call_allowed"] is True


def test_shared_task_prefix_is_identical_before_small_role_deltas() -> None:
    facts = _facts(
        task_shape="review", surfaces=["python"], risk="medium", uncertainty="medium",
        objective="independently inspect one admitted Python interface",
    )
    artifacts = {
        role: materialize_context_artifact(compile_context(role, facts))
        for role in ("E1", "E2", "E4")
    }
    assert len({item["shared_task_context_digest"] for item in artifacts.values()}) == 1
    assert len({item["shared_task_context_canonical"] for item in artifacts.values()}) == 1
    assert len({item["role_context_delta_digest"] for item in artifacts.values()}) == 3
    for role, artifact in artifacts.items():
        assert f'"logical_role":"{role}"' in artifact["role_context_delta_canonical"]
        assert artifact["semantic_input_tokens"] < artifact["canonical_plan"].__len__() // 4


def test_semantic_projection_tamper_is_rejected_before_call_admission() -> None:
    facts = _facts(surfaces=["python"], risk="medium", uncertainty="medium")
    artifact = materialize_context_artifact(compile_context("E2", facts))
    forged = deepcopy(artifact)
    forged["role_context_delta_canonical"] = forged["role_context_delta_canonical"].replace(
        '"logical_role":"E2"', '"logical_role":"E1"',
    )
    result = validate_context_artifact(forged, expected_task_facts=facts)
    assert any("role_context_delta_canonical" in error for error in result["errors"])


def test_unrelated_ambient_generation_changes_full_envelope_not_semantic_cache() -> None:
    facts = _facts(surfaces=["python"], risk="medium", uncertainty="medium")
    original = compile_context("E2", facts)
    changed = deepcopy(original)
    changed["task_contract"]["baseline"]["dirty_diff_hash"] = "sha256:" + "9" * 64
    changed["mandatory_content"]["baseline"] = changed["task_contract"]["baseline"]
    for source in changed["sources"]:
        source["baseline"] = changed["task_contract"]["baseline"]
    changed["context_digest"] = context_plan_digest(changed)
    original_artifact = materialize_context_artifact(original)
    changed_artifact = materialize_context_artifact(changed)
    assert original_artifact["artifact_digest"] != changed_artifact["artifact_digest"]
    assert original_artifact["shared_task_context_digest"] == changed_artifact["shared_task_context_digest"]
    assert "repository_bytes_v1" not in original_artifact["shared_task_context_canonical"]


def test_verdict_evidence_freshness_changes_semantic_cache_digest() -> None:
    facts = _facts(surfaces=["bybit"], risk="medium", uncertainty="medium")
    original = compile_context("BB", facts)
    changed = deepcopy(original)
    evidence = next(
        source for source in changed["sources"]
        if source["source"] == "official Bybit source when freshness matters"
    )
    evidence["observed_at"] = "2026-07-11T00:00:00+00:00"
    evidence["expires_at"] = "2026-07-12T00:00:00+00:00"
    evidence["producer"] = {"id": "external_policy_capture_adapter_v1", "input_digest": "sha256:" + "1" * 64}
    changed["context_digest"] = context_plan_digest(changed)
    assert (
        materialize_context_artifact(original)["shared_task_context_digest"]
        != materialize_context_artifact(changed)["shared_task_context_digest"]
    )
