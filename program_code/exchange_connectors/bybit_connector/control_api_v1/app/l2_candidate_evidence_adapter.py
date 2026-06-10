"""l2_candidate_evidence_adapter — AEG candidate evidence v1 → math_gate_inputs 轉換層。

MODULE_NOTE
模塊用途：
  L2 P3b owed ③（PA 設計 2026-06-10 §B）：把 AEG-S3 候選的 evidence 契約 v1
  （aeg_candidate_evidence.v1，inline JSON）轉成 l2_ml_advisory_executor._run_math_gate
  消費的 context = {"candidate_returns", "math_gate_inputs"{...}}。兩層分離：
    (1) 純函數層 build_math_gate_context（0 DB / 0 IO；單測主體）。
    (2) 唯讀 DB 層 load_factor_bundle（market.klines BTC 1d + altcap producer + down-mask；
        Linux smoke 對象）。
  route（layer2_routes /ml-advisory/dispatch）經 build_context_from_evidence 組合兩層。

主要類/函數：
  - FactorBundle：因子資料載體（btc_returns / altcap_returns / down_market_mask / reasons）。
  - build_math_gate_context(evidence, *, factors)：純函數映射（缺值=None，誠實 DEFER）。
  - load_factor_bundle(...)：唯讀載入因子（任何子載入失敗 → 對應欄 None + reason，fail-soft）。
  - build_context_from_evidence(...)：route 入口（derive window → load factors → 純函數）。

依賴（全部 lazy import，模組本體 0 跨 package import）：
  - db_pool.get_pg_conn（唯讀 SELECT market.klines；可注入 conn_provider）。
  - program_code.research.altcap_basket（producer 已 ship，零改動 reuse）。
  - program_code.learning_engine.beta_neutral_check.compute_down_market_mask（零改動 reuse）。
  - program_code.learning_engine.bar_index_reindex.reindex_to_int_bar_index（E1-A 介面凍結
    per PA §D.2；模組未落地時 fail-soft 留 temporal key → B1 入口 fail-loud 顯式 DEFER）。

硬邊界：
  - ★ 捏造禁令（E2 grep target）：mean_daily_bps / net_bps 兩個標量欄名「只允許」出現在
    本段禁令註釋——本模塊**不存在任何標量→序列合成路徑**。理由（PA §0 F2）：用標量合成
    常數報酬序列，對因子 OLS 必得 β≈0 → B1 偽 pass → 直接放行 down-beta 偽裝（重開殺 5
    候選的失敗模式），比誠實 DEFER 危險一個量級。缺 daily_returns ⇒ candidate_returns=None
    ⇒ B1 stage DEFER（executor b1_inputs_missing_defer）。
  - regime row 選擇（防 selection bias，QC 軸）：selected_regime 顯式給才用；缺省且恰一行
    才用；多行無顯式指定 → 全標量 None + reason regime_ambiguous_no_selection。本模塊
    **絕不**自動挑 best-Sharpe row（自動挑 = cherry-pick = selection bias 進 gate 輸入）。
  - M3 typing：leak flag 只在 producer 自報 source_class 與欄位名一致時採信
    （report 自稱 leak-free 不算）；否則 None（leak stage DEFER）。
  - 唯讀：0 寫入、0 order path、0 新 singleton（純函數 + 注入式依賴）。
"""

from __future__ import annotations

import datetime as dt
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from . import db_pool

logger = logging.getLogger("l2_candidate_evidence_adapter")

# evidence 契約版本（route 收的 inline JSON；PA §B.2）。
EVIDENCE_SCHEMA_V1 = "aeg_candidate_evidence.v1"

# return_unit 合法值：fraction（原樣）/ bps（÷1e4 正規化）。未知 unit → None（不猜）。
_RETURN_UNIT_FRACTION = "fraction"
_RETURN_UNIT_BPS = "bps"

# BTC closes 的回看緩衝（天）：down-mask 的 prior-30-bar 窗 + 首日報酬的 t-1 需要窗前資料；
# crypto 無休市日，45 個 calendar day 足覆 30 bar lookback。
_MASK_LOOKBACK_BUFFER_DAYS = 45

# BTC 因子 symbol（market.klines 1d）。
_BTC_SYMBOL = "BTCUSDT"


