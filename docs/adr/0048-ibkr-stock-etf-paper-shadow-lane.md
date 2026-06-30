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
| Promotion to live | Existing live gates | Denied; positive paper/shadow may only open a new ADR discussion after `tiny_live_adr_eligibility_v1` passes |

## Mandatory Phase Gates

Phase 1 source foundation may start only after the Phase 0 named contract packet exists in repo and is internally consistent with this ADR and AMD-2026-06-29-01.

`stock_etf_phase0_contract_packet_manifest_v1` must be machine-checkable as the
Phase 0 manifest authority. It must pin schema/status/scope, ADR/AMD/packet
paths, IBKR loopback paper API baseline, global denials, exact named contract
list, and phase unlock table, while rejecting prior IBKR contact, live-port
allowance, missing/duplicate/unknown contracts, missing denials, Phase 2 contact
unlock, evidence-clock start, GUI runtime enablement, Phase 5 online status,
tiny-live, and live.

`broker_capability_registry_v1` must be machine-checkable before effect-capable paper-route implementation. It must prove the full operation matrix, Bybit live execution unchanged, Python broker write authority denied, paper writes Rust-owned, read/paper/shadow/scorecard gates present, and live/margin/short/options/CFD/transfer/account-write operations typed-denied.

`lane_scoped_ipc_v1` must be machine-checkable before any Stock/ETF paper IPC
route, Python bridge, or agent handoff can reach Rust authority. It must prove
the exact `stock_etf.*` method matrix, required gates, request fields, typed
denial reasons, Rust ownership for preview/submit/cancel/replace, and explicit
separation from existing Bybit paper IPC paths. It rejects unknown/Bybit IPC
methods, direct Python broker write authority, existing Bybit paper-path reuse,
IBKR contact, connector runtime, serialized secrets, live environment, and
Bybit-live regression. Passing this source contract starts no IPC server and
does not authorize paper orders.

The Python no-write static guard must pass before any IBKR Python surface is
accepted. It must AST-scan Stock/ETF/IBKR route and future connector files while
excluding existing Bybit modules, reject direct Python broker write methods,
forbidden paper-order IPC strings, direct `ibapi` / `ib_insync` imports, and
non-GET Stock/ETF/IBKR routes until a later Rust-authority contract explicitly
revises that boundary.

`stock_etf_ibkr_readonly_probe_request_v1` must be machine-checkable before any
future IBKR health, account, contract-details, or market-data read probe can be
considered. It must bind the probe kind to an allowed read action and broker
operation, require Phase 2 gate/allowlist/secret-slot/topology/session/
redaction/rate-limit/audit lineage hashes, and reject prior contact, connector
runtime, secret serialization, order routing, paper submission, DB apply,
evidence-clock start, Bybit path reuse, entitlement purchase, Client Portal Web
API use, Python direct broker writes, and tiny-live/live or
margin/short/options/CFD authority. Passing this source contract performs no
probe and does not authorize IBKR contact by itself.

`instrument_identity_contract_v1` must be machine-checkable before market data,
contract details, shadow fill reconstruction, or paper order intent consumes a
symbol. It must prove point-in-time symbol/listing/primary-exchange/currency/
tradability/PRIIPs/fractional-policy/calendar/corporate-action identity hashes
while rejecting unknown venues, crypto/CFD instruments, non-USD v1 currency,
untradable instruments, prior IBKR contact, serialized secrets, and any Bybit
live regression.

`stock_etf_pit_universe_contract_v1` must be machine-checkable before evidence
clock days, stock shadow signals, or scorecard derivation rely on a universe
hash. It must prove point-in-time universe id/version/hash, effective window,
bounded constituents, per-constituent identity/tradability/PRIIPs/currency/
venue checks, inclusion/exclusion/liquidity/tradability/PRIIPs policy hashes,
delisted/inactive survivorship controls, corporate-action/calendar/source
hashes, Bybit-live unchanged proof, and IBKR-live denial, while rejecting prior
IBKR contact and serialized secrets.

`stock_etf_strategy_hypothesis_contract_v1` must be machine-checkable before
evidence clock days, stock shadow signals, or scorecard derivation rely on a
strategy hypothesis hash. It must prove pre-registered hypothesis id/version,
allowed low/medium-turnover strategy family, daily/weekly timeframe, PIT
universe/benchmark/cost-model/rule/feature/statistical-design/preregistration
hashes, bias and multiple-testing controls, benchmark-relative after-cost
metrics, no options/CFD/margin/short policy, paper/shadow-only posture,
Bybit-live unchanged proof, and IBKR-live denial, while rejecting profitability
claims, live/tiny-live authority claims, prior contact, and serialized secrets.

`stock_etf_kill_switch_and_disable_cleanup_runbook_v1` must be machine-checkable
before any release or evidence-clock completion claim. It must prove exact
disable flags, collector stop, GUI disabled/hidden posture, live-secret absence,
forward-only archive/DB retention, append-only audit preservation, and Bybit
live execution unchanged, while rejecting IBKR contact, connector runtime,
paper order routing, secret creation/serialization, destructive DB cleanup,
paper-shadow launch authority, tiny-live, and live.

`stock_etf_db_evidence_ddl_v1` must remain source-only until separate migration authorization. Its source contract must prove required schemas/tables/natural keys, stock/ETF and IBKR constraints, paper/shadow separation, audit-event storage, Guard A/B/C migration controls, future Linux PG dry-run and double-apply requirements, and no DB apply/sqlx registration/PG write claim.

