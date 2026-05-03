#!/usr/bin/env python3
"""wave9_business_kpi_collector.py — REF-20 Wave 9 R20-W9-T2

Daily cron: collect P6 business KPI samples on 7d + 14d rolling windows.
每日 cron：以 7 天 + 14 天滾動窗口採集 P6 業務 KPI 樣本。

MODULE_NOTE (EN): REF-20 V3 §11 P6 specifies these business KPIs that must
  be sampled continuously after P6 deploy:

    1. replay_routes_daily_request_count       — daily request count to
                                                  /api/v1/replay/* routes
                                                  (V045 run_state row count
                                                  in window).
    2. manifest_verify_fail_mode_breakdown     — counts per fail mode
                                                  (signature_invalid /
                                                   manifest_expired /
                                                   key_retired /
                                                   key_expired) from
                                                  governance_audit_log.
    3. handoff_success_rate                    — handoff_requests rows
                                                  WHERE result='success' /
                                                  total in window.
    4. quota_cap_hit_rate                      — governance_audit_log rows
                                                  WHERE alert_type LIKE
                                                  'replay_artifact_prune_storage_cap%'
                                                  / total prune rows.
    5. cost_edge_ratio_p50                     — median cost_regime_ratio
                                                  from
                                                  governance_audit_log
                                                  rows in window.
    6. dsr_pbo_gate_fire_rate                  — count of governance_audit_log
                                                  rows with
                                                  rule_failures containing
                                                  'DSR' or 'PBO' / total
                                                  review_live_candidate
                                                  rows.

  Each KPI is sampled on both 7d and 14d windows (per V3 §11 P6 KPI list);
  results written to replay.business_kpi_snapshots via UPSERT
  (UNIQUE(snapshot_date, window_type, kpi_name)).

  Idempotency: re-running same day yields same result (UPSERT pattern via
  ON CONFLICT DO UPDATE on UNIQUE triple). Each cron cycle replaces the
  previous day's snapshot for the same date; cron at 06:00 UTC means
  snapshot_date = today (UTC).

  V047 graceful absent: probes
  `replay.business_kpi_snapshots` via information_schema.
  If absent → log + exit 0. The cron entry can be installed pre-V047-land
  without alarm.

  Mac dev environment override: when OPENCLAW_WAVE9_KPI_MOCK=1 env var is
  set, the cron writes to /tmp/wave9_kpi_test_only/snapshot.jsonl instead
  of the DB. This lets us validate the cron logic on Mac without spinning
  up real PG (mirror sibling cron pattern for development testing).

MODULE_NOTE (中): REF-20 V3 §11 P6 規定 P6 deploy 後必持續採樣的業務 KPI
  6 項：

    1. replay_routes_daily_request_count       — V045 run_state row count
    2. manifest_verify_fail_mode_breakdown     — 4 個 fail mode count
    3. handoff_success_rate                    — handoff success / total
    4. quota_cap_hit_rate                      — quota cap 命中 / prune total
    5. cost_edge_ratio_p50                     — cost_regime_ratio 中位
    6. dsr_pbo_gate_fire_rate                  — DSR/PBO 拒絕率

  每個 KPI 在 7d + 14d 兩個窗口採樣；UPSERT 寫 replay.business_kpi_snapshots
  （UNIQUE(snapshot_date, window_type, kpi_name)）。

  Idempotent：同日重跑得同結果（UPSERT pattern via ON CONFLICT DO UPDATE）。

  V047 graceful absent：表缺即 log + exit 0；cron 條目可在 V047 land 前
  先安裝。

  Mac dev 環境覆蓋：當 OPENCLAW_WAVE9_KPI_MOCK=1 時，cron 寫到
  /tmp/wave9_kpi_test_only/snapshot.jsonl 而非 DB；讓 Mac 沒 PG 也能驗證
  cron 邏輯。

Spec source / 規格來源:
  - REF-20 V3 §11 P6 Business KPI list
  - workplan R20-W9-T2 (Wave 9)
  - V047 replay.business_kpi_snapshots schema
  - sibling cron pattern: replay_artifact_prune.py

Suggested cron entry (operator manually adds via `crontab -e`).
建議 cron 條目（operator 用 `crontab -e` 加）：
  0 6 * * * "$OPENCLAW_BASE_DIR/helper_scripts/cron/wave9_business_kpi_collector.py"

Exit codes:
  0   success (rows upserted OR V047 absent fallback OR mock mode write OK)
  1   PG connection / SQL error (cron mailer surfaces)
  2   environment misconfigured (no DSN buildable; not in mock mode)
"""
from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


