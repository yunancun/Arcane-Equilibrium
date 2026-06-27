# Bounded Demo Probe Capture Normalization And Lease Blocker

## Status

`BLOCKED_BY_RUNTIME`: the Demo-only soak now captures current Cost Gate rejects into the admission ledger, including the selected `grid_trading|AVAXUSDT|Sell` candidate, but active bounded order submission remains blocked because the runner has no final-window Decision Lease / active order request.

## Source Change

- Commit `5aa5fff0b90239d2fee5ca36fff377f833b0fd3c` updates `normalize_reject_reason_code()` so the hot-path adapter recognizes the runtime `cost_gate(JS-demo): estimated=-...bps < 0` negative-edge format.
- Regression coverage now includes the actual `estimated=-... < 0` formatter shape and confirms positive threshold rejects are not normalized into `DEMO_ELIGIBLE_PARTIAL`.

Verification:

- Local: `cargo test -p openclaw_engine demo_learning_lane -- --nocapture` passed 27 targeted tests.
- Local: `cargo test -p openclaw_engine demo_learning_lane_hot_path -- --nocapture` passed 5 targeted tests.
- Runtime: both targeted suites passed on `trade-core`.
- `git diff --check` passed before commit.

## Runtime Deployment

- Runtime source fast-forwarded to `5aa5fff0b90239d2fee5ca36fff377f833b0fd3c`.
- Release rebuild/restart verified new engine PID `4164391`.
- `/proc/4164391/exe` sha matches disk sha `fef422953a221c1d81bf434864ba45968454530238455d90db52bd1eb29ceae0`.
- Demo-only env remains set: `OPENCLAW_ALLOW_MAINNET=0`, `OPENCLAW_ENABLE_PAPER=0`, `OPENCLAW_DEMO_LEARNING_LANE_WRITER=1`, `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=1`.

## Runtime Evidence

- Admission ledger increased from `99196` to `99235` lines after deploy.
- Non-selected rows correctly emit `SIDE_CELL_NOT_SELECTED` with `allowed_to_submit_order=false`.
- Selected rows for `grid_trading|AVAXUSDT|Sell` now appear, proving candidate capture is fixed:
  - `ctx-demo-AVAXUSDT-1782595724549`
  - `ctx-demo-AVAXUSDT-1782595754609`
- Both selected rows are `ADAPTER_DISABLED`, reason `runtime_adapter_enable_flag_is_false`, with `allowed_to_submit_order=false`.

Interpretation: the env flag is enabled, but the writer's effective adapter gate also requires `active_order_request.is_some()` and dispatch channel availability. For these selected rejects, `active_order_request` is absent because the final-window bounded probe runner is not yet acquiring/providing a Decision Lease for the active order request. This is the next blocker; do not solve it with a fake lease id or by bypassing Governance.

## Boundaries

Demo only. No live/mainnet, no global Cost Gate lowering, no Guardian/risk/Decision Lease/Rust authority bypass, no fake lease id, no order/fill/profit proof. The next source/runtime work is a candidate-scoped final-window Decision Lease acquisition path inside the bounded Demo runner that produces a real active order request before admission.
