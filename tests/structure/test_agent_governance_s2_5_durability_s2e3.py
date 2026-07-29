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


# ── F3:兩個 lock 是兩個資源(型別互斥 + 路徑相異守衛)───────────────────────────────
def test_install_lock_default_path_is_the_s2_4_lock_not_the_s2_5_lifecycle_lock():
    """F3 的根:``install_lock_free`` 修前探的是 S2.5 自己的 lifecycle 鎖(歸因錯誤)。"""

    assert (
        lifecycle.S2_4InstallLockFreeProbe().lock_path
        == Path(lifecycle.S2_4_INSTALL_LOCK_PATH)
    )
    assert lifecycle.S2_5LifecycleLockHold().lock_path == Path(lifecycle.S2_5_LOCK_PATH)
    assert lifecycle.S2_4_INSTALL_LOCK_PATH != lifecycle.S2_5_LOCK_PATH


def test_a_hold_style_object_is_never_accepted_as_the_install_lock_probe():
    """型別互斥:帶 acquire 面的物件是 lifecycle 鎖,不是 S2.4 install 探針。"""

    free, reasons = lifecycle.derive_s2_4_install_lock_free(
        kit.SimulatedLifecycleLock()
    )
    assert free is False
    assert any("hold-style acquire" in reason for reason in reasons), reasons


def test_one_object_or_one_path_can_never_stand_for_both_locks(tmp_path, monkeypatch):
    """資源分離守衛:同物件 / 同解析路徑 ⇒ typed 拒(在取 hold 之前,零消費零 effect)。"""

    shared_path = tmp_path / "shared.lock"

    class _BothFaces:
        """修前形狀:一個 class 同時是 probe-only 面與 hold 面。"""

        lock_path = str(shared_path)

        def flock_probe(self):
            return {"held": False, "exists": True, "lock_path": str(shared_path)}

        def acquire(self):
            return {
                "status": lifecycle.S2_5_LOCK_ACQUIRED,
                "lock_path": str(shared_path),
                "reasons": [],
            }

        def release(self):
            return {
                "status": lifecycle.S2_5_LOCK_RELEASED,
                "lock_path": str(shared_path),
                "reasons": [],
            }

    both = _BothFaces()
    # 同一物件充當兩面:先被 derive 的型別互斥守衛擋(install_lock_free 不可證)。
    assert lifecycle._lock_resource_separation_reasons(both, both)[0].startswith(
        "the S2.4 install-lock probe and the S2.5 lifecycle hold are the same object"
    )
    # 兩個不同物件、但指向同一個 lock 檔:同樣拒。
    separation = lifecycle._lock_resource_separation_reasons(
        kit.SimulatedInstallLockProbe(lock_path=str(shared_path)),
        kit.SimulatedLifecycleLock(lock_path=str(shared_path)),
    )
    assert separation and "resolve to the same file" in separation[0]
    # 端到端:同路徑注入 ⇒ REQUEST_REJECTED、零 driver 接觸、零 state_root 落盤。
    _key, intent, permit, _u = kit.a_side_setup(tmp_path, monkeypatch)
    unit = kit.SimulatedUnit()
    ledger = {"entries": []}
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=unit, replay_ledger=ledger,
            install_lock_probe=kit.SimulatedInstallLockProbe(lock_path=str(shared_path)),
            lifecycle_lock=kit.SimulatedLifecycleLock(lock_path=str(shared_path)),
        ),
    )
    assert verdict["status"] == "REQUEST_REJECTED", verdict
    assert any("same file" in reason for reason in verdict["reasons"])
    assert unit.calls == []
    assert ledger["entries"] == []
    assert not (tmp_path / "state").exists()


def test_lock_faces_without_a_declared_path_cannot_prove_separation():
    """位置不可導出 = 分離不可證 ⇒ fail-closed(不預設「不同物件就一定不同資源」)。"""

    class _Anonymous:
        def acquire(self):  # pragma: no cover —— 永不該被呼叫。
            raise AssertionError("the hold must never be acquired without separation")

    reasons = lifecycle._lock_resource_separation_reasons(
        kit.SimulatedInstallLockProbe(), _Anonymous()
    )
    assert reasons and "resolvable lock_path" in reasons[0]
