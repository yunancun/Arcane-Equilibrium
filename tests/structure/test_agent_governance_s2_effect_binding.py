"""S2E.1:S2 effect closure binding sibling(agent_governance_s2_effect_binding)測試。

鏡 ``test_agent_governance_p0b_effect_adapter.py`` 的 closure 段:結構綁定測試把
receipt 實際重算的縫(``_receipt_validation_errors``,真身=中央 AIML 閘)monkeypatch
為 [],另以 sentinel 測試釘住真委派;R3 敘事型負例證明「route 通過但 adapter 拒」
(EXTERNAL_VERIFICATION_PENDING/RECOVERY_REQUIRED 永不換算 closure PASS)。
"""
from __future__ import annotations

import json
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
# CC-A1/CC-B:closure PASS 被 contract 明文阻塞的 step(今日 = S2_0_APPLY + S2_1_DRILL)
# 不進正例參數化。
PASSABLE_STEPS = sorted(
    step for step in S2_EFFECT_STEPS
    if binding.S2_STEP_RECEIPT_CONTRACTS[step]["closure_pass_blocked_reason"] is None
)
BLOCKED_STEPS = sorted(set(S2_EFFECT_STEPS) - set(PASSABLE_STEPS))
# 被阻塞 step 的「最佳可得 status」——用來證明即使拿出該 status 也不換算 PASS。
_BLOCKED_STEP_STATUS = {
    "S2_0_APPLY": "APPLIED_ROLLED_BACK_EXACT",
    "S2_1_DRILL": "QUIESCED_STATIC_GUARDS_HELD",
}


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
    """CC-A1/CC-B:兩個被阻塞 step 的「最佳可得 status」都是 disposable_local 邏輯證明。

    * S2.1 ``QUIESCED_STATIC_GUARDS_HELD`` ⇒ quiesce_result_v1 規定
      target_class=disposable_local / evidence_class=LOCAL_REPRODUCIBLE,boundary 無條件
      production_fence_performed=false。
    * S2.0 ``APPLIED_ROLLED_BACK_EXACT`` ⇒ pg_observer_bootstrap_result_v1 規定
      target_class=disposable_local / evidence_class=LOCAL_REPRODUCIBLE,且 status != APPLIED
      的 else 臂令 boundary.production_apply_performed=false。

    binding 絕不能在「明知未對 production 施加」的收據上簽發 runtime_contact PASS。
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


def test_s2_0_and_s2_1_blocked_dispositions_are_symmetric() -> None:
    """CC-A1:S2.0 不得只是「收窄成功集」——那仍讓一份拋棄式收據把 S2.0 記成 EFFECT_DONE。

    收窄後的 ``APPLIED_ROLLED_BACK_EXACT`` 依 schema 恆為 disposable_local/
    LOCAL_REPRODUCIBLE 且 production_apply_performed=false,而 binding 對成功 step 強制
    runtime_contact=true + CHANGED、wrapper 另蓋 environment ⇒ 與 S2.1(CC-B)同型缺陷。
    處置必須對稱:兩步一律空成功集 + typed blocked reason,並在模組內明文記錄對稱性。
    """

    contract = binding.S2_STEP_RECEIPT_CONTRACTS["S2_0_APPLY"]
    reason = contract["closure_pass_blocked_reason"]
    assert "APPLIED_ROLLED_BACK_EXACT is schema-pinned" in reason
    assert "target_class=disposable_local" in reason
    assert "production_apply_performed=false" in reason
    assert "out-of-band trusted-host verification" in reason
    assert "S2.4-W0a-authenticity-hardening.md" in reason
    for step in ("S2_0_APPLY", "S2_1_DRILL"):
        step_contract = binding.S2_STEP_RECEIPT_CONTRACTS[step]
        assert step_contract["success_statuses"] == frozenset(), step
        assert step_contract["closure_pass_blocked_reason"] is not None, step
    # 既有硬門的成功語義仍是 S2.0 收據 status 的權威(單一權威,不各自為政)——但那是
    # adapter/receipt 層的成功,不是 closure PASS。
    import agent_governance_pg_observer_bootstrap as observer

    assert "APPLIED_ROLLED_BACK_EXACT" in observer.RESULT_STATUSES
    # CC:「目前無記錄說明為何不對稱」⇒ 契約表必須明文記錄兩步的處置對稱性。
    source = (
        HELPERS / "agent_governance_s2_effect_binding.py"
    ).read_text(encoding="utf-8")
    assert "S2.0 與 S2.1 的處置對稱性" in source


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


def test_two_receipts_of_the_same_step_are_rejected(structural_receipts) -> None:
    """NEW-P2-D:``len(matching) != 1`` 的 count>1 方向(把守衛削成 ``< 1`` 即此處紅)。

    兩份同 step 的**合法**收據(同一 schema、同一 scope、僅 self_digest 相異)不得換算 PASS
    ——「恰一」是身分閘,不是「至少一」。
    """

    route = _route(GUARD_STEP)
    receipt = _receipt(GUARD_STEP)
    second = deepcopy(receipt)
    second["self_digest"] = "sha256:" + "c" * 64
    packet, fragments, evidence_by_id = _packet(GUARD_STEP, receipt)
    errors = binding.validate_s2_effect_binding(
        packet, route, fragments, evidence_by_id,
        {"effect": receipt, "effect-duplicate": second},
    )
    assert errors == [
        f"S2 closure PASS requires exactly one {GUARD_STEP} effect receipt"
    ]
    # 恰一份時同一輸入是綠的(證明紅的原因就是「第二份」)。
    assert binding.validate_s2_effect_binding(
        packet, route, fragments, evidence_by_id, {"effect": receipt}
    ) == []


def test_delegated_gate_exception_becomes_a_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NEW-P3-F:被委派謂詞拋例外時不得裸 traceback 逸出,必轉 typed error(fail-closed)。"""

    def _raiser(*_args, **_kwargs):
        raise TypeError("malformed packet")

    monkeypatch.setattr(binding, "_receipt_validation_errors", lambda *_a, **_k: [])
    monkeypatch.setitem(binding._DELEGATED_STEP_BINDINGS, "S2_0_APPLY", _raiser)
    route = _route("S2_0_APPLY")
    receipt = _receipt("S2_0_APPLY")
    packet, fragments, evidence_by_id = _packet("S2_0_APPLY", receipt)
    errors = binding.validate_s2_effect_binding(
        packet, route, fragments, evidence_by_id, {"effect": receipt}
    )
    assert (
        "S2 S2_0_APPLY delegated per-step closure gate raised TypeError: "
        "malformed packet"
    ) in errors


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
    成功集即 closure 拒收,永不換算 PASS。

    (CC-A1 後 S2.0 改由 blocked 分支拒;此處改用一個仍有可達成功頂點的 step,才驗得到
    「成功集判定」那一條分支。)
    """

    route = _route("S2_4_W6B_APPLY")
    assert [
        node["id"] for node in route["nodes"] if node["kind"] == "effect_adapter"
    ] == [routing.S2_4_INSTALL_ADAPTER_ID]
    receipt = _receipt("S2_4_W6B_APPLY")
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
    assert validated is None
    assert (
        "S2 S2_5A_START receipt status 'SOURCE_SIMULATION_PASS' is not a "
        "closure-admissible production success (RECOVERY_REQUIRED/"
        "EXTERNAL_VERIFICATION_PENDING/source-simulation never convert to PASS)"
    ) in errors


# --------------------------------------------------------------------------- #
# E2-P1-1 / E4:守衛的 targeted negative(每條 typed 拒絕分支各釘完整錯誤字串)
# --------------------------------------------------------------------------- #
GUARD_STEP = "S2_5A_START"


def _guard_case(step: str = GUARD_STEP):
    route = _route(step)
    receipt = _receipt(step)
    packet, fragments, evidence_by_id = _packet(step, receipt)
    return route, receipt, packet, fragments, evidence_by_id


def test_route_must_select_exactly_the_admitted_step_adapter_node(
    structural_receipts,
) -> None:
    expected = "S2 closure route did not select exactly the admitted step adapter node"
    route, receipt, packet, fragments, evidence_by_id = _guard_case()
    # 零 effect 節點。
    stripped = deepcopy(route)
    stripped["nodes"] = [
        node for node in stripped["nodes"] if node["kind"] != "effect_adapter"
    ]
    assert expected in binding.validate_s2_effect_binding(
        packet, stripped, fragments, evidence_by_id, {"effect": receipt}
    )
    # 兩個 effect 節點(其一是別的 adapter)。
    doubled = deepcopy(route)
    doubled["nodes"].append({
        "id": routing.S2_4_INSTALL_ADAPTER_ID, "kind": "effect_adapter",
        "mandatory": True, "requires": [], "reason": "smuggled",
        "effect_step": "S2_4_W6B_APPLY",
    })
    assert expected in binding.validate_s2_effect_binding(
        packet, doubled, fragments, evidence_by_id, {"effect": receipt}
    )
    # 恰一節點但 adapter id 是別人的。
    relabelled = deepcopy(route)
    for node in relabelled["nodes"]:
        if node["kind"] == "effect_adapter":
            node["id"] = routing.S2_4_INSTALL_ADAPTER_ID
    assert expected in binding.validate_s2_effect_binding(
        packet, relabelled, fragments, evidence_by_id, {"effect": receipt}
    )


def test_route_adapter_node_effect_step_must_equal_the_claim_admission(
    structural_receipts,
) -> None:
    route, receipt, packet, fragments, evidence_by_id = _guard_case()
    # S2.5A/S2.5B 共用 adapter id 之外的唯一區別就是 effect_step;把它改標成另一 step。
    tampered = deepcopy(route)
    for node in tampered["nodes"]:
        if node["kind"] == "effect_adapter":
            node["effect_step"] = "S2_5B_FINAL"
    assert "S2 closure route adapter node step differs from claim admission" in (
        binding.validate_s2_effect_binding(
            packet, tampered, fragments, evidence_by_id, {"effect": receipt}
        )
    )


def test_receipt_adapter_id_must_equal_the_step_adapter(structural_receipts) -> None:
    receipt = _receipt("S2_5A_START")
    receipt["adapter_id"] = routing.S2_5_FINAL_ATTESTATION_ADAPTER_ID
    evidence = binding.build_s2_effect_evidence(receipt)
    errors, validated = binding.validate_s2_effect_evidence(
        evidence, expected_source_head=HEAD
    )
    assert validated is None
    assert "S2 effect receipt adapter_id does not match the step adapter" in errors


@pytest.mark.parametrize("count", [0, 2])
def test_exactly_one_independent_ops_postcheck_is_required(
    structural_receipts, count: int,
) -> None:
    route, receipt, packet, fragments, evidence_by_id = _guard_case()
    contract = binding.S2_STEP_RECEIPT_CONTRACTS[GUARD_STEP]
    expected = (
        "S2 closure requires exactly one independent ops_postcheck runtime evidence "
        f"of kind {contract['postcheck_kind']}"
    )
    if count == 0:
        fragments["ops_postcheck"] = {"evidence_refs": []}
    else:
        second = _postcheck(GUARD_STEP, receipt, "pc2")
        evidence_by_id["pc2"] = second
        fragments["ops_postcheck"]["evidence_refs"].append("pc2")
    assert expected in binding.validate_s2_effect_binding(
        packet, route, fragments, evidence_by_id, {"effect": receipt}
    )


def test_ops_postcheck_kind_whitelist_rejects_a_foreign_artifact(
    structural_receipts,
) -> None:
    route, receipt, packet, fragments, evidence_by_id = _guard_case()
    evidence_by_id["pc"]["kind"] = "ops_preflight_v1"
    assert (
        "S2 closure requires exactly one independent ops_postcheck runtime evidence "
        "of kind ops_postcheck_v1"
    ) in binding.validate_s2_effect_binding(
        packet, route, fragments, evidence_by_id, {"effect": receipt}
    )


def test_ops_postcheck_payload_must_cross_bind_the_receipt_self_digest(
    structural_receipts,
) -> None:
    route, receipt, packet, fragments, evidence_by_id = _guard_case()
    evidence_by_id["pc"]["payload"]["effect_receipt_digest"] = "sha256:" + "0" * 64
    assert (
        "S2 ops_postcheck payload.effect_receipt_digest is not bound to the effect "
        "receipt self_digest"
    ) in binding.validate_s2_effect_binding(
        packet, route, fragments, evidence_by_id, {"effect": receipt}
    )


def test_successful_effect_requires_runtime_contact_and_changed_disposition(
    structural_receipts,
) -> None:
    route, receipt, packet, fragments, evidence_by_id = _guard_case()
    without_contact = deepcopy(packet)
    without_contact["side_effects"] = {"runtime_contact": False}
    assert "S2 successful effect must record runtime_contact=true" in (
        binding.validate_s2_effect_binding(
            without_contact, route, fragments, evidence_by_id, {"effect": receipt}
        )
    )
    unchanged = deepcopy(packet)
    unchanged["disposition"] = "UNCHANGED"
    assert "S2 successful effect closure disposition must be CHANGED" in (
        binding.validate_s2_effect_binding(
            unchanged, route, fragments, evidence_by_id, {"effect": receipt}
        )
    )


def test_probe_scope_fallthrough_is_fail_closed() -> None:
    """probe 兩 step 共用 schema:scope 缺失或第三值一律導不出 step(絕不猜)。"""

    assert binding.s2_effect_step_for_receipt(
        {"schema_version": "s2_4_capability_probe_effect_receipt_v1"}
    ) is None
    assert binding.s2_effect_step_for_receipt({
        "schema_version": "s2_4_capability_probe_effect_receipt_v1",
        "probe_scope": "SOME_THIRD_SCOPE",
    }) is None
    assert binding.s2_effect_step_for_receipt("not-a-dict") is None
    assert binding.s2_effect_step_for_receipt({"schema_version": "unknown_v1"}) is None
    # 兩個合法 scope 仍各自唯一導出。
    for step, scope in (
        ("S2_4_W6A_PROBE", "PREPARE_SANDBOX"), ("S2_4_W6B_PROBE", "INSTALLED_UNIT"),
    ):
        assert binding.s2_effect_step_for_receipt({
            "schema_version": "s2_4_capability_probe_effect_receipt_v1",
            "probe_scope": scope,
        }) == step


def test_binding_rejects_an_invalid_or_absent_claim_admission(
    structural_receipts,
) -> None:
    route, receipt, packet, fragments, evidence_by_id = _guard_case()
    # selector 在場但 claim set 不 exact → route 層 typed ValueError 被轉成 closure error。
    invalid = deepcopy(route)
    invalid["task_facts"]["claim_inputs"].pop("s2_5a_start_permit")
    errors = binding.validate_s2_effect_binding(
        packet, invalid, fragments, evidence_by_id, {"effect": receipt}
    )
    assert len(errors) == 1
    assert errors[0].startswith("S2 closure route is invalid: ")
    assert "requires exact claim_inputs" in errors[0]
    # selector 缺席(source lane)→ 無 admitted step。
    assert binding.validate_s2_effect_binding(
        packet, {"task_facts": {"claim_inputs": {}}, "nodes": []},
        fragments, evidence_by_id, {"effect": receipt},
    ) == ["S2 closure route did not admit an S2 effect step"]


def test_evidence_wrapper_rejects_a_missing_or_underivable_receipt() -> None:
    assert binding.validate_s2_effect_evidence(
        {"receipt": None}, expected_source_head=HEAD
    ) == (["S2 effect evidence missing canonical receipt payload"], None)
    errors, validated = binding.validate_s2_effect_evidence(
        {"receipt": {"schema_version": "s2_4_capability_probe_effect_receipt_v1"}},
        expected_source_head=HEAD,
    )
    assert validated is None
    assert errors == [
        "S2 effect receipt step is not derivable from schema_version/probe_scope"
    ]
    with pytest.raises(ValueError, match="S2 effect receipt step is not derivable"):
        binding.build_s2_effect_evidence({"schema_version": "not_an_s2_receipt_v1"})


def test_naive_or_malformed_timestamps_are_typed_rejections(structural_receipts) -> None:
    """_parse_time 要求時區:naive/畸形時間戳走 typed 拒絕,不是裸例外也不是靜默通過。"""

    route, receipt, packet, fragments, evidence_by_id = _guard_case()
    naive = deepcopy(evidence_by_id)
    naive["pc"] = deepcopy(evidence_by_id["pc"])
    naive["pc"]["observed_at"] = "2026-07-28T10:06:00"  # 無時區
    assert "S2 ops_postcheck timestamps are invalid" in (
        binding.validate_s2_effect_binding(
            packet, route, fragments, naive, {"effect": receipt}
        )
    )
    malformed = deepcopy(packet)
    malformed["authority_refs"][0]["observed_at"] = "not-a-timestamp"
    assert "S2 S2_5A_START intent authority timestamp is invalid" in (
        binding.validate_s2_effect_binding(
            malformed, route, fragments, evidence_by_id, {"effect": receipt}
        )
    )
    with pytest.raises(ValueError, match="timezone is required"):
        binding._parse_time("2026-07-28T10:06:00")


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


def test_self_digest_recompute_covers_the_central_gate_gap_schemas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CC-C #1:中央閘無 self_digest 反偽造分支的 schema,由本模組在同一縫補上。"""

    import aiml_gate_receipt_schema_core as core
    import aiml_gate_receipt_validator as central

    monkeypatch.setattr(central, "validate_aiml_artifact", lambda *_a, **_k: [])
    forged = {
        "schema_version": "s2_4_prepare_effect_receipt_v1",
        "prepare_id": "s2-4-prepare-0001",
        "self_digest": "sha256:" + "0" * 64,
    }
    assert binding._receipt_validation_errors(forged, now=T_DONE) == [
        "receipt self_digest does not bind the canonical receipt "
        "(the central AIML gate has no self_digest recompute for this schema)"
    ]
    honest = dict(forged)
    honest["self_digest"] = core.artifact_self_digest(honest)
    assert binding._receipt_validation_errors(honest, now=T_DONE) == []
    # 中央閘已有自己分支的 schema 不由本模組重複執法(避免兩處各自為政)。
    assert binding._receipt_validation_errors(
        {"schema_version": "quiesce_result_v1", "self_digest": "sha256:" + "0" * 64},
        now=T_DONE,
    ) == []


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


