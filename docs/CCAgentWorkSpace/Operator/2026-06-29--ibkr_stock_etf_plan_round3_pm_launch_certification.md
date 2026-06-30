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
通過，paper/shadow 上線 scope 就完整。2026-06-30 目前 Phase 0 ADR/AMD +
named contract packet 已在 source 中落地，後續仍必須逐 gate 完成 source/runtime
hardening；這不是直接打開 IBKR connector runtime。

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

## 2026-06-30 Operator Update — Paper-Shadow Reconciliation Contract

本 session 已完成下一個 source-only checkpoint：
`stock_etf_paper_shadow_reconciliation_v1`。

這次不是 reconciliation writer、不是 fill importer、不是 shadow fill generator，
也不是 scorecard writer。變更只在 Rust contract、blocked template、Phase0 manifest/count、
reconciliation status fixture 與 FastAPI normalizer/tests：

- 新增 paper lifecycle/fill facts 與 synthetic shadow fill 之間的 typed
  reconciliation contract。
- Contract 要求 reconciliation/order/execution/commission/shadow-signal identity，
  lifecycle/event-log/paper-fill import/shadow-signal/shadow-fill/cost-model/
  market-data/divergence-threshold/paper-shadow-link/source hashes。
- Accepted shape 必須 paper fill imported、shadow fill synthetic、divergence 在 frozen
  threshold 內，且 unmatched paper/shadow fills 都是 0。
- Phase0 contract count 從 31 更新為 32，包含
  `stock_etf_paper_shadow_reconciliation_v1`。
- Reconciliation status 現在會顯示這個 contract 的 id、accepted/blockers、
  paper-shadow link hash、paper fill imported、shadow fill synthetic 與 writer/
  side-effect flags；default 仍是 blocked false。

Verification 已過：

- Reconciliation acceptance：`5 passed`
- Phase0 manifest：`6 passed`
- FastAPI Phase0/reconciliation focused：`9 passed`
- Engine reconciliation status focused：`1 passed`
- Engine Stock/ETF：`27 passed`
- Workspace `cargo check`：PASS
- `rustfmt --check` / `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 secret access/creation、沒有 connector runtime、
沒有 reconciliation writer、沒有 fill import、沒有 shadow fill generation、沒有
scorecard writer、沒有 DB apply、沒有 paper order/cancel/replace、沒有 evidence clock、
沒有 Linux runtime sync/restart，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — Reconciliation GUI Contract Display

本 session 已完成下一個 display-only checkpoint：Stock/ETF Reconciliation GUI
contract display。

這次不是 runtime reconciliation。變更是 GUI 抽檔與顯示同步：

- 新增 `tab-stock-etf-reconciliation.js`，主 `tab-stock-etf.js` 從 1951 行降到
  1847 行，低於 2000 行硬上限。
- Reconciliation panel 現在會顯示
  `stock_etf_paper_shadow_reconciliation_v1` 的 expected/actual contract id、
  accepted/blockers、paper-shadow link hash、paper fill imported、shadow fill synthetic，
  以及 writer / IBKR contact / connector / secret / fill import / shadow-fill side-effect
  flags。
- 新檔已納入 static route contract test 與 Stock/ETF no-write static guard。

Verification 已過：

- Node syntax：PASS
- GUI line counts：396 / 1847 / 177 / 149 / 138 / 132
- Focused route/static/no-write：`13 passed`
- Full Stock/ETF Python route/static：`90 passed`

邊界不變：沒有 IBKR contact、沒有 secret access/creation、沒有 connector runtime、
沒有 reconciliation writer、沒有 fill import、沒有 shadow fill generation、沒有
scorecard writer、沒有 DB apply、沒有 paper order/cancel/replace、沒有 evidence clock、
沒有 Linux runtime sync/restart，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — Shadow Signal Request Contract + IPC Binding

本 session 已完成下一個 source-only checkpoint：
`stock_etf_shadow_signal_request_v1`，並把 `stock_etf.evaluate_shadow_signal`
綁到這個 typed request。

這次不是 shadow collector，也不是 signal emission。變更只在 Rust contract、blocked
template、Phase0 manifest/count、IPC handler verdict 與 tests：

- 新增 future shadow signal evaluation 的 typed request contract。
- Contract 要求 `shadow` environment、`shadow_only` authority、signal/evaluation ids，
  以及 evidence clock、PIT universe、strategy hypothesis、instrument identity、
  market-data provenance、cost model、asset-lane event、source artifact hashes。
- IBKR contact、connector runtime、secret serialization、shadow signal emitted、
  shadow fill generated、scorecard writer、DB apply、order routing、Bybit path reuse 都會被拒絕。
- `stock_etf.evaluate_shadow_signal` response 現在會包含 `shadow_signal_request`
  verdict；minimal/stale params 會 fail closed。
- Phase0 contract count 現在是 31。

Verification 已過：

- Shadow signal request acceptance：`5 passed`
- Phase0 manifest：`6 passed`
- FastAPI Phase0 route：`4 passed`
- FastAPI StockETF focused：`14 passed`
- Engine shadow-signal IPC focused：`2 passed`
- Engine Stock/ETF：`27 passed`
- Workspace `cargo check`：PASS
- `rustfmt --check` / `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 secret access/creation、沒有 connector runtime、
沒有 shadow collector、沒有 shadow signal emission、沒有 shadow fill generation、
沒有 Phase 1/2/3/4/5 runtime start、沒有 fill import、沒有 DB apply、沒有 paper
order/cancel/replace、沒有 evidence clock、沒有 scorecard writer、沒有 Linux runtime
sync/restart，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — Paper Fill Import IPC Binding

