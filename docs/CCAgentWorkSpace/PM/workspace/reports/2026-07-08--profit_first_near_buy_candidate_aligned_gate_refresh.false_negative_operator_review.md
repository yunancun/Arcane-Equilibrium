# Cost Gate False-Negative Operator Review

- Generated: `2026-07-08T10:06:47.482566+00:00`
- Status: `APPROVED_COST_GATE_FALSE_NEGATIVE_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT`
- Decision: `approve-preflight`
- Operator: `profit-first-fast-demo-loop`
- Side-cell: `ma_crossover|NEARUSDT|Buy`
- False-negative rank: `1`
- Avg net bps: `64.983`
- Net cost cushion bps: `64.983`
- Wrongful block score: `129.9659`
- Boundary: artifact-only Cost Gate false-negative operator review; no PG query/write, Bybit call, order, config, risk, auth, runtime mutation, main Cost Gate lowering, probe authority, order authority, or promotion proof.

## Approval Phrase

`approve_cost_gate_false_negative_preflight:ma_crossover|NEARUSDT|Buy:1`

## Gates

| gate | passed | status | reason |
|---|---:|---|---|
| authority_boundary_preserved | `True` | `PRESERVED` | review input must not grant Cost Gate lowering, probe/order authority, or promotion proof |
| standing_demo_authorization_valid_for_preflight_review | `True` | `VALID` | standing Demo envelope must be fresh, Demo-only, scoped for bounded probe review, candidate-scoped, unexpired, and free of runtime/order/Cost Gate/promotion authority |
| false_negative_candidate_packet_ready | `True` | `COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW` | candidate packet must be fresh, schema-valid, and ready for operator review |
| candidate_selected | `True` | `SELECTED` | review must name a ranked false-negative side-cell candidate |
| candidate_reviewable | `True` | `DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE` | selected candidate must remain a no-authority false-negative after-cost review row |
| operator_id_present | `True` | `PRESENT` | approval requires a non-empty operator id |
| typed_confirm_matches | `True` | `STANDING_DEMO_AUTHORIZATION` | typed-confirm approval requires the exact phrase; standing Demo envelope approval is recorded in its separate fail-closed gate |

## Next Actions

- `build_candidate_matched_bounded_demo_probe_preflight_for_approved_false_negative`
- `preserve_global_cost_gate_no_lowering`
- `require_touchability_fill_fee_slippage_lineage_before_probe_authorization`
