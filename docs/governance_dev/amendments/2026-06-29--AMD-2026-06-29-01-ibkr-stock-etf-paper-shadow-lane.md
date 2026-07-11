# AMD-2026-06-29-01: IBKR Stock/ETF Paper + Shadow Lane Boundary

Date: 2026-06-29
Status: **Superseded in part by AMD-2026-07-11-01 (historic paper/shadow amendment retained)**
Related ADRs: ADR-0001, ADR-0006, ADR-0033, ADR-0040, ADR-0047, ADR-0048.
Scope: `stock_etf_cash` paper/shadow research lane only.

> **Supersession notice (2026-07-11).** AMD-2026-07-11-01 supersedes this
> amendment only where it limits `stock_etf_cash` capability development to
> readonly/paper/shadow or denies tiny-live/live-capable source and production
> wiring. It does not authorize actual broker contact or money effects: default
> remains inactive; an exact Rust-validated, time-bounded
> `ibkr_activation_envelope_v1` and human-provided bound session are required.
> Credentials/session never auto-activate. Rust authority, fail-closed controls,
> Bybit isolation, and denials for margin/short/options/CFD/transfer/
> account-management writes remain binding.

## Decision

Amend the project boundary from "Bybit is the only exchange target" to the more precise rule:

> Bybit remains the only active live execution venue. Registered non-Bybit exceptions require ADR/AMD approval, closed feature flags, separate secrets, Rust-owned authority, and fail-closed gates. The first accepted non-Bybit broker-paper exception is `stock_etf_cash` with IBKR read-only/paper/shadow scope only.

This amendment does not approve any IBKR live, tiny-live, margin, short, options, CFD, transfer, or account-management write surface.

## Phase 0 Contract Packet

The accepted Phase 0 packet is:

- `docs/adr/0048-ibkr-stock-etf-paper-shadow-lane.md`
- `docs/execution_plan/specs/2026-06-29--stock_etf_cash_phase0_named_contract_packet.md`
- `docs/execution_plan/specs/2026-06-29--stock_etf_cash_phase0_named_contract_packet.manifest.json`

Phase 1 source foundation may implement only the contracts named in that packet:

- type reservation and denial tests
- default-off flag/readiness parsing
- source-only DDL implementation after contract review, with Linux PG dry-run before apply
- lane-scoped IPC/order-lifecycle fixtures

Phase 1 must not create an IBKR connector, create secret slots, call IBKR, enable GUI runtime stock views, or start an evidence clock.

## API Baseline

The first broker baseline is:

- IBKR **IB Gateway + TWS API protocol**
- runtime topology: loopback-only session on `trade-core`
- initial paper port policy: paper gateway port only; live gateway/TWS ports are denied unless a future ADR supersedes this amendment
- first contact must be gated by `phase2_ibkr_external_surface_gate_v1`
- future health/account/contract-details/market-data read probes must also
  satisfy `stock_etf_ibkr_readonly_probe_request_v1` before any contact attempt

This baseline is a contract choice only. No IBKR process is started and no IBKR API call is authorized by this amendment.

## Secret Boundary

Allowed future slots:

- `$OPENCLAW_SECRETS_DIR/external/ibkr/readonly/`
- `$OPENCLAW_SECRETS_DIR/external/ibkr/paper/`

Denied slot:

- `$OPENCLAW_SECRETS_DIR/external/ibkr/live/`

If a live IBKR credential material is found, healthcheck must fail closed and emit a typed blocker. Environment-variable fallback is not allowed.

## Runtime Boundary

Rust remains the trading, risk, strategy-config, and execution authority. Python/FastAPI may expose read-only status, fixtures, and a thin Rust IPC caller only after the accepted lane-scoped IPC contract exists. Python must not own broker order truth, retry broker writes, or expose direct `place_order`, `cancel_order`, or `replace_order` APIs.

The current `program_code/broker_connectors/ibkr_connector/` package is an inert source-only skeleton. It may model blocked readiness/previews and fixtures only; it must not import IBKR SDKs, open sockets or HTTP sessions, read secrets, expose broker write methods, import fills, write DB rows, or imply connector runtime approval.

## Evidence Boundary

IBKR paper fills and shadow fills are evidence inputs, not live proof. Promotion-like language requires:

- candidate identity
- real paper fill fees where applicable
- conservative shadow cost model
- benchmark-relative after-cost scorecard
- independent-observation count
- regime, breadth, freshness, survivorship, and execution-realism labels
- paper-vs-shadow divergence checks

Positive paper/shadow evidence may only trigger a new `tiny_live_adr_eligibility_v1` discussion. It cannot auto-promote to tiny-live or live.

That future discussion gate must carry scorecard derivation, scorecard verdict, scorecard manifest, paper-shadow reconciliation, DQ/statistical preregistration, and QC/MIT/QA lineage. Passing it remains discussion-only and cannot authorize connector runtime, tiny-live, live, account-management writes, or secret creation.

## Required Source-of-Truth Updates

This amendment requires minimal stable-boundary wording updates in:

- `CLAUDE.md`
- `.codex/MEMORY.md`
- `README.md`
- `docs/_indexes/document_index.md`
- `docs/_indexes/initiative_index.md`
- `docs/governance_dev/SPECIFICATION_REGISTER.md`

The wording must preserve the Bybit runtime path and explicitly mark IBKR as paper/shadow only.

## Completion Criteria

This AMD is complete when:

1. ADR-0048 and the Phase 0 named contract packet are present.
2. Stable boundary docs distinguish active Bybit execution from IBKR paper/shadow research.
3. TODO has an explicit next row for Phase 1 source foundation or role closeout, without implying connector/API/runtime enablement.
4. PM and Operator checkpoint reports exist.
5. Verification records no IBKR API call, secret write, runtime mutation, Bybit path regression, or migration apply.

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | Current PM session request to start the IBKR development goal under the round3 plan | 2026-06-29 | Accepted for paper/shadow governance only |
| PM | ADR/AMD/contract packet materialization | 2026-06-29 | Active |
| CC/FA/PA/E3/E5/QC/MIT/QA | Round3 launch-certification | 2026-06-29 | `CERTIFIABLE_IF_GATES_PASS`, `SCOPE=paper_shadow_only`, `FINDINGS=0` |
