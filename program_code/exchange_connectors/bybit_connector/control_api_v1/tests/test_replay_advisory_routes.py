from __future__ import annotations

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
from app.replay_advisory_routes import (  # noqa: E402
    replay_advisory_router,
    rank_replay_advisory_candidates,
    ReplayAdvisoryCandidate,
)


def _operator_actor() -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_id="replay-advisory-test",
        actor_type="human",
        roles={"operator", "viewer"},
        scopes={"replay:write"},
    )


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(replay_advisory_router)
    app.dependency_overrides[current_actor] = _operator_actor
    return TestClient(app)


def test_rank_replay_advisory_candidates_is_advisory_only() -> None:
    candidates = [
        ReplayAdvisoryCandidate(
            experiment_id="slow",
            analytics={
                "net_bps_after_fee": 1.0,
                "reject_or_miss_rate": 0.5,
                "verdict": "development_sandbox_pass",
            },
            coverage_verdict={"tier": "S2_PUBLIC_KLINE_ONLY"},
        ),
        ReplayAdvisoryCandidate(
            experiment_id="strong",
            analytics={
                "net_bps_after_fee": 12.0,
                "reject_or_miss_rate": 0.0,
                "verdict": "development_sandbox_pass",
            },
            coverage_verdict={"tier": "S1_LIMITED_READY"},
        ),
    ]

    ranked = rank_replay_advisory_candidates(candidates)

    assert [item["experiment_id"] for item in ranked] == ["strong", "slow"]
    assert all(item["advisory_only"] is True for item in ranked)
    assert all(item["mutation_allowed"] is False for item in ranked)
    assert all(item["eligible_for_demo_handoff"] is False for item in ranked)


def test_replay_advisory_rank_route_caps_and_never_invokes_applier() -> None:
    client = _client()
    resp = client.post(
        "/api/v1/replay/advisory/rank",
        json={
            "requester": "dream_engine",
            "objective": "fee_net_bps",
            "candidates": [
                {
                    "experiment_id": "exp-a",
                    "strategy": "grid_trading",
                    "analytics": {
                        "net_bps_after_fee": 4.0,
                        "reject_or_miss_rate": 0.1,
                        "verdict": "development_sandbox_pass",
                    },
                    "coverage_verdict": {"tier": "S2_PLUS_LOCAL_BBO"},
                }
            ],
        },
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["mode"] == "replay_advisory_rank"
    assert data["requester"] == "dream_engine"
    assert data["advisory_only"] is True
    assert data["mutation_allowed"] is False
    assert data["applier_path"] == "not_invoked"
    assert data["ranked_candidates"][0]["eligible_for_demo_handoff"] is False
    assert data["output_policy"] == "read_only_ml_dream_advisory_no_live_or_demo_mutation"
