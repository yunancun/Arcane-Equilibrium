"""
BacktestEngine — Strategy Alpha Verification Infrastructure
回测引擎 — 策略 Alpha 验证基础设施

MODULE_NOTE (中文):
  本模块实现 Phase 2 Batch 2B 规格的回测引擎。
  职责：在历史 OHLCV 数据上运行策略，计算回测结果（胜率、收益率、Sharpe等），
  用于验证策略是否具备真实的 alpha。

  核心设计：
  1. BacktestConfig — 回测配置（交易对、时间框架、策略、资金等）
  2. BacktestTrade  — 单笔模拟交易记录（含手续费、滑点、PnL）
  3. BacktestResult — 回测汇总结果（胜率、收益率、最大回撤、Sharpe等）
  4. _BacktestKlineAdapter — 轻量适配器，向 IndicatorEngine 提供"截止到当前 bar"的历史数据
  5. BacktestEngine — 主类，bar-by-bar 回放，每根 K 线运行指标→信号→模拟成交

  原则 7 隔离（Principle 7 Isolation）：
  - 回测结果不影响任何 Live/Paper 管线
  - 不调用 MessageBus.send()、GovernanceHub、PaperTradingEngine
  - IndicatorEngine/SignalEngine 在回测内部创建独立新实例，不污染线上缓存
  - 所有回测逻辑完全自封闭，唯一出口是返回的 BacktestResult

  Sharpe Ratio 年化因子：
    1m=525600, 5m=105120, 15m=35040, 1h=8760, 4h=2190, 1d=365
    (每年该时间框架的 K 线根数，用于年化标准差)

MODULE_NOTE (English):
  This module implements the backtest engine per Phase 2 Batch 2B spec.
  Responsibilities: run a strategy on historical OHLCV data, compute backtest
  results (win rate, returns, Sharpe, etc.) to verify whether a strategy has
  genuine alpha.

  Core design:
  1. BacktestConfig         — backtest configuration (symbol, timeframe, strategy, capital, etc.)
  2. BacktestTrade          — single simulated trade record (with fees, slippage, PnL)
  3. BacktestResult         — backtest summary (win rate, return, max drawdown, Sharpe, etc.)
  4. _BacktestKlineAdapter  — lightweight adapter feeding IndicatorEngine with data "up to bar i"
  5. BacktestEngine         — main class, bar-by-bar replay with indicators → signals → simulation

  Principle 7 Isolation:
  - Backtest results do NOT affect any Live/Paper pipeline
  - Does NOT call MessageBus.send(), GovernanceHub, or PaperTradingEngine
  - Independent IndicatorEngine/SignalEngine instances created per backtest (no online cache pollution)
  - All backtest logic is self-contained; the only output is the returned BacktestResult

Safety invariant / 安全不变量:
  - 纯离线计算，禁止任何 Live/Paper 副作用 / Pure offline computation, no Live/Paper side effects
  - backtest_mode=True 强制校验，防误用 / backtest_mode=True mandatory check, prevents misuse
"""

from __future__ import annotations

import logging
import math
import statistics
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

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


# =============================================================================
# _BacktestKlineAdapter — Isolated OHLCV Provider for Backtest
# 回测专用轻量 OHLCV 适配器（不污染线上 KlineManager 缓存）
# =============================================================================

