"""S2.4(WP4·W4b)aggregate 交易的 **per-effect-edge crash matrix**(§10.3 W4 exit / §10.5 #6/#7)。

W4 的 exit 謂詞是:「effect-edge crash matrix restores exact pre-state or returns typed recovery
with no surviving probe and inactive installed unit」。本檔逐一列出 aggregate 交易裡**每一個**
外部 effect edge,對每一個注入一次確定性失敗/崩潰,並斷言同一組不變量:

  1. 終端結果是 §10.2 的 typed 非成功——**永不** ``APPLIED_INACTIVE``,也永不
     ``SOURCE_SIMULATION_PASS``(那是成功身分),且永不回一份 effect receipt;
  2. **無倖存 probe unit**:aggregate 交易在構造上沒有 probe 生命週期面
     (:func:`assert_no_aggregate_forbidden_surface`),且兩份 terminal probe receipt 在任何變更
     之前就已證明 zero residue;
  3. **已安裝 unit 為 inactive**(或補償後不存在):每一條終端路徑都獨立觀測一次,
     ENGINE_SCANNER driver 上更不存在任何 enable/start/restart/signal 面;
  4. 已施作的 row 一律依 §5.4 逆序補償,exactness 只由**獨立** verifier 的補償後再觀測導出;
     無法證明 exact 即 ``RECOVERY_REQUIRED``(絕不把安全的部分態變成 ``APPLIED_INACTIVE``)。

edge → 測試名對照(每個 edge 至少一支):

===============================================  ==============================================
effect edge                                      test
===============================================  ==============================================
E1 install-lock ``flock``                        ``test_e1_lock_contention_edge``
E2 install-lock ``fstat`` 前置證明                ``test_e2_lock_precheck_edge``
E3 APPLY journal 讀回(啟動 reconcile)          ``test_e3_journal_read_edge``
E4 replay-ledger 讀回(前導 lineage)            ``test_e4_ledger_read_edge``
E5 replay-ledger durable append                  ``test_e5_ledger_append_edge``
E6 第一個 row 的 ``APPLYING`` fsync              ``test_e6_first_applying_fsync_edge``
E7-E11 五個 row 的主機 apply                     ``test_e7_to_e11_fail_after_each_step``
E12 每個 row 的三個 WAL crash 窗                 ``test_e12_wal_crash_windows``
E13 aggregate 獨立 postcheck                     ``test_e13_aggregate_postcheck_edge``
E14 終端 journal fsync                           ``test_e14_terminal_journal_edge``
E15 逆向補償 op                                  ``test_e15_reverse_compensation_edge``
E16 已安裝 unit 觀測                             ``test_e16_installed_unit_observation_edge``
E17 trusted host time                            ``test_e17_trusted_host_time_edge``
===============================================  ==============================================

時間全部錨在 :mod:`s2_4_w3b_testkit` 的凍結常量上(無 wall clock,故無日期腐化)。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
PROGRAM_CODE = ROOT / "program_code"
for candidate in (HELPERS, ML_ROOT, PROGRAM_CODE, ROOT / "tests/structure"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_4_apply as apply_mod  # noqa: E402
import agent_governance_s2_4_install_driver as runner  # noqa: E402
import agent_governance_s2_4_journal as journal  # noqa: E402
import agent_governance_s2_4_lock as lock  # noqa: E402
import agent_governance_s2_4_reconcile as reconcile_leaf  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
import s2_4_w3b_testkit as kit  # noqa: E402
import s2_4_w4b_testkit as w4b  # noqa: E402

_SUCCESS_STATUSES = {"APPLIED_INACTIVE", "SOURCE_SIMULATION_PASS"}
# 每個 row 的「施作之後才失敗」注入(§10.5 #6:fail-after-each-step)。
_FAIL_AFTER_APPLY = {
    "HOST_IDENTITY_INSTALL": {"postcheck_ok": False},
    "PG_ROLE_ACL_MIGRATION": {"postcheck_ok": False},
    "CREDENTIAL_INSTALL": {"postcheck_ok": False},
    "LEARNING_RUNTIME": {"postcheck_ok": False},
    "ENGINE_SCANNER": {"postcheck_ok": False},
}


@pytest.fixture()
def fx(tmp_path, monkeypatch):
    return w4b.Fixture(tmp_path, monkeypatch)


# ── 共用不變量 ─────────────────────────────────────────────────────────────────
def assert_typed_non_success(verdict) -> None:
    assert verdict["status"] in runner.AGGREGATE_TYPED_STATUSES, verdict["status"]
    assert verdict["status"] not in _SUCCESS_STATUSES
    assert verdict["receipt"] is None
    assert verdict["production_authority_flags"] == {
        "nine_authorities_false": True, "production_apply_performed": False,
        "running_attested": False,
    }


def assert_no_surviving_probe(fx) -> None:
    """無倖存 probe unit:aggregate 沒有 probe 面,且兩份 receipt 已證 zero residue。"""

    assert runner.assert_no_aggregate_forbidden_surface(fx.driver) == []
    for scope in runner.PROBE_SCOPES:
        receipt = fx.probe_receipts[scope]
        assert receipt["terminal_status"] == "TERMINAL_CLEAN"
        assert receipt["transient_unit_lifecycle"]["zero_residue_verified"] is True
        assert receipt["transient_unit_lifecycle"]["removed"] is True


def assert_installed_unit_inactive(fx) -> None:
    """已安裝 unit 為 inactive 或不存在;driver 上更沒有任何 enable/start 面。"""

    assert apply_mod.assert_no_unit_lifecycle_surface(
        fx.row_drivers["ENGINE_SCANNER"]
    ) == []
    observed = fx.driver.observe_installed_unit_state()
    assert observed is None or (
        observed.get("inactive") is True and not observed.get("active")
    ), observed


def assert_edge_invariants(fx, verdict) -> None:
    assert_typed_non_success(verdict)
    assert_no_surviving_probe(fx)
    assert_installed_unit_inactive(fx)


# ══════════════════ E1/E2 install lock ═════════════════════════════════════════
def test_e1_lock_contention_edge(fx) -> None:
    fx.lock_fake.flock_succeeds = False
    verdict = fx.apply()
    assert verdict["status"] == "INSTALL_LOCK_HELD"
    assert_edge_invariants(fx, verdict)
    # 零 install 變更:沒有 journal、沒有 append、沒有任何 row driver 呼叫。
    assert fx.persisted_install_journal() is None
    assert len(fx.persisted_replay_ledger()["entries"]) == 3
    assert all(driver.calls == [] for driver in fx.row_drivers.values())
    assert verdict["mutation_performed"] is False


def test_e2_lock_precheck_edge(fx) -> None:
    fx.lock_fake.lock_nlink = 2  # hardlinked lock
    verdict = fx.apply()
    assert verdict["status"] == "PRECHECK_FAILED"
    assert any("link count is not one" in reason for reason in verdict["reasons"])
    assert_edge_invariants(fx, verdict)
    assert fx.persisted_install_journal() is None
    assert all(driver.calls == [] for driver in fx.row_drivers.values())


# ══════════════════ E3/E4 durable 讀回 ═════════════════════════════════════════
def test_e3_journal_read_edge(fx) -> None:
    basename = journal.install_journal_path(fx.plan["plan_id"]).rsplit("/", 1)[-1]
    corrupt = b'{"schema_version": "s2_4_install_journal_v1", "entries": [truncated'
    fx.fs.files[basename] = corrupt
    verdict = fx.apply()
    assert verdict["status"] == "JOURNAL_CORRUPT_RECOVERY_REQUIRED"
    assert_edge_invariants(fx, verdict)
    # §5.2:畸形 journal 絕不被自動改名或覆寫。
    assert fx.fs.files[basename] == corrupt
    assert all(driver.calls == [] for driver in fx.row_drivers.values())


def test_e4_ledger_read_edge(fx) -> None:
    corrupt = b"not-json-at-all"
    fx.fs.files[w4b.LEDGER_BASENAME] = corrupt
    verdict = fx.apply()
    assert verdict["status"] == "JOURNAL_CORRUPT_RECOVERY_REQUIRED"
    assert_edge_invariants(fx, verdict)
    assert fx.fs.files[w4b.LEDGER_BASENAME] == corrupt
    assert all(driver.calls == [] for driver in fx.row_drivers.values())


# ══════════════════ E5 replay-ledger durable append ════════════════════════════
def test_e5_ledger_append_edge(tmp_path, monkeypatch) -> None:
    """ledger 的 append 是第一次 durable 寫入;短寫即 typed 非成功且零 row 變更。"""

    fixture = w4b.Fixture(tmp_path, monkeypatch, fs=w4b.CountingFs(fail_write_at=1))
    verdict = fixture.apply()
    assert_edge_invariants(fixture, verdict)
    assert verdict["status"] in {"PRECHECK_FAILED", "RECOVERY_REQUIRED"}
    assert all(driver.calls == [] for driver in fixture.row_drivers.values())
    assert fixture.persisted_install_journal() is None
    # 短寫的 temp 檔絕不被 rename 成正本:ledger 仍是前導 lineage 的三筆。
    assert len(fixture.persisted_replay_ledger()["entries"]) == 3


# ══════════════════ E6 第一個 row 的 APPLYING fsync ════════════════════════════
def test_e6_first_applying_fsync_edge(tmp_path, monkeypatch) -> None:
    """write-ahead 次序:``APPLYING`` 沒能 fsync,外部 effect 就**從未**被嘗試。"""

    fixture = w4b.Fixture(tmp_path, monkeypatch, fs=w4b.CountingFs(fail_write_at=2))
    verdict = fixture.apply()
    assert_edge_invariants(fixture, verdict)
    assert verdict["status"] in {"PRECHECK_FAILED", "RECOVERY_REQUIRED"}
    assert any(
        "the external effect was never attempted" in reason for reason in verdict["reasons"]
    )
    assert all(driver.calls == [] for driver in fixture.row_drivers.values())
    # §5.2:未 fsync 的 ``APPLYING`` 不存在;但「沒有殘留」這句話本身需要一份**終端** journal,
    # 故落盤的是一筆單獨的終端 FAILED——證據上明確區分「從未施作」與「施作後失敗」。
    persisted = fixture.persisted_install_journal()
    assert persisted is not None and persisted["terminal"] is True
    assert [entry["state"] for entry in persisted["entries"]] == ["FAILED"]
    assert journal.journal_integrity_errors(persisted) == []
    assert validator.validate_aiml_artifact(persisted) == []


# ══════════════════ E7-E11 五個 row 的 fail-after-each-step ════════════════════
@pytest.mark.parametrize("failing_row", list(runner.APPLY_ROW_ORDER))
def test_e7_to_e11_fail_after_each_step(fx, failing_row) -> None:
    """§10.5 #6:每一 row 在**施作之後**失敗,已施作的前綴依 §5.4 逆序補償。"""

    for attribute, value in _FAIL_AFTER_APPLY[failing_row].items():
        setattr(fx.row_drivers[failing_row], attribute, value)
    verdict = fx.apply()
    assert_edge_invariants(fx, verdict)
    assert verdict["status"] in {"POSTCHECK_FAILED_ROLLED_BACK", "RECOVERY_REQUIRED"}
    index = runner.APPLY_ROW_ORDER.index(failing_row)
    applied_prefix = list(runner.APPLY_ROW_ORDER[: index + 1])
    # 逆序補償恰覆蓋已施作的前綴(未施作的 row 沒有 delta,絕不被「補償」)。
    assert fx.driver.compensated == list(reversed(applied_prefix))
    # 五條 reverse op 都在 rollback 契約裡,次序 = §5.4 逆序。
    rollback = verdict["rollback"]
    assert [op["component_effect_class"] for op in rollback["reverse_ops"]] == list(
        reversed(runner.APPLY_ROW_ORDER)
    )
    assert validator.validate_aiml_artifact(rollback) == []
    assert rollback["observer_role_preserved"] is True
    assert rollback["no_secret_reconstructed"] is True
    for op in rollback["reverse_ops"]:
        assert op["per_row_rollback_digest"] == runner.per_row_rollback_digest(
            plan_id=fx.plan["plan_id"],
            component_effect_class=op["component_effect_class"],
        )
    # 終端 journal:COMPENSATING 之後是終端態,且 journal 仍完整可再導出。
    persisted = fx.persisted_install_journal()
    states = [entry["state"] for entry in persisted["entries"]]
    assert "COMPENSATING" in states
    assert states[-1] in {"COMPENSATED", "FAILED"}
    assert persisted["terminal"] is True
    assert journal.journal_integrity_errors(persisted) == []
    assert validator.validate_aiml_artifact(persisted) == []


