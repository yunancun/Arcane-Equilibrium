"""S2E.1:S2 effect closure binding sibling(agent_governance_s2_effect_binding)測試。

鏡 ``test_agent_governance_p0b_effect_adapter.py`` 的 closure 段:結構綁定測試把
receipt 實際重算的縫(``_receipt_validation_errors``,真身=中央 AIML 閘)monkeypatch
為 [],另以 sentinel 測試釘住真委派;R3 敘事型負例證明「route 通過但 adapter 拒」
(EXTERNAL_VERIFICATION_PENDING/RECOVERY_REQUIRED 永不換算 closure PASS)。
"""
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for _candidate in (HELPERS, ML_ROOT):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import agent_governance_effects as effects  # noqa: E402
import agent_governance_routing as routing  # noqa: E402
import agent_governance_s2_effect_binding as binding  # noqa: E402
from agent_governance_routing import (  # noqa: E402
    S2_CLAIM_KEYS_BY_STEP,
    S2_EFFECT_SELECTION_CLAIM_KEY,
    S2_EFFECT_STEPS,
    route_task,
    s2_effect_selection_digest,
)


DIGEST = "sha256:" + "a" * 64
HEAD = "b" * 40
T_START = "2026-07-28T10:00:00Z"
T_DONE = "2026-07-28T10:05:00Z"
T_POST = "2026-07-28T10:06:00Z"
T_EXPIRY = "2026-07-28T10:20:00Z"
# 與 routing 測試同形的 per-step 合法粗類 facts(effect lane 硬性要求 authority 面)。
STEP_FACT_SHAPES = {
    "S2_0_APPLY": {"surfaces": ["authority", "pg", "runtime_effect"], "risk": "high"},
    "S2_4_W6A_PROBE": {
        "surfaces": ["authority", "runtime_effect", "service"], "risk": "high",
    },
    "S2_4_W6A_PREPARE": {
        "surfaces": ["authority", "runtime_effect", "service"], "risk": "high",
    },
    "S2_4_W6B_PROBE": {
        "surfaces": ["authority", "runtime_effect", "service"], "risk": "high",
    },
    "S2_4_W6B_APPLY": {
        "surfaces": ["authority", "runtime_effect", "service", "pg", "secret"],
        "risk": "critical",
    },
    "S2_5A_START": {
        "surfaces": ["authority", "runtime_effect", "service"], "risk": "high",
    },
    "S2_1_DRILL": {
        "surfaces": ["authority", "runtime_effect", "service"], "risk": "high",
    },
    "S2_5B_FINAL": {
        "surfaces": ["authority", "runtime_effect", "service"], "risk": "high",
    },
    "S2_2B_RUNTIME_DONE": {
        "surfaces": ["authority", "pg", "runtime_effect"], "risk": "high",
    },
}
# CC-B:closure PASS 被 contract 明文阻塞的 step(今日 = S2_1_DRILL)不進正例參數化。
PASSABLE_STEPS = sorted(
    step for step in S2_EFFECT_STEPS
    if binding.S2_STEP_RECEIPT_CONTRACTS[step]["closure_pass_blocked_reason"] is None
)
BLOCKED_STEPS = sorted(set(S2_EFFECT_STEPS) - set(PASSABLE_STEPS))
# 被阻塞 step 的「最佳可得 status」——用來證明即使拿出該 status 也不換算 PASS。
_BLOCKED_STEP_STATUS = {"S2_1_DRILL": "QUIESCED_STATIC_GUARDS_HELD"}


def _claims(step: str) -> dict[str, str]:
    claims = {
        key: DIGEST for key in S2_CLAIM_KEYS_BY_STEP[step]
        if key != S2_EFFECT_SELECTION_CLAIM_KEY
    }
    claims[S2_EFFECT_SELECTION_CLAIM_KEY] = s2_effect_selection_digest(step)
    return claims


