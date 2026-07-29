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

import json
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


# ── F2/F2b:reconcile 與 install-lock 重探都在 hold 窗內 ───────────────────────────
class _DeferredHold(lifecycle.S2_5LifecycleLockHold):
    """在**取鎖之前**插入一個 callback 的 hold(單執行緒地重現兩 applier 的交錯)。

    真實競態:A1 與 A2 幾乎同時在窗外 reconcile 得乾淨;A1 先取鎖→寫 APPLYING→釋放→
    進入(鎖已釋放的)長效果窗;A2 此刻才到取鎖點,鎖已自由 ⇒ 取鎖成功,而它手上的
    reconcile 是舊觀測、永不重跑。callback 就是「A1 在 A2 取鎖前跑完鎖窗」。
    """

    def __init__(self, lock_path, callback) -> None:
        super().__init__(lock_path)
        self._callback = callback
        self.fired = False

    def acquire(self):
        if not self.fired:
            self.fired = True
            self._callback()
        return super().acquire()


def _crash_in_the_effect_window(unit: "kit.SimulatedUnit") -> None:
    """讓 A1 在 `enable_now()`(鎖已釋放的效果窗)崩掉,journal 因此停在 APPLYING。

    用 KeyboardInterrupt(BaseException)是刻意的:applier 的 `except Exception` 臂不會
    捕捉它,故不會走 rollback / journal terminal——這正是「主機狀態不明」的殘留形狀。
    """

    def _boom() -> None:
        unit.calls.append("enable_now")
        raise KeyboardInterrupt("harness: the applier process died mid-effect")

    unit.enable_now = _boom


def test_second_applier_reconciles_the_residue_left_after_the_first_hold_closed(
    tmp_path, monkeypatch
):
    """F2 的核心紅測試:A1 的 APPLYING 殘留必須擋住 A2,即使 A2 早在窗外看過「乾淨」。"""

    state_root = kit.fresh_state_root(tmp_path, "shared-state")
    lock_path = tmp_path / "shared-lifecycle.lock"
    ledger = {"entries": []}
    private_key, intent1, permit1, unit1 = kit.a_side_setup(tmp_path, monkeypatch)
    _crash_in_the_effect_window(unit1)

    def _run_first_applier() -> None:
        try:
            lifecycle.apply_s2_5_start(
                intent1, permit1, unit1,
                **kit.apply_kwargs(
                    tmp_path=tmp_path, unit=unit1, state_root=state_root,
                    replay_ledger=ledger,
                    lifecycle_lock=lifecycle.S2_5LifecycleLockHold(lock_path),
                ),
            )
        except KeyboardInterrupt:
            pass  # A1 的行程死在效果窗中(kernel 會釋放它的 flock)。

    intent2 = kit.start_intent("S2_5A_START", target_host="trade-core-second-applier")
    permit2 = kit.signed_permit(private_key, intent2)
    unit2 = kit.SimulatedUnit()
    verdict = lifecycle.apply_s2_5_start(
        intent2, permit2, unit2,
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=unit2, state_root=state_root, replay_ledger=ledger,
            lifecycle_lock=_DeferredHold(lock_path, _run_first_applier),
        ),
    )
    assert verdict["status"] == "RECOVERY_REQUIRED", verdict
    assert any("non-terminal state 'APPLYING'" in r for r in verdict["reasons"]), verdict
    assert unit2.calls == []            # A2 從未碰過 driver。
    assert len(ledger["entries"]) == 1  # 只有 A1 消費過;A2 零消費。
    assert lifecycle._flock_free_observation(lock_path)["held"] is False  # 鎖已釋放。


def test_residue_still_blocks_when_the_hold_is_obtained_cleanly(tmp_path, monkeypatch):
    """對照組:殘留在**乾淨取鎖**的路徑上同樣擋(reconcile 不是被 hold 順序偷換掉的)。"""

    state_root = kit.fresh_state_root(tmp_path, "residue-state")
    state_root.mkdir(parents=True)
    (state_root / f"s2-5-{'1' * 64}.journal.json").write_text(
        '{"schema_version": "s2_5_start_journal_v1_informal", "start_id": "s2-5-'
        + "1" * 64
        + '", "state": "APPLYING", "updated_at": "'
        + kit.NOW
        + '", "history": []}',
        encoding="utf-8",
    )
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(tmp_path=tmp_path, unit=unit, state_root=state_root),
    )
    assert verdict["status"] == "RECOVERY_REQUIRED", verdict
    assert unit.calls == []