@pytest.mark.parametrize("failing_row", list(runner.APPLY_ROW_ORDER))
def test_a_row_rejected_before_mutation_propagates_its_typed_status(fx, failing_row) -> None:
    """變更**之前**被拒的 row(且無前置 row 施作過)→ 直接投影該 row 的 typed 狀態。"""

    # intent 過期 = 該 row 在任何 driver 接觸之前即被拒。
    stale = dict(fx.component_intents)
    original = stale[failing_row]
    stale[failing_row] = runner._component.build_component_effect_intent(
        component_effect_class=failing_row,
        install_plan_digest=original["install_plan_digest"],
        pre_state_digest=original["pre_state_digest"],
        required_intent_fields=original["required_intent_fields"],
        expires_at=kit.ISSUED,
    )
    verdict = fx.apply(component_intents=stale)
    # plan 釘住 intent 的每一欄,故換掉 expiry 會先被 §10.5 #24 的輸入閘攔下。
    assert_edge_invariants(fx, verdict)
    assert verdict["status"] == "PRECHECK_FAILED"
    assert all(driver.calls == [] for driver in fx.row_drivers.values())


# ══════════════════ E12 三個 WAL crash 窗 × 五 row ═════════════════════════════
@pytest.mark.parametrize("row", list(runner.APPLY_ROW_ORDER))
@pytest.mark.parametrize("window", list(journal.WAL_FAULT_WINDOWS))
def test_e12_wal_crash_windows(fx, row, window) -> None:
    """§10.5 #7:每一 row 的三個窗各自崩潰,持久化狀態確定,且 reconcile 確定性收斂。

    崩潰 = 行程消失,故 :class:`JournalCrash` **刻意**逸出(那不是一個 typed 結果的替代品;
    它就是「沒有結果」)。可斷言的是:已 fsync 的 journal 留著、未 fsync 的不存在、已安裝的
    unit 絕不可能是 active(driver 上沒有 start 面),而下一次啟動的 reconcile 收斂是確定的。
    """

    crash = w4b.CrashingClock(f"{row}:{window}")
    with pytest.raises(journal.JournalCrash) as excinfo:
        fx.apply(fault=crash)
    assert excinfo.value.window == f"{row}:{window}"
    assert_no_surviving_probe(fx)
    assert_installed_unit_inactive(fx)
    persisted = fx.persisted_install_journal()
    assert persisted is not None and persisted["terminal"] is False
    states = [entry["state"] for entry in persisted["entries"]]
    index = runner.APPLY_ROW_ORDER.index(row)
    # 每個完成的 row 在共用 WAL 上留六筆(aggregate APPLYING、row APPLYING/APPLIED/VERIFIED、
    # aggregate APPLIED、aggregate VERIFYING)。崩潰窗因此確定持久化的最後一筆:
    #   pre_effect                        → 只有 aggregate 的 APPLYING 落了盤;
    #   post_effect_pre_observation       → row 的三筆也落了盤(effect 已發生),停在 VERIFIED;
    #   post_observation_pre_applied_fsync → 同上(再觀測不落盤),aggregate 的 APPLIED 不存在。
    if window == "pre_effect":
        assert states[-1] == "APPLYING"
        assert len(states) == 6 * index + 1
    else:
        assert states[-1] == "VERIFIED"
        assert len(states) == 6 * index + 4
    assert "VERIFYING" not in states[6 * index:]
    assert journal.journal_integrity_errors(persisted) == []
    assert validator.validate_aiml_artifact(persisted) == []
    # 下一次啟動:reconcile 對同一份 journal 的收斂是確定的。非終端的 journal 即使最後一筆
    # 是某 row 的 ``VERIFIED``(那是**該 row** 的終端,不是交易的),也絕不被當成「沒事」。
    held = {"status": lock.LOCK_STATUS_ACQUIRED}
    last = persisted["entries"][-1]
    paths = {"install": journal.install_journal_path(fx.plan["plan_id"])}

    def _reconcile(observed):
        return reconcile_leaf.reconcile_startup_journals(
            fx.fs, journal_paths=paths, lock_verdict=held,
            observed_state_digests={"install": observed},
        )

    assert _reconcile(last["post_state_digest"])["status"] == (
        "STARTUP_RECONCILE_RESUME_VERIFICATION"
    )
    if window == "pre_effect":
        # 外部 effect 從未發生 → 觀測到 pre-state 即可安全標記未施作並續行。
        not_applied = _reconcile(last["pre_state_digest"])
        assert not_applied["status"] == "STARTUP_RECONCILE_STEP_NOT_APPLIED"
        assert not_applied["admits_new_work"] is True
    else:
        # effect 已發生:該步永遠不會被判成「未施作」(最後一筆的 pre == post)。
        assert last["pre_state_digest"] == last["post_state_digest"]
        assert _reconcile(last["pre_state_digest"])["status"] == (
            "STARTUP_RECONCILE_RESUME_VERIFICATION"
        )
    ambiguous = _reconcile("sha256:" + "9" * 64)
    assert ambiguous["status"] == "RECOVERY_REQUIRED"
    assert ambiguous["admits_new_work"] is False
    assert ambiguous["mutation_performed"] is False


