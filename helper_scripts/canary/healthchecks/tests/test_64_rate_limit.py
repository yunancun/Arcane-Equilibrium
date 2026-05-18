"""[64] close_maker_rate_limit_pause_duration run() 單元測試。"""

from __future__ import annotations


def test_empty_returns_insufficient(hc64, fake_cursor_factory):
    cur = fake_cursor_factory([[], []])  # per_symbol_rows + global_rows
    result = hc64.run(
        cur,
        window_secs=604800,
        engine_modes=["demo", "live_demo"],
        per_symbol_warn=5,
        per_symbol_fail=30,
        global_warn=5,
        global_fail=30,
    )
    assert result["verdict"] == "INSUFFICIENT_SAMPLE"


def test_per_symbol_pass_under_threshold(hc64, fake_cursor_factory):
    # 7d window → 7 days; 1 BTC backoff = 1/7 per_day = 0.14 ≤ 5 → PASS
    per_symbol_rows = [("BTCUSDT", "demo", 1)]
    global_rows = []
    cur = fake_cursor_factory([per_symbol_rows, global_rows])
    result = hc64.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        per_symbol_warn=5,
        per_symbol_fail=30,
        global_warn=5,
        global_fail=30,
    )
    assert result["verdict"] == "PASS"
    assert result["per_symbol_cells"][0]["verdict"] == "PASS"


def test_per_symbol_warn_band(hc64, fake_cursor_factory):
    # 7d → 70/7=10 per day → WARN band (5,30]
    per_symbol_rows = [("BTCUSDT", "demo", 70)]
    cur = fake_cursor_factory([per_symbol_rows, []])
    result = hc64.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        per_symbol_warn=5,
        per_symbol_fail=30,
        global_warn=5,
        global_fail=30,
    )
    assert result["verdict"] == "WARN"


def test_per_symbol_fail_band(hc64, fake_cursor_factory):
    # 7d → 1000/7=143 per day → FAIL (>30)
    per_symbol_rows = [("BTCUSDT", "demo", 1000)]
    cur = fake_cursor_factory([per_symbol_rows, []])
    result = hc64.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        per_symbol_warn=5,
        per_symbol_fail=30,
        global_warn=5,
        global_fail=30,
    )
    assert result["verdict"] == "FAIL"


def test_global_pause_scope_tag_warning(hc64, fake_cursor_factory):
    """global pause rows 沒有 details.rate_limit_scope='global' tag → WARN scope_note。"""
    # 10 global pause / 7d ≈ 1.4 per day → PASS rate；但 scope_tagged=5 < 10 → WARN
    cur = fake_cursor_factory([
        [],  # per_symbol
        [("demo", 10, 5)],  # 10 global pause, only 5 tagged
    ])
    result = hc64.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        per_symbol_warn=5,
        per_symbol_fail=30,
        global_warn=5,
        global_fail=30,
    )
    # overall verdict 應被 scope WARN 拉高（即使 rate verdict 是 PASS）
    assert result["verdict"] == "WARN"
    g = result["global_cells"][0]
    assert g["scope_tagged_count"] == 5
    assert "tagged" in g["scope_note"]


def test_multi_symbol_takes_worst(hc64, fake_cursor_factory):
    per_symbol_rows = [
        ("BTCUSDT", "demo", 1),  # PASS
        ("ETHUSDT", "demo", 70),  # WARN
        ("SOLUSDT", "demo", 1000),  # FAIL
    ]
    cur = fake_cursor_factory([per_symbol_rows, []])
    result = hc64.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        per_symbol_warn=5,
        per_symbol_fail=30,
        global_warn=5,
        global_fail=30,
    )
    assert result["verdict"] == "FAIL"
    assert len(result["per_symbol_cells"]) == 3
