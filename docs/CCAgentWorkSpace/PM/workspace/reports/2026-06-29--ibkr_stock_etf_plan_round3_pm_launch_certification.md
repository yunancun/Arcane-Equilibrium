# PM 第三輪 launch-certification 報告 — IBKR Stock/ETF Paper + Shadow 方案

日期：2026-06-29
角色：PM(default)
範圍：整合 CC / FA / PA / E3 / E5 / QC / MIT / QA 對
`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md`
第二輪 hard-gated 版本的第三輪 launch-certification。

## Verdict

**PM SIGN-OFF: CONDITIONAL / PAPER_SHADOW_LAUNCH_CERTIFIABLE_IF_ALL_GATES_PASS**

這不是當前 launch approval。它的含義是：如果 Phase 0 named contract packet
被接受，且 Phase 1-5 所有 gate 按計劃以 machine-checkable artifacts 全部通過，
PM 可以簽核 `stock_etf_cash` paper/shadow lane 完整上線。

不批准：

- 當前直接上線。
- Phase 1+ 在 Phase 0 packet 未 accepted 前開工。
- IBKR live / tiny-live / margin / short / options / CFD / transfer。
- Python broker write authority。
- GUI lane selector 作為交易 authority。
- 任何盈利、durable alpha、live readiness 或 automatic promotion claim。

## Review Question

第三輪問題被收窄為：

> 在第二輪 hard gates 已寫入主計劃後，如果 Phase 0 named contract packet 和
> Phase 1-5 gates 全部完成且通過，是否仍有阻止 paper/shadow lane 完整上線的
> missing launch gate？

八角色答案一致：沒有發現額外 minimum launch gate，但結論只在
`paper_shadow_only` scope 與 all-gates-pass 假設下成立。

## Role Results

| Role | Certification | Findings | Report |
|---|---|---:|---|
| CC | CERTIFIABLE_IF_GATES_PASS | 0 | `docs/CCAgentWorkSpace/CC/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round3_cc_launch_certification.md` |
| FA | CERTIFIABLE_IF_GATES_PASS | 0 | `docs/CCAgentWorkSpace/FA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round3_fa_launch_certification.md` |
| PA | CERTIFIABLE_IF_GATES_PASS | 0 | `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round3_pa_launch_certification.md` |
| E3 | CERTIFIABLE_IF_GATES_PASS | 0 | `docs/CCAgentWorkSpace/E3/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round3_e3_launch_certification.md` |
| E5 | CERTIFIABLE_IF_GATES_PASS | 0 | `docs/CCAgentWorkSpace/E5/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round3_e5_launch_certification.md` |
| QC | CERTIFIABLE_IF_GATES_PASS | 0 | `docs/CCAgentWorkSpace/QC/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round3_qc_launch_certification.md` |
| MIT | CERTIFIABLE_IF_GATES_PASS | 0 | `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round3_mit_launch_certification.md` |
| QA | CERTIFIABLE_IF_GATES_PASS | 0 | `docs/CCAgentWorkSpace/QA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round3_qa_launch_certification.md` |

## Certified Scope

第三輪可條件簽核的 scope 只包括：

- `stock_etf_cash` paper/shadow lane。
- IBKR read-only health/account/market-data surface after `phase2_ibkr_external_surface_gate_v1` PASS。
- IBKR broker-paper lifecycle rehearsal through Rust-owned authority only。
- Shadow signal, shadow fill, cost reconstruction, paper-vs-shadow reconciliation。
- GUI badge/readiness/evidence/export views after route/cache/auth negative tests PASS。
- Data-quality, evidence clock, immutable artifact manifest, release packet。
- Kill switch, disable cleanup, secret absence proof, and evidence archive path。

## Required Gate Interpretation

`paper_shadow_online_complete` means all of the following are true:

1. Phase 0 ADR/AMD and named contract packet are accepted.
2. Phase 1 type/config/schema/IPC foundation implements only accepted contracts.
3. Phase 2 external-surface gate passes before any IBKR call, then read-only/paper
   lifecycle gates pass with session/account attestation.
4. Phase 3 collector, point-in-time universe, market-data provenance, corporate
   action, DQ, scorecard, and evidence clock gates pass.
5. Phase 4 GUI badge/readiness-first slices, stock evidence views, negative tests,
   route/cache/auth partition, and crypto regression gates pass.
6. Phase 5 engineering shakedown, release packet, operator runbook, kill/disable
   cleanup, and evidence archive gates pass.

Only after all six conditions are true can PM sign off paper/shadow launch.

## Current State

Current state remains not launch-ready:

- Phase 0 ADR/AMD/named contract packet now exists in source and has source
  validation coverage, but it does not unlock runtime by itself.
- Multiple Phase 1-5 source/status/display-only checkpoints now exist. Runtime
  artifacts for first contact, secret-slot materialization, connector runtime,
  paper order rehearsal, fill import, DB apply, evidence clock, scorecard writer,
  paper-shadow launch, and release remain blocked.
- IBKR API call, secret slot, paper order rehearsal, GUI runtime activation, and
  evidence clock remain blocked.
- Profitability is unproven; 6-8 weeks can provide engineering shakedown and
  preliminary feasibility only, not durable alpha proof.

## PM Decision

PM can now tell the operator:

> 在 `paper_shadow_only` 範圍內，如果 Phase 0 named contract packet 和 Phase 1-5
> gates 全部完成且通過，八角色沒有發現額外 missing launch gate；可以簽核
> `stock_etf_cash` paper/shadow lane 按計劃完整上線。

PM must not say:

- 現在可上線。
- IBKR live / tiny-live 可上。
- paper/shadow 證明盈利。
- durable alpha 已成立。
- 絕對無遺漏。

下一步仍是 Phase 0 ADR/AMD + named contract packet，不是 connector implementation。

## 2026-06-30 PM Session Checkpoint

PM 已在本 session 追加一個 source-only checkpoint：Policy / Capability Status
read-only surface。

已完成：

- Rust IPC：`stock_etf.get_policy_status` fixture，來源為
  `stock_etf_risk_policy_v1` + `broker_capability_registry_v1` blocked/default posture。
- FastAPI：authenticated/no-store
  `GET /api/v1/stock-etf/policy-status`，只 read IPC、fail-closed normalize。
- GUI：`Policy Gate` metric 與 `Policy / Capability Status` panel。
- Contracts：`lane_scoped_ipc_v1` 增加 `GetPolicyStatus`；
  `gui_lane_contract_v1` 增加 exact GET-only policy-status endpoint。

Verification：

