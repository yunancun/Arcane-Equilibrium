STATUS: DONE
CERTIFICATION: CERTIFIABLE_IF_GATES_PASS, SCOPE=paper_shadow_only, FINDINGS=0(C:0/H:0/M:0/L:0)

# FA Round 3 Launch-Certification Closure Audit - IBKR `stock_etf_cash`

Date: 2026-06-29
Role: FA(default)
Scope owner: functional completeness / product workflow launch certification
Boundary: report-only; no code, runtime, TODO, IBKR, Bybit, Linux, PG, services, secrets, or network touched.

## Decision

Yes - under the operator's narrowed definition of "fully online", FA can certify product-workflow completeness **if and only if** every Phase 0 named contract packet and every Phase 1-5 gate in the hardened plan passes exactly as written.

Certified scope is only:

- `stock_etf_cash` read-only / broker-paper rehearsal / shadow evidence lane.
- IBKR read-only account and market-data health evidence.
- IBKR broker-paper order lifecycle rehearsal evidence, routed through Rust authority.
- Shadow signals, synthetic fills, conservative fill/cost reconstruction, daily scorecard, evidence clock, GUI evidence views, release packet, and disable/cleanup workflow.

This is not a current readiness certification. It is a conditional certification of the hardened plan's completed end state. If any required contract packet or gate is missing, stale, partially passed, or passed by prose instead of artifact/test evidence, the certification collapses to not certifiable.

## Why Round 3 Can Certify Conditionally

Round 2 correctly could not certify "no omissions" because the plan was still a blocker register. The hardened plan now front-loads the missing product workflow contracts into Phase 0 and makes Phase 1-5 executable gates:

- Phase 0 defines the product boundary, operator decision matrix, broker capability registry, non-Bybit allowlist, IBKR topology/session attestation, feature/secret/auth matrix, lane-scoped IPC, paper lifecycle, event log, DDL/evidence, provenance, cost, benchmark, shadow fill, GUI, storage, kill-switch, release packet, and tiny-live eligibility firewall.
- Phase 1 is limited to accepted type/config/schema/IPC implementation, default OFF, no IBKR connector, no secret slot, no external call, and no runtime mutation.
- Phase 2 is blocked until `phase2_ibkr_external_surface_gate_v1` passes, including paper/read-only attestation, live-slot absent/empty proof, redaction, allowlist, and no-write Python guard.
- Phase 3 is blocked until the evidence clock, market-data provenance, PIT universe, corporate actions, FX/cost/benchmark, storage, reconciliation, and statistical validation are machine-checkable.
- Phase 4 is badge/readiness/status first, with client lane state untrusted and route/cache/auth negative tests before any selector.
- Phase 5 is explicitly engineering shakedown + preliminary feasibility screen, with no durable-alpha or tiny-live auto-promotion claim.

Given the task's strict interpretation of "fully online" as paper/shadow evidence workflows only, this closes the FA round2 functional omissions: operator-visible workflows, disabled/error/recovery/export states, crypto regression, release packet, and kill/disable cleanup are now either named Phase 0 packets or later pass/fail gates.

## Required Operator-Visible Workflows At Launch

These workflows must exist and be demonstrably passing before PM may use the certification wording below.

1. Lane readiness workflow:
   - `crypto_perp` remains the default lane.
   - `stock_etf_cash` appears only as paper/shadow readiness/status/evidence.
   - `cfd_margin` and stock live surfaces are disabled with explicit reason codes and no write path.

2. IBKR read-only workflow:
   - Operator can see masked/fingerprinted account/session, API family/topology, market-data entitlement/tier, connector health, expiry, degraded states, and audit event references.
   - No secret/session/token appears in argv, logs, GUI payloads, artifacts, or stack traces.

3. Universe / hypothesis / risk freeze workflow:
   - Operator can see universe version, benchmark version, cost model version, strategy hypothesis hash, market calendar, corporate-action/FX/fee source as-of, risk/loss caps, and data-cost ceiling.

4. Broker-paper rehearsal workflow:
   - Paper order intent construction is Rust-owned and requires scoped authorization, Decision Lease, Guardian/risk, cost model, instrument tradability, market session, paper account attestation, and audit sink in the same final window.
   - Operator can inspect lifecycle states: submit, acknowledge, partial fill, fill, cancel, replace, reject, inactive, unknown/manual review.
   - Broker order id, execution id, commission report id, idempotency key, and lifecycle audit references are visible where applicable.