本 session 已完成下一個 source-only checkpoint：
`stock_etf.import_paper_fills` typed IPC binding。

這次仍不是 fill importer，也不是 DB persistence。變更只在 Rust IPC handler 與
engine tests：

- `stock_etf.import_paper_fills` 現在會嘗試解析 params 為
  `stock_etf_paper_fill_import_request_v1`。
- Response 會回傳 `fill_import_request` verdict：parse status、expected/request
  method、IPC method match、validator blockers、read-only authority posture、lineage
  fields、side-effect boundary flags。
- Minimal/stale params 會顯示 `fill_import_request_parse_failed`。
- Valid fill-import request 可以通過 typed validator，但仍是 no-runtime fixture；
  不會匯入 fill、不寫 DB、不碰 IBKR、不碰 secret，也不重用 Bybit path。

Verification 已過：

- Engine fill-import IPC focused：`2 passed`
- Fill import request acceptance：`6 passed`
- Engine Stock/ETF：`25 passed`
- Workspace `cargo check`：PASS
- Rust format check / `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 secret access/creation、沒有 connector runtime、
沒有 lifecycle writer、沒有 Phase 1/2/3/4/5 runtime start、沒有 fill import、沒有
DB apply、沒有 paper order/cancel/replace、沒有 evidence clock、沒有 scorecard
writer、沒有 Linux runtime sync/restart，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — Paper Lifecycle State Machine

本 session 已完成下一個 source-only checkpoint：
`ibkr_paper_order_lifecycle_v1` / `broker_lifecycle_event_log_v1`
state-machine contract hardening。

這次不是 paper order runtime，也不是 lifecycle writer。變更只在 Rust contract、
tests、blocked template 與 Phase0 spec：

- Lifecycle event 現在要帶 event sequence、genesis marker、previous event hash、
  event hash、request contract id、request envelope hash 與 stale-state policy。
- Non-genesis event 必須接上 previous event hash；genesis event 必須 sequence `1`
  且 previous hash empty。
- Lifecycle event 必須是 exact paper environment。
- Submit / cancel / replace / fill-import 各自只能覆蓋自己的 state transition；
  不能用 submit 冒充 fill，也不能用 replace 冒充 fill/cancel。
- Denied event 不能把 order 推進 active broker state。
- `STATE_UNKNOWN` recovery 要分清 manual review 與 terminal reconciliation。

Verification 已過：

- Lifecycle acceptance：`12 passed`
- Linked acceptance：`12 + 8 + 9 + 6 passed`
- Engine Stock/ETF：`21 passed`
- Full openclaw_types：`35` unit/golden + `221` integration/acceptance + `0` doc-tests
- Workspace `cargo check`：PASS
- `rustfmt --check` / `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 secret access/creation、沒有 connector runtime、
沒有 lifecycle writer、沒有 Phase 1/2/3/4/5 runtime start、沒有 paper order/cancel/
replace、沒有 fill import、沒有 DB apply、沒有 evidence clock、沒有 scorecard
writer、沒有 Linux runtime sync/restart，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — Paper Status Lifecycle Surface

