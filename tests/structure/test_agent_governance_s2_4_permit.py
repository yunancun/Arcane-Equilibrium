"""S2.4(WP4·W4a)PERMIT_PLAN_BINDING 與 §9 時間/授權預算的 focused 測試(§10.5 #10/#36)。

證明:

- ``authorization_id`` 由 profile 具名的 exact payload **導出**,且每個消費閘再導出比對:
  一張簽好的 permit 無法在 TTL 內授權另一個 intent(**intent-substitution attack**);
- W3 形的舊 permit(只有 payload_fields 的**名字**、沒有 payload_binding)一律被拒——包含
  原封不動的 W3 fixture 形狀;
- probe / PREPARE / APPLY-row 三個消費閘各自從 intent 獨立再導出期望 payload,並在 driver
  接觸之前 typed ``AUTHORIZATION_REJECTED``;
- §9 三條不等式(APPLY / PREPARE / PROBE)雙向再導出,term/bound 鍵集為 exact set
  (缺項即 typed 拒——少一項就等於偷偷放寬不等式),且 3600 秒操作不能在 900 秒 permit 下跑;
- §10.5 #10:過期禁止新建立/恢復觀測,但**不得**阻擋安全清理;過期永不把部分 apply 變成成功。

時間全部錨在凍結常量上(無 wall clock,故無日期腐化)。
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
for candidate in (HELPERS, ML_ROOT, PROGRAM_CODE):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_4_apply as apply_mod  # noqa: E402
import agent_governance_s2_4_component as component  # noqa: E402
import agent_governance_s2_4_permit as permit  # noqa: E402
import agent_governance_s2_4_prepare as prepare  # noqa: E402
import agent_governance_s2_4_probe as probe  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
import s2_4_w3b_testkit as kit  # noqa: E402


# ── PERMIT_PLAN_BINDING:id 由 payload 導出 ─────────────────────────────────────
def test_payload_binding_field_set_is_the_profile_payload_minus_the_self_reference() -> None:
    for key, profile in validator.S2_4_AUTHORIZATION_PROFILES.items():
        fields = validator.authorization_payload_binding_fields(key)
        assert set(fields) == set(profile["payload_fields"]) - {"authorization_id"}
        assert "authorization_id" not in fields
        # profile_identity 亦可解析(consumer 側常只有身分字串)。
        assert validator.authorization_payload_binding_fields(
            profile["profile_identity"]
        ) == fields
    with pytest.raises(ValueError):
        validator.authorization_payload_binding_fields("not-a-profile")


def test_authorization_id_is_a_deterministic_derivation_over_the_named_payload() -> None:
    binding = kit.apply_payload_binding("apply_aggregate")
    permit_artifact = validator.build_s2_4_operator_authorization(
        "apply_aggregate", payload_binding=binding,
        issued_at=kit.ISSUED, expires_at=kit.EXPIRES,
    )
    assert permit_artifact["authorization_id"] == validator.derive_authorization_id(
        permit_artifact
    )
    # domain separation:同一組值在別的 profile 下得到不同的 id。
    assert validator.s2_4_authorization_identity_digest(
        profile_identity="aiml-s2-install-operator-v1",
        signature_namespace="arcane-equilibrium-aiml-s2-install",
        payload_fields=list(permit_artifact["payload_fields"]),
        payload_binding=binding,
    ) != validator.s2_4_authorization_identity_digest(
        profile_identity="aiml-s2-pg-migration-operator-v1",
        signature_namespace="arcane-equilibrium-aiml-s2-pg-migration",
        payload_fields=list(permit_artifact["payload_fields"]),
        payload_binding=binding,
    )
    # 任一 payload 值改動 → 不同的 id(permit 不可被重新指向另一份 plan)。
    other = dict(binding, plan_core_digest="sha256:" + "9" * 64)
    assert validator.s2_4_authorization_identity_digest(
        profile_identity=permit_artifact["profile_identity"],
        signature_namespace=permit_artifact["signature_namespace"],
        payload_fields=list(permit_artifact["payload_fields"]),
        payload_binding=other,
    ) != permit_artifact["authorization_id"]


def test_build_refuses_a_payload_binding_that_is_not_the_exact_profile_payload() -> None:
    binding = kit.apply_payload_binding("apply_aggregate")
    binding.pop("hba_delta_digest")
    with pytest.raises(ValueError):
        validator.build_s2_4_operator_authorization(
            "apply_aggregate", payload_binding=binding,
            issued_at=kit.ISSUED, expires_at=kit.EXPIRES,
        )


def test_the_central_gate_rejects_a_permit_whose_id_does_not_rederive(
    tmp_path, monkeypatch
) -> None:
    private_key, public_key, fingerprint = kit.mint_key(tmp_path)
    kit.install_pinned_key(monkeypatch, public_key, fingerprint)
    forged = kit.authorization(
        private_key, profile_key="apply_aggregate",
        payload_binding=kit.apply_payload_binding("apply_aggregate"),
        authorization_id="sha256:" + "a" * 64,   # 手寫 id:與其 payload 無關
    )
    errors = validator._s2_4_operator_authorization_errors(forged, now=kit.NOW)
    assert any("does not re-derive from its own" in error for error in errors)
    assert validator.validate_aiml_artifact(forged, now=kit.NOW)


@pytest.mark.parametrize(
    "mutation,marker",
    [
        ({"domain": "arcane-equilibrium-aiml-s2-pg-migration"}, "signature namespace"),
        ({"issued_at": "2030-01-01T00:05:00+00:00"}, "top-level authorization field"),
        ({"expires_at": "2030-01-01T00:20:00+00:00"}, "top-level authorization field"),
        ({"plan_core_digest": None}, "must not be null"),
    ],
)
def test_payload_binding_internal_coherence_is_load_bearing(
    tmp_path, monkeypatch, mutation, marker
) -> None:
    private_key, public_key, fingerprint = kit.mint_key(tmp_path)
    kit.install_pinned_key(monkeypatch, public_key, fingerprint)
    binding = kit.apply_payload_binding("apply_aggregate")
    binding.update(mutation)
    forged = kit.authorization(
        private_key, profile_key="apply_aggregate", payload_binding=binding
    )
    errors = validator._s2_4_operator_authorization_errors(forged, now=kit.NOW)
    assert any(marker in error for error in errors), errors


def test_a_w3_shaped_permit_without_payload_binding_fails_the_closed_schema(
    tmp_path, monkeypatch
) -> None:
    """W3 fixture 形狀(只有 payload_fields 的名字)在 W4a 之後必被拒。"""

    private_key, public_key, fingerprint = kit.mint_key(tmp_path)
    kit.install_pinned_key(monkeypatch, public_key, fingerprint)
    signed = kit.authorization(
        private_key, profile_key="apply_aggregate",
        payload_binding=kit.apply_payload_binding("apply_aggregate"),
    )
    legacy = {key: value for key, value in signed.items() if key != "payload_binding"}
    legacy["self_digest"] = validator.artifact_self_digest(legacy)
    schema_errors = validator.validate_aiml_artifact(legacy, now=kit.NOW)
    assert any("payload_binding" in error for error in schema_errors), schema_errors
    binding_errors = validator._s2_4_operator_authorization_errors(legacy, now=kit.NOW)
    assert any("authorizes any intent of its class" in error for error in binding_errors)


def test_derive_permit_plan_binding_refuses_an_empty_expectation(tmp_path, monkeypatch) -> None:
    private_key, public_key, fingerprint = kit.mint_key(tmp_path)
    kit.install_pinned_key(monkeypatch, public_key, fingerprint)
    signed = kit.authorization(
        private_key, profile_key="apply_aggregate",
        payload_binding=kit.apply_payload_binding("apply_aggregate"),
    )
    verdict = validator.derive_permit_plan_binding_status(
        signed, expected_payload_binding={}, profile_key="apply_aggregate"
    )
    assert verdict["status"] == "PERMIT_PLAN_BINDING_REJECTED"
    assert any("would authorize any intent" in reason for reason in verdict["reasons"])


# ── intent-substitution attack:probe ───────────────────────────────────────────
def _probe_intent(target_host="trade-core"):
    core = probe.build_capability_probe_core(
        scope="PREPARE_SANDBOX", host=kit.HOST, cgroup_manager_scope="system_manager",
        cgroup_root_pattern=kit.CGROUP_ROOT, source_head=kit.SOURCE_HEAD,
        target_host=target_host, created_at=kit.ISSUED, max_cleanup_seconds=30,
        max_cgroup_drain_seconds=10, artifact_mirror_allowlist=list(kit.MIRROR),
    )
    return probe.build_capability_probe_intent(
        core, expires_at=kit.EXPIRES, max_ttl_seconds=600
    )


class _CountingProbeDriver(kit._ProbeDriver):
    """任一次主機接觸都記錄下來(用於證明拒絕發生在 driver 之前)。"""

    def __init__(self, property_digest):
        super().__init__(property_digest)
        self.host_calls: list[str] = []

    def start_transient_unit(self, **kwargs):
        self.host_calls.append("start_transient_unit")
        return super().start_transient_unit(**kwargs)


def test_probe_permit_is_bound_to_one_intent_and_an_intent_substitution_is_rejected(
    tmp_path, monkeypatch
) -> None:
    """§10.5 #36:一張為 intent A 簽的 probe permit 不得授權 intent B。"""

    private_key, public_key, fingerprint = kit.mint_key(tmp_path)
    kit.install_pinned_key(monkeypatch, public_key, fingerprint)
    intent_a = _probe_intent()
    intent_b = _probe_intent(target_host="other-host")
    assert intent_a["probe_id"] != intent_b["probe_id"]
    permit_a = kit.authorization(
        private_key, profile_key="capability_probe",
        payload_binding=probe.probe_permit_payload_binding(
            intent_a, artifact_mirror_allowlist=list(kit.MIRROR)
        ),
    )
    driver = _CountingProbeDriver(intent_b["core"]["transient_unit_property_digest"])
    verdict = probe.run_s2_4_capability_probe(
        intent_b, permit_a, driver, now=kit.NOW, clock=kit.frozen_clock(),
        replay_ledger=kit.replay_ledger(), artifact_mirror_allowlist=list(kit.MIRROR),
    )
    assert verdict["status"] == "AUTHORIZATION_REJECTED", verdict["reasons"]
    assert verdict["mutation_performed"] is False
    assert verdict["driver_engaged"] is False
    assert driver.host_calls == []
    assert any("intent substitution" in reason for reason in verdict["reasons"])
    # 同一張 permit 對它自己的 intent 仍然成立(不是把整條路封死)。
    clean = probe.run_s2_4_capability_probe(
        intent_a, permit_a,
        kit._ProbeDriver(intent_a["core"]["transient_unit_property_digest"]),
        now=kit.NOW, clock=kit.frozen_clock(), replay_ledger=kit.replay_ledger(),
        artifact_mirror_allowlist=list(kit.MIRROR),
    )
    assert clean["status"] == "TERMINAL_CLEAN", clean["reasons"]


