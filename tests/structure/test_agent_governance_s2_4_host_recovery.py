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

import ast
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

    tree = ast.parse(
        (HELPERS / "agent_governance_s2_4_host_recovery.py").read_text(encoding="utf-8")
    )
    wrapping_functions: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for inner in ast.walk(node):
            func = getattr(inner, "func", None)
            if not isinstance(inner, ast.Call) or not isinstance(func, ast.Attribute):
                continue
            if func.attr != "JournalRoutedDriver":
                continue
            wrapping_functions.append(node.name)
            # 直接判準:被包的那個東西不得是 ``…​.row_driver(...)`` 的回傳物。
            wrapped = inner.args[0] if inner.args else None
            assert not (
                isinstance(wrapped, ast.Call)
                and isinstance(wrapped.func, ast.Attribute)
                and wrapped.func.attr == "row_driver"
            ), node.name
    # 反例保護:名字改了(或包裹點消失了)就不是這個檢查了。
    assert wrapping_functions == ["_gate_under_lock"], wrapping_functions
    # 範圍判準:唯一的包裹點所在函式裡完全不出現 ``row_driver``。
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in wrapping_functions:
            assert "row_driver" not in ast.unparse(node), node.name
    assert any(
        isinstance(node, ast.Attribute) and node.attr == "row_driver"
        for node in ast.walk(tree)
    ), "the compensator is still expected to call row_driver() as an independent verifier"


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


# --------------------------------------------------------------------------- #
# C4 §C:新 probe / PREPARE intent 之前的 journal-routed 收斂閘
# --------------------------------------------------------------------------- #
_PROBE_ID = journal.PROBE_ID_PREFIX + "a" * 64
_PREPARE_ID = journal.PREPARE_ID_PREFIX + "a" * 64


def _outcome(status, admits, *, lanes=None):
    return {"status": status, "admits_new_work": admits, "lanes": lanes or {}, "reasons": []}


@pytest.mark.parametrize("status,admits,expected", [
    (reconcile_leaf.RECONCILE_STATUS_CLEAN, True, recovery.INTENT_GATE_ADMITTED),
    (reconcile_leaf.RECONCILE_STATUS_NOT_APPLIED, True, recovery.INTENT_GATE_ADMITTED),
    (reconcile_leaf.RECONCILE_STATUS_RESUME, False, recovery.INTENT_GATE_RECOVERY_REQUIRED),
    (reconcile_leaf.RECONCILE_STATUS_RECOVERY_REQUIRED, False,
     recovery.INTENT_GATE_RECOVERY_REQUIRED),
    (reconcile_leaf.RECONCILE_STATUS_CORRUPT, False, recovery.INTENT_GATE_JOURNAL_CORRUPT),
    (reconcile_leaf.RECONCILE_STATUS_LOCK_REQUIRED, False, recovery.INTENT_GATE_LOCK_HELD),
    (reconcile_leaf.RECONCILE_STATUS_PENDING, False, recovery.INTENT_GATE_PENDING),
    (reconcile_leaf.RECONCILE_STATUS_SURFACE_ABSENT, None,
     recovery.INTENT_GATE_SURFACE_ABSENT),
])
@pytest.mark.parametrize("lane", list(recovery.INTENT_GATE_LANES))
def test_the_dispatch_matrix_covers_every_convergence(status, admits, expected, lane):
    decision = recovery.dispatch_startup_reconcile(_outcome(status, admits), lane=lane)
    assert decision["status"] == expected
    assert decision["status"] in recovery.INTENT_GATE_TYPED_STATUSES


@pytest.mark.parametrize("lane", list(recovery.INTENT_GATE_LANES))
def test_a_compensating_install_lane_routes_to_the_reverse_chain_not_to_this_gate(lane):
    decision = recovery.dispatch_startup_reconcile(
        _outcome(
            reconcile_leaf.RECONCILE_STATUS_COMPENSATE, False,
            lanes={"install": {"status": reconcile_leaf.RECONCILE_STATUS_COMPENSATE}},
        ),
        lane=lane,
    )
    assert decision["status"] == recovery.INTENT_GATE_INSTALL_COMPENSATION_REQUIRED
    assert any("compensate_s2_4_startup_residue" in r for r in decision["reasons"])