- Python compile PASS；Node inline parser PASS。
- Focused FastAPI/static pytest `18 passed`。
- Full Stock/ETF FastAPI/static pytest `72 passed`。
- Engine Stock/ETF cargo filter `17 passed`。
- GUI/lane IPC acceptance `17 passed`。
- Full openclaw_types `35` unit/golden + `206` integration/acceptance + `0` doc-tests。

PM 判定：checkpoint 可接受，但仍不是 launch approval。未批准 IBKR contact、secret、
connector runtime、paper order rehearsal/submit、fill import、evidence clock、scorecard
writer、DB apply、GUI lane authority、tiny-live、live 或 Bybit behavior change。

## 2026-06-30 PM Session Checkpoint — Authorization Status

PM 已在本 session 追加下一個 source-only checkpoint：Authorization Status
read-only surface。

已完成：

- Rust IPC：`stock_etf.get_authorization_status` fixture，來源為
  `feature_flag_secret_auth_matrix_v1`、`ibkr_secret_slot_contract_v1`、
  `phase2_ibkr_external_surface_gate_v1`、`ibkr_session_attestation_v1` 與
  authorization envelope 的 blocked/default posture。
- FastAPI：authenticated/no-store
  `GET /api/v1/stock-etf/authorization-status`，只 read IPC、fail-closed normalize，
  並拒絕 client-supplied authorization state。
- GUI：`Authorization Gate` metric 與 `Authorization Status` panel。
- Contracts：`lane_scoped_ipc_v1` 增加 `GetAuthorizationStatus`；
  `gui_lane_contract_v1` 增加 exact GET-only authorization-status endpoint。

Verification：

- Python compile PASS；Node inline parser PASS（7 inline scripts）。
- Full Stock/ETF FastAPI/static pytest `77 passed`。
- Engine Stock/ETF cargo filter `18 passed`。
- GUI/lane IPC acceptance `17 passed`。
- Full openclaw_types `35` unit/golden + `206` integration/acceptance + `0` doc-tests。
- Workspace `cargo check` PASS。

PM 判定：checkpoint 可接受，但仍不是 launch approval。未批准 IBKR contact、secret、
connector runtime、paper order rehearsal/submit、fill import、evidence clock、scorecard
writer、DB apply、GUI lane authority、Phase 2/3/5 start、tiny-live、live 或 Bybit
behavior change。

## 2026-06-30 PM Session Hygiene Checkpoint — Stock/ETF GUI Split

Authorization Status 落地後，`tab-stock-etf.html` 累積到 2225 行，已超過 repo
2000 行硬上限。PM 先完成純 GUI 拆檔，避免後續每個 read-only surface 都擴大
維護風險。

已完成：

- 將大段 Stock/ETF inline JS 原樣抽出為 `/static/tab-stock-etf.js`。
- `tab-stock-etf.html` 降至 341 行；`tab-stock-etf.js` 為 1883 行。
- Static no-write guard 改為掃 HTML+JS bundle，保留 endpoint presence 與 forbidden
  write snippet 檢查。

Verification：

- `python3 -m py_compile` for changed route/static tests：PASS。
- `node --check tab-stock-etf.js`：PASS。
- HTML inline parser：PASS（1 inline script）。
- Full Stock/ETF FastAPI/static pytest `77 passed`。
- `git diff --check` PASS。

PM 判定：checkpoint 可接受。這是純拆檔 hygiene；未新增 endpoint、未改 IPC/contract、
未批准 IBKR contact、secret、connector runtime、paper order、DB apply、Linux runtime
sync/restart、tiny-live/live 或 Bybit behavior change。

## 2026-06-30 PM Session Checkpoint — Disable Cleanup Status

PM 已在本 session 追加下一個 source-only checkpoint：
`disable-cleanup-status` read-only surface。

已完成：

- Rust IPC：`stock_etf.get_disable_cleanup_status` fixture，來源為
  `stock_etf_kill_switch_and_disable_cleanup_runbook_v1` source-ready runbook shape，
  但 runtime posture 仍為 blocked；collector/gui/archive/DB cleanup request 全部 false。
- Rust dispatch/registry：method 為 readonly、slot none，且不進 Bybit live-write token
  surface；`lane_scoped_ipc_v1` 增加 `GetDisableCleanupStatus`。
- FastAPI：authenticated/no-store
  `GET /api/v1/stock-etf/disable-cleanup-status`，只 read IPC、fail-closed normalize，
  並拒絕 client-supplied cleanup/launch/live state。
- GUI：`Disable Cleanup` metric 與 `Disable / Cleanup Status` panel；render hook 拆入
  `/static/tab-stock-etf-disable-cleanup.js`，主 Stock/ETF JS 仍低於 2000 行。
- Contracts：`gui_lane_contract_v1` 增加 exact GET-only disable-cleanup-status
  endpoint；blocked template 同步更新。

Verification：

- Python compile PASS。
- Full Stock/ETF FastAPI/static pytest `81 passed`。
- Node check PASS for `tab-stock-etf.js` and `tab-stock-etf-disable-cleanup.js`。
- HTML inline parser PASS（1 inline script）。
- GUI line caps PASS：HTML 359、main JS 1895、disable-cleanup JS 132。
- Engine Stock/ETF cargo filter `19 passed`。
- openclaw_types `stock_etf` filter PASS。

PM 判定：checkpoint 可接受，但仍不是 launch approval。未批准 IBKR contact、secret、
connector runtime、collector stop、GUI hide、evidence archive、DB cleanup/apply、
paper order rehearsal/submit、fill import、evidence clock、scorecard writer、Phase 2/3/5
start、paper-shadow launch、tiny-live、live、Linux runtime sync/restart 或 Bybit behavior
change。

## 2026-06-30 PM Session Checkpoint — Release Packet Status

PM 已在本 session 追加下一個 source-only checkpoint：
`release-packet-status` read-only surface。

已完成：

- Rust IPC：`stock_etf.get_release_packet_status` fixture，來源為
  `stock_etf_release_packet_v1` accepted source fixture 與
  `stock_etf_kill_switch_and_disable_cleanup_runbook_v1` proof 摘要；runtime launch
  fields 全部 blocked false。
- Rust dispatch/registry：method 為 readonly、slot none，且不進 Bybit live-write token
  surface；`lane_scoped_ipc_v1` 增加 `GetReleasePacketStatus`。
- FastAPI：authenticated/no-store
  `GET /api/v1/stock-etf/release-packet-status`，只 read IPC、fail-closed normalize，
  並拒絕 client-supplied launch/live state。
