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
from test_agent_governance_s2_4_lock import FakeLockDriver  # noqa: E402

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
    # 交易 verdict 的終端集合是 receipt enum 的**嚴格超集**:兩個永不簽發 receipt 的終端
    # (ALREADY_APPLIED_IDEMPOTENT / RECEIPT_EMISSION_PENDING)只存在於 verdict。
    assert verdict["status"] in runner.AGGREGATE_ALL_TYPED_STATUSES, verdict["status"]
    assert verdict["status"] not in _SUCCESS_STATUSES
    assert verdict["receipt"] is None
    assert verdict["production_authority_flags"] == {
        "nine_authorities_false": True, "production_apply_performed": False,
        "running_attested": False,
    }


def assert_no_surviving_probe(fx) -> None:
    """無倖存 probe unit(**結構性**,而不是 fixture 自己寫的 receipt 欄位)。

    誠實界線(Fix-C):``receipt["transient_unit_lifecycle"]["zero_residue_verified"]`` 是
    fixture 自己寫進去的常量,對每一個 crash 窗都成立,所以斷言它**證明不了**任何本次交易的
    事實。真正載重的是兩件結構事實:(a) aggregate driver 面上沒有任何 probe 生命週期入口
    (在 driver 被接觸之前硬檢),(b) 五個 row driver 面上也沒有;於是這筆交易在構造上不可能
    產生一個 probe unit。receipt 的欄位只作為「交易開始之前 probe 已被證明零殘留」的**輸入**
    前置,故此處也一併檢查它,但它不是本函式的主張。
    """

    assert runner.assert_no_aggregate_forbidden_surface(fx.driver) == []
    for name, row_driver in fx.row_drivers.items():
        # E15:``… == [] or (row_driver is fx.row_drivers["ENGINE_SCANNER"])`` 讓**唯一那個
        # 安裝 unit 的 row**永久豁免這道檢查。今天五個 fake 都回 [],所以豁免是死的——正因為
        # 是死的,它才不會被任何測試發現,而它守的恰好是這裡最重要的一列。
        assert runner.assert_no_aggregate_forbidden_surface(row_driver) == [], name
    assert not hasattr(fx.driver, "build_transient_unit")
    assert not hasattr(fx.driver, "start_transient_unit")
    for scope in runner.PROBE_SCOPES:
        receipt = fx.probe_receipts[scope]
        assert receipt["terminal_status"] == "TERMINAL_CLEAN"
        assert receipt["transient_unit_lifecycle"]["zero_residue_verified"] is True
        assert receipt["transient_unit_lifecycle"]["removed"] is True


def assert_installed_unit_inactive(fx) -> None:
    """已安裝 unit 為 inactive 或不存在——並且該觀測**確實反映本次交易做過什麼**。

    誠實界線(Fix-C):``FakeAggregateDriver.unit_state`` 的預設值是常量 ``"inactive"``,而只有
    ``compensate_component_row`` 會改它,所以「觀測到 inactive」在**每一個** crash 窗都成立,
    包含 ENGINE_SCANNER 已經寫下 unit fragment 的那一個。此處因此改為同時檢查 ENGINE_SCANNER
    row driver 的**呼叫紀錄**:若它安裝過 fragment 而該安裝未被補償移除,``unit_state`` 必須仍
    是被觀測到的那個值,且該 driver 面上不存在任何 enable/start/restart/signal 入口。
    """

    engine = fx.row_drivers["ENGINE_SCANNER"]
    assert apply_mod.assert_no_unit_lifecycle_surface(engine) == []
    installed = any(str(call).startswith("install_unit_fragment") for call in engine.calls)
    removed = any(str(call).startswith("remove:") for call in engine.calls)
    observed = fx.driver.observe_installed_unit_state()
    assert observed is None or (
        observed.get("inactive") is True and not observed.get("active")
    ), observed
    if installed and not removed:
        # fragment 還在主機上:觀測必須是「存在且 inactive」,而不是「不存在」。
        assert observed is not None and observed.get("inactive") is True, (
            observed, engine.calls
        )
    if removed:
        assert observed is None, (observed, engine.calls)


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
    # A2:每一道「必須持有 lock」的閘現在檢查 module-private token,不再接受同形字典。
    held = lock.acquire_s2_4_install_lock(FakeLockDriver())
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
    """C8(b):journal 已終端**之後**的失敗不是「主機不明」,是「receipt 還沒投影出來」。

    主機正確且完整、沒有任何東西需要補償;缺的只有那份 receipt。過去它回
    ``RECOVERY_REQUIRED`` 且無法重試(重試會撞上 idempotent replay,而那條路過去也是
    ``RECOVERY_REQUIRED``),於是這筆安裝在不重發 permit 的前提下**永遠**產不出 receipt。
    """

    def _raise():
        raise RuntimeError("injected clock failure")

    fx.driver.trusted_host_time = _raise
    verdict = fx.apply()
    assert_typed_non_success(verdict)
    assert_no_surviving_probe(fx)
    assert_installed_unit_inactive(fx)
    assert verdict["status"] == "RECEIPT_EMISSION_PENDING"
    assert any("trusted host time is unavailable" in r for r in verdict["reasons"])
    assert any("DURABLY TERMINAL" in r for r in verdict["reasons"])
    # 終端 journal 存在、零補償、五 row 的施作原封不動留著。
    assert verdict["journal"]["terminal"] is True
    assert fx.driver.compensated == []
    assert verdict["rollback"] is None


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


