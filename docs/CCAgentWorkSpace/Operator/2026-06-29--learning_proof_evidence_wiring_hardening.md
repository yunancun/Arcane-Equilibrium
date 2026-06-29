# Learning Proof Evidence Wiring Hardening

Date: 2026-06-29
Owner: PM
Status: DONE_WITH_CONCERNS

Correction on 2026-06-30: the observed key is in the Bybit Demo slot, not the live/mainnet key, and the operator confirmed masked `FWkGZX...g53T` is the correct Demo Read-Write key with OpenAPI IP whitelist `79.117.10.224`. The previous `BHw4...` expected-prefix mismatch is a stale expected-hint false positive. Do not enable connector writes until readiness is rerun and a reviewed Demo-only connector cutover is green.

What changed:

- Added a row-backed proof-evidence producer for `cost_gate_learning_candidate_proof_evidence_v1`.
- Tightened proof identity: fills and controls must match side-cell, strategy, symbol, side, and horizon.
- Tightened authority scanning for `*_allowed_by_this_packet=true`.
- Tightened learning stack health so stale cron expected-head pins become explicit blockers.

Verification:

- Proof/serving/evidence focused tests: `31 passed`
- Learning stack health tests: `8 passed`
- `py_compile` and `git diff --check`: PASS
- `/openapi.json`: HTTP `200`

No secret/env/cron/service/runtime mutation, Bybit call, order, Cost Gate change, model load, PG/registry write, live authority, or promotion authority occurred.
