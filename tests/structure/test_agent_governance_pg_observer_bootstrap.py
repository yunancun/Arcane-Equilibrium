"""Always-run offline/structural tests for the S2.0 observer-bootstrap SOURCE Adapter.

These need NO PostgreSQL: they exercise the structured-SQL allowlist (fail-closed
rejection of any over-grant / raw SQL), the intent/pending-result/postcheck/rollback
build+validate round-trips and forgeries, the operator-SSHSIG domain separation
(reusing a throwaway test key + monkeypatch), the central-validator delegation, and
the guardrails the task pins: the frozen classifier digest stays byte-unchanged and
PROGRAM_SCHEMA_PATHS is untouched.  The REAL apply/rollback/denial-SQLSTATE proofs
live in the disposable-cluster sibling; production apply is fail-closed here.
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_pg_observer_bootstrap as obs  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402

HEAD = "0123456789abcdef0123456789abcdef01234567"
OTHER_HEAD = "fedcba9876543210fedcba9876543210fedcba98"
CREATED = "2026-07-24T12:00:00+00:00"
NOW = "2026-07-24T12:01:00+00:00"
LATER = "2026-07-24T12:02:00+00:00"
FROZEN_CLASSIFIER = (
    "sha256:1cf8c021b066ceeb364e968add074d263cb28d63db421fdc40620e9904d0ddbc"
)


def _intent(target_class="disposable_local", **overrides):
    kwargs = dict(
        target_class=target_class, target_host="trade-core", database="openclaw",
        observer_role="aiml_observer_ro", observed_schema="trading",
        observed_relations=["fills", "orders"], socket_dir="/var/run/postgresql",
        auth_mapping="pg_hba_ident_local", applier_node_id="observer_apply_actor",
        postcheck_node_id="observer_ops_postcheck", created_at=CREATED,
        ttl_seconds=900, source_head=HEAD,
    )
    kwargs.update(overrides)
    return obs.build_pg_observer_bootstrap_intent(**kwargs)


def _install_operator_profile(tmp_path, monkeypatch):
    private_key = tmp_path / "operator"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)], check=True
    )
    parts = private_key.with_suffix(".pub").read_text(encoding="ascii").split()
    public_key = " ".join(parts[:2])
    fingerprint = subprocess.run(
        ["ssh-keygen", "-lf", str(private_key.with_suffix(".pub")), "-E", "sha256"],
        check=True, capture_output=True, text=True,
    ).stdout.split()[1]
    monkeypatch.setattr(obs, "OPERATOR_PUBLIC_KEY", public_key)
    monkeypatch.setattr(obs, "OPERATOR_FINGERPRINT", fingerprint)
    return private_key


_SIGN_SEQ = [0]


def _sign(private_key, intent, source_head, *, namespace=None):
    authorization = obs.build_operator_authorization(intent=intent, source_head=source_head)
    # 每次簽章用獨一無二的 message 檔:ssh-keygen -Y sign 不會覆寫既有 .sig,重用檔名會靜默沿用舊簽。
    _SIGN_SEQ[0] += 1
    message = private_key.parent / f"permit-{_SIGN_SEQ[0]}.json"
    message.write_bytes(obs.canonical_bytes(authorization))
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", str(private_key), "-n",
         namespace or obs.OPERATOR_SIGNATURE_NAMESPACE, str(message)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    signature = message.with_suffix(".json.sig").read_bytes()
    return authorization, signature


# --------------------------------------------------------------------------- #
# intent + grant-set allowlist
# --------------------------------------------------------------------------- #
def test_intent_round_trip_and_central_delegation():
    intent = _intent()
    assert obs.validate_pg_observer_bootstrap_intent(intent, now=NOW) == []
    assert validator.validate_aiml_artifact(intent, now=NOW) == []


def test_grant_set_is_exact_minimal_read_only_observer():
    grant_set = obs.generate_observer_grant_sql(_intent())
    assert grant_set["create_role"] == (
        'CREATE ROLE "aiml_observer_ro" NOLOGIN NOSUPERUSER NOCREATEROLE '
        'NOCREATEDB NOREPLICATION NOBYPASSRLS'
    )
    # FIX-C3:role-level 唯讀約束為結構化(非呼叫端 SQL)、角色以引號化 ident 建構的 exact 兩敘述。
    assert grant_set["alter_role_settings"] == [
        'ALTER ROLE "aiml_observer_ro" SET default_transaction_read_only = on',
        'ALTER ROLE "aiml_observer_ro" SET search_path = pg_catalog',
    ]
    assert grant_set["grant_usage"] == 'GRANT USAGE ON SCHEMA "trading" TO "aiml_observer_ro"'
    assert grant_set["grant_select"] == [
        'GRANT SELECT ON "trading"."fills" TO "aiml_observer_ro"',
        'GRANT SELECT ON "trading"."orders" TO "aiml_observer_ro"',
    ]
    assert grant_set["connection_options"] == (
        "-c default_transaction_read_only=on -c search_path=pg_catalog"
    )


@pytest.mark.parametrize("mutation", [
    {"grant_set_selector": "observer_read_write_v1"},
    {"observed_relations": ["fills; DROP TABLE x"]},
    {"observer_role": "pg_superuser_obs"},
    {"privileges": ["SELECT", "INSERT"]},
    {"with_grant_option": True},
    {"role_membership": "aiml_writer"},
    {"raw_sql": "GRANT ALL ON ALL TABLES IN SCHEMA trading TO obs"},
    {"auth_mapping": "pg_hba_scram_local"},
])
def test_grant_set_allowlist_rejects_over_grant(mutation):
    caller_intent = {
        "grant_set_selector": "observer_read_only_v1", "observer_role": "aiml_observer_ro",
        "observed_schema": "trading", "observed_relations": ["fills"],
        "auth_mapping": "pg_hba_ident_local",
    }
    caller_intent.update(mutation)
    with pytest.raises(obs.PgObserverBootstrapError):
        obs.generate_observer_grant_sql(caller_intent)


# --------------------------------------------------------------------------- #
# fail-closed production apply — no fake success
# --------------------------------------------------------------------------- #
def test_apply_without_sshsig_is_pending_never_success():
    result = obs.apply_observer_bootstrap(_intent(), None, None, now=NOW, source_head=HEAD)
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert result["boundary"]["nine_authorities_false"] is True
    assert result["boundary"]["production_apply_performed"] is False
    assert result["independent_postcheck"] is None and result["rollback_record"] is None
    assert validator.validate_aiml_artifact(result, now=LATER) == []


def test_production_apply_with_valid_sshsig_still_pending(tmp_path, monkeypatch):
    # W0a 重構:reachable-but-authority-locked。即使帶一張 VALID operator SSHSIG,production 目標在**無 host
    # driver**(Mac/源碼/測試恆 driver=None)時走 reachable 閘的 step 5 → EXTERNAL_VERIFICATION_PENDING 且
    # 零變更(reachable 閘已在,只是沒有 driver 可執行)。不再是「deferred to the S2.0 EFFECT session」。
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent(target_class="production")
    authorization, signature = _sign(private_key, intent, HEAD)
    assert obs.validate_operator_authorization(
        authorization, signature, intent=intent, source_head=HEAD, now=NOW
    ) == []
    result = obs.apply_observer_bootstrap(intent, authorization, signature, now=NOW, source_head=HEAD)
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert "no host production driver" in result["failure_reason"]
    assert "zero mutation" in result["failure_reason"]
    assert result["boundary"]["production_apply_performed"] is False
    assert result["boundary"]["nine_authorities_false"] is True
    assert result["independent_postcheck"] is None and result["rollback_record"] is None
    assert result["operator_signature_pem"] is None  # 零變更:pending 不帶簽章
    assert validator.validate_aiml_artifact(result, now=LATER) == []


# --------------------------------------------------------------------------- #
# W0a — S2.0 production-driver reachability (reachable, authority-locked gate).
# driver=None (all source/tests/Mac) -> EXTERNAL_VERIFICATION_PENDING, zero mutation.
# An injected simulation driver REACHES the driver call but its non-attested evidence
# can NEVER forge production_apply_performed=true; a naive fabricated APPLIED is rejected.
# NOTE (honest boundary): no fixture here impersonates PLATFORM_ATTESTED runtime — every
# injected driver honestly reports LOCAL_REPRODUCIBLE/STRUCTURAL_ONLY, so NONE emits APPLIED.
# --------------------------------------------------------------------------- #
class _SimulationProductionDriver:
    """In-memory (NO real PG) fixed-operation driver for the reachable-gate tests.

    刻意回報一個**非** PLATFORM_ATTESTED 的 evidence_class;它不可、也絕不冒充平台背書的 runtime,
    故經此 driver 的 production 閘**永不** emit APPLIED(§10.5 #13)。records method calls to prove
    the gate REACHES the driver.
    """

    def __init__(self, *, evidence_class="LOCAL_REPRODUCIBLE"):
        self.evidence_class = evidence_class
        self.calls: list[str] = []
        self._present = False
        self._applied = False

    def observer_role_present(self, *, role):
        self.calls.append("observer_role_present")
        return self._present

    def observe_acl_state(self, *, role, schema, relations):
        self.calls.append("observe_acl_state")
        marker = "present" if self._applied else "absent"
        return "sha256:" + hashlib.sha256(f"{role}:{schema}:{marker}".encode()).hexdigest()

    def create_read_only_observer(self, *, grant_set):
        self.calls.append("create_read_only_observer")
        self._present = True
        self._applied = True

    def independent_read_only_proof(self, *, grant_set):
        self.calls.append("independent_read_only_proof")
        return {
            "read_only_proof": _valid_read_only_proof(),
            "reobserved_digest": "sha256:" + "d" * 64,
            "verifier_capture_digest": "sha256:" + "e" * 64,
        }

    def compensate(self, *, grant_set):
        self.calls.append("compensate")
        self._present = False
        self._applied = False


def test_production_driver_none_is_pending_zero_mutation(tmp_path, monkeypatch):
    # (a) production 目標 + driver=None(即使 SSHSIG 有效)→ EXTERNAL_VERIFICATION_PENDING,零變更。
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent(target_class="production")
    authorization, signature = _sign(private_key, intent, HEAD)
    result = obs.apply_observer_bootstrap(
        intent, authorization, signature, now=NOW, source_head=HEAD, driver=None
    )
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert result["boundary"]["production_apply_performed"] is False
    assert result["boundary"]["nine_authorities_false"] is True
    assert result["independent_postcheck"] is None and result["rollback_record"] is None
    # 零變更佐證:pending result 不帶任何 apply/簽章欄位。
    assert result["operator_signature_pem"] is None
    assert result["applied_grant_set_digest"] is None
    assert validator.validate_aiml_artifact(result, now=LATER) == []


def test_production_non_attested_target_host_is_pending(tmp_path, monkeypatch):
    # step 2:production 目標的 target_host 命名 Mac/dev/loopback → 於 SSHSIG 之前即 typed 非成功(零變更)。
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent(target_class="production", target_host="my-macbook.local")
    authorization, signature = _sign(private_key, intent, HEAD)
    driver = _SimulationProductionDriver()
    result = obs.apply_observer_bootstrap(
        intent, authorization, signature, now=NOW, source_head=HEAD, driver=driver
    )
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert "attested Linux target host" in result["failure_reason"]
    assert driver.calls == []  # host 檢查在 driver 之前 → 零變更


def test_production_missing_stale_wrong_namespace_sshsig_rejected(tmp_path, monkeypatch):
    # (b) production + (missing / wrong-namespace / stale) SSHSIG → typed pending;driver 從不被觸達(零變更)。
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent(target_class="production")
    driver = _SimulationProductionDriver()
    # missing:無授權/簽章 → AUTHORIZATION_REJECTED-class pending。
    r_missing = obs.apply_observer_bootstrap(intent, None, None, now=NOW, source_head=HEAD, driver=driver)
    assert r_missing["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert "AUTHORIZATION_REJECTED" in r_missing["failure_reason"]
    # wrong-namespace:以 S1 target-host namespace 簽的授權 → SSHSIG 無效 → AUTHORIZATION_REJECTED。
    authorization, wrong_ns_sig = _sign(
        private_key, intent, HEAD, namespace="arcane-equilibrium-aiml-s1-target-host-apply"
    )
    r_wrongns = obs.apply_observer_bootstrap(
        intent, authorization, wrong_ns_sig, now=NOW, source_head=HEAD, driver=driver
    )
    assert r_wrongns["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert "AUTHORIZATION_REJECTED" in r_wrongns["failure_reason"]
    # stale:授權/意圖皆逾期(now 超出有效窗)→ 於上游 window 檢查先 fail-closed(仍 pending)。
    authorization2, signature2 = _sign(private_key, intent, HEAD)
    stale = "2026-07-24T13:30:00+00:00"
    r_stale = obs.apply_observer_bootstrap(
        intent, authorization2, signature2, now=stale, source_head=HEAD, driver=driver
    )
    assert r_stale["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert "validity window" in r_stale["failure_reason"]
    # driver 全程未被觸達(SSHSIG/window 在 driver 之前 fail-closed)→ 零變更。
    assert driver.calls == []


def test_production_reachable_with_injected_driver(tmp_path, monkeypatch):
    # 「gate REACHES the driver call」:注入一個(非 PLATFORM_ATTESTED)simulation driver,production 閘走過
    # step 6-8(observe/create/independent postcheck)真的觸達 driver;step 9 因 evidence 非 PLATFORM_ATTESTED
    # → 補償 + typed pending(絕不 APPLIED)。這證 reachable 閘已在、driver 被真觸達。
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent(target_class="production")
    authorization, signature = _sign(private_key, intent, HEAD)
    driver = _SimulationProductionDriver(evidence_class="LOCAL_REPRODUCIBLE")
    result = obs.apply_observer_bootstrap(
        intent, authorization, signature, now=NOW, source_head=HEAD, driver=driver
    )
    for reached in ("observer_role_present", "observe_acl_state", "create_read_only_observer",
                    "independent_read_only_proof", "compensate"):
        assert reached in driver.calls, reached
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert result["status"] != "APPLIED"
    assert result["boundary"]["production_apply_performed"] is False
    assert "not PLATFORM_ATTESTED" in result["failure_reason"]
    assert validator.validate_aiml_artifact(result, now=LATER) == []


def test_injected_simulation_driver_cannot_forge_production_flag(tmp_path, monkeypatch):
    # §10.5 #13:任何注入的 simulation/disposable driver(誠實回報 LOCAL_REPRODUCIBLE / STRUCTURAL_ONLY)
    # 皆**不可**令 production_apply_performed=true / status=APPLIED。fixture 絕不冒充平台背書 runtime。
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent(target_class="production")
    authorization, signature = _sign(private_key, intent, HEAD)
    for evidence in ("LOCAL_REPRODUCIBLE", "STRUCTURAL_ONLY"):
        driver = _SimulationProductionDriver(evidence_class=evidence)
        result = obs.apply_observer_bootstrap(
            intent, authorization, signature, now=NOW, source_head=HEAD, driver=driver
        )
        assert result["status"] != "APPLIED", evidence
        assert result["status"] == "EXTERNAL_VERIFICATION_PENDING", evidence
        assert result["boundary"]["production_apply_performed"] is False, evidence
        assert validator.validate_aiml_artifact(result, now=LATER) == [], evidence


def test_fabricated_applied_without_platform_attested_is_rejected():
    # (c) 從一份 production PENDING result 竄改為 APPLIED / production_apply_performed=true(無真 driver、無
    # PLATFORM_ATTESTED 結構證據)並重簽 self_digest → result validator + central validator 皆拒。
    # 誠實界線:離線 validator 只證結構/整合——它擋下的是「缺 PLATFORM_ATTESTED 結構」的偽造;真「已 apply」
    # 的平台背書屬 S2.0 EFFECT session(見模組 docstring)。故此測試用**未帶** PLATFORM_ATTESTED 結構的偽造。
    pending = obs.apply_observer_bootstrap(
        _intent(target_class="production"), None, None, now=NOW, source_head=HEAD
    )
    assert pending["status"] == "EXTERNAL_VERIFICATION_PENDING"

    # (c1) 只翻 status + production_apply_performed(evidence_class 仍 STRUCTURAL_ONLY、postcheck 仍 null)。
    c1 = copy.deepcopy(pending)
    c1["status"] = "APPLIED"
    c1["boundary"]["production_apply_performed"] = True
    c1["self_digest"] = obs.artifact_self_digest(c1)
    assert obs.validate_pg_observer_bootstrap_result(c1, now=LATER)
    assert validator.validate_aiml_artifact(c1, now=LATER)

    # (c2) 再把 evidence_class 改成 PLATFORM_ATTESTED,但仍缺 postcheck/簽章、failure_reason 未清 → 仍被拒。
    c2 = copy.deepcopy(c1)
    c2["evidence_class"] = "PLATFORM_ATTESTED"
    c2["self_digest"] = obs.artifact_self_digest(c2)
    assert obs.validate_pg_observer_bootstrap_result(c2, now=LATER)
    assert validator.validate_aiml_artifact(c2, now=LATER)

    # (c3) production_apply_performed=true 掛在**非** APPLIED status → schema else 釘 false + validator 皆拒。
    c3 = copy.deepcopy(pending)
    c3["boundary"]["production_apply_performed"] = True
    c3["self_digest"] = obs.artifact_self_digest(c3)
    assert obs.validate_pg_observer_bootstrap_result(c3, now=LATER)
    assert validator.validate_aiml_artifact(c3, now=LATER)


def test_applied_result_builder_fail_closed_guards():
    # APPLIED builder 護欄(只證 fail-closed、不造「通過」的 APPLIED、不冒充平台背書):非 PLATFORM_ATTESTED /
    # applied==pre / 非 production 目標皆 raise。這些是純函式護欄斷言。
    intent = _intent(target_class="production")
    grant_set = obs.generate_observer_grant_sql(intent)
    postcheck = _postcheck(intent, "sha256:" + "b" * 64)
    armor_sig = b"-----BEGIN SSH SIGNATURE-----\nU1NIU0lHAAAAAQ==\n-----END SSH SIGNATURE-----\n"
    common = dict(
        grant_set=grant_set, pre_state_digest="sha256:" + "a" * 64,
        applied_grant_set_digest="sha256:" + "c" * 64, postcheck=postcheck,
        operator_authorization=obs.build_operator_authorization(intent=intent, source_head=HEAD),
        operator_signature=armor_sig, apply_actor_node=intent["applier_node_id"],
        started_at=NOW, completed_at=NOW,
    )
    # 非 PLATFORM_ATTESTED evidence → raise。
    with pytest.raises(obs.PgObserverBootstrapError):
        obs.build_pg_observer_bootstrap_applied_result(intent=intent, evidence_class="LOCAL_REPRODUCIBLE", **common)
    # applied == pre(apply 未改變 catalog)→ raise。
    with pytest.raises(obs.PgObserverBootstrapError):
        obs.build_pg_observer_bootstrap_applied_result(
            intent=intent, evidence_class="PLATFORM_ATTESTED",
            **{**common, "applied_grant_set_digest": common["pre_state_digest"]},
        )
    # 非 production 目標 → raise(在 evidence 檢查之前)。
    disp = _intent(target_class="disposable_local")
    with pytest.raises(obs.PgObserverBootstrapError):
        obs.build_pg_observer_bootstrap_applied_result(
            intent=disp, evidence_class="PLATFORM_ATTESTED",
            **{**common, "grant_set": obs.generate_observer_grant_sql(disp)},
        )


def test_registry_adapter_status_is_authority_locked_production_capable():
    # (d) registry status 由 declared_production_apply_disabled_until_operator_sshsig 翻為
    # AUTHORITY_LOCKED_PRODUCTION_CAPABLE(reachable 但 authority-locked);authority/invariant prose 明載三要件。
    registry = json.loads((ROOT / ".codex/agent_registry_v1.json").read_text(encoding="utf-8"))
    adapter = registry["effect_adapters"]["pg_observer_bootstrap_adapter_v1"]
    assert adapter["status"] == "AUTHORITY_LOCKED_PRODUCTION_CAPABLE"
    assert "reachable but authority-locked" in adapter["authority"]
    assert "PLATFORM_ATTESTED" in adapter["authority"]
    assert "zero mutation" in adapter["authority"]
    assert "nine authorities stay false" in adapter["invariant"]


# --------------------------------------------------------------------------- #
# FIX-6 — stale (expired-window) intent normalizes to PENDING; malformed still raises
# --------------------------------------------------------------------------- #
def test_stale_window_intent_is_pending_not_raise():
    # 結構有效但當前有效窗已過(created 12:00 + ttl 900s → expires 12:15;now 13:30 已過)。
    intent = _intent()
    stale = "2026-07-24T13:30:00+00:00"
    result = obs.apply_observer_bootstrap(intent, None, None, now=stale, source_head=HEAD)
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert "validity window" in result["failure_reason"]
    assert result["boundary"]["nine_authorities_false"] is True
    assert result["independent_postcheck"] is None and result["rollback_record"] is None
    assert validator.validate_aiml_artifact(result, now=stale) == []


def test_malformed_intent_still_raises_not_pending():
    # genuine 結構錯誤(observed_relations 為空,違反 schema minItems + 破壞 self_digest)→ 仍 raise,
    # 絕不被 FIX-6 的 stale-window→PENDING 正規化吞掉(malformed 與 stale-window 明確分離)。
    bad = copy.deepcopy(_intent())
    bad["observed_relations"] = []
    with pytest.raises(obs.PgObserverBootstrapError):
        obs.apply_observer_bootstrap(bad, None, None, now=NOW, source_head=HEAD)


def test_malformed_now_raises_typed_error_not_bare_valueerror():
    # FIX-9(E2 #3):intent 結構有效但 governance 供給的 now 本身 malformed → 比照 malformed-intent
    # 硬合約 fail-closed 為 PgObserverBootstrapError,絕不讓 build_pending_result 內 _parse_time(now)
    # 逸出裸 ValueError,也不冒充「outside validity window」的 stale-window pending。
    intent = _intent()
    for bad_now in ("not-a-timestamp", "2026-13-40T99:99:99", ""):
        with pytest.raises(obs.PgObserverBootstrapError):
            obs.apply_observer_bootstrap(intent, None, None, now=bad_now, source_head=HEAD)


# --------------------------------------------------------------------------- #
# operator SSHSIG — domain separation + tamper
# --------------------------------------------------------------------------- #
def test_operator_authorization_valid_and_domain_separated(tmp_path, monkeypatch):
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent()
    authorization, signature = _sign(private_key, intent, HEAD)
    assert obs.OPERATOR_SIGNATURE_NAMESPACE == "arcane-equilibrium-aiml-s2-observer-bootstrap"
    assert obs.OPERATOR_IDENTITY == "aiml-s2-observer-bootstrap-operator-v1"
    assert obs.validate_operator_authorization(
        authorization, signature, intent=intent, source_head=HEAD, now=NOW
    ) == []
    # 以「S1 target-host namespace」簽的相同 permit 在 S2 observer profile 下因 namespace 不符被拒。
    _auth2, wrong_ns_sig = _sign(
        private_key, intent, HEAD, namespace="arcane-equilibrium-aiml-s1-target-host-apply"
    )
    errors = obs.validate_operator_authorization(
        authorization, wrong_ns_sig, intent=intent, source_head=HEAD, now=NOW
    )
    assert any("SSH signature is invalid" in e for e in errors)


def test_operator_authorization_rejects_wrong_source_head_and_expiry(tmp_path, monkeypatch):
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent()
    authorization, signature = _sign(private_key, intent, HEAD)
    # source head 不符。
    assert obs.validate_operator_authorization(
        authorization, signature, intent=intent, source_head=OTHER_HEAD, now=NOW
    )
    # 過期 now(> expires)。
    stale = (datetime.fromisoformat(CREATED) + timedelta(minutes=30)).isoformat()
    assert obs.validate_operator_authorization(
        authorization, signature, intent=intent, source_head=HEAD, now=stale
    )


# --------------------------------------------------------------------------- #
# postcheck / rollback structural validators + forgery
# --------------------------------------------------------------------------- #
def _valid_read_only_proof():
    return {
        "write_denied": {"attempted": "DELETE FROM \"trading\".\"fills\"", "observed_sqlstate": "42501", "verdict": "DENIED"},
        "set_role_denied": {"attempted": "SET ROLE \"aiml_writer\"", "observed_sqlstate": "42501", "verdict": "DENIED"},
        "search_path_reset_harmless": {"attempted": "SET search_path TO public", "effective_search_path": "public", "harmless": True, "queries_schema_qualified": True},
        "credential_escalation_denied": {"attempted": "connect_with_escalated_credential", "observed_sqlstate": "28P01", "verdict": "DENIED"},
    }


def _postcheck(intent, baseline_digest):
    return obs.build_pg_observer_bootstrap_postcheck(
        intent=intent, verifier_node="observer_ops_postcheck", applier_node="observer_apply_actor",
        reobserved_post_rollback_digest=baseline_digest, read_only_proof=_valid_read_only_proof(),
        verifier_capture_digest="sha256:" + "a" * 64, observed_at=NOW,
    )


def test_postcheck_builder_requires_real_denials():
    intent = _intent()
    baseline = "sha256:" + "b" * 64
    proof = _valid_read_only_proof()
    proof["write_denied"]["observed_sqlstate"] = "00000"  # 非拒絕碼
    with pytest.raises(obs.PgObserverReadOnlyError):
        obs.build_pg_observer_bootstrap_postcheck(
            intent=intent, verifier_node="v", applier_node="a",
            reobserved_post_rollback_digest=baseline, read_only_proof=proof,
            verifier_capture_digest="sha256:" + "a" * 64, observed_at=NOW,
        )


def test_postcheck_rejects_applier_equals_verifier():
    intent = _intent()
    with pytest.raises(obs.PgObserverBootstrapError):
        obs.build_pg_observer_bootstrap_postcheck(
            intent=intent, verifier_node="same", applier_node="same",
            reobserved_post_rollback_digest="sha256:" + "b" * 64,
            read_only_proof=_valid_read_only_proof(),
            verifier_capture_digest="sha256:" + "a" * 64, observed_at=NOW,
        )


def test_postcheck_round_trip_and_forgery():
    intent = _intent()
    baseline = "sha256:" + "b" * 64
    postcheck = _postcheck(intent, baseline)
    assert obs.validate_pg_observer_bootstrap_postcheck(postcheck, now=LATER) == []
    assert validator.validate_aiml_artifact(postcheck, now=LATER) == []
    # forgery:改寫 write denial SQLSTATE 但不重簽 → self_digest 不符 + PASS 檢查失敗。
    forged = copy.deepcopy(postcheck)
    forged["read_only_proof"]["write_denied"]["observed_sqlstate"] = "00000"
    assert obs.validate_pg_observer_bootstrap_postcheck(forged, now=LATER)
    # forgery:重簽 self_digest 也擋不住 PASS-必要拒絕碼檢查。
    forged["self_digest"] = obs.artifact_self_digest(forged)
    assert obs.validate_pg_observer_bootstrap_postcheck(forged, now=LATER)


def test_rollback_exact_restoration_crux():
    intent = _intent()
    grant_set = obs.generate_observer_grant_sql(intent)
    baseline = "sha256:" + "b" * 64
    rollback = obs.build_pg_observer_bootstrap_rollback(
        intent=intent, grant_set=grant_set, pre_state_digest=baseline,
        post_state_digest=baseline, observer_absent=True, observed_at=NOW,
    )
    assert rollback["status"] == "RESTORED_EXACT"
    assert obs.validate_pg_observer_bootstrap_rollback(rollback, now=LATER) == []
    assert validator.validate_aiml_artifact(rollback, now=LATER) == []
    # 非精確還原(post != pre)不能宣稱 RESTORED_EXACT。
    not_restored = obs.build_pg_observer_bootstrap_rollback(
        intent=intent, grant_set=grant_set, pre_state_digest=baseline,
        post_state_digest="sha256:" + "c" * 64, observer_absent=False, observed_at=NOW,
    )
    assert not_restored["status"] == "NOT_RESTORED"


def test_pending_result_forgery_flip_boundary_rejected():
    result = obs.apply_observer_bootstrap(_intent(), None, None, now=NOW, source_head=HEAD)
    forged = copy.deepcopy(result)
    forged["boundary"]["nine_authorities_false"] = False
    forged["self_digest"] = obs.artifact_self_digest(forged)
    assert obs.validate_pg_observer_bootstrap_result(forged, now=LATER)
    assert validator.validate_aiml_artifact(forged, now=LATER)


# --------------------------------------------------------------------------- #
# FIX-2 / FIX-7 — operator_signature_pem schema-pinned to the FULL SSHSIG armor
# (header + base64-only body + END footer);an armor-WRAPPED DSN is now rejected.
# --------------------------------------------------------------------------- #
def test_result_schema_pins_operator_signature_pem_to_sshsig_armor(tmp_path, monkeypatch):
    schema = json.loads(obs.RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))
    prop = schema["properties"]["operator_signature_pem"]
    applied_then = schema["allOf"][0]["then"]["properties"]["operator_signature_pem"]

    def base_ok(value):
        return schema_subset_errors(value, prop, schema) == []

    def applied_ok(value):
        return schema_subset_errors(value, applied_then, schema) == []

    # null 分支仍合法(pending / production 路徑一律 emit null)。
    assert base_ok(None)
    # 手工最小 base64 armor 合法(header + base64 body + END footer)。
    armored = "-----BEGIN SSH SIGNATURE-----\nU1NIU0lHAAAAAQ==\n-----END SSH SIGNATURE-----\n"
    assert base_ok(armored)
    assert applied_ok(armored)
    # FIX-7 主證:一張**真** ssh-keygen -Y sign 簽出的 armored SSHSIG(= receipt 內
    # operator_signature_pem 的真實形態)於 base + APPLIED then 兩處皆 validate [](pattern 由此
    # 真樣本經驗性導出:多行、body 含 +///= padding)。
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    _auth, real_sig = _sign(private_key, _intent(), HEAD)
    real_pem = real_sig.decode("ascii")
    assert real_pem.startswith("-----BEGIN SSH SIGNATURE-----\n")
    assert real_pem.rstrip("\n").endswith("-----END SSH SIGNATURE-----")
    assert base_ok(real_pem)
    assert applied_ok(real_pem)
    # FIX-7(E2 P3 精確反例):armor-WRAPPED DSN(header/footer 齊全但 body 夾帶 DSN)→ 被
    # base64-only body 擋掉,不再冒充合法簽章。
    dsn_in_armor = (
        "-----BEGIN SSH SIGNATURE-----\n"
        "postgres://trade-core:5432/openclaw\n"
        "-----END SSH SIGNATURE-----\n"
    )
    assert not base_ok(dsn_in_armor)
    assert not applied_ok(dsn_in_armor)
    # FIX-7:armor 包但 body 非 base64(含 @ : 空白等非 base64 字元)→ 亦被擋。
    nonbase64_in_armor = (
        "-----BEGIN SSH SIGNATURE-----\n"
        "@@@ not base64 @@@\n"
        "-----END SSH SIGNATURE-----\n"
    )
    assert not base_ok(nonbase64_in_armor)
    assert not applied_ok(nonbase64_in_armor)
    # 缺 END footer 的 armor(只有 header + base64 body)→ 拒(必須帶 closing footer)。
    assert not base_ok("-----BEGIN SSH SIGNATURE-----\nU1NIU0lHAAAAAQ==\n")
    # naked DSN / 任何非 armor 字串一律拒(base + APPLIED then 兩處)。
    assert not base_ok("postgres://host:5432/db")
    assert not base_ok("not-a-signature")
    assert not applied_ok("postgres://host:5432/db")


# --------------------------------------------------------------------------- #
# FIX-4 / FIX-5 — closure-binding negatives (offline synthetic APPLIED receipt)
# --------------------------------------------------------------------------- #
def _synthetic_binding_case():
    """A minimal offline APPLIED-shaped closure case that validates [] — mutate one facet per negative."""

    intent = _intent()
    capture_digest = "sha256:" + "e" * 64
    postcheck = obs.build_pg_observer_bootstrap_postcheck(
        intent=intent, verifier_node=intent["postcheck_node_id"], applier_node=intent["applier_node_id"],
        reobserved_post_rollback_digest="sha256:" + "b" * 64, read_only_proof=_valid_read_only_proof(),
        verifier_capture_digest=capture_digest, observed_at=NOW,
    )
    receipt = {
        "adapter_id": obs.ADAPTER_ID,
        "status": "APPLIED_ROLLED_BACK_EXACT",
        "intent_id": intent["intent_id"],
        "intent_digest": intent["self_digest"],
        # FIX-C1:合成 receipt 需攜帶 _base_result 的完整身分欄位(target_host/database/observer_role),
        # 因 postcheck validator 現以完整身分綁定(不只 intent_id),否則此 baseline 會被誤判不符。
        "target_host": intent["target_host"],
        "database": intent["database"],
        "observer_role": intent["observer_role"],
        "source_head": HEAD,
        "apply_actor_node": intent["applier_node_id"],
        "independent_verifier_node": intent["postcheck_node_id"],
        "operator_authorization": obs.build_operator_authorization(intent=intent, source_head=HEAD),
        "independent_postcheck": postcheck,
    }
    capture = {"schema_version": "command_capture_v2", "node_id": intent["postcheck_node_id"], "record_digest": capture_digest}
    return {
        "intent": intent,
        "receipt": receipt,
        "route": {"nodes": [{"id": obs.ADAPTER_ID, "kind": "effect_adapter", "mandatory": True}]},
        "fragments": {"ops_preflight": {"evidence_refs": []}, "ops_postcheck": {"evidence_refs": ["ev-cap"]}},
        "evidence_by_id": {"ev-cap": {"id": "ev-cap", "scope": "runtime", "source": "ops_postcheck",
                                      "kind": "command_capture_v2", "digest": capture_digest, "artifact": capture}},
        "packet": {
            "authority_refs": [{"class": "claim_evidence",
                                "source": f"{obs.INTENT_SCHEMA_VERSION}:{intent['intent_id']}",
                                "digest": intent["self_digest"]}],
            "acceptance": [{"status": "PASS", "evidence_refs": ["ev-receipt", "ev-cap"]}],
        },
        "valid_receipts": {"ev-receipt": receipt},
    }


def _run_binding(case):
    return obs.validate_pg_observer_bootstrap_binding(
        case["packet"], case["route"], case["fragments"], case["evidence_by_id"], case["valid_receipts"],
    )


def test_binding_offline_baseline_is_admissible():
    assert _run_binding(_synthetic_binding_case()) == []


def test_binding_rejects_not_exactly_one_receipt():
    case = _synthetic_binding_case()
    assert obs.validate_pg_observer_bootstrap_binding(
        case["packet"], case["route"], case["fragments"], case["evidence_by_id"], {}
    ) == ["observer bootstrap closure PASS requires exactly one observer-bootstrap effect receipt"]
    two = {"ev-r1": case["receipt"], "ev-r2": copy.deepcopy(case["receipt"])}
    assert any("exactly one observer-bootstrap effect receipt" in e for e in obs.validate_pg_observer_bootstrap_binding(
        case["packet"], case["route"], case["fragments"], case["evidence_by_id"], two
    ))


def test_binding_rejects_missing_ops_preflight_fragment():
    case = _synthetic_binding_case()
    case["fragments"] = {"ops_postcheck": case["fragments"]["ops_postcheck"]}
    assert any("requires an OPS preflight fragment" in e for e in _run_binding(case))


def test_binding_rejects_not_exactly_one_command_capture():
    case = _synthetic_binding_case()
    case["fragments"]["ops_postcheck"] = {"evidence_refs": []}
    assert any("exactly one verifier command_capture_v2" in e for e in _run_binding(case))


def test_binding_rejects_capture_node_equal_to_applier():
    case = _synthetic_binding_case()
    case["evidence_by_id"]["ev-cap"]["artifact"]["node_id"] = case["receipt"]["apply_actor_node"]
    assert any("verifier capture node must differ from the applier node" in e for e in _run_binding(case))


def test_binding_rejects_bogus_operator_authorization():
    # FIX-5(E2 P2 精確重現):{"totally":"bogus"} 授權於 closure binding 被結構契約擋掉。
    case = _synthetic_binding_case()
    case["receipt"]["operator_authorization"] = {"totally": "bogus"}
    assert any("operator authorization fields do not match the exact contract" in e for e in _run_binding(case))


def test_binding_rejects_intent_mismatched_operator_authorization():
    # FIX-5:結構良好但綁到「別的 intent / source_head」的授權 → intent 綁定不符被拒。
    case = _synthetic_binding_case()
    other = _intent(source_head=OTHER_HEAD)
    case["receipt"]["operator_authorization"] = obs.build_operator_authorization(intent=other, source_head=OTHER_HEAD)
    assert any("is not bound to the result" in e for e in _run_binding(case))


# --------------------------------------------------------------------------- #
# FIX-C1 (Codex P2) — postcheck full-identity binding: a forged postcheck for a
# DIFFERENT target that reuses the SAME intent_id must be rejected by BOTH the
# postcheck validator and the closure binding (intent_id alone is caller-supplied).
# --------------------------------------------------------------------------- #
def test_postcheck_forged_intent_digest_same_intent_id_rejected_by_validator_and_binding():
    intent = _intent()
    result = obs._base_result(
        intent, obs.generate_observer_grant_sql(intent), apply_actor_node=intent["applier_node_id"]
    )
    baseline = "sha256:" + "b" * 64
    postcheck = _postcheck(intent, baseline)
    # baseline:完整身分綁定通過(intent_id/intent_digest/source_head/observer_role/database/host 皆相符)。
    assert obs.validate_pg_observer_bootstrap_postcheck(postcheck, result=result, now=LATER) == []
    # 偽造:intent_id **不變**(舊綁定僅比 intent_id/applier/verifier → 會放行),只把 intent_digest 換成
    # 別的 digest 並重簽 self_digest(self_digest 檢查因此通過,唯一失敗者是新的 intent_digest 綁定)。
    forged = copy.deepcopy(postcheck)
    forged["intent_digest"] = "sha256:" + "f" * 64
    forged["self_digest"] = obs.artifact_self_digest(forged)
    assert forged["intent_id"] == result["intent_id"]  # intent_id 仍相符,只有 intent_digest 不符
    validator_errors = obs.validate_pg_observer_bootstrap_postcheck(forged, result=result, now=LATER)
    assert any("intent_digest is not bound to the result" in e for e in validator_errors)
    # closure binding:把同一偽造嵌入 receipt(receipt 攜帶真 intent_digest,內嵌 postcheck 被換成別的)→ 亦拒。
    case = _synthetic_binding_case()
    embedded = case["receipt"]["independent_postcheck"]
    embedded["intent_digest"] = "sha256:" + "f" * 64
    embedded["self_digest"] = obs.artifact_self_digest(embedded)
    assert any("intent_digest is not bound to the result" in e for e in _run_binding(case))


def test_postcheck_forged_target_host_same_intent_id_rejected():
    # FIX-C1(target 欄位面):host(=result.target_host)被換成別的 target 但 intent_id 不變 → 被拒。
    intent = _intent()
    result = obs._base_result(
        intent, obs.generate_observer_grant_sql(intent), apply_actor_node=intent["applier_node_id"]
    )
    forged = copy.deepcopy(_postcheck(intent, "sha256:" + "b" * 64))
    forged["host"] = "other_host"
    forged["self_digest"] = obs.artifact_self_digest(forged)
    errors = obs.validate_pg_observer_bootstrap_postcheck(forged, result=result, now=LATER)
    assert any("host is not bound to the result" in e for e in errors)


# --------------------------------------------------------------------------- #
# FIX-C2 (Codex P2) — a non-dict verifier capture artifact (artifact: null / a bare
# digest string) is REJECTED, not silently skipped past the record checks while still
# counting toward acceptance.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad_artifact", [None, "sha256:" + "e" * 64, ["not", "a", "dict"]])
def test_binding_rejects_non_dict_verifier_capture_artifact(bad_artifact):
    case = _synthetic_binding_case()
    # outer digest 仍相符,但 artifact 非 dict(null / 裸 digest 字串)→ 舊 isinstance guard 會靜默跳過
    # record 驗證卻仍計入 acceptance;修後直接 fail-closed,且不計入 acceptance。
    case["evidence_by_id"]["ev-cap"]["artifact"] = bad_artifact
    errors = _run_binding(case)
    assert any("artifact must be a well-formed record" in e for e in errors)
    assert any("must bind the effect receipt + verifier command capture" in e for e in errors)


def test_result_validator_rejects_bogus_operator_authorization_on_pending_shell():
    # FIX-5(central-validator 路徑的 offline 佐證):把 pending result 竄改為 APPLIED + bogus 授權後
    # 重簽外層,validate_pg_observer_bootstrap_result 仍拒(此處為粗粒度「非 [] 」;pending shell 缺
    # postcheck/rollback/簽章,validator 會在 schema 階段短路——真正**孤立** auth-binding 接線的斷言
    # 見下方 FIX-8 companion 與可拋棄叢集 forgery D/E)。
    pending = obs.apply_observer_bootstrap(_intent(), None, None, now=NOW, source_head=HEAD)
    forged = copy.deepcopy(pending)
    forged["status"] = "APPLIED_ROLLED_BACK_EXACT"
    forged["operator_authorization"] = {"totally": "bogus"}
    forged["self_digest"] = obs.artifact_self_digest(forged)
    assert obs.validate_pg_observer_bootstrap_result(forged, now=LATER)


_AUTH_FIELDS_MSG = "operator authorization fields do not match the exact contract"
_AUTH_BIND_MSG = "is not bound to the result"


def _offline_applied_result(intent, *, operator_authorization, operator_signature):
    """Synthesize a SCHEMA-VALID APPLIED_ROLLED_BACK_EXACT result offline (no PG).

    關鍵:validate_pg_observer_bootstrap_result 在 schema 違規時會**提前 return**,故只有一份
    schema-valid 的 APPLIED result 才會真的走到 FIX-5 的 operator_authorization_binding_errors 分支。
    這讓 auth-binding 訊息之有無能被**孤立**觀察(不被其他結構錯誤淹沒),即使在 PG-less CI。
    """

    grant_set = obs.generate_observer_grant_sql(intent)
    pre = "sha256:" + "b" * 64
    applied = "sha256:" + "c" * 64
    postcheck = obs.build_pg_observer_bootstrap_postcheck(
        intent=intent, verifier_node=intent["postcheck_node_id"], applier_node=intent["applier_node_id"],
        reobserved_post_rollback_digest=pre, read_only_proof=_valid_read_only_proof(),
        verifier_capture_digest="sha256:" + "e" * 64, observed_at=NOW,
    )
    rollback = obs.build_pg_observer_bootstrap_rollback(
        intent=intent, grant_set=grant_set, pre_state_digest=pre,
        post_state_digest=pre, observer_absent=True, observed_at=NOW,
    )
    return obs.build_pg_observer_bootstrap_result(
        intent=intent, grant_set=grant_set, status="APPLIED_ROLLED_BACK_EXACT",
        pre_state_digest=pre, applied_grant_set_digest=applied, postcheck=postcheck,
        rollback_record=rollback, operator_authorization=operator_authorization,
        operator_signature=operator_signature, apply_actor_node=intent["applier_node_id"],
        started_at=NOW, completed_at=NOW,
    )


def test_result_validator_isolates_operator_auth_binding_offline(tmp_path, monkeypatch):
    # FIX-8(E4 #2):在 PG-less 環境**孤立**驗證 FIX-5 auth-binding 接線——用一份 schema-valid 的離線
    # APPLIED result(validator 不在 schema 階段短路,真的走到 auth-binding 分支),斷言「特定訊息在
    # bogus / intent-mismatch 出現、在 well-formed intent-bound 消失」,而非僅「非空」。結構檢查不驗
    # 簽章,故無需真簽金鑰即可用 build_operator_authorization 造 well-formed 授權。
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent()
    well_formed, signature = _sign(private_key, intent, HEAD)

    # (a) well-formed intent-bound 授權 → 完整 valid([]);兩條 auth-binding 訊息皆 ABSENT。
    ok = _offline_applied_result(intent, operator_authorization=well_formed, operator_signature=signature)
    ok_errors = obs.validate_pg_observer_bootstrap_result(ok, now=LATER)
    assert ok_errors == []
    assert not any(_AUTH_FIELDS_MSG in e for e in ok_errors)
    assert not any(_AUTH_BIND_MSG in e for e in ok_errors)

    # (b) bogus 授權 → 「fields do not match the exact contract」PRESENT(re-sign 外層 self_digest,
    #     其餘結構仍 valid,故訊息之有無精確追蹤 operator_authorization 這一個輸入)。
    bogus = copy.deepcopy(ok)
    bogus["operator_authorization"] = {"totally": "bogus"}
    bogus["self_digest"] = obs.artifact_self_digest(bogus)
    bogus_errors = obs.validate_pg_observer_bootstrap_result(bogus, now=LATER)
    assert any(_AUTH_FIELDS_MSG in e for e in bogus_errors)

    # (c) 結構良好但綁到別的 intent / source_head → 「is not bound to the result」PRESENT,且
    #     fields-contract 訊息 ABSENT(欄位集合正確,只是綁定不符)。
    other = _intent(source_head=OTHER_HEAD)
    mismatched = copy.deepcopy(ok)
    mismatched["operator_authorization"] = obs.build_operator_authorization(intent=other, source_head=OTHER_HEAD)
    mismatched["self_digest"] = obs.artifact_self_digest(mismatched)
    mismatched_errors = obs.validate_pg_observer_bootstrap_result(mismatched, now=LATER)
    assert any(_AUTH_BIND_MSG in e for e in mismatched_errors)
    assert not any(_AUTH_FIELDS_MSG in e for e in mismatched_errors)


# --------------------------------------------------------------------------- #
# FIX-10 (E2 P2) — operator_signature_pem armor body must be STRICT base64;
# plaintext-secret bodies that ride the FIX-7 armor charset are now precluded.
# --------------------------------------------------------------------------- #
_STRICT_B64_MSG = "operator_signature_pem body is not strict base64 (possible non-signature payload)"

# E2 精確反例:armor 外殼合法(body charset [A-Za-z0-9+/=\n])但 body 夾帶可讀 plaintext 機密。
_PLAINTEXT_SECRET_PEMS = {
    "password": "-----BEGIN SSH SIGNATURE-----\npassword=hunter2\n-----END SSH SIGNATURE-----\n",
    "pgpassword": "-----BEGIN SSH SIGNATURE-----\npgpassword=s3cr3tpw\n-----END SSH SIGNATURE-----\n",
    "bearer": "-----BEGIN SSH SIGNATURE-----\nbearer\nAAAAAAAAAAAAbbbb\n-----END SSH SIGNATURE-----\n",
}
# 控制:去 armor 後含 ':'/'@' 非 body-charset 字元 → 連 schema armor pattern 都過不了(仍 REJECTED)。
_DSN_IN_ARMOR = "-----BEGIN SSH SIGNATURE-----\npostgres://h:5432/db\n-----END SSH SIGNATURE-----\n"
# 合法 base64 blob(無 armor plaintext)→ 接受(documented inherent case:base64-encoded 非可讀 plaintext)。
_VALID_B64_ARMOR = "-----BEGIN SSH SIGNATURE-----\nU1NIU0lHAAAAAQ==\n-----END SSH SIGNATURE-----\n"


def test_operator_signature_pem_body_strict_base64_helper(tmp_path, monkeypatch):
    # helper-level 單元:真 armored SSHSIG body 去 armor 後為嚴格 base64=True;三個 E2 plaintext 反例 +
    # naked DSN 皆 False;valid base64 blob=True;null / 空字串 = False(fail-closed)。
    assert obs._operator_signature_pem_body_is_strict_base64(_VALID_B64_ARMOR) is True
    for label, pem in _PLAINTEXT_SECRET_PEMS.items():
        assert obs._operator_signature_pem_body_is_strict_base64(pem) is False, label
    assert obs._operator_signature_pem_body_is_strict_base64(_DSN_IN_ARMOR) is False
    assert obs._operator_signature_pem_body_is_strict_base64(None) is False
    assert obs._operator_signature_pem_body_is_strict_base64("") is False
    # 一張**真** ssh-keygen -Y sign 簽出的 armored SSHSIG → body 去 armor 後為嚴格 base64=True。
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    _auth, real_sig = _sign(private_key, _intent(), HEAD)
    assert obs._operator_signature_pem_body_is_strict_base64(real_sig.decode("ascii")) is True


def test_build_result_refuses_plaintext_secret_pem_body():
    # build 期護欄:APPLIED result 若 operator_signature 的 armor body 非嚴格 base64 → 直接 fail-closed
    # (SecretLeakageError),build 絕不 emit 一份 body 夾帶可讀 plaintext 的簽章欄位。授權在 build 期不做
    # 密碼學驗證,故以 build_operator_authorization 造 well-formed 授權即可觸達簽章欄位護欄。
    intent = _intent()
    authorization = obs.build_operator_authorization(intent=intent, source_head=HEAD)
    for label, pem in _PLAINTEXT_SECRET_PEMS.items():
        with pytest.raises(obs.SecretLeakageError):
            _offline_applied_result(
                intent, operator_authorization=authorization, operator_signature=pem.encode("ascii"),
            )


def test_result_validator_rejects_plaintext_secret_pem_body_offline(tmp_path, monkeypatch):
    # FIX-10(E2 P2 精確重現 + 孤立):以一份 schema-valid 的離線 APPLIED result 為基底(validator 不在
    # schema 階段短路),把 operator_signature_pem 竄改為「armor 外殼合法但 body 夾帶 plaintext 機密」的三個
    # E2 反例並重簽外層 self_digest;validate 應精確追加 strict-base64 錯誤。secret 掃描排除該欄位,故唯一擋
    # 下它的正是 FIX-10 的 strict-base64 body 檢查(bypass 已關閉)。
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent()
    well_formed, signature = _sign(private_key, intent, HEAD)
    base = _offline_applied_result(intent, operator_authorization=well_formed, operator_signature=signature)
    # 真 armored SSHSIG → 完整 valid([]),且 strict-base64 錯誤 ABSENT。
    base_errors = obs.validate_pg_observer_bootstrap_result(base, now=LATER)
    assert base_errors == []
    assert not any(_STRICT_B64_MSG in e for e in base_errors)

    for label, pem in _PLAINTEXT_SECRET_PEMS.items():
        forged = copy.deepcopy(base)
        forged["operator_signature_pem"] = pem
        forged["self_digest"] = obs.artifact_self_digest(forged)
        errors = obs.validate_pg_observer_bootstrap_result(forged, now=LATER)
        assert any(_STRICT_B64_MSG in e for e in errors), (label, errors)
        # 中央 validator 同一路徑亦拒(schema armor pattern 過關後委派至 validate_pg_observer_bootstrap_result)。
        assert validator.validate_aiml_artifact(forged, now=LATER)
        # 佐證 bypass 之所在:secret 掃描排除此欄位,故 SECRET_LIKE_RE 認得的 plaintext 不被 secret-scan 攔——
        # 唯一擋它的是 strict-base64 檢查。
        assert obs._contains_secret_like(obs._result_secret_scan_view(forged)) is False

    # DSN 控制:body 含 ':'/'@' 非 armor-charset → 在 schema 階段即被 armor pattern 拒(仍 REJECTED)。
    dsn_forged = copy.deepcopy(base)
    dsn_forged["operator_signature_pem"] = _DSN_IN_ARMOR
    dsn_forged["self_digest"] = obs.artifact_self_digest(dsn_forged)
    assert obs.validate_pg_observer_bootstrap_result(dsn_forged, now=LATER)

    # valid base64 blob(無 armor plaintext)→ 接受(documented inherent case)。
    b64_forged = copy.deepcopy(base)
    b64_forged["operator_signature_pem"] = _VALID_B64_ARMOR
    b64_forged["self_digest"] = obs.artifact_self_digest(b64_forged)
    assert obs.validate_pg_observer_bootstrap_result(b64_forged, now=LATER) == []

    # null(pending 路徑):operator_signature_pem=None 不觸發 strict-base64 檢查 → 仍接受。
    pending = obs.apply_observer_bootstrap(_intent(), None, None, now=NOW, source_head=HEAD)
    assert pending["operator_signature_pem"] is None
    assert obs.validate_pg_observer_bootstrap_result(pending, now=LATER) == []


# --------------------------------------------------------------------------- #
# FIX-11 (E2 P2 ROOT-CAUSE) — strict-base64 body guard is UNCONDITIONAL across ALL
# statuses (hoisted out of the APPLIED elif); no non-APPLIED status/path can carry a
# readable plaintext secret in operator_signature_pem past module OR central gate.
# --------------------------------------------------------------------------- #
_NULL_PIN_MSG = "operator_signature_pem"

# E2 exact repro:任何非 APPLIED status 夾帶可讀 plaintext 機密的 armor(secret 掃描排除此欄位)。
_E2_REPRO_PEMS = (
    "-----BEGIN SSH SIGNATURE-----\npassword=hunter2\n-----END SSH SIGNATURE-----\n",
    "-----BEGIN SSH SIGNATURE-----\npgpassword=s3cr3tpw\n-----END SSH SIGNATURE-----\n",
)


def _offline_result_status(intent, status, *, operator_authorization, operator_signature):
    """Synthesize a SCHEMA-VALID non-APPLIED result offline via build_pg_observer_bootstrap_result.

    FAILED / ROLLED_BACK_INTERRUPTED / NOT_RESTORED_FAILED legitimately carry a non-None
    operator_signature_pem (the schema does NOT pin them null), so a real armored signature
    validates [] and the ONLY thing precluding a plaintext body is the now-unconditional
    strict-base64 validator check.
    """

    grant_set = obs.generate_observer_grant_sql(intent)
    return obs.build_pg_observer_bootstrap_result(
        intent=intent, grant_set=grant_set, status=status,
        pre_state_digest="sha256:" + "b" * 64, applied_grant_set_digest="sha256:" + "c" * 64,
        postcheck=None, rollback_record=None, operator_authorization=operator_authorization,
        operator_signature=operator_signature, apply_actor_node=intent["applier_node_id"],
        started_at=NOW, completed_at=NOW,
    )


def test_fix11_strict_base64_unconditional_for_signature_carrying_statuses(tmp_path, monkeypatch):
    # FIX-11:strict-base64 body 護欄已移出 APPLIED_ROLLED_BACK_EXACT elif,對任何非 None 字串**無條件**
    # 生效。以下三個「合法帶簽章」的非 APPLIED status(schema 不釘 null)各造一份 schema-valid 離線 result:
    # 真 armored 簽章 → validate [];竄改為 armor 外殼合法但 body 夾帶 plaintext 機密("password=hunter2"/
    # "pgpassword=s3cr3tpw")→ module 與 central 皆拒,且帶 strict-base64 訊息;secret 掃描仍排除此欄位,
    # 證明 strict-base64 是唯一守門者(bypass 已對所有 status 關閉)。
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent()
    well_formed, signature = _sign(private_key, intent, HEAD)
    for status in ("FAILED", "ROLLED_BACK_INTERRUPTED", "NOT_RESTORED_FAILED"):
        base = _offline_result_status(
            intent, status, operator_authorization=well_formed, operator_signature=signature
        )
        base_errors = obs.validate_pg_observer_bootstrap_result(base, now=LATER)
        assert base_errors == [], (status, base_errors)
        assert validator.validate_aiml_artifact(base, now=LATER) == [], status
        assert not any(_STRICT_B64_MSG in e for e in base_errors), status
        for label, pem in _PLAINTEXT_SECRET_PEMS.items():
            forged = copy.deepcopy(base)
            forged["operator_signature_pem"] = pem
            forged["self_digest"] = obs.artifact_self_digest(forged)
            errors = obs.validate_pg_observer_bootstrap_result(forged, now=LATER)
            assert any(_STRICT_B64_MSG in e for e in errors), (status, label, errors)
            assert validator.validate_aiml_artifact(forged, now=LATER), (status, label)
            # secret 掃描排除此欄位 → SECRET_LIKE_RE 認得的 plaintext 不被 secret-scan 攔,唯一擋它的是
            # 無條件 strict-base64 檢查。
            assert obs._contains_secret_like(obs._result_secret_scan_view(forged)) is False, (status, label)


def test_fix11_pending_forged_signature_rejected_by_schema_null_pin():
    # FIX-11 縱深防禦:EXTERNAL_VERIFICATION_PENDING 恆以 None emit operator_signature_pem;schema allOf 為
    # 此 status 釘 operator_signature_pem: null。任何非 None 簽章(即使 armor 外殼合法)在 schema 階段即被
    # null 契約擋下(短路於 strict-base64 檢查之前)。同時直接斷言 helper 對該 plaintext PEM 回 False,證明
    # 無條件 strict-base64 語意亦覆蓋 PENDING(即使 schema 未先攔)。legit PENDING(None 簽章)仍 validate []。
    pending = obs.apply_observer_bootstrap(_intent(), None, None, now=NOW, source_head=HEAD)
    assert pending["operator_signature_pem"] is None
    assert obs.validate_pg_observer_bootstrap_result(pending, now=LATER) == []
    assert validator.validate_aiml_artifact(pending, now=LATER) == []
    for label, pem in _PLAINTEXT_SECRET_PEMS.items():
        forged = copy.deepcopy(pending)
        forged["operator_signature_pem"] = pem
        forged["self_digest"] = obs.artifact_self_digest(forged)
        errors = obs.validate_pg_observer_bootstrap_result(forged, now=LATER)
        assert any(_NULL_PIN_MSG in e and "null" in e for e in errors), (label, errors)
        assert validator.validate_aiml_artifact(forged, now=LATER), label
        # 無條件 strict-base64 語意 backstop:即使 schema null 釘先攔,該 plaintext body 本就非嚴格 base64。
        assert obs._operator_signature_pem_body_is_strict_base64(pem) is False, label
    # 縱深:即使帶一份**合法** base64 armor blob,PENDING 也因 null 釘被拒(PENDING 不該帶任何簽章)。
    valid_armor = copy.deepcopy(pending)
    valid_armor["operator_signature_pem"] = _VALID_B64_ARMOR
    valid_armor["self_digest"] = obs.artifact_self_digest(valid_armor)
    assert obs.validate_pg_observer_bootstrap_result(valid_armor, now=LATER)


def test_fix11_exact_e2_repro_forged_pending_plaintext_pem_rejected_by_both():
    # E2(CONFIRMED P2)精確重現:於 EXTERNAL_VERIFICATION_PENDING 夾帶 "password=hunter2" /
    # "pgpassword=s3cr3tpw" 的 operator_signature_pem 並重簽 self_digest。修復前同時通過
    # validate_pg_observer_bootstrap_result 與 central validate_aiml_artifact(0 errors,plaintext 被序列化過
    # 中央閘);FIX-11 後兩者皆拒,plaintext 機密不再過閘。
    pending = obs.apply_observer_bootstrap(_intent(), None, None, now=NOW, source_head=HEAD)
    for pem in _E2_REPRO_PEMS:
        forged = copy.deepcopy(pending)
        forged["operator_signature_pem"] = pem
        forged["self_digest"] = obs.artifact_self_digest(forged)
        assert obs.validate_pg_observer_bootstrap_result(forged, now=LATER), pem
        assert validator.validate_aiml_artifact(forged, now=LATER), pem
        assert pem.split("\n")[1] in json.dumps(forged)  # 機密確實在 payload 中,靠閘門攔下而非「不在」


def test_fix11_schema_pins_pending_signature_null_and_preserves_other_paths():
    # FIX-11 schema 縱深:EXTERNAL_VERIFICATION_PENDING conditional 釘 operator_signature_pem: null;APPLIED
    # conditional 仍釘完整 SSHSIG armor pattern(FIX-7 未變);ROLLED_BACK_INTERRUPTED / NOT_RESTORED_FAILED /
    # FAILED 合法帶真簽章,**不**得被釘 null(交由頂層 armor pattern + 無條件 strict-base64 驗證者覆蓋),避免
    # 過度拒絕。
    schema = json.loads(obs.RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))

    def _conditional_then(status):
        for clause in schema["allOf"]:
            if clause.get("if", {}).get("properties", {}).get("status", {}).get("const") == status:
                return clause["then"].get("properties", {})
        return None

    pending_then = _conditional_then("EXTERNAL_VERIFICATION_PENDING")
    assert pending_then is not None
    assert pending_then.get("operator_signature_pem") == {"type": "null"}
    applied_then = _conditional_then("APPLIED_ROLLED_BACK_EXACT")
    assert applied_then is not None
    armor = applied_then.get("operator_signature_pem", {})
    assert armor.get("type") == "string" and "BEGIN SSH SIGNATURE" in armor.get("pattern", "")
    for status in ("ROLLED_BACK_INTERRUPTED", "NOT_RESTORED_FAILED", "FAILED"):
        then = _conditional_then(status)
        if then is not None:  # 若日後新增專屬 conditional,也絕不得把此欄釘 null
            assert then.get("operator_signature_pem") != {"type": "null"}, status
    # 頂層 operator_signature_pem 仍為 armor-string ∪ null(FIX-7 armor pattern 保留)。
    assert {"type": "null"} in schema["properties"]["operator_signature_pem"]["anyOf"]


def test_fix11_legit_non_exact_real_signature_receipts_not_over_rejected(tmp_path, monkeypatch):
    # 反過度拒絕:ROLLED_BACK_INTERRUPTED / NOT_RESTORED_FAILED 合法帶一份**真** ssh-keygen -Y sign 的
    # armored 簽章(body 去 armor 後為嚴格 base64)→ module 與 central 皆 []。證明 FIX-11 只擋 plaintext,
    # 不誤傷合法簽章。
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent()
    well_formed, signature = _sign(private_key, intent, HEAD)
    assert obs._operator_signature_pem_body_is_strict_base64(signature.decode("ascii")) is True
    for status in ("ROLLED_BACK_INTERRUPTED", "NOT_RESTORED_FAILED"):
        receipt = _offline_result_status(
            intent, status, operator_authorization=well_formed, operator_signature=signature
        )
        assert receipt["operator_signature_pem"].startswith("-----BEGIN SSH SIGNATURE-----")
        assert obs.validate_pg_observer_bootstrap_result(receipt, now=LATER) == [], status
        assert validator.validate_aiml_artifact(receipt, now=LATER) == [], status


# --------------------------------------------------------------------------- #
# guardrails pinned by the task
# --------------------------------------------------------------------------- #
def test_frozen_classifier_digest_unchanged():
    # SCHEMA_FILES 新增四鍵絕不進入 classifier 輸入;S0.3 分類身分 byte-unchanged。
    assert validator.aiml_effect_classifier_digest() == FROZEN_CLASSIFIER


def test_program_schema_paths_untouched_and_schema_files_registered():
    for name in (
        "pg_observer_bootstrap_intent_v1", "pg_observer_bootstrap_result_v1",
        "pg_observer_bootstrap_postcheck_v1", "pg_observer_bootstrap_rollback_v1",
    ):
        assert name in validator.SCHEMA_FILES
        schema_path = f"program_code/ml_training/schemas/aiml_gate_receipts/{name}.schema.json"
        assert schema_path not in validator.PROGRAM_SCHEMA_PATHS


def test_no_secret_serialized_in_pending_result():
    result = obs.apply_observer_bootstrap(_intent(), None, None, now=NOW, source_head=HEAD)
    blob = json.dumps(result)
    assert "password" not in blob.lower()
    assert obs._contains_secret_like(result) is False
