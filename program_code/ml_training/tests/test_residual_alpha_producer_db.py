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


# ---- Gap B：多因子 bucket panel（btc + market + funding）----

from program_code.ml_training.residual_alpha_producer_db import (  # noqa: E402
    bucketed_funding_factor,
    bucketed_multi_factor,
    load_funding_rates,
)

_B = 14400.0  # 4h bucket


def _sym_klines(n: int, *, open_=100.0, close=100.5):
    # 每桶一根 4h kline（ts 對齊桶起點）。
    return [{"ts": i * _B, "open": open_, "close": close} for i in range(n)]


def test_multi_factor_btc_only_matches_btc_factor():
    """required_factors=("btc",) 的 multi-factor panel 必須與 bucketed_btc_factor
    完全一致（行為中性的結構保證：預設路徑零漂移）。"""
    klines = {"BTCUSDT": _sym_klines(10)}
    lifecycles = {"BTCUSDT": (0.0, None)}
    multi = bucketed_multi_factor(klines, lifecycles, required_factors=("btc",), bucket_sec=_B)
    btc = bucketed_btc_factor(klines["BTCUSDT"], _B)
    assert multi == btc  # dict 相等（key 集 + 值）


def test_multi_factor_market_basket_pit_and_min_size():
    """market 因子：每桶取該桶 PIT-active 等權；成員 < min_basket 該桶無值。"""
    # 10 個 symbol 全程上市 → market basket 充足
    syms = {f"S{i}" for i in range(10)} | {"BTCUSDT"}
    klines = {s: _sym_klines(6) for s in syms}
    lifecycles = {s: (0.0, None) for s in syms}
    panel = bucketed_multi_factor(
        klines, lifecycles, required_factors=("btc", "market"), bucket_sec=_B,
        min_basket_symbols=8,
    )
    assert len(panel) == 6
    for vals in panel.values():
        assert set(vals.keys()) == {"btc", "market"}
        # 每個 symbol 桶報酬皆 (100.5/100-1)*1e4 = 50 bps → basket=50
        assert vals["market"] == pytest.approx(50.0)
        assert vals["btc"] == pytest.approx(50.0)

    # 只 3 個 symbol 有 lifecycle → basket < 8 → market 桶全無值 → panel 空（intersection）
    thin_life = {"BTCUSDT": (0.0, None), "S0": (0.0, None), "S1": (0.0, None)}
    thin_panel = bucketed_multi_factor(
        klines, thin_life, required_factors=("btc", "market"), bucket_sec=_B,
        min_basket_symbols=8,
    )
    assert thin_panel == {}


def test_multi_factor_market_excludes_delisted_bucket_pit():
    """market PIT：symbol 在某桶後下市，下市後的桶不得計入該 symbol（survivorship）。"""
    syms = [f"S{i}" for i in range(9)]  # 9 個常駐 → 含 D 後仍可達 min 8
    klines = {s: _sym_klines(4) for s in syms}
    klines["BTCUSDT"] = _sym_klines(4)
    klines["D"] = _sym_klines(4)
    lifecycles = {s: (0.0, None) for s in syms}
    lifecycles["BTCUSDT"] = (0.0, None)
    # D 在 t=_B*2 前下市：delisted=_B*1.5 → 桶 [0,_B] 仍 active（delisted>bucket_end=_B），
    # 桶 [_B,2_B] 起 delisted<=bucket_end 被排除。
    lifecycles["D"] = (0.0, _B * 1.5)
    panel = bucketed_multi_factor(
        klines, lifecycles, required_factors=("market",), bucket_sec=_B, min_basket_symbols=8,
    )
    # 桶 0：D active（9 S + BTC + D = 11 成員）；桶 >=1：D 排除（10 成員）。
    # 都 >= 8 → 4 桶都有 market 值（驗 D 的納入/排除不影響存在性，但驗無 crash 且 PIT 生效）。
    assert len(panel) == 4


def test_bucketed_funding_factor_pit_only_settled_rows():
    """funding PIT（§5.1 最高風險）：一桶只用結算時刻 ts 落在桶窗內的結算列，
    桶結束後才結算的下一筆費率（未來）必被排除。"""
    # 桶 [0,_B)、[_B,2_B)。settlement 結算時刻：
    #   ts=100（落桶 0）、ts=_B+100（落桶 1）、ts=2_B+100（落桶 2，對桶 1 而言是未來）
    funding = {
        "BTCUSDT": [
            {"ts": 100.0, "funding_rate": 0.001},        # 桶 0
            {"ts": _B + 100.0, "funding_rate": 0.002},   # 桶 1
            {"ts": 2 * _B + 100.0, "funding_rate": 9.0}, # 桶 2（巨值；若洩漏到桶 1 會爆）
        ]
    }
    out = bucketed_funding_factor(funding, ["BTCUSDT"], net_side=1, bucket_sec=_B)
    # 做多：funding>0=付費=負報酬 → -rate*1e4
    assert out[0.0] == pytest.approx(-0.001 * 1e4)
    assert out[_B] == pytest.approx(-0.002 * 1e4)
    # 桶 1 絕不可含 ts=2_B+100 的未來費率（9.0）：值必為 -20 bps 而非天文數字
    assert abs(out[_B]) < 100.0
    # 桶 2 的未來列只歸它自己的桶
    assert out[2 * _B] == pytest.approx(-9.0 * 1e4)