本 session 已完成下一個 source-only checkpoint：paper-status lifecycle surface
hardening。

這次不是 paper order runtime，也不是 lifecycle writer。你現在在 Stock/ETF GUI 的
paper lifecycle panel 會看到更完整的 state-machine 狀態：

- request contract id
- event sequence / genesis marker
- previous/event hash presence
- request-envelope hash presence
- stale-state policy
- event hash chain / request-envelope reconstructability

後端也已同步：Rust `stock_etf.get_paper_status`、FastAPI normalizer、route tests 與
GUI fallback 都採用同一個 blocked/default shape。缺少新 lifecycle 欄位的舊 payload
會被擋成 `contract_violation_blocked`，不會被當成可下單狀態。

Verification 已過：

- Focused paper-status FastAPI：`6 passed`
- Wider Stock/ETF FastAPI/static：`19 passed`
- JS syntax：PASS
- Engine `stock_etf_paper_status` focused：PASS
- Engine Stock/ETF：`21 passed`
- Workspace `cargo check`：PASS

邊界不變：沒有 IBKR contact、沒有 secret access/creation、沒有 connector runtime、
沒有 lifecycle writer、沒有 Phase 1/2/3/4/5 runtime start、沒有 paper order/cancel/
replace、沒有 fill import、沒有 DB apply、沒有 evidence clock、沒有 scorecard
writer、沒有 Linux runtime sync/restart，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — Paper IPC Request Envelope Binding

本 session 已完成下一個 source-only checkpoint：paper IPC request envelope binding。

這次不是 paper order runtime。變更只在 Rust `stock_etf.preview/submit/cancel/
replace_paper_order` fixture：

- IPC handler 現在會嘗試解析 params 為 `stock_etf_paper_order_request_v1` envelope。
- Response 會回傳 `request_envelope` verdict：parse status、expected/request method、
  IPC method match、validator blockers、authority/effect posture、lineage fields、
  side-effect boundary flags。
- 舊的 minimal/stale params 會顯示 `request_envelope_parse_failed`，但仍不需要
  Bybit paper command channel，也不會觸碰 IBKR。
- Valid preview envelope 可以通過 typed validator，但仍是 no-runtime fixture。
- Valid submit envelope 若送到 cancel IPC method，會被擋成 `ipc_method_mismatch`。

Verification 已過：

- Engine Stock/ETF：`23 passed`
- Paper request acceptance：`8 passed`
- Workspace `cargo check`：PASS
- Rust format check：PASS

邊界不變：沒有 IBKR contact、沒有 secret access/creation、沒有 connector runtime、
沒有 lifecycle writer、沒有 Phase 1/2/3/4/5 runtime start、沒有 paper order/cancel/
replace、沒有 fill import、沒有 DB apply、沒有 evidence clock、沒有 scorecard
writer、沒有 Linux runtime sync/restart，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — Paper Fill Import Request Contract

本 session 已完成下一個 source-only checkpoint：
`stock_etf_paper_fill_import_request_v1`。

這次不是 fill importer，也不是 DB persistence。變更只在 Rust contract、blocked
template、Phase0 manifest/count 與 tests：

- 新增 future `stock_etf.import_paper_fills` 的 typed request contract。
- Contract 要求 read-only fill-import posture、session/lifecycle/event-log/redaction
  hashes、broker order/execution/commission ids、import idempotency、observed order
  state、stale-state policy、raw/redacted artifact hashes。
- Duplicate import、沒有 stale-state policy 的 unknown state、IBKR contact、connector
  runtime、secret serialization、fill import side effect、DB apply、Bybit path reuse 都會被拒絕。
