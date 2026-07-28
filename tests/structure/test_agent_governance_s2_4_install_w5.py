"""S2.4(WP4·W5)wave-exit 中央導出的 focused 測試(§10.3 W5 row / §10.5 #27)。

證明:

- W5 wave-exit 於當前 checkout 自足再導出(結構 + 鏈綁定),且中央閘接受它;
- 竄改鏈上任一環(W4 receipt / W5 predecessor digest / owned-path 或 ABI 投影 / 非當前
  HEAD / caller 自證 status / 缺 chain)一律 NOT_PASS;
- W5 exported-ABI 折入的六組活裁決確實可再導出——它們就是 W5 補上的六條 §10.5 覆蓋缺口,
  任何一條的 source 面被弱化,``w5_structural_errors`` 必然給出具名 reason;
- W4 交出的**每一項**義務(數量取自 W4 的活 ABI,不手抄)逐條被帶到 W5 且 owner 不被偷偷
  降級;W5 逐輪自審新增的各項以同一誠實形狀記錄;
- W5 owned-path 集合每一條都真實存在(pin 不得腐化成死路徑);
- 「未實作 wave」的 fail-closed 邊界由 W5 推進到 W6。

誠實邊界:W5 的投影葉是 facade top-level import,因此進入 engine-scanner runtime import
閉包並被宣告在 ``application_bundle_runtime_closure_v1.json``。application-bundle builder
從**已提交 blob** 解析宣告路徑,所以在 PM 提交之前該 builder 會 typed 回
``APPLICATION_BUNDLE_TREE_INVALID``,W2 段因此不 PASS——那是 committed-blob 契約在正常運作,
不是缺陷。故本檔與 W4 的姿態一致:分別斷言「W5 自身再導出」與「鏈斷即斷」,不假裝乾淨樹。
"""
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
PROGRAM_CODE = ROOT / "program_code"
for candidate in (HELPERS, ML_ROOT, PROGRAM_CODE):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_4_install as install  # noqa: E402
import aiml_gate_receipt_schema_core as schema_core  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402

_EVID = {
    "test_digests": ["sha256:" + "1" * 64],
    "capture_digests": ["sha256:" + "2" * 64],
    "review_fragment_digests": ["sha256:" + "3" * 64],
}
# W4 交出的義務(§10.3 誠實面);W5 一項都不得靜默丟掉。**由 W4 的 ABI 直接列舉**:上一版
# 把它抄成一個十二項的手寫 tuple,而 W4 實際匯出十五項,於是被丟掉的那一項
# (ATTESTED_EVIDENCE_CLASS_VERIFIER)連測都測不到——手抄的清單只能證明「手抄的那些在」。
_W4_ROWS = {
    row["obligation_id"]: row
    for row in validator._W4_EXPORTED_ABI["remaining_owned_obligations"]
}
_W4_HANDOVER = tuple(sorted(_W4_ROWS))
_W5_ROWS = {
    row["obligation_id"]: row
    for row in validator._W5_EXPORTED_ABI["remaining_owned_obligations"]
}


def _provision_class(typed_status: str) -> str:
    """把 ``…_BY_W4B`` / ``…_BY_W5`` 這類**波次標籤**剝掉,只留提供程度的語義類別。

    W4→W5 的重述可以換波次名(NOT_PROVIDED_BY_W4B → NOT_PROVIDED_BY_W5),但不得換等級
    (NOT_PROVIDED → PARTIALLY_PROVIDED);後者是「悄悄軟化一項未關閉的義務」。
    """

    import re as _re

    return _re.sub(r"_BY_W\d+[AB]?", "", str(typed_status))


_W5_NEW = (
    # W5 後半段(2026-07-27)實作了 §9.2 的閘,於是舊的「整份缺席」義務被關閉,換成兩條
    # 精確殘留:§3 的 receipt 綁定欄位不存在,以及 reproducer 節點獨立性只有宣告面。
    "DEPENDENCY_REFRESH_RECEIPT_BINDING_ABSENT",
    "DEPENDENCY_REFRESH_REPRODUCER_NODE_IS_DECLARATIVE",
    # W5 對抗審計輪(2026-07-27)新記兩條:一條是 W5 掀開卻不在自己 owned path 上的既有
    # 掃描缺口,一條是 W5 只關掉自己那兩處、W4 那處仍開著的 import 期 namespace 加寬。
    "ENCODED_SECRET_SCAN_MISSES_COMPOSITE_PAYLOADS",
    "OWNED_PATH_PROJECTION_RULER_IS_NOT_UNIFORM",
    # 第三輪更名:舊 id 只點名 W4,而 W3 葉做的是**同一件事**且從未被提及。
    # 第四輪再更名:第三輪掃到四處就宣告關閉,漏了 facade top-level import 的 W2 葉(第五處)。
    "PROGRAM_CODE_IS_ON_THE_SCANNER_PATH_VIA_W2_W3_AND_W4",
    "PR_SET_DUMPABLE_IS_DECLARED_NOT_ENFORCED",
    "S2_5_LIFECYCLE_FIXTURES_DO_NOT_EXIST",
    # W5 對抗審計第二輪(2026-07-27)新記三條:§9.2 裁決零生產呼叫端、wave-exit evidence
    # digest 不可認證、PG row 的 expected_topology 是 caller 可弱化且未被簽的輸入。
    "EMITTED_EVIDENCE_DIGESTS_ARE_UNAUTHENTICATED",
    "EXPECTED_TOPOLOGY_IS_CALLER_SUPPLIED_AND_UNSIGNED",
    "SOURCE_IDENTITY_FRESHNESS_HAS_NO_PRODUCTION_CALL_SITE",
    # W5 對抗審計第三輪(2026-07-27)新記三條:§9.2 觀測窗對 S1.3 仍是 caller 自選、
    # 九個 evidence class 只映到五份 schema、S1.3 的 assurance class 可在投影不變下被抬高。
    "DEPENDENCY_OBSERVATION_WINDOW_IS_CALLER_AUTHORED",
    "EVIDENCE_CLASS_TO_SCHEMA_MAP_IS_MANY_TO_ONE",
    "S1_3_ASSURANCE_CLASS_IS_INFLATABLE_WITHOUT_CHANGING_THE_PROJECTION",
)
# 髒工作樹在 owned scope 上的具名 reason:與其他結構 reason 分開檢查,而非放寬。
_OWNED_SCOPE_REASON = validator._W5_OWNED_SCOPE_REASON


def _non_worktree_reasons(reasons) -> list[str]:
    return [reason for reason in reasons if not reason.startswith(_OWNED_SCOPE_REASON)]


@pytest.fixture(scope="module")
def chain():
    admission = install.build_w0_source_admission_receipt(ROOT)
    w0 = install.build_w0_wave_exit_receipt(admission, **deepcopy(_EVID))
    w1 = install.build_w1_wave_exit_receipt(admission, w0, **deepcopy(_EVID))
    w2 = install.build_w2_wave_exit_receipt(admission, w1, **deepcopy(_EVID))
    w3 = install.build_w3_wave_exit_receipt(admission, w2, **deepcopy(_EVID))
    w4 = install.build_w4_wave_exit_receipt(admission, w3, **deepcopy(_EVID))
    w5 = validator.build_w5_wave_exit_receipt(admission, w4, **deepcopy(_EVID))
    return admission, w0, w1, w2, w3, w4, w5


def _derive(w5, admission, w4, w0, w1, w2, w3):
    return validator.derive_wave_exit_status(
        w5,
        source_admission_receipt=admission,
        predecessor_wave_receipt=w4,
        predecessor_wave_chain=(w0, w1, w2, w3),
    )


# ── W5 自身的結構/綁定再導出(與 predecessor 鏈狀態無關)────────────────────────
def test_w5_structural_and_chain_binding_rederive_on_the_current_checkout(chain) -> None:
    """W5 自身的結構再導出:除了「owned scope 髒」那一條之外必須零 reason。

    誠實邊界(P1-C 修法之後):owned scope 一旦相對 bound commit 有 index/worktree 差異,
    W5 就**必須**給出具名 reason,所以在一棵未提交的工作樹上這一條是預期存在的,而它是否
    只在該情形下出現由
    ``test_a_dirty_or_undecidable_owned_scope_breaks_the_w5_wave_exit`` 逐案釘住。
    """

    admission, _w0, _w1, _w2, _w3, w4, w5 = chain
    assert _non_worktree_reasons(validator.w5_structural_errors(w5)) == []
    assert _non_worktree_reasons(validator._wave_exit_structural_errors(w5)) == []
    assert validator.w5_chain_binding_errors(
        w5, admission, w4, validator._git_head(ROOT)
    ) == []
    assert _non_worktree_reasons(validator.validate_aiml_artifact(w5)) == []
    assert w5["wave"] == "W5"
    assert not any(key in w5 for key in validator._CALLER_STATUS_KEYS)
    assert w5["production_authority_flags"] == {
        "nine_authorities_false": True,
        "production_apply_performed": False,
        "running_attested": False,
    }


def test_the_w5_derivation_is_wired_and_no_longer_the_unimplemented_branch(chain) -> None:
    admission, w0, w1, w2, w3, w4, w5 = chain
    result = _derive(w5, admission, w4, w0, w1, w2, w3)
    assert not any(
        "only implemented for" in reason for reason in result["reasons"]
    ), result["reasons"]
    predecessor = validator.derive_wave_exit_status(
        w4, source_admission_receipt=admission, predecessor_wave_receipt=w3,
        predecessor_wave_chain=(w0, w1, w2),
    )
    residual = _non_worktree_reasons(result["reasons"])
    if predecessor["status"] == "PASS":
        # 乾淨 owned scope ⇒ PASS;髒 owned scope ⇒ NOT_PASS 且**只**剩那一條具名 reason。
        assert residual == [], residual
        if not validator.w5_exported_abi_projection()["owned_scope_worktree_delta"]:
            assert result == {"status": "PASS", "reasons": []}
        else:
            assert result["status"] == "NOT_PASS"
            assert len(result["reasons"]) == 1, result["reasons"]
    else:
        assert result["status"] == "NOT_PASS"
        assert all(
            reason.startswith("W5 wave-exit bound predecessor_wave_receipt does not derive PASS")
            for reason in residual
        ), residual


def test_tampered_w4_predecessor_breaks_the_w5_chain(chain) -> None:
    admission, w0, w1, w2, w3, w4, w5 = chain
    forged_w4 = deepcopy(w4)
    forged_w4["owned_path_diff_digest"] = "sha256:" + "e" * 64
    forged_w4["self_digest"] = validator.artifact_self_digest(forged_w4)
    result = _derive(w5, admission, forged_w4, w0, w1, w2, w3)
    assert result["status"] == "NOT_PASS"
    assert any(
        "predecessor_wave_receipt does not derive PASS" in reason
        for reason in result["reasons"]
    )


def test_w5_requires_the_exact_four_element_predecessor_chain(chain) -> None:
    admission, w0, w1, w2, w3, w4, w5 = chain
    for bad in ((), (w0,), (w0, w1), (w0, w1, w2), (w0, w1, w2, w3, w4)):
        assert validator.derive_wave_exit_status(
            w5,
            source_admission_receipt=admission,
            predecessor_wave_receipt=w4,
            predecessor_wave_chain=bad,
        )["status"] == "NOT_PASS"
    assert validator.derive_wave_exit_status(
        w5, source_admission_receipt=admission, predecessor_wave_chain=(w0, w1, w2, w3)
    )["status"] == "NOT_PASS"
    assert validator.derive_wave_exit_status(
        w5, predecessor_wave_receipt=w4, predecessor_wave_chain=(w0, w1, w2, w3)
    )["status"] == "NOT_PASS"


def test_w5_predecessor_must_be_the_w4_receipt(chain) -> None:
    admission, _w0, _w1, _w2, w3, _w4, w5 = chain
    swapped = deepcopy(w5)
    swapped["predecessor_wave_receipt_digest"] = w3["self_digest"]
    swapped["self_digest"] = validator.artifact_self_digest(swapped)
    reasons = validator.w5_chain_binding_errors(
        swapped, admission, w3, validator._git_head(ROOT)
    )
    assert any("predecessor must be the W4 wave-exit receipt" in r for r in reasons)


@pytest.mark.parametrize("field,value", [
    ("status", "PASS"), ("pass", True), ("done", True), ("admitted", True),
])
def test_w5_self_declared_status_rejected_before_derivation(chain, field, value) -> None:
    admission, w0, w1, w2, w3, w4, w5 = chain
    forged = deepcopy(w5)
    forged[field] = value
    forged["self_digest"] = validator.artifact_self_digest(forged)
    result = _derive(forged, admission, w4, w0, w1, w2, w3)
    assert result["status"] == "NOT_PASS"
    assert any("must not self-declare status" in r for r in result["reasons"])


@pytest.mark.parametrize("field", [
    "owned_path_manifest_digest", "owned_path_diff_digest", "exported_abi_digest",
])
def test_w5_projection_drift_is_not_pass(chain, field) -> None:
    admission, w0, w1, w2, w3, w4, w5 = chain
    forged = deepcopy(w5)
    forged[field] = "sha256:" + "a" * 64
    forged["self_digest"] = validator.artifact_self_digest(forged)
    assert validator.w5_structural_errors(forged)
    assert _derive(forged, admission, w4, w0, w1, w2, w3)["status"] == "NOT_PASS"


def test_w5_null_predecessor_digest_is_structurally_rejected(chain) -> None:
    _admission, _w0, _w1, _w2, _w3, _w4, w5 = chain
    forged = deepcopy(w5)
    forged["predecessor_wave_receipt_digest"] = None
    forged["self_digest"] = validator.artifact_self_digest(forged)
    assert any(
        "non-null predecessor_wave_receipt_digest" in r
        for r in validator.w5_structural_errors(forged)
    )


