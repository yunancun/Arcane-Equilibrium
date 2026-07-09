# MLDE Demo Autonomous Applier Report

Date: 2026-04-29 18:45 CEST

## Decision

Operator requested ML / DreamEngine / other ML to learn on demo, tune all adjustable strategy/risk/leverage parameters there, then deploy improved models or parameter sets to live.

Implemented boundary:

- Demo can autonomously apply bounded MLDE recommendations.
- Live/live_demo cannot be mutated by this path.
- Strong demo evidence creates a governed live `experiment_plan` candidate only.
- Live deployment still requires GovernanceHub approval, Decision Lease, and existing live gates.

## Implementation

- Added migration `sql/migrations/V032__mlde_demo_param_applications.sql`.
- Added `program_code/ml_training/mlde_demo_applier.py`.
- Wired applier into `EdgeEstimatorScheduler._run_mlde_unblock()` for `mode == "demo"`.
- Added healthcheck `[37] mlde_demo_applier`.
- Adjusted healthcheck `[35]` so legacy pre-attribution rows do not keep the deploy permanently red; only recent attribution regressions fail.

## Parameter Surfaces

Strategy parameters:

- Current params from Rust `get_strategy_params`.
- Adjustable ranges from Rust `get_param_ranges`.
- Apply through `update_strategy_params`.
- Supports ML `rank`/`veto`, DreamEngine parameter proposals, and explicit `proposed_params`.

Risk / leverage:

- Current RiskConfig from `get_risk_config(engine=demo)`.
- Apply through `patch_risk_config(engine=demo, source=agent)`.
- Supports OpportunityTracker regret summaries and explicit `risk_patch`.
- Numeric patches are delta-bounded against the current config.

Live promotion:

- Positive demo evidence can create live `experiment_plan` rows in `learning.mlde_shadow_recommendations`.
- These rows are `applied=false` and `requires_governance=true`.

## Tunability

Defaults are env-tunable:

- `OPENCLAW_MLDE_DEMO_APPLIER_ENABLED`
- `OPENCLAW_MLDE_DEMO_APPLIER_LOOKBACK_HOURS`
- `OPENCLAW_MLDE_DEMO_APPLIER_MIN_CONFIDENCE`
- `OPENCLAW_MLDE_DEMO_APPLIER_MIN_SAMPLES`
- `OPENCLAW_MLDE_DEMO_APPLIER_MAX_RECOMMENDATIONS`
- `OPENCLAW_MLDE_DEMO_APPLIER_MAX_PARAM_DELTA_PCT`
- `OPENCLAW_MLDE_DEMO_APPLIER_MAX_RISK_DELTA_PCT`
- `OPENCLAW_MLDE_DEMO_APPLIER_DEDUPE_HOURS`
- `OPENCLAW_MLDE_LIVE_CANDIDATE_MIN_CONFIDENCE`
- `OPENCLAW_MLDE_LIVE_CANDIDATE_MIN_SAMPLES`
- `OPENCLAW_MLDE_LIVE_CANDIDATE_MIN_NET_BPS`
- `OPENCLAW_MLDE_DEMO_APPLIER_DRY_RUN`

## Verification

Local targeted tests:

```bash
python3 -m pytest -q \
  program_code/ml_training/tests/test_mlde_demo_applier.py \
  helper_scripts/db/test_mlde_healthchecks.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_edge_estimator_scheduler_observability.py
```

Result: 21 passed.

## Follow-Up

- Observe `learning.mlde_shadow_recommendations`, `learning.mlde_param_applications`, and `learning.linucb_state` after runtime deploy.
- `[35]` may warn until post-fix fills produce LinUCB-ready rows.
- `[36]` may warn until advisory rows exist.
- `[37]` may warn until the applier has an actionable demo recommendation.
- Switching Rust active LinUCB arm-space from `v1_15` to richer `mlde_arm_id` remains a separate migration.
