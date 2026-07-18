from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_routing import (  # noqa: E402
    P0B_ADAPTER_ID,
    P0B_CLAIM_KEYS_BY_PHASE,
    p0b_effect_selection_digest,
    route_task,
)
import agent_governance_p0b_effects as p0b  # noqa: E402
import agent_governance_p0b_phase1_lineage as phase1_lineage  # noqa: E402
import agent_governance_p0b_sources as source_bindings  # noqa: E402
import p0b_alr_current_head_rollforward_v1 as runtime_core  # noqa: E402
from agent_governance_p0b_sources import (  # noqa: E402
    component_claim_digests,
    component_claim_paths,
    validate_component_claims,
)


DIGEST = "sha256:" + "a" * 64
HEAD = "b" * 40


def _claims(phase: str) -> dict[str, str]:
    claims = {key: DIGEST for key in P0B_CLAIM_KEYS_BY_PHASE[phase]}
    claims["p0b_effect_adapter_selection"] = p0b_effect_selection_digest(phase)
    return claims


def _facts(phase: str) -> dict:
    return {
        "task_shape": "deploy",
        "surfaces": ["authority", "service", "runtime_effect"],
        "risk": "critical",
        "uncertainty": "low",
        "runtime_claim": True,
        "end_to_end_claim": False,
        "side_effect_class": "deploy",
        "task_prompt": f"govern P0-B {phase}",
        "claim_inputs": _claims(phase),
    }


@pytest.mark.parametrize("phase", ["stage", "cutover"])
def test_p0b_phase_is_an_exact_independently_admitted_effect(phase: str) -> None:
    route = route_task(_facts(phase))
    effect_nodes = [
        node for node in route["nodes"] if node["kind"] == "effect_adapter"
    ]

    assert effect_nodes == [
        {
            "id": P0B_ADAPTER_ID,
            "kind": "effect_adapter",
            "requires": [f"pm_p0b_{phase}_approval"],
            "mandatory": True,
            "reason": f"purpose-built P0-B {phase} effect seam",
            "effect_phase": phase,
            "intent_schema_version": "p0b_alr_rollforward_intent_v1",
            "result_schema_version": "p0b_alr_rollforward_effect_result_v1",
        }
    ]
    assert route["task_facts"]["claim_inputs"] == _claims(phase)
    assert any(node["id"] == f"pm_p0b_{phase}_approval" for node in route["nodes"])
    assert not any(node["id"] == "deploy_adapter_v1" for node in route["nodes"])


@pytest.mark.parametrize("phase", ["stage", "cutover"])
def test_p0b_selection_and_claim_inventory_fail_closed(phase: str) -> None:
    missing = _facts(phase)
    missing["claim_inputs"].pop(next(
        key for key in P0B_CLAIM_KEYS_BY_PHASE[phase]
        if key != "p0b_effect_adapter_selection"
    ))
    with pytest.raises(ValueError, match="exact claim_inputs"):
        route_task(missing)

    extra = _facts(phase)
    extra["claim_inputs"]["unadmitted_extra"] = DIGEST
    with pytest.raises(ValueError, match="exact claim_inputs"):
        route_task(extra)

    relabelled = _facts(phase)
    relabelled["claim_inputs"]["p0b_effect_adapter_selection"] = (
        p0b_effect_selection_digest("cutover" if phase == "stage" else "stage")
    )
    with pytest.raises(ValueError, match="selection digest"):
        route_task(relabelled)


def test_generic_deploy_does_not_accidentally_select_p0b() -> None:
    route = route_task({
        "task_shape": "deploy",
        "surfaces": ["service"],
        "risk": "high",
        "uncertainty": "low",
        "runtime_claim": True,
        "end_to_end_claim": False,
        "side_effect_class": "deploy",
        "task_prompt": "generic deploy",
        "claim_inputs": {},
    })
    assert [
        node["id"] for node in route["nodes"] if node["kind"] == "effect_adapter"
    ] == ["deploy_adapter_v1"]


def test_registry_binds_purpose_built_adapter_components_and_schemas() -> None:
    registry = json.loads(
        (ROOT / ".codex/agent_registry_v1.json").read_text(encoding="utf-8")
    )
    adapter = registry["effect_adapters"][P0B_ADAPTER_ID]
    assert adapter["status"] == "declared_two_phase_apply_gated"
    assert adapter["runtime_bindings_schema_path"] == (
        ".codex/schemas/phase_runtime_bindings_v1.schema.json"
    )
    assert adapter["phase1_closure_schema_path"] == (
        ".codex/schemas/p0b_alr_phase1_governance_closure_v1.schema.json"
    )
    assert adapter["phase1_lineage_schema_path"] == (
        ".codex/schemas/p0b_alr_phase1_sealed_lineage_bundle_v1.schema.json"
    )
    assert "helper_scripts/maintenance_scripts/agent_governance_p0b_effects.py" in (
        adapter["implementation_paths"]
    )
    assert "helper_scripts/maintenance_scripts/agent_governance_p0b_observer.py" in (
        adapter["implementation_paths"]
    )
    assert (
        "helper_scripts/maintenance_scripts/agent_governance_p0b_runtime_bindings.py"
        in adapter["implementation_paths"]
    )
    assert "helper_scripts/maintenance_scripts/agent_governance_p0b_sources.py" in (
        adapter["implementation_paths"]
    )
    assert (
        "helper_scripts/maintenance_scripts/agent_governance_p0b_phase1_lineage.py"
        in adapter["implementation_paths"]
    )
    assert "helper_scripts/maintenance_scripts/p0b_generation_pin_apply_current_head_v1.py" in (
        adapter["component_paths"]
    )
    assert all("_211f26_" not in path for path in adapter["component_paths"])


