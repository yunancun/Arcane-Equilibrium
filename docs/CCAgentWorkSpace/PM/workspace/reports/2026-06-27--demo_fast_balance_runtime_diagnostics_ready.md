# Demo Fast-Balance Runtime Diagnostics Ready

Generated: 2026-06-27T09:21:00Z

## State Transition

`DONE_WITH_CONCERNS`

## What Changed

`helper_scripts/research/cost_gate_learning_lane/demo_fast_balance_equity_artifact.py` now supports optional runtime diagnostics alongside the existing supplied/captured fast-balance payload.

The diagnostics can record:

- runtime data-dir snapshot metadata for `pipeline_snapshot_demo.json`, `pipeline_snapshot.json`, and `pipeline_snapshot_paper.json`
- Demo snapshot `paper_state` balance presence
- Bybit Demo secret-slot metadata by path/name/mode only
- runtime diagnostic blockers such as missing/stale Demo snapshot or missing active Demo secret slot

Secret contents are not read or emitted.

## Runtime Evidence

Fresh `trade-core` read-only diagnosis produced:

- artifact: `/tmp/openclaw/demo_fast_balance_runtime_diagnosis_20260627T091742Z/demo_account_equity_artifact_runtime_diagnosed.json`
- sha256: `67ea82032fc33545322745f8bd6102023d89fc79168caad085503367bbcb6d86`
- status: `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY`
- `read_model=rust_snapshot_fast`
- `pipeline_status=connected`
- equity: `9551.36942603`
- runtime blockers: `[]`
- `secret_values_read=false`

This supersedes the previous `disconnected` artifact as current evidence. The old artifact remains historical blocker evidence only.

## GUI Risk Semantics

The operator GUI remains the source of truth:

- GUI `P1 Risk/Trade=10.0%` means `per_trade_risk_pct=0.1`, not fixed `10 USDT`.
- GUI `Max Single Position=25%` means `position_size_max_pct=25.0`, not fixed `25 USDT`.
- With fresh equity `9551.36942603`, P1 10% resolves to `955.1369426 USDT`.
- With fresh equity `9551.36942603`, max-single-position 25% resolves to `2387.84235651 USDT`.

## Verification

- Focused artifact suite: `11 passed in 0.06s`
- Adjacent GUI-cap/envelope/artifact suite: `32 passed in 0.07s`
- `python3 -m py_compile`: passed
- `git diff --check`: passed

## Remaining Concern

Runtime source on `trade-core` is still `9d9c575b2bfbe0cfab24ec001b866c90c016059c`, while local/origin source contains newer GUI cap lineage hardening and this diagnostics change. Do not open another actual-admission BBO Decision Lease window until runtime source sync is reviewed and a fresh same-window no-order envelope/BBO/admission chain is regenerated.

No order, Bybit private/order call, public quote capture, PG write, runtime mutation, service restart, Cost Gate change, risk expansion, live/mainnet authority, execution, or profit proof occurred.

Session state: `/tmp/openclaw/session_loop_state_20260627T092100Z_demo_fast_balance_runtime_diagnosed/session_loop_state.json` sha `390e7459dcf6c625092e89fd35484f38f30f16a95e0a485e242487e28d3d1bde`.
