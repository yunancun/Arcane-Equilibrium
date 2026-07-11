# GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1 — B2.2c Event-Primary Follow-up

Date: 2026-07-11
Goal: `GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1`
State: `DONE_SOURCE_ACCEPTED_B2_2C_EVENT_PRIMARY`
READY-handoff repair: `03ef761bf92a6055ef3555d68d47a1f075b2298b`
Event-primary checkpoint: `1b85318f29a16d5a7575b27cb158486fdfd47331`
Goal next item: `WP3-PROOF-REWARD-REPOSITORY-ADAPTERS`

## Outcome

The concurrently landed `328125a08` handoff and `8999aa2b` WP3
validation adapter were preserved. The stale local seven-file implementation
was neither pushed nor cherry-picked. Reconciliation isolated two current-main
gaps and landed them as separate narrow commits.

The first commit repairs a B2.2c causality regression: when normalized READY
evidence is valid but a missing/invalid policy leaves the arbiter timestamp
empty, the hash-bound board `evaluated_at` becomes the fallback decision time.
An arbiter-supplied time still wins, malformed/non-READY evidence cannot supply
the fallback, and `_build_handoff_identity()` still enforces exact decision
time plus `generated_at <= evaluated_at`.

The second commit replaces five-second candidate-board polling with a bounded
Linux inotify wake source multiplexed with the existing PostgreSQL listener.
Event names are wake-only; learning content always comes from a full bounded
`load_candidate_evidence_snapshot()` reconciliation. Startup, queue overflow,
and current-watch invalidation request reconciliation and rebuild the complete
event fd/watch. A held directory fd plus `/proc/self/fd/<fd>/.` binds the
watch to the verified inode across configured-path ABA. `IN_DELETE` is
intentional because publication links the new immutable board before pruning
the previous board; deletion retries a create-time scan that observed the
transient file-count ceiling.

## Machine verification

- Pristine `origin/main` affected projection file: `6 failed, 17 passed`.
- Repaired projection file: `23 passed in 0.09s`.
- Event consumer: `33 passed, 1 skipped in 0.06s`.
- Complete `program_code/ml_training/tests`: `1790 passed, 36 skipped in 11.89s`.
- Python compile: PASS.
- `git diff --check`: PASS.
- Independent event E2 review: PASS.
- Independent handoff-causality review: PASS.
- Final P0/P1/P2: `0/0/0`.

The one focused skip is the real Linux `os.link()`/inotify integration on
Darwin. Synthetic ABI, overflow/rearm, distinct-fd ownership, post-rearm
selection, PG fairness, candidate-input forwarding, truncation, and held-fd ABA
tests pass locally.

## Boundaries

This is source acceptance, not Linux or runtime acceptance. No Linux checkout,
service, PostgreSQL, Bybit, exchange, order, Decision Lease, Guardian,
RiskConfig, Cost Gate, training, model, registry, serving, promotion, or
retention mutation occurred. All direct authority remains false and all
authority counters remain zero. Actual Linux `/proc/self/fd`, inotify,
service restart/recovery, and natural-cycle evidence require a fresh exact
`E3 -> BB -> PM` gate.

## Fact / inference / assumption

Fact: current source now has event-primary candidate-board wakes and the full ML
suite is green. Fact: WP3 validation source remains untouched and accepted.
Fact: proof/reward/complete runtime chains remain zero at the last accepted
runtime snapshot.

Inference: the source seam is ready for a later Linux gate; it is not evidence
that the production service has consumed any board event.

Assumption: the user remains Operator and has not granted any new runtime,
exchange, order, serving, promotion, or protected-evidence deletion authority.

## Next action

Keep the Goal `ACTIVE`. Implement only the remaining WP3 proof/reward
repository adapter seam. Do not reopen B2.2c event transport without a material
P0/P1 or a fresh Linux runtime gate.
