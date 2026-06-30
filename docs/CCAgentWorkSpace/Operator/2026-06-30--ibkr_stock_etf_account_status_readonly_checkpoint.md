# Operator Brief - IBKR Stock/ETF Account Status Read-Only Checkpoint

日期：2026-06-30
結論：完成一個 source-only / display-only checkpoint。

## 做了什麼

- 新增 `GET /api/v1/stock-etf/account-status`。
- GUI `Stock/ETF · IBKR Readiness` 頁新增 `IBKR Account` summary 與 `Account / Connector Status` 面板。
- Rust IPC 新增只讀 fixture `stock_etf.get_account_status`。
- `lane_scoped_ipc_v1` 與 `gui_lane_contract_v1` 已同步要求 account-status 是 display-only / GET-only。
- API/GUI 只顯示 blocked/fail-closed account、session、paper-attestation、connector/socket 狀態，不把任何 account snapshot、session attestation、connector runtime 或 gateway socket 當成已存在 evidence。

## 驗證

- Python compile：PASS
- Rust format check：PASS
- FastAPI/static guard focused pytest：`52 passed`
- Rust engine Stock/ETF focused tests：`13 passed`
- GUI/lane IPC contract focused tests：`17 passed`
- Node inline scripts：PASS
- `git diff --check`：PASS

## 注意

第一次 Python route 驗證抓到 IPC down 時 account fallback 被誤判成 contract violation；已修正為 degraded/fail-closed，重跑後綠。

## 不代表什麼

不代表 IBKR 已接通、不代表 Phase 2/3 啟動、不代表 secret slot 建立、不代表 connector runtime、account snapshot、portfolio snapshot、cash ledger、broker paper attestation、paper order、fill import、lifecycle writer、scorecard writer、DB apply 或 live/tiny-live 權限。Bybit live 行為未變。