# ─── Logging setup / 日誌設定 ─────────────────────────────────────────
_LOG_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=_LOG_FMT, stream=sys.stderr)
log = logging.getLogger("wave9_business_kpi_collector")


# ─── KPI list / KPI 名單 ────────────────────────────────────────────
# V3 §11 P6 KPI list. Each KPI name maps to a sampler function below.
# V3 §11 P6 KPI 名單；每個 KPI 名稱對應下方 sampler 函數。
KPI_NAMES = (
    "replay_routes_daily_request_count",
    "manifest_verify_fail_mode_breakdown",
    "handoff_success_rate",
    "quota_cap_hit_rate",
    "cost_edge_ratio_p50",
    "dsr_pbo_gate_fire_rate",
)

# Both windows sampled per KPI (per V3 §11 P6).
# 每個 KPI 兩個窗口（per V3 §11 P6）。
WINDOW_TYPES = ("7d", "14d")


# ─── KPI sample dataclass / KPI 樣本資料類 ──────────────────────────


@dataclass(slots=True)
class KpiSample:
    """One (snapshot_date, window_type, kpi_name) sample.

    一個 (snapshot_date, window_type, kpi_name) 樣本。
    """

    kpi_name: str
    window_type: str
    kpi_value: float | None
    sample_size: int | None
    extra: dict[str, Any] = field(default_factory=dict)


# ─── DSN builder (mirror sibling cron) ────────────────────────────────


