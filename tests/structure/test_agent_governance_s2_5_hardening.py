"""S2.5(WP5 tranche 1b)對抗審查退回件的紅→綠測試(E2/E3 findings)。

修前紅證據:同批斷言在 pristine HEAD ``e7dc140b8`` 的 scratchpad clone 上以舊簽名重放,
全部 FAIL(P1-1 例外裸逸、P1-2 自報 digest 放行、P1-3 截斷/清空重放成功、P1-4/P1-5 缺件);
本檔是修後綠的正本。

- P1-1:effect 之後觀測例外不得裸逸(rollback + journal terminal + recovery 閂 + typed)。
- P1-2:上游 artifact digest 就地重算;production S2.5B 必錨 production RUNNING_ATTESTED。
- P1-3:replay ledger 持久化 + head-anchor(截斷/清空/fork 全拒)。
- P1-5:install_lock_free 由真 flock 探測導出(§11.14 lock 競爭 typed 拒)。
- P2:redaction/secret 掃描、§5.3 rollback 詮釋、TTL 預算、owner 重算、kind 錯配、
  前向 skew、非有限數。
"""
from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for _candidate in (HELPERS, ML_ROOT):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import agent_governance_s2_5_attestation as attestation  # noqa: E402
import agent_governance_s2_5_lifecycle as lifecycle  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
import s2_5_testkit as kit  # noqa: E402


# ── P1-1(E3):enable_now 之後的觀測例外不得裸逸 ──────────────────────────────────
def _journal_state(tmp_path: Path, intent: dict) -> str:
    journal_path = lifecycle.s2_5_journal_path(tmp_path / "state", intent["start_id"])
    return json.loads(journal_path.read_text(encoding="utf-8"))["state"]


def test_observer_exception_rolls_back_latches_recovery_and_stays_typed(
    tmp_path, monkeypatch
):
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    observers = kit.HarnessObserver(unit, clock=kit.frozen_clock())

    def _boom():
        raise RuntimeError("observer backend lost")

    observers.observe_running_dimensions = _boom
    recovery = lifecycle.S2_5RecoveryState()
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=unit, observers=observers, recovery_state=recovery,
        ),
    )
    # 例外臂:typed verdict + rollback 回 inactive/disabled + journal terminal + 閂。
    assert verdict["status"] == "ATTESTATION_FAILED"
    assert any("observation raised" in reason for reason in verdict["reasons"])
    assert verdict["rollback_receipt"]["status"] == "RESTORED_INACTIVE"
    assert unit.properties["ActiveState"] == "inactive"
    assert unit.properties["UnitFileState"] == "disabled"
    assert recovery.unresolved is not None
    assert _journal_state(tmp_path, intent) == "TERMINAL_ROLLED_BACK"


def test_bad_oldest_evidence_timestamp_rolls_back_instead_of_escaping(
    tmp_path, monkeypatch
):
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    observers = kit.HarnessObserver(unit, clock=kit.frozen_clock())
    observers.oldest_evidence_at = lambda: "not-a-timestamp"
    recovery = lifecycle.S2_5RecoveryState()
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=unit, observers=observers, recovery_state=recovery,
        ),
    )
    assert verdict["status"] == "ATTESTATION_FAILED"
    assert unit.properties["ActiveState"] == "inactive"
    assert recovery.unresolved is not None
    assert _journal_state(tmp_path, intent) == "TERMINAL_ROLLED_BACK"


def test_observation_exception_with_failed_rollback_is_recovery_required(
    tmp_path, monkeypatch
):
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    observers = kit.HarnessObserver(unit, clock=kit.frozen_clock())
    observers.observe_running_dimensions = lambda: (_ for _ in ()).throw(
        RuntimeError("observer backend lost")
    )
    unit.fail_rollback = True
    recovery = lifecycle.S2_5RecoveryState()
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=unit, observers=observers, recovery_state=recovery,
        ),
    )
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert verdict["rollback_receipt"]["status"] == "NOT_RESTORED"
    assert recovery.unresolved is not None
    assert _journal_state(tmp_path, intent) == "RECOVERY_REQUIRED"


