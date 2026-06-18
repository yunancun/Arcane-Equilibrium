#!/usr/bin/env python3
"""tail_dislocation_meanrev.prepilot_gates — arc-first 尾部錯位 alpha 的三個 pre-pilot $0 gate
（G1 per-crash-regime 歸屬 + leave-one-crash-out / G2 fixed-notional death-spiral MC /
 G3 DSR + PBO/CSCV deflation），決定 demo-pilot BUILD 還是 downgrade（$0 唯讀 OFFLINE）。

MODULE_NOTE
模塊用途：
  extend_history.py 已證實這是本盈利弧在 17 條死軸後的「第一個統計上真實 edge」：
  6.23yr 1d panel、day-clustered block-bootstrap boot_t（K15N3 C3）4.69、CI[0.031,0.076]
  排除 0、過 Bonferroni、真 2021/2022 崩盤 survivable（fixed-notional C3 maxDD K15=12%）、
  OOS hold K>=15、beta-clean DOWN-regime over-reaction、清成本牆數量級。verdict
  CONDITIONAL-GO demo-only。但鏈定三個未解 gate（live 前 do-NOT-skip，本檔全 $0 跑）：

    (G1) PER-MACRO-REGIME ATTRIBUTION（最深疑慮，QC reservation #3）：146 day-episode 不是
         146 個獨立宏觀事件——6yr 真獨立崩盤 regime ~ 10-15。整個 boot_t / PnL 可能由 <=3
         次崩盤（China-ban 2021-05、LUNA 2022-05、FTX 2022-11）扛。leave-one-crash-regime-out：
         移除單一最大貢獻崩盤後 edge（boot_t、mean net）是否 SURVIVE？若拿掉 LUNA/FTX 就
         塌成不顯著 → 是「6 年 3 個事件」非 repeatable engine。

    (G2) DEATH-SPIRAL MONTE-CARLO on FIXED-NOTIONAL：survivor panel（26 仍交易、
         n_possibly_delisted=0）結構性排除「LUNA 接刀後永不反彈直接歸零」。在 fixed-notional
         曲線上重跑合成死亡 overlay（cond-death 2/3/5% per deep-K entry + gap-through-to-95%
         terminal），要求 p95 maxDD<=25%。prior stop-anchored 變體在 2% 就破；fixed-notional
         decouple leverage 應更穩，但這是 INFERRED 尚未實測。

    (G3) DSR/PBO DEFLATION：scripts 內無 DSR/PBO/Bonferroni（grep 證）。best_fn（K15N1 C5 nf20、
         Sharpe 2.22）是 720-cell grid 上未 deflate 的 argmax。算 Deflated-Sharpe-Ratio + PBO
         (CSCV)，用誠實的 trial 數（720）與誠實 effective-N（~10-15 獨立 regime）。chosen
         operating point 是否 survive deflation，還是只剩 pre-specified 保守 anchor（K15N3 C3
         nf10、Sharpe 2.25）撐得住？

  delisting-inclusive ATTEMPT（$0 if feasible）：Bybit 公開 REST 能否回 DELISTED linear symbol
  的 klines（注入真死亡事件）？feasible 就抓幾個真死名；不 $0-feasible 就標明並以 G2 MC 當
  proxy（絕不付費）。

  決定的事：recommend demo-pilot BUILD 還是 downgrade。survival-first（Principle 5）非協商；
  no extra pay / no capital scale-up；no self-deception。

硬邊界（R-0 隔離紅線，mirror screen.py / survival_safe.py / extend_history.py）：
  - 純讀 PG：import screen.py / survival_safe.py / extend_history.py 的 read-only 連線 / 事件 /
    sizing / 統計 helper（0 改 sibling）；DB 只 SELECT；REST 純網路（無 key、無 auth）；
    0 寫 PG、0 order path、0 production code 改、0 auth/lease/risk 觸碰。
  - merged klines 復用 extend_history 的 REST cache CSV（已驗 overlap 26/26 MATCH）+ DB anchor，
    不重抓（$0、快）；衝突日以 DB clean anchor 為準。
  - net 計算保守（與 sibling 對齊）：maker 進場 2bp、退出 maker 2bp / taker 5.5bp、funding
    over hold；禁 rebate。
  - 死亡注入 / bootstrap / CSCV 用獨立 RNG seed（per-caller 確定性），絕不污染實證統計。
  - artifact root 禁硬編碼：${OPENCLAW_DATA_DIR:-/tmp/openclaw}/ 推導。
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import itertools
import json
import math
import os
import random
from typing import Any, Optional

import screen as base
import survival_safe as surv
import extend_history as ext

try:
    import numpy as np
    from scipy import stats as scipy_stats
    _SCIPY = True
except Exception:  # noqa: BLE001 — 無 scipy 時 fail-loud（DSR/PBO 需要）
    _SCIPY = False

GATES_VERSION = "tail_dislocation_meanrev.prepilot_gates.v0.1"

# ---------------------------------------------------------------------------
# G1：macro-crash-regime 窗（比 extend_history 的 5 個 EMPIRICAL_CRASH_WINDOWS 更完整，
# 覆蓋 mandate 列舉的所有真獨立崩盤 regime；COVID 若 BTC/ETH 覆蓋）。
#
# 為什麼這套窗：mandate 要求把每個 deep-K entry 標到一個 macro-crash-regime，量化
# 每 regime 對總 net PnL 與 boot_t 的貢獻，並做 leave-one-regime-out。窗以 UTC 日界，
# half-open 概念用閉區間（日層）。窗之外的 fill 標 "non_crash_dip"（非宏觀崩盤的日常 dip）。
# 窗界以 BTC/ETH/大-cap 的歷史峰崩日訂（leak-free 不適用——這是事後歸因標籤，非交易信號）。
# ---------------------------------------------------------------------------
MACRO_CRASH_REGIMES = [
    ("covid_2020_03",        "2020-03-01", "2020-03-31"),  # COVID −50%（BTC/ETH REST 自 2020-03-25 起，部分覆蓋）
    ("china_ban_2021_05",    "2021-05-10", "2021-05-31"),  # 2021-05 China-ban −50%
    ("bear_2021_12_2022_03", "2021-11-10", "2022-03-31"),  # ATH→bear 起跌長窗
    ("luna_2022_05",         "2022-05-05", "2022-05-31"),  # LUNA/UST −100%
    ("threeac_2022_06",      "2022-06-01", "2022-06-30"),  # 3AC contagion + 續崩
    ("ftx_2022_11",          "2022-11-05", "2022-11-30"),  # FTX 崩盤
    ("svb_2023_03",          "2023-03-08", "2023-03-15"),  # SVB / USDC depeg
    ("yen_carry_2024_08",    "2024-08-01", "2024-08-09"),  # 2024-08 yen-carry unwind
    ("dip_2025",             "2025-01-01", "2025-12-31"),  # 2025 各 dip（粗窗，無單一大事件）
    ("dip_2026",             "2026-01-01", "2026-12-31"),  # 2026 各 dip
]


def _macro_regime_of(date_iso: str) -> str:
    """回該 entry_date 所屬的 macro-crash-regime 名；不在任何窗 = 'non_crash_dip'。"""
    d = dt.date.fromisoformat(date_iso)
    for name, lo, hi in MACRO_CRASH_REGIMES:
        if dt.date.fromisoformat(lo) <= d <= dt.date.fromisoformat(hi):
            return name
    return "non_crash_dip"


# ---------------------------------------------------------------------------
# merged klines（復用 extend_history REST cache + DB anchor，0 重抓）
# ---------------------------------------------------------------------------

def _load_rest_cache_csv(root: str, symbol: str) -> list[dict[str, Any]]:
    """讀 extend_history 寫過的 per-symbol REST cache CSV（已驗 overlap MATCH）。"""
    path = os.path.join(root, f"{symbol}_1d.csv")
    if not os.path.exists(path):
        return []
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        rdr = csv.DictReader(fh)
        for r in rdr:
            try:
                o, h, l, c = float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])
            except (ValueError, TypeError, KeyError):
                continue
            if not all(math.isfinite(x) for x in (o, h, l, c)) or min(o, h, l, c) <= 0:
                continue
            turn = None
            try:
                turn = float(r["turnover"]) if r.get("turnover") not in (None, "", "None") else None
            except (ValueError, TypeError):
                turn = None
            rows.append({"date": r["date"], "open": o, "high": h, "low": l, "close": c, "turnover": turn})
    rows.sort(key=lambda x: x["date"])
    return rows


def build_merged_klines(conn) -> tuple[dict[str, list[dict[str, Any]]], dict, dict, dict, dict]:
    """合併 REST cache 全歷史 + DB clean anchor（衝突以 DB 為準），回 (merged, funding, btc_fwd, btc_regime, meta)。

    為什麼復用 cache：extend_history 已抓全 26 symbol 到最早可得並驗 overlap 26/26 MATCH
    （max_rel=0.0）→ cache 可信，重抓無意義且不禮貌。DB anchor 補近端 clean bar。
    """
    rest_root = os.path.join(ext._data_root(), "research", "tail_dislocation_meanrev", "rest_cache")
    symbols = base.list_symbols(conn)
    db_klines = {s: base.load_1d_klines(conn, s) for s in symbols}
    funding = base.load_funding_daily(conn)

    merged: dict[str, list[dict[str, Any]]] = {}
    for s in symbols:
        rest_rows = _load_rest_cache_csv(rest_root, s)
        by_date: dict[str, dict[str, Any]] = {}
        for r in rest_rows:
            by_date[r["date"]] = {"date": r["date"], "open": r["open"], "high": r["high"],
                                  "low": r["low"], "close": r["close"], "turnover": r["turnover"]}
        for r in db_klines.get(s, []):  # DB clean anchor 覆蓋衝突日
            by_date[r["date"]] = {"date": r["date"], "open": r["open"], "high": r["high"],
                                  "low": r["low"], "close": r["close"], "turnover": r["turnover"]}
        merged[s] = [by_date[d] for d in sorted(by_date.keys())]

    btc_fwd, btc_regime = base.build_btc_helpers(merged.get("BTCUSDT", []))
    gf = min((ks[0]["date"] for ks in merged.values() if ks), default=None)
    gl = max((ks[-1]["date"] for ks in merged.values() if ks), default=None)
    span = ((dt.date.fromisoformat(gl) - dt.date.fromisoformat(gf)).days / 365.0) if (gf and gl) else None
    meta = {"n_symbols": len(symbols), "global_first": gf, "global_last": gl, "span_years": span,
            "n_rest_cached": sum(1 for s in symbols if _load_rest_cache_csv(rest_root, s))}
    return merged, funding, btc_fwd, btc_regime, meta


# ---------------------------------------------------------------------------
# G1：per-macro-crash-regime attribution + leave-one-crash-out
# ---------------------------------------------------------------------------

def _day_means_by_regime(kept: list[dict[str, Any]], ret_key: str) -> dict[str, list[float]]:
    """把 kept 事件按 macro-regime 分桶，每桶內再 day-cluster（同日等權平均 → 單一日報酬）。

    為什麼 day-cluster within regime：同一崩盤日多 symbol 同時 fill 高度相關，誠實有效 N =
    distinct crash episode（非逐筆）。leave-one-out 必須在 day-clustered 日報酬層做，否則
    又會 iid-高估。
    """
    by_regime_day: dict[str, dict[str, list[float]]] = {}
    for e in kept:
        r = e.get(ret_key)
        if r is None:
            continue
        reg = _macro_regime_of(e["entry_date"])
        by_regime_day.setdefault(reg, {}).setdefault(e["entry_date"], []).append(r)
    out: dict[str, list[float]] = {}
    for reg, dd in by_regime_day.items():
        out[reg] = [sum(v) / len(v) for v in dd.values()]
    return out


def regime_attribution_and_loo(
    merged, funding, btc_fwd, btc_regime, *, k: float, hold: int, cap: Optional[int],
    label: str, seed: int,
) -> dict[str, Any]:
    """G1：對一個 config 算 (a) per-regime 貢獻（net PnL 份額 + day-clustered boot_t）、
    (b) leave-one-crash-regime-out（移除單一 / top-2 / top-3 最大貢獻崩盤後的 boot_t/mean）、
    (c) 多少獨立崩盤 regime 各扛 >X% 的 edge。

    為什麼這是 THE decisive G1：若移除 LUNA（或 top contributor）後 boot_t 跌破 2 / CI 含 0，
    edge 是「少數事件」非 repeatable engine（QC reservation #3）。
    """
    ev = surv.build_events_stopped(merged, funding, btc_fwd, btc_regime, k=k, hold=hold, stop=None)
    cap_int = None if cap in (None, "unlimited") else int(cap)
    kept = surv.apply_concurrency_cap(ev, cap=cap_int)["kept"]

    # 全集 day-clustered baseline（與 extend_history decisive 對齊）。
    full_dcs = surv.day_clustered_significance(kept, ret_key="net_taker", seed=seed)
    full_b1 = full_dcs.get("block_bootstrap_day_b1", {})

    # per-regime 貢獻：total net PnL（sum of net_taker，等-notional 加總近似）+ day-clustered boot_t。
    regimes = sorted(set(_macro_regime_of(e["entry_date"]) for e in kept))
    total_net = sum(e["net_taker"] for e in kept if e.get("net_taker") is not None)
    per_regime: dict[str, Any] = {}
    regime_day_means = _day_means_by_regime(kept, "net_taker")
    for reg in regimes:
        reg_ev = [e for e in kept if _macro_regime_of(e["entry_date"]) == reg]
        reg_net = sum(e["net_taker"] for e in reg_ev if e.get("net_taker") is not None)
        n_days = len(set(e["entry_date"] for e in reg_ev))
        dm = regime_day_means.get(reg, [])
        # 單一 regime 內 day-clustered boot_t（block=1）。
        reg_boot = (base._block_bootstrap_tstat(dm, block_len=1, n_boot=base.BLOCK_BOOTSTRAP_N,
                                                 seed=seed + hash(reg) % 9973)
                    if len(dm) >= 3 else {"boot_t": None, "ci95": [None, None]})
        per_regime[reg] = {
            "n_fills": len(reg_ev), "n_distinct_days": n_days,
            "net_pnl_sum": reg_net,
            "pct_of_total_net_pnl": (reg_net / total_net) if total_net not in (0, None) else None,
            "mean_per_fill": base._mean([e["net_taker"] for e in reg_ev]),
            "within_regime_boot_t": reg_boot.get("boot_t"),
            "within_regime_ci95": reg_boot.get("ci95"),
        }

    # leave-one(/two/three)-crash-regime-out：按 net_pnl_sum 降序找 top contributors，
    # 逐步移除其 fills，重算全集 day-clustered boot_t / mean / CI。
    crash_regimes = [r for r in regimes if r != "non_crash_dip"]
    ranked = sorted(crash_regimes, key=lambda r: per_regime[r]["net_pnl_sum"], reverse=True)

    def _recompute_without(excluded: set[str]) -> dict[str, Any]:
        sub = [e for e in kept if _macro_regime_of(e["entry_date"]) not in excluded]
        dcs = surv.day_clustered_significance(sub, ret_key="net_taker",
                                              seed=seed + 31 * len(excluded) + 7)
        b1 = dcs.get("block_bootstrap_day_b1", {})
        ci = b1.get("ci95", [None, None])
        ci_excl0 = (ci[0] is not None and ((ci[0] > 0) or (ci[1] < 0)))
        sub_net = sum(e["net_taker"] for e in sub if e.get("net_taker") is not None)
        return {
            "excluded": sorted(excluded),
            "n_fills_remaining": len(sub),
            "n_distinct_days_remaining": dcs.get("n_distinct_days"),
            "boot_t": b1.get("boot_t"),
            "ci95": ci,
            "ci_excludes_zero": ci_excl0,
            "mean_day_return": dcs.get("mean_day_return"),
            "net_pnl_sum_remaining": sub_net,
            "survives": bool(b1.get("boot_t") is not None and b1["boot_t"] >= 2.0 and ci_excl0),
        }

    loo = []
    if ranked:
        loo.append({"removed_rank": "top-1", **_recompute_without({ranked[0]})})
    if len(ranked) >= 2:
        loo.append({"removed_rank": "top-2", **_recompute_without(set(ranked[:2]))})
    if len(ranked) >= 3:
        loo.append({"removed_rank": "top-3", **_recompute_without(set(ranked[:3]))})
    # 也測「移除 LUNA+FTX」（mandate 點名的最關鍵兩個）。
    luna_ftx = {r for r in ("luna_2022_05", "ftx_2022_11") if r in crash_regimes}
    if luna_ftx:
        loo.append({"removed_rank": "luna+ftx_named", **_recompute_without(luna_ftx)})

    # 多少獨立崩盤 regime 各扛 >X% edge。
    edge_carriers = {}
    for thr in (0.10, 0.20, 0.30):
        carriers = [r for r in crash_regimes
                    if per_regime[r]["pct_of_total_net_pnl"] is not None
                    and per_regime[r]["pct_of_total_net_pnl"] > thr]
        edge_carriers[f">{int(thr*100)}pct"] = {"n_regimes": len(carriers), "regimes": carriers}

    # top-1/2/3 累積 net PnL 份額。
    cum_share = {}
    cum = 0.0
    for i, r in enumerate(ranked[:3], start=1):
        s = per_regime[r]["pct_of_total_net_pnl"]
        cum += (s if s is not None else 0.0)
        cum_share[f"top{i}_cum_pct_of_net_pnl"] = cum

    # 多少 distinct INDEPENDENT crash regime over 6yr（有 fill 的非 non_crash_dip 窗數）。
    n_independent_crash_regimes_with_fills = len([r for r in crash_regimes if per_regime[r]["n_fills"] > 0])

    return {
        "config": {"label": label, "k": k, "hold": hold, "cap": cap},
        "full_day_clustered_boot_t": full_b1.get("boot_t"),
        "full_day_clustered_ci95": full_b1.get("ci95"),
        "full_n_distinct_days": full_dcs.get("n_distinct_days"),
        "full_n_kept": len(kept),
        "total_net_pnl_sum": total_net,
        "n_independent_crash_regimes_with_fills": n_independent_crash_regimes_with_fills,
        "n_macro_regimes_defined": len(MACRO_CRASH_REGIMES),
        "per_regime_attribution": per_regime,
        "regime_rank_by_net_pnl": ranked,
        "top_cumulative_net_pnl_share": cum_share,
        "edge_carriers_above_threshold": edge_carriers,
        "leave_one_crash_out": loo,
    }


# ---------------------------------------------------------------------------
# G2：death-spiral Monte-Carlo on FIXED-NOTIONAL curves
# ---------------------------------------------------------------------------

def fixed_notional_death_spiral_stress(
    kept: list[dict[str, Any]], *, ret_key: str, notional_frac: float,
    cond_death_rate: float, n_seeds: int = surv.DEATH_STRESS_SEEDS, base_seed: int = 0,
) -> dict[str, Any]:
    """G2：在 FIXED-NOTIONAL 曲線上注入合成死亡（cond-death per deep-K entry + gap-through-to-95%），
    多 seed MC，報 maxDD/annret 的 mean + p95 + p99。

    為什麼 fixed-notional（非 survival_safe 的 stop-anchored）：survival_safe 的 stop-anchored
    sizing 使 lever=r/S，stop 越緊 lever 越大 → gap-through 時放大損失（雙重反效果，2% 就破）。
    fixed-notional decouple：每槽固定 notional_frac × equity，單槽最大損失 = nf × |worst|（有界、
    與 stop 無關）→ 應對 gap-through 死亡更穩。本 gate 實測這個 INFERRED 穩健性。

    死亡建模（mandate）：每筆深-K entry 以 Bernoulli(cond_death_rate) 死亡；死亡事件 fill 成功
    但 terminal 結算到 DEATH_TERMINAL_RET(−95%)（gap-through：hard-limit fill 可跳空穿過）。
    fixed-notional 無 stop 概念 → 全部死亡都是 gap-through-to-terminal（最保守）。
    """
    maxdds: list[float] = []
    annrets: list[float] = []
    cvars: list[float] = []
    killed: list[int] = []
    for s in range(n_seeds):
        rng = random.Random(base_seed + s * 7919 + 13)
        stressed = []
        n_killed = 0
        for e in kept:
            e2 = dict(e)
            if rng.random() < cond_death_rate:
                n_killed += 1
                # gap-through-to-terminal：fixed-notional 無 stop，死亡 = 近全損。
                # 取 min(−95%, symbol 最後可得 close 隱含的更差值) 概念上更保守，但 −95%
                # 已是 fixed-notional 單槽乘法步進的近全損上界（nf×−0.95），用 −95% terminal。
                e2[ret_key] = surv.DEATH_TERMINAL_RET
            stressed.append(e2)
        fn = ext.fixed_notional_equity_curve(stressed, ret_key=ret_key, notional_frac=notional_frac)
        if fn.get("max_drawdown") is not None:
            maxdds.append(fn["max_drawdown"])
            annrets.append(fn["annualized_return"])
            if fn.get("cvar05_day_return") is not None:
                cvars.append(fn["cvar05_day_return"])
        killed.append(n_killed)
    maxdd_mean = base._mean(maxdds)
    maxdd_p95 = base._percentile(maxdds, 0.95)
    maxdd_p99 = base._percentile(maxdds, 0.99)
    return {
        "cond_death_rate_per_entry": cond_death_rate,
        "notional_frac": notional_frac,
        "n_events": len(kept),
        "n_seeds": n_seeds,
        "mean_killed_per_run": base._mean([float(x) for x in killed]),
        "death_terminal_ret": surv.DEATH_TERMINAL_RET,
        "gap_through_model": "all_deaths_gap_through_to_terminal (fixed-notional has no stop)",
        "fn_maxdd_stressed_mean": maxdd_mean,
        "fn_maxdd_stressed_p95": maxdd_p95,
        "fn_maxdd_stressed_p99": maxdd_p99,
        "fn_annret_stressed_mean": base._mean(annrets),
        "fn_cvar05_day_stressed_mean": base._mean(cvars) if cvars else None,
        "survivable_p95": (maxdd_p95 is not None and maxdd_p95 <= surv.SURVIVABLE_MAXDD),
        "survivable_p99": (maxdd_p99 is not None and maxdd_p99 <= surv.SURVIVABLE_MAXDD),
    }


def run_g2(merged, funding, btc_fwd, btc_regime, *, best_fn_cfg: Optional[dict]) -> dict[str, Any]:
    """G2 driver：對保守 anchor（K15N3 C3 nf10）+ best_fn + 代表 deep-K config 跑
    cond-death {2%,3%,5%} × fixed-notional death-spiral MC。"""
    targets = [
        {"k": 0.15, "hold": 3, "cap": 3, "nf": 0.10, "label": "conservative_anchor_K15N3C3_nf10"},
        {"k": 0.10, "hold": 3, "cap": 3, "nf": 0.10, "label": "K10N3C3_nf10"},
        {"k": 0.20, "hold": 3, "cap": 5, "nf": 0.10, "label": "K20N3C5_nf10"},
    ]
    if best_fn_cfg is not None:
        targets.insert(1, {"k": best_fn_cfg["k"], "hold": best_fn_cfg["hold"],
                           "cap": best_fn_cfg["cap"], "nf": best_fn_cfg["notional_frac"],
                           "label": "best_fn_K%dN%dC%s_nf%g" % (
                               int(best_fn_cfg["k"] * 100), best_fn_cfg["hold"],
                               best_fn_cfg["cap"], best_fn_cfg["notional_frac"])})
    out = []
    for tgt in targets:
        ev = surv.build_events_stopped(merged, funding, btc_fwd, btc_regime,
                                       k=tgt["k"], hold=tgt["hold"], stop=None)
        cap_int = None if tgt["cap"] in (None, "unlimited") else int(tgt["cap"])
        kept = surv.apply_concurrency_cap(ev, cap=cap_int)["kept"]
        # baseline（無死亡注入）fixed-notional。
        base_fn = ext.fixed_notional_equity_curve(kept, ret_key="net_taker", notional_frac=tgt["nf"])
        per_rate = []
        for cdr in (0.02, 0.03, 0.05):
            sres = fixed_notional_death_spiral_stress(
                kept, ret_key="net_taker", notional_frac=tgt["nf"], cond_death_rate=cdr,
                base_seed=int(cdr * 100000) + tgt["hold"] * 17 + int(tgt["k"] * 1000))
            per_rate.append(sres)
        # nf 敏感度：fixed-notional 是曲線上的純標量 → 找能讓 p95 maxDD<=25%（含合成死亡）
        # 的最大 survivable nf（這是真正可部署 sizing，非 headline nf=10/20%）。
        nf_sensitivity = []
        for nf_test in (0.02, 0.03, 0.05, 0.10, 0.20):
            b = ext.fixed_notional_equity_curve(kept, ret_key="net_taker", notional_frac=nf_test)
            s2 = fixed_notional_death_spiral_stress(
                kept, ret_key="net_taker", notional_frac=nf_test, cond_death_rate=0.02,
                base_seed=int(nf_test * 1000) + 101)
            s3 = fixed_notional_death_spiral_stress(
                kept, ret_key="net_taker", notional_frac=nf_test, cond_death_rate=0.03,
                base_seed=int(nf_test * 1000) + 103)
            nf_sensitivity.append({
                "notional_frac": nf_test,
                "baseline_maxdd": b.get("max_drawdown"),
                "baseline_annret": b.get("annualized_return"),
                "death2pct_p95_maxdd": s2.get("fn_maxdd_stressed_p95"),
                "death2pct_survivable_p95": s2.get("survivable_p95"),
                "death3pct_p95_maxdd": s3.get("fn_maxdd_stressed_p95"),
                "death3pct_survivable_p95": s3.get("survivable_p95"),
            })
        # 最大 survivable nf（要求 death-3% p95<=25%，最嚴）。
        survivable_nfs = [x["notional_frac"] for x in nf_sensitivity if x["death3pct_survivable_p95"]]
        max_survivable_nf = max(survivable_nfs) if survivable_nfs else None
        out.append({
            "config": tgt,
            "n_kept": len(kept),
            "baseline_fn_maxdd": base_fn.get("max_drawdown"),
            "baseline_fn_annret": base_fn.get("annualized_return"),
            "baseline_fn_worst_trade": base_fn.get("worst_single_trade"),
            "death_spiral_mc": per_rate,
            "nf_sensitivity_to_find_survivable_sizing": nf_sensitivity,
            "max_survivable_notional_frac_death3pct": max_survivable_nf,
        })
    return {"survivable_maxdd_threshold": surv.SURVIVABLE_MAXDD,
            "cond_death_rates_tested": [0.02, 0.03, 0.05], "results": out}


# ---------------------------------------------------------------------------
# G3：Deflated Sharpe Ratio + PBO/CSCV deflation
# ---------------------------------------------------------------------------

def _daily_return_series_for_config(
    merged, funding, btc_fwd, btc_regime, *, k: float, hold: int, cap: Optional[int], nf: float,
) -> tuple[list[str], list[float]]:
    """回某 config 的 day-clustered fixed-notional 日報酬序列（用於 DSR / CSCV）。

    為什麼日層：事件叢集在崩盤日，組合節律是日層；DSR 的 Sharpe / skew / kurt 與 PBO 的
    IS/OOS 排名都在「distinct entry-day 的 fixed-notional 日報酬」序列上算（誠實有效 N）。
    """
    ev = surv.build_events_stopped(merged, funding, btc_fwd, btc_regime, k=k, hold=hold, stop=None)
    cap_int = None if cap in (None, "unlimited") else int(cap)
    kept = surv.apply_concurrency_cap(ev, cap=cap_int)["kept"]
    by_day: dict[str, list[float]] = {}
    for e in kept:
        r = e.get("net_taker")
        if r is not None:
            by_day.setdefault(e["entry_date"], []).append(r)
    days = sorted(by_day.keys())
    # fixed-notional 日報酬：同日各槽等-notional 平均 ret × nf（單日權益乘法近似為線性小注）。
    day_rets = [nf * (sum(by_day[d]) / len(by_day[d])) for d in days]
    return days, day_rets


def _sharpe(rets: list[float]) -> Optional[float]:
    """非年化 Sharpe（per-period），用於 DSR / PBO。"""
    if len(rets) < 2:
        return None
    m = base._mean(rets)
    sd = base._stddev(rets)
    return (m / sd) if (sd and sd > 0) else None


def deflated_sharpe_ratio(
    rets: list[float], *, n_trials: int, effective_n: Optional[int] = None,
) -> dict[str, Any]:
    """Bailey & López de Prado (2014) Deflated Sharpe Ratio。

    為什麼：best_fn 是 720-cell grid 上未 deflate 的 argmax Sharpe；多重試驗下，純運氣
    也能產生高 Sharpe。DSR 把觀察 Sharpe 對「試驗數 N、報酬 skew/kurt、樣本長度」做 deflation，
    回 PSR（probabilistic Sharpe ratio）相對於 deflated benchmark SR0。

    SR0 = sqrt(Var(SR across trials)) * ((1-γ)*Z^-1(1-1/N) + γ*Z^-1(1-1/(N*e)))
      （E[max] of N independent SR estimates 的期望近似，γ=Euler-Mascheroni）。
    DSR = PSR(SR0) = Φ( (SR_hat - SR0) * sqrt(T-1) / sqrt(1 - skew*SR_hat + (kurt-1)/4*SR_hat^2) )。

    effective_n（誠實 effective-N ~10-15 獨立 regime）覆蓋 n_trials 用於 SR variance 的有效自由度：
    若提供，用 effective_n 算 trial-variance 的 E[max] benchmark（更誠實，因 720 cell 高度相關，
    獨立試驗實際 ~10-15）。同時報 n_trials=720 與 effective_n 兩個 DSR。
    """
    if not _SCIPY:
        return {"error": "scipy_unavailable"}
    arr = np.asarray([r for r in rets if r is not None], dtype=float)
    T = arr.size
    if T < 8:
        return {"error": "insufficient_sample", "T": int(T)}
    sr_hat = float(arr.mean() / arr.std(ddof=1)) if arr.std(ddof=1) > 0 else None
    if sr_hat is None:
        return {"error": "zero_variance", "T": int(T)}
    skew = float(scipy_stats.skew(arr, bias=False))
    kurt = float(scipy_stats.kurtosis(arr, fisher=False, bias=False))  # 非超額（Pearson）
    gamma = 0.5772156649015329  # Euler-Mascheroni
    e = math.e

    def _sr0(n: int, sr_var: float) -> float:
        """N 個獨立 SR 估計的 max 的期望（benchmark SR0）。"""
        z1 = scipy_stats.norm.ppf(1.0 - 1.0 / n) if n > 1 else 0.0
        z2 = scipy_stats.norm.ppf(1.0 - 1.0 / (n * e)) if n > 1 else 0.0
        return math.sqrt(sr_var) * ((1.0 - gamma) * z1 + gamma * z2)

    def _psr(sr0: float) -> float:
        """PSR relative to sr0：Φ((SR_hat - sr0)*sqrt(T-1)/sqrt(1 - skew*SR_hat + (kurt-1)/4*SR_hat^2))。"""
        denom = 1.0 - skew * sr_hat + ((kurt - 1.0) / 4.0) * sr_hat * sr_hat
        if denom <= 0:
            return float("nan")
        z = (sr_hat - sr0) * math.sqrt(T - 1) / math.sqrt(denom)
        return float(scipy_stats.norm.cdf(z))

    out: dict[str, Any] = {
        "sharpe_per_period_hat": sr_hat,
        "T_periods": int(T),
        "skew": skew,
        "kurtosis_pearson": kurt,
        "n_trials": n_trials,
        "effective_n": effective_n,
    }
    return out, _sr0, _psr  # 回 helper 供 caller 用實際 trial SR variance 算


def run_g3_dsr(
    merged, funding, btc_fwd, btc_regime, *, grid_cells: list[dict[str, Any]],
    chosen_label: str, anchor_label: str, n_trials: int, effective_n: int,
) -> dict[str, Any]:
    """G3 DSR：對 720-cell grid 算每 cell 的非年化 Sharpe（trial 分佈），再對 chosen(best_fn)
    與 conservative anchor 算 DSR（用 trial SR variance 的 E[max] benchmark）。

    為什麼 trial SR variance：DSR 的 SR0 需要「跨試驗的 SR 變異」——用 720 cell 實際算出的
    Sharpe 樣本變異（V[{SR_n}]），分別以 n_trials=720 與 effective_n（~10-15）兩個 N 算 E[max]
    benchmark，回兩個 DSR。effective_n 更誠實（720 cell 高度相關，真獨立試驗少）。
    """
    if not _SCIPY:
        return {"error": "scipy_unavailable"}
    # 每 cell 的非年化 Sharpe（day-clustered fixed-notional 日報酬）。
    trial_sharpes: list[float] = []
    cell_series: dict[str, list[float]] = {}
    for c in grid_cells:
        _, dr = _daily_return_series_for_config(merged, funding, btc_fwd, btc_regime,
                                                k=c["k"], hold=c["hold"], cap=c["cap"], nf=c["nf"])
        sr = _sharpe(dr)
        if sr is not None and math.isfinite(sr):
            trial_sharpes.append(sr)
        cell_series[c["label"]] = dr

    sr_arr = np.asarray(trial_sharpes, dtype=float)
    sr_var = float(sr_arr.var(ddof=1)) if sr_arr.size >= 2 else 0.0

    def _eval(label: str) -> dict[str, Any]:
        dr = cell_series.get(label, [])
        res = deflated_sharpe_ratio(dr, n_trials=n_trials, effective_n=effective_n)
        if isinstance(res, dict):  # error path
            return res
        out, sr0_fn, psr_fn = res
        sr0_full = sr0_fn(n_trials, sr_var)
        sr0_eff = sr0_fn(effective_n, sr_var)
        out["trial_sr_variance"] = sr_var
        out["n_trial_sharpes"] = int(sr_arr.size)
        out["sr0_benchmark_full_trials"] = sr0_full
        out["sr0_benchmark_effective_n"] = sr0_eff
        out["dsr_pvalue_full_trials"] = psr_fn(sr0_full)
        out["dsr_pvalue_effective_n"] = psr_fn(sr0_eff)
        # 也報 PSR vs 0（無 deflation 基準）。
        out["psr_vs_zero"] = psr_fn(0.0)
        out["dsr_survives_full_trials"] = bool(out["dsr_pvalue_full_trials"] is not None
                                               and out["dsr_pvalue_full_trials"] >= 0.95)
        out["dsr_survives_effective_n"] = bool(out["dsr_pvalue_effective_n"] is not None
                                               and out["dsr_pvalue_effective_n"] >= 0.95)
        return out

    return {
        "trial_sharpe_distribution": {
            "n_cells_with_sharpe": int(sr_arr.size),
            "mean": float(sr_arr.mean()) if sr_arr.size else None,
            "std": math.sqrt(sr_var) if sr_var > 0 else None,
            "max": float(sr_arr.max()) if sr_arr.size else None,
            "min": float(sr_arr.min()) if sr_arr.size else None,
        },
        "n_trials_nominal": n_trials,
        "effective_n_honest": effective_n,
        "chosen_best_fn": {"label": chosen_label, **_eval(chosen_label)},
        "conservative_anchor": {"label": anchor_label, **_eval(anchor_label)},
    }


def run_g3_pbo_cscv(
    cell_series: dict[str, list[float]], *, n_partitions: int = 10,
) -> dict[str, Any]:
    """PBO via CSCV (Bailey et al. 2015)：把對齊的「cell × day-return matrix」切成 S 塊，
    取所有 size-S/2 的組合當 IS、補集當 OOS，IS argmax 的 OOS rank 的 logit → PBO。

    為什麼：PBO = P(IS-best config 在 OOS 落到下半 performance) = 過擬合機率。高 PBO（>0.5）
    = grid selection 是過擬合，best_fn 的 IS 優勢 OOS 不延續。在「day-clustered fixed-notional
    日報酬」矩陣上做（誠實有效 N）。

    對齊：各 cell 的日報酬序列日期不同（不同 K/cap → 不同 fill 日）。用所有 cell 共同覆蓋的
    日聯集，缺日填 0（該 config 當日無 fill = 0 報酬，等同未持倉）→ 矩陣對齊。
    """
    if not _SCIPY:
        return {"error": "scipy_unavailable"}
    # 對齊到日聯集（缺日=0）。需先取得每 cell 的 (days, rets)；此處 cell_series 已是 rets，
    # 但長度不一 → 改用 caller 傳對齊矩陣。為自洽，這裡假設 caller 傳的是等長對齊序列。
    labels = list(cell_series.keys())
    mat = np.asarray([cell_series[l] for l in labels], dtype=float)  # shape (M_configs, T_days)
    M, T = mat.shape
    if M < 2 or T < n_partitions * 2:
        return {"error": "insufficient_for_cscv", "M": int(M), "T": int(T)}
    # 切 S 塊（沿時間軸，等長，丟尾餘）。
    S = n_partitions
    block = T // S
    blocks = [list(range(b * block, (b + 1) * block)) for b in range(S)]
    half = S // 2
    logits: list[float] = []
    n_oos_below_median = 0
    n_comb = 0
    for is_combo in itertools.combinations(range(S), half):
        is_idx = [i for b in is_combo for i in blocks[b]]
        oos_idx = [i for b in range(S) if b not in is_combo for i in blocks[b]]
        is_sr = np.array([_sharpe_np(mat[m, is_idx]) for m in range(M)])
        oos_sr = np.array([_sharpe_np(mat[m, oos_idx]) for m in range(M)])
        if np.all(np.isnan(is_sr)):
            continue
        best_is = int(np.nanargmax(is_sr))
        # best_is 在 OOS 的 rank（百分位）。
        oos_best = oos_sr[best_is]
        valid = oos_sr[~np.isnan(oos_sr)]
        if valid.size < 2 or np.isnan(oos_best):
            continue
        rank = (np.sum(valid < oos_best) + 0.5 * np.sum(valid == oos_best)) / valid.size
        rank = min(max(rank, 1e-6), 1 - 1e-6)
        logits.append(math.log(rank / (1 - rank)))
        if rank < 0.5:
            n_oos_below_median += 1
        n_comb += 1
    if not logits:
        return {"error": "no_valid_combinations"}
    pbo = n_oos_below_median / n_comb  # P(IS-best 落 OOS 下半)
    return {
        "n_configs": int(M),
        "n_days": int(T),
        "n_partitions": S,
        "n_combinations": n_comb,
        "pbo": pbo,
        "mean_logit": base._mean(logits),
        "interpretation": "PBO = P(IS-best config OOS 落下半 performance)；>0.5 = 過擬合主導",
        "overfit_verdict": "OVERFIT" if pbo > 0.5 else ("BORDERLINE" if pbo > 0.30 else "ROBUST"),
    }


def _sharpe_np(arr) -> float:
    """numpy 版非年化 Sharpe（CSCV 內用，nan-safe）。"""
    a = arr[~np.isnan(arr)] if hasattr(arr, "__len__") else arr
    if a.size < 2:
        return float("nan")
    sd = a.std(ddof=1)
    return float(a.mean() / sd) if sd > 0 else float("nan")


def build_aligned_cell_matrix(
    merged, funding, btc_fwd, btc_regime, *, grid_cells: list[dict[str, Any]],
) -> dict[str, list[float]]:
    """為 CSCV 建「cell × 對齊日報酬」矩陣（日聯集，缺日=0）。"""
    per_cell_days: dict[str, dict[str, float]] = {}
    all_days: set[str] = set()
    for c in grid_cells:
        days, rets = _daily_return_series_for_config(
            merged, funding, btc_fwd, btc_regime, k=c["k"], hold=c["hold"], cap=c["cap"], nf=c["nf"])
        per_cell_days[c["label"]] = dict(zip(days, rets))
        all_days.update(days)
    ordered = sorted(all_days)
    out: dict[str, list[float]] = {}
    for lbl, dmap in per_cell_days.items():
        out[lbl] = [dmap.get(d, 0.0) for d in ordered]
    return out


# ---------------------------------------------------------------------------
# delisting-inclusive ATTEMPT（$0 feasibility probe）
# ---------------------------------------------------------------------------

KNOWN_DELISTED_LINEAR = [
    # 歷史上 Bybit 曾上線後下市的 linear perp 候選（探 REST 是否仍回歷史 klines）。
    "LUNAUSDT",    # Terra classic（崩盤後多所下市/改名 → REST empty）
    "FTTUSDT",     # FTX token（FTX 崩盤 → REST empty）
    "SRMUSDT",     # Serum（FTX 系 → REST empty）
    "ANCUSDT",     # Anchor（Terra 系 → REST empty）
    "RAYUSDT",     # 對照
    "BTTUSDT",     # 老幣
    "SCUSDT",      # Siacoin
    "OMGUSDT",     # OMG（已下市，REST 仍回 → 真 delisted-to-truncation）
]

# REST 實證可 $0 抓到、且非 26-survivor 集的「真死亡/真重崩」名（probe 已驗）。
# 兩類：(a) DELISTED-truncation：last_day 遠早於 now（GTC/OMG/KLAY/MULTI/FTM，REST 在下市點截止）；
#       (b) SEVERELY-CRASHED survivor：仍交易但自首日崩 >98%（LUNA2/USTC/CVC/WAVES/HNT，真接刀歸零路徑）。
# 這比合成 death-spiral MC 真實：注入真實的「接刀後續崩到截止/近零」事件。
REAL_DEATH_INCLUSIVE_NAMES = [
    "GTCUSDT", "OMGUSDT", "KLAYUSDT", "MULTIUSDT", "FTMUSDT",   # delisted-truncation
    "LUNA2USDT", "USTCUSDT", "CVCUSDT", "WAVESUSDT", "HNTUSDT",  # severely-crashed survivors
]


def delisting_inclusive_attempt(*, max_calls: int = 8) -> dict[str, Any]:
    """探 Bybit 公開 REST 是否能 $0 回 DELISTED linear symbol 的歷史 klines。

    為什麼：survivor panel 結構性排除「真歸零/下市」；若能 $0 抓到真死名的歷史 klines，
    就能注入真死亡事件（比 G2 合成 MC 更真）。若不 $0-feasible（REST 不回下市 symbol），
    則明標並以 G2 MC 當 proxy（mandate：絕不付費）。
    """
    probe = []
    feasible_any = False
    for sym in KNOWN_DELISTED_LINEAR:
        rows = ext._fetch_klines_rest(sym, max_calls=max_calls)
        err = rows[0]["_rest_error"] if rows else "empty"
        n = len([r for r in rows if r.get("_rest_error") is None])
        first = rows[0]["date"] if rows else None
        last = rows[-1]["date"] if rows else None
        min_low = min((r["low"] for r in rows), default=None) if rows else None
        # 「真死」啟發：last_day 遠早於 now（>180d）AND 抓到 bars。
        is_dead = (last is not None and
                   (dt.date.today() - dt.date.fromisoformat(last)).days > 180)
        if n > 0:
            feasible_any = True
        probe.append({
            "symbol": sym, "n_bars": n, "rest_error": err,
            "first_day": first, "last_day": last, "min_low": min_low,
            "looks_delisted_dead": bool(is_dead and n > 0),
        })
    return {
        "feasible_zero_cost": feasible_any,
        "probed": probe,
        "note": ("若 feasible_zero_cost=True 且有 looks_delisted_dead symbol → REST 服務下市歷史，"
                 "可注入真死亡；否則 G2 合成 death-spiral MC 是 proxy（mandate：不付費）。"),
    }


# ---------------------------------------------------------------------------
# delisting-inclusive PANEL（注入真死亡名，REST 實證可 $0 抓）
# ---------------------------------------------------------------------------

def build_delisting_inclusive_panel(
    merged_survivors: dict[str, list[dict[str, Any]]], *, max_calls: int = 8,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """在 26-survivor merged panel 上注入 REST 可抓的真死亡/真重崩名（非 prod PG）。

    為什麼：survivor panel 結構性排除真歸零/下市。REST 實證能 $0 回這些名的歷史
    klines（probe 證）→ 注入真實「接刀 → 後續崩到截止/近零」事件，比合成 MC 真實。
    DELISTED-truncation 名（last_day 遠早於 global）= survivorship-correct 退出（最後可得 bar
    結算），深-K 接刀在它們臨終前 = realized 大虧計入。
    """
    panel = dict(merged_survivors)
    injected = []
    for s in REAL_DEATH_INCLUSIVE_NAMES:
        if s in panel:
            continue
        rows = ext._fetch_klines_rest(s, max_calls=max_calls)
        clean = [{"date": r["date"], "open": r["open"], "high": r["high"],
                  "low": r["low"], "close": r["close"], "turnover": r.get("turnover")}
                 for r in rows if r.get("_rest_error") is None]
        clean.sort(key=lambda x: x["date"])
        if not clean:
            injected.append({"symbol": s, "n_bars": 0, "skipped": "rest_empty"})
            continue
        panel[s] = clean
        first, last = clean[0]["date"], clean[-1]["date"]
        min_low = min(b["low"] for b in clean)
        crash_ratio = min_low / clean[0]["open"] if clean[0]["open"] else None
        injected.append({"symbol": s, "n_bars": len(clean), "first_day": first, "last_day": last,
                         "min_low": min_low, "crash_ratio_vs_first_open": crash_ratio})
    return panel, {"n_survivors": len(merged_survivors), "n_injected": len(panel) - len(merged_survivors),
                   "injected": injected}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def run_gates(conn, *, do_delisting: bool, n_partitions: int) -> dict[str, Any]:
    merged, funding, btc_fwd, btc_regime, meta = build_merged_klines(conn)

    # best_fn config（從 prior extend_full.json 已知 K15N1 C5 nf20；此處重算確認以求自洽）。
    best_fn_cfg = {"k": 0.15, "hold": 1, "cap": 5, "notional_frac": 0.20}

    # === G1：per-macro-regime attribution + leave-one-crash-out ===
    # 最重要：保守 anchor K15N3 C3（mandate 點名的 decisive config）。
    g1_anchor = regime_attribution_and_loo(
        merged, funding, btc_fwd, btc_regime, k=0.15, hold=3, cap=3,
        label="conservative_anchor_K15N3C3", seed=20260618)
    # best_fn 也跑 G1（chosen operating point）。
    g1_best = regime_attribution_and_loo(
        merged, funding, btc_fwd, btc_regime, k=0.15, hold=1, cap=5,
        label="best_fn_K15N1C5", seed=20260619)
    # K10/K20 anchor 對照。
    g1_k10 = regime_attribution_and_loo(
        merged, funding, btc_fwd, btc_regime, k=0.10, hold=3, cap=3,
        label="K10N3C3", seed=20260620)
    g1_k20 = regime_attribution_and_loo(
        merged, funding, btc_fwd, btc_regime, k=0.20, hold=3, cap=3,
        label="K20N3C3", seed=20260621)

    # === G2：fixed-notional death-spiral MC ===
    g2 = run_g2(merged, funding, btc_fwd, btc_regime, best_fn_cfg=best_fn_cfg)

    # === G3：DSR + PBO/CSCV over 720-cell grid ===
    # 720 cell = K(3) × N(4) × stop(5) × cap(4) × nf(3) = 720（與 extend_history grid 對齊）；
    # 但 stop 對 fixed-notional 日報酬無影響（fixed-notional 無 stop 概念）→ 真正獨立 Sharpe
    # 維度是 K×N×cap×nf = 3×4×4×3 = 144 unique fixed-notional 日報酬序列。誠實揭露：720 是
    # 名目試驗數（grid cell），144 是 fixed-notional 下實際不同序列，effective-N（真獨立 regime）
    # ~10-15。三個數都報。
    grid_cells: list[dict[str, Any]] = []
    for k in (0.10, 0.15, 0.20):
        for hold in (1, 2, 3, 5):
            for cap in (1, 3, 5, "unlimited"):
                for nf in (0.05, 0.10, 0.20):
                    grid_cells.append({"k": k, "hold": hold, "cap": cap, "nf": nf,
                                       "label": "K%dN%dC%s_nf%g" % (int(k * 100), hold, cap, nf)})
    chosen_label = "K15N1C5_nf0.2"
    anchor_label = "K15N3C3_nf0.1"
    g3_dsr = run_g3_dsr(merged, funding, btc_fwd, btc_regime, grid_cells=grid_cells,
                        chosen_label=chosen_label, anchor_label=anchor_label,
                        n_trials=720, effective_n=12)
    aligned = build_aligned_cell_matrix(merged, funding, btc_fwd, btc_regime, grid_cells=grid_cells)
    g3_pbo = run_g3_pbo_cscv(aligned, n_partitions=n_partitions)

    # === delisting-inclusive attempt + REAL death-inclusive panel re-run ===
    delisting = delisting_inclusive_attempt() if do_delisting else {"skipped": True}
    delisting_panel_result: dict[str, Any] = {"skipped": True}
    if do_delisting:
        # 注入真死亡名 → 在 death-inclusive panel 上重跑 G1 anchor + G2（真死亡取代/補強合成 MC）。
        panel, inj_meta = build_delisting_inclusive_panel(merged)
        # BTC helpers 不變（BTCUSDT 在 survivor 集）；funding 只覆蓋 survivor → 死亡名 funding=0
        # （conservative-favorable，已標）。
        g1_anchor_dead = regime_attribution_and_loo(
            panel, funding, btc_fwd, btc_regime, k=0.15, hold=3, cap=3,
            label="conservative_anchor_K15N3C3_DEATH_INCLUSIVE", seed=20260622)
        g2_dead = run_g2(panel, funding, btc_fwd, btc_regime, best_fn_cfg=best_fn_cfg)
        delisting_panel_result = {
            "panel_meta": inj_meta,
            "g1_anchor_death_inclusive": g1_anchor_dead,
            "g2_death_inclusive": g2_dead,
            "note": ("真 delisted/重崩名注入後重跑：G1 看 edge 是否仍 survive leave-one-crash-out、"
                     "G2 看 baseline（含真死亡）fixed-notional maxDD + 再疊合成 MC 是否仍 p95<=25%。"),
        }

    return {
        "gates_version": GATES_VERSION,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "data_meta": meta,
        "params": {
            "macro_crash_regimes": MACRO_CRASH_REGIMES,
            "survivable_maxdd": surv.SURVIVABLE_MAXDD,
            "death_terminal_ret": surv.DEATH_TERMINAL_RET,
            "death_stress_seeds": surv.DEATH_STRESS_SEEDS,
            "grid_nominal_trials": len(grid_cells),
            "grid_unique_fixed_notional_series": "K(3)xN(4)xcap(4)xnf(3)=144 (stop 對 fixed-notional 無效)",
            "effective_n_honest": 12,
            "maker_fee_bps": base.MAKER_FEE_BPS, "taker_fee_bps": base.TAKER_FEE_BPS,
        },
        "g1_regime_attribution": {
            "conservative_anchor_K15N3C3": g1_anchor,
            "best_fn_K15N1C5": g1_best,
            "K10N3C3": g1_k10,
            "K20N3C3": g1_k20,
        },
        "g2_death_spiral_fixed_notional": g2,
        "g3_dsr": g3_dsr,
        "g3_pbo_cscv": g3_pbo,
        "delisting_inclusive_attempt": delisting,
        "delisting_inclusive_panel": delisting_panel_result,
    }


def write_artifact(report: dict[str, Any], *, out_path: Optional[str]) -> str:
    if out_path is None:
        root = os.path.join(ext._data_root(), "research", "tail_dislocation_meanrev")
        os.makedirs(root, exist_ok=True)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = os.path.join(root, f"prepilot_gates_{stamp}.json")
    else:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    blob = json.dumps(report, indent=2, sort_keys=True, default=str)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(blob)
    sha = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    with open(out_path + ".sha256", "w", encoding="utf-8") as fh:
        fh.write(sha + "  " + os.path.basename(out_path) + "\n")
    return out_path


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="尾部錯位 alpha 三個 pre-pilot $0 gate（G1/G2/G3 + delisting attempt）")
    ap.add_argument("--out", default=None)
    ap.add_argument("--delisting", action="store_true", help="跑 delisting-inclusive REST feasibility probe")
    ap.add_argument("--partitions", type=int, default=10, help="CSCV partition 數 S（偶數）")
    args = ap.parse_args(argv)

    conn = base.connect_pg()
    try:
        report = run_gates(conn, do_delisting=args.delisting, n_partitions=args.partitions)
    finally:
        conn.close()
    out = write_artifact(report, out_path=args.out)

    print(f"[{GATES_VERSION}] artifact -> {out}")
    dm = report["data_meta"]
    print(f"data: n_sym={dm['n_symbols']} span={dm['span_years']:.2f}yr range={dm['global_first']}..{dm['global_last']}")

    # G1 摘要。
    print("\n=== G1 leave-one-crash-out (conservative anchor K15N3C3) ===")
    a = report["g1_regime_attribution"]["conservative_anchor_K15N3C3"]
    print(f"full day-clustered boot_t={a['full_day_clustered_boot_t']:.3f} ci={a['full_day_clustered_ci95']} "
          f"n_days={a['full_n_distinct_days']}")
    print(f"n_independent_crash_regimes_with_fills={a['n_independent_crash_regimes_with_fills']}")
    print(f"regime_rank_by_net_pnl={a['regime_rank_by_net_pnl']}")
    print(f"top_cum_share={a['top_cumulative_net_pnl_share']}")
    for l in a["leave_one_crash_out"]:
        bt = l["boot_t"]
        print(f"  remove {l['removed_rank']} ({l['excluded']}): boot_t={bt:.3f} ci={l['ci95']} "
              f"ci_excl0={l['ci_excludes_zero']} survives={l['survives']}" if bt is not None
              else f"  remove {l['removed_rank']}: boot_t=None")

    # G2 摘要。
    print("\n=== G2 fixed-notional death-spiral MC (p95/p99 maxDD) ===")
    for r in report["g2_death_spiral_fixed_notional"]["results"]:
        lbl = r["config"]["label"]
        print(f"  {lbl}: baseline_maxDD={r['baseline_fn_maxdd']:.3f}")
        for s in r["death_spiral_mc"]:
            print(f"     cond_death={s['cond_death_rate_per_entry']:.0%}: p95_maxDD={s['fn_maxdd_stressed_p95']:.3f} "
                  f"p99={s['fn_maxdd_stressed_p99']:.3f} surv_p95={s['survivable_p95']}")

    # G3 摘要。
    print("\n=== G3 DSR + PBO/CSCV ===")
    dsr = report["g3_dsr"]
    if "error" not in dsr:
        for key in ("chosen_best_fn", "conservative_anchor"):
            e = dsr[key]
            print(f"  {key} ({e.get('label')}): SR_hat={e.get('sharpe_per_period_hat'):.4f} "
                  f"skew={e.get('skew'):.2f} kurt={e.get('kurtosis_pearson'):.2f} "
                  f"DSR_pval(720)={e.get('dsr_pvalue_full_trials')} "
                  f"DSR_pval(effN=12)={e.get('dsr_pvalue_effective_n')} "
                  f"survives_effN={e.get('dsr_survives_effective_n')}")
    pbo = report["g3_pbo_cscv"]
    if "error" not in pbo:
        print(f"  PBO={pbo['pbo']:.3f} ({pbo['overfit_verdict']}) over {pbo['n_combinations']} CSCV combos, "
              f"{pbo['n_configs']} configs × {pbo['n_days']} days")
    else:
        print(f"  PBO error: {pbo}")

    # delisting。
    d = report["delisting_inclusive_attempt"]
    if not d.get("skipped"):
        print(f"\n=== delisting attempt: feasible_zero_cost={d['feasible_zero_cost']} ===")
        for p in d["probed"]:
            print(f"  {p['symbol']}: n_bars={p['n_bars']} last={p['last_day']} "
                  f"dead={p['looks_delisted_dead']} err={p['rest_error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
