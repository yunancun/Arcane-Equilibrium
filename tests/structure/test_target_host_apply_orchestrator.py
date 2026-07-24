"""S1 Wave B1: intent-derived target-host effect APPLY orchestrator.

Proves the admitted-intent applier path end to end on Mac (structurally):
- a VALID intent + a properly-attested governed capture, through
  apply_target_host_probe_effect (with an injected "as-if trade-core" probe
  output), produces a strictly-valid target_host_effect_result_v1 and a valid
  aiml_landing_session_attempt_v1;
- a distinct verifier (!= applier, distinct capture) upgrades PROVISIONAL -> BINDING
  by threading its OWN residue observation through attach_independent_postcheck;
- BYPASS-NEGATIVES all fail closed: invalid intent (const/ttl/throwaway_root/expiry),
  applier==postcheck (self-verify), a bare-capture / STRUCTURAL_ONLY receipt is not
  closure-admissible, a bare user-env probe with NO validated intent cannot yield an
  admissible effect result, and verifier==applier (or a reused applier capture) fails
  the distinct-verifier attach.

Mac-structural: the real run_target_host_probe SKIPs off-target via
target_host_available(); we inject a deterministic probe_runner returning a
pre-built attested probe output, and separately assert the SKIP is real.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_target_host_probe as th  # noqa: E402
import agent_governance_target_host_choice as thc  # noqa: E402
import agent_governance_target_host_effects as tfx  # noqa: E402
import agent_governance_target_host_apply as apply  # noqa: E402
import agent_governance_target_host_child_apply as thchild  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
from target_host_capture_support import (  # noqa: E402
    install_test_operator_profile,
    signed_observation_capture,
    typed_intent,
)


HEAD = subprocess.check_output(
    ["git", "rev-parse", "HEAD"],
    cwd=ROOT,
    text=True,
).strip()
OBS = "2026-07-23T12:00:00+00:00"
NOW = "2026-07-23T12:05:00+00:00"
LATER = "2026-07-23T12:06:00+00:00"
D = "sha256:" + "1" * 64
OWNED = "helper_scripts/maintenance_scripts/agent_governance_target_host_apply.py"
APPLIER = "s16b_apply_actor"
VERIFIER = "s16b_independent_verifier"
CLEAN = {"units_gone": True, "cgroup_gone": True, "netns_gone": True, "temp_gone": True}

CAP: dict = {}
TEST_INTENT: dict = {}
CAP_DIGEST = ""
VERIFIER_CAP = "sha256:" + "9" * 64

DEP = {
    "runtime_candidate_receipt_a_digest": "sha256:" + "a" * 64,
    "runtime_candidate_receipt_b_digest": "sha256:" + "b" * 64,
    "runtime_candidate_comparison_digest": "sha256:" + "c" * 64,
    "effect_seams_ready_receipt_digest": "sha256:" + "d" * 64,
    "pg_readonly_identity_receipt_digest": "sha256:" + "e" * 64,
}


@pytest.fixture(autouse=True)
def _signed_target_host_capture(tmp_path, monkeypatch):
    global CAP, CAP_DIGEST, TEST_INTENT
    private_key = install_test_operator_profile(tmp_path, monkeypatch)
    TEST_INTENT = typed_intent(
        applier_node=APPLIER,
        postcheck_node=VERIFIER,
        now=__import__("datetime").datetime.fromisoformat(OBS),
    )
    CAP = signed_observation_capture(
        ROOT,
        private_key=private_key,
        intent=TEST_INTENT,
        source_head=HEAD,
        mode="preflight",
        node_id="ops_preflight",
    )
    CAP_DIGEST = CAP["record_digest"]


def _intent(**overrides) -> dict:
    intent = copy.deepcopy(TEST_INTENT)
    intent.update(overrides)
    return intent


def _probe_output(
    *,
    pg_mode: str = th.PG_MODE_REAL,
    evidence_class: str | None = None,
    independent_postcheck_attached: bool = False,
    capture_digest: str | None = None,
) -> dict:
    # 一份「as-if trade-core」的 run_target_host_probe 輸出:applier 自跑 → independent_postcheck DEFERRED。
    return {
        "host_identity": thc._structural_host_identity(),
        "pg_identity_mode": pg_mode,
        "fixed_path_seams": th.synthesize_fixed_path_seams(
            pg_mode, evidence_marker=th.EVIDENCE_ATTESTED,
            independent_postcheck_attached=independent_postcheck_attached,
        ),
        "target_host_capture_digest": capture_digest or CAP_DIGEST,
        "evidence_class": evidence_class or th.EVIDENCE_ATTESTED,
    }


def _runner(**_kwargs) -> dict:
    return _probe_output()


def _apply(**overrides) -> dict:
    kwargs = {
        "source_head": HEAD,
        "approved_by": "operator",
        "approved_at": "2026-07-23T12:01:00+00:00",
        "capture_digest": CAP_DIGEST,
        "capture_artifact": CAP,
        "verifier_node_id": VERIFIER,
        "now": NOW,
        "dependency_receipts": DEP,
        "probe_runner": _runner,
    }
    intent = overrides.pop("intent", None) or _intent()
    kwargs.update(overrides)
    return apply.apply_target_host_probe_effect(intent, **kwargs)


def _landing_kwargs(result: dict, **overrides) -> dict:
    kwargs = dict(
        effect_result=result,
        session_id="S1.6B",
        cohort_epoch="epoch-1",
        owner="E1",
        source={"branch": "agent/aiml-s1-formal-closure", "worktree": "/w", "checkpoint_head": "b" * 40},
        lease={
            "lease_id": "lease-1", "epoch": 1,
            "acquired_at": "2026-07-23T11:00:00+00:00",
            "heartbeat_at": "2026-07-23T11:30:00+00:00",
            "expires_at": "2026-07-23T13:00:00+00:00",
        },
        landing_scope_id=D,
        work_package_id="AIML-S1.6B-TARGET-HOST-APPLY",
        direct_interfaces=["agent_governance_target_host_apply"],
        owned_paths=[OWNED],
        dependency_generations=[{
            "session_id": "S1.5", "schema_version": "effect_seams_ready_receipt_v1",
            "receipt_digest": D,
        }],
        bootstrap={
            "task_id": "AIML-S1-6B-APPLY", "task_contract_digest": D,
            "dag_digest": D, "context_artifact_digest": D,
        },
        ci_classifier_digest=D,
        effect_classification_digest=D,
        closure_packet_digest=D,
        created_at=NOW,
    )
    kwargs.update(overrides)
    return kwargs


def _landing(result: dict, **overrides) -> dict:
    return apply.build_target_host_landing_attempt(**_landing_kwargs(result, **overrides))


# --------------------------------------------------------------------------- #
# positive: valid intent + attested capture -> valid result + valid landing attempt
# --------------------------------------------------------------------------- #
def test_apply_produces_valid_effect_result() -> None:
    result = _apply()
    assert result["schema_version"] == "target_host_effect_result_v1"
    assert result["adapter_id"] == apply.TARGET_HOST_ADAPTER_ID
    assert result["effect_status"] == "TARGET_HOST_DISPOSABLE_PROBE_PASS"
    # applier / verifier 節點由 VALIDATED intent 派生。
    assert result["applier_node_id"] == APPLIER
    assert result["postcheck_verifier_node_id"] == VERIFIER
    assert result["intent_id"] == _intent()["intent_id"]
    assert result["intent_digest"] == _intent()["self_digest"]
    # applier 自跑:independent_postcheck DEFERRED -> binding PROVISIONAL(尚未 distinct-verified)。
    assert result["choice_receipt"]["selection"]["binding"] == th.BINDING_PROVISIONAL
    # 嚴格 lane(§13 C4)通過。
    assert tfx.validate_target_host_effect_result(
        result, now=NOW, expected_source_head=HEAD, require_success=True
    ) == []
    # 中央離線閘(strict on the dedicated result)亦通過。
    assert validator.validate_aiml_artifact(result, now=NOW) == []


def test_apply_emits_valid_landing_attempt() -> None:
    result = apply.attach_distinct_verifier_postcheck(
        _apply(), verifier_node_id=VERIFIER, verifier_capture_digest=VERIFIER_CAP,
        residue_observation=CLEAN, now=LATER,
    )
    attempt = _landing(result)
    assert attempt["schema_version"] == "aiml_landing_session_attempt_v1"
    assert attempt["adapter_id"] == apply.TARGET_HOST_ADAPTER_ID
    assert attempt["actor_node"] == APPLIER
    assert attempt["independent_postcheck_node"] == VERIFIER
    assert attempt["required_effects"][0]["adapter_id"] == apply.TARGET_HOST_ADAPTER_ID
    assert attempt["closure_binding"]["effect_receipt_digest"] == result["receipt_digest"]
    assert attempt["closure_binding"]["effect_adapter_id"] == apply.TARGET_HOST_ADAPTER_ID
    # 走中央 validator 的 landing-attempt 分支(非 S0.3 硬編路徑)。
    assert validator.validate_aiml_artifact(attempt, now=NOW) == []


# --------------------------------------------------------------------------- #
# distinct verifier (decision #5): applier != verifier; upgrades to BINDING
# --------------------------------------------------------------------------- #
def test_distinct_verifier_upgrades_to_binding() -> None:
    result = _apply()
    upgraded = apply.attach_distinct_verifier_postcheck(
        result, verifier_node_id=VERIFIER, verifier_capture_digest=VERIFIER_CAP,
        residue_observation=CLEAN, now=LATER,
    )
    assert upgraded["choice_receipt"]["selection"]["binding"] == th.BINDING_BINDING
    assert upgraded["choice_receipt"]["selection"]["pending_seams"] == []
    assert tfx.validate_target_host_effect_result(
        upgraded, now=NOW, expected_source_head=HEAD, require_success=True
    ) == []


def test_distinct_verifier_rejects_self_verify() -> None:
    result = _apply()
    with pytest.raises(apply.TargetHostApplyError, match="differ from the applier node"):
        apply.attach_distinct_verifier_postcheck(
            result, verifier_node_id=APPLIER, verifier_capture_digest=VERIFIER_CAP,
            residue_observation=CLEAN, now=LATER,
        )


def test_distinct_verifier_rejects_reused_applier_capture() -> None:
    # decision #7:capture 也須相異;裸重用 applier 的 capture digest 一律拒。
    result = _apply()
    with pytest.raises(apply.TargetHostApplyError, match="differ from the applier capture"):
        apply.attach_distinct_verifier_postcheck(
            result, verifier_node_id=VERIFIER, verifier_capture_digest=CAP_DIGEST,
            residue_observation=CLEAN, now=LATER,
        )


def test_distinct_verifier_rejects_unclean_residue() -> None:
    result = _apply()
    dirty = dict(CLEAN, temp_gone=False)
    with pytest.raises(th.TargetHostProbeError, match="all clean"):
        apply.attach_distinct_verifier_postcheck(
            result, verifier_node_id=VERIFIER, verifier_capture_digest=VERIFIER_CAP,
            residue_observation=dirty, now=LATER,
        )


# --------------------------------------------------------------------------- #
# BYPASS-NEGATIVES: invalid intent (const / ttl / throwaway_root / expiry / self-verify)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("overrides", [
    {"non_root_uid": False},
    {"user_scope_only": False},
    {"risk": "low"},
    {"ttl_seconds": 3601},
    {"throwaway_root": "/opt/aiml/probe"},
    {"applier_node_id": "same", "postcheck_node_id": "same"},
    {"created_at": "2026-07-23T11:00:00+00:00", "expires_at": "2026-07-23T12:00:00+00:00"},  # expired
])
def test_apply_rejects_invalid_intent(overrides) -> None:
    verifier = overrides.get("postcheck_node_id", VERIFIER)
    with pytest.raises(apply.TargetHostApplyError):
        _apply(intent=_intent(**overrides), verifier_node_id=verifier)


def test_validate_probe_intent_flags_expiry_and_passes_fresh() -> None:
    assert apply.validate_probe_intent(_intent(), now=NOW) == []
    expired = _intent(created_at="2026-07-23T11:00:00+00:00", expires_at="2026-07-23T12:00:00+00:00")
    errors = apply.validate_probe_intent(expired, now=NOW)
    assert any("already expired" in e for e in errors)


def test_apply_rejects_verifier_not_matching_intent_postcheck() -> None:
    with pytest.raises(apply.TargetHostApplyError, match="postcheck_node_id"):
        _apply(verifier_node_id="some_other_node")


# --------------------------------------------------------------------------- #
# BYPASS-NEGATIVES: bare-capture / STRUCTURAL_ONLY receipts are not closure-admissible
# --------------------------------------------------------------------------- #
def test_apply_rejects_bare_capture_no_governed_artifact() -> None:
    # attested PASS choice 但無內嵌 governed command_capture_v2 → 嚴格 lane 拒 → applier fail-closed。
    with pytest.raises(apply.TargetHostApplyError, match="non-admissible"):
        _apply(capture_digest=None, capture_artifact=None)


def test_apply_rejects_structural_only_probe_output() -> None:
    # STRUCTURAL_ONLY 探針輸出 -> choice status=FAIL -> effect FAILED,require_success 拒。
    with pytest.raises(apply.TargetHostApplyError):
        _apply(probe_runner=lambda **_kw: _probe_output(evidence_class=th.EVIDENCE_STRUCTURAL))


# --------------------------------------------------------------------------- #
# intent-derived authorization boundary (fixed decision #4)
# --------------------------------------------------------------------------- #
def test_intent_derived_authorization_boundary() -> None:
    # (1) 唯有 intent-validated applier 路徑產得出 closure-admissible 的 dedicated effect result。
    result = _apply()
    assert tfx.validate_target_host_effect_result(
        result, now=NOW, expected_source_head=HEAD, require_success=True
    ) == []
    # (2) 一份「裸 env-var 探針」的原始輸出(即 run_target_host_probe 回傳的 dict)不是 dedicated effect
    #     result:沒有 intent 綁定 / adapter_id / receipt_digest。缺 intent-validated applier 封裝 = 不可採信。
    raw_probe_output = _probe_output()
    errors = tfx.validate_target_host_effect_result(
        raw_probe_output, now=NOW, expected_source_head=HEAD, require_success=True
    )
    assert errors  # a raw probe output is NOT a target_host_effect_result_v1
    assert raw_probe_output.get("adapter_id") is None
    assert raw_probe_output.get("intent_id") is None


def test_bare_env_var_probe_skips_on_mac_never_fakes() -> None:
    # 誠實界線:即使裸設 AIML_TARGET_HOST_PROBE=1,Mac 上 run_target_host_probe 仍乾淨 SKIP(非 linux/
    # 無 systemd-run),絕不合成 kernel 事實。真效果只在被授權的 target host 由 admitted-intent applier 驅動。
    prior = os.environ.get("AIML_TARGET_HOST_PROBE")
    os.environ["AIML_TARGET_HOST_PROBE"] = "1"
    try:
        if th.target_host_available():
            pytest.skip("on a real target host; the Mac-SKIP boundary does not apply here")
        with pytest.raises(th.TargetHostUnavailableError):
            th.run_target_host_probe(
                throwaway_root="/run/user/1000/aiml-probe-xyz",
                pg_readonly_identity_receipt_digest=DEP["pg_readonly_identity_receipt_digest"],
            )
    finally:
        if prior is None:
            os.environ.pop("AIML_TARGET_HOST_PROBE", None)
        else:
            os.environ["AIML_TARGET_HOST_PROBE"] = prior


def test_injected_runner_never_opens_the_parent_process_gate() -> None:
    # P1(Codex)修復:applier 不再於 **parent** 行程翻開 AIML_TARGET_HOST_PROBE。注入 runner 路徑為
    # in-process 直呼,期間 parent env 從未被設閘,結束後亦然(舊實作會在此窗口對整個 parent 行程開閘)。
    assert "AIML_TARGET_HOST_PROBE" not in os.environ
    seen = {}

    def _spy_runner(**_kwargs):
        seen["gate"] = os.environ.get("AIML_TARGET_HOST_PROBE")
        return _probe_output()

    _apply(probe_runner=_spy_runner)
    assert seen["gate"] is None  # 注入 runner 執行期間 parent env 從未持有授權閘
    assert "AIML_TARGET_HOST_PROBE" not in os.environ  # 之後亦然


def test_real_runner_delegates_to_isolated_child_and_keeps_parent_gate_clean(monkeypatch) -> None:
    # 真 runner(預設 th.run_target_host_probe)由 VALIDATED intent 派生一張 authorization capsule,委派給
    # 隔離子行程 run_probe_via_child;parent 行程從不翻開授權閘。以 fake child 捕獲 capsule 驗其綁定。
    assert "AIML_TARGET_HOST_PROBE" not in os.environ
    captured = {}

    def _fake_child(capsule, **_kw):
        captured["capsule"] = capsule
        captured["gate_during"] = os.environ.get("AIML_TARGET_HOST_PROBE")
        return _probe_output()

    monkeypatch.setattr(thchild, "run_probe_via_child", _fake_child)
    permit = {"authorization_digest": "sha256:" + "7" * 64}
    result = _apply(
        probe_runner=th.run_target_host_probe,
        operator_authorization=permit,
        operator_signature=b"test-signature",
    )

    cap = captured["capsule"]
    assert cap["intent_digest"] == _intent()["self_digest"]  # 綁 intent digest
    assert cap["source_head"] == HEAD                          # 綁 source head
    assert cap["expected_host"] == "trade-core"                # 綁 expected host
    assert cap["actor_node"] == APPLIER                        # 綁 actor node
    assert cap["operator_authorization_digest"] == permit[
        "authorization_digest"
    ]
    assert thchild.validate_capsule(cap, now=NOW) == []        # capsule 自洽、未過期
    assert captured["gate_during"] is None                     # 委派期間 parent env 無授權閘
    assert result["verifier_capture_digest"] is None           # 交付的是升 BINDING 前的 applier 自跑
    assert "AIML_TARGET_HOST_PROBE" not in os.environ


def test_real_runner_on_mac_fails_closed_via_child_no_parent_gate() -> None:
    # 於 Mac 走真隔離子行程:因 expected_host=trade-core != 本機 / 非 target host 而 fail-closed。過程中
    # parent env 從不持有授權閘(真隔離的證明)——授權只存在於已結束的子行程。
    assert "AIML_TARGET_HOST_PROBE" not in os.environ
    with pytest.raises(
        (apply.TargetHostApplyError, thchild.TargetHostChildApplyError, th.TargetHostUnavailableError)
    ):
        _apply(probe_runner=th.run_target_host_probe)
    assert "AIML_TARGET_HOST_PROBE" not in os.environ


# --------------------------------------------------------------------------- #
# B1 P2 (E2): the distinct verifier capture digest is durably bound into the artifact
# --------------------------------------------------------------------------- #
def test_distinct_verifier_capture_digest_is_bound_into_upgraded_artifact() -> None:
    upgraded = apply.attach_distinct_verifier_postcheck(
        _apply(), verifier_node_id=VERIFIER, verifier_capture_digest=VERIFIER_CAP,
        residue_observation=CLEAN, now=LATER,
    )
    # 相異 capture digest 持久出現在升級後 artifact(independent_postcheck seam note)。
    assert VERIFIER_CAP in json.dumps(upgraded)
    fixed = next(
        b for b in upgraded["choice_receipt"]["candidate_probes"]
        if b["candidate_id"] == th.CANDIDATE_FIXED_PATH
    )
    ip_seam = next(
        s for s in fixed["seams"] if s["seam_id"] == th.SEAM_INDEPENDENT_POSTCHECK
    )
    assert VERIFIER_CAP in ip_seam["note"]
    assert ip_seam["verdict"] == th.SEAM_VERDICT_PASSED
    # 綁定 tamper-evident 且不破壞既有嚴格驗證:嚴格 lane + 中央離線閘皆通過。
    assert tfx.validate_target_host_effect_result(
        upgraded, now=NOW, expected_source_head=HEAD, require_success=True
    ) == []
    assert validator.validate_aiml_artifact(upgraded, now=NOW) == []


# --------------------------------------------------------------------------- #
# E4 coverage: build_target_host_landing_attempt's six own guards
# --------------------------------------------------------------------------- #
def test_landing_rejects_non_dict_effect_result() -> None:
    with pytest.raises(apply.TargetHostApplyError, match="effect_result must be an object"):
        apply.build_target_host_landing_attempt(**_landing_kwargs("not-a-dict"))


def test_landing_rejects_adapter_id_mismatch() -> None:
    result = copy.deepcopy(_apply())
    result["adapter_id"] = "some_other_adapter_v1"
    with pytest.raises(apply.TargetHostApplyError, match="route-node adapter"):
        apply.build_target_host_landing_attempt(**_landing_kwargs(result))


@pytest.mark.parametrize("field", ["applier_node_id", "postcheck_verifier_node_id", "source_head"])
def test_landing_rejects_missing_required_result_field(field) -> None:
    result = copy.deepcopy(_apply())
    result[field] = ""
    with pytest.raises(apply.TargetHostApplyError, match="is required to bind a landing attempt"):
        apply.build_target_host_landing_attempt(**_landing_kwargs(result))


def test_landing_rejects_non_sha256_effect_receipt_digest() -> None:
    result = copy.deepcopy(_apply())
    result["receipt_digest"] = "not-a-sha256"
    with pytest.raises(apply.TargetHostApplyError, match="receipt_digest must be a sha256 digest"):
        apply.build_target_host_landing_attempt(**_landing_kwargs(result))


def test_landing_rejects_non_sha256_closure_packet_digest() -> None:
    with pytest.raises(apply.TargetHostApplyError, match="closure_packet_digest must be a sha256 digest"):
        apply.build_target_host_landing_attempt(**_landing_kwargs(_apply(), closure_packet_digest="bad"))


def test_landing_rejects_empty_owned_paths() -> None:
    with pytest.raises(apply.TargetHostApplyError, match="owned_paths must be a non-empty"):
        apply.build_target_host_landing_attempt(**_landing_kwargs(_apply(), owned_paths=[]))


# --------------------------------------------------------------------------- #
# E4 coverage: attach_distinct_verifier_postcheck negatives
# --------------------------------------------------------------------------- #
def test_attach_rejects_verifier_not_declared_postcheck() -> None:
    # verifier != applier 但 != effect result 宣告的 postcheck 節點 ⇒ 拒。
    with pytest.raises(apply.TargetHostApplyError, match="declared postcheck node"):
        apply.attach_distinct_verifier_postcheck(
            _apply(), verifier_node_id="a-third-node", verifier_capture_digest=VERIFIER_CAP,
            residue_observation=CLEAN, now=LATER,
        )


def test_attach_rejects_malformed_capture_digest() -> None:
    with pytest.raises(apply.TargetHostApplyError, match="verifier_capture_digest must be a sha256 digest"):
        apply.attach_distinct_verifier_postcheck(
            _apply(), verifier_node_id=VERIFIER, verifier_capture_digest="not-sha256",
            residue_observation=CLEAN, now=LATER,
        )


def test_attach_rejects_missing_embedded_choice() -> None:
    result = copy.deepcopy(_apply())
    del result["choice_receipt"]
    with pytest.raises(apply.TargetHostApplyError, match="lacks an embedded choice receipt"):
        apply.attach_distinct_verifier_postcheck(
            result, verifier_node_id=VERIFIER, verifier_capture_digest=VERIFIER_CAP,
            residue_observation=CLEAN, now=LATER,
        )


# --------------------------------------------------------------------------- #
# E4 coverage: validate_probe_intent negatives
# --------------------------------------------------------------------------- #
def test_validate_probe_intent_rejects_non_dict() -> None:
    assert apply.validate_probe_intent("x", now=NOW) == ["target-host probe intent must be an object"]


def test_validate_probe_intent_rejects_bad_schema_version() -> None:
    errors = apply.validate_probe_intent(_intent(schema_version="wrong_v9"), now=NOW)
    assert errors == ["target-host probe intent schema_version is invalid"]


def test_validate_probe_intent_flags_created_after_expires() -> None:
    intent = _intent(
        created_at="2026-07-23T13:00:00+00:00", expires_at="2026-07-23T12:30:00+00:00",
    )
    errors = apply.validate_probe_intent(intent, now="2026-07-23T13:10:00+00:00")
    assert any("created_at must precede expires_at" in e for e in errors)


def test_validate_probe_intent_flags_not_yet_valid() -> None:
    intent = _intent(
        created_at="2026-07-23T13:00:00+00:00", expires_at="2026-07-23T14:00:00+00:00",
    )
    errors = apply.validate_probe_intent(intent, now=NOW)  # now < created_at
    assert any("is not yet valid" in e for e in errors)


def test_validate_probe_intent_flags_malformed_timestamps() -> None:
    errors = apply.validate_probe_intent(_intent(created_at="not-a-timestamp"), now=NOW)
    assert any("timestamps are invalid" in e for e in errors)