@pytest.mark.parametrize("lane", list(recovery.INTENT_GATE_LANES))
def test_a_compensating_probe_or_prepare_lane_is_typed_unsupported_at_the_gate(lane):
    decision = recovery.dispatch_startup_reconcile(
        _outcome(
            reconcile_leaf.RECONCILE_STATUS_COMPENSATE, False,
            lanes={"probe:" + _PROBE_ID: {
                "status": reconcile_leaf.RECONCILE_STATUS_COMPENSATE
            }},
        ),
        lane=lane,
    )
    assert decision["status"] == recovery.INTENT_GATE_LANE_UNSUPPORTED


def test_the_gate_branches_on_admits_new_work_not_on_the_status_string():
    """status 字串是給人讀的;``admits_new_work`` 才是那份 verdict 的裁決。先看字串等於在
    收斂端重新實作一次收斂判準,而兩份判準分岔的方向是放行。"""

    # 「壞名字 + admits=True」必須放行 —— 否則分流讀的是字串。
    assert recovery.dispatch_startup_reconcile(
        _outcome(reconcile_leaf.RECONCILE_STATUS_RECOVERY_REQUIRED, True), lane="probe"
    )["status"] == recovery.INTENT_GATE_ADMITTED
    # 「好名字 + admits=None」必須是 SURFACE_ABSENT —— None 既不是 False 也不是 True。
    assert recovery.dispatch_startup_reconcile(
        _outcome(reconcile_leaf.RECONCILE_STATUS_CLEAN, None), lane="probe"
    )["status"] == recovery.INTENT_GATE_SURFACE_ABSENT
    # 「好名字 + admits=False」必須擋下。
    assert recovery.dispatch_startup_reconcile(
        _outcome(reconcile_leaf.RECONCILE_STATUS_CLEAN, False), lane="probe"
    )["status"] == recovery.INTENT_GATE_RECOVERY_REQUIRED


def test_the_resume_verification_gap_is_recorded_as_an_obligation_not_invented_away():
    decision = recovery.dispatch_startup_reconcile(
        _outcome(reconcile_leaf.RECONCILE_STATUS_RESUME, False), lane="prepare"
    )
    assert decision["obligations"] == [recovery.RESUME_VERIFICATION_OBLIGATION]
    assert any("verify-only entry point" in reason for reason in decision["reasons"])


@pytest.mark.parametrize("lane,lane_id", [("probe", _PROBE_ID), ("prepare", _PREPARE_ID)])
def test_a_clean_lane_admits_the_intent_under_the_lock(fx, lane, lane_id):
    seen = {}

    def _run(wrapped):
        seen["wrapped_driver"] = wrapped.wrapped_driver
        bound = wrapped.startup_reconcile_surface()
        # intent 在**同一把已取得的 lock 之下**執行(閘與 intent 分成兩次 lock 會留 TOCTOU 窗)。
        seen["held"] = lock.install_lock_is_held(bound["lock_verdict"])
        seen["file_driver"] = bound["file_driver"]
        return {"ran": True}

    sentinel = object()
    verdict = recovery.reconcile_before_s2_4_intent(
        fx.driver, lane=lane, lane_id=lane_id, intent_driver=sentinel,
        build_journal=lambda entries, terminal: None, run_intent=_run,
        clock=kit.frozen_clock(),
    )
    assert verdict["status"] == recovery.INTENT_GATE_ADMITTED, verdict["reasons"]
    assert verdict["admits_new_work"] is True
    assert verdict["intent_executed"] is True
    assert verdict["intent_result"] == {"ran": True}
    assert seen["wrapped_driver"] is sentinel
    assert seen["held"] is True
    assert seen["file_driver"] is fx.fs
    # 離開之後 lock 已釋放(下一次取得成功即證明)。
    assert lock.acquire_s2_4_install_lock(fx.lock_fake)["status"] == (
        lock.LOCK_STATUS_ACQUIRED
    )


def test_a_dry_run_gate_runs_no_intent_and_mutates_nothing(fx):
    verdict = recovery.reconcile_before_s2_4_intent(
        fx.driver, lane="probe", lane_id=_PROBE_ID, clock=kit.frozen_clock()
    )
    assert verdict["status"] == recovery.INTENT_GATE_ADMITTED
    assert verdict["intent_executed"] is False
    assert verdict["mutation_performed"] is False
    assert any("dry-run gate" in reason for reason in verdict["reasons"])


