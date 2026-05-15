from __future__ import annotations

"""
INFRA-PREBUILD-1 Part B — ML model registry routes.
INFRA-PREBUILD-1 B 部 — ML 模型 registry 路由。

GET  /api/v1/ml/model_registry     — list rows (filterable by strategy / engine_mode / canary_status)
GET  /api/v1/ml/model_info         — single-slot resolver: latest production or promoting row
POST /api/v1/ml/model_promote      — Operator-gate canary_status transition (shadow → promoting →
                                      production → retired | rejected)

Reads and writes are direct to PostgreSQL `learning.model_registry` (V023). This
module does not talk to Rust engine IPC — current Rust OnnxModelManager has no
live consumer of registry rows (Phase 3+ will wire it). Promote thus only
updates the DB; Rust will pick up the new row on next SIGHUP/restart (deferred).

Spec: docs/references/2026-04-23--model_canary_promotion_rules_draft.md
      sql/migrations/V023__model_registry.sql

Design notes:
- `model_promote` requires Operator role plus `ml:write` scope. Non-Operator
  or under-scoped actors get 403.
- Transition state machine enforced by calling
  `program_code.ml_training.model_registry.transition_canary_status` so the
  allowed-from matrix stays the single-source-of-truth (defined in Python
  module, mirrored in Rust tests).
- GET responses serialize acceptance_report as a nested object (JSONB) so
  operators can inspect metrics directly without a second call.
- All endpoints fail-soft on psycopg availability: if DB connect fails,
  return 503 rather than 500 — signals "infra issue, not a code bug".

2026-04-23 作者註：CLAUDE.md §九「Route Handler 只做 parse → call → format」，
此處 parse + DB query + format；業務邏輯（state machine）在 ml_training/model_registry.py。
"""

import logging
from datetime import datetime
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from . import main_legacy as base
from .governance_routes import _get_auth_actor
from .secret_runtime import get_secret_value

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ml", tags=["ml-registry"])


# ───── INFRA-PREBUILD-1 P3-1 (2026-04-23): ExitSource drift-guard constants ──
# Single-source-of-truth tuple mirroring Rust combine_layer.rs EXIT_SOURCE_TAGS.
# Any drift between:
#   - rust/openclaw_engine/src/combine_layer.rs: EXIT_SOURCE_TAGS
#   - sql/migrations/V021__fills_exit_source.sql: CHECK (exit_source IN ...)
#   - this tuple
# is caught by test_exit_source_tags_aligned_across_layers in
# program_code/ml_training/tests/test_model_registry.py.
#
# INFRA-PREBUILD-1 P3-1（2026-04-23）：ExitSource 漂移守常數。
# 與 Rust combine_layer.rs EXIT_SOURCE_TAGS + V021 migration CHECK 對齊；
# 任一漂移由 ml_training/tests/test_model_registry.py 的
# test_exit_source_tags_aligned_across_layers 測試擋紅。
VALID_EXIT_SOURCES: tuple[str, ...] = ("Physical", "Hybrid", "ML", "Disabled")

# Literal type for route / schema validation (optional; available to callers).
# Literal 型別供路由 / schema 驗證（下游可選採納）。
ExitSourceLiteral = Literal["Physical", "Hybrid", "ML", "Disabled"]


# ───── INFRA-PREBUILD-1 P3-2 (2026-04-23): Python ModelSlot ──────────
# Mirror of rust::ml::registry::ModelSlot. A slot = (strategy, engine_mode,
# quantile); registry rows are identified by this tuple + canary_status.
# Currently used only for Python-side test scaffolding + drift guard;
# model_info route keeps its 3-Query-param surface for backwards compat.
# Future refactor may switch model_info to use this via FastAPI Depends().
#
# INFRA-PREBUILD-1 P3-2（2026-04-23）：Python ModelSlot 對應 Rust
# ml::registry::ModelSlot。slot = (strategy, engine_mode, quantile)；registry
# 列以此 tuple + canary_status 識別。目前僅用於測試 scaffold 與漂移守；
# model_info route 保持 3 個 Query params 介面不動（向後相容）。未來可透過
# FastAPI Depends() 注入 ModelSlot 統一。