def test_w5_source_head_must_be_the_current_checkout_head(chain) -> None:
    admission, _w0, _w1, _w2, _w3, w4, w5 = chain
    forged = deepcopy(w5)
    forged["source_head"] = "b" * 40
    forged["self_digest"] = validator.artifact_self_digest(forged)
    reasons = validator.w5_chain_binding_errors(
        forged, admission, w4, validator._git_head(ROOT)
    )
    assert any("source_head" in r for r in reasons)


@pytest.mark.parametrize("field", ["test_digests", "capture_digests", "review_fragment_digests"])
def test_w5_empty_evidence_lists_never_derive_pass(chain, field) -> None:
    admission, w0, w1, w2, w3, w4, _w5 = chain
    evidence = deepcopy(_EVID)
    evidence[field] = []
    forged = validator.build_w5_wave_exit_receipt(admission, w4, **evidence)
    assert _derive(forged, admission, w4, w0, w1, w2, w3)["status"] == "NOT_PASS"


# ── owned paths / exported ABI ──────────────────────────────────────────────────
def test_w5_owned_paths_are_live_and_cover_the_w5_surface() -> None:
    """第四輪 P2:舊版只點名 14 條裡的 5 條,於是 worker **縮小**自己的 scope 不會變紅。

    §10.1.2 (d) 的三支測試都只看「§10.1 之外」的路徑,而第三輪把 owned-scope 乾淨度變成
    承重之後,少掉一條就等於替那條路徑重開旁路——把
    ``helper_scripts/maintenance_scripts/agent_governance_s2_4_install.py``(§10.1 逐字清單
    上、且 W6 operator 真的會執行的那一支)從 ``_W5_OWNED_PATHS`` 拿掉,整條 124 支的 W5
    lane 全綠。所以這裡改成**全集合**釘死:縮表與擴表都必須是兩處明示編輯,其中一處在
    reviewer 會逐行讀的測試 diff 裡。
    """

    required = {
        "helper_scripts/maintenance_scripts/agent_governance_s2_4_install.py",
        "helper_scripts/maintenance_scripts/agent_governance_s2_4_w5_emit.py",
        "program_code/ml_training/aiml_gate_receipt_s2_4_contracts.py",
        "program_code/ml_training/aiml_gate_receipt_schema_core.py",
        "program_code/ml_training/aiml_gate_receipt_validator.py",
        "program_code/ml_training/aiml_gate_receipt_w5_obligations.py",
        "program_code/ml_training/aiml_gate_receipt_wave_w5.py",
        "program_code/ml_training/application_bundle_runtime_closure_v1.json",
        "program_code/ml_training/schemas/aiml_gate_receipts/"
        "s2_4_dependency_refresh_attestation_v1.schema.json",
        "program_code/ml_training/tests/test_aiml_gate_receipt_validator_s2_4.py",
        "tests/structure/test_agent_governance_s2_4_acceptance_matrix.py",
        "tests/structure/test_agent_governance_s2_4_install_w3.py",
        "tests/structure/test_agent_governance_s2_4_install_w5.py",
        "tests/structure/test_agent_governance_s2_4_install_w5_emit.py",
    }
    assert set(validator._W5_OWNED_PATHS) == required, {
        "narrowed_away": sorted(required - set(validator._W5_OWNED_PATHS)),
        "added_without_updating_this_pin": sorted(
            set(validator._W5_OWNED_PATHS) - required
        ),
    }
    dead = [rel for rel in validator._W5_OWNED_PATHS if not (ROOT / rel).is_file()]
    assert not dead, f"W5 owned paths contain dead entries: {dead}"


def test_the_w5_projection_leaf_is_declared_in_the_runtime_import_closure() -> None:
    """facade top-level import ⇒ 進入 engine-scanner runtime import 閉包 ⇒ 必須被宣告。"""

    import json

    closure = json.loads(
        (ML_ROOT / "application_bundle_runtime_closure_v1.json").read_text(encoding="utf-8")
    )
    assert "program_code/ml_training/aiml_gate_receipt_wave_w5.py" in closure["python_modules"]
    assert closure["self_digest"] == validator.artifact_self_digest(
        {k: v for k, v in closure.items() if k != "self_digest"}
    )


def test_a_degraded_dependency_refresh_gate_breaks_the_w5_wave_exit_by_name(
    chain, monkeypatch
) -> None:
    """§9.2 的活裁決是**接進 wave-exit** 的,不只是投影裡的一個值。

    把 ``_dependency_refresh_live`` 換成一份「refresh-by-reference 被放行 + 復述舊 digest
    被採信」的退化投影,``w5_structural_errors`` 必須給出具名 reason。若有人把
    ``_dependency_refresh_reasons`` 的接線拿掉,本測試轉紅。
    """

    import aiml_gate_receipt_wave_w5 as wave_w5

    _admission, _w0, _w1, _w2, _w3, _w4, w5 = chain
    clean = wave_w5._dependency_refresh_live(ROOT)
    degraded = dict(clean)
    degraded["reasserted_original_digest_status"] = "DEPENDENCY_REFRESH_ADMITTED"
    degraded["never_refreshable_statuses"] = {
        name: "SOURCE_DEPENDENCY_ADMITTED_BY_REFRESH"
        for name in clean["never_refreshable_classes"]
    }
    monkeypatch.setattr(wave_w5, "_dependency_refresh_live", lambda *_a, **_k: degraded)
    reasons = validator.w5_structural_errors(w5)
    assert any("merely re-asserts the original digest" in r for r in reasons), reasons
    assert any("refresh-by-reference" in r for r in reasons), reasons


def test_w5_exported_abi_projection_folds_the_seven_live_verdict_groups() -> None:
    projection = validator.w5_exported_abi_projection()
    secret = projection["secret_scan_live"]
    assert secret["encoded_forms_detected"] == {
        "raw": True, "base64": True, "base16_upper": True, "base16_lower": True,
        "urlsafe_base64": True, "hex": True,
    }
    assert secret["dict_key_is_scanned"] is True
    assert secret["bytes_node_is_scanned"] is True
    assert secret["clean_artifact_passes"] is True
    assert secret["no_sentinel_is_a_noop"] is True
    pg = projection["pg_role_identity_live"]
    assert pg["manifest_role_name_const"] == "aiml_engine_scanner"
    assert pg["shipped_manifest_role_name"] == "aiml_engine_scanner"
    assert pg["observer_named_manifest_is_centrally_rejected"] is True
    assert pg["observer_absent_from_generated_sql"] is True
    assert pg["every_generated_statement_names_the_scanner_role_or_public"] is True
    assert pg["grantee_vocabulary"] == ['"aiml_engine_scanner"', "PUBLIC"]
    scope = projection["component_scope_live"]
    assert scope["row_count"] == 5
    assert all(scope["forbidden_component_identities_absent"].values())
    postcheck = projection["inactive_postcheck_live"]
    assert postcheck["postcheck_carries_no_lifecycle_claim"] is True
    assert postcheck["receipt_carries_no_lifecycle_claim"] is True
    assert postcheck["postcheck_additional_properties_closed"] is True
    assert all(postcheck["enable_and_start_are_forbidden"].values())
    unit = projection["rendered_unit_negative_live"]
    assert unit["clean_unit_status"] == "PASS"
    assert unit["system_interpreter_status"] == "ENGINE_SCANNER_UNIT_INVALID"
    assert unit["alr_shadow_identity_status"] == "ENGINE_SCANNER_UNIT_INVALID"
    assert unit["mutable_checkout_status"] == "ENGINE_SCANNER_UNIT_INVALID"
    schema = projection["schema_registration_live"]
    assert schema["unregistered_schema_keys"] == []
    assert schema["unresolvable_schema_keys"] == []
    assert schema["undeclared_on_disk_schema_keys"] == []
    # W5 後半段:§10.1 明列的那一份 schema 已存在且已註冊(缺口由「記錄」翻成「已建」)。
    assert schema["dependency_refresh_schema_file_exists"] is True
    assert schema["dependency_refresh_schema_registered"] is True
    refresh = projection["dependency_refresh_live"]
    assert refresh["positive_refresh_status"] == "DEPENDENCY_REFRESH_ADMITTED"
    assert refresh["positive_admission_status"] == "SOURCE_DEPENDENCY_ADMITTED_BY_REFRESH"
    assert refresh["expired_without_refresh_status"] == (
        "SOURCE_DEPENDENCY_EXPIRED_NO_REFRESH"
    )
    for key in (
        "reasserted_original_digest_status",
        "same_producer_node_status",
        "refresh_of_a_refresh_status",
        "self_declared_status_status",
        "substituted_original_status",
        "stale_head_status",
        "semantic_digest_drift_status",
    ):
        assert refresh[key] == "DEPENDENCY_REFRESH_REJECTED", key
    assert refresh["two_refreshes_status"] == "SOURCE_DEPENDENCY_REJECTED"
    assert all(
        status == "DEPENDENCY_REFRESH_BY_REFERENCE_FORBIDDEN"
        for status in refresh["never_refreshable_statuses"].values()
    )
    assert refresh["refresh_carries_no_signature_field"] is True
    assert all(refresh["reproducible_class_field_sets"].values())


def test_w5_abi_states_its_boundary_and_names_no_effect() -> None:
    abi = validator._W5_EXPORTED_ABI
    assert abi["wave"] == "W5"
    assert "no runtime, host, production-PostgreSQL or effect evidence" in (
        abi["boundary_contract"]
    )
    assert "SOURCE_READY only" in abi["boundary_contract"]
    assert "adds no production gate and performs no effect" in abi["wave_scope"]
    for contract in (
        "secret_scan_contract", "pg_role_identity_contract", "component_scope_contract",
        "inactive_postcheck_contract", "rendered_unit_identity_contract",
        "schema_registration_contract", "acceptance_map_contract",
    ):
        assert abi[contract] and len(abi[contract]) > 120, contract


# ── 義務移交:一項都不得靜默丟掉 ─────────────────────────────────────────────────
@pytest.mark.parametrize("obligation_id", _W4_HANDOVER)
def test_every_w4_obligation_is_carried_forward_with_an_owner(obligation_id) -> None:
    """W4 的**每一列**(由 W4 ABI 列舉,非手抄)都必須在 W5 帳上,且帶完整誠實欄位。"""

    assert obligation_id in _W5_ROWS, (
        f"W5 dropped the W4 obligation {obligation_id}; a row whose residual is live is "
        "carried forward, never deleted"
    )
    entry = _W5_ROWS[obligation_id]
    assert entry["owner_wave"] and entry["spec_refs"] and entry["statement"]
    assert entry["w5_provides"]


@pytest.mark.parametrize("obligation_id", _W4_HANDOVER)
def test_a_carried_obligation_is_never_silently_softened(obligation_id) -> None:
    """帶過來的 typed_status 只能換波次標籤,不能換提供等級(W5 沒提供就不准變得更綠)。

    上一版把 ATTESTATION_EXPIRY_AND_HOST_TIME_ARE_NOT_CROSS_CHECKED 由 NOT_PROVIDED_BY_W4B
    寫成 PARTIALLY_PROVIDED_BY_W4B,而該列 statement 第一句就是「BOTH halves W4 named are
    still open」;既有的帳本測試只釘 membership 與 owner,量不到這種軟化。
    """

    w4_class = _provision_class(_W4_ROWS[obligation_id]["typed_status"])
    w5_class = _provision_class(_W5_ROWS[obligation_id]["typed_status"])
    assert w5_class == w4_class, (
        f"{obligation_id} typed_status changed provision level "
        f"{_W4_ROWS[obligation_id]['typed_status']!r} -> "
        f"{_W5_ROWS[obligation_id]['typed_status']!r}"
    )
    w4_owner = str(_W4_ROWS[obligation_id]["owner_wave"])
    w5_owner = str(_W5_ROWS[obligation_id]["owner_wave"])
    # owner 可以在 W4 已完成後收窄(如 "W4/W6" -> "W6"),但不得換到別人頭上。
    assert w5_owner in w4_owner.split("/"), (obligation_id, w4_owner, w5_owner)


def test_w5_records_its_own_new_findings_in_the_same_honest_shape() -> None:
    assert set(_W5_NEW) <= set(_W5_ROWS)
    for obligation_id in _W5_NEW:
        entry = _W5_ROWS[obligation_id]
        assert set(entry) >= {
            "obligation_id", "typed_status", "owner_wave", "spec_refs", "statement",
            "w5_provides",
        }
        assert len(entry["statement"]) > 200
    # ATTESTED_EVIDENCE_CLASS_VERIFIER 的 W6B 殘留(在真主機上**取得**簽章)仍是活的,故它
    # 是被帶過來的 W4 列,而不是 W5 的新發現,也不得被刪。
    assert _W5_ROWS["ATTESTED_EVIDENCE_CLASS_VERIFIER"]["typed_status"] == (
        _W4_ROWS["ATTESTED_EVIDENCE_CLASS_VERIFIER"]["typed_status"]
    )


