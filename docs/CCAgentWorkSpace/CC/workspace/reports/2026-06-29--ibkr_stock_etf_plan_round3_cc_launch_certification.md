STATUS: DONE
CERTIFICATION: CERTIFIABLE_IF_GATES_PASS, SCOPE=paper_shadow_only, FINDINGS=0(C:0/H:0/M:0/L:0)

# CC Round 3 Launch Certification Closure Audit - IBKR Stock/ETF Paper/Shadow Lane

日期：2026-06-29
角色：CC(default)
範圍：governance/root-principle launch certification for the hardened
`stock_etf_cash` paper/shadow plan.
邊界：report-only；未改 code/runtime/TODO；未呼叫 IBKR/Bybit；未觸碰 Linux
`trade-core`、PG、services、secrets 或 network。依本任務指定輸出，只寫本報告，
不追加 CC memory 或 Operator mirror。

## Direct Answer

Yes, conditionally.

If every Phase 0 named contract packet and every Phase 1-5 gate in
`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md`
passes exactly as written, CC can certify the lane as governance-complete for
launch within the strict scope below.

This is not an absolute "no omissions" claim. It means: under the written
hardened plan, all known CC hard-boundary blockers from rounds 1-2 have been
converted into named, reviewable, machine-checkable gates; if those gates all
pass with accepted artifacts and role closeout, CC sees no remaining minimum
launch-certification gate for the paper/shadow lane.

Final PM-facing decision:

`PAPER_SHADOW_LAUNCH_CERTIFIABLE_IF_ALL_GATES_PASS`

## Certified Scope

The certified launch scope is exactly:

- Asset lane: `stock_etf_cash`.
- Mode: read-only / broker-paper / synthetic shadow research lane only.
- Broker surface: IBKR read-only account/market-data healthcheck and IBKR
  paper account lifecycle rehearsal only after the Phase 2 external-surface
  gate, paper/session attestation, scoped authorization, Decision Lease,
  Guardian/risk, Rust authority, audit, and reconstructability gates pass.
- Evidence surface: shadow signals, conservative fill/cost reconstruction,
  paper-vs-shadow reconciliation, after-cost scorecard, daily/weekly evidence
  review, GUI evidence/readiness/status views.
- GUI surface: badge/readiness/status first; client-side lane state remains
  display/filter-only and cannot authorize trading.
- Runtime authority: Rust remains the order/risk/execution authority; Python is
  only bridge/read/import/thin IPC caller where explicitly allowed.

Plan anchors:

- The plan defines the target as an isolated `stock_etf_cash` research lane using
  IBKR paper plus shadow evidence, not a direct market/live migration
  (`arrangement.md:9-12`).
- The allowed near-term final state is read-only healthcheck, IBKR paper
  lifecycle rehearsal, shadow reconstruction, and GUI evidence, with live IBKR,
  margin, short, options, CFD, transfer, and non-Bybit live excluded
  (`arrangement.md:25-35`).
- The lane table names `stock_etf_cash` as paper/shadow only and keeps
  `crypto_perp` on existing Bybit governance (`arrangement.md:68-72`).

## Non-Negotiable Exclusions

This certification does not authorize:

- IBKR live or tiny-live.
- Any non-Bybit live execution.
- Margin, short selling, options, CFD, leveraged/inverse expansion, transfer,
  withdrawal, or account-management writes.
- Functional `OPENCLAW_IBKR_LIVE_ENABLED` or an IBKR live secret slot.
- A paper/shadow result automatically promoting to live/tiny-live.
- Profitability, durable-alpha, or production-readiness guarantees.
- Python direct broker write methods, generic broker write helpers, or route
  paths that bypass Rust authority.
- GUI lane selector/localStorage/query/hidden-field state as trading authority.
- Legacy Paper promotion semantics; broker paper and synthetic shadow evidence
  must remain separated and proof-excluded from live promotion.
- eToro/Saxo/other broker integration unless separately approved after this
  lane's scope.

## Why Certifiable If All Gates Pass

1. Current Bybit-only and Rust-authority boundaries are explicitly amended only
   for paper/shadow research.

   ADR-0001 keeps Rust `openclaw_engine` as the trading/risk/execution authority
   and restricts Python to bridge/read/analysis behavior (`ADR-0001:6-8`).
   ADR-0006 keeps Bybit as the sole active exchange baseline
   (`ADR-0006:6-12`). The hardened plan requires a new ADR/AMD that amends that
   boundary only for `stock_etf_cash` read-only/paper/shadow research, not live
   (`arrangement.md:486-535`, `arrangement.md:751-765`).

