"""ma_crossover GROSS-edge reality test + execution-infra fix 量化（唯讀研究分析）。

MODULE_NOTE:
  模塊用途：回答決定性問題——cost-bleed 分解揭露 ma_crossover 有 +3.35 bps GROSS edge
    被 fee 吃掉（net 負）。本腳本判定那 +3.35 是「regime-independent 真 trend edge」
    還是「down-beta / regime artifact」（QC 先驗 t≈−0.59 結構性無 alpha）。
    **PART 1 是 gate**：若 GROSS edge 經 beta-中性化後消失 / 只在單一 regime 為正 →
    判 down-beta artifact、**STOP，不做 PART 2 的 wishful 成本反事實**。
    **PART 2 僅在 PART 1 通過時跑**：量化 taker-close→maker 反事實淨 bps（含真實成交率
    折損）+ turnover lever。本腳本只做 DIAGNOSIS，不實作任何 fix。
  PART 1 方法（全部 GROSS = 扣費前 realized PnL，來自 realized_pnl 真實成交價）：
    1. GROSS PnL mean + 兩維 cluster（symbol × day）t-stat + bootstrap 95% CI（cluster-block
       bootstrap by symbol，保留 symbol 內相關）。
    2. beta-中性化：GROSS PnL 對該筆 [entry,exit] 窗 BTC 報酬（leak-free contained-bar）OLS，
       報 alpha 截距（殘差 GROSS edge）+ 兩維 cluster t。alpha t 不顯著正 → down-beta。
    3. regime-split：以 leak-free PIT 標籤（shift(1) BTC 趨勢，**禁含 current bar 的 rolling
       max/min**）切 BTC-up / BTC-down / chop，逐 regime 報 GROSS edge。只在單一 regime 為正
       → down-beta / short-crash-insurance 指紋。
    4. long-leg vs short-leg：按 entry side（Buy=long / Sell=short）拆，看 GROSS edge 是否
       對稱，或集中在跌市做空（down-beta tell）。
  PART 2 方法（僅 PART 1 PASS 才跑）：
    - maker-close 反事實：把 ma_crossover taker close 腿的 fee 由 taker→maker，但用**post-05-18
      close-maker 真實成交率**（從已嘗試 maker close 的資料估 achievable fill rate），非 100%；
      未成交回退 taker。算 net bps/RT 是否翻正。
    - turnover lever：ma_crossover 是否過度交易（多低 edge RT）；只留高信心子集 net 是否改善。
  硬邊界（研究紅線）：
    - PG **唯讀**：conn.set_session(readonly=True)，只 SELECT。
    - leak-free：GROSS 為 realized-only；regime 標籤 shift(1) 禁 current bar；BTC 窗報酬用
      contained-bar（複用 residual producer，無前視）。naive vs leak-free 雙軌對照。
    - 不碰 runtime / order / risk / auth；不修 production engine 代碼。
    - 復用 production SSOT（realized_edge_stats FIFO 配對 / residual producer BTC 窗報酬），
      不另寫會 drift 的配對；只額外建 entry-side overlay（按 is_exit 同一分類重放）。
    - 最終 alpha-reality verdict 由 QC 下；本腳本給證據與初判。
  依賴：numpy + psycopg2（延遲 import）；複用 ml_training.realized_edge_stats（FIFO）
    + residual_alpha_producer_db（contained_bar_return_bps / load_btc_klines / to_epoch_seconds）。
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from collections import defaultdict
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
    from program_code.ml_training import realized_edge_stats as res
    from program_code.ml_training import residual_alpha_producer_db as rdb
except ModuleNotFoundError:  # pragma: no cover - 直跑 fallback
    from ml_training import realized_edge_stats as res  # type: ignore
    from ml_training import residual_alpha_producer_db as rdb  # type: ignore

BTC_SYMBOL = "BTCUSDT"
SINCE = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)  # demo fills 從 2026-04 才有
TARGET_STRATEGY = "ma_crossover"
ENGINE_MODE = "demo"
BOOTSTRAP_N = 5000
BOOTSTRAP_SEED = 20260617
# regime 標籤：以 shift(1) BTC 趨勢（不含 current bar）切 up/down/chop。
# 用該 round-trip entry 「前一日」為止的 BTC 趨勢（leak-free PIT）。
REGIME_TREND_WINDOW_DAYS = 5     # 趨勢視窗（日）
REGIME_CHOP_BAND = 0.01          # |累計報酬| < 1% 視為 chop
# PART 2 maker fee 假設（demo 實測中位數，動態取，此為 fallback）。
_FALLBACK_TAKER_FEE_BPS = 6.0
_FALLBACK_MAKER_FEE_BPS = 2.1


def _connect():
    import psycopg2

    dsn = os.environ.get("OPENCLAW_DATABASE_URL", "")
    if not dsn:
        raise SystemExit("OPENCLAW_DATABASE_URL 未設定")
    conn = psycopg2.connect(dsn, application_name="ma_crossover_edge_reality")
    conn.set_session(readonly=True)
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = %s", (300000,))
    return conn


def _f(v):
    if v is None:
        return None
    try:
        x = float(v)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _norm_ts(ts):
    if ts is None:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=dt.timezone.utc)
    return ts.astimezone(dt.timezone.utc)


# ---------------------------------------------------------------------------
# 資料載入
# ---------------------------------------------------------------------------
def load_round_trips_with_funding(conn) -> tuple[list, dict]:
    """復用 realized_edge_stats FIFO 配對 + funding 歸因，並建 entry-side overlay。

    entry-side overlay：以與 _pair_round_trips 完全相同的 is_exit 分類重放原始 fills，
    捕捉每筆 entry fill 的 side（Buy=long / Sell=short），鍵 (symbol, entry_ts)。
    為什麼可這樣對齊：RoundTripRecord.entry_ts == 配對到的 entry fill ts；同 symbol 同
    毫秒撞鍵機率極低（demo），撞鍵保留首見並計數（report 揭露）。
    """
    from psycopg2.extras import RealDictCursor

    modes = res._engine_mode_scope(ENGINE_MODE)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(res._FILLS_QUERY, {"since": SINCE, "engine_modes": modes})
        fills = [dict(r) for r in cur.fetchall()]
        cur.execute(res._FUNDING_QUERY, {"since": SINCE, "engine_modes": modes})
        funding_rows = [dict(r) for r in cur.fetchall()]

    # entry-side overlay：重放 is_exit 分類（與 SSOT 完全一致，不 drift）。
    entry_side: dict = {}
    side_collisions = 0
    for f in fills:
        strategy_name = f["strategy_name"]
        realized_pnl = float(f["realized_pnl"])
        is_exit = (
            realized_pnl != 0.0
            or strategy_name.startswith("risk_close")
            or strategy_name.startswith("stop_trigger")
            or strategy_name.startswith("strategy_close")
            or strategy_name.startswith("stop_")
            or strategy_name.startswith("time_stop")
        )
        if is_exit:
            continue
        key = (f["symbol"], _norm_ts(f["ts"]))
        if key in entry_side:
            side_collisions += 1
            continue
        entry_side[key] = (f.get("side") or "").lower()  # 'buy' / 'sell'
    entry_side["_collisions"] = side_collisions

    records = res._pair_round_trips(fills)
    res._attach_funding_to_records(records, funding_rows)
    return [r for r in records if r.exit_ts is not None], entry_side


def load_cost_meta(conn) -> dict:
    """per-fill cost overlay（fee_rate / role / close_maker_attempt / fallback）供 PART 2。"""
    from psycopg2.extras import RealDictCursor

    modes = res._engine_mode_scope(ENGINE_MODE)
    meta: dict = {}
    collisions = 0
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT symbol, ts, liquidity_role, fee_rate, exit_reason,
                   close_maker_attempt, close_maker_fallback_reason
            FROM trading.fills
            WHERE engine_mode = ANY(%(modes)s) AND ts >= %(since)s
              AND (strategy_name IS NULL OR strategy_name NOT LIKE 'unattributed:%%')
            """,
            {"modes": modes, "since": SINCE},
        )
        for row in cur.fetchall():
            key = (row["symbol"], _norm_ts(row["ts"]))
            if key in meta:
                collisions += 1
                continue
            meta[key] = {
                "role": row["liquidity_role"],
                "fee_rate_bps": (_f(row["fee_rate"]) or 0.0) * 10_000.0,
                "exit_reason": row["exit_reason"],
                "close_maker_attempt": row["close_maker_attempt"],
                "close_maker_fallback_reason": row["close_maker_fallback_reason"],
            }
    meta["_collisions"] = collisions
    return meta


