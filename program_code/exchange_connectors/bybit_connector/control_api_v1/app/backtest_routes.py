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
import json as _json
import logging
import os
import threading
import urllib.parse
import urllib.request
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

# ── sys.path 注入（統一由 _path_setup 模塊處理）──────────────────────────────────
# sys.path injection — centralized in _path_setup.py (APR01-MEDIUM-11 dedup)
from . import _path_setup  # noqa: F401  — ensures program_code/ is on sys.path

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


def _get_kline_manager() -> Any:
    """
    Lazily import KLINE_MANAGER from phase2_strategy_routes.
    延遲導入 phase2_strategy_routes 的 KLINE_MANAGER 單例。

    Returns None if import fails (fail-open — BacktestEngine handles None gracefully,
    and _fetch_ohlcv_from_bybit provides an independent fallback).
    導入失敗時返回 None（fail-open — BacktestEngine 會妥善處理 None，
    且 _fetch_ohlcv_from_bybit 提供獨立的後備數據源）。
    """
    try:
        from .strategy_wiring import KLINE_MANAGER  # noqa: PLC0415  — import from source, not facade, to avoid circular import
        return KLINE_MANAGER
    except Exception as e:
        logger.warning(
            "Cannot import KLINE_MANAGER from phase2_strategy_routes: %s / "
            "無法從 phase2_strategy_routes 導入 KLINE_MANAGER：%s",
            e, e,
        )
        return None


# ── Bybit REST API 直接獲取 OHLCV / Direct Bybit REST OHLCV fetch ──────────────
# Fallback data source when KlineManager has no cached data for the requested
# symbol/timeframe. This is a read-only operation that fetches historical klines
# directly from Bybit public API. Principle 7 safe — no live state mutation.
# 當 KlineManager 沒有請求的 symbol/timeframe 緩存數據時的後備數據源。
# 這是唯讀操作，直接從 Bybit 公開 API 獲取歷史 K 線。符合原則 7 — 不修改任何線上狀態。

_BYBIT_TF_MAP: dict[str, str] = {
    "1m": "1", "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "4h": "240", "1d": "D",
}

# 歷史 K 線為公開 API，mainnet 和 demo 返回相同數據；
# 默認 demo 避免回測模組意外指向 mainnet。
_BYBIT_BASE_URL = os.getenv("OPENCLAW_BYBIT_BACKTEST_URL", "https://api-demo.bybit.com")


def _fetch_ohlcv_from_bybit(
    symbol: str, timeframe: str, limit: int = 200,
) -> dict[str, list[float]] | None:
    """
    Fetch historical OHLCV directly from Bybit REST API as a fallback.
    從 Bybit REST API 直接獲取歷史 OHLCV 作為後備數據源。

    Returns OHLCV dict {"open":[], "high":[], "low":[], "close":[], "volume":[]}
    or None on failure. This is a synchronous call — intended to run inside
    asyncio.to_thread().
    返回 OHLCV 字典，失敗時返回 None。這是同步調用 — 設計在 asyncio.to_thread() 中運行。

    Safety / 安全:
      - Read-only public API call, no authentication needed / 唯讀公開 API，無需認證
      - 10s timeout to prevent blocking / 10 秒超時防止阻塞
      - fail-open: returns None on any error / fail-open：任何錯誤返回 None
    """
    bybit_interval = _BYBIT_TF_MAP.get(timeframe)
    if bybit_interval is None:
        logger.warning(
            "Unsupported timeframe '%s' for Bybit API fetch / "
            "不支持的時間框架 '%s'，無法從 Bybit API 獲取",
            timeframe, timeframe,
        )
        return None

    limit = min(limit, 200)  # Bybit max is 200 per request / Bybit 每次最多 200

    try:
        url = (
            f"{_BYBIT_BASE_URL}/v5/market/kline"
            f"?category=linear&symbol={urllib.parse.quote(symbol, safe='')}"
            f"&interval={urllib.parse.quote(bybit_interval, safe='')}&limit={limit}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "OpenClaw/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read().decode())

        if data.get("retCode") != 0:
            logger.warning(
                "Bybit kline API error for %s/%s: %s / Bybit K線 API 錯誤",
                symbol, timeframe, data.get("retMsg", "unknown"),
            )
            return None

        klines = data.get("result", {}).get("list", [])
        if not klines:
            return None

        # Bybit returns newest first → reverse to chronological order
        # Bybit 返回最新在前 → 反轉為時間順序
        klines.reverse()

        opens, highs, lows, closes, volumes = [], [], [], [], []
        for k in klines:
            # Bybit kline format: [startTime, open, high, low, close, volume, turnover]
            opens.append(float(k[1]))
            highs.append(float(k[2]))
            lows.append(float(k[3]))
            closes.append(float(k[4]))
            volumes.append(float(k[5]))

        logger.info(
            "Fetched %d bars from Bybit API for %s/%s / "
            "從 Bybit API 獲取了 %d 根 K 線（%s/%s）",
            len(closes), symbol, timeframe,
            len(closes), symbol, timeframe,
        )
        return {
            "open": opens, "high": highs, "low": lows,
            "close": closes, "volume": volumes,
        }

    except Exception as e:
        logger.warning(
            "Failed to fetch OHLCV from Bybit API for %s/%s: %s / "
            "從 Bybit API 獲取 %s/%s OHLCV 失敗：%s",
            symbol, timeframe, e, symbol, timeframe, e,
        )
        return None


