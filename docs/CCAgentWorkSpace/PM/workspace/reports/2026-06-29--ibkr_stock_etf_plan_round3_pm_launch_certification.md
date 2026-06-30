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
