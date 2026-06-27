# GUI Percent Cap Semantics Guard

1. `blocker_id`: `P0-GUI-RISK-CAP-RESOLVER-CURRENT-CANDIDATE-DRIFT-RECONCILE`
2. `state_transition`: `DONE_WITH_CONCERNS`
3. `operator_correction`: GUI/Rust RiskConfig is authoritative for all risk parameters. GUI `P1 Risk/Trade=10.0%` means Rust `per_trade_risk_pct=0.1`, not a fixed `10 USDT` order cap. GUI `Max Single Position=25%` means `position_size_max_pct=25.0`.
4. `source_change`: `e4fb5c7f4087d55ed1a8330174234bdb3f00aa3e` (`Guard GUI percent cap semantics`)
5. `runtime_sync`: `trade-core` fast-forwarded `efa92a88 -> e4fb5c7f`; crontab expected-head pins `efa92a88=11 -> 0`, `e4fb5c7f=0 -> 11`, line count `70`; no service restart.
6. `runtime_sync_manifest`: `/tmp/openclaw/runtime_source_sync_gui_percent_cap_guard_20260627T0723Z/runtime_sync_manifest.json`
7. `runtime_sync_manifest_sha256`: `a6af92acbc6af17e365b3752a6f1abd1ce472332a041812d5b11d0b34b3224e7`
8. `session_state`: `/tmp/openclaw/session_loop_state_20260627T0728Z_gui_percent_cap_semantics_guard.json`
9. `session_state_sha256`: `5b1612164c48afa37a31d3d133335b296ebb053935ea511612e285e08e623225`

## Result

The staircase worksheet now emits machine-checkable cap semantics:

- `risk_source_of_truth=GUI-backed Rust RiskConfig`
- `gui_percent_semantics`: GUI `10.0%` is TOML/Rust `0.1`, not `10 USDT`
- `bounded_probe_local_cap_usdt_is_authority=false`
- `local_10_usdt_cap_is_global_risk_authority=false`

The new regression locks the current Demo values:

- account equity: `9552.43426257`
- GUI per-trade cap: `955.24342626 USDT`
- GUI max-single-position budget: `2388.10856564 USDT`
- legacy source construction cap input: `10.0`
- resolved GUI cap: `955.24342626`

Local source-only worksheet:

- path: `/tmp/openclaw/gui_risk_cap_percent_semantics_guard_20260627T071928Z_source_only_legacy_10_input/current_cap_staircase_risk_worksheet.json`
- sha256: `9148c16de63bef3846d38d2dcff9d7fcf914a409311c6f6e3b75a345d68b4962`
- status: `CURRENT_CAP_STAIRCASE_RISK_WORKSHEET_READY_NO_AUTHORITY`

Runtime worksheet:

- path: `/tmp/openclaw/gui_risk_cap_percent_semantics_guard_20260627T0725Z_runtime_source_only_legacy_10_input/current_cap_staircase_risk_worksheet.json`
- sha256: `32530c078db63699bc6b50dfba4f0b84240e143c73474452d0036f6963715c57`
- status: `CONTROL_IDENTITY_CONTRACT_INPUT_NOT_READY`
- note: cap fields still prove the GUI percent semantics; the old runtime control-contract input is not READY, so this artifact is not admission evidence.

## Verification

- local: `py_compile` passed
- local: `git diff --check` passed
- local: GUI-cap/admission/sizing/active-window focused suite `41 passed`
- runtime: Python `3.12.3`, `tomllib` available
- runtime: same focused suite `41 passed`

## Boundary

No order, cancel, modify, Bybit private/order call, PG write, service restart, Cost Gate lowering, risk expansion, Decision Lease acquire/release, writer/adapter enablement, live/mainnet authority, execution, or profit proof occurred.

Runtime admission remains blocked by Guardian `CAUTIOUS` / reconciler drift. Next work should diagnose or wait for Guardian recovery, then reacquire a fresh active current-candidate Demo Decision Lease and rerun gate evidence inside the final actual-admission BBO window.