def test_final_observation_exception_is_terminal_failed_never_an_escape(
    tmp_path, monkeypatch
):
    """P2-1(tranche 2):S2.5B `_observe_and_build` 例外臂的 mutation-killer。

    單獨把該臂的 try/except 拿掉(裸逸)即紅:RuntimeError 會直接逸出使本測試 error;
    砍 journal transition 或改 terminal state 也各自紅(斷言 TERMINAL_FAILED 落盤)。
    """

    _key, intent, permit, unit, pre_drill = kit.b_side_setup(tmp_path, monkeypatch)
    observers = kit.HarnessObserver(unit, clock=kit.frozen_clock())
    observers.observe_running_dimensions = lambda: (_ for _ in ()).throw(
        RuntimeError("post-drill observer backend lost")
    )
    verdict = lifecycle.apply_s2_5_final(
        intent, permit, unit,
        **kit.final_apply_kwargs(tmp_path=tmp_path, unit=unit, observers=observers),
        s2_1_drill_receipt=kit.drill_receipt(),
        pre_drill_attestation=pre_drill,
    )
    # 例外臂:typed verdict(絕不裸逸)+ journal TERMINAL_FAILED + reset 未發生。
    assert verdict["status"] == "ATTESTATION_FAILED"
    assert any("post-drill observation raised" in r for r in verdict["reasons"])
    assert _journal_state(tmp_path, intent) == "TERMINAL_FAILED"
    assert "reset_failed" not in unit.calls  # 觀測未證,watchdog reset 永不可發生。


def test_final_post_reset_observation_exception_latches_recovery(tmp_path, monkeypatch):
    _key, intent, permit, unit, pre_drill = kit.b_side_setup(tmp_path, monkeypatch)
    observers = kit.HarnessObserver(unit, clock=kit.frozen_clock())
    observers.observe_post_reset = lambda: (_ for _ in ()).throw(
        RuntimeError("post-reset probe lost")
    )
    recovery = lifecycle.S2_5RecoveryState()
    verdict = lifecycle.apply_s2_5_final(
        intent, permit, unit,
        **kit.final_apply_kwargs(
            tmp_path=tmp_path, unit=unit, observers=observers, recovery_state=recovery,
        ),
        s2_1_drill_receipt=kit.drill_receipt(),
        pre_drill_attestation=pre_drill,
    )
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert recovery.unresolved is not None
    assert _journal_state(tmp_path, intent) == "RECOVERY_REQUIRED"


# ── P1-2(E3/E2 F1):上游綁定不採信自報 digest ───────────────────────────────────
def test_stub_s2_4_receipt_with_self_reported_digest_is_rejected(tmp_path, monkeypatch):
    _key, intent, permit, _unit = kit.a_side_setup(tmp_path, monkeypatch)
    # 替身 stub:self_digest 照抄 core 綁定值,但內容重算不相等(修前它能一路放行到 PASS)。
    stub = {
        "schema_version": "s2_4_install_effect_receipt_v1",
        "status": "APPLIED_INACTIVE",
        "forged_payload": "anything",
        "self_digest": kit.S2_4_RECEIPT_DIGEST,
    }
    unit = kit.SimulatedUnit()
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(tmp_path=tmp_path, unit=unit, s2_4_install_effect_receipt=stub),
    )
    assert verdict["status"] == "REQUEST_REJECTED", verdict
    assert any("does not re-derive" in reason for reason in verdict["reasons"])
    assert unit.calls == []