5. Shadow evidence workflow:
   - Operator can inspect signals, synthetic fills, conservative fill model, cost components, and benchmark comparison.
   - Broker-paper fills and synthetic shadow fills remain separated and labeled.

6. Paper-vs-shadow reconciliation workflow:
   - Divergence thresholds are visible.
   - Breaches produce quarantine / manual review / `execution_model_invalid` or `insufficient_evidence`, not pooled favorable PnL.

7. Evidence-clock and scorecard workflow:
   - Daily inclusion is deterministic: PASS / FAIL / QUARANTINED.
   - Scorecard rows regenerate from atomic facts and input hashes.
   - Operator can inspect gross PnL, commissions, spread, slippage, FX, tax/fee assumptions, net PnL, benchmark excess, cost-edge ratio, PSR/DSR or equivalent deflation, concentration, and independent observation count.

8. Weekly review / export workflow:
   - PM/QC/MIT weekly review and operator brief exist.
   - Evidence exports include manifest hashes, DQ manifests, scorecard regeneration output, role reports, E2/E4/QA logs, redaction fixtures, PG dry-run logs where applicable, and GUI screenshots.

9. GUI workflow:
   - Stock overview, universe, paper, shadow, risk, and evidence views exist with empty/loading/stale/error states.
   - GUI lane state is display/filter only; localStorage, query params, and hidden fields cannot authorize trading.
   - Existing crypto tabs/routes/risk/Decision Lease/scorecard behavior is regression-verified.

10. Kill switch / disable cleanup workflow:
   - Operator can disable the lane, stop collectors, block new broker calls, prove live slot absent/empty, hide GUI surfaces, preserve read-only status/audit, archive evidence, and retain DB history forward-only.
   - `STATE_UNKNOWN` and stale broker state route to manual review, not automatic retry or silent success.

## Explicit Exclusions

This certification excludes:

- IBKR live and IBKR tiny-live.
- Any non-Bybit live trading authority.
- Margin, short, options, CFD, leveraged/inverse ETF, transfer, withdrawal, account-management write paths.
- Profitability guarantee, durable-alpha proof, or production live readiness.
- Automatic promotion from paper/shadow to tiny-live/live.
- Python-owned broker writes or Python as broker order truth.
- GUI lane selector as authority.
- Legacy Paper promotion-lane revival.

## Missing Gates

Under the stated hypothetical - every Phase 0 named contract packet and every Phase 1-5 gate passes exactly as written - FA finds no additional minimum missing product workflow or gate for `stock_etf_cash` paper/shadow launch certification.

If the hypothetical is not satisfied, the minimum missing gate is whichever named packet or phase gate is first incomplete. In particular, any of the following immediately makes the launch not certifiable:

- Phase 0 packet not accepted or not closed by CC/FA/PA/E3/E5/QC/MIT/QA.
- `phase2_ibkr_external_surface_gate_v1` missing before first IBKR healthcheck.
- `ibkr_session_attestation_v1` missing before paper/order lifecycle rehearsal.
- `stock_etf_evidence_clock_v1` not machine-checkable before evidence clock start.
- `gui_lane_contract_v1` route/cache/auth and crypto-regression tests missing before GUI activation.
- `stock_etf_release_packet_v1` or kill-switch/disable cleanup runbook missing before launch.

## Exact PM Wording

PM may use:

> FA certifies that the hardened IBKR `stock_etf_cash` plan is product-workflow complete for a paper/shadow-only launch if, and only if, the accepted Phase 0 contract packet and all Phase 1-5 gates pass exactly as written. The certified launch scope is read-only IBKR health/account/market-data evidence, broker-paper order-lifecycle rehearsal through Rust authority, shadow signal/fill/cost reconstruction, GUI evidence/status/export workflows, evidence-clock operation, weekly review, release packet, and kill/disable cleanup. This does not certify IBKR live or tiny-live, margin, short, options, CFD, transfer, profitability, durable alpha, or any automatic promotion beyond paper/shadow.

PM must not use:

> IBKR is fully live-ready.
> Stock/ETF trading can go live after the schedule.
> Paper/shadow success proves profitability.
> Positive Phase 5 evidence authorizes tiny-live.

## Final PM-Facing Decision

PAPER_SHADOW_LAUNCH_CERTIFIABLE_IF_ALL_GATES_PASS
