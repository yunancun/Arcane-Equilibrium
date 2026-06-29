# PM 二輪整合報告 — IBKR Stock/ETF Paper + Shadow 方案

日期：2026-06-29
角色：PM(default)
範圍：整合 CC / FA / PA / E3 / E5 / QC / MIT / QA 對
`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md`
的第二輪對抗性審查。
結論：工程方向有效；只批准 Phase 0。不能確認「無遺漏」，不能確認
「按排程後完整上線」，不能批准 Phase 1+ implementation。

## Verdict

**PM SIGN-OFF: CONDITIONAL / APPROVE_PHASE0_ONLY**

批准：

- Phase 0 ADR/AMD + interface/security/data/GUI/evidence/QA release packet。
- 繼續以 IBKR 作 `stock_etf_cash` paper/shadow 第一 baseline 的研究性設計。
- 把二輪發現轉成 machine-checkable gates。

不批准：

- Phase 1+ 實作。
- IBKR read-only healthcheck 或任何外部 IBKR API 接觸。
- IBKR secret slot 建立。
- IBKR paper fill import 或 paper order rehearsal。
- GUI runtime activation / login lane selector。
- 6-8 週 evidence clock 起算。
- 任何 tiny-live / live / margin / short / options / CFD / transfer。

## Role Results

| Role | Verdict | Severity summary | Report |
|---|---|---|---|
| CC | DONE_WITH_CONCERNS | C0 / H3 / M3 / L0 | `docs/CCAgentWorkSpace/CC/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_cc_review.md` |
| FA | DONE_WITH_CONCERNS | C1 / H4 / M2 / L0 | `docs/CCAgentWorkSpace/FA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_fa_review.md` |
| PA | DONE_WITH_CONCERNS | C1 / H4 / M3 / L0 | `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_pa_review.md` |
| E3 | DONE_WITH_CONCERNS | C0 / H3 / M3 / L0 | `docs/CCAgentWorkSpace/E3/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_e3_review.md` |
| E5 | DONE_WITH_CONCERNS | C0 / H2 / M3 / L0 | `docs/CCAgentWorkSpace/E5/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_e5_review.md` |
| QC | DONE_WITH_CONCERNS | C0 / H3 / M3 / L0 | `docs/CCAgentWorkSpace/QC/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_qc_review.md` |
| MIT | DONE_WITH_CONCERNS | C2 / H5 / M1 / L0 | `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_mit_review.md` |
| QA | DONE_WITH_CONCERNS | C1 / H4 / M3 / L0 | `docs/CCAgentWorkSpace/QA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_qa_review.md` |

All roles returned `APPROVE_PHASE0_ONLY`.

## Deduplicated Findings

### B1 — Scheduled full-online claim is not supportable

The current plan is a Phase 0 governance/spec packet. It cannot certify no
omissions, implementation readiness, production readiness, IBKR live readiness,
or profitability. The correct operator-facing wording is: Phase 0 can proceed;
everything after it is gated.

Required action: avoid `fully online`, `live ready`, or `complete上线` wording.
Use phase-specific gates and release packets.

### B2 — Phase 0 must include interface/spec packets, not only ADR prose

PA/QA/E5 independently flagged that Phase 0/Phase 1 boundaries still risk E1
inventing interfaces during implementation. That would create shallow modules
and ad hoc connector debt.

Required action: Phase 0 now includes `broker_capability_registry_v1`,
`lane_scoped_ipc_v1`, `ibkr_paper_order_lifecycle_v1`,
`broker_lifecycle_event_log_v1`, `stock_etf_db_evidence_ddl_v1`,
`gui_lane_contract_v1`, `stock_etf_evidence_clock_v1`, and related packets.

### B3 — First IBKR healthcheck needs an external-surface gate

E3 and CC agree that read-only healthcheck is still non-Bybit external contact
and may expose secrets/session/runtime topology.

Required action: no IBKR healthcheck until `phase2_ibkr_external_surface_gate_v1`
passes: accepted ADR, API family choice, topology, secret contract, allowlist,
redaction suite, live-slot absent/empty proof, audit event, rate limits, and
paper/read-only attestation.

