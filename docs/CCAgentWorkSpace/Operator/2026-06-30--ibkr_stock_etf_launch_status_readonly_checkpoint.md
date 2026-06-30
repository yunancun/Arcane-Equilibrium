# Operator Brief - IBKR Stock/ETF Launch Status Read-Only Checkpoint

日期：2026-06-30
結論：完成一個 source-only / display-only checkpoint。

## 做了什麼

- 新增 `GET /api/v1/stock-etf/launch-status`。
- GUI `Stock/ETF · IBKR Readiness` 頁新增 `Launch Gate` summary 與 `Launch / Release Status` 面板。
- Rust IPC 新增只讀 fixture `stock_etf.get_launch_status`。
- `lane_scoped_ipc_v1` 與 `gui_lane_contract_v1` 已同步要求 launch-status 是 display-only / GET-only。
- API/GUI 只顯示 blocked/fail-closed launch posture：release packet、disable-cleanup runbook、tiny-live ADR eligibility 仍未接受，launch/live 權限維持 false。

## 驗證

- Python compile：PASS
- Rust format check：PASS
- FastAPI/static guard focused pytest：`58 passed`
- Rust engine Stock/ETF focused tests：`15 passed`
- GUI/lane IPC focused tests：`17 passed`
- Full `openclaw_types`：`35` unit/golden + `174` integration/acceptance + `0` doc-tests passed
- Node inline scripts：PASS (`7` scripts)
- `git diff --check`：PASS

## 不代表什麼

不代表 IBKR 已接通、不代表 Phase 2/3/5 啟動、不代表 secret slot 建立、不代表 connector runtime、evidence clock、scorecard writer、DB apply、paper-shadow launch、account snapshot、paper order、fill import、lifecycle writer、GUI lane authority 或 live/tiny-live 權限。Bybit live 行為未變。

Linux runtime 未 sync、未 restart、未 fast-forward。