- Phase0 contract count 現在是 30。

Verification 已過：

- Fill import request acceptance：`6 passed`
- Phase0 manifest：`6 passed`
- FastAPI Phase0/StockETF focused：`14 passed`
- Full openclaw_types：`35 + 227 + 0 doc-tests`
- Engine Stock/ETF：`23 passed`
- Workspace `cargo check`：PASS

邊界不變：沒有 IBKR contact、沒有 secret access/creation、沒有 connector runtime、
沒有 lifecycle writer、沒有 Phase 1/2/3/4/5 runtime start、沒有 fill import、沒有
DB apply、沒有 paper order/cancel/replace、沒有 evidence clock、沒有 scorecard
writer、沒有 Linux runtime sync/restart，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — Paper Request Envelope Contract

本 session 已完成下一個 source-only checkpoint：
`stock_etf_paper_order_request_v1` typed request envelope。

這次不是 paper order runtime。變更只在 Rust contract、tests、Phase0 manifest 與
顯示面 count：

- 新增 typed envelope，放在 lane-scoped IPC 和 IBKR paper lifecycle 之間。
- Preview/submit 會檢查 symbol、stock/ETF instrument kind、side、market/limit
  order type、positive decimal quantity、explicit limit-price policy、time in force。
- Submit 要求 session/scoped authorization、Decision Lease、Guardian、risk、
  instrument、lifecycle、capability、audit lineage，以及 local order/idempotency。
- Cancel 要求 local order id、broker order id、cancel reason、idempotency，並拒絕
  submit order-shape pollution。
- Replace 要求 replacement idempotency/quantity/limit-price-policy/time-in-force、
  replace reason，並拒絕 original mutable fields pollution。
- Phase0 contract count 從 28 更新為 29，包含
  `stock_etf_paper_order_request_v1`；FastAPI normalizer/tests 同步。

Verification 已過：

- Paper request acceptance：`8 passed`
- Phase0 manifest：`6 passed`
- Lane IPC：`9 passed`
- FastAPI Phase0/StockETF focused：`14 passed`
- Engine Stock/ETF：`21 passed`
- Full openclaw_types：`35` unit/golden + `217` integration/acceptance + `0` doc-tests
- Workspace `cargo check`：PASS
- `rustfmt --check` / `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 secret access/creation、沒有 connector runtime、
沒有 Phase 1/2/3/4/5 runtime start、沒有 paper order/cancel/replace、沒有 fill import、
沒有 DB apply、沒有 evidence clock、沒有 scorecard writer、沒有 Linux runtime
sync/restart，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — Scorecard Reconciliation Lineage Gate

本 session 已完成下一個 source/status/display-only checkpoint：
scorecard reconciliation lineage gate。

這次不是 scorecard writer，也不是 reconciliation runtime。變更只在 Rust scorecard
contract、blocked template、read-only scorecard status、FastAPI normalizer/tests 與 GUI：

- `stock_etf_scorecard_verdict_v1` 現在必須帶
  `paper_shadow_reconciliation_hash`，否則 validator 會 fail closed。
- `/api/v1/stock-etf/scorecard-status` 會顯示
  `paper_shadow_reconciliation_hash_present=false`。
- 如果 pre-gate payload 宣稱該 hash present，FastAPI 會以
  `contract_violation_blocked` 阻擋。
- GUI scorecard panel 會顯示這個 gate，避免將 scorecard readiness 和
  paper-vs-shadow reconciliation 脫鉤。

Verification 已過：

- Scorecard verdict acceptance：`8 passed`
- Focused FastAPI/static：`15 passed`
- Full Stock/ETF FastAPI/static：`90 passed`
- Engine Stock/ETF：`27 passed`
- Full openclaw_types：`35` unit/golden + `236` integration/acceptance + `0` doc-tests
- Workspace `cargo check`：PASS
- `rustfmt --check` / `node --check`：PASS

邊界不變：沒有 IBKR contact、沒有 secret access/creation、沒有 connector runtime、
沒有 Phase 1/2/3/4/5 runtime start、沒有 paper order/cancel/replace、沒有 fill import、
沒有 shadow fill generation、沒有 reconciliation writer、沒有 DB apply、沒有 evidence
clock、沒有 scorecard writer、沒有 Linux runtime sync/restart，也沒有改動 Bybit live
execution 行為。

## 2026-06-30 Operator Update — Read-Only Probe IPC Binding

本 session 已完成下一個 source-only checkpoint：
`stock_etf.preview_readonly_probe`。

這次不是 IBKR read probe，也不是 connector runtime。變更只在 Rust IPC contract、
method registry、dispatch、handler/test 與 source spec/template：

- `stock_etf.preview_readonly_probe` 會把 params 解析成
  `stock_etf_ibkr_readonly_probe_request_v1`，回傳 typed verdict。
- valid envelope 只能證明 request shape 可接受；top-level `allowed` 仍因 Phase 2
  gate/default flags 維持 false。
- minimal/空 params 會 fail closed：`readonly_probe_request_parse_failed`。
- `lane_scoped_ipc_v1` 現在要求這個 method 是 readonly/slot-none，並帶 Phase 2
  gate、API allowlist、secret-slot/topology/session、redaction/rate-limit/audit
  lineage。

Verification 已過：

- Rust format：PASS
- Lane-scoped IPC acceptance：`9 passed`
- Readonly-probe IPC focused：`2 passed`
- Registry boundary focused：`1 passed`
- Full openclaw_types：`35` unit/golden + `247` integration/acceptance + `0` doc-tests
- Engine Stock/ETF：`29 passed`
- Workspace `cargo check`：PASS
- `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 secret access/creation、沒有 connector runtime、
沒有 IBKR SDK import、沒有 socket/HTTP、沒有 read probe execution、沒有 Phase
1/2/3/4/5 runtime start、沒有 paper order/cancel/replace、沒有 fill import、沒有 DB
apply、沒有 evidence clock、沒有 scorecard writer、沒有 Linux runtime sync/restart，
也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — Tiny-Live Eligibility Lineage Gate

