"""AEG-S2 breadth ladder — 讀 FND-2 universe artifact + survivorship mask 繼承。

MODULE_NOTE:
  模塊用途：讀 FND-2 PIT universe artifact（universe.csv 為 SoT，universe.parquet 可選），
    取 ``included`` / ``cohort_ids`` / ``alive_from_utc`` / ``alive_to_utc`` /
    ``seen_delisted`` 等欄，組成 breadth ladder 所需的 universe rows + alive_mask +
    per-tier metadata（top_liquidity 降級）。**0 DB（只讀檔）**。
  主要函數：
    - ``load_fnd2_universe``：讀 universe.csv → ``(rows, meta)``（rows=每 symbol dict）。
    - ``build_alive_mask``：從 included rows 組 ``{symbol: (alive_from, alive_to)}``
      （survivorship **繼承不重算**，MIT b.2）。
    - ``build_seen_delisted_map``：``{symbol: bool}``（artifact 權威 delisted flag）。
    - ``tier_quality_and_exclusion``：per-tier metadata（top_liquidity diagnostic-only，
      OQ-B3 R-1）。
  硬邊界（PA §4 Step 1-2 + D-3；E2 must-check #3）：
    - **survivorship 繼承不重算**：alive_mask 直接用 artifact 的 ``alive_from_utc`` /
      ``alive_to_utc``；(b) 0 自寫 listed_at / symbol_universe_snapshots 查詢（避免 R-1
      trap：snapshot ts 僅 27d 不可作 lifetime 邊界）。**禁 current-survivor 捷徑**。
    - **top_liquidity_40_50 cross-section rank 是 asof-constant（KNOWN LEAK FLAG）**：
      FND-2 turnover rank 來自 latest snapshot at asof（single point）套整窗 = mild
      look-ahead；per-rebalance PIT rank 無資料源（market.market_tickers latest-only，
      S0 §3.1；index/mark persistence bug S0 §1.7）。故 top_liquidity tier 標
      ``tier_quality='liquidity_source_not_pit'`` + ``tier_rank_pit_mode='asof_constant'``
      + ``excluded_from_promotion=true``（diagnostic-only，**待 MIT review 確認**，OQ-B3）。
      core25 / full_survivorship 成員資格不依 liquidity，無此問題，是 monotonicity 主軸。
    - 只讀檔（FND-2 artifact），0 PG / 0 寫；0 import control_api_v1 runtime。
  依賴：標準庫（csv / json / datetime）。parquet 讀經 duckdb（延遲 import，可選，csv 為
    SoT）。import-time 零 DB 依賴。
"""

from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path
from typing import Optional

from . import tiers as tiers_mod

# FND-2 artifact 內 (b) 需要的欄（子集，PA §1.1）。其餘 FND-2 欄 passthrough 不強制。
_REQUIRED_FND2_COLUMNS = (
    "symbol", "cohort_ids", "included", "alive_from_utc", "alive_to_utc",
    "seen_delisted", "recommended_tier", "unknown_lifetime",
)


def load_fnd2_universe(run_dir: Path) -> tuple:
    """讀 FND-2 universe artifact（universe.csv SoT）→ ``(rows, meta)``。

    run_dir：FND-2 artifact run 目錄（含 universe.csv + universe_summary.json + manifest）。
    rows：``list[dict]``（每 symbol 一個，含 _REQUIRED_FND2_COLUMNS）。
    meta：``{fnd2_universe_id, fnd2_run_id, fnd2_summary, fnd2_manifest}``（provenance 鏈）。

    為什麼用 csv 不用 parquet：universe.csv 是 FND-2 SoT（artifact.py:66），parquet 是
    可選鏡像；讀 csv 純標準庫、跨平台、無 duckdb 依賴（MIT/E4 Mac 可跑）。
    """
    run_dir = Path(run_dir)
    csv_path = run_dir / "universe.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"FND-2 universe.csv 不存在：{csv_path}")

    rows = []
    with open(csv_path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        _assert_required_columns(header, csv_path)
        for r in reader:
            rows.append(r)

    meta = _load_meta(run_dir, rows)
    return rows, meta


def _assert_required_columns(header: list, path: Path) -> None:
    """缺必要欄 → raise（fail-loud，不靜默用空值）。"""
    missing = [c for c in _REQUIRED_FND2_COLUMNS if c not in header]
    if missing:
        raise ValueError(f"FND-2 universe.csv 缺必要欄 {missing}：{path}")


def _load_meta(run_dir: Path, rows: list) -> dict:
    """從 universe_summary.json / manifest.json 取 universe_id / run_id provenance。"""
    universe_id = None
    fnd2_run_id = None
    summary = None
    manifest = None
    summary_path = run_dir / "universe_summary.json"
    manifest_path = run_dir / "manifest.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        universe_id = summary.get("universe_id")
        fnd2_run_id = summary.get("run_id")
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        universe_id = universe_id or manifest.get("universe_id")
        fnd2_run_id = fnd2_run_id or manifest.get("run_id")
    # 退化：summary/manifest 缺 → 從 row 取 universe_id（CSV 有 universe_id 欄）。
    if universe_id is None and rows:
        universe_id = rows[0].get("universe_id")
    if fnd2_run_id is None and rows:
        fnd2_run_id = rows[0].get("run_id")
    return {
        "fnd2_universe_id": universe_id or "unknown_fnd2_universe_id",
        "fnd2_run_id": fnd2_run_id or "unknown_fnd2_run_id",
        "fnd2_summary": summary,
        "fnd2_manifest": manifest,
    }


def _is_included(row: dict) -> bool:
    val = row.get("included")
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "t", "1")
    return bool(val)


