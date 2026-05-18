"""
測試 phase_1b_sweep_report module — Wilson CI + acceptance gate + output IO。

為什麼這些 test：spec §4 acceptance gate 是 sweep 最終 PASS/FAIL 決策關卡；
任何 gate logic bug 直接影響 cell selection 與 §5 pilot dispatch。
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase_1b_sweep_replay import (  # noqa: E402
    CellSimulationOutcome,
    FillSimulationResult,
)
from phase_1b_sweep_report import (  # noqa: E402
    CellReport,
    aggregate_summary,
    build_report_for_cell,
    classify_cell,
    fee_saving_ci,
    wilson_score_interval,
    write_outputs,
)


# ---- wilson_score_interval ----
def test_wilson_ci_at_100_percent():
    low, high = wilson_score_interval(10, 10)
    # 10/10 should have CI low < 1.0 (Wilson 保守，不會 exact 1.0)
    assert 0.7 <= low <= 1.0
    assert high == 1.0


def test_wilson_ci_at_0_percent():
    low, high = wilson_score_interval(0, 10)
    assert low == 0.0
    assert 0.0 <= high <= 0.3


def test_wilson_ci_at_50_percent():
    """n=10, 5 successes → 95% CI 約 (0.24, 0.76)。"""
    low, high = wilson_score_interval(5, 10)
    assert 0.20 < low < 0.30
    assert 0.70 < high < 0.80


def test_wilson_ci_n_zero():
    """n=0 → (0, 0)。"""
    assert wilson_score_interval(0, 0) == (0.0, 0.0)


def test_wilson_ci_small_sample_n_4():
    """n=4, 1 success (post-restart Phase 1b 4/4 timeout scenario reversed)。
    Wilson 在小樣本仍可計，CI 寬廣。
    """
    low, high = wilson_score_interval(1, 4)
    # CI 大概 (0.04, 0.70)（教科書）
    assert 0.0 < low < 0.20
    assert 0.50 < high < 0.90


# ---- fee_saving_ci ----
def test_fee_saving_ci_constant_values():
    """全部 fills 同 saving → CI low = high = mean。"""
    low, high = fee_saving_ci([3.5, 3.5, 3.5])
    assert abs(low - 3.5) < 1e-9
    assert abs(high - 3.5) < 1e-9


def test_fee_saving_ci_empty():
    assert fee_saving_ci([]) == (0.0, 0.0)


def test_fee_saving_ci_single_value():
    low, high = fee_saving_ci([2.0])
    assert (low, high) == (2.0, 2.0)


# ---- classify_cell PASS / CONDITIONAL / FAIL ----
def test_classify_pass_when_all_thresholds_met():
    gate = classify_cell(
        maker_fill_rate=0.30,
        fill_rate_wilson_ci_low=0.20,
        expected_fee_saving_bps=1.0,
        fee_saving_wilson_ci_low=0.5,
        adverse_selection_proxy_bps=2.0,
        pre_phase_1b_taker_baseline_bps=5.5,
    )
    assert gate == "PASS"


def test_classify_fail_when_fill_rate_low():
    gate = classify_cell(
        maker_fill_rate=0.10,  # < 0.25
        fill_rate_wilson_ci_low=0.05,
        expected_fee_saving_bps=1.0,
        fee_saving_wilson_ci_low=0.5,
        adverse_selection_proxy_bps=2.0,
        pre_phase_1b_taker_baseline_bps=5.5,
    )
    assert gate == "FAIL"


def test_classify_conditional_when_marginal_fill_rate():
    """0.15 ≤ fill_rate < 0.25, fee_saving ≥ 0.3, adverse ok → CONDITIONAL."""
    gate = classify_cell(
        maker_fill_rate=0.18,
        fill_rate_wilson_ci_low=0.10,
        expected_fee_saving_bps=0.4,
        fee_saving_wilson_ci_low=0.0,
        adverse_selection_proxy_bps=2.0,
        pre_phase_1b_taker_baseline_bps=5.5,
    )
    assert gate == "CONDITIONAL"


def test_classify_fail_when_adverse_exceeds_baseline():
    """adverse > taker baseline → FAIL even if fill rate good。"""
    gate = classify_cell(
        maker_fill_rate=0.40,
        fill_rate_wilson_ci_low=0.25,
        expected_fee_saving_bps=1.5,
        fee_saving_wilson_ci_low=0.5,
        adverse_selection_proxy_bps=10.0,  # > 5.5 baseline
        pre_phase_1b_taker_baseline_bps=5.5,
    )
    assert gate == "FAIL"


def test_classify_fail_when_adverse_none():
    """adverse=None (無 post-drift sample) → fail-closed."""
    gate = classify_cell(
        maker_fill_rate=0.40,
        fill_rate_wilson_ci_low=0.25,
        expected_fee_saving_bps=1.5,
        fee_saving_wilson_ci_low=0.5,
        adverse_selection_proxy_bps=None,
        pre_phase_1b_taker_baseline_bps=5.5,
    )
    assert gate == "FAIL"


def test_classify_fail_when_wilson_ci_too_low():
    """fill rate 25% but Wilson CI low 5% → FAIL (sample 太小)."""
    gate = classify_cell(
        maker_fill_rate=0.25,
        fill_rate_wilson_ci_low=0.05,  # < 0.15
        expected_fee_saving_bps=1.0,
        fee_saving_wilson_ci_low=0.5,
        adverse_selection_proxy_bps=2.0,
        pre_phase_1b_taker_baseline_bps=5.5,
    )
    # AC-14 Wilson gate not met → not PASS; but CONDITIONAL conditions met → CONDITIONAL
    assert gate == "CONDITIONAL"


# ---- build_report_for_cell ----
def _make_outcome(
    cell_id="G-AB-02-C30",
    n_attempts=10,
    n_simulated_fills=3,
    n_skip_spread_guard=0,
    n_skip_no_bbo=0,
    fee_savings=None,
    adverse=2.0,
) -> CellSimulationOutcome:
    if fee_savings is None:
        fee_savings = [3.5, 3.0, 2.5]  # 3 fills
    fill_ts = datetime(2026, 5, 18, 0, 0, 0, tzinfo=timezone.utc)
    per_fill = [
        FillSimulationResult(
            cell_id=cell_id, fill_order_id=f"o{i}", symbol="BTCUSDT",
            fill_ts=fill_ts, exit_reason="grid_close_short",
            seed_source="post_restart",
            simulated_fill=(i < len(fee_savings)),
            simulated_fill_px=100.0 if i < len(fee_savings) else None,
            simulated_fill_ts=fill_ts if i < len(fee_savings) else None,
            actual_taker_px=100.0,
            fee_saving_bps=fee_savings[i] if i < len(fee_savings) else None,
            adverse_selection_proxy_bps=adverse if i < len(fee_savings) else None,
            skipped_reason=None,
            limit_price=100.0,
            mid_at_fill_plus_60s=101.0 if i < len(fee_savings) else None,
        )
        for i in range(n_attempts)
    ]
    avg_fee = sum(fee_savings) / len(fee_savings) if fee_savings else 0.0
    return CellSimulationOutcome(
        cell_id=cell_id,
        n_attempts=n_attempts,
        n_simulated_fills=n_simulated_fills,
        n_skipped_spread_guard=n_skip_spread_guard,
        n_skipped_no_bbo=n_skip_no_bbo,
        n_skipped_tick_missing=0,
        n_skipped_family_mismatch=0,
        n_skipped_crossed_book=0,
        maker_fill_rate=n_simulated_fills / max(1, n_attempts - n_skip_spread_guard - n_skip_no_bbo),
        expected_fee_saving_bps=avg_fee,
        adverse_selection_proxy_bps=adverse,
        per_fill_results=tuple(per_fill),
    )


def test_build_report_includes_required_fields():
    outcome = _make_outcome()
    meta = {
        "block": 1, "family": "grid", "offset_bps": 0.5,
        "buffer_ticks": 0, "timeout_ms": 30_000, "spread_guard_bps": 50.0,
        "is_baseline": False, "direction_note": "test",
    }
    report = build_report_for_cell(
        outcome=outcome,
        cell_meta=meta,
        pre_phase_1b_taker_baseline_bps=5.5,
    )
    # spec §2.4 required fields
    assert report.cell_id == "G-AB-02-C30"
    assert report.n_attempts == 10
    assert report.maker_fill_rate == 0.3
    assert report.fill_rate_wilson_ci_low > 0
    assert report.fee_saving_wilson_ci_low <= report.expected_fee_saving_bps
    assert report.pass_gate in ("PASS", "CONDITIONAL", "FAIL")
    assert report.data_source == "bybit_demo_ws"


def test_aggregate_summary_counts_and_tops():
    """aggregate 排序 by fill_rate × fee_saving，識別 top-2。"""
    fill_ts = datetime(2026, 5, 18, 0, 0, 0, tzinfo=timezone.utc)
    reports = [
        CellReport(
            cell_id="A", block=1, family="grid",
            offset_bps=0.5, buffer_ticks=0, timeout_ms=30_000,
            spread_guard_bps=50.0, is_baseline=False, direction_note="",
            n_attempts=10, n_simulated_fills=4, n_skipped_spread_guard=0,
            n_skipped_no_bbo=0, n_skipped_tick_missing=0, n_skipped_family_mismatch=0,
            n_skipped_crossed_book=0, n_eligible=10,
            maker_fill_rate=0.40, fill_rate_wilson_ci_low=0.20,
            fill_rate_wilson_ci_high=0.65,
            expected_fee_saving_bps=2.0, fee_saving_wilson_ci_low=1.0,
            fee_saving_wilson_ci_high=3.0,
            adverse_selection_proxy_bps=2.0,
            pre_phase_1b_taker_baseline_bps=5.5,
            pass_gate="PASS",
        ),
        CellReport(
            cell_id="B", block=1, family="grid",
            offset_bps=0.5, buffer_ticks=0, timeout_ms=30_000,
            spread_guard_bps=50.0, is_baseline=False, direction_note="",
            n_attempts=10, n_simulated_fills=3, n_skipped_spread_guard=0,
            n_skipped_no_bbo=0, n_skipped_tick_missing=0, n_skipped_family_mismatch=0,
            n_skipped_crossed_book=0, n_eligible=10,
            maker_fill_rate=0.30, fill_rate_wilson_ci_low=0.18,
            fill_rate_wilson_ci_high=0.55,
            expected_fee_saving_bps=1.0, fee_saving_wilson_ci_low=0.5,
            fee_saving_wilson_ci_high=1.5,
            adverse_selection_proxy_bps=2.0,
            pre_phase_1b_taker_baseline_bps=5.5,
            pass_gate="PASS",
        ),
        CellReport(
            cell_id="C", block=1, family="grid",
            offset_bps=0.5, buffer_ticks=0, timeout_ms=30_000,
            spread_guard_bps=50.0, is_baseline=False, direction_note="",
            n_attempts=10, n_simulated_fills=1, n_skipped_spread_guard=0,
            n_skipped_no_bbo=0, n_skipped_tick_missing=0, n_skipped_family_mismatch=0,
            n_skipped_crossed_book=0, n_eligible=10,
            maker_fill_rate=0.10, fill_rate_wilson_ci_low=0.0,
            fill_rate_wilson_ci_high=0.40,
            expected_fee_saving_bps=0.2, fee_saving_wilson_ci_low=0.0,
            fee_saving_wilson_ci_high=0.5,
            adverse_selection_proxy_bps=10.0,  # FAIL adverse
            pre_phase_1b_taker_baseline_bps=5.5,
            pass_gate="FAIL",
        ),
    ]
    summary = aggregate_summary(reports)
    assert summary["total_cells"] == 3
    assert summary["n_pass"] == 2
    assert summary["n_fail"] == 1
    # score A = 0.40 * 2.0 = 0.8; score B = 0.30 * 1.0 = 0.3 → top = [A, B]
    assert summary["top_pass_cells"] == ["A", "B"]


def test_write_outputs_creates_files():
    """write_outputs 創 3 種 file: per-cell JSON + CSV + summary。"""
    fill_ts = datetime(2026, 5, 18, 0, 0, 0, tzinfo=timezone.utc)
    reports = [
        CellReport(
            cell_id="T1", block=1, family="grid",
            offset_bps=0.5, buffer_ticks=0, timeout_ms=30_000,
            spread_guard_bps=50.0, is_baseline=False, direction_note="",
            n_attempts=10, n_simulated_fills=3, n_skipped_spread_guard=0,
            n_skipped_no_bbo=0, n_skipped_tick_missing=0, n_skipped_family_mismatch=0,
            n_skipped_crossed_book=0, n_eligible=10,
            maker_fill_rate=0.30, fill_rate_wilson_ci_low=0.18,
            fill_rate_wilson_ci_high=0.55,
            expected_fee_saving_bps=1.0, fee_saving_wilson_ci_low=0.5,
            fee_saving_wilson_ci_high=1.5,
            adverse_selection_proxy_bps=2.0,
            pre_phase_1b_taker_baseline_bps=5.5,
            pass_gate="PASS",
        ),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "sweep_out"
        info = write_outputs(reports, out_dir)
        assert (out_dir / "cells" / "T1.json").exists()
        assert (out_dir / "sweep_aggregate.csv").exists()
        assert (out_dir / "sweep_summary.json").exists()
        # 驗 summary content
        summary = json.loads((out_dir / "sweep_summary.json").read_text())
        assert summary["total_cells"] == 1
        assert summary["n_pass"] == 1
        # 驗 per-cell JSON content
        cell_data = json.loads((out_dir / "cells" / "T1.json").read_text())
        assert cell_data["cell_id"] == "T1"
        assert cell_data["pass_gate"] == "PASS"
