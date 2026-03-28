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
        paper_engine: Any = None,
        *,
        max_symbols: int = 5,
        risk_per_trade_pct: float = 1.0,  # Risk 1% of balance per trade
        min_qty_usdt: float = 10.0,       # Minimum $10 per trade
        max_qty_pct: float = 10.0,        # Max 10% of balance per single trade
        market_feed_add_fn: Any = None,   # Optional: callable(symbol) to subscribe market feed
    ) -> None:
        self._orch = orchestrator
        self._km = kline_manager
        self._engine = paper_engine
        self._max_symbols = max_symbols
        self._risk_pct = risk_per_trade_pct
        self._min_qty_usdt = min_qty_usdt
        self._max_qty_pct = max_qty_pct
        self._market_feed_add_fn = market_feed_add_fn
        self._lock = threading.Lock()

        # Track auto-deployed strategies: {strategy_name: {symbol, category, deployed_ts, ...}}
        self._deployed: dict[str, dict[str, Any]] = {}
        # G1: consecutive loss tracking per strategy / G1：每策略连续亏损追踪
        self._consecutive_losses: dict[str, int] = {}
        self._MAX_CONSECUTIVE_LOSSES = 10  # auto-pause after 10 consecutive losses
        self._stats = {
            "strategies_deployed": 0,
            "strategies_removed": 0,
            "scan_callbacks_received": 0,
            "strategies_auto_paused": 0,
        }

    def on_scan_results(self, opportunities: list[Any]) -> None:
        """
        Callback from MarketScanner. Deploys/updates strategies based on opportunities.
        市场扫描回调。根据机会部署/更新策略。
        """
        with self._lock:
            self._stats["scan_callbacks_received"] += 1
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

                # Deploy strategy
                try:
                    self._deploy_strategy(symbol, category, opp)
                    if symbol not in current_symbols:
                        available_slots -= 1
                        current_symbols.add(symbol)
                except Exception:
                    logger.exception("Failed to deploy %s for %s", category, symbol)

    def _compute_qty(self, symbol: str, price: float, score: float) -> float:
        """
        Compute position size based on balance, opportunity score, and risk.
        根据余额、机会评分和风险计算仓位大小。

        Logic:
        - Base: risk_per_trade_pct of account balance
        - Score bonus: higher score → larger allocation (up to 2x)
        - Divided by active symbol count (portfolio balance)
        - Clamped to min/max limits
        """
        # Get current balance
        balance = 10000.0  # Default
        if self._engine:
            try:
                state = self._engine.get_state()
                sess = state.get("session", {})
                balance = sess.get("current_paper_balance_usdt", 10000.0)
            except Exception:
                pass

        if balance <= 0 or price <= 0:
            return self._min_qty_usdt / max(price, 1)

        # Base allocation: risk% of balance
        base_usdt = balance * (self._risk_pct / 100.0)

        # Score multiplier: score 50→1.0x, score 100→1.5x, score 200→2.0x
        score_mult = min(2.0, 0.5 + score / 200.0)
        allocated_usdt = base_usdt * score_mult

        # Divide by number of active symbols (portfolio balance)
        # Include the symbol being deployed to correctly size allocation.
        # / 包含即将部署的品种，正确计算仓位分配。
        active_count = max(1, len(set(d["symbol"] for d in self._deployed.values()) | {symbol}))
        per_symbol_usdt = allocated_usdt / active_count

        # Clamp to limits
        per_symbol_usdt = max(self._min_qty_usdt, per_symbol_usdt)
        max_usdt = balance * (self._max_qty_pct / 100.0)
        per_symbol_usdt = min(per_symbol_usdt, max_usdt)

        # Convert to asset quantity
        qty = per_symbol_usdt / price
        qty = round(qty, 6)

        logger.info(
            "Position sizing: %s balance=$%.0f score=%.0f → $%.1f (%.6f units) / 仓位计算",
            symbol, balance, score, per_symbol_usdt, qty,
        )
        return qty

    def _deploy_strategy(self, symbol: str, category: str, opp: Any) -> None:
        """Create and register a strategy instance with intelligent sizing."""
        from .strategies.ma_crossover import MACrossoverStrategy
        from .strategies.bollinger_reversion import BollingerReversionStrategy
        from .strategies.funding_rate_arb import FundingRateArbStrategy
        from .strategies.grid_trading import GridTradingStrategy
        from .strategies.bb_breakout import BBBreakoutStrategy

        key = f"{category}_{symbol}"
        strategy = None

        # Compute intelligent position size
        qty = self._compute_qty(opp.symbol, opp.price, opp.score)

        if category == "funding_arb":
            strategy = FundingRateArbStrategy(symbol=symbol, qty_per_trade=qty)

        elif category == "grid":
            # Calculate grid range from current price (+-5%)
            price = opp.price
            upper = price * 1.05
            lower = price * 0.95
            strategy = GridTradingStrategy(
                symbol=symbol, upper_price=upper, lower_price=lower,
                grid_count=20, qty_per_grid=qty,
            )

        elif category == "trend":
            # 过滤 pump/dump 币：24小时涨跌幅超过 40% 的币不适合 MA Crossover
            # 这类币往往是暴拉暴跌，MA 信号会被反复震仓
            # Filter pump/dump coins: abs daily change > 40% is too noisy for MA Crossover
            if abs(getattr(opp, "price_change_pct_24h", 0.0)) > 40.0:
                logger.info(
                    "Skipping trend deploy for %s: extreme daily change=%.1f%% (pump/dump risk) / 跳过：日涨跌幅过大",
                    symbol, opp.price_change_pct_24h,
                )
                return
            # 提高置信度阈值：auto-deploy 使用 0.55，避免追噪声信号
            # Raise confidence threshold for auto-deployed strategies to reduce noise trading
            strategy = MACrossoverStrategy(symbol=symbol, qty_per_trade=qty, min_confidence=0.55)

        elif category == "reversion":
            strategy = BollingerReversionStrategy(symbol=symbol, qty_per_trade=qty)

        elif category == "breakout":
            strategy = BBBreakoutStrategy(symbol=symbol, qty_per_trade=qty)

        if strategy is None:
            return

        # Unique registration key includes symbol to prevent name collision
        # 唯一注册键包含 symbol 以防止名称冲突（R1 fix）
        unique_name = f"{strategy.name}_{symbol}"

        # Add symbol to kline manager if not tracked (use public API)
        # 使用公开 API 检查是否已追踪
        new_symbol = symbol not in self._km.get_tracked_symbols()
        if new_symbol:
            self._km.add_symbol(symbol)
            # Bootstrap historical klines for new symbol
            try:
                self._km.bootstrap_from_rest(limit=200)
            except Exception:
                pass
            # Subscribe market feed so live prices flow in for this symbol
            # 订阅行情流，让该品种的实时价格数据流入
            if self._market_feed_add_fn is not None:
                try:
                    self._market_feed_add_fn(symbol)
                    logger.info("Market feed subscribed to %s / 行情流已订阅 %s", symbol, symbol)
                except Exception:
                    logger.debug("Market feed add skipped for %s (feed may not be running yet)", symbol)

        # Register with unique name and activate
        self._orch.register_strategy(strategy, name=unique_name)
        self._orch.activate_strategy(unique_name)

        # R2 fix: trigger initial indicator computation for newly added symbols
        # so strategies don't have to wait for the next kline close.
        # 为新添加的 symbol 触发初始指标计算，策略无需等待下一根 K线闭合。
        if new_symbol:
            for tf in self._km.get_timeframes():
                try:
                    self._orch.compute_indicators(symbol, tf)
                except Exception:
                    logger.debug(
                        "Initial indicator computation skipped for %s:%s / 初始指标计算跳过",
                        symbol, tf,
                    )

        self._deployed[key] = {
            "symbol": symbol,
            "category": category,
            "strategy_name": unique_name,
            "score": opp.score,
            "deployed_ts_ms": int(time.time() * 1000),
            "reason": opp.reason,
        }
        self._stats["strategies_deployed"] += 1

        logger.info(
            "Auto-deployed %s for %s (score=%.0f): %s / 自动部署策略",
            category, symbol, opp.score, opp.reason,
        )

    def notify_fill(self, strategy_name: str, fill: dict, is_open: bool) -> None:
        """
        Route a confirmed fill back to the originating strategy's on_fill callback.
        This prevents position state drift caused by intent-first (optimistic) updates.
        将已确认的成交路由回原始策略的 on_fill 回调，防止仓位状态因意图先行更新而漂移。
        """
        try:
            with self._lock:
                strategy = self._orch._strategies.get(strategy_name)
            if strategy is not None:
                strategy.on_fill(fill, is_open)
        except Exception:
            logger.debug("notify_fill error for %s (non-fatal)", strategy_name)

    def on_trade_result(self, strategy_name: str, close_pnl: float) -> None:
        """
        G1: Called after each round-trip trade to track consecutive losses.
        Auto-pause the strategy after MAX_CONSECUTIVE_LOSSES in a row.
        G1：每轮交易后调用以追踪连续亏损。
        连续亏损超过阈值后自动暂停策略。
        """
        with self._lock:
            if close_pnl < 0:
                self._consecutive_losses[strategy_name] = self._consecutive_losses.get(strategy_name, 0) + 1
                losses = self._consecutive_losses[strategy_name]
                logger.info(
                    "Strategy %s consecutive losses: %d / 策略连续亏损: %d",
                    strategy_name, losses, losses,
                )
                if losses >= self._MAX_CONSECUTIVE_LOSSES:
                    # Auto-pause: strategy is losing consistently, stop deploying it
                    # 自动暂停：策略持续亏损，停止其交易
                    try:
                        self._orch.pause_strategy(strategy_name)
                        self._stats["strategies_auto_paused"] += 1
                        logger.warning(
                            "AUTO-PAUSED strategy %s after %d consecutive losses / "
                            "自动暂停策略 %s，连续亏损 %d 次",
                            strategy_name, losses, strategy_name, losses,
                        )
                    except Exception:
                        logger.debug("Could not pause strategy %s (may not be registered)", strategy_name)
            else:
                # Win or break-even: reset consecutive loss counter
                # 盈利或平局：重置连续亏损计数器
                self._consecutive_losses.pop(strategy_name, None)

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
