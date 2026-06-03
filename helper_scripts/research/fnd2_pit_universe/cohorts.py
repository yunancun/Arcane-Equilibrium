"""FND-2 cohort / tier 凍結定義。

MODULE_NOTE:
  模塊用途：凍結 FND-2 universe 的 cohort 成員與 tier 排序規則。core25 成員從 seed
    CSV（``docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-31--s1_w1_s1_
    survivorship_universe_18mo_usdt_perp.csv``，sha256 fbf14a3f…）的 25 個
    ``in_core25_pinned=t`` 行提取並凍結，**E1 不自創**（OQ-2：以 seed 為準）。
  主要常數/函數：
    - ``CORE25_PINNED``：凍結的 25-symbol 集合。
    - ``RECOMMENDED_TIER_*`` / ``classify_recommended_tier``：tier 優先序裁決。
    - ``classify_status``：raw status → status_class 映射。
  硬邊界：
    - core25 是凍結常數，禁止依當前 DB 狀態動態重算（否則 survivorship 對照失效）。
    - tier 由 turnover **排序**得出（``top_liquidity_40_50``），但 turnover 缺失
      **絕不**把 symbol 排除（liquidity 缺 ≠ 排除，FND-2 §5 / contract §5）。
  依賴：標準庫。
"""

from __future__ import annotations

from typing import Optional

# ── core25 pinned（從 seed CSV in_core25_pinned=t 的 25 行提取，凍結，canonical 升序）──
# 為什麼凍結：core25 是 S1 首要分析 cohort（contract §0），且 seed 是 regression
# check（contract「seed 是 regression check」）。動態重算會讓 survivorship/seed 對照
# 失去意義。若未來需改成員，須走 PM/MIT 決策再升 BUILDER_VERSION。
CORE25_PINNED = (
    "ADAUSDT", "APTUSDT", "ARBUSDT", "ATOMUSDT", "AVAXUSDT",
    "BCHUSDT", "BTCUSDT", "DOGEUSDT", "DOTUSDT", "ETCUSDT",
    "ETHUSDT", "FILUSDT", "ICPUSDT", "INJUSDT", "LINKUSDT",
    "LTCUSDT", "NEARUSDT", "OPUSDT", "POLUSDT", "SOLUSDT",
    "SUIUSDT", "TONUSDT", "TRXUSDT", "UNIUSDT", "XRPUSDT",
)
CORE25_PINNED_SET = frozenset(CORE25_PINNED)
assert len(CORE25_PINNED) == 25, "core25 必須恰為 25 成員（seed 凍結）"

# ── recommended_tier 枚舉（PA §4 Step G，算法權威；非 seed 的 tier 命名）──
# 為什麼用 PA 枚舉而非 seed 命名：seed（2026-05-31）的 tier 命名（current_bybit_
# usdt_perp / historical_delisted_18mo / scanner_24h_dynamic）早於本 contract 的
# tier 分類法。本 builder 以 PA §4 Step G 枚舉為 output 權威；seed regression 在
# drift_explanation 解釋此 tier 命名差異（named drift，非靜默）。
TIER_CORE25_PINNED = "core25_pinned"
TIER_SCANNER_ACTIVE_ASOF = "scanner_active_asof"
TIER_TOP_LIQUIDITY_40_50 = "top_liquidity_40_50"
TIER_FULL_SURVIVORSHIP = "full_survivorship"

# top_liquidity tier 的 turnover rank 上界（rank ≤ 此值且 liquidity source 有 PIT
# 記錄者）。PA §4 Step G「turnover rank ≤ 50」。
TOP_LIQUIDITY_RANK_MAX = 50

# ── status_class 映射（PA §6 / contract）──
_STATUS_CLASS_MAP = {
    "trading": "trading",
    "closed": "closed",
    "prelaunch": "prelaunch",
    "delivering": "delivering",
    "settled": "settled",
    "delisted": "delisted",
}


def classify_status(status_raw: Optional[str]) -> str:
    """raw status → status_class（小寫枚舉）。未知值 → ``other``（不偽造分類）。"""
    if not status_raw:
        return "other"
    return _STATUS_CLASS_MAP.get(status_raw.strip().lower(), "other")


def classify_recommended_tier(
    symbol: str,
    *,
    in_scanner_window: bool,
    turnover_rank: Optional[int],
) -> str:
    """裁決 recommended_tier（優先序，PA §4 Step G）。

    優先序：core25 > scanner-active > top-liquidity（turnover rank ≤ 50 且 rank 已知）
    > full_survivorship（default）。

    為什麼 turnover 缺失（rank=None）不影響 inclusion：liquidity 只能排序 tier，
    不能當 inclusion 條件（FND-2 §5）。rank 未知時退為 full_survivorship，symbol
    仍 included（由 builder 的 inclusion 規則決定，與 tier 無關）。
    """
    if symbol in CORE25_PINNED_SET:
        return TIER_CORE25_PINNED
    if in_scanner_window:
        return TIER_SCANNER_ACTIVE_ASOF
    if turnover_rank is not None and turnover_rank <= TOP_LIQUIDITY_RANK_MAX:
        return TIER_TOP_LIQUIDITY_40_50
    return TIER_FULL_SURVIVORSHIP


def cohort_ids_for(
    symbol: str,
    *,
    in_scanner_window: bool,
    seen_delisted: bool,
    turnover_rank: Optional[int],
) -> list:
    """symbol 命中的所有 cohort id（array，PA §4 Step G ``cohort_ids``）。

    cohort 是「集合歸屬」（可多重），與 recommended_tier（單一優先序裁決）不同。
    """
    out = ["full_survivorship"]
    if symbol in CORE25_PINNED_SET:
        out.append("core25_pinned")
    if in_scanner_window:
        out.append("scanner_active_asof")
    if seen_delisted:
        out.append("historical_delisted")
    if turnover_rank is not None and turnover_rank <= TOP_LIQUIDITY_RANK_MAX:
        out.append("top_liquidity_40_50")
    return out


__all__ = [
    "CORE25_PINNED",
    "CORE25_PINNED_SET",
    "TIER_CORE25_PINNED",
    "TIER_SCANNER_ACTIVE_ASOF",
    "TIER_TOP_LIQUIDITY_40_50",
    "TIER_FULL_SURVIVORSHIP",
    "TOP_LIQUIDITY_RANK_MAX",
    "classify_status",
    "classify_recommended_tier",
    "cohort_ids_for",
]
