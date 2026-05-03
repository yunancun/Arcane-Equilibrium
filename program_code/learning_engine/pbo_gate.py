"""pbo_gate — REF-20 Wave 6 P4-Q2 Probability of Backtest Overfitting (CSCV).

PBO < 0.5 gate — REF-20 Wave 6 P4-Q2 回測過擬合機率（CSCV）。

MODULE_NOTE (EN): Implements Bailey, Borwein, Lopez de Prado, Zhu (2014)
  Combinatorially Symmetric Cross-Validation (CSCV) framework to compute
  Probability of Backtest Overfitting (PBO). The procedure:

    1. Split T observations into S even sub-slices (S even, default 16).
    2. Enumerate all C(S, S/2) combinations of "in-sample" / "out-of-sample"
       partitions where each partition is symmetric (equal half-and-half).
    3. For each combination, rank candidates by IS Sharpe; record OOS rank
       of best-IS candidate.
    4. Compute logit transform of OOS rank; PBO = P(logit < 0) =
       P(best IS candidate has below-median OOS rank).

  PBO < 0.5 means selecting on IS Sharpe still yields above-median OOS rank
  more often than not. PBO ≥ 0.5 means selection is uninformative/harmful.

  Pure-math IMPL: 0 IPC / 0 DB / 0 exchange. Hand-rolled CSCV (no scipy
  dependency for combinatorial enumeration). Output feeds
  `replay_routes.generate_handoff_verdict` advisory verdict layer.

MODULE_NOTE (中): 實作 Bailey, Borwein, Lopez de Prado, Zhu (2014) 組合對稱
  交叉驗證（CSCV）框架，計算回測過擬合機率（PBO）。流程：

    1. 將 T 個觀察分為 S 個均等子切片（S 偶，預設 16）。
    2. 列舉所有 C(S, S/2) 組「樣本內 / 樣本外」分區，每分區對稱（均半半）。
    3. 對每組合，依樣本內 Sharpe 排序候選；記錄樣本內最佳之樣本外 rank。
    4. 計算樣本外 rank 的 logit 變換；PBO = P(logit < 0) =
       P(樣本內最佳候選之樣本外 rank 低於中位數)。

  PBO < 0.5 表示依樣本內 Sharpe 選擇仍多數時間產出高於中位數的樣本外 rank。
  PBO ≥ 0.5 表示選擇無資訊或有害。

  純數學 IMPL：0 IPC / 0 DB / 0 exchange。手寫 CSCV（避免 scipy 依賴）。
  輸出餵 `replay_routes.generate_handoff_verdict` advisory verdict 層。

V3 §8.3 + §11 P4 + §12 #17 binding / V3 綁定:
  - "PBO < 0.5 when K >= 10 and total trades >= 320" (§8.3)
  - "DSR(K)>0.95 + PBO<0.5 (K>=10) + power gate enforced" (§12 #17)
  - "if PBO cannot run because power insufficient → verdict `defer_data`" (§8.3)

Reference / 參考:
  - Bailey, D. H., Borwein, J. M., Lopez de Prado, M. M., & Zhu, Q. J.
    (2014). The Probability of Backtest Overfitting. Journal of
    Computational Finance, 20(4), 39-69.

Wave 6 P4-Q2 scope (this commit):
  - PboGate class with compute_pbo() + gate() pure methods.
  - PboResult dataclass (pbo / n_splits / total_trades / median_oos_sharpe /
    passes_threshold).
  - 4 pytest cases: PBO=0.3 + sufficient → promote / PBO=0.6 → block /
    K=5 → block (insufficient n_splits) / total_trades=200 → block.

NOT in this scope:
  - replay_routes.py call-site wiring (separate sub-task).
  - DB INSERT replay.pbo_audit_log (P6 governance_audit_log subtask).
  - DSR(K) sibling gate (P4-Q1 → dsr_gate.py).
  - cost_edge_ratio gate (P4-Q6 → cost_edge_advisor.py).

SPEC:
  - REF-20 V3 §8.3 (Selection Bias Controls)
  - REF-20 V3 §11 P4 Exit
  - REF-20 V3 §12 acceptance #17
Workplan: docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 R20-P4-Q2
"""

