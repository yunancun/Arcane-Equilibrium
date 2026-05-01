"""Strategy Read Routes — GET-only route handlers (TD-02 split)."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from . import main_legacy as base
from .ipc_state_reader import get_rust_reader
from .prelive_edge_gate_trends import fetch_prelive_edge_gate_trends
from .rust_scanner_reader import (
    enrich_scanner_status_with_db,
    normalize_scanner_opportunities,
)
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


# ── Pre-Live Gate Trend Routes / Pre-Live Gate 趨勢路由 ──

@phase2_router.get("/prelive/edge-gates")
async def get_prelive_edge_gates(
    window_days: int = Query(
        default=7,
        ge=3,
        le=30,
        description="Trend window in days / 趨勢天數",
    ),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Return read-only trend data for pre-live gates [33], [38], and [40].
    回傳 pre-live gate [33]/[38]/[40] 的只讀趨勢資料。
    """
    try:
        return _envelope(fetch_prelive_edge_gate_trends(window_days=window_days))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error in get_prelive_edge_gates / get_prelive_edge_gates 異常")
        return _envelope(
            {
                "available": False,
                "source": "pg_prelive_edge_gate_trends",
                "window_days": window_days,
                "gates": {},
                "readiness": {"ready": False, "status": "not_ready", "items": []},
                "error": f"{type(exc).__name__}: {exc}",
            }
        )


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
        # Rust-first for klines — Python KlineManager is stale fallback only.
        # Rust 優先讀 K 線 — Python KlineManager 僅作降級備援。
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
        # Rust-first for ALL timeframes — Python INDICATOR_ENGINE is stale fallback only.
        # Rust 優先讀所有時間框架 — Python INDICATOR_ENGINE 僅作降級備援。
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
async def get_dynamic_risk_status(
    engine: str = Query("demo", description="paper|demo|live"),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get dynamic risk adjustment status (Sharpe-based) per engine.
    获取动态风控调整状态（基于 Sharpe，按引擎）。

    DYNAMIC-RISK-1: forwards to Rust IPC `get_dynamic_risk_status`. Python
    AUTO_DEPLOYER remains a stub; Rust is authoritative. Falls back to the stub
    shape on IPC failure so the GUI still renders a sane card.
    DYNAMIC-RISK-1：轉發到 Rust IPC；IPC 失敗時回 stub 形狀，GUI 不破版。
    """
    engine = (engine or "demo").lower()
    if engine not in ("paper", "demo", "live"):
        raise HTTPException(status_code=400, detail="engine must be paper|demo|live")
    # Lazy-import to avoid circular import at module load.
    # 懶匯入避免載入時循環依賴。
    try:
        from .strategy_write_routes import _get_strategy_ipc
        client = await _get_strategy_ipc()
        resp = await client.call(
            "get_dynamic_risk_status",
            params={"engine": engine},
        )
        if isinstance(resp, dict):
            out = dict(resp)
            out["engine"] = engine
            out["available"] = True
            return _envelope(out)
    except Exception as e:
        logger.warning("get_dynamic_risk_status IPC error engine=%s: %s", engine, e)
    # Fallback — sizer not reachable (engine down, pre-boot, or Python-only tests).
    # 回退 — 引擎不可達時回 stub 形狀。
    if AUTO_DEPLOYER is None:
        return _envelope({
            "engine": engine,
            "enabled": False,
            "available": False,
        })
    stub = AUTO_DEPLOYER.get_dynamic_risk_status()
    stub.update({"engine": engine, "available": False})
    return _envelope(stub)


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
        # 3E-ARCH: explicit mode="paper" — strategy intents view tracks paper engine.
        # 3E-ARCH：必須明確 mode="paper"，策略意圖視圖追蹤 paper 引擎。
        reader = get_rust_reader()
        if reader.is_engine_available("paper"):
            rust_intents = reader.get_recent_intents(mode="paper")
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
    # DEAD-PY-2: PIPELINE_BRIDGE permanently None — Rust engine is sole source.
    # DEAD-PY-2：PIPELINE_BRIDGE 永久 None — Rust 引擎為唯一數據源。
    return _envelope({"available": False})


@phase2_router.get("/scanner/opportunities")
async def get_scanner_opportunities(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """Get latest market scan opportunities from Rust scanner via IPC.

    IPC-SCAN-1c: Python MarketScanner is a stub (local_model_tools/market_scanner.py);
    authoritative data lives in rust/openclaw_engine/src/scanner/. This route reads
    `last_scan.top_candidates` from IPC `get_scanner_status`, keeps the legacy
    GUI fields, and exposes scanner_context / fitness / strategy_judgments when
    available.

    IPC-SCAN-1c：Python MarketScanner 僅為 stub，權威掃描資料在 Rust scanner。
    此路由透過 IPC get_scanner_status 讀取 last_scan.top_candidates，保留
    GUI 舊欄位，並補出 scanner_context / fitness / strategy_judgments。
    """
    try:
        from .ipc_client import EngineIPCClient  # noqa: PLC0415
        client = EngineIPCClient()
        try:
            await client.connect()
            result = await client.call("get_scanner_status", params={}, timeout=3.0)
        finally:
            await client.disconnect()

        status = result.get("status", "unknown")
        if status != "ok":
            return _envelope({
                "opportunities": [],
                "stats": {"status": status},
                "source": "rust_scanner",
            })

        result = enrich_scanner_status_with_db(result)
        last_scan = result.get("last_scan") or {}
        opportunities = normalize_scanner_opportunities(result)

        stats = {
            "scan_ts_ms": last_scan.get("scan_ts_ms"),
            "duration_ms": last_scan.get("duration_ms"),
            "added": last_scan.get("added"),
            "removed": last_scan.get("removed"),
            "rejected_count": last_scan.get("rejected_count"),
            "active_count": result.get("active_count"),
            "candidate_detail_source": last_scan.get("candidate_detail_source", "ipc"),
        }
        return _envelope({
            "opportunities": opportunities,
            "stats": stats,
            "source": "rust_scanner",
        })
    except Exception as e:
        # IPC unavailable — degrade to empty opportunities list, preserve envelope.
        # IPC 不可用，降級為空機會列表，保留 envelope 結構。
        logger.warning("scanner/opportunities IPC failed: %s", e)
        return _envelope({
            "opportunities": [],
            "stats": {},
            "source": "unavailable",
        })


@phase2_router.get("/scanner/deployed")
async def get_auto_deployed(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """
    Get active symbols managed by Rust ScannerRunner (primary) with Python deployer as fallback.
    優先返回 Rust ScannerRunner 管理的活躍 symbol universe；降級到 Python 部署器。

    NOTE: Python AUTO_DEPLOYER.on_scan_results() is deprecated (2026-04-10) — Rust ScannerRunner
    owns symbol management. This route now reflects the true runtime state via IPC.
    注意：Python AUTO_DEPLOYER 回調已棄用，此路由改為透過 IPC 讀取 Rust 真實活躍 symbol。
    """
    # IPC-SCAN-1a: Rust ScannerRunner is the authoritative symbol source.
    # IPC-SCAN-1a：Rust ScannerRunner 為活躍 symbol 的權威來源。
    try:
        from .ipc_client import EngineIPCClient  # noqa: PLC0415
        client = EngineIPCClient()
        try:
            await client.connect()
            result = await client.call("get_active_symbols", params={}, timeout=3.0)
        finally:
            await client.disconnect()

        symbols: list[str] = result.get("symbols", [])
        pinned: list[str] = result.get("pinned", [])
        status: str = result.get("status", "unknown")

        if status == "ok" and symbols:
            deployed = [
                {
                    "symbol": sym,
                    "strategy_name": "All Strategies",
                    "kind": "pinned" if sym in pinned else "dynamic",
                    "state": "active",
                    "source": "rust_scanner",
                }
                for sym in symbols
            ]
            stats = AUTO_DEPLOYER.get_stats() if AUTO_DEPLOYER is not None else {}
            return _envelope({
                "deployed": deployed,
                "stats": stats,
                "source": "rust_scanner",
                "symbol_count": len(symbols),
            })
    except Exception:
        # IPC unavailable — fall through to Python deployer.
        # IPC 不可用，降級到 Python 部署器。
        pass

    # Fallback: Python AUTO_DEPLOYER (deprecated path, may be empty).
    # 降級：Python AUTO_DEPLOYER（已棄用路徑，可能為空）。
    if AUTO_DEPLOYER is None:
        return _envelope({"available": False, "deployed": [], "source": "none"})
    try:
        return _envelope({
            "deployed": AUTO_DEPLOYER.get_deployed(),
            "stats": AUTO_DEPLOYER.get_stats(),
            "source": "python_deployer",
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


# ── PG-direct Data Routes (Phase 3b) / PG 直讀數據路由 ──


def _get_pg_conn():
    """Get a PostgreSQL connection from the shared pool. Returns None on failure.
    從共享連接池獲取 PG 連接。失敗返回 None。"""
    from . import db_pool
    return db_pool.get_conn()


def _put_pg_conn(conn) -> None:
    """Return a PostgreSQL connection to the shared pool.
    將 PG 連接歸還到共享連接池。"""
    from . import db_pool
    db_pool.put_conn(conn)


@phase2_router.get("/data/fills/recent")
async def get_recent_fills_from_pg(
    symbol: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """Get recent fills directly from PostgreSQL trading.fills table.
    從 PostgreSQL trading.fills 表直接獲取最近成交記錄。

    Source: Rust engine → trading_writer → PG (real-time).
    數據源：Rust 引擎 → trading_writer → PG（即時）。

    W1-T3 (PA 2026-04-29 strategy_name attribution cleanup §1.2 GUI passthrough):
    SELECT additionally returns ``exit_reason`` (V033 column, nullable). Once
    W1-T2 lands the close-path emit normalisation, ``strategy_name`` will hold
    the 5 enum entry strategy name and ``exit_reason`` will carry the dynamic
    trace (e.g. ``TRAILING STOP: peak X% - current Y% = ...``). Historical rows
    pre-V033 keep ``exit_reason = NULL`` and the legacy ``strategy_name`` shape;
    GUI renders ``strategy_name + (exit_reason ? ' (' + exit_reason + ')' : '')``
    so operator still sees both pieces.

    W1-T3（PA 2026-04-29 attribution cleanup §1.2 GUI passthrough）：
    SELECT 多回 ``exit_reason``（V033 nullable column）。W1-T2 落地後 close path
    的 ``strategy_name`` 為 5 enum 之一、``exit_reason`` 帶動態 trace；歷史 row
    維持原 ``strategy_name`` + ``exit_reason=NULL``。
    """
    conn = _get_pg_conn()
    if conn is None:
        return JSONResponse(status_code=503, content={"error": "database_unavailable", "fills": []})
    try:
        cur = conn.cursor()
        if symbol:
            cur.execute(
                "SELECT ts, fill_id, symbol, side, qty, price, fee, realized_pnl, strategy_name, exit_reason "
                "FROM trading.fills WHERE symbol = %s ORDER BY ts DESC LIMIT %s",
                (symbol, limit),
            )
        else:
            cur.execute(
                "SELECT ts, fill_id, symbol, side, qty, price, fee, realized_pnl, strategy_name, exit_reason "
                "FROM trading.fills ORDER BY ts DESC LIMIT %s",
                (limit,),
            )
        rows = cur.fetchall()
        cols = [
            "ts",
            "fill_id",
            "symbol",
            "side",
            "qty",
            "price",
            "fee",
            "realized_pnl",
            "strategy",
            "exit_reason",
        ]
        fills = [dict(zip(cols, row)) for row in rows]
        # Convert timestamps to ISO strings / 轉換時間戳為 ISO 字符串
        for f in fills:
            if f["ts"]:
                f["ts"] = f["ts"].isoformat()
        return _envelope({"fills": fills, "count": len(fills), "source": "pg_trading_fills"})
    except Exception as e:
        logger.error("PG fills query failed: %s", e)
        return JSONResponse(status_code=503, content={"error": "database_unavailable", "detail": str(e), "fills": []})
    finally:
        _put_pg_conn(conn)


@phase2_router.get("/data/signals/recent")
async def get_recent_signals_from_pg(
    symbol: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    """Get recent signals directly from PostgreSQL trading.signals table.
    從 PostgreSQL trading.signals 表直接獲取最近信號。

    Source: Rust engine → trading_writer → PG (real-time).
    數據源：Rust 引擎 → trading_writer → PG（即時）。
    """
    conn = _get_pg_conn()
    if conn is None:
        return JSONResponse(status_code=503, content={"error": "database_unavailable", "signals": []})
    try:
        cur = conn.cursor()
        if symbol:
            cur.execute(
                "SELECT ts, signal_id, symbol, strategy_name, signal_type, strength "
                "FROM trading.signals WHERE symbol = %s ORDER BY ts DESC LIMIT %s",
                (symbol, limit),
            )
        else:
            cur.execute(
                "SELECT ts, signal_id, symbol, strategy_name, signal_type, strength "
                "FROM trading.signals ORDER BY ts DESC LIMIT %s",
                (limit,),
            )
        rows = cur.fetchall()
        cols = ["ts", "signal_id", "symbol", "strategy_name", "signal_type", "strength"]
        signals = [dict(zip(cols, row)) for row in rows]
        for s in signals:
            if s["ts"]:
                s["ts"] = s["ts"].isoformat()
        return _envelope({"signals": signals, "count": len(signals), "source": "pg_trading_signals"})
    except Exception as e:
        logger.error("PG signals query failed: %s", e)
        return JSONResponse(status_code=503, content={"error": "database_unavailable", "detail": str(e), "signals": []})
    finally:
        _put_pg_conn(conn)


@phase2_router.get("/data/features/latest")
async def get_latest_features_from_pg(
    symbol: str | None = Query(None),
):
    """Get latest feature vectors from PostgreSQL features.online_latest table.
    從 PostgreSQL features.online_latest 表獲取最新特徵向量。

    Source: Rust engine → feature_writer → PG (real-time UPSERT).
    數據源：Rust 引擎 → feature_writer → PG（即時 UPSERT）。
    """
    conn = _get_pg_conn()
    if conn is None:
        return JSONResponse(status_code=503, content={"error": "database_unavailable", "features": []})
    try:
        cur = conn.cursor()
        if symbol:
            cur.execute(
                "SELECT symbol, timeframe, updated_ts_ms, feature_vector, feature_version "
                "FROM features.online_latest WHERE symbol = %s",
                (symbol,),
            )
        else:
            cur.execute(
                "SELECT symbol, timeframe, updated_ts_ms, feature_vector, feature_version "
                "FROM features.online_latest ORDER BY symbol",
            )
        rows = cur.fetchall()
        cols = ["symbol", "timeframe", "updated_ts_ms", "feature_vector", "feature_version"]
        features = [dict(zip(cols, row)) for row in rows]
        return _envelope({"features": features, "count": len(features), "source": "pg_features_online"})
    except Exception as e:
        logger.error("PG features query failed: %s", e)
        return JSONResponse(status_code=503, content={"error": "database_unavailable", "detail": str(e), "features": []})
    finally:
        _put_pg_conn(conn)