# --------------------------------------------------------------------------- #
# 契約漂移守衛(P2):欄位名/schema 版本/claim 覆蓋今日全對,但先前無任何守衛
# --------------------------------------------------------------------------- #
def _schema_of(schema_version: str) -> dict:
    import aiml_gate_receipt_schema_core as core

    return json.loads(
        (core.SCHEMA_DIR / core.SCHEMA_FILES[schema_version]).read_text(encoding="utf-8")
    )


def _resolve_node(node) -> dict | None:
    """解析 anyOf/allOf/oneOf 包裹;內嵌別的 typed artifact 時改以該 artifact 的正本 schema 為準
    (巢狀處常只重述 schema_version/self_digest 兩欄,例:ingestion receipt 的
    s2_5_final_attestation 錨)。"""

    import aiml_gate_receipt_schema_core as core

    if not isinstance(node, dict):
        return None
    properties = node.get("properties")
    if isinstance(properties, dict):
        const = (properties.get("schema_version") or {}).get("const")
        if const in core.SCHEMA_FILES:
            return _schema_of(const)
        return node
    for key in ("anyOf", "allOf", "oneOf"):
        for branch in node.get(key, []):
            resolved = _resolve_node(branch)
            if resolved is not None:
                return resolved
    return None


def _schema_has_field(schema: dict, dotted: str) -> bool:
    node = _resolve_node(schema)
    parts = dotted.split(".")
    for index, part in enumerate(parts):
        properties = node.get("properties") if isinstance(node, dict) else None
        if not isinstance(properties, dict) or part not in properties:
            return False
        if index == len(parts) - 1:
            return True
        node = _resolve_node(properties[part])
    return False