class _BacktestKlineAdapter:
    """
    Lightweight OHLCV adapter for the backtest loop.
    回测循环的轻量 OHLCV 适配器。

    ISOLATION PURPOSE (Principle 7): This adapter wraps a static OHLCV dict
    and exposes only data up to bar index `bars_up_to_idx`. This prevents
    look-ahead bias (future bars are invisible) and ensures the backtest
    engine never touches the real KlineManager's live data.
    隔离目的（原则 7）：此适配器封装静态 OHLCV 字典，只暴露截止到
    bars_up_to_idx 的数据，防止未来数据泄露（look-ahead bias），
    确保回测引擎不触及真实 KlineManager 的线上数据。

    It also implements register_on_kline_close() as a no-op to satisfy
    IndicatorEngine's constructor without wiring into the live pipeline.
    同时实现 register_on_kline_close() 为 no-op，满足 IndicatorEngine
    构造器的接口要求，但不接入线上管线。
    """

    def __init__(self, ohlcv_data: dict[str, list[float]], bars_up_to_idx: int) -> None:
        """
        Args:
          ohlcv_data     — full OHLCV dict: {"open":[], "high":[], "low":[], "close":[], "volume":[]}
                           完整 OHLCV 字典
          bars_up_to_idx — slice limit; only bars[:bars_up_to_idx] are visible
                           切片上限；只有 bars[:bars_up_to_idx] 可见
        """
        self._ohlcv_data = ohlcv_data
        self._bars_up_to_idx = bars_up_to_idx

    def update_idx(self, new_idx: int) -> None:
        """
        Advance the visible data window to a new index.
        推进可见数据窗口到新索引（由 BacktestEngine 在每根 bar 后调用）。
        """
        self._bars_up_to_idx = new_idx

    def get_ohlcv(
        self,
        symbol: str,  # noqa: ARG002 — interface compat, ignored in backtest
        timeframe: str,  # noqa: ARG002 — interface compat, ignored in backtest
        n: int | None = None,
    ) -> dict[str, list[float]]:
        """
        Return OHLCV arrays truncated at bars_up_to_idx (no look-ahead).
        返回截断到 bars_up_to_idx 的 OHLCV 数组（无未来数据泄露）。

        The symbol and timeframe args are accepted to match KlineManager's
        interface but are ignored — the adapter serves one symbol/timeframe.
        symbol 和 timeframe 参数接受但忽略，以兼容 KlineManager 接口。
        """
        sliced: dict[str, list[float]] = {}
        for key in ("open", "high", "low", "close", "volume"):
            arr = self._ohlcv_data.get(key, [])
            truncated = arr[: self._bars_up_to_idx]
            sliced[key] = truncated[-n:] if n is not None else truncated
        return sliced

    def register_on_kline_close(self, callback: Any) -> None:
        """
        No-op: prevents backtest from wiring into the live kline pipeline.
        No-op：防止回测接入线上 K 线管线。

        IndicatorEngine calls this in __init__ to subscribe to kline events.
        In backtest mode, we drive indicator computation manually bar-by-bar,
        so we do NOT want any callback-based trigger firing.
        IndicatorEngine 在 __init__ 中调用此方法注册回调。
        回测模式下，我们手动逐 bar 驱动指标计算，不需要回调触发。
        """
        # Intentional no-op — backtest_engine drives computation directly
        # 故意 no-op — backtest_engine 直接驱动计算
        pass


# =============================================================================
# Pure helper functions for indicator computation in backtest
# 回测专用纯函数指标计算辅助函数（不依赖 IndicatorEngine 框架，避免副作用）
# =============================================================================

def _compute_sma(close: list[float], period: int) -> float | None:
    """Simple Moving Average / 简单移动平均"""
    if len(close) < period:
        return None
    window = close[-period:]
    return sum(window) / period


def _compute_ema(close: list[float], period: int) -> float | None:
    """Exponential Moving Average / 指数移动平均"""
    if len(close) < period:
        return None
    k = 2.0 / (period + 1)
    ema = sum(close[:period]) / period
    for price in close[period:]:
        ema = price * k + ema * (1 - k)
    return ema


