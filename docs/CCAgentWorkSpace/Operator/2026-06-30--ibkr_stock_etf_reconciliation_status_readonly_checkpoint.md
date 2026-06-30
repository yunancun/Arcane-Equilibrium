# Operator Brief - IBKR Stock/ETF Reconciliation Status Read-Only Checkpoint

日期：2026-06-30
結論：完成一個 source-only / display-only checkpoint。

## 做了什麼

- 新增 `GET /api/v1/stock-etf/reconciliation-status`。
- GUI `Stock/ETF · IBKR Readiness` 頁新增 `Reconciliation Status` 面板。
- Rust IPC 新增只讀 fixture `stock_etf.get_reconciliation_status`。
- `lane_scoped_ipc_v1` 與 `gui_lane_contract_v1` 已同步要求 reconciliation-status 是 display-only / GET-only。
- API/GUI 只顯示 blocked/fail-closed reconciliation 狀態，不把 paper/shadow link、divergence、ids、hashes、scorecard writer 或 DB apply 當成已存在 evidence。

## 驗證

- Python compile：PASS
- Rust format check：PASS
- FastAPI/static guard focused pytest：`47 passed`
- Rust engine Stock/ETF focused tests：`12 passed`
- GUI/lane IPC contract focused tests：`17 passed`
- Node inline scripts：`parsed 7 inline script(s)`
- `git diff --check`：PASS

## 注意

第一次 engine 驗證抓到 dispatch/method-registry 漏接新 method；已補成 read-only / slot=None，重跑後綠。

## 不代表什麼

不代表 IBKR 已接通、不代表 Phase 2/3 啟動、不代表 secret slot 建立、不代表 connector runtime、paper account snapshot、broker paper attestation、paper order、fill import、lifecycle writer、scorecard writer、DB apply 或 live/tiny-live 權限。Bybit live 行為未變。