def _route(step: str) -> dict:
    return route_task({
        "task_shape": "audit",
        "risk": STEP_FACT_SHAPES[step]["risk"],
        "surfaces": list(STEP_FACT_SHAPES[step]["surfaces"]),
        "uncertainty": "low",
        "runtime_claim": True,
        "end_to_end_claim": False,
        "side_effect_class": S2_EFFECT_STEPS[step]["side_effect_class"],
        "task_prompt": f"S2E.1 {step} closure binding",
        "dirty_scope": [],
        "claim_inputs": _claims(step),
    })


def _receipt(step: str) -> dict:
    """最小 receipt:只鋪 binding 模組所觸欄位(實際重算縫由 monkeypatch 短路)。"""

    contract = binding.S2_STEP_RECEIPT_CONTRACTS[step]
    receipt: dict = {
        "schema_version": contract["receipt_schema_version"],
        "self_digest": "sha256:" + "d" * 64,
        "source_head": HEAD,
    }
    if step == "S2_2B_RUNTIME_DONE":
        receipt["status"] = "RUNTIME_COMPATIBILITY_ATTESTED"
        receipt["manifest_revalidation"] = {
            "observed_at": T_DONE, "evidence_expires_at": T_EXPIRY,
        }
        receipt["s2_5_final_attestation"] = {"target_host": "trade-core"}
        receipt["s2_5_final_attestation_digest"] = DIGEST
        return receipt
    receipt["target_host"] = "trade-core"
    receipt[contract["status_field"]] = (
        next(iter(contract["success_statuses"]))
        if contract["success_statuses"] else _BLOCKED_STEP_STATUS[step]
    )
    receipt[contract["intent_id_field"]] = f"{step.lower()}-0001"
    receipt[contract["intent_digest_field"]] = "sha256:" + "e" * 64
    if contract["started_field"] == contract["observed_field"]:
        # s2_4 家族:observed_at/expires_at 單時窗。
        receipt["observed_at"] = T_DONE
        receipt["expires_at"] = T_EXPIRY
    else:
        receipt["started_at"] = T_START
        receipt["completed_at"] = T_DONE
        receipt["evidence_expires_at"] = T_EXPIRY
    if "probe_scope" in S2_EFFECT_STEPS[step]:
        receipt["probe_scope"] = S2_EFFECT_STEPS[step]["probe_scope"]
    if step in {"S2_0_APPLY", "S2_1_DRILL", "S2_5A_START", "S2_5B_FINAL"}:
        receipt["adapter_id"] = S2_EFFECT_STEPS[step]["adapter_id"]
    # claim↔receipt 綁定欄位鋪成 admission claim 的同值。
    claims = _claims(step)
    for claim_key, receipt_field in contract["claim_receipt_bindings"].items():
        receipt[receipt_field] = claims[claim_key]
    return receipt


def _postcheck(step: str, receipt: dict, postcheck_id: str = "pc") -> dict:
    """契約白名單 kind 的獨立 ops_postcheck evidence(payload 交叉綁 receipt self_digest)。"""

    contract = binding.S2_STEP_RECEIPT_CONTRACTS[step]
    postcheck = {
        "id": postcheck_id,
        "scope": "runtime",
        "source": "ops_postcheck",
        "kind": contract["postcheck_kind"],
        "observed_at": T_POST,
        "expiry": T_EXPIRY,
    }
    binding_field = contract["postcheck_receipt_binding"]
    if binding_field is not None:
        assert binding_field.startswith("payload.")
        postcheck["payload"] = {
            binding_field.split(".", 1)[1]: receipt["self_digest"]
        }
    return postcheck


def _packet(step: str, receipt: dict, postcheck_id: str = "pc") -> tuple[dict, dict, dict]:
    contract = binding.S2_STEP_RECEIPT_CONTRACTS[step]
    postcheck = _postcheck(step, receipt, postcheck_id)
    authority_refs = []
    if contract["intent_schema_version"] is not None:
        authority_refs.append({
            "class": "claim_evidence",
            "source": (
                f"{contract['intent_schema_version']}:"
                f"{receipt[contract['intent_id_field']]}"
            ),
            "digest": receipt[contract["intent_digest_field"]],
            "observed_at": T_START,
        })
    packet = {
        "authority_refs": authority_refs,
        "acceptance": [{"status": "PASS", "evidence_refs": ["effect", postcheck_id]}],
        "side_effects": {"runtime_contact": True},
        "disposition": "CHANGED",
    }
    fragments = {"ops_postcheck": {"evidence_refs": [postcheck_id]}}
    evidence_by_id = {postcheck_id: postcheck}
    return packet, fragments, evidence_by_id


