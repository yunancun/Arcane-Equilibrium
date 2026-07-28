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
import agent_governance_s2_4_install_evidence as evidence_leaf  # noqa: E402
import agent_governance_s2_4_journal as journal  # noqa: E402
import agent_governance_s2_4_lock as lock  # noqa: E402
import agent_governance_s2_4_reconcile as reconcile_leaf  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
import s2_4_w3b_testkit as kit  # noqa: E402
import s2_4_w4b_testkit as w4b  # noqa: E402
from test_agent_governance_s2_4_lock import FakeLockDriver  # noqa: E402


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


# ══════════════ S2.4-AMEND-2:plan-derived expected_topology(§10.5 #25)═════════
def test_a_caller_supplied_expected_topology_is_refused_by_the_frozen_allowlist(fx) -> None:
    """曾經的唯一弱化路徑:caller 遞交 expected_topology。現在是 allowlist typed 拒。"""

    payloads = fx.row_payloads()
    payloads["PG_ROLE_ACL_MIGRATION"]["expected_topology"] = kit.topology_expected(
        fx.attestation
    )
    verdict = fx.apply(row_payloads=payloads)
    assert verdict["status"] == "PRECHECK_FAILED"
    assert any(
        "expected_topology" in reason and "frozen row ABI allowlist" in reason
        for reason in verdict["reasons"]
    ), verdict["reasons"]
    assert verdict["mutation_performed"] is False
    assert fx.driver.calls == []
    assert fx.row_drivers["PG_ROLE_ACL_MIGRATION"].calls == []


def test_the_pg_expected_topology_is_derived_from_the_signed_plan(fx) -> None:
    """正向:零 caller 基線鍵——簽章 delta + 基線 attestation 導出**全鍵** expected,
    disposable lane 的 PG row SATISFIED(缺鍵靜默跳過已無入口)。"""

    payload = fx.row_payloads()["PG_ROLE_ACL_MIGRATION"]
    assert "expected_topology" not in payload and "hba_delta" in payload
    derived = runner.derive_plan_expected_topology(
        plan=fx.plan, hba_delta=fx.hba_delta, topology_attestation=fx.attestation,
    )
    assert derived["status"] == "PLAN_EXPECTED_TOPOLOGY_DERIVED", derived["reasons"]
    assert sorted(derived["expected_topology"]) == [
        "cluster_identity_digest", "hba_projection", "listener_config_digest",
        "proxy_config_digest", "source_head", "target_host",
    ]
    verdict = fx.apply()
    assert verdict["status"] == "SOURCE_SIMULATION_PASS", verdict["reasons"]
    assert verdict["row_verdicts"]["PG_ROLE_ACL_MIGRATION"]["status"] == "SATISFIED"


@pytest.mark.parametrize("mutation", ["absent", "tampered", "foreign_plan"])
def test_an_absent_tampered_or_misbound_hba_delta_is_topology_unproven(fx, mutation) -> None:
    """hba_delta 缺席 / 內容被換(binding digest 不再等 core)/ 綁到別份 plan → 一律
    PG_TOPOLOGY_UNPROVEN,PG row driver 未被觸及。"""

    payloads = fx.row_payloads()
    pg = payloads["PG_ROLE_ACL_MIGRATION"]
    if mutation == "absent":
        pg.pop("hba_delta")
    elif mutation == "tampered":
        pg["hba_delta"]["effective_rule"]["user"] = "postgres"
        pg["hba_delta"]["self_digest"] = validator.artifact_self_digest(pg["hba_delta"])
    else:
        pg["hba_delta"]["plan_id"] = "s2-4-" + "9" * 64
        pg["hba_delta"]["self_digest"] = validator.artifact_self_digest(pg["hba_delta"])
    verdict = fx.apply(row_payloads=payloads)
    assert verdict["status"] == "PG_TOPOLOGY_UNPROVEN", verdict["reasons"]
    assert any("never caller-supplied" in reason for reason in verdict["reasons"])
    assert fx.row_drivers["PG_ROLE_ACL_MIGRATION"].calls == []


def test_a_signed_rule_outside_the_observed_hba_is_topology_unproven(
    tmp_path, monkeypatch,
) -> None:
    """簽進 core 的投影只含另一條 rule 時,attested effective rule 落在簽章投影之外。"""

    fixture = w4b.Fixture(tmp_path, monkeypatch, hba_effective_rule={
        "source": "127.0.0.1/32", "database": "trading_ai",
        "user": "postgres", "method": "scram-sha-256",
    })
    verdict = fixture.apply()
    assert verdict["status"] == "PG_TOPOLOGY_UNPROVEN", verdict["reasons"]
    assert any(
        "outside the signed HBA projection" in reason for reason in verdict["reasons"]
    )
    assert fixture.row_drivers["PG_ROLE_ACL_MIGRATION"].calls == []


def test_a_forged_attestation_wearing_the_signed_baseline_digest_is_refused(fx) -> None:
    """P2-2:偽 attestation 貼上真 baseline digest(欄位等值可過)→ 葉內重算
    ``artifact_self_digest`` 拒;單呼叫葉自此與聚合 lane 同樣 fail-closed。"""

    forged = deepcopy(fx.attestation)
    forged["cluster_identity"]["system_identifier"] = "7000000000000000002"
    # 不重封:貼真簽章 digest 使欄位等值檢查通過,重算必不過。
    forged["self_digest"] = fx.plan["core"]["topology_pre_digest"]
    derived = runner.derive_plan_expected_topology(
        plan=fx.plan, hba_delta=fx.hba_delta, topology_attestation=forged,
    )
    assert derived["status"] == "PLAN_EXPECTED_TOPOLOGY_UNPROVEN"
    assert any(
        "does not re-derive its own canonical bytes" in reason
        for reason in derived["reasons"]
    ), derived["reasons"]


