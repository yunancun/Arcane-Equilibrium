STATUS: DONE
CERTIFICATION: CERTIFIABLE_IF_GATES_PASS, SCOPE=paper_shadow_only, FINDINGS=0(C:0/H:0/M:0/L:0)

# PA Round 3 Launch-Certification Closure Audit — IBKR Stock/ETF Paper + Shadow

日期：2026-06-29
角色：PA(default)
範圍：architecture / sequence / no-technical-debt launch certification closure audit。
邊界：report-only；未改 code/runtime/TODO，未觸碰 IBKR/Bybit/Linux/PG/services/secrets/network。

## Decision

Yes. If, and only if, every Phase 0 named contract in the hardened plan is accepted
as a machine-checkable contract, and every Phase 1-5 gate subsequently passes,
PA can certify the architecture is complete enough for a `stock_etf_cash`
paper/shadow launch without knowingly accumulating architecture technical debt.

This is not a current launch approval. It is a conditional closure statement:
the current repo authority still says this initiative is not in the active
implementation queue, and Phase 1+ remains blocked until Phase 0 contracts are
accepted.

## Exact Architecture-Complete Scope

Certified scope after all gates pass:

- Asset lane: `stock_etf_cash` only.
- Broker/environment: IBKR read-only plus IBKR broker-paper rehearsal, with
  broker-reported paper/read-only attestation and no live slot.
- Execution class: paper/shadow evidence lane only.
- Allowed functions: read-only health/status, paper account snapshot, paper
  order lifecycle rehearsal through Rust-owned lane-scoped IPC, paper fill /
  commission import, synthetic shadow signals/fills, conservative fill/cost
  reconstruction, daily after-cost scorecard, GUI badge/readiness/status and
  stock evidence views.
- Authority model: Rust remains the order/risk/IPC authority; Python is only
  API client, health/status, import helper, GUI/control plane, or thin Rust IPC
  caller. Python direct broker writes remain forbidden.
- Evidence model: atomic facts are the source of truth; scorecards are derived
  artifacts; audit/event references are immutable or hash-linked; market data,
  instrument identity, cash/FX, cost, benchmark, corporate action, paper, and
  shadow lineage are reconstructable.
- GUI model: badge/readiness first; client lane state is display/filter state
  only and never authority.
- Evidence window: engineering shakedown plus preliminary feasibility screen
  only; positive paper/shadow results can at most open a separate tiny-live ADR
  discussion.

## Explicit Exclusions

This certification excludes IBKR live, tiny-live, margin, short, options, CFD,
transfers/withdrawals, any non-Bybit live execution, any change to existing
Bybit live gates, legacy Paper promotion reactivation, durable-alpha proof,
production/live readiness, and profitability guarantees.

## Technical-Debt Closure Criteria

The conditional certification depends on these closure rules, all of which must
be satisfied by concrete artifacts rather than prose:

1. Phase 0 contracts are accepted before E1 implementation: ADR/AMD, asset lane
   taxonomy, broker capability registry, non-Bybit API allowlist, IBKR session
   topology/attestation, feature flag + secret/auth matrix, lane-scoped IPC,
   paper order lifecycle, broker lifecycle event log, DB evidence DDL, market
   data provenance, account/portfolio/cash/FX ledger, cost model, benchmark,
   shadow fill model, GUI contract, storage/capacity, kill-switch/disable
   cleanup, release packet, evidence clock, and tiny-live eligibility.
2. Phase 1 implements only accepted contracts: default-off type/config/schema/IPC
   foundation, denial tests, no catch-all broker/lane enum, no legacy
   `submit_paper_order` reuse for stock/ETF, and crypto/Bybit regression green.
3. Phase 2 does not contact IBKR until `phase2_ibkr_external_surface_gate_v1`
   passes, including API baseline, topology, secret slot, live-slot absence,
   allowlist, redaction, rate limits, audit, and paper/read-only attestation.
4. Phase 3 starts only after DDL/provenance/storage/evidence-clock contracts are
   machine-checkable, with deterministic PASS/FAIL/QUARANTINED DQ manifests and
   scorecard regeneration from atomic facts.
5. Phase 4 proves GUI lane state is untrusted, routes/cache/auth are partitioned,
   disabled live/CFD states are no-write, and existing crypto tabs/routes remain
   unchanged.
6. Phase 5 uses pre-registered sample, benchmark, cost, paper-vs-shadow,
   regime/breadth, PSR/DSR or equivalent deflation, and verdict-label gates.
   Underpowered positives remain `research_promising` or `insufficient_evidence`.
7. The release packet contains role reports, E2/E4/QA logs, command outputs,
   hashes, PG dry-run evidence where applicable, redaction fixtures, GUI
   screenshots, DQ manifests, scorecard regeneration outputs, and disable/cleanup
   proof.

## Missing Gates

Minimum missing architecture contract under the stated hypothetical: none.

Important distinction: in the current state, the accepted Phase 0 packet and
Phase 1-5 evidence do not yet exist, so the lane is not certifiable today. The
conditional answer becomes valid only after those named contracts and gates are
completed and passed.

## PM Wording

PM may use this wording:

> PA certifies the `stock_etf_cash` architecture as paper/shadow-launch
> certifiable only after the accepted Phase 0 contract packet and every Phase
> 1-5 gate pass. The certified scope is IBKR read-only + IBKR broker-paper
> rehearsal + synthetic shadow evidence collection for cash stock/ETF only,
> default-off, Rust-authority, reconstructable, and append-only audited. This
> excludes IBKR live/tiny-live, margin, short, options, CFD, transfers, and any
> profitability or durable-alpha guarantee.

## Final PM-Facing Decision

PAPER_SHADOW_LAUNCH_CERTIFIABLE_IF_ALL_GATES_PASS