def test_the_w5_obligation_ledger_has_no_duplicate_or_unowned_row() -> None:
    rows = validator._W5_EXPORTED_ABI["remaining_owned_obligations"]
    ids = [row["obligation_id"] for row in rows]
    assert len(ids) == len(set(ids))
    # 帳本 = W4 全部 + W5 新記,**不多不少**:多一列 = 憑空長出來,少一列 = 被靜默丟掉。
    assert set(ids) == set(_W4_HANDOVER) | set(_W5_NEW), {
        "extra": sorted(set(ids) - set(_W4_HANDOVER) - set(_W5_NEW)),
        "missing": sorted((set(_W4_HANDOVER) | set(_W5_NEW)) - set(ids)),
    }
    # owner 必須是一個**真的**下游 owner。W5 只有在該列已由 W5 自己交付時才可以是 owner,
    # 而那時 typed_status 必須明說是誰批准的(§10.1.1 的 path-scope 決定不是工人自己下的)。
    for row in rows:
        assert row["owner_wave"] in {"PM", "S1.3", "S2.5A", "W5", "W6", "W6B"}, (
            row["obligation_id"]
        )
        if row["owner_wave"] == "W5":
            assert row["typed_status"] == "PROVIDED_BY_W5_UNDER_PM_RULING", row[
                "obligation_id"
            ]


# ── 未實作 wave 的 fail-closed 邊界推進到 W6 ────────────────────────────────────
def test_w6_and_beyond_remain_fail_closed(chain) -> None:
    admission, w0, w1, w2, w3, w4, _w5 = chain
    forged = deepcopy(w4)
    forged["wave"] = "W5"  # schema enum 只到 W5;W6 需要先擴 enum,故以 W5-shaped W4 探測
    forged["self_digest"] = validator.artifact_self_digest(forged)
    # W4 的投影冒充 W5 → W5 的結構再導出必然拒(投影不對),而非被當成已實作而放行。
    result = validator.derive_wave_exit_status(
        forged, source_admission_receipt=admission, predecessor_wave_receipt=w4,
        predecessor_wave_chain=(w0, w1, w2, w3),
    )
    assert result["status"] == "NOT_PASS"
    assert any("W5 exported-ABI projection" in r for r in result["reasons"])
    # schema 的 wave enum 仍封閉在 W0..W5:W6 不可能被自證。
    schema = validator._load_schema("s2_4_wave_exit_receipt_v1")
    assert schema["properties"]["wave"]["enum"] == ["W0", "W1", "W2", "W3", "W4", "W5"]


def test_the_facade_reexports_the_w5_surface() -> None:
    for name in (
        "_W5_OWNED_PATHS", "_W5_EXPORTED_ABI", "w5_structural_errors",
        "w5_chain_binding_errors", "w5_exported_abi_projection", "w5_owned_path_diff_digest",
        "build_w5_wave_exit_receipt",
    ):
        assert hasattr(validator, name), name
    assert validator._WAVE_PREDECESSOR_CHAIN["W5"][0] == "W4"
    assert validator._WAVE_PREDECESSOR_CHAIN["W5"][1] == 4


# ── W5 對抗審計輪:§9.2 閘自身的四個裁決(每一支在 b78185b00 上都會紅)───────────────
_NOW = "2026-07-27T00:05:00+00:00"
_AT = "2026-07-27T00:00:00+00:00"
_PLATFORM = {"os": "darwin", "arch": "arm64", "python_version": "3.12"}
_S2_2A_V1 = "docs/execution_plan/ai_ml_landing/receipts/S2.2A-source-compatibility-receipt-v1.json"


def _git(root: Path, *args: str) -> str:
    import subprocess

    done = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


def _seed_repo(target: Path, paths) -> str:
    """把 REPO 的這些路徑複製進一棵新的 git 樹並提交一次;回傳該 commit。"""

    import subprocess

    for rel in paths:
        (target / rel).parent.mkdir(parents=True, exist_ok=True)
        (target / rel).write_bytes((ROOT / rel).read_bytes())
    subprocess.run(["git", "init", "-q", str(target)], capture_output=True, check=True)
    _git(target, "config", "user.email", "e1@local")
    _git(target, "config", "user.name", "e1")
    _git(target, "add", "-A")
    _git(target, "commit", "-q", "-m", "seed")
    return _git(target, "rev-parse", "HEAD")


def test_a_drifted_commit_cannot_be_refreshed_from_a_restored_working_tree(tmp_path) -> None:
    """§9.2 review P1-A:head 取自 git、位元組取自工作樹,兩把尺混用即可繞過整個閘。

    情境是真的:某個 producer 輸入在 head 上已漂移,故該身分**確實**復現不出來(§9.2 的
    正解是重新觀測)。攻擊者只在工作樹把 pre-drift 位元組放回去——不 commit、不 git add,
    因為舊路徑走 ``Path.read_bytes()`` 根本不看 index——重算就又對上了。
    """

    import json

    lrm = __import__("learning_runtime_manifest")
    inputs = sorted(set(
        lrm.CAPTURE_INPUTS + lrm.LEARNING_CODE_INPUTS_V2 + lrm.MIGRATION_INPUTS + (
            lrm.REGIME_OOS_LABEL_CONTRACT, lrm.POLICY_TEMPLATE,
            lrm.DEPENDENCY_LOCK_SPEC_FILE, lrm.DEPENDENCY_LOCK_LOCK_FILE,
            "program_code/ml_training/learning_runtime_manifest.py",
            "program_code/ml_training/edge_feature_schema_contract.py",
        )
    ))
    mini = tmp_path / "mini"
    _seed_repo(mini, inputs)
    original = json.loads((ROOT / _S2_2A_V1).read_text(encoding="utf-8"))
    refresh = validator.build_s2_4_dependency_refresh_attestation(
        original, reproducer_caller="E1:independent", reproducer_platform=dict(_PLATFORM),
        reproduced_at=_AT, repo_root=mini,
    )
    # 乾淨的 head 上,repo 自帶的真 receipt 逐欄復現得出 → 正向路徑仍然成立。
    assert validator.derive_dependency_refresh_status(
        refresh, original_receipt=original, now=_NOW, repo_root=mini
    )["status"] == "DEPENDENCY_REFRESH_ADMITTED"

    victim = mini / lrm.CAPTURE_INPUTS[0]
    pre_drift = victim.read_bytes()
    victim.write_bytes(pre_drift + b"\n# drift\n")
    _git(mini, "add", "-A")
    _git(mini, "commit", "-q", "-m", "drift")
    spliced = {**refresh, "current_source_head": _git(mini, "rev-parse", "HEAD")}
    spliced.pop("self_digest")
    spliced["self_digest"] = validator.artifact_self_digest(spliced)

    def _verdict():
        return validator.derive_dependency_refresh_status(
            spliced, original_receipt=original, now=_NOW, repo_root=mini
        )

    assert _verdict()["status"] == "DEPENDENCY_REFRESH_REJECTED"
    victim.write_bytes(pre_drift)  # ← 攻擊:只還原工作樹
    assert _git(mini, "status", "--porcelain")
    verdict = _verdict()
    assert verdict["status"] == "DEPENDENCY_REFRESH_REJECTED", verdict
    assert any("differs from the bound commit" in reason for reason in verdict["reasons"])
    assert validator.derive_source_dependency_admission_status(
        evidence_class="S2_2A_SOURCE_COMPATIBILITY", receipt=original, refresh=spliced,
        now=_NOW, repo_root=mini,
    )["status"] == "SOURCE_DEPENDENCY_REJECTED"
    with pytest.raises(ValueError):
        validator.build_s2_4_dependency_refresh_attestation(
            original, reproducer_caller="E1:independent",
            reproducer_platform=dict(_PLATFORM), reproduced_at=_AT, repo_root=mini,
        )


def test_a_hand_written_original_no_session_produced_is_never_refreshable() -> None:
    """§9.2 review P1-C:原 receipt 只被 isinstance/schema_version/自指 digest 檢查過。

    於是攻擊者可以手寫一份任何 S2.3 session 都沒產出過的 "original"、自帶
    ``running_attested: True``、自選 observation_time/expires_at,再刷新它;而自選到期
    也順帶讓「reproduced_at 必須晚於原到期」這條反自我刷新控制形同虛設。
    """

    forged = {
        "schema_version": "expected_identity_receipt_v1",
        "caller": "E9:hand-written",
        "platform": dict(_PLATFORM),
        "observation_time": "2020-01-01T00:00:00+00:00",
        "expires_at": "2020-01-01T00:30:00+00:00",
        "running_attested": True,
        **validator.reproduce_dependency_semantic_digests(
            "S2_3_EXPECTED_IDENTITY",
            original_schema_version="expected_identity_receipt_v1", repo_root=ROOT,
        ),
    }
    assert validator.validate_aiml_artifact(forged) != []
    refresh = validator.build_s2_4_dependency_refresh_attestation(
        forged, reproducer_caller="E1:independent", reproducer_platform=dict(_PLATFORM),
        reproduced_at=_AT, repo_root=ROOT,
    )
    verdict = validator.derive_dependency_refresh_status(
        refresh, original_receipt=forged, now=_NOW, repo_root=ROOT
    )
    assert verdict["status"] == "DEPENDENCY_REFRESH_REJECTED"
    assert validator.derive_source_dependency_admission_status(
        evidence_class="S2_3_EXPECTED_IDENTITY", receipt=forged, refresh=refresh,
        now=_NOW, repo_root=ROOT,
    )["status"] == "SOURCE_DEPENDENCY_REJECTED"
    # 真 receipt 拿掉自己的 self_digest 之後同樣不可刷新(artifact_self_digest 忽略該欄位,
    # 故 original_receipt_digest 仍對得上——這正是自指比對什麼都證明不了的地方)。
    import json

    unsigned = {
        key: value
        for key, value in json.loads((ROOT / _S2_2A_V1).read_text(encoding="utf-8")).items()
        if key != "self_digest"
    }
    stripped = validator.build_s2_4_dependency_refresh_attestation(
        unsigned, reproducer_caller="E1:independent", reproducer_platform=dict(_PLATFORM),
        reproduced_at=_AT, repo_root=ROOT,
    )
    assert stripped["original_receipt_digest"] == validator.artifact_self_digest(unsigned)
    assert validator.derive_dependency_refresh_status(
        stripped, original_receipt=unsigned, now=_NOW, repo_root=ROOT
    )["status"] == "DEPENDENCY_REFRESH_REJECTED"


def test_repo_root_selects_the_tree_the_semantic_digests_come_from(tmp_path) -> None:
    """§9.2 review P1-B:``repo_root`` 過去只決定 head 與 producer blob,語義 digest 卻由
    producer 自己的 module anchor 決定 → 隔離 clone + 預設 checkout 的兩樹拼接。"""

    import hashlib

    s1_3 = "helper_scripts/maintenance_scripts/agent_governance_identity_acl_contract.py"
    schema = (
        "program_code/ml_training/schemas/aiml_gate_receipts/"
        "identity_acl_contract_receipt_v1.schema.json"
    )
    iso = tmp_path / "iso"
    (iso / s1_3).parent.mkdir(parents=True, exist_ok=True)
    (iso / s1_3).write_bytes((ROOT / s1_3).read_bytes() + b"\n# isolated divergence\n")
    _seed_repo(iso, [schema])
    reproduced = validator.reproduce_dependency_semantic_digests(
        "S1_3_IDENTITY_CONTRACT",
        original_schema_version="identity_acl_contract_receipt_v1", repo_root=iso,
    )
    assert reproduced["source_sha256"] == "sha256:" + hashlib.sha256(
        (iso / s1_3).read_bytes()
    ).hexdigest()
    assert reproduced["source_sha256"] != "sha256:" + hashlib.sha256(
        (ROOT / s1_3).read_bytes()
    ).hexdigest()


@pytest.mark.parametrize("evidence_class", sorted(validator.S2_4_NEVER_REFRESHABLE_EVIDENCE))
def test_evidence_class_is_a_label_not_the_proof_of_what_the_artifact_is(
    evidence_class,
) -> None:
    """§9.2 review P2-D:未經驗證的兩鍵 dict 冠上任一 never-refreshable 類別即導出 FRESH。"""

    verdict = validator.derive_source_dependency_admission_status(
        evidence_class=evidence_class,
        receipt={"expires_at": "2099-01-01T00:00:00+00:00"},
        now=_NOW, repo_root=ROOT,
    )
    assert verdict["status"] == "SOURCE_DEPENDENCY_REJECTED", verdict
    assert validator.dependency_evidence_schema_versions(evidence_class)


