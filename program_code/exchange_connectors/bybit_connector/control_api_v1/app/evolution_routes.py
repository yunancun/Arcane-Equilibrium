from __future__ import annotations

"""
Evolution Routes — REST API endpoints for EvolutionEngine
進化路由 — EvolutionEngine 的 REST API 端點

MODULE_NOTE (中文):
  本模塊為 Phase 3 Batch 3B EvolutionEngine 提供 FastAPI 路由，供 GUI 和外部工具觸發
  策略參數自動優化搜索：
  1. POST /api/v1/evolution/run    — 執行策略參數進化搜索（需 Operator 角色）
  2. GET  /api/v1/evolution/status — 查詢 EvolutionEngine 狀態（只讀，無需 Operator 角色）

  安全不變量 / Safety invariants:
  - POST /run 需要 Operator 角色認證（write action gate）
  - EvolutionResult.is_simulated 始終為 True（__post_init__ 強制）
  - EvolutionEngine 內部強制 backtest_mode=True，誤用時拋出 ValueError
  - EvolutionEngine 異常 fail-closed → 500 "Internal server error"（不洩露異常細節）
  - TruthRegistry 注入失敗為 non-fatal（fail-open，記錄 warning 繼續返回結果）

  原則對應 / Principle alignment:
  - 原則 7: 進化平面與 Live 平面隔離（EvolutionEngine 只運行回測，無 live 模組 import）
  - 原則 8: 每次進化搜索可重建（EvolutionResult.to_dict() 包含完整配置與結果）
  - 原則 12: 高品質進化結果自動注入 TruthSourceRegistry（持續進化學習管線）

MODULE_NOTE (English):
  Provides FastAPI routes for Phase 3 Batch 3B EvolutionEngine, allowing GUI and external
  tools to trigger strategy parameter auto-optimization:
  1. POST /api/v1/evolution/run    — Execute strategy parameter evolution search (Operator role required)
  2. GET  /api/v1/evolution/status — Query EvolutionEngine status (read-only)

  Safety invariants:
  - POST /run requires Operator role authentication (write action gate)
  - EvolutionResult.is_simulated is always True (enforced by __post_init__)
  - EvolutionEngine internally enforces backtest_mode=True; misuse raises ValueError
  - EvolutionEngine exception → fail-closed 500 "Internal server error" (no detail leak)
  - TruthRegistry injection failure is non-fatal (fail-open, logs warning and continues)

  Principle alignment:
  - Principle 7: Evolution plane isolated from Live plane (EvolutionEngine only runs
    backtests, zero live module imports)
  - Principle 8: Each evolution run is reproducible (EvolutionResult.to_dict() has full config + results)
  - Principle 12: High-quality evolution results auto-inject TruthSourceRegistry
    (continuous evolution learning pipeline)
"""

import asyncio
import logging
import threading
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, validator

# ── sys.path 注入（統一由 _path_setup 模塊處理）──────────────────────────────────
# sys.path injection — centralized in _path_setup.py (APR01-MEDIUM-11 dedup)
from . import _path_setup  # noqa: F401  — ensures program_code/ is on sys.path

from local_model_tools.evolution_engine import EvolutionEngine, ParameterGrid  # noqa: E402

# ── 認證輔助函數（複用 governance_routes.py 的模式）──────────────────────────────
# Auth helpers reuse the same pattern as governance_routes.py for consistency.
# 複用 governance_routes.py 的 _get_auth_actor + _require_operator_role 模式。
from .governance_routes import _require_operator_role, _get_auth_actor  # noqa: E402

logger = logging.getLogger(__name__)

# ── 模組級單例 / Module-level singleton ──────────────────────────────────────────
# Singleton engine: initialized once at first request, reused across requests.
# 單例引擎：第一次請求時初始化，跨請求複用（雙重檢查鎖確保線程安全）。
_evolution_engine: Optional[Any] = None
_evolution_lock = threading.Lock()

