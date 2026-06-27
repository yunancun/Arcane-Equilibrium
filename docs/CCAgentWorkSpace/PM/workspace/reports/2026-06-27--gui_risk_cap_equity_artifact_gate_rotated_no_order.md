# GUI Risk Cap Equity Artifact Gate Rotated No-Order

| Field | Value |
|---|---|
| `blocker_id` | `P0-GUI-RISK-CAP-RESOLVER-CURRENT-CANDIDATE-DRIFT-RECONCILE` |
| `state_transition` | `ROTATED` |
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260627T004415Z_gui_risk_cap_resolver_eth_no_order.json` |
| `session_loop_state_sha256` | `f85450ed96d21b3f7f414e9ab581f062832a1e67f30cd47d33ecc62bf9bcf859` |

## Runtime Delta

Read-only runtime inspection found that canonical `_latest` artifacts are no longer ETH:

- bounded auth latest sha `247113ac575aaaa2075a1ce1ba5911c339a79ac9c61f03f681d3e95d1e5a27de`
- mtime `2026-06-27T00:45:04.817271+00:00`
- status `FALSE_NEGATIVE_PREFLIGHT_NOT_READY`, decision `defer`
- candidate `grid_trading|AVAXUSDT|Sell`
- false-negative review sha `9cd4a0063f05fdd53873dec0401bc404a4c104267e99a47ff4210836d54d5f36` is `STANDING_DEMO_AUTHORIZATION_INVALID_FOR_PREFLIGHT_REVIEW`
- preflight sha `bbdfd1e13ee6591552b667dcc410ba0344e7f07c82a3f55730e7d1c4ed85b077` is `STANDING_DEMO_AUTHORIZATION_INVALID_FOR_PREFLIGHT`

No current `source_only_control_identity_contract_latest.json`, `bounded_probe_candidate_construction_preview_latest.json`, or audited balance/equity artifact was found under `/tmp/openclaw` read-only search. ETH-specific construction refresh is therefore rotated/stale until runtime artifacts realign.

## Source Change

`current_cap_staircase_risk_worksheet.py` now requires an accepted `demo_account_equity_artifact_v1` before deriving `resolved_cap_usdt`.

Accepted equity evidence must wrap `/api/v1/strategy/demo/balance?fast=1` output and prove:

- Demo environment
- `read_model = rust_snapshot_fast`
- `pipeline_status = connected`
- positive equity
- fresh `generated_at_utc`
- no authority/order/proof/runtime/PG/Bybit contamination

Naked `--account-equity-usdt` now fails closed and can only cross-check a matching artifact.

## Verification

```text
PYTHONPATH=helper_scripts/research ./venvs/mac_dev/bin/python -m pytest -q \
  helper_scripts/research/tests/test_cost_gate_current_cap_staircase_risk_worksheet.py
12 passed

PYTHONPATH=helper_scripts/research ./venvs/mac_dev/bin/python -m pytest -q \
  helper_scripts/research/tests/test_cost_gate_bbo_freshness_public_quote_capture.py \
  helper_scripts/research/tests/test_atomic_quote_adapter_preview_runner.py \
  helper_scripts/research/tests/test_cost_gate_atomic_quote_adapter_preview_design.py \
  helper_scripts/research/tests/test_cost_gate_reviewed_public_quote_capture_packet.py \
  helper_scripts/research/tests/test_public_quote_market_snapshot_adapter.py \
  helper_scripts/research/tests/test_cost_gate_bounded_probe_candidate_construction_preview.py \
  helper_scripts/research/tests/test_cost_gate_current_cap_staircase_risk_worksheet.py
113 passed

./venvs/mac_dev/bin/python -m py_compile ...modified module/test
PASS
```

CLI smoke path: `/tmp/openclaw/gui_risk_cap_equity_artifact_smoke_20260627T0044Z`.

- `manual_equity_rejected.json`: `GUI_RISK_CAP_INPUT_REQUIRED_NO_AUTHORITY`, `resolved_cap_usdt=None`, artifact accepted `false`
- `equity_artifact_ready.json`: `CURRENT_CAP_STAIRCASE_RISK_WORKSHEET_READY_NO_AUTHORITY`, `resolved_cap_usdt=20.0`, artifact accepted `true`, ETH min executable notional `15.7105`, tier count `1`

## Boundary

No runtime sync, no Bybit/API/private/order/cancel/modify call, no PG query/write, no service/crontab/env mutation, no Cost Gate lowering, no risk expansion, no adapter/writer enablement, no probe/order/live authority, and no profit/proof claim.

## Next

Open a narrow PM -> E3 -> BB review for exact cache-only Demo fast-balance equity artifact capture plus current-candidate no-order construction refresh/reconcile. If no accepted equity artifact or current-candidate scope cannot be reconciled, mark `BLOCKED_BY_LOSS_CONTROL`; if candidate rotates again, record `ROTATED`.
