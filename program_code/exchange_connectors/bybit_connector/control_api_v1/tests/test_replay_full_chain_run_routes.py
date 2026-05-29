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


def _default_execution_calibration(**kwargs: Any) -> dict[str, Any]:
    return {
        "status": "insufficient_samples",
        "reason": "test_default_s2_bound",
        "source": "trading.fills",
        "sample_count": 0,
        "slippage_sample_count": 0,
        "recommended_taker_slippage_bps": 50.0,
        "recommended_taker_slippage_clamped": False,
        "execution_confidence": "S2_CONSERVATIVE_BOUND",
        "maker_fill_probability_status": "unavailable_without_order_outcomes",
        "maker_fill_confidence": "S2_CONSERVATIVE_BOUND",
        "maker_fill_probability_reason": "test_no_order_outcomes",
        "maker_order_sample_count": 0,
        "maker_any_fill_probability": 0.0,
        "recommended_maker_fill_probability_cap": 0.40,
        "maker_fill_cap_source": "default_conservative_cap",
        "risk_overlay": {"applied": False},
    }


def _operator_actor() -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_id="full-chain-run-test",
        actor_type="human",
        roles={"operator", "viewer"},
        scopes={"replay:write"},
    )


def _client(monkeypatch, tmp_path: Path) -> TestClient:
    import app.replay_full_chain_routes as mod

    monkeypatch.setenv("OPENCLAW_REPLAY_FULL_CHAIN_FIXTURE_DIR", str(tmp_path))
    monkeypatch.setenv("OPENCLAW_REPLAY_MICROSTRUCTURE_OVERLAY_ENABLED", "0")
    monkeypatch.setattr(
        mod._ec,
        "fetch_execution_calibration_sync",
        _default_execution_calibration,
    )
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


