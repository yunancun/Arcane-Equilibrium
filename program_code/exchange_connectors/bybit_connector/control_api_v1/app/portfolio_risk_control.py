"""
Portfolio Correlation Risk Control — EX-01 §6 / DOC-01 §5.16 / GAP-H4
组合相关性风控

MODULE_NOTE (中文):
  实现 EX-01 §6 组合级风控：
  - 滚动相关系数矩阵（价格回报率 Pearson 相关）
  - 0.7 相关阈值门控（阻止高相关新仓）
  - 行业/类别集中度限制
  - 最低储备缓冲（30% 权益不可分配）
  - 组合风险度量（平均相关、有效分散度）
  - 与 RiskManager.check_order_allowed() 集成
  - 为 AI 上下文提供组合度量

MODULE_NOTE (English):
  Implements EX-01 §6 portfolio-level risk control:
  - Rolling correlation matrix (price return Pearson correlation)
  - 0.7 correlation threshold gate (block new entries in correlated instruments)
  - Sector/category concentration limits
  - Minimum reserve buffer (30% equity unallocated)
  - Portfolio risk metrics (avg correlation, effective diversification)
  - Integrates with RiskManager.check_order_allowed()
  - Provides portfolio metrics for AI context

Safety invariant:
  - 相关性检查不可跳过
  - 高相关 (>0.7) 时阻止同方向新开仓
  - 储备缓冲硬限制（不可被 AI/P2 调整放宽）
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration / 配置
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class PortfolioRiskConfig:
    """Configuration for portfolio-level risk control / 组合风控配置"""
    # Correlation settings
    correlation_threshold: float = 0.7       # Block new entries above this
    correlation_lookback: int = 20           # Rolling window size (data points)
    min_data_points: int = 5                 # Minimum points for valid correlation

    # Sector/category concentration
    max_sector_exposure_pct: float = 40.0    # Max allocation to any single sector
    sector_mapping: dict = field(default_factory=lambda: {
        # Default sector assignments — can be overridden
        "BTCUSDT": "L1", "ETHUSDT": "L1", "SOLUSDT": "L1",
        "BNBUSDT": "L1", "ADAUSDT": "L1", "DOTUSDT": "L1",
        "AVAXUSDT": "L1", "MATICUSDT": "L1",
        "LINKUSDT": "Oracle", "AAVEUSDT": "DeFi",
        "UNIUSDT": "DeFi", "MKRUSDT": "DeFi",
        "DOGEUSDT": "Meme", "SHIBUSDT": "Meme", "PEPEUSDT": "Meme",
    })

    # Reserve buffer
    min_reserve_buffer_pct: float = 30.0     # Minimum unallocated equity

    # Portfolio metrics
    max_avg_correlation: float = 0.6         # Warn threshold for portfolio avg correlation


# ═══════════════════════════════════════════════════════════════════════════════
# Price Return Tracker / 价格回报追踪器
# ═══════════════════════════════════════════════════════════════════════════════

class PriceReturnTracker:
    """
    Tracks price returns for correlation calculation.
    追踪价格回报率用于相关系数计算。
    """

    def __init__(self, lookback: int = 20) -> None:
        self._lookback = lookback
        self._prices: dict[str, deque[float]] = {}  # symbol → recent prices
        self._returns: dict[str, deque[float]] = {}  # symbol → recent returns
        self._lock = threading.Lock()

    def record_price(self, symbol: str, price: float) -> None:
        """Record a new price tick / 记录新价格"""
        with self._lock:
            if symbol not in self._prices:
                self._prices[symbol] = deque(maxlen=self._lookback + 1)
                self._returns[symbol] = deque(maxlen=self._lookback)

            prices = self._prices[symbol]
            returns = self._returns[symbol]

            if prices and prices[-1] > 0:
                ret = (price - prices[-1]) / prices[-1]
                returns.append(ret)

            prices.append(price)

    def get_returns(self, symbol: str) -> list[float]:
        """Get recent returns for a symbol / 获取某币种的近期回报"""
        with self._lock:
            if symbol in self._returns:
                return list(self._returns[symbol])
            return []

    def has_sufficient_data(self, symbol: str, min_points: int) -> bool:
        """Check if enough data for correlation / 检查数据是否足够"""
        with self._lock:
            return symbol in self._returns and len(self._returns[symbol]) >= min_points

    def get_tracked_symbols(self) -> list[str]:
        """Get all tracked symbols / 获取所有追踪的币种"""
        with self._lock:
            return list(self._prices.keys())


# ═══════════════════════════════════════════════════════════════════════════════
# Correlation Calculator / 相关系数计算器
# ═══════════════════════════════════════════════════════════════════════════════

def pearson_correlation(x: list[float], y: list[float]) -> float:
    """
    Calculate Pearson correlation coefficient between two return series.
    计算两个回报序列的 Pearson 相关系数。

    Returns 0.0 if insufficient data or zero variance.
    """
    n = min(len(x), len(y))
    if n < 2:
        return 0.0

    x = x[-n:]
    y = y[-n:]

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n)) / n
    var_x = sum((xi - mean_x) ** 2 for xi in x) / n
    var_y = sum((yi - mean_y) ** 2 for yi in y) / n

    if var_x <= 0 or var_y <= 0:
        return 0.0

    return cov / math.sqrt(var_x * var_y)


# ═══════════════════════════════════════════════════════════════════════════════
# Portfolio Risk Control / 组合风控引擎
# ═══════════════════════════════════════════════════════════════════════════════

class PortfolioRiskControl:
    """
    Portfolio-level risk control engine.
    组合级风控引擎。

    Provides three key checks:
    1. Correlation gate: blocks new entries when correlated with existing positions
    2. Sector concentration: limits exposure to any single category
    3. Reserve buffer: ensures minimum equity remains unallocated

    Usage:
        prc = PortfolioRiskControl(config)
        prc.record_price("BTCUSDT", 50000)
        prc.record_price("ETHUSDT", 3000)
        ...
        allowed, reason = prc.check_new_entry(
            symbol="SOLUSDT", side="Buy", notional=5000,
            positions=current_positions, balance=100000
        )
    """

    def __init__(
        self,
        config: Optional[PortfolioRiskConfig] = None,
        audit_callback: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self._config = config or PortfolioRiskConfig()
        self._tracker = PriceReturnTracker(self._config.correlation_lookback)
        self._audit_callback = audit_callback
        self._lock = threading.Lock()
        self._check_count = 0
        self._block_count = 0

    # ───────────────────────────────────────────────────────────────────────
    # Price Recording / 价格记录
    # ───────────────────────────────────────────────────────────────────────

    def record_price(self, symbol: str, price: float) -> None:
        """Record a price tick for correlation tracking / 记录价格"""
        self._tracker.record_price(symbol, price)

    def record_prices(self, prices: dict[str, float]) -> None:
        """Record multiple price ticks / 批量记录价格"""
        for symbol, price in prices.items():
            self._tracker.record_price(symbol, price)

    # ───────────────────────────────────────────────────────────────────────
    # Pre-Entry Check / 入场前检查
    # ───────────────────────────────────────────────────────────────────────

    def check_new_entry(
        self,
        symbol: str,
        side: str,
        notional: float,
        positions: dict[str, dict],
        balance: float,
        market_prices: Optional[dict[str, float]] = None,
    ) -> tuple[bool, str]:
        """
        Check if a new position entry is allowed by portfolio risk rules.
        检查新开仓是否符合组合风控规则。

        Args:
            symbol: Trading pair (e.g. "BTCUSDT")
            side: "Buy" or "Sell"
            notional: Notional value of new position
            positions: Current positions {symbol: {side, size, avg_entry_price, category}}
            balance: Total account equity
            market_prices: Current market prices {symbol: price}

        Returns:
            (allowed, reason) tuple
        """
        with self._lock:
            self._check_count += 1

            # 1. Reserve buffer check / 储备缓冲检查
            ok, reason = self._check_reserve_buffer(notional, positions, balance, market_prices)
            if not ok:
                self._block_count += 1
                self._emit_audit("reserve_buffer_block", symbol, reason)
                return False, reason

            # 2. Sector concentration check / 行业集中度检查
            ok, reason = self._check_sector_concentration(symbol, notional, positions, balance, market_prices)
            if not ok:
                self._block_count += 1
                self._emit_audit("sector_concentration_block", symbol, reason)
                return False, reason

            # 3. Correlation check / 相关性检查
            ok, reason = self._check_correlation(symbol, side, positions)
            if not ok:
                self._block_count += 1
                self._emit_audit("correlation_block", symbol, reason)
                return False, reason

            return True, "portfolio_check_passed"

    # ───────────────────────────────────────────────────────────────────────
    # Reserve Buffer / 储备缓冲
    # ───────────────────────────────────────────────────────────────────────

    def _check_reserve_buffer(
        self,
        new_notional: float,
        positions: dict[str, dict],
        balance: float,
        market_prices: Optional[dict[str, float]] = None,
    ) -> tuple[bool, str]:
        """Check minimum reserve buffer / 检查最低储备缓冲"""
        if balance <= 0:
            return False, "zero_balance"

        # Calculate total exposure
        total_exposure = self._calculate_total_exposure(positions, market_prices)
        new_total = total_exposure + new_notional

        used_pct = (new_total / balance) * 100
        reserve_pct = 100 - used_pct
        min_reserve = self._config.min_reserve_buffer_pct

        if reserve_pct < min_reserve:
            return False, (
                f"reserve_buffer_{reserve_pct:.1f}pct_below_min_{min_reserve:.1f}pct"
            )
        return True, ""

    # ───────────────────────────────────────────────────────────────────────
    # Sector Concentration / 行业集中度
    # ───────────────────────────────────────────────────────────────────────

    def _check_sector_concentration(
        self,
        symbol: str,
        notional: float,
        positions: dict[str, dict],
        balance: float,
        market_prices: Optional[dict[str, float]] = None,
    ) -> tuple[bool, str]:
        """Check sector exposure limits / 检查行业集中度"""
        if balance <= 0:
            return False, "zero_balance"

        sector = self._get_sector(symbol)
        if not sector:
            return True, ""  # Unknown sector, skip check

        # Calculate sector exposure
        sector_exposure = 0.0
        for sym, pos in positions.items():
            if self._get_sector(sym) == sector:
                size = float(pos.get("size", pos.get("qty", 0)))
                price = self._get_position_price(sym, pos, market_prices)
                sector_exposure += size * price

        new_sector_exposure = sector_exposure + notional
        sector_pct = (new_sector_exposure / balance) * 100
        max_sector = self._config.max_sector_exposure_pct

        if sector_pct > max_sector:
            return False, (
                f"sector_{sector}_exposure_{sector_pct:.1f}pct_exceeds_max_{max_sector:.1f}pct"
            )
        return True, ""

    # ───────────────────────────────────────────────────────────────────────
    # Correlation Gate / 相关性门控
    # ───────────────────────────────────────────────────────────────────────

    def _check_correlation(
        self,
        symbol: str,
        side: str,
        positions: dict[str, dict],
    ) -> tuple[bool, str]:
        """
        Check pairwise correlation with existing positions.
        检查与现有持仓的成对相关性。

        EX-01 §6: If correlation > 0.7 with any existing same-direction position,
        block new entry in the correlated instrument.
        """
        if not self._tracker.has_sufficient_data(symbol, self._config.min_data_points):
            return True, ""  # Not enough data, allow (conservative in data, not in trading)

        new_returns = self._tracker.get_returns(symbol)
        threshold = self._config.correlation_threshold

        for pos_sym, pos_data in positions.items():
            if pos_sym == symbol:
                continue  # Adding to existing position, skip correlation check

            pos_side = pos_data.get("side", "")
            pos_size = float(pos_data.get("size", pos_data.get("qty", 0)))

            if pos_size <= 0:
                continue  # No active position

            # Only check same-direction positions for correlation blocking
            if pos_side.lower() != side.lower():
                continue

            if not self._tracker.has_sufficient_data(pos_sym, self._config.min_data_points):
                continue

            pos_returns = self._tracker.get_returns(pos_sym)
            corr = pearson_correlation(new_returns, pos_returns)

            if corr > threshold:
                return False, (
                    f"correlation_{symbol}_vs_{pos_sym}={corr:.3f}_exceeds_threshold_{threshold}"
                )

        return True, ""

    # ───────────────────────────────────────────────────────────────────────
    # Correlation Matrix / 相关矩阵
    # ───────────────────────────────────────────────────────────────────────

    def compute_correlation_matrix(
        self,
        symbols: Optional[list[str]] = None,
    ) -> dict[str, dict[str, float]]:
        """
        Compute full pairwise correlation matrix.
        计算完整的成对相关矩阵。

        Returns: {sym_a: {sym_b: correlation, ...}, ...}
        """
        if symbols is None:
            symbols = self._tracker.get_tracked_symbols()

        matrix: dict[str, dict[str, float]] = {}

        for i, sym_a in enumerate(symbols):
            matrix[sym_a] = {}
            returns_a = self._tracker.get_returns(sym_a)

            for j, sym_b in enumerate(symbols):
                if i == j:
                    matrix[sym_a][sym_b] = 1.0
                elif j < i and sym_b in matrix and sym_a in matrix[sym_b]:
                    matrix[sym_a][sym_b] = matrix[sym_b][sym_a]
                else:
                    returns_b = self._tracker.get_returns(sym_b)
                    matrix[sym_a][sym_b] = pearson_correlation(returns_a, returns_b)

        return matrix

    # ───────────────────────────────────────────────────────────────────────
    # Portfolio Metrics / 组合度量
    # ───────────────────────────────────────────────────────────────────────

    def get_portfolio_metrics(
        self,
        positions: dict[str, dict],
        balance: float,
        market_prices: Optional[dict[str, float]] = None,
    ) -> dict:
        """
        Compute portfolio-level risk metrics for AI context.
        为 AI 上下文计算组合级风险度量。
        """
        total_exposure = self._calculate_total_exposure(positions, market_prices)

        # Sector exposures
        sector_exposures: dict[str, float] = {}
        for sym, pos in positions.items():
            sector = self._get_sector(sym) or "Unknown"
            size = float(pos.get("size", pos.get("qty", 0)))
            price = self._get_position_price(sym, pos, market_prices)
            notional = size * price
            sector_exposures[sector] = sector_exposures.get(sector, 0) + notional

        # Convert to percentages
        sector_pcts = {}
        if balance > 0:
            for sector, val in sector_exposures.items():
                sector_pcts[sector] = round((val / balance) * 100, 2)

        # Correlation metrics
        active_symbols = [
            sym for sym, pos in positions.items()
            if float(pos.get("size", pos.get("qty", 0))) > 0
        ]
        corr_matrix = self.compute_correlation_matrix(active_symbols) if len(active_symbols) > 1 else {}

        # Average pairwise correlation
        avg_corr = 0.0
        corr_count = 0
        correlated_pairs: list[dict] = []
        for i, sym_a in enumerate(active_symbols):
            for j, sym_b in enumerate(active_symbols):
                if j > i and sym_a in corr_matrix and sym_b in corr_matrix.get(sym_a, {}):
                    c = corr_matrix[sym_a][sym_b]
                    avg_corr += c
                    corr_count += 1
                    if abs(c) > self._config.correlation_threshold:
                        correlated_pairs.append({
                            "pair": f"{sym_a}/{sym_b}",
                            "correlation": round(c, 4),
                        })

        if corr_count > 0:
            avg_corr /= corr_count

        # Reserve buffer
        reserve_pct = ((balance - total_exposure) / balance * 100) if balance > 0 else 0

        # Effective diversification (1 / avg_corr, capped)
        eff_diversification = 1.0 / max(avg_corr, 0.01) if avg_corr > 0 else len(active_symbols)
        eff_diversification = min(eff_diversification, len(active_symbols))

        return {
            "total_exposure": round(total_exposure, 4),
            "total_exposure_pct": round((total_exposure / balance * 100) if balance > 0 else 0, 2),
            "reserve_buffer_pct": round(reserve_pct, 2),
            "position_count": len(active_symbols),
            "sector_exposures_pct": sector_pcts,
            "avg_portfolio_correlation": round(avg_corr, 4),
            "correlated_pairs": correlated_pairs,
            "effective_diversification": round(eff_diversification, 2),
            "correlation_threshold": self._config.correlation_threshold,
            "max_sector_pct": self._config.max_sector_exposure_pct,
            "min_reserve_pct": self._config.min_reserve_buffer_pct,
            "checks_performed": self._check_count,
            "entries_blocked": self._block_count,
        }

    # ───────────────────────────────────────────────────────────────────────
    # Status / 状态
    # ───────────────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Get engine status / 获取引擎状态"""
        return {
            "tracked_symbols": self._tracker.get_tracked_symbols(),
            "checks_performed": self._check_count,
            "entries_blocked": self._block_count,
            "block_rate_pct": round(
                (self._block_count / self._check_count * 100) if self._check_count > 0 else 0, 2
            ),
            "config": {
                "correlation_threshold": self._config.correlation_threshold,
                "correlation_lookback": self._config.correlation_lookback,
                "max_sector_exposure_pct": self._config.max_sector_exposure_pct,
                "min_reserve_buffer_pct": self._config.min_reserve_buffer_pct,
            },
        }

    # ───────────────────────────────────────────────────────────────────────
    # Helpers / 工具函数
    # ───────────────────────────────────────────────────────────────────────

    def _get_sector(self, symbol: str) -> str:
        """Get sector for a symbol / 获取币种所属行业"""
        return self._config.sector_mapping.get(symbol, "")

    def _get_position_price(
        self,
        symbol: str,
        position: dict,
        market_prices: Optional[dict[str, float]] = None,
    ) -> float:
        """Get current price for a position / 获取持仓当前价格"""
        if market_prices and symbol in market_prices:
            return float(market_prices[symbol])
        return float(position.get("avg_entry_price", position.get("avgPrice", 0)))

    def _calculate_total_exposure(
        self,
        positions: dict[str, dict],
        market_prices: Optional[dict[str, float]] = None,
    ) -> float:
        """Calculate total portfolio notional exposure / 计算组合总名义敞口"""
        total = 0.0
        for sym, pos in positions.items():
            size = float(pos.get("size", pos.get("qty", 0)))
            price = self._get_position_price(sym, pos, market_prices)
            total += size * price
        return total

    def _emit_audit(self, event_type: str, symbol: str, reason: str) -> None:
        """Emit audit record / 发送审计记录"""
        if self._audit_callback:
            try:
                self._audit_callback({
                    "event_type": f"portfolio_risk_{event_type}",
                    "symbol": symbol,
                    "reason": reason,
                    "check_count": self._check_count,
                    "block_count": self._block_count,
                    "timestamp_ms": int(time.time() * 1000),
                })
            except Exception as e:
                logger.error("Portfolio risk audit error: %s", e)