def test_a_previous_plans_stranded_transaction_blocks_a_new_probe_intent(fx):
    """§5.2 的「**任何**非終端 journal」:上一份 plan 半途崩掉留下的那本也擋新 intent。"""

    _crash(fx, "PG_ROLE_ACL_MIGRATION:post_effect_pre_observation")
    verdict = recovery.reconcile_before_s2_4_intent(
        fx.driver, lane="probe", lane_id=_PROBE_ID,
        run_intent=lambda wrapped: pytest.fail("the intent must not run"),
        clock=kit.frozen_clock(),
    )
    assert verdict["status"] == recovery.INTENT_GATE_RECOVERY_REQUIRED
    assert verdict["admits_new_work"] is False
    assert verdict["intent_executed"] is False


def test_the_gate_takes_the_lock_before_it_asks_for_a_file_surface(fx):
    """§5.2 的閘序是 lock-first:倒過來會讓「無 lock ∧ 無 driver」回報
    EXTERNAL_VERIFICATION_PENDING,那句話讀起來像「只差一個主機面就成」。"""

    from test_agent_governance_s2_4_lock import FakeLockDriver

    fx.driver._lock = FakeLockDriver(flock_succeeds=False)
    verdict = recovery.reconcile_before_s2_4_intent(
        fx.driver, lane="probe", lane_id=_PROBE_ID,
        run_intent=lambda wrapped: pytest.fail("the intent must not run"),
        clock=kit.frozen_clock(),
    )
    assert verdict["status"] == recovery.INTENT_GATE_LOCK_HELD
    assert verdict["reconcile"] is None
    assert verdict["intent_executed"] is False


def test_no_driver_is_authority_locked_at_the_gate_too(fx):
    verdict = recovery.reconcile_before_s2_4_intent(
        None, lane="probe", lane_id=_PROBE_ID
    )
    assert verdict["status"] == recovery.INTENT_GATE_PENDING
    assert verdict["driver_engaged"] is False
    assert verdict["lane_path"] == journal.probe_journal_path(_PROBE_ID)


@pytest.mark.parametrize("bad", ["", "../etc/passwd", "s2-4-probe-zz", None, 7])
def test_a_caller_string_is_never_joined_into_the_state_root(fx, bad):
    verdict = recovery.reconcile_before_s2_4_intent(
        fx.driver, lane="probe", lane_id=bad, clock=kit.frozen_clock()
    )
    assert verdict["status"] == recovery.INTENT_GATE_RECOVERY_REQUIRED
    assert verdict["lane_path"] is None
    assert verdict["driver_engaged"] is False


def test_the_apply_lane_is_not_gated_here(fx):
    verdict = recovery.reconcile_before_s2_4_intent(
        fx.driver, lane="install", lane_id="s2-4-" + "a" * 64, clock=kit.frozen_clock()
    )
    assert verdict["status"] == recovery.INTENT_GATE_RECOVERY_REQUIRED
    assert any("apply_s2_4_install_plan" in reason for reason in verdict["reasons"])
    assert verdict["driver_engaged"] is False


def test_an_intent_without_a_journal_builder_can_never_write_a_wal(fx):
    """沒有 journal builder 就不可能有 durable WAL —— typed raise,絕不落一本空 journal。"""

    def _run(wrapped):
        wrapped.journal_transition(entry={
            "state": "APPLYING", "pre_state_digest": "sha256:" + "1" * 64,
            "post_state_digest": "sha256:" + "2" * 64,
            "component_effect_class": "CAPABILITY_PROBE",
        })

    verdict = recovery.reconcile_before_s2_4_intent(
        fx.driver, lane="probe", lane_id=_PROBE_ID, run_intent=_run,
        clock=kit.frozen_clock(),
    )
    assert verdict["status"] == recovery.INTENT_GATE_RECOVERY_REQUIRED
    assert verdict["intent_executed"] is True
    assert any("raised under the install lock" in r for r in verdict["reasons"])


