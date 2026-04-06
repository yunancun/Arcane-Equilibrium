"""Tests for DL-3 Go/No-Go report generator (Phase 4 4-13).

DL-3 Go/No-Go 報告生成器測試。
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from program_code.ml_training.dl3_go_no_go import (
    MAX_COST_USD_PER_INFERENCE,
    MAX_LATENCY_MS_FOR_GO,
    GoNoGoMetadata,
    GoNoGoReport,
    derive_decision,
    generate_report,
    write_report,
)


# ---------------------------------------------------------------------------
# Helpers / 輔助
# ---------------------------------------------------------------------------


def _meta(latency_ms: float = 500.0, cost_usd: float = 0.001) -> GoNoGoMetadata:
    return GoNoGoMetadata(
        average_latency_ms=latency_ms,
        cost_usd_per_inference=cost_usd,
        inference_count_tested=100,
        chronos_available=True,
        timesfm_available=True,
    )


def _ab_dict(decision: str, **overrides) -> dict:
    base = {
        "decision": decision,
        "baseline_auc": 0.55,
        "augmented_auc": 0.58,
        "baseline_brier": 0.20,
        "augmented_brier": 0.18,
        "auc_delta": 0.03,
        "n_samples": 500,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Decision matrix tests
# 決策矩陣測試
# ---------------------------------------------------------------------------


def test_derive_decision_promote_low_latency_low_cost_returns_go():
    """PROMOTE_PENDING + 快 + 便宜 → GO."""
    decision, reason = derive_decision(
        "PROMOTE_PENDING", _meta(latency_ms=500.0, cost_usd=0.001)
    )
    assert decision == "GO"
    assert "AUC improvement" in reason


def test_derive_decision_promote_high_latency_returns_no_go():
    """PROMOTE_PENDING + 太慢 → NO_GO."""
    decision, reason = derive_decision(
        "PROMOTE_PENDING", _meta(latency_ms=2500.0, cost_usd=0.001)
    )
    assert decision == "NO_GO"
    assert "latency" in reason


def test_derive_decision_promote_high_cost_returns_no_go():
    """PROMOTE_PENDING + 太貴 → NO_GO."""
    decision, reason = derive_decision(
        "PROMOTE_PENDING", _meta(latency_ms=500.0, cost_usd=0.05)
    )
    assert decision == "NO_GO"
    assert "cost" in reason
    assert "principle #14" in reason


def test_derive_decision_deprecate_returns_no_go():
    """DEPRECATE → NO_GO."""
    decision, reason = derive_decision("DEPRECATE", _meta())
    assert decision == "NO_GO"
    assert "below the 0.01 threshold" in reason


def test_derive_decision_inconclusive_returns_no_go():
    """INCONCLUSIVE → NO_GO (fail-closed)."""
    decision, reason = derive_decision("INCONCLUSIVE", _meta())
    assert decision == "NO_GO"
    assert "Fail-closed" in reason


def test_derive_decision_insufficient_returns_pending_data():
    """INSUFFICIENT_DATA → PENDING_DATA."""
    decision, reason = derive_decision("INSUFFICIENT_DATA", _meta())
    assert decision == "PENDING_DATA"
    assert "Defer" in reason


def test_derive_decision_unknown_returns_no_go_fail_closed():
    """Unknown ab_decision → NO_GO (fail-closed)."""
    decision, reason = derive_decision("WEIRD_VALUE", _meta())
    assert decision == "NO_GO"
    assert "fail-closed" in reason.lower()


def test_derive_decision_exact_latency_threshold_is_no_go():
    """latency exactly == threshold → NO_GO (uses >= not >)."""
    decision, _ = derive_decision(
        "PROMOTE_PENDING", _meta(latency_ms=MAX_LATENCY_MS_FOR_GO, cost_usd=0.001)
    )
    assert decision == "NO_GO"


def test_derive_decision_exact_cost_threshold_is_no_go():
    """cost exactly == threshold → NO_GO."""
    decision, _ = derive_decision(
        "PROMOTE_PENDING", _meta(latency_ms=500.0, cost_usd=MAX_COST_USD_PER_INFERENCE)
    )
    assert decision == "NO_GO"


# ---------------------------------------------------------------------------
# Report generation tests
# 報告生成測試
# ---------------------------------------------------------------------------


def test_generate_report_includes_all_metrics_in_markdown():
    """Markdown report should mention every key metric."""
    ab = _ab_dict("PROMOTE_PENDING")
    meta = _meta()
    report = generate_report(ab, meta)
    md = report.markdown
    assert "ROC-AUC" in md
    assert "Brier Score" in md
    assert "Average latency" in md
    assert "Cost per inference" in md
    assert "Chronos available" in md
    assert "TimesFM available" in md
    assert "Sign-off" in md
    # All numeric values present
    # 所有數值都在
    assert "0.5500" in md  # baseline_auc
    assert "0.5800" in md  # augmented_auc
    assert "100" in md  # inference_count_tested


def test_generate_report_machine_summary_keys_complete():
    """machine_summary should contain all required keys."""
    report = generate_report(_ab_dict("PROMOTE_PENDING"), _meta())
    summary = report.machine_summary
    required_keys = {
        "decision",
        "reason",
        "ab_decision",
        "baseline_auc",
        "augmented_auc",
        "auc_delta",
        "baseline_brier",
        "augmented_brier",
        "brier_delta",
        "n_samples",
        "metadata",
        "thresholds",
        "generated_at_iso",
    }
    assert required_keys.issubset(set(summary.keys()))
    assert summary["thresholds"]["max_latency_ms"] == MAX_LATENCY_MS_FOR_GO
    assert summary["thresholds"]["max_cost_usd_per_inference"] == MAX_COST_USD_PER_INFERENCE


def test_generate_report_decision_in_markdown_header():
    """The final decision should appear bold in the Markdown header."""
    report = generate_report(_ab_dict("PROMOTE_PENDING"), _meta())
    assert "**Decision**: **GO**" in report.markdown


def test_generate_report_deterministic_with_now_override():
    """Passing a fixed `now` makes the timestamp deterministic."""
    fixed = datetime(2026, 4, 7, 12, 0, 0, tzinfo=timezone.utc)
    r1 = generate_report(_ab_dict("PROMOTE_PENDING"), _meta(), now=fixed)
    r2 = generate_report(_ab_dict("PROMOTE_PENDING"), _meta(), now=fixed)
    assert r1.markdown == r2.markdown
    assert "2026-04-07T12:00:00Z" in r1.markdown


def test_generate_report_handles_dataclass_ab_result():
    """ab_result can be a dataclass-like object (uses getattr)."""

    class FakeAbResult:
        decision = "DEPRECATE"
        baseline_auc = 0.55
        augmented_auc = 0.555
        baseline_brier = 0.20
        augmented_brier = 0.18
        auc_delta = 0.005
        n_samples = 500

    report = generate_report(FakeAbResult(), _meta())
    assert report.decision == "NO_GO"
    assert "0.005" in report.machine_summary["auc_delta"].__str__() or report.machine_summary["auc_delta"] == 0.005


def test_generate_report_operator_notes_appear_in_markdown():
    """Operator notes should appear under the Operator Notes section."""
    report = generate_report(
        _ab_dict("DEPRECATE"), _meta(), operator_notes="Manual override considered"
    )
    assert "Manual override considered" in report.markdown


def test_generate_report_no_operator_notes_renders_none():
    """Empty notes render as '(none)'."""
    report = generate_report(_ab_dict("DEPRECATE"), _meta())
    assert "(none)" in report.markdown


# ---------------------------------------------------------------------------
# write_report tests
# write_report 測試
# ---------------------------------------------------------------------------


def test_write_report_creates_md_and_json():
    """write_report should create both .md and .md.json files."""
    report = generate_report(_ab_dict("PROMOTE_PENDING"), _meta())
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = Path(tmpdir) / "subdir" / "report.md"
        result_path = write_report(report, md_path)
        assert result_path == md_path
        assert md_path.exists()
        json_path = md_path.with_suffix(md_path.suffix + ".json")
        assert json_path.exists()
        # Verify JSON parses + contains decision
        # 驗證 JSON 可解析且包含 decision
        loaded = json.loads(json_path.read_text())
        assert loaded["decision"] == "GO"


def test_write_report_creates_parent_dirs():
    """write_report should create missing parent directories."""
    report = generate_report(_ab_dict("INSUFFICIENT_DATA"), _meta())
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = Path(tmpdir) / "a" / "b" / "c" / "deep.md"
        write_report(report, md_path)
        assert md_path.exists()
