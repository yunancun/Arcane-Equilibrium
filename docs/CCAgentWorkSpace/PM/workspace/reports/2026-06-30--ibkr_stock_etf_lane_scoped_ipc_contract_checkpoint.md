# PM Checkpoint — IBKR Stock/ETF Lane-Scoped IPC Contract

日期：2026-06-30
角色：PM(default)
範圍：ADR-0048 / AMD-2026-06-29-01 lane-scoped IPC source contract

## Verdict

`DONE_WITH_CONCERNS_SOURCE_ONLY`

本 checkpoint 新增 `lane_scoped_ipc_v1` Rust source validator 與 blocked
broker template，補齊 Phase 0 manifest 已列 `lane_scoped_ipc_v1`、但缺少
machine-checkable method/gate/field/typed-denial matrix 的缺口。

## What Changed

- 新增 `openclaw_types::stock_etf_lane_scoped_ipc::StockEtfLaneScopedIpcContractV1`。
- 新增 blocked template：`settings/broker/stock_etf_lane_scoped_ipc.template.toml`。
- 新增 acceptance tests：`stock_etf_lane_scoped_ipc_acceptance`。
- 將 `broker_capability_registry_v1` 的 paper submit/cancel/replace rows 額外綁到 `lane_scoped_ipc_v1`。
- 更新 ADR-0048、Phase 0 packet、SPEC register、document/initiative indexes。

## Contract Requirements

Validator pins exact Stock/ETF IPC methods:

- `stock_etf.get_lane_status`
- `stock_etf.get_readiness`
- `stock_etf.preview_paper_order`
- `stock_etf.submit_paper_order`
- `stock_etf.cancel_paper_order`
- `stock_etf.replace_paper_order`
- `stock_etf.import_paper_fills`
- `stock_etf.evaluate_shadow_signal`

Paper submit/cancel/replace require Rust ownership plus:

- `phase2_ibkr_external_surface_gate_v1`
- `ibkr_session_attestation_v1`
- `stock_etf_scoped_authorization_v1`
- Decision Lease and Guardian gates
- risk-config, instrument-identity, idempotency, lifecycle, broker-registry, and audit-event fields

Validator rejects:

- missing or duplicate IPC methods
- unknown or Bybit paper IPC methods
- direct Python broker write authority
- reuse of existing Bybit paper IPC/order paths
- missing method gates, request fields, typed denials, or Rust ownership
- IBKR contact, connector runtime, serialized secrets, live environment, and Bybit-live regression

## Dispatch Note

Repo workflow would normally separate PA/E1/E2/E4/QA for broader implementation.
This desktop turn kept the work PM-local because the change is a narrow
source-only contract and no runtime / connector / order path is touched.
Focused Rust tests plus crate-level regression are the verification surface.

## Verification

Executed:

```bash
rustfmt rust/openclaw_types/src/stock_etf_lane_scoped_ipc.rs rust/openclaw_types/tests/stock_etf_lane_scoped_ipc_acceptance.rs rust/openclaw_types/src/lib.rs rust/openclaw_types/src/stock_etf_broker_capability_registry.rs
cargo test -p openclaw_types --test stock_etf_lane_scoped_ipc_acceptance --test stock_etf_broker_capability_registry_acceptance --test stock_etf_phase0_manifest_acceptance
cargo test -p openclaw_types
rustfmt --check rust/openclaw_types/src/stock_etf_lane_scoped_ipc.rs rust/openclaw_types/tests/stock_etf_lane_scoped_ipc_acceptance.rs rust/openclaw_types/src/stock_etf_broker_capability_registry.rs
git diff --check
```

Result:

- lane-scoped IPC acceptance: 7 passed
- broker capability registry acceptance: 8 passed
- Phase 0 manifest acceptance: 6 passed
- full `openclaw_types` regression: 35 unit/golden + 156 integration/acceptance passed
- focused `rustfmt --check`: passed
- `git diff --check`: passed

## Non-Authority Statement

This checkpoint grants no IPC runtime, no IBKR API contact, no contract-details
call, no market data collection, no secret access, no connector runtime, no
paper order, no DB migration/apply, no scorecard write, no evidence-clock
start, no GUI lane authority, no release approval, no tiny-live, and no live
authority.

First IBKR contact remains blocked until real secret/topology evidence and an
immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
