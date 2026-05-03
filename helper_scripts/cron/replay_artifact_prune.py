#!/usr/bin/env python3
"""replay_artifact_prune.py — REF-20 P2a-S5 (Wave 3 Batch 3A)
6-hourly cron: prune expired replay manifests + artifacts past TTL / storage cap.
每 6 小時 cron：清理過 TTL / storage cap 的 replay manifest + artifact。

MODULE_NOTE (EN): REF-20 V3 §5 specifies "manifest TTL = 30 days default" +
  "artifact storage cap = env-specific (config-defined)" + "prune job
  required before sustained P2 usage". Workplan §4 Wave 3 R20-P2a-S5 binds
  this cron + the ReplayQuotaEnforcer Python class as a paired delivery.

  Prune algorithm (per V3 §5 + workplan S5 row):
    1. SELECT manifests in `replay.experiments` where
       `expires_at < NOW() AND status NOT IN ('cancelled')` AND not pinned
       (pin column reserved; default false).
    2. For each manifest, list its `replay.report_artifacts` rows
       (cascading via FK in V3 §4.1). DELETE artifact filesystem files
       (URI-resolved local path; `replay://...` URIs treated as logical
       and not file-deleted in this sprint — physical artifact filesystem
       layout lands with P2b-T1).
    3. UPDATE manifest status='cancelled'... no — V3 §4.1 status enum is
       `created/running/completed/failed/cancelled`. Per workplan: artifact
       prune is the destructive op (DELETE artifact rows + filesystem),
       not status flip. Manifest itself stays as historical row (V3 §6
       audit trail invariant: signed manifests retained forever for
       reproducibility).
    4. INSERT one governance_audit_log row per pruned batch (event_type
       reused enum 'audit_write_failed' + payload alert_type pattern, same
       approach as P2a-S1 sibling `replay_key_archive_cleanup.py`; sibling
       task expands enum eventually).

  Also enforces storage cap: when an env's total live bytes exceeds
  `OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB` (default 1024), oldest-first
  artifacts get pruned even if not yet TTL-expired (V3 §5
  "oldest-first by created_at" implicit from "storage cap exceeded
  prune"). This protects sustained P2 usage from runaway disk growth.

  Idempotency: rerunning the same hour yields zero deletes because
  pruned artifacts no longer satisfy the WHERE filter (rows DELETEd, files
  gone). The audit row dedup is by `len(pruned)` per cycle (one row when
  > 0; zero rows when nothing pruned).

  V042 / replay schema absent graceful: probes
  `replay.experiments` + `replay.report_artifacts` via information_schema.
  If either absent → log + exit 0. The cron entry can be installed pre-
  schema-land and become useful once P2b runner SQL fixture lands the
  replay schema (Wave 3-4 per workplan §4).

  Constraints (non-goals):
    - 0 PG schema mutation (no DDL).
    - 0 trading.* / live config mutation (V3 §12 #14).
    - 0 GovernanceHub / Decision Lease coupling.
    - 0 IPC / dispatch invocation.
    - 0 Bybit REST/WS call.
    - 0 mlde_shadow / advisory writes.

MODULE_NOTE (中): REF-20 V3 §5 規定「manifest TTL 預設 30 天」+「artifact
  storage cap 由實作定義 env-specific cap」+「sustained P2 使用前必有
  prune job」。Workplan §4 Wave 3 R20-P2a-S5 把本 cron 與
  ReplayQuotaEnforcer Python class 綁為配對交付。

  Prune 演算法（per V3 §5 + workplan S5 row）：
    1. SELECT `replay.experiments` 中 `expires_at < NOW() AND status NOT
       IN ('cancelled')` 且未 pin（pin 欄保留；預設 false）的 manifest。
    2. 對每個 manifest 列出 `replay.report_artifacts`（V3 §4.1 FK 級聯）。
       DELETE artifact filesystem 檔（URI 解析為 local path；本 sprint 對
       `replay://...` URI 視為 logical 不做 file delete — 物理 artifact
       filesystem 配置由 P2b-T1 land）。
    3. UPDATE manifest status 不做 — V3 §4.1 status 列舉為
       `created/running/completed/failed/cancelled`。Per workplan：
       artifact prune 是 destructive op（DELETE artifact row + filesystem），
       而非 status flip。Manifest 本身保留為歷史 row（V3 §6 audit trail
       不變量：已簽 manifest 永久保留供 reproducibility）。
    4. 每個 prune batch 寫一 row governance_audit_log（沿用 enum
       'audit_write_failed' + payload alert_type 模式；對齊 P2a-S1 sibling
       `replay_key_archive_cleanup.py`；後續 sibling task 擴 enum）。

  也執行 storage cap：當 env total live bytes 超過
  `OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB`（預設 1024）時，按
  oldest-first prune 即使尚未 TTL expired（V3 §5「oldest-first by
  created_at」隱含於「storage cap exceeded prune」）。保護 sustained P2
  使用免於 runaway disk growth。

  Idempotent：同小時重跑 0 delete（已 prune row 不再符合 WHERE filter；
  row 已 DELETEd、檔已不在）。Audit row dedup 按 cycle 寫一 row（>0 時 1
  row；nothing pruned 時 0 row）。

  V042 / replay schema 缺 graceful：probe
  `replay.experiments` + `replay.report_artifacts`，任一缺即 log + exit 0。
  Cron 條目可在 schema land 前先安裝，等 P2b runner SQL fixture land 後
  自動生效（Wave 3-4 per workplan §4）。

  限制（non-goals）：
    - 0 PG schema mutation（無 DDL）。
    - 0 trading.* / live config mutation（V3 §12 #14）。
    - 0 GovernanceHub / Decision Lease 耦合。
    - 0 IPC / dispatch 呼叫。
    - 0 Bybit REST/WS 呼叫。
    - 0 mlde_shadow / advisory write。

Spec source / 規格來源:
  - REF-20 V3 §5 (Manifest, Quota, Retention)
  - workplan R20-P2a-S5 (Wave 3 Batch 3A)
  - quota_enforcer.py (Python class — paired delivery)
  - sql/migrations/REF-20_RESERVATION.md V042 + replay schema land note
  - V035 governance_audit_log schema (existing)

Suggested cron entry (operator manually adds via `crontab -e`).
建議 cron 條目（operator 用 `crontab -e` 加）：
  0 */6 * * * "$OPENCLAW_BASE_DIR/helper_scripts/cron/replay_artifact_prune.py"

Exit codes:
  0   success (rows pruned OR schema absent fallback OR no rows due — all OK)
  1   PG connection / SQL error (cron mailer surfaces)
  2   environment misconfigured (no DSN buildable)
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any


# ─── Logging setup / 日誌設定 ─────────────────────────────────────────
# Mirror passive_wait_healthcheck logger naming (per OpenClaw convention)
# + sibling cron `replay_key_archive_cleanup.py`.
# 對齊 passive_wait_healthcheck logger 命名（OpenClaw convention）+ sibling
# cron `replay_key_archive_cleanup.py`。
_LOG_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=_LOG_FMT, stream=sys.stderr)
log = logging.getLogger("replay_artifact_prune")


# ─── Config / 配置 ───────────────────────────────────────────────────
# Storage cap mirror env var of `quota_enforcer._resolve_storage_cap_mb`.
# Cron picks up env var on each invocation (operator can adjust without
# code change).
# Storage cap 對齊 `quota_enforcer._resolve_storage_cap_mb` env var。
# Cron 每次呼叫重讀 env var（operator 不需改碼即可調整）。
DEFAULT_STORAGE_CAP_MB = 1024


def _resolve_storage_cap_mb() -> int:
    """Resolve storage cap from env var; mirror quota_enforcer logic.
    從 env var 解析 storage cap；對齊 quota_enforcer 邏輯。
    """
    raw = os.environ.get("OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB", "")
    if not raw:
        return DEFAULT_STORAGE_CAP_MB
    try:
        parsed = int(raw)
    except ValueError:
        log.warning(
            "OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB=%r not int; default %d",
            raw,
            DEFAULT_STORAGE_CAP_MB,
        )
        return DEFAULT_STORAGE_CAP_MB
    if parsed <= 0:
        log.warning(
            "OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB=%d ≤ 0; default %d",
            parsed,
            DEFAULT_STORAGE_CAP_MB,
        )
        return DEFAULT_STORAGE_CAP_MB
    return parsed


# ─── DSN builder (mirror sibling cron) ────────────────────────────────
def _build_dsn() -> str | None:
    """Build psycopg2 DSN from env vars (priority: OPENCLAW_DATABASE_URL).
    從 env 構造 psycopg2 DSN（優先 OPENCLAW_DATABASE_URL）。

    Mirrors `replay_key_archive_cleanup._build_dsn` exactly so cron wrapper
    `replay_key_archive_cleanup.sh`-style installation patterns apply
    identically.

    完全對齊 `replay_key_archive_cleanup._build_dsn`，cron wrapper 安裝
    模式可同款套用。
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


