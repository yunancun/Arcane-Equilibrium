# PM Checkpoint Report — IBKR Stock/ETF Session Attestation Data-Tier Lineage Guard

Date: 2026-07-01
Status: DONE_WITH_CONCERNS

## Summary

This checkpoint hardens `ibkr_session_attestation_v1` so Phase 2 session
evidence records data tier, entitlements lineage, market-data entitlement
purchase denial, and gateway startup time before any broker contact can be
accepted. It is source-only and does not add an IBKR SDK import, socket/HTTP,
secret lookup, connector runtime, read probe, market-data ingestion, paper
order, endpoint, or IPC method.

## Changes

- Added `IbkrSessionDataTier`.
- Added `data_tier`, `entitlements_fingerprint`,
  `market_data_entitlement_purchase_denied`, and `gateway_started_at_ms` to
  `IbkrSessionAttestationV1`.
- Hardened session fingerprint and raw-artifact validation to require 64-hex
  hash shape.
- Added blockers for missing/invalid data-tier lineage, market-data entitlement
  purchase not denied, and gateway startup after attestation.
- Updated inert Python connector preview and FastAPI account/authorization
  normalizers to expose only fail-closed display fields.
- Updated Phase0 named-contract packet for the session attestation fields and
  blockers.

## Boundary

No IBKR contact, SDK import, socket/HTTP, secret access, connector runtime,
read probe execution, collector start, market-data ingestion, DQ writer, paper
order/cancel/replace, fill import, DB/evidence/scorecard writer, evidence
clock, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## Verification

- Python changed files `py_compile`: PASS.
- Connector/account/authorization focused pytest: `18 passed`.
- Scoped Rust `rustfmt --edition 2021 --check`: PASS.
- IBKR Phase2 gate acceptance: `11 passed`.
- IBKR feature-flag auth acceptance: `8 passed`.
- Full Stock/ETF FastAPI/static pytest: `120 passed`.
- Full `cargo test -p openclaw_types`: `291 passed`.
- Focused docs trace: `2 passed`.
- `git diff --check`: PASS.

## PM Sign-Off

APPROVED for source-only session-attestation contract hardening. This is not
Phase 2 runtime approval, IBKR contact approval, read-only probe approval, paper
channel approval, market-data ingestion approval, or launch approval.
