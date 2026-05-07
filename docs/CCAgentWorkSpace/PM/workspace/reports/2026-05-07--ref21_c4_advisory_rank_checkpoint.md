# REF-21 C4 Replay Advisory Ranking Checkpoint

## Scope

This checkpoint adds the first ML/Dream-facing replay advisory surface. It is
read-only and cannot write strategy/risk parameters, replay advisory rows,
handoff candidates, or live/demo config.

## Implemented

- Added `app/replay_advisory_routes.py`.
  - `POST /api/v1/replay/advisory/rank`
  - Operator + `replay:write` auth gate.
  - Same 10/min replay limiter.
  - Candidate cap defaults to 100 and is bounded to <=1000 via
    `OPENCLAW_REPLAY_ADVISORY_MAX_K`.
- Added deterministic advisory ranking from replay report analytics and
  coverage verdicts.
  - Score uses fee-net bps, reject/miss penalty, and recorder fidelity tier.
  - Every output row sets:
    `advisory_only=true`, `mutation_allowed=false`,
    `eligible_for_demo_handoff=false`.
- Registered the router in `app/main.py`.

## Verification

- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_advisory_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py`
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_advisory_routes.py -q`
  - 2 passed.
- `git diff --check`

## Boundary

This is not a DreamEngine applier and not a demo handoff path. It only ranks
already-produced replay summaries. Any future parameter application must still
flow through the separate governed demo applier path.
