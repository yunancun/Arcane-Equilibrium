"""AEG-S2 breadth ladder tier 凍結定義 + cumulative-nested 組裝。

MODULE_NOTE:
  模塊用途：凍結 4 個 breadth tier 定義，並從 FND-2 universe row 的 ``cohort_ids``
    （multi-membership array）組 **cumulative-nested** tier symbol-set。
  主要常數/函數：
    - ``BREADTH_TIERS``：凍結 tier 名 + 組裝規則 + nested/overlap 標記 + 序。
    - ``assemble_tiers(universe_rows)``：回 ``{tier: frozenset[symbol]}``。
    - ``assert_nested_invariant(tiers)``：機械驗 ``core25 ⊆ top_liquidity ⊆ full``。
    - ``ordered_tier_digest_basis``：tier 名 → monotonicity_rank（序，進 ladder digest）。
  硬邊界（算法權威 = PA 設計報告 §1.2 + E2 must-check #1）：
    - **tier 組裝唯一正確源 = FND-2 ``cohort_ids``（multi-membership）**，NOT
      ``recommended_tier``（single-pick 優先序裁決）。理由：breadth ladder 語義是嵌套
      加寬（core25 ⊂ top_liquidity ⊂ full），core25 成員（如 BTCUSDT）必須同時出現在
      更寬 tier；但 ``recommended_tier`` 對每 symbol 只給一個 tier（core25 > scanner >
      top_liq > full 優先序），BTCUSDT 只會是 ``core25_pinned`` 不在 ``top_liquidity``
      集 → 誤用會讓 tier 互斥、monotonicity 比較完全失真。
    - **只取 ``included=true`` 行**（FND-2 的 excluded 是診斷行，非 scoring-ready）。
    - top_liquidity 用 ``OR core25`` 顯式補 nested（FND-2 給 core25 同時帶
      ``full_survivorship`` 但 **不**自動帶 ``top_liquidity_40_50``，故 nested 須顯式補）。
    - tier 定義凍結；任何 tier 成員規則變更須升 ``BREADTH_LADDER_VERSION``（進 ladder
      digest），否則 monotonicity 對帳會誤判（MIT b.4：候選不能挑有利 tier 組成）。
  依賴：標準庫。import-time 零 DB / 零檔案 IO。
"""

from __future__ import annotations

from dataclasses import dataclass

# ── FND-2 cohort id 凍結字串（與 fnd2_pit_universe.cohorts.cohort_ids_for 對齊）──
# 為什麼在此重述而非 import FND-2 常數：(b) 消費 FND-2 **artifact**（CSV 的 cohort_ids
# JSON array 字串），契約是「artifact 欄值」非「FND-2 code 常數」；artifact 是凍結事實，
# 故在此釘住 artifact 內出現的 cohort id 字面值（PA §1.2 表）。
COHORT_FULL_SURVIVORSHIP = "full_survivorship"
COHORT_CORE25_PINNED = "core25_pinned"
COHORT_SCANNER_ACTIVE_ASOF = "scanner_active_asof"
COHORT_TOP_LIQUIDITY_40_50 = "top_liquidity_40_50"
COHORT_HISTORICAL_DELISTED = "historical_delisted"

# ── 4 breadth tier 凍結名（S0 §1.3 / MIT b.1 / PA §1.2）──
TIER_CORE25_PINNED = "core25_pinned"
TIER_SCANNER_ACTIVE_ASOF = "scanner_active_asof"
TIER_TOP_LIQUIDITY_40_50 = "top_liquidity_40_50"
TIER_FULL_SURVIVORSHIP = "full_survivorship"


@dataclass(frozen=True)
class BreadthTier:
    """單一 breadth tier 的凍結定義。

    name：tier 凍結名（= breadth_ladder.parquet 的 ``breadth_cohort`` 欄值）。
    required_cohorts：命中此 tier 所需的 cohort id（OR 語義；任一命中即入 tier）。
    nested：是否屬嚴格 nested 軸（core25/top_liq/full 為 True；scanner 為 overlap=False）。
    monotonicity_rank：nested tier 在 breadth 軸的序（core25=0 < top_liq=1 < full=2）；
      非 nested tier（scanner）為 None（單獨報，不入 monotonicity 主軸）。
    """

    name: str
    required_cohorts: tuple
    nested: bool
    monotonicity_rank: object  # int（nested）或 None（overlap-only）


# ── 凍結 tier 表（PA §1.2，組裝邏輯從 cohort_ids membership）──
# 為什麼 top_liquidity 含 core25（required_cohorts 含兩者）：nested 不變量要求
# core25 ⊆ top_liquidity；FND-2 不自動把 core25 symbol 標 top_liquidity_40_50，故在此
# 用 OR core25 顯式補 nested（PA §1.2 守則）。
# 為什麼 full_survivorship required_cohorts 只列 full_survivorship：FND-2 給**所有**
# included symbol 此 cohort（cohorts.py:104），故它等價「全 included」=最寬集。
BREADTH_TIERS = (
    BreadthTier(
        name=TIER_CORE25_PINNED,
        required_cohorts=(COHORT_CORE25_PINNED,),
        nested=True,
        monotonicity_rank=0,
    ),
    BreadthTier(
        name=TIER_TOP_LIQUIDITY_40_50,
        required_cohorts=(COHORT_CORE25_PINNED, COHORT_TOP_LIQUIDITY_40_50),
        nested=True,
        monotonicity_rank=1,
    ),
    BreadthTier(
        name=TIER_FULL_SURVIVORSHIP,
        required_cohorts=(COHORT_FULL_SURVIVORSHIP,),
        nested=True,
        monotonicity_rank=2,
    ),
    BreadthTier(
        name=TIER_SCANNER_ACTIVE_ASOF,
        required_cohorts=(COHORT_SCANNER_ACTIVE_ASOF,),
        nested=False,           # overlap-only（非嚴格 nested），單獨報
        monotonicity_rank=None,
    ),
)