def test_full_chain_coverage_preflight_is_read_only_and_surfaces_verdict(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import app.replay_full_chain_routes as mod

    def fake_coverage(**kwargs):
        assert kwargs["symbols"] == ["BTCUSDT", "ETHUSDT"]
        assert kwargs["timeframe"] == "1m"
        expected = 4
        return {
            "status": "ok",
            "source": "local_market_recorder",
            "symbols": kwargs["symbols"],
            "symbol_count": 2,
            "expected_bars_per_symbol": 2,
            "expected_event_slots": expected,
            "tables": {},
            "bbo": {
                "status": "ok",
                "source": "market.market_tickers",
                "covered_event_slots": 3,
                "expected_event_slots": expected,
                "coverage_ratio": 0.75,
            },
            "orderbook_depth": {
                "status": "empty",
                "source": "market.ob_snapshots",
                "covered_event_slots": 0,
                "expected_event_slots": expected,
                "coverage_ratio": 0.0,
            },
            "funding_rate": {
                "status": "ok",
                "source": "market.market_tickers",
                "covered_event_slots": 2,
                "expected_event_slots": expected,
                "coverage_ratio": 0.5,
            },
            "open_interest": {
                "status": "ok",
                "source": "market.market_tickers",
                "covered_event_slots": 2,
                "expected_event_slots": expected,
                "coverage_ratio": 0.5,
            },
            "index_price": {
                "status": "ok",
                "source": "market.market_tickers",
                "covered_event_slots": 2,
                "expected_event_slots": expected,
                "coverage_ratio": 0.5,
            },
            "instrument_specs": {
                "status": "ok",
                "source": "market.symbol_universe_snapshots",
                "covered_event_slots": 2,
                "expected_event_slots": 2,
                "coverage_ratio": 1.0,
            },
        }

    monkeypatch.setattr(mod._dc, "estimate_replay_window_coverage_sync", fake_coverage)
    monkeypatch.setattr(
        mod,
        "_fetch_edge_estimate_snapshot_sync",
        lambda **kwargs: {
            "status": "ok",
            "source": "v059_edge_estimate_snapshots",
            "cell_count": 1,
            "edge_estimates": {},
        },
    )
    monkeypatch.setattr(
        mod._er,
        "run_register_in_pg_xact",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("coverage preflight must not register manifests")
        ),
    )

    client = _client(monkeypatch, tmp_path)
    resp = client.post(
        "/api/v1/replay/full-chain/coverage",
        json={
            "universe_preset": "custom",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "strategies": ["grid_trading"],
            "engine": "demo",
            "timeframe": "1m",
            "category": "linear",
            "data_window_start": "2026-05-01T00:00:00Z",
            "data_window_end": "2026-05-01T00:02:00Z",
            "use_current_config": True,
        },
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["mode"] == "full_chain_coverage_preflight"
    assert data["execution_mode"] == "read_only_preflight_no_subprocess"
    assert data["promotion_allowed"] is False
    assert data["symbols"] == ["BTCUSDT", "ETHUSDT"]
    assert data["recorder_coverage"]["bbo"]["coverage_ratio"] == 0.75
    assert data["coverage_verdict"]["tier"] == "S2_PLUS_LOCAL_BBO"
    assert "bbo_coverage_below_s1" in data["coverage_verdict"]["reason_codes"]
    assert "orderbook_coverage_below_s1" in data["warnings"]
    assert "runs" not in data
    assert "fixture_uri" not in data


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
    assert all(body.risk_overrides["slippage"]["default_rate"] >= 0.005 for body in registered)
    assert all(
        all(tier["rate"] >= 0.005 for tier in body.risk_overrides["slippage"]["tiers"])
        for body in registered
    )
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
    assert data["execution_calibration"]["execution_confidence"] == "S2_CONSERVATIVE_BOUND"
    assert data["input_fidelity"]["execution_calibration"]["risk_overlay_applied"] is True
    assert data["input_fidelity"]["microstructure"]["bbo_anchor_status"] == "unavailable"
    assert data["input_fidelity"]["microstructure"]["bbo_anchor_coverage_ratio"] == 0.0
    assert all(
        body.manifest_jsonb["execution_calibration"]["risk_overlay"]["applied"] is True
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
        assert kwargs["max_symbols"] == 25
        return {
            "status": "ok",
            "source": "v058_symbol_universe_snapshots",
            "symbols": ["SOLUSDT", "XRPUSDT"],
            "symbol_count": 2,
            "entries": [
                {"symbol": "SOLUSDT", "tick_size": 0.01, "qty_step": 0.1, "min_notional": 5.0},
                {"symbol": "XRPUSDT", "tick_size": 0.0001, "qty_step": 1.0, "min_notional": 5.0},
            ],
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
    assert data["instrument_specs"]["coverage_ratio"] == 1.0
    assert data["input_fidelity"]["instrument_specs"]["status"] == "ok"

    manifest = registered[0].manifest_jsonb
    assert manifest["universe_source"] == "v058_symbol_universe_snapshots"
    assert manifest["historical_universe"]["symbol_count"] == 2
    assert manifest["edge_snapshot_meta"]["cell_count"] == 1
    assert manifest["edge_estimates"]["grid_trading::SOLUSDT"]["runtime_bps"] == 4.2
    assert manifest["input_fidelity"]["edge_snapshot"]["cell_count"] == 1
    assert manifest["execution_calibration"]["recommended_taker_slippage_bps"] == 50.0


def test_full_chain_run_embeds_limited_execution_calibration_overlay(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import app.replay_full_chain_routes as mod

    registered: list[Any] = []

    async def fake_events(**kwargs):
        return ([_sample_event("BTCUSDT", 1_700_000_000_000)], {"BTCUSDT": 1})

    async def fake_strategy_params(**kwargs):
        return {"grid_trading": {"grid_levels": 12}}

    async def fake_risk_config(**kwargs):
        return {
            "limits": {"position_size_max_pct": 10.0},
            "slippage": {
                "default_rate": 0.0001,
                "tiers": [
                    {"min_turnover_usd": 1_000_000_000.0, "rate": 0.0001},
                    {"min_turnover_usd": 0.0, "rate": 0.0002},
                ],
            },
        }

    def fake_execution_calibration(**kwargs):
        assert kwargs["symbols"] == ["BTCUSDT"]
        assert kwargs["strategies"] == ["grid_trading"]
        assert kwargs["asof_ms"] == 1_777_593_600_000
        return {
            "status": "limited",
            "reason": None,
            "source": "trading.fills",
            "sample_count": 31,
            "slippage_sample_count": 31,
            "recommended_taker_slippage_bps": 12.0,
            "recommended_taker_slippage_clamped": False,
            "execution_confidence": "S1_LIMITED",
            "maker_fill_probability_status": "limited",
            "maker_fill_confidence": "S1_LIMITED",
            "maker_fill_probability_reason": None,
            "maker_order_sample_count": 40,
            "maker_any_fill_probability": 0.35,
            "recommended_maker_fill_probability_cap": 0.35,
            "maker_fill_cap_source": "observed_order_outcomes",
            "risk_overlay": {"applied": False},
        }

    def fake_register(get_pg_conn, actor, body, **kwargs):
        registered.append(body)
        return {
            "experiment_id": str(uuid.uuid4()),
            "manifest_hash": "d" * 64,
            "status": "created",
            "idempotency_hit": False,
        }, None

    def fake_run(**kwargs):
        return uuid.uuid4().hex, 1234, None, tmp_path / "artifact"

    monkeypatch.setattr(mod, "_fetch_full_chain_events", fake_events)
    monkeypatch.setattr(mod, "_fetch_full_chain_strategy_params", fake_strategy_params)
    monkeypatch.setattr(mod, "_fetch_current_risk_config", fake_risk_config)
    monkeypatch.setattr(mod, "_fetch_edge_estimate_snapshot_sync", _empty_edge_snapshot)
    monkeypatch.setattr(mod._er, "run_register_in_pg_xact", fake_register)
    monkeypatch.setattr(mod._rrun, "_do_pg_path_for_run_sync", fake_run)

    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(
        mod._ec,
        "fetch_execution_calibration_sync",
        fake_execution_calibration,
    )
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
            "use_current_config": True,
        },
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["execution_calibration"]["execution_confidence"] == "S1_LIMITED"
    assert data["execution_calibration"]["maker_fill_confidence"] == "S1_LIMITED"
    assert data["execution_calibration"]["risk_overlay"]["applied"] is True
    assert data["input_fidelity"]["execution_calibration"]["status"] == "limited"
    assert data["input_fidelity"]["execution_calibration"][
        "recommended_maker_fill_probability_cap"
    ] == 0.35
    assert not any(
        item.startswith("execution_calibration_conservative_bound")
        for item in data["warnings"]
    )
    assert not any(
        item.startswith("maker_fill_probability_conservative_bound")
        for item in data["warnings"]
    )
    assert registered[0].risk_overrides["slippage"]["default_rate"] == 0.0012
    assert all(
        tier["rate"] >= 0.0012
        for tier in registered[0].risk_overrides["slippage"]["tiers"]
    )
    assert (
        registered[0]
        .manifest_jsonb["execution_calibration"]["recommended_taker_slippage_bps"]
        == 12.0
    )


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
                    "turnover_24h": 5_000_000.0,
                    "index_price": 100.0,
                    "open_interest": 12345.0,
                    "funding_rate": 0.0001,
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
        "orderbook_records": {
            "BTCUSDT": [
                {
                    "ts_ms": 1_700_000_010_000,
                    "bid_depth_5": 20.0,
                    "ask_depth_5": 30.0,
                    "spread_bps": 18.0,
                }
            ]
        },
    }

    stats = mod._apply_microstructure_overlays(  # noqa: SLF001
        events,
        overlay,
        max_staleness_ms=120_000,
    )

    assert stats["status"] == "ok"
    assert stats["enriched_event_count"] == 1
    assert stats["bbo_anchor_status"] == "available"
    assert stats["bbo_anchor_event_count"] == 1
    assert stats["bbo_anchor_coverage_ratio"] == 0.5
    assert stats["orderbook_depth_event_count"] == 1
    assert stats["orderbook_depth_coverage_ratio"] == 0.5
    assert events[0]["best_bid"] == 99.9
    assert events[0]["best_ask"] == 100.1
    assert events[0]["bid_depth_5"] == 20.0
    assert events[0]["ask_depth_5"] == 30.0
    assert events[0]["turnover_24h"] == 5_000_000.0
    assert events[0]["index_price"] == 100.0
    assert events[0]["open_interest"] == 12345.0
    assert events[0]["funding_rate"] == 0.0001
    assert stats["field_counts"]["turnover_24h"] == 1
    assert events[0]["microstructure_source"] == "market.market_tickers+market.ob_snapshots"
    assert "best_bid" not in events[1]


def test_execution_calibration_floors_all_replay_slippage_tiers() -> None:
    import app.replay_execution_calibration as ec

    asof_ms = 1_700_000_000_000
    records = [
        {
            "ts": asof_ms - 1_000,
            "liquidity_role": "taker" if idx % 2 else "maker",
            "slippage_bps": float(idx),
            "fee_rate": 0.00055,
        }
        for idx in range(31)
    ]
    calibration = ec.build_execution_calibration_summary(
        records,
        asof_ms=asof_ms,
        source="test",
    )
    risk = ec.apply_execution_calibration_to_risk_overrides(
        {
            "limits": {"position_size_max_pct": 10.0},
            "slippage": {
                "default_rate": 0.0001,
                "tiers": [
                    {"min_turnover_usd": 1_000_000_000.0, "rate": 0.0001},
                    {"min_turnover_usd": 0.0, "rate": 0.0002},
                ],
            },
        },
        calibration,
    )

    floor_rate = calibration["recommended_taker_slippage_bps"] / 10_000.0
    assert calibration["status"] == "limited"
    assert calibration["risk_overlay"]["applied"] is True
    assert risk["limits"]["position_size_max_pct"] == 10.0
    assert risk["slippage"]["default_rate"] >= floor_rate
    assert all(tier["rate"] >= floor_rate for tier in risk["slippage"]["tiers"])


def test_replay_coverage_verdict_promotes_only_when_samples_and_depth_pass() -> None:
    import app.replay_data_coverage as dc

    recorder = {
        "bbo": {"coverage_ratio": 0.85},
        "orderbook_depth": {"coverage_ratio": 0.81},
        "instrument_specs": {"coverage_ratio": 1.0},
    }
    calibrated = dc.build_replay_coverage_verdict(
        recorder_coverage=recorder,
        execution_calibration={
            "maker_order_sample_count": 220,
            "slippage_sample_count": 240,
        },
    )
    assert calibrated["tier"] == "S1_CALIBRATED_READY"
    assert calibrated["verdict"] == "calibrated_advisory_ready"

    limited = dc.build_replay_coverage_verdict(
        recorder_coverage={**recorder, "orderbook_depth": {"coverage_ratio": 0.0}},
        execution_calibration={
            "maker_order_sample_count": 40,
            "slippage_sample_count": 45,
        },
    )
    assert limited["tier"] == "S1_LIMITED_READY"
    assert limited["verdict"] == "limited_advisory_ready"
    assert "orderbook_coverage_below_s1" in limited["reason_codes"]


def test_maker_order_outcome_summary_clamps_to_conservative_cap() -> None:
    import app.replay_execution_calibration as ec

    now_ms = 1_777_593_600_000
    records = [
        {
            "order_ts": now_ms - 60_000,
            "latest_state_ts": now_ms - 30_000,
            "any_fill": idx < 35,
            "full_fill": idx < 20,
            "rejected": idx >= 35,
            "cancelled": False,
            "post_only_cross": idx >= 35,
        }
        for idx in range(50)
    ]

    summary = ec.build_maker_order_outcome_summary(
        records,
        asof_ms=now_ms,
        source="unit",
    )

    assert summary["maker_fill_probability_status"] == "limited"
    assert summary["maker_fill_confidence"] == "S1_LIMITED"
    assert summary["maker_order_sample_count"] == 50
    assert summary["maker_order_any_fill_count"] == 35
    assert summary["maker_any_fill_probability"] == 0.7
    assert summary["recommended_maker_fill_probability_cap"] == 0.40
    assert summary["maker_fill_cap_source"] == "observed_order_outcomes"
    assert summary["latency_status"] == "limited"
    assert summary["latency_sample_count"] == 50
    assert summary["latency_ms"]["q50"] == 30_000
    assert summary["latency_ms"]["q90"] == 30_000
    assert summary["recommended_latency_ms"] == 30_000


# ─────────────────────────────────────────────────────────────────────────────
# P0 Replay Tier A T3 + T4 tests（2026-05-11）— manifest config echo
# ─────────────────────────────────────────────────────────────────────────────


def _write_minimal_scanner_config(settings_root: Path) -> Path:
    """寫 minimal scanner_config.toml fixture（含 25 pinned sym）。"""
    risk_dir = settings_root / "risk_control_rules"
    risk_dir.mkdir(parents=True, exist_ok=True)
    toml_path = risk_dir / "scanner_config.toml"
    pinned_25 = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
        "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT", "POLUSDT",
        "LTCUSDT", "BCHUSDT", "NEARUSDT", "UNIUSDT", "ATOMUSDT",
        "ETCUSDT", "FILUSDT", "ICPUSDT", "TRXUSDT", "ARBUSDT",
        "OPUSDT", "APTUSDT", "SUIUSDT", "TONUSDT", "INJUSDT",
    ]
    pinned_lines = ",\n    ".join(f'"{sym}"' for sym in pinned_25)
    toml_path.write_text(
        "[meta]\nversion = 1\nsaved_ts_ms = 0\n\n"
        "[scheduling]\nscan_interval_secs = 60\nwarmup_delay_secs = 60\n\n"
        "[universe]\nmax_symbols = 40\n"
        f"pinned_symbols = [\n    {pinned_lines}\n]\n\n"
        "[hard_filters]\nmin_turnover_24h_usdt = 50000000.0\n"
        "max_spread_bps = 8.0\nmin_price_usdt = 0.001\nbtc_min_move_pct = 0.3\n\n"
        "[anti_churn]\nmin_hold_cycles = 30\n"
        "challenger_threshold = 15.0\nremoval_cooldown_minutes = 30\n\n"
        "[market_judgment]\nenabled = true\ngate_score_cap = 25.0\n"
        "grid_max_trend_score = 0.55\n\n"
        "[opportunity]\nenabled = true\ncanary_block_new_entries = true\n",
        encoding="utf-8",
    )
    return toml_path


def _write_minimal_strategy_params(
    settings_root: Path,
    engine: str,
    *,
    bb_min_persistence_ms: int = 120000,
    ma_min_trend_snr: float = 0.60,
) -> Path:
    """寫 minimal strategy_params_<engine>.toml fixture，含 P0 Option A-Lite 值。"""
    settings_root.mkdir(parents=True, exist_ok=True)
    toml_path = settings_root / f"strategy_params_{engine}.toml"
    toml_path.write_text(
        f"[ma_crossover]\nactive = true\ncooldown_ms = 600000\n"
        f"min_trend_snr = {ma_min_trend_snr}\n\n"
        f"[bb_reversion]\nactive = true\ncooldown_ms = 600000\n"
        f"min_persistence_ms = {bb_min_persistence_ms}\n\n"
        f"[grid_trading]\nactive = true\ncooldown_ms = 180000\n",
        encoding="utf-8",
    )
    return toml_path


def _write_minimal_risk_config(settings_root: Path, engine: str) -> Path:
    """寫 minimal risk_config_<engine>.toml fixture。"""
    risk_dir = settings_root / "risk_control_rules"
    risk_dir.mkdir(parents=True, exist_ok=True)
    toml_path = risk_dir / f"risk_config_{engine}.toml"
    toml_path.write_text(
        "[meta]\nversion = 2\nsaved_ts_ms = 0\n\n"
        "[limits]\nstop_loss_max_pct = 25.0\nposition_size_max_pct = 25.0\n"
        "open_positions_max = 25\nper_trade_risk_pct = 0.1\n\n"
        "[per_strategy.ma_crossover]\nenabled = true\n"
        "stop_loss_max_pct_override = 2.5\ntake_profit_max_pct_override = 8.0\n",
        encoding="utf-8",
    )
    return toml_path


def test_scanner_config_echo_includes_pinned_25(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """T3: manifest 應含 production scanner_config.toml echo（25 pinned sym）。"""
    import app.replay_full_chain_routes as mod

    settings_root = tmp_path / "settings"
    _write_minimal_scanner_config(settings_root)
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(tmp_path))

    registered: list[Any] = []

    async def fake_events(**kwargs):
        return ([_sample_event("BTCUSDT", 1_700_000_000_000)], {"BTCUSDT": 1})

    def fake_register(get_pg_conn, actor, body, **kwargs):
        registered.append(body)
        return {
            "experiment_id": str(uuid.uuid4()),
            "manifest_hash": "e" * 64,
            "status": "created",
            "idempotency_hit": False,
        }, None

    def fake_run(**kwargs):
        return uuid.uuid4().hex, 1234, None, tmp_path / "artifact"

    monkeypatch.setattr(mod, "_fetch_full_chain_events", fake_events)
    monkeypatch.setattr(mod, "_fetch_edge_estimate_snapshot_sync", _empty_edge_snapshot)
    monkeypatch.setattr(mod._er, "run_register_in_pg_xact", fake_register)
    monkeypatch.setattr(mod._rrun, "_do_pg_path_for_run_sync", fake_run)

    client = _client(monkeypatch, tmp_path / "fixtures")
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
    manifest = registered[0].manifest_jsonb
    # T3 acceptance：scanner_config 進 manifest top-level
    assert "scanner_config" in manifest
    sc = manifest["scanner_config"]
    # production 25 pinned sym 完整 echo
    assert sc["universe"]["max_symbols"] == 40
    pinned = sc["universe"]["pinned_symbols"]
    assert len(pinned) == 25
    assert "BTCUSDT" in pinned
    assert "TONUSDT" in pinned
    assert "INJUSDT" in pinned
    # 其他 production block 也存在
    assert sc["anti_churn"]["min_hold_cycles"] == 30
    assert sc["market_judgment"]["enabled"] is True
    assert sc["opportunity"]["canary_block_new_entries"] is True


def test_strategy_params_echo_matches_production_toml(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """T4: manifest 應含 caller IPC fetched 的 production strategy_params echo。"""
    import app.replay_full_chain_routes as mod

    settings_root = tmp_path / "settings"
    _write_minimal_scanner_config(settings_root)
    _write_minimal_strategy_params(
        settings_root, "demo",
        bb_min_persistence_ms=120000,
        ma_min_trend_snr=0.60,
    )
    _write_minimal_risk_config(settings_root, "demo")
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(tmp_path))

    registered: list[Any] = []

    async def fake_events(**kwargs):
        return ([_sample_event("BTCUSDT", 1_700_000_000_000)], {"BTCUSDT": 1})

    # caller IPC fetched production strategy params（P0 Option A-Lite 後值）
    async def fake_strategy_params(**kwargs):
        assert kwargs == {"engine": "demo"}
        return {
            "ma_crossover": {"active": True, "min_trend_snr": 0.60},
            "bb_reversion": {"active": True, "min_persistence_ms": 120000},
            "grid_trading": {"active": True, "grid_levels": 7},
        }

    async def fake_risk_config(**kwargs):
        return {
            "limits": {"position_size_max_pct": 25.0, "open_positions_max": 25},
            "per_strategy": {
                "ma_crossover": {
                    "enabled": True,
                    "stop_loss_max_pct_override": 2.5,
                    "take_profit_max_pct_override": 8.0,
                }
            },
        }

    def fake_register(get_pg_conn, actor, body, **kwargs):
        registered.append(body)
        return {
            "experiment_id": str(uuid.uuid4()),
            "manifest_hash": "f" * 64,
            "status": "created",
            "idempotency_hit": False,
        }, None

    def fake_run(**kwargs):
        return uuid.uuid4().hex, 1234, None, tmp_path / "artifact"

    monkeypatch.setattr(mod, "_fetch_full_chain_events", fake_events)
    monkeypatch.setattr(mod, "_fetch_full_chain_strategy_params", fake_strategy_params)
    monkeypatch.setattr(mod, "_fetch_current_risk_config", fake_risk_config)
    monkeypatch.setattr(mod, "_fetch_edge_estimate_snapshot_sync", _empty_edge_snapshot)
    monkeypatch.setattr(mod._er, "run_register_in_pg_xact", fake_register)
    monkeypatch.setattr(mod._rrun, "_do_pg_path_for_run_sync", fake_run)

    client = _client(monkeypatch, tmp_path / "fixtures")
    resp = client.post(
        "/api/v1/replay/full-chain/run",
        json={
            "universe_preset": "custom",
            "symbols": ["BTCUSDT"],
            "strategies": ["grid_trading", "ma_crossover", "bb_reversion"],
            "engine": "demo",
            "timeframe": "1m",
            "category": "linear",
            "data_window_start": "2026-05-01T00:00:00Z",
            "data_window_end": "2026-05-01T00:02:00Z",
            "use_current_config": True,
        },
    )

    assert resp.status_code == 200
    # 三 strategy 都有對應 register call；每個 manifest 都帶相同 strategy_params blob
    assert len(registered) == 3
    for body in registered:
        manifest = body.manifest_jsonb
        # T4 acceptance：strategy_params + risk_overrides 進 manifest top-level
        assert "strategy_params" in manifest
        assert "risk_overrides" in manifest
        # P0 Option A-Lite 後值（QC approved demo-only）verbatim echo
        assert manifest["strategy_params"]["bb_reversion"]["min_persistence_ms"] == 120000
        assert manifest["strategy_params"]["ma_crossover"]["min_trend_snr"] == 0.60
        # per_strategy override 也 echo
        assert (
            manifest["risk_overrides"]["per_strategy"]["ma_crossover"][
                "stop_loss_max_pct_override"
            ] == 2.5
        )


def test_manifest_jsonb_hash_changes_when_scanner_config_changes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """T3 invariant：scanner_config 變動 → manifest_jsonb canonical hash 變動。

    V3 §5 sha256(manifest_jsonb)==manifest_hash 不變式 — 新加 key 改變
    canonical bytes 應產生不同 hash。
    """
    import app.replay_full_chain_routes as mod

    settings_root = tmp_path / "settings"
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(tmp_path))

    # 場景 1：完整 25-sym scanner_config
    _write_minimal_scanner_config(settings_root)
    sc_full = mod._load_production_scanner_config()
    assert sc_full is not None
    assert len(sc_full["universe"]["pinned_symbols"]) == 25
    hash_full = mod._canonical_sha256({"scanner_config": sc_full})

    # 場景 2：縮成 5-sym scanner_config（模擬 production 改動）
    risk_dir = settings_root / "risk_control_rules"
    (risk_dir / "scanner_config.toml").write_text(
        "[meta]\nversion = 1\nsaved_ts_ms = 0\n\n"
        "[scheduling]\nscan_interval_secs = 60\nwarmup_delay_secs = 60\n\n"
        "[universe]\nmax_symbols = 40\n"
        'pinned_symbols = [\n    "BTCUSDT",\n    "ETHUSDT",\n    "SOLUSDT",\n'
        '    "XRPUSDT",\n    "DOGEUSDT"\n]\n\n'
        "[hard_filters]\nmin_turnover_24h_usdt = 50000000.0\n"
        "max_spread_bps = 8.0\nmin_price_usdt = 0.001\nbtc_min_move_pct = 0.3\n\n"
        "[anti_churn]\nmin_hold_cycles = 30\n"
        "challenger_threshold = 15.0\nremoval_cooldown_minutes = 30\n\n"
        "[market_judgment]\nenabled = true\ngate_score_cap = 25.0\n"
        "grid_max_trend_score = 0.55\n\n"
        "[opportunity]\nenabled = true\ncanary_block_new_entries = true\n",
        encoding="utf-8",
    )
    sc_small = mod._load_production_scanner_config()
    assert sc_small is not None
    assert len(sc_small["universe"]["pinned_symbols"]) == 5
    hash_small = mod._canonical_sha256({"scanner_config": sc_small})

    # 不變式驗證：scanner_config 內容改變 → canonical sha256 改變
    assert hash_full != hash_small