def test_p0b_schemas_are_exact_and_phase_specific() -> None:
    intent = json.loads(
        (ROOT / ".codex/schemas/p0b_alr_rollforward_intent_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    result = json.loads(
        (
            ROOT
            / ".codex/schemas/p0b_alr_rollforward_effect_result_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    runtime_bindings = json.loads(
        (ROOT / ".codex/schemas/phase_runtime_bindings_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert intent["additionalProperties"] is False
    assert intent["$defs"]["claimBindings"]["additionalProperties"] is False
    assert result["additionalProperties"] is False
    assert result["$defs"]["claimBindings"]["additionalProperties"] is False
    assert result["properties"]["phase_result"]["oneOf"][:2] == [
        {"$ref": "#/$defs/stageResult"},
        {"$ref": "#/$defs/cutoverResult"},
    ]
    assert result["$defs"]["stageResult"]["additionalProperties"] is False
    assert result["$defs"]["cutoverResult"]["additionalProperties"] is False
    assert runtime_bindings["additionalProperties"] is False
    assert runtime_bindings["$defs"]["sourceAttestation"]["additionalProperties"] is False
    assert runtime_bindings["$defs"]["protectedRuntimeBaseline"][
        "additionalProperties"
    ] is False
    assert runtime_bindings["$defs"]["protectedSnapshot"]["properties"][
        "engine"
    ]["minItems"] == 0
    assert runtime_bindings["$defs"]["protectedSnapshot"]["properties"][
        "engine"
    ]["maxItems"] == 1
    assert runtime_bindings["$defs"]["stagePaths"]["additionalProperties"] is False
    assert runtime_bindings["$defs"]["cutoverPaths"]["additionalProperties"] is False
    assert "minProperties" not in runtime_bindings["$defs"]["hashInventory"]
    assert p0b.schema_subset_errors(
        {}, runtime_bindings["$defs"]["hashInventory"], runtime_bindings
    ) == []
    assert "ControlGroup" in runtime_bindings["$defs"]["activeIdentity"]["required"]
    assert runtime_bindings["$defs"]["activeIdentity"]["properties"][
        "ControlGroup"
    ] == {"type": "string", "pattern": "^/"}
    protected_identity = {
        "MainPID": "123",
        "ProcessStartTicks": "456",
        "InvocationID": "a" * 32,
        "ExecMainStartTimestampMonotonic": "789",
        "NRestarts": "0",
        "ALRSourceHead": HEAD,
        "ControlGroup": "/user.slice/openclaw-alr-shadow.service",
    }
    assert p0b.schema_subset_errors(
        protected_identity,
        runtime_bindings["$defs"]["activeIdentity"],
        runtime_bindings,
    ) == []
    assert "phase1_receipt_path" not in intent["$defs"]["governanceBindings"][
        "properties"
    ]
    assert "authorization_digest" not in json.dumps(runtime_bindings)
    observer = result["$defs"]["observerResult"]
    assert observer["properties"]["status"] == {
        "const": "OBSERVER_V2_EXACT_POSTCHECK_PASS"
    }
    assert "receipt_digest" not in observer["properties"]
    runtime_cycles = result["$defs"]["observerRuntimeAndCycles"]
    assert runtime_cycles["properties"]["cycle_count"] == {"const": 2}
    assert runtime_cycles["properties"]["cycles_distinct"] == {"const": True}
    assert result["$defs"]["twoRawDigests"]["minItems"] == 2
    assert result["$defs"]["twoRawDigests"]["maxItems"] == 2
    assert observer["additionalProperties"] is False
    assert result["$defs"]["observerLineage"]["additionalProperties"] is False
    assert result["$defs"]["runtimeAuthorization"]["additionalProperties"] is False
    assert result["$defs"]["authorizationGovernanceBindings"][
        "additionalProperties"
    ] is False
    assert "phase1_receipt_path" not in result["$defs"][
        "authorizationGovernanceBindings"
    ]["properties"]
    assert result["$defs"]["provisionalCutover"]["properties"][
        "cutover_authorization"
    ]["allOf"][0] == {"$ref": "#/$defs/runtimeAuthorization"}
    private_bundle = result["$defs"]["privateBundleResult"]
    assert private_bundle["properties"]["no_network"] == {"const": True}
    assert private_bundle["properties"]["no_package_install"] == {"const": True}
    assert private_bundle["properties"]["credentials_read"] == {"const": False}

    phase1_closure = json.loads(
        (
            ROOT
            / ".codex/schemas/p0b_alr_phase1_governance_closure_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    phase1_bundle = json.loads(
        (
            ROOT
            / ".codex/schemas/p0b_alr_phase1_sealed_lineage_bundle_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert phase1_closure["additionalProperties"] is False
    assert phase1_closure["properties"]["status"] == {
        "const": "PHASE1_GOVERNANCE_CLOSURE_PASS"
    }
    assert phase1_closure["properties"]["ops_postcheck"]["$ref"] == (
        "closure_packet_v1.schema.json#/$defs/opsP0bPostcheck"
    )
    assert phase1_bundle["additionalProperties"] is False
    assert phase1_bundle["properties"]["staged_board"] == {
        "$ref": "#/$defs/artifactBinding"
    }
    assert "phase1_sealed_lineage_bundle" not in phase1_closure["properties"]


def _canonical_digest(value) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _bound_json(tmp_path: Path, name: str, value: dict) -> dict[str, str]:
    path = tmp_path / name
    raw = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()
    path.write_bytes(raw)
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}


def _phase1_lineage_fixture(tmp_path: Path, mutation: str | None = None):
    stage_id = "p0b-stage-lineage-0001"
    task_digest = "sha256:" + "1" * 64
    route_digest = "sha256:" + "2" * 64
    context_digest = "sha256:" + "3" * 64
    stage_intent_digest = "sha256:" + "4" * 64
    authorized_runtime = {
        "expected_old_runtime_source_head": "d" * 40,
        "expected_old_pin_digest": "sha256:" + "5" * 64,
        "expected_source_tree_digest": "sha256:" + "6" * 64,
        "expected_pin_consumer_inventory_digest": "sha256:" + "7" * 64,
        "expected_runtime_identity_digest": "sha256:" + "8" * 64,
    }
    stage_authorization = {
        "schema_version": "p0b_alr_runtime_authorization_v1",
        "phase": "stage",
        "intent_id": (
            "p0b-stage-forged-0001" if mutation == "authorization" else stage_id
        ),
        "intent_digest": stage_intent_digest,
        "task_contract_digest": task_digest,
        "context_artifact_digest": context_digest,
        "expected_source_head": HEAD,
        "approved_at": "2026-07-18T10:01:00Z",
        "governance_bindings": {"compiled_route_digest": route_digest},
        **authorized_runtime,
    }
    stage_authorization["authorization_digest"] = _canonical_digest(
        {
            key: value for key, value in stage_authorization.items()
            if key != "authorization_digest"
        }
    )
    stage_authorization_binding = _bound_json(
        tmp_path, "stage-authorization.json", stage_authorization
    )
    stage_bindings = {
        "schema_version": "phase_runtime_bindings_v1",
        "phase": "stage",
        "intent_id": stage_id,
    }
    stage_bindings["artifact_digest"] = _canonical_digest(stage_bindings)
    stage_bindings_binding = _bound_json(
        tmp_path, "stage-runtime-bindings.json", stage_bindings
    )
    manifest = "9" * 64
    private_receipt = {
        "schema_version": "p0b_psycopg_private_bundle_stage_v1",
        "status": "APPLIED_POSTCHECK_PASS",
        "reason_codes": [],
        "source_root": "/home/ncyu/Projects/TradeBot/srv",
        "destination": p0b.PRIVATE_BUNDLE_DESTINATION,
        "source_manifest_sha256": manifest,
        "destination_manifest_sha256": manifest,
        "mutation_performed": True,
        "boundaries": phase1_lineage.PRIVATE_BOUNDARIES,
        "source_total_bytes": 4096,
    }
    private_binding = _bound_json(tmp_path, "private-receipt.json", private_receipt)
    board = {
        "schema_version": "cost_gate_demo_learning_lane_blocked_outcome_review_v6",
        "candidate_board_generation_state": "COMPLETE",
        "ledger_scan_status": "COMPLETE",
        "latest_alias_used": False,
        "generated_at_utc": "2026-07-18T10:04:00Z",
        "order_authority": "NOT_GRANTED",
        "promotion_evidence": False,
        "learning_candidate_board": {
            "schema_version": "cost_gate_learning_candidate_board_v2",
            "candidate_universe_complete": True,
            "candidate_rows": [{
                "candidate_id": "natural-candidate-1",
                "expected_value_bps": 12.5,
                "order_authority": "NOT_GRANTED",
            }],
        },
    }
    if mutation == "board_authority":
        board["learning_candidate_board"]["candidate_rows"][0][
            "order_authority"
        ] = "GRANTED"
    board_binding = _bound_json(tmp_path, "staged-board.json", board)
    dummy = {"path": "/tmp/p0b-lineage-dummy.json", "sha256": "a" * 64}
    lock = {"dev": 1, "ino": 2, "uid": 1000, "gid": 1000, "mode": 384, "nlink": 1}
    sealed = {
        "started_at_utc": "2026-07-18T10:02:00Z",
        "completed_at_utc": "2026-07-18T10:05:00Z",
        "token": "b" * 32,
        "completion": dummy,
        "producer_board": dummy,
        "cron_staged_board": dummy,
        "staged_board": board_binding,
        "staging_publisher_receipt": dummy,
        "private_deps_receipt": private_binding,
        "private_deps_destination": p0b.PRIVATE_BUNDLE_DESTINATION,
        "private_deps_manifest_sha256": manifest,
        "publisher_result": {"status": "PUBLISHED"},
        "execution_tree": {"source": "sealed"},
        "live_inventory_sha256": "sha256:" + "b" * 64,
        "completion_inventory_sha256": "sha256:" + "c" * 64,
        "producer_inventory_sha256": "sha256:" + "d" * 64,
        "ledger_pre_inventory_sha256": "sha256:" + "e" * 64,
        "ledger_post_inventory_sha256": "sha256:" + "f" * 64,
        "lane_effective_config_sha256": "sha256:" + "0" * 64,
        "alr_availability_monitor": {"sample_count": 1},
        "normal_lane_returncode": 0,
    }
    receipt = {
        "schema_version": "p0b_alr_current_head_rollforward_v1",
        "phase": 1,
        "status": "PHASE1_STAGING_APPLIED_PASS",
        "approval_id": stage_id,
        "authorization_digest": stage_authorization["authorization_digest"],
        "stage_authorization": stage_authorization_binding,
        "stage_authorization_digest": stage_authorization["authorization_digest"],
        "stage_runtime_bindings": stage_bindings_binding,
        "stage_runtime_bindings_artifact_digest": stage_bindings["artifact_digest"],
        "stage_authorized_runtime": authorized_runtime,
        "target_head": HEAD,
        "old_head": "d" * 40,
        "protected_sha256": "sha256:" + "1" * 64,
        "old_alr_retained_running": True,
        "global_pin_retained_old": True,
        "live_publication_performed": False,
        "sealed_lineage": sealed,
        "completed_at_utc": "2026-07-18T10:05:00Z",
        "intent": {"path": "/tmp/phase1.intent.json", "sha256": "2" * 64, "size": 10},
        "locks_held_through_effect_receipt": {
            "cost": lock, "alpha": lock, "unit": lock, "publisher": True,
        },
        "boundaries": phase1_lineage.LANE_BOUNDARIES,
    }
    if mutation == "arbitrary_receipt":
        receipt = {"nonempty": True}
    receipt_binding = _bound_json(tmp_path, "phase1-receipt.json", receipt)
    receipt_raw_digest = "sha256:" + receipt_binding["sha256"]
    phase_result_digest = _canonical_digest(receipt)
    operation = {
        "schema_version": "ops_p0b_alr_postcheck_v1",
        "adapter_id": P0B_ADAPTER_ID,
        "phase": "stage",
        "intent_id": stage_id,
        "intent_digest": stage_intent_digest,
        "task_contract_digest": task_digest,
        "context_artifact_digest": context_digest,
        "compiled_route_digest": route_digest,
        "source_head": HEAD,
        "target_host": "trade-core",
        "target_user_unit": "openclaw-alr-shadow.service",
        "effect_receipt_digest": receipt_raw_digest,
        "phase_result_digest": phase_result_digest,
        "observer_receipt_digest": None,
        "observed_at": "2026-07-18T10:06:00Z",
        "expires_at": "2026-07-18T10:15:00Z",
        "verified": True,
    }
    operation["operation_digest"] = _canonical_digest(operation)
    closure = {
        "schema_version": "p0b_alr_phase1_governance_closure_v1",
        "status": (
            "FORGED_PASS" if mutation == "closure_status"
            else "PHASE1_GOVERNANCE_CLOSURE_PASS"
        ),
        "phase": "stage",
        "intent_id": stage_id,
        "intent_digest": stage_intent_digest,
        "task_contract_digest": task_digest,
        "compiled_route_digest": route_digest,
        "context_artifact_digest": context_digest,
        "stage_authorization_digest": stage_authorization["authorization_digest"],
        "stage_runtime_bindings_artifact_digest": stage_bindings["artifact_digest"],
        "phase1_effect_receipt_digest": receipt_raw_digest,
        "phase_result_digest": phase_result_digest,
        "ops_postcheck": operation,
        "ops_postcheck_digest": operation["operation_digest"],
        "closed_at_utc": "2026-07-18T10:07:00Z",
    }
    closure["closure_digest"] = _canonical_digest(closure)
    closure_binding = _bound_json(tmp_path, "phase1-closure.json", closure)
    bundle = {
        "schema_version": "p0b_alr_phase1_sealed_lineage_bundle_v1",
        "target_head": "e" * 40 if mutation == "bundle_target" else HEAD,
        "intent_id": stage_id,
        "intent_digest": stage_intent_digest,
        "task_contract_digest": task_digest,
        "compiled_route_digest": route_digest,
        "context_artifact_digest": context_digest,
        "stage_authorization": stage_authorization_binding,
        "stage_authorization_digest": stage_authorization["authorization_digest"],
        "stage_runtime_bindings": stage_bindings_binding,
        "stage_runtime_bindings_artifact_digest": stage_bindings["artifact_digest"],
        "phase1_effect_receipt": receipt_binding,
        "phase1_effect_receipt_digest": receipt_raw_digest,
        "phase1_closure": closure_binding,
        "phase1_closure_digest": "sha256:" + closure_binding["sha256"],
        "private_deps_receipt": private_binding,
        "private_deps_destination": p0b.PRIVATE_BUNDLE_DESTINATION,
        "private_deps_manifest_sha256": manifest,
        "staged_board": board_binding,
    }
    bundle["bundle_digest"] = _canonical_digest(bundle)
    bundle_binding = _bound_json(tmp_path, "phase1-lineage-bundle.json", bundle)
    lineage = {
        "phase1_receipt": receipt_binding,
        "phase1_closure": closure_binding,
        "sealed_lineage_bundle": bundle_binding,
        "private_deps_receipt": private_binding,
        "staged_board": board_binding,
    }
    claims = {
        "p0b_phase1_intent": stage_intent_digest,
        "p0b_phase1_task_contract": task_digest,
        "p0b_phase1_route": route_digest,
        "p0b_phase1_context_artifact": context_digest,
        "p0b_phase1_receipt": receipt_raw_digest,
        "p0b_phase1_closure": "sha256:" + closure_binding["sha256"],
        "p0b_sealed_lineage_bundle": "sha256:" + bundle_binding["sha256"],
        "p0b_private_bundle_receipt": "sha256:" + private_binding["sha256"],
        "p0b_staged_candidate_board": "sha256:" + board_binding["sha256"],
    }
    intent = {
        "phase": "cutover",
        "expected_source_head": HEAD,
        "claim_bindings": claims,
        "phase1_effect_receipt_digest": receipt_raw_digest,
        "phase1_closure_digest": "sha256:" + closure_binding["sha256"],
        "sealed_lineage_bundle_digest": "sha256:" + bundle_binding["sha256"],
    }
    return intent, {"lineage": lineage}


def test_cutover_phase1_lineage_accepts_exact_pass_with_natural_candidate(
    tmp_path: Path,
) -> None:
    intent, runtime = _phase1_lineage_fixture(tmp_path)
    assert phase1_lineage.validate_cutover_phase1_lineage(
        intent,
        runtime,
        authorization_validator=lambda *_args, **_kwargs: [],
        runtime_bindings_validator=lambda *_args, **_kwargs: [],
    ) == []


@pytest.mark.parametrize(
    "mutation",
    ["arbitrary_receipt", "closure_status", "bundle_target", "authorization", "board_authority"],
)
def test_cutover_phase1_lineage_rejects_rehashed_illegal_pass_graph(
    tmp_path: Path, mutation: str,
) -> None:
    intent, runtime = _phase1_lineage_fixture(tmp_path, mutation)
    errors = phase1_lineage.validate_cutover_phase1_lineage(
        intent,
        runtime,
        authorization_validator=lambda *_args, **_kwargs: [],
        runtime_bindings_validator=lambda *_args, **_kwargs: [],
    )
    assert errors, mutation


@pytest.mark.parametrize("phase", ["stage", "cutover"])
def test_component_claims_are_exact_repository_byte_hashes(
    tmp_path: Path, phase: str
) -> None:
    for index, relative in enumerate(component_claim_paths(phase).values()):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"component-{index}".encode())
    claims = component_claim_digests(tmp_path, phase)
    assert validate_component_claims(claims, root=tmp_path, phase=phase) == []
    first = next(iter(claims))
    claims[first] = DIGEST
    assert validate_component_claims(claims, root=tmp_path, phase=phase) == [
        f"P0-B {first} does not match exact repository bytes"
    ]


def _write_component_fixtures(root: Path, phase: str) -> list[Path]:
    paths = []
    for index, relative in enumerate(component_claim_paths(phase).values()):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"secure-component-{index}".encode())
        paths.append(path)
    return paths


def test_component_hashing_rejects_symlink(tmp_path: Path) -> None:
    paths = _write_component_fixtures(tmp_path, "stage")
    paths[0].unlink()
    paths[0].symlink_to(paths[1])
    errors = validate_component_claims({}, root=tmp_path, phase="stage")
    assert len(errors) == 1
    assert "component source inventory unavailable" in errors[0]


def test_component_hashing_rejects_identity_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_component_fixtures(tmp_path, "stage")
    original = source_bindings._identity
    calls = 0

    def drifting_identity(observed):
        nonlocal calls
        calls += 1
        identity = original(observed)
        return (
            (identity[0], identity[1] + 1, *identity[2:])
            if calls == 3 else identity
        )

    monkeypatch.setattr(source_bindings, "_identity", drifting_identity)
    errors = validate_component_claims({}, root=tmp_path, phase="stage")
    assert len(errors) == 1
    assert "component identity changed while hashing" in errors[0]


def _admission_fixture(monkeypatch: pytest.MonkeyPatch, phase: str = "stage"):
    facts = _facts(phase)
    facts["baseline"] = {
        "source_head": HEAD,
        "dirty_diff_hash": DIGEST,
        "untracked_relevant_hash": DIGEST,
    }
    runtime_bindings = {
        "schema_version": "phase_runtime_bindings_v1",
        "phase": phase,
        "intent_id": f"p0b-{phase}-0001",
        "target_head": HEAD,
        "phase_paths": (
            {} if phase == "stage"
            else {"phase1_receipt_path": "/tmp/p0b-stage-receipt.json"}
        ),
    }
    runtime_bindings["artifact_digest"] = _canonical_digest(runtime_bindings)
    facts["claim_inputs"]["p0b_phase_runtime_bindings"] = runtime_bindings[
        "artifact_digest"
    ]
    route = route_task(facts)
    task_digest = "sha256:" + "c" * 64
    context_artifacts = {
        key: {
            "schema_version": "context_artifact_v1",
            "artifact_digest": "sha256:" + character * 64,
            "task_contract_digest": task_digest,
            "_test_role": role,
        }
        for (key, role), character in zip(
            p0b.CONTEXT_ROLES.items(), ("1", "2", "3", "4")
        )
    }

    def context_validator(artifact, **_kwargs):
        return {"errors": [], "plan": {"role": artifact["_test_role"]}}

    monkeypatch.setattr(p0b, "validate_context_artifact", context_validator)
    monkeypatch.setattr(p0b, "validate_phase_runtime_bindings", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(p0b, "validate_cutover_phase1_lineage", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(p0b, "validate_component_claims", lambda *_args, **_kwargs: [])
    governance_artifacts = {
        "pa_role_fragment": {
            "schema_version": "role_fragment_v1", "role": "PA",
            "work_status": "DONE", "gate_verdict": "PASS",
        },
        "pa_command_capture": {
            "schema_version": "command_capture_v2", "role_id": "PA",
            "result": "PASS", "exit_code": 0,
        },
        "e3_role_fragment": {
            "schema_version": "role_fragment_v1", "role": "E3",
            "work_status": "DONE", "gate_verdict": "PASS",
        },
        "e3_command_capture": {
            "schema_version": "command_capture_v2", "role_id": "E3",
            "result": "PASS", "exit_code": 0,
        },
        "ops_preflight_role_fragment": {
            "schema_version": "role_fragment_v1", "role": "OPS",
            "work_status": "DONE", "gate_verdict": "PASS",
        },
        "ops_preflight_command_capture": {
            "schema_version": "command_capture_v2", "role_id": "OPS",
            "result": "PASS", "exit_code": 0,
        },
        "ops_preflight_attestation": {
            "schema_version": "p0b_alr_ops_preflight_attestation_v1",
            "role": "OPS",
            "observed_at": "2026-07-18T10:00:00Z",
            "expires_at": "2026-07-18T10:15:00Z",
        },
        "pm_approval_artifact": {
            "schema_version": "p0b_alr_pm_approval_v1", "role": "PM",
            "approved_at": "2026-07-18T10:01:00Z",
        },
        "phase_runtime_bindings": runtime_bindings,
    }
    bindings = {
        "compiled_route_schema": "hybrid_execution_dag_v1",
        "compiled_route_digest": _canonical_digest(route),
        "route_dag_digest": route["dag_digest"],
        "context_artifact_schema": "context_artifact_v1",
        "pm_context_artifact_digest": context_artifacts["pm"]["artifact_digest"],
        "pa_context_artifact_digest": context_artifacts["pa"]["artifact_digest"],
        "e3_context_artifact_digest": context_artifacts["e3"]["artifact_digest"],
        "ops_preflight_context_artifact_digest": context_artifacts["ops_preflight"]["artifact_digest"],
        "ops_preflight_observed_at": "2026-07-18T10:00:00Z",
        "ops_preflight_expires_at": "2026-07-18T10:15:00Z",
        "authorized_argv_digest": _canonical_digest([
            "--phase1-apply" if phase == "stage" else "--phase2-apply"
        ]),
        "phase_runtime_bindings_artifact_digest": runtime_bindings["artifact_digest"],
        "phase_runtime_bindings_path": f"/tmp/p0b-{phase}-runtime-bindings.json",
        "authorization_path": f"/tmp/p0b-{phase}-authorization.json",
        "protected_baseline_digest": facts["claim_inputs"]["p0b_protected_runtime_baseline"],
    }
    for field, (key, _role, _schema) in p0b.GOVERNANCE_ARTIFACT_BINDINGS.items():
        if field != "phase_runtime_bindings_artifact_digest":
            bindings[field] = _canonical_digest(governance_artifacts[key])
    intent = {
        "schema_version": "p0b_alr_rollforward_intent_v1",
        "adapter_id": P0B_ADAPTER_ID,
        "phase": phase,
        "intent_id": f"p0b-{phase}-0001",
        "intent_digest": DIGEST,
        "task_contract_digest": task_digest,
        "context_artifact_digest": context_artifacts["pm"]["artifact_digest"],
        "governance_bindings": bindings,
        "claim_bindings": facts["claim_inputs"],
        "expected_source_head": HEAD,
        "expected_origin_main_head": HEAD,
        "expected_old_runtime_source_head": "d" * 40,
        "expected_old_pin_digest": "sha256:" + "e" * 64,
        "expected_source_tree_digest": "sha256:" + "f" * 64,
        "expected_pin_consumer_inventory_digest": "sha256:" + "9" * 64,
        "expected_runtime_identity_digest": "sha256:" + "8" * 64,
        "target_host": "trade-core",
        "target_environment": "trade_core_alr",
        "target_user_unit": "openclaw-alr-shadow.service",
        "require_clean_tree": True,
        "require_fresh_origin_main": True,
        "phase1_effect_receipt_digest": None if phase == "stage" else "sha256:" + "7" * 64,
        "phase1_closure_digest": None if phase == "stage" else "sha256:" + "6" * 64,
        "sealed_lineage_bundle_digest": None if phase == "stage" else "sha256:" + "5" * 64,
        "private_bundle_destination": p0b.PRIVATE_BUNDLE_DESTINATION,
        "observer_requirement": "NOT_APPLICABLE" if phase == "stage" else "REQUIRED_PASS",
        "approved_by": "operator",
        "approved_at": "2026-07-18T10:01:00Z",
        "expires_at": (
            "2026-07-18T10:16:00Z" if phase == "cutover"
            else "2026-07-18T12:00:00Z"
        ),
        "typed_confirm": f"p0b-alr-rollforward:{phase}:trade-core:{HEAD}:p0b-{phase}-0001",
        "hard_stops": p0b.P0B_HARD_STOPS_BY_PHASE[phase],
    }
    intent["intent_digest"] = p0b.p0b_intent_digest(intent)
    argv = [
        "--phase1-apply" if phase == "stage" else "--phase2-apply",
        "--authorization-json", bindings["authorization_path"],
        "--runtime-bindings-json", bindings["phase_runtime_bindings_path"],
        "--runtime-bindings-sha256",
        bindings["phase_runtime_bindings_artifact_digest"].removeprefix("sha256:"),
    ]
    if phase == "cutover":
        argv.extend([
            "--phase1-receipt-json",
            runtime_bindings["phase_paths"]["phase1_receipt_path"],
            "--phase1-receipt-sha256",
            intent["phase1_effect_receipt_digest"].removeprefix("sha256:"),
        ])
    bindings["authorized_argv_digest"] = _canonical_digest(argv)
    intent["intent_digest"] = p0b.p0b_intent_digest(intent)
    return route, context_artifacts, governance_artifacts, intent


@pytest.mark.parametrize("phase", ["stage", "cutover"])
def test_p0b_intent_validates_route_materialized_context_and_exact_effect_argv(
    monkeypatch: pytest.MonkeyPatch, phase: str,
) -> None:
    route, contexts, artifacts, intent = _admission_fixture(monkeypatch, phase)
    argv = [
        "--phase1-apply" if phase == "stage" else "--phase2-apply",
        "--authorization-json",
        intent["governance_bindings"]["authorization_path"],
        "--runtime-bindings-json",
        intent["governance_bindings"]["phase_runtime_bindings_path"],
        "--runtime-bindings-sha256",
        intent["governance_bindings"]["phase_runtime_bindings_artifact_digest"].removeprefix("sha256:"),
    ]
    if phase == "cutover":
        argv.extend([
            "--phase1-receipt-json",
            artifacts["phase_runtime_bindings"]["phase_paths"]["phase1_receipt_path"],
            "--phase1-receipt-sha256",
            intent["phase1_effect_receipt_digest"].removeprefix("sha256:"),
        ])
    assert p0b.validate_p0b_intent(
        intent,
        route=route,
        context_artifacts=contexts,
        governance_artifacts=artifacts,
        authorized_argv=argv,
        expected_local_head=HEAD,
        fresh_origin_main_head=HEAD,
        now="2026-07-18T10:05:00Z",
    ) == []

    forged = deepcopy(intent)
    forged["governance_bindings"]["context_artifact_schema"] = "context_plan_v1"
    forged["intent_digest"] = p0b.p0b_intent_digest(forged)
    errors = p0b.validate_p0b_intent(
        forged,
        route=route,
        context_artifacts=contexts,
        governance_artifacts=artifacts,
        authorized_argv=argv,
        expected_local_head=HEAD,
        fresh_origin_main_head=HEAD,
        now="2026-07-18T10:05:00Z",
    )
    assert any("context_artifact_v1" in error for error in errors)


def test_runtime_authorization_is_exact_canonical_intent_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _route, _contexts, _artifacts, intent = _admission_fixture(monkeypatch)
    authorization = p0b.build_p0b_runtime_authorization(intent)
    assert authorization["schema_version"] == "p0b_alr_runtime_authorization_v1"
    assert authorization["authorization_digest"] == p0b.p0b_authorization_digest(
        authorization
    )
    assert p0b.validate_p0b_runtime_authorization(
        authorization, now="2026-07-18T10:05:00Z"
    ) == []

    generic = deepcopy(authorization)
    generic["governance_bindings"]["compiled_route_schema"] = "deployment_intent_v1"
    generic["authorization_digest"] = p0b.p0b_authorization_digest(generic)
    assert p0b.validate_p0b_runtime_authorization(
        generic, now="2026-07-18T10:05:00Z"
    )


def test_governance_valid_stage_authorization_is_accepted_by_runtime_core(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _route, _contexts, _artifacts, intent = _admission_fixture(monkeypatch)
    authorization = p0b.build_p0b_runtime_authorization(intent)

    runtime_core.validate_runtime_authorization(
        authorization,
        phase="stage",
        now=datetime(2026, 7, 18, 10, 5, tzinfo=timezone.utc),
    )


def test_cutover_authority_has_fifteen_minute_ttl_and_stage_names_allowed_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _route, _contexts, _artifacts, cutover = _admission_fixture(
        monkeypatch, phase="cutover"
    )
    cutover["expires_at"] = "2026-07-18T10:16:01Z"
    cutover["intent_digest"] = p0b.p0b_intent_digest(cutover)
    authorization = p0b.build_p0b_runtime_authorization(cutover)
    assert any(
        "cutover intent TTL" in error
        for error in p0b.validate_p0b_runtime_authorization(
            authorization, now="2026-07-18T10:05:00Z"
        )
    )
    assert (
        "only fresh public Git origin read, normal-lane readonly PG, and existing "
        "fixed-path credential load are allowed"
    ) in p0b.P0B_HARD_STOPS_BY_PHASE["stage"]
    assert all("no network" not in item for item in p0b.COMMON_HARD_STOPS)


def test_provisional_digest_is_non_recursive_and_embedded_auth_is_fully_validated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provisional = {"schema_version": "fixture", "provisional_digest": DIGEST}
    assert p0b.p0b_provisional_digest(provisional) == p0b.p0b_provisional_digest(
        {"schema_version": "fixture"}
    )
    called = []

    def authorization_validator(value, *, now):
        called.append((value, now))
        return ["sentinel authorization rejection"]

    monkeypatch.setattr(p0b, "validate_p0b_runtime_authorization", authorization_validator)
    errors = p0b._validate_provisional(
        {
            "cutover_authorization": {"phase": "cutover", "authorization_digest": DIGEST},
            "cutover_authorization_digest": DIGEST,
        },
        now="2026-07-18T10:05:00Z",
    )
    assert called
    assert "sentinel authorization rejection" in errors


def _ops_receipt(phase: str = "stage") -> tuple[dict, dict]:
    route = route_task(_facts(phase))
    receipt = {
        "adapter_id": P0B_ADAPTER_ID,
        "phase": phase,
        "intent_id": f"p0b-{phase}-0001",
        "intent_digest": "sha256:" + "1" * 64,
        "task_contract_digest": "sha256:" + "2" * 64,
        "context_artifact_digest": "sha256:" + "3" * 64,
        "source_head": HEAD,
        "target_host": "trade-core",
        "target_environment": "trade_core_alr",
        "target_user_unit": "openclaw-alr-shadow.service",
        "claim_bindings": _claims(phase),
        "started_at": "2026-07-18T10:05:00Z",
        "completed_at": "2026-07-18T10:06:00Z",
        "phase_result": {"schema_version": f"fixture-{phase}"},
        "receipt_digest": "sha256:" + "4" * 64,
    }
    return receipt, route


def _ops_evidence(node_id: str, receipt: dict, route: dict) -> dict:
    preflight = node_id == "ops_preflight"
    operation = {
        "schema_version": (
            "ops_p0b_alr_preflight_v1" if preflight
            else "ops_p0b_alr_postcheck_v1"
        ),
        "adapter_id": P0B_ADAPTER_ID,
        "phase": receipt["phase"],
        "intent_id": receipt["intent_id"],
        "intent_digest": receipt["intent_digest"],
        "task_contract_digest": receipt["task_contract_digest"],
        "context_artifact_digest": receipt["context_artifact_digest"],
        "compiled_route_digest": p0b._route_digest(route),
        "source_head": receipt["source_head"],
        "target_host": receipt["target_host"],
        "target_user_unit": receipt["target_user_unit"],
        "observed_at": (
            "2026-07-18T10:04:00Z" if preflight else "2026-07-18T10:06:01Z"
        ),
        "expires_at": "2026-07-18T10:14:00Z",
    }
    if preflight:
        operation.update({
            "runtime_bindings_digest": receipt["claim_bindings"][
                "p0b_phase_runtime_bindings"
            ],
            "protected_baseline_digest": receipt["claim_bindings"][
                "p0b_protected_runtime_baseline"
            ],
            "ready": True,
        })
    else:
        observer = receipt["phase_result"].get("observer")
        operation.update({
            "effect_receipt_digest": receipt["receipt_digest"],
            "phase_result_digest": p0b._digest(receipt["phase_result"]),
            "observer_receipt_digest": (
                p0b._digest(observer) if receipt["phase"] == "cutover" else None
            ),
            "verified": True,
        })
    operation["operation_digest"] = p0b.p0b_operation_digest(operation)
    return {
        "id": f"evidence-{node_id}",
        "kind": f"ops_{'preflight' if preflight else 'postcheck'}_v1",
        "source": f"p0b_{node_id}",
        "scope": "runtime",
        "host": receipt["target_host"],
        "environment": receipt["target_environment"],
        "digest": operation["operation_digest"],
        "observed_at": operation["observed_at"],
        "expiry": operation["expires_at"],
        "operation_receipt": operation,
    }


def test_ops_preflight_and_later_postcheck_are_exact_cross_bound() -> None:
    receipt, route = _ops_receipt()
    preflight = _ops_evidence("ops_preflight", receipt, route)
    postcheck = _ops_evidence("ops_postcheck", receipt, route)
    assert p0b._validate_p0b_ops_evidence(
        preflight, node_id="ops_preflight", receipt=receipt, route=route
    ) == []
    assert p0b._validate_p0b_ops_evidence(
        postcheck, node_id="ops_postcheck", receipt=receipt, route=route
    ) == []

    forged = deepcopy(postcheck)
    forged["operation_receipt"]["phase_result_digest"] = DIGEST
    forged["operation_receipt"]["operation_digest"] = p0b.p0b_operation_digest(
        forged["operation_receipt"]
    )
    forged["digest"] = forged["operation_receipt"]["operation_digest"]
    errors = p0b._validate_p0b_ops_evidence(
        forged, node_id="ops_postcheck", receipt=receipt, route=route
    )
    assert any("phase_result_digest" in error for error in errors)


def test_ops_postcheck_observer_digest_is_phase_specific() -> None:
    stage, route = _ops_receipt()
    stage_evidence = _ops_evidence("ops_postcheck", stage, route)
    stage_evidence["operation_receipt"]["observer_receipt_digest"] = DIGEST
    stage_evidence["operation_receipt"]["operation_digest"] = p0b.p0b_operation_digest(
        stage_evidence["operation_receipt"]
    )
    stage_evidence["digest"] = stage_evidence["operation_receipt"]["operation_digest"]
    assert any(
        "observer_receipt_digest" in error
        for error in p0b._validate_p0b_ops_evidence(
            stage_evidence, node_id="ops_postcheck", receipt=stage, route=route
        )
    )

    cutover, cutover_route = _ops_receipt("cutover")
    cutover["phase_result"]["observer"] = {
        "schema_version": "p0b_alr_current_head_two_cycle_observer_v2",
        "status": "OBSERVER_V2_EXACT_POSTCHECK_PASS",
    }
    cutover_evidence = _ops_evidence("ops_postcheck", cutover, cutover_route)
    assert p0b._validate_p0b_ops_evidence(
        cutover_evidence,
        node_id="ops_postcheck",
        receipt=cutover,
        route=cutover_route,
    ) == []


def test_closure_acceptance_requires_final_receipt_plus_later_ops_postcheck() -> None:
    receipt, route = _ops_receipt()
    receipt["intent_expires_at"] = "2026-07-18T12:00:00Z"
    preflight = _ops_evidence("ops_preflight", receipt, route)
    postcheck = _ops_evidence("ops_postcheck", receipt, route)
    evidence = {
        preflight["id"]: preflight,
        postcheck["id"]: postcheck,
    }
    fragments = {
        "ops_preflight": {"evidence_refs": [preflight["id"]]},
        "ops_postcheck": {"evidence_refs": [postcheck["id"]]},
    }
    packet = {
        "dispatch": {"context_artifact": {
            "task_contract_digest": receipt["task_contract_digest"],
            "artifact_digest": receipt["context_artifact_digest"],
        }},
        "authority_refs": [{
            "class": "claim_evidence",
            "source": f"p0b_alr_rollforward_intent_v1:{receipt['intent_id']}",
            "digest": receipt["intent_digest"],
            "expiry": receipt["intent_expires_at"],
        }],
        "acceptance": [{
            "status": "PASS",
            "evidence_refs": ["effect", postcheck["id"]],
        }],
        "side_effects": {"runtime_contact": True},
        "disposition": "CHANGED",
    }
    assert p0b.validate_p0b_effect_binding(
        packet, route, fragments, evidence, {"effect": receipt}
    ) == []

    packet["acceptance"][0]["evidence_refs"] = ["effect"]
    assert "P0-B passed acceptance does not bind final receipt plus OPS postcheck" in (
        p0b.validate_p0b_effect_binding(
            packet, route, fragments, evidence, {"effect": receipt}
        )
    )


def test_tracked_p0b_governance_never_pins_a_current_commit_constant() -> None:
    paths = [
        ROOT / "helper_scripts/maintenance_scripts/agent_governance_routing.py",
        ROOT / "helper_scripts/maintenance_scripts/agent_governance_p0b_effects.py",
        ROOT / "helper_scripts/maintenance_scripts/agent_governance_p0b_observer.py",
        ROOT / "helper_scripts/maintenance_scripts/agent_governance_p0b_runtime_bindings.py",
        ROOT / "helper_scripts/maintenance_scripts/agent_governance_p0b_sources.py",
        ROOT / ".codex/schemas/p0b_alr_rollforward_intent_v1.schema.json",
        ROOT / ".codex/schemas/p0b_alr_rollforward_effect_result_v1.schema.json",
        ROOT / ".codex/schemas/phase_runtime_bindings_v1.schema.json",
    ]
    for path in paths:
        assert "211f26" not in path.read_text(encoding="utf-8")