# ═══════════════════════════════════════════════════════════════════════════════
# FactorBundle（DB 層輸出；date-key，最終由 reindex 統一轉 int bar index）
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class FactorBundle:
    """因子資料載體（PA §B.1）。任一欄 None = 該因子不可得（B1 自己 DEFER，不偽造）。"""

    btc_returns: dict[Any, float] | None  # market.klines BTCUSDT 1d → daily return（date key）
    altcap_returns: dict[Any, float] | None  # altcap producer returns（date key；空 → None）
    down_market_mask: dict[Any, bool] | None  # compute_down_market_mask（date key）
    reasons: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# 純函數層（0 DB 0 IO）——evidence 契約 v1 → math gate context 映射
# ═══════════════════════════════════════════════════════════════════════════════


def _none_context() -> dict[str, Any]:
    """全 None 的 math gate context（每缺一鍵 = 對應 stage 誠實 DEFER；bar 固定 daily）。"""
    return {
        "candidate_returns": None,
        "math_gate_inputs": {
            "n_trades_oos": None,
            "observed_sharpe": None,
            "n_trials": None,
            "cpcv_oos_returns_per_split": None,
            "btc_returns": None,
            "altcap_returns": None,
            "down_market_mask": None,
            "bar": "daily",  # AEG-S3 = daily 研究（PA §B.3；4h 不在本輪）
            "shift1_compliance_leak_free": None,
            "is_oos_gap_leak_free": None,
        },
    }


def build_math_gate_context(
    evidence: dict[str, Any], *, factors: FactorBundle | None
) -> tuple[dict[str, Any], list[str]]:
    """evidence 契約 v1 → math gate context（PA §B.3 映射表的唯一權威實作）。

    回 (context, reasons)。缺值一律 None（誠實 DEFER），reasons 記每個缺口供 route notes / D3。
    最後一步呼 E1-A 的 reindex_to_int_bar_index 把 candidate/btc/altcap/mask 統一轉 int bar
    index（滿足 beta_neutral_check 的 fail-loud int-bar-index 契約）。

    為什麼缺值不補、不估、不合成：math gate 的 DEFER 語義就是「證據不足」，補值＝偽造證據
    強度（見 MODULE_NOTE 捏造禁令）。
    """
    reasons: list[str] = []
    ctx = _none_context()
    gi = ctx["math_gate_inputs"]

    if not isinstance(evidence, Mapping):
        reasons.append("evidence_not_mapping")
        return ctx, reasons

    schema = str(evidence.get("evidence_schema", ""))
    if schema != EVIDENCE_SCHEMA_V1:
        # 未知 schema → 不信任任何欄（fail-closed：全 None = math gate 全 DEFER）。
        reasons.append(f"evidence_schema_unsupported:{schema or 'absent'}")
        return ctx, reasons

    # ── regime row 選擇（防 cherry-pick；見 MODULE_NOTE 硬邊界）──
    row, row_reasons = _select_regime_row(evidence)
    reasons.extend(row_reasons)
    if row is not None:
        # n_trades_oos ← n_independent（cluster-adjusted N；builder 註解明禁 n_days 冒充）。
        gi["n_trades_oos"] = _int_or_none(row.get("n_independent"))
        if gi["n_trades_oos"] is None:
            reasons.append("n_independent_missing_q1_defer")
        # observed_sharpe ← oos_sharpe（OOS 觀測 sharpe 才是 DSR deflation 的正確輸入；
        # 非 in-sample annualized_net_sharpe）。
        gi["observed_sharpe"] = _float_or_none(row.get("oos_sharpe"))
        if gi["observed_sharpe"] is None:
            reasons.append("oos_sharpe_missing_dsr_defer")
        # n_trials ← k_trials（multiple-testing K）。
        gi["n_trials"] = _int_or_none(row.get("k_trials"))
        if gi["n_trials"] is None:
            reasons.append("k_trials_missing_dsr_defer")

    # ── cpcv（可選；單配置 → None → PBO honest-DEFER，不捏造 peer）──
    cpcv = evidence.get("cpcv_oos_returns_per_split")
    if cpcv is None:
        gi["cpcv_oos_returns_per_split"] = None
        reasons.append("cpcv_absent_pbo_honest_defer")
    elif isinstance(cpcv, (list, tuple)):
        gi["cpcv_oos_returns_per_split"] = list(cpcv)
    else:
        gi["cpcv_oos_returns_per_split"] = None
        reasons.append("cpcv_malformed_pbo_honest_defer")

    # ── candidate daily returns（缺 → None → B1 DEFER；嚴禁標量合成）──
    candidate, cand_reasons = _normalize_daily_returns(
        evidence.get("daily_returns"), evidence.get("return_unit")
    )
    reasons.extend(cand_reasons)

    # ── leak producers（M3 typing：source_class 必須與欄位名一致才採信）──
    leak = evidence.get("leak_producers")
    leak_map = leak if isinstance(leak, Mapping) else {}
    gi["shift1_compliance_leak_free"] = _extract_leak_flag(
        leak_map, "shift1_compliance", reasons
    )
    gi["is_oos_gap_leak_free"] = _extract_leak_flag(leak_map, "is_oos_gap", reasons)

    # ── 因子（FactorBundle；非 evidence——因子由本系統唯讀載入，候選不得自報因子）──
    btc = altcap = mask = None
    if factors is None:
        reasons.append("factor_bundle_missing_b1_defer")
    else:
        reasons.extend(factors.reasons)
        btc = factors.btc_returns
        altcap = factors.altcap_returns
        mask = factors.down_market_mask

    # ── 最後一步：統一 int bar index（E1-A reindex；B1 fail-loud 契約）──
    candidate, btc, altcap, mask = _reindex_all(candidate, btc, altcap, mask, reasons)
    ctx["candidate_returns"] = candidate
    gi["btc_returns"] = btc
    gi["altcap_returns"] = altcap
    gi["down_market_mask"] = mask

    return ctx, reasons


