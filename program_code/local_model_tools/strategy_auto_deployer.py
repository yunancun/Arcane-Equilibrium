"""
Strategy Auto-Deployer — Automatically deploy strategies based on market opportunities
策略自动部署器 — 根据市场机会自动部署策略

MODULE_NOTE (中文):
  接收 MarketScanner 的扫描结果，自动：
  1. 为高分机会创建对应策略实例
  2. 激活新策略
  3. 停用表现差或机会消失的策略

  风险感知：
  - 最大同时交易品种数限制（默认 25，与 MarketScanner 对齐）
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

# DEPRECATED(R-07): Strategy dispatch migrated to Rust Orchestrator.
#   Rust: openclaw_engine/src/orchestrator.rs (strategy dispatch, tick fan-out)
#   Stays in Python: deployment decision logic, auto-deploy from evolution/learning, health monitoring, API integration
#   DO NOT DELETE — 15+ importers depend on this module. Remove after R-07 grey-period.

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

# Category priority bonus for deployment ordering.
# Funding arb is delta-neutral (lowest risk) → highest priority.
# 品類優先級加分：funding arb 為 delta-neutral（最低風險）→ 最高優先。
CATEGORY_PRIORITY_BONUS = {
    "funding_arb": 50,
    "grid": 20,
    "reversion": 10,
    "trend": 0,
    "breakout": 0,
}


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
        reserved_slots: dict[str, int] | None = None,  # Reserved slots per api_category
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
        # Reserved slots per api_category — guarantees capacity for underrepresented categories.
        # 每個 api_category 的預留槽位 — 保證少數品類（如 spot）不被多數品類（linear）擠佔。
        # Example: {"spot": 5} reserves 5 slots exclusively for spot strategies.
        self._reserved_slots: dict[str, int] = reserved_slots or {}
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

        # ── Dynamic risk adjustment (Sharpe-based) / 動態風控調整（基於 Sharpe） ──
        # Adjusts risk_per_trade_pct based on portfolio Sharpe ratio.
        # Auto-enables when sufficient trade data is available (>= 50 round trips).
        # 根據組合 Sharpe 比率調整 risk_per_trade_pct。
        # 當交易數據足夠時（>= 50 筆往返）自動啟用。
        self._dynamic_risk_enabled: bool = True  # Master toggle / 主開關
        self._dynamic_risk_active: bool = False   # True when enough data / 數據充足時為 True
        self._base_risk_pct: float = risk_per_trade_pct  # Original value, never mutated / 原始值，不可變
        self._min_trades_for_dynamic: int = 50    # Minimum round trips before activation / 啟用前最少交易數
        self._risk_pct_floor: float = 1.0         # Absolute minimum / 絕對下限
        self._risk_pct_ceil: float = 5.0          # Absolute maximum / 絕對上限
        self._risk_adjust_step: float = 0.5       # Max change per adjustment / 每次最大調幅
        self._last_risk_adjust_ts: float = 0.0    # Timestamp of last adjustment / 上次調整時間
        self._risk_adjust_interval: float = 300.0  # Adjust at most every 5 min / 最多每 5 分鐘調一次

        # 0A-5: Optional BacktestEngine for pre-deployment validation.
        # 0A-5：可選的 BacktestEngine，用於部署前回測驗證。
        # If injected, _deploy_strategy runs a quick backtest on recent klines.
        # Deploy proceeds only if Sharpe >= min threshold (or backtest unavailable → fail-open).
        # 若已注入，_deploy_strategy 在近期 K 線上快速回測，Sharpe >= 閾值才允許部署。
        # 回測不可用時 fail-open（不阻擋部署）。
        self._backtest_engine: Any = None
        self._backtest_min_sharpe: float = 0.0  # 0.0 = deploy any positive expectation
        self._backtest_stats: dict[str, int] = {
            "validations_run": 0,
            "validations_passed": 0,
            "validations_failed": 0,
            "validations_skipped": 0,
        }

    def set_backtest_engine(self, engine: Any, min_sharpe: float = 0.0) -> None:
        """
        0A-5: Inject BacktestEngine for pre-deployment strategy validation.
        注入 BacktestEngine，用於部署前策略回測驗證。

        Args:
            engine: BacktestEngine instance (read-only usage, Principle 7 safe).
            min_sharpe: Minimum Sharpe ratio to allow deployment (default 0.0).
        """
        self._backtest_engine = engine
        self._backtest_min_sharpe = min_sharpe
        logger.info(
            "0A-5: BacktestEngine injected into auto-deployer (min_sharpe=%.2f) / "
            "BacktestEngine 已注入自動部署器（最低 Sharpe=%.2f）",
            min_sharpe, min_sharpe,
        )

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

    # ── B13: Evolution Result Application / B13: 进化结果应用 ──

    def apply_evolution_result(self, result: dict) -> bool:
        """
        Apply evolution engine best parameters to a currently active deployed strategy.
        将进化引擎最优参数应用到当前活跃的已部署策略。

        B13: First connection between EvolutionEngine output and StrategyAutoDeployer.
        This method receives the best parameters from evolution (e.g., best short_window,
        long_window for MA crossover) and updates the deployed strategy's parameters
        if the strategy is currently active.

        B13：EvolutionEngine 输出与 StrategyAutoDeployer 的首次连接。
        接收进化引擎的最优参数（如 MA 交叉的 short_window、long_window），
        若对应策略当前为活跃状态则更新其参数。

        Args:
            result — dict with at least 'strategy_name', 'best_params', 'best_sharpe'.
                     Must come from EvolutionResult.to_dict().
                     至少包含 strategy_name、best_params、best_sharpe 的字典，
                     应来自 EvolutionResult.to_dict()。

        Returns:
            True if parameters were applied to at least one active deployment.
            若参数已成功应用到至少一个活跃部署则返回 True。
        """
        strategy_name = result.get("strategy_name", "")
        best_params = result.get("best_params", {})
        best_sharpe = result.get("best_sharpe", 0.0)

        if not strategy_name or not best_params:
            logger.warning(
                "apply_evolution_result: missing strategy_name or best_params, skipping / "
                "缺少 strategy_name 或 best_params，跳过"
            )
            return False

        applied = False
        with self._lock:
            for deploy_key, info in self._deployed.items():
                # Match by strategy_name substring — deployed keys often include symbol suffix
                # 按 strategy_name 子串匹配 — 部署键通常包含幣種后缀
                if strategy_name in deploy_key or strategy_name == info.get("strategy_name", ""):
                    info["evolution_params"] = best_params
                    info["evolution_sharpe"] = best_sharpe
                    info["evolution_applied_ts"] = time.time()
                    applied = True
                    logger.info(
                        "apply_evolution_result: updated strategy=%s with params=%s sharpe=%.2f / "
                        "进化结果已应用：策略=%s 参数=%s Sharpe=%.2f",
                        deploy_key, best_params, best_sharpe,
                        deploy_key, best_params, best_sharpe,
                    )

        if not applied:
            logger.info(
                "apply_evolution_result: no active deployment found for strategy=%s / "
                "未找到策略 %s 的活跃部署",
                strategy_name, strategy_name,
            )

        return applied

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

        DEPRECATED 2026-04-10: Symbol management is now handled by the Rust ScannerRunner
        (openclaw_engine/src/scanner/runner.rs). This callback is dead code — Rust engine
        does not call Python scanner. Kept for audit trail only.
        已棄用 2026-04-10：symbol 管理已由 Rust ScannerRunner 接管，此回調為死代碼，
        Rust 引擎不調用 Python scanner。僅保留用於審計追蹤。

        Smart rebalancing: when all slots are full and a high-score opportunity appears,
        evaluate existing positions and close the weakest one to make room.
        智能再平衡：當所有槽位已滿且出現高分機會時，評估現有持倉，
        關閉最弱的持倉以騰出空間。
        """
        # DEPRECATED: Rust ScannerRunner owns symbol selection. This path is never called
        # from live trading. / Rust ScannerRunner 已接管 symbol 選擇，此路徑不被 live 交易調用。
        return

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

            # ── Reserved slot accounting ──
            # Count deployed per api_category to enforce reserved slots
            # 統計每個 api_category 已部署數量，用於預留槽位機制
            _deployed_by_api_cat: dict[str, int] = {}
            for _d in self._deployed.values():
                _ac = _d.get("api_category", "linear")
                _deployed_by_api_cat[_ac] = _deployed_by_api_cat.get(_ac, 0) + 1

            # Apply category priority: funding arb > grid > trend (risk-adjusted ordering)
            # 套利優先：funding arb 風險最低 → 優先部署
            prioritized = sorted(
                opportunities,
                key=lambda o: getattr(o, 'score', 0) + CATEGORY_PRIORITY_BONUS.get(getattr(o, 'category', ''), 0),
                reverse=True,
            )

            for opp in prioritized:
                symbol = opp.symbol
                category = opp.category

                # Skip if already trading this symbol with same category
                key = f"{category}_{symbol}"
                if key in self._deployed:
                    continue

                # ── Reserved slot enforcement ──
                # If this category has reserved slots, check if slots are truly full
                # 預留槽位：若此品類有預留，即使總槽位滿也允許部署（從其他品類的配額中借）
                opp_api_cat = getattr(opp, "api_category", "linear")
                reserved = self._reserved_slots.get(opp_api_cat, 0)
                deployed_in_cat = _deployed_by_api_cat.get(opp_api_cat, 0)
                has_reserved_room = reserved > 0 and deployed_in_cat < reserved

                if available_slots <= 0 and not has_reserved_room:
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
        Compute position size — Kelly-preferred with fixed-risk fallback.
        計算倉位大小 — 優先使用 Kelly，不足時回退固定風險公式。

        Primary path (Kelly):
          Uses PositionSizer.compute_recommendation() with trade stats + ATR.
          Kelly provides risk-adjusted sizing that adapts to actual edge.
          Kelly 提供根據實際 edge 自適應的風控倉位。

        Fallback path (fixed risk%):
          Base: risk_per_trade_pct of account balance / 5% hard stop.
          Score bonus: higher score → larger allocation (up to 2x).
          Used when Kelly data is insufficient or PositionSizer unavailable.
          當 Kelly 數據不足或 PositionSizer 不可用時使用。

        Invariant: NEVER returns 0 — minimum qty is always preserved.
        不變量：永不返回 0 — 最小倉位始終保留。
        """
        balance = self._get_balance()
        min_qty = self._min_qty_usdt / max(price, 1)

        if balance <= 0 or price <= 0:
            return min_qty

        # ── Kelly path: try PositionSizer first / 優先嘗試 Kelly 路徑 ──
        kelly_qty = self._try_kelly_sizing(symbol, balance, price)
        if kelly_qty is not None and kelly_qty > 0:
            # Apply score multiplier on top of Kelly recommendation
            # 在 Kelly 建議基礎上疊加評分乘數
            score_mult = min(1.5, 0.75 + score / 400.0)  # gentler than fallback: 50→0.875x, 200→1.25x
            qty = kelly_qty * score_mult

            # Enforce floor and ceiling / 強制上下限
            qty = max(min_qty, qty)
            max_qty = balance * (self._max_qty_pct / 100.0) / price
            qty = min(qty, max_qty)
            qty = round(qty, 6)

            logger.info(
                "Position sizing [Kelly]: %s balance=$%.0f score=%.0f → %.6f units "
                "(kelly_base=%.6f, score_mult=%.2f) / Kelly 倉位計算",
                symbol, balance, score, qty, kelly_qty, score_mult,
            )
            return qty

        # ── Fallback path: fixed risk% formula / 回退路徑：固定風險公式 ──
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
            "Position sizing [fallback]: %s balance=$%.0f score=%.0f → $%.1f (%.6f units) / 固定風險倉位計算",
            symbol, balance, score, allocated_usdt, qty,
        )
        return max(min_qty, qty)

    def _try_kelly_sizing(
        self, symbol: str, balance: float, price: float,
    ) -> float | None:
        """
        Attempt Kelly-based sizing via PositionSizer. Returns qty or None on failure.
        嘗試通過 PositionSizer 進行 Kelly 倉位計算。失敗返回 None。

        Gathers trade stats from PaperTradingEngine and ATR from the orchestrator's
        indicator engine. If insufficient data, returns None to trigger fallback.
        從 PaperTradingEngine 收集交易統計，從策略編排器的指標引擎獲取 ATR。
        數據不足時返回 None 以觸發回退。
        """
        try:
            # Lazy-init PositionSizer (same pattern as get_kelly_recommendations)
            # 惰性初始化 PositionSizer（與 get_kelly_recommendations 相同模式）
            sizer = getattr(self, '_position_sizer', None)
            if sizer is None:
                from .position_sizer import PositionSizer
                self._position_sizer = PositionSizer(
                    p1_max_pct=2.0, risk_pct_default=self._risk_pct,
                )
                sizer = self._position_sizer

            # Gather trade stats for this symbol from paper engine
            # 從 paper engine 收集此幣種的交易統計
            win_rate = 0.0
            avg_win = 0.0
            avg_loss = 0.0
            trade_count = 0
            unrealized_pnl = 0.0

            if self._engine:
                try:
                    state = self._engine.get_state()
                    trade_history = state.get("trade_history", [])

                    # Filter trades for this symbol / 篩選此幣種的交易
                    wins, losses = 0, 0
                    win_pnls: list[float] = []
                    loss_pnls: list[float] = []
                    for trade in trade_history:
                        if trade.get("symbol") != symbol:
                            continue
                        pnl = trade.get("pnl", 0.0)
                        if pnl > 0:
                            wins += 1
                            win_pnls.append(pnl)
                        else:
                            losses += 1
                            loss_pnls.append(abs(pnl))

                    trade_count = wins + losses
                    if trade_count > 0:
                        win_rate = wins / trade_count
                    if win_pnls:
                        avg_win = sum(win_pnls) / len(win_pnls)
                    if loss_pnls:
                        avg_loss = sum(loss_pnls) / len(loss_pnls)

                    # Get unrealized PnL for dampening / 獲取未實現盈虧用於抑制
                    positions = state.get("positions", {})
                    pos = positions.get(symbol, {})
                    unrealized_pnl = pos.get("unrealized_pnl", 0.0)
                except Exception:
                    pass

            # Get ATR from orchestrator's indicator engine (if available)
            # 從策略編排器的指標引擎獲取 ATR（如有）
            atr_value = 0.0
            try:
                if self._orch and hasattr(self._orch, 'get_indicators'):
                    indicators = self._orch.get_indicators(symbol, "1h")
                    # Look for ATR indicators in cache / 在緩存中查找 ATR 指標
                    for key, val in indicators.items():
                        if key.startswith("ATR(") and isinstance(val, dict):
                            atr = val.get("atr")
                            if atr is not None and atr > 0:
                                # Use the largest ATR (conservative) / 使用最大 ATR（保守）
                                atr_value = max(atr_value, atr)
            except Exception:
                pass

            # Minimum trades required for Kelly to be meaningful.
            # With < 10 trades, Kelly has no statistical basis — use fallback.
            # 最少交易次數要求：少於 10 筆時 Kelly 無統計基礎，使用回退。
            _KELLY_MIN_TRADES = 10
            if trade_count < _KELLY_MIN_TRADES:
                logger.debug(
                    "Kelly skipped for %s: only %d trades (need %d) / Kelly 跳過：交易不足",
                    symbol, trade_count, _KELLY_MIN_TRADES,
                )
                return None

            rec = sizer.compute_recommendation(
                balance=balance,
                price=price,
                win_rate=win_rate,
                avg_win=avg_win,
                avg_loss=avg_loss,
                trade_count=trade_count,
                atr=atr_value,
                unrealized_pnl=unrealized_pnl,
            )

            if rec.recommended_qty > 0:
                logger.debug(
                    "Kelly sizing for %s: fraction=%.4f tier=%s qty=%.6f "
                    "(trades=%d, wr=%.2f, atr=%.4f) / Kelly 倉位詳情",
                    symbol, rec.kelly_fraction, rec.kelly_tier,
                    rec.recommended_qty, trade_count, win_rate, atr_value,
                )
                return rec.recommended_qty

            return None

        except Exception as exc:
            logger.debug("Kelly sizing unavailable for %s: %s / Kelly 不可用", symbol, exc)
            return None

    # ── Dynamic Risk Adjustment (Sharpe-based) / 動態風控調整 ──

    def update_risk_from_sharpe(self) -> None:
        """
        Periodically adjust risk_per_trade_pct based on portfolio Sharpe ratio.
        定期根據組合 Sharpe 比率調整 risk_per_trade_pct。

        Rules:
        - Disabled if _dynamic_risk_enabled=False (master toggle)
        - Only activates when return_count >= 50 (enough data)
        - Sharpe > 1.0: gradually increase risk (good performance)
        - Sharpe 0~1.0: maintain base risk (neutral)
        - Sharpe < 0: gradually decrease risk (losing)
        - Max ±0.5% per adjustment, clamped to [1%, 5%]
        - Adjusts at most every 5 minutes (damping)

        規則：
        - _dynamic_risk_enabled=False 時完全禁用（主開關）
        - 僅在 return_count >= 50 時啟用（數據充足）
        - Sharpe > 1.0：逐步增加風險（表現好）
        - Sharpe 0~1.0：維持基準（中性）
        - Sharpe < 0：逐步降低風險（虧損中）
        - 每次最多 ±0.5%，鉗位在 [1%, 5%]
        - 最多每 5 分鐘調一次（阻尼）
        """
        if not self._dynamic_risk_enabled:
            return
        if not self._engine:
            return

        now = time.time()
        if now - self._last_risk_adjust_ts < self._risk_adjust_interval:
            return
        self._last_risk_adjust_ts = now

        # Get Sharpe data from paper engine
        try:
            from exchange_connectors.bybit_connector.control_api_v1.app.paper_trading_metrics import (
                compute_sharpe_ratio,
            )
            state = self._engine.get_state()
            fills = state.get("fills", [])
            session = state.get("session", {})
            initial_balance = session.get("initial_paper_balance_usdt", 1000.0)
            pnl = state.get("pnl")

            sharpe_data = compute_sharpe_ratio(fills, initial_balance, pnl)
        except Exception as e:
            logger.debug("Dynamic risk: could not compute Sharpe: %s", e)
            return

        return_count = sharpe_data.get("return_count", 0)
        sharpe = sharpe_data.get("sharpe_ratio", 0.0)
        note = sharpe_data.get("note", "")

        # Not enough data → stay inactive, use base risk / 數據不足 → 不啟用，用基準值
        if return_count < self._min_trades_for_dynamic or note in ("insufficient_data", "insufficient_returns", "zero_volatility"):
            if self._dynamic_risk_active:
                # Was active but data became stale → revert to base / 曾啟用但數據過期 → 恢復基準
                self._risk_pct = self._base_risk_pct
                self._dynamic_risk_active = False
                logger.info("Dynamic risk deactivated (data stale): reverting to base %.1f%% / 動態風控停用，恢復基準", self._base_risk_pct)
            return

        self._dynamic_risk_active = True

        # Compute target risk_pct based on Sharpe / 根據 Sharpe 計算目標 risk_pct
        if sharpe > 1.0:
            # Strong performance → increase toward ceil / 表現好 → 向上限靠近
            target = self._base_risk_pct + min(sharpe - 1.0, 2.0)  # +1% per Sharpe above 1.0, max +2%
        elif sharpe >= 0:
            # Neutral → stay at base / 中性 → 維持基準
            target = self._base_risk_pct
        else:
            # Losing → decrease toward floor / 虧損 → 向下限靠近
            target = self._base_risk_pct + max(sharpe, -2.0)  # -1% per Sharpe below 0, max -2%

        target = max(self._risk_pct_floor, min(target, self._risk_pct_ceil))

        # Damped adjustment: max ±step per interval / 阻尼調整：每次最多 ±step
        old = self._risk_pct
        delta = target - old
        if abs(delta) > self._risk_adjust_step:
            delta = self._risk_adjust_step if delta > 0 else -self._risk_adjust_step
        new_risk = max(self._risk_pct_floor, min(old + delta, self._risk_pct_ceil))

        if abs(new_risk - old) > 0.01:
            self._risk_pct = new_risk
            logger.info(
                "Dynamic risk adjusted: %.1f%% → %.1f%% (Sharpe=%.2f, trades=%d) / 動態風控調整",
                old, new_risk, sharpe, return_count,
            )

    def get_dynamic_risk_status(self) -> dict[str, Any]:
        """Get current dynamic risk adjustment status / 獲取動態風控調整狀態"""
        return {
            "enabled": self._dynamic_risk_enabled,
            "active": self._dynamic_risk_active,
            "base_risk_pct": self._base_risk_pct,
            "current_risk_pct": self._risk_pct,
            "floor": self._risk_pct_floor,
            "ceil": self._risk_pct_ceil,
            "min_trades": self._min_trades_for_dynamic,
        }

    def set_dynamic_risk_enabled(self, enabled: bool) -> None:
        """Toggle dynamic risk adjustment / 切換動態風控調整開關"""
        self._dynamic_risk_enabled = enabled
        if not enabled:
            # Revert to base when disabled / 禁用時恢復基準
            self._risk_pct = self._base_risk_pct
            self._dynamic_risk_active = False
            logger.info("Dynamic risk DISABLED: reverting to base %.1f%% / 動態風控已禁用", self._base_risk_pct)
        else:
            logger.info("Dynamic risk ENABLED / 動態風控已啟用")

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

    def _validate_strategy_backtest(
        self, symbol: str, strategy_name: str, category: str,
    ) -> bool:
        """
        0A-5: Run quick backtest on recent klines before deploying a strategy.
        部署策略前在近期 K 線上快速回測驗證。

        Returns True if strategy passes validation (or validation is unavailable).
        Fail-open: any error → return True (don't block deployment).
        返回 True 表示策略通過驗證（或驗證不可用）。
        Fail-open：任何異常 → 返回 True（不阻擋部署）。
        """
        try:
            from .backtest_engine import BacktestConfig

            config = BacktestConfig(
                symbol=symbol,
                timeframe="1h",
                strategy_name=strategy_name,
                backtest_mode=True,
            )
            result = self._backtest_engine.run(config)
            self._backtest_stats["validations_run"] += 1

            if result.total_trades < 3:
                # Not enough trades to judge — allow deployment (fail-open)
                # 交易次數不足以判斷 — 允許部署（fail-open）
                self._backtest_stats["validations_skipped"] += 1
                logger.info(
                    "0A-5: Backtest for %s/%s: only %d trades, skipping validation / "
                    "回測驗證跳過：交易數不足",
                    symbol, strategy_name, result.total_trades,
                )
                return True

            if result.sharpe_ratio >= self._backtest_min_sharpe:
                self._backtest_stats["validations_passed"] += 1
                logger.info(
                    "0A-5: Backtest PASSED for %s/%s: sharpe=%.2f trades=%d / "
                    "回測驗證通過：Sharpe=%.2f 交易數=%d",
                    symbol, strategy_name, result.sharpe_ratio, result.total_trades,
                    result.sharpe_ratio, result.total_trades,
                )
                return True
            else:
                self._backtest_stats["validations_failed"] += 1
                logger.info(
                    "0A-5: Backtest FAILED for %s/%s: sharpe=%.2f < min=%.2f — skipping deploy / "
                    "回測驗證未通過：Sharpe=%.2f < 閾值=%.2f — 跳過部署",
                    symbol, strategy_name, result.sharpe_ratio, self._backtest_min_sharpe,
                    result.sharpe_ratio, self._backtest_min_sharpe,
                )
                return False

        except Exception as e:
            # Fail-open: backtest error does not block deployment
            # Fail-open：回測異常不阻擋部署
            self._backtest_stats["validations_skipped"] += 1
            logger.warning(
                "0A-5: Backtest validation error for %s/%s (fail-open): %s / "
                "回測驗證異常（fail-open）：%s",
                symbol, strategy_name, e, e,
            )
            return True

    def _compute_leverage(self, opp: Any) -> float:
        """
        Compute leverage based on category + volatility, within risk limits.
        根據品類和波動率計算槓桿，在風控上限內。

        Logic:
        - Category base: spot=1x, linear=5x, inverse=3x
        - Volatility adjustment: high vol → lower leverage (conservative)
        - Hard cap from RiskManager.max_leverage per category
        品類基準：spot=1x（無槓桿）, linear=5x, inverse=3x
        波動率調整：高波動 → 降低槓桿（保守）
        硬上限來自 RiskManager 的 max_leverage
        """
        api_cat = getattr(opp, "api_category", "linear")
        vol_pct = getattr(opp, "volatility_pct", 5.0)

        # Category base leverage / 品類基礎槓桿
        if api_cat == "spot":
            return 1.0  # Spot has no leverage / 現貨無槓桿
        elif api_cat == "inverse":
            base = 3.0
            hard_cap = 10.0
        else:  # linear
            base = 5.0
            hard_cap = 20.0

        # Volatility factor: target ~5% daily vol as "normal"
        # vol_pct < 3% (low vol) → boost up to 1.5x base
        # vol_pct 3-8% (normal) → use base
        # vol_pct > 8% (high vol) → reduce to 0.5x base
        # 波動率因子：以 5% 日波動為「正常」基準
        if vol_pct <= 0:
            vol_factor = 1.0
        elif vol_pct < 3.0:
            vol_factor = 1.5  # Low vol → can afford more leverage / 低波動 → 可加槓桿
        elif vol_pct <= 8.0:
            vol_factor = 1.0  # Normal range / 正常範圍
        else:
            vol_factor = max(0.3, 5.0 / vol_pct)  # High vol → reduce / 高波動 → 降低

        leverage = base * vol_factor

        # Clamp to hard cap (from risk manager category config)
        leverage = max(1.0, min(leverage, hard_cap))

        # Round to 1 decimal for clean values
        return round(leverage, 1)

    def _deploy_strategy(self, symbol: str, category: str, opp: Any) -> None:
        """
        DEAD-PY-2: Python strategy classes deleted — Rust openclaw_engine handles execution.
        This method is retained as a stub for deployment tracking only.
        DEAD-PY-2：Python 策略類已刪除 — Rust openclaw_engine 負責策略執行。
        此方法保留為 stub 僅用於部署追蹤。
        """
        # TODO(R-07): Replace with Rust-side strategy deployment signal once R-07 phase complete.
        # 待 R-07 完成後替換為 Rust 端策略部署信號。
        logger.debug(
            "DEAD-PY-2 stub: _deploy_strategy called for %s/%s (no-op, Rust handles execution) / "
            "DEAD-PY-2 stub：_deploy_strategy 被調用（無操作，Rust 負責執行）",
            symbol, category,
        )
        return

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

    def get_kelly_recommendations(self) -> dict[str, Any]:
        """
        0B-3: Compute Kelly-based sizing recommendations for all deployed strategies.
        計算所有已部署策略的 Kelly 倉位建議。

        Uses trade outcome data from PaperTradingEngine (if available) to compute
        win_rate, avg_win, avg_loss per strategy. Falls back to minimal defaults.
        使用 PaperTradingEngine 的交易數據（如有）計算每策略勝率、平均盈虧。

        Returns:
            Dict with "strategies" key containing per-strategy recommendations.
        """
        if self._backtest_engine is None and not hasattr(self, '_position_sizer'):
            # Try lazy import / 嘗試惰性導入
            try:
                from .position_sizer import PositionSizer
                self._position_sizer = PositionSizer(p1_max_pct=2.0, risk_pct_default=self._risk_pct)
            except ImportError:
                return {"strategies": {}, "error": "PositionSizer not available"}

        sizer = getattr(self, '_position_sizer', None)
        if sizer is None:
            try:
                from .position_sizer import PositionSizer
                self._position_sizer = PositionSizer(p1_max_pct=2.0, risk_pct_default=self._risk_pct)
                sizer = self._position_sizer
            except ImportError:
                return {"strategies": {}, "error": "PositionSizer not available"}

        # Get balance and trade data from paper engine / 從 paper engine 獲取餘額和交易數據
        balance = 10000.0  # default
        trade_history: list = []
        if self._engine:
            try:
                state = self._engine.get_state()
                balance = state.get("balance", 10000.0)
                trade_history = state.get("trade_history", [])
            except Exception:
                pass

        # Aggregate per-strategy stats from trade history / 從交易歷史聚合每策略統計
        strategy_stats: dict[str, dict] = {}
        for trade in trade_history:
            sname = trade.get("strategy_name", "unknown")
            if sname not in strategy_stats:
                strategy_stats[sname] = {"wins": 0, "losses": 0, "win_pnls": [], "loss_pnls": []}
            pnl = trade.get("pnl", 0.0)
            if pnl > 0:
                strategy_stats[sname]["wins"] += 1
                strategy_stats[sname]["win_pnls"].append(pnl)
            else:
                strategy_stats[sname]["losses"] += 1
                strategy_stats[sname]["loss_pnls"].append(abs(pnl))

        # Compute recommendations for each deployed strategy / 為每個已部署策略計算建議
        result: dict[str, Any] = {}
        with self._lock:
            for key, info in self._deployed.items():
                symbol = info["symbol"]
                sname = info.get("strategy_name", key)
                stats = strategy_stats.get(sname, {})

                total = stats.get("wins", 0) + stats.get("losses", 0)
                win_rate = stats["wins"] / total if total > 0 else 0.0
                avg_win = (sum(stats.get("win_pnls", [])) / len(stats["win_pnls"])
                          if stats.get("win_pnls") else 0.0)
                avg_loss = (sum(stats.get("loss_pnls", [])) / len(stats["loss_pnls"])
                           if stats.get("loss_pnls") else 0.0)

                # Get approximate price / 獲取大約價格
                price = 1.0
                try:
                    ohlcv = self._km.get_ohlcv(symbol, "1h")
                    if ohlcv and ohlcv.get("close"):
                        price = ohlcv["close"][-1]
                except Exception:
                    pass

                rec = sizer.compute_recommendation(
                    balance=balance,
                    price=price,
                    win_rate=win_rate,
                    avg_win=avg_win,
                    avg_loss=avg_loss,
                    trade_count=total,
                )
                result[sname] = rec.to_dict()

        return {"strategies": result, "balance": balance}

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "component": "strategy_auto_deployer",
                "deployed_count": len(self._deployed),
                "deployed_symbols": list(set(d["symbol"] for d in self._deployed.values())),
                **self._stats,
                "backtest_validation": dict(self._backtest_stats),
            }
