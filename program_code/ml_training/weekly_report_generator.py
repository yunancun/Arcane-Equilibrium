"""Phase 4 Weekly Review Report Generator (4-20).

Phase 4 週度審查報告生成器（4-20）。

MODULE_NOTE (EN/中):
    Pulls 7d statistics from PG (directive_executions, foundation_model_features,
    news_signals, ai_usage_log, decision_context_snapshots) and produces a
    plain-English Markdown report with DoD A/C/E metrics + sign-off section.

    從 PG 拉 7d 統計並產出純英文 Markdown 報告，含 DoD A/C/E 指標 + 簽核區塊。

    Fail-soft: missing tables / no PG → returns INSUFFICIENT_DATA report
    (still produces Markdown so operator sees what is wrong).
    fail-soft：缺表 / 無 PG → 回 INSUFFICIENT_DATA，仍產 Markdown 讓 operator
    看到問題所在。
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DoD thresholds / DoD 閾值
# ---------------------------------------------------------------------------

#: DoD A — Sharpe delta vs Phase 3 baseline must improve by >= +0.15.
#: DoD A — 相比 Phase 3 baseline，Sharpe 必須改善 >= +0.15。
DOD_A_SHARPE_DELTA: float = 0.15

#: DoD C — Scorer Tier-1 ROC AUC must be >= 0.55.
#: DoD C — Scorer Tier-1 ROC AUC 必須 >= 0.55。
DOD_C_AUC_MIN: float = 0.55

#: DoD E — Teacher directive execution rate must be >= 80%.
#: DoD E — Teacher directive 執行率必須 >= 80%。
DOD_E_EXEC_RATE_MIN: float = 0.80


# ---------------------------------------------------------------------------
# Lazy psycopg2 import / 延遲 psycopg2 匯入
# ---------------------------------------------------------------------------


def _try_import_psycopg2():
    """Lazy psycopg2 import. None on failure. / 延遲 psycopg2 匯入；失敗回 None。"""
    try:
        import psycopg2  # type: ignore

        return psycopg2
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Dataclasses / 資料類別
# ---------------------------------------------------------------------------


@dataclass
class WeeklyMetrics:
    """7d aggregate metrics for Phase 4 DoD evaluation.
    Phase 4 DoD 評估的 7d 聚合指標。
    """

    week_iso: str
    week_start: datetime
    week_end: datetime

    # DoD A: Sharpe
    sharpe_paper_7d: Optional[float] = None
    sharpe_baseline: Optional[float] = None
    sharpe_delta: Optional[float] = None

    # DoD C: Scorer AUC
    scorer_auc_7d: Optional[float] = None

    # DoD E: Teacher directive execution
    teacher_total_7d: int = 0
    teacher_applied_7d: int = 0
    teacher_exec_rate: float = 0.0
    teacher_avg_outcome_24h: Optional[float] = None

    # LinUCB
    linucb_active_version: str = "v1_15"
    linucb_total_pulls: int = 0
    linucb_converged_arms: int = 0

    # News
    news_total_7d: int = 0
    news_halt_triggers_7d: int = 0
    news_max_severity_7d: Optional[float] = None

    # DL-3
    dl3_inference_count_7d: int = 0
    dl3_avg_latency_ms: Optional[float] = None
    dl3_ok_rate_7d: Optional[float] = None

    # AI Cost
    ai_cost_usd_7d: float = 0.0
    ai_cost_local_total_remaining: float = 0.0
    ai_degrade_level: str = "unknown"

    # Source health flag
    is_insufficient_data: bool = False
    insufficient_reason: str = ""


@dataclass
class WeeklyReport:
    week_iso: str
    metrics: WeeklyMetrics
    markdown: str
    machine_summary: dict = field(default_factory=dict)
    dod_status: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Week ISO helpers / 週 ISO 輔助
# ---------------------------------------------------------------------------


def current_week_iso(now: Optional[datetime] = None) -> str:
    """Return current ISO week label like '2026-W15'.
    返回目前 ISO 週標籤，例如 '2026-W15'。
    """
    if now is None:
        now = datetime.now(timezone.utc)
    iso = now.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def week_range_for_iso(week_iso: str) -> tuple[datetime, datetime]:
    """Return (start, end) UTC datetimes for an ISO week label.
    返回 ISO 週標籤對應的 (start, end) UTC datetime。
    """
    parts = week_iso.split("-W")
    if len(parts) != 2:
        raise ValueError(f"invalid week_iso: {week_iso}")
    year = int(parts[0])
    week = int(parts[1])
    monday = datetime.fromisocalendar(year, week, 1).replace(tzinfo=timezone.utc)
    end = monday + timedelta(days=7)
    return (monday, end)


# ---------------------------------------------------------------------------
# Data fetching / 資料拉取
# ---------------------------------------------------------------------------


def _empty_metrics(week_iso: str, reason: str) -> WeeklyMetrics:
    start, end = week_range_for_iso(week_iso)
    return WeeklyMetrics(
        week_iso=week_iso,
        week_start=start,
        week_end=end,
        is_insufficient_data=True,
        insufficient_reason=reason,
    )


def fetch_weekly_metrics(
    dsn: Optional[str], week_iso: Optional[str] = None
) -> WeeklyMetrics:
    """Pull all 7d aggregate metrics from PG. Fail-soft on any error.
    從 PG 拉所有 7d 聚合指標。任何錯誤 fail-soft。
    """
    if week_iso is None:
        week_iso = current_week_iso()

    if dsn is None:
        return _empty_metrics(week_iso, "no dsn provided")

    psycopg2 = _try_import_psycopg2()
    if psycopg2 is None:
        return _empty_metrics(week_iso, "psycopg2 unavailable")

    start, end = week_range_for_iso(week_iso)
    metrics = WeeklyMetrics(week_iso=week_iso, week_start=start, week_end=end)

    try:
        conn = psycopg2.connect(dsn)
    except Exception as e:
        logger.warning("weekly_report: connect failed: %s", e)
        return _empty_metrics(week_iso, f"connect failed: {e}")

    try:
        with conn.cursor() as cur:
            # ── Teacher directive 7d stats / Teacher directive 7d 統計 ──
            try:
                cur.execute(
                    """
                    SELECT COUNT(*)::int,
                           COUNT(*) FILTER (WHERE success IS TRUE)::int,
                           AVG(outcome_pnl_24h)
                    FROM learning.directive_executions
                    WHERE ts >= %s AND ts < %s
                    """,
                    (start, end),
                )
                row = cur.fetchone()
                if row:
                    metrics.teacher_total_7d = int(row[0] or 0)
                    metrics.teacher_applied_7d = int(row[1] or 0)
                    metrics.teacher_avg_outcome_24h = (
                        float(row[2]) if row[2] is not None else None
                    )
                    metrics.teacher_exec_rate = (
                        metrics.teacher_applied_7d / metrics.teacher_total_7d
                        if metrics.teacher_total_7d > 0
                        else 0.0
                    )
            except Exception as e:
                logger.warning("weekly_report: teacher fetch failed: %s", e)
                conn.rollback()

            # ── LinUCB 7d state / LinUCB 7d 狀態 ──
            try:
                cur.execute(
                    "SELECT to_version FROM learning.linucb_migrations "
                    "ORDER BY migration_id DESC LIMIT 1"
                )
                row = cur.fetchone()
                if row:
                    metrics.linucb_active_version = row[0]
                cur.execute(
                    "SELECT COALESCE(SUM(n_pulls), 0)::bigint, "
                    "COUNT(*) FILTER (WHERE n_pulls >= 100)::int "
                    "FROM learning.linucb_state WHERE arm_space_version = %s",
                    (metrics.linucb_active_version,),
                )
                row = cur.fetchone()
                if row:
                    metrics.linucb_total_pulls = int(row[0] or 0)
                    metrics.linucb_converged_arms = int(row[1] or 0)
            except Exception as e:
                logger.warning("weekly_report: linucb fetch failed: %s", e)
                conn.rollback()

            # ── News 7d stats / News 7d 統計 ──
            try:
                cur.execute(
                    """
                    SELECT COUNT(*)::int,
                           COUNT(*) FILTER (WHERE severity >= 0.8)::int,
                           MAX(severity)
                    FROM market.news_signals
                    WHERE ts >= %s AND ts < %s
                    """,
                    (start, end),
                )
                row = cur.fetchone()
                if row:
                    metrics.news_total_7d = int(row[0] or 0)
                    metrics.news_halt_triggers_7d = int(row[1] or 0)
                    metrics.news_max_severity_7d = (
                        float(row[2]) if row[2] is not None else None
                    )
            except Exception as e:
                logger.warning("weekly_report: news fetch failed: %s", e)
                conn.rollback()

            # ── DL-3 7d stats / DL-3 7d 統計 ──
            try:
                cur.execute(
                    """
                    SELECT COUNT(*)::int,
                           AVG(latency_ms),
                           AVG(CASE WHEN ok THEN 1.0 ELSE 0.0 END)
                    FROM learning.foundation_model_features
                    WHERE time >= %s AND time < %s
                    """,
                    (start, end),
                )
                row = cur.fetchone()
                if row:
                    metrics.dl3_inference_count_7d = int(row[0] or 0)
                    metrics.dl3_avg_latency_ms = (
                        float(row[1]) if row[1] is not None else None
                    )
                    metrics.dl3_ok_rate_7d = (
                        float(row[2]) if row[2] is not None else None
                    )
            except Exception as e:
                logger.warning("weekly_report: dl3 fetch failed: %s", e)
                conn.rollback()

            # ── AI cost 7d stats / AI cost 7d 統計 ──
            try:
                cur.execute(
                    "SELECT COALESCE(SUM(cost_usd), 0.0) "
                    "FROM learning.ai_usage_log "
                    "WHERE time >= %s AND time < %s",
                    (start, end),
                )
                row = cur.fetchone()
                if row:
                    metrics.ai_cost_usd_7d = float(row[0] or 0.0)
                # Local total remaining = config.local_total - mtd usage
                # 本月剩餘 = 配置.local_total - mtd 已用
                cur.execute(
                    "SELECT monthly_usd FROM learning.ai_budget_config "
                    "WHERE scope = 'local_total'"
                )
                row = cur.fetchone()
                local_total_limit = float(row[0]) if row else 100.0
                cur.execute(
                    "SELECT COALESCE(SUM(cost_usd), 0.0) "
                    "FROM learning.ai_usage_log "
                    "WHERE time >= date_trunc('month', NOW())"
                )
                row = cur.fetchone()
                mtd_used = float(row[0] or 0.0) if row else 0.0
                metrics.ai_cost_local_total_remaining = max(
                    0.0, local_total_limit - mtd_used
                )
                # Degrade level inference based on % used
                # 根據已用百分比推斷降級等級
                pct_used = (mtd_used / local_total_limit) if local_total_limit > 0 else 1.0
                if pct_used >= 1.0:
                    metrics.ai_degrade_level = "killswitch"
                elif pct_used >= 0.95:
                    metrics.ai_degrade_level = "hard_limit"
                elif pct_used >= 0.80:
                    metrics.ai_degrade_level = "soft_warn"
                else:
                    metrics.ai_degrade_level = "none"
            except Exception as e:
                logger.warning("weekly_report: ai_cost fetch failed: %s", e)
                conn.rollback()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return metrics


# ---------------------------------------------------------------------------
# DoD evaluation / DoD 評估
# ---------------------------------------------------------------------------


def evaluate_dod(metrics: WeeklyMetrics) -> dict[str, str]:
    """Map metrics → DoD A/C/E status.
    將指標對映為 DoD A/C/E 狀態。

    Returns dict with keys A_sharpe / C_auc / E_teacher, values
    PASS / FAIL / N/A (per criterion).
    返回 dict (key = A_sharpe/C_auc/E_teacher, value = PASS/FAIL/N/A)。
    """
    out: dict[str, str] = {}

    # A — Sharpe delta
    if metrics.sharpe_delta is None:
        out["A_sharpe"] = "N/A"
    elif metrics.sharpe_delta >= DOD_A_SHARPE_DELTA:
        out["A_sharpe"] = "PASS"
    else:
        out["A_sharpe"] = "FAIL"

    # C — Scorer AUC
    if metrics.scorer_auc_7d is None:
        out["C_auc"] = "N/A"
    elif metrics.scorer_auc_7d >= DOD_C_AUC_MIN:
        out["C_auc"] = "PASS"
    else:
        out["C_auc"] = "FAIL"

    # E — Teacher exec rate AND outcome non-negative
    if metrics.teacher_total_7d == 0:
        out["E_teacher"] = "N/A"
    else:
        rate_ok = metrics.teacher_exec_rate >= DOD_E_EXEC_RATE_MIN
        outcome = metrics.teacher_avg_outcome_24h or 0.0
        outcome_ok = outcome >= 0.0
        out["E_teacher"] = "PASS" if (rate_ok and outcome_ok) else "FAIL"

    return out


# ---------------------------------------------------------------------------
# Report generation / 報告生成
# ---------------------------------------------------------------------------


def _emoji_for(status: str) -> str:
    return {"PASS": "✅", "FAIL": "❌", "N/A": "⚪"}.get(status, "⚪")


def _fmt(val: Any, decimals: int = 4, none_str: str = "—") -> str:
    if val is None:
        return none_str
    if isinstance(val, float):
        return f"{val:.{decimals}f}"
    return str(val)


def generate_report(
    metrics: WeeklyMetrics,
    operator_notes: str = "",
    now: Optional[datetime] = None,
) -> WeeklyReport:
    """Build the full Markdown report and machine_summary.
    建構完整 Markdown 報告與機器摘要。
    """
    if now is None:
        now = datetime.now(timezone.utc)
    dod = evaluate_dod(metrics)

    sharpe_delta_str = (
        f"{metrics.sharpe_delta:+.4f}"
        if metrics.sharpe_delta is not None
        else "—"
    )
    auc_str = _fmt(metrics.scorer_auc_7d)
    exec_rate_str = (
        f"{metrics.teacher_exec_rate * 100:.1f}%" if metrics.teacher_total_7d > 0 else "N/A"
    )
    outcome_str = (
        f"+${metrics.teacher_avg_outcome_24h:.2f}"
        if metrics.teacher_avg_outcome_24h is not None and metrics.teacher_avg_outcome_24h >= 0
        else (
            f"-${abs(metrics.teacher_avg_outcome_24h):.2f}"
            if metrics.teacher_avg_outcome_24h is not None
            else "—"
        )
    )

    notes_block = operator_notes.strip() if operator_notes else "(none provided)"
    pass_count = sum(1 for v in dod.values() if v == "PASS")
    eligible_count = sum(1 for v in dod.values() if v in ("PASS", "FAIL"))
    overall = (
        "APPROVE" if pass_count == eligible_count and eligible_count > 0 else "REVIEW"
    )

    insufficient_banner = ""
    if metrics.is_insufficient_data:
        insufficient_banner = (
            f"\n⚠️ **INSUFFICIENT DATA**: {metrics.insufficient_reason}\n"
            "All metrics may be zero or N/A. Operator approval should NOT proceed.\n\n"
        )

    markdown = f"""# Phase 4 Weekly Review — {metrics.week_iso}