- GUI：`Release Packet` metric 與 `Release Packet Status` panel；render hook 拆入
  `/static/tab-stock-etf-release-packet.js`，主 Stock/ETF JS 仍低於 2000 行。
- Contracts：`gui_lane_contract_v1` 增加 exact GET-only release-packet-status
  endpoint；blocked template 同步更新。

Verification：

- Python compile PASS。
- Full Stock/ETF FastAPI/static pytest `85 passed`。
- Node check PASS for `tab-stock-etf.js`、`tab-stock-etf-release-packet.js`、
  `tab-stock-etf-disable-cleanup.js`。
- HTML inline parser PASS（1 inline script）。
- Engine Stock/ETF cargo filter `20 passed`。
- Full openclaw_types PASS。
- Workspace `cargo check` PASS。

PM 判定：checkpoint 可接受，但仍不是 launch approval。未批准 IBKR contact、secret、
connector runtime、release packet materialization、paper-shadow launch、paper order、
fill import、evidence clock、scorecard writer、DB apply、Phase 2/3/5 start、
tiny-live、live、Linux runtime sync/restart 或 Bybit behavior change。

## 2026-06-30 PM Session Checkpoint — Phase 0 Packet Status

PM 已在本 session 追加下一個 source-only checkpoint：
`phase0-status` read-only surface。

已完成：

- Rust IPC：`stock_etf.get_phase0_status` fixture，來源為
  `stock_etf_phase0_contract_packet_manifest_v1` accepted source manifest；runtime
  phase、connector、order、secret、DB、evidence-clock、scorecard、launch、Bybit reuse
  fields 全部 blocked false。
- Rust dispatch/registry：method 為 readonly、slot none，且不進 Bybit live-write token
  surface；`lane_scoped_ipc_v1` 增加 `GetPhase0Status`。
- FastAPI：authenticated/no-store
  `GET /api/v1/stock-etf/phase0-status`，只 read IPC、fail-closed normalize，
  並拒絕 client-supplied Phase 0/launch/live state。
- GUI：`Phase 0 Packet` metric 與 `Phase 0 Packet Status` panel；render hook 拆入
  `/static/tab-stock-etf-phase0.js`，主 Stock/ETF JS 仍低於 2000 行。
- Contracts：`gui_lane_contract_v1` 增加 exact GET-only phase0-status endpoint；
  blocked template、settings README、Phase 0 named contract packet endpoint 清單同步更新。

Verification：

- Python compile PASS。
- Full Stock/ETF FastAPI/static pytest `89 passed`。
- Node check PASS for `tab-stock-etf.js`、`tab-stock-etf-phase0.js`、
  `tab-stock-etf-release-packet.js`、`tab-stock-etf-disable-cleanup.js`。
- HTML inline parser PASS（1 inline script）。
- Rust format checks PASS（含 `lib.rs` with `skip_children=true`）。
- Engine Stock/ETF cargo filter `21 passed`。
- Full openclaw_types PASS：`35` unit/golden + `206` integration/acceptance + `0` doc-tests。
- Workspace `cargo check` PASS。

PM 判定：checkpoint 可接受，但仍不是 launch approval。未批准 IBKR contact、secret、
connector runtime、Phase 1/2/3/4/5 runtime start、release packet materialization、
paper-shadow launch、paper order、fill import、evidence clock、scorecard writer、
DB apply、GUI lane authority、tiny-live、live、Linux runtime sync/restart 或 Bybit
behavior change。

## 2026-06-30 PM Session Checkpoint — DB Evidence DDL Source Audit

PM 已在本 session 追加 Phase 1C source-only checkpoint：
`stock_etf_db_evidence_ddl_v1.source_only.sql` auditor hardening。

已完成：

- Rust `openclaw_types`：新增 exported
  `audit_stock_etf_db_evidence_source_sql`，對 source-only DDL draft 做 machine
  audit。
- Audit coverage：source-only banner、migration/apply denial、destructive SQL
  denial、required schemas/tables、Guard A、key table column declarations、natural
  keys、stock/IBKR/paper checks、live denial、synthetic shadow fill separation、
  raw artifact hash、audit append-only posture 與 hot-path indexes。
- Acceptance：實際 source SQL 現在必須 audit accepted、13 required tables、至少 6
  indexes；drift tests 會刪欄位宣告、刪 synthetic shadow check、追加 `DROP TABLE`
  並確認 fail-closed。

Verification：

- Rust format checks PASS（`lib.rs` with `skip_children=true`）。
- Focused source SQL audit `2 passed`。
- DB evidence DDL acceptance `9 passed`。
- Full openclaw_types PASS：`35` unit/golden + `207` integration/acceptance +
  `0` doc-tests。
- Workspace `cargo check` PASS。

PM 判定：checkpoint 可接受，但仍不是 DB deployment approval。未批准 DB
migration/apply、Postgres dry-run、double apply、IBKR contact、secret、connector
runtime、Phase 1/2/3/4/5 runtime start、paper order、fill import、evidence clock、
scorecard writer、tiny-live、live、Linux runtime sync/restart 或 Bybit behavior
change。

## 2026-06-30 PM Session Checkpoint — DB Evidence DDL Source Contract Hardening

PM 已在本 session 追加 Phase 1C source-only checkpoint：DB evidence DDL contract
hardening。這是在上一個 source auditor 之上補 DB contract 面，不是 DB deployment。

已完成：

- Source SQL：新增 Guard B type-sensitive checks 與 Guard C
  `pg_get_indexdef` hot-path index drift checks。
- Source SQL：新增 FK lineage，覆蓋 instrument listing/order/fill/commission/shadow
  signal/fill chain，並補 shadow fill 的 `broker` / `strategy_id` 欄位。
- Source SQL：新增 scorecard lineage 欄位：broker/environment、cost model version、
  market-data provenance hash、corporate-actions hash、FX/cash-ledger hash、paper-vs-shadow
  reconciliation hash。
- Source SQL：新增 TimescaleDB hypertable/retention promotion plan，但明確不執行；
  未來 V### promotion 前必須先設計 partition-safe primary/unique constraints。
- Rust auditor：新增 Guard B/C、dry-run plan、required FK、hypertable/retention plan
  blockers，並追蹤 source SQL `foreign_key_count`。

Verification：

- Rust format checks PASS（`lib.rs` with `skip_children=true`）。
- DB evidence DDL acceptance `10 passed`。
- Full openclaw_types PASS：`35` unit/golden + `208` integration/acceptance +
  `0` doc-tests。
- Workspace `cargo check` PASS。