def _compute_rsi(close: list[float], period: int = 14) -> float | None:
    """RSI using Wilder's smoothing / 使用 Wilder 平滑法的 RSI"""
    if len(close) < period + 1:
        return None
    changes = [close[i] - close[i - 1] for i in range(1, len(close))]
    gains = [max(c, 0.0) for c in changes]
    losses = [max(-c, 0.0) for c in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(changes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss < 1e-10:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def _compute_indicators_pure(ohlcv: dict[str, list[float]]) -> dict[str, Any]:
    """
    Compute a minimal indicator set from raw OHLCV using pure functions.
    使用纯函数从原始 OHLCV 计算最小指标集（不依赖 IndicatorEngine 框架）。

    This is the fallback used inside BacktestEngine when the injected
    IndicatorEngine cannot easily be driven manually (e.g., it relies on
    live KlineManager state). The pure-function approach guarantees:
    - No side effects on any online state
    - Correct look-ahead prevention (caller controls which bars are fed)
    当注入的 IndicatorEngine 无法手动驱动时（如依赖线上 KlineManager 状态），
    此函数作为 BacktestEngine 内部的后备方案。纯函数方法保证：
    - 对线上状态无副作用
    - 正确防止未来数据泄露（调用者控制喂入哪些 bar）

    Returns dict with keys used by built-in signal rules:
    返回内置信号规则使用的指标键：
      "SMA(20)", "SMA(50)", "EMA(12)", "EMA(26)", "RSI(14)", "MACD(12,26,9)"
    """
    close = ohlcv.get("close", [])
    if not close:
        return {}

    result: dict[str, Any] = {}

    sma20 = _compute_sma(close, 20)
    sma50 = _compute_sma(close, 50)
    ema12 = _compute_ema(close, 12)
    ema26 = _compute_ema(close, 26)
    rsi14 = _compute_rsi(close, 14)

    if sma20 is not None:
        result["SMA(20)"] = {"sma": sma20}
    if sma50 is not None:
        result["SMA(50)"] = {"sma": sma50}
    if ema12 is not None:
        result["EMA(12)"] = {"ema": ema12}
    if ema26 is not None:
        result["EMA(26)"] = {"ema": ema26}
    if rsi14 is not None:
        result["RSI(14)"] = {"rsi": rsi14}

    # MACD / MACD 指标
    if ema12 is not None and ema26 is not None:
        macd_line = ema12 - ema26
        # Approximate signal line: EMA(9) of MACD values computed over last 35 bars
        # 信号线：最近 35 根 bar 的 MACD 序列的 EMA(9)
        if len(close) >= 35:
            macd_series = []
            for i in range(9, min(len(close), 35) + 1):
                sub = close[:i]
                e12 = _compute_ema(sub, 12)
                e26 = _compute_ema(sub, 26)
                if e12 is not None and e26 is not None:
                    macd_series.append(e12 - e26)
            if len(macd_series) >= 9:
                signal_line = _compute_ema(macd_series, 9)
                if signal_line is not None:
                    histogram = macd_line - signal_line
                    result["MACD(12,26,9)"] = {
                        "macd": macd_line,
                        "signal": signal_line,
                        "histogram": histogram,
                    }
        # Fallback without signal line
        # 无信号线的后备
        if "MACD(12,26,9)" not in result:
            result["MACD(12,26,9)"] = {
                "macd": macd_line,
                "signal": None,
                "histogram": None,
            }

    return result


# =============================================================================
# _compute_sharpe — Sharpe Ratio Calculation / Sharpe 比率计算
# =============================================================================

def _compute_sharpe(pnl_per_trade: list[float], timeframe: str) -> float:
    """
    Compute annualized Sharpe ratio from a list of per-trade PnL values.
    从每笔交易 PnL 列表计算年化 Sharpe 比率。

    Formula:
      sharpe = mean(pnl) / std(pnl) × sqrt(annualization_factor)

    Edge cases:
    - total_trades < 2 or std == 0 → return 0.0 (not nan or inf)
    - 交易数 < 2 或标准差为 0 → 返回 0.0（不返回 nan 或 inf）

    Args:
      pnl_per_trade  — list of per-trade net PnL values / 每笔交易净利润列表
      timeframe      — e.g., "1h", used to look up annualization factor / 时间框架

    Returns:
      Annualized Sharpe ratio, 0.0 if insufficient data / 年化 Sharpe 比率
    """
    n = len(pnl_per_trade)
    if n < MIN_TRADES_FOR_STATS:
        return 0.0

    mean_pnl = statistics.mean(pnl_per_trade)
    try:
        std_pnl = statistics.stdev(pnl_per_trade)
    except statistics.StatisticsError:
        return 0.0

    if std_pnl < 1e-10:
        # Zero standard deviation — all trades same PnL, Sharpe undefined → 0.0
        # 标准差为 0 — 所有交易 PnL 相同，Sharpe 无意义 → 0.0
        return 0.0

    ann_factor = ANNUALIZATION_FACTORS.get(timeframe, 365)
    sharpe = (mean_pnl / std_pnl) * math.sqrt(ann_factor)

    # Guard against inf/nan (shouldn't happen, but be safe)
    # 防止 inf/nan（理论上不会，但保持防御性）
    if not math.isfinite(sharpe):
        return 0.0

    return sharpe


# =============================================================================
# _compute_max_drawdown — Maximum Drawdown Calculation / 最大回撤计算
# =============================================================================

def _compute_max_drawdown(equity_curve: list[float]) -> float:
    """
    Compute maximum peak-to-trough drawdown as a percentage.
    计算最大峰谷回撤（百分比）。

    Returns:
      Max drawdown percentage (positive number, e.g., 15.3 means 15.3% drawdown).
      最大回撤百分比（正数，如 15.3 表示 15.3% 回撤）。
      Returns 0.0 if insufficient data.
      数据不足时返回 0.0。
    """
    if len(equity_curve) < 2:
        return 0.0

    peak = equity_curve[0]
    max_dd = 0.0

    for value in equity_curve[1:]:
        if value > peak:
            peak = value
        if peak > 0:
            dd = (peak - value) / peak * 100.0
            if dd > max_dd:
                max_dd = dd

    return max_dd


# =============================================================================
# BacktestEngine — Main Backtest Runner / 主回测运行器
# =============================================================================

class BacktestEngine:
    """
    Main backtest engine: replays historical OHLCV bar-by-bar, runs indicators
    and signal rules, simulates trades, and returns a BacktestResult.
    主回测引擎：逐 bar 回放历史 OHLCV，运行指标和信号规则，模拟交易，返回 BacktestResult。

    PRINCIPLE 7 ISOLATION: This engine does NOT:
    原则 7 隔离：本引擎不：
    - Call MessageBus.send() / 调用 MessageBus.send()
    - Call GovernanceHub or acquire any Decision Lease / 调用 GovernanceHub 或获取决策租约
    - Interact with PaperTradingEngine or any live execution path / 与 PaperTradingEngine 或任何实盘路径交互
    - Modify the injected KlineManager/IndicatorEngine/SignalEngine state / 修改注入的线上实例状态

    Each run() call creates fresh internal instances for indicator/signal computation.
    每次 run() 调用都为指标/信号计算创建全新的内部实例。

    Usage:
      engine = BacktestEngine(kline_manager=km, indicator_engine=ie, signal_engine=se)
      config = BacktestConfig(symbol="BTCUSDT", timeframe="1h", strategy_name="rsi_bb")
      result = engine.run(config, ohlcv_data)
      print(result.win_rate, result.sharpe_ratio)
    """

    def __init__(
        self,
        kline_manager: Any = None,
        indicator_engine: Any = None,
        signal_engine: Any = None,
    ) -> None:
        """
        Args:
          kline_manager    — live KlineManager instance (used only to read historical OHLCV)
                             线上 KlineManager（仅用于读取历史 OHLCV，不写入）
          indicator_engine — live IndicatorEngine (provides indicator classes reference)
                             线上 IndicatorEngine（提供指标类参考，回测内部创建独立实例）
          signal_engine    — live SignalEngine (provides signal rule classes reference)
                             线上 SignalEngine（提供信号规则类参考，回测内部创建独立实例）

          All three can be None — the engine falls back to pure-function computation.
          三者均可为 None，引擎将使用纯函数后备计算。
        """
        self._live_kline_manager = kline_manager
        self._live_indicator_engine = indicator_engine
        self._live_signal_engine = signal_engine

        # Last result stored for /api/v1/backtest/status endpoint
        # 最近一次结果，供 /api/v1/backtest/status 端点查询
        self._last_result: BacktestResult | None = None
        self._last_run_ts: float = 0.0

    # ── Public API / 公开 API ──

    def run(
        self,
        config: BacktestConfig,
        ohlcv_data: dict[str, list[float]] | None = None,
    ) -> BacktestResult:
        """
        Execute a full backtest run for the given config.
        执行给定配置的完整回测。

        Args:
          config     — BacktestConfig with backtest_mode=True (enforced)
                       BacktestConfig，必须 backtest_mode=True（强制检查）
          ohlcv_data — optional preloaded OHLCV dict. If None, tries to fetch
                       from the live KlineManager. If neither available, returns
                       a BacktestResult with a warning.
                       可选的预加载 OHLCV 字典。为 None 时尝试从线上 KlineManager 获取。
                       两者均不可用时返回含 warning 的 BacktestResult。

        Returns:
          BacktestResult with all performance metrics computed.
          包含所有绩效指标的 BacktestResult。

        Raises:
          ValueError — if config.backtest_mode is False (safety guard)
                       若 config.backtest_mode 为 False（安全守护，禁止误用）
        """
        # Safety guard: backtest_mode MUST be True
        # 安全守护：backtest_mode 必须为 True，防止误将回测配置用于实盘
        if not config.backtest_mode:
            raise ValueError(
                "BacktestConfig.backtest_mode must be True. "
                "Setting it to False is not allowed — this prevents accidental "
                "use of backtest config in live/paper trading. "
                "回测配置的 backtest_mode 必须为 True，防止误用于实盘/模拟交易。"
            )

        # Resolve OHLCV data / 解析 OHLCV 数据
        data = ohlcv_data or self._fetch_ohlcv_from_live(config.symbol, config.timeframe)

        if not data or not data.get("close"):
            warning = (
                f"No OHLCV data available for {config.symbol}/{config.timeframe}. "
                f"Backtest aborted. / 无法获取 {config.symbol}/{config.timeframe} 的 OHLCV 数据，回测中止。"
            )
            logger.warning(warning)
            return self._empty_result(config, warning=warning)

        n_bars = len(data["close"])
        if n_bars < MIN_BARS_REQUIRED:
            warning = (
                f"Insufficient data: {n_bars} bars < minimum {MIN_BARS_REQUIRED} required. "
                f"Backtest aborted. / 数据不足：{n_bars} 根 K 线 < 最少需要 {MIN_BARS_REQUIRED} 根，回测中止。"
            )
            logger.warning(warning)
            return self._empty_result(config, warning=warning, n_bars=n_bars)

        logger.info(
            "BacktestEngine.run: symbol=%s tf=%s strategy=%s bars=%d / "
            "开始回测：%s %s 策略=%s %d 根K线",
            config.symbol, config.timeframe, config.strategy_name, n_bars,
            config.symbol, config.timeframe, config.strategy_name, n_bars,
        )

        # Run the bar-by-bar simulation / 执行逐 bar 模拟
        result = self._simulate(config, data)

        # Store for status endpoint / 存储供状态端点查询
        self._last_result = result
        self._last_run_ts = time.time()

        logger.info(
            "BacktestEngine.run complete: trades=%d win_rate=%.2f%% "
            "total_return=%.2f%% sharpe=%.3f / "
            "回测完成：交易数=%d 胜率=%.2f%% 总收益=%.2f%% Sharpe=%.3f",
            result.total_trades, result.win_rate * 100,
            result.total_return_pct, result.sharpe_ratio,
            result.total_trades, result.win_rate * 100,
            result.total_return_pct, result.sharpe_ratio,
        )

        return result

    def get_last_result(self) -> BacktestResult | None:
        """
        Return the most recent BacktestResult (for status endpoint).
        返回最近一次 BacktestResult（供状态端点查询）。
        """
        return self._last_result

    def get_status(self) -> dict[str, Any]:
        """
        Return engine status dict (for /api/v1/backtest/status).
        返回引擎状态字典（供 /api/v1/backtest/status 端点查询）。
        """
        if self._last_result is None:
            return {
                "status": "idle",
                "message": "No backtest has been run yet / 尚未运行任何回测",
                "last_run_ts": None,
            }
        return {
            "status": "completed",
            "last_run_ts": self._last_run_ts,
            "summary": {
                "symbol": self._last_result.symbol,
                "timeframe": self._last_result.timeframe,
                "strategy_name": self._last_result.strategy_name,
                "total_trades": self._last_result.total_trades,
                "win_rate": round(self._last_result.win_rate, 4),
                "total_return_pct": round(self._last_result.total_return_pct, 4),
                "sharpe_ratio": round(self._last_result.sharpe_ratio, 4),
                "max_drawdown_pct": round(self._last_result.max_drawdown_pct, 4),
                "warning": self._last_result.warning,
            },
        }

    # ── Internal Simulation / 内部模拟 ──

    def _simulate(
        self,
        config: BacktestConfig,
        ohlcv_data: dict[str, list[float]],
    ) -> BacktestResult:
        """
        Core bar-by-bar simulation loop.
        核心逐 bar 模拟循环。

        For each bar (starting from bar 30 to ensure indicator warmup):
        每根 bar（从第 30 根开始，确保指标预热）：
          1. Feed data up to current bar into pure indicator computation
             将截至当前 bar 的数据送入纯函数指标计算
          2. Evaluate signal rules against computed indicators
             用计算出的指标评估信号规则
          3. If flat: check for entry signal → open position
             若无仓位：检查入场信号 → 开仓
          4. If in position: check stop-loss first, then exit signal → close
             若有仓位：先检查止损，再检查出场信号 → 平仓
          5. Record equity after each bar
             记录每根 bar 后的资金曲线

        PRINCIPLE 7 NOTE: Uses pure function indicators (_compute_indicators_pure)
        to avoid touching live IndicatorEngine/SignalEngine state.
        原则 7 说明：使用纯函数指标（_compute_indicators_pure）
        避免触及线上 IndicatorEngine/SignalEngine 状态。
        """
        close_prices = ohlcv_data["close"]
        n_bars = len(close_prices)

        capital = config.initial_capital
        equity_curve: list[float] = []
        trades: list[BacktestTrade] = []
        trade_id_counter = 0

        # Current open position state / 当前未平仓仓位状态
        position: dict[str, Any] | None = None

        # Build signal rules once for this backtest run
        # 为本次回测构建信号规则（独立实例，不复用线上 SignalEngine）
        signal_rules = self._build_signal_rules(config.strategy_name)

        # Warmup offset: start iterating from MIN_BARS_REQUIRED to allow indicator calc
        # 预热偏移：从 MIN_BARS_REQUIRED 开始迭代以允许指标计算
        for bar_idx in range(MIN_BARS_REQUIRED, n_bars):
            current_price = close_prices[bar_idx]

            # PRINCIPLE 7: Compute indicators using pure functions on sliced data
            # 原则 7：使用纯函数在切片数据上计算指标（不修改线上缓存）
            ohlcv_slice = {
                key: arr[: bar_idx + 1]  # bars up to and including current bar
                for key, arr in ohlcv_data.items()
                if isinstance(arr, list)
            }
            indicators = _compute_indicators_pure(ohlcv_slice)

            # Check stop-loss first if in position / 有仓位时先检查止损
            if position is not None:
                stop_price = position["stop_price"]
                if position["direction"] == "long" and current_price <= stop_price:
                    # Stop-loss hit on long / 多仓止损触发
                    trade = self._close_position(
                        config, position, current_price, bar_idx,
                        "stop_loss", capital, trade_id_counter,
                    )
                    trade_id_counter += 1
                    capital += trade.net_pnl
                    trades.append(trade)
                    position = None
                elif position["direction"] == "short" and current_price >= stop_price:
                    # Stop-loss hit on short / 空仓止损触发
                    trade = self._close_position(
                        config, position, current_price, bar_idx,
                        "stop_loss", capital, trade_id_counter,
                    )
                    trade_id_counter += 1
                    capital += trade.net_pnl
                    trades.append(trade)
                    position = None

            # Evaluate signals / 评估信号
            signals = self._evaluate_signals(
                config.symbol, config.timeframe, indicators, signal_rules,
            )

            if position is None:
                # Flat: look for entry signal / 无仓位：寻找入场信号
                entry_signal = self._pick_entry_signal(signals)
                if entry_signal is not None:
                    position = self._open_position(
                        config, entry_signal, current_price, bar_idx, capital,
                    )
            else:
                # In position: look for exit signal / 有仓位：寻找出场信号
                exit_signal = self._pick_exit_signal(signals, position["direction"])
                if exit_signal is not None:
                    trade = self._close_position(
                        config, position, current_price, bar_idx,
                        "signal", capital, trade_id_counter,
                    )
                    trade_id_counter += 1
                    capital += trade.net_pnl
                    trades.append(trade)
                    position = None

            # Record equity at this bar / 记录本 bar 的资金曲线
            # If in a position, mark-to-market the unrealized PnL
            # 若有仓位，以当前价格估算未实现盈亏（mark-to-market）
            if position is not None:
                unrealized = self._unrealized_pnl(position, current_price)
                equity_curve.append(capital + unrealized)
            else:
                equity_curve.append(capital)

        # Close any open position at end of data / 数据结束时强制平仓
        if position is not None:
            last_price = close_prices[-1]
            trade = self._close_position(
                config, position, last_price, n_bars - 1,
                "end_of_data", capital, trade_id_counter,
            )
            trade_id_counter += 1
            capital += trade.net_pnl
            trades.append(trade)
            # Update last equity point / 更新最后资金点
            if equity_curve:
                equity_curve[-1] = capital
            else:
                equity_curve.append(capital)

        # Compute summary statistics / 计算汇总统计
        return self._build_result(config, trades, equity_curve, capital, n_bars)

    def _open_position(
        self,
        config: BacktestConfig,
        signal: Any,
        current_price: float,
        bar_idx: int,
        capital: float,
    ) -> dict[str, Any]:
        """
        Simulate opening a position with slippage applied.
        模拟开仓（含滑点）。

        Slippage is applied adversarially: long entry price is higher,
        short entry price is lower.
        滑点对交易者不利：多仓入场价更高，空仓入场价更低。
        """
        slippage_mult = config.slippage_bps / 10000.0

        if signal.direction == "long":
            # Long: slippage pushes price up / 多仓：滑点使价格上升（不利）
            entry_price = current_price * (1.0 + slippage_mult)
        else:
            # Short: slippage pushes price down / 空仓：滑点使价格下降（不利）
            entry_price = current_price * (1.0 - slippage_mult)

        # Position sizing: risk_capital / price = qty
        # 仓位计算：资金 × position_size_pct / 入场价 = 数量
        notional = capital * config.position_size_pct
        qty = notional / entry_price
        entry_fee = notional * config.fee_rate_taker

        # Stop-loss price / 止损价
        if signal.direction == "long":
            stop_price = entry_price * (1.0 - config.stop_loss_pct)
        else:
            stop_price = entry_price * (1.0 + config.stop_loss_pct)

        return {
            "direction": signal.direction,
            "entry_price": entry_price,
            "entry_bar_idx": bar_idx,
            "qty": qty,
            "notional": notional,
            "entry_fee": entry_fee,
            "stop_price": stop_price,
            "signal_source": getattr(signal, "source", ""),
        }

    def _close_position(
        self,
        config: BacktestConfig,
        position: dict[str, Any],
        current_price: float,
        bar_idx: int,
        exit_reason: str,
        capital: float,
        trade_id: int,
    ) -> BacktestTrade:
        """
        Simulate closing a position and compute PnL.
        模拟平仓并计算 PnL。

        Slippage is applied adversarially on exit too.
        出场也使用不利滑点。
        """
        slippage_mult = config.slippage_bps / 10000.0

        if position["direction"] == "long":
            # Long exit: price drops due to slippage / 多仓出场：价格因滑点下降
            exit_price = current_price * (1.0 - slippage_mult)
            gross_pnl = (exit_price - position["entry_price"]) * position["qty"]
        else:
            # Short exit: price rises due to slippage / 空仓出场：价格因滑点上升
            exit_price = current_price * (1.0 + slippage_mult)
            gross_pnl = (position["entry_price"] - exit_price) * position["qty"]

        exit_fee = exit_price * position["qty"] * config.fee_rate_taker
        net_pnl = gross_pnl - position["entry_fee"] - exit_fee
        pnl_pct = net_pnl / position["notional"] if position["notional"] > 0 else 0.0

        return BacktestTrade(
            trade_id=trade_id,
            symbol=config.symbol,
            direction=position["direction"],
            entry_bar_idx=position["entry_bar_idx"],
            exit_bar_idx=bar_idx,
            entry_price=position["entry_price"],
            exit_price=exit_price,
            qty=position["qty"],
            notional_usd=position["notional"],
            entry_fee=position["entry_fee"],
            exit_fee=exit_fee,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            pnl_pct=pnl_pct,
            exit_reason=exit_reason,
            signal_source=position.get("signal_source", ""),
        )

    def _unrealized_pnl(self, position: dict[str, Any], current_price: float) -> float:
        """
        Estimate unrealized PnL for mark-to-market equity curve.
        估算未实现盈亏（用于资金曲线的逐市价估算）。
        Does not include fees (they will be charged on actual close).
        不含手续费（实际平仓时才扣除）。
        """
        if position["direction"] == "long":
            return (current_price - position["entry_price"]) * position["qty"]
        else:
            return (position["entry_price"] - current_price) * position["qty"]

    def _evaluate_signals(
        self,
        symbol: str,
        timeframe: str,
        indicators: dict[str, Any],
        signal_rules: list[Any],
    ) -> list[Any]:
        """
        Evaluate all signal rules against current indicators.
        用当前指标评估所有信号规则。

        PRINCIPLE 7: Uses backtest-local rule instances, not the live SignalEngine.
        原则 7：使用回测本地的规则实例，不使用线上 SignalEngine。
        """
        signals = []
        for rule in signal_rules:
            try:
                sig = rule.evaluate(symbol, timeframe, indicators)
                if sig is not None:
                    signals.append(sig)
            except Exception:
                logger.debug(
                    "Signal rule %s evaluation error in backtest / 回测中信号规则 %s 评估异常",
                    getattr(rule, "name", str(rule)),
                    getattr(rule, "name", str(rule)),
                )
        return signals

    def _pick_entry_signal(self, signals: list[Any]) -> Any | None:
        """
        Pick the best entry signal from a list.
        从信号列表中选择最佳入场信号。

        Strategy: highest confidence among "long" and "short" signals.
        策略：从 "long" 和 "short" 信号中选择置信度最高的。
        """
        entry_signals = [
            s for s in signals
            if getattr(s, "direction", None) in ("long", "short")
        ]
        if not entry_signals:
            return None
        # Pick highest confidence / 选择置信度最高的
        return max(entry_signals, key=lambda s: getattr(s, "confidence", 0.0))

    def _pick_exit_signal(self, signals: list[Any], position_direction: str) -> Any | None:
        """
        Pick an exit signal matching the current position direction.
        选择与当前仓位方向匹配的出场信号。

        - For "long" position → look for "close_long" signal
          持多仓 → 寻找 "close_long" 信号
        - For "short" position → look for "close_short" signal
          持空仓 → 寻找 "close_short" 信号
        """
        target = "close_long" if position_direction == "long" else "close_short"
        exit_signals = [
            s for s in signals
            if getattr(s, "direction", None) == target
        ]
        if not exit_signals:
            return None
        return max(exit_signals, key=lambda s: getattr(s, "confidence", 0.0))

    def _build_signal_rules(self, strategy_name: str) -> list[Any]:
        """
        Build an independent set of signal rules for this backtest run.
        为本次回测构建独立的信号规则集。

        PRINCIPLE 7: These are NEW instances, not the live SignalEngine's rules.
        原则 7：这是全新实例，不是线上 SignalEngine 的规则。
        They carry no state from previous live trading activity.
        它们不携带任何来自线上交易活动的状态。

        Uses built-in rules from signal_generator module.
        使用 signal_generator 模块的内置规则。
        Falls back to empty list if import fails.
        导入失败时退而使用空列表（回测会进行但不产生交易）。
        """
        try:
            from .signal_generator import create_default_signal_rules  # type: ignore
            # Create fresh instances / 创建全新实例（不复用线上对象）
            return create_default_signal_rules()
        except Exception:
            logger.warning(
                "Could not import signal rules for backtest '%s', "
                "using empty rule set. No trades will be generated. / "
                "无法为回测 '%s' 导入信号规则，使用空规则集，不会产生交易。",
                strategy_name, strategy_name,
            )
            return []

    def _build_result(
        self,
        config: BacktestConfig,
        trades: list[BacktestTrade],
        equity_curve: list[float],
        final_capital: float,
        n_bars: int,
    ) -> BacktestResult:
        """
        Compute all summary statistics from completed trade list.
        从完成的交易列表计算所有汇总统计指标。
        """
        total = len(trades)
        winning = [t for t in trades if t.net_pnl > 0]
        losing = [t for t in trades if t.net_pnl <= 0]

        win_rate = len(winning) / total if total > 0 else 0.0
        total_net_pnl = sum(t.net_pnl for t in trades)
        total_return_pct = (total_net_pnl / config.initial_capital * 100.0
                            if config.initial_capital > 0 else 0.0)

        avg_win_pct = (
            statistics.mean(t.pnl_pct for t in winning) * 100.0
            if winning else 0.0
        )
        avg_loss_pct = (
            statistics.mean(t.pnl_pct for t in losing) * 100.0
            if losing else 0.0
        )
        avg_trade_pct = (
            statistics.mean(t.pnl_pct for t in trades) * 100.0
            if trades else 0.0
        )

        # Profit factor: sum of gross wins / sum of gross losses
        # 盈亏比：总毛利 / 总毛损
        gross_wins = sum(t.net_pnl for t in winning)
        gross_losses = abs(sum(t.net_pnl for t in losing))
        profit_factor = gross_wins / gross_losses if gross_losses > 0 else (
            float("inf") if gross_wins > 0 else 0.0
        )
        # Cap profit_factor to avoid inf in JSON serialization
        # 限制 profit_factor 防止 JSON 序列化时出现 inf
        if not math.isfinite(profit_factor):
            profit_factor = 999.0

        # Sharpe ratio / Sharpe 比率
        pnl_list = [t.net_pnl for t in trades]
        sharpe = _compute_sharpe(pnl_list, config.timeframe)

        # Max drawdown / 最大回撤
        full_curve = [config.initial_capital] + equity_curve
        max_dd = _compute_max_drawdown(full_curve)

        return BacktestResult(
            symbol=config.symbol,
            timeframe=config.timeframe,
            strategy_name=config.strategy_name,
            initial_capital=config.initial_capital,
            final_capital=final_capital,
            total_trades=total,
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=win_rate,
            total_net_pnl=total_net_pnl,
            total_return_pct=total_return_pct,
            max_drawdown_pct=max_dd,
            sharpe_ratio=sharpe,
            avg_win_pct=avg_win_pct,
            avg_loss_pct=avg_loss_pct,
            profit_factor=profit_factor,
            avg_trade_pct=avg_trade_pct,
            total_bars_processed=n_bars,
            trades=trades,
            equity_curve=equity_curve,
            config=config,
            warning="",
        )

    def _fetch_ohlcv_from_live(
        self, symbol: str, timeframe: str,
    ) -> dict[str, list[float]] | None:
        """
        Attempt to read OHLCV data from the injected live KlineManager.
        尝试从注入的线上 KlineManager 读取 OHLCV 数据。

        This is a READ-ONLY operation — we only call get_ohlcv().
        这是只读操作 — 只调用 get_ohlcv()，不修改任何状态。
        """
        if self._live_kline_manager is None:
            return None
        try:
            data = self._live_kline_manager.get_ohlcv(symbol, timeframe)
            return data
        except Exception:
            logger.warning(
                "Failed to fetch OHLCV from live KlineManager for %s/%s / "
                "从线上 KlineManager 获取 %s/%s OHLCV 数据失败",
                symbol, timeframe, symbol, timeframe,
            )
            return None

    @staticmethod
    def _empty_result(
        config: BacktestConfig,
        warning: str = "",
        n_bars: int = 0,
    ) -> BacktestResult:
        """
        Build an empty BacktestResult with zero trades (used on early abort).
        构建零交易的空 BacktestResult（用于提前中止场景）。
        """
        return BacktestResult(
            symbol=config.symbol,
            timeframe=config.timeframe,
            strategy_name=config.strategy_name,
            initial_capital=config.initial_capital,
            final_capital=config.initial_capital,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            total_net_pnl=0.0,
            total_return_pct=0.0,
            max_drawdown_pct=0.0,
            sharpe_ratio=0.0,
            avg_win_pct=0.0,
            avg_loss_pct=0.0,
            profit_factor=0.0,
            avg_trade_pct=0.0,
            total_bars_processed=n_bars,
            trades=[],
            equity_curve=[],
            config=config,
            warning=warning,
        )
