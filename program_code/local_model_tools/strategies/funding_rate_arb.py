"""
Funding Rate Arbitrage Strategy / Funding Rate 套利策略

MODULE_NOTE (中文):
  Bybit 永续合约每 8 小时结算一次 funding rate。
  当 funding rate 极端时存在套利机会：
  - 正 funding rate 过高（多头付空头）→ 做空收取 funding
  - 负 funding rate 过低（空头付多头）→ 做多收取 funding

  这是一个低频、低风险、低收益的策略，适合作为"底仓"运行。
  核心优势：不需要预测价格方向，只需 funding rate 足够覆盖手续费。

  Agent 偏好这类策略的原因：
  - AI 注意力成本低（不需要频繁监控）
  - 边际明确（funding rate 是已知数据，不是预测）
  - 风险可控（holding 成本主要是保证金机会成本）

  入场条件：
  1. |funding_rate| > threshold（默认 0.01% = 10bps）
  2. 预估 funding 收入 > 手续费 + 滑点 + AI 注意力成本
  3. 距离下次结算时间足够（至少 2 小时）

  出场条件：
  1. 收到 funding 后自动评估是否继续持有
  2. funding rate 反转（方向变了）→ 平仓
  3. 持仓成本（含 AI 注意力税）超过预期收益 → 平仓

  注意：当前实现为 Paper Trading 模拟版，funding rate 数据需从 Bybit API 获取。

MODULE_NOTE (English):
  Bybit perpetual contracts settle funding rate every 8 hours.
  Extreme funding rates present arbitrage opportunities:
  - High positive rate (longs pay shorts) → go short to collect funding
  - High negative rate (shorts pay longs) → go long to collect funding

  Low-frequency, low-risk, low-return strategy. Good as a "base position".
  Core advantage: doesn't need to predict price direction, only needs funding
  rate to cover fees.

  Why Agent prefers this strategy:
  - Low AI attention cost (infrequent monitoring)
  - Clear edge (funding rate is known data, not prediction)
  - Controllable risk (holding cost is mainly margin opportunity cost)

Safety invariant / 安全不变量:
  - 只产生 OrderIntent / Only generates OrderIntents
  - funding rate 数据是只读的 / Funding rate data is read-only
"""

from __future__ import annotations

import time
from typing import Any

from .base import OrderIntent, StrategyBase, STRATEGY_ACTIVE


