# Learning Proof/Promotion Gate Runtime Checkpoint

Date: 2026-06-29
Owner: PM
Status: DONE_WITH_CONCERNS
Runtime transition: BLOCKED_BY_RUNTIME

## What changed

`trade-core` is now source-synced to `16f4028313f45dc6af411e81d9eb841ed39878d4`, and the learning cron expected-head markers were repinned. The proof/promotion gate was run on runtime and correctly failed closed.

Key artifact:

- `/tmp/openclaw/session_loop_state_20260629T_proof_promotion_gate/learning_proof_promotion_gate_after_16f_sync.json`
- sha256 `38e3e1fec04c7eb8cb8bb4ec8860b6a92bd0c8159e41c5845eaeb035b8faa9e5`
- status `LEARNING_PROOF_PROMOTION_BLOCKED_BY_SERVING_SNAPSHOT_NO_AUTHORITY`
- authority violations `0`

## Runtime status

- Engine PID `877736` is alive.
- Demo-only env is intact: mainnet disabled, legacy paper disabled, bounded Demo learning lane enabled.
- API unit ownership was repaired: an orphan uvicorn process was holding port 8000; `openclaw-trading-api.service` now owns it at MainPID `970845`.
- `/openapi.json` still returns a Pydantic forward-ref 500. Console redirects and protected API behavior still respond, but OpenAPI/schema tooling is not clean.

## Still blocked

Bounded Demo execution is still blocked because:

- Demo API key slot is still `FWkGZX...g53T`, not expected `BHw4...`.
- Connector mode is still read-only / write-disabled.
- Serving/proof chain is not ready.
- There is still no candidate-matched order/fill/fee/slippage/reconstruction evidence.

No order, live/mainnet, Cost Gate change, model load, registry/PG write, or secret/env mutation was performed.
