"""LR1(S2.2A)scoped compatibility identity 的單元測試。

以 tmp_path 假 repo 樹覆蓋:docs-only 不停、learning-code 翻轉 quarantine、feature/
label/action-policy 不相容、preflight==spawn==finalize 同一 self_digest、V151-V160
指紋、fail-closed(缺檔/symlink)、以及 receipt round-trip 與竄改偵測。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ml_training import learning_runtime_manifest as lrm
from ml_training.learning_runtime_manifest import (
    CAPTURE_INPUTS,
    DEPENDENCY_LOCK_FILE,
    LEARNING_CODE_INPUTS,
    MIGRATION_INPUTS,
    POLICY_TEMPLATE,
    REGIME_OOS_LABEL_CONTRACT,
    LearningRuntimeManifestError,
    build_learning_runtime_manifest,
    build_source_compatibility_receipt,
    evaluate_compatibility,
    evaluate_runtime_digest_pin,
    try_build_learning_runtime_manifest,
)
from ml_training.aiml_gate_receipt_validator import validate_aiml_artifact


_HEAD_A = "a" * 40
_HEAD_B = "b" * 40

_POLICY_TEMPLATE_BODY = {
    "algorithm_version": "candidate_learning_arbiter_v2",
    "tie_break_version": "candidate_learning_tie_break_v1",
    "q18_scale": 18,
    "thresholds": {"e1_n_eff_min": 30},
    "cooldown_seconds": 1800,
    "unknown_portfolio_penalty": "1",
    "row_budget": None,
    "byte_budget": None,
}


def _write(root: Path, rel: str, content: bytes) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _make_fake_repo(root: Path) -> None:
    """建置一棵含全部 allowlisted 輸入的最小假 repo 樹。"""
    for rel in CAPTURE_INPUTS:
        _write(root, rel, f"# capture {rel}\n".encode("utf-8"))
    for rel in LEARNING_CODE_INPUTS:
        _write(root, rel, f"# learning {rel}\n".encode("utf-8"))
    for rel in MIGRATION_INPUTS:
        _write(root, rel, f"-- migration {rel}\n".encode("utf-8"))
    _write(root, REGIME_OOS_LABEL_CONTRACT, b'SCHEMA_VERSION = "regime_v1"\n')
    _write(root, POLICY_TEMPLATE, json.dumps(_POLICY_TEMPLATE_BODY).encode("utf-8"))
    _write(root, DEPENDENCY_LOCK_FILE, b"numpy==1.0\n")


@pytest.fixture()
def fake_repo(tmp_path: Path) -> Path:
    _make_fake_repo(tmp_path)
    return tmp_path


# ── (1) docs-only 不停 ────────────────────────────────────────────────────────
def test_docs_only_change_and_head_move_does_not_change_component_digests(
    fake_repo: Path,
) -> None:
    m1 = build_learning_runtime_manifest(fake_repo, repo_source_head=_HEAD_A)
    # 改一個「非 allowlisted」檔(README) + 換 HEAD:純遙測移動,不動任何元件 digest。
    _write(fake_repo, "README.md", b"docs only change\n")
    m2 = build_learning_runtime_manifest(fake_repo, repo_source_head=_HEAD_B)

    assert m1["capture_contract"]["digest"] == m2["capture_contract"]["digest"]
    assert m1["training_contract"]["digest"] == m2["training_contract"]["digest"]
    assert m1["self_digest"] == m2["self_digest"]
    assert m1["repo_source_head"] != m2["repo_source_head"]

    compat = evaluate_compatibility(m1, m2)
    assert compat["capture_status"] == "COMPATIBLE"
    assert compat["fit_status"] == "COMPATIBLE"
    assert compat["manifest_identical"] is True


def test_pin_reduction_keeps_capture_running_on_docs_only(fake_repo: Path) -> None:
    m1 = build_learning_runtime_manifest(fake_repo, repo_source_head=_HEAD_A)
    _write(fake_repo, "docs/whatever.md", b"docs\n")
    m2 = build_learning_runtime_manifest(fake_repo, repo_source_head=_HEAD_B)
    compat = evaluate_runtime_digest_pin(m1["self_digest"], m2)
    assert compat["capture_status"] == "COMPATIBLE"
    assert compat["fit_status"] == "COMPATIBLE"


# ── (2) learning-code 翻轉 ⇒ fit QUARANTINE、capture 不變 ─────────────────────
def test_learning_code_flip_quarantines_fit_but_keeps_capture(fake_repo: Path) -> None:
    baseline = build_learning_runtime_manifest(fake_repo, repo_source_head=_HEAD_A)
    _write(
        fake_repo,
        LEARNING_CODE_INPUTS[0],
        b"# learning code mutated\n",
    )
    flipped = build_learning_runtime_manifest(fake_repo, repo_source_head=_HEAD_A)

    assert baseline["capture_contract"]["digest"] == flipped["capture_contract"]["digest"]
    assert baseline["training_contract"]["digest"] != flipped["training_contract"]["digest"]

    compat = evaluate_compatibility(baseline, flipped)
    assert compat["capture_status"] == "COMPATIBLE"
    assert compat["fit_status"] == "QUARANTINE"
    assert "training_contract_digest_changed" in compat["quarantine_reasons"]


def test_capture_code_flip_stops_capture(fake_repo: Path) -> None:
    baseline = build_learning_runtime_manifest(fake_repo, repo_source_head=_HEAD_A)
    _write(fake_repo, CAPTURE_INPUTS[0], b"# capture code mutated\n")
    flipped = build_learning_runtime_manifest(fake_repo, repo_source_head=_HEAD_A)
    compat = evaluate_compatibility(baseline, flipped)
    assert compat["capture_status"] == "INCOMPATIBLE"
    assert "capture_contract_digest_changed" in compat["capture_stop_reasons"]


# ── (3) feature/label/action-policy 不相容 ⇒ fit QUARANTINE ───────────────────
def test_label_contract_flip_quarantines_fit(fake_repo: Path) -> None:
    baseline = build_learning_runtime_manifest(fake_repo, repo_source_head=_HEAD_A)
    _write(fake_repo, REGIME_OOS_LABEL_CONTRACT, b'SCHEMA_VERSION = "regime_v2"\n')
    flipped = build_learning_runtime_manifest(fake_repo, repo_source_head=_HEAD_A)
    assert evaluate_compatibility(baseline, flipped)["fit_status"] == "QUARANTINE"


def test_action_policy_flip_quarantines_fit(fake_repo: Path) -> None:
    baseline = build_learning_runtime_manifest(fake_repo, repo_source_head=_HEAD_A)
    changed = dict(_POLICY_TEMPLATE_BODY)
    changed["cooldown_seconds"] = 3600
    _write(fake_repo, POLICY_TEMPLATE, json.dumps(changed).encode("utf-8"))
    flipped = build_learning_runtime_manifest(fake_repo, repo_source_head=_HEAD_A)
    assert evaluate_compatibility(baseline, flipped)["fit_status"] == "QUARANTINE"


def test_feature_contract_flip_quarantines_fit(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = build_learning_runtime_manifest(fake_repo, repo_source_head=_HEAD_A)
    monkeypatch.setattr(
        lrm, "compute_feature_schema_hash", lambda names: "sha256:feature-drift"
    )
    flipped = build_learning_runtime_manifest(fake_repo, repo_source_head=_HEAD_A)
    assert baseline["capture_contract"]["digest"] == flipped["capture_contract"]["digest"]
    assert evaluate_compatibility(baseline, flipped)["fit_status"] == "QUARANTINE"


# ── (4) preflight==spawn==finalize 同一 self_digest;竄改 finalize ⇒ mismatch ──
def test_three_builds_share_identical_self_digest(fake_repo: Path) -> None:
    preflight = build_learning_runtime_manifest(
        fake_repo, repo_source_head=_HEAD_A, generated_at_utc="2026-07-24T00:00:00Z"
    )
    spawn = build_learning_runtime_manifest(
        fake_repo, repo_source_head=_HEAD_B, generated_at_utc="2026-07-24T01:00:00Z"
    )
    finalize = build_learning_runtime_manifest(
        fake_repo, repo_source_head=_HEAD_A, generated_at_utc="2026-07-24T02:00:00Z"
    )
    assert preflight["self_digest"] == spawn["self_digest"] == finalize["self_digest"]


def test_tampered_finalize_digest_is_detected(fake_repo: Path) -> None:
    spawn = build_learning_runtime_manifest(fake_repo, repo_source_head=_HEAD_A)
    # 竄改 finalize 的 training digest → fit 面立即偵測為 QUARANTINE(capture 不受影響)。
    finalize = build_learning_runtime_manifest(fake_repo, repo_source_head=_HEAD_A)
    finalize["training_contract"]["digest"] = "sha256:" + "0" * 64
    compat = evaluate_compatibility(spawn, finalize)
    assert compat["fit_status"] == "QUARANTINE"
    assert compat["capture_status"] == "COMPATIBLE"
    # 竄改 self_digest → 身分不再相同(manifest_identical=False)。
    tampered_identity = build_learning_runtime_manifest(fake_repo, repo_source_head=_HEAD_A)
    tampered_identity["self_digest"] = "sha256:" + "0" * 64
    assert evaluate_compatibility(spawn, tampered_identity)["manifest_identical"] is False


# ── (5) V151-V160 指紋:翻轉一個 migration byte ⇒ training digest 變 ──────────
def test_migration_byte_flip_changes_training_contract_digest(fake_repo: Path) -> None:
    baseline = build_learning_runtime_manifest(fake_repo, repo_source_head=_HEAD_A)
    fingerprints = baseline["training_contract"]["components"]["migration_fingerprints"]
    assert len(fingerprints) == 10
    assert sorted(name.split("__", 1)[0] for name in fingerprints) == [
        f"V{index}" for index in range(151, 161)
    ]
    _write(fake_repo, MIGRATION_INPUTS[4], b"-- migration mutated byte\n")
    flipped = build_learning_runtime_manifest(fake_repo, repo_source_head=_HEAD_A)
    assert baseline["training_contract"]["digest"] != flipped["training_contract"]["digest"]
    assert evaluate_compatibility(baseline, flipped)["fit_status"] == "QUARANTINE"


def test_missing_migration_span_fails_closed(fake_repo: Path) -> None:
    (fake_repo / MIGRATION_INPUTS[9]).unlink()
    manifest, errors = try_build_learning_runtime_manifest(
        fake_repo, repo_source_head=_HEAD_A
    )
    assert manifest is None
    assert errors and "V160" in errors[0]


# ── (6) fail-closed:缺檔 / symlink ⇒ 兩者 INDETERMINATE ─────────────────────
def test_missing_allowlisted_input_is_indeterminate_on_both(fake_repo: Path) -> None:
    good = build_learning_runtime_manifest(fake_repo, repo_source_head=_HEAD_A)
    (fake_repo / LEARNING_CODE_INPUTS[3]).unlink()
    manifest, errors = try_build_learning_runtime_manifest(
        fake_repo, repo_source_head=_HEAD_A
    )
    assert manifest is None and errors
    compat = evaluate_compatibility(good, manifest)
    assert compat["capture_status"] == "INDETERMINATE"
    assert compat["fit_status"] == "INDETERMINATE"


def test_symlink_input_is_indeterminate_on_both(fake_repo: Path) -> None:
    good = build_learning_runtime_manifest(fake_repo, repo_source_head=_HEAD_A)
    target = CAPTURE_INPUTS[1]
    (fake_repo / target).unlink()
    (fake_repo / target).symlink_to(fake_repo / CAPTURE_INPUTS[0])
    manifest, errors = try_build_learning_runtime_manifest(
        fake_repo, repo_source_head=_HEAD_A
    )
    assert manifest is None
    assert errors and errors[0].startswith("symlink_input:")
    compat = evaluate_compatibility(good, manifest)
    assert compat["capture_status"] == "INDETERMINATE"
    assert compat["fit_status"] == "INDETERMINATE"


def test_pin_reduction_fails_closed_on_build_error(fake_repo: Path) -> None:
    (fake_repo / CAPTURE_INPUTS[0]).unlink()
    manifest, _ = try_build_learning_runtime_manifest(
        fake_repo, repo_source_head=_HEAD_A
    )
    compat = evaluate_runtime_digest_pin("sha256:" + "1" * 64, manifest)
    assert compat["capture_status"] == "INDETERMINATE"
    assert compat["fit_status"] == "INDETERMINATE"


def test_bad_repo_source_head_fails_closed(fake_repo: Path) -> None:
    with pytest.raises(LearningRuntimeManifestError):
        build_learning_runtime_manifest(fake_repo, repo_source_head="not-a-head")


# ── (7) receipt round-trip 與竄改偵測 ────────────────────────────────────────
def test_receipt_round_trips_and_validates(fake_repo: Path) -> None:
    receipt = build_source_compatibility_receipt(
        fake_repo, repo_source_head=_HEAD_A, generated_at_utc="2026-07-24T00:00:00Z"
    )
    assert receipt["status"] == "SOURCE_READY"
    assert receipt["session_id"] == "S2.2A"
    assert receipt["learning_runtime_digest"] == receipt["learning_runtime_manifest"]["self_digest"]
    reloaded = json.loads(json.dumps(receipt))
    assert validate_aiml_artifact(reloaded) == []


def test_receipt_tampered_self_digest_fails_validation(fake_repo: Path) -> None:
    receipt = build_source_compatibility_receipt(fake_repo, repo_source_head=_HEAD_A)
    receipt["self_digest"] = "sha256:" + "0" * 64
    assert validate_aiml_artifact(receipt) != []


def test_receipt_learning_runtime_digest_must_bind_manifest(fake_repo: Path) -> None:
    receipt = build_source_compatibility_receipt(fake_repo, repo_source_head=_HEAD_A)
    receipt["learning_runtime_digest"] = "sha256:" + "1" * 64
    errors = validate_aiml_artifact(receipt)
    assert any("learning_runtime_digest" in error for error in errors)
