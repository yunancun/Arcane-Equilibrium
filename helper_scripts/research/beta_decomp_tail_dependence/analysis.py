"""Axis (a) beta/residual PnL 分解 + Axis (d) 兩流尾部共依存（唯讀研究分析）。

MODULE_NOTE:
  模塊用途：以最廉價的決定性測試，回答「收割 managed-beta + 結合 cross-sectional
    market-neutral 是否為兩條正交、Sharpe-additive 的流」是否成立，抑或只是
    down-beta trap 換名。**只實作 axis (a) + (d)**，不建 conditioning-signal 搜索
    （該搜索 gated on 本測通過，由 QC 裁）。
  Axis (a) — 歷史 PnL 的 beta/residual 分解：
    每筆 demo round-trip 把 realized net_pnl_bps 對該筆持倉窗 [entry,exit] 的 BTC
    報酬（leak-free contained-bar，複用 residual producer 的 contained_bar_return_bps）
    做 OLS；報告 beta（b·BTC_ret）解釋的 PnL 變異比例、殘差 e 的均值 + 兩維 cluster
    （symbol × day）t-stat、leak-free vs naive 雙軌（確認無前視）。
  Axis (d) — 兩流尾部共依存（決定性部分）：
    - stream_F = managed-beta 日 PnL 代理 = constant-vol-target buy-and-hold BTC 日序列
      （leak-free，shift(1) sizing：用 t-1 為止的 realized vol 決定 t 日曝險）。
    - stream_ε = cross-sectional residual 日 PnL = 把 demo round-trips 經 BTC-residualize
      （複用 residual producer 的 bucket-by-exit + BTC-beta 殘差化）後的殘差 PnL 聚到日。
    在重疊日窗計算：Pearson + Spearman ρ（無條件，預期 ~0，不被其安撫）；下尾依存
    λ_L = P(ε 落最差 q% | F 落最差 q%)（q=5%、10%）；co-exceedance 計數 vs 獨立期望；
    crash 子集（BTC 日報酬 < −5% OR realized-vol 頂十分位）條件 ρ vs 全樣本 ρ；
    覆蓋的 crash 日 stress 表（兩流合併 PnL + max-DD + 是否同號爆掉）。
  Pass/fail bar（QC）：λ_L < 0.2 AND crash-subset ρ 不顯著大於 full-sample ρ AND 無
    任何覆蓋情境出現「兩流同號虧損超過單流 max-DD」→ 才談得上 Sharpe-additive。
  硬邊界（研究紅線）：
    - PG **唯讀**：conn.set_session(readonly=True)，只 SELECT。
    - leak-free shift(1) 鐵律：信號只用 t-1 及更早；禁 rolling 含 current bar；
      entry 在 next-bar open；每測同時算 naive vs leak-free 雙軌，背離 >30% 標警。
    - 不碰 runtime / order / risk / auth；不修 production engine 代碼。
    - 最終 verdict 不由本腳本下（QC 在 MIT 審 leak-free 完整性後裁）。
  依賴：numpy + psycopg2（延遲 import）；複用 ml_training.residual_alpha_producer_db
    （contained_bar_return_bps / bucket_round_trips_by_exit / bucketed_btc_factor /
    load_round_trips / load_btc_klines）+ realized_edge_stats（FIFO 配對）。
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys
from pathlib import Path

import numpy as np


def _resolve_srv_root() -> Path:
    """向上找含 program_code 的目錄（env 優先；不硬編碼 user path，§六）。"""
    env = os.environ.get("OPENCLAW_SRV_ROOT", "").strip()
    if env and (Path(env) / "program_code").is_dir():
        return Path(env)
    here = Path(__file__).resolve()
    for cand in [here, *here.parents]:
        if (cand / "program_code").is_dir():
            return cand
    cwd = Path.cwd()
    if (cwd / "program_code").is_dir():
        return cwd
    raise SystemExit("找不到 srv root（含 program_code 的目錄）；請設 OPENCLAW_SRV_ROOT")


_SRV_ROOT = _resolve_srv_root()
for _p in (str(_SRV_ROOT), str(_SRV_ROOT / "helper_scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from program_code.ml_training import residual_alpha_producer_db as rdb
    from program_code.ml_training import realized_edge_stats as res
except ModuleNotFoundError:  # pragma: no cover - 直跑 fallback
    from ml_training import residual_alpha_producer_db as rdb  # type: ignore
    from ml_training import realized_edge_stats as res  # type: ignore

BTC_SYMBOL = "BTCUSDT"
SINCE = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)  # demo fills 從 2026-04 才有
# Axis (d) constant-vol-target buy-and-hold 參數（leak-free）。
VOL_WINDOW = 30          # realized vol 視窗（日）
VOL_TARGET = 0.02        # 目標日波動（不 sweep；2% ≈ crypto 典型）
MAX_LEVERAGE = 3.0       # sizing clamp（防低 vol 時槓桿爆掉）
CRASH_RET_THRESHOLD = -0.05   # BTC 日報酬 < −5% 視為 crash 子集成員
TAIL_Q = (0.05, 0.10)    # 下尾依存 q


# ---------------------------------------------------------------------------
# 唯讀連線
# ---------------------------------------------------------------------------
def _connect():
    import psycopg2

    dsn = os.environ.get("OPENCLAW_DATABASE_URL", "")
    if not dsn:
        raise SystemExit("OPENCLAW_DATABASE_URL 未設定")
    conn = psycopg2.connect(dsn, application_name="beta_decomp_analysis")
    conn.set_session(readonly=True)
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = %s", (300000,))
    return conn


# ---------------------------------------------------------------------------
# 資料載入
# ---------------------------------------------------------------------------
def load_all_round_trips(conn) -> list:
    """所有 demo round-trips（FIFO 配對，net_pnl_bps 已扣費帶方向）。回 RoundTripRecord。"""
    from psycopg2.extras import RealDictCursor

    modes = res._engine_mode_scope("demo")
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(res._FILLS_QUERY, {"since": SINCE, "engine_modes": modes})
        fills = [dict(r) for r in cur.fetchall()]
    return [r for r in res._pair_round_trips(fills) if r.exit_ts is not None]


def load_btc_1m(conn, start_ts, end_ts) -> list:
    return rdb.load_btc_klines(conn, start_ts=start_ts, end_ts=end_ts, timeframe="1m")


def load_btc_1d(conn) -> list:
    """BTC 1d klines（[date, open, close]）供 stream_F 與 crash 子集。"""
    from psycopg2.extras import RealDictCursor

    out = []
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT ts::date AS d, open, close
            FROM market.klines
            WHERE symbol = %s AND timeframe = '1d'
            ORDER BY ts ASC
            """,
            (BTC_SYMBOL,),
        )
        for row in cur.fetchall():
            o = rdb._finite(row["open"])
            c = rdb._finite(row["close"])
            if o is None or c is None or o <= 0:
                continue
            out.append((row["d"], o, c))
    return out


