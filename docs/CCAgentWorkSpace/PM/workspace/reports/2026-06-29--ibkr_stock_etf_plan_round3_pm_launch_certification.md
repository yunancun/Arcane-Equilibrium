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

- Phase 0 packet does not yet exist as accepted artifacts.
- Phase 1-5 implementation and verification artifacts do not yet exist.
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