def _select_regime_row(
    evidence: Mapping[str, Any]
) -> tuple[Mapping[str, Any] | None, list[str]]:
    """regime row 選擇規則（PA §B.3）：顯式 selected_regime → 用之；缺省且恰一行 → 用之；
    多行無顯式 → None + regime_ambiguous_no_selection（絕不自動挑 best-Sharpe = cherry-pick）。
    """
    rows = evidence.get("regime_rows")
    if not isinstance(rows, (list, tuple)) or not rows:
        return None, ["regime_rows_missing"]
    valid = [r for r in rows if isinstance(r, Mapping)]
    if not valid:
        return None, ["regime_rows_missing"]
    selected = evidence.get("selected_regime")
    if selected is not None and str(selected).strip():
        sel = str(selected).strip()
        for r in valid:
            if str(r.get("regime", "")) == sel:
                return r, []
        # 顯式指定但 rows 裡沒有 → 不退而求其次（fail-closed：標量全缺 → DEFER）。
        return None, [f"selected_regime_not_in_rows:{sel}"]
    if len(valid) == 1:
        return valid[0], []
    # 多行且無顯式指定 → DEFER（selection-bias 閘）。
    return None, ["regime_ambiguous_no_selection"]


def _normalize_daily_returns(
    raw: Any, return_unit: Any
) -> tuple[dict[Any, float] | None, list[str]]:
    """daily_returns 正規化：fraction 原樣 / bps ÷1e4；key 原樣保留（reindex 統一轉 int）。

    fail-loud（非部分靜默丟）：任一 value 非有限數值 → 整條 None + reason。理由：部分丟 row
    正是 beta_neutral_check 2026-06-10 修補的「靜默丟 row → 假結論」反模式；序列不可信就整條
    DEFER，不給「殘缺但看似可用」的序列。
    """
    if raw is None:
        return None, ["daily_returns_missing_b1_defer"]
    if not isinstance(raw, Mapping) or not raw:
        return None, ["daily_returns_malformed_b1_defer"]
    unit = str(return_unit).strip() if return_unit is not None else _RETURN_UNIT_FRACTION
    if unit not in (_RETURN_UNIT_FRACTION, _RETURN_UNIT_BPS):
        return None, [f"return_unit_unknown:{unit}"]
    scale = 1e-4 if unit == _RETURN_UNIT_BPS else 1.0
    out: dict[Any, float] = {}
    for k, v in raw.items():
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None, ["daily_returns_unparseable_b1_defer"]
        if not math.isfinite(f):
            return None, ["daily_returns_unparseable_b1_defer"]
        out[k] = f * scale
    return out, []