def test_a_held_lifecycle_lock_rejects_before_any_state_root_write(tmp_path, monkeypatch):
    """鎖被別人持有 ⇒ typed REQUEST_REJECTED、零 state_root 落盤,且說明殘留未被觀測。"""

    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    state_root = kit.fresh_state_root(tmp_path, "held-state")
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=unit, state_root=state_root,
            lifecycle_lock=kit.SimulatedLifecycleLock(held=True),
        ),
    )
    assert verdict["status"] == "REQUEST_REJECTED", verdict
    assert any("re-run once the lock is released" in r for r in verdict["reasons"])
    assert unit.calls == []
    assert not state_root.exists()


class _InstallLockTakenInsideTheWindow:
    """窗外探測自由、窗內(第二次探測起)被持有——F2b 的 TOCTOU 形狀。"""

    def __init__(self, lock_path: str = "/tmp/s2-5-testkit/f2b-install.lock") -> None:
        self.lock_path = lock_path
        self.probes = 0

    def flock_probe(self):
        self.probes += 1
        return {
            "held": self.probes > 1,
            "exists": True,
            "lock_path": self.lock_path,
        }


def test_install_lock_taken_after_the_fail_fast_probe_is_caught_inside_the_window(
    tmp_path, monkeypatch
):
    """F2b:step 3 的探測即釋放同樣有 TOCTOU;窗內重探把「窗外自由、窗內被搶走」抓下來。"""

    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    probe = _InstallLockTakenInsideTheWindow()
    ledger = {"entries": []}
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=unit, replay_ledger=ledger, install_lock_probe=probe,
        ),
    )
    assert verdict["status"] == "REQUEST_REJECTED", verdict
    assert any("S2.4 install lock is held" in r for r in verdict["reasons"]), verdict
    assert probe.probes == 2      # 窗外 fail-fast 一次 + 窗內權威一次。
    assert unit.calls == []
    assert ledger["entries"] == []  # 窗內拒絕在 consume 之前。


# ── F4:release 是 typed outcome,鎖窗證據進 verdict/receipt ──────────────────────────
def _journal_state(state_root: Path, intent: dict) -> str:
    return json.loads(
        lifecycle.s2_5_journal_path(state_root, intent["start_id"]).read_text(
            encoding="utf-8"
        )
    )["state"]


def test_release_failure_blocks_the_effect_window_instead_of_being_swallowed(
    tmp_path, monkeypatch
):
    """修前:release 例外被 `except Exception: pass` 吞掉、回傳值不被接,enable --now 照跑。"""

    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    state_root = kit.fresh_state_root(tmp_path, "release-fail-state")
    recovery = lifecycle.S2_5RecoveryState()
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=unit, state_root=state_root, recovery_state=recovery,
            lifecycle_lock=kit.SimulatedLifecycleLock(fail_release=True),
        ),
    )
    assert verdict["status"] == "RECOVERY_REQUIRED", verdict
    assert verdict["lock_window"] == {
        "hold_acquired": True,
        "hold_released": False,
        "release_status": lifecycle.S2_5_LOCK_RELEASE_FAILED,
    }
    assert "enable_now" not in unit.calls   # 效果窗永不開始。
    assert "receipt" not in verdict          # 無 receipt(絕不轉成功)。
    assert _journal_state(state_root, intent) == "RECOVERY_REQUIRED"
    assert recovery.unresolved is not None


def test_a_lock_without_a_release_face_is_typed_untyped_not_ignored(tmp_path, monkeypatch):
    """無 release 面:修前 `callable(release)` 為假就靜默跳過;現在是 typed RELEASE_UNTYPED。"""

    class _NoReleaseFace:
        lock_path = "/tmp/s2-5-testkit/no-release-face.lock"

        def acquire(self):
            return {
                "status": lifecycle.S2_5_LOCK_ACQUIRED,
                "lock_path": self.lock_path,
                "reasons": [],
            }

    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(tmp_path=tmp_path, unit=unit, lifecycle_lock=_NoReleaseFace()),
    )
    assert verdict["status"] == "RECOVERY_REQUIRED", verdict
    assert verdict["lock_window"]["release_status"] == lifecycle.S2_5_LOCK_RELEASE_UNTYPED
    assert "enable_now" not in unit.calls