class ModelSlot(BaseModel):
    """INFRA-PREBUILD-1 P3-2: Python mirror of rust::ml::registry::ModelSlot.

    A slot = (strategy, engine_mode, quantile) uniquely identifies which
    production-or-promoting model the Rust engine should load for that
    strategy × engine_mode × quantile combination. Registry rows with
    matching (slot, canary_status) represent the active artifact.

    INFRA-PREBUILD-1 P3-2：Rust ModelSlot 的 Python 對應。slot 3 欄唯一識別一個
    strategy × engine_mode × quantile 組合對應的 production/promoting model。
    """

    strategy: str = Field(
        ...,
        min_length=1,
        description="Strategy name, e.g. 'ma_crossover'. Non-empty string.",
    )
    engine_mode: str = Field(
        ...,
        description="One of paper|demo|live|live_demo (same domain as V023 CHECK).",
    )
    quantile: str = Field(
        ...,
        description="One of q10|q50|q90 (same domain as V023 CHECK).",
    )

    @field_validator("engine_mode")
    @classmethod
    def _validate_engine_mode(cls, v: str) -> str:
        if v not in ("paper", "demo", "live", "live_demo"):
            raise ValueError(
                f"engine_mode must be one of paper|demo|live|live_demo, got {v!r}"
            )
        return v

    @field_validator("quantile")
    @classmethod
    def _validate_quantile(cls, v: str) -> str:
        if v not in ("q10", "q50", "q90"):
            raise ValueError(f"quantile must be one of q10|q50|q90, got {v!r}")
        return v


# ───── Pydantic models ───────────────────────────────────────────────


class PromoteRequest(BaseModel):
    """POST /model_promote body — Operator specifies target row + new status.
    POST /model_promote body — Operator 指定目標 row 與新狀態。"""

    row_id: int = Field(..., description="learning.model_registry.id")
    to_status: str = Field(
        ...,
        description="'promoting' | 'production' | 'retired' | 'rejected'",
    )
    retirement_reason: Optional[str] = Field(
        None,
        description="Required when to_status is 'retired' or 'rejected'; ignored otherwise",
    )
    confirm: bool = Field(
        False,
        description="Must be True for irreversible transitions (retired/rejected)",
    )


# ───── Helpers ───────────────────────────────────────────────────────


def _connect_pg():
    """Short-lived psycopg connection. 503 on failure."""
    try:
        import os

        import psycopg
    except ImportError as e:
        logger.warning("model_registry: psycopg import failed: %s", e)
        raise HTTPException(status_code=503, detail="model registry database unavailable")
    dsn = get_secret_value("OPENCLAW_DATABASE_URL")
    if not dsn:
        raise HTTPException(status_code=503, detail="model registry database unavailable")
    try:
        return psycopg.connect(dsn)
    except Exception as e:  # noqa: BLE001
        logger.warning("model_registry: PG connect failed: %s", e)
        raise HTTPException(status_code=503, detail="model registry database unavailable")


def _row_to_dict(cols: list[str], row: tuple) -> dict:
    """Zip column names with row tuple; JSON-serialize datetime/date."""
    out: dict[str, Any] = {}
    for col, val in zip(cols, row):
        if isinstance(val, (datetime,)):
            out[col] = val.isoformat()
        else:
            out[col] = val
    return out


def _require_ml_read(actor: base.AuthenticatedActor) -> None:
    """Shared Batch B gate for model registry observability.
    Batch B 共用模型 registry 讀取閘門：必須具 ml:read scope。
    """
    base.require_scope(actor, "ml:read")


# ───── GET /model_registry (list) ─────────────────────────────────────


