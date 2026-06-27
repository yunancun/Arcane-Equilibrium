# Demo Fast-Balance Equity Artifact Source

| Field | Value |
|---|---|
| `blocker_id` | `P0-GUI-RISK-CAP-RESOLVER-CURRENT-CANDIDATE-DRIFT-RECONCILE` |
| `state_transition` | `DONE_WITH_CONCERNS` |
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260627T0100Z_demo_fast_balance_equity_artifact_source.json` |
| `session_loop_state_sha256` | `8191a90b29eb3ef2a789051065a7f42466d9c0c407ca931a7f82a05f8a41dae9` |

## Source Change

Added `helper_scripts/research/cost_gate_learning_lane/demo_fast_balance_equity_artifact.py`.

The helper emits `demo_account_equity_artifact_v1` only when the supplied/captured payload is the Demo fast balance contract:

- endpoint: `GET /api/v1/strategy/demo/balance?fast=1`
- Phase 2 paper envelope: `action_result=success`, `is_simulated=true`, `data_category=paper_simulated`
- data source: `rust_engine`
- read model: `rust_snapshot_fast`
- pipeline: `connected`
- equity: positive USDT value
- authority scan: no Bybit, PG, order, runtime, risk, Cost Gate, probe/order/live, or proof contamination

Capture mode is fixed to approved local Control API bases and loads Bearer tokens only from `OPENCLAW_API_TOKEN` or a `0600` token file. It does not accept tokens on argv.

`current_cap_staircase_risk_worksheet.py` now also requires account-equity artifacts to carry status `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY`. A source-failure or not-ready artifact cannot resolve GUI risk cap by schema shape alone.

## Verification

```text
PYTHONPATH=helper_scripts/research ./venvs/mac_dev/bin/python -m pytest -q \
  helper_scripts/research/tests/test_cost_gate_demo_fast_balance_equity_artifact.py \
  helper_scripts/research/tests/test_cost_gate_current_cap_staircase_risk_worksheet.py
22 passed

PYTHONPATH=helper_scripts/research ./venvs/mac_dev/bin/python -m pytest -q \
  helper_scripts/research/tests/test_cost_gate_*.py
510 passed

PYTHONPATH=helper_scripts/research ./venvs/mac_dev/bin/python -m py_compile \
  helper_scripts/research/cost_gate_learning_lane/demo_fast_balance_equity_artifact.py \
  helper_scripts/research/cost_gate_learning_lane/current_cap_staircase_risk_worksheet.py
PASS

git diff --check
PASS
```

Unit integration verifies the operator correction directly: GUI `per_trade_risk_pct=0.1` means `10.0%`. With Demo equity `200`, the resolver returns `per_order_cap_usdt=20.0`; the older construction-preview `cap_usdt=10.0` remains diagnostic-only and is not risk authority.

## Boundary

No runtime/control API capture, no Bybit/API/private/order/cancel/modify call, no PG query/write, no service/crontab/env mutation, no Cost Gate lowering, no risk expansion, no adapter/writer enablement, no probe/order/live authority, and no profit/proof claim.

## Concern

This checkpoint provides the source producer and consumer gate only. It did not capture a runtime Demo fast-balance artifact and did not refresh the current AVAX no-order construction preview.

## Next

Open a narrow PM -> E3 -> BB review for exact cache-only Demo fast-balance equity artifact capture plus current-candidate no-order construction refresh/reconcile. If no accepted equity artifact or current-candidate scope cannot be reconciled, mark `BLOCKED_BY_LOSS_CONTROL`; if candidate rotates again, record `ROTATED`.
