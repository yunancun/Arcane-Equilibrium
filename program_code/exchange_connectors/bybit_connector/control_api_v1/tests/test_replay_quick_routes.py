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

from app.main_legacy import current_actor  # noqa: E402
from app.auth import AuthenticatedActor  # noqa: E402
from app.replay_quick_routes import quick_replay_router  # noqa: E402


def _operator_actor() -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_id="quick-replay-test",
        actor_type="human",
        roles={"operator", "viewer"},
        scopes={"replay:write"},
    )


def _client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("OPENCLAW_REPLAY_QUICK_FIXTURE_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(quick_replay_router)
    app.dependency_overrides[current_actor] = _operator_actor
    return TestClient(app)


def test_quick_prepare_writes_s2_fixture_and_current_config(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import app.replay_quick_routes as mod

    def fake_fetch(**kwargs):
        assert kwargs["symbol"] == "BTCUSDT"
        assert kwargs["timeframe"] == "1m"
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

    async def fake_strategy_params(**kwargs):
        assert kwargs == {"engine": "demo", "strategy": "grid_trading"}
        return {"grid_trading": {"grid_levels": 12}}

    async def fake_risk_config(**kwargs):
        assert kwargs == {"engine": "demo"}
        return {"limits": {"position_size_max_pct": 10.0}}

    monkeypatch.setattr(mod, "_fetch_bybit_klines_sync", fake_fetch)
    monkeypatch.setattr(mod, "_fetch_current_strategy_params", fake_strategy_params)
    monkeypatch.setattr(mod, "_fetch_current_risk_config", fake_risk_config)

    client = _client(monkeypatch, tmp_path)
    resp = client.post(
        "/api/v1/replay/quick/prepare",
        json={
            "symbol": "BTCUSDT",
            "strategy": "grid_trading",
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
    assert data["source"] == "s2_bybit_public"
    assert data["event_count"] == 1
    assert data["strategy_params"] == {"grid_trading": {"grid_levels": 12}}
    assert data["risk_overrides"] == {"limits": {"position_size_max_pct": 10.0}}

    fixture_path = Path(data["fixture_uri"])
    assert fixture_path.exists()
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert fixture["schema_version"] == 1
    assert fixture["source"] == "s2_bybit_public"
    assert fixture["events"][0]["symbol"] == "BTCUSDT"


def test_quick_prepare_rejects_oversized_window(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OPENCLAW_REPLAY_QUICK_MAX_BARS", "200")
    client = _client(monkeypatch, tmp_path)

    resp = client.post(
        "/api/v1/replay/quick/prepare",
        json={
            "symbol": "BTCUSDT",
            "strategy": "grid_trading",
            "engine": "demo",
            "timeframe": "1m",
            "category": "linear",
            "data_window_start": "2026-05-01T00:00:00Z",
            "data_window_end": "2026-05-01T04:00:00Z",
            "starting_balance": 10000,
        },
    )

    assert resp.status_code == 400
    assert "replay_quick_window_too_large" in resp.json()["detail"]["reason_codes"]
