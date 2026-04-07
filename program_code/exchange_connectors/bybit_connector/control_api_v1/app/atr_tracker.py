from __future__ import annotations

"""
ATR Tracker / ATR 追蹤器

MODULE_NOTE (中文):
  從 risk_manager.py 抽出的純價格歷史追蹤器（ARCH-RC1 1C-3-B 拆分）。
  與 RiskManager 完全解耦，可由任何 caller 獨立持有。
  Rust 引擎在 tick_pipeline.rs 已有自己的 PriceHistoryTracker，本檔僅供
  Python bridge / 工具腳本在不需要 IPC 來回的情況下做本地 ATR 推斷。

MODULE_NOTE (English):
  Pure price-history tracker extracted from risk_manager.py (ARCH-RC1 1C-3-B
  split). Fully decoupled from RiskManager — any caller can own its own
  instance. The Rust engine has its own PriceHistoryTracker in
  tick_pipeline.rs; this file exists for Python bridges / tooling that need
  a local ATR estimate without round-tripping through IPC.
"""

import time
from typing import Any

# Price history window for ATR calculation / ATR 計算用價格歷史窗口
ATR_WINDOW_SECONDS = 300  # 5 minutes of tick data
ATR_MIN_SAMPLES = 10      # Minimum samples to compute ATR

# Spike detection thresholds / 尖刺檢測閾值
SPIKE_REVERT_THRESHOLD_PCT = 0.5    # Price reverts >50% within window → spike
SPIKE_WINDOW_SECONDS = 180          # 3 minute window for spike detection


class PriceHistoryTracker:
    """
    Tracks recent price ticks per symbol for ATR and spike detection.
    跟踪每个品种的近期价格 tick，用于 ATR 和尖刺检测。
    """

    def __init__(self, window_sec: float = ATR_WINDOW_SECONDS) -> None:
        self._history: dict[str, list[tuple[float, float]]] = {}  # symbol → [(ts, price)]
        self._window_sec = window_sec

    def record(self, symbol: str, price: float) -> None:
        if symbol not in self._history:
            self._history[symbol] = []
        now = time.time()
        self._history[symbol].append((now, price))
        # Prune old entries
        cutoff = now - self._window_sec
        self._history[symbol] = [(t, p) for t, p in self._history[symbol] if t >= cutoff]
        # Prune symbols with no recent data (prevent unbounded growth)
        if len(self._history) > 100:
            stale_symbols = [s for s, hist in self._history.items() if not hist]
            for s in stale_symbols:
                del self._history[s]

    def bootstrap_from_klines(self, symbol: str, klines: list) -> int:
        """
        Seed price history from historical kline close prices so ATR is
        immediately available after restart (eliminates cold-start blind period).
        從歷史 K線收盤價初始化價格歷史，使重啟後 ATR 立即可用（消除冷啟動盲期）。
        """
        if not klines:
            return 0

        sample = klines[-60:] if len(klines) > 60 else list(klines)

        now = time.time()
        count = len(sample)
        if count == 0:
            return 0

        spacing = self._window_sec / (count + 1)

        if symbol not in self._history:
            self._history[symbol] = []

        seeded = 0
        for i, bar in enumerate(sample):
            close_price = getattr(bar, "close", None)
            if close_price is None or close_price <= 0:
                continue
            synthetic_ts = now - self._window_sec + spacing * (i + 1)
            self._history[symbol].append((synthetic_ts, close_price))
            seeded += 1

        return seeded

    def get_prices(self, symbol: str) -> list[tuple[float, float]]:
        return self._history.get(symbol, [])

    def compute_atr_pct(self, symbol: str) -> float | None:
        """
        Compute ATR-like metric as percentage of price.
        計算 ATR 類指標（占價格的百分比）。
        """
        prices = self.get_prices(symbol)
        if len(prices) < ATR_MIN_SAMPLES:
            return None
        changes = []
        for i in range(1, len(prices)):
            prev_p = prices[i - 1][1]
            curr_p = prices[i][1]
            if prev_p > 0:
                changes.append(abs(curr_p - prev_p) / prev_p * 100)
        if not changes:
            return None
        return sum(changes) / len(changes)

    def detect_spike(self, symbol: str, current_price: float) -> dict[str, Any] | None:
        """
        Detect if current price movement looks like a stop-hunting spike.
        檢測當前價格走勢是否像止損獵殺的尖刺。
        """
        prices = self.get_prices(symbol)
        if len(prices) < 5:
            return None

        now = time.time()
        window_cutoff = now - SPIKE_WINDOW_SECONDS
        recent = [(t, p) for t, p in prices if t >= window_cutoff]
        if len(recent) < 3:
            return None

        min_p = min(p for _, p in recent)
        max_p = max(p for _, p in recent)
        first_p = recent[0][1]

        if first_p <= 0 or max_p <= min_p:
            return None

        total_range = max_p - min_p
        range_pct = total_range / first_p * 100

        if current_price > first_p:
            revert_from_min = (current_price - min_p) / total_range if total_range > 0 else 0
            if revert_from_min > SPIKE_REVERT_THRESHOLD_PCT and range_pct > 0.3:
                return {
                    "type": "spike_down_reverted",
                    "range_pct": round(range_pct, 3),
                    "revert_fraction": round(revert_from_min, 3),
                    "confidence": min(revert_from_min, 0.95),
                }
        else:
            revert_from_max = (max_p - current_price) / total_range if total_range > 0 else 0
            if revert_from_max > SPIKE_REVERT_THRESHOLD_PCT and range_pct > 0.3:
                return {
                    "type": "spike_up_reverted",
                    "range_pct": round(range_pct, 3),
                    "revert_fraction": round(revert_from_max, 3),
                    "confidence": min(revert_from_max, 0.95),
                }

        return None