from __future__ import annotations

import itertools
import logging
import math
from dataclasses import dataclass
from typing import Literal, Sequence

import numpy as np


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# V3 §8.3 / §11 P4 thresholds / V3 閾值常數
# ─────────────────────────────────────────────────────────────────────────────

# PBO < 0.5 promotion threshold.
# PBO < 0.5 升級閾值。
DEFAULT_PBO_THRESHOLD: float = 0.5

# Minimum K (n_splits / equiv combinations) per V3 §8.3.
# 最小 K（n_splits / 等效組合數）依 V3 §8.3。
DEFAULT_MIN_K: int = 10

# Minimum total trades across all splits per V3 §8.3.
# 全 splits 跨累計最小 trades 數依 V3 §8.3。
DEFAULT_MIN_TOTAL_TRADES: int = 320

# Default S = number of sub-slices for CSCV (workplan §4 Q2 spec).
# Default S = CSCV 子切片數（workplan §4 Q2 規格）。
DEFAULT_S_SLICES: int = 16


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass / 結果 dataclass
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class PboResult:
    """PBO computation result via CSCV.

    透過 CSCV 計算 PBO 之結果。

    Attributes / 屬性:
        pbo: Probability of Backtest Overfitting in [0, 1]. /
             回測過擬合機率，範圍 [0, 1]。
        n_splits: Number of CSCV combinations evaluated. /
                  評估的 CSCV 組合數。
        total_trades: Total trades across all splits + candidates. /
                      跨全 splits + candidates 之累計 trades 數。
        median_oos_sharpe: Median OOS Sharpe of best-IS candidate across splits. /
                           跨 splits 之樣本內最佳候選的樣本外 Sharpe 中位數。
        passes_threshold: True if PBO < threshold AND n_splits >= min_K
                          AND total_trades >= min_total_trades. /
                          當 PBO < 閾值 AND n_splits >= min_K AND
                          total_trades >= min_total_trades 時為 True。
        insufficient_power: True if n_splits or total_trades below threshold. /
                            n_splits 或 total_trades 低於閾值時為 True。
    """

    pbo: float
    n_splits: int
    total_trades: int
    median_oos_sharpe: float
    passes_threshold: bool
    insufficient_power: bool


# ─────────────────────────────────────────────────────────────────────────────
# Math helpers / 數學輔助
# ─────────────────────────────────────────────────────────────────────────────


def _compute_sharpe(returns: np.ndarray) -> float:
    """Compute Sharpe ratio (mean / std).

    計算 Sharpe 比率（均值 / 標準差）。

    Returns 0.0 if std == 0 (degenerate constant return series), or if
    returns array is empty.
    當 std == 0（退化常數報酬序列）或 returns 為空時回 0.0。

    Note / 註: For PBO, absolute Sharpe magnitude doesn't matter — only
    relative ranking across candidates within the same split. So we
    return raw mean/std without annualization.
    對 PBO 而言，Sharpe 絕對量級不重要 — 僅關注同一 split 內候選之相對 rank。
    故回原始 mean/std 不年化。
    """
    if len(returns) == 0:
        return 0.0
    mu = float(np.mean(returns))
    sigma = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
    if sigma == 0.0:
        return 0.0
    return mu / sigma


def _logit(rank_prob: float) -> float:
    """Logit transform: log(p / (1 - p)).

    Logit 變換：log(p / (1 - p))。

    Caps at p ∈ [eps, 1-eps] to avoid ±inf at boundaries.
    對 p 限制在 [eps, 1-eps] 內以避免邊界 ±inf。
    """
    eps = 1e-12
    p = max(eps, min(1.0 - eps, float(rank_prob)))
    return math.log(p / (1.0 - p))


# ─────────────────────────────────────────────────────────────────────────────
# CSCV core / CSCV 核心
# ─────────────────────────────────────────────────────────────────────────────


