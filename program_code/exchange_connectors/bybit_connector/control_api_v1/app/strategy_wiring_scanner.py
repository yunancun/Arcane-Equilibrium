from __future__ import annotations

"""
Strategy Wiring -- MarketScanner + AutoDeployer + ScoutWorker + Auto-Observation
(Split from strategy_wiring.py per STRATEGY-WIRING-SPLIT P2, 2026-04-28)

MODULE_NOTE (中文):
  從 strategy_wiring.py 抽出的「市場掃描器 + 策略自動部署器 + ScoutWorker 30
  分鐘情報注入 + Auto-Observation Writer + Scout routes 接線」leaf cluster。
  4 個邏輯子塊全屬 leaf — 無下游 wiring 依賴此處的 closure；只消費已建好的
  singleton（ORCHESTRATOR / KLINE_MANAGER / PAPER_ENGINE / SCOUT_AGENT /
  MESSAGE_BUS）。

  以函數 ``wire_market_scanner_and_workers(deps)`` 暴露，由 strategy_wiring.py
  在原 init 順序的位置呼叫並把回傳的 singleton 綁回 module attribute（保
  ``app.strategy_wiring.MARKET_SCANNER`` / ``AUTO_DEPLOYER`` 屬性 grep 穩定，
  下游 strategy_read_routes / strategy_write_routes ``from .strategy_wiring
  import MARKET_SCANNER, AUTO_DEPLOYER`` 不破）。

MODULE_NOTE (English):
  Market scanner + auto-deployer + ScoutWorker (30-min intel injection) +
  auto-observation writer + scout_routes wiring extracted from
  strategy_wiring.py per STRATEGY-WIRING-SPLIT P2 (2026-04-28). All 4
  sub-blocks are leaf — no downstream wiring depends on closures here;
  they only consume already-built singletons (ORCHESTRATOR / KLINE_MANAGER /
  PAPER_ENGINE / SCOUT_AGENT / MESSAGE_BUS).

  Exposed as ``wire_market_scanner_and_workers(deps)``; strategy_wiring.py
  calls it at the original init-sequence position and binds returned
  singletons to module attributes (preserves
  ``app.strategy_wiring.MARKET_SCANNER`` / ``AUTO_DEPLOYER`` grep stability;
  downstream ``from .strategy_wiring import MARKET_SCANNER, AUTO_DEPLOYER``
  callers in strategy_read_routes / strategy_write_routes unaffected).

安全不变量 / Safety invariants:
  - All sub-blocks are fail-open: any exception logs and continues with the
    relevant singleton set to None (CLAUDE.md §二 原則 #6 失敗默認收縮 +
    main pipeline never disrupted)
  - DEAD-PY-2 paths preserved: PIPELINE_BRIDGE = None → auto-observation
    writer not injected (no-op pass)
"""

import logging
import time as _time_mod
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ScannerWiringResult:
    """Container for singletons produced by ``wire_market_scanner_and_workers``.

    各 field 對應原 strategy_wiring.py module-level singleton。caller 應將
    這些值 bind 回 ``app.strategy_wiring`` 的 module attribute，以維持下游
    ``from .strategy_wiring import MARKET_SCANNER, AUTO_DEPLOYER`` 的 grep
    stability。

    Container for singletons produced by the wiring function. Caller should
    bind these back to ``app.strategy_wiring`` module attributes to preserve
    grep stability for downstream ``from .strategy_wiring import ...``.
    """

    market_scanner: Optional[Any] = None
    auto_deployer: Optional[Any] = None
    scout_worker: Optional[Any] = None