def get_backtest_engine() -> BacktestEngine:
    """
    Return the module-level BacktestEngine singleton, creating it if needed.
    返回模塊級 BacktestEngine 單例，不存在時創建。

    Injects KLINE_MANAGER so BacktestEngine can read historical OHLCV data
    from the live KlineManager cache (read-only, Principle 7 safe).
    注入 KLINE_MANAGER，使 BacktestEngine 可從線上 KlineManager 緩存讀取
    歷史 OHLCV 數據（唯讀，符合原則 7 隔離）。

    Thread-safe via double-check locking pattern.
    雙重檢查鎖確保線程安全。
    """
    global _backtest_engine
    if _backtest_engine is None:
        with _backtest_lock:
            # Double-check: another thread may have initialized while waiting
            # 雙重檢查：等待鎖期間另一個線程可能已初始化
            if _backtest_engine is None:
                km = _get_kline_manager()
                _backtest_engine = BacktestEngine(kline_manager=km)
                logger.info(
                    "BacktestEngine singleton initialized (kline_manager=%s) / "
                    "BacktestEngine 單例已初始化（kline_manager=%s）",
                    "injected" if km is not None else "None",
                    "已注入" if km is not None else "無",
                )
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
    symbol: str = Field(..., max_length=40, pattern=r"^[A-Z0-9]{1,40}$")  # e.g. "BTCUSDT" — 40 chars covers all Bybit pairs
    timeframe: str = Field(..., max_length=10)       # e.g. "5m", "1h"
    strategy_name: str = Field(..., max_length=200)  # strategy identifier
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

    # ── Resolve OHLCV data / 解析 OHLCV 數據 ──────────────────────────────────
    # Strategy: try KlineManager cache first (via engine._live_kline_manager),
    # then fall back to direct Bybit API fetch if no cached data available.
    # 策略：先嘗試 KlineManager 緩存（透過 engine._live_kline_manager），
    # 若無緩存數據則回退到直接從 Bybit API 獲取。
    ohlcv_data: dict[str, list[float]] | None = None

    # Let BacktestEngine try KlineManager first by passing ohlcv_data=None;
    # if KlineManager is injected and has data, engine.run() will use it.
    # We pre-check here to provide the Bybit API fallback if KlineManager is empty.
    # 先讓 BacktestEngine 嘗試 KlineManager（透過 ohlcv_data=None）；
    # 若 KlineManager 已注入且有數據，engine.run() 會直接使用。
    # 這裡預先檢查，若 KlineManager 為空則提供 Bybit API 後備。
    km = engine._live_kline_manager
    if km is not None:
        try:
            cached = km.get_ohlcv(body.symbol, body.timeframe)
            if cached and cached.get("close") and len(cached["close"]) > 0:
                ohlcv_data = cached
        except Exception:
            pass  # Will try Bybit API fallback below / 下方會嘗試 Bybit API 後備

    if ohlcv_data is None:
        # KlineManager has no data → fetch directly from Bybit API
        # KlineManager 無數據 → 直接從 Bybit API 獲取
        logger.info(
            "KlineManager has no cached data for %s/%s, fetching from Bybit API / "
            "KlineManager 無 %s/%s 緩存，從 Bybit API 獲取",
            body.symbol, body.timeframe, body.symbol, body.timeframe,
        )
        ohlcv_data = await asyncio.to_thread(
            _fetch_ohlcv_from_bybit, body.symbol, body.timeframe, 200,
        )

    try:
        # Run in thread pool to avoid blocking the async event loop
        # 在線程池中執行，避免阻塞異步事件循環
        result = await asyncio.to_thread(engine.run, config, ohlcv_data)
    except ValueError as ve:
        # BacktestEngine raises ValueError for invalid config; log server-side, sanitize response
        # BacktestEngine 對無效配置拋出 ValueError；伺服器端記錄，HTTP 響應不暴露細節
        logger.warning("Backtest config validation error: %s", ve)
        raise HTTPException(status_code=400, detail="Invalid backtest configuration") from ve
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
