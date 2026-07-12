# WP4 Durable Fit-Attestation — Disposable PostgreSQL Verification Gate

Date: 2026-07-12
Goal: `GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1`
Work item: `WP4-DURABLE-FIT-ATTESTATION-DISPOSABLE-PG-VERIFICATION-GATE`
Verified source head: `74d8475e32ff89b67e2b6a1346e0839bbcfa646f`
Branch: `agent/alr-wp4-contracts`
Observed `origin/main`: `2dd5d1f1c88fa2eac10289442884214f18bee596`
Hosted run/job: `29195892105` / `86658665742`
Status: `DONE_DISPOSABLE_PG_VERIFIED`

## Machine verdict

The PR-only GitHub Actions run completed `success` at the exact verified head.
All seven jobs passed. The authoritative schema job used
`timescale/timescaledb:2.26.1-pg16`, created distinct functional and
concurrency databases from separate V157 baselines, applied V158/V159 only in
those disposable databases, exercised both probes, force-dropped both
databases, passed the Rust schema consumer, executed `audit_migrations.py` as
informational-only/non-gating, and stopped the container.

Functional probe `alr_v159_disposable_pg_probe_v1` returned `PASS` with exact
double-apply, byte/hash/readback, malformed-receipt, ACL, replay, expiry,
rollback, atomic bundle, and false/zero-authority markers. Its transient fixture
counts were receipts/attestations/runs/artifacts/registry `4/3/1/3/1`.
`signature_fixture_only=true`, `external_authenticity_proven=false`, and
`model_fit_performed_by_probe=false` remained explicit.

Concurrency probe `alr_v159_concurrency_disposable_pg_probe_v1` returned
`PASS` with `postgresql_executed=true`, real blocked advisory-lock observation,
thread-local sessions, read-committed UTC sessions, identical/divergent replay,
all six structural collisions, same/cross/exact artifact collisions,
uncommitted invisibility, rollback, deferred partial-bundle rejection, and all
three wait-past-expiry paths. Its transient fixture counts were
receipts/attestations/runs/artifacts/registry `3/3/2/6/2`.

Workflow cleanup steps 10 and 12 force-dropped the two isolated databases and
the final container teardown passed. Therefore transient disposable writes
occurred as intended, surviving rows after cleanup are `0`, and production or
TradeBot-runtime rows written by this gate are `0`.

## Exact source and verification identity

- V158 SHA-256:
  `7ed70599c6bd5f3cdb3376bc135a952d8c18f4ad62a62432c2bfdd8ee84e446b`
- V159 SHA-256:
  `2e11d0ae0cbc2c1161a47d04bed4054c31b728e8cf945f931197f9b3455b7d74`
- Functional probe:
  `d29d4b817370a5797f95590d7d5e06573de8bd99da9901dce71ecb06d878a8f4`
- Concurrency probe:
  `5965ae7e65689705d1c91744058a3e9bbf81697f4af42394462a4257659c9795`
- Static contract:
  `f6ffc199f4708d3099d018571dca691f02cf1ba786adda8dfac61073d133b64a`
- Rust harness:
  `3f3e01aecec1396af27e58d3e4a50aeaabc2e84a118a5c32f10ae78175dc028a`
- CI workflow:
  `2ab91a26392e11a87fcbc5b84ca26e00eb65fae29c9fba91a63bd2d727337f66`
- Migration scan: `141` eligible versioned migrations, maximum V159, duplicate
  versions `0`.
- Local final source checks: V159 `323`, combined V158/V159 `362`,
  development-agent governance `230`, governance validate/render `PASS`.
- Independent final changed-scope reviews: P0/P1/P2 `0/0/0`.

## Retry and RCA ledger

The green run was attempt 12 after `same_scope_retries=11`. Each prior run
failed closed and retained successful cleanup where applicable:

1. `29188590473`: governance/V158 parse preconditions.
2. `29189139357`: chained `IS` SQL syntax.
3. `29189547269`: text/character concatenation typing.
4. `29189906560`: eager reference to an absent forward regprocedure.
5. `29190357749`: invalid JSON subject construction.
6. `29190748041`: legacy parameter naming.
7. `29192224851`: invalid `GROUP BY TRUE` usage.
8. `29192626663`: PostgreSQL ARE bound exceeded 255.
9. `29194346333`: bind-time oracle queried nonexistent training-run columns.
10. `29194800637`: nonfinite timestamp expected an unreachable downstream
    constraint instead of the exact pre-insert writer rejection.
11. `29195301806`: the long-lived observer transaction reused a stale
    `pg_stat_activity` snapshot and reached its exact lock timeout.

The final repair clears the observer's transaction-cached statistics snapshot
before every `pg_stat_activity` sample. AST and mutation contracts pin that
placement and reject a `SELECT TRUE` bypass. No timeout, migration, TTL,
authority, or runtime behavior was widened.

## G1-G9 adjudication and effect boundary

- G1: `PARTIAL`; disposable schema behavior is verified, but current
  candidate/fill/cost/risk acquisition evidence is still absent.
- G2: `PARTIAL_DISPOSABLE_PG_VERIFIED`; source plus isolated PG behavior is
  proven, but production/runtime candidate qualification is not.
- G3: `FAIL_DISPOSABLE_PG_VERIFIED_NO_REAL_RECEIPT_OR_OUTCOME_CHAIN`.
- G4: `FAIL_DISPOSABLE_PG_VERIFIED_EXECUTION_NOT_ESTABLISHED`.
- G5/G6/G7: `FAIL`.
- G8/G9: `PARTIAL_WP1_PASS`.

The hosted fixtures are synthetic and cannot establish an externally
authenticated real receipt, real runner use, real fit, model training, model
bytes, qualified reward, or production durable lineage. V159 was applied only
inside disposable CI databases; production/runtime V159 remains unapplied and
unrefreshed. No Linux `trade-core`, private runtime, broker, exchange, trainer,
fit, model/file, serving, promotion, symlink, order, risk, Guardian, Decision
Lease, Cost Gate, or trading authority effect occurred. All authority remains
false and all counters remain zero. The Goal and WP4 remain `ACTIVE`.

## Next safe action

Advance to
`WP4-TRUSTED-ISSUER-ISOLATED-RUNNER-HANDSHAKE-DESIGN-PREAUTHORING-GATE`.
This is a pure request/receipt design gate only: define identities, freshness,
failure states, and no-authority handoff without consuming raw receipt bytes,
opening PostgreSQL/files/network, running a trainer or fit, creating model
artifacts, applying V159 to runtime, or granting serving/promotion/trading
authority. Source authoring or any external execution requires a later fresh
gate.
