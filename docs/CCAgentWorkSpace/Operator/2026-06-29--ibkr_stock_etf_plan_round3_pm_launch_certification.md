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

## 2026-07-01 Operator Update — Scorecard Input Result-Import Lineage Guard

本 session 已把 readonly probe result-import request lineage 接入
Stock/ETF scorecard input 與 scorecard status display surface：

- `StockEtfScorecardInputBundleV1` 現在要求
  `stock_etf_ibkr_readonly_probe_result_import_request_v1` contract id 與 64-hex
  result-import request hash。
- Scorecard input blocked template 仍不帶 hash、不導入 broker result、不啟動
  writer；accepted fixture 才能帶完整 lineage。
- Rust IPC `stock_etf.get_scorecard_status` 現在顯示 default-blocked
  `scorecard_input_bundle` 摘要，只輸出 hash-present boolean。
- FastAPI scorecard status normalizer/GUI 會 fail-closed 顯示 input bundle lineage，
  並拒絕 accepted/hash-present/writer/DB/IBKR/Bybit reuse side-effect claims。

Verification 已過：

- Python changed files `py_compile`：PASS
- Stock/ETF JS syntax：PASS
- Scoped Rust rustfmt：PASS
- Focused Rust scorecard input acceptance：PASS
- Focused engine scorecard IPC fixture：PASS
- Focused FastAPI scorecard/static pytest：PASS
- Full Stock/ETF FastAPI/static pytest：PASS
- Docs trace guard：PASS

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 GUI fanout、沒有 IBKR
contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有
connector runtime、沒有 read probe execution、沒有 result import、沒有 collector、
沒有 market-data ingestion、沒有 DQ writer、沒有 evidence writer、沒有 DB apply、
沒有 evidence clock、沒有 scorecard writer、沒有 paper order/cancel/replace、沒有
tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — Scorecard Fallback Input Lineage Guard

本 session 已把 scorecard input bundle result-import lineage 補進 browser-side
fallback：

- `scorecardFallback()` 現在包含 default-degraded `scorecard_input_bundle`。
- Fallback 固定顯示
  `stock_etf_ibkr_readonly_probe_result_import_request_v1` contract id，且
  result-import hash-present、market/reference/risk/atomic/source lineage flags 與所有
  side-effect flags 均為 false。
- Static no-write/split guard 已鎖住 fallback payload 不可再漏掉
  `scorecard_input_bundle` 與 readonly probe result-import request lineage 欄位。

Verification 已過：

- Python changed files `py_compile`：PASS
- Stock/ETF JS syntax：PASS
- Focused fallback/static/docs trace pytest：PASS
- Full Stock/ETF FastAPI/static pytest：PASS
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 GUI fanout、沒有 IBKR
contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有
connector runtime、沒有 read probe execution、沒有 result import、沒有 DB/evidence/
scorecard writer、沒有 paper order/cancel/replace、沒有 tiny-live/live authority，也
沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — Scorecard Status Module Split Guard

本 session 已拆分 Rust scorecard status source fixture：

- `scorecard_status_summary` 從
  `rust/openclaw_engine/src/ipc_server/handlers/stock_etf/status_summaries.rs`
  移到 `status_summaries/scorecard.rs`。
- 父檔保留 thin wrapper，因此既有 `stock_etf.get_scorecard_status` IPC surface 與
  payload shape 不變。
- `status_summaries.rs` 從 1006 行降到 785 行，新 scorecard 子模組 228 行。

Verification 已過：

- Scoped Rust rustfmt：PASS
- Focused engine scorecard IPC fixture：PASS
- Engine Stock/ETF IPC regression：`29 passed`
- Docs trace guard：PASS
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 payload 行為改動、沒有 IBKR
contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有
connector runtime、沒有 read probe execution、沒有 result import、沒有 DB/evidence/
scorecard writer、沒有 paper order/cancel/replace、沒有 tiny-live/live authority，也
沒有改動 Bybit live execution 行為。

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

## 2026-06-30 Operator Update — Plan Timeline Checkpoint Guard

本 session 已完成主計畫治理清理：

- 主開發安排內的 PM session checkpoints 已重排為 14 到 82 連續遞增，消除重複與倒序。
- 23-41 區塊按 PM memory / Operator 實際 source timeline 排列；section-body 對比確認
  沒有丟失 checkpoint 正文。
- 新增 structure test，防止 IBKR 主計畫 checkpoint 編號再次重複或倒序。

Verification 已過：

- IBKR timeline focused structure test：`1 passed`
- Section-body compare against `HEAD`：PASS
- `git diff --check`：PASS

註：完整 `tests/structure/test_docs_readme_index_static.py` 仍有既有 docs README index drift
失敗；這不是本次 IBKR timeline guard 新增造成。

邊界不變：沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret
access/creation、沒有 connector runtime、沒有 read probe execution、沒有 paper
order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有 DB apply、沒有
evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — Python Connector Network Static Guard

本 session 已加固 Stock/ETF / IBKR Python static guard：

- `test_stock_etf_python_no_write_static_guard.py` 現在不只禁止 Python broker write
  methods、direct IBKR SDK import、非 GET route、GUI write snippets；也禁止
  Stock/ETF / IBKR Python surface 導入 socket/HTTP/WebSocket network client module。
- 禁止清單包含 `socket`、`http.client`、`requests`、`httpx`、`urllib`、`urllib3`、
  `aiohttp`、`websocket`、`websockets`。
- 同一 guard 也檢查 `__import__()` / `import_module()` 對 IBKR SDK 或 network
  module 的動態導入。
- 掃描範圍只限 Stock/ETF / IBKR Python surface 與 IBKR connector skeleton；
  不掃既有 Bybit connector，不改 Bybit 行為。

這次不是 IBKR contact、不是 connector runtime、不是 read probe，也不是 paper order。

Verification 已過：

- Python no-write static guard：`4 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret
access/creation、沒有 connector runtime、沒有 read probe execution、沒有 paper
order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有 DB apply、沒有
evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — PM Memory Traceability Backfill

本 session 已補齊 PM memory 已記錄、但主計畫與 Operator 摘要沒有明確 title trace 的
中間 checkpoint。這是審計線 backfill，不是新增 runtime 能力。

回補 title：

- `Source Posture Header Catch-up`
- `Rust Connector Skeleton Readiness Source`
- `Read-Only Probe Request Contract`
- `Read-Only Probe Readiness Gate`

Verification 已過：

- IBKR timeline + traceability focused structure tests：`2 passed`
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

## 2026-06-30 Operator Update — GUI Endpoint Template Consistency Guard

本 session 已加固 Stock/ETF GUI / FastAPI endpoint 一致性：

- 新增 `test_stock_etf_openapi_paths_match_gui_lane_contract_template`。
- FastAPI OpenAPI 暴露的 Stock/ETF GET endpoint set 必須等於
  `settings/broker/stock_etf_gui_lane_contract.template.toml` 的 `*_endpoint` set。
- 測試排除 root redirect `/api/v1/stock-etf`，因它是 authenticated redirect，不是
  GUI lane contract status endpoint。
- parser 覆蓋含數字的 key，例如 `phase0_status_endpoint`。

這次不是新增 endpoint、不是 GUI runtime activation、不是 IBKR contact、不是
connector runtime，也不是 paper order。

Verification 已過：

- Stock/ETF route tests：`11 passed`
- Full Stock/ETF FastAPI/static：`96 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret
access/creation、沒有 connector runtime、沒有 read probe execution、沒有 paper
order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有 DB apply、沒有
evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — GUI Static Endpoint Template Consistency Guard

本 session 已加固 Stock/ETF static GUI bundle 與 GUI lane contract template 的
endpoint 一致性：