# ══════════════════ E18 Fix-C:先前沒有 edge 的三個外部呼叫 ═════════════════════
def test_e16b_an_unobservable_installed_unit_is_never_compensated(fx) -> None:
    """C1:「觀測不到」與「觀測到 active」是兩件事,而且前者**絕不**觸發補償。

    對照 677a12df9 的行為:``_observe_residue`` 吞掉每一個例外並留下
    ``installed_unit_inactive=None``,呼叫端以 ``is not True`` 判,於是**一次** ``TimeoutError``
    就會把一筆已完整驗證的安裝整個拆掉(unit fragment + daemon-reload、三棵 runtime 樹、
    credential slot、PG role/ACL/HBA + reload、uid/gid 與目錄),而終端訊息還宣稱「補償後經
    獨立確認」。把一份正確的安裝原封不動留著,嚴格優於因讀取失敗而拆掉 PG 與憑證狀態。
    """

    calls: list[int] = []

    def _raise():
        calls.append(1)
        raise TimeoutError("injected unit observation timeout")

    fx.driver.observe_installed_unit_state = _raise
    verdict = fx.apply()
    assert_typed_non_success(verdict)
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert verdict["receipt"] is None
    # 有界重試之後才放棄,而不是第一次失敗就下結論。
    assert len(calls) == runner._evidence.RESIDUE_OBSERVATION_ATTEMPTS
    assert verdict["residue"]["observation_status"] == "INSTALLED_UNIT_OBSERVATION_UNAVAILABLE"
    assert any("could not be observed" in reason for reason in verdict["reasons"])
    assert any("is NOT 'observed active'" in reason for reason in verdict["reasons"])
    # **零補償**:五列的施作原封不動。
    assert fx.driver.compensated == []
    assert verdict["rollback"] is None
    for name, driver in fx.row_drivers.items():
        assert not any(str(call).startswith("remove:") for call in driver.calls), name


def test_e18_row_driver_unavailable_during_compensation_is_typed(fx) -> None:
    """C2:``_compensate_transaction`` 裡的 ``driver.row_driver()`` 過去沒有 try/except。

    一個 untyped ``RuntimeError`` 會直接逸出 §10.2 的凍結 ABI——恰好在主機處於部分施作態、
    最不能逸出的時刻。它自此經 ``redact_driver_error`` typed 化,``exact`` 設為 False。
    """

    original = fx.driver.row_driver

    def _row_driver(*, component_effect_class):
        # 補償一開始就失效(``compensate_component_row`` 先跑,故 compensated 非空)。
        if fx.driver.compensated:
            raise RuntimeError("injected row driver unavailability")
        return original(component_effect_class=component_effect_class)

    fx.driver.row_driver = _row_driver
    fx.driver.postcheck_flags["plan_lineage_verified"] = False  # 觸發補償
    verdict = fx.apply()  # 絕不逸出
    assert_typed_non_success(verdict)
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert verdict["rollback"]["exact_pre_state_restored"] is False
    assert any(
        "row driver was unavailable during compensation" in reason
        for reason in verdict["reasons"]
    )
    assert any("RuntimeError" in reason for reason in verdict["reasons"])
    persisted = fx.persisted_install_journal()
    assert persisted is not None and persisted["terminal"] is True