**Generated**: {now.strftime("%Y-%m-%dT%H:%M:%SZ")}
**Week range**: {metrics.week_start.strftime("%Y-%m-%d")} → {metrics.week_end.strftime("%Y-%m-%d")}
{insufficient_banner}
## DoD Status / DoD 狀態

| Criterion | Threshold | Actual | Status |
|---|---|---|---|
| **A** Sharpe Δ | ≥ +{DOD_A_SHARPE_DELTA:.2f} | {sharpe_delta_str} | {_emoji_for(dod["A_sharpe"])} {dod["A_sharpe"]} |
| **C** Scorer AUC | ≥ {DOD_C_AUC_MIN:.2f} | {auc_str} | {_emoji_for(dod["C_auc"])} {dod["C_auc"]} |
| **E** Teacher exec rate | ≥ {DOD_E_EXEC_RATE_MIN * 100:.0f}% & outcome ≥ 0 | {exec_rate_str} / {outcome_str} | {_emoji_for(dod["E_teacher"])} {dod["E_teacher"]} |

**Overall**: {pass_count}/{eligible_count} criteria PASS. Recommended decision: **{overall}**.

## Module Health / 模組健康

### 🧑‍🏫 Claude Teacher
- Directives this week: {metrics.teacher_total_7d} ({metrics.teacher_applied_7d} applied, {metrics.teacher_total_7d - metrics.teacher_applied_7d} vetoed)
- Execution rate: {exec_rate_str}
- Average 24h outcome: {outcome_str}

