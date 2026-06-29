# PM Checkpoint — IBKR Stock/ETF Disable-Cleanup Runbook Contract

日期：2026-06-30
角色：PM(default)
範圍：ADR-0048 / AMD-2026-06-29-01 `stock_etf_cash` paper/shadow source-only contract

## Verdict

`DONE_WITH_CONCERNS_SOURCE_ONLY`

本 checkpoint 新增 `stock_etf_kill_switch_and_disable_cleanup_runbook_v1`
Rust source validator 與 blocked broker template，將 Phase 0 packet 第 21 節
kill-switch / disable-cleanup 條款變成 machine-checkable contract。

## What Changed

- 新增 `openclaw_types::stock_etf_disable_cleanup_runbook::StockEtfDisableCleanupRunbookV1`。
- 新增 blocked template：`settings/broker/stock_etf_disable_cleanup_runbook.template.toml`。
- 新增 acceptance tests：`stock_etf_disable_cleanup_runbook_acceptance`。
- 更新 ADR-0048、Phase 0 packet、SPEC register、document/initiative indexes。

## Contract Requirements

Validator accepts only when all of these are proven:

- `OPENCLAW_STOCK_ETF_LANE_ENABLED=0`
- `OPENCLAW_IBKR_READONLY_ENABLED=0`
- `OPENCLAW_IBKR_PAPER_ENABLED=0`
- `OPENCLAW_STOCK_ETF_SHADOW_ONLY=1`
- collector stopped
- GUI stock views disabled or hidden
- live-secret absence proven
- evidence archive forward-only
- DB retention forward-only
- append-only audit preserved
- Bybit live execution unchanged

Validator rejects:

- IBKR contact performed
- connector runtime started
- paper order routed
- secret-slot creation
- secret content serialization
- destructive DB cleanup
- DB delete/truncate permission
- paper-shadow launch authority claim
- tiny-live / live authority claim

## Dispatch Note

Repo workflow would normally separate PA/E1/E2/E4/QA for implementation work.
This desktop turn did not spawn subagents because the available multi-agent tool
requires explicit operator authorization for delegation. PM therefore kept the
scope narrow and source-only, then used focused Rust acceptance tests plus the
crate-level test plan below as the verification surface.

## Verification

Executed:

```bash
rustfmt rust/openclaw_types/src/stock_etf_disable_cleanup_runbook.rs rust/openclaw_types/tests/stock_etf_disable_cleanup_runbook_acceptance.rs
cargo test -p openclaw_types --test stock_etf_disable_cleanup_runbook_acceptance
cargo test -p openclaw_types
rustfmt --check rust/openclaw_types/src/stock_etf_disable_cleanup_runbook.rs rust/openclaw_types/tests/stock_etf_disable_cleanup_runbook_acceptance.rs
git diff --check
```

Result:

- focused acceptance: 6 passed
- full `openclaw_types`: 35 unit/golden passed + 124 integration/acceptance passed
- rustfmt check: passed
- diff check: passed

## Non-Authority Statement

This checkpoint grants no IBKR API contact, no secret access, no connector
runtime, no paper order, no DB migration/apply, no evidence-clock start, no GUI
lane authority, no release approval, no tiny-live, and no live authority.

First IBKR contact remains blocked until real secret/topology evidence and an
immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