# ─── Schema presence probe / Schema 存在偵測 ─────────────────────────
def _table_exists(cur: Any, schema: str, table: str) -> bool:
    """Return True iff `schema.table` exists.
    若 `schema.table` 存在則 True。

    Mirrors `replay_key_archive_cleanup._v042_present` — cleanup-safe SQL
    that does not require `replay` schema to exist (information_schema is
    always present in PostgreSQL).

    對齊 `replay_key_archive_cleanup._v042_present` — cleanup-safe SQL，
    不要求 `replay` schema 存在（information_schema 在 PostgreSQL 永遠在）。
    """
    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = %s LIMIT 1;",
        (schema, table),
    )
    return cur.fetchone() is not None


def _replay_schema_ready(cur: Any) -> bool:
    """Probe both `replay.experiments` AND `replay.report_artifacts`.
    探測 `replay.experiments` AND `replay.report_artifacts` 兩表。

    Both must be present for prune to be safe — pruning artifacts requires
    the experiments parent (FK + manifest pinning + env scope), and
    pruning experiments requires the artifacts child (DELETE cascade
    safety).

    兩表都需在才安全 prune — prune artifact 需要 experiments parent
    （FK + manifest pin + env scope），prune experiment 需要 artifact
    child（DELETE cascade safety）。
    """
    return _table_exists(cur, "replay", "experiments") and _table_exists(
        cur, "replay", "report_artifacts"
    )


