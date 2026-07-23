"""S1.6B target-host effect adapter: registry, route, closure, and bypass-negatives.

Covers the S1 formal-closure Wave A effect seam: the registered
target_host_disposable_runtime_probe_adapter_v1 with its impl/component/intent/
result paths; route_task admitting side_effect_class=target_host_probe as the
exact ops_preflight -> pm_target_host_approval -> adapter -> ops_postcheck chain
(and generic deploy NOT selecting it); the dedicated target_host_effect_result_v1
consumed by the closure binding with intent cross-binding and runtime_contact PASS;
the STRICT attestation bypass-negative (§13 C4: a STRUCTURAL_ONLY / bare-capture
choice receipt is rejected at the effect lane while the central offline gate
accepts it structure-only); the frozen classifier-digest pin; and S1-signer
domain separation.
"""

from __future__ import annotations

import copy
import functools
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_target_host_probe as th  # noqa: E402
import agent_governance_target_host_effects as tfx  # noqa: E402
import agent_governance_effects as effects  # noqa: E402
import agent_governance_routing as routing  # noqa: E402
import agent_governance_aiml_trusted_host as host  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402


ADAPTER = "target_host_disposable_runtime_probe_adapter_v1"
OBS = "2026-07-23T12:00:00+00:00"
NOW = "2026-07-23T12:05:00+00:00"
HEAD = "0" * 40
FROZEN_CLASSIFIER = (
    "sha256:1cf8c021b066ceeb364e968add074d263cb28d63db421fdc40620e9904d0ddbc"
)


def _effect_result(*, include_capture_artifact: bool = True, pg_mode=None) -> dict:
    # applier 自跑形:independent_postcheck DEFERRED、verifier_capture_digest=None(PROVISIONAL)。
    # closure 端須先經 distinct 驗證者 attach_distinct_verifier_postcheck 升 BINDING(見 _closure_inputs)。
    choice = th.build_attested_reference_receipt(
        now=OBS, pg_mode=pg_mode or th.PG_MODE_REAL,
        include_capture_artifact=include_capture_artifact,
        independent_postcheck_attached=False,
    )
    return tfx.build_target_host_effect_result(
        choice_receipt=choice,
        intent_id="thintent-0001",
        intent_digest="sha256:" + "a" * 64,
        source_head=HEAD,
        approved_by="operator",
        approved_at="2026-07-23T12:01:00+00:00",
        started_at="2026-07-23T12:02:00+00:00",
        completed_at=NOW,
        intent_expires_at="2026-07-23T12:14:00+00:00",
        evidence_expires_at="2026-07-23T12:10:00+00:00",
    )


def _resign(result: dict) -> dict:
    result = copy.deepcopy(result)
    result.pop("receipt_digest", None)
    result["receipt_digest"] = tfx.target_host_effect_receipt_digest(result)
    return result


# --------------------------------------------------------------------------- #
# registry wiring
# --------------------------------------------------------------------------- #
def test_registry_binds_target_host_adapter_paths_and_schemas() -> None:
    registry = json.loads((ROOT / ".codex/agent_registry_v1.json").read_text(encoding="utf-8"))
    adapter = registry["effect_adapters"][ADAPTER]
    assert adapter["status"] == "declared_disposable_target_host_probe_gated"
    assert adapter["owner_session"] == "S1.6B"
    assert adapter["authority"] and adapter["invariant"]
    assert adapter["implementation_paths"] == [
        "helper_scripts/maintenance_scripts/agent_governance_target_host_choice.py",
        "helper_scripts/maintenance_scripts/agent_governance_target_host_effects.py",
    ]
    assert adapter["component_paths"] == [
        "helper_scripts/maintenance_scripts/agent_governance_target_host_probe.py"
    ]
    assert adapter["intent_schema_path"] == (
        "program_code/ml_training/schemas/aiml_gate_receipts/"
        "target_host_disposable_runtime_probe_intent_v1.schema.json"
    )
    # §13 C1:result schema 是專屬 target_host_effect_result_v1(非通用 effect_adapter_result_v1)。
    assert adapter["result_schema_path"] == (
        "program_code/ml_training/schemas/aiml_gate_receipts/"
        "target_host_effect_result_v1.schema.json"
    )
    for key in ("implementation_paths", "component_paths"):
        for path in adapter[key]:
            assert (ROOT / path).is_file(), path
    for key in ("intent_schema_path", "result_schema_path"):
        assert (ROOT / adapter[key]).is_file(), adapter[key]


