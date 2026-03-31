from __future__ import annotations

"""
Backtest Routes — REST API endpoints for BacktestEngine
回測路由 — BacktestEngine 的 REST API 端點

MODULE_NOTE (中文):
  本模塊為 Phase 2 BacktestEngine 提供 FastAPI 路由，供 GUI 和外部工具觸發策略回測：
  1. POST /api/v1/backtest/run   — 執行單次策略回測（需 Operator 角色）
  2. GET  /api/v1/backtest/status — 查詢最近一次回測狀態（只讀，無需 Operator 角色）

  安全不變量 / Safety invariants:
  - backtest_mode 強制為 True，防止回測配置誤用於實盤（BacktestEngine 內部強制）
  - POST /run 需要 Operator 角色認證（write action gate）
  - BacktestResult.sharpe_ratio > 1.0 且 total_trades >= 10 時自動注入 TruthSourceRegistry
  - TruthRegistry 注入失敗為 non-fatal（fail-open，記錄 warning 繼續返回結果）

  原則對應 / Principle alignment:
  - 原則 7: 回測平面與 Live 平面隔離（backtest_mode=True 強制，is_simulated 標記）
  - 原則 8: 每次回測可重建（BacktestResult.to_dict() 包含完整配置與結果）
  - 原則 12: 回測結果自動注入 TruthSourceRegistry（持續進化學習管線）

MODULE_NOTE (English):
  Provides FastAPI routes for Phase 2 BacktestEngine, allowing GUI and external tools
  to trigger strategy backtests:
  1. POST /api/v1/backtest/run   — Execute a single strategy backtest (Operator role required)
  2. GET  /api/v1/backtest/status — Query most recent backtest status (read-only)

  Safety invariants:
  - backtest_mode is forced True to prevent misuse in live trading (enforced by BacktestEngine)
  - POST /run requires Operator role authentication (write action gate)
  - When BacktestResult.sharpe_ratio > 1.0 and total_trades >= 10, auto-inject TruthSourceRegistry
  - TruthRegistry injection failure is non-fatal (fail-open, logs warning and continues)

  Principle alignment:
  - Principle 7: Backtest plane isolated from Live plane (backtest_mode=True enforced)
  - Principle 8: Each backtest is reproducible (BacktestResult.to_dict() has full config + results)
  - Principle 12: Backtest results auto-inject TruthSourceRegistry (continuous evolution pipeline)
"""

import asyncio
import logging
import os
import sys
import threading
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

# ── sys.path 注入（複用 phase2_strategy_routes.py 的 5 級目錄上溯模式）──────────
# sys.path injection — 5-level traversal to reach program_code/ root
# Matches the pattern in phase2_strategy_routes.py to ensure consistent import paths.
# 與 phase2_strategy_routes.py 保持一致，確保 import 路徑穩定。
_app_dir = os.path.dirname(os.path.abspath(__file__))          # app/
_control_api_dir = os.path.dirname(_app_dir)                    # control_api_v1/
_bybit_connector_dir = os.path.dirname(_control_api_dir)        # bybit_connector/
_exchange_connectors_dir = os.path.dirname(_bybit_connector_dir)  # exchange_connectors/
_program_code_dir = os.path.dirname(_exchange_connectors_dir)   # program_code/
if _program_code_dir not in sys.path:
    sys.path.insert(0, _program_code_dir)

from local_model_tools.backtest_engine import BacktestEngine, BacktestConfig

# ── Auth helpers (from main_legacy via governance_routes pattern) ─────────────
# 認證輔助函數，複用 governance_routes.py 的模式（_get_auth_actor + _require_operator_role）
# Auth helpers reuse the same pattern as governance_routes.py to stay consistent.
from . import main_legacy as base  # current_actor dependency
from .governance_routes import _require_operator_role, _get_auth_actor

logger = logging.getLogger(__name__)

