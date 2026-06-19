# MLDE LinUCB / Shadow Timeout Fix

VERDICT: PASS_WITH_LIMITS
CONFIDENCE: high

日期：2026-06-20

## 結論

Production logs showed a live learning blindspot: daily ML training maintenance and the API scheduler repeatedly timed out on all 15 LinUCB arms, and `mlde_shadow_advisor` also timed out. The root cause matched the 2026-06-14 ADPE RCA: consumers were still reading `learning.mlde_edge_training_rows`, whose `trading.signals` lateral can bulk-decompress compressed Timescale chunks.

This patch preserves the MLDE training-row contract but switches LinUCB and shadow-advisor reads to base-table queries over `trading.intents`, `learning.decision_features`, and the PK-backed `trading.decision_context_snapshots` lateral. Routine LinUCB windows now default to 30d, with 5s statement timeout.

## Evidence

- `/tmp/openclaw/logs/ml_training_maintenance_cron.log` showed repeated `fetch_arm_observations ... canceling statement due to statement timeout` on 2026-06-16 through 2026-06-19.
- `/tmp/openclaw/api.log` showed the same LinUCB arm timeouts plus `mlde shadow advisor failed: canceling statement due to statement timeout`.
- Remote read-only smoke with patched modules:
  - 30d `demo_live_demo` all 15 LinUCB arms: 14.1s total, max single arm 1.69s, 94,734 rows, no timeout.
  - shadow aggregate: demo 570ms, live_demo 520ms, no timeout.
  - 90d all-arm smoke was manually interrupted after >60s, so routine scheduler default was reduced to 30d.

## Verification

- `python3 -m py_compile program_code/ml_training/linucb_trainer.py program_code/ml_training/mlde_shadow_advisor.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py helper_scripts/cron/ml_training_maintenance.py`
- `bash -n helper_scripts/cron/ml_training_maintenance_cron.sh`
- `python3 -m pytest program_code/ml_training/tests/test_linucb_trainer.py program_code/ml_training/tests/test_mlde_shadow_advisor.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_edge_estimator_scheduler_observability.py -q` = 36 passed
- `git diff --check` on the touched files = PASS

## Boundary

No schema migration, no DB write during remote smoke, no Bybit private/signed call, no auth/risk/order/trading mutation. This restores routine learning/advisory freshness; it is not an alpha promotion proof.