- 新增 static guard：GUI bundle 中出現的 `/api/v1/stock-etf...` endpoint set
  必須精確等於 `settings/broker/stock_etf_gui_lane_contract.template.toml` 的
  `*_endpoint` set。
- 這補上 checkpoint 45 的另一半：OpenAPI ↔ template 已對齊，現在 GUI source ↔
  template 也對齊。
- guard 只掃 `tab-stock-etf*` static source，不新增 endpoint、不改 route handler、
  不啟動 GUI runtime authority。

Verification 已過：

- Python no-write static guard：`5 passed`
- Full Stock/ETF FastAPI/static：`97 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret
access/creation、沒有 connector runtime、沒有 read probe execution、沒有 paper
order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有 DB apply、沒有
evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — FastAPI Route Auth Coverage Guard

本 session 已加固 Stock/ETF FastAPI route auth coverage：

- 新增 route-level guard，從 OpenAPI 自動取得所有 Stock/ETF GET route。
- 另加入 authenticated root redirect `/api/v1/stock-etf`。
- 未登入、未 override `current_actor` 時，每條 route 都必須回 `401`。
- 這防止未來 display-only Stock/ETF endpoint 被新增時漏掉 auth dependency。

Verification 已過：

- Stock/ETF route tests：`12 passed`
- Full Stock/ETF FastAPI/static：`98 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret
access/creation、沒有 connector runtime、沒有 read probe execution、沒有 paper
order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有 DB apply、沒有
evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — FastAPI Route Cache Header Coverage Guard

本 session 已加固 Stock/ETF FastAPI route cache/auth partition：

- 新增 route-level guard，從 OpenAPI 自動取得所有 Stock/ETF GET route。
- 另加入 root redirect `/api/v1/stock-etf`。
- 每條 route 都必須帶 private/no-store cache headers，且 `Vary: Authorization`。
- 這防止未來 display-only Stock/ETF endpoint 漏掉 cache partition，造成 stale /
  cross-actor status 泄漏。

Verification 已過：

- Stock/ETF route tests：`13 passed`
- Full Stock/ETF FastAPI/static：`99 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret
access/creation、沒有 connector runtime、沒有 read probe execution、沒有 paper
order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有 DB apply、沒有
evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — FastAPI IPC Empty Params Guard

本 session 已加固 Stock/ETF FastAPI 到 Rust IPC 的 client-state-untrusted 邊界：

- 新增 AST guard，掃描 `stock_etf_routes.py` 的每個 `ipc.call(...)`。
- 每個 Stock/ETF status IPC read 都必須使用 literal `params={}`。
- 任何未來把 query params、headers、client lane claims 或非空 params 傳進 Rust IPC
  的改動都會失敗。

Verification 已過：

- Python no-write static guard：`6 passed`
- Full Stock/ETF FastAPI/static：`100 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret
access/creation、沒有 connector runtime、沒有 read probe execution、沒有 paper
order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有 DB apply、沒有
evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — FastAPI Handler Client-State Guard

本 session 已加固 Stock/ETF FastAPI route handler 的 client-state-untrusted 邊界：

- 新增 AST guard，掃描每個 `@stock_etf_router.get` handler。
- handler 只允許接收 `response` 與/或 authenticated `actor`。
- `actor` 必須以 `Depends(base.current_actor)` 注入。
- 未來若加入 Request/Header/Query/Body/Cookie/Form 類 client-state input，guard 會失敗。

Verification 已過：

- Python no-write static guard：`7 passed`
- Full Stock/ETF FastAPI/static：`101 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret
access/creation、沒有 connector runtime、沒有 read probe execution、沒有 paper
order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有 DB apply、沒有
evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — FastAPI IPC Method Allowlist Guard

本 session 已加固 Stock/ETF FastAPI 到 Rust IPC 的 method allowlist 邊界：

- 新增 AST guard，解析 `stock_etf_routes.py` 的 `_..._METHOD` constants。
- 每個 `ipc.call(...)` 必須使用 named method constant。
- resolved method set 必須精確等於 readonly Stock/ETF status/readiness IPC allowlist。
- 未來若把 paper preview/submit/cancel/replace、fill import、shadow evaluation 或
  readonly-probe preview method 接到 FastAPI GET/status surface，guard 會失敗。

Verification 已過：

- Python no-write static guard：`8 passed`
- Full Stock/ETF FastAPI/static：`102 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret
access/creation、沒有 connector runtime、沒有 read probe execution、沒有 paper
order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有 DB apply、沒有
evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — Python Persistence Static Guard

本 session 已加固 Stock/ETF / IBKR Python source surface 的 persistence/no-writer 邊界：

- 新增 AST guard，掃描 scoped Stock/ETF / IBKR Python files。
- 禁止匯入 DB/persistence/object-store modules，例如 psycopg/psycopg2/sqlalchemy/
  sqlite3/asyncpg/duckdb/redis/boto3。
- 禁止匯入 local persistence/evidence-writer modules，例如 `db_pool`、
  `audit_persistence`、`state_store`、`agent_event_store`。
- 禁止 dynamic persistence imports 與明確 file writer calls：`write_text`、
  `write_bytes`、write-mode `open(...)`、`os.replace(...)` 等。

Verification 已過：

- Python no-write static guard：`9 passed`
- Full Stock/ETF FastAPI/static：`103 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret
access/creation、沒有 connector runtime、沒有 read probe execution、沒有 paper
order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有 DB apply、沒有
evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — OpenAPI Client Input Surface Guard

本 session 已加固 Stock/ETF public OpenAPI client-input surface：

- 新增 route/OpenAPI guard，掃描所有 `/api/v1/stock-etf...` GET operations。
- 每條 OpenAPI operation 不得暴露 `requestBody`。
- parameters 只允許既有 auth 的 optional `Authorization` header。
- 未來若加入 query/path/header/cookie/body client-state inputs，guard 會失敗。

Verification 已過：

- Stock/ETF route tests：`14 passed`
- Full Stock/ETF FastAPI/static：`104 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret
access/creation、沒有 connector runtime、沒有 read probe execution、沒有 paper
order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有 DB apply、沒有
evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — Rust Status IPC Untrusted Params Guard

本 session 已加固 Rust IPC 層 Stock/ETF status/readiness method 的 params 邊界：

- 新增 Rust IPC regression，覆蓋所有 Stock/ETF status/readiness methods。
- 每個 method 用 `{}` params 與惡意非空 params 各呼叫一次。
- 惡意 params 宣稱 live、Bybit、paper submit、IBKR contact、secret touch、
  order routing、Bybit IPC reuse。
- 兩次 result 必須完全一致，證明 direct IPC caller 無法用 params 影響 status/readiness
  fixture output。

Verification 已過：

- `rustfmt`：PASS
- Focused engine test：`1 passed`
- Engine `stock_etf` filter：`31 passed`
- Full Stock/ETF FastAPI/static：`104 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret
access/creation、沒有 connector runtime、沒有 read probe execution、沒有 paper
order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有 DB apply、沒有
evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — Rust Dispatch Registry Routing Guard

本 session 已加固 Rust IPC dispatch 的 Stock/ETF routing source-of-truth：

- `dispatch.rs` 不再維護一份獨立 Stock/ETF method match list。
- 新增 registry helper `is_stock_etf_fixture_method(...)`。
- Dispatch 現在只要 method 是 registered `stock_etf.` fixture 且 `slot=None`，就路由到
  Stock/ETF handler。
- 這把 dispatch routing 綁回 `method_registry.rs` 的同一份 metadata，降低新增/改名
  Stock/ETF method 時 registry、dispatch、live-token exclusion 發生 drift 的風險。

Verification 已過：

- `rustfmt`：PASS
- Engine `stock_etf` filter：`31 passed`
- Full Stock/ETF FastAPI/static：`104 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret
access/creation、沒有 connector runtime、沒有 read probe execution、沒有 paper
order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有 DB apply、沒有
evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — GUI Data/Policy Fallback Split Guard