2. Round-two omissions are now represented as named Phase 0 packets.

   Phase 0 requires `asset_lane_taxonomy_v1`,
   `broker_capability_registry_v1`, `non_bybit_api_allowlist_v1`,
   `ibkr_api_session_topology_v1`, `ibkr_session_attestation_v1`,
   `feature_flag_secret_auth_matrix_v1`, `lane_scoped_ipc_v1`,
   `stock_etf_evidence_clock_v1`, `ibkr_paper_order_lifecycle_v1`,
   `broker_lifecycle_event_log_v1`, `stock_etf_db_evidence_ddl_v1`,
   `stock_market_data_provenance_v1`,
   `broker_account_portfolio_cash_ledger_v1`, `cost_model_version_v1`,
   `benchmark_versions_v1`, `stock_shadow_fill_model_v1`,
   `gui_lane_contract_v1`, `stock_etf_storage_capacity_v1`,
   `stock_etf_kill_switch_and_disable_cleanup_runbook_v1`,
   `stock_etf_release_packet_v1`, and `tiny_live_adr_eligibility_v1`
   (`arrangement.md:492-527`).

3. External broker contact is fail-closed behind an explicit gate.

   Phase 2 cannot start unless `phase2_ibkr_external_surface_gate_v1` passes.
   Even the first read-only healthcheck is treated as non-Bybit external contact
   and requires accepted ADR/AMD, API baseline, topology, secret contract,
   allowlist, redaction, rate limits, audit event, and live-slot absent/empty
   proof (`arrangement.md:568-595`, `arrangement.md:803-820`).

4. Paper order rehearsal remains controlled, auditable, and scoped.

   Phase 1 prohibits IBKR connector creation, secret slot creation, external
   IBKR calls, and runtime mutation; it only implements accepted contracts,
   default-off flags, DDL/design gates, and fixture IPC/order-lifecycle work
   (`arrangement.md:537-566`). Phase 2 then requires paper/read-only session
   attestation, broker IDs, idempotent import/recovery tests, Python no-write
   structural tests, and live compile/runtime fail-closed behavior
   (`arrangement.md:585-595`).

5. Evidence is bounded as screening, not proof or live readiness.

   Phase 3 cannot start until data vendor/tier, PIT universe, corporate actions,
   FX/cost model, benchmark, storage/capacity, retention, reconciliation, and
   statistical validation are machine-checkable (`arrangement.md:597-621`).
   Phase 5 explicitly says the 6-8 week window is engineering shakedown plus
   preliminary feasibility only, not durable-alpha proof or production readiness,
   and positive point estimates cannot trigger tiny-live (`arrangement.md:647-670`).
   ADR-0047 requires regime/breadth/freshness/survivorship/execution-realism and
   statistical gates, and says this evidence governance grants no trading
   authority or relaxation of live gates (`ADR-0047:21-59`).

6. GUI and operator surfaces are controlled.

   Phase 4 requires badge/readiness first, route/cache/auth partition tests,
   proof that client-side lane state is untrusted, crypto regression, and stock
   live fail-closed display (`arrangement.md:623-645`). The first acceptance
   criteria require GUI state to remain non-authoritative and paper order paths
   to go through Rust authority (`arrangement.md:695-711`).

7. Release and shutdown are part of the launch gate.

   The hardened Phase 0 additions require `stock_etf_release_packet_v1` with role
   reports, commands, hashes, screenshots, DQ manifests, redaction fixtures, PG
   logs, and scorecard regeneration outputs; they also require
   `stock_etf_kill_switch_and_disable_cleanup_runbook_v1` covering lane disable,
   collector stop, secret absence proof, GUI hide, evidence archive, and DB
   forward-only retention (`arrangement.md:803-820`).

## Missing Gates

Under the hypothetical stated by the operator - every Phase 0 named contract
packet and every Phase 1-5 gate passes exactly as written - CC identifies no
additional minimum launch-certification gate for the `stock_etf_cash`
paper/shadow lane.

Current-state caveat: today this is not launch-certified, because those packets
and gates have not passed. The current first missing gate remains the accepted
Phase 0 ADR/AMD plus the full named contract packet closeout. This report is a
conditional launch-certification closure audit, not a present runtime approval.

## Exact PM Wording

PM may use the following wording with the operator:

> CC can certify the `stock_etf_cash` lane as governance-complete for paper/shadow
> launch if, and only if, every Phase 0 named contract packet and every Phase 1-5
> gate in the hardened plan passes exactly as written and the release packet
> artifacts are accepted. The certified scope is read-only IBKR health/account
> evidence, IBKR paper order-lifecycle rehearsal only when paper-scoped
> authorization/session attestation and Rust/Decision Lease/Guardian gates pass,
> synthetic shadow collection, after-cost scorecards, and GUI evidence views.
> This does not authorize IBKR live or tiny-live, margin, short, options, CFD,
> transfers, non-Bybit live, or any profitability/alpha guarantee. Positive
> paper/shadow evidence can only open a separate tiny-live ADR discussion.

## Final Decision

`PAPER_SHADOW_LAUNCH_CERTIFIABLE_IF_ALL_GATES_PASS`
