# WP4 Qualified Receipt Repository Writer — Source Checkpoint

Date: 2026-07-11
Goal: `GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1`
Work item: `WP4-QUALIFIED-RECEIPT-REPOSITORY-TDD`
Source checkpoint: `c0aec6813b59f3c17b1fb93350794a3581ccd5ae`
Status: `DONE_SOURCE_ACCEPTED_QUALIFIED_RECEIPT_REPOSITORY_TRACER`

## Accepted source effect

The new `alr_challenger_repository.py` exposes one narrow public operation:
persist an already validated `alr_challenger_training_contract_v1` through
V158's fixed qualified-receipt writer. It snapshots the input before
validation, derives the domain-separated reward-set hash and exact 30-field
durable-receipt payload, and supplies exactly 15 TEXT arguments plus canonical
JSONB to `learning.persist_alr_qualified_training_receipt_v1`.

The repository accepts only exact PERSISTED or DUPLICATE responses with the
complete 20-field server row, typed canonical-payload parity, original
offset-aware `created_at`, and exact no-authority maps. It requires
`autocommit is False` and psycopg2 transaction status IDLE before opening a
cursor, so it cannot commit or roll back unrelated pending work. It calls no
table DML, role emulation, reader, result, registry, trainer, fit, filesystem,
serving, or external path.

Frozen SHA-256 values:

- repository module: `92d8d692f07a8a573c1d2ce968919458d5e54ec10e2f4bd598a2fcb553e71b92`
- repository tests: `9344b2d4cc08c8cdf708a3bdb82d9b37bdc003b4add8f4778e9919fc6f7e863d`

## Verification

- First RED: missing `ml_training.alr_challenger_repository` at collection.
- Focused repository suite: `31 passed`.
- Adjacent repository/training-contract/V158 suite: `121 passed`.
- Full ML with broken local LightGBM treated as its normal unavailable
  optional dependency: `1920 passed, 28 skipped in 15.10s`; the identical
  environment baseline without the new test file was `1889 passed, 28
  skipped`, an exact `+31` delta.
- Native full attempt exposed only the existing missing `libomp.dylib` for the
  installed optional LightGBM package; no tracer failure was present.
- Python compile, exact SQL pin, hash goldens, forbidden-path scan, and diff
  checks: PASS.
- Two exact-byte final reviews: P0/P1/P2 `0/0/0`.

## Deliberate unexecuted boundary

This was fake-connection source TDD only. V158 was not applied or exercised;
PostgreSQL and `_sqlx_migrations` were not contacted. Source publication
created no durable receipt/run/artifact/registry row, proof/reward fact, fit,
model byte, file, symlink, serving/promotion state, Linux/runtime change,
exchange action, order, lease, Cost Gate change, or authority. G3 and G4 remain
failed at runtime.

## Next safe action

The Goal remains `ACTIVE`. Add only fake-connection `FOUND/NOT_FOUND` behavior
for `learning.read_alr_qualified_training_receipt_v1`, with exact identity and
full-row validation plus the same clean-connection ownership contract. Result
writer/reader, trainer, fit, ONNX/filesystem publication, registry, V158 apply,
PG/Linux/runtime, serving, and exchange work remain outside that cycle.
