"""altcap_basket — equal-weight ex-BTC CORE25 籃子報酬（B1 第二因子，on-the-fly）。

MODULE_NOTE
模塊用途：
  L2 Phase 3b B1 的 altcap 因子 producer（PA P3b 設計 §B + QC B1 spec §2）。產出 ex-BTC
  CORE25 的「每日等權」籃子報酬序列，餵 beta_neutral_check 的第二因子（雙因子模型的
  r_altcap 臂）。equal-weight（operator 鎖）：cap data 不存在（0 hits market_cap/
  circulating_supply over srv），且 funding-tilt PCA PC1 ~69% ⇒ 籃子被共同 alt move 主導，
  weighting 是二階（equal/cap/volume ~0.95+ corr）；0 free param。

  ★ PIT 紀律（MIT M3 review 的「唯一」熱點）：bar t 的成員 = FND-2 alive_from/alive_to
    walk-forward 在 t 時的 alive set，NOT 今日 survivors，NOT zombie forward-fill 已下市
    symbol 的最後價。新上市在 alive_from 進籃、下市在 alive_to 後離籃。

主要類/函數：
  - AltcapReturnSeries：dataclass（returns / constituents_by_day / n_constituents_by_day /
    reasons）。
  - build_altcap_returns(...)：純函數核心（input FND-2 rows + daily closes，0 DB）。
  - load_fnd2_universe_rows(...)：薄 read-only loader（FND-2 data_loader → builder，唯讀）。

依賴：
  - fnd2_pit_universe.cohorts.CORE25_PINNED（24 = CORE25 減 BTCUSDT）。
  - fnd2_pit_universe.builder.UNIVERSE_COLUMNS（alive_from_utc / alive_to_utc 欄）。
  - 純函數核心僅標準庫；loader 才碰 FND-2 data_loader（唯讀 SELECT）。

硬邊界：
  - leak-free-by-construction：成員 walk-forward（alive_from ≤ bar ≤ alive_to），無 today's-
    survivors 捷徑、無 delisted forward-fill。
  - producer 不可建（無成員 alive / 價缺）→ 回空 returns ⇒ B1 見 altcap=None-等價 → DEFER
    （fail-closed by construction）。
  - on-the-fly：deterministic function of (FND-2 membership + daily closes)；無持久表、無 V138。
  - read-only：0 寫入、0 order path。
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

# CORE25 凍結成員（24 = 減 BTCUSDT）；alive_from/alive_to 欄名來自 FND-2 builder。
from helper_scripts.research.fnd2_pit_universe.cohorts import CORE25_PINNED

# ex-BTC（QC §2：ex-BTC，ex-stablecoin 已由 FND-2 USDT-perp scope 排除）。
_BTC_SYMBOL = "BTCUSDT"
# launch scope = CORE25 ex-BTC = 24 survivorship-vetted symbol（QC §2；post-launch 再擴 full FND-2）。
CORE25_EX_BTC: tuple[str, ...] = tuple(s for s in CORE25_PINNED if s != _BTC_SYMBOL)


@dataclass
class AltcapReturnSeries:
    """altcap 籃子報酬序列 + PIT 成員審計。

    returns 空 ⇒ producer 不可建（B1 見 altcap=None-等價 → DEFER）。constituents_by_day 是
    PIT proof（每 bar 誰 alive），供 MIT M3 review 與 audit。
    """

    returns: dict[Any, float]                       # {date: r_altcap_t}（PIT-alive 成員等權均值）
    constituents_by_day: dict[Any, list[str]]       # {date: [alive symbol]}（PIT proof）
    n_constituents_by_day: dict[Any, int]
    reasons: list[str] = field(default_factory=list)  # e.g. day_skipped_no_constituents

    def to_dict(self) -> dict[str, Any]:
        return {
            "returns": {_iso(k): v for k, v in self.returns.items()},
            "constituents_by_day": {_iso(k): v for k, v in self.constituents_by_day.items()},
            "n_constituents_by_day": {_iso(k): v for k, v in self.n_constituents_by_day.items()},
            "reasons": list(self.reasons),
        }


def build_altcap_returns(
    fnd2_universe_rows: Sequence[Mapping[str, Any]],
    daily_closes: Mapping[str, Mapping[Any, float]],
    *,
    window_start: Any,
    window_end: Any,
    ex_symbols: tuple[str, ...] = (_BTC_SYMBOL,),
    universe_scope: Optional[Sequence[str]] = None,
) -> AltcapReturnSeries:
    """從 FND-2 membership + daily closes 算 equal-weight ex-BTC 籃子報酬（PIT walk-forward）。

    參數：
      - fnd2_universe_rows：FND-2 build_universe() rows（含 alive_from_utc / alive_to_utc /
        symbol / included）OR loaded universe.csv 行。只取 included=True 的行。
      - daily_closes：{symbol: {date: close}}（market.klines 1d，read-only）。
      - window_start / window_end：date（分析窗；籃子報酬只在窗內算）。
      - ex_symbols：排除集（預設 ("BTCUSDT",)；ex-stablecoin 已由 FND-2 USDT-perp scope 排除）。
      - universe_scope：限定 universe（預設 None = CORE25 ex-BTC 24 檔；post-launch 可給 full
        FND-2 included set）。

    回 AltcapReturnSeries。r_altcap_t = mean over PIT-alive constituents of
    (close_s,t / close_s,{t-1} − 1)，daily equal-weight（每 alive constituent 權重 1/N_t）。
    無成員 alive 或價缺 → 該 bar skip（reasons 記）；全 skip → returns 空（B1 DEFER）。
    """
    scope = set(universe_scope) if universe_scope is not None else set(CORE25_EX_BTC)
    ex = set(ex_symbols)
    # ── 取 PIT lifetime（alive_from / alive_to）：只取 included=True 且在 scope、非 ex 的行 ──
    lifetimes = _extract_lifetimes(fnd2_universe_rows, scope=scope, ex=ex)

    returns: dict[Any, float] = {}
    constituents_by_day: dict[Any, list[str]] = {}
    n_by_day: dict[Any, int] = {}
    reasons: list[str] = []

    # ── 交易日軸：用 scope 內 symbol 的 daily_closes 日期聯集，限在 [window_start, window_end] ──
    all_dates = _sorted_dates_in_window(daily_closes, scope, ex, window_start, window_end)
    if len(all_dates) < 2:
        reasons.append("insufficient_dates_in_window")
        return AltcapReturnSeries(returns={}, constituents_by_day={}, n_constituents_by_day={}, reasons=reasons)

    prev_date = all_dates[0]
    for d in all_dates[1:]:
        # bar t 的 PIT-alive 成員（alive_from ≤ d ≤ alive_to；walk-forward，非今日 survivor）。
        alive = [
            sym for sym in scope
            if sym not in ex and _is_alive(lifetimes.get(sym), d)
        ]
        per_symbol_rets: list[float] = []
        used_symbols: list[str] = []
        for sym in alive:
            closes = daily_closes.get(sym)
            if not closes:
                continue
            c_t = closes.get(d)
            c_prev = closes.get(prev_date)
            # 兩日皆有「真」close 才計入（無 zombie forward-fill 已下市 symbol 的最後價）。
            if c_t is None or c_prev is None:
                continue
            if c_prev is None or abs(float(c_prev)) < 1e-12:
                continue
            per_symbol_rets.append(float(c_t) / float(c_prev) - 1.0)
            used_symbols.append(sym)
        if per_symbol_rets:
            # equal-weight：每 alive-且-有價 constituent 權重 1/N（N = len(used_symbols)）。
            returns[d] = sum(per_symbol_rets) / float(len(per_symbol_rets))
            constituents_by_day[d] = sorted(used_symbols)
            n_by_day[d] = len(used_symbols)
        else:
            reasons.append("day_skipped_no_constituents")
        prev_date = d

    return AltcapReturnSeries(
        returns=returns,
        constituents_by_day=constituents_by_day,
        n_constituents_by_day=n_by_day,
        reasons=_dedupe(reasons),
    )


def load_fnd2_universe_rows(
    window_start: dt.datetime,
    window_end: dt.datetime,
    asof: dt.datetime,
    closed_bar_cutoff: dt.datetime,
    *,
    run_id: str = "altcap_basket",
    dsn: Optional[str] = None,
) -> list[dict[str, Any]]:
    """唯讀載入 FND-2 universe rows（data_loader → builder）。回 build_universe() 的 rows。

    為什麼薄 wrap：altcap producer 偏好 in-memory recompute（leak-free per run）。此 helper
    走 FND-2 既有唯讀路徑（data_loader.load_lifecycles set_session readonly fail-closed →
    builder.build_universe 純函數），不複製 FND-2 的 lifecycle SQL。

    注意：本函式碰 DB（FND-2 唯讀 SELECT）；純函數核心 build_altcap_returns 不碰 DB（可
    synthetic 測）。Linux smoke（24 symbol × window 真 market.klines）owed-runtime。
    """
    from helper_scripts.research.fnd2_pit_universe.builder import WindowSpec, build_universe
    from helper_scripts.research.fnd2_pit_universe.data_loader import load_lifecycles

    window = WindowSpec(
        window_start_utc=window_start,
        window_end_utc=window_end,
        asof_utc=asof,
        closed_bar_cutoff_utc=closed_bar_cutoff,
    )
    lifecycles = load_lifecycles(window, dsn=dsn)
    rows, _summary = build_universe(lifecycles, window, run_id=run_id)
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# 內部 helper（PIT lifetime 抽取 / alive 判定 / 日期軸 / 解析）
# ═══════════════════════════════════════════════════════════════════════════════


def _extract_lifetimes(
    rows: Sequence[Mapping[str, Any]], *, scope: set[str], ex: set[str]
) -> dict[str, tuple[Optional[dt.date], Optional[dt.date]]]:
    """從 FND-2 rows 取 {symbol: (alive_from_date, alive_to_date)}。只取 included=True 的行。

    為什麼只取 included=True：excluded 行（unknown_lifetime / lifetime_outside_window）是
    診斷行，alive_from/alive_to 為 None；不該進籃。alive_from/alive_to 是 FND-2 walk-forward
    的 PIT lifetime 權威（builder Step F：clip 到窗的 effective lifetime）。
    """
    out: dict[str, tuple[Optional[dt.date], Optional[dt.date]]] = {}
    for row in rows:
        sym = str(row.get("symbol", ""))
        if not sym or sym in ex or sym not in scope:
            continue
        if not bool(row.get("included", False)):
            continue
        af = _to_date(row.get("alive_from_utc"))
        at = _to_date(row.get("alive_to_utc"))
        if af is None or at is None:
            # included 但 alive_from/alive_to 缺（不該發生於 included 行）→ 保守跳過（不偽造邊界）。
            continue
        out[sym] = (af, at)
    return out


def _is_alive(
    lifetime: Optional[tuple[Optional[dt.date], Optional[dt.date]]], d: Any
) -> bool:
    """bar d 是否落在 PIT lifetime [alive_from, alive_to]（含端點）。

    為什麼含端點：alive_from 是進籃日、alive_to 是最後在籃日（FND-2 Step F 的 effective
    lifetime clip）。lifetime 缺 → 非 alive（fail-closed，無今日 survivor 捷徑）。
    """
    if lifetime is None:
        return False
    af, at = lifetime
    if af is None or at is None:
        return False
    dd = _to_date(d)
    if dd is None:
        return False
    return af <= dd <= at


def _sorted_dates_in_window(
    daily_closes: Mapping[str, Mapping[Any, float]],
    scope: set[str],
    ex: set[str],
    window_start: Any,
    window_end: Any,
) -> list[Any]:
    """scope 內 symbol 的 daily_closes 日期聯集，限在 [window_start, window_end]，升序去重。

    為什麼用聯集而非單一 symbol 的軸：不同 symbol 上下市日不同；交易日軸取所有 in-scope
    symbol 出現過的日期，確保每個 bar 都評估全體 PIT-alive 成員。
    """
    ws = _to_date(window_start)
    we = _to_date(window_end)
    seen: set[Any] = set()
    for sym, closes in daily_closes.items():
        if sym in ex or sym not in scope:
            continue
        for d in closes:
            dd = _to_date(d)
            if dd is None:
                continue
            if ws is not None and dd < ws:
                continue
            if we is not None and dd > we:
                continue
            seen.add(d)
    return sorted(seen, key=_date_sort_key)


def _date_sort_key(d: Any) -> tuple[int, Any]:
    """日期升序 key（date/datetime → ordinal；其餘 → 字串）。確定性、跨型別不 raise。"""
    dd = _to_date(d)
    if dd is not None:
        return (0, dd.toordinal())
    return (1, str(d))


def _to_date(value: Any) -> Optional[dt.date]:
    """把 date / datetime / ISO 字串 → date。無法解析 → None（不偽造）。"""
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            # 容 ISO datetime（含 Z / 時區）與純 date。
            iso = s.replace("Z", "+00:00")
            return dt.datetime.fromisoformat(iso).date()
        except ValueError:
            try:
                return dt.date.fromisoformat(s[:10])
            except ValueError:
                return None
    return None


def _iso(value: Any) -> str:
    """date/datetime → ISO 字串（dict key 序列化用）；其餘 → str。"""
    isofmt = getattr(value, "isoformat", None)
    if callable(isofmt):
        return str(isofmt())
    return str(value)


def _dedupe(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it in seen:
            continue
        seen.add(it)
        out.append(it)
    return out


__all__ = [
    "CORE25_EX_BTC",
    "AltcapReturnSeries",
    "build_altcap_returns",
    "load_fnd2_universe_rows",
]
