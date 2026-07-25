"""W0 (WP4) source-implementation admission alignment — always-run offline tests.

These need NO PostgreSQL / no runtime. They prove the central-validator DERIVES
``ADMITTED``/``PASS`` from repository re-derivation and never from a caller-supplied
status:

- derived-``ADMITTED`` happy path with a REAL receipt (actual current source_head,
  the exact §1.2 predecessor merges, freshly recomputed projection/trust-pin/driver
  digests);
- reject a self-declared ``status``/``pass``/``done`` (§10.5 #27);
- reject the old ``S2.1@EFFECT_DONE``-before-``S2.4`` effect chain if a projection
  reintroduces it (§10.5 #20);
- reject a WP3 ``systemctl --user`` production path from the WP3 executable
  constants (§10.5 #20);
- tamper each predecessor head / trust pin / projection digest / driver-reachability
  flag → derivation returns non-``ADMITTED`` (§10.5 #27);
- frozen S0.3 classifier + v1 component-classifier bytes unchanged after adding the
  two W0 schemas (§10.5 #2);
- PR #132 projection + PR #134 WP3 system-level property present.

The admission receipt is SOURCE evidence: nine authorities false,
production_apply_performed false, running_attested false. The derivation
authenticates the INTEGRITY of the source seams, never a runtime.
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import aiml_gate_receipt_validator as validator  # noqa: E402
import agent_governance_alr_quiesce_inventory as inventory  # noqa: E402


def _current_head() -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _build_admission_receipt(source_head: str) -> dict:
    """A REAL, derivation-passing admission receipt built from live repo bytes."""

    module_bytes = (ROOT / validator._TRUSTED_HOST_MODULE_PATH).read_bytes()
    test_bytes = (ROOT / validator._TRUSTED_HOST_TEST_PATH).read_bytes()
    receipt = {
        "schema_version": "s2_4_source_admission_receipt_v1",
        "program_id": "AIML-LONG-LIVED-LANDING-V2",
        "work_package": "WP4",
        "wave": "W0",
        "source_head": source_head,
        "predecessor_heads": dict(validator._PREDECESSOR_HEADS),
        "three_head_projection_digest": validator.three_head_projection_digest(),
        "trust_pin_digests": {
            "trusted_host_module_blob": validator.git_blob_sha1(module_bytes),
            "trusted_host_module_sha256": "sha256:" + hashlib.sha256(module_bytes).hexdigest(),
            "independent_test_blob": validator.git_blob_sha1(test_bytes),
            "independent_test_sha256": "sha256:" + hashlib.sha256(test_bytes).hexdigest(),
            "operator_fingerprint": validator._OPERATOR_FINGERPRINT,
        },
        "s2_0_driver_reachability_proof": {
            "adapter_id": "pg_observer_bootstrap_adapter_v1",
            "registry_status": "AUTHORITY_LOCKED_PRODUCTION_CAPABLE",
            "unconditional_production_pending_removed": True,
            "driver_protocol_present": True,
            "production_success_status": "APPLIED",
        },
        "wp3_system_unit_alignment_proof": {
            "lifecycle_owner": "host_system_manager",
            "systemctl_user_absent": True,
            "role": "aiml_engine_scanner",
            "database": "trading_ai",
        },
        "frozen_classifier_digest": validator.aiml_effect_classifier_digest(),
        "component_classifier_v1_digest": validator.aiml_component_effect_class_matrix_digest(),
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
        "negative_tests_pass": validator.canonical_digest(
            ["reject_old_chain", "reject_systemctl_user", "reject_self_declared_status"]
        ),
    }
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    return receipt


def _build_wave_exit_receipt(admission: dict) -> dict:
    receipt = {
        "schema_version": "s2_4_wave_exit_receipt_v1",
        "wave": "W0",
        "predecessor_wave_receipt_digest": None,
        "source_admission_receipt_digest": admission["self_digest"],
        "source_head": admission["source_head"],
        "owned_path_manifest_digest": validator.canonical_digest(
            sorted(validator._W0_OWNED_PATHS)
        ),
        "owned_path_diff_digest": validator.canonical_digest(["w0b-diff"]),
        "exported_abi_digest": validator.canonical_digest(validator._W0_EXPORTED_ABI),
        "test_digests": [validator.canonical_digest(["test_s2_4_w0_admission"])],
        "capture_digests": [],
        "review_fragment_digests": [],
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
    }
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    return receipt


# ── happy path ───────────────────────────────────────────────────────────────


def test_source_admission_derives_admitted_on_real_receipt() -> None:
    receipt = _build_admission_receipt(_current_head())
    result = validator.derive_source_admission_status(receipt)
    assert result == {"status": "ADMITTED", "reasons": []}
    # central gate returns [] (schema + full derivation)
    assert validator.validate_aiml_artifact(receipt) == []


def test_wave_exit_derives_pass_when_bound_admission_is_admitted() -> None:
    admission = _build_admission_receipt(_current_head())
    wave_exit = _build_wave_exit_receipt(admission)
    result = validator.derive_wave_exit_status(
        wave_exit, source_admission_receipt=admission
    )
    assert result == {"status": "PASS", "reasons": []}
    # central gate (no bound admission) still validates the self-contained structure
    assert validator.validate_aiml_artifact(wave_exit) == []


# ── §10.5 #27: caller cannot self-declare a status ───────────────────────────


@pytest.mark.parametrize("field, value", [
    ("status", "ADMITTED"),
    ("pass", True),
    ("done", True),
    ("admitted", True),
])
def test_reject_self_declared_admission_status(field: str, value) -> None:
    receipt = _build_admission_receipt(_current_head())
    receipt[field] = value
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any("must not self-declare status" in reason for reason in result["reasons"])
    # the closed schema also rejects it at the central gate
    assert validator.validate_aiml_artifact(receipt) != []


@pytest.mark.parametrize("field, value", [
    ("status", "PASS"),
    ("pass", True),
    ("done", True),
])
def test_reject_self_declared_wave_exit_status(field: str, value) -> None:
    admission = _build_admission_receipt(_current_head())
    wave_exit = _build_wave_exit_receipt(admission)
    wave_exit[field] = value
    wave_exit["self_digest"] = validator.artifact_self_digest(wave_exit)
    result = validator.derive_wave_exit_status(
        wave_exit, source_admission_receipt=admission
    )
    assert result["status"] == "NOT_PASS"
    assert any("must not self-declare status" in reason for reason in result["reasons"])
    assert validator.validate_aiml_artifact(wave_exit) != []


# ── §10.5 #20: reject the old effect chain / a --user WP3 path ────────────────


def test_reject_old_effect_chain_if_reintroduced_into_a_projection() -> None:
    # a projection that reverted the canonical apply-order back to the old
    # S2.1@EFFECT_DONE-before-S2.4 chain (new chain absent) is rejected.
    old_chain_only = "operator apply order: S2.0→S2.1→S2.4→S2.5→S2.2B (old cycle)"
    errors = validator._projection_effect_dag_errors({"TODO.md": old_chain_only})
    assert errors and all("missing the canonical" in e for e in errors)
    # the real repo projections DO carry the new canonical chain.
    real_texts = validator._read_three_head_texts(ROOT)
    assert validator._projection_effect_dag_errors(real_texts) == []


def test_reject_wp3_systemctl_user_production_path_from_executable_constants() -> None:
    # the WP3 executable allowlist executably rejects any `--user` (user-systemd) form;
    # only the system-level manager path is admitted (PR #134 system-level property).
    with pytest.raises(Exception):
        inventory._assert_allowlisted_systemctl(
            [inventory.SYSTEMD, "--user", "show", inventory.UNIT_NAME]
        )
    inventory._assert_allowlisted_systemctl(
        [inventory.SYSTEMD, "show", inventory.UNIT_NAME]
    )
    assert inventory.SYSTEMD == "/usr/bin/systemctl"
    # a receipt claiming a user-systemd WP3 path fails the derived property re-check.
    receipt = _build_admission_receipt(_current_head())
    receipt["wp3_system_unit_alignment_proof"]["systemctl_user_absent"] = False
    receipt["wp3_system_unit_alignment_proof"]["lifecycle_owner"] = "user_systemd"
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any("wp3_system_unit_alignment_proof" in r for r in result["reasons"])


# ── §10.5 #27: tamper each re-derived input → non-ADMITTED ────────────────────


def test_tamper_predecessor_head_breaks_admission() -> None:
    receipt = _build_admission_receipt(_current_head())
    receipt["predecessor_heads"]["wp3_system_unit_merge"] = "0" * 40
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any("predecessor" in r for r in result["reasons"])


def test_tamper_trust_pin_breaks_admission() -> None:
    receipt = _build_admission_receipt(_current_head())
    receipt["trust_pin_digests"]["trusted_host_module_sha256"] = "sha256:" + "0" * 64
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any("trust pin" in r for r in result["reasons"])


def test_tamper_operator_fingerprint_breaks_admission() -> None:
    receipt = _build_admission_receipt(_current_head())
    receipt["trust_pin_digests"]["operator_fingerprint"] = "SHA256:" + "A" * 43
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any("operator_fingerprint" in r or "trust pin" in r for r in result["reasons"])


def test_tamper_projection_digest_breaks_admission() -> None:
    receipt = _build_admission_receipt(_current_head())
    receipt["three_head_projection_digest"] = "sha256:" + "0" * 64
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any("three_head_projection_digest" in r for r in result["reasons"])


def test_tamper_driver_reachability_flag_breaks_admission() -> None:
    receipt = _build_admission_receipt(_current_head())
    receipt["s2_0_driver_reachability_proof"]["unconditional_production_pending_removed"] = False
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any("s2_0_driver_reachability_proof" in r for r in result["reasons"])


def test_tamper_frozen_classifier_digest_breaks_admission() -> None:
    receipt = _build_admission_receipt(_current_head())
    receipt["frozen_classifier_digest"] = "sha256:" + "0" * 64
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any("frozen_classifier_digest" in r for r in result["reasons"])


def test_tamper_production_flag_true_breaks_admission() -> None:
    receipt = _build_admission_receipt(_current_head())
    receipt["production_authority_flags"]["production_apply_performed"] = True
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any("production_authority_flags" in r for r in result["reasons"])


# ── §10.5 #2: frozen S0.3 + v1 component bytes unchanged after the schemas ────


def test_frozen_classifier_and_component_v1_unchanged_after_registering_w0_schemas() -> None:
    assert validator.aiml_effect_classifier_digest() == (
        "sha256:1cf8c021b066ceeb364e968add074d263cb28d63db421fdc40620e9904d0ddbc"
    )
    assert validator.aiml_component_effect_class_matrix_digest() == (
        "sha256:22d78882a2dace9ceb640b74b2a5dca2f2a8cc05861720f5ab25c5c9ac86c445"
    )
    # the two W0 schemas are registered in SCHEMA_FILES only (schema lookup), never in
    # PROGRAM_SCHEMA_PATHS (the fixed 7-name S0.3 tuple) — proving the classifier inputs
    # are untouched.
    for key in ("s2_4_source_admission_receipt_v1", "s2_4_wave_exit_receipt_v1"):
        assert key in validator.SCHEMA_FILES
        assert (validator.SCHEMA_DIR / validator.SCHEMA_FILES[key]).is_file()
    assert len(validator.PROGRAM_SCHEMA_PATHS) == 7
    for key in ("s2_4_source_admission_receipt_v1", "s2_4_wave_exit_receipt_v1"):
        assert not any(key in path for path in validator.PROGRAM_SCHEMA_PATHS)


# ── PR #132 projection + PR #134 WP3 system-level property present ─────────────


def test_pr132_projection_and_pr134_wp3_property_present() -> None:
    # PR #132 effect-DAG projection + PR #134 WP3 unit merge are the exact §1.2 lineage.
    assert validator._PREDECESSOR_HEADS == {
        "program_dag_projection_merge": "4915be30c4214f8a3d591b7f9259169cdb65c75b",
        "wp3_system_unit_merge": "e514f1e761ab9c1965a133f1f113e2e7ccd854df",
    }
    # both are ancestors of the current source_head.
    head = _current_head()
    for merge in validator._PREDECESSOR_HEADS.values():
        assert validator._git_is_ancestor(ROOT, merge, head)
    # PR #132 projection: the corrected effect DAG is present in all three docs.
    assert validator._projection_effect_dag_errors(
        validator._read_three_head_texts(ROOT)
    ) == []
    # PR #134 WP3 system-level property re-derives (role + no --user), property-only
    # (NOT bound to the exact unit name — §7 #4 defers that to W2).
    assert validator._wp3_system_unit_property_errors({
        "lifecycle_owner": "host_system_manager",
        "systemctl_user_absent": True,
        "role": "aiml_engine_scanner",
        "database": "trading_ai",
    }) == []
