from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient


_TEST_DIR = Path(__file__).resolve().parent
_CONTROL_API_DIR = _TEST_DIR.parent
if str(_CONTROL_API_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTROL_API_DIR))

from app.auth import AuthenticatedActor  # noqa: E402
from app.main_legacy import current_actor  # noqa: E402
from app.replay_full_chain_routes import full_chain_replay_router  # noqa: E402


def _operator_actor() -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_id="full-chain-run-test",
        actor_type="human",
        roles={"operator", "viewer"},
        scopes={"replay:write"},
    )


def _client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("OPENCLAW_REPLAY_FULL_CHAIN_FIXTURE_DIR", str(tmp_path))
    monkeypatch.setenv("OPENCLAW_REPLAY_MICROSTRUCTURE_OVERLAY_ENABLED", "0")
    app = FastAPI()
    app.include_router(full_chain_replay_router)
    app.dependency_overrides[current_actor] = _operator_actor
    return TestClient(app)


def _sample_event(symbol: str, ts_ms: int) -> dict[str, Any]:
    return {
        "ts_ms": ts_ms,
        "symbol": symbol,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 12.0,
    }


def _empty_edge_snapshot(**kwargs: Any) -> dict[str, Any]:
    return {
        "status": "empty",
        "source": "v059_edge_estimate_snapshots",
        "reason": "test_empty",
        "edge_estimates": {},
    }


