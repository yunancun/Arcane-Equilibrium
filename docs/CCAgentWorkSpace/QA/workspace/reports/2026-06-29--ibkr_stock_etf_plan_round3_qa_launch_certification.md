STATUS: DONE
CERTIFICATION: CERTIFIABLE_IF_GATES_PASS, SCOPE=paper_shadow_only, FINDINGS=0(C:0/H:0/M:0/L:0)

# QA Round 3 Launch Certification Closure Audit - IBKR Stock/ETF Paper + Shadow

Date: 2026-06-29
Role: QA(worker)
Task shape: third-round release-certification closure audit, report-only
Scope: `stock_etf_cash` productized paper/shadow lane only.
Boundary observed: no code/runtime/TODO edits, no IBKR/Bybit calls, no Linux/PG/services/secrets/network actions.

## Decision

Yes, under the exact premise in the task: if every Phase 0 named contract packet and every Phase 1-5 E2/E4/QA gate in the hardened plan passes exactly as written, QA can certify paper/shadow launch completeness for `stock_etf_cash`.

This is not a present-tense launch approval. Current repo state remains pre-Phase-0: the initiative index says the IBKR Stock/ETF lane is not in the active TODO queue and requires Phase 0 ADR/AMD + named contract packet approval first. The certification here is conditional closure of the launch-gate question: no additional QA launch gate is missing beyond the hardened plan's named contract packets, phase gates, and final release packet.

## Basis

- The plan constrains the maximum allowed near-term state to IBKR read-only healthcheck, broker-paper order lifecycle rehearsal, shadow signal/fill/cost reconstruction, GUI evidence viewing, and explicitly excludes live IBKR, margin, short, options, CFD, transfer, and non-Bybit live (`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:25-35`).
- Phase 0 now names the required contract packets, including asset lane taxonomy, broker capability registry, API/session/attestation, feature/secret/auth matrix, lane-scoped IPC, evidence clock, paper lifecycle, DDL, market-data provenance, cash ledger, cost/benchmark versions, shadow fill model, GUI contract, storage capacity, kill/disable runbook, release packet, and tiny-live eligibility separation (`...arrangement.md:492-527`).
- Phase 1-5 now carry concrete blockers and acceptance gates: default-off type/config/schema/IPC foundation; external-surface gate before any IBKR healthcheck; evidence-clock/DQ and reproducible scorecard gates; GUI route/cache/auth partition and crypto regression gates; and a Phase 5 report with machine-checkable verdict labels while live remains forbidden (`...arrangement.md:537-670`).
- The hardened release criteria require `stock_etf_release_packet_v1` with role reports, E2/E4/QA logs, manifest hashes, PG dry-run logs, redaction fixtures, GUI screenshots, DQ manifests, and scorecard regeneration outputs before evidence collection (`...arrangement.md:695-711`).
- The second-round mandatory outputs directly close the prior QA gaps: external-surface gate, DDL/event references, storage, GUI contract, release packet, kill/disable runbook, and separate tiny-live ADR eligibility gate (`...arrangement.md:803-820`).

## What Complete Means

`complete` means the `stock_etf_cash` paper/shadow lane is productized enough to run as a governed, auditable research/evidence lane:

- all paper/shadow routes, configs, schemas, Rust IPC, broker-paper lifecycle, shadow collector, scorecard, GUI evidence views, and disable paths are implemented only from accepted contracts;
- every contract and phase gate has immutable evidence in `stock_etf_release_packet_v1`;
- the lane is default-off until its phase gate passes, fail-closed on unknown/live/CFD/margin/short/options/transfer states, and disableable without losing audit evidence;
- evidence collection can start only after the 5-trading-day pre-clock shakedown and `stock_etf_evidence_clock_v1` checker pass;
- the lane can produce preliminary engineering/evidence verdicts, not live authority or profit guarantees.

It does not mean no future product work exists. It means QA finds no launch-blocking omission for the paper/shadow lane against the hardened plan, assuming all named gates pass with artifacts.

## Final QA Launch Checklist