def test_probe_permit_payload_binding_covers_every_named_payload_field() -> None:
    intent = _probe_intent()
    binding = probe.probe_permit_payload_binding(
        intent, artifact_mirror_allowlist=list(kit.MIRROR)
    )
    named = set(validator.authorization_payload_binding_fields("capability_probe"))
    # 消費閘導出的是它能獨立再導出的部分;permit 自身的窗(issued/expires)不在其中。
    assert set(binding) == named - {"issued_at", "expires_at"}
    assert binding["probe_core_digest"] == intent["core_digest"]
    assert binding["probe_id"] == intent["probe_id"]
    assert binding["scope"] == "PREPARE_SANDBOX"
    assert binding["output_derived_unit_digest_or_null"] is None


# ── intent-substitution attack:PREPARE ─────────────────────────────────────────
def test_prepare_permit_is_bound_to_one_prepare_core(tmp_path, monkeypatch) -> None:
    from test_agent_governance_s2_4_prepare import _FakePrepareDriver, _intent as _p_intent

    private_key, public_key, fingerprint = kit.mint_key(tmp_path)
    kit.install_pinned_key(monkeypatch, public_key, fingerprint)
    evidence = kit.terminal_probe_evidence(private_key)
    receipt_digest = evidence["PREPARE_SANDBOX"]["effect_receipt"]["self_digest"]
    intent_a = _p_intent(receipt_digest)
    # 另一份 prepare core(不同 staging parent device → 不同 core digest/prepare_id)。
    other_core = prepare.build_prepare_core(
        staging_parent_device=999_999, staging_parent_inode=909_090,
        max_bytes=2_000_000_000, max_seconds=1800, max_fetch_bytes=800_000_000,
        max_fetch_seconds=600, max_artifacts=64, max_build_bytes=1_500_000_000,
        max_build_seconds=900, source_head=kit.SOURCE_HEAD, target_host=kit.HOST,
        created_at=kit.ISSUED,
    )
    intent_b = prepare.build_prepare_intent(
        other_core,
        source_compatibility_receipt_digest="sha256:" + "1" * 64,
        sealed_build_receipt_digest="sha256:" + "2" * 64,
        identity_contract_digest="sha256:" + "3" * 64,
        application_manifest_digest="sha256:" + "d" * 64,
        prepare_sandbox_probe_receipt_digest=receipt_digest,
        expires_at=kit.EXPIRES, max_ttl_seconds=600,
    )
    assert intent_a["prepare_id"] != intent_b["prepare_id"]
    permit_a = kit.authorization(
        private_key, profile_key="prepare",
        payload_binding=prepare.prepare_permit_payload_binding(intent_a),
    )
    driver = _FakePrepareDriver()
    verdict = prepare.prepare_s2_4_install_bundle(
        intent_b, permit_a, driver, now=kit.NOW, clock=kit.frozen_clock(),
        replay_ledger=kit.replay_ledger(), probe_evidence=evidence,
    )
    assert verdict["status"] == "AUTHORIZATION_REJECTED", verdict["reasons"]
    assert verdict["mutation_performed"] is False
    assert driver.calls == []


