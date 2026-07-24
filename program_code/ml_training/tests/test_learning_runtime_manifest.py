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
    DEPENDENCY_LOCK_LOCK_FILE,
    DEPENDENCY_LOCK_SPEC_FILE,
    LEARNING_CODE_INPUTS,
    LEARNING_CODE_INPUTS_V2,
    MIGRATION_INPUTS,
    POLICY_TEMPLATE,
    REGIME_OOS_LABEL_CONTRACT,
    LearningRuntimeManifestError,
    build_learning_runtime_manifest,
    build_learning_runtime_manifest_v2,
    build_source_compatibility_receipt,
    build_source_compatibility_receipt_v2,
    evaluate_compatibility,
    try_build_learning_runtime_manifest,
    try_build_learning_runtime_manifest_v2,
)
from ml_training.aiml_gate_receipt_validator import (
    artifact_self_digest,
    validate_aiml_artifact,
)


import hashlib
import shutil


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


def test_receipt_inner_capture_input_forgery_is_rejected(fake_repo: Path) -> None:
    # 攻擊者竄改內層 capture inputs 的一個值,但保持 capture_contract.digest 不變,並只
    # 重封「外層」receipt self_digest 讓外層自洽——validator 內層反偽造重算必攔下。
    receipt = build_source_compatibility_receipt(fake_repo, repo_source_head=_HEAD_A)
    inputs = receipt["learning_runtime_manifest"]["capture_contract"]["inputs"]
    inputs[sorted(inputs)[0]] = "0" * 64
    receipt["self_digest"] = artifact_self_digest(receipt)
    errors = validate_aiml_artifact(receipt)
    assert any("capture_contract.digest does not bind its inputs" in e for e in errors)


def test_receipt_inner_component_forgery_is_rejected(fake_repo: Path) -> None:
    # 竄改內層 training component(feature_contract_digest),不動 training_contract.digest,
    # 只重封外層 self_digest——validator 重算 training digest 必攔下。
    receipt = build_source_compatibility_receipt(fake_repo, repo_source_head=_HEAD_A)
    components = receipt["learning_runtime_manifest"]["training_contract"]["components"]
    components["feature_contract_digest"] = "sha256:" + "0" * 64
    receipt["self_digest"] = artifact_self_digest(receipt)
    errors = validate_aiml_artifact(receipt)
    assert any("training_contract.digest does not bind its components" in e for e in errors)


# ── (8) committed receipt 抗漂移(NON-tmp_path:對真實 checkout 重建) ────────────
def test_committed_receipt_matches_real_checkout_rebuild() -> None:
    # 由真實 repo checkout 重建清單,並斷言 committed receipt 的三個 HEAD-independent
    # digest 與重建結果一致;任何漂移(如編輯了 allowlisted 檔卻沒重生 receipt)即紅燈。
    repo_root = Path(__file__).resolve().parents[3]
    receipt_path = (
        repo_root
        / "docs"
        / "execution_plan"
        / "ai_ml_landing"
        / "receipts"
        / "S2.2A-source-compatibility-receipt-v1.json"
    )
    assert receipt_path.is_file(), f"missing committed receipt at {receipt_path}"
    committed = json.loads(receipt_path.read_text(encoding="utf-8"))
    # 注入固定 head 以避免對 git 的依賴;三個 digest 皆為 HEAD-independent。
    rebuilt = build_learning_runtime_manifest(repo_root, repo_source_head="0" * 40)
    assert committed["learning_runtime_digest"] == rebuilt["self_digest"]
    assert committed["capture_contract_digest"] == rebuilt["capture_contract"]["digest"]
    assert committed["training_contract_digest"] == rebuilt["training_contract"]["digest"]
    assert (
        committed["migration_fingerprints"]
        == rebuilt["training_contract"]["components"]["migration_fingerprints"]
    )


