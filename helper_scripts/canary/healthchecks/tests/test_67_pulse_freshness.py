"""[67] liquidation_pulse_freshness run() 單元測試。

MODULE_NOTE:
  覆蓋四維度 verdict ladder：
    - freshness（latest_age_secs vs warn/fail threshold）
    - row_volume（per-hour rate ladder + 折半 WARN）
    - symbol_coverage（cohort_observed/cohort_total 比例）
    - parse_guard（Buy/Sell enum coverage + non-finite count）

  與 [62-65] tests 共用 conftest.fake_cursor_factory，但本 check 走 fetchone
  + fetchall 兩步 query，要 stub queue 兩個 result。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


# 本 module 不在 conftest fixtures 內（避動到既有 fixture），用本地 loader
HEALTHCHECKS_DIR = Path(__file__).resolve().parent.parent
if str(HEALTHCHECKS_DIR) not in sys.path:
    sys.path.insert(0, str(HEALTHCHECKS_DIR))


def _load_script(filename: str, module_name: str) -> ModuleType:
    """以 importlib 從 digit-prefixed file 載入 module（複用 conftest pattern）。"""
    spec = importlib.util.spec_from_file_location(
        module_name, HEALTHCHECKS_DIR / filename
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def hc67():
    return _load_script(
        "67_liquidation_pulse_freshness.py", "hc67_liquidation_pulse_freshness"
    )


# Test cohort = 5 sym subset（便於覆蓋率比例算術簡單）
TEST_COHORT: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT")


def _make_queue(stats_row: tuple, observed_symbols: list[str]) -> list:
    """構造 fake_cursor_factory 需要的 queue（兩 query：fetchone + fetchall）。

    Query 1 (fetchone)：(n_rows, latest_age_secs, buy, sell, non_finite)
    Query 2 (fetchall)：[(symbol,), ...]
    """
    return [
        [stats_row],  # fetchone 取 list[0]
        [(s,) for s in observed_symbols],  # fetchall iterate
    ]


# ───────────────────────────────────────────────────────────────────────────
# Overall verdict / severity_max 整合
# ───────────────────────────────────────────────────────────────────────────


def test_all_green_passes(hc67, fake_cursor_factory):
    """正常生產：latest age 30s / 600 row / 5 cohort sym / Buy+Sell 均出現。"""
    queue = _make_queue(
        (600, 30.0, 300, 300, 0),
        ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"],
    )
    cur = fake_cursor_factory(queue)
    result = hc67.run(
        cur,
        window_secs=3600,  # 1h
        cohort=TEST_COHORT,
        pass_lower_per_hour=30.0,
        warn_freshness_secs=60.0,
        fail_freshness_secs=300.0,
        warn_coverage=0.80,
        fail_coverage=0.50,
    )
    assert result["verdict"] == "PASS"
    assert result["dimensions"]["freshness"]["verdict"] == "PASS"
    assert result["dimensions"]["row_volume"]["verdict"] == "PASS"
    assert result["dimensions"]["symbol_coverage"]["verdict"] == "PASS"
    assert result["dimensions"]["parse_guard"]["verdict"] == "PASS"
    assert result["cohort_coverage_pct"] == 100.0
    assert result["check_id"] == "[67]"


# ───────────────────────────────────────────────────────────────────────────
# Freshness ladder
# ───────────────────────────────────────────────────────────────────────────


def test_freshness_warn_above_60s(hc67, fake_cursor_factory):
    """latest_age = 120s → WARN（> 60s, < 300s）；其他維 PASS。"""
    queue = _make_queue(
        (100, 120.0, 50, 50, 0),
        list(TEST_COHORT),
    )
    cur = fake_cursor_factory(queue)
    result = hc67.run(
        cur, window_secs=3600, cohort=TEST_COHORT,
        pass_lower_per_hour=30.0,
        warn_freshness_secs=60.0, fail_freshness_secs=300.0,
        warn_coverage=0.80, fail_coverage=0.50,
    )
    assert result["dimensions"]["freshness"]["verdict"] == "WARN"
    assert result["verdict"] == "WARN"
    assert "latest_age=120s" in result["dimensions"]["freshness"]["note"]


def test_freshness_fail_above_300s(hc67, fake_cursor_factory):
    """latest_age = 500s → FAIL。"""
    queue = _make_queue(
        (100, 500.0, 50, 50, 0),
        list(TEST_COHORT),
    )
    cur = fake_cursor_factory(queue)
    result = hc67.run(
        cur, window_secs=3600, cohort=TEST_COHORT,
        pass_lower_per_hour=30.0,
        warn_freshness_secs=60.0, fail_freshness_secs=300.0,
        warn_coverage=0.80, fail_coverage=0.50,
    )
    assert result["dimensions"]["freshness"]["verdict"] == "FAIL"
    assert result["verdict"] == "FAIL"


def test_freshness_none_when_zero_rows(hc67, fake_cursor_factory):
    """0 row → freshness INSUFFICIENT_SAMPLE；row_volume 也 FAIL。"""
    queue = _make_queue(
        (0, None, 0, 0, 0),
        [],
    )
    cur = fake_cursor_factory(queue)
    result = hc67.run(
        cur, window_secs=3600, cohort=TEST_COHORT,
        pass_lower_per_hour=30.0,
        warn_freshness_secs=60.0, fail_freshness_secs=300.0,
        warn_coverage=0.80, fail_coverage=0.50,
    )
    assert result["dimensions"]["freshness"]["verdict"] == "INSUFFICIENT_SAMPLE"
    assert result["dimensions"]["row_volume"]["verdict"] == "FAIL"
    # row_volume FAIL overrides
    assert result["verdict"] == "FAIL"
    assert result["latest_age_secs"] is None


# ───────────────────────────────────────────────────────────────────────────
# Row volume ladder
# ───────────────────────────────────────────────────────────────────────────


def test_volume_pass_at_exact_threshold(hc67, fake_cursor_factory):
    """n_rows = pass_lower_per_hour × hours = 30 → PASS（不嚴格 < ）。"""
    queue = _make_queue(
        (30, 10.0, 15, 15, 0),
        list(TEST_COHORT),
    )
    cur = fake_cursor_factory(queue)
    result = hc67.run(
        cur, window_secs=3600, cohort=TEST_COHORT,
        pass_lower_per_hour=30.0,
        warn_freshness_secs=60.0, fail_freshness_secs=300.0,
        warn_coverage=0.80, fail_coverage=0.50,
    )
    assert result["dimensions"]["row_volume"]["verdict"] == "PASS"


def test_volume_warn_below_pass(hc67, fake_cursor_factory):
    """n_rows = 20 (between warn=15 and pass=30) → WARN。"""
    queue = _make_queue(
        (20, 10.0, 10, 10, 0),
        list(TEST_COHORT),
    )
    cur = fake_cursor_factory(queue)
    result = hc67.run(
        cur, window_secs=3600, cohort=TEST_COHORT,
        pass_lower_per_hour=30.0,
        warn_freshness_secs=60.0, fail_freshness_secs=300.0,
        warn_coverage=0.80, fail_coverage=0.50,
    )
    assert result["dimensions"]["row_volume"]["verdict"] == "WARN"
    assert result["verdict"] == "WARN"


def test_volume_fail_below_warn(hc67, fake_cursor_factory):
    """n_rows = 5 (< warn=15) → FAIL。"""
    queue = _make_queue(
        (5, 10.0, 3, 2, 0),
        list(TEST_COHORT),
    )
    cur = fake_cursor_factory(queue)
    result = hc67.run(
        cur, window_secs=3600, cohort=TEST_COHORT,
        pass_lower_per_hour=30.0,
        warn_freshness_secs=60.0, fail_freshness_secs=300.0,
        warn_coverage=0.80, fail_coverage=0.50,
    )
    assert result["dimensions"]["row_volume"]["verdict"] == "FAIL"
    assert result["verdict"] == "FAIL"


# ───────────────────────────────────────────────────────────────────────────
# Symbol coverage ladder
# ───────────────────────────────────────────────────────────────────────────


def test_coverage_warn_below_80pct(hc67, fake_cursor_factory):
    """3/5 sym = 60% < 80% warn → WARN。"""
    queue = _make_queue(
        (300, 10.0, 150, 150, 0),
        ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    )
    cur = fake_cursor_factory(queue)
    result = hc67.run(
        cur, window_secs=3600, cohort=TEST_COHORT,
        pass_lower_per_hour=30.0,
        warn_freshness_secs=60.0, fail_freshness_secs=300.0,
        warn_coverage=0.80, fail_coverage=0.50,
    )
    assert result["dimensions"]["symbol_coverage"]["verdict"] == "WARN"
    assert result["verdict"] == "WARN"
    assert result["cohort_coverage_pct"] == 60.0
    assert "XRPUSDT" in result["missing_cohort_symbols"]


def test_coverage_fail_below_50pct(hc67, fake_cursor_factory):
    """2/5 sym = 40% < 50% fail → FAIL。"""
    queue = _make_queue(
        (200, 10.0, 100, 100, 0),
        ["BTCUSDT", "ETHUSDT"],
    )
    cur = fake_cursor_factory(queue)
    result = hc67.run(
        cur, window_secs=3600, cohort=TEST_COHORT,
        pass_lower_per_hour=30.0,
        warn_freshness_secs=60.0, fail_freshness_secs=300.0,
        warn_coverage=0.80, fail_coverage=0.50,
    )
    assert result["dimensions"]["symbol_coverage"]["verdict"] == "FAIL"
    assert result["verdict"] == "FAIL"
    assert result["cohort_coverage_pct"] == 40.0


def test_coverage_excludes_non_cohort(hc67, fake_cursor_factory):
    """Non-cohort symbols (BSBUSDT) 不算 coverage 分子。"""
    queue = _make_queue(
        (500, 10.0, 250, 250, 0),
        ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"],
        # 注意：BSBUSDT 即使在 raw distinct 內，因為 SQL 已過 cohort filter,
        # observed_symbols 只該回 cohort 內的。本 test 直接驗 cohort-only。
    )
    cur = fake_cursor_factory(queue)
    result = hc67.run(
        cur, window_secs=3600, cohort=TEST_COHORT,
        pass_lower_per_hour=30.0,
        warn_freshness_secs=60.0, fail_freshness_secs=300.0,
        warn_coverage=0.80, fail_coverage=0.50,
    )
    assert result["cohort_observed"] == 5
    assert result["dimensions"]["symbol_coverage"]["verdict"] == "PASS"


# ───────────────────────────────────────────────────────────────────────────
# Parse guard
# ───────────────────────────────────────────────────────────────────────────


def test_parse_guard_fails_when_buy_absent(hc67, fake_cursor_factory):
    """100% Sell row → Buy_side_absent FAIL（parser silent degradation）。"""
    queue = _make_queue(
        (100, 30.0, 0, 100, 0),
        list(TEST_COHORT),
    )
    cur = fake_cursor_factory(queue)
    result = hc67.run(
        cur, window_secs=3600, cohort=TEST_COHORT,
        pass_lower_per_hour=30.0,
        warn_freshness_secs=60.0, fail_freshness_secs=300.0,
        warn_coverage=0.80, fail_coverage=0.50,
    )
    assert result["dimensions"]["parse_guard"]["verdict"] == "FAIL"
    assert "Buy_side_absent" in result["dimensions"]["parse_guard"]["note"]
    assert result["verdict"] == "FAIL"


def test_parse_guard_fails_when_sell_absent(hc67, fake_cursor_factory):
    """100% Buy → Sell_side_absent。"""
    queue = _make_queue(
        (100, 30.0, 100, 0, 0),
        list(TEST_COHORT),
    )
    cur = fake_cursor_factory(queue)
    result = hc67.run(
        cur, window_secs=3600, cohort=TEST_COHORT,
        pass_lower_per_hour=30.0,
        warn_freshness_secs=60.0, fail_freshness_secs=300.0,
        warn_coverage=0.80, fail_coverage=0.50,
    )
    assert result["dimensions"]["parse_guard"]["verdict"] == "FAIL"
    assert "Sell_side_absent" in result["dimensions"]["parse_guard"]["note"]


def test_parse_guard_fails_on_non_finite(hc67, fake_cursor_factory):
    """non_finite_count = 5 → FAIL（qty/price <= 0）。"""
    queue = _make_queue(
        (100, 30.0, 50, 50, 5),
        list(TEST_COHORT),
    )
    cur = fake_cursor_factory(queue)
    result = hc67.run(
        cur, window_secs=3600, cohort=TEST_COHORT,
        pass_lower_per_hour=30.0,
        warn_freshness_secs=60.0, fail_freshness_secs=300.0,
        warn_coverage=0.80, fail_coverage=0.50,
    )
    assert result["dimensions"]["parse_guard"]["verdict"] == "FAIL"
    assert "non_finite_qty_or_price=5" in result["dimensions"]["parse_guard"]["note"]


# ───────────────────────────────────────────────────────────────────────────
# severity_max integration
# ───────────────────────────────────────────────────────────────────────────


def test_severity_max_fail_overrides_warn(hc67, fake_cursor_factory):
    """WARN freshness + FAIL coverage → overall FAIL（嚴重者 wins）。"""
    queue = _make_queue(
        (200, 120.0, 100, 100, 0),  # latest_age=120s → WARN freshness
        ["BTCUSDT", "ETHUSDT"],     # 40% coverage → FAIL coverage
    )
    cur = fake_cursor_factory(queue)
    result = hc67.run(
        cur, window_secs=3600, cohort=TEST_COHORT,
        pass_lower_per_hour=30.0,
        warn_freshness_secs=60.0, fail_freshness_secs=300.0,
        warn_coverage=0.80, fail_coverage=0.50,
    )
    assert result["dimensions"]["freshness"]["verdict"] == "WARN"
    assert result["dimensions"]["symbol_coverage"]["verdict"] == "FAIL"
    assert result["verdict"] == "FAIL"


def test_sql_uses_window_secs(hc67, fake_cursor_factory):
    """確保 SQL 用 window_secs 參數。"""
    queue = _make_queue(
        (10, 10.0, 5, 5, 0),
        list(TEST_COHORT),
    )
    cur = fake_cursor_factory(queue)
    hc67.run(
        cur, window_secs=7200, cohort=TEST_COHORT,
        pass_lower_per_hour=30.0,
        warn_freshness_secs=60.0, fail_freshness_secs=300.0,
        warn_coverage=0.80, fail_coverage=0.50,
    )
    # 第一個 query 用 window_secs；第二個 query 用 window_secs + cohort
    sql1, params1 = cur.executed_sqls[0]
    assert "market.liquidations" in sql1
    assert "MAX(ts)" in sql1
    assert params1 == (7200,)

    sql2, params2 = cur.executed_sqls[1]
    assert "DISTINCT symbol" in sql2
    assert "symbol = ANY" in sql2
    # 注意 cohort 可能轉成 list；SQL params 預期 (window_secs, list)
    assert params2[0] == 7200
    assert set(params2[1]) == set(TEST_COHORT)


# ───────────────────────────────────────────────────────────────────────────
# Hardcoded cohort sanity（與 main.rs DEFAULT_COHORT 對齊）
# ───────────────────────────────────────────────────────────────────────────


def test_cohort_size_25(hc67):
    """COHORT_SYMBOLS 必 = 25 sym（與 main.rs 對齊；POLUSDT 取代 MATICUSDT）。"""
    assert len(hc67.COHORT_SYMBOLS) == 25
    assert "POLUSDT" in hc67.COHORT_SYMBOLS
    assert "MATICUSDT" not in hc67.COHORT_SYMBOLS
    assert "BTCUSDT" in hc67.COHORT_SYMBOLS
    assert "ETHUSDT" in hc67.COHORT_SYMBOLS