def test_stub_drill_receipt_and_stub_pre_drill_are_rejected(tmp_path, monkeypatch):
    _key, intent, permit, unit, pre_drill = kit.b_side_setup(tmp_path, monkeypatch)
    # drill receipt 替身(自報 digest)。
    forged_drill = {
        "schema_version": "quiesce_result_v1",
        "status": "QUIESCED_STATIC_GUARDS_HELD_RESTORED",
        "forged": True,
        "self_digest": kit.DRILL_DIGEST,
    }
    verdict = lifecycle.apply_s2_5_final(
        intent, permit, UntouchableFinalDriver(),
        **kit.final_apply_kwargs(tmp_path=tmp_path, unit=unit),
        s2_1_drill_receipt=forged_drill,
        pre_drill_attestation=pre_drill,
    )
    assert verdict["status"] == "REQUEST_REJECTED"
    # pre-drill 替身(三鍵 stub,自報 digest):修前它是唯一被接受的形狀。
    stub_pre_drill = {
        "schema_version": "s2_5_running_attestation_v1",
        "status": "SOURCE_SIMULATION_PASS",
        "self_digest": pre_drill["self_digest"],
    }
    verdict2 = lifecycle.apply_s2_5_final(
        intent, permit, UntouchableFinalDriver(),
        **kit.final_apply_kwargs(tmp_path=tmp_path, unit=unit),
        s2_1_drill_receipt=kit.drill_receipt(),
        pre_drill_attestation=stub_pre_drill,
    )
    assert verdict2["status"] == "REQUEST_REJECTED"


class UntouchableFinalDriver:
    """precheck 拒絕路徑的零接觸斷言用。"""

    def __getattr__(self, name):  # noqa: D105
        raise AssertionError(f"driver surface {name!r} was touched before authorization")


def test_simulated_pre_drill_anchor_never_unlocks_a_production_final(
    tmp_path, monkeypatch
):
    # production lane 的 S2.5B 必須 pre_drill.status==RUNNING_ATTESTED 且
    # target_class==production;SOURCE_SIMULATION_PASS 錨只屬 simulated lane。
    _key, intent, permit, unit, pre_drill = kit.b_side_setup(tmp_path, monkeypatch)
    assert pre_drill["status"] == "SOURCE_SIMULATION_PASS"
    verdict = lifecycle.apply_s2_5_final(
        intent, permit, UntouchableFinalDriver(),
        **kit.final_apply_kwargs(
            tmp_path=tmp_path, unit=unit, target_class="production",
        ),
        s2_1_drill_receipt=kit.drill_receipt(),
        pre_drill_attestation=pre_drill,
    )
    assert verdict["status"] == "REQUEST_REJECTED", verdict
    assert any("production" in reason for reason in verdict["reasons"])


# ── P1-3(E3):replay ledger 持久化 + head-anchor ────────────────────────────────
def test_tail_truncated_ledger_rejects_reconsumption(tmp_path, monkeypatch):
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    ledger = kit.empty_ledger()
    first = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(tmp_path=tmp_path, unit=unit, replay_ledger=ledger),
    )
    assert first["status"] == "SOURCE_SIMULATION_PASS"
    # durable ledger 已鎖下持久化(0600;canonical self_digest)。
    ledger_path = lifecycle.s2_5_replay_ledger_path(tmp_path / "state")
    persisted = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert validator.validate_aiml_artifact(persisted) == []
    assert (os.stat(ledger_path).st_mode & 0o777) == 0o600
    # 攻擊:截掉尾 entry(消費紀錄消失),同 permit 再消費 ⇒ head-anchor 拒。
    ledger["entries"].pop()
    unit2 = kit.SimulatedUnit()
    second = lifecycle.apply_s2_5_start(
        intent, permit, unit2,
        **kit.apply_kwargs(tmp_path=tmp_path, unit=unit2, replay_ledger=ledger),
    )
    assert second["status"] == "AUTHORIZATION_REJECTED", second
    assert any("truncated or wiped" in reason for reason in second["reasons"])
    assert unit2.calls == []