def test_prepare_rollback_contract_digest_is_derivable_before_the_run() -> None:
    """§5.1:被簽的 ``prepare_rollback_digest`` 必須在跑之前就能算出來。"""

    prepare_id = "s2-4-prepare-" + "a" * 64
    staging_root = prepare.prepared_staging_root(prepare_id)
    contract = prepare.prepare_rollback_contract(
        prepare_id=prepare_id, staging_root=staging_root
    )
    assert contract["task_owned_only"] is True
    assert contract["authorized_after_apply_authority_expiry"] is True
    assert contract["journal_path"] == prepare.prepare_journal_path(prepare_id)
    assert prepare.prepare_rollback_contract_digest(
        prepare_id=prepare_id, staging_root=staging_root
    ) == validator.canonical_digest(contract)


# ── intent-substitution attack:APPLY row ───────────────────────────────────────
def test_apply_row_permit_is_bound_to_the_plan_the_intent_references(
    tmp_path, monkeypatch
) -> None:
    signed = kit.signed_authorizations(tmp_path, monkeypatch)
    manifest = apply_mod.build_uid_gid_directory_manifest(uid=kit.UID, gid=kit.GID)
    other_plan_intent = apply_mod.build_component_effect_intent(
        component_effect_class="HOST_IDENTITY_INSTALL",
        install_plan_digest="sha256:" + "7" * 64,     # 另一份 plan
        pre_state_digest=kit.PRE_STATE,
        required_intent_fields={
            "uid_gid_directory_manifest_digest": validator.canonical_digest(manifest)
        },
        expires_at=kit.EXPIRES,
    )
    reasons = component._authorization_set_reasons(
        {"apply_aggregate": signed["apply_aggregate"]}, kit.replay_ledger(),
        component_effect_class="HOST_IDENTITY_INSTALL", now=kit.NOW,
        intent=other_plan_intent,
    )
    assert any("intent substitution" in reason for reason in reasons), reasons
    # 綁對的 plan 則過。
    own_plan_intent = apply_mod.build_component_effect_intent(
        component_effect_class="HOST_IDENTITY_INSTALL",
        install_plan_digest=kit.PLAN_DIGEST, pre_state_digest=kit.PRE_STATE,
        required_intent_fields={
            "uid_gid_directory_manifest_digest": validator.canonical_digest(manifest)
        },
        expires_at=kit.EXPIRES,
    )
    assert component._authorization_set_reasons(
        {"apply_aggregate": signed["apply_aggregate"]}, kit.replay_ledger(),
        component_effect_class="HOST_IDENTITY_INSTALL", now=kit.NOW,
        intent=own_plan_intent,
    ) == []


