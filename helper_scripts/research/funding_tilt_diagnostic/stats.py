"""純 numpy 統計檢定 — funding-tilt 診斷 harness 專用。

MODULE_NOTE:
  模塊用途：實作協議 §4 統計門檻所需的純數值統計：funding persistence
    （§4.1 Ljung-Box on funding series，carry 統計基礎）、funding-tilt forward
    significance（§4.1 pooled cross-sectional mean forward + HAC t-stat）、
    兩個 N_eff（§4.3：price-return PCA + funding-tiltscore PCA）、JB / ARCH
    （§4.1 厚尾 → PSR 非 normal、vol clustering → block bootstrap）。
  為什麼純 numpy 自實作（不用 statsmodels）：Linux runtime（trade-core）只有
    numpy 2.4.4 + pandas，無 scipy / statsmodels。harness 必須能在 authoritative
    Linux PG 機器跑，故所有檢定純 numpy 重寫；卡方/常態臨界值用查表（避免 scipy）。
    PSR/DSR(K=8)/PBO/block-bootstrap 復用 ``lib/stats_common``（純 stdlib，互補
    不重疊），本模塊提供它沒有的 numpy 檢定（Ljung-Box/HAC/PCA/JB/ARCH）。
  主要函數：
    - ``funding_persistence_ljung_box`` — funding 序列正自相關（§4.1 carry 基礎）。
    - ``funding_tilt_forward_significance`` — pooled tertile long-short forward
      return mean + HAC t-stat（§4.1 verdict 主檢定）。
    - ``pca_effective_n`` — price-return N_eff（§4.3 裸價格方向集中度）。
    - ``funding_tiltscore_pca_effective_n`` — funding 信號有效獨立維度（§4.3 新）。
    - ``ljung_box`` / ``jarque_bera`` / ``arch_lm`` / ``sharpe`` /
      ``annualized_sharpe`` — 沿用 trend harness 同名實作。
  硬邊界：所有檢定對 NaN / 樣本不足回傳 None（caller fail-closed），不偽造 p-value。
    退化輸入（近常數序列 FP 噪音級離散度）→ 相對離散度地板 fail-closed（防 false-GO）。
  注意：本模塊只做 math，import-time 零 DB / 零檔案 I/O。
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

# crypto 24/7：年化用 √365 而非 √252（協議 §4.1）。
ANNUALIZATION_DAYS = 365.0

# 相對離散度地板（fail-closed 顯著性護欄，沿用 trend re-E2 MEDIUM-1）。
# 為什麼需要：退化輸入（確定性 ramp / 近常數序列）的離散度 ≈0 但因浮點誤差非精確 0。
#   原 `lrv<=0→None` / `sd>0` 護欄只擋精確 0，會被 FP 噪音繞過 → se 相對 |mu| 可忽略
#   → t≈mu/se≈1e16 garbage → 在「證偽優先」harness 的**最壞方向**製造 false-GO。
# 修法：若 se 相對序列量級 max(|mu|,1) 可忽略（< 此相對閾值）→ 視為無有意義離散度、
#   不顯著，return None（fail-closed）。
# 閾值取 1e-9：遠大於 FP round-off（~1e-15 量級）、遠小於任何真實報酬序列的相對 SE。
_REL_DISPERSION_FLOOR = 1e-9

# χ² 上尾臨界值查表（避免依賴 scipy.stats.chi2）。key=自由度 df，value=(p0.10, p0.05, p0.01)。
_CHI2_UPPER = {
    1: (2.706, 3.841, 6.635),
    2: (4.605, 5.991, 9.210),
    3: (6.251, 7.815, 11.345),
    4: (7.779, 9.488, 13.277),
    5: (9.236, 11.070, 15.086),
    6: (10.645, 12.592, 16.812),
    7: (12.017, 14.067, 18.475),
    8: (13.362, 15.507, 20.090),
    9: (14.684, 16.919, 21.666),
    10: (15.987, 18.307, 23.209),
    11: (17.275, 19.675, 24.725),
    12: (18.549, 21.026, 26.217),
    13: (19.812, 22.362, 27.688),
    14: (21.064, 23.685, 29.141),
    15: (22.307, 24.996, 30.578),
    16: (23.542, 26.296, 32.000),
    17: (24.769, 27.587, 33.409),
    18: (25.989, 28.869, 34.805),
    19: (27.204, 30.144, 36.191),
    20: (28.412, 31.410, 37.566),
}


def _clean(values) -> np.ndarray:
    """濾掉 None / 非有限值，回傳 float ndarray。"""
    arr = np.asarray([v for v in values if v is not None], dtype=float)
    return arr[np.isfinite(arr)]


def _chi2_pvalue_bucket(stat: float, df: int) -> Optional[float]:
    """用查表回傳卡方上尾 p-value 的保守上界（bucketed）。

    為什麼 bucketed 而非精確 p：無 scipy，但 harness 決策只需「p<0.05 顯著與否」。
    回傳值為保守上界：stat ≥ 1% 臨界 → p≤0.01；≥5% → p≤0.05；≥10% → p≤0.10；否則 0.5。
    """
    if df not in _CHI2_UPPER:
        return None
    c10, c5, c1 = _CHI2_UPPER[df]
    if stat >= c1:
        return 0.01
    if stat >= c5:
        return 0.05
    if stat >= c10:
        return 0.10
    return 0.50


def autocorr(x: np.ndarray, lag: int) -> float:
    """樣本自相關係數 ρ_k（除以 lag-0 變異，標準定義）。"""
    n = len(x)
    if n <= lag or n < 2:
        return float("nan")
    xm = x - x.mean()
    denom = np.sum(xm * xm)
    if denom == 0:
        return float("nan")
    num = np.sum(xm[lag:] * xm[:-lag])
    return float(num / denom)


def ljung_box(values, lags: int = 10) -> Optional[dict]:
    """Ljung-Box Q 檢定：H0 = 前 lags 階自相關全為 0（白噪音）。

    Q = n(n+2) Σ_{k=1..h} ρ_k²/(n-k)，漸近 χ²(h)。Q 顯著大 → 拒絕白噪音。
    同時回傳 lag-1..lag-5 各階 ρ_k 與低階 ρ 加權和符號，供 caller 判定**正**自相關。
    """
    x = _clean(values)
    n = len(x)
    h = min(lags, n - 1)
    if n < 8 or h < 1:
        return None
    rhos = [autocorr(x, k) for k in range(1, h + 1)]
    if any(math.isnan(r) for r in rhos):
        return None
    q = n * (n + 2) * sum((rhos[k - 1] ** 2) / (n - k) for k in range(1, h + 1))
    p = _chi2_pvalue_bucket(q, h)
    low_order = rhos[: min(5, len(rhos))]
    rho_sum_low = float(sum(low_order))
    return {
        "lags": h,
        "q_stat": float(q),
        "p_value_upper_bound": p,
        "rho_by_lag": [round(r, 5) for r in rhos],
        "rho_sum_low_order": round(rho_sum_low, 5),
        "rho_1": round(rhos[0], 5),
        "significant": (p is not None and p <= 0.05),
        "positive_autocorr": (p is not None and p <= 0.05 and rho_sum_low > 0),
    }


def jarque_bera(values) -> Optional[dict]:
    """Jarque-Bera 常態性檢定：JB = n/6 (S² + (K-3)²/4)，漸近 χ²(2)。

    為什麼必拒 normality：crypto 報酬厚尾 + 偏態，常態 z-test 高估顯著性
    （協議 §4.1）。拒絕 → 後續用 PSR/DSR（skew-kurt aware）而非 normal z-test。
    K 為**非超額**峰度（normal=3）。
    """
    x = _clean(values)
    n = len(x)
    if n < 8:
        return None
    mu = x.mean()
    sd = x.std(ddof=0)
    if sd == 0:
        return None
    z = (x - mu) / sd
    skew = float(np.mean(z ** 3))
    kurt = float(np.mean(z ** 4))  # 非超額峰度
    jb = (n / 6.0) * (skew ** 2 + ((kurt - 3.0) ** 2) / 4.0)
    p = _chi2_pvalue_bucket(jb, 2)
    return {
        "jb_stat": round(jb, 4),
        "skewness": round(skew, 4),
        "kurtosis": round(kurt, 4),
        "excess_kurtosis": round(kurt - 3.0, 4),
        "p_value_upper_bound": p,
        "reject_normality_5pct": bool(p is not None and p <= 0.05),
        "fat_tailed": bool(kurt > 3.0),
    }


def arch_lm(values, lags: int = 5) -> Optional[dict]:
    """Engle ARCH-LM 檢定 vol clustering：H0 = 無 ARCH 效應（殘差平方無自相關）。

    回歸 ε_t² 對其 lags，檢定 R²。LM = n·R² 漸近 χ²(lags)。顯著 → 有 vol clustering
    → 確認用 block bootstrap（非 IID）。
    """
    x = _clean(values)
    n = len(x)
    if n < lags + 8:
        return None
    e2 = (x - x.mean()) ** 2
    rows = len(e2) - lags
    if rows < 8:
        return None
    cols = [np.ones(rows)]
    for i in range(1, lags + 1):
        cols.append(e2[lags - i: lags - i + rows])
    X = np.column_stack(cols)
    y = e2[lags: lags + rows]
    # 為什麼包 errstate：numpy 2.4.4 在 lstsq/matmul 對病態/含 0 行的設計矩陣會發
    # divide-by-zero / overflow / invalid RuntimeWarning，但結果仍由下方有限性檢查把關。
    with np.errstate(all="ignore"):
        beta, _res, _rank, _sv = np.linalg.lstsq(X, y, rcond=None)
        pred = X @ beta
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    if ss_tot == 0:
        return None
    ss_res = float(np.sum((y - pred) ** 2))
    r2 = max(0.0, 1.0 - ss_res / ss_tot)
    lm = rows * r2
    p = _chi2_pvalue_bucket(lm, lags)
    return {
        "arch_lm_stat": round(lm, 4),
        "lags": lags,
        "r_squared": round(r2, 5),
        "p_value_upper_bound": p,
        "arch_effect_5pct": bool(p is not None and p <= 0.05),
    }


def _pca_effective_n_from_matrix(matrix: np.ndarray) -> Optional[dict]:
    """通用 PCA 有效獨立維度 N_eff = (Σλ)² / Σλ²（協議 §4.3 兩個 N_eff 共用核心）。

    matrix: shape (T, S)，T=時間（觀測）、S=symbol（橫截面欄）。對齊後 dropna。
    為什麼共用：price-return N_eff 與 funding-tiltscore N_eff 用同一公式，差別只在
    餵進來的矩陣（日報酬 vs 每 rebalance tiltscore）。
    """
    if matrix.ndim != 2:
        return None
    mask = np.all(np.isfinite(matrix), axis=1)
    m = matrix[mask]
    t, s = m.shape
    if t < s + 2 or s < 2:
        return None
    std = m.std(axis=0, ddof=1)
    std[std == 0] = np.nan
    z = (m - m.mean(axis=0)) / std
    z = z[:, np.all(np.isfinite(z), axis=0)]
    if z.shape[1] < 2:
        return None
    corr = np.corrcoef(z, rowvar=False)
    eig = np.linalg.eigvalsh(corr)
    eig = np.clip(eig, 0.0, None)
    s_lambda = float(np.sum(eig))
    s_lambda2 = float(np.sum(eig ** 2))
    if s_lambda2 == 0:
        return None
    n_eff = (s_lambda ** 2) / s_lambda2
    eig_desc = np.sort(eig)[::-1]
    pc1_share = float(eig_desc[0] / s_lambda) if s_lambda > 0 else None
    return {
        "n_columns": int(z.shape[1]),
        "n_eff": round(float(n_eff), 3),
        "pc1_explained_share": round(pc1_share, 4) if pc1_share is not None else None,
        "eigenvalues_desc": [round(float(e), 4) for e in eig_desc[:8]],
        "window_rows": int(t),
    }


def pca_effective_n(return_matrix: np.ndarray) -> Optional[dict]:
    """price-return PCA 有效獨立維度（§4.3：裸價格方向風險集中度）。

    為什麼關鍵：20 個高相關 crypto perp 不是 20 個獨立樣本（PC1 通常是 BTC beta）。
    funding-tilt long-short 雖剝離 PC1，但裸 price-return N_eff 仍是「price-side
    集中度」的參考（trend 實測 ≈2.087）。return_matrix: shape (T, S) 日報酬矩陣。
    """
    return _pca_effective_n_from_matrix(return_matrix)


def funding_tiltscore_pca_effective_n(tiltscore_matrix: np.ndarray) -> Optional[dict]:
    """funding-tiltscore PCA 有效獨立維度（§4.3 新，回答 operator 核心問題）。

    為什麼與 price-return N_eff 並列：operator 直接問「cross-sectional funding 是否
    比 trend 的 price-return 更獨立」。本函數對「每 rebalance × 每 symbol 的 tiltscore」
    矩陣算 N_eff——若 funding 橫截面相關性低於 price-return，則 funding-tilt 比 trend
    更有 power（不同命題）。crypto funding 橫截面相關性高 → 須實證，不可假設。
    tiltscore_matrix: shape (R, S)，R=rebalance 時點、S=symbol。
    """
    return _pca_effective_n_from_matrix(tiltscore_matrix)


def sharpe(per_period_returns) -> Optional[float]:
    """每期 Sharpe（mean/std，未年化）。樣本 std (ddof=1)。"""
    x = _clean(per_period_returns)
    if len(x) < 2:
        return None
    sd = x.std(ddof=1)
    if sd == 0:
        return None
    return float(x.mean() / sd)


def annualized_sharpe(per_day_returns) -> Optional[float]:
    """年化 Sharpe = 日 Sharpe × √365（crypto 24/7，協議 §4.1 禁 ×252）。"""
    s = sharpe(per_day_returns)
    if s is None:
        return None
    return float(s * math.sqrt(ANNUALIZATION_DAYS))


def required_n_for_sharpe_delta(delta_sr: float = 0.5, alpha: float = 0.05, power: float = 0.80) -> int:
    """協議 §4.0 樣本量門檻：N_min ≈ ((z_{α/2}+z_β)/Δ)²（σ=1 標準化 Sharpe）。

    detect Sharpe Δ=0.5 在 α=0.05 雙尾 + power=0.80 下 → N_min≈31.4，但協議要求
    ≥60 獨立 trades 作保守門檻（cluster 縮減後）。本函數回理論值；harness 用 60 硬門檻。
    """
    z_a = 1.959964  # Φ⁻¹(0.975)
    z_b = 0.841621  # Φ⁻¹(0.80)
    if delta_sr <= 0:
        return 10 ** 9
    return int(math.ceil(((z_a + z_b) / delta_sr) ** 2))


def _newey_west_mean_tstat(x: np.ndarray, lag: int) -> Optional[float]:
    """單樣本均值是否顯著異於 0 的 HAC（Newey-West）t-stat。

    為什麼用 HAC 而非樸素 t：本檢定的觀測是「重疊持有期前瞻報酬」逐日滑動取樣，相鄰
    觀測重疊 → 序列自相關 → 樸素 SE 嚴重低估、t-stat 虛高。Newey-West 用 Bartlett
    權重的 long-run variance 修正重疊誘發的自相關（Newey-West 1987）。lag 取重疊長度。
    t = mean(x) / sqrt(LRV / n)，LRV = γ₀ + 2 Σ_{j=1..lag} (1 - j/(lag+1)) γ_j。
    """
    n = len(x)
    if n < 3:
        return None
    mu = float(x.mean())
    e = x - mu
    # 為什麼包 errstate：合成/極端量級報酬內積可能觸發 numpy 2.4.4 matmul overflow
    # RuntimeWarning，但下方 lrv 有限性與 ≤0 檢查已 fail-closed。
    with np.errstate(all="ignore"):
        gamma0 = float(e @ e) / n
        lrv = gamma0
        L = max(0, min(int(lag), n - 1))
        for j in range(1, L + 1):
            w = 1.0 - j / (L + 1.0)
            gamma_j = float(e[j:] @ e[:-j]) / n
            lrv += 2.0 * w * gamma_j
    # LRV 可能因強負自相關被修正成 ≤0（極端小樣本）→ 退回樸素變異避免除零/虛 inf。
    if not math.isfinite(lrv) or lrv <= 0:
        lrv = gamma0
        if lrv <= 0:
            return None
    se = math.sqrt(lrv / n)
    if se == 0 or not math.isfinite(se):
        return None
    # fail-closed 相對離散度護欄：se 相對序列量級可忽略 → 退化輸入（確定性 ramp /
    # 近常數）的 FP 噪音，t=mu/se 會是 ~1e16 garbage 並誤判 false-GO。退回 None。
    if se < _REL_DISPERSION_FLOOR * max(abs(mu), 1.0):
        return None
    return float(mu / se)


def funding_persistence_ljung_box(funding_by_symbol: dict, lags: int = 10) -> Optional[dict]:
    """funding 序列正自相關（§4.1 carry 統計基礎，預期 PASS）。

    為什麼：carry 因子的統計前提 = funding 有持續性（強自相關，與 price return 的
    近白噪音相反）。對每 symbol 的已實現 funding 序列跑 Ljung-Box，pool 全 symbol
    計「多少 symbol 有顯著正自相關」。無正自相關（罕見）→ NO-GO-A。
    funding_by_symbol: {symbol: ndarray[已實現 funding rate 序列（時序）]}。
    """
    if not funding_by_symbol:
        return None
    per_symbol: dict = {}
    n_positive = 0
    n_significant = 0
    n_evaluated = 0
    rho1_values: list = []
    for s, series in funding_by_symbol.items():
        arr = _clean(series)
        lb = ljung_box(arr, lags=lags) if len(arr) >= 8 else None
        if lb is None:
            per_symbol[s] = None
            continue
        n_evaluated += 1
        per_symbol[s] = {
            "rho_1": lb["rho_1"],
            "rho_sum_low_order": lb["rho_sum_low_order"],
            "significant": lb["significant"],
            "positive_autocorr": lb["positive_autocorr"],
        }
        if lb["positive_autocorr"]:
            n_positive += 1
        if lb["significant"]:
            n_significant += 1
        if lb.get("rho_1") is not None:
            rho1_values.append(float(lb["rho_1"]))
    return {
        "lags": lags,
        "n_symbols_evaluated": n_evaluated,
        "n_symbols_positive_autocorr": n_positive,
        "n_symbols_significant": n_significant,
        "median_rho_1": round(float(np.median(rho1_values)), 5) if rho1_values else None,
        "per_symbol": per_symbol,
        # carry 基礎成立判定：funding 有 persistence 是 universe-wide 現象。
        "funding_has_positive_persistence": n_positive >= max(1, n_evaluated // 2),
    }


def funding_tilt_forward_significance(
    signed_forward_returns,
    *,
    overlap_lag: int,
) -> Optional[dict]:
    """pooled funding-tilt forward-return 顯著性 + HAC t-stat（§4.1 verdict 主檢定）。

    為什麼這是 verdict 主檢定（對標 trend 的 tsmom_significance）：問「funding-tiltscore
    對未來 net forward 報酬有無 cross-sectional 預測力」。signed_forward_returns 是
    pooled 全 (rebalance, symbol) 的「持倉方向 × 前瞻 net 報酬（分數）」序列（由 harness
    用 leak-free tertile 信號 + open-to-open 前瞻算好）。
    回 mean forward (bps) + hit rate + **overlap-corrected HAC t-stat**（lag=重疊持有期
    天數，修正逐日滑動取樣的重疊自相關，協議 §4.1）+ 樸素 t（僅對照）。
    決策語意：mean>0 且 HAC |t|≥2 → 顯著；否則無顯著 forward edge。
    """
    arr = _clean(signed_forward_returns)
    n = len(arr)
    if n < max(8, 2 * max(1, overlap_lag)):
        return {
            "n_obs": n,
            "insufficient": True,
            "note": "insufficient pooled forward observations",
        }
    mean_signed = float(arr.mean())
    hit_rate = float(np.mean(arr > 0))
    tstat = _newey_west_mean_tstat(arr, lag=overlap_lag)
    # 樸素 t（僅供對照，凸顯 overlap 修正影響；不作判定）。同相對離散度護欄。
    naive_t = None
    sd = arr.std(ddof=1)
    if sd > _REL_DISPERSION_FLOOR * max(abs(mean_signed), 1.0) and n > 1:
        naive_t = float(mean_signed / (sd / math.sqrt(n)))
    return {
        "n_obs": n,
        "overlap_lag": overlap_lag,
        "mean_forward_bps": round(mean_signed * 1e4, 4),
        "hit_rate": round(hit_rate, 4),
        "t_stat_hac": round(tstat, 4) if tstat is not None else None,
        "t_stat_naive_overlapping": round(naive_t, 4) if naive_t is not None else None,
        # 顯著正 forward edge：mean>0 且 HAC |t|≥2。
        "significant_positive": bool(
            tstat is not None and tstat >= 2.0 and mean_signed > 0),
    }