本 session 已完成下一個 source/status/display-only checkpoint：
`tiny_live_adr_eligibility_v1` lineage gate。

這次不是 tiny-live approval，也不是 live approval。變更只在 Rust contract、blocked
template、read-only launch status、FastAPI normalizer/tests 與 GUI：

- 未來若要進入 ADR tiny-live 討論，eligibility artifact 必須帶 scorecard derivation、
  scorecard verdict、scorecard manifest、paper-shadow reconciliation、DQ/statistical
  preregistration、QC/MIT/QA review hashes。
- QA review 現在也是 hard gate：缺 `qa_review_hash` 或 `qa_review_passed=false`
  都會 fail closed。
- `/api/v1/stock-etf/launch-status` 和 GUI launch panel 現在顯示 blocked
  lineage-present booleans。
- 如果 pre-gate payload 宣稱 derivation/verdict/reconciliation/QA lineage present，
  或宣稱 QA review passed，FastAPI 會以 `contract_violation_blocked` 擋下。

Verification 已過：

- Tiny-live eligibility acceptance：`7 passed`
- Python compile：PASS
- Focused FastAPI/static：`15 passed`
- Full Stock/ETF FastAPI/static：`90 passed`
- Engine launch-status focused：`1 passed`
- Engine Stock/ETF：`27 passed`
- Full openclaw_types：`35` unit/golden + `241` integration/acceptance + `0` doc-tests
- Workspace `cargo check`：PASS
- `rustfmt --check` / `node --check` / `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 secret access/creation、沒有 connector runtime、
沒有 Phase 1/2/3/4/5 runtime start、沒有 paper order/cancel/replace、沒有 fill import、
沒有 shadow fill generation、沒有 reconciliation writer、沒有 DB apply、沒有 evidence
clock、沒有 scorecard writer、沒有 Linux runtime sync/restart，沒有 tiny-live/live
authority，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — IBKR Read-Only Connector Skeleton Boundary

本 session 已完成下一個 source-only checkpoint：
`program_code/broker_connectors/ibkr_connector/`。

這次不是 IBKR connector runtime。新增的是隔離 package 和測試邊界：

- package 不在既有 Bybit connector tree 下。
- 不導入 `ibapi` / `ib_insync`。
- 不開 socket/HTTP、不讀 secret、不接 broker。
- 不提供 order/cancel/replace/write method。
- 只回傳 blocked readiness / preview payload，供後續 read-only/paper gate 實作前先
  固定 Python 邊界。
- 既有 no-write static guard 現在會掃描這個實際 package。

Verification 已過：

- Python compile：PASS
- Connector skeleton + no-write static guard：`7 passed`
- Full Stock/ETF FastAPI/static：`94 passed`

邊界不變：沒有 IBKR contact、沒有 secret access/creation、沒有 connector runtime、
沒有 IBKR SDK import、沒有 Phase 1/2/3/4/5 runtime start、沒有 paper
order/cancel/replace、沒有 fill import、沒有 DB apply、沒有 evidence clock、沒有
scorecard writer、沒有 Linux runtime sync/restart，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — Connector Skeleton Readiness Gate

本 session 已把 IBKR connector skeleton 的 blocked boundary 顯示到
`/api/v1/stock-etf/readiness` 和 GUI readiness panel。

這次不是 connector runtime：

- GUI 現在會顯示 connector skeleton surface/status。
- network contact、secret loaded、paper/live channel、write method、Bybit path reuse
  都會顯示為 false。
- 如果 pre-gate payload 宣稱任何上述 flag 為 true，FastAPI 會
  `contract_violation_blocked`。

Verification 已過：

- Python compile：PASS
- Focused readiness/no-write：`9 passed`
- Full Stock/ETF FastAPI/static：`94 passed`
- `node --check` / `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 secret access/creation、沒有 connector runtime、
沒有 IBKR SDK import、沒有 Phase 1/2/3/4/5 runtime start、沒有 paper
order/cancel/replace、沒有 fill import、沒有 DB apply、沒有 evidence clock、沒有
scorecard writer、沒有 Linux runtime sync/restart，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — ADR/Register Lineage Catch-up