def test_receipt_contract_field_names_exist_in_the_real_schemas() -> None:
    """契約表的每個 receipt 欄位名必真存在於該 schema(防欄位改名後綁定靜默變 None)。"""

    field_keys = (
        "status_field", "started_field", "observed_field", "expiry_field", "host_field",
        "intent_id_field", "intent_digest_field",
    )
    for step, contract in binding.S2_STEP_RECEIPT_CONTRACTS.items():
        schema = _schema_of(contract["receipt_schema_version"])
        for key in field_keys:
            dotted = contract.get(key)
            if dotted is None:
                continue
            assert _schema_has_field(schema, dotted), (step, key, dotted)
        for claim_key, dotted in contract["claim_receipt_bindings"].items():
            assert _schema_has_field(schema, dotted), (step, claim_key, dotted)


def test_claim_bindings_and_declaration_only_claims_cover_the_route_inventory() -> None:
    """E2-P2-1:空/部分綁定必須是刻意的——bindings ∪ declaration_only ∪ {selector} 恰等於
    route claim inventory,任一新 claim 未分類即紅。"""

    for step, contract in binding.S2_STEP_RECEIPT_CONTRACTS.items():
        bound = set(contract["claim_receipt_bindings"])
        declared = set(contract["declaration_only_claims"])
        assert not (bound & declared), (step, sorted(bound & declared))
        assert bound | declared | {S2_EFFECT_SELECTION_CLAIM_KEY} == set(
            S2_CLAIM_KEYS_BY_STEP[step]
        ), step
    # 最高權限那一步的雙 permit 必須真綁到 receipt 欄位(E3-M-2),不得只作宣告。
    apply_bindings = binding.S2_STEP_RECEIPT_CONTRACTS["S2_4_W6B_APPLY"][
        "claim_receipt_bindings"
    ]
    assert apply_bindings["s2_4_install_authorization"] == "aggregate_authorization_digest"
    assert apply_bindings["s2_4_pg_migration_authorization"] == "pg_authorization_digest"
    assert apply_bindings["s2_4_prepare_effect_receipt"] == "prepare_result_digest"
    for step in ("S2_4_W6A_PROBE", "S2_4_W6B_PROBE"):
        assert binding.S2_STEP_RECEIPT_CONTRACTS[step]["claim_receipt_bindings"][
            "s2_4_probe_authorization"
        ] == "authorization_digest"
    assert binding.S2_STEP_RECEIPT_CONTRACTS["S2_4_W6A_PREPARE"][
        "claim_receipt_bindings"
    ]["s2_4_prepare_authorization"] == "authorization_digest"
    # 兩個 probe step 共用 schema 但 claim inventory 不同 → 契約子物件不得是同一個 dict。
    w6a = binding.S2_STEP_RECEIPT_CONTRACTS["S2_4_W6A_PROBE"]
    w6b = binding.S2_STEP_RECEIPT_CONTRACTS["S2_4_W6B_PROBE"]
    assert w6a["claim_receipt_bindings"] is not w6b["claim_receipt_bindings"]
    assert w6a["declaration_only_claims"] != w6b["declaration_only_claims"]