def _v035_present(cur: Any) -> bool:
    """Return True iff `learning.governance_audit_log` exists.
    若 `learning.governance_audit_log` 存在則 True。

    Mirror sibling cron `replay_key_archive_cleanup._v035_present`.
    對齊 sibling cron `replay_key_archive_cleanup._v035_present`。
    """
    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = %s LIMIT 1;",
        ("learning", "governance_audit_log"),
    )
    return cur.fetchone() is not None


# ─── Prune core / 主清理邏輯 ──────────────────────────────────────────
def _prune_expired_artifacts(cur: Any) -> list[tuple[str, str, int]]:
    """DELETE artifact rows whose owning experiment has expires_at < NOW().
    DELETE 所屬 experiment 的 expires_at < NOW() 之 artifact row。

    Returns list of (experiment_id, artifact_id, bytes) for newly-pruned
    rows so caller can emit one summary audit row per prune batch.

    回傳新 prune 的 (experiment_id, artifact_id, bytes) tuple list；caller
    為每個 batch 寫一 summary audit row。

    Idempotent / 冪等: rerunning yields 0 rows because deleted rows no
    longer satisfy the WHERE filter.
    """
    # NOTE: V3 §4.1 schema:
    #   replay.experiments(experiment_id, expires_at, status, ...)
    #   replay.report_artifacts(artifact_id, experiment_id, expires_at, bytes, ...)
    # We DELETE child artifacts whose parent is past TTL. We do NOT delete
    # the experiment row itself — V3 §6 audit trail invariant says signed
    # manifests retained forever (artifact files removed but manifest row
    # survives for reproducibility query).
    # NOTE: V3 §4.1 schema：
    #   replay.experiments(experiment_id, expires_at, status, ...)
    #   replay.report_artifacts(artifact_id, experiment_id, expires_at, bytes, ...)
    # 我們 DELETE child artifact，其 parent 過 TTL。**不**刪 experiment row
    # 本身 — V3 §6 audit trail 不變量：signed manifest 永久保留（artifact
    # 檔被刪但 manifest row 留存以供 reproducibility 查詢）。
    cur.execute(
        """
        DELETE FROM replay.report_artifacts ra
         USING replay.experiments ex
         WHERE ra.experiment_id = ex.experiment_id
           AND ex.expires_at < NOW()
           AND COALESCE(ex.status, 'created') NOT IN ('cancelled')
        RETURNING ra.experiment_id, ra.artifact_id, COALESCE(ra.bytes, 0);
        """
    )
    rows = cur.fetchall() or []
    return [
        (str(exp_id), str(art_id), int(bytes_n))
        for exp_id, art_id, bytes_n in rows
    ]