# --------------------------------------------------------------------------- #
# routing
# --------------------------------------------------------------------------- #
def test_route_admits_target_host_probe_exact_chain() -> None:
    route = routing.route_task({
        "task_shape": "audit",
        "surfaces": ["runtime_effect", "service", "authority"],
        "risk": "high", "uncertainty": "low", "runtime_claim": True,
        "end_to_end_claim": False, "side_effect_class": "target_host_probe",
        "task_prompt": "S1.6B disposable target-host probe", "dirty_scope": [],
        "claim_inputs": {},
    })
    effect_nodes = [n for n in route["nodes"] if n["kind"] == "effect_adapter"]
    assert [n["id"] for n in effect_nodes] == [ADAPTER]
    adapter_node = effect_nodes[0]
    assert adapter_node["intent_schema_version"] == "target_host_disposable_runtime_probe_intent_v1"
    assert adapter_node["result_schema_version"] == "target_host_effect_result_v1"
    assert adapter_node["requires"] == ["pm_target_host_approval"]
    by_id = {n["id"]: n for n in route["nodes"]}
    assert by_id["pm_target_host_approval"]["role"] == "PM"
    assert by_id["pm_target_host_approval"]["requires"] == ["ops_preflight"]
    assert by_id["ops_postcheck"]["requires"] == [ADAPTER]


def test_target_host_probe_requires_runtime_surface_claim_and_risk() -> None:
    # §13 C3 FORWARD rule:少了 runtime_claim=true / 表面 / 高risk 皆 fail-closed。
    for bad in (
        {"runtime_claim": False},
        {"surfaces": ["authority"]},
        {"risk": "low", "uncertainty": "low"},
    ):
        facts = {
            "task_shape": "audit", "surfaces": ["runtime_effect", "service"],
            "risk": "high", "uncertainty": "low", "runtime_claim": True,
            "side_effect_class": "target_host_probe",
            "task_prompt": "probe", "dirty_scope": [], "claim_inputs": {},
        }
        facts.update(bad)
        with pytest.raises(ValueError):
            routing.route_task(facts)


def test_generic_deploy_does_not_select_target_host_adapter() -> None:
    route = routing.route_task({
        "task_shape": "deploy", "surfaces": ["deploy", "service", "runtime_effect"],
        "risk": "high", "uncertainty": "low", "runtime_claim": True,
        "end_to_end_claim": False, "side_effect_class": "deploy",
        "task_prompt": "generic deploy", "dirty_scope": [], "claim_inputs": {},
    })
    ids = [n["id"] for n in route["nodes"] if n["kind"] == "effect_adapter"]
    assert ids == ["deploy_adapter_v1"]
    assert ADAPTER not in ids


# --------------------------------------------------------------------------- #
# effect result + closure binding
# --------------------------------------------------------------------------- #
def test_effect_result_positive_and_wrapper_binding() -> None:
    result = _effect_result()
    assert result["effect_status"] == "TARGET_HOST_DISPOSABLE_PROBE_PASS"
    assert tfx.validate_target_host_effect_result(
        result, now=NOW, expected_source_head=HEAD, require_success=True
    ) == []
    evidence = tfx.build_target_host_effect_evidence(result)
    errors, receipt = tfx.validate_target_host_effect_evidence(
        evidence, expected_source_head=HEAD
    )
    assert errors == []
    assert receipt is result or receipt == result


CLEAN_RESIDUE = {"units_gone": True, "cgroup_gone": True, "netns_gone": True, "temp_gone": True}


@functools.lru_cache(maxsize=1)
def _governed_verifier_capture() -> dict:
    """A REAL distinct-verifier governed ``command_capture_v2`` that passes the FULL offline validator.

    以 OPS review context + 一條 read-only argv 對真 repo 產出的真 governed record(通過
    ``validate_governed_command_capture`` 的完整 RECORD_FIELDS/trust_tier/effect_enforcement/no-self-
    asserted-host-sandbox/execution-task/authorization/self-digest 驗)——非空殼 stub。cache 以免每測都跑
    git;真 trade-core 出口綁的是 OPS ``capture-command`` 對殘留掃描的等機制真 record。capturer 身分
    (native_agent=OPS / node_id=ops_preflight)與 applier(e3-ops / s16b_ops_capture_node)天然相異。
    """

    import agent_governance_command_capture_v2 as capmod
    from agent_governance_context import capture_repository_baseline
    from agent_governance_execution import compile_context, materialize_context_artifact

    vscope = ["helper_scripts/maintenance_scripts/runtime_environment_probe.py"]
    facts = {
        "task_shape": "review", "surfaces": ["operations"], "risk": "medium",
        "uncertainty": "low", "side_effect_class": "none",
        "objective": "capture one bounded target-host residue sweep receipt",
        "scope": vscope, "dirty_scope": [], "verification_scope": vscope,
        "acceptance_criteria": ["one exact read-only command receipt"],
        "hard_stops": ["no runtime mutation"], "baseline": capture_repository_baseline(),
        "direct_interfaces": ["runtime_environment_probe_v1"],
        "previous_failure": "no derived read-only path scope",
    }
    routed = routing.route_task(facts)
    artifact = materialize_context_artifact(compile_context("OPS", routed["task_facts"]))
    return capmod.capture_governed_command(
        native_agent="OPS", node_id="ops_preflight", context_artifact=artifact,
        argv=["git", "rev-parse", "--is-inside-work-tree"], root=ROOT,
    )


