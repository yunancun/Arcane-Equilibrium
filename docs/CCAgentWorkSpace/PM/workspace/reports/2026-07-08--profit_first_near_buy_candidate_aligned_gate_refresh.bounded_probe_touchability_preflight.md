# Bounded Demo Probe Touchability Preflight

- Generated: `2026-07-08T10:10:43.996834+00:00`
- Status: `FIRST_ATTEMPT_TOUCHABILITY_BOOTSTRAP_REQUIRED`
- Reason: no_candidate_matched_orders_exist_for_first_touchability_attempt
- Candidate: `ma_crossover|NEARUSDT|Buy`
- Order-touchability status: `FILL_FLOW_PRESENT`
- Reviewed orders: `100`
- Candidate-matched orders: `0`
- Candidate-matched fills: `0`
- Deep passive no-touch orders: `0`
- Max observed best-touch gap bps: `146.6077`
- Required max initial passive gap bps: `75.0`
- Boundary: artifact-only bounded Demo probe touchability preflight; no PG query/write, Bybit call, order, config, risk, auth, runtime mutation, Cost Gate lowering, probe authority, order authority, or promotion proof

## Next Actions

- `build_review_only_first_attempt_near_touch_or_skip_design`
- `require_separate_operator_authorization_before_any_candidate_order`
- `rerun_order_to_fill_touchability_audit_after_first_candidate_attempt`
