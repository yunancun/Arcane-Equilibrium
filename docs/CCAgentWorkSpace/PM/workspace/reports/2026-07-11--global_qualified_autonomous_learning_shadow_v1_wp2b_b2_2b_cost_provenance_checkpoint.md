# GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1 — WP2-B2.2b Cost Provenance Checkpoint

Date: 2026-07-11
Owner: PM
State: `DONE_SOURCE_ACCEPTED_B2_2B_COST_PROVENANCE`
Source checkpoint: `a7d8d5f8b3af3282ab75667b31e45a40a712b2c4`
Source commits: `d42671056`, `bb7312033`, `c91b41c12`, `a7d8d5f8b`
Next work: `WP2-B2.2c-RESTART-SAFE-EVENT-DRIVEN-PRIMARY-HANDOFF`

## Decision

The B2.2b source vertical is accepted. A fully rehashed artifact can no longer
make the global expected-cost mean differ from the count-weighted accepted
symbol means. Both independent untrusted-ingress normalizers enforce exact
keysets, finite non-bool numbers, positive integral counts, sorted unique
symbols, global count closure, an exact `abs(mean_signed) <= mean_abs` relation,
and the weighted global `mean_abs` reconstruction. Invalid evidence fails
closed; a thin symbol uses only the reconciled global fallback and cannot obtain
a lower invented cost.

The publisher, board, adapter, and arbiter bind the same canonical artifact
payload/projection hashes and causal source-as-of/board/decision sequence.
Canonical JSON key reordering retains semantics; material mutation changes the
bound hash/fingerprint. Eligibility, ranking, cooldown, and proof-gap logic do
not bypass cost evidence. Authority counters remain zero.

## Verification

- E1 focused adversarial fixtures: `4 passed` (including global and symbol
  signed-cost overages of `5e-10`).
- E2 independent logic/bypass review: `PASS`.
- QC algebra and cost-invariant review: `PASS`.
- E4, one complete integrated suite for the final byte generation: `586 passed
  in 6.38s`.
- QA: `PASS_SOURCE_CHECKPOINT_TO_PM`.
- `git diff --check`: `PASS`.

The governance wrapper denied the substituted `mac_dev` interpreter before a
subprocess started (zero tests); it did not silently run another interpreter.
The existing project `venvs/mac_dev` interpreter then ran the one authorized
complete suite exactly once under the explicit source/test scope.

## Scope, complexity, and minimality

Against the clean `1e994d641` source baseline, the accepted B2.2b vertical has
11 production/config files (`+6,357/-542`) and 14 test/support files
(`+8,109/-635`), total `+14,466/-1,177`. It contains the original
board/publisher and adapter/arbiter integration plus the c91 invariant closure
and final four-path strict-bound micro-fix. The final P1 repair is exactly two
production guards and two tests (`+13/-14`): it removes an inappropriate
`1e-9` allowance from the safety inequality while retaining tolerance only for
weighted rollup comparison.
The two normalizers cannot safely share a new helper without introducing a third
abstraction across separate fail-closed ingress boundaries. This is the
documented minimality decision, not a reopening of WP2.

The earliest retained canonical B2.2b worktree timestamp is
`2026-07-11T13:59:40Z`; the final acceptance observation at
`2026-07-11T14:23:25Z` bounds the observed WIP age to `23m45s`. There were three
review/fix waves across two different source generations: the final c91 P1 was
repaired and independently closed by E2, QC, and QA with P0/P1 `0/0`. No third
provenance reopen is permitted for the final generation.

## Boundaries

No Linux, service, PostgreSQL, cron, Bybit, exchange, order, Decision Lease,
Guardian, Cost Gate, serving, promotion, migration, training, proof, reward,
or runtime action occurred. The historical Linux/service pin remains
`7d1c247947f0fb6c139f8a0583c5e6ed6ae62c70`; it was not refreshed.

This checkpoint is source acceptance only. It does not claim a qualified
candidate, runtime deployment, actual training, OOS result, or profitability.

## Next safe work

Start B2.2c directly: event-driven processing becomes primary, cron is only
reconciliation, cursor/state recovery is restart-safe, the v2 board reaches the
ALR consumer, and no-qualified-candidate cases persist one durable rotate/no-
candidate outcome without manufacturing duplicate no-delta `DEFER` records.
Any later runtime proof requires a fresh exact E3/BB gate.
