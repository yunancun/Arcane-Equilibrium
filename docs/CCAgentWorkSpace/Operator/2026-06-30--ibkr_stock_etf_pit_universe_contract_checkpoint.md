# Operator Brief — IBKR Stock/ETF PIT Universe Contract

日期：2026-06-30
結論：source-only checkpoint complete；不授權 IBKR contact。

## Verdict

`DONE_WITH_CONCERNS_SOURCE_ONLY`

PM 新增 `stock_etf_pit_universe_contract_v1`，把 future Stock/ETF point-in-time
universe membership 變成 machine-checkable contract。這補的是 Phase 3 evidence
clock 前的 source gap：不能只看到 `universe_hash`，還要能驗成分、PIT as-of、
screen policy、survivorship controls。

## What This Adds

- Rust validator: `StockEtfPitUniverseV1`
- Blocked template: `settings/broker/stock_etf_pit_universe.template.toml`
- Acceptance coverage for default-denied posture, accepted PIT fixture,
  constituent blockers, rule/screen hash blockers, survivorship/freeze blockers,
  contact/secret blockers, and template parsing.
- Phase 0 manifest now explicitly lists `stock_etf_pit_universe_contract_v1`。

## Boundary

No IBKR API contact occurred. No market-data collector, contract-details call,
secret read, connector runtime, paper order, DB migration/apply, scorecard write,
evidence-clock start, GUI lane authority, release approval, tiny-live, or live
authority is granted.

Bybit remains the only active live execution venue. First IBKR contact remains
blocked until real secret/topology evidence and an immutable
`phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
