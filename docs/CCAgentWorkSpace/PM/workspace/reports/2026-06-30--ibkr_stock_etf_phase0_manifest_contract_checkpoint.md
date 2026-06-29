# PM Checkpoint — IBKR Stock/ETF Phase 0 Manifest Contract

日期：2026-06-30
角色：PM(default)
範圍：ADR-0048 / AMD-2026-06-29-01 Phase 0 manifest source-only validation

## Verdict

`DONE_WITH_CONCERNS_SOURCE_ONLY`

本 checkpoint 新增 `stock_etf_phase0_contract_packet_manifest_v1` Rust source
validator，讓 Phase 0 named contract packet 的 machine-readable manifest 可由
`openclaw_types` acceptance test 直接驗證。

## What Changed

- 新增 `openclaw_types::stock_etf_phase0_manifest::StockEtfPhase0ContractPacketManifestV1`。
- 新增 acceptance tests：`stock_etf_phase0_manifest_acceptance`。
- 測試直接讀取並驗證
  `docs/execution_plan/specs/2026-06-29--stock_etf_cash_phase0_named_contract_packet.manifest.json`。
- 更新 ADR-0048、Phase 0 packet、SPEC register、document/initiative indexes。

## Contract Requirements

Validator pins:

- manifest schema/status/scope/date
- ADR/AMD/contract-packet authority paths
- IBKR API baseline: `ib_gateway_tws_api`, loopback only, paper port `4002`
- `live_ports_denied=true`
- `ibkr_call_performed=false`
- all global denials
- exact named contract list with no missing, duplicate, or unexpected entries
- fail-closed phase unlock table

Validator rejects:

- prior IBKR contact
- live-port allowance
- missing global denials
- missing/duplicate/unknown contracts
- Phase 2 contact unlock
- Phase 3 evidence-clock start
- Phase 4 GUI runtime enablement
- Phase 5 paper-shadow online claim
- tiny-live / live unlock

## Dispatch Note

Repo workflow would normally separate PA/E1/E2/E4/QA for implementation work.
This desktop turn did not spawn subagents because the available multi-agent tool
requires explicit operator authorization for delegation. PM kept scope narrow and
source-only, then used focused Rust acceptance tests plus crate-level regression
as the verification surface.

## Verification

Executed:

```bash
rustfmt rust/openclaw_types/src/stock_etf_phase0_manifest.rs rust/openclaw_types/tests/stock_etf_phase0_manifest_acceptance.rs
cargo test -p openclaw_types --test stock_etf_phase0_manifest_acceptance
cargo test -p openclaw_types
rustfmt --check rust/openclaw_types/src/stock_etf_phase0_manifest.rs rust/openclaw_types/tests/stock_etf_phase0_manifest_acceptance.rs
git diff --check
```

Result:

- focused acceptance: 6 passed
- full `openclaw_types`: 35 unit/golden passed + 130 integration/acceptance passed
- rustfmt check: passed
- diff check: passed

## Non-Authority Statement

This checkpoint grants no IBKR API contact, no secret access, no connector
runtime, no paper order, no DB migration/apply, no evidence-clock start, no GUI
lane authority, no release approval, no tiny-live, and no live authority.

First IBKR contact remains blocked until real secret/topology evidence and an
immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
