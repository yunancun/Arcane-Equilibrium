"""Tests for cost_edge_advisor (REF-20 Wave 6 P4-Q6).

cost_edge_advisor 測試（REF-20 Wave 6 P4-Q6）。

Coverage / 覆蓋:
  1. ratio=1.0 + env=True → 'actionable'. /
     ratio=1.0 + env=True → 'actionable'。
  2. ratio=0.5 + env=True → 'block'. /
     ratio=0.5 + env=True → 'block'。
  3. ratio=0.9 + env=False → 'advisory_only' (env-gate respect). /
     ratio=0.9 + env=False → 'advisory_only'（env-gate 遵守）。
  4. env_gate respect at boundary cases (degenerate cost / negative edge). /
     env_gate 在邊界案例（退化 cost / 負 edge）的遵守。
"""

from __future__ import annotations

import math

import pytest

from program_code.learning_engine.cost_edge_advisor import (
    DEFAULT_RATIO_THRESHOLD,
    ENV_VAR_NAME,
    CostEdgeAdvisor,
    CostEdgeResult,
    evaluate_cost_edge,
    is_env_gate_enabled,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: ratio=1.0 + env=True → 'actionable'
# ─────────────────────────────────────────────────────────────────────────────


def test_ratio_above_threshold_env_on_actionable():
    """ratio=1.0 (>=0.8) + env_gate=True → 'actionable'.

    ratio=1.0 (>=0.8) + env_gate=True → 'actionable'。

    Setup / 設定: edge=2.0 bps, cost=2.0 bps → ratio=1.0 >= 0.8.
    """
    advisor = CostEdgeAdvisor(ratio_threshold=0.8)
    result = advisor.evaluate(
        expected_edge_bps=2.0,
        expected_cost_bps=2.0,
        env_gate=True,
    )

    assert isinstance(result, CostEdgeResult)
    assert math.isclose(result.ratio, 1.0, abs_tol=1e-12)
    assert result.passes_threshold is True
    assert result.env_gate_enabled is True

    verdict = advisor.gate(result)
    assert verdict == "actionable", f"expected 'actionable', got '{verdict}'"


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: ratio=0.5 + env=True → 'block'
# ─────────────────────────────────────────────────────────────────────────────


def test_ratio_below_threshold_blocks():
    """ratio=0.5 (<0.8) + env_gate=True → 'block'.

    ratio=0.5 (<0.8) + env_gate=True → 'block'。

    Setup / 設定: edge=1.0 bps, cost=2.0 bps → ratio=0.5 < 0.8.
    """
    advisor = CostEdgeAdvisor(ratio_threshold=0.8)
    result = advisor.evaluate(
        expected_edge_bps=1.0,
        expected_cost_bps=2.0,
        env_gate=True,
    )

    assert math.isclose(result.ratio, 0.5, abs_tol=1e-12)
    assert result.passes_threshold is False
    assert result.env_gate_enabled is True

    verdict = advisor.gate(result)
    assert verdict == "block", f"expected 'block', got '{verdict}'"


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: ratio=0.9 + env=False → 'advisory_only'
# ─────────────────────────────────────────────────────────────────────────────


def test_env_gate_off_returns_advisory_only_regardless():
    """ratio=0.9 (>=0.8) + env_gate=False → 'advisory_only' (NOT actionable).

    ratio=0.9 (>=0.8) + env_gate=False → 'advisory_only'（非 actionable）。

    Setup / 設定: edge=1.8 bps, cost=2.0 bps → ratio=0.9.
    Even though ratio passes the threshold, env_gate=False forces
    'advisory_only' verdict — the V3 §11 P4 footnote semantic.

    儘管 ratio 通過閾值，env_gate=False 強制 'advisory_only' 判決
    （V3 §11 P4 footnote 語義）。
    """
    advisor = CostEdgeAdvisor(ratio_threshold=0.8)
    result = advisor.evaluate(
        expected_edge_bps=1.8,
        expected_cost_bps=2.0,
        env_gate=False,
    )

    assert math.isclose(result.ratio, 0.9, abs_tol=1e-12)
    assert result.passes_threshold is True
    assert result.env_gate_enabled is False

    verdict = advisor.gate(result)
    assert verdict == "advisory_only", f"expected 'advisory_only', got '{verdict}'"


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: env_gate respect (boundary cases)
# ─────────────────────────────────────────────────────────────────────────────


def test_env_gate_respect_across_modes():
    """env_gate respect across (high ratio / low ratio / NaN) × (on / off).

    跨（高 ratio / 低 ratio / NaN）× （on / off）的 env_gate 遵守。

    Verdict matrix / 判決矩陣:

    | env_gate | ratio   | verdict          |
    |----------|---------|------------------|
    | True     | 1.0     | actionable       |
    | True     | 0.5     | block            |
    | True     | NaN     | block (fail-closed) |
    | False    | 1.0     | advisory_only    |
    | False    | 0.5     | advisory_only    |
    | False    | NaN     | advisory_only    |
    """
    advisor = CostEdgeAdvisor(ratio_threshold=0.8)

    # env=True, high ratio → actionable / env=True，高 ratio → actionable
    r_high = advisor.evaluate(2.0, 2.0, env_gate=True)
    assert advisor.gate(r_high) == "actionable"

    # env=True, low ratio → block
    r_low = advisor.evaluate(1.0, 2.0, env_gate=True)
    assert advisor.gate(r_low) == "block"

    # env=True, degenerate cost → NaN ratio → block (fail-closed) /
    # env=True, 退化 cost → NaN ratio → block
    r_nan = advisor.evaluate(2.0, 0.0, env_gate=True)
    assert math.isnan(r_nan.ratio)
    assert advisor.gate(r_nan) == "block"

    # env=False (default) → advisory_only across all ratios /
    # env=False（預設）→ 跨全 ratio 一律 advisory_only
    for edge, cost in [(2.0, 2.0), (1.0, 2.0), (2.0, 0.0)]:
        r = advisor.evaluate(edge, cost, env_gate=False)
        assert advisor.gate(r) == "advisory_only", (
            f"env=False edge={edge} cost={cost} verdict mismatch"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Edge / 邊緣案例（防禦性）
# ─────────────────────────────────────────────────────────────────────────────


def test_invalid_threshold_raises():
    """ratio_threshold <= 0 or non-finite must raise.

    ratio_threshold <= 0 或非有限必拋。
    """
    with pytest.raises(ValueError):
        CostEdgeAdvisor(ratio_threshold=0.0)
    with pytest.raises(ValueError):
        CostEdgeAdvisor(ratio_threshold=-0.5)
    with pytest.raises(ValueError):
        CostEdgeAdvisor(ratio_threshold=float("inf"))
    with pytest.raises(ValueError):
        CostEdgeAdvisor(ratio_threshold=float("nan"))


def test_nan_input_raises():
    """NaN edge or cost must raise.

    NaN edge 或 cost 必拋。
    """
    advisor = CostEdgeAdvisor()
    with pytest.raises(ValueError):
        advisor.compute_ratio(float("nan"), 2.0)
    with pytest.raises(ValueError):
        advisor.compute_ratio(1.0, float("nan"))


def test_negative_edge_blocks_when_env_on():
    """Negative edge with positive cost → ratio < 0 → 'block' under env=True.

    負 edge + 正 cost → ratio < 0 → env=True 下 'block'。
    """
    advisor = CostEdgeAdvisor()
    result = advisor.evaluate(
        expected_edge_bps=-1.0,
        expected_cost_bps=2.0,
        env_gate=True,
    )
    assert result.ratio == -0.5
    assert advisor.gate(result) == "block"


def test_zero_cost_returns_nan_ratio():
    """expected_cost_bps=0.0 → ratio NaN (degenerate).

    expected_cost_bps=0.0 → ratio NaN（退化）。
    """
    advisor = CostEdgeAdvisor()
    ratio = advisor.compute_ratio(2.0, 0.0)
    assert math.isnan(ratio)


def test_negative_cost_returns_nan_ratio():
    """Negative cost should also return NaN (sentinel for degenerate).

    負 cost 也回 NaN（退化哨兵）。
    """
    advisor = CostEdgeAdvisor()
    ratio = advisor.compute_ratio(2.0, -1.0)
    assert math.isnan(ratio)


def test_module_shortcut_matches_class():
    """Module-level evaluate_cost_edge matches CostEdgeAdvisor.evaluate.

    模組級 evaluate_cost_edge 須等同 CostEdgeAdvisor.evaluate。
    """
    a = evaluate_cost_edge(2.0, 1.5, ratio_threshold=0.8, env_gate=True)
    b = CostEdgeAdvisor(ratio_threshold=0.8).evaluate(2.0, 1.5, env_gate=True)
    assert math.isclose(a.ratio, b.ratio, abs_tol=1e-12)
    assert a.passes_threshold == b.passes_threshold
    assert a.env_gate_enabled == b.env_gate_enabled


def test_env_var_strict_equal_one(monkeypatch):
    """is_env_gate_enabled() strict-equal "1" semantics.

    is_env_gate_enabled() 嚴格 "1" 語義。
    """
    # "1" → True
    monkeypatch.setenv(ENV_VAR_NAME, "1")
    assert is_env_gate_enabled() is True

    # Not set → False / 未設 → False
    monkeypatch.delenv(ENV_VAR_NAME, raising=False)
    assert is_env_gate_enabled() is False

    # "true" → False (strict-equal "1" only) / "true" → False（嚴格 "1" only）
    monkeypatch.setenv(ENV_VAR_NAME, "true")
    assert is_env_gate_enabled() is False

    # "0" → False
    monkeypatch.setenv(ENV_VAR_NAME, "0")
    assert is_env_gate_enabled() is False

    # " 1" (leading space) → False (no trim) / " 1"（前空白）→ False（不修剪）
    monkeypatch.setenv(ENV_VAR_NAME, " 1")
    assert is_env_gate_enabled() is False

    # "1 " (trailing space) → False / "1 "（後空白）→ False
    monkeypatch.setenv(ENV_VAR_NAME, "1 ")
    assert is_env_gate_enabled() is False


def test_gate_takes_raw_ratio_too():
    """gate() accepts raw float ratio in addition to CostEdgeResult.

    gate() 也接受原始 float ratio（除 CostEdgeResult 外）。
    """
    advisor = CostEdgeAdvisor(ratio_threshold=0.8)
    # Raw ratio path / 原始 ratio 路徑
    assert advisor.gate(1.0, env_gate=True) == "actionable"
    assert advisor.gate(0.5, env_gate=True) == "block"
    assert advisor.gate(0.9, env_gate=False) == "advisory_only"
    # NaN raw ratio path / NaN 原始 ratio 路徑
    assert advisor.gate(float("nan"), env_gate=True) == "block"


def test_default_env_read_from_environment(monkeypatch):
    """When env_gate=None, advisor reads `OPENCLAW_COST_EDGE_ADVISOR` env.

    env_gate=None 時 advisor 讀 `OPENCLAW_COST_EDGE_ADVISOR` env。
    """
    advisor = CostEdgeAdvisor(ratio_threshold=0.8)

    # env unset → advisory_only / env 未設 → advisory_only
    monkeypatch.delenv(ENV_VAR_NAME, raising=False)
    result = advisor.evaluate(2.0, 2.0, env_gate=None)
    assert result.env_gate_enabled is False
    assert advisor.gate(result) == "advisory_only"

    # env=1 → actionable / env=1 → actionable
    monkeypatch.setenv(ENV_VAR_NAME, "1")
    result2 = advisor.evaluate(2.0, 2.0, env_gate=None)
    assert result2.env_gate_enabled is True
    assert advisor.gate(result2) == "actionable"
