# 2026-06-30 IBKR Stock/ETF Storage Capacity Guard Checkpoint

VERDICT: PASS
CONFIDENCE: high

## Result

- `stock_etf_storage_capacity_v1` now rejects unbounded initial evidence plans before Phase 3 can start.
- Guarded limits are max `1,000` instruments, max `5,000,000` rows/day, max `8,192` MB index budget, max `5,000` ms query SLO, raw payload hash retention at least `365` days, compressed retention between raw-hash retention and `3,650` days, and lane-scoped relative archive paths under `evidence/stock_etf_cash/`.
- Acceptance tests now cover excessive volume, slow query SLO, retention-order violations, and unsafe archive paths.
- The Phase 0 named contract packet was updated to match the source validator.

## Boundary

- Source-only contract/test/spec hardening.
- No IBKR contact, connector runtime, secret access, evidence clock runtime, scorecard writer, DB apply, PG write, paper order, fill import, GUI/lane selector authority, release, tiny-live, or live authority was added or exercised.
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

Sub-agent E2 was not spawned because the available sub-agent tool policy allows spawning only when the user explicitly asks for sub-agents or parallel agent work. Full `openclaw_types` verification covered this shared contract change.

## Next Gate

Keep IBKR Stock/ETF in source-only/pre-contact mode. Do not start IBKR read-only contact, Phase 3 collector/evidence clock, connector runtime, scorecard writing, DB apply, or paper order authority until the required immutable gates and real secret/topology evidence exist.