def test_scanner_config_load_failure_returns_none_does_not_break_replay(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """T3 fail-soft：scanner_config.toml 不存在時 _load 回 None，replay 不阻斷。"""
    import app.replay_full_chain_routes as mod

    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(tmp_path))  # 無 settings/ 目錄
    sc = mod._load_production_scanner_config()
    assert sc is None  # fail-soft

    # 跑 full-chain run 仍應 OK，manifest 不含 scanner_config key
    registered: list[Any] = []

    async def fake_events(**kwargs):
        return ([_sample_event("BTCUSDT", 1_700_000_000_000)], {"BTCUSDT": 1})

    def fake_register(get_pg_conn, actor, body, **kwargs):
        registered.append(body)
        return {
            "experiment_id": str(uuid.uuid4()),
            "manifest_hash": "9" * 64,
            "status": "created",
            "idempotency_hit": False,
        }, None

    def fake_run(**kwargs):
        return uuid.uuid4().hex, 1234, None, tmp_path / "artifact"

    monkeypatch.setattr(mod, "_fetch_full_chain_events", fake_events)
    monkeypatch.setattr(mod, "_fetch_edge_estimate_snapshot_sync", _empty_edge_snapshot)
    monkeypatch.setattr(mod._er, "run_register_in_pg_xact", fake_register)
    monkeypatch.setattr(mod._rrun, "_do_pg_path_for_run_sync", fake_run)

    client = _client(monkeypatch, tmp_path / "fixtures")
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
    manifest = registered[0].manifest_jsonb
    # scanner_config load 失敗 → manifest 不含此 key（fail-soft）
    assert "scanner_config" not in manifest
    # 其他既有 manifest field 仍 OK
    assert manifest["mode"] == "full_chain"
    assert manifest["strategy"] == "grid_trading"


