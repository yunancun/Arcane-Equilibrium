"""
regime_controller — REF-20 Wave 5 RGM-Q1/Q2/Q3/Q4 cell regime state machine.

regime_controller — REF-20 Wave 5 RGM-Q1/Q2/Q3/Q4 cell regime 狀態機。

MODULE_NOTE (EN):
    Sequential state machine for V3 §8.4 Regime Controls. Layers four
    independent gates per cell:
        1. RGM-Q1: warmup (first 500 fills cannot drive handoff)
        2. RGM-Q2: CUSUM ±3σ break detection → freeze handoff (NOT model)
        3. RGM-Q3: Kupiec POF n>=250 cell-independent VaR backtest
        4. RGM-Q4: PSR(0)<0.95 across 3×250 rolling windows → refit + PM alert

    State semantics / 狀態語意:
        warmup → active → break → refit_pending → reactive

    Each method is independent — caller composes verdicts. The
    ``CompositeCellStatusLiteral`` widens with every Q to surface the
    most-restrictive state for downstream gating.

    Architecture / 架構:
        Pure-Python in-memory cell state machine. Zero DB writer / IPC /
        exchange dependency. Caller (Wave 5+ replay_routes hook or P3b
        cell_calibrator) feeds incoming fill counts; controller returns
        ``WarmupStatus`` indicating whether the cell is ready to drive
        actionable handoff or still warming up.

        Production acceptance requires the controller to be wired into
        ``replay_routes.py::generate_handoff_verdict`` (extends
        CalibrationGate.gate_handoff with regime check) — separate
        sub-task; this commit lands the math + interface only.

    Cell key format / Cell key 格式:
        ``"<strategy>::<symbol>::<side>"`` (canonical V3 §4.1 cell tuple).
        ``<side>`` ∈ {long, short}. Caller MUST canonicalise before
        invoking this module — controller does NOT validate the format
        beyond non-empty string requirement.

    Warmup gate semantics / Warmup gate 語意:
        - n_fills < 500       → ``ready=False``, ``remaining=500-n_fills``
        - n_fills >= 500      → ``ready=True``,  ``remaining=0``
        - 500 is V3 §8.4 #1 spec; ``warmup_threshold`` ctor param allows
          hermetic test override; production caller MUST use default.

    Why a base class for RGM-Q2/Q3/Q4 / 為什麼設成可擴展基類:
        Wave 5 RGM-Q2 (CUSUM ±3σ) needs to consume cell warmup status
        before deciding whether to act on a regime break. RGM-Q3
        (Kupiec POF) and RGM-Q4 (PSR(0)) similarly compose on top of
        warmup-gated cells. Keeping ``check_warmup`` + ``get_cell_status``
        as the canonical entry points avoids 4 separate consumers
        re-implementing the cell key + threshold contract.

MODULE_NOTE (中):
    V3 §8.4 Regime Controls 順序狀態機。每 cell 疊四層獨立 gate：
        1. RGM-Q1：warmup（首 500 fills 不可推 handoff）
        2. RGM-Q2：CUSUM ±3σ break 偵測 → freeze handoff（不 freeze model）
        3. RGM-Q3：Kupiec POF n>=250 cell 獨立 VaR backtest
        4. RGM-Q4：PSR(0)<0.95 across 3×250 滾動窗 → refit + PM alert

    狀態語意：warmup → active → break → refit_pending → reactive

    每方法獨立 — caller 組 verdict。CompositeCellStatusLiteral 隨每 Q
    widen 以揭最嚴狀態給下游 gate。

    架構：純 Python in-memory cell 狀態機，0 DB writer / IPC / exchange
    依賴。Caller（Wave 5+ replay_routes hook 或 P3b cell_calibrator）
    餵入 fill 數，controller 回 ``WarmupStatus``。

    Cell key 格式 = ``"<strategy>::<symbol>::<side>"``（V3 §4.1 規範
    cell tuple）。caller 必先 canonicalise；controller 不驗格式（僅驗
    非空字串）。

    Warmup gate 語意：n_fills < 500 → not ready；>= 500 → ready。500
    為 V3 §8.4 #1 規格；ctor 允許 hermetic test 覆寫；production 必用預設。

    為什麼設成可擴展基類：Wave 5 RGM-Q2/Q3/Q4 都要先驗 cell warmup
    再決定行動，將 ``check_warmup`` + ``get_cell_status`` 作為 canonical
    entry point 避免四個 consumer 各自重寫 cell key + 閾值契約。

SPEC:
  - REF-20 V3 §8.4 #1 (warmup phase 500 fills) → RGM-Q1
  - REF-20 V3 §8.4 #2 (CUSUM ±3σ break → freeze handoff) → RGM-Q2
  - REF-20 V3 §8.4 #3 (Kupiec POF n>=250 cell-independent) → RGM-Q3
  - REF-20 V3 §8.4 #4 (PSR(0)<0.95 across 3×250 windows + PM alert) → RGM-Q4
  - REF-20 V3 §3 G12 (quant patches; regime warmup 500 fills)
  - REF-20 V3 §11 P3b Exit (regime shift controls present)
  - REF-20 V3 §12 acceptance #18 (replay_regime_shift_gate)
Workplan:
  docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4
    R20-RGM-Q1 / Q2 / Q3 / Q4
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Sequence

import numpy as np

# Internal math helpers extracted to keep this file under the 1200-LOC
# hard cap (CLAUDE.md §七). Underscore prefix on module path signals
# "internal — do not import outside learning_engine".
# 內部數學輔助抽出，使本檔合 1200 LOC 硬上限（CLAUDE.md §七）。
# 模組路徑底線前綴示意「內部 — 不在 learning_engine 外 import」。
from program_code.learning_engine._regime_math import (
    cusum_statistic as _cusum_statistic,
    kupiec_lr_pof as _kupiec_lr_pof,
    psr_zero as _psr_zero,
    validate_returns as _validate_returns,
)


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# V3 §8.4 #1 threshold constant / V3 §8.4 #1 閾值常數
# ─────────────────────────────────────────────────────────────────────────────

# V3 §8.4 #1: First 500 fills after a negative-edge regime transition
# cannot drive handoff. This is the spec default; constructor allows
# hermetic test override.
# V3 §8.4 #1：負 edge regime transition 後首 500 fills 不可推 handoff。
# 規格預設；ctor 允許 hermetic test 覆寫。
WARMUP_FILLS_THRESHOLD: int = 500

# V3 §8.4 #2: CUSUM ±3σ break threshold (Z-score scale).
# V3 §8.4 #2：CUSUM ±3σ break 閾值（Z-score 尺度）。
CUSUM_SIGMA_THRESHOLD: float = 3.0

# V3 §8.4 #3: Kupiec POF minimum sample size per cell.
# V3 §8.4 #3：Kupiec POF 每 cell 最小樣本量。
KUPIEC_MIN_N: int = 250

# Kupiec p-value rejection threshold (V3 §8.4 #3 standard 5%).
# Kupiec p-value 拒絕閾值（V3 §8.4 #3 標準 5%）。
KUPIEC_P_VALUE_THRESHOLD: float = 0.05

# V3 §8.4 #4: PSR(0) threshold across 3 windows.
# V3 §8.4 #4：PSR(0) 跨 3 窗閾值。
PSR_THRESHOLD: float = 0.95

# V3 §8.4 #4: window size and number of windows.
# V3 §8.4 #4：窗大小與窗數。
PSR_WINDOW_SIZE: int = 250
PSR_NUM_WINDOWS: int = 3

# Combined required sample for PSR test (3×250 = 750).
# PSR 檢定所需總樣本（3×250 = 750）。
PSR_MIN_TOTAL_SAMPLES: int = PSR_WINDOW_SIZE * PSR_NUM_WINDOWS


# ─────────────────────────────────────────────────────────────────────────────
# Status literals / 狀態 literal
# ─────────────────────────────────────────────────────────────────────────────


# Per-cell warmup status literal (Q2/Q3/Q4 will extend the composite status).
# 單 cell warmup 狀態 literal（Q2/Q3/Q4 擴展複合狀態時加）。
WarmupStatusLiteral = Literal["warming_up", "ready"]


# Composite cell status literal — widened across Q1 (warmup) /
# Q2 (CUSUM break) / Q3 (Kupiec POF) / Q4 (PSR refit). Order from
# warming_up → ready → break → refit_pending → reactive forms the
# state-machine progression; severity decreases left-to-right *except*
# break/refit_pending which freeze handoff. Caller chooses which gate
# to apply via the corresponding method.
# 複合 cell 狀態 literal — Q1/Q2/Q3/Q4 widen 後完整狀態機進程：
# warming_up → ready → break → refit_pending → reactive。
# break/refit_pending 凍結 handoff；caller 透過對應方法選 gate。
CompositeCellStatusLiteral = Literal[
    "warming_up",
    "ready",
    "break",
    "refit_pending",
    "reactive",
    "kupiec_fail",
]


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclasses / 結果 dataclass
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class WarmupStatus:
    """Per-cell warmup gate result.

    單 cell 暖機 gate 結果。

    Attributes:
        cell_key: Canonical "<strategy>::<symbol>::<side>" cell tuple.
        fills_count: Observed fill count for the cell.
        threshold: Warmup threshold (V3 §8.4 #1 default = 500).
        ready: True iff fills_count >= threshold.
        remaining: ``max(0, threshold - fills_count)``; 0 when ready.
        status: Literal status string mirroring ``ready`` for surface APIs.
        reason_zh: Chinese reason; empty when ready.
        reason_en: English reason; empty when ready.
    """

    cell_key: str
    fills_count: int
    threshold: int
    ready: bool
    remaining: int
    status: WarmupStatusLiteral
    reason_zh: str
    reason_en: str


@dataclass(frozen=True)
class CellRegimeStatus:
    """Composite cell-level regime status.

    複合 cell-level regime 狀態。

    Q1 ships warmup-only fields. Q2 (CUSUM) / Q3 (Kupiec) / Q4 (PSR)
    extend via additional fields and a wider ``composite_status``
    literal — this dataclass is the canonical extension point so
    consumers (replay_routes generate_handoff_verdict, P3b
    cell_calibrator) need not re-import per sub-task.

    Q1 只交付 warmup 欄位；Q2/Q3/Q4 透過追加欄位擴展。
    """

    cell_key: str
    warmup: WarmupStatus
    composite_status: CompositeCellStatusLiteral
    reason_zh: str
    reason_en: str
    # Forward-compat extension slots (Q2-Q4 will populate).
    # 向前相容擴展欄（Q2-Q4 將填）。
    extra_payload: Dict[str, object] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# RGM-Q2 / Q3 / Q4 result dataclasses / Q2/Q3/Q4 結果 dataclass
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CusumResult:
    """RGM-Q2 CUSUM ±3σ break detection result.

    RGM-Q2 CUSUM ±3σ break 偵測結果。

    Attributes / 屬性:
        cell_key: Canonical cell tuple. / 規範 cell tuple。
        n: Number of return observations consumed. / 消耗的報酬觀測數。
        cusum_value: Most-extreme CUSUM running statistic (max |S_t|). /
            最極端 CUSUM 統計（max |S_t|）。
        threshold: ±σ threshold (V3 §8.4 #2 default 3.0). /
            ±σ 閾值（V3 §8.4 #2 預設 3.0）。
        break_detected: True iff |cusum_value| > threshold. /
            |cusum_value| > threshold 時 True。
        state_after: ``'active'`` when no break; ``'break'`` when break detected. /
            無 break 時 'active'；有則 'break'。
        sample_mean: Drift used as CUSUM centring. / CUSUM 中心化用 drift。
        sample_std: Sample std used for normalisation. /
            標準化用樣本 std。
        reason_zh: Bilingual reason (Chinese). / 中文原因。
        reason_en: Bilingual reason (English). / 英文原因。
    """

    cell_key: str
    n: int
    cusum_value: float
    threshold: float
    break_detected: bool
    state_after: Literal["active", "break"]
    sample_mean: float
    sample_std: float
    reason_zh: str
    reason_en: str


@dataclass(frozen=True)
class KupiecResult:
    """RGM-Q3 Kupiec POF (Proportion of Failures) result.

    RGM-Q3 Kupiec POF（失敗比率）結果。

    Attributes / 屬性:
        cell_key: Canonical cell tuple. / 規範 cell tuple。
        n: Sample size; MUST be >= KUPIEC_MIN_N (250). /
            樣本量；須 >= KUPIEC_MIN_N（250）。
        observed_violations: Number of VaR breaches observed. /
            觀察到的 VaR 違反數。
        expected_violations: Expected breaches under nominal coverage
            (n × alpha). / 名目覆蓋下預期違反數（n × alpha）。
        coverage_alpha: VaR confidence level breach probability (e.g.,
            0.05 for 95% VaR). / VaR 違反機率（例 0.05 = 95% VaR）。
        lr_test_statistic: Likelihood ratio test statistic (chi² 1df). /
            概似比檢定統計量（chi² 1df）。
        p_value: p-value of LR test (chi² 1df survival). / LR 檢定 p-value。
        reject_h0: True iff p < KUPIEC_P_VALUE_THRESHOLD (0.05). /
            p < KUPIEC_P_VALUE_THRESHOLD（0.05）時 True。
        sufficient_sample: True iff n >= KUPIEC_MIN_N. /
            n >= KUPIEC_MIN_N 時 True。
        reason_zh: Bilingual reason (Chinese). / 中文原因。
        reason_en: Bilingual reason (English). / 英文原因。
    """

    cell_key: str
    n: int
    observed_violations: int
    expected_violations: float
    coverage_alpha: float
    lr_test_statistic: float
    p_value: float
    reject_h0: bool
    sufficient_sample: bool
    reason_zh: str
    reason_en: str


@dataclass(frozen=True)
class PsrResult:
    """RGM-Q4 PSR(0) across 3×250 windows result.

    RGM-Q4 PSR(0) across 3×250 窗結果。

    Attributes / 屬性:
        cell_key: Canonical cell tuple. / 規範 cell tuple。
        n_total: Total sample size consumed. / 總消耗樣本量。
        window_size: Per-window size (V3 §8.4 #4 default 250). /
            每窗大小（V3 §8.4 #4 預設 250）。
        num_windows: Number of windows used (default 3). /
            使用窗數（預設 3）。
        window_psrs: Per-window PSR(0) values. / 每窗 PSR(0)。
        threshold: PSR threshold (V3 §8.4 #4 default 0.95). /
            PSR 閾值（V3 §8.4 #4 預設 0.95）。
        all_below_threshold: True iff every window's PSR < threshold. /
            每窗 PSR 都 < threshold 時 True。
        refit_trigger: True iff all_below_threshold AND
            sufficient_sample (drives refit recommendation). /
            all_below_threshold AND sufficient_sample 時 True（驅動
            refit 建議）。
        sufficient_sample: True iff n_total >= PSR_MIN_TOTAL_SAMPLES. /
            n_total >= PSR_MIN_TOTAL_SAMPLES 時 True。
        pm_alert_emitted: True iff a governance audit alert was
            recorded by an emitter callback (set by ``check_psr_3windows``
            when caller supplied a callback). /
            紀錄治理 audit alert 時 True（caller 提供 callback 才設）。
        reason_zh: Bilingual reason (Chinese). / 中文原因。
        reason_en: Bilingual reason (English). / 英文原因。
    """

    cell_key: str
    n_total: int
    window_size: int
    num_windows: int
    window_psrs: List[float]
    threshold: float
    all_below_threshold: bool
    refit_trigger: bool
    sufficient_sample: bool
    pm_alert_emitted: bool
    reason_zh: str
    reason_en: str


# Forward-declared callback signature for PsrResult emitter.
# PsrResult 發射 callback 的前向宣告型別。
PmAlertCallback = Optional[Any]  # callable[[CellKey, PsrResult], None]


# ─────────────────────────────────────────────────────────────────────────────
# RegimeController / Regime 控制器
# ─────────────────────────────────────────────────────────────────────────────


class RegimeController:
    """Cell-level regime gate.

    Cell-level regime gate。

    Wave 5 RGM-Q1 ships the first-500-fills warmup gate only. Sibling
    tasks RGM-Q2 (CUSUM) / RGM-Q3 (Kupiec POF) / RGM-Q4 (PSR(0))
    extend this class via additional methods and broader
    ``CompositeCellStatusLiteral`` — this commit keeps the class
    instantiable + import-clean so those sub-tasks can subclass or
    extend without breaking ABI.

    本 commit 只交付 first-500-fills warmup gate；RGM-Q2/Q3/Q4 sibling
    在後續 commit 擴展。

    Args:
        warmup_threshold: V3 §8.4 #1 warmup fill count (default 500).
            Constructor override is for hermetic test only; production
            caller MUST use default.
    """

    def __init__(
        self,
        warmup_threshold: int = WARMUP_FILLS_THRESHOLD,
        cusum_sigma_threshold: float = CUSUM_SIGMA_THRESHOLD,
        kupiec_min_n: int = KUPIEC_MIN_N,
        kupiec_p_value_threshold: float = KUPIEC_P_VALUE_THRESHOLD,
        psr_threshold: float = PSR_THRESHOLD,
        psr_window_size: int = PSR_WINDOW_SIZE,
        psr_num_windows: int = PSR_NUM_WINDOWS,
        pm_alert_callback: PmAlertCallback = None,
    ) -> None:
        if not isinstance(warmup_threshold, int):
            raise ValueError(
                f"warmup_threshold must be int (V3 §8.4 #1 fill count); "
                f"got {type(warmup_threshold).__name__}"
            )
        if warmup_threshold <= 0:
            raise ValueError(
                f"warmup_threshold must be positive (V3 §8.4 #1); "
                f"got {warmup_threshold}"
            )
        if cusum_sigma_threshold <= 0:
            raise ValueError(
                f"cusum_sigma_threshold must be positive (V3 §8.4 #2); "
                f"got {cusum_sigma_threshold}"
            )
        if not isinstance(kupiec_min_n, int) or kupiec_min_n <= 0:
            raise ValueError(
                f"kupiec_min_n must be positive int (V3 §8.4 #3); "
                f"got {kupiec_min_n!r}"
            )
        if not 0.0 < kupiec_p_value_threshold < 1.0:
            raise ValueError(
                f"kupiec_p_value_threshold must be in (0, 1); "
                f"got {kupiec_p_value_threshold}"
            )
        if not 0.0 < psr_threshold < 1.0:
            raise ValueError(
                f"psr_threshold must be in (0, 1); got {psr_threshold}"
            )
        if not isinstance(psr_window_size, int) or psr_window_size <= 0:
            raise ValueError(
                f"psr_window_size must be positive int; got {psr_window_size!r}"
            )
        if not isinstance(psr_num_windows, int) or psr_num_windows <= 0:
            raise ValueError(
                f"psr_num_windows must be positive int; got {psr_num_windows!r}"
            )
        if pm_alert_callback is not None and not callable(pm_alert_callback):
            raise ValueError(
                "pm_alert_callback must be callable or None"
            )
        self._warmup_threshold = warmup_threshold
        self._cusum_sigma_threshold = float(cusum_sigma_threshold)
        self._kupiec_min_n = kupiec_min_n
        self._kupiec_p_value_threshold = float(kupiec_p_value_threshold)
        self._psr_threshold = float(psr_threshold)
        self._psr_window_size = psr_window_size
        self._psr_num_windows = psr_num_windows
        self._pm_alert_callback = pm_alert_callback
        # Per-cell state map for cross-call isolation (RGM-Q2/3/4 do not
        # require persistence beyond callsite; this map is reserved for
        # forward-compat scenarios where caller wants composite gating).
        # 每 cell 狀態表 — Q2/3/4 不要求跨呼叫持久；保留為 forward-compat。
        self._cell_state: Dict[str, Dict[str, object]] = {}

    @property
    def warmup_threshold(self) -> int:
        """Effective warmup threshold (V3 §8.4 #1 default 500).

        生效中的 warmup 閾值（V3 §8.4 #1 預設 500）。
        """
        return self._warmup_threshold

    @property
    def cusum_sigma_threshold(self) -> float:
        """Effective CUSUM ±σ threshold (V3 §8.4 #2 default 3.0).

        生效中 CUSUM ±σ 閾值（V3 §8.4 #2 預設 3.0）。
        """
        return self._cusum_sigma_threshold

    @property
    def kupiec_min_n(self) -> int:
        """Effective Kupiec min n (V3 §8.4 #3 default 250).

        生效中 Kupiec 最小 n（V3 §8.4 #3 預設 250）。
        """
        return self._kupiec_min_n

    @property
    def psr_threshold(self) -> float:
        """Effective PSR(0) threshold (V3 §8.4 #4 default 0.95).

        生效中 PSR(0) 閾值（V3 §8.4 #4 預設 0.95）。
        """
        return self._psr_threshold

    @property
    def psr_window_size(self) -> int:
        """Effective PSR window size (V3 §8.4 #4 default 250).

        生效中 PSR 窗大小（V3 §8.4 #4 預設 250）。
        """
        return self._psr_window_size

    @property
    def psr_num_windows(self) -> int:
        """Effective PSR num windows (V3 §8.4 #4 default 3).

        生效中 PSR 窗數（V3 §8.4 #4 預設 3）。
        """
        return self._psr_num_windows

    def check_warmup(self, cell_key: str, fills_count: int) -> WarmupStatus:
        """Return ``WarmupStatus`` for the cell.

        回 cell 的 ``WarmupStatus``。

        Args:
            cell_key: Canonical "<strategy>::<symbol>::<side>" tuple
                (caller MUST canonicalise upstream).
            fills_count: Observed fill count for the cell. Must be
                non-negative integer.

        Returns:
            ``WarmupStatus`` with ``ready=True`` iff
            ``fills_count >= warmup_threshold``; otherwise ``ready=False``
            with ``remaining = threshold - fills_count``.

        Raises:
            ValueError: on empty cell_key, non-integer fills_count, or
                negative fills_count.
        """
        # Validate cell_key shape — empty string is the most common
        # caller bug (forgot to populate cell tuple); non-empty is the
        # only invariant Q1 enforces (sub-tasks Q2/Q3/Q4 may add a
        # stricter format CHECK if needed).
        # 驗 cell_key 形狀 — 空字串是最常見的 caller bug；只要求非空。
        if not isinstance(cell_key, str) or not cell_key.strip():
            raise ValueError(
                "cell_key must be non-empty string "
                "(V3 §4.1 cell tuple '<strategy>::<symbol>::<side>')"
            )

        if not isinstance(fills_count, int):
            raise ValueError(
                f"fills_count must be int; got {type(fills_count).__name__}"
            )
        if fills_count < 0:
            raise ValueError(
                f"fills_count must be non-negative; got {fills_count}"
            )

        if fills_count >= self._warmup_threshold:
            ready = True
            remaining = 0
            status: WarmupStatusLiteral = "ready"
            reason_zh = ""
            reason_en = ""
        else:
            ready = False
            remaining = self._warmup_threshold - fills_count
            status = "warming_up"
            reason_zh = (
                f"Cell {cell_key} 暖機中：{fills_count}/{self._warmup_threshold} fills "
                f"（缺 {remaining} fills 達 V3 §8.4 #1 門檻）"
            )
            reason_en = (
                f"cell {cell_key} warming up: {fills_count}/{self._warmup_threshold} fills "
                f"({remaining} fills short of V3 §8.4 #1 threshold)"
            )

        return WarmupStatus(
            cell_key=cell_key,
            fills_count=fills_count,
            threshold=self._warmup_threshold,
            ready=ready,
            remaining=remaining,
            status=status,
            reason_zh=reason_zh,
            reason_en=reason_en,
        )

    def get_cell_status(
        self,
        cell_key: str,
        fills_count: int,
        *,
        extra_payload: Optional[Dict[str, object]] = None,
    ) -> CellRegimeStatus:
        """Return composite ``CellRegimeStatus``.

        回複合 ``CellRegimeStatus``。

        Wave 5 RGM-Q1 composite status mirrors the warmup status (1:1
        mapping). RGM-Q2 / Q3 / Q4 sub-tasks extend ``composite_status``
        and ``extra_payload`` with regime_break / kupiec_fail /
        psr_fail dimensions.

        Args:
            cell_key: Canonical cell tuple.
            fills_count: Observed fill count.
            extra_payload: Optional caller-supplied auxiliary payload
                (forward-compat hook for Q2/Q3/Q4 to inject CUSUM /
                Kupiec / PSR diagnostics without breaking ABI).

        Returns:
            ``CellRegimeStatus`` carrying the warmup result + a
            composite_status literal (currently 1:1 with warmup).

        Raises:
            ValueError: on invalid cell_key / fills_count.
        """
        warmup = self.check_warmup(cell_key, fills_count)

        if warmup.ready:
            composite: CompositeCellStatusLiteral = "ready"
            reason_zh = (
                f"Cell {cell_key} ready：暖機完成（{warmup.fills_count} fills）"
            )
            reason_en = (
                f"cell {cell_key} ready: warmup complete ({warmup.fills_count} fills)"
            )
        else:
            composite = "warming_up"
            reason_zh = warmup.reason_zh
            reason_en = warmup.reason_en

        return CellRegimeStatus(
            cell_key=cell_key,
            warmup=warmup,
            composite_status=composite,
            reason_zh=reason_zh,
            reason_en=reason_en,
            extra_payload=dict(extra_payload) if extra_payload else {},
        )

    # ------------------------------------------------------------------
    # RGM-Q2: CUSUM ±3σ break detection / RGM-Q2 CUSUM ±3σ break 偵測
    # ------------------------------------------------------------------

    def check_cusum(
        self,
        cell_key: str,
        recent_returns: Sequence[float],
        *,
        min_n: int = 30,
    ) -> CusumResult:
        """Return CUSUM ±σ break detection result for the cell.

        回 cell 的 CUSUM ±σ break 偵測結果。

        Algorithm / 演算法:
            1. Standardise returns: z_i = (r_i - μ) / σ.
            2. Compute cumulative S_t = Σ_{i<=t} z_i.
            3. Normalise by sqrt(n): S_z = max_t |S_t| / sqrt(n).
            4. Break iff S_z > ``cusum_sigma_threshold`` (default 3.0).

        Per V3 §8.4 #2: detection freezes ACTIONABLE HANDOFF only — the
        underlying calibration model continues training. Caller (handoff
        endpoint) is expected to short-circuit handoff on
        ``state_after == 'break'``.
        V3 §8.4 #2：偵測只 freeze 可執行 handoff — 模型仍訓練。caller
        (handoff endpoint) 在 state_after == 'break' 時短路 handoff。

        Args:
            cell_key: Canonical "<strategy>::<symbol>::<side>" cell tuple.
            recent_returns: Recent realised edge / PnL series for the cell.
                Caller MUST canonicalise window selection (e.g., last
                N fills since warmup completion).
            min_n: Minimum sample size to compute CUSUM (default 30 —
                the V3 §8.1 cell-level n>=30 contract).

        Returns:
            ``CusumResult`` with break_detected + state_after literal.

        Raises:
            ValueError: empty / invalid cell_key, or n < min_n after
                non-finite filtering.
        """
        _validate_cell_key_internal(cell_key)
        arr = _validate_returns(recent_returns, "check_cusum", min_n)

        max_abs_z, mean, std = _cusum_statistic(arr)
        break_detected = max_abs_z > self._cusum_sigma_threshold
        state_after: Literal["active", "break"] = (
            "break" if break_detected else "active"
        )

        if break_detected:
            reason_zh = (
                f"Cell {cell_key} CUSUM break：max|S_z|={max_abs_z:.3f} > "
                f"閾值 {self._cusum_sigma_threshold:.1f}σ；handoff 凍結（V3 §8.4 #2）"
            )
            reason_en = (
                f"cell {cell_key} CUSUM break: max|S_z|={max_abs_z:.3f} > "
                f"threshold {self._cusum_sigma_threshold:.1f}σ; handoff frozen "
                f"(V3 §8.4 #2)"
            )
        else:
            reason_zh = (
                f"Cell {cell_key} CUSUM active：max|S_z|={max_abs_z:.3f} <= "
                f"閾值 {self._cusum_sigma_threshold:.1f}σ"
            )
            reason_en = (
                f"cell {cell_key} CUSUM active: max|S_z|={max_abs_z:.3f} <= "
                f"threshold {self._cusum_sigma_threshold:.1f}σ"
            )

        return CusumResult(
            cell_key=cell_key,
            n=len(arr),
            cusum_value=max_abs_z,
            threshold=self._cusum_sigma_threshold,
            break_detected=break_detected,
            state_after=state_after,
            sample_mean=mean,
            sample_std=std,
            reason_zh=reason_zh,
            reason_en=reason_en,
        )

    # ------------------------------------------------------------------
    # RGM-Q3: Kupiec POF n>=250 / Kupiec POF n>=250
    # ------------------------------------------------------------------

    def check_kupiec_pof(
        self,
        cell_key: str,
        predicted_var_breaches: Sequence[bool],
        coverage_alpha: float = 0.05,
    ) -> KupiecResult:
        """Return Kupiec POF (Proportion of Failures) test result.

        回 Kupiec POF（失敗比率）檢定結果。

        V3 §8.4 #3 contract / V3 §8.4 #3 契約:
            - Independent sample per (strategy, symbol) cell;
              MUST NOT borrow from PBO test sample (separate windows).
            - n >= 250 per cell — below threshold returns
              ``sufficient_sample=False`` and the gate is non-actionable.
            - Caller supplies VaR breach booleans (True = breach observed,
              False = within VaR). Caller MUST construct breaches from
              cell-independent backtest window.

            獨立每 cell 樣本；禁從 PBO 借樣本。n < 250 → 不可行；
            caller 提供 VaR 違反 boolean（True = 違反）。

        Algorithm:
            LR = -2 * ln(L0/L1), chi² 1df.
            p_value = 1 - chi2.cdf(LR, df=1).
            reject_h0 iff p_value < kupiec_p_value_threshold (0.05).

        Args:
            cell_key: Canonical cell tuple.
            predicted_var_breaches: bool sequence (True = breach).
            coverage_alpha: VaR breach probability (default 0.05).
                Common values: 0.05 for 95% VaR; 0.01 for 99% VaR.

        Returns:
            ``KupiecResult`` with p_value + reject_h0 + sufficient_sample.

        Raises:
            ValueError: invalid cell_key / coverage_alpha out of (0,1) /
                non-bool sequence detected.
        """
        _validate_cell_key_internal(cell_key)
        if not 0.0 < coverage_alpha < 1.0:
            raise ValueError(
                f"coverage_alpha must be in (0, 1); got {coverage_alpha}"
            )
        if predicted_var_breaches is None:
            raise ValueError("predicted_var_breaches must not be None")
        # Allow sequences of bool / int 0-1 / np.bool_; reject anything else.
        # 接受 bool / 0-1 int / np.bool_；其他 reject。
        try:
            arr = np.asarray(list(predicted_var_breaches))
        except Exception as exc:
            raise ValueError(
                f"predicted_var_breaches must be sequence of bool: {exc}"
            ) from exc
        # Validate bool / 0/1.
        if arr.size == 0:
            n = 0
        else:
            # Accept bool dtype OR int with values strictly in {0,1}.
            # 接受 bool dtype 或 int 值 ∈ {0,1}。
            if arr.dtype == bool:
                pass
            elif np.issubdtype(arr.dtype, np.integer):
                if not np.all((arr == 0) | (arr == 1)):
                    raise ValueError(
                        "predicted_var_breaches int values must be 0 or 1"
                    )
            else:
                raise ValueError(
                    f"predicted_var_breaches dtype must be bool or int 0/1; "
                    f"got {arr.dtype}"
                )
            n = int(arr.size)
        observed = int(np.sum(arr.astype(bool))) if n > 0 else 0

        sufficient = n >= self._kupiec_min_n
        if not sufficient:
            # Insufficient sample — refuse the test per V3 §8.4 #3 ("cell n<250 skipped").
            # 樣本不足 — 拒絕檢定（V3 §8.4 #3「cell n<250 skipped」）。
            reason_zh = (
                f"Cell {cell_key} Kupiec POF skipped：n={n} < "
                f"{self._kupiec_min_n}（V3 §8.4 #3）"
            )
            reason_en = (
                f"cell {cell_key} Kupiec POF skipped: n={n} < "
                f"{self._kupiec_min_n} (V3 §8.4 #3)"
            )
            expected = float(coverage_alpha) * float(n)
            return KupiecResult(
                cell_key=cell_key,
                n=n,
                observed_violations=observed,
                expected_violations=expected,
                coverage_alpha=coverage_alpha,
                lr_test_statistic=float("nan"),
                p_value=float("nan"),
                reject_h0=False,
                sufficient_sample=False,
                reason_zh=reason_zh,
                reason_en=reason_en,
            )

        expected = float(coverage_alpha) * float(n)
        lr, p_value = _kupiec_lr_pof(n, observed, coverage_alpha)
        reject_h0 = (
            math.isfinite(p_value)
            and p_value < self._kupiec_p_value_threshold
        )

        if reject_h0:
            reason_zh = (
                f"Cell {cell_key} Kupiec POF reject H0：observed={observed} "
                f"expected={expected:.1f} p={p_value:.4f} < {self._kupiec_p_value_threshold} "
                f"(V3 §8.4 #3)；模型 underestimates 風險"
            )
            reason_en = (
                f"cell {cell_key} Kupiec POF reject H0: observed={observed} "
                f"expected={expected:.1f} p={p_value:.4f} < {self._kupiec_p_value_threshold} "
                f"(V3 §8.4 #3); model under-estimates risk"
            )
        else:
            reason_zh = (
                f"Cell {cell_key} Kupiec POF accept H0：observed={observed} "
                f"expected={expected:.1f} p={p_value:.4f} >= {self._kupiec_p_value_threshold}"
            )
            reason_en = (
                f"cell {cell_key} Kupiec POF accept H0: observed={observed} "
                f"expected={expected:.1f} p={p_value:.4f} >= {self._kupiec_p_value_threshold}"
            )

        return KupiecResult(
            cell_key=cell_key,
            n=n,
            observed_violations=observed,
            expected_violations=expected,
            coverage_alpha=coverage_alpha,
            lr_test_statistic=lr,
            p_value=p_value,
            reject_h0=reject_h0,
            sufficient_sample=True,
            reason_zh=reason_zh,
            reason_en=reason_en,
        )

    # ------------------------------------------------------------------
    # RGM-Q4: PSR(0) across 3×250 windows / PSR(0) across 3×250 窗
    # ------------------------------------------------------------------

    def check_psr_3windows(
        self,
        cell_key: str,
        returns: Sequence[float],
    ) -> PsrResult:
        """Return PSR(0) test across 3 rolling windows (V3 §8.4 #4).

        回 PSR(0) 跨 3 滾動窗結果（V3 §8.4 #4）。

        V3 §8.4 #4 contract / V3 §8.4 #4 契約:
            - 3 consecutive windows × 250 fills each.
            - PSR(0) computed on the LAST ``num_windows × window_size``
              fills; window 0 is the oldest, window N-1 is the newest.
            - Refit + PM alert iff PSR < threshold in ALL windows.
            - PM alert is best-effort: callable-callback supplied at
              construction time receives ``(cell_key, PsrResult)``;
              if no callback configured, ``pm_alert_emitted=False``.

        Algorithm:
            for w in 0..num_windows:
                window = returns[(N-num_windows+w)*window_size :
                                 (N-num_windows+w+1)*window_size]
                psr_w = PSR(0) on window
            all_below_threshold = all(psr < threshold)
            refit_trigger = all_below_threshold AND sufficient_sample

        Args:
            cell_key: Canonical cell tuple.
            returns: Time-ordered returns (per-fill realised edge).

        Returns:
            ``PsrResult`` with window_psrs + refit_trigger + pm_alert_emitted.

        Raises:
            ValueError: invalid cell_key / returns is None.
        """
        _validate_cell_key_internal(cell_key)
        if returns is None:
            raise ValueError("returns must not be None")
        arr = np.asarray(list(returns), dtype=np.float64).flatten()
        arr = arr[np.isfinite(arr)]
        n_total = int(len(arr))

        required = self._psr_num_windows * self._psr_window_size
        sufficient = n_total >= required

        if not sufficient:
            # Insufficient sample — return placeholder with reasonable
            # window_psrs (NaN list) and refit_trigger=False.
            # 樣本不足 — placeholder + window_psrs NaN + refit=False。
            window_psrs = [float("nan")] * self._psr_num_windows
            reason_zh = (
                f"Cell {cell_key} PSR(0) skipped：n_total={n_total} < "
                f"required={required} ({self._psr_num_windows}×{self._psr_window_size}, V3 §8.4 #4)"
            )
            reason_en = (
                f"cell {cell_key} PSR(0) skipped: n_total={n_total} < "
                f"required={required} ({self._psr_num_windows}×{self._psr_window_size}, V3 §8.4 #4)"
            )
            return PsrResult(
                cell_key=cell_key,
                n_total=n_total,
                window_size=self._psr_window_size,
                num_windows=self._psr_num_windows,
                window_psrs=window_psrs,
                threshold=self._psr_threshold,
                all_below_threshold=False,
                refit_trigger=False,
                sufficient_sample=False,
                pm_alert_emitted=False,
                reason_zh=reason_zh,
                reason_en=reason_en,
            )

        # Compute PSR per window — use the LAST 3 windows (most recent
        # data); allows caller to feed long history while we slice the
        # tail. Window order: window[0] = oldest of the 3; window[-1] = newest.
        # 用最近 3 窗（caller 可餵長史；我切尾）。
        # 窗序：window[0] = 3 窗中最舊；window[-1] = 最新。
        window_psrs: List[float] = []
        tail_start = n_total - required
        for w in range(self._psr_num_windows):
            start = tail_start + w * self._psr_window_size
            end = start + self._psr_window_size
            window_arr = arr[start:end]
            psr_val = _psr_zero(window_arr)
            window_psrs.append(psr_val)

        all_below = all(
            math.isfinite(p) and p < self._psr_threshold
            for p in window_psrs
        )
        refit_trigger = all_below

        pm_alert_emitted = False
        if refit_trigger and self._pm_alert_callback is not None:
            try:
                self._pm_alert_callback(cell_key, {
                    "cell_key": cell_key,
                    "window_psrs": list(window_psrs),
                    "threshold": self._psr_threshold,
                    "n_total": n_total,
                    "v3_section": "8.4#4",
                })
                pm_alert_emitted = True
            except Exception as exc:
                # Best-effort: log + leave pm_alert_emitted=False.
                # Best-effort：log + 留 pm_alert_emitted=False。
                logger.warning(
                    "regime_controller: pm_alert_callback raised for cell=%s: %s",
                    cell_key,
                    exc,
                )

        if refit_trigger:
            reason_zh = (
                f"Cell {cell_key} PSR(0) refit triggered：所有 "
                f"{self._psr_num_windows} 窗 PSR < {self._psr_threshold}; "
                f"window_psrs={['%.3f' % p for p in window_psrs]} (V3 §8.4 #4)"
            )
            reason_en = (
                f"cell {cell_key} PSR(0) refit triggered: all "
                f"{self._psr_num_windows} windows PSR < {self._psr_threshold}; "
                f"window_psrs={['%.3f' % p for p in window_psrs]} (V3 §8.4 #4)"
            )
        else:
            reason_zh = (
                f"Cell {cell_key} PSR(0) ok：window_psrs="
                f"{['%.3f' % p for p in window_psrs]}; threshold={self._psr_threshold}"
            )
            reason_en = (
                f"cell {cell_key} PSR(0) ok: window_psrs="
                f"{['%.3f' % p for p in window_psrs]}; threshold={self._psr_threshold}"
            )

        return PsrResult(
            cell_key=cell_key,
            n_total=n_total,
            window_size=self._psr_window_size,
            num_windows=self._psr_num_windows,
            window_psrs=window_psrs,
            threshold=self._psr_threshold,
            all_below_threshold=all_below,
            refit_trigger=refit_trigger,
            sufficient_sample=True,
            pm_alert_emitted=pm_alert_emitted,
            reason_zh=reason_zh,
            reason_en=reason_en,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Internal cell_key validation helper / 內部 cell_key 驗證
# ─────────────────────────────────────────────────────────────────────────────


def _validate_cell_key_internal(cell_key: str) -> None:
    """Cell key must be non-empty string. / cell_key 須為非空字串。

    Mirrors RGM-Q1 ``check_warmup`` invariant — kept module-level so
    Q2/Q3/Q4 methods don't depend on Q1 method internals.
    鏡像 RGM-Q1 ``check_warmup`` 不變量 — 保模組級避 Q2/Q3/Q4 依賴 Q1 內部。
    """
    if not isinstance(cell_key, str) or not cell_key.strip():
        raise ValueError(
            "cell_key must be non-empty string "
            "(V3 §4.1 cell tuple '<strategy>::<symbol>::<side>')"
        )


__all__ = [
    "CUSUM_SIGMA_THRESHOLD",
    "CellRegimeStatus",
    "CompositeCellStatusLiteral",
    "CusumResult",
    "KUPIEC_MIN_N",
    "KUPIEC_P_VALUE_THRESHOLD",
    "KupiecResult",
    "PSR_MIN_TOTAL_SAMPLES",
    "PSR_NUM_WINDOWS",
    "PSR_THRESHOLD",
    "PSR_WINDOW_SIZE",
    "PsrResult",
    "RegimeController",
    "WARMUP_FILLS_THRESHOLD",
    "WarmupStatus",
    "WarmupStatusLiteral",
]
