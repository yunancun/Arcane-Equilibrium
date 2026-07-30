"""Aggregate execution-policy, history, surface, and recursion contracts."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
sys.path.insert(0, str(HELPERS))

from agent_governance_execution_policy import (  # noqa: E402
    admit_execution_event,
    compile_execution_budget_policy,
    default_history_binding,
    execution_policy_digest,
    new_execution_event_ledger,
    registry_execution_policy_errors,
    requested_history_errors,
    surface_allows_mandatory_role,
    surface_profile_binding,
    validate_execution_event_ledger,
)
from agent_governance_execution import (  # noqa: E402
    capture_repository_baseline,
    compile_context,
    materialize_context_artifact,
)
from agent_governance_context_validation import (  # noqa: E402
    validate_context_artifact,
)
from agent_governance_registry import load_registry  # noqa: E402
from agent_governance_routing import route_task  # noqa: E402
from agent_governance_workflow_identity import requested_identity_errors  # noqa: E402


DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def _event(
    event_id: str,
    kind: str,
    *,
    depth: int,
    call_digest: str | None = None,
) -> dict:
    return {
        "event_id": event_id,
        "kind": kind,
        "parent_event_id": None if kind == "root_turn" else "root:1",
        "node_id": "PM" if kind == "root_turn" else "node-a",
        "spawn_depth": depth,
        "watcher_id": "watcher-1",
        "outcome": "completed",
        "call_record_digest": call_digest,
    }


def test_registry_compiles_one_digest_bound_execution_budget_policy() -> None:
    registry = load_registry()

    assert registry_execution_policy_errors(registry) == []
    policy = compile_execution_budget_policy("narrow", registry)
    assert policy["schema_version"] == "execution_budget_policy_v1"
    assert policy["envelope"] == "narrow"
    assert policy["max_concurrent_calls"] == 2
    assert policy["max_spawn_depth_from_root"] == 1
    assert policy["max_total_model_turns"] == (
        1 + policy["max_call_attempts"] + policy["max_followup_attempts"]
    )
    assert policy["platform_token_cap"] == {
        "status": "EXTERNAL_LIMIT",
        "max_total_tokens": None,
        "required_metric": "platform_attested_total_tokens",
    }
    assert execution_policy_digest(policy).startswith("sha256:")


def test_route_promotes_envelope_after_required_node_projection() -> None:
    facts = {
        "task_shape": "implementation",
        "surfaces": ["python", "docs", "bybit"],
        "risk": "low",
        "uncertainty": "low",
        "side_effect_class": "repo_write",
        "dirty_scope": ["program_code/example.py", "docs/example.md"],
        "task_prompt": "implement code docs and Bybit compatibility",
    }
    route = route_task(facts)

    assert len(route["required_role_nodes"]) == 6
    assert route["budget_envelope"] == "standard"
    assert route["execution_budget_policy"]["envelope"] == "standard"
    assert route["execution_budget_policy_digest"] == execution_policy_digest(
        route["execution_budget_policy"]
    )


def test_route_and_context_share_exact_execution_budget_policy() -> None:
    registry = load_registry()
    facts = {
        "task_shape": "implementation",
        "surfaces": ["python", "docs", "bybit"],
        "risk": "low",
        "uncertainty": "low",
        "runtime_claim": False,
        "end_to_end_claim": False,
        "side_effect_class": "repo_write",
        "objective": "bind one promoted execution policy",
        "scope": [
            "helper_scripts/maintenance_scripts/agent_governance_execution.py",
            "docs/agents/context-loading.md",
        ],
        "dirty_scope": [
            "helper_scripts/maintenance_scripts/agent_governance_execution.py",
            "docs/agents/context-loading.md",
        ],
        "acceptance_criteria": ["route and Context bytes are identical"],
        "hard_stops": ["no runtime effect"],
        "baseline": capture_repository_baseline(ROOT),
        "direct_interfaces": ["Development-Agent Governance Module"],
        "previous_failure": "Context independently selected narrow",
        "focus": "execution policy digest",
        "task_prompt": "bind route and Context execution policy",
    }
    route = route_task(facts)
    plan = compile_context("E2", facts, registry, ROOT)

    assert plan["budget"]["envelope"] == route["budget_envelope"] == "standard"
    assert plan["budget"]["authority"] == route["execution_budget_policy"]
    assert plan["budget"]["authority_digest"] == route[
        "execution_budget_policy_digest"
    ]


def test_injected_registry_is_one_route_context_and_validation_authority() -> None:
    registry = deepcopy(load_registry())
    registry["budget_envelopes"]["narrow"]["max_unique_nodes"] = 2
    registry["native_agent_adapters"]["E1"] = [{
        "name": "E1-test-injected",
        "node_class": "work",
        "permission": registry["roles"]["E1"]["permission"],
    }]
    scope = ["helper_scripts/maintenance_scripts/agent_governance_execution.py"]
    facts = {
        "task_shape": "implementation",
        "surfaces": ["python"],
        "risk": "low",
        "uncertainty": "low",
        "runtime_claim": False,
        "end_to_end_claim": False,
        "side_effect_class": "repo_write",
        "objective": "bind one injected Registry across route and Context",
        "scope": scope,
        "dirty_scope": scope,
        "verification_scope": scope,
        "acceptance_criteria": ["three delegated nodes promote beyond narrow"],
        "hard_stops": ["no ambient Registry reload"],
        "baseline": capture_repository_baseline(ROOT),
        "direct_interfaces": ["Development-Agent Governance Module"],
        "previous_failure": "Context used injected caps after ambient routing",
        "task_prompt": "compile one custom-registry route and Context",
    }

    route = route_task(facts, registry=registry)
    plan = compile_context("E2", facts, registry, ROOT)
    artifact = materialize_context_artifact(plan)
    validated = validate_context_artifact(
        artifact,
        registry=registry,
        root=ROOT,
    )

    assert len(route["required_role_nodes"]) == 3
    assert route["budget_envelope"] == plan["budget"]["envelope"] == "standard"
    assert next(
        node for node in route["required_role_nodes"]
        if node["node_id"] == "implementation"
    )["native_agent"] == "E1-test-injected"
    assert plan["budget"]["authority"] == route["execution_budget_policy"]
    assert validated["errors"] == []


def test_history_defaults_none_and_rejects_missing_all_or_unbound_bounded_mode() -> None:
    registry = load_registry()
    history = default_history_binding(registry)

    assert history == {
        "schema_version": "requested_history_v1",
        "mode": "none",
        "source_thread_id": None,
        "boundary_turn_id": None,
        "ephemeral": True,
        "exception_digest": None,
    }
    assert requested_history_errors(history, admitted_exception_digests=set()) == []
    assert requested_history_errors(None, admitted_exception_digests=set())
    assert requested_history_errors(
        {**history, "mode": "all"}, admitted_exception_digests=set()
    )

    bounded = {
        **history,
        "mode": "bounded",
        "source_thread_id": "thread-1",
        "boundary_turn_id": "turn-12",
        "exception_digest": DIGEST_A,
    }
    assert requested_history_errors(
        bounded, admitted_exception_digests={DIGEST_A}
    ) == []
    assert requested_history_errors(
        bounded, admitted_exception_digests=set()
    )


def test_surface_profile_prevents_generic_host_from_closing_mandatory_roles() -> None:
    registry = load_registry()
    saved = surface_profile_binding("claude_saved_workflow_v1", registry)
    codex = surface_profile_binding("codex_native_collaboration_v1", registry)
    generic = surface_profile_binding("generic_host_v1", registry)

    assert saved["profile"]["schema_version"] == "execution_surface_profile_v1"
    assert saved["profile"]["native_selector_binding"] == "enforced"
    assert surface_allows_mandatory_role(saved["profile"], "PA")
    assert codex["profile"]["native_selector_binding"] == "reported_only"
    assert codex["profile"]["history_selection"] == "reported_only"
    assert codex["profile"]["ephemeral_fork"] == "reported_only"
    assert codex["profile"]["event_coverage"] == []
    assert not surface_allows_mandatory_role(codex["profile"], "PA")
    assert not surface_allows_mandatory_role(codex["profile"], "E4")
    assert not surface_allows_mandatory_role(generic["profile"], "PA")
    assert not surface_allows_mandatory_role(generic["profile"], "E4")
    assert saved["digest"] != generic["digest"]


@pytest.mark.parametrize(
    "field",
    [
        "native_selector_binding",
        "history_selection",
        "ephemeral_fork",
        "concurrency_limit",
    ],
)
def test_mandatory_role_surface_requires_all_identity_controls_enforced(
    field: str,
) -> None:
    registry = deepcopy(load_registry())
    registry["execution_policy"]["surface_profiles"][
        "claude_saved_workflow_v1"
    ][field] = "reported_only"

    errors = registry_execution_policy_errors(registry)
    assert any(
        "mandatory-role eligible surface requires enforced" in error
        for error in errors
    )
    profile = registry["execution_policy"]["surface_profiles"][
        "claude_saved_workflow_v1"
    ]
    assert not surface_allows_mandatory_role(profile, "E2")


def test_governed_surfaces_disable_model_visible_interrupt_injection() -> None:
    registry = load_registry()
    assert registry["execution_policy"]["surface_profiles"][
        "claude_saved_workflow_v1"
    ]["model_visible_interruptions"] == "disabled"
    assert registry["execution_policy"]["surface_profiles"][
        "codex_native_collaboration_v1"
    ]["model_visible_interruptions"] == "disabled"
    assert registry["execution_policy"]["surface_profiles"]["generic_host_v1"][
        "model_visible_interruptions"
    ] == "unavailable"


def test_requested_identity_binds_history_and_surface_capabilities() -> None:
    registry = load_registry()
    surface = surface_profile_binding("claude_saved_workflow_v1", registry)
    requested = {
        "logical_role": "E2",
        "platform": surface["profile"]["platform"],
        "platform_requested_agent": "E2",
        "native_binding": {
            "logical_role": "E2",
            "native_agent": "E2",
            "node_class": "verification",
            "permission": "read_only",
        },
        "surface_profile_id": surface["profile"]["profile_id"],
        "surface_profile_digest": surface["digest"],
        "history": default_history_binding(registry),
        "model": registry["saved_workflow_model_policy"]["model"],
        "effort": registry["saved_workflow_model_policy"]["role_efforts"]["E2"],
        "isolation": None,
        "node_class": "verification",
        "permission": "read_only",
    }

    assert requested_identity_errors(requested, expected_role="E2") == []
    missing_history = deepcopy(requested)
    del missing_history["history"]
    assert requested_identity_errors(missing_history, expected_role="E2")
    inherited_all = deepcopy(requested)
    inherited_all["history"]["mode"] = "all"
    assert requested_identity_errors(inherited_all, expected_role="E2")
    forged_surface = deepcopy(requested)
    forged_surface["surface_profile_digest"] = DIGEST_A
    assert requested_identity_errors(forged_surface, expected_role="E2")
    inherited_or_arbitrary = deepcopy(requested)
    inherited_or_arbitrary["model"] = None
    inherited_or_arbitrary["effort"] = "max"
    identity_errors = requested_identity_errors(
        inherited_or_arbitrary, expected_role="E2"
    )
    assert any("model differs" in error for error in identity_errors)
    assert any("effort differs" in error for error in identity_errors)

    generic = surface_profile_binding("generic_host_v1", registry)
    degraded = deepcopy(requested)
    degraded["platform"] = generic["profile"]["platform"]
    degraded["surface_profile_id"] = generic["profile"]["profile_id"]
    degraded["surface_profile_digest"] = generic["digest"]
    assert any(
        "mandatory" in error
        for error in requested_identity_errors(degraded, expected_role="E2")
    )


def test_event_ledger_denies_next_call_at_cap_and_rejects_child_spawn() -> None:
    registry = load_registry()
    policy = deepcopy(compile_execution_budget_policy("narrow", registry))
    policy["max_call_attempts"] = 1
    policy["max_total_model_turns"] = (
        1 + policy["max_call_attempts"] + policy["max_followup_attempts"]
    )
    surface = surface_profile_binding("claude_saved_workflow_v1", registry)
    ledger = new_execution_event_ledger(
        root_execution_id="root-exec-1",
        policy_digest=execution_policy_digest(policy),
        surface_profile_digest=surface["digest"],
        watcher_id="watcher-1",
    )

    allowed, ledger = admit_execution_event(
        policy, ledger, _event("root:1", "root_turn", depth=0)
    )
    assert allowed
    allowed, ledger = admit_execution_event(
        policy,
        ledger,
        _event("call:1", "model_call", depth=1, call_digest=DIGEST_A),
    )
    assert allowed
    allowed, ledger = admit_execution_event(
        policy,
        ledger,
        _event("call:2", "model_call", depth=1, call_digest=DIGEST_B),
    )
    assert not allowed
    assert ledger["terminal_reason"] == "BUDGET_EXHAUSTED"
    assert validate_execution_event_ledger(
        policy, ledger, call_record_digests=[DIGEST_A]
    ) == []
    assert validate_execution_event_ledger(
        policy, ledger, call_record_digests=[DIGEST_A, DIGEST_B]
    )

    child_ledger = new_execution_event_ledger(
        root_execution_id="root-exec-2",
        policy_digest=execution_policy_digest(policy),
        surface_profile_digest=surface["digest"],
        watcher_id="watcher-1",
    )
    _, child_ledger = admit_execution_event(
        policy, child_ledger, _event("root:1", "root_turn", depth=0)
    )
    allowed, child_ledger = admit_execution_event(
        policy, child_ledger, _event("spawn:child", "spawn", depth=2)
    )
    assert not allowed
    assert child_ledger["terminal_reason"] == "SPAWN_DEPTH_EXCEEDED"


def test_execution_event_ledger_rejects_a_call_with_a_missing_parent() -> None:
    registry = load_registry()
    policy = compile_execution_budget_policy("narrow", registry)
    surface = surface_profile_binding("claude_saved_workflow_v1", registry)
    ledger = new_execution_event_ledger(
        root_execution_id="root-exec-orphan",
        policy_digest=execution_policy_digest(policy),
        surface_profile_digest=surface["digest"],
        watcher_id="watcher-1",
    )
    _, ledger = admit_execution_event(
        policy, ledger, _event("root:1", "root_turn", depth=0)
    )
    orphan = _event(
        "call:orphan", "model_call", depth=1, call_digest=DIGEST_A
    )
    orphan["parent_event_id"] = "missing:parent"

    with pytest.raises(ValueError, match="parent"):
        admit_execution_event(policy, ledger, orphan)

    forged = deepcopy(ledger)
    forged["events"].append({**orphan, "sequence": 1})
    forged["ledger_digest"] = (
        "sha256:bb26ac150271743148e81ab3bd3d7b9e2a4f501872aa44daff1b47dc93933c3f"
    )
    errors = validate_execution_event_ledger(
        policy, forged, call_record_digests=[DIGEST_A]
    )
    assert any("parent" in error for error in errors)


def test_execution_event_ledger_requires_exactly_one_first_root() -> None:
    registry = load_registry()
    policy = compile_execution_budget_policy("narrow", registry)
    surface = surface_profile_binding("claude_saved_workflow_v1", registry)
    empty = new_execution_event_ledger(
        root_execution_id="root-exec-order",
        policy_digest=execution_policy_digest(policy),
        surface_profile_digest=surface["digest"],
        watcher_id="watcher-1",
    )

    with pytest.raises(ValueError, match="first event must be root_turn"):
        admit_execution_event(
            policy,
            empty,
            _event("call:first", "model_call", depth=1, call_digest=DIGEST_A),
        )

    _, rooted = admit_execution_event(
        policy, empty, _event("root:1", "root_turn", depth=0)
    )
    with pytest.raises(ValueError, match="exactly one root_turn"):
        admit_execution_event(
            policy, rooted, _event("root:2", "root_turn", depth=0)
        )

    forged = deepcopy(rooted)
    forged["events"].append(
        {**_event("root:2", "root_turn", depth=0), "sequence": 1}
    )
    errors = validate_execution_event_ledger(
        policy, forged, call_record_digests=[]
    )
    assert any("exactly one first root_turn" in error for error in errors)


def test_execution_event_ledger_requires_unique_event_ids() -> None:
    registry = load_registry()
    policy = compile_execution_budget_policy("narrow", registry)
    surface = surface_profile_binding("claude_saved_workflow_v1", registry)
    ledger = new_execution_event_ledger(
        root_execution_id="root-exec-unique",
        policy_digest=execution_policy_digest(policy),
        surface_profile_digest=surface["digest"],
        watcher_id="watcher-1",
    )
    _, ledger = admit_execution_event(
        policy, ledger, _event("root:1", "root_turn", depth=0)
    )
    duplicate = _event(
        "root:1", "model_call", depth=1, call_digest=DIGEST_A
    )

    with pytest.raises(ValueError, match="event_id must be unique"):
        admit_execution_event(policy, ledger, duplicate)

    forged = deepcopy(ledger)
    forged["events"].append({**duplicate, "sequence": 1})
    errors = validate_execution_event_ledger(
        policy, forged, call_record_digests=[DIGEST_A]
    )
    assert any("event_id is duplicated" in error for error in errors)


def test_execution_event_ledger_enforces_root_and_child_depth_invariants() -> None:
    registry = load_registry()
    policy = compile_execution_budget_policy("narrow", registry)
    surface = surface_profile_binding("claude_saved_workflow_v1", registry)
    empty = new_execution_event_ledger(
        root_execution_id="root-exec-depth",
        policy_digest=execution_policy_digest(policy),
        surface_profile_digest=surface["digest"],
        watcher_id="watcher-1",
    )
    malformed_root = _event("root:bad", "root_turn", depth=1)
    malformed_root["parent_event_id"] = "another-root"

    with pytest.raises(ValueError, match="root_turn.*depth 0.*no parent"):
        admit_execution_event(policy, empty, malformed_root)

    _, rooted = admit_execution_event(
        policy, empty, _event("root:1", "root_turn", depth=0)
    )
    malformed_child = _event(
        "call:bad-depth", "model_call", depth=0, call_digest=DIGEST_A
    )
    with pytest.raises(ValueError, match="model_call.*depth"):
        admit_execution_event(policy, rooted, malformed_child)

    forged = deepcopy(rooted)
    forged["events"].append({**malformed_child, "sequence": 1})
    errors = validate_execution_event_ledger(
        policy, forged, call_record_digests=[DIGEST_A]
    )
    assert any("model_call depth" in error for error in errors)


def test_execution_event_ledger_binds_call_digests_only_to_sampling_events() -> None:
    registry = load_registry()
    policy = compile_execution_budget_policy("narrow", registry)
    surface = surface_profile_binding("claude_saved_workflow_v1", registry)
    empty = new_execution_event_ledger(
        root_execution_id="root-exec-call-digest",
        policy_digest=execution_policy_digest(policy),
        surface_profile_digest=surface["digest"],
        watcher_id="watcher-1",
    )
    root_with_call = _event(
        "root:bad-call", "root_turn", depth=0, call_digest=DIGEST_A
    )
    with pytest.raises(ValueError, match="non-sampling.*call_record_digest"):
        admit_execution_event(policy, empty, root_with_call)

    _, rooted = admit_execution_event(
        policy, empty, _event("root:1", "root_turn", depth=0)
    )
    call_without_digest = _event(
        "call:no-digest", "model_call", depth=1, call_digest=None
    )
    with pytest.raises(ValueError, match="sampling.*call_record_digest"):
        admit_execution_event(policy, rooted, call_without_digest)

    forged = deepcopy(rooted)
    forged["events"][0]["call_record_digest"] = DIGEST_A
    errors = validate_execution_event_ledger(
        policy, forged, call_record_digests=[]
    )
    assert any("non-sampling" in error for error in errors)


def test_execution_event_ledger_requires_retry_to_follow_a_sampling_call() -> None:
    registry = load_registry()
    policy = compile_execution_budget_policy("narrow", registry)
    surface = surface_profile_binding("claude_saved_workflow_v1", registry)
    ledger = new_execution_event_ledger(
        root_execution_id="root-exec-retry-parent",
        policy_digest=execution_policy_digest(policy),
        surface_profile_digest=surface["digest"],
        watcher_id="watcher-1",
    )
    _, ledger = admit_execution_event(
        policy, ledger, _event("root:1", "root_turn", depth=0)
    )
    _, ledger = admit_execution_event(
        policy,
        ledger,
        _event("call:1", "model_call", depth=1, call_digest=DIGEST_A),
    )
    retry = _event("retry:1", "retry", depth=1, call_digest=DIGEST_B)

    with pytest.raises(ValueError, match="retry parent.*sampling"):
        admit_execution_event(policy, ledger, retry)

    forged = deepcopy(ledger)
    forged["events"].append({**retry, "sequence": 2})
    errors = validate_execution_event_ledger(
        policy, forged, call_record_digests=[DIGEST_A, DIGEST_B]
    )
    assert any("retry parent" in error for error in errors)


def test_execution_event_ledger_retry_preserves_parent_node_and_depth() -> None:
    registry = load_registry()
    policy = compile_execution_budget_policy("narrow", registry)
    surface = surface_profile_binding("claude_saved_workflow_v1", registry)
    ledger = new_execution_event_ledger(
        root_execution_id="root-exec-retry-lineage",
        policy_digest=execution_policy_digest(policy),
        surface_profile_digest=surface["digest"],
        watcher_id="watcher-1",
    )
    _, ledger = admit_execution_event(
        policy, ledger, _event("root:1", "root_turn", depth=0)
    )
    _, ledger = admit_execution_event(
        policy,
        ledger,
        _event("call:1", "model_call", depth=1, call_digest=DIGEST_A),
    )
    wrong_node = _event(
        "retry:wrong-node", "retry", depth=1, call_digest=DIGEST_B
    )
    wrong_node["parent_event_id"] = "call:1"
    wrong_node["node_id"] = "node-b"
    with pytest.raises(ValueError, match="retry.*same node"):
        admit_execution_event(policy, ledger, wrong_node)

    wrong_depth = _event(
        "retry:wrong-depth", "retry", depth=0, call_digest=DIGEST_B
    )
    wrong_depth["parent_event_id"] = "call:1"
    with pytest.raises(ValueError, match="retry.*same depth"):
        admit_execution_event(policy, ledger, wrong_depth)

    valid_retry = _event(
        "retry:valid", "retry", depth=1, call_digest=DIGEST_B
    )
    valid_retry["parent_event_id"] = "call:1"
    allowed, ledger = admit_execution_event(policy, ledger, valid_retry)
    assert allowed
    assert validate_execution_event_ledger(
        policy, ledger, call_record_digests=[DIGEST_A, DIGEST_B]
    ) == []


def test_execution_event_ledger_spawn_descends_exactly_one_level() -> None:
    registry = load_registry()
    policy = compile_execution_budget_policy("narrow", registry)
    surface = surface_profile_binding("claude_saved_workflow_v1", registry)
    ledger = new_execution_event_ledger(
        root_execution_id="root-exec-spawn-lineage",
        policy_digest=execution_policy_digest(policy),
        surface_profile_digest=surface["digest"],
        watcher_id="watcher-1",
    )
    _, ledger = admit_execution_event(
        policy, ledger, _event("root:1", "root_turn", depth=0)
    )
    same_depth = _event("spawn:same-depth", "spawn", depth=0)
    with pytest.raises(ValueError, match="spawn.*one level"):
        admit_execution_event(policy, ledger, same_depth)

    valid_spawn = _event("spawn:valid", "spawn", depth=1)
    allowed, spawned = admit_execution_event(policy, ledger, valid_spawn)
    assert allowed

    call = _event("call:spawned", "model_call", depth=1, call_digest=DIGEST_A)
    call["parent_event_id"] = "spawn:valid"
    allowed, spawned = admit_execution_event(policy, spawned, call)
    assert allowed
    assert validate_execution_event_ledger(
        policy, spawned, call_record_digests=[DIGEST_A]
    ) == []


def test_execution_event_ledger_spawned_call_uses_spawned_node_identity() -> None:
    registry = load_registry()
    policy = compile_execution_budget_policy("narrow", registry)
    surface = surface_profile_binding("claude_saved_workflow_v1", registry)
    ledger = new_execution_event_ledger(
        root_execution_id="root-exec-spawn-node",
        policy_digest=execution_policy_digest(policy),
        surface_profile_digest=surface["digest"],
        watcher_id="watcher-1",
    )
    _, ledger = admit_execution_event(
        policy, ledger, _event("root:1", "root_turn", depth=0)
    )
    _, ledger = admit_execution_event(
        policy, ledger, _event("spawn:1", "spawn", depth=1)
    )
    wrong_node = _event(
        "call:wrong-node", "model_call", depth=1, call_digest=DIGEST_A
    )
    wrong_node["parent_event_id"] = "spawn:1"
    wrong_node["node_id"] = "node-b"

    with pytest.raises(ValueError, match="model_call.*spawned node"):
        admit_execution_event(policy, ledger, wrong_node)


def test_execution_event_ledger_follow_up_stays_on_prior_call_lineage() -> None:
    registry = load_registry()
    policy = compile_execution_budget_policy("standard", registry)
    surface = surface_profile_binding("claude_saved_workflow_v1", registry)
    ledger = new_execution_event_ledger(
        root_execution_id="root-exec-follow-up",
        policy_digest=execution_policy_digest(policy),
        surface_profile_digest=surface["digest"],
        watcher_id="watcher-1",
    )
    _, ledger = admit_execution_event(
        policy, ledger, _event("root:1", "root_turn", depth=0)
    )
    _, ledger = admit_execution_event(
        policy,
        ledger,
        _event("call:1", "model_call", depth=1, call_digest=DIGEST_A),
    )
    detached = _event(
        "follow-up:detached", "follow_up", depth=1, call_digest=DIGEST_B
    )
    with pytest.raises(ValueError, match="follow_up parent.*sampling"):
        admit_execution_event(policy, ledger, detached)

    attached = deepcopy(detached)
    attached["event_id"] = "follow-up:attached"
    attached["parent_event_id"] = "call:1"
    allowed, ledger = admit_execution_event(policy, ledger, attached)
    assert allowed
    assert validate_execution_event_ledger(
        policy, ledger, call_record_digests=[DIGEST_A, DIGEST_B]
    ) == []


def test_execution_event_ledger_caps_distinct_delegated_nodes_excluding_root() -> None:
    registry = load_registry()
    policy = deepcopy(compile_execution_budget_policy("narrow", registry))
    policy["max_unique_nodes"] = 1
    surface = surface_profile_binding("claude_saved_workflow_v1", registry)
    ledger = new_execution_event_ledger(
        root_execution_id="root-exec-node-cap",
        policy_digest=execution_policy_digest(policy),
        surface_profile_digest=surface["digest"],
        watcher_id="watcher-1",
    )
    _, ledger = admit_execution_event(
        policy, ledger, _event("root:1", "root_turn", depth=0)
    )
    allowed, ledger = admit_execution_event(
        policy,
        ledger,
        _event("call:node-a", "model_call", depth=1, call_digest=DIGEST_A),
    )
    assert allowed  # The PM root is not a delegated node.

    sibling = _event(
        "call:node-b", "model_call", depth=1, call_digest=DIGEST_B
    )
    sibling["node_id"] = "node-b"
    allowed, ledger = admit_execution_event(policy, ledger, sibling)
    assert not allowed
    assert ledger["terminal_reason"] == "BUDGET_EXHAUSTED"
    assert validate_execution_event_ledger(
        policy, ledger, call_record_digests=[DIGEST_A]
    ) == []

    forged = deepcopy(ledger)
    forged["events"][-1]["outcome"] = "completed"
    forged["events"][-1]["call_record_digest"] = DIGEST_B
    forged["terminal_reason"] = None
    errors = validate_execution_event_ledger(
        policy, forged, call_record_digests=[DIGEST_A, DIGEST_B]
    )
    assert any("distinct delegated-node cap" in error for error in errors)


def test_execution_event_ledger_enforces_retry_budget_before_retry_call() -> None:
    registry = load_registry()
    policy = deepcopy(compile_execution_budget_policy("narrow", registry))
    policy["retry_budget"] = 0
    surface = surface_profile_binding("claude_saved_workflow_v1", registry)
    ledger = new_execution_event_ledger(
        root_execution_id="root-exec-retry-cap",
        policy_digest=execution_policy_digest(policy),
        surface_profile_digest=surface["digest"],
        watcher_id="watcher-1",
    )
    _, ledger = admit_execution_event(
        policy, ledger, _event("root:1", "root_turn", depth=0)
    )
    _, ledger = admit_execution_event(
        policy,
        ledger,
        _event("call:1", "model_call", depth=1, call_digest=DIGEST_A),
    )
    retry = _event("retry:1", "retry", depth=1, call_digest=DIGEST_B)
    retry["parent_event_id"] = "call:1"

    allowed, ledger = admit_execution_event(policy, ledger, retry)
    assert not allowed
    assert ledger["terminal_reason"] == "BUDGET_EXHAUSTED"
    assert validate_execution_event_ledger(
        policy, ledger, call_record_digests=[DIGEST_A]
    ) == []


def test_execution_event_ledger_validates_terminal_cap_rejections() -> None:
    registry = load_registry()
    surface = surface_profile_binding("claude_saved_workflow_v1", registry)

    follow_policy = deepcopy(
        compile_execution_budget_policy("standard", registry)
    )
    follow_policy["max_followup_attempts"] = 0
    follow_ledger = new_execution_event_ledger(
        root_execution_id="root-exec-follow-cap",
        policy_digest=execution_policy_digest(follow_policy),
        surface_profile_digest=surface["digest"],
        watcher_id="watcher-1",
    )
    _, follow_ledger = admit_execution_event(
        follow_policy, follow_ledger, _event("root:1", "root_turn", depth=0)
    )
    _, follow_ledger = admit_execution_event(
        follow_policy,
        follow_ledger,
        _event("call:1", "model_call", depth=1, call_digest=DIGEST_A),
    )
    follow = _event(
        "follow-up:cap", "follow_up", depth=1, call_digest=DIGEST_B
    )
    follow["parent_event_id"] = "call:1"
    allowed, follow_ledger = admit_execution_event(
        follow_policy, follow_ledger, follow
    )
    assert not allowed
    assert validate_execution_event_ledger(
        follow_policy, follow_ledger, call_record_digests=[DIGEST_A]
    ) == []

    wait_policy = deepcopy(compile_execution_budget_policy("narrow", registry))
    wait_policy["max_wait_cycles"] = 0
    wait_ledger = new_execution_event_ledger(
        root_execution_id="root-exec-wait-cap",
        policy_digest=execution_policy_digest(wait_policy),
        surface_profile_digest=surface["digest"],
        watcher_id="watcher-1",
    )
    _, wait_ledger = admit_execution_event(
        wait_policy, wait_ledger, _event("root:1", "root_turn", depth=0)
    )
    _, wait_ledger = admit_execution_event(
        wait_policy, wait_ledger, _event("spawn:1", "spawn", depth=1)
    )
    wait = _event("wait:cap", "wait", depth=1)
    wait["parent_event_id"] = "spawn:1"
    allowed, wait_ledger = admit_execution_event(
        wait_policy, wait_ledger, wait
    )
    assert not allowed
    assert validate_execution_event_ledger(
        wait_policy, wait_ledger, call_record_digests=[]
    ) == []

    wake_policy = deepcopy(
        compile_execution_budget_policy("standard", registry)
    )
    wake_policy["max_no_delta_wakeups"] = 0
    wake_ledger = new_execution_event_ledger(
        root_execution_id="root-exec-wakeup-cap",
        policy_digest=execution_policy_digest(wake_policy),
        surface_profile_digest=surface["digest"],
        watcher_id="watcher-1",
    )
    _, wake_ledger = admit_execution_event(
        wake_policy, wake_ledger, _event("root:1", "root_turn", depth=0)
    )
    _, wake_ledger = admit_execution_event(
        wake_policy, wake_ledger, _event("spawn:1", "spawn", depth=1)
    )
    wait = _event("wait:1", "wait", depth=1)
    wait["parent_event_id"] = "spawn:1"
    _, wake_ledger = admit_execution_event(wake_policy, wake_ledger, wait)
    wakeup = _event("wakeup:cap", "no_delta_wakeup", depth=1)
    wakeup["parent_event_id"] = "wait:1"
    wakeup["outcome"] = "no_delta"
    allowed, wake_ledger = admit_execution_event(
        wake_policy, wake_ledger, wakeup
    )
    assert not allowed
    assert validate_execution_event_ledger(
        wake_policy, wake_ledger, call_record_digests=[]
    ) == []


def test_execution_event_ledger_enforces_wait_wakeup_terminate_lifecycle() -> None:
    registry = load_registry()
    policy = compile_execution_budget_policy("standard", registry)
    surface = surface_profile_binding("claude_saved_workflow_v1", registry)
    ledger = new_execution_event_ledger(
        root_execution_id="root-exec-lifecycle",
        policy_digest=execution_policy_digest(policy),
        surface_profile_digest=surface["digest"],
        watcher_id="watcher-1",
    )
    _, ledger = admit_execution_event(
        policy, ledger, _event("root:1", "root_turn", depth=0)
    )
    _, ledger = admit_execution_event(
        policy, ledger, _event("spawn:1", "spawn", depth=1)
    )

    detached_wait = _event("wait:detached", "wait", depth=1)
    with pytest.raises(ValueError, match="wait parent"):
        admit_execution_event(policy, ledger, detached_wait)

    wait = _event("wait:1", "wait", depth=1)
    wait["parent_event_id"] = "spawn:1"
    _, ledger = admit_execution_event(policy, ledger, wait)

    detached_wakeup = _event(
        "wakeup:detached", "no_delta_wakeup", depth=1
    )
    detached_wakeup["outcome"] = "no_delta"
    with pytest.raises(ValueError, match="no_delta_wakeup parent.*wait"):
        admit_execution_event(policy, ledger, detached_wakeup)

    wakeup = deepcopy(detached_wakeup)
    wakeup["event_id"] = "wakeup:1"
    wakeup["parent_event_id"] = "wait:1"
    wakeup["outcome"] = "no_delta"
    _, ledger = admit_execution_event(policy, ledger, wakeup)

    terminate = _event("terminate:1", "terminate", depth=1)
    terminate["parent_event_id"] = "wakeup:1"
    terminate["outcome"] = "terminated"
    _, ledger = admit_execution_event(policy, ledger, terminate)

    after_terminate = _event(
        "call:after-terminate", "model_call", depth=1, call_digest=DIGEST_A
    )
    with pytest.raises(ValueError, match="node lineage is already terminated"):
        admit_execution_event(policy, ledger, after_terminate)

    assert validate_execution_event_ledger(
        policy, ledger, call_record_digests=[]
    ) == []


def test_execution_event_ledger_enforces_kind_specific_and_terminal_state() -> None:
    registry = load_registry()
    policy = compile_execution_budget_policy("narrow", registry)
    surface = surface_profile_binding("claude_saved_workflow_v1", registry)
    empty = new_execution_event_ledger(
        root_execution_id="root-exec-state",
        policy_digest=execution_policy_digest(policy),
        surface_profile_digest=surface["digest"],
        watcher_id="watcher-1",
    )
    pending_root = _event("root:pending", "root_turn", depth=0)
    pending_root["outcome"] = "pending"
    with pytest.raises(ValueError, match="outcome is invalid for root_turn"):
        admit_execution_event(policy, empty, pending_root)

    _, rooted = admit_execution_event(
        policy, empty, _event("root:1", "root_turn", depth=0)
    )
    terminal_without_rejection = deepcopy(rooted)
    terminal_without_rejection["terminal_reason"] = "BUDGET_EXHAUSTED"
    errors = validate_execution_event_ledger(
        policy, terminal_without_rejection, call_record_digests=[]
    )
    assert any("terminal reason requires one final rejected event" in error for error in errors)

    rejected_without_terminal = deepcopy(rooted)
    rejected_without_terminal["events"].append(
        {
            **_event("spawn:rejected", "spawn", depth=1),
            "sequence": 1,
            "outcome": "rejected",
        }
    )
    errors = validate_execution_event_ledger(
        policy, rejected_without_terminal, call_record_digests=[]
    )
    assert any("final rejected event requires a terminal reason" in error for error in errors)

    call_cap_policy = deepcopy(policy)
    call_cap_policy["max_call_attempts"] = 0
    call_cap_policy["max_total_model_turns"] = 1
    capped = new_execution_event_ledger(
        root_execution_id="root-exec-terminal-reason",
        policy_digest=execution_policy_digest(call_cap_policy),
        surface_profile_digest=surface["digest"],
        watcher_id="watcher-1",
    )
    _, capped = admit_execution_event(
        call_cap_policy, capped, _event("root:1", "root_turn", depth=0)
    )
    _, capped = admit_execution_event(
        call_cap_policy,
        capped,
        _event("call:rejected", "model_call", depth=1, call_digest=DIGEST_A),
    )
    capped["terminal_reason"] = "WAIT_BUDGET_EXHAUSTED"
    errors = validate_execution_event_ledger(
        call_cap_policy, capped, call_record_digests=[]
    )
    assert any("terminal reason does not match policy denial" in error for error in errors)


def test_execution_event_ledger_sampling_outcomes_keep_call_record_lineage() -> None:
    registry = load_registry()
    policy = compile_execution_budget_policy("narrow", registry)
    surface = surface_profile_binding("claude_saved_workflow_v1", registry)
    ledger = new_execution_event_ledger(
        root_execution_id="root-exec-sampling-outcomes",
        policy_digest=execution_policy_digest(policy),
        surface_profile_digest=surface["digest"],
        watcher_id="watcher-1",
    )
    _, ledger = admit_execution_event(
        policy, ledger, _event("root:1", "root_turn", depth=0)
    )
    null_call = _event(
        "call:null", "model_call", depth=1, call_digest=DIGEST_A
    )
    null_call["outcome"] = "null"
    _, ledger = admit_execution_event(policy, ledger, null_call)

    timeout_retry = _event(
        "retry:timeout", "retry", depth=1, call_digest=DIGEST_B
    )
    timeout_retry["parent_event_id"] = "call:null"
    timeout_retry["outcome"] = "timeout"
    _, ledger = admit_execution_event(policy, ledger, timeout_retry)

    assert validate_execution_event_ledger(
        policy, ledger, call_record_digests=[DIGEST_A, DIGEST_B]
    ) == []


def test_execution_event_ledger_checks_only_surface_attested_event_coverage() -> None:
    registry = load_registry()
    policy = compile_execution_budget_policy("standard", registry)
    surface = surface_profile_binding("claude_saved_workflow_v1", registry)
    ledger = new_execution_event_ledger(
        root_execution_id="root-exec-surface-coverage",
        policy_digest=execution_policy_digest(policy),
        surface_profile_digest=surface["digest"],
        watcher_id="watcher-1",
    )
    _, ledger = admit_execution_event(
        policy,
        ledger,
        _event("root:1", "root_turn", depth=0),
        surface_profile=surface["profile"],
    )
    _, ledger = admit_execution_event(
        policy,
        ledger,
        _event("call:1", "model_call", depth=1, call_digest=DIGEST_A),
        surface_profile=surface["profile"],
    )
    assert validate_execution_event_ledger(
        policy,
        ledger,
        call_record_digests=[DIGEST_A],
        surface_profile=surface["profile"],
    ) == []  # Unsupported wait events are not invented as required coverage.

    unsupported_wait = _event("wait:unsupported", "wait", depth=1)
    unsupported_wait["parent_event_id"] = "call:1"
    with pytest.raises(ValueError, match="surface profile.*does not attest wait"):
        admit_execution_event(
            policy,
            ledger,
            unsupported_wait,
            surface_profile=surface["profile"],
        )

    _, structural_only = admit_execution_event(
        policy, ledger, unsupported_wait
    )
    errors = validate_execution_event_ledger(
        policy,
        structural_only,
        call_record_digests=[DIGEST_A],
        surface_profile=surface["profile"],
    )
    assert any("does not attest wait" in error for error in errors)
