# PM Checkpoint — IBKR Stock/ETF Strategy Hypothesis Contract

日期：2026-06-30
角色：PM(default)
範圍：ADR-0048 / AMD-2026-06-29-01 strategy hypothesis preregistration source contract

## Verdict

`DONE_WITH_CONCERNS_SOURCE_ONLY`

本 checkpoint 新增 `stock_etf_strategy_hypothesis_contract_v1` Rust source
validator 與 blocked broker template，補齊 Phase 3 evidence clock 前只驗
`strategy_hypothesis_hash`、但未驗 hypothesis preregistration / low-medium
turnover scope / statistical design / bias controls 的 source gate 缺口。

## What Changed

- 新增 `openclaw_types::stock_etf_strategy_hypothesis::StockEtfStrategyHypothesisV1`。
- 新增 blocked template：`settings/broker/stock_etf_strategy_hypothesis.template.toml`。
- 新增 acceptance tests：`stock_etf_strategy_hypothesis_acceptance`。
- 將 `stock_etf_strategy_hypothesis_contract_v1` 加入 Phase 0 manifest JSON 與 manifest validator。
- 將 broker capability registry 的 shadow signal / scorecard gates 綁到 strategy hypothesis contract。
- 更新 ADR-0048、Phase 0 packet、SPEC register、document/initiative indexes。

## Contract Requirements

Validator accepts only source-backed `stock_etf_cash` / IBKR strategy hypotheses with:

- hypothesis id and version
- allowed v1 strategy family: daily/weekly momentum, sector rotation, or ETF trend/risk-off
- daily or weekly v1 timeframe
- instrument scope
- PIT universe, universe, benchmark, cost model, entry, exit, risk, feature,
  data-source-policy, statistical-design, and preregistration hashes
- minimum holding period and bounded monthly turnover
- max constituents and independent-observation target
- lookahead, survivorship, and multiple-testing controls
- benchmark-relative and after-cost metrics
- explicit no options / CFD / margin / short policy
- paper/shadow-only posture
- Bybit live execution unchanged
- IBKR live denied

Validator rejects:

- high-frequency or event-driven reserved families
- intraday v1 timeframe
- missing design/preregistration hashes
- missing bias or multiple-testing controls
- missing benchmark-relative after-cost metrics
- missing forbidden-instrument policy
- over-high turnover
- premature profitability claims
- live/tiny-live authority claims
- prior IBKR contact
- serialized secret content

## Dispatch Note

Repo workflow would normally separate PA/E1/E2/E4/QA for implementation work.
This desktop turn did not spawn subagents because the available multi-agent tool
requires explicit operator authorization for delegation. PM kept the scope narrow
and source-only, then used focused Rust acceptance tests plus crate-level
regression as the verification surface.

## Verification

Executed:

```bash
rustfmt rust/openclaw_types/src/stock_etf_strategy_hypothesis.rs rust/openclaw_types/tests/stock_etf_strategy_hypothesis_acceptance.rs rust/openclaw_types/src/lib.rs rust/openclaw_types/src/stock_etf_phase0_manifest.rs rust/openclaw_types/src/stock_etf_broker_capability_registry.rs
cargo test -p openclaw_types --test stock_etf_strategy_hypothesis_acceptance --test stock_etf_phase0_manifest_acceptance --test stock_etf_broker_capability_registry_acceptance
cargo test -p openclaw_types
rustfmt --check rust/openclaw_types/src/stock_etf_strategy_hypothesis.rs rust/openclaw_types/tests/stock_etf_strategy_hypothesis_acceptance.rs rust/openclaw_types/src/stock_etf_phase0_manifest.rs rust/openclaw_types/src/stock_etf_broker_capability_registry.rs
git diff --check
```

Result:

- strategy hypothesis acceptance: 6 passed
- Phase 0 manifest acceptance: 6 passed
- broker capability registry acceptance: 8 passed
- full `openclaw_types` regression: 35 unit/golden + 149 integration/acceptance passed
- focused `rustfmt --check`: passed
- `git diff --check`: passed

## Non-Authority Statement

This checkpoint grants no IBKR API contact, no contract-details call, no market
data collection, no secret access, no connector runtime, no paper order, no DB
migration/apply, no scorecard write, no evidence-clock start, no profitability
claim, no GUI lane authority, no release approval, no tiny-live, and no live
authority.

First IBKR contact remains blocked until real secret/topology evidence and an
immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
