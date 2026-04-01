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
        max_symbols: int = 25,
        risk_per_trade_pct: float = 3.0,  # Risk 3% of balance per trade (max loss)
        min_qty_usdt: float = 10.0,       # Minimum $10 per trade
        max_qty_pct: float = 10.0,        # Max 10% of balance per single trade
        market_feed_add_fn: Any = None,   # Optional: callable(symbol) to subscribe market feed
        pinned_symbols: list[str] | None = None,  # Always-deployed symbols (e.g. BTCUSDT, ETHUSDT)
    ) -> None:
        self._orch = orchestrator
        self._km = kline_manager
        self._engine = paper_engine
        self._max_symbols = max_symbols
        self._risk_pct = risk_per_trade_pct
        self._min_qty_usdt = min_qty_usdt
        self._max_qty_pct = max_qty_pct
        self._market_feed_add_fn = market_feed_add_fn
        # Pinned symbols: always deployed, never evicted by rebalancer.
        # 釘選幣種：始終部署，不會被智能再平衡驅逐。
        # These are the most liquid and competitive pairs — valuable for learning/evolution.
        # 這些是最活躍、競爭最激烈的交易對 — 對學習和進化極有價值。
        self._pinned_symbols: set[str] = set(pinned_symbols or [])
        self._pinned_deployed: bool = False  # Track if pinned symbols have been deployed
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
            "rebalance_triggered": 0,
            "rebalance_closed": 0,
        }
        # Wave 7a 方案 B：PipelineBridge 引用，用於登記 symbol-category 映射。
        # Wave 7a Plan B: PipelineBridge reference for registering symbol-category mappings.
        # Optional; if None, category registration is silently skipped (non-blocking).
        self._pipeline_bridge: Any = None

    # ── Portfolio position evaluation ──

    def _get_open_positions(self) -> dict[str, Any]:
        """Get current open positions from paper engine / 從紙上引擎獲取當前持倉"""
        if not self._engine:
            return {}
        try:
            state = self._engine.get_state()
            return state.get("positions", {})
        except Exception:
            return {}

    def _score_existing_position(self, symbol: str, pos: dict) -> float:
        """
        Score an existing position on how worthwhile it is to keep (0-100).
        評估現有持倉的保留價值（0-100分）。

        High score = keep it. Low score = candidate for closing.
        Factors:
        - Unrealized PnL direction and magnitude
        - How long it's been held (stale positions score lower)
        - Consecutive losses on this strategy
        """
        score = 50.0  # neutral baseline

        # 1. Unrealized PnL impact (most important factor)
        unrealized_pnl = pos.get("unrealized_pnl", 0.0)
        notional = pos.get("qty", 0) * pos.get("avg_entry_price", 1)
        if notional > 0:
            pnl_pct = (unrealized_pnl / notional) * 100
        else:
            pnl_pct = 0.0

        if pnl_pct > 2.0:
            # Strong profit — high keep value but diminishing returns above 3%
            score += min(30.0, pnl_pct * 5)
        elif pnl_pct > 0:
            # Small profit — moderate keep value
            score += pnl_pct * 10
        elif pnl_pct > -2.0:
            # Small loss — still has potential
            score += pnl_pct * 8  # penalty proportional to loss
        else:
            # Significant loss (> -2%) — low keep value, unlikely to recover
            score += max(-40.0, pnl_pct * 10)

        # 2. Hold time penalty: positions held > 4h get progressively lower scores
        entry_ts = pos.get("created_ts_ms", pos.get("updated_ts_ms", 0))
        if entry_ts:
            hold_hours = (time.time() * 1000 - entry_ts) / 3_600_000
            if hold_hours > 4:
                score -= min(15.0, (hold_hours - 4) * 1.5)

        # 3. Consecutive loss penalty from strategy tracking
        for key, info in self._deployed.items():
            if info["symbol"] == symbol:
                strategy_name = info.get("strategy_name", "")
                losses = self._consecutive_losses.get(strategy_name, 0)
                score -= losses * 3  # each consecutive loss reduces keep-score
                break

        return max(0.0, min(100.0, score))

    def _find_weakest_position(self, exclude_symbols: set[str] | None = None) -> tuple[str | None, float]:
        """
        Find the position with lowest keep-score that could be closed.
        找到保留價值最低的持倉（可被關閉以騰出資金）。

        Returns: (symbol, keep_score) or (None, 100.0) if no candidates.
        """
        positions = self._get_open_positions()
        if not positions:
            return None, 100.0

        worst_symbol = None
        worst_score = 100.0

        for symbol, pos in positions.items():
            if exclude_symbols and symbol in exclude_symbols:
                continue
            # Pinned symbols are never evicted by rebalancer
            # 釘選幣種不會被智能再平衡驅逐
            if symbol in self._pinned_symbols:
                continue
            keep_score = self._score_existing_position(symbol, pos)
            if keep_score < worst_score:
                worst_score = keep_score
                worst_symbol = symbol

        return worst_symbol, worst_score

    def _close_position_for_rebalance(self, symbol: str) -> bool:
        """
        Close a position by submitting a counter-side market order via paper engine.
        通過提交反向市價單來平倉。

        Returns True if the close order was submitted successfully.
        """
        positions = self._get_open_positions()
        pos = positions.get(symbol)
        if not pos:
            return False

        close_side = "Sell" if pos["side"] == "Buy" else "Buy"
        close_qty = pos.get("qty", 0)
        if close_qty <= 0:
            return False

        try:
            # Get current market price for submission
            state = self._engine.get_state()
            # Build market_prices from positions' updated prices or fall back
            market_prices = {}
            for s, p in state.get("positions", {}).items():
                if "mark_price" in p:
                    market_prices[s] = p["mark_price"]

            result = self._engine.submit_order(
                symbol=symbol,
                side=close_side,
                order_type="market",
                qty=close_qty,
                market_prices=market_prices,
            )
            rejected = result.get("rejected_reason") if isinstance(result, dict) else None
            if rejected:
                logger.warning(
                    "Rebalance close rejected: %s reason=%s / 再平衡平倉被拒",
                    symbol, rejected,
                )
                return False

            logger.info(
                "Rebalance: closed %s %s qty=%.6f to free capital / 再平衡：平倉 %s 以釋放資金",
                symbol, close_side, close_qty, symbol,
            )

            # Remove the deployed strategy for this symbol
            to_remove = [k for k, v in self._deployed.items() if v["symbol"] == symbol]
            for k in to_remove:
                info = self._deployed.pop(k)
                try:
                    self._orch.stop_strategy(info["strategy_name"])
                    self._orch.remove_strategy(info["strategy_name"])
                except Exception:
                    pass

            self._stats["strategies_removed"] += 1
            self._stats["rebalance_closed"] += 1
            return True
        except Exception:
            logger.exception("Rebalance close failed for %s / 再平衡平倉失敗", symbol)
            return False

    # ── Main scan callback (with smart rebalancing) ──

    def on_scan_results(self, opportunities: list[Any]) -> None:
        """
        Callback from MarketScanner. Deploys/updates strategies based on opportunities.
        市场扫描回调。根据机会部署/更新策略。

        Smart rebalancing: when all slots are full and a high-score opportunity appears,
        evaluate existing positions and close the weakest one to make room.
        智能再平衡：當所有槽位已滿且出現高分機會時，評估現有持倉，
        關閉最弱的持倉以騰出空間。
        """
        with self._lock:
            self._stats["scan_callbacks_received"] += 1

            # ── Deploy pinned symbols on first scan (BTCUSDT, ETHUSDT etc) ──
            # 首次掃描時部署釘選幣種（BTC、ETH 等最活躍交易對）
            # Pinned symbols use MA_Crossover as default strategy (trend-following).
            # Condition: only deploy if not already deployed. Scanner conditions still
            # apply at order time (H0 Gate, Guardian) — pinned means "always monitor
            # and attempt to trade", not "force trade regardless of conditions".
            # 釘選意味著「始終監控並嘗試交易」，不是「無視條件強行交易」。
            if not self._pinned_deployed and self._pinned_symbols:
                for psym in self._pinned_symbols:
                    key = f"trend_{psym}"
                    if key not in self._deployed:
                        from dataclasses import dataclass as _dc, field as _fld
                        @_dc
                        class _PinnedOpp:
                            symbol: str = psym
                            score: float = 50.0
                            category: str = "trend"
                            price: float = 0.0
                            price_change_pct_24h: float = 0.0
                            api_category: str = "linear"
                            reason: str = "Pinned symbol (always monitor)"
                        # Fetch current price for qty calculation
                        _price = 0.0
                        if self._engine:
                            try:
                                _state = self._engine.get_state()
                                _feed = _state.get("market_feed", {})
                                _price = _feed.get(psym, 0.0)
                            except Exception:
                                pass
                        _popp = _PinnedOpp(price=_price if _price > 0 else 1.0)
                        self._deploy_strategy(psym, "trend", _popp)
                        logger.info(
                            "Pinned symbol deployed: %s (always monitor) / 釘選幣種已部署: %s",
                            psym, psym,
                        )
                self._pinned_deployed = True

            current_symbols = set(d["symbol"] for d in self._deployed.values())
            available_slots = self._max_symbols - len(current_symbols)

            for opp in opportunities:
                symbol = opp.symbol
                category = opp.category

                # Skip if already trading this symbol with same category
                key = f"{category}_{symbol}"
                if key in self._deployed:
                    continue

                if available_slots <= 0:
                    # ── Smart rebalancing: slots full, try to replace weak positions ──
                    # Only rebalance for high-quality opportunities (score >= 70)
                    if opp.score < 70:
                        continue

                    weakest_sym, weakest_score = self._find_weakest_position(
                        exclude_symbols={symbol}
                    )
                    if weakest_sym is None:
                        continue

                    # Only replace if new opportunity is significantly better
                    # New opp score (0-200 range) vs keep-score (0-100 range)
                    # Normalize: opp.score/2 gives 0-100 comparable range
                    new_score_normalized = opp.score / 2.0
                    if new_score_normalized <= weakest_score + 15:
                        # New opportunity isn't compelling enough to justify closing
                        logger.debug(
                            "Rebalance skip: %s (score %.0f) not enough better than %s (keep %.0f) / "
                            "再平衡跳過：新機會不夠優",
                            symbol, opp.score, weakest_sym, weakest_score,
                        )
                        continue

                    self._stats["rebalance_triggered"] += 1
                    logger.info(
                        "Rebalance trigger: closing %s (keep=%.0f) for %s (opp=%.0f) / "
                        "再平衡觸發：關閉弱倉以部署新機會",
                        weakest_sym, weakest_score, symbol, opp.score,
                    )
                    if self._close_position_for_rebalance(weakest_sym):
                        current_symbols.discard(weakest_sym)
                        available_slots += 1
                    else:
                        continue

                # Deploy strategy
                try:
                    self._deploy_strategy(symbol, category, opp)
                    if symbol not in current_symbols:
                        available_slots -= 1
                        current_symbols.add(symbol)
                except Exception:
                    logger.exception("Failed to deploy %s for %s", category, symbol)

    def _get_balance(self) -> float:
        """Read current balance from paper engine / 從紙上交易引擎讀取當前餘額"""
        if self._engine:
            try:
                state = self._engine.get_state()
                return state.get("session", {}).get("current_paper_balance_usdt", 10000.0)
            except Exception:
                pass
        return 10000.0

    def _compute_qty(self, symbol: str, price: float, score: float) -> float:
        """
        Compute position size based on balance, opportunity score, and risk.
        根据余额、机会评分和风险计算仓位大小。

        Logic:
        - Base: risk_per_trade_pct of account balance (= max acceptable loss per trade)
        - With 5% hard stop, position_notional = risk_amount / stop_pct
        - Score bonus: higher score → larger allocation (up to 2x)
        - Clamped to min/max limits
        - NOT divided by active symbol count (each trade sized independently)
        """
        balance = self._get_balance()

        if balance <= 0 or price <= 0:
            return self._min_qty_usdt / max(price, 1)

        # risk_per_trade_pct = max loss as % of balance if stop-loss hits
        # With 5% hard stop: notional = risk_amount / 0.05
        # E.g. 3% risk on $100k = $3k risk → $3k / 0.05 = $60k notional (capped by max_qty_pct)
        risk_amount = balance * (self._risk_pct / 100.0)
        hard_stop_pct = 0.05  # 5% hard stop
        base_usdt = risk_amount / hard_stop_pct

        # Score multiplier: score 50→1.0x, score 100→1.5x, score 200→2.0x
        score_mult = min(2.0, 0.5 + score / 200.0)
        allocated_usdt = base_usdt * score_mult

        # Clamp to limits (no division by active count — each trade sized independently)
        allocated_usdt = max(self._min_qty_usdt, allocated_usdt)
        max_usdt = balance * (self._max_qty_pct / 100.0)
        allocated_usdt = min(allocated_usdt, max_usdt)

        # Convert to asset quantity
        qty = allocated_usdt / price
        qty = round(qty, 6)

        logger.info(
            "Position sizing: %s balance=$%.0f score=%.0f → $%.1f (%.6f units) / 仓位计算",
            symbol, balance, score, allocated_usdt, qty,
        )
        return qty

    def compute_dynamic_qty(self, symbol: str, price: float) -> float:
        """
        Recompute qty at order submission time using current balance.
        在訂單提交時根據當前餘額重新計算倉位大小。

        Called by PipelineBridge before submitting each order, ensuring
        position sizes reflect the latest account state.
        """
        # Look up the deployed strategy's original score, or use default
        score = 50.0  # default moderate score
        with self._lock:
            for info in self._deployed.values():
                if info["symbol"] == symbol:
                    score = info.get("score", 50.0)
                    break
        return self._compute_qty(symbol, price, score)

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

        # Inject api_category into strategy default metadata so all intents carry it.
        # Pipeline bridge reads intent.metadata["category"] to route to correct Bybit API.
        # 注入 api_category 到策略預設元數據，所有 intent 自動攜帶品類信息。
        api_category = getattr(opp, "api_category", "linear")
        if api_category != "linear":
            strategy._default_metadata["category"] = api_category

        # Wave 7a 方案 B：通知 PipelineBridge 登記此 symbol 的 category。
        # Wave 7a Plan B: notify PipelineBridge to register this symbol's category for
        # accurate downstream kline/funding queries. Always register (even linear) so the
        # bridge knows this symbol was explicitly deployed and won't emit a "no category" warning.
        if self._pipeline_bridge is not None:
            try:
                self._pipeline_bridge.register_symbol_category(symbol, api_category)
            except Exception as _reg_err:
                # 登記失敗不阻斷部署流程，記錄 warning 即可
                # Registration failure must not block strategy deployment (non-critical)
                logger.warning(
                    "Failed to register symbol category %s→%s with PipelineBridge: %s "
                    "/ 登記 symbol category 失敗（非致命）：%s→%s",
                    symbol, api_category, _reg_err, symbol, api_category,
                )

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

        _reason = getattr(opp, "reason", "") or ""
        self._deployed[key] = {
            "symbol": symbol,
            "category": category,
            "strategy_name": unique_name,
            "score": opp.score,
            "deployed_ts_ms": int(time.time() * 1000),
            "reason": _reason,
        }
        self._stats["strategies_deployed"] += 1

        logger.info(
            "Auto-deployed %s for %s (score=%.0f): %s / 自动部署策略",
            category, symbol, opp.score, _reason,
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

    def set_pipeline_bridge(self, bridge: Any) -> None:
        """
        設置 PipelineBridge 引用，用於在部署策略時登記 symbol-category 映射。
        Set PipelineBridge reference for registering symbol-category mappings on deployment.

        讓 PipelineBridge 的 kline/funding 查詢能取得正確的 category，
        解決 BTCUSDT(spot) 與 BTCUSDT(linear) 無法用命名區分的問題。
        Enables PipelineBridge kline/funding queries to use the correct category,
        fixing the ambiguity where BTCUSDT(spot) and BTCUSDT(linear) share the same name.
        """
        self._pipeline_bridge = bridge

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
