# Operator Brief - IBKR Stock/ETF Status Normalizer Split

日期：2026-06-30
結論：完成一個 source-only / behavior-preserving refactor checkpoint。

## 做了什麼

- 把 `stock_etf_routes.py` 裡的大量 fail-closed status normalizer 拆到獨立模組。
- route 檔現在只保留 authenticated GET handler、IPC 查詢、no-store header。
- normalizer 按 readiness、evidence、universe、shadow、paper 分層，所有新增 status normalizer 模組都低於 800 行 review-attention threshold。
- `stock_etf_routes.py` 從 1550 行降到 257 行。

## 驗證

- Python compile：PASS
- FastAPI/static guard focused pytest：`42 passed`
- `git diff --check`：PASS

## 注意

`test_stock_etf_routes.py` 仍是 1736 行，低於 2000 hard cap，但高於 800 行 review-attention threshold。下一次動到 Stock/ETF route tests 時，應先拆 shared fixtures/assertions。

## 不代表什麼

不代表 IBKR 已接通、不代表 Phase 2/3 啟動、不代表 secret slot 建立、不代表 connector runtime、paper account snapshot、broker paper attestation、paper order、fill import、lifecycle writer、DB apply 或 live/tiny-live 權限。Bybit live 行為未變。