本 session 已降低 Stock/ETF GUI 主 bundle 的維護風險：

- 將 Data Foundation / Policy 的大型 fallback payload 從 `tab-stock-etf.js`
  拆到 `tab-stock-etf-data-policy.js`。
- `tab-stock-etf.js` 從 `1976` 行降到 `1805` 行；所有 Stock/ETF GUI bundle
  檔案都低於 2000 行 governance cap。
- HTML 在主 loader 前載入 data/policy split，既有 display-only 渲染與 endpoint
  呼叫流程不變。
- 靜態 no-write guard 現在掃描新 JS 檔，並新增 GUI bundle line-cap regression。

Verification 已過：

- Stock/ETF JS `node --check`：PASS
- Python no-write/static guard：`10 passed`
- Full Stock/ETF FastAPI/static：`105 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、
沒有 secret access/creation、沒有 connector runtime、沒有 read probe execution、沒有
paper order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有 DB apply、沒有
evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — Rust IPC Test Split Guard

本 session 已降低 Stock/ETF Rust IPC 測試檔的結構風險：

- 將尾端 Account/Reconciliation/Scorecard/Launch/Release/Disable status fixture
  tests 拆到 `rust/openclaw_engine/src/ipc_server/tests/stock_etf/status_fixtures.rs`。
- 父檔 `stock_etf.rs` 從 `2532` 行降到 `1852` 行；子檔為 `685` 行。
- 新增結構 guard，要求 Stock/ETF Rust IPC 測試父檔與子檔都低於 2000 行
  governance cap。
- Guard 同時確認拆出的 status method 字串存在，並阻止 moved fixture 檔引入 IBKR SDK
  或 socket/HTTP client token。

Verification 已過：

- `rustfmt`：PASS
- Engine `stock_etf` filter：`31 passed`
- Rust IPC split static guard：`2 passed`
- Full Stock/ETF FastAPI/static：`105 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、
沒有 secret access/creation、沒有 connector runtime、沒有 read probe execution、沒有
paper order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有 DB apply、沒有
evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — Rust IPC Handler Split Guard

本 session 已降低 Stock/ETF Rust IPC handler 檔案的結構風險：

- 將 tail status summary builders 從
  `rust/openclaw_engine/src/ipc_server/handlers/stock_etf.rs` 拆到
  `rust/openclaw_engine/src/ipc_server/handlers/stock_etf/status_summaries.rs`。
- 父檔 `stock_etf.rs` 從 `2217` 行降到 `1292` 行；子檔為 `934` 行。
- 父檔仍保留 IPC 入口、readiness/phase2 precontact 與 request envelope parsing。
- 新增 handler split guard，要求 Stock/ETF Rust IPC handler 父檔與子檔都低於
  2000 行 governance cap。
- Guard 同時確認 moved builder functions 在子模組，並阻止子模組引入 IBKR SDK
  或 socket/HTTP client token。

Verification 已過：

- `rustfmt`：PASS
- Engine `stock_etf` filter：`31 passed`
- Rust IPC handler/test split static guards：`4 passed`
- Full Stock/ETF FastAPI/static：`105 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 IBKR contact、沒有 SDK import、
沒有 socket/HTTP、沒有 secret access/creation、沒有 connector runtime、沒有 read probe
execution、沒有 paper order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有
DB apply、沒有 evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live
execution 行為。

## 2026-06-30 Operator Update — Route Fixture Split Guard

本 session 已降低 Stock/ETF FastAPI route fixture 的結構風險：

- 將 `stock_etf_route_fixtures.py` 拆成同名 package：
  `stock_etf_route_fixtures/`。
- Package 內部按責任切分為 `app.py`、`phase2_payloads.py`、
  `phase3_payloads.py`、`phase5_payloads.py` 與 `__init__.py` re-export。
- 既有 route tests 的 `from stock_etf_route_fixtures import ...` import surface
  不變。
- 原 1525 行 fixture 檔移除；拆分後各模組為 `57`、`63`、`482`、`629`、
  `364` 行，全部低於 800 行 review-attention threshold。
- 新增 structure guard，要求 legacy flat helper 保持移除、package module/export
  surface 穩定，並阻止 payload fixture 模組引入 network / IBKR SDK / file-write
  token。

Verification 已過：

- Route fixture `py_compile`：PASS
- Route fixture split static guard：`3 passed`
- Full Stock/ETF FastAPI/static：`105 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 IBKR contact、沒有 SDK import、
沒有 socket/HTTP、沒有 secret access/creation、沒有 connector runtime、沒有 read probe
execution、沒有 paper order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有
DB apply、沒有 evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live
execution 行為。

## 2026-06-30 Operator Update — Rust IPC Request Contract Test Split Guard

本 session 已進一步降低 Stock/ETF Rust IPC 測試父檔的結構風險：

- 將 paper/fill/shadow/readonly-probe request contract tests 從
  `rust/openclaw_engine/src/ipc_server/tests/stock_etf.rs` 拆到
  `rust/openclaw_engine/src/ipc_server/tests/stock_etf/request_contracts.rs`。
- 父檔 `stock_etf.rs` 從 `1852` 行降到 `1110` 行。
- 新子檔 `request_contracts.rs` 為 `745` 行；既有 `status_fixtures.rs` 保持
  `685` 行。
- Rust IPC test split guard 現在要求子模組集合固定為 `request_contracts.rs` 與
  `status_fixtures.rs`，並把父/子測試檔 line cap 收緊到 `1200`。
- Guard 同時確認 request-contract 子模組保留 paper / fill import / shadow /
  readonly-probe method 覆蓋，並阻止引入 IBKR SDK 或 socket/HTTP client token。

Verification 已過：

- `rustfmt`：PASS
- Engine `stock_etf` filter：`31 passed`
- Rust IPC test split static guard：`3 passed`
- Full Stock/ETF FastAPI/static：`105 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 IBKR contact、沒有 SDK import、
沒有 socket/HTTP、沒有 secret access/creation、沒有 connector runtime、沒有 read probe
execution、沒有 paper order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有
DB apply、沒有 evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live
execution 行為。

## 2026-06-30 Operator Update — Rust IPC Handler Request Summary Split Guard

本 session 已進一步降低 Stock/ETF Rust IPC production handler 的結構風險：

- 將 request parsing 與 paper/fill/shadow/readonly-probe source-only summary helpers
  從 `rust/openclaw_engine/src/ipc_server/handlers/stock_etf.rs` 拆到
  `rust/openclaw_engine/src/ipc_server/handlers/stock_etf/request_summaries.rs`。
- 父檔 `stock_etf.rs` 從 `1292` 行降到 `823` 行。
- 新子檔 `request_summaries.rs` 為 `477` 行；既有 `status_summaries.rs` 保持
  `934` 行。
- Handler split guard 現在要求子模組集合固定為 `request_summaries.rs` 與
  `status_summaries.rs`，並把父/子 handler 檔 line cap 收緊到 `1200`。
- Guard 同時確認 request summary helpers 在子模組，並阻止引入 IBKR SDK 或
  socket/HTTP client token。

Verification 已過：

- `rustfmt --check`：PASS
- Engine `stock_etf` filter：`31 passed`
- Rust IPC handler/test split static guards：`6 passed`
- Full Stock/ETF FastAPI/static：`105 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有新增 dispatch route、沒有
IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有
connector runtime、沒有 read probe execution、沒有 paper order/cancel/replace、沒有 fill
import、沒有 evidence writer、沒有 DB apply、沒有 evidence clock、沒有 tiny-live/live
authority，也沒有改動 Bybit live execution 行為。