def load_btc_1m(conn, start_ts, end_ts) -> list:
    return rdb.load_btc_klines(conn, start_ts=start_ts, end_ts=end_ts, timeframe="1m")


def load_btc_1d(conn) -> list:
    """BTC 1d klines（[date, open, close]）供 leak-free regime 標籤。"""
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
# 統計工具
# ---------------------------------------------------------------------------
def _two_way_cluster_t(y, x, sym_ids, day_ids) -> dict:
    """y = a + b·x + e 的 OLS，兩維 cluster（symbol × day）穩健 SE（Cameron-Gelbach-Miller）。

    若 x 為 None → 純截距模型（mean + cluster-SE），用於 GROSS edge mean 的 t-stat。
    為什麼兩維 cluster：同 symbol 殘差相關、同日受同一市場衝擊；V = V_sym + V_day − V_inter。
    """
    n = len(y)
    if x is None:
        X = np.ones((n, 1))
    else:
        X = np.column_stack([np.ones(n), x])
    k = X.shape[1]
    XtX = X.T @ X
    try:
        XtX_inv = np.linalg.inv(XtX)
    except np.linalg.LinAlgError:
        return {"ok": False, "reason": "singular_XtX"}
    beta = XtX_inv @ (X.T @ y)
    resid = y - X @ beta

    def _meat(group_ids):
        meat = np.zeros((k, k))
        for g in np.unique(group_ids):
            idx = np.where(group_ids == g)[0]
            Xg, ug = X[idx], resid[idx]
            sg = Xg.T @ ug
            meat += np.outer(sg, sg)
        return meat

    sym_arr = np.asarray(sym_ids)
    day_arr = np.asarray(day_ids)
    inter = np.array([f"{s}|{d}" for s, d in zip(sym_arr, day_arr)])
    meat = _meat(sym_arr) + _meat(day_arr) - _meat(inter)
    V = XtX_inv @ meat @ XtX_inv
    se = np.sqrt(np.clip(np.diag(V), 0.0, None))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    ss_res = float(np.sum(resid ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    out = {
        "ok": True, "n": n,
        "intercept_bps": float(beta[0]),
        "intercept_se": float(se[0]),
        "intercept_t": float(beta[0] / se[0]) if se[0] > 0 else float("nan"),
        "n_sym_clusters": int(len(np.unique(sym_arr))),
        "n_day_clusters": int(len(np.unique(day_arr))),
        "mean_y_bps": float(y.mean()),
    }
    if x is not None:
        out["beta"] = float(beta[1])
        out["beta_se"] = float(se[1])
        out["beta_t"] = float(beta[1] / se[1]) if se[1] > 0 else float("nan")
        out["r2_beta_explained"] = float(r2)
    return out


def _cluster_block_bootstrap_ci(y, sym_ids, n_boot=BOOTSTRAP_N, seed=BOOTSTRAP_SEED) -> dict:
    """cluster-block bootstrap 95% CI（by symbol，保留 symbol 內相關，不假設 iid）。"""
    rng = np.random.default_rng(seed)
    sym_arr = np.asarray(sym_ids)
    clusters = {}
    for i, s in enumerate(sym_arr):
        clusters.setdefault(s, []).append(i)
    cluster_keys = list(clusters.keys())
    cluster_idx = [np.asarray(clusters[k]) for k in cluster_keys]
    nC = len(cluster_keys)
    means = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, nC, size=nC)
        idx = np.concatenate([cluster_idx[p] for p in pick])
        means[b] = float(y[idx].mean())
    lo, hi = np.quantile(means, [0.025, 0.975])
    return {
        "mean_bps": float(y.mean()),
        "ci95_low_bps": float(lo),
        "ci95_high_bps": float(hi),
        "n_clusters": nC,
        "n_boot": n_boot,
        "excludes_zero": bool(lo > 0 or hi < 0),
    }


# ---------------------------------------------------------------------------
# leak-free PIT regime 標籤
# ---------------------------------------------------------------------------
def build_regime_labels(btc_1d) -> dict:
    """leak-free PIT 標籤：date → {'up','down','chop'}，用該日**之前** W 日 BTC 累計報酬。

    為什麼 shift(1)：標籤代表「進場當下可知的趨勢」。禁用含 current bar 的 rolling
    max/min（repo 既有 look-ahead bug）。trend_{d} = C_{d-1}/C_{d-1-W} − 1（完全用 d 之前）。
    """
    dates = [d for d, _o, _c in btc_1d]
    closes = np.array([c for _d, _o, c in btc_1d], dtype=float)
    t = len(closes)
    labels: dict = {}
    for i in range(t):
        # 用 d 之前（含 d-1，不含 d）的 W 日視窗：C_{i-1} / C_{i-1-W} − 1。
        j_end = i - 1
        j_start = i - 1 - REGIME_TREND_WINDOW_DAYS
        if j_start < 0 or j_end < 0:
            continue
        c_end, c_start = closes[j_end], closes[j_start]
        if c_start <= 0:
            continue
        trend = c_end / c_start - 1.0
        if trend > REGIME_CHOP_BAND:
            lab = "btc_up"
        elif trend < -REGIME_CHOP_BAND:
            lab = "btc_down"
        else:
            lab = "chop"
        labels[dates[i].isoformat()] = {"label": lab, "trend": float(trend)}
    return labels


def build_regime_labels_naive(btc_1d) -> dict:
    """naive 對照（**含 current bar**，故意洩漏）：trend_{d} = C_d / C_{d-W} − 1。

    僅供雙軌診斷：若 naive 與 leak-free 的 regime 分類大幅背離 → 標前視警告。
    """
    dates = [d for d, _o, _c in btc_1d]
    closes = np.array([c for _d, _o, c in btc_1d], dtype=float)
    t = len(closes)
    labels: dict = {}
    for i in range(t):
        j = i - REGIME_TREND_WINDOW_DAYS
        if j < 0:
            continue
        c_end, c_start = closes[i], closes[j]  # 含 current bar i（洩漏）
        if c_start <= 0:
            continue
        trend = c_end / c_start - 1.0
        if trend > REGIME_CHOP_BAND:
            lab = "btc_up"
        elif trend < -REGIME_CHOP_BAND:
            lab = "btc_down"
        else:
            lab = "chop"
        labels[dates[i].isoformat()] = lab
    return labels


# ---------------------------------------------------------------------------
# PART 1 — GROSS edge reality
# ---------------------------------------------------------------------------
def build_trade_frame(round_trips, entry_side, btc_1m, regime_leak, regime_naive) -> dict:
    """逐 ma_crossover round-trip 組裝 GROSS bps、entry side、BTC 窗報酬、regime 標籤。"""
    rows = []
    n_no_btc = 0
    n_no_regime = 0
    n_regime_disagree = 0
    for rt in round_trips:
        if rt.strategy_name != TARGET_STRATEGY:
            continue
        gross = rdb._finite(rt.gross_pnl_bps)
        if gross is None:
            continue
        entry = rdb.to_epoch_seconds(rt.entry_ts)
        exit_ = rdb.to_epoch_seconds(rt.exit_ts)
        if entry is None or exit_ is None or exit_ <= entry:
            continue
        btc_ret = rdb.contained_bar_return_bps(btc_1m, entry, exit_)
        # naive 窗報酬（放寬 ±60s 模擬含跨界 bar）— 雙軌診斷。
        btc_ret_naive = rdb.contained_bar_return_bps(btc_1m, entry - 60.0, exit_ + 60.0)
        side = entry_side.get((rt.symbol, _norm_ts(rt.entry_ts)), "")
        if side == "buy":
            leg = "long"
        elif side == "sell":
            leg = "short"
        else:
            leg = "unknown"
        eday = rt.entry_ts.date().isoformat()
        reg = regime_leak.get(eday)
        reg_label = reg["label"] if reg else None
        reg_naive = regime_naive.get(eday)
        if reg_label is None:
            n_no_regime += 1
        if reg_label is not None and reg_naive is not None and reg_label != reg_naive:
            n_regime_disagree += 1
        if btc_ret is None:
            n_no_btc += 1
        rows.append({
            "symbol": rt.symbol,
            "entry_day": eday,
            "gross_bps": gross,
            "net_bps": rt.net_pnl_bps,
            "entry_fee_bps": rt.entry_fee_bps,
            "exit_fee_bps": rt.exit_fee_bps,
            "fee_bps": rt.entry_fee_bps + rt.exit_fee_bps,
            "funding_bps": rt.funding_bps,
            "btc_ret_bps": btc_ret,
            "btc_ret_naive_bps": btc_ret_naive,
            "leg": leg,
            "regime": reg_label,
            "regime_naive": reg_naive,
            "entry_ts": _norm_ts(rt.entry_ts),
            "exit_ts": _norm_ts(rt.exit_ts),
        })
    return {
        "rows": rows,
        "n": len(rows),
        "n_no_btc_bar": n_no_btc,
        "n_no_regime_label": n_no_regime,
        "n_regime_naive_vs_leak_disagree": n_regime_disagree,
    }


def part1_gross_reality(frame) -> dict:
    """PART 1 全套：mean+t+CI / beta-中性化 alpha / regime-split / long-short split。"""
    rows = frame["rows"]
    out = {"n_round_trips": len(rows)}

    # ---- (1) GROSS mean + 兩維 cluster t + cluster-block bootstrap CI ----
    y = np.array([r["gross_bps"] for r in rows], dtype=float)
    sym = [r["symbol"] for r in rows]
    day = [r["entry_day"] for r in rows]
    out["gross_mean"] = _two_way_cluster_t(y, None, sym, day)
    out["gross_bootstrap_ci"] = _cluster_block_bootstrap_ci(y, sym)

    # ---- (2) beta-中性化：GROSS ~ a + b·BTC_window_return ----
    beta_rows = [r for r in rows if r["btc_ret_bps"] is not None]
    if len(beta_rows) >= 30:
        yb = np.array([r["gross_bps"] for r in beta_rows], dtype=float)
        xb = np.array([r["btc_ret_bps"] for r in beta_rows], dtype=float)
        symb = [r["symbol"] for r in beta_rows]
        dayb = [r["entry_day"] for r in beta_rows]
        out["beta_neutralized_leak_free"] = _two_way_cluster_t(yb, xb, symb, dayb)
        # naive 雙軌（含跨界 bar）。
        xn = np.array([
            r["btc_ret_naive_bps"] if r["btc_ret_naive_bps"] is not None else r["btc_ret_bps"]
            for r in beta_rows
        ], dtype=float)
        out["beta_neutralized_naive"] = _two_way_cluster_t(yb, xn, symb, dayb)
        a_leak = out["beta_neutralized_leak_free"].get("intercept_bps")
        a_naive = out["beta_neutralized_naive"].get("intercept_bps")
        out["beta_alpha_dual_track_divergence_bps"] = (
            abs(a_leak - a_naive) if (a_leak is not None and a_naive is not None) else None
        )
        out["n_aligned_with_btc"] = len(beta_rows)
    else:
        out["beta_neutralized_leak_free"] = {"ok": False, "reason": "insufficient_btc_aligned"}

    # ---- (3) regime-split（leak-free PIT 標籤） ----
    reg_groups = defaultdict(list)
    for r in rows:
        if r["regime"] is not None:
            reg_groups[r["regime"]].append(r)
    regime_out = {}
    for lab, recs in sorted(reg_groups.items()):
        yr = np.array([rr["gross_bps"] for rr in recs], dtype=float)
        symr = [rr["symbol"] for rr in recs]
        dayr = [rr["entry_day"] for rr in recs]
        stat = _two_way_cluster_t(yr, None, symr, dayr) if len(yr) >= 5 else {"ok": False, "reason": "n<5"}
        regime_out[lab] = {
            "n": len(recs),
            "gross_mean_bps": float(yr.mean()),
            "gross_median_bps": float(np.median(yr)),
            "net_mean_bps": float(np.mean([rr["net_bps"] for rr in recs])),
            "cluster_t": stat.get("intercept_t") if stat.get("ok") else None,
            "n_days": len(set(dayr)),
        }
    out["regime_split_leak_free"] = regime_out
    # regime 標籤分佈（誠實揭露樣本是否集中單一 regime）。
    out["regime_label_distribution"] = {
        k: v["n"] for k, v in regime_out.items()
    }

    # ---- (4) long-leg vs short-leg ----
    leg_groups = defaultdict(list)
    for r in rows:
        leg_groups[r["leg"]].append(r)
    leg_out = {}
    for leg, recs in sorted(leg_groups.items()):
        yl = np.array([rr["gross_bps"] for rr in recs], dtype=float)
        syml = [rr["symbol"] for rr in recs]
        dayl = [rr["entry_day"] for rr in recs]
        stat = _two_way_cluster_t(yl, None, syml, dayl) if len(yl) >= 5 else {"ok": False, "reason": "n<5"}
        # 各 leg 在 down regime 的 GROSS（down-beta tell：short 在 down 賺）。
        down_recs = [rr for rr in recs if rr["regime"] == "btc_down"]
        up_recs = [rr for rr in recs if rr["regime"] == "btc_up"]
        leg_out[leg] = {
            "n": len(recs),
            "gross_mean_bps": float(yl.mean()),
            "cluster_t": stat.get("intercept_t") if stat.get("ok") else None,
            "gross_mean_in_btc_down": (
                float(np.mean([rr["gross_bps"] for rr in down_recs])) if down_recs else None
            ),
            "n_in_btc_down": len(down_recs),
            "gross_mean_in_btc_up": (
                float(np.mean([rr["gross_bps"] for rr in up_recs])) if up_recs else None
            ),
            "n_in_btc_up": len(up_recs),
        }
    out["long_short_split"] = leg_out

    # ---- 初判 verdict（QC 下最終）----
    out["preliminary_verdict"] = _verdict(out)
    return out


def _verdict(p1) -> dict:
    """初判：GROSS edge 是 regime-independent 真 trend edge，還是 beta/regime artifact。"""
    reasons = []
    artifact_signals = 0

    # 訊號 A：beta-中性化後 alpha 截距是否仍顯著正。
    bn = p1.get("beta_neutralized_leak_free", {})
    a_bps = bn.get("intercept_bps")
    a_t = bn.get("intercept_t")
    if a_bps is not None and a_t is not None:
        if a_bps <= 0 or a_t < 1.64:
            artifact_signals += 1
            reasons.append(
                f"beta-中性化 alpha={a_bps:.2f} bps t={a_t:.2f} 未顯著正（<1.64）→ GROSS edge 由 BTC-beta 解釋"
            )
        else:
            reasons.append(f"beta-中性化 alpha={a_bps:.2f} bps t={a_t:.2f} 顯著正 → 存在 beta 外殘差 edge")

    # 訊號 B：GROSS edge 是否只在單一 regime 為正。
    reg = p1.get("regime_split_leak_free", {})
    pos_regimes = [k for k, v in reg.items() if v["gross_mean_bps"] > 0]
    neg_regimes = [k for k, v in reg.items() if v["gross_mean_bps"] <= 0]
    if len(pos_regimes) <= 1 and len(reg) >= 2:
        artifact_signals += 1
        reasons.append(
            f"GROSS edge 僅在 {pos_regimes} 為正、{neg_regimes} 非正 → regime-dependent（非真 trend edge）"
        )
    else:
        reasons.append(f"GROSS edge 在多個 regime 為正 {pos_regimes} → regime-independent 傾向")

    # 訊號 C：short leg 在 down regime 是否為 GROSS 正貢獻主體（down-beta tell）。
    legs = p1.get("long_short_split", {})
    short = legs.get("short", {})
    long_ = legs.get("long", {})
    if short.get("gross_mean_in_btc_down") is not None and short["gross_mean_in_btc_down"] > 0:
        if (long_.get("gross_mean_bps") or 0) <= 0:
            artifact_signals += 1
            reasons.append(
                "short leg 在 btc_down 為正 GROSS、long leg 整體非正 → 不對稱、down-beta short-crash-insurance 指紋"
            )

    # 訊號 D：bootstrap CI 是否含 0（mean edge 本身不顯著）。
    ci = p1.get("gross_bootstrap_ci", {})
    if not ci.get("excludes_zero", False):
        artifact_signals += 1
        reasons.append(
            f"GROSS mean 的 cluster-block bootstrap 95% CI 含 0 "
            f"[{ci.get('ci95_low_bps'):.2f}, {ci.get('ci95_high_bps'):.2f}] → mean edge 不顯著"
        )

    verdict = "DOWN_BETA_OR_REGIME_ARTIFACT" if artifact_signals >= 2 else "REGIME_SURVIVING_REAL_EDGE_CANDIDATE"
    return {
        "artifact_signal_count": artifact_signals,
        "verdict": verdict,
        "proceed_to_part2": bool(verdict == "REGIME_SURVIVING_REAL_EDGE_CANDIDATE"),
        "reasons": reasons,
        "note": "初判，最終 alpha-reality verdict 由 QC 下；artifact_signals>=2 即判 artifact、STOP PART 2",
    }


# ---------------------------------------------------------------------------
# PART 2 — execution-infra fix（僅 PART 1 PASS 才跑）
# ---------------------------------------------------------------------------
def estimate_maker_close_fill_rate(cost_meta) -> dict:
    """從 post-05-18 已嘗試 close-maker 的資料估 achievable maker-close 成交率。

    close_maker_attempt=true 的腿中：role='maker'（成功掛到 maker）vs fallback（timeout/reject
    退 taker）。achievable_fill_rate = maker_success / attempted。誠實：這是全策略的
    close-maker 成交率（ma_crossover 子樣本可能太小），用作 PART 2 haircut。
    """
    attempted = 0
    maker_success = 0
    fallback = 0
    for key, m in cost_meta.items():
        if key == "_collisions":
            continue
        if m.get("close_maker_attempt"):
            attempted += 1
            if m.get("role") == "maker":
                maker_success += 1
            else:
                fallback += 1
    rate = (maker_success / attempted) if attempted > 0 else None
    return {
        "attempted_close_maker_legs": attempted,
        "maker_filled": maker_success,
        "fell_back_to_taker": fallback,
        "achievable_maker_close_fill_rate": rate,
    }


def part2_infra_fix(frame, cost_meta, taker_fee_bps, maker_fee_bps, fill_rate) -> dict:
    """ma_crossover taker-close→maker 反事實（含真實成交率折損）+ turnover lever。"""
    rows = frame["rows"]
    out = {
        "taker_fee_bps": taker_fee_bps,
        "maker_fee_bps": maker_fee_bps,
        "assumed_maker_close_fill_rate": fill_rate,
    }
    if fill_rate is None:
        out["status"] = "no_fill_rate_data"
        fill_rate = 0.0

    # 找每個 RT 的 exit leg role / fee（用 exit_ts cost_meta）。
    # 反事實：taker exit 腿若改 maker，省 (taker_fee − maker_fee) × fill_rate（未成交回退 taker）。
    fee_delta = taker_fee_bps - maker_fee_bps
    base_net = []
    cf_net = []
    n_taker_exit = 0
    n_maker_exit = 0
    n_unknown_exit = 0
    for r in rows:
        em = cost_meta.get((r["symbol"], r["exit_ts"]))
        exit_role = em["role"] if em else None
        base_net.append(r["net_bps"])
        if exit_role == "taker":
            n_taker_exit += 1
            # 期望節省 = fee_delta × fill_rate（未成交那部分仍付 taker，無節省）。
            cf_net.append(r["net_bps"] + fee_delta * fill_rate)
        elif exit_role == "maker":
            n_maker_exit += 1
            cf_net.append(r["net_bps"])
        else:
            n_unknown_exit += 1
            # role 未知（舊 fill）：以全策略 taker exit 佔比保守視為 taker 並折損。
            cf_net.append(r["net_bps"] + fee_delta * fill_rate)
    base_arr = np.array(base_net, dtype=float)
    cf_arr = np.array(cf_net, dtype=float)
    out["counterfactual_maker_close"] = {
        "n_round_trips": len(rows),
        "n_taker_exit_known": n_taker_exit,
        "n_maker_exit_known": n_maker_exit,
        "n_unknown_exit_role": n_unknown_exit,
        "fee_delta_bps": fee_delta,
        "base_net_mean_bps": float(base_arr.mean()),
        "counterfactual_net_mean_bps": float(cf_arr.mean()),
        "improvement_bps_per_rt": float(cf_arr.mean() - base_arr.mean()),
        "counterfactual_net_positive": bool(cf_arr.mean() > 0),
        "note": (
            "保守：未成交回退 taker（無節省）；role 未知腿視為 taker 折損。"
            "改的是 ma_crossover 自身 turnover/路由（sibling 未涉策略級）。"
        ),
    }

    # ---- turnover lever：高信心子集（GROSS 正的 RT）net 是否改善 ----
    high_conv = [r for r in rows if r["gross_bps"] > 0]
    low_conv = [r for r in rows if r["gross_bps"] <= 0]
    out["turnover_lever"] = {
        "n_total": len(rows),
        "n_high_conviction_gross_positive": len(high_conv),
        "n_low_conviction_gross_nonpositive": len(low_conv),
        "all_rt_net_mean_bps": float(base_arr.mean()),
        "high_conv_net_mean_bps": (
            float(np.mean([r["net_bps"] for r in high_conv])) if high_conv else None
        ),
        "high_conv_gross_mean_bps": (
            float(np.mean([r["gross_bps"] for r in high_conv])) if high_conv else None
        ),
        "low_conv_net_mean_bps": (
            float(np.mean([r["net_bps"] for r in low_conv])) if low_conv else None
        ),
        "note": (
            "高信心子集 = GROSS 正的 RT。注意：此為事後 in-sample 切分（看到 GROSS 才知正負），"
            "非可交易信號；只診斷『若只交易賺錢的那批』理論上限，QC 須以 ex-ante 信號驗。"
        ),
    }

    # ---- 淨可尋址 ----
    out["net_addressable"] = {
        "improvement_bps_per_rt": out["counterfactual_maker_close"]["improvement_bps_per_rt"],
        "rt_count": len(rows),
        "total_addressable_bps": out["counterfactual_maker_close"]["improvement_bps_per_rt"] * len(rows),
        "flips_net_positive_after_haircut": out["counterfactual_maker_close"]["counterfactual_net_positive"],
    }
    return out


# ---------------------------------------------------------------------------
# 主編排
# ---------------------------------------------------------------------------
def main() -> None:
    conn = _connect()
    try:
        round_trips, entry_side = load_round_trips_with_funding(conn)
        cost_meta = load_cost_meta(conn)
        ma_rts = [r for r in round_trips if r.strategy_name == TARGET_STRATEGY]
        if not ma_rts:
            print(json.dumps({"error": "no ma_crossover round-trips"}, ensure_ascii=False))
            return
        entries = [r.entry_ts for r in ma_rts]
        exits = [r.exit_ts for r in ma_rts if r.exit_ts]
        start_ts = min(entries) - dt.timedelta(minutes=5)
        end_ts = max(exits) + dt.timedelta(minutes=5)
        btc_1m = load_btc_1m(conn, start_ts, end_ts)
        btc_1d = load_btc_1d(conn)
        # 動態 fee 中位數。
        from psycopg2.extras import RealDictCursor
        modes = res._engine_mode_scope(ENGINE_MODE)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT liquidity_role,
                  (percentile_cont(0.5) WITHIN GROUP (ORDER BY fee_rate)) * 10000 AS med_bps
                FROM trading.fills
                WHERE engine_mode = ANY(%(modes)s) AND ts >= %(since)s
                  AND strategy_name = %(strat)s
                  AND liquidity_role IN ('taker','maker')
                GROUP BY liquidity_role
                """,
                {"modes": modes, "since": SINCE, "strat": TARGET_STRATEGY},
            )
            fee_med = {row["liquidity_role"]: _f(row["med_bps"]) for row in cur.fetchall()}
    finally:
        conn.close()

    taker_fee = fee_med.get("taker") or _FALLBACK_TAKER_FEE_BPS
    maker_fee = fee_med.get("maker") or _FALLBACK_MAKER_FEE_BPS

    regime_leak = build_regime_labels(btc_1d)
    regime_naive = build_regime_labels_naive(btc_1d)
    frame = build_trade_frame(round_trips, entry_side, btc_1m, regime_leak, regime_naive)

    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "strategy": TARGET_STRATEGY,
        "engine_mode": ENGINE_MODE,
        "n_btc_1m_bars": len(btc_1m),
        "n_btc_1d_bars": len(btc_1d),
        "n_regime_days_labeled": len(regime_leak),
        "entry_side_collisions": entry_side.get("_collisions", 0),
        "cost_meta_collisions": cost_meta.get("_collisions", 0),
        "median_taker_fee_bps": taker_fee,
        "median_maker_fee_bps": maker_fee,
        "frame_diagnostics": {
            "n_round_trips": frame["n"],
            "n_no_btc_bar": frame["n_no_btc_bar"],
            "n_no_regime_label": frame["n_no_regime_label"],
            "n_regime_naive_vs_leak_disagree": frame["n_regime_naive_vs_leak_disagree"],
        },
        "params": {
            "regime_trend_window_days": REGIME_TREND_WINDOW_DAYS,
            "regime_chop_band": REGIME_CHOP_BAND,
            "bootstrap_n": BOOTSTRAP_N,
        },
    }

    part1 = part1_gross_reality(frame)
    report["part1_gross_edge_reality"] = part1

    # PART 2 僅在 PART 1 初判通過時跑（artifact → STOP）。
    if part1["preliminary_verdict"]["proceed_to_part2"]:
        fill_est = estimate_maker_close_fill_rate(cost_meta)
        report["part2_maker_close_fill_rate_estimate"] = fill_est
        report["part2_infra_fix"] = part2_infra_fix(
            frame, cost_meta, taker_fee, maker_fee,
            fill_est["achievable_maker_close_fill_rate"],
        )
    else:
        report["part2_infra_fix"] = {
            "status": "SKIPPED",
            "reason": "PART 1 初判為 down-beta / regime artifact；不對非-edge 做 wishful 成本反事實",
        }

    out_path = os.environ.get("ANALYSIS_OUT", "/tmp/openclaw/ma_crossover_edge/analysis.json")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False, default=str)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
