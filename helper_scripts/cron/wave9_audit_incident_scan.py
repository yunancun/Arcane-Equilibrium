#!/usr/bin/env python3
"""wave9_audit_incident_scan.py — REF-20 Wave 9 R20-W9-T3

Daily cron: scan learning.governance_audit_log for high-severity incidents
in 14-day window; write summary rows + alert on violation.

每日 cron：對 learning.governance_audit_log 14 天窗口掃 high-severity
incident；寫 summary row + 違反時 alert。

MODULE_NOTE (EN): REF-20 V3 §11 P6 KPI specifies "14d gradient 0 incident"
  for production stability. This cron implements the continuous validation
  by scanning learning.governance_audit_log (V035) for the following high-
  severity event signatures:

    1. event_type='replay_handoff_request' AND payload.result='rejected'
       → handoff was rejected (not a benign success).
       Severity: 'high' (rejected handoffs indicate operator config issue
       or security policy violation).

    2. event_type='audit_write_failed' AND
       payload.alert_type='replay_key_rotation_due'
       → key rotation is overdue per replay_key_rotation_check.sh
       sibling cron (Wave 3).
       Severity: 'high' (overdue rotation = manifest signature trust
       degraded).

    3. event_type='audit_write_failed' AND
       payload.alert_type IS NULL or other
       → generic audit write failures (DB constraint violation, schema
       drift, etc.).
       Severity: 'medium'.

  Expected truth: 14d window 0 high-severity events for production stability.
  When violation found:
    - Write summary row(s) to replay.audit_incident_summaries (V048).
    - stderr ALERT diagnostic.
    - exit 1 (cron mailer surfaces).
  When 0 violation: silent success + exit 0.

  V048 graceful absent: probes table via information_schema; if absent,
  log + exit 0 (cron entry safe pre-V048).

  V035 graceful absent: probes governance_audit_log table; if absent,
  log + exit 0 (cron entry safe even on fresh DB).

MODULE_NOTE (中): REF-20 V3 §11 P6 KPI 規定「14d gradient 0 incident」為
  生產穩定條件。本 cron 持續驗證，掃 V035 governance_audit_log 找下列
  high-severity event signature：

    1. event_type='replay_handoff_request' AND payload.result='rejected'
       → handoff 被拒（非良性 success）。Severity: 'high'。

    2. event_type='audit_write_failed' AND
       payload.alert_type='replay_key_rotation_due'
       → 違反 sibling Wave 3 cron 的 key rotation 排程。Severity: 'high'。

    3. event_type='audit_write_failed' （其他 alert_type）
       → 通用 audit write 失敗。Severity: 'medium'。

  期望真相：14d 窗口 0 high-severity event。違反時：
    - 寫 summary row 至 replay.audit_incident_summaries（V048）。
    - stderr ALERT 診斷。
    - exit 1（cron mailer 揭示）。
  無違反：silent success + exit 0。

  V048 graceful absent / V035 graceful absent：表缺即 log + exit 0；
  cron 條目可在 V048/V035 land 前先安裝。

Spec source / 規格來源:
  - REF-20 V3 §11 P6 KPI: 14d gradient 0 incident
  - workplan §4 Wave 9 row 3
  - V048 replay.audit_incident_summaries schema
  - sibling cron pattern: replay_key_rotation_check.sh + replay_artifact_prune.py

Suggested cron entry (operator manually adds via `crontab -e`).
建議 cron 條目（operator 用 `crontab -e` 加）：
  30 6 * * * "$OPENCLAW_BASE_DIR/helper_scripts/cron/wave9_audit_incident_scan.py"

Exit codes:
  0   No violation OR V048/V035 absent fallback (graceful).
  1   At least one high-severity incident detected; summary row(s) written;
      stderr alert diagnostic.
  2   Misconfiguration (DSN missing, Python import failure).
"""
from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any


# ─── Logging setup / 日誌設定 ─────────────────────────────────────────
_LOG_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=_LOG_FMT, stream=sys.stderr)
log = logging.getLogger("wave9_audit_incident_scan")


# ─── Incident definition / Incident 定義 ────────────────────────────


@dataclass(slots=True)
class IncidentSummary:
    """One (severity, event_type) incident summary row.

    一個 (severity, event_type) incident summary row。
    """

    severity: str
    event_type: str
    incident_count: int
    first_incident_ts: datetime | None
    last_incident_ts: datetime | None
    sample_payload: dict[str, Any] | None = field(default=None)


