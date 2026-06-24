# Operator Note: Public Quote Transport Diagnostics

PM closed the source-only transport diagnostics checkpoint for the AVAXUSDT Sell public quote path.

Source:

- commit `37a0315419454c8bb82e666451423e155760c37e`
- helper `helper_scripts/research/cost_gate_learning_lane/bbo_freshness_public_quote_capture.py`
- focused public quote tests `15 passed`
- adjacent public quote + co-located runner + construction preview tests `45 passed`

What changed:

- Transport failures now record sanitized diagnostic fields:
  - error class
  - reason type
  - sanitized reason
  - errno
  - stage
  - sanitized flag
- Sanitization redacts bearer/auth material, env-style secrets, cookies, DSNs/URLs, local paths, and tracebacks.
- Diagnostic URL preservation is limited to `https://api.bybit.com` public market-data paths, stripped to scheme+host+path.

What did not change:

- no Bybit call in this checkpoint
- no order/cancel/modify
- no private/auth endpoint
- no PG read/write
- no runtime/source sync
- no service/env/crontab mutation
- no Cost Gate lowering
- no probe/order/live authority
- no promotion/profit proof

Interpretation:

This does not prove AVAX profitability and does not admit an order. It only makes future public quote failures diagnosable and audit-safe. The earlier local one-shot artifact still failed closed with `transport_error:URLError` and no BBO.

Next gate:

`P0-BOUNDED-PROBE-PUBLIC-QUOTE-RUNTIME-ROUTE-E3-BB-REVIEW-DEMO-ONLY`

Any runtime-host invocation, source sync, or repeated Bybit public quote call still requires PM->E3->BB review.
