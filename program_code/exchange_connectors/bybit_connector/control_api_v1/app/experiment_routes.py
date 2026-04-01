from __future__ import annotations

"""
Experiment Routes — REST API endpoints for ExperimentLedger (Phase 3 Batch 3A)
實驗路由 — ExperimentLedger 的 REST API 端點（Phase 3 Batch 3A）

MODULE_NOTE (中文):
  本模塊為 Phase 3 Batch 3A 的假設驗證管線提供 FastAPI 路由。
  系統可通過以下端點管理實驗假設的完整生命週期：
  1. POST /api/v1/experiments/propose          — 提出新假設（需 Operator 角色）
  2. POST /api/v1/experiments/{id}/observe     — 記錄觀測結果（需 Operator 角色）
  3. GET  /api/v1/experiments/{id}             — 查詢假設詳情（已認證即可）
  4. GET  /api/v1/experiments/status           — 查詢總帳狀態（已認證即可）

  安全不變量 / Safety invariants:
  - 寫入操作（propose / observe）需要 Operator 角色
  - 查詢操作對所有已認證 actor 開放（可觀察性需求）
  - 未知 hypothesis_id → 404，fail-closed，不暴露內部細節
  - ExperimentLedger 以模組級單例運行，雙重檢查鎖確保線程安全

  原則對應 / Principle alignment:
  - 原則 7: 實驗平面與 Live 平面隔離（ExperimentLedger 不導入任何 live 模塊）
  - 原則 10: 認知誠實（假設明確區分 PENDING / CONFIRMED / REFUTED 狀態）
  - 原則 12: 持續進化（確認假設後可注入 TruthSourceRegistry 學習管線）
  - 原則 15: 多 Agent 協作（假設可由 StrategistAgent / AnalystAgent 查詢利用）

MODULE_NOTE (English):
  Provides FastAPI routes for Phase 3 Batch 3A hypothesis validation pipeline.
  Manages the complete lifecycle of experiment hypotheses:
  1. POST /api/v1/experiments/propose          — Propose new hypothesis (Operator role required)
  2. POST /api/v1/experiments/{id}/observe     — Record observation (Operator role required)
  3. GET  /api/v1/experiments/{id}             — Get hypothesis details (auth only)
  4. GET  /api/v1/experiments/status           — Get ledger stats (auth only)

  Safety invariants:
  - Write actions (propose / observe) require Operator role
  - Read actions open to all authenticated actors (observability)
  - Unknown hypothesis_id → 404 fail-closed, no internal details exposed
  - ExperimentLedger runs as module-level singleton, thread-safe via double-check lock

  Principle alignment:
  - Principle 7: Experiment plane isolated from Live plane (no live module imports)
  - Principle 10: Cognitive honesty (hypotheses explicitly tagged PENDING/CONFIRMED/REFUTED)
  - Principle 12: Continuous evolution (confirmed hypotheses injected into TruthSourceRegistry)
  - Principle 15: Multi-agent collaboration (hypotheses queryable by StrategistAgent / AnalystAgent)
"""

import asyncio
import logging
import threading
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

# ── sys.path 注入（統一由 _path_setup 模塊處理）──────────────────────────────────
# sys.path injection — centralized in _path_setup.py (APR01-MEDIUM-11 dedup)
from . import _path_setup  # noqa: F401  — ensures program_code/ is on sys.path

# ── Auth helpers (from governance_routes — same pattern as backtest_routes.py) ──
# 認證輔助函數，複用 governance_routes.py 的模式（_get_auth_actor + _require_operator_role）
from .governance_routes import _require_operator_role, _get_auth_actor  # noqa: E402

logger = logging.getLogger(__name__)

# ── 模組級單例 / Module-level singleton ──────────────────────────────────────────
# Singleton ledger: initialized lazily on first request, reused across all requests.
# 單例帳本：首次請求時懶加載，跨請求複用。
# Double-check locking prevents concurrent initialization race conditions.
# 雙重檢查鎖防止並發初始化競態問題。
_ledger: Optional[Any] = None
_ledger_lock = threading.Lock()