def test_the_commit_bound_recomputation_is_the_producers_own_identity_function() -> None:
    """物化樹上的重算必須**逐字**等於各 producer 自己的公開身分函式(乾淨樹上)。

    這是 P1-A/P1-B 修法的正確性條件:換 anchor 不得換語義,否則 §9.2 的「不得改動任何
    語義 digest」會因為驗證端用了另一把尺而假性失敗。
    """

    import agent_governance_identity_acl_contract as s1_3
    import agent_governance_sealed_build as sealed
    from ml_training import learning_runtime_manifest as lrm

    identity = validator.reproduce_dependency_semantic_digests(
        "S1_3_IDENTITY_CONTRACT",
        original_schema_version="identity_acl_contract_receipt_v1", repo_root=ROOT,
    )
    assert identity["schema_sha256"] == s1_3.schema_sha256()
    assert identity["source_sha256"] == s1_3.source_sha256()
    contract = s1_3.canonical_identity_acl_contract()
    assert identity["identity_projection_digest"] == validator.canonical_digest(
        validator.s1_3_identity_projection(contract)
    )
    assert identity["negative_acl_kinds_digest"] == validator.canonical_digest(sorted({
        case["over_grant_kind"] for case in s1_3.build_negative_acl_cases(contract)
    }))
    closure = sealed.verify_lock_closure(
        ROOT / "requirements-ml.lock", ROOT / "requirements-ml.txt"
    )
    runtime_digest = sealed.runtime_content_digest(
        closure_hash=closure["closure_hash"],
        isolated_launch_config=sealed._launch_block(),
        native_lib_inventory_digest=sealed._native_inventory_digest(
            sealed.project_native_inventory(closure)
        ),
        python_version=sealed.TARGET_PYTHON_VERSION,
        target_platform=sealed.TARGET_PLATFORM,
    )
    import json as _json

    committed_sealed = _json.loads(
        (ROOT / validator.S2_3_SEALED_BUILD_RECEIPT_REL).read_text(encoding="utf-8")
    )
    assert validator.reproduce_dependency_semantic_digests(
        "S2_3_EXPECTED_IDENTITY",
        original_schema_version="expected_identity_receipt_v1", repo_root=ROOT,
    ) == {
        "expected_component_identities_digest": validator.canonical_digest(
            sealed.expected_component_identities()
        ),
        "rollback_binding_digest": sealed._rollback_binding()["rollback_digest"],
        "runtime_content_digest": runtime_digest,
        "s1_3_negatives_digest": sealed.s1_3_negatives_digest(),
        "schema_sha256": sealed.expected_identity_schema_sha256(),
        "sealed_build_digest": sealed.receipt_digest(committed_sealed),
        "source_sha256": sealed.source_sha256(),
    }
    sealed_digests = validator.reproduce_dependency_semantic_digests(
        "S2_3_SEALED_BUILD", original_schema_version="sealed_build_receipt_v1", repo_root=ROOT
    )
    assert sealed_digests["schema_sha256"] == sealed.sealed_schema_sha256()
    assert sealed_digests["source_sha256"] == sealed.source_sha256()
    assert sealed_digests["closure_hash"] == closure["closure_hash"]
    assert sealed_digests["runtime_content_digest"] == runtime_digest
    assert sealed_digests["native_library_inventory_digest"] == (
        sealed._native_inventory_digest(sealed.project_native_inventory(closure))
    )
    manifest, errors = lrm.try_build_learning_runtime_manifest_v2(ROOT)
    assert errors == []
    assert validator.reproduce_dependency_semantic_digests(
        "S2_2A_SOURCE_COMPATIBILITY",
        original_schema_version="source_compatibility_receipt_v2", repo_root=ROOT,
    ) == {
        "capture_contract_digest": manifest["capture_contract"]["digest"],
        "learning_runtime_digest": manifest["self_digest"],
        "training_contract_digest": manifest["training_contract"]["digest"],
    }


# ── W5 對抗審計第二輪(2026-07-27):A / B / C / D 四項的具名回歸 ────────────────────
_S2_3_EXPECTED = (
    "docs/execution_plan/ai_ml_landing/receipts/S2.3-expected-identity-receipt-v1.json"
)


def _reseal(artifact: dict) -> dict:
    artifact = dict(artifact)
    artifact.pop("self_digest", None)
    artifact["self_digest"] = validator.artifact_self_digest(artifact)
    return artifact


# A:被證主體逐個漂移。每一個在修正前都拿得到 DEPENDENCY_REFRESH_ADMITTED,因為 S2.3/S1.3 的
# semantic_digest_fields 只有 (schema 檔雜湊, producer 檔雜湊),而後者就是 producer_module_digest。
_S2_3_SUBJECT_DRIFTS = {
    "sealed_build_digest": lambda r: {**r, "sealed_build_digest": "sha256:" + "a" * 64},
    "runtime_content_digest": lambda r: {**r, "runtime_content_digest": "sha256:" + "c" * 64},
    "expected_component_identities": lambda r: {
        **r,
        "expected_component_identities": [
            {**row, "pg_role": "postgres"} if row["component"] == "serving" else row
            for row in r["expected_component_identities"]
        ],
    },
    "rollback_binding": lambda r: {
        **r,
        "rollback_binding": {**r["rollback_binding"], "rollback_digest": "sha256:" + "d" * 64},
    },
    "s1_3_negatives_digest": lambda r: {
        **r,
        "negative_acl_binding": {
            **r["negative_acl_binding"], "s1_3_negatives_digest": "sha256:" + "e" * 64,
        },
    },
    # 第九個漂移(本輪驗證時新發現):status 是 enum ["PASS","FAIL"],家族驗證器預設
    # require_success=False,故補上 failure_reason 讓 schema 過關之後,一份自陳 FAIL 的
    # artifact 照樣可被刷新——§9.2 續的是過期身分,不是失敗觀測。
    "status_flipped_to_fail": lambda r: {
        **r, "status": "FAIL", "failure_reason": "forged failure",
    },
}


@pytest.mark.parametrize("subject", sorted(_S2_3_SUBJECT_DRIFTS))
def test_a_drifted_s2_3_subject_can_never_be_refreshed(subject) -> None:
    """§9.2 P1-A:refresh 復現的必須是**被證主體**,不是 producer 檔案自己的雜湊。

    原表的 ``source_sha256`` 逐位元組等於 refresh 另欄已綁的 ``producer_module_digest``
    (兩者都是 ``_file_sha256(SOURCE_PATH)``),於是「獨立復現 producer/semantic checks」
    只證了兩個檔案沒變:把 sealed 對象、runtime 內容身分、expected-component 身分、rollback
    綁定或 negative 綁定換掉,復現照樣成功。
    """

    import json

    original = json.loads((ROOT / _S2_3_EXPECTED).read_text(encoding="utf-8"))
    drifted = _reseal(_S2_3_SUBJECT_DRIFTS[subject](original))
    refresh = validator.build_s2_4_dependency_refresh_attestation(
        drifted, reproducer_caller="E1:S2.4:W5-subject-drift",
        reproducer_platform=dict(_PLATFORM), reproduced_at=_AT, repo_root=ROOT,
    )
    verdict = validator.derive_dependency_refresh_status(
        refresh, original_receipt=drifted, now=_NOW, repo_root=ROOT
    )
    assert verdict["status"] == "DEPENDENCY_REFRESH_REJECTED", verdict
    assert validator.derive_source_dependency_admission_status(
        evidence_class="S2_3_EXPECTED_IDENTITY", receipt=drifted, refresh=refresh,
        now=_NOW, repo_root=ROOT,
    )["status"] == "SOURCE_DEPENDENCY_REJECTED"


def test_the_untouched_s2_3_identities_still_refresh_and_bind_their_subjects() -> None:
    """正向:三族真 receipt 都仍可被一份獨立復現的 refresh 續命,主體集合逐項相等。"""

    import json

    for rel, evidence_class in (
        (_S2_3_EXPECTED, "S2_3_EXPECTED_IDENTITY"),
        (
            "docs/execution_plan/ai_ml_landing/receipts/S2.3-sealed-build-receipt-v1.json",
            "S2_3_SEALED_BUILD",
        ),
        (_S2_2A_V1, "S2_2A_SOURCE_COMPATIBILITY"),
    ):
        original = json.loads((ROOT / rel).read_text(encoding="utf-8"))
        refresh = validator.build_s2_4_dependency_refresh_attestation(
            original, reproducer_caller="E1:S2.4:W5-positive",
            reproducer_platform=dict(_PLATFORM), reproduced_at=_AT, repo_root=ROOT,
        )
        assert validator.derive_source_dependency_admission_status(
            evidence_class=evidence_class, receipt=original, refresh=refresh,
            now=_NOW, repo_root=ROOT,
        )["status"] == "SOURCE_DEPENDENCY_ADMITTED_BY_REFRESH", rel
        subjects = validator.dependency_semantic_subject_values(evidence_class, original)
        assert subjects == refresh["reproduced_semantic_digests"], rel
        assert set(subjects) == set(
            validator.S2_4_DEPENDENCY_REFRESH_CLASSES[evidence_class]["semantic_digest_fields"]
        )


@pytest.mark.parametrize(
    "rel,evidence_class,move_forward,move_back",
    [
        (
            _S2_3_EXPECTED, "S2_3_EXPECTED_IDENTITY",
            {"observation_time": "2026-07-27T00:00:00+00:00",
             "expires_at": "2026-07-27T00:30:00+00:00"},
            {"observation_time": "2020-01-01T00:00:00+00:00",
             "expires_at": "2020-01-01T00:30:00+00:00"},
        ),
        (
            "docs/execution_plan/ai_ml_landing/receipts/S2.3-sealed-build-receipt-v1.json",
            "S2_3_SEALED_BUILD",
            {"observation_time": "2026-07-27T00:00:00+00:00",
             "expires_at": "2026-07-27T00:30:00+00:00"},
            {"observation_time": "2020-01-01T00:00:00+00:00",
             "expires_at": "2020-01-01T00:30:00+00:00"},
        ),
        (
            _S2_2A_V1, "S2_2A_SOURCE_COMPATIBILITY",
            {"generated_at_utc": "2026-07-27T00:00:00Z"},
            {"generated_at_utc": "2020-01-01T00:00:00Z"},
        ),
    ],
)
def test_the_observation_window_cannot_be_moved_by_editing_two_caller_fields(
    rel, evidence_class, move_forward, move_back
) -> None:
    """§9.2 review 第三輪 P1-B:整個 §9.2 閘可以被「改兩個時間戳 + 重封」跳過。

    ``dependency_original_observation_window`` 直接讀原 receipt 自帶的
    ``observation_time``/``expires_at``(S2.2A 是 ``generated_at_utc``),而那是 caller 的欄位。
    在**真的**已出貨 receipt 上把窗往前推一次,三族一律導出 ``SOURCE_DEPENDENCY_FRESH``——沒有
    refresh、沒有復現、沒有 clean-tree 閘、沒有物化;往後推再配一份 refresh 則導出
    ``SOURCE_DEPENDENCY_ADMITTED_BY_REFRESH`` 且零 reason。家族驗證器兩次都回 ``[]``,因為它
    認證的是形狀,不是那個窗。

    修法是把原身分綁回 bound commit 的 blob(與 P1-A 同一把尺):三族的原身分在 repo 內都是
    已提交的固定路徑。S1.3 沒有已提交的 receipt,其窗因此**仍然**是 caller 自選的,由
    ``DEPENDENCY_OBSERVATION_WINDOW_IS_CALLER_AUTHORED`` 逐字記錄。
    """

    import json

    original = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    # 未經竄改的那一份仍走得到 §9.2 的正常出口(否則本測試證的只是「什麼都拒」)。
    assert validator.derive_source_dependency_admission_status(
        evidence_class=evidence_class, receipt=original, now=_NOW, repo_root=ROOT,
    )["status"] == "SOURCE_DEPENDENCY_EXPIRED_NO_REFRESH"

    forward = _reseal({**original, **move_forward})
    assert validator.validate_aiml_artifact(forward, now=_NOW) == []  # 形狀仍然合法
    moved = validator.derive_source_dependency_admission_status(
        evidence_class=evidence_class, receipt=forward, now=_NOW, repo_root=ROOT,
    )
    assert moved["status"] == "SOURCE_DEPENDENCY_REJECTED", moved
    assert any("committed at the bound commit" in r for r in moved["reasons"]), moved

    backward = _reseal({**original, **move_back})
    refresh = validator.build_s2_4_dependency_refresh_attestation(
        backward, reproducer_caller="E1:S2.4:W5-window-probe",
        reproducer_platform=dict(_PLATFORM), reproduced_at=_AT, repo_root=ROOT,
    )
    assert validator.derive_source_dependency_admission_status(
        evidence_class=evidence_class, receipt=backward, refresh=refresh,
        now=_NOW, repo_root=ROOT,
    )["status"] == "SOURCE_DEPENDENCY_REJECTED"
    assert validator.derive_dependency_refresh_status(
        refresh, original_receipt=backward, now=_NOW, repo_root=ROOT
    )["status"] == "DEPENDENCY_REFRESH_REJECTED"


def test_the_committed_identity_table_is_code_owned_and_its_gap_is_recorded() -> None:
    """P1-B 的誠實面:哪幾族的窗被 commit 綁住,哪一族不是,以及後者必須在冊。"""

    table = validator.S2_4_COMMITTED_SOURCE_IDENTITY_PATHS
    assert sorted(table) == sorted(validator.S2_4_DEPENDENCY_REFRESH_CLASSES)
    for name, paths in table.items():
        for rel in paths:
            assert (ROOT / rel).is_file(), (name, rel)
        digests = validator.committed_source_identity_digests(name, ROOT)
        if paths:
            assert digests, name
        else:
            # S1.3 = 一次性 disposable 觀測,repo 內沒有已提交的原身分。
            assert digests is None, name
    caller_authored = sorted(name for name, paths in table.items() if not paths)
    assert caller_authored == ["S1_3_IDENTITY_CONTRACT"]
    obligations = {
        row["obligation_id"]: row
        for row in validator.S2_4_W5_REMAINING_OWNED_OBLIGATIONS
    }
    row = obligations["DEPENDENCY_OBSERVATION_WINDOW_IS_CALLER_AUTHORED"]
    assert row["typed_status"] == "PARTIALLY_PROVIDED_BY_W5"
    assert "S1_3_IDENTITY_CONTRACT" in row["statement"]