# ── 模組級單例 / Module-level singleton ─────────────────────────────────────────
# Singleton engine: initialized once at import time, reused across requests.
# 單例引擎：模塊導入時初始化一次，跨請求複用。
_backtest_engine: Optional[BacktestEngine] = None
_backtest_lock = threading.Lock()


def get_backtest_engine() -> BacktestEngine:
    """
    Return the module-level BacktestEngine singleton, creating it if needed.
    返回模塊級 BacktestEngine 單例，不存在時創建。

    Thread-safe via double-check locking pattern.
    雙重檢查鎖確保線程安全。
    """
    global _backtest_engine
    if _backtest_engine is None:
        with _backtest_lock:
            # Double-check: another thread may have initialized while waiting
            # 雙重檢查：等待鎖期間另一個線程可能已初始化
            if _backtest_engine is None:
                _backtest_engine = BacktestEngine()
                logger.info("BacktestEngine singleton initialized / BacktestEngine 單例已初始化")
    return _backtest_engine


# ── 路由器 / Router ──────────────────────────────────────────────────────────────
router = APIRouter(prefix="/api/v1/backtest", tags=["backtest"])


# ── 請求模型 / Request Model ─────────────────────────────────────────────────────

class BacktestRunRequest(BaseModel):
    """
    Request body for POST /api/v1/backtest/run.
    POST /api/v1/backtest/run 的請求體。

    Fields / 字段:
      symbol         — trading pair, e.g. "BTCUSDT" / 交易對
      timeframe      — kline timeframe, e.g. "5m", "1h" / K線時間框架
      strategy_name  — strategy identifier matching BacktestEngine supported strategies / 策略名稱
      lookback_days  — number of historical days to use / 歷史天數（默認 30）
      backtest_mode  — MUST be True; route enforces this / 必須為 True（端點強制）
    """
    symbol: str
    timeframe: str       # e.g. "5m", "1h"
    strategy_name: str
    lookback_days: int = 30
    backtest_mode: bool = True


# ── POST /api/v1/backtest/run ────────────────────────────────────────────────────

