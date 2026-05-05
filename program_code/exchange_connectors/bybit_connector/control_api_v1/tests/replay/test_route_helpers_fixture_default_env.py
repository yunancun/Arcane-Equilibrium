"""REF-20 Sprint A R3 Round 6 T4-3 — fixture URI default env fallback.
REF-20 Sprint A R3 Round 6 T4-3 — fixture URI default env fallback 測試。

MODULE_NOTE (EN):
    T4-3 unit tests for ``replay/route_helpers.py::build_default_manifest_payload``
    Round 6 fixture URI fallback chain:

      1. ``OPENCLAW_REPLAY_FIXTURE_URI`` (highest priority — operator/test).
      2. ``OPENCLAW_REPLAY_FIXTURE_DEFAULT`` (server-side default injected
         by ``restart_all.sh``).
      3. ``<output_dir>/fixture.json`` (legacy fallback).

    R4 UI integration relies on (2): operator can omit fixture_uri from
    register payload and rely on server-side default for Sprint A smoke
    runs.

MODULE_NOTE (中):
    Round 6 fixture URI fallback chain：env override → server-side default
    → legacy 路徑。R4 UI 依賴 (2) 使 operator 可省 fixture_uri。

SPEC: REF-20 V3 §6.2 + Sprint A R3 Round 6 task DAG (T3a).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(os.path.dirname(_test_dir))
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from replay.route_helpers import build_default_manifest_payload  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """Strip all replay fixture env vars so each test starts clean.
    清空所有 replay fixture env，每 test clean slate。
    """
    monkeypatch.delenv("OPENCLAW_REPLAY_FIXTURE_URI", raising=False)
    monkeypatch.delenv("OPENCLAW_REPLAY_FIXTURE_DEFAULT", raising=False)
    yield


def test_fixture_uri_env_override_highest_priority(monkeypatch, tmp_path: Path):
    """OPENCLAW_REPLAY_FIXTURE_URI overrides default + legacy.
    OPENCLAW_REPLAY_FIXTURE_URI 蓋過 default + legacy。
    """
    explicit = "/some/explicit/fixture.json"
    monkeypatch.setenv("OPENCLAW_REPLAY_FIXTURE_URI", explicit)
    # default + legacy paths exist but should be ignored.
    # default + legacy 存在但應被忽略。
    monkeypatch.setenv("OPENCLAW_REPLAY_FIXTURE_DEFAULT", "/some/default.json")

    payload = build_default_manifest_payload(
        experiment_id="exp", output_dir=tmp_path / "rx",
    )
    assert payload["fixture_uri"] == explicit


def test_fixture_uri_default_env_used_when_override_absent(
    monkeypatch, tmp_path: Path,
):
    """OPENCLAW_REPLAY_FIXTURE_DEFAULT used when override absent.
    override 缺時用 OPENCLAW_REPLAY_FIXTURE_DEFAULT。
    """
    default_fixture = tmp_path / "synthetic_btcusdt.json"
    default_fixture.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("OPENCLAW_REPLAY_FIXTURE_DEFAULT", str(default_fixture))

    payload = build_default_manifest_payload(
        experiment_id="exp", output_dir=tmp_path / "rx",
    )
    assert payload["fixture_uri"] == str(default_fixture)


def test_fixture_uri_legacy_fallback_when_no_env(monkeypatch, tmp_path: Path):
    """No env at all → fall back to <output_dir>/fixture.json.
    完全沒 env → fallback 到 <output_dir>/fixture.json。
    """
    output_dir = tmp_path / "ry"
    payload = build_default_manifest_payload(
        experiment_id="exp", output_dir=output_dir,
    )
    expected = str(output_dir / "fixture.json")
    assert payload["fixture_uri"] == expected


def test_fixture_uri_default_env_whitespace_trimmed(monkeypatch, tmp_path: Path):
    """Whitespace-only OPENCLAW_REPLAY_FIXTURE_DEFAULT → fall through to legacy.
    純空白 OPENCLAW_REPLAY_FIXTURE_DEFAULT → fall through 到 legacy。
    """
    monkeypatch.setenv("OPENCLAW_REPLAY_FIXTURE_DEFAULT", "   ")
    output_dir = tmp_path / "rz"
    payload = build_default_manifest_payload(
        experiment_id="exp", output_dir=output_dir,
    )
    assert payload["fixture_uri"] == str(output_dir / "fixture.json")


def test_fixture_uri_override_whitespace_trimmed_then_default_used(
    monkeypatch, tmp_path: Path,
):
    """Whitespace-only OPENCLAW_REPLAY_FIXTURE_URI → fall through to default.
    純空白 override → fall through 到 default。
    """
    default_fixture = tmp_path / "synthetic.json"
    default_fixture.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("OPENCLAW_REPLAY_FIXTURE_URI", "   ")
    monkeypatch.setenv("OPENCLAW_REPLAY_FIXTURE_DEFAULT", str(default_fixture))

    payload = build_default_manifest_payload(
        experiment_id="exp", output_dir=tmp_path / "rx",
    )
    assert payload["fixture_uri"] == str(default_fixture)


def test_manifest_fixture_uri_overrides_server_default(
    monkeypatch, tmp_path: Path,
):
    """Persisted V049 manifest fixture_uri wins over server smoke default.
    V049 manifest_jsonb.fixture_uri 覆蓋服務端 smoke default。
    """
    import replay.experiment_registry as registry

    manifest_fixture = tmp_path / "historical_btcusdt.json"
    manifest_fixture.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("OPENCLAW_REPLAY_FIXTURE_DEFAULT", "/server/smoke.json")
    monkeypatch.setattr(
        registry,
        "lookup_replay_manifest_runtime_config",
        lambda cur, experiment_id: {
            "data_tier": "S2",
            "manifest_jsonb": {
                "symbol": "BTCUSDT",
                "strategy": "grid_trading",
                "timeframe": "1m",
                "data_tier": "S2",
                "fixture_uri": str(manifest_fixture),
            },
        },
    )
    monkeypatch.setattr(
        registry,
        "lookup_replay_config_blob",
        lambda cur, experiment_id: {"strategy_params": {}, "risk_overrides": {}},
    )

    payload = build_default_manifest_payload(
        experiment_id="exp", output_dir=tmp_path / "rx", cur=object(),
    )
    assert payload["fixture_uri"] == str(manifest_fixture)
    assert payload["strategy"] == "grid_trading"


def test_manifest_fixture_uri_rejects_control_chars(
    monkeypatch, tmp_path: Path,
):
    """Control characters in persisted fixture_uri fail loud.
    manifest fixture_uri 內含控制字符時 fail loud。
    """
    import replay.experiment_registry as registry

    monkeypatch.setattr(
        registry,
        "lookup_replay_manifest_runtime_config",
        lambda cur, experiment_id: {
            "data_tier": "S2",
            "manifest_jsonb": {
                "strategy": "grid_trading",
                "fixture_uri": "bad\npath",
            },
        },
    )
    monkeypatch.setattr(
        registry,
        "lookup_replay_config_blob",
        lambda cur, experiment_id: {"strategy_params": {}, "risk_overrides": {}},
    )

    with pytest.raises(ValueError, match="replay_manifest_fixture_uri_invalid"):
        build_default_manifest_payload(
            experiment_id="exp", output_dir=tmp_path / "rx", cur=object(),
        )
