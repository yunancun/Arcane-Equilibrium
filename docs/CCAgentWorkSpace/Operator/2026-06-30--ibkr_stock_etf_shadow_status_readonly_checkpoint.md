# Operator Brief — IBKR Stock/ETF Shadow Status Read-Only Checkpoint

日期：2026-06-30
結論：完成一個 source-only / display-only checkpoint。

## 做了什麼

- 新增 `GET /api/v1/stock-etf/shadow-status`。
- GUI `Stock/ETF · IBKR Readiness` 頁新增 `Shadow Status` 面板。
- Rust IPC 新增只讀 fixture `stock_etf.get_shadow_status`。
- `gui_lane_contract_v1` 現在要求 readiness、lane-status、evidence-status、universe-status、shadow-status 五個 GET-only surface。

## 驗證

- Rust engine Stock/ETF focused tests：`10 passed`
- FastAPI/static guard：`37 passed`
- Node inline scripts：`checked 2 inline scripts`
- Full `openclaw_types`：`35` unit/golden + `198` integration/acceptance + `0` doc-tests
- `git diff --check`：PASS

## 注意

`stock_etf_routes.py` 現在 `1263` 行，低於 2000 hard cap，但已超過 800 行 review-attention threshold。下一個類似 endpoint 前應先拆 shared normalizer/test helpers。

## 不代表什麼

不代表 IBKR 已接通、不代表 Phase 2/3 啟動、不代表 secret slot 建立、不代表 shadow collector/signal/fill、evidence clock、scorecard 或 DB 啟動、不代表 paper order 或 live/tiny-live 權限。Bybit live 行為未變。
