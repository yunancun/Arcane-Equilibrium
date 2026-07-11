# WP4 V158 Qualified Challenger Schema — Source Checkpoint

Date: 2026-07-11
Goal: `GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1`
Work item: `WP4-V158-QUALIFIED-CHALLENGER-SCHEMA`
Source checkpoint: `beeb77325c83a157c74cf54e79b7146876ed5e27`
Status: `DONE_SOURCE_ACCEPTED_V158_SCHEMA_UNAPPLIED`

## Accepted source effect

The exact E3 R3 and BB pre-authoring gates authorized migration and isolated
test source only. `origin/main` now contains forward-only V158 source with four
append-only isolated relations:

- qualified training receipts;
- completed challenger training runs;
- exact q10/q50/q90 immutable model artifacts;
- a NOT_SERVING challenger registry.

V158 exposes only fixed typed receipt/result persistence and read APIs. It
binds repository receipt lineage, actual data/split/code/config/schema hashes,
server-owned status and timestamps, exact model-set hashes, and all-false/zero
authority fields. Replay is exact and conflict-closed. Deferred constraint
triggers require one run, three distinct quantiles with matching schema and set
hash, and one NOT_SERVING registry row before the result writer returns.
Update/delete, non-origin replication posture, wrong session identity, unsafe
role membership, generic EXECUTE/parameter authority, unexpected ACLs, and
serving/symlink/promotion state fail closed.

The migration creates no role, credential, DSN, sequence, view, serving
pointer, or legacy registry write. V152/V153/V157 remain unmodified.

## Test-source effect

The source checkpoint adds inert functional and concurrency disposable-PG
probes. They require an exact disposable target, explicit password or secure
absolute passfile, frozen target identity, canonical migration bytes, and
bounded fixed fixtures. The functional source names generic EXECUTE and
`session_replication_role` denials plus exact partial-trio `SET CONSTRAINTS`
and schema-mismatch `COMMIT` boundaries. The concurrency source preserves the
production caller's connection limit by using isolated administrator sessions
with test-only session authorization.

The Rust full-tree schema harness now provisions four exact disposable fixture
roles only behind `OPENCLAW_TEST_PG_DESTRUCTIVE=1`; configured connection
failure is fatal. Hosted CI runs the static V158 contract and supplies the
destructive acknowledgement only to the existing ephemeral schema job.

## Verification

- Focused V158 static/adversarial suite: `37 passed`.
- Adjacent local migration suite: `44 passed`.
- Full `program_code/ml_training/tests`: `1850 passed, 36 skipped in 13.78s`.
- Rust schema-contract target: compile-only PASS with PG environment removed.
- Python compile, embedded fixture validation, canonical hash validation, both
  probe `--help` paths, file-scoped rustfmt, workflow YAML, and diff checks:
  PASS.
- Three independent final reviews: P0/P1/P2 `0/0/0`.

Frozen SHA-256 values:

- V158 SQL: `b1ff8e2da1878fc498b1bf87e61a105a113bd21b3194a60df84238c8f890d8b9`
- static contract: `b780046a50d89e5b3ca9c8fd712313dce80980b7960c3605531e38dec1149c02`
- functional probe: `ea5ac5005feefe6d63fc394628a8dbed84ab0d6a5eb94aaefa4c4c9e2f3db07a`
- concurrency probe: `816242f9b8b6636b53add499cc4e392ea9b9522f783e00d454f100bb06840afb`
- Rust harness: `ac9dbbbed1273a49fb9551138ecaffa3b718e46e7483bdf3751f45f503f35695`
- CI workflow: `63c86e9113570623828251ee65637b44841a05bce167f3da51b65d60bf9d8c19`

## Deliberate unexecuted boundary

Both disposable-PG probes remain **unexecuted**. This checkpoint did not apply
V158, contact PostgreSQL, refresh `_sqlx_migrations`, inspect or deploy Linux,
touch runtime services, or contact Bybit/any exchange. Production PG and
runtime state are `UNVERIFIED_NOT_REFRESHED`.

Source publication created no durable receipt, training-run, artifact, or
registry rows; no fit or model bytes; no symlink, `_latest`, serving, or
promotion state; and no order, lease, Guardian, RiskConfig, Cost Gate, trading,
or exchange authority. G3 and G4 therefore remain failed at runtime.

## Next safe action

The Goal remains `ACTIVE`. Implement only the durable-receipt repository tracer
against V158's fixed receipt API with fake-connection TDD. It must validate the
existing receipt-only admission contract and keep exact replay fail closed.
Trainer, fit, filesystem publication, and fixed result/registry APIs remain
outside this cycle. Source TDD grants no migration apply, PG, Linux, runtime,
registry-write, serving, or exchange authority.