def test_the_dependency_input_scope_names_every_class_and_the_imported_leaf() -> None:
    """P1-C:``required`` 集合漏掉被 import 的 feature 葉,而 S1.3 根本沒有 required 條目。

    ``edge_feature_schema_contract.py`` 在 §9.2 輸入集合裡的**唯一**理由是讓 clean-tree 閘
    蓋到它(物化樹幫不上被 import 的葉)。刪掉 ``dependency_producer_input_paths`` 裡那一行,
    全樹 6111/46 逐位元組不變——沒有任何東西釘住它。S1.3 那一族靠的是
    ``required.get(name, set())`` 的空集合,於是它的 required 恆真。
    """

    import aiml_gate_receipt_wave_w5 as wave_w5

    live = validator.w5_exported_abi_projection()["dependency_refresh_live"]
    scope = live["producer_input_scope_covers_the_allowlists"]
    assert sorted(scope) == sorted(validator.S2_4_DEPENDENCY_REFRESH_CLASSES)
    assert all(covered is True for covered in scope.values()), scope
    s2_2a = validator.dependency_producer_input_paths("S2_2A_SOURCE_COMPATIBILITY")
    assert "program_code/ml_training/edge_feature_schema_contract.py" in s2_2a
    # 每一族都有**具名**的 required 條目(不是 .get(name, set()) 的恆真空集合)。
    scoped = wave_w5._producer_input_scope_live(validator)
    assert sorted(scoped) == sorted(validator.S2_4_DEPENDENCY_REFRESH_CLASSES)
    # 縮小任何一族的輸入集合都必須弄破 wave exit,而不只是靜默變弱。
    original = validator.dependency_producer_input_paths

    def _narrowed(dependency_class):
        return tuple(
            rel for rel in original(dependency_class)
            if rel != "program_code/ml_training/edge_feature_schema_contract.py"
        )

    class _Narrowed:
        S2_4_DEPENDENCY_REFRESH_CLASSES = validator.S2_4_DEPENDENCY_REFRESH_CLASSES
        dependency_producer_input_paths = staticmethod(_narrowed)

    narrowed_scope = wave_w5._producer_input_scope_live(_Narrowed)
    assert narrowed_scope["S2_2A_SOURCE_COMPATIBILITY"] is False, narrowed_scope
    assert wave_w5._dependency_refresh_reasons({
        **live, "producer_input_scope_covers_the_allowlists": narrowed_scope,
    })


def test_a_drifted_s1_3_identity_projection_can_never_be_refreshed() -> None:
    """§9.2 P1-A 的 S1.3 面:身分/ACL 投影是被證主體,兩個檔案雜湊不是。"""

    import agent_governance_identity_acl_contract as s1_3

    contract = s1_3.canonical_identity_acl_contract()
    receipt = s1_3.build_identity_acl_contract_receipt(
        caller="S1.3:probe",
        platform={"os": "darwin", "arch": "arm64", "postgres_version": "16.3"},
        target_class="disposable_local", contract=contract,
        observation_time="2026-07-01T00:00:00+00:00", ttl_seconds=1800,
        evidence_class="STRUCTURAL_ONLY",
    )
    build = validator.build_s2_4_dependency_refresh_attestation
    clean = build(
        receipt, reproducer_caller="E1:S2.4:W5-s1-3", reproducer_platform=dict(_PLATFORM),
        reproduced_at=_AT, repo_root=ROOT,
    )
    assert validator.derive_dependency_refresh_status(
        clean, original_receipt=receipt, now=_NOW, repo_root=ROOT
    )["status"] == "DEPENDENCY_REFRESH_ADMITTED"
    # engine_scanner 被指到 postgres 角色:兩個檔案雜湊完全沒動,主體變了。
    drifted = _reseal({
        **receipt,
        "pg_role_topology": [
            {**row, "role_name": "postgres"} if row["component"] == "engine_scanner" else row
            for row in receipt["pg_role_topology"]
        ],
    })
    assert validator.s1_3_identity_projection(drifted) != (
        validator.s1_3_identity_projection(receipt)
    )
    assert validator.derive_dependency_refresh_status(
        build(
            drifted, reproducer_caller="E1:S2.4:W5-s1-3",
            reproducer_platform=dict(_PLATFORM), reproduced_at=_AT, repo_root=ROOT,
        ),
        original_receipt=drifted, now=_NOW, repo_root=ROOT,
    )["status"] == "DEPENDENCY_REFRESH_REJECTED"


@pytest.mark.parametrize(
    "delta,marker",
    [
        (["tests/structure/test_agent_governance_s2_4_acceptance_matrix.py"], "differ in content"),
        (None, "git is unreadable"),
    ],
)
def test_a_dirty_or_undecidable_owned_scope_breaks_the_w5_wave_exit(
    chain, monkeypatch, delta, marker
) -> None:
    """P1-C:``owned_scope_worktree_delta`` 折進投影卻沒有任何 reason 消費它。

    修正前:把 W5 自己新寫的驗收矩陣測試清空成一行註解,W0..W5 全數仍 PASS,而投影裡明明
    白白記著那個 delta。一份綁了 ``source_head`` 的 receipt 正是在宣稱「我的 owned scope 就
    在那個 head 上」;不可判定同樣 fail-closed。第三輪 P1-D 之後裁決住在共用的 wave-exit
    路徑(``validator._owned_scope_delta_reasons``),故本測試對著那把共用的尺。
    """

    _admission, _w0, _w1, _w2, _w3, _w4, w5 = chain
    monkeypatch.setattr(
        schema_core, "owned_scope_worktree_delta", lambda *_a, **_k: delta
    )
    reasons = [
        reason for reason in validator._wave_exit_structural_errors(w5)
        if reason.startswith(_OWNED_SCOPE_REASON)
    ]
    assert len(reasons) == 1, validator._wave_exit_structural_errors(w5)
    assert marker in reasons[0]
    # 髒 scope 的 reason 必須帶祈使句(operator 拿到的是「該做什麼」,不是三句理由)。
    if delta:
        assert "commit or revert these paths, then re-derive" in reasons[0]


def test_a_clean_owned_scope_emits_no_worktree_reason(chain, monkeypatch) -> None:
    """反向:owned scope 乾淨時那條 reason 必須消失(它不是一條恆真的 reason)。"""

    _admission, _w0, _w1, _w2, _w3, _w4, w5 = chain
    monkeypatch.setattr(
        schema_core, "owned_scope_worktree_delta", lambda *_a, **_k: []
    )
    assert not [
        reason for reason in validator._wave_exit_structural_errors(w5)
        if reason.startswith(_OWNED_SCOPE_REASON)
    ]


def _assert_wave_owned_paths_map_to_their_own_leaf() -> None:
    """第四輪 P2:``_WAVE_OWNED_PATHS`` 的**對應關係**本身沒有被釘住。

    下面那圈把 ``owned_scope_worktree_delta`` 整個 monkeypatch 掉,於是那把尺量的是「有沒有
    接線」,不是「接到哪一條線」;把 ``"W2"`` 指去 ``_W0_OWNED_PATHS``,整條 W5 lane 照樣全綠,
    而 W2 的 owned scope 就此無人看管(W2 擁有 operator 真正執行的那幾支腳本)。這裡逐波要求
    「同一個物件」,並額外要求六個投影兩兩相異——後者才擋得住 W0/W1 之間的互指。
    """

    import aiml_gate_receipt_wave_w2 as wave_w2
    import aiml_gate_receipt_wave_w3 as wave_w3
    import aiml_gate_receipt_wave_w4 as wave_w4
    import aiml_gate_receipt_wave_w5 as wave_w5

    canonical = {
        # W0/W1 的投影住在 facade 自身,W2..W5 住在各自的葉。
        "W0": validator._W0_OWNED_PATHS,
        "W1": validator._W1_OWNED_PATHS,
        "W2": wave_w2._W2_OWNED_PATHS,
        "W3": wave_w3._W3_OWNED_PATHS,
        "W4": wave_w4._W4_OWNED_PATHS,
        "W5": wave_w5._W5_OWNED_PATHS,
    }
    for wave, paths in canonical.items():
        assert validator._WAVE_OWNED_PATHS[wave] is paths, (
            f"_WAVE_OWNED_PATHS[{wave!r}] does not point at that wave's own owned-path "
            "projection; a mis-wired row leaves that wave's owned scope unwatched"
        )
    seen: dict[int, str] = {}
    for wave, paths in validator._WAVE_OWNED_PATHS.items():
        assert id(paths) not in seen, (wave, seen[id(paths)])
        seen[id(paths)] = wave


def test_every_wave_exit_consumes_its_own_owned_scope_delta(chain, monkeypatch) -> None:
    """P1-D:fail-closed 的 owned-scope 消費原本**只有 W5 有**(w2/w3/w4 consumed=0)。

    W2 擁有 operator 真正執行的四支腳本(``agent_governance_s2_4_install`` / ``_render`` /
    ``_sql_scan`` / ``_emit_sink``),所以一份綁了 ``source_head`` 的 W2 wave-exit 能從一棵
    那四支被本地改過的樹導出 PASS。刪掉 ``_wave_exit_structural_errors`` 裡那一行接線,本
    測試對 W0..W4 立刻轉紅。
    """

    admission, w0, w1, w2, w3, w4, w5 = chain
    receipts = {"W0": w0, "W1": w1, "W2": w2, "W3": w3, "W4": w4, "W5": w5}
    # 每一波的 owned-path 集合都真的被登記(漏一波 = 那一波無人看管)。
    assert sorted(validator._WAVE_OWNED_PATHS) == ["W0", "W1", "W2", "W3", "W4", "W5"]
    _assert_wave_owned_paths_map_to_their_own_leaf()
    assert validator.owned_scope_reason_prefix("W5") == _OWNED_SCOPE_REASON
    for wave, receipt in receipts.items():
        prefix = validator.owned_scope_reason_prefix(wave)
        for delta in ([f"{wave}/tampered.py"], None):
            monkeypatch.setattr(
                schema_core, "owned_scope_worktree_delta", lambda *_a, **_k: delta
            )
            named = [
                reason for reason in validator._wave_exit_structural_errors(receipt)
                if reason.startswith(prefix)
            ]
            assert len(named) == 1, (wave, delta, named)
        monkeypatch.setattr(
        schema_core, "owned_scope_worktree_delta", lambda *_a, **_k: []
    )
        assert not [
            reason for reason in validator._wave_exit_structural_errors(receipt)
            if reason.startswith(prefix)
        ], wave
        # 且它必須真的擋住 PASS,而不只是多印一行。
        monkeypatch.setattr(
            schema_core, "owned_scope_worktree_delta", lambda *_a, **_k: ["x.py"]
        )
        predecessors = {
            "W0": (None, ()), "W1": (w0, ()), "W2": (w1, (w0,)), "W3": (w2, (w0, w1)),
            "W4": (w3, (w0, w1, w2)), "W5": (w4, (w0, w1, w2, w3)),
        }[wave]
        assert validator.derive_wave_exit_status(
            receipt,
            source_admission_receipt=admission,
            predecessor_wave_receipt=predecessors[0],
            predecessor_wave_chain=predecessors[1],
        )["status"] == "NOT_PASS", wave


def test_every_folded_value_that_carries_a_claim_has_a_reason_level_consumer(
    chain, monkeypatch
) -> None:
    """P2-G:折進投影卻**沒有任何 reason 消費者**的值只是裝飾品。

    逐個把它反轉成假宣稱,``w5_structural_errors`` 都必須具名報出來。修正前這五個值反轉之後
    146 支 W5 lane 測試全綠:``s2_5_lifecycle_source_absent``(連測試級斷言都沒有)、
    ``pg_role_identity_live.grant_statement_count``、``inactive_postcheck_live`` 的兩組
    ``*_properties`` 與 ``aggregate_forbidden_methods``、``schema_registration_live``
    的 ``dependency_refresh_schema_key``。
    """

    import aiml_gate_receipt_wave_w5 as wave_w5

    _admission, _w0, _w1, _w2, _w3, _w4, w5 = chain
    baseline = validator.w5_exported_abi_projection()

    def _with(section: str, **overrides):
        projection = deepcopy(baseline)
        projection[section].update(overrides)
        monkeypatch.setattr(
            wave_w5, "w5_exported_abi_projection", lambda *_a, **_k: projection
        )
        return validator.w5_structural_errors(w5)

    for section, overrides, marker in (
        # PM O-1(2026-07-28)後 S2.5 source 已存在且 row 已標 CLOSED_BY_S2_5_SOURCE:
        # 反向假宣稱是「S2.5 source 不存在」——row 不再是 OUT_OF_WP4_SCOPE,該臂必須具名。
        ("inactive_postcheck_live", {"s2_5_lifecycle_source_files": [],
                                     "s2_5_lifecycle_source_absent": True},
         "does not record S2_5_LIFECYCLE_FIXTURES_DO_NOT_EXIST as OUT_OF_WP4_SCOPE"),
        ("inactive_postcheck_live", {"s2_5_lifecycle_source_absent": None},
         "cannot measure whether an S2.5 lifecycle source exists"),
        ("inactive_postcheck_live", {"aggregate_forbidden_methods": []},
         "forbidden-method inventory is empty"),
        ("inactive_postcheck_live", {"postcheck_properties": []},
         "exposes no properties at all"),
        ("inactive_postcheck_live", {"receipt_properties": []},
         "exposes no properties at all"),
        ("pg_role_identity_live", {"grant_statement_count": 0},
         "generates no statement at all"),
        ("schema_registration_live", {"dependency_refresh_schema_key": "something_else"},
         "is not the §10.1-named"),
    ):
        reasons = _with(section, **overrides)
        assert any(marker in reason for reason in reasons), (section, overrides, reasons)

    # 正向:未被動過的投影不得產生上述任何一條(它們不是恆真的 reason)。
    monkeypatch.setattr(
        wave_w5, "w5_exported_abi_projection", lambda *_a, **_k: deepcopy(baseline)
    )
    clean = validator.w5_structural_errors(w5)
    for marker in (
        "still records S2_5_LIFECYCLE_FIXTURES_DO_NOT_EXIST",
        "does not record S2_5_LIFECYCLE_FIXTURES_DO_NOT_EXIST",
        "forbidden-method inventory is empty",
        "exposes no properties at all",
        "generates no statement at all",
        "is not the §10.1-named",
    ):
        assert not any(marker in reason for reason in clean), (marker, clean)
    # 而 S2.5 的判定必須用同一個 glob(舊碼只看一個猜出來的檔名)——WP5 落地後
    # glob 必須命中 S2.5 設計正本(檔案消失=§10.5 #29 後半再度失去 owner=上方臂變紅)。
    assert baseline["inactive_postcheck_live"]["s2_5_lifecycle_source_files"] == [
        "S2.5-running-attestation-source-seam.md"
    ]


