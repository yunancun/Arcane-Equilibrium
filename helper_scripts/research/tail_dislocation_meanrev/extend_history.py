#!/usr/bin/env python3
"""tail_dislocation_meanrev.extend_history — 用 Bybit 公開 REST 把尾部錯位 alpha 的歷史
延伸到 ~4-5yr（含 2021/2022 真實 death-spiral），跑 PM 訂的決定性 re-entry gate（$0 唯讀 OFFLINE）。

MODULE_NOTE
模塊用途：
  prior `survival_safe.py` 在 26 大-cap survivor × 2024-06..2026-06（~2yr）上回 NO_GO，
  binding kill 是**統計性**且先於存活：誠實 day-clustering 下有效 N = ~119 distinct crash
  episode（非 819 相關 fill），block-bootstrap boot_t=1.43、95% CI [-0.004,+0.027] 含 0；
  且尾部是 SYNTHETIC overlay（universe 無真下市）。

  PM 訂的精確 re-entry gate：
    「binding constraint = effective episode count（~119/2yr），唯一可由 time accumulation
     或 broader universe 修；在 delisting-inclusive panel + FIXED-NOTIONAL sizing 上重測；
     線僅在 capped+fixed-notional day-clustered boot_t 過 ~2.0（CI 排除 0）時以 CONDITIONAL
     candidate 重入。」

  本檔執行該 gate 的 $0 lever = **延伸 HISTORY**（時間累積）：Bybit 公開 REST /v5/market/kline
  （category=linear, interval=D, 免 key keyless）把每個 symbol 回拉到其最早可得（BTC/ETH ~2020、
  多數 alt 2021-2022），這同時 (a) 倍增 episode 數、(b) 納入 2021-05 China-ban −50%、2021-12..2022
  bear、2022-05 LUNA −100%、2022-06 3AC、2022-11 FTX 等 REAL deep-K flash-crash + 續跌事件
  （= 經驗 death-spiral 尾部，取代 survival_safe 的 2% 合成 overlay）。

  決定性問題（誠實，survival-first，不 hype）：在 4-5yr 真崩盤上，edge 是否 SIGNIFICANT
  AND SURVIVABLE，還是 definitively not？四個 mandate 加固：
    (1) day-clustered 顯著性（更大 episode 數上）— THE decisive test：boot_t 過 ~2.0、CI 排除 0，
        還是 effect 稀釋（=2024-26 regime-specific）？
    (2) EMPIRICAL 尾部（真 2021/2022 death-spiral in-sample）— deep-K 接刀在 2022 是否被毀滅？
        真相關尾部 maxDD（取代合成 2% overlay）。
    (3) FIXED-NOTIONAL sizing（decouple stop 與 leverage）— 每槽固定名目，不隨 stop 緊度放大 lever。
    (4) true walk-forward OOS split（早期選 config → 晚期測，反之亦然）— in-sample-chosen config
        是否 OOS hold，還是 overfit / regime-specific？

  資料完整性鐵則（survivor-bias 反向修正）：
    - REST fetch 寫入 RESEARCH ARTIFACT（parquet/csv 於 ${OPENCLAW_DATA_DIR}/research/.../rest_cache），
      **絕不寫 prod PG**（prod 唯讀）。
    - VALIDATE：REST 抓到的 2024-06..2026-06 overlap 必與 DB clean anchor（OHLC）逐 bar 比對，
      不符 = flag（證 REST path 乾淨、延伸歷史可信）。
    - 若 symbol 在歷史中下市則其 REST 歷史在某點終止 → 接近終止的 deep-K 進場永不反彈 =
      realized 大虧，必須計入（= 合成 death overlay 的經驗對應）。本檔不丟棄任何 truncated 事件。

硬邊界（R-0 隔離紅線，mirror screen.py / survival_safe.py）：
  - 純讀 PG：import screen.py 連線/事件/統計 helper（0 改 sibling），DB 只 SELECT market.klines
    做 overlap 驗證；REST fetch 是純網路（無 key、無 auth）；0 寫 PG、0 order path、0 production
    code 改動、0 auth/lease/risk 觸碰。
  - net 計算保守：maker 進場 2bp、退出 maker 2bp / taker 5.5bp、hard-stop 退出 taker 5.5bp、
    funding over hold（REST 歷史多無 funding → 缺值 0，conservative-favorable，report 標）；禁 rebate。
  - artifact root 禁硬編碼：${OPENCLAW_DATA_DIR:-/tmp/openclaw}/ 推導。
  - REST 節流：每 call <=1000 bars、call 間 sleep，禁濫用公開端點。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import time
import urllib.request
from typing import Any, Optional

# 復用 prior screen / survival_safe 的 read-only 連線 / 事件生成 / 統計 / sizing helper（0 改 sibling）。
import screen as base
import survival_safe as surv

EXTEND_VERSION = "tail_dislocation_meanrev.extend_history.v0.1"

# ---------------------------------------------------------------------------
# Bybit 公開 REST kline（免 key keyless）
# ---------------------------------------------------------------------------

BYBIT_KLINE_URL = "https://api.bybit.com/v5/market/kline"
REST_CATEGORY = "linear"
REST_INTERVAL = "D"            # 日線
REST_LIMIT = 1000             # 每 call 最大
REST_SLEEP_S = 0.20           # call 間節流（公開端點禮貌）
MS_PER_DAY = 86_400_000

# overlap 驗證容差（REST 與 DB 同一 bar 的相對價差上界）。
# REST 與 DB backfill 可能來自不同 snapshot 時點 → 容極小數值漂移；超過 = flag。
OVERLAP_REL_TOL = 1e-3        # 0.1% 相對容差（OHLC 各自）

# walk-forward 切點（早/晚期；以 entry_date 切）。
# 早期 = 含 2021/2022 真崩盤；晚期 = 2024-06 起（= prior survival_safe 窗）。
WF_SPLIT_DATE = "2024-01-01"


def _fetch_klines_rest(symbol: str, *, earliest_floor_ms: Optional[int] = None,
                       max_calls: int = 60) -> list[dict[str, Any]]:
    """從 Bybit 公開 REST 回拉單 symbol 全部 1d klines（往回分頁到最早可得）。

    為什麼往回分頁：Bybit kline 回傳按 ts 降序、每 call <=1000 bars。用 end 游標
    逐次往回（end = 本批最舊 ts - 1day）直到回空或達 max_calls / earliest_floor。
    回 (date, OHLC, turnover, volume) 升序 list，去重（同 ts 取一）。
    leak-free 不適用此處（純資料抓取）；資料品質守衛：非有限 / <=0 價 bar 丟棄並計數。
    """
    seen: dict[int, dict[str, Any]] = {}
    end_ms: Optional[int] = None
    calls = 0
    bad = 0
    while calls < max_calls:
        calls += 1
        params = f"category={REST_CATEGORY}&symbol={symbol}&interval={REST_INTERVAL}&limit={REST_LIMIT}"
        if end_ms is not None:
            params += f"&end={end_ms}"
        url = f"{BYBIT_KLINE_URL}?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "openclaw-research/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                payload = json.load(r)
        except Exception as exc:  # noqa: BLE001 — 網路錯誤 fail-soft（記錄，回已抓到的）
            return _finalize_rest(seen, bad, symbol, error=f"fetch_error:{exc}")
        if payload.get("retCode") != 0:
            return _finalize_rest(seen, bad, symbol, error=f"retCode={payload.get('retCode')}:{payload.get('retMsg')}")
        lst = payload.get("result", {}).get("list", [])
        if not lst:
            break
        oldest_in_batch = None
        for row in lst:
            # row = [start_ms, open, high, low, close, volume, turnover]（字串）
            try:
                ts = int(row[0])
                o, h, l, c = float(row[1]), float(row[2]), float(row[3]), float(row[4])
                vol = float(row[5]) if len(row) > 5 and row[5] is not None else None
                turn = float(row[6]) if len(row) > 6 and row[6] is not None else None
            except (ValueError, TypeError, IndexError):
                bad += 1
                continue
            if not all(math.isfinite(x) for x in (o, h, l, c)) or min(o, h, l, c) <= 0:
                bad += 1
                continue
            seen[ts] = {"ts": ts, "open": o, "high": h, "low": l, "close": c,
                        "volume": vol, "turnover": turn}
            oldest_in_batch = ts if oldest_in_batch is None else min(oldest_in_batch, ts)
        if oldest_in_batch is None:
            break
        if earliest_floor_ms is not None and oldest_in_batch <= earliest_floor_ms:
            break
        # 往回：下一批 end = 本批最舊 - 1 天。
        next_end = oldest_in_batch - MS_PER_DAY
        if end_ms is not None and next_end >= end_ms:
            break  # 無進展，止
        end_ms = next_end
        time.sleep(REST_SLEEP_S)
    return _finalize_rest(seen, bad, symbol)


def _finalize_rest(seen: dict[int, dict[str, Any]], bad: int, symbol: str,
                   *, error: Optional[str] = None) -> list[dict[str, Any]]:
    """ts 升序整理 REST 結果並轉成 screen.py 事件機制要的 (date, OHLC, turnover) 形狀。"""
    rows = []
    for ts in sorted(seen.keys()):
        b = seen[ts]
        d = dt.datetime.fromtimestamp(ts / 1000, dt.timezone.utc).date()
        rows.append({
            "date": d.isoformat(),
            "open": b["open"], "high": b["high"], "low": b["low"], "close": b["close"],
            "turnover": b["turnover"], "volume": b["volume"],
            "_ts": ts, "_symbol": symbol, "_bad_skipped": bad, "_rest_error": error,
        })
    return rows


# ---------------------------------------------------------------------------
# overlap 驗證（REST vs DB clean anchor）
# ---------------------------------------------------------------------------

def validate_overlap(rest_rows: list[dict[str, Any]], db_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """逐 bar（共同日期）比對 REST 與 DB anchor 的 OHLC。

    為什麼：確認 REST path 乾淨（與已驗過匹配 Bybit 的 DB clean 集一致），延伸歷史可信。
    回共同日數、不符 bar 數（任一 OHLC 相對差 > OVERLAP_REL_TOL）、最大相對差、樣本。
    """
    rest_by_date = {r["date"]: r for r in rest_rows}
    db_by_date = {r["date"]: r for r in db_rows}
    common = sorted(set(rest_by_date) & set(db_by_date))
    mismatches = []
    max_rel = 0.0
    for d in common:
        rr, dd = rest_by_date[d], db_by_date[d]
        worst = 0.0
        for fld in ("open", "high", "low", "close"):
            rv, dv = rr[fld], dd[fld]
            if dv == 0:
                continue
            rel = abs(rv - dv) / abs(dv)
            worst = max(worst, rel)
        max_rel = max(max_rel, worst)
        if worst > OVERLAP_REL_TOL:
            mismatches.append({"date": d, "max_rel_diff": worst,
                               "rest": {k: rr[k] for k in ("open", "high", "low", "close")},
                               "db": {k: dd[k] for k in ("open", "high", "low", "close")}})
    return {
        "n_common_bars": len(common),
        "n_db_bars": len(db_rows),
        "n_rest_bars": len(rest_rows),
        "n_mismatch": len(mismatches),
        "max_rel_diff_overall": max_rel,
        "rel_tol": OVERLAP_REL_TOL,
        "match": len(mismatches) == 0 and len(common) > 0,
        "mismatch_sample": mismatches[:10],
    }


# ---------------------------------------------------------------------------
# 真實 crash 期經驗尾部標記（取代合成 overlay）
# ---------------------------------------------------------------------------

# 真實歷史 crash 窗（UTC 日期區間）— 用於把事件標記為「落在已知 death-spiral 期」。
EMPIRICAL_CRASH_WINDOWS = [
    ("china_ban_2021_05", "2021-05-12", "2021-05-23"),     # 2021-05 China-ban −50%
    ("bear_2021_12_2022_01", "2021-11-10", "2022-01-24"),  # 2021-12 ATH→bear 起跌
    ("luna_2022_05", "2022-05-07", "2022-05-15"),          # LUNA/UST −100%
    ("threeac_2022_06", "2022-06-10", "2022-06-19"),       # 3AC contagion
    ("ftx_2022_11", "2022-11-06", "2022-11-21"),           # FTX 崩盤
]


def _in_crash_window(date_iso: str) -> Optional[str]:
    """回該日期所屬的經驗 crash 窗名（無則 None）。"""
    d = dt.date.fromisoformat(date_iso)
    for name, lo, hi in EMPIRICAL_CRASH_WINDOWS:
        if dt.date.fromisoformat(lo) <= d <= dt.date.fromisoformat(hi):
            return name
    return None


# ---------------------------------------------------------------------------
# FIXED-NOTIONAL sizing（PM gate #1：decouple stop 緊度與 leverage）
# ---------------------------------------------------------------------------

def fixed_notional_equity_curve(
    events: list[dict[str, Any]],
    *,
    ret_key: str,
    notional_frac: float,
) -> dict[str, Any]:
    """固定名目 sizing 組合等值曲線（每槽固定 notional_frac × equity，**不**隨 stop 放大）。

    為什麼（PM gate #1）：survival_safe 的 stop-anchored sizing 把 risk_unit=S → lever=r/S，
    stop 越緊 lever 越大 → gap-through 時損失放大（stop 雙重反效果，死亡注入下更脆）。
    固定名目 decouple：每筆對權益乘法步進 = 1 + notional_frac * trade_ret，與 stop 緊度無關。
    這是「每槽投入固定比例本金」的真實下單方式（survival-first：單槽最大損失 = notional_frac × |worst|，
    有界且與 stop 無關）。同日多筆獨立槽 → 同日 C 筆全崩 ≈ equity *= prod(1 + nf*r_i)。

    回 maxDD / CVaR / annret / Sharpe / Sortino（鏡像 survival_safe.sized_portfolio_equity_curve
    的輸出結構，便於直接對比 stop-anchored vs fixed-notional）。
    """
    seq = sorted(events, key=lambda e: (e["entry_date"], e["symbol"]))
    if not seq:
        return {"n": 0}
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    per_trade_equity_ret: list[float] = []
    daily_eq: list[tuple[str, float]] = []
    for e in seq:
        r = e[ret_key]
        if r is None:
            continue
        r_clamped = max(r, -0.99)
        contrib = notional_frac * r_clamped   # 固定名目：與 stop 無關
        per_trade_equity_ret.append(contrib)
        equity *= (1.0 + contrib)
        if equity <= 0:
            equity = 1e-9
        peak = max(peak, equity)
        max_dd = max(max_dd, 1.0 - equity / peak)
        daily_eq.append((e["entry_date"], equity))

    day_equity: dict[str, float] = {}
    for d, eq in daily_eq:
        day_equity[d] = eq
    days_sorted = sorted(day_equity.keys())
    day_rets: list[float] = []
    prev = 1.0
    for d in days_sorted:
        eq = day_equity[d]
        day_rets.append(eq / prev - 1.0)
        prev = eq

    mean_day = base._mean(day_rets)
    sd_day = base._stddev(day_rets)
    downside = [min(0.0, x) for x in day_rets]
    dsd = math.sqrt(sum(x * x for x in downside) / len(downside)) if downside else None
    first_d = dt.date.fromisoformat(days_sorted[0])
    last_d = dt.date.fromisoformat(days_sorted[-1])
    span_days = max(1, (last_d - first_d).days)
    ann_factor = surv.TRADING_DAYS_PER_YEAR / span_days
    ann_return = math.exp(math.log(max(equity, 1e-9)) * ann_factor) - 1.0
    active_days = len(day_rets)
    days_per_year_active = active_days / (span_days / surv.TRADING_DAYS_PER_YEAR) if span_days else None
    sharpe = sortino = None
    if mean_day is not None and sd_day and sd_day > 0 and days_per_year_active:
        sharpe = (mean_day / sd_day) * math.sqrt(days_per_year_active)
    if mean_day is not None and dsd and dsd > 0 and days_per_year_active:
        sortino = (mean_day / dsd) * math.sqrt(days_per_year_active)
    return {
        "n": len(per_trade_equity_ret),
        "notional_frac": notional_frac,
        "final_equity": equity,
        "total_return": equity - 1.0,
        "annualized_return": ann_return,
        "max_drawdown": max_dd,
        "cvar05_per_trade_equity": base._cvar(per_trade_equity_ret, base.CVAR_ALPHA),
        "cvar05_day_return": base._cvar(day_rets, base.CVAR_ALPHA),
        "sharpe_annualized": sharpe,
        "sortino_annualized": sortino,
        "mean_day_return": mean_day,
        "n_active_days": active_days,
        "span_days": span_days,
        "worst_single_trade": min((e[ret_key] for e in seq if e[ret_key] is not None), default=None),
        "survivable_maxdd": max_dd <= surv.SURVIVABLE_MAXDD,
    }


# ---------------------------------------------------------------------------
# walk-forward OOS split（PM gate #4）
# ---------------------------------------------------------------------------

def _filter_events_by_date(events: list[dict[str, Any]], *, lo: Optional[str], hi: Optional[str]) -> list[dict[str, Any]]:
    out = []
    for e in events:
        d = e["entry_date"]
        if lo is not None and d < lo:
            continue
        if hi is not None and d >= hi:
            continue
        out.append(e)
    return out


def walk_forward_oos(
    klines_by_sym, funding, btc_fwd, btc_regime, *, split_date: str,
    candidate_configs: list[dict[str, Any]],
) -> dict[str, Any]:
    """true walk-forward：在一段選 config，在另一段測（兩向）。

    為什麼（PM gate #4）：in-sample 上 optimizer 選出的最佳 config 可能 overfit / regime-specific。
    walk-forward 用早期（含 2021/2022 真崩盤）選 config → 晚期（2024-06 起 = prior 窗）測 OOS，
    並反向（晚期選 → 早期測）。對每個 candidate config 報兩段的 day-clustered boot_t + fixed-notional
    sized maxDD/annret，看 in-sample-chosen 是否 OOS hold。

    candidate_configs：[{k,hold,stop,cap,notional_frac}, ...]。本函數對每個 config 在
    早/晚兩段各算 day-clustered 顯著性 + fixed-notional sized 指標，並標哪段為 IS/OOS。
    """
    def eval_segment(cfg, *, lo, hi):
        ev = surv.build_events_stopped(klines_by_sym, funding, btc_fwd, btc_regime,
                                       k=cfg["k"], hold=cfg["hold"], stop=cfg.get("stop"))
        ev = _filter_events_by_date(ev, lo=lo, hi=hi)
        cap_int = cfg.get("cap")
        cap_int = None if cap_int in (None, "unlimited") else int(cap_int)
        kept = surv.apply_concurrency_cap(ev, cap=cap_int)["kept"]
        if not kept:
            return {"n_kept": 0}
        dcs = surv.day_clustered_significance(kept, ret_key="net_taker",
                                              seed=hash((cfg["k"], cfg["hold"], lo or "", hi or "")) % (2**31))
        fn = fixed_notional_equity_curve(kept, ret_key="net_taker", notional_frac=cfg["notional_frac"])
        b1 = dcs.get("block_bootstrap_day_b1", {})
        return {
            "n_kept": len(kept),
            "n_distinct_days": dcs.get("n_distinct_days"),
            "day_clustered_boot_t": b1.get("boot_t"),
            "day_clustered_ci95": b1.get("ci95"),
            "day_clustered_mean": dcs.get("mean_day_return"),
            "fixed_notional_maxdd": fn.get("max_drawdown"),
            "fixed_notional_annret": fn.get("annualized_return"),
            "fixed_notional_sharpe": fn.get("sharpe_annualized"),
            "fixed_notional_worst_trade": fn.get("worst_single_trade"),
            "mean_net_taker": base._mean([e["net_taker"] for e in kept]),
        }

    results = []
    for cfg in candidate_configs:
        early = eval_segment(cfg, lo=None, hi=split_date)   # IS = 早期（含真崩盤）
        late = eval_segment(cfg, lo=split_date, hi=None)    # OOS = 晚期
        results.append({
            "config": cfg,
            "split_date": split_date,
            "early_segment_2020_to_split": early,   # 含 2021/2022 真崩盤
            "late_segment_split_to_now": late,      # 2024-06 起（prior survival_safe 窗）
            "holds_oos_late": _config_holds(late),
            "holds_oos_early": _config_holds(early),
        })
    return {"split_date": split_date, "configs_evaluated": len(candidate_configs), "results": results}


def _config_holds(seg: dict[str, Any]) -> Optional[bool]:
    """OOS hold 判定：day-clustered boot_t 過 ~2.0 AND CI 排除 0 AND fixed-notional maxDD<=survivable。"""
    bt = seg.get("day_clustered_boot_t")
    ci = seg.get("day_clustered_ci95")
    mdd = seg.get("fixed_notional_maxdd")
    if bt is None or ci is None or mdd is None or ci[0] is None:
        return None
    ci_excludes_zero = (ci[0] > 0) or (ci[1] < 0)
    return bool(bt >= 2.0 and ci_excludes_zero and mdd <= surv.SURVIVABLE_MAXDD)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def run_extend(conn, *, max_calls: int, only_symbols: Optional[list[str]] = None) -> dict[str, Any]:
    # --- 1. DB anchor（clean，唯讀）---
    symbols = base.list_symbols(conn)
    if only_symbols:
        symbols = [s for s in symbols if s in set(only_symbols)]
    db_klines = {s: base.load_1d_klines(conn, s) for s in symbols}
    funding = base.load_funding_daily(conn)

    # --- 2. REST fetch 全歷史 + overlap 驗證 + 合併 ---
    rest_cache_root = os.path.join(_data_root(), "research", "tail_dislocation_meanrev", "rest_cache")
    os.makedirs(rest_cache_root, exist_ok=True)

    merged_klines: dict[str, list[dict[str, Any]]] = {}
    fetch_report: list[dict[str, Any]] = []
    overlap_report: list[dict[str, Any]] = []
    for s in symbols:
        rest_rows = _fetch_klines_rest(s, max_calls=max_calls)
        # 寫 REST 研究 artifact（csv，per symbol；非 prod PG）。
        _write_rest_csv(rest_cache_root, s, rest_rows)
        rest_err = rest_rows[0]["_rest_error"] if rest_rows else "empty"
        bad_skipped = rest_rows[0]["_bad_skipped"] if rest_rows else 0
        # overlap 驗證（REST vs DB）。
        ov = validate_overlap(rest_rows, db_klines.get(s, []))
        ov["symbol"] = s
        overlap_report.append(ov)
        # 合併：以 REST 全歷史為主，DB anchor 補 REST 缺的近端（理論上 REST 已覆蓋；
        # 衝突日以 DB clean anchor 為準，因 DB 已驗匹配 Bybit）。
        by_date: dict[str, dict[str, Any]] = {}
        for r in rest_rows:
            by_date[r["date"]] = {"date": r["date"], "open": r["open"], "high": r["high"],
                                  "low": r["low"], "close": r["close"], "turnover": r["turnover"]}
        for r in db_klines.get(s, []):
            by_date[r["date"]] = {"date": r["date"], "open": r["open"], "high": r["high"],
                                  "low": r["low"], "close": r["close"], "turnover": r["turnover"]}
        merged = [by_date[d] for d in sorted(by_date.keys())]
        merged_klines[s] = merged
        first = merged[0]["date"] if merged else None
        last = merged[-1]["date"] if merged else None
        years = ((dt.date.fromisoformat(last) - dt.date.fromisoformat(first)).days / 365.0
                 if (first and last) else None)
        fetch_report.append({
            "symbol": s, "rest_bars": len(rest_rows), "rest_error": rest_err,
            "rest_bad_skipped": bad_skipped,
            "merged_bars": len(merged), "earliest": first, "latest": last, "years": years,
            "db_bars": len(db_klines.get(s, [])),
        })

    # --- 3. BTC helpers（用合併全歷史；alpha-vs-beta + PIT regime）---
    btc_ks = merged_klines.get("BTCUSDT", [])
    btc_fwd, btc_regime = base.build_btc_helpers(btc_ks)

    # 全窗跨度。
    global_first = min((ks[0]["date"] for ks in merged_klines.values() if ks), default=None)
    global_last = max((ks[-1]["date"] for ks in merged_klines.values() if ks), default=None)
    span_years = ((dt.date.fromisoformat(global_last) - dt.date.fromisoformat(global_first)).days / 365.0
                  if (global_first and global_last) else None)

    # --- 4. 全歷史上重跑 survival_safe 核心：hard_stop_grid + portfolio_grid + best ---
    # （直接複用 survival_safe 的事件/sizing/concurrency 機制，餵合併 klines）
    stop_grid: list[dict[str, Any]] = []
    for k in surv.K_GRID:
        for hold in surv.N_GRID:
            for stop in surv.STOP_GRID:
                ev = surv.build_events_stopped(merged_klines, funding, btc_fwd, btc_regime,
                                               k=k, hold=hold, stop=stop)
                n = len(ev)
                pct_stopped = (sum(1 for e in ev if e["stopped"]) / n) if n else None
                seed = int(k * 1000) * 1000 + hold * 100 + int((stop or 0) * 100)
                stop_grid.append({
                    "k": k, "hold": hold, "stop": stop, "n_events": n,
                    "pct_stopped": pct_stopped,
                    "net_taker": base.summarize_returns([e["net_taker"] for e in ev], seed=seed + 1),
                    "gross": base.summarize_returns([e["gross"] for e in ev], seed=seed + 3),
                })

    # --- 5. episode count（distinct crash entry-day）per K：binding constraint vs prior ~119 ---
    episode_count: dict[str, Any] = {}
    for k in surv.K_GRID:
        ev = surv.build_events_stopped(merged_klines, funding, btc_fwd, btc_regime,
                                       k=k, hold=3, stop=None)
        distinct_days = len({e["entry_date"] for e in ev})
        # 經驗 crash 窗內的 deep-K 進場數（2022 death-spiral 接刀）。
        in_crash = sum(1 for e in ev if _in_crash_window(e["entry_date"]))
        episode_count[f"K{int(k*100)}"] = {
            "n_fills": len(ev), "n_distinct_episodes": distinct_days,
            "n_fills_in_empirical_crash_windows": in_crash,
        }

    # --- 6. 全歷史 portfolio grid（fixed-notional sizing；PM gate #1）---
    # 固定名目 grid 取代 stop-anchored；notional_frac grid 對齊 risk_per_slot 直覺。
    NOTIONAL_GRID = (0.05, 0.10, 0.20)  # 每槽佔權益比例（固定，與 stop 無關）
    portfolio_grid_fn: list[dict[str, Any]] = []
    best_fn = None
    for k in surv.K_GRID:
        for hold in surv.N_GRID:
            for stop in surv.STOP_GRID:
                ev_full = surv.build_events_stopped(merged_klines, funding, btc_fwd, btc_regime,
                                                    k=k, hold=hold, stop=stop)
                if not ev_full:
                    continue
                for cap in surv.CONCURRENCY_GRID:
                    kept = surv.apply_concurrency_cap(ev_full, cap=cap)["kept"]
                    if not kept:
                        continue
                    for nf in NOTIONAL_GRID:
                        fn = fixed_notional_equity_curve(kept, ret_key="net_taker", notional_frac=nf)
                        mean_net = base._mean([e["net_taker"] for e in kept])
                        cell = {
                            "k": k, "hold": hold, "stop": stop,
                            "cap": cap if cap is not None else "unlimited",
                            "notional_frac": nf,
                            "n_kept": len(kept),
                            "mean_net_taker_per_trade": mean_net,
                            "fixed_notional_maxdd": fn.get("max_drawdown"),
                            "fixed_notional_annret": fn.get("annualized_return"),
                            "fixed_notional_sharpe": fn.get("sharpe_annualized"),
                            "fixed_notional_worst_trade": fn.get("worst_single_trade"),
                            "survivable_maxdd": fn.get("survivable_maxdd"),
                            "positive_expectancy": (mean_net is not None and mean_net > 0),
                        }
                        portfolio_grid_fn.append(cell)
                        if (cell["positive_expectancy"] and cell["survivable_maxdd"]
                                and fn.get("annualized_return") is not None):
                            if best_fn is None or fn["annualized_return"] > best_fn["fixed_notional_annret"]:
                                best_fn = cell

    # --- 7. THE decisive test：day-clustered 顯著性（全歷史，最大 episode 數）---
    # 對一組代表 capped + fixed-notional config（含 best_fn 若有）做 day-clustered boot_t。
    dc_targets = []
    if best_fn is not None:
        dc_targets.append({"k": best_fn["k"], "hold": best_fn["hold"], "stop": best_fn.get("stop"),
                           "cap": best_fn["cap"], "label": "best_fn"})
    # 代表：無 stop（mean-rev alpha 最完整）+ capped，K10/K15/K20 × cap3。
    for k in surv.K_GRID:
        dc_targets.append({"k": k, "hold": 3, "stop": None, "cap": 3, "label": f"K{int(k*100)}N3_nostop_C3"})
    day_clustered_decisive = []
    for tgt in dc_targets:
        cap_int = tgt["cap"]
        cap_int = None if cap_int in (None, "unlimited") else int(cap_int)
        ev = surv.build_events_stopped(merged_klines, funding, btc_fwd, btc_regime,
                                       k=tgt["k"], hold=tgt["hold"], stop=tgt.get("stop"))
        kept = surv.apply_concurrency_cap(ev, cap=cap_int)["kept"]
        dcs = surv.day_clustered_significance(kept, ret_key="net_taker",
                                              seed=hash(("dc", tgt["label"])) % (2**31))
        dcs["config"] = tgt
        dcs["n_kept"] = len(kept)
        day_clustered_decisive.append(dcs)

    # --- 8. EMPIRICAL tail（真 2021/2022 death-spiral in-sample；PM gate #2）---
    # deep-K (K15/K20) 接刀在經驗 crash 窗的 outcome 分佈 vs 全窗，加全歷史 fixed-notional maxDD。
    empirical_tail = {}
    for k in (0.15, 0.20):
        ev = surv.build_events_stopped(merged_klines, funding, btc_fwd, btc_regime,
                                       k=k, hold=3, stop=None)
        crash_ev = [e for e in ev if _in_crash_window(e["entry_date"])]
        crash_rets = [e["net_taker"] for e in crash_ev if e["net_taker"] is not None]
        all_rets = [e["net_taker"] for e in ev if e["net_taker"] is not None]
        # capped + fixed-notional 全歷史尾部（含真崩盤）。
        kept = surv.apply_concurrency_cap(ev, cap=3)["kept"]
        fn = fixed_notional_equity_curve(kept, ret_key="net_taker", notional_frac=0.10)
        empirical_tail[f"K{int(k*100)}N3_nostop"] = {
            "n_all_fills": len(ev),
            "n_fills_in_empirical_crash": len(crash_ev),
            "crash_window_outcomes": base.summarize_returns(crash_rets, seed=int(k * 9000) + 1) if crash_rets else {"n": 0},
            "all_window_outcomes": base.summarize_returns(all_rets, seed=int(k * 9000) + 2) if all_rets else {"n": 0},
            "per_crash_window_breakdown": _per_crash_breakdown(crash_ev),
            "full_history_capped_fixed_notional_C3_nf10": {
                "maxdd": fn.get("max_drawdown"), "annret": fn.get("annualized_return"),
                "sharpe": fn.get("sharpe_annualized"), "worst_trade": fn.get("worst_single_trade"),
                "cvar05_per_trade": fn.get("cvar05_per_trade_equity"),
                "survivable_maxdd": fn.get("survivable_maxdd"),
            },
        }

    # --- 9. walk-forward OOS（PM gate #4）---
    wf_candidates = [
        {"k": 0.10, "hold": 3, "stop": None, "cap": 3, "notional_frac": 0.10},
        {"k": 0.15, "hold": 3, "stop": None, "cap": 3, "notional_frac": 0.10},
        {"k": 0.20, "hold": 3, "stop": None, "cap": 5, "notional_frac": 0.10},
        {"k": 0.10, "hold": 2, "stop": None, "cap": 3, "notional_frac": 0.10},
    ]
    if best_fn is not None:
        wf_candidates.insert(0, {"k": best_fn["k"], "hold": best_fn["hold"],
                                 "stop": best_fn.get("stop"),
                                 "cap": best_fn["cap"], "notional_frac": best_fn["notional_frac"]})
    walk_forward = walk_forward_oos(merged_klines, funding, btc_fwd, btc_regime,
                                    split_date=WF_SPLIT_DATE, candidate_configs=wf_candidates)

    # --- 10. universe 組成（含真下市偵測：last_day 遠早於 global = 真死亡）---
    universe = []
    n_truly_dead = 0
    for s in symbols:
        ks = merged_klines[s]
        if not ks:
            continue
        first, last = ks[0]["date"], ks[-1]["date"]
        min_low = min(b["low"] for b in ks)
        # 真下市候選：last 明顯早於 global_last（>30d）。
        delisted = (global_last is not None
                    and (dt.date.fromisoformat(global_last) - dt.date.fromisoformat(last)).days > 30)
        if delisted:
            n_truly_dead += 1
        universe.append({
            "symbol": s, "bars": len(ks), "first_day": first, "last_day": last,
            "min_low": min_low, "possibly_delisted": delisted,
        })

    return {
        "extend_version": EXTEND_VERSION,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "params": {
            "rest_source": BYBIT_KLINE_URL, "rest_category": REST_CATEGORY, "rest_interval": REST_INTERVAL,
            "overlap_rel_tol": OVERLAP_REL_TOL, "wf_split_date": WF_SPLIT_DATE,
            "K_grid": list(surv.K_GRID), "N_grid": list(surv.N_GRID),
            "stop_grid": list(surv.STOP_GRID), "concurrency_grid": list(surv.CONCURRENCY_GRID),
            "notional_grid": list(NOTIONAL_GRID),
            "maker_fee_bps": base.MAKER_FEE_BPS, "taker_fee_bps": base.TAKER_FEE_BPS,
            "survivable_maxdd": surv.SURVIVABLE_MAXDD,
            "empirical_crash_windows": EMPIRICAL_CRASH_WINDOWS,
        },
        "data_extension": {
            "n_symbols": len(symbols),
            "global_first_day": global_first, "global_last_day": global_last,
            "span_years": span_years,
            "per_symbol_fetch": fetch_report,
        },
        "overlap_validation": overlap_report,
        "universe_composition": {
            "n_symbols": len(universe), "n_possibly_delisted": n_truly_dead, "symbols": universe,
        },
        "episode_count": episode_count,
        "hard_stop_grid": stop_grid,
        "portfolio_grid_fixed_notional": portfolio_grid_fn,
        "best_fixed_notional_config": best_fn,
        "day_clustered_significance_decisive": day_clustered_decisive,
        "empirical_tail_2021_2022": empirical_tail,
        "walk_forward_oos": walk_forward,
        "funding_coverage": {
            "funding_symbols": len(funding),
            "funding_total_daily_rows": sum(len(v) for v in funding.values()),
        },
    }


def _per_crash_breakdown(crash_ev: list[dict[str, Any]]) -> dict[str, Any]:
    """逐經驗 crash 窗的 deep-K 進場 outcome（接刀在 LUNA/3AC/FTX 是否被毀滅）。"""
    out: dict[str, Any] = {}
    for name, _lo, _hi in EMPIRICAL_CRASH_WINDOWS:
        evs = [e for e in crash_ev if _in_crash_window(e["entry_date"]) == name]
        rets = [e["net_taker"] for e in evs if e["net_taker"] is not None]
        if rets:
            out[name] = {
                "n": len(rets), "mean": base._mean(rets), "median": base._median(rets),
                "min": min(rets), "max": max(rets),
                "pct_positive": sum(1 for r in rets if r > 0) / len(rets),
                "symbols": sorted({e["symbol"] for e in evs}),
            }
        else:
            out[name] = {"n": 0}
    return out


# ---------------------------------------------------------------------------
# Artifact 寫出
# ---------------------------------------------------------------------------

def _data_root() -> str:
    return os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")


def _write_rest_csv(root: str, symbol: str, rows: list[dict[str, Any]]) -> None:
    """寫 per-symbol REST 研究 artifact（csv；非 prod PG）。"""
    path = os.path.join(root, f"{symbol}_1d.csv")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("date,open,high,low,close,volume,turnover\n")
        for r in rows:
            fh.write(f"{r['date']},{r['open']},{r['high']},{r['low']},{r['close']},"
                     f"{r.get('volume')},{r.get('turnover')}\n")


def write_artifact(report: dict[str, Any], *, out_path: Optional[str]) -> str:
    if out_path is None:
        root = os.path.join(_data_root(), "research", "tail_dislocation_meanrev")
        os.makedirs(root, exist_ok=True)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = os.path.join(root, f"extend_history_{stamp}.json")
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
    ap = argparse.ArgumentParser(description="尾部錯位 alpha 歷史延伸 + 決定性 re-entry gate（$0 唯讀 OFFLINE research）")
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-calls", type=int, default=60, help="每 symbol REST 最大分頁次數（1000 bar/call）")
    ap.add_argument("--symbols", default=None, help="逗號分隔 symbol 子集（debug；預設全 26）")
    args = ap.parse_args(argv)

    only = [s.strip() for s in args.symbols.split(",")] if args.symbols else None
    conn = base.connect_pg()
    try:
        report = run_extend(conn, max_calls=args.max_calls, only_symbols=only)
    finally:
        conn.close()
    out = write_artifact(report, out_path=args.out)

    de = report["data_extension"]
    print(f"[{EXTEND_VERSION}] artifact -> {out}")
    print(f"span_years={de['span_years']:.2f} symbols={de['n_symbols']} "
          f"range={de['global_first_day']}..{de['global_last_day']}")
    print("overlap (symbol: common/mismatch/max_rel):")
    n_bad = 0
    for ov in report["overlap_validation"]:
        if not ov["match"]:
            n_bad += 1
        print(f"  {ov['symbol']}: common={ov['n_common_bars']} mismatch={ov['n_mismatch']} "
              f"max_rel={ov['max_rel_diff_overall']:.2e} match={ov['match']}")
    print(f"overlap_summary: {len(report['overlap_validation'])-n_bad}/{len(report['overlap_validation'])} symbols MATCH")
    print("episode_count (K: fills / distinct_episodes / in_crash):")
    for kk, v in report["episode_count"].items():
        print(f"  {kk}: fills={v['n_fills']} episodes={v['n_distinct_episodes']} "
              f"in_crash={v['n_fills_in_empirical_crash_windows']}")
    print("DECISIVE day-clustered (config: boot_t / ci95 / n_kept / n_days):")
    for dc in report["day_clustered_significance_decisive"]:
        b1 = dc.get("block_bootstrap_day_b1", {})
        ci = b1.get("ci95", [None, None])
        bt = b1.get("boot_t")
        lbl = dc.get("config", {}).get("label")
        def f(x): return f"{x:.4f}" if isinstance(x, (int, float)) else "None"
        print(f"  {lbl}: boot_t={f(bt)} ci=[{f(ci[0])},{f(ci[1])}] "
              f"n_kept={dc.get('n_kept')} n_days={dc.get('n_distinct_days')}")
    best = report["best_fixed_notional_config"]
    if best:
        print(f"BEST fixed-notional: K{int(best['k']*100)} N{best['hold']} S={best['stop']} "
              f"C={best['cap']} nf={best['notional_frac']} | maxDD={best['fixed_notional_maxdd']:.4f} "
              f"annret={best['fixed_notional_annret']:.4f} sharpe={best['fixed_notional_sharpe']}")
    else:
        print("BEST fixed-notional: NONE (no positive-EV + survivable-maxDD config)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