def test_wiped_ledger_rejects_reconsumption_via_the_journal_pin(tmp_path, monkeypatch):
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    first = lifecycle.apply_s2_5_start(
        intent, permit, unit, **kit.apply_kwargs(tmp_path=tmp_path, unit=unit)
    )
    assert first["status"] == "SOURCE_SIMULATION_PASS"
    # 攻擊:整本清空——連 durable ledger 檔一併刪除;journal 釘的 head 仍在 ⇒ 拒。
    # note-1(S2E.3)之後偵測**提前**到 reconcile:終端 journal 宣稱的 ledger head 必須被
    # durable ledger 涵蓋,故 typed status 由 AUTHORIZATION_REJECTED 前移為 RECOVERY_REQUIRED
    # (擋得更早、語義更誠實:整本被清空=主機狀態不明);「永不重新放行」的保證不變。
    lifecycle.s2_5_replay_ledger_path(tmp_path / "state").unlink()
    unit2 = kit.SimulatedUnit()
    second = lifecycle.apply_s2_5_start(
        intent, permit, unit2,
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=unit2, replay_ledger=kit.empty_ledger(),
        ),
    )
    assert second["status"] == "RECOVERY_REQUIRED", second
    assert any("journal" in reason for reason in second["reasons"])
    assert any("truncated or wiped" in reason for reason in second["reasons"])
    assert unit2.calls == []


def test_forked_double_write_breaks_the_chain(tmp_path, monkeypatch):
    private_key, intent, permit, _unit = kit.a_side_setup(tmp_path, monkeypatch)
    intent_b = kit.start_intent("S2_5A_START", target_host="trade-core-b")
    permit_b = kit.signed_permit(private_key, intent_b)
    ledger = kit.empty_ledger()
    attestation.consume_s2_5_authorization(
        ledger, permit, start_id=intent["start_id"], consumed_at=kit.NOW
    )
    # 併發雙寫:第二筆沿用同一(genesis)prev ⇒ fork,seq/prev 重驗必斷。
    forked_entry = attestation.consume_s2_5_authorization(
        kit.empty_ledger(), permit_b, start_id=intent_b["start_id"], consumed_at=kit.NOW
    )
    ledger["entries"].append(forked_entry)
    intent_c = kit.start_intent("S2_5A_START", target_host="trade-core-c")
    permit_c = kit.signed_permit(private_key, intent_c)
    verdict = attestation.derive_s2_5_replay_binding(
        permit_c, ledger, start_id=intent_c["start_id"]
    )
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert any("hash chain is broken" in reason for reason in verdict["reasons"])


def test_tampered_durable_ledger_blocks_new_consumption(tmp_path, monkeypatch):
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    ledger = kit.empty_ledger()
    first = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(tmp_path=tmp_path, unit=unit, replay_ledger=ledger),
    )
    assert first["status"] == "SOURCE_SIMULATION_PASS"
    # durable ledger 被改寫(truncate 後未重封)⇒ self_digest 重算即斷 ⇒ 新消費全擋。
    ledger_path = lifecycle.s2_5_replay_ledger_path(tmp_path / "state")
    persisted = json.loads(ledger_path.read_text(encoding="utf-8"))
    persisted["entries"] = []
    ledger_path.write_text(json.dumps(persisted), encoding="utf-8")
    # anchor 層的 self_digest 重算守衛本身仍在(直接釘住,避免被下方前移的偵測遮蔽)。
    anchor_reasons = lifecycle._replay_ledger_anchor_reasons(
        lifecycle.s2_5_journal_path(tmp_path / "state", intent["start_id"]),
        ledger_path,
        kit.empty_ledger(),
    )
    assert any("self_digest" in reason for reason in anchor_reasons), anchor_reasons
    # note-1(S2E.3):終端 journal 釘的 head 未被 durable ledger 涵蓋 ⇒ reconcile 先擋
    # (RECOVERY_REQUIRED);零 effect 的保證不變。
    private_key2, intent2, permit2, unit2 = kit.a_side_setup(tmp_path, monkeypatch)
    second = lifecycle.apply_s2_5_start(
        intent2, permit2, unit2,
        **kit.apply_kwargs(tmp_path=tmp_path, unit=unit2),
    )
    assert second["status"] == "RECOVERY_REQUIRED", second
    assert any("terminal-journal" in reason for reason in second["reasons"])
    assert unit2.calls == []