def _extract_leak_flag(
    leak_map: Mapping[str, Any], producer_key: str, reasons: list[str]
) -> bool | None:
    """取 leak producer 的 leak_free（bool|None）。M3 typing：僅當該 entry 自報
    source_class == producer_key 才採信（report 自稱 leak-free 不算 producer 證據）。
    """
    entry = leak_map.get(producer_key)
    if not isinstance(entry, Mapping):
        reasons.append(f"leak_producer_absent:{producer_key}")
        return None
    if str(entry.get("source_class", "")) != producer_key:
        reasons.append(f"leak_producer_source_class_mismatch:{producer_key}")
        return None
    flag = entry.get("leak_free")
    if isinstance(flag, bool):
        return flag
    reasons.append(f"leak_producer_flag_not_bool:{producer_key}")
    return None


def _int_or_none(v: Any) -> int | None:
    try:
        if v is None or isinstance(v, bool):
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def _float_or_none(v: Any) -> float | None:
    try:
        if v is None or isinstance(v, bool):
            return None
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _resolve_reindex() -> Callable[..., Any] | None:
    """取 E1-A bar_index_reindex.reindex_to_int_bar_index（介面凍結 per PA §D.2）。

    模組未落地（E1-A 並行中）→ None：series 保持 temporal key 傳下去，beta_neutral_check
    入口會 fail-loud 顯式 DEFER（temporal_keys_unsupported_need_int_bar_index）——誠實可
    診斷，非靜默壞掉。
    """
    try:
        from program_code.learning_engine.bar_index_reindex import (  # noqa: PLC0415
            reindex_to_int_bar_index,
        )

        return reindex_to_int_bar_index
    except ImportError:
        try:
            from learning_engine.bar_index_reindex import (  # type: ignore  # noqa: PLC0415
                reindex_to_int_bar_index,
            )

            return reindex_to_int_bar_index
        except ImportError:
            return None


def _reindex_all(
    candidate: dict[Any, float] | None,
    btc: dict[Any, float] | None,
    altcap: dict[Any, float] | None,
    mask: dict[Any, bool] | None,
    reasons: list[str],
) -> tuple[Any, Any, Any, Any]:
    """四 series 統一轉 int bar index（E1-A reindex_to_int_bar_index）。

    reindex 不可得 → 保留 temporal key + reason（B1 入口 fail-loud DEFER）。reindex 例外 →
    全 None + reason（fail-soft：wiring 例外不可冒進 route/dispatch；全 None = 誠實 DEFER）。
    """
    if candidate is None and btc is None and altcap is None and mask is None:
        return None, None, None, None
    if candidate is None:
        # E2 LOW-1：evidence 無 daily_returns（AEG-S3 標量輸出的常態）而因子載入成功時，
        # 進 reindex 必觸 candidate_returns_missing fail-loud → 因子連帶全 None + 每次
        # warning（常態當異常記）。B1 對 candidate=None 本就 DEFER（b1_inputs_missing_defer），
        # 短路語義等價且不再噪音；因子保留原樣（candidate 缺與因子可得性無關）。
        reasons.append("candidate_returns_missing_reindex_skipped")
        return None, btc, altcap, mask
    reindex = _resolve_reindex()
    if reindex is None:
        reasons.append("bar_index_reindex_unavailable_temporal_keys_left")
        return candidate, btc, altcap, mask
    try:
        rr = reindex(candidate, btc, altcap, mask, bar="daily")
        rr_reasons = getattr(rr, "reasons", None) or []
        reasons.extend(str(r) for r in rr_reasons)
        return rr.candidate, rr.btc, rr.altcap, rr.mask
    except Exception as exc:  # noqa: BLE001 — wiring 例外 fail-soft（全 None = 誠實 DEFER）
        logger.warning("bar_index_reindex 失敗（fail-soft → 全 None）：%s", exc)
        reasons.append("bar_index_reindex_error_all_none")
        return None, None, None, None