# Default window per V3 §11 P6 KPI.
# V3 §11 P6 KPI 預設窗口。
DEFAULT_WINDOW_DAYS = 14

# Sample payload truncation cap (avoid blob unbounded JSON in summary table).
# Sample payload 截斷上限（避免 unbounded JSON blob 進 summary 表）。
SAMPLE_PAYLOAD_MAX_KB = 8


# ─── DSN builder (mirror sibling cron) ────────────────────────────────


def _build_dsn() -> str | None:
    """Build psycopg2 DSN from env vars.
    從 env 構造 DSN。
    """
    explicit = os.environ.get("OPENCLAW_DATABASE_URL")
    if explicit:
        return explicit
    user = os.environ.get("POSTGRES_USER", "")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    db = os.environ.get("POSTGRES_DB", "")
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "5432")
    if not user or not password or not db:
        return None
    return f"postgresql://redacted@{host}:{port}/{db}"


# ─── Schema presence probe / Schema 偵測 ────────────────────────────


def _table_present(cur: Any, schema: str, table: str) -> bool:
    """Generic information_schema probe.
    通用 information_schema probe。
    """
    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = %s LIMIT 1;",
        (schema, table),
    )
    return cur.fetchone() is not None


# ─── Incident scanner / Incident 掃描器 ─────────────────────────────


def _scan_handoff_rejected(
    cur: Any, window_days: int
) -> IncidentSummary | None:
    """Scan for handoff_request rows with result='rejected'.

    掃 handoff_request row 中 result='rejected' 的。

    Returns IncidentSummary if count > 0, else None.
    Count > 0 時回 IncidentSummary，否則 None。
    """
    cur.execute(
        """
        SELECT
            COUNT(*) AS incident_count,
            MIN(ts) AS first_ts,
            MAX(ts) AS last_ts,
            (
                SELECT payload
                  FROM learning.governance_audit_log
                 WHERE ts >= NOW() - INTERVAL '%s days'
                   AND event_type = 'replay_handoff_request'
                   AND payload->>'result' = 'rejected'
                 ORDER BY ts ASC LIMIT 1
            ) AS sample_payload
          FROM learning.governance_audit_log
         WHERE ts >= NOW() - INTERVAL '%s days'
           AND event_type = 'replay_handoff_request'
           AND payload->>'result' = 'rejected';
        """,
        (window_days, window_days),
    )
    row = cur.fetchone()
    if not row:
        return None
    count = int(row[0]) if row[0] is not None else 0
    if count == 0:
        return None
    first_ts = row[1]
    last_ts = row[2]
    sample = row[3]
    return IncidentSummary(
        severity="high",
        event_type="replay_handoff_request",
        incident_count=count,
        first_incident_ts=first_ts,
        last_incident_ts=last_ts,
        sample_payload=sample if isinstance(sample, dict) else None,
    )


def _scan_key_rotation_due(
    cur: Any, window_days: int
) -> IncidentSummary | None:
    """Scan for replay_key_rotation_due alerts.

    掃 replay_key_rotation_due alert。
    """
    cur.execute(
        """
        SELECT
            COUNT(*) AS incident_count,
            MIN(ts) AS first_ts,
            MAX(ts) AS last_ts,
            (
                SELECT payload
                  FROM learning.governance_audit_log
                 WHERE ts >= NOW() - INTERVAL '%s days'
                   AND event_type = 'audit_write_failed'
                   AND payload->>'alert_type' = 'replay_key_rotation_due'
                 ORDER BY ts ASC LIMIT 1
            ) AS sample_payload
          FROM learning.governance_audit_log
         WHERE ts >= NOW() - INTERVAL '%s days'
           AND event_type = 'audit_write_failed'
           AND payload->>'alert_type' = 'replay_key_rotation_due';
        """,
        (window_days, window_days),
    )
    row = cur.fetchone()
    if not row:
        return None
    count = int(row[0]) if row[0] is not None else 0
    if count == 0:
        return None
    return IncidentSummary(
        severity="high",
        event_type="replay_key_rotation_due",
        incident_count=count,
        first_incident_ts=row[1],
        last_incident_ts=row[2],
        sample_payload=row[3] if isinstance(row[3], dict) else None,
    )


