# Operator Brief - IBKR Stock/ETF Scorecard Status Read-Only Checkpoint

日期：2026-06-30
結論：完成一個 source-only / display-only checkpoint。

## 做了什麼

- 新增 `GET /api/v1/stock-etf/scorecard-status`。
- GUI `Stock/ETF · IBKR Readiness` 頁新增 `Scorecard` summary 與 `Scorecard Verdict Status` 面板。
- Rust IPC 新增只讀 fixture `stock_etf.get_scorecard_status`。
- `lane_scoped_ipc_v1` 與 `gui_lane_contract_v1` 已同步要求 scorecard-status 是 display-only / GET-only。
- API/GUI 只顯示 blocked/fail-closed scorecard verdict posture，不把任何 verdict artifact、hash、review、sample/window、PnL、LCB、PSR/DSR 或 quality label 當成已存在 evidence。

## 驗證

- Python compile：PASS
- Rust format check：PASS
- FastAPI/static guard focused pytest：`57 passed`
- Rust engine Stock/ETF focused tests：`14 passed`
- Full `openclaw_types`：`35` unit/golden + `206` integration/acceptance + `0` doc-tests passed
- Node inline scripts：PASS
- `git diff --check`：PASS

## 不代表什麼

不代表 IBKR 已接通、不代表 Phase 2/3 啟動、不代表 secret slot 建立、不代表 connector runtime、evidence clock、scorecard writer、scorecard DB apply、account snapshot、paper order、fill import、lifecycle writer、GUI lane authority 或 live/tiny-live 權限。Bybit live 行為未變。

Linux runtime 未 sync、未 restart、未 fast-forward。