# ── P1-5(E2 E1#5):§5.7 lock 真 flock 探測(§11.14 acceptance)─────────────────────
def test_real_flock_contention_yields_a_typed_rejection(tmp_path, monkeypatch):
    # F3:被持有的必須是**真的 S2.4 install lock**(修前這裡加鎖的是 S2.5 自己的 lifecycle
    # lock,卻斷言 reason 說「install lock is held」——把歸因錯誤固化進了測試)。
    install_lock_path = tmp_path / "s2-4-install.lock"
    install_lock_path.touch()
    holder_fd = os.open(install_lock_path, os.O_RDWR)
    try:
        fcntl.flock(holder_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # 對手真的持 install 鎖。
        probe = lifecycle.S2_4InstallLockFreeProbe(install_lock_path)
        assert probe.flock_probe()["held"] is True
        _key, intent, permit, _unit = kit.a_side_setup(tmp_path, monkeypatch)
        unit = kit.SimulatedUnit()
        verdict = lifecycle.apply_s2_5_start(
            intent, permit, unit,
            **kit.apply_kwargs(tmp_path=tmp_path, unit=unit, install_lock_probe=probe),
        )
        assert verdict["status"] == "REQUEST_REJECTED"
        assert any("S2.4 install lock" in reason for reason in verdict["reasons"])
        assert unit.calls == []
    finally:
        fcntl.flock(holder_fd, fcntl.LOCK_UN)
        os.close(holder_fd)
    # 釋放後同一 probe 導出 free(探測即釋放,絕不 unlink)。
    assert lifecycle.S2_4InstallLockFreeProbe(install_lock_path).flock_probe()["held"] is False
    assert install_lock_path.exists()
    # 對照:S2.5 自己的 lifecycle 鎖被持有時,理由**不再**冒充 S2.4 install lock。
    lifecycle_lock_path = tmp_path / "s2-5-lifecycle.lock"
    contender = lifecycle.S2_5LifecycleLockHold(lifecycle_lock_path)
    assert contender.acquire()["status"] == lifecycle.S2_5_LOCK_ACQUIRED
    try:
        _key2, intent2, permit2, _u2 = kit.a_side_setup(tmp_path, monkeypatch)
        unit2 = kit.SimulatedUnit()
        blocked = lifecycle.apply_s2_5_start(
            intent2, permit2, unit2,
            **kit.apply_kwargs(
                tmp_path=tmp_path, unit=unit2,
                install_lock_probe=lifecycle.S2_4InstallLockFreeProbe(install_lock_path),
                lifecycle_lock=lifecycle.S2_5LifecycleLockHold(lifecycle_lock_path),
            ),
        )
        assert blocked["status"] == "REQUEST_REJECTED", blocked
        assert not any("install lock" in reason for reason in blocked["reasons"]), blocked
        assert any("lifecycle lock" in reason for reason in blocked["reasons"]), blocked
    finally:
        contender.release()


def test_lock_probe_symlink_and_absence_semantics(tmp_path):
    # 不存在 ⇒ 無人持有;symlink ⇒ O_NOFOLLOW 拒(探測逸出=unproven-free)。
    absent = lifecycle.S2_4InstallLockFreeProbe(tmp_path / "missing.lock").flock_probe()
    assert absent == {
        "held": False, "exists": False,
        "lock_path": str(tmp_path / "missing.lock"),
    }
    real = tmp_path / "real.lock"
    real.touch()
    link = tmp_path / "link.lock"
    link.symlink_to(real)
    free, reasons = lifecycle.derive_s2_4_install_lock_free(
        lifecycle.S2_4InstallLockFreeProbe(link)
    )
    assert free is False and reasons


# ── P2-c/P2-f:redaction 與 secret-like 掃描 ───────────────────────────────────────
def test_driver_diagnostics_and_secret_shaped_reasons_are_redacted(tmp_path, monkeypatch):
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)

    def _leaky_enable():
        unit.calls.append("enable_now")
        raise subprocess.CalledProcessError(1, ["systemctl", "--secret-arg=hunter2"])

    unit.enable_now = _leaky_enable
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit, **kit.apply_kwargs(tmp_path=tmp_path, unit=unit)
    )
    assert verdict["status"] == "ATTESTATION_FAILED"
    rendered = json.dumps(verdict["reasons"])
    assert "hunter2" not in rendered and "systemctl" not in rendered
    assert any("redacted" in reason for reason in verdict["reasons"])