def test_window_rejection_paths_also_carry_the_lock_window(tmp_path, monkeypatch):
    """窗內拒絕(前態不符)也帶鎖窗證據——F4 覆蓋的是**每一個**窗出口。"""

    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    unit.enable_now()  # 前態已 active ⇒ 窗內 REQUEST_REJECTED。
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit, **kit.apply_kwargs(tmp_path=tmp_path, unit=unit)
    )
    assert verdict["status"] == "REQUEST_REJECTED"
    assert verdict["lock_window"] == {
        "hold_acquired": True,
        "hold_released": True,
        "release_status": lifecycle.S2_5_LOCK_RELEASED,
    }
    # hold 根本沒取到的路徑同樣帶(hold_acquired=False)。
    _k2, intent2, permit2, unit2 = kit.a_side_setup(tmp_path, monkeypatch)
    held = lifecycle.apply_s2_5_start(
        intent2, permit2, unit2,
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=unit2,
            lifecycle_lock=kit.SimulatedLifecycleLock(held=True),
        ),
    )
    assert held["lock_window"]["hold_acquired"] is False


def test_final_release_failure_blocks_the_reset(tmp_path, monkeypatch):
    """S2.5B 同形:鎖窗未證關閉 ⇒ 觀測/watchdog reset 都不發生。"""

    _key, intent, permit, unit, pre_drill = kit.b_side_setup(tmp_path, monkeypatch)
    state_root = kit.fresh_state_root(tmp_path, "final-release-fail")
    verdict = lifecycle.apply_s2_5_final(
        intent, permit, unit,
        **kit.final_apply_kwargs(
            tmp_path=tmp_path, unit=unit, state_root=state_root,
            lifecycle_lock=kit.SimulatedLifecycleLock(fail_release=True),
        ),
        s2_1_drill_receipt=kit.drill_receipt(),
        pre_drill_attestation=pre_drill,
    )
    assert verdict["status"] == "RECOVERY_REQUIRED", verdict
    assert verdict["lock_window"]["hold_released"] is False
    assert "reset_failed" not in unit.calls
    assert _journal_state(state_root, intent) == "RECOVERY_REQUIRED"


def test_a_success_receipt_without_a_proven_lock_window_is_rejected_centrally(
    tmp_path, monkeypatch
):
    """中央閘硬門:成功 receipt 必須帶「鎖窗已 typed 關閉」的三欄證據。"""

    import aiml_gate_receipt_validator as validator

    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit, **kit.apply_kwargs(tmp_path=tmp_path, unit=unit)
    )
    assert verdict["status"] == "SOURCE_SIMULATION_PASS", verdict["reasons"]
    receipt = verdict["receipt"]
    assert receipt["lock_window"]["release_status"] == lifecycle.S2_5_LOCK_RELEASED
    assert validator.validate_aiml_artifact(receipt, now=kit.NOW) == []
    for forged_window in (
        {
            "hold_acquired": True,
            "hold_released": False,
            "release_status": lifecycle.S2_5_LOCK_RELEASE_FAILED,
        },
        {
            "hold_acquired": False,
            "hold_released": False,
            "release_status": lifecycle.S2_5_LOCK_NOT_HELD,
        },
    ):
        forged = dict(receipt, lock_window=forged_window)
        forged["self_digest"] = validator.artifact_self_digest(
            {k: v for k, v in forged.items() if k != "self_digest"}
        )
        errors = validator.validate_aiml_artifact(forged, now=kit.NOW)
        assert any("typed-closed lifecycle lock window" in e for e in errors), errors
    # lock_window 整個拿掉 ⇒ closed schema 直接拒(必填欄)。
    stripped = {k: v for k, v in receipt.items() if k != "lock_window"}
    stripped["self_digest"] = validator.artifact_self_digest(
        {k: v for k, v in stripped.items() if k != "self_digest"}
    )
    assert validator.validate_aiml_artifact(stripped, now=kit.NOW)