def _verifier_capture() -> dict:
    return copy.deepcopy(_governed_verifier_capture())


def _closure_inputs(
    result: dict,
    *,
    verifier_node: str = "s16b_independent_verifier",
    ops_verifier_node: str | None = None,
    capture: dict | None = None,
    ops_capture_digest_override: str | None = None,
    residue: dict | None = None,
    include_capture_ref: bool = True,
    acceptance_refs: list | None = None,
):
    """Build a full target-host closure over the DISTINCT-VERIFIER-UPGRADED effect result.

    先以 ``attach_distinct_verifier_postcheck`` 把 applier 自跑結果升 BINDING(綁 verifier 的相異 capture),
    再組出 ops_postcheck(綁 verifier capture digest / residue / source_head / host / observed_at)、第三份
    verifier command_capture_v2 evidence,與同時綁三者的 acceptance。各覆寫參數供負向測試注入缺陷。
    """

    import agent_governance_target_host_apply as apply_mod

    cap = capture if capture is not None else _verifier_capture()
    upgraded = apply_mod.attach_distinct_verifier_postcheck(
        result, verifier_node_id=verifier_node,
        verifier_capture_digest=cap["record_digest"],
        residue_observation=CLEAN_RESIDUE, now=NOW,
    )
    evidence = tfx.build_target_host_effect_evidence(upgraded)
    receipt_id = evidence["id"]
    ops_post = {
        "id": "ops_post_1", "scope": "runtime", "source": "ops_postcheck", "status": "PASS",
        "verifier_node": ops_verifier_node or verifier_node,
        "verifier_capture_digest": ops_capture_digest_override or cap["record_digest"],
        "residue_observation": CLEAN_RESIDUE if residue is None else residue,
        "source_head": upgraded["source_head"], "host": upgraded["target_host"],
        "observed_at": NOW,
        "evidence_refs": (["verifier_capture_1"] if include_capture_ref else []),
    }
    vcap_evidence = {
        "id": "verifier_capture_1", "scope": "runtime", "kind": "command_capture_v2",
        "source": cap.get("native_agent"), "digest": cap["record_digest"], "capture": cap,
    }
    route = {"nodes": [{"id": ADAPTER, "kind": "effect_adapter", "mandatory": True}]}
    fragments = {"ops_postcheck": {"evidence_refs": ["ops_post_1"]}}
    evidence_by_id = {
        receipt_id: evidence, "ops_post_1": ops_post, "verifier_capture_1": vcap_evidence,
    }
    if acceptance_refs is None:
        acceptance_refs = [receipt_id, "ops_post_1", "verifier_capture_1"]
    packet = {
        "authority_refs": [{
            "class": "claim_evidence",
            "source": f"target_host_disposable_runtime_probe_intent_v1:{upgraded['intent_id']}",
            "digest": upgraded["intent_digest"], "expiry": upgraded["intent_expires_at"],
            "observed_at": "2026-07-23T12:01:30+00:00",
        }],
        "acceptance": [{"status": "PASS", "evidence_refs": acceptance_refs}],
        "side_effects": {"runtime_contact": True},
        "disposition": "CHANGED",
    }
    return packet, route, fragments, evidence_by_id, {receipt_id: upgraded}


def test_closure_consumes_dedicated_result_with_intent_binding() -> None:
    result = _effect_result()
    packet, route, fragments, evidence_by_id, valid = _closure_inputs(result)
    assert tfx.validate_target_host_effect_binding(
        packet, route, fragments, evidence_by_id, valid
    ) == []


def test_closure_rejects_missing_intent_authority() -> None:
    result = _effect_result()
    packet, route, fragments, evidence_by_id, valid = _closure_inputs(result)
    packet["authority_refs"] = []
    errors = tfx.validate_target_host_effect_binding(
        packet, route, fragments, evidence_by_id, valid
    )
    assert any("lacks exact intent authority" in e for e in errors)


def test_closure_rejects_applier_equals_verifier() -> None:
    # ops_postcheck 宣稱的 verifier_node == applier → closure 拒(相異 role/node 是硬性)。
    result = _effect_result()
    packet, route, fragments, evidence_by_id, valid = _closure_inputs(
        result, ops_verifier_node=result["applier_node_id"]
    )
    errors = tfx.validate_target_host_effect_binding(
        packet, route, fragments, evidence_by_id, valid
    )
    assert any("verifier must differ from the applier" in e for e in errors)


def test_closure_rejects_runtime_contact_false() -> None:
    result = _effect_result()
    packet, route, fragments, evidence_by_id, valid = _closure_inputs(result)
    packet["side_effects"]["runtime_contact"] = False
    errors = tfx.validate_target_host_effect_binding(
        packet, route, fragments, evidence_by_id, valid
    )
    assert any("runtime_contact=true" in e for e in errors)


