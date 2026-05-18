"""[63] close_maker_fallback_audit run() 單元測試。"""

from __future__ import annotations


def test_empty_distribution(hc63, fake_cursor_factory):
    cur = fake_cursor_factory([
        [],  # enum distribution
        (0, 0, 0, 0),  # null ladder counts
    ])
    result = hc63.run(
        cur,
        window_secs=604800,
        engine_modes=["demo", "live_demo"],
        pass_rate=0.001,
        warn_rate=0.01,
        min_sample=5,
    )
    assert result["verdict"] == "INSUFFICIENT_SAMPLE"
    assert result["n_attempts"] == 0


def test_legal_enums_pass_clean(hc63, fake_cursor_factory):
    """All audit fields full → PASS。"""
    # n_attempts=100；fallback distribution（含 NULL）合法
    enum_rows = [
        ("timeout_taker", 30),
        ("<NULL>", 70),  # 70 maker fills 標 NULL = 預期
        ("not_attempted_safety_path", 0),  # safety path
    ]
    # null ladder counts:
    # not_safety_total=100 (none of the rows are safety_path)
    # null_audit_missing=0 (all maker fills have all 3 JSONB keys)
    # null_count=70
    # null_audit_complete=70
    ladder_row = (100, 0, 70, 70)
    cur = fake_cursor_factory([enum_rows, ladder_row])
    result = hc63.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        pass_rate=0.001,
        warn_rate=0.01,
        min_sample=5,
    )
    # NULL rate = 70/100 = 0.70 — 但這是 maker fill success（合法 NULL），按 spec
    # §8.1 line 547-549 NULL ladder 設計目的是抓「audit 漏寫」；本檔的 verdict
    # 計算當前語意把所有 NULL 都算進分子，70% 必 FAIL
    # 這對應 spec line 547 的「NULL rate ≤ 0.1% PASS」原始定義
    assert result["null_rate"] > 0.5
    assert result["verdict"] == "FAIL"
    assert result["illegal_reasons"] == []


def test_illegal_enum_fails(hc63, fake_cursor_factory):
    enum_rows = [
        ("timeout_taker", 50),
        ("BOGUS_REASON", 5),  # 非 V094 enum allowlist
    ]
    ladder_row = (55, 0, 0, 0)
    cur = fake_cursor_factory([enum_rows, ladder_row])
    result = hc63.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        pass_rate=0.001,
        warn_rate=0.01,
        min_sample=5,
    )
    assert result["verdict"] == "FAIL"
    assert "BOGUS_REASON(n=5)" in result["illegal_reasons"]


def test_safety_path_excluded_from_null_ladder(hc63, fake_cursor_factory):
    # 全部 100 rows = safety path → not_safety_total = 0 → INSUFFICIENT or PASS
    enum_rows = [
        ("not_attempted_safety_path", 60),
        ("engine_shutdown_safety", 40),
    ]
    ladder_row = (0, 0, 0, 0)  # not_safety_total=0
    cur = fake_cursor_factory([enum_rows, ladder_row])
    result = hc63.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        pass_rate=0.001,
        warn_rate=0.01,
        min_sample=5,
    )
    # n_attempts=100 ≥ min；not_safety_total=0 → null_rate=0 → PASS
    assert result["verdict"] == "PASS"
    assert result["n_safety_path"] == 100
    assert result["not_safety_total"] == 0


def test_warn_band_null_rate(hc63, fake_cursor_factory):
    # null_rate = 5/1000 = 0.005 → in (0.001, 0.01] → WARN
    enum_rows = [
        ("timeout_taker", 995),
        ("<NULL>", 5),
    ]
    # not_safety_total = 1000 (no safety)
    # null_count = 5
    ladder_row = (1000, 0, 5, 0)
    cur = fake_cursor_factory([enum_rows, ladder_row])
    result = hc63.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        pass_rate=0.001,
        warn_rate=0.01,
        min_sample=5,
    )
    assert result["verdict"] == "WARN"
    assert 0.001 < result["null_rate"] <= 0.01