本 session 已完成 governance catch-up：

- `SPECIFICATION_REGISTER.md` 已登記最新 tiny-live lineage gate。
- ADR-0048 已補明：future tiny-live discussion 必須帶 scorecard derivation、
  verdict、manifest、paper-shadow reconciliation、DQ/preregistration、QC/MIT/QA
  lineage。
- ADR-0048 已補明：`program_code/broker_connectors/ibkr_connector/` 現在只是
  inert source-only skeleton，不是 runtime connector。
- AMD-2026-06-29-01 也同步補上同樣邊界。

Verification 已過：

- Register/ADR/AMD `rg` check：PASS
- `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 secret access/creation、沒有 connector runtime、
沒有 IBKR SDK import、沒有 Phase 1/2/3/4/5 runtime start、沒有 paper
order/cancel/replace、沒有 fill import、沒有 DB apply、沒有 evidence clock、沒有
scorecard writer、沒有 Linux runtime sync/restart，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — Scorecard Derivation Contract

本 session 已完成下一個 source/status/display-only checkpoint：
`stock_etf_scorecard_derivation_v1`。

這次不是 scorecard writer，也不是 DB persistence。變更只在 Rust contract、blocked
template、read-only scorecard status、FastAPI normalizer/tests 與 GUI：

- Derivation contract 要求 input bundle、paper-shadow reconciliation、verdict、
  formula/preregistration、output artifact、QC/MIT/QA review hashes。
- Contract 要求 derived-only、idempotent replay、paper/shadow fill separation、
  Bybit live unchanged、sealed。
- IBKR contact、connector runtime、fill import、shadow fill generation、
  reconciliation writer、scorecard writer、DB apply、evidence clock、secret
  serialization、tiny-live/live authority 都會被拒絕。
- `/api/v1/stock-etf/scorecard-status` 和 GUI 現在顯示 blocked
  `scorecard_derivation` block；pre-gate truthy derivation claims 會被
  `contract_violation_blocked` 擋下。

Verification 已過：

- Scorecard derivation acceptance：`5 passed`
- Python compile：PASS
- Focused FastAPI/static：`15 passed`
- Full Stock/ETF FastAPI/static：`90 passed`
- Engine scorecard focused：`1 passed`
- Engine Stock/ETF：`27 passed`
- Full openclaw_types：`35` unit/golden + `241` integration/acceptance + `0` doc-tests
- Workspace `cargo check`：PASS
- `rustfmt --check` / `node --check`：PASS

邊界不變：沒有 IBKR contact、沒有 secret access/creation、沒有 connector runtime、
沒有 Phase 1/2/3/4/5 runtime start、沒有 paper order/cancel/replace、沒有 fill import、
沒有 shadow fill generation、沒有 reconciliation writer、沒有 DB apply、沒有 evidence
clock、沒有 scorecard writer、沒有 Linux runtime sync/restart，也沒有改動 Bybit live
execution 行為。

## 2026-06-30 Operator Update — Broker Read Capability Probe Gate

本 session 已完成 source-only hardening：`broker_capability_registry_v1` 的四個
read rows 不再只靠外部 gate / operation-specific gate。

新增邊界：

- `health_read`
- `account_snapshot_read`
- `market_data_read`
- `contract_details_read`

上述 read rows 現在必須同時要求 `lane_scoped_ipc_v1` 和
`stock_etf_ibkr_readonly_probe_request_v1`，再加上原有 session/provenance/
instrument identity 等 per-operation gates，才會通過 registry validator。

這次不是 read probe execution、不是 IBKR connector、不是 first contact。它只是把
broker capability registry 綁到前面已完成的 typed IPC / readonly-probe request
邊界，避免未來只看 capability row 就繞過 typed request。

Verification 已過：

- `rustfmt`：PASS
- Broker capability acceptance：`10 passed`
- Full openclaw_types：`35` unit/golden + `248` integration/acceptance + `0`
  doc-tests
- Workspace `cargo check`：PASS
- `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret
access/creation、沒有 connector runtime、沒有 read probe execution、沒有 paper
order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有 DB apply、沒有
evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — Policy Status Read-Row Gate Display