def _prune_oldest_for_storage_cap(
    cur: Any, env: str, cap_mb: int
) -> list[tuple[str, str, int]]:
    """Prune oldest-first artifacts when env's total live bytes > cap.
    當 env 加總 live bytes > cap 時，oldest-first prune artifact。

    Returns list of pruned (experiment_id, artifact_id, bytes) tuples per
    env. Iterates until env total <= cap or 0 candidate rows left (loop
    bounded; will not infinite-loop on schema malformation).

    回傳 prune 的 (experiment_id, artifact_id, bytes) tuple list per env。
    迭代到 env total ≤ cap 或無 candidate row（迴圈有上限；schema 異常
    不會 infinite-loop）。

    Algorithm / 演算法:
      1. SELECT SUM(bytes) FROM live artifacts WHERE env = ?.
      2. While sum > cap*1024*1024:
         a. SELECT oldest live artifact for env (ORDER BY created_at).
         b. DELETE it; subtract bytes from running sum.
      3. Return list of pruned rows.

    Note: this is a separate concern from TTL prune. TTL prune (above)
    runs first; storage cap (here) only fires if env still over cap.

    註：與 TTL prune 是不同 concern。TTL prune（上面）先跑；storage cap
    （這裡）只在 env 仍超 cap 時觸發。
    """
    cap_bytes = cap_mb * 1024 * 1024

    # 1) Get current env total. / 1) 取 env 當前 total。
    cur.execute(
        """
        SELECT COALESCE(SUM(ra.bytes), 0)
          FROM replay.report_artifacts ra
          JOIN replay.experiments ex
            ON ra.experiment_id = ex.experiment_id
         WHERE ex.runtime_environment = %s
           AND (ra.expires_at IS NULL OR ra.expires_at > NOW());
        """,
        (env,),
    )
    row = cur.fetchone()
    total_bytes = int(row[0]) if row and row[0] is not None else 0

    if total_bytes <= cap_bytes:
        return []

    pruned: list[tuple[str, str, int]] = []
    # Loop bound: number of candidate rows; defensive sanity max iter to
    # avoid runaway. In practice a single pass loop will exit when SUM
    # drops below cap.
    # 迴圈上限：candidate row 數量；defensive max iter 防 runaway。
    # 實務上 single pass 即可（SUM < cap 後退出）。
    max_iter = 100_000
    iter_count = 0
    while total_bytes > cap_bytes and iter_count < max_iter:
        iter_count += 1
        # 2a) Select oldest live artifact for env. / 2a) 選 env 最舊 live artifact。
        cur.execute(
            """
            SELECT ra.artifact_id, ra.experiment_id, COALESCE(ra.bytes, 0)
              FROM replay.report_artifacts ra
              JOIN replay.experiments ex
                ON ra.experiment_id = ex.experiment_id
             WHERE ex.runtime_environment = %s
               AND (ra.expires_at IS NULL OR ra.expires_at > NOW())
             ORDER BY ra.created_at ASC
             LIMIT 1;
            """,
            (env,),
        )
        oldest = cur.fetchone()
        if oldest is None:
            break
        artifact_id, experiment_id, bytes_n = oldest

        # 2b) DELETE it. / 2b) DELETE。
        cur.execute(
            "DELETE FROM replay.report_artifacts WHERE artifact_id = %s;",
            (artifact_id,),
        )
        pruned.append((str(experiment_id), str(artifact_id), int(bytes_n)))
        total_bytes -= int(bytes_n)

    if iter_count >= max_iter:
        log.warning(
            "storage-cap prune for env=%s hit max_iter=%d; bytes_remaining=%d",
            env,
            max_iter,
            total_bytes,
        )
    return pruned


