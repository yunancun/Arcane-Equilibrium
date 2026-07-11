# WP3 Proof/Reward Validation Adapter — Source Checkpoint

Date: 2026-07-11
Goal: `GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1`
Work item: `WP3-PROOF-REWARD-VALIDATION-ADAPTER`
Source checkpoint: `8999aa2b7e4a3bba3841f4c72cf054d88cb69c5c`
Status: `DONE_SOURCE_ACCEPTED_VALIDATION_ADAPTER`

## Accepted effect

`candidate_proof_adapter_v1` is a pure, no-contact summary boundary. It uses
the existing public B2.2c projection-plan validator and requires an immutable
handoff. It derives candidate/context identity from the selected WP2 identity
and context hashes, then validates caller-provided ProofPacket/RewardLedger
artifacts against the exact projection artifact, decision, handoff, PIT scope,
and decision-time causality.

It creates no proof packet, reward record, fill, broker receipt, repository
record, training run, service state, or authority. Durable receipt state is
explicitly `unverified_source_only`. Valid no-fill remains non-reward; invalid
or missing artifacts fail closed. Equivalent valid reward-record permutations
produce one canonical proof-input and adapter hash.

## Verification

- Focused: `10 passed in 0.08s`.
- Final current-generation integration: `263 passed in 1.08s`.
- E2: PASS after repairing caller-substitutable candidate/context binding.
- QC: PASS after requiring B2.2c handoff and canonical reward-set ordering.
- QA: `PASS_SOURCE_CHECKPOINT_TO_PM`; final P0/P1 `0/0`.
- `git diff --check`: PASS.

## Scope and boundary

Production/test delta: `1/1` files, `+546/+313` lines, one new module. The
module deliberately reuses existing ProofPacket, RewardLedger, PIT, and
projection-plan contracts rather than adding a migration, DB path, raw
execution parser, or runtime consumer.

No Linux, PostgreSQL, cron, service, Bybit, exchange, order, Decision Lease,
Guardian, Cost Gate, training, serving, promotion, or external credential
action occurred.

## Next action

Remain `ACTIVE`. Advance only to
`WP3-PROOF-REWARD-REPOSITORY-ADAPTERS`; B2.2c runtime proof and all real
receipt acquisition remain a fresh exact `E3 -> BB -> Operator` gate.
