# Operator Brief — IBKR Stock/ETF Strategy Hypothesis Contract

日期：2026-06-30
結論：source-only checkpoint complete；不授權 IBKR contact 或 profitability claim。

## Verdict

`DONE_WITH_CONCERNS_SOURCE_ONLY`

PM 新增 `stock_etf_strategy_hypothesis_contract_v1`，把 future Stock/ETF
strategy hypothesis preregistration 變成 machine-checkable contract。這補的是
Phase 3 evidence clock 前的 source gap：不能只看到 `strategy_hypothesis_hash`，
還要能驗 hypothesis 範圍、turnover、statistical design、bias controls、after-cost
metric 和 no-live/no-margin/no-CFD 邊界。

## What This Adds

- Rust validator: `StockEtfStrategyHypothesisV1`
- Blocked template: `settings/broker/stock_etf_strategy_hypothesis.template.toml`
- Acceptance coverage for default-denied posture, accepted preregistered fixture,
  family/timeframe/scope blockers, design hash blockers, limit/control blockers,
  authority-claim blockers, and template parsing.
- Phase 0 manifest now explicitly lists `stock_etf_strategy_hypothesis_contract_v1`。

## Boundary

No IBKR API contact occurred. No market-data collector, secret read, connector
runtime, paper order, DB migration/apply, scorecard write, evidence-clock start,
profitability claim, GUI lane authority, release approval, tiny-live, or live
authority is granted.

Bybit remains the only active live execution venue. First IBKR contact remains
blocked until real secret/topology evidence and an immutable
`phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