def test_verdict_reason_secret_scrub_is_load_bearing():
    # DSN 字面量以 runtime 拼接構造(repo 衛生閘不許 blob 內出現完整 DSN——它自己就是證據)。
    dsn_shaped = "postgres" + "://scanner:" + "supersecretpw@localhost:5432/trading_ai"
    scrubbed = lifecycle._verdict("X", [dsn_shaped + " refused"])
    assert "supersecretpw" not in json.dumps(scrubbed["reasons"])
    assert scrubbed["reasons"] == [lifecycle._S2_5_SECRET_REDACTED]
    # receipt 面:secret-like 字串在 _seal 掃描時 typed 拒(不逸出例外)。
    hits = lifecycle._secret_scan_errors({"failure_reason": "PGPASSWORD=abcdef"})
    assert hits and "secret-like" in hits[0]


# ── P2-g:§5.3 rollback 詮釋(兩方向)────────────────────────────────────────────
def test_rollback_identity_drift_is_not_restored(tmp_path, monkeypatch):
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    observers = kit.HarnessObserver(
        unit, clock=kit.frozen_clock(), faults={"network.listening_sockets_empty": False}
    )
    original_stop = unit.stop

    def _stop_and_swap_fragment():
        original_stop()
        unit.properties["FragmentDigest"] = "sha256:" + "9" * 64  # 替身 unit 滑入。

    unit.stop = _stop_and_swap_fragment
    recovery = lifecycle.S2_5RecoveryState()
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=unit, observers=observers, recovery_state=recovery,
        ),
    )
    # identity tuple 不等 ⇒ NOT_RESTORED 誠實失敗 + RECOVERY(即使 active/unit_file 都回位)。
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert verdict["rollback_receipt"]["status"] == "NOT_RESTORED"
    assert recovery.unresolved is not None


def test_rollback_restart_drift_is_recorded_without_blocking_restored(
    tmp_path, monkeypatch
):
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    observers = kit.HarnessObserver(
        unit, clock=kit.frozen_clock(), faults={"network.listening_sockets_empty": False}
    )
    original_stop = unit.stop

    def _stop_with_restart_drift():
        unit.properties["NRestarts"] = str(int(unit.properties["NRestarts"]) + 1)
        original_stop()

    unit.stop = _stop_with_restart_drift
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(tmp_path=tmp_path, unit=unit, observers=observers),
    )
    rollback = verdict["rollback_receipt"]
    # n_restarts 漂移記錄於 watchdog_last,不阻 RESTORED_INACTIVE(PM §5.3 詮釋)。
    assert rollback["status"] == "RESTORED_INACTIVE"
    assert rollback["watchdog_last"]["unexplained_restart_detected"] is True
    assert rollback["watchdog_last"]["n_restarts_after"] == 1


