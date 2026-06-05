"""residual_alpha_producer_db 純核心測試（R-2 leak surface）。

只測無 DB 的純函數：epoch 轉換、contained-bar 報酬（排除 straddling/partial）、
PIT active universe（含已下市、排除 survivorship）、組裝 drop 路徑。
DB 查詢層在 Linux runtime 另行驗證。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from program_code.ml_training.residual_alpha_producer_db import (
    assemble_residual_inputs,
    build_residual_report_from_data,
    contained_bar_return_bps,
    load_btc_klines,
    load_round_trips,
    pit_active_symbols,
    to_epoch_seconds,
)


class _FakeCursor:
    """模擬 psycopg2 cursor 的 context manager。"""

    def __init__(self, rows):
        self._rows = rows
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self, **kwargs):
        return _FakeCursor(self._rows)


def _bars(start: float, end: float, *, open_: float = 100.0, close: float = 100.0, step: float = 60.0):
    out = []
    ts = start
    while ts < end:
        out.append({"ts": ts, "open": open_, "close": close})
        ts += step
    return out


# ---- to_epoch_seconds ----

def test_to_epoch_seconds_variants():
    aware = datetime(2026, 6, 5, 0, 0, 0, tzinfo=timezone.utc)
    assert to_epoch_seconds(aware) == pytest.approx(aware.timestamp())
    # naive 當 UTC
    naive = datetime(2026, 6, 5, 0, 0, 0)
    assert to_epoch_seconds(naive) == pytest.approx(naive.replace(tzinfo=timezone.utc).timestamp())
    assert to_epoch_seconds(1700.5) == 1700.5
    assert to_epoch_seconds(None) is None
    assert to_epoch_seconds(True) is None  # bool 不當數值


# ---- contained_bar_return_bps ----

def test_contained_bars_open_to_close():
    bars = [
        {"ts": 100.0, "open": 100.0, "close": 105.0},
        {"ts": 160.0, "open": 105.0, "close": 108.0},
        {"ts": 220.0, "open": 108.0, "close": 110.0},
    ]
    # 窗 [100, 280]：三根全包含；first open=100，last close=110 → 1000 bps
    assert contained_bar_return_bps(bars, 100.0, 280.0, 60.0) == pytest.approx(1000.0)


def test_straddling_entry_bar_excluded():
    bars = [
        {"ts": 100.0, "open": 100.0, "close": 105.0},
        {"ts": 160.0, "open": 105.0, "close": 108.0},
        {"ts": 220.0, "open": 108.0, "close": 110.0},
    ]
    # 窗 [130, 280]：ts=100 跨 entry（100<130）排除；first open=105(ts160)，last close=110 → ~476.19 bps
    out = contained_bar_return_bps(bars, 130.0, 280.0, 60.0)
    assert out == pytest.approx((110.0 / 105.0 - 1.0) * 10_000.0)


def test_straddling_exit_partial_bar_excluded():
    bars = [
        {"ts": 100.0, "open": 100.0, "close": 105.0},
        {"ts": 160.0, "open": 105.0, "close": 108.0},
        {"ts": 220.0, "open": 108.0, "close": 110.0},
    ]
    # 窗 [100, 250]：ts=220 的 close 在 280>250（partial）排除；last close=108(ts160)
    out = contained_bar_return_bps(bars, 100.0, 250.0, 60.0)
    assert out == pytest.approx((108.0 / 100.0 - 1.0) * 10_000.0)


def test_no_inside_bar_returns_none():
    bars = [{"ts": 100.0, "open": 100.0, "close": 105.0}]
    assert contained_bar_return_bps(bars, 100.0, 150.0, 60.0) is None  # 100+60>150


def test_bad_price_returns_none():
    bars = [{"ts": 100.0, "open": 0.0, "close": 105.0}]
    assert contained_bar_return_bps(bars, 100.0, 280.0, 60.0) is None


# ---- pit_active_symbols（survivorship 防護）----

def test_pit_active_universe_includes_delisted_excludes_future_listed():
    lifecycles = {
        "A": (50.0, None),    # listed 早、未下市 → 含
        "B": (150.0, None),   # listed 晚於 entry → 排除
        "C": (50.0, 250.0),   # delisted 250 > exit 200 → 含（窗內仍可交易）
        "D": (50.0, 180.0),   # delisted 180 <= exit 200 → 排除
        "E": (None, None),    # listed 未知 → 排除
    }
    active = set(pit_active_symbols(lifecycles, 100.0, 200.0))
    assert active == {"A", "C"}
    # 同一 universe 換更長窗 [100,300]：C 的 delisted 250<=300 → 排除
    active2 = set(pit_active_symbols(lifecycles, 100.0, 300.0))
    assert active2 == {"A"}


# ---- assemble_residual_inputs（drop 路徑 + diag）----

def _full_klines():
    syms = {f"S{i}" for i in range(10)} | {"BTCUSDT"}
    return {s: _bars(0.0, 100_000.0, open_=100.0, close=100.5) for s in syms}


def _full_lifecycles():
    syms = {f"S{i}" for i in range(10)} | {"BTCUSDT"}
    return {s: (0.0, None) for s in syms}


def test_assemble_drop_paths_and_diag():
    klines = _full_klines()
    lifecycles = _full_lifecycles()
    round_trips = [
        {"entry_ts": 1020.0, "exit_ts": 2820.0, "net_bps": 3.0},   # 有效 → aligned
        {"entry_ts": 200_000.0, "exit_ts": 201_800.0, "net_bps": 2.0},  # 超出 klines → no_btc_bar
        {"entry_ts": 1020.0, "exit_ts": 2820.0, "net_bps": 9.0},   # 與第一筆同 entry → dup
        {"entry_ts": 6000.0, "exit_ts": 5000.0, "net_bps": 1.0},   # exit<entry → bad_window
    ]
    candidate, factor, diag = assemble_residual_inputs(
        round_trips, klines, lifecycles, min_basket_symbols=8
    )
    assert diag["aligned"] == 1
    assert diag["no_btc_bar"] == 1
    assert diag["dup_entry_ts"] == 1
    assert diag["bad_window"] == 1
    assert set(candidate.keys()) == {1020.0}
    assert set(factor[1020.0].keys()) == {"btc", "market"}
    # market = 10 個 S* 等權；每個 contained 報酬皆 (100.5/100-1)*1e4 = 50 bps
    assert factor[1020.0]["market"] == pytest.approx(50.0)
    assert factor[1020.0]["btc"] == pytest.approx(50.0)


def test_assemble_thin_basket_dropped():
    klines = _full_klines()
    # 只讓 3 個 symbol 有 lifecycle → basket 成員 < min 8
    lifecycles = {"BTCUSDT": (0.0, None), "S0": (0.0, None), "S1": (0.0, None), "S2": (0.0, None)}
    round_trips = [{"entry_ts": 1020.0, "exit_ts": 2820.0, "net_bps": 3.0}]
    candidate, factor, diag = assemble_residual_inputs(
        round_trips, klines, lifecycles, min_basket_symbols=8
    )
    assert diag["aligned"] == 0
    assert diag["thin_basket"] == 1
    assert candidate == {}


def test_assemble_btc_only_skips_basket():
    # v1：required_factors=("btc",) 只需 BTC 1m，免 PIT basket，可擴展
    klines = {"BTCUSDT": _bars(0.0, 100_000.0, open_=100.0, close=100.5)}
    lifecycles = {"BTCUSDT": (0.0, None)}  # 無其他 symbol
    round_trips = [{"entry_ts": 1020.0, "exit_ts": 2820.0, "net_bps": 3.0}]
    candidate, factor, diag = assemble_residual_inputs(
        round_trips, klines, lifecycles, required_factors=("btc",), min_basket_symbols=8
    )
    assert diag["aligned"] == 1
    assert diag["thin_basket"] == 0
    assert set(factor[1020.0].keys()) == {"btc"}
    assert factor[1020.0]["btc"] == pytest.approx(50.0)


def test_build_from_data_smoke_feeds_r1():
    klines = _full_klines()
    lifecycles = _full_lifecycles()
    # 60 筆小時級 round-trip，皆有效
    round_trips = [
        {"entry_ts": 1020.0 + i * 3600.0, "exit_ts": 1020.0 + i * 3600.0 + 1800.0, "net_bps": 2.0 + (i % 4)}
        for i in range(60)
    ]
    result, diag = build_residual_report_from_data(
        round_trips,
        klines,
        lifecycles,
        n_trials=5,
        embargo_gap=3600.0,
        peer_oos_returns=None,
        min_train_observations=20,
        min_eval_observations=8,
        min_coverage=0.8,
    )
    assert diag["aligned"] >= 1
    # 餵進 R-1 並回 canonical 結果結構
    assert hasattr(result, "report") and hasattr(result, "promotion_ready")
    assert "verdict" in result.report


# ---- DB 函數（mock cursor，Mac 驗 Python 邏輯；SQL 已在 Linux 驗）----

def test_load_btc_klines_converts_and_drops_bad():
    rows = [
        {"ts": datetime(2026, 6, 5, 0, 0, tzinfo=timezone.utc), "open": 100.0, "close": 101.0},
        {"ts": datetime(2026, 6, 5, 0, 1, tzinfo=timezone.utc), "open": None, "close": 101.0},  # 壞 open → drop
    ]
    bars = load_btc_klines(
        _FakeConn(rows),
        start_ts=datetime(2026, 6, 5, tzinfo=timezone.utc),
        end_ts=datetime(2026, 6, 6, tzinfo=timezone.utc),
    )
    assert len(bars) == 1
    assert bars[0]["ts"] == pytest.approx(datetime(2026, 6, 5, 0, 0, tzinfo=timezone.utc).timestamp())
    assert bars[0]["open"] == 100.0 and bars[0]["close"] == 101.0


def test_load_round_trips_filters_strategy_and_exit(monkeypatch):
    from program_code.ml_training import realized_edge_stats as res

    entry = datetime(2026, 6, 5, 0, 0, tzinfo=timezone.utc)
    exit_ = datetime(2026, 6, 5, 0, 30, tzinfo=timezone.utc)

    def _rec(strategy, net, exit_ts):
        return res.RoundTripRecord(strategy, "BTCUSDT", 0.0, 0.0, 0.0, net, entry, exit_ts, 1000.0)

    monkeypatch.setattr(res, "_engine_mode_scope", lambda m: [m])
    monkeypatch.setattr(
        res,
        "_pair_round_trips",
        lambda fills: [
            _rec("grid_trading", 5.0, exit_),     # 命中
            _rec("other_strategy", 9.0, exit_),   # 別的策略 → 排除
            _rec("grid_trading", 3.0, None),      # 無 exit → 排除
        ],
    )

    out = load_round_trips(
        _FakeConn([]), "grid_trading", engine_mode="demo",
        since=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    assert len(out) == 1
    assert out[0]["net_bps"] == 5.0
    assert out[0]["entry_ts"] == pytest.approx(entry.timestamp())
    assert out[0]["exit_ts"] == pytest.approx(exit_.timestamp())


# ---- 非重疊 bucket 路徑（QC/MIT 2026-06-05 定稿）----

from program_code.ml_training.residual_alpha_producer_db import (  # noqa: E402
    bucket_floor,
    bucket_round_trips_by_exit,
    bucketed_btc_factor,
    build_bucketed_residual_report,
)


def test_bucket_floor_aligns_to_grid():
    assert bucket_floor(0.0, 14400.0) == 0.0
    assert bucket_floor(14399.0, 14400.0) == 0.0
    assert bucket_floor(14400.0, 14400.0) == 14400.0
    assert bucket_floor(14401.0, 14400.0) == 14400.0


def test_bucket_round_trips_by_exit_attribution_and_sum():
    rts = [
        {"entry_ts": 100.0, "exit_ts": 1000.0, "net_bps": 3.0},    # 桶 0
        {"entry_ts": 200.0, "exit_ts": 5000.0, "net_bps": 2.0},    # 桶 0
        {"entry_ts": 300.0, "exit_ts": 20000.0, "net_bps": 7.0},   # 桶 14400
        {"entry_ts": 400.0, "exit_ts": None, "net_bps": 9.0},      # 無 exit → skip
        {"entry_ts": 500.0, "exit_ts": 400.0, "net_bps": 1.0},     # exit<entry → skip
    ]
    sums, counts = bucket_round_trips_by_exit(rts, 14400.0)
    assert sums == {0.0: 5.0, 14400.0: 7.0}
    assert counts == {0.0: 2, 14400.0: 1}


def test_bucketed_btc_factor_open_to_close_floored():
    klines = [
        {"ts": 0.0, "open": 100.0, "close": 105.0},
        {"ts": 14400.0, "open": 105.0, "close": 110.0},
    ]
    factor = bucketed_btc_factor(klines, 14400.0)
    assert set(factor.keys()) == {0.0, 14400.0}
    assert factor[0.0]["btc"] == pytest.approx((105.0 / 100.0 - 1.0) * 10_000.0)
    assert factor[14400.0]["btc"] == pytest.approx((110.0 / 105.0 - 1.0) * 10_000.0)


def test_build_bucketed_smoke_feeds_r1():
    bucket = 14400.0
    rts = [
        {"entry_ts": i * bucket + 100.0, "exit_ts": i * bucket + 200.0, "net_bps": 2.0 + (i % 4)}
        for i in range(60)
    ]
    klines = [{"ts": i * bucket, "open": 100.0, "close": 100.5} for i in range(60)]
    result, diag = build_bucketed_residual_report(
        rts, klines, n_trials=5, embargo_buckets=1,
        min_train_observations=20, min_eval_observations=8, min_coverage=0.8,
    )
    assert diag["aligned_buckets"] == 60.0
    assert diag["mean_trips_per_bucket"] == 1.0
    assert hasattr(result, "report") and hasattr(result, "promotion_ready")
    assert "verdict" in result.report
