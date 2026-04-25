"""Unit tests for canary_promoter (G4-03 Phase A, 2026-04-25).
canary_promoter 單元測試（G4-03 Phase A）。

Pure mock tests — no live PG, no DB rows mutated. Verifies the
eligibility gate logic per draft thresholds + state machine call shape.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from program_code.ml_training import canary_promoter as cp
from program_code.ml_training.canary_promoter import (
    CanaryDecision,
    CanaryThresholds,
    EvaluationResult,
    evaluate_canary_eligibility,
    is_auto_promote_enabled,
)
from program_code.ml_training.model_registry import (
    CANARY_PROMOTING,
    CANARY_PRODUCTION,
    CANARY_REJECTED,
    CANARY_SHADOW,
    VERDICT_NO_SHIP,
    VERDICT_SHADOW_ONLY,
    VERDICT_SHOULD_SHIP,
)


# ---------- Fixtures ----------

NOW = datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc)


def _row(
    *,
    rid: int = 1,
    strategy: str = "grid_trading",
    engine_mode: str = "demo",
    quantile: str = "q50",
    canary_status: str = CANARY_SHADOW,
    verdict: str = VERDICT_SHADOW_ONLY,
    sample_size: int = 600,
    age_days: float = 2.0,
) -> dict:
    return {
        "id": rid,
        "strategy": strategy,
        "engine_mode": engine_mode,
        "quantile": quantile,
        "canary_status": canary_status,
        "verdict": verdict,
        "train_date": (NOW - timedelta(days=age_days)).date(),
        "training_sample_size": sample_size,
        "created_at": NOW - timedelta(days=age_days),
    }


def _cur_with_obs(total: int, agreed: int) -> MagicMock:
    cur = MagicMock()
    cur.fetchone = MagicMock(return_value=(total, agreed))
    return cur


# ---------- Default-OFF env gate ----------


def test_g4_03_is_auto_promote_enabled_default_off(monkeypatch):
    # Env unset → False.
    # Env 未設 → False。
    monkeypatch.delenv("OPENCLAW_AUTO_PROMOTE_ENABLED", raising=False)
    assert is_auto_promote_enabled() is False


def test_g4_03_is_auto_promote_enabled_explicit_on(monkeypatch):
    # "1" / "true" / "yes" all enable.
    # 三種值都啟用。
    for v in ("1", "true", "yes"):
        monkeypatch.setenv("OPENCLAW_AUTO_PROMOTE_ENABLED", v)
        assert is_auto_promote_enabled() is True


def test_g4_03_is_auto_promote_enabled_garbage_off(monkeypatch):
    # "no" / "off" / "0" / random string → False.
    # 雜訊值不啟用。
    for v in ("no", "off", "0", "maybe"):
        monkeypatch.setenv("OPENCLAW_AUTO_PROMOTE_ENABLED", v)
        assert is_auto_promote_enabled() is False


# ---------- shadow → promoting eligibility ----------


def test_g4_03_shadow_eligible_should_ship_promotes():
    row = _row(verdict=VERDICT_SHOULD_SHIP, sample_size=600, age_days=2.0)
    res = evaluate_canary_eligibility(row, MagicMock(), CanaryThresholds(), NOW)
    assert res.decision is CanaryDecision.PROMOTE
    assert res.target_status == CANARY_PROMOTING


def test_g4_03_shadow_eligible_shadow_only_promotes():
    # shadow_only verdict is also eligible (per draft).
    # shadow_only verdict 也合格。
    row = _row(verdict=VERDICT_SHADOW_ONLY)
    res = evaluate_canary_eligibility(row, MagicMock(), CanaryThresholds(), NOW)
    assert res.decision is CanaryDecision.PROMOTE


def test_g4_03_shadow_no_ship_holds():
    # no_ship never registered, but defensive: verdict is filtered.
    # no_ship 不該入 registry，但防禦性測試。
    row = _row(verdict=VERDICT_NO_SHIP)
    res = evaluate_canary_eligibility(row, MagicMock(), CanaryThresholds(), NOW)
    assert res.decision is CanaryDecision.HOLD
    assert any("not in eligible" in r for r in res.reasons)


def test_g4_03_shadow_low_sample_size_holds():
    row = _row(sample_size=100)
    res = evaluate_canary_eligibility(row, MagicMock(), CanaryThresholds(), NOW)
    assert res.decision is CanaryDecision.HOLD
    assert any("training_sample_size=100" in r for r in res.reasons)


def test_g4_03_shadow_too_young_holds():
    # 12 hours old → less than 1d minimum → Hold.
    # 12h 太年輕，<1d 預設門檻 → Hold。
    row = _row(age_days=0.5)
    res = evaluate_canary_eligibility(row, MagicMock(), CanaryThresholds(), NOW)
    assert res.decision is CanaryDecision.HOLD
    assert any("age" in r for r in res.reasons)


# ---------- promoting → production eligibility ----------


def test_g4_03_promoting_full_window_promotes_to_production():
    # 8 days old + 600 obs + 65% agreement → promote.
    # 8d 老 + 600 觀測 + 65% agreement → 升 production。
    row = _row(canary_status=CANARY_PROMOTING, age_days=8.0)
    cur = _cur_with_obs(total=600, agreed=int(600 * 0.65))
    res = evaluate_canary_eligibility(row, cur, CanaryThresholds(), NOW)
    assert res.decision is CanaryDecision.PROMOTE
    assert res.target_status == CANARY_PRODUCTION
    assert res.metrics["agreement_full_window"] == pytest.approx(0.65, abs=0.001)


def test_g4_03_promoting_too_young_holds():
    row = _row(canary_status=CANARY_PROMOTING, age_days=2.0)
    cur = _cur_with_obs(total=1000, agreed=900)
    res = evaluate_canary_eligibility(row, cur, CanaryThresholds(), NOW)
    assert res.decision is CanaryDecision.HOLD
    assert any("min" in r and "d" in r for r in res.reasons)


def test_g4_03_promoting_insufficient_obs_holds():
    row = _row(canary_status=CANARY_PROMOTING, age_days=8.0)
    cur = _cur_with_obs(total=200, agreed=180)
    res = evaluate_canary_eligibility(row, cur, CanaryThresholds(), NOW)
    assert res.decision is CanaryDecision.HOLD
    assert any("observations 200" in r for r in res.reasons)


def test_g4_03_promoting_low_agreement_holds():
    # 8d + 600 obs + 50% agreement (below 60% threshold) → Hold.
    # 8d + 600 obs + 50% agreement < 60% 門檻 → Hold。
    row = _row(canary_status=CANARY_PROMOTING, age_days=8.0)
    cur = _cur_with_obs(total=600, agreed=300)
    res = evaluate_canary_eligibility(row, cur, CanaryThresholds(), NOW)
    assert res.decision is CanaryDecision.HOLD
    assert any("agreement 50.00%" in r for r in res.reasons)


# ---------- promoting → rejected (auto-retire on disagreement collapse) ----------


def test_g4_03_promoting_low_3d_agreement_retires():
    # 4d old promoting row; 3d agreement window 30% < 40% strict floor → reject.
    # 4d 老 promoting；3d agreement 30% < 40% 嚴格底線 → 拒。
    row = _row(canary_status=CANARY_PROMOTING, age_days=4.0)
    cur = _cur_with_obs(total=100, agreed=30)
    res = evaluate_canary_eligibility(row, cur, CanaryThresholds(), NOW)
    assert res.decision is CanaryDecision.RETIRE
    assert res.target_status == CANARY_REJECTED
    assert any("auto-reject" in r for r in res.reasons)


# ---------- Terminal states ----------


def test_g4_03_production_noop():
    row = _row(canary_status=CANARY_PRODUCTION)
    res = evaluate_canary_eligibility(row, MagicMock(), CanaryThresholds(), NOW)
    assert res.decision is CanaryDecision.HOLD
    assert any("terminal" in r for r in res.reasons)


def test_g4_03_rejected_noop():
    row = _row(canary_status=CANARY_REJECTED)
    res = evaluate_canary_eligibility(row, MagicMock(), CanaryThresholds(), NOW)
    assert res.decision is CanaryDecision.HOLD


# ---------- Scanner: auto_promote_eligible_models ----------


def test_g4_03_scanner_dry_run_does_not_call_transition(monkeypatch):
    # Ensure dry_run=True never calls transition_canary_status (state machine).
    # dry_run=True 永不呼叫狀態機 → DB 不變。
    fake_conn = MagicMock()
    fake_cur = MagicMock()
    fake_conn.__enter__.return_value = fake_conn
    fake_conn.cursor.return_value.__enter__.return_value = fake_cur

    # First fetchall: registry rows. Second fetchone (per row): obs counts.
    fake_cur.description = [
        ("id",), ("strategy",), ("engine_mode",), ("quantile",),
        ("canary_status",), ("verdict",), ("train_date",),
        ("training_sample_size",), ("created_at",),
    ]
    fake_cur.fetchall.return_value = [
        (1, "grid_trading", "demo", "q50", CANARY_SHADOW, VERDICT_SHADOW_ONLY,
         (NOW - timedelta(days=2)).date(), 600, NOW - timedelta(days=2)),
    ]
    fake_cur.fetchone.return_value = (0, 0)

    transition_called = []
    monkeypatch.setattr(
        cp, "transition_canary_status",
        lambda *a, **kw: transition_called.append((a, kw)) or True,
    )

    with patch.object(cp, "_connect", return_value=fake_conn, create=True), \
            patch("program_code.ml_training.model_registry._connect", return_value=fake_conn):
        results = cp.auto_promote_eligible_models(dry_run=True, now=NOW)

    assert len(results) == 1
    assert results[0].decision is CanaryDecision.PROMOTE
    assert transition_called == [], "dry_run must not call transition"


def test_g4_03_scanner_apply_requires_env_gate(monkeypatch):
    # dry_run=False but env gate unset → still does NOT apply.
    # dry_run=False 但 env 未設 → 仍不套用。
    fake_conn = MagicMock()
    fake_cur = MagicMock()
    fake_conn.__enter__.return_value = fake_conn
    fake_conn.cursor.return_value.__enter__.return_value = fake_cur
    fake_cur.description = [
        ("id",), ("strategy",), ("engine_mode",), ("quantile",),
        ("canary_status",), ("verdict",), ("train_date",),
        ("training_sample_size",), ("created_at",),
    ]
    fake_cur.fetchall.return_value = [
        (1, "grid_trading", "demo", "q50", CANARY_SHADOW, VERDICT_SHADOW_ONLY,
         (NOW - timedelta(days=2)).date(), 600, NOW - timedelta(days=2)),
    ]
    fake_cur.fetchone.return_value = (0, 0)

    transition_called = []
    monkeypatch.setattr(
        cp, "transition_canary_status",
        lambda *a, **kw: transition_called.append((a, kw)) or True,
    )
    monkeypatch.delenv("OPENCLAW_AUTO_PROMOTE_ENABLED", raising=False)

    with patch("program_code.ml_training.model_registry._connect", return_value=fake_conn):
        results = cp.auto_promote_eligible_models(dry_run=False, now=NOW)

    assert len(results) == 1
    assert transition_called == [], "env gate must guard apply path"


def test_g4_03_thresholds_from_env_overrides(monkeypatch):
    monkeypatch.setenv("OPENCLAW_CANARY_SHADOW_MIN_SAMPLES", "300")
    monkeypatch.setenv("OPENCLAW_CANARY_PROMOTING_MIN_AGREEMENT", "0.75")
    th = CanaryThresholds.from_env()
    assert th.shadow_min_training_samples == 300
    assert th.promoting_min_agreement_pct == pytest.approx(0.75)