# ═══════════════════════════════════════════════════════════════════════════════
# DB 層（read-only SELECT；fail-soft——任何子載入失敗 → 對應欄 None + reason）
# ═══════════════════════════════════════════════════════════════════════════════


def load_factor_bundle(
    window_start: Any,
    window_end: Any,
    *,
    dsn: str | None = None,
    conn_provider: Any = None,
    fnd2_rows_loader: Callable[..., list[dict[str, Any]]] | None = None,
) -> FactorBundle:
    """唯讀載入因子資料（PA §B.1）：BTC 1d returns + altcap producer returns + down-mask。

    參數：
      - window_start / window_end：date / datetime / ISO 字串（分析窗）。
      - dsn：FND-2 universe loader 的顯式 DSN（其原生參數；None = 該 loader 預設）。
      - conn_provider：market.klines 連線注入（測試隔離鐵則：loader 測試注入 fake conn）；
        None = db_pool.get_pg_conn。
      - fnd2_rows_loader：FND-2 rows 載入注入（測試隔離）；None = altcap_basket.
        load_fnd2_universe_rows。

    fail-soft：任何子載入失敗 → 對應欄 None + reason（B1 自己 DEFER）；本函數不 raise。
    """
    reasons: list[str] = []
    ws = _to_date(window_start)
    we = _to_date(window_end)
    if ws is None or we is None or ws > we:
        return FactorBundle(
            btc_returns=None, altcap_returns=None, down_market_mask=None,
            reasons=["factor_window_unparseable"],
        )

    # ── 1) klines closes（BTC + CORE25 ex-BTC，一次唯讀 SELECT）──
    symbols = _factor_symbols(reasons)
    closes_by_symbol = _load_daily_closes(
        symbols,
        ws - dt.timedelta(days=_MASK_LOOKBACK_BUFFER_DAYS),
        we,
        conn_provider=conn_provider,
        reasons=reasons,
    )

    # ── 2) BTC returns + down-mask（皆從 BTC closes 衍生）──
    # 裁窗語意（QC B1 wiring 帶 2026-06-10）：closes 含 _MASK_LOOKBACK_BUFFER_DAYS 窗前
    # buffer——mask 的 prior-only 回看（peak[i-30,i-1] / 7d lag）需要它，否則窗首 30 bar
    # 結構性 False 縮 down-leg span（QC F5）。但 bundle **輸出**必須裁回 [ws, we]：buffer
    # bars 留在 returns/mask 會虛增 n_bars 量綱（340 vs 窗內 295）；B1 交集對齊雖使回歸
    # 無害，bundle 層計數仍須與分析窗一致（QC 預註冊帶 btc_bars∈[290,297] 的契約）。
    btc_returns: dict[Any, float] | None = None
    down_mask: dict[Any, bool] | None = None
    btc_closes = closes_by_symbol.get(_BTC_SYMBOL) or {}
    if len(btc_closes) >= 2:
        btc_returns = _clip_window(_returns_from_closes(btc_closes), ws, we)
        down_mask = _clip_window(_down_mask_from_closes(btc_closes, reasons), ws, we)
    else:
        reasons.append("btc_klines_insufficient")

    # ── 3) altcap producer（FND-2 rows + closes → equal-weight ex-BTC 籃子；空 → None）──
    altcap_returns = _load_altcap_returns(
        closes_by_symbol, ws, we, dsn=dsn, fnd2_rows_loader=fnd2_rows_loader, reasons=reasons
    )

    return FactorBundle(
        btc_returns=btc_returns,
        altcap_returns=altcap_returns,
        down_market_mask=down_mask,
        reasons=_dedupe(reasons),
    )


def _clip_window(
    series: dict[dt.date, Any] | None, ws: dt.date, we: dt.date
) -> dict[dt.date, Any] | None:
    """把 date-key 序列裁回分析窗 [ws, we]（buffer bars 只供 mask 回看，不入 bundle 輸出）。"""
    if series is None:
        return None
    return {d: v for d, v in series.items() if ws <= d <= we}


def _factor_symbols(reasons: list[str]) -> list[str]:
    """BTC + CORE25 ex-BTC（altcap producer scope）。altcap 模組不可得 → 只載 BTC + reason。"""
    syms = [_BTC_SYMBOL]
    ex_btc = _resolve_altcap_module_attr("CORE25_EX_BTC")
    if ex_btc is None:
        reasons.append("altcap_module_unavailable")
    else:
        syms.extend(ex_btc)
    return syms


