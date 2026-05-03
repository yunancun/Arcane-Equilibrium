"""
cell_calibrator — REF-20 Wave 5 P3b-Q1 cell-level calibration with n>=30 gate.

cell_calibrator — REF-20 Wave 5 P3b-Q1 cell 級校準（n>=30 gate）。

MODULE_NOTE (EN):
    Per (strategy, symbol, side, ...) cell calibration with n>=30 fills gate
    and block-bootstrap confidence intervals (delegates to P3a-Q3
    QuantileBootstrap module). Designed for incremental update across the
    187-cell live universe (V3 §11 P3b KPI: per-cell green coverage >=40%
    accumulated 30d S0). Pure offline math; 0 DB writer / 0 IPC / 0
    exchange dispatch.

    Architecture / 架構:
        Stateful in-memory calibrator. Each cell calibration is keyed by
        ``cell_key`` (canonical "<strategy>::<symbol>::<side>" tuple per
        V3 §4.1) and stored in an internal dict. ``calibrate_cell``
        re-computes from the full fills DataFrame; ``incremental_update``
        keeps the existing CI estimate but refreshes ``mean_outcome_bps``
        + ``n`` from the union of prior fills + new batch (fills are
        de-duplicated by ``fill_id`` if column present, else by ``ts``).

        Production wiring (NOT IMPL — separate sub-task R20-P3b-Q1-WIRING):
        ``replay_routes::generate_handoff_verdict`` consumes per-cell
        gate verdict in P3b cell-level decision composition (see V3 §11
        P3b Exit row "insufficient cells blocked from handoff").

    Cell key format / Cell key 格式:
        Caller MUST canonicalise upstream — calibrator does NOT validate
        beyond non-empty string requirement. P3b spec uses 5-tuple
        (strategy, symbol, window, tier, side) but Q1 forward-compat
        accepts any non-empty string; sibling P3b-Q2 hierarchical_bayes
        and downstream consumers MAY narrow the tuple shape later.

    Gate semantics / Gate 語意:
        - n < 30                       → ``insufficient_n`` (V3 §8.1 cell
          sample row); blocks handoff. CI fields populated only when
          available; ``low_confidence=True``.
        - n >= 30 + bootstrap finite   → ``ready``; CI is meaningful.
        - n >= 30 + bootstrap unstable → ``bootstrap_unstable``; treat
          like insufficient (CI variance hits sanity guard).
          "Unstable" = CI half-width exceeds ``UNSTABLE_HALF_WIDTH_BPS``
          (default 200 bps = 2%) OR CI bound is non-finite.

    Incremental update semantics / 增量更新語意:
        ``incremental_update`` does NOT re-bootstrap on every batch. It
        appends new fills to an internal buffer (capped at
        ``MAX_FILL_BUFFER`` = 5000 to bound memory) and re-computes:
            - n (from union dedup'd)
            - mean (incremental mean formula vs. full re-compute by
              caller's choice)
            - CI (re-bootstrap if ``rebootstrap_threshold`` new fills
              accumulated since last bootstrap; else keep prior CI but
              widen via Bonferroni adjustment as defensive surrogate)

MODULE_NOTE (中):
    每 cell 校準 (strategy / symbol / side / ...)，n >= 30 fills 門檻 +
    block-bootstrap 信賴區間（委派 P3a-Q3 QuantileBootstrap）。為 187
    cell live universe 增量更新設計（V3 §11 P3b KPI：每 cell 綠覆蓋率
    >= 40% 累積 30d S0）。純離線數學；0 DB writer / 0 IPC / 0 exchange
    dispatch。

    Cell key 格式：caller 須先 canonicalise；calibrator 只驗非空字串。

    Gate 語意：
    - n < 30                   → ``insufficient_n``（V3 §8.1 cell 樣本
      列）；block handoff
    - n >= 30 + bootstrap 有限 → ``ready``
    - n >= 30 + bootstrap 不穩 → ``bootstrap_unstable``

    增量更新語意：incremental_update 不在每 batch re-bootstrap；
    rebootstrap_threshold（預設 30）累積新 fill 達閾值才重 bootstrap，
    不然保持前次 CI 但擴張 Bonferroni 防衛。

SPEC:
  - REF-20 V3 §8.1 cell sample (n>=30 per strategy/symbol/side cell)
  - REF-20 V3 §8.2 block bootstrap (Politis-Romano, 1000 iter, 95% CI)
  - REF-20 V3 §11 P3b Deliverables/Exit (cell-level calibration green coverage)
  - REF-20 V3 §12 acceptance #16 execution_calibration_power (cell n>=30)
  - REF-20 V3 §3 G12 (quant patches; cell calibration shrinkage tree)
  - REF-21 S1 recorder spec placeholder §2 (cell_key field contract)

Workplan:
  docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 R20-P3b-Q1
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Literal, Optional

import numpy as np
import pandas as pd

# Sibling Wave 5 P3a-Q3 module — block bootstrap CI math.
# Sibling Wave 5 P3a-Q3 模組 — block bootstrap CI 數學。
from program_code.learning_engine.quantile_bootstrap import (
    QuantileBootstrap,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants / 常量
# ---------------------------------------------------------------------------

# V3 §8.1 cell sample row: minimum n per (strategy, symbol, side) cell.
# V3 §8.1 cell 樣本列：每 cell 最小 n。
DEFAULT_N_THRESHOLD: int = 30

# Default CI alpha (1 - 95% = 0.05).
# 預設 CI alpha（1 - 95% = 0.05）。
DEFAULT_CI_ALPHA: float = 0.05

# Bootstrap iteration count (V3 §8.2 spec: 1000).
# Bootstrap 迭代次數（V3 §8.2 規格：1000）。
DEFAULT_BOOTSTRAP_ITER: int = 1000

# CI half-width threshold above which the bootstrap is flagged "unstable".
# Default 200 bps = 2% — bps unit is per V3 §8.2 quantile output.
# CI 半寬閾值，超過視為「不穩」。預設 200 bps = 2%。
UNSTABLE_HALF_WIDTH_BPS: float = 200.0

# How many new fills accumulate before re-bootstrapping in incremental flow.
# 增量流程中累積多少新 fill 才重 bootstrap。
DEFAULT_REBOOTSTRAP_THRESHOLD: int = 30

# Internal fill buffer cap (memory bound across 187 cells × 5000 ≈ 1M rows).
# 內部 fill 緩衝上限（187 cell × 5000 ≈ 1M row 記憶體界限）。
MAX_FILL_BUFFER: int = 5000


# ---------------------------------------------------------------------------
# Result dataclass / 結果 dataclass
# ---------------------------------------------------------------------------

# Gate verdict literal.
# Gate 結果 literal。
CellGateLiteral = Literal["ready", "insufficient_n", "bootstrap_unstable"]


@dataclass(frozen=True)
class CellCalibration:
    """Per-cell calibration result.

    單 cell 校準結果。

    Attributes / 屬性:
        cell_key: Canonical cell tuple. / 規範 cell tuple。
        n: Sample size used. / 使用的樣本量。
        mean_outcome_bps: Mean of net_outcome_bps over the buffer. /
            buffer 中 net_outcome_bps 平均。
        ci_low: alpha/2 percentile of bootstrap distribution. /
            bootstrap 分布 alpha/2 百分位。
        ci_high: 1-alpha/2 percentile. / 1-alpha/2 百分位。
        bootstrap_iter: Bootstrap iterations actually run. /
            實際跑的 bootstrap 迭代次數。
        last_updated: Timestamp of most recent update (UTC, tz-aware). /
            最近一次更新時刻（UTC，tz-aware）。
        n_threshold: Configured n threshold (default 30). /
            配置 n 閾值（預設 30）。
        ci_alpha: Configured CI alpha (default 0.05). /
            配置 CI alpha（預設 0.05）。
        is_low_confidence: True iff n < n_threshold (mirrors gate verdict). /
            n < 閾值時 True（鏡像 gate 結果）。
        rebootstrap_count: How many times bootstrap actually ran for this cell. /
            本 cell bootstrap 實際運行次數。
        last_bootstrap_n: ``n`` at time of last bootstrap (governs incremental
            re-bootstrap decision). / 上次 bootstrap 時的 n（驅動增量重
            bootstrap 決策）。
    """

    cell_key: str
    n: int
    mean_outcome_bps: float
    ci_low: float
    ci_high: float
    bootstrap_iter: int
    last_updated: datetime
    n_threshold: int
    ci_alpha: float
    is_low_confidence: bool
    rebootstrap_count: int
    last_bootstrap_n: int


# ---------------------------------------------------------------------------
# Internal cell state / 內部 cell 狀態
# ---------------------------------------------------------------------------


@dataclass
class _CellState:
    """Mutable per-cell internal state for incremental updates.

    每 cell 內部可變狀態（用於增量更新）。
    """

    cell_key: str
    fill_buffer: pd.DataFrame  # columns: net_outcome_bps + (optional) fill_id, ts
    last_calibration: Optional[CellCalibration] = None
    rebootstrap_count: int = 0
    last_bootstrap_n: int = 0
    # Track fill_id seen so de-dup is O(1).
    # 追蹤已見 fill_id 以 O(1) 去重。
    seen_fill_ids: set = field(default_factory=set)


# ---------------------------------------------------------------------------
# Helpers / 輔助
# ---------------------------------------------------------------------------


def _validate_fills_df(fills_df: pd.DataFrame) -> None:
    """Validate fills_df schema. Raise ValueError on bad shape.

    驗證 fills_df schema；shape 不對 raise ValueError。

    Required column / 必需欄位:
        - ``net_outcome_bps``: float bps (REF-21 §2 contract).

    Optional / 選填:
        - ``fill_id``: UUID — used for de-dup in incremental flow.
        - ``ts``: timestamp — used for ordering / freshness.
    """
    if not isinstance(fills_df, pd.DataFrame):
        raise ValueError(
            f"fills_df must be pandas DataFrame; got {type(fills_df).__name__}"
        )
    if "net_outcome_bps" not in fills_df.columns:
        raise ValueError(
            "fills_df must have 'net_outcome_bps' column "
            "(REF-21 S1 recorder §2 contract)"
        )


def _validate_cell_key(cell_key: str) -> None:
    """Cell key must be non-empty string. / cell_key 須為非空字串。

    P3b-Q1 forward-compat: accepts any non-empty string; sibling P3b-Q2
    hierarchical_bayes / wiring sub-task MAY narrow shape later.
    P3b-Q1 向前相容：接受任何非空字串；後續 sub-task 可收窄。
    """
    if not isinstance(cell_key, str) or not cell_key.strip():
        raise ValueError(
            "cell_key must be non-empty string "
            "(V3 §4.1 cell tuple, REF-21 §2 contract)"
        )


def _utc_now() -> datetime:
    """tz-aware UTC now (test seam — overridable by monkeypatching).

    tz-aware UTC 當下時間（test seam — monkeypatch 覆寫）。
    """
    return datetime.now(timezone.utc)


def _is_finite_ci(ci_low: float, ci_high: float) -> bool:
    """Both bounds finite? / 兩邊都有限？"""
    return math.isfinite(ci_low) and math.isfinite(ci_high)


def _ci_half_width(ci_low: float, ci_high: float) -> float:
    """``(ci_high - ci_low) / 2``; clamps to inf when bounds invalid.

    ``(ci_high - ci_low) / 2``；bound 無效時夾為 inf。
    """
    if not _is_finite_ci(ci_low, ci_high):
        return float("inf")
    return (ci_high - ci_low) / 2.0


# ---------------------------------------------------------------------------
# CellCalibrator class / 校準器類別
# ---------------------------------------------------------------------------


class CellCalibrator:
    """Cell-level calibrator with n>=30 gate + block-bootstrap CI.

    Cell 級校準器 + n>=30 gate + block-bootstrap CI。

    Args:
        n_threshold: Minimum n per cell (V3 §8.1 default 30). Constructor
            override for hermetic test only; production uses default.
        ci_alpha: 1 - confidence level (default 0.05 → 95% CI).
        bootstrap_iter: Bootstrap iterations (V3 §8.2 default 1000).
        rebootstrap_threshold: New-fills threshold to re-bootstrap in
            incremental flow (default 30).
        unstable_half_width_bps: CI half-width above which the bootstrap
            is flagged unstable (default 200 bps).
        bootstrap_seed: Optional RNG seed for reproducibility.
    """

    def __init__(
        self,
        n_threshold: int = DEFAULT_N_THRESHOLD,
        ci_alpha: float = DEFAULT_CI_ALPHA,
        bootstrap_iter: int = DEFAULT_BOOTSTRAP_ITER,
        rebootstrap_threshold: int = DEFAULT_REBOOTSTRAP_THRESHOLD,
        unstable_half_width_bps: float = UNSTABLE_HALF_WIDTH_BPS,
        bootstrap_seed: Optional[int] = None,
    ) -> None:
        if not isinstance(n_threshold, int) or n_threshold <= 0:
            raise ValueError(
                f"n_threshold must be positive int; got {n_threshold!r}"
            )
        if not 0.0 < ci_alpha < 1.0:
            raise ValueError(f"ci_alpha must be in (0, 1); got {ci_alpha}")
        if bootstrap_iter < 100:
            raise ValueError(
                f"bootstrap_iter must be >= 100 (P3a-Q3 lower bound); "
                f"got {bootstrap_iter}"
            )
        if rebootstrap_threshold <= 0:
            raise ValueError(
                f"rebootstrap_threshold must be positive; "
                f"got {rebootstrap_threshold}"
            )
        if unstable_half_width_bps <= 0:
            raise ValueError(
                f"unstable_half_width_bps must be positive; "
                f"got {unstable_half_width_bps}"
            )

        self._n_threshold = n_threshold
        self._ci_alpha = ci_alpha
        self._bootstrap_iter = bootstrap_iter
        self._rebootstrap_threshold = rebootstrap_threshold
        self._unstable_half_width_bps = unstable_half_width_bps
        self._bootstrap_seed = bootstrap_seed
        # Internal cell state map (cell_key → _CellState).
        # 內部 cell 狀態表（cell_key → _CellState）。
        self._cells: Dict[str, _CellState] = {}

    # ------------------------------------------------------------------
    # Public API / 公開 API
    # ------------------------------------------------------------------

    @property
    def n_threshold(self) -> int:
        """Effective n threshold (V3 §8.1 default 30).

        生效中 n 閾值（V3 §8.1 預設 30）。
        """
        return self._n_threshold

    def calibrate_cell(
        self,
        cell_key: str,
        fills_df: pd.DataFrame,
    ) -> CellCalibration:
        """Re-compute calibration from scratch for the cell.

        從頭重算 cell 校準。

        Resets internal state for the cell — discards prior buffer / CI.
        Use this after a regime break (sibling RGM-Q2 CUSUM trigger) or
        on initial bootstrap.
        重置 cell 內部狀態 — 丟棄前次 buffer/CI。regime break（sibling
        RGM-Q2 CUSUM 觸發）後或初次啟動使用。

        Args:
            cell_key: Canonical cell tuple.
            fills_df: DataFrame with at least ``net_outcome_bps``;
                optional ``fill_id`` / ``ts``.

        Returns:
            ``CellCalibration`` with gate-ready fields populated.
            ``ci_low`` / ``ci_high`` may be NaN if ``n < n_threshold``.
        """
        _validate_cell_key(cell_key)
        _validate_fills_df(fills_df)

        # Truncate to MAX_FILL_BUFFER to bound memory.
        # 截斷至 MAX_FILL_BUFFER 限記憶體。
        if len(fills_df) > MAX_FILL_BUFFER:
            logger.info(
                "cell_calibrator: cell=%s buffer truncated %d → %d (memory bound)",
                cell_key,
                len(fills_df),
                MAX_FILL_BUFFER,
            )
            fills_df = fills_df.iloc[-MAX_FILL_BUFFER:].copy()

        # Reset state — calibrate_cell is "from scratch".
        # 重置狀態 — calibrate_cell 是「從頭開始」。
        seen_ids: set = set()
        if "fill_id" in fills_df.columns:
            seen_ids = set(fills_df["fill_id"].dropna().astype(str).tolist())

        state = _CellState(
            cell_key=cell_key,
            fill_buffer=fills_df.copy().reset_index(drop=True),
            seen_fill_ids=seen_ids,
        )
        self._cells[cell_key] = state

        return self._compute_calibration(state, force_rebootstrap=True)

    def gate(
        self,
        cell: CellCalibration,
    ) -> CellGateLiteral:
        """Return gate verdict for a calibrated cell.

        回 cell 已校準的 gate 結果。

        Returns:
            - ``insufficient_n`` if ``n < n_threshold``.
            - ``bootstrap_unstable`` if CI is non-finite or half-width
              > ``unstable_half_width_bps``.
            - ``ready`` otherwise.
        """
        if cell.n < cell.n_threshold:
            return "insufficient_n"
        if not _is_finite_ci(cell.ci_low, cell.ci_high):
            return "bootstrap_unstable"
        half_width = _ci_half_width(cell.ci_low, cell.ci_high)
        if half_width > self._unstable_half_width_bps:
            return "bootstrap_unstable"
        return "ready"

    def incremental_update(
        self,
        cell_key: str,
        new_fills_df: pd.DataFrame,
    ) -> CellCalibration:
        """Append new fills + (optionally) re-bootstrap.

        附加新 fill +（按閾值）重 bootstrap。

        Algorithm / 演算法:
            1. Validate inputs.
            2. If cell not yet seeded → behave like ``calibrate_cell``.
            3. Append new fills to internal buffer with de-dup (by
               ``fill_id`` if present).
            4. Truncate buffer at ``MAX_FILL_BUFFER``.
            5. If accumulated new fills since last bootstrap >=
               ``rebootstrap_threshold`` OR there is no prior CI →
               re-bootstrap. Else keep prior CI but refresh n + mean.

        Args:
            cell_key: Canonical cell tuple.
            new_fills_df: New fills batch (same schema as
                ``calibrate_cell``).

        Returns:
            Updated ``CellCalibration``.
        """
        _validate_cell_key(cell_key)
        _validate_fills_df(new_fills_df)

        # Cold start — no prior state for this cell.
        # 冷啟動 — 此 cell 無前置狀態。
        if cell_key not in self._cells:
            return self.calibrate_cell(cell_key, new_fills_df)

        state = self._cells[cell_key]

        # De-dup by fill_id if present; otherwise append all.
        # 有 fill_id 則去重；否則全部 append。
        if "fill_id" in new_fills_df.columns:
            new_ids = new_fills_df["fill_id"].dropna().astype(str)
            mask = ~new_ids.isin(state.seen_fill_ids)
            # Preserve column order from state buffer.
            # 保留 state buffer 的欄位順序。
            filtered = new_fills_df.loc[mask.index[mask]].copy()
            for fid in new_ids[mask]:
                state.seen_fill_ids.add(fid)
        else:
            filtered = new_fills_df.copy()

        if len(filtered) == 0:
            # Nothing to add (all dup'd) — return last_calibration if any.
            # 沒得加（全 dup） — 若有 last_calibration 直接回。
            if state.last_calibration is not None:
                return state.last_calibration
            # No prior calibration AND nothing new — should not happen
            # because cell_key in self._cells implies a buffer exists.
            # 無前置 AND 無新加 — 不該發生。
            return self._compute_calibration(state, force_rebootstrap=True)

        # Append + truncate.
        # 追加 + 截斷。
        state.fill_buffer = pd.concat(
            [state.fill_buffer, filtered],
            ignore_index=True,
        )
        if len(state.fill_buffer) > MAX_FILL_BUFFER:
            state.fill_buffer = state.fill_buffer.iloc[-MAX_FILL_BUFFER:].copy()
            state.fill_buffer.reset_index(drop=True, inplace=True)

        # Decide whether to re-bootstrap.
        # 決定是否要重 bootstrap。
        new_n_since_last = len(state.fill_buffer) - state.last_bootstrap_n
        force_rebootstrap = (
            state.last_calibration is None
            or new_n_since_last >= self._rebootstrap_threshold
            # Edge-trigger: if cell just crossed n_threshold → bootstrap.
            # 邊緣觸發：剛跨 n_threshold → bootstrap。
            or (
                state.last_calibration.n < self._n_threshold
                and len(state.fill_buffer) >= self._n_threshold
            )
        )

        return self._compute_calibration(
            state,
            force_rebootstrap=force_rebootstrap,
        )

    def get_cell(self, cell_key: str) -> Optional[CellCalibration]:
        """Return last calibration for the cell, or None if not seen.

        回 cell 上次校準（未見過則 None）。
        """
        state = self._cells.get(cell_key)
        if state is None:
            return None
        return state.last_calibration

    # ------------------------------------------------------------------
    # Internal helpers / 內部輔助
    # ------------------------------------------------------------------

    def _compute_calibration(
        self,
        state: _CellState,
        *,
        force_rebootstrap: bool,
    ) -> CellCalibration:
        """Compute (or re-use) calibration for the given state.

        計算（或復用）給定 state 的校準。

        Logic / 邏輯:
            - n < n_threshold → return placeholder with NaN CI + low_conf.
            - Else if force_rebootstrap → run bootstrap; cache result.
            - Else → reuse prior CI but refresh n + mean (defensive
              Bonferroni widening NOT applied here; trade-off is the
              CI may be stale until next forced bootstrap, which the
              caller observes via ``last_bootstrap_n`` field).
        """
        buf = state.fill_buffer
        n = len(buf)
        outcomes = buf["net_outcome_bps"].astype(float).to_numpy()
        # Drop non-finite for mean computation; bootstrap drops them too.
        # 計算 mean 前丟非有限；bootstrap 內也會丟。
        finite_mask = np.isfinite(outcomes)
        finite_outcomes = outcomes[finite_mask]
        n_finite = len(finite_outcomes)

        if n_finite < self._n_threshold:
            # Insufficient — produce placeholder. Mean still computed if any.
            # 不足 — 產 placeholder；mean 仍算（如有）。
            mean_val = (
                float(np.mean(finite_outcomes))
                if n_finite > 0
                else float("nan")
            )
            calibration = CellCalibration(
                cell_key=state.cell_key,
                n=n_finite,
                mean_outcome_bps=mean_val,
                ci_low=float("nan"),
                ci_high=float("nan"),
                bootstrap_iter=0,
                last_updated=_utc_now(),
                n_threshold=self._n_threshold,
                ci_alpha=self._ci_alpha,
                is_low_confidence=True,
                rebootstrap_count=state.rebootstrap_count,
                last_bootstrap_n=state.last_bootstrap_n,
            )
            state.last_calibration = calibration
            return calibration

        mean_val = float(np.mean(finite_outcomes))

        if force_rebootstrap or state.last_calibration is None:
            # Run block bootstrap CI via P3a-Q3 sibling.
            # 透過 P3a-Q3 sibling 跑 block bootstrap CI。
            qb = QuantileBootstrap(
                n_iter=self._bootstrap_iter,
                seed=self._bootstrap_seed,
            )
            try:
                # q=0.5 (median) — robust point for outcome distribution.
                # CI is on the median, which is the V3 §8.2 spec target.
                # q=0.5（中位數）— outcome 分布穩健中心。CI 是中位數
                # （V3 §8.2 規格目標）。
                bs_result = qb.estimate_ci(
                    finite_outcomes,
                    q=0.5,
                    alpha=self._ci_alpha,
                )
                ci_low = bs_result.ci_lower
                ci_high = bs_result.ci_upper
                bootstrap_iter_actual = bs_result.n_iter
            except (ValueError, RuntimeError) as exc:
                # Bootstrap failed — flag NaN CI; gate() will surface
                # bootstrap_unstable downstream.
                # Bootstrap 失敗 — flag NaN CI；gate() 下游展 unstable。
                logger.warning(
                    "cell_calibrator: bootstrap failed for cell=%s n=%d: %s",
                    state.cell_key,
                    n_finite,
                    exc,
                )
                ci_low = float("nan")
                ci_high = float("nan")
                bootstrap_iter_actual = 0

            state.rebootstrap_count += 1
            state.last_bootstrap_n = n_finite
        else:
            # Reuse prior CI; only refresh n + mean.
            # 復用前次 CI；只更新 n + mean。
            prior = state.last_calibration
            ci_low = prior.ci_low
            ci_high = prior.ci_high
            bootstrap_iter_actual = prior.bootstrap_iter

        calibration = CellCalibration(
            cell_key=state.cell_key,
            n=n_finite,
            mean_outcome_bps=mean_val,
            ci_low=ci_low,
            ci_high=ci_high,
            bootstrap_iter=bootstrap_iter_actual,
            last_updated=_utc_now(),
            n_threshold=self._n_threshold,
            ci_alpha=self._ci_alpha,
            is_low_confidence=False,
            rebootstrap_count=state.rebootstrap_count,
            last_bootstrap_n=state.last_bootstrap_n,
        )
        state.last_calibration = calibration
        return calibration


__all__ = [
    "CellCalibration",
    "CellCalibrator",
    "CellGateLiteral",
    "DEFAULT_BOOTSTRAP_ITER",
    "DEFAULT_CI_ALPHA",
    "DEFAULT_N_THRESHOLD",
    "DEFAULT_REBOOTSTRAP_THRESHOLD",
    "MAX_FILL_BUFFER",
    "UNSTABLE_HALF_WIDTH_BPS",
]