@pytest.fixture()
def structural_receipts(monkeypatch: pytest.MonkeyPatch):
    """結構綁定測試短路兩個委派縫(真委派各由 sentinel 與 typed 負例另釘)。

    * ``_receipt_validation_errors`` —— receipt 實際重算(中央 AIML 閘)。
    * ``_delegated_binding_errors`` —— S2.0/S2.1 的既有 per-step closure 硬門(CC-A);
      其真收據需要真 SSHSIG/丟棄式叢集,結構層測試以此縫短路。
    """

    monkeypatch.setattr(binding, "_receipt_validation_errors", lambda *_a, **_k: [])
    monkeypatch.setattr(binding, "_delegated_binding_errors", lambda *_a, **_k: [])


@pytest.mark.parametrize("step", PASSABLE_STEPS)
def test_each_step_closure_binding_passes_with_exact_cross_bound_evidence(
    structural_receipts, step: str,
) -> None:
    route = _route(step)
    receipt = _receipt(step)
    packet, fragments, evidence_by_id = _packet(step, receipt)
    assert binding.validate_s2_effect_binding(
        packet, route, fragments, evidence_by_id, {"effect": receipt}
    ) == []

    evidence = binding.build_s2_effect_evidence(receipt)
    errors, validated = binding.validate_s2_effect_evidence(
        evidence, expected_source_head=HEAD
    )
    assert errors == []
    assert validated is receipt


@pytest.mark.parametrize("step", PASSABLE_STEPS)
def test_acceptance_missing_postcheck_binding_fails_closed(
    structural_receipts, step: str,
) -> None:
    route = _route(step)
    receipt = _receipt(step)
    packet, fragments, evidence_by_id = _packet(step, receipt)
    packet["acceptance"] = [{"status": "PASS", "evidence_refs": ["effect"]}]
    assert (
        "S2 passed acceptance must bind the effect receipt and the "
        "independent ops_postcheck"
    ) in binding.validate_s2_effect_binding(
        packet, route, fragments, evidence_by_id, {"effect": receipt}
    )


@pytest.mark.parametrize("step", BLOCKED_STEPS)
def test_blocked_step_never_converts_a_disposable_proof_into_a_pass(
    structural_receipts, step: str,
) -> None:
    """CC-B:S2.1 的 QUIESCED_STATIC_GUARDS_HELD 是 disposable_local 邏輯證明。

    quiesce_result_v1.schema.json 規定該 status ⇒ target_class=disposable_local 且
    evidence_class=LOCAL_REPRODUCIBLE,且 boundary 無條件 production_fence_performed=false。
    binding 絕不能在「明知未對 production 施加 fence」的收據上簽發 runtime_contact PASS。
    """

    route = _route(step)
    receipt = _receipt(step)
    packet, fragments, evidence_by_id = _packet(step, receipt)
    errors = binding.validate_s2_effect_binding(
        packet, route, fragments, evidence_by_id, {"effect": receipt}
    )
    assert any(
        f"S2 {step} has no closure-admissible success status" in error
        for error in errors
    ), errors
    # 該 step 的成功集為空:任何 status 都進不了 valid_receipts。
    evidence = binding.build_s2_effect_evidence(receipt)
    evidence_errors, validated = binding.validate_s2_effect_evidence(
        evidence, expected_source_head=HEAD
    )
    assert validated is None
    assert any(
        f"S2 {step} has no closure-admissible success status" in error
        for error in evidence_errors
    ), evidence_errors
    # 被阻塞的 step 不得順帶要求 runtime_contact/CHANGED(無可達成功頂點時那是假語義)。
    assert not any("runtime_contact=true" in error for error in errors), errors
    assert not any("must be CHANGED" in error for error in errors), errors