def test_an_unclean_release_downgrades_the_gate_without_borrowing_a_receipt_status(
    fx, monkeypatch
):
    original = lock.release_s2_4_install_lock

    def _dirty(driver, lock_verdict):
        original(driver, lock_verdict)
        return {
            "status": lock.LOCK_STATUS_RECOVERY_REQUIRED,
            "reasons": ["install-lock release failed: injected"], "lock_unlinked": False,
        }

    monkeypatch.setattr(lock, "release_s2_4_install_lock", _dirty)
    verdict = recovery.reconcile_before_s2_4_intent(
        fx.driver, lane="probe", lane_id=_PROBE_ID, clock=kit.frozen_clock()
    )
    assert verdict["status"] == recovery.INTENT_GATE_RECOVERY_REQUIRED
    assert verdict["schema_version"] == recovery.INTENT_GATE_SCHEMA_VERSION
    assert verdict["lock_release"]["status"] == lock.LOCK_STATUS_RECOVERY_REQUIRED
    assert any("not cleanly released" in reason for reason in verdict["reasons"])
    assert verdict["status"] not in runner.AGGREGATE_TYPED_STATUSES or (
        verdict["status"] == "RECOVERY_REQUIRED"
    )


# --------------------------------------------------------------------------- #
# C5 §F-0.2:「補完就重跑」是一道自己打不開的門
# --------------------------------------------------------------------------- #
def test_the_aggregate_compensate_verdict_never_promises_a_re_run(fx):
    """`install_driver` 的 COMPENSATE 分支過去說 runner「compensates **and re-runs**」。

    那句話與同一個函式下方的程式碼直接矛盾:permit 已 durable 消費、終端 ``COMPENSATED``
    被明文拒絕當作完成證據,所以同一份 plan 結構上永遠不能重跑。照著它建的 runner 會撞上
    一道自己打不開的門,故 verdict 的 reason(那是**程式碼**,不是註解)必須自己說清楚。
    """

    persisted = _crash(fx, "PG_ROLE_ACL_MIGRATION:post_effect_pre_observation")
    verdict = fx.apply(
        startup_task_owned_partials={"install": True},
        startup_observed_state_digests={"install": _PARTIAL_STATE},
        ownership_evidence=_ownership(persisted),
    )
    assert verdict["status"] == runner.AGGREGATE_STATUS_RECOVERY_REQUIRED
    assert verdict["reconcile"]["status"] == reconcile_leaf.RECONCILE_STATUS_COMPENSATE
    joined = " ".join(verdict["reasons"])
    assert "compensates and re-runs" not in joined
    assert "does NOT make this plan runnable again" in joined
    assert "compensate_s2_4_startup_residue" in joined
    assert "mint a NEW signed plan with fresh permits" in joined


@pytest.mark.parametrize("terminal_state", ["COMPENSATED", "FAILED"])
def test_a_terminal_non_verified_journal_is_never_readable_as_completed(fx, terminal_state):
    """`_load_terminal_journal` 的判準:只有終端 ``VERIFIED`` 證明第一次執行真的完成。

    ``COMPENSATED`` 的意思是本次 task-owned delta 已被逆序移除(安裝**沒有**發生),
    ``FAILED`` 的意思是補償無法被證明為 exact(§5.4 記下確切殘留)——把任一個讀成
    ``ALREADY_APPLIED_IDEMPOTENT`` 會對 on-call 謊報一次不存在的安裝。
    """

    persisted = _crash(fx, "PG_ROLE_ACL_MIGRATION:post_effect_pre_observation")
    entries = [dict(entry) for entry in persisted["entries"]]
    entries.append({
        "seq": len(entries), "state": terminal_state, "step_index": 0,
        "pre_state_digest": fx.plan["core"]["pre_state_digest"],
        "post_state_digest": fx.plan["core"]["pre_state_digest"],
        "fsynced": True, "recorded_at": kit.ISSUED,
        "entry_source": journal.ENTRY_SOURCE_AGGREGATE,
        "component_effect_class": journal.ENTRY_SCOPE_AGGREGATE_TRANSACTION,
    })
    closed = journal.build_install_journal(
        plan_id=fx.plan["plan_id"], plan_core_digest=fx.plan["core_digest"],
        idempotency_key=fx.plan["plan_id"],
        expected_pre_state_digest=persisted["expected_pre_state_digest"],
        aggregate_rollback_digest=persisted["aggregate_rollback_digest"],
        entries=entries, terminal=True,
    )
    basename = journal.install_journal_path(fx.plan["plan_id"]).rsplit("/", 1)[-1]
    fx.fs.files[basename] = validator._canonical_bytes(closed)
    loaded = runner._load_terminal_journal(fx.fs, fx.plan["plan_id"])
    assert loaded["status"] == runner.APPLY_JOURNAL_UNPROVEN
    assert loaded["terminal_state"] == terminal_state
    assert any("not 'VERIFIED'" in reason for reason in loaded["reasons"])


