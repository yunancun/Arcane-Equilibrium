# Governance IPC Protocol Diagnostics Ready

## Summary

PM advanced `P0-CURRENT-CANDIDATE-FRESH-INVOCATION-WINDOW-SOURCE-INPUT-REFRESH-GATE` by diagnosing and fixing the recurrent read-only governance IPC blocker without retrying public quote capture.

- Session loop state: `/tmp/openclaw/session_loop_state_20260701T_ipc_response_mismatch_diagnosis/session_loop_state.json`, sha `f434bba0960db9b1bbfed46112c76c942234a2d531752bdf6dceee078ee9f751`, status `DONE_WITH_CONCERNS`.
- Source commits:
  - `5f45254cf3f6c09fcc08d2ab3450e32cd656a125` adds fail-closed JSON-RPC protocol diagnostics.
  - `c5fce0c6008b783e8264ce06a3a5f781fe18c26e` fixes the snapshot helper await call and adds default-dispatcher coverage.
- Runtime cherry-picks:
  - `4353be2164166d889306f896c9d88fa6163b31de` cherry-picks `5f45254c`.
  - `461dfbe210a46b3cd9c23a1424085124adf5b9ee` cherry-picks `c5fce0c6`.

## Source Fix

`EngineIPCClient` now raises `EngineProtocolError` when the auth response id is not `0`, when auth does not return `result.authenticated=true`, when normal responses have the wrong id, or when normal responses have no `result`.

`runtime_governance_ipc_readonly_snapshot.py` no longer routes its production/default one-shot IPC call through `governance_lease_bridge._run_async_blocking`, which collapsed exceptions into `None`. It now awaits the one-shot coroutine directly and preserves protocol error reasons in fail-closed method entries.

## Verification

Mac/source verification:

- `test_ipc_client_protocol_unit.py` + HMAC smoke + disconnected smoke: `8 passed`.
- `test_runtime_governance_ipc_readonly_snapshot.py`: `6 passed`.
- `py_compile`: passed.
- `git diff --check`: passed.
- E2: `ACCEPT_WITH_CONCERNS`; auth-response validation finding addressed before commit.
- E4: `PASS`.

Runtime verification after E3 approval:

- Runtime precheck clean at `5e1c4091c1ce9182fcafa83c55feb4a9887425cb`, then source commit `5f45254c` cherry-picked to `4353be2164166d889306f896c9d88fa6163b31de`.
- First E3-approved read-only diagnostic snapshot `/tmp/openclaw/runtime_governance_ipc_protocol_diagnostics_20260701T004353Z/governance/runtime_governance_snapshot.json` sha `ac0aaf45bf3e5c9742f4a1af8757e5ce2b65d5af24977802120fa3057d427f55` failed before IPC as `ipc_dispatch_exception:TypeError`, exposing the helper await-call bug.
- Source commit `c5fce0c6` fixed that bug and was cherry-picked after second E3 approval to runtime `461dfbe210a46b3cd9c23a1424085124adf5b9ee`.
- Runtime source-only checks after the second cherry-pick: IPC protocol/HMAC smoke `8 passed`, snapshot helper tests `6 passed`, `py_compile` passed, `git diff --check` passed.
- Final read-only governance snapshot `/tmp/openclaw/runtime_governance_ipc_protocol_diagnostics_20260701T004959Z_after_await_fix/governance/runtime_governance_snapshot.json` sha `53930c4bf898f0308a2a643833f956b8e65f760f7c4750ffcfece87549456176` is `RUNTIME_GOVERNANCE_IPC_READONLY_SNAPSHOT_READY`.

Final snapshot summary:

- `runtime_blockers=[]`
- `risk_level=NORMAL`
- `position_size_multiplier=1.0`
- `new_entries_allowed=true`
- `lease_live_count=0`
- `lease_count=0`
- `governance.get_status`, `governance.list_leases`, and `governance.get_risk_state` all returned `ok=true`.

## Boundary

No public quote retry, Bybit endpoint, private endpoint, PG query/write, Decision Lease acquire/release, order/cancel/modify, service restart, risk mutation, Cost Gate mutation, live/mainnet authority, fill/PnL, or profit proof occurred.

The READY governance snapshot is read-only runtime state evidence only. It does not grant order authority, persistent active lease evidence, Cost Gate proof, live/mainnet authority, or downstream admission clearance.

## Next

State transition: `DONE_WITH_CONCERNS`.

Next blocker remains `P0-CURRENT-CANDIDATE-FRESH-INVOCATION-WINDOW-SOURCE-INPUT-REFRESH-GATE`. The consumed no-retry BB public quote scope remains consumed. The next PM should start a fresh source/envelope window and seek renewed E3/BB before any exchange-facing quote retry, then rebuild gate/dry-run evidence from fresh quote, sizing, and the READY governance snapshot if freshness still holds.
