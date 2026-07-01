# IBKR Connector Skeleton

This package is an ADR-0048 source-only boundary for the `stock_etf_cash` lane.
It is not a runtime IBKR connector.

Allowed in this package now:

- typed blocked readiness payloads
- non-secret loopback endpoint descriptors
- display-only account, market-data, contract-detail, lifecycle, and fill-import previews
- display-only session and paper attestation previews
- static fixtures for tests

Denied in this package now:

- IBKR SDK imports
- socket or HTTP network contact
- secret reads, env secret fallback, or serialized credential material
- broker write methods
- paper order routing, fill import side effects, DB writes, tiny-live, or live

Rust gates remain the authority for any future read-only or paper capability.