def test_route_metadata_schema_versions_equal_the_registry_schema_paths() -> None:
    """9 個 step 的 intent/result/rollback schema version ↔ registry `*_schema_path` 等值。"""

    registry = json.loads(
        (ROOT / ".codex/agent_registry_v1.json").read_text(encoding="utf-8")
    )
    adapters = registry["effect_adapters"]
    for step, contract in S2_EFFECT_STEPS.items():
        entry = adapters[contract["adapter_id"]]
        # s2_4 家族兩者皆有:receipt_schema_path 才是 effect receipt(result_schema_path 是
        # PREPARE bundle / install step result 等另一種 artifact)。
        result_path = entry.get("receipt_schema_path") or entry["result_schema_path"]
        expected = {
            "result_schema_version": result_path,
            "intent_schema_version": entry.get("intent_schema_path"),
            "rollback_schema_version": entry.get("rollback_schema_path"),
        }
        for key, path in expected.items():
            if key not in contract:
                assert path is None or key == "result_schema_version", (step, key)
                continue
            assert path is not None, (step, key)
            assert contract[key] == Path(path).name.removesuffix(".schema.json"), (
                step, key,
            )
            assert (ROOT / path).is_file(), path


def test_central_gate_self_digest_gap_list_is_pinned_to_the_gate_source() -> None:
    """CC-C #1:中央閘「無 schema_version 專屬分支」的清單必與其原始碼一致(漂移即紅)。"""

    gate_source = (
        ML_ROOT / "aiml_gate_receipt_validator.py"
    ).read_text(encoding="utf-8")
    for schema_version in binding.S2_RECEIPT_SCHEMA_VERSIONS:
        has_branch = f'schema_version == "{schema_version}"' in gate_source
        in_gap = schema_version in binding._CENTRAL_GATE_SELF_DIGEST_GAP_SCHEMAS
        assert has_branch is not in_gap, schema_version


