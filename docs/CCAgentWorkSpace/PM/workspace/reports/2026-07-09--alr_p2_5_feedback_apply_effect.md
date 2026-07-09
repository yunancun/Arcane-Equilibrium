# PM Apply Effect - ALR P2-5 Feedback and Rotation

Date: 2026-07-09
State: `P2_5_OPERATIONAL_COMPLETE_P2_6_ACTIVE`
Authority chain: PM -> E3 -> BB -> PM, `ROLE_FALLBACK_SINGLE_SESSION`

At aligned source head `2787042d09960186cb6edd1471c4c712ff78af0d`, PM applied
V153, re-applied the reviewed shadow role contract, and restarted only
`openclaw-alr-shadow.service` with its new source-head pin.

The service persisted one P2-5 outcome feedback event for the prior P2-4 run:
`DEFER_EVIDENCE`, proof absent, reward count zero, `rotate_next_target=true`,
and `global_stop=false`. It then made one next scanner-backed target decision.
Production readback has two `DEFER_EVIDENCE` statistical runs, 64
`training_input` edges, one feedback-rotation edge, zero duplicate source keys,
and exact false/zero authority fields for both run and feedback ledgers.

The scanner count advanced from `79757` to `79758` during the checkpoint because
the unchanged Rust engine wrote a natural cycle. ALR has scanner INSERT denied,
and no scanner write originated from this service. The engine stayed PID
`1561777`; no engine action, exchange/MCP call, order/probe, Decision Lease,
Cost Gate, proof claim, serving, promotion, `_latest`, or deletion occurred.

P2-6 is active for ALR-owned derived-cache retention only.
