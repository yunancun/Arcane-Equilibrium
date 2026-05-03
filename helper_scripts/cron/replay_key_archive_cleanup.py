#!/usr/bin/env python3
"""replay_key_archive_cleanup.py — REF-20 P2a-S1 (Wave 2 Batch 1)
Daily cron: mark `replay.replay_signing_keys` rows past 180d retention as expired.
每日 cron：將 `replay.replay_signing_keys` 中過了 180d retention 的 row 標記為 expired。

MODULE_NOTE (EN): REF-20 V3 §5 specifies "old key retention = verify archived
  manifests for at most 180 days". After that boundary, any manifest signed
  by the retired key permanently enters `key_expired` fail-mode (V3 §5 /
  runbook §6). Runbook §4.3 calls for a daily cron to flip
  `status='retired' AND retention_until<NOW()` rows to `status='expired'`.

  This script implements that flip + emits one governance_audit_log row per
  newly-expired key for audit trail (NOT one row per existing 'expired' key
  — that would create daily duplicate noise). Archive rows are NEVER
  deleted; expired rows are retained forever for audit (per runbook §6
  governance invariant: distinguishing the 4 fail-modes requires the
  archive history of all keys that ever existed).

  Graceful fallback: if V042 (`replay.replay_signing_keys`) is not yet
  applied to the DB (current state of codebase as of 2026-05-03; V042 is
  reserved per `sql/migrations/REF-20_RESERVATION.md` but not yet land),
  the script logs and exits 0 — never crashes — so the cron entry can be
  installed before V042 lands.

  Idempotency: rerunning the same day yields zero updates because expired
  rows are filtered out by `WHERE status='retired'`. The audit row dedup
  is enforced by only writing audit when UPDATE actually flips rows
  (RETURNING fingerprint).

MODULE_NOTE (中): REF-20 V3 §5 規定「舊 key retention = 驗證歷史 manifest
  最多 180 天」。過該界後，任何用 retired key 簽的 manifest 永久進入
  `key_expired` fail-mode（V3 §5 / runbook §6）。Runbook §4.3 要求每日
  cron 把 `status='retired' AND retention_until<NOW()` row 翻成
  `status='expired'`。

  本腳本實現該翻轉 + 為每個新翻為 expired 的 key 寫一 row
  governance_audit_log（非為既有 'expired' row 寫 — 那會每天 duplicate
  noise）。Archive row 永不刪；expired row 永久保留供 audit（per runbook
  §6 governance invariant：區分 4 fail-mode 需要所有曾存在 key 的
  archive 歷史）。

  Graceful fallback：若 V042（`replay.replay_signing_keys`）尚未 applied
  到 DB（2026-05-03 codebase 當前；V042 per
  `sql/migrations/REF-20_RESERVATION.md` 預留但未 land），腳本 log 後
  exit 0 — 永不 crash — cron 條目可在 V042 land 前先安裝。

  Idempotent：同日重跑得到 0 update（已 expired 的 row 被
  `WHERE status='retired'` 過濾）。Audit row dedup 由「只在 UPDATE 真
  翻轉 row 時才寫」（RETURNING fingerprint）強制。

Spec source / 規格來源:
  - REF-20 V3 §5 (manifest signature, 4 fail-mode audit)
  - workplan R20-P2a-S1 (Wave 2 Batch 1)
  - runbook §4.3 + §6 + §8
  - sql/migrations/REF-20_RESERVATION.md V042
  - V035 governance_audit_log schema (existing)

Suggested cron entry (operator manually adds via `crontab -e`).
建議 cron 條目（operator `crontab -e` 加）：
  30 9 * * * "$OPENCLAW_BASE_DIR/helper_scripts/cron/replay_key_archive_cleanup.py"

Exit codes:
  0   success (rows updated OR V042 absent fallback OR no rows due — all OK)
  1   PG connection / SQL error (cron mailer surfaces)
  2   environment misconfigured (no DSN buildable)
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


# ─── Logging setup / 日誌設定 ─────────────────────────────────────────
# Mirror passive_wait_healthcheck logger naming (per OpenClaw convention).
# 對齊 passive_wait_healthcheck logger 命名（OpenClaw convention）。
_LOG_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=_LOG_FMT, stream=sys.stderr)
log = logging.getLogger("replay_key_archive_cleanup")


# ─── DSN builder (mirror passive_wait_healthcheck/db.py) ──────────────
def _build_dsn() -> str | None:
    """Build psycopg2 DSN from env vars (priority: OPENCLAW_DATABASE_URL).
    從 env 構造 psycopg2 DSN（優先 OPENCLAW_DATABASE_URL）。

    Returns DSN string or None when neither path is fully populated. Mirrors
    `helper_scripts/db/passive_wait_healthcheck/db.py:_get_conn` pattern so
    cron wrappers (e.g. edge_label_backfill_cron.sh) can export
    OPENCLAW_DATABASE_URL once and every helper picks it up.

    回傳 DSN 字串；兩條路徑都無法湊出時回 None。對齊
    `helper_scripts/db/passive_wait_healthcheck/db.py:_get_conn`，cron
    wrapper export 一次 OPENCLAW_DATABASE_URL 後所有 helper 都能用。
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

    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


