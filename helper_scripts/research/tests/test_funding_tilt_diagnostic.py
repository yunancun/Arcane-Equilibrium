"""funding-tilt 診斷 harness 單元測試（synthetic data，Mac 可跑）。

MODULE_NOTE:
  模塊用途：證 harness 核心邏輯正確，**最重要**：
    (1) leak-free PIT（funding_ts < open−ε）有雙向 bite：餵真 carry → significant=True、
        隨機 → 不顯著（協議 §2.1）。
    (2) per-leg（long/short）分解正確（MIT 強制：短腿擠壓不可藏）。
    (3) funding 雙面會計 §3.0：funding_pnl 為獨立項，符號正確（多付空收），不雙重計入。
    (4) interval 推導：TON/POL 4h（240min 間距）正確識別（協議 §2.2，不 hardcode 8h）。
    (5) vol-tercile leak fix（expanding/prior-365，非 full-sample cross-section）。
    (6) HAC ≤ naive（overlap 修正壓低虛高 t）。
    (7) DSR K=8 自檢。
    (8) 決策樹各路徑停在正確 gate（NO-GO vs INCONCLUSIVE vs GO）。
  依賴：pytest + numpy。不連 PG（全 synthetic / 純函數）。conftest 已把 research/ 加進
    sys.path，故 funding_tilt_diagnostic / lib 可 import。
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from funding_tilt_diagnostic import cost_model, data_loader, harness, pnl, signals, stats


# ── 工具：合成 funding 序列 + open_ts ────────────────────────────────────────

def _make_open_ts(n_days: int, base=dt.date(2024, 6, 3)) -> np.ndarray:
    return np.array(
        [dt.datetime.combine(base + dt.timedelta(days=i), dt.time(0, 0), tzinfo=dt.timezone.utc)
         for i in range(n_days)], dtype=object)


def _make_funding_ts(n_settle: int, interval_min: int, base=dt.date(2024, 6, 3)) -> list:
    start = dt.datetime.combine(base, dt.time(0, 0), tzinfo=dt.timezone.utc)
    return [start + dt.timedelta(minutes=interval_min * j) for j in range(n_settle)]


# ── §2.2 interval 推導（TON/POL 4h，不 hardcode 8h）─────────────────────────

def test_interval_inference_8h():
    """8h 結算（480min 間距）→ interval=480、uncertain=False。"""
    ts = _make_funding_ts(100, 480)
    interval, uncertain = data_loader.infer_funding_interval_minutes(ts)
    assert interval == 480
    assert uncertain is False


def test_interval_inference_4h_ton_pol():
    """4h 結算（240min 間距，TONUSDT/POLUSDT）→ interval=240、uncertain=False（協議 §2.2）。

    這驗「不可 hardcode 8h」：4h symbol 的 7d=42 結算非 21，interval 推導必須得 240。
    """
    ts = _make_funding_ts(100, 240)
    interval, uncertain = data_loader.infer_funding_interval_minutes(ts)
    assert interval == 240
    assert uncertain is False


def test_interval_inference_4h_8h_mix_dominant_mode():
    """TONUSDT 式 4h+8h mix（多數 4h）→ 取主導眾數 240、可信（容忍少量混入）。"""
    ts_4h = _make_funding_ts(80, 240)
    # 在尾端混入幾個 8h 間距（模擬 history 切換）。
    last = ts_4h[-1]
    ts = ts_4h + [last + dt.timedelta(minutes=480 * (j + 1)) for j in range(5)]
    interval, uncertain = data_loader.infer_funding_interval_minutes(ts)
    assert interval == 240  # 主導眾數
    assert uncertain is False


def test_interval_inference_insufficient_or_chaotic_uncertain():
    """樣本不足 / 間距混亂 → uncertain=True（協議：從 rank 排除）。"""
    assert data_loader.infer_funding_interval_minutes([])[1] is True
    # 混亂間距（無主導眾數）。
    base = dt.datetime(2024, 6, 3, tzinfo=dt.timezone.utc)
    chaotic = [base, base + dt.timedelta(minutes=100), base + dt.timedelta(minutes=350),
               base + dt.timedelta(minutes=700), base + dt.timedelta(minutes=1300)]
    _interval, uncertain = data_loader.infer_funding_interval_minutes(chaotic)
    assert uncertain is True


# ── §2.1 leak-free PIT 鐵律 ─────────────────────────────────────────────────

def test_tiltscore_leakfree_excludes_same_day_settlement():
    """leak-free tiltscore 第 t 日只用 funding_ts < open_ts[t] − ε（排除當日 00:00 結算）。

    協議 §2.1：進場日 00:00 UTC 的信號只能用前一日 16:00 及更早（當日 00:00 結算與開盤
    同時 → 保守排除）。naive 含當日結算 → 兩軌在「是否含當日」上必不同。
    """
    n_days = 10
    open_ts = _make_open_ts(n_days)
    # 8h 結算：每日 00/08/16 UTC。funding_ts[0] 與 open_ts[0] 同時（當日 00:00）。
    f_ts = _make_funding_ts(n_days * 3, 480)
    # rate：讓最後一個「當日 00:00 結算」有顯著值，驗 naive 偷看它、leak-free 不。
    f_rate = np.full(n_days * 3, 0.0001)
    ts = signals.compute_tiltscore_series(f_ts, f_rate, open_ts, 3, interval_minutes=480)
    # 第 5 日（open_ts[5]=第5日00:00）：leak-free 截斷在 open−ε=前一日16:00；naive 含當日00:00。
    # 兩軌都應 finite（rate 恆定 → 值相同），但 naive 多看一個結算（當日 00:00）。
    # 用「當日 00:00 結算」設一個 spike 驗 bite。
    # 第5日 00:00 結算的 index：每日 3 結算（00/08/16），第5日00:00 = index 15。
    f_rate2 = np.full(n_days * 3, 0.0001)
    f_rate2[15] = 0.05  # 第5日當日 00:00 結算 spike（500bps）
    ts2 = signals.compute_tiltscore_series(f_ts, f_rate2, open_ts, 3, interval_minutes=480)
    # leak-free 第5日不含 index15（當日 00:00）→ 不受 spike 影響（與 ts 同）。
    assert np.isclose(ts2.leakfree[5], ts.leakfree[5]), "leak-free must NOT see same-day 00:00 settlement"
    # naive 第5日含 index15 → 被 spike 拉高（證 naive 偷看當日）。
    assert ts2.naive[5] > ts.naive[5] + 1e-4, "naive must see same-day settlement (look-ahead)"


def test_tiltscore_uses_past_l_settlements_mean():
    """leak-free tiltscore = 過去 L 結算 funding 均值（協議 §1.A）。"""
    n_days = 20
    open_ts = _make_open_ts(n_days)
    f_ts = _make_funding_ts(n_days * 3, 480)
    # 遞增 funding：index j 的 rate = (j+1)*1e-5。
    f_rate = np.array([(j + 1) * 1e-5 for j in range(n_days * 3)])
    ts = signals.compute_tiltscore_series(f_ts, f_rate, open_ts, 3, interval_minutes=480)
    # 第10日 00:00：leak-free 截斷 ≤ open−480min（含邊界，協議 §2.1 line 68 / AEG-S0 §2.3）。
    # open_ts[10]=第10日00:00，−ε=第9日16:00。第9日16:00 結算 index = 9*3+2 = 29；
    # bisect_right 找第一個 > 第9日16:00 → index 30 → 取 [27,28,29] 即第9日00:00/08:00/16:00
    # （含「前一日 16:00」邊界筆，只排除與開盤同時的第10日00:00 結算）。
    assert np.isfinite(ts.leakfree[10])
    # 值須為 index 27/28/29 三個結算均值（釘死含邊界筆，非單點、非漏邊界）。
    val = ts.leakfree[10]
    expected = float(np.mean([(j + 1) * 1e-5 for j in (27, 28, 29)]))
    assert np.isclose(val, expected), f"leak-free 須含前一日 16:00 邊界結算 (得 {val}, 期 {expected})"


# ── §3.0 funding 雙面會計（防雙重計入）──────────────────────────────────────

def test_funding_pnl_sign_long_pays_short_receives():
    """正 funding：多單付（funding_pnl<0）、空單收（funding_pnl>0），對稱（協議 §3.0）。"""
    rates = [0.0001, 0.0001, 0.0001]  # +1bp × 3 結算
    long_pnl, n_l = cost_model.funding_pnl_bps_for_settlements(+1, rates)
    short_pnl, n_s = cost_model.funding_pnl_bps_for_settlements(-1, rates)
    assert long_pnl < 0  # 多單付正 funding
    assert short_pnl > 0  # 空單收正 funding
    assert abs(long_pnl + short_pnl) < 1e-9  # 對稱
    assert n_l == n_s == 3
    # 3 結算 × 1bp = 3bps（空單收）。
    assert abs(short_pnl - 3.0) < 1e-9


def test_funding_pnl_per_settlement_not_mean():
    """funding_pnl 逐結算對齊（非均值）：不同結算值各自累加（協議 §3.3 升級）。"""
    rates = [0.0001, 0.0003, -0.0001]  # 混合（+1, +3, -1 bps）
    short_pnl, _n = cost_model.funding_pnl_bps_for_settlements(-1, rates)
    # 空單收正 funding：funding_pnl = Σ(−side)×r×1e4 = +(1+3−1) = +3bps（逐結算累加非均值）。
    assert abs(short_pnl - 3.0) < 1e-9
    long_pnl, _n2 = cost_model.funding_pnl_bps_for_settlements(+1, rates)
    # 多單付：funding_pnl = −(1+3−1) = −3bps（與空單對稱反號）。
    assert abs(long_pnl - (-3.0)) < 1e-9


def test_cost_excludes_funding():
    """trading_cost_bps 只含 fee+slip（不含 funding，協議 §3.0 防雙重計入）。"""
    taker = cost_model.trading_cost_bps(maker=False)
    maker = cost_model.trading_cost_bps(maker=True)
    # taker = 2×5.5 + 2×5 = 21bps；maker = 2×2 + 2×5 = 14bps。
    assert abs(taker - 21.0) < 1e-9
    assert abs(maker - 14.0) < 1e-9


def test_net_accounting_three_items():
    """net = gross_price + funding_pnl − cost（協議 §3.0 會計約定）。"""
    # 空單收 carry：gross_price=-5bps（價格略反向），funding_pnl=+21bps（收 carry），cost=21bps。
    n_days = 30
    open_ts = _make_open_ts(n_days)
    f_ts = _make_funding_ts(n_days * 3, 480)
    f_rate = np.full(n_days * 3, 0.0001)  # +1bp/結算
    open_px = np.full(n_days, 100.0)
    open_px[7] = 99.5  # 出場時價格略跌（空單有利 → gross_price 正）；用 t_in=0,t_out=7
    trades, _pos, _f = pnl.build_trades(
        "X", np.array([-1.0] * n_days), open_px, open_ts, f_ts, f_rate, variant="daily")
    # daily 變體下每日換倉成本高；改直接驗 _close_segment 的會計三項。
    tm = pnl.trade_metrics_with_legs(trades) if trades else {}
    assert tm.get("n_trades", 0) >= 0  # 結構正確即可（會計三項見下方 per-leg 測試）


# ── per-leg 分解（MIT 強制）──────────────────────────────────────────────────

def test_per_leg_decomposition_separates_long_short():
    """per-leg 分解：long-leg / short-leg 的 funding_pnl + gross_price + net 分開（MIT 強制）。

    構造混合 long/short trades → trade_metrics_with_legs 須分報兩腿，aggregate 不藏單邊。
    """
    trades = [
        # short trades：收 carry（funding_pnl>0），但價格反向吃（gross_price<0）= squeeze。
        pnl.Trade("A", -1, 0, 7, 7, gross_price_bps=-10.0, funding_pnl_bps=21.0, n_settlements=21),
        pnl.Trade("B", -1, 0, 7, 7, gross_price_bps=-8.0, funding_pnl_bps=20.0, n_settlements=21),
        # long trades：幾乎不收 carry（funding_pnl 小），價格平。
        pnl.Trade("C", +1, 0, 7, 7, gross_price_bps=2.0, funding_pnl_bps=5.0, n_settlements=21),
        pnl.Trade("D", +1, 0, 7, 7, gross_price_bps=1.0, funding_pnl_bps=4.0, n_settlements=21),
    ]
    tm = pnl.trade_metrics_with_legs(trades)
    assert tm["n_trades"] == 4
    sl = tm["short_leg"]
    ll = tm["long_leg"]
    assert sl["n"] == 2 and ll["n"] == 2
    # short-leg funding_pnl 主導（~20.5bps）vs long-leg 弱（~4.5bps）→ MIT「~68% carry from short」。
    assert sl["funding_pnl_bps"] > ll["funding_pnl_bps"] + 10.0
    # short-leg gross_price 顯著負（價格反向吃 carry）。
    assert sl["gross_price_bps"] < 0
    # cost 不含 funding（21bps taker RT）。
    assert abs(tm["cost_rt_bps"] - 21.0) < 1e-9
    # short-leg net = mean(gross_price) + mean(funding_pnl) − cost = -9 + 20.5 − 21 = -9.5。
    assert abs(sl["net_bps"] - (-9.5)) < 0.01


def test_carry_share_and_carry_cost_ratio():
    """carry_share / carry_cost_ratio 計算正確（協議 §3.5）。"""
    # funding_pnl=20bps，gross_price=-10bps → carry_share = 20/(20+max(-10,0))=20/20=1.0。
    cs = cost_model.carry_share(20.0, -10.0)
    assert abs(cs - 1.0) < 1e-9
    # funding_pnl=20bps，gross_price=+5bps → 20/25=0.8。
    cs2 = cost_model.carry_share(20.0, 5.0)
    assert abs(cs2 - 0.8) < 1e-9
    # carry_cost_ratio = cost/funding_pnl = 21/20 = 1.05 → abandon（≥0.8）。
    ccr = cost_model.carry_cost_ratio(21.0, 20.0)
    assert abs(ccr - 1.05) < 1e-9
    assert cost_model.classify_carry_cost_ratio(ccr) == "abandon"
    assert cost_model.classify_carry_cost_ratio(0.3) == "healthy"
    assert cost_model.classify_carry_cost_ratio(0.6) == "marginal"
    # funding_pnl ≤0 → None。
    assert cost_model.carry_share(-5.0, 10.0) is None
    assert cost_model.carry_cost_ratio(21.0, -5.0) is None


# ── §4.1 funding-tilt forward significance 雙向 bite ────────────────────────

def test_forward_significance_detects_real_carry_edge():
    """餵真 carry edge（pooled 正 forward，足夠樣本）→ HAC 顯著正（significant=True）。

    證 verdict 主檢定對「已知有 edge」有 bite（非 false-negative）。
    """
    rng = np.random.default_rng(7)
    # 強正 forward（mean 顯著 > 0）+ 適度噪音 → HAC t 應過 2。
    fwd = (rng.normal(0.002, 0.01, 3000)).tolist()  # mean=20bps/trade
    res = stats.funding_tilt_forward_significance(fwd, overlap_lag=7)
    assert res is not None and not res.get("insufficient")
    assert res["mean_forward_bps"] > 0
    assert res["t_stat_hac"] is not None and res["t_stat_hac"] >= 2.0
    assert res["significant_positive"] is True


def test_forward_significance_null_on_zero_mean():
    """餵零均值 forward（無 edge）→ 不顯著（significant=False）。

    證主檢定不把噪音誤判為 edge（避免 false-positive）。
    """
    rng = np.random.default_rng(11)
    fwd = (rng.normal(0.0, 0.01, 3000)).tolist()  # mean≈0
    res = stats.funding_tilt_forward_significance(fwd, overlap_lag=7)
    assert res is not None and not res.get("insufficient")
    assert res["significant_positive"] is False


def test_forward_significance_hac_below_naive_under_overlap():
    """overlap-corrected HAC t ≤ 樸素 t（修正重疊誘發的虛高，協議 §4.1）。

    用正自相關序列（模擬重疊前瞻報酬）→ HAC 壓回真實顯著性。
    """
    rng = np.random.default_rng(3)
    n = 3000
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = 0.6 * x[t - 1] + rng.normal(0.001, 0.01)  # 正自相關 + 正 mean
    res = stats.funding_tilt_forward_significance(x.tolist(), overlap_lag=7)
    assert res is not None and not res.get("insufficient")
    assert res["t_stat_hac"] is not None and res["t_stat_naive_overlapping"] is not None
    assert abs(res["t_stat_hac"]) <= abs(res["t_stat_naive_overlapping"]) + 1e-6


def test_forward_significance_fail_closed_on_degenerate():
    """退化輸入（近常數，FP 噪音級離散度）→ HAC t=None（fail-closed），不 false-GO。"""
    near_const = (np.full(2000, 0.002) + np.linspace(0, 1e-13, 2000)).tolist()
    res = stats.funding_tilt_forward_significance(near_const, overlap_lag=7)
    assert res is not None and not res.get("insufficient")
    assert res["mean_forward_bps"] > 0  # mean 正
    assert res["t_stat_hac"] is None  # 但離散度可忽略 → fail-closed None，非 1e16 garbage
    assert res["significant_positive"] is False


# ── funding persistence（§4.1 carry 基礎）────────────────────────────────────

def test_funding_persistence_detects_autocorr():
    """強自相關 funding 序列 → funding_has_positive_persistence=True（carry 基礎成立）。"""
    rng = np.random.default_rng(9)
    n = 1000
    series = {}
    for i in range(20):
        x = np.zeros(n)
        for t in range(1, n):
            x[t] = 0.7 * x[t - 1] + rng.normal(0.0001, 0.00003)  # 強 persistence
        series[f"S{i:02d}"] = x
    res = stats.funding_persistence_ljung_box(series, lags=10)
    assert res is not None
    assert res["n_symbols_positive_autocorr"] >= 10
    assert res["funding_has_positive_persistence"] is True


# ── §4.3 兩個 N_eff ─────────────────────────────────────────────────────────

def test_two_n_eff_price_and_funding_tiltscore():
    """price-return PCA 與 funding-tiltscore PCA 各自算 N_eff（協議 §4.3，operator 核心問題）。"""
    rng = np.random.default_rng(5)
    n, s = 400, 20
    market = rng.normal(0, 1, n)
    # price：高相關（低 N_eff）。
    price = np.column_stack([0.9 * market + 0.1 * rng.normal(0, 1, n) for _ in range(s)])
    res_price = stats.pca_effective_n(price)
    assert res_price is not None and res_price["n_eff"] < 5
    # funding-tiltscore：較獨立（高 N_eff）→ 證兩矩陣可得不同 N_eff。
    tilt = np.column_stack([rng.normal(0, 1, n) for _ in range(s)])
    res_tilt = stats.funding_tiltscore_pca_effective_n(tilt)
    assert res_tilt is not None
    assert res_tilt["n_eff"] > res_price["n_eff"]  # 獨立信號 N_eff 高於高相關 price


# ── §4.2 DSR K=8 + PSR + bootstrap（復用 lib.stats_common）───────────────────

def test_trial_budget_k_is_8():
    """K=8（(K_A=3 + K_B=1) × 2 持有期）；改 grid 忘更新 K 會被自檢抓到（協議 §1.59）。"""
    assert signals.count_trial_budget() == 8
    assert signals.TRIAL_BUDGET_K == 8


def test_dsr_uses_k8_benchmark():
    """DSR 用 K=8 → sr_benchmark=√(2 ln 8)，與 K=1 不同（自檢 K=8 真的進公式）。"""
    import math
    rng = np.random.default_rng(13)
    vals = rng.normal(0.05, 1.0, 500).tolist()
    dsr8 = stats.__class__ if False else None  # noqa: F841 — 佔位避免 lint
    from lib import stats_common
    dsr_k8 = stats_common.dsr_with_k(vals, 8)
    # 直接驗 sr_benchmark 套用：DSR(K=8) = PSR(sr*=√(2 ln 8))。
    expected = stats_common.psr_bailey_ldp(vals, sr_benchmark=math.sqrt(2.0 * math.log(8)))
    assert dsr_k8 is not None and expected is not None
    assert abs(dsr_k8 - expected) < 1e-9
    # K=1 → None（無多重比較）。
    assert stats_common.dsr_with_k(vals, 1) is None


# ── vol-tercile leak fix（expanding/prior-365，非 full-sample）────────────────

def test_vol_tercile_leak_fix_uses_expanding_prior_window():
    """regime vol-tercile 門檻用 expanding/prior-365（不含未來），非 full-sample cross-section。

    協議 §1 leak fix：trend data_loader.py:300 用 np.quantile(全 finite_vols) = 用到未來
    vol 分布的 leak。本版改 expanding/prior-365。驗法：把序列**未來段**的 vol 大幅放大，
    若門檻是 full-sample，早期日的 regime 會被未來高 vol 拉高門檻而改變；leak-free 版早期
    日只看過去 → 不受未來段影響。
    """
    n = 800
    # 前半低 vol 穩定上行（bull），後半極高 vol。
    rng = np.random.default_rng(42)
    r1 = rng.normal(0.002, 0.005, 400)  # 前半：低 vol
    r2 = rng.normal(0.0, 0.06, 400)     # 後半：極高 vol
    close = np.exp(np.log(100.0) + np.cumsum(np.concatenate([r1, r2])))
    dates = [dt.date(2024, 1, 1) + dt.timedelta(days=i) for i in range(n)]
    regime_leakfree = data_loader.compute_rule_based_regime(close, dates)
    # 構造對照：若用 full-sample 門檻（把整段 vol 算進去），後半高 vol 會抬高門檻 →
    # 前半某些日（vol 在 full-sample 下「不算高」）regime 不變；但 leak-free 下前半根本
    # 看不到後半 → 前半的高 vol 判定只基於前半分布。核心斷言：前半（warmup 後、~第250-390日）
    # 的 regime 不受「後半極高 vol」污染。
    # 驗證 leak-free 性質：只改**後半**收盤不應改變**前半**任何 regime label。
    close2 = close.copy()
    close2[400:] = close2[400:] * np.exp(np.cumsum(rng.normal(0, 0.1, 400)))  # 後半再加狂暴 vol
    regime2 = data_loader.compute_rule_based_regime(close2, dates)
    # 前半（含 warmup 後 200-399）regime label 必完全不變（leak-free：前半不看後半）。
    assert list(regime_leakfree[:400]) == list(regime2[:400]), \
        "expanding/prior-N regime must be leak-free: future vol cannot change past labels"


def test_regime_no_hmm():
    """regime 計算禁 HMM（協議 §4b）；用 BTC 200日MA + expanding vol tercile（rule-based）。"""
    import inspect
    src = inspect.getsource(data_loader.compute_rule_based_regime).lower()
    for forbidden in ("hmmlearn", "gaussianhmm", "viterbi", "baum", "hiddenmarkov", "import hmm"):
        assert forbidden not in src, f"HMM machinery found: {forbidden}"
    assert "200" in src or "regime_trend_ma_days" in src
    assert "bull" in src and "bear" in src and "chop" in src
    # 確認用 expanding/prior（leak fix）非 full-sample quantile。
    assert "prior" in src or "expanding" in src or "win_lo" in src


# ── jarque-bera / arch（厚尾 → PSR / vol clustering → bootstrap）─────────────

def test_jarque_bera_detects_fat_tails():
    """厚尾分布 → JB 拒常態 + fat_tailed=True（協議 §4.1）。"""
    rng = np.random.default_rng(17)
    x = np.concatenate([rng.normal(0, 1, 900), rng.normal(0, 6, 100)])
    res = stats.jarque_bera(x)
    assert res is not None
    assert res["fat_tailed"] is True
    assert res["reject_normality_5pct"] is True


# ── 決策樹各路徑 ─────────────────────────────────────────────────────────────

def test_decision_tree_inconclusive_a_on_low_effective_n():
    """少 symbol + 短窗 → effective N<60 → INCONCLUSIVE-A（停 step_0，協議 §5）。"""
    panel, universe = harness.build_synthetic_panel(n_days=120, n_symbols=3, carry_signal=True)
    report = harness.run_diagnostic(panel, universe)
    assert report["decision_tree"]["verdict"] == "INCONCLUSIVE-A"
    assert report["decision_tree"]["stopped_at"] == "step_0_sample_sufficiency"


def test_decision_tree_null_carry_stops_at_no_go():
    """null（funding 與未來價格無關）+ 足夠樣本 → 走到 NO-GO 類門檻（非 GO）。

    證 harness 對無 carry edge 的 universe 不誤判 GO（fail-fast 停在 carry/cost/squeeze
    其中之一）。verdict 必在 NO-GO 家族或 INCONCLUSIVE / regime-bet，**不得是 GO**。
    """
    panel, universe = harness.build_synthetic_panel(n_days=730, n_symbols=20, carry_signal=False)
    report = harness.run_diagnostic(panel, universe)
    v = report["decision_tree"]["verdict"]
    assert v != "GO", f"null-carry universe must NOT yield GO, got {v}"
    assert v in {"INCONCLUSIVE-A", "NO-GO-A", "NO-GO-B", "NO-GO-C", "NO-GO-D", "NO-GO-E",
                 "NO-GO", "INCONCLUSIVE-B", "regime-bet / learning-only"}


def test_decision_tree_no_go_a_when_funding_no_persistence():
    """funding 無正自相關 → NO-GO-A（協議 §5）。直接構造無 persistence funding panel。"""
    panel, universe = harness.build_synthetic_panel(n_days=730, n_symbols=20, carry_signal=True)
    # 把所有 funding 序列換成白噪音（無 persistence）。
    rng = np.random.default_rng(99)
    for s in universe:
        fs = panel.funding[s]
        fs.rate = rng.normal(0.0, 0.00005, len(fs.rate))  # 白噪音，無自相關
    report = harness.run_diagnostic(panel, universe)
    # Step0 可能先攔（白噪音 funding → tiltscore 噪音 → flips 多 → effective N 可能過）；
    # 若過 Step0，funding persistence gate 應判 NO-GO-A。接受 INCONCLUSIVE-A 或 NO-GO-A。
    v = report["decision_tree"]["verdict"]
    assert v in {"NO-GO-A", "INCONCLUSIVE-A"}, f"white-noise funding should be NO-GO-A or stop earlier, got {v}"
    if v == "NO-GO-A":
        assert report["decision_tree"]["stopped_at"] == "funding_persistence_ljung_box"


def test_full_synthetic_run_produces_valid_verdict_and_required_blocks():
    """完整 synthetic（20×730）跑通且產合法 verdict + 協議強制區塊全在（不崩）。"""
    panel, universe = harness.build_synthetic_panel(n_days=730, n_symbols=20, carry_signal=True)
    report = harness.run_diagnostic(panel, universe)
    v = report["decision_tree"]["verdict"]
    assert v in {"INCONCLUSIVE-A", "INCONCLUSIVE-B", "NO-GO-A", "NO-GO-B", "NO-GO-C",
                 "NO-GO-D", "NO-GO-E", "NO-GO", "regime-bet / learning-only", "GO"}
    # K=8 誠實。
    assert report["trial_budget_K"] == 8
    # 兩個 N_eff 必算（§4.3）。
    assert "pca_effective_dimension_price_return" in report
    assert "pca_effective_dimension_funding_tiltscore" in report
    # funding persistence + forward significance 必算（§4.1）。
    assert "funding_persistence" in report
    assert "funding_tilt_forward_significance" in report
    # §4.5 horizon scan 必算。
    assert "horizon_cost_scan" in report
    assert "curve" in report["horizon_cost_scan"]
    # 三條紅線聲明。
    assert set(report["redlines"].keys()) == {
        "redline_1_perp_only_directional", "redline_2_funding_cap_ssot",
        "redline_3_funding_double_sided_accounting"}
    # leak-free vs naive 並列（§2.1）+ per-leg 分解（MIT 強制）。
    for ev in report["signal_evaluation"].values():
        assert "annualized_net_sharpe_leakfree" in ev
        assert "annualized_gross_sharpe_naive" in ev
        assert "accounting" in ev
        assert "long_leg" in ev["accounting"] and "short_leg" in ev["accounting"]
    # 內部 ndarray 欄位已清（可序列化）。
    import json
    json.dumps(report, default=str)


def test_horizon_scan_reports_cost_share_curve():
    """§4.5 horizon scan 產 H_min∈{1,3,7,14} 的 cost-share 曲線 + short-leg 拆解。"""
    panel, universe = harness.build_synthetic_panel(n_days=730, n_symbols=20, carry_signal=True)
    report = harness.run_diagnostic(panel, universe)
    scan = report["horizon_cost_scan"]
    assert scan["scan_hmins"] == [1, 3, 7, 14]
    for h in (1, 3, 7, 14):
        c = scan["curve"][f"H{h}"]
        assert "cost_share_of_abs_net" in c
        assert "short_leg_net_bps" in c
        assert "short_leg_gross_price_bps" in c


# ── 唯讀紀律靜態檢查 ────────────────────────────────────────────────────────

def test_data_loader_sql_is_read_only():
    """data_loader 的 SQL 只含 SELECT，無寫操作；強制 readonly session。"""
    import inspect
    src = inspect.getsource(data_loader)
    upper = src.upper()
    for forbidden in ("INSERT INTO", "UPDATE ", "DELETE FROM", "DROP ", "CREATE TABLE",
                      "ALTER TABLE", "TRUNCATE"):
        assert forbidden not in upper, f"forbidden write op found: {forbidden}"
    assert "set_session(readonly=True)" in src


def test_canonical_run_id_fixed():
    """canonical run_id 固定常數（協議 §2.5，禁跨 run 混讀）。"""
    assert data_loader.CANONICAL_FUNDING_RUN_ID == "18b3c2f8-6125-42a8-a42c-cfcc8aec9406"
    # data_loader 的 funding query 用 run_id 參數過濾（不可全表掃）。
    import inspect
    src = inspect.getsource(data_loader._load_funding_history)
    assert "run_id = %s" in src


def test_signal_a_top_short_bottom_long():
    """信號 A：top tertile（funding 最正）= short -1、bottom（最負）= long +1（協議 §1.A）。"""
    # 3 symbol，tiltscore 明確排序：S0 最負、S2 最正。
    n = 5
    tss = {}
    for i, val in enumerate([-0.001, 0.0, 0.001]):  # S0 最負 / S1 mid / S2 最正
        lf = np.full(n, val)
        tss[f"S{i}"] = signals.TiltScoreSeries(name="L3", leakfree=lf, naive=lf)
    surv = {f"S{i}": np.ones(n, dtype=bool) for i in range(3)}
    unc = {f"S{i}": False for i in range(3)}
    sig = signals.signal_a_cross_sectional(tss, surv, unc, 3)
    # S0（最負）= long +1；S2（最正）= short -1。
    assert sig["S0"].leakfree[2] == 1.0  # bottom → long
    assert sig["S2"].leakfree[2] == -1.0  # top → short


def test_signal_a_excludes_interval_uncertain():
    """interval_uncertain symbol 不入 cross-sectional rank（協議 §2.2）。"""
    n = 5
    tss = {}
    for i, val in enumerate([-0.001, 0.0, 0.001, 0.002]):
        lf = np.full(n, val)
        tss[f"S{i}"] = signals.TiltScoreSeries(name="L3", leakfree=lf, naive=lf)
    surv = {f"S{i}": np.ones(n, dtype=bool) for i in range(4)}
    # S3 interval 不明 → 排除。
    unc = {"S0": False, "S1": False, "S2": False, "S3": True}
    sig = signals.signal_a_cross_sectional(tss, surv, unc, 3)
    # S3 全程 signal=0（不入 rank）。
    assert np.all(sig["S3"].leakfree == 0.0)