def _scan_audit_write_failed_other(
    cur: Any, window_days: int
) -> IncidentSummary | None:
    """Scan for audit_write_failed rows EXCLUDING the typed-alert sub-types
    that other scanners cover (e.g. replay_key_rotation_due, replay_artifact_prune_*).

    掃 audit_write_failed row（排除其他 scanner 已覆蓋的 typed alert 子類）。
    """
    cur.execute(
        """
        SELECT
            COUNT(*) AS incident_count,
            MIN(ts) AS first_ts,
            MAX(ts) AS last_ts,
            (
                SELECT payload
                  FROM learning.governance_audit_log
                 WHERE ts >= NOW() - INTERVAL '%s days'
                   AND event_type = 'audit_write_failed'
                   AND (
                       payload IS NULL
                       OR (
                           COALESCE(payload->>'alert_type', '') NOT IN (
                               'replay_key_rotation_due',
                               'replay_artifact_prune_ttl',
                               'replay_artifact_prune_storage_cap',
                               'replay_key_archive_expired',
                               'replay_no_live_mutation_violation'
                           )
                       )
                   )
                 ORDER BY ts ASC LIMIT 1
            ) AS sample_payload
          FROM learning.governance_audit_log
         WHERE ts >= NOW() - INTERVAL '%s days'
           AND event_type = 'audit_write_failed'
           AND (
               payload IS NULL
               OR (
                   COALESCE(payload->>'alert_type', '') NOT IN (
                       'replay_key_rotation_due',
                       'replay_artifact_prune_ttl',
                       'replay_artifact_prune_storage_cap',
                       'replay_key_archive_expired',
                       'replay_no_live_mutation_violation'
                   )
               )
           );
        """,
        (window_days, window_days),
    )
    row = cur.fetchone()
    if not row:
        return None
    count = int(row[0]) if row[0] is not None else 0
    if count == 0:
        return None
    return IncidentSummary(
        severity="medium",
        event_type="audit_write_failed",
        incident_count=count,
        first_incident_ts=row[1],
        last_incident_ts=row[2],
        sample_payload=row[3] if isinstance(row[3], dict) else None,
    )


