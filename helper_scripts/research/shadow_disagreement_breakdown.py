#!/usr/bin/env python3
"""shadow disagreement reason breakdown — read-only PG analysis tool.
shadow 分歧原因分布報告 — 唯讀 PG 分析工具。

MODULE_NOTE (EN): Wave 3 EDGE-P2-flip T2 helper. Reads
`learning.decision_shadow_exits` over a configurable lookback window and
reports the distribution of `disagreement_reason` strings for rows where
`disagreed = TRUE` (Combine Layer != Physical baseline). Provides both an
overall reason histogram and a per-strategy breakdown so operator / QC can
see whether disagreement clusters around one strategy or one root cause
before deciding to keep / revert / extend EDGE-P2-flip Phase 2 observation.

Phase 1a dormant path: when 24h rows = 0 (shadow_enabled=false default),
emits "Phase 1a dormant (shadow_enabled=false)" and exits 0 — operator
can run this tool any time without false alarms.

Pure read-only: no writes, no business-logic mutation. Lazy-imports
psycopg2 inside main() (CLAUDE.md §七 hygiene rule — no PG connect at
import time so unit tests / smoke tests do not hard-depend on DB).

Output channels:
  - stdout: markdown (default) or JSON envelope
  - JSON artifact: /tmp/openclaw/shadow_disagreement_breakdown.json
    (always written, regardless of --output-format choice; for downstream
     pipe / cron consumption)
  - stderr: INFO logging (kept off stdout for pipe-friendliness)

Edge cases:
  - 24h rows = 0 → emit "Phase 1a dormant (shadow_enabled=false)" + exit 0
  - per-strategy with n < 5 disagreed rows → list strategy total but
    skip reason-distribution detail (sample too small for trust)
  - DB connection failure → exit 2

MODULE_NOTE (中): Wave 3 EDGE-P2-flip T2 helper。讀
`learning.decision_shadow_exits` 指定窗口（預設 24h），對 disagreed=TRUE
的 row 報 `disagreement_reason` 分布（總體 + per-strategy）。EDGE-P2-flip
Phase 2 觀察期判斷「該繼續、回退還是延期」前的證據工具。

Phase 1a dormant 路徑：當 24h 行數 = 0（shadow_enabled=false 預設），輸出
「Phase 1a dormant」並 exit 0 — operator 隨時可跑無虛警。

純唯讀：不寫資料、不動業務邏輯。psycopg2 lazy-import 進 main()
（CLAUDE.md §七 hygiene — import 期不連 PG，方便測試 / smoke）。

輸出通道：
  - stdout：markdown（預設）或 JSON envelope
  - JSON artifact：/tmp/openclaw/shadow_disagreement_breakdown.json
    （無論 --output-format 為何都寫；供下游 pipe / cron 消費）
  - stderr：INFO logging（不污染 stdout 便於 pipe）

Edge cases：
  - 24h rows = 0 → 輸出 dormant + exit 0
  - per-strategy n<5 disagreed 行：顯示 strategy total 但跳過 reason 細節
    （樣本太小不可信）
  - DB 連線失敗 → exit 2

Usage:
  OPENCLAW_DATABASE_URL=postgresql://... \\
    python3 helper_scripts/research/shadow_disagreement_breakdown.py \\
      [--engine-mode demo] [--lookback-hours 24] \\
      [--output-format markdown] [--strategies grid_trading,ma_crossover]

Exit codes:
  0 = success (Phase 1a dormant counts as success)
  1 = success but data anomaly (e.g., disagreement_reason all NULL → schema drift)
  2 = DB connection error
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ─────────────────────────────────────────────────────────────────────────
# SQL templates (no PG connect at import time).
# SQL 模板（import 期不連 PG）。
# ─────────────────────────────────────────────────────────────────────────
#
# Notes / 備註：
#   - %s placeholder style (psycopg2 default — not :name).
#   - lookback_hours uses interval `'%s hours'` constructed from validated int.
#   - strategy_name = ANY(%s) so psycopg2 maps Python list → PG array
#     (placeholder count fixed = 1; safe vs IN (a,b,c,...) string-build).
#   - per RFC §9 #2: precise = matching, NOT prefix LIKE — collisions
#     between e.g. `grid_trading` vs `grid_oddity` would corrupt counts.

# Total + disagreed counts per (strategy, engine_mode); used for both the
# overall agreement metric and the per-strategy slice.
# 每 (strategy, engine_mode) 的 total + disagreed 行數，供整體 + per-strategy 用。
TOTALS_SQL = """
SELECT
    strategy_name,
    engine_mode,
    COUNT(*)::int                                   AS total,
    COUNT(*) FILTER (WHERE disagreed = TRUE)::int   AS disagreed_n
