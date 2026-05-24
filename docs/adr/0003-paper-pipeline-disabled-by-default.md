---
status: accepted
date: 2026-04-16
---

# Paper pipeline is archived; OPENCLAW_ENABLE_PAPER=1 is ignored

From 2026-04-16 until the 2026-05-23 archive rebase, the Paper pipeline was
not spawned at engine start unless `OPENCLAW_ENABLE_PAPER=1` was set; otherwise
the engine wrote a DISABLED marker, ran a minimal drain task to keep upstream
channels unblocked, and notified the fan-out barrier so demo/live did not wait.
Rationale: a 2-day observation showed paper hit -137% drawdown ($783→-$292) and
produced 27× more fills than demo for the same strategy, polluting the edge / ML
/ audit datasets that already exclude paper data.

2026-05-23 update: `OPENCLAW_ENABLE_PAPER=1` no longer enables an active paper
runtime path. Paper is retained as Archive / replay-infrastructure lineage only.
It is not part of AMD-03 graduated canary, unblock, or promotion evidence.
Active canary flow is Stage 0R replay preflight followed by Stage 1 Demo
micro-canary.

## Consequences

The 3E-ARCH structure is preserved (Paper kind/state/predictors all retained); only runtime spawn is gated. Edge studies must continue to source from Demo, never Paper.