def test_apply_permit_internal_plan_id_and_idempotency_key_derivations(
    tmp_path, monkeypatch
) -> None:
    private_key, public_key, fingerprint = kit.mint_key(tmp_path)
    kit.install_pinned_key(monkeypatch, public_key, fingerprint)
    drifted = kit.apply_payload_binding("apply_aggregate", plan_id="s2-4-" + "0" * 64)
    signed = kit.authorization(
        private_key, profile_key="apply_aggregate", payload_binding=drifted
    )
    reasons = component._apply_permit_internal_derivation_reasons(
        {"apply_aggregate": signed}, ("apply_aggregate",)
    )
    assert any("does not re-derive from its bound plan_core_digest" in r for r in reasons)
    assert any("idempotency_key is not the bound plan_id" in r for r in reasons)


def test_the_aggregate_and_pg_permits_must_bind_the_same_plan_lineage(
    tmp_path, monkeypatch
) -> None:
    private_key, public_key, fingerprint = kit.mint_key(tmp_path)
    kit.install_pinned_key(monkeypatch, public_key, fingerprint)
    aggregate = kit.authorization(
        private_key, profile_key="apply_aggregate",
        payload_binding=kit.apply_payload_binding("apply_aggregate"),
    )
    pg = kit.authorization(
        private_key, profile_key="pg_migration",
        payload_binding=kit.apply_payload_binding(
            "pg_migration", hba_delta_digest="sha256:" + "f" * 64
        ),
    )
    reasons = component._apply_permit_internal_derivation_reasons(
        {"apply_aggregate": aggregate, "pg_migration": pg},
        ("apply_aggregate", "pg_migration"),
    )
    assert any("different plan lineages" in reason for reason in reasons), reasons


