"""
MODULE_NOTE
模塊用途：Residual alpha PRODUCER 純核心（R-1）。把 timestamped 候選報酬與
時間對齊的 factor（BTC / market）序列組裝成 ResidualAlphaGate 輸入，呼叫離線
gate，回傳 canonical ``demo_residual_alpha_report`` dict 與 promotion-ready 判定。
主要類/函數：ResidualAlphaProducerResult、build_residual_alpha_report。
依賴：標準庫 + residual_alpha_gate + residual_alpha_report_contract；不連 DB、
不讀交易所、不碰 runtime / order / risk / auth。
硬邊界：
  - 只在 candidate 與 factor「同時存在、值皆 finite、factor 含全部 required
    factor」的 timestamp 上對齊（leak-free intersection）；任一缺值的 ts 丟棄。
  - train / eval 由 timestamp 排序後切分，train 在前、eval 在後，
    train_end < eval_start by construction（gate 禁 full-sample beta）。
  - 不發明資料：對齊樣本不足、PBO peer 缺失、或 gate 判 defer/fail 時，
    promotion_ready 一律 False（由 canonical validator 把關），不得偽造 pass。
  - candidate 與 factor 必須同單位（預設 bps）；price→return 與單位換算是
    caller（R-2 DB adapter）的責任，本核心只做組裝與評估。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Hashable, Mapping, Sequence

try:  # 套件式 import（app runtime）
    from program_code.learning_engine.residual_alpha_gate import (
        DEFAULT_MAX_PERM_P_VALUE,
        DEFAULT_PERMUTATION_N,
        ResidualAlphaFitWindow,
        ResidualAlphaGate,
        ResidualAlphaProtocol,
    )
    from program_code.ml_training.residual_alpha_report_contract import (
        validate_demo_residual_alpha_report,
    )
except ModuleNotFoundError:  # pragma: no cover - 直跑 fallback
    from learning_engine.residual_alpha_gate import (  # type: ignore
        DEFAULT_MAX_PERM_P_VALUE,
        DEFAULT_PERMUTATION_N,
        ResidualAlphaFitWindow,
        ResidualAlphaGate,
        ResidualAlphaProtocol,
    )
    from ml_training.residual_alpha_report_contract import (  # type: ignore
        validate_demo_residual_alpha_report,
    )


DEFAULT_TRAIN_FRACTION: float = 0.7
DEFAULT_REQUIRED_FACTORS: tuple[str, ...] = ("btc", "market")


@dataclass(frozen=True)
class ResidualAlphaProducerResult:
    """Producer 輸出：canonical report dict + promotion-ready 判定 + 對齊診斷。

    report 即 ResidualEdgeReport.to_dict()（或樣本不足時的 fail-closed defer
    report）；promotion_ready 由 canonical validate_demo_residual_alpha_report
    判定，caller 應只把 report 寫進候選 row，由下游 gate 再次強制驗證。
    """

    report: dict[str, Any]
    promotion_ready: bool
    reason: str
    aligned_observations: int
    train_observations: int
    eval_observations: int


def build_residual_alpha_report(
    candidate_returns: Mapping[Hashable, Any],
    factor_returns: Mapping[Hashable, Mapping[str, Any]],
    *,
    n_trials: int,
    peer_oos_returns: Sequence[Any] | None = None,
    train_fraction: float = DEFAULT_TRAIN_FRACTION,
    embargo_gap: float = 0.0,
    required_factors: tuple[str, ...] = DEFAULT_REQUIRED_FACTORS,
    return_unit: str = "bps",
    min_train_observations: int = 30,
    min_eval_observations: int = 10,
    min_coverage: float = 0.8,
    min_r_beta_retention: float = 0.5,
    max_beta_edge_share: float = 0.5,
    min_psr: float = 0.95,
    min_dsr: float = 0.95,
    max_pbo: float = 0.5,
    psr_benchmark_bps: float = 0.0,
    permutation_enabled: bool = False,
    permutation_n: int = DEFAULT_PERMUTATION_N,
    permutation_seed: int | None = None,
    max_perm_p_value: float = DEFAULT_MAX_PERM_P_VALUE,
) -> ResidualAlphaProducerResult:
    """組裝並評估 residual alpha report。

    參數：
      candidate_returns: ``{timestamp: return}``，單位由 return_unit 指定。
      factor_returns: ``{timestamp: {"btc": ret, "market": ret, ...}}``，與
        candidate 同單位、共用同一條 timestamp 軸。
      n_trials: 本輪多重檢驗的真實試驗數（供 DSR deflation；不得硬編 1）。
      peer_oos_returns: PBO peer 的 OOS 報酬序列（建議用 timestamped
        ``{ts: value}``，gate 會自動 scope 到 eval 窗）；缺則 gate 無法算
        PBO → 不得 promotion-ready。
      train_fraction: train 佔對齊樣本比例，其餘為 eval（皆至少 1 筆）。
      embargo_gap: train→eval 接縫前 purge 的 ts 缺口（同 ts 單位，預設 0）；
        用來避免 train obs 的持倉/前瞻窗與 eval obs 重疊造成滲漏。R-2 應傳
        ≥ 最大持倉窗（如 1m round-trip 的保守上界）的值。
    回傳 ResidualAlphaProducerResult；promotion_ready 由 canonical validator 判定。
    """
    if return_unit not in ("bps", "fraction"):
        raise ValueError("return_unit must be 'bps' or 'fraction'")
    if n_trials < 1:
        raise ValueError("n_trials must be >= 1")
    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction must be in (0, 1)")
    if embargo_gap < 0.0:
        raise ValueError("embargo_gap must be >= 0")
    if not required_factors:
        raise ValueError("required_factors must not be empty")

    aligned = _aligned_timestamps(candidate_returns, factor_returns, required_factors)
    window_split = _build_fit_window(aligned, train_fraction, embargo_gap)
    if window_split is None:
        return _insufficient_result(len(aligned))
    window, n_train, n_eval = window_split

    return_key = "return_bps" if return_unit == "bps" else "return_fraction"
    candidate_rows = [
        {"timestamp": ts, return_key: float(candidate_returns[ts])} for ts in aligned
    ]
    factor_rows = [
        {
            "timestamp": ts,
            **{factor: float(factor_returns[ts][factor]) for factor in required_factors},
        }
        for ts in aligned
    ]

    protocol = ResidualAlphaProtocol(
        fit_window=window,
        required_factors=required_factors,
        return_unit=return_unit,
        min_coverage=min_coverage,
        min_train_observations=min_train_observations,
        min_eval_observations=min_eval_observations,
        min_r_beta_retention=min_r_beta_retention,
        max_beta_edge_share=max_beta_edge_share,
        min_psr=min_psr,
        min_dsr=min_dsr,
        max_pbo=max_pbo,
        n_trials=n_trials,
        psr_benchmark_bps=psr_benchmark_bps,
        candidate_oos_returns=peer_oos_returns,
        # Gap C 接線（行為中性）：預設 permutation_enabled=False → 與既有 caller
        # 完全一致（不算 perm、to_dict 不帶 perm 欄位、hash byte-identical）。只有
        # Stage-0R orchestrator 透過 evaluate_cell ``**gate_kwargs`` 顯式傳
        # permutation_enabled=True 才啟用 model-free null。permutation_seed=None
        # 時由 gate 從 factor_panel_hash 衍生確定性 seed（hash 穩定、可重現）。
        permutation_enabled=permutation_enabled,
        permutation_n=permutation_n,
        permutation_seed=permutation_seed,
        max_perm_p_value=max_perm_p_value,
    )

    report = ResidualAlphaGate().evaluate(candidate_rows, factor_rows, protocol)
    report_dict = report.to_dict()
    ok, reason = validate_demo_residual_alpha_report(report_dict)
    return ResidualAlphaProducerResult(
        report=report_dict,
        promotion_ready=ok,
        reason=reason,
        aligned_observations=len(aligned),
        train_observations=n_train,
        eval_observations=n_eval,
    )


def _aligned_timestamps(
    candidate_returns: Mapping[Hashable, Any],
    factor_returns: Mapping[Hashable, Mapping[str, Any]],
    required_factors: Sequence[str],
) -> list[Hashable]:
    """leak-free 對齊：candidate 與 factor 同時存在、值皆 finite、factor 含全部
    required factor 的 timestamp，依時間排序回傳。"""
    if not isinstance(candidate_returns, Mapping) or not isinstance(factor_returns, Mapping):
        return []
    aligned: list[Hashable] = []
    for ts, raw in candidate_returns.items():
        if _finite(raw) is None:
            continue
        factor_row = factor_returns.get(ts)
        if not isinstance(factor_row, Mapping):
            continue
        if any(_finite(factor_row.get(factor)) is None for factor in required_factors):
            continue
        aligned.append(ts)
    try:
        aligned.sort()
    except TypeError:
        # timestamp 不可比較 → 無法切時間窗 → 視為不可用
        return []
    return aligned


def _build_fit_window(
    aligned: Sequence[Hashable], train_fraction: float, embargo_gap: float
) -> tuple[ResidualAlphaFitWindow, int, int] | None:
    """把排序後對齊樣本切成 train（前）/ eval（後），保證 train_end < eval_start。

    embargo_gap > 0 時，purge 掉 eval_start 前 embargo_gap（同 ts 單位）內的
    train-tail 觀測：避免 train obs 的前瞻/持倉窗與 eval obs 重疊造成滲漏
    （Lopez de Prado purge+embargo）。被 purge 的 ts 落在 (train_end, eval_start)
    之間，天然不在 gate 的 fit-scope 內，故 caller 仍可整批傳入。ts 不可做數值
    相減時跳過 embargo（回退純時間切分）。
    """
    n = len(aligned)
    if n < 2:
        return None
    n_train = int(math.floor(train_fraction * n))
    n_train = max(1, min(n_train, n - 1))  # 至少 1 train、至少 1 eval
    eval_ts = list(aligned[n_train:])
    eval_start = eval_ts[0]
    train_ts = list(aligned[:n_train])
    if embargo_gap > 0.0:
        try:
            cutoff = eval_start - embargo_gap  # type: ignore[operator]
            train_ts = [ts for ts in train_ts if ts <= cutoff]
        except TypeError:
            pass  # ts 不可數值相減 → 跳過 embargo
    if not train_ts or not eval_ts:
        return None
    window = ResidualAlphaFitWindow(
        train_start=train_ts[0],
        train_end=train_ts[-1],
        eval_start=eval_start,
        eval_end=eval_ts[-1],
        label="producer_time_split",
    )
    return window, len(train_ts), len(eval_ts)


def _insufficient_result(aligned_count: int) -> ResidualAlphaProducerResult:
    """對齊樣本不足以切窗：回 fail-closed defer report（不得偽 pass）。"""
    report: dict[str, Any] = {
        "passes": False,
        "verdict": "defer_data",
        "reasons": ("producer_insufficient_aligned_observations",),
        "raw_mean_bps": 0.0,
        "residual_mean_bps": 0.0,
        "aligned_observations": aligned_count,
    }
    return ResidualAlphaProducerResult(
        report=report,
        promotion_ready=False,
        reason="passes_not_true",
        aligned_observations=aligned_count,
        train_observations=0,
        eval_observations=0,
    )


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


__all__ = [
    "ResidualAlphaProducerResult",
    "build_residual_alpha_report",
]