def _truncate_payload(
    payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Truncate sample_payload to under SAMPLE_PAYLOAD_MAX_KB.

    截斷 sample_payload 至 SAMPLE_PAYLOAD_MAX_KB 下。

    If serialised payload is too large, replace with truncation marker.
    若序列化後過大，以截斷標記替代。
    """
    if payload is None:
        return None
    try:
        serialised = json.dumps(payload, default=str)
    except (TypeError, ValueError):
        return {"_truncated": True, "_reason": "non_serialisable"}
    if len(serialised.encode("utf-8")) > SAMPLE_PAYLOAD_MAX_KB * 1024:
        return {
            "_truncated": True,
            "_reason": "size_exceeded",
            "_size_kb": len(serialised.encode("utf-8")) // 1024,
        }
    return payload


# ─── Summary writer / Summary 寫入 ──────────────────────────────────


def _write_summary(
    cur: Any, scan_date: date, window_days: int, summary: IncidentSummary
) -> None:
    """UPSERT one row to replay.audit_incident_summaries.
    UPSERT 一 row 至 replay.audit_incident_summaries。
    """
    sample_truncated = _truncate_payload(summary.sample_payload)
    cur.execute(
        """
        INSERT INTO replay.audit_incident_summaries
          (summary_id, scan_date, window_days, incident_count,
           severity, event_type, first_incident_ts, last_incident_ts,
           sample_payload)
        VALUES
          (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (scan_date, severity, event_type)
        DO UPDATE SET
          incident_count = EXCLUDED.incident_count,
          first_incident_ts = EXCLUDED.first_incident_ts,
          last_incident_ts = EXCLUDED.last_incident_ts,
          sample_payload = EXCLUDED.sample_payload;
        """,
        (
            str(uuid.uuid4()),
            scan_date,
            window_days,
            summary.incident_count,
            summary.severity,
            summary.event_type,
            summary.first_incident_ts,
            summary.last_incident_ts,
            json.dumps(sample_truncated, default=str)
            if sample_truncated is not None
            else None,
        ),
    )


# ─── Main entrypoint / 主入口 ─────────────────────────────────────────


def main() -> int:
    """Cron entrypoint. Returns process exit code.
    Cron 入口。

    Workflow / 流程:
      1. Build DSN; exit 2 if env missing.
      2. Connect PG; exit 1 on connection failure.
      3. Probe V035 + V048; graceful exit 0 if either absent.
      4. Run 3 scanners; collect non-None IncidentSummary.
      5. If 0 incidents: silent exit 0.
      6. If >=1 incidents: UPSERT each to V048 + stderr alert + exit 1.
      7. Commit; exit 0 (no incident) or exit 1 (incidents detected).
    """
    dsn = _build_dsn()
    if dsn is None:
        log.error(
            "DSN unavailable — set OPENCLAW_DATABASE_URL or POSTGRES_{USER,PASSWORD,DB}"
        )
        return 2

    try:
        import psycopg2  # type: ignore
    except ImportError:
        log.error("psycopg2 not installed; install via control_api_v1 venv")
        return 1

    try:
        conn = psycopg2.connect(dsn)
    except Exception as exc:  # noqa: BLE001
        log.error("psycopg2 connect failed: %s", exc)
        return 1

    try:
        window_days = int(
            os.environ.get("OPENCLAW_WAVE9_INCIDENT_WINDOW_DAYS", str(DEFAULT_WINDOW_DAYS))
        )
    except ValueError:
        window_days = DEFAULT_WINDOW_DAYS
        log.warning(
            "OPENCLAW_WAVE9_INCIDENT_WINDOW_DAYS not int; default %d",
            DEFAULT_WINDOW_DAYS,
        )

    try:
        with conn:
            with conn.cursor() as cur:
                # Probe V035 governance_audit_log presence.
                # 偵測 V035 governance_audit_log 存在。
                if not _table_present(cur, "learning", "governance_audit_log"):
                    log.info(
                        "V035 (learning.governance_audit_log) absent; "
                        "graceful exit 0 (cron entry safe pre-V035)"
                    )
                    return 0

                # Probe V048 audit_incident_summaries presence.
                # 偵測 V048 audit_incident_summaries 存在。
                v048_ok = _table_present(
                    cur, "replay", "audit_incident_summaries"
                )
                if not v048_ok:
                    log.info(
                        "V048 (replay.audit_incident_summaries) absent; "
                        "scan still runs but cannot persist summary "
                        "(cron entry safe pre-V048)"
                    )

                # Run 3 scanners.
                # 跑 3 個 scanner。
                scanners = (
                    _scan_handoff_rejected,
                    _scan_key_rotation_due,
                    _scan_audit_write_failed_other,
                )
                incidents: list[IncidentSummary] = []
                for scanner in scanners:
                    try:
                        result = scanner(cur, window_days)
                    except Exception as exc:  # noqa: BLE001 — log + continue.
                        log.error("scanner %s failed: %s", scanner.__name__, exc)
                        continue
                    if result is not None:
                        incidents.append(result)

                if not incidents:
                    # Silent success: 0 high-severity in window.
                    # Silent 成功：窗口內 0 high-severity。
                    return 0

                # Violation path: UPSERT each summary + stderr alert.
                # 違反路徑：UPSERT 每 summary + stderr alert。
                scan_date = datetime.now(timezone.utc).date()
                total_count = sum(i.incident_count for i in incidents)
                log.error(
                    "INCIDENT VIOLATION: %d total high-severity event(s) in last %d days "
                    "across %d category(ies); details below",
                    total_count,
                    window_days,
                    len(incidents),
                )
                for inc in incidents:
                    log.error(
                        "  - severity=%s event_type=%s count=%d first=%s last=%s",
                        inc.severity,
                        inc.event_type,
                        inc.incident_count,
                        inc.first_incident_ts,
                        inc.last_incident_ts,
                    )
                    if v048_ok:
                        try:
                            _write_summary(cur, scan_date, window_days, inc)
                        except Exception as exc:  # noqa: BLE001
                            log.error(
                                "summary UPSERT failed for %s: %s",
                                inc.event_type,
                                exc,
                            )
                return 1
    except Exception as exc:  # noqa: BLE001
        log.error("scan transaction failed: %s", exc)
        try:
            conn.rollback()
        except Exception as rb_exc:  # noqa: BLE001
            log.warning("rollback failed: %s", rb_exc, exc_info=True)
        return 1
    finally:
        try:
            conn.close()
        except Exception as close_exc:  # noqa: BLE001
            log.warning("conn.close() failed: %s", close_exc, exc_info=True)


if __name__ == "__main__":
    sys.exit(main())