@router.post("/run")
async def run_backtest(
    body: BacktestRunRequest,
    actor: Any = Depends(_get_auth_actor),
) -> dict:
    """
    Execute a single strategy backtest run.
    執行單次策略回測。

    Requires Operator role — write action that records pattern evidence.
    需要 Operator 角色 — 寫入操作，會記錄模式證據。

    Steps / 執行步驟:
    1. Validate Operator role / 驗證 Operator 角色
    2. Force backtest_mode=True in config / 強制 backtest_mode=True
    3. Run BacktestEngine in thread pool (non-blocking) / 在線程池中執行（非阻塞）
    4. If sharpe_ratio > 1.0 and total_trades >= 10 → inject TruthSourceRegistry
       若 sharpe_ratio > 1.0 且 total_trades >= 10 → 注入 TruthSourceRegistry
    5. Return result.to_dict() / 返回 result.to_dict()

    Returns / 返回:
      dict with backtest results including trades, metrics, and optional truth_registered flag
      包含交易記錄、績效指標及可選 truth_registered 標記的回測結果字典
    """
    # Operator role guard — write/record action requires operator
    # Operator 角色守衛 — 寫入/記錄動作需要操作員權限
    _require_operator_role(actor)

    # Safety: force backtest_mode=True regardless of request body
    # 安全守衛：強制 backtest_mode=True，防止請求體傳入 False
    if not body.backtest_mode:
        raise HTTPException(
            status_code=400,
            detail="backtest_mode must be True; live/paper execution via this endpoint is not allowed",
        )

    # Build BacktestConfig / 構建 BacktestConfig
    config = BacktestConfig(
        symbol=body.symbol,
        timeframe=body.timeframe,
        strategy_name=body.strategy_name,
        backtest_mode=True,  # Explicitly enforced / 顯式強制
    )

    engine = get_backtest_engine()

    try:
        # Run in thread pool to avoid blocking the async event loop
        # 在線程池中執行，避免阻塞異步事件循環
        result = await asyncio.to_thread(engine.run, config, None)
    except ValueError as ve:
        # BacktestEngine raises ValueError for backtest_mode=False; re-raise as 400
        # BacktestEngine 在 backtest_mode=False 時拋出 ValueError，轉換為 400
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    except Exception as exc:
        logger.exception(
            "BacktestEngine.run raised unexpected exception for %s/%s: %s / "
            "BacktestEngine 執行時發生意外異常",
            body.symbol, body.timeframe, exc,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from exc

    result_dict = result.to_dict()

    # ── TruthSourceRegistry 注入（原則 12 — 持續進化學習管線）───────────────────
    # Inject high-quality backtest results into TruthSourceRegistry to feed
    # the learning pipeline (Principle 12).  This is fail-open: any error logs
    # a warning but does not affect the API response.
    # 將高品質回測結果注入 TruthSourceRegistry 以驅動學習管線（原則 12）。
    # fail-open：任何異常僅記錄 warning，不影響 API 響應。
    truth_registered = False
    if result.sharpe_ratio > 1.0 and result.total_trades >= 10:
        try:
            from .phase2_strategy_routes import ANALYST_AGENT  # noqa: PLC0415
            registry = getattr(ANALYST_AGENT, "_truth_registry", None)
            if registry is not None:
                registry.register_claim(
                    pattern_text=(
                        f"{body.strategy_name} on {body.symbol}/{body.timeframe}: "
                        f"win_rate={result.win_rate:.2%}, sharpe={result.sharpe_ratio:.2f}"
                    ),
                    evidence_source=f"statistical_N={result.total_trades}",
                    observation_count=result.total_trades,
                    # Cap confidence at win_rate but never exceed 0.7 (non-FACT evidence)
                    # 信度上限為 win_rate，且不超過 0.7（非 FACT 類證據）
                    confidence=min(0.7, result.win_rate),
                    applies_to_regime="all",
                    applies_to_strategy=body.strategy_name,
                )
                truth_registered = True
                logger.info(
                    "TruthRegistry: registered backtest claim for %s/%s strategy=%s "
                    "sharpe=%.2f win_rate=%.2f%% / "
                    "已向 TruthRegistry 登記回測聲明",
                    body.symbol, body.timeframe, body.strategy_name,
                    result.sharpe_ratio, result.win_rate * 100,
                )
            else:
                logger.debug(
                    "TruthRegistry not injected into AnalystAgent yet; "
                    "skipping backtest claim registration / "
                    "TruthRegistry 尚未注入 AnalystAgent，跳過聲明登記"
                )
        except Exception as e:
            # fail-open: TruthRegistry injection failure must not break backtest response
            # fail-open：TruthRegistry 注入失敗不得中斷回測響應
            logger.warning(
                "Backtest TruthRegistry injection failed (non-fatal): %s / "
                "TruthRegistry 注入失敗（非致命）",
                e,
            )

    result_dict["truth_registered"] = truth_registered
    return result_dict


# ── GET /api/v1/backtest/status ─────────────────────────────────────────────────

@router.get("/status")
async def get_backtest_status(
    actor: Any = Depends(_get_auth_actor),
) -> dict:
    """
    Return most recent BacktestEngine status (read-only, no Operator role required).
    返回最近一次 BacktestEngine 狀態（只讀，無需 Operator 角色）。

    All authenticated actors can query backtest status for observability.
    所有已認證的 actor 均可查詢回測狀態（可觀察性需求）。

    Returns / 返回:
      dict with status, last_run_ts, and summary of most recent backtest result
      包含狀態、最後執行時間戳及最近回測結果摘要的字典
    """
    # No Operator role required — read-only endpoint for observability
    # 無需 Operator 角色 — 只讀端點，供可觀察性查詢
    engine = get_backtest_engine()
    return engine.get_status()