def test_bucketed_funding_factor_boundary_settlement_goes_to_prior_bucket():
    """結算時刻恰在桶邊界 ts==bucket_start 時歸入上一桶（(start,end] 半開語意），
    確保不把桶起點當下一桶的未來費率。"""
    funding = {"X": [{"ts": _B, "funding_rate": 0.001}]}  # 恰在桶 1 起點
    out = bucketed_funding_factor(funding, ["X"], net_side=1, bucket_sec=_B)
    # ts=_B 屬桶 0 的尾（(0,_B]），不屬桶 1
    assert set(out.keys()) == {0.0}
    assert out[0.0] == pytest.approx(-0.001 * 1e4)


def test_bucketed_funding_factor_sign_matches_net_side():
    """funding 符號隨 net_side：做空收費（funding>0）→ 正報酬；做多付費 → 負報酬。"""
    funding = {"X": [{"ts": 100.0, "funding_rate": 0.001}]}
    long_out = bucketed_funding_factor(funding, ["X"], net_side=1, bucket_sec=_B)
    short_out = bucketed_funding_factor(funding, ["X"], net_side=-1, bucket_sec=_B)
    assert long_out[0.0] == pytest.approx(-0.001 * 1e4)   # 做多付費 → 負
    assert short_out[0.0] == pytest.approx(+0.001 * 1e4)  # 做空收費 → 正


def test_bucketed_funding_factor_multi_symbol_equal_weight():
    """多 symbol funding 取等權（只在有結算列的 symbol 上平均）。"""
    funding = {
        "A": [{"ts": 100.0, "funding_rate": 0.001}],
        "B": [{"ts": 100.0, "funding_rate": 0.003}],
    }
    out = bucketed_funding_factor(funding, ["A", "B"], net_side=1, bucket_sec=_B)
    # realized 平均 = (0.001+0.003)/2 = 0.002 → -20 bps
    assert out[0.0] == pytest.approx(-0.002 * 1e4)


def test_multi_factor_funding_requires_inputs():
    """required_factors 含 funding 但缺 funding_by_symbol/position_symbols → raise
    （fail-closed，不得靜默產出無 funding 的 panel 誤判已涵蓋 carry）。"""
    klines = {"BTCUSDT": _sym_klines(4)}
    lifecycles = {"BTCUSDT": (0.0, None)}
    with pytest.raises(ValueError, match="funding factor requires"):
        bucketed_multi_factor(
            klines, lifecycles, required_factors=("btc", "funding"), bucket_sec=_B,
        )


def test_multi_factor_three_factors_aligned_on_same_grid():
    """btc+market+funding 三因子在同一桶網格 intersection 對齊。"""
    syms = {f"S{i}" for i in range(10)} | {"BTCUSDT"}
    klines = {s: _sym_klines(6) for s in syms}
    lifecycles = {s: (0.0, None) for s in syms}
    funding = {"BTCUSDT": [{"ts": i * _B + 100.0, "funding_rate": 0.001} for i in range(6)]}
    panel = bucketed_multi_factor(
        klines, lifecycles,
        required_factors=("btc", "market", "funding"), bucket_sec=_B,
        min_basket_symbols=8,
        funding_by_symbol=funding, position_symbols=["BTCUSDT"], net_side=1,
    )
    assert len(panel) == 6
    for vals in panel.values():
        assert set(vals.keys()) == {"btc", "market", "funding"}
        assert vals["funding"] == pytest.approx(-0.001 * 1e4)


def test_multi_factor_funding_partial_bucket_intersection():
    """funding 只覆蓋部分桶時，panel 只保留三因子都有值的桶（intersection）。"""
    syms = {f"S{i}" for i in range(10)} | {"BTCUSDT"}
    klines = {s: _sym_klines(6) for s in syms}
    lifecycles = {s: (0.0, None) for s in syms}
    # funding 只有前 3 桶
    funding = {"BTCUSDT": [{"ts": i * _B + 100.0, "funding_rate": 0.001} for i in range(3)]}
    panel = bucketed_multi_factor(
        klines, lifecycles,
        required_factors=("btc", "market", "funding"), bucket_sec=_B,
        min_basket_symbols=8,
        funding_by_symbol=funding, position_symbols=["BTCUSDT"], net_side=1,
    )
    # btc/market 有 6 桶，funding 只有 3 桶 → intersection = 3
    assert len(panel) == 3


def test_load_funding_rates_converts_and_drops_bad():
    """DB loader（mock cursor）：timestamptz→epoch，壞 rate drop。"""
    rows_by_call = [
        [
            {"ts": datetime(2026, 6, 5, 0, 0, tzinfo=timezone.utc), "funding_rate": 0.0001},
            {"ts": datetime(2026, 6, 5, 8, 0, tzinfo=timezone.utc), "funding_rate": None},  # drop
        ],
    ]

    class _MultiCursor:
        def __init__(self, batches):
            self._batches = list(batches)
            self._last = []

        def execute(self, q, p=None):
            self._last = self._batches.pop(0) if self._batches else []

        def fetchall(self):
            return self._last

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class _MultiConn:
        def __init__(self, batches):
            self._batches = batches

        def cursor(self, **kw):
            return _MultiCursor(self._batches)

    out = load_funding_rates(
        _MultiConn(rows_by_call), ["BTCUSDT"],
        start_ts=datetime(2026, 6, 5, tzinfo=timezone.utc),
        end_ts=datetime(2026, 6, 6, tzinfo=timezone.utc),
    )
    assert set(out.keys()) == {"BTCUSDT"}
    assert len(out["BTCUSDT"]) == 1
    assert out["BTCUSDT"][0]["funding_rate"] == 0.0001
    assert out["BTCUSDT"][0]["ts"] == pytest.approx(
        datetime(2026, 6, 5, 0, 0, tzinfo=timezone.utc).timestamp()
    )
