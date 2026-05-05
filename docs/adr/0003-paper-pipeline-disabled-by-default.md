---
status: accepted
date: 2026-04-16
---

# Paper pipeline is opt-in via OPENCLAW_ENABLE_PAPER=1

Since 2026-04-16, the Paper pipeline is not spawned at engine start unless `OPENCLAW_ENABLE_PAPER=1` is set; otherwise the engine writes a DISABLED marker, runs a minimal drain task to keep upstream channels unblocked, and notifies the fan-out barrier so demo/live do not wait. Rationale: a 2-day observation showed paper hit -137% drawdown ($783→-$292) and produced 27× more fills than demo for the same strategy, polluting the edge / ML / audit datasets that already exclude paper data.

## Consequences

The 3E-ARCH structure is preserved (Paper kind/state/predictors all retained); only runtime spawn is gated. Edge studies must continue to source from Demo, never Paper.
