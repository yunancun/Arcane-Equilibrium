"""
Cost-Aware Entry Gate — Pre-trade volatility vs. cost check
成本感知入場門檻 — 開倉前波動率 vs 交易成本檢查

MODULE_NOTE (中文):
  本模組在開倉前檢查預期波動是否足以覆蓋交易成本（手續費 + 滑點）。
  背景：Demo 交易數據顯示 14 筆贏利交易中 11 筆 gross profit < 手續費，
  即「贏了但實際虧錢」。此門檻確保只在波動足夠時才開倉。

  設計原則：
  - 確定性規則，不依賴歷史交易表現
  - Fail-open：ATR 數據不可用時放行（不阻塞冷啟動）
  - Per-symbol 成本計算（不同幣種手續費 + 滑點不同）
  - 安全閥：不能造成看盤一天完全沒有成交（Operator 2026-04-02 決策）

  公式：
    c_round_pct = (taker_fee + slippage) × 2          # 開+平倉各一次
    min_expected_move_pct = c_round_pct / max(0.3, win_rate) × 1.3  # 安全邊際
    若 ATR% < min_expected_move_pct → 拒絕開倉

MODULE_NOTE (English):
  This module checks whether expected volatility covers trading costs before opening.
  Background: Demo data showed 11 of 14 winning trades had gross profit < fees,
  meaning "wins that actually lost money". This gate ensures sufficient volatility.

  Design principles:
  - Deterministic rule, no dependency on historical trade performance
  - Fail-open: passes through when ATR data unavailable (no cold-start blocking)
  - Per-symbol cost calculation (different symbols have different fee + slippage)
  - Safety valve: must not cause zero trades for a full day (Operator decision 2026-04-02)

  Formula:
    c_round_pct = (taker_fee + slippage) × 2
    min_expected_move_pct = c_round_pct / max(0.3, win_rate) × 1.3
    If ATR% < min_expected_move_pct → reject entry

Safety invariant / 安全不變量:
  - 純決策邏輯，不執行任何交易操作 / Pure decision logic, no trading operations
  - Fail-open on missing data / 數據缺失時放行
  - 原則 5（生存 > 利潤）+ 原則 13（成本感知）
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# ─── Fee Constants / 手續費常量 ───
# Bybit linear USDT perpetual taker fee rate
# Bybit 永續合約 taker 手續費率
BYBIT_TAKER_FEE_RATE: float = 0.00055  # 0.055%


# ─── Slippage Tiers / 滑點分級 ───
# Source: paper_trading_engine.py SLIPPAGE_TIERS (duplicated to avoid circular import)
# 來源：paper_trading_engine.py SLIPPAGE_TIERS（複製以避免循環依賴）
# Sorted descending by 24h USD turnover threshold.
# 按 24h 成交額閾值降序排列。
SLIPPAGE_TIERS: list[tuple[float, float]] = [
    (1_000_000_000, 0.0001),   # >$1B turnover: 1 bps (BTC/ETH)
    (100_000_000,   0.0002),   # >$100M: 2 bps
    (10_000_000,    0.0005),   # >$10M: 5 bps
    (1_000_000,     0.0015),   # >$1M: 15 bps
    (0,             0.0030),   # <$1M: 30 bps (illiquid alts)
]

# Default slippage when volume data is unavailable / 無成交量數據時的默認滑點
DEFAULT_SLIPPAGE_RATE: float = 0.0005  # 5 bps


def _lookup_slippage(volume_24h: float) -> float:
    """
    Look up slippage rate by 24h volume tier.
    根據 24h 成交量查找滑點率。

    Args:
        volume_24h: 24-hour trading volume in USD / 24 小時成交量（USD）

    Returns:
        Slippage rate as a decimal (e.g. 0.0005 = 5 bps) / 滑點率（小數）
    """
    if volume_24h <= 0:
        return DEFAULT_SLIPPAGE_RATE
    for threshold, rate in SLIPPAGE_TIERS:
        if volume_24h >= threshold:
            return rate
    return DEFAULT_SLIPPAGE_RATE


def compute_round_trip_cost_pct(
    symbol: str,
    volume_24h: float = 0.0,
    taker_fee_rate: float = BYBIT_TAKER_FEE_RATE,
) -> float:
    """
    Compute round-trip cost as a percentage of notional value.
    計算來回交易成本佔名義價值的百分比。

    Round trip = open + close, each incurs taker fee + slippage.
    一來一回 = 開倉 + 平倉，各產生 taker 手續費 + 滑點。

    Args:
        symbol:         Trading pair (for logging) / 交易對（用於日誌）
        volume_24h:     24h volume in USD for slippage lookup / 24h 成交量
        taker_fee_rate: Taker fee rate (default Bybit linear) / Taker 手續費率

    Returns:
        Round-trip cost as percentage (e.g. 0.21 means 0.21%)
        來回成本百分比（如 0.21 表示 0.21%）
    """
    slippage_rate = _lookup_slippage(volume_24h)
    # Each leg: taker_fee + slippage; two legs for round trip
    # 每一腿：手續費 + 滑點；來回共兩腿
    cost_pct = (taker_fee_rate + slippage_rate) * 2 * 100.0  # convert to percentage
    return cost_pct


def should_reject_for_cost(
    symbol: str,
    atr_pct: float | None,
    win_rate: float = 0.5,
    daily_trade_count: int = 0,
    volume_24h: float = 0.0,
) -> tuple[bool, str]:
    """
    Decide whether to reject a trade entry due to insufficient volatility.
    決定是否因波動率不足拒絕開倉。

    Logic:
      1. ATR unavailable → fail-open (pass through, principle 6: uncertain → conservative
         but don't block cold-start)
      2. Compute min_expected_move_pct = c_round / max(0.3, win_rate) * 1.3
      3. Safety valve: if no trades today and ATR > half of round-trip cost → allow
         (Operator decision: avoid zero-trade days)
      4. If ATR% < min_expected_move_pct → reject

    邏輯：
      1. ATR 不可用 → fail-open（放行，原則 6：不確定時保守但不阻塞冷啟動）
      2. 計算 min_expected_move_pct = 來回成本 / max(0.3, 勝率) × 1.3
      3. 安全閥：若今天尚無成交且 ATR > 來回成本一半 → 放行
         （Operator 決策：避免整天零成交）
      4. 若 ATR% < min_expected_move_pct → 拒絕

    Args:
        symbol:            Trading pair / 交易對
        atr_pct:           ATR as % of price (e.g. 1.5 = 1.5%), or None / ATR 佔價格百分比
        win_rate:          Estimated win rate (0.0-1.0, default 0.5) / 估計勝率
        daily_trade_count: Number of trades already executed today / 今天已成交數
        volume_24h:        24h volume in USD for slippage lookup / 24h 成交量

    Returns:
        (should_reject: bool, reason: str)
        (是否拒絕, 原因字符串)
    """
    # ── Fail-open: no ATR data → allow (cold-start safety) ──
    # 無 ATR 數據 → 放行（冷啟動安全）
    if atr_pct is None:
        return (False, "atr_unavailable_pass_through")

    # ── Compute round-trip cost and minimum required move ──
    # 計算來回成本和最低所需波動
    c_round_pct = compute_round_trip_cost_pct(symbol, volume_24h=volume_24h)
    clamped_wr = max(0.3, min(1.0, win_rate))  # clamp to [0.3, 1.0] / 限制在 [0.3, 1.0]
    min_move_pct = c_round_pct / clamped_wr * 1.3  # 30% safety margin / 30% 安全邊際

    # ── Safety valve: avoid zero-trade days ──
    # 安全閥：避免整天零成交（Operator 決策 2026-04-02）
    # If no trades today and ATR is at least half the round-trip cost, allow entry.
    # This ensures some trades execute even in low-volatility markets.
    # 若今天尚無成交且 ATR 至少為來回成本一半，放行。
    if daily_trade_count == 0 and atr_pct > c_round_pct * 0.5:
        return (False, "daily_safety_valve")

    # ── Core check: ATR must exceed minimum required move ──
    # 核心檢查：ATR 必須超過最低所需波動
    if atr_pct < min_move_pct:
        return (
            True,
            "insufficient_volatility: atr=%.4f < min=%.4f (cost=%.4f wr=%.2f)"
            % (atr_pct, min_move_pct, c_round_pct, clamped_wr),
        )

    return (False, "")
