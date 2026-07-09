# PM Authorization - ALR P2-4 Shadow Apply R2

Date: 2026-07-09
State: `AUTHORIZED_EXACT_P2_4_SHADOW_APPLY_R2`
Authority chain: PM -> E3 -> BB -> PM, `ROLE_FALLBACK_SINGLE_SESSION`

PM accepts E3 and BB R2 without expansion. Apply only source head
`cf2fb7607b5bacf35bc2a50f168453f10dfbada9`, V152, the reviewed role contract,
and the source-head-pinned existing ALR unit restart. Stop on source/migration/
privilege/service mismatch, scanner mutation, nonzero authority counters, or
any need to touch the engine.

No order, probe, Decision Lease, Cost Gate, Bybit/official-MCP, live/mainnet,
RiskConfig, Guardian, order dispatch, serving, promotion, `_latest`, proof, or
deletion authority is granted.
