# PM Request - ALR P2-5 Feedback Apply

Date: 2026-07-09
Authority chain: PM -> E3 -> BB -> PM, `ROLE_FALLBACK_SINGLE_SESSION`
Target behavioral source head: `2787042d09960186cb6edd1471c4c712ff78af0d`

Fresh preflight: Linux checkout/origin are clean at the target head; V153 is
absent; one P2-4 run has no feedback event; the active ALR service remains
pinned to the prior behavioral source. The existing engine retains write-capable
Demo flags and is excluded.

Requested actions are exactly: apply V153; reapply the reviewed ALR role
contract; render the existing ALR unit with the target source head; daemon-reload
and restart only that unit; read back one feedback event, one rotation edge, one
next target, unchanged scanner count, zero duplicate source keys, exact false/
zero authority records, and denied UPDATE/DELETE/scanner INSERT privilege.

No engine restart, scanner mutation, Bybit/MCP, order/probe/cancel/modify,
Decision Lease, Cost Gate, RiskConfig, Guardian, order dispatch, live/mainnet,
serving, promotion, `_latest`, proof claim, or deletion is authorized.