def test_no_wave_leaf_widens_the_scanner_namespace_at_import_time() -> None:
    """P2(PM ruling):W3/W4 葉在 import 期把 ``program_code`` 放進 sys.path。

    facade 的 top-level import 閉包一旦這麼做,engine-scanner 進程的 top-level namespace 就
    多出 broker_connectors / exchange_connectors / dashboard / ai_agents。§10.1.1 條件 4 禁的
    是**授予**父進程沒有的能力,移除它是**縮小**能力,故與該條件同向。
    """

    import ast

    for rel in (
        "program_code/ml_training/aiml_gate_receipt_s2_4_contracts.py",
        "program_code/ml_training/aiml_gate_receipt_wave_w3.py",
        "program_code/ml_training/aiml_gate_receipt_wave_w4.py",
        "program_code/ml_training/aiml_gate_receipt_wave_w5.py",
    ):
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        for node in tree.body:  # 只看 module 層級(函式內的開窗是允許的形)
            dumped = ast.dump(node)
            assert "sys.path" not in dumped.replace("'sys'", "").replace(
                "attr='path'", ""
            ) or "_PROGRAM_CODE_DIR" not in dumped, rel
            assert "_PROGRAM_CODE_DIR" not in dumped, rel
        assert "_PROGRAM_CODE_DIR" not in (ROOT / rel).read_text(encoding="utf-8"), rel


def test_the_s1_3_assurance_class_inflation_is_pinned_where_it_is_reachable() -> None:
    """E2/E3 分歧的實證裁決(第三輪):兩邊各對一半,而只有成對的組合走得到。

    E2 對:逐項單獨漂移 ``s1_3_identity_projection`` 排除的欄位,家族驗證器逐個抓到
    (2..16 個 error),只有 ``negative_acl_cases[].reason`` 與兩個 rotation 指紋槽存活。
    E3 對:assurance class **確實**可以在投影逐位元組不變的情況下由 STRUCTURAL_ONLY 抬到
    LOCAL_REPRODUCIBLE——但必須是**成對**的(socket ``mode_source`` + 對應的頂層
    ``evidence_class``),而一次一欄的掃法找不到那個組合。E3 對 ``_evidence_ceiling`` 輸入
    的描述在此 head 上不準確:它讀的是 ``_has_live_disposable_witness``(rotation proof 的
    ``observation_source`` 與 socket 的 ``mode_source``),不是逐 facet 的 ``evidence_class``。
    """

    import copy

    import agent_governance_identity_acl_contract as s1_3

    contract = s1_3.canonical_identity_acl_contract()
    base = s1_3.build_identity_acl_contract_receipt(
        caller="S1.3:probe",
        platform={"os": "darwin", "arch": "arm64", "postgres_version": "16.3"},
        target_class="disposable_local", contract=contract,
        observation_time="2026-07-01T00:00:00+00:00", ttl_seconds=1800,
        evidence_class="STRUCTURAL_ONLY",
    )

    def _refresh_status(receipt):
        refresh = validator.build_s2_4_dependency_refresh_attestation(
            receipt, reproducer_caller="E1:S2.4:W5-s1-3-ceiling",
            reproducer_platform=dict(_PLATFORM), reproduced_at=_AT, repo_root=ROOT,
        )
        return validator.derive_dependency_refresh_status(
            refresh, original_receipt=receipt, now=_NOW, repo_root=ROOT
        )["status"]

    assert _refresh_status(base) == "DEPENDENCY_REFRESH_ADMITTED"
    assert s1_3._evidence_ceiling(base) == "STRUCTURAL_ONLY"

    # (1) E2 的結果:逐項單獨漂移全被家族驗證器抓到。
    for mutate in (
        lambda r: r["socket_dir_acl"][0].__setitem__("mode", "0777"),
        lambda r: r["socket_dir_acl"][0].__setitem__("mode_source", "host_observation"),
        lambda r: r["secret_lifecycle"]["rotation"]["old_credential_rejection_proof"]
        .__setitem__("verdict", "ALLOWED"),
        lambda r: r.__setitem__("evidence_class", "RUNNING_ATTESTED"),
        lambda r: [x.__setitem__("evidence_class", "HOST_OBSERVED") for x in
                   r["host_uid_topology"]],
    ):
        drifted = copy.deepcopy(base)
        mutate(drifted)
        drifted = _reseal(drifted)
        assert validator.s1_3_identity_projection(drifted) == (
            validator.s1_3_identity_projection(base)
        )
        assert s1_3.validate_identity_acl_contract_receipt(drifted), drifted["evidence_class"]
        assert _refresh_status(drifted) == "DEPENDENCY_REFRESH_REJECTED"

    # (2) E3 的結果:成對的 mode_source + evidence_class 是**一致的**,家族驗證器零 error,
    #     投影逐位元組不變,而 assurance class 已被抬高。
    inflated = copy.deepcopy(base)
    inflated["socket_dir_acl"][0]["mode_source"] = "live_chmod_stat"
    inflated["evidence_class"] = "LOCAL_REPRODUCIBLE"
    inflated = _reseal(inflated)
    assert s1_3.validate_identity_acl_contract_receipt(inflated) == []
    assert validator.s1_3_identity_projection(inflated) == (
        validator.s1_3_identity_projection(base)
    )
    assert s1_3._evidence_ceiling(inflated) == "LOCAL_REPRODUCIBLE"
    assert s1_3._evidence_ceiling(base) == "STRUCTURAL_ONLY"
    assert _refresh_status(inflated) == "DEPENDENCY_REFRESH_ADMITTED"

    # (3) rotation 那條路走不到(live proof 另外要求新憑證已連線過)。
    rotation = copy.deepcopy(base)
    rotation["secret_lifecycle"]["rotation"]["old_credential_rejection_proof"][
        "observation_source"
    ] = "live_disposable_pg"
    rotation["evidence_class"] = "LOCAL_REPRODUCIBLE"
    rotation = _reseal(rotation)
    assert s1_3.validate_identity_acl_contract_receipt(rotation) != []
    assert _refresh_status(rotation) == "DEPENDENCY_REFRESH_REJECTED"

    # (4) 後果必須在冊,且逐字說出「LOCAL_REPRODUCIBLE 只是宣稱」。
    row = {
        r["obligation_id"]: r for r in validator.S2_4_W5_REMAINING_OWNED_OBLIGATIONS
    }["S1_3_ASSURANCE_CLASS_IS_INFLATABLE_WITHOUT_CHANGING_THE_PROJECTION"]
    assert "live_chmod_stat" in row["statement"]
    assert "negative_acl_cases[].reason" in row["statement"]


def test_the_owned_scope_delta_is_content_addressed_not_git_status(tmp_path) -> None:
    """P1-A:``git status`` 不是可靠的 oracle,而 ``source_head`` 也不是 HEAD。

    三個各自獨立的繞道,全部在一棵自建的小 repo 上實證:

    1. ``git update-index --assume-unchanged`` 讓被改過的檔案自 ``git status`` 消失;
    2. ``--skip-worktree`` 同理;
    3. ``git status`` 永遠比對 HEAD,故綁定的 ``source_head`` 是**前一個** commit 時,
       「與 HEAD 無差異」被舊碼當成了「與 bound commit 無差異」。

    修正前(``git status --porcelain`` 形)三個案例都回 ``[]``。
    """

    import aiml_gate_receipt_schema_core as core

    mini = tmp_path / "mini"
    (mini / "pkg").mkdir(parents=True)
    (mini / "pkg" / "a.py").write_text("ORIGINAL\n", encoding="utf-8")
    (mini / "pkg" / "b.py").write_text("B\n", encoding="utf-8")
    _seed_repo(mini, [])
    first = _git(mini, "rev-parse", "HEAD")
    owned = ("pkg/a.py", "pkg/b.py")
    assert core.owned_scope_worktree_delta(mini, owned) == []

    # (1) assume-unchanged:git status 看不見,內容定址看得見。
    (mini / "pkg" / "a.py").write_text("TAMPERED\n", encoding="utf-8")
    _git(mini, "update-index", "--assume-unchanged", "pkg/a.py")
    assert _git(mini, "status", "--porcelain") == ""
    assert core.owned_scope_worktree_delta(mini, owned) == ["pkg/a.py"]
    _git(mini, "update-index", "--no-assume-unchanged", "pkg/a.py")

    # (2) skip-worktree:同樣看不見。
    _git(mini, "update-index", "--skip-worktree", "pkg/a.py")
    assert _git(mini, "status", "--porcelain") == ""
    assert core.owned_scope_worktree_delta(mini, owned) == ["pkg/a.py"]
    _git(mini, "update-index", "--no-skip-worktree", "pkg/a.py")
    (mini / "pkg" / "a.py").write_text("ORIGINAL\n", encoding="utf-8")

    # (3) source_head ≠ HEAD:工作樹相對 HEAD 乾淨,相對 bound commit 並不乾淨。
    (mini / "pkg" / "b.py").write_text("B2\n", encoding="utf-8")
    _git(mini, "add", "-A")
    _git(mini, "commit", "-q", "-m", "second")
    assert _git(mini, "status", "--porcelain") == ""
    assert core.owned_scope_worktree_delta(mini, owned) == []
    assert core.owned_scope_worktree_delta(mini, owned, source_head=first) == ["pkg/b.py"]

    # 該 commit 根本沒有那個 blob → 同樣計入差異(fail-closed,不是靜默通過)。
    assert core.owned_scope_worktree_delta(mini, ("pkg/never.py",)) == ["pkg/never.py"]


def test_the_section_9_2_admission_verdict_has_no_production_call_site() -> None:
    """B:§9.2 的裁決今天零生產呼叫端——這是**被測量**的事實,不是被宣稱的。"""

    import agent_governance_s2_4_host_identity as host

    live = validator.w5_exported_abi_projection()["refresh_call_site_live"]
    assert live["production_call_sites"] == []
    assert live["apply_time_consumer_derives_freshness"] is False
    # 唯一在 APPLY 期消費 §9.2 source 身分的地方:讀 repo 固定路徑的 S2.3 artifact,
    # 只驗 status / self_digest / 三個身分欄位,對 expires_at 一個字都沒有。
    assert host.s2_3_expected_identity_reasons() == []
    assert "expires_at" not in host.s2_3_expected_identity_reasons.__code__.co_consts
    # 而那三份 receipt 本身是**真的過期**的,中央閘照樣零 error(§9.2 的規則今天沒有執法點)。
    import json

    for rel in (
        _S2_2A_V1, _S2_3_EXPECTED,
        "docs/execution_plan/ai_ml_landing/receipts/S2.3-sealed-build-receipt-v1.json",
    ):
        artifact = json.loads((ROOT / rel).read_text(encoding="utf-8"))
        assert validator.validate_aiml_artifact(artifact, now=_NOW) == [], rel


@pytest.mark.parametrize(
    "obligation_id",
    [
        "SOURCE_IDENTITY_FRESHNESS_HAS_NO_PRODUCTION_CALL_SITE",
        "EMITTED_EVIDENCE_DIGESTS_ARE_UNAUTHENTICATED",
    ],
)
def test_a_deleted_honest_obligation_breaks_the_w5_wave_exit(
    chain, monkeypatch, obligation_id
) -> None:
    """B/D:兩條誠實面義務被靜默刪掉時 ``w5_structural_errors`` 必須具名報出來。

    這條閂是接進 wave-exit 的,不只是投影裡的一個值:把 ``_honest_surface_reasons`` 的接線
    從 ``w5_structural_errors`` 拿掉,本測試轉紅。
    """

    import aiml_gate_receipt_wave_w5 as wave_w5

    _admission, _w0, _w1, _w2, _w3, _w4, w5 = chain
    kept = [
        row for row in wave_w5._W5_EXPORTED_ABI["remaining_owned_obligations"]
        if row["obligation_id"] != obligation_id
    ]
    monkeypatch.setitem(wave_w5._W5_EXPORTED_ABI, "remaining_owned_obligations", kept)
    reasons = validator.w5_structural_errors(w5)
    assert any(
        f"W5 does not record {obligation_id}" in reason for reason in reasons
    ), reasons


def _call_site_measurement(**overrides) -> dict:
    measured = {
        "production_call_sites": [],
        "production_call_site_scan_roots": ["helper_scripts/maintenance_scripts", "program_code"],
        "production_call_site_definition_sites": [],
        "production_call_site_modules_scanned": 717,
        "production_call_site_undecidable_modules": [],
        "apply_time_consumer": "x",
        "apply_time_consumer_derives_freshness": False,
    }
    measured.update(overrides)
    return measured


_EVIDENCE_MEASUREMENT = {
    "only_shape_is_constrained": True,
    "emit_sink_accepts_fabricated_evidence": True,
    "emit_sink_refuses_empty_evidence": True,
    "emit_sink_refuses_secret_like_evidence": True,
}


