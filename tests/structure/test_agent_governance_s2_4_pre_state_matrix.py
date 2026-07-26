"""S2.4(WP4·W4b)§5.3 pre-existing-state 決策矩陣的**逐列**測試(§10.5 #19)。

§5.3 有七列;本檔逐列一支測試,並在可能處同時取兩層證據:分類謂詞本身,以及一條**真的**
row/aggregate 路徑(證明該分類確實在第一次變更之前決定行為)。

===========================================================  ================================
§5.3 列                                                       test
===========================================================  ================================
absent → 建立並標記 exact delta 為 task-owned                 ``test_row1_absent_creates_and_marks_the_task_owned_delta``
exact desired + 相符的 S2.4 receipt/journal → NOOP_VERIFIED    ``test_row2_exact_desired_with_ownership_is_a_zero_mutation_noop``
exact desired bytes 但無擁有權 → PREEXISTING_UNOWNED_STATE     ``test_row3_exact_desired_without_ownership_is_never_adopted``
不同的既有 bytes/state → PRESTATE_MISMATCH                     ``test_row4_different_pre_existing_state_is_never_overwritten``
task-owned 部分態 + 合法 journal → 確定性 reconcile             ``test_row5_task_owned_partial_with_a_valid_journal_reconciles``
無合法 task-owned journal 的部分態 → RECOVERY_REQUIRED          ``test_row6_partial_without_a_valid_journal_is_recovery_required``
credential slot 已存在且無擁有權 → 不讀/不備份/不收養/不輪替     ``test_row7_unowned_credential_slot_is_never_adopted_or_rotated``
===========================================================  ================================

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
import agent_governance_s2_4_component as component  # noqa: E402
import agent_governance_s2_4_credential as credential  # noqa: E402
import agent_governance_s2_4_install_driver as runner  # noqa: E402
import agent_governance_s2_4_journal as journal  # noqa: E402
import agent_governance_s2_4_lock as lock  # noqa: E402
import agent_governance_s2_4_reconcile as reconcile_leaf  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
import s2_4_w3b_testkit as kit  # noqa: E402
import s2_4_w4b_testkit as w4b  # noqa: E402
from test_agent_governance_s2_4_apply import _FakeCredentialDriver, _credential_intent  # noqa: E402

_DESIRED = {"path": "/opt/example", "owner": "root", "mode": "0555"}
_OWNED = {
    "s2_4_receipt_digest": "sha256:" + "a" * 64,
    "journal_digest": "sha256:" + "b" * 64,
}


@pytest.fixture()
def fx(tmp_path, monkeypatch):
    return w4b.Fixture(tmp_path, monkeypatch)


@pytest.fixture()
def signed(tmp_path, monkeypatch):
    return kit.signed_authorizations(tmp_path, monkeypatch)


# ══════════════════ 列 1:absent → 建立並標記 task-owned delta ══════════════════
def test_row1_absent_creates_and_marks_the_task_owned_delta(fx) -> None:
    assert component.classify_pre_state(
        observed=None, desired=_DESIRED, ownership_evidence=None
    ) == {"state": "ABSENT", "reasons": []}
    assert component.classify_ownership_only(
        observed_subject=None, ownership_evidence=None
    ) == {"state": "ABSENT", "reasons": []}
    # 真路徑:五 row 全為 absent → 全部建立,且每一步都記下 task-owned delta digest。
    verdict = fx.apply()
    assert verdict["status"] == "SOURCE_SIMULATION_PASS", verdict["reasons"]
    for step in verdict["step_results"]:
        assert step["task_owned_delta_digest"] == validator.canonical_digest({
            "component_effect_class": step["component_effect_class"],
            "mutation_performed": True,
        })
        assert step["compensation_intent_digest"] == runner.per_row_rollback_digest(
            plan_id=fx.plan["plan_id"],
            component_effect_class=step["component_effect_class"],
        )
    assert all(row["mutation_performed"] is True for row in verdict["row_verdicts"].values())


# ══════════════════ 列 2:exact desired + 擁有權 → NOOP_VERIFIED ════════════════
def test_row2_exact_desired_with_ownership_is_a_zero_mutation_noop(fx) -> None:
    assert component.classify_pre_state(
        observed=dict(_DESIRED), desired=_DESIRED, ownership_evidence=dict(_OWNED)
    ) == {"state": "NOOP_VERIFIED", "reasons": []}
    # 真路徑:LEARNING_RUNTIME 的三棵樹逐位元組等於 desired 且帶 S2.4 擁有權 → 零發佈。
    targets = fx.targets
    existing = {
        target: {"digest": fx.prepared_bundle[field]} for field, target in targets.items()
    }
    fx.row_drivers["LEARNING_RUNTIME"].existing = existing
    ownership = {
        "LEARNING_RUNTIME": {target: dict(_OWNED) for target in targets.values()},
    }
    verdict = fx.apply(ownership_evidence=ownership)
    assert verdict["status"] == "SOURCE_SIMULATION_PASS", verdict["reasons"]
    runtime = verdict["row_verdicts"]["LEARNING_RUNTIME"]
    assert runtime["status"] == "NOOP_VERIFIED"
    assert runtime["mutation_performed"] is False
    assert not any(
        call.startswith("publish_tree")
        for call in fx.row_drivers["LEARNING_RUNTIME"].calls
    )
    # NOOP 的 row 仍然是「admitted」,故 aggregate 照樣走到成功身分。
    assert verdict["receipt"] is not None


# ══════════════════ 列 3:exact desired 但無擁有權 → 不收養 ═════════════════════
def test_row3_exact_desired_without_ownership_is_never_adopted(fx) -> None:
    state = component.classify_pre_state(
        observed=dict(_DESIRED), desired=_DESIRED, ownership_evidence=None
    )
    assert state["state"] == "PREEXISTING_UNOWNED_STATE"
    assert any("no adoption is performed" in reason for reason in state["reasons"])
    # 裸的擁有權物件永遠不成立(空 dict 不得把拒絕換成放行)。
    for bogus in ({}, {"s2_4_receipt_digest": "not-a-digest"}, "owned", 1):
        assert component.classify_pre_state(
            observed=dict(_DESIRED), desired=_DESIRED, ownership_evidence=bogus
        )["state"] == "PREEXISTING_UNOWNED_STATE"
    # 真路徑:既有的三棵樹逐位元組相符但**沒有**擁有權證據 → 零發佈、零覆寫。
    fx.row_drivers["LEARNING_RUNTIME"].existing = {
        target: {"digest": fx.prepared_bundle[field]}
        for field, target in fx.targets.items()
    }
    verdict = fx.apply()
    assert verdict["status"] == "PREEXISTING_UNOWNED_STATE"
    assert verdict["receipt"] is None
    assert not any(
        call.startswith("publish_tree")
        for call in fx.row_drivers["LEARNING_RUNTIME"].calls
    )
    # 前三 row 已施作 → 依 §5.4 逆序補償;被拒的 LEARNING_RUNTIME 與從未跑到的
    # ENGINE_SCANNER 都沒有 delta,故絕不被「補償」。
    assert fx.driver.compensated == [
        "CREDENTIAL_INSTALL", "PG_ROLE_ACL_MIGRATION", "HOST_IDENTITY_INSTALL",
    ]


# ══════════════════ 列 4:不同的既有 state → 不覆寫 ═════════════════════════════
def test_row4_different_pre_existing_state_is_never_overwritten(fx) -> None:
    drifted = {**_DESIRED, "mode": "0755"}
    state = component.classify_pre_state(
        observed=drifted, desired=_DESIRED, ownership_evidence=dict(_OWNED)
    )
    assert state["state"] == "PRESTATE_MISMATCH"
    assert any("no overwrite is performed" in reason for reason in state["reasons"])
    assert any("drifted attributes: ['mode']" in reason for reason in state["reasons"])
    # 真路徑:既有的 candidate policy 檔案漂移 → ENGINE_SCANNER row 在變更之前停手。
    fx.row_drivers["ENGINE_SCANNER"].existing_policy = {
        "path": apply_mod.CANDIDATE_POLICY_PATH, "owner": "root",
        "group": "aiml-engine-scanner", "mode": "0644",
        "digest": "sha256:" + "e" * 64,
    }
    verdict = fx.apply(
        ownership_evidence={"ENGINE_SCANNER": {"policy": dict(_OWNED)}}
    )
    assert verdict["status"] == "PRESTATE_MISMATCH"
    assert verdict["receipt"] is None
    engine = fx.row_drivers["ENGINE_SCANNER"]
    assert "install_policy_file" not in engine.calls
    assert "install_unit_fragment" not in engine.calls
    assert engine.reloads == 0


# ══════════════════ 列 5:task-owned 部分態 + 合法 journal → 確定性 reconcile ════
def test_row5_task_owned_partial_with_a_valid_journal_reconciles() -> None:
    built = journal.build_install_journal(
        plan_id=journal.PLAN_ID_PREFIX + "a" * 64, plan_core_digest="sha256:" + "1" * 64,
        idempotency_key=journal.PLAN_ID_PREFIX + "a" * 64,
        expected_pre_state_digest="sha256:" + "2" * 64,
        aggregate_rollback_digest="sha256:" + "3" * 64,
        entries=[{
            "seq": 0, "step_index": 0, "state": "APPLYING",
            "pre_state_digest": "sha256:" + "2" * 64,
            "post_state_digest": "sha256:" + "4" * 64,
            "fsynced": True, "recorded_at": kit.ISSUED,
        }],
        terminal=False,
    )
    # (a) 觀測 == 計畫 post-state → 續驗;(b) == pre-state → 該步未施作;
    # (c) task-owned 部分態 + 合法 journal 擁有權 → 逆序補償。
    assert journal.reconcile_journal(
        built, observed_state_digest="sha256:" + "4" * 64
    )["status"] == journal.RECONCILE_RESUME_VERIFICATION
    assert journal.reconcile_journal(
        built, observed_state_digest="sha256:" + "2" * 64
    )["status"] == journal.RECONCILE_STEP_NOT_APPLIED
    compensate = journal.reconcile_journal(
        built, observed_state_digest="sha256:" + "9" * 64, task_owned_partial=True,
        ownership_evidence={"journal_subject": dict(_OWNED)},
    )
    assert compensate["status"] == journal.RECONCILE_COMPENSATE_REVERSE
    assert compensate["mutation_performed"] is False
    # 啟動 reconcile 的 typed 投影一致(lane 級)。
    assert reconcile_leaf._RECONCILE_PROJECTION[journal.RECONCILE_COMPENSATE_REVERSE] == (
        "STARTUP_RECONCILE_COMPENSATE_REVERSE_ORDER"
    )
    assert "STARTUP_RECONCILE_COMPENSATE_REVERSE_ORDER" not in (
        reconcile_leaf.RECONCILE_ADMITS_NEW_WORK
    )


# ══════════════════ 列 6:無合法 journal 的部分態 → 零變更 recovery ═════════════
def test_row6_partial_without_a_valid_journal_is_recovery_required(fx) -> None:
    built = journal.build_install_journal(
        plan_id=fx.plan["plan_id"], plan_core_digest=fx.plan["core_digest"],
        idempotency_key=fx.plan["plan_id"],
        expected_pre_state_digest=fx.plan["core"]["pre_state_digest"],
        aggregate_rollback_digest=runner.aggregate_rollback_digest(
            plan_id=fx.plan["plan_id"]
        ),
        entries=[{
            "seq": 0, "step_index": 0, "state": "APPLYING",
            "pre_state_digest": "sha256:" + "2" * 64,
            "post_state_digest": "sha256:" + "4" * 64,
            "fsynced": True, "recorded_at": kit.ISSUED,
        }],
        terminal=False,
    )
    # (a) 宣告 task-owned 但沒有合法擁有權綁定 → RECOVERY_REQUIRED,零變更。
    for bogus in (None, {}, {"journal_subject": {}}, {"journal_subject": "owned"}):
        verdict = journal.reconcile_journal(
            built, observed_state_digest="sha256:" + "9" * 64, task_owned_partial=True,
            ownership_evidence=bogus,
        )
        assert verdict["status"] == journal.RECONCILE_RECOVERY_REQUIRED
        assert verdict["mutation_performed"] is False
    # (b) 真路徑:一份非終端 journal + 無法對上的獨立觀測 → aggregate 零變更 RECOVERY_REQUIRED。
    basename = journal.install_journal_path(fx.plan["plan_id"]).rsplit("/", 1)[-1]
    fx.fs.files[basename] = validator._canonical_bytes(built)
    result = fx.apply(startup_observed_state_digests={"install": "sha256:" + "9" * 64})
    assert result["status"] == "RECOVERY_REQUIRED"
    assert result["reconcile"]["lanes"]["install"]["status"] == "RECOVERY_REQUIRED"
    assert all(driver.calls == [] for driver in fx.row_drivers.values())
    assert fx.fs.files[basename] == validator._canonical_bytes(built)
    assert len(fx.persisted_replay_ledger()["entries"]) == 3  # 零 permit 消費


# ══════════════════ 列 7:既有 credential slot 無擁有權 → 不讀/不輪替 ═══════════
def test_row7_unowned_credential_slot_is_never_adopted_or_rotated(signed) -> None:
    """§5.3 最後一列:``no read, backup, adoption or rotation``。"""

    broker = credential.SecretBroker(operation_id="cred-op")
    _pg_handle, dsn_handle = broker.mint_first_provisioning_handles()
    existing = {
        "slot_path": credential.CREDENTIAL_SLOT_PATH,
        "encrypted_blob_digest": "sha256:" + "f" * 64,
        "owner": "root", "mode": "0600",
    }
    driver = _FakeCredentialDriver(slot=existing)
    verdict = apply_mod.apply_s2_4_credential_install(
        _credential_intent(), driver=driver, dsn_handle=dsn_handle,
        **kit.common_apply_kwargs(signed),
    )
    assert verdict["status"] == "PREEXISTING_UNOWNED_STATE"
    assert any(
        "no read, backup, adoption or rotation is performed" in reason
        for reason in verdict["reasons"]
    )
    # 只觀測過能力與 slot 的存在;絕沒有加密、安裝、還原或移除。
    assert driver.calls == ["host_credential_capability", "observe_credential_slot"]
    assert driver.restored is None and driver.removed is False
    assert driver.consumed_dsn is None
    assert verdict["mutation_performed"] is False


def test_row7b_rotation_of_an_unowned_slot_is_refused(signed) -> None:
    broker = credential.SecretBroker(operation_id="cred-op")
    _pg_handle, dsn_handle = broker.mint_first_provisioning_handles()
    driver = _FakeCredentialDriver(slot={
        "slot_path": credential.CREDENTIAL_SLOT_PATH,
        "encrypted_blob_digest": "sha256:" + "f" * 64,
        "owner": "root", "mode": "0600",
    })
    verdict = apply_mod.apply_s2_4_credential_install(
        _credential_intent(), driver=driver, dsn_handle=dsn_handle, mode="ROTATION",
        **kit.common_apply_kwargs(signed),
    )
    assert verdict["status"] == "PREEXISTING_UNOWNED_STATE"
    assert driver.restored is None and driver.removed is False
    assert "encrypt_credential" not in driver.calls
    # 自報 ``task_owned`` 但沒有 digest 綁定的證據,同樣換不到放行。
    self_declared = _FakeCredentialDriver(slot={
        "slot_path": credential.CREDENTIAL_SLOT_PATH,
        "encrypted_blob_digest": "sha256:" + "f" * 64,
        "owner": "root", "mode": "0600", "task_owned": True,
    })
    _pg2, dsn2 = credential.SecretBroker(
        operation_id="cred-op"
    ).mint_first_provisioning_handles()
    verdict = apply_mod.apply_s2_4_credential_install(
        _credential_intent(), driver=self_declared, dsn_handle=dsn2, mode="ROTATION",
        **kit.common_apply_kwargs(signed),
    )
    assert verdict["status"] == "PREEXISTING_UNOWNED_STATE"
    assert "encrypt_credential" not in self_declared.calls


def test_row7c_an_unowned_credential_slot_stops_the_whole_transaction(fx) -> None:
    """aggregate 層:第三 row 的既有 slot 無擁有權 → 前兩 row 逆序補償,無 receipt。"""

    fx.row_drivers["CREDENTIAL_INSTALL"].slot = {
        "slot_path": credential.CREDENTIAL_SLOT_PATH,
        "encrypted_blob_digest": "sha256:" + "f" * 64,
        "owner": "root", "mode": "0600",
    }
    verdict = fx.apply()
    assert verdict["status"] == "PREEXISTING_UNOWNED_STATE"
    assert verdict["receipt"] is None
    assert fx.driver.compensated == ["PG_ROLE_ACL_MIGRATION", "HOST_IDENTITY_INSTALL"]
    assert "encrypt_credential" not in fx.row_drivers["CREDENTIAL_INSTALL"].calls
    assert fx.row_drivers["ENGINE_SCANNER"].calls == []
    assert verdict["rollback"]["observer_role_preserved"] is True
    assert verdict["rollback"]["no_secret_reconstructed"] is True


# ══════════════════ 矩陣完整性 ═════════════════════════════════════════════════
def test_the_matrix_covers_all_seven_rows_of_the_decision_table() -> None:
    module = sys.modules[__name__]
    names = {name for name in dir(module) if name.startswith("test_row")}
    assert {name.split("_")[1] for name in names} == {
        "row1", "row2", "row3", "row4", "row5", "row6", "row7", "row7b", "row7c",
    }
    # §5.3 的三個 typed 結果都在 component / aggregate 的封閉狀態集中。
    for status in ("PREEXISTING_UNOWNED_STATE", "PRESTATE_MISMATCH", "NOOP_VERIFIED"):
        assert status in component.COMPONENT_TYPED_STATUSES
    for status in ("PREEXISTING_UNOWNED_STATE", "PRESTATE_MISMATCH", "RECOVERY_REQUIRED"):
        assert status in runner.AGGREGATE_TYPED_STATUSES
    assert lock.LOCK_STATUS_ACQUIRED == "INSTALL_LOCK_ACQUIRED"
