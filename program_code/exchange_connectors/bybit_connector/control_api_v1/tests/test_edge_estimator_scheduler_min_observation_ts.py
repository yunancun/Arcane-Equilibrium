"""
EDGE-DIAG-2 (2026-04-28) — tests for EdgeEstimatorScheduler.min_observation_ts.

Covers:
  1. Default cutoff parses to expected post-fix UTC timestamp
  2. Explicit ctor argument overrides class default
  3. OPENCLAW_EDGE_MIN_OBSERVATION_TS env var overrides class default
  4. Invalid env var falls back to None (cutoff disabled, log warning)
  5. Naive ctor datetime is normalized to UTC
  6. status() surfaces min_observation_ts as ISO-8601 string

EDGE-DIAG-2（2026-04-28）— EdgeEstimatorScheduler.min_observation_ts 測試。
"""

from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path

import pytest


# ───── PATH SETUP / 路徑設置 ─────────────────────────────────────────────────
_THIS_DIR = Path(__file__).resolve().parent
_CONTROL_API = _THIS_DIR.parent
_BYBIT_CONNECTOR = _CONTROL_API.parent
_EXCHANGE_CONNECTORS = _BYBIT_CONNECTOR.parent
_PROGRAM_CODE = _EXCHANGE_CONNECTORS.parent
_SRV_ROOT = _PROGRAM_CODE.parent
for _p in (str(_CONTROL_API), str(_SRV_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


from app.edge_estimator_scheduler import EdgeEstimatorScheduler  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Each test starts with no env override unless it sets one explicitly."""
    monkeypatch.delenv("OPENCLAW_EDGE_MIN_OBSERVATION_TS", raising=False)
    yield


def test_default_cutoff_is_post_p013_fix_in_utc():
    """Default DEFAULT_MIN_OBSERVATION_TS_ISO must parse to 2026-04-22 21:00 UTC.
    確認預設 cutoff 為 2026-04-22 21:00 UTC（P0-13 ATR fix + V2 SWAP 部署後）。"""
    sched = EdgeEstimatorScheduler()
    expected = datetime.datetime(2026, 4, 22, 21, 0, 0, tzinfo=datetime.timezone.utc)
    assert sched._min_observation_ts == expected


def test_explicit_ctor_arg_wins_over_default():
    """Explicit ctor min_observation_ts beats class default + env."""
    custom = datetime.datetime(2026, 4, 25, 0, 0, 0, tzinfo=datetime.timezone.utc)
    sched = EdgeEstimatorScheduler(min_observation_ts=custom)
    assert sched._min_observation_ts == custom


def test_env_var_overrides_class_default(monkeypatch):
    """OPENCLAW_EDGE_MIN_OBSERVATION_TS env var beats class default."""
    monkeypatch.setenv("OPENCLAW_EDGE_MIN_OBSERVATION_TS", "2026-05-01T12:00:00+00:00")
    sched = EdgeEstimatorScheduler()
    expected = datetime.datetime(2026, 5, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
    assert sched._min_observation_ts == expected


def test_invalid_env_var_disables_cutoff(monkeypatch, caplog):
    """Bad env value → fall back to None + log warning (don't crash startup)."""
    monkeypatch.setenv("OPENCLAW_EDGE_MIN_OBSERVATION_TS", "not-a-date")
    with caplog.at_level("WARNING"):
        sched = EdgeEstimatorScheduler()
    assert sched._min_observation_ts is None
    assert any("OPENCLAW_EDGE_MIN_OBSERVATION_TS" in r.message for r in caplog.records)


def test_naive_ctor_datetime_normalized_to_utc():
    """Naive datetime gets UTC tzinfo attached so SQL comparison is well-defined."""
    naive = datetime.datetime(2026, 4, 23, 0, 0, 0)
    sched = EdgeEstimatorScheduler(min_observation_ts=naive)
    assert sched._min_observation_ts.tzinfo == datetime.timezone.utc


def test_status_surfaces_cutoff_as_iso_string():
    """status() must include min_observation_ts ISO-8601 string for healthcheck visibility."""
    sched = EdgeEstimatorScheduler()
    s = sched.status()
    assert "min_observation_ts" in s
    assert s["min_observation_ts"] == "2026-04-22T21:00:00+00:00"


def test_status_min_observation_ts_none_when_invalid_env(monkeypatch):
    """status() reports None when env var is invalid (disabled cutoff path)."""
    monkeypatch.setenv("OPENCLAW_EDGE_MIN_OBSERVATION_TS", "garbage")
    sched = EdgeEstimatorScheduler()
    s = sched.status()
    assert s["min_observation_ts"] is None