def test_a_wired_call_site_must_close_the_obligation_instead_of_carrying_it() -> None:
    """B 的另一半閂:有人把閘接進 APPLY 之後,那條義務必須被關掉而不是永遠掛著。"""

    import aiml_gate_receipt_wave_w5 as wave_w5

    reasons = wave_w5._honest_surface_reasons(
        _call_site_measurement(
            production_call_sites=[
                "helper_scripts/maintenance_scripts/agent_governance_s2_4_host_identity.py"
            ],
            apply_time_consumer_derives_freshness=True,
        ),
        dict(_EVIDENCE_MEASUREMENT),
    )
    assert any("close the obligation instead" in reason for reason in reasons), reasons


@pytest.mark.parametrize(
    "call_site_overrides",
    [
        {"production_call_sites": None},
        {"production_call_site_modules_scanned": 0},
        {"production_call_site_undecidable_modules": ["helper_scripts/x.py"]},
        {"apply_time_consumer_derives_freshness": None},
    ],
)
def test_an_ambiguous_call_site_measurement_can_never_demand_deleting_the_row(
    call_site_overrides,
) -> None:
    """P1-E:量測失敗 / 含糊**永遠**落在「不可關閉」那一臂,絕不落在「必須關閉」。

    舊閂是 ``if f"{name}(" in text`` 施於原始檔案文字、非遞迴、單一目錄:一句提到該名字的
    **註解**就讓 ``production_call_sites`` 變非空,而那條閂的下一臂寫著「close the obligation
    instead」——於是一個誤報會逼人刪掉一條仍然為真的誠實列。反向同樣是拒絕原語:同一句註解
    配上那一列還在冊,就強制 NOT_PASS。
    """

    import aiml_gate_receipt_wave_w5 as wave_w5

    reasons = wave_w5._honest_surface_reasons(
        _call_site_measurement(**call_site_overrides), dict(_EVIDENCE_MEASUREMENT)
    )
    assert any("cannot measure whether" in reason for reason in reasons), reasons
    assert not any("close the obligation instead" in reason for reason in reasons), reasons


def test_a_comment_mentioning_the_entry_point_is_not_a_call_site(tmp_path) -> None:
    """P1-E 的具體誤報形:註解 / 字串 / 定義都不是呼叫,``ast.Call`` 才是。"""

    import aiml_gate_receipt_wave_w5 as wave_w5

    entry = wave_w5._REFRESH_ADMISSION_ENTRY
    for source, expected in (
        (f"# see {entry}() for the §9.2 verdict\n", False),
        (f'DOC = "{entry}("\n', False),
        (f"def {entry}(**kwargs):\n    return None\n", False),
        (f"x = {entry}(evidence_class='X')\n", True),
        (f"x = facade.{entry}(evidence_class='X')\n", True),
    ):
        path = tmp_path / "probe.py"
        path.write_text(source, encoding="utf-8")
        assert wave_w5._module_calls_the_name(path, entry) is expected, source
    broken = tmp_path / "broken.py"
    broken.write_text("def (:\n", encoding="utf-8")
    assert wave_w5._module_calls_the_name(broken, entry) is None


def test_a_documentation_only_schema_edit_does_not_flip_the_evidence_latch(
    monkeypatch,
) -> None:
    """P1-E:``$defs/digest`` 加一句 ``description`` 是純文件編輯,不是認證性約束。

    舊版是鍵集合比對(``in (["pattern","type"], ["type"])``),於是那句 description 會把
    ``only_shape_is_constrained`` 翻成 False,而下一臂寫著「close the obligation instead」。
    """

    import aiml_gate_receipt_wave_w5 as wave_w5

    facade = validator
    original = facade._load_schema

    def _annotated(schema_version: str):
        schema = original(schema_version)
        if schema_version == "s2_4_wave_exit_receipt_v1":
            schema["$defs"]["digest"]["description"] = "a sha256 content digest"
        return schema

    monkeypatch.setattr(facade, "_load_schema", _annotated)
    live = wave_w5._evidence_authenticity_live()
    assert live["only_shape_is_constrained"] is True, live
    reasons = wave_w5._honest_surface_reasons(_call_site_measurement(), live)
    assert not any("close the obligation instead" in reason for reason in reasons), reasons

    # 反向:出現一個既非註解也非形狀的關鍵字 → 無法判定 → 只能走 fail-closed 臂。
    def _unknown(schema_version: str):
        schema = original(schema_version)
        if schema_version == "s2_4_wave_exit_receipt_v1":
            schema["$defs"]["digest"]["x-attestor-binding"] = "required"
        return schema

    monkeypatch.setattr(facade, "_load_schema", _unknown)
    live = wave_w5._evidence_authenticity_live()
    assert live["only_shape_is_constrained"] is None, live
    reasons = wave_w5._honest_surface_reasons(_call_site_measurement(), live)
    assert any("cannot measure what constrains" in reason for reason in reasons), reasons
    assert not any("close the obligation instead" in reason for reason in reasons), reasons


def test_a_stricter_emit_sink_never_demands_deleting_a_still_true_evidence_row() -> None:
    """第四輪 P2:latch-D 的誤報換了一條路徑活著——關閉臂綁在**空對照組**上。

    reviewer 的變異:在 ``agent_governance_s2_4_emit_sink.validate_emit_evidence`` 加一句良性
    形狀檢查(``if "command" not in test_evidence: raise ValueError(...)``)。它把
    ``emit_sink_accepts_fabricated_evidence`` 翻成 False,舊碼於是掉到最後一臂,吐出
    「the evidence digests are no longer shape-only; close the obligation instead」——而同一份
    投影裡 ``only_shape_is_constrained`` 仍是 ``True``。訊息是假的,而它的處方是刪掉一條仍為
    真的誠實列(這正是 P1-E 修過一次、又從另一個輸入復活的同一個誤報形)。
    """

    import aiml_gate_receipt_wave_w5 as wave_w5

    stricter = dict(_EVIDENCE_MEASUREMENT, emit_sink_accepts_fabricated_evidence=False)
    reasons = wave_w5._honest_surface_reasons(_call_site_measurement(), stricter)
    assert not any("close the obligation instead" in r for r in reasons), reasons
    # 對照組翻面 = 量測不再成立 → fail-closed(而不是「必須關閉」)。
    assert any("not a real predicate" in r for r in reasons), reasons
    # 反向:只有**主體**(schema 真的長出非形狀性約束)翻成 False 才可以要求關閉這一列。
    subject_false = dict(_EVIDENCE_MEASUREMENT, only_shape_is_constrained=False)
    reasons = wave_w5._honest_surface_reasons(_call_site_measurement(), subject_false)
    assert any("close the obligation instead" in r for r in reasons), reasons
    # 三個 sink 探針現在是同一組對照:任一翻面都走 fail-closed 臂,語義一致。
    for probe in (
        "emit_sink_refuses_empty_evidence",
        "emit_sink_refuses_secret_like_evidence",
        "emit_sink_accepts_fabricated_evidence",
    ):
        flipped = dict(_EVIDENCE_MEASUREMENT)
        flipped[probe] = False
        reasons = wave_w5._honest_surface_reasons(_call_site_measurement(), flipped)
        assert any("not a real predicate" in r for r in reasons), (probe, reasons)
        assert not any("close the obligation instead" in r for r in reasons), (probe, reasons)


def test_the_wave_exit_evidence_digests_are_shape_only(chain) -> None:
    """D:整條 W0→W5 鏈在 ``sha256:111…1`` 上導出 PASS——它證不了測試跑過或審查發生過。"""

    admission, w0, w1, w2, w3, w4, _w5 = chain
    live = validator.w5_exported_abi_projection()["evidence_authenticity_live"]
    assert live["only_shape_is_constrained"] is True
    assert live["emit_sink_accepts_fabricated_evidence"] is True
    # 正對照:守衛不是恆真的(空 evidence 與帶秘密的 evidence 都真的被擋)。
    assert live["emit_sink_refuses_empty_evidence"] is True
    assert live["emit_sink_refuses_secret_like_evidence"] is True
    fabricated = validator.build_w5_wave_exit_receipt(
        admission, w4,
        test_digests=["sha256:" + "1" * 64], capture_digests=["sha256:" + "1" * 64],
        review_fragment_digests=["sha256:" + "1" * 64],
    )
    # 中央閘對這份「全部捏造」的 evidence 沒有任何話說;唯一擋住它的是 owned scope 那一條。
    assert _non_worktree_reasons(validator.validate_aiml_artifact(fabricated)) == []
    entry = _W5_ROWS["EMITTED_EVIDENCE_DIGESTS_ARE_UNAUTHENTICATED"]
    assert "cannot authenticate its own execution" in entry["statement"]
    assert "ORCHESTRATOR_BOUND" in entry["statement"]


def test_expected_topology_is_plan_derived_and_no_longer_caller_suppliable() -> None:
    """E(S2.4-AMEND-2 後):PG row 的 ``expected_topology`` 由簽章 plan 導出,caller 無入口。

    本測試在 AMEND-2 之前斷言的是弱化路徑本身(allowlist 有 expected_topology、五個
    ``expected.get(field) is not None`` 缺鍵靜默跳過);source 收口後改釘**關閉後的形**,
    任一半被回退(key 回到 allowlist / 缺鍵守衛形復活)即紅。"""

    import agent_governance_s2_4_install_driver as runner
    import agent_governance_s2_4_topology as topology

    assert "expected_topology" not in runner.ROW_PAYLOAD_ALLOWLIST["PG_ROLE_ACL_MIGRATION"]
    assert "hba_delta" in runner.ROW_PAYLOAD_ALLOWLIST["PG_ROLE_ACL_MIGRATION"]
    # 簽過的 component intent 對 PG row 仍只要求四個 digest(row ABI 一字不改)。
    schema = validator._load_schema("s2_4_component_effect_intent_v1")
    pg_branch = next(
        branch for branch in schema["allOf"]
        if branch["if"]["properties"]["component_effect_class"]["const"]
        == "PG_ROLE_ACL_MIGRATION"
    )
    required = pg_branch["then"]["properties"]["required_intent_fields"]["required"]
    assert sorted(required) == [
        "acl_manifest_digest", "admin_handle_descriptor_digest",
        "pg_migration_permit_digest", "topology_attestation_digest",
    ]
    # 葉層五鍵 fail-closed:缺鍵靜默跳過的守衛形已不存在,缺鍵即具名 reason。
    source = (
        ROOT / "helper_scripts/maintenance_scripts/agent_governance_s2_4_topology.py"
    ).read_text(encoding="utf-8")
    assert source.count("expected.get(field) is not None") == 0
    assert "expected baseline is missing" in source
    assert topology.derive_pg_topology_status(
        {"schema_version": "pg_topology_attestation_v1"}, expected={}, now=None
    )["status"] == topology.TOPOLOGY_STATUS_UNPROVEN
    # 導出來源正是義務列點名的兩個簽章欄位(plan-derived 而非 code-owned/caller-owned)。
    plan_core = validator._load_schema("s2_4_install_plan_core_v1")
    assert {"topology_pre_digest", "hba_delta_digest"} <= set(plan_core["properties"])
    assert callable(runner.derive_plan_expected_topology)
    assert callable(runner.hba_delta_plan_binding_digest)
    entry = _W5_ROWS["EXPECTED_TOPOLOGY_IS_CALLER_SUPPLIED_AND_UNSIGNED"]
    assert "hba_delta_digest" in entry["statement"]


