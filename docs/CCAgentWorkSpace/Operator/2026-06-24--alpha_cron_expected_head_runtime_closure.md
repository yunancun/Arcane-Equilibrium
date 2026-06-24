# Alpha Cron Expected-Head Runtime Closure

PM closed `P1-ALPHA-CRON-RUNTIME-RUNNER-EXPECTED-HEAD-PROPAGATION` as `DONE_WITH_CONCERNS`.

What changed:

- Source commit `44a337e3` makes `alpha_discovery_throughput_cron.sh` pass expected-head into `runtime_runner`.
- Runtime `trade-core` is clean at `44a337e3`.
- Demo-learning crontab expected-head pins are synced to `44a337e3`.
- Alpha natural cron line 57 now includes `OPENCLAW_EXPECTED_SOURCE_HEAD=44a337e3cca07c8c984f6c3af0a702d7550628a5`.

Latest alpha artifact after cron-shape refresh:

- `created_at_utc=2026-06-24T14:52:50Z`
- `runtime_source.expected_head_status=MATCH`
- `runtime_source.git_status=SYNCED_CLEAN`
- `runtime_probe_authority_found=false`
- `runtime_order_authority_found=false`
- `promotion_evidence_found=false`
- `cost_gate_mutation_found=false`
- `actionable_probe_semantics=OPERATOR_REVIEW_READY_NO_RUNTIME_AUTHORITY`

Important read:

- Legacy `ready_for_probe=1` remains review readiness only.
- This does not grant probe/order/live authority.
- Bounded probe authorization still requires exact candidate-scoped typed-confirm.

Boundary preserved：no Bybit call/order/cancel/modify, no API POST, no PG write, no service restart, no Cost Gate lowering, no probe/order/live authority, no Rust writer, no promotion proof.
