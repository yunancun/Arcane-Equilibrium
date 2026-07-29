"""S2E.2b-1 C3:S2.4 §5.4 **啟動逆序補償器**的 focused 測試。

核心判準是 **crash matrix 逐 fault window 重放**:對五 row × 三個 WAL 崩潰窗各注入一次崩潰,
再對同一份持久化狀態跑一次啟動補償器,結果必須**只**收在
``STARTUP_COMPENSATION_COMPLETED_EXACT`` 或 ``RECOVERY_REQUIRED`` —— 沒有第三種。

另證(每一條都是本元件存在的理由):

* **無 permit 消費紀錄 → typed 拒且零主機接觸**(§B.1 S2c)。沒有這一道,本模組就是一支
  「找到任何 journal 就對主機做破壞性動作」的免 permit 工具;
* ``applied_rows`` 與 ``ownership_verified`` 都由 durable state 導出,caller 遞交不進來;
* ``pre_compensation_observed_digest`` 取自該 row driver 自己寫的 WAL entry(**不是** aggregate
  空間由 plan 導出的 ``_row_observation_digest`` —— 後者補償前後恆等,比對會變成空的);
* 補償成功**不**重開 lane:同一份 plan 重跑必然停在 ``RECOVERY_REQUIRED``(F-0.2)。

時間全部錨在 :mod:`s2_4_w3b_testkit` 的凍結常量上(無 wall clock,故無日期腐化)。
"""
from __future__ import annotations

import inspect
import json
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

import agent_governance_s2_4_host_recovery as recovery  # noqa: E402
import agent_governance_s2_4_install_driver as runner  # noqa: E402
import agent_governance_s2_4_install_evidence as evidence_leaf  # noqa: E402
import agent_governance_s2_4_journal as journal  # noqa: E402
import agent_governance_s2_4_lock as lock  # noqa: E402
import agent_governance_s2_4_reconcile as reconcile_leaf  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
import s2_4_w3b_testkit as kit  # noqa: E402
import s2_4_w4b_testkit as w4b  # noqa: E402
from test_agent_governance_s2_4_journal import FakeDurableFs  # noqa: E402


# 「主機處在一個既非 pre-state 也非 planned post-state 的部分態」——那正是 §5.4 的觸發條件。
_PARTIAL_STATE = "sha256:" + "9" * 64
_TERMINAL_STATUSES = {
    recovery.STARTUP_COMPENSATION_COMPLETED_EXACT,
    recovery.STARTUP_COMPENSATION_RECOVERY_REQUIRED,
}


