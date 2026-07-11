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

from program_code.ml_training.registry_serving_contract import (
    RegistryServingContractError,
    attach_registry_serving_contract,
)

logger = logging.getLogger(__name__)

# Item 7 (PIT lineage, V157)：新增 training_window_start / training_window_end /
#   pit_manifest_hash 三欄一起持久化，讓 PIT lineage 可在「不翻動 production
#   contract_bound_run」的前提下由 registry row 直接重建。三欄一律 append 在
#   既有欄之後，param tuple 位序不變（既有測試按位讀 params[2]/[8] 不受影響）。
_REGISTER_MODEL_SQL = """
                INSERT INTO learning.model_registry (
                    strategy, engine_mode, quantile, schema_version, train_date,
                    artifact_path, artifact_size_bytes, artifact_sha256,
                    acceptance_report, verdict,
                    feature_schema_hash, training_config_hash, training_sample_size,
                    created_by,
                    training_window_start, training_window_end, pit_manifest_hash
                ) VALUES (
                    %s, %s, %s, %s, %s::date,
                    %s, %s, %s,
                    %s::jsonb, %s,
                    %s, %s, %s,
                    %s,
                    %s, %s, %s
                )
                ON CONFLICT (strategy, engine_mode, quantile, schema_version, train_date)
                DO UPDATE SET
                    artifact_path         = EXCLUDED.artifact_path,
                    artifact_size_bytes   = EXCLUDED.artifact_size_bytes,
                    artifact_sha256       = EXCLUDED.artifact_sha256,
                    acceptance_report     = EXCLUDED.acceptance_report,
                    verdict               = EXCLUDED.verdict,
                    feature_schema_hash   = EXCLUDED.feature_schema_hash,
                    training_config_hash  = EXCLUDED.training_config_hash,
                    training_sample_size  = EXCLUDED.training_sample_size,
                    created_by            = EXCLUDED.created_by,
                    training_window_start = EXCLUDED.training_window_start,
                    training_window_end   = EXCLUDED.training_window_end,
                    pit_manifest_hash     = EXCLUDED.pit_manifest_hash,
                    updated_at            = NOW()
                WHERE learning.model_registry.canary_status NOT IN ('promoting', 'production')
                RETURNING id
                """

# Item 7 tolerance (V157 pending)：legacy INSERT，故意 **不含** 三個 PIT lineage 欄
#   （training_window_start / training_window_end / pit_manifest_hash）。當 prod PG
#   仍在 V150、V157 尚未 apply 時，full SQL 會因欄位不存在而整筆 register 失敗
#   （quantile 路徑更會升成 RegistryServingContractError）。此 legacy 版只綁 14 個
#   param，讓 register 在欄位缺席下仍成功；欄位到位後自動切回 full SQL。其餘語意
#   （ON CONFLICT DO UPDATE、canary_status NOT IN ('promoting','production') guard、
#   RETURNING id）與 full 版完全一致。
# Item 7 tolerance (EN): legacy INSERT WITHOUT the 3 PIT-lineage columns; used when
#   V157 has not been applied yet so `register_model` degrades gracefully instead of
#   hard-failing. Identical ON CONFLICT / canary guard / RETURNING semantics.
_LEGACY_REGISTER_MODEL_SQL = """
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
                    artifact_path         = EXCLUDED.artifact_path,
                    artifact_size_bytes   = EXCLUDED.artifact_size_bytes,
                    artifact_sha256       = EXCLUDED.artifact_sha256,
                    acceptance_report     = EXCLUDED.acceptance_report,
                    verdict               = EXCLUDED.verdict,
                    feature_schema_hash   = EXCLUDED.feature_schema_hash,
                    training_config_hash  = EXCLUDED.training_config_hash,
                    training_sample_size  = EXCLUDED.training_sample_size,
                    created_by            = EXCLUDED.created_by,
                    updated_at            = NOW()
                WHERE learning.model_registry.canary_status NOT IN ('promoting', 'production')
                RETURNING id
                """

# 一次性 schema 探測：查 information_schema 確認 lineage 欄是否已存在。
#   pit_manifest_hash 是 V157 三欄中最後 append 的一欄，存在即代表三欄齊備。
# One-time schema probe: pit_manifest_hash is the last of the three V157 columns,
#   so its presence implies the whole lineage trio is available.
_LINEAGE_PROBE_SQL = """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'learning'
                  AND table_name = 'model_registry'
                  AND column_name = 'pit_manifest_hash'
                LIMIT 1
                """