PM 判定：checkpoint 可接受，但仍不是 DB deployment approval。未批准 DB
migration/apply、Postgres dry-run、double apply、sqlx migration registration、IBKR
contact、secret、connector runtime、Phase 1/2/3/4/5 runtime start、paper order、
fill import、evidence clock、scorecard writer、tiny-live、live、Linux runtime
sync/restart 或 Bybit behavior change。

## 2026-06-30 PM Session Checkpoint — Paper IPC Request Shape Hardening

PM 已在本 session 追加 Phase 1D source-only checkpoint：lane-scoped paper IPC request
shape hardening。這是 Rust contract/acceptance hardening，不是 paper order runtime。

已完成：

- `lane_scoped_ipc_v1` 拆分 `PreviewPaperOrder`、`SubmitPaperOrder`、
  `CancelPaperOrder`、`ReplacePaperOrder` 的 request field contract；submit、
  cancel、replace 不再共用同一組 generic paper-effect fields。
- Submit contract pin 住完整 order intent：account fingerprint hash、instrument
  identity hash、symbol、instrument kind、side、order type、quantity、
  `limit_price_policy`、time in force、`order_local_id`、idempotency key，以及
  session/scoped authorization/guardian/risk/lifecycle/capability/audit fields。
- Cancel contract pin 住 `order_local_id`、`broker_order_id`、`cancel_reason`、
  idempotency、lifecycle/capability/audit fields，並明確不要求 submit 的
  quantity/order_type/limit-price fields。
- Replace contract pin 住 `replacement_idempotency_key`、`replacement_quantity`、
  `replacement_limit_price_policy`、`replacement_time_in_force`、`replace_reason`，
  並帶回原 order/broker ids、instrument identity、symbol、side 與 audit lineage。
- Acceptance tests 新增 cross-wire regression，證明 cancel-as-submit、
  replace-as-cancel、submit-as-cancel 都會 fail-closed 到
  `CommandRequestFieldMissing`。

Verification：

- Rust format checks PASS。
- Lane IPC acceptance `9 passed`。
- Lane IPC + Phase0 manifest `15 passed`。
- Full openclaw_types PASS：`35` unit/golden + `209` integration/acceptance +
  `0` doc-tests。
- Engine Stock/ETF cargo filter `21 passed`。
- Workspace `cargo check` PASS。
- `git diff --check` PASS。

PM 判定：checkpoint 可接受，但仍不是 Phase 1 runtime approval 或 paper-order
approval。未批准 IBKR contact、secret、connector runtime、Phase 1/2/3/4/5 runtime
start、paper order/cancel/replace、fill import、DB apply、Postgres dry-run、
evidence clock、scorecard writer、tiny-live、live、Linux runtime sync/restart 或
Bybit behavior change。

## 2026-06-30 PM Session Checkpoint — Paper-Shadow Reconciliation Contract

PM 已在本 session 追加 Phase 3 前置 source-only checkpoint：
`stock_etf_paper_shadow_reconciliation_v1`。這是 contract/test/status hardening，
不是 reconciliation writer、fill importer、shadow fill generator 或 scorecard writer。

已完成：

- Rust `openclaw_types` 新增 `StockEtfPaperShadowReconciliationV1`，作為未來
  paper lifecycle/fill facts、synthetic shadow fill 與 divergence threshold 之間的
  typed reconciliation contract。
- Validator 固定 stock/ETF + IBKR + `paper_shadow` scope、read-only authority、
  effect-capable false posture，並要求 reconciliation/order/execution/commission/
  shadow-signal identities 與 lifecycle/event-log/paper-fill import/shadow-signal/
  shadow-fill/cost-model/market-data/divergence-threshold/paper-shadow-link/source
  hashes。
- Validator 要求 append-only event ready、paper fill imported、synthetic shadow fill、
  positive threshold、divergence within threshold、zero unmatched paper/shadow fills。
- Validator 拒絕 IBKR contact、connector runtime、secret serialization、fill import
  side effect、shadow fill generation、reconciliation writer、scorecard writer、DB apply、
  order routing、Bybit path reuse、tiny-live/live、margin/short/options/CFD、Python direct
  broker write。
- Phase0 manifest source + JSON、FastAPI Phase0 count/fixtures/tests、Phase0 packet spec、
  settings README 均更新到 32 contracts。
- Rust `stock_etf.get_reconciliation_status` 與 FastAPI reconciliation normalizer 現在
  顯示並 fail-closed 檢查 reconciliation contract id、accepted/blockers、paper-shadow
  link hash、paper fill imported、synthetic shadow fill 與 writer/side-effect flags。

Verification：

- Reconciliation acceptance `5 passed`。
- Phase0 manifest acceptance `6 passed`。
- FastAPI Phase0/reconciliation focused `9 passed`。
- Engine reconciliation status focused `1 passed`。
- Engine Stock/ETF cargo filter `27 passed`（既有 warnings only）。
- Workspace `cargo check` PASS。
- Rust format check PASS；`git diff --check` PASS。

PM 判定：checkpoint 可接受，但仍不是 Phase 3 runtime approval、reconciliation writer
approval、fill importer approval、shadow fill generator approval 或 scorecard writer
approval。未批准 IBKR contact、secret、connector runtime、Phase 1/2/3/4/5 runtime
start、fill import、shadow fill generation、DB apply、Postgres dry-run、paper order/cancel/
replace、evidence clock、scorecard writer、tiny-live、live、Linux runtime sync/restart 或
Bybit behavior change。

## 2026-06-30 PM Session Checkpoint — Reconciliation GUI Contract Display

PM 已在本 session 追加 display-only checkpoint：Stock/ETF Reconciliation GUI
contract display hardening。這是 GUI 抽檔與顯示欄位同步，不是 runtime reconciliation。

已完成：

- 新增 `/static/tab-stock-etf-reconciliation.js`，從主 `tab-stock-etf.js` 抽出
  reconciliation fallback/render；主 JS 從 1951 行降到 1847 行。
- Reconciliation panel 顯示 `stock_etf_paper_shadow_reconciliation_v1` 的 expected/
  actual contract id、accepted/blockers、contract reconciliation run id、paper-shadow
  link hash、paper fill imported、shadow fill synthetic，以及 reconciliation writer /
  IBKR contact / connector runtime / secret serialization / fill import / shadow fill
  generation flags。
- HTML 載入新檔；static route contract test 與 Stock/ETF no-write static guard
  都把新檔納入掃描。

Verification：

- Node syntax check PASS for `tab-stock-etf-reconciliation.js` and main
  `tab-stock-etf.js`。