@pytest.mark.parametrize("bad", [
    None,
    "not-a-mapping",
    {},
    {"S2_2A_SOURCE_COMPATIBILITY": None, "S2_3_EXPECTED_IDENTITY": None},
    {
        "S2_2A_SOURCE_COMPATIBILITY": None, "S2_3_EXPECTED_IDENTITY": None,
        "S2_3_SEALED_BUILD": None, "S1_3_IDENTITY_CONTRACT": None,
    },
    {
        "S2_2A_SOURCE_COMPATIBILITY": "not-a-digest", "S2_3_EXPECTED_IDENTITY": None,
        "S2_3_SEALED_BUILD": None,
    },
])
def test_the_receipt_builder_refuses_a_non_admission_shaped_refresh_digest_map(
    fx, bad,
) -> None:
    """P2-1:builder 只在 step (2b) admission 之後可達——None/缺鍵/多鍵/非 digest 值
    一律 typed 契約拒,絕不靜默寫成「三族全 FRESH」的 receipt 宣稱(silent-FRESH 關閉)。"""

    with pytest.raises(runner.InstallDriverContractError):
        evidence_leaf._build_install_effect_receipt(
            plan=fx.plan, status="SOURCE_SIMULATION_PASS",
            authorizations=fx.authorization_set,
            probe_receipt_digests={}, prepare_result_digest="sha256:" + "1" * 64,
            prepare_postcheck_digest="sha256:" + "2" * 64,
            dependency_refresh_digests=bad,
            row_results={}, journal_digest="sha256:" + "3" * 64,
            unit_state={"loaded": True, "disabled": True, "inactive": True},
            evidence_class="STRUCTURAL_ONLY", trusted_host_time=kit.NOW,
            clock=kit.frozen_clock(),
        )


def test_a_presented_attestation_that_is_not_the_signed_baseline_is_unproven(fx) -> None:
    """換叢集:presented attestation ≠ core.topology_pre_digest 所指的簽章前基線。"""

    observation = kit.topology_observation()
    observation["cluster_identity"]["system_identifier"] = "7000000000000000002"
    payloads = fx.row_payloads()
    payloads["PG_ROLE_ACL_MIGRATION"]["topology_attestation"] = kit.topology_attestation(
        observation
    )
    verdict = fx.apply(row_payloads=payloads)
    assert verdict["status"] == "PG_TOPOLOGY_UNPROVEN", verdict["reasons"]
    assert any(
        "not the signed pre-observation baseline" in reason
        for reason in verdict["reasons"]
    )
    assert fx.row_drivers["PG_ROLE_ACL_MIGRATION"].calls == []


# ══════════════ S2.4-AMEND-1:§9.2 ingress at APPLY step (2b)════════════════════
def test_the_apply_ingress_gates_expired_identities_through_one_refresh_each(fx) -> None:
    """三份已提交原身分於凍結 NOW 下**真的已過期**:零 refresh → PRECHECK_FAILED 零變更
    (含 EXPIRED_NO_REFRESH 語義);恰一份真 refresh/族 → 放行,terminal receipt 逐族記
    該 refresh 的 self_digest(§3 的 DEPENDENCY-REFRESH 綁定)。"""

    denied = fx.apply(dependency_refreshes=None)
    assert denied["status"] == "PRECHECK_FAILED"
    assert any("SOURCE_DEPENDENCY_EXPIRED_NO_REFRESH" in r for r in denied["reasons"])
    assert any("§9.2" in r for r in denied["reasons"])
    assert denied["driver_engaged"] is False and denied["mutation_performed"] is False
    assert fx.driver.calls == [] and fx.persisted_install_journal() is None
    refreshes = w4b.dependency_refreshes()
    verdict = fx.apply()
    assert verdict["status"] == "SOURCE_SIMULATION_PASS", verdict["reasons"]
    assert verdict["receipt"]["dependency_refresh_digests"] == {
        cls: refreshes[cls]["self_digest"]
        for cls in evidence_leaf.S2_4_APPLY_GATED_DEPENDENCY_CLASSES
    }
    assert validator.validate_aiml_artifact(verdict["receipt"]) == []


@pytest.mark.parametrize("mutation", [
    "stale_expired", "over_ttl", "inside_original_window", "reasserted_digest",
    "same_producer_label", "foreign_original", "semantic_drift", "two_refreshes",
    "unknown_class",
])
def test_forged_or_stale_refreshes_are_refused_before_any_effect_semantics(
    fx, mutation,
) -> None:
    """§9.2 的每一種禁止形都在 step (2b) typed 拒:重封時間戳、超窗、落在原窗內的復現、
    複述原 digest、同 producer 標籤、綁到非 committed original、語義 digest 漂移、兩份
    refresh、未知 class 鍵——一律 PRECHECK_FAILED、driver 未觸、零 mutation。"""

    refreshes = w4b.dependency_refreshes()
    target = "S2_2A_SOURCE_COMPATIBILITY"
    row = refreshes[target]

    def _reseal_identity() -> None:
        row["reproduction"]["reproducer_identity"] = validator.dependency_producer_identity(
            caller=row["reproduction"]["reproducer_caller"],
            observation_time=row["reproduction"]["reproduced_at"],
            platform=row["reproduction"]["reproducer_platform"],
        )

    if mutation == "stale_expired":
        row["reproduction"]["reproduced_at"] = "2029-12-31T23:00:00+00:00"
        row["expires_at"] = "2029-12-31T23:15:00+00:00"
        _reseal_identity()
    elif mutation == "over_ttl":
        row["refresh_ttl_seconds"] = 901
        row["expires_at"] = "2030-01-01T00:15:01+00:00"
    elif mutation == "inside_original_window":
        row["reproduction"]["reproduced_at"] = "2026-07-24T00:00:00+00:00"
        row["expires_at"] = "2026-07-24T00:15:00+00:00"
        _reseal_identity()
    elif mutation == "reasserted_digest":
        row["reproduced_semantic_digests"] = {
            field: row["original_receipt_digest"]
            for field in row["reproduced_semantic_digests"]
        }
    elif mutation == "same_producer_label":
        row["reproduction"]["reproducer_caller"] = "S2.2A"
        _reseal_identity()
    elif mutation == "foreign_original":
        row["original_receipt_digest"] = "sha256:" + "a" * 64
    elif mutation == "semantic_drift":
        field = sorted(row["reproduced_semantic_digests"])[0]
        row["reproduced_semantic_digests"][field] = "sha256:" + "d" * 64
    row["self_digest"] = validator.artifact_self_digest(row)
    supplied: dict = dict(refreshes)
    if mutation == "two_refreshes":
        supplied[target] = [refreshes[target], refreshes[target]]
    elif mutation == "unknown_class":
        supplied["PG_TOPOLOGY_ATTESTATION"] = refreshes[target]
    verdict = fx.apply(dependency_refreshes=supplied)
    assert verdict["status"] == "PRECHECK_FAILED", (mutation, verdict["reasons"])
    assert any("§9.2" in reason for reason in verdict["reasons"]), verdict["reasons"]
    assert verdict["driver_engaged"] is False
    assert verdict["mutation_performed"] is False
    assert fx.driver.calls == []
    assert fx.persisted_install_journal() is None


