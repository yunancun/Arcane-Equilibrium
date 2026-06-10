"""altcap_basket 聚焦測試 — equal-weight ex-BTC CORE25 + PIT walk-forward（MIT M3 熱點）。

覆蓋（對映 PA P3b §B + QC B1 spec §2）：
  - CORE25 ex-BTC = 24（減 BTCUSDT）。
  - equal-weight：r_altcap_t = mean over PIT-alive constituents（每檔權重 1/N_t）。
  - ★ PIT walk-forward：bar t 成員 = alive_from ≤ t ≤ alive_to（NOT 今日 survivors）。
  - 無 zombie forward-fill：下市 symbol 在 alive_to 後離籃，不續用最後價。
  - included=False 行（unknown_lifetime / outside_window）不進籃。
  - producer 不可建（無成員 / 價缺）→ 空 returns（B1 DEFER）。

Mac-tested（純函數核心，無 DB）。Linux smoke（24 symbol × window 真 market.klines）owed。
"""

from __future__ import annotations

import datetime as dt

import pytest

from program_code.research.altcap_basket import (
    CORE25_EX_BTC,
    AltcapReturnSeries,
    build_altcap_returns,
)


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def test_core25_ex_btc_is_24_without_btc():
    """CORE25 ex-BTC = 24 檔（凍結減 BTCUSDT）。"""
    assert len(CORE25_EX_BTC) == 24
    assert "BTCUSDT" not in CORE25_EX_BTC
    # 仍含 CORE25 其他成員。
    assert "ADAUSDT" in CORE25_EX_BTC and "ETHUSDT" in CORE25_EX_BTC


def test_pit_walk_forward_entry_and_exit():
    """★ PIT walk-forward：新上市在 alive_from 進籃、下市在 alive_to 後離籃（無 zombie forward-fill）。"""
    dates = [_d(f"2024-06-{i:02d}") for i in range(1, 11)]
    rows = [
        {"symbol": "ADAUSDT", "included": True, "alive_from_utc": "2024-06-01", "alive_to_utc": "2024-06-10"},
        {"symbol": "APTUSDT", "included": True, "alive_from_utc": "2024-06-05", "alive_to_utc": "2024-06-10"},  # 進
        {"symbol": "ARBUSDT", "included": True, "alive_from_utc": "2024-06-01", "alive_to_utc": "2024-06-04"},   # 離
    ]
    closes = {
        sym: {dates[i]: 100.0 + i for i in range(10)}
        for sym in ("ADAUSDT", "APTUSDT", "ARBUSDT")
    }
    res = build_altcap_returns(rows, closes, window_start=_d("2024-06-01"), window_end=_d("2024-06-10"))
    # ARB 在 day 02-04 在籃；day 05 起離籃（alive_to=06-04）。
    assert "ARBUSDT" in res.constituents_by_day[_d("2024-06-04")]
    assert "ARBUSDT" not in res.constituents_by_day[_d("2024-06-05")]
    # APT 在 day 05 起進籃（alive_from=06-05）。
    assert "APTUSDT" not in res.constituents_by_day.get(_d("2024-06-04"), [])
    assert "APTUSDT" in res.constituents_by_day[_d("2024-06-05")]


def test_excluded_rows_not_in_basket():
    """included=False 行（unknown_lifetime / outside_window）不進籃。"""
    dates = [_d(f"2024-06-{i:02d}") for i in range(1, 6)]
    rows = [
        {"symbol": "ADAUSDT", "included": True, "alive_from_utc": "2024-06-01", "alive_to_utc": "2024-06-05"},
        {"symbol": "XRPUSDT", "included": False, "alive_from_utc": None, "alive_to_utc": None},  # excluded
    ]
    closes = {
        "ADAUSDT": {dates[i]: 100.0 + i for i in range(5)},
        "XRPUSDT": {dates[i]: 50.0 + i for i in range(5)},  # 有價但 excluded → 不進籃
    }
    res = build_altcap_returns(rows, closes, window_start=_d("2024-06-01"), window_end=_d("2024-06-05"))
    for day, members in res.constituents_by_day.items():
        assert "XRPUSDT" not in members


def test_equal_weight_mean_of_constituents():
    """equal-weight：r_altcap_t = mean over alive constituents（每檔 1/N_t）。"""
    dates = [_d(f"2024-06-{i:02d}") for i in range(1, 4)]
    rows = [
        {"symbol": "ADAUSDT", "included": True, "alive_from_utc": "2024-06-01", "alive_to_utc": "2024-06-03"},
        {"symbol": "ETHUSDT", "included": True, "alive_from_utc": "2024-06-01", "alive_to_utc": "2024-06-03"},
    ]
    # ADA +10%/day, ETH +20%/day → mean = +15%/day。
    closes = {
        "ADAUSDT": {dates[0]: 100.0, dates[1]: 110.0, dates[2]: 121.0},
        "ETHUSDT": {dates[0]: 100.0, dates[1]: 120.0, dates[2]: 144.0},
    }
    res = build_altcap_returns(rows, closes, window_start=_d("2024-06-01"), window_end=_d("2024-06-03"))
    # day 02 return = mean(0.10, 0.20) = 0.15。
    assert res.returns[dates[1]] == pytest.approx(0.15, abs=1e-9)
    assert res.n_constituents_by_day[dates[1]] == 2


def test_no_constituents_yields_empty_returns():
    """無成員 alive（全 excluded）→ 空 returns（B1 見 altcap=None-等價 → DEFER）。"""
    dates = [_d(f"2024-06-{i:02d}") for i in range(1, 4)]
    rows = [
        {"symbol": "XRPUSDT", "included": False, "alive_from_utc": None, "alive_to_utc": None},
    ]
    closes = {"XRPUSDT": {dates[i]: 50.0 + i for i in range(3)}}
    res = build_altcap_returns(rows, closes, window_start=_d("2024-06-01"), window_end=_d("2024-06-03"))
    assert res.returns == {}


def test_btc_excluded_from_basket():
    """BTCUSDT 即使在 rows + closes 也被 ex_symbols 排除（ex-BTC）。"""
    dates = [_d(f"2024-06-{i:02d}") for i in range(1, 4)]
    rows = [
        {"symbol": "BTCUSDT", "included": True, "alive_from_utc": "2024-06-01", "alive_to_utc": "2024-06-03"},
        {"symbol": "ADAUSDT", "included": True, "alive_from_utc": "2024-06-01", "alive_to_utc": "2024-06-03"},
    ]
    closes = {
        "BTCUSDT": {dates[i]: 60000.0 + i * 1000 for i in range(3)},
        "ADAUSDT": {dates[i]: 100.0 + i for i in range(3)},
    }
    res = build_altcap_returns(rows, closes, window_start=_d("2024-06-01"), window_end=_d("2024-06-03"))
    for members in res.constituents_by_day.values():
        assert "BTCUSDT" not in members


def test_window_clips_returns():
    """籃子報酬只在 [window_start, window_end] 內算（窗外日期不計）。"""
    dates = [_d(f"2024-06-{i:02d}") for i in range(1, 11)]
    rows = [
        {"symbol": "ADAUSDT", "included": True, "alive_from_utc": "2024-06-01", "alive_to_utc": "2024-06-10"},
    ]
    closes = {"ADAUSDT": {dates[i]: 100.0 + i for i in range(10)}}
    # 窗只取 06-03 → 06-06。
    res = build_altcap_returns(rows, closes, window_start=_d("2024-06-03"), window_end=_d("2024-06-06"))
    for day in res.returns:
        assert _d("2024-06-03") <= day <= _d("2024-06-06")
