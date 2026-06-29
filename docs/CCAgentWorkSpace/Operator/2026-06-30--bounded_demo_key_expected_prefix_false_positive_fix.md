# Bounded Demo Key Expected Prefix False Positive Fix

Date: 2026-06-30
Owner: PM
Status: DONE_WITH_CONCERNS

Operator correction accepted: masked `FWkGZX...g53T` is the correct Bybit Demo Read-Write key, and the Demo API page shows OpenAPI IP whitelist `79.117.10.224`.

The previous `BHw4...` mismatch was a stale expected-prefix hint, not a live key issue and not evidence that the Demo slot key was wrong. Source is now fixed so expected Demo key sha/prefix mismatch is advisory by default; it blocks only with explicit `--require-expected-demo-api-key-match`.

Remaining blockers are connector/runtime/proof, not the key itself: `BYBIT_MODE=read_only`, `BYBIT_CONNECTOR_WRITE_ENABLED=false`, no candidate-matched fills, and serving/proof gates still red.

Verified focused readiness/cutover/settings tests: `11 passed` plus `6 passed`; no secret/env/service/cron/runtime mutation, Bybit call, order action, Cost Gate change, live authority, or promotion proof occurred.