# ── (9) v2(learning_runtime_manifest_v2)additive 身分 ────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[3]
_V1_FROZEN_DIGEST = (
    "sha256:6cf76b60a763035d26d0d4e9e0e6aa0aa8877d99966367c778420e5f63a79595"
)
_COMMITTED_V2_RECEIPT = (
    _REPO_ROOT
    / "docs/execution_plan/ai_ml_landing/receipts"
    / "S2.2A-source-compatibility-receipt-v2.json"
)


def _serialize_receipt(payload: dict) -> str:
    # 必須與 _write_json 的序列化逐位元一致(byte-equality drift 檢查)。
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def test_v2_is_distinct_identity_and_v1_stays_byte_frozen() -> None:
    # v1 身分不動(仍 6cf76b60);v2 因 schema_version + dependency_lock + parquet_etl 而相異;
    # capture 面兩者相同(v2 只強化 training)。
    v1 = build_learning_runtime_manifest(_REPO_ROOT, repo_source_head="0" * 40)
    v2 = build_learning_runtime_manifest_v2(_REPO_ROOT, repo_source_head="0" * 40)
    assert v1["self_digest"] == _V1_FROZEN_DIGEST
    assert v2["schema_version"] == "learning_runtime_manifest_v2"
    assert v2["self_digest"] != v1["self_digest"]
    assert v2["capture_contract"]["digest"] == v1["capture_contract"]["digest"]
    assert v2["training_contract"]["digest"] != v1["training_contract"]["digest"]


def test_v2_dependency_lock_binds_both_spec_and_sealed_lock() -> None:
    # v2 dependency_lock = {spec_digest(requirements-ml.txt), lock_digest(requirements-ml.lock)}。
    v2 = build_learning_runtime_manifest_v2(_REPO_ROOT, repo_source_head="0" * 40)
    dependency_lock = v2["training_contract"]["components"]["dependency_lock"]
    assert set(dependency_lock) == {"spec_digest", "lock_digest"}
    spec_sha = hashlib.sha256(
        (_REPO_ROOT / DEPENDENCY_LOCK_SPEC_FILE).read_bytes()
    ).hexdigest()
    lock_sha = hashlib.sha256(
        (_REPO_ROOT / DEPENDENCY_LOCK_LOCK_FILE).read_bytes()
    ).hexdigest()
    assert dependency_lock["spec_digest"] == "sha256:" + spec_sha
    assert dependency_lock["lock_digest"] == "sha256:" + lock_sha
    # spec 面與 v1 scalar dependency_lock_digest 同源(requirements-ml.txt);lock 面為 v2 新綁。
    v1 = build_learning_runtime_manifest(_REPO_ROOT, repo_source_head="0" * 40)
    assert (
        v1["training_contract"]["components"]["dependency_lock_digest"]
        == dependency_lock["spec_digest"]
    )
    assert dependency_lock["lock_digest"] != dependency_lock["spec_digest"]


def test_v2_learning_code_digest_folds_parquet_etl_compute() -> None:
    # B.3:parquet_etl.py 併入 v2 learning-code allowlist(v1 只綁特徵名+schema 版本,漏 COMPUTE)。
    assert "program_code/ml_training/parquet_etl.py" in LEARNING_CODE_INPUTS_V2
    assert "program_code/ml_training/parquet_etl.py" not in LEARNING_CODE_INPUTS
    assert len(LEARNING_CODE_INPUTS_V2) == len(LEARNING_CODE_INPUTS) + 1
    v1 = build_learning_runtime_manifest(_REPO_ROOT, repo_source_head="0" * 40)
    v2 = build_learning_runtime_manifest_v2(_REPO_ROOT, repo_source_head="0" * 40)
    assert (
        v2["training_contract"]["components"]["learning_code_digest"]
        != v1["training_contract"]["components"]["learning_code_digest"]
    )


def test_v2_receipt_round_trips_and_validates() -> None:
    receipt = build_source_compatibility_receipt_v2(
        _REPO_ROOT, repo_source_head="0" * 40, generated_at_utc="2026-07-24T00:00:00Z"
    )
    assert receipt["schema_version"] == "source_compatibility_receipt_v2"
    assert receipt["session_id"] == "S2.2A"
    assert receipt["learning_runtime_digest"] == receipt["learning_runtime_manifest"]["self_digest"]
    assert validate_aiml_artifact(json.loads(json.dumps(receipt))) == []