# ---------------------------------------------------------------------------
# Axis (a) — beta/residual 分解
# ---------------------------------------------------------------------------
def _ols_with_clustered_se(y: np.ndarray, x: np.ndarray, sym_ids, day_ids) -> dict:
    """y = a + b·x + e 的 OLS，兩維 cluster（symbol × day）穩健 SE（Cameron-Gelbach-Miller）。

    為什麼兩維 cluster：同 symbol 的 trade 殘差相關（symbol cluster）、同日的 trade
    受同一市場衝擊（day cluster）；兩維 SE = V_sym + V_day − V_(sym,day)（CGM 2011），
    校正雙重計入的交集。純 numpy（無 statsmodels）。
    """
    n = len(y)
    X = np.column_stack([np.ones(n), x])  # [intercept, x]
    k = X.shape[1]
    XtX = X.T @ X
    try:
        XtX_inv = np.linalg.inv(XtX)
    except np.linalg.LinAlgError:
        return {"ok": False, "reason": "singular_XtX"}
    beta = XtX_inv @ (X.T @ y)
    resid = y - X @ beta

    def _cluster_meat(group_ids):
        meat = np.zeros((k, k))
        for g in np.unique(group_ids):
            idx = np.where(group_ids == g)[0]
            Xg = X[idx]
            ug = resid[idx]
            sg = Xg.T @ ug
            meat += np.outer(sg, sg)
        return meat

    sym_arr = np.asarray(sym_ids)
    day_arr = np.asarray(day_ids)
    # 交集 cluster id（symbol×day）。
    inter = np.array([f"{s}|{d}" for s, d in zip(sym_arr, day_arr)])
    meat = _cluster_meat(sym_arr) + _cluster_meat(day_arr) - _cluster_meat(inter)
    V = XtX_inv @ meat @ XtX_inv
    # 截距 = mean residual edge（x=0 時的預期 net_pnl_bps）。
    se = np.sqrt(np.clip(np.diag(V), 0.0, None))
    # PnL 變異被 beta 解釋的比例 = R²（單因子，b·x 與 total）。
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    ss_res = float(np.sum(resid ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    a_t = beta[0] / se[0] if se[0] > 0 else float("nan")
    b_t = beta[1] / se[1] if se[1] > 0 else float("nan")
    return {
        "ok": True,
        "n": n,
        "intercept_bps": float(beta[0]),
        "intercept_se": float(se[0]),
        "intercept_t": float(a_t),
        "beta": float(beta[1]),
        "beta_se": float(se[1]),
        "beta_t": float(b_t),
        "r2_beta_explained": float(r2),
        "mean_residual_bps": float(resid.mean()),
        "mean_net_pnl_bps": float(y.mean()),
        "n_sym_clusters": int(len(np.unique(sym_arr))),
        "n_day_clusters": int(len(np.unique(day_arr))),
    }


def axis_a(round_trips, btc_1m_bars) -> dict:
    """每筆 trade 把 net_pnl_bps 對其 [entry,exit] 窗 BTC 報酬回歸（leak-free + naive 雙軌）。"""
    btc_bars = btc_1m_bars
    y_list, x_leak, x_naive, sym_ids, day_ids = [], [], [], [], []
    n_no_btc = 0
    for rt in round_trips:
        entry = rdb.to_epoch_seconds(rt.entry_ts)
        exit_ = rdb.to_epoch_seconds(rt.exit_ts)
        net = rdb._finite(rt.net_pnl_bps)
        if entry is None or exit_ is None or net is None or exit_ <= entry:
            continue
        # leak-free：只用完全落在 [entry,exit] 內的 bar（contained-bar，無前視）。
        btc_ret_leak = rdb.contained_bar_return_bps(btc_bars, entry, exit_)
        # naive 對照：用同窗但容許跨界 bar（含 entry 前 / exit 後 partial）——
        # 放寬到 [entry - 60s, exit + 60s] 模擬「含 current bar」式洩漏，僅診斷。
        btc_ret_naive = rdb.contained_bar_return_bps(btc_bars, entry - 60.0, exit_ + 60.0)
        if btc_ret_leak is None:
            n_no_btc += 1
            continue
        y_list.append(net)
        x_leak.append(btc_ret_leak)
        x_naive.append(btc_ret_naive if btc_ret_naive is not None else btc_ret_leak)
        sym_ids.append(rt.symbol)
        day_ids.append(rt.entry_ts.date().isoformat())
    y = np.asarray(y_list, dtype=float)
    out = {
        "n_round_trips_in": len(round_trips),
        "n_aligned_with_btc": len(y),
        "n_dropped_no_btc_bar": n_no_btc,
    }
    if len(y) < 30:
        out["status"] = "insufficient_aligned"
        return out
    leak = _ols_with_clustered_se(y, np.asarray(x_leak), sym_ids, day_ids)
    naive = _ols_with_clustered_se(y, np.asarray(x_naive), sym_ids, day_ids)
    out["leak_free"] = leak
    out["naive"] = naive
    # 雙軌背離旗標（R² 差 >30% 視為強前視警告）。
    if leak.get("ok") and naive.get("ok"):
        r2l = leak["r2_beta_explained"]
        r2n = naive["r2_beta_explained"]
        out["dual_track_r2_divergence"] = abs(r2n - r2l)
        out["dual_track_flag_lookahead"] = bool(abs(r2n - r2l) > 0.30)
    return out


def axis_a_per_strategy(round_trips, btc_1m_bars) -> dict:
    """per-strategy 拆解（beta 解釋比例與殘差均值可能異質）。"""
    by_strat: dict[str, list] = {}
    for rt in round_trips:
        by_strat.setdefault(rt.strategy_name, []).append(rt)
    out = {}
    for strat, recs in by_strat.items():
        if len(recs) < 30:
            continue
        out[strat] = axis_a(recs, btc_1m_bars)
    return out


# ---------------------------------------------------------------------------
# Axis (d) — 兩流日序列
# ---------------------------------------------------------------------------
def build_stream_F_btc_voltarget(btc_1d) -> dict:
    """stream_F = constant-vol-target buy-and-hold BTC 日 PnL（leak-free，shift(1) sizing）。

    為什麼這個代理：operator 的「managed-beta」就是受控曝險的方向性 beta 流；
    最簡可辯護的代理 = 目標波動定倉的 buy-and-hold BTC。sizing 只用 t-1 為止的
    realized vol（shift(1)），entry 在 t 日（無前視）；日 PnL_t = size_{t} × r_t，
    size_t = clamp(VOL_TARGET / vol_{t-1}, 0, MAX_LEVERAGE)。
    回 {date_iso: pnl_frac}。
    """
    dates = [d for d, _o, _c in btc_1d]
    closes = np.array([c for _d, _o, c in btc_1d], dtype=float)
    t = len(closes)
    # 日對數報酬 r_t = ln(C_t / C_{t-1})。
    r = np.full(t, np.nan)
    r[1:] = np.log(closes[1:] / closes[:-1])
    # leak-free realized vol：vol_t 用 [t-VOL_WINDOW, t-1] 的報酬（不含 t）。
    out: dict[str, float] = {}
    for i in range(t):
        lo = i - VOL_WINDOW
        if lo < 1 or not np.isfinite(r[i]):
            continue
        seg = r[lo:i]  # 不含 r[i]（shift(1)）
        seg = seg[np.isfinite(seg)]
        if len(seg) < 5:
            continue
        vol = float(np.std(seg, ddof=1))
        if vol <= 0:
            continue
        size = min(VOL_TARGET / vol, MAX_LEVERAGE)
        out[dates[i].isoformat()] = size * float(r[i])
    return out


def build_stream_eps_residual_daily(round_trips, btc_1m_bars) -> dict:
    """stream_ε = cross-sectional residual 日 PnL（市場中性，扣 BTC beta）。

    複用 residual producer：把 round-trips 按 exit_ts 歸 4h bucket（非重疊，已實現於
    exit 無前視）→ 與同桶 BTC 報酬對齊 → 對 bucket 候選報酬做 BTC-beta 殘差化
    （e = candidate − b·BTC，b 由全樣本 OLS 估，與 residual producer 同形式）→ 殘差
    按 bucket 的 exit 日聚到日。回 {date_iso: residual_bps_sum}。

    為什麼用 round-trip 殘差而非 producer 的 gate verdict：axis (d) 要的是「市場中性
    殘差流的日 PnL 時間序列」，不是 promote/defer 判定；故取殘差化後的 per-bucket
    殘差再聚日，即 producer 殘差化核心的時間序列投影。
    """
    rts = [
        {"entry_ts": rdb.to_epoch_seconds(rt.entry_ts),
         "exit_ts": rdb.to_epoch_seconds(rt.exit_ts),
         "net_bps": rdb._finite(rt.net_pnl_bps)}
        for rt in round_trips
    ]
    rts = [r for r in rts if r["entry_ts"] and r["exit_ts"] and r["net_bps"] is not None]
    bucket_sec = rdb.DEFAULT_BUCKET_SEC
    cand, counts = rdb.bucket_round_trips_by_exit(rts, bucket_sec)
    factor = rdb.bucketed_btc_factor(btc_1m_bars, bucket_sec)
    aligned = sorted(set(cand) & set(factor))
    if len(aligned) < 10:
        return {"_status": "insufficient_aligned_buckets", "_n_aligned": len(aligned)}
    y = np.array([cand[b] for b in aligned], dtype=float)
    x = np.array([factor[b]["btc"] for b in aligned], dtype=float)
    # BTC-beta 殘差化（全樣本 OLS：e = y − (a + b·x)）。
    X = np.column_stack([np.ones(len(y)), x])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    # 殘差按 bucket 的 exit 日聚到日。
    daily: dict[str, float] = {}
    for b, e in zip(aligned, resid):
        d = dt.datetime.fromtimestamp(b, tz=dt.timezone.utc).date().isoformat()
        daily[d] = daily.get(d, 0.0) + float(e)
    daily["_beta_btc"] = float(beta[1])
    daily["_intercept_bps"] = float(beta[0])
    daily["_n_aligned_buckets"] = float(len(aligned))
    return daily


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Spearman ρ = Pearson ρ on ranks（純 numpy，平均秩處理 ties）。"""
    def rank(x):
        order = np.argsort(x, kind="mergesort")
        ranks = np.empty(len(x), dtype=float)
        ranks[order] = np.arange(1, len(x) + 1, dtype=float)
        # ties → 平均秩
        _, inv, counts = np.unique(x, return_inverse=True, return_counts=True)
        sums = np.zeros(len(counts))
        np.add.at(sums, inv, ranks)
        avg = sums / counts
        return avg[inv]
    ra, rb = rank(a), rank(b)
    return float(np.corrcoef(ra, rb)[0, 1])


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def axis_d(stream_F: dict, stream_eps: dict, btc_1d) -> dict:
    """兩流尾部共依存：Pearson/Spearman、λ_L、co-exceedance、crash-subset ρ、stress 表。"""
    eps_clean = {k: v for k, v in stream_eps.items() if not k.startswith("_")}
    common = sorted(set(stream_F) & set(eps_clean))
    out = {
        "n_days_F": len(stream_F),
        "n_days_eps": len(eps_clean),
        "n_overlap_days": len(common),
        "overlap_span": [common[0], common[-1]] if common else None,
        "residual_beta_diag": {k: stream_eps[k] for k in stream_eps if k.startswith("_")},
    }
    if len(common) < 20:
        out["status"] = "insufficient_overlap"
        return out
    F = np.array([stream_F[d] for d in common], dtype=float)
    E = np.array([eps_clean[d] for d in common], dtype=float)
    out["pearson_rho"] = _pearson(F, E)
    out["spearman_rho"] = _spearman(F, E)

    # 下尾依存 λ_L = P(E 在最差 q% | F 在最差 q%)。
    tail = {}
    for q in TAIL_Q:
        fq = np.quantile(F, q)
        eq = np.quantile(E, q)
        f_tail = F <= fq
        e_tail = E <= eq
        n_f = int(f_tail.sum())
        co = int((f_tail & e_tail).sum())
        lam = co / n_f if n_f > 0 else float("nan")
        # 獨立期望 co-exceedance = n_f * q（E 落最差 q% 的邊際機率 ≈ q）。
        exp_indep = n_f * q
        tail[f"q={q}"] = {
            "lambda_L": lam,
            "n_F_tail": n_f,
            "co_exceedance": co,
            "expected_if_independent": round(exp_indep, 3),
        }
    out["lower_tail_dependence"] = tail

    # crash 子集：BTC 日報酬 < −5% OR realized-vol 頂十分位。
    btc_ret_by_day, btc_vol_by_day = _btc_daily_ret_vol(btc_1d)
    rets = np.array([btc_ret_by_day.get(d, np.nan) for d in common])
    vols = np.array([btc_vol_by_day.get(d, np.nan) for d in common])
    finite_vol = vols[np.isfinite(vols)]
    vol_decile = np.quantile(finite_vol, 0.90) if len(finite_vol) > 10 else np.inf
    crash_mask = ((rets < CRASH_RET_THRESHOLD) | (vols >= vol_decile)) & np.isfinite(rets)
    out["crash_subset"] = {
        "n_crash_days": int(crash_mask.sum()),
        "btc_ret_lt_-5pct_days": int(np.sum((rets < CRASH_RET_THRESHOLD) & np.isfinite(rets))),
        "vol_top_decile_threshold": float(vol_decile) if np.isfinite(vol_decile) else None,
    }
    if crash_mask.sum() >= 5:
        out["crash_subset"]["pearson_rho_crash"] = _pearson(F[crash_mask], E[crash_mask])
        out["crash_subset"]["pearson_rho_full"] = out["pearson_rho"]
        out["crash_subset"]["delta_rho"] = (
            out["crash_subset"]["pearson_rho_crash"] - out["pearson_rho"]
        )
    else:
        out["crash_subset"]["note"] = "crash 日 <5，條件 ρ power 不足，誠實標 INCONCLUSIVE"

    # stress 表：覆蓋窗內每個 crash 日兩流合併 PnL（等權）+ 視窗 max-DD。
    combined = F + E  # 等權合併（兩流同單位前先標準化？保守用原值並標單位差異）
    # 單流 max-DD（cumulative）。
    out["stress"] = {
        "single_stream_F_max_dd": _max_drawdown(F),
        "single_stream_eps_max_dd": _max_drawdown(E),
        "combined_max_dd": _max_drawdown(combined),
        "note": (
            "F=vol-target BTC 日報酬(frac)、ε=residual 日 PnL(bps sum)，單位不同；"
            "stress 表逐 crash 日列兩流符號，combined DD 僅供同號性參考非可加 PnL"
        ),
        "crash_day_detail": [],
    }
    for i, d in enumerate(common):
        if crash_mask[i]:
            out["stress"]["crash_day_detail"].append({
                "date": d,
                "btc_ret": round(float(rets[i]), 4) if np.isfinite(rets[i]) else None,
                "stream_F": round(float(F[i]), 5),
                "stream_eps_bps": round(float(E[i]), 3),
                "both_negative": bool(F[i] < 0 and E[i] < 0),
            })
    # 「兩流同號虧損超過單流 max-DD」的 crash 情境判定。
    both_neg_days = [c for c in out["stress"]["crash_day_detail"] if c["both_negative"]]
    out["stress"]["n_crash_days_both_negative"] = len(both_neg_days)

    # ---- QC pass/fail bar 初判（不下最終 verdict，QC 在 MIT 審後裁） ----
    lam5 = tail.get("q=0.05", {}).get("lambda_L")
    lam10 = tail.get("q=0.1", {}).get("lambda_L")
    bar_lambda = (lam5 is not None and not math.isnan(lam5) and lam5 < 0.2) and \
                 (lam10 is not None and not math.isnan(lam10) and lam10 < 0.2)
    delta_rho = out["crash_subset"].get("delta_rho")
    # 「不顯著大於」粗判：crash ρ − full ρ < 0.2（無正式檢定，power 受限，標保守）。
    bar_crash_rho = (delta_rho is None) or (delta_rho < 0.2)
    bar_stress = (len(both_neg_days) == 0)
    out["preliminary_bars"] = {
        "lambda_L_below_0.2": bool(bar_lambda),
        "crash_rho_not_materially_higher": bool(bar_crash_rho),
        "no_crash_scenario_both_streams_lose": bool(bar_stress),
        "all_bars_pass": bool(bar_lambda and bar_crash_rho and bar_stress),
        "note": "初判，最終 verdict 由 QC 在 MIT 審 leak-free 完整性後下",
    }
    return out


def _btc_daily_ret_vol(btc_1d):
    dates = [d for d, _o, _c in btc_1d]
    closes = np.array([c for _d, _o, c in btc_1d], dtype=float)
    t = len(closes)
    r = np.full(t, np.nan)
    r[1:] = closes[1:] / closes[:-1] - 1.0
    ret_by_day = {dates[i].isoformat(): float(r[i]) for i in range(t) if np.isfinite(r[i])}
    vol_by_day = {}
    logr = np.full(t, np.nan)
    logr[1:] = np.log(closes[1:] / closes[:-1])
    for i in range(t):
        lo = i - VOL_WINDOW
        if lo < 1:
            continue
        seg = logr[lo:i + 1]
        seg = seg[np.isfinite(seg)]
        if len(seg) < 5:
            continue
        vol_by_day[dates[i].isoformat()] = float(np.std(seg, ddof=1))
    return ret_by_day, vol_by_day


def _max_drawdown(series: np.ndarray) -> float:
    cum = np.cumsum(series)
    peak = np.maximum.accumulate(cum)
    dd = cum - peak
    return float(dd.min()) if len(dd) else 0.0


# ---------------------------------------------------------------------------
# 主編排
# ---------------------------------------------------------------------------
def main() -> None:
    conn = _connect()
    try:
        round_trips = load_all_round_trips(conn)
        # BTC 1m 窗 = round-trips 的 entry 最早 → exit 最晚（含緩衝）。
        entries = [rt.entry_ts for rt in round_trips]
        exits = [rt.exit_ts for rt in round_trips if rt.exit_ts]
        start_ts = min(entries) - dt.timedelta(minutes=5)
        end_ts = max(exits) + dt.timedelta(minutes=5)
        btc_1m = load_btc_1m(conn, start_ts, end_ts)
        btc_1d = load_btc_1d(conn)
    finally:
        conn.close()

    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "n_round_trips": len(round_trips),
        "n_btc_1m_bars": len(btc_1m),
        "n_btc_1d_bars": len(btc_1d),
        "params": {
            "vol_window": VOL_WINDOW, "vol_target": VOL_TARGET,
            "max_leverage": MAX_LEVERAGE, "crash_ret_threshold": CRASH_RET_THRESHOLD,
            "tail_q": list(TAIL_Q), "bucket_sec": rdb.DEFAULT_BUCKET_SEC,
        },
    }
    # Axis (a)
    report["axis_a_pooled"] = axis_a(round_trips, btc_1m)
    report["axis_a_per_strategy"] = axis_a_per_strategy(round_trips, btc_1m)
    # Axis (d)
    stream_F = build_stream_F_btc_voltarget(btc_1d)
    stream_eps = build_stream_eps_residual_daily(round_trips, btc_1m)
    report["axis_d"] = axis_d(stream_F, stream_eps, btc_1d)

    out_path = os.environ.get("ANALYSIS_OUT", "/tmp/openclaw/beta_decomp/analysis.json")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False, default=str)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