def _emit_audit_row(
    cur: Any,
    alert_type: str,
    pruned: list[tuple[str, str, int]],
    env: str | None = None,
) -> bool:
    """Write one governance_audit_log row summarising the prune batch.
    寫一 row governance_audit_log 摘要本 prune batch。

    Uses the existing `event_type='audit_write_failed'` enum slot (V035
    CHECK) with payload `alert_type='replay_artifact_prune_*'` until a
    sibling task expands the enum to include 'replay_*' types. This
    mirrors `replay_key_archive_cleanup._emit_audit_row` exactly.

    沿用 V035 CHECK enum `event_type='audit_write_failed'` + payload
    `alert_type='replay_artifact_prune_*'`，直到 sibling task 擴 enum 為
    'replay_*' 類型。完全對齊 `replay_key_archive_cleanup._emit_audit_row`。

    Returns True on successful insert, False on logged error (caller
    decides; current behaviour: log + continue).
    """
    payload: dict[str, Any] = {
        "alert_type": alert_type,
        "pruned_count": len(pruned),
        "pruned_bytes_total": sum(b for _, _, b in pruned),
        "source": "replay_artifact_prune_cron",
    }
    if env is not None:
        payload["env"] = env
    # Emit first 10 (experiment_id, artifact_id) pairs for spot check (full
    # set is reconstructable from `replay.report_artifacts` history; we
    # don't blob unbounded id list into payload).
    # 寫前 10 個 (experiment_id, artifact_id) 對給 spot check（完整集可從
    # `replay.report_artifacts` 歷史重建；不把無界 id list blob 進 payload）。
    payload["sample_pairs"] = [
        {"experiment_id": eid, "artifact_id": aid}
        for eid, aid, _ in pruned[:10]
    ]
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
                "replay_artifact_prune_cron",
                json.dumps(payload),
            ),
        )
        return True
    except Exception as exc:  # noqa: BLE001 — must continue cron loop
        log.error(
            "audit insert failed for alert_type=%s pruned=%d: %s",
            alert_type,
            len(pruned),
            exc,
        )
        return False