def _resolve_altcap_module_attr(attr: str) -> Any:
    """lazy 取 altcap_basket 模組屬性（dual-path import；不可得 → None，fail-soft）。"""
    try:
        from program_code.research import altcap_basket as _ab  # noqa: PLC0415
    except ImportError:
        try:
            from research import altcap_basket as _ab  # type: ignore  # noqa: PLC0415
        except ImportError:
            return None
    return getattr(_ab, attr, None)


def _load_daily_closes(
    symbols: list[str],
    start: dt.date,
    end: dt.date,
    *,
    conn_provider: Any,
    reasons: list[str],
) -> dict[str, dict[dt.date, float]]:
    """唯讀 SELECT market.klines 1d closes → {symbol: {date: close}}。失敗 → {} + reason。"""
    provider = conn_provider or db_pool.get_pg_conn
    out: dict[str, dict[dt.date, float]] = {}
    try:
        with provider() as conn:
            if conn is None:
                reasons.append("klines_db_unavailable")
                return out
            cur = conn.cursor()
            # 參數化（symbol 列表 / 窗邊界皆綁定參數）；timeframe='1d' 對齊既有讀路徑。
            cur.execute(
                """
                SELECT symbol, ts, close
                FROM market.klines
                WHERE timeframe = '1d'
                  AND symbol = ANY(%s)
                  AND ts >= %s AND ts <= %s
                ORDER BY symbol, ts
                """,
                (
                    list(symbols),
                    dt.datetime.combine(start, dt.time.min, tzinfo=dt.timezone.utc),
                    dt.datetime.combine(end, dt.time.max, tzinfo=dt.timezone.utc),
                ),
            )
            for sym, ts, close in cur.fetchall():
                d = _to_date(ts)
                if d is None or close is None:
                    continue
                out.setdefault(str(sym), {})[d] = float(close)
    except Exception as exc:  # noqa: BLE001 — 唯讀載入失敗 fail-soft（B1 DEFER 兜底）
        logger.warning("market.klines 1d 載入失敗（fail-soft）：%s", exc)
        reasons.append("klines_load_failed")
        return {}
    return out


def _returns_from_closes(closes: dict[dt.date, float]) -> dict[dt.date, float] | None:
    """{date: close} → {date_t: close_t/close_{t-1} − 1}（chronological 相鄰 bar）。"""
    days = sorted(closes.keys())
    out: dict[dt.date, float] = {}
    for prev, cur in zip(days, days[1:]):
        base = closes[prev]
        if abs(base) < 1e-12:
            continue
        out[cur] = closes[cur] / base - 1.0
    return out or None


def _down_mask_from_closes(
    closes: dict[dt.date, float], reasons: list[str]
) -> dict[dt.date, bool] | None:
    """down-market mask（reuse compute_down_market_mask，零改動）——但以 ordinal int key 餵入。

    ★ 與 PA 設計字面的偏差（最小安全解，實證 ground）：compute_down_market_mask 內部 reuse
    residual gate 的 ±inf fit-window 解析，date key 與 float 邊界比較的 TypeError 被吞 →
    「空 mask」（實證：date-key 餵入回 size=0；int-key 正常）。2026-06-10 的 fail-loud 修補
    只加在 beta_neutral_check 主閘入口，不含此函數。本模塊不改 beta_neutral_check（P3b 已
    green+QC sign-off），改在呼叫端以 date.toordinal() int key 餵入再映回 date key——mask
    計算用「位置」索引（i−30 / i−7 on sorted list），key 只影響排序，ordinal int 與 date 的
    chronological 排序完全同序，語義零差。
    """
    try:
        try:
            from program_code.learning_engine.beta_neutral_check import (  # noqa: PLC0415
                compute_down_market_mask,
            )
        except ImportError:  # pragma: no cover — dual-path fallback
            from learning_engine.beta_neutral_check import (  # type: ignore  # noqa: PLC0415
                compute_down_market_mask,
            )
        ord_closes = {d.toordinal(): c for d, c in closes.items()}
        mask_ord = compute_down_market_mask(ord_closes)
        return {dt.date.fromordinal(int(o)): bool(v) for o, v in mask_ord.items()}
    except Exception as exc:  # noqa: BLE001 — mask 衍生失敗 fail-soft（B1 down_mask_missing_defer）
        logger.warning("down-market mask 計算失敗（fail-soft）：%s", exc)
        reasons.append("down_mask_compute_failed")
        return None