# --------------------------------------------------------------------------- #
# P1(Codex): ops_postcheck evidence must be bound to the verifier's own capture
# --------------------------------------------------------------------------- #
def test_closure_rejects_empty_postcheck_evidence_refs() -> None:
    # 空 evidence_refs(不引用任何 verifier command_capture_v2)→ closure 拒。這正是 Codex 指出的
    # 「空 evidence_refs 也能過閘」漏洞:現在必須綁一份 verifier capture。
    result = _effect_result()
    packet, route, fragments, evidence_by_id, valid = _closure_inputs(
        result, include_capture_ref=False, acceptance_refs=None,
    )
    # acceptance 仍列 verifier_capture_1,但 ops_post 不再引用它;binding 應因缺 capture ref 而拒。
    errors = tfx.validate_target_host_effect_binding(
        packet, route, fragments, evidence_by_id, valid
    )
    assert any("exactly one verifier command_capture_v2" in e for e in errors)


def test_closure_rejects_fake_verifier_string_without_capture() -> None:
    # ops_postcheck 只有 verifier_node 字串、無真 capture evidence(evidence_refs 指向不存在的 id)→ 拒。
    result = _effect_result()
    packet, route, fragments, evidence_by_id, valid = _closure_inputs(result)
    evidence_by_id["ops_post_1"]["evidence_refs"] = ["nonexistent_capture"]
    errors = tfx.validate_target_host_effect_binding(
        packet, route, fragments, evidence_by_id, valid
    )
    assert any("exactly one verifier command_capture_v2" in e for e in errors)


def test_closure_rejects_non_governed_stub_verifier_capture() -> None:
    # E2 exploit:一個內容空殼(非完整 RECORD_FIELDS 的 governed capture)於 offline 閘被
    # validate_governed_command_capture 拒——不能只憑 schema_version + 自洽 record_digest 過關。
    import agent_governance_command_capture_v2 as capmod

    stub = {"schema_version": "command_capture_v2", "node_id": "x", "native_agent": "y", "role_id": "z"}
    stub["record_digest"] = capmod._self_digest(stub)
    packet, route, fragments, evidence_by_id, valid = _closure_inputs(_effect_result(), capture=stub)
    errors = tfx.validate_target_host_effect_binding(
        packet, route, fragments, evidence_by_id, valid
    )
    assert any("verifier command_capture_v2 invalid" in e for e in errors)


def test_closure_rejects_verifier_capture_self_asserting_host_sandbox() -> None:
    # E2 精確 exploit:governed capture 不得自證 host sandbox;自報 host_sandbox_attestation_ref 者被拒。
    import agent_governance_command_capture_v2 as capmod

    cap = copy.deepcopy(_governed_verifier_capture())
    cap["host_sandbox_attestation_ref"] = "sha256:" + "a" * 64
    cap["record_digest"] = capmod._self_digest(cap)  # 重簽以隔離出 host-sandbox 檢查(非 self-digest)
    packet, route, fragments, evidence_by_id, valid = _closure_inputs(_effect_result(), capture=cap)
    errors = tfx.validate_target_host_effect_binding(
        packet, route, fragments, evidence_by_id, valid
    )
    assert any("host sandbox" in e for e in errors)


def test_closure_rejects_capture_digest_mismatch() -> None:
    # ops_postcheck 攜帶的 verifier_capture_digest 與 effect receipt 結構化欄位不符 → 拒。
    result = _effect_result()
    packet, route, fragments, evidence_by_id, valid = _closure_inputs(
        result, ops_capture_digest_override="sha256:" + "d" * 64,
    )
    errors = tfx.validate_target_host_effect_binding(
        packet, route, fragments, evidence_by_id, valid
    )
    assert any("verifier_capture_digest must equal the effect receipt" in e for e in errors)


def test_closure_rejects_tampered_verifier_capture_record() -> None:
    # verifier capture record 被竄改(native_agent 改後未重簽)→ governed 閘拒(self-digest / execution-task 不符)。
    result = _effect_result()
    packet, route, fragments, evidence_by_id, valid = _closure_inputs(result)
    evidence_by_id["verifier_capture_1"]["capture"]["native_agent"] = "tampered-agent"
    errors = tfx.validate_target_host_effect_binding(
        packet, route, fragments, evidence_by_id, valid
    )
    assert any("verifier command_capture_v2 invalid" in e for e in errors)


def test_closure_rejects_missing_residue_observation() -> None:
    # ops_postcheck 缺 residue_observation → 拒(無法證明殘留已清)。
    result = _effect_result()
    packet, route, fragments, evidence_by_id, valid = _closure_inputs(result)
    evidence_by_id["ops_post_1"].pop("residue_observation")
    errors = tfx.validate_target_host_effect_binding(
        packet, route, fragments, evidence_by_id, valid
    )
    assert any("clean residue_observation" in e for e in errors)


