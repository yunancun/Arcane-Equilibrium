# Operator Brief — IBKR Stock/ETF Plan 第三輪 launch-certification

日期：2026-06-29
結論：第三輪完成；八角色一致條件式 certifiable。

## Verdict

CC / FA / PA / E3 / E5 / QC / MIT / QA 全部返回：

`CERTIFIABLE_IF_GATES_PASS`, `SCOPE=paper_shadow_only`, `FINDINGS=0`

PM 簽核語句：

`PAPER_SHADOW_LAUNCH_CERTIFIABLE_IF_ALL_GATES_PASS`

## 這句話的準確含義

在 `paper_shadow_only` 範圍內，如果 Phase 0 named contract packet 被接受，且
Phase 1-5 所有 gates 都按主計劃完成、通過、落下 immutable artifacts，八角色
沒有再發現額外 missing launch gate。到那個時間點，可以簽核
`stock_etf_cash` paper/shadow lane 按排程完整上線。

## 這句話不代表

- 不代表現在可上線。
- 不代表 IBKR live / tiny-live 可上。
- 不代表 margin、short、options、CFD 或 transfer 可做。
- 不代表盈利已證明。
- 不代表 durable alpha 已成立。
- 不代表絕對「無遺漏」保證。

## PM 判斷

第二輪把缺口全部前移成 hard gates；第三輪確認：只要這些 gates 按計劃全部
通過，paper/shadow 上線 scope 就完整。下一步仍是 Phase 0 ADR/AMD + named
contract packet，不是直接寫 IBKR connector。

## 2026-06-30 Operator Update

本 session 已完成下一個 source-only checkpoint：`policy-status`。

你現在會在 Stock/ETF GUI 看到新的 `Policy Gate` 與
`Policy / Capability Status` 面板；後端是
`GET /api/v1/stock-etf/policy-status`，Rust IPC 是
`stock_etf.get_policy_status`。

這只是顯示 blocked/default 的 risk policy 與 broker capability registry 狀態，
不是 IBKR 連線、不是 paper order、不是 Phase 2 start。

Verification 已過：

- Focused FastAPI/static：`18 passed`
- Full Stock/ETF FastAPI/static：`72 passed`
- Engine Stock/ETF：`17 passed`
- GUI/lane IPC acceptance：`17 passed`
- Full openclaw_types：`35 + 206 + 0 doc-tests`

邊界不變：沒有 IBKR contact、沒有 secret、沒有 connector runtime、沒有 paper order、
沒有 DB apply、沒有 evidence clock、沒有 Linux runtime sync/restart，也沒有改動 Bybit
live execution 行為。

## 2026-06-30 Operator Update — Authorization Status

本 session 已完成下一個 source-only checkpoint：`authorization-status`。

你現在會在 Stock/ETF GUI 看到新的 `Authorization Gate` 與
`Authorization Status` 面板；後端是
`GET /api/v1/stock-etf/authorization-status`，Rust IPC 是
`stock_etf.get_authorization_status`。

這只是顯示 blocked/default 的 feature-flag、secret-slot、Phase 2 gate、
session attestation 與 authorization envelope 狀態，不是 IBKR 連線、不是 secret
讀取、不是 paper order、不是 Phase 2 start。

Verification 已過：

- Full Stock/ETF FastAPI/static：`77 passed`
- Engine Stock/ETF：`18 passed`
- GUI/lane IPC acceptance：`17 passed`
- Full openclaw_types：`35 + 206 + 0 doc-tests`
- Workspace `cargo check`：PASS

邊界不變：沒有 IBKR contact、沒有 secret access、沒有 connector runtime、沒有
paper order、沒有 DB apply、沒有 evidence clock、沒有 Linux runtime sync/restart，
也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — GUI Split Hygiene

`authorization-status` 完成後，我把 Stock/ETF GUI 做了純拆檔：原本
`tab-stock-etf.html` 已到 2225 行，超過 repo 2000 行硬上限；現在 HTML 是 341 行，
主要 JS 移到 `tab-stock-etf.js`，1883 行。

Verification 已過：`node --check`、HTML inline parser、Full Stock/ETF
FastAPI/static `77 passed`、`git diff --check`。

這只是維護性拆檔：沒有新增 endpoint、沒有 IBKR contact、沒有 secret、沒有
connector runtime、沒有 paper order、沒有 DB apply、沒有 Linux runtime sync/restart，
也沒有改動 Bybit live execution 行為。
