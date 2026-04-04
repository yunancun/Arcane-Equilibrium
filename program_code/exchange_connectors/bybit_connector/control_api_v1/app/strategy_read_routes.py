"""Strategy Read Routes — GET-only route handlers (TD-02 split)."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, HTTPException, Query

from . import main_legacy as base
from .ipc_state_reader import get_rust_reader
from .strategy_wiring import (
    phase2_router,
    KLINE_MANAGER,
    INDICATOR_ENGINE,
    SIGNAL_ENGINE,
    ORCHESTRATOR,
    PIPELINE_BRIDGE,
    MARKET_SCANNER,
    AUTO_DEPLOYER,
    _validate_symbol,
    _validate_strategy_name,
    _envelope,
    _VALID_TIMEFRAMES,
)

logger = logging.getLogger(__name__)


# ── Kline Routes / K线路由 ──

@phase2_router.get("/klines/{symbol}/{timeframe}")
async def get_klines(
    symbol: str,
    timeframe: str,
    n: int = Query(default=50, ge=1, le=500, description="Number of klines to return / 返回K线数量"),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get latest N closed klines for a symbol + timeframe.
    获取指定交易对 + 时间框架的最近 N 根已闭合 K线。
    """
    sym = _validate_symbol(symbol)
    if sym is None:
        raise HTTPException(status_code=400, detail="Invalid symbol (1-20 alphanumeric) / 无效交易对")
    if timeframe not in _VALID_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe, valid: {sorted(_VALID_TIMEFRAMES)} / 无效时间框架")
    try:
        # RC-11: Rust-first for klines — Rust is sole tick processor, Python KlineManager
        # no longer receives ticks and returns empty data.
        # RC-11：K 線優先讀 Rust — Rust 為唯一 tick 處理器，Python KlineManager
        # 不再接收 tick，返回空數據。
        reader = get_rust_reader()
        if reader.is_available():
            rust_klines = reader.get_klines(sym, n=n)
            if rust_klines:
                return _envelope({
                    "symbol": sym,
                    "timeframe": timeframe,
                    "closed_klines": rust_klines,
                    "current_bar": None,  # Rust snapshot only has closed bars
                    "count": len(rust_klines),
                    "source": "rust_engine",
                })
        # Fallback to Python KlineManager (stale data, for backward compat)
        # 降級到 Python KlineManager（過期數據，向後兼容）
        klines = KLINE_MANAGER.get_latest_klines(sym, timeframe, n=n)
        current = KLINE_MANAGER.get_current_bar(sym, timeframe)
        return _envelope({
            "symbol": sym,
            "timeframe": timeframe,
            "closed_klines": klines,
            "current_bar": current.to_dict() if current else None,
            "count": len(klines),
        })
    except Exception:
        logger.exception("Error in get_klines / get_klines 异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


# ── Indicator Routes / 指标路由 ──

@phase2_router.get("/indicators/{symbol}/{timeframe}")
async def get_indicators(
    symbol: str,
    timeframe: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get latest cached indicator values for a symbol + timeframe.
    获取指定交易对 + 时间框架的最新缓存指标值。
    """
    sym = _validate_symbol(symbol)
    if sym is None:
        raise HTTPException(status_code=400, detail="Invalid symbol / 无效交易对")
    if timeframe not in _VALID_TIMEFRAMES:
        raise HTTPException(status_code=400, detail="Invalid timeframe / 无效时间框架")
    try:
        # RC-11: Rust-first for ALL timeframes — Rust is the sole tick processor,
        # Python INDICATOR_ENGINE no longer receives ticks and returns stale/empty data.
        # RC-11：所有時間框架都優先讀 Rust — Rust 是唯一 tick 處理器，
        # Python INDICATOR_ENGINE 不再接收 tick，返回過期/空數據。
        reader = get_rust_reader()
        if reader.is_available():
            rust_ind = reader.get_indicators(sym)
            if rust_ind:
                return _envelope({
                    "symbol": sym,
                    "timeframe": timeframe,
                    "indicators": rust_ind,
                    "indicator_count": len(rust_ind),
                    "source": "rust_engine",
                })
        # Fallback to Python IndicatorEngine (stale data, for backward compat)
        # 降級到 Python 指標引擎（過期數據，向後兼容）
        indicators = INDICATOR_ENGINE.get_indicators(sym, timeframe)
        return _envelope({
            "symbol": sym,
            "timeframe": timeframe,
            "indicators": indicators,
            "indicator_count": len(indicators),
        })
    except Exception:
        logger.exception("Error in get_indicators / get_indicators 异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


# ── Signal Routes / 信号路由 ──

@phase2_router.get("/signals")
async def get_signals(
    symbol: str = Query(default=None, description="Filter by symbol / 按交易对过滤"),
    n: int = Query(default=50, ge=1, le=200, description="Number of signals / 信号数量"),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get recent trading signals.
    获取最近的交易信号。
    """
    filter_sym = None
    if symbol:
        filter_sym = _validate_symbol(symbol)
        if filter_sym is None:
            raise HTTPException(status_code=400, detail="Invalid symbol / 无效交易对")
    try:
        # IPC-03: Rust-first for signals / 優先讀 Rust 信號
        reader = get_rust_reader()
        if reader.is_available():
            rust_signals = reader.get_signals()
            if rust_signals:
                # Apply symbol filter if requested / 若指定了交易對則過濾
                if filter_sym:
                    rust_signals = [s for s in rust_signals if s.get("symbol") == filter_sym]
                rust_signals = rust_signals[:n]
                return _envelope({
                    "signals": rust_signals,
                    "count": len(rust_signals),
                    "filter_symbol": filter_sym,
                    "source": "rust_engine",
                })
        # Fallback to Python SignalEngine / 降級到 Python 信號引擎
        signals = SIGNAL_ENGINE.get_latest_signals(symbol=filter_sym, n=n)
        return _envelope({
            "signals": signals,
            "count": len(signals),
            "filter_symbol": filter_sym,
        })
    except Exception:
        logger.exception("Error in get_signals / get_signals 异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


@phase2_router.get("/signals/{symbol}/summary")
async def get_signal_summary(
    symbol: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get signal consensus summary for a symbol.
    获取指定交易对的信号共识摘要。
    """
    sym = _validate_symbol(symbol)
    if sym is None:
        raise HTTPException(status_code=400, detail="Invalid symbol / 无效交易对")
    try:
        # IPC-03: Rust-first — compute consensus from Rust signals / 優先用 Rust 信號計算共識
        reader = get_rust_reader()
        if reader.is_available():
            rust_signals = reader.get_signals()
            if rust_signals:
                sym_signals = [s for s in rust_signals if s.get("symbol") == sym]
                if sym_signals:
                    # Compute simple consensus from Rust signals / 從 Rust 信號計算簡單共識
                    buy_count = sum(1 for s in sym_signals if s.get("direction") == "buy")
                    sell_count = sum(1 for s in sym_signals if s.get("direction") == "sell")
                    total = len(sym_signals)
                    consensus = "neutral"
                    if buy_count > sell_count:
                        consensus = "bullish"
                    elif sell_count > buy_count:
                        consensus = "bearish"
                    return _envelope({
                        "symbol": sym,
                        "consensus": consensus,
                        "buy_signals": buy_count,
                        "sell_signals": sell_count,
                        "total_signals": total,
                        "source": "rust_engine",
                    })
        # Fallback to Python SignalEngine / 降級到 Python 信號引擎
        summary = SIGNAL_ENGINE.get_signal_summary(sym)
        return _envelope(summary)
    except Exception:
        logger.exception("Error in get_signal_summary / get_signal_summary 异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


# ── Strategy Management Routes / 策略管理路由 ──

@phase2_router.get("/list")
async def list_strategies(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    List all registered strategies and their states.
    列出所有注册的策略及其状态。
    """
    try:
        # IPC-03: Rust-first for strategy list / 優先讀 Rust 策略列表
        reader = get_rust_reader()
        if reader.is_available():
            rust_strategies = reader.get_strategies()
            if rust_strategies:
                return _envelope({
                    "strategies": rust_strategies,
                    "count": len(rust_strategies),
                    "source": "rust_engine",
                })
        # Fallback to Python Orchestrator / 降級到 Python 編排器
        statuses = ORCHESTRATOR.get_all_strategies_status()
        return _envelope({
            "strategies": statuses,
            "count": len(statuses),
        })
    except Exception:
        logger.exception("Error in list_strategies / list_strategies 异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


@phase2_router.get("/dynamic-risk/status")
async def get_dynamic_risk_status(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """
    Get dynamic risk adjustment status (Sharpe-based).
    获取动态风控调整状态（基于 Sharpe）。
    """
    if AUTO_DEPLOYER is None:
        return _envelope({"enabled": False, "active": False, "available": False})
    try:
        return _envelope(AUTO_DEPLOYER.get_dynamic_risk_status())
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")


@phase2_router.get("/{name}/status")
async def get_strategy_status(
    name: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get status of a specific strategy.
    获取指定策略的状态。
    """
    if _validate_strategy_name(name) is None:
        raise HTTPException(status_code=400, detail="Invalid strategy name / 无效策略名称")
    try:
        # IPC-03: Rust-first — find strategy by name / 優先從 Rust 按名稱查找策略
        reader = get_rust_reader()
        if reader.is_available():
            rust_strategies = reader.get_strategies()
            if rust_strategies:
                match = next((s for s in rust_strategies if s.get("name") == name), None)
                if match:
                    return _envelope({**match, "source": "rust_engine"})
        # Fallback to Python Orchestrator / 降級到 Python 編排器
        status = ORCHESTRATOR.get_strategy_status(name)
        if status is None:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found / 策略 '{name}' 未找到")
        return _envelope(status)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error in get_strategy_status / get_strategy_status 异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


# ── Intent & Status Routes / 意图与状态路由 ──

@phase2_router.get("/intents")
async def get_intents(
    n: int = Query(default=50, ge=1, le=200, description="Number of intents / 意图数量"),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get recent OrderIntent history.
    获取最近的 OrderIntent 历史。
    """
    try:
        # IPC-03: Rust-first for recent intents / 優先讀 Rust 最近交易意圖
        reader = get_rust_reader()
        if reader.is_available():
            rust_intents = reader.get_recent_intents()
            if rust_intents:
                return _envelope({
                    "intents": rust_intents[:n],
                    "count": min(len(rust_intents), n),
                    "source": "rust_engine",
                })
        # Fallback to Python Orchestrator / 降級到 Python 編排器
        history = ORCHESTRATOR.get_intent_history(n=n)
        return _envelope({
            "intents": history,
            "count": len(history),
        })
    except Exception:
        logger.exception("Error in get_intents / get_intents 异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


@phase2_router.get("/status")
async def get_orchestrator_status(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get comprehensive orchestrator status including all sub-components.
    获取编排器综合状态，包括所有子组件。
    """
    try:
        # IPC-03: Rust-first for strategy portion of status / 優先讀 Rust 策略狀態
        reader = get_rust_reader()
        if reader.is_available():
            rust_strategies = reader.get_strategies()
            if rust_strategies:
                # Merge Rust strategy data into orchestrator status / 將 Rust 策略數據合併到編排器狀態
                py_status = ORCHESTRATOR.get_status()
                py_status["strategies"] = rust_strategies
                py_status["strategy_source"] = "rust_engine"
                return _envelope(py_status)
        return _envelope(ORCHESTRATOR.get_status())
    except Exception:
        logger.exception("Error in get_orchestrator_status / get_orchestrator_status 异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


# ── Market Scanner Routes / 市场扫描路由 ──

@phase2_router.get("/pipeline/stats")
async def get_pipeline_stats(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """Get pipeline bridge statistics / 获取管线桥接器统计"""
    # R06-B: try Rust engine tick stats first / 優先讀取 Rust 引擎 tick 統計
    rust = get_rust_reader()
    rust_stats = rust.get_tick_stats() if rust.is_available() else None
    if rust_stats is not None:
        return _envelope({
            "source": "rust_engine",
            "total_ticks": rust_stats.get("total_ticks", 0),
            "total_fills": rust_stats.get("total_fills", 0),
            "total_intents": rust_stats.get("total_intents", 0),
            "total_stops": rust_stats.get("total_stops", 0),
            "last_tick_ms": rust_stats.get("last_tick_ms", 0),
        })
    if PIPELINE_BRIDGE is None:
        return _envelope({"available": False})
    try:
        return _envelope(PIPELINE_BRIDGE.get_stats())
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")


@phase2_router.get("/scanner/opportunities")
async def get_scanner_opportunities(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """Get latest market scan opportunities / 获取最新市场扫描机会"""
    if MARKET_SCANNER is None:
        return _envelope({"available": False})
    try:
        return _envelope({
            "opportunities": MARKET_SCANNER.get_latest_opportunities(),
            "stats": MARKET_SCANNER.get_stats(),
        })
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")


@phase2_router.get("/scanner/deployed")
async def get_auto_deployed(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """Get auto-deployed strategies / 获取自动部署的策略"""
    if AUTO_DEPLOYER is None:
        return _envelope({"available": False})
    try:
        return _envelope({
            "deployed": AUTO_DEPLOYER.get_deployed(),
            "stats": AUTO_DEPLOYER.get_stats(),
        })
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")


@phase2_router.get("/kelly-recommendations")
async def get_kelly_recommendations(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """
    0B-3: Get Kelly-based position sizing recommendations for all deployed strategies.
    獲取所有已部署策略的 Kelly 倉位建議。
    """
    if AUTO_DEPLOYER is None:
        return _envelope({"strategies": {}, "available": False})
    try:
        return _envelope(AUTO_DEPLOYER.get_kelly_recommendations())
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")