- GUI line counts PASS：HTML 396、main JS 1847、reconciliation JS 177、phase0 JS 149、
  release-packet JS 138、disable-cleanup JS 132。
- Focused route/static/no-write pytest `13 passed`。
- Full Stock/ETF Python route/static suite `90 passed`。

PM 判定：checkpoint 可接受，但仍不是 runtime reconciliation approval。未批准 IBKR
contact、secret、connector runtime、reconciliation writer、fill import、shadow fill
generation、scorecard writer、DB apply、paper order/cancel/replace、evidence clock、
tiny-live、live、Linux runtime sync/restart 或 Bybit behavior change。

## 2026-06-30 PM Session Checkpoint — Shadow Signal Request Contract + IPC Binding

PM 已在本 session 追加 source-only checkpoint：
`stock_etf_shadow_signal_request_v1` + `stock_etf.evaluate_shadow_signal` IPC binding。
這是 typed contract / handler gate，不是 shadow runtime 或 collector。

已完成：

- Rust `openclaw_types` 新增 `StockEtfShadowSignalRequestV1`，固定
  Stock/ETF + IBKR + shadow identity、`EvaluateShadowSignal` IPC method、
  `ShadowSignalEmit` operation、`ShadowOnly` authority、`effect_capable=false`。
- Validator 要求 request/evaluation/signal identity，以及 evidence clock、PIT
  universe、strategy hypothesis、instrument identity、market-data provenance、cost
  model、asset-lane event、source artifact lineage hashes。
- Validator 拒絕 IBKR contact、connector runtime、secret serialization、shadow signal
  emission、shadow fill generation、scorecard writer startup、DB apply、order routing、
  Bybit path reuse、live/tiny-live authority、margin/short/options/CFD、Python direct
  broker writes。
- Added blocked secret-free template and synchronized Phase0 manifest source, repository
  manifest JSON, FastAPI Phase0 count, route fixtures/tests, settings README, and Phase0
  packet spec. Contract count is now 31.
- IPC handler now returns `shadow_signal_request` verdict and requires
  `shadow_signal_request_accepted_for_ipc` for top-level `allowed`.

Verification：

- Shadow signal request acceptance `5 passed`。
- Phase0 manifest acceptance `6 passed`。
- FastAPI Phase0 route `4 passed`；FastAPI StockETF focused `14 passed`。
- Engine shadow-signal IPC focused `2 passed`。
- Engine Stock/ETF cargo filter `27 passed`（既有 warnings only）。
- Workspace `cargo check` PASS。
- scoped `rustfmt --check` PASS；`git diff --check` PASS。

PM 判定：checkpoint 可接受，但仍不是 Phase 3 runtime approval、shadow collector
approval、signal emission approval、scorecard writer approval 或 paper-shadow launch
approval。未批准 IBKR contact、secret、connector runtime、Phase 1/2/3/4/5 runtime
start、shadow signal emission、shadow fill generation、fill import、DB apply、
Postgres dry-run、paper order/cancel/replace、evidence clock、scorecard writer、
tiny-live、live、Linux runtime sync/restart 或 Bybit behavior change。

## 2026-06-30 PM Session Checkpoint — Paper Fill Import IPC Binding

PM 已在本 session 追加 Phase 1D source-only checkpoint：
`stock_etf.import_paper_fills` IPC typed request binding。這是 handler/test
hardening，不是 fill importer 或 DB persistence。

已完成：

- Rust IPC handler 現在會對 `stock_etf.import_paper_fills` params 嘗試解析
  `StockEtfPaperFillImportRequestV1`。
- Response 新增 `fill_import_request` verdict，包含 parse status、expected/request
  method、IPC method match、validator blockers、read-only authority posture、lineage
  field presence、boundary flags。
- Minimal/stale params 會 fail closed 為 `fill_import_request_parse_failed`，但仍不
  觸碰 legacy Bybit paper channel、不觸碰 IBKR、不啟動 connector。
- Valid fill-import request 可通過 typed validator，但 top-level 仍是 no-runtime
  fixture：`runtime_authority_denied=true`，且 IBKR/secret/routing/Bybit side-effect
  fields 全部 false。
- `allowed` 現在同時受 broker capability decision、paper request envelope verdict
  與 fill-import request verdict 約束。

Verification：

- Rust format check PASS。
- Engine fill-import IPC focused `2 passed`。
- Fill import request acceptance `6 passed`。
- Engine Stock/ETF cargo filter `25 passed`（既有 warnings only）。
- Workspace `cargo check` PASS。
- `git diff --check` PASS。

PM 判定：checkpoint 可接受，但仍不是 Phase 1 runtime approval、fill importer
approval、lifecycle writer approval、DB persistence approval 或 paper-order approval。
未批准 IBKR contact、secret、connector runtime、Phase 1/2/3/4/5 runtime start、
fill import、DB apply、Postgres dry-run、paper order/cancel/replace、evidence clock、
scorecard writer、tiny-live、live、Linux runtime sync/restart 或 Bybit behavior change。

## 2026-06-30 PM Session Checkpoint — Paper Lifecycle State Machine

PM 已在本 session 追加 Phase 1D source-only checkpoint：
`ibkr_paper_order_lifecycle_v1` / `broker_lifecycle_event_log_v1` state-machine
contract hardening。這是 Rust contract/test/spec/template hardening，不是 lifecycle
writer 或 paper order runtime。

已完成：

- `BrokerLifecycleEventLogV1` 新增 event sequence、genesis marker、previous event
  hash、event hash、`stock_etf_paper_order_request_v1` request contract id、
  request envelope hash、stale-state policy。
- Validator 要求 non-genesis event 有 previous event hash；genesis event 必須
  sequence `1` 且 previous hash empty；所有 event 必須有 event hash 與 request
  envelope hash。
- Validator 要求 exact paper environment，並新增 submit/cancel/replace/fill-import
  operation-to-transition matrix，避免 submit 冒充 fill、cancel 冒充 replace、
  replace 冒充 fill/cancel。
- Denied event 不能推進 active broker state；`STATE_UNKNOWN` manual-review 與
  terminal reconciliation policy 分開檢查。
- Blocked TOML template 與 Phase 0 named contract packet spec 已同步。

Verification：

- Lifecycle acceptance `12 passed`。
- Linked acceptance：lifecycle `12` + paper request `8` + lane IPC `9` + Phase0
  manifest `6` passed。
- Engine Stock/ETF cargo filter `21 passed`（既有 warnings only）。
- Full openclaw_types `35` unit/golden + `221` integration/acceptance +
  `0` doc-tests。
