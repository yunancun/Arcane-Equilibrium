# PM Checkpoint - IBKR Stock/ETF Scorecard Verdict Contract

日期：2026-06-30
角色：PM(default)
範圍：ADR-0048 / AMD-2026-06-29-01 Phase 3 scorecard verdict source contract

## Verdict

`DONE_WITH_CONCERNS_NO_RUNTIME_AUTHORITY`

This checkpoint adds the missing source-only contract between scorecard inputs
and the future `tiny_live_adr_eligibility_v1` discussion gate. It defines the
machine-checkable scorecard verdict artifact for CI/PSR/DSR-style statistical
thresholds, paper-vs-shadow divergence, after-cost lower confidence bounds, and
quality labels without granting any execution authority.

## Changed

- Added `stock_etf_scorecard_verdict_v1` as an exported Rust source contract:
  `StockEtfScorecardVerdictV1`.
- Added verdict labels:
  `engineering_ready`, `research_promising`, `profitability_feasible`,
  `insufficient_evidence`, `execution_model_invalid`, and `kill`.
- Positive verdicts require pre-registered sample/window thresholds,
  paper-vs-shadow divergence limits, PSR/DSR-style thresholds, positive
  benchmark/cost-stress lower confidence bounds where applicable, quality
  labels, and QC/MIT/QA review hashes.
- Negative verdicts can be formally sealed without positive profitability,
  avoiding a scorecard system that only accepts profitable-looking outcomes.
- The contract rejects IBKR contact, connector runtime, broker fill import,
  scorecard writer side effects, DB apply, evidence-clock start, serialized
  secrets, tiny-live/live authority, and Bybit-live regression.
- Added the default-blocked template
  `settings/broker/stock_etf_scorecard_verdict.template.toml`.
- Updated the main development arrangement, Phase 0 packet spec note, settings
  README, PM memory, and Operator brief.

## Boundary

No IBKR contact, no IBKR process startup, no secret read/create/serialization,
no connector runtime, no broker fill import, no scorecard writer, no DB apply,
no evidence clock, no GUI lane authority, no paper order, no tiny-live, no live,
and no Bybit live execution behavior change.

This is a source-only contract checkpoint. The Linux `trade-core` runtime was
not synced, restarted, or fast-forwarded.

## Dispatch Note

PA/E1/E2/E4/QA subagents were not spawned because this Codex desktop session
does not expose a subagent execution tool. PM performed the narrow
source-contract implementation, local review, and focused regression directly.

## Verification

Focused verification:

```bash
rustfmt --check rust/openclaw_types/src/stock_etf_scorecard_verdict.rs rust/openclaw_types/tests/stock_etf_scorecard_verdict_acceptance.rs
cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_scorecard_verdict_acceptance
cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_scorecard_inputs_acceptance
cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_tiny_live_eligibility_acceptance
cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_phase0_manifest_acceptance
git diff --check
```

Result: `8 + 12 + 7 + 6` focused acceptance tests passed, and diff check passed.

Full package:

```bash
cargo test --manifest-path rust/Cargo.toml -p openclaw_types
```

Result: `35` unit/golden + `206` integration/acceptance + `0` doc-tests passed.