def test_strategy_params_toml_loader_engine_normalization(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """T4 helper unit test：_load_production_strategy_params_toml engine 正規化。"""
    import app.replay_full_chain_routes as mod

    settings_root = tmp_path / "settings"
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(tmp_path))
    _write_minimal_strategy_params(settings_root, "demo")
    _write_minimal_strategy_params(settings_root, "live")

    # 正規化大小寫
    demo = mod._load_production_strategy_params_toml(engine="DEMO")
    assert demo is not None
    assert "ma_crossover" in demo

    live = mod._load_production_strategy_params_toml(engine="live")
    assert live is not None
    assert "ma_crossover" in live

    # 未知 engine 回 None
    assert mod._load_production_strategy_params_toml(engine="mainnet") is None
    assert mod._load_production_strategy_params_toml(engine="") is None

    # risk config loader 對稱行為
    _write_minimal_risk_config(settings_root, "demo")
    risk_demo = mod._load_production_risk_overrides_toml(engine="demo")
    assert risk_demo is not None
    assert risk_demo["limits"]["open_positions_max"] == 25
    assert mod._load_production_risk_overrides_toml(engine="unknown") is None


# ──────────────────────────────────────────────────────────────────────
# P2-10：duplicate-spawn 並發覆蓋 + Linux-empirical evidence gate 分離
#
# 背景（cold audit Wave 4 P2-10）：上方 full-chain happy-path test 把
# ``_do_pg_path_for_run_sync`` 整個 monkeypatch 掉（test 235 段 fake_run），
# 因此 run_route.py:178-198 的真正 dedup 邏輯——PG advisory lock + per-actor/
# global cap probe——從未被任何 Mac 單測執行。後果：Mac 全綠時，Linux PG /
# subprocess 路徑可能已壞或會 duplicate-spawn 而沒人發現。
#
# 本段不再 mock 掉 dedup，而是用 fake route_helpers + fake PG cursor 真正驅動
# ``_do_pg_path_for_run_sync``，讓兩次「並發」run 競爭同一 actor 的 cap，
# 斷言只有第一次成功、第二次被 cap probe 擋下回 replay_per_actor_cap_exceeded
# →409。驗的是 dedup 的「意圖」（重複 run 不得同時 register/spawn），不是把它
# mock 走。
#
# 為什麼用「已提交狀態」共享而非真 thread race：真正的 race 互斥點在 PG
# advisory lock（``try_acquire_pg_advisory_locks``，serializable xact 內），
# 那是 PG runtime 語意，Mac sandbox 無 PG 抓不到。Mac 層能且只能驗
# defense-in-depth 的 cap-count gate：第一個 run INSERT 'starting'/'running'
# 後，第二個 run 的 ``count_active_runs_for_actor`` 必須看到 >=cap 並 fail-closed。
# advisory-lock 互斥本身的 race 證明屬下方 LINUX-EMPIRICAL gate。
# ──────────────────────────────────────────────────────────────────────


