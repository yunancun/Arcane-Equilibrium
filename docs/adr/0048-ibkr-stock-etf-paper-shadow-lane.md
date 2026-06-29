---
status: accepted
date: 2026-06-29
scope: stock_etf_cash paper/shadow research only
---

# ADR 0048: IBKR Stock/ETF Paper + Shadow Lane

Date: 2026-06-29
Status: **Accepted - paper/shadow governance scope only**
Operator Sign-off: 2026-06-29 current PM session instruction, materialized by this ADR, AMD-2026-06-29-01, and the Phase 0 named contract packet.
Related: ADR-0001, ADR-0006, ADR-0033, ADR-0040, ADR-0047, AMD-2026-06-29-01.

## Context

ADR-0006 made Bybit the sole exchange target so the project could keep a single controlled execution surface. Later ADRs created narrow non-Bybit exceptions only for governed read-only or future-gated cases, most notably Binance market data in ADR-0033 and the multi-venue gate in ADR-0040.

The 2026-06-29 IBKR Stock/ETF plan completed three rounds of PM-led review. CC, FA, PA, E3, E5, QC, MIT, and QA all returned `CERTIFIABLE_IF_GATES_PASS` only inside `paper_shadow_only` scope. That review did not approve IBKR live, tiny-live, margin, short, options, CFD, transfers, account-management writes, or automatic promotion.

The operator now asks PM to start the IBKR development goal. The safe first step is to materialize Phase 0 governance and named contracts so any later source implementation has explicit boundaries instead of letting E1 invent broker, IPC, database, GUI, or evidence semantics during coding.

## Decision

Create a new isolated asset lane:

- `asset_lane = stock_etf_cash`
- `broker = ibkr`
- `environment in {readonly, paper, shadow}`
- `live`, `tiny_live`, `margin`, `short`, `options`, `cfd`, `transfer`, and account-management writes are denied.

This ADR amends ADR-0006 only for the following research surfaces:

1. IBKR read-only health/account/market-data checks after `phase2_ibkr_external_surface_gate_v1` passes.
2. IBKR broker-paper order lifecycle rehearsal after paper session attestation, Rust authority, scoped authorization, and fail-closed lifecycle contracts pass.
3. Shadow signal, conservative shadow fill, cost reconstruction, benchmark, and scorecard evidence.
4. GUI display/export of stock/ETF paper/shadow evidence with client lane state treated as untrusted.

Bybit remains the only active live execution venue. The existing `crypto_perp` lane, Bybit Demo/LiveDemo/Live gates, Guardian, Decision Lease, Rust authority, and Cost Gate semantics remain unchanged by this ADR.

## Required Taxonomy

`AssetLane` must be closed:

- `crypto_perp`
- `stock_etf_cash`
- `cfd_margin_reserved`

`Broker` must be closed:

- `bybit`
- `ibkr`

`BrokerEnvironment` must be closed:

- `readonly`
- `paper`
- `shadow`
- `live_reserved_denied`

No `Other(String)`, catch-all broker, catch-all lane, or string-literal venue bypass is allowed. A future new broker or live venue requires a new ADR.

## Authority Matrix

| Operation class | `crypto_perp` | `stock_etf_cash` |
|---|---|---|
| Bybit Demo / LiveDemo / Live gates | Existing governed path | Not applicable |
| IBKR read-only account / market data | Not applicable | Allowed only after external-surface gate PASS |
| IBKR paper order lifecycle rehearsal | Not applicable | Allowed only after paper attestation + Rust authority + scoped authorization |
| IBKR live / tiny-live | Denied | Denied by typed policy |
| Margin / short / options / CFD | Existing Bybit policies where applicable | Denied |
| Transfer / account-management write | Existing governed policy where applicable | Denied |
| Shadow fill / scorecard evidence | Existing learning contracts | Allowed as research evidence only |
| Promotion to live | Existing live gates | Denied; positive paper/shadow may only open a new ADR discussion |

## Mandatory Phase Gates

Phase 1 source foundation may start only after the Phase 0 named contract packet exists in repo and is internally consistent with this ADR and AMD-2026-06-29-01.

Phase 2 IBKR external contact may start only after `phase2_ibkr_external_surface_gate_v1` emits an immutable PASS artifact. The first read-only healthcheck is external contact and is not exempt.

Phase 3 evidence clock may start only after `stock_etf_evidence_clock_v1` proves collector stability, frozen universe/benchmark/cost model/strategy hypothesis hashes, corporate-action and FX source contracts, and paper-vs-shadow divergence thresholds.

Phase 4 GUI runtime may expose stock/ETF views only after route/cache/auth negative tests prove client lane state cannot authorize any effect-capable action.

Phase 5 may sign off paper/shadow online only after the release packet, immutable artifact manifest, kill/disable cleanup runbook, evidence archive, and engineering shakedown all pass.

## Denied Paths

The following are explicitly not approved:

- Functional `OPENCLAW_IBKR_LIVE_ENABLED`.
- Creating `$OPENCLAW_SECRETS_DIR/external/ibkr/live/`.
- Reusing Bybit paper `submit_paper_order` IPC for stock/ETF broker-paper orders.
- Python broker write authority or Python retrying broker writes.
- Treating GUI lane selection, localStorage, query params, or hidden form fields as authorization.
- Treating IBKR paper fills as live fills.
- Treating 6-8 weeks of paper/shadow evidence as durable alpha proof by itself.
- Auto-promoting from paper/shadow to tiny-live or live.

## Consequences

Positive:

- The project can explore a lower-cost, lower-correlation stock/ETF evidence lane without weakening Bybit execution governance.
- Future source implementation has closed enums, typed denials, and named contracts instead of ad hoc broker abstractions.
- IBKR paper/shadow evidence becomes reconstructable and comparable to existing scorecard governance.

Risk and mitigation:

- IBKR broker-paper is still effect-capable. It is gated behind paper attestation, Rust authority, scoped authorization, and lifecycle reconciliation.
- GUI lane split could create accidental authority confusion. The first GUI slice is badge/readiness/display-only, and client state is untrusted.
- Evidence may be statistically weak after 6-8 weeks. QC/MIT gates require independent-observation and benchmark-relative labels before any feasibility verdict.

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | Current PM session instruction to start IBKR development under the three-round plan | 2026-06-29 | Accepted for paper/shadow governance only |
| PM | Phase 0 ADR/AMD/named contract materialization | 2026-06-29 | Accepted with gates |
| CC/FA/PA/E3/E5/QC/MIT/QA | Round 3 launch certification reports | 2026-06-29 | `CERTIFIABLE_IF_GATES_PASS`, scope `paper_shadow_only` |

## References

- `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round3_pm_launch_certification.md`
- `docs/CCAgentWorkSpace/Operator/2026-06-29--ibkr_stock_etf_plan_round3_pm_launch_certification.md`
- `docs/execution_plan/specs/2026-06-29--stock_etf_cash_phase0_named_contract_packet.md`
- `docs/governance_dev/amendments/2026-06-29--AMD-2026-06-29-01-ibkr-stock-etf-paper-shadow-lane.md`