def test_e18_install_lock_release_failure_is_never_a_clean_success(fx) -> None:
    """C11:``finally: release_s2_4_install_lock(...)`` 的 typed 回值過去被整個丟掉。

    於是 ``INSTALL_LOCK_RECOVERY_REQUIRED``(``close()`` 拋例外 = FD 可能仍持有 flock)完全
    不可見:一筆帶著未釋放 lock 的交易照樣簽出 receipt。刪掉整個 ``finally`` 對每一支測試
    都是隱形的。
    """

    def _close(*, fd):
        raise OSError("injected close failure")

    fx.lock_fake.close = _close
    verdict = fx.apply()
    assert_typed_non_success(verdict)
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert verdict["receipt"] is None
    assert verdict["lock_release"]["status"] == "RECOVERY_REQUIRED"
    assert any(
        "was not cleanly released" in reason for reason in verdict["reasons"]
    )


# ══════════════════ E7-E11 的第二種失敗模式:mid-effect 主機失敗 ═════════════════
_MID_EFFECT_FAILURE = {
    "HOST_IDENTITY_INSTALL": "create_directory",
    "PG_ROLE_ACL_MIGRATION": "apply_manifest_grants",
    "CREDENTIAL_INSTALL": "install_encrypted_slot",
    "LEARNING_RUNTIME": "publish_tree",
    "ENGINE_SCANNER": "install_unit_fragment",
}


@pytest.mark.parametrize("failing_row", list(runner.APPLY_ROW_ORDER))
def test_e7_to_e11_mid_effect_host_failure(fx, failing_row) -> None:
    """§10.5 #6 的第二種失敗模式:主機動作**做到一半**拋例外(不是 postcheck 說不行)。

    五個 edge 過去全部只用 ``postcheck_ok=False`` 一種失敗模式驅動,於是「effect 本身炸掉」
    這條路徑在 aggregate 級從未被走過。
    """

    method = _MID_EFFECT_FAILURE[failing_row]
    row_driver = fx.row_drivers[failing_row]
    if not hasattr(row_driver, method):
        pytest.skip(f"{failing_row} fake has no {method} surface")
    original = getattr(row_driver, method)

    def _raise(*args, **kwargs):
        row_driver.calls.append(f"{method}:injected-failure")
        raise RuntimeError("injected mid-effect host failure")

    setattr(row_driver, method, _raise)
    try:
        verdict = fx.apply()
    finally:
        setattr(row_driver, method, original)
    assert_typed_non_success(verdict)
    assert verdict["receipt"] is None
    assert verdict["status"] in {
        "POSTCHECK_FAILED_ROLLED_BACK", "RECOVERY_REQUIRED", "PRECHECK_FAILED",
    }
    assert_no_surviving_probe(fx)
    # 前綴列(若有)一律逆序補償;失敗列自己是否算「已施作」由它的 mutation_performed 決定。
    index = runner.APPLY_ROW_ORDER.index(failing_row)
    prefix = list(runner.APPLY_ROW_ORDER[:index])
    assert set(fx.driver.compensated) >= set(prefix), (
        fx.driver.compensated, prefix
    )
    assert fx.driver.compensated == sorted(
        fx.driver.compensated,
        key=lambda name: -runner.APPLY_ROW_ORDER.index(name),
    )
    persisted = fx.persisted_install_journal()
    assert persisted is not None and persisted["terminal"] is True
    assert journal.journal_integrity_errors(persisted) == []


