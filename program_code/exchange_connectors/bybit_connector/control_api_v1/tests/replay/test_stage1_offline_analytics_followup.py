"""U1：以公開分析函式與 CLI 驗證持倉區間與拒絕行為。"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

CONTROL_ROOT = Path(__file__).resolve().parents[2]
ROOT = CONTROL_ROOT.parents[3]
sys.path.insert(0, str(CONTROL_ROOT))
from replay.offline_analytics import analyze_report


def report(*, closed=False, timing="next_symbol_open"):
    fills = [dict(ts_ms=86_340_000, effective_ts_ms=86_340_000, symbol="BTCUSDT",
                  side="long", qty=1, price=100, fee=0, slippage_bps=0)]
    if closed:
        fills.append({**fills[0], "side": "short"})
    return {"result": {"fills": fills, "pnl_summary": {"starting_balance": 10000, "net_pnl": 0},
                       "status": {"kind": "completed"}},
            "stage1": {"execution_timing": timing, "replay_end_ts_ms": 86_340_000}}


def test_last_bar_close_includes_midnight_funding():
    output = analyze_report(report(), bar_duration_ms=60_000)
    funding = output["funding"]
    assert funding["open_position_crossing_count"] == 1
    assert funding["funding_crossed"] is True
    assert funding["crossing_check_exact"] is True
    assert funding["replay_end_ts_ms"] == 86_400_000
    assert funding["replay_end_source"] == "report_stage1_plus_bar_duration"
    assert output["unmatched_fills"][0]["replay_end_ts_ms"] == 86_400_000


def test_open_without_duration_has_inexact_end():
    funding = analyze_report(report())["funding"]
    assert funding["crossing_check_exact"] is False
    assert funding["timestamp_basis"] == "execution_event_open"
    assert funding["replay_end_ts_ms"] == 86_340_000
    assert funding["funding_crossed"] is False


@pytest.mark.parametrize("duration", [None, 60_000])
def test_closed_positions_remain_exact_and_unchanged(duration):
    plain = analyze_report(report(closed=True))
    actual = analyze_report(report(closed=True), bar_duration_ms=duration)
    assert actual == plain
    assert actual["funding"]["crossing_check_exact"] is True
    assert actual["round_trips"][0]["exit_ts_ms"] == 86_340_000
    assert actual["reconciliation"]["residual"] == 0


def test_legacy_time_basis_never_becomes_exact():
    funding = analyze_report(report(timing="current_bar_close"), bar_duration_ms=60_000)["funding"]
    assert funding["timestamp_basis"] == "bar_open_label"
    assert funding["crossing_check_exact"] is False


@pytest.mark.parametrize("duration", [0, -1, 1.5, "60000", True])
def test_duration_must_be_a_positive_integer(duration):
    with pytest.raises(ValueError, match="bar_duration_ms"):
        analyze_report(report(), bar_duration_ms=duration)


@pytest.mark.parametrize("stage1", [None, [], "bad", 1])
def test_non_object_stage1_is_value_error(stage1):
    payload = report(); payload["stage1"] = stage1
    with pytest.raises(ValueError, match="stage1"):
        analyze_report(payload)


@pytest.mark.parametrize("kind", ["aborted_forbidden", "failed", None])
def test_incomplete_status_is_rejected(kind):
    payload = report(); payload["result"]["status"]["kind"] = kind
    with pytest.raises(ValueError, match="completed"):
        analyze_report(payload)


@pytest.mark.parametrize("status", [None, {}])
def test_missing_status_kind_is_legacy_compatible(status):
    payload = report(closed=True)
    if status is None:
        del payload["result"]["status"]
    else:
        payload["result"]["status"] = status
    assert analyze_report(payload)["reconciliation"]["residual"] == 0


def test_caller_end_still_compared_before_duration():
    with pytest.raises(ValueError, match="conflicts"):
        analyze_report(report(), replay_end_ts_ms=86_400_000, bar_duration_ms=60_000)
    assert analyze_report(report(), replay_end_ts_ms=86_340_000, bar_duration_ms=60_000)["funding"]["replay_end_ts_ms"] == 86_400_000


@pytest.mark.parametrize("null_stage1", [False, True])
def test_cli_duration_and_null_stage1(tmp_path, null_stage1):
    payload = report()
    if null_stage1: payload["stage1"] = None
    source = tmp_path / "report.json"; source.write_text(json.dumps(payload))
    output = tmp_path / "analytics.json"
    run = subprocess.run([sys.executable, str(ROOT / "helper_scripts/replay/replay_local.py"),
                          "analytics", str(source), "--output", str(output), "--bar-duration-ms", "60000"],
                         capture_output=True, text=True)
    if null_stage1:
        assert run.returncode == 2
        assert len(run.stderr.splitlines()) == 1
        assert "stage1" in run.stderr and "Traceback" not in run.stderr
        assert not output.exists()
    else:
        assert run.returncode == 0, run.stderr
        assert json.loads(output.read_text())["funding"]["crossing_check_exact"] is True