class _FakeRunBody:
    """duck-type body：``_do_pg_path_for_run_sync`` 只讀這兩個屬性。"""

    def __init__(self, experiment_id: str, idempotency_key: str) -> None:
        self.experiment_id = experiment_id
        self.idempotency_key = idempotency_key


class _FakeCursor:
    """最小 PG cursor stub：execute 吞掉所有 SQL（dedup 邏輯不依賴回傳）。"""

    def execute(self, *args: Any, **kwargs: Any) -> None:
        return None


class _FakeConn:
    """context-manager PG conn stub；commit/rollback no-op。"""

    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def __enter__(self) -> "_FakeConn":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False


class _DedupFakeRouteHelpers:
    """fake route_helpers，模擬 V045 active-run 帳本。

    關鍵：``count_active_runs_for_actor`` 回傳「已成功啟動的 run 數」，使第二
    次呼叫看到第一次留下的 'running' row → 觸發 real cap gate。advisory lock
    一律放行（Mac 不模擬鎖互斥；那是 Linux gate）。
    """

    def __init__(self, *, manifest_uuid: str, fixture_path: Path) -> None:
        self._manifest_uuid = manifest_uuid
        self._fixture_path = fixture_path
        self.active_for_actor = 0
        self.spawn_calls = 0
        self.lock_attempts = 0

    def v045_table_present(self, cur: Any) -> bool:
        return True

    def try_acquire_pg_advisory_locks(self, cur: Any, actor_id: str):
        # Mac 層：鎖永遠成功；真正的鎖互斥 race 在 Linux PG gate 驗。
        self.lock_attempts += 1
        return True, None

    def count_active_runs_for_actor(self, cur: Any, actor_id: str) -> int:
        return self.active_for_actor

    def count_active_runs_global(self, cur: Any) -> int:
        return self.active_for_actor

    def lookup_registered_experiment_id(self, cur: Any, experiment_id: str):
        return self._manifest_uuid

    def resolve_artifact_output_dir(self, run_id: str) -> Path:
        return self._fixture_path / run_id

    def build_default_manifest_payload(self, **kwargs: Any) -> dict[str, Any]:
        return {"experiment_id": kwargs.get("experiment_id")}

    def write_manifest_fixture(self, **kwargs: Any) -> Path:
        return self._fixture_path / "manifest.json"

    def spawn_replay_runner(self, **kwargs: Any):
        # 成功 spawn → 該 actor active 數 +1，使後續 run 落入 cap gate。
        self.spawn_calls += 1
        self.active_for_actor += 1
        return 4321, None

    def resolve_process_started_at_ms(self, pid: int) -> int:
        return 1_700_000_000_000


