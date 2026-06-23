# Operator Note: Sealed Horizon Operator Review Runtime Canonicalization

The alpha discovery cron now produces a canonical pending/defer sealed-horizon operator-review artifact before the profitability scorecard runs.

Canonical files:

- `/tmp/openclaw/cost_gate_learning_lane/sealed_horizon_operator_review_latest.json`
- `/tmp/openclaw/cost_gate_learning_lane/sealed_horizon_operator_review_latest.md`

Important boundary: the cron uses `--decision defer` and does not pass `--operator-id` or `--typed-confirm`. This is a review surface only. It does not approve preflight, authorize a bounded demo probe, lower Cost Gate, grant order/probe authority, mutate runtime, or create promotion evidence.

After runtime sync and alpha cron smoke, the killboard should expose:

- `sealed_horizon_operator_review_present`
- `sealed_horizon_operator_review_status`
- `sealed_horizon_operator_review_decision`
- `sealed_horizon_operator_review_approved`
- `sealed_horizon_operator_review_review_grants_runtime_authority`
- `sealed_horizon_operator_review_order_authority_granted`
- `sealed_horizon_operator_review_probe_authority_granted`

This keeps the Cost Gate escape path explicit: convert blocked-signal learning evidence into reviewed bounded demo probe evidence, then require separate preflight alignment and separate bounded demo authorization before any actual probe.