# ── P2-j:TTL 預算不等式 ────────────────────────────────────────────────────────
def test_ttl_budget_inequality_blocks_a_start_that_cannot_roll_back_in_time(
    tmp_path, monkeypatch
):
    ok = lifecycle.derive_ttl_budget_status(kit.start_core(), now=kit.NOW)
    assert ok["status"] == "TTL_BUDGET_OK"
    late = (kit.ANCHOR + timedelta(minutes=8)).isoformat()  # 剩 120s < 120+120+30。
    exceeded = lifecycle.derive_ttl_budget_status(kit.start_core(), now=late)
    assert exceeded["status"] == "TTL_BUDGET_EXCEEDED"
    _key, intent, permit, _unit = kit.a_side_setup(tmp_path, monkeypatch)
    unit = kit.SimulatedUnit()
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(tmp_path=tmp_path, unit=unit, now=late),
    )
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert any("ttl budget" in reason for reason in verdict["reasons"])
    assert unit.calls == []


# ── P2-k:owner fingerprint 模組內重算(caller 供值僅交叉檢查)──────────────────────
def test_owner_fingerprint_is_recomputed_and_cross_checked(tmp_path, monkeypatch):
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    happy = lifecycle.apply_s2_5_start(
        intent, permit, unit, **kit.apply_kwargs(tmp_path=tmp_path, unit=unit)
    )
    assert happy["status"] == "SOURCE_SIMULATION_PASS"
    # receipt 載的是模組經 WP3 compute_owner_fingerprint 重算的值。
    assert happy["receipt"]["owner_fingerprint"] == kit.OWNER_FINGERPRINT
    # caller 供值與觀測訊號不符 ⇒ 交叉檢查失敗 ⇒ rollback + ATTESTATION_FAILED。
    _key2, intent2, permit2, unit2 = kit.a_side_setup(tmp_path, monkeypatch)
    verdict = lifecycle.apply_s2_5_start(
        intent2, permit2, unit2,
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=unit2,
            state_root=kit.fresh_state_root(tmp_path, "owner-state"),
            owner_fingerprint="sha256:" + "3" * 64,
        ),
    )
    assert verdict["status"] == "ATTESTATION_FAILED"
    assert any("cross-check" in reason for reason in verdict["reasons"])
    assert unit2.properties["ActiveState"] == "inactive"  # 已 rollback。


# ── P2-a/P2-m:attestation kind 錯配與前向 skew ───────────────────────────────────
def test_kind_b_attestation_never_verifies_for_phase_a(tmp_path, monkeypatch):
    private_key, public_key, fingerprint = kit.mint_key(tmp_path)
    kit.install_pinned_key(monkeypatch, public_key, fingerprint)
    intent = kit.start_intent("S2_5A_START")
    dims = {"unit": {"active_state": "active"}}
    gate = {"verifier_node_id": "v", "stale": False}
    wrong_kind = kit.signed_attestation(
        private_key, attestation_kind="B", intent=intent,
        running_dimensions=dims, observer_gate=gate,
    )
    errors = attestation.verify_s2_5_trusted_host_attestation(
        wrong_kind, intent_digest=intent["self_digest"], running_dimensions=dims,
        observer_gate=gate, now=kit.NOW, expected_kind="A",
    )
    assert any("attestation_kind" in error for error in errors)


