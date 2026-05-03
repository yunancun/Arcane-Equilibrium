"""cost_edge_advisor — REF-20 Wave 6 P4-Q6 cost/edge ratio promotion gate.

cost_edge_ratio >= 0.8 gate — REF-20 Wave 6 P4-Q6 cost/edge 比率 gate。

MODULE_NOTE (EN): Python advisor + gate for V3 §8.1 + §12 #24
  `cost_edge_ratio >= 0.8` constraint on LLM/ML-assisted candidate loops.
  Computes ratio = expected_edge / expected_cost (both bps); gates against
  threshold; respects `OPENCLAW_COST_EDGE_ADVISOR=1` env-gate (P1-FAKE-3).
  When env-gate is False (default), advisor returns 'advisory_only' verdict
  regardless of ratio — output is logged but not actionable.

  Pure-math IMPL: 0 IPC / 0 DB / 0 exchange. Output feeds replay_routes
  advisory verdict layer. Mirrors Rust `CostEdgeAdvisor` env-gate semantics
  at `rust/openclaw_engine/src/cost_edge_advisor_boot.rs:142` (strict-equal
  "1" comparison).

MODULE_NOTE (中): V3 §8.1 + §12 #24 `cost_edge_ratio >= 0.8` 約束的 Python
  advisor + gate（針對 LLM/ML 輔助候選 loop）。計算 ratio = expected_edge /
  expected_cost（均 bps）；對閾值 gate；遵守 `OPENCLAW_COST_EDGE_ADVISOR=1`
  env-gate（P1-FAKE-3）。env-gate 關（預設）時 advisor 回 'advisory_only'，
  output 記錄但不 actionable。

  純數學 IMPL：0 IPC / 0 DB / 0 exchange。輸出餵 replay_routes advisory
  verdict 層。鏡像 Rust `CostEdgeAdvisor` env-gate semantics
  （`rust/openclaw_engine/src/cost_edge_advisor_boot.rs:142` 嚴格 "1" 比對）。

V3 §8.1 + §11 P4 + §12 #24 binding / V3 綁定:
  - "cost gate: cost_edge_ratio >= 0.8 for LLM/ML assisted candidate loops" (§8.1)
  - "LLM/ML assisted candidate loops respect cost_edge_ratio >= 0.8" (§12 #24)
  - "advisor disabled (OPENCLAW_COST_EDGE_ADVISOR != \"1\"), daemon not spawned"
    (Rust ref `cost_edge_advisor_boot.rs:145`)

CLAUDE.md memory binding / CLAUDE.md memory 綁定:
  - feedback_disable_adaptive_thinking
  - 18 blocker #10: HStateCache + CostEdgeAdvisor 兩 late-inject slot env-gated OFF

Wave 6 P4-Q6 scope (this commit):
  - CostEdgeAdvisor class with compute_ratio() + gate() pure methods.
  - CostEdgeResult dataclass.
  - 4 pytest cases: ratio=1.0 + env=True → actionable / ratio=0.5 → block /
    ratio=0.9 + env=False → advisory_only / env_gate respect.

NOT in this scope:
  - replay_routes.py call-site wiring (separate sub-task).
  - Rust-side `CostEdgeAdvisorDbSlot` integration (Rust端已存在).
  - DSR(K) sibling gate (P4-Q1 → dsr_gate.py).
  - PBO sibling gate (P4-Q2 → pbo_gate.py).

SPEC:
  - REF-20 V3 §8.1 (cost gate)
  - REF-20 V3 §11 P4 Exit
  - REF-20 V3 §12 acceptance #24 (replay_cost_edge_ratio_gate)
Workplan: docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 R20-P4-Q6
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from typing import Literal, Optional


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# V3 §8.1 / §12 #24 thresholds / V3 閾值常數
# ─────────────────────────────────────────────────────────────────────────────

# V3 §8.1 / §12 #24 ratio threshold for actionable gate.
# V3 §8.1 / §12 #24 actionable gate ratio 閾值。
DEFAULT_RATIO_THRESHOLD: float = 0.8

# Env var name (strict-equal "1" semantics — mirrors Rust spec at
# `rust/openclaw_engine/src/cost_edge_advisor_boot.rs:97`).
# 環境變數名稱（嚴格 "1" 比對 — 鏡像 Rust 規格）。
ENV_VAR_NAME: str = "OPENCLAW_COST_EDGE_ADVISOR"
ENV_VAR_TRUE_VALUE: str = "1"


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass / 結果 dataclass
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CostEdgeResult:
    """Cost/edge ratio computation result.

    Cost/edge 比率計算結果。

    Attributes / 屬性:
        expected_edge_bps: Expected per-trade edge in basis points. /
                           預期每筆 edge（基點）。
        expected_cost_bps: Expected per-trade cost in basis points
                           (fees + slippage + LLM/ML inference). /
                           預期每筆成本（基點，含 fee + slippage + LLM/ML 推論）。
        ratio: edge_bps / cost_bps; NaN if cost <= 0. /
               edge_bps / cost_bps；cost <= 0 時為 NaN。
        threshold: Configured ratio threshold (default 0.8). /
                   設定的 ratio 閾值（預設 0.8）。
        env_gate_enabled: True if `OPENCLAW_COST_EDGE_ADVISOR == "1"`. /
                          當 `OPENCLAW_COST_EDGE_ADVISOR == "1"` 時為 True。
        passes_threshold: True if ratio >= threshold (regardless of env_gate). /
                          當 ratio >= 閾值時為 True（不管 env_gate）。
    """

    expected_edge_bps: float
    expected_cost_bps: float
    ratio: float
    threshold: float
    env_gate_enabled: bool
    passes_threshold: bool


# ─────────────────────────────────────────────────────────────────────────────
# Helpers / 輔助
# ─────────────────────────────────────────────────────────────────────────────


def is_env_gate_enabled() -> bool:
    """Return True iff `OPENCLAW_COST_EDGE_ADVISOR == "1"` (strict equality).

    當 `OPENCLAW_COST_EDGE_ADVISOR == "1"`（嚴格相等）時回 True。

    Mirrors Rust spec at `rust/openclaw_engine/src/cost_edge_advisor_boot.rs:142`
    (`!is_advisor_env_enabled()` short-circuit).

    鏡像 Rust 規格（嚴格 "1" 比對）。

    Note / 註: ANY non-"1" value (including "true" / "yes" / "TRUE" / "1 ") →
    disabled. This matches Rust `env::var("OPENCLAW_COST_EDGE_ADVISOR")
    .map(|v| v == "1").unwrap_or(false)` pattern.
    註：任何非 "1" 值（含 "true" / "yes" / "TRUE" / "1 "）→ disabled。
    """
    raw = os.environ.get(ENV_VAR_NAME)
    return raw == ENV_VAR_TRUE_VALUE


# ─────────────────────────────────────────────────────────────────────────────
# CostEdgeAdvisor class / CostEdgeAdvisor 類別
# ─────────────────────────────────────────────────────────────────────────────


class CostEdgeAdvisor:
    """V3 §8.1 + §12 #24 cost/edge ratio gate (Python advisor).

    V3 §8.1 + §12 #24 cost/edge 比率 gate（Python advisor）。

    Composite gate that:
      1. Computes ratio = expected_edge_bps / expected_cost_bps.
      2. Compares against threshold.
      3. Respects `OPENCLAW_COST_EDGE_ADVISOR=1` env-gate:
         - env_gate=False → returns 'advisory_only' regardless of ratio.
         - env_gate=True + ratio >= threshold → 'actionable'.
         - env_gate=True + ratio < threshold → 'block'.

    複合 gate：
      1. 計算 ratio = expected_edge_bps / expected_cost_bps。
      2. 對閾值比較。
      3. 遵守 `OPENCLAW_COST_EDGE_ADVISOR=1` env-gate：
         - env_gate=False → 不管 ratio 一律回 'advisory_only'。
         - env_gate=True + ratio >= 閾值 → 'actionable'。
         - env_gate=True + ratio < 閾值 → 'block'。

    Usage / 使用:
        advisor = CostEdgeAdvisor(ratio_threshold=0.8)
        ratio = advisor.compute_ratio(
            expected_edge_bps=2.0,
            expected_cost_bps=1.5,
        )
        verdict = advisor.gate(ratio)  # 'actionable' / 'advisory_only' / 'block'
    """

    def __init__(
        self,
        ratio_threshold: float = DEFAULT_RATIO_THRESHOLD,
    ) -> None:
        """Initialize advisor with configurable threshold.

        以可配置閾值初始化 advisor。

        Args / 引數:
            ratio_threshold: edge/cost threshold for actionable verdict
                             (V3 §8.1 default 0.8). /
                             actionable verdict 用 edge/cost 閾值
                             （V3 §8.1 預設 0.8）。

        Raises / 拋出:
            ValueError: ratio_threshold not in (0, ∞).
        """
        if ratio_threshold <= 0.0 or not math.isfinite(ratio_threshold):
            raise ValueError(
                f"ratio_threshold={ratio_threshold} must be positive finite"
            )
        self.ratio_threshold = float(ratio_threshold)

    def compute_ratio(
        self,
        expected_edge_bps: float,
        expected_cost_bps: float,
    ) -> float:
        """Compute ratio = expected_edge / expected_cost.

        計算 ratio = expected_edge / expected_cost。

        Args / 引數:
            expected_edge_bps: Per-trade edge in basis points (signed).
                               Negative values pass through (gate will block). /
                               每筆 edge（基點，可帶符號）。負值穿透（gate 將 block）。
            expected_cost_bps: Per-trade cost in basis points (must > 0). /
                               每筆 cost（基點，必 > 0）。

        Returns / 回傳:
            ratio float; NaN if cost <= 0 (degenerate case).
            ratio float；cost <= 0 時回 NaN（退化）。

        Raises / 拋出:
            ValueError: NaN inputs.
        """
        if math.isnan(expected_edge_bps) or math.isnan(expected_cost_bps):
            raise ValueError(
                f"NaN input: edge={expected_edge_bps}, cost={expected_cost_bps}"
            )
        if expected_cost_bps <= 0.0:
            # Degenerate: zero-cost world. Return NaN to signal undefined ratio.
            # Caller's gate() must treat NaN as 'block' fail-closed.
            # 退化：零成本世界。回 NaN 表示未定義 ratio。
            # Caller 之 gate() 必將 NaN 視為 'block' fail-closed。
            logger.warning(
                "expected_cost_bps=%s <= 0; returning NaN ratio (degenerate)",
                expected_cost_bps,
            )
            return float("nan")
        return float(expected_edge_bps) / float(expected_cost_bps)

    def evaluate(
        self,
        expected_edge_bps: float,
        expected_cost_bps: float,
        env_gate: Optional[bool] = None,
    ) -> CostEdgeResult:
        """Compute ratio + populate full result struct.

        計算 ratio 並填入完整 result struct。

        Args / 引數:
            expected_edge_bps: Per-trade edge (basis points). /
                               每筆 edge（基點）。
            expected_cost_bps: Per-trade cost (basis points). /
                               每筆 cost（基點）。
            env_gate: Optional override for env-gate state. None → read
                      `OPENCLAW_COST_EDGE_ADVISOR` env. /
                      env-gate 狀態之選填覆蓋。None → 讀環境變數。

        Returns / 回傳:
            CostEdgeResult.
        """
        ratio = self.compute_ratio(expected_edge_bps, expected_cost_bps)
        env_enabled = is_env_gate_enabled() if env_gate is None else bool(env_gate)
        passes = (math.isfinite(ratio) and ratio >= self.ratio_threshold)

        return CostEdgeResult(
            expected_edge_bps=float(expected_edge_bps),
            expected_cost_bps=float(expected_cost_bps),
            ratio=float(ratio),
            threshold=self.ratio_threshold,
            env_gate_enabled=bool(env_enabled),
            passes_threshold=bool(passes),
        )

    def gate(
        self,
        ratio_or_result: float | CostEdgeResult,
        env_gate: Optional[bool] = None,
    ) -> Literal["actionable", "advisory_only", "block"]:
        """Decide verdict from ratio or CostEdgeResult.

        從 ratio 或 CostEdgeResult 決定判決。

        Verdict logic / 判決邏輯 (V3 §11 P4 footnote):
          - env_gate == False → 'advisory_only' regardless of ratio.
            env_gate == False → 不管 ratio 一律 'advisory_only'。
          - env_gate == True + ratio >= threshold → 'actionable'.
          - env_gate == True + ratio < threshold (or NaN) → 'block'.

        Args / 引數:
            ratio_or_result: float ratio (use self.ratio_threshold) or
                             CostEdgeResult (use embedded threshold). /
                             float ratio 或 CostEdgeResult。
            env_gate: Optional override; None → read env. /
                      選填覆蓋；None → 讀環境變數。

        Returns / 回傳:
            'actionable' | 'advisory_only' | 'block'.
        """
        if isinstance(ratio_or_result, CostEdgeResult):
            ratio = ratio_or_result.ratio
            threshold = ratio_or_result.threshold
            # If caller didn't pass explicit env_gate, use the one captured
            # in the result (more accurate snapshot). Otherwise, the
            # explicit param takes priority.
            # 若 caller 未傳明確 env_gate，用 result 中捕捉值（更準快照）。
            # 否則明確 param 優先。
            if env_gate is None:
                env_enabled = ratio_or_result.env_gate_enabled
            else:
                env_enabled = bool(env_gate)
        else:
            ratio = float(ratio_or_result)
            threshold = self.ratio_threshold
            env_enabled = is_env_gate_enabled() if env_gate is None else bool(env_gate)

        # env_gate=False → advisory_only regardless / env_gate=False → 一律 advisory_only
        if not env_enabled:
            return "advisory_only"

        # env_gate=True path / env_gate=True 路徑
        if not math.isfinite(ratio):
            # Fail-closed: NaN ratio (cost<=0 degenerate) → block.
            # Fail-closed：NaN ratio（cost<=0 退化）→ block。
            return "block"
        if ratio >= threshold:
            return "actionable"
        return "block"


# ─────────────────────────────────────────────────────────────────────────────
# Module-level convenience / 模組級便利函數
# ─────────────────────────────────────────────────────────────────────────────


def evaluate_cost_edge(
    expected_edge_bps: float,
    expected_cost_bps: float,
    ratio_threshold: float = DEFAULT_RATIO_THRESHOLD,
    env_gate: Optional[bool] = None,
) -> CostEdgeResult:
    """Module-level shortcut for CostEdgeAdvisor.evaluate.

    CostEdgeAdvisor.evaluate 的模組級捷徑。
    """
    return CostEdgeAdvisor(ratio_threshold=ratio_threshold).evaluate(
        expected_edge_bps=expected_edge_bps,
        expected_cost_bps=expected_cost_bps,
        env_gate=env_gate,
    )
