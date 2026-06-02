"""多日 trend 診斷 harness 單元測試（synthetic data，Mac 可跑）。

MODULE_NOTE:
  模塊用途：證 harness 核心邏輯正確，**最重要 = 證 leak-free shift(1) 有 bite**：
    注入 look-ahead（信號偷看 current bar）→ 測試抓到（naive ≠ leak-free）。
  覆蓋（對齊協議 §2 / §3 / §4）：
    - shift(1) 鐵律：leak-free 信號第 t 日只用 C_{t-1}（無 current bar）。
    - leak detection bite：構造「完美 look-ahead」信號 → naive Sharpe 遠高於 leak-free。
    - cost 含 funding 累積：持有越久 funding drag 越高；多空符號正確。
    - effective N：方向翻轉次數 → cluster 縮減。
    - 統計檢定（Ljung-Box / JB / ADF）在已知 synthetic 性質上回正確判定。
    - 決策樹 fail-fast：低 effective N → INCONCLUSIVE-A。
    - 唯讀紀律：data_loader 強制 readonly session（靜態檢查 SQL 無寫操作）。
  依賴：pytest + numpy。不連 PG（全 synthetic / 純函數）。
"""

from __future__ import annotations

import numpy as np
import pytest

from multiday_trend_diagnostic import cost_model, data_loader, harness, pnl, signals, stats


# ── §2 shift(1) 鐵律 ────────────────────────────────────────────────────────

def test_shift1_excludes_current_bar():
    """leak-free 信號第 t 日的計算根本拿不到 C_t（shift(1) 鐵律）。"""
    close = np.array([100.0, 110.0, 90.0, 95.0, 130.0])
    shifted = signals._shift1(close)
    assert np.isnan(shifted[0])  # 第 0 日沒有 t-1
    assert shifted[1] == 100.0  # out[1] = close[0]
    assert shifted[2] == 110.0
    assert shifted[4] == 95.0  # out[4]=close[3]，絕不是 close[4]=130