# 進程級快取：None=尚未探測；True=三欄存在（走 full SQL）；False=尚未存在（走
#   legacy SQL，V157 pending）。cron 是一次性進程，V157 對整段執行要嘛全 applied
#   要嘛全未 applied，故一次探測快取到進程結束即可；下一次 cron 進程 cache 歸零重探，
#   V157 apply 後自動切回 full。測試可將本 global 設回 None 重置。
# Process-scoped cache for the lineage-column probe (tests reset it to None).
_LINEAGE_COLUMNS_PRESENT: Optional[bool] = None

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

REQUIRED_QUANTILES: tuple[str, str, str] = ("q10", "q50", "q90")

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
    driver = None
    try:
        import psycopg  # type: ignore

        driver = psycopg
    except ImportError:
        try:
            import psycopg2  # type: ignore

            driver = psycopg2
        except ImportError:
            logger.info(
                "model_registry: psycopg/psycopg2 not installed; skipping DB write"
            )
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
        return driver.connect(conninfo)
    except Exception as e:  # noqa: BLE001 — any connect error → skip
        logger.warning("model_registry: connect failed: %s", e)
        return None


class RegistryPersistenceError(RuntimeError):
    """P1-14：live-readiness 工件要求注册持久化但 DB 不可用时抛出。

    为什么 fail-loud：should_ship / shadow_only + 完整 q10/q50/q90 三件套是
    canary_promoter 的晋升候选来源；DB 不可用时若静默 skip，registry 会悄悄
    陈旧（runtime 实测曾出现 0 条新行），训练却报成功 → 掩盖断链。
    no_ship / unknown verdict 不属于 required，不触发本错误。
    """


