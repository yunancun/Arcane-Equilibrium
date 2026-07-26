"""S2.4(WP4·W4b)aggregate APPLY 交易的 focused 測試(§5.1/§5.2/§6/§10.2/§10.5 #8/#24)。

證明:

- **source lane 零 effect**:``driver=None`` typed ``EXTERNAL_VERIFICATION_PENDING``、零變更、
  零 driver 接觸;而 ``APPLIED_INACTIVE`` 在源碼/丟棄式線**構造上不可達**(自報 attested
  evidence class 一律被拒 → ``SOURCE_SIMULATION_PASS``,九 authority 全 false);
- **§10.5 #24**:兩個 scoped terminal probe receipt + PREPARE 結果 + 五個**相異** APPLY row
  結果缺一不可;同一份 probe 充當兩個 scope、非終端 probe/PREPARE、被換掉的 component intent
  一律在任何主機接觸之前 typed 拒;
- **AGGREGATE_PLAN_PAYLOAD_FULL_COMPARISON**(W4a 記錄的 gap):aggregate 與 PG permit 的
  **每一個** §9.1 payload 欄位都逐欄對已驗 plan 比對(coverage 投影證明零未比對欄位),任一欄
  被換即 ``AUTHORIZATION_REJECTED``;
- **§5.1 無 digest 環**:plan core 釘住 component intent 的每一欄(除兩個自指欄位),intent 指向
  plan 的 core digest;兩側任一被換即拒;
- **§5.2**:install lock 為唯一 writer(競爭 = ``INSTALL_LOCK_HELD`` 零變更)、啟動 reconcile
  在接受新 plan 之前收斂、兩張 permit 在**同一把** lock 下 consume-once 且 hash-chained 落盤、
  同 key 的 replay 不重跑任何 effect;
- **§5.4**:失敗即逆序補償(unit → launch/app/base runtime → credential → auth/PG → host),
  且 exactness 只由**獨立** verifier 的補償後再觀測導出;
- **RUNNER_WAL_LOCK_WIRING**:``JournalRoutedDriver`` 把既有 driver 的 ``journal_transition``
  路由進 durable ``JournalStore`` 且要求已取得的 lock,不改該 driver 對主機做什麼。

時間全部錨在 :mod:`s2_4_w3b_testkit` 的凍結常量上(無 wall clock,故無日期腐化)。
"""
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
PROGRAM_CODE = ROOT / "program_code"
for candidate in (HELPERS, ML_ROOT, PROGRAM_CODE, ROOT / "tests/structure"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_4_install_driver as runner  # noqa: E402
import agent_governance_s2_4_journal as journal  # noqa: E402
import agent_governance_s2_4_lock as lock  # noqa: E402
import agent_governance_s2_4_reconcile as reconcile_leaf  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
import s2_4_w3b_testkit as kit  # noqa: E402
import s2_4_w4b_testkit as w4b  # noqa: E402


@pytest.fixture()
def fx(tmp_path, monkeypatch):
    return w4b.Fixture(tmp_path, monkeypatch)


# ══════════════════════════ source lane / success identity ═════════════════════
def test_source_lane_is_pending_with_zero_mutation(fx) -> None:
    verdict = fx.apply(driver=None)
    assert verdict["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert verdict["mutation_performed"] is False
    assert verdict["driver_engaged"] is False
    assert verdict["receipt"] is None and verdict["journal"] is None
    # 零主機接觸:lock/檔案面從未被索取,ledger/journal 皆未落盤。
    assert fx.driver.calls == []
    assert fx.lock_fake.calls == []
    assert fx.persisted_install_journal() is None
    assert w4b.LEDGER_BASENAME in fx.fs.files  # 只有 fixture 種下的前導 lineage
    assert len(fx.persisted_replay_ledger()["entries"]) == 3


def test_the_full_transaction_drives_five_rows_in_the_required_order(fx) -> None:
    verdict = fx.apply()
    assert verdict["status"] == "SOURCE_SIMULATION_PASS", verdict["reasons"]
    assert [step["component_effect_class"] for step in verdict["step_results"]] == list(
        runner.APPLY_ROW_ORDER
    )
    assert [step["step_index"] for step in verdict["step_results"]] == [0, 1, 2, 3, 5]
    assert all(step["state"] == "VERIFIED" for step in verdict["step_results"])
    assert all(
        validator.validate_aiml_artifact(step) == [] for step in verdict["step_results"]
    )
    assert {name: v["status"] for name, v in verdict["row_verdicts"].items()} == {
        name: "SATISFIED" for name in runner.APPLY_ROW_ORDER
    }


def test_success_emits_a_validated_receipt_bound_to_the_plan_lineage(fx) -> None:
    verdict = fx.apply()
    receipt = verdict["receipt"]
    assert validator.validate_aiml_artifact(receipt) == []
    assert validator.derive_install_lineage_status(receipt, install_plan=fx.plan) == {
        "status": "SATISFIED", "reasons": []
    }
    assert receipt["plan_id"] == fx.plan["plan_id"] == receipt["idempotency_key"]
    assert receipt["plan_core_digest"] == fx.plan["core_digest"]
    assert receipt["reverse_compensation_chain_digest"] == runner.aggregate_rollback_digest(
        plan_id=fx.plan["plan_id"]
    )
    assert receipt["journal_digest"] == fx.persisted_install_journal()["self_digest"]
    assert receipt["unit_state"] == {"loaded": True, "disabled": True, "inactive": True}
    assert receipt["service_flags"] == {
        "service_enabled": False, "service_active": False, "service_started_by_s2_4": False,
    }


def test_a_self_declared_attested_driver_never_reaches_applied_inactive(tmp_path, monkeypatch) -> None:
    """§10.5 #13:in-process 無從分辨 fixture 與真主機 driver,故自報 attested 一律被拒。"""

    fixture = w4b.Fixture(tmp_path, monkeypatch)
    fixture.driver.evidence_class = "PLATFORM_ATTESTED"
    verdict = fixture.apply()
    assert verdict["status"] == "SOURCE_SIMULATION_PASS"
    assert verdict["receipt"]["status"] != "APPLIED_INACTIVE"
    assert verdict["receipt"]["evidence_class"] == "STRUCTURAL_ONLY"
    assert verdict["receipt"]["production_authority_flags"] == {
        "nine_authorities_false": True, "production_apply_performed": False,
        "running_attested": False,
    }
    assert any("self-declared" in reason for reason in verdict["reasons"])


def test_the_abi_names_applied_inactive_as_the_only_success_identity() -> None:
    projection = runner.install_driver_abi_projection()
    assert projection["install_receipt_success_identity"] == "APPLIED_INACTIVE"
    assert projection["source_lane_terminal_identity"] == "SOURCE_SIMULATION_PASS"
    assert projection["aggregate_entrypoint"].endswith("apply_s2_4_install_plan")
    assert projection["apply_row_order"] == list(runner.APPLY_ROW_ORDER)
    assert projection["reverse_compensation_order"] == list(
        reversed(runner.APPLY_ROW_ORDER)
    )
    # §10.2 的 typed 終端集合恰為 receipt schema 的封閉 enum(無別名把其一變成 success)。
    schema = validator._load_schema("s2_4_install_effect_receipt_v1")
    enum = set(schema["$defs"]["status"]["enum"])
    assert set(runner.AGGREGATE_TYPED_STATUSES) <= enum


# ══════════════════════════ §10.5 #24 aggregate inputs/success ═════════════════
def test_both_scoped_probe_receipts_are_required(fx) -> None:
    for missing in ("PREPARE_SANDBOX", "INSTALLED_UNIT"):
        partial = {k: v for k, v in fx.probe_receipts.items() if k != missing}
        verdict = fx.apply(probe_receipts=partial)
        assert verdict["status"] == "PRECHECK_FAILED"
        assert any("BOTH scoped terminal" in reason for reason in verdict["reasons"])
        assert fx.driver.calls == []


def test_one_probe_cannot_serve_both_scopes(fx) -> None:
    duplicated = {scope: fx.probe_receipts["PREPARE_SANDBOX"] for scope in fx.probe_receipts}
    verdict = fx.apply(probe_receipts=duplicated)
    assert verdict["status"] == "PRECHECK_FAILED"
    assert any("probe_scope is" in reason for reason in verdict["reasons"])
    assert fx.driver.calls == []


def test_a_non_terminal_probe_receipt_cannot_gate_the_transaction(fx) -> None:
    forged = deepcopy(fx.probe_receipts)
    forged["INSTALLED_UNIT"] = dict(forged["INSTALLED_UNIT"])
    forged["INSTALLED_UNIT"]["terminal_status"] = "RECOVERY_REQUIRED"
    forged["INSTALLED_UNIT"]["self_digest"] = validator.artifact_self_digest({
        k: v for k, v in forged["INSTALLED_UNIT"].items() if k != "self_digest"
    })
    verdict = fx.apply(probe_receipts=forged)
    assert verdict["status"] == "PRECHECK_FAILED"
    assert any("terminal_status" in reason for reason in verdict["reasons"])


def test_a_probe_receipt_without_zero_residue_is_rejected(fx) -> None:
    forged = deepcopy(fx.probe_receipts)
    receipt = dict(forged["PREPARE_SANDBOX"])
    lifecycle = dict(receipt["transient_unit_lifecycle"])
    lifecycle["zero_residue_verified"] = False
    receipt["transient_unit_lifecycle"] = lifecycle
    receipt["self_digest"] = validator.artifact_self_digest(
        {k: v for k, v in receipt.items() if k != "self_digest"}
    )
    forged["PREPARE_SANDBOX"] = receipt
    verdict = fx.apply(probe_receipts=forged)
    assert verdict["status"] == "PRECHECK_FAILED"
    assert any("zero_residue_verified" in reason for reason in verdict["reasons"])


def test_a_stale_or_swapped_prepare_receipt_is_rejected(fx) -> None:
    forged = deepcopy(fx.prepare_receipt)
    forged["terminal_status"] = "PREPARE_FAILED"
    forged["self_digest"] = validator.artifact_self_digest(
        {k: v for k, v in forged.items() if k != "self_digest"}
    )
    verdict = fx.apply(prepare_effect_receipt=forged)
    assert verdict["status"] == "PRECHECK_FAILED"
    assert any("non-terminal or changed PREPARE lineage" in r for r in verdict["reasons"])


def test_all_five_component_intents_are_required_and_plan_bound(fx) -> None:
    for missing in runner.APPLY_ROW_ORDER:
        partial = {k: v for k, v in fx.component_intents.items() if k != missing}
        verdict = fx.apply(component_intents=partial)
        assert verdict["status"] == "PRECHECK_FAILED"
        assert any("five §5.1 APPLY component intents" in r for r in verdict["reasons"])
        assert fx.driver.calls == []


def test_a_substituted_component_intent_is_not_the_one_the_plan_pinned(fx) -> None:
    swapped = dict(fx.component_intents)
    original = swapped["ENGINE_SCANNER"]
    swapped["ENGINE_SCANNER"] = runner._component.build_component_effect_intent(
        component_effect_class="ENGINE_SCANNER",
        install_plan_digest=original["install_plan_digest"],
        pre_state_digest=original["pre_state_digest"],
        required_intent_fields={
            **original["required_intent_fields"],
            "inactive_post_state_digest": "sha256:" + "9" * 64,
        },
        expires_at=original["expires_at"],
    )
    verdict = fx.apply(component_intents=swapped)
    assert verdict["status"] == "PRECHECK_FAILED"
    assert any("no-cycle binding" in reason for reason in verdict["reasons"])
    assert fx.driver.calls == []


def test_the_plan_intent_binding_has_no_digest_cycle() -> None:
    """§5.1「There is no digest/signature cycle」:兩個自指欄位被排除,其餘全被釘住。"""

    intent = runner._component.build_component_effect_intent(
        component_effect_class="HOST_IDENTITY_INSTALL",
        install_plan_digest="sha256:" + "1" * 64,
        pre_state_digest="sha256:" + "2" * 64,
        required_intent_fields={"uid_gid_directory_manifest_digest": "sha256:" + "3" * 64},
        expires_at=kit.EXPIRES,
    )
    binding = runner.component_intent_plan_binding_digest(intent)
    # 換 install_plan_digest / self_digest 不改 binding(否則就是環)。
    repointed = dict(intent)
    repointed["install_plan_digest"] = "sha256:" + "4" * 64
    repointed["self_digest"] = validator.artifact_self_digest(
        {k: v for k, v in repointed.items() if k != "self_digest"}
    )
    assert runner.component_intent_plan_binding_digest(repointed) == binding
    # 換任何**其他**欄位一定改 binding。
    for field, value in (
        ("pre_state_digest", "sha256:" + "5" * 64), ("expires_at", kit.ISSUED),
    ):
        drifted = dict(intent)
        drifted[field] = value
        assert runner.component_intent_plan_binding_digest(drifted) != binding
    assert runner.install_driver_abi_projection()["intent_self_referential_fields"] == [
        "install_plan_digest", "self_digest"
    ]


def test_aggregate_success_requires_five_distinct_row_results() -> None:
    probes = {"PREPARE_SANDBOX": "sha256:" + "1" * 64, "INSTALLED_UNIT": "sha256:" + "2" * 64}
    prepare = "sha256:" + "3" * 64
    good = {
        name: ("sha256:" + f"{index}" * 64, "sha256:" + f"{index + 5}" * 64)
        for index, name in enumerate(runner.APPLY_ROW_ORDER)
    }
    assert runner.derive_aggregate_success_status(
        probe_receipt_digests=probes, prepare_result_digest=prepare, row_results=good
    )["status"] == "AGGREGATE_SUCCESS_SATISFIED"
    # 缺一列 / 重複的 result digest / 缺 PREPARE / 同一 probe 兩 scope 皆不滿足。
    for broken in (
        {k: v for k, v in good.items() if k != "ENGINE_SCANNER"},
        {**good, "ENGINE_SCANNER": good["HOST_IDENTITY_INSTALL"]},
    ):
        assert runner.derive_aggregate_success_status(
            probe_receipt_digests=probes, prepare_result_digest=prepare, row_results=broken
        )["status"] == "AGGREGATE_SUCCESS_NOT_SATISFIED"
    assert runner.derive_aggregate_success_status(
        probe_receipt_digests=probes, prepare_result_digest=None, row_results=good
    )["status"] == "AGGREGATE_SUCCESS_NOT_SATISFIED"
    assert runner.derive_aggregate_success_status(
        probe_receipt_digests={scope: probes["INSTALLED_UNIT"] for scope in probes},
        prepare_result_digest=prepare, row_results=good,
    )["status"] == "AGGREGATE_SUCCESS_NOT_SATISFIED"


# ══════════════════ AGGREGATE_PLAN_PAYLOAD_FULL_COMPARISON ═════════════════════
def test_every_permit_payload_field_is_compared_field_by_field() -> None:
    coverage = runner.derive_permit_payload_coverage()
    for profile_key in ("apply_aggregate", "pg_migration"):
        row = coverage[profile_key]
        assert row["complete"] is True
        assert row["uncompared_fields"] == [] and row["extra_fields"] == []
        # 15 個 §9.1 payload 欄位 = 14 個被逐欄比對 + 自指的 authorization_id。
        assert row["payload_field_count"] == 15
        assert row["compared_field_count"] == 14
        assert row["window_fields"] == ["issued_at", "expires_at"]


def test_the_expected_bindings_are_derived_from_the_plan_not_the_permit(fx) -> None:
    aggregate = runner.aggregate_permit_payload_binding(
        fx.plan, installed_unit_probe_receipt=fx.probe_receipts["INSTALLED_UNIT"],
        issued_at=kit.ISSUED, expires_at=kit.EXPIRES,
    )
    core = fx.plan["core"]
    assert aggregate["plan_core_digest"] == fx.plan["core_digest"]
    assert aggregate["plan_id"] == aggregate["idempotency_key"] == fx.plan["plan_id"]
    assert aggregate["prepare_receipt_digest"] == core["prepare_receipt_digest"]
    assert aggregate["topology_pre_digest"] == core["topology_pre_digest"]
    assert aggregate["hba_delta_digest"] == core["hba_delta_digest"]
    assert aggregate["pre_state_digest"] == core["pre_state_digest"]
    assert aggregate["installed_unit_probe_receipt_digest"] == (
        fx.probe_receipts["INSTALLED_UNIT"]["self_digest"]
    )
    assert aggregate["aggregate_rollback_digest"] == runner.aggregate_rollback_digest(
        plan_id=fx.plan["plan_id"]
    )
    pg = runner.pg_permit_payload_binding(
        fx.plan, component_intents=fx.component_intents,
        installed_unit_probe_receipt=fx.probe_receipts["INSTALLED_UNIT"],
        issued_at=kit.ISSUED, expires_at=kit.EXPIRES,
    )
    pg_intent = fx.component_intents["PG_ROLE_ACL_MIGRATION"]
    assert pg["pg_acl_digest"] == pg_intent["required_intent_fields"]["acl_manifest_digest"]
    assert pg["pg_pre_state_digest"] == pg_intent["pre_state_digest"]
    assert pg["pg_rollback_digest"] == runner.per_row_rollback_digest(
        plan_id=fx.plan["plan_id"], component_effect_class="PG_ROLE_ACL_MIGRATION"
    )


@pytest.mark.parametrize("field", [
    "plan_core_digest", "plan_id", "idempotency_key", "source_head", "target_host",
    "prepare_receipt_digest", "topology_pre_digest", "installed_unit_probe_receipt_digest",
    "hba_delta_digest", "pre_state_digest", "aggregate_rollback_digest",
])
def test_a_single_swapped_aggregate_payload_field_is_authorization_rejected(fx, field) -> None:
    binding = runner.aggregate_permit_payload_binding(
        fx.plan, installed_unit_probe_receipt=fx.probe_receipts["INSTALLED_UNIT"],
        issued_at=kit.ISSUED, expires_at=kit.EXPIRES,
    )
    binding[field] = (
        "1" * 40 if field == "source_head"
        else "other-host" if field == "target_host"
        else "s2-4-" + "9" * 64 if field in {"plan_id", "idempotency_key"}
        else "sha256:" + "9" * 64
    )
    forged = kit.authorization(
        fx.private_key, profile_key="apply_aggregate", payload_binding=binding
    )
    verdict = fx.apply(
        authorization_set={**fx.authorization_set, "apply_aggregate": forged}
    )
    assert verdict["status"] == "AUTHORIZATION_REJECTED", verdict["reasons"]
    assert fx.driver.calls == []
    assert len(fx.persisted_replay_ledger()["entries"]) == 3  # 零 append


@pytest.mark.parametrize("field", [
    "pg_acl_digest", "pg_pre_state_digest", "pg_rollback_digest", "topology_pre_digest",
])
def test_a_single_swapped_pg_payload_field_is_authorization_rejected(fx, field) -> None:
    binding = runner.pg_permit_payload_binding(
        fx.plan, component_intents=fx.component_intents,
        installed_unit_probe_receipt=fx.probe_receipts["INSTALLED_UNIT"],
        issued_at=kit.ISSUED, expires_at=kit.EXPIRES,
    )
    binding[field] = "sha256:" + "9" * 64
    forged = kit.authorization(
        fx.private_key, profile_key="pg_migration", payload_binding=binding
    )
    verdict = fx.apply(authorization_set={**fx.authorization_set, "pg_migration": forged})
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert fx.driver.calls == []


def test_both_permits_are_required_and_extras_are_refused(fx) -> None:
    for missing in ("apply_aggregate", "pg_migration"):
        partial = {k: v for k, v in fx.authorization_set.items() if k != missing}
        verdict = fx.apply(authorization_set=partial)
        assert verdict["status"] == "AUTHORIZATION_REJECTED"
        assert any(f"requires the {missing} permit" in r for r in verdict["reasons"])
    verdict = fx.apply(
        authorization_set={**fx.authorization_set, "prepare": fx.authorization_set[
            "apply_aggregate"
        ]}
    )
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert any("unrelated authorization profiles" in r for r in verdict["reasons"])


def test_a_permit_ttl_over_the_ceiling_is_rejected(fx) -> None:
    binding = runner.aggregate_permit_payload_binding(
        fx.plan, installed_unit_probe_receipt=fx.probe_receipts["INSTALLED_UNIT"],
        issued_at=kit.ISSUED, expires_at="2030-01-01T01:00:00+00:00",
    )
    forged = kit.authorization(
        fx.private_key, profile_key="apply_aggregate",
        payload_binding=binding, expires_at="2030-01-01T01:00:00+00:00",
    )
    verdict = fx.apply(
        authorization_set={**fx.authorization_set, "apply_aggregate": forged}
    )
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert any("ceiling" in reason for reason in verdict["reasons"])


# ══════════════════════════ §9 TTL budget ══════════════════════════════════════
def test_the_apply_budget_must_fit_inside_every_governing_ttl(fx) -> None:
    verdict = fx.apply(apply_budget={**w4b.APPLY_BUDGET, "apply_budget": 3600})
    assert verdict["status"] == "PRECHECK_FAILED"
    assert any("§9 forbids running the operation" in r for r in verdict["reasons"])
    assert fx.driver.calls == []


def test_an_incomplete_budget_term_set_is_rejected(fx) -> None:
    incomplete = {
        term: 30 for term in runner._permit.APPLY_TTL_BUDGET_TERMS if term != "safety_margin"
    }
    verdict = fx.apply(apply_budget=incomplete)
    assert verdict["status"] == "PRECHECK_FAILED"
    assert any("exact §9 term set" in reason for reason in verdict["reasons"])


# ══════════════════════════ §5.2 lock / replay / reconcile ═════════════════════
def test_lock_contention_is_install_lock_held_with_zero_mutation(fx) -> None:
    fx.lock_fake.flock_succeeds = False
    verdict = fx.apply()
    assert verdict["status"] == "INSTALL_LOCK_HELD"
    assert verdict["mutation_performed"] is False
    assert fx.persisted_install_journal() is None
    assert len(fx.persisted_replay_ledger()["entries"]) == 3
    assert all(row.calls == [] for row in fx.row_drivers.values())


@pytest.mark.parametrize("attribute,value", [
    ("lock_nlink", 2), ("lock_is_regular", False), ("lock_uid", 1000),
    ("parent_mode", "1777"), ("replace_parent_on_fstat", True),
])
def test_hostile_lock_state_fails_before_any_mutation(fx, attribute, value) -> None:
    setattr(fx.lock_fake, attribute, value)
    verdict = fx.apply()
    assert verdict["status"] == "PRECHECK_FAILED"
    assert fx.persisted_install_journal() is None
    assert all(row.calls == [] for row in fx.row_drivers.values())


def test_both_permits_are_consumed_once_under_the_acquired_lock(fx) -> None:
    verdict = fx.apply()
    assert verdict["status"] == "SOURCE_SIMULATION_PASS"
    ledger = fx.persisted_replay_ledger()
    assert [entry["profile_identity"] for entry in ledger["entries"][-2:]] == [
        "aiml-s2-install-operator-v1", "aiml-s2-pg-migration-operator-v1"
    ]
    assert validator._s2_4_replay_ledger_errors(ledger) == []
    assert verdict["replay"]["status"] == "AUTHORIZATION_CONSUMPTION_APPENDED"
    assert sorted(verdict["replay"]["appended_authorization_ids"]) == sorted(
        [
            fx.authorization_set["apply_aggregate"]["authorization_id"],
            fx.authorization_set["pg_migration"]["authorization_id"],
        ]
    )
    # flock 在 openat + fstat 四項證明之後才發生,且 lock 從不被 unlink。
    assert fx.lock_fake.calls.index("flock_exclusive_nonblocking") > fx.lock_fake.calls.index(
        "fstat_lock_file"
    )
    assert not any("unlink" in call for call in fx.lock_fake.calls)


def test_replaying_the_same_key_re_executes_nothing(fx) -> None:
    first = fx.apply()
    assert first["status"] == "SOURCE_SIMULATION_PASS"
    before = {name: list(driver.calls) for name, driver in fx.row_drivers.items()}
    ledger_before = fx.persisted_replay_ledger()
    second = fx.apply()
    assert second["status"] == "RECOVERY_REQUIRED"
    assert any("re-executes nothing" in reason for reason in second["reasons"])
    assert second["receipt"] is None
    # 沒有第二筆 append,也沒有任何 row 被重跑。
    assert fx.persisted_replay_ledger() == ledger_before
    assert {name: driver.calls for name, driver in fx.row_drivers.items()} == before


def test_the_same_key_bound_to_a_different_plan_is_rejected(fx, tmp_path, monkeypatch) -> None:
    """§10.5 #8 後半:同一 idempotency key 綁到不同 plan 一律 AUTHORIZATION_REJECTED。"""

    fx.apply()
    ledger = fx.persisted_replay_ledger()
    consumed_id = ledger["entries"][-2]["authorization_id"]
    binding = runner.aggregate_permit_payload_binding(
        fx.plan, installed_unit_probe_receipt=fx.probe_receipts["INSTALLED_UNIT"],
        issued_at=kit.ISSUED, expires_at=kit.EXPIRES,
    )
    # 同 id、不同 payload(hba_delta 被換掉)= 同 key 指向另一份 plan。
    binding["hba_delta_digest"] = "sha256:" + "c" * 64
    forged = kit.authorization(
        fx.private_key, profile_key="apply_aggregate", payload_binding=binding,
        authorization_id=consumed_id,
    )
    verdict = fx.apply(
        authorization_set={**fx.authorization_set, "apply_aggregate": forged}
    )
    assert verdict["status"] == "AUTHORIZATION_REJECTED"


def test_an_empty_ledger_proves_the_prior_lineage_never_consumed_anything(fx) -> None:
    """§5.1:APPLY 之前 probe/PREPARE 必已 durable 消費過自己的 permit。"""

    fx.fs.files.pop(w4b.LEDGER_BASENAME)
    verdict = fx.apply()
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert any("records no prior consumption" in r for r in verdict["reasons"])
    assert fx.persisted_install_journal() is None
    assert all(row.calls == [] for row in fx.row_drivers.values())


def test_a_corrupt_ledger_is_never_overwritten(fx) -> None:
    fx.fs.files[w4b.LEDGER_BASENAME] = b'{"schema_version": "s2_4_authorization_replay_l'
    verdict = fx.apply()
    assert verdict["status"] == "JOURNAL_CORRUPT_RECOVERY_REQUIRED"
    assert fx.fs.files[w4b.LEDGER_BASENAME] == (
        b'{"schema_version": "s2_4_authorization_replay_l'
    )
    assert all(row.calls == [] for row in fx.row_drivers.values())


def test_a_non_terminal_apply_journal_blocks_a_new_plan(fx) -> None:
    """§5.2:啟動 reconcile 在接受新 plan 之前收斂;不明狀態 = RECOVERY_REQUIRED 零變更。"""

    stranded = journal.build_install_journal(
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
    basename = journal.install_journal_path(fx.plan["plan_id"]).rsplit("/", 1)[-1]
    fx.fs.files[basename] = validator._canonical_bytes(stranded)
    verdict = fx.apply()
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert verdict["reconcile"]["lanes"]["install"]["status"] == "RECOVERY_REQUIRED"
    assert all(row.calls == [] for row in fx.row_drivers.values())
    # journal 未被覆寫。
    assert fx.fs.files[basename] == validator._canonical_bytes(stranded)


def test_a_corrupt_apply_journal_is_typed_corrupt_and_never_renamed(fx) -> None:
    basename = journal.install_journal_path(fx.plan["plan_id"]).rsplit("/", 1)[-1]
    fx.fs.files[basename] = b'{"schema_version": "s2_4_install_journal_v1", "entr'
    verdict = fx.apply()
    assert verdict["status"] == "JOURNAL_CORRUPT_RECOVERY_REQUIRED"
    assert fx.fs.files[basename] == (
        b'{"schema_version": "s2_4_install_journal_v1", "entr'
    )
    assert all(row.calls == [] for row in fx.row_drivers.values())


def test_reconcile_resume_and_not_applied_projections(fx) -> None:
    """§5.2 四分:等於 post-state → 續驗(不接受新 plan);等於 pre-state → 安全續行。"""

    def _stranded(post_state: str) -> bytes:
        built = journal.build_install_journal(
            plan_id=fx.plan["plan_id"], plan_core_digest=fx.plan["core_digest"],
            idempotency_key=fx.plan["plan_id"],
            expected_pre_state_digest=fx.plan["core"]["pre_state_digest"],
            aggregate_rollback_digest=runner.aggregate_rollback_digest(
                plan_id=fx.plan["plan_id"]
            ),
            entries=[{
                "seq": 0, "step_index": 0, "state": "APPLYING",
                "pre_state_digest": "sha256:" + "2" * 64, "post_state_digest": post_state,
                "fsynced": True, "recorded_at": kit.ISSUED,
            }],
            terminal=False,
        )
        return validator._canonical_bytes(built)

    basename = journal.install_journal_path(fx.plan["plan_id"]).rsplit("/", 1)[-1]
    # (a) 觀測 == 計畫 post-state → RESUME_VERIFICATION,不接受新 plan。
    fx.fs.files[basename] = _stranded("sha256:" + "4" * 64)
    verdict = fx.apply(startup_observed_state_digests={"install": "sha256:" + "4" * 64})
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert verdict["reconcile"]["lanes"]["install"]["status"] == (
        "STARTUP_RECONCILE_RESUME_VERIFICATION"
    )
    # (b) 觀測 == pre-state → 標記未施作並安全續行(交易照跑)。
    fx.fs.files[basename] = _stranded("sha256:" + "4" * 64)
    resumed = fx.apply(startup_observed_state_digests={"install": "sha256:" + "2" * 64})
    assert resumed["reconcile"]["lanes"]["install"]["status"] == (
        "STARTUP_RECONCILE_STEP_NOT_APPLIED"
    )
    assert resumed["reconcile"]["admits_new_work"] is True
    assert resumed["status"] == "SOURCE_SIMULATION_PASS", resumed["reasons"]


def test_reconcile_requires_the_lock_and_refuses_without_a_driver() -> None:
    paths = {"install": journal.install_journal_path("s2-4-" + "a" * 64)}
    assert reconcile_leaf.reconcile_startup_journals(
        object(), journal_paths=paths, lock_verdict=None
    )["status"] == "INSTALL_LOCK_REQUIRED"
    held = {"status": lock.LOCK_STATUS_ACQUIRED}
    pending = reconcile_leaf.reconcile_startup_journals(
        None, journal_paths=paths, lock_verdict=held
    )
    assert pending["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert pending["mutation_performed"] is False
    assert reconcile_leaf.reconcile_startup_journals(
        object(), journal_paths={}, lock_verdict=held
    )["status"] == "RECOVERY_REQUIRED"


def test_reconcile_covers_the_probe_and_prepare_lanes_when_paths_are_supplied(fx) -> None:
    probe_id = journal.PROBE_ID_PREFIX + "a" * 64
    prepare_id = journal.PREPARE_ID_PREFIX + "b" * 64
    stranded = journal.build_probe_journal(
        probe_id=probe_id, derived_unit_name=f"arcane-aiml-s2-4-probe-{'a' * 64}.service",
        scope="PREPARE_SANDBOX", transient_unit_property_digest="sha256:" + "1" * 64,
        expected_invocation_id_pattern="^[0-9a-f]{32}$",
        cleanup_rollback_digest="sha256:" + "2" * 64,
        entries=[{
            "seq": 0, "state": "APPLYING", "pre_state_digest": "sha256:" + "3" * 64,
            "post_state_digest": "sha256:" + "4" * 64, "fsynced": True,
            "recorded_at": kit.ISSUED,
        }],
        terminal=False,
    )
    basename = journal.probe_journal_path(probe_id).rsplit("/", 1)[-1]
    fx.fs.files[basename] = validator._canonical_bytes(stranded)
    verdict = fx.apply(startup_journal_paths={
        "probe": journal.probe_journal_path(probe_id),
        "prepare": journal.prepare_journal_path(prepare_id),
    })
    assert verdict["status"] == "RECOVERY_REQUIRED"
    lanes = verdict["reconcile"]["lanes"]
    assert lanes["probe"]["status"] == "RECOVERY_REQUIRED"
    assert lanes["prepare"]["status"] == "STARTUP_RECONCILE_CLEAN"
    assert all(row.calls == [] for row in fx.row_drivers.values())


# ══════════════════════════ RUNNER_WAL_LOCK_WIRING ═════════════════════════════
def _routed(driver, fs, *, lock_verdict, step_index=0):
    plan_id = journal.PLAN_ID_PREFIX + "a" * 64
    store = journal.JournalStore(fs, journal_path=journal.install_journal_path(plan_id))

    def _build(entries, terminal):
        return journal.build_install_journal(
            plan_id=plan_id, plan_core_digest="sha256:" + "1" * 64, idempotency_key=plan_id,
            expected_pre_state_digest="sha256:" + "2" * 64,
            aggregate_rollback_digest="sha256:" + "3" * 64, entries=entries, terminal=terminal,
        )

    return reconcile_leaf.JournalRoutedDriver(
        driver, store=store, build_journal=_build, lock_verdict=lock_verdict,
        clock=kit.frozen_clock(), step_index=step_index,
    )


def test_journal_routed_driver_persists_through_the_store_under_the_lock() -> None:
    from test_agent_governance_s2_4_journal import FakeDurableFs

    class _Host:
        evidence_class = "STRUCTURAL_ONLY"

        def __init__(self):
            self.calls = []

        def journal_transition(self, *, entry):
            self.calls.append("host_journal_transition")

        def observe_unit(self):
            self.calls.append("observe_unit")
            return None

    fs = FakeDurableFs()
    host = _Host()
    routed = _routed(host, fs, lock_verdict={"status": lock.LOCK_STATUS_ACQUIRED})
    routed.journal_transition(entry={
        "state": "APPLYING", "pre_state_digest": "sha256:" + "2" * 64,
        "post_state_digest": "sha256:" + "4" * 64,
    })
    # journalling 走 store(temp → fsync → rename → parent fsync),不再落在 host driver 上。
    assert host.calls == []
    assert "atomic_rename" in fs.calls and fs.parent_fsyncs == 1
    assert len(routed.entries) == 1 and routed.entries[0]["seq"] == 0
    assert routed.entries[0]["step_index"] == 0 and routed.entries[0]["fsynced"] is True
    # 其他每一個屬性原樣委派(host 對主機做什麼完全沒變)。
    assert routed.observe_unit() is None
    assert host.calls == ["observe_unit"]
    assert routed.wrapped_driver is host
    assert routed.evidence_class == "STRUCTURAL_ONLY"


def test_journal_routed_driver_refuses_to_persist_without_the_lock() -> None:
    from test_agent_governance_s2_4_journal import FakeDurableFs

    class _Host:
        def journal_transition(self, *, entry):
            raise AssertionError("must not reach the host driver")

    fs = FakeDurableFs()
    for held in (None, {"status": "INSTALL_LOCK_HELD"}, {}):
        routed = _routed(_Host(), fs, lock_verdict=held)
        with pytest.raises(reconcile_leaf.InstallDriverContractError) as excinfo:
            routed.journal_transition(entry={
                "state": "APPLYING", "pre_state_digest": "sha256:" + "2" * 64,
                "post_state_digest": "sha256:" + "4" * 64,
            })
        assert excinfo.value.code == "journal_transition_requires_the_install_lock"
    assert fs.files == {}


def test_journal_routed_driver_raises_when_the_write_is_not_durable() -> None:
    from test_agent_governance_s2_4_journal import FakeDurableFs

    class _Host:
        def journal_transition(self, *, entry):
            return None

    fs = FakeDurableFs(short_write=True)
    routed = _routed(_Host(), fs, lock_verdict={"status": lock.LOCK_STATUS_ACQUIRED})
    with pytest.raises(reconcile_leaf.InstallDriverContractError) as excinfo:
        routed.journal_transition(entry={
            "state": "APPLYING", "pre_state_digest": "sha256:" + "2" * 64,
            "post_state_digest": "sha256:" + "4" * 64,
        })
    assert excinfo.value.code == "journal_transition_was_not_durably_committed"
    assert fs.files == {}
    assert routed.entries == []


# ══════════════════════════ WAL / journal shape ════════════════════════════════
def test_the_apply_journal_is_a_write_ahead_log_not_a_retrospective_log(fx) -> None:
    verdict = fx.apply()
    assert verdict["status"] == "SOURCE_SIMULATION_PASS"
    persisted = fx.persisted_install_journal()
    states = [entry["state"] for entry in persisted["entries"]]
    # 一筆交易一本 WAL:每個 row 六筆——aggregate 的 APPLYING、該 row 內部的
    # APPLYING/APPLIED/VERIFIED(經 JournalRoutedDriver 路由進同一本),再回到 aggregate 的
    # APPLIED(帶**觀測到的** digest)與 VERIFYING;最後是交易的終端 VERIFIED。
    assert states == [
        "APPLYING", "APPLYING", "APPLIED", "VERIFIED", "APPLIED", "VERIFYING",
    ] * 5 + ["VERIFIED"]
    assert [entry["step_index"] for entry in persisted["entries"]] == (
        [0] * 6 + [1] * 6 + [2] * 6 + [3] * 6 + [5] * 7
    )
    assert [entry["seq"] for entry in persisted["entries"]] == list(range(31))
    # 這些 row 內部的轉移**不再**落在 row driver 上(只改 journalling 走哪裡)。
    for driver in fx.row_drivers.values():
        assert not any(str(call).startswith("journal:") for call in driver.calls)
    assert persisted["terminal"] is True
    assert persisted["journal_integrity"]["applying_fsynced_before_effect"] is True
    assert persisted["expected_pre_state_digest"] == fx.plan["core"]["pre_state_digest"]
    assert persisted["aggregate_rollback_digest"] == runner.aggregate_rollback_digest(
        plan_id=fx.plan["plan_id"]
    )
    assert persisted["self_digest"] != persisted["outer_checksum"]
    assert journal.journal_integrity_errors(persisted) == []
    assert validator.validate_aiml_artifact(persisted) == []


def test_the_journal_records_the_observed_post_state_of_each_step(fx) -> None:
    verdict = fx.apply()
    assert verdict["status"] == "SOURCE_SIMULATION_PASS"
    persisted = fx.persisted_install_journal()
    for name in runner.APPLY_ROW_ORDER:
        step_index = runner.APPLY_ROW_STEP_INDEX[name]
        applied = [
            entry for entry in persisted["entries"]
            if entry["step_index"] == step_index and entry["state"] == "APPLIED"
        ]
        expected = runner._row_observation_digest(
            component_effect_class=name,
            component_intent_digest=runner.component_intent_plan_binding_digest(
                fx.component_intents[name]
            ),
            admitted=True,
        )
        # 該步的最後一筆 APPLIED 是 aggregate 的,帶**觀測到的** post-state digest。
        assert applied[-1]["post_state_digest"] == expected


def test_the_row_journalling_is_routed_through_the_shared_wal_under_the_lock(fx) -> None:
    """RUNNER_WAL_LOCK_WIRING 真的被接上:row 的轉移落在同一本 WAL,而非 row driver 上。"""

    verdict = fx.apply()
    assert verdict["status"] == "SOURCE_SIMULATION_PASS", verdict["reasons"]
    persisted = fx.persisted_install_journal()
    # 每個 row 內部的三筆(APPLYING/APPLIED/VERIFIED)都在同一本 journal 內、seq 單調。
    for name in runner.APPLY_ROW_ORDER:
        step_index = runner.APPLY_ROW_STEP_INDEX[name]
        group = [
            entry for entry in persisted["entries"] if entry["step_index"] == step_index
        ]
        assert [entry["state"] for entry in group][:4] == [
            "APPLYING", "APPLYING", "APPLIED", "VERIFIED"
        ]
        assert all(entry["fsynced"] is True for entry in group)
    # 沒有第二本 journal 被建立(一筆交易一本 WAL)。
    journal_files = [
        name for name in fx.fs.files
        if name.endswith(".journal.json") and not name.startswith(".")
    ]
    assert journal_files == [
        journal.install_journal_path(fx.plan["plan_id"]).rsplit("/", 1)[-1]
    ]


# ══════════════════════════ plan validation / forbidden surfaces ═══════════════
def test_only_a_validated_install_plan_is_accepted(fx) -> None:
    for bad in (None, {}, {"schema_version": "s2_4_prepare_intent_v1"}):
        verdict = runner.apply_s2_4_install_plan(bad, fx.authorization_set, fx.driver)
        assert verdict["status"] == "PRECHECK_FAILED"
        assert verdict["mutation_performed"] is False
    forged = deepcopy(fx.plan)
    forged["core"]["target_host"] = "other-host"
    verdict = runner.apply_s2_4_install_plan(
        forged, fx.authorization_set, fx.driver, component_intents=fx.component_intents,
        probe_receipts=fx.probe_receipts, prepare_effect_receipt=fx.prepare_receipt,
        apply_budget=dict(w4b.APPLY_BUDGET), remaining_ttls=dict(w4b.REMAINING_TTLS),
        now=kit.NOW, clock=kit.frozen_clock(),
    )
    assert verdict["status"] == "PRECHECK_FAILED"
    assert fx.driver.calls == []


def test_an_out_of_order_plan_core_is_rejected_centrally(fx) -> None:
    forged = deepcopy(fx.plan)
    forged["core"]["apply_rows"].reverse()
    forged["core_digest"] = validator.canonical_digest(forged["core"])
    forged["plan_id"] = "s2-4-" + forged["core_digest"].split(":", 1)[1]
    forged["idempotency_key"] = forged["plan_id"]
    forged["self_digest"] = validator.artifact_self_digest(
        {k: v for k, v in forged.items() if k != "self_digest"}
    )
    verdict = runner.apply_s2_4_install_plan(
        forged, fx.authorization_set, fx.driver, component_intents=fx.component_intents,
        probe_receipts=fx.probe_receipts, prepare_effect_receipt=fx.prepare_receipt,
        apply_budget=dict(w4b.APPLY_BUDGET), remaining_ttls=dict(w4b.REMAINING_TTLS),
        now=kit.NOW, clock=kit.frozen_clock(),
    )
    assert verdict["status"] == "PRECHECK_FAILED"
    assert any("§5.1 order" in reason for reason in verdict["reasons"])


@pytest.mark.parametrize("method", [
    "start_transient_unit", "enable", "start", "restart", "enable_unit",
])
def test_an_aggregate_driver_with_a_probe_or_lifecycle_surface_is_refused(fx, method) -> None:
    setattr(fx.driver, method, lambda *args, **kwargs: None)
    verdict = fx.apply()
    assert verdict["status"] == "PRECHECK_FAILED"
    assert any("forbidden operations" in reason for reason in verdict["reasons"])
    assert fx.lock_fake.calls == []
    assert runner.assert_no_aggregate_forbidden_surface(object()) == []


def test_the_installed_unit_must_be_inactive_on_the_success_path(fx) -> None:
    fx.driver.unit_state = "active"
    verdict = fx.apply()
    assert verdict["status"] in {"POSTCHECK_FAILED_ROLLED_BACK", "RECOVERY_REQUIRED"}
    assert verdict["receipt"] is None
    assert any("never a successful S2.4 apply" in r for r in verdict["reasons"])
    assert fx.driver.compensated == list(reversed(runner.APPLY_ROW_ORDER))


def test_the_aggregate_postcheck_verifier_must_differ_from_the_applier(fx) -> None:
    fx.driver.verifier_node = runner.AGGREGATE_APPLIER_NODE
    verdict = fx.apply()
    assert verdict["status"] in {"POSTCHECK_FAILED_ROLLED_BACK", "RECOVERY_REQUIRED"}
    assert any("must differ from the applier" in r for r in verdict["reasons"])
    assert verdict["receipt"] is None


def test_an_aggregate_postcheck_that_fails_compensates_and_emits_no_receipt(fx) -> None:
    verdict = fx.apply(driver=_with_flags(fx, {"all_apply_rows_satisfied": False}))
    assert verdict["status"] == "POSTCHECK_FAILED_ROLLED_BACK", verdict["reasons"]
    assert verdict["receipt"] is None
    assert verdict["postcheck"]["status"] == "FAIL"
    assert any("FAILED on" in reason for reason in verdict["reasons"])
    assert verdict["rollback"]["status"] == "COMPENSATED_EXACT"
    assert verdict["residue"]["installed_unit_inactive"] is True


def _with_flags(fx, flags):
    fx.driver.postcheck_flags.update(flags)
    return fx.driver


def test_the_verifier_cannot_claim_rows_the_applier_did_not_observe(fx) -> None:
    """守門謂詞:獨立 verifier 宣稱五 row 全 satisfied 但 applier 觀測不同 → 該宣稱被拒。

    誠實界線:aggregate 主流程在任一 row 未 admitted 時**先**進逆序補償,故此謂詞是
    「未來若有 admitted-but-not-satisfied 的 row」的守門;此處直接對謂詞本身取證。
    """

    postcheck, reasons = runner._build_aggregate_postcheck(
        driver=fx.driver, plan=fx.plan, applier_node=runner.AGGREGATE_APPLIER_NODE,
        all_rows_admitted=False, clock=kit.frozen_clock(),
    )
    assert postcheck["status"] == "PASS"
    assert any("the claim is refused" in reason for reason in reasons)
    clean, clean_reasons = runner._build_aggregate_postcheck(
        driver=fx.driver, plan=fx.plan, applier_node=runner.AGGREGATE_APPLIER_NODE,
        all_rows_admitted=True, clock=kit.frozen_clock(),
    )
    assert clean["status"] == "PASS" and clean_reasons == []
    assert validator.validate_aiml_artifact(clean) == []