# ══════════════════ 矩陣完整性:edge 集合由**源碼**導出 ═════════════════════════
# 每一個 aggregate 交易可達的外部 effect edge → 覆蓋它的測試。清單是**被比對的一側**:
# 另一側由 AST 從 apply_s2_4_install_plan 可達的源碼掃出來,故新加一個 driver 呼叫而沒有
# 對應條目時,這支測試會紅——不再靠人手維護一份「測試函式名清單」。
EFFECT_EDGE_INVENTORY = {
    "driver.lock_driver": "test_e1_lock_contention_edge / test_e18_install_lock_...",
    "driver.file_driver": "test_e5_ledger_append_edge",
    "driver.row_driver": "test_e7_to_e11_fail_after_each_step / test_e18_row_driver_...",
    "driver.compensate_component_row": "test_e15_reverse_compensation_edge",
    "driver.observe_installed_unit_state": "test_e16_installed_unit_observation_edge",
    "driver.aggregate_independent_postcheck": "test_e13_aggregate_postcheck_edge",
    "driver.trusted_host_time": "test_e17_trusted_host_time_edge",
    "_lock.acquire_s2_4_install_lock": "test_e1_lock_contention_edge",
    "_lock.release_s2_4_install_lock": "test_e18_install_lock_release_failure_...",
    "_lock.consume_authorizations_under_lock": "test_e5_ledger_append_edge",
    "_lock.seal_replay_ledger": "test_e4_ledger_read_edge",
    "_lock._read_durable_ledger": "test_e4_ledger_read_edge",
    "_journal.JournalStore": "test_e3_journal_read_edge",
    "_journal.WriteAheadTransaction": "test_e12_wal_crash_windows",
    "_journal.install_journal_path": "test_e3_journal_read_edge",
    "_journal.build_install_journal": "test_e6_first_applying_fsync_edge",
    "_evidence.observe_install_residue": "test_e16b_an_unobservable_installed_unit_...",
    "_evidence.collect_driver_apply_attestation": "test_c12_* (install_driver 檔)",
    "_evidence.derive_apply_attestation_status": "test_c12_* (install_driver 檔)",
    "_evidence.build_install_evidence_set": "test_c20_* (install_driver 檔)",
    "_evidence.commit_install_evidence_set": "test_c20_* (install_driver 檔)",
    "_evidence.install_evidence_set_path": "test_c20_* (install_driver 檔)",
    "_evidence.derive_apply_remaining_ttls": "test_c4_* (install_driver 檔)",
    "_evidence.success_path_residue_reasons": "test_c16_* (install_driver 檔)",
    "_evidence.resolve_now": "test_c4_an_expired_plan_is_refused_before_any_host_contact",
    "_evidence.install_evidence_abi_projection": "W4 wave-exit 投影(非 effect edge)",
    "transaction.record": "test_e14_terminal_journal_edge / test_c6_*",
    "transaction.step": "test_e12_wal_crash_windows",
    "store.load": "test_replaying_the_same_key_re_executes_nothing",
    # durable 證據集的落盤 edge(與 journal/ledger 逐字同一套 temp→fsync→rename→parent-fsync)。
    "store._open_parent": "test_c20_* (install_driver 檔)",
    "store._reresolve_parent_reasons": "test_c20_* (install_driver 檔)",
    "file_driver.create_temp_file": "test_c20_* / test_e5_ledger_append_edge",
    "file_driver.write_bytes": "test_e5_ledger_append_edge / test_e14_terminal_journal_edge",
    "file_driver.fsync_file": "test_c20_* (install_driver 檔)",
    "file_driver.atomic_rename": "test_c20_* (install_driver 檔)",
    "file_driver.fsync_parent_dir": "test_c20_* (install_driver 檔)",
    "file_driver.close": "test_c20_* (install_driver 檔)",
    "_journal.assert_no_journal_destructive_surface": "test_e3_journal_read_edge",
    "_journal.journal_temp_basename": "test_c20_* (install_driver 檔)",
    "_journal._temp_file_precheck_reasons": "test_c20_* (install_driver 檔)",
    "_journal._temp_residue_reason": "test_c20_* (install_driver 檔)",
    "_journal.JournalContractError": "install_evidence_set_path 的 typed 契約錯(非 effect edge)",
    "_journal.journal_terminal_state": "test_e1_* 的 idempotent-replay 分支(install_driver 檔)",
    # ── §10.1.1 拆分後的其餘四個可達葉(E6:掃描面自兩個模組擴到六個)──────────────
    # reconcile 葉(§5.2 啟動收斂,step 7)。
    "_component.ownership_binding_reasons": "test_a7_* / test_c23_* (§5.3 ownership 綁定)",
    "_component.ownership_evidence_reasons": "test_a7_* (§5.3 ownership 證據)",
    "driver.startup_reconcile_surface": "test_a8_the_probe_entrypoint_reconciles_...",
    "driver.list_journal_basenames": "test_a4_a_driver_without_an_enumeration_surface_...",
    "store.list_basenames": "test_a4_/test_a5_ (§5.2 三個 parent 的列舉)",
    "store.commit": "test_e6_first_applying_fsync_edge / test_e14_terminal_journal_edge",
    "_journal.reconcile_journal": "test_reconcile_resume_and_not_applied_projections",
    # component 葉(row 契約機制 + 補償後獨立 postcheck)。
    "_component.compensation_with_independent_postcheck": "test_c3_* (install_driver 檔)",
    "_component.derive_compensation_status": "test_c3_* / test_e15_reverse_compensation_edge",
    # S2.4-AMEND-2:PG row 的 plan-derived expected_topology 失敗時的 typed 拒建構點
    # (零 driver 接觸、零 mutation,非 effect edge)。
    "_component._verdict": (
        "test_an_absent_tampered_or_misbound_hba_delta_is_topology_unproven (install_driver 檔)"
    ),
    "_component.derive_recorded_evidence_class": "test_c12_* (install_driver 檔)",
    "_component.scan_serializable_surface": "§10.5 #15 秘密掃描(verdict 出境面)",
    "driver.independent_postcheck": "test_c3_* / test_e15_reverse_compensation_edge",
    "driver.evidence_class": "test_c12_a_self_declared_attested_driver_...",
    # evidence 葉的 apply attestation surface(APPLIED_INACTIVE 的唯一鑰匙)。
    "driver.apply_attestation": (
        "test_c12_* (foreign_key / corrupted_signature_bytes 兩支負向;install_driver 檔)"
    ),
    # journal 葉:JournalStore 的 durable 落盤/讀回/列舉面(自 self.driver 走)。
    "driver.open_parent_directory": "test_e3_journal_read_edge / test_e2_lock_precheck_edge",
    "driver.read_journal_bytes": "test_e3_journal_read_edge",
    "driver.create_temp_file": "test_e5_ledger_append_edge / test_e14_terminal_journal_edge",
    "driver.write_bytes": "test_e5_ledger_append_edge / test_e14_terminal_journal_edge",
    "driver.fsync_file": "test_e14_terminal_journal_edge",
    "driver.atomic_rename": "test_e14_terminal_journal_edge",
    "driver.fsync_parent_dir": "test_e14_terminal_journal_edge",
    "driver.close": "test_a12_a_contended_acquisition_closes_the_lock_fd",
    "driver.journal_transition": "test_the_row_journalling_is_routed_through_the_shared_wal_...",
    "_journal.redact_driver_error": "typed 錯誤遮蔽(非 effect edge)",
    # lock 葉:install lock 的 openat/fstat/flock 面。
    "driver.openat_lock_file": "test_e2_lock_precheck_edge",
    "driver.fstat_lock_file": "test_e2_lock_precheck_edge",
    "driver.flock_exclusive_nonblocking": "test_e1_lock_contention_edge",
    "_lock.install_lock_is_held": "test_a2_* (forged/released lock proof)",
    "_lock._lock_not_held_reasons": "test_a2_* (forged/released lock proof)",
}
_EFFECT_RECEIVERS = {"driver", "file_driver", "lock_driver", "row_driver", "transaction", "store"}
# E6:交易真正**到達**的六個葉(install_driver 自己 + §10.1.1 拆出的 evidence / reconcile /
# component,以及 W4a 的 journal / lock)。只掃前兩個等於宣告「reconcile 葉與 journal/lock 葉
# 裡的 driver 呼叫不是 effect edge」——``reconcile_startup_journals`` 是 step 7,而
# ``store.list_basenames()`` 最終就落在 ``lister(parent_fd=…)`` 上。
_EFFECT_MODULES = {"_lock", "_journal", "_evidence", "_component", "_reconcile"}
# 屬性接收者 → 它其實是哪個 effect 面(``self._store.commit(...)`` / ``self.driver.close(...)``
# / ``self._driver.x(...)`` 這些形狀過去在構造上不可見)。
_RECEIVER_ATTRIBUTES = {
    "driver": "driver", "_driver": "driver",
    "store": "store", "_store": "store",
    "transaction": "transaction", "_transaction": "transaction",
    "file_driver": "file_driver", "lock_driver": "lock_driver", "row_driver": "row_driver",
}


