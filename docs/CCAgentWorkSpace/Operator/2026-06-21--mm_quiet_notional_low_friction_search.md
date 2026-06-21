# 2026-06-21 -- Operator note: MM quiet-notional low-friction search

No operator action is required.

What changed:

- fill_sim now searches existing PIT `recent_trade_abs_qty_10s/30s` as quiet-notional low-friction features.
- The new candidates are research-only and artifact-only.
- Latest runtime alpha remains `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`.

Latest evidence:

- best refreshed sample-gated gross MM cell: `2.647bp`
- current maker round-trip threshold: `4.0bp`
- net at current fee: `-1.353bp`
- break-even maker fee: `1.3235bp/side`
- train leg did not pass sample gate, so this is not a promotion candidate.

Boundary:

- No trading call.
- No order/risk/strategy/auth mutation.
- No engine/API restart.
- No PG write or schema migration.

Practical implication: keep collecting/searching. Do not treat lower-fee cases or holdout-only low-friction cells as actionable at current scale.
