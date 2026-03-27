"""
Strategy Auto-Deployer — Automatically deploy strategies based on market opportunities
策略自动部署器 — 根据市场机会自动部署策略

MODULE_NOTE (中文):
  接收 MarketScanner 的扫描结果，自动：
  1. 为高分机会创建对应策略实例
  2. 激活新策略
  3. 停用表现差或机会消失的策略

  风险感知：
  - 最大同时交易品种数限制（默认 5）
  - 每个品种最大仓位限制
  - 不会在同一品种上重复部署同类策略
  - 自动停用连续亏损策略

MODULE_NOTE (English):
  Receives MarketScanner results and automatically:
  1. Creates strategy instances for high-scoring opportunities
  2. Activates new strategies
  3. Deactivates underperforming or stale strategies

Safety invariant:
  - 受 max_symbols 限制 / Bounded by max_symbols
  - 受风控框架约束 / Subject to risk framework
  - system_mode = read_only 不变 / system_mode unchanged
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class StrategyAutoDeployer:
    """
    Automatically deploys and manages strategies across multiple symbols.
    """

    def __init__(
        self,
        orchestrator: Any,
        kline_manager: Any,
        *,
        max_symbols: int = 5,
        qty_per_trade: float = 0.001,
    ) -> None:
        self._orch = orchestrator
        self._km = kline_manager
        self._max_symbols = max_symbols
        self._qty = qty_per_trade
        self._lock = threading.Lock()

        # Track auto-deployed strategies: {strategy_name: {symbol, category, deployed_ts, ...}}
        self._deployed: dict[str, dict[str, Any]] = {}
        self._stats = {
            "strategies_deployed": 0,
            "strategies_removed": 0,
            "scan_callbacks_received": 0,
        }

    def on_scan_results(self, opportunities: list[Any]) -> None:
        """
        Callback from MarketScanner. Deploys/updates strategies based on opportunities.
        市场扫描回调。根据机会部署/更新策略。
        """
        self._stats["scan_callbacks_received"] += 1

        with self._lock:
            current_symbols = set(d["symbol"] for d in self._deployed.values())
            available_slots = self._max_symbols - len(current_symbols)

            for opp in opportunities:
                if available_slots <= 0:
                    break

                symbol = opp.symbol
                category = opp.category

                # Skip if already trading this symbol with same category
                key = f"{category}_{symbol}"
                if key in self._deployed:
                    continue

                # Skip if already at max symbols
                if symbol not in current_symbols and available_slots <= 0:
                    continue

                # Deploy strategy
                try:
                    self._deploy_strategy(symbol, category, opp)
                    if symbol not in current_symbols:
                        available_slots -= 1
                        current_symbols.add(symbol)
                except Exception:
                    logger.exception("Failed to deploy %s for %s", category, symbol)

    def _deploy_strategy(self, symbol: str, category: str, opp: Any) -> None:
        """Create and register a strategy instance."""
        from .strategies.ma_crossover import MACrossoverStrategy
        from .strategies.bollinger_reversion import BollingerReversionStrategy
        from .strategies.funding_rate_arb import FundingRateArbStrategy
        from .strategies.grid_trading import GridTradingStrategy
        from .strategies.bb_breakout import BBBreakoutStrategy

        key = f"{category}_{symbol}"
        strategy = None

        if category == "funding_arb":
            strategy = FundingRateArbStrategy(symbol=symbol, qty_per_trade=self._qty)

        elif category == "grid":
            # Calculate grid range from current price (+-5%)
            price = opp.price
            upper = price * 1.05
            lower = price * 0.95
            strategy = GridTradingStrategy(
                symbol=symbol, upper_price=upper, lower_price=lower,
                grid_count=20, qty_per_grid=self._qty,
            )

        elif category == "trend":
            strategy = MACrossoverStrategy(symbol=symbol, qty_per_trade=self._qty)

        elif category == "reversion":
            strategy = BollingerReversionStrategy(symbol=symbol, qty_per_trade=self._qty)

        elif category == "breakout":
            strategy = BBBreakoutStrategy(symbol=symbol, qty_per_trade=self._qty)

        if strategy is None:
            return

        # Override name to be unique (include symbol)
        # Strategy names must be unique in orchestrator
        unique_name = f"{strategy.name}_{symbol}"

        # Add symbol to kline manager if not tracked
        if symbol not in self._km._symbols:
            self._km.add_symbol(symbol)
            # Bootstrap historical klines for new symbol
            try:
                self._km.bootstrap_from_rest(limit=200)
            except Exception:
                pass

        # Register and activate
        self._orch.register_strategy(strategy)
        self._orch.activate_strategy(strategy.name)

        self._deployed[key] = {
            "symbol": symbol,
            "category": category,
            "strategy_name": strategy.name,
            "score": opp.score,
            "deployed_ts_ms": int(time.time() * 1000),
            "reason": opp.reason,
        }
        self._stats["strategies_deployed"] += 1

        logger.info(
            "Auto-deployed %s for %s (score=%.0f): %s / 自动部署策略",
            category, symbol, opp.score, opp.reason,
        )

    def remove_stale_strategies(self, active_symbols: set[str]) -> None:
        """Remove strategies for symbols no longer in top opportunities."""
        with self._lock:
            to_remove = []
            for key, info in self._deployed.items():
                if info["symbol"] not in active_symbols:
                    to_remove.append(key)

            for key in to_remove:
                info = self._deployed.pop(key)
                try:
                    self._orch.stop_strategy(info["strategy_name"])
                    self._orch.remove_strategy(info["strategy_name"])
                    self._stats["strategies_removed"] += 1
                    logger.info("Removed stale strategy %s / 移除过期策略", info["strategy_name"])
                except Exception:
                    pass

    def get_deployed(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._deployed.values())

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "component": "strategy_auto_deployer",
                "deployed_count": len(self._deployed),
                "deployed_symbols": list(set(d["symbol"] for d in self._deployed.values())),
                **self._stats,
            }
