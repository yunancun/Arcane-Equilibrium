"""
Tests for Layer 2 autonomous escalation rules (G3-06 Phase A).
Layer 2 自主升級規則測試（G3-06 Phase A）。

Coverage:
  - Default L0 path (low signal, low notional, no news)
  - L1 escalation triggered by signal_strength
  - L1 escalation triggered by position_notional
  - L2 escalation: L1 uncertainty + high notional → L2
  - Cost-aware: L1 uncertainty + LOW notional → stays at L1
  - News severity → L2 trigger when uncertain
  - cost_edge_ratio threshold → L2 trigger
  - Budget cap (calls/24h) → forces L1 even if criteria met
  - Budget cap (remaining USD) → forces L1
  - Threshold env override (LayerEscalationConfig.from_env)
  - Empty context → L0 default
  - Disabled config (default OFF) → L0 pass-through
  - tier_rank ordering
  - Safe input coercion (None / NaN / strings)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.layer2_escalation import (
    EscalationDecision,
    EscalationTier,
    LayerEscalationConfig,
    decide_escalation_tier,
    tier_rank,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures / 測試夾具
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def enabled_config() -> LayerEscalationConfig:
    """Standard enabled config with default thresholds / 啟用的預設配置."""
    cfg = LayerEscalationConfig()
    cfg.enabled = True
    return cfg


# ═══════════════════════════════════════════════════════════════════════════════
# Tier ordering / 層級排序
# ═══════════════════════════════════════════════════════════════════════════════


def test_tier_rank_ordering():
    assert tier_rank(EscalationTier.L0_DETERMINISTIC) == 0
    assert tier_rank(EscalationTier.L1_LOCAL_LLM) == 1
    assert tier_rank(EscalationTier.L2_CLOUD_LLM) == 2
    # Sanity: monotonic
    assert (
        tier_rank(EscalationTier.L0_DETERMINISTIC)
        < tier_rank(EscalationTier.L1_LOCAL_LLM)
        < tier_rank(EscalationTier.L2_CLOUD_LLM)
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Phase A safety: default-disabled passthrough / Phase A 安全：預設關閉
# ═══════════════════════════════════════════════════════════════════════════════


def test_default_disabled_returns_l0():
    """Phase A safety contract: when disabled, ALL contexts return L0."""
    decision = decide_escalation_tier(
        context={
            "signal_strength": 0.99,
            "position_notional_usdt": 999_999.0,
            "agent_uncertainty_flag": True,
            "news_severity_recent": 1.0,
            "cost_edge_ratio": 5.0,
            "l2_budget_remaining_usd": 100.0,
        },
        # No config passed → default LayerEscalationConfig() with enabled=False
    )
    assert decision.target_tier == EscalationTier.L0_DETERMINISTIC
    assert "escalation_disabled" in decision.reasons
    assert decision.budget_estimate_usd == 0.0


def test_default_config_is_disabled():
    """Default config must be disabled (Phase A pass-through)."""
    cfg = LayerEscalationConfig()
    assert cfg.enabled is False


# ═══════════════════════════════════════════════════════════════════════════════
# L0 default cases / L0 預設情境
# ═══════════════════════════════════════════════════════════════════════════════


def test_empty_context_returns_l0(enabled_config):
    """Empty context → all defaults to 0/False → L0."""
    decision = decide_escalation_tier(context={}, config=enabled_config)
    assert decision.target_tier == EscalationTier.L0_DETERMINISTIC
    assert "no_l1_trigger_default_l0" in decision.reasons
    assert decision.budget_estimate_usd == 0.0


def test_none_context_returns_l0(enabled_config):
    """None context → safe default → L0."""
    decision = decide_escalation_tier(context=None, config=enabled_config)
    assert decision.target_tier == EscalationTier.L0_DETERMINISTIC


def test_low_everything_stays_l0(enabled_config):
    """All inputs below threshold → L0."""
    decision = decide_escalation_tier(
        context={
            "signal_strength": 0.1,
            "position_notional_usdt": 5.0,
            "cost_edge_ratio": 0.0,
            "agent_uncertainty_flag": False,
            "news_severity_recent": 0.0,
        },
        config=enabled_config,
    )
    assert decision.target_tier == EscalationTier.L0_DETERMINISTIC


# ═══════════════════════════════════════════════════════════════════════════════
# L1 escalation / L1 升級
# ═══════════════════════════════════════════════════════════════════════════════


def test_signal_above_threshold_escalates_l1(enabled_config):
    """signal_strength ≥ l1_signal_min → L1."""
    decision = decide_escalation_tier(
        context={
            "signal_strength": 0.6,
            "position_notional_usdt": 0.0,
        },
        config=enabled_config,
    )
    assert decision.target_tier == EscalationTier.L1_LOCAL_LLM
    # Reason mentions signal threshold cross
    assert any("signal_strength" in r for r in decision.reasons)
    assert decision.budget_estimate_usd > 0
    assert decision.budget_estimate_usd < 0.5  # L1 ~ $0.01


def test_position_above_threshold_escalates_l1(enabled_config):
    """position_notional_usdt ≥ l1_position_min_usdt → L1."""
    decision = decide_escalation_tier(
        context={
            "signal_strength": 0.0,
            "position_notional_usdt": 100.0,
            "agent_uncertainty_flag": False,
        },
        config=enabled_config,
    )
    assert decision.target_tier == EscalationTier.L1_LOCAL_LLM
    assert any("position_notional" in r for r in decision.reasons)


def test_l1_uncertain_low_notional_stays_l1(enabled_config):
    """L1 fires + agent uncertain BUT no material-risk signal → stays L1 (cost-aware)."""
    decision = decide_escalation_tier(
        context={
            "signal_strength": 0.6,  # triggers L1
            "agent_uncertainty_flag": True,
            "position_notional_usdt": 100.0,  # under l2_position_min (500)
            "cost_edge_ratio": 0.0,
            "news_severity_recent": 0.0,
            "recent_l2_calls_24h": 0,
            "l2_budget_remaining_usd": 5.0,
        },
        config=enabled_config,
    )
    assert decision.target_tier == EscalationTier.L1_LOCAL_LLM
    assert "uncertain_but_no_material_risk_signal_stay_l1" in decision.reasons


# ═══════════════════════════════════════════════════════════════════════════════
# L2 escalation / L2 升級
# ═══════════════════════════════════════════════════════════════════════════════


def test_l2_via_high_notional_and_uncertainty(enabled_config):
    """L1 + agent uncertain + high notional + budget OK → L2."""
    decision = decide_escalation_tier(
        context={
            "signal_strength": 0.6,
            "agent_uncertainty_flag": True,
            "position_notional_usdt": 1000.0,  # >= 500 (l2_position_min)
            "recent_l2_calls_24h": 0,
            "l2_budget_remaining_usd": 5.0,
        },
        config=enabled_config,
    )
    assert decision.target_tier == EscalationTier.L2_CLOUD_LLM
    assert "all_l2_gates_passed" in decision.reasons
    assert decision.budget_estimate_usd >= 0.5  # L2 ~ $1


def test_l2_via_cost_edge_ratio(enabled_config):
    """cost_edge_ratio ≥ 0.8 + L1 + uncertain + budget OK → L2 (DOC-01 #13)."""
    decision = decide_escalation_tier(
        context={
            "signal_strength": 0.6,
            "agent_uncertainty_flag": True,
            "position_notional_usdt": 100.0,  # below l2 notional but cost_edge fires
            "cost_edge_ratio": 0.85,
            "recent_l2_calls_24h": 0,
            "l2_budget_remaining_usd": 5.0,
        },
        config=enabled_config,
    )
    assert decision.target_tier == EscalationTier.L2_CLOUD_LLM
    assert any("cost_edge_ratio" in r for r in decision.reasons)


def test_l2_via_news_severity(enabled_config):
    """news_severity_recent ≥ 0.7 + L1 + uncertain → L2 (urgent)."""
    decision = decide_escalation_tier(
        context={
            "signal_strength": 0.6,
            "agent_uncertainty_flag": True,
            "position_notional_usdt": 100.0,
            "news_severity_recent": 0.85,
            "recent_l2_calls_24h": 0,
            "l2_budget_remaining_usd": 5.0,
        },
        config=enabled_config,
    )
    assert decision.target_tier == EscalationTier.L2_CLOUD_LLM
    assert any("news_severity" in r for r in decision.reasons)


def test_l2_requires_uncertainty(enabled_config):
    """High notional + L1 fires BUT agent NOT uncertain → stays L1."""
    decision = decide_escalation_tier(
        context={
            "signal_strength": 0.6,
            "agent_uncertainty_flag": False,  # L1 confident
            "position_notional_usdt": 10_000.0,
            "recent_l2_calls_24h": 0,
            "l2_budget_remaining_usd": 5.0,
        },
        config=enabled_config,
    )
    assert decision.target_tier == EscalationTier.L1_LOCAL_LLM
    assert "agent_uncertainty_flag=false_stay_l1" in decision.reasons


# ═══════════════════════════════════════════════════════════════════════════════
# Hard ceilings (budget protection) / 硬上限（預算保護）
# ═══════════════════════════════════════════════════════════════════════════════


def test_l2_calls_cap_forces_l1(enabled_config):
    """recent_l2_calls_24h >= cap → forces downgrade to L1 (root principle #6+#13)."""
    decision = decide_escalation_tier(
        context={
            "signal_strength": 0.6,
            "agent_uncertainty_flag": True,
            "position_notional_usdt": 5_000.0,
            "news_severity_recent": 0.95,
            "cost_edge_ratio": 1.5,
            "recent_l2_calls_24h": 99,  # >> cap (10)
            "l2_budget_remaining_usd": 100.0,  # plenty of budget
        },
        config=enabled_config,
    )
    assert decision.target_tier == EscalationTier.L1_LOCAL_LLM
    assert any("budget_cap_l2_calls_24h" in r for r in decision.reasons)


def test_l2_remaining_budget_below_min_forces_l1(enabled_config):
    """l2_budget_remaining_usd < min → forces downgrade to L1."""
    decision = decide_escalation_tier(
        context={
            "signal_strength": 0.6,
            "agent_uncertainty_flag": True,
            "position_notional_usdt": 5_000.0,
            "news_severity_recent": 0.95,
            "recent_l2_calls_24h": 0,
            "l2_budget_remaining_usd": 0.10,  # below min 0.50
        },
        config=enabled_config,
    )
    assert decision.target_tier == EscalationTier.L1_LOCAL_LLM
    assert any("budget_cap_remaining" in r for r in decision.reasons)


# ═══════════════════════════════════════════════════════════════════════════════
# Config / from_env / 配置覆蓋
# ═══════════════════════════════════════════════════════════════════════════════


def test_config_from_env_overrides():
    """Operator can override thresholds via env vars."""
    env = {
        "OPENCLAW_L2_ESCALATION_ENABLED": "true",
        "OPENCLAW_L2_ESCALATION_L1_SIGNAL_MIN": "0.25",
        "OPENCLAW_L2_ESCALATION_L1_POSITION_MIN": "10.0",
        "OPENCLAW_L2_ESCALATION_L2_POSITION_MIN": "200.0",
        "OPENCLAW_L2_ESCALATION_L2_COST_EDGE_MAX": "0.5",
        "OPENCLAW_L2_ESCALATION_L2_NEWS_MIN": "0.4",
        "OPENCLAW_L2_ESCALATION_L2_CALLS_CAP": "25",
        "OPENCLAW_L2_ESCALATION_L2_MIN_BUDGET": "0.10",
    }
    with patch.dict(os.environ, env, clear=False):
        cfg = LayerEscalationConfig.from_env()
    assert cfg.enabled is True
    assert cfg.l1_signal_min == 0.25
    assert cfg.l1_position_min_usdt == 10.0
    assert cfg.l2_position_min_usdt == 200.0
    assert cfg.l2_cost_edge_max == 0.5
    assert cfg.l2_news_severity_min == 0.4
    assert cfg.l2_calls_24h_cap == 25
    assert cfg.l2_min_budget_usd == 0.10


def test_config_from_env_missing_uses_defaults():
    """Missing env vars → dataclass defaults preserved."""
    # Clear all known escalation env vars
    keys = [k for k in os.environ if k.startswith("OPENCLAW_L2_ESCALATION_")]
    with patch.dict(os.environ, {k: "" for k in keys}, clear=False):
        for k in keys:
            os.environ.pop(k, None)
        cfg = LayerEscalationConfig.from_env()
    assert cfg.enabled is False  # default OFF
    assert cfg.l1_signal_min == 0.5
    assert cfg.l2_calls_24h_cap == 10


def test_config_from_env_bad_float_uses_default(caplog):
    """Garbage env value → default + warning logged (fail-soft)."""
    with patch.dict(
        os.environ,
        {
            "OPENCLAW_L2_ESCALATION_ENABLED": "1",
            "OPENCLAW_L2_ESCALATION_L1_SIGNAL_MIN": "not_a_number",
        },
        clear=False,
    ):
        cfg = LayerEscalationConfig.from_env()
    assert cfg.l1_signal_min == 0.5  # default preserved


# ═══════════════════════════════════════════════════════════════════════════════
# Safe input coercion / 安全輸入轉型
# ═══════════════════════════════════════════════════════════════════════════════


def test_string_inputs_coerced(enabled_config):
    """Non-numeric strings → safe default (0.0) → L0."""
    decision = decide_escalation_tier(
        context={
            "signal_strength": "not a number",
            "position_notional_usdt": None,
        },
        config=enabled_config,
    )
    assert decision.target_tier == EscalationTier.L0_DETERMINISTIC


def test_nan_inputs_treated_as_zero(enabled_config):
    """NaN / Inf → fail-closed to default → no spurious L1 trigger."""
    decision = decide_escalation_tier(
        context={
            "signal_strength": float("nan"),
            "position_notional_usdt": float("inf"),
        },
        config=enabled_config,
    )
    # Both rejected → default 0 → no L1 trigger
    assert decision.target_tier == EscalationTier.L0_DETERMINISTIC


# ═══════════════════════════════════════════════════════════════════════════════
# EscalationDecision serialization / 序列化
# ═══════════════════════════════════════════════════════════════════════════════


def test_decision_to_dict_shape(enabled_config):
    """Decision serializes to dict with expected keys (for IPC / audit logging)."""
    decision = decide_escalation_tier(
        context={"signal_strength": 0.6}, config=enabled_config
    )
    d = decision.to_dict()
    assert set(d.keys()) == {"target_tier", "reasons", "budget_estimate_usd"}
    assert d["target_tier"] == "l1_local_llm"
    assert isinstance(d["reasons"], list)
    assert isinstance(d["budget_estimate_usd"], float)
