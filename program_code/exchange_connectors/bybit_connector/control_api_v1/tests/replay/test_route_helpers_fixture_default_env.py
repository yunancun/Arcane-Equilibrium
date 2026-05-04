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