def test_apply_permit_payload_binding_refuses_a_non_digest_plan_reference() -> None:
    with pytest.raises(component.ComponentContractError):
        component.apply_permit_payload_binding(
            {"install_plan_digest": "/srv/worker-chosen"}, profile_key="apply_aggregate"
        )


# ── §9 三條 TTL 不等式 ─────────────────────────────────────────────────────────
def test_the_three_budget_phases_have_the_exact_declared_terms() -> None:
    assert permit.APPLY_TTL_BUDGET_TERMS == (
        "apply_budget", "postcheck_duration", "postcheck_sample_interval",
        "rollback_budget", "safety_margin",
    )
    assert set(permit.APPLY_TTL_BOUND_TERMS) == {
        "install_intent_remaining_ttl", "operator_authorization_remaining_ttl",
        "pg_migration_authorization_remaining_ttl", "topology_attestation_remaining_ttl",
        "installed_unit_probe_receipt_remaining_ttl", "prepared_bundle_remaining_ttl",
        "dependency_effect_receipt_remaining_ttl",
    }
    # §9:PREPARE 不依賴 final unit / PG topology / HBA delta / W6B permit。
    assert not any(
        token in " ".join(permit.PREPARE_TTL_BOUND_TERMS)
        for token in ("topology", "hba", "installed_unit", "pg_migration")
    )
    assert permit.PROBE_TTL_BOUND_TERMS == ("probe_authorization_remaining_ttl",)