### 🎰 LinUCB Bandit
- Active version: {metrics.linucb_active_version}
- Total pulls: {metrics.linucb_total_pulls}
- Converged arms (≥100 pulls): {metrics.linucb_converged_arms}

### 📰 News
- Items processed: {metrics.news_total_7d}
- Halt triggers (severity ≥ 0.8): {metrics.news_halt_triggers_7d}
- Max severity observed: {_fmt(metrics.news_max_severity_7d, 2)}

### 🧠 DL-3 Foundation
- Inferences this week: {metrics.dl3_inference_count_7d}
- Average latency: {_fmt(metrics.dl3_avg_latency_ms, 0)} ms
- Success rate: {f"{metrics.dl3_ok_rate_7d * 100:.1f}%" if metrics.dl3_ok_rate_7d is not None else "—"}

### 💰 AI Cost
- Spent this week: ${metrics.ai_cost_usd_7d:.2f}
- Local total remaining (MTD): ${metrics.ai_cost_local_total_remaining:.2f}
- Degrade level: {metrics.ai_degrade_level}

## Operator Notes / 操作員備註

{notes_block}

## Sign-off / 簽核

- [ ] AI-E reviewed and approved (DoD A + C + E + module health)
- [ ] PA architectural review (no Phase 4 invariant violation)
- [ ] PM final acknowledgment