def test_pg_run_path_second_concurrent_run_blocked_by_cap_no_duplicate_spawn(
    tmp_path: Path,
) -> None:
    """LOCAL 並發 dedup：第二個 run 撞 per-actor cap → 不 duplicate-spawn。

    直接驅動 run_route._do_pg_path_for_run_sync（不 mock），兩次同 actor 呼叫
    模擬並發提交。real cap probe（run_route.py:194）必須讓第二次回
    replay_per_actor_cap_exceeded，且 spawn_replay_runner 僅被呼叫一次。
    """
    from replay import run_route as rrun  # type: ignore[import-not-found]

    helpers = _DedupFakeRouteHelpers(
        manifest_uuid=str(uuid.uuid4()),
        fixture_path=tmp_path,
    )

    def get_pg_conn_fn():
        return _FakeConn(_FakeCursor())

    body = _FakeRunBody(
        experiment_id=str(uuid.uuid4()),
        idempotency_key="dedup-test-key",
    )

    # 第一個 run：cap=1、actor 目前 0 active → 應成功 spawn。
    run_id_1, pid_1, err_1, _ = rrun._do_pg_path_for_run_sync(
        body=body,
        actor_id="dedup-actor",
        get_pg_conn_fn=get_pg_conn_fn,
        route_helpers=helpers,
        statement_timeout_ms=2000,
        per_actor_cap=1,
        global_cap=1,
    )
    assert err_1 is None
    assert run_id_1 is not None
    assert pid_1 == 4321
    assert helpers.spawn_calls == 1
    assert helpers.active_for_actor == 1

    # 第二個 run（同 actor、模擬並發提交）：actor 已有 1 active、cap=1
    # → real cap gate 必須 fail-closed，且絕不可第二次 spawn。
    run_id_2, pid_2, err_2, _ = rrun._do_pg_path_for_run_sync(
        body=body,
        actor_id="dedup-actor",
        get_pg_conn_fn=get_pg_conn_fn,
        route_helpers=helpers,
        statement_timeout_ms=2000,
        per_actor_cap=1,
        global_cap=1,
    )
    assert err_2 == "replay_per_actor_cap_exceeded"
    assert run_id_2 is None
    assert pid_2 is None
    # 核心 dedup 不變式：duplicate run 沒有觸發第二次 subprocess spawn。
    assert helpers.spawn_calls == 1

    # cap-exceeded → 409（不 fallback in-memory；PG 狀態 canonical）。
    http_err = rrun.map_run_pg_error_to_http(err_2, experiment_id=body.experiment_id)
    assert http_err is not None
    status, detail = http_err
    assert status == 409
    assert "replay_per_actor_cap_exceeded" in detail["reason_codes"]