def wire_market_scanner_and_workers(
    *,
    orchestrator: Any,
    kline_manager: Any,
    paper_engine: Any,
    scout_agent: Any,
    message_bus: Any,
) -> ScannerWiringResult:
    """Wire MarketScanner + AutoDeployer + ScoutWorker + scout_routes.

    執行 4 個原 strategy_wiring.py top-level 子塊：
      1. MarketScanner + StrategyAutoDeployer 建構 + scan callback 註冊 +
         BacktestEngine / evolution_routes 注入
      2. ScoutWorker 30-min 情報注入 (每 30 分鐘呼叫 MarketScanner.scan() →
         經 ScoutAgent.produce_intel() 注入給 Strategist chain)
      3. scout_routes ScoutAgent + MessageBus + PerceptionPlane 接線
      4. Auto-Observation Writer (DEAD-PY-2 後僅保留閉環 try/except，不再
         注入 PipelineBridge — pass)

    Run the 4 original strategy_wiring.py top-level sub-blocks listed above.

    Args:
      orchestrator: ORCHESTRATOR singleton (StrategyOrchestrator)
      kline_manager: KLINE_MANAGER singleton (KlineManager)
      paper_engine: PAPER_ENGINE singleton (None since ARCH-RC1 1C-3-F)
      scout_agent: SCOUT_AGENT singleton (ScoutAgent)
      message_bus: MESSAGE_BUS singleton (MessageBus)

    Returns:
      ScannerWiringResult with market_scanner / auto_deployer / scout_worker
      (any of them can be None if the corresponding sub-block fail-open path
      was taken).
    """

    result = ScannerWiringResult()

    # ── Market Scanner + Strategy Auto-Deployer (autonomous opportunity discovery) ──
    # 市场扫描器 + 策略自动部署器（自主发现交易机会）
    try:
        from local_model_tools.market_scanner import MarketScanner
        from local_model_tools.strategy_auto_deployer import StrategyAutoDeployer

        # Lazy dispatcher reference: resolves at call time so it works even if
        # market feed starts after the auto-deployer is created.
        # 惰性 dispatcher 引用：调用时才解析，无论行情流何时启动均有效。
        from . import paper_trading_routes as _ptr  # noqa: F401 — kept for parity

        result.market_scanner = MarketScanner(max_symbols=25, categories=["linear", "spot"])
        result.auto_deployer = StrategyAutoDeployer(
            orchestrator=orchestrator,
            kline_manager=kline_manager,
            paper_engine=paper_engine,
            max_symbols=30,            # 25 linear + 5 spot reserved
            risk_per_trade_pct=3.0,    # Risk 3% of balance per trade (max loss per trade)
            min_qty_usdt=20.0,         # Minimum $20 per trade
            max_qty_pct=18.0,          # Max 18% of balance per single trade (90% of 20% risk limit, 10% headroom)

            pinned_symbols=["BTCUSDT", "ETHUSDT"],  # Always monitor + attempt to trade (learning/evolution)
            reserved_slots={"spot": 5},  # 5 slots reserved for spot — linear can't squeeze them out
        )
        result.market_scanner.register_on_scan(result.auto_deployer.on_scan_results)
        result.market_scanner.start()

        # DEAD-PY-2: PipelineBridge removed — auto-deployer runs without bridge reference.
        # DEAD-PY-2：PipelineBridge 已移除 — 自動部署器不再持有橋接器引用。

        # 0A-5: Inject BacktestEngine into auto-deployer for pre-deployment validation.
        # 0A-5：注入 BacktestEngine 到自動部署器，供部署前回測驗證使用。
        try:
            from .backtest_routes import get_backtest_engine as _get_bt_engine
            _bt_engine = _get_bt_engine()
            result.auto_deployer.set_backtest_engine(_bt_engine, min_sharpe=0.0)
            logger.info(
                "0A-5: BacktestEngine injected into auto-deployer / "
                "BacktestEngine 已注入自動部署器供部署前驗證"
            )
        except Exception as _bt_wire_err:
            logger.warning(
                "0A-5: Could not wire BacktestEngine to auto-deployer (fail-open): %s",
                _bt_wire_err,
            )

        # 0A-2: Inject auto-deployer into evolution_routes for B13 auto-apply on evolution completion.
        # 0A-2：注入自動部署器到 evolution_routes，使進化完成後自動應用最優參數（B13 閉環）。
        # Paper/demo mode: no confirmation needed (per Operator decision in Batch 9).
        # Paper/demo 模式：免確認（依 Batch 9 Operator 決策）。
        try:
            from . import evolution_routes as _evolution_routes
            _evolution_routes.set_auto_deployer(result.auto_deployer)
            logger.info(
                "0A-2: Auto-deployer injected into evolution_routes for B13 auto-apply / "
                "自動部署器已注入 evolution_routes 供 B13 進化結果自動應用"
            )
        except Exception as _evo_wire_err:
            logger.warning(
                "0A-2: Could not wire auto-deployer to evolution_routes (fail-open): %s",
                _evo_wire_err,
            )

        logger.info("Market scanner + auto-deployer started / 市场扫描器+自动部署器已启动")
    except Exception as e:
        result.market_scanner = None
        result.auto_deployer = None
        logger.warning("Market scanner not available: %s", e)

    # ── ScoutWorker: 30-minute periodic intel injection into Strategist chain ──
    # ScoutWorker：每 30 分鐘定時掃描並通過 ScoutAgent → MessageBus 向策略師注入情報
    # This complements MarketScanner's own 5-minute loop (which feeds AUTO_DEPLOYER).
    # ScoutWorker 補充 MarketScanner 自身的 5 分鐘循環（後者只饋送 AUTO_DEPLOYER）。
    # ScoutWorker covers the Scout→Strategist intel pipeline for AI-driven analysis.
    # ScoutWorker 覆蓋 Scout→策略師情報管線，供 AI 驅動的策略分析使用。
    try:
        from .scout_worker import ScoutWorker as _ScoutWorkerClass

        def _make_scout_scan_fn():
            """
            Build a scan function that runs one full scan and injects intel via ScoutAgent.
            構建掃描函數：執行一次完整掃描，並通過 ScoutAgent.produce_intel() 注入情報。

            Captures the scanner / agent singletons created above; if either is
            unavailable returns None (fail-open for scout intel).
            捕獲上面建好的 scanner / agent singleton；若任一不可用，返回
            None（情報注入 fail-open，不影響主程序）。
            """
            _ms = result.market_scanner
            _sa = scout_agent
            if _ms is None or _sa is None:
                return None

            def _scan_and_produce_intel() -> None:
                """
                Execute one scan cycle and push top opportunities as Scout intel.
                執行一次掃描週期，將頂部機會推送為 Scout 情報供策略師分析。

                Fail-open: exceptions are caught in ScoutWorker._run_loop(), so
                this function only needs to raise on genuine failures.
                Fail-open：ScoutWorker._run_loop() 已捕獲異常，此函數只需在真正失敗時拋出。
                """
                opportunities = _ms.scan()
                if not opportunities:
                    logger.debug(
                        "ScoutWorker: scan returned no opportunities / 掃描未返回機會，跳過情報注入"
                    )
                    return
                # Take top-5 opportunities by score to avoid intel flooding.
                # 取評分最高的前 5 個機會，避免情報洪泛策略師消息隊列。
                top = sorted(opportunities, key=lambda o: getattr(o, "score", 0.0), reverse=True)[:5]
                symbols = [getattr(o, "symbol", str(o)) for o in top]
                summary = ", ".join(
                    f"{getattr(o, 'symbol', '?')}({getattr(o, 'score', 0.0):.2f})"
                    for o in top
                )
                _sa.produce_intel(
                    source="ScoutWorker",
                    content=f"30-min periodic scan top opportunities: {summary}",
                    symbols=symbols,
                    relevance_score=0.6,
                    freshness_seconds=0,
                    metadata={"trigger": "scout_worker_30min", "total_opportunities": len(opportunities)},
                )
                logger.info(
                    "ScoutWorker: intel produced for %d symbols (top 5 of %d opportunities) "
                    "/ ScoutWorker：已為 %d 個幣種生成情報（%d 個機會中的前 5）",
                    len(symbols), len(opportunities), len(symbols), len(opportunities),
                )

            return _scan_and_produce_intel

        _scout_scan_fn = _make_scout_scan_fn()
        if _scout_scan_fn is not None:
            result.scout_worker = _ScoutWorkerClass(scan_fn=_scout_scan_fn)
            result.scout_worker.start()
            logger.info(
                "ScoutWorker initialized and started (30-min intel injection) "
                "/ ScoutWorker 已初始化並啟動（30 分鐘情報注入）"
            )
        else:
            logger.warning(
                "ScoutWorker not started: MARKET_SCANNER or SCOUT_AGENT unavailable "
                "/ ScoutWorker 未啟動：MARKET_SCANNER 或 SCOUT_AGENT 不可用"
            )
    except Exception as _scout_worker_exc:
        # Scout intel injection failure is non-fatal; main pipeline continues.
        # Scout 情報注入失敗不影響主程序；繼續運行。
        logger.warning(
            "ScoutWorker initialization failed (non-fatal): %s "
            "/ ScoutWorker 初始化失敗（非致命）：%s",
            type(_scout_worker_exc).__name__,
            _scout_worker_exc,
        )
        result.scout_worker = None

    # --- Wire ScoutAgent + MessageBus into scout_routes ---
    try:
        from . import scout_routes
        scout_routes.set_scout_agent(scout_agent)
        scout_routes.set_message_bus(message_bus)
        # Batch 9: Wire PerceptionPlane into scout_routes for cognitive level marking
        # Batch 9：将感知平面接入 scout 路由用于认知级别标记
        try:
            from .paper_trading_routes import PERCEPTION_PLANE as _PP_FOR_SCOUT
            if _PP_FOR_SCOUT is not None:
                scout_routes.set_perception_plane(_PP_FOR_SCOUT)
        except ImportError:
            pass
        logger.info("ScoutAgent + MessageBus (+ PerceptionPlane) wired to scout_routes / Scout 代理 + 消息总线（+ 感知平面）已接入 scout 路由")
    except Exception as e:
        logger.warning("Could not wire scout_routes: %s", e)

    # ── E1: Auto-Observation Writer (writes observations after each round-trip trade) ──
    # E1：自动观察写入器（每轮交易结束后写入观察）
    # DEAD-PY-2: PIPELINE_BRIDGE = None → observation writer no longer wired.
    # The closure remains defined for grep stability / future re-enablement.
    # DEAD-PY-2：PIPELINE_BRIDGE = None → observation writer 已不再 wire；
    # closure 定義保留供 grep stability / 未來重啟。
    try:
        from . import main_legacy as _ml

        def _write_auto_observation(  # noqa: F841 — kept for grep / future use
            symbol: str,
            strategy_name: str,
            close_pnl: float,
            hold_ms: int,
            regime: str,
        ) -> None:
            """Write a trading observation to the learning state after each round-trip."""
            try:
                outcome = "win" if close_pnl > 0 else ("loss" if close_pnl < 0 else "breakeven")
                hold_h = hold_ms / 3_600_000
                obs_text = (
                    f"[Auto] {strategy_name} on {symbol}: {outcome} "
                    f"PnL={close_pnl:+.4f} USDT, hold={hold_h:.2f}h, regime={regime}"
                )

                def mutator(state):
                    import uuid
                    ts = int(_time_mod.time() * 1000)
                    record = {
                        "observation_id": f"auto:{uuid.uuid4().hex[:12]}",
                        "observation_ts_ms": ts,
                        "observation_type": "trade_outcome",
                        "confidence_level": "fact",
                        "title": f"Trade: {strategy_name}/{symbol} → {outcome}",
                        "detail": obs_text,
                        "related_hypothesis_id": None,
                        "tags": ["auto", "trade", strategy_name, symbol, outcome, regime],
                    }
                    ls = state.setdefault("learning_state", {})
                    ls.setdefault("observation_summary", {}).setdefault("last_observation_ts_ms", None)
                    ls["observation_summary"]["last_observation_ts_ms"] = ts
                    ls.setdefault("records", {}).setdefault("observations", []).append(record)
                    return state

                _ml.STORE.mutate(mutator)
            except Exception:
                pass  # non-fatal, best-effort

        # DEAD-PY-2: observation writer no longer injected into PipelineBridge (PIPELINE_BRIDGE = None).
        pass
    except Exception as _e1_e:
        logger.info("Auto-observation writer not wired: %s", _e1_e)

    return result


__all__ = [
    "ScannerWiringResult",
    "wire_market_scanner_and_workers",
]