def test_a_3600_second_operation_cannot_run_under_a_900_second_permit() -> None:
    verdict = permit.derive_ttl_budget_status(
        "APPLY",
        budget={
            "apply_budget": 3600, "postcheck_duration": 0, "postcheck_sample_interval": 0,
            "rollback_budget": 0, "safety_margin": 0,
        },
        remaining_ttls={term: 900 for term in permit.APPLY_TTL_BOUND_TERMS},
    )
    assert verdict["status"] == "TTL_BUDGET_EXCEEDED"
    assert verdict["required_seconds"] == 3600 and verdict["available_seconds"] == 900


def test_the_inequality_binds_on_the_smallest_remaining_ttl() -> None:
    remaining = {term: 900 for term in permit.APPLY_TTL_BOUND_TERMS}
    remaining["prepared_bundle_remaining_ttl"] = 125
    verdict = permit.derive_ttl_budget_status(
        "APPLY",
        budget={
            "apply_budget": 60, "postcheck_duration": 30, "postcheck_sample_interval": 5,
            "rollback_budget": 20, "safety_margin": 10,
        },
        remaining_ttls=remaining,
    )
    # 總和恰為 125 秒 == binding evidence 的剩餘;``<=`` 成立。
    assert verdict["status"] == "TTL_BUDGET_SATISFIED"
    assert verdict["required_seconds"] == 125
    assert verdict["binding_evidence"] == "prepared_bundle_remaining_ttl"
    tight = permit.derive_ttl_budget_status(
        "APPLY",
        budget={
            "apply_budget": 60, "postcheck_duration": 30, "postcheck_sample_interval": 6,
            "rollback_budget": 20, "safety_margin": 10,
        },
        remaining_ttls=remaining,
    )
    assert tight["status"] == "TTL_BUDGET_EXCEEDED"
    assert tight["binding_evidence"] == "prepared_bundle_remaining_ttl"


@pytest.mark.parametrize("phase", ["APPLY", "PREPARE", "PROBE"])
def test_every_phase_rejects_a_missing_or_extra_term(phase) -> None:
    budget_terms, bound_terms = permit.TTL_PHASES[phase]
    full_budget = {term: 1 for term in budget_terms}
    full_bounds = {term: 900 for term in bound_terms}
    assert permit.derive_ttl_budget_status(
        phase, budget=full_budget, remaining_ttls=full_bounds
    )["status"] == "TTL_BUDGET_SATISFIED"
    for drop in budget_terms:
        partial = {term: 1 for term in budget_terms if term != drop}
        verdict = permit.derive_ttl_budget_status(
            phase, budget=partial, remaining_ttls=full_bounds
        )
        assert verdict["status"] == "TTL_BUDGET_REJECTED"
        assert any("silently loosens" in reason for reason in verdict["reasons"])
    extra = dict(full_budget, sneaky_term=1)
    assert permit.derive_ttl_budget_status(
        phase, budget=extra, remaining_ttls=full_bounds
    )["status"] == "TTL_BUDGET_REJECTED"
    for drop in bound_terms:
        partial_bounds = {term: 900 for term in bound_terms if term != drop}
        assert permit.derive_ttl_budget_status(
            phase, budget=full_budget, remaining_ttls=partial_bounds
        )["status"] == "TTL_BUDGET_REJECTED"


@pytest.mark.parametrize("bad", [-1, "60", True, float("inf"), float("nan"), None])
def test_non_numeric_or_negative_budget_terms_are_rejected(bad) -> None:
    budget = {term: 1 for term in permit.APPLY_TTL_BUDGET_TERMS}
    budget["safety_margin"] = bad
    verdict = permit.derive_ttl_budget_status(
        "APPLY", budget=budget,
        remaining_ttls={term: 900 for term in permit.APPLY_TTL_BOUND_TERMS},
    )
    assert verdict["status"] == "TTL_BUDGET_REJECTED"


def test_an_unknown_phase_is_fail_closed() -> None:
    assert permit.derive_ttl_budget_status(
        "W6C", budget={}, remaining_ttls={}
    )["status"] == "TTL_BUDGET_REJECTED"


