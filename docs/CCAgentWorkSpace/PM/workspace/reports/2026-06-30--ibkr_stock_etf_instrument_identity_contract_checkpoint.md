# PM Checkpoint — IBKR Stock/ETF Instrument Identity Contract

日期：2026-06-30
角色：PM(default)
範圍：ADR-0048 / AMD-2026-06-29-01 point-in-time instrument identity source contract

## Verdict

`DONE_WITH_CONCERNS_SOURCE_ONLY`

本 checkpoint 新增 `instrument_identity_contract_v1` Rust source validator 與
blocked broker template，補齊 `broker_capability_registry_v1` 已引用但原本未
machine-checkable 的 `contract_details_read` gate。

## What Changed

- 新增 `openclaw_types::stock_etf_instrument_identity::StockEtfInstrumentIdentityV1`。
- 新增 blocked template：`settings/broker/stock_etf_instrument_identity.template.toml`。
- 新增 acceptance tests：`stock_etf_instrument_identity_acceptance`。
- 將 `instrument_identity_contract_v1` 加入 Phase 0 manifest JSON 與 manifest validator。
- 更新 ADR-0048、Phase 0 packet、SPEC register、document/initiative indexes。

## Contract Requirements

Validator accepts only point-in-time `stock_etf_cash` / IBKR identity records with:

- closed `stock` / `etf` / `cash` instrument kind
- closed listing venue and primary exchange
- v1 USD currency
- tradable status
- PRIIPs KID status `not_required` or `present`
- fractional policy recorded
- point-in-time as-of timestamp
- market calendar id and hash
- broker contract-details hash
- instrument identity hash
- corporate-action adjustment version hash
- source artifact hash
- Bybit live execution unchanged
- IBKR live, margin/short, and options/CFD denied

Validator rejects:

- crypto or CFD instruments
- unknown venue/exchange
- cash-vs-noncash venue mismatch
- non-USD v1 currency
- untradable or halted instruments
- blocked/unknown PRIIPs KID status
- missing PIT/hash/calendar/fractional-policy evidence
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
rustfmt rust/openclaw_types/src/stock_etf_instrument_identity.rs rust/openclaw_types/tests/stock_etf_instrument_identity_acceptance.rs rust/openclaw_types/src/stock_etf_phase0_manifest.rs
cargo test -p openclaw_types --test stock_etf_instrument_identity_acceptance --test stock_etf_phase0_manifest_acceptance
cargo test -p openclaw_types
rustfmt --check rust/openclaw_types/src/stock_etf_instrument_identity.rs rust/openclaw_types/tests/stock_etf_instrument_identity_acceptance.rs rust/openclaw_types/src/stock_etf_phase0_manifest.rs
git diff --check
```

Result:

- instrument identity acceptance: 7 passed
- Phase 0 manifest acceptance: 6 passed
- full `openclaw_types`: 35 unit/golden passed + 137 integration/acceptance passed
- rustfmt check: passed
- git diff whitespace check: passed

## Non-Authority Statement

This checkpoint grants no IBKR API contact, no contract-details call, no market
data subscription, no secret access, no connector runtime, no paper order, no DB
migration/apply, no evidence-clock start, no GUI lane authority, no release
approval, no tiny-live, and no live authority.

First IBKR contact remains blocked until real secret/topology evidence and an
immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