def test_e12c_a_row_level_verified_is_not_a_terminal_transaction(fx) -> None:
    """§5.2 fail-closed:非終端 journal 的最後一筆是 row 的 ``VERIFIED`` 也不得放行新 plan。

    APPLY 的共用 WAL 上,某個 row 內部的 ``VERIFIED`` 是**該 row** 的終端而非**交易**的終端。
    只看最後一筆 state 會把一筆未完成的交易誤判成「沒事」,於是新 plan 被放行、主機上卻躺著
    部分施作的狀態。收斂因此必須同時要求 journal 自己宣告 ``terminal``。
    """

    crash = w4b.CrashingClock("HOST_IDENTITY_INSTALL:post_effect_pre_observation")
    with pytest.raises(journal.JournalCrash):
        fx.apply(fault=crash)
    persisted = fx.persisted_install_journal()
    assert persisted["terminal"] is False
    assert persisted["entries"][-1]["state"] == "VERIFIED"
    # 只看 state 會回 TERMINAL_NOTHING_TO_RECONCILE;實際必須落在觀測驅動的四分上。
    assert journal.journal_terminal_state(persisted) in journal.TERMINAL_JOURNAL_STATES
    verdict = journal.reconcile_journal(persisted, observed_state_digest="sha256:" + "9" * 64)
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert verdict["mutation_performed"] is False
    # 同一份 journal 標成 terminal 之後才「無需收斂」。
    closed = dict(persisted)
    closed["terminal"] = True
    closed = journal.seal_journal(closed)
    assert journal.reconcile_journal(
        closed, observed_state_digest="sha256:" + "9" * 64
    )["status"] == "TERMINAL_NOTHING_TO_RECONCILE"


