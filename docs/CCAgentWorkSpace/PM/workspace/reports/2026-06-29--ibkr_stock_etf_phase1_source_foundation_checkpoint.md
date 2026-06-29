# IBKR Stock/ETF Phase 1 Source Foundation Checkpoint

Date: 2026-06-29
Status: **DONE_WITH_CONCERNS - source/test foundation only**
Scope: `stock_etf_cash` IBKR read-only / paper / shadow research lane.

## Result

Phase 1 source foundation is present for ADR-0048 / AMD-2026-06-29-01:

- closed Rust taxonomy and denial matrix in `openclaw_types::stock_etf_lane`
- default-off lane/broker/risk config files under `settings/`
- lane-scoped `stock_etf.*` IPC fixture that returns readiness or typed denial and does not send `PipelineCommand`
- source-only DDL draft for broker/research/audit stock/ETF evidence tables
- focused Rust acceptance tests for default-off posture, typed denials, config parse, IPC separation, and no Bybit paper IPC reuse

## Hard Boundary

This checkpoint does not authorize:

- IBKR API call or IBKR Gateway/TWS connection
- IBKR connector implementation
- secret-slot creation or credential write
- broker-paper order submission
- active DB migration apply
- GUI stock/ETF runtime activation
- evidence clock start
- live, tiny-live, margin, short, options, CFD, transfer, or account-management writes

Bybit remains the only active live execution venue. Existing Bybit paper/live execution handlers were not converted into stock/ETF authority.

## Verification

- `cargo test -p openclaw_types --test stock_etf_lane_acceptance` — 8 passed
- `cargo test -p openclaw_engine ipc_server::tests::stock_etf` — 3 passed
- `cargo test -p openclaw_engine ipc_server::method_registry::tests::stock_etf_methods_are_registered_as_lane_scoped_fixtures` — 1 passed
- `git diff --check` — pass

Warnings observed are pre-existing Rust test warnings (`async_trait` unused import, `ScriptedSpawn` visibility) and are unrelated to this checkpoint.

## Next Gate

Next work is Phase 2 external-surface gate source/review only. First IBKR contact remains blocked until `phase2_ibkr_external_surface_gate_v1` has an immutable PASS artifact.
