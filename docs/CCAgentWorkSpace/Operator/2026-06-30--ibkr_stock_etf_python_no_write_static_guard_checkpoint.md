# Operator 摘要 — IBKR Stock/ETF Python No-Write Static Guard

日期：2026-06-30
範圍：IBKR `stock_etf_cash` Python/FastAPI boundary source-only checkpoint

## 結論

已新增 Python AST static guard，確保目前 IBKR Stock/ETF Python surface 仍是
readiness/display-only，不會直接持有 broker write API。

## 現在會擋什麼

- `place_order`
- `submit_order`
- `submit_paper_order`
- `cancel_order`
- `cancel_all_orders`
- `cancel_paper_order`
- `replace_order`
- `replace_paper_order`
- `modify_order`
- `create_order`
- `stock_etf.submit_paper_order` 等 forbidden paper-order IPC 字串
- 直接 import `ibapi` / `ib_insync`
- Stock/ETF/IBKR Python 非 GET route

測試只掃描 Stock/ETF/IBKR route surface 與未來
`program_code/broker_connectors/ibkr_connector/`，不掃描既有 Bybit modules，
所以不會把現有 Bybit governed execution surface 誤判成 IBKR 違規。

## 驗證

- `python3 -m pytest tests/test_stock_etf_python_no_write_static_guard.py`：2 passed
- `python3 -m pytest tests/test_stock_etf_routes.py`：8 passed

## 仍然不授權

- 不接觸 IBKR
- 不建立 secret slot
- 不啟動 connector
- 不送 paper order
- 不 apply DB migration
- 不開始 evidence clock
- 不授權 GUI lane authority
- 不授權 release
- 不授權 tiny-live / live

第一個 IBKR contact 仍需要 real secret/topology evidence + immutable Phase 2 PASS artifact。