@pytest.mark.parametrize("label", [
    "pre_lock", "post_lock", "pre_consume", "post_consume", "pre_aggregate_postcheck",
    "pre_terminal_journal",
])
def test_e12b_aggregate_level_crash_windows(fx, label) -> None:
    """aggregate 級的六個窗:lock 前後、消費前後、postcheck 前、終端 journal 前。"""

    crash = w4b.CrashingClock(label)
    with pytest.raises(journal.JournalCrash):
        fx.apply(fault=crash)
    assert_no_surviving_probe(fx)
    assert_installed_unit_inactive(fx)
    ledger = fx.persisted_replay_ledger()
    persisted = fx.persisted_install_journal()
    if label in {"pre_lock", "post_lock", "pre_consume"}:
        # 消費之前崩潰:零 append、零 journal。
        assert len(ledger["entries"]) == 3
        assert persisted is None
    elif label == "post_consume":
        # 已消費、尚未動任何 row:兩筆 append 存在,journal 仍未開始。
        assert len(ledger["entries"]) == 5
        assert persisted is None
    else:
        assert len(ledger["entries"]) == 5
        assert persisted is not None and persisted["terminal"] is False


# ══════════════════ E13 aggregate 獨立 postcheck ═══════════════════════════════
def test_e13_aggregate_postcheck_edge(fx) -> None:
    fx.driver.postcheck_flags["pre_state_lineage_verified"] = False
    verdict = fx.apply()
    assert_edge_invariants(fx, verdict)
    assert verdict["status"] == "POSTCHECK_FAILED_ROLLED_BACK"
    assert verdict["postcheck"]["status"] == "FAIL"
    assert verdict["rollback"]["status"] == "COMPENSATED_EXACT"
    # 五 row 全施作過 → 五條逆向 op 全跑。
    assert fx.driver.compensated == list(reversed(runner.APPLY_ROW_ORDER))
    assert verdict["rollback"]["daemon_reload_reasserted"] is True
    assert verdict["rollback"]["hba_reload_reasserted"] is True


