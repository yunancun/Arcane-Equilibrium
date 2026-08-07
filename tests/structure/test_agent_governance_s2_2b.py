"""S2.2B(WP5 tranche 2)ingestion-compatibility seam 測試(S2.5 design §10)。

fixtures:S2.2A 側**直接消費 repo 內 persisted 真檔**
(`receipts/S2.2A-source-compatibility-receipt-v1.json`);S2.5 側以 tranche 1 的
`real_pre_drill_receipt` 形制產**真** `s2_5_final_attestation_v1` 配對物(simulated
lane,走完整 apply_s2_5_final 鏈)。正例綠 + 逐維失敗注入紅:

- S2.2A digest 漂移(內容改動/自報 digest)⇒ 三值鏈重算拒;
- final attestation 缺席或 simulated-lane 錨 production ⇒ 拒;
- V151-V160 任一項 revalidation fail ⇒ 整份拒(claimed MATCH 不採信);
- fixture 假冒 platform-attested ⇒ 拒;
- refresh-by-reference ⇒ §9.2 typed 禁;
- 過期/缺 now ⇒ fail-closed。

honesty:一切綠只證 source 結構/綁定;不證任何 runtime 上的 revalidation 發生過。
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for _candidate in (HELPERS, ML_ROOT):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import agent_governance_s2_2b as builder  # noqa: E402
import agent_governance_s2_5_lifecycle as lifecycle  # noqa: E402
import aiml_gate_receipt_s2_2b as leaf  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
import s2_5_testkit as kit  # noqa: E402

S2_2A_RECEIPT_PATH = ROOT / builder.S2_2A_RECEIPT_V1_REL
LATE_NOW = (kit.ANCHOR + timedelta(days=2)).isoformat()


def _real_s2_2a_receipt() -> dict:
    return json.loads(S2_2A_RECEIPT_PATH.read_text(encoding="utf-8"))


def _real_final_attestation(tmp_path, monkeypatch) -> dict:
    """tranche 1 `real_pre_drill_receipt` 形制:走完整 S2.5B 鏈的真 receipt(simulated)。"""

    _key, intent, permit, unit, pre_drill = kit.b_side_setup(tmp_path, monkeypatch)
    verdict = lifecycle.apply_s2_5_final(
        intent, permit, unit,
        **kit.final_apply_kwargs(tmp_path=tmp_path, unit=unit),
        s2_1_drill_receipt=kit.drill_receipt(),
        pre_drill_attestation=pre_drill,
    )
    assert verdict["status"] == "SOURCE_SIMULATION_PASS", verdict["reasons"]
    return verdict["receipt"]


def _built_receipt(tmp_path, monkeypatch, **overrides) -> dict:
    source_receipt = _real_s2_2a_receipt()
    kwargs = {
        "source_compatibility_receipt": source_receipt,
        "s2_5_final_attestation": _real_final_attestation(tmp_path, monkeypatch),
        "observed_fingerprints": dict(source_receipt["migration_fingerprints"]),
        "application_root_learning_runtime_digest": source_receipt[
            "learning_runtime_digest"
        ],
        "verifier_node_id": "s2-2b-independent-verifier",
        "observed_at": kit.NOW,
        "evidence_expires_at": kit.EXPIRES,
        "source_head": kit.SOURCE_HEAD,
    }
    kwargs.update(overrides)
    return builder.build_ingestion_compatibility_receipt(**kwargs)


def _reseal(receipt: dict) -> dict:
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    return receipt


# ── 正例:真 S2.2A 檔 + 真 simulated final attestation ⇒ 全綠 ───────────────────────
def test_source_lane_positive_round_trips_the_central_gate(tmp_path, monkeypatch):
    receipt = _built_receipt(tmp_path, monkeypatch)
    assert receipt["status"] == "SOURCE_REVALIDATION_PASS"
    assert receipt["evidence_class"] == "LOCAL_REPRODUCIBLE"
    assert receipt["effect_class"] == "REMOTE_READONLY"
    assert receipt["runtime_attestor"] is None
    assert validator.validate_aiml_artifact(receipt, now=kit.NOW) == []
    # V151-V160 十項全 MATCH 且 expected 錨在真 S2.2A fingerprints 上。
    items = receipt["manifest_revalidation"]["items"]
    assert len(items) == 10
    assert all(item["result"] == "MATCH" for item in items)
    assert receipt["manifest_revalidation"]["learning_runtime_digest_match"] is True


def test_registration_is_additive_and_frozen_surfaces_unmoved():
    # SCHEMA_FILES 93 + schema 檔在盤:既有 79 加上
    # s2e_launch_genesis_receipt_v1、s2e_launch_wave_receipt_v1、
    # receipt_carrier_attestation_v1、s2e_launch_acceptance_review_bundle_v1，以及
    # signed host capture、四份 identity-bound S2.5 recovery contract，以及
    # closed disposable-test effect chain、predecessor consume-once ledger，
    # purpose-specific signed consumption bootstrap authority，以及 predecessor
    # registry attestation；Tier 1(2026-08-06)退掉 external WORM provider
    # attestation、加入 durability anchor attestation 與其 committed floor ⇒ 94。
    # PROGRAM_SCHEMA_PATHS 與 frozen 分類身分未動(digest 凍結值由既有 s2_5 測試釘住)。
    assert "ingestion_compatibility_receipt_v1" in validator.SCHEMA_FILES
    assert len(validator.SCHEMA_FILES) == 94
    for s2e_key in (
        "s2e_launch_genesis_receipt_v1",
        "s2e_launch_consumption_bootstrap_authority_v1",
        "s2e_launch_predecessor_consumption_ledger_v1",
        "s2e_launch_wave_receipt_v1",
        "receipt_carrier_attestation_v1",
        "s2e_launch_acceptance_review_bundle_v1",
        "s2_5_recovery_host_capture_v1",
        "s2_5_recovery_intent_v1",
        "s2_5_recovery_postcheck_v1",
        "s2_5_recovery_result_v1",
        "s2_5_recovery_rollback_v1",
    ):
        assert (
            validator.SCHEMA_DIR / validator.SCHEMA_FILES[s2e_key]
        ).is_file()
    assert (
        validator.SCHEMA_DIR
        / validator.SCHEMA_FILES["ingestion_compatibility_receipt_v1"]
    ).is_file()
    assert not any(
        "ingestion_compatibility" in path for path in validator.PROGRAM_SCHEMA_PATHS
    )
    projection = leaf.s2_2b_abi_projection()
    assert projection["effect_class"] == "REMOTE_READONLY"
    assert projection["runtime_done_consumes"] == "S2.5B@EFFECT_DONE"
    assert projection["schema_file_present"] is True


def test_closed_schema_rejects_extra_keys_and_missing_now(tmp_path, monkeypatch):
    receipt = _built_receipt(tmp_path, monkeypatch)
    smuggled = _reseal(dict(receipt, smuggled_key="x"))
    assert validator.validate_aiml_artifact(smuggled, now=kit.NOW)
    # now 缺席=中央閘 fail-closed。
    assert any(
        "requires now" in error
        for error in validator.validate_aiml_artifact(receipt)
    )
    # 過期 fail-closed。
    assert any(
        "expired" in error
        for error in validator.validate_aiml_artifact(receipt, now=LATE_NOW)
    )


# ── S2.2A 綁定:digest 漂移/替身 stub 拒 ─────────────────────────────────────────
def test_s2_2a_digest_drift_is_rejected(tmp_path, monkeypatch):
    receipt = _built_receipt(tmp_path, monkeypatch)
    # (a) 內容漂移、外層重封:內嵌 self_digest 重算即斷。
    drifted = deepcopy(receipt)
    drifted["source_compatibility_receipt"]["learning_runtime_digest"] = (
        "sha256:" + "9" * 64
    )
    _reseal(drifted)
    errors = validator.validate_aiml_artifact(drifted, now=kit.NOW)
    assert any("does not re-derive" in error for error in errors), errors
    # (b) 內嵌 receipt 誠實重封但外層綁定 digest 未跟上:三值鏈第三值斷。
    swapped = deepcopy(receipt)
    swapped["source_compatibility_receipt"]["session_id"] = "S2.2A-FORGED"
    swapped["source_compatibility_receipt"]["self_digest"] = (
        validator.artifact_self_digest(swapped["source_compatibility_receipt"])
    )
    _reseal(swapped)
    errors2 = validator.validate_aiml_artifact(swapped, now=kit.NOW)
    assert any("does not re-derive" in error for error in errors2), errors2
    # (c) 內嵌+外層一起重封:內層反偽造重算(中央閘 S2.2A 分支)接手拒。
    forged = deepcopy(receipt)
    forged["source_compatibility_receipt"]["learning_runtime_digest"] = (
        "sha256:" + "9" * 64
    )
    forged["source_compatibility_receipt"]["self_digest"] = (
        validator.artifact_self_digest(forged["source_compatibility_receipt"])
    )
    forged["source_compatibility_receipt_digest"] = forged[
        "source_compatibility_receipt"
    ]["self_digest"]
    _reseal(forged)
    errors3 = validator.validate_aiml_artifact(forged, now=kit.NOW)
    assert any("central gate" in error for error in errors3), errors3
    # builder 端 fail-fast:替身 stub 不進 builder。
    stub = dict(_real_s2_2a_receipt(), forged=True)
    with pytest.raises(ValueError, match="never enters the builder"):
        builder.build_ingestion_compatibility_receipt(
            source_compatibility_receipt=stub,
            s2_5_final_attestation=None,
            observed_fingerprints={},
            application_root_learning_runtime_digest=None,
            verifier_node_id="v",
            observed_at=kit.NOW,
            evidence_expires_at=kit.EXPIRES,
            source_head=kit.SOURCE_HEAD,
        )


# ── final attestation 錨:缺席/竄改/simulated 錨 production 拒 ────────────────────────
def test_final_attestation_absent_or_tampered_is_rejected(tmp_path, monkeypatch):
    receipt = _built_receipt(tmp_path, monkeypatch)
    # 成功 status + 錨缺席:closed schema 條件先拒(anchor 必為 object)。
    absent = deepcopy(receipt)
    absent["s2_5_final_attestation"] = None
    absent["s2_5_final_attestation_digest"] = None
    _reseal(absent)
    errors = validator.validate_aiml_artifact(absent, now=kit.NOW)
    assert any("s2_5_final_attestation" in error for error in errors), errors
    # PENDING + 錨缺席:schema 允許 null,但 leaf 臂拒(缺錨只可 COMPATIBILITY_REJECTED)。
    pending_absent = deepcopy(absent)
    pending_absent["status"] = "EXTERNAL_VERIFICATION_PENDING"
    pending_absent["evidence_class"] = "STRUCTURAL_ONLY"
    pending_absent["failure_reason"] = "anchor absent"
    _reseal(pending_absent)
    errors0 = validator.validate_aiml_artifact(pending_absent, now=kit.NOW)
    assert any("anchor in hand" in error for error in errors0), errors0
    tampered = deepcopy(receipt)
    tampered["s2_5_final_attestation"]["owner_fingerprint"] = "sha256:" + "8" * 64
    _reseal(tampered)
    errors2 = validator.validate_aiml_artifact(tampered, now=kit.NOW)
    assert any("does not re-derive" in error for error in errors2), errors2
    # 錨誠實重封但過不了中央閘(status 換成 attested 卻無 attestor)⇒ 全套重驗拒
    # (tranche 1b P1-2 紀律:digest 綁定只證 bytes,不證這份 attestation 站得住)。
    unattested = deepcopy(receipt)
    final = unattested["s2_5_final_attestation"]
    final["status"] = "FINAL_ATTESTED"
    final["self_digest"] = validator.artifact_self_digest(final)
    unattested["s2_5_final_attestation_digest"] = final["self_digest"]
    _reseal(unattested)
    errors3 = validator.validate_aiml_artifact(unattested, now=kit.NOW)
    assert any("central gate" in error for error in errors3), errors3


def test_simulated_lane_anchor_never_unlocks_the_runtime_done_lane(
    tmp_path, monkeypatch
):
    # 把 simulated 錨硬塞進 runtime-DONE lane 的形狀:schema/leaf 兩層都必須拒。
    receipt = _built_receipt(tmp_path, monkeypatch)
    forged = deepcopy(receipt)
    forged["status"] = "RUNTIME_COMPATIBILITY_ATTESTED"
    forged["target_class"] = "production"
    forged["evidence_class"] = "PLATFORM_OR_EXTERNAL_ATTESTED"
    revalidation_digest = validator.canonical_digest(forged["manifest_revalidation"])
    forged["runtime_attestor"] = {
        "attestor_identity": "aiml-s2-2b-ingestion-attestor-v1",
        "signature_namespace": (
            "arcane-equilibrium-aiml-s2-2b-ingestion-compatibility"
        ),
        "attestation_kind": "INGESTION",
        "manifest_revalidation_digest": revalidation_digest,
        "s2_5_final_attestation_digest": forged["s2_5_final_attestation_digest"],
        "attested_at": kit.NOW,
        "expires_at": kit.EXPIRES,
        "signature_armored": "forged",
    }
    _reseal(forged)
    errors = validator.validate_aiml_artifact(forged, now=kit.NOW)
    assert any(
        "simulated-lane anchor never unlocks" in error for error in errors
    ), errors


def test_fixture_impersonating_platform_evidence_is_rejected(tmp_path, monkeypatch):
    receipt = _built_receipt(tmp_path, monkeypatch)
    impersonated = _reseal(
        dict(deepcopy(receipt), evidence_class="PLATFORM_OR_EXTERNAL_ATTESTED")
    )
    errors = validator.validate_aiml_artifact(impersonated, now=kit.NOW)
    assert errors, "a fixture claiming platform evidence must be rejected"


# ── manifest revalidation:任一項 fail ⇒ 整份拒;claimed MATCH 不採信 ────────────────
def test_one_failing_manifest_item_fails_the_whole_receipt(tmp_path, monkeypatch):
    source_receipt = _real_s2_2a_receipt()
    observed = dict(source_receipt["migration_fingerprints"])
    drift_file = sorted(observed)[0]
    observed[drift_file] = "f" * 64  # V151 指紋漂移。
    receipt = _built_receipt(
        tmp_path, monkeypatch, observed_fingerprints=observed
    )
    # builder 誠實導出 REJECTED + 具名失敗維。
    assert receipt["status"] == "COMPATIBILITY_REJECTED"
    assert drift_file in (receipt["failure_reason"] or "")
    assert validator.validate_aiml_artifact(receipt, now=kit.NOW) == []
    # 對手把同一份改宣稱成功(claimed MATCH/翻 result)⇒ 中央閘導出式重驗拒。
    forged = deepcopy(receipt)
    forged["status"] = "SOURCE_REVALIDATION_PASS"
    forged["evidence_class"] = "LOCAL_REPRODUCIBLE"
    forged["failure_reason"] = None
    _reseal(forged)
    errors = validator.validate_aiml_artifact(forged, now=kit.NOW)
    assert any("one failing item fails the whole receipt" in e for e in errors), errors
    # 連 result 欄一起偽成 MATCH ⇒ observed↔expected 導出重驗拒。
    forged2 = deepcopy(forged)
    for item in forged2["manifest_revalidation"]["items"]:
        item["result"] = "MATCH"
    _reseal(forged2)
    errors2 = validator.validate_aiml_artifact(forged2, now=kit.NOW)
    assert any("never trusted" in e for e in errors2), errors2
    # 直接把 observed 改回 expected(整段偽造)⇒ expected 錨 S2.2A,仍需與真檔一致,
    # 此路徑等於全 MATCH——所以 expected_fingerprint 才是錨:改 expected 即拒。
    forged3 = deepcopy(receipt)
    forged3["manifest_revalidation"]["items"][0]["expected_fingerprint"] = "f" * 64
    forged3["manifest_revalidation"]["items"][0]["result"] = "MATCH"
    _reseal(forged3)
    errors3 = validator.validate_aiml_artifact(forged3, now=kit.NOW)
    assert any("anchored, never caller-supplied" in e for e in errors3), errors3


def test_dropped_or_smuggled_manifest_rows_are_rejected(tmp_path, monkeypatch):
    receipt = _built_receipt(tmp_path, monkeypatch)
    dropped = deepcopy(receipt)
    dropped["manifest_revalidation"]["items"].pop()
    _reseal(dropped)
    errors = validator.validate_aiml_artifact(dropped, now=kit.NOW)
    assert any("cover exactly" in e for e in errors), errors
    # learning_runtime_digest_match 不可自證。
    unmatched = deepcopy(receipt)
    unmatched["manifest_revalidation"][
        "application_root_learning_runtime_digest"
    ] = "sha256:" + "9" * 64
    _reseal(unmatched)
    errors2 = validator.validate_aiml_artifact(unmatched, now=kit.NOW)
    assert any("learning_runtime_digest" in e for e in errors2), errors2


# ── §9.2 never-refreshable 歸類 ─────────────────────────────────────────────────
def test_refresh_by_reference_is_forbidden_and_expiry_means_reobservation(
    tmp_path, monkeypatch
):
    receipt = _built_receipt(tmp_path, monkeypatch)
    refreshed = leaf.derive_s2_2b_source_dependency_admission_status(
        evidence_class="S2_2B_INGESTION_COMPATIBILITY",
        receipt=receipt,
        refresh={"refreshed_by": "reference"},
        now=kit.NOW,
    )
    assert refreshed["status"] == "DEPENDENCY_REFRESH_BY_REFERENCE_FORBIDDEN"
    fresh = leaf.derive_s2_2b_source_dependency_admission_status(
        evidence_class="S2_2B_INGESTION_COMPATIBILITY", receipt=receipt, now=kit.NOW,
    )
    assert fresh["status"] == "SOURCE_DEPENDENCY_FRESH"
    expired = leaf.derive_s2_2b_source_dependency_admission_status(
        evidence_class="S2_2B_INGESTION_COMPATIBILITY", receipt=receipt,
        now=LATE_NOW,
    )
    assert expired["status"] == "DEPENDENCY_EVIDENCE_REOBSERVATION_REQUIRED"
    unknown = leaf.derive_s2_2b_source_dependency_admission_status(
        evidence_class="NOT_A_CLASS", receipt=receipt, now=kit.NOW,
    )
    assert unknown["status"] == "SOURCE_DEPENDENCY_REJECTED"


# ── CLI:build/validate 綠、apply=typed PENDING(S2.5B@EFFECT_DONE 前不可達)────────
def test_cli_build_validate_and_apply_endpoints(tmp_path, monkeypatch, capsys):
    final = _real_final_attestation(tmp_path, monkeypatch)
    source_receipt = _real_s2_2a_receipt()
    observation = {
        "observed_fingerprints": dict(source_receipt["migration_fingerprints"]),
        "application_root_learning_runtime_digest": source_receipt[
            "learning_runtime_digest"
        ],
        "verifier_node_id": "s2-2b-independent-verifier",
        "observed_at": kit.NOW,
        "evidence_expires_at": kit.EXPIRES,
        "source_head": kit.SOURCE_HEAD,
    }
    final_path = tmp_path / "final.json"
    final_path.write_text(json.dumps(final), encoding="utf-8")
    observation_path = tmp_path / "observation.json"
    observation_path.write_text(json.dumps(observation), encoding="utf-8")
    code = builder._main([
        "build", "--final-attestation", str(final_path),
        "--observation", str(observation_path),
    ])
    built = json.loads(capsys.readouterr().out)
    assert code == 0 and built["status"] == "SOURCE_REVALIDATION_PASS"
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(built), encoding="utf-8")
    code2 = builder._main([
        "validate", "--artifact", str(receipt_path), "--now", kit.NOW,
    ])
    assert code2 == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PASS"
    # apply 面=typed PENDING(exit 0、零變更;runtime DONE 消費尚不存在的
    # S2.5B@EFFECT_DONE)。壞件先 typed REJECTED(exit 2)。
    code3 = builder._main(["apply", "--artifact", str(receipt_path), "--now", kit.NOW])
    applied = json.loads(capsys.readouterr().out)
    assert code3 == 0
    assert applied["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert any("S2.5B@EFFECT_DONE" in reason for reason in applied["reasons"])
    broken_path = tmp_path / "broken.json"
    broken_path.write_text(json.dumps(dict(built, self_digest="sha256:" + "0" * 64)),
                           encoding="utf-8")
    code4 = builder._main(["apply", "--artifact", str(broken_path), "--now", kit.NOW])
    assert code4 == 2
    assert json.loads(capsys.readouterr().out)["status"] == "REJECTED"


def test_production_without_attestor_is_typed_pending(tmp_path, monkeypatch):
    # production lane 全 MATCH 但無 runtime attestor ⇒ 誠實 PENDING(STRUCTURAL_ONLY)。
    receipt = _built_receipt(tmp_path, monkeypatch, target_class="production")
    assert receipt["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert receipt["evidence_class"] == "STRUCTURAL_ONLY"
    assert "S2.5B@EFFECT_DONE" in (receipt["failure_reason"] or "")
    assert validator.validate_aiml_artifact(receipt, now=kit.NOW) == []
