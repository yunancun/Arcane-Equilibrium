# ALR P2-3 Fresh Event-Consumer Gate

Date: 2026-07-09
Work item: `P2-3-ALR-EVENT-CONSUMER-FRESH-GATE`
Status: `SOURCE_AND_ISOLATED_TESTS_AUTHORIZED`
Execution mode: `ROLE_FALLBACK_SINGLE_SESSION`

## Result

P2-3 source work is approved: a best-effort post-persist scanner notification,
a bounded local listener, and a user-unit definition. The scope preserves
scanner behavior and provides no broker or trading authority.

Existing PG has no ALR role and scanner persistence has no event notification.
The eventual service must use a dedicated least-privilege identity and a
notification payload with source identity/hash only. Role/secret provisioning,
engine rebuild/restart, and service start remain blocked pending the implemented
source evidence and prestart recheck.