def test_e13b_aggregate_postcheck_that_raises_is_typed(fx) -> None:
    def _raise(**kwargs):
        raise RuntimeError("injected postcheck failure")

    fx.driver.aggregate_independent_postcheck = _raise
    verdict = fx.apply()
    assert_edge_invariants(fx, verdict)
    assert verdict["status"] in {"POSTCHECK_FAILED_ROLLED_BACK", "RECOVERY_REQUIRED"}
    assert any("RuntimeError" in reason for reason in verdict["reasons"])


# ══════════════════ E14 終端 journal fsync ═════════════════════════════════════
def test_e14_terminal_journal_edge(tmp_path, monkeypatch) -> None:
    """終端 ``VERIFIED`` 沒能 fsync → 絕不簽發 receipt(§10.5 #14),逆序補償。"""

    # 寫入序:1 = ledger append,2..31 = 五 row × 六筆(aggregate 三 + row 內部三),
    # 32 = 交易的終端 VERIFIED。
    fixture = w4b.Fixture(tmp_path, monkeypatch, fs=w4b.CountingFs(fail_write_at=32))
    verdict = fixture.apply()
    assert_edge_invariants(fixture, verdict)
    assert verdict["status"] in {"POSTCHECK_FAILED_ROLLED_BACK", "RECOVERY_REQUIRED"}
    assert any("terminal APPLY journal" in reason for reason in verdict["reasons"])
    assert fixture.driver.compensated == list(reversed(runner.APPLY_ROW_ORDER))


