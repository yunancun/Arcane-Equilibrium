#!/usr/bin/env bash
# wave9_replay_no_live_mutation_watch.sh — REF-20 Wave 9 R20-W9-T1
# Hourly cron: enforce V3 §12 acceptance #14 + §11 P6 KPI 14d window.
# 每小時 cron：強制 V3 §12 acceptance #14 + §11 P6 KPI 14 天窗口。
#
# MODULE_NOTE (EN):
#   Wave 9 R20-W9-T1 — 14d gradient observation infrastructure for the
#   `replay_no_live_mutation` continuous acceptance gate. Runs hourly via
#   crontab `0 * * * *` and:
#
#     1. Calls the Python validator (wave9_continuous_validator.py) to scan
#        trading.live_orders / trading.fills / trading.positions for rows
#        where `source LIKE 'replay_%'` in the rolling 14d window.
#     2. Expected truth: 0 row in 14d window. REF-20 mainline guarantee.
#     3. If violation detected:
#          - Emit one governance_audit_log row (alert_type='replay_no_live_mutation_violation').
#          - Print diagnostic to stderr (cron mailer surfaces).
#          - Exit 1 (cron flagged as failure for operator attention).
#     4. If 0 violation:
#          - Silent success (no log noise).
#          - Exit 0.
#
#   Idempotency: re-running yields same result for the same DB snapshot
#   (read-only validator + dedup'd audit row by alert_type + scan_id).
#
#   V044/V045 graceful absent fallback: validator returns ok=True if
#   trading schema absent or all 3 tables absent; cron exits 0 cleanly.
#
# MODULE_NOTE (中):
#   Wave 9 R20-W9-T1 — `replay_no_live_mutation` continuous acceptance gate
#   的 14 天 gradient observation 基礎設施。每小時跑（crontab `0 * * * *`）
#   並：
#
#     1. 呼叫 Python 驗證器 wave9_continuous_validator.py 掃 trading 三表。
#     2. 期望真相：14d 窗口 0 row。REF-20 主線保證。
#     3. 偵測到違反：
#          - 寫一 row governance_audit_log。
#          - stderr 列診斷（cron mailer 揭示）。
#          - exit 1（cron 標 failure，operator 注意）。
#     4. 0 違反：silent success（無 log noise）；exit 0。
#
#   Idempotent：同 DB snapshot 重跑得相同結果（read-only validator + audit
#   row dedup）。
#
#   V044/V045 graceful absent fallback：trading schema 缺或 3 表全缺時
#   validator 回 ok=True；cron 乾淨 exit 0。
#
# Spec source / 規格來源:
#   - V3 §12 acceptance #14 `replay_no_live_mutation`
#   - V3 §11 P6 KPI: live mutation count → continuous PASS=0
#   - workplan §4 Wave 9 row 1 (14d gradient observation)
#   - sibling cron pattern: replay_artifact_prune.py (DSN + psycopg2 lazy import)
#
# Suggested cron entry (operator manually adds via `crontab -e`):
# 建議 cron 條目（operator 用 `crontab -e` 加）：
#   0 * * * * "$OPENCLAW_BASE_DIR/helper_scripts/cron/wave9_replay_no_live_mutation_watch.sh"
#
# Exit codes:
#   0  No violation OR graceful absent fallback (trading schema absent etc.).
#   1  At least one violation detected; audit row emitted; stderr diagnostic.
#   2  Misconfiguration (DSN missing, Python import failure).

set -euo pipefail

# ─── Logging helpers / 日誌工具 ──────────────────────────────────────
log_info() {
    printf '[%s] [INFO] wave9_no_live_mutation_watch: %s\n' \
        "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" 1>&2
}

log_error() {
    printf '[%s] [ERROR] wave9_no_live_mutation_watch: %s\n' \
        "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" 1>&2
}


# ─── Path resolution / 路徑解析 ──────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRV_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Allow operator to override via OPENCLAW_BASE_DIR (CLAUDE.md §六 cross-platform).
# 允許 operator 用 OPENCLAW_BASE_DIR 覆蓋（CLAUDE.md §六 跨平台）。
OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$SRV_ROOT}"


# ─── Window config / 窗口配置 ────────────────────────────────────────
# Default 14d per V3 §11 P6 KPI. Operator may shorten for faster smoke
# (e.g. 1d) without modifying validator code.
# 預設 14d（V3 §11 P6 KPI）。Operator 可縮短至 1d 做 smoke（不改 validator）。
WINDOW_DAYS="${OPENCLAW_WAVE9_WINDOW_DAYS:-14}"


# ─── Python invocation / Python 呼叫 ─────────────────────────────────
# Inline Python script: import validator + connect PG + scan + audit emit
# + exit code. Keeps shell script lean; the heavy lifting in Python module
# (wave9_continuous_validator.py) is unit-tested separately.
# 內嵌 Python：import validator + 連 PG + 掃描 + audit emit + exit code。
# Shell 保持精簡；重邏輯在 Python module（已單元測試）。

PYTHON_BIN="${OPENCLAW_PYTHON:-python3}"

# Use absolute path so cron PATH does not matter for module import.
# 用絕對路徑，讓 cron PATH 不影響 module import。
VALIDATOR_MODULE_PATH="$OPENCLAW_BASE_DIR/program_code/exchange_connectors/bybit_connector/control_api_v1/replay"

# Verify module file exists; if not, exit 2 (misconfiguration).
# 驗證 module 檔案存在；不存在則 exit 2（設定錯誤）。
if [[ ! -f "$VALIDATOR_MODULE_PATH/wave9_continuous_validator.py" ]]; then
    log_error "validator module not found at $VALIDATOR_MODULE_PATH/wave9_continuous_validator.py"
    exit 2
fi

