# Earn Wave D IPC Contract Integration Checkpoint

Date: 2026-06-18
Owner: PM local execution
TODO: `P2-EARN-WAVE-D-CONTRACT-INTEGRATION-TEST`

## Result

Closed the Wave D source/test contract gap between Python `/api/v1/earn/stake` and Rust IPC:

- Rust IPC method `process_earn_intent` is now registered in dispatch + method metadata.
- IPC handler validates the Python param contract and routes through `EngineCommandChannels`.
- New `PipelineCommand::ProcessEarnIntent` carries the Earn stake payload into the per-pipeline owner task.
- Event consumer async path builds an Earn `OrderIntent` and calls `IntentProcessor::process_earn_intent`.
- Python route test now locks method name, timeout, and exact 8-field param shape.
- Rust tests cover IPC dispatch -> command envelope and owner-task fail-closed behavior.

## Verification

- `cargo test -p openclaw_engine process_earn_intent --lib`
  Result: 3 passed.
- `cargo test -p openclaw_engine earn_router_fail_closed_when_unwired --lib`
  Result: 1 passed.
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_earn_routes.py`
  Result: 28 passed, 1 existing Pydantic deprecation warning.

## Boundary

This does **not** execute a real Bybit Earn stake. Current production bootstrap still does not inject `BybitEarnClient` or `EarnMovementWriter` into `IntentProcessor`, so the true Rust path returns:

```text
submitted=false
rejected_reason contains earn_dispatch_unwired
```

That is the intended fail-closed contract for this checkpoint. No credential/key/secret mutation, no real Bybit call, no deploy/rebuild/restart, and no runtime/DB/auth/risk/order/trading mutation occurred.

## Remaining

`P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` remains active. It requires OP-1/OP-2/OP-3 plus Rust Earn capability injection before a first real stake can be claimed.