- Workspace `cargo check` PASS。
- Rust format check PASS；`git diff --check` PASS。

PM 判定：checkpoint 可接受，但仍不是 Phase 1 runtime approval、lifecycle writer
approval 或 paper-order approval。未批准 IBKR contact、secret、connector runtime、
Phase 1/2/3/4/5 runtime start、paper order/cancel/replace、fill import、DB apply、
Postgres dry-run、evidence clock、scorecard writer、tiny-live、live、Linux runtime
sync/restart 或 Bybit behavior change。本 turn 因可用 multi-agent tool policy
限制「必須 operator 明確要求 subagent 才能 spawn」，未派 E1/E2/E4 subagent；PM
用本地 focused/full regression 完成 verification。

## 2026-06-30 PM Session Checkpoint — Paper Status Lifecycle Surface

PM 已在本 session 追加 source-only checkpoint：paper-status lifecycle surface
hardening。這是 Rust IPC read-only fixture、FastAPI normalizer/route guard、GUI
display 與 tests 的收斂，不是 lifecycle writer 或 paper-order runtime。

已完成：

- `stock_etf.get_paper_status` 現在輸出 lifecycle request contract id、event
  sequence、genesis marker、previous/event hash presence、request-envelope hash
  presence、stale-state policy presence。
- FastAPI paper-status normalizer 現在 machine-checks 這些 state-machine 欄位；
  stale lifecycle shape 會被標記為 `paper_lifecycle_state_machine_fields_missing`
  並 fail-closed。
- Pre-gate event-chain/request-envelope/stale-policy readiness claim 會被轉成
  `contract_violation_blocked`；`paper_order_entry_visible` 與 `order_routed` 保持
  false。
- GUI paper lifecycle panel 顯示 request contract、sequence/hash/stale-policy 與
  reconstructability 欄位，fallback shape 也同步保持 display-only blocked。

Verification：

- Python compile PASS for changed paper-status common/normalizer/fixture/test files。
- Focused paper-status route tests `6 passed`。
- Wider Stock/ETF FastAPI/static tests `19 passed`。
- JS syntax check PASS。
- Rust format check PASS。
- Engine `stock_etf_paper_status` focused test PASS。
- Engine Stock/ETF cargo filter `21 passed`（既有 warnings only）。
- Workspace `cargo check` PASS。

PM 判定：checkpoint 可接受，但仍不是 Phase 1 runtime approval、lifecycle writer
approval 或 paper-order approval。未批准 IBKR contact、secret、connector runtime、
Phase 1/2/3/4/5 runtime start、paper order/cancel/replace、fill import、DB apply、
Postgres dry-run、evidence clock、scorecard writer、tiny-live、live、Linux runtime
sync/restart 或 Bybit behavior change。

## 2026-06-30 PM Session Checkpoint — Paper IPC Request Envelope Binding

PM 已在本 session 追加 Phase 1D source-only checkpoint：Rust IPC paper request
envelope binding。這是 handler/test hardening，不是 paper order runtime。

已完成：

- `stock_etf.preview_paper_order` / `submit_paper_order` / `cancel_paper_order` /
  `replace_paper_order` 現在會嘗試解析 params 為
  `StockEtfPaperOrderRequestEnvelopeV1`。
- Response 新增 `request_envelope` verdict，包含 parse status、expected/request
  method、IPC method match、validator blockers、authority/effect posture、lineage
  field presence、boundary flags。
- Minimal/stale params 會顯示 `request_envelope_parse_failed`，但不觸碰 legacy
  Bybit paper channel。
- Valid preview envelope 可通過 typed validator，但仍保留
  `runtime_authority_denied=true`，不產生 IBKR contact、secret touch 或 order routing。
- Valid submit envelope 若送到 cancel IPC method，會被 IPC binding 擋成
  `ipc_method_mismatch`，不能 accepted-for-IPC。

Verification：

- Rust format check PASS。
- Engine Stock/ETF cargo filter `23 passed`（既有 warnings only）。
- Paper request acceptance `8 passed`。
- Workspace `cargo check` PASS。

PM 判定：checkpoint 可接受，但仍不是 Phase 1 runtime approval、lifecycle writer
approval 或 paper-order approval。未批准 IBKR contact、secret、connector runtime、
Phase 1/2/3/4/5 runtime start、paper order/cancel/replace、fill import、DB apply、
Postgres dry-run、evidence clock、scorecard writer、tiny-live、live、Linux runtime
sync/restart 或 Bybit behavior change。

## 2026-06-30 PM Session Checkpoint — Paper Fill Import Request Contract

PM 已在本 session 追加 Phase 1D source-only checkpoint：
`stock_etf_paper_fill_import_request_v1`。這是 contract/test/template/spec
hardening，不是 fill importer 或 DB persistence。

已完成：

- Rust `openclaw_types` 新增 `StockEtfPaperFillImportRequestV1`，作為未來
  `stock_etf.import_paper_fills` 入口與 lifecycle reconstruction 之間的 typed
  request contract。
- Validator 固定 stock/ETF + IBKR + paper identity，read-only fill-import authority，
  session/lifecycle/event-log/redaction/source lineage，broker order/execution/
  commission ids，import idempotency，observed order state，stale-state policy，
  raw/redacted artifact hashes。
- Validator 拒絕 duplicate import、stale unknown state without policy、IBKR contact、
  connector runtime、secret serialization、fill import side effect、DB apply、order
  routing、Bybit path reuse、live/tiny-live authority、margin/short/options/CFD、Python
  direct broker writes。
- Added blocked secret-free template and synchronized Phase0 manifest source, repository
  manifest JSON, FastAPI Phase0 count, route fixtures/tests, and Phase0 packet spec.
  Contract count is now 30.

Verification：

- Fill import request acceptance `6 passed`。
- Phase0 manifest acceptance `6 passed`。
- FastAPI Phase0/StockETF focused tests `14 passed`。
- Full openclaw_types `35` unit/golden + `227` integration/acceptance +
  `0` doc-tests。
- Engine Stock/ETF cargo filter `23 passed`（既有 warnings only）。
- Workspace `cargo check` PASS。

PM 判定：checkpoint 可接受，但仍不是 Phase 1 runtime approval、fill importer
approval、lifecycle writer approval 或 paper-order approval。未批准 IBKR contact、
secret、connector runtime、Phase 1/2/3/4/5 runtime start、fill import、DB apply、
Postgres dry-run、paper order/cancel/replace、evidence clock、scorecard writer、
tiny-live、live、Linux runtime sync/restart 或 Bybit behavior change。

