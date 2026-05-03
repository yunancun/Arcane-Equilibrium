"""Tests for selection_bias_validator (REF-20 Wave 6 P4-Q3).

selection_bias_validator 測試（REF-20 Wave 6 P4-Q3）。

Coverage / 覆蓋:
  1. Valid manifest → ok=True. /
     有效 manifest → ok=True。
  2. K < 10 → fail (K_TOO_LOW). /
     K < 10 → fail。
  3. oos_pct < 0.20 → fail (OOS_PCT_TOO_LOW). /
     oos_pct < 0.20 → fail。
  4. unknown cv_protocol → fail (UNKNOWN_CV_PROTOCOL). /
     未知 cv_protocol → fail。
"""

from __future__ import annotations

import pytest

from program_code.exchange_connectors.bybit_connector.control_api_v1.replay.selection_bias_validator import (
    ALLOWED_CV_PROTOCOLS,
    MIN_EMBARGO_DAYS_FLOOR,
    MIN_OOS_PCT,
    MIN_TRIALS_K,
    SelectionBiasCorrection,
    SelectionBiasFailMode,
    ValidationResult,
    validate_selection_bias_correction,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _make_valid_block() -> dict:
    """Construct a valid `selection_bias_correction` block.

    構造有效的 `selection_bias_correction` block。
    """
    return {
        "n_trials_K": 15,
        "backtest_period_days": 90,
        "out_of_sample_pct": 0.30,
        "cv_protocol": "walk_forward",
        "embargo_days": 14,
    }


def _make_manifest(block_overrides: dict | None = None) -> dict:
    """Construct a manifest with the bias block (with optional overrides).

    構造含 bias block 的 manifest（可選 overrides）。
    """
    block = _make_valid_block()
    if block_overrides:
        block.update(block_overrides)
    return {
        "experiment_id": "test-exp-1",
        "manifest_hash": "abc123",
        "selection_bias_correction": block,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Valid manifest → ok=True
# ─────────────────────────────────────────────────────────────────────────────


def test_valid_manifest_passes():
    """Fully valid block → ok=True with parsed dataclass.

    完全有效 block → ok=True 含解析 dataclass。
    """
    manifest = _make_manifest()
    result = validate_selection_bias_correction(manifest)

    assert isinstance(result, ValidationResult)
    assert result.ok is True
    assert result.fail_mode is None
    assert result.reason_zh == ""
    assert result.reason_en == ""
    assert isinstance(result.parsed, SelectionBiasCorrection)
    assert result.parsed.n_trials_K == 15
    assert result.parsed.backtest_period_days == 90
    assert result.parsed.out_of_sample_pct == 0.30
    assert result.parsed.cv_protocol == "walk_forward"
    assert result.parsed.embargo_days == 14


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: K < 10 → fail (K_TOO_LOW)
# ─────────────────────────────────────────────────────────────────────────────


def test_k_too_low_fails():
    """K=5 < min_K=10 → fail with K_TOO_LOW.

    K=5 < min_K=10 → 失敗於 K_TOO_LOW。
    """
    manifest = _make_manifest({"n_trials_K": 5})
    result = validate_selection_bias_correction(manifest)

    assert result.ok is False
    assert result.fail_mode == SelectionBiasFailMode.K_TOO_LOW
    # Reason fields should mention K and threshold.
    # reason 應提及 K 與閾值。
    assert "5" in result.reason_zh
    assert "5" in result.reason_en
    assert str(MIN_TRIALS_K) in result.reason_en
    # parsed should still be populated for diagnostic.
    # parsed 應仍填寫供診斷用。
    assert result.parsed is not None
    assert result.parsed.n_trials_K == 5


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: oos_pct < 0.20 → fail (OOS_PCT_TOO_LOW)
# ─────────────────────────────────────────────────────────────────────────────


def test_oos_pct_too_low_fails():
    """oos_pct=0.10 < 0.20 → fail with OOS_PCT_TOO_LOW.

    oos_pct=0.10 < 0.20 → 失敗於 OOS_PCT_TOO_LOW。
    """
    manifest = _make_manifest({"out_of_sample_pct": 0.10})
    result = validate_selection_bias_correction(manifest)

    assert result.ok is False
    assert result.fail_mode == SelectionBiasFailMode.OOS_PCT_TOO_LOW
    assert "0.1" in result.reason_zh
    assert str(MIN_OOS_PCT) in result.reason_en
    assert result.parsed is not None
    assert result.parsed.out_of_sample_pct == 0.10


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Unknown cv_protocol → fail (UNKNOWN_CV_PROTOCOL)
# ─────────────────────────────────────────────────────────────────────────────


def test_unknown_cv_protocol_fails():
    """Unknown cv_protocol → fail with UNKNOWN_CV_PROTOCOL.

    未知 cv_protocol → 失敗於 UNKNOWN_CV_PROTOCOL。
    """
    manifest = _make_manifest({"cv_protocol": "naive_kfold"})
    result = validate_selection_bias_correction(manifest)

    assert result.ok is False
    assert result.fail_mode == SelectionBiasFailMode.UNKNOWN_CV_PROTOCOL
    assert "naive_kfold" in result.reason_zh
    assert "naive_kfold" in result.reason_en
    # All allowlist entries should be referenced for operator visibility.
    # 全 allowlist 應於 reason 中提及供 operator 可視。
    for protocol in ALLOWED_CV_PROTOCOLS:
        assert protocol in result.reason_en


# ─────────────────────────────────────────────────────────────────────────────
# Edge / 邊緣案例
# ─────────────────────────────────────────────────────────────────────────────


def test_missing_block_fails():
    """Missing top-level `selection_bias_correction` → MISSING_BLOCK.

    缺頂層 `selection_bias_correction` → MISSING_BLOCK。
    """
    manifest = {"experiment_id": "no-block", "manifest_hash": "xxx"}
    result = validate_selection_bias_correction(manifest)
    assert result.ok is False
    assert result.fail_mode == SelectionBiasFailMode.MISSING_BLOCK


def test_block_not_dict_fails():
    """`selection_bias_correction` not a dict → MISSING_BLOCK.

    `selection_bias_correction` 非 dict → MISSING_BLOCK。
    """
    manifest = {"selection_bias_correction": "string-not-dict"}
    result = validate_selection_bias_correction(manifest)
    assert result.ok is False
    assert result.fail_mode == SelectionBiasFailMode.MISSING_BLOCK


def test_missing_field_fails():
    """Block missing `embargo_days` field → MISSING_BLOCK.

    block 缺 `embargo_days` 欄位 → MISSING_BLOCK。
    """
    block = _make_valid_block()
    del block["embargo_days"]
    manifest = {"selection_bias_correction": block}
    result = validate_selection_bias_correction(manifest)
    assert result.ok is False
    assert result.fail_mode == SelectionBiasFailMode.MISSING_BLOCK
    assert "embargo_days" in result.reason_en


def test_embargo_too_low_fails():
    """embargo_days=3 < V041 floor=7 → EMBARGO_TOO_LOW.

    embargo_days=3 < V041 下限=7 → EMBARGO_TOO_LOW。
    """
    manifest = _make_manifest({"embargo_days": 3})
    result = validate_selection_bias_correction(manifest)
    assert result.ok is False
    assert result.fail_mode == SelectionBiasFailMode.EMBARGO_TOO_LOW
    assert str(MIN_EMBARGO_DAYS_FLOOR) in result.reason_en


def test_oos_pct_at_boundary_passes():
    """oos_pct exactly == 0.20 → ok (boundary inclusive).

    oos_pct 剛好 == 0.20 → ok（邊界含）。
    """
    manifest = _make_manifest({"out_of_sample_pct": 0.20})
    result = validate_selection_bias_correction(manifest)
    assert result.ok is True


def test_oos_pct_at_one_fails():
    """oos_pct >= 1.0 → OOS_PCT_TOO_LOW (cannot consume 100%).

    oos_pct >= 1.0 → OOS_PCT_TOO_LOW（不可佔 100%）。
    """
    manifest = _make_manifest({"out_of_sample_pct": 1.0})
    result = validate_selection_bias_correction(manifest)
    assert result.ok is False
    assert result.fail_mode == SelectionBiasFailMode.OOS_PCT_TOO_LOW


def test_k_at_boundary_passes():
    """K exactly == 10 → ok (boundary inclusive).

    K 剛好 == 10 → ok（邊界含）。
    """
    manifest = _make_manifest({"n_trials_K": 10})
    result = validate_selection_bias_correction(manifest)
    assert result.ok is True


def test_bool_rejected_for_int_field():
    """bool for int field → MISSING_BLOCK (type mismatch).

    int 欄位給 bool → MISSING_BLOCK（型別不符）。
    """
    manifest = _make_manifest({"n_trials_K": True})  # bool not allowed
    result = validate_selection_bias_correction(manifest)
    assert result.ok is False
    assert result.fail_mode == SelectionBiasFailMode.MISSING_BLOCK


def test_int_accepted_for_float_field():
    """int for float field is accepted (numeric coerce).

    int 給 float 欄位被接受（數值 coerce）。
    """
    block = _make_valid_block()
    block["out_of_sample_pct"] = 1  # int — but 1 >= 1.0 fails OOS upper.
    manifest = {"selection_bias_correction": block}
    result = validate_selection_bias_correction(manifest)
    # Type accepted, but 1 >= 1.0 fails OOS upper bound.
    # 型別接受，但 1 >= 1.0 觸發 OOS 上限。
    assert result.ok is False
    assert result.fail_mode == SelectionBiasFailMode.OOS_PCT_TOO_LOW

    # Now use int that is in valid OOS range numerically — but 0 < 0.2 → fail.
    block2 = _make_valid_block()
    block2["out_of_sample_pct"] = 0  # int 0
    manifest2 = {"selection_bias_correction": block2}
    result2 = validate_selection_bias_correction(manifest2)
    assert result2.ok is False
    assert result2.fail_mode == SelectionBiasFailMode.OOS_PCT_TOO_LOW


def test_dataclass_to_dict_roundtrip():
    """SelectionBiasCorrection.to_dict round-trips through validator.

    SelectionBiasCorrection.to_dict 通過 validator round-trip。
    """
    sbc = SelectionBiasCorrection(
        n_trials_K=20,
        backtest_period_days=180,
        out_of_sample_pct=0.30,
        cv_protocol="cscv",
        embargo_days=14,
    )
    manifest = {"selection_bias_correction": sbc.to_dict()}
    result = validate_selection_bias_correction(manifest)
    assert result.ok is True
    assert result.parsed == sbc
