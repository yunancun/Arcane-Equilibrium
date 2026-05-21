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


# ─────────────────────────────────────────────────────────────────────────────
# P1-OBS-FILL-RATE-STRATIFY tests（2026-05-21）
# 驗證 --stratify hour / dow / both 三模式行為，並確保 none 預設逐字節向後兼容。
# ─────────────────────────────────────────────────────────────────────────────


def test_stratify_none_keeps_legacy_sql_verbatim(hc62, fake_cursor_factory):
    """stratify=none 必須與舊版 SQL 逐字節相同（含 GROUP BY engine_mode 不帶 extra cols）。"""
    rows = [[]]
    cur = fake_cursor_factory(rows)
    hc62.run(
        cur,
        window_secs=3600,
        engine_modes=["demo"],
        pass_lower=0.60,
        warn_lower=0.40,
        min_sample=30,
        stratify="none",
    )
    sql, _ = cur.executed_sqls[0]
    # none 模式 SQL 不應包含 EXTRACT(HOUR ...) / EXTRACT(DOW ...) 任何痕跡
    assert "EXTRACT(HOUR" not in sql
    assert "EXTRACT(DOW" not in sql
    assert "GROUP BY engine_mode" in sql
    # 不要在 GROUP BY engine_mode 之後追加 extra 列
    group_idx = sql.index("GROUP BY engine_mode")
    order_idx = sql.index("ORDER BY engine_mode")
    assert "," not in sql[group_idx:order_idx]


def test_stratify_hour_adds_extract_hour_clauses(hc62, fake_cursor_factory):
    rows = [[]]
    cur = fake_cursor_factory(rows)
    hc62.run(
        cur,
        window_secs=3600,
        engine_modes=["demo"],
        pass_lower=0.60,
        warn_lower=0.40,
        min_sample=30,
        stratify="hour",
    )
    sql, params = cur.executed_sqls[0]
    assert "EXTRACT(HOUR FROM ts)" in sql
    assert "EXTRACT(DOW" not in sql
    assert "AS hour" in sql
    assert params == (3600, ["demo"])


def test_stratify_dow_adds_extract_dow_clauses(hc62, fake_cursor_factory):
    rows = [[]]
    cur = fake_cursor_factory(rows)
    hc62.run(
        cur,
        window_secs=3600,
        engine_modes=["demo"],
        pass_lower=0.60,
        warn_lower=0.40,
        min_sample=30,
        stratify="dow",
    )
    sql, _ = cur.executed_sqls[0]
    assert "EXTRACT(DOW FROM ts)" in sql
    assert "EXTRACT(HOUR" not in sql
    assert "AS dow" in sql


def test_stratify_both_adds_hour_and_dow(hc62, fake_cursor_factory):
    rows = [[]]
    cur = fake_cursor_factory(rows)
    hc62.run(
        cur,
        window_secs=3600,
        engine_modes=["demo"],
        pass_lower=0.60,
        warn_lower=0.40,
        min_sample=30,
        stratify="both",
    )
    sql, _ = cur.executed_sqls[0]
    assert "EXTRACT(HOUR FROM ts)" in sql
    assert "EXTRACT(DOW FROM ts)" in sql


def test_stratify_hour_rows_carry_hour_field(hc62, fake_cursor_factory):
    """stratify=hour 時 row schema = (engine_mode, attempts, fills, fallbacks, hour)，
    cells dict 應帶 hour 欄位。"""
    rows = [[
        ("demo", 100, 80, 20, 14),
        ("demo", 50, 40, 10, 22),
    ]]
    cur = fake_cursor_factory(rows)
    result = hc62.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        pass_lower=0.60,
        warn_lower=0.40,
        min_sample=30,
        stratify="hour",
    )
    assert result["stratify"] == "hour"
    assert result["cells"][0]["hour"] == 14
    assert result["cells"][1]["hour"] == 22
    assert "dow" not in result["cells"][0]


def test_stratify_dow_rows_carry_dow_field(hc62, fake_cursor_factory):
    rows = [[
        ("demo", 100, 80, 20, 1),  # Monday
        ("demo", 100, 80, 20, 6),  # Saturday
    ]]
    cur = fake_cursor_factory(rows)
    result = hc62.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        pass_lower=0.60,
        warn_lower=0.40,
        min_sample=30,
        stratify="dow",
    )
    assert result["stratify"] == "dow"
    assert result["cells"][0]["dow"] == 1
    assert result["cells"][1]["dow"] == 6
    assert "hour" not in result["cells"][0]