class _RenameLatestFs(FakeDurableFs):
    """共用 in-memory fake 的一處保真度修正(**只**在本檔生效,不改共用假件)。

    ``FakeDurableFs.atomic_rename`` 以**第一個**同名 ``_temp_names`` 命中決定要 rename 哪個
    緩衝區。同一個行程內只要有兩個 :class:`JournalStore` 先後寫同一本 journal,暫存名就會重複
    (``journal_temp_basename`` 的唯一性來自 ``<pid>-<隨機>``,而 ``attempt`` 是**每個 store
    實例**從 0 起算的),於是第二個 store 的 rename 會把**第一個 store 的舊緩衝區**搬成正本。

    這正是啟動補償器的形狀:它必然是「apply 之後、同一個行程內」對同一本 journal 開的第二個
    store。真 POSIX ``renameat`` 沒有這個行為——舊暫存檔在它自己那次 rename 時就已經不叫那個
    名字了,所以「同名」只可能指最新建立的那一個。此處以逆序命中還原該語義。

    (共用假件的這個缺陷已記為 follow-up:它會讓任何「一個行程內兩次寫同一本 journal」的
    測試靜默讀到舊位元組。)
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 每一次落盤時該 journal 自報的 ``terminal``(鏈中崩潰的 fail-open 檢查用)。
        self.committed_terminals: list[tuple[str, bool]] = []

    def atomic_rename(self, *, parent_fd, from_basename, to_basename):
        self.calls.append("atomic_rename")
        for fd in reversed(list(getattr(self, "_temp_names", {}))):
            if self._temp_names[fd] == from_basename:
                self.files[to_basename] = self.temp_buffers[fd]
                body = json.loads(self.temp_buffers[fd].decode("utf-8"))
                if isinstance(body, dict) and "terminal" in body:
                    self.committed_terminals.append(
                        (str(body["entries"][-1]["state"]), bool(body["terminal"]))
                    )
                return
        raise AssertionError(f"no temp buffer for {from_basename}")


@pytest.fixture()
def fx(tmp_path, monkeypatch):
    return w4b.Fixture(tmp_path, monkeypatch, fs=_RenameLatestFs())


def _crash(fx, label):
    with pytest.raises(journal.JournalCrash):
        fx.apply(fault=w4b.CrashingClock(label))
    persisted = fx.persisted_install_journal()
    assert persisted is not None and persisted["terminal"] is False
    return persisted


def _ownership(persisted, **overrides):
    subject = {
        "s2_4_receipt_digest": "sha256:" + "a" * 64,
        "journal_digest": persisted["self_digest"],
    }
    subject.update(overrides)
    return {"install": {"journal_subject": subject}}


def _compensate(fx, persisted, **overrides):
    payload = {
        "component_intents": fx.component_intents,
        "ownership_evidence": _ownership(persisted),
        "startup_task_owned_partials": {"install": True},
        "startup_observed_state_digests": {"install": _PARTIAL_STATE},
        "probe_receipt_digests": {
            scope: receipt["self_digest"] for scope, receipt in fx.probe_receipts.items()
        },
        "clock": kit.frozen_clock(),
    }
    plan = overrides.pop("plan", fx.plan)
    authorization_set = overrides.pop("authorization_set", fx.authorization_set)
    driver = overrides.pop("driver", fx.driver)
    payload.update(overrides)
    return recovery.compensate_s2_4_startup_residue(
        plan, authorization_set, driver, **payload
    )


# --------------------------------------------------------------------------- #
# ★驗收判準★ crash matrix:逐 fault window 重放,只有兩種收場
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("row", list(runner.APPLY_ROW_ORDER))
@pytest.mark.parametrize("window", list(journal.WAL_FAULT_WINDOWS))
def test_every_crash_window_replays_into_exactly_two_terminal_statuses(fx, row, window):
    persisted = _crash(fx, f"{row}:{window}")
    verdict = _compensate(fx, persisted)

    assert verdict["status"] in _TERMINAL_STATUSES, (row, window, verdict["reasons"])
    assert verdict["status"] in recovery.STARTUP_COMPENSATION_TYPED_STATUSES
    # 本模組**不簽發** receipt,也絕不借用凍結的 receipt status enum(§B.6)。
    assert verdict["emits_effect_receipt"] is False
    assert "receipt" not in verdict
    assert verdict["production_authority_flags"] == {
        "nine_authorities_false": True, "production_apply_performed": False,
        "running_attested": False,
    }
    # 逆序:被補償的 row 一定是 §5.4 逆序的子序列,且 NO_DELTA 的 row 一步都不做。
    classification = verdict["row_classification"]
    expected_touched = [
        name for name in runner.REVERSE_COMPENSATION_ORDER
        if classification[name]["classification"] != recovery.ROW_NO_DELTA
    ]
    assert fx.driver.compensated == expected_touched, (row, window)
    # 終端 journal 落盤且自己宣告 terminal;所有 row 級記錄一律 terminal=False。
    final = fx.persisted_install_journal()
    assert final["terminal"] is True
    assert final["entries"][-1]["component_effect_class"] == (
        journal.ENTRY_SCOPE_AGGREGATE_TRANSACTION
    )
    assert journal.journal_integrity_errors(final) == []
    assert validator.validate_aiml_artifact(final) == []
    assert validator.validate_aiml_artifact(verdict["rollback"]) == []


def test_at_least_one_crash_window_reaches_completed_exact(fx):
    """反例式判準:若**每個**窗都收在 RECOVERY_REQUIRED,「兩種收場」就只是一種,而
    ``COMPLETED_EXACT`` 這條路徑從未被執行過(測試會全綠而永遠不知道)。"""

    persisted = _crash(fx, "PG_ROLE_ACL_MIGRATION:post_effect_pre_observation")
    verdict = _compensate(fx, persisted)
    assert verdict["status"] == recovery.STARTUP_COMPENSATION_COMPLETED_EXACT, (
        verdict["reasons"]
    )
    assert verdict["mutation_performed"] is True
    assert verdict["rollback"]["exact_pre_state_restored"] is True
    assert fx.persisted_install_journal()["entries"][-1]["state"] == "COMPENSATED"


def test_only_the_transaction_terminal_record_is_ever_marked_terminal(fx):
    """鏈中崩潰必須仍走四分收斂:``reconcile_journal`` 要求 ``state ∈ TERMINAL`` **且**
    ``journal["terminal"] is True`` 才算「無需收斂」,故每一筆 row 級 ``COMPENSATED`` 都必須
    ``terminal=False``——否則一次中途崩潰會被下一次啟動讀成「整筆交易已收尾」。"""

    persisted = _crash(fx, "PG_ROLE_ACL_MIGRATION:post_effect_pre_observation")
    fx.fs.committed_terminals.clear()
    assert _compensate(fx, persisted)["status"] == (
        recovery.STARTUP_COMPENSATION_COMPLETED_EXACT
    )
    trail = fx.fs.committed_terminals
    assert trail, "the compensator must have written durable records"
    assert [flag for _state, flag in trail[:-1]] == [False] * (len(trail) - 1), trail
    assert trail[-1] == ("COMPENSATED", True)
    assert {state for state, _flag in trail[:-1]} == {"COMPENSATING", "COMPENSATED"}


def test_a_crash_inside_an_effect_window_can_never_claim_exact(fx):
    """崩在 effect 窗內的 row 沒有任何自己寫的 WAL entry ⇒ 拿不到補償前觀測 ⇒ 永不宣稱 exact。"""

    persisted = _crash(fx, "CREDENTIAL_INSTALL:pre_effect")
    verdict = _compensate(fx, persisted)
    assert verdict["status"] == recovery.STARTUP_COMPENSATION_RECOVERY_REQUIRED
    assert verdict["row_classification"]["CREDENTIAL_INSTALL"]["classification"] == (
        recovery.ROW_DELTA_POSSIBLE
    )
    assert verdict["row_classification"]["CREDENTIAL_INSTALL"][
        "pre_compensation_observed_digest"
    ] is None
    assert any("cannot be checked at all" in reason for reason in verdict["reasons"])
    # 但它仍然**被補償**:一個可能存在的 delta 永遠不被跳過。
    assert "CREDENTIAL_INSTALL" in fx.driver.compensated


# --------------------------------------------------------------------------- #
# §B.1 S2c —— 本元件最重要的安全性質
# --------------------------------------------------------------------------- #
def test_without_a_replay_consumption_record_nothing_touches_the_host(fx):
    """補償是破壞性的;授權來自那兩張**已燒掉**的 permit。燒過的證據不在,就不許動主機。"""

    persisted = _crash(fx, "PG_ROLE_ACL_MIGRATION:post_effect_pre_observation")
    # 把 ledger 換成只含前導 lineage(probe/PREPARE)的 head:APPLY 的兩張 permit 從未被消費。
    w4b.seed_prior_lineage_ledger(fx.fs)
    verdict = _compensate(fx, persisted)
    assert verdict["status"] == recovery.STARTUP_COMPENSATION_RECOVERY_REQUIRED
    assert verdict["mutation_performed"] is False
    assert fx.driver.compensated == []
    assert any(
        "permit-free destructive tool" in reason for reason in verdict["reasons"]
    ), verdict["reasons"]
    # journal 沒有被加上任何一筆(零變更是結構性的,不只是「沒呼叫 driver」)。
    assert fx.persisted_install_journal()["entries"] == persisted["entries"]


@pytest.mark.parametrize("missing", list(recovery.REQUIRED_AUTHORIZATION_PROFILE_KEYS))
def test_one_permit_never_authorizes_an_apply_that_consumed_two(fx, missing):
    persisted = _crash(fx, "PG_ROLE_ACL_MIGRATION:post_effect_pre_observation")
    partial = {
        key: value for key, value in fx.authorization_set.items() if key != missing
    }
    verdict = _compensate(fx, persisted, authorization_set=partial)
    assert verdict["status"] == recovery.STARTUP_COMPENSATION_RECOVERY_REQUIRED
    assert fx.driver.compensated == []
    assert any(missing in reason for reason in verdict["reasons"])


def test_a_permit_for_another_plan_is_not_this_plans_burnt_authorization(fx):
    """一張**完全合法、真簽章**但綁到別份 plan 的 permit,不是這台主機那次 delta 的授權。

    刻意用真 builder 重簽(而不是改欄位讓 schema 先拒):那樣測到的是 schema 閘,不是本模組
    的 plan 綁定判準。
    """

    persisted = _crash(fx, "PG_ROLE_ACL_MIGRATION:post_effect_pre_observation")
    other_plan_id = "s2-4-" + "b" * 64
    forged = dict(fx.authorization_set)
    forged["apply_aggregate"] = kit.authorization(
        fx.private_key, profile_key="apply_aggregate",
        payload_binding=dict(
            fx.authorization_set["apply_aggregate"]["payload_binding"],
            plan_id=other_plan_id, idempotency_key=other_plan_id,
        ),
    )
    assert validator.validate_aiml_artifact(forged["apply_aggregate"]) == []
    verdict = _compensate(fx, persisted, authorization_set=forged)
    assert verdict["status"] == recovery.STARTUP_COMPENSATION_RECOVERY_REQUIRED
    assert fx.driver.compensated == []
    assert any("not bound to this plan" in reason for reason in verdict["reasons"]), (
        verdict["reasons"]
    )


def test_a_self_reported_authorization_id_binds_nothing(fx):
    """id 必須由**綁定這一份 plan 的 payload** 重新導出;permit 自報的值不算數。

    本模組自己再導出一次是縱深防禦:中央 schema 閘也導出同一個 id,故兩道都會說話——
    重點是「自報 id 換不到任何一次主機接觸」。
    """

    persisted = _crash(fx, "PG_ROLE_ACL_MIGRATION:post_effect_pre_observation")
    forged = dict(fx.authorization_set)
    forged["pg_migration"] = kit.authorization(
        fx.private_key, profile_key="pg_migration",
        authorization_id="sha256:" + "c" * 64,
        payload_binding=dict(fx.authorization_set["pg_migration"]["payload_binding"]),
    )
    verdict = _compensate(fx, persisted, authorization_set=forged)
    assert verdict["status"] == recovery.STARTUP_COMPENSATION_RECOVERY_REQUIRED
    assert fx.driver.compensated == []
    assert any(
        "does not re-derive from its own" in reason for reason in verdict["reasons"]
    ), verdict["reasons"]


def test_the_aggregate_permit_never_stands_in_for_the_pg_permit(fx):
    """registry invariant:「the aggregate permit never replaces the PG permit」。

    這也是本模組自己再導出一次 id **不**與中央 schema 閘重複的地方:中央閘用 permit
    **自報的** profile/namespace/payload_fields 再導出,所以一張完全合法的 aggregate permit
    被填到 ``pg_migration`` 這個位置時,它自己驗得過。本模組改用 **profile 表**的值導出,
    於是位置與身分不符當場現形。
    """

    persisted = _crash(fx, "PG_ROLE_ACL_MIGRATION:post_effect_pre_observation")
    aggregate = fx.authorization_set["apply_aggregate"]
    assert validator.validate_aiml_artifact(aggregate) == []
    substituted = {"apply_aggregate": aggregate, "pg_migration": aggregate}
    reasons = recovery.replay_consumption_reasons(
        fx.persisted_replay_ledger(), fx.plan, substituted
    )
    assert any("is not the digest re-derived from" in reason for reason in reasons), reasons
    verdict = _compensate(fx, persisted, authorization_set=substituted)
    assert verdict["status"] == recovery.STARTUP_COMPENSATION_RECOVERY_REQUIRED
    assert fx.driver.compensated == []


def test_a_stale_permit_still_proves_a_past_consumption(fx):
    """誠實界線:重啟時 permit 幾乎必然已過期;新鮮度若是判準,補償器恰在被需要時不可達。

    錨是 ledger 的 ``authorization_digest``(綁整份 canonical permit,含簽章位元組),不是 TTL。
    """

    persisted = _crash(fx, "PG_ROLE_ACL_MIGRATION:post_effect_pre_observation")
    ledger = fx.persisted_replay_ledger()
    assert recovery.replay_consumption_reasons(ledger, fx.plan, fx.authorization_set) == []
    # 同一組輸入在「現在能不能授權**新**工作」的閘上是被拒的(permit 早已過期)。
    stale = lock.derive_replay_consumption_decision(
        fx.authorization_set["apply_aggregate"], ledger,
        expected_payload_binding=None, profile_key="apply_aggregate",
        now="2099-01-01T00:00:00+00:00",
    )
    assert stale["status"] == lock.REPLAY_STATUS_REJECTED


# --------------------------------------------------------------------------- #
# §B.1 S2b / S2 gate
# --------------------------------------------------------------------------- #
def test_a_journal_read_at_this_plans_path_must_still_name_this_plan(fx):
    """S2b:四欄逐一比對。路徑由 ``plan_id`` 導出,所以只有**內容**可以說謊——一本完整性、
    schema 都通過但 ``plan_core_digest`` / ``expected_pre_state_digest`` /
    ``aggregate_rollback_digest`` 任一不符的 journal,描述的不是這份 plan,裡面沒有任何東西
    授權一次破壞性的逆序補償。
    """

    persisted = _crash(fx, "PG_ROLE_ACL_MIGRATION:post_effect_pre_observation")
    basename = journal.install_journal_path(fx.plan["plan_id"]).rsplit("/", 1)[-1]
    clean = validator._canonical_bytes(persisted)
    for field in ("plan_core_digest", "expected_pre_state_digest",
                  "aggregate_rollback_digest"):
        tampered = journal.seal_journal(dict(persisted, **{field: "sha256:" + "d" * 64}))
        assert journal.journal_integrity_errors(tampered) == []
        assert validator.validate_aiml_artifact(tampered) == []
        fx.fs.files[basename] = validator._canonical_bytes(tampered)
        verdict = _compensate(fx, tampered)
        assert verdict["status"] == recovery.STARTUP_COMPENSATION_RECOVERY_REQUIRED, field
        assert fx.driver.compensated == [], field
        assert any(
            "does not describe this plan" in reason for reason in verdict["reasons"]
        ), (field, verdict["reasons"])
        fx.fs.files[basename] = clean  # 下一輪從乾淨的 journal 重來


def test_a_journal_belonging_to_another_plan_is_never_read_at_all(fx):
    persisted = _crash(fx, "PG_ROLE_ACL_MIGRATION:post_effect_pre_observation")
    other = dict(fx.plan)
    other["plan_id"] = "s2-4-" + "d" * 64
    verdict = _compensate(fx, persisted, plan=other)
    assert verdict["status"] == recovery.STARTUP_COMPENSATION_RECOVERY_REQUIRED
    assert fx.driver.compensated == []


def test_a_clean_startup_is_not_applicable_and_touches_nothing(fx):
    verdict = _compensate(
        fx, {"self_digest": "sha256:" + "e" * 64},
        startup_task_owned_partials={}, startup_observed_state_digests={},
        ownership_evidence=None,
    )
    assert verdict["status"] == recovery.STARTUP_COMPENSATION_NOT_APPLICABLE
    assert verdict["mutation_performed"] is False
    assert fx.driver.compensated == []


def test_a_compensating_probe_or_prepare_lane_is_typed_unsupported(fx):
    """§5.4 的五 row 逆序鏈只對 install lane 有定義;別的 lane 不被「順便」處理掉。"""

    verdict = recovery._reverse_compensation_gate({
        "status": reconcile_leaf.RECONCILE_STATUS_COMPENSATE,
        "lanes": {
            "install": {"status": reconcile_leaf.RECONCILE_STATUS_CLEAN},
            "probe:s2-4-probe-" + "a" * 64: {
                "status": reconcile_leaf.RECONCILE_STATUS_COMPENSATE
            },
        },
        "reasons": [],
    })
    assert verdict["status"] == recovery.STARTUP_COMPENSATION_LANE_UNSUPPORTED
    assert any("only for the install lane" in reason for reason in verdict["reasons"])


def test_a_resume_verification_convergence_is_not_silently_compensated(fx):
    verdict = recovery._reverse_compensation_gate({
        "status": reconcile_leaf.RECONCILE_STATUS_RESUME, "lanes": {}, "reasons": [],
    })
    assert verdict["status"] == recovery.STARTUP_COMPENSATION_RECOVERY_REQUIRED


def test_no_driver_is_authority_locked_with_zero_mutation(fx):
    verdict = recovery.compensate_s2_4_startup_residue(fx.plan, fx.authorization_set, None)
    assert verdict["status"] == recovery.STARTUP_COMPENSATION_PENDING
    assert verdict["mutation_performed"] is False
    assert verdict["driver_engaged"] is False


# --------------------------------------------------------------------------- #
# §B.2 / §B.3:applied_rows 與 ownership 都由 durable state 導出
# --------------------------------------------------------------------------- #
def test_the_public_signature_accepts_no_caller_view_of_ownership_or_applied_rows():
    parameters = set(
        inspect.signature(recovery.compensate_s2_4_startup_residue).parameters
    )
    assert "ownership_verified" not in parameters
    assert "applied_rows" not in parameters
    assert "compensate_rows" not in parameters


def test_an_interrupted_previous_compensation_is_never_skipped(fx):
    """有 ``COMPENSATING`` 而無該 row 的 ``COMPENSATED`` ⇒ 必再補償(冪等),永不跳過。

    一次被中斷的補償留下的殘留與「從未補償過」在主機上不可分辨。
    """

    persisted = _crash(fx, "PG_ROLE_ACL_MIGRATION:post_effect_pre_observation")
    entries = [dict(entry) for entry in persisted["entries"]]
    entries.append({
        "seq": len(entries), "state": "COMPENSATING", "step_index": 0,
        "pre_state_digest": entries[3]["post_state_digest"],
        "post_state_digest": entries[1]["pre_state_digest"],
        "fsynced": True, "recorded_at": kit.ISSUED,
        "entry_source": journal.ENTRY_SOURCE_COMPONENT_ROW,
        "component_effect_class": "HOST_IDENTITY_INSTALL",
    })
    classification = recovery.classify_journal_rows({"entries": entries})
    assert classification["HOST_IDENTITY_INSTALL"]["classification"] == (
        recovery.ROW_DELTA_POSSIBLE
    )
    entries.append(dict(entries[-1], seq=len(entries), state="COMPENSATED"))
    assert recovery.classify_journal_rows({"entries": entries})[
        "HOST_IDENTITY_INSTALL"
    ]["classification"] == recovery.ROW_DELTA_PROVEN


def test_a_transaction_scoped_entry_never_classifies_a_row(fx):
    """``ENTRY_SCOPE_AGGREGATE_TRANSACTION`` 的 pre/post 是 plan 級前態,不屬任何一 row。"""

    classification = recovery.classify_journal_rows({"entries": [{
        "seq": 0, "state": "COMPENSATING", "pre_state_digest": "sha256:" + "1" * 64,
        "post_state_digest": "sha256:" + "1" * 64, "fsynced": True,
        "recorded_at": kit.ISSUED, "entry_source": journal.ENTRY_SOURCE_AGGREGATE,
        "component_effect_class": journal.ENTRY_SCOPE_AGGREGATE_TRANSACTION,
    }]})
    assert {row["classification"] for row in classification.values()} == {
        recovery.ROW_NO_DELTA
    }


def test_an_unbound_component_intent_is_a_caller_view_not_evidence(fx):
    persisted = _crash(fx, "PG_ROLE_ACL_MIGRATION:post_effect_pre_observation")
    tampered = {name: dict(intent) for name, intent in fx.component_intents.items()}
    tampered["HOST_IDENTITY_INSTALL"]["pre_state_digest"] = "sha256:" + "7" * 64
    verdict = _compensate(fx, persisted, component_intents=tampered)
    assert verdict["status"] == recovery.STARTUP_COMPENSATION_RECOVERY_REQUIRED
    assert fx.driver.compensated == []
    assert any("does not re-derive" in reason for reason in verdict["reasons"])


# --------------------------------------------------------------------------- #
# §B.4:pre_compensation_observed_digest 的來源
# --------------------------------------------------------------------------- #
def test_the_pre_compensation_digest_comes_from_the_row_drivers_own_wal_entry(fx):
    """**絕不**是 aggregate 空間的 ``_row_observation_digest``:那由 plan 導出、與主機無關,
    補償前後恆等 ⇒ 「verifier 有沒有真的再看一次」這道檢查會變成空的。"""

    persisted = _crash(fx, "PG_ROLE_ACL_MIGRATION:post_effect_pre_observation")
    classification = recovery.classify_journal_rows(persisted)
    row_entries = [
        entry for entry in persisted["entries"]
        if entry["component_effect_class"] == "HOST_IDENTITY_INSTALL"
        and entry["entry_source"] == journal.ENTRY_SOURCE_COMPONENT_ROW
    ]
    assert row_entries, "the row driver must have written its own entries"
    assert classification["HOST_IDENTITY_INSTALL"]["pre_compensation_observed_digest"] == (
        row_entries[-1]["post_state_digest"]
    )
    # 對照組:aggregate 空間的值是由 plan 導出的,與主機無關 —— 兩者必不相同。
    aggregate_space = evidence_leaf._row_observation_digest(
        component_effect_class="HOST_IDENTITY_INSTALL",
        component_intent_digest=runner.component_intent_plan_binding_digest(
            fx.component_intents["HOST_IDENTITY_INSTALL"]
        ),
        admitted=True,
    )
    assert classification["HOST_IDENTITY_INSTALL"][
        "pre_compensation_observed_digest"
    ] != aggregate_space


# --------------------------------------------------------------------------- #
# §B.7:失敗處理
# --------------------------------------------------------------------------- #
def test_a_failed_pre_compensation_wal_commit_stops_the_whole_chain(tmp_path, monkeypatch):
    """前 WAL 落不了盤 ⇒ 該 row 一步都不做,整鏈中止。un-journalled compensation 最壞:
    主機被拆而磁碟上沒有證據,下一次重啟會對半拆主機收斂出 RESUME_VERIFICATION。"""

    class _CountingRenameLatestFs(_RenameLatestFs, w4b.CountingFs):
        pass

    counting = _CountingRenameLatestFs()
    local = w4b.Fixture(tmp_path, monkeypatch, fs=counting)
    persisted = _crash(local, "PG_ROLE_ACL_MIGRATION:post_effect_pre_observation")
    counting.fail_write_at = counting.write_count + 1
    verdict = _compensate(local, persisted)
    assert verdict["status"] == recovery.STARTUP_COMPENSATION_RECOVERY_REQUIRED
    assert local.driver.compensated == []
    assert verdict["mutation_performed"] is False
    assert any(
        "could not be durably committed" in reason for reason in verdict["reasons"]
    ), verdict["reasons"]


def test_a_raising_compensate_row_does_not_stop_the_remaining_reverse_ops(
    tmp_path, monkeypatch
):
    local = w4b.Fixture(
        tmp_path, monkeypatch, fs=_RenameLatestFs(),
        compensation_raises=("PG_ROLE_ACL_MIGRATION",)
    )
    persisted = _crash(local, "PG_ROLE_ACL_MIGRATION:post_effect_pre_observation")
    verdict = _compensate(local, persisted)
    assert verdict["status"] == recovery.STARTUP_COMPENSATION_RECOVERY_REQUIRED
    # 後面那一 row 仍然被補償(§B.7:redact 錯誤、exact=False、**繼續**)。
    assert "HOST_IDENTITY_INSTALL" in local.driver.compensated
    assert "PG_ROLE_ACL_MIGRATION" not in local.driver.compensated
    ops = {op["component_effect_class"]: op for op in verdict["reverse_ops"]}
    assert ops["PG_ROLE_ACL_MIGRATION"]["ownership_verified"] is False


def test_an_unavailable_residue_observation_is_never_read_as_clean(tmp_path, monkeypatch):
    local = w4b.Fixture(tmp_path, monkeypatch, fs=_RenameLatestFs())

    def _raise():
        raise RuntimeError("observation unavailable")

    persisted = _crash(local, "PG_ROLE_ACL_MIGRATION:post_effect_pre_observation")
    local.driver.observe_installed_unit_state = _raise
    verdict = _compensate(local, persisted)
    assert verdict["status"] == recovery.STARTUP_COMPENSATION_RECOVERY_REQUIRED
    assert verdict["residue"]["observation_status"] == (
        evidence_leaf.RESIDUE_OBSERVATION_UNAVAILABLE
    )
    assert any("is NOT 'observed clean'" in reason for reason in verdict["reasons"])


def test_an_unclean_lock_release_downgrades_the_whole_result(fx, monkeypatch):
    persisted = _crash(fx, "PG_ROLE_ACL_MIGRATION:post_effect_pre_observation")
    original = lock.release_s2_4_install_lock

    def _dirty(driver, lock_verdict):
        original(driver, lock_verdict)
        return {
            "status": lock.LOCK_STATUS_RECOVERY_REQUIRED,
            "reasons": ["install-lock release failed: injected"],
            "lock_unlinked": False,
        }

    monkeypatch.setattr(lock, "release_s2_4_install_lock", _dirty)
    verdict = _compensate(fx, persisted)
    assert verdict["status"] == recovery.STARTUP_COMPENSATION_RECOVERY_REQUIRED
    # 政策取自 install_driver 的單一擁有者,但形狀留在本模組的 informal namespace(§B.6)。
    assert verdict["schema_version"] == recovery.STARTUP_COMPENSATION_SCHEMA_VERSION
    assert verdict["lock_release"]["status"] == lock.LOCK_STATUS_RECOVERY_REQUIRED
    assert any("not cleanly released" in reason for reason in verdict["reasons"])


def test_a_contended_install_lock_is_typed_and_touches_nothing(fx):
    from test_agent_governance_s2_4_lock import FakeLockDriver

    persisted = _crash(fx, "PG_ROLE_ACL_MIGRATION:post_effect_pre_observation")
    fx.driver._lock = FakeLockDriver(flock_succeeds=False)
    verdict = _compensate(fx, persisted)
    assert verdict["status"] == recovery.STARTUP_COMPENSATION_LOCK_HELD
    assert verdict["mutation_performed"] is False
    assert fx.driver.compensated == []


# --------------------------------------------------------------------------- #
# §B.6:補償成功不重開 lane(F-0.2)
# --------------------------------------------------------------------------- #
def test_a_successful_compensation_does_not_reopen_the_lane(fx):
    persisted = _crash(fx, "PG_ROLE_ACL_MIGRATION:post_effect_pre_observation")
    assert _compensate(fx, persisted)["status"] == (
        recovery.STARTUP_COMPENSATION_COMPLETED_EXACT
    )
    # 同一份 plan 重跑:兩張 permit 已 durable 消費且永不因 rollback 釋放 ⇒ IDEMPOTENT_REPLAY,
    # 而終端 COMPENSATED 明文不可續行 ⇒ RECOVERY_REQUIRED(F-0.2)。
    replay = fx.apply()
    assert replay["status"] == runner.AGGREGATE_STATUS_RECOVERY_REQUIRED
    assert replay["receipt"] is None
    assert any(
        "not 'VERIFIED'" in reason or "never emitted one" in reason
        for reason in replay["reasons"]
    ), replay["reasons"]


# --------------------------------------------------------------------------- #
# 結構:§A 紀律 —— row_driver() 的回傳物永遠拿不到 WAL 與 lock
# --------------------------------------------------------------------------- #
def test_the_compensator_never_wraps_a_row_driver_into_a_journal_routed_driver():
    """``JournalRoutedDriver.__getattr__`` 把一切原樣委派,所以一個假冒 row driver 只要被包
    進去就直接拿到 WAL 與 install lock。啟動補償器只把 ``row_driver()`` 的回傳物當**獨立
    verifier** 用,故它在結構上不出現在任何包裹點。"""

    source = (HELPERS / "agent_governance_s2_4_host_recovery.py").read_text(encoding="utf-8")
    assert "JournalRoutedDriver" not in source
    assert "row_driver" in source  # 反例保護:名字改了就不是這個檢查了


def test_the_typed_status_namespace_is_disjoint_from_the_frozen_receipt_enum():
    """``s2_4_install_effect_receipt_v1`` 的 status enum 裡沒有任何值的語義是「上一筆交易在
    啟動時被撤銷」;借用它等於對稽核說謊,擴充它等於改凍結 schema。"""

    own = set(recovery.STARTUP_COMPENSATION_TYPED_STATUSES)
    assert recovery.STARTUP_COMPENSATION_COMPLETED_EXACT not in runner.AGGREGATE_TYPED_STATUSES
    assert recovery.STARTUP_COMPENSATION_NOT_APPLICABLE not in runner.AGGREGATE_TYPED_STATUSES
    assert recovery.STARTUP_COMPENSATION_LANE_UNSUPPORTED not in (
        runner.AGGREGATE_TYPED_STATUSES
    )
    assert "APPLIED_INACTIVE" not in own
    assert "SOURCE_SIMULATION_PASS" not in own
    assert own == set(sorted(own))
