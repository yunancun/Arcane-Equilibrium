"""純 numpy 統計檢定 — 多日 trend 診斷 harness 專用。

MODULE_NOTE:
  模塊用途：實作協議 §4.7 資料品質 5-test（ADF / KPSS / Ljung-Box / Jarque-Bera /
    ARCH-LM）+ §4.6 PCA effective N + §4.1 樣本量門檻所需的純數值統計。
  為什麼純 numpy 自實作（不用 statsmodels）：Linux runtime（trade-core）只有
    numpy 2.4.4 + pandas，無 scipy / statsmodels。harness 必須能在 authoritative
    Linux PG 機器跑，故所有檢定純 numpy 重寫；卡方/常態臨界值用查表（避免 scipy）。
  主要函數：
    - ``ljung_box`` — 日尺度正自相關檢定（已降級為 data_quality 廣度統計；verdict 依據
      改為 harness 的正確尺度 TSMOM coherence gate → NO-GO-TREND，見 FIX-2）。
    - ``adf_test`` / ``kpss_test`` — 平穩性（單根 vs 趨勢平穩）。
    - ``jarque_bera`` — 常態性（crypto 厚尾必拒 → 後續用 PSR 非 normal z-test）。
    - ``arch_lm`` — vol clustering（ARCH 效應）。
    - ``pca_effective_n`` — N_eff≈(Σλ)²/Σλ²（20 高相關 symbol 的真實獨立維度）。
    - ``sharpe`` / ``annualized_sharpe`` — 年化 ×365（crypto 24/7，非 ×252）。
  硬邊界：所有檢定對 NaN / 樣本不足回傳 None（caller fail-closed），不偽造 p-value。
  注意：本模塊只做 math，import-time 零 DB / 零檔案 I/O（與 W2 metrics 同契約）。
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

# crypto 24/7：年化用 √365 而非 √252（協議 §4.8）。
ANNUALIZATION_DAYS = 365.0

# 相對離散度地板（fail-closed 顯著性護欄，re-E2 MEDIUM-1）。
# 為什麼需要：退化輸入（確定性 ramp / 近常數序列）的離散度 ≈0 但因浮點誤差非精確 0
#   （如 gamma0≈7.9e-31、se≈1.3e-16）。原 `lrv<=0→None` / `sd>0` 護欄只擋精確 0，
#   會被 FP 噪音繞過 → se 相對 |mu| 可忽略 → t≈mu/se≈1e16 garbage → 在「證偽優先」
#   harness 的**最壞方向**製造 false-GO（假顯著動量）。
# 修法：若 se 相對序列量級 max(|mu|,1) 可忽略（< 此相對閾值）→ 視為無有意義離散度、
#   不顯著，return None（fail-closed）。確定性 ramp / 近常數 → 不顯著、不 false-GO。
# 閾值取 1e-9：遠大於 FP round-off（~1e-15 量級）、遠小於任何真實報酬序列的相對 SE，
#   故只攔退化輸入、不誤殺真實樣本。
_REL_DISPERSION_FLOOR = 1e-9

# χ² 上尾臨界值查表（避免依賴 scipy.stats.chi2）。key=自由度 df，value=(p0.10, p0.05, p0.01)。
# 來源：標準 χ² 分布表。harness 用 df∈{1..20} 範圍（Ljung-Box lags / ARCH lags）。
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

# ADF 臨界值（含截距、無趨勢，"c" 模型）— MacKinnon (2010) 大樣本近似。
# 為什麼硬編碼：無 scipy/statsmodels；這是標準教科書值，用於與 ADF t-stat 比較。
# 拒絕 H0（有單根）需 t-stat < 臨界值（更負）。
_ADF_CRIT_C = {0.01: -3.43, 0.05: -2.86, 0.10: -2.57}

# KPSS 臨界值（level-stationary，"c" 模型）— Kwiatkowski et al. (1992) Table 1。
# 拒絕 H0（趨勢平穩）需 LM-stat > 臨界值。
_KPSS_CRIT_C = {0.10: 0.347, 0.05: 0.463, 0.025: 0.574, 0.01: 0.739}


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

    為什麼是 trend 統計基礎：TSMOM 要 work，日報酬須有**正**自相關（動量持續）。
    Q = n(n+2) Σ_{k=1..h} ρ_k²/(n-k)，漸近 χ²(h)。Q 顯著大 → 拒絕白噪音。
    但 Ljung-Box 不分正負自相關，故同時回傳 lag-1..lag-5 各階 ρ_k 與「ρ 加權和符號」
    供 caller 判定**正**自相關。注意：此為日尺度（次日）統計，已降級為 data_quality
    廣度報告；verdict 依據改為正確尺度 TSMOM coherence gate（NO-GO-TREND，FIX-2）。
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
    # 正自相關判定：低階（1-5）ρ 之和。trend 在低階應為正。
    low_order = rhos[: min(5, len(rhos))]
    rho_sum_low = float(sum(low_order))
    return {
        "lags": h,
        "q_stat": float(q),
        "p_value_upper_bound": p,
        "rho_by_lag": [round(r, 5) for r in rhos],
        "rho_sum_low_order": round(rho_sum_low, 5),
        "rho_1": round(rhos[0], 5),
        # 顯著（白噪音被拒）且低階 ρ 和為正 → 有正自相關（trend 基礎成立）。
        "significant": (p is not None and p <= 0.05),
        "positive_autocorr": (p is not None and p <= 0.05 and rho_sum_low > 0),
    }


def _ols_resid_and_tstat_on_last_coef(y: np.ndarray, X: np.ndarray) -> tuple[np.ndarray, float]:
    """OLS：回傳殘差與「最後一個係數」的 t-stat（純 numpy lstsq）。

    為什麼自實作：ADF/ARCH 都需要 OLS t-stat，但無 statsmodels。
    用 (X'X)^{-1} 的對角元算係數標準誤。
    """
    n, k = X.shape
    # 列縮放（避免 y_{t-1} 量級大時 X'X 病態 / overflow）。縮放後算 t-stat（比值
    # 對縮放不變），最後不需還原（t-stat = β/se 對 column scale 不變）。
    col_norm = np.sqrt(np.sum(X * X, axis=0))
    col_norm[col_norm == 0] = 1.0
    Xs = X / col_norm
    # 為什麼包 errstate：價格/報酬序列縮放後仍可能讓 lstsq/inv 觸發 numpy 2.4.4 的
    # divide-by-zero / overflow / invalid RuntimeWarning（病態 X'X），但 diag<0 與
    # se 有限性檢查已 fail-closed 回 NaN。抑制偽警告（協議 FIX-5）。
    with np.errstate(all="ignore"):
        beta, _res, _rank, _sv = np.linalg.lstsq(Xs, y, rcond=None)
        resid = y - Xs @ beta
        dof = n - k
        if dof <= 0:
            return resid, float("nan")
        sigma2 = float(resid @ resid) / dof
        try:
            xtx_inv = np.linalg.inv(Xs.T @ Xs)
        except np.linalg.LinAlgError:
            return resid, float("nan")
    diag = xtx_inv[-1, -1]
    if not math.isfinite(diag) or diag < 0:
        return resid, float("nan")
    se_last = math.sqrt(sigma2 * diag)
    if se_last == 0 or not math.isfinite(se_last):
        return resid, float("nan")
    return resid, float(beta[-1] / se_last)


def adf_test(values, max_lag: Optional[int] = None) -> Optional[dict]:
    """Augmented Dickey-Fuller 單根檢定（含截距，"c" 模型）。

    回歸：Δy_t = α + γ y_{t-1} + Σ δ_i Δy_{t-i} + ε_t。H0: γ=0（有單根，非平穩）。
    t-stat(γ) < 臨界值（更負）→ 拒絕 H0 → 平穩。價格序列預期非平穩（單根），
    報酬序列預期平穩。lag 數用 Schwert 法則上限。
    """
    x = _clean(values)
    n = len(x)
    if n < 20:
        return None
    if max_lag is None:
        max_lag = int(math.floor(12 * (n / 100.0) ** 0.25))
    max_lag = max(0, min(max_lag, n // 4))
    dy = np.diff(x)
    # 構造設計矩陣：截距 + y_{t-1} + lagged Δy。最後一個 regressor 必須是 y_{t-1}，
    # 因 _ols 回傳「最後係數」t-stat；故把 y_{t-1} 放最後一欄。
    start = max_lag
    rows = len(dy) - start
    if rows < 8:
        return None
    cols = [np.ones(rows)]
    for i in range(1, max_lag + 1):
        cols.append(dy[start - i: start - i + rows])
    cols.append(x[start: start + rows])  # y_{t-1}，最後一欄
    X = np.column_stack(cols)
    y = dy[start: start + rows]
    _resid, tstat = _ols_resid_and_tstat_on_last_coef(y, X)
    if math.isnan(tstat):
        return None
    reject_unit_root = tstat < _ADF_CRIT_C[0.05]
    return {
        "adf_tstat": round(tstat, 4),
        "used_lag": max_lag,
        "crit_5pct": _ADF_CRIT_C[0.05],
        "reject_unit_root_5pct": bool(reject_unit_root),
        "stationary": bool(reject_unit_root),
    }


def kpss_test(values, lags: Optional[int] = None) -> Optional[dict]:
    """KPSS 平穩性檢定（level-stationary，"c" 模型）。

    與 ADF 對偶：H0 = 趨勢平穩（與 ADF 的 H0 相反）。LM-stat > 臨界值 → 拒絕 H0 →
    非平穩。ADF + KPSS 並用可區分「確定性 vs 隨機趨勢」。
    LM = Σ S_t² / (n² σ̂²)，S_t = 部分和殘差，σ̂² = Newey-West 長期變異。
    """
    x = _clean(values)
    n = len(x)
    if n < 20:
        return None
    if lags is None:
        lags = int(math.floor(4 * (n / 100.0) ** 0.25))
    lags = max(1, min(lags, n - 1))
    resid = x - x.mean()
    s = np.cumsum(resid)
    eta = float(np.sum(s * s)) / (n * n)
    # Newey-West 長期變異估計。
    s0 = float(np.sum(resid * resid)) / n
    lrv = s0
    for lag in range(1, lags + 1):
        w = 1.0 - lag / (lags + 1.0)
        gamma = float(np.sum(resid[lag:] * resid[:-lag])) / n
        lrv += 2.0 * w * gamma
    if lrv <= 0:
        return None
    lm = eta / lrv
    reject_stationary = lm > _KPSS_CRIT_C[0.05]
    return {
        "kpss_lm": round(lm, 5),
        "used_lag": lags,
        "crit_5pct": _KPSS_CRIT_C[0.05],
        "reject_stationarity_5pct": bool(reject_stationary),
        "stationary": bool(not reject_stationary),
    }


def jarque_bera(values) -> Optional[dict]:
    """Jarque-Bera 常態性檢定：JB = n/6 (S² + (K-3)²/4)，漸近 χ²(2)。

    為什麼必拒 normality：crypto 報酬厚尾 + 偏態，常態 z-test 高估顯著性
    （協議 §4.3）。拒絕 → 後續用 PSR/DSR（skew-kurt aware）而非 normal z-test。
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
    （crypto 典型）→ 確認用 block bootstrap（非 IID）而非 IID 假設。
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
    # divide-by-zero / overflow / invalid RuntimeWarning（殘差平方量級大時），但結果仍由
    # 下方有限性檢查把關。抑制偽警告避免污染 research artifact 輸出（協議 FIX-5）。
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


def pca_effective_n(return_matrix: np.ndarray) -> Optional[dict]:
    """PCA 有效獨立維度 N_eff = (Σλ)² / Σλ²（協議 §4.6）。

    為什麼關鍵：20 個高相關 crypto perp 不是 20 個獨立樣本（PC1 通常是 BTC beta，
    解釋 50-70%）。N_eff 縮減 Step0 的有效 pooled trades；20 symbol 真實獨立維度
    預期 3-8。
    return_matrix: shape (T, S)，T=時間、S=symbol。對齊後（dropna）的日報酬矩陣。
    """
    if return_matrix.ndim != 2:
        return None
    # 去掉含 NaN 的列（保留所有 symbol 都有觀測的交集視窗）。
    mask = np.all(np.isfinite(return_matrix), axis=1)
    m = return_matrix[mask]
    t, s = m.shape
    if t < s + 2 or s < 2:
        return None
    # 標準化各 symbol 後算相關矩陣的特徵值。
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
        "n_symbols": int(z.shape[1]),
        "n_eff": round(float(n_eff), 3),
        "pc1_explained_share": round(pc1_share, 4) if pc1_share is not None else None,
        "eigenvalues_desc": [round(float(e), 4) for e in eig_desc[:8]],
        "window_rows": int(t),
    }


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
    """年化 Sharpe = 日 Sharpe × √365（crypto 24/7，協議 §4.8 禁 ×252）。"""
    s = sharpe(per_day_returns)
    if s is None:
        return None
    return float(s * math.sqrt(ANNUALIZATION_DAYS))