# --------------------------------------------------------------------------- #
# C7:CLI 的 s2_4 session(artifact 的 exit_code 與 process 真實退出碼恆一致)
# --------------------------------------------------------------------------- #
import aiml_s2_effect_host_run as cli  # noqa: E402


_HEAD = "0" * 40


def _run_cli(tmp_path, name, *extra):
    out = tmp_path / name
    code = cli.main(["--out-dir", str(out), "--source-head", _HEAD, *extra])
    summary = json.loads((out / "run_summary.json").read_text(encoding="utf-8"))
    # ★驗收判準★ 落盤 artifact 的 exit_code 與 process 真實退出碼恆一致。
    assert summary["exit_code"] == code, (name, summary)
    return code, summary, out


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return path


def test_the_cli_reconcile_mode_is_authority_locked_and_writes_its_verdict(tmp_path):
    code, summary, out = _run_cli(
        tmp_path, "ok", "--session", "s2_4", "--mode", "reconcile",
        "--lane", "probe", "--lane-id", _PROBE_ID,
    )
    assert code == cli.EXIT_HOST_CAPABILITY_ABSENT
    assert summary["status"] == recovery.INTENT_GATE_PENDING
    assert summary["mutation_performed"] is False
    verdict = json.loads((out / "s2_4_startup_verdict.json").read_text(encoding="utf-8"))
    assert verdict["schema_version"] == recovery.INTENT_GATE_SCHEMA_VERSION
    assert verdict["lane_path"] == journal.probe_journal_path(_PROBE_ID)


def test_the_cli_reconcile_mode_refuses_a_caller_path_segment(tmp_path):
    code, summary, _out = _run_cli(
        tmp_path, "bad-lane", "--session", "s2_4", "--mode", "reconcile",
        "--lane", "prepare", "--lane-id", "../../etc/passwd",
    )
    assert code == cli.EXIT_RECOVERY_REQUIRED
    assert summary["status"] == recovery.INTENT_GATE_RECOVERY_REQUIRED


def test_the_cli_compensate_mode_is_authority_locked_on_a_real_plan(fx, tmp_path):
    code, summary, out = _run_cli(
        tmp_path, "compensate", "--session", "s2_4", "--mode", "compensate",
        "--plan-file", str(_write(tmp_path / "plan.json", fx.plan)),
        "--component-intents-file",
        str(_write(tmp_path / "intents.json", fx.component_intents)),
        "--apply-aggregate-permit",
        str(_write(tmp_path / "agg.json", fx.authorization_set["apply_aggregate"])),
        "--pg-migration-permit",
        str(_write(tmp_path / "pg.json", fx.authorization_set["pg_migration"])),
    )
    assert code == cli.EXIT_HOST_CAPABILITY_ABSENT
    assert summary["status"] == recovery.STARTUP_COMPENSATION_PENDING
    assert summary["driver_engaged"] is False
    verdict = json.loads((out / "s2_4_startup_verdict.json").read_text(encoding="utf-8"))
    assert verdict["schema_version"] == recovery.STARTUP_COMPENSATION_SCHEMA_VERSION
    assert verdict["emits_effect_receipt"] is False


def test_the_cli_compensate_mode_refuses_a_plan_that_is_not_an_install_plan(tmp_path):
    code, summary, _out = _run_cli(
        tmp_path, "bad-plan", "--session", "s2_4", "--mode", "compensate",
        "--plan-file", str(_write(tmp_path / "plan.json", {"schema_version": "nope"})),
        "--component-intents-file", str(_write(tmp_path / "intents.json", {})),
        "--apply-aggregate-permit", str(_write(tmp_path / "agg.json", {})),
        "--pg-migration-permit", str(_write(tmp_path / "pg.json", {})),
    )
    assert code == cli.EXIT_RECOVERY_REQUIRED
    assert summary["status"] == recovery.STARTUP_COMPENSATION_RECOVERY_REQUIRED


