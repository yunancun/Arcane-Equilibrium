# Operator Brief - IBKR Stock/ETF Route Test Split

日期：2026-06-30
結論：完成一個 source-only / behavior-preserving test refactor checkpoint。

## 做了什麼

- 把原本 1736 行的 `test_stock_etf_routes.py` 拆成共用 fixture helper 加多個 endpoint 專用測試檔。
- 原 route test 檔現在只保留 auth、OpenAPI GET-only、redirect、static GUI registration/display-only 類測試。
- lane/readiness/evidence/universe/shadow/paper status 測試各自分檔。
- 所有 Stock/ETF route-test 檔都低於 800 行 review-attention threshold。

## 驗證

- Python compile：PASS
- Split FastAPI/static guard focused pytest：`42 passed`
- `git diff --check`：PASS

## 不代表什麼

不代表 IBKR 已接通、不代表 Phase 2/3 啟動、不代表 secret slot 建立、不代表 connector runtime、paper account snapshot、broker paper attestation、paper order、fill import、lifecycle writer、DB apply 或 live/tiny-live 權限。Bybit live 行為未變。
