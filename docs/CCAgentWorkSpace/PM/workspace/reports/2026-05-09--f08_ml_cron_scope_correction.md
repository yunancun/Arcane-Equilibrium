# F-08 ML Cron Scope Correction

## Scope

- Target: W-AUDIT-4 F-08 / `P2-AUDIT-VERIFY-4`.
- Boundary: source/test only. No crontab install, DB write, rebuild, restart, live auth mutation, or runtime reload.
- Reason: AI-E v2 verified the previous `ml_training_maintenance` runner covered a different five jobs than the original audit target set.

## Source Fix

`helper_scripts/cron/ml_training_maintenance.py` now separates:

- operational jobs: `linucb_trainer`, `mlde_shadow_advisor`, `mlde_demo_applier`, `scorer_trainer`, `quantile_trainer`
- original audit jobs: `thompson_sampling`, `optuna_optimizer`, `cpcv_validator`, `dl3_foundation`, `weekly_report_generator`

The cron wrapper default job list includes both sets.

Real paths added for the original audit jobs:

- `thompson_sampling`: aggregates real `trading.fills` returns into `learning.bayesian_posteriors`.
- `optuna_optimizer`: uses IPC/env param ranges plus real fills and writes `learning.ml_parameter_suggestions` when data/deps exist.
- `cpcv_validator`: invokes the existing training pipeline CPCV path.
- `dl3_foundation`: reads real `market.klines` history and writes `learning.foundation_model_features`.
- `weekly_report_generator`: runs with `--persist` and writes `learning.weekly_review_log`.

## Verification

- `python3 -m py_compile helper_scripts/cron/ml_training_maintenance.py tests/helper_scripts/test_ml_training_maintenance_cron_static.py`
- `python3 -m pytest -q tests/helper_scripts/test_ml_training_maintenance_cron_static.py`
- `python3 helper_scripts/cron/ml_training_maintenance.py --jobs thompson_sampling,optuna_optimizer,cpcv_validator,dl3_foundation,weekly_report_generator --dry-run --force-audit-jobs --status-json /tmp/openclaw_ml_training_maintenance_test_status.json`
- `python3 -m pytest -q tests/helper_scripts/test_ml_training_maintenance_cron_static.py program_code/ml_training/tests/test_weekly_report_generator.py program_code/ml_training/tests/test_dl3_foundation.py program_code/ml_training/tests/test_thompson.py`

## Residual

This closes the source scope mismatch only. Runtime impact still requires operator-authorized crontab installation and a 24h fire verification.
