"""
Governance Promotion Routes — Strategy promotion pipeline endpoints (6-01~03).
治理晉升路由 — 策略漸進放權管線端點（6-01~03）。

MODULE_NOTE (EN): Extracted from governance_routes.py (FIX-08 file size).
  Contains PromotionGate lazy singleton, and three promotion pipeline endpoints:
  GET /promotion-pipeline/status, POST /promote, POST /operator-decision.
MODULE_NOTE (中): 從 governance_routes.py 提取（FIX-08 文件大小）。
  包含 PromotionGate 延遲單例，以及三個晉升管線端點：
  GET /promotion-pipeline/status、POST /promote、POST /operator-decision。
"""

from __future__ import annotations

import html
import logging
import threading
from typing import Any

from fastapi import Depends, HTTPException

from .governance_routes import (
    GovernanceResponse,
    _get_auth_actor,
    _require_operator_role,
    governance_router,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# PromotionGate Singleton / PromotionGate 單例
# ═══════════════════════════════════════════════════════════════════════════════

_promotion_gate_lock = threading.Lock()


def _load_promotion_pipeline_rows_from_db() -> list[dict[str, Any]]:
    """Fail-soft DB restore for promotion pipeline rows."""
    try:
        from .db_pool import get_pg_conn
    except Exception:
        return []

    try:
        with get_pg_conn() as conn:
            if conn is None:
                return []
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('learning.promotion_pipeline') IS NOT NULL")
                exists = cur.fetchone()
                if not exists or not exists[0]:
                    return []
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'learning'
                      AND table_name = 'promotion_pipeline'
                    """
                )
                columns = {str(row[0]) for row in cur.fetchall()}
                optional_reports = [
                    col
                    for col in (
                        "demo_selection_bias_report",
                        "demo_tail_risk_report",
                    )
                    if col in columns
                ]
                base_columns = [
                    "pipeline_id",
                    "strategy_name",
                    "model_name",
                    "model_version",
                    "current_stage",
                    "paper_start_ts",
                    "paper_trades",
                    "paper_win_rate",
                    "paper_net_pnl_pct",
                    "paper_max_drawdown_pct",
                    "paper_sharpe",
                    "demo_start_ts",
                    "demo_trades",
                    "demo_win_rate",
                    "demo_net_pnl_pct",
                    "demo_max_drawdown_pct",
                    "demo_sharpe",
                    "demo_avg_slippage_bps",
                    "demo_api_reliability",
                    "evaluation_report",
                    "operator_decision",
                    "approved_capital_pct",
                    "approved_max_leverage",
                ]
                select_columns = [c for c in base_columns if c in columns] + optional_reports
                if not select_columns:
                    return []
                cur.execute(
                    "SELECT "
                    + ", ".join(select_columns)
                    + " FROM learning.promotion_pipeline ORDER BY updated_ts DESC"
                )
                rows = [dict(zip(select_columns, row)) for row in cur.fetchall()]
                return rows
    except Exception as exc:  # noqa: BLE001
        logger.warning("promotion pipeline DB restore failed (fail-soft): %s", exc)
        return []


def _sync_promotion_gate_from_db(gate: Any) -> None:
    rows = _load_promotion_pipeline_rows_from_db()
    if not rows:
        return
    try:
        gate.load_from_db_rows(rows)
    except Exception as exc:  # noqa: BLE001
        logger.warning("promotion gate DB row load failed (fail-soft): %s", exc)


def _get_promotion_gate():
    """
    Lazy import PromotionGate singleton (thread-safe) / 延遲導入 PromotionGate 單例（線程安全）。

    Created once per process; backed by DB via to_db_rows/load_from_db_rows.
    每個進程創建一次；通過 to_db_rows/load_from_db_rows 與 DB 同步。
    """
    try:
        from .promotion_pipeline import PromotionGate
        with _promotion_gate_lock:
            if not hasattr(_get_promotion_gate, "_instance"):
                _get_promotion_gate._instance = PromotionGate(
                    audit_callback=lambda r: logger.info(
                        "promotion_audit: %s", r.get("action", "unknown")
                    )
                )
                _sync_promotion_gate_from_db(_get_promotion_gate._instance)
        return _get_promotion_gate._instance
    except ImportError:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Promotion Pipeline Endpoints / 漸進放權管線端點
# ═══════════════════════════════════════════════════════════════════════════════

@governance_router.get("/promotion-pipeline/status")
def get_promotion_pipeline_status(
    strategy_name: str | None = None,
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    6-01: Get promotion pipeline status for all or a specific strategy.
    6-01：查詢所有或特定策略的漸進放權管線狀態。

    Query params:
      - strategy_name (optional): Filter to a specific strategy / 篩選特定策略
    """
    gate = _get_promotion_gate()
    if gate is None:
        raise HTTPException(status_code=503, detail="PromotionGate not available")
    _sync_promotion_gate_from_db(gate)

    try:
        if strategy_name:
            # Use raw name for internal lookup; html.escape only for log/response display
            entry = gate.get_entry(strategy_name)
            if entry is None:
                return GovernanceResponse.success(
                    data={"strategy_name": html.escape(strategy_name), "stage": "LEARNING", "registered": False},
                    message="promotion_pipeline_status"
                )
            rows = gate.to_db_rows()
            row = next((r for r in rows if r["strategy_name"] == strategy_name), None)
            return GovernanceResponse.success(
                data=row or {"strategy_name": html.escape(strategy_name), "stage": "LEARNING"},
                message="promotion_pipeline_status"
            )
        else:
            rows = gate.to_db_rows()
            return GovernanceResponse.success(
                data={"entries": rows, "count": len(rows)},
                message="promotion_pipeline_status"
            )
    except Exception as e:
        logger.error("Error getting promotion pipeline status: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.post("/promotion-pipeline/promote")
def promote_strategy(
    request: dict[str, Any],
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    6-02: Promote a strategy to the next stage (operator only).
    6-02：將策略晉升到下一階段（僅限 Operator）。

    Body: {strategy_name: str, target_stage: str, initiator: str (optional)}
    target_stage: PAPER_SHADOW | DEMO_ACTIVE | LIVE_PENDING | LIVE_ACTIVE
    """
    _require_operator_role(actor)

    gate = _get_promotion_gate()
    if gate is None:
        raise HTTPException(status_code=503, detail="PromotionGate not available")
    _sync_promotion_gate_from_db(gate)

    try:
        from .promotion_pipeline import PromotionStage

        strategy_name = str(request.get("strategy_name", "")).strip()
        target_stage_str = str(request.get("target_stage", "")).strip()
        initiator = str(request.get("initiator", "operator")).strip()

        if not strategy_name:
            raise HTTPException(status_code=400, detail="strategy_name is required")

        # Map string to PromotionStage enum / 將字串映射到 PromotionStage 枚舉
        stage_map = {s.name: s for s in PromotionStage}
        target_stage = stage_map.get(target_stage_str.upper())
        if target_stage is None:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid target_stage. Valid: {list(stage_map.keys())}"
            )

        # Auto-register if not yet registered / 若未註冊則自動註冊
        gate.register_strategy(strategy_name)

        # Check graduation gates before promotion / 晉升前檢查畢業門檻
        current_stage = gate.get_stage(strategy_name)
        gate_info: dict[str, Any] = {}

        if target_stage == PromotionStage.DEMO_ACTIVE and current_stage == PromotionStage.PAPER_SHADOW:
            eligible, reasons = gate.check_paper_graduation(strategy_name)
            gate_info = {"paper_graduation_eligible": eligible, "gate_failures": reasons}
            if not eligible:
                return GovernanceResponse.success(
                    data={"promoted": False, "reason": "paper_gates_not_met", **gate_info},
                    message="promotion_blocked"
                )

        if target_stage == PromotionStage.LIVE_PENDING and current_stage == PromotionStage.DEMO_ACTIVE:
            eligible, reasons = gate.check_demo_graduation(strategy_name)
            gate_info = {"demo_graduation_eligible": eligible, "gate_failures": reasons}
            if not eligible:
                return GovernanceResponse.success(
                    data={"promoted": False, "reason": "demo_gates_not_met", **gate_info},
                    message="promotion_blocked"
                )

        ok, msg = gate.promote(strategy_name, target_stage, initiator=initiator)

        return GovernanceResponse.success(
            data={"promoted": ok, "message": msg, "target_stage": target_stage.name, **gate_info},
            message="promotion_result"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error promoting strategy: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.post("/promotion-pipeline/operator-decision")
def set_promotion_operator_decision(
    request: dict[str, Any],
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    6-03: Set operator decision for LIVE_PENDING strategy (operator only).
    6-03：為 LIVE_PENDING 階段的策略設定 Operator 決策（僅限 Operator）。

    Body: {
        strategy_name: str,
        decision: "APPROVED" | "REJECTED" | "EXTEND",
        capital_pct: float (optional, for APPROVED),
        max_leverage: float (optional, for APPROVED),
        evaluation_report: dict (optional)
    }
    """
    _require_operator_role(actor)

    gate = _get_promotion_gate()
    if gate is None:
        raise HTTPException(status_code=503, detail="PromotionGate not available")
    _sync_promotion_gate_from_db(gate)

    try:
        strategy_name = str(request.get("strategy_name", "")).strip()
        decision = str(request.get("decision", "")).strip()
        capital_pct = request.get("capital_pct")
        max_leverage = request.get("max_leverage")
        evaluation_report = request.get("evaluation_report")

        if not strategy_name:
            raise HTTPException(status_code=400, detail="strategy_name is required")
        if not decision:
            raise HTTPException(status_code=400, detail="decision is required")

        # P2: Type-validate capital_pct/max_leverage / 類型驗證
        if capital_pct is not None:
            if not isinstance(capital_pct, (int, float)) or capital_pct < 0 or capital_pct > 100:
                raise HTTPException(status_code=400, detail="capital_pct must be 0-100")
        if max_leverage is not None:
            if not isinstance(max_leverage, (int, float)) or max_leverage < 0 or max_leverage > 100:
                raise HTTPException(status_code=400, detail="max_leverage must be 0-100")

        ok, msg = gate.set_operator_decision(
            strategy_name,
            decision.upper(),
            capital_pct=capital_pct,
            max_leverage=max_leverage,
            evaluation_report=evaluation_report,
        )

        return GovernanceResponse.success(
            data={"accepted": ok, "message": msg, "decision": decision.upper()},
            message="operator_decision_result"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error setting operator decision: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
