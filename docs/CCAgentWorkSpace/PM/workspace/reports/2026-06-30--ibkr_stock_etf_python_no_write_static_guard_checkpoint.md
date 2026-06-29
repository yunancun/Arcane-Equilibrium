# PM Checkpoint — IBKR Stock/ETF Python No-Write Static Guard

日期：2026-06-30
角色：PM(default)
範圍：ADR-0048 / AMD-2026-06-29-01 Python/FastAPI boundary verification

## Verdict

`DONE_WITH_CONCERNS_SOURCE_ONLY`

本 checkpoint 新增 Phase 1 verification guard：
`test_stock_etf_python_no_write_static_guard.py`。它用 Python AST 掃描
Stock/ETF/IBKR Python route surface 和未來
`program_code/broker_connectors/ibkr_connector/`，確保 Python/FastAPI 不暴露
direct IBKR broker write API。

## What Changed

- 新增 `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`。
- 更新 ADR-0048、Phase 0 packet、SPEC register、document/initiative indexes。

## Guard Coverage

The guard rejects:

- direct function definitions or calls named `place_order`, `submit_order`, `submit_paper_order`, `cancel_order`, `cancel_all_orders`, `cancel_paper_order`, `replace_order`, `replace_paper_order`, `modify_order`, or `create_order`
- forbidden paper-order IPC method strings such as `stock_etf.submit_paper_order`
- direct `ibapi` / `ib_insync` imports in Stock/ETF/IBKR Python surfaces
- non-GET Stock/ETF/IBKR routes until a later Rust-authority contract explicitly revises this boundary

It intentionally does not scan existing Bybit modules, so the existing Bybit
REST client and governed Bybit execution surface are not regressed by this guard.

## Dispatch Note

Repo workflow would normally separate PA/E1/E2/E4/QA for implementation work.
This desktop turn did not spawn subagents because the available multi-agent tool
requires explicit operator authorization for delegation. PM kept the scope narrow
and used focused pytest verification on the new guard plus the existing
Stock/ETF readiness route tests.

## Verification

Executed:

```bash
python3 -m pytest tests/test_stock_etf_python_no_write_static_guard.py
python3 -m pytest tests/test_stock_etf_routes.py
```

Result:

- Python no-write static guard: 2 passed
- Stock/ETF readiness/GUI route tests: 8 passed

## Non-Authority Statement

This checkpoint grants no IBKR API contact, no secret access, no connector
runtime, no paper order, no DB migration/apply, no evidence-clock start, no GUI
lane authority, no release approval, no tiny-live, and no live authority.

First IBKR contact remains blocked until real secret/topology evidence and an
immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist.