@router.get("/model_registry")
async def list_registry(
    strategy: Optional[str] = Query(None, description="Exact match strategy name"),
    engine_mode: Optional[str] = Query(None, description="paper|demo|live|live_demo"),
    canary_status: Optional[str] = Query(
        None,
        description="shadow|promoting|production|retired|rejected (omit = all)",
    ),
    limit: int = Query(50, ge=1, le=500, description="Max rows (1..500)"),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict:
    """List learning.model_registry rows with optional filters.
    列出 learning.model_registry 列（可過濾）。

    Response: {"rows": [...], "count": N}. Each row includes identity +
    artifact + verdict + acceptance_report (JSONB) + canary metadata.

    Read-only but authenticated: model artifact paths/schema hashes are internal
    release metadata and require ml:read.
    只讀但需認證：模型 artifact path/schema hash 屬內部 release metadata。
    """
    _require_ml_read(actor)
    conn = _connect_pg()
    cols = [
        "id", "strategy", "engine_mode", "quantile", "schema_version",
        "train_date", "artifact_path", "artifact_size_bytes",
        "verdict", "canary_status", "promoted_at", "retired_at",
        "retirement_reason", "feature_schema_hash", "training_sample_size",
        "acceptance_report", "created_at", "updated_at",
    ]
    where_clauses: list[str] = []
    params: list[Any] = []
    if strategy:
        where_clauses.append(f"strategy = ${len(params) + 1}")
        params.append(strategy)
    if engine_mode:
        where_clauses.append(f"engine_mode = ${len(params) + 1}")
        params.append(engine_mode)
    if canary_status:
        where_clauses.append(f"canary_status = ${len(params) + 1}")
        params.append(canary_status)
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    sql = (
        f"SELECT {', '.join(cols)} "
        f"FROM learning.model_registry "
        f"{where_sql} "
        f"ORDER BY created_at DESC "
        f"LIMIT ${len(params) + 1}"
    )
    params.append(limit)
    # psycopg uses %s not $N placeholders — swap style.
    # psycopg 用 %s 而非 $N placeholder，這裡改寫。
    sql = sql.replace("$1", "%s").replace("$2", "%s").replace("$3", "%s").replace("$4", "%s")

    try:
        with conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return {
            "rows": [_row_to_dict(cols, r) for r in rows],
            "count": len(rows),
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("model_registry list failed: %s", e)
        raise HTTPException(status_code=500, detail="model registry query failed")
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


# ───── GET /model_info (single slot resolver) ────────────────────────


@router.get("/model_info")
async def model_info(
    strategy: str = Query(..., description="Strategy name (required)"),
    engine_mode: str = Query(..., description="paper|demo|live|live_demo (required)"),
    quantile: str = Query("q50", description="q10|q50|q90 (default q50)"),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict:
    """Resolve the latest production-or-promoting model for a slot.
    解析 slot 當前權威 model（production 或 promoting）。

    Mirrors the resolver logic in `rust/openclaw_engine/src/ml/registry.rs`
    (`resolve_latest_production_artifact`) so Python-side tools see the same
    row the Rust side would load on SIGHUP. Returns 404 when no matching row
    exists (operator should fall back to filesystem `_current` symlink).
    """
    _require_ml_read(actor)
    if quantile not in ("q10", "q50", "q90"):
        raise HTTPException(
            status_code=400,
            detail=f"quantile must be one of q10/q50/q90, got {quantile!r}",
        )
    if engine_mode not in ("paper", "demo", "live", "live_demo"):
        raise HTTPException(
            status_code=400,
            detail=f"engine_mode must be paper|demo|live|live_demo, got {engine_mode!r}",
        )
    conn = _connect_pg()
    sql = (
        "SELECT id, artifact_path, canary_status, verdict, "
        "       train_date, artifact_sha256, promoted_at, created_at, schema_version "
        "FROM learning.model_registry "
        "WHERE strategy = %s AND engine_mode = %s AND quantile = %s "
        "  AND canary_status IN ('production', 'promoting') "
        "ORDER BY "
        "  CASE canary_status WHEN 'production' THEN 0 ELSE 1 END ASC, "
        "  promoted_at DESC NULLS LAST, created_at DESC "
        "LIMIT 1"
    )
    try:
        with conn, conn.cursor() as cur:
            cur.execute(sql, (strategy, engine_mode, quantile))
            row = cur.fetchone()
            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"no production/promoting row for {strategy}/{engine_mode}/{quantile}",
                )
            (rid, path, status, verdict, train_date, sha256, promoted_at, created_at, schema_version) = row
            cur.execute(
                """
                SELECT quantile, id, artifact_path, artifact_sha256
                FROM learning.model_registry
                WHERE strategy = %s
                  AND engine_mode = %s
                  AND schema_version = %s
                  AND train_date = %s
                  AND canary_status = %s
                  AND quantile IN ('q10', 'q50', 'q90')
                """,
                (strategy, engine_mode, schema_version, train_date, status),
            )
            siblings = cur.fetchall()
        sibling_by_quantile = {r[0]: r for r in siblings}
        required = {"q10", "q50", "q90"}
        if set(sibling_by_quantile) != required:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"incomplete serving trio for {strategy}/{engine_mode}/"
                    f"{schema_version}/{train_date}: have={sorted(sibling_by_quantile)}"
                ),
            )
        return {
            "id": rid,
            "artifact_path": path,
            "canary_status": status,
            "verdict": verdict,
            "train_date": train_date.isoformat() if hasattr(train_date, "isoformat") else str(train_date),
            "artifact_sha256": sha256,
            "promoted_at": promoted_at.isoformat() if promoted_at else None,
            "created_at": created_at.isoformat() if created_at else None,
            "schema_version": schema_version,
            "serving_unit_quantiles": sorted(required),
            "serving_unit_status": status,
        }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.warning("model_info query failed: %s", e)
        raise HTTPException(status_code=500, detail="model registry query failed")
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