## 2026-06-30 PM Session Checkpoint — Paper Request Envelope Contract

PM 已在本 session 追加 Phase 1D source-only checkpoint：
`stock_etf_paper_order_request_v1` typed request envelope。這是 contract/test/docs
hardening，不是 paper order runtime。

已完成：

- Rust `openclaw_types` 新增 `StockEtfPaperOrderRequestEnvelopeV1`，作為
  lane-scoped IPC 與 IBKR paper lifecycle 之間的 typed request contract。
- Validator 固定 stock/ETF + IBKR + paper identity，並驗證 request method、
  broker operation、authority scope、effect-capable flag 必須對映 preview / submit /
  cancel / replace。
- Preview/submit request shape 現在 machine-checks normalized symbol、stock/ETF
  instrument kind、buy/sell side、market/limit order type、positive decimal
  quantity、explicit limit-price policy、day/GTC time-in-force。
- Submit additionally requires session/scoped authorization/Decision Lease/
  Guardian/risk/instrument/lifecycle/capability/audit lineage and local
  order/idempotency ids; broker order id is rejected before broker ack.
- Cancel requires local order id, broker order id, cancel reason, idempotency,
  lifecycle/capability/audit lineage, and rejects submit order-shape pollution.
- Replace requires original local/broker ids plus replacement idempotency,
  quantity, limit-price policy, time-in-force, replace reason, and rejects
  original mutable-field pollution.
- Phase0 manifest source + JSON now include `stock_etf_paper_order_request_v1`;
  contract count is now 29, with FastAPI Phase0 normalizer/tests updated.
- Added blocked secret-free template
  `settings/broker/stock_etf_paper_order_request.template.toml`.

Verification：

- Python compile PASS for changed Phase0 normalizer/test fixture files.
- Paper request acceptance `8 passed`; Phase0 manifest `6 passed`.
- Lane IPC acceptance `9 passed`.
- FastAPI Phase0/StockETF focused tests `14 passed`.
- Engine Stock/ETF cargo filter `21 passed`（既有 warnings only）。
- Full openclaw_types PASS：`35` unit/golden + `217` integration/acceptance +
  `0` doc-tests。
- Workspace `cargo check` PASS。
- `rustfmt --check` PASS。
- `git diff --check` PASS。

PM 判定：checkpoint 可接受，但仍不是 Phase 1 runtime approval 或 paper-order
approval。未批准 IBKR contact、secret、connector runtime、Phase 1/2/3/4/5 runtime
start、paper order/cancel/replace、fill import、DB apply、Postgres dry-run、
evidence clock、scorecard writer、tiny-live、live、Linux runtime sync/restart 或
Bybit behavior change。

## 2026-06-30 PM Session Checkpoint — Scorecard Reconciliation Lineage Gate

PM 已在本 session 追加 Phase 3 source/status/display-only checkpoint：
`stock_etf_scorecard_verdict_v1` reconciliation lineage gate。這是 scorecard
contract/status/GUI hardening，不是 scorecard writer。

已完成：

- Scorecard verdict contract 新增 `paper_shadow_reconciliation_hash`，並以
  SHA-256 hex validator 作為硬 gate。
- Default verdict 與 blocked template 均保持 fail closed；positive fixture 必須攜帶
  reconciliation hash 才能通過。
- Rust `stock_etf.get_scorecard_status` 回報
  `paper_shadow_reconciliation_hash_present=false`，維持 source-only blocked status。
- FastAPI normalizer/tests 會阻擋 pre-gate payload 宣稱 reconciliation hash present。
- GUI scorecard panel 顯示 reconciliation hash gate，避免 Operator 將 scorecard
  readiness 與 paper-shadow reconciliation 脫鉤。

Verification：

- Scorecard verdict acceptance `8 passed`。
- Focused FastAPI/static tests `15 passed`。
- Full Stock/ETF FastAPI/static tests `90 passed`。
- Engine Stock/ETF cargo filter `27 passed`（既有 warnings only）。
- Full openclaw_types PASS：`35` unit/golden + `236` integration/acceptance +
  `0` doc-tests。
- Workspace `cargo check` PASS。
- `rustfmt --check` PASS。
- `node --check` PASS。

PM 判定：checkpoint 可接受，但仍不是 Phase 3 evidence clock approval、reconciliation
writer approval、scorecard writer approval 或 paper-shadow launch approval。未批准 IBKR
contact、secret、connector runtime、Phase 1/2/3/4/5 runtime start、paper order/cancel/
replace、fill import、shadow fill generation、reconciliation writer、scorecard writer、
DB apply、Postgres dry-run、evidence clock、tiny-live、live、Linux runtime sync/restart
或 Bybit behavior change。

## 2026-06-30 PM Session Checkpoint — Scorecard Derivation Contract

PM 已在本 session 追加 Phase 3 source/status/display-only checkpoint：
`stock_etf_scorecard_derivation_v1`。這是 scorecard derivation artifact contract 與
display hardening，不是 scorecard writer。

已完成：

- Rust `openclaw_types` 新增 `StockEtfScorecardDerivationV1` 與 blocked template。
- Contract pins input bundle、evidence-clock/DQ manifest、paper-shadow reconciliation、
  formula/preregistration、scorecard manifest、verdict、source commit/code/output
  artifact、QC/MIT/QA review hashes。
- Validator 要求 derived-only、idempotent replay、paper/shadow fill separation、
  Bybit live unchanged、sealed；拒絕 IBKR contact、connector runtime、fill import、
  shadow fill generation、reconciliation writer、scorecard writer、DB/evidence clock、
  secret serialization、tiny-live/live authority。
- Rust/FastAPI/GUI scorecard status 現在顯示 blocked `scorecard_derivation` block，
  並阻擋 pre-gate truthy derivation claims。

Verification：

- Scorecard derivation acceptance `5 passed`。
- Python compile PASS for scorecard normalizer/status common/tests/fixtures。
- Focused FastAPI/static tests `15 passed`。
- Full Stock/ETF FastAPI/static tests `90 passed`。
- Engine scorecard focused `1 passed`。
- Engine Stock/ETF cargo filter `27 passed`（既有 warnings only）。
- Full openclaw_types PASS：`35` unit/golden + `241` integration/acceptance +
  `0` doc-tests。
- Workspace `cargo check` PASS。
- `rustfmt --check` PASS。
- `node --check` PASS。

