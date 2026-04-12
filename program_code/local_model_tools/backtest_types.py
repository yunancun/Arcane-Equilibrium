"""
Backtest Types — Data classes for backtest configuration, trades, and results.
回测类型 — 回测配置、交易记录、结果的数据类。

MODULE_NOTE (EN): Extracted from backtest_engine.py (FIX-08 file size).
  Contains BacktestConfig, BacktestTrade, BacktestResult dataclasses and
  related constants. Pure data definitions — no computation logic.
MODULE_NOTE (中): 从 backtest_engine.py 提取（FIX-08 文件大小）。
  包含 BacktestConfig、BacktestTrade、BacktestResult 数据类和相关常量。
  纯数据定义 — 无计算逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# =============================================================================
# Annualization factors per timeframe / 每个时间框架的年化因子
# Bars per year for each timeframe (used for Sharpe ratio annualization)
# 每年该时间框架的 K 线根数（用于 Sharpe 年化）
# =============================================================================
ANNUALIZATION_FACTORS: dict[str, int] = {
    "1m":  525600,
    "5m":  105120,
    "15m": 35040,
    "30m": 17520,
    "1h":  8760,
    "4h":  2190,
    "1d":  365,
}

# Minimum number of klines required to run a backtest
# 回测所需的最少 K 线根数
MIN_BARS_REQUIRED = 30

# Minimum trades for meaningful statistics
# 有意义统计所需的最少交易数
MIN_TRADES_FOR_STATS = 2


# =============================================================================
# BacktestConfig — Backtest Configuration / 回测配置
# =============================================================================

@dataclass
class BacktestConfig:
    """
    Configuration for a single backtest run.
    单次回测运行的配置。

    All fields are documented with their purpose and valid ranges.
    所有字段均记录了其用途和有效范围。

    Fields:
      symbol           — trading pair (e.g., "BTCUSDT") / 交易对
      timeframe        — kline timeframe (e.g., "5m", "1h") / K线时间框架
      strategy_name    — identifier for the signal rule set / 策略名称标识符
      initial_capital  — starting capital in USDT / 初始资金（USDT）
      fee_rate_taker   — taker fee rate (0.00055 = 0.055%) / 吃单手续费率
      fee_rate_maker   — maker fee rate (0.0002 = 0.02%) / 挂单手续费率
      slippage_bps     — simulated slippage in basis points / 模拟滑点（基点）
      position_size_pct — fraction of capital per trade (0.02 = 2%) / 每笔交易资金占比
      stop_loss_pct    — stop-loss as fraction of entry price (0.02 = 2%) / 止损比例
      backtest_mode    — MUST be True; prevents misuse as live config / 必须为 True，防误用
    """
    symbol: str
    timeframe: str
    strategy_name: str
    initial_capital: float = 1000.0
    fee_rate_taker: float = 0.00055
    fee_rate_maker: float = 0.0002
    slippage_bps: float = 5.0
    position_size_pct: float = 0.02
    stop_loss_pct: float = 0.02
    # Safety: backtest_mode MUST be True. BacktestEngine.run() raises ValueError if False.
    # 安全守护：backtest_mode 必须为 True。BacktestEngine.run() 若为 False 则抛 ValueError。
    backtest_mode: bool = True


# =============================================================================
# BacktestTrade — Single Simulated Trade / 单笔模拟交易记录
# =============================================================================

@dataclass
class BacktestTrade:
    """
    Record of a single simulated trade.
    单笔模拟交易的记录。

    Fields:
      trade_id      — sequential trade number / 顺序交易编号
      symbol        — trading pair / 交易对
      direction     — "long" or "short" / 方向
      entry_bar_idx — bar index when position was opened / 开仓 bar 索引
      exit_bar_idx  — bar index when position was closed / 平仓 bar 索引
      entry_price   — simulated fill price (includes slippage) / 模拟成交价（含滑点）
      exit_price    — simulated exit price (includes slippage) / 模拟退出价（含滑点）
      qty           — position size in base currency / 仓位大小（基础货币）
      notional_usd  — position notional value in USD / 仓位名义价值（USD）
      entry_fee     — fee paid on entry / 开仓手续费
      exit_fee      — fee paid on exit / 平仓手续费
      gross_pnl     — PnL before fees and slippage / 毛利润（未扣手续费）
      net_pnl       — PnL after all costs / 净利润（扣除所有成本）
      pnl_pct       — net PnL as percentage of notional / 净利润占名义价值的百分比
      exit_reason   — why trade was closed: "signal" / "stop_loss" / "end_of_data"
      signal_source — which rule triggered entry / 触发入场的信号来源
    """
    trade_id: int
    symbol: str
    direction: str
    entry_bar_idx: int
    exit_bar_idx: int
    entry_price: float
    exit_price: float
    qty: float
    notional_usd: float
    entry_fee: float
    exit_fee: float
    gross_pnl: float
    net_pnl: float
    pnl_pct: float
    exit_reason: str
    signal_source: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for API responses / 序列化为字典（用于 API 返回）"""
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_bar_idx": self.entry_bar_idx,
            "exit_bar_idx": self.exit_bar_idx,
            "entry_price": round(self.entry_price, 6),
            "exit_price": round(self.exit_price, 6),
            "qty": round(self.qty, 8),
            "notional_usd": round(self.notional_usd, 4),
            "entry_fee": round(self.entry_fee, 6),
            "exit_fee": round(self.exit_fee, 6),
            "gross_pnl": round(self.gross_pnl, 6),
            "net_pnl": round(self.net_pnl, 6),
            "pnl_pct": round(self.pnl_pct, 6),
            "exit_reason": self.exit_reason,
            "signal_source": self.signal_source,
        }


