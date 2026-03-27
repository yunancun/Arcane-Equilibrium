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

  费用模型：
  - 永续 taker: 0.055% × 2 sides = 11 bps
  - 现货 taker: 0.10% × 2 sides = 20 bps（Bybit VIP0 spot taker 0.10%）
  - 总来回费用 ≈ 31 bps
  - 因此 funding rate 需 > 31 bps 才有正期望（约 0.0031）
  - 但如果持仓跨多个 funding 周期（每 8h），费用摊薄

  入场条件：
  1. |funding_rate| > threshold（默认 5bps = 0.0005）
  2. 预估多周期 funding 收入 > 总费用
  3. 距下次结算 ≥ 2 小时

  出场条件：
  1. funding rate 反转
  2. funding rate 太小不值得继续持有
  3. 持仓超时

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

    Parameters:
      symbol              — trading pair / 交易对
      qty_per_trade       — position size per leg / 每腿仓位大小
      funding_threshold   — minimum |funding_rate| to enter (default 0.0005 = 5bps)
      min_hours_to_settle — minimum hours before next settlement
      perp_fee_bps        — perpetual round-trip fee (default 11 bps)
      spot_fee_bps        — spot round-trip fee (default 20 bps)
      delta_neutral       — True=hedge with spot, False=naked perp only (legacy mode)
    """

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        qty_per_trade: float = 0.001,
        funding_threshold: float = 0.0005,  # 5 bps (higher than before — needs to cover 2-leg fees)
        min_hours_to_settle: float = 2.0,
        perp_fee_bps: float = 11.0,
        spot_fee_bps: float = 20.0,
        delta_neutral: bool = True,
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
        self._total_fee_bps = perp_fee_bps + (spot_fee_bps if delta_neutral else 0)

        self._current_position: str | None = None  # "short_perp_long_spot" / "long_perp_short_spot" / None
        self._entry_funding_rate: float | None = None
        self._entry_ts_ms: int = 0
        self._trade_count = 0
        self._funding_collected: float = 0.0
        self._funding_periods_held: int = 0

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
    ) -> None:
        """
        Evaluate whether to enter or exit based on funding rate data.
        根据 funding rate 数据评估是否入场或出场。
        """
        if self._state != STRATEGY_ACTIVE:
            return

        now_ms = current_ts_ms or int(time.time() * 1000)
        hours_to_settle = (next_settle_ts_ms - now_ms) / 3600_000

        with self._intent_lock:
            # ── Exit evaluation / 出场评估 ──
            if self._current_position is not None:
                should_exit = False
                exit_reason = ""

                # Exit if funding rate flipped / funding rate 反转
                if "short_perp" in self._current_position and funding_rate < 0:
                    should_exit = True
                    exit_reason = f"Rate flipped negative ({funding_rate:.6f})"
                elif "long_perp" in self._current_position and funding_rate > 0:
                    should_exit = True
                    exit_reason = f"Rate flipped positive ({funding_rate:.6f})"

                # Exit if rate too small to cover ongoing costs
                # Use only the exit-leg fee (not full round-trip, entry fee is sunk)
                # 只用退出腿费用（入场费已沉没）
                elif abs(funding_rate) * 10000 < (self._perp_fee_bps / 2 + (self._spot_fee_bps / 2 if self._delta_neutral else 0)):
                    should_exit = True
                    exit_reason = f"Rate too small ({abs(funding_rate)*10000:.1f}bps < exit_fee)"

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

            # Expected edge: funding bps - total fee bps
            funding_bps = abs(funding_rate) * 10000
            edge_bps = funding_bps - self._total_fee_bps
            if edge_bps <= 0:
                return

            # Determine direction and open both legs
            if funding_rate > self._threshold:
                # Positive rate: longs pay shorts
                # → Short perp (collect funding) + Long spot (hedge)
                self._emit_entry_intents(
                    perp_side="Sell",
                    spot_side="Buy",
                    position_label="short_perp_long_spot",
                    funding_rate=funding_rate,
                    funding_bps=funding_bps,
                    edge_bps=edge_bps,
                    hours_to_settle=hours_to_settle,
                )

            elif funding_rate < -self._threshold:
                # Negative rate: shorts pay longs
                # → Long perp (collect funding) + Short spot (hedge)
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

    def get_persistent_state(self) -> dict[str, Any]:
        base = super().get_persistent_state()
        base.update({
            "current_position": self._current_position,
            "entry_funding_rate": self._entry_funding_rate,
            "entry_ts_ms": self._entry_ts_ms,
            "trade_count": self._trade_count,
            "funding_collected": self._funding_collected,
            "funding_periods_held": self._funding_periods_held,
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
            "total_fee_bps": self._total_fee_bps,
            "trade_count": self._trade_count,
            "funding_collected_usdt": round(self._funding_collected, 4),
            "funding_periods_held": self._funding_periods_held,
        }