def check_db_connectivity(dsn: Optional[str] = None) -> bool:
    """轻量探测 registry DB 是否可连。

    为什么单独探测：register_model 的 None 返回混淆了三种原因
    （verdict 跳过 / slot 锁定 / DB 不可用）。caller 在存在 required 工件时
    先用本函数判定 DB 是否可达，可在不改 register_model 签名的前提下，
    把「DB 不可用」这一原因单独识别为 fail-loud。
    """
    conn = _connect(dsn)
    if conn is None:
        return False
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("model_registry: connectivity probe failed: %s", e)
        return False
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


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
    training_window_start: Any = None,
    training_window_end: Any = None,
    pit_manifest_hash: Optional[str] = None,
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
            return _register_model_row(
                cur,
                strategy=strategy,
                engine_mode=engine_mode,
                quantile=quantile,
                schema_version=schema_version,
                train_date=train_date,
                artifact_path=artifact_path,
                artifact_size_bytes=size,
                artifact_sha256=sha,
                report_jsonb=report_jsonb,
                verdict=verdict,
                feature_schema_hash=feature_schema_hash,
                training_config_hash=training_config_hash,
                training_sample_size=training_sample_size,
                created_by=created_by,
                training_window_start=training_window_start,
                training_window_end=training_window_end,
                pit_manifest_hash=pit_manifest_hash,
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("model_registry: upsert failed for %s/%s/%s: %s",
                       strategy, engine_mode, quantile, e)
        return None
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def has_required_persistence_artifact(*, onnx_out: Dict[str, Any], verdict: str) -> bool:
    """P1-14：判定本次 onnx_out 是否含「要求注册持久化」的工件。

    定义（live-readiness-bearing）：verdict ∈ {should_ship, shadow_only}
    且至少一个 q10/q50/q90 已写盘（entry["written"]==True 且 path 非空）。
    no_ship / unknown verdict → 非 required（合法跳过，不 fail-loud）。
    """
    if verdict not in (VERDICT_SHOULD_SHIP, VERDICT_SHADOW_ONLY):
        return False
    artifacts = onnx_out.get("artifacts", {}) or {}
    for qname, entry in artifacts.items():
        if qname not in ("q10", "q50", "q90"):
            continue
        if entry.get("written", False) and entry.get("path", ""):
            return True
    return False


def register_quantile_trio_from_onnx_out(
    *,
    onnx_out: Dict[str, Any],
    strategy: str,
    engine_mode: str,
    schema_version: str,
    verdict: str,
    acceptance_report_path: Optional[str] = None,
    registry_serving_contract: Optional[Dict[str, Any]] = None,
    feature_schema_hash: Optional[str] = None,
    training_config_hash: Optional[str] = None,
    training_sample_size: Optional[int] = None,
    dsn: Optional[str] = None,
    created_by: str = "run_training_pipeline",
    training_window_start: Any = None,
    training_window_end: Any = None,
    pit_manifest_hash: Optional[str] = None,
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

    # V157 tolerance note：production cron 以 contract_bound_run=False 執行 →
    #   registry_serving_contract 恆為 None → 走下方 per-quantile register_model 迴圈，
    #   而非 _register_serving_contract_trio_atomic。兩條路徑最終都經 _register_model_row，
    #   已對 lineage 欄缺席容忍（V157 pending 走 legacy SQL），故 serving-contract 路徑
    #   （僅 contract_bound_run=True 才進，prod 永不觸及）同樣容忍，不硬性要求三欄存在。
    if registry_serving_contract is not None:
        # registry_serving_contract 是 JSONB 內的 source-only advisory metadata。
        # 只有完整且唯一的 q10/q50/q90 written trio 可攜帶它；partial/q50-only
        # output 直接 fail closed，避免單 row 被誤讀為 serving-capable。
        acceptance_report = attach_registry_serving_contract(
            acceptance_report,
            registry_serving_contract,
        )
        if not _has_exact_written_quantile_trio(artifacts):
            logger.warning(
                "model_registry: registry_serving_contract provided but ONNX "
                "artifacts are not an exact written q10/q50/q90 trio; skipping DB write"
            )
            return []
        _verify_registry_serving_contract_artifact_hashes(
            registry_serving_contract,
            artifacts,
        )
        return _register_serving_contract_trio_atomic(
            artifacts=artifacts,
            train_date=train_date,
            strategy=strategy,
            engine_mode=engine_mode,
            schema_version=schema_version,
            verdict=verdict,
            acceptance_report=acceptance_report,
            feature_schema_hash=feature_schema_hash,
            training_config_hash=training_config_hash,
            training_sample_size=training_sample_size,
            dsn=dsn,
            created_by=created_by,
            training_window_start=training_window_start,
            training_window_end=training_window_end,
            pit_manifest_hash=pit_manifest_hash,
        )

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
            training_window_start=training_window_start,
            training_window_end=training_window_end,
            pit_manifest_hash=pit_manifest_hash,
        )
        if row_id is None and registry_serving_contract is not None:
            # 這裡仍不是單一 DB transaction；未來需把三筆 registry write
            # 收進同一連線事務。當前先 fail-loud，避免 caller 把半套持久化
            # 誤判成完整 serving contract 已註冊成功。
            raise RegistryServingContractError(
                f"registry_trio_persistence_incomplete:{qname}"
            )
        if row_id is not None:
            registered.append(row_id)
    return registered


def _lineage_columns_present(cur: Any) -> bool:
    """探測 `learning.model_registry` 是否已具備 V157 的三個 PIT lineage 欄。
    Probe whether the V157 PIT-lineage columns exist yet (cached process-wide).

    為何需要：V157 是 PENDING migration（prod 仍在 V150），若 register 無條件寫三欄，
    欄位缺席時整筆 INSERT 會失敗、quantile 路徑更會升成 RegistryServingContractError。
    先探測一次並快取，讓 register 路徑在欄位到位前走 legacy SQL、到位後走 full SQL。
    探測失敗（極少：多半代表連線已壞，屆時 INSERT 也會失敗）→ 保守回 legacy 且不快取，
    下次重探。
    """
    global _LINEAGE_COLUMNS_PRESENT
    if _LINEAGE_COLUMNS_PRESENT is not None:
        return _LINEAGE_COLUMNS_PRESENT
    try:
        cur.execute(_LINEAGE_PROBE_SQL)
        row = cur.fetchone()
    except Exception as e:  # noqa: BLE001 — 探測失敗保守走 legacy，不快取以便重探
        logger.warning(
            "model_registry: lineage 欄位探測失敗，暫走 legacy register 路徑: %s", e,
        )
        return False
    present = row is not None
    _LINEAGE_COLUMNS_PRESENT = present
    if not present:
        # 只在首次判定為缺席時 log 一行（快取後不再重複）。
        logger.info(
            "model_registry: PIT lineage 欄位尚未存在（V157 pending）；register 暫走 legacy 路徑"
        )
    return present


def _register_model_row(
    cur: Any,
    *,
    strategy: str,
    engine_mode: str,
    quantile: str,
    schema_version: str,
    train_date: str,
    artifact_path: str,
    artifact_size_bytes: Optional[int],
    artifact_sha256: Optional[str],
    report_jsonb: Optional[str],
    verdict: str,
    feature_schema_hash: Optional[str],
    training_config_hash: Optional[str],
    training_sample_size: Optional[int],
    created_by: str,
    training_window_start: Any = None,
    training_window_end: Any = None,
    pit_manifest_hash: Optional[str] = None,
) -> Optional[int]:
    # V157 已 apply → full SQL（17 param，含三個 lineage 欄）；未 apply → legacy SQL
    #   （14 param，丟掉三個 lineage 值）。兩條路徑其餘語意一致，故 register_model
    #   與 _register_serving_contract_trio_atomic 兩個上游都自動獲得容忍性。
    if _lineage_columns_present(cur):
        cur.execute(
            _REGISTER_MODEL_SQL,
            (
                strategy, engine_mode, quantile, schema_version, train_date,
                artifact_path, artifact_size_bytes, artifact_sha256,
                report_jsonb, verdict,
                feature_schema_hash, training_config_hash, training_sample_size,
                created_by,
                training_window_start, training_window_end, pit_manifest_hash,
            ),
        )
    else:
        cur.execute(
            _LEGACY_REGISTER_MODEL_SQL,
            (
                strategy, engine_mode, quantile, schema_version, train_date,
                artifact_path, artifact_size_bytes, artifact_sha256,
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


def _register_serving_contract_trio_atomic(
    *,
    artifacts: Dict[str, Any],
    train_date: str,
    strategy: str,
    engine_mode: str,
    schema_version: str,
    verdict: str,
    acceptance_report: Optional[Dict[str, Any]],
    feature_schema_hash: Optional[str],
    training_config_hash: Optional[str],
    training_sample_size: Optional[int],
    dsn: Optional[str],
    created_by: str,
    training_window_start: Any = None,
    training_window_end: Any = None,
    pit_manifest_hash: Optional[str] = None,
) -> List[int]:
    conn = _connect(dsn)
    if conn is None:
        raise RegistryServingContractError(
            "registry_trio_persistence_incomplete:db_unavailable"
        )

    report_jsonb = json.dumps(acceptance_report) if acceptance_report is not None else None
    registered: List[int] = []
    try:
        with conn:
            with conn.cursor() as cur:
                for qname in REQUIRED_QUANTILES:
                    entry = artifacts[qname]
                    artifact_path = str(entry.get("path", "")).strip()
                    size, sha = _file_size_and_sha256(artifact_path)
                    row_id = _register_model_row(
                        cur,
                        strategy=strategy,
                        engine_mode=engine_mode,
                        quantile=qname,
                        schema_version=schema_version,
                        train_date=train_date,
                        artifact_path=artifact_path,
                        artifact_size_bytes=size,
                        artifact_sha256=sha,
                        report_jsonb=report_jsonb,
                        verdict=verdict,
                        feature_schema_hash=feature_schema_hash,
                        training_config_hash=training_config_hash,
                        training_sample_size=training_sample_size,
                        created_by=created_by,
                        training_window_start=training_window_start,
                        training_window_end=training_window_end,
                        pit_manifest_hash=pit_manifest_hash,
                    )
                    if row_id is None:
                        raise RegistryServingContractError(
                            f"registry_trio_persistence_incomplete:{qname}"
                        )
                    registered.append(row_id)
    except RegistryServingContractError:
        raise
    except Exception as e:  # noqa: BLE001
        raise RegistryServingContractError(
            f"registry_trio_persistence_failed:{type(e).__name__}"
        ) from e
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    return registered


def _has_exact_written_quantile_trio(artifacts: Any) -> bool:
    if not isinstance(artifacts, dict):
        return False
    if tuple(artifacts.keys()) != REQUIRED_QUANTILES:
        return False
    for qname in REQUIRED_QUANTILES:
        entry = artifacts.get(qname)
        if not isinstance(entry, dict):
            return False
        if not entry.get("written", False):
            return False
    return True


def _verify_registry_serving_contract_artifact_hashes(
    contract: Dict[str, Any],
    artifacts: Any,
) -> None:
    contract_hashes = contract.get("artifact_hashes")
    if not isinstance(contract_hashes, dict):
        raise RegistryServingContractError(
            "invalid registry serving contract: artifact_hashes_missing"
        )
    for qname in REQUIRED_QUANTILES:
        artifact_path = str(artifacts[qname].get("path", "")).strip()
        if not artifact_path:
            raise RegistryServingContractError(
                f"invalid registry serving contract: artifact_path_missing:{qname}"
            )
        _size, actual_sha = _file_size_and_sha256(artifact_path)
        if not actual_sha:
            raise RegistryServingContractError(
                f"invalid registry serving contract: artifact_sha_unavailable:{qname}"
            )
        expected_sha = _strip_sha256_prefix(str(contract_hashes.get(qname, "")).strip())
        if expected_sha != actual_sha:
            raise RegistryServingContractError(
                f"invalid registry serving contract: artifact_hash_mismatch:{qname}"
            )


def _strip_sha256_prefix(value: str) -> str:
    if value.startswith("sha256:"):
        return value[len("sha256:") :]
    return value


def transition_canary_status(
    *,
    row_id: int,
    to_status: str,
    retirement_reason: Optional[str] = None,
    dsn: Optional[str] = None,
) -> bool:
    """Transition a registry row's canary_status as an atomic quantile trio.
    推進 canary_status 狀態機。

    Valid transitions (enforced by this function; DB only enforces enum values):
    - shadow     → promoting | rejected
    - promoting  → production | rejected
    - production → retired
    - retired    → (terminal)
    - rejected   → (terminal)

    The input row identifies a serving unit by
    (strategy, engine_mode, schema_version, train_date). All q10/q50/q90
    rows in that unit must exist and all must currently satisfy the same
    allowed-from status; the UPDATE then changes all three rows in one DB
    transaction. This prevents q50-only promotion with stale q10/q90 siblings.

    Updates `promoted_at` when → production; updates `retired_at` +
    `retirement_reason` when → retired | rejected.

    合法轉移（此函式守；DB 僅守 enum 值），且以 q10/q50/q90 三檔為原子單元：
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
                """
                SELECT strategy, engine_mode, schema_version, train_date, canary_status
                FROM learning.model_registry
                WHERE id = %s
                """,
                (row_id,),
            )
            row = cur.fetchone()
            if row is None:
                logger.warning("model_registry: id=%d not found", row_id)
                return False
            strategy, engine_mode, schema_version, train_date, current = row
            allowed = allowed_from.get(to_status, set())
            if current not in allowed:
                logger.warning(
                    "model_registry: invalid transition %s → %s for id=%d",
                    current, to_status, row_id,
                )
                return False

            cur.execute(
                """
                SELECT id, quantile, canary_status
                FROM learning.model_registry
                WHERE strategy = %s
                  AND engine_mode = %s
                  AND schema_version = %s
                  AND train_date = %s
                  AND quantile IN ('q10', 'q50', 'q90')
                """,
                (strategy, engine_mode, schema_version, train_date),
            )
            trio_rows = cur.fetchall()
            trio = {q: (int(rid), status) for rid, q, status in trio_rows}
            missing = [q for q in REQUIRED_QUANTILES if q not in trio]
            if missing:
                logger.warning(
                    "model_registry: refusing %s for incomplete trio %s/%s/%s/%s; missing=%s",
                    to_status, strategy, engine_mode, schema_version, train_date, missing,
                )
                return False
            invalid = [
                (q, status)
                for q, (_rid, status) in trio.items()
                if status not in allowed
            ]
            if invalid:
                logger.warning(
                    "model_registry: refusing %s for trio with invalid source statuses=%s",
                    to_status, invalid,
                )
                return False
            trio_ids = [trio[q][0] for q in REQUIRED_QUANTILES]

            # Build UPDATE with timestamp semantics per state.
            # 依狀態決定要刷新的 timestamp 欄。
            if to_status == CANARY_PRODUCTION:
                cur.execute(
                    """
                    UPDATE learning.model_registry
                    SET canary_status = %s, promoted_at = NOW()
                    WHERE id IN (%s, %s, %s)
                    """,
                    (to_status, *trio_ids),
                )
            elif to_status in (CANARY_RETIRED, CANARY_REJECTED):
                cur.execute(
                    """
                    UPDATE learning.model_registry
                    SET canary_status = %s, retired_at = NOW(),
                        retirement_reason = %s
                    WHERE id IN (%s, %s, %s)
                    """,
                    (to_status, retirement_reason, *trio_ids),
                )
            else:
                cur.execute(
                    """
                    UPDATE learning.model_registry
                    SET canary_status = %s
                    WHERE id IN (%s, %s, %s)
                    """,
                    (to_status, *trio_ids),
                )
            logger.info(
                "model_registry: trio ids=%s transitioned %s → %s",
                trio_ids, current, to_status,
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