def test_unreadable_cli_input_stays_typed_input_invalid(tmp_path):
    code, summary, _out = _run_cli(
        tmp_path, "unreadable", "--session", "s2_4", "--mode", "compensate",
        "--plan-file", str(tmp_path / "absent.json"),
        "--component-intents-file", str(_write(tmp_path / "intents.json", {})),
        "--apply-aggregate-permit", str(_write(tmp_path / "agg.json", {})),
        "--pg-migration-permit", str(_write(tmp_path / "pg.json", {})),
    )
    assert code == cli.EXIT_INPUT_INVALID
    assert summary["status"] == "INPUT_INVALID"


@pytest.mark.parametrize("session,mode", [
    ("s2_0", "reconcile"), ("s2_0", "compensate"),
    ("s2_1", "reconcile"), ("s2_1", "compensate"),
    ("s2_4", "probe"), ("s2_4", "admit"), ("s2_4", "apply"),
])
def test_each_session_only_accepts_its_own_modes(fx, tmp_path, session, mode):
    """每一組都餵**該 mode 完整合法的**輸入,於是唯一能擋下它的就是 session↔mode 那道閘。

    (只餵 ``--session``/``--mode`` 會讓「缺 --lane」這種別的閘先擋下來,測試就會因為錯的理由
    而綠。)
    """

    complete = {
        "probe": [],
        "admit": ["--intent-file", str(_write(tmp_path / "intent.json", {}))],
        "apply": ["--intent-file", str(_write(tmp_path / "intent.json", {}))],
        "reconcile": ["--lane", "probe", "--lane-id", _PROBE_ID],
        "compensate": [
            "--plan-file", str(_write(tmp_path / "plan.json", fx.plan)),
            "--component-intents-file",
            str(_write(tmp_path / "intents.json", fx.component_intents)),
            "--apply-aggregate-permit",
            str(_write(tmp_path / "agg.json", fx.authorization_set["apply_aggregate"])),
            "--pg-migration-permit",
            str(_write(tmp_path / "pg.json", fx.authorization_set["pg_migration"])),
        ],
    }[mode]
    with pytest.raises(SystemExit) as caught:
        cli.main([
            "--out-dir", str(tmp_path / "x"), "--source-head", _HEAD,
            "--session", session, "--mode", mode, *complete,
        ])
    assert caught.value.code == cli.EXIT_USAGE


@pytest.mark.parametrize("extra", [
    ("--session", "s2_4", "--mode", "reconcile"),
    ("--session", "s2_4", "--mode", "reconcile", "--lane", "probe"),
    ("--session", "s2_4", "--mode", "compensate"),
])
def test_the_s2_4_modes_require_their_whole_input_set(tmp_path, extra):
    with pytest.raises(SystemExit) as caught:
        cli.main(["--out-dir", str(tmp_path / "y"), "--source-head", _HEAD, *extra])
    assert caught.value.code == cli.EXIT_USAGE


def test_no_typed_non_success_status_can_map_to_a_zero_exit_code():
    """表外一律 EXIT_RECOVERY_REQUIRED:一個沒被列舉的新終端絕不能靜默變成 0。"""

    successes = {
        recovery.STARTUP_COMPENSATION_COMPLETED_EXACT,
        recovery.STARTUP_COMPENSATION_NOT_APPLICABLE,
        recovery.INTENT_GATE_ADMITTED,
    }
    every = set(recovery.STARTUP_COMPENSATION_TYPED_STATUSES) | set(
        recovery.INTENT_GATE_TYPED_STATUSES
    )
    for status in every:
        code = cli.S2_4_STATUS_EXIT_CODES.get(status, cli.EXIT_RECOVERY_REQUIRED)
        assert (code == cli.EXIT_OK) is (status in successes), status
    # 未來新增的終端(表外)預設落在 8,不是 0。
    assert cli.S2_4_STATUS_EXIT_CODES.get(
        "A_STATUS_NOBODY_ENUMERATED_YET", cli.EXIT_RECOVERY_REQUIRED
    ) == cli.EXIT_RECOVERY_REQUIRED
    assert cli.EXIT_RECOVERY_REQUIRED not in {
        cli.EXIT_OK, cli.EXIT_USAGE, cli.EXIT_ADMISSION_REFUSED,
        cli.EXIT_HOST_CAPABILITY_ABSENT, cli.EXIT_OBSERVATION_FAILED,
        cli.EXIT_INPUT_INVALID, cli.EXIT_INTERNAL_ERROR,
    }
