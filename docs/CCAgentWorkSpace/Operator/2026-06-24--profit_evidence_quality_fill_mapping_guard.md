# Operator Mirror: Profit Evidence Quality Fill Mapping Guard

Date: 2026-06-24
Source checkpoint: `66f063ccbf3edfd2559527c4151fdac2fc74e24b`
PM report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--profit_evidence_quality_fill_mapping_guard.md`

## Operator-Relevant Summary

`P0-PROFIT-EVIDENCE-QUALITY` remains `BLOCKED_BY_OPERATOR_ACTION`: exchange working-order overhang cleanup/quarantine and runtime/exchange-local fill-lineage reconciliation still require explicit operator authorization or explicit quarantine.

This checkpoint only adds a source-only Rust fill-lineage guard. It does not deploy code, restart services, write PG, call Bybit, cancel/modify/close orders, lower Cost Gate, grant probe/order/live authority, enable the Rust writer, or create promotion proof.

## What Changed In Source

- Successful primary REST order dispatch responses can now emit a local `orderId -> orderLinkId` mapping event.
- The new dispatch-response mapping is recorded only when the pending order is still active.
- Stale mappings are removed and fall back to unattributed audit rather than arbitrary attribution.
- Mapping cleanup now covers common pending-order lifecycle removals and reset/sweep paths.

Required caveat: this is source-only fill-lineage guard, not deployed/runtime-proven lineage closure. The pre-existing OrderUpdate mapping path remains separate.

## Verification

- `cargo test -p openclaw_engine pending_registration_order_type_tests -- --nocapture`: 26 focused tests passed; command exited 0.
- `git diff --check`: clean.
- PA/E2/E4/QA reviews: PASS.

## Still Required From Operator

- Authorize or explicitly quarantine exchange working-order overhang cleanup and runtime fill-lineage reconciliation before candidate selection.
- Any Bybit cancel/modify/close, PG reconciliation/write, crontab/restart/deploy/source sync, bounded Demo probe, order authority, live authority, or Rust writer enablement still requires explicit authorization.

Unattributed fills and `flash_dip_buy` demo fills remain excluded from bounded-probe proof, Cost Gate proof, promotion evidence, and risk-adjusted net PnL proof.