本 session 已把上一個 broker read capability hardening 顯示到
`/api/v1/stock-etf/policy-status` 和 Stock/ETF GUI policy panel。

新增顯示/檢查：

- `registry.lane_scoped_ipc_contract_id`
- `registry.readonly_probe_request_contract_id`
- `registry.read_rows_require_lane_scoped_ipc`
- `registry.read_rows_require_readonly_probe_request`

如果未來 IPC payload 宣稱 `broker_capability_registry.accepted=true`，但沒有證明 read
rows 要求 lane-scoped IPC 和 readonly-probe request，FastAPI 會降成
`contract_violation_blocked`，並列出明確 violation。

Verification 已過：

- Python compile：PASS
- Node syntax：PASS
- Focused policy/static：`15 passed`
- Engine policy-status focused：`1 passed`
- Full Stock/ETF FastAPI/static：`94 passed`
- Engine Stock/ETF filter：`29 passed`
- Workspace `cargo check`：PASS
- `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret
access/creation、沒有 connector runtime、沒有 read probe execution、沒有 paper
order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有 DB apply、沒有
evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — Read-Only Probe Request Operation Binding

本 session 已修正 `stock_etf.preview_readonly_probe` 的 source semantics：

- valid `stock_etf_ibkr_readonly_probe_request_v1` envelope 會決定 top-level
  broker decision operation。
- `market_data_snapshot` 這類 request 現在會顯示
  `decision.operation=market_data_read`，不再只繼承 method fallback 的
  `health_read`。
- invalid / parse-failed payload 不會被信任；仍然 fallback 到 method-level
  fail-closed fixture boundary。

這次不是 read probe execution、不是 IBKR contact、不是 connector runtime。

Verification 已過：

- `rustfmt`：PASS
- Readonly-probe IPC focused：`3 passed`
- Engine Stock/ETF filter：`30 passed`
- Workspace `cargo check`：PASS
- `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret
access/creation、沒有 connector runtime、沒有 read probe execution、沒有 paper
order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有 DB apply、沒有
evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。
