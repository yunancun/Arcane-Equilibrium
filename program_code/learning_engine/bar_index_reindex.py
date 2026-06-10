"""bar_index_reindex — date→int bar index re-index（B1 int-bar-index 契約的 producer-side 對偶）。

MODULE_NOTE
模塊用途：
  L2 P3b owed ①（PA 2026-06-10 owed-conductor-wiring 設計 §D）。beta_neutral_check（B1）
  的入口契約要求 candidate/btc/altcap returns 與 down_mask 的 key MUST 是共享 int bar
  index（非 date/datetime/str；違反 → 顯式 DEFER temporal_keys_unsupported_need_int_bar_index）。
  本模組是該契約的官方 producer-side 轉換函數：把 date-key 的四組輸入統一 re-index 成
  共享 int bar index，供 conductor/adapter（l2_candidate_evidence_adapter）在餵 B1 前呼叫。

主要類/函數：
  - ReindexResult：dataclass（candidate/btc/altcap/mask 重 key 後輸出 + index_map 審計 +
    n_bars + reasons）。
  - reindex_to_int_bar_index(...)：入口（純函數，0 DB / 0 IO，synthetic 可測）。

依賴：僅 Python 標準庫（datetime / dataclasses / logging）。不 import beta_neutral_check /
  residual_alpha_gate 的私有 helper（避免跨模組私有依賴 drift；等價小函數自帶）。

硬邊界：
  - **int 賦值規則 = ordinal-day offset（默認）**：idx = d.toordinal() − d0.toordinal()。
    為什麼不是 dense 0..N-1：B1 的 _span_days 對 int key 用 max−min 直接當天數，而 down-leg
    的 ≥180d span 檢查語意是 calendar 跨度；序列有缺 bar（backfill 洞 / 稀疏期）時 dense 會把
    span 壓成 N−1 → 系統性低估真 calendar 跨度 → 無謂多 DEFER（犧牲真資料窗）。ordinal-offset
    保真 span；無缺 bar 時兩者完全相同（恰為 0..N-1）。dense 仍以 index_rule="dense" 提供
    （QC/PM 若堅持字面 0..N-1，adapter 端一行可切）。
  - **fail-loud（reasons + 全 None，非靜默）**：混型 key（int+temporal，含跨輸入）/ 同日重複
    key / 不可解析 key / bar≠"daily" / index_rule 未知 → 對應 reason + 全 None 結果 +
    logger.warning（帶型別/值，接線錯誤 log 即可診斷）。絕不靜默覆蓋重複日、絕不猜測壞 key。
  - mask 不參與交集（mask 是 BTC closes 全集的衍生，date 域 ⊇ btc returns 域）；交集內缺
    date → 該 bar False + reason mask_gap_filled_false:<n>（與 B1 mask.get(ts, False) 同
    保守語意，但顯式記帳）。
  - bar="4h" 顯式不支持（toordinal 取日會撞 key、span 換算 6x）；AEG-S3 是 daily 研究，
    4h 接入是未來另案 + 需重看 _span_days 語意。
  - 全輸入已是 int bar index → pass-through 原樣回（reason already_int_passthrough），
    不重編不變造（caller 已滿足 B1 契約）。
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Any, Hashable, Mapping

_LOG = logging.getLogger(__name__)

# index 賦值規則（§D.3）。ordinal_offset 為默認（span 保真）；dense 為對照備援。
INDEX_RULE_ORDINAL_OFFSET = "ordinal_offset"
INDEX_RULE_DENSE = "dense"
_SUPPORTED_INDEX_RULES = (INDEX_RULE_ORDINAL_OFFSET, INDEX_RULE_DENSE)

# bar 支持面：AEG-S3 = daily 研究；4h 顯式不支持（見 MODULE_NOTE 硬邊界）。
_SUPPORTED_BARS = ("daily",)

# key 分類結果（內部枚舉）。
_KIND_INT = "int"
_KIND_DATE = "date"
_KIND_BAD = "bad"


@dataclass(frozen=True)
class ReindexResult:
    """re-index 輸出。

    fail-loud 時 candidate/btc 為 None（reasons 記原因）；正常路徑四輸出 key 域 = 同一
    int 集合（altcap/mask 輸入為 None 時對應輸出 None，B1 自己 DEFER）。
    reasons 是記帳（informational + fail-loud 並存），非空不等於失敗——判斷失敗看
    candidate/btc 是否 None。
    """

    candidate: dict[int, float] | None
    btc: dict[int, float] | None
    altcap: dict[int, float] | None
    mask: dict[int, bool] | None
    index_map: dict[int, dt.date]  # 審計：int → 原 date（D3 可重建；passthrough/fail 時空）
    n_bars: int                    # 交集 bar 數（passthrough 時 = int key 交集大小）
    reasons: tuple[str, ...]


def reindex_to_int_bar_index(
    candidate_returns: Mapping[Hashable, float] | None,
    btc_returns: Mapping[Hashable, float] | None,
    altcap_returns: Mapping[Hashable, float] | None,
    down_market_mask: Mapping[Hashable, bool] | None,
    *,
    bar: str = "daily",
    index_rule: str = INDEX_RULE_ORDINAL_OFFSET,
) -> ReindexResult:
    """把 date/datetime/ISO-str key 的四組輸入統一 re-index 成共享 int bar index。

    對齊規則（PA §D.3）：
      1. 各輸入 key 正規化為 dt.date（datetime 取 .date()；ISO 字串容 Z/時區，語意同
         altcap_basket 的日期解析）。
      2. 共同 span = candidate ∩ btc ∩ altcap 的 date 交集（altcap=None 時 = candidate ∩ btc）。
         mask 不參與交集；在交集 date 上取值，缺 date → False + mask_gap_filled_false:<n>。
      3. int 賦值默認 ordinal-day offset：idx = d.toordinal() − d0.toordinal()（d0 = 交集
         最早 date）；index_rule="dense" 時為排序後 0..N-1（span 會低估，僅對照用）。
      4. 四輸出 key 域 = 同一 int 集合（B1 的 pooled 交集將是滿交集）。

    fail-loud（reasons + 全 None + logger.warning，非 raise——對齊 PA §D.2 與 adapter 的
    reason-flow 串接設計）：混型 / 重複日 / 不可解析 key / 不支持的 bar / 未知 index_rule。
    """
    # ── 入參邊界（fail-loud）──
    if bar not in _SUPPORTED_BARS:
        # 4h 的 bar-delta 規則顯式不在本輪（toordinal 取日會撞 key；見 MODULE_NOTE）。
        return _fail_loud(
            [f"bar_reindex_unsupported:{bar}"],
            "reindex_to_int_bar_index: bar=%r 不支持（僅 daily）",
            bar,
        )
    if index_rule not in _SUPPORTED_INDEX_RULES:
        # 未知規則絕不靜默 fallback（fallback 會無聲改變 span 語意）。
        return _fail_loud(
            [f"index_rule_unsupported:{index_rule}"],
            "reindex_to_int_bar_index: index_rule=%r 未知（僅 %s）",
            index_rule,
            _SUPPORTED_INDEX_RULES,
        )

    missing: list[str] = []
    if candidate_returns is None:
        missing.append("candidate_returns_missing")
    if btc_returns is None:
        missing.append("btc_returns_missing")
    if missing:
        # candidate/btc 是交集的必要成員，缺任一無從 re-index。
        return _fail_loud(missing, "reindex_to_int_bar_index: 必要輸入缺失 %s", missing)

    inputs: dict[str, Mapping[Hashable, Any] | None] = {
        "candidate_returns": candidate_returns,
        "btc_returns": btc_returns,
        "altcap_returns": altcap_returns,
        "down_market_mask": down_market_mask,
    }
    for label, series in inputs.items():
        if series is not None and not isinstance(series, Mapping):
            # 簽名契約是 Mapping；其他 shape（list/tuple）屬接線錯誤，顯式拒絕不猜測。
            return _fail_loud(
                ["unsupported_series_shape"],
                "reindex_to_int_bar_index: %s 非 Mapping（got %s）",
                label,
                type(series).__name__,
            )

    all_keys = [k for s in inputs.values() if s is not None for k in s.keys()]
    if not all_keys:
        # 全空輸入：無事可做，輸出空結構（B1 收空 series 自然 window DEFER）。
        return ReindexResult(
            candidate={},
            btc={},
            altcap={} if altcap_returns is not None else None,
            mask={} if down_market_mask is not None else None,
            index_map={},
            n_bars=0,
            reasons=("empty_inputs",),
        )

    # ── 已是 int bar index → pass-through（不重編不變造；B1 契約已滿足）──
    if all(_is_int_bar_index(k) for k in all_keys):
        common = set(candidate_returns) & set(btc_returns)
        if altcap_returns is not None:
            common &= set(altcap_returns)
        return ReindexResult(
            candidate=dict(candidate_returns),
            btc=dict(btc_returns),
            altcap=dict(altcap_returns) if altcap_returns is not None else None,
            mask=dict(down_market_mask) if down_market_mask is not None else None,
            index_map={},
            n_bars=len(common),
            reasons=("already_int_passthrough",),
        )

    # ── temporal 正規化（任一輸入 fail → 全 None；混型含「跨輸入」int+temporal）──
    reasons: list[str] = []
    normalized: dict[str, dict[dt.date, Any] | None] = {}
    failed = False
    for label, series in inputs.items():
        if series is None:
            normalized[label] = None
            continue
        norm = _normalize_series(series, label=label, reasons=reasons)
        normalized[label] = norm
        if norm is None:
            failed = True
    if failed:
        return _fail_loud(reasons, "reindex_to_int_bar_index: temporal key 正規化失敗 %s", reasons)

    cand_n = normalized["candidate_returns"]
    btc_n = normalized["btc_returns"]
    alt_n = normalized["altcap_returns"]
    mask_n = normalized["down_market_mask"]
    assert cand_n is not None and btc_n is not None  # 上面已擋 None / fail

    # informational 記帳（供 route notes / D3；非失敗信號——B1 對 None 自己 DEFER）。
    if altcap_returns is None:
        reasons.append("altcap_missing")
    if down_market_mask is None:
        reasons.append("mask_missing")

    # ── 交集（mask 不參與：mask date 域 ⊇ btc returns 域，參與會錯誤縮窗）──
    common_dates = set(cand_n) & set(btc_n)
    if alt_n is not None:
        common_dates &= set(alt_n)
    dates = sorted(common_dates)
    if not dates:
        reasons.append("empty_date_intersection")
        return ReindexResult(
            candidate={},
            btc={},
            altcap={} if alt_n is not None else None,
            mask={} if mask_n is not None else None,
            index_map={},
            n_bars=0,
            reasons=tuple(_dedupe(reasons)),
        )

    # ── int 賦值（§D.3 第 3 步；ordinal-offset 保真 calendar span，dense 僅對照）──
    d0 = dates[0]
    if index_rule == INDEX_RULE_ORDINAL_OFFSET:
        idx_of = {d: d.toordinal() - d0.toordinal() for d in dates}
    else:  # INDEX_RULE_DENSE
        idx_of = {d: i for i, d in enumerate(dates)}

    index_map = {idx_of[d]: d for d in dates}
    candidate_out = {idx_of[d]: cand_n[d] for d in dates}
    btc_out = {idx_of[d]: btc_n[d] for d in dates}
    altcap_out = {idx_of[d]: alt_n[d] for d in dates} if alt_n is not None else None

    mask_out: dict[int, bool] | None = None
    if mask_n is not None:
        # 交集內缺 date → False（與 B1 mask.get(ts, False) 同保守語意）+ 顯式記帳。
        mask_out = {}
        gap = 0
        for d in dates:
            if d in mask_n:
                mask_out[idx_of[d]] = bool(mask_n[d])
            else:
                mask_out[idx_of[d]] = False
                gap += 1
        if gap:
            reasons.append(f"mask_gap_filled_false:{gap}")

    return ReindexResult(
        candidate=candidate_out,
        btc=btc_out,
        altcap=altcap_out,
        mask=mask_out,
        index_map=index_map,
        n_bars=len(dates),
        reasons=tuple(_dedupe(reasons)),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 內部 helper（key 分類 / 正規化 / fail-loud / dedupe）
# ═══════════════════════════════════════════════════════════════════════════════


def _is_int_bar_index(key: Hashable) -> bool:
    """key 是否為合法 int bar index（與 beta_neutral_check._is_int_bar_index 同語意，自帶不跨 import）。

    為什麼排除 bool：bool 是 int 子類（isinstance(True, int) is True），但 True/False 當
    series key 是病態輸入，不算合法 bar index。
    """
    return isinstance(key, int) and not isinstance(key, bool)


def _parse_iso_date(value: str) -> dt.date | None:
    """ISO 字串 → date（容 Z / 時區與純 date；語意同 altcap_basket 的日期解析，自帶等價實作）。

    為什麼不跨模組 import altcap_basket._to_date：私有 helper 跨模組依賴會造成 drift 面；
    此函數 10 行，自帶成本低於耦合成本。無法解析 → None（交由 caller fail-loud，不偽造）。
    """
    s = value.strip()
    if not s:
        return None
    try:
        iso = s.replace("Z", "+00:00")
        return dt.datetime.fromisoformat(iso).date()
    except ValueError:
        try:
            return dt.date.fromisoformat(s[:10])
        except ValueError:
            return None


def _classify_key(key: Hashable) -> tuple[str, dt.date | None]:
    """key 分類：int bar index / temporal（轉成 date）/ bad（不可解析）。

    datetime 必須先於 date 判（datetime 是 date 子類）；bool 必須先於 int 判（bool 是
    int 子類，屬病態輸入歸 bad）。
    """
    if isinstance(key, bool):
        return (_KIND_BAD, None)
    if isinstance(key, int):
        return (_KIND_INT, None)
    if isinstance(key, dt.datetime):
        # daily bar：datetime 取當地 .date()（同 altcap 解析語意，不轉 UTC）。
        return (_KIND_DATE, key.date())
    if isinstance(key, dt.date):
        return (_KIND_DATE, key)
    if isinstance(key, str):
        d = _parse_iso_date(key)
        return (_KIND_DATE, d) if d is not None else (_KIND_BAD, None)
    return (_KIND_BAD, None)


def _normalize_series(
    series: Mapping[Hashable, Any],
    *,
    label: str,
    reasons: list[str],
) -> dict[dt.date, Any] | None:
    """單一輸入的 key 正規化為 dt.date。fail-loud 回 None（reason 已 append + warning 已記）。

    為什麼重複日 fail-loud 而非靜默取後者：dict 靜默覆蓋會無聲丟資料（datetime 同日兩筆 /
    str+date 同日並存都是上游資料 bug），對齊 B1「mixed 也違規」的契約精神——接線錯誤必須
    在 log 可診斷，不能靜默吞。
    """
    out: dict[dt.date, Any] = {}
    for key, value in series.items():
        kind, d = _classify_key(key)
        if kind == _KIND_INT:
            # 走到 temporal 路徑表示全集裡存在 temporal key；此處再見 int key = 混型
            # （單 series 內或跨輸入皆算）。混型對齊會靜默丟 row，必須 fail-loud。
            reasons.append("mixed_int_and_temporal_keys")
            _LOG.warning(
                "bar_index_reindex: %s 混型 key（int bar index 與 temporal key 並存；"
                "違規 key=%r）— 全輸入須同為 int 或同為 date/datetime/ISO-str。",
                label,
                key,
            )
            return None
        if kind == _KIND_BAD:
            reasons.append("unparseable_temporal_key")
            _LOG.warning(
                "bar_index_reindex: %s 含不可解析 key（type=%s key=%r）— "
                "僅容 date/datetime/ISO-str/int bar index。",
                label,
                type(key).__name__,
                key,
            )
            return None
        assert d is not None
        if d in out:
            # 同日重複（datetime 同日兩筆 / str+date 同日並存）→ 不靜默覆蓋。
            reasons.append("duplicate_date_after_normalize")
            _LOG.warning(
                "bar_index_reindex: %s 正規化後同日重複 key（date=%s 第二筆 key=%r）— "
                "上游資料含重複日，拒絕靜默覆蓋。",
                label,
                d.isoformat(),
                key,
            )
            return None
        out[d] = value
    return out


def _fail_loud(reasons: list[str], msg: str, *args: Any) -> ReindexResult:
    """fail-loud 結果（全 None + reasons + logger.warning）。

    為什麼全 None 而非 raise：caller（l2_candidate_evidence_adapter）走 reason-flow 串接
    （缺值=None → B1 誠實 DEFER），exception-flow 會迫使每個 caller 包 try/except 且容易
    被 fail-soft 外殼吞掉變回靜默；None + reason + warning 同時滿足 fail-loud 與可組合性。
    """
    _LOG.warning(msg, *args)
    return ReindexResult(
        candidate=None,
        btc=None,
        altcap=None,
        mask=None,
        index_map={},
        n_bars=0,
        reasons=tuple(_dedupe(reasons)),
    )


def _dedupe(reasons: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for r in reasons:
        if r in seen:
            continue
        seen.add(r)
        out.append(r)
    return out


__all__ = [
    "INDEX_RULE_DENSE",
    "INDEX_RULE_ORDINAL_OFFSET",
    "ReindexResult",
    "reindex_to_int_bar_index",
]