def get_experiment_ledger() -> Any:
    """
    Return the module-level ExperimentLedger singleton, creating it if needed.
    返回模塊級 ExperimentLedger 單例，不存在時創建。

    Thread-safe via double-check locking pattern.
    雙重檢查鎖確保線程安全：第一次無鎖檢查快速路徑，第二次有鎖檢查防並發。
    """
    global _ledger
    # Fast path: no lock needed if already initialized
    # 快速路徑：已初始化則無需加鎖
    if _ledger is None:
        with _ledger_lock:
            # Double-check: another thread may have initialized while we waited for lock
            # 雙重檢查：等待鎖期間另一個線程可能已完成初始化
            if _ledger is None:
                from .experiment_ledger import ExperimentLedger  # noqa: PLC0415
                _ledger = ExperimentLedger()

                # Restore persisted state from snapshot (fail-open: missing/corrupt file → start fresh)
                # 从快照恢复持久化状态（fail-open：文件缺失/损坏 → 从空白开始）
                try:
                    snapshot_path = _ledger._resolve_snapshot_path()
                    loaded = _ledger.load_snapshot(snapshot_path)
                    if loaded > 0:
                        logger.info(
                            "ExperimentLedger: restored %d hypotheses from snapshot / "
                            "从快照恢复了 %d 条假设",
                            loaded, loaded,
                        )
                except Exception as exc:
                    # fail-open: snapshot load failure must not prevent ledger from starting
                    # fail-open：快照加载失败不得阻止账本启动
                    logger.warning(
                        "ExperimentLedger: snapshot load failed (fail-open, starting fresh): %s / "
                        "快照加载失败（fail-open，从空白开始）：%s",
                        exc, exc,
                    )

                logger.info(
                    "ExperimentLedger singleton initialized / ExperimentLedger 單例已初始化"
                )
    return _ledger


# ── 路由器 / Router ───────────────────────────────────────────────────────────────
router = APIRouter(prefix="/api/v1/experiments", tags=["experiments"])


# ── 請求模型 / Request Models ─────────────────────────────────────────────────────

class ProposeHypothesisRequest(BaseModel):
    """
    Request body for POST /api/v1/experiments/propose.
    POST /api/v1/experiments/propose 的請求體。

    Fields / 字段:
      description      — human-readable hypothesis description / 可讀假設描述（max 2000 chars）
      strategy_name    — strategy this hypothesis applies to / 所屬策略名稱（max 200 chars）
      regime           — market regime: "all", "trending", "ranging", etc. / 市場 Regime（max 100 chars）
      min_observations — minimum observations before verdict / 最少觀測次數後才判定
      ttl_days         — optional time-to-live in days (None = no expiry) / 可選有效期（天）

    max_length 約束防止超長字符串濫用（DoS / 存儲膨脹）。
    max_length constraints prevent oversized string abuse (DoS / storage bloat).
    """
    description: str = Field(..., max_length=2000)
    strategy_name: str = Field(..., max_length=200)
    regime: str = Field(default="all", max_length=100)
    min_observations: int = 20
    ttl_days: Optional[int] = None


class RecordObservationRequest(BaseModel):
    """
    Request body for POST /api/v1/experiments/{hypothesis_id}/observe.
    POST /api/v1/experiments/{hypothesis_id}/observe 的請求體。

    Fields / 字段:
      outcome — "supporting" (evidence supports hypothesis) or "refuting" (evidence against)
                "supporting"（證據支持假設）或 "refuting"（證據反對假設）

    max_length 約束防止超長字符串濫用。
    max_length constraint prevents oversized string abuse.
    """
    outcome: Literal["supporting", "refuting", "neutral"] = Field(...)  # constrained to valid observation outcomes


# ── POST /api/v1/experiments/propose ─────────────────────────────────────────────