# ─── V042 presence probe / V042 表存在偵測 ────────────────────────────
def _v042_present(cur: Any) -> bool:
    """Return True iff `replay.replay_signing_keys` table exists.
    若 `replay.replay_signing_keys` 表存在則 True。

    V042 is reserved (per `sql/migrations/REF-20_RESERVATION.md`) but not
    yet applied. Until then, this cron exits 0 gracefully (no crash) so
    the cron entry can be installed pre-V042 without alarms.

    V042 已預留（per `sql/migrations/REF-20_RESERVATION.md`）但未 apply。
    在那之前本 cron graceful exit 0（不 crash）— cron 條目可在 V042
    land 前先安裝。
    """
    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = %s LIMIT 1;",
        ("replay", "replay_signing_keys"),
    )
    return cur.fetchone() is not None


# ─── V035 governance_audit_log presence probe ─────────────────────────
def _v035_present(cur: Any) -> bool:
    """Return True iff `learning.governance_audit_log` exists (V035 land).
    若 `learning.governance_audit_log` 存在則 True（V035 已 land）。

    Audit log writes are best-effort — when V035 not yet applied (unlikely
    but defensible), the expiry flip still succeeds and cleanup row count
    is logged via stderr instead.

    Audit log 寫入為 best-effort — V035 尚未 apply 時（不太可能但要設防），
    expiry 翻轉仍成功，cleanup row 計數改 stderr log。
    """
    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = %s LIMIT 1;",
        ("learning", "governance_audit_log"),
    )
    return cur.fetchone() is not None


# ─── Cleanup core / 主清理邏輯 ────────────────────────────────────────
def _flip_retired_to_expired(cur: Any) -> list[tuple[str, str, datetime]]:
    """UPDATE rows past retention_until from 'retired' to 'expired'.
    將過了 retention_until 的 'retired' row 翻成 'expired'。

    Returns the list of (env, fingerprint, retention_until) for newly-flipped
    rows so the caller can emit one audit row each. Idempotent: rerunning
    the same day picks up zero rows because the WHERE clause filters out
    already-expired rows.

    回傳新翻轉的 (env, fingerprint, retention_until) tuple list；caller
    為每一筆寫一 audit row。Idempotent：同日重跑得 0 row（WHERE 已過濾）。
    """
    # Use RETURNING so we get the exact rows that were updated (vs SELECT-then-
    # UPDATE which has TOCTOU race; matters even at low concurrency for audit
    # correctness).
    # 用 RETURNING 拿 UPDATE 真正翻的 row（避免 SELECT-then-UPDATE 的
    # TOCTOU race；低並發下亦影響 audit 正確性）。
    cur.execute(
        """
        UPDATE replay.replay_signing_keys
           SET status = 'expired'
         WHERE status = 'retired'
           AND retention_until < NOW()
        RETURNING env, fingerprint, retention_until;
        """
    )
    rows = cur.fetchall() or []
    return [
        (str(env), str(fp), retention_until)
        for env, fp, retention_until in rows
    ]