def test_closure_rejects_nonzero_residue() -> None:
    # 殘留非零(某 teardown flag False)→ 拒。
    result = _effect_result()
    packet, route, fragments, evidence_by_id, valid = _closure_inputs(
        result, residue={"units_gone": True, "cgroup_gone": True, "netns_gone": True, "temp_gone": False},
    )
    errors = tfx.validate_target_host_effect_binding(
        packet, route, fragments, evidence_by_id, valid
    )
    assert any("clean residue_observation" in e for e in errors)


def test_closure_rejects_acceptance_missing_verifier_capture() -> None:
    # acceptance 只綁 effect receipt + ops_postcheck,未綁第三份 verifier capture → 拒。
    result = _effect_result()
    packet, route, fragments, evidence_by_id, valid = _closure_inputs(result)
    receipt_id = next(iter(valid))
    packet["acceptance"] = [{"status": "PASS", "evidence_refs": [receipt_id, "ops_post_1"]}]
    errors = tfx.validate_target_host_effect_binding(
        packet, route, fragments, evidence_by_id, valid
    )
    assert any("must bind the effect receipt + independent ops_postcheck + verifier capture" in e for e in errors)


def test_closure_rejects_applier_self_run_result_without_verifier_capture_digest() -> None:
    # 直接把 applier 自跑結果(vcd=None)塞進 closure valid_receipts → 缺 verifier_capture_digest,拒。
    result = _effect_result()
    packet, route, fragments, evidence_by_id, valid = _closure_inputs(result)
    receipt_id = next(iter(valid))
    valid[receipt_id] = result  # 換回未升 BINDING 的 applier 自跑結果
    errors = tfx.validate_target_host_effect_binding(
        packet, route, fragments, evidence_by_id, valid
    )
    assert any("lacks a bound verifier_capture_digest" in e for e in errors)


def _upgraded_result() -> dict:
    _, _, _, _, valid = _closure_inputs(_effect_result())
    return valid[next(iter(valid))]


# result-validator twin of the closure vcd cross-bind — the "can't set a vcd without a
# real distinct-verifier attach" anti-forgery invariant (E4 gap).
def test_result_validator_rejects_passed_postcheck_without_vcd() -> None:
    result = _resign({**_upgraded_result(), "verifier_capture_digest": None})
    errors = tfx.validate_target_host_effect_result(
        result, now=NOW, expected_source_head=HEAD, require_success=True
    )
    assert any("must carry a sha256 verifier_capture_digest" in e for e in errors)


def test_result_validator_rejects_vcd_not_matching_seam_note() -> None:
    result = _resign({**_upgraded_result(), "verifier_capture_digest": "sha256:" + "7" * 64})
    errors = tfx.validate_target_host_effect_result(
        result, now=NOW, expected_source_head=HEAD, require_success=True
    )
    assert any("must equal the distinct-verifier" in e for e in errors)


def test_result_validator_rejects_deferred_postcheck_with_vcd() -> None:
    # applier 自跑(independent_postcheck DEFERRED)卻攜 vcd → 拒(不能無真 attach 就自封 BINDING)。
    result = _resign({**_effect_result(), "verifier_capture_digest": "sha256:" + "7" * 64})
    errors = tfx.validate_target_host_effect_result(
        result, now=NOW, expected_source_head=HEAD, require_success=True
    )
    assert any("must be null when the independent_postcheck" in e for e in errors)


# ops_postcheck non-residue binding fields (E4 gap: branch (c) + (b) partial).
def test_closure_rejects_postcheck_wrong_source_head() -> None:
    packet, route, fragments, evidence_by_id, valid = _closure_inputs(_effect_result())
    evidence_by_id["ops_post_1"]["source_head"] = "f" * 40
    errors = tfx.validate_target_host_effect_binding(packet, route, fragments, evidence_by_id, valid)
    assert any("source_head is not bound" in e for e in errors)


def test_closure_rejects_postcheck_wrong_host() -> None:
    packet, route, fragments, evidence_by_id, valid = _closure_inputs(_effect_result())
    evidence_by_id["ops_post_1"]["host"] = "not-trade-core"
    errors = tfx.validate_target_host_effect_binding(packet, route, fragments, evidence_by_id, valid)
    assert any("host is not bound" in e for e in errors)


def test_closure_rejects_postcheck_missing_observed_at() -> None:
    packet, route, fragments, evidence_by_id, valid = _closure_inputs(_effect_result())
    evidence_by_id["ops_post_1"].pop("observed_at")
    errors = tfx.validate_target_host_effect_binding(packet, route, fragments, evidence_by_id, valid)
    assert any("observation time" in e for e in errors)