def test_kind_b_attestation_keeps_a_production_start_unattested(tmp_path, monkeypatch):
    private_key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    clock = kit.frozen_clock()
    preview_unit = kit.SimulatedUnit()
    preview = lifecycle.apply_s2_5_start(
        intent, kit.signed_permit(private_key, intent), preview_unit,
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=preview_unit,
            observers=kit.HarnessObserver(preview_unit, clock=clock),
            state_root=kit.fresh_state_root(tmp_path, "preview-state"),
        ),
    )
    assert preview["status"] == "SOURCE_SIMULATION_PASS"
    wrong_kind = kit.signed_attestation(
        private_key, attestation_kind="B", intent=intent,
        running_dimensions=preview["receipt"]["running_dimensions"],
        observer_gate=preview["receipt"]["observer_gate"],
    )
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=unit,
            observers=kit.HarnessObserver(unit, clock=clock),
            target_class="production", trusted_host_attestation=wrong_kind,
            state_root=kit.fresh_state_root(tmp_path, "prod-state"),
        ),
    )
    assert verdict["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert "attestation_kind" in (verdict["receipt"]["failure_reason"] or "")


def test_future_dated_attestation_is_rejected_by_the_forward_skew_cap(
    tmp_path, monkeypatch
):
    private_key, public_key, fingerprint = kit.mint_key(tmp_path)
    kit.install_pinned_key(monkeypatch, public_key, fingerprint)
    intent = kit.start_intent("S2_5A_START")
    dims = {"unit": {"active_state": "active"}}
    gate = {"verifier_node_id": "v", "stale": False}
    future = kit.signed_attestation(
        private_key, attestation_kind="A", intent=intent,
        running_dimensions=dims, observer_gate=gate,
        trusted_host_time=(kit.ANCHOR + timedelta(days=400)).isoformat(),
    )
    errors = attestation.verify_s2_5_trusted_host_attestation(
        future, intent_digest=intent["self_digest"], running_dimensions=dims,
        observer_gate=gate, now=kit.NOW,
    )
    assert any("forward clock skew" in error for error in errors)


# ── P2-e:非有限數 typed 拒(非 crash)───────────────────────────────────────────
def test_non_finite_numbers_in_permit_or_ledger_are_typed_rejections(
    tmp_path, monkeypatch
):
    private_key, public_key, fingerprint = kit.mint_key(tmp_path)
    kit.install_pinned_key(monkeypatch, public_key, fingerprint)
    intent = kit.start_intent("S2_5A_START")
    permit = kit.signed_permit(private_key, intent)
    permit["payload_binding"]["rollback_budget_seconds"] = float("nan")
    errors = attestation.verify_s2_5_operator_permit(permit, intent, now=kit.NOW)
    assert any("non-finite" in error for error in errors)
    ledger = {"entries": [{"seq": 0, "prev_entry_digest": None,
                           "authorization_id": "s2-5-auth-" + "0" * 64,
                           "start_id": intent["start_id"], "consumed_at": kit.NOW,
                           "entry_digest": "sha256:" + "0" * 64,
                           "fsynced": True, "weight": float("inf")}]}
    verdict = attestation.derive_s2_5_replay_binding(
        kit.signed_permit(private_key, intent), ledger, start_id=intent["start_id"]
    )
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert any("non-finite" in reason for reason in verdict["reasons"])


# ── P2-d:journal 路徑派生與落盤紀律 ─────────────────────────────────────────────
def test_journal_path_derives_from_start_id_and_rejects_arbitrary_names(tmp_path):
    with pytest.raises(ValueError, match="malformed"):
        lifecycle.s2_5_journal_path(tmp_path, "../../etc/passwd")
    with pytest.raises(ValueError, match="malformed"):
        lifecycle.s2_5_journal_path(tmp_path, "s2-5-not-hex")
    derived = lifecycle.s2_5_journal_path(tmp_path, "s2-5-" + "a" * 64)
    assert derived.name == f"s2-5-{'a' * 64}.journal.json"


def test_journal_durability_discipline_modes_and_no_temp_residue(tmp_path, monkeypatch):
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit, **kit.apply_kwargs(tmp_path=tmp_path, unit=unit)
    )
    assert verdict["status"] == "SOURCE_SIMULATION_PASS"
    state_root = tmp_path / "state"
    journal_path = lifecycle.s2_5_journal_path(state_root, intent["start_id"])
    assert (os.stat(state_root).st_mode & 0o777) == 0o700   # 目錄 0700。
    assert (os.stat(journal_path).st_mode & 0o777) == 0o600  # 檔案 0600。
    assert not [p for p in state_root.iterdir() if ".tmp." in p.name]  # 零暫存殘留。