def _build_returns_matrix(
    oos_returns_per_split: Sequence[np.ndarray],
) -> np.ndarray:
    """Stack per-split OOS returns into a uniform matrix (truncate to min len).

    將每 split 的樣本外 returns 堆疊為均勻矩陣（截至最短長度）。

    Args / 引數:
        oos_returns_per_split: List of N candidate return series, each
            series length T_i. We treat each "candidate" as an entry. /
            N 個候選報酬序列。

    Returns / 回傳:
        2-D ndarray of shape (T_min, N_candidates). /
        形狀 (T_min, N_candidates) 之 2-D ndarray。

    Note / 註: CSCV requires aligned timestamps across candidates. Caller
    must ensure series are temporally aligned (same trade/period index).
    Caller 必須保證序列時間對齊。
    """
    if len(oos_returns_per_split) == 0:
        return np.zeros((0, 0))
    arrays = [np.asarray(s, dtype=np.float64).flatten() for s in oos_returns_per_split]
    min_len = min(len(a) for a in arrays)
    if min_len == 0:
        return np.zeros((0, len(arrays)))
    truncated = [a[:min_len] for a in arrays]
    return np.column_stack(truncated)


def _cscv_pbo(
    matrix: np.ndarray,
    s_slices: int,
) -> tuple[float, int, float]:
    """Run CSCV on returns matrix → return (pbo, n_combinations, median_oos_sharpe).

    在 returns 矩陣上執行 CSCV → 回 (pbo, n_combinations, median_oos_sharpe)。

    Algorithm / 演算法 (Bailey-Borwein-LdP-Zhu 2014):
      1. Divide T rows into S equal slices (S even).
      2. For each combination C(S, S/2) of S/2 slices as IS, rest as OOS:
         - Rank candidates by IS Sharpe.
         - Find best-IS candidate; record its OOS rank.
         - Compute logit of (1 - OOS_rank/(N-1)).
      3. PBO = fraction of combinations with logit < 0.

    Args / 引數:
        matrix: (T, N) returns matrix.
        s_slices: number of slices S; must be even.

    Returns / 回傳:
        (pbo, n_combinations, median_oos_sharpe).

    Raises / 拋出:
        ValueError: invalid S or insufficient data.
    """
    T, N = matrix.shape
    if N < 2:
        raise ValueError(f"need >=2 candidates for ranking; got N={N}")
    if s_slices < 2 or s_slices % 2 != 0:
        raise ValueError(f"s_slices={s_slices} must be even and >= 2")
    if T < s_slices:
        raise ValueError(
            f"T={T} too few observations for s_slices={s_slices}"
        )

    # Step 1: Divide T rows into S near-equal slices.
    # 步驟 1：將 T 行分為 S 個近均等切片。
    slice_size = T // s_slices
    slices = [
        matrix[i * slice_size : (i + 1) * slice_size, :]
        for i in range(s_slices)
    ]

    # Step 2: Enumerate all C(S, S/2) IS partitions.
    # 步驟 2：列舉所有 C(S, S/2) 樣本內分區。
    half = s_slices // 2
    all_indices = list(range(s_slices))
    is_combinations = list(itertools.combinations(all_indices, half))
    n_combinations = len(is_combinations)

    logits: list[float] = []
    oos_sharpes_of_winners: list[float] = []

    for is_indices in is_combinations:
        oos_indices = tuple(i for i in all_indices if i not in is_indices)

        # Concatenate IS / OOS rows.
        # 串接樣本內 / 樣本外行。
        is_data = np.vstack([slices[i] for i in is_indices])
        oos_data = np.vstack([slices[i] for i in oos_indices])

        # Rank candidates by IS Sharpe.
        # 依樣本內 Sharpe 排序候選。
        is_sharpes = np.array(
            [_compute_sharpe(is_data[:, j]) for j in range(N)]
        )
        oos_sharpes = np.array(
            [_compute_sharpe(oos_data[:, j]) for j in range(N)]
        )

        best_is_idx = int(np.argmax(is_sharpes))

        # OOS rank of best-IS candidate (rank = position in OOS-sorted order).
        # 樣本內最佳之樣本外 rank。
        # rank: lower-rank = worse OOS performance; we want fraction of
        # OOS Sharpes that are <= winner's OOS Sharpe (higher = better).
        oos_winner = oos_sharpes[best_is_idx]
        # Fraction strictly less than winner (excluding winner itself).
        # 嚴格小於 winner 之比例（不含 winner 自身）。
        # 使用 (rank-1)/(N-1) style → rank_prob ∈ [0, 1].
        n_below = int(np.sum(oos_sharpes < oos_winner))
        rank_prob = float(n_below) / float(N - 1) if N > 1 else 0.5

        # Edge case: when winner ties with all others, rank_prob = 0 by above
        # → logit = -inf → PBO inflated. Use mean rank for ties.
        # 邊緣案例：當 winner 與所有其他並列時 rank_prob = 0 → logit = -inf。
        # 並列時用平均 rank。
        n_equal = int(np.sum(oos_sharpes == oos_winner))
        if n_equal > 1:
            rank_prob = (float(n_below) + 0.5 * float(n_equal - 1)) / float(N - 1)

        logits.append(_logit(rank_prob))
        oos_sharpes_of_winners.append(float(oos_winner))

    # Step 3: PBO = fraction of combinations with logit < 0.
    # 步驟 3：PBO = logit < 0 之組合比例。
    logits_arr = np.asarray(logits)
    pbo = float(np.mean(logits_arr < 0.0))

    median_oos_sharpe = float(np.median(oos_sharpes_of_winners)) if oos_sharpes_of_winners else 0.0

    return pbo, n_combinations, median_oos_sharpe


