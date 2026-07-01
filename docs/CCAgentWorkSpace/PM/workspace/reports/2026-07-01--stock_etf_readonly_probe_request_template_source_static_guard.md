# 2026-07-01 — Stock/ETF Read-Only Probe Request Template Source Static Guard

## Scope

PM added a source-only structure guard for
`settings/broker/stock_etf_ibkr_readonly_probe_request.template.toml`.

This is not read-only probe execution, not IBKR contact, not connector runtime, not SDK import, not
secret access, not DB apply, not evidence-clock runtime, not paper order routing, and not a Bybit
behavior change. The checkpoint closes a settings/template coverage gap: the Rust read-only probe
request source was guarded, but its default-blocked template was not directly read by any
acceptance or structure test.

## Guard Added

- `tests/structure/test_stock_etf_readonly_probe_request_template_source_static.py`

The guard pins:

- default denied posture: empty contract id, `source_version = 0`, `crypto_perp`/`bybit`,
  `live_reserved_denied`, client-portal-denied action, transfer/account-write operation, denied
  authority, and `effect_capable = false`;
- empty request/probe id and all Phase 2 / allowlist / secret-slot / topology / session /
  redaction / rate-limit / audit / artifact lineage fields;
- all side-effect and authority flags false, including IBKR contact, connector runtime, secret
  serialization, order route, paper submit, DB apply, evidence clock, Bybit path reuse, live/tiny
  authority, margin/short/options/CFD, account write, entitlement purchase, client portal use, and
  Python direct broker write;
- absence of runtime/network/IBKR SDK/order/Bybit client tokens and secret material keys.

## Verification

- New structure guard py_compile: PASS.
- Focused structure guard pytest: `5 passed`.
- Focused read-only probe request acceptance: `6 passed`.
- Full `cargo test -p openclaw_types`: PASS.
- Docs PM trace tests: PASS.
- Diff check: PASS.

## Boundary

No IBKR SDK import, no socket/HTTP, no read-only probe execution, no secret read or creation, no
connector runtime, no result import, no evidence or scorecard writer, no evidence-clock runtime, no
DB apply, no paper order route, no tiny-live/live authorization, and no Bybit live/demo execution
change.
