"""Tests for Phase 4 weekly report generator (4-20).

Phase 4 週度報告生成器測試。
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from program_code.ml_training.weekly_report_generator import (
    DOD_A_SHARPE_DELTA,
    DOD_C_AUC_MIN,
    DOD_E_EXEC_RATE_MIN,
    WeeklyMetrics,
    current_week_iso,
    evaluate_dod,
    fetch_weekly_metrics,
    generate_report,
    week_range_for_iso,
    write_report,
)


# ---------------------------------------------------------------------------
# Helpers / 輔助
# ---------------------------------------------------------------------------


def _metrics(**overrides) -> WeeklyMetrics:
    """Build a metrics fixture with sane defaults + overrides."""
    base = WeeklyMetrics(
        week_iso="2026-W15",
        week_start=datetime(2026, 4, 6, tzinfo=timezone.utc),
        week_end=datetime(2026, 4, 13, tzinfo=timezone.utc),
        sharpe_paper_7d=0.45,
        sharpe_baseline=0.20,
        sharpe_delta=0.25,
        scorer_auc_7d=0.58,
        teacher_total_7d=12,
        teacher_applied_7d=10,
        teacher_exec_rate=10 / 12,
        teacher_avg_outcome_24h=3.20,
        linucb_active_version="v1_15",
        linucb_total_pulls=1240,
        linucb_converged_arms=6,
        news_total_7d=384,
        news_halt_triggers_7d=2,
        news_max_severity_7d=0.92,
        dl3_inference_count_7d=168,
        dl3_avg_latency_ms=1234.0,
        dl3_ok_rate_7d=0.982,
        ai_cost_usd_7d=14.50,
        ai_cost_local_total_remaining=85.50,
        ai_degrade_level="none",
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


# ---------------------------------------------------------------------------
# Week ISO helpers
# ---------------------------------------------------------------------------


def test_current_week_iso_format():
    iso = current_week_iso(datetime(2026, 4, 7, tzinfo=timezone.utc))
    assert iso.startswith("2026-W")
    assert len(iso.split("W")[1]) == 2


def test_week_range_for_iso_returns_monday_start_and_seven_day_end():
    start, end = week_range_for_iso("2026-W15")
    assert (end - start) == timedelta(days=7)
    # ISO week starts Monday
    # ISO 週從週一開始
    assert start.weekday() == 0


def test_week_range_for_iso_invalid_raises():
    with pytest.raises(ValueError):
        week_range_for_iso("not-a-week")


# ---------------------------------------------------------------------------
# DoD evaluation
# ---------------------------------------------------------------------------


def test_evaluate_dod_a_pass_when_sharpe_delta_above_threshold():
    m = _metrics(sharpe_delta=0.20)
    dod = evaluate_dod(m)
    assert dod["A_sharpe"] == "PASS"


def test_evaluate_dod_a_fail_when_sharpe_delta_below_threshold():
    m = _metrics(sharpe_delta=0.10)
    dod = evaluate_dod(m)
    assert dod["A_sharpe"] == "FAIL"


def test_evaluate_dod_a_at_exact_threshold_passes():
    m = _metrics(sharpe_delta=DOD_A_SHARPE_DELTA)
    dod = evaluate_dod(m)
    assert dod["A_sharpe"] == "PASS"


def test_evaluate_dod_a_na_when_sharpe_none():
    m = _metrics(sharpe_delta=None)
    dod = evaluate_dod(m)
    assert dod["A_sharpe"] == "N/A"


def test_evaluate_dod_c_auc_pass():
    m = _metrics(scorer_auc_7d=0.58)
    dod = evaluate_dod(m)
    assert dod["C_auc"] == "PASS"


def test_evaluate_dod_c_auc_fail():
    m = _metrics(scorer_auc_7d=0.50)
    dod = evaluate_dod(m)
    assert dod["C_auc"] == "FAIL"


def test_evaluate_dod_c_auc_na_when_none():
    m = _metrics(scorer_auc_7d=None)
    dod = evaluate_dod(m)
    assert dod["C_auc"] == "N/A"


def test_evaluate_dod_e_teacher_pass():
    m = _metrics(
        teacher_total_7d=10, teacher_applied_7d=9, teacher_exec_rate=0.9, teacher_avg_outcome_24h=2.0
    )
    dod = evaluate_dod(m)
    assert dod["E_teacher"] == "PASS"


def test_evaluate_dod_e_teacher_fail_low_exec_rate():
    m = _metrics(
        teacher_total_7d=10, teacher_applied_7d=5, teacher_exec_rate=0.5, teacher_avg_outcome_24h=2.0
    )
    dod = evaluate_dod(m)
    assert dod["E_teacher"] == "FAIL"


def test_evaluate_dod_e_teacher_fail_negative_outcome():
    m = _metrics(
        teacher_total_7d=10, teacher_applied_7d=10, teacher_exec_rate=1.0, teacher_avg_outcome_24h=-5.0
    )
    dod = evaluate_dod(m)
    assert dod["E_teacher"] == "FAIL"


def test_evaluate_dod_e_teacher_na_when_no_directives():
    m = _metrics(teacher_total_7d=0, teacher_applied_7d=0, teacher_exec_rate=0.0)
    dod = evaluate_dod(m)
    assert dod["E_teacher"] == "N/A"


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def test_generate_report_markdown_includes_dod_table():
    report = generate_report(_metrics())
    assert "## DoD Status" in report.markdown
    assert "**A** Sharpe" in report.markdown
    assert "**C** Scorer AUC" in report.markdown
    assert "**E** Teacher exec rate" in report.markdown


def test_generate_report_machine_summary_keys_complete():
    report = generate_report(_metrics())
    summary = report.machine_summary
    required = {"week_iso", "generated_at_iso", "dod_status", "overall", "metrics", "thresholds"}
    assert required.issubset(set(summary.keys()))
    assert summary["thresholds"]["dod_a_sharpe_delta"] == DOD_A_SHARPE_DELTA
    assert summary["thresholds"]["dod_c_auc_min"] == DOD_C_AUC_MIN
    assert summary["thresholds"]["dod_e_exec_rate_min"] == DOD_E_EXEC_RATE_MIN


def test_generate_report_overall_approve_when_all_pass():
    report = generate_report(_metrics())
    assert report.machine_summary["overall"] == "APPROVE"


def test_generate_report_overall_review_when_any_fail():
    m = _metrics(sharpe_delta=0.05)  # A FAIL
    report = generate_report(m)
    assert report.machine_summary["overall"] == "REVIEW"


def test_generate_report_insufficient_data_banner():
    m = _metrics()
    m.is_insufficient_data = True
    m.insufficient_reason = "test reason"
    report = generate_report(m)
    assert "INSUFFICIENT DATA" in report.markdown
    assert "test reason" in report.markdown


def test_generate_report_operator_notes_appear():
    report = generate_report(_metrics(), operator_notes="manual override note")
    assert "manual override note" in report.markdown


def test_generate_report_no_operator_notes_renders_none():
    report = generate_report(_metrics())
    assert "(none provided)" in report.markdown


def test_generate_report_module_health_sections_present():
    report = generate_report(_metrics())
    assert "Claude Teacher" in report.markdown
    assert "LinUCB Bandit" in report.markdown
    assert "News" in report.markdown
    assert "DL-3 Foundation" in report.markdown
    assert "AI Cost" in report.markdown


# ---------------------------------------------------------------------------
# write_report
# ---------------------------------------------------------------------------


def test_write_report_creates_md_and_json():
    report = generate_report(_metrics())
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = Path(tmpdir) / "subdir" / "report.md"
        out = write_report(report, md_path)
        assert out == md_path
        assert md_path.exists()
        json_path = md_path.with_suffix(md_path.suffix + ".json")
        assert json_path.exists()
        loaded = json.loads(json_path.read_text())
        assert loaded["week_iso"] == "2026-W15"
        assert loaded["overall"] == "APPROVE"


# ---------------------------------------------------------------------------
# fetch_weekly_metrics fail-soft
# ---------------------------------------------------------------------------


def test_fetch_weekly_metrics_no_dsn_returns_default():
    m = fetch_weekly_metrics(None, week_iso="2026-W15")
    assert m.is_insufficient_data is True
    assert "no dsn" in m.insufficient_reason
    assert m.teacher_total_7d == 0
