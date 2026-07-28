"""S2E.1:六段 S2 effect DAG 的 claim-gated governance routing 測試。

鏡 ``test_agent_governance_p0b_effect_adapter.py`` 的兩段式 claim-selector 先例:

* selector 缺席 → 現行 source route(零 effect 節點注入;registry invariant 行為),
  既有 per-step routing 測試檔保持原樣作 source-lane 回歸錨;
* selector 在場 → exact-match 恰一 step + exact claim-key set + side_effect_class 互鎖,
  任何不符 typed ValueError,絕不靜默回落 source route;
* S2.2B 為 identity-only 註冊(registry 條目 + route class),可執行 runtime
  observer/attestor 屬 S2E.4。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

import agent_governance_routing as routing  # noqa: E402
from agent_governance_routing import (  # noqa: E402
    S2_CLAIM_KEYS_BY_STEP,
    S2_EFFECT_SELECTION_CLAIM_KEY,
    S2_EFFECT_STEPS,
    route_task,
    s2_effect_selection_digest,
)


S2_2B_ADAPTER_ID = "s2_2b_ingestion_compatibility_adapter_v1"
DIGEST = "sha256:" + "a" * 64
ALL_S2_ADAPTER_IDS = sorted({
    contract["adapter_id"] for contract in S2_EFFECT_STEPS.values()
})
# per-step 的合法粗類 facts(FORWARD 表面一致性規則的最小滿足面;install 必 critical)。
STEP_FACT_SHAPES = {
    "S2_0_APPLY": {"surfaces": ["pg", "runtime_effect"], "risk": "high"},
    "S2_4_W6A_PROBE": {"surfaces": ["runtime_effect", "service"], "risk": "high"},
    "S2_4_W6A_PREPARE": {"surfaces": ["runtime_effect", "service"], "risk": "high"},
    "S2_4_W6B_PROBE": {"surfaces": ["runtime_effect", "service"], "risk": "high"},
    "S2_4_W6B_APPLY": {
        "surfaces": ["runtime_effect", "service", "pg", "secret"], "risk": "critical",
    },
    "S2_5A_START": {"surfaces": ["runtime_effect", "service"], "risk": "high"},
    "S2_1_DRILL": {"surfaces": ["runtime_effect", "service"], "risk": "high"},
    "S2_5B_FINAL": {"surfaces": ["runtime_effect", "service"], "risk": "high"},
    "S2_2B_RUNTIME_DONE": {"surfaces": ["pg", "runtime_effect"], "risk": "high"},
}


def _claims(step: str) -> dict[str, str]:
    claims = {
        key: DIGEST for key in S2_CLAIM_KEYS_BY_STEP[step]
        if key != S2_EFFECT_SELECTION_CLAIM_KEY
    }
    claims[S2_EFFECT_SELECTION_CLAIM_KEY] = s2_effect_selection_digest(step)
    return claims


def _facts(step: str, **overrides) -> dict:
    facts = {
        "task_shape": "audit",
        "risk": STEP_FACT_SHAPES[step]["risk"],
        "surfaces": list(STEP_FACT_SHAPES[step]["surfaces"]),
        "uncertainty": "low",
        "runtime_claim": True,
        "end_to_end_claim": False,
        "side_effect_class": S2_EFFECT_STEPS[step]["side_effect_class"],
        "task_prompt": f"S2E.1 {step} effect admission",
        "dirty_scope": [],
        "claim_inputs": _claims(step),
    }
    facts.update(overrides)
    return facts


@pytest.mark.parametrize("step", sorted(S2_EFFECT_STEPS))
def test_each_s2_step_is_an_exact_independently_admitted_effect(step: str) -> None:
    contract = S2_EFFECT_STEPS[step]
    route = route_task(_facts(step))
    effect_nodes = [
        node for node in route["nodes"] if node["kind"] == "effect_adapter"
    ]
    approval_id = f"pm_{step.lower()}_approval"
    expected = {
        "id": contract["adapter_id"],
        "kind": "effect_adapter",
        "requires": [approval_id],
        "mandatory": True,
        "reason": f"claim-admitted S2 {step} effect seam",
        "effect_step": step,
        **{
            key: value for key, value in contract.items()
            if key not in {"adapter_id", "side_effect_class"}
        },
    }
    assert effect_nodes == [expected]
    by_id = {node["id"]: node for node in route["nodes"]}
    assert by_id[approval_id]["role"] == "PM"
    assert by_id[approval_id]["requires"] == ["ops_preflight"]
    assert by_id["ops_postcheck"]["requires"] == [contract["adapter_id"]]
    # 相鄰 adapter / 通用 deploy adapter 不得出現。
    node_ids = set(by_id)
    for other in ALL_S2_ADAPTER_IDS:
        if other != contract["adapter_id"]:
            assert other not in node_ids, other
    assert "deploy_adapter_v1" not in node_ids
    assert routing.TARGET_HOST_PROBE_ADAPTER_ID not in node_ids
    assert route["task_facts"]["claim_inputs"] == _claims(step)


@pytest.mark.parametrize("step", sorted(S2_EFFECT_STEPS))
def test_effect_lane_admission_keeps_the_delegated_dag_digest_stable(step: str) -> None:
    # effect-lane facts 的 claim_inputs 不同=新 admission(task_contract_digest 變),
    # 但 role 拓撲穩定:effect_adapter/PM 節點不進 required_role_nodes,delegated
    # predecessors 穿透回 ops_preflight → dag_digest 與同 facts 的 source-lane route 相等。
    effect_route = route_task(_facts(step))
    source_route = route_task(_facts(step, claim_inputs={}))
    assert effect_route["dag_digest"] == source_route["dag_digest"]
    assert [
        node["node_id"] for node in effect_route["required_role_nodes"]
    ] == [
        node["node_id"] for node in source_route["required_role_nodes"]
    ]


def test_s2_selection_and_claim_inventory_fail_closed() -> None:
    # 缺一個 claim key → exact-set ValueError。
    missing = _facts("S2_4_W6B_APPLY")
    missing["claim_inputs"].pop("s2_4_pg_migration_authorization")
    with pytest.raises(ValueError, match="exact claim_inputs"):
        route_task(missing)

    # 多一個未 admitted 的 claim key → exact-set ValueError。
    extra = _facts("S2_0_APPLY")
    extra["claim_inputs"]["unadmitted_extra"] = DIGEST
    with pytest.raises(ValueError, match="exact claim_inputs"):
        route_task(extra)

    # 跨 step permit key 混入(S2_5A inventory + S2_5B permit)→ exact-set ValueError。
    mixed = _facts("S2_5A_START")
    mixed["claim_inputs"]["s2_5b_final_permit"] = DIGEST
    with pytest.raises(ValueError, match="exact claim_inputs"):
        route_task(mixed)

    # 跨 step selector relabel(W6A probe 的 claims + W6B probe 的 selector)→ exact-set
    # ValueError(兩 step 的 claim inventory 不同,relabel 後集合必不 exact)。
    relabelled = _facts("S2_4_W6A_PROBE")
    relabelled["claim_inputs"][S2_EFFECT_SELECTION_CLAIM_KEY] = (
        s2_effect_selection_digest("S2_4_W6B_PROBE")
    )
    with pytest.raises(ValueError, match="exact claim_inputs"):
        route_task(relabelled)

    # selector + 空 inventory → exact-set ValueError(missing 全列)。
    bare = _facts("S2_1_DRILL")
    bare["claim_inputs"] = {
        S2_EFFECT_SELECTION_CLAIM_KEY: s2_effect_selection_digest("S2_1_DRILL")
    }
    with pytest.raises(ValueError, match="exact claim_inputs"):
        route_task(bare)

    # 偽 selector digest(格式合法、值不中恰一 step)→ typed ValueError。
    forged = _facts("S2_0_APPLY")
    forged["claim_inputs"][S2_EFFECT_SELECTION_CLAIM_KEY] = DIGEST
    with pytest.raises(ValueError, match="selection digest is invalid"):
        route_task(forged)

    # S2 step claim key 出現但 selector 缺 → typed ValueError(絕不靜默回落 source route)。
    orphan = _facts("S2_0_APPLY")
    orphan["claim_inputs"] = {"s2_0_operator_authorization": DIGEST}
    with pytest.raises(ValueError, match="exact selection digest"):
        route_task(orphan)


def test_s2_selector_class_interlock_rejects_wrong_side_effect_class() -> None:
    # selector=S2_0_APPLY 但粗類是 quiesce_fence(表面規則合法)→ 互鎖 ValueError。
    facts = _facts("S2_0_APPLY")
    facts["surfaces"] = ["runtime_effect", "service"]
    facts["side_effect_class"] = "quiesce_fence"
    with pytest.raises(ValueError, match="requires side_effect_class=pg_observer_bootstrap"):
        route_task(facts)


def test_effect_lane_does_not_relax_source_lane_surface_rules() -> None:
    # S2.5B effect lane 帶 pg 面照樣被 s2_5 forbidden-surface 規則拒(FORWARD 規則原樣續跑)。
    facts = _facts("S2_5B_FINAL")
    facts["surfaces"] = ["runtime_effect", "service", "pg"]
    with pytest.raises(ValueError, match="must not carry"):
        route_task(facts)
    # probe effect lane 帶 APPLY 面(secret)亦拒(§10.5 #38)。
    probe = _facts("S2_4_W6A_PROBE")
    probe["surfaces"] = ["runtime_effect", "service", "secret"]
    with pytest.raises(ValueError, match="must not carry APPLY surfaces"):
        route_task(probe)


def test_s2_selector_does_not_disturb_p0b_admission() -> None:
    from agent_governance_routing import (
        P0B_ADAPTER_ID, P0B_CLAIM_KEYS_BY_PHASE, p0b_effect_selection_digest,
    )

    claims = {key: DIGEST for key in P0B_CLAIM_KEYS_BY_PHASE["stage"]}
    claims["p0b_effect_adapter_selection"] = p0b_effect_selection_digest("stage")
    route = route_task({
        "task_shape": "deploy",
        "surfaces": ["authority", "service", "runtime_effect"],
        "risk": "critical",
        "uncertainty": "low",
        "runtime_claim": True,
        "end_to_end_claim": False,
        "side_effect_class": "deploy",
        "task_prompt": "P0-B stage remains claim-admitted",
        "claim_inputs": claims,
    })
    assert [
        node["id"] for node in route["nodes"] if node["kind"] == "effect_adapter"
    ] == [P0B_ADAPTER_ID]
    for adapter_id in ALL_S2_ADAPTER_IDS:
        assert adapter_id not in {node["id"] for node in route["nodes"]}


@pytest.mark.parametrize(
    "effect_class",
    sorted({contract["side_effect_class"] for contract in S2_EFFECT_STEPS.values()}),
)
def test_source_lane_stays_unreachable_without_selector(effect_class: str) -> None:
    # source lane 不可達性證明義務:對每個 S2 class,claim_inputs={} 斷言零 effect 節點且
    # 9 個 adapter id 全不在 node_ids(registry invariant 要求的行為;含新 S2.2B class)。
    step = next(
        step for step, contract in S2_EFFECT_STEPS.items()
        if contract["side_effect_class"] == effect_class
    )
    route = route_task(_facts(step, claim_inputs={}))
    node_ids = {node["id"] for node in route["nodes"]}
    assert [
        node for node in route["nodes"] if node["kind"] == "effect_adapter"
    ] == []
    for adapter_id in ALL_S2_ADAPTER_IDS:
        assert adapter_id not in node_ids, adapter_id
    assert "ops_preflight" in node_ids and "ops_postcheck" in node_ids


def test_selection_digests_are_distinct_and_step_bound() -> None:
    digests = {step: s2_effect_selection_digest(step) for step in S2_EFFECT_STEPS}
    assert len(set(digests.values())) == len(digests)
    with pytest.raises(ValueError, match="invalid S2 effect step"):
        s2_effect_selection_digest("S2_9_UNKNOWN")


def test_s2_2b_routing_constant_matches_registry_identity() -> None:
    assert routing.S2_2B_INGESTION_ADAPTER_ID == S2_2B_ADAPTER_ID
    assert S2_EFFECT_STEPS["S2_2B_RUNTIME_DONE"]["adapter_id"] == S2_2B_ADAPTER_ID
    # identity-only:S2.2B step 無 intent/rollback schema metadata(S2E.4 才有可執行 attestor)。
    assert "intent_schema_version" not in S2_EFFECT_STEPS["S2_2B_RUNTIME_DONE"]
    assert "rollback_schema_version" not in S2_EFFECT_STEPS["S2_2B_RUNTIME_DONE"]


def test_registry_carries_identity_only_s2_2b_adapter_fail_closed() -> None:
    registry = json.loads(
        (ROOT / ".codex/agent_registry_v1.json").read_text(encoding="utf-8")
    )
    entry = registry["effect_adapters"][S2_2B_ADAPTER_ID]
    assert entry["status"] == (
        "declared_runtime_done_fail_closed_until_s2e4_observer_attestor"
    )
    assert entry["owner_session"] == "S2.2B"
    invariant = entry["invariant"]
    # 五個 invariant 子句(設計 §C):fail-closed / 九 authority false / EFFECT session 前
    # 不注入 / S2.5B 唯一合法上游 / runtime-attestor 執行與驗證屬 S2E.4。
    for clause in (
        "fail-closed EXTERNAL_VERIFICATION_PENDING",
        "nine authorities stay false",
        "no route_task effect node or closure effect binding is injected "
        "before the S2.2B EFFECT session",
        "only s2_5_final_attestation_v1 is the legal upstream of the S2.2B runtime-DONE",
        "execution/verification is S2E.4",
    ):
        assert clause in invariant, clause
    assert entry["implementation_paths"] == [
        "helper_scripts/maintenance_scripts/agent_governance_s2_2b.py"
    ]
    assert entry["component_paths"] == [
        "program_code/ml_training/aiml_gate_receipt_s2_2b.py"
    ]
    assert entry["receipt_schema_path"] == (
        "program_code/ml_training/schemas/aiml_gate_receipts/"
        "ingestion_compatibility_receipt_v1.schema.json"
    )
    for path in (
        *entry["implementation_paths"],
        *entry["component_paths"],
        entry["receipt_schema_path"],
    ):
        assert (ROOT / path).is_file(), path