---

To approve: `POST /api/v1/phase4/weekly_review/approve`
To reject:  `POST /api/v1/phase4/weekly_review/reject`
"""

    machine_summary = {
        "week_iso": metrics.week_iso,
        "generated_at_iso": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dod_status": dod,
        "overall": overall,
        "metrics": {
            k: (v.isoformat() if isinstance(v, datetime) else v)
            for k, v in asdict(metrics).items()
        },
        "thresholds": {
            "dod_a_sharpe_delta": DOD_A_SHARPE_DELTA,
            "dod_c_auc_min": DOD_C_AUC_MIN,
            "dod_e_exec_rate_min": DOD_E_EXEC_RATE_MIN,
        },
    }

    return WeeklyReport(
        week_iso=metrics.week_iso,
        metrics=metrics,
        markdown=markdown,
        machine_summary=machine_summary,
        dod_status=dod,
    )


def write_report(report: WeeklyReport, output_path: str | Path) -> Path:
    """Write Markdown + sibling .json with machine_summary.
    寫 Markdown + sibling .json 含 machine_summary。
    """
    md_path = Path(output_path)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(report.markdown, encoding="utf-8")
    json_path = md_path.with_suffix(md_path.suffix + ".json")
    json_path.write_text(
        json.dumps(report.machine_summary, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return md_path


def persist_to_pg(
    dsn: Optional[str], report: WeeklyReport, md_path: Optional[Path] = None
) -> Optional[int]:
    """INSERT a row into learning.weekly_review_log. Returns review_id or None.
    INSERT 一行到 learning.weekly_review_log，返回 review_id 或 None。
    Fail-soft.
    """
    if dsn is None:
        return None
    psycopg2 = _try_import_psycopg2()
    if psycopg2 is None:
        return None
    try:
        from psycopg2.extras import Json  # type: ignore
    except ImportError:
        return None
    try:
        conn = psycopg2.connect(dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO learning.weekly_review_log
                        (week_iso, metrics_json, report_md_path)
                    VALUES (%s, %s, %s)
                    RETURNING review_id
                    """,
                    (
                        report.week_iso,
                        Json(report.machine_summary),
                        str(md_path) if md_path else None,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return int(row[0]) if row else None
        finally:
            conn.close()
    except Exception as e:
        logger.warning("weekly_report: persist failed: %s", e)
        return None


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Phase 4 weekly report generator")
    parser.add_argument("--week", type=str, default=None, help="ISO week (e.g. 2026-W15), default current")
    parser.add_argument("--output", type=str, default="reports/phase4_weekly.md")
    parser.add_argument("--notes", type=str, default="")
    parser.add_argument("--dsn", type=str, default=None)
    parser.add_argument("--persist", action="store_true", help="POST to learning.weekly_review_log")
    args = parser.parse_args(argv)

    metrics = fetch_weekly_metrics(args.dsn, week_iso=args.week)
    report = generate_report(metrics, operator_notes=args.notes)
    md_path = write_report(report, args.output)
    if args.persist:
        review_id = persist_to_pg(args.dsn, report, md_path)
        if review_id:
            print(f"persisted to learning.weekly_review_log review_id={review_id}")
    print(f"weekly report written: {md_path} (overall={report.machine_summary.get('overall')})")
    return 0