def test_closure_rejects_postcheck_verifier_not_receipt_node() -> None:
    # verifier_node != applier 但也 != receipt 宣告的 postcheck 節點 → 拒。
    packet, route, fragments, evidence_by_id, valid = _closure_inputs(
        _effect_result(), ops_verifier_node="some_unrelated_node"
    )
    errors = tfx.validate_target_host_effect_binding(packet, route, fragments, evidence_by_id, valid)
    assert any("must equal the effect receipt postcheck_verifier_node_id" in e for e in errors)


# --------------------------------------------------------------------------- #
# §13 C4 — STRICT attestation is the real enforcement (bypass-negatives)
# --------------------------------------------------------------------------- #
def test_effect_lane_rejects_bare_capture_attested_receipt() -> None:
    # attested PASS choice 但無內嵌 governed command_capture_v2 artifact → 嚴格 effect lane 拒。
    result = _effect_result(include_capture_artifact=False)
    errors = tfx.validate_target_host_effect_result(
        result, now=NOW, expected_source_head=HEAD, require_success=True
    )
    assert any("command_capture_v2" in e or "certify the target-host exit" in e for e in errors)


def test_effect_lane_rejects_structural_only_choice() -> None:
    # STRUCTURAL_ONLY 合成的 choice(status=FAIL)無法成為 PASS effect result(schema allOf 先擋),
    # 且作 FAILED 又 require_success=True 於 closure 路徑拒——雙向 fail-closed。
    choice = th.build_target_host_choice_receipt(
        caller="mac-structural",
        platform=th.detect_platform(),
        target_class=th.TARGET_CLASS,
        host_identity={
            "expected_host": "trade-core", "observed_host": "trade-core",
            "non_root_uid": True, "passwordless_sudo_present": False,
            "delegated_controllers": ["cpu", "memory", "pids"],
            "throwaway_root_under_runtime_dir": True,
        },
        apply_actor_node="a", postcheck_verifier_node="b",
        fixed_path_seams=th.synthesize_fixed_path_seams(
            th.PG_MODE_REAL, evidence_marker=th.EVIDENCE_STRUCTURAL,
            independent_postcheck_attached=True,
        ),
        pg_identity_mode=th.PG_MODE_REAL,
        evidence_class=th.EVIDENCE_STRUCTURAL,
        real_target_host_primitives_invoked=False,
        complete_teardown_verified=False,
        runtime_candidate_receipt_a_digest="sha256:" + "1" * 64,
        runtime_candidate_receipt_b_digest="sha256:" + "2" * 64,
        runtime_candidate_comparison_digest="sha256:" + "3" * 64,
        effect_seams_ready_receipt_digest="sha256:" + "4" * 64,
        pg_readonly_identity_receipt_digest="sha256:" + "5" * 64,
        observation_time=OBS, ttl_seconds=900,
    )
    assert choice["status"] == "FAIL"
    result = tfx.build_target_host_effect_result(
        choice_receipt=choice, intent_id="thintent-0009",
        intent_digest="sha256:" + "a" * 64, source_head=HEAD,
        approved_by="operator", approved_at="2026-07-23T12:01:00+00:00",
        started_at="2026-07-23T12:02:00+00:00", completed_at=NOW,
        intent_expires_at="2026-07-23T12:14:00+00:00",
        evidence_expires_at="2026-07-23T12:10:00+00:00",
        effect_status="TARGET_HOST_DISPOSABLE_PROBE_PASS",
    )
    result = _resign(result)
    errors = tfx.validate_target_host_effect_result(
        result, now=NOW, expected_source_head=HEAD, require_success=True
    )
    assert errors  # PASS effect result over a STRUCTURAL_ONLY/FAIL choice is rejected


def test_effect_lane_rejects_decoupled_choice_digest() -> None:
    result = _effect_result()
    result["choice_receipt_digest"] = "sha256:" + "e" * 64  # decouple from embedded self_digest
    result = _resign(result)
    errors = tfx.validate_target_host_effect_result(
        result, now=NOW, expected_source_head=HEAD, require_success=True
    )
    assert any("choice_receipt_digest must equal" in e for e in errors)


def test_effect_evidence_rejects_wrong_wrapper_adapter_source() -> None:
    result = _effect_result()
    evidence = tfx.build_target_host_effect_evidence(result)
    evidence["source"] = "deploy_adapter_v1"  # wrapper source != route node id
    errors, receipt = tfx.validate_target_host_effect_evidence(
        evidence, expected_source_head=HEAD
    )
    assert receipt is None
    assert any("is not receipt-bound" in e for e in errors)


# --------------------------------------------------------------------------- #
# central offline gate: structure-only for the choice receipt; strict for the result
# --------------------------------------------------------------------------- #
def test_central_gate_accepts_structural_choice_receipt() -> None:
    # 中央離線閘對 choice receipt 用 require_target_host_attested=False:bare-capture 的 attested
    # PASS 於此結構驗被接受(CLAUDE.md:離線 CLI 無法認證 PASS,只證結構/整合)。
    choice = th.build_attested_reference_receipt(
        now=OBS, pg_mode=th.PG_MODE_REAL, include_capture_artifact=False
    )
    assert validator.validate_aiml_artifact(choice, now=NOW) == []


