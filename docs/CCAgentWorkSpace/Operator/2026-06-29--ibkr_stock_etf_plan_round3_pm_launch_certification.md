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

## 2026-06-30 Operator Update — Disable Cleanup Status

本 session 已完成下一個 source-only checkpoint：`disable-cleanup-status`。

你現在會在 Stock/ETF GUI 看到新的 `Disable Cleanup` 指標與
`Disable / Cleanup Status` 面板；後端是
`GET /api/v1/stock-etf/disable-cleanup-status`，Rust IPC 是
`stock_etf.get_disable_cleanup_status`。

這只是顯示 kill-switch / disable-cleanup runbook 的 source-ready shape 與
runtime-blocked 狀態；不是 collector stop、不是 GUI hide、不是 secret absence
proof 執行、不是 archive、不是 DB cleanup、不是 Phase 5 start，也不是
paper/shadow launch。

Verification 已過：

- Full Stock/ETF FastAPI/static：`81 passed`
- Engine Stock/ETF：`19 passed`
- Node check：`tab-stock-etf.js` + `tab-stock-etf-disable-cleanup.js` PASS
- HTML inline parser：PASS
- GUI line caps：359 / 1895 / 132

邊界不變：沒有 IBKR contact、沒有 secret access/creation、沒有 connector runtime、
沒有 paper order、沒有 fill import、沒有 evidence clock、沒有 scorecard writer、
沒有 DB apply/cleanup、沒有 Linux runtime sync/restart，也沒有改動 Bybit live
execution 行為。

## 2026-06-30 Operator Update — Release Packet Status

本 session 已完成下一個 source-only checkpoint：`release-packet-status`。

你現在會在 Stock/ETF GUI 看到新的 `Release Packet` 指標與
`Release Packet Status` 面板；後端是
`GET /api/v1/stock-etf/release-packet-status`，Rust IPC 是
`stock_etf.get_release_packet_status`。

這只是顯示 `stock_etf_release_packet_v1` 的 source fixture 與 disable-cleanup proof
摘要；不是 release packet 物化、不是 Phase 5 start、不是 paper/shadow launch、
不是 connector runtime，也不是任何 order/write path。

Verification 已過：

- Full Stock/ETF FastAPI/static：`85 passed`
- Engine Stock/ETF：`20 passed`
- Full openclaw_types：PASS
- Workspace `cargo check`：PASS
- Node check：`tab-stock-etf.js` + `tab-stock-etf-release-packet.js` +
  `tab-stock-etf-disable-cleanup.js` PASS

邊界不變：沒有 IBKR contact、沒有 secret access/creation、沒有 connector runtime、
沒有 paper order、沒有 fill import、沒有 evidence clock、沒有 scorecard writer、
沒有 DB apply、沒有 Linux runtime sync/restart，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — Phase 0 Packet Status

本 session 已完成下一個 source-only checkpoint：`phase0-status`。

你現在會在 Stock/ETF GUI 看到新的 `Phase 0 Packet` 指標與
`Phase 0 Packet Status` 面板；後端是
`GET /api/v1/stock-etf/phase0-status`，Rust IPC 是
`stock_etf.get_phase0_status`。

這只是顯示 `stock_etf_phase0_contract_packet_manifest_v1` 的 accepted source
manifest、contract count、API baseline、global denials 與 phase unlock posture；
不是 Phase 1+ 啟動、不是 release packet 物化、不是 paper/shadow launch、不是
connector runtime，也不是任何 order/write path。

Verification 已過：

- Full Stock/ETF FastAPI/static：`89 passed`
- Engine Stock/ETF：`21 passed`
- Full openclaw_types：`35` unit/golden + `206` integration/acceptance + `0` doc-tests
- Workspace `cargo check`：PASS
- Node check：`tab-stock-etf.js` + `tab-stock-etf-phase0.js` +
  `tab-stock-etf-release-packet.js` + `tab-stock-etf-disable-cleanup.js` PASS

邊界不變：沒有 IBKR contact、沒有 secret access/creation、沒有 connector runtime、
沒有 Phase 1/2/3/4/5 runtime start、沒有 paper order、沒有 fill import、沒有
evidence clock、沒有 scorecard writer、沒有 DB apply、沒有 Linux runtime sync/restart，
也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — DB Evidence DDL Source Audit

