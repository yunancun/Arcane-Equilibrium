# PM Report: AVAX CA-Safe Public Quote Route Source Patch

Date: 2026-06-25
Status: DONE_WITH_CONCERNS
Active blocker: `P0-BOUNDED-PROBE-AVAX-CA-SAFE-PUBLIC-QUOTE-ROUTE-DEMO-ONLY`

## Decision

Advanced the AVAX CA-safe public quote route as a source-only checkpoint. The public quote helper now builds its no-redirect urllib opener with a verified SSL context, preferring the `certifi` CA bundle when available and falling back to the system CA store.

This resolves the source-side Mac TLS trust path that blocked the previous quote attempt, but it does not rerun the Bybit quote, does not produce a fresh BBO artifact, and does not grant probe/order/live authority.

## Source Change

- `helper_scripts/research/cost_gate_learning_lane/bbo_freshness_public_quote_capture.py`
  - adds `_certifi_cafile()`
  - adds `_verified_ssl_context()`
  - routes `urlopen_no_redirect()` through `_no_redirect_opener()`
  - preserves `_RedirectRefusedHandler`
  - uses `ssl.create_default_context(...)`; no unverified TLS context is introduced
- `helper_scripts/research/tests/test_cost_gate_bbo_freshness_public_quote_capture.py`
  - pins certifi-backed verified context behavior
  - pins fallback to default CA behavior

## Evidence

- Focused public quote tests: `17 passed`
- Adjacent no-order adapter/construction-preview tests: `57 passed`
- E2 adversarial review: PASS, no findings
- E4 focused regression: PASS, no findings
  - broader no-order regression: `86 passed` twice
  - py_compile passed
  - diff-check passed

## Boundary

No Bybit call, no private/auth endpoint, no auth/cookie headers, no order/cancel/modify, no PG query/write, no `_latest` overwrite, no service/env/crontab/runtime mutation, no Cost Gate lowering or cap/freshness-gate widening, no Rust writer/adapter enablement, no probe/order/live authority, and no promotion proof.

## Anti-Repeat

The v519 quote approval was one-shot and already consumed. This checkpoint supplies a source-level evidence delta, so it is not a repeated quote attempt. A future quote invocation still requires a fresh `PM -> E3 -> BB` exchange-facing review.

## Next Safe Action

Start `P0-BOUNDED-PROBE-AVAX-PUBLIC-QUOTE-E3-BB-REFRESH-DEMO-ONLY`: review exactly one no-order public market-data helper invocation on the verified-TLS helper path. If and only if that produces `PUBLIC_QUOTE_CAPTURE_READY_NO_ORDER`, proceed to no-order adapter + construction preview. If it fails closed, classify the new blocker without retrying under the same approval.
