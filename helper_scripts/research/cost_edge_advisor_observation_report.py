#!/usr/bin/env python3
"""G3-09 Phase B observation report — cost_edge_advisor distribution analytics.

G3-09 Phase B 觀察期報告 — cost_edge_advisor 分佈分析。

MODULE_NOTE (EN):
  Generates the Phase B observation deliverable
  (``docs/audits/YYYY-MM-DD--cost_edge_advisor_phase_b_observation.md``)
  from rows in ``learning.cost_edge_advisor_log`` (V026 hypertable).
  Computes per-RFC §5.2 sections:

    * §1 Counters (24h rolling): evaluations_24h / triggers_24h /
      triggers_per_hour peak / triggers_per_week count
    * §2 Status distribution (% time in each status, last 7d)
    * §3 Ratio histogram (per engine_mode, ASCII chart bins
      -2.0 / -1.5 / -1.0 / -0.5 / 0 / 0.5)
    * §5.3 Heatmap proxies — per-status × per-engine_mode 6×3 grid +
      per-hour-of-day Trigger count heatmap (24h × 7day)
    * §6 Recommendation skeleton (Phase C readiness checklist with
      thresholds populated from observed counters)

  per-strategy / per-symbol heatmap deferred to Phase D (RFC §5.3).
  This report is the **single source of truth** PM uses to decide
  GO/NO-GO Phase C.

  Pure-Python + psycopg2; no IPC dependency. Cross-platform (Mac dev
  + Linux prod) — uses the same ``_get_conn`` pattern as the
  passive_wait_healthcheck runner.

MODULE_NOTE (中)：
  生成 Phase B 觀察期 deliverable
  （``docs/audits/YYYY-MM-DD--cost_edge_advisor_phase_b_observation.md``），
  資料來源 ``learning.cost_edge_advisor_log``（V026 hypertable）。
  按 RFC §5.2 計算 §1-§6 各章節。

  per-strategy / per-symbol heatmap 留給 Phase D（RFC §5.3）。本報告為
  PM 決定 GO/NO-GO Phase C 的單一真實來源。

  純 Python + psycopg2，無 IPC 依賴。跨平台（Mac dev + Linux prod）—
  使用與 passive_wait_healthcheck runner 相同的 ``_get_conn`` pattern。

Usage / 用法：

    # Default — write to docs/audits/<today>--cost_edge_advisor_phase_b_observation.md
    python3 helper_scripts/research/cost_edge_advisor_observation_report.py

    # Dry-run (print to stdout only, do not write file)
    python3 helper_scripts/research/cost_edge_advisor_observation_report.py --dry-run

    # Custom output path
    python3 helper_scripts/research/cost_edge_advisor_observation_report.py \\
        --out /tmp/observation.md
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# DB connection helper — mirrors helper_scripts/db/passive_wait_healthcheck/db.py
# DB 連線輔助 — 鏡射 passive_wait_healthcheck/db.py
# ---------------------------------------------------------------------------


def _get_conn():
    """Build a psycopg2 connection (priority: OPENCLAW_DATABASE_URL else POSTGRES_*).

    建 psycopg2 connection（優先 OPENCLAW_DATABASE_URL，否則 POSTGRES_* 五件組）。
    """
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


# ---------------------------------------------------------------------------
# §1 Counters — 24h rolling at report time.
# §1 計數器 — 報告時的 24h rolling。
# ---------------------------------------------------------------------------


def section_1_counters(cur) -> dict:
    """Return the §1 counters dict.

    回 §1 counters dict（evaluations_24h / triggers_24h / peak / weekly）。
    """
    out = {}
    # evaluations_24h — total cycle rows (transition + down-sampled cycle)
    # 24h 視窗內全部 cycle row 數（transition + down-sampled cycle）。
    cur.execute(
        "SELECT COUNT(*) FROM learning.cost_edge_advisor_log "
        "WHERE ts_ms > (extract(epoch from now()) * 1000)::BIGINT - 86400000"
    )
    out["evaluations_24h"] = int(cur.fetchone()[0] or 0)

    # triggers_24h — entry transitions (status='Trigger' AND transition_from IS NOT NULL)
    cur.execute(
        "SELECT COUNT(*) FROM learning.cost_edge_advisor_log "
        "WHERE ts_ms > (extract(epoch from now()) * 1000)::BIGINT - 86400000 "
        "  AND transition_from IS NOT NULL "
        "  AND status = 'Trigger'"
    )
    out["triggers_24h"] = int(cur.fetchone()[0] or 0)

    # triggers_per_hour peak (last 24h, group by hour)
    cur.execute(
        "SELECT COALESCE(MAX(c), 0) FROM ("
        "  SELECT COUNT(*) AS c FROM learning.cost_edge_advisor_log "
        "  WHERE ts_ms > (extract(epoch from now()) * 1000)::BIGINT - 86400000 "
        "    AND transition_from IS NOT NULL "
        "    AND status = 'Trigger' "
        "  GROUP BY (ts_ms / 3600000)::BIGINT"
        ") sub"
    )
    out["triggers_per_hour_peak"] = int(cur.fetchone()[0] or 0)

    # triggers_per_week
    cur.execute(
        "SELECT COUNT(*) FROM learning.cost_edge_advisor_log "
        "WHERE ts_ms > (extract(epoch from now()) * 1000)::BIGINT - 604800000 "
        "  AND transition_from IS NOT NULL "
        "  AND status = 'Trigger'"
    )
    out["triggers_per_week"] = int(cur.fetchone()[0] or 0)
    return out


def verdict_for_counter(name: str, value: int) -> str:
    """Map (counter, value) → "Healthy / WARN / FAIL" verdict per RFC §2.2.

    依 RFC §2.2 把 (counter, value) 映射到 "Healthy / WARN / FAIL" 判決。
    """
    if name == "evaluations_24h":
        if value >= 8000:
            return "Healthy"
        if value >= 4000:
            return "WARN"
        return "FAIL"
    if name == "triggers_24h":
        if value <= 10:
            return "Healthy"
        if value <= 50:
            return "WARN"
        return "FAIL"
    if name == "triggers_per_hour_peak":
        if value <= 5:
            return "Healthy"
        if value <= 20:
            return "WARN"
        return "FAIL"
    if name == "triggers_per_week":
        if value >= 1:
            return "Healthy"
        # WARN at 0 only when ratio histogram has near-threshold samples;
        # we treat unknown-context as Informational here (real verdict in §6).
        # 0 trigger 是否 WARN 須看 ratio histogram；此處標 Informational。
        return "Informational"
    return "Unknown"


# ---------------------------------------------------------------------------
# §2 Status distribution (% time in each status, last 7d).
# §2 Status 分佈（最近 7 天每個 status 的時間佔比）。
# ---------------------------------------------------------------------------


def section_2_status_distribution(cur) -> list[tuple[str, float, int]]:
    """Return [(status, pct_time, row_count), ...] sorted by row_count desc.

    回 [(status, pct_time, row_count), ...]，依 row_count 降序。
    """
    cur.execute(
        "SELECT status, COUNT(*) FROM learning.cost_edge_advisor_log "
        "WHERE ts_ms > (extract(epoch from now()) * 1000)::BIGINT - 604800000 "
        "GROUP BY status ORDER BY COUNT(*) DESC"
    )
    rows = cur.fetchall()
    total = sum(int(c or 0) for _s, c in rows) or 1
    return [(s, 100.0 * int(c or 0) / total, int(c or 0)) for s, c in rows]


# ---------------------------------------------------------------------------
# §3 Ratio histogram (per engine_mode, ASCII chart).
# §3 Ratio histogram (per engine_mode，ASCII 圖)。
# ---------------------------------------------------------------------------


_RATIO_BIN_EDGES = [-2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0]


def section_3_ratio_histogram(cur) -> dict[str, list[tuple[str, int]]]:
    """Return {engine_mode: [(bin_label, count), ...]} ratio histograms.

    回 {engine_mode: [(bin_label, count), ...]} 的 ratio histogram。
    """
    cur.execute(
        "SELECT DISTINCT engine_mode FROM learning.cost_edge_advisor_log "
        "WHERE ts_ms > (extract(epoch from now()) * 1000)::BIGINT - 604800000"
    )
    engines = [r[0] for r in cur.fetchall()]
    out: dict[str, list[tuple[str, int]]] = {}
    for em in engines:
        bins: list[tuple[str, int]] = []
        for i in range(len(_RATIO_BIN_EDGES) - 1):
            lo, hi = _RATIO_BIN_EDGES[i], _RATIO_BIN_EDGES[i + 1]
            cur.execute(
                "SELECT COUNT(*) FROM learning.cost_edge_advisor_log "
                "WHERE engine_mode = %s "
                "  AND ts_ms > (extract(epoch from now()) * 1000)::BIGINT - 604800000 "
                "  AND ratio IS NOT NULL "
                "  AND ratio >= %s AND ratio < %s",
                (em, lo, hi),
            )
            bins.append((f"[{lo:+.1f}, {hi:+.1f})", int(cur.fetchone()[0] or 0)))
        out[em] = bins
    return out


def render_ascii_histogram(bins: list[tuple[str, int]], width: int = 40) -> str:
    """Render an ASCII bar chart from histogram bin counts.

    從 histogram bin count 渲染 ASCII bar chart。
    """
    max_count = max((c for _b, c in bins), default=0) or 1
    out_lines = []
    for label, count in bins:
        bar_len = int(round(width * count / max_count))
        bar = "#" * bar_len
        out_lines.append(f"  {label:<16s} {count:>6d} | {bar}")
    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
# §5.3 Heatmap proxies — per-status × per-engine_mode + per-hour-of-day
# §5.3 Heatmap 替代 — per-status × per-engine_mode + per-hour-of-day
# ---------------------------------------------------------------------------


def section_5_status_engine_heatmap(cur) -> list[tuple[str, str, int]]:
    """Return [(status, engine_mode, count), ...] for the 6×3 grid.

    回 [(status, engine_mode, count), ...] 給 6×3 heatmap grid。
    """
    cur.execute(
        "SELECT status, engine_mode, COUNT(*) FROM learning.cost_edge_advisor_log "
        "WHERE ts_ms > (extract(epoch from now()) * 1000)::BIGINT - 604800000 "
        "GROUP BY status, engine_mode ORDER BY status, engine_mode"
    )
    return [(s, em, int(c or 0)) for s, em, c in cur.fetchall()]


def section_5_hour_of_day_triggers(cur) -> list[tuple[int, int]]:
    """Return [(hour_of_day, trigger_count), ...] for 24-cell heatmap.

    回 [(hour_of_day, trigger_count), ...] 給 24-cell heatmap。
    """
    cur.execute(
        "SELECT (EXTRACT(HOUR FROM TO_TIMESTAMP(ts_ms / 1000.0)))::INT AS hod, "
        "       COUNT(*) "
        "FROM learning.cost_edge_advisor_log "
        "WHERE ts_ms > (extract(epoch from now()) * 1000)::BIGINT - 604800000 "
        "  AND transition_from IS NOT NULL AND status = 'Trigger' "
        "GROUP BY hod ORDER BY hod"
    )
    rows = {int(h): int(c or 0) for h, c in cur.fetchall()}
    return [(h, rows.get(h, 0)) for h in range(24)]


# ---------------------------------------------------------------------------
# §6 Phase C readiness checklist + threshold calibration recommendation.
# §6 Phase C 啟動 checklist + threshold 重校建議。
# ---------------------------------------------------------------------------


def section_6_recommendation(cur, counters: dict) -> dict:
    """Return Phase C readiness assessment + threshold recommendation.

    回 Phase C readiness 評估 + threshold 建議。
    """
    out = {}
    # Observation window in days (uses earliest ts_ms in table).
    # 觀察窗（天）— 用表中最早的 ts_ms。
    cur.execute("SELECT MIN(ts_ms) FROM learning.cost_edge_advisor_log")
    earliest_ms = int(cur.fetchone()[0] or 0)
    if earliest_ms == 0:
        out["observation_days"] = 0.0
    else:
        from time import time as _time

        out["observation_days"] = (int(_time() * 1000) - earliest_ms) / 86_400_000.0

    out["window_matured"] = out["observation_days"] >= 7.0
    out["triggers_in_healthy_range"] = 0 <= counters["triggers_24h"] <= 10
    out["no_recent_fail_verdict"] = counters["triggers_per_hour_peak"] <= 20

    # Threshold calibration — compute the 5th percentile of observed ratio.
    # If the observed 5th percentile is well below the current threshold,
    # recommend keeping; if above, recommend recalibration.
    # Threshold 重校 — 算觀察 ratio 的 5th percentile；遠低於 threshold
    # 表保留，高於則建議重校。
    cur.execute(
        "SELECT PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY ratio) "
        "FROM learning.cost_edge_advisor_log WHERE ratio IS NOT NULL"
    )
    pct5 = cur.fetchone()[0]
    out["ratio_5th_percentile"] = float(pct5) if pct5 is not None else None
    return out


# ---------------------------------------------------------------------------
# Markdown rendering — RFC §5.2 deliverable layout.
# Markdown 渲染 — RFC §5.2 deliverable 版式。
# ---------------------------------------------------------------------------


def render_markdown(
    counters: dict,
    status_dist: list,
    histograms: dict,
    status_eng_heatmap: list,
    hour_of_day: list,
    recommendation: dict,
) -> str:
    """Render the full markdown report per RFC §5.2.

    依 RFC §5.2 渲染完整 markdown 報告。
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# G3-09 Phase B cost_edge_advisor — Observation Report",
        "",
        f"- **Generated**: {today}",
        f"- **Source**: ``learning.cost_edge_advisor_log`` (V026 hypertable)",
        f"- **RFC**: ``docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g3_09_phase_b_shadow_dryrun_design.md``",
        "",
        "## §1 Counters (24h rolling at report time)",
        "",
        "| Metric | Value | Verdict (per RFC §2.2) |",
        "|---|---|---|",
        f"| evaluations_24h | {counters['evaluations_24h']} | "
        f"{verdict_for_counter('evaluations_24h', counters['evaluations_24h'])} |",
        f"| triggers_24h | {counters['triggers_24h']} | "
        f"{verdict_for_counter('triggers_24h', counters['triggers_24h'])} |",
        f"| triggers_per_hour peak | {counters['triggers_per_hour_peak']} | "
        f"{verdict_for_counter('triggers_per_hour_peak', counters['triggers_per_hour_peak'])} |",
        f"| triggers_per_week count | {counters['triggers_per_week']} | "
        f"{verdict_for_counter('triggers_per_week', counters['triggers_per_week'])} |",
        "",
        "## §2 Status distribution (% time in each status, last 7d)",
        "",
        "| Status | % time | row count |",
        "|---|---|---|",
    ]
    for s, pct, n in status_dist:
        lines.append(f"| {s} | {pct:.1f}% | {n} |")
    if not status_dist:
        lines.append("| _(no data)_ | - | - |")

    lines.extend(["", "## §3 Ratio histogram (per engine_mode, last 7d)", ""])
    if not histograms:
        lines.append("_(no ratio samples — daemon may be in WarmUp / Disabled)_")
    for em, bins in histograms.items():
        lines.append(f"### engine_mode = `{em}`")
        lines.append("```")
        lines.append(render_ascii_histogram(bins))
        lines.append("```")
        lines.append("")

    lines.extend(
        [
            "## §4 Per-strategy / per-symbol breakdown",
            "",
            "_DEFERRED to Phase D._ Phase A H5 ``cost_edge_ratio`` is "
            "portfolio-level (not per-strategy); per-strategy heatmap "
            "requires H5 cost_tracker bucket split. See PA RFC §5.3 + "
            "backlog ticket ``G3-09-PHASE-D-PER-STRATEGY-RATIO P3``.",
            "",
            "## §5 Heatmap proxies",
            "",
            "### §5.1 Per-status × per-engine_mode (last 7d)",
            "",
            "| Status | engine_mode | row count |",
            "|---|---|---|",
        ]
    )
    for s, em, n in status_eng_heatmap:
        lines.append(f"| {s} | {em} | {n} |")
    if not status_eng_heatmap:
        lines.append("| _(no data)_ | - | - |")

    lines.extend(["", "### §5.2 Per-hour-of-day trigger count (last 7d)", "```"])
    max_hod = max((n for _h, n in hour_of_day), default=0) or 1
    for h, n in hour_of_day:
        bar = "#" * int(round(40 * n / max_hod))
        lines.append(f"  hour {h:02d}  {n:>4d} | {bar}")
    lines.append("```")
    lines.append("")

    lines.extend(
        [
            "## §6 Phase C readiness assessment",
            "",
            f"- Observation window: {recommendation['observation_days']:.1f} days "
            f"({'✅ matured (≥7d)' if recommendation['window_matured'] else '⏳ warming up'})",
            f"- triggers_24h in healthy range (0-10): "
            f"{'✅' if recommendation['triggers_in_healthy_range'] else '❌'}",
            f"- No FAIL on triggers_per_hour peak (≤20): "
            f"{'✅' if recommendation['no_recent_fail_verdict'] else '❌'}",
        ]
    )
    if recommendation.get("ratio_5th_percentile") is not None:
        lines.append(
            f"- ratio 5th percentile (calibration anchor): "
            f"`{recommendation['ratio_5th_percentile']:.4f}` "
            f"(if well below current threshold → keep; "
            f"if above → recalibrate to this value)"
        )
    else:
        lines.append("- ratio 5th percentile: _(insufficient data)_")
    lines.extend(
        [
            "",
            "**GO / NO-GO Phase C**: pending PA + PM joint sign-off based on "
            "the observation period extending to ≥7d AND all checklist items "
            "above marked ✅.",
            "",
        ]
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n", 1)[0])
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output markdown path (default: docs/audits/<today>--cost_edge_advisor_phase_b_observation.md)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print to stdout only; do not write a file.",
    )
    args = parser.parse_args()

    try:
        conn = _get_conn()
    except Exception as e:  # noqa: BLE001
        print(f"[FATAL] DB connect failed: {e}", file=sys.stderr)
        return 2

    try:
        with conn.cursor() as cur:
            counters = section_1_counters(cur)
            status_dist = section_2_status_distribution(cur)
            histograms = section_3_ratio_histogram(cur)
            status_eng_heatmap = section_5_status_engine_heatmap(cur)
            hour_of_day = section_5_hour_of_day_triggers(cur)
            recommendation = section_6_recommendation(cur, counters)
    finally:
        conn.close()

    md = render_markdown(
        counters,
        status_dist,
        histograms,
        status_eng_heatmap,
        hour_of_day,
        recommendation,
    )

    if args.dry_run:
        print(md)
        return 0

    base = os.environ.get("OPENCLAW_BASE_DIR") or os.environ.get("OPENCLAW_SRV_ROOT")
    if not base:
        base = str(Path.home() / "BybitOpenClaw" / "srv")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = (
        Path(args.out)
        if args.out
        else Path(base) / "docs" / "audits" / f"{today}--cost_edge_advisor_phase_b_observation.md"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
