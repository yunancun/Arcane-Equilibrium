from __future__ import annotations

"""
risk_manager.py — ARCH-RC1 1C-3-D shim over RiskViewClient.

MODULE_NOTE (中文):
  原 1633 行 Python RiskManager 已被 ARCH-RC1 收編到 Rust ConfigStore +
  intent_processor + position_risk_evaluator。本檔僅保留兩個對外符號：

  1. `REGIME_TIME_MULTIPLIERS` — bridge_stats / test_winrate_param_fixes 仍消費
     的 regime → time multiplier 常量（純資料，無行為）。
  2. `RiskManager` — RiskViewClient 的薄子類，讓 paper_trading_wiring 等
     歷史 import 點維持向後相容；建構不接受 ipc_client（無 IPC 連接時所有
     deprecated 方法走 RiskViewClient 內建的 _warn_deprecated_once no-op）。

  禁止再加任何邏輯到本檔。新功能請改 RiskViewClient 或直接走 IPC。

MODULE_NOTE (English):
  The 1633-line Python RiskManager has been absorbed into Rust ConfigStore +
  intent_processor + position_risk_evaluator under ARCH-RC1. This file is a
  pure shim exposing two symbols:

  1. `REGIME_TIME_MULTIPLIERS` — still consumed by bridge_stats and one
     winrate test fixture (data only, no behaviour).
  2. `RiskManager` — thin RiskViewClient subclass kept for backwards-compat
     of historical import sites such as paper_trading_wiring.

  Do not add logic here. New behaviour belongs in RiskViewClient.
"""

from .risk_view_client import RiskViewClient

# Regime → time-stop multiplier constant. Consumed by bridge_stats.py and
# test_winrate_param_fixes.py. Pure data — no behaviour attached.
# 風險體制 → 時間止損乘數常量（純數據，無行為附帶）。
REGIME_TIME_MULTIPLIERS: dict[str, float] = {
    "trending": 1.5,
    "volatile": 0.8,
    "ranging": 0.8,
    "squeeze": 1.0,
    "unknown": 1.0,
}


class RiskManager(RiskViewClient):
    """Backwards-compat alias for RiskViewClient (ARCH-RC1 1C-3-D)."""

    def __init__(self) -> None:
        super().__init__(ipc_client=None)


__all__ = ["REGIME_TIME_MULTIPLIERS", "RiskManager"]
