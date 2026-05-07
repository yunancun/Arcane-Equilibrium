"""REF-21 replay advisory-only ranking routes.

These routes are for ML/Dream exploration support. They do not run replay,
write advisory rows, call appliers, or mutate live/demo parameters.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import main_legacy as base
from .auth import require_scope_and_operator

try:
    from ..replay import route_helpers as _rh  # type: ignore[no-redef]
except ImportError:
    from replay import route_helpers as _rh  # type: ignore[no-redef]


replay_advisory_router = APIRouter(
    prefix="/api/v1/replay/advisory",
    tags=["Replay Advisory / 回放建議"],
)
_REPLAY_LIMITER = base.limiter


class ReplayAdvisoryCandidate(BaseModel):
    experiment_id: str = Field(min_length=1, max_length=128)
    strategy: Optional[str] = Field(default=None, max_length=64)
    symbol: Optional[str] = Field(default=None, max_length=32)
    analytics: dict[str, Any] = Field(default_factory=dict)
    coverage_verdict: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplayAdvisoryRankRequest(BaseModel):
    requester: str = Field(default="operator", min_length=1, max_length=64)
    candidates: list[ReplayAdvisoryCandidate] = Field(default_factory=list)
    objective: str = Field(default="fee_net_bps", min_length=1, max_length=64)


def _replay_advisory_rate_limit_key(request: Request) -> str:
    actor = getattr(request.state, "actor", None)
    actor_id = getattr(actor, "actor_id", None)
    return str(actor_id or request.client.host if request.client else "unknown")


def _require_replay_write(actor: base.AuthenticatedActor) -> None:
    require_scope_and_operator(actor, "replay:write")


def _max_advisory_candidates() -> int:
    raw = os.environ.get("OPENCLAW_REPLAY_ADVISORY_MAX_K", "100")
    try:
        parsed = int(raw)
    except ValueError:
        parsed = 100
    return max(1, min(parsed, 1000))


def _num(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed == parsed else default


def _tier_bonus(tier: str) -> float:
    if tier == "S1_CALIBRATED_READY":
        return 20.0
    if tier == "S1_LIMITED_READY":
        return 10.0
    if tier == "S2_PLUS_LOCAL_BBO":
        return 2.0
    return 0.0


def rank_replay_advisory_candidates(
    candidates: list[ReplayAdvisoryCandidate],
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for idx, candidate in enumerate(candidates):
        analytics = dict(candidate.analytics or {})
        coverage = dict(candidate.coverage_verdict or {})
        net_bps = _num(analytics.get("net_bps_after_fee"), 0.0)
        reject_rate = _num(analytics.get("reject_or_miss_rate"), 0.0)
        tier = str(coverage.get("tier") or "S2_PUBLIC_KLINE_ONLY")
        score = net_bps - (reject_rate * 25.0) + _tier_bonus(tier)
        reason_codes = []
        reason_codes.extend(analytics.get("reason_codes") or [])
        reason_codes.extend(coverage.get("reason_codes") or [])
        ranked.append({
            "rank": 0,
            "input_index": idx,
            "experiment_id": candidate.experiment_id,
            "strategy": candidate.strategy,
            "symbol": candidate.symbol,
            "score": score,
            "net_bps_after_fee": analytics.get("net_bps_after_fee"),
            "verdict": analytics.get("verdict") or "needs_more_data",
            "coverage_tier": tier,
            "reject_or_miss_rate": reject_rate,
            "advisory_only": True,
            "mutation_allowed": False,
            "eligible_for_demo_handoff": False,
            "reason_codes": sorted({str(item) for item in reason_codes if item}),
        })
    ranked.sort(key=lambda item: item["score"], reverse=True)
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank
    return ranked


@replay_advisory_router.post("/rank")
@_REPLAY_LIMITER.limit("10/minute", key_func=_replay_advisory_rate_limit_key)
async def post_replay_advisory_rank(
    request: Request,
    body: ReplayAdvisoryRankRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    _require_replay_write(actor)
    cap = _max_advisory_candidates()
    if len(body.candidates) > cap:
        raise HTTPException(
            status_code=400,
            detail={
                "reason_codes": ["replay_advisory_candidate_cap_exceeded"],
                "message": f"candidate count {len(body.candidates)} exceeds cap {cap}",
            },
        )
    ranked = rank_replay_advisory_candidates(body.candidates)
    return _rh.replay_response_envelope({
        "mode": "replay_advisory_rank",
        "requester": body.requester,
        "objective": body.objective,
        "candidate_count": len(body.candidates),
        "candidate_cap": cap,
        "advisory_only": True,
        "mutation_allowed": False,
        "applier_path": "not_invoked",
        "output_policy": "read_only_ml_dream_advisory_no_live_or_demo_mutation",
        "ranked_candidates": ranked,
    })


__all__ = [
    "replay_advisory_router",
    "rank_replay_advisory_candidates",
]
