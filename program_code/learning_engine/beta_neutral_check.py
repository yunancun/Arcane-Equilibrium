"""beta_neutral_check（B1）— 純數學雙因子 beta 中性閘。

MODULE_NOTE
模塊用途：
  L2 Phase 3b B1 gate member（PA P3b 設計 §A + QC B1 four numbers）。把候選報酬對
  「BTC + altcap 雙因子」回歸，量 |β_btc| / |β_alt| / |β_down|（down sub-sample），並用
  coefficient SE 的 95% 上界（β + 1.96·SE）擋掉「小但噪音大」的偽中性。這是殺掉「down-
  market beta 偽裝 alpha」的閘——5 個候選（A1 funding_short / oi_delta / cascade-fade /
  funding-tilt / listing）全死於這個維度，故 getting it wrong 會重開那個失敗模式。

  它「重用」residual_alpha_gate._fit_factor_beta 的 OLS（np.linalg.lstsq，不 fork 回歸），
  只「加」一件 residual gate 不算的東西：coefficient SE（= residual-var × diag((X'X)⁻¹)），
  並在 Durbin-Watson < 1.5（殘差自相關）時升級為 HAC（Newey-West）SE。

主要類/函數：
  - BetaNeutralResult：dataclass（verdict / 三 β / SE / β_upper / DW / used_hac / n_bars /
    n_down_bars / reasons / factor_hash）。
  - beta_neutral_check(...)：入口（pure-math，0 DB / 0 Bybit / 0 order path）。
  - compute_down_market_mask(...)：從 BTC 1d closes 算 leak-free prior-only down-mask
    （30d-dd>8% OR 7d<-5%，絕對 scalar 門檻；不綁 V127、不用 full-sample percentile）。

依賴：
  - 僅 Python 標準庫 + numpy。
  - residual_alpha_gate._fit_factor_beta（OLS；不 fork）+ 其 candidate 解析 helper（同 shape）。

硬邊界：
  - verdict ∈ {pass, fail, DEFER}，strictest-wins（fail > DEFER > pass）：一個既 |β|≥0.15
    又 down-bars<30 的候選是 fail（非 DEFER），對齊 residual_alpha_gate 的 strictest 語義。
  - 雙因子「強制」：altcap_returns is None（producer 缺）→ DEFER（never 用 BTC-only 模型
    當中性——那正是 by-construction 的 masquerade pass）。
  - down-mask 必 leak-free prior-only（peak/LAG 都不含當前 bar）；down sub-sample 必由
    ≥180d span 抽（last-90d 只有 23 down-bars < 30 → 結構性不足）。
  - 0 LLM-invocation（math gate 是唯一 alpha validator；CC/E2/MIT grep target）。
  - **int-bar-index 契約（math_gate_inputs key 形態）**：candidate/btc/altcap returns 與
    down_mask 的 key **MUST 是共享 int bar index**（非 date/datetime/str）。原因：本閘的
    series 解析「重用」residual_alpha_gate._parse_candidate_returns，後者用 ±inf fit-window
    邊界界定範圍（`float('-inf') <= ts <= float('inf')`）；date/datetime/str key 與 float 邊界
    比較 raise TypeError 被 _contains 吞成 False → 該 row 被「靜默」丟棄 → 空 series → 偽
    universal DEFER（fail-safe 但靜默，違 fail-loud）。故入口顯式偵測 key 形態：任一非
    int(bar-index) key（含 mixed）→ **顯式 DEFER**（reason
    temporal_keys_unsupported_need_int_bar_index + logger.warning），非靜默空-series-DEFER。
    producer→context-assembly seam（未來 conductor wiring）須在傳入本閘前把 date→int bar
    index re-index；違反契約 → 顯式 DEFER（讓接線錯誤 fail-loud，不會靜默壞掉 hypothesize）。
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass
from typing import Any, Hashable, Mapping, Sequence

import numpy as np

# 重用 residual gate 的 OLS（_fit_factor_beta）+ candidate/factor 解析 + timestamp 抽取 +
# provenance hash（同 shape，不複製）。_extract_candidate_timestamp 用於 int-bar-index 契約檢測，
# 與 _parse_candidate_returns 用同一套 row→timestamp 語意（避免 fork 抽取邏輯造成 drift）。
from .residual_alpha_gate import (
    _extract_candidate_timestamp,
    _fit_factor_beta,
    _hash_factor_rows,
    _parse_candidate_returns,
)

_LOG = logging.getLogger(__name__)


# ── QC B1 four final numbers（QC spec §1，FINAL deterministic 常數）──
# 為什麼是 module-level 常數：QC-owned，閘設計成「拒絕」非「發現」，門檻固定不 sweep
# （replication-crisis 紀律：0 free param）。
BETA_NEUTRAL_THRESHOLD = 0.15      # |β| point-estimate 門檻（QC #3）：任一 |β_j| ≥ 0.15 → fail
BETA_UPPER_CAP = 0.20             # β + 1.96·SE 上界（QC #4）：任一 β_upper_j ≥ 0.20 → fail
WINDOW_DAYS_MIN = 90              # overall β window floor（QC #2）：對齊 bar 數 < 90 → DEFER
DOWN_SUBSAMPLE_SPAN_DAYS_MIN = 180  # down-leg span floor（QC #3c-window；MIT runtime：90d=23<30）
DOWN_BARS_MIN = 30               # down sub-sample ≥30 bars else DEFER（QC #3c-window）
N_TRADES_OOS_MIN = 50            # Q1：N_trades_oos ≥ 50 else DEFER（QC #Q1；map dsr_gate min_observations=50）

# down-market 定義（QC #3c；BTC anchor，lagged-PIT，絕對 scalar 非 percentile）。
_DOWN_DRAWDOWN_30D = 0.08        # 30d drawdown > 8%（close < prior-30d-peak × 0.92）
_DOWN_RETURN_7D = -0.05          # 7d return < -5%（close < close_{t-7} × 0.95）
_DOWN_DRAWDOWN_LOOKBACK = 30     # drawdown peak 的 prior 窗（不含當前 bar）
_DOWN_RETURN_LOOKBACK = 7        # 7d return 的 lag（不含當前 bar）

# z 值（95% 單尾-用-雙尾 1.96，QC #4 β_upper = β + 1.96·SE）。
_Z_95 = 1.96
# Durbin-Watson 自相關門檻：DW < 1.5 → 殘差正自相關顯著 → 升級 HAC SE（QC spec line 18）。
_DW_HAC_THRESHOLD = 1.5
_EPSILON = 1e-12

# 因子順序（雙因子模型 r_strat = α + β_btc·r_btc + β_alt·r_altcap + ε）。
_FACTORS_POOLED = ("btc", "altcap")
_FACTOR_DOWN = "btc"  # down sub-sample 只對 BTC 回歸（β_down = down-market 期間的 BTC beta）


@dataclass(frozen=True)
class BetaNeutralResult:
    """B1 beta-neutral 裁決結果。

    verdict ∈ {pass, fail, DEFER}（strictest-wins）。beta_* / se / beta_upper 在資料不足
    （DEFER）時為 None（不偽造數值）。
    """

    verdict: str  # "pass" | "fail" | "DEFER"
    beta_btc: float | None
    beta_alt: float | None
    beta_down: float | None
    se: dict[str, float | None]          # {"btc","alt","down"} coefficient SE（HAC-escalated 時為 HAC SE）
    beta_upper: dict[str, float | None]  # {"btc","alt","down"} β + 1.96·SE（QC #4）
    durbin_watson: float | None          # pooled 殘差的 DW（→ HAC escalation）
    used_hac: bool                       # 是否升級 HAC SE（DW < 1.5）
    n_bars: int                          # pooled 對齊 bar 數
    n_down_bars: int                     # down sub-sample bar 數
    reasons: tuple[str, ...]
    factor_hash: str                     # provenance（reuse residual gate 的 _hash_factor_rows）

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe dict（供 D3 row / audit surface）。"""
        out = asdict(self)
        return _json_safe(out)