## 2026-06-30 Operator Update — FastAPI Route IPC Query Helper Guard

本 session 已降低 Stock/ETF FastAPI route IPC query 重複邏輯風險：

- 將 `stock_etf_routes.py` 內 16 個重複的 `_query_stock_etf_*` IPC status helper
  收斂為單一 `_query_stock_etf_status(ipc, method)`。
- 既有 endpoint、auth dependency、no-store headers、method constants、normalizer、
  response envelope 與 OpenAPI GET-only surface 不變。
- `stock_etf_routes.py` 從 `587` 行降到 `393` 行。
- Python no-write static guard 現在確認只有一個 `ipc.call(method, params={})`
  呼叫點，且 16 個 route handler 只能以 allowlisted readonly Stock/ETF method
  constant 呼叫 central helper。

Verification 已過：

- `py_compile`：PASS
- Route/no-write focused tests：`24 passed`
- Full Stock/ETF FastAPI/static：`105 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 client input、沒有 IBKR
contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有
connector runtime、沒有 read probe execution、沒有 paper order/cancel/replace、沒有 fill
import、沒有 evidence writer、沒有 DB apply、沒有 evidence clock、沒有 tiny-live/live
authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — Session Attestation Data-Tier Lineage Guard

本 session 已把 `ibkr_session_attestation_v1` source-only contract 補硬：

- Rust 新增 `IbkrSessionDataTier`，並在 session attestation 中記錄
  `data_tier`、`entitlements_fingerprint`、
  `market_data_entitlement_purchase_denied`、`gateway_started_at_ms`。
- Session validator 現在要求 account/secret-slot/entitlements/raw artifact lineage
  皆為 64-hex hash 形狀，並拒絕 missing data tier、未禁止 market-data
  entitlement purchase、gateway startup 晚於 attestation 的 payload。
- Inert Python connector session preview 與 FastAPI account/authorization
  normalizers 同步新增 display-only fail-closed 欄位：`unknown` / `False` / `0`。
- Account/authorization contract violation guard 會拒絕 client/IPC 提前宣稱
  data tier、entitlements fingerprint、market-data entitlement purchase denial 或
  gateway startup timestamp。
- Phase0 named-contract packet 同步補齊 `ibkr_session_attestation_v1` required
  fields / blockers。

Verification 已過：

- Python changed files `py_compile`：PASS
- Connector/account/authorization focused tests：`18 passed`
- Scoped Rust `rustfmt --edition 2021 --check`：PASS
- IBKR Phase2 gate acceptance：`11 passed`
- IBKR feature-flag auth acceptance：`8 passed`
- Full Stock/ETF FastAPI/static：`120 passed`
- Full `cargo test -p openclaw_types`：`291 passed`
- Focused docs trace：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 client input、沒有 IBKR
contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有
connector runtime、沒有 read probe execution、沒有 market-data ingestion、沒有 paper
order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有 DB apply、沒有
evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — Evidence Clock Lineage Guard

本 session 已完成下一個 source-only checkpoint：Evidence Clock Lineage Guard。

這次把 `stock_etf_evidence_clock_v1` checker 補成必須引用 collector run 與 DQ
manifest 的 contract id/hash lineage。你會在 existing Evidence Status panel 看到
evidence-clock 的 collector/DQ/source/provenance/scorecard input hash presence。

Verification 已過：

- Python changed files `py_compile` PASS
- Stock/ETF evidence/fallback JS `node --check` PASS
- Scoped Rust `rustfmt --edition 2021 --check` PASS
- Phase3 evidence acceptance：`19 passed`
- Phase0 manifest acceptance：`6 passed`
- Full Stock/ETF FastAPI/static pytest：`120 passed`
- Full `cargo test -p openclaw_types` PASS
- Engine Stock/ETF focused test PASS
- Docs trace：`2 passed`
- `git diff --check` PASS
- Focused evidence-status pytest：`4 passed`

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 GUI fanout 增加、沒有 IBKR
contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有 connector
runtime、沒有 read probe execution、沒有 collector start、沒有 market-data ingestion、
沒有 DQ writer、沒有 paper order/cancel/replace、沒有 fill import、沒有 DB/evidence
writer、沒有 evidence clock、沒有 scorecard writer、沒有 Linux runtime sync/restart、
沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — Connector Attestation Preview Guard

本 session 已完成一個 source-only connector checkpoint：Connector Attestation
Preview Guard。

這次只是在 inert IBKR connector skeleton 補上 blocked session attestation 與
paper attestation preview payload。它不是 IBKR contact、不是 read probe、不是 paper
account/channel attestation runtime，也沒有新增 FastAPI endpoint 或 IPC method。

結果：

- `IbkrReadOnlyClient` 現在有 `session_attestation_preview()`。
- `IbkrPaperClientBoundary` 現在有 `paper_attestation_preview()`。
- Preview payload 都固定 secret-free、no network、no Bybit path、accepted false。
- Static fixtures 與 connector public surface freeze tests 已同步。

Verification 已過：

- Python changed files `py_compile` PASS
- Connector skeleton focused test：`8 passed`
- Full Stock/ETF FastAPI/static pytest：`120 passed`
- Docs trace：`2 passed`
- `git diff --check` PASS

邊界不變：沒有 IBKR contact、SDK import、socket/HTTP、secret access/creation、
connector runtime、read probe execution、collector start、market-data ingestion、
DQ writer、paper order/cancel/replace、fill import、DB/evidence writer、evidence clock、
scorecard writer、Linux runtime sync/restart、tiny-live/live authority，也沒有改動
Bybit live execution 行為。

## 2026-07-01 Operator Update — Phase3 Evidence Module Split Guard

本 session 已完成一個 source-only maintainability checkpoint：
Phase3 Evidence Module Split Guard。

這次沒有改 contract 語義，也沒有改 FastAPI/GUI payload；只是把 Phase3
market-data provenance 與 frozen-input contract 從
`stock_etf_phase3_evidence.rs` 拆到
`stock_etf_phase3_evidence/market_data.rs`，並保留原 public re-export。

結果：

- `stock_etf_phase3_evidence.rs` 從 982 行降到 742 行，低於 800 行
  review-attention threshold。
- 新子模組 `market_data.rs` 為 254 行。

Verification 已過：

- Scoped Rust `rustfmt --edition 2021 --check` PASS
- Phase3 evidence acceptance：`19 passed`
- Phase0 manifest acceptance：`6 passed`

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 GUI fanout 增加、沒有 IBKR
contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有 connector
runtime、沒有 read probe execution、沒有 collector start、沒有 market-data ingestion、
沒有 DQ writer、沒有 paper order/cancel/replace、沒有 fill import、沒有 DB/evidence
writer、沒有 evidence clock、沒有 scorecard writer、沒有 Linux runtime sync/restart、
沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — DQ Manifest Contract

本 session 已新增 `stock_etf_dq_manifest_v1`，把未來 Phase 3 daily DQ manifest
必須提供的 identity、collector/provenance/source lineage 與 side-effect denial 固定為
source-only contract。

重點：

- Phase0 named contracts 從 34 更新為 35，新增 `stock_etf_dq_manifest_v1`。
- Existing Evidence Status panel 現在顯示 default-blocked `dq_manifest` contract
  identity、lineage hash presence 與 side-effect flags。
- FastAPI normalizer 會把 DQ manifest 的 IBKR contact、connector runtime、
  market-data ingestion、DQ writer、evidence-clock start、scorecard writer、DB apply、
  secret serialization、tiny-live/live truthy claims 擋成 `contract_violation_blocked`。
- 沒有新增 endpoint、IPC method、GUI fanout、background work、runtime writer 或 connector。

Verification 已過：

- Python changed files `py_compile`：PASS
- Stock/ETF JS `node --check`：PASS
- Scoped Rust `rustfmt --check`：PASS；`lib.rs` 使用 `skip_children=true` 避開既有
  unrelated `risk.rs` formatting drift
- Phase3 evidence acceptance：`19 passed`
- Phase0 manifest acceptance：`6 passed`
- Focused Phase0/Evidence/Route pytest：`22 passed`
- Full Stock/ETF FastAPI/static：`120 passed`
- Full `openclaw_types`：PASS
- Engine Stock/ETF focused：`31 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有 IBKR contact、SDK import、socket/HTTP、secret access、connector
runtime、read probe execution、collector start、market-data ingestion、DQ writer、paper
order/cancel/replace、fill import、DB/evidence/scorecard writer、evidence clock、
tiny-live/live、Linux runtime sync/restart 或 Bybit behavior change。

