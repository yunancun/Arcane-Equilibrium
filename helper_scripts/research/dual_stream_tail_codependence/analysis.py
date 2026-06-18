"""STEP 1-3 — 雙流尾部共依存決定性測試（純 1d kline，唯讀研究）。

MODULE_NOTE:
  模塊用途：用 market.klines 1d 兩年歷史（26 symbol，2024-06 → 2026-06，已含
    2024-08-05 carry unwind 與 2026-02-05 −14% 崩盤）構造兩條 leak-free 日策略流，
    量測它們在壓力下是否真正正交（Sharpe-additive）抑或同步崩（down-beta trap 換名）。
    這修正先前 axis (d) 被 44 日 demo-fills 窗（窗內零真崩盤）困住的根因——本測**不用
    demo fills**，兩流皆由 1d kline 純構造，故 tail co-dependence 第一次有真崩盤樣本。
  兩流（皆 shift(1) leak-free，net 成本 haircut）：
    - stream_F（managed-beta）：BTCUSDT 1d 上的 vol-target TSMOM。
      sign(trailing return, shift(1)) × inverse-realized-vol sizing(shift(1))。
      **禁** current-bar rolling max/min（repo trend.rs::donchian 有該 bug，不重用）。
    - stream_eps（cross-sectional market-neutral）：26-sym universe，每 symbol 日報酬
      對 BTC 做 rolling beta(shift(1)) 殘差化，殘差上做橫截面 z-score mean-reversion，
      dollar-neutral long/short book。
  量測（STEP 2）：Pearson+Spearman rho、下尾依存 lambda_L(q=5%,10%)、co-exceedance vs
    獨立期望、crash 子集條件 rho vs 全樣本 rho、2024-08-05 專項 stress、各流獨立的
    annualized Sharpe/Sortino/Calmar/maxDD + regime-split + PSR(0)（skew-kurt-aware）。
  pass/fail（STEP 3）：lambda_L<0.2 AND crash-subset rho 不顯著大於 full-sample
    AND 2024-08-05 無 co-blowup → "Sharpe-additive dual-stream" 可辯護；否則 REJECT。
  硬邊界（研究紅線）：
    - PG **唯讀**（set_session readonly），只 SELECT，絕不寫 production 表。
    - realized only；shift(1) everywhere；naive-vs-leakfree 雙軌，背離 >30% 旗標。
    - 不碰 runtime / order / risk / auth；不修 production engine 代碼。
    - **最終 verdict 不由本腳本下**——交 QC 在 MIT 審 leak-free 完整性後裁。
  依賴：psycopg2 / numpy / scipy（延遲 import）。
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

# 成本 haircut：1.3 bp/side（任務 SSOT，與 cost-bleed 報告 maker-leg 量級對齊）。
COST_BP_PER_SIDE = 1.3
# 年化因子（crypto 365 日連續交易）。
ANN = 365.0
# vol-target 年化目標（managed-beta 流）。
VOL_TARGET_ANN = 0.40
# stream_F 倉位上限（leverage clamp，避免低 vol 期爆倉）。
MAX_LEVERAGE = 3.0
# rolling lookback（日）。
TSMOM_LOOKBACK = 30      # trailing return 動量訊號窗
VOL_LOOKBACK = 30        # 已實現波動估計窗
BETA_LOOKBACK = 60       # 橫截面 beta 殘差化窗
ZSCORE_LOOKBACK = 20     # 殘差橫截面前的時間序列去均值窗（per-symbol）


def _connect():
    """連 PG（唯讀，fail-closed）。DSN 取 OPENCLAW_DATABASE_URL 或 secret 檔。"""
    import psycopg2

    dsn = os.environ.get("OPENCLAW_DATABASE_URL", "").strip()
    if not dsn:
        secret = Path("/tmp/openclaw/runtime_secrets/openclaw_database_url")
        if secret.is_file():
            dsn = secret.read_text(encoding="utf-8").strip()
    if not dsn:
        raise SystemExit("OPENCLAW_DATABASE_URL 未設定且 secret 檔不存在")
    conn = psycopg2.connect(dsn, application_name="dual_stream_tail")
    conn.set_session(readonly=True)
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = %s", (180000,))
    return conn


def load_daily_closes(conn) -> tuple[list[str], list[dt.date], np.ndarray]:
    """載入全 26 symbol 的 1d close 矩陣，對齊到公共日期軸。

    回傳 (symbols, dates, close_matrix[T, N])。缺值 = NaN（POLUSDT 早期等）。
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT symbol, ts::date AS d, close
            FROM market.klines
            WHERE timeframe = '1d'
            ORDER BY symbol, d
            """
        )
        rows = cur.fetchall()
    # 建 symbol × date 字典。
    by_sym: dict[str, dict[dt.date, float]] = {}
    all_dates: set[dt.date] = set()
    for sym, d, close in rows:
        by_sym.setdefault(sym, {})[d] = float(close)
        all_dates.add(d)
    symbols = sorted(by_sym.keys())
    dates = sorted(all_dates)
    mat = np.full((len(dates), len(symbols)), np.nan)
    date_idx = {d: i for i, d in enumerate(dates)}
    for j, sym in enumerate(symbols):
        for d, c in by_sym[sym].items():
            mat[date_idx[d], j] = c
    return symbols, dates, mat


def daily_log_returns(close_mat: np.ndarray) -> np.ndarray:
    """log 報酬（T-1 行）；不做 current-bar 任何前視操作。"""
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.log(close_mat[1:] / close_mat[:-1])
    r[~np.isfinite(r)] = np.nan
    return r


# ---------------------------------------------------------------------------
# stream_F — managed-beta：BTCUSDT vol-target TSMOM（leak-free shift(1)）
# ---------------------------------------------------------------------------
def build_stream_F(btc_ret: np.ndarray) -> np.ndarray:
    """vol-target TSMOM on BTC 日 log 報酬。

    為什麼 shift(1)：訊號與倉位**只能用截至昨日收盤可知的資訊**，否則前視洩漏。
      - 動量符號 = sign(sum(過去 TSMOM_LOOKBACK 日報酬, 截至 t-1))。
      - 倉位大小 = clamp(VOL_TARGET / 已實現vol(過去 VOL_LOOKBACK 日, 截至 t-1), 0, MAX_LEVERAGE)。
      - 當日 PnL = position_t × btc_ret_t。position_t 完全由 [.., t-1] 決定 → leak-free。
    禁 current-bar rolling max/min（donchian bug）：此處只用 trailing sum / std，
      且**嚴格 shift(1)**（t 期倉位用到 t-1 為止的窗），無當期 bar 進入訊號。
    回傳長度 = len(btc_ret)；前 max(lookback) 期因窗不足 = 0 倉（NaN→0）。
    """
    T = len(btc_ret)
    pos = np.zeros(T)
    for t in range(T):
        lb_end = t  # 截至 t-1（不含 t）的窗：索引 [t-LB, t-1] = btc_ret[max(0,t-LB):t]
        mom_win = btc_ret[max(0, t - TSMOM_LOOKBACK):t]
        vol_win = btc_ret[max(0, t - VOL_LOOKBACK):t]
        if mom_win.size < TSMOM_LOOKBACK or vol_win.size < VOL_LOOKBACK:
            continue
        mom = np.nansum(mom_win)
        sgn = 1.0 if mom > 0 else (-1.0 if mom < 0 else 0.0)
        rv_daily = np.nanstd(vol_win, ddof=1)
        rv_ann = rv_daily * math.sqrt(ANN)
        if not np.isfinite(rv_ann) or rv_ann <= 1e-9:
            continue
        size = VOL_TARGET_ANN / rv_ann
        size = float(np.clip(size, 0.0, MAX_LEVERAGE))
        pos[t] = sgn * size
    # gross 日 PnL（fraction）。
    gross = pos * np.nan_to_num(btc_ret, nan=0.0)
    # 成本 haircut：turnover = |pos_t - pos_{t-1}|，每單位 turnover 收 2×side cost。
    turnover = np.abs(np.diff(pos, prepend=0.0))
    cost = turnover * (COST_BP_PER_SIDE * 1e-4)
    return gross - cost


# ---------------------------------------------------------------------------
# stream_eps — cross-sectional market-neutral residual book（leak-free）
# ---------------------------------------------------------------------------
def build_stream_eps(
    returns: np.ndarray, btc_col: int
) -> tuple[np.ndarray, np.ndarray]:
    """橫截面 BTC-殘差 z-score mean-reversion，dollar-neutral long/short。

    為什麼 leak-free：
      1. per-symbol rolling beta vs BTC：cov(sym, btc) / var(btc)，窗 = [t-BETA_LB, t-1]
         （**shift(1)**，不含當期 t）。
      2. 殘差 resid_t = ret_t - beta_{t-1} * btc_ret_t（扣掉已知 beta 的當期市場曝險）。
      3. 訊號 = 橫截面 z-score of (per-symbol 去均值殘差動量, 截至 t-1)；mean-reversion =
         做空近期殘差贏家、做多輸家。權重 dollar-neutral（sum=0）、gross 歸一（sum|w|=1）。
      4. 當日 book PnL = sum_j w_{j,t} * ret_{j,t}。w 完全由 [.., t-1] 決定 → leak-free。
    回傳 (pnl[T], weights[T, N])。
    """
    T, N = returns.shape
    pnl = np.zeros(T)
    weights = np.zeros((T, N))
    btc = returns[:, btc_col]
    for t in range(T):
        if t < BETA_LOOKBACK + ZSCORE_LOOKBACK:
            continue
        # ---- 1. rolling beta（shift(1)，窗不含 t）----
        bwin = btc[t - BETA_LOOKBACK:t]
        if np.count_nonzero(np.isfinite(bwin)) < BETA_LOOKBACK // 2:
            continue
        var_b = np.nanvar(bwin, ddof=1)
        if not np.isfinite(var_b) or var_b <= 1e-12:
            continue
        betas = np.full(N, np.nan)
        for j in range(N):
            swin = returns[t - BETA_LOOKBACK:t, j]
            mask = np.isfinite(swin) & np.isfinite(bwin)
            if np.count_nonzero(mask) < BETA_LOOKBACK // 2:
                continue
            cov = np.cov(swin[mask], bwin[mask], ddof=1)[0, 1]
            betas[j] = cov / var_b
        # ---- 2. 殘差動量訊號（用截至 t-1 的殘差，shift(1)）----
        # 殘差 = ret - beta*btc，逐日；訊號取過去 ZSCORE_LOOKBACK 日殘差和（截至 t-1）。
        sig = np.full(N, np.nan)
        for j in range(N):
            if not np.isfinite(betas[j]):
                continue
            rwin = returns[t - ZSCORE_LOOKBACK:t, j]
            bwin2 = btc[t - ZSCORE_LOOKBACK:t]
            resid_win = rwin - betas[j] * bwin2
            if np.count_nonzero(np.isfinite(resid_win)) < ZSCORE_LOOKBACK // 2:
                continue
            sig[j] = np.nansum(resid_win)
        valid = np.isfinite(sig)
        if np.count_nonzero(valid) < 4:
            continue
        # ---- 3. 橫截面 z-score → mean-reversion 權重（dollar-neutral, gross-normalized）----
        sv = sig[valid]
        z = (sv - sv.mean()) / (sv.std(ddof=1) + 1e-12)
        raw = -z  # mean-reversion：贏家做空、輸家做多
        raw = raw - raw.mean()  # dollar-neutral（sum=0）
        gnorm = np.sum(np.abs(raw))
        if gnorm <= 1e-12:
            continue
        w = raw / gnorm  # gross-normalized（sum|w|=1）
        weights[t, valid] = w
        # ---- 4. 當日 book PnL ----
        rt = returns[t, valid]
        rt = np.nan_to_num(rt, nan=0.0)
        pnl[t] = float(np.dot(w, rt))
    # 成本 haircut：turnover = sum_j |w_{j,t} - w_{j,t-1}|，每單位 turnover 收 side cost。
    turnover = np.sum(np.abs(np.diff(weights, axis=0, prepend=np.zeros((1, N)))), axis=1)
    cost = turnover * (COST_BP_PER_SIDE * 1e-4)
    return pnl - cost, weights


# ---------------------------------------------------------------------------
# 風險調整指標
# ---------------------------------------------------------------------------
def perf_stats(pnl: np.ndarray) -> dict:
    """annualized Sharpe / Sortino / Calmar / maxDD + PSR(0) skew-kurt-aware。"""
    from scipy import stats as sps

    r = pnl[np.isfinite(pnl)]
    r = r[r != 0.0] if np.count_nonzero(r) > 0 else r  # 去除全 0 暖機期影響均值
    # 用含 0 的完整序列算累積/DD，但統計矩用非零（暖機 0 倉不是真實虧損也不是收益）。
    full = pnl[np.isfinite(pnl)]
    n = full.size
    if n < 30 or full.std() == 0:
        return {"n": int(n), "insufficient": True}
    mu = full.mean()
    sd = full.std(ddof=1)
    sharpe_ann = (mu / sd) * math.sqrt(ANN) if sd > 0 else float("nan")
    downside = full[full < 0]
    dsd = math.sqrt(np.mean(downside ** 2)) if downside.size else float("nan")
    sortino_ann = (mu / dsd) * math.sqrt(ANN) if dsd and dsd > 0 else float("nan")
    # 累積（算術累加，PnL 已是日報酬量級）。
    equity = np.cumsum(full)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    max_dd = float(dd.min())  # 最深回撤（負）
    ann_ret = mu * ANN
    calmar = (ann_ret / abs(max_dd)) if max_dd < 0 else float("nan")
    # PSR(0)：skew-kurt-aware（非 normal-z）。SR_hat 用每期（非年化）Sharpe。
    sr = mu / sd if sd > 0 else 0.0
    skew = float(sps.skew(full))
    kurt = float(sps.kurtosis(full, fisher=False))  # 非超額峰度
    denom = math.sqrt(max(1e-12, 1 - skew * sr + ((kurt - 1) / 4.0) * sr ** 2))
    psr_z = (sr * math.sqrt(n - 1)) / denom
    psr = float(sps.norm.cdf(psr_z))
    return {
        "n": int(n),
        "mean_daily": float(mu),
        "std_daily": float(sd),
        "sharpe_ann": float(sharpe_ann),
        "sortino_ann": float(sortino_ann),
        "max_dd": max_dd,
        "calmar": float(calmar),
        "ann_ret": float(ann_ret),
        "skew": skew,
        "kurt": kurt,
        "psr_zero": psr,
    }


def regime_labels(btc_ret: np.ndarray) -> np.ndarray:
    """leak-free PIT regime：shift(1) 過去 TSMOM_LOOKBACK 日 BTC 趨勢；±2% chop band。

    為什麼 shift(1)：regime 標籤只能用截至 t-1 的資訊，否則用當期報酬給標籤 = 前視。
    回傳每期 'bull'/'down'/'chop'（前 lookback 期 = 'warmup'）。
    """
    T = len(btc_ret)
    out = np.array(["warmup"] * T, dtype=object)
    for t in range(T):
        win = btc_ret[max(0, t - TSMOM_LOOKBACK):t]
        if win.size < TSMOM_LOOKBACK:
            continue
        cum = np.nansum(win)
        if cum > 0.02:
            out[t] = "bull"
        elif cum < -0.02:
            out[t] = "down"
        else:
            out[t] = "chop"
    return out


def tail_codependence(f: np.ndarray, e: np.ndarray, q: float) -> dict:
    """下尾依存 lambda_L = P(e 最差 q% | f 最差 q%) + co-exceedance vs 獨立期望。"""
    mask = np.isfinite(f) & np.isfinite(e)
    fa, ea = f[mask], e[mask]
    n = fa.size
    f_thr = np.quantile(fa, q)
    e_thr = np.quantile(ea, q)
    f_tail = fa <= f_thr
    e_tail = ea <= e_thr
    n_f = int(f_tail.sum())
    co = int(np.sum(f_tail & e_tail))
    lam = (co / n_f) if n_f > 0 else float("nan")
    indep_exp = q * n_f  # 獨立下，F-tail 內 e 也 tail 的期望數
    return {
        "q": q,
        "n": int(n),
        "n_f_tail": n_f,
        "co_exceedance": co,
        "lambda_L": float(lam),
        "indep_expected_co": float(indep_exp),
    }


def main() -> None:
    from scipy import stats as sps

    conn = _connect()
    try:
        symbols, dates, close_mat = load_daily_closes(conn)
    finally:
        conn.close()

    btc_col = symbols.index("BTCUSDT")
    returns = daily_log_returns(close_mat)  # [T-1, N]
    ret_dates = dates[1:]  # 報酬對應到「當日」（close-to-close）
    btc_ret = returns[:, btc_col]

    # ---- 構造兩流 ----
    f = build_stream_F(btc_ret)
    e, weights = build_stream_eps(returns, btc_col)

    # ---- naive 對照（無 shift(1)：訊號用含當期窗）——僅供 leak 旗標 ----
    def build_F_naive(btc_ret):
        T = len(btc_ret); pos = np.zeros(T)
        for t in range(T):
            mom_win = btc_ret[max(0, t - TSMOM_LOOKBACK + 1):t + 1]  # 含當期 → 洩漏
            vol_win = btc_ret[max(0, t - VOL_LOOKBACK + 1):t + 1]
            if mom_win.size < TSMOM_LOOKBACK or vol_win.size < VOL_LOOKBACK:
                continue
            sgn = 1.0 if np.nansum(mom_win) > 0 else (-1.0 if np.nansum(mom_win) < 0 else 0.0)
            rv = np.nanstd(vol_win, ddof=1) * math.sqrt(ANN)
            if not np.isfinite(rv) or rv <= 1e-9: continue
            pos[t] = sgn * float(np.clip(VOL_TARGET_ANN / rv, 0, MAX_LEVERAGE))
        return pos * np.nan_to_num(btc_ret, nan=0.0)
    f_naive = build_F_naive(btc_ret)

    # leak 旗標：leak-free vs naive Sharpe 背離
    sf = perf_stats(f); sf_naive = perf_stats(f_naive)
    sh_lf = sf.get("sharpe_ann", float("nan"))
    sh_nv = sf_naive.get("sharpe_ann", float("nan"))
    leak_div = abs(sh_nv - sh_lf) / (abs(sh_lf) + 1e-9) if np.isfinite(sh_lf) else float("nan")

    # ---- STEP 2 量測（對齊兩流非暖機區）----
    active = (f != 0.0) & (e != 0.0) & np.isfinite(f) & np.isfinite(e)
    fa, ea = f[active], e[active]
    pear = float(np.corrcoef(fa, ea)[0, 1]) if fa.size > 2 else float("nan")
    spear = float(sps.spearmanr(fa, ea).statistic) if fa.size > 2 else float("nan")

    tail5 = tail_codependence(f[active], e[active], 0.05)
    tail10 = tail_codependence(f[active], e[active], 0.10)

    # crash 子集 vs 全樣本條件 rho
    btc_active = btc_ret[active]
    rv_series = np.array([
        np.nanstd(btc_ret[max(0, i - VOL_LOOKBACK):i], ddof=1) if i >= VOL_LOOKBACK else np.nan
        for i in range(len(btc_ret))
    ])[active]
    rv_decile = np.nanquantile(rv_series, 0.90)
    crash_mask = (btc_active < -0.05) | (rv_series >= rv_decile)
    full_rho = pear
    if np.count_nonzero(crash_mask) > 2:
        crash_rho = float(np.corrcoef(fa[crash_mask], ea[crash_mask])[0, 1])
    else:
        crash_rho = float("nan")
    calm_mask = ~crash_mask
    calm_rho = float(np.corrcoef(fa[calm_mask], ea[calm_mask])[0, 1]) if np.count_nonzero(calm_mask) > 2 else float("nan")

    # Fisher-z 顯著性檢定：crash_rho 是否顯著大於 full_rho
    def fisher_z(rho, n):
        rho = max(min(rho, 0.999999), -0.999999)
        return 0.5 * math.log((1 + rho) / (1 - rho)), 1.0 / math.sqrt(max(n - 3, 1))
    n_crash = int(np.count_nonzero(crash_mask))
    z_c, se_c = fisher_z(crash_rho, n_crash) if np.isfinite(crash_rho) else (float("nan"), float("nan"))
    z_f, se_f = fisher_z(full_rho, fa.size)
    if np.isfinite(z_c):
        z_diff = (z_c - z_f) / math.sqrt(se_c ** 2 + se_f ** 2)
        p_crash_gt_full = 1.0 - sps.norm.cdf(z_diff)  # 單尾：crash > full
    else:
        z_diff = p_crash_gt_full = float("nan")

    # ---- stress 視窗 helper（任一目標日的 +/-3 窗）----
    di = {d: i for i, d in enumerate(ret_dates)}
    # stream_eps 首個非暖機日（BETA_LOOKBACK+ZSCORE_LOOKBACK 之後才有倉位）。
    eps_active_idx = next((i for i in range(len(e)) if e[i] != 0.0), None)
    eps_active_date = str(ret_dates[eps_active_idx]) if eps_active_idx is not None else None

    def stress_window_for(target: dt.date) -> dict:
        win = []
        in_eps_warmup = False
        if target in di:
            ti = di[target]
            in_eps_warmup = (eps_active_idx is not None and ti < eps_active_idx)
            for off in range(-3, 4):
                k = ti + off
                if 0 <= k < len(ret_dates):
                    win.append({
                        "date": str(ret_dates[k]),
                        "btc_ret": float(btc_ret[k]),
                        "stream_F": float(f[k]),
                        "stream_eps": float(e[k]),
                        "eps_warmup": bool(eps_active_idx is not None and k < eps_active_idx),
                        "both_neg": bool(f[k] < 0 and e[k] < 0),
                    })
        return {"target": str(target), "window": win, "eps_in_warmup_at_target": in_eps_warmup}

    # 2024-08-05（任務指定）；eps 在此日仍暖機 → 旗標 + 改用首批 co-active 真崩盤。
    stress_0805 = stress_window_for(dt.date(2024, 8, 5))
    # 真正決定性的 co-active 崩盤：worst co-active day（2026-02-05 −15%）+ 首個 co-active 崩盤
    # （2024-08-27，緊接 carry-unwind 後的尾段）。
    stress_worst = stress_window_for(dt.date(2026, 2, 5))
    stress_first_coactive = stress_window_for(dt.date(2024, 8, 27))

    # ---- 50/50 combined：兩流在 co-active 窗各自標準化到單位日 vol 再等權 ----
    # 為什麼用 active 窗 std：暖機 0 倉不該污染 vol 估計，否則 combined cumsum 出現假性巨額 DD。
    # 單位說明：fn/en 是 z-scaled 日報酬（無量綱）。combined 的 maxDD 故為「標準差單位」
    #   的累積回撤，**不可**與單流 fraction-單位 maxDD 直接比較；要 apples-to-apples 比 maxDD，
    #   下面額外算「同樣 z-scaled 的單流 maxDD」（fn_active / en_active）供對照。
    f_std = fa.std(ddof=1) or 1.0
    e_std = ea.std(ddof=1) or 1.0
    fn_active = fa / f_std
    en_active = ea / e_std
    combined_active = 0.5 * fn_active + 0.5 * en_active
    s_combined = perf_stats(combined_active)
    s_F_zscaled = perf_stats(fn_active)
    s_eps_zscaled = perf_stats(en_active)
    # co-blowup 鐵則檢驗：combined z-scaled maxDD 是否「淺於」單流（diversification 真生效）
    #   還是「深於」最深單流（=尾部同步崩，分散失效）。
    coactive_maxdd_compare = {
        "combined_zscaled_maxdd": s_combined.get("max_dd"),
        "stream_F_zscaled_maxdd": s_F_zscaled.get("max_dd"),
        "stream_eps_zscaled_maxdd": s_eps_zscaled.get("max_dd"),
        "combined_deeper_than_worst_single": bool(
            np.isfinite(s_combined.get("max_dd", float("nan")))
            and s_combined.get("max_dd", 0) < min(
                s_F_zscaled.get("max_dd", 0), s_eps_zscaled.get("max_dd", 0))
        ),
    }

    # co-blowup 判定：在 worst co-active 崩盤日，兩流是否同號為負（= 尾部同步崩）。
    def coblowup_at(target: dt.date) -> dict | None:
        if target not in di:
            return None
        ti = di[target]
        in_warmup = (eps_active_idx is not None and ti < eps_active_idx)
        return {
            "date": str(target),
            "btc_ret": float(btc_ret[ti]),
            "stream_F": float(f[ti]),
            "stream_eps": float(e[ti]),
            "eps_in_warmup": in_warmup,
            "both_negative": bool((not in_warmup) and f[ti] < 0 and e[ti] < 0),
        }
    crash_co_blowup = coblowup_at(dt.date(2026, 2, 5))      # 決定性：worst co-active 崩盤
    co_blowup_0805 = coblowup_at(dt.date(2024, 8, 5))        # 旗標 eps 暖機
    co_blowup_0827 = coblowup_at(dt.date(2024, 8, 27))       # 首個 co-active 崩盤
    # 全 co-active 崩盤日同號虧損掃描（誠實統計，不只看單日）。
    coactive_crash_scan = []
    for i, d in enumerate(ret_dates):
        if eps_active_idx is not None and i >= eps_active_idx and np.isfinite(btc_ret[i]) and btc_ret[i] < -0.05:
            coactive_crash_scan.append({
                "date": str(d), "btc_ret": float(btc_ret[i]),
                "stream_F": float(f[i]), "stream_eps": float(e[i]),
                "both_negative": bool(f[i] < 0 and e[i] < 0),
            })
    n_coactive_crash = len(coactive_crash_scan)
    n_both_neg = sum(1 for x in coactive_crash_scan if x["both_negative"])

    # ---- regime split 各流 ----
    reg = regime_labels(btc_ret)
    reg_active = reg[active]
    regime_perf = {}
    for label in ("bull", "down", "chop"):
        m = reg_active == label
        if np.count_nonzero(m) >= 30:
            regime_perf[label] = {
                "stream_F": perf_stats(fa[m]),
                "stream_eps": perf_stats(ea[m]),
                "n_days": int(np.count_nonzero(m)),
            }
        else:
            regime_perf[label] = {"n_days": int(np.count_nonzero(m)), "insufficient": True}

    # ---- STEP 3 pass/fail ----
    # 注意：2024-08-05（任務指定）落在 stream_eps 暖機（首倉 2024-08-22），故該日 co-blowup 不可判；
    #   決定性 stress 改用 worst co-active 崩盤 2026-02-05（−15%），並佐以全 co-active 崩盤同號掃描。
    bar_lambda = (tail5["lambda_L"] < 0.2) and (tail10["lambda_L"] < 0.2)
    bar_crash_rho = (not np.isfinite(p_crash_gt_full)) or (p_crash_gt_full > 0.05)
    # co-blowup bar：worst co-active 崩盤不同號為負 AND co-active 崩盤同號比例 < 50%。
    bar_coblowup = (not (crash_co_blowup and crash_co_blowup["both_negative"])) and (
        n_coactive_crash == 0 or (n_both_neg / n_coactive_crash) < 0.5
    )
    all_pass = bool(bar_lambda and bar_crash_rho and bar_coblowup)

    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "params": {
            "cost_bp_per_side": COST_BP_PER_SIDE, "vol_target_ann": VOL_TARGET_ANN,
            "max_leverage": MAX_LEVERAGE, "tsmom_lookback": TSMOM_LOOKBACK,
            "vol_lookback": VOL_LOOKBACK, "beta_lookback": BETA_LOOKBACK,
            "zscore_lookback": ZSCORE_LOOKBACK,
        },
        "universe": {"n_symbols": len(symbols), "symbols": symbols,
                     "n_dates": len(ret_dates), "span": [str(ret_dates[0]), str(ret_dates[-1])]},
        "leak_check": {
            "stream_F_sharpe_leakfree": sh_lf, "stream_F_sharpe_naive": sh_nv,
            "divergence_ratio": leak_div, "flag_over_30pct": bool(np.isfinite(leak_div) and leak_div > 0.30),
        },
        "correlation": {"pearson": pear, "spearman": spear, "n_active": int(fa.size)},
        "tail_dependence": {"q05": tail5, "q10": tail10},
        "conditional_rho": {
            "full_sample_rho": full_rho, "calm_rho": calm_rho, "crash_rho": crash_rho,
            "delta_crash_minus_full": (crash_rho - full_rho) if np.isfinite(crash_rho) else None,
            "n_crash_days": n_crash,
            "fisher_z_diff": z_diff, "p_crash_gt_full": p_crash_gt_full,
            "crash_def": "BTC daily < -5% OR realized-vol top decile",
        },
        "stream_eps_activation": {"first_active_date": eps_active_date, "first_active_idx": eps_active_idx},
        "stress_2024_08_05": {
            "note": "stream_eps 在此日仍暖機（首倉 2024-08-22），故 eps PnL=0，co-blowup 不可判",
            "window": stress_0805["window"],
            "eps_in_warmup_at_target": stress_0805["eps_in_warmup_at_target"],
            "co_blowup": co_blowup_0805,
        },
        "stress_worst_coactive_2026_02_05": {
            "note": "worst co-active 崩盤（BTC −15% log），決定性 co-blowup 判定日",
            "window": stress_worst["window"], "co_blowup": crash_co_blowup,
        },
        "stress_first_coactive_2024_08_27": {
            "note": "首個 co-active 崩盤（carry-unwind 尾段）",
            "window": stress_first_coactive["window"], "co_blowup": co_blowup_0827,
        },
        "coactive_crash_scan": {
            "n_coactive_crash_days": n_coactive_crash,
            "n_both_negative": n_both_neg,
            "frac_both_negative": (n_both_neg / n_coactive_crash) if n_coactive_crash else None,
            "days": coactive_crash_scan,
        },
        "standalone_perf": {"stream_F": sf, "stream_eps": perf_stats(e), "combined_5050": s_combined},
        "coactive_maxdd_compare_zscaled": coactive_maxdd_compare,
        "regime_split": regime_perf,
        "pass_fail": {
            "bar_lambda_L_lt_0.2": bool(bar_lambda),
            "bar_crash_rho_not_sig_gt_full": bool(bar_crash_rho),
            "bar_no_coblowup_coactive_crashes": bool(bar_coblowup),
            "all_pass_sharpe_additive_defensible": all_pass,
        },
    }
    out_path = os.environ.get("DUAL_OUT", "/tmp/openclaw/dual_stream/analysis.json")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False, default=str)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
