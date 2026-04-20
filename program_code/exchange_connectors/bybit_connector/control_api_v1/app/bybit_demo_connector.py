"""
Bybit Exchange Utility Functions — Price and Qty rounding helpers
Bybit 交易所工具函數 — 價格與數量精度取整

MODULE_NOTE (中文):
  DEAD-PY-2 清理後，本模塊僅保留兩個純工具函數：
  - round_qty_for_exchange()：按交易所 qtyStep 向下取整數量
  - round_price_for_exchange()：按交易所 tickSize 取整價格

  BybitDemoConnector 交易類已刪除（DEAD-PY-2）。
  Demo 帳戶讀取改用 httpx BybitClient（只讀）。
  Demo 訂單執行通過 Rust IPC（openclaw_engine）。

MODULE_NOTE (English):
  After DEAD-PY-2 cleanup, this module retains only two pure utility functions:
  - round_qty_for_exchange(): floor-round qty to exchange qtyStep precision
  - round_price_for_exchange(): round price to exchange tickSize precision

  BybitDemoConnector trading class deleted (DEAD-PY-2).
  Demo account reads use the httpx BybitClient (read-only).
  Demo order execution goes through Rust IPC (openclaw_engine).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Kept for any external code that imports these constants.
# 保留供外部代碼導入這些常量。
DEMO_BASE_URL = "https://api-demo.bybit.com"
RECV_WINDOW = "5000"


def round_qty_for_exchange(
    qty: float,
    category: str = "linear",
    qty_step: float | None = None,
) -> float:
    """
    Round qty to Bybit exchange step precision.
    四捨五入到 Bybit 交易所步長精度。

    When qty_step is provided (from SymbolCategoryRegistry), rounds to the
    nearest multiple of qty_step using floor (to avoid exceeding balance).
    當提供 qty_step 時（來自 SymbolCategoryRegistry），取 qty_step 的整數倍（向下）。

    Fallback heuristic (qty_step=None): inverse or qty >= 1 → integer; qty < 1 → 3dp.
    回退啟發式（qty_step=None）：inverse 或 qty >= 1 → 取整；qty < 1 → 3 位小數。
    """
    import math

    # Use actual qty_step from exchange when available / 有步長數據時使用精確取整
    if qty_step and qty_step > 0:
        floored = math.floor(qty / qty_step) * qty_step
        # Derive decimal places from qty_step to avoid float artifacts
        # 從 qty_step 推導小數位數避免浮點誤差
        step_str = f"{qty_step:.10f}".rstrip("0")
        decimals = len(step_str.split(".")[-1]) if "." in step_str else 0
        return round(floored, decimals)

    # Fallback heuristic / 回退啟發式
    if category == "inverse" or qty >= 1.0:
        return float(round(qty))
    return round(qty, 3)


def round_price_for_exchange(
    price: float,
    tick_size: float | None = None,
    direction: str = "floor",
) -> float:
    """
    Round price to exchange tick size precision with direction control.
    按交易所 tickSize 精度取整價格，支持方向控制。

    direction:
      "floor" — round down (default, conservative for long stop-loss)
      "ceil"  — round up (conservative for short stop-loss)
      "nearest" — round to nearest tick (for limit orders)

    direction:
      "floor" — 向下取整（默認，保守用於多頭止損）
      "ceil"  — 向上取整（保守用於空頭止損）
      "nearest" — 取最近的 tick（用於限價單）
    """
    if tick_size and tick_size > 0:
        import math
        if direction == "ceil":
            aligned = math.ceil(price / tick_size) * tick_size
        elif direction == "nearest":
            aligned = round(price / tick_size) * tick_size
        else:  # "floor" or default
            aligned = math.floor(price / tick_size) * tick_size
        return round(aligned, 10)
    return round(price, 8)