def test_s2_1_drill_success_status_is_blocked_not_silently_dropped() -> None:
    contract = binding.S2_STEP_RECEIPT_CONTRACTS["S2_1_DRILL"]
    assert contract["success_statuses"] == frozenset()
    reason = contract["closure_pass_blocked_reason"]
    assert "quiesce_result_v1 has no production/attested success status today" in reason
    assert "production_fence_performed=false" in reason
    assert "QUIESCED_STATIC_GUARDS_HELD" in reason


def test_s2_0_success_set_excludes_production_applied() -> None:
    """CC-A:production APPLIED 需 out-of-band trusted-host 驗證,屬 S2.0 EFFECT session。"""

    contract = binding.S2_STEP_RECEIPT_CONTRACTS["S2_0_APPLY"]
    assert contract["success_statuses"] == frozenset({"APPLIED_ROLLED_BACK_EXACT"})
    assert "APPLIED" not in contract["success_statuses"]
    # 既有硬門的成功語義即本模組的成功集(單一權威,不各自為政)。
    import agent_governance_pg_observer_bootstrap as observer

    assert contract["success_statuses"] <= observer.RESULT_STATUSES


def test_delegated_per_step_hard_gates_are_wired_not_bypassed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CC-A sentinel:S2.0/S2.1 一定實際呼叫既有 per-step closure predicate。"""

    import agent_governance_alr_quiesce_fence as quiesce
    import agent_governance_pg_observer_bootstrap as observer

    assert binding._DELEGATED_STEP_BINDINGS == {
        "S2_0_APPLY": observer.validate_pg_observer_bootstrap_binding,
        "S2_1_DRILL": quiesce.validate_quiesce_fence_binding,
    }
    monkeypatch.setattr(binding, "_receipt_validation_errors", lambda *_a, **_k: [])
    for step, module, attr in (
        ("S2_0_APPLY", observer, "validate_pg_observer_bootstrap_binding"),
        ("S2_1_DRILL", quiesce, "validate_quiesce_fence_binding"),
    ):
        seen: list = []
        monkeypatch.setitem(
            binding._DELEGATED_STEP_BINDINGS, step,
            lambda *args, _seen=seen: _seen.append(args) or ["sentinel"],
        )
        route = _route(step)
        receipt = _receipt(step)
        packet, fragments, evidence_by_id = _packet(step, receipt)
        errors = binding.validate_s2_effect_binding(
            packet, route, fragments, evidence_by_id, {"effect": receipt}
        )
        assert "sentinel" in errors, step
        assert seen and seen[0] == (
            packet, route, fragments, evidence_by_id, {"effect": receipt}
        ), step
        assert callable(getattr(module, attr))


@pytest.mark.parametrize(
    ("step", "expected"),
    [
        (
            "S2_0_APPLY",
            "observer bootstrap closure requires the receipt's embedded independent postcheck",
        ),
        (
            "S2_1_DRILL",
            "quiesce fence closure requires the receipt's embedded post-unfence observation",
        ),
    ],
)
def test_delegated_hard_gate_rejects_a_receipt_without_the_embedded_postcheck(
    monkeypatch: pytest.MonkeyPatch, step: str, expected: str,
) -> None:
    """CC-A 真委派負例(不 monkeypatch 委派縫):既有硬門要求的內嵌獨立 postcheck 缺席即拒。

    這正是新模組完全沒有的檢查——applier != verifier 與三方 digest 交叉核的入口。
    """

    monkeypatch.setattr(binding, "_receipt_validation_errors", lambda *_a, **_k: [])
    route = _route(step)
    receipt = _receipt(step)
    receipt["status"] = (
        "APPLIED_ROLLED_BACK_EXACT" if step == "S2_0_APPLY"
        else "QUIESCED_STATIC_GUARDS_HELD"
    )
    packet, fragments, evidence_by_id = _packet(step, receipt)
    fragments["ops_preflight"] = {"evidence_refs": []}
    errors = binding.validate_s2_effect_binding(
        packet, route, fragments, evidence_by_id, {"effect": receipt}
    )
    assert expected in errors, errors
    # 內嵌 postcheck 缺席 ⇒ 委派硬門的 acceptance 也必須拒(verifier capture 未被承認)。
    assert any(
        "passed acceptance must bind the effect receipt + verifier command capture" in error
        for error in errors
    ), errors


@pytest.mark.parametrize(
    ("step", "embedded_field", "expected"),
    [
        (
            "S2_0_APPLY", "independent_postcheck",
            "observer bootstrap verifier capture digest is not the three-way-bound digest",
        ),
        (
            "S2_1_DRILL", "post_unfence_observation",
            "quiesce fence verifier capture digest is not the three-way-bound digest",
        ),
    ],
)
def test_delegated_hard_gate_runs_the_three_way_capture_cross_check(
    monkeypatch: pytest.MonkeyPatch, step: str, embedded_field: str, expected: str,
) -> None:
    """CC-A:receipt 內嵌 verifier_capture_digest == ops_postcheck evidence digest ==
    內嵌 command_capture_v2.record_digest,且 capture node ≠ applier——本模組沒有這條,
    只有被委派的既有硬門有。"""

    monkeypatch.setattr(binding, "_receipt_validation_errors", lambda *_a, **_k: [])
    bound = "sha256:" + "9" * 64
    route = _route(step)
    receipt = _receipt(step)
    receipt["status"] = (
        "APPLIED_ROLLED_BACK_EXACT" if step == "S2_0_APPLY"
        else "QUIESCED_STATIC_GUARDS_HELD"
    )
    receipt["apply_actor_node"] = "s2_apply_actor"
    receipt[embedded_field] = {
        "verifier_node": "s2_ops_postcheck", "verifier_capture_digest": bound,
    }
    packet, fragments, evidence_by_id = _packet(step, receipt)
    fragments["ops_preflight"] = {"evidence_refs": []}
    evidence_by_id["pc"].update({
        "digest": "sha256:" + "8" * 64,
        "artifact": {
            "schema_version": "command_capture_v2",
            "node_id": "s2_apply_actor",
            "record_digest": "sha256:" + "7" * 64,
        },
    })
    errors = binding.validate_s2_effect_binding(
        packet, route, fragments, evidence_by_id, {"effect": receipt}
    )
    assert expected in errors, errors
    assert any("record_digest is not the bound digest" in error for error in errors), errors
    assert any(
        "capture node must differ from the applier node" in error for error in errors
    ), errors


def test_delegated_hard_gate_requires_the_ops_preflight_fragment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(binding, "_receipt_validation_errors", lambda *_a, **_k: [])
    route = _route("S2_0_APPLY")
    receipt = _receipt("S2_0_APPLY")
    packet, fragments, evidence_by_id = _packet("S2_0_APPLY", receipt)
    assert "observer bootstrap closure requires an OPS preflight fragment" in (
        binding.validate_s2_effect_binding(
            packet, route, fragments, evidence_by_id, {"effect": receipt}
        )
    )


def test_delegated_hard_gate_rejects_production_applied_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CC-A:即使有人把 production APPLIED 收據硬塞進 valid_receipts,委派硬門仍拒。"""

    monkeypatch.setattr(binding, "_receipt_validation_errors", lambda *_a, **_k: [])
    route = _route("S2_0_APPLY")
    receipt = _receipt("S2_0_APPLY")
    receipt["status"] = "APPLIED"
    packet, fragments, evidence_by_id = _packet("S2_0_APPLY", receipt)
    assert (
        "observer bootstrap closure PASS requires an APPLIED_ROLLED_BACK_EXACT receipt"
    ) in binding.validate_s2_effect_binding(
        packet, route, fragments, evidence_by_id, {"effect": receipt}
    )