Phase 2 IBKR external contact may start only after `phase2_ibkr_external_surface_gate_v1` emits an immutable PASS artifact. The first read-only healthcheck is external contact and is not exempt.

`stock_etf_risk_policy_v1` must be machine-checkable before any paper-order
rehearsal, shadow-fill reconstruction, or scorecard can rely on a
`risk_config_hash`. It must prove the dormant paper/shadow source posture,
finite ordered notional caps, bounded open-order/open-position limits,
cash-only no-margin/no-short/no-options/no-CFD/no-transfer/no-live rules,
instrument universe requirements, cost model prerequisites, Rust authority,
session attestation, Decision Lease, Guardian, idempotency, broker
reconciliation, Bybit-live unchanged proof, and no IBKR contact, connector
runtime, or secret serialization.

`stock_etf_reference_data_sources_v1` must be machine-checkable before Phase 3
evidence-clock days, shadow-fill reconstruction, or scorecards can consume
corporate-action, FX, fee, tax/FTT, or withholding-treatment hashes. It must
prove frozen source names, as-of timestamps, source artifact hashes, USD v1
currency treatment, Bybit-live unchanged proof, and no IBKR contact, connector
runtime, serialized secrets, tiny-live, or live authority.

Phase 3 evidence clock may start only after `stock_etf_evidence_clock_v1`
proves collector stability, accepted PIT universe, strategy hypothesis,
market-data provenance, and reference-data source contracts plus frozen
universe/benchmark/cost/strategy hypothesis/reference-data hashes and
paper-vs-shadow divergence thresholds. `stock_market_data_provenance_v1` must
be machine-checkable before market-data facts, shadow-fill reconstruction, or
scorecards can consume quote/bar source hashes; it must prove lane/broker/
environment, vendor/entitlement, timestamps, adjustment marker, instrument and
calendar hashes, source artifact hash, Bybit-live unchanged proof, and no IBKR
contact, connector runtime, serialized secrets, tiny-live, or live authority.
`stock_etf_evidence_clock_v1` day evidence must also machine-check exact
contract id/source version, lane/broker/environment, source artifact hash,
market-data provenance and scorecard input hashes, Bybit-live unchanged proof,
and checker-side denials for IBKR contact, connector runtime, runtime clock
start, scorecard writer, DB apply, serialized secrets, and tiny-live/live
authority. `WINDOW_COMPLETE` cannot be asserted by the source checker alone.
Scorecard inputs must remain source-validated, derived-only, paper/shadow
separated, and unable to claim live fills. The scorecard input source contracts
must machine-check exact contract ids and source versions for cash ledger, cost
model, benchmark, shadow fill, and storage capacity inputs. The bundle must
carry accepted market-data provenance, reference-data source, and risk-policy
contract hashes while rejecting IBKR contact, connector runtime, broker fill
import, scorecard writer, DB apply, evidence-clock start, serialized secrets,
and tiny-live/live authority.

Cross-phase `stock_etf_cash` evidence must be referable through `audit.asset_lane_events_v1` immutable event references. These references require lane/broker/environment/operation fields, hash-chain continuity, producer/source metadata, artifact hashes, and redaction boundaries; they do not write audit rows or authorize runtime actions by themselves.

Phase 4 GUI runtime may expose stock/ETF views only after route/cache/auth negative tests prove client lane state cannot authorize any effect-capable action. `gui_lane_contract_v1` artifacts must prove GET-only display, client state untrusted, no effect-capable surfaces, route/cache/auth partition, stale-cache cross-lane denial, and crypto Decision Lease/risk regression before fuller views or selector discussion.

Phase 5 may sign off paper/shadow online only after the release packet, immutable artifact manifest, kill/disable cleanup runbook, evidence archive, and engineering shakedown all pass.

`tiny_live_adr_eligibility_v1` is a discussion gate only. It may be evaluated after the paper/shadow window and Phase 5 release evidence are complete, but passing it cannot authorize tiny-live, live, margin, short, options, CFD, transfer, account-management writes, secret creation, or connector runtime.

The tiny-live discussion gate must carry scorecard derivation, scorecard verdict, scorecard manifest, paper-shadow reconciliation, DQ/statistical preregistration, and QC/MIT/QA lineage. Missing or pre-gate truthy lineage claims remain fail-closed; this lineage only determines whether a new ADR discussion may start.

The Python IBKR package at `program_code/broker_connectors/ibkr_connector/` is currently an inert source-only skeleton outside the Bybit connector tree. It may expose blocked readiness/previews and secret-free fixtures only; it must not import IBKR SDKs, open sockets or HTTP sessions, read secrets, expose broker write methods, import fills, or write DB rows.

## Denied Paths

The following are explicitly not approved:

- Functional `OPENCLAW_IBKR_LIVE_ENABLED`.
- Creating `$OPENCLAW_SECRETS_DIR/external/ibkr/live/`.
- Reusing Bybit paper `submit_paper_order` IPC for stock/ETF broker-paper orders.
- Python broker write authority or Python retrying broker writes.
- Treating GUI lane selection, localStorage, query params, or hidden form fields as authorization.
- Treating IBKR paper fills as live fills.
- Treating 6-8 weeks of paper/shadow evidence as durable alpha proof by itself.
- Auto-promoting from paper/shadow to tiny-live or live, including via `tiny_live_adr_eligibility_v1`.

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