class FundingRateArbStrategy(StrategyBase):
    """
    Funding Rate Arbitrage strategy.
    Funding Rate 套利策略。

    Parameters:
      symbol              — trading pair / 交易对
      qty_per_trade       — position size / 仓位大小
      funding_threshold   — minimum |funding_rate| to enter (default 0.0001 = 1bps) / 入场最小 funding rate
      min_hours_to_settle — minimum hours before next settlement / 距结算最少小时数
      fee_bps             — estimated round-trip fee in bps / 预估来回手续费（基点）
    """

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        qty_per_trade: float = 0.001,
        funding_threshold: float = 0.0001,  # 1 bps
        min_hours_to_settle: float = 2.0,
        fee_bps: float = 11.0,  # taker×2 = 0.055%×2 = 11 bps
    ) -> None:
        super().__init__()
        self._symbol = symbol
        self._qty = qty_per_trade
        self._threshold = funding_threshold
        self._min_hours = min_hours_to_settle
        self._fee_bps = fee_bps
        self._current_position: str | None = None
        self._entry_funding_rate: float | None = None
        self._trade_count = 0
        self._funding_collected: float = 0.0  # Cumulative funding collected / 累计收取的 funding

    @property
    def name(self) -> str:
        return "FundingRate_Arb"

    @property
    def description(self) -> str:
        return (
            "Funding Rate 套利策略 / Funding Rate Arbitrage strategy. "
            "当 funding rate 极端时做反向，收取 funding 费用"
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

        This should be called periodically (e.g., every hour) with the latest
        funding rate from Bybit API.
        应定期调用（如每小时），传入 Bybit API 的最新 funding rate。

        Args:
          funding_rate     — current predicted funding rate (e.g., 0.0003 = 3bps)
                            当前预测的 funding rate
          next_settle_ts_ms — next settlement timestamp in ms / 下次结算时间戳
          current_ts_ms    — current time (None=now) / 当前时间
        """
        if self._state != STRATEGY_ACTIVE:
            return

        now_ms = current_ts_ms or int(time.time() * 1000)
        hours_to_settle = (next_settle_ts_ms - now_ms) / 3600_000

        # Check if we should exit / 检查是否应出场
        if self._current_position is not None:
            should_exit = False
            exit_reason = ""

            # Exit if funding rate flipped / funding rate 反转则出场
            if self._current_position == "short" and funding_rate < 0:
                should_exit = True
                exit_reason = f"Funding rate flipped negative ({funding_rate:.6f}) / Funding rate 转负"
            elif self._current_position == "long" and funding_rate > 0:
                should_exit = True
                exit_reason = f"Funding rate flipped positive ({funding_rate:.6f}) / Funding rate 转正"

            # Exit if funding too small to cover costs / funding 不足以覆盖成本
            elif abs(funding_rate) * 10000 < self._fee_bps * 0.3:
                should_exit = True
                exit_reason = f"Funding too small ({abs(funding_rate)*10000:.1f}bps vs fee {self._fee_bps}bps) / Funding 过小"

            if should_exit:
                side = "Buy" if self._current_position == "short" else "Sell"
                self._emit_intent(OrderIntent(
                    symbol=self._symbol, side=side, order_type="market",
                    qty=self._qty, strategy_name=self.name,
                    reason=f"Exit funding arb: {exit_reason}",
                    confidence=0.6,
                ))
                self._current_position = None
                self._entry_funding_rate = None
            return

        # Check if we should enter / 检查是否应入场
        if abs(funding_rate) < self._threshold:
            return  # Funding rate too small / Funding rate 太小

        if hours_to_settle < self._min_hours:
            return  # Too close to settlement / 距结算时间太近

        # Calculate expected edge / 计算预期边际
        funding_bps = abs(funding_rate) * 10000
        edge_bps = funding_bps - self._fee_bps
        if edge_bps <= 0:
            return  # Not enough edge after fees / 扣除手续费后无边际

        # Determine direction / 确定方向
        if funding_rate > self._threshold:
            # Positive rate: longs pay shorts → go short / 正费率：多付空 → 做空
            self._emit_intent(OrderIntent(
                symbol=self._symbol, side="Sell", order_type="market",
                qty=self._qty, strategy_name=self.name,
                reason=(
                    f"Funding arb short: rate={funding_rate:.6f} ({funding_bps:.1f}bps), "
                    f"edge={edge_bps:.1f}bps, settle in {hours_to_settle:.1f}h / "
                    f"Funding 套利做空"
                ),
                confidence=min(1.0, edge_bps / 20 + 0.3),
                metadata={"funding_rate": funding_rate, "edge_bps": edge_bps},
            ))
            self._current_position = "short"
            self._entry_funding_rate = funding_rate
            self._trade_count += 1

        elif funding_rate < -self._threshold:
            # Negative rate: shorts pay longs → go long / 负费率：空付多 → 做多
            self._emit_intent(OrderIntent(
                symbol=self._symbol, side="Buy", order_type="market",
                qty=self._qty, strategy_name=self.name,
                reason=(
                    f"Funding arb long: rate={funding_rate:.6f} ({funding_bps:.1f}bps), "
                    f"edge={edge_bps:.1f}bps, settle in {hours_to_settle:.1f}h / "
                    f"Funding 套利做多"
                ),
                confidence=min(1.0, edge_bps / 20 + 0.3),
                metadata={"funding_rate": funding_rate, "edge_bps": edge_bps},
            ))
            self._current_position = "long"
            self._entry_funding_rate = funding_rate
            self._trade_count += 1

    def record_funding_payment(self, amount_usdt: float) -> None:
        """
        Record a funding payment received / 记录收到的 funding 支付

        Args:
          amount_usdt — funding payment amount (positive = received) / 收到的金额
        """
        self._funding_collected += amount_usdt

    def get_status(self) -> dict[str, Any]:
        return {
            "strategy": self.name,
            "state": self.state,
            "symbol": self._symbol,
            "current_position": self._current_position,
            "entry_funding_rate": self._entry_funding_rate,
            "qty_per_trade": self._qty,
            "funding_threshold": self._threshold,
            "fee_bps": self._fee_bps,
            "trade_count": self._trade_count,
            "funding_collected_usdt": round(self._funding_collected, 4),
        }
