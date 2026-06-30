# 2026-06-30 IBKR Stock/ETF Storage Capacity Guard Checkpoint

VERDICT: PASS
CONFIDENCE: high

## Result

- Hardened `stock_etf_storage_capacity_v1` source validation so Phase 3 evidence cannot start from an unbounded or unsafe storage plan.
- Added machine-checkable limits for the initial paper/shadow evidence plan: max `1,000` instruments, max `5,000,000` rows/day, max `8,192` MB index budget, and max `5,000` ms query SLO.
- Added retention-order checks: raw payload hashes must be retained at least `365` days, compressed retention must not be shorter than raw-hash retention, and compressed retention above `3,650` days requires a future reviewed source version.
- Added lane-scoped archive-path validation requiring a relative `evidence/stock_etf_cash/...` path with no absolute path, parent traversal, double slash, or cross-lane archive target.
- Updated the Phase 0 named contract packet so the written `stock_etf_storage_capacity_v1` spec matches the validator.

## Boundary

- This is a source-only Phase 0/1 contract hardening checkpoint.
- No IBKR contact, healthcheck, socket, connector construction/runtime, secret read/create/serialization, evidence clock runtime, scorecard writer, DB migration apply, PG write, paper order, fill import, GUI authority, lane selector authority, release, tiny-live, or live authority was added or exercised.
- No Bybit live execution behavior was changed.
- Linux `trade-core` runtime checkout was not touched or fast-forwarded.

## Verification

- `rustfmt --edition 2021 rust/openclaw_types/src/stock_etf_scorecard_inputs.rs rust/openclaw_types/tests/stock_etf_scorecard_inputs_acceptance.rs`
  - passed
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_scorecard_inputs_acceptance`
  - `12 passed`
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_phase0_manifest_acceptance`
  - `6 passed`
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_phase3_evidence_acceptance`
  - `13 passed`
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`
  - `35` unit/golden tests + `181` integration/acceptance tests + `0` doc-tests passed
- `git diff --check`
  - passed

## Dispatch Note

Sub-agent E2 was not spawned because the available sub-agent tool policy allows spawning only when the user explicitly asks for sub-agents or parallel agent work. This checkpoint is narrow and source-only; full `openclaw_types` verification covers the shared contract surface.

## Next Gate

Continue source-only contract hardening or Phase 4 display-only views. Do not proceed to Phase 2 IBKR read-only contact, Phase 3 collector/evidence-clock runtime, DB apply, connector runtime, or paper-order authority until the required immutable gates and real secret/topology evidence exist.