def test_central_gate_is_strict_on_the_dedicated_result() -> None:
    good = _effect_result(include_capture_artifact=True)
    assert validator.validate_aiml_artifact(good, now=NOW) == []
    bare = _effect_result(include_capture_artifact=False)
    assert validator.validate_aiml_artifact(bare, now=NOW)  # strict lane rejects


def test_central_gate_needs_now_for_result() -> None:
    good = _effect_result()
    errors = validator.validate_aiml_artifact(good)  # no now
    assert any("now" in e for e in errors)


# --------------------------------------------------------------------------- #
# frozen classifier-digest pin (additive SCHEMA_FILES keys did not move S0.3 identity)
# --------------------------------------------------------------------------- #
def test_classifier_digest_pin_is_frozen() -> None:
    assert validator.aiml_effect_classifier_digest() == FROZEN_CLASSIFIER


# --------------------------------------------------------------------------- #
# S1 signer domain separation (an S0.3-namespace sig does not verify under S1)
# --------------------------------------------------------------------------- #
def _timestamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def test_s1_signer_profile_rejects_s0_3_namespace_bundle() -> None:
    da, db, dc = ("sha256:" + c * 64 for c in "abc")
    now_dt = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)
    entry = {
        "kind": "target_host_effect_result_v1", "subject_digest": db,
        "artifact_digest": db, "observed_at": _timestamp(now_dt - timedelta(minutes=1)),
        "expires_at": _timestamp(now_dt + timedelta(minutes=5)),
    }
    s0_3_bundle = {
        "schema_version": "trusted_execution_bundle_v1",
        "signer_identity": host.EXPECTED_EXECUTION_SIGNER_IDENTITY,
        "signer_fingerprint": host.EXPECTED_EXECUTION_SIGNER_FINGERPRINT,
        "algorithm": host.EXECUTION_BUNDLE_ALGORITHM,
        "signature_namespace": host.EXECUTION_SIGNATURE_NAMESPACE,
        "task_contract_digest": da, "context_artifact_digest": db, "dag_digest": dc,
        "issued_at": _timestamp(now_dt - timedelta(minutes=1)),
        "expires_at": _timestamp(now_dt + timedelta(minutes=5)), "entries": [entry],
    }
    with pytest.raises(ValueError, match="signer identity is invalid"):
        host.AuthenticatedExecutionEvidenceIndex.from_bundle(
            s0_3_bundle, signature=b"x", now=now_dt,
            task_contract_digest=da, context_artifact_digest=db, dag_digest=dc,
            signer_profile=host.S1_TARGET_HOST_EXECUTION_SIGNER_PROFILE,
        )


def test_s1_signer_consts_are_domain_separated_from_s0_3() -> None:
    assert host.EXPECTED_S1_TARGET_HOST_SIGNER_IDENTITY != host.EXPECTED_EXECUTION_SIGNER_IDENTITY
    assert host.S1_TARGET_HOST_SIGNATURE_NAMESPACE != host.EXECUTION_SIGNATURE_NAMESPACE
    # §13 更正 C2:專屬 dedicated result 以通用 effect_adapter_result_v1 kind 被認證(mirror P0-B),
    # 故其自身 kind 刻意 NOT 白名單(白名單它會成死碼+未消費項 fail-closed 陷阱)。
    assert "target_host_effect_result_v1" not in host.ALLOWED_EXECUTION_KINDS
    # 內嵌 choice receipt kind 亦刻意不加(§13 C2)。
    assert "learning_runtime_choice_receipt_target_host_v1" not in host.ALLOWED_EXECUTION_KINDS