## 2026-07-01 Operator Update — Collector Run Contract

本次是 Phase 3 source-only collector run contract，不是 collector runtime：

- 新增 `stock_etf_collector_run_v1`，Phase0 named contracts 從 33 增為 34。
- Validator 要求至少 5 個 green trading sessions，並要求 PIT universe、
  market-data provenance、reference-data sources、storage capacity、gap report、
  DQ manifest、replay manifest、source artifact lineage hashes。
- Existing `stock_etf.get_evidence_status` 現在顯示 default-blocked
  `collector_run` block；FastAPI / GUI 只做 display/fail-closed normalization。
- 沒有新增 endpoint、沒有新增 IPC method、沒有新增 GUI API fanout。

Verification 已過：

- Python changed files `py_compile`：PASS
- Stock/ETF JS `node --check`：PASS
- Scoped Rust `rustfmt --edition 2021 --check`：PASS
- Full Stock/ETF FastAPI/static：`120 passed`
- Full `openclaw_types`：`287` tests passed
- Engine Stock/ETF focused：`31 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret
access/creation、沒有 connector runtime、沒有 read probe execution、沒有 collector
start、沒有 market-data ingestion、沒有 paper order/cancel/replace、沒有 fill import、
沒有 evidence writer、沒有 DB apply、沒有 evidence clock、沒有 scorecard writer、沒有
Linux runtime sync/restart、沒有 tiny-live/live authority，也沒有改動 Bybit live
execution 行為。

## 2026-07-01 Operator Update — IBKR Connector Preview Payload Guard

這次不是 IBKR contact、不是 connector runtime、不是 read probe，也不是 paper/fill
writer。變更只收緊 inert Python connector skeleton 的 preview payload：

- `IbkrReadOnlyClient.connection_plan()` 現在和其他 skeleton preview 一樣明確
  fail-closed：`surface_id`、`accepted=false`、`status=blocked_source_only`、
  `phase2_gate_not_accepted`、`connection_plan_blocked`。
- 新增 exact payload-shape regression，覆蓋 connection plan、readiness、account
  snapshot、market data、contract details、paper lifecycle、fill import 和 static
  fixture previews。
- 測試固定所有 preview payload 的 no-network、no-secret、no-paper-channel、no-live、
  no-write、no-DB-apply、no-Bybit-reuse posture。
- 這讓未來 connector 實作前的 source-only skeleton 不會被 display/API 消費者誤判為
  已可連線或可操作。

Verification 已過：

- Python compile：PASS
- Connector skeleton focused tests：`5 passed`
- Python no-write static guard：`17 passed`
- Full Stock/ETF FastAPI/static：`113 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 client input、沒有 IBKR
contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有
connector runtime、沒有 read probe execution、沒有 paper order/cancel/replace、沒有 fill
import、沒有 evidence writer、沒有 DB apply、沒有 evidence clock、沒有 tiny-live/live
authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — IBKR Connector Bybit Import Separation Guard

這次不是 IBKR contact、不是 connector runtime、不是 Bybit runtime refactor。變更只
加一條 source-only separation guard：

- IBKR connector skeleton 現在有 AST test，禁止 import Bybit connector、
  control-api `app`、`exchange_connectors.bybit_connector` 或
  `program_code.exchange_connectors.bybit_connector`。
- Guard 也掃 literal dynamic import：`__import__` 與 `importlib.import_module`。
- 這保留現有 `bybit_path_reused=false` display 欄位，但防止未來直接重用 Bybit
  runtime/control-api path。
- Scope 僅限 `program_code/broker_connectors/ibkr_connector/**/*.py` 與 tests。

Verification 已過：

- Python compile：PASS
- Connector skeleton focused tests：`6 passed`
- Python no-write static guard：`17 passed`
- Full Stock/ETF FastAPI/static：`114 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 client input、沒有 IBKR
contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有
connector runtime、沒有 read probe execution、沒有 paper order/cancel/replace、沒有 fill
import、沒有 evidence writer、沒有 DB apply、沒有 evidence clock、沒有 tiny-live/live
authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — FastAPI IBKR Connector Runtime Wiring Guard

這次不是 connector runtime，也不是把 Python skeleton 接到 FastAPI。變更只新增
source guard，防止未批准前接線：

- `control_api_v1/app` 的 Stock/ETF / IBKR production Python surface 不得 import
  `program_code.broker_connectors.ibkr_connector`。
- Guard 同時禁止 bare `ibkr_connector`、`broker_connectors.ibkr_connector` 與
  literal dynamic import。
- Dedicated skeleton tests 仍可 import skeleton package；production route/normalizer
  path 不可。
- Shared dynamic import helper 現在也識別 `importlib.import_module`。

Verification 已過：

- Python no-write static guard：`18 passed`
- Connector skeleton focused tests：`6 passed`
- Full Stock/ETF FastAPI/static：`115 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 client input、沒有 IBKR
contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有
connector runtime、沒有 read probe execution、沒有 paper order/cancel/replace、沒有 fill
import、沒有 evidence writer、沒有 DB apply、沒有 evidence clock、沒有 tiny-live/live
authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — Rust IPC Bybit Runtime Separation Guard

這次不是 Rust runtime 改動，也不是接 Bybit path。變更只新增 source guard，防止
Stock/ETF IPC handler/tests 未來 import 或 call Bybit runtime/order modules：

- Handler guard 掃描 `stock_etf.rs`、`request_summaries.rs`、
  `status_summaries.rs`。
- Test guard 掃描 parent IPC test、`request_contracts.rs`、
  `status_fixtures.rs`。
- 禁止 Bybit REST/WS/Earn module/client、order manager、order router、paper
  state、bounded-probe active-order module、`handle_submit_paper_order` 與 direct
  order method call token。
- 允許 contract/posture 層的顯式否定欄位，例如 `bybit_ipc_reused=false`、
  `bybit_path_reused=false`、Bybit live execution unchanged，以及 legacy Bybit
  channel regression。

Verification 已過：