# ══════════════════ E15 逆向補償 op ════════════════════════════════════════════
def test_e15_reverse_compensation_edge(fx) -> None:
    """補償 op 自己失敗 → ``RECOVERY_REQUIRED``(絕不宣稱 exact 還原)。"""

    fx.driver.postcheck_flags["plan_lineage_verified"] = False  # 觸發補償
    fx.driver.compensation_raises = {"CREDENTIAL_INSTALL"}
    verdict = fx.apply()
    assert_edge_invariants(fx, verdict)
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert verdict["rollback"]["status"] == "RECOVERY_REQUIRED"
    assert verdict["rollback"]["exact_pre_state_restored"] is False
    failed_op = next(
        op for op in verdict["rollback"]["reverse_ops"]
        if op["component_effect_class"] == "CREDENTIAL_INSTALL"
    )
    assert failed_op["ownership_verified"] is False
    assert any(
        "safe exact compensation could not be proved" in reason
        for reason in verdict["reasons"]
    )


def test_e15b_a_reverse_op_disproved_by_the_independent_verifier_is_recovery(fx) -> None:
    """補償「沒拋例外」但獨立 verifier 反證 → RECOVERY_REQUIRED(applier 不得自證)。"""

    fx.driver.postcheck_flags["plan_lineage_verified"] = False
    fx.row_drivers["LEARNING_RUNTIME"].residue_clean = False
    verdict = fx.apply()
    assert_edge_invariants(fx, verdict)
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert any(
        "still observes the applied state after compensation" in reason
        for reason in verdict["reasons"]
    )
    assert verdict["rollback"]["exact_pre_state_restored"] is False


