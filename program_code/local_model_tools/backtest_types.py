"""
STUB: Backtest types / 回测类型 stub.

MODULE_NOTE (EN): Backtest runs in Rust `openclaw_core::backtest`. These
  dataclasses are retained for legacy imports; they are construction-only
  shells with zero-filled defaults.
MODULE_NOTE (中): 回测已迁移至 Rust `openclaw_core::backtest`。此模块仅保留
  dataclass 定义供旧 import，字段默认零值。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ANNUALIZATION_FACTORS: dict[str, int] = {
    "1m": 525_600,
    "5m": 105_120,
    "15m": 35_040,
    "30m": 17_520,
    "1h": 8_760,
    "4h": 2_190,
    "1d": 365,
}
MIN_BARS_REQUIRED: int = 30
MIN_TRADES_FOR_STATS: int = 2


@dataclass
class BacktestConfig:
    symbol: str = ""
    timeframe: str = "1h"
    strategy_name: str = ""
    initial_capital: float = 1000.0
    fee_rate_taker: float = 0.00055
    fee_rate_maker: float = 0.0002
    slippage_bps: float = 5.0
    position_size_pct: float = 0.02
    stop_loss_pct: float = 0.02
    backtest_mode: bool = True


@dataclass
class BacktestTrade:
    trade_id: int = 0
    symbol: str = ""
    direction: str = ""
    entry_bar_idx: int = 0
    exit_bar_idx: int = 0
    entry_price: float = 0.0
    exit_price: float = 0.0
    qty: float = 0.0
    notional_usd: float = 0.0
    entry_fee: float = 0.0
    exit_fee: float = 0.0
    gross_pnl: float = 0.0
    net_pnl: float = 0.0
    pnl_pct: float = 0.0
    exit_reason: str = ""
    signal_source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_bar_idx": self.entry_bar_idx,
            "exit_bar_idx": self.exit_bar_idx,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "qty": self.qty,
            "notional_usd": self.notional_usd,
            "entry_fee": self.entry_fee,
            "exit_fee": self.exit_fee,
            "gross_pnl": self.gross_pnl,
            "net_pnl": self.net_pnl,
            "pnl_pct": self.pnl_pct,
            "exit_reason": self.exit_reason,
            "signal_source": self.signal_source,
        }


@dataclass
class BacktestResult:
    symbol: str = ""
    timeframe: str = "1h"
    strategy_name: str = ""
    initial_capital: float = 0.0
    final_capital: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_net_pnl: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    profit_factor: float = 0.0
    avg_trade_pct: float = 0.0
    total_bars_processed: int = 0
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    config: BacktestConfig | None = None
    warning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "strategy_name": self.strategy_name,
            "initial_capital": self.initial_capital,
            "final_capital": self.final_capital,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "total_net_pnl": self.total_net_pnl,
            "total_return_pct": self.total_return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "avg_win_pct": self.avg_win_pct,
            "avg_loss_pct": self.avg_loss_pct,
            "profit_factor": self.profit_factor,
            "avg_trade_pct": self.avg_trade_pct,
            "total_bars_processed": self.total_bars_processed,
            "trades": [t.to_dict() for t in self.trades],
            "equity_curve": list(self.equity_curve),
            "warning": self.warning or "backtest runs in Rust engine",
        }


__all__ = [
    "ANNUALIZATION_FACTORS",
    "MIN_BARS_REQUIRED",
    "MIN_TRADES_FOR_STATS",
    "BacktestConfig",
    "BacktestTrade",
    "BacktestResult",
]