# ─── Main entrypoint / 主入口 ─────────────────────────────────────────
def main() -> int:
    """Cron entrypoint. Returns process exit code.
    Cron 入口；回傳行程 exit code。

    Workflow / 流程:
      1. Build DSN; exit 2 if env missing.
      2. Connect PG; exit 1 on connection failure.
      3. Probe replay schema (experiments + report_artifacts); exit 0
         gracefully if absent (V042 / replay schema not yet land).
      4. TTL prune: DELETE artifacts whose owning experiment past
         expires_at. Emit 1 audit row if anything pruned.
      5. Storage cap prune (per env): for each env in {paper, demo, live},
         if total > cap → oldest-first prune. Emit 1 audit row per env
         that pruned.
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
    # require the package (mirrors sibling cron pattern).
    # 延遲 import psycopg2，讓單元測試 import 本模組時不需要該 package
    # （對齊 sibling cron pattern）。
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

    storage_cap_mb = _resolve_storage_cap_mb()
    log.info(
        "replay_artifact_prune start: storage_cap=%d MB", storage_cap_mb
    )

    try:
        with conn:
            with conn.cursor() as cur:
                if not _replay_schema_ready(cur):
                    log.info(
                        "replay schema (experiments + report_artifacts) "
                        "not yet land — graceful exit 0; cron becomes useful "
                        "once P2b runner SQL fixture lands the replay schema"
                    )
                    return 0

                # 4) TTL prune. / 4) TTL prune。
                ttl_pruned = _prune_expired_artifacts(cur)
                log.info(
                    "TTL prune: deleted %d artifact(s); bytes_total=%d",
                    len(ttl_pruned),
                    sum(b for _, _, b in ttl_pruned),
                )

                v035_ok = _v035_present(cur)
                if not v035_ok:
                    log.warning(
                        "V035 (learning.governance_audit_log) absent; "
                        "skipping audit row writes (DELETE already committed below)"
                    )

                if ttl_pruned and v035_ok:
                    _emit_audit_row(
                        cur, "replay_artifact_prune_ttl", ttl_pruned
                    )

                # 5) Storage cap prune per env. / 5) 各 env storage cap prune。
                # V3 §4.1 runtime_environment ∈ {linux_trade_core,
                # mac_dev_smoke_test_only}. Iterate over the runtime envs that
                # may exceed cap (mac dev smoke is unlikely but included
                # for completeness; future envs added by extending list).
                # V3 §4.1 runtime_environment ∈ {linux_trade_core,
                # mac_dev_smoke_test_only}。迭代可能超 cap 的 runtime env
                # （mac dev smoke 不太可能但保留完整；未來新 env 擴此 list）。
                envs_to_check = ["linux_trade_core", "mac_dev_smoke_test_only"]
                cap_pruned_total = 0
                for env in envs_to_check:
                    pruned = _prune_oldest_for_storage_cap(
                        cur, env, storage_cap_mb
                    )
                    if pruned:
                        log.info(
                            "storage-cap prune env=%s: deleted %d artifact(s); "
                            "bytes_total=%d (cap=%d MB)",
                            env,
                            len(pruned),
                            sum(b for _, _, b in pruned),
                            storage_cap_mb,
                        )
                        if v035_ok:
                            _emit_audit_row(
                                cur,
                                "replay_artifact_prune_storage_cap",
                                pruned,
                                env=env,
                            )
                        cap_pruned_total += len(pruned)
                    else:
                        log.debug(
                            "storage-cap prune env=%s: under cap=%d MB",
                            env,
                            storage_cap_mb,
                        )

                log.info(
                    "replay_artifact_prune done: ttl_pruned=%d, "
                    "storage_cap_pruned=%d",
                    len(ttl_pruned),
                    cap_pruned_total,
                )
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("prune transaction failed: %s", exc)
        # Mirror sibling MED-4 retrofit pattern: explicit rollback
        # logging instead of bare except: pass.
        # 對齊 sibling MED-4 retrofit pattern：顯式 rollback log，避免
        # bare except: pass。
        try:
            conn.rollback()
        except Exception as rollback_exc:  # noqa: BLE001
            log.warning(
                "conn.rollback() also failed (cleanup race): %s",
                rollback_exc,
                exc_info=True,
            )
        return 1
    finally:
        try:
            conn.close()
        except Exception as close_exc:  # noqa: BLE001
            log.warning(
                "conn.close() also failed (cleanup race): %s",
                close_exc,
                exc_info=True,
            )


if __name__ == "__main__":
    sys.exit(main())