def test_pg_run_path_global_cap_blocks_cross_actor_duplicate(
    tmp_path: Path,
) -> None:
    """global cap：不同 actor 但 global active 已滿 → 第二個 run 被擋。

    驗 run_route.py:196-198 的 global-cap defense-in-depth：actor B 即便自身
    0 active，只要 global active >= global_cap 即 fail-closed，不 duplicate-spawn。
    """
    from replay import run_route as rrun  # type: ignore[import-not-found]

    helpers = _DedupFakeRouteHelpers(
        manifest_uuid=str(uuid.uuid4()),
        fixture_path=tmp_path,
    )

    def get_pg_conn_fn():
        return _FakeConn(_FakeCursor())

    # actor A 先成功啟動 → global active = 1。
    body_a = _FakeRunBody(experiment_id=str(uuid.uuid4()), idempotency_key="key-a")
    _, _, err_a, _ = rrun._do_pg_path_for_run_sync(
        body=body_a,
        actor_id="actor-a",
        get_pg_conn_fn=get_pg_conn_fn,
        route_helpers=helpers,
        statement_timeout_ms=2000,
        per_actor_cap=5,  # per-actor 寬鬆，逼測試只命中 global gate
        global_cap=1,
    )
    assert err_a is None
    assert helpers.spawn_calls == 1

    # actor B per-actor 0 active，但 global 已滿 → global cap gate 必須 fire。
    body_b = _FakeRunBody(experiment_id=str(uuid.uuid4()), idempotency_key="key-b")
    _, _, err_b, _ = rrun._do_pg_path_for_run_sync(
        body=body_b,
        actor_id="actor-b",
        get_pg_conn_fn=get_pg_conn_fn,
        route_helpers=helpers,
        statement_timeout_ms=2000,
        per_actor_cap=5,
        global_cap=1,
    )
    assert err_b == "replay_global_cap_exceeded"
    # 跨 actor duplicate 也不得 spawn 第二次。
    assert helpers.spawn_calls == 1

    status, detail = rrun.map_run_pg_error_to_http(
        err_b, experiment_id=body_b.experiment_id,
    )
    assert status == 409
    assert "replay_global_cap_exceeded" in detail["reason_codes"]


