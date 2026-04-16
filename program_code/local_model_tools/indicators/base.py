"""
STUB: Indicator base class / 指标基类 stub.

MODULE_NOTE (EN): Computation moved to Rust `openclaw_core::indicators`. This
  Python class exists only to preserve the public interface for legacy imports;
  `compute()` returns None.
MODULE_NOTE (中): 计算已迁移至 Rust `openclaw_core::indicators`。此 Python
  类仅为兼容旧 import 保留接口，`compute()` 返回 None。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IndicatorBase(ABC):
    @property
    def name(self) -> str:
        return self.__class__.__name__

    @property
    def min_periods(self) -> int:
        return 1

    @abstractmethod
    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        ...


__all__ = ["IndicatorBase"]