# --------------------------------------------------------------------------- #
# E4 gap (a): the agent_governance_effects dispatch seam actually routes a
# target-host effect_adapter_result_v1-wrapped dedicated result to the sibling
# agent_governance_target_host_effects validator (not the generic deploy
# validator), keyed on the receipt adapter_id / the routed effect-node id.
# --------------------------------------------------------------------------- #
def test_effects_evidence_dispatch_routes_target_host_to_sibling(monkeypatch) -> None:
    result = _effect_result()
    evidence = tfx.build_target_host_effect_evidence(result)

    calls = {"n": 0}
    real = tfx.validate_target_host_effect_evidence

    def spy(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(tfx, "validate_target_host_effect_evidence", spy)
    errors, receipt = effects.validate_effect_evidence(
        evidence, expected_adapter_id=ADAPTER, expected_source_head=HEAD
    )
    assert calls["n"] == 1  # dispatched to the sibling target-host validator
    assert errors == []
    assert receipt is result or receipt == result


def test_effects_evidence_mismatched_adapter_does_not_dispatch(monkeypatch) -> None:
    # adapter_id 非 target-host → 不得委派 sibling;落回通用 deploy 驗證(對 target-host 形狀 receipt 拒)。
    mismatched = copy.deepcopy(_effect_result())
    mismatched["adapter_id"] = "deploy_adapter_v1"
    mismatched.pop("receipt_digest", None)
    mismatched["receipt_digest"] = tfx.target_host_effect_receipt_digest(mismatched)
    evidence = tfx.build_target_host_effect_evidence(mismatched)

    calls = {"n": 0}
    real = tfx.validate_target_host_effect_evidence

    def spy(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(tfx, "validate_target_host_effect_evidence", spy)
    errors, receipt = effects.validate_effect_evidence(
        evidence, expected_adapter_id="deploy_adapter_v1", expected_source_head=HEAD
    )
    assert calls["n"] == 0  # NOT dispatched to the target-host sibling
    assert errors  # generic deploy validator rejects a target-host-shaped receipt
    assert receipt is None


def test_effects_binding_dispatch_routes_target_host_to_sibling(monkeypatch) -> None:
    result = _effect_result()
    packet, route, fragments, evidence_by_id, valid = _closure_inputs(result)

    calls = {"n": 0}
    real = tfx.validate_target_host_effect_binding

    def spy(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(tfx, "validate_target_host_effect_binding", spy)
    errors = effects.validate_deploy_effect_binding(
        packet, route, fragments, evidence_by_id, valid
    )
    assert calls["n"] == 1  # dispatched to the sibling target-host binding
    assert errors == []


def test_effects_binding_without_target_host_node_does_not_dispatch(monkeypatch) -> None:
    # route 無 target-host adapter 節點(改為 deploy_adapter_v1)→ binding 不委派 sibling。
    result = _effect_result()
    packet, _route, fragments, evidence_by_id, valid = _closure_inputs(result)
    deploy_route = {
        "nodes": [{"id": "deploy_adapter_v1", "kind": "effect_adapter", "mandatory": True}]
    }

    calls = {"n": 0}
    real = tfx.validate_target_host_effect_binding

    def spy(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(tfx, "validate_target_host_effect_binding", spy)
    errors = effects.validate_deploy_effect_binding(
        packet, deploy_route, fragments, evidence_by_id, valid
    )
    assert calls["n"] == 0  # NOT dispatched to the target-host sibling
    # 通用 deploy 路徑看到未路由的 target-host receipt → 明確拒(未路由 adapter)。
    assert errors


# --------------------------------------------------------------------------- #
# E4 gap (b): target_host_disposable_runtime_probe_intent_v1 is in SCHEMA_FILES
# but had no artifact test. Positive passes; each documented-invariant negative
# is rejected — schema const/pattern/enum/ttl plus the wired applier!=postcheck.
# --------------------------------------------------------------------------- #
def _probe_intent() -> dict:
    return {
        "schema_version": "target_host_disposable_runtime_probe_intent_v1",
        "intent_id": "sha256:" + "a" * 64,
        "expected_host": "trade-core",
        "non_root_uid": True,
        "user_scope_only": True,
        "candidate_ids": ["content_addressed_fixed_path"],
        "per_seam_argv": {"start_stop": ["systemd-run", "--user", "--scope"]},
        "throwaway_root": "/run/user/1000/aiml-probe-xyz",
        "ttl_seconds": 900,
        "risk": "high",
        "rollback": {
            "atomic_pointer_swap": "swap current->new",
            "teardown_reset_failed": "systemctl --user reset-failed",
            "rmtree": "rm -rf throwaway_root",
        },
        "applier_node_id": "s16b_applier",
        "postcheck_node_id": "s16b_independent_verifier",
        "created_at": "2026-07-23T12:00:00+00:00",
        "expires_at": "2026-07-23T12:14:00+00:00",
        "self_digest": "sha256:" + "b" * 64,
    }


def test_probe_intent_positive_validates() -> None:
    assert validator.validate_aiml_artifact(_probe_intent(), now=NOW) == []


@pytest.mark.parametrize("mutate, needle", [
    (lambda a: a.update(postcheck_node_id=a["applier_node_id"]),
     "must differ from postcheck_node_id"),
    (lambda a: a.update(ttl_seconds=3601), "ttl_seconds"),
    (lambda a: a.update(throwaway_root="/opt/aiml/probe"), "throwaway_root"),
    (lambda a: a.update(non_root_uid=False), "non_root_uid"),
    (lambda a: a.update(user_scope_only=False), "user_scope_only"),
    (lambda a: a.update(risk="low"), "risk"),
])
def test_probe_intent_negatives_reject(mutate, needle) -> None:
    intent = _probe_intent()
    mutate(intent)
    errors = validator.validate_aiml_artifact(intent, now=NOW)
    assert any(needle in e for e in errors), errors