def required_n_for_sharpe_delta(delta_sr: float = 0.5, alpha: float = 0.05, power: float = 0.80) -> int:
    """協議 §4.1 樣本量門檻：N_min ≈ ((z_{α/2}+z_β)/Δ)²（σ=1 標準化 Sharpe）。

    detect Sharpe Δ=0.5 在 α=0.05 雙尾 + power=0.80 下 → z_{α/2}=1.96, z_β=0.84，
    N_min=((1.96+0.84)/0.5)²≈31.4，但協議要求 ≥60 獨立 trades 作保守門檻
    （cluster 縮減後）。本函數回理論值；harness 用協議的 60 作硬門檻。
    """
    z_a = 1.959964  # Φ⁻¹(0.975)
    z_b = 0.841621  # Φ⁻¹(0.80)
    if delta_sr <= 0:
        return 10 ** 9
    return int(math.ceil(((z_a + z_b) / delta_sr) ** 2))


def _newey_west_mean_tstat(x: np.ndarray, lag: int) -> Optional[float]:
    """單樣本均值是否顯著異於 0 的 HAC（Newey-West）t-stat。

    為什麼用 HAC 而非樸素 t：本檢定的觀測是「k 日前瞻報酬」逐日滑動取樣，相鄰觀測
    重疊 k-1 日 → 序列自相關 → 樸素 SE 嚴重低估、t-stat 虛高。Newey-West 用 Bartlett
    權重的 long-run variance 修正重疊誘發的自相關（overlapping-returns 標準修正，
    Newey-West 1987）。lag 取重疊長度 k-1。
    t = mean(x) / sqrt(LRV / n)，LRV = γ₀ + 2 Σ_{j=1..lag} (1 - j/(lag+1)) γ_j。
    """
    n = len(x)
    if n < 3:
        return None
    mu = float(x.mean())
    e = x - mu
    # 為什麼包 errstate：合成/極端量級報酬的內積可能觸發 numpy 2.4.4 matmul overflow
    # RuntimeWarning，但下方 lrv 有限性與 ≤0 檢查已 fail-closed。抑制偽警告（協議 FIX-5）。
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
    # fail-closed 相對離散度護欄（re-E2 MEDIUM-1）：se 相對序列量級可忽略 → 退化輸入
    # （確定性 ramp / 近常數）的 FP 噪音，t=mu/se 會是 ~1e16 garbage 並誤判 false-GO。
    # 退回「不顯著」（None），不讓無有意義變異的序列產出虛高顯著性。
    if se < _REL_DISPERSION_FLOOR * max(abs(mu), 1.0):
        return None
    return float(mu / se)


