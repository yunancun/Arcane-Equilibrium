"""S2.5(WP5)三態 lifecycle fixtures——§10.5 #29 第二子句的 source 表達(design §8.1)。

這個檔案就是活 ABI obligation ``S2_5_LIFECYCLE_FIXTURES_DO_NOT_EXIST`` 的關閉事實面:
``enable --now`` / enabled+reboot-persistence / running 五維 / rollback-to-disabled /
watchdog-reset-last 五個場景,全部在注入 harness(``SimulatedUnit``)上真實走查,真實
主機零接觸。fixture 產物的 evidence_class 恆 ``LOCAL_REPRODUCIBLE``——假冒 platform-attested
PASS 是 CLAUDE.md 硬邊界,由 schema const-false + 中央閘測試釘死(見 validator 測試)。

§9.3 latch 契約:本檔的五個場景測試 id(``test_enable_now_happy_path…`` 等)被
``test_aiml_s2_5_obligation_latch.py`` 機械釘住——改名/刪除任一場景會使 latch 變紅。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for _candidate in (HELPERS, ML_ROOT):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import agent_governance_s2_5_lifecycle as lifecycle  # noqa: E402
import s2_5_testkit as kit  # noqa: E402


# ── 場景 1:enable --now happy path(precheck → enable → 五維 → SOURCE_SIMULATION_PASS)──
def test_enable_now_happy_path_full_chain_source_simulation_pass(tmp_path, monkeypatch):
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit, **kit.apply_kwargs(tmp_path=tmp_path, unit=unit)
    )
    assert verdict["status"] == "SOURCE_SIMULATION_PASS", verdict["reasons"]
    receipt = verdict["receipt"]
    assert receipt["schema_version"] == "s2_5_running_attestation_v1"
    assert receipt["evidence_class"] == "LOCAL_REPRODUCIBLE"
    assert receipt["trusted_host_attestation"] is None
    assert receipt["boundary"]["fixture_impersonates_platform_attested"] is False
    # unit 真的被翻成 enabled/active/running(harness 狀態機,非宣稱)。
    assert unit.properties["ActiveState"] == "active"
    assert unit.properties["UnitFileState"] == "enabled"
    assert "enable_now" in unit.calls
    # WAL:APPLYING 先寫、terminal 收尾(journal 檔名由 start_id 派生,P2-d)。
    journal_path = lifecycle.s2_5_journal_path(tmp_path / "state", intent["start_id"])
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    states = [entry["state"] for entry in journal["history"]]
    assert states[0] == "APPLYING" and journal["state"] == "TERMINAL_SUCCESS"
    # P1-3:journal 釘住消費當下的 ledger head(截斷/清空自此可測)。
    assert journal["replay_ledger_head"]["entry_count"] == 1


# ── 場景 2:enabled / reboot-persistence(WantedBy link + manager 語義;O-6 後者)────
def test_enabled_and_reboot_persistence_source_half(tmp_path, monkeypatch):
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit, **kit.apply_kwargs(tmp_path=tmp_path, unit=unit)
    )
    receipt = verdict["receipt"]
    persistence = receipt["enabled_persistence"]
    assert persistence["unit_file_state"] == "enabled"
    assert persistence["wanted_by_link_present"] is True
    # O-6:真 reboot 存活誠實留 effect/S3.4——source lane 恆 null,絕不冒 true。
    assert persistence["reboot_survival_observed"] is None
    # harness「重啟 manager」後 unit 仍 enabled(persistence 的 source 可證半邊)。
    unit.manager_restart()
    assert unit.properties["UnitFileState"] == "enabled"
    assert unit.wanted_by_link is True


# ── 場景 3:running 五維逐維失敗注入 ⇒ 對應維 fail ⇒ 整份非 PASS ─────────────────────
@pytest.mark.parametrize("dotted, value, dimension", [
    ("unit.unit_file_state", "disabled", "unit"),                      # disabled 未翻
    ("unit.main_pid", 0, "unit"),                                      # MainPID=0
    ("pid_cgroup.control_group_match", False, "pid_cgroup"),           # cgroup 外進程
    ("mount.loader_closure_match", False, "mount"),                    # loader 閉包外 mapping
    ("mount.executable_mappings_in_manifest", False, "mount"),         # manifest 外 mapping
    ("network.listening_sockets_empty", False, "network"),             # 監聽 socket 出現
    ("pg_identity.advisory_lock_holder_count", 2, "pg_identity"),      # advisory lock 雙持有
    ("pg_identity.advisory_lock_holder_count", 0, "pg_identity"),      # advisory lock 零持有
    ("pg_identity.unclosed_session_absent", False, "pg_identity"),     # unclosed session 懸掛
])
def test_each_running_dimension_failure_fails_the_whole_attestation(
    tmp_path, monkeypatch, dotted, value, dimension
):
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    observers = kit.HarnessObserver(
        unit, clock=kit.frozen_clock(), faults={dotted: value}
    )
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(tmp_path=tmp_path, unit=unit, observers=observers),
    )
    assert verdict["status"] == "ATTESTATION_FAILED", verdict
    assert any(dimension in reason for reason in verdict["reasons"]), verdict["reasons"]
    # 對應維 fail ⇒ 整份 attestation 非 PASS,且已 rollback 回 disabled/inactive。
    assert verdict["rollback_receipt"]["status"] == "RESTORED_INACTIVE"
    assert unit.properties["ActiveState"] == "inactive"
    assert unit.properties["UnitFileState"] == "disabled"


# ── 場景 4:rollback-to-disabled(start 失敗與 attestation 失敗兩路;rollback 自身失敗誠實)──
def test_rollback_to_disabled_restores_the_exact_s2_4_prestate(tmp_path, monkeypatch):
    # 4a. start 失敗路:enable --now 炸 → rollback → RESTORED_INACTIVE。
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    unit.fail_enable = True
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit, **kit.apply_kwargs(tmp_path=tmp_path, unit=unit)
    )
    assert verdict["status"] == "ATTESTATION_FAILED"
    rollback = verdict["rollback_receipt"]
    assert rollback["kind"] == "ROLLBACK_TO_DISABLED"
    assert rollback["status"] == "RESTORED_INACTIVE"
    assert rollback["post_state"]["active_state"] == "inactive"
    assert rollback["post_state"]["unit_file_state"] == "disabled"
    # post_state 等於 S2.4 inactive 前態(digest 綁定)。
    import aiml_gate_receipt_validator as validator
    assert rollback["s2_4_inactive_prestate_digest"] == validator.canonical_digest(
        kit.s2_4_prestate()
    )
    # 4b. attestation 失敗路已由場景 3 覆蓋 rollback;此處驗 rollback 自身失敗的誠實面。
    _key2, intent2, permit2, unit2 = kit.a_side_setup(tmp_path, monkeypatch)
    observers = kit.HarnessObserver(
        unit2, clock=kit.frozen_clock(), faults={"network.listening_sockets_empty": False}
    )
    unit2.fail_rollback = True
    state_root = kit.fresh_state_root(tmp_path, "state-4b")
    recovery = kit.recovery_controller(state_root)
    verdict2 = lifecycle.apply_s2_5_start(
        intent2, permit2, unit2,
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=unit2, observers=observers,
            state_root=state_root,
            recovery_state=recovery,
        ),
    )
    # rollback 失敗 → NOT_RESTORED 誠實失敗 + RECOVERY_REQUIRED,絕不轉成功。
    assert verdict2["status"] == "RECOVERY_REQUIRED"
    assert verdict2["rollback_receipt"]["status"] == "NOT_RESTORED"
    assert recovery.unresolved is not None
    # recovery 未解時擋下一次 apply(§3.1c)。
    _key3, intent3, permit3, unit3 = kit.a_side_setup(tmp_path, monkeypatch)
    verdict3 = lifecycle.apply_s2_5_start(
        intent3, permit3, unit3,
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=unit3,
            state_root=state_root,
            recovery_state=recovery,
        ),
    )
    assert verdict3["status"] == "RECOVERY_REQUIRED"
    assert unit3.calls == []  # 零 driver 接觸。


# ── 場景 5:watchdog reset last(supervening restart ⇒ RESET_CLEAN 不可達)───────────
def test_watchdog_reset_last_supervening_restart_blocks_reset_clean(tmp_path, monkeypatch):
    # 5a. 乾淨 reset:RESET_CLEAN + SOURCE_SIMULATION_PASS(pre-drill 錨=真 S2.5A receipt)。
    _key, intent, permit, unit, pre_drill = kit.b_side_setup(tmp_path, monkeypatch)
    verdict = lifecycle.apply_s2_5_final(
        intent, permit, unit,
        **kit.final_apply_kwargs(tmp_path=tmp_path, unit=unit),
        s2_1_drill_receipt=kit.drill_receipt(),
        pre_drill_attestation=pre_drill,
    )
    assert verdict["status"] == "SOURCE_SIMULATION_PASS", verdict["reasons"]
    assert verdict["reset_receipt"]["status"] == "RESET_CLEAN"
    watchdog = verdict["receipt"]["watchdog_last"]
    assert watchdog["watchdog_usec"] == "none"  # O-2:unit 無 WatchdogSec,誠實記 none。
    assert watchdog["n_restarts_after"] == 0
    assert watchdog["unexplained_restart_detected"] is False
    assert unit.calls[-2] == "reset_failed" or "reset_failed" in unit.calls
    # 5b. reset 之後注入一次 supervening restart ⇒ RESET_CLEAN 不可達。
    _key2, intent2, permit2, unit2, pre_drill2 = kit.b_side_setup(tmp_path, monkeypatch)
    original_reset = unit2.reset_failed
    def _reset_then_restart():
        original_reset()
        unit2.supervening_restart()
    unit2.reset_failed = _reset_then_restart
    verdict2 = lifecycle.apply_s2_5_final(
        intent2, permit2, unit2,
        **kit.final_apply_kwargs(
            tmp_path=tmp_path, unit=unit2,
            state_root=kit.fresh_state_root(tmp_path, "state-5b"),
        ),
        s2_1_drill_receipt=kit.drill_receipt(),
        pre_drill_attestation=pre_drill2,
    )
    assert verdict2["status"] == "ATTESTATION_FAILED"
    assert verdict2["rollback_receipt"]["status"] == "FAILED"
    assert verdict2["rollback_receipt"]["watchdog_last"][
        "unexplained_restart_detected"
    ] is True