def _load_altcap_returns(
    closes_by_symbol: dict[str, dict[dt.date, float]],
    ws: dt.date,
    we: dt.date,
    *,
    dsn: str | None,
    fnd2_rows_loader: Callable[..., list[dict[str, Any]]] | None,
    reasons: list[str],
) -> dict[Any, float] | None:
    """altcap producer（零改動 reuse）：FND-2 rows + daily closes → equal-weight ex-BTC 籃子。

    任何失敗 / 空 returns → None + reason（B1 altcap_missing_btc_only_defer 兜底）。
    """
    build = _resolve_altcap_module_attr("build_altcap_returns")
    default_loader = _resolve_altcap_module_attr("load_fnd2_universe_rows")
    if build is None:
        reasons.append("altcap_module_unavailable")
        return None
    loader = fnd2_rows_loader or default_loader
    if loader is None:
        reasons.append("altcap_fnd2_loader_unavailable")
        return None
    try:
        now = dt.datetime.now(dt.timezone.utc)
        rows = loader(
            dt.datetime.combine(ws, dt.time.min, tzinfo=dt.timezone.utc),
            dt.datetime.combine(we, dt.time.max, tzinfo=dt.timezone.utc),
            now,  # asof：以現在視角（歷史窗的 bar 全已 closed）
            now,  # closed_bar_cutoff：同上
            dsn=dsn,
        )
        series = build(rows, closes_by_symbol, window_start=ws, window_end=we)
        reasons.extend(str(r) for r in (getattr(series, "reasons", None) or []))
        rets = getattr(series, "returns", None) or {}
        if not rets:
            reasons.append("altcap_returns_empty")
            return None
        return dict(rets)
    except Exception as exc:  # noqa: BLE001 — producer 失敗 fail-soft（B1 DEFER）
        logger.warning("altcap producer 失敗（fail-soft）：%s", exc)
        reasons.append("altcap_producer_failed")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# route 組合入口（derive window → load factors → 純函數映射）
# ═══════════════════════════════════════════════════════════════════════════════


def build_context_from_evidence(
    evidence: dict[str, Any],
    *,
    factor_loader: Callable[..., FactorBundle] | None = None,
    dsn: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """route 入口：evidence → (context, reasons)。window 缺/壞 → 不載因子（factors=None，
    B1 DEFER）；factor_loader 注入供測試（預設 load_factor_bundle）。
    """
    factors: FactorBundle | None = None
    pre_reasons: list[str] = []
    if isinstance(evidence, Mapping):
        ws = _to_date(evidence.get("window_start"))
        we = _to_date(evidence.get("window_end"))
        if ws is None or we is None:
            pre_reasons.append("window_missing_factors_not_loaded")
        else:
            loader = factor_loader or load_factor_bundle
            factors = loader(ws, we, dsn=dsn)
    context, reasons = build_math_gate_context(evidence, factors=factors)
    return context, _dedupe(pre_reasons + reasons)


# ═══════════════════════════════════════════════════════════════════════════════
# 小工具（date 解析 / dedupe）
# ═══════════════════════════════════════════════════════════════════════════════


def _to_date(value: Any) -> dt.date | None:
    """date / datetime / ISO 字串 → date；無法解析 → None（不偽造）。

    語意對齊 altcap_basket._to_date（私有 helper 不跨模組 import，自帶等價小函數，
    與 PA §D.2 對 reindex 模組的同一指示一致）。
    """
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
            return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return dt.date.fromisoformat(s[:10])
            except ValueError:
                return None
    return None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it in seen:
            continue
        seen.add(it)
        out.append(it)
    return out


__all__ = [
    "EVIDENCE_SCHEMA_V1",
    "FactorBundle",
    "build_math_gate_context",
    "load_factor_bundle",
    "build_context_from_evidence",
]
