# Killboard Probe Authority Semantics Runtime Sync

PM closed `P1-RUNTIME-SOURCE-SYNC-KILLBOARD-AUTHORITY-SEMANTICS-REFRESH` as `DONE_WITH_CONCERNS`.

Runtime is now clean at `7d118e81`; cron expected-head pins are synced to that head; direct `runtime_runner` refresh updated `alpha_discovery_latest.json`.

Important operator read: legacy `ready_for_probe=1` / `actionable_probe_found=true` now means review readiness only. The authority fields are explicit and false:

- `actionable_probe_semantics=OPERATOR_REVIEW_READY_NO_RUNTIME_AUTHORITY`
- `runtime_probe_authority_found=false`
- `runtime_order_authority_found=false`
- `promotion_evidence_found=false`
- `cost_gate_mutation_found=false`

Boundary preserved：no Bybit call/order/cancel/modify, no API POST, no PG write, no service restart, no Cost Gate lowering, no probe/order/live authority, no Rust writer, no promotion proof.
