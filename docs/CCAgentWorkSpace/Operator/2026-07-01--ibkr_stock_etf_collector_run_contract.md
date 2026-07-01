# Operator Brief — IBKR Stock/ETF Collector Run Contract

Date: 2026-07-01

## Summary

新增 `stock_etf_collector_run_v1`，把未來 Phase 3 collector run 必須提供的
source-only 證據形狀固定下來。這不是 collector 啟動，也不是 IBKR first contact。

## What Changed

- Phase0 named contracts 從 33 增為 34。
- Collector run contract 要求至少 5 個 green trading sessions。
- 必須帶 PIT universe、market-data provenance、reference data、storage capacity、gap
  report、DQ manifest、replay manifest、source artifact hashes。
- Existing Evidence Status panel 現在顯示 default-blocked `collector_run`。
- FastAPI 和 GUI 只做 fail-closed display，沒有新增 endpoint、IPC method 或 GUI fanout。

## Verification

- Python compile: PASS
- JS syntax: PASS
- Rust format: PASS
- Full Stock/ETF FastAPI/static: `120 passed`
- Full `openclaw_types`: `287` tests passed
- Engine Stock/ETF focused: `31 passed`
- Docs trace guard: `2 passed`
- `git diff --check`: PASS

## Boundary

沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有
connector runtime、沒有 read probe execution、沒有 collector start、沒有 market-data
ingestion、沒有 paper order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有
scorecard writer、沒有 DB apply、沒有 evidence clock、沒有 Linux runtime sync/restart、沒有
tiny-live/live authority，也沒有改動 Bybit live execution 行為。