@router.post("/propose")
async def propose_hypothesis(
    body: ProposeHypothesisRequest,
    actor: Any = Depends(_get_auth_actor),
) -> dict:
    """
    Propose a new experiment hypothesis.
    提出新的實驗假設。

    Requires Operator role — write action that creates a new hypothesis record.
    需要 Operator 角色 — 寫入操作，創建新假設記錄。

    Steps / 執行步驟:
    1. Validate Operator role / 驗證 Operator 角色
    2. Call ledger.propose_hypothesis() in thread pool (non-blocking) / 在線程池中執行（非阻塞）
    3. Return hypothesis_id + initial status / 返回假設 ID 及初始狀態

    Returns / 返回:
      {"hypothesis_id": str, "status": "PENDING"}
    """
    # 寫入操作：需要 Operator 角色 / Write action: Operator role required
    _require_operator_role(actor)

    ledger = get_experiment_ledger()

    try:
        # Run in thread pool to avoid blocking the async event loop
        # 在線程池中執行，避免阻塞異步事件循環（ExperimentLedger 可能有同步 I/O）
        hypothesis_id = await asyncio.to_thread(
            ledger.propose_hypothesis,
            description=body.description,
            strategy_name=body.strategy_name,
            regime=body.regime,
            proposed_by="operator",
            min_observations=body.min_observations,
            ttl_days=body.ttl_days,
        )
    except Exception as exc:
        logger.exception(
            "ExperimentLedger.propose_hypothesis raised unexpected exception: %s / "
            "propose_hypothesis 發生意外異常",
            exc,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from exc

    logger.info(
        "Hypothesis proposed: id=%s strategy=%s regime=%s / 假設已提出",
        hypothesis_id, body.strategy_name, body.regime,
    )
    return {"hypothesis_id": hypothesis_id, "status": "PENDING"}


# ── POST /api/v1/experiments/{hypothesis_id}/observe ─────────────────────────────

@router.post("/{hypothesis_id}/observe")
async def record_observation(
    hypothesis_id: str,
    body: RecordObservationRequest,
    actor: Any = Depends(_get_auth_actor),
) -> dict:
    """
    Record a supporting or refuting observation for a hypothesis.
    為假設記錄支持或反駁的觀測結果。

    Requires Operator role — write action that mutates hypothesis state.
    需要 Operator 角色 — 寫入操作，會改變假設狀態。

    Steps / 執行步驟:
    1. Validate Operator role / 驗證 Operator 角色
    2. Look up hypothesis — 404 if not found / 查找假設，未找到返回 404
    3. Record observation in thread pool / 在線程池中記錄觀測
    4. Return updated status / 返回更新後的狀態

    Returns / 返回:
      {"hypothesis_id": str, "status": str}
    """
    # 寫入操作：需要 Operator 角色 / Write action: Operator role required
    _require_operator_role(actor)

    ledger = get_experiment_ledger()

    # Pre-flight: verify hypothesis exists before recording observation
    # 前置檢查：在記錄觀測前確認假設存在
    hypothesis = await asyncio.to_thread(ledger.get_hypothesis, hypothesis_id)
    # fail-closed：未知假設 ID → 404，不暴露內部細節 / fail-closed: unknown hypothesis_id → 404
    if hypothesis is None:
        raise HTTPException(status_code=404, detail="Hypothesis not found")

    try:
        # Run in thread pool to avoid blocking the async event loop
        # 在線程池中執行，避免阻塞異步事件循環
        status = await asyncio.to_thread(
            ledger.record_observation,
            hypothesis_id,
            body.outcome,
        )
    except Exception as exc:
        logger.exception(
            "ExperimentLedger.record_observation raised unexpected exception "
            "for hypothesis_id=%s: %s / record_observation 發生意外異常",
            hypothesis_id, exc,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from exc

    # Handle both enum (HypothesisStatus) and plain string status values
    # 兼容枚舉（HypothesisStatus）和純字符串兩種狀態值形式
    status_str = status.value if hasattr(status, "value") else str(status)

    logger.info(
        "Observation recorded: hypothesis_id=%s outcome=%s new_status=%s / 觀測已記錄",
        hypothesis_id, body.outcome, status_str,
    )
    return {"hypothesis_id": hypothesis_id, "status": status_str}


# ── GET /api/v1/experiments/status ───────────────────────────────────────────────
# IMPORTANT: /status must be registered BEFORE /{hypothesis_id} to prevent FastAPI
# from treating the literal string "status" as a hypothesis_id path parameter.
# 重要：/status 必須在 /{hypothesis_id} 之前注冊，否則 FastAPI 會將字面量 "status"
# 當作 hypothesis_id 路徑參數處理，導致 /status 永遠被路由到 get_hypothesis()。

@router.get("/status")
async def get_ledger_status(
    actor: Any = Depends(_get_auth_actor),
) -> dict:
    """
    Return ExperimentLedger aggregate statistics (read-only).
    返回 ExperimentLedger 聚合統計信息（只讀）。

    All authenticated actors can query ledger status for observability.
    所有已認證的 actor 均可查詢帳本狀態（可觀察性需求）。

    Returns / 返回:
      dict with total / pending / confirmed / refuted counts and other stats
      包含 total / pending / confirmed / refuted 計數及其他統計信息的字典
    """
    # No Operator role required — read-only endpoint for observability
    # 無需 Operator 角色 — 只讀端點，供可觀察性查詢

    ledger = get_experiment_ledger()

    # Run in thread pool to avoid blocking the async event loop
    # 在線程池中執行，避免阻塞異步事件循環
    return await asyncio.to_thread(ledger.get_stats)


# ── GET /api/v1/experiments/{hypothesis_id} ───────────────────────────────────────

@router.get("/{hypothesis_id}")
async def get_hypothesis(
    hypothesis_id: str,
    actor: Any = Depends(_get_auth_actor),
) -> dict:
    """
    Get detailed information about a specific hypothesis.
    查詢特定假設的詳細信息。

    Read-only — any authenticated actor can query hypothesis details.
    只讀操作 — 所有已認證 actor 均可查詢假設詳情（可觀察性需求）。

    Returns / 返回:
      hypothesis.to_dict() — full hypothesis record including status / confidence / observations
      完整假設記錄，含狀態 / 信度 / 觀測記錄
    """
    # No Operator role required — read-only endpoint for observability
    # 無需 Operator 角色 — 只讀端點，供可觀察性查詢

    ledger = get_experiment_ledger()

    # Run in thread pool to avoid blocking the async event loop
    # 在線程池中執行，避免阻塞異步事件循環
    hypothesis = await asyncio.to_thread(ledger.get_hypothesis, hypothesis_id)

    # fail-closed：未知假設 ID → 404，不暴露內部細節 / fail-closed: unknown hypothesis_id → 404
    if hypothesis is None:
        raise HTTPException(status_code=404, detail="Hypothesis not found")

    return hypothesis.to_dict()
