"""Tests for backfill_directive_outcomes helper script (Phase 4 4-03).

backfill_directive_outcomes 輔助腳本測試。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


# Load the helper script as a module without going through a package import
# (it lives in helper_scripts/phase4/, not in any package).
# 透過 importlib 載入 helper script（位於 helper_scripts/phase4/，不在 package 中）。
_HELPER_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "helper_scripts"
    / "phase4"
    / "backfill_directive_outcomes.py"
)


@pytest.fixture(scope="module")
def backfill_module():
    spec = importlib.util.spec_from_file_location(
        "backfill_directive_outcomes", _HELPER_PATH
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# extract_outcome_from_jsonb tests
# ---------------------------------------------------------------------------


def test_extract_outcome_from_jsonb_flat_keys(backfill_module):
    """Top-level pnl_1h / pnl_24h / sharpe_24h are extracted into outcome_* keys."""
    blob = {
        "pnl_1h": 1.5,
        "pnl_24h": 12.0,
        "sharpe_24h": 0.85,
    }
    out = backfill_module.extract_outcome_from_jsonb(blob)
    assert out["outcome_pnl_1h"] == 1.5
    assert out["outcome_pnl_24h"] == 12.0
    assert out["outcome_sharpe_24h"] == 0.85
    assert "outcome_pnl_4h" not in out


def test_extract_outcome_from_jsonb_outcome_prefixed_keys(backfill_module):
    """outcome_pnl_1h key (already-prefixed) is also accepted."""
    blob = {"outcome_pnl_1h": 2.5}
    out = backfill_module.extract_outcome_from_jsonb(blob)
    assert out["outcome_pnl_1h"] == 2.5


def test_extract_outcome_from_jsonb_nested_outcome_dict(backfill_module):
    """Nested 'outcome': {pnl_1h: ...} structure is also accepted."""
    blob = {"outcome": {"pnl_1h": 3.0, "pnl_4h": 7.0, "sharpe_24h": 0.5}}
    out = backfill_module.extract_outcome_from_jsonb(blob)
    assert out["outcome_pnl_1h"] == 3.0
    assert out["outcome_pnl_4h"] == 7.0
    assert out["outcome_sharpe_24h"] == 0.5


def test_extract_outcome_from_jsonb_top_level_wins_over_nested(backfill_module):
    """Top-level keys take precedence over nested outcome dict."""
    blob = {"pnl_1h": 100.0, "outcome": {"pnl_1h": 999.0}}
    out = backfill_module.extract_outcome_from_jsonb(blob)
    assert out["outcome_pnl_1h"] == 100.0


def test_extract_outcome_from_jsonb_none_returns_empty(backfill_module):
    """None input returns empty dict."""
    assert backfill_module.extract_outcome_from_jsonb(None) == {}


def test_extract_outcome_from_jsonb_non_dict_returns_empty(backfill_module):
    """Non-dict input returns empty dict (defensive)."""
    assert backfill_module.extract_outcome_from_jsonb("not-a-dict") == {}
    assert backfill_module.extract_outcome_from_jsonb(42) == {}
    assert backfill_module.extract_outcome_from_jsonb([1, 2, 3]) == {}


def test_extract_outcome_from_jsonb_string_value_ignored(backfill_module):
    """Non-numeric values are ignored (not converted)."""
    blob = {"pnl_1h": "not-a-number"}
    out = backfill_module.extract_outcome_from_jsonb(blob)
    assert "outcome_pnl_1h" not in out


def test_extract_outcome_from_jsonb_empty_dict_returns_empty(backfill_module):
    """Empty dict returns empty dict."""
    assert backfill_module.extract_outcome_from_jsonb({}) == {}


# ---------------------------------------------------------------------------
# backfill() fail-soft tests
# backfill() fail-soft 測試
# ---------------------------------------------------------------------------


def test_backfill_no_dsn_returns_zero(backfill_module, monkeypatch):
    """No DSN env / arg → backfill returns 0, no raise."""
    monkeypatch.delenv("DSN", raising=False)
    monkeypatch.delenv("OPENCLAW_DATABASE_URL", raising=False)
    n = backfill_module.backfill(dsn=None)
    assert n == 0


def test_backfill_psycopg2_unavailable_returns_zero(backfill_module, monkeypatch):
    """psycopg2 missing → backfill returns 0, no raise."""
    monkeypatch.setattr(
        backfill_module, "_try_import_psycopg2", lambda: None
    )
    n = backfill_module.backfill(dsn="postgresql://fake")
    assert n == 0