FROM learning.decision_shadow_exits
WHERE engine_mode = %s
  AND ts > now() - (%s || ' hours')::interval
  {strategy_filter}
GROUP BY strategy_name, engine_mode
ORDER BY total DESC, strategy_name ASC
"""

# Reason distribution: (strategy, reason) -> count for disagreed rows.
# Reason 分布：disagreed=TRUE 的 (strategy, reason) -> count。
REASONS_SQL = """
SELECT
    strategy_name,
    COALESCE(disagreement_reason, '(null)')::text   AS reason,
    COUNT(*)::int                                   AS n
FROM learning.decision_shadow_exits
WHERE engine_mode = %s
  AND ts > now() - (%s || ' hours')::interval
  AND disagreed = TRUE
  {strategy_filter}
GROUP BY strategy_name, reason
ORDER BY strategy_name ASC, n DESC, reason ASC
"""

# Strategies-filter sub-clause; only applied when --strategies is given.
# Strategies 過濾子句；只在 --strategies 提供時注入。
STRATEGY_FILTER_TEMPLATE = "AND strategy_name = ANY(%s)"


# ─────────────────────────────────────────────────────────────────────────
# DB helpers — mirror passive_wait_healthcheck.py + ma_crossover_counterfactual_replay.py
# DB 連線 — 沿用既有 helper 風格（ENV → DSN）。
# ─────────────────────────────────────────────────────────────────────────


def _build_dsn() -> str:
    """Build PG DSN from env, mirroring style in helper_scripts/db/passive_wait_healthcheck.py.
    從 env 構造 PG DSN，沿用 helper_scripts/db/passive_wait_healthcheck.py 風格。
    """
    return (
        os.environ.get("OPENCLAW_DATABASE_URL")
        or f"postgresql://{os.environ.get('POSTGRES_USER','')}"
        f":{os.environ.get('POSTGRES_PASSWORD','')}"
        f"@{os.environ.get('POSTGRES_HOST','127.0.0.1')}"
        f":{os.environ.get('POSTGRES_PORT','5432')}"
        f"/{os.environ.get('POSTGRES_DB','')}"
    )


def _open_conn():
    """Lazy import + open PG connection. Failure raises (caller handles exit 2).
    延遲載入並開 PG 連線；失敗向上拋（呼叫端轉 exit 2）。
    """
    import psycopg2  # type: ignore  # lazy: avoid import-time DB hard-dep

    dsn = _build_dsn()
    return psycopg2.connect(dsn)


# ─────────────────────────────────────────────────────────────────────────
# Aggregator: turn raw rows into structured envelope.
# 聚合器：原始 row → 結構化 envelope。
# ─────────────────────────────────────────────────────────────────────────


def aggregate_breakdown(
    totals_rows: list[tuple[Any, ...]],
    reason_rows: list[tuple[Any, ...]],
    sparse_threshold: int = 5,
) -> dict[str, Any]:
    """Combine totals + reason queries into a single structured envelope.

    Output structure:
      {
        "overall": {
          "total_rows": int,
          "disagreed_rows": int,
          "agreement_pct": float | None,    # None when total_rows == 0
        },
        "per_strategy": [
          {
            "strategy_name": str,
            "engine_mode": str,
            "total_rows": int,
            "disagreed_rows": int,
            "agreement_pct": float,
            "reason_distribution": [{"reason": str, "n": int, "pct": float}, ...]
              # — when disagreed_rows < sparse_threshold, list is replaced with
              #   single sentinel `{"reason": "(sample <5; suppressed)", ...}`.
          },
          ...
        ],
        "overall_reason_distribution": [{"reason": str, "n": int, "pct": float}, ...]
          # pooled across all strategies (always full, never suppressed)
      }

    將 totals + reason 兩 query 結果合成單一 envelope；per-strategy 樣本
    < sparse_threshold 時 reason 細節被 sentinel 取代避免噪音。
    """
    # Per-strategy totals.
    # Per-strategy 總計。
    per_strategy: list[dict[str, Any]] = []
    overall_total = 0
    overall_disagreed = 0
    for row in totals_rows:
        name = str(row[0] or "(null)")
        engine_mode = str(row[1] or "")
        total = int(row[2] or 0)
        disagreed_n = int(row[3] or 0)
        overall_total += total
        overall_disagreed += disagreed_n
        agree_pct = 100.0 * (total - disagreed_n) / total if total > 0 else 0.0
        per_strategy.append({
            "strategy_name": name,
            "engine_mode": engine_mode,
            "total_rows": total,
            "disagreed_rows": disagreed_n,
            "agreement_pct": agree_pct,
            "reason_distribution": [],  # filled below
        })

    # Index per_strategy by name for fast lookup when merging reasons.
    # 用 strategy_name 建索引便於合併 reason 行。
    by_name: dict[str, dict[str, Any]] = {p["strategy_name"]: p for p in per_strategy}

    # Reason distribution — group by strategy + global pool.
    # Reason 分布 — 按 strategy 分組 + 全局合併。
    reasons_by_strategy: dict[str, list[tuple[str, int]]] = {}
    overall_reason_counts: dict[str, int] = {}
    for row in reason_rows:
        name = str(row[0] or "(null)")
        reason = str(row[1] or "(null)")
        n = int(row[2] or 0)
        reasons_by_strategy.setdefault(name, []).append((reason, n))
        overall_reason_counts[reason] = overall_reason_counts.get(reason, 0) + n

    for name, rdists in reasons_by_strategy.items():
        target = by_name.get(name)
        if target is None:
            # Strategy appeared in reasons query but not totals — unusual but
            # possible if totals filter is tighter (it isn't here, but safe).
            # Skip rather than fabricate a totals entry.
            # Strategy 在 reasons 但不在 totals — 不偽造 entry，跳過。
            continue
        d_total = target["disagreed_rows"]
        if d_total < sparse_threshold:
            # Sample too small — replace with sentinel + total marker.
            # 樣本太小 — 用 sentinel + total 標記取代。
            target["reason_distribution"] = [{
                "reason": f"(disagreed_n={d_total}; <{sparse_threshold}, suppressed)",
                "n": d_total,
                "pct": 100.0,
            }]
            continue
        # Sort by n desc, then reason asc.
        # 按 n 降序、reason 升序排序。
        rdists.sort(key=lambda x: (-x[1], x[0]))
        target["reason_distribution"] = [
            {"reason": r, "n": n, "pct": 100.0 * n / d_total}
            for r, n in rdists
        ]

    # Build overall reason distribution from pooled counts.
    # 用合併計數構建總體 reason 分布。
    overall_reasons_sorted = sorted(
        overall_reason_counts.items(),
        key=lambda kv: (-kv[1], kv[0]),
    )
    overall_reason_dist = [
        {"reason": r, "n": n, "pct": 100.0 * n / overall_disagreed if overall_disagreed > 0 else 0.0}
        for r, n in overall_reasons_sorted
    ]

    return {
        "overall": {
            "total_rows": overall_total,
            "disagreed_rows": overall_disagreed,
            "agreement_pct": (
                100.0 * (overall_total - overall_disagreed) / overall_total
                if overall_total > 0 else None
            ),
        },
        "per_strategy": per_strategy,
        "overall_reason_distribution": overall_reason_dist,
    }


# ─────────────────────────────────────────────────────────────────────────
# Output formatters.
# 輸出格式化。
# ─────────────────────────────────────────────────────────────────────────


def render_markdown(envelope: dict[str, Any], lookback_hours: int, engine_mode: str) -> str:
    """Render envelope as a markdown report (overall + per-strategy + reasons).
    渲染 envelope 為 markdown 報告（總體 + per-strategy + reasons）。
    """
    lines: list[str] = []
    overall = envelope["overall"]
    per_strategy = envelope["per_strategy"]
    overall_reasons = envelope["overall_reason_distribution"]

    lines.append(f"# shadow disagreement breakdown — {engine_mode} {lookback_hours}h")
    lines.append("")

    # Overall summary line.
    # 總體 summary 行。
    if overall["total_rows"] == 0:
        lines.append("**Phase 1a dormant** (shadow_enabled=false; "
                     "decision_shadow_exits empty within window).")
        lines.append("")
        lines.append(f"_window: now() - {lookback_hours}h, engine_mode={engine_mode}_")
        return "\n".join(lines)

    agree_pct = overall["agreement_pct"]
    lines.append(
        f"**Overall**: total={overall['total_rows']}, "
        f"disagreed={overall['disagreed_rows']}, "
        f"agreement={agree_pct:.2f}%"
    )
    lines.append("")

    # Per-strategy table.
    # Per-strategy 表。
    lines.append("## Per-strategy")
    lines.append("")
    headers = ["strategy", "engine_mode", "total", "disagreed", "agreement"]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for p in per_strategy:
        lines.append("| " + " | ".join([
            p["strategy_name"],
            p["engine_mode"],
            str(p["total_rows"]),
            str(p["disagreed_rows"]),
            f"{p['agreement_pct']:.2f}%",
        ]) + " |")
    lines.append("")

    # Per-strategy reason breakdown (only when disagreed_n >= sparse_threshold).
    # Per-strategy reason 細節（disagreed_n >= sparse_threshold 才出）。
    has_any_reason = any(p["reason_distribution"] for p in per_strategy)
    if has_any_reason:
        lines.append("## Per-strategy disagreement reasons")
        lines.append("")
        for p in per_strategy:
            if not p["reason_distribution"]:
                continue
            lines.append(f"### {p['strategy_name']} (disagreed={p['disagreed_rows']})")
            lines.append("")
            r_headers = ["reason", "count", "pct"]
            lines.append("| " + " | ".join(r_headers) + " |")
            lines.append("|" + "|".join(["---"] * len(r_headers)) + "|")
            for rd in p["reason_distribution"]:
                lines.append("| " + " | ".join([
                    rd["reason"],
                    str(rd["n"]),
                    f"{rd['pct']:.1f}%",
                ]) + " |")
            lines.append("")

    # Overall reason distribution (always full, even when per-strategy suppressed).
    # 總體 reason 分布（永遠完整，per-strategy 被 sentinel 替換時仍可看）。
    if overall_reasons:
        lines.append("## Overall disagreement reasons (pooled)")
        lines.append("")
        r_headers = ["reason", "count", "pct"]
        lines.append("| " + " | ".join(r_headers) + " |")
        lines.append("|" + "|".join(["---"] * len(r_headers)) + "|")
        for rd in overall_reasons:
            lines.append("| " + " | ".join([
                rd["reason"],
                str(rd["n"]),
                f"{rd['pct']:.1f}%",
            ]) + " |")
        lines.append("")

    lines.append(f"_window: now() - {lookback_hours}h, engine_mode={engine_mode}_")
    return "\n".join(lines)


def render_json(envelope: dict[str, Any], lookback_hours: int, engine_mode: str) -> str:
    """Render envelope + window metadata as JSON.
    渲染 envelope + window 元資料為 JSON。
    """
    payload = {
        "schema_version": "edge_p2_flip.shadow_disagreement_breakdown.v1",
        "window": {
            "lookback_hours": lookback_hours,
            "engine_mode": engine_mode,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        **envelope,
    }
    return json.dumps(payload, indent=2, default=str)


# ─────────────────────────────────────────────────────────────────────────
# CLI + main.
# CLI 與主流程。
# ─────────────────────────────────────────────────────────────────────────


def _build_query(strategies: list[str] | None) -> tuple[str, str]:
    """Return (totals_sql, reasons_sql) with strategy filter applied if given.
    視 --strategies 是否提供回傳已注入過濾的 SQL。
    """
    if strategies:
        sub = STRATEGY_FILTER_TEMPLATE
    else:
        sub = ""
    return (
        TOTALS_SQL.format(strategy_filter=sub),
        REASONS_SQL.format(strategy_filter=sub),
    )


def _write_artifact(payload_json: str, log: logging.Logger) -> None:
    """Write JSON artifact to /tmp/openclaw/ regardless of stdout format.

    Uses OPENCLAW_DATA_DIR if set (Mac dev / non-default Linux), falling back
    to /tmp/openclaw on Linux defaults. Failure to write is non-fatal —
    log a warning and continue (artifact is convenience, not contract).

    無論 stdout 格式如何，都寫 JSON artifact 到 /tmp/openclaw/。
    OPENCLAW_DATA_DIR 設了走那裡（Mac dev / 非預設 Linux），否則 fallback。
    寫失敗不致命（log warning 後繼續）；artifact 是便利不是契約。
    """
    runtime_dir = Path(
        os.environ.get(
            "OPENCLAW_DATA_DIR",
            "/tmp/openclaw" if os.name != "nt" else str(Path.home() / "openclaw"),
        )
    )
    artifact = runtime_dir / "shadow_disagreement_breakdown.json"
    try:
        runtime_dir.mkdir(parents=True, exist_ok=True)
        artifact.write_text(payload_json, encoding="utf-8")
        log.info("artifact written: %s (%d bytes)", artifact, len(payload_json))
    except Exception as exc:
        log.warning("artifact write failed (%s): %s — stdout output is authoritative",
                    artifact, exc)


def main() -> int:
    """CLI entrypoint. Returns process exit code per docstring spec.
    CLI 入口；exit code 依 docstring 規格。
    """
    parser = argparse.ArgumentParser(
        description="shadow disagreement breakdown (Wave 3 EDGE-P2-flip T2).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 shadow_disagreement_breakdown.py --engine-mode demo\n"
            "  python3 shadow_disagreement_breakdown.py --lookback-hours 168\n"
            "  python3 shadow_disagreement_breakdown.py --strategies grid_trading,ma_crossover\n"
            "  python3 shadow_disagreement_breakdown.py --output-format json\n"
        ),
    )
    parser.add_argument(
        "--engine-mode", default="demo",
        choices=["demo", "live_demo", "paper", "live"],
        help="engine_mode column filter (default: demo).",
    )
    parser.add_argument(
        "--lookback-hours", type=int, default=24,
        help="window of ts > now() - N hours (default: 24).",
    )
    parser.add_argument(
        "--output-format", default="markdown",
        choices=["markdown", "json"],
        help="stdout format (default: markdown). JSON artifact always written to "
             "$OPENCLAW_DATA_DIR/shadow_disagreement_breakdown.json regardless.",
    )
    parser.add_argument(
        "--strategies", default=None,
        help="optional comma-separated strategy_name whitelist. Default: ALL. "
             "Precise match (NOT prefix) per RFC §9 #2 — `grid_trading` won't "
             "match `grid_oddity`.",
    )

    args = parser.parse_args()

    # Logging: simple INFO-level format, stderr (so stdout stays clean for piping).
    # Logging：簡單 INFO 格式，stderr 輸出，stdout 保留純結果便於 pipe。
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stderr,
    )
    log = logging.getLogger("shadow_disagreement_breakdown")

    if args.lookback_hours <= 0:
        log.error("--lookback-hours must be > 0 (got %s)", args.lookback_hours)
        return 2

    strategies = (
        [s.strip() for s in args.strategies.split(",") if s.strip()]
        if args.strategies else None
    )
    totals_sql, reasons_sql = _build_query(strategies)

    # ── Connect / fetch ──
    # 連線並取資料；連線錯 → exit 2。
    try:
        conn = _open_conn()
    except Exception as e:
        log.error("DB connection failed: %s", e)
        return 2

    totals_rows: list[tuple[Any, ...]] = []
    reason_rows: list[tuple[Any, ...]] = []
    try:
        with conn.cursor() as cur:
            # Existence guard — same defensive pattern as healthcheck [15].
            # 存在性守衛 — 與 [15] 同模式。
            try:
                cur.execute("SELECT to_regclass('learning.decision_shadow_exits') IS NOT NULL")
                exists = cur.fetchone()[0]
            except Exception as e:
                log.error("decision_shadow_exits existence check failed: %s", e)
                return 2
            if not exists:
                log.error("learning.decision_shadow_exits missing — V021 not applied")
                return 2

            # Bind args order: (engine_mode, lookback_hours, [strategies]).
            # Bind args 順序：(engine_mode, lookback_hours, [strategies])。
            base_args: tuple = (args.engine_mode, str(args.lookback_hours))
            if strategies:
                base_args = base_args + (strategies,)

            log.info("fetching totals (engine=%s lookback=%dh strategies=%s)",
                     args.engine_mode, args.lookback_hours,
                     strategies if strategies else "ALL")
            cur.execute(totals_sql, base_args)
            totals_rows = list(cur.fetchall())
            log.info("totals rows: %d", len(totals_rows))

            log.info("fetching reasons distribution")
            cur.execute(reasons_sql, base_args)
            reason_rows = list(cur.fetchall())
            log.info("reasons rows: %d", len(reason_rows))
    finally:
        conn.close()

    envelope = aggregate_breakdown(totals_rows, reason_rows)
    overall = envelope["overall"]

    # Always write JSON artifact (regardless of stdout format).
    # 永遠寫 JSON artifact（與 stdout 格式無關）。
    json_payload = render_json(envelope, args.lookback_hours, args.engine_mode)
    _write_artifact(json_payload, log)

    # stdout output.
    # stdout 輸出。
    if args.output_format == "markdown":
        print(render_markdown(envelope, args.lookback_hours, args.engine_mode))
    else:  # json
        print(json_payload)

    # Phase 1a dormant — exit 0 (no disagreement to analyze, by design).
    # Phase 1a dormant — exit 0（設計上無分歧可分析）。
    if overall["total_rows"] == 0:
        log.info("Phase 1a dormant (decision_shadow_exits 24h=0); exit 0")
        return 0

    # Data anomaly: all disagreements have NULL reason — schema drift signal.
    # 資料異常：所有 disagreement 都是 NULL reason — schema drift 訊號。
    if overall["disagreed_rows"] > 0:
        non_null_reasons = [
            r for r in envelope["overall_reason_distribution"]
            if r["reason"] != "(null)"
        ]
        if not non_null_reasons:
            log.warning(
                "all %d disagreed rows have NULL disagreement_reason — "
                "writer regression suspected (V021 schema column unwired?)",
                overall["disagreed_rows"],
            )
            return 1

    log.info("done: total=%d, disagreed=%d, agreement=%.2f%%, strategies=%d",
             overall["total_rows"], overall["disagreed_rows"],
             overall["agreement_pct"] or 0.0,
             len(envelope["per_strategy"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