def test_cross_step_receipt_is_rejected_as_unrouted(structural_receipts) -> None:
    # admitted W6A probe route + INSTALLED_UNIT scope receipt:scope 互斥由 step 差保證。
    route = _route("S2_4_W6A_PROBE")
    receipt = _receipt("S2_4_W6B_PROBE")
    packet, fragments, evidence_by_id = _packet("S2_4_W6B_PROBE", receipt)
    errors = binding.validate_s2_effect_binding(
        packet, route, fragments, evidence_by_id, {"effect": receipt}
    )
    assert any("not routed to the admitted step" in error for error in errors)
    assert any("exactly one S2_4_W6A_PROBE effect receipt" in error for error in errors)


def test_claim_receipt_digest_binding_fails_closed(structural_receipts) -> None:
    route = _route("S2_4_W6B_APPLY")
    receipt = _receipt("S2_4_W6B_APPLY")
    receipt["installed_unit_probe_receipt_digest"] = "sha256:" + "f" * 64
    packet, fragments, evidence_by_id = _packet("S2_4_W6B_APPLY", receipt)
    assert any(
        "installed_unit_probe_receipt_digest is not claim-bound" in error
        for error in binding.validate_s2_effect_binding(
            packet, route, fragments, evidence_by_id, {"effect": receipt}
        )
    )