def test_the_ingress_originals_are_read_from_the_bound_commit_not_the_caller(fx) -> None:
    """caller 無從遞交/替換原身分:ingress 的封閉輸入面只有 {class: refresh};
    原 receipt 由驗證端自 bound commit 的 committed 路徑讀出(code-owned 表最新版)。"""

    import inspect

    signature = inspect.signature(evidence_leaf.derive_apply_source_dependency_admissions)
    assert sorted(signature.parameters) == ["dependency_refreshes", "now", "repo_root"]
    for cls in evidence_leaf.S2_4_APPLY_GATED_DEPENDENCY_CLASSES:
        original = evidence_leaf.load_committed_source_identity(cls)
        assert isinstance(original, dict), cls
        committed = validator.committed_source_identity_digests(cls, w4b.ROOT)
        assert validator.artifact_self_digest(original) in committed, cls
    # S1.3 誠實缺口:不入閘,typed 記錄。
    assert evidence_leaf.load_committed_source_identity("S1_3_IDENTITY_CONTRACT") is None
    admissions = evidence_leaf.derive_apply_source_dependency_admissions(
        now=kit.NOW, dependency_refreshes=w4b.dependency_refreshes(),
    )
    assert admissions["status"] == "SOURCE_DEPENDENCIES_ADMITTED"
    assert "S1_3_IDENTITY_CONTRACT" in admissions["s1_3_not_gated_reason"]


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
    """§10.5 #8:重跑同一份已簽 plan 是 idempotent replay,**不是** recovery 事故。

    這是操作員在一次含糊逾時之後最可能做的事;它過去和「主機處於未知半途態」共用同一個
    ``RECOVERY_REQUIRED``,於是 on-call 無法以狀態分流。它自此有自己的非 recovery 終端,
    並帶回 durable APPLY journal 的 digest(receipt 是那本終端 journal 的投影)。
    """

    first = fx.apply()
    assert first["status"] == "SOURCE_SIMULATION_PASS"
    before = {name: list(driver.calls) for name, driver in fx.row_drivers.items()}
    ledger_before = fx.persisted_replay_ledger()
    second = fx.apply()
    assert second["status"] == "ALREADY_APPLIED_IDEMPOTENT"
    assert second["status"] not in runner.AGGREGATE_TYPED_STATUSES
    assert second["status"] in runner.AGGREGATE_ALL_TYPED_STATUSES
    assert any("re-executes nothing" in reason for reason in second["reasons"])
    assert any("idempotent replay, NOT a recovery" in r for r in second["reasons"])
    assert second["receipt"] is None
    # 終端 journal 的 digest 被交回來,所以 receipt 可以由它投影而不必重新消費 permit。
    assert second["journal"]["terminal"] is True
    assert second["journal"]["self_digest"] == first["journal"]["self_digest"]
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
            "entry_source": "aggregate_transaction",
            "component_effect_class": "HOST_IDENTITY_INSTALL",
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
                "entry_source": "aggregate_transaction",
                "component_effect_class": "HOST_IDENTITY_INSTALL",
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
    # H1:lock 閘在 driver 閘**之前**(§5.2:重啟的 runner 只在持有互斥 install lock 時巡查
    # 並收斂 journal),所以「沒有 driver」這句話只在**已持有** lock 之後才說得出口。
    held = lock.acquire_s2_4_install_lock(FakeLockDriver())
    assert lock.install_lock_is_held(held)
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
            "entry_source": "capability_probe",
            "component_effect_class": "HOST_CAPABILITY_PROBE",
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
    # A2:lock 證明現在是 module-private token,不再是同形的 caller 字典。
    routed = _routed(host, fs, lock_verdict=lock.acquire_s2_4_install_lock(
        FakeLockDriver()
    ))
    routed.journal_transition(entry={
        "state": "APPLYING", "pre_state_digest": "sha256:" + "2" * 64,
        "post_state_digest": "sha256:" + "4" * 64,
        # H2:producer 判別欄現在是 entry 的必要部分,連 pass-through 分支也不例外。
        "entry_source": "component_row_driver",
        "component_effect_class": "HOST_IDENTITY_INSTALL",
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
    routed = _routed(_Host(), fs, lock_verdict=lock.acquire_s2_4_install_lock(
        FakeLockDriver()
    ))
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


# ══════════════════ Fix-C:五腿對抗審計的回歸 ═══════════════════════════════════
def _sign_attestation(fixture, attestation, *, tag, signing_key=None):
    import subprocess

    key = signing_key if signing_key is not None else fixture.private_key
    message = key.parent / f"w4b-attestation-{tag}.bin"
    message.write_bytes(validator._canonical_bytes(attestation))
    signature_path = message.with_name(message.name + ".sig")
    if signature_path.exists():
        signature_path.unlink()
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", str(key),
         "-n", evidence_leaf.APPLY_ATTESTATION_NAMESPACE, str(message)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return signature_path.read_bytes()


def _attest_on_demand(
    fixture, monkeypatch, *, tag="live", mutate=None, signing_key=None, signature_bytes=None,
):
    """讓 fixture 的 driver 在 ``apply_attestation()` 被呼叫時,以**本次**的實觀 row 結果簽出背書。

    真主機上,attestation 正是在 apply 跑完之後才產生的(它綁的 ``applied_row_results_digest``
    只有那時才知道);此處以同一個時序在丟棄式線上重現它。
    """

    captured: dict = {}
    original_run_row = runner._run_row

    def _record(name, **kwargs):
        verdict = original_run_row(name, **kwargs)
        captured[name] = verdict
        return verdict

    monkeypatch.setattr(runner, "_run_row", _record)

    def _produce():
        row_results = {
            name: (
                captured[name]["result"]["self_digest"],
                captured[name]["postcheck"]["self_digest"],
            )
            for name in runner.APPLY_ROW_ORDER
            if isinstance(captured.get(name, {}).get("result"), dict)
        }
        attestation = evidence_leaf.build_s2_4_install_apply_attestation(
            plan=fixture.plan, applier_node=runner.AGGREGATE_APPLIER_NODE,
            verifier_node=fixture.driver.verifier_node, row_results=row_results,
            installed_unit_state={"loaded": True, "disabled": True, "inactive": True},
            trusted_host_time=kit.NOW,
        )
        if mutate is not None:
            attestation = mutate(attestation)
            attestation["attestation_digest"] = evidence_leaf.apply_attestation_digest(
                attestation
            )
        if signature_bytes is not None:
            return {"attestation": attestation, "signature": signature_bytes}
        return {
            "attestation": attestation,
            "signature": _sign_attestation(
                fixture, attestation, tag=tag, signing_key=signing_key
            ),
        }

    fixture.driver.apply_attestation = _produce
    return captured


def test_c12_a_full_transaction_with_a_valid_attestation_reaches_applied_inactive(
    fx, monkeypatch
) -> None:
    """§10.2 的成功身分自此有**活的**轉移:APPLIED_INACTIVE 只由已驗簽的背書解鎖。

    在此之前 ``recorded_evidence_class in EVIDENCE_CLASS_ATTESTED`` 是恆假的套套邏輯
    (``derive_recorded_evidence_class`` 兩條分支都回 ``STRUCTURAL_ONLY``),於是
    ``APPLIED_INACTIVE`` 從未被執行過一次,§10.5 #14 也拿不到正向測試。
    """

    _attest_on_demand(fx, monkeypatch)
    verdict = fx.apply()
    assert verdict["status"] == "APPLIED_INACTIVE", verdict["reasons"]
    assert verdict["attestation"]["status"] == "APPLY_ATTESTATION_VERIFIED"
    assert verdict["receipt"]["status"] == "APPLIED_INACTIVE"
    assert verdict["receipt"]["evidence_class"] == "PLATFORM_ATTESTED"
    assert validator.validate_aiml_artifact(verdict["receipt"]) == []
    assert validator.derive_install_lineage_status(
        verdict["receipt"], install_plan=fx.plan
    )["status"] == "SATISFIED"
    # §10.5 #13:成功身分**不**放寬九 authority,unit 仍 disabled/inactive。
    assert verdict["production_authority_flags"] == {
        "nine_authorities_false": True, "production_apply_performed": False,
        "running_attested": False,
    }
    assert verdict["receipt"]["production_authority_flags"] == (
        verdict["production_authority_flags"]
    )
    assert verdict["receipt"]["service_flags"] == {
        "service_enabled": False, "service_active": False, "service_started_by_s2_4": False,
    }
    assert verdict["receipt"]["unit_state"] == {
        "loaded": True, "disabled": True, "inactive": True
    }


def test_c12_a_self_declared_attested_driver_still_terminates_at_source_simulation(
    fx,
) -> None:
    fx.driver.evidence_class = "PLATFORM_ATTESTED"
    verdict = fx.apply()
    assert verdict["status"] == "SOURCE_SIMULATION_PASS"
    assert verdict["receipt"]["evidence_class"] == "STRUCTURAL_ONLY"
    assert verdict["attestation"]["status"] == "APPLY_ATTESTATION_ABSENT"
    assert any("self-declares evidence_class" in r for r in verdict["reasons"])


@pytest.mark.parametrize("mutation", [
    "plan", "namespace", "verifier", "row_results", "unit_state", "stale_signed_time",
])
def test_c12_a_tampered_attestation_never_unlocks_applied_inactive(
    fx, monkeypatch, mutation
) -> None:
    def _mutate(attestation):
        attestation = dict(attestation)
        if mutation == "plan":
            attestation["plan_core_digest"] = "sha256:" + "e" * 64
        elif mutation == "namespace":
            attestation["signature_namespace"] = (
                "arcane-equilibrium-aiml-s2-install"  # permit 的 namespace
            )
        elif mutation == "verifier":
            attestation["verifier_node"] = runner.AGGREGATE_APPLIER_NODE
        elif mutation == "row_results":
            attestation["reobserved_row_results_digest"] = "sha256:" + "f" * 64
        elif mutation == "unit_state":
            attestation["installed_unit_state_digest"] = "sha256:" + "0" * 64
        else:
            attestation["trusted_host_time"] = "2025-01-01T00:00:00+00:00"
            attestation["attestation_expires_at"] = "2025-01-01T00:10:00+00:00"
        return attestation

    _attest_on_demand(fx, monkeypatch, tag=mutation, mutate=_mutate)
    verdict = fx.apply()
    assert verdict["status"] == "SOURCE_SIMULATION_PASS", verdict["status"]
    assert verdict["attestation"]["status"] == "APPLY_ATTESTATION_REJECTED"
    assert verdict["receipt"]["evidence_class"] == "STRUCTURAL_ONLY"


# ── E2:上面六個負向全部**改欄位再重簽**,所以每一個都被某個欄位比對抓住,沒有一個
#     真的走到 ``_verify_ssh_signature``。M07(把那道驗簽短路掉)因此在 624 支測試下全綠,
#     而一份帶著字面垃圾 bytes 的 attestation 能一路換到 APPLIED_INACTIVE。以下兩支是
#     **只有**驗簽能擋住的負向:攜帶完全合法欄位、但簽章不是 §9.1 信任根簽的。
def test_c12_an_attestation_signed_by_a_foreign_key_never_unlocks_applied_inactive(
    fx, monkeypatch, tmp_path
) -> None:
    """完全合法的 18 欄 + 一把丟棄式外來 Ed25519 金鑰的**真** SSHSIG。

    每一個欄位比對都通過(內容與正例逐字相同),唯一不同的是簽章不是 pinned 信任根簽的——
    所以只有 ``_trusted_host._verify_ssh_signature`` 能拒絕它。
    """

    foreign_key, _foreign_public, _foreign_fingerprint = kit.mint_key(
        tmp_path, name="w4b-foreign-attestor"
    )
    _attest_on_demand(fx, monkeypatch, tag="foreign-key", signing_key=foreign_key)
    verdict = fx.apply()
    assert verdict["status"] == "SOURCE_SIMULATION_PASS", verdict["reasons"]
    assert verdict["attestation"]["status"] == "APPLY_ATTESTATION_REJECTED"
    assert verdict["attestation"]["reasons"] == [
        "apply attestation SSH signature is invalid"
    ], verdict["attestation"]["reasons"]
    assert verdict["receipt"]["evidence_class"] == "STRUCTURAL_ONLY"
    assert verdict["receipt"]["status"] != "APPLIED_INACTIVE"


def test_c12_an_attestation_with_garbage_signature_bytes_never_unlocks_applied_inactive(
    fx, monkeypatch
) -> None:
    """合法欄位 + 字面垃圾 SSHSIG bytes:同樣只有真驗簽能擋。"""

    _attest_on_demand(
        fx, monkeypatch, tag="garbage-signature",
        signature_bytes=(
            b"-----BEGIN SSH SIGNATURE-----\nAAAAdeadbeef\n-----END SSH SIGNATURE-----"
        ),
    )
    verdict = fx.apply()
    assert verdict["status"] == "SOURCE_SIMULATION_PASS", verdict["reasons"]
    assert verdict["attestation"]["status"] == "APPLY_ATTESTATION_REJECTED"
    assert verdict["attestation"]["reasons"] == [
        "apply attestation SSH signature is invalid"
    ], verdict["attestation"]["reasons"]
    assert verdict["receipt"]["evidence_class"] == "STRUCTURAL_ONLY"
    assert verdict["receipt"]["status"] != "APPLIED_INACTIVE"


# ── C3:aggregate 級也必須把補償前的獨立觀測 digest 交出去 ──────────────────────
def test_c3_a_constant_returning_verifier_cannot_buy_exactness_at_the_aggregate_level(
    fx,
) -> None:
    """五個 row driver 在補償前後都回同一個常量 digest → 絕不可換到 ``COMPENSATED_EXACT``。

    row 級呼叫點本來就傳 ``pre_compensation_observed_digest``;aggregate 級過去沒傳,於是
    ``component.py`` 那道「byte-identical ⇒ verifier 沒真的再看一次」的檢查在交易層完全空轉,
    而 W4a commit body 與 ``compensation_exactness_contract`` 都宣稱它有效。
    """

    constant = "sha256:" + "8" * 64
    for row_driver in fx.row_drivers.values():
        row_driver.independent_postcheck = (
            lambda *, component_effect_class, install_plan_digest, applier_node: {
                "verifier_node": "s2-4-independent-verifier",
                "observed_subject_digest": constant,
                "verifier_capture_digest": kit.CAPTURE_DIGEST,
                "applied_state_verified": False,
                "pre_state_lineage_verified": True,
            }
        )
    fx.driver.postcheck_flags["plan_lineage_verified"] = False  # 觸發補償
    verdict = fx.apply()
    assert verdict["status"] == "RECOVERY_REQUIRED", verdict["status"]
    assert verdict["rollback"]["status"] != "COMPENSATED_EXACT"
    assert verdict["rollback"]["exact_pre_state_restored"] is False
    assert any(
        "byte-identical to the pre-compensation observation" in reason
        for reason in verdict["reasons"]
    )


# ── C4:證據新鮮度不再是 caller 自報 ────────────────────────────────────────────
def test_c4_a_year_stale_probe_receipt_can_never_gate_an_apply(fx) -> None:
    stale = deepcopy(fx.probe_receipts)
    receipt = dict(stale["INSTALLED_UNIT"])
    receipt["expires_at"] = "2025-01-01T00:00:00+00:00"
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    stale["INSTALLED_UNIT"] = receipt
    verdict = fx.apply(probe_receipts=stale)
    assert verdict["status"] in {"PRECHECK_FAILED", "AUTHORIZATION_REJECTED"}
    assert verdict["mutation_performed"] is False
    assert all(driver.calls == [] for driver in fx.row_drivers.values())


def test_c4_an_expired_plan_is_refused_before_any_host_contact(fx) -> None:
    stale = deepcopy(fx.plan)
    stale["expires_at"] = "2025-01-01T00:00:00+00:00"
    stale["self_digest"] = validator.artifact_self_digest(stale)
    verdict = runner.apply_s2_4_install_plan(
        stale, fx.authorization_set, fx.driver,
        component_intents=fx.component_intents, row_payloads=fx.row_payloads(),
        probe_receipts=fx.probe_receipts, prepare_effect_receipt=fx.prepare_receipt,
        apply_budget=dict(w4b.APPLY_BUDGET), remaining_ttls=dict(w4b.REMAINING_TTLS),
        now=kit.NOW, clock=kit.frozen_clock(),
    )
    assert verdict["status"] == "PRECHECK_FAILED"
    assert any("the install plan expired" in reason for reason in verdict["reasons"])
    assert verdict["driver_engaged"] is False
    assert fx.driver.calls == []


def test_c4_a_caller_remaining_ttl_can_only_tighten_the_bound(fx) -> None:
    ttls = evidence_leaf.derive_apply_remaining_ttls(
        plan=fx.plan, component_intents=fx.component_intents,
        probe_receipts=fx.probe_receipts, prepare_effect_receipt=fx.prepare_receipt,
        authorizations=fx.authorization_set, row_payloads=fx.row_payloads(),
        now=kit.NOW, caller_remaining_ttls={term: 10 ** 9 for term in ttls_terms()},
    )
    assert ttls["status"] == "APPLY_EVIDENCE_TTLS_DERIVED"
    # caller 遞交十億秒也不能把界放寬:每一項都仍是證據自己的剩餘 TTL。
    for term, value in ttls["effective"].items():
        assert value == ttls["derived"][term] <= 10 ** 9
    tighter = evidence_leaf.derive_apply_remaining_ttls(
        plan=fx.plan, component_intents=fx.component_intents,
        probe_receipts=fx.probe_receipts, prepare_effect_receipt=fx.prepare_receipt,
        authorizations=fx.authorization_set, row_payloads=fx.row_payloads(),
        now=kit.NOW, caller_remaining_ttls={term: 1 for term in ttls_terms()},
    )
    assert set(tighter["effective"].values()) == {1}


def ttls_terms():
    import agent_governance_s2_4_permit as permit_leaf

    return permit_leaf.APPLY_TTL_BOUND_TERMS


def test_c4_a_stale_prepare_receipt_is_a_zero_mutation_refusal(fx) -> None:
    """§6 step 5 的 prepared-bundle 再雜湊排在 step 7 的 consume 與 step 11 的 driver 之前。

    過去一份過期的 PREPARE receipt 只在第 4 列(``LEARNING_RUNTIME``)被抓到——也就是在 host
    identity / PG / credential 三列都已施作**之後**,於是它們必須被補償。
    """

    stale = deepcopy(fx.prepare_receipt)
    stale["expires_at"] = "2025-01-01T00:00:00+00:00"
    verdict = fx.apply(prepare_effect_receipt=stale)
    assert verdict["status"] == "PRECHECK_FAILED"
    assert verdict["mutation_performed"] is False
    assert fx.driver.compensated == []
    assert all(driver.calls == [] for driver in fx.row_drivers.values())


# ── C5:INSTALLED_UNIT probe receipt 的 probe_core_digest 比對 ─────────────────
def test_c5_a_probe_receipt_for_another_unit_is_rejected_when_the_expected_core_is_supplied(
    fx,
) -> None:
    verdict = fx.apply(
        expected_installed_unit_probe_core_digest="sha256:" + "e" * 64
    )
    assert verdict["status"] == "PRECHECK_FAILED"
    assert any("probe_core_digest is not the expected" in r for r in verdict["reasons"])
    assert all(driver.calls == [] for driver in fx.row_drivers.values())
    # 遞交正確值時照常放行(閘只在被指名時生效;未指名的殘餘由 obligation 記錄)。
    ok = fx.apply(
        expected_installed_unit_probe_core_digest=(
            fx.probe_receipts["INSTALLED_UNIT"]["probe_core_digest"]
        )
    )
    assert ok["status"] == "SOURCE_SIMULATION_PASS", ok["reasons"]


# ── C6:COMPENSATING 是 write-ahead 的 ─────────────────────────────────────────
def test_c6_an_uncommittable_compensating_record_compensates_nothing(
    tmp_path, monkeypatch
) -> None:
    """``COMPENSATING`` 沒能 durable commit → **一列都不補償**,typed RECOVERY_REQUIRED。

    過去它的回值被丟掉:短寫時 durable journal 裡沒有 COMPENSATING,五 row 卻已被破壞性補償,
    verdict 還記成乾淨的 ``POSTCHECK_FAILED_ROLLED_BACK``;若行程在此消失,WAL 的最後一筆是某
    row 的 ``VERIFYING``,重啟的 runner 會對一台被部分拆解的主機收斂出 ``RESUME_VERIFICATION``。
    """

    fixture = w4b.Fixture(tmp_path, monkeypatch, fs=w4b.CountingFs(fail_write_at=32))
    fixture.driver.postcheck_flags["plan_lineage_verified"] = False
    verdict = fixture.apply()
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert fixture.driver.compensated == []
    assert verdict["rollback"] is None
    assert any(
        "NO reverse compensation was attempted" in reason for reason in verdict["reasons"]
    )
    persisted = fixture.persisted_install_journal()
    assert "COMPENSATING" not in [entry["state"] for entry in persisted["entries"]]


# ── C7:ownership-aware 條件不再恆真 ───────────────────────────────────────────
def test_c7_the_ownership_aware_condition_is_actually_computed(fx) -> None:
    """``or isinstance(row_verdicts.get(name), dict)`` 對任何有 verdict 的 row 恆為真。

    而 row 只有產生 verdict 才可能進 ``applied_rows``,所以 §5.4 的 ownership-aware 條件
    從未被計算,production driver 永遠收到「ownership 已驗」。
    """

    seen: list[bool] = []
    original = fx.driver.compensate_component_row

    def _record(*, component_effect_class, plan_id, per_row_rollback_digest,
                ownership_verified):
        seen.append(ownership_verified)
        return original(
            component_effect_class=component_effect_class, plan_id=plan_id,
            per_row_rollback_digest=per_row_rollback_digest,
            ownership_verified=ownership_verified,
        )

    fx.driver.compensate_component_row = _record
    # LEARNING_RUNTIME 的 rollback artifact 被抽掉 ownership_aware → 該 row 的條件必為 False。
    fx.driver.postcheck_flags["plan_lineage_verified"] = False
    verdict = fx.apply()
    assert verdict["status"] in {"POSTCHECK_FAILED_ROLLED_BACK", "RECOVERY_REQUIRED"}
    # 每一列都有自己的 per-row rollback artifact,故此處全為 True(見下一支測試:把該
    # artifact 的 ownership_aware 拿掉,那一列就必須收到 False,而不是被 fallback 補成 True)。
    assert seen == [True] * len(runner.APPLY_ROW_ORDER)


def test_c7_a_row_without_a_rollback_artifact_is_not_ownership_verified(fx) -> None:
    seen: dict[str, bool] = {}
    original = fx.driver.compensate_component_row

    def _record(*, component_effect_class, plan_id, per_row_rollback_digest,
                ownership_verified):
        seen[component_effect_class] = ownership_verified
        return original(
            component_effect_class=component_effect_class, plan_id=plan_id,
            per_row_rollback_digest=per_row_rollback_digest,
            ownership_verified=ownership_verified,
        )

    fx.driver.compensate_component_row = _record
    fx.driver.postcheck_flags["plan_lineage_verified"] = False
    original_run_row = runner._run_row

    def _strip(name, **kwargs):
        verdict = original_run_row(name, **kwargs)
        if name == "CREDENTIAL_INSTALL" and isinstance(verdict.get("rollback"), dict):
            verdict["rollback"] = dict(verdict["rollback"])
            verdict["rollback"]["ownership_aware"] = False
        return verdict

    runner._run_row = _strip
    try:
        verdict = fx.apply()
    finally:
        runner._run_row = original_run_row
    assert seen["CREDENTIAL_INSTALL"] is False
    assert seen["ENGINE_SCANNER"] is True
    assert any(
        "no per-row rollback artifact declaring ownership_aware" in reason
        for reason in verdict["reasons"]
    )


# ── C9:未簽 permit 在 lock 之前即被拒 ──────────────────────────────────────────
def test_c9_an_unsigned_permit_never_reaches_the_install_lock(fx) -> None:
    """§6 固定「step 6 驗兩張 fresh SSHSIG → step 7 取 install lock」。

    過去第一次簽章驗證發生在 ``consume_authorizations_under_lock`` 內,也就是**取得 lock、
    跑完啟動 reconcile、讀完 ledger 之後**;一張未簽的 permit 因此能走到在主機上建立並 flock
    ``/run/lock/arcane-equilibrium-aiml-s2-4-install.lock``,verdict 還記 ``driver_engaged=True``。
    """

    forged = deepcopy(fx.authorization_set)
    permit = dict(forged["apply_aggregate"])
    permit["sshsig_armored"] = (
        "-----BEGIN SSH SIGNATURE-----\nAAAA\n-----END SSH SIGNATURE-----\n"
    )
    forged["apply_aggregate"] = permit
    verdict = fx.apply(authorization_set=forged)
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert verdict["driver_engaged"] is False
    assert verdict["mutation_performed"] is False
    assert any("before the install lock is created" in r for r in verdict["reasons"])
    # 零主機接觸:lock/file 面從未被要求。
    assert fx.driver.calls == []
    assert fx.lock_fake.calls == [] if hasattr(fx.lock_fake, "calls") else True


# ── C10:§10.5 #24 的成功閘必須在**真路徑**上被證明 ─────────────────────────────
def test_c10_the_success_gate_is_enforced_on_the_real_transaction_path(fx) -> None:
    """刪掉 ``_drive_rows`` 裡的成功閘分支,829+127 支測試全綠——因為它只被當純函式測過。

    此測讓一個 row 回「satisfied 但沒有 result/postcheck」,於是 ``row_results`` 缺一列,
    成功謂詞不滿足,而這件事**必須**在真交易上導致零 receipt + 逆序補償。
    """

    original_run_row = runner._run_row

    def _strip_result(name, **kwargs):
        verdict = original_run_row(name, **kwargs)
        if name == "CREDENTIAL_INSTALL":
            verdict = dict(verdict)
            verdict["result"] = None
            verdict["postcheck"] = None
        return verdict

    runner._run_row = _strip_result
    try:
        verdict = fx.apply()
    finally:
        runner._run_row = original_run_row
    assert verdict["receipt"] is None
    # 被抽掉 postcheck 的那一列因此也沒有補償**前**的獨立觀測 digest,§5.4 的 exactness 於是
    # typed 為未證(E4 修:``pre_compensation_observed_digest is None`` = 沒有約束**可證**,
    # 不是沒有約束),終端因而是 RECOVERY_REQUIRED 而非 POSTCHECK_FAILED_ROLLED_BACK。
    # 本測的載重主張不變:零 receipt + 五列全數逆序補償 + 成功閘的 typed 原因。
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert fx.driver.compensated == list(reversed(runner.APPLY_ROW_ORDER))
    assert any(
        "aggregate success requires all five distinct APPLY component results" in reason
        for reason in verdict["reasons"]
    )
    assert any(
        "no independent pre-compensation observation was captured" in reason
        for reason in verdict["reasons"]
    )


# ── C15:row payload 的 exact allowlist ────────────────────────────────────────
@pytest.mark.parametrize("key,value", [
    ("applier_node", "s2-4-install-verifier"),
    ("repo_root", "/tmp"),
    ("now", "2030-01-01T00:00:00+00:00"),
    ("clock", None),
    ("replay_ledger", {}),
    ("ownership_evidence", {}),
])
def test_c15_code_owned_row_abi_fields_can_never_be_supplied(fx, key, value) -> None:
    payloads = fx.row_payloads()
    payloads["PG_ROLE_ACL_MIGRATION"] = {**payloads["PG_ROLE_ACL_MIGRATION"], key: value}
    verdict = fx.apply(row_payloads=payloads)
    assert verdict["status"] == "PRECHECK_FAILED"
    assert any("outside the frozen row ABI allowlist" in r for r in verdict["reasons"])
    assert verdict["mutation_performed"] is False
    assert all(driver.calls == [] for driver in fx.row_drivers.values())


def test_c15_the_applier_node_is_code_owned_per_row(fx) -> None:
    verdict = fx.apply()
    assert verdict["status"] == "SOURCE_SIMULATION_PASS", verdict["reasons"]
    for name in runner.APPLY_ROW_ORDER:
        assert verdict["row_verdicts"][name]["postcheck"]["applier_node"] == (
            runner.ROW_APPLIER_NODES[name]
        )
        assert verdict["row_verdicts"][name]["postcheck"]["verifier_node"] != (
            runner.ROW_APPLIER_NODES[name]
        )


# ── C16:absent 不是成功;probe_unit_surviving 不再是無讀者的字面值 ──────────────
def test_c16_a_transaction_that_installed_nothing_is_never_a_terminal_success(fx) -> None:
    fx.driver.unit_state = "absent"
    verdict = fx.apply()
    assert verdict["receipt"] is None
    assert verdict["status"] in {"POSTCHECK_FAILED_ROLLED_BACK", "RECOVERY_REQUIRED"}
    assert any(
        "installed nothing and can never be a terminal success" in r
        for r in verdict["reasons"]
    )


def test_c16_the_success_path_requires_a_positive_loaded_observation(fx) -> None:
    fx.driver.unit_state = {"loaded": False, "disabled": True, "inactive": True}
    verdict = fx.apply()
    assert verdict["receipt"] is None
    assert any("OBSERVED loaded, disabled and inactive" in r for r in verdict["reasons"])


def test_c16_residue_no_longer_presents_a_write_only_probe_flag(fx) -> None:
    verdict = fx.apply()
    assert "probe_unit_surviving" not in verdict["residue"]
    assert verdict["residue"]["probe_residue_evidence"] == (
        "terminal_probe_receipt_zero_residue_verified"
    )
    assert verdict["residue"]["observation_status"] == "INSTALLED_UNIT_OBSERVED_INACTIVE"


# ── C17:五個相異 postcheck ────────────────────────────────────────────────────
def test_c17_five_rows_sharing_one_postcheck_digest_do_not_satisfy_the_aggregate() -> None:
    shared = "sha256:" + "c" * 64
    results = {
        name: ("sha256:" + str(index) * 64, shared)
        for index, name in enumerate(runner.APPLY_ROW_ORDER)
    }
    verdict = runner.derive_aggregate_success_status(
        probe_receipt_digests={
            "PREPARE_SANDBOX": "sha256:" + "a" * 64,
            "INSTALLED_UNIT": "sha256:" + "b" * 64,
        },
        prepare_result_digest="sha256:" + "d" * 64,
        row_results=results,
    )
    assert verdict["status"] == "AGGREGATE_SUCCESS_NOT_SATISFIED"
    assert any("postcheck_digest duplicates" in reason for reason in verdict["reasons"])


# ── C18:permit 新鮮度不由 caller 的時鐘決定 ────────────────────────────────────
def test_c18_the_trusted_host_time_is_cross_checked_against_the_observed_time(fx) -> None:
    fx.driver.trusted_time = "2030-01-01T00:00:00+00:00"
    verdict = fx.apply()
    assert verdict["receipt"] is None
    assert verdict["status"] == "RECEIPT_EMISSION_PENDING"
    assert any("§9.1 clock skew ceiling" in r for r in verdict["reasons"])


# ── C19/C20:durable 證據集 ────────────────────────────────────────────────────
def test_c20_the_step_results_and_rollback_are_durably_persisted(fx) -> None:
    """失敗之後,「五列裡哪幾列施作過」必須是 durable 事實,而不是記憶體裡的 verdict 欄位。"""

    fx.driver.postcheck_flags["plan_lineage_verified"] = False
    verdict = fx.apply()
    assert verdict["evidence_set"]["status"] == "INSTALL_EVIDENCE_SET_COMMITTED"
    basename = evidence_leaf.install_evidence_set_path(
        fx.plan["plan_id"]
    ).rsplit("/", 1)[-1]
    import json as _json

    persisted = _json.loads(fx.fs.files[basename].decode("utf-8"))
    assert persisted["schema_version"] == "s2_4_install_evidence_set_v1_informal"
    assert persisted["applied_rows"] == list(runner.APPLY_ROW_ORDER)
    assert [step["component_effect_class"] for step in persisted["step_results"]] == list(
        runner.APPLY_ROW_ORDER
    )
    assert persisted["rollback"]["schema_version"] == "s2_4_install_rollback_v1"
    assert persisted["journal_digest"] == verdict["journal"]["self_digest"]
    # C19:§5.2 的三件證據(終端 journal + 獨立殘留觀測 + 啟動 reconcile 裁決)一起被綁住。
    assert persisted["startup_reconcile_status"] == verdict["reconcile"]["status"]
    assert persisted["startup_reconcile_digest"] == validator.canonical_digest(
        verdict["reconcile"]
    )
    assert persisted["residue_digest"] == validator.canonical_digest(verdict["residue"])
    assert persisted["installed_unit_observation_status"] == (
        verdict["residue"]["observation_status"]
    )


def test_c20_the_success_path_evidence_set_binds_the_receipt(fx) -> None:
    verdict = fx.apply()
    assert verdict["status"] == "SOURCE_SIMULATION_PASS", verdict["reasons"]
    basename = evidence_leaf.install_evidence_set_path(
        fx.plan["plan_id"]
    ).rsplit("/", 1)[-1]
    import json as _json

    persisted = _json.loads(fx.fs.files[basename].decode("utf-8"))
    assert persisted["effect_receipt_digest"] == verdict["receipt"]["self_digest"]
    assert persisted["terminal_status"] == "SOURCE_SIMULATION_PASS"


# ── C22:plan 的 pre-state 投影不是一個 row-independent 常量 ────────────────────
def test_c22_the_plan_pre_state_projection_is_row_dependent(fx) -> None:
    """把 ``derive_plan_pre_state_projection`` 換成 row-independent 常量,零測試轉紅。

    因為 ``derive_aggregate_input_status`` 用同一支函式再導出,``build_s2_4_install_plan``
    也用它建。此處以**獨立寫出**的期望值取證,並證明任一 row 的 pre-state 被換掉即改變
    ``core["pre_state_digest"]``。
    """

    expected = validator.canonical_digest({
        "domain": "arcane-equilibrium-aiml-s2-4-plan-pre-state-projection-v1",
        "rows": [
            {
                "component_effect_class": name,
                "pre_state_digest": fx.component_intents[name]["pre_state_digest"],
            }
            for name in [
                "HOST_IDENTITY_INSTALL", "PG_ROLE_ACL_MIGRATION", "CREDENTIAL_INSTALL",
                "LEARNING_RUNTIME", "ENGINE_SCANNER",
            ]
        ],
    })
    assert fx.plan["core"]["pre_state_digest"] == expected
    for name in runner.APPLY_ROW_ORDER:
        mutated = dict(fx.component_intents)
        mutated[name] = {
            **fx.component_intents[name], "pre_state_digest": "sha256:" + "9" * 64
        }
        assert runner.derive_plan_pre_state_projection(mutated) != expected


# ── C23:§5.3 列 5 的 COMPENSATE lane 也要在 aggregate 級被證明 ─────────────────
def test_c23_a_task_owned_partial_reconcile_lane_blocks_the_aggregate_fail_closed(
    fx,
) -> None:
    """``STARTUP_RECONCILE_COMPENSATE_REVERSE`` 經 ``apply_s2_4_install_plan`` 可達且 fail-closed。

    它過去只被當純函式測過;此測走真進入點,並釘住「aggregate **自己不補償**」這個誠實面。
    """

    crash = w4b.CrashingClock("HOST_IDENTITY_INSTALL:post_effect_pre_observation")
    with pytest.raises(journal.JournalCrash):
        fx.apply(fault=crash)
    persisted = fx.persisted_install_journal()
    verdict = fx.apply(
        startup_observed_state_digests={"install": "sha256:" + "9" * 64},
        startup_task_owned_partials={"install": True},
        ownership_evidence={
            "install": {
                "journal_subject": {
                    "s2_4_receipt_digest": "sha256:" + "1" * 64,
                    "journal_digest": persisted["self_digest"],
                }
            }
        },
    )
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert verdict["reconcile"]["status"] == "STARTUP_RECONCILE_COMPENSATE_REVERSE_ORDER"
    assert verdict["reconcile"]["mutation_performed"] is False
    assert any(
        "does NOT itself run the §5.4 reverse compensation" in reason
        for reason in verdict["reasons"]
    )
    assert fx.driver.compensated == []
