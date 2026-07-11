# WP3 Read-Only Proof/Reward Repository Adapter — Source Checkpoint

Date: 2026-07-11
Goal: `GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1`
Work item: `WP3-PROOF-REWARD-REPOSITORY-ADAPTERS`
Source checkpoint: `c2bdefbfdb52eeaab4e801de783719ecfe0da7bc`
Status: `DONE_SOURCE_ACCEPTED_READ_ONLY_REPOSITORY_ADAPTER`

## Accepted effect

WP3 now has a repository-owned seam rather than a caller-owned projection and
binding. `candidate_proof_repository.py` discovers the newest candidate
projection family, requires exact v2 semantics, reconstructs complete
`training_input` lineage from immutable `learning.alr_*` rows, derives the
selection/proof binding internally, and validates existing V153
`alr_outcome_bridge_artifact_v1` proof/reward bytes through the accepted pure
adapter.

Before a semantic receipt is returned, one final PostgreSQL statement rechecks
the current projection head, all bounded lineage identities, and the bounded
matching bridge set in the same database snapshot. Lineage is capped at
`64+1`; bridge discovery is capped at caller `limit+1`. Overflow produces an
explicit schema-required state and no receipt. Source-key drift is rejected,
exact reward array order is retained, and a separately labelled canonical copy
feeds permutation-stable adaptation.

Both the full operational cycle and candidate-board-only reconciliation invoke
the seam immediately after candidate projection. The result is an in-memory
hash-bound receipt only: `receipt_persisted=false`,
`runtime_or_exchange_attested=false`, and nested durability remains
`unverified_source_only`.

## Schema adjudication

Independent CC/FA review chose `READ_ONLY_SCHEMA_REQUIRED`. V153
`outcome_bridge` and `candidate_outcome_bridge` are frozen V152-run-bound
feedback semantics. PostgreSQL would syntactically accept a generic node/edge
reuse, but that would silently widen their domain contract. WP3 therefore
issues SELECTs only and leaves a dedicated durable projection-receipt kind,
edge, or table to WP4 after a fresh collision scan and exact migration gate.

V152/V153 bytes were not changed. No migration was reserved, created, or
applied.

## Verification

- TDD repository red: missing `ml_training.candidate_proof_repository`.
- TDD event red: missing `process_candidate_proof_repository_backlog`.
- Final focused repository/event/full-chain: `66 passed, 1 skipped`.
- Final `program_code/ml_training/tests`: `1818 passed, 36 skipped in 11.92s`.
- Python compile: PASS.
- `git diff --check`: PASS.
- Independent E2: PASS, P0/P1/P2 `0/0/0`.
- Independent QA: PASS, P0/P1/P2 `0/0/0`.
- Independent CC/FA effect review: PASS, P0/P1/P2 `0/0/0`.

Adversarial coverage includes newer unknown candidate schemas, concurrent
rotation/lineage/bridge appends, missing/extra/ambiguous lineage, exact source
key drift, wrong-schema/tampered/authority-injected bridge containers,
no-fill, invalid projection binding, reward permutations and duplicate
containers, mapping/tuple cursor parity, max-plus-one overflow, zero SQL
writes, and strict consumer receipt/authority/batch metrics.

## Boundary and effect accounting

- Repository rows written: `0`.
- Repository payload bytes written: `0`.
- Proof/reward facts created: `0/0`.
- Training/model/registry/serving/promotion facts created: `0/0/0/0/0`.
- Exchange/order/probe/Decision Lease/Cost Gate actions: `0/0/0/0/0`.
- Linux, service, PostgreSQL runtime, or Bybit contact: none.

This is source acceptance, not G3 runtime completion. Actual ProofPacket,
RewardLedger, matched fills, PIT after-cost labels, training, OOS, registry,
serving, and profit evidence remain zero or unrefreshed.

## Next action

The Goal remains `ACTIVE`. WP4 is now active. Run a fresh source migration
collision scan, identify the next legal version after current source, and
specify typed durable receipt/training/registry contracts. Do not reserve,
create, or apply a migration until exact `E3 -> BB` review is current. Do not
reopen WP3 unless a material P0/P1 or schema collision appears.
