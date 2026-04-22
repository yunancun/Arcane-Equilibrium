#!/usr/bin/env python3
"""Passive-wait pipeline healthcheck.
被動等待管線健康檢查。

MODULE_NOTE (EN): Single-command check that 7 key runtime data pipelines
are actually producing data, versus silently failing under fail-open
error handling. Triggered by 2026-04-22 P1-19 RCA which discovered that
phys_lock / MICRO-PROFIT / label backfill pipelines had all been silently
dead for 2.5–3 days despite "passive wait" TODOs treating them as healthy.

MODULE_NOTE (中): 單命令檢查 7 個關鍵 runtime 資料管線實際有資料流入，
識破 fail-open 下的 silent failure。由 2026-04-22 P1-19 RCA 觸發 — 當時
發現 phys_lock / MICRO-PROFIT / label backfill 三條管線都 silent-dead
2.5-3 天，但 TODO 卻敘述為「被動等待中（健康）」。

Usage:
  POSTGRES_USER=... POSTGRES_PASSWORD=... POSTGRES_DB=... \\
    python3 helper_scripts/db/passive_wait_healthcheck.py

Exit codes:
  0 = all checks PASS (all 7 pipelines healthy)
  1 = ≥1 check FAIL (pipeline silent-dead or anomalous)
  2 = DB connection error

Checks（each prints PASS / FAIL / WARN with a one-line explanation）:
  [1] close_fills_24h                — baseline: close fills on demo in last 24h
  [2] label_backfill_ratio           — learning.decision_features writes vs close_fills ratio
  [3] exit_features_writer_ratio     — learning.exit_features writes vs close_fills (EXIT-FEATURES-TABLE-1)
  [4] phys_lock_runtime              — trading.fills 'risk_close:phys_lock_*' count (TRACK-P v2)
  [5] micro_profit_fire              — trading.fills 'risk_close:COST EDGE*' count (MICRO-PROFIT-FIX-1)
  [6] trailing_stop_fire             — trading.fills 'risk_close:TRAILING STOP%' count
  [7] edge_estimates_freshness       — settings/edge_estimates.json mtime < 90min

Rule of thumb: close_fills_24h ≥ 10 且 labels 1:1 ratio ≥ 0.8 且 exit_features
1:1 ratio ≥ 0.8 且 ≥1 risk-layer exit mechanism (#4/5/6) fire ≥ 1 time.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---- connection ----

def _get_conn():
    import psycopg2  # type: ignore
    dsn = (
        os.environ.get("OPENCLAW_DATABASE_URL")
        or f"postgresql://{os.environ.get('POSTGRES_USER','')}"
        f":{os.environ.get('POSTGRES_PASSWORD','')}"
        f"@{os.environ.get('POSTGRES_HOST','127.0.0.1')}"
        f":{os.environ.get('POSTGRES_PORT','5432')}"
        f"/{os.environ.get('POSTGRES_DB','')}"
    )
    return psycopg2.connect(dsn)


# ---- single-query helpers ----

def _scalar(cur, sql: str) -> int:
    cur.execute(sql)
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


# ---- individual checks ----

def check_close_fills_24h(cur) -> tuple[str, str, int]:
    """[1] Baseline: demo close_fills in last 24h. All other ratios built on this."""
    n = _scalar(cur,
        "SELECT COUNT(*) FROM trading.fills "
        "WHERE ts > now() - interval '24 hours' "
        "AND engine_mode = 'demo' AND realized_pnl != 0"
    )
    if n == 0:
        return ("FAIL", f"demo 24h close_fills = 0 — P1-10 fee drag 極度壓制 or engine dead", n)
    if n < 5:
        return ("WARN", f"demo 24h close_fills = {n} — extremely low sample, ratios unreliable", n)
    return ("PASS", f"demo 24h close_fills = {n}", n)


def check_label_backfill_ratio(cur, close_fills: int) -> tuple[str, str]:
    """[2] learning.decision_features labels vs close_fills (target ratio ≥ 0.5)."""
    n = _scalar(cur,
        "SELECT COUNT(*) FROM learning.decision_features "
        "WHERE label_filled_at > now() - interval '24 hours' "
        "AND label_net_edge_bps IS NOT NULL "
        "AND engine_mode = 'demo'"
    )
    if close_fills == 0:
        return ("WARN", f"no close_fills baseline, labels={n} unscoreable")
    ratio = n / close_fills if close_fills else 0.0
    if ratio < 0.3:
        return ("FAIL", f"labels_24h={n} vs close_fills={close_fills} (ratio {ratio:.2f}) — backfill stalled")
    if ratio < 0.7:
        return ("WARN", f"labels_24h={n} vs close_fills={close_fills} (ratio {ratio:.2f}) — partial backfill")
    return ("PASS", f"labels_24h={n} vs close_fills={close_fills} (ratio {ratio:.2f})")


def check_exit_features_writer(cur, close_fills: int) -> tuple[str, str]:
    """[3] EXIT-FEATURES-TABLE-1 Rust writer — expect 1:1 with close_fills."""
    n = _scalar(cur,
        "SELECT COUNT(*) FROM learning.exit_features "
        "WHERE ts > now() - interval '24 hours' AND engine_mode = 'demo'"
    )
    if close_fills == 0:
        return ("WARN", f"no close_fills baseline, exit_features={n} unscoreable")
    delta = abs(n - close_fills)
    if delta > max(3, close_fills // 3):
        return ("FAIL", f"exit_features_24h={n} vs close_fills={close_fills} (delta {delta}) — writer broken")
    return ("PASS", f"exit_features_24h={n} vs close_fills={close_fills} (delta {delta})")


def check_phys_lock_runtime(cur) -> tuple[str, str]:
    """[4] TRACK-P v2 phys_lock runtime fire rate — expect ≥1 per 24h if edge populated."""
    n_24h = _scalar(cur,
        "SELECT COUNT(*) FROM trading.fills "
        "WHERE ts > now() - interval '24 hours' "
        "AND engine_mode = 'demo' "
        "AND strategy_name LIKE 'risk_close:phys_lock_%'"
    )
    n_7d = _scalar(cur,
        "SELECT COUNT(*) FROM trading.fills "
        "WHERE ts > now() - interval '7 days' "
        "AND engine_mode = 'demo' "
        "AND strategy_name LIKE 'risk_close:phys_lock_%'"
    )
    if n_7d == 0:
        return ("FAIL", f"phys_lock_* 7d=0 — Priority 6 runtime 完全 dead (P0-13/P0-14)")
    if n_24h == 0:
        return ("WARN", f"phys_lock_* 24h=0 (7d={n_7d}) — 近期停火，查 edge_estimates / atr coverage")
    return ("PASS", f"phys_lock_* 24h={n_24h} (7d={n_7d})")


def check_micro_profit_fire(cur) -> tuple[str, str]:
    """[5] MICRO-PROFIT-FIX-1 (legacy COST EDGE gate) — expect ≥1 per 24h if alive."""
    n_24h = _scalar(cur,
        "SELECT COUNT(*) FROM trading.fills "
        "WHERE ts > now() - interval '24 hours' "
        "AND engine_mode = 'demo' "
        "AND strategy_name LIKE 'risk_close:COST EDGE%'"
    )
    n_7d = _scalar(cur,
        "SELECT COUNT(*) FROM trading.fills "
        "WHERE ts > now() - interval '7 days' "
        "AND engine_mode = 'demo' "
        "AND strategy_name LIKE 'risk_close:COST EDGE%'"
    )
    if n_7d == 0:
        return ("FAIL", f"COST EDGE 7d=0 — MICRO-PROFIT gate 已被 T3 deprecated (P0-15)，現在靠 PHYS-LOCK")
    if n_24h == 0:
        return ("WARN", f"COST EDGE 24h=0 (7d={n_7d}) — stale; 確認 runtime 是否 rebuild 後 gate 被註解")
    return ("PASS", f"COST EDGE 24h={n_24h} (7d={n_7d})")


def check_trailing_stop_fire(cur) -> tuple[str, str]:
    """[6] TRAILING STOP fire rate — expect ≥1 per 7d."""
    n_7d = _scalar(cur,
        "SELECT COUNT(*) FROM trading.fills "
        "WHERE ts > now() - interval '7 days' "
        "AND engine_mode = 'demo' "
        "AND strategy_name LIKE 'risk_close:TRAILING STOP%'"
    )
    if n_7d == 0:
        return ("FAIL", f"TRAILING STOP 7d=0 — 所有倉位的 peak 都 < activation_pct?")
    return ("PASS", f"TRAILING STOP 7d={n_7d}")


def check_edge_estimates_freshness() -> tuple[str, str]:
    """[7] settings/edge_estimates.json mtime < 90 min (scheduler hourly)."""
    base = Path(os.environ.get("OPENCLAW_BASE_DIR", str(Path.home() / "BybitOpenClaw/srv")))
    p = base / "settings" / "edge_estimates.json"
    if not p.exists():
        return ("FAIL", f"edge_estimates.json 不存在 at {p}")
    mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
    age_min = (datetime.now(tz=timezone.utc) - mtime).total_seconds() / 60.0
    if age_min > 90:
        return ("FAIL", f"edge_estimates.json age {age_min:.0f} min — scheduler 可能掛了")
    if age_min > 65:
        return ("WARN", f"edge_estimates.json age {age_min:.0f} min — 略過 hourly 節奏")
    # P0-14 RCA 2026-04-22 修正：JSON 是 flat map（key = "{strategy}::{symbol}"），不是
    # 「cells array」。原 `.get("cells", [])` 永遠回 [] 空。改成 flat map 遍歷，並同時
    # 計算 strategy prefix 分布（驗 H4 — `bybit_sync` / `orphan_*` / `dust_*` 等
    # runtime owner_strategy 是否有對應 cell）。
    # P0-14 RCA 2026-04-22 fix: JSON is a flat map (key = "{strategy}::{symbol}")
    # not a "cells array". The old `.get("cells", [])` always returned []. This
    # walks the flat map and also breaks down by strategy prefix to verify H4
    # (whether runtime owner_strategy values — bybit_sync / orphan_* / dust_* —
    # have matching cells at all).
    try:
        data = json.load(p.open())
        # Flat map path — skip meta keys (anything starting with "_" or matching
        # known aggregate names like "grand_mean_bps" / "generated_at").
        meta_keys = {"grand_mean_bps", "generated_at", "n_total", "version"}
        cell_items = {
            k: v for k, v in data.items()
            if isinstance(v, dict) and not k.startswith("_") and k not in meta_keys
        }
        total = len(cell_items)
        populated = sum(
            1 for v in cell_items.values() if v.get("shrunk_bps") is not None
        )
        # strategy prefix breakdown（用於 P0-14 H4 判斷）
        prefixes: dict[str, int] = {}
        for k in cell_items:
            prefix = k.split("::", 1)[0] if "::" in k else k
            prefixes[prefix] = prefixes.get(prefix, 0) + 1
        prefix_summary = ",".join(f"{p}:{n}" for p, n in sorted(prefixes.items()))
        cov = populated / total if total else 0.0
        msg = (f"edge_estimates.json age {age_min:.0f}m, "
               f"populated {populated}/{total} ({cov:.1%}), "
               f"prefixes[{prefix_summary or 'NONE'}]")
        if total == 0:
            return ("FAIL", msg + " — JSON 無 cells（scheduler first-run 或完全停寫）")
        # H4 指紋：若 runtime 有 bybit_sync/orphan/dust 持倉但 JSON 無對應 prefix
        known_dormant = {"bybit_sync", "orphan_adopted", "orphan_frozen", "dust_frozen"}
        missing_dormant = known_dormant - set(prefixes.keys())
        if missing_dormant:
            return ("WARN", msg + f" — P0-14 H4 indicator：JSON 缺 {sorted(missing_dormant)} prefix cells")
        if cov < 0.3:
            return ("WARN", msg + " — low coverage")
        return ("PASS", msg)
    except Exception as e:
        return ("WARN", f"edge_estimates.json age {age_min:.0f}m, parse error: {e}")


# ---- main ----

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quiet", action="store_true", help="Only print non-PASS lines")
    args = ap.parse_args()

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"Passive-wait healthcheck @ {now} UTC")
    print("=" * 70)

    try:
        conn = _get_conn()
    except Exception as e:
        print(f"[FATAL] DB connect failed: {e}")
        return 2

    results: list[tuple[str, str, str]] = []  # (check_name, status, msg)
    try:
        with conn.cursor() as cur:
            # [1] baseline
            s, m, close_fills = check_close_fills_24h(cur)
            results.append(("[1] close_fills_24h", s, m))

            # [2] labels
            s, m = check_label_backfill_ratio(cur, close_fills)
            results.append(("[2] label_backfill", s, m))

            # [3] exit_features writer
            s, m = check_exit_features_writer(cur, close_fills)
            results.append(("[3] exit_features_writer", s, m))

            # [4] phys_lock
            s, m = check_phys_lock_runtime(cur)
            results.append(("[4] phys_lock_runtime", s, m))

            # [5] micro_profit
            s, m = check_micro_profit_fire(cur)
            results.append(("[5] micro_profit_fire", s, m))

            # [6] trailing stop
            s, m = check_trailing_stop_fire(cur)
            results.append(("[6] trailing_stop_fire", s, m))
    finally:
        conn.close()

    # [7] filesystem check
    s, m = check_edge_estimates_freshness()
    results.append(("[7] edge_estimates_freshness", s, m))

    # output
    any_fail = False
    any_warn = False
    for name, status, msg in results:
        if args.quiet and status == "PASS":
            continue
        print(f"{status:4s} {name:<36s} {msg}")
        if status == "FAIL":
            any_fail = True
        elif status == "WARN":
            any_warn = True

    print("=" * 70)
    if any_fail:
        print("SUMMARY: FAIL — ≥1 pipeline silent-dead，查 docs/worklogs/2026-04-22--passive_wait_silent_fail_audit.md")
        return 1
    if any_warn:
        print("SUMMARY: WARN — 非致命但需關注")
        return 0
    print("SUMMARY: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