def test_full_chain_run_live_profile_requires_bulk_prod_ip_override(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import app.replay_full_chain_routes as mod

    monkeypatch.setenv("OPENCLAW_RELEASE_PROFILE", "live")
    monkeypatch.delenv("OPENCLAW_REPLAY_BULK_ALLOW_PROD_IP", raising=False)

    async def forbidden_events(**kwargs):
        raise AssertionError("prod IP guard must fire before market fetch")

    monkeypatch.setattr(mod, "_fetch_full_chain_events", forbidden_events)
    client = _client(monkeypatch, tmp_path)

    resp = client.post(
        "/api/v1/replay/full-chain/run",
        json={
            "universe_preset": "custom",
            "symbols": ["BTCUSDT"],
            "strategies": ["grid_trading"],
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


def test_full_chain_run_registers_and_starts_one_subprocess_per_strategy(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import app.replay_full_chain_routes as mod

    registered: list[Any] = []
    run_requests: list[Any] = []

    async def fake_events(**kwargs):
        assert kwargs["symbols"] == ["ETHUSDT", "BTCUSDT"]
        return (
            [
                _sample_event("BTCUSDT", 1_700_000_000_000),
                _sample_event("ETHUSDT", 1_699_999_999_000),
            ],
            {"BTCUSDT": 1, "ETHUSDT": 1},
        )

    async def fake_strategy_params(**kwargs):
        assert kwargs == {"engine": "demo"}
        return {"grid_trading": {"grid_levels": 12}, "ma_crossover": {"fast": 8}}

    async def fake_risk_config(**kwargs):
        assert kwargs == {"engine": "demo"}
        return {"limits": {"position_size_max_pct": 10.0}}

    def fake_register(get_pg_conn, actor, body, **kwargs):
        registered.append(body)
        return {
            "experiment_id": str(uuid.uuid4()),
            "manifest_hash": "a" * 64,
            "status": "created",
            "idempotency_hit": False,
        }, None

    def fake_run(**kwargs):
        body = kwargs["body"]
        run_requests.append((body, kwargs["per_actor_cap"], kwargs["global_cap"]))
        return uuid.uuid4().hex, 1234, None, tmp_path / "artifact"

    monkeypatch.setattr(mod, "_fetch_full_chain_events", fake_events)
    monkeypatch.setattr(mod, "_fetch_full_chain_strategy_params", fake_strategy_params)
    monkeypatch.setattr(mod, "_fetch_current_risk_config", fake_risk_config)
    monkeypatch.setattr(mod, "_fetch_edge_estimate_snapshot_sync", _empty_edge_snapshot)
    monkeypatch.setattr(mod._er, "run_register_in_pg_xact", fake_register)
    monkeypatch.setattr(mod._rrun, "_do_pg_path_for_run_sync", fake_run)

    client = _client(monkeypatch, tmp_path)
    resp = client.post(
        "/api/v1/replay/full-chain/run",
        json={
            "universe_preset": "custom",
            "symbols": ["ethusdt", "btcusdt"],
            "strategies": ["grid_trading", "ma_crossover"],
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
    assert data["mode"] == "full_chain_run"
    assert data["execution_mode"] == "subprocess_strategy_risk_per_strategy"
    assert data["scanner_scope"] == "historical_scanner_timeline_from_fixture"
    assert data["symbols"] == ["ETHUSDT", "BTCUSDT"]
    assert data["strategies"] == ["grid_trading", "ma_crossover"]
    assert data["strategy_count"] == 2
    assert len(data["runs"]) == 2
    assert all(item["status"] == "running" for item in data["runs"])
    assert all(item["subprocess_pid"] == 1234 for item in data["runs"])

    assert [body.strategy for body in registered] == ["grid_trading", "ma_crossover"]
    assert all(body.symbol == "FULL_CHAIN" for body in registered)
    assert all(body.data_tier == "S2" for body in registered)
    assert all(body.half_life_days == 7.0 for body in registered)
    assert all(body.embargo_days == 14.0 for body in registered)
    assert all(body.strategy_params["grid_trading"]["grid_levels"] == 12 for body in registered)
    assert all(body.risk_overrides["limits"]["position_size_max_pct"] == 10.0 for body in registered)
    assert all(body.manifest_jsonb["fixture_uri"] == data["fixture_uri"] for body in registered)
    assert all(
        body.manifest_jsonb["execution_scope"]
        == "historical_scanner_timeline_to_strategy_risk_exit"
        for body in registered
    )
    assert all(body.manifest_jsonb["promotion_allowed"] is False for body in registered)
    assert all(
        body.manifest_jsonb["edge_snapshot_meta"]["source"]
        == "v059_edge_estimate_snapshots"
        for body in registered
    )
    assert [cap for _body, cap, _global_cap in run_requests] == [2, 2]
    assert [cap for _body, _cap, cap in run_requests] == [2, 2]

    fixture = json.loads(Path(data["fixture_uri"]).read_text(encoding="utf-8"))
    assert fixture["mode"] == "full_chain"
    assert [event["symbol"] for event in fixture["events"]] == ["ETHUSDT", "BTCUSDT"]


def test_full_chain_run_finalizes_completed_in_poll(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import app.replay_full_chain_routes as mod

    async def fake_events(**kwargs):
        return ([_sample_event("BTCUSDT", 1_700_000_000_000)], {"BTCUSDT": 1})

    def fake_register(get_pg_conn, actor, body, **kwargs):
        return {
            "experiment_id": str(uuid.uuid4()),
            "manifest_hash": "b" * 64,
            "status": "created",
            "idempotency_hit": False,
        }, None

    def fake_run(**kwargs):
        return uuid.uuid4().hex, None, None, tmp_path / "artifact"

    async def fake_finalize(**kwargs):
        return {"fills_inserted": 1, "status": "completed"}, None

    monkeypatch.setattr(mod, "_fetch_full_chain_events", fake_events)
    monkeypatch.setattr(mod, "_fetch_edge_estimate_snapshot_sync", _empty_edge_snapshot)
    monkeypatch.setattr(mod._er, "run_register_in_pg_xact", fake_register)
    monkeypatch.setattr(mod._rrun, "_do_pg_path_for_run_sync", fake_run)
    monkeypatch.setattr(mod._fr, "run_finalize_in_pg_xact", fake_finalize)

    client = _client(monkeypatch, tmp_path)
    resp = client.post(
        "/api/v1/replay/full-chain/run",
        json={
            "universe_preset": "custom",
            "symbols": ["BTCUSDT"],
            "strategies": ["grid_trading"],
            "engine": "demo",
            "timeframe": "1m",
            "category": "linear",
            "data_window_start": "2026-05-01T00:00:00Z",
            "data_window_end": "2026-05-01T00:02:00Z",
            "use_current_config": False,
        },
    )

    assert resp.status_code == 200
    run = resp.json()["data"]["runs"][0]
    assert run["status"] == "completed"
    assert run["finalize_status"] == "completed"
    assert run["finalize"]["fills_inserted"] == 1


def test_full_chain_run_prefers_v058_universe_and_embeds_v059_edges(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import app.replay_full_chain_routes as mod

    registered: list[Any] = []

    def fake_universe(**kwargs):
        assert kwargs["category"] == "linear"
        assert kwargs["max_symbols"] == 8
        return {
            "status": "ok",
            "source": "v058_symbol_universe_snapshots",
            "symbols": ["SOLUSDT", "XRPUSDT"],
            "symbol_count": 2,
            "entries": [],
            "warnings": [],
        }

    async def forbidden_current_scanner():
        raise AssertionError("V058 hit must avoid current scanner fallback")

    async def fake_events(**kwargs):
        assert kwargs["symbols"] == ["SOLUSDT", "XRPUSDT"]
        return (
            [
                _sample_event("SOLUSDT", 1_700_000_000_000),
                _sample_event("XRPUSDT", 1_700_000_000_000),
            ],
            {"SOLUSDT": 1, "XRPUSDT": 1},
        )

    def fake_edge(**kwargs):
        assert kwargs["symbols"] == ["SOLUSDT", "XRPUSDT"]
        assert kwargs["strategies"] == ["grid_trading"]
        return {
            "status": "ok",
            "source": "v059_edge_estimate_snapshots",
            "cutoff_ms": kwargs["cutoff_ms"],
            "cell_count": 1,
            "cells": [{"key": "grid_trading::SOLUSDT"}],
            "edge_estimates": {
                "grid_trading::SOLUSDT": {
                    "runtime_bps": 4.2,
                    "n": 31,
                    "std_bps": 12.0,
                }
            },
        }

    def fake_register(get_pg_conn, actor, body, **kwargs):
        registered.append(body)
        return {
            "experiment_id": str(uuid.uuid4()),
            "manifest_hash": "c" * 64,
            "status": "created",
            "idempotency_hit": False,
        }, None

    def fake_run(**kwargs):
        return uuid.uuid4().hex, 1234, None, tmp_path / "artifact"

    monkeypatch.setattr(mod, "_fetch_historical_universe_snapshot_sync", fake_universe)
    monkeypatch.setattr(mod, "_fetch_current_scanner_snapshot", forbidden_current_scanner)
    monkeypatch.setattr(mod, "_fetch_full_chain_events", fake_events)
    monkeypatch.setattr(mod, "_fetch_edge_estimate_snapshot_sync", fake_edge)
    monkeypatch.setattr(mod._er, "run_register_in_pg_xact", fake_register)
    monkeypatch.setattr(mod._rrun, "_do_pg_path_for_run_sync", fake_run)

    client = _client(monkeypatch, tmp_path)
    resp = client.post(
        "/api/v1/replay/full-chain/run",
        json={
            "universe_preset": "current_scanner",
            "strategies": ["grid_trading"],
            "engine": "demo",
            "timeframe": "1m",
            "category": "linear",
            "data_window_start": "2026-05-01T00:00:00Z",
            "data_window_end": "2026-05-01T00:05:00Z",
            "use_current_config": False,
        },
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["symbols"] == ["SOLUSDT", "XRPUSDT"]
    assert data["universe_source"] == "v058_symbol_universe_snapshots"
    assert data["historical_universe"]["source"] == "v058_symbol_universe_snapshots"
    assert data["edge_snapshot"]["cell_count"] == 1

    manifest = registered[0].manifest_jsonb
    assert manifest["universe_source"] == "v058_symbol_universe_snapshots"
    assert manifest["historical_universe"]["symbol_count"] == 2
    assert manifest["edge_snapshot_meta"]["cell_count"] == 1
    assert manifest["edge_estimates"]["grid_trading::SOLUSDT"]["runtime_bps"] == 4.2


def test_full_chain_run_rejects_strategy_cap(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OPENCLAW_REPLAY_FULL_CHAIN_MAX_STRATEGIES", "1")
    client = _client(monkeypatch, tmp_path)

    resp = client.post(
        "/api/v1/replay/full-chain/run",
        json={
            "universe_preset": "custom",
            "symbols": ["BTCUSDT"],
            "strategies": ["grid_trading", "ma_crossover"],
            "engine": "demo",
            "timeframe": "1m",
            "category": "linear",
            "data_window_start": "2026-05-01T00:00:00Z",
            "data_window_end": "2026-05-01T00:02:00Z",
            "use_current_config": False,
        },
    )

    assert resp.status_code == 400
    assert "replay_full_chain_strategy_cap_exceeded" in resp.json()["detail"]["reason_codes"]


def test_apply_microstructure_overlay_enriches_prior_bbo_only() -> None:
    import app.replay_full_chain_routes as mod

    events = [
        _sample_event("BTCUSDT", 1_700_000_060_000),
        _sample_event("ETHUSDT", 1_700_000_060_000),
    ]
    overlay = {
        "status": "ok",
        "source": "market.market_tickers",
        "records": {
            "BTCUSDT": [
                {
                    "ts_ms": 1_700_000_000_000,
                    "best_bid": 99.9,
                    "best_ask": 100.1,
                    "bid_size": 2.0,
                    "ask_size": 3.0,
                    "spread_bps": 20.0,
                }
            ],
            "ETHUSDT": [
                {
                    "ts_ms": 1_700_000_070_000,
                    "best_bid": 49.9,
                    "best_ask": 50.1,
                }
            ],
        },
    }

    stats = mod._apply_microstructure_overlays(  # noqa: SLF001
        events,
        overlay,
        max_staleness_ms=120_000,
    )

    assert stats["status"] == "ok"
    assert stats["enriched_event_count"] == 1
    assert events[0]["best_bid"] == 99.9
    assert events[0]["best_ask"] == 100.1
    assert events[0]["microstructure_source"] == "market.market_tickers"
    assert "best_bid" not in events[1]