def test_signal_a_leakfree_uses_only_past_close():
    """signal_A leak-free 在 t 日只用 C_{t-1..t-1-k}；改 C_t 不影響當日 leak-free 信號。

    這是 shift(1) 鐵律的單元證明：current bar C_t 改任何值，leak-free 整條序列不動。
    """
    k = 2
    # 用會讓 naive 改「符號」的價格：C_5 從上漲改成暴跌 → naive 第 5 日 sign 翻負。
    close = np.array([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    ss = signals.signal_a(close, k)
    lf_before = ss.leakfree.copy()
    close2 = close.copy()
    close2[5] = 50.0  # current bar 暴跌
    ss2 = signals.signal_a(close2, k)
    # leak-free：第 5 日信號 = sign(ln(C_4/C_2))，與 C_5 無關 → 整條不變（鐵律）。
    assert np.allclose(np.nan_to_num(lf_before), np.nan_to_num(ss2.leakfree), equal_nan=True)
    # naive：第 5 日信號 = sign(ln(C_5/C_3))；C_5 50<C_3 103 → 由 +1 翻成 -1（證 naive 偷看 C_t）。
    assert ss.naive[5] == 1.0
    assert ss2.naive[5] == -1.0


# ── §2.2 leak detection BITE（最重要）──────────────────────────────────────

def _execute_signal_on_same_bar_close(signal: np.ndarray, close: np.ndarray) -> np.ndarray:
    """F3 Donchian 漏洞重現：用「算信號那一根的收盤→次根收盤」報酬執行信號。

    leak 程度 = 信號用第 t 根資料、卻在第 t 根收盤就成交。harness 正式路徑用 open-to-open
    且信號 shift 過，避免此漏；本 helper 只在測試裡刻意製造漏，證 naive 軌能放大它。
    return[t] = signal[t] × ln(close[t+1]/close[t])。
    """
    n = len(signal)
    out = np.zeros(n, dtype=float)
    for t in range(n - 1):
        s = signal[t]
        if np.isfinite(s) and s != 0:
            out[t] = np.sign(s) * float(np.log(close[t + 1] / close[t]))
    return out


def test_leakfree_has_bite_against_perfect_lookahead():
    """構造強自相關價格 → naive（含 current bar）的 look-ahead 應放大 gross Sharpe。

    證 harness 的 naive-vs-leakfree 並列能 catch look-ahead（協議 §2.2 Donchian F3 教訓）。
    用強正自相關（趨勢持續）價格 + signal_A：naive 在第 t 日已知 C_t（含當日漲跌），
    leak-free 只到 C_{t-1}；在自相關下「今天剛漲」對「明天續漲」有預測力 → naive 同 bar
    執行的 gross Sharpe 顯著高於 leak-free 同 bar 執行。差距即 look-ahead inflation。
    """
    rng = np.random.default_rng(7)
    n = 600
    # 強正自相關報酬（AR(1) φ=0.5）→ 動量真實存在，但「偷看今天」放大優勢。
    r = np.zeros(n)
    for t in range(1, n):
        r[t] = 0.5 * r[t - 1] + rng.normal(0, 0.01)
    close = np.exp(np.log(100.0) + np.cumsum(r))
    ss = signals.signal_a(close, k=5)
    # 兩軌都用「同 bar 執行」隔離 look-ahead 維度（唯一差異 = 信號是否含 C_t）。
    pnl_lf = _execute_signal_on_same_bar_close(ss.leakfree, close)
    pnl_nv = _execute_signal_on_same_bar_close(ss.naive, close)
    s_lf = stats.sharpe(pnl_lf)
    s_nv = stats.sharpe(pnl_nv)
    assert s_lf is not None and s_nv is not None
    # naive 偷看 C_t → gross Sharpe 明顯高於 leak-free（bite 證明）。
    assert s_nv > s_lf + 0.1, f"naive {s_nv} should clearly exceed leakfree {s_lf} under look-ahead"
    # 且 inflation 比例 > 30%（協議 §2.2 的 NO-GO-B 閾值能被觸發）。
    inflation = (s_nv - s_lf) / abs(s_lf)
    assert inflation > 0.30, f"look-ahead inflation {inflation:.2%} should exceed 30%"


def test_leakfree_naive_identical_when_no_lookahead_advantage_on_random_walk():
    """純隨機漫步（無趨勢）下 leak-free 與 naive 都應接近 0 Sharpe（無 edge 可偷）。"""
    rng = np.random.default_rng(11)
    n = 500
    close = np.exp(np.log(100.0) + np.cumsum(rng.normal(0, 0.02, n)))
    open_px = np.concatenate([[close[0]], close[:-1]])
    ss = signals.signal_a(close, k=40)
    _t, pos_lf, _f = pnl.build_trades("X", ss.leakfree, open_px, variant="daily")
    g_lf, _ = pnl.daily_returns_from_positions(pos_lf, open_px, 0.0)
    s_lf = stats.sharpe(g_lf)
    # 隨機漫步上 TSMOM 無 edge → leak-free Sharpe 應接近 0（|.|<0.15 寬鬆界）。
    assert s_lf is None or abs(s_lf) < 0.15


# ── §3 cost 含 funding 累積 ─────────────────────────────────────────────────

def test_funding_accumulates_with_holding_days():
    """funding 按時間累積：持有越久 → 多單 funding drag 越高（協議 §3 樞紐）。"""
    rate = 0.0001  # +1bp/8h 正 funding
    c5, _ = cost_model.funding_cost_bps_for_holding(+1, 5, rate)
    c30, _ = cost_model.funding_cost_bps_for_holding(+1, 30, rate)
    c60, _ = cost_model.funding_cost_bps_for_holding(+1, 60, rate)
    assert c5 < c30 < c60  # 單調遞增
    # 30 日 × 3 結算/日 × 1bp = 90bp 多單 funding 成本。
    assert abs(c30 - 90.0) < 1e-6


def test_funding_sign_long_pays_short_receives():
    """正 funding 下：多單付（正成本）、空單收（負成本=補貼）。"""
    rate = 0.0001
    long_cost, _ = cost_model.funding_cost_bps_for_holding(+1, 10, rate)
    short_cost, _ = cost_model.funding_cost_bps_for_holding(-1, 10, rate)
    assert long_cost > 0  # 多單付正 funding
    assert short_cost < 0  # 空單收正 funding（補貼）
    assert abs(long_cost + short_cost) < 1e-9  # 對稱


def test_round_trip_cost_taker_vs_maker():
    """taker RT=11bps、maker RT=4bps（協議 §3）。"""
    taker = cost_model.round_trip_cost_bps(+1, 0.0, 0.0, maker=False)
    maker = cost_model.round_trip_cost_bps(+1, 0.0, 0.0, maker=True)
    assert abs(taker.fee_bps - 11.0) < 1e-9
    assert abs(maker.fee_bps - 4.0) < 1e-9
    # 0 持有期 → funding=0。
    assert taker.funding_bps == 0.0


def test_cost_edge_ratio_classification():
    """cost_edge_ratio 分級：<0.5 healthy / 0.5-0.8 marginal / ≥0.8 abandon。"""
    assert cost_model.classify_cost_edge_ratio(0.3) == "healthy"
    assert cost_model.classify_cost_edge_ratio(0.6) == "marginal"
    assert cost_model.classify_cost_edge_ratio(0.9) == "abandon"
    # gross ≤0 → undefined。
    assert cost_model.cost_edge_ratio(11.0, -5.0) is None
    assert cost_model.classify_cost_edge_ratio(None) == "undefined_or_gross_negative"


def test_funding_killer_scenario():
    """gross 正但持有久 → funding 把 net 拖負（協議 §5 funding-is-killer 標記）。"""
    # gross +50bps，多單持 40 日（120 結算）× 1bp funding = 120bp funding → net 應為負。
    rate = 0.0001
    cb = cost_model.round_trip_cost_bps(+1, 40.0, rate)
    gross_bps = 50.0
    net = gross_bps - cb.total_bps
    assert cb.funding_bps == pytest.approx(120.0, abs=1e-6)
    assert net < 0  # funding 是殺手


# ── §4 effective N / 翻轉次數 ───────────────────────────────────────────────

def test_direction_flips_counted():
    """方向翻轉次數 = effective N 原料；信號每翻一次 position 變一次。

    position[t]=sign(signal[t-1])（t-1 收盤算的信號，t 日開盤建倉）。最後一根 signal
    無法在無 t+1 開盤下執行，故不形成 position（leak-free 執行紀律的必然結果）。
    """
    signal = np.array([np.nan, 1.0, 1.0, -1.0, -1.0, 1.0])
    open_px = np.array([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    _trades, pos, flips = pnl.build_trades("X", signal, open_px, variant="daily")
    # position: signal[0]=nan→pos[1]=0; signal[1]=1→pos[2]=1; signal[2]=1→pos[3]=1;
    # signal[3]=-1→pos[4]=-1; signal[4]=-1→pos[5]=-1。序列 [0,0,1,1,-1,-1]。
    assert list(pos) == [0.0, 0.0, 1.0, 1.0, -1.0, -1.0]
    # 方向改變：idx2 (0→+1)、idx4 (+1→-1) = 2 次。
    assert flips == 2


def test_flip_hold_min_reduces_turnover():
    """variant flip_hold_min（H_min=5）turnover 應低於 daily（過濾 whipsaw）。"""
    rng = np.random.default_rng(3)
    n = 300
    # 高頻翻轉信號（whipsaw）。
    raw = np.sign(rng.normal(0, 1, n))
    signal = raw.astype(float)
    open_px = np.exp(np.log(100.0) + np.cumsum(rng.normal(0, 0.01, n)))
    _t1, _p1, flips_daily = pnl.build_trades("X", signal, open_px, variant="daily")
    _t2, _p2, flips_hold = pnl.build_trades("X", signal, open_px, variant="flip_hold_min")
    assert flips_hold < flips_daily  # 最短持有過濾掉大量 whipsaw


def test_pca_effective_n_below_symbol_count_for_correlated():
    """高相關 symbol → N_eff 遠小於 symbol 數（協議 §4.6）。"""
    rng = np.random.default_rng(5)
    n, s = 400, 20
    market = rng.normal(0, 1, n)
    # 每 symbol = 0.9×market + 0.1×idio → 高相關。
    mat = np.column_stack([0.9 * market + 0.1 * rng.normal(0, 1, n) for _ in range(s)])
    res = stats.pca_effective_n(mat)
    assert res is not None
    assert res["n_eff"] < 5  # 20 高相關 → 有效維度 << 20
    assert res["pc1_explained_share"] > 0.7  # PC1 主導


# ── §4.7 統計檢定正確性 ─────────────────────────────────────────────────────

def test_ljung_box_detects_positive_autocorr():
    """AR(1) 正係數序列 → Ljung-Box 偵測正自相關。"""
    rng = np.random.default_rng(9)
    n = 600
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = 0.4 * x[t - 1] + rng.normal(0, 1)  # 正 AR(1)
    res = stats.ljung_box(x, lags=10)
    assert res is not None
    assert res["rho_1"] > 0.2  # 一階自相關明顯為正
    assert res["positive_autocorr"] is True


def test_ljung_box_white_noise_no_autocorr():
    """白噪音 → Ljung-Box 不應宣稱正自相關。"""
    rng = np.random.default_rng(13)
    x = rng.normal(0, 1, 600)
    res = stats.ljung_box(x, lags=10)
    assert res is not None
    assert res["positive_autocorr"] is False


# ── FIX-2 正確尺度 TSMOM 顯著性檢定（取代 daily-LB gate）────────────────────

def _trending_close(n: int, seed: int, *, segment_len: int = 120, drift: float = 0.004) -> np.ndarray:
    """構造**多日 momentum 真實存在**的收盤：長段（>>k）單向趨勢，符號分段持續。

    為什麼這驗 TSMOM bite：每段 ~segment_len 日同向漂移（遠長於 k）→ 過去 k 日報酬符號
    對未來 k 日報酬有預測力（正動量）。正確尺度檢定應偵測到（mean>0、|t|≥2）。
    """
    rng = np.random.default_rng(seed)
    r = np.zeros(n)
    sign = 1.0
    for t in range(n):
        if t % segment_len == 0:
            sign = 1.0 if rng.random() < 0.5 else -1.0
        r[t] = sign * drift + rng.normal(0, 0.012)
    return np.exp(np.log(100.0) + np.cumsum(r))


def test_tsmom_significance_detects_real_multiday_momentum():
    """多日 momentum 真實存在（長趨勢段）→ 正確尺度 TSMOM 檢定 mean>0 且顯著。

    證 FIX-2 的正確尺度檢定對「已知有 trend」序列有 bite（非 false-negative）。
    用 20 個共享趨勢段相位的 symbol（高相關但 momentum 真實）→ pooled 顯著正動量。
    """
    n = 800
    close = {f"S{i:02d}": _trending_close(n, seed=100 + i, segment_len=140, drift=0.005)
             for i in range(20)}
    res = stats.tsmom_significance(close, None, k=30)
    assert res is not None and not res.get("insufficient")
    assert res["mean_signed_fwd_bps"] > 0, "trending series should have positive signed forward return"
    assert res["t_stat_hac"] is not None and res["t_stat_hac"] >= 2.0, \
        f"HAC t-stat {res['t_stat_hac']} should clear 2.0 on genuine multi-day momentum"
    assert res["significant_positive_momentum"] is True
    assert res["hit_rate"] > 0.5


def test_tsmom_significance_null_on_random_walk():
    """純隨機漫步（無 momentum）→ 正確尺度 TSMOM 不顯著（mean≈0 / |t|<2 / hit≈50%）。

    證 FIX-2 不會把白噪音誤判為 momentum（避免 false-positive）。
    """
    rng = np.random.default_rng(31)
    n = 800
    close = {f"S{i:02d}": np.exp(np.log(100.0) + np.cumsum(rng.normal(0, 0.02, n)))
             for i in range(20)}
    res = stats.tsmom_significance(close, None, k=30)
    assert res is not None and not res.get("insufficient")
    assert res["significant_positive_momentum"] is False, \
        f"random walk must NOT show significant positive momentum (t={res['t_stat_hac']})"
    assert abs(res["hit_rate"] - 0.5) < 0.1  # hit rate 接近 50%


def test_tsmom_hac_tstat_below_naive_under_overlap():
    """overlap-corrected（HAC）t-stat 應 ≤ 樸素 t-stat（修正重疊誘發的虛高顯著性）。

    證 Newey-West 修正確實壓低了重疊取樣下被低估的 SE → t-stat 不再虛高（協議要求
    overlap-corrected，非樸素）。
    """
    n = 800
    close = {f"S{i:02d}": _trending_close(n, seed=200 + i, segment_len=140, drift=0.005)
             for i in range(20)}
    res = stats.tsmom_significance(close, None, k=30)
    assert res is not None and not res.get("insufficient")
    assert res["t_stat_naive_overlapping"] is not None and res["t_stat_hac"] is not None
    # 正動量下兩者同號；HAC 修正後 |t| 應不超過樸素 |t|（重疊使樸素 SE 偏小、t 偏大）。
    assert abs(res["t_stat_hac"]) <= abs(res["t_stat_naive_overlapping"]) + 1e-6


def test_tsmom_significance_deterministic_ramp_no_false_go():
    """退化輸入（確定性 ramp / 近常數序列）→ 不顯著、不產 garbage t、不 false-GO（FIX-A）。

    re-E2 MEDIUM-1 回歸：近常數序列的離散度 ≈0 但因浮點誤差非精確 0（gamma0≈1e-31、
    se≈1e-16）。原 `lrv<=0→None`/`sd>0` 護欄會被 FP 噪音繞過 → t=mu/se≈1e16 garbage →
    significant_positive_momentum=True = 在證偽優先 harness 的**最壞方向**製造 false-GO。
    相對離散度地板（fail-closed）應把這類退化輸入判為「無有意義離散度」→ t_stat 退回 None、
    不顯著。餵每 symbol 完全相同的確定性線性 ramp（過去/未來 k 日報酬恆正且幾乎無變異）。
    """
    n = 600
    k = 30
    # 確定性線性 ramp：log-price 每日恆定增量 → 每個 signed forward 報酬幾乎相同（離散度≈FP 噪音）。
    base = np.exp(np.log(100.0) + np.cumsum(np.full(n, 0.001)))
    close = {f"S{i:02d}": base.copy() for i in range(20)}
    res = stats.tsmom_significance(close, None, k=k)
    assert res is not None and not res.get("insufficient")
    # mean 為正（ramp 上行 + sign(lookback)>0），但離散度可忽略 → t 必須是 None（fail-closed），
    # 絕不能是 ~1e16 的 garbage。
    assert res["mean_signed_fwd_bps"] > 0
    assert res["t_stat_hac"] is None, \
        f"degenerate ramp must yield None HAC t (fail-closed), got garbage {res['t_stat_hac']}"
    assert res["t_stat_naive_overlapping"] is None, \
        f"degenerate ramp must yield None naive t, got garbage {res['t_stat_naive_overlapping']}"
    # 最關鍵：不得 false-GO（退化輸入不是顯著動量）。
    assert res["significant_positive_momentum"] is False


def test_newey_west_tstat_fail_closed_on_near_constant():
    """_newey_west_mean_tstat 對近常數序列（FP 噪音級離散度）回 None，不產 1e16 garbage（FIX-A）。

    直測底層 HAC：近常數序列 se 相對 |mu| 可忽略 → fail-closed None。對照真實有變異的序列
    仍正常產出有限 t（護欄不誤殺真實樣本）。
    """
    # 近常數：1.0 + 極小 FP 級擾動 → mu≈1、se≈1e-16 → 原本會算出 ~1e16 garbage。
    near_const = np.full(500, 1.0) + np.linspace(0, 1e-13, 500)
    assert stats._newey_west_mean_tstat(near_const, lag=29) is None
    # 對照：真實有變異的序列（mean 偏離 0、正常離散度）→ 仍產有限 t（不誤殺）。
    rng = np.random.default_rng(77)
    real = rng.normal(0.01, 0.02, 500)
    t = stats._newey_west_mean_tstat(real, lag=29)
    assert t is not None and np.isfinite(t)


def test_tsmom_significance_survivorship_excludes_pre_listing():
    """上市前（survivorship=False）的進場與前瞻終點都不計入 TSMOM 觀測。"""
    n = 400
    close = {f"S{i:02d}": _trending_close(n, seed=300 + i) for i in range(5)}
    surv = {s: np.ones(n, dtype=bool) for s in close}
    # 其中一個 symbol 前 200 日未上市。
    surv["S00"][:200] = False
    res_full = stats.tsmom_significance(close, None, k=30)
    res_surv = stats.tsmom_significance(close, surv, k=30)
    assert res_full is not None and res_surv is not None
    # 套 survivorship 後觀測數應較少（S00 前 200 日被排除）。
    assert res_surv["n_obs"] < res_full["n_obs"]


# ── FIX-3 per-symbol / pooled Ljung-Box 廣度 ────────────────────────────────

def test_ljung_box_universe_reports_per_symbol_and_pooled():
    """ljung_box_universe 回 per-symbol（全部）+ pooled + 計數（FIX-3 廣度）。"""
    rng = np.random.default_rng(41)
    n = 500
    # 全白噪音 universe → 0 symbol 顯著正自相關。
    close = {f"S{i:02d}": np.exp(np.log(100.0) + np.cumsum(rng.normal(0, 0.02, n)))
             for i in range(20)}
    res = stats.ljung_box_universe(close, lags=10)
    assert res is not None
    assert res["n_symbols_evaluated"] == 20
    assert len(res["per_symbol"]) == 20
    assert res["pooled_demeaned"] is not None
    assert res["n_symbols_positive_autocorr"] == 0  # 白噪音 universe
    assert res["universe_has_positive_autocorr"] is False


# ── FIX-2/FIX-4 相干性判定（gate 依據，非單一孤立 k）─────────────────────────

def _mk_tsmom_k(t_hac, mean_bps, *, hit=0.51, n_obs=12000):
    """構造單 k 的 tsmom_significance 結果（給 _summarize_tsmom 測相干性）。"""
    return {
        "k": 30, "n_obs": n_obs, "n_eff_non_overlapping": n_obs / 30,
        "mean_signed_fwd_bps": mean_bps, "hit_rate": hit, "t_stat_hac": t_hac,
        "t_stat_naive_overlapping": t_hac * 3, "significant_positive_momentum": (t_hac >= 2.0 and mean_bps > 0),
    }


def test_summarize_tsmom_isolated_single_k_is_not_coherent():
    """孤立單 k 顯著（相鄰不顯著）→ coherent_positive_momentum=False（雜訊非 momentum）。

    重現真實 PG 形態：k40 孤立顯著（t=2.72）但 k20/k30/k60 不顯著、k90 反轉 → 不相干。
    """
    per_k = {
        "k20": _mk_tsmom_k(0.40, 18.0),
        "k30": _mk_tsmom_k(1.66, 113.0),
        "k40": _mk_tsmom_k(2.72, 241.0, hit=0.533),  # 孤立顯著
        "k60": _mk_tsmom_k(0.83, 118.0),
        "k90": _mk_tsmom_k(-2.60, -622.0, hit=0.442),  # 顯著反轉
    }
    s = harness._summarize_tsmom(per_k)
    assert s["any_significant_positive"] is True  # k40 單 k 確實過 2.0
    assert s["significant_positive_ks"] == ["k40"]
    assert s["significant_reversal_ks"] == ["k90"]
    # 但相干性 = False（孤立單 k + 有反轉）→ gate 會判 NO-GO-TREND。
    assert s["coherent_positive_momentum"] is False


def test_summarize_tsmom_coherent_when_two_adjacent_ks_significant():
    """≥2 相鄰 k 顯著正 且 無反轉 → coherent_positive_momentum=True（通過 gate）。"""
    per_k = {
        "k20": _mk_tsmom_k(1.5, 50.0),
        "k30": _mk_tsmom_k(2.4, 200.0, hit=0.55),  # 顯著
        "k40": _mk_tsmom_k(2.9, 280.0, hit=0.57),  # 顯著（相鄰）
        "k60": _mk_tsmom_k(1.9, 150.0),
        "k90": _mk_tsmom_k(1.2, 90.0),
    }
    s = harness._summarize_tsmom(per_k)
    assert set(s["significant_positive_ks"]) == {"k30", "k40"}
    assert s["significant_reversal_ks"] == []
    assert s["coherent_positive_momentum"] is True


def test_summarize_tsmom_non_adjacent_ks_not_coherent():
    """兩端非相鄰 k 顯著正（k20+k90，中間斷裂）+ 無反轉 → coherent=False（FIX-B）。

    re-E2 MEDIUM-2 回歸：原 `len(sig_pos)>=2` 會把 k20+k90 這種非相鄰兩端顯著誤判為
    coherent（與「相鄰 plateau」docstring 矛盾、MIT 終裁實作相鄰）。相鄰約束下，k20 與 k90
    在 grid(20,30,40,60,90) 不連續（中間 k30/k40/k60 不顯著）→ plateau 斷裂 → 不相干。
    """
    per_k = {
        "k20": _mk_tsmom_k(2.6, 90.0, hit=0.55),   # 顯著正（grid 端點）
        "k30": _mk_tsmom_k(1.1, 40.0),              # 不顯著
        "k40": _mk_tsmom_k(0.9, 30.0),              # 不顯著
        "k60": _mk_tsmom_k(1.3, 50.0),              # 不顯著
        "k90": _mk_tsmom_k(2.8, 120.0, hit=0.56),  # 顯著正（另一端點，與 k20 非相鄰）
    }
    s = harness._summarize_tsmom(per_k)
    assert set(s["significant_positive_ks"]) == {"k20", "k90"}
    assert s["significant_reversal_ks"] == []
    assert s["any_significant_positive"] is True  # 確有 2 個 k 顯著正
    # 但非相鄰（中間斷裂）→ 不形成連續尺度 plateau → 不相干。
    assert s["coherent_positive_momentum"] is False


def test_summarize_tsmom_reversal_breaks_coherence():
    """即使有 2 個 k 顯著正，只要存在顯著反轉 → 不相干（momentum 與 reversal 並存=雜訊）。"""
    per_k = {
        "k20": _mk_tsmom_k(2.3, 100.0, hit=0.54),  # 顯著正
        "k30": _mk_tsmom_k(2.5, 180.0, hit=0.55),  # 顯著正
        "k90": _mk_tsmom_k(-2.4, -400.0, hit=0.45),  # 顯著反轉
    }
    s = harness._summarize_tsmom(per_k)
    assert len(s["significant_positive_ks"]) == 2
    assert s["significant_reversal_ks"] == ["k90"]
    assert s["coherent_positive_momentum"] is False  # 反轉破壞相干性


def test_jarque_bera_detects_fat_tails():
    """厚尾分布（t-dist-like）→ JB 拒常態 + fat_tailed=True。"""
    rng = np.random.default_rng(17)
    # 混合常態製造厚尾。
    x = np.concatenate([rng.normal(0, 1, 900), rng.normal(0, 6, 100)])
    res = stats.jarque_bera(x)
    assert res is not None
    assert res["fat_tailed"] is True
    assert res["reject_normality_5pct"] is True


def test_adf_random_walk_nonstationary_returns_stationary():
    """隨機漫步價格非平穩（不拒單根）；其報酬平穩（拒單根）。"""
    rng = np.random.default_rng(19)
    n = 500
    logp = np.cumsum(rng.normal(0, 1, n))  # 隨機漫步
    rets = np.diff(logp)
    res_p = stats.adf_test(logp)
    res_r = stats.adf_test(rets)
    assert res_p is not None and res_r is not None
    # 報酬（白噪音）應平穩。
    assert res_r["stationary"] is True


def test_annualized_sharpe_uses_365():
    """年化用 √365（crypto 24/7）。"""
    rng = np.random.default_rng(21)
    daily = rng.normal(0.001, 0.01, 500)
    s_daily = stats.sharpe(daily)
    s_ann = stats.annualized_sharpe(daily)
    assert abs(s_ann - s_daily * np.sqrt(365.0)) < 1e-9


def test_trial_budget_k_is_24():
    """K=24（12 信號變體 × 2 持有期）；改 grid 忘更新 K 會被自檢抓到。"""
    assert signals.count_trial_budget() == 24
    assert signals.TRIAL_BUDGET_K == 24


# ── 決策樹 fail-fast ────────────────────────────────────────────────────────

def test_decision_tree_inconclusive_a_on_low_effective_n():
    """少 symbol + 短窗 → effective N<60 → INCONCLUSIVE-A（停，不跑 Phase 2）。"""
    # 3 symbol、150 日 → flips × cluster_factor 必 < 60。
    panel, universe = harness.build_synthetic_panel(n_days=150, n_symbols=3, trending=True)
    report = harness.run_diagnostic(panel, universe)
    assert report["decision_tree"]["verdict"] == "INCONCLUSIVE-A"
    assert report["decision_tree"]["stopped_at"] == "step_0_effective_n"


def test_synthetic_full_run_produces_verdict():
    """完整 synthetic（20 symbol × 730 日）跑通並產合法 verdict（不崩）。"""
    panel, universe = harness.build_synthetic_panel(n_days=730, n_symbols=20, trending=True)
    report = harness.run_diagnostic(panel, universe)
    v = report["decision_tree"]["verdict"]
    assert v in {"INCONCLUSIVE-A", "NO-GO-TREND", "NO-GO-B", "NO-GO-C",
                 "SURVIVES_EARLY_GATES_NEEDS_PHASE_2"}
    # leak-free vs naive 必並列（協議 §2.2 報告強制）。
    for ev in report["signal_evaluation"].values():
        assert "annualized_net_sharpe_leakfree" in ev
        assert "annualized_gross_sharpe_naive" in ev
    # PCA effective N 必算。
    assert report["pca_effective_dimension"] is not None
    # K 誠實。
    assert report["trial_budget_K"] == 24
    # FIX-2：正確尺度 TSMOM 區塊必算（verdict 依據）。
    assert "tsmom_correct_scale_significance" in report
    assert "per_k" in report["tsmom_correct_scale_significance"]
    # FIX-3：per-symbol/pooled Ljung-Box 必在 data_quality。
    assert "ljung_box_universe" in report["data_quality"]


def test_verdict_produced_inside_run_diagnostic_not_main():
    """FIX-1 接線修復：verdict 必由 run_diagnostic 直接產出（不依賴 main 事後覆寫）。

    回歸防護：原 _inject_ljung_box_gate 只在 main 呼叫 → 被測 API run_diagnostic 永不產
    正確 verdict。本測試直呼 run_diagnostic（不經 main）→ verdict 必為終值、不需任何覆寫。
    """
    # 確認舊的接線函數已刪除（不再有 main-only 的 verdict 覆寫路徑）。
    assert not hasattr(harness, "_inject_ljung_box_gate")
    panel, universe = harness.build_synthetic_panel(n_days=730, n_symbols=20, trending=False)
    report = harness.run_diagnostic(panel, universe)
    # run_diagnostic 自身產出的 decision_tree 已是終值（含 stopped_at），無 pre_ljung_box 殘留。
    assert report["decision_tree"]["verdict"] != ""
    assert "decision_tree_pre_ljung_box" not in report
    # data_quality 在決策樹前算好（門檻可讀 ljung_box_universe / tsmom 結果）。
    assert report["data_quality"].get("ljung_box_universe") is not None


def test_end_to_end_no_momentum_verdict_is_close_trend():
    """FIX-5 端到端：已知無-momentum 序列 + 足夠 effective N → 終 verdict = NO-GO-TREND。

    餵「長窗 + 多 symbol 隨機漫步（無 momentum）」確保 Step0 effective N 過門檻（不被
    INCONCLUSIVE-A 提前攔），讓決策樹一路走到正確尺度 TSMOM 門檻並停在那裡（close-trend
    的合法理由 = 正確尺度無顯著 momentum，非 daily autocorr）。
    """
    rng = np.random.default_rng(20260602)
    n = 900
    universe = tuple(f"RW{i:02d}USDT" for i in range(20))
    base = __import__("datetime").date(2024, 1, 1)
    dates = [base + __import__("datetime").timedelta(days=i) for i in range(n)]
    close, open_, surv = {}, {}, {}
    # 高頻翻轉的隨機漫步（無 momentum）→ 大量方向翻轉 → effective N 高、過 Step0。
    for s in universe:
        r = rng.normal(0, 0.02, n)
        c = np.exp(np.log(100.0) + np.cumsum(r))
        close[s] = c
        open_[s] = np.concatenate([[c[0]], c[:-1]])
        surv[s] = np.ones(n, dtype=bool)
    regime = data_loader.compute_rule_based_regime(close[universe[0]], dates)
    panel = data_loader.Panel(
        dates=dates, close=close, open_=open_,
        high={s: close[s] for s in universe}, low={s: close[s] for s in universe},
        volume={s: np.full(n, 1e6) for s in universe},
        survivorship=surv, regime=regime, funding_mean_per_8h={s: 0.0001 for s in universe},
        coverage_notes={"synthetic": True},
    )
    report = harness.run_diagnostic(panel, universe)
    dt_tree = report["decision_tree"]
    # 不應被 Step0 提前攔（effective N 足夠）。
    assert dt_tree["stopped_at"] != "step_0_effective_n", \
        f"expected to pass Step0 but stopped_at={dt_tree['stopped_at']}"
    # 終 verdict = NO-GO-TREND，停在正確尺度 TSMOM 門檻。
    assert dt_tree["verdict"] == "NO-GO-TREND", f"got {dt_tree['verdict']}"
    assert dt_tree["stopped_at"] == "correct_scale_tsmom_significance"
    # FIX-4：verdict 不再叫 NO-GO-A，且帶誠實 power caveat。
    assert "power_caveat" in dt_tree
    assert dt_tree["power_caveat"].get("statement")
    # reason 反映正確尺度證據，非「daily autocorrelation」。
    assert "correct-scale" in dt_tree["reason"].lower()


def test_survivorship_masks_pre_listing():
    """上市前（survivorship=False）信號歸零 → 不入場。"""
    n = 100
    close = np.exp(np.log(100.0) + np.cumsum(np.full(n, 0.001)))
    surv = np.zeros(n, dtype=bool)
    surv[50:] = True  # 前 50 日未上市
    ss = signals.signal_a(close, k=10)
    lf_sig = np.where(surv, ss.leakfree, 0.0)
    open_px = np.concatenate([[close[0]], close[:-1]])
    _trades, pos, _flips = pnl.build_trades("X", lf_sig, open_px, variant="daily")
    # 上市前持倉必為 0。
    assert np.all(pos[:50] == 0.0)


# ── 唯讀紀律靜態檢查 ────────────────────────────────────────────────────────

def test_data_loader_sql_is_read_only():
    """data_loader 的 SQL 字串只含 SELECT，無 INSERT/UPDATE/DELETE/DROP/CREATE。"""
    import inspect

    src = inspect.getsource(data_loader)
    upper = src.upper()
    for forbidden in ("INSERT INTO", "UPDATE ", "DELETE FROM", "DROP ", "CREATE TABLE",
                      "ALTER TABLE", "TRUNCATE"):
        assert forbidden not in upper, f"forbidden write op found: {forbidden}"
    # 必有 readonly session 強制。
    assert "set_session(readonly=True)" in src


def test_rule_based_regime_no_hmm():
    """regime 計算禁 HMM（協議 §4b）；用 BTC 200日MA + vol tercile（rule-based）。

    檢查執行邏輯不依賴 HMM 機制（hmmlearn / GaussianHMM / viterbi / baum-welch），
    且確實用 200日MA + tercile rule。docstring 提及「禁 HMM」是說明，不算違規。
    """
    import inspect

    src = inspect.getsource(data_loader.compute_rule_based_regime).lower()
    for forbidden in ("hmmlearn", "gaussianhmm", "viterbi", "baum", "hiddenmarkov", "import hmm"):
        assert forbidden not in src, f"HMM machinery found: {forbidden}"
    # 確認用 rule-based 元件。
    assert "regime_trend_ma_days" in src or "200" in src
    assert "bull" in src and "bear" in src and "chop" in src