def _is_true(val) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "t", "1")
    return bool(val)


def _parse_utc(s: Optional[str]) -> Optional[dt.datetime]:
    """ISO8601 字串 → tz-aware UTC datetime。None/空 → None。"""
    if s is None:
        return None
    s2 = str(s).strip()
    if not s2:
        return None
    if s2.endswith("Z"):
        s2 = s2[:-1] + "+00:00"
    try:
        d = dt.datetime.fromisoformat(s2)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def build_alive_mask(rows: list) -> dict:
    """從 included rows 組 ``{symbol: (alive_from_utc, alive_to_utc)}``（繼承不重算）。

    為什麼直接繼承 artifact 值：MIT b.2「per-symbol PIT mask 繼承 FND-2，不重算」——
    避免 R-1 trap（snapshot ts 僅 27d）。(b) 把此 mask 傳給候選評估器，候選只能在
    [alive_from, alive_to] 內持倉（上市前/delist 後 signal=0）。
    """
    mask = {}
    for row in rows:
        if not _is_included(row):
            continue
        symbol = row.get("symbol")
        if not symbol:
            continue
        alive_from = _parse_utc(row.get("alive_from_utc"))
        alive_to = _parse_utc(row.get("alive_to_utc"))
        mask[symbol] = (alive_from, alive_to)
    return mask


def build_seen_delisted_map(rows: list) -> dict:
    """從 included rows 組 ``{symbol: seen_delisted(bool)}``（artifact 權威 delisted flag）。"""
    out = {}
    for row in rows:
        if not _is_included(row):
            continue
        symbol = row.get("symbol")
        if not symbol:
            continue
        out[symbol] = _is_true(row.get("seen_delisted"))
    return out


def count_tier_seen_delisted(tier_symbols, seen_delisted_map: dict) -> int:
    """tier 內被 artifact 標 delisted 的 symbol 數（healthcheck + TierResult 覆寫用）。"""
    return sum(1 for s in tier_symbols if seen_delisted_map.get(s, False))


def tier_quality_and_exclusion() -> tuple:
    """per-tier metadata（tier_quality / tier_rank_pit_mode / promotion-exclusion）。

    回 ``(quality_by_name, pit_mode_by_name, exclusion_by_name)``，凍結（PA §4 Step 2 +
    OQ-B3）：
      - core25_pinned / full_survivorship：成員資格不依 liquidity → ``ok`` / ``n/a`` /
        不排除（monotonicity 主軸）。
      - top_liquidity_40_50：asof-constant rank（KNOWN LEAK FLAG）→
        ``liquidity_source_not_pit`` / ``asof_constant`` / **excluded_from_promotion=
        true**（diagnostic-only，待 MIT review 確認 per-rebalance PIT 不可行，OQ-B3）。
      - scanner_active_asof：overlap-only（asof-snapshot）→ ``overlap_only`` / ``n/a`` /
        excluded（本就 diagnostic，非 nested 主軸）。

    為什麼把 top_liquidity 標 excluded 而非靜默納入：S0 §3.1（market.market_tickers
    latest-only）+ S0 §1.7（index/mark persistence bug）→ per-rebalance liquidity 史不
    存在 → asof-constant 是 mild look-ahead（後來才流動的 symbol 被選入 2024）；誠實標記
    不偽裝 PIT（E2 must-check #3 / R-1）。
    """
    quality = {
        tiers_mod.TIER_CORE25_PINNED: "ok",
        tiers_mod.TIER_FULL_SURVIVORSHIP: "ok",
        tiers_mod.TIER_TOP_LIQUIDITY_40_50: "liquidity_source_not_pit",
        tiers_mod.TIER_SCANNER_ACTIVE_ASOF: "overlap_only",
    }
    pit_mode = {
        tiers_mod.TIER_CORE25_PINNED: "n/a",
        tiers_mod.TIER_FULL_SURVIVORSHIP: "n/a",
        tiers_mod.TIER_TOP_LIQUIDITY_40_50: "asof_constant",
        tiers_mod.TIER_SCANNER_ACTIVE_ASOF: "n/a",
    }
    exclusion = {
        tiers_mod.TIER_CORE25_PINNED: (False, None),
        tiers_mod.TIER_FULL_SURVIVORSHIP: (False, None),
        tiers_mod.TIER_TOP_LIQUIDITY_40_50: (True, "liquidity_source_not_pit_asof_constant"),
        tiers_mod.TIER_SCANNER_ACTIVE_ASOF: (True, "scanner_overlap_only_not_nested_axis"),
    }
    return quality, pit_mode, exclusion


__all__ = [
    "load_fnd2_universe",
    "build_alive_mask",
    "build_seen_delisted_map",
    "count_tier_seen_delisted",
    "tier_quality_and_exclusion",
]