def test_v2_build_fails_closed_without_valid_lock(fake_repo: Path) -> None:
    # fake_repo 無有效 requirements-ml.lock(且缺 parquet_etl.py)→ v2 建置 fail-closed。
    manifest, errors = try_build_learning_runtime_manifest_v2(
        fake_repo, repo_source_head=_HEAD_A
    )
    assert manifest is None
    assert errors


def test_committed_v2_receipt_head_independent_digests_match_rebuild() -> None:
    # 抗漂移(mirror v1 §8):三個 HEAD-independent digest 必等於真 checkout 的 v2 重建;
    # 任何 allowlisted 檔(含 parquet_etl / requirements-ml.lock)被改卻沒重生 receipt 即紅。
    assert _COMMITTED_V2_RECEIPT.is_file(), f"missing committed v2 receipt {_COMMITTED_V2_RECEIPT}"
    committed = json.loads(_COMMITTED_V2_RECEIPT.read_text(encoding="utf-8"))
    rebuilt = build_learning_runtime_manifest_v2(_REPO_ROOT, repo_source_head="0" * 40)
    assert committed["learning_runtime_digest"] == rebuilt["self_digest"]
    assert committed["capture_contract_digest"] == rebuilt["capture_contract"]["digest"]
    assert committed["training_contract_digest"] == rebuilt["training_contract"]["digest"]


def test_committed_v2_receipt_rebuilds_byte_for_byte() -> None:
    # B.4/B.5 PR-time receipt-freshness:以 committed 的 head+time 重建,斷言逐位元相等——
    # stale pin(改了 allowlisted 檔卻沒重生 receipt)無法靜默出貨。head 取自 receipt(免 git 依賴)。
    committed_text = _COMMITTED_V2_RECEIPT.read_text(encoding="utf-8")
    committed = json.loads(committed_text)
    rebuilt = build_source_compatibility_receipt_v2(
        _REPO_ROOT,
        repo_source_head=committed["repo_source_head"],
        generated_at_utc=committed["generated_at_utc"],
    )
    assert committed == rebuilt
    assert committed_text == _serialize_receipt(rebuilt)


def test_v2_receipt_lock_digest_forgery_is_rejected() -> None:
    # B.5 forgery:交換內層 dependency_lock.lock_digest,只重封外層 self_digest——中央閘由
    # training_contract.digest 重算綁定整個 components,必攔下。
    receipt = build_source_compatibility_receipt_v2(_REPO_ROOT, repo_source_head="0" * 40)
    components = receipt["learning_runtime_manifest"]["training_contract"]["components"]
    components["dependency_lock"]["lock_digest"] = "sha256:" + "0" * 64
    receipt["self_digest"] = artifact_self_digest(receipt)
    errors = validate_aiml_artifact(receipt)
    assert any("training_contract.digest does not bind its components" in e for e in errors)


def test_v2_receipt_spec_digest_forgery_is_rejected() -> None:
    # E4 nit-2a(mirror lock_digest):交換 dependency_lock.spec_digest,只重封外層 self_digest →
    # 中央閘由 training_contract.digest 重算綁定整個 components,必攔下(訊息特定)。
    receipt = build_source_compatibility_receipt_v2(_REPO_ROOT, repo_source_head="0" * 40)
    components = receipt["learning_runtime_manifest"]["training_contract"]["components"]
    components["dependency_lock"]["spec_digest"] = "sha256:" + "0" * 64
    receipt["self_digest"] = artifact_self_digest(receipt)
    errors = validate_aiml_artifact(receipt)
    assert any("training_contract.digest does not bind its components" in e for e in errors)


