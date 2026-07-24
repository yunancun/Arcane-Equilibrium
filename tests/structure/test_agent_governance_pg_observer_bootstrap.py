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
    # 即使帶一張 VALID operator SSHSIG,WP2 SOURCE lane 也絕不開生產 socket:恆 pending。
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent(target_class="production")
    authorization, signature = _sign(private_key, intent, HEAD)
    assert obs.validate_operator_authorization(
        authorization, signature, intent=intent, source_head=HEAD, now=NOW
    ) == []
    result = obs.apply_observer_bootstrap(intent, authorization, signature, now=NOW, source_head=HEAD)
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert "deferred to the S2.0 EFFECT session" in result["failure_reason"]
    assert result["boundary"]["nine_authorities_false"] is True


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
