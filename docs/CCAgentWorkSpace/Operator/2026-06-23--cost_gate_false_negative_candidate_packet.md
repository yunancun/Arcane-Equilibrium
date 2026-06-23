# Operator Note: Cost Gate False-Negative Candidate Packet

Source checkpoint: `b713c672`

This pass adds a ranked packet for Cost Gate blocked-signal learning.

The new packet answers:

- Which blocked signals look like after-cost false negatives?
- Which rows need stronger edge or lower friction before they can cross cost?
- Which rows still need more samples?
- Which rows should stay blocked?

Latest Linux artifact-only smoke on the current blocked-outcome review reports:

- status: `COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW`
- false-negative candidates: `16`
- top candidate: `grid_trading|AVAXUSDT|Sell`
- top net cost cushion: `73.4563bps`
- top wrongful-block score: `146.9126`

Operational meaning: do not globally lower Cost Gate. Review the ranked
false-negative candidates first, then require bounded Demo probe authority and
candidate-matched touchability/fill/fee/slippage lineage before any Cost Gate
change.

No authority was granted: no Cost Gate lowering, no probe/order authority, no
runtime mutation, no deployment, no actual order, and no promotion proof.