def tsmom_significance(
    close_by_symbol: dict,
    survivorship_by_symbol: Optional[dict],
    k: int,
) -> Optional[dict]:
    """正確時間尺度的多日 TSMOM 顯著性檢定（協議核心 FIX-2）。

    為什麼是 verdict 依據（取代 daily-lag Ljung-Box）：daily-lag(1-10) Ljung-Box 測
    「日報酬能否預測次日」（高頻），但 TSMOM(k=20-90) 賭「過去 k 日趨勢能否持續到
    未來 k 日」（低頻）。兩者時間尺度不同 → daily-LB 對慢趨勢無診斷力（MOP 2012：
    TSMOM 的日報酬同樣近白噪音，但 k 月尺度仍可有動量）。本檢定在**正確尺度**上問：
      過去 k 日報酬的「符號」是否預測未來 k 日報酬？

    對每 symbol、每個可算的日 t：
      lookback = ln(C_{t-1}/C_{t-1-k})（leak-free，只用 t-1 及更早）
      forward  = ln(C_{t+k}/C_t)（嚴格未來；feature 與 target 視窗不重疊）
      signed_fwd = sign(lookback) × forward
    pooled 全 symbol → 算 mean signed forward return（bps）+ hit rate（signed_fwd>0
    比例）+ **overlap-corrected t-stat**（Newey-West，lag=k-1，修正逐日滑動取樣的
    k-1 日重疊自相關）。同時報 n_eff = n_obs / k（非重疊有效樣本參考）。

    決策語意：mean>0 且 |t|≥2（HAC）→ 多日 momentum 在此尺度顯著；否則無顯著
    momentum（t<2 或 hit≈50% 或 mean 反轉為負）。t-stat 用 HAC 後對 N_eff 先天受限
    的 crypto 樣本仍可能無法達顯著 → 屬 power 限制（誠實標明，非高 power 反證）。
    """
    if not close_by_symbol or k < 2:
        return None
    signed_fwd_all: list = []
    lookback_pos = 0  # lookback>0 的觀測數（診斷 long/short 偏態）
    fwd_when_long: list = []
    fwd_when_short: list = []
    n_symbols_used = 0
    for s, close in close_by_symbol.items():
        c = np.asarray(close, dtype=float)
        n = len(c)
        if n < 2 * k + 2:
            continue
        surv = None
        if survivorship_by_symbol is not None:
            surv = np.asarray(survivorship_by_symbol.get(s), dtype=bool) if \
                survivorship_by_symbol.get(s) is not None else None
        used_any = False
        # t 範圍：需要 C_{t-1-k}（t≥k+1）與 C_{t+k}（t≤n-1-k）。
        for t in range(k + 1, n - k):
            c_prev = c[t - 1]
            c_prev_k = c[t - 1 - k]
            c_t = c[t]
            c_fwd = c[t + k]
            if not (np.isfinite(c_prev) and np.isfinite(c_prev_k) and
                    np.isfinite(c_t) and np.isfinite(c_fwd)):
                continue
            if c_prev <= 0 or c_prev_k <= 0 or c_t <= 0 or c_fwd <= 0:
                continue
            # 上市前不計（survivorship PIT）：進場日 t 與前瞻終點 t+k 都須已上市。
            if surv is not None and (not surv[t] or not surv[t + k]):
                continue
            lookback = np.log(c_prev / c_prev_k)
            forward = np.log(c_fwd / c_t)
            sgn = 1.0 if lookback > 0 else (-1.0 if lookback < 0 else 0.0)
            if sgn == 0.0:
                continue
            signed_fwd_all.append(sgn * forward)
            if sgn > 0:
                lookback_pos += 1
                fwd_when_long.append(forward)
            else:
                fwd_when_short.append(-forward)  # 做空：報酬 = -forward
            used_any = True
        if used_any:
            n_symbols_used += 1

    n_obs = len(signed_fwd_all)
    if n_obs < max(8, 2 * k):
        return {
            "k": k,
            "n_obs": n_obs,
            "n_symbols_used": n_symbols_used,
            "insufficient": True,
            "note": "insufficient non-pre-listing observations at this scale",
        }
    arr = np.asarray(signed_fwd_all, dtype=float)
    mean_signed = float(arr.mean())
    hit_rate = float(np.mean(arr > 0))
    # overlap-corrected t-stat：相鄰前瞻報酬重疊 k-1 日 → Newey-West lag=k-1。
    tstat = _newey_west_mean_tstat(arr, lag=k - 1)
    # 樸素 t（僅供對照，凸顯 overlap 修正的影響；不作判定）。
    # fail-closed 相對離散度護欄（re-E2 MEDIUM-1）：sd 相對 |mean_signed| 可忽略時
    # （退化/近常數序列的 FP 噪音）naive_t 會是 ~1e16 garbage，污染 artifact；視為
    # 無有意義離散度 → naive_t=None（與 HAC 同護欄，保持顯著性判定一致 fail-closed）。
    naive_t = None
    sd = arr.std(ddof=1)
    if sd > _REL_DISPERSION_FLOOR * max(abs(mean_signed), 1.0) and n_obs > 1:
        naive_t = float(mean_signed / (sd / math.sqrt(n_obs)))
    return {
        "k": k,
        "n_obs": n_obs,
        "n_eff_non_overlapping": round(n_obs / k, 2),
        "n_symbols_used": n_symbols_used,
        "mean_signed_fwd_bps": round(mean_signed * 1e4, 4),
        "hit_rate": round(hit_rate, 4),
        "t_stat_hac": round(tstat, 4) if tstat is not None else None,
        "t_stat_naive_overlapping": round(naive_t, 4) if naive_t is not None else None,
        "long_share": round(lookback_pos / n_obs, 4) if n_obs else None,
        "mean_long_fwd_bps": round(float(np.mean(fwd_when_long)) * 1e4, 4) if fwd_when_long else None,
        "mean_short_fwd_bps": round(float(np.mean(fwd_when_short)) * 1e4, 4) if fwd_when_short else None,
        # 顯著正動量：mean>0 且 HAC |t|≥2。
        "significant_positive_momentum": bool(
            tstat is not None and tstat >= 2.0 and mean_signed > 0),
    }