def test_postcheck_must_not_predate_effect_completion(structural_receipts) -> None:
    route = _route("S2_5B_FINAL")
    receipt = _receipt("S2_5B_FINAL")
    packet, fragments, evidence_by_id = _packet("S2_5B_FINAL", receipt)
    evidence_by_id["pc"]["observed_at"] = "2026-07-28T10:04:00Z"
    assert "S2 ops_postcheck predates the effect receipt completion" in (
        binding.validate_s2_effect_binding(
            packet, route, fragments, evidence_by_id, {"effect": receipt}
        )
    )


def test_intent_authority_cross_binding_fails_closed(structural_receipts) -> None:
    route = _route("S2_5A_START")
    receipt = _receipt("S2_5A_START")
    packet, fragments, evidence_by_id = _packet("S2_5A_START", receipt)
    forged = deepcopy(packet)
    forged["authority_refs"][0]["digest"] = DIGEST
    assert any(
        "lacks exact intent authority" in error
        for error in binding.validate_s2_effect_binding(
            forged, route, fragments, evidence_by_id, {"effect": receipt}
        )
    )
    late = deepcopy(packet)
    late["authority_refs"][0]["observed_at"] = T_DONE
    assert any(
        "observed after effect start" in error
        for error in binding.validate_s2_effect_binding(
            late, route, fragments, evidence_by_id, {"effect": receipt}
        )
    )


@pytest.mark.parametrize(
    "status", ["EXTERNAL_VERIFICATION_PENDING", "RECOVERY_REQUIRED"],
)
def test_r3_route_admission_is_never_apply_authority(
    structural_receipts, status: str,
) -> None:
    """R3 敘事型負例:route 通過(claim admission 成立)但 adapter 層拒——head/freshness/
    permit 的真偽閉合在 adapter 與 closure,route 層 typed 收據 status 不在 production
    成功集即 closure 拒收,永不換算 PASS。"""

    route = _route("S2_0_APPLY")
    assert [
        node["id"] for node in route["nodes"] if node["kind"] == "effect_adapter"
    ] == [routing.PG_OBSERVER_BOOTSTRAP_ADAPTER_ID]
    receipt = _receipt("S2_0_APPLY")
    receipt["status"] = status
    evidence = binding.build_s2_effect_evidence(receipt)
    errors, validated = binding.validate_s2_effect_evidence(
        evidence, expected_source_head=HEAD
    )
    assert validated is None
    assert any("not a closure-admissible production success" in e for e in errors)


def test_source_simulation_pass_is_not_an_effect_receipt(structural_receipts) -> None:
    receipt = _receipt("S2_5A_START")
    receipt["status"] = "SOURCE_SIMULATION_PASS"
    evidence = binding.build_s2_effect_evidence(receipt)
    errors, validated = binding.validate_s2_effect_evidence(
        evidence, expected_source_head=HEAD
    )
    assert validated is None and errors


def test_evidence_wrapper_binding_and_head_fail_closed(structural_receipts) -> None:
    receipt = _receipt("S2_0_APPLY")
    evidence = binding.build_s2_effect_evidence(receipt)
    tampered = deepcopy(evidence)
    tampered["host"] = "other-host"
    errors, validated = binding.validate_s2_effect_evidence(
        tampered, expected_source_head=HEAD
    )
    assert validated is None
    assert any("host is not receipt-bound" in error for error in errors)
    errors, validated = binding.validate_s2_effect_evidence(
        evidence, expected_source_head="c" * 40
    )
    assert validated is None
    assert any("source_head does not match closure baseline" in e for e in errors)


