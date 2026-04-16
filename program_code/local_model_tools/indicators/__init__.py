"""
STUB: Technical indicators package / 技术指标包 stub.

MODULE_NOTE (EN): Classes retained for legacy imports only. All computation
  is performed in Rust `openclaw_core::indicators`. `compute()` returns None.
MODULE_NOTE (中): 仅为兼容旧 import 保留类名。所有指标计算已迁移至 Rust
  `openclaw_core::indicators`，Python 侧 `compute()` 恒返回 None。
"""
from .base import IndicatorBase
from .atr import ATR
from .bollinger_bands import BollingerBands
from .extended import (
    ADX,
    KAMA,
    DonchianChannel,
    EWMAVolIndicator,
    HurstIndicator,
    VolumeRatio,
)
from .macd import MACD
from .moving_averages import EMA, SMA
from .rsi import RSI
from .stochastic import Stochastic

__all__ = [
    "IndicatorBase",
    "SMA",
    "EMA",
    "RSI",
    "BollingerBands",
    "MACD",
    "ATR",
    "Stochastic",
    "KAMA",
    "ADX",
    "HurstIndicator",
    "EWMAVolIndicator",
    "VolumeRatio",
    "DonchianChannel",
]
