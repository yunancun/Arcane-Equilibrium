# E3 Review - ALR F5 Exact Demo Authorization Packet

Date: 2026-07-10
Verdict: `E3_APPROVE_EXACT_PACKET_FOR_OPERATOR_DECISION_ONLY`
Packet SHA-256: `1ab349a6f753e4d3846b0699d7404f18e231d8ca95b8f250bb19b9f89b7eabde`

The immutable packet closes the five prior blockers. Its latest possible entry
fill is `+90s`, close submission is bounded by the earlier of `fill+900s` and
authorization `+960s`, and reconciliation/lease cleanup ends by `+1020s`.
Zero-, partial-, and full-fill paths bind the sole entry identity, at most one
residual cancel, and at most one exact-open-quantity reduce-only Buy Market IOC
close. Cancel/close rejection remains fail-closed and cannot create a retry,
replacement, second entry, or second close.

One exact `AUTHORIZE_EXACT_PACKET` decision covers only that entry, cancel, and
risk-reducing close. The loss components total `1.00000 USDT` plus a `0.25000`
reserve under a hard `1.25000 USDT` envelope with pre-entry depth/slippage
admission. The embedded VOI manifest and runtime hashes reproduce exactly, and
the repository arbiter rebuild matches the embedded runtime payload.

This review grants no operator, exchange, trading, order/probe, Decision Lease,
Cost Gate, proof, serving, promotion, or `_latest` authority. The packet remains
Demo-only and unauthorized; all authority flags are false, all action counters
are zero, and no exchange contact or action occurred.