本 session 已完成下一個 source-only checkpoint：
`stock_etf_db_evidence_ddl_v1.source_only.sql` auditor hardening。

這次不是 DB 部署。新增的是 Rust source auditor，會檢查 DDL draft 是否仍是
source-only、是否明確禁止 migration/apply、是否包含 required schemas/tables、
Guard A、欄位宣告、natural keys、stock/IBKR/paper checks、live denial、
synthetic shadow fill separation、raw artifact hash、append-only audit posture 與
hot-path indexes。

Verification 已過：

- Focused source SQL audit：`2 passed`
- DB evidence DDL acceptance：`9 passed`
- Full openclaw_types：`35` unit/golden + `207` integration/acceptance + `0` doc-tests
- Workspace `cargo check`：PASS

邊界不變：沒有 DB migration/apply、沒有 Postgres dry-run、沒有 IBKR contact、
沒有 secret access/creation、沒有 connector runtime、沒有 Phase 1/2/3/4/5 runtime
start、沒有 paper order、沒有 fill import、沒有 evidence clock、沒有 scorecard
writer、沒有 Linux runtime sync/restart，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — DB Evidence DDL Source Contract Hardening

本 session 已完成下一個 source-only checkpoint：
DB evidence DDL source contract hardening。

這次仍不是 DB 部署。變更只在 source draft 與 Rust auditor：

- DDL draft 現在有 Guard B type checks 與 Guard C index drift checks。
- DDL draft 補上 instrument/order/fill/commission/shadow lineage FKs。
- Scorecard source table 補 cost model、market-data provenance、corporate actions、
  FX/cash ledger、paper-vs-shadow reconciliation hashes。
- Hypertable/retention 只新增 promotion plan；未來要進 V### migration 前，還要先把
  primary/unique constraints 改成 Timescale partition-safe。

Verification 已過：

- DB evidence DDL acceptance：`10 passed`
- Full openclaw_types：`35` unit/golden + `208` integration/acceptance + `0` doc-tests
- Workspace `cargo check`：PASS

邊界不變：沒有 DB migration/apply、沒有 Postgres dry-run、沒有 sqlx migration
registration、沒有 IBKR contact、沒有 secret access/creation、沒有 connector runtime、
沒有 Phase 1/2/3/4/5 runtime start、沒有 paper order、沒有 fill import、沒有
evidence clock、沒有 scorecard writer、沒有 Linux runtime sync/restart，也沒有改動
Bybit live execution 行為。

## 2026-06-30 Operator Update — Paper IPC Request Shape Hardening

本 session 已完成下一個 source-only checkpoint：
paper IPC request shape hardening。

這次不是 paper order runtime。變更只在 Rust `lane_scoped_ipc_v1` contract 與
acceptance tests：

- Preview/submit 現在要求完整 order intent 欄位：symbol、instrument kind、side、
  order type、quantity、`limit_price_policy`、time in force、account/instrument hashes。
- Submit 另要求 `order_local_id`、idempotency、session/scoped authorization、
  guardian、risk、lifecycle、capability、audit 欄位。
- Cancel 只走撤單 envelope：`order_local_id`、`broker_order_id`、
  `cancel_reason`、idempotency、lifecycle/capability/audit。
- Replace 只走改單 envelope：replacement idempotency、replacement quantity、
  replacement limit-price policy、replacement time in force、`replace_reason`，
  加上原 order/broker ids 與 audit lineage。
- Tests 會拒絕 submit/cancel/replace 欄位混接，避免未來 runtime 把三種 request
  schema 混用。

Verification 已過：

- Lane IPC acceptance：`9 passed`
- Lane IPC + Phase0 manifest：`15 passed`
- Full openclaw_types：`35` unit/golden + `209` integration/acceptance + `0` doc-tests
- Engine Stock/ETF：`21 passed`
- Workspace `cargo check`：PASS
- `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 secret access/creation、沒有 connector runtime、
沒有 Phase 1/2/3/4/5 runtime start、沒有 paper order/cancel/replace、沒有 fill import、
沒有 DB apply、沒有 evidence clock、沒有 scorecard writer、沒有 Linux runtime
sync/restart，也沒有改動 Bybit live execution 行為。
