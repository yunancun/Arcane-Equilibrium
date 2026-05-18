"""[65] reject_sample_healthcheck run() 單元測試。"""

from __future__ import annotations


def test_empty_window_returns_insufficient(hc65, fake_cursor_factory):
    cur = fake_cursor_factory([[]])
    result = hc65.run(
        cur,
        window_secs=604800,
        engine_modes=["demo", "live_demo"],
        min_attempts=5,
    )
    assert result["verdict"] == "INSUFFICIENT_SAMPLE"
    assert result["total_attempts"] == 0
    assert result["missing_categories"] == []


def test_both_categories_present_passes(hc65, fake_cursor_factory):
    rows = [[
        # engine_mode, attempts, postonly, max_pending
        ("demo", 50, 3, 2),
    ]]
    cur = fake_cursor_factory(rows)
    result = hc65.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        min_attempts=5,
    )
    assert result["verdict"] == "PASS"
    assert result["cells"][0]["verdict"] == "PASS"
    assert result["total_postonly_samples"] == 3
    assert result["total_max_pending_samples"] == 2


def test_missing_postonly_fails(hc65, fake_cursor_factory):
    rows = [[("demo", 50, 0, 3)]]
    cur = fake_cursor_factory(rows)
    result = hc65.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        min_attempts=5,
    )
    assert result["verdict"] == "FAIL"
    assert "demo/EC_PostOnlyWillTakeLiquidity" in result["missing_categories"]


def test_missing_max_pending_fails(hc65, fake_cursor_factory):
    rows = [[("demo", 50, 5, 0)]]
    cur = fake_cursor_factory(rows)
    result = hc65.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        min_attempts=5,
    )
    assert result["verdict"] == "FAIL"
    assert "demo/EC_ReachMaxPendingOrders" in result["missing_categories"]


def test_below_min_attempts_insufficient(hc65, fake_cursor_factory):
    rows = [[("demo", 2, 1, 1)]]
    cur = fake_cursor_factory(rows)
    result = hc65.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        min_attempts=5,
    )
    # 單 cell INSUFFICIENT；overall 也 INSUFFICIENT
    assert result["verdict"] == "INSUFFICIENT_SAMPLE"
    assert result["cells"][0]["verdict"] == "INSUFFICIENT_SAMPLE"


def test_mixed_engine_modes(hc65, fake_cursor_factory):
    """demo PASS + live_demo FAIL → overall FAIL。"""
    rows = [[
        ("demo", 50, 3, 2),  # PASS
        ("live_demo", 50, 0, 5),  # missing PostOnly → FAIL
    ]]
    cur = fake_cursor_factory(rows)
    result = hc65.run(
        cur,
        window_secs=604800,
        engine_modes=["demo", "live_demo"],
        min_attempts=5,
    )
    assert result["verdict"] == "FAIL"
    assert "live_demo/EC_PostOnlyWillTakeLiquidity" in result["missing_categories"]
    assert any(c["verdict"] == "PASS" for c in result["cells"])
    assert any(c["verdict"] == "FAIL" for c in result["cells"])