PM 判定：checkpoint 可接受，但仍不是 Phase 3 evidence clock approval、reconciliation
writer approval、scorecard writer approval、DB persistence approval 或 paper-shadow launch
approval。未批准 IBKR contact、secret、connector runtime、Phase 1/2/3/4/5 runtime
start、paper order/cancel/replace、fill import、shadow fill generation、reconciliation
writer、scorecard writer、DB apply、Postgres dry-run、evidence clock、tiny-live、live、
Linux runtime sync/restart 或 Bybit behavior change。

## 2026-06-30 PM Session Checkpoint — Tiny-Live Eligibility Lineage Gate

PM 已在本 session 追加 Phase 5 ADR-discussion gate hardening：
`tiny_live_adr_eligibility_v1` 現在必須帶 scorecard derivation、scorecard verdict、
paper-shadow reconciliation 與 QA lineage。這是 source/status/display-only hardening，
不是 tiny-live approval。

已完成：

- Rust tiny-live eligibility contract 新增 `scorecard_derivation_hash`、
  `scorecard_verdict_hash`、`paper_shadow_reconciliation_hash`、`qa_review_hash`
  與 `qa_review_passed`。
- Validator 新增 derivation/verdict/reconciliation/QA hash blockers 與
  `QaReviewMissing`；default/template 仍 fail closed。
- Rust `stock_etf.get_launch_status`、FastAPI normalizer/tests/fixtures 與 GUI launch
  panel 顯示 blocked lineage-present booleans。
- FastAPI launch-status guard 會阻擋 pre-gate truthy lineage 或 QA review pass claims。
- Phase0 packet spec 與 broker README 已同步。

Verification：

- Tiny-live eligibility acceptance `7 passed`。
- Python compile PASS for launch normalizer/test/fixtures。
- Focused FastAPI/static tests `15 passed`。
- Full Stock/ETF FastAPI/static tests `90 passed`。
- Engine launch-status focused `1 passed`（既有 warnings only）。
- Engine Stock/ETF cargo filter `27 passed`（既有 warnings only）。
- Full openclaw_types PASS：`35` unit/golden + `241` integration/acceptance +
  `0` doc-tests。
- Workspace `cargo check` PASS。
- `rustfmt --check` PASS。
- `node --check` PASS。
- `git diff --check` PASS。

PM 判定：checkpoint 可接受，但仍不是 ADR approval、tiny-live approval、live approval、
Phase 5 release approval 或 runtime approval。未批准 IBKR contact、secret、
connector runtime、Phase 1/2/3/4/5 runtime start、paper order/cancel/replace、
fill import、shadow fill generation、reconciliation writer、scorecard writer、DB apply、
Postgres dry-run、evidence clock、tiny-live、live、Linux runtime sync/restart 或 Bybit
behavior change。

## 2026-06-30 PM Session Checkpoint — IBKR Read-Only Connector Skeleton Boundary

PM 已在本 session 追加隔離 Python connector skeleton：
`program_code/broker_connectors/ibkr_connector/`。這是 source-only boundary，
不是 runtime connector。

已完成：

- 新增 connector package + README，位置不在既有 Bybit connector tree 下。
- `models.py` 定義 non-secret loopback descriptor 與 blocked read-only status。
- `readonly_client.py` 只回傳 blocked readiness/account/market-data/contract-detail
  previews，不導入 IBKR SDK、不開 network、不讀 secret。
- `paper_client.py` 只回傳 paper lifecycle / fill-import readiness previews，明確
  Python 無 broker write authority。
- 新增 dedicated skeleton tests；既有 Python no-write static guard 會 AST 掃描新
  connector package。
- Phase0 packet spec 已同步。

Verification：

- Python compile PASS for connector package and skeleton test。
- Connector skeleton + no-write static guard `7 passed`。
- Full Stock/ETF FastAPI/static tests `94 passed`。

PM 判定：checkpoint 可接受，但仍不是 Phase 2 read-only contact approval、secret-slot
approval、connector runtime approval、paper-order approval、fill-import approval 或 DB
persistence approval。未批准 IBKR contact、IBKR SDK import、socket/HTTP、secret、
connector runtime、Phase 1/2/3/4/5 runtime start、paper order/cancel/replace、
fill import、scorecard writer、DB apply、evidence clock、tiny-live、live、Linux runtime
sync/restart 或 Bybit behavior change。

## 2026-06-30 PM Session Checkpoint — ADR/Register Lineage Catch-up

PM 已補治理索引與 ADR/AMD，使 governance source of truth 反映本 session 最新
source gates。

已完成：

- `SPECIFICATION_REGISTER.md` Last Updated 改為 lineage + connector-skeleton
  hardening。
- 新增 ADR-0048 Addendum E：scorecard derivation/verdict/reconciliation/tiny-live
  lineage。
- 新增 ADR-0048 Addendum F：IBKR connector skeleton inert boundary。
- ADR-0048 與 AMD-2026-06-29-01 同步補明 tiny-live discussion lineage 與 Python
  skeleton denied paths。

Verification：

- Register/ADR/AMD `rg` check PASS。
- `git diff --check` PASS。

PM 判定：checkpoint 可接受，但只是 governance catch-up。未批准 IBKR contact、
IBKR SDK import、socket/HTTP、secret、connector runtime、Phase 1/2/3/4/5 runtime
start、paper order/cancel/replace、fill import、scorecard writer、DB apply、
evidence clock、tiny-live、live、Linux runtime sync/restart 或 Bybit behavior change。

## 2026-06-30 PM Session Checkpoint — Connector Skeleton Readiness Gate

PM 已把 inert IBKR connector skeleton boundary 接入 display-only readiness surface。
這不是 connector runtime，也沒有 import 新 connector package。

已完成：

- FastAPI readiness normalizer 新增 fail-closed `connector_skeleton` block。
- Pre-gate truthy claims：accepted、non-blocked status、network contact、secret load、
  paper/live channel、write method、Bybit path reuse，全部會被
  `contract_violation_blocked` 擋下。
- GUI readiness panel 顯示 connector skeleton surface/status 與 side-effect flags。
- Route tests 覆蓋 fallback、正常 blocked display、truthy violation。

Verification：

- Python compile PASS。
- Focused readiness/no-write tests `9 passed`。
- Full Stock/ETF FastAPI/static tests `94 passed`。
- `node --check` PASS。
- `git diff --check` PASS。

PM 判定：checkpoint 可接受，但只是 display hardening。未批准 IBKR contact、
IBKR SDK import、socket/HTTP、secret、connector runtime、Phase 1/2/3/4/5 runtime
start、paper order/cancel/replace、fill import、scorecard writer、DB apply、
evidence clock、tiny-live、live、Linux runtime sync/restart 或 Bybit behavior change。
