# WP4 Durable Fit-Attestation Schema — Source Checkpoint

Date: 2026-07-12
Goal: `GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1`
Work item: `WP4-DURABLE-FIT-ATTESTATION-SCHEMA-SOURCE-TDD`
Source checkpoint: `27bfe34b608b732071205c351dd1aa3fdd7d2283`
Branch: `agent/alr-wp4-contracts`
Base `origin/main`: `b83ddee0d2c1e74db52355fbcce9ff0c49cee44f`
Status: `DONE_SOURCE_ACCEPTED_DURABLE_FIT_ATTESTATION_SCHEMA`

## Accepted source effect

Forward-only V159 source now closes the direct V158 unattested persistence
surface contractually. The migration admits only an externally authenticated,
byte-exact fit receipt, recomputes its durable identities in PostgreSQL, and
keeps the immutable attestation distinct from the atomic completed
run/q10-q50-q90/`NOT_SERVING` registry bundle. Exact replay, divergent reuse,
database-time expiry, structural-versus-durable identity, path binding,
deferred completeness, concurrency, least privilege, and false/zero authority
remain fail-closed.

The source collision scan found maximum V159 with zero duplicate versions. The
frozen V158 migration remains byte-identical at
`b1ff8e2da1878fc498b1bf87e61a105a113bd21b3194a60df84238c8f890d8b9`.
V006's `trading_ai` CI precondition was independently found to be missing,
reproduced as four RED checks, and repaired to four GREEN checks before final
acceptance.

The exact six-file source scope and SHA-256 values are:

- `sql/migrations/V159__alr_durable_fit_attestation.sql`:
  `a4d24a28dbb189f47f15ddca2bb6505100eeb5837a8e8e819801f51207c82c63`
- `program_code/ml_training/tests/integration/alr_durable_fit_attestation_isolated_pg.py`:
  `fd43e331e2c30cdac3971f3688f4f51ef7cb3e6f51227af8c4224dd8c1e4cbc2`
- `program_code/ml_training/tests/integration/alr_durable_fit_attestation_concurrency_isolated_pg.py`:
  `387f398e4ffe144c7fd13b7ddb85ea51105be135da53eabfb1f78b1c23c7600d`
- `tests/migrations/test_v159_alr_durable_fit_attestation.py`:
  `82a85a145e2f781e91a9d35bc57cfa4b7813d5ea3a82bb7425ce569558ac5222`
- `rust/openclaw_engine/tests/schema_contract_test.rs`:
  `3f3e01aecec1396af27e58d3e4a50aeaabc2e84a118a5c32f10ae78175dc028a`
- `.github/workflows/ci.yml`:
  `2ab91a26392e11a87fcbc5b84ca26e00eb65fae29c9fba91a63bd2d727337f66`

## Verification and review

- V159 source/static verification: `232/232` passed.
- V158 plus V159 combined source verification: `269/269` passed.
- Governed Rust schema-harness verification: `7/7` passed.
- Collision scan: `max=159`, duplicate versions `0`.
- V158 frozen-byte check: PASS.
- E2, CC, E3, and MIT final findings: P0/P1/P2 `0/0/0`.
- E4 verdict: `SOURCE_ONLY_PASS` with the dependency-network effect concern
  recorded below.
- Source commit `27bfe34b608b732071205c351dd1aa3fdd7d2283` is published at
  `origin/agent/alr-wp4-contracts`.

The disposable functional and concurrency programs were verified as bounded
source contracts only. They were not run against PostgreSQL in this loop.

## Effect incident and exact boundary

The governed Cargo run used an isolated `HOME` and fetched public dependencies
from crates.io before the `7/7` tests passed. This is a real public dependency
network delta. A subsequent offline retry failed before tests because that
isolated home did not contain the dependency cache. Therefore zero-network and
offline reproducibility are **not proven** by this checkpoint.

Beyond the expected GitHub source fetch/push recorded above, no private
trading/runtime or broker endpoint, PostgreSQL, Linux runtime, or trading
runtime was contacted. No migration or disposable PG probe was executed. No trainer or fit
ran; no model/ONNX/file, durable receipt/attestation/run/artifact/registry row,
symlink, serving/promotion state, order, Guardian/Lease/risk/Cost-Gate mutation,
or trading authority was created. Source generation remained unchanged during
verification.

V159 contractually closes the direct V158 unattested persistence surface, but
it does not establish G3 or G4. There is no externally authenticated real
receipt, applied V159, durable row, production caller, fit, or model-training
fact. G1-G9 are not complete and the Goal remains `ACTIVE`.

## Next safe action

Advance to
`WP4-DURABLE-FIT-ATTESTATION-DISPOSABLE-PG-VERIFICATION-GATE`: under a fresh
governed E3/BB-compatible scope, run the functional and concurrency probes only
against isolated disposable PostgreSQL 16/Timescale databases and prove clean
residue and least privilege. This next gate still grants no runtime, fit,
filesystem, registry-serving, promotion, exchange, or trading authority.
External issuer evidence and a real fit remain a later, separate gate.
