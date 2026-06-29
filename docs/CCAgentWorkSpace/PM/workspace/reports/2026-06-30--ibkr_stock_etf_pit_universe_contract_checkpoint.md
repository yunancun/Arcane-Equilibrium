# PM Checkpoint — IBKR Stock/ETF PIT Universe Contract

日期：2026-06-30
角色：PM(default)
範圍：ADR-0048 / AMD-2026-06-29-01 point-in-time universe source contract

## Verdict

`DONE_WITH_CONCERNS_SOURCE_ONLY`

本 checkpoint 新增 `stock_etf_pit_universe_contract_v1` Rust source validator
與 blocked broker template，補齊 Phase 3 evidence clock 前只驗
`universe_hash`、但未驗 universe membership / PIT as-of / constituent
screening / survivorship controls 的 source gate 缺口。

## What Changed

- 新增 `openclaw_types::stock_etf_pit_universe::StockEtfPitUniverseV1`。
- 新增 blocked template：`settings/broker/stock_etf_pit_universe.template.toml`。
- 新增 acceptance tests：`stock_etf_pit_universe_acceptance`。
- 將 `stock_etf_pit_universe_contract_v1` 加入 Phase 0 manifest JSON 與 manifest validator。
- 將 broker capability registry 的 shadow signal / scorecard gates 綁到 PIT universe contract。
- 更新 ADR-0048、Phase 0 packet、SPEC register、document/initiative indexes。

## Contract Requirements

Validator accepts only source-backed `stock_etf_cash` / IBKR PIT universe records with:

- universe id, version, hash, as-of time, and effective membership window
- bounded constituent count and v1 maximum bound
- per-constituent symbol, instrument kind, instrument identity hash, listing venue,
  primary exchange, currency, tradability, PRIIPs, and included marker
- inclusion, exclusion, liquidity, tradability, PRIIPs, delisted/inactive policy,
  corporate-action, market-calendar, and source artifact hashes
- evidence-clock freeze flag
- survivorship-bias controls
- Bybit live execution unchanged
- IBKR live denied

Validator rejects:

- crypto / CFD / cash constituents
- unknown or cash-ledger venues
- non-USD v1 currency
- untradable constituents
- blocked/unknown PRIIPs status
- malformed universe id/version/hash/window/counts
- missing screen/policy/corporate-action/calendar/source hashes
- missing freeze or survivorship controls
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
rustfmt rust/openclaw_types/src/stock_etf_pit_universe.rs rust/openclaw_types/tests/stock_etf_pit_universe_acceptance.rs rust/openclaw_types/src/lib.rs rust/openclaw_types/src/stock_etf_phase0_manifest.rs rust/openclaw_types/src/stock_etf_broker_capability_registry.rs
cargo test -p openclaw_types --test stock_etf_pit_universe_acceptance --test stock_etf_phase0_manifest_acceptance --test stock_etf_broker_capability_registry_acceptance
cargo test -p openclaw_types
rustfmt --check rust/openclaw_types/src/stock_etf_pit_universe.rs rust/openclaw_types/tests/stock_etf_pit_universe_acceptance.rs rust/openclaw_types/src/stock_etf_phase0_manifest.rs rust/openclaw_types/src/stock_etf_broker_capability_registry.rs
git diff --check
```

Result:

- PIT universe acceptance: 6 passed
- Phase 0 manifest acceptance: 6 passed
- broker capability registry acceptance: 8 passed
- full `openclaw_types`: 35 unit/golden passed + 143 integration/acceptance passed
- rustfmt focused check: passed
- git diff whitespace check: passed

## Non-Authority Statement

This checkpoint grants no IBKR API contact, no contract-details call, no market
data collection, no secret access, no connector runtime, no paper order, no DB
migration/apply, no scorecard write, no evidence-clock start, no GUI lane
authority, no release approval, no tiny-live, and no live authority.

First IBKR contact remains blocked until real secret/topology evidence and an
immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