# ─────────────────────────────────────────────────────────────────────────────
# PBO Gate class / PBO Gate 類別
# ─────────────────────────────────────────────────────────────────────────────


class PboGate:
    """PBO < 0.5 gate per V3 §11 P4 Exit + §12 #17.

    依 V3 §11 P4 Exit + §12 #17 的 PBO < 0.5 gate。

    Composite gate that:
      1. Builds returns matrix from per-candidate OOS returns.
      2. Runs CSCV with S sub-slices.
      3. Compares PBO against threshold AND validates n_splits + total_trades.
      4. Returns 'promote' / 'block' verdict.

    複合 gate：
      1. 從候選樣本外 returns 構建矩陣。
      2. 用 S 個子切片執行 CSCV。
      3. 比較 PBO 對閾值 AND 驗證 n_splits + total_trades。
      4. 回 'promote' / 'block' 判決。

    Usage / 使用:
        gate = PboGate(threshold=0.5, min_K=10, min_total_trades=320)
        result = gate.compute_pbo(oos_returns_per_split=[r1, r2, r3, ...])
        verdict = gate.gate(result)  # 'promote' / 'block'
    """

    def __init__(
        self,
        threshold: float = DEFAULT_PBO_THRESHOLD,
        min_K: int = DEFAULT_MIN_K,
        min_total_trades: int = DEFAULT_MIN_TOTAL_TRADES,
        s_slices: int = DEFAULT_S_SLICES,
    ) -> None:
        """Initialize gate with configurable thresholds.

        以可配置閾值初始化 gate。

        Args / 引數:
            threshold: PBO must be < threshold for promotion (default 0.5). /
                       升級用 PBO 必 < 閾值（預設 0.5）。
            min_K: Minimum n_splits / combinations (default 10). /
                   最小 n_splits / 組合數（預設 10）。
            min_total_trades: Minimum total_trades across splits (default 320). /
                              跨 splits 之最小 total_trades（預設 320）。
            s_slices: CSCV sub-slices S (must be even, default 16). /
                      CSCV 子切片數 S（必偶，預設 16）。
        """
        if not 0.0 < threshold < 1.0:
            raise ValueError(f"threshold={threshold} must be in (0, 1)")
        if min_K < 2:
            raise ValueError(f"min_K={min_K} must be >= 2")
        if min_total_trades < 1:
            raise ValueError(f"min_total_trades={min_total_trades} must be >= 1")
        if s_slices < 2 or s_slices % 2 != 0:
            raise ValueError(f"s_slices={s_slices} must be even and >= 2")
        self.threshold = float(threshold)
        self.min_K = int(min_K)
        self.min_total_trades = int(min_total_trades)
        self.s_slices = int(s_slices)

    def compute_pbo(
        self,
        oos_returns_per_split: Sequence[np.ndarray],
    ) -> PboResult:
        """Compute PBO via CSCV given per-candidate OOS returns.

        給定每候選樣本外 returns 透過 CSCV 計算 PBO。

        Args / 引數:
            oos_returns_per_split: List of N candidate OOS return arrays
                (each of length T_i; will be truncated to min length). /
                N 個候選樣本外 returns 陣列（各長 T_i；將截至最短長度）。

        Returns / 回傳:
            PboResult with pbo / n_splits / total_trades /
            median_oos_sharpe / passes_threshold / insufficient_power.

        Raises / 拋出:
            ValueError: empty input or insufficient candidates.
        """
        if len(oos_returns_per_split) == 0:
            raise ValueError("oos_returns_per_split is empty")
        if len(oos_returns_per_split) < 2:
            raise ValueError(
                f"need >=2 candidates for CSCV ranking; got {len(oos_returns_per_split)}"
            )

        matrix = _build_returns_matrix(oos_returns_per_split)
        T, N = matrix.shape

        # Total trades = sum of all candidate fills (use total cells in matrix
        # as proxy; caller should pass actual fills/trades arrays where each
        # element is one trade outcome).
        # total_trades = N candidates × T trades each.
        total_trades = int(T * N)

        # Try CSCV; if T too small for s_slices, fall back gracefully.
        # 試執行 CSCV；若 T 不夠則優雅 fallback。
        if T < self.s_slices:
            logger.warning(
                "T=%s < s_slices=%s; PBO insufficient power",
                T, self.s_slices,
            )
            return PboResult(
                pbo=float("nan"),
                n_splits=0,
                total_trades=total_trades,
                median_oos_sharpe=0.0,
                passes_threshold=False,
                insufficient_power=True,
            )

        pbo, n_combinations, median_oos = _cscv_pbo(matrix, self.s_slices)

        insufficient = (
            n_combinations < self.min_K or total_trades < self.min_total_trades
        )
        passes = (
            (pbo < self.threshold)
            and (n_combinations >= self.min_K)
            and (total_trades >= self.min_total_trades)
        )

        return PboResult(
            pbo=float(pbo),
            n_splits=int(n_combinations),
            total_trades=int(total_trades),
            median_oos_sharpe=float(median_oos),
            passes_threshold=bool(passes),
            insufficient_power=bool(insufficient),
        )

    def gate(self, pbo_result: PboResult) -> Literal["promote", "block"]:
        """Decide verdict from PboResult.

        從 PboResult 決定判決。

        Verdict / 判決:
          - passes_threshold = True → 'promote'
          - else → 'block' (caller should map insufficient_power → 'defer_data'
            verdict at replay_routes layer per V3 §8.3)

        passes_threshold = True → 'promote'；否則 'block'。
        Caller 應在 replay_routes 層將 insufficient_power 映射為 'defer_data'
        verdict（依 V3 §8.3）。
        """
        if pbo_result.passes_threshold:
            return "promote"
        return "block"


# ─────────────────────────────────────────────────────────────────────────────
# Module-level convenience / 模組級便利函數
# ─────────────────────────────────────────────────────────────────────────────


def compute_pbo(
    oos_returns_per_split: Sequence[np.ndarray],
    threshold: float = DEFAULT_PBO_THRESHOLD,
    min_K: int = DEFAULT_MIN_K,
    min_total_trades: int = DEFAULT_MIN_TOTAL_TRADES,
    s_slices: int = DEFAULT_S_SLICES,
) -> PboResult:
    """Module-level shortcut for PboGate.compute_pbo.

    PboGate.compute_pbo 的模組級捷徑。
    """
    return PboGate(
        threshold=threshold,
        min_K=min_K,
        min_total_trades=min_total_trades,
        s_slices=s_slices,
    ).compute_pbo(oos_returns_per_split)
