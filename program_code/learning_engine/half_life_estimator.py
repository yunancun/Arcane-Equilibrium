"""
half_life_estimator — REF-20 Wave 5 P3a-Q1 signal half-life estimation pipeline.
信號半衰期估計管線 — REF-20 Wave 5 P3a-Q1。

MODULE_NOTE (EN): Estimates per-(strategy, symbol, cell) signal decay half-life
  via three fallback estimators. Output feeds OOS embargo computation
  (`max(7d, 2 * signal_half_life)` per V3 §8.1) and replay manifest's
  `oos_embargo_seconds` column. Pure offline math; no DB / IPC / exchange
  dependencies. Production acceptance requires FUP-2 attribution writer +
  decision_outcomes timeframe fix GREEN; current IMPL ships fixture-driven.
MODULE_NOTE (中): 透過三個 fallback 估計器，估計每 (策略, 幣種, cell) 訊號衰減
  半衰期。輸出餵 OOS embargo 計算（V3 §8.1：`max(7d, 2 * signal_half_life)`）
  與 replay manifest `oos_embargo_seconds` column。純離線數學；無 DB / IPC /
  exchange 依賴。生產驗收需 FUP-2 attribution writer + decision_outcomes
  timeframe fix GREEN；當前 IMPL 以 fixture 驅動。

Fallback estimators / Fallback 估計器:
1. **PnL decay** — exponential fit `y = a * exp(-t / half_life)` on
   `net_bps_after_fees` time series. Use scipy.optimize.curve_fit.
2. **Sharpe decay** — exponential fit on rolling Sharpe series.
3. **Default 14d** — conservative fallback when (a) PnL+Sharpe both fail
   p-value gate (>= 0.10) OR (b) sample size n < 30.

Half-life formula / 半衰期公式:
    PnL_t = PnL_0 * exp(-lambda * t)
    half_life = ln(2) / lambda

V3 §8.1 binding / V3 §8.1 綁定:
- "Half-life unmeasured → conservative default 14d."
- "Half-life = ln(2) / lambda."
- "Per strategy fit `PnL_t = PnL_0 * exp(-lambda * t)` on cell-level realized edge."

Usage / 使用:
    from program_code.learning_engine.half_life_estimator import (
        HalfLifeEstimator, HalfLifeResult,
    )
    estimator = HalfLifeEstimator()
    result = estimator.estimate_with_fallback(fills_df)
    # result.half_life_days, result.method_used, result.low_confidence
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np
import pandas as pd

try:
    from scipy.optimize import curve_fit  # type: ignore[import-untyped]
    from scipy import stats  # type: ignore[import-untyped]

    _SCIPY_AVAILABLE = True
except ImportError:  # pragma: no cover
    curve_fit = None  # type: ignore[assignment]
    stats = None  # type: ignore[assignment]
    _SCIPY_AVAILABLE = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants / 常量
# ---------------------------------------------------------------------------

# Default half-life when fit fails or sample insufficient (per V3 §8.1).
# 當擬合失敗或樣本不足時的預設半衰期（依 V3 §8.1）。
DEFAULT_HALF_LIFE_DAYS: float = 14.0

# Minimum sample size required for parametric fit attempt.
# 嘗試參數擬合所需的最小樣本量。
MIN_SAMPLE_SIZE: int = 30

# p-value threshold above which a fit is considered NOT significant.
# Per QC convention, p >= 0.10 → fall back to next estimator.
# p-value 閾值，超過此值視為擬合不顯著；依 QC 慣例，p >= 0.10 → 落到下個估計器。
P_VALUE_FAIL_THRESHOLD: float = 0.10

# Bounds for half-life output (sanity guard).
# 半衰期輸出邊界（健全性護欄）。
HALF_LIFE_MIN_DAYS: float = 0.1   # 2.4 hours min
HALF_LIFE_MAX_DAYS: float = 365.0  # 1 year max (cap unphysical fits)


# ---------------------------------------------------------------------------
# Result dataclass / 結果 dataclass
# ---------------------------------------------------------------------------


@dataclass
class HalfLifeResult:
    """
    Half-life estimation outcome.
    半衰期估計結果。

    Attributes / 屬性:
        half_life_days: estimated half-life in days; ALWAYS > 0 (sanity-clamped). /
                        估計半衰期（天）；恆為正（健全性夾取）。
        method_used: which estimator produced this result. /
                     產生此結果的估計器名稱。
        fit_p_value: parametric fit significance (None when method == 'default_14d'). /
                     參數擬合顯著性（method == 'default_14d' 時為 None）。
        sample_size: number of observations consumed by fit. /
                     擬合消耗的觀測數量。
        low_confidence: True when default_14d fallback triggered. /
                        觸發 default_14d fallback 時為 True。
    """

    half_life_days: float
    method_used: str  # 'pnl_decay' | 'sharpe_decay' | 'default_14d'
    fit_p_value: Optional[float]
    sample_size: int
    low_confidence: bool


# ---------------------------------------------------------------------------
# Helpers / 輔助函數
# ---------------------------------------------------------------------------


def _exp_decay_model(t: np.ndarray, a: float, half_life: float) -> np.ndarray:
    """
    Exponential decay model: y = a * exp(-t * ln(2) / half_life).
    指數衰減模型。

    Reparametrized so the fitted parameter IS the half-life (not lambda).
    / 重新參數化使擬合參數就是半衰期（非 lambda）。
    """
    # Guard half_life > 0 to avoid div-by-zero. / 保護 half_life > 0 防止除零。
    safe_half_life = max(half_life, 1e-9)
    return a * np.exp(-t * math.log(2.0) / safe_half_life)


def _absolute_residual_p_value(
    y_obs: np.ndarray,
    y_pred: np.ndarray,
    n_params: int,
) -> float:
    """
    Compute approximate goodness-of-fit p-value via residual ANOVA F-test.
    透過殘差 ANOVA F 檢定計算近似擬合 p-value。

    Null hypothesis: model offers no improvement over mean-only prediction.
    null 假設：模型對僅均值預測無改進。

    Returns p-value in [0, 1]. Lower p ⇒ fit is significant.
    回傳 [0, 1] 內的 p-value；越低代表擬合越顯著。
    """
    if not _SCIPY_AVAILABLE:  # pragma: no cover
        # No scipy → return neutral 0.5 (neither pass nor fail).
        # 無 scipy → 回傳中性 0.5（既不通過也不失敗）。
        return 0.5

    n = len(y_obs)
    if n <= n_params:
        return 1.0  # under-determined → fail-closed (not significant) / 欠定 → 失敗

    y_mean = float(np.mean(y_obs))
    ss_total = float(np.sum((y_obs - y_mean) ** 2))
    ss_residual = float(np.sum((y_obs - y_pred) ** 2))

    if ss_total <= 1e-12:
        # Constant series → undefined improvement; return neutral.
        # 常數序列 → 改進未定義；回傳中性。
        return 1.0

    ss_explained = ss_total - ss_residual
    if ss_explained <= 0:
        return 1.0  # model worse than mean / 模型比均值差

    df_model = n_params - 1  # exp_decay has 2 params → df_model = 1
    df_residual = n - n_params

    if df_model < 1 or df_residual < 1:
        return 1.0

    f_stat = (ss_explained / df_model) / (ss_residual / df_residual)
    p_value = float(1.0 - stats.f.cdf(f_stat, df_model, df_residual))
    # Clamp to [0, 1] for floating-point safety. / 浮點安全夾取。
    return max(0.0, min(1.0, p_value))


def _clamp_half_life(value: float) -> float:
    """
    Clamp half-life to [HALF_LIFE_MIN_DAYS, HALF_LIFE_MAX_DAYS].
    將半衰期夾取至 [min, max] 範圍。
    """
    if not math.isfinite(value):
        return DEFAULT_HALF_LIFE_DAYS
    return max(HALF_LIFE_MIN_DAYS, min(HALF_LIFE_MAX_DAYS, value))


# ---------------------------------------------------------------------------
# Estimator class / 估計器類別
# ---------------------------------------------------------------------------


class HalfLifeEstimator:
    """
    Three-fallback half-life estimator (PnL decay → Sharpe decay → default 14d).
    三 fallback 半衰期估計器（PnL decay → Sharpe decay → default 14d）。

    Input fills_df schema (REQUIRED columns):
    輸入 fills_df schema（必需欄位）:
        - 'ts': pd.Timestamp or float epoch seconds (sortable). / 排序鍵。
        - 'net_bps_after_fees': float bps per fill (for PnL decay). / 每筆 bps。
        - 'sharpe_60d_window': float rolling Sharpe (for Sharpe decay). / 滾動 Sharpe。
                               OPTIONAL — if absent, Sharpe estimator skipped. /
                               選填 — 缺失則跳過 Sharpe 估計器。

    Production note / 生產備註: when FUP-2 attribution writer + decision_outcomes
    timeframe fix deploy, fills_df shall be loaded from `trading.fills` JOIN
    `learning.exit_features` per cell key (strategy, symbol, side). For now,
    fixture-driven IMPL accepts arbitrary DataFrame matching schema above.
    """

    def __init__(
        self,
        min_sample_size: int = MIN_SAMPLE_SIZE,
        p_value_threshold: float = P_VALUE_FAIL_THRESHOLD,
        default_half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    ) -> None:
        """
        Initialize estimator with tunable thresholds.
        以可調閾值初始化估計器。

        Args / 引數:
            min_sample_size: minimum n for parametric fit attempt. /
                             參數擬合所需最小 n。
            p_value_threshold: p above which fit fails. /
                               擬合失敗的 p 閾值。
            default_half_life_days: fallback half-life. /
                                    fallback 半衰期。
        """
        self.min_sample_size = int(min_sample_size)
        self.p_value_threshold = float(p_value_threshold)
        self.default_half_life_days = float(default_half_life_days)

    # ------------------------------------------------------------------
    # Public API / 公開 API
    # ------------------------------------------------------------------

    def estimate(
        self,
        fills_df: pd.DataFrame,
        method: Literal["pnl_decay", "sharpe_decay", "default_14d"],
    ) -> HalfLifeResult:
        """
        Estimate half-life with explicit method selection.
        以顯式方法選擇估計半衰期。

        Args / 引數:
            fills_df: fills DataFrame (see class docstring schema). /
                      fills DataFrame（schema 見類別 docstring）。
            method: one of 'pnl_decay' / 'sharpe_decay' / 'default_14d'. /
                    方法名稱之一。

        Returns / 回傳:
            HalfLifeResult populated per chosen method. /
            按選擇方法填充的 HalfLifeResult。

        Raises / 拋出:
            ValueError: invalid method. / 無效方法。
        """
        if method == "default_14d":
            return self._default_fallback(sample_size=len(fills_df))
        if method == "pnl_decay":
            return self._fit_pnl_decay(fills_df)
        if method == "sharpe_decay":
            return self._fit_sharpe_decay(fills_df)
        raise ValueError(f"Invalid method: {method!r}")

    def estimate_with_fallback(self, fills_df: pd.DataFrame) -> HalfLifeResult:
        """
        Run three-fallback chain: PnL decay → Sharpe decay → default 14d.
        執行三 fallback 鏈：PnL decay → Sharpe decay → default 14d。

        Logic / 邏輯:
        1. If n < min_sample_size → default_14d immediately.
           若 n < min_sample_size → 立刻 default_14d。
        2. Try PnL decay; if fit p-value < threshold → return.
           嘗試 PnL decay；若 fit p-value < threshold → 回傳。
        3. Try Sharpe decay (if column present); if p < threshold → return.
           嘗試 Sharpe decay（若 column 存在）；若 p < threshold → 回傳。
        4. Otherwise → default_14d (low_confidence=True).
           否則 → default_14d（low_confidence=True）。

        Args / 引數:
            fills_df: see class docstring. / 見類別 docstring。

        Returns / 回傳:
            HalfLifeResult — best-of-three estimate. /
            HalfLifeResult — 三選一最佳估計。
        """
        n = len(fills_df)

        # Step 1: sample-size gate / 樣本量門檻
        if n < self.min_sample_size:
            logger.info(
                "half_life: n=%d < min=%d → default_14d fallback",
                n,
                self.min_sample_size,
            )
            return self._default_fallback(sample_size=n)

        # Step 2: try PnL decay / 嘗試 PnL decay
        pnl_result = self._fit_pnl_decay(fills_df)
        if (
            pnl_result.method_used == "pnl_decay"
            and pnl_result.fit_p_value is not None
            and pnl_result.fit_p_value < self.p_value_threshold
        ):
            return pnl_result

        # Step 3: try Sharpe decay (only if column present)
        # / 嘗試 Sharpe decay（僅當 column 存在）
        if "sharpe_60d_window" in fills_df.columns:
            sharpe_result = self._fit_sharpe_decay(fills_df)
            if (
                sharpe_result.method_used == "sharpe_decay"
                and sharpe_result.fit_p_value is not None
                and sharpe_result.fit_p_value < self.p_value_threshold
            ):
                return sharpe_result

        # Step 4: default fallback / 預設 fallback
        logger.info(
            "half_life: PnL+Sharpe fits both p>=%.2f → default_14d (n=%d)",
            self.p_value_threshold,
            n,
        )
        return self._default_fallback(sample_size=n)

    # ------------------------------------------------------------------
    # Internal estimators / 內部估計器
    # ------------------------------------------------------------------

    def _fit_pnl_decay(self, fills_df: pd.DataFrame) -> HalfLifeResult:
        """
        Fit `net_bps = a * exp(-t * ln(2) / half_life)` on absolute net_bps.
        在絕對 net_bps 上擬合指數衰減。

        Rationale: signal magnitude decay (alpha bleeds out as edge erodes);
        sign of bps captured separately via realized_edge_stats. We fit |bps|.
        理由：訊號量級衰減；bps 符號由 realized_edge_stats 分開捕獲；擬合 |bps|。
        """
        if "net_bps_after_fees" not in fills_df.columns:
            return self._default_fallback(sample_size=len(fills_df))

        if not _SCIPY_AVAILABLE:  # pragma: no cover
            logger.warning("half_life: scipy unavailable → default_14d")
            return self._default_fallback(sample_size=len(fills_df))

        df = fills_df.dropna(subset=["ts", "net_bps_after_fees"]).copy()
        if len(df) < self.min_sample_size:
            return self._default_fallback(sample_size=len(df))

        # Sort by ts ascending / 按 ts 升序排序
        df = df.sort_values("ts").reset_index(drop=True)
        # Convert ts to days-from-first / 將 ts 轉為距首日的天數
        ts_series = df["ts"]
        if pd.api.types.is_datetime64_any_dtype(ts_series):
            ts_seconds = (
                ts_series.astype("int64").to_numpy() / 1e9
            )  # ns → seconds / 納秒 → 秒
        else:
            ts_seconds = ts_series.astype(float).to_numpy()
        t_days = (ts_seconds - ts_seconds[0]) / 86400.0

        y = np.abs(df["net_bps_after_fees"].astype(float).to_numpy())
        if np.all(y == 0):
            return self._default_fallback(sample_size=len(df))

        # Initial guess: a=max(y), half_life=median of t / 初始猜測
        a0 = float(np.max(y))
        half_life0 = max(float(np.median(t_days)), 1.0)

        try:
            popt, _ = curve_fit(  # type: ignore[misc]
                _exp_decay_model,
                t_days,
                y,
                p0=[a0, half_life0],
                bounds=([0, HALF_LIFE_MIN_DAYS], [np.inf, HALF_LIFE_MAX_DAYS * 2]),
                maxfev=5000,
            )
            a_fit, half_life_fit = float(popt[0]), float(popt[1])
            y_pred = _exp_decay_model(t_days, a_fit, half_life_fit)
            p_value = _absolute_residual_p_value(y, y_pred, n_params=2)

            return HalfLifeResult(
                half_life_days=_clamp_half_life(half_life_fit),
                method_used="pnl_decay",
                fit_p_value=p_value,
                sample_size=len(df),
                low_confidence=False,
            )
        except (RuntimeError, ValueError) as e:
            logger.info("half_life: PnL decay fit failed: %s → fallback", e)
            return HalfLifeResult(
                half_life_days=self.default_half_life_days,
                method_used="pnl_decay",
                fit_p_value=1.0,  # explicit fail-flag / 明確失敗旗標
                sample_size=len(df),
                low_confidence=True,
            )

    def _fit_sharpe_decay(self, fills_df: pd.DataFrame) -> HalfLifeResult:
        """
        Fit `|sharpe_60d| = a * exp(-t * ln(2) / half_life)`.
        在 |sharpe_60d| 上擬合指數衰減。
        """
        if "sharpe_60d_window" not in fills_df.columns:
            return self._default_fallback(sample_size=len(fills_df))

        if not _SCIPY_AVAILABLE:  # pragma: no cover
            return self._default_fallback(sample_size=len(fills_df))

        df = fills_df.dropna(subset=["ts", "sharpe_60d_window"]).copy()
        if len(df) < self.min_sample_size:
            return self._default_fallback(sample_size=len(df))

        df = df.sort_values("ts").reset_index(drop=True)
        ts_series = df["ts"]
        if pd.api.types.is_datetime64_any_dtype(ts_series):
            ts_seconds = ts_series.astype("int64").to_numpy() / 1e9
        else:
            ts_seconds = ts_series.astype(float).to_numpy()
        t_days = (ts_seconds - ts_seconds[0]) / 86400.0

        y = np.abs(df["sharpe_60d_window"].astype(float).to_numpy())
        if np.all(y == 0):
            return self._default_fallback(sample_size=len(df))

        a0 = float(np.max(y))
        half_life0 = max(float(np.median(t_days)), 1.0)

        try:
            popt, _ = curve_fit(  # type: ignore[misc]
                _exp_decay_model,
                t_days,
                y,
                p0=[a0, half_life0],
                bounds=([0, HALF_LIFE_MIN_DAYS], [np.inf, HALF_LIFE_MAX_DAYS * 2]),
                maxfev=5000,
            )
            a_fit, half_life_fit = float(popt[0]), float(popt[1])
            y_pred = _exp_decay_model(t_days, a_fit, half_life_fit)
            p_value = _absolute_residual_p_value(y, y_pred, n_params=2)

            return HalfLifeResult(
                half_life_days=_clamp_half_life(half_life_fit),
                method_used="sharpe_decay",
                fit_p_value=p_value,
                sample_size=len(df),
                low_confidence=False,
            )
        except (RuntimeError, ValueError) as e:
            logger.info("half_life: Sharpe decay fit failed: %s → fallback", e)
            return HalfLifeResult(
                half_life_days=self.default_half_life_days,
                method_used="sharpe_decay",
                fit_p_value=1.0,
                sample_size=len(df),
                low_confidence=True,
            )

    def _default_fallback(self, sample_size: int) -> HalfLifeResult:
        """
        Return conservative 14d default with low_confidence=True.
        回傳保守 14d 預設並標記 low_confidence=True。
        """
        return HalfLifeResult(
            half_life_days=self.default_half_life_days,
            method_used="default_14d",
            fit_p_value=None,
            sample_size=sample_size,
            low_confidence=True,
        )


# ---------------------------------------------------------------------------
# Module-level convenience / 模組級便利函數
# ---------------------------------------------------------------------------


def estimate_half_life(
    fills_df: pd.DataFrame,
    min_sample_size: int = MIN_SAMPLE_SIZE,
) -> HalfLifeResult:
    """
    Module-level shortcut for HalfLifeEstimator.estimate_with_fallback.
    HalfLifeEstimator.estimate_with_fallback 的模組級捷徑。
    """
    return HalfLifeEstimator(min_sample_size=min_sample_size).estimate_with_fallback(
        fills_df
    )