def test_receipt_revalidation_truly_delegates_to_the_central_aiml_gate() -> None:
    # 不 monkeypatch:一份缺欄位的最小 receipt 必被中央閘(schema 閉合驗)拒。
    errors = binding._receipt_validation_errors(
        {"schema_version": "pg_observer_bootstrap_result_v1"}, now=T_DONE
    )
    assert errors
    receipt = _receipt("S2_0_APPLY")
    evidence = binding.build_s2_effect_evidence(receipt)
    errors, validated = binding.validate_s2_effect_evidence(
        evidence, expected_source_head=HEAD
    )
    assert validated is None
    assert any("S2 S2_0_APPLY receipt invalid" in error for error in errors)


def test_effects_dispatch_delegates_s2_family_by_schema_and_node(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel_evidence: list = []
    sentinel_binding: list = []
    monkeypatch.setattr(
        effects.s2_effect_binding, "validate_s2_effect_evidence",
        lambda evidence, *, expected_source_head: (
            sentinel_evidence.append(expected_source_head) or (["sentinel"], None)
        ),
    )
    monkeypatch.setattr(
        effects.s2_effect_binding, "validate_s2_effect_binding",
        lambda *args: sentinel_binding.append(args) or ["sentinel-binding"],
    )
    errors, validated = effects.validate_effect_evidence(
        {"receipt": {"schema_version": "quiesce_result_v1"}},
        expected_adapter_id="alr_quiesce_fence_adapter_v1",
        expected_source_head=HEAD,
    )
    assert errors == ["sentinel"] and validated is None and sentinel_evidence == [HEAD]

    route = _route("S2_5B_FINAL")
    assert effects.validate_deploy_effect_binding({}, route, {}, {}, {}) == [
        "sentinel-binding"
    ]
    assert sentinel_binding


def test_generic_deploy_binding_still_rejects_unrouted_s2_receipts() -> None:
    # source-lane route(無 effect 節點)夾帶 S2 receipt:通用分支必以 unrouted 拒收。
    route = route_task({
        "task_shape": "audit", "surfaces": ["runtime_effect"], "risk": "high",
        "uncertainty": "low", "runtime_claim": True, "end_to_end_claim": False,
        "side_effect_class": "none", "task_prompt": "no effect admitted",
        "dirty_scope": [], "claim_inputs": {},
    })
    receipt = {"schema_version": "quiesce_result_v1", "adapter_id": "alr_quiesce_fence_adapter_v1"}
    errors = effects.validate_deploy_effect_binding({}, route, {}, {}, {"x": receipt})
    assert any("unrouted effect Adapter receipts" in error for error in errors)


def test_r1_claim_inventory_cross_checks_frozen_adapter_contracts() -> None:
    """R1:route claim inventory ↔ v3 矩陣 required_intent_fields / s2_4 contracts 常數。"""

    import aiml_gate_receipt_s2_2b as s2_2b_leaf
    import aiml_gate_receipt_s2_4_contracts as s2_4_contracts
    import aiml_gate_receipt_s2_5 as s2_5_leaf

    # 四個 s2_4 authorization claim key ↔ §9.1 四 trust profile(一一對應,封閉集)。
    profile_by_claim = {
        "s2_4_probe_authorization": "capability_probe",
        "s2_4_prepare_authorization": "prepare",
        "s2_4_install_authorization": "apply_aggregate",
        "s2_4_pg_migration_authorization": "pg_migration",
    }
    assert set(profile_by_claim.values()) == set(
        s2_4_contracts.S2_4_AUTHORIZATION_PROFILES
    )
    assert profile_by_claim.keys() <= (
        S2_CLAIM_KEYS_BY_STEP["S2_4_W6A_PROBE"]
        | S2_CLAIM_KEYS_BY_STEP["S2_4_W6A_PREPARE"]
        | S2_CLAIM_KEYS_BY_STEP["S2_4_W6B_APPLY"]
    )
    # W6B APPLY 雙 permit:aggregate + 窄 PG-migration(registry s2_4_install_adapter_v1)。
    assert {
        "s2_4_install_authorization", "s2_4_pg_migration_authorization",
    } <= S2_CLAIM_KEYS_BY_STEP["S2_4_W6B_APPLY"]

    # probe scope 常數 ↔ s2_4 contracts 的 evidence-class 判別子(封閉兩 scope)。
    scopes = {
        contract["probe_scope"]
        for contract in S2_EFFECT_STEPS.values() if "probe_scope" in contract
    }
    assert scopes == {
        scope for field, scope in
        s2_4_contracts.S2_4_EVIDENCE_CLASS_DISCRIMINATORS.values()
        if field == "probe_scope"
    } == {"PREPARE_SANDBOX", "INSTALLED_UNIT"}

    # v3 矩陣:adapter id / actor / independent postcheck node 與 route metadata 等值;
    # required_intent_fields 的上游 digest 欄 ↔ claim key 命名對應(`_digest` 尾碼;
    # pre_drill_attestation_digest ↔ s2_5a_running_attestation 屬非機械對應,錨定 registry
    # s2_5_final_attestation_adapter_v1 authority「the exact S2.5A s2_5_running_attestation_v1
    # digest」)。
    matrix = s2_5_leaf.AIML_COMPONENT_EFFECT_CLASS_MATRIX_V3
    start = matrix["ENGINE_SCANNER_SERVICE_START"]
    final = matrix["WATCHDOG_ROLLBACK_TEST"]
    assert S2_EFFECT_STEPS["S2_5A_START"]["adapter_id"] == start["adapter_id"]
    assert S2_EFFECT_STEPS["S2_5B_FINAL"]["adapter_id"] == final["adapter_id"]
    for step, row in (("S2_5A_START", start), ("S2_5B_FINAL", final)):
        assert S2_EFFECT_STEPS[step]["actor_node_id"] == row["actor_node_id"]
        assert S2_EFFECT_STEPS[step]["independent_postcheck_node_id"] == (
            row["independent_postcheck_node_id"]
        )
    assert "s2_4_install_effect_receipt_digest" in start["required_intent_fields"]
    assert "s2_4_install_effect_receipt" in S2_CLAIM_KEYS_BY_STEP["S2_5A_START"]
    assert "s2_1_drill_receipt_digest" in final["required_intent_fields"]
    assert "s2_1_drill_receipt" in S2_CLAIM_KEYS_BY_STEP["S2_5B_FINAL"]
    assert "pre_drill_attestation_digest" in final["required_intent_fields"]
    assert "s2_5a_running_attestation" in S2_CLAIM_KEYS_BY_STEP["S2_5B_FINAL"]

    # S2.2B:binding 契約的 schema/成功集直接等值 leaf 常數;PENDING 永不在成功集。
    contract = binding.S2_STEP_RECEIPT_CONTRACTS["S2_2B_RUNTIME_DONE"]
    assert contract["receipt_schema_version"] == s2_2b_leaf.S2_2B_SCHEMA_VERSION
    assert contract["success_statuses"] == {
        s2_2b_leaf.S2_2B_STATUS_RUNTIME_ATTESTED
    }
    assert s2_2b_leaf.S2_2B_STATUS_PENDING not in contract["success_statuses"]
    assert s2_2b_leaf.S2_2B_STATUS_SOURCE_PASS not in contract["success_statuses"]


def test_binding_success_sets_match_per_step_result_vocabularies() -> None:
    import agent_governance_alr_quiesce_fence as quiesce
    import agent_governance_pg_observer_bootstrap as observer

    assert binding.S2_STEP_RECEIPT_CONTRACTS["S2_0_APPLY"]["success_statuses"] <= (
        observer.RESULT_STATUSES
    )
    assert binding.S2_STEP_RECEIPT_CONTRACTS["S2_1_DRILL"]["success_statuses"] <= (
        quiesce.RESULT_STATUSES
    )
    # 每 step 的 receipt schema 與 route metadata result_schema_version 等值。
    for step, contract in binding.S2_STEP_RECEIPT_CONTRACTS.items():
        assert contract["receipt_schema_version"] == (
            S2_EFFECT_STEPS[step]["result_schema_version"]
        ), step