def test_stratify_both_rows_carry_hour_and_dow(hc62, fake_cursor_factory):
    rows = [[("demo", 100, 80, 20, 14, 3)]]
    cur = fake_cursor_factory(rows)
    result = hc62.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        pass_lower=0.60,
        warn_lower=0.40,
        min_sample=30,
        stratify="both",
    )
    assert result["cells"][0]["hour"] == 14
    assert result["cells"][0]["dow"] == 3


def test_stratify_ignores_insufficient_cells_for_overall(hc62, fake_cursor_factory):
    """Stratify 模式下 INSUFFICIENT cells 不影響 overall — 1 PASS + N INSUFFICIENT
    應 overall = PASS（避免稀疏 hour/dow bucket 把 verdict 拉成 INSUFFICIENT）。"""
    rows = [[
        ("demo", 100, 80, 20, 14),  # PASS (n=100, fill=0.8)
        ("demo", 5, 4, 1, 22),       # INSUFFICIENT (n<30)
        ("demo", 3, 2, 1, 3),        # INSUFFICIENT
    ]]
    cur = fake_cursor_factory(rows)
    result = hc62.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        pass_lower=0.60,
        warn_lower=0.40,
        min_sample=30,
        stratify="hour",
    )
    assert result["verdict"] == "PASS"
    # cells 仍保留三 cell（不過濾），只是 overall 不被 INSUFFICIENT 拖累
    assert len(result["cells"]) == 3


def test_stratify_all_insufficient_overall_is_insufficient(hc62, fake_cursor_factory):
    """全部 cells INSUFFICIENT → overall INSUFFICIENT。"""
    rows = [[
        ("demo", 5, 4, 1, 14),
        ("demo", 3, 2, 1, 22),
    ]]
    cur = fake_cursor_factory(rows)
    result = hc62.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        pass_lower=0.60,
        warn_lower=0.40,
        min_sample=30,
        stratify="hour",
    )
    assert result["verdict"] == "INSUFFICIENT_SAMPLE"


def test_stratify_fail_cell_pulls_overall_to_fail(hc62, fake_cursor_factory):
    """Stratify 模式下 FAIL cell 仍應 dominate overall verdict。"""
    rows = [[
        ("demo", 100, 80, 20, 14),   # PASS
        ("demo", 100, 20, 80, 22),   # FAIL (upper < 0.40)
    ]]
    cur = fake_cursor_factory(rows)
    result = hc62.run(
        cur,
        window_secs=604800,
        engine_modes=["demo"],
        pass_lower=0.60,
        warn_lower=0.40,
        min_sample=30,
        stratify="hour",
    )
    assert result["verdict"] == "FAIL"


def test_stratify_sql_addons_mapping(hc62):
    """直接驗證 _stratify_sql_addons mapping，避免 SQL 字串組裝失誤。"""
    assert hc62._stratify_sql_addons("none") == ("", "")
    sel_h, grp_h = hc62._stratify_sql_addons("hour")
    assert "EXTRACT(HOUR FROM ts)" in sel_h and "AS hour" in sel_h
    assert "EXTRACT(HOUR FROM ts)" in grp_h
    sel_d, grp_d = hc62._stratify_sql_addons("dow")
    assert "EXTRACT(DOW FROM ts)" in sel_d and "AS dow" in sel_d
    assert "EXTRACT(DOW FROM ts)" in grp_d
    sel_b, grp_b = hc62._stratify_sql_addons("both")
    assert "AS hour" in sel_b and "AS dow" in sel_b
    assert "EXTRACT(HOUR FROM ts)" in grp_b and "EXTRACT(DOW FROM ts)" in grp_b


def test_result_includes_stratify_key_in_none_mode(hc62, fake_cursor_factory):
    """向後兼容檢查：stratify=none 時 result 仍含 'stratify' key 等於 'none'。
    舊 caller 若不讀此 key 不受影響，新 caller 可用此判斷模式。"""
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
    assert result["stratify"] == "none"