def beta_neutral_check(
    candidate_returns: Mapping[Hashable, float] | Sequence[Any],
    btc_returns: Mapping[Hashable, float] | Sequence[Any],
    altcap_returns: Mapping[Hashable, float] | Sequence[Any] | None,
    down_market_mask: Mapping[Hashable, bool] | None,
    *,
    bar: str = "daily",
    window_days: int = WINDOW_DAYS_MIN,
    threshold: float = BETA_NEUTRAL_THRESHOLD,
    upper_cap: float = BETA_UPPER_CAP,
    down_bars_min: int = DOWN_BARS_MIN,
    n_trades_oos: int | None = None,
) -> BetaNeutralResult:
    """對候選報酬跑 B1 雙因子 beta 中性檢定（QC four numbers，確定性 fail-closed）。

    參數：
      - candidate_returns / btc_returns / altcap_returns：同 residual_alpha_gate 的 candidate
        解析 shape（Mapping[ts,float] / Sequence[(ts,val)] / dict rows）。altcap=None ⇒ 雙因子
        缺第二臂 → DEFER（QC #1，never BTC-only 偽中性）。**key 形態契約**：ts MUST 是共享
        int bar index（見下「int-bar-index 契約」）。
      - down_market_mask：Mapping[ts,bool]（§A.4 leak-free prior-only 算好的）；None ⇒ β_down
        無法估 → DEFER（保守）。
      - bar："daily" | "4h"（QC #2；不接 1m——衰減偏差）。
      - n_trades_oos：Q1 樣本數（None ⇒ 略過 Q1，由上游 math gate STEP0 統一把關；提供時
        < 50 → DEFER reason data_below_min_trades_oos）。

    int-bar-index 契約（fail-loud）：
      所有 series/mask 的 key MUST 是共享 int bar index（非 date/datetime/str/mixed）。本閘
      的 series 解析重用 residual_alpha_gate 的 ±inf fit-window 邊界，date/datetime/str key 與
      float 邊界比較會 raise TypeError 被 _contains 吞成 False → row「靜默」全丟 → 空 series →
      偽 universal DEFER。為避免「未來接真 market.klines date-key 資料時靜默壞掉 hypothesize
      能力」，入口顯式偵測 key 形態：任一非 int(bar-index) key（含 mixed）→ **顯式 DEFER**
      （reason temporal_keys_unsupported_need_int_bar_index + logger.warning），非靜默空-series。
      date→int re-index 是 producer/conductor wiring 階段的責任（本 fix 只鎖契約 + fail-loud）。

    回 BetaNeutralResult。verdict strictest-wins：任一 fail reason → fail；否則任一 DEFER
    reason → DEFER；否則 pass。
    """
    reasons: list[str] = []

    # ── int-bar-index 契約閘（fail-LOUD，必須在 _parse_series 之前）──
    # 為什麼在解析前：_parse_series → residual gate 的 ±inf fit-window 對 date/datetime/str key
    # 會靜默丟 row（TypeError 被 _contains 吞）→ 空 series → 偽 universal DEFER（靜默）。此處在
    # row 被吞之前偵測原始 key 形態，把「靜默壞掉」轉成「顯式可診斷的 DEFER + warning」。
    non_int_key = _first_non_int_bar_index_key(
        candidate_returns, btc_returns, altcap_returns, down_market_mask
    )
    if non_int_key is not None:
        _LOG.warning(
            "beta_neutral_check: math_gate_inputs key 非 int bar index "
            "(got %s key=%r) — 契約要求共享 int bar index；顯式 DEFER（非靜默空-series）。"
            "date→int re-index 須在 producer/conductor wiring 階段完成。",
            type(non_int_key).__name__,
            non_int_key,
        )
        # 顯式 DEFER：不繼續走會靜默丟 row 的解析路徑（factor_hash 無從可信計算，給空 hash）。
        return _defer_result(
            ["temporal_keys_unsupported_need_int_bar_index"],
            n_bars=0,
            n_down_bars=0,
            factor_hash="",
        )
    if bar not in ("daily", "4h"):
        # 1m 不接（QC #2 attenuation）；未知 bar → DEFER（不偽裝可信）。
        reasons.append(f"unsupported_bar:{bar}")

    # ── Q1（可選，math gate STEP0 也把關；此處提供 n_trades_oos 時順手檢）──
    if n_trades_oos is not None and n_trades_oos < N_TRADES_OOS_MIN:
        reasons.append("data_below_min_trades_oos")

    # ── QC #1：雙因子強制——altcap 缺 → DEFER（never BTC-only 偽中性）──
    if altcap_returns is None:
        reasons.append("altcap_missing_btc_only_defer")

    # 解析候選 + 因子（用 residual gate 的 candidate 解析語意：無 fit_window 限制，全域對齊）。
    candidate = _parse_series(candidate_returns)
    btc = _parse_series(btc_returns)
    altcap = _parse_series(altcap_returns) if altcap_returns is not None else {}

    # ── pooled 對齊：candidate ∩ btc ∩ altcap 的共同 ts（雙因子需三者皆有）──
    pooled_ts = _aligned_ts(candidate, btc, altcap) if altcap_returns is not None else []
    n_bars = len(pooled_ts)
    if altcap_returns is not None and n_bars < window_days:
        # QC #2：對齊 bar 數 < 90d → DEFER（資料窗不足，β 不可信）。
        reasons.append("window_below_90d")

    # provenance hash（reuse residual gate 的 factor hash；以 pooled ts 的 btc/altcap 值算）。
    factor_hash = _factor_hash(pooled_ts, btc, altcap)

    # 資料不足時直接回 DEFER（不做不可信的 β 推論；對齊 residual gate 的早退語意）。
    if reasons and _strictest_verdict(reasons) == "DEFER" and (
        altcap_returns is None or n_bars < window_days
    ):
        return _defer_result(reasons, n_bars=n_bars, n_down_bars=0, factor_hash=factor_hash)

    # ── STEP 3a：pooled betas（β_btc, β_alt）on ≥90d ──
    y = np.asarray([candidate[ts] for ts in pooled_ts], dtype=np.float64)
    x = np.asarray(
        [[btc[ts], altcap[ts]] for ts in pooled_ts], dtype=np.float64
    )
    pooled_fit = _fit_with_se(y, x, factor_names=_FACTORS_POOLED)
    if pooled_fit is None:
        # 退化（singular X'X / n ≤ k）→ DEFER（不 crash；對齊 residual gate fail-soft）。
        reasons.append("pooled_regression_degenerate")
        return _defer_result(reasons, n_bars=n_bars, n_down_bars=0, factor_hash=factor_hash)

    beta_btc = pooled_fit["betas"]["btc"]
    beta_alt = pooled_fit["betas"]["altcap"]
    se_btc = pooled_fit["se"]["btc"]
    se_alt = pooled_fit["se"]["altcap"]
    dw = pooled_fit["durbin_watson"]
    used_hac = pooled_fit["used_hac"]

    # ── STEP 3b：down-leg（β_down）on ≥180d-span down sub-sample ──
    beta_down: float | None = None
    se_down: float | None = None
    n_down_bars = 0
    if down_market_mask is None:
        reasons.append("down_mask_missing_defer")
    else:
        down_ts = [ts for ts in pooled_ts if bool(down_market_mask.get(ts, False))]
        n_down_bars = len(down_ts)
        # span 檢查：down sub-sample 抽樣窗跨度須 ≥180d（QC #3c-window；不是 down-bar 數本身）。
        span_ok = _span_days(down_ts) >= DOWN_SUBSAMPLE_SPAN_DAYS_MIN if down_ts else False
        if n_down_bars < down_bars_min:
            # QC #3c-window：down-bars < 30 → DEFER（β_down 不可信）。
            reasons.append("down_bars_below_30_defer")
        elif not span_ok:
            # bars 夠但抽樣窗 < 180d（過度集中於短期）→ DEFER（QC #3c-window span 要求）。
            reasons.append("down_subsample_span_below_180d_defer")
        else:
            y_d = np.asarray([candidate[ts] for ts in down_ts], dtype=np.float64)
            x_d = np.asarray([[btc[ts]] for ts in down_ts], dtype=np.float64)
            down_fit = _fit_with_se(y_d, x_d, factor_names=(_FACTOR_DOWN,))
            if down_fit is None:
                reasons.append("down_regression_degenerate")
            else:
                beta_down = down_fit["betas"]["btc"]
                se_down = down_fit["se"]["btc"]

    # ── QC #3：|β| ≥ 0.15 → fail（三 β 皆檢；None 的臂不誤判 fail）──
    if beta_btc is not None and abs(beta_btc) >= threshold:
        reasons.append("beta_btc_above_threshold")
    if beta_alt is not None and abs(beta_alt) >= threshold:
        reasons.append("beta_alt_above_threshold")
    if beta_down is not None and abs(beta_down) >= threshold:
        reasons.append("beta_down_above_threshold")

    # ── QC #4：β_upper = β + 1.96·SE ≥ 0.20 → fail（殺「小但噪音大」的偽中性）──
    # 為什麼用 |β| + 1.96·SE：β 可正可負；中性要求是 |β| 的上界 < cap，故對 |β| 加 1.96·SE。
    beta_upper = {
        "btc": _beta_upper(beta_btc, se_btc),
        "alt": _beta_upper(beta_alt, se_alt),
        "down": _beta_upper(beta_down, se_down),
    }
    for leg, up in beta_upper.items():
        if up is not None and up >= upper_cap:
            reasons.append(f"beta_{leg}_upper_above_cap")

    verdict = _strictest_verdict(reasons)
    return BetaNeutralResult(
        verdict=verdict,
        beta_btc=beta_btc,
        beta_alt=beta_alt,
        beta_down=beta_down,
        se={"btc": se_btc, "alt": se_alt, "down": se_down},
        beta_upper=beta_upper,
        durbin_watson=dw,
        used_hac=used_hac,
        n_bars=n_bars,
        n_down_bars=n_down_bars,
        reasons=tuple(_dedupe(reasons)),
        factor_hash=factor_hash,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# down-market mask — leak-free prior-only（§A.4，MIT Path B，不綁 V127）
# ═══════════════════════════════════════════════════════════════════════════════


def compute_down_market_mask(
    btc_daily_closes: Mapping[Hashable, float] | Sequence[tuple[Hashable, float]],
) -> dict[Hashable, bool]:
    """從 BTC 1d closes 算 leak-free prior-only down-market mask（§A.4 / QC #3c / MIT §3.5）。

    down-market(t) = (30d drawdown > 8%) OR (7d return < -5%)，兩者皆 prior-only：
      - 30d drawdown：close_t < peak(close[t-30 : t-1]) × 0.92（peak 取「前」30 bar，不含 t）。
      - 7d return：close_t < close_{t-7} × 0.95。

    為什麼絕對 scalar（8% / 5%）而非 full-sample percentile：避免 data_loader.py:300 那種
    full-sample vol-tercile cross-section leak（label 偷看整段分布）。門檻是固定 scalar，
    label@t 只用 ≤t 的資料（lagged-PIT），故無 look-ahead。

    回 {ts: bool}。前 30 bar（prior 窗不足）一律 False（保守：無法證 down 就不標 down）。
    """
    parsed = _parse_series(btc_daily_closes)
    # chronological 排序（非字典序）：prior-peak / 7d-lag 依賴真時間序，整數 ts 字典序會錯。
    ts_sorted = sorted(parsed.keys(), key=_chrono_key)
    closes = [parsed[ts] for ts in ts_sorted]
    mask: dict[Hashable, bool] = {}
    for i, ts in enumerate(ts_sorted):
        is_down = False
        # 30d drawdown（peak 取 prior [i-30, i-1]，不含 i）。
        if i >= _DOWN_DRAWDOWN_LOOKBACK:
            prior_peak = max(closes[i - _DOWN_DRAWDOWN_LOOKBACK : i])
            if prior_peak > _EPSILON and closes[i] < prior_peak * (1.0 - _DOWN_DRAWDOWN_30D):
                is_down = True
        # 7d return（close_{i-7}，不含 i）。
        if not is_down and i >= _DOWN_RETURN_LOOKBACK:
            ref = closes[i - _DOWN_RETURN_LOOKBACK]
            if ref > _EPSILON and (closes[i] / ref - 1.0) < _DOWN_RETURN_7D:
                is_down = True
        mask[ts] = is_down
    return mask


# ═══════════════════════════════════════════════════════════════════════════════
# OLS + coefficient SE + HAC（§A.2，重用 _fit_factor_beta，只「加」SE）
# ═══════════════════════════════════════════════════════════════════════════════


def _fit_with_se(
    y: np.ndarray, x: np.ndarray, *, factor_names: tuple[str, ...]
) -> dict[str, Any] | None:
    """OLS（重用 residual gate _fit_factor_beta）+ coefficient SE（+ DW<1.5 時 HAC）。

    回 {"betas":{name:val}, "se":{name:val}, "durbin_watson":float, "used_hac":bool}，
    或 None（退化：n ≤ k 或 singular X'X）。

    為什麼不 fork lstsq：residual_alpha_gate._fit_factor_beta 已是 design=[1|x] 的 OLS 權威；
    B1 只「加」殘差變異 × diag((X'X)⁻¹) 的 SE（這是 residual gate 唯一不算的東西）。
    """
    n = len(y)
    k = x.shape[1] + 1  # intercept + factors
    if n <= k:
        return None  # 自由度不足（n - k ≤ 0），SE 無法估。

    # 步驟 1-2：重用 _fit_factor_beta 的 lstsq（design = [ones | x]，identical OLS）。
    intercept, beta = _fit_factor_beta(y, x)
    design = np.column_stack([np.ones(n, dtype=np.float64), x])
    coef = np.concatenate([[intercept], beta])
    resid = y - design @ coef

    # 步驟 3：residual variance σ²_resid = SSR / (n - k)。
    ssr = float(np.sum(resid ** 2))
    sigma2 = ssr / float(n - k)

    # 步驟 4：(X'X)⁻¹（singular → pinv fail-soft；完全退化 → None）。
    xtx = design.T @ design
    try:
        xtx_inv = np.linalg.inv(xtx)
    except np.linalg.LinAlgError:
        xtx_inv = np.linalg.pinv(xtx)
    if not np.all(np.isfinite(xtx_inv)):
        return None

    # 步驟 6：Durbin-Watson on residual（DW < 1.5 → 殘差自相關顯著 → HAC）。
    dw = _durbin_watson(resid)
    used_hac = dw is not None and dw < _DW_HAC_THRESHOLD

    if used_hac:
        # 步驟 6（HAC）：Newey-West（Bartlett kernel）SE。
        cov = _newey_west_cov(design, resid, xtx_inv)
    else:
        # 步驟 5：OLS SE = sqrt(σ²_resid · diag((X'X)⁻¹))。
        cov = sigma2 * xtx_inv

    diag = np.diag(cov)
    # coef index 0 是 intercept；factor j 對應 index j+1。
    betas: dict[str, float] = {}
    se: dict[str, float] = {}
    for j, name in enumerate(factor_names):
        idx = j + 1
        betas[name] = float(coef[idx])
        d = float(diag[idx])
        se[name] = float(math.sqrt(d)) if d > 0.0 and math.isfinite(d) else float("nan")
    return {
        "betas": betas,
        "se": se,
        "durbin_watson": dw,
        "used_hac": used_hac,
    }


def _durbin_watson(resid: np.ndarray) -> float | None:
    """Durbin-Watson 統計量 DW = Σ(e_t − e_{t-1})² / Σe_t²。

    為什麼：DW ≈ 2 無自相關；DW < 1.5（QC line 18）→ 正自相關顯著 → OLS SE 低估，須升級 HAC。
    """
    denom = float(np.sum(resid ** 2))
    if denom <= _EPSILON or len(resid) < 2:
        return None
    diff = np.diff(resid)
    return float(np.sum(diff ** 2) / denom)


def _newey_west_cov(
    design: np.ndarray, resid: np.ndarray, xtx_inv: np.ndarray
) -> np.ndarray:
    """Newey-West HAC 協方差（Bartlett kernel，手搓無 statsmodels）。

    Cov = (X'X)⁻¹ · (X' Ω̂ X) · (X'X)⁻¹，其中 X' Ω̂ X 用 Bartlett-kernel 加權自協方差：
      S = Σ_t e_t² x_t x_t'  +  Σ_{l=1..L} w_l Σ_t e_t e_{t-l} (x_t x_{t-l}' + x_{t-l} x_t')
      w_l = 1 - l/(L+1)（Bartlett）；L = floor(4·(n/100)^(2/9))（標準 Newey-West bandwidth）。

    為什麼手搓：對齊 dsr_gate「hand-roll 避免 scipy 依賴」（dsr_gate.py:161-164）；HAC 只需
    numpy + stdlib。殘差正自相關時這給更誠實（更大）的 SE，使 β_upper 更難過 cap。
    """
    n, p = design.shape
    # Bartlett bandwidth L（標準 Newey-West；n 很小時至少 1）。
    lag = int(math.floor(4.0 * (n / 100.0) ** (2.0 / 9.0)))
    lag = max(1, min(lag, n - 1))

    # S0 = Σ_t e_t² x_t x_t'。
    s = np.zeros((p, p), dtype=np.float64)
    e2x = (resid[:, None] * design)  # e_t · x_t（n×p）
    s += e2x.T @ e2x  # = Σ e_t² x_t x_t'
    # lagged terms。
    for l in range(1, lag + 1):
        w = 1.0 - l / (lag + 1.0)  # Bartlett weight
        # Σ_t e_t e_{t-l} x_t x_{t-l}'（t 從 l 起）。
        a = e2x[l:]        # e_t x_t
        b = e2x[:-l]       # e_{t-l} x_{t-l}
        gamma = a.T @ b
        s += w * (gamma + gamma.T)

    cov = xtx_inv @ s @ xtx_inv
    return cov


# ═══════════════════════════════════════════════════════════════════════════════
# 內部 helper（解析 / 對齊 / span / verdict / json-safe）
# ═══════════════════════════════════════════════════════════════════════════════


def _is_int_bar_index(key: Hashable) -> bool:
    """key 是否為合法 int bar index。

    為什麼排除 bool：Python 中 bool 是 int 子類（isinstance(True, int) is True），但 True/False
    當 series key 是病態輸入，不算合法 bar index；故顯式排除（type(key) is bool）。datetime/date/
    str/float 皆非 int → 非合法 bar index（觸發 fail-loud DEFER）。
    """
    return isinstance(key, int) and not isinstance(key, bool)


def _input_keys(
    series: Mapping[Hashable, float] | Sequence[Any] | None,
) -> list[Hashable]:
    """抽出 series/mask 的 timestamp-position key（不經 ±inf fit-window 過濾，故不會靜默丟 row）。

    為什麼不用 _parse_series 的結果取 key：_parse_series 對 temporal key 回空 dict（row 全被吞），
    取不到 key 形態。此處在「吞」之前直接讀原始 key：Mapping → .keys()；Sequence/(ts,val)/dict-row
    → 重用 residual gate 的 _extract_candidate_timestamp（與真正解析用同一套 row→ts 語意）。
    抽取失敗的 row 跳過（交由下游解析報 invalid_candidate_return_row，本契約閘只看可抽出的 key）。
    """
    if series is None:
        return []
    if isinstance(series, Mapping):
        return list(series.keys())
    keys: list[Hashable] = []
    for row in series:
        try:
            keys.append(_extract_candidate_timestamp(row))
        except (KeyError, TypeError, ValueError):
            continue  # malformed row：留給下游解析報錯，契約閘不在此判 key 形態
    return keys


def _first_non_int_bar_index_key(
    *inputs: Mapping[Hashable, float] | Sequence[Any] | None,
) -> Hashable | None:
    """掃所有非 None 輸入的 key；回第一個非 int(bar-index) key（含 mixed），全合法回 None。

    為什麼回「第一個違規 key」而非 bool：給 logger.warning 帶上實際型別/值，讓接線錯誤
    （date→int re-index 漏做）在 log 即可診斷，不必反推。任一輸入任一 key 非 int → 觸發
    fail-loud DEFER（混型 int+date 也算違規：down-leg/pooled 對齊會因型別不一致再次靜默丟 row）。
    """
    for series in inputs:
        for key in _input_keys(series):
            if not _is_int_bar_index(key):
                return key
    return None


def _parse_series(
    series: Mapping[Hashable, float] | Sequence[Any] | None,
) -> dict[Hashable, float]:
    """把 candidate/factor series 解析成 {ts: float}（reuse residual gate 的 candidate 解析語意）。

    為什麼 reuse _parse_candidate_returns：B1 的 candidate/factor 接受同樣 shape（Mapping /
    (ts,val) / dict-row）；用一個無 fit_window 限制的 wide window 取全部 finite row。
    """
    if series is None:
        return {}
    # 用一個涵蓋一切的 fit_window（B1 不分 train/eval，全域對齊）；_parse_candidate_returns
    # 的 _in_fit_scope 只用來界定範圍，這裡給 [-inf, inf] 等價窗（任何可比較 ts 都落入）。
    wide = _WideFitWindow()
    parsed, _reasons = _parse_candidate_returns(series, wide)  # type: ignore[arg-type]
    return parsed


class _WideFitWindow:
    """涵蓋一切的 fit_window stub（_in_fit_scope 對任意 ts 回 True）。

    為什麼：_parse_candidate_returns 需要一個有 train_*/eval_* 屬性的 window 來界定範圍；
    B1 要全域對齊（非 train/eval 分割），故給一個「任何 ts 都 in scope」的窗。
    """

    # _contains(ts, start, end) 用 start <= ts <= end；以 ±inf 邊界讓任何數值/可比較 ts 落入。
    train_start = float("-inf")
    train_end = float("inf")
    eval_start = float("-inf")
    eval_end = float("inf")
    label = "b1_wide"


def _chrono_key(ts: Hashable) -> tuple[int, float, str]:
    """時間序排序 key（chronological，非字典序）。

    為什麼不直接用 residual_alpha_gate._sort_key：那個按字串 repr 排（對 datetime ISO 正確、
    對整數是字典序 "10"<"9"）。B1 的 Durbin-Watson / Newey-West 依賴殘差「真時間序」，故 ts
    必須 chronological：datetime → toordinal；數值 → 數值；其餘退回字串（穩定）。tuple 首位
    分桶確保跨型別排序確定（不會 datetime vs int 比較 raise）。
    """
    o = _to_ordinal(ts)
    if o is not None:
        return (0, o, "")
    try:
        return (1, float(ts), "")  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return (2, 0.0, str(ts))


def _aligned_ts(
    candidate: dict[Hashable, float],
    btc: dict[Hashable, float],
    altcap: dict[Hashable, float],
) -> list[Hashable]:
    """candidate ∩ btc ∩ altcap 的共同 ts（chronological 排序）。雙因子需三者皆有值。

    為什麼 chronological（非 _sort_key 字典序）：回歸殘差的 DW/HAC 依賴真時間序（見 _chrono_key）。
    """
    common = set(candidate) & set(btc) & set(altcap)
    return sorted(common, key=_chrono_key)


def _span_days(ts_list: Sequence[Hashable]) -> float:
    """ts list 的跨度（天）。ts 為 datetime → 真天數；為數值（bar index/天序）→ 差值當天數。

    為什麼容兩種：B1 的 ts 可能是 date/datetime（真窗）或整數 bar index（合成測試）。datetime
    走 toordinal；數值走 max-min（每單位視為一天，與 daily bar 對齊）。

    為什麼取真 min/max 而非 list[0]/list[-1]：上游用 residual_alpha_gate._sort_key（按字串
    repr 排序，對 datetime ISO 字串正確、對整數是字典序），故 list 端點不保證是數值極值；此處
    對 ordinal/數值取真 min/max，跨度計算與排序順序解耦（避免整數 bar index 的字典序假 span）。
    """
    if not ts_list:
        return 0.0
    # 優先 datetime-like（toordinal）；全部可轉 ordinal → 用 ordinal 真 min/max。
    ords = [_to_ordinal(ts) for ts in ts_list]
    if all(o is not None for o in ords):
        return abs(max(ords) - min(ords))  # type: ignore[type-var]
    # 數值 ts（bar index）：取真 min/max（每單位一天，daily bar）。
    nums: list[float] = []
    for ts in ts_list:
        try:
            nums.append(float(ts))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0
    return abs(max(nums) - min(nums)) if nums else 0.0


def _to_ordinal(ts: Hashable) -> float | None:
    """datetime/date → 序數天（toordinal）；非日期型回 None。"""
    to_ord = getattr(ts, "toordinal", None)
    if callable(to_ord):
        try:
            return float(to_ord())
        except Exception:  # noqa: BLE001 — 非標準 date-like → 視為非日期
            return None
    return None


def _beta_upper(beta: float | None, se: float | None) -> float | None:
    """β_upper = |β| + 1.96·SE（QC #4）。β/SE 任一缺或非 finite → None。"""
    if beta is None or se is None:
        return None
    if not (math.isfinite(beta) and math.isfinite(se)):
        return None
    return abs(beta) + _Z_95 * se


def _factor_hash(
    pooled_ts: Sequence[Hashable],
    btc: dict[Hashable, float],
    altcap: dict[Hashable, float],
) -> str:
    """provenance hash（reuse residual gate 的 _hash_factor_rows，以 btc/altcap 值算）。"""
    factors: dict[Hashable, dict[str, float]] = {}
    for ts in pooled_ts:
        row: dict[str, float] = {}
        if ts in btc:
            row["btc"] = btc[ts]
        if ts in altcap:
            row["altcap"] = altcap[ts]
        if row:
            factors[ts] = row
    required = ("btc", "altcap") if altcap else ("btc",)
    return _hash_factor_rows(
        factors=factors,
        timestamps=tuple(pooled_ts),
        required_factors=required,
        return_unit="fraction",
    )


# fail / DEFER reason 分類（strictest-wins）。
# 為什麼顯式列舉 fail reason：fail 必須 dominate DEFER（一個既越門檻又樣本不足的候選是 fail），
# 對齊 residual_alpha_gate._verdict_from_blocking_reasons 的 strictest 語義。
_FAIL_REASON_PREFIXES = (
    "beta_btc_above_threshold",
    "beta_alt_above_threshold",
    "beta_down_above_threshold",
    "beta_btc_upper_above_cap",
    "beta_alt_upper_above_cap",
    "beta_down_upper_above_cap",
)


def _strictest_verdict(reasons: Sequence[str]) -> str:
    """strictest-wins：任一 fail reason → fail；否則任一 reason（DEFER）→ DEFER；否則 pass。"""
    if not reasons:
        return "pass"
    if any(r in _FAIL_REASON_PREFIXES for r in reasons):
        return "fail"
    return "DEFER"


def _defer_result(
    reasons: Sequence[str], *, n_bars: int, n_down_bars: int, factor_hash: str
) -> BetaNeutralResult:
    """資料不足時的 DEFER 結果（β/SE 全 None，不偽造數值）。"""
    return BetaNeutralResult(
        verdict=_strictest_verdict(reasons),
        beta_btc=None,
        beta_alt=None,
        beta_down=None,
        se={"btc": None, "alt": None, "down": None},
        beta_upper={"btc": None, "alt": None, "down": None},
        durbin_watson=None,
        used_hac=False,
        n_bars=n_bars,
        n_down_bars=n_down_bars,
        reasons=tuple(_dedupe(reasons)),
        factor_hash=factor_hash,
    )


def _dedupe(reasons: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for r in reasons:
        if r in seen:
            continue
        seen.add(r)
        out.append(r)
    return out


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


__all__ = [
    "BETA_NEUTRAL_THRESHOLD",
    "BETA_UPPER_CAP",
    "WINDOW_DAYS_MIN",
    "DOWN_SUBSAMPLE_SPAN_DAYS_MIN",
    "DOWN_BARS_MIN",
    "N_TRADES_OOS_MIN",
    "BetaNeutralResult",
    "beta_neutral_check",
    "compute_down_market_mask",
]
