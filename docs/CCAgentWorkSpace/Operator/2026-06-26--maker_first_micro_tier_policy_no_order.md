# Operator Note: Maker-First Micro-Tier Placement Policy No-Order

Status: `DONE_WITH_CONCERNS`

PM closed `P1-AGGRESSIVE-ALPHA-MAKER-FIRST-MICRO-TIER-PLACEMENT-POLICY-NO-ORDER` as source/test/docs only. The new helper `helper_scripts/research/cost_gate_learning_lane/maker_first_micro_tier_policy.py` defines the future maker-first placement/skip policy for AVAX.

The packet does not call Bybit, does not capture quotes, and does not authorize placement. It selects the smallest current-cap AVAX tier as the primary review tier (`0.9 AVAX / 5.4576 USDT`), keeps larger tiers review-only, requires `PostOnly` maker-first limit-or-skip, and requires a Sell limit to stay non-marketable against best_bid. If spread/cost/edge-cushion data is missing or unfavorable, the policy says skip, not taker fallback.

Smoke artifact:

`/tmp/openclaw/maker_first_micro_tier_policy_smoke_20260626T085600Z/maker_first_micro_tier_policy.json`

Smoke status is `MAKER_FIRST_MICRO_TIER_POLICY_READY_NO_AUTHORITY`. All authority/proof answers remain false, including public quote capture, placement call, Bybit call, probe/order/live authority, PG query/write, order admission, Cost Gate lowering, promotion evidence, and promotion proof.

Per your request, stop after this round. Next if resumed and no real authorization delta: `P1-AGGRESSIVE-ALPHA-REVIEWED-PUBLIC-QUOTE-CAPTURE-PACKET-NO-CAPTURE`. If a real AVAX-scoped auth delta appears first, return to `P0-BOUNDED-PROBE-AUTHORIZATION`.