# nested 軸 tier（monotonicity 主軸；按 rank 升序）。scanner 不在此（overlap-only）。
NESTED_TIER_ORDER = tuple(
    t.name for t in sorted(
        (t for t in BREADTH_TIERS if t.nested),
        key=lambda t: t.monotonicity_rank,
    )
)


def _cohort_ids_of(row: dict) -> frozenset:
    """從 universe row 取 cohort_ids 集合（容忍 list / JSON-array-string）。

    為什麼容忍兩種型別：universe_artifact 讀 CSV 時 cohort_ids 是 JSON array 字串
    （如 ``'["full_survivorship","core25_pinned"]'``），讀 parquet（all_varchar）亦同；
    但 synthetic 測試直接給 list。在此統一成 frozenset，下游組裝只用集合運算。
    """
    raw = row.get("cohort_ids")
    if raw is None:
        return frozenset()
    if isinstance(raw, (list, tuple, set, frozenset)):
        return frozenset(str(c) for c in raw)
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return frozenset()
        # JSON array 字串 → 解析；非 JSON（單值/逗號分隔）退化保守處理。
        import json
        try:
            parsed = json.loads(s)
            if isinstance(parsed, (list, tuple)):
                return frozenset(str(c) for c in parsed)
            return frozenset({str(parsed)})
        except (ValueError, TypeError):
            # 非 JSON：以逗號切（保守，不靜默吞）。
            return frozenset(p.strip() for p in s.split(",") if p.strip())
    return frozenset()


def assemble_tiers(universe_rows: list) -> dict:
    """從 FND-2 universe rows 組 cumulative-nested tier symbol-set。

    回 ``{tier_name: frozenset[symbol]}``（含 4 tier）。只取 ``included=true`` 行；
    tier 命中 = row 的 cohort_ids 與 tier.required_cohorts 有交集（OR 語義）。

    為什麼用 cohort_ids 而非 recommended_tier：見 MODULE_NOTE 硬邊界（E2 must-check #1）。
    """
    out: dict = {t.name: set() for t in BREADTH_TIERS}
    for row in universe_rows:
        if not _is_included(row):
            continue
        symbol = row.get("symbol")
        if not symbol:
            continue
        cohorts = _cohort_ids_of(row)
        for tier in BREADTH_TIERS:
            if cohorts & frozenset(tier.required_cohorts):
                out[tier.name].add(symbol)
    return {name: frozenset(members) for name, members in out.items()}


def _is_included(row: dict) -> bool:
    """row 是否 included（容忍 bool / 'true'/'false' 字串，CSV 讀回是字串）。"""
    val = row.get("included")
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "t", "1")
    return bool(val)


def assert_nested_invariant(tiers: dict) -> None:
    """機械驗 nested 不變量：core25 ⊆ top_liquidity_40_50 ⊆ full_survivorship。

    為什麼是硬斷言（非警告）：nested 是 monotonicity 比較的前提（嵌套加寬才能談「edge
    隨 breadth 存活」）；若 core25 有 symbol 不在 full，代表 tier 組裝錯（多半是誤用
    recommended_tier 的指紋）→ 直接 raise，不讓錯誤 ladder 產出（E2 must-check #1）。
    scanner_active_asof 是 overlap-only，不參與 nested 斷言。
    """
    core25 = tiers.get(TIER_CORE25_PINNED, frozenset())
    top_liq = tiers.get(TIER_TOP_LIQUIDITY_40_50, frozenset())
    full = tiers.get(TIER_FULL_SURVIVORSHIP, frozenset())
    missing_in_top = core25 - top_liq
    if missing_in_top:
        raise AssertionError(
            "nested 不變量違反：core25 成員不在 top_liquidity_40_50："
            f"{sorted(missing_in_top)}（多半是誤用 recommended_tier 組裝）"
        )
    missing_in_full = top_liq - full
    if missing_in_full:
        raise AssertionError(
            "nested 不變量違反：top_liquidity_40_50 成員不在 full_survivorship："
            f"{sorted(missing_in_full)}"
        )


def tier_by_name(name: str) -> BreadthTier:
    """凍結 tier 名 → BreadthTier。未知名 raise（不偽造 tier）。"""
    for t in BREADTH_TIERS:
        if t.name == name:
            return t
    raise KeyError(f"未知 breadth tier：{name!r}（凍結集合：{[t.name for t in BREADTH_TIERS]}）")


__all__ = [
    "BreadthTier",
    "BREADTH_TIERS",
    "NESTED_TIER_ORDER",
    "TIER_CORE25_PINNED",
    "TIER_SCANNER_ACTIVE_ASOF",
    "TIER_TOP_LIQUIDITY_40_50",
    "TIER_FULL_SURVIVORSHIP",
    "COHORT_FULL_SURVIVORSHIP",
    "COHORT_CORE25_PINNED",
    "COHORT_SCANNER_ACTIVE_ASOF",
    "COHORT_TOP_LIQUIDITY_40_50",
    "COHORT_HISTORICAL_DELISTED",
    "assemble_tiers",
    "assert_nested_invariant",
    "tier_by_name",
]