# ───── POST /model_promote (Operator + scope gate) ───────────────────


@router.post("/model_promote")
async def promote(
    body: PromoteRequest,
    actor: Any = Depends(_get_auth_actor),
) -> dict:
    """Transition a registry row's canary_status.
    推進 registry row 的 canary_status 狀態機。

    Validations:
    - Actor must be Operator role (403 otherwise — same as governance routes).
    - retired/rejected are **irreversible** (terminal states); require
      `confirm=True` in the body to prevent typo-triggered retirement.
    - State machine legality enforced by
      `program_code.ml_training.model_registry.transition_canary_status`
      (invalid from-state or unknown to_status returns 409 Conflict).
    """
    base.require_scope_and_operator(actor, "ml:write")

    to_status = body.to_status
    if to_status not in ("promoting", "production", "retired", "rejected"):
        raise HTTPException(
            status_code=400,
            detail=f"to_status must be promoting|production|retired|rejected, got {to_status!r}",
        )
    if to_status in ("retired", "rejected"):
        if not body.confirm:
            raise HTTPException(
                status_code=400,
                detail=(
                    "irreversible transition requires `confirm: true` in body "
                    "(guard against typos). 不可逆轉移需 confirm=true（防誤按）。"
                ),
            )
        if to_status == "retired" and not body.retirement_reason:
            raise HTTPException(
                status_code=400,
                detail="retirement_reason required when to_status=retired",
            )

    # Defer to the Python writer — same state machine that governs
    # register_quantile_trio_from_onnx_out so behaviour stays consistent.
    # 委派給 Python writer，同一狀態機避免分叉。
    try:
        from program_code.ml_training.model_registry import transition_canary_status  # noqa: PLC0415
    except ImportError as e:
        # WP-05 Real Fix
        from .error_sanitize import sanitize_exc_for_detail  # noqa: PLC0415
        raise HTTPException(
            status_code=503,
            detail=sanitize_exc_for_detail(e, "internal_error"),
        )

    ok = transition_canary_status(
        row_id=body.row_id,
        to_status=to_status,
        retirement_reason=body.retirement_reason,
    )
    if not ok:
        raise HTTPException(
            status_code=409,
            detail=(
                f"transition rejected: row_id={body.row_id} may not exist, "
                f"may already be in terminal state, or current status forbids "
                f"transition to {to_status!r}. Check GET /model_registry."
            ),
        )
    # Log for audit trail — Operator promotions are rare + high-signal.
    # Audit log — Operator 晉升罕見且訊號高。
    actor_ref = getattr(actor, "actor_id", getattr(actor, "role", "unknown"))
    logger.info(
        "model_promote: row=%d → %s by actor=%s reason=%r",
        body.row_id, to_status, actor_ref, body.retirement_reason,
    )
    return {
        "row_id": body.row_id,
        "to_status": to_status,
        "actor": str(actor_ref),
        "transitioned": True,
    }
