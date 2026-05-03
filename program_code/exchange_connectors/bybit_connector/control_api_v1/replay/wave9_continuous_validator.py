"""REF-20 Wave 9 — replay_no_live_mutation continuous validator (14d window).

REF-20 Wave 9 — replay_no_live_mutation 持續驗證器（14 天窗口）。

MODULE_NOTE (EN):
    Wave 9 R20-W9-T1 (14d gradient observation infrastructure). Validates V3
    §12 acceptance #14 (`replay_no_live_mutation`) on a rolling 14-day window
    by querying trading.live_orders / trading.fills / trading.positions for
    rows whose `source` column matches `'replay_%'` LIKE pattern. Expected
    truth: 0 row in 14d window — REF-20 mainline guarantee that replay
    subsystem never mutates trading.* tables.

    Scope / 邊界:
      - Pure SELECT queries on trading.* tables (information_schema probe + 3
        existence checks). NO DDL, NO trading.* mutation, NO governance_hub
        coupling, NO Decision Lease coupling.
      - Returns ContinuousValidatorResult dataclass with ok / total /
        first_violation_ts / details. Caller (Wave 9 cron) wraps + emits
        governance_audit_log row when ok=False.
      - Idempotent: re-running yields identical result for the same DB
        snapshot (read-only query).

    Graceful absent fallback:
      - trading schema absent → ok=True (no rows = no violation; system
        not yet writing to those tables); details note "schema_absent".
      - Individual table absent (e.g. trading.live_orders not yet land) →
        graceful skip per table; details note "<table>_absent".

    The cron caller (`wave9_replay_no_live_mutation_watch.sh`) passes the
    result into the audit emit + exit-code logic.

MODULE_NOTE (中):
    Wave 9 R20-W9-T1（14 天 gradient observation 基礎建設）。驗證 V3 §12
    acceptance #14（`replay_no_live_mutation`）在 14 天滾動窗口；查 trading
    schema 三張表是否有 source 開頭 'replay_' 的 row。Mainline 保證 0 row。

    範圍：
      - 純 SELECT；trading.* 三表（live_orders / fills / positions）+
        information_schema 偵測。無 DDL、無 trading.* 修改、無 governance_hub
        / Decision Lease 耦合。
      - 回 ContinuousValidatorResult dataclass：ok / total / first_violation_ts
        / details。Caller（Wave 9 cron）包裝 + 寫 governance_audit_log row
        於 ok=False。
      - Idempotent：同 DB snapshot 重跑回相同結果（read-only 查詢）。

    Graceful absent fallback：
      - trading schema 缺 → ok=True（無 row 即無違反；系統未寫入）；
        details 記 "schema_absent"。
      - 個別 table 缺（如 trading.live_orders 未 land）→ per-table 跳過；
        details 記 "<table>_absent"。

    Cron caller（`wave9_replay_no_live_mutation_watch.sh`）把結果傳入 audit
    emit + exit-code 邏輯。

Spec source / 規格來源:
    - V3 §12 acceptance #14 `replay_no_live_mutation`
    - V3 §11 P6 KPI: live mutation count → continuous PASS=0
    - workplan §4 Wave 9 row 1 (14d gradient observation)
    - sibling cron pattern: replay_artifact_prune.py (info_schema probe)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


logger = logging.getLogger("replay.wave9_continuous_validator")


# ─── Dataclass / 資料類 ─────────────────────────────────────────────


@dataclass(slots=True)
class ContinuousValidatorResult:
    """Result of a 14d window scan over trading.* tables.

    14 天窗口掃描 trading.* 表的結果。

    Attributes / 屬性:
        ok: True iff zero rows with source LIKE 'replay_%' in the window.
        total_replay_source_rows: Total count across the 3 tables (sum).
        first_violation_ts: ts of the earliest violation row (NULL on ok=True).
        details: Diagnostic dict — per-table count + schema-absent notes.
        window_days: Window size (default 14, configurable).
        scanned_at: ts when scan was performed (UTC).
    """

    ok: bool
    total_replay_source_rows: int
    first_violation_ts: Optional[datetime]
    details: dict[str, Any] = field(default_factory=dict)
    window_days: int = 14
    scanned_at: Optional[datetime] = None


# ─── Config / 配置 ──────────────────────────────────────────────────

# The 3 trading.* tables to scan. Each must have a `source` column when
# present; absent column also causes graceful skip per table.
# 三張要掃描的 trading.* 表；每張存在時必有 source 欄位；缺欄位也 graceful 跳。
TRADING_TABLES = ("live_orders", "fills", "positions")

# `source` column LIKE pattern — REF-20 source naming convention prefixes
# replay-derived rows with 'replay_' (e.g. 'replay_runner', 'replay_advisory').
# REF-20 source 命名約定：replay 衍生 row 以 'replay_' 開頭。
REPLAY_SOURCE_LIKE = "replay_%"


# ─── Schema probe / Schema 偵測 ─────────────────────────────────────


def _trading_schema_present(cursor: Any) -> bool:
    """True iff `trading` schema exists.
    若 `trading` schema 存在則 True。
    """
    cursor.execute(
        "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s LIMIT 1;",
        ("trading",),
    )
    return cursor.fetchone() is not None


def _trading_table_present(cursor: Any, table: str) -> bool:
    """True iff `trading.<table>` exists.
    若 `trading.<table>` 存在則 True。
    """
    cursor.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = %s LIMIT 1;",
        ("trading", table),
    )
    return cursor.fetchone() is not None


def _table_has_source_column(cursor: Any, table: str) -> bool:
    """True iff `trading.<table>` has a `source` column.
    若 `trading.<table>` 有 `source` 欄則 True。

    Defensive: rare schema edits could remove `source` column. We then
    treat the table as graceful-absent (no rows can match LIKE 'replay_%'
    if column doesn't exist).

    防禦：罕見 schema 修改可能移除 `source` 欄；視為 graceful-absent。
    """
    cursor.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s AND column_name = %s LIMIT 1;",
        ("trading", table, "source"),
    )
    return cursor.fetchone() is not None


# ─── Per-table scan / 每表掃描 ───────────────────────────────────────


def _scan_table_for_replay_source(
    cursor: Any, table: str, window_days: int
) -> tuple[int, Optional[datetime]]:
    """Count rows in `trading.<table>` with source LIKE 'replay_%' in window.

    在 14d 窗口內 count `trading.<table>` 中 source LIKE 'replay_%' 的 row。

    Each trading.* table is expected to have a timestamp column; we use
    `ts` as the canonical name (matches V035 governance_audit_log + V044
    handoff_requests + standard OpenClaw schema convention).

    每張 trading.* 表預期有 timestamp 欄；用 `ts` 為 canonical（對齊 V035 +
    V044 + OpenClaw schema 慣例）。

    Returns / 回傳:
        (count, first_violation_ts) — count of rows matched; ts of earliest
        matching row or None if count=0.
    """
    # Use parameterised SQL (SQL injection safe). Window via `NOW() - INTERVAL`
    # so cron timezone matches PG NOW() semantic.
    # 用參數化 SQL（SQL injection 安全）。窗口 NOW() - INTERVAL，cron 時區
    # 與 PG NOW() 一致。
    sql = f"""
        SELECT COUNT(*), MIN(ts)
          FROM trading.{table}
         WHERE source LIKE %s
           AND ts >= NOW() - INTERVAL '%s days';
    """  # noqa: S608 — table name is from controlled allowlist
    cursor.execute(sql, (REPLAY_SOURCE_LIKE, window_days))
    row = cursor.fetchone()
    if not row:
        return 0, None
    count = int(row[0]) if row[0] is not None else 0
    first_ts = row[1] if count > 0 else None
    return count, first_ts


# ─── Main API / 主 API ──────────────────────────────────────────────


def validate_no_live_mutation(
    cursor: Any, window_days: int = 14
) -> ContinuousValidatorResult:
    """Scan trading.* for replay-source rows in window; return result.

    在窗口內掃 trading.* 三表是否有 replay-source row；回 result。

    Args / 參數:
        cursor: psycopg2 cursor (caller-managed transaction; we only
                read so caller MAY use a read-only transaction).
        window_days: Rolling window size in days (default 14 per V3 §11
                     P6 KPI "14d gradient 0 incident").

    Returns / 回傳:
        ContinuousValidatorResult — ok=True iff total_replay_source_rows=0.

    Behaviour / 行為:
        - trading schema absent → ok=True with details={"trading_schema_absent": True}.
        - Per-table absent → graceful skip; details["<table>_absent"]=True.
        - Per-table source column absent → graceful skip;
          details["<table>_source_col_absent"]=True.
        - All present + 0 rows match → ok=True, total=0, first_violation_ts=None.
        - Any rows match → ok=False, total=sum, first_violation_ts=earliest ts.

    Raises / 例外:
        ValueError if window_days <= 0 or > 365 (sanity bound to avoid
        accidental "all-history" scan).
    """
    if window_days <= 0 or window_days > 365:
        raise ValueError(
            f"window_days must be in (0, 365]; got {window_days}"
        )

    # Capture scan timestamp for result trace (UTC).
    # 記錄掃描時間（UTC）供 result trace。
    from datetime import timezone

    scanned_at = datetime.now(timezone.utc)

    details: dict[str, Any] = {
        "scanned_tables": [],
        "skipped_tables": [],
    }

    # Step 1: trading schema probe / 步驟 1：trading schema 偵測.
    if not _trading_schema_present(cursor):
        details["trading_schema_absent"] = True
        logger.info(
            "wave9_continuous_validator: trading schema absent — "
            "graceful ok=True (no schema = no violation)"
        )
        return ContinuousValidatorResult(
            ok=True,
            total_replay_source_rows=0,
            first_violation_ts=None,
            details=details,
            window_days=window_days,
            scanned_at=scanned_at,
        )

    # Step 2: per-table scan / 步驟 2：每表掃描.
    total_count = 0
    first_ts: Optional[datetime] = None
    per_table_counts: dict[str, int] = {}

    for table in TRADING_TABLES:
        if not _trading_table_present(cursor, table):
            details["skipped_tables"].append(table)
            details[f"{table}_absent"] = True
            continue

        if not _table_has_source_column(cursor, table):
            details["skipped_tables"].append(table)
            details[f"{table}_source_col_absent"] = True
            logger.warning(
                "wave9_continuous_validator: trading.%s missing source column "
                "— graceful skip (cannot match LIKE 'replay_%%' on absent col)",
                table,
            )
            continue

        count, ts = _scan_table_for_replay_source(cursor, table, window_days)
        per_table_counts[table] = count
        details["scanned_tables"].append(table)
        total_count += count

        # Track earliest violation across all tables.
        # 追蹤跨表最早違反 ts。
        if count > 0 and ts is not None:
            if first_ts is None or ts < first_ts:
                first_ts = ts

    details["per_table_counts"] = per_table_counts

    ok = total_count == 0

    if not ok:
        logger.error(
            "wave9_continuous_validator VIOLATION: total=%d rows with "
            "source LIKE 'replay_%%' in last %d days; per-table=%s; "
            "first_violation_ts=%s",
            total_count,
            window_days,
            per_table_counts,
            first_ts,
        )
    else:
        logger.info(
            "wave9_continuous_validator OK: 0 rows with source LIKE "
            "'replay_%%' in last %d days across %d table(s)",
            window_days,
            len(details["scanned_tables"]),
        )

    return ContinuousValidatorResult(
        ok=ok,
        total_replay_source_rows=total_count,
        first_violation_ts=first_ts,
        details=details,
        window_days=window_days,
        scanned_at=scanned_at,
    )


__all__ = [
    "TRADING_TABLES",
    "REPLAY_SOURCE_LIKE",
    "ContinuousValidatorResult",
    "validate_no_live_mutation",
]
