"""Model registry writer (INFRA-PREBUILD-1 Part B, 2026-04-23).
Model registry 寫入器（INFRA-PREBUILD-1 B 部）。

MODULE_NOTE (EN): Persists ONNX artifact + canary deployment metadata to
  `learning.model_registry` (V023 migration). Called from
  `run_training_pipeline.py` right after `export_quantile_trio_to_onnx`
  succeeds with verdict != 'no_ship'. One registry row per (strategy,
  engine_mode, quantile, schema_version, train_date) — ON CONFLICT DO
  UPDATE refreshes the row so re-training the same slot replaces its
  metadata without losing canary_status / promoted_at (those are
  Operator-controlled via IPC/API, not training-controlled).

  Also offers `transition_canary_status` for Operator flip from shadow →
  promoting → production → retired (with optional retirement_reason),
  used by /api/v1/ml/model_promote (lands in B5).

  Graceful degradation: DB unavailable → log + return None. Callers treat
  None as "registry write skipped" and keep going (ONNX artifact + symlink
  still produced — registry is a catalogue, not the blob).

MODULE_NOTE (中): 將 ONNX artifact 與 canary 部署 metadata 寫入
  `learning.model_registry`（V023）。`run_training_pipeline.py` 於
  `export_quantile_trio_to_onnx` 成功且 verdict != 'no_ship' 後呼叫。
  每筆 (strategy, engine_mode, quantile, schema_version, train_date) 一列，
  ON CONFLICT DO UPDATE 讓 re-training 刷新 metadata 而不丟 canary_status。
  另提供 `transition_canary_status` 供 operator 透過 API/IPC 推進
  shadow → promoting → production → retired 的狀態機。
  DB 不可用 → log + 回 None；callers 視為 skip，ONNX artifact + symlink
  仍產出（registry 是目錄，不是 blob）。

Spec: sql/migrations/V023__model_registry.sql
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Canary status state-machine values (keep aligned with V023 CHECK constraint).
# 狀態機值（與 V023 CHECK 對齊）。
CANARY_SHADOW = "shadow"
CANARY_PROMOTING = "promoting"
CANARY_PRODUCTION = "production"
CANARY_RETIRED = "retired"
CANARY_REJECTED = "rejected"

CANARY_STATES: tuple[str, ...] = (
    CANARY_SHADOW,
    CANARY_PROMOTING,
    CANARY_PRODUCTION,
    CANARY_RETIRED,
    CANARY_REJECTED,
)

# Verdict values from quantile_reports.py (mirror, don't import — circular dep).
# Verdict 值（鏡射；不 import 避免循環依賴）。
VERDICT_SHOULD_SHIP = "should_ship"
VERDICT_SHADOW_ONLY = "shadow_only"
VERDICT_NO_SHIP = "no_ship"


def _file_size_and_sha256(path: str) -> tuple[Optional[int], Optional[str]]:
    """Compute (size_bytes, sha256_hex) for an existing file.
    計算檔案大小 + sha256；不存在 → (None, None) 不拋。

    Caller decides whether missing-file is fatal. Registry writer treats it as
    "best-effort provenance" — the artifact path itself is the source of truth,
    integrity columns are audit candy.
    """
    try:
        stat = os.stat(path)
    except OSError as e:
        logger.warning("model_registry: stat %s failed: %s", path, e)
        return (None, None)
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(1 << 20):  # 1 MiB
                h.update(chunk)
        return (int(stat.st_size), h.hexdigest())
    except OSError as e:
        logger.warning("model_registry: sha256 %s failed: %s", path, e)
        return (int(stat.st_size), None)


def _connect(dsn: Optional[str] = None):
    """Open a short-lived psycopg connection. `None` dsn → env defaults.
    開一個短生命周期 psycopg 連線；dsn=None → 走 env 預設。

    Returns None if psycopg is missing or connection fails (graceful degradation
    — the writer is audit-only; a failed registry write never blocks training).
    回 None（psycopg 缺或連線失敗）時 graceful degrade；registry 純審計，
    寫失敗不擋訓練。
    """
    try:
        import psycopg
    except ImportError:
        logger.info("model_registry: psycopg not installed; skipping DB write")
        return None
    try:
        # DSN resolution mirrors parquet_etl._get_pg_conn so all ml_training
        # callers share identical DB wiring (OPENCLAW_DATABASE_URL first, then
        # POSTGRES_* env vars, then graceful skip).
        # DSN 解析與 parquet_etl._get_pg_conn 對齊；ml_training 模組統一走
        # OPENCLAW_DATABASE_URL → POSTGRES_* → skip。
        conninfo = (
            dsn
            or os.environ.get("OPENCLAW_DATABASE_URL")
            or os.environ.get("DSN")
        )
        if not conninfo:
            user = os.environ.get("POSTGRES_USER")
            password = os.environ.get("POSTGRES_PASSWORD")
            db = os.environ.get("POSTGRES_DB")
            if user and db:
                host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
                port = os.environ.get("POSTGRES_PORT", "5432")
                conninfo = f"postgresql://{user}:{password or ''}@{host}:{port}/{db}"
        if not conninfo:
            logger.info(
                "model_registry: no DSN (OPENCLAW_DATABASE_URL / DSN / POSTGRES_* all unset); skipping"
            )
            return None
        return psycopg.connect(conninfo)
    except Exception as e:  # noqa: BLE001 — any connect error → skip
        logger.warning("model_registry: connect failed: %s", e)
        return None


def register_model(
    *,
    strategy: str,
    engine_mode: str,
    quantile: str,
    schema_version: str,
    train_date: str,
    artifact_path: str,
    verdict: str,
    acceptance_report: Optional[Dict[str, Any]] = None,
    feature_schema_hash: Optional[str] = None,
    training_config_hash: Optional[str] = None,
    training_sample_size: Optional[int] = None,
    dsn: Optional[str] = None,
    created_by: str = "run_training_pipeline",
) -> Optional[int]:
    """Insert or refresh a row in `learning.model_registry`.
    插入或刷新 `learning.model_registry` 一列。

    Returns the row id on success, `None` when the write was skipped (DB
    unavailable) or declined (invalid verdict → no_ship shouldn't be registered).

    Semantics:
    - `no_ship` verdict → returns None without touching DB (ONNX export gate
      already skipped; registry stays clean).
    - ON CONFLICT on the unique key refreshes artifact + verdict + acceptance
      report but **preserves** `canary_status / promoted_at / retired_at`
      so re-training the same slot doesn't regress an already-promoted model
      to 'shadow'. Operator explicitly transitions via
      `transition_canary_status`.
    - INFRA-PREBUILD-1 audit L2-3 (2026-04-23) hardening: the ON CONFLICT DO
      UPDATE clause is filtered by
      `WHERE learning.model_registry.canary_status NOT IN ('promoting',
      'production')` — PostgreSQL's UPSERT-where rule skips the UPDATE entirely
      when the existing row is mid-promote or already in production. Without
      the filter, a re-training run would rewrite artifact_path / verdict /
      acceptance_report / created_by on top of a promoted slot, effectively
      swapping the live canary/production ONNX behind Operator's back. With
      the filter the UPDATE no-ops and `RETURNING id` yields nothing, so this
      function returns `None` — the caller can treat that as "slot is locked
      in promoting/production, skipping refresh" and act accordingly.

    回傳 row id 於成功；None = skip（DB 不可用 / verdict=no_ship 拒絕 / slot
    正在 promoting|production 被 WHERE 過濾跳過 DO UPDATE）。ON CONFLICT 刷新
    artifact/verdict/report 但**保留** canary_status / promoted_at / retired_at，
    並透過 `WHERE ... NOT IN ('promoting','production')` 保證 promoting/production
    slot 下的 artifact/verdict 全欄位不被 retrain 悄悄改寫；此時 RETURNING 無值
    → return None，caller 應視為「slot 已鎖，跳過刷新」。
    """
    if verdict == VERDICT_NO_SHIP:
        logger.info(
            "model_registry: verdict=no_ship for %s/%s/%s — not registering",
            strategy, engine_mode, quantile,
        )
        return None
    if verdict not in (VERDICT_SHOULD_SHIP, VERDICT_SHADOW_ONLY):
        logger.warning(
            "model_registry: unknown verdict %r; not registering %s/%s/%s",
            verdict, strategy, engine_mode, quantile,
        )
        return None

    conn = _connect(dsn)
    if conn is None:
        return None

    size, sha = _file_size_and_sha256(artifact_path)
    report_jsonb = json.dumps(acceptance_report) if acceptance_report is not None else None

    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO learning.model_registry (
                    strategy, engine_mode, quantile, schema_version, train_date,
                    artifact_path, artifact_size_bytes, artifact_sha256,
                    acceptance_report, verdict,
                    feature_schema_hash, training_config_hash, training_sample_size,
                    created_by
                ) VALUES (
                    %s, %s, %s, %s, %s::date,
                    %s, %s, %s,
                    %s::jsonb, %s,
                    %s, %s, %s,
                    %s
                )
                ON CONFLICT (strategy, engine_mode, quantile, schema_version, train_date)
                DO UPDATE SET
                    artifact_path        = EXCLUDED.artifact_path,
                    artifact_size_bytes  = EXCLUDED.artifact_size_bytes,
                    artifact_sha256      = EXCLUDED.artifact_sha256,
                    acceptance_report    = EXCLUDED.acceptance_report,
                    verdict              = EXCLUDED.verdict,
                    feature_schema_hash  = EXCLUDED.feature_schema_hash,
                    training_config_hash = EXCLUDED.training_config_hash,
                    training_sample_size = EXCLUDED.training_sample_size,
                    created_by           = EXCLUDED.created_by,
                    updated_at           = NOW()
                WHERE learning.model_registry.canary_status NOT IN ('promoting', 'production')
                RETURNING id
                """,
                (
                    strategy, engine_mode, quantile, schema_version, train_date,
                    artifact_path, size, sha,
                    report_jsonb, verdict,
                    feature_schema_hash, training_config_hash, training_sample_size,
                    created_by,
                ),
            )
            row = cur.fetchone()
            row_id = int(row[0]) if row else None
            logger.info(
                "model_registry: upsert id=%s %s/%s/%s verdict=%s",
                row_id, strategy, engine_mode, quantile, verdict,
            )
            return row_id
    except Exception as e:  # noqa: BLE001
        logger.warning("model_registry: upsert failed for %s/%s/%s: %s",
                       strategy, engine_mode, quantile, e)
        return None
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def register_quantile_trio_from_onnx_out(
    *,
    onnx_out: Dict[str, Any],
    strategy: str,
    engine_mode: str,
    schema_version: str,
    verdict: str,
    acceptance_report_path: Optional[str] = None,
    feature_schema_hash: Optional[str] = None,
    training_config_hash: Optional[str] = None,
    training_sample_size: Optional[int] = None,
    dsn: Optional[str] = None,
    created_by: str = "run_training_pipeline",
) -> List[int]:
    """Convenience wrapper — register q10 + q50 + q90 from
    `export_quantile_trio_to_onnx`'s return value. Mirrors the trio structure
    so run_training_pipeline only has to make one call.

    便利包裝：從 `export_quantile_trio_to_onnx` 的回傳批次登記 q10/q50/q90。
    run_training_pipeline 單次呼叫覆蓋 3 個 quantile。
    """
    artifacts = onnx_out.get("artifacts", {})
    train_date = onnx_out.get("train_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Load acceptance report JSON lazily from path (JSONB column stores full
    # verdict + metrics dict — Operator reads this when deciding to promote).
    # Lazy load 驗收報告 JSON（JSONB 欄位存完整 verdict+metrics，operator 晉升前讀）。
    acceptance_report: Optional[Dict[str, Any]] = None
    if acceptance_report_path and Path(acceptance_report_path).exists():
        try:
            acceptance_report = json.loads(Path(acceptance_report_path).read_text())
        except Exception as e:  # noqa: BLE001
            logger.warning("model_registry: acceptance_report read %s failed: %s",
                           acceptance_report_path, e)

    registered: List[int] = []
    for qname, entry in artifacts.items():
        if qname not in ("q10", "q50", "q90"):
            continue
        if not entry.get("written", False):
            logger.info("model_registry: %s artifact not written; skipping register", qname)
            continue
        artifact_path = entry.get("path", "")
        if not artifact_path:
            logger.warning("model_registry: %s entry has no path; skipping", qname)
            continue
        row_id = register_model(
            strategy=strategy,
            engine_mode=engine_mode,
            quantile=qname,
            schema_version=schema_version,
            train_date=train_date,
            artifact_path=artifact_path,
            verdict=verdict,
            acceptance_report=acceptance_report,
            feature_schema_hash=feature_schema_hash,
            training_config_hash=training_config_hash,
            training_sample_size=training_sample_size,
            dsn=dsn,
            created_by=created_by,
        )
        if row_id is not None:
            registered.append(row_id)
    return registered


def transition_canary_status(
    *,
    row_id: int,
    to_status: str,
    retirement_reason: Optional[str] = None,
    dsn: Optional[str] = None,
) -> bool:
    """Transition a registry row's canary_status.
    推進 canary_status 狀態機。

    Valid transitions (enforced by this function; DB only enforces enum values):
    - shadow     → promoting | rejected
    - promoting  → production | rejected
    - production → retired
    - retired    → (terminal)
    - rejected   → (terminal)

    Updates `promoted_at` when → production; updates `retired_at` +
    `retirement_reason` when → retired | rejected.

    合法轉移（此函式守；DB 僅守 enum 值）：
    shadow → promoting|rejected
    promoting → production|rejected
    production → retired
    retired/rejected → 終態。
    """
    if to_status not in CANARY_STATES:
        logger.warning("model_registry: invalid to_status %r", to_status)
        return False

    allowed_from: Dict[str, set] = {
        CANARY_PROMOTING: {CANARY_SHADOW},
        CANARY_PRODUCTION: {CANARY_PROMOTING},
        CANARY_RETIRED: {CANARY_PRODUCTION},
        CANARY_REJECTED: {CANARY_SHADOW, CANARY_PROMOTING},
    }
    conn = _connect(dsn)
    if conn is None:
        return False
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "SELECT canary_status FROM learning.model_registry WHERE id = %s",
                (row_id,),
            )
            row = cur.fetchone()
            if row is None:
                logger.warning("model_registry: id=%d not found", row_id)
                return False
            current = row[0]
            allowed = allowed_from.get(to_status, set())
            if current not in allowed:
                logger.warning(
                    "model_registry: invalid transition %s → %s for id=%d",
                    current, to_status, row_id,
                )
                return False

            # Build UPDATE with timestamp semantics per state.
            # 依狀態決定要刷新的 timestamp 欄。
            if to_status == CANARY_PRODUCTION:
                cur.execute(
                    """
                    UPDATE learning.model_registry
                    SET canary_status = %s, promoted_at = NOW()
                    WHERE id = %s
                    """,
                    (to_status, row_id),
                )
            elif to_status in (CANARY_RETIRED, CANARY_REJECTED):
                cur.execute(
                    """
                    UPDATE learning.model_registry
                    SET canary_status = %s, retired_at = NOW(),
                        retirement_reason = %s
                    WHERE id = %s
                    """,
                    (to_status, retirement_reason, row_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE learning.model_registry
                    SET canary_status = %s
                    WHERE id = %s
                    """,
                    (to_status, row_id),
                )
            logger.info(
                "model_registry: id=%d transitioned %s → %s",
                row_id, current, to_status,
            )
            return True
    except Exception as e:  # noqa: BLE001
        logger.warning("model_registry: transition id=%d failed: %s", row_id, e)
        return False
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