def _effect_scan_modules() -> list:
    """aggregate 交易可達的六個葉(module 物件;順序不影響結果)。"""

    return [
        runner, runner._evidence, runner._component, runner._journal, runner._lock,
        reconcile_leaf,
    ]


def _edge_receiver(node, aliases: dict[str, str]) -> str | None:
    """把一個 AST 接收者正規化成 effect 面名(``ast.Name`` / 屬性 / 區域別名皆可見)。"""

    import ast

    if isinstance(node, ast.Name):
        name = aliases.get(node.id, node.id)
        return name if name in _EFFECT_RECEIVERS or name in _EFFECT_MODULES else None
    if isinstance(node, ast.Attribute):
        name = _RECEIVER_ATTRIBUTES.get(node.attr)
        return name if name in _EFFECT_RECEIVERS else None
    return None


def _edge_aliases(tree) -> dict[str, str]:
    """``_alias = driver`` 這種區域別名(M27 的形狀)→ 它指向的 effect 面。"""

    import ast

    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        base = _edge_receiver(node.value, {})
        if base is not None:
            aliases[target.id] = base
    return aliases


def _discovered_effect_edges() -> set[str]:
    """從交易可達的**六個**葉的源碼掃出每一個外部 effect 呼叫點。

    三種呼叫形狀都看得見:``receiver.method()``、``self._receiver.method()``、
    ``alias = receiver`` 之後的 ``alias.method()``,以及
    ``getattr(receiver, "method", …)``(``collect_driver_apply_attestation`` 正是這一種,
    所以 ``driver.apply_attestation`` —— APPLIED_INACTIVE 的鑰匙 —— 過去完全不被發現)。
    """

    import ast
    import inspect

    edges: set[str] = set()
    for module in _effect_scan_modules():
        tree = ast.parse(inspect.getsource(module))
        aliases = _edge_aliases(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id == "getattr" and len(node.args) >= 2:
                base = _edge_receiver(node.args[0], aliases)
                literal = node.args[1]
                if base is not None and isinstance(literal, ast.Constant) and isinstance(
                    literal.value, str
                ):
                    edges.add(f"{base}.{literal.value}")
                continue
            if not isinstance(func, ast.Attribute):
                continue
            base = _edge_receiver(func.value, aliases)
            if base is not None:
                edges.add(f"{base}.{func.attr}")
    return edges


def test_the_matrix_covers_every_effect_edge_discovered_in_source() -> None:
    """C21/E6:edge 集合由源碼 AST 導出,而不是一份人手維護的測試函式名清單。

    對照 677a12df9:``test_the_matrix_covers_every_named_effect_edge`` 斷言的是**本模組自己**
    的 15 個函式名加兩個長度檢查,所以在成功路徑上新加一個對外 driver 的呼叫,407 支測試全綠。
    E6 之後掃描面是交易可達的**六個**葉與四種呼叫形狀,故 ``_alias = driver`` 之後的呼叫、
    reconcile 葉裡的呼叫、``self._store.commit`` 與 ``getattr(driver, "x")()`` 都不再隱形。
    """

    discovered = _discovered_effect_edges()
    assert discovered, "the AST scan found no effect edges at all (scanner is broken)"
    unmapped = sorted(discovered - set(EFFECT_EDGE_INVENTORY))
    assert unmapped == [], (
        f"these external effect edges are reachable from apply_s2_4_install_plan but have no "
        f"declared crash-matrix entry: {unmapped}"
    )
    # 清單不得腐化成「宣告了一個源碼裡已經不存在的 edge」。
    stale = sorted(set(EFFECT_EDGE_INVENTORY) - discovered)
    assert stale == [], f"declared effect edges no longer present in source: {stale}"


@pytest.mark.parametrize("module_name", [
    "agent_governance_s2_4_install_driver",
    "agent_governance_s2_4_install_evidence",
    "agent_governance_s2_4_component",
    "agent_governance_s2_4_journal",
    "agent_governance_s2_4_lock",
    "agent_governance_s2_4_reconcile",
])
def test_the_effect_edge_scan_parses_every_leaf_the_transaction_reaches(module_name) -> None:
    """E6:掃描面是**六個**葉,不是兩個。少任何一個都讓那個葉裡的新 driver 呼叫隱形。"""

    assert module_name in {module.__name__ for module in _effect_scan_modules()}


def test_e15_the_engine_scanner_row_driver_is_not_exempt_from_the_forbidden_surface_check(
    fx,
) -> None:
    """E15:``assert_no_surviving_probe`` 曾對 ENGINE_SCANNER 開一個永久豁免。

    今天五個 fake 都沒有被禁的面,所以那個豁免是**死的**——而死的豁免不會被任何既有測試
    發現,它守的又恰好是唯一那個安裝 unit 的 row。此處把一個 ``start_unit`` 面掛到該 row
    driver 上:有豁免時本檢查什麼也不做,沒有豁免時它必須紅。
    """

    engine = fx.row_drivers["ENGINE_SCANNER"]
    assert runner.assert_no_aggregate_forbidden_surface(engine) == []
    engine.start_unit = lambda **_kwargs: None
    try:
        assert runner.assert_no_aggregate_forbidden_surface(engine) != []
        with pytest.raises(AssertionError):
            assert_no_surviving_probe(fx)
    finally:
        del engine.start_unit