@pytest.mark.parametrize(
    "leaf",
    [
        # 第四輪 P1:**facade 本身**必須先入列。逐葉迴圈是第五處(wave_w2)藏身的地方——
        # 它不在被點名的葉清單裡,卻是 facade 的 top-level import,於是「載入 facade 的
        # 進程不被加寬」這句話在 round 3 是被宣稱而非被量測的。
        "aiml_gate_receipt_validator",
        "aiml_gate_receipt_s2_4_contracts",
        "aiml_gate_receipt_wave_w2",
        "aiml_gate_receipt_wave_w3",
        "aiml_gate_receipt_wave_w4",
        "aiml_gate_receipt_wave_w5",
    ],
)
def test_the_w5_leaves_do_not_widen_the_top_level_namespace_at_import_time(leaf) -> None:
    """§10.1.1 #4:facade 及其 import 閉包在 import 期都不得把 ``program_code`` 放進 sys.path。

    舊版只掃兩支葉、且從不 import facade,所以第五處(``aiml_gate_receipt_wave_w2``,facade 的
    top-level import)整輪沒被看見,而義務列卻寫著「process-level property IS achieved」。
    現在逐項量測:路徑本身不得出現,四個 top-level 套件也不得變成 find_spec 可解析——後者才是
    這條義務真正在講的能力面(路徑進來、套件跟著可匯入)。

    誠實邊界:本測試量的是 facade 的 import 閉包。engine-scanner **launcher** 仍可能自己把
    program_code 放上去(閉包裡有十五支模組以 package 形匯入 ml_training.*),那是決策而非
    副作用,不在本條之內——義務列逐字寫著同一句。
    """

    import subprocess

    probe = subprocess.run(
        [
            sys.executable, "-c",
            "import sys, os, importlib.util as u;sys.path.insert(0, %r);import %s;"
            "print(%r in [os.path.abspath(p) for p in sys.path]);"
            "print([n for n in ('broker_connectors','exchange_connectors','dashboard',"
            "'ai_agents') if u.find_spec(n) is not None])"
            % (str(ML_ROOT), leaf, str(PROGRAM_CODE)),
        ],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert probe.returncode == 0, probe.stderr
    on_path, resolvable = probe.stdout.strip().splitlines()
    assert on_path == "False", (leaf, probe.stdout)
    assert resolvable == "[]", (leaf, probe.stdout)


def test_w5_builds_a_receipt_without_writing_anything(tmp_path, chain) -> None:
    """建構 ≠ 發射:``build_w5_wave_exit_receipt`` 只回記憶體物件、零檔案副作用。

    (本檔早先版本把「W5 不擁有發射器」也寫進這支測試。那是當時的事實,不是設計:§10.3 首句
    要求**每個** source wave 發射 ``s2_4_wave_exit_receipt_v1``,而 W0-W4 都有持久化 receipt。
    發射器落地後那兩條斷言被移除,builder 純度這條仍然承重——發射面必須留在發射葉裡。)
    """

    admission, _w0, _w1, _w2, _w3, w4, _w5 = chain
    before = sorted(p.name for p in tmp_path.iterdir())
    receipt = validator.build_w5_wave_exit_receipt(admission, w4, **deepcopy(_EVID))
    assert receipt["wave"] == "W5"
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    # builder 自身仍不得攜帶任何持久化面。
    import aiml_gate_receipt_wave_w5 as wave_w5

    assert not hasattr(wave_w5, "emit_w5_receipts")


# ── §10.1.2 (d):(b) 具名清單 vs 活 owned-path 投影 ────────────────────────────
_DESIGN_DOC = ROOT / "docs/execution_plan/ai_ml_landing/design/S2.4-install-source-seams.md"


def _design_section_fence_opens(lines: list[str], start: int) -> list[int]:
    """某標題所轄區段(止於下一個圍欄外的標題)內,所有 ```text 圍欄的開頭行號。"""

    opens: list[int] = []
    in_fence = False
    for n in range(start + 1, len(lines)):
        stripped = lines[n].strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            if in_fence and stripped == "```text":
                opens.append(n)
        elif not in_fence and lines[n].startswith("#"):
            break
    return opens


def _design_fenced_paths(heading_prefix: str, doc_text: str | None = None) -> list[str]:
    """從設計文件某個標題所轄區段的**唯一** ```text 圍欄逐行解析路徑清單。

    兩份清單都**解析**而不是抄寫:硬編副本正是本修正案要擋的漂移,一份被抄進測試的清單
    只會在文件與測試一起改壞時保持綠燈。
    """

    text = _DESIGN_DOC.read_text(encoding="utf-8") if doc_text is None else doc_text
    lines = text.splitlines()
    # 第四輪 P2:舊碼取**第一個**符合的標題,於是文件前段再放一個 ``#### 10.1.2 `` 誘餌節,
    # 讀到的就是誘餌而不是權威節。標題必須唯一,不唯一即拒絕解析(fail-closed)。
    starts = [n for n, line in enumerate(lines) if line.startswith(heading_prefix)]
    assert len(starts) == 1, (
        f"design heading is not unique: {heading_prefix!r} matches {len(starts)} lines "
        f"{[lines[n] for n in starts]}; a decoy section would be parsed instead of the "
        "authoritative one"
    )
    start = starts[0]
    # 第五輪 P2:標題唯一之後誘餌就改放**第二個圍欄**——舊碼取區段內第一個 ```text 圍欄,
    # 權威圍欄被掏空成一條路徑照樣全綠。圍欄在區段內同樣必須唯一,零個或多個都拒絕解析。
    opens = _design_section_fence_opens(lines, start)
    assert len(opens) == 1, (
        f"expected exactly one ```text fence under {heading_prefix!r}, found "
        f"{len(opens)} at lines {[n + 1 for n in opens]}; a decoy fence would shadow "
        "the authoritative block"
    )
    open_fence = opens[0]
    close_fence = next(
        (n for n in range(open_fence + 1, len(lines)) if lines[n].strip() == "```"), None
    )
    assert close_fence is not None, f"unterminated ```text fence under {heading_prefix!r}"
    return [line.strip() for line in lines[open_fence + 1:close_fence] if line.strip()]


def _measured_out_of_list_union() -> set[str]:
    """W3∪W4∪W5 活投影,扣掉 §10.1 逐字清單 = 修正案 (b) 段該具名的那一組。"""

    union = (
        set(validator._W3_OWNED_PATHS)
        | set(validator._W4_OWNED_PATHS)
        | set(validator._W5_OWNED_PATHS)
    )
    return union - set(_design_fenced_paths("### 10.1 Exact owned-path allowlist"))


def test_10_1_2_b_block_is_a_hard_superset_of_the_measured_owned_path_union() -> None:
    """斷言 1(承重方向):量到的 out-of-list 路徑**每一條**都必須在 (b) 段被具名。

    這是 §10.1.2 (d) 的執行面:worker 自己寫的 ``_WX_OWNED_PATHS`` 投影不能自證 scope,
    新增一條沒有對應 (b) 條目的 out-of-list 路徑即 drift,而且必須在**測試**上變紅,
    不是留給 review 眼力。
    """

    named = _design_fenced_paths("#### 10.1.2 ")
    unnamed = sorted(_measured_out_of_list_union() - set(named))
    assert not unnamed, (
        "§10.1.2 (d):下列 owned path 在 W3/W4/W5 投影裡但沒有在 §10.1.2 (b) 段被具名——"
        f"依 (d) 條這是 drift,需 PM 具名而非 worker 自行擴表:{unnamed}"
    )


def test_10_1_2_b_block_names_nothing_that_exists_but_is_unowned() -> None:
    """斷言 2(窄反向):(b) 段裡**檔案真的存在**的條目,必須落在活投影聯集內。

    為什麼是窄反向而不是全等——刪檔/改名是 §10.1.1 條件 1 允許的重構,全等之下唯一回綠的
    路徑會變成「編設計文件」,而 §10.4 恰好把 owned-path scope 排除在 worker 可選之外;
    全等會讓這條規則在它最可能遇到的情況下自我失效。

    窄反向仍保住抗俘獲性:一個懸空的名字不能被悄悄拿去裝未經審查的內容,因為只要那個檔案
    被重建,斷言 2 立刻重新武裝。永久刪除留下的是一個惰性名字——(a) 條已經中和了它(「Presence
    in one is not authorising either」),而投影那一側早就有既有的
    ``dead = [rel for rel in _WX_OWNED_PATHS if not (ROOT / rel).is_file()]`` 檢查在掃。
    """

    named = _design_fenced_paths("#### 10.1.2 ")
    union = _measured_out_of_list_union()
    live_but_unowned = sorted(
        rel for rel in named if (ROOT / rel).is_file() and rel not in union
    )
    assert not live_but_unowned, (
        "§10.1.2 (b) 具名了存在於磁碟但不在任何 W3/W4/W5 owned-path 投影內的路徑:"
        f"{live_but_unowned}"
    )


def test_10_1_2_b_block_is_sorted_and_duplicate_free() -> None:
    """斷言 3:(b) 段本身必須是排序且無重複的清單(可審、可 diff、不能靠重複灌水)。"""

    named = _design_fenced_paths("#### 10.1.2 ")
    duplicates = sorted({rel for rel in named if named.count(rel) > 1})
    assert not duplicates, f"§10.1.2 (b) 具名清單有重複條目:{duplicates}"
    assert named == sorted(named), "§10.1.2 (b) 具名清單必須逐行排序"


def test_10_1_2_parser_refuses_a_decoy_fence_under_the_authoritative_heading() -> None:
    """第五輪 P2-1 的逐字重演:在唯一且權威的標題底下插第二個 ```text 圍欄(真清單的
    複本),再把權威圍欄掏空成一條路徑。舊碼取區段內**第一個**圍欄,於是上面三支 (d)
    測試連同整條 lane 實測 150 passed 全綠;刪掉圍欄唯一性斷言本測試即由紅轉綠。
    """

    lines = _DESIGN_DOC.read_text(encoding="utf-8").splitlines()
    head = next(n for n, s in enumerate(lines) if s.startswith("#### 10.1.2 "))
    opened = _design_section_fence_opens(lines, head)[0]
    closed = next(n for n in range(opened + 1, len(lines)) if lines[n].strip() == "```")
    real = lines[opened + 1:closed]
    tampered = (
        lines[:head + 1] + ["", "```text"] + real + ["```", ""]
        + lines[head + 1:opened + 1] + real[:1] + lines[closed:]
    )
    # 對照組:同一支解析器讀未竄改的文字仍須給出權威的那一份清單(否則本測試會空轉綠)。
    assert _design_fenced_paths("#### 10.1.2 ", "\n".join(lines)) == [
        s.strip() for s in real if s.strip()
    ]
    with pytest.raises(AssertionError, match="exactly one ```text fence"):
        _design_fenced_paths("#### 10.1.2 ", "\n".join(tampered))


def test_10_1_2_parser_refuses_a_decoy_heading() -> None:
    """第四輪加的標題唯一性斷言自己沒有任何測試(第五輪 P2-2):換成裸 ``starts[0]``,
    整條 W5 lane 實測 114 passed 逐位元組不變。誘餌標題帶一個只剩一條路徑的圍欄即重現。
    """

    lines = _DESIGN_DOC.read_text(encoding="utf-8").splitlines()
    head = next(n for n, s in enumerate(lines) if s.startswith("#### 10.1.2 "))
    decoy = [lines[head], "", "```text", _design_fenced_paths("#### 10.1.2 ")[0], "```", ""]
    with pytest.raises(AssertionError, match="heading is not unique"):
        _design_fenced_paths("#### 10.1.2 ", "\n".join(lines[:head] + decoy + lines[head:]))


# §10.1.2 (d) 只約束 W3/W4/W5(「From this amendment, a wave that creates a path outside
# §10.1's literal list must name it in the (b) block」),W0/W1/W2 的 out-of-list 路徑由
# §10.1.1 的追認散文覆蓋。於是 W0/W1/W2 那一側**完全沒有測試在看**:新增一條 out-of-list
# 路徑不會弄紅任何東西。把設計文件補成涵蓋 W0-W2 屬 §10.4 排除 worker 的 owned-path scope
# 決策,所以這裡改為把**現況缺口**釘死:缺口不得長大(新增即紅),縮小則要求同步更新本表。
# 下面每一條都是量出來的,不是抄的——重跑
#   set(W0∪W1∪W2) - §10.1 逐字清單 - §10.1.2 (b) 具名清單
# 即得。
_W0_W2_OUT_OF_LIST_UNNAMED = frozenset({
    "helper_scripts/deploy/openclaw-alr-candidate-policy.template.json",
    "helper_scripts/maintenance_scripts/agent_governance_pg_observer_bootstrap.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_emit_sink.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_sql_scan.py",
    "program_code/ml_training/aiml_gate_receipt_adoption.py",
    "program_code/ml_training/aiml_gate_receipt_classifiers.py",
    "program_code/ml_training/aiml_gate_receipt_wave_w2.py",
    "program_code/ml_training/alr_application_identity.py",
    "program_code/ml_training/alr_candidate_board_events.py",
    "program_code/ml_training/alr_consumer_write_metrics.py",
    "program_code/ml_training/alr_retention_runner.py",
    "program_code/ml_training/edge_feature_schema_contract.py",
    "program_code/ml_training/schemas/aiml_gate_receipts/"
    "application_bundle_runtime_closure_v1.schema.json",
    "program_code/ml_training/schemas/aiml_gate_receipts/"
    "pg_observer_bootstrap_result_v1.schema.json",
    "program_code/ml_training/tests/aiml_gate_receipt_validator_testkit.py",
    "program_code/ml_training/tests/test_aiml_gate_receipt_validator_adoption.py",
    "program_code/ml_training/tests/test_alr_application_identity.py",
    "program_code/ml_training/tests/test_alr_candidate_board_events.py",
    "program_code/ml_training/tests/test_alr_candidate_full_chain.py",
    "program_code/ml_training/tests/test_alr_consumer_resilience.py",
    "program_code/ml_training/tests/test_alr_retention_runner.py",
    "tests/structure/test_agent_governance_pg_observer_bootstrap.py",
    "tests/structure/test_agent_governance_s2_4_consumer_resilience_disposable.py",
    "tests/structure/test_agent_governance_s2_4_install_application_bundle.py",
    "tests/structure/test_agent_governance_s2_4_install_engine_scanner.py",
    "tests/structure/test_agent_governance_s2_4_install_engine_scanner_disposable.py",
    "tests/structure/test_agent_governance_s2_4_install_render.py",
    "tests/structure/test_learning_runtime_manifest_source_static.py",
    "tests/structure/test_s2_4_w0_admission.py",
})


def test_the_w0_w2_out_of_list_gap_is_pinned_and_cannot_grow() -> None:
    """第四輪 P2:``_measured_out_of_list_union`` 只涵蓋 W3∪W4∪W5。

    於是 W0/W1/W2 的投影可以長出一條全新的 out-of-list 路徑而不弄紅任何東西——正是 (d) 條
    要擋的那件事,只是換一波。把它補進 (d) 的承重斷言需要在 §10.1.2 (b) 段具名 29 條路徑,
    而 §10.4 把 owned-path scope 排除在 worker 可選之外,所以這裡不編文件、改釘缺口:
    多一條 = 紅(未被任何具名機制覆蓋的新 scope),少一條 = 也紅(要求把本表一起收斂)。
    """

    union = (
        set(validator._W0_OWNED_PATHS)
        | set(validator._W1_OWNED_PATHS)
        | set(validator._W2_OWNED_PATHS)
    )
    measured = (
        union
        - set(_design_fenced_paths("### 10.1 Exact owned-path allowlist"))
        - set(_design_fenced_paths("#### 10.1.2 "))
    )
    assert measured == set(_W0_W2_OUT_OF_LIST_UNNAMED), {
        "new_and_unnamed_anywhere": sorted(measured - _W0_W2_OUT_OF_LIST_UNNAMED),
        "pinned_but_no_longer_measured": sorted(_W0_W2_OUT_OF_LIST_UNNAMED - measured),
    }
