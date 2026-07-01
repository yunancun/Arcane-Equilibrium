# Demo Fast-Balance Source Policy Guard

## Scope

Active blocker: `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD`.

This was a source/test/docs checkpoint only. It addressed the BB review condition from the previous standing-envelope refresh attempt:

- prove the runtime artifact capture can use token-file-only auth and fail if `OPENCLAW_API_TOKEN` fallback is present;
- prove `/api/v1/strategy/demo/balance?fast=1` remains on the Rust snapshot fast path and cannot fall through to Bybit wallet REST when the snapshot is unavailable.

Source moved while the patch was in flight. PM first built the patch on `f1d6dd1c8bffa0ec7338e3dfc7c8c973d905e032`, rebased cleanly onto `origin/main 0a22594caf837d07119cd96e735df0cf90601ffd`, then rebased cleanly again onto pre-push upstream `origin/main 601f94514f3d0fac3f2a824cbb8a7a3ec63a874c`.

## Source Changes

- `helper_scripts/research/cost_gate_learning_lane/demo_fast_balance_equity_artifact.py`
  - adds `--forbid-env-token`;
  - records `token_source`, env-token policy, token-file path/mode/existence/used metadata;
  - raises `SourcePolicyError` before any Control API GET if env-token fallback is forbidden but `OPENCLAW_API_TOKEN` exists;
  - still records no token values, prefixes, suffixes, or hashes.
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_ai_routes.py`
  - fail-closes fast Demo balance when the Rust snapshot is unavailable;
  - returns `source=rust_engine`, `read_model=rust_snapshot_fast`, `pipeline_status=snapshot_unavailable`, and `balance=None`;
  - does not call `_get_rust_client()` / `refresh_balance` in the missing-snapshot fast path.
- Tests were added/updated for both contracts.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=helper_scripts/research python3 -m pytest -q -p no:cacheprovider helper_scripts/research/tests/test_cost_gate_demo_fast_balance_equity_artifact.py
# 13 passed

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code/exchange_connectors/bybit_connector/control_api_v1 python3 -m pytest -q -p no:cacheprovider program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_gui_fast_snapshot_routes.py
# 8 passed; existing Pydantic deprecation warnings

PYTHONDONTWRITEBYTECODE=1 python3 -B -m py_compile helper_scripts/research/cost_gate_learning_lane/demo_fast_balance_equity_artifact.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_ai_routes.py
git diff --check origin/main..HEAD
```

E2/E4 read-only reviews returned `DONE_WITH_CONCERNS` with no blocking findings. E4 identified missing direct CLI/redaction assertions; PM added them and reran the focused suites above.

## Boundary

No runtime or exchange-facing action occurred. No Control API GET, public quote, runtime standing-envelope materialization, plan inclusion preview, canonical plan write, `_latest`, Decision Lease, private/order endpoint, order/cancel/modify, PG write, service/env/risk mutation, Cost Gate change, live/mainnet, fill/PnL/proof, or consumable approval occurred.

## Status

State transition: `DONE_WITH_CONCERNS`.

The source gaps are closed, but the standing Demo envelope remains expired in the last verified runtime evidence. The next PM step is a fresh current-head source/impact guard plus exact E3/BB runtime-refresh request using the new `--forbid-env-token` capture contract. No runtime action is allowed without fresh E3 and BB approval.