def test_v2_receipt_malformed_dependency_lock_shape_is_rejected() -> None:
    # E4 nit-2b:dependency_lock 形狀畸形(缺鍵 / 多鍵 / digest 格式錯)→ v2 schema
    # $defs/dependency_lock(additionalProperties=false / required / pattern)在 schema_subset 攔下。
    base = build_source_compatibility_receipt_v2(_REPO_ROOT, repo_source_head="0" * 40)

    def _mutate(fn) -> list[str]:
        receipt = json.loads(json.dumps(base))
        dependency_lock = receipt["learning_runtime_manifest"]["training_contract"][
            "components"
        ]["dependency_lock"]
        fn(dependency_lock)
        receipt["self_digest"] = artifact_self_digest(receipt)
        return validate_aiml_artifact(receipt)

    missing = _mutate(lambda dependency_lock: dependency_lock.pop("lock_digest"))
    assert any("missing required property lock_digest" in e for e in missing), missing
    extra = _mutate(lambda dependency_lock: dependency_lock.__setitem__("extra", "x"))
    assert any("unexpected property extra" in e for e in extra), extra
    bad = _mutate(
        lambda dependency_lock: dependency_lock.__setitem__("lock_digest", "not-a-digest")
    )
    assert any("does not match pattern" in e for e in bad), bad


_HERMETIC_SPEC = _REPO_ROOT / "tests/fixtures/sealed_build/hermetic_closure.txt"
_HERMETIC_LOCK = _REPO_ROOT / "tests/fixtures/sealed_build/hermetic_closure.lock"


@pytest.fixture()
def fake_repo_v2(fake_repo: Path) -> Path:
    # 在 v1 假樹上補齊 v2 專屬輸入:parquet_etl.py + 有效 hermetic lock/spec 當 requirements-ml.*
    # (verify_lock_closure 需一個完全 pin/hash/封閉的真鎖;hermetic fixture 即是)。
    _write(
        fake_repo,
        "program_code/ml_training/parquet_etl.py",
        b"# fake parquet_etl COMPUTE v0\n",
    )
    shutil.copyfile(_HERMETIC_SPEC, fake_repo / "requirements-ml.txt")
    shutil.copyfile(_HERMETIC_LOCK, fake_repo / "requirements-ml.lock")
    return fake_repo


def test_v2_feature_compute_change_moves_v2_identity_but_not_v1(fake_repo_v2: Path) -> None:
    # E4 nit-3(analogous to migration_byte_flip):擾動 v2 learning-code allowlist 中
    # parquet_etl.py 的 bytes → v2 身分(learning_code_digest + self_digest)變,而 v1 身分不變
    # (v1 不綁 parquet_etl)。capture 面不受影響(feature COMPUTE 只在 training 面)。
    v1_base = build_learning_runtime_manifest(fake_repo_v2, repo_source_head=_HEAD_A)
    v2_base = build_learning_runtime_manifest_v2(fake_repo_v2, repo_source_head=_HEAD_A)
    _write(
        fake_repo_v2,
        "program_code/ml_training/parquet_etl.py",
        b"# fake parquet_etl COMPUTE v1 (perturbed)\n",
    )
    v1_flip = build_learning_runtime_manifest(fake_repo_v2, repo_source_head=_HEAD_A)
    v2_flip = build_learning_runtime_manifest_v2(fake_repo_v2, repo_source_head=_HEAD_A)

    assert v1_base["self_digest"] == v1_flip["self_digest"]
    assert (
        v2_base["training_contract"]["components"]["learning_code_digest"]
        != v2_flip["training_contract"]["components"]["learning_code_digest"]
    )
    assert v2_base["self_digest"] != v2_flip["self_digest"]
    assert v2_base["capture_contract"]["digest"] == v2_flip["capture_contract"]["digest"]
    # 全局不變量:真 repo 的 v1 身分仍是凍結的 6cf76b60(擾動假樹不影響它)。
    assert (
        build_learning_runtime_manifest(_REPO_ROOT, repo_source_head="0" * 40)["self_digest"]
        == _V1_FROZEN_DIGEST
    )
