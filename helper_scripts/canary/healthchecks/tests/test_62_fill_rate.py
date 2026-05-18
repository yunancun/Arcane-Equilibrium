"""[62] close_maker_fill_rate run() 邏輯單元測試（fake cursor）。"""

from __future__ import annotations


def test_empty_window_returns_insufficient_sample(hc62, fake_cursor_factory):
    cur = fake_cursor_factory([[]])  # 0 rows
    result = hc62.run(
        cur,
        window_secs=604800,
        engine_modes=["demo", "live_demo"],
        pass_lower=0.60,
        warn_lower=0.40,
        min_sample=30,
    )
    assert result["verdict"] == "INSUFFICIENT_SAMPLE"
    assert result["total_attempts"] == 0
    assert result["check_id"] == "[62]"


def test_pass_above_threshold(hc62, fake_cursor_factory):
    # demo 100 attempts / 80 fills → Wilson lower ≈ 0.711 ≥ 0.60 → PASS
    rows = [[("demo", 100, 80, 20)]]
    cur = fake_cursor_factory(rows)
    result = hc62.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        pass_lower=0.60,
        warn_lower=0.40,
        min_sample=30,
    )
    assert result["verdict"] == "PASS"
    assert result["total_attempts"] == 100
    assert result["total_fills"] == 80
    assert result["cells"][0]["wilson_lower"] >= 0.60


def test_fail_when_upper_below_warn(hc62, fake_cursor_factory):
    # demo 100 / 20 fills → Wilson upper ≈ 0.288 < 0.40 → FAIL
    rows = [[("demo", 100, 20, 80)]]
    cur = fake_cursor_factory(rows)
    result = hc62.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        pass_lower=0.60,
        warn_lower=0.40,
        min_sample=30,
    )
    assert result["verdict"] == "FAIL"
    assert result["cells"][0]["wilson_upper"] < 0.40


def test_multi_engine_takes_most_severe(hc62, fake_cursor_factory):
    rows = [
        [
            ("demo", 100, 80, 20),  # PASS
            ("live_demo", 100, 20, 80),  # FAIL
        ]
    ]
    cur = fake_cursor_factory(rows)
    result = hc62.run(
        cur,
        window_secs=604800,
        engine_modes=["demo", "live_demo"],
        pass_lower=0.60,
        warn_lower=0.40,
        min_sample=30,
    )
    assert result["verdict"] == "FAIL"  # FAIL wins
    assert len(result["cells"]) == 2


def test_below_min_sample_each_cell_insufficient(hc62, fake_cursor_factory):
    rows = [[("demo", 10, 7, 3)]]  # n<30
    cur = fake_cursor_factory(rows)
    result = hc62.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        pass_lower=0.60,
        warn_lower=0.40,
        min_sample=30,
    )
    assert result["cells"][0]["verdict"] == "INSUFFICIENT_SAMPLE"
    # overall = severity_max(PASS, INSUFFICIENT) = INSUFFICIENT
    assert result["verdict"] == "INSUFFICIENT_SAMPLE"


def test_alternative_thresholds_via_kwargs(hc62, fake_cursor_factory):
    """AC-19 conservative ladder: 25 / 50。"""
    # n=100 k=30 → Wilson (0.218, 0.398); lower<0.50 + upper>0.25 → WARN
    rows = [[("demo", 100, 30, 70)]]
    cur = fake_cursor_factory(rows)
    result = hc62.run(
        cur,
        window_secs=604800 * 2,
        engine_modes=["demo"],
        pass_lower=0.50,
        warn_lower=0.25,
        min_sample=30,
    )
    assert result["verdict"] == "WARN"
    assert result["thresholds"]["pass_lower"] == 0.50


def test_sql_uses_engine_mode_filter(hc62, fake_cursor_factory):
    """確保 SQL where clause 用 engine_mode = ANY(%s::text[])。"""
    rows = [[]]
    cur = fake_cursor_factory(rows)
    hc62.run(
        cur,
        window_secs=3600,
        engine_modes=["demo"],
        pass_lower=0.60,
        warn_lower=0.40,
        min_sample=30,
    )
    sql, params = cur.executed_sqls[0]
    assert "close_maker_attempt = TRUE" in sql
    assert "engine_mode = ANY" in sql
    assert params == (3600, ["demo"])