# Run inline Python — stdin heredoc keeps logic visible + grep-able.
# 跑內嵌 Python — stdin heredoc 保持邏輯可見 + grep-able。
exec "$PYTHON_BIN" - <<PYEOF
"""Wave 9 cron-driven 14d replay_no_live_mutation watcher.

Wave 9 cron 觸發的 14 天 replay_no_live_mutation watcher。

This inline Python script is invoked by wave9_replay_no_live_mutation_watch.sh
hourly. It connects to PG via the same DSN convention as sibling cron scripts
(OPENCLAW_DATABASE_URL or POSTGRES_*), scans the trading.* tables in the
configured rolling window, and on violation:

  1. emits one row to learning.governance_audit_log (event_type='audit_write_failed'
     fallback enum slot until V###+ extends to 'replay_no_live_mutation_violation';
     mirrors P2a-S5 audit pattern).
  2. prints a stderr diagnostic with details.
  3. exits 1.

On no violation it silently exits 0.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone

# Inject validator module path into sys.path.
# 將 validator module 路徑注入 sys.path。
sys.path.insert(0, "$VALIDATOR_MODULE_PATH")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("wave9_no_live_mutation_watch")


def _build_dsn() -> str | None:
    """Build psycopg2 DSN; mirror sibling cron pattern.
    對齊 sibling cron 構造 DSN。
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


def _v035_present(cur) -> bool:
    """True iff learning.governance_audit_log exists (audit emit guard).
    若 governance_audit_log 存在則 True（audit emit 守門）。
    """
    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = %s LIMIT 1;",
        ("learning", "governance_audit_log"),
    )
    return cur.fetchone() is not None


def _emit_violation_audit(cur, result) -> bool:
    """Emit governance_audit_log row for violation.
    為違反寫 governance_audit_log row。

    Reuses event_type='audit_write_failed' enum slot per sibling P2a-S5 pattern
    (V044 already extended event_type with 'replay_handoff_request'; future
    migration will add 'replay_no_live_mutation_violation' for typed slot).

    沿用 event_type='audit_write_failed' enum slot（per P2a-S5）；V044 已加
    'replay_handoff_request'，未來 migration 加 'replay_no_live_mutation_violation'
    typed slot。
    """
    payload = {
        "alert_type": "replay_no_live_mutation_violation",
        "window_days": result.window_days,
        "total_replay_source_rows": result.total_replay_source_rows,
        "first_violation_ts": (
            result.first_violation_ts.isoformat()
            if result.first_violation_ts is not None
            else None
        ),
        "scanned_at": (
            result.scanned_at.isoformat()
            if result.scanned_at is not None
            else None
        ),
        "details": result.details,
        "source": "wave9_replay_no_live_mutation_watch_cron",
    }
    try:
        cur.execute(
            """
            INSERT INTO learning.governance_audit_log
              (event_type, decided_by, payload)
            VALUES
              (%s, %s, %s::jsonb);
            """,
            (
                "audit_write_failed",
                "wave9_replay_no_live_mutation_watch_cron",
                json.dumps(payload, default=str),
            ),
        )
        return True
    except Exception as exc:  # noqa: BLE001 — log + return False; caller decides.
        log.error("audit insert failed: %s", exc)
        return False


def main() -> int:
    """Cron entrypoint.
    Cron 入口。
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
        return 2

    try:
        conn = psycopg2.connect(dsn)
    except Exception as exc:  # noqa: BLE001
        log.error("psycopg2 connect failed: %s", exc)
        return 2

    # Lazy-import validator AFTER psycopg2 import succeeds + sys.path injected.
    # 在 psycopg2 import OK + sys.path 注入後 lazy-import validator。
    try:
        from wave9_continuous_validator import validate_no_live_mutation
    except ImportError as exc:
        log.error("failed to import wave9_continuous_validator: %s", exc)
        try:
            conn.close()
        except Exception:
            pass
        return 2

    try:
        window_days = int(os.environ.get("OPENCLAW_WAVE9_WINDOW_DAYS", "14"))
    except ValueError:
        window_days = 14
        log.warning("OPENCLAW_WAVE9_WINDOW_DAYS not int; defaulting to 14")

    try:
        with conn:
            with conn.cursor() as cur:
                result = validate_no_live_mutation(
                    cursor=cur, window_days=window_days
                )

                if result.ok:
                    # Silent success: no log noise to keep cron mailer quiet.
                    # Silent 成功：保持 cron mailer 安靜。
                    return 0

                # Violation path / 違反路徑
                log.error(
                    "VIOLATION DETECTED: %d row(s) with source LIKE 'replay_%%' "
                    "in last %d days; first_ts=%s; details=%s",
                    result.total_replay_source_rows,
                    result.window_days,
                    result.first_violation_ts,
                    result.details,
                )

                if _v035_present(cur):
                    audit_ok = _emit_violation_audit(cur, result)
                    if audit_ok:
                        log.info(
                            "audit row emitted for violation (alert_type=replay_no_live_mutation_violation)"
                        )
                    else:
                        log.warning(
                            "audit emit failed; violation still flagged via exit 1"
                        )
                else:
                    log.warning(
                        "V035 governance_audit_log absent; cannot emit audit row "
                        "(violation still flagged via exit 1)"
                    )
                return 1
    except Exception as exc:  # noqa: BLE001
        log.error("watcher transaction failed: %s", exc)
        try:
            conn.rollback()
        except Exception as rb_exc:  # noqa: BLE001
            log.warning("rollback failed: %s", rb_exc)
        return 2
    finally:
        try:
            conn.close()
        except Exception as close_exc:  # noqa: BLE001
            log.warning("conn.close() failed: %s", close_exc)


if __name__ == "__main__":
    sys.exit(main())
PYEOF