# B13: Optional auto-deployer reference for applying evolution results.
# B13: 可選的自動部署器引用，用於應用進化結果到已部署策略。
# Set via set_auto_deployer() from startup or phase2_strategy_routes.
# 由啟動邏輯或 phase2_strategy_routes 通過 set_auto_deployer() 設置。
_auto_deployer: Optional[Any] = None


def set_auto_deployer(deployer: Any) -> None:
    """
    Inject the StrategyAutoDeployer reference for B13 auto-apply.
    注入 StrategyAutoDeployer 引用，供 B13 自動應用進化結果。
    """
    global _auto_deployer
    _auto_deployer = deployer
    logger.info("B13: auto_deployer injected into evolution_routes / 自動部署器已注入進化路由")


def get_evolution_engine() -> Any:
    """
    Return the module-level EvolutionEngine singleton, creating it if needed.
    返回模塊級 EvolutionEngine 單例，不存在時創建。

    Thread-safe via double-check locking pattern.
    雙重檢查鎖確保線程安全。
    """
    global _evolution_engine
    if _evolution_engine is None:
        with _evolution_lock:
            # Double-check: another thread may have initialized while we waited for the lock
            # 雙重檢查：等待鎖期間另一個線程可能已初始化
            if _evolution_engine is None:
                _evolution_engine = EvolutionEngine()
                logger.info("EvolutionEngine singleton initialized / EvolutionEngine 單例已初始化")
    return _evolution_engine


# ── 路由器 / Router ───────────────────────────────────────────────────────────────
router = APIRouter(prefix="/api/v1/evolution", tags=["evolution"])


# ── 請求模型 / Request Model ──────────────────────────────────────────────────────

class EvolutionRunRequest(BaseModel):
    """
    POST /api/v1/evolution/run 的請求體。
    Request body for POST /api/v1/evolution/run.

    Fields / 字段:
      strategy_name    — 策略名稱 / Strategy name
      symbol           — 交易對 / Trading pair (e.g. "BTCUSDT")
      timeframe        — K線時間框架 / Kline timeframe (e.g. "1h", "4h")
      parameter_grids  — 參數搜索網格列表 / Parameter search grids: list of {name, values}
      min_sharpe       — 注入 TruthRegistry 的最低 Sharpe / Min sharpe for registry injection (default 1.0)
      max_combinations — 最大組合數上限（默認 50）/ Max combinations cap (default 50)
    """
    strategy_name: str = Field(..., max_length=200)  # strategy identifier
    symbol: str = Field(..., max_length=40, pattern=r"^[A-Z0-9]{1,40}$")  # e.g. "BTCUSDT"
    timeframe: str = Field(default="1h", max_length=10)
    # list of {name: str, values: list} — validated in endpoint before ParameterGrid construction
    # 字典列表，{name: str, values: list}，在端點構造 ParameterGrid 前驗證格式
    parameter_grids: list
    min_sharpe: float = 1.0
    max_combinations: int = Field(default=50, le=200)  # cap at 200 to prevent combinatorial explosion

    @validator("parameter_grids", each_item=True)
    def _cap_values_list(cls, item: Any) -> Any:  # noqa: N805
        """Cap each parameter grid's values list at 50 items to bound search space.
        限制每個參數網格的 values 列表最多 50 項，防止搜索空間爆炸。"""
        if isinstance(item, dict) and isinstance(item.get("values"), list):
            if len(item["values"]) > 50:
                item["values"] = item["values"][:50]
        return item


# ── POST /api/v1/evolution/run ────────────────────────────────────────────────────