1. Accepted ADR/AMD exists and only approves `stock_etf_cash` read-only / broker-paper rehearsal / shadow research. It explicitly excludes IBKR live, tiny-live, margin, short, options, CFD, transfer, and any non-Bybit live authority.
2. Phase 0 named packet is accepted and hashed: `asset_lane_taxonomy_v1`, `broker_capability_registry_v1`, `non_bybit_api_allowlist_v1`, `ibkr_api_session_topology_v1`, `ibkr_session_attestation_v1`, `feature_flag_secret_auth_matrix_v1`, `lane_scoped_ipc_v1`, `stock_etf_evidence_clock_v1`, `ibkr_paper_order_lifecycle_v1`, `broker_lifecycle_event_log_v1`, `stock_etf_db_evidence_ddl_v1`, `stock_market_data_provenance_v1`, `broker_account_portfolio_cash_ledger_v1`, `cost_model_version_v1`, `benchmark_versions_v1`, `stock_shadow_fill_model_v1`, `gui_lane_contract_v1`, `stock_etf_storage_capacity_v1`, `stock_etf_kill_switch_and_disable_cleanup_runbook_v1`, `stock_etf_release_packet_v1`, and `tiny_live_adr_eligibility_v1` as a separation gate only.
3. PM records source-of-truth sync or no-sync rationale for ADR/README/CLAUDE/.codex/TODO. Chat-only approval is not accepted.
4. Phase 1 E2/E4/QA gates pass: no catch-all broker/lane enum; no live/CFD/margin/short/options route; legacy Bybit/Paper `submit_paper_order` is not reused for stock/ETF; all flags default OFF; `crypto_perp` remains default; no runtime mutation.
5. DDL/evidence gate passes: accepted DDL/ERD with PK/FK/natural keys, CHECKs, indexes, storage/retention/compression, Guard A/B/C, Linux PG dry-run/double-apply evidence if migration apply is in scope, immutable atomic facts, and derived-only scorecard.
6. Phase 2 external-surface gate passes before any IBKR call: chosen API baseline, topology, API allowlist, secret contract, live slot absent/empty proof, redaction fixtures, rate limits, audit event, and paper/read-only attestation.
7. Paper fill import gate passes: reconstructable account/fill/commission data, stable broker ids, idempotency/duplicate/stale-state tests, no submit/cancel/replace capability, and manual-review/quarantine for unknown states.
8. Paper order rehearsal gate passes if paper rehearsal is enabled: Rust-owned lifecycle, signed scoped paper envelope, fresh Decision Lease, Guardian/risk, cost model, instrument tradability, market session, paper session attestation, loss controls, and append-only lifecycle audit in the same final window.
9. Python no-write guard passes: no direct IBKR submit/cancel/replace route, no generic authenticated writer bypass, and static/AST/route tests for selected API-family writer methods/endpoints.
10. Phase 3 evidence-clock gate passes: market-data vendor/tier, PIT universe, corporate actions, FX/cost/tax sources, benchmark, storage, paper/shadow divergence thresholds, statistical preregistration, and deterministic PASS/FAIL/QUARANTINED day-count checker.
11. Five trading-day pre-clock shakedown passes: calendar-aware coverage, symbol completeness, latency/DQ manifests, daily scorecard regeneration from atomic facts, GUI reconstructability, and no unresolved quarantine.
12. Phase 4 GUI gate passes: badge/readiness-first behavior, client lane state untrusted, route/cache/auth partition tests, disabled CFD/live no-write states, stock evidence export links, desktop/mobile screenshots, and existing crypto tabs/routes/Decision Lease/risk/scorecard unchanged.
13. Kill switch / disable cleanup gate passes: lane disable blocks new broker calls, preserves read-only status/audit, handles stale/unknown broker states, hides or deactivates GUI surfaces as specified, archives evidence, and proves live secret slot absent/empty.
14. Phase 5 evidence-window gate passes: 6-8 week report, QC/MIT/AI-E review, PM go/no-go, reproducible scorecard, DQ inclusion replay, paper-vs-shadow quarantine, and machine-checkable verdict labels: `engineering_ready`, `research_promising`, `profitability_feasible`, `insufficient_evidence`, `execution_model_invalid`, or `kill`.
15. Final `stock_etf_release_packet_v1` is assembled and QA-verifiable: manifests with hashes, command outputs, screenshots, role reports, E2/E4 logs, E3 security artifacts, QC/MIT evidence specs, PG logs if applicable, redaction outputs, DQ manifests, scorecard regeneration outputs, and disable/runbook paths.

## Explicit Exclusions

This certification excludes:

- IBKR live or tiny-live authority;
- margin, short, options, CFD, transfer, withdrawal, or account-management writes;
- any change to Bybit live/Demo/LiveDemo authority;
- any profitability guarantee, durable-alpha proof, or production/live readiness claim;
- automatic promotion from paper/shadow evidence to live/tiny-live;
- any external broker call, secret creation, runtime mutation, DB migration apply, GUI activation, or evidence clock before its own gate passes.

Positive paper/shadow results may at most open a separate tiny-live ADR discussion if `tiny_live_adr_eligibility_v1` passes. They do not authorize live execution.

## Missing Gates

None under the stated premise.

If any premise element is absent, stale, unreviewed, or not machine-checkable, the minimum blocking QA launch gate is the final `stock_etf_release_packet_v1` acceptance: it must prove that all Phase 0 contracts and Phase 1-5 E2/E4/QA gates passed with immutable artifacts and hashes. Without that packet, QA cannot certify launch completeness even if individual reports say PASS.

## PM Wording

PM may use this wording:

> QA can certify `stock_etf_cash` paper/shadow launch completeness if, and only if, the accepted Phase 0 named contract packet and every Phase 1-5 E2/E4/QA gate in the hardened plan pass with immutable release-packet evidence. This certification permits only the productized paper/shadow research lane and evidence collection. It does not authorize IBKR live/tiny-live, margin, short, options, CFD, transfer, or any profitability/durable-alpha guarantee. Any live/tiny-live path requires a separate ADR/authorization/spec and fresh review.

Final PM-facing decision: PAPER_SHADOW_LAUNCH_CERTIFIABLE_IF_ALL_GATES_PASS
