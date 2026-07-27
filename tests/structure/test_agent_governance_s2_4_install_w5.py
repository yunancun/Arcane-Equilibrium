"""S2.4(WP4·W5)wave-exit 中央導出的 focused 測試(§10.3 W5 row / §10.5 #27)。

證明:

- W5 wave-exit 於當前 checkout 自足再導出(結構 + 鏈綁定),且中央閘接受它;
- 竄改鏈上任一環(W4 receipt / W5 predecessor digest / owned-path 或 ABI 投影 / 非當前
  HEAD / caller 自證 status / 缺 chain)一律 NOT_PASS;
- W5 exported-ABI 折入的六組活裁決確實可再導出——它們就是 W5 補上的六條 §10.5 覆蓋缺口,
  任何一條的 source 面被弱化,``w5_structural_errors`` 必然給出具名 reason;
- W4 交出的十二項義務逐條被帶到 W5 且 owner 不被偷偷降級;W5 自審新增的四項以同一誠實形狀
  記錄;
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
    "PROGRAM_CODE_IS_ON_THE_SCANNER_PATH_VIA_W4",
    "PR_SET_DUMPABLE_IS_DECLARED_NOT_ENFORCED",
    "S2_5_LIFECYCLE_FIXTURES_DO_NOT_EXIST",
    # W5 對抗審計第二輪(2026-07-27)新記三條:§9.2 裁決零生產呼叫端、wave-exit evidence
    # digest 不可認證、PG row 的 expected_topology 是 caller 可弱化且未被簽的輸入。
    "EMITTED_EVIDENCE_DIGESTS_ARE_UNAUTHENTICATED",
    "EXPECTED_TOPOLOGY_IS_CALLER_SUPPLIED_AND_UNSIGNED",
    "SOURCE_IDENTITY_FRESHNESS_HAS_NO_PRODUCTION_CALL_SITE",
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
    required = {
        "program_code/ml_training/aiml_gate_receipt_validator.py",
        "program_code/ml_training/aiml_gate_receipt_wave_w5.py",
        "program_code/ml_training/application_bundle_runtime_closure_v1.json",
        "tests/structure/test_agent_governance_s2_4_acceptance_matrix.py",
        "tests/structure/test_agent_governance_s2_4_install_w5.py",
    }
    missing = required - set(validator._W5_OWNED_PATHS)
    assert not missing, f"W5 owned-path binding misses W5 surface members: {sorted(missing)}"
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
    for row in rows:
        assert row["owner_wave"] in {"PM", "S2.5A", "W6", "W6B"}, row["obligation_id"]


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
        (["tests/structure/test_agent_governance_s2_4_acceptance_matrix.py"], "differ from"),
        (None, "undecidable"),
    ],
)
def test_a_dirty_or_undecidable_owned_scope_breaks_the_w5_wave_exit(
    chain, monkeypatch, delta, marker
) -> None:
    """P1-C:``owned_scope_worktree_delta`` 折進投影卻沒有任何 reason 消費它。

    修正前:把 W5 自己新寫的驗收矩陣測試清空成一行註解,W0..W5 全數仍 PASS,而投影裡明明
    白白記著那個 delta。一份綁了 ``source_head`` 的 receipt 正是在宣稱「我的 owned scope 就
    在那個 head 上」;不可判定同樣 fail-closed。
    """

    import aiml_gate_receipt_wave_w5 as wave_w5

    _admission, _w0, _w1, _w2, _w3, _w4, w5 = chain
    monkeypatch.setattr(wave_w5, "owned_scope_worktree_delta", lambda *_a, **_k: delta)
    reasons = [
        reason for reason in validator.w5_structural_errors(w5)
        if reason.startswith(_OWNED_SCOPE_REASON)
    ]
    assert len(reasons) == 1, validator.w5_structural_errors(w5)
    assert marker in reasons[0]


def test_a_clean_owned_scope_emits_no_worktree_reason(chain, monkeypatch) -> None:
    """反向:owned scope 乾淨時那條 reason 必須消失(它不是一條恆真的 reason)。"""

    import aiml_gate_receipt_wave_w5 as wave_w5

    _admission, _w0, _w1, _w2, _w3, _w4, w5 = chain
    monkeypatch.setattr(wave_w5, "owned_scope_worktree_delta", lambda *_a, **_k: [])
    assert not [
        reason for reason in validator.w5_structural_errors(w5)
        if reason.startswith(_OWNED_SCOPE_REASON)
    ]


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


def test_a_wired_call_site_must_close_the_obligation_instead_of_carrying_it() -> None:
    """B 的另一半閂:有人把閘接進 APPLY 之後,那條義務必須被關掉而不是永遠掛著。"""

    import aiml_gate_receipt_wave_w5 as wave_w5

    reasons = wave_w5._honest_surface_reasons(
        {
            "production_call_sites": [
                "helper_scripts/maintenance_scripts/agent_governance_s2_4_host_identity.py"
            ],
            "apply_time_consumer": "x",
            "apply_time_consumer_derives_freshness": True,
        },
        {
            "only_shape_is_constrained": True,
            "emit_sink_accepts_fabricated_evidence": True,
            "emit_sink_refuses_empty_evidence": True,
            "emit_sink_refuses_secret_like_evidence": True,
        },
    )
    assert any("close the obligation instead" in reason for reason in reasons), reasons


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


def test_expected_topology_is_caller_suppliable_and_bound_to_nothing() -> None:
    """E:PG row 的 ``expected_topology`` 可被 caller 弱化,且沒有任何簽章覆蓋它。"""

    import json

    import agent_governance_s2_4_install_driver as runner
    import agent_governance_s2_4_topology as topology

    assert "expected_topology" in runner.ROW_PAYLOAD_ALLOWLIST["PG_ROLE_ACL_MIGRATION"]
    # 簽過的 component intent 對 PG row 只要求四個 digest,沒有 expected_topology 的位置。
    schema = validator._load_schema("s2_4_component_effect_intent_v1")
    pg_branch = next(
        branch for branch in schema["allOf"]
        if branch["if"]["properties"]["component_effect_class"]["const"]
        == "PG_ROLE_ACL_MIGRATION"
    )
    required = pg_branch["then"]["properties"]["required_intent_fields"]["required"]
    assert "expected_topology_digest" not in required
    assert sorted(required) == [
        "acl_manifest_digest", "admin_handle_descriptor_digest",
        "pg_migration_permit_digest", "topology_attestation_digest",
    ]
    # 省略不能弱化(缺 hba_projection 即 UNPROVEN),但省略單一基線鍵可以跳過該次比對。
    source = (
        ROOT / "helper_scripts/maintenance_scripts/agent_governance_s2_4_topology.py"
    ).read_text(encoding="utf-8")
    assert "expected signed HBA projection is missing" in source
    assert source.count('expected.get(field) is not None') >= 2
    assert topology.derive_pg_topology_status(
        {"schema_version": "pg_topology_attestation_v1"}, expected={}, now=None
    )["status"] == topology.TOPOLOGY_STATUS_UNPROVEN
    # 計畫端**已經**帶著正解需要的兩個欄位,故這是 plumbing 決策而非缺資料。
    plan_core = validator._load_schema("s2_4_install_plan_core_v1")
    assert {"topology_pre_digest", "hba_delta_digest"} <= set(plan_core["properties"])
    assert "effective_rule" in json.dumps(
        validator._load_schema("s2_4_pg_hba_delta_v1")["properties"]
    )
    entry = _W5_ROWS["EXPECTED_TOPOLOGY_IS_CALLER_SUPPLIED_AND_UNSIGNED"]
    assert "hba_delta_digest" in entry["statement"]


def test_the_w5_leaves_do_not_widen_the_top_level_namespace_at_import_time() -> None:
    """§9.2 review P2-E:兩支 W5 葉在 import 期把 ``program_code`` 放進 sys.path。

    誠實邊界(見 obligation PROGRAM_CODE_IS_ON_THE_SCANNER_PATH_VIA_W4):W4 的葉仍然這麼做
    且早於 W5,故 scanner 進程層級的性質尚未達成;本測試釘住的是 W5 自己那兩處。
    """

    import subprocess

    for leaf in ("aiml_gate_receipt_s2_4_contracts", "aiml_gate_receipt_wave_w5"):
        probe = subprocess.run(
            [
                sys.executable, "-c",
                "import sys;sys.path.insert(0, %r);import %s;"
                "print(%r in sys.path)" % (str(ML_ROOT), leaf, str(PROGRAM_CODE)),
            ],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert probe.returncode == 0, probe.stderr
        assert probe.stdout.strip() == "False", (leaf, probe.stdout)


def test_w5_builds_a_receipt_without_writing_anything(tmp_path, chain) -> None:
    """W5 不擁有發射器:``build_w5_wave_exit_receipt`` 只回記憶體物件、零檔案副作用。"""

    admission, _w0, _w1, _w2, _w3, w4, _w5 = chain
    before = sorted(p.name for p in tmp_path.iterdir())
    receipt = validator.build_w5_wave_exit_receipt(admission, w4, **deepcopy(_EVID))
    assert receipt["wave"] == "W5"
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert not hasattr(install, "emit_w5_receipts")
    assert not (
        ROOT / "docs/execution_plan/ai_ml_landing/receipts/S2.4-WP4-W5"
    ).exists()
