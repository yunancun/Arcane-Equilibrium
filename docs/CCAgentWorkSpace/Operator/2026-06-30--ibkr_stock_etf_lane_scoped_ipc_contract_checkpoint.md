# Operator Brief — IBKR Stock/ETF Lane-Scoped IPC Contract

日期：2026-06-30
結論：source-only checkpoint complete；不授權 IPC runtime、IBKR contact 或 paper order。

## Verdict

`DONE_WITH_CONCERNS_SOURCE_ONLY`

PM 新增 `lane_scoped_ipc_v1`，把 future Stock/ETF `stock_etf.*` IPC method
matrix 變成 machine-checkable contract。這補的是 paper order rehearsal 前的
隔離缺口：Stock/ETF paper submit/cancel/replace 必須走獨立 Rust-owned
lane-scoped IPC contract，不得復用現有 Bybit paper IPC/order path。

## What This Adds

- Rust validator: `StockEtfLaneScopedIpcContractV1`
- Blocked template: `settings/broker/stock_etf_lane_scoped_ipc.template.toml`
- Acceptance coverage for default-denied posture, exact method coverage,
  paper effect gates/fields/typed denials, Bybit IPC reuse denial, and
  template parsing.
- Broker capability registry paper write rows now require `lane_scoped_ipc_v1`。

## Boundary

No IPC runtime was started. No IBKR API contact occurred. No market-data
collector, secret read, connector runtime, paper order, DB migration/apply,
scorecard write, evidence-clock start, GUI lane authority, release approval,
tiny-live, or live authority is granted.

Bybit remains the only active live execution venue. First IBKR contact remains
blocked until real secret/topology evidence and an immutable
`phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