- Rust IPC split static guards：`10 passed`
- Full Stock/ETF FastAPI/static：`115 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有 Rust runtime behavior change、沒有新增 endpoint、沒有新增 IPC method、
沒有 client input、沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret
access/creation、沒有 connector runtime、沒有 read probe execution、沒有 paper
order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有 DB apply、沒有
evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — IBKR Connector Public API Freeze Guard

這次不是 connector runtime，也不是把 Python skeleton 變成 IBKR client。變更只凍結
IBKR connector skeleton 的 public package/class API：

- `ibkr_connector.__all__` 只能 export surface id、read-only client、paper boundary
  client、endpoint config、surface status。
- `IbkrReadOnlyClient` public surface 只能是 read-only/display preview methods。
- `IbkrPaperClientBoundary` public surface 只能是 lifecycle/fill-import readiness
  descriptors。
- 既有 forbidden write method guard 保留；新增 exact public surface freeze，防止
  未批准前加出 runtime start、order write、secret/network 或 Bybit reuse 入口。

Verification 已過：

- Connector skeleton focused tests：`8 passed`
- Python no-write static guard：`18 passed`
- Full Stock/ETF FastAPI/static：`117 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 client input、沒有 IBKR
contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有
connector runtime、沒有 read probe execution、沒有 paper order/cancel/replace、沒有 fill
import、沒有 evidence writer、沒有 DB apply、沒有 evidence clock、沒有 tiny-live/live
authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — Python Runtime Side-Effect Static Guard

這次不是 runtime behavior change，也不是 IBKR connector wiring。變更只新增
Stock/ETF / IBKR Python scoped surface 的 AST guard：

- 禁止 scoped Stock/ETF/IBKR Python surface import `time`、`datetime`、`asyncio`、
  `threading`、`multiprocessing`、`subprocess`、`concurrent`。
- 禁止 timing/concurrency/subprocess calls，例如 `sleep()`、`time()`、
  `monotonic()`、`perf_counter()`、`now()`、`Thread()`、`Process()`、`Popen()`、
  `asyncio.run()`、`create_task()`、`to_thread()`。
- Scope 只包含 Stock/ETF FastAPI routes/normalizers 和 inert IBKR connector
  skeleton；不掃既有 Bybit runtime modules。
- 目的：保持 display/source-only deterministic，不引入 background work、timer、
  thread 或 subprocess overhead。

Verification 已過：