# =============================================================================
# BacktestResult — Backtest Summary Results / 回测汇总结果
# =============================================================================

@dataclass
class BacktestResult:
    """
    Summary of a completed backtest run.
    已完成回测的汇总结果。

    Core performance metrics / 核心绩效指标:
      total_trades     — number of completed trades / 完成的交易数
      winning_trades   — trades with net_pnl > 0 / 净利润为正的交易数
      losing_trades    — trades with net_pnl <= 0 / 净利润为负或零的交易数
      win_rate         — winning_trades / total_trades (0.0 ~ 1.0) / 胜率
      total_net_pnl    — sum of all net_pnl / 总净利润
      total_return_pct — total_net_pnl / initial_capital × 100 / 总收益率（%）
      max_drawdown_pct — maximum peak-to-trough drawdown in % / 最大回撤（%）
      sharpe_ratio     — annualized Sharpe ratio (risk-adjusted return) / 年化 Sharpe 比率
      avg_win_pct      — average PnL% of winning trades / 盈利交易平均收益率
      avg_loss_pct     — average PnL% of losing trades (negative) / 亏损交易平均亏损率
      profit_factor    — gross_wins / gross_losses / 盈亏比
      avg_trade_pct    — average PnL% per trade / 每笔交易平均收益率

    Metadata / 元数据:
      symbol, timeframe, strategy_name — from config / 来自配置
      initial_capital, final_capital   — capital at start/end / 初末资金
      total_bars_processed — number of kline bars replayed / 回放的 K 线数量
      config               — original BacktestConfig / 原始配置
      trades               — list of all BacktestTrade / 所有交易记录列表
      equity_curve         — list of capital values per bar / 每根 K 线对应的资金曲线
      warning              — non-empty if there were data quality issues / 若有数据质量问题则非空
    """
    # Identity / 标识
    symbol: str
    timeframe: str
    strategy_name: str

    # Capital / 资金
    initial_capital: float
    final_capital: float

    # Trade counts / 交易计数
    total_trades: int
    winning_trades: int
    losing_trades: int

    # Core metrics / 核心指标
    win_rate: float          # 0.0 ~ 1.0
    total_net_pnl: float
    total_return_pct: float  # percentage
    max_drawdown_pct: float  # percentage (positive means drawdown)
    sharpe_ratio: float      # annualized
    avg_win_pct: float
    avg_loss_pct: float      # negative value
    profit_factor: float
    avg_trade_pct: float

    # Volume / 数量
    total_bars_processed: int

    # Detail / 详情
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    config: BacktestConfig | None = None
    warning: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for API responses / 序列化为字典（用于 API 返回）"""
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "strategy_name": self.strategy_name,
            "initial_capital": round(self.initial_capital, 4),
            "final_capital": round(self.final_capital, 4),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 4),
            "total_net_pnl": round(self.total_net_pnl, 4),
            "total_return_pct": round(self.total_return_pct, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "avg_win_pct": round(self.avg_win_pct, 4),
            "avg_loss_pct": round(self.avg_loss_pct, 4),
            "profit_factor": round(self.profit_factor, 4),
            "avg_trade_pct": round(self.avg_trade_pct, 4),
            "total_bars_processed": self.total_bars_processed,
            "trades": [t.to_dict() for t in self.trades],
            "equity_curve": [round(v, 4) for v in self.equity_curve],
            "warning": self.warning,
        }
