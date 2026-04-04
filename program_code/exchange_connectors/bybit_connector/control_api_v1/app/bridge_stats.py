"""
Pipeline Bridge — Stats & Market Data Mixin (positions, round-trips, funding, volume).
管線橋接器 — 統計與市場數據 Mixin（持倉、交易回合、資金費率、成交量）。

Split from pipeline_bridge.py (TD-01) to stay under 1200-line limit.
"""
from __future__ import annotations

import json as _json_mod
import logging
import time
from typing import Any

from .risk_manager import REGIME_TIME_MULTIPLIERS
from .utils.time_utils import now_ms

logger = logging.getLogger(__name__)


class _BridgeStatsMixin:
    """Stats, market data, and position lifecycle methods for PipelineBridge."""

    def _on_position_open(
        self, intent: Any, fill_price: float, actual_qty: float = 0.0,
        demo_fill_price: float = 0.0,
    ) -> None:
        """
        Called when a new position is opened.
        Record it in _open_positions and register with StopManager using ATR-based stop.
        新持仓开仓时调用。记录到 _open_positions 并用 ATR 动态止损注册到 StopManager。

        actual_qty: The rounded qty actually submitted (for Demo consistency).
                    If 0, falls back to intent.qty.
        demo_fill_price: Demo 的真實成交價，用於計算交易所端條件止損單的觸發價。
                         若為 0 則回退到 Paper fill_price（向後兼容）。
                         Demo's actual fill price for exchange conditional stop-loss trigger.
                         Falls back to Paper fill_price if 0 (backward compatible).
        """
        symbol = intent.symbol
        strategy_name = getattr(intent, "strategy_name", "unknown")
        side = "long" if intent.side == "Buy" else "short"
        qty = actual_qty if actual_qty > 0 else intent.qty
        regime = (intent.metadata or {}).get("_regime", "unknown") if intent.metadata else "unknown"
        key = f"{strategy_name}:{symbol}"

        # U-05: Capture entry fee from the fill record for accurate round-trip cost accounting.
        # U-05：从成交记录中获取开仓费用，用于精确的 round-trip 成本核算。
        _entry_fee = 0.0
        if self._engine:
            try:
                _state = self._engine.get_state()
                _fills = _state.get("fills", [])
                # Find the most recent fill for this symbol (entry fill).
                # 查找该 symbol 最近一次成交（开仓成交）。
                for _f in reversed(_fills):
                    if _f.get("symbol") == symbol:
                        _entry_fee = float(_f.get("fee", 0.0))
                        break
            except Exception:
                pass  # fail-open: missing fee won't block trading / 缺失费用不阻塞交易

        # U-05: Capture confidence from intent for param_snapshot.
        # U-05：从 intent 获取置信度用于参数快照。
        _confidence = getattr(intent, "confidence", 0.0) or 0.0
        _strategy = getattr(intent, "strategy_name", strategy_name) or strategy_name

        with self._lock:
            self._open_positions[key] = {
                "symbol": symbol,
                "strategy_name": strategy_name,
                "side": side,
                "entry_price": fill_price,
                "qty": qty,
                "entry_ts_ms": now_ms(),
                "regime": regime,
                # U-05: Entry fee for round-trip cost accounting (Principle 8 auditability).
                # U-05：开仓费用，用于 round-trip 成本审计（原则 8 可审计性）。
                "entry_fee": _entry_fee,
                # U-05: Signal confidence at entry time.
                # U-05：开仓时的信号置信度。
                "confidence": _confidence,
            }

        # Write regime to paper engine position so RiskManager can use it for stop/TP/time scaling
        # 将市场状态写入纸上交易引擎持仓，让 RiskManager 用于止损/止盈/时间缩放
        if self._engine and regime != "unknown":
            try:
                store = self._engine.store
                def _inject_regime(state: dict) -> dict:
                    if symbol in state.get("positions", {}):
                        state["positions"][symbol]["regime"] = regime
                    return state
                store.mutate(_inject_regime)
            except Exception:
                logger.debug("Could not write regime to position (non-fatal): %s", symbol)

        # U-09: ATR dual-window stop — use max(ATR_fast, ATR_slow) for conservative estimate
        # U-09：ATR 双窗口止损 — 取 max(快窗口, 慢窗口) 作为保守估计
        # Fast window (5-period) reacts quicker to regime changes; slow (14) is stable.
        # 快窗口（5 期）对 regime 切换反应更快；慢窗口（14 期）更稳定。取大值更保守。
        atr_stop_pct = 5.0  # default hard stop / 默认硬止损
        if self._ie and fill_price > 0:
            try:
                atr_data = self._ie.get_conservative_atr(symbol, "1h")
                atr_raw = atr_data.get("atr_conservative")
                if atr_raw and atr_raw > 0:
                    atr_stop_pct = min(15.0, max(2.0, (atr_raw * 2.0 / fill_price) * 100))
            except Exception as e:
                # Log but allow fallback to default 5.0% stop (fail-closed)
                logger.error("Failed to compute ATR stop percentage for %s: %s; using default 5.0%%", symbol, e)

        # H1: register with StopManager using ATR-based dynamic stop + regime-adjusted time stop
        # H1：使用 ATR 动态止损 + 市场状态调整时间止损注册到 StopManager
        if self._stop_mgr:
            try:
                from local_model_tools.stop_manager import StopConfig
                # Regime-adjusted time stop / 市场状态调整时间止损
                time_stop_hours = 48.0 * REGIME_TIME_MULTIPLIERS.get(regime, 1.0)
                # B6: Dynamic trailing stop = max(5%, 2×ATR/price*100)
                # B6：动态追踪止损 = max(5%, 2×ATR/价格*100)，避免噪音触发
                trailing_pct = 5.0  # floor: never tighter than 5%
                try:
                    indics_trail = self._km.get_latest_indicators(symbol) if hasattr(self._km, 'get_latest_indicators') else None
                    atr_val = indics_trail.get("atr") if indics_trail else None
                    if atr_val and atr_val > 0 and fill_price > 0:
                        atr_trail_pct = (atr_val * 2.0 / fill_price) * 100
                        trailing_pct = max(5.0, min(15.0, atr_trail_pct))
                except Exception:
                    pass  # fallback to 5% floor
                self._stop_mgr.track_position(
                    symbol=symbol,
                    side=side,
                    entry_price=fill_price,
                    qty=qty,
                    strategy_name=strategy_name,
                    stop_config=StopConfig(
                        hard_stop_pct=atr_stop_pct,
                        trailing_stop_pct=trailing_pct,
                        time_stop_hours=time_stop_hours,
                    ),
                )
                logger.info(
                    "Tracking position %s %s atr_stop=%.2f%% time_stop=%.1fh regime=%s / 追踪持仓",
                    strategy_name, symbol, atr_stop_pct, time_stop_hours, regime,
                )
            except Exception:
                logger.exception("StopManager track error (non-fatal) / 止损追踪异常（非致命）")

        # U-05: Snapshot dynamic parameters at entry time for round-trip auditing (Principle 8).
        # U-05：开仓时快照动态参数，用于 round-trip 审计回溯（原则 8 可审计性）。
        # These values are stored in _open_positions and written to round-trip records at close.
        # 这些值存储在 _open_positions 中，平仓时写入 round-trip 记录。
        _atr_pct = (atr_stop_pct / 2.0) if fill_price > 0 else 0.0  # ATR/price approx
        _trail_activation_pct = atr_stop_pct * 0.5  # trailing activates at 50% of stop distance
        _c_round_pct = 0.0
        if fill_price > 0 and qty > 0:
            # Estimate round-trip cost as 2x entry fee / notional
            # 估算 round-trip 成本 = 2 倍开仓费 / 名义金额
            _notional = fill_price * qty
            _c_round_pct = (2 * _entry_fee / _notional * 100) if _notional > 0 else 0.0

        with self._lock:
            if key in self._open_positions:
                self._open_positions[key]["param_snapshot"] = {
                    "atr_pct": round(_atr_pct, 4),
                    "stop_distance_pct": round(atr_stop_pct, 4),
                    "trail_activation_pct": round(_trail_activation_pct, 4),
                    "trail_distance_pct": round(trailing_pct if self._stop_mgr else 5.0, 4),
                    "c_round_pct": round(_c_round_pct, 6),
                    "regime": regime,
                    "strategy_name": strategy_name,
                    "confidence": round(_confidence, 4),
                }

        # ── Batch 11: Exchange conditional stop-loss (DOC-01 §5.9 dual defense) ──
        # Batch 11：交易所条件止损单（DOC-01 §5.9 双重防线）
        # fail-closed: if conditional order creation fails, log but do NOT block local stop-loss
        # 失败安全：条件单创建失败仅记录日志，不阻止本地止损
        if self._demo_connector and self._demo_connector.is_enabled and fill_price > 0:
            try:
                from .bybit_demo_connector import round_price_for_exchange
                # Close side is opposite of position side
                # 平仓方向与持仓方向相反
                close_side = "Sell" if side == "long" else "Buy"

                # ★ FIX: 使用 Demo 真實成交價計算止損觸發價（而非 Paper 模擬價）
                # Demo entry price may differ from Paper due to real orderbook vs simulated slippage.
                # Using Paper price caused PIPPINUSDT to round(0.056859, 2) = 0.06 ≈ market price,
                # triggering false stop loss within 19 seconds.
                # ★ FIX: Use Demo actual fill price for stop trigger (not Paper simulated price).
                _stop_base_price = demo_fill_price if demo_fill_price > 0 else fill_price

                _hard_stop_pct = atr_stop_pct
                if side == "long":
                    raw_trigger = _stop_base_price * (1 - _hard_stop_pct / 100)
                else:
                    raw_trigger = _stop_base_price * (1 + _hard_stop_pct / 100)

                # ★ FIX: 用交易所 tickSize 取整，而非硬編碼 round(..., 2)
                # round(..., 2) 對低價幣（$0.06）會把 0.056859 進位到 0.06 = 市價
                # ★ FIX: Round using exchange tick_size, not hardcoded round(..., 2).
                # round(..., 2) on low-price coins ($0.06) rounds 0.056859 UP to 0.06 = market price.
                tick_size = None
                if self._symbol_registry:
                    try:
                        tick_size = self._symbol_registry.get_tick_size(symbol)
                    except Exception:
                        pass  # fallback to 8dp
                trigger_price = round_price_for_exchange(raw_trigger, tick_size)

                cond_result = self._demo_connector.place_conditional_order(
                    symbol=symbol,
                    side=close_side,
                    qty=qty,
                    trigger_price=trigger_price,
                )
                if cond_result.get("retCode") == 0:
                    logger.info(
                        "Dual defense: exchange stop-loss created %s %s trigger=%s "
                        "(base_price=%s tick_size=%s) / "
                        "双重防线：交易所止损单已创建",
                        symbol, close_side, trigger_price,
                        _stop_base_price, tick_size,
                    )
                else:
                    logger.warning(
                        "Dual defense: exchange stop-loss FAILED %s reason=%s (local stop still active) / "
                        "双重防线：交易所止损单创建失败（本地止损仍然有效）",
                        symbol, cond_result.get("retMsg"),
                    )

                # 0B-2: Place TP (take-profit) conditional order alongside SL.
                # 0B-2：在 SL 旁邊同時掛 TP（止盈）條件單。
                # TP at 2× the SL distance (risk:reward ~1:2). Fail-open: TP failure doesn't block.
                # TP 距離 = 2× SL 距離（風險回報比 ~1:2）。TP 失敗不阻擋。
                try:
                    _tp_mult = 2.0  # TP = 2× SL distance for 1:2 R:R
                    if side == "long":
                        tp_raw = _stop_base_price * (1 + _hard_stop_pct * _tp_mult / 100)
                        tp_dir = 1  # Sell TP triggers on price rise
                    else:
                        tp_raw = _stop_base_price * (1 - _hard_stop_pct * _tp_mult / 100)
                        tp_dir = 2  # Buy TP triggers on price fall
                    tp_price = round_price_for_exchange(tp_raw, tick_size)
                    tp_result = self._demo_connector.place_conditional_order(
                        symbol=symbol,
                        side=close_side,
                        qty=qty,
                        trigger_price=tp_price,
                        trigger_direction=tp_dir,
                    )
                    if tp_result.get("retCode") == 0:
                        logger.info(
                            "0B-2: TP order created %s %s trigger=%s / 止盈單已創建",
                            symbol, close_side, tp_price,
                        )
                except Exception as _tp_err:
                    logger.debug("0B-2: TP order failed (SL still active): %s", _tp_err)

            except Exception as _cond_err:
                logger.warning(
                    "Dual defense: conditional order error %s: %s (local stop still active) / "
                    "双重防线：条件单创建异常（本地止损仍然有效）",
                    symbol, _cond_err,
                )

    def _try_learning_promotion(self, close_pnl: float) -> None:
        """
        EX-05 §3: Attempt to promote learning tier based on trade outcome.
        根据交易结果尝试晋升学习等级。

        This is called after each round-trip completion to:
        1. Record the trade outcome (win/loss) and update local stats
        2. Update tier metrics (observation_count, win_rate, etc.)
        3. Check for promotion eligibility and auto-promote if eligible

        L1→L2 promotion requires:
          - observation_count >= 500
          - win_rate >= 20%

        Non-fatal if gate is not set or if promotion fails.

        在每个 round-trip 完成后调用以：
        1. 记录交易结果（赢/亏）并更新本地统计
        2. 更新等级指标（观察计数、胜率等）
        3. 检查晋升资格并在符合条件时自动晋升

        L1→L2 晋升需要：
          - 观察计数 >= 500
          - 胜率 >= 20%

        如果未设置门控或晋升失败，则为非致命。

        Args:
            close_pnl: Closed PnL of the completed trade (positive = win, negative/zero = loss)
        """
        if not self._learning_tier_gate:
            return

        try:
            # Determine win/loss: close_pnl > 0 means win, otherwise loss
            # 确定 win/loss：close_pnl > 0 表示赢，否则表示亏
            win = close_pnl > 0

            # Update local learning stats for this bridge instance
            # 更新此桥接器实例的本地学习统计
            with self._lock:
                self._learning_stats["total_trades"] += 1
                if win:
                    self._learning_stats["winning_trades"] += 1
                total = self._learning_stats["total_trades"]
                wins = self._learning_stats["winning_trades"]

            # Calculate win_rate from local stats
            # 从本地统计计算胜率
            win_rate = wins / total if total > 0 else 0.0

            # Update metrics in the gate
            # 更新门控中的指标
            self._learning_tier_gate.update_metrics(
                observation_count=total,
                win_rate=win_rate,
            )

            # Attempt promotion to next tier if eligible
            # 如果符合条件，尝试晋升到下一个等级
            next_tier_method = getattr(self._learning_tier_gate, '_next_tier', None)
            if next_tier_method:
                from .learning_tier_gate import LearningTier
                current = self._learning_tier_gate.current_tier
                next_tier = next_tier_method(current)

                if next_tier > current:
                    eligible, reasons = self._learning_tier_gate.check_tier_eligibility(next_tier)
                    if eligible:
                        try:
                            self._learning_tier_gate.promote_tier(
                                next_tier,
                                initiator="LearningGate",
                                reason=f"auto_promotion from {current.name} to {next_tier.name}",
                            )
                            logger.info(
                                "Learning tier auto-promoted: %s → %s / 学习等级自动晋升",
                                current.name,
                                next_tier.name,
                            )
                        except Exception as e:
                            logger.debug("Learning tier promotion error (non-fatal): %s", e)
        except Exception as e:
            logger.debug("Learning tier gate error (non-fatal): %s", e)

    def _emit_round_trip(
        self, symbol: str, strategy_name: str, exit_price: float, close_pnl: float,
        *, close_fee: float = 0.0,
    ) -> None:
        """
        Core round-trip completion handler — shared by intent-path and tick-path closes.
        Pops _open_positions, fires G1 + E1 callbacks, unregisters from StopManager.

        U-05: Now includes real fees_paid (entry_fee + close_fee) and param_snapshot in
        round-trip records for accurate cost attribution and parameter auditing (Principle 8).

        核心 round-trip 完成处理器 — 被意图路径和 tick 路径共用。
        弹出 _open_positions，触发 G1 + E1 回调，从 StopManager 取消注册。

        U-05：现在在 round-trip 记录中包含真实费用（开仓费 + 平仓费）和参数快照，
        用于精确的成本归因和参数审计（原则 8 可审计性）。
        """
        key = f"{strategy_name}:{symbol}"

        with self._lock:
            pos_info = self._open_positions.pop(key, None)

        hold_ms = 0
        regime = "unknown"
        entry_ts_ms = now_ms()
        entry_price = 0.0
        qty = 0.0
        entry_fee = 0.0
        param_snapshot: dict = {}

        if pos_info:
            hold_ms = now_ms() - pos_info.get("entry_ts_ms", now_ms())
            regime = pos_info.get("regime", "unknown")
            entry_ts_ms = pos_info.get("entry_ts_ms", now_ms())
            entry_price = pos_info.get("entry_price", 0.0)
            qty = pos_info.get("qty", 0.0)
            # U-05: Extract entry fee and param_snapshot stored at open time.
            # U-05：提取开仓时保存的入场费用和参数快照。
            entry_fee = pos_info.get("entry_fee", 0.0)
            param_snapshot = pos_info.get("param_snapshot", {})

        # U-05: Compute real round-trip fees = entry_fee + close_fee.
        # U-05：计算真实 round-trip 费用 = 开仓费 + 平仓费。
        fees_paid = entry_fee + close_fee

        # U-05: Compute slippage if entry_price is available.
        # Slippage = |exit_price - entry_price| normalized by entry_price.
        # For stop-loss exits this represents the actual price deviation.
        # U-05：如果有入场价格，计算滑点 = |出场价 - 入场价| / 入场价。
        slippage = 0.0
        slippage_estimated = True
        if entry_price > 0 and exit_price > 0:
            slippage = abs(exit_price - entry_price) / entry_price
            slippage_estimated = False

        # Untrack from StopManager (position is closed) / 从 StopManager 取消追踪
        if self._stop_mgr:
            try:
                self._stop_mgr.untrack_position(symbol, strategy_name)
            except Exception as e:
                # Critical path: position untracking should not silently fail
                logger.error("Failed to untrack position %s from StopManager: %s", symbol, e)

        # G1: notify auto-deployer for consecutive loss tracking
        # G1：通知自动部署器进行连续亏损追踪
        if self._auto_deployer:
            try:
                self._auto_deployer.on_trade_result(strategy_name, close_pnl)
            except Exception as e:
                # Log at warning: consecutive-loss tracking failure means auto-deployer
                # may not pause the strategy on drawdown — worth surfacing
                # 使用 warning 级别：连续亏损追踪失败意味着自动部署器可能无法在回撤时暂停策略
                logger.warning("Auto-deployer on_trade_result error for %s (consecutive-loss tracking may be stale): %s", strategy_name, e)

        # E1: write auto-observation
        # E1：写入自动观察
        if self._observation_writer:
            try:
                self._observation_writer(
                    symbol=symbol,
                    strategy_name=strategy_name,
                    close_pnl=close_pnl,
                    hold_ms=hold_ms,
                    regime=regime,
                )
            except Exception:
                logger.debug("Observation writer error (non-fatal)")

        # L1.01: Trade Attribution / L1.01：交易归因
        # 当交易完成时，分解交易为归因因子（ALPHA/TIMING/SIZING/EXECUTION/COST/LUCK）
        # When trade completes, decompose into attribution factors
        if self._trade_attribution and entry_price > 0 and qty > 0:
            try:
                import datetime
                import uuid

                exit_ts_ms = now_ms()
                entry_dt = datetime.datetime.fromtimestamp(entry_ts_ms / 1000.0, tz=datetime.timezone.utc)
                exit_dt = datetime.datetime.fromtimestamp(exit_ts_ms / 1000.0, tz=datetime.timezone.utc)
                trade_id = f"{strategy_name}:{symbol}:{uuid.uuid4().hex[:8]}"

                # Calculate gross PnL from entry/exit prices and quantity
                # 从入场/出场价格和数量计算毛利润
                gross_pnl = (exit_price - entry_price) * qty

                # Call attribution engine with minimal required parameters
                # 用最少必需的参数调用归因引擎
                attribution_result = self._trade_attribution.attribute_trade(
                    trade_id=trade_id,
                    symbol=symbol,
                    strategy=strategy_name,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    quantity=qty,
                    entry_timestamp=entry_dt,
                    exit_timestamp=exit_dt,
                    market_prices_at_entry={},  # Empty dict as default
                    market_prices_at_exit={},   # Empty dict as default
                    fees_paid=fees_paid,        # U-05: Real fees (entry + close)
                    slippage=slippage,          # U-05: Real price slippage
                    ai_cost=0.0,               # Could be enhanced with model costs
                )

                # Log attribution results for learning_tier
                # 将归因结果记录到学习层
                logger.info(
                    "Trade attribution: %s → skill=%.2f%% luck=%.2f%% alpha=%.4f / 交易归因: skill=%.2f%% luck=%.2f%%",
                    trade_id,
                    attribution_result.skill_pct * 100,
                    attribution_result.luck_pct * 100,
                    attribution_result.attribution_scores[0].score if attribution_result.attribution_scores else 0.0,
                )
            except Exception as e:
                logger.debug("Trade attribution error (non-fatal): %s", e)

        # EX-05 §3: Learning Tier Auto-Promotion / EX-05 §3：学习等级自动晋升
        # Record trade outcome and check for promotion eligibility
        # 记录交易结果并检查晋升资格
        self._try_learning_promotion(close_pnl)

        # Batch 9: Emit ROUND_TRIP_COMPLETE to MessageBus for AnalystAgent
        # Batch 9：通过消息总线发送 ROUND_TRIP_COMPLETE 给 AnalystAgent
        if self._message_bus:
            try:
                from .multi_agent_framework import AgentMessage, AgentRole, MessageType
                rt_msg = AgentMessage(
                    sender=AgentRole.EXECUTOR,
                    receiver=AgentRole.ANALYST,
                    message_type=MessageType.ROUND_TRIP_COMPLETE,
                    priority=5,
                    payload={
                        "trade_id": f"{strategy_name}:{symbol}:{int(time.time())}",
                        "symbol": symbol,
                        "strategy": strategy_name,
                        "direction": "long" if pos_info and pos_info.get("side") == "Buy" else "short",
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "pnl": close_pnl,
                        "hold_ms": hold_ms,
                        "regime": regime,
                        "timestamp_ms": now_ms(),
                        # U-05: Real fees and parameter snapshot for auditing (Principle 8).
                        # U-05：真实费用和参数快照用于审计（原则 8）。
                        "fees_paid": fees_paid,
                        "param_snapshot": param_snapshot,
                    },
                )
                self._message_bus.send(rt_msg)
            except Exception as _rt_err:
                logger.debug("MessageBus ROUND_TRIP_COMPLETE send error (non-fatal): %s", _rt_err)

        # Batch 9: Register trade result as INFERENCE in Perception Plane
        # Batch 9：将交易结果注册为 INFERENCE 到感知平面
        if self._perception_plane:
            try:
                from .perception_data_plane import DataSourceType, CognitiveLevel
                self._perception_plane.register_data(
                    source_type=DataSourceType.LEARNING_HISTORY,
                    content={"symbol": symbol, "strategy": strategy_name, "pnl": close_pnl, "regime": regime},
                    source_detail="round_trip_complete",
                    cognitive_level=CognitiveLevel.INFERENCE,
                    symbols=[symbol],
                    marked_by="PipelineBridge._emit_round_trip",
                    marking_reason="Trade result analysis = INFERENCE (learning data)",
                )
            except Exception:
                pass  # Non-fatal / 非致命

        logger.info(
            "Round-trip complete: %s %s pnl=%.4f fees=%.6f hold=%.1fh regime=%s / 交易完成",
            strategy_name, symbol, close_pnl, fees_paid, hold_ms / 3600000, regime,
        )

    def _on_round_trip_complete(
        self, intent: Any, exit_price: float, close_pnl: float,
        *, close_fee: float = 0.0,
    ) -> None:
        """
        Called when a position is closed via immediate market-order fill in submit_order().
        Delegates to _emit_round_trip.
        U-05: Now passes close_fee for accurate round-trip cost accounting.
        通过 submit_order() 即时成交路径平仓时调用，委托给 _emit_round_trip。
        U-05：现在传递平仓费用用于精确的 round-trip 成本核算。
        """
        symbol = intent.symbol
        strategy_name = getattr(intent, "strategy_name", "unknown")
        self._emit_round_trip(symbol, strategy_name, exit_price, close_pnl, close_fee=close_fee)

    def on_tick_result(self, tick_result: dict) -> None:
        """
        Called by MarketDataDispatcher after engine.tick() produced fills.
        Detects positions closed via tick path (risk_auto_close, time stop, soft stop)
        and fires E1/G1 hooks that the submit_order path would otherwise miss.

        由 MarketDataDispatcher 在 engine.tick() 产生成交后调用。
        检测通过 tick 路径平仓的仓位（risk_auto_close/时间止损/软止损），
        触发 submit_order 路径本会遗漏的 E1/G1 回调。
        """
        fills = tick_result.get("fills", [])
        if not fills:
            return

        # Snapshot tracked open positions to avoid holding lock during callbacks
        with self._lock:
            tracked = dict(self._open_positions)

        if not tracked:
            return

        already_emitted: set = set()

        for fill in fills:
            symbol = fill.get("symbol", "")
            fill_side = fill.get("side", "")   # "Buy" or "Sell"
            fill_price = fill.get("price", 0.0)
            close_fee = fill.get("fee", 0.0)

            if not symbol or fill_price <= 0:
                continue

            # Find a tracked open position for this symbol with a matching close direction
            for key, pos_info in tracked.items():
                if pos_info.get("symbol") != symbol:
                    continue
                if key in already_emitted:
                    continue

                pos_side = pos_info.get("side", "")  # "long" or "short"
                is_close = (
                    (pos_side == "long" and fill_side == "Sell") or
                    (pos_side == "short" and fill_side == "Buy")
                )
                if not is_close:
                    continue

                # Approximate close_pnl from entry/exit price (entry fee already sunk)
                entry_price = pos_info.get("entry_price", 0.0)
                qty = pos_info.get("qty", 0.0)
                if entry_price > 0 and qty > 0:
                    raw_pnl = (fill_price - entry_price) * qty if pos_side == "long" \
                        else (entry_price - fill_price) * qty
                    close_pnl = raw_pnl - close_fee
                else:
                    close_pnl = 0.0

                strategy_name = pos_info.get("strategy_name", "unknown")
                # U-05: Pass close_fee for accurate round-trip cost accounting.
                # U-05：传递平仓费用用于精确的 round-trip 成本核算。
                self._emit_round_trip(symbol, strategy_name, fill_price, close_pnl, close_fee=close_fee)
                already_emitted.add(key)
                break  # one emit per tracked position per tick

    @staticmethod
    def _infer_category_from_symbol(symbol: str) -> str:
        """Infer Bybit V5 category from symbol naming convention.
        根據 Bybit V5 symbol 命名規則推斷品類。

        Rules (Bybit naming convention):
          - Ends with "USD" but not "USDT" or "USDC" → "inverse"  (e.g. BTCUSD, ETHUSD)
          - Contains "-" (option format, e.g. BTC-1JAN25-50000-C) → "option"
          - "USDT" / "USDC" perpetuals or spot share the same suffix; we default to "linear"
            because spot symbols are also tracked in market_scanner with category metadata.
            Callers that know the true category should pass it explicitly.
          - Fallback → "linear"

        規則（Bybit 命名慣例）：
          - 以 "USD" 結尾但不以 "USDT"/"USDC" 結尾 → inverse（如 BTCUSD、ETHUSD）
          - 包含 "-" → option（如 BTC-1JAN25-50000-C）
          - 其餘情況默認 linear；真正的 spot symbol 需呼叫端明確指定 category
        """
        sym = symbol.upper()
        if "-" in sym:
            return "option"
        if sym.endswith("USD") and not sym.endswith("USDT") and not sym.endswith("USDC"):
            return "inverse"
        # fallback：命名規則無法區分 linear 與 spot，可能推斷錯誤。
        # Fallback: naming convention cannot distinguish linear from spot; may be incorrect.
        # 呼叫端應通過 register_symbol_category() 或 SymbolCategoryRegistry 提供正確 category。
        # Callers should provide correct category via register_symbol_category() or SymbolCategoryRegistry.
        logger.warning(
            "Category inferred as linear for symbol=%s — may be incorrect for spot symbols. "
            "Register via StrategyAutoDeployer or SymbolCategoryRegistry to fix. "
            "/ symbol=%s 的 category 被推斷為 linear，對 spot symbol 可能錯誤",
            symbol, symbol,
        )
        return "linear"

    def _refresh_kline_volume(self) -> None:
        """
        Periodically fetch latest kline from REST API to get real volume data.
        定期从 REST API 获取最新 K线以获取真实成交量。

        Dynamically covers all tracked symbols, not just BTC/ETH.
        动态覆盖所有已追踪的交易对，不仅限于 BTC/ETH。

        SPOT-4: Category is now inferred per-symbol so Spot symbols query the correct
        endpoint. Bybit v5 /market/kline requires the correct category to return data.
        SPOT-4：現在為每個 symbol 推斷正確的 category，避免 spot symbol 查到錯誤端點。
        """
        import urllib.request
        # E5 NEW-S4: Use module-level _json_mod instead of local re-import
        # E5 NEW-S4：使用模塊級 _json_mod 而非局部重新導入

        tf_map = {"1m": "1", "5m": "5", "15m": "15", "1h": "60"}

        # Use all actively tracked symbols / 使用所有活跃追踪的交易对
        tracked = self._km.get_tracked_symbols() if hasattr(self._km, "get_tracked_symbols") else []
        if not tracked:
            tracked = list(self._latest_prices.keys())
        # Cap to 10 symbols per refresh to avoid rate limits / 限制每次最多 10 个以避免频率限制
        symbols = tracked[:10]

        for symbol in symbols:
            # Wave 7a 方案 B：優先從運行時映射查詢，fallback 到名稱推斷（可能不準確）。
            # Wave 7a Plan B: prefer runtime map; fallback to name inference (may be inaccurate
            # for spot symbols that share the same suffix as linear, e.g. BTCUSDT).
            kline_category = self._symbol_category_map.get(symbol) or self._infer_category_from_symbol(symbol)

            for tf, interval in tf_map.items():
                try:
                    url = (
                        f"https://api.bybit.com/v5/market/kline"
                        f"?category={kline_category}&symbol={symbol}&interval={interval}&limit=2"
                    )
                    req = urllib.request.Request(url, headers={"User-Agent": "OpenClaw/1.0"})
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        data = _json_mod.loads(resp.read().decode())

                    if data.get("retCode") != 0:
                        continue

                    klines = data.get("result", {}).get("list", [])
                    if not klines:
                        continue

                    # Bybit returns newest first; we want the most recently CLOSED kline (index 1)
                    # The kline at index 0 is still forming
                    if len(klines) >= 2:
                        closed = klines[1]  # [startTime, open, high, low, close, volume, turnover]
                        volume = float(closed[5]) if len(closed) > 5 else 0.0
                        # Update the last closed bar's volume in KlineManager
                        buf = self._km.get_buffer(symbol, tf)
                        if buf and len(buf) > 0:
                            last_bar = buf._bars[-1]  # Access internal deque
                            if last_bar.volume == 0 and volume > 0:
                                last_bar.volume = volume
                                last_bar.turnover = float(closed[6]) if len(closed) > 6 else 0.0
                except Exception:
                    pass  # Non-critical, silently skip

    def _fetch_single_funding_rate(self, symbol: str, category: str | None = None) -> tuple[float, int] | None:
        """Fetch funding rate for a single symbol from Bybit API.
        为单个品种从 Bybit API 获取 funding rate。

        Returns:
            (funding_rate, next_settle_ts_ms) or None if unavailable.
            返回 (funding_rate, next_settle_ts_ms)，不可用时返回 None。

        SPOT-4: Spot and option symbols have no funding rate — return None immediately.
        SPOT-4：現貨（spot）和期權（option）沒有資金費率，立即返回 None。
        """
        import urllib.request
        # E5 NEW-S4: Use module-level _json_mod instead of local re-import
        # E5 NEW-S4：使用模塊級 _json_mod 而非局部重新導入

        # SPOT-4: Funding rate only applies to perpetual contracts (linear / inverse).
        # Spot and option have no funding mechanism — skip API call entirely to avoid
        # spurious HTTP errors and unnecessary load on Bybit rate limits.
        # SPOT-4：資金費率只適用於永續合約（linear/inverse）。
        # Spot/option 沒有 funding 機制，直接跳過 API 調用，避免無效請求。
        # Wave 7a 方案 B：優先用呼叫端傳入的 category，其次查運行時映射，最後才用名稱推斷。
        # Wave 7a Plan B: explicit category arg > runtime map > name inference.
        resolved_category = category or self._symbol_category_map.get(symbol) or self._infer_category_from_symbol(symbol)
        if resolved_category in ("spot", "option"):
            logger.debug(
                "Skipping funding rate fetch for %s (category=%s, no funding rate) "
                "/ 跳過資金費率查詢：%s 品類無資金費率",
                symbol, resolved_category, symbol,
            )
            return None

        try:
            url = f"https://api.bybit.com/v5/market/tickers?category={resolved_category}&symbol={symbol}"
            req = urllib.request.Request(url, headers={"User-Agent": "OpenClaw/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = _json_mod.loads(resp.read().decode())

            if data.get("retCode") != 0:
                return None

            ticker_list = data.get("result", {}).get("list", [])
            if not ticker_list:
                return None

            ticker = ticker_list[0]
            funding_rate = float(ticker.get("fundingRate", 0))
            next_funding_ts = int(ticker.get("nextFundingTime", 0))

            if funding_rate == 0 or next_funding_ts == 0:
                return None

            return funding_rate, next_funding_ts
        except Exception:
            logger.debug("Funding rate fetch failed for %s / 获取失败: %s", symbol, symbol)
            return None

    def _check_funding_rates(self) -> None:
        """Fetch funding rate for each deployed FundingRate strategy's own symbol.
        为每个已部署的 FundingRate 策略获取其自身品种的 funding rate。

        Fix P0-A2: previously only fetched BTCUSDT/ETHUSDT and fed all strategies with
        wrong data. Now each strategy receives the rate for its own symbol.
        修复 P0-A2：此前只获取 BTCUSDT/ETHUSDT 并将错误数据喂给所有策略。
        现在每个策略接收其自身品种的 funding rate。
        """
        for strategy in self._orch._strategies.values():
            if not hasattr(strategy, "evaluate_funding_opportunity"):
                continue

            symbol = getattr(strategy, "_symbol", None) or getattr(strategy, "symbol", None)
            if not symbol:
                continue

            result = self._fetch_single_funding_rate(symbol)
            if result is None:
                continue

            funding_rate, next_funding_ts = result

            # B5: Pass spot/perp prices for basis risk calculation
            # B5：传递现货/永续价格供基差风险计算
            # Latest tick price serves as perp_price; spot is approximated as same
            # (until dedicated spot price feed is available).
            # 最新 tick 价格作为永续价格；现货近似为相同值
            # （在有专用现货价格源之前）。
            _latest_price = self._latest_prices.get(symbol)
            try:
                strategy.evaluate_funding_opportunity(
                    funding_rate=funding_rate,
                    next_settle_ts_ms=next_funding_ts,
                    spot_price=_latest_price,
                    perp_price=_latest_price,
                )
            except Exception:
                logger.exception("Funding rate eval error for %s / funding rate 评估异常: %s", symbol, symbol)

    def get_stats(self) -> dict[str, Any]:
        """Get bridge statistics / 获取桥接器统计"""
        with self._lock:
            return {
                "component": "pipeline_bridge",
                "active": self._active,
                **dict(self._stats),
            }