def test_permit_ttl_ceiling_is_900_seconds(tmp_path, monkeypatch) -> None:
    private_key, public_key, fingerprint = kit.mint_key(tmp_path)
    kit.install_pinned_key(monkeypatch, public_key, fingerprint)
    ok = kit.authorization(
        private_key, profile_key="apply_aggregate",
        payload_binding=kit.apply_payload_binding("apply_aggregate"),
    )
    assert permit.derive_permit_ttl_ceiling_status(ok)["status"] == "TTL_BUDGET_SATISFIED"
    over = deepcopy(ok)
    over["expires_at"] = "2030-01-01T00:16:00+00:00"
    assert permit.derive_permit_ttl_ceiling_status(over)["status"] == "TTL_BUDGET_EXCEEDED"
    assert permit.MAX_PERMIT_TTL_SECONDS == 900
    assert permit.PERMIT_CLOCK_SKEW_SECONDS == 60


# ── §10.5 #10:過期後只剩安全清理 ───────────────────────────────────────────────
@pytest.mark.parametrize("operation", permit.POST_EXPIRY_SAFETY_OPERATIONS)
def test_expiry_never_blocks_the_exact_safety_cleanup(operation) -> None:
    assert permit.derive_post_expiry_operation_status(
        operation=operation, permit_expired=True
    )["status"] == "POST_EXPIRY_SAFETY_CLEANUP_AUTHORIZED"
    assert permit.derive_post_expiry_operation_status(
        operation=operation, permit_expired=False
    )["status"] == "OPERATION_AUTHORIZED"


@pytest.mark.parametrize("operation", permit.POST_EXPIRY_FORBIDDEN_OPERATIONS)
def test_expiry_forbids_new_creation_publication_and_resumption(operation) -> None:
    assert permit.derive_post_expiry_operation_status(
        operation=operation, permit_expired=True
    )["status"] == "POST_EXPIRY_OPERATION_FORBIDDEN"


def test_an_unknown_operation_name_is_fail_closed() -> None:
    assert permit.derive_post_expiry_operation_status(
        operation="brand_new_effect", permit_expired=True
    )["status"] == "UNKNOWN_OPERATION_FORBIDDEN"
    assert permit.derive_post_expiry_operation_status(
        operation="brand_new_effect", permit_expired=False
    )["status"] == "UNKNOWN_OPERATION_FORBIDDEN"


def test_expiry_during_apply_triggers_compensation_and_never_success() -> None:
    live = permit.derive_expiry_during_apply_status(
        permit_expires_at=kit.EXPIRES, observed_now=kit.NOW, mutation_performed=True
    )
    assert live["status"] == "PERMIT_LIVE" and live["apply_may_resume"] is True
    expired = permit.derive_expiry_during_apply_status(
        permit_expires_at=kit.ISSUED, observed_now=kit.NOW, mutation_performed=True
    )
    assert expired["status"] == "EXPIRY_DURING_APPLY_COMPENSATE"
    assert expired["apply_may_resume"] is False
    assert expired["safety_cleanup_authorized"] is True
    assert expired["converts_partial_apply_to_success"] is False
    stranded = permit.derive_expiry_during_apply_status(
        permit_expires_at=kit.ISSUED, observed_now=kit.NOW, mutation_performed=True,
        compensation_available=False,
    )
    assert stranded["status"] == "RECOVERY_REQUIRED"
    assert stranded["safety_cleanup_authorized"] is True


def test_expiry_during_apply_is_fail_closed_on_an_unparseable_clock() -> None:
    assert permit.derive_expiry_during_apply_status(
        permit_expires_at="not-a-time", observed_now=kit.NOW, mutation_performed=True
    )["status"] == "RECOVERY_REQUIRED"
    assert permit.derive_expiry_during_apply_status(
        permit_expires_at=kit.EXPIRES, observed_now=7, mutation_performed=False
    )["status"] == "RECOVERY_REQUIRED"


def test_permit_projection_is_stable_and_claims_no_production() -> None:
    projection = permit.permit_abi_projection()
    assert projection["max_permit_ttl_seconds"] == 900
    assert set(projection["post_expiry_safety_operations"]) == set(
        permit.POST_EXPIRY_SAFETY_OPERATIONS
    )
    assert "TTL_BUDGET_EXCEEDED" in projection["ttl_typed_statuses"]
