# WP4 Schema-Required Challenger Training Contract — Source Checkpoint

Date: 2026-07-11
Goal: `GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1`
Work item: `WP4-QUALIFIED-CHALLENGER-TRAINING-CONTRACT`
Source checkpoint: `f36379b9ddf10ee1055daeda27805c409c6ee8bd`
Status: `DONE_SOURCE_ACCEPTED_SCHEMA_REQUIRED_TRAINING_CONTRACT`

## Accepted effect

WP4 now has a typed, deterministic source contract between the accepted WP3
repository receipt and a future isolated challenger trainer. The public builder
accepts only `candidate_proof_repository_receipt_v1`; it has no raw candidate,
ProofPacket, RewardLedger, or PIT-manifest argument. It revalidates the exact
receipt self-hash, adapter self-hash, selection binding, projection/repository
parity, canonical proof/reward hashes, raw source containers, embedded PIT
manifest, candidate scope, and after-cost Demo reward semantics.

The contract independently recomputes `proof_input_hash`, rejects split
binding/projection identities, and binds projection, decision, handoff,
source-set, proof, reward, PIT, dataset, row-set, train/validation/test split,
feature, label, leakage, and after-cost label-set hashes into deterministic
`training_input_hash`, `evidence_set_hash`, and `training_key_hash` values.

Code identity is explicit: the source head, dependency lock, and the current
`pit_dataset_manifest.py`, `quantile_trainer.py`,
`run_training_pipeline.py`, and `model_registry.py` seams each require a
64-hex content hash. The effective LightGBM quantile configuration materializes
every current `QuantileTrainingConfig` field. A bounded local resource contract
requires positive wall/CPU/memory/artifact/row limits and exactly zero external
requests and paid API budget.

## Deliberate non-executable state

Every valid contract is `SCHEMA_REQUIRED` with reason
`durable_receipt_schema_required`. It states:

- `training_allowed=false`
- `model_training_performed=false`
- `registry_write_allowed=false`
- `runtime_or_exchange_attested=false`
- all authority counters zero

The execution contract requires the future durable path to rehash actual data,
code, source head, effective configuration, and exact split membership; observe
a real fit and model bytes; write only to an immutable isolated challenger
directory/registry; and keep symlink, legacy `run_training_pipeline`, legacy
`learning.model_registry`, serving, and promotion paths disabled.

This checkpoint therefore does not claim G4. It makes false G4 claims harder
and specifies the exact admission identity that a forward repository/trainer
must later persist and consume.

## Migration collision adjudication

At clean source head and local `origin/main`
`f36379b9ddf10ee1055daeda27805c409c6ee8bd`:

- `sql/migrations` contains `139` eligible migrations, maximum `V157`, with
  zero duplicate versions.
- No `V158` migration or active V158 reservation exists in the current source,
  registered worktrees, or current local/remote-tracking refs.
- The checksum lock still ends at V150; that is source-lock evidence only and
  does not refresh PostgreSQL runtime state.
- V157 remains the narrow PIT-lineage addition to the legacy serving registry
  and cannot be widened or reused for ALR challenger semantics.

`V158` is therefore the observed next collision-free candidate, not a reserved,
created, approved, or applied migration. Reservation/creation/apply remains a
fresh exact `E3 -> BB -> PM` gate.

## TDD and adversarial verification

- Initial red: `ModuleNotFoundError: ml_training.alr_challenger_training_contract`.
- Final focused contract/mutation suite: `32 passed`.
- Adjacent proof/reward/PIT/trainer/pipeline/registry suite:
  `213 passed, 3 skipped`.
- Exact-head full `program_code/ml_training/tests`:
  `1850 passed, 36 skipped in 14.64s`.
- Python compile: PASS.
- Cached diff check: PASS.
- Independent QA final: PASS, P0/P1/P2 `0/0/0`.
- Independent E2 final: PASS, P0/P1/P2 `0/0/0`.

The first adversarial round found and closed forged `proof_input_hash`, split
binding/projection identity, hash-only semantic-validator, NaN totality, and
Boolean/integer alias defects. Final mutations prove those surfaces fail
closed, including nested authority/counter maps.

## Boundary and effect accounting

- Migration files reserved/created/applied: `0/0/0`.
- Database rows/payload bytes written: `0/0`.
- Model fits/artifact bytes/registry rows: `0/0/0`.
- `model_training_performed=true` claims: `0`.
- Symlink/latest/serving/promotion actions: `0/0/0/0`.
- Linux/service/PostgreSQL runtime/Bybit contact: none.
- Exchange/order/probe/Decision Lease/Cost Gate actions: `0/0/0/0/0`.

## Next action

The Goal remains `ACTIVE`. Prepare a current exact E3/BB gate for the
provisional forward schema reservation/creation and the isolated no-symlink
trainer/repository design. Do not reserve, create, or apply V158 before that
gate. After source schema acceptance, implement actual row/split/code/config
rehashing and real-fit truth before any durable
`model_training_performed=true` or challenger-registry row is possible.