### B4 — DB/evidence design is not implementation-ready

MIT found the largest irreversible-data-debt risk: table names and requirement
lists are not a DDL contract. Starting schema/collector work too early could
lock in bad instrument joins, raw/adjusted data mixing, missing cash/FX/cost
lineage, and scorecard-as-truth.

Required action: Phase 0 must produce DDL/ERD with PK/FK/natural keys, CHECKs,
indexes, hypertable/retention/compression, Guard A/B/C, Linux PG dry-run plan,
immutable atomic facts, and derived-only scorecards.

### B5 — GUI must start with badge/readiness, not a first-screen selector

FA/PA/E5/QA all flagged the same UX/control risk: a login selector can look
like authority. Client lane state must remain untrusted.

Required action: Phase 4A is `crypto_perp` default badge/readiness/status-only.
Full lane selector comes later after server-side route/cache/auth negative tests
and crypto regression pass.

### B6 — Evidence window is a screening gate, not durable-alpha proof

QC and MIT agree the 6-8 week window can support engineering shakedown and
preliminary feasibility only. Low-frequency strategies may remain underpowered.

Required action: pre-register independent sample counts, benchmarks, costs,
paper-vs-shadow divergence, regime labels, PSR/DSR or equivalent deflation, and
verdict labels. Positive but underpowered results become `research_promising` or
`insufficient_evidence`, not tiny-live readiness.

### B7 — QA release packet and rollback/disable runbook are mandatory

QA/E5 found that the plan lacked concrete release artifacts, command outputs,
manifest paths, rollback/disable behavior, and failed evidence-day handling.

Required action: add `stock_etf_release_packet_v1` and
`stock_etf_kill_switch_and_disable_cleanup_runbook_v1`; include role reports,
hashes, screenshots, PG logs, redaction fixtures, DQ manifests, scorecard
regeneration outputs, lane disable proof, evidence archival, and secret absence
proof.

### B8 — Storage/capacity must be specified before collectors

E5/MIT flagged unbounded data growth risk for quotes/bars/orders/scorecards.

Required action: add `stock_etf_storage_capacity_v1` before any market-data
collector or daily writer: universe size, frequency, row volume, retention,
compression, index budget, raw payload hash retention, and query SLO.

## Plan Patch Applied

PM updated the main execution plan after round 2:

- Added second-round PM conclusion to §0.
- Replaced first-screen GUI selector wording with badge/readiness-first rollout.
- Expanded Phase 0 into ADR + interface/security/data/GUI/evidence/QA release packet.
- Reframed Phase 1 as implementation of accepted contracts only.
- Added `phase2_ibkr_external_surface_gate_v1` before any IBKR healthcheck.
- Tightened Phase 3 evidence-clock, DQ, storage, and regeneration requirements.
- Split GUI rollout into Phase 4A/4B/4C.
- Reworded Phase 5 as preliminary feasibility screen only.
- Updated estimates and operator decision checklist.
- Added §12 second-round gate matrix and mandatory outputs.

## PM Decision

The plan is valid only as a Phase 0 exploration packet. The way to avoid
technical debt is not to start a connector early; it is to freeze the contracts
first, with denial behavior, evidence lineage, test surfaces, and cleanup paths
defined before E1 implementation.

Next allowed dispatch:

- `PM -> CC -> FA -> PA -> E3 -> E5 -> QC -> MIT -> QA -> PM`
- Scope: produce Phase 0 ADR/AMD + named contract packet.
- No runtime, no IBKR API, no secret slot, no GUI activation, no DB migration
  apply, no evidence clock.

Next blocked dispatch:

- Any Phase 1 code implementation before Phase 0 packet is accepted.
- Any IBKR healthcheck, secret, API/session, fill import, paper order rehearsal.
- Any tiny-live/live discussion not routed through a new ADR/spec/runbook.

## Verification

- Sub-agent work was report-only.
- PM integration did not touch Linux `trade-core`, PG, IBKR, Bybit, services,
  secrets, runtime flags, or live authorization.
- Unrelated worktree changes outside this doc set were not staged or reverted.