# ──────────────────────────────────────────────────────────────────────
# LINUX-EMPIRICAL EVIDENCE GATE（與上方 Mac 單測明確分離）
#
# 上方 Mac 單測只能驗 cap-count defense-in-depth gate（run_route.py:194-198）。
# 真正抗並發 race 的互斥點是 PG advisory lock（try_acquire_pg_advisory_locks，
# serializable xact 內），以及 subprocess 真實 spawn——兩者皆是 PG/OS runtime
# 語意，Mac mock sandbox 無法觸及（CLAUDE.md「Data, Migrations, And
# Validation」：Mac mocked pytest 抓不到 PG runtime semantics）。
#
# 下列斷言必須在 Linux trade-core 以真 PG empirical 驗證，預設 skip：
#   1. 兩個真並發 HTTP /full-chain/run（同 actor）對打 advisory lock，
#      恰一個拿到鎖 INSERT、另一個 lock_err 回 409，DB 內只有 1 條
#      replay.run_state 'running' row（無 duplicate row）。
#   2. spawn_replay_runner 真的只 fork 出一個 replay_runner subprocess
#      （ps 計數 == 1），且第二次請求 0 subprocess。
#   3. V045 (replay.run_state) 表存在；count_active_runs_* 對真 schema 回正確值。
#
# 啟用方式（Linux runtime，operator/E4 執行）：
#   OPENCLAW_REPLAY_LINUX_PG_EMPIRICAL=1 pytest -q \
#     tests/test_replay_full_chain_run_routes.py \
#     -k linux_empirical_duplicate_spawn
# 在 Mac CI / dev 此 test 永遠 skip，不阻塞綠燈，但也不偽裝已驗 PG race。
# ──────────────────────────────────────────────────────────────────────


def test_linux_empirical_duplicate_spawn_advisory_lock_gate() -> None:
    """PG advisory-lock 並發 race 的真實證據門（Linux-only，預設 skip）。

    為什麼必須 fail-closed skip 而非 mock：advisory-lock 互斥是 PG runtime
    語意；若在 Mac 用 mock「假裝」驗過，會掩蓋 Linux PG 路徑壞掉或 duplicate-
    spawn 的風險（正是 P2-10 要堵的洞）。此 gate 只在真 PG 環境跑。
    """
    import os

    import pytest

    if os.environ.get("OPENCLAW_REPLAY_LINUX_PG_EMPIRICAL") != "1":
        pytest.skip(
            "Linux PG empirical gate：需 OPENCLAW_REPLAY_LINUX_PG_EMPIRICAL=1 + "
            "真 trade-core PG（advisory-lock 並發 race + subprocess 計數驗證）。"
            "Mac mock sandbox 抓不到 PG runtime semantics，刻意不在此實作以免偽綠。"
        )

    pytest.fail(
        "Linux PG empirical duplicate-spawn 證據尚未接線；請 E4 在 trade-core "
        "以真 PG + 兩並發 /full-chain/run 驗 advisory-lock 互斥 + 單一 run_state "
        "row + 單一 subprocess（見本檔 LINUX-EMPIRICAL gate 註解步驟 1-3）。"
    )
