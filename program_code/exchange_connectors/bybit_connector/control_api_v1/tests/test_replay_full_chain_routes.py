from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


_TEST_DIR = Path(__file__).resolve().parent
_CONTROL_API_DIR = _TEST_DIR.parent
if str(_CONTROL_API_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTROL_API_DIR))

from app.auth import AuthenticatedActor  # noqa: E402
from app.main_legacy import current_actor  # noqa: E402
from app.replay_quick_routes import quick_replay_router  # noqa: E402


def _operator_actor() -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_id="full-chain-replay-test",
        actor_type="human",
        roles={"operator", "viewer"},
        scopes={"replay:write"},
    )


def _client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("OPENCLAW_REPLAY_FULL_CHAIN_FIXTURE_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(quick_replay_router)
    app.dependency_overrides[current_actor] = _operator_actor
    return TestClient(app)


def test_full_chain_prepare_disabled_by_default(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import app.replay_quick_routes as mod

    monkeypatch.delenv("OPENCLAW_REPLAY_PREPARE_ENABLED", raising=False)

    def forbidden_fetch(**kwargs):
        raise AssertionError("disabled full-chain prepare must not fetch market data")

    monkeypatch.setattr(mod, "_fetch_bybit_klines_sync", forbidden_fetch)

    client = _client(monkeypatch, tmp_path)
    resp = client.post(
        "/api/v1/replay/full-chain/prepare",
        json={
            "universe_preset": "custom",
            "symbols": ["BTCUSDT"],
            "engine": "demo",
            "timeframe": "1m",
            "category": "linear",
            "data_window_start": "2026-05-01T00:00:00Z",
            "data_window_end": "2026-05-01T00:02:00Z",
            "use_current_config": False,
        },
    )

    assert resp.status_code == 403
    assert "replay_full_chain_prepare_disabled" in resp.json()["detail"]["reason_codes"]


def test_full_chain_prepare_live_profile_requires_bulk_prod_ip_override(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import app.replay_quick_routes as mod

    monkeypatch.setenv("OPENCLAW_REPLAY_PREPARE_ENABLED", "1")
    monkeypatch.setenv("OPENCLAW_RELEASE_PROFILE", "live")
    monkeypatch.delenv("OPENCLAW_REPLAY_BULK_ALLOW_PROD_IP", raising=False)

    def forbidden_fetch(**kwargs):
        raise AssertionError("prod IP guard must fire before market fetch")

    monkeypatch.setattr(mod, "_fetch_bybit_klines_sync", forbidden_fetch)

    client = _client(monkeypatch, tmp_path)
    resp = client.post(
        "/api/v1/replay/full-chain/prepare",
        json={
            "universe_preset": "custom",
            "symbols": ["BTCUSDT"],
            "engine": "demo",
            "timeframe": "1m",
            "category": "linear",
            "data_window_start": "2026-05-01T00:00:00Z",
            "data_window_end": "2026-05-01T00:02:00Z",
            "use_current_config": False,
        },
    )

    assert resp.status_code == 403
    assert "replay_full_chain_prod_ip_blocked" in resp.json()["detail"]["reason_codes"]


def test_full_chain_prepare_writes_time_ordered_multi_symbol_fixture(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import app.replay_quick_routes as mod

    monkeypatch.setenv("OPENCLAW_REPLAY_PREPARE_ENABLED", "1")

    def fake_fetch(**kwargs):
        symbol = kwargs["symbol"]
        if symbol == "BTCUSDT":
            return [
                {
                    "ts_ms": 1_700_000_000_000,
                    "symbol": "BTCUSDT",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 12.0,
                }
            ]
        return [
            {
                "ts_ms": 1_699_999_999_000,
                "symbol": symbol,
                "open": 200.0,
                "high": 202.0,
                "low": 198.0,
                "close": 201.0,
                "volume": 8.0,
            }
        ]

    async def fake_strategy_params(**kwargs):
        assert kwargs == {"engine": "demo"}
        return {"grid_trading": {"grid_levels": 12}}

    async def fake_risk_config(**kwargs):
        assert kwargs == {"engine": "demo"}
        return {"limits": {"position_size_max_pct": 10.0}}

    monkeypatch.setattr(mod, "_fetch_bybit_klines_sync", fake_fetch)
    monkeypatch.setattr(mod, "_fetch_full_chain_strategy_params", fake_strategy_params)
    monkeypatch.setattr(mod, "_fetch_current_risk_config", fake_risk_config)

    client = _client(monkeypatch, tmp_path)
    resp = client.post(
        "/api/v1/replay/full-chain/prepare",
        json={
            "universe_preset": "custom",
            "symbols": ["ethusdt", "btcusdt", "ETHUSDT"],
            "engine": "demo",
            "timeframe": "1m",
            "category": "linear",
            "data_window_start": "2026-05-01T00:00:00Z",
            "data_window_end": "2026-05-01T00:05:00Z",
            "starting_balance": 10000,
        },
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["data_tier"] == "S2"
    assert data["source"] == "s2_bybit_public_full_chain"
    assert data["mode"] == "full_chain"
    assert data["execution_mode"] == "dataset_only_until_ref21_runner"
    assert data["symbols"] == ["ETHUSDT", "BTCUSDT"]
    assert data["event_count"] == 2
    assert data["per_symbol_event_counts"] == {"ETHUSDT": 1, "BTCUSDT": 1}
    assert data["strategy_params"] == {"grid_trading": {"grid_levels": 12}}
    assert data["risk_overrides"] == {"limits": {"position_size_max_pct": 10.0}}

    fixture_path = Path(data["fixture_uri"])
    assert fixture_path.exists()
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert fixture["schema_version"] == 1
    assert fixture["mode"] == "full_chain"
    assert fixture["source"] == "s2_bybit_public_full_chain"
    assert fixture["symbols"] == ["ETHUSDT", "BTCUSDT"]
    assert [event["symbol"] for event in fixture["events"]] == ["ETHUSDT", "BTCUSDT"]


def test_full_chain_prepare_uses_scanner_universe(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import app.replay_quick_routes as mod

    monkeypatch.setenv("OPENCLAW_REPLAY_PREPARE_ENABLED", "1")

    def fake_fetch(**kwargs):
        symbol = kwargs["symbol"]
        return [
            {
                "ts_ms": 1_700_000_000_000,
                "symbol": symbol,
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.5,
                "volume": 1.0,
            }
        ]

    async def fake_scanner_snapshot():
        return {
            "last_scan": {
                "scan_id": "scan-123",
                "top_candidates": [
                    {"symbol": "SOLUSDT", "score": 0.8},
                    {"symbol": "XRPUSDT", "score": 0.7},
                ],
            }
        }

    monkeypatch.setattr(mod, "_fetch_bybit_klines_sync", fake_fetch)
    monkeypatch.setattr(mod, "_fetch_current_scanner_snapshot", fake_scanner_snapshot)

    client = _client(monkeypatch, tmp_path)
    resp = client.post(
        "/api/v1/replay/full-chain/prepare",
        json={
            "universe_preset": "current_scanner",
            "engine": "demo",
            "timeframe": "1m",
            "category": "linear",
            "data_window_start": "2026-05-01T00:00:00Z",
            "data_window_end": "2026-05-01T00:02:00Z",
            "use_current_config": False,
        },
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["symbols"] == ["SOLUSDT", "XRPUSDT"]
    assert data["scanner_snapshot"]["last_scan"]["scan_id"] == "scan-123"
    assert data["warnings"] == []


def test_full_chain_prepare_rejects_custom_empty_universe(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OPENCLAW_REPLAY_PREPARE_ENABLED", "1")
    client = _client(monkeypatch, tmp_path)
    resp = client.post(
        "/api/v1/replay/full-chain/prepare",
        json={
            "universe_preset": "custom",
            "symbols": [],
            "engine": "demo",
            "timeframe": "1m",
            "category": "linear",
            "data_window_start": "2026-05-01T00:00:00Z",
            "data_window_end": "2026-05-01T00:02:00Z",
        },
    )

    assert resp.status_code == 400
    assert (
        "replay_full_chain_custom_symbols_required"
        in resp.json()["detail"]["reason_codes"]
    )


def test_full_chain_prepare_rejects_oversized_window(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OPENCLAW_REPLAY_PREPARE_ENABLED", "1")
    monkeypatch.setenv("OPENCLAW_REPLAY_FULL_CHAIN_MAX_EVENTS", "10")
    client = _client(monkeypatch, tmp_path)

    resp = client.post(
        "/api/v1/replay/full-chain/prepare",
        json={
            "universe_preset": "custom",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "engine": "demo",
            "timeframe": "1m",
            "category": "linear",
            "data_window_start": "2026-05-01T00:00:00Z",
            "data_window_end": "2026-05-01T10:00:00Z",
            "use_current_config": False,
        },
    )

    assert resp.status_code == 400
    assert "replay_full_chain_window_too_large" in resp.json()["detail"]["reason_codes"]
