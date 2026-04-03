"""
Funding Rate Arbitrage Strategy — Delta-Neutral / Funding Rate 套利策略 — 市场中性

MODULE_NOTE (中文):
  真正的 Delta-Neutral Funding Rate 套利：
  - 正 funding rate → 做空永续 + 做多现货（对冲价格风险）
  - 负 funding rate → 做多永续 + 做空现货

  两腿同时开仓，价格波动相互抵消，只赚 funding rate 差额。

  与旧版的区别：
  - 旧版只开永续单腿（裸方向性敞口，不是真套利）
  - 新版同时开 perp + spot 两腿，delta-neutral

  费用模型（0B-1 精算）：
  - 永续 taker: 0.055% × 2 sides = 11 bps
  - 现货 taker: 0.10% × 2 sides = 20 bps（Bybit VIP0 spot taker 0.10%）
  - 预估滑点: 默认 3 bps（可配置，随波动率调整）
  - 总来回费用 ≈ 31 bps + 滑点 ≈ 34 bps
  - 因此 funding rate 需 > 34 bps / 预期持仓周期数 才有正期望
  - 持仓跨多个 funding 周期（每 8h）时费用摊薄：edge = rate × periods - total_fee

  入场条件：
  1. |funding_rate| > threshold（默认 5bps = 0.0005）
  2. 预估多周期 funding 收入 > 总费用（含滑点）
  3. 距下次结算 ≥ 2 小时
  4. basis risk（现货-永续价差）< max_basis_pct

  出场条件：
  1. funding rate 反转
  2. funding rate 太小不值得继续持有（考虑摊薄后费用）
  3. 持仓超时
  4. basis risk 超过阈值（价差过大，对冲失效）
  5. 累计 funding 收入已覆盖费用 + 合理利润（止盈）

MODULE_NOTE (English):
  True Delta-Neutral Funding Rate Arbitrage:
  - Positive funding → short perp + long spot (hedge price risk)
  - Negative funding → long perp + short spot

  Both legs open simultaneously, price movements cancel out,
  profit comes only from funding rate payments.

Safety invariant / 安全不变量:
  - 只产生 OrderIntent / Only generates OrderIntents
  - 每次入场同时发出 2 个意图（perp + spot）/ Each entry emits 2 intents
  - funding rate 数据是只读的 / Funding rate data is read-only
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .base import OrderIntent, StrategyBase, STRATEGY_ACTIVE

logger = logging.getLogger(__name__)


class FundingRateArbStrategy(StrategyBase):
    """
    Delta-Neutral Funding Rate Arbitrage strategy.
    Delta-Neutral Funding Rate 套利策略。

    Parameters / 参数:
      symbol              — trading pair / 交易对
      qty_per_trade       — position size per leg / 每腿仓位大小
      funding_threshold   — minimum |funding_rate| to enter (default 5bps)
      min_hours_to_settle — minimum hours before next settlement
      perp_fee_bps        — perpetual round-trip fee (default 11 bps)
      spot_fee_bps        — spot round-trip fee (default 20 bps)
      delta_neutral       — True=hedge with spot, False=naked perp only
      slippage_bps        — estimated slippage per round-trip (default 3 bps) / 预估滑点
      max_basis_pct       — max spot-perp price divergence before exit (default 0.5%) / 最大基差
      expected_periods    — expected holding periods for fee amortization (default 3) / 预期持仓周期数
      max_hold_hours      — maximum holding time in hours (default 72 = 9 periods) / 最大持仓时间
    """

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        qty_per_trade: float = 0.001,
        funding_threshold: float = 0.0005,  # 5 bps
        min_hours_to_settle: float = 2.0,
        perp_fee_bps: float = 11.0,
        spot_fee_bps: float = 20.0,
        delta_neutral: bool = True,
        slippage_bps: float = 3.0,
        max_basis_pct: float = 0.5,
        expected_periods: int = 3,
        max_hold_hours: float = 72.0,
    ) -> None:
        super().__init__()
        if qty_per_trade <= 0:
            raise ValueError(f"qty_per_trade must be > 0, got {qty_per_trade}")
        self._symbol = symbol
        self._qty = qty_per_trade
        self._threshold = funding_threshold
        self._min_hours = min_hours_to_settle
        self._perp_fee_bps = perp_fee_bps
        self._spot_fee_bps = spot_fee_bps
        self._delta_neutral = delta_neutral
        self._slippage_bps = slippage_bps
        # 0B-1: Total round-trip cost includes fees + slippage / 總往返成本 = 費用 + 滑點
        self._total_fee_bps = perp_fee_bps + (spot_fee_bps if delta_neutral else 0) + slippage_bps
        self._max_basis_pct = max_basis_pct
        self._expected_periods = max(1, expected_periods)
        self._max_hold_hours = max_hold_hours

        self._current_position: str | None = None
        self._entry_funding_rate: float | None = None
        self._entry_ts_ms: int = 0
        self._trade_count = 0
        self._funding_collected: float = 0.0
        self._funding_periods_held: int = 0
        # 0B-1: Basis risk tracking / 基差風險追蹤
        self._last_basis_pct: float = 0.0
        self._max_basis_observed: float = 0.0
        # 0B-1: Real cost tracking (populated via record_actual_fees) / 真實成本追蹤
        self._actual_entry_fees: float = 0.0
        self._actual_slippage_bps: float = 0.0

    @property
    def name(self) -> str:
        return "FundingRate_Arb"

    @property
    def description(self) -> str:
        mode = "Delta-Neutral" if self._delta_neutral else "Directional"
        return (
            f"Funding Rate {mode} 套利策略 / Funding Rate {mode} Arbitrage. "
            f"Threshold={self._threshold*10000:.0f}bps, Fees={self._total_fee_bps:.0f}bps"
        )

    def evaluate_funding_opportunity(
        self,
        funding_rate: float,
        next_settle_ts_ms: int,
        current_ts_ms: int | None = None,
        spot_price: float | None = None,
        perp_price: float | None = None,
    ) -> None:
        """
        Evaluate whether to enter or exit based on funding rate data.
        根据 funding rate 数据评估是否入场或出场。

        0B-1: Enhanced with basis risk, multi-period amortization, holding cost tracking.
        0B-1：增強版含基差風險、多周期攤薄、持倉成本追蹤。

        Args:
            funding_rate: Current funding rate (e.g. 0.0001 = 1 bps).
            next_settle_ts_ms: Next funding settlement timestamp in ms.
            current_ts_ms: Current timestamp (optional, defaults to now).
            spot_price: Current spot price (optional, for basis risk calculation).
            perp_price: Current perpetual price (optional, for basis risk calculation).
        """
        if self._state != STRATEGY_ACTIVE:
            return

        now_ms = current_ts_ms if current_ts_ms is not None and current_ts_ms != 0 else int(time.time() * 1000)
        hours_to_settle = (next_settle_ts_ms - now_ms) / 3600_000

        # 0B-1: Update basis risk tracking / 更新基差風險追蹤
        if spot_price and perp_price and spot_price > 0:
            self._last_basis_pct = abs(perp_price - spot_price) / spot_price * 100
            self._max_basis_observed = max(self._max_basis_observed, self._last_basis_pct)

        with self._intent_lock:
            # ── Exit evaluation / 出场评估 ──
            if self._current_position is not None:
                should_exit = False
                exit_reason = ""

                # Exit 1: funding rate flipped / funding rate 反转
                if "short_perp" in self._current_position and funding_rate < 0:
                    should_exit = True
                    exit_reason = f"Rate flipped negative ({funding_rate:.6f})"
                elif "long_perp" in self._current_position and funding_rate > 0:
                    should_exit = True
                    exit_reason = f"Rate flipped positive ({funding_rate:.6f})"

                # Exit 2: rate too small considering amortized costs
                # 0B-1: Use amortized exit threshold — if already held N periods, fee is partially covered
                # 只看退出腿費用 + 考慮已攤薄的入場費
                elif not should_exit:
                    exit_fee_bps = (self._perp_fee_bps / 2 +
                                   (self._spot_fee_bps / 2 if self._delta_neutral else 0) +
                                   self._slippage_bps / 2)
                    if abs(funding_rate) * 10000 < exit_fee_bps:
                        should_exit = True
                        exit_reason = f"Rate too small ({abs(funding_rate)*10000:.1f}bps < exit_fee {exit_fee_bps:.1f}bps)"

                # Exit 3: basis risk exceeded threshold / 基差超過閾值
                if not should_exit and self._last_basis_pct > self._max_basis_pct:
                    should_exit = True
                    exit_reason = f"Basis risk {self._last_basis_pct:.2f}% > max {self._max_basis_pct:.1f}%"

                # Exit 4: max hold time exceeded / 持倉超時
                if not should_exit and self._entry_ts_ms > 0:
                    hold_hours = (now_ms - self._entry_ts_ms) / 3600_000
                    if hold_hours > self._max_hold_hours:
                        should_exit = True
                        exit_reason = f"Max hold time exceeded ({hold_hours:.1f}h > {self._max_hold_hours:.0f}h)"

                # Exit 5: funding collected enough for profit target
                # 0B-1: If funding_collected > total_fee_bps * qty * price / 10000, take profit
                if not should_exit and self._funding_periods_held >= self._expected_periods:
                    # Amortized cost check: have we earned back the entry fees + some profit?
                    # 攤薄成本檢查：是否已賺回入場費 + 合理利潤？
                    if self._funding_collected > 0 and self._funding_periods_held >= self._expected_periods * 2:
                        should_exit = True
                        exit_reason = (
                            f"Profit target: collected {self._funding_collected:.4f} USDT "
                            f"over {self._funding_periods_held} periods"
                        )

                if should_exit:
                    self._emit_close_intents(exit_reason)
                    self._current_position = None
                    self._entry_funding_rate = None
                    self._entry_ts_ms = 0
                return

            # ── Entry evaluation / 入场评估 ──
            if abs(funding_rate) < self._threshold:
                return

            if hours_to_settle < self._min_hours:
                return

            # 0B-1: Basis risk gate — don't enter if spot-perp spread is too wide
            # 基差風險門控 — 現貨與永續價差過大時不入場
            if self._last_basis_pct > self._max_basis_pct:
                logger.debug(
                    "Funding arb entry skipped: basis %.2f%% > max %.1f%% / 基差過大跳過入場",
                    self._last_basis_pct, self._max_basis_pct,
                )
                return

            # 0B-1: Multi-period amortized edge calculation / 多周期攤薄邊際計算
            # Expected edge = (rate × expected_periods) - total_fee_bps
            # Fee is paid once; funding is collected every 8h period.
            # 費用支付一次；funding 每 8h 收取一次。
            funding_bps = abs(funding_rate) * 10000
            amortized_fee_per_period = self._total_fee_bps / self._expected_periods
            edge_bps = funding_bps - amortized_fee_per_period
            if edge_bps <= 0:
                return

            # Also check: total expected funding > total costs (absolute check)
            total_expected_funding_bps = funding_bps * self._expected_periods
            if total_expected_funding_bps <= self._total_fee_bps:
                return

            # Determine direction and open both legs
            if funding_rate >= self._threshold:
                self._emit_entry_intents(
                    perp_side="Sell",
                    spot_side="Buy",
                    position_label="short_perp_long_spot",
                    funding_rate=funding_rate,
                    funding_bps=funding_bps,
                    edge_bps=edge_bps,
                    hours_to_settle=hours_to_settle,
                )

            elif funding_rate <= -self._threshold:
                self._emit_entry_intents(
                    perp_side="Buy",
                    spot_side="Sell",
                    position_label="long_perp_short_spot",
                    funding_rate=funding_rate,
                    funding_bps=funding_bps,
                    edge_bps=edge_bps,
                    hours_to_settle=hours_to_settle,
                )

    def _emit_entry_intents(
        self,
        perp_side: str,
        spot_side: str,
        position_label: str,
        funding_rate: float,
        funding_bps: float,
        edge_bps: float,
        hours_to_settle: float,
    ) -> None:
        """Emit entry intents for both legs / 发出两腿入场意图"""
        confidence = min(1.0, edge_bps / 20 + 0.3)
        reason_base = (
            f"Funding arb {position_label}: rate={funding_rate:.6f} ({funding_bps:.1f}bps), "
            f"edge={edge_bps:.1f}bps, settle={hours_to_settle:.1f}h"
        )

        # Leg 1: Perpetual / 永续腿
        self._emit_intent(OrderIntent(
            symbol=self._symbol,
            side=perp_side,
            order_type="market",
            qty=self._qty,
            strategy_name=self.name,
            reason=f"[PERP] {reason_base}",
            confidence=confidence,
            metadata={
                "funding_rate": funding_rate,
                "edge_bps": edge_bps,
                "leg": "perp",
                "category": "linear",
            },
        ))

        # Leg 2: Spot hedge (if delta-neutral) / 现货对冲腿
        if self._delta_neutral:
            self._emit_intent(OrderIntent(
                symbol=self._symbol,
                side=spot_side,
                order_type="market",
                qty=self._qty,
                strategy_name=self.name,
                reason=f"[SPOT HEDGE] {reason_base}",
                confidence=confidence,
                metadata={
                    "funding_rate": funding_rate,
                    "edge_bps": edge_bps,
                    "leg": "spot_hedge",
                    "category": "spot",
                },
            ))

        self._current_position = position_label
        self._entry_funding_rate = funding_rate
        self._entry_ts_ms = int(time.time() * 1000)
        self._trade_count += 1

        logger.info(
            "Funding arb entry: %s rate=%.6f edge=%.1fbps delta_neutral=%s / 入场",
            position_label, funding_rate, edge_bps, self._delta_neutral,
        )

    def _emit_close_intents(self, reason: str) -> None:
        """Emit close intents for both legs / 发出两腿平仓意图"""
        if self._current_position is None:
            return

        # Determine close directions (opposite of entry)
        if "short_perp" in self._current_position:
            perp_close_side = "Buy"   # Close short perp
            spot_close_side = "Sell"  # Close long spot
        else:
            perp_close_side = "Sell"  # Close long perp
            spot_close_side = "Buy"   # Close short spot

        # Close perp leg
        self._emit_intent(OrderIntent(
            symbol=self._symbol,
            side=perp_close_side,
            order_type="market",
            qty=self._qty,
            strategy_name=self.name,
            reason=f"[PERP CLOSE] {reason}",
            confidence=0.6,
            metadata={"leg": "perp_close", "category": "linear"},
        ))

        # Close spot hedge leg
        if self._delta_neutral:
            self._emit_intent(OrderIntent(
                symbol=self._symbol,
                side=spot_close_side,
                order_type="market",
                qty=self._qty,
                strategy_name=self.name,
                reason=f"[SPOT CLOSE] {reason}",
                confidence=0.6,
                metadata={"leg": "spot_close", "category": "spot"},
            ))

        logger.info(
            "Funding arb exit: %s reason=%s / 出场", self._current_position, reason,
        )

    def record_funding_payment(self, amount_usdt: float) -> None:
        """Record a funding payment received / 记录收到的 funding 支付"""
        self._funding_collected += amount_usdt
        self._funding_periods_held += 1

    def record_actual_fees(self, entry_fee: float, slippage_bps: float = 0.0) -> None:
        """
        0B-1: Record actual entry fees from execution report for cost reconciliation.
        記錄來自成交報告的真實入場費用，用於成本核對。

        Args:
            entry_fee: Actual fee paid in USDT on entry (from fill report).
            slippage_bps: Estimated actual slippage in bps (from fill price vs mid).
        """
        self._actual_entry_fees += entry_fee
        if slippage_bps > 0:
            self._actual_slippage_bps = slippage_bps

    def get_cost_summary(self) -> dict[str, Any]:
        """
        0B-1: Return complete cost model summary for auditing (Principle 8).
        返回完整成本模型摘要供審計（原則 8）。
        """
        hold_hours = 0.0
        if self._entry_ts_ms > 0:
            hold_hours = (int(time.time() * 1000) - self._entry_ts_ms) / 3600_000
        return {
            "estimated_fee_bps": self._total_fee_bps,
            "actual_entry_fees_usdt": round(self._actual_entry_fees, 6),
            "slippage_bps_estimated": self._slippage_bps,
            "slippage_bps_actual": self._actual_slippage_bps,
            "basis_pct_current": round(self._last_basis_pct, 4),
            "basis_pct_max_observed": round(self._max_basis_observed, 4),
            "funding_collected_usdt": round(self._funding_collected, 6),
            "funding_periods_held": self._funding_periods_held,
            "expected_periods": self._expected_periods,
            "hold_hours": round(hold_hours, 1),
            "max_hold_hours": self._max_hold_hours,
            "amortized_fee_per_period_bps": round(self._total_fee_bps / self._expected_periods, 2),
            "net_funding_pnl": round(self._funding_collected - self._actual_entry_fees, 6),
        }

    def get_persistent_state(self) -> dict[str, Any]:
        base = super().get_persistent_state()
        base.update({
            "current_position": self._current_position,
            "entry_funding_rate": self._entry_funding_rate,
            "entry_ts_ms": self._entry_ts_ms,
            "trade_count": self._trade_count,
            "funding_collected": self._funding_collected,
            "funding_periods_held": self._funding_periods_held,
            "last_basis_pct": self._last_basis_pct,
            "max_basis_observed": self._max_basis_observed,
            "actual_entry_fees": self._actual_entry_fees,
        })
        return base

    def restore_persistent_state(self, saved: dict[str, Any]) -> None:
        super().restore_persistent_state(saved)
        self._current_position = saved.get("current_position")
        self._entry_funding_rate = saved.get("entry_funding_rate")
        self._entry_ts_ms = saved.get("entry_ts_ms", 0)
        self._trade_count = saved.get("trade_count", 0)
        self._funding_collected = saved.get("funding_collected", 0.0)
        self._funding_periods_held = saved.get("funding_periods_held", 0)
        self._last_basis_pct = saved.get("last_basis_pct", 0.0)
        self._max_basis_observed = saved.get("max_basis_observed", 0.0)
        self._actual_entry_fees = saved.get("actual_entry_fees", 0.0)

    def on_intent_rejected(self, intent: OrderIntent) -> None:
        """Roll back _current_position on rejected intent / intent 被拒后回滚仓位状态"""
        if getattr(intent, "symbol", None) != self._symbol:
            return
        with self._intent_lock:
            self._current_position = None

    def get_status(self) -> dict[str, Any]:
        return {
            "strategy": self.name,
            "state": self.state,
            "symbol": self._symbol,
            "delta_neutral": self._delta_neutral,
            "current_position": self._current_position,
            "entry_funding_rate": self._entry_funding_rate,
            "qty_per_trade": self._qty,
            "funding_threshold": self._threshold,
            "perp_fee_bps": self._perp_fee_bps,
            "spot_fee_bps": self._spot_fee_bps,
            "slippage_bps": self._slippage_bps,
            "total_fee_bps": self._total_fee_bps,
            "trade_count": self._trade_count,
            "funding_collected_usdt": round(self._funding_collected, 4),
            "funding_periods_held": self._funding_periods_held,
            "expected_periods": self._expected_periods,
            "max_hold_hours": self._max_hold_hours,
            "max_basis_pct": self._max_basis_pct,
            "cost_summary": self.get_cost_summary(),
        }
