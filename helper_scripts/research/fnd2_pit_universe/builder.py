"""FND-2 builder 純函數核心 — lifecycle → lifetime mask → cohort/tier → universe rows。

MODULE_NOTE:
  模塊用途：FND-2 PIT universe 的**純函數**核心。輸入 per-symbol lifecycle dataclass
    list + 顯式 window 參數，輸出 universe row list + summary dict。**0 DB 依賴**，全
    in-memory，可用 synthetic 資料測（mirror multiday 的 leak-test 哲學：核心邏輯純
    函數，Mac 可跑）。
  主要類/函數：
    - ``SymbolLifecycle``：data_loader 聚合出的單 symbol lifecycle 輸入。
    - ``WindowSpec``：顯式分析窗（無隱式 now()）。
    - ``build_universe``：核心 builder（Step D-H），回 ``(rows, summary)``。
    - ``compute_universe_id`` / ``ordered_row_digest``：determinism digest。
  硬邊界（算法權威 = PA 設計報告 §4 修正版，**非** contract §3 字面）：
    - **lifetime 邊界源**：``listed_at``/``delisted_at`` 是唯一權威。``first_seen_ts``
      /``last_seen_ts`` **僅診斷**，絕不作 lifetime 邊界（snapshot ts 只跨 27 天，
      coalesce 到 ts 會把 2024 上市幣的 alive_from 錯夾到 2026-05 → 全錯）。兩權威欄
      全 NULL 才標 ``unknown_lifetime``（不 coalesce 到 ts）。
    - **含 delisted**：inclusion 是 lifetime ∩ window 的對稱判定，含窗內 delist 的
      symbol。絕無 current-survivor 捷徑、無 LIMIT/截斷。
    - **determinism**：row 固定排序（by symbol），float 固定格式化（%.12g），同
      input 同 universe_id（T4）。
  依賴：標準庫（datetime / hashlib / dataclasses）。
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass, field
from typing import Optional

from . import BUILDER_VERSION, QUERY_SCHEMA_VERSION
from .cohorts import (
    classify_recommended_tier,
    classify_status,
    cohort_ids_for,
    CORE25_PINNED_SET,
)

# universe.csv/.parquet 凍結欄序（contract §4 / PA §6）。任何欄序變更須升
# UNIVERSE_SCHEMA_VERSION（影響 ordered_row_digest → universe_id）。
UNIVERSE_COLUMNS = (
    "run_id", "universe_id", "asof_utc", "exchange", "category", "symbol", "status",
    "status_raw", "status_class", "recommended_tier", "cohort_ids",
    "current_survivor_only_comparison", "in_core25_pinned", "in_scanner_window",
    "listed_at_utc", "delisted_at_utc", "first_seen_ts_utc", "last_seen_ts_utc",
    "alive_from_utc", "alive_to_utc", "alive_days_in_window",
    "unknown_lifetime", "is_delisted_at_asof", "seen_delisted", "statuses_seen",
    "base_coin", "quote_coin", "contract_type", "tick_size", "qty_step", "min_notional",
    "source_uri", "source_snapshot_ts_utc", "source_payload_hash",
    "included", "inclusion_reason", "exclusion_reason",
)

# digest 用的 row 欄子集（穩定、語義關鍵欄；排除 run_id/universe_id 自身避免循環）。
# 為什麼不含 run_id：universe_id 必須對「同 DB 狀態 + 同窗」穩定，與 run_id 無關
# （contract §4）。為什麼不含 universe_id：它是 digest 的輸出。
_DIGEST_COLUMNS = (
    "symbol", "status_raw", "status_class", "recommended_tier", "cohort_ids",
    "in_core25_pinned", "in_scanner_window",
    "listed_at_utc", "delisted_at_utc",
    "alive_from_utc", "alive_to_utc", "alive_days_in_window",
    "unknown_lifetime", "is_delisted_at_asof", "seen_delisted", "statuses_seen",
    "tick_size", "qty_step", "min_notional",
    "source_payload_hash", "included", "inclusion_reason", "exclusion_reason",
)


@dataclass
class SymbolLifecycle:
    """單 symbol 的 lifecycle 聚合 + latest 投影（data_loader 產，builder 消費）。

    為什麼把聚合與 latest 投影併進一個 dataclass：builder 是純函數，所有 per-symbol
    輸入都在此封裝，測試可直接構造 synthetic instance（不連 DB）。
    時間欄全為 timezone-aware UTC datetime 或 None。
    """

    symbol: str
    # lifecycle 聚合（Step A）
    listed_at: Optional[dt.datetime]
    delisted_at: Optional[dt.datetime]
    seen_delisted: bool
    statuses_seen: tuple
    first_seen_ts: Optional[dt.datetime]  # 診斷欄，非 lifetime 權威
    last_seen_ts: Optional[dt.datetime]   # 診斷欄，非 lifetime 權威
    # latest 投影（Step B）
    status_raw: Optional[str]
    base_coin: Optional[str]
    quote_coin: Optional[str]
    contract_type: Optional[str]
    tick_size: Optional[float]
    qty_step: Optional[float]
    min_notional: Optional[float]
    is_delisted_at_asof: bool
    source_uri: Optional[str]
    source_snapshot_ts: Optional[dt.datetime]
    source_payload_hash: Optional[str]  # hex text（data_loader encode）
    # tier 排序源（Step C）+ scanner overlap（Step G）
    turnover_24h: Optional[float] = None
    in_scanner_window: bool = False


@dataclass
class WindowSpec:
    """顯式分析窗（無隱式 now()，contract §1）。全 UTC、tz-aware。"""

    window_start_utc: dt.datetime
    window_end_utc: dt.datetime
    asof_utc: dt.datetime
    closed_bar_cutoff_utc: dt.datetime
    exchange: str = "bybit"
    category: str = "linear"


def _iso(d: Optional[dt.datetime]) -> Optional[str]:
    """tz-aware UTC datetime → ISO8601 字串。None 保留 None。"""
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc).isoformat()


def _fmt_num(x: Optional[float]) -> Optional[str]:
    """數值固定格式化（determinism，避免平台浮點漂移）。None 保留 None。

    為什麼 %.12g：tick_size/qty_step/min_notional 來自 PG numeric，跨平台 repr 可能
    差異；%.12g 給足精度又消除尾差，進 digest 穩定（PA R-3 / T4）。
    """
    if x is None:
        return None
    return "%.12g" % float(x)


def _days_between(a: dt.datetime, b: dt.datetime) -> int:
    """(b - a) 的整日數（至少 0）。a/b tz-aware。"""
    if a.tzinfo is None:
        a = a.replace(tzinfo=dt.timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=dt.timezone.utc)
    delta = b - a
    return max(0, delta.days)


def build_universe(
    lifecycles: list,
    window: WindowSpec,
    *,
    run_id: str,
) -> tuple:
    """核心 builder（PA §4 Step D-H）。回 ``(rows, summary)``。

    rows：每 symbol 一個 dict（UNIVERSE_COLUMNS 全欄），含 included=false 的診斷行。
    summary：counts + delisted_proof_count + survivor_rejection_status + ...（PA §6）。

    為什麼 included=false 的行也保留：unknown_lifetime / lifetime_outside_window 是
    診斷證據（contract §3 step 7「diagnostics-only」），下游與審計需看見「為何排除」。
    """
    ws = window.window_start_utc
    we = window.window_end_utc

    # ── Step C: turnover rank（僅排序，不截斷）──
    # rank 依 turnover_24h 降序；turnover 缺（None）者 rank=None（不參與排序、不排除）。
    ranked = sorted(
        (lc for lc in lifecycles if lc.turnover_24h is not None),
        key=lambda lc: (-float(lc.turnover_24h), lc.symbol),
    )
    turnover_rank = {lc.symbol: i + 1 for i, lc in enumerate(ranked)}

    rows = []
    for lc in lifecycles:
        rows.append(_build_row(lc, window, run_id, turnover_rank.get(lc.symbol)))

    # row 固定排序（by symbol）— determinism 前置（digest + artifact 寫出皆依此序）。
    rows.sort(key=lambda r: r["symbol"])

    universe_id = compute_universe_id(rows, window)
    for r in rows:
        r["universe_id"] = universe_id

    summary = _build_summary(rows, window, run_id, universe_id)
    return rows, summary


def _build_row(
    lc: SymbolLifecycle,
    window: WindowSpec,
    run_id: str,
    turnover_rank: Optional[int],
) -> dict:
    """單 symbol → universe row（Step D-G）。"""
    ws = window.window_start_utc
    we = window.window_end_utc

    # ── Step D: lifetime 計算（PA 修正：lifecycle 欄優先，ts 僅診斷，絕不 coalesce）──
    listed_at = lc.listed_at
    delisted_at = lc.delisted_at
    # 兩權威欄全缺才 unknown_lifetime（NOT first_seen_ts，因 snapshot ts 只跨 27 天）。
    unknown_lifetime = (listed_at is None) and (delisted_at is None)

    # ── Step E: inclusion（lifetime ∩ window；含 delisted）──
    # 上市於窗結束前 AND delist 於窗開始後（含窗內 delisted）。缺 listed_at 用 ws、缺
    # delisted_at 用 we 作對稱保守邊界（NOT first/last_seen_ts）。
    eff_listed = listed_at if listed_at is not None else ws
    eff_delisted = delisted_at if delisted_at is not None else we
    intersects = (eff_listed <= we) and (eff_delisted >= ws)

    in_core25 = lc.symbol in CORE25_PINNED_SET
    in_scanner = bool(lc.in_scanner_window)
    status_class = classify_status(lc.status_raw)
    recommended_tier = classify_recommended_tier(
        lc.symbol, in_scanner_window=in_scanner, turnover_rank=turnover_rank,
    )
    cohort_ids = cohort_ids_for(
        lc.symbol, in_scanner_window=in_scanner, seen_delisted=lc.seen_delisted,
        turnover_rank=turnover_rank,
    )

    included = True
    inclusion_reason = None
    exclusion_reason = None
    alive_from = None
    alive_to = None
    alive_days = None

    if unknown_lifetime:
        # 兩權威欄全缺：診斷-only 排除（contract §3 step 7；除非 MIT 批准顯式規則）。
        # 不 coalesce 到 ts、不退回 current scanner（FND-2 §5 禁 fallback）。
        included = False
        exclusion_reason = "unknown_lifetime"
    elif not intersects:
        included = False
        exclusion_reason = "lifetime_outside_window"
    else:
        # ── Step F: effective lifetime（clip 到窗）──
        alive_from = max(eff_listed, ws)
        alive_to = min(eff_delisted, we)
        if alive_from > alive_to:
            included = False
            exclusion_reason = "lifetime_outside_window"
            alive_from = None
            alive_to = None
        else:
            alive_days = _days_between(alive_from, alive_to)
            # PreLaunch row = universe metadata（included 但非 scoring-ready；下游
            # coverage gate 才判 OHLCV）。其餘 included 標 lifetime_intersects_window。
            if status_class == "prelaunch":
                inclusion_reason = "prelaunch_metadata"
            else:
                inclusion_reason = "lifetime_intersects_window"

    return {
        "run_id": run_id,
        "universe_id": "",  # build_universe 末段回填
        "asof_utc": _iso(window.asof_utc),
        "exchange": window.exchange,
        "category": window.category,
        "symbol": lc.symbol,
        "status": lc.status_raw,
        "status_raw": lc.status_raw,
        "status_class": status_class,
        "recommended_tier": recommended_tier,
        "cohort_ids": list(cohort_ids),
        # 「僅當前 survivor」對照欄：標非 delisted 的當前在交易 symbol（這是欄位，
        # 不是 universe 過濾——full universe 必含 delisted）。
        "current_survivor_only_comparison": (not lc.seen_delisted) and (not lc.is_delisted_at_asof),
        "in_core25_pinned": in_core25,
        "in_scanner_window": in_scanner,
        "listed_at_utc": _iso(listed_at),
        "delisted_at_utc": _iso(delisted_at),
        "first_seen_ts_utc": _iso(lc.first_seen_ts),
        "last_seen_ts_utc": _iso(lc.last_seen_ts),
        "alive_from_utc": _iso(alive_from),
        "alive_to_utc": _iso(alive_to),
        "alive_days_in_window": alive_days,
        "unknown_lifetime": unknown_lifetime,
        "is_delisted_at_asof": bool(lc.is_delisted_at_asof),
        "seen_delisted": bool(lc.seen_delisted),
        "statuses_seen": list(lc.statuses_seen),
        "base_coin": lc.base_coin,
        "quote_coin": lc.quote_coin,
        "contract_type": lc.contract_type,
        "tick_size": _fmt_num(lc.tick_size),
        "qty_step": _fmt_num(lc.qty_step),
        "min_notional": _fmt_num(lc.min_notional),
        "source_uri": lc.source_uri,
        "source_snapshot_ts_utc": _iso(lc.source_snapshot_ts),
        "source_payload_hash": lc.source_payload_hash,
        "included": included,
        "inclusion_reason": inclusion_reason,
        "exclusion_reason": exclusion_reason,
    }


def _canonical_cell(value) -> str:
    """digest 用的 cell canonical 字串化（穩定、跨平台）。"""
    if value is None:
        return "\x00NULL"
    if isinstance(value, bool):
        return "T" if value else "F"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_canonical_cell(v) for v in value) + "]"
    return str(value)


def ordered_row_digest(rows: list) -> str:
    """canonical-sorted（by symbol）included+excluded 全 row 的穩定 digest（sha256 hex）。

    為什麼含 excluded row：universe_id 須對「完整 universe 判定」穩定，excluded 的
    診斷行也是判定的一部分（換實作把某 symbol 從 excluded 變 included 應改 digest）。
    為什麼用固定 _DIGEST_COLUMNS 子集：排除 run_id/universe_id（避免循環）與純展示欄。
    """
    h = hashlib.sha256()
    for r in sorted(rows, key=lambda x: x["symbol"]):
        for col in _DIGEST_COLUMNS:
            h.update(_canonical_cell(r.get(col)).encode("utf-8"))
            h.update(b"\x1f")  # 欄分隔
        h.update(b"\x1e")  # 行分隔
    return h.hexdigest()


def compute_universe_id(rows: list, window: WindowSpec) -> str:
    """deterministic universe_id（contract §4）。

    digest 輸入 = window_start || window_end || source_table || max(source_snapshot_ts)
    || QUERY_SCHEMA_VERSION || BUILDER_VERSION || ordered_row_digest。
    同 asof + 同 DB 狀態 → 同 universe_id（T4）。
    """
    max_snap = ""
    snaps = [r["source_snapshot_ts_utc"] for r in rows if r.get("source_snapshot_ts_utc")]
    if snaps:
        max_snap = max(snaps)
    parts = [
        _iso(window.window_start_utc) or "",
        _iso(window.window_end_utc) or "",
        "market.symbol_universe_snapshots",
        max_snap,
        QUERY_SCHEMA_VERSION,
        BUILDER_VERSION,
        ordered_row_digest(rows),
    ]
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()


def _build_summary(rows: list, window: WindowSpec, run_id: str, universe_id: str) -> dict:
    """summary dict（PA §6）含 survivor_rejection_status 機械化裁決。"""
    included = [r for r in rows if r["included"]]
    excluded = [r for r in rows if not r["included"]]

    counts_by_status: dict = {}
    counts_by_cohort: dict = {}
    counts_by_tier: dict = {}
    for r in included:
        counts_by_status[r["status_class"]] = counts_by_status.get(r["status_class"], 0) + 1
        counts_by_tier[r["recommended_tier"]] = counts_by_tier.get(r["recommended_tier"], 0) + 1
        for c in r["cohort_ids"]:
            counts_by_cohort[c] = counts_by_cohort.get(c, 0) + 1

    delisted_proof_count = sum(1 for r in included if r["seen_delisted"])
    unknown_lifetime_count = sum(1 for r in rows if r["unknown_lifetime"])

    survivor_rejection_status = _survivor_rejection_status(rows, included)

    snaps = [r["source_snapshot_ts_utc"] for r in rows if r.get("source_snapshot_ts_utc")]
    return {
        "run_id": run_id,
        "universe_id": universe_id,
        "window_start_utc": _iso(window.window_start_utc),
        "window_end_utc": _iso(window.window_end_utc),
        "asof_utc": _iso(window.asof_utc),
        "closed_bar_cutoff_utc": _iso(window.closed_bar_cutoff_utc),
        "source_snapshot_ts_min": (min(snaps) if snaps else None),
        "source_snapshot_ts_max": (max(snaps) if snaps else None),
        "counts_by_status": counts_by_status,
        "counts_by_cohort": counts_by_cohort,
        "counts_by_recommended_tier": counts_by_tier,
        "included_count": len(included),
        "excluded_count": len(excluded),
        "delisted_proof_count": delisted_proof_count,
        "unknown_lifetime_count": unknown_lifetime_count,
        "survivor_rejection_status": survivor_rejection_status,
        "builder_version": BUILDER_VERSION,
        "query_schema_version": QUERY_SCHEMA_VERSION,
    }


def _survivor_rejection_status(rows: list, included: list) -> str:
    """survivor-rejection gate（contract §5 核心，機械化）。

    回值：
      - ``PASS``：窗內存在 delisted-proof symbol（rows 有 seen_delisted=true）**且**
        included 集至少含一個 seen_delisted=true（universe 確實納入了 delisted）。
      - ``FAIL``：窗內存在 delisted-proof（任一 row seen_delisted=true）但 included
        集**全部** current-survivor（無 seen_delisted included）→ 這正是
        current-survivor-only 捷徑，必須 reject（contract §5「containing only
        current scanner/trading symbols fails」）。
      - ``PROVEN_NONE_IN_WINDOW``：rows 中根本無 seen_delisted=true（窗內無 delisted
        可證）→ 不算失敗，但須證明 none exist（contract §5「otherwise the run must
        prove none exist」）。

    為什麼用 included 集判 FAIL：contract §5 要求「if window contains closed/delisted
    symbols, at least one **included** row has seen_delisted=true」。若把窗內 delisted
    全排除（只留 current survivor included）就是 survivorship truncation regression。
    """
    any_delisted_in_window = any(r["seen_delisted"] for r in rows)
    included_has_delisted = any(r["seen_delisted"] for r in included)
    if not any_delisted_in_window:
        return "PROVEN_NONE_IN_WINDOW"
    return "PASS" if included_has_delisted else "FAIL"


__all__ = [
    "SymbolLifecycle",
    "WindowSpec",
    "UNIVERSE_COLUMNS",
    "build_universe",
    "compute_universe_id",
    "ordered_row_digest",
]