@router.post("/run")
async def run_evolution(
    body: EvolutionRunRequest,
    actor: Any = Depends(_get_auth_actor),
) -> dict:
    """
    執行策略參數進化搜索（需要 Operator 角色）。
    Run strategy parameter evolution search (Operator role required).

    Steps / 執行步驟:
    1. Validate Operator role / 驗證 Operator 角色（write action gate）
    2. Build ParameterGrid objects from request body / 從請求體構造 ParameterGrid 對象
    3. Run EvolutionEngine in thread pool (non-blocking) / 在線程池中執行進化搜索（非阻塞）
    4. Return EvolutionResult.to_dict() / 返回序列化結果字典

    Fail-closed guards / 失敗守衛:
    - Non-operator → 403 / 非 Operator → 403
    - Invalid parameter_grids format → 422 / 格式錯誤 → 422
    - EvolutionEngine exception → 500 "Internal server error" / 引擎異常 → 500（不洩露細節）

    Returns / 返回:
      dict with evolution results including best_params, best_sharpe, all_results,
      and is_simulated=True (Principle 7 isolation marker)
      包含 best_params、best_sharpe、all_results 及 is_simulated=True（原則 7 隔離標記）的字典
    """
    # Operator 角色守衛 — 寫入/搜索動作需要操作員權限
    # Operator role guard — write/search action requires operator permission
    _require_operator_role(actor)

    engine = get_evolution_engine()

    # 構造 ParameterGrid 對象，驗證格式 / Build ParameterGrid objects, validate format
    try:
        grids = [ParameterGrid(name=g["name"], values=g["values"]) for g in body.parameter_grids]
    except (KeyError, TypeError) as e:
        # 格式錯誤：缺少必填字段或類型不匹配 / Format error: missing required field or type mismatch
        raise HTTPException(status_code=422, detail="Invalid parameter_grids format") from e

    try:
        # 在線程池中執行進化搜索，避免阻塞異步事件循環
        # Run in thread pool to avoid blocking the async event loop
        result = await asyncio.to_thread(
            engine.run_evolution,
            strategy_name=body.strategy_name,
            symbol=body.symbol,
            timeframe=body.timeframe,
            parameter_grids=grids,
            min_sharpe_to_register=body.min_sharpe,
        )
    except Exception as exc:
        # fail-closed：引擎異常 → 500，不洩露 Python 異常細節（原則 3/8）
        # fail-closed: engine exception → 500; do not leak Python exception details (Principles 3/8)
        logger.exception(
            "EvolutionEngine.run_evolution raised: %s / 進化搜索發生意外異常",
            exc,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from exc

    logger.info(
        "Evolution complete: strategy=%s symbol=%s best_sharpe=%.2f / 進化搜索完成",
        body.strategy_name, body.symbol, result.best_sharpe,
    )

    # B13: Optionally apply evolution result to auto-deployer if sharpe > 1.0
    # B13: 若 Sharpe > 1.0 且配置了自動部署器，可選地將進化結果應用到自動部署器
    # Fail-open: deployer errors must not block the evolution result return.
    # fail-open：部署器異常不阻塞進化結果返回。
    result_dict = result.to_dict()
    if result.best_sharpe > 1.0 and _auto_deployer is not None:
        try:
            applied = _auto_deployer.apply_evolution_result(result_dict)
            result_dict["auto_deploy_applied"] = applied
            if applied:
                logger.info(
                    "B13: Evolution result auto-applied to deployer: strategy=%s sharpe=%.2f / "
                    "進化結果已自動應用到部署器",
                    body.strategy_name, result.best_sharpe,
                )
        except Exception as e:
            # fail-open: deployer error does not block evolution result
            # fail-open：部署器異常不阻塞進化結果返回
            logger.warning("B13: auto-deploy apply failed (fail-open): %s", e)
            result_dict["auto_deploy_applied"] = False

    return result_dict


# ── GET /api/v1/evolution/status ──────────────────────────────────────────────────

@router.get("/status")
async def get_evolution_status(
    actor: Any = Depends(_get_auth_actor),
) -> dict:
    """
    返回 EvolutionEngine 狀態（只讀，無需 Operator 角色）。
    Return EvolutionEngine status (read-only, no Operator role required).

    All authenticated actors can query evolution status for observability.
    所有已認證的 actor 均可查詢進化狀態（可觀察性需求）。

    Returns / 返回:
      dict with total_runs, last_run_ts, max_combinations
    """
    # 只讀端點：無需 Operator 角色，任何已認證 actor 均可查詢
    # Read-only endpoint: no Operator role required; all authenticated actors may query
    engine = get_evolution_engine()
    return await asyncio.to_thread(engine.get_status)
