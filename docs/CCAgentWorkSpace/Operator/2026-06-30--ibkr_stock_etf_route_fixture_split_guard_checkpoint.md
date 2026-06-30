# Operator Brief - IBKR Stock/ETF Route Fixture Split Guard

日期：2026-06-30
結論：完成一個 source-only / behavior-preserving route fixture structure checkpoint。

## 做了什麼

- 把 1525 行的 `stock_etf_route_fixtures.py` 拆成同名 package：
  `stock_etf_route_fixtures/`。
- Package 內部拆成 `app.py`、`phase2_payloads.py`、`phase3_payloads.py`、
  `phase5_payloads.py`，並由 `__init__.py` 維持舊 import surface。
- 既有 route tests 的 `from stock_etf_route_fixtures import ...` 不變。
- 拆分後每個 fixture 模組都低於 800 行 review-attention threshold。
- 新增 structure guard，防止 fixture package 回退成大型單檔或引入 network /
  IBKR SDK / file-write token。

## 驗證

- Route fixture `py_compile`：PASS
- Route fixture split static guard：`3 passed`
- Full Stock/ETF FastAPI/static：`105 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

## 不代表什麼

不代表 IBKR 已接通、不代表 Phase 2/3 啟動、不代表 secret slot 建立、不代表 connector
runtime、read probe execution、paper account snapshot、paper order、fill import、evidence
writer、DB apply 或 live/tiny-live 權限。Bybit live 行為未變。