def test_e15c_a_pg_reverse_op_must_reassert_hba_reload_and_keep_the_observer(fx) -> None:
    fx.driver.postcheck_flags["plan_lineage_verified"] = False
    fx.driver.compensation["PG_ROLE_ACL_MIGRATION"] = {
        "hba_reload_reasserted": False, "observer_role_preserved": False,
    }
    verdict = fx.apply()
    assert_edge_invariants(fx, verdict)
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert any("topology-attested reload operation id" in r for r in verdict["reasons"])
    assert any("aiml_observer_ro is preserved" in r for r in verdict["reasons"])


def test_e15d_a_unit_rollback_must_re_run_daemon_reload(fx) -> None:
    fx.driver.postcheck_flags["plan_lineage_verified"] = False
    fx.driver.compensation["ENGINE_SCANNER"] = {"daemon_reload_reasserted": False}
    verdict = fx.apply()
    assert_edge_invariants(fx, verdict)
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert any("typed daemon-reload" in reason for reason in verdict["reasons"])


# ══════════════════ E16 已安裝 unit 觀測 ═══════════════════════════════════════
def test_e16_installed_unit_observation_edge(fx) -> None:
    """觀測到 active/enabled → 絕不成功,且該事實本身即 §5.4 的 exactness 反證。"""

    fx.driver.unit_state = "active"
    verdict = fx.apply()
    assert_typed_non_success(verdict)
    assert_no_surviving_probe(fx)
    assert any("never a successful S2.4 apply" in r for r in verdict["reasons"])
    # 補償把 unit 移除,終端觀測因此回到 absent。
    assert fx.driver.observe_installed_unit_state() is None


def test_e16b_an_unobservable_installed_unit_is_never_a_success(fx) -> None:
    def _raise():
        raise RuntimeError("injected unit observation failure")

    fx.driver.observe_installed_unit_state = _raise
    verdict = fx.apply()
    assert_typed_non_success(verdict)
    assert_no_surviving_probe(fx)
    assert any("could not be observed" in reason for reason in verdict["reasons"])


# ══════════════════ E17 trusted host time ══════════════════════════════════════
def test_e17_trusted_host_time_edge(fx) -> None:
    def _raise():
        raise RuntimeError("injected clock failure")

    fx.driver.trusted_host_time = _raise
    verdict = fx.apply()
    assert_typed_non_success(verdict)
    assert_no_surviving_probe(fx)
    assert_installed_unit_inactive(fx)
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert any("trusted host time is unavailable" in r for r in verdict["reasons"])


# ══════════════════ 矩陣完整性(edge 清單不得靜默縮水)══════════════════════════
def test_the_matrix_covers_every_named_effect_edge() -> None:
    """每一個 aggregate 交易的 effect edge 都有對應測試(清單縮水即紅)。"""

    module = sys.modules[__name__]
    names = {name for name in dir(module) if name.startswith("test_")}
    for edge in (
        "test_e1_lock_contention_edge",
        "test_e2_lock_precheck_edge",
        "test_e3_journal_read_edge",
        "test_e4_ledger_read_edge",
        "test_e5_ledger_append_edge",
        "test_e6_first_applying_fsync_edge",
        "test_e7_to_e11_fail_after_each_step",
        "test_e12_wal_crash_windows",
        "test_e12b_aggregate_level_crash_windows",
        "test_e12c_a_row_level_verified_is_not_a_terminal_transaction",
        "test_e13_aggregate_postcheck_edge",
        "test_e14_terminal_journal_edge",
        "test_e15_reverse_compensation_edge",
        "test_e16_installed_unit_observation_edge",
        "test_e17_trusted_host_time_edge",
    ):
        assert edge in names, edge
    # 五 row × 三窗 = 15 個 WAL 窗;aggregate 級另有六個窗。
    assert len(journal.WAL_FAULT_WINDOWS) == 3
    assert len(runner.APPLY_ROW_ORDER) == 5
