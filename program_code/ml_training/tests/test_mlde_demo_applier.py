from __future__ import annotations

import pytest

from ml_training.mlde_demo_applier import (
    DemoApplierConfig,
    _already_applied,
    _noop_audit_payload,
    _record_noop_audit,
    build_risk_patch,
    build_strategy_patch,
    should_create_live_candidate,
)


class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.executed = []

    def execute(self, sql, params=()):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.rows.pop(0)


def test_grid_dream_spacing_maps_to_bounded_runtime_params():
    cfg = DemoApplierConfig(max_param_delta_pct=0.20)
    patch = build_strategy_patch(
        strategy_name="grid_trading",
        recommendation_type="parameter_proposal",
        payload={
            "param_name": "grid_spacing_bps",
            "suggested_change_pct": 0.50,
            "direction": "widen",
        },
        current_params={"cooldown_ms": 120_000, "max_cooldown_boost": 2.0},
        param_ranges=[
            {
                "name": "cooldown_ms",
                "min": 30_000,
                "max": 600_000,
                "step": 30_000,
                "agent_adjustable": True,
            },
            {
                "name": "max_cooldown_boost",
                "min": 0.0,
                "max": 10.0,
                "step": 0.5,
                "agent_adjustable": True,
            },
        ],
        cfg=cfg,
    )

    assert patch == {"cooldown_ms": 144_000, "max_cooldown_boost": pytest.approx(2.4)}


def test_veto_reduces_conf_scale_without_param_range():
    cfg = DemoApplierConfig(veto_conf_scale_step_pct=0.10, max_param_delta_pct=0.20)
    patch = build_strategy_patch(
        strategy_name="ma_crossover",
        recommendation_type="veto",
        payload={},
        current_params={"conf_scale": 1.0},
        param_ranges=[],
        cfg=cfg,
    )

    assert patch == {"conf_scale": pytest.approx(0.9)}


def test_overtrading_regret_reduces_demo_risk_and_leverage():
    cfg = DemoApplierConfig(max_risk_delta_pct=0.10)
    patch = build_risk_patch(
        payload={"net_regret_direction": "overtrading"},
        current_risk_config={
            "limits": {
                "per_trade_risk_pct": 0.02,
                "leverage_max": 10.0,
                "open_positions_max": 5,
            }
        },
        recommendation_type="regret_summary",
        cfg=cfg,
    )

    assert patch["limits"]["per_trade_risk_pct"] == pytest.approx(0.018)
    assert patch["limits"]["leverage_max"] == pytest.approx(9.0)
    assert patch["limits"]["open_positions_max"] == 4


def test_explicit_risk_patch_is_delta_bounded():
    cfg = DemoApplierConfig(max_risk_delta_pct=0.10)
    patch = build_risk_patch(
        payload={"risk_patch": {"limits": {"leverage_max": 50.0}}},
        current_risk_config={"limits": {"leverage_max": 10.0}},
        recommendation_type="regret_summary",
        cfg=cfg,
    )

    assert patch == {"limits": {"leverage_max": pytest.approx(11.0)}}


def test_live_candidate_requires_strong_demo_evidence():
    cfg = DemoApplierConfig(
        live_candidate_min_net_bps=5.0,
        live_candidate_min_confidence=0.65,
        live_candidate_min_samples=30,
    )

    assert should_create_live_candidate(
        {"expected_net_bps": 7.0, "confidence": 0.8, "sample_count": 40},
        cfg,
    )
    assert not should_create_live_candidate(
        {"expected_net_bps": 7.0, "confidence": 0.6, "sample_count": 40},
        cfg,
    )


def test_noop_audit_payload_reports_threshold_context():
    cfg = DemoApplierConfig(
        lookback_hours=72,
        min_confidence=0.4,
        min_samples=8,
        max_recommendations=12,
    )
    cur = _Cursor([(10, 4, 0)])

    payload = _noop_audit_payload(cur, cfg)

    assert payload["reason"] == "no_eligible_recommendations"
    assert payload["lookback_hours"] == 72
    assert payload["min_confidence"] == pytest.approx(0.4)
    assert payload["min_samples"] == 8
    assert payload["max_recommendations"] == 12
    assert payload["lookback_recommendations"] == 10
    assert payload["demo_recommendations"] == 4
    assert payload["eligible_recommendations"] == 0


def test_record_noop_audit_writes_deduped_skipped_row(monkeypatch):
    cfg = DemoApplierConfig()
    cur = _Cursor([(3, 3, 0)])
    recorded = {}

    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._already_applied",
        lambda _cur, _fp, _cfg: False,
    )

    def fake_record_application(cur, **kwargs):
        recorded.update(kwargs)
        return 123

    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._record_application",
        fake_record_application,
    )

    result = _record_noop_audit(cur, cfg)

    assert result == {
        "status": "skipped",
        "reason": "no_eligible_recommendations",
        "target": "mlde_demo_applier",
        "eligible_recommendations": 0,
    }
    assert recorded["application_type"] == "strategy_params"
    assert recorded["target_name"] == "mlde_demo_applier"
    assert recorded["status"] == "skipped"
    assert recorded["reason"] == "no_eligible_recommendations"
    assert recorded["payload"]["fingerprint"]


def test_record_noop_audit_dedupes_recent_fingerprint(monkeypatch):
    cfg = DemoApplierConfig()
    cur = _Cursor([(3, 3, 0)])
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._already_applied",
        lambda _cur, _fp, _cfg: True,
    )

    result = _record_noop_audit(cur, cfg)

    assert result["status"] == "skipped"
    assert result["reason"] == "no_eligible_recommendations_deduped"


def test_already_applied_dedupe_includes_skipped_rows():
    cfg = DemoApplierConfig()
    cur = _Cursor([(False,)])

    assert not _already_applied(cur, "abc", cfg)

    sql = cur.executed[0][0]
    assert "status IN ('applied', 'dry_run', 'skipped')" in sql