- Python no-write static guard：`19 passed`
- Connector skeleton focused tests：`8 passed`
- Full Stock/ETF FastAPI/static：`118 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 client input、沒有 IBKR
contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有
connector runtime、沒有 read probe execution、沒有 paper order/cancel/replace、沒有 fill
import、沒有 evidence writer、沒有 DB apply、沒有 evidence clock、沒有 tiny-live/live
authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — Rust IPC Runtime Side-Effect Static Guard

這次不是 Rust runtime behavior change，也不是 IBKR connector wiring。變更只新增
Stock/ETF Rust IPC split source 的 structure guard：

- Handler guard 掃描 `stock_etf.rs`、`request_summaries.rs`、
  `status_summaries.rs`。
- Test guard 掃描 parent IPC test、`request_contracts.rs`、
  `status_fixtures.rs`。
- 禁止 `std::time`、`SystemTime`、`Instant`、`chrono`、`Utc::now`、
  `Local::now`、`std::thread`、`thread::spawn`、`tokio::spawn`、
  `tokio::task`、`tokio::time`、`sleep(`、`std::process`、`Command::new`、
  `.spawn(` 等 clock/thread/task/process side-effect token。

Verification 已過：

- Rust IPC split static guards：`12 passed`
- Full Stock/ETF FastAPI/static：`118 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有 Rust runtime behavior change、沒有新增 endpoint、沒有新增 IPC method、
沒有 client input、沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret
access/creation、沒有 connector runtime、沒有 read probe execution、沒有 paper
order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有 DB apply、沒有
evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — GUI Background Work Static Guard

這次不是 GUI runtime activation，也不是自動刷新。變更只新增 Stock/ETF static GUI
no-background-work guard：

- 掃描 `tab-stock-etf*.js` 與 `tab-stock-etf.html`。
- 禁止 `setInterval`、`setTimeout`、`requestAnimationFrame`、
  `requestIdleCallback`、WebSocket、SSE `EventSource`、Worker、SharedWorker、
  BroadcastChannel、XHR、sendBeacon、`performance.now`、`Date.now`。
- 既有一次性 authenticated GET load path 保留；`new Date().toLocaleTimeString()`
  只顯示更新時間，不啟動 background work。
- 目的：避免 display-only Stock/ETF tab 在未批准前產生 polling/push/worker overhead。

Verification 已過：

- Python no-write static guard：`20 passed`
- Full Stock/ETF FastAPI/static：`119 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 client input、沒有 IBKR
contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有
connector runtime、沒有 read probe execution、沒有 paper order/cancel/replace、沒有 fill
import、沒有 evidence writer、沒有 DB apply、沒有 evidence clock、沒有 tiny-live/live
authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — GUI One-Shot Fanout Budget Guard

這次不是 GUI runtime activation，也不是新增 endpoint。變更只鎖住 Stock/ETF GUI 的
一次性 GET fanout budget：

- `tab-stock-etf.js` 只能有一個 `Promise.all` 和一個
  `waitForServerUp(loadReadiness)`。
- 只能有 16 個 `ocApi` call，全部必須是 GET。
- 每個 call 都必須使用 `timeoutMs: 5000` 與 `toastOnError: false`。
- 目的：防止 display-only tab 未來增加額外 fanout、拉高 timeout 或重複 loader，
  影響 control-api/browser runtime 效率。

Verification 已過：

- Python no-write static guard：`21 passed`
- Full Stock/ETF FastAPI/static：`120 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 client input、沒有 IBKR
contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有
connector runtime、沒有 read probe execution、沒有 paper order/cancel/replace、沒有 fill
import、沒有 evidence writer、沒有 DB apply、沒有 evidence clock、沒有 tiny-live/live
authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — Rust IPC Secret/Env Material Static Guard

本 session 已補上 Stock/ETF Rust IPC split files 的 secret/env material 靜態守衛：

- Handler guard 掃描 `stock_etf.rs`、`request_summaries.rs`、
  `status_summaries.rs`。
- Test guard 掃描 Rust parent IPC test、`request_contracts.rs`、
  `status_fixtures.rs`。
- Parent handler 只允許既有 typed feature-flag path：
  `StockEtfFeatureFlags::from_env()`。
- Guard 禁止 direct `std::env` / `env::var` bypass、secret-file readers、
  include material macros、network/socket clients，以及 direct IBKR SDK tokens。

Verification 已過：

- Rust IPC split static guards：`8 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- Full Stock/ETF FastAPI/static：`112 passed`
- `git diff --check`：PASS

邊界不變：沒有 Rust runtime behavior change、沒有新增 endpoint、沒有新增 IPC method、
沒有 client input、沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret
access/creation、沒有 connector runtime、沒有 read probe execution、沒有 paper
order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有 DB apply、沒有
evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — Rust Feature Flag Env Allowlist Guard

本 session 已補上 Stock/ETF Rust feature flag env lookup allowlist 守衛：

- 新 test 記錄 `StockEtfFeatureFlags::from_lookup` 實際查詢的 key order。
- Exact allowlist 只有五個非 secret feature flag key：
  lane enabled、IBKR readonly enabled、IBKR paper enabled、asset-lane default、
  Stock/ETF shadow-only。
- 全部 key absent 時必須回到 default-off `StockEtfFeatureFlags::default()`。
- Allowlist key 不可包含 `secret`、`token`、`password`、`account`、`key`。

Verification 已過：

- File-scoped `rustfmt --check`：PASS
- `stock_etf_lane_acceptance`：`9 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- Full Stock/ETF FastAPI/static：`112 passed`
- `git diff --check`：PASS

註：workspace-wide `cargo fmt --all -- --check` 仍因既有 unrelated Rust formatting
drift 失敗；本 checkpoint 未修改那些檔案。

邊界不變：沒有 Rust runtime behavior change、沒有新增 endpoint、沒有新增 IPC method、
沒有 client input、沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret
access/creation、沒有 connector runtime、沒有 read probe execution、沒有 paper
order/cancel/replace、沒有 fill import、沒有 evidence writer、沒有 DB apply、沒有
evidence clock、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — Python Secret/Env Access Static Guard

本 session 已補上 Stock/ETF / IBKR Python secret/env material access 靜態守衛：

- 新增 AST guard 掃描 Stock/ETF FastAPI routes、normalizers 與
  `program_code/broker_connectors/ibkr_connector/`。
- Guard 禁止 `os`、`dotenv`、`getpass`、`keyring` 這類 env/secret helper import。
- Guard 禁止 `os.environ`、`getenv` / `os.getenv`、`Path.home`、
  `expanduser`、`read_text`、`read_bytes` 與任意 `open()` call。
- 現有 `secret_slot_contract` 仍只是 display-only blocked schema normalization；
  不代表可讀取 secret material。

Verification 已過：

- Python no-write static guard：`17 passed`
- Route/no-write focused tests：`31 passed`
- Full Stock/ETF FastAPI/static：`112 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 client input、沒有 IBKR
contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有
connector runtime、沒有 read probe execution、沒有 paper order/cancel/replace、沒有 fill
import、沒有 evidence writer、沒有 DB apply、沒有 evidence clock、沒有 tiny-live/live
authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — GUI Fallback Payload Split Guard

本 session 已進一步降低 Stock/ETF 靜態 GUI 主 bundle 的審查面：

- 將 authorization、account、evidence、universe、shadow、paper、scorecard、launch
  fallback payload builders 從 `tab-stock-etf.js` 拆到
  `tab-stock-etf-fallbacks.js`。
- `tab-stock-etf.js` 從 `1805` 行降到 `1244` 行；新 fallback 模組為 `563` 行。
- HTML 在主 loader 前載入 fallback 模組，既有 endpoint、renderer、GET-only、
  display-only 語義不變。
- Static no-write guard 現在掃描新 fallback 模組，並確認大型 fallback builders
  不回流主 bundle：`tab-stock-etf.js <= 1400`、
  `tab-stock-etf-fallbacks.js <= 800`。
- Route readonly display test 也已納入 data-policy / fallback 子模組，避免分檔後漏掃
  scorecard 或 launch evidence tokens。

Verification 已過：

- Stock/ETF JS `node --check`：PASS
- Route/no-write focused tests：`25 passed`
- Full Stock/ETF FastAPI/static：`106 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 client input、沒有 IBKR
contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有
connector runtime、沒有 read probe execution、沒有 paper order/cancel/replace、沒有 fill
import、沒有 evidence writer、沒有 DB apply、沒有 evidence clock、沒有 tiny-live/live
authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — GUI Data/Policy Renderer Split Guard

本 session 已把 Data Foundation / Policy panel renderer 也納入既有 data-policy 子模組：

- 將 `renderDataFoundationStatus` 與 `renderPolicyStatus` 從
  `tab-stock-etf.js` 搬到 `tab-stock-etf-data-policy.js`。
- `tab-stock-etf.js` 從 `1244` 行降到 `985` 行。
- `tab-stock-etf-data-policy.js` 從 `170` 行增至 `469` 行，仍低於 700 行。
- Data-policy 子模組現在同時擁有 fallback payload builders 與 renderers，並保留
  與其他 Stock/ETF split modules 一致的本地 UI helper。
- Static no-write guard 現在確認 data/policy renderers 不回流主 bundle：
  `tab-stock-etf.js <= 1100`、`tab-stock-etf-data-policy.js <= 700`。

Verification 已過：

- Stock/ETF JS `node --check`：PASS
- Route/no-write focused tests：`26 passed`
- Full Stock/ETF FastAPI/static：`107 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 client input、沒有 IBKR
contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有
connector runtime、沒有 read probe execution、沒有 paper order/cancel/replace、沒有 fill
import、沒有 evidence writer、沒有 DB apply、沒有 evidence clock、沒有 tiny-live/live
authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — GUI Authorization/Account Renderer Split Guard

本 session 已把 Authorization / Account panel renderer 從主 Stock/ETF GUI bundle 拆出：

- 新增 `tab-stock-etf-auth-account.js`，承載 `renderAuthorizationStatus` 與
  `renderAccountStatus`。
- `tab-stock-etf.js` 從 `985` 行降到 `798` 行。
- 新 auth/account 模組為 `235` 行，並以 `window.renderAuthorizationStatus` /
  `window.renderAccountStatus` 暴露給主 loader。
- HTML 在 fallback module 後、主 loader 前載入 auth/account module。
- Static no-write guard 現在掃描新模組，並確認 auth/account renderers 不回流主
  bundle：`tab-stock-etf.js <= 900`、
  `tab-stock-etf-auth-account.js <= 400`。

Verification 已過：

- Stock/ETF JS `node --check`：PASS
- Route/no-write focused tests：`27 passed`
- Full Stock/ETF FastAPI/static：`108 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 client input、沒有 IBKR
contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有
connector runtime、沒有 read probe execution、沒有 paper order/cancel/replace、沒有 fill
import、沒有 evidence writer、沒有 DB apply、沒有 evidence clock、沒有 tiny-live/live
authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — GUI Evidence/Paper Renderer Split Guard

本 session 已把 Evidence / Universe / Shadow / Paper panel renderer 從主
Stock/ETF GUI bundle 拆出：

- 新增 `tab-stock-etf-evidence-paper.js`，承載 `renderEvidenceStatus`、
  `renderUniverseStatus`、`renderShadowStatus` 與 `renderPaperStatus`。
- `tab-stock-etf.js` 從 `798` 行降到 `583` 行。
- 新 evidence/paper 模組為 `265` 行，並以 `window.renderEvidenceStatus` /
  `window.renderUniverseStatus` / `window.renderShadowStatus` /
  `window.renderPaperStatus` 暴露給主 loader。
- HTML 在 auth/account module 後、主 loader 前載入 evidence/paper module。
- Static no-write guard 現在掃描新模組，並確認 evidence/paper renderers 不回流主
  bundle：`tab-stock-etf.js <= 650`、
  `tab-stock-etf-evidence-paper.js <= 500`。

Verification 已過：

- Stock/ETF JS `node --check`：PASS
- Route/no-write focused tests：`28 passed`
- Full Stock/ETF FastAPI/static：`109 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 client input、沒有 IBKR
contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有
connector runtime、沒有 read probe execution、沒有 paper order/cancel/replace、沒有 fill
import、沒有 evidence writer、沒有 DB apply、沒有 evidence clock、沒有 tiny-live/live
authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — GUI Scorecard/Launch Renderer Split Guard

本 session 已把 Scorecard / Launch panel renderer 從主 Stock/ETF GUI bundle 拆出：

- 新增 `tab-stock-etf-scorecard-launch.js`，承載 `renderScorecardStatus` 與
  `renderLaunchStatus`。
- `tab-stock-etf.js` 從 `583` 行降到 `350` 行。
- 新 scorecard/launch 模組為 `281` 行，並以 `window.renderScorecardStatus` /
  `window.renderLaunchStatus` 暴露給主 loader。
- HTML 在 evidence/paper module 後、主 loader 前載入 scorecard/launch module。
- Static no-write guard 現在掃描新模組，並確認 scorecard/launch renderers 不回流主
  bundle：`tab-stock-etf.js <= 400`、
  `tab-stock-etf-scorecard-launch.js <= 500`。

Verification 已過：

- Stock/ETF JS `node --check`：PASS
- Route/no-write focused tests：`29 passed`
- Full Stock/ETF FastAPI/static：`110 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 client input、沒有 IBKR
contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有
connector runtime、沒有 read probe execution、沒有 paper order/cancel/replace、沒有 fill
import、沒有 evidence writer、沒有 DB apply、沒有 evidence clock、沒有 tiny-live/live
authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — GUI Readiness Renderer Split Guard

本 session 已把 Readiness / Lane Boundary panel renderer 從主 Stock/ETF GUI bundle
拆出：

- 新增 `tab-stock-etf-readiness.js`，承載 `renderReadiness` 與其本地 UI helpers。
- `tab-stock-etf.js` 從 `350` 行降到 `197` 行，現在主要保留 endpoint constants、
  fallback orchestration 與 loader flow。
- 新 readiness 模組為 `159` 行，並以 `window.renderReadiness` 暴露給主 loader。
- HTML 在 data/policy module 前、主 loader 前載入 readiness module。
- Static no-write guard 現在掃描新模組，並確認 readiness renderer/helper 不回流主
  bundle：`tab-stock-etf.js <= 250`、`tab-stock-etf-readiness.js <= 250`。

Verification 已過：

- Stock/ETF JS `node --check`：PASS
- Route/no-write focused tests：`30 passed`
- Full Stock/ETF FastAPI/static：`111 passed`
- IBKR timeline + trace-title structure guard：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 client input、沒有 IBKR
contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有
connector runtime、沒有 read probe execution、沒有 paper order/cancel/replace、沒有 fill
import、沒有 evidence writer、沒有 DB apply、沒有 evidence clock、沒有 tiny-live/live
authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — Read-Only Probe Result Import Request Contract

本 session 已新增 source-only
`stock_etf_ibkr_readonly_probe_result_import_request_v1` contract：

- 新 Rust validator 固定 future sanitized IBKR read-only probe result 進入 evidence
  前的 request/session/allowlist/redaction/audit/result hash lineage。
- Validator 依 probe kind 要求 downstream lineage：health snapshot、account cash
  ledger、market-data provenance、instrument identity 或 broker lifecycle event log。
- Phase0 manifest/JSON 從 35 named contracts 更新為 36，納入新 named contract。
- Broker capability registry 的 `scorecard_derive` gate 現在要求 readonly probe
  result import request lineage。
- 新增 default-blocked secret-free TOML template，並更新 settings README 與 Phase0
  spec。

Verification 已過：

- Scoped Rust format：PASS
- Result import request acceptance：`6 passed`
- Phase0 manifest acceptance：`6 passed`
- Broker capability registry acceptance：`10 passed`
- Full `cargo test -p openclaw_types`：PASS
- Full Stock/ETF FastAPI/static pytest：`120 passed`
- Focused docs trace：`2 passed`
- `git diff --check`：PASS

邊界不變：沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret
access/creation、沒有 connector runtime、沒有 read probe execution、沒有 result
import、沒有 evidence writer、沒有 DB apply、沒有 evidence clock、沒有 scorecard
writer、沒有 paper order/cancel/replace、沒有 tiny-live/live authority，也沒有改動
Bybit live execution 行為。

## 2026-07-01 Operator Update — Phase0 Result-Import Display Lineage Guard

本 session 已把 readonly probe result-import request contract 傳遞到
Stock/ETF/IBKR display/control-plane surface：

- FastAPI Phase0 status 從 35 contracts 同步為 36，並要求
  `stock_etf_ibkr_readonly_probe_request_v1` 與
  `stock_etf_ibkr_readonly_probe_result_import_request_v1` 同時存在。
- Rust IPC Phase0 status test 同步 36-contract manifest。
- Rust IPC + FastAPI policy status 現在輸出
  `readonly_probe_result_import_request_contract_id` 與
  `scorecard_requires_readonly_probe_result_import_request`。
- GUI Phase0 panel 顯示 result-import request presence；Policy panel 顯示
  scorecard gate 是否要求 result-import lineage。

Verification 已過：

- Python changed files `py_compile`：PASS
- Stock/ETF JS `node --check`：PASS
- Scoped Rust rustfmt：PASS
- Focused FastAPI Phase0/Policy/Route pytest：`23 passed`
- Full Stock/ETF FastAPI/static pytest：`120 passed`
- Focused engine Phase0/Policy IPC tests：PASS
- Engine Stock/ETF IPC regression：`31 passed`

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 GUI fanout 增加、沒有 IBKR
contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、沒有
connector runtime、沒有 read probe execution、沒有 result import、沒有 evidence writer、
沒有 DB apply、沒有 evidence clock、沒有 scorecard writer、沒有 paper order/cancel/
replace、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — Readiness Result-Import Request Guard

本 session 已把 readonly probe result-import request contract 傳遞到
Stock/ETF readiness display/control-plane surface：

- Rust IPC `stock_etf.get_readiness` 的 `phase2` source fixture 現在包含
  `readonly_probe_result_import_request`，預設
  `blocked_no_result_import_request_artifact`。
- FastAPI readiness normalizer 會在 result-import request 缺失時 fail-closed，
  並拒絕 contract id/version/status mismatch 或任何 result import / writer / DB /
  order / Bybit reuse side-effect claim。
- GUI readiness Phase2/Guard 表格與 API-unavailable fallback 現在顯示
  result-import request 的 contract、status、blockers 與 side-effect flags。
- 沒有新增 endpoint、IPC method、GUI fanout、client input 或 connector skeleton
  public API。

Verification 已過：

- Python changed files `py_compile`：PASS
- Stock/ETF JS syntax：PASS
- Scoped Rust rustfmt：PASS
- Focused FastAPI readiness/static route pytest：`20 passed`
- Focused engine readiness IPC test：PASS
- Full Stock/ETF FastAPI/static pytest：`120 passed`
- Engine Stock/ETF IPC regression：`31 passed`

邊界不變：沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret
access/creation、沒有 connector runtime、沒有 read probe execution、沒有 result
import、沒有 collector、沒有 market-data ingestion、沒有 DQ writer、沒有 evidence
writer、沒有 DB apply、沒有 evidence clock、沒有 scorecard writer、沒有 paper order/
cancel/replace、沒有 tiny-live/live authority，也沒有改動 Bybit live execution 行為。

## 2026-07-01 Operator Update — Connector Result-Import Preview Guard

本 session 已把 readonly probe result-import request 補進 inert IBKR connector
skeleton 的 source-only preview surface：

- 新增 `IbkrReadOnlyProbeResultImportPreview` 與
  `IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID`。
- `IbkrReadOnlyClient` 現在只有一個新的 display preview method：
  `readonly_probe_result_import_request_preview()`。
- 新 preview 與 fixture 預設
  `blocked_no_result_import_request_artifact`，且 import/writer/DB/order/live/
  Bybit reuse side-effect flags 全部為 false。
- Connector public API freeze、payload shape guard、no-Bybit-import guard 與
  Python no-write static guard 已同步。

Verification 已過：

- Python changed files `py_compile`：PASS
- Connector skeleton focused pytest：`8 passed`
- Python no-write static guard：`21 passed`
- Full Stock/ETF FastAPI/static pytest：`120 passed`

邊界不變：沒有新增 endpoint、沒有新增 IPC method、沒有 FastAPI production import、
沒有 IBKR contact、沒有 SDK import、沒有 socket/HTTP、沒有 secret access/creation、
沒有 connector runtime、沒有 read probe execution、沒有 result import、沒有 DB/
evidence/scorecard writer、沒有 paper order/cancel/replace、沒有 tiny-live/live
authority，也沒有改動 Bybit live execution 行為。
