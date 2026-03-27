"""
Indicator Base Class / 指标基类

MODULE_NOTE (中文):
  所有技术指标的抽象基类。定义统一接口：
  - name: 指标名称
  - compute(): 从 OHLCV 数据计算指标值
  - min_periods: 计算所需的最少 K线数量

  设计原则：
  1. 纯函数计算 — 给相同输入总是返回相同输出，无副作用
  2. 防御性输入检查 — 数据不足时返回 None 而非报错
  3. 零外部依赖 — 只用 Python 标准库，不依赖 numpy/pandas/ta-lib
     (减少部署复杂度，这些指标的计算量不需要向量化加速)

MODULE_NOTE (English):
  Abstract base class for all technical indicators. Defines uniform interface:
  - name: indicator name
  - compute(): calculate indicator values from OHLCV data
  - min_periods: minimum number of klines needed for calculation

  Design principles:
  1. Pure functional computation — same input always produces same output, no side effects
  2. Defensive input checks — returns None when data is insufficient, never raises
  3. Zero external dependencies — only Python stdlib, no numpy/pandas/ta-lib
     (reduces deployment complexity; these indicators don't need vectorized acceleration)

Safety invariant / 安全不变量:
  - 纯数学计算，不涉及任何外部 I/O / Pure math, no external I/O
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IndicatorBase(ABC):
    """
    Abstract base class for all technical indicators.
    所有技术指标的抽象基类。

    Subclasses must implement:
      - name (property): human-readable indicator name / 人类可读的指标名称
      - min_periods (property): minimum data points needed / 需要的最少数据点数
      - compute(**kwargs) -> dict | None: calculate and return indicator values / 计算并返回指标值
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable indicator name / 人类可读的指标名称"""
        ...

    @property
    @abstractmethod
    def min_periods(self) -> int:
        """
        Minimum number of data points (klines) required for a valid calculation.
        计算有效结果所需的最少数据点（K线）数量。
        """
        ...

    @abstractmethod
    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        """
        Compute the indicator value(s).
        计算指标值。

        Common kwargs:
          close  — list of close prices (newest last) / 收盘价列表（最新的在最后）
          high   — list of high prices / 最高价列表
          low    — list of low prices / 最低价列表
          open   — list of open prices / 开盘价列表
          volume — list of volume values / 成交量列表

        Returns:
          dict of indicator values (keys depend on the indicator), or None if insufficient data.
          指标值字典（键取决于具体指标），数据不足时返回 None。

        Examples:
          RSI.compute(close=[...]) → {"rsi": 65.3}
          MACD.compute(close=[...]) → {"macd": 0.5, "signal": 0.3, "histogram": 0.2}
          BollingerBands.compute(close=[...]) → {"upper": 101, "middle": 100, "lower": 99, "bandwidth": 0.02}
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name}, min_periods={self.min_periods})"