def test_s2_receipts_get_a_distinct_execution_attestation_identity() -> None:
    """E3-M-1:S2 收據無 receipt_digest 欄位,舊碼把它們全塌成 ("...", "") 同一身分。"""

    from agent_governance_execution_attestation import validate_execution_attestations

    receipts = {
        "w6a": _receipt("S2_4_W6A_PROBE"),
        "w6b": _receipt("S2_4_W6B_PROBE"),
        "install": _receipt("S2_4_W6B_APPLY"),
    }
    receipts["w6b"]["self_digest"] = "sha256:" + "d" * 64  # 與 w6a 同摘要,scope 不同
    errors = validate_execution_attestations(
        gate_verdict="PASS", captures={"waves": {}, "telemetry": {}},
        observation_artifacts={}, effect_receipts=receipts, verifier=None,
    )
    # 三份收據 = 三個獨立身分(舊碼只會產生一條錯誤)。
    assert len(errors) == 3, errors
    assert all("lacks out-of-band execution attestation" in error for error in errors)
    # digest 取自 self_digest 而非空字串。
    assert not any("<missing>" in error for error in errors), errors

    seen: list[tuple[str, str]] = []

    def verifier(kind: str, digest: str, _artifact: dict) -> bool:
        seen.append((kind, digest))
        return True

    assert validate_execution_attestations(
        gate_verdict="PASS", captures={"waves": {}, "telemetry": {}},
        observation_artifacts={}, effect_receipts=receipts, verifier=verifier,
    ) == []
    assert len(seen) == 3
    assert {digest for _kind, digest in seen} == {
        receipt["self_digest"] for receipt in receipts.values()
    }
