# BB Review - ALR F5 Exact Demo Authorization Packet

Date: 2026-07-10
Verdict: `BB_APPROVE_EXACT_PACKET_FOR_OPERATOR_DECISION_ONLY`
Packet SHA-256: `1ab349a6f753e4d3846b0699d7404f18e231d8ca95b8f250bb19b9f89b7eabde`

The packet hash matches. Canonical reproduction gives manifest hash
`4838cce69cc50517740451aa0e495207b636bc2ec892a339811aafd122ecc9f3`,
runtime hash
`0e8eacd5a9f9874fd30de999de302ea801d0a13676b8df3dde3e73170cdc7cc2`,
and VOI score `1 + 1 - 0.7153 - 0.125 = 1.1597`.

The `1020s` envelope, `+960s` close-submission ceiling, one-entry/one-cancel/
one-reduce-only-close state machine, local BBO/instrument recapture, admission
checks, and `1.25000 USDT` loss ceiling are bounded and fail closed. The same
single exact operator decision covers the three permitted actions and nothing
else. Partial/rejected paths cannot widen the packet.

This is approval only to present the exact hash to the operator. It is not
operator authorization or execution approval. Global Cost Gate, Guardian,
RiskConfig, live/mainnet, serving, promotion, and `_latest` remain untouched;
all authority flags are false and all action counters are zero. The stale
`bd90...` review is superseded.

