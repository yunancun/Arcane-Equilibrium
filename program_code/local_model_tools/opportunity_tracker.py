"""
1-7: OpportunityTracker — Virtual PnL Tracking / 虛擬 PnL 追蹤（遺憾追蹤）
==========================================================================

MODULE_NOTE (中文):
  OpportunityTracker 追蹤被跳過的交易機會的虛擬表現：
  - record_skipped()：記錄被過濾/拒絕的信號及其入場價
  - update_virtual_pnl()：每次 tick 更新虛擬 PnL
  - get_regret_summary()：計算 bullets_dodged（避開的虧損）vs regret（錯過的盈利）

  [Q2] 虛擬 PnL 扣除 2× 預估費用（0.075%×2 = 0.15%）防止假性後悔偏差
  [Q3] 方向判斷使用歸一化比較（avg_regret vs avg_dodged），非絕對值
  [R1-8] 每側至少 5 個樣本才判斷方向

MODULE_NOTE (English):
  OpportunityTracker tracks virtual performance of skipped trading opportunities:
  - record_skipped(): record filtered/rejected signals with entry price
  - update_virtual_pnl(): update virtual PnL every tick
  - get_regret_summary(): compute bullets_dodged vs regret_from_undertrading

  [Q2] Virtual PnL deducts 2× estimated fee (0.075%×2 = 0.15%) to suppress false regret
  [Q3] Direction uses normalized comparison (avg_regret vs avg_dodged), not absolute
  [R1-8] Minimum 5 samples per side for direction judgment
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Constants / 常量
_ESTIMATED_FEE_PCT = 0.075   # One-way estimated fee % / 單邊預估費用
_VIRTUAL_SL_PCT = -5.0       # Virtual stop-loss % / 虛擬止損
_VIRTUAL_TP_PCT = 10.0       # Virtual take-profit % / 虛擬止盈
_TTL_MS = 7 * 24 * 3600 * 1000  # 7 days TTL / 7 天有效期
_MAX_TRACKED = 100            # Max active opportunities / 最大活躍機會數
_MAX_SETTLED = 500            # Max settled history / 最大結算歷史
_MIN_SAMPLES = 5              # [R1-8] Min samples per side / 每側最少樣本數


@dataclass
class SkippedOpportunity:
    """A single skipped trading opportunity / 單個被跳過的交易機會"""
    opp_id: str = ""
    symbol: str = ""
    direction: str = "long"
    entry_price: float = 0.0
    entry_ts_ms: int = 0
    signal_confidence: float = 0.0
    skip_reason: str = ""
    skip_source: str = ""
    strategy_name: str = ""
    # Virtual tracking / 虛擬追蹤
    current_pnl_pct: float = 0.0
    peak_favorable_pct: float = 0.0
    peak_adverse_pct: float = 0.0
    is_settled: bool = False
    settle_reason: str = ""


class OpportunityTracker:
    """
    Track skipped opportunities and compute regret/bullets-dodged metrics.
    追蹤被跳過的機會並計算遺憾/避開的損失指標。
    """

    def __init__(self) -> None:
        self._active: deque[SkippedOpportunity] = deque(maxlen=_MAX_TRACKED)
        self._settled: deque[SkippedOpportunity] = deque(maxlen=_MAX_SETTLED)
        self._next_id = 0
        self._cached_summary: dict[str, Any] | None = None

    def record_skipped(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        signal_confidence: float = 0.5,
        skip_reason: str = "",
        skip_source: str = "unknown",
        strategy_name: str = "",
    ) -> str:
        """
        Record a skipped opportunity for virtual PnL tracking.
        記錄一個被跳過的機會供虛擬 PnL 追蹤。

        Returns: opportunity ID.
        """
        self._next_id += 1
        opp = SkippedOpportunity(
            opp_id=f"opp_{self._next_id}",
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            entry_ts_ms=int(time.time() * 1000),
            signal_confidence=signal_confidence,
            skip_reason=skip_reason[:80],
            skip_source=skip_source,
            strategy_name=strategy_name,
        )
        self._active.append(opp)
        # [R1-2] Invalidate cache / 失效緩存
        self._cached_summary = None
        return opp.opp_id

    def update_virtual_pnl(self, current_prices: dict[str, float]) -> None:
        """
        Update virtual PnL for all active opportunities and settle if triggered.
        更新所有活躍機會的虛擬 PnL 並在觸發條件時結算。

        [Q2] Virtual PnL deducts 2× fee to suppress false regret bias.
        虛擬 PnL 扣除 2× 費用以抑制虛假遺憾偏差。
        """
        now_ms = int(time.time() * 1000)
        to_settle: list[int] = []

        for i, opp in enumerate(self._active):
            if opp.is_settled:
                continue

            price = current_prices.get(opp.symbol, 0.0)
            if price <= 0 or opp.entry_price <= 0:
                continue

            # Raw PnL / 原始 PnL
            if opp.direction == "long":
                raw_pct = (price - opp.entry_price) / opp.entry_price * 100
            else:
                raw_pct = (opp.entry_price - price) / opp.entry_price * 100

            # [Q2] Deduct 2× friction cost / 扣除 2× 摩擦成本
            pnl_pct = raw_pct - 2 * _ESTIMATED_FEE_PCT

            opp.current_pnl_pct = pnl_pct
            opp.peak_favorable_pct = max(opp.peak_favorable_pct, pnl_pct)
            opp.peak_adverse_pct = min(opp.peak_adverse_pct, pnl_pct)

            # Settlement triggers / 結算觸發條件
            if pnl_pct <= _VIRTUAL_SL_PCT:
                opp.is_settled = True
                opp.settle_reason = "virtual_sl"
                to_settle.append(i)
            elif pnl_pct >= _VIRTUAL_TP_PCT:
                opp.is_settled = True
                opp.settle_reason = "virtual_tp"
                to_settle.append(i)
            elif now_ms - opp.entry_ts_ms > _TTL_MS:
                opp.is_settled = True
                opp.settle_reason = "ttl_expired"
                to_settle.append(i)

        # [E3] Flush settled to history / 批量移動已結算到歷史
        if to_settle:
            self._flush_settled()
            self._cached_summary = None

    def _flush_settled(self) -> None:
        """Move settled opportunities from active to history / 將已結算機會移到歷史"""
        remaining: list[SkippedOpportunity] = []
        for opp in self._active:
            if opp.is_settled:
                self._settled.append(opp)
            else:
                remaining.append(opp)
        self._active.clear()
        for opp in remaining:
            self._active.append(opp)

    def get_regret_summary(self, window_days: int = 7) -> dict[str, Any]:
        """
        Compute regret summary: bullets_dodged vs regret_from_undertrading.
        計算遺憾摘要：避開的虧損 vs 過度保守的遺憾。

        [Q3] Normalized direction comparison, [R1-8] min 5 samples.
        """
        if self._cached_summary is not None:
            return self._cached_summary

        cutoff_ms = int(time.time() * 1000) - window_days * 24 * 3600 * 1000

        # Gather all relevant opportunities (active + settled within window)
        relevant: list[SkippedOpportunity] = []
        for opp in self._active:
            if opp.entry_ts_ms >= cutoff_ms:
                relevant.append(opp)
        for opp in self._settled:
            if opp.entry_ts_ms >= cutoff_ms:
                relevant.append(opp)

        would_profit: list[float] = []
        would_loss: list[float] = []
        top_missed_desc = ""
        top_missed_pnl = 0.0

        for opp in relevant:
            pnl = opp.current_pnl_pct
            if pnl > 0:
                would_profit.append(pnl)
                if pnl > top_missed_pnl:
                    top_missed_pnl = pnl
                    top_missed_desc = f"{opp.symbol} {opp.direction} +{pnl:.1f}% ({opp.skip_source})"
            else:
                would_loss.append(abs(pnl))

        regret = sum(would_profit)
        dodged = sum(would_loss)

        # [Q3] Normalized direction judgment / 歸一化方向判斷
        avg_regret = regret / len(would_profit) if would_profit else 0.0
        avg_dodged = dodged / len(would_loss) if would_loss else 0.0

        # [R1-8] Require >= 5 samples per side / 每側至少 5 個樣本
        if avg_regret > avg_dodged * 1.3 and len(would_profit) >= _MIN_SAMPLES:
            direction = "undertrading"
        elif avg_dodged > avg_regret * 1.3 and len(would_loss) >= _MIN_SAMPLES:
            direction = "overtrading"
        else:
            direction = "balanced"

        total = len(relevant)
        hit_rate = len(would_profit) / total if total > 0 else 0.0

        self._cached_summary = {
            "bullets_dodged": round(dodged, 4),
            "regret_from_undertrading": round(regret, 4),
            "net_regret_direction": direction,
            "top_missed": top_missed_desc[:80],
            "total_tracked": len(self._active),
            "total_settled": len(self._settled),
            "hit_rate_if_taken": round(hit_rate, 4),
        }
        return self._cached_summary

    def get_status(self) -> dict[str, Any]:
        return {
            "active_count": len(self._active),
            "settled_count": len(self._settled),
            "summary": self.get_regret_summary(),
        }