def _daily_log_returns(close) -> np.ndarray:
    """從收盤序列算 leak-safe 日對數報酬（剔除非正/非有限）。"""
    c = np.asarray(close, dtype=float)
    mask = np.isfinite(c) & (c > 0)
    cc = c[mask]
    if len(cc) < 3:
        return np.array([], dtype=float)
    return np.diff(np.log(cc))


def ljung_box_universe(close_by_symbol: dict, lags: int = 10) -> Optional[dict]:
    """per-symbol（全 universe）+ pooled Ljung-Box（協議 FIX-3 廣度）。

    為什麼補廣度：原 data_quality 只在 BTC 日報酬上算 Ljung-Box，無法說明「無正自相關」
    是 universe-wide 現象還是單一 symbol artifact。本函數對每個 symbol 各跑一次
    Ljung-Box，並 pool 全 symbol 的**去均值**日報酬跑一次，回報「多少 symbol 有顯著
    正自相關」。注意：Ljung-Box / 自相關仍是日報酬尺度的 data_quality 統計（補充而非
    verdict 依據；verdict 依據是 tsmom_significance 的正確尺度檢定）。
    pooled 去均值：各 symbol 報酬先減自身均值再串接，避免 cross-symbol 均值差污染
    自相關估計（pooled 仍是日尺度近似，僅作 universe 廣度旁證）。
    """
    if not close_by_symbol:
        return None
    per_symbol: dict = {}
    n_positive = 0
    n_significant = 0
    n_evaluated = 0
    pooled_demeaned: list = []
    rho1_values: list = []
    for s, close in close_by_symbol.items():
        rets = _daily_log_returns(close)
        lb = ljung_box(rets, lags=lags) if len(rets) >= 8 else None
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
        pooled_demeaned.append(rets - rets.mean())
    pooled_lb = None
    if pooled_demeaned:
        pooled = np.concatenate(pooled_demeaned)
        pooled_lb = ljung_box(pooled, lags=lags)
    return {
        "lags": lags,
        "n_symbols_evaluated": n_evaluated,
        "n_symbols_positive_autocorr": n_positive,
        "n_symbols_significant": n_significant,
        "median_rho_1": round(float(np.median(rho1_values)), 5) if rho1_values else None,
        "per_symbol": per_symbol,
        "pooled_demeaned": pooled_lb,
        # universe 廣度判定：有任一 symbol 顯著正自相關才算 universe 有 trend 基礎跡象。
        "universe_has_positive_autocorr": n_positive > 0,
    }
