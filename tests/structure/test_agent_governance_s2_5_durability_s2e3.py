"""S2E.3 durability 紅→綠測試——PR#153 Codex-4 + S2.5 的 F2/F3/F4/note-1 四項缺陷。

每一節都對應一個「修前可過、修後 typed 拒」的具體縫:

* **H(Codex-4)**:上游 S2.4 install receipt / S2.1 drill receipt 的 digest 綁定只證 bytes——
  修前任何 canonical 自洽的兩鍵 stub、或一份已過期的 receipt,都能綁進 operator-signed
  intent 並一路放行到 effect;修後兩者都必須過中央閘(closed schema + lineage/委派驗)
  且未過期。
* F2/F2b/F3/F4/note-1 的節在後續 commit 逐一補上。

⚠ honesty:本檔全部是 simulated/disposable lane 的注入式 harness;綠**不**證明任何真主機
狀態,九項 authority 恆 false。
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for _candidate in (HELPERS, ML_ROOT):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import agent_governance_s2_5_lifecycle as lifecycle  # noqa: E402
import s2_5_testkit as kit  # noqa: E402


class UntouchableDriver:
    """precheck 拒絕路徑的零接觸斷言用(任何 driver 面被碰即炸)。"""

    def __getattr__(self, name):  # noqa: D105
        raise AssertionError(f"driver surface {name!r} was touched before authorization")


# ── H(PR#153 Codex-4):上游 receipt 必須過中央閘 + 未過期 ──────────────────────────
def test_legacy_two_key_s2_4_stub_no_longer_unlocks_the_start(tmp_path, monkeypatch):
    """修前唯一被檢查的三件事(dict / status / self_digest 三值鏈)全部成立,仍必須被拒。

    stub 的 self_digest 是**真的**重算值,且 core 綁的就是它——P1-2 的 digest 閘完全滿足。
    擋下它的只能是 closed schema/lineage 那一層(刪掉即紅)。
    """

    stub = kit.legacy_s2_4_receipt_stub()
    private_key, _, _, _ = kit.a_side_setup(tmp_path, monkeypatch)
    intent = kit.start_intent(
        "S2_5A_START", s2_4_install_effect_receipt_digest=stub["self_digest"]
    )
    permit = kit.signed_permit(private_key, intent)
    unit = kit.SimulatedUnit()
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, UntouchableDriver(),
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=unit, s2_4_install_effect_receipt=stub,
        ),
    )
    assert verdict["status"] == "REQUEST_REJECTED", verdict
    assert any(
        "central closed-schema/lineage gate" in reason for reason in verdict["reasons"]
    ), verdict["reasons"]
    assert unit.calls == []


def test_expired_s2_4_receipt_no_longer_unlocks_the_start(tmp_path, monkeypatch):
    """§3.1a 的另一半:receipt 必須「在手**且未過期**」——中央閘對該 schema 沒有窗判。"""

    expired = kit.s2_4_receipt(
        expires_at=(kit.ANCHOR + timedelta(minutes=1)).isoformat()  # NOW 是 ANCHOR+2min。
    )
    private_key, _, _, _ = kit.a_side_setup(tmp_path, monkeypatch)
    intent = kit.start_intent(
        "S2_5A_START", s2_4_install_effect_receipt_digest=expired["self_digest"]
    )
    permit = kit.signed_permit(private_key, intent)
    unit = kit.SimulatedUnit()
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, UntouchableDriver(),
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=unit, s2_4_install_effect_receipt=expired,
        ),
    )
    assert verdict["status"] == "REQUEST_REJECTED", verdict
    assert any("expired at" in reason for reason in verdict["reasons"]), verdict["reasons"]
    assert unit.calls == []
    # 對照組:同一份 fixture 未過期時放行到窗內(拒絕來自 expiry 臂,而非 fixture 壞掉)。
    fresh_intent = kit.start_intent("S2_5A_START")
    fresh_unit = kit.SimulatedUnit()
    fresh = lifecycle.apply_s2_5_start(
        fresh_intent, kit.signed_permit(private_key, fresh_intent), fresh_unit,
        **kit.apply_kwargs(tmp_path=tmp_path, unit=fresh_unit),
    )
    assert fresh["status"] == "SOURCE_SIMULATION_PASS", fresh["reasons"]


def test_legacy_two_key_drill_stub_no_longer_unlocks_the_final(tmp_path, monkeypatch):
    """同形第二洞:S2.5B 的 drill 錨修前只被檢查 ``status.startswith("QUIESCED")`` + digest。"""

    stub = kit.legacy_drill_receipt_stub()
    private_key, _, _, _, pre_drill = kit.b_side_setup(tmp_path, monkeypatch)
    intent = kit.start_intent(
        "S2_5B_FINAL",
        s2_1_drill_receipt_digest=stub["self_digest"],
        pre_drill_attestation_digest=pre_drill["self_digest"],
    )
    permit = kit.signed_permit(private_key, intent)
    unit = kit.SimulatedUnit()
    unit.enable_now()
    verdict = lifecycle.apply_s2_5_final(
        intent, permit, UntouchableDriver(),
        **kit.final_apply_kwargs(tmp_path=tmp_path, unit=unit),
        s2_1_drill_receipt=stub,
        pre_drill_attestation=pre_drill,
    )
    assert verdict["status"] == "REQUEST_REJECTED", verdict
    assert any(
        "central closed-schema/lineage gate" in reason for reason in verdict["reasons"]
    ), verdict["reasons"]


def test_bound_upstream_receipt_of_the_wrong_schema_is_rejected(tmp_path, monkeypatch):
    """schema_version 換名的「另一種 artifact」即便 digest 綁定成立也拒(名字先於內容)。"""

    impostor = dict(kit.drill_receipt())
    impostor["schema_version"] = "quiesce_observation_v1"
    import aiml_gate_receipt_validator as validator

    impostor["self_digest"] = validator.artifact_self_digest(
        {k: v for k, v in impostor.items() if k != "self_digest"}
    )
    reasons = lifecycle._upstream_receipt_gate_reasons(
        impostor,
        now_dt=lifecycle._resolve_now(kit.NOW),
        schema_version="s2_4_install_effect_receipt_v1",
        label="probe",
        expiry_field="expires_at",
    )
    assert reasons and "does not declare schema_version" in reasons[0]
