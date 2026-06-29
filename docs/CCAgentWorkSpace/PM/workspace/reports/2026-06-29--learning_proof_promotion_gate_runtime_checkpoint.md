# Learning Proof/Promotion Gate Runtime Checkpoint

Date: 2026-06-29
Owner: PM
Status: DONE_WITH_CONCERNS
Runtime transition: BLOCKED_BY_RUNTIME

## Summary

`trade-core` was fast-forwarded to `16f4028313f45dc6af411e81d9eb841ed39878d4` and the learning cron expected-head markers were repinned to that head. The bounded Demo proof/promotion gate was materialized again after sync.

Runtime proof artifact:

- JSON: `/tmp/openclaw/session_loop_state_20260629T_proof_promotion_gate/learning_proof_promotion_gate_after_16f_sync.json`
- JSON sha256: `38e3e1fec04c7eb8cb8bb4ec8860b6a92bd0c8159e41c5845eaeb035b8faa9e5`
- Markdown sha256: `e94276a479a18e97add61c88efe94e23358c32d99fe56be30c0291f312347539`
- Status: `LEARNING_PROOF_PROMOTION_BLOCKED_BY_SERVING_SNAPSHOT_NO_AUTHORITY`
- Authority violations: `0`

The gate remains correctly blocked because the serving snapshot is not ready and there are no row-backed candidate-matched Demo fills with fee/slippage/reconstruction/after-cost evidence.

## Runtime Verification

- Runtime checkout: clean on `main...origin/main` at `16f4028313f45dc6af411e81d9eb841ed39878d4`
- Learning cron expected-head marker count for `16f4028313f45dc6af411e81d9eb841ed39878d4`: `9`
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/learning_proof_promotion_gate.py helper_scripts/research/tests/test_cost_gate_learning_proof_promotion_gate.py`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_learning_proof_promotion_gate.py` -> `11 passed`
- Adjacent learning/readiness suite -> `57 passed`
- `git diff --check`

## Runtime Process State

- Engine PID `877736` remains alive.
- Engine env remains Demo-only:
  - `OPENCLAW_ALLOW_MAINNET=0`
  - `OPENCLAW_ENABLE_PAPER=0`
  - `OPENCLAW_DEMO_LEARNING_LANE_WRITER=1`
  - `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=1`
  - `OPENCLAW_DEMO_LEARNING_LANE_PLAN=/tmp/openclaw/cost_gate_learning_lane/bounded_demo_probe_soak_plan.json`
- API process ownership drift was repaired: orphan uvicorn PID `938438` held port `100.91.109.86:8000`; after recovery `openclaw-trading-api.service` owns the port at MainPID `970845`, `NRestarts=0`.
- Remaining API concern: `/openapi.json` returns a Pydantic forward-ref 500. The console redirects and authenticated API endpoints still protect as expected, but this should be treated as runtime hygiene debt before relying on OpenAPI-generated tooling.

## Remaining Blockers

- Demo API slot still shows key prefix `FWkGZX...g53T`, while the expected operator-provided prefix is `BHw4...`.
- `trading_services.env` remains `BYBIT_MODE=read_only` and `BYBIT_CONNECTOR_WRITE_ENABLED=false`.
- Serving snapshot remains blocked by training/registry repair state.
- Strict candidate evidence scan still has no candidate-matched actual order/fill/fee/slippage/reconstruction evidence.

## Boundary

No engine restart, secret write, env mutation, private Bybit call, Decision Lease acquire/release, order/cancel/modify, registry/PG write, model load, serving slot write, Cost Gate lowering, live/mainnet authority, promotion authority, or profit proof occurred. The only runtime mutation was API process ownership recovery for the existing control API user unit.

Next executable step is secure Demo key/secret entry through the approved settings API/GUI path plus reviewed Demo-only connector mode cutover, then rerun readiness and final-window BBO/Decision Lease/Guardian/Rust authority/GUI cap gates.