def _emit_audit_row(
    cur: Any, env: str, fingerprint: str, retention_until: datetime
) -> bool:
    """Write one governance_audit_log row for a newly-expired key.
    為每個新 expired 的 key 寫一 row governance_audit_log。

    Uses the existing `event_type='audit_write_failed'` enum slot (V035
    CHECK) with payload alert_type='replay_key_archive_expired' until a
    sibling task expands the enum to include 'replay_key_*'. This matches
    the same approach used by replay_key_rotation_check.sh.

    用既有 V035 CHECK 的 `event_type='audit_write_failed'` enum slot 加
    payload alert_type='replay_key_archive_expired'，直到 sibling task 擴
    enum；對齊 replay_key_rotation_check.sh 同款做法。

    Returns True on successful insert, False on logged error (caller
    decides whether to fail loud — current behaviour: log + continue).
    成功 insert 回 True；錯誤 log 後回 False（caller 決定是否 fail loud；
    目前行為：log + 繼續）。
    """
    payload: dict[str, Any] = {
        "alert_type": "replay_key_archive_expired",
        "env": env,
        "fingerprint": fingerprint,
        "retention_until": retention_until.astimezone(timezone.utc).isoformat(),
        "source": "replay_key_archive_cleanup_cron",
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
                "replay_key_archive_cleanup_cron",
                json.dumps(payload),
            ),
        )
        return True
    except Exception as exc:  # noqa: BLE001 — must continue cron loop
        log.error("audit insert failed for env=%s fp=%s: %s", env, fingerprint, exc)
        return False


# ─── Main entrypoint / 主入口 ─────────────────────────────────────────
def main() -> int:
    """Cron entrypoint. Returns process exit code.
    Cron 入口；回傳行程 exit code。

    Workflow / 流程：
      1. Build DSN; exit 2 if env missing (cron mailer surfaces).
      2. Connect to PG; exit 1 on connection failure.
      3. Probe V042 presence; exit 0 gracefully if absent.
      4. Flip retired → expired with RETURNING; collect row tuples.
      5. For each flipped row, emit one governance_audit_log row (V035
         must be present; if not, log + continue).
      6. Commit; exit 0 on success.
    """
    dsn = _build_dsn()
    if dsn is None:
        log.error(
            "cannot build DSN — set OPENCLAW_DATABASE_URL or "
            "POSTGRES_{USER,PASSWORD,DB} (host/port default)"
        )
        return 2

    # Lazy import psycopg2 so importing this module for tests does not
    # require the package (mirrors passive_wait_healthcheck/db.py pattern).
    # 延遲 import psycopg2，讓單元測試 import 本模組時不需要該 package
    # （對齊 passive_wait_healthcheck/db.py 模式）。
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
        with conn:
            with conn.cursor() as cur:
                if not _v042_present(cur):
                    log.info(
                        "V042 (replay.replay_signing_keys) not yet applied — "
                        "graceful exit 0; cron will become useful once V042 lands"
                    )
                    return 0

                flipped = _flip_retired_to_expired(cur)
                log.info("flipped %d retired→expired row(s)", len(flipped))

                if not flipped:
                    return 0

                v035_ok = _v035_present(cur)
                if not v035_ok:
                    log.warning(
                        "V035 (learning.governance_audit_log) absent; "
                        "skipping audit row writes (UPDATE already committed below)"
                    )
                    return 0

                audit_written = 0
                for env, fingerprint, retention_until in flipped:
                    if _emit_audit_row(cur, env, fingerprint, retention_until):
                        audit_written += 1
                log.info(
                    "audit rows written: %d / %d", audit_written, len(flipped)
                )
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("cleanup transaction failed: %s", exc)
        try:
            conn.rollback()
        except Exception:
            pass
        return 1
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