def _build_dsn() -> str | None:
    """Build psycopg2 DSN from env vars (mirror sibling cron).
    從 env 構造 DSN（對齊 sibling cron）。
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


# ─── Schema presence probe / Schema 偵測 ────────────────────────────


def _v047_present(cur: Any) -> bool:
    """True iff replay.business_kpi_snapshots exists.
    若 replay.business_kpi_snapshots 存在則 True。
    """
    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = %s LIMIT 1;",
        ("replay", "business_kpi_snapshots"),
    )
    return cur.fetchone() is not None


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


# ─── Per-KPI samplers / 每 KPI sampler ─────────────────────────────


def _sample_routes_request_count(
    cur: Any, window_days: int
) -> tuple[float | None, int | None, dict[str, Any]]:
    """Sample replay_routes_daily_request_count.

    採樣 V045 replay.run_state row count in window — proxy for daily
    request count (each /api/v1/replay/run POST creates one row).

    從 V045 replay.run_state row count（窗口內）— /api/v1/replay/run
    POST 的 proxy。
    """
    if not _table_present(cur, "replay", "run_state"):
        return None, None, {"absent_table": "replay.run_state"}
    cur.execute(
        "SELECT COUNT(*) FROM replay.run_state "
        "WHERE created_at >= NOW() - INTERVAL '%s days';",
        (window_days,),
    )
    row = cur.fetchone()
    count = int(row[0]) if row and row[0] is not None else 0
    # KPI value is the avg per day; sample size is total count.
    # KPI value = 日均；sample size = 總數。
    avg_per_day = float(count) / float(window_days) if window_days > 0 else 0.0
    return avg_per_day, count, {"total_in_window": count}


def _sample_manifest_verify_fail_modes(
    cur: Any, window_days: int
) -> tuple[float | None, int | None, dict[str, Any]]:
    """Sample manifest_verify_fail_mode_breakdown.

    Count rows from learning.governance_audit_log where payload
    alert_type LIKE 'replay_manifest_%_fail' or alert_type matches the
    4 known fail modes (signature_invalid / manifest_expired /
    key_retired / key_expired).

    從 learning.governance_audit_log 抓 payload alert_type 中的 4 fail
    mode 計數。
    """
    if not _table_present(cur, "learning", "governance_audit_log"):
        return None, None, {"absent_table": "learning.governance_audit_log"}

    # Composite KPI: count per fail mode + total.
    # 複合 KPI：每 fail mode count + 總數。
    fail_modes = (
        "signature_invalid",
        "manifest_expired",
        "key_retired",
        "key_expired",
    )
    counts: dict[str, int] = {}
    total = 0
    for fm in fail_modes:
        cur.execute(
            """
            SELECT COUNT(*) FROM learning.governance_audit_log
             WHERE ts >= NOW() - INTERVAL '%s days'
               AND payload->>'alert_type' = %s;
            """,
            (window_days, fm),
        )
        row = cur.fetchone()
        c = int(row[0]) if row and row[0] is not None else 0
        counts[fm] = c
        total += c
    # KPI value = total fail count; extra = per-mode breakdown.
    return float(total), total, {"per_mode": counts}


def _sample_handoff_success_rate(
    cur: Any, window_days: int
) -> tuple[float | None, int | None, dict[str, Any]]:
    """Sample handoff_success_rate.

    handoff_requests rows in window where result='success' / total in window.
    handoff_requests 中 result='success' 的比例（窗口內）。
    """
    if not _table_present(cur, "replay", "handoff_requests"):
        return None, None, {"absent_table": "replay.handoff_requests"}
    cur.execute(
        """
        SELECT
            COUNT(*) FILTER (WHERE result = 'success') AS success_count,
            COUNT(*) AS total_count
          FROM replay.handoff_requests
         WHERE ts >= NOW() - INTERVAL '%s days';
        """,
        (window_days,),
    )
    row = cur.fetchone()
    success = int(row[0]) if row and row[0] is not None else 0
    total = int(row[1]) if row and row[1] is not None else 0
    rate = success / total if total > 0 else None
    return rate, total, {"success_count": success, "total_count": total}


def _sample_quota_cap_hit_rate(
    cur: Any, window_days: int
) -> tuple[float | None, int | None, dict[str, Any]]:
    """Sample quota_cap_hit_rate.

    governance_audit_log rows with alert_type='replay_artifact_prune_storage_cap'
    / all replay_artifact_prune_* rows.

    governance_audit_log 中 storage_cap 命中 / 全 prune row 比例。
    """
    if not _table_present(cur, "learning", "governance_audit_log"):
        return None, None, {"absent_table": "learning.governance_audit_log"}
    cur.execute(
        """
        SELECT
            COUNT(*) FILTER (
                WHERE payload->>'alert_type' = 'replay_artifact_prune_storage_cap'
            ) AS cap_hits,
            COUNT(*) FILTER (
                WHERE payload->>'alert_type' LIKE 'replay_artifact_prune%%'
            ) AS total_prunes
          FROM learning.governance_audit_log
         WHERE ts >= NOW() - INTERVAL '%s days';
        """,
        (window_days,),
    )
    row = cur.fetchone()
    cap_hits = int(row[0]) if row and row[0] is not None else 0
    total_prunes = int(row[1]) if row and row[1] is not None else 0
    rate = cap_hits / total_prunes if total_prunes > 0 else None
    return rate, total_prunes, {
        "cap_hits": cap_hits,
        "total_prunes": total_prunes,
    }


def _sample_cost_edge_ratio_p50(
    cur: Any, window_days: int
) -> tuple[float | None, int | None, dict[str, Any]]:
    """Sample cost_edge_ratio_p50.

    Median cost_regime_ratio (V035 column) from governance_audit_log rows in window.
    governance_audit_log 中 cost_regime_ratio 的中位（窗口內）。
    """
    if not _table_present(cur, "learning", "governance_audit_log"):
        return None, None, {"absent_table": "learning.governance_audit_log"}
    cur.execute(
        """
        SELECT
            percentile_cont(0.5) WITHIN GROUP (ORDER BY cost_regime_ratio) AS p50,
            COUNT(cost_regime_ratio) AS sample_n
          FROM learning.governance_audit_log
         WHERE ts >= NOW() - INTERVAL '%s days'
           AND cost_regime_ratio IS NOT NULL;
        """,
        (window_days,),
    )
    row = cur.fetchone()
    p50 = float(row[0]) if row and row[0] is not None else None
    sample_n = int(row[1]) if row and row[1] is not None else 0
    return p50, sample_n, {"p50": p50, "n": sample_n}


def _sample_dsr_pbo_gate_fire_rate(
    cur: Any, window_days: int
) -> tuple[float | None, int | None, dict[str, Any]]:
    """Sample dsr_pbo_gate_fire_rate.

    Count review_live_candidate rows with rule_failures containing 'DSR'
    or 'PBO' / total review rows.

    review_live_candidate row 中 rule_failures 含 'DSR' 或 'PBO' 的比例。
    """
    if not _table_present(cur, "learning", "governance_audit_log"):
        return None, None, {"absent_table": "learning.governance_audit_log"}
    cur.execute(
        """
        SELECT
            COUNT(*) FILTER (
                WHERE 'DSR' = ANY(rule_failures) OR 'PBO' = ANY(rule_failures)
            ) AS gate_fires,
            COUNT(*) AS total_reviews
          FROM learning.governance_audit_log
         WHERE ts >= NOW() - INTERVAL '%s days'
           AND event_type = 'review_live_candidate';
        """,
        (window_days,),
    )
    row = cur.fetchone()
    fires = int(row[0]) if row and row[0] is not None else 0
    total = int(row[1]) if row and row[1] is not None else 0
    rate = fires / total if total > 0 else None
    return rate, total, {
        "gate_fires": fires,
        "total_reviews": total,
    }


# ─── Sampler dispatch / Sampler 分派 ────────────────────────────────


_SAMPLER_DISPATCH = {
    "replay_routes_daily_request_count": _sample_routes_request_count,
    "manifest_verify_fail_mode_breakdown": _sample_manifest_verify_fail_modes,
    "handoff_success_rate": _sample_handoff_success_rate,
    "quota_cap_hit_rate": _sample_quota_cap_hit_rate,
    "cost_edge_ratio_p50": _sample_cost_edge_ratio_p50,
    "dsr_pbo_gate_fire_rate": _sample_dsr_pbo_gate_fire_rate,
}


def _sample_all_kpis(cur: Any) -> list[KpiSample]:
    """Sample all KPIs on both windows; return list of KpiSample.
    在兩個窗口採樣所有 KPI；回 KpiSample list。
    """
    samples: list[KpiSample] = []
    for window in WINDOW_TYPES:
        window_days = 7 if window == "7d" else 14
        for kpi_name in KPI_NAMES:
            sampler = _SAMPLER_DISPATCH.get(kpi_name)
            if sampler is None:
                log.warning("no sampler for kpi_name=%s; skipping", kpi_name)
                continue
            try:
                kpi_value, sample_size, extra = sampler(cur, window_days)
            except Exception as exc:  # noqa: BLE001 — log + continue
                log.error(
                    "sampler %s failed on window=%s: %s",
                    kpi_name, window, exc,
                )
                continue
            samples.append(
                KpiSample(
                    kpi_name=kpi_name,
                    window_type=window,
                    kpi_value=kpi_value,
                    sample_size=sample_size,
                    extra=extra,
                )
            )
    return samples


# ─── Snapshot writer / Snapshot 寫入 ────────────────────────────────


def _write_snapshots(cur: Any, samples: list[KpiSample]) -> int:
    """UPSERT snapshots into replay.business_kpi_snapshots.
    UPSERT 寫 replay.business_kpi_snapshots。

    Returns count of rows upserted (insertions or updates).
    回上插 row 數（insert 或 update）。
    """
    snapshot_date = datetime.now(timezone.utc).date()
    count = 0
    for s in samples:
        cur.execute(
            """
            INSERT INTO replay.business_kpi_snapshots
              (snapshot_id, snapshot_date, window_type, kpi_name,
               kpi_value, sample_size)
            VALUES
              (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (snapshot_date, window_type, kpi_name)
            DO UPDATE SET
              kpi_value = EXCLUDED.kpi_value,
              sample_size = EXCLUDED.sample_size,
              created_at = NOW();
            """,
            (
                str(uuid.uuid4()),
                snapshot_date,
                s.window_type,
                s.kpi_name,
                s.kpi_value,
                s.sample_size,
            ),
        )
        count += 1
    return count


# ─── Mock-mode writer (Mac dev) / Mock 模式寫入（Mac dev）─────────


def _write_mock_snapshots(samples: list[KpiSample]) -> Path:
    """Write samples to /tmp/wave9_kpi_test_only/snapshot.jsonl (Mac dev).

    寫樣本到 /tmp/wave9_kpi_test_only/snapshot.jsonl（Mac dev 模式）。

    Returns path written.
    回寫入路徑。
    """
    out_dir = Path("/tmp/wave9_kpi_test_only")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "snapshot.jsonl"
    snapshot_date = datetime.now(timezone.utc).date().isoformat()

    with out_path.open("w", encoding="utf-8") as f:
        for s in samples:
            row = {
                "snapshot_date": snapshot_date,
                "window_type": s.window_type,
                "kpi_name": s.kpi_name,
                "kpi_value": s.kpi_value,
                "sample_size": s.sample_size,
                "extra": s.extra,
                "mock": True,
            }
            f.write(json.dumps(row, default=str) + "\n")

    return out_path


# ─── Main entrypoint / 主入口 ─────────────────────────────────────────


def main() -> int:
    """Cron entrypoint. Returns process exit code.
    Cron 入口；回傳行程 exit code。

    Workflow / 流程:
      1. Detect mock mode (OPENCLAW_WAVE9_KPI_MOCK=1).
      2. Build DSN; in mock mode this can be skipped.
      3. Connect PG (skip in mock mode).
      4. Probe V047 presence; exit 0 graceful if absent.
      5. Sample all KPIs on 7d + 14d windows.
      6. UPSERT snapshots (or write mock JSONL).
      7. Commit; exit 0.
    """
    mock_mode = os.environ.get("OPENCLAW_WAVE9_KPI_MOCK", "") == "1"

    if mock_mode:
        # Mac dev mock mode — no DB, write JSONL to /tmp/.
        # Mac dev mock 模式 — 不連 DB，寫 JSONL 到 /tmp/。
        log.info("mock mode active: writing to /tmp/wave9_kpi_test_only/")
        # In mock mode, we still need a fake cursor for samplers.
        # We construct a no-op cursor that returns (0, None) for everything.
        # Mock 模式下仍需 fake cursor 給 sampler；我們構造一個 no-op cursor，
        # 讓所有 sampler 回 (0, None)。

        class _NoOpCursor:
            """Mock cursor returning (0, None) for all queries.
            Mock cursor 對所有查詢回 (0, None)。
            """

            def execute(self, sql: str, params: Any = None) -> None:
                pass

            def fetchone(self) -> Any:
                # Return None for absence probes; (0, 0) for COUNT queries.
                # information_schema probe → None means absent.
                # 對 absence probe 回 None；對 COUNT 查詢回 (0, 0)。
                return None

        # Skip DB sampling; write empty/skeleton snapshot for testing.
        # 跳過 DB 採樣；寫空/骨架 snapshot 供測試。
        no_op = _NoOpCursor()
        samples = _sample_all_kpis(no_op)  # Will produce skeleton samples.
        out_path = _write_mock_snapshots(samples)
        log.info(
            "mock snapshot written to %s (%d samples, all extra={'absent_table': ...})",
            out_path,
            len(samples),
        )
        return 0

    # Production mode / 生產模式
    dsn = _build_dsn()
    if dsn is None:
        log.error(
            "DSN unavailable — set OPENCLAW_DATABASE_URL or POSTGRES_{USER,PASSWORD,DB} "
            "(or set OPENCLAW_WAVE9_KPI_MOCK=1 for Mac dev)"
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
        with conn:
            with conn.cursor() as cur:
                if not _v047_present(cur):
                    log.info(
                        "V047 (replay.business_kpi_snapshots) not yet "
                        "applied — graceful exit 0; cron becomes useful "
                        "once V047 lands"
                    )
                    return 0

                samples = _sample_all_kpis(cur)
                count = _write_snapshots(cur, samples)
                log.info(
                    "wave9_business_kpi_collector: upserted %d sample(s) "
                    "across %d window(s) × %d KPI(s)",
                    count,
                    len(WINDOW_TYPES),
                    len(KPI_NAMES),
                )
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("collector transaction failed: %s", exc)
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
