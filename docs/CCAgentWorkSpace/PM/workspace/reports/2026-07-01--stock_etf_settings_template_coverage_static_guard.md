# 2026-07-01 — Stock/ETF Settings Template Coverage Static Guard

## Scope

PM added a source-only meta guard for IBKR/Stock-ETF settings/template coverage.

This is not a settings mutation, not runtime enablement, not IBKR contact, not secret access, not a
connector runtime, not a paper order route, and not a Bybit behavior change. The guard freezes the
coverage lesson from the read-only probe request template gap: every source-controlled
IBKR/Stock-ETF TOML under `settings/asset_lanes`, `settings/broker`, and
`settings/risk_control_rules` must be directly referenced by an acceptance or structure test.

## Guard Added

- `tests/structure/test_stock_etf_settings_template_coverage_static.py`

The guard:

- dynamically scans settings files whose names contain `ibkr`, `stock_etf`, or the legacy
  `stock_market_data` alias;
- asserts the scan includes the non-prefixed `stock_market_data_provenance.template.toml` naming
  exception;
- asserts the scan does not pull unrelated Bybit runtime risk configs such as `risk_config_demo`,
  `risk_config_live`, or `risk_config_paper`;
- fails if any matching settings file is not directly referenced by Rust acceptance tests,
  structure tests, or Stock/ETF control-api tests.

## Verification

- New structure guard py_compile: PASS.
- Focused structure guard pytest: `3 passed`.
- Docs PM trace tests: PASS.
- Diff check: PASS.

## Boundary

No settings values changed, no IBKR SDK import, no socket/HTTP, no secret read or creation, no
connector runtime, no read-only probe, no result import, no evidence or scorecard writer, no
evidence-clock runtime, no DB apply, no paper order route, no tiny-live/live authorization, and no
Bybit live/demo execution change.
