# PM Report - IBKR Stock/ETF Data Foundation Status Read-Only Checkpoint

日期：2026-06-30
狀態：source-only / display-only checkpoint complete

## Scope

本 checkpoint 補上 `stock_etf_cash` paper/shadow 前的 data-foundation 可觀測面，將既有 `instrument_identity_contract_v1` 與 `stock_etf_reference_data_sources_v1` posture 暴露給 operator 與 GUI。

新增內容：

- Rust IPC fixture：`stock_etf.get_data_foundation_status`
- FastAPI route：`GET /api/v1/stock-etf/data-foundation-status`
- GUI：`Data Foundation` summary metric 與 `Data Foundation Status` panel
- Python normalizer：IPC unavailable fail-closed、side-effect drift contract violation、top-level authority fields forced false
- Contract sync：`lane_scoped_ipc_v1` 新增 `GetDataFoundationStatus` display-only method；`gui_lane_contract_v1` 新增 data-foundation GET-only endpoint

## Boundary

明確未做：

- no IBKR API/contact/healthcheck
- no secret read/create/serialization
- no connector runtime
- no contract-details request
- no reference-data collection/ingestion
- no market-data ingestion or collector start
- no evidence clock / scorecard writer / DB apply
- no paper order / fill import / lifecycle writer
- no GUI lane authority / selector authority
- no tiny-live / live / margin / short / options / CFD
- no Bybit behavior change
- no Linux runtime sync/restart

## Verification

- Python compile: PASS
- Node inline scripts: PASS (`7` scripts)
- Rust format check: PASS
- FastAPI/static focused pytest: `18 passed`
- Full Stock/ETF FastAPI/static pytest: `67 passed`
- Rust engine Stock/ETF focused tests: `16 passed`
- GUI/lane IPC focused tests: `17 passed`
- Full `openclaw_types`: `35` unit/golden + `206` integration/acceptance + `0` doc-tests
- `git diff --check`: PASS

## Dispatch Note

本 session 未暴露 repo subagent execution tool；PM 未能實際派發 PA/E1/E2/E4/QA subagents。此 checkpoint 由 PM 依 `srv/.codex` 角色規則執行 source-only 變更，並以自動化測試替代可機器檢查的最低驗收。正式 launch certification 仍不得把本報告視為角色 closeout。
