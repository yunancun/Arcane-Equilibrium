# GUI Single-Position Effective Cap Guard

## Decision

Operator correction remains binding: all risk parameters follow GUI-backed Rust
RiskConfig. GUI `P1 Risk/Trade=10.0%` is Rust `per_trade_risk_pct=0.1`, not a
fixed `10 USDT` cap. GUI `Max Single Position=25%` resolves from accepted Demo
equity into `single_position_budget_usdt`.

This checkpoint hardens the no-order review chain so `cap_usdt` cannot be
accepted unless the artifact also carries:

- `per_trade_budget_usdt`
- `single_position_budget_usdt`
- `max_order_notional_usdt`
- `resolved_cap_usdt`
- `effective_single_order_cap_usdt`

`effective_single_order_cap_usdt` must be GUI/Rust/equity derived, greater than
the stale local `10 USDT` diagnostic value, and no larger than per-trade budget,
max-single-position budget, or positive `max_order_notional_usdt`.

## Source

- Commit: `a9436c8a7a32e94ef2f1bfb38651ecd40c1a4625`
- Subject: `Harden GUI single-position cap review [skip ci]`
- Changed helpers:
  - `current_candidate_bounded_demo_admission_envelope_review.py`
  - `current_candidate_order_enablement_review.py`
  - `current_candidate_e3_bb_enablement_review_contract.py`

## Verification

- Local `py_compile`: passed
- Local focused/adjacent pytest: `37 passed`
- Local `git diff --check`: passed
- Runtime `py_compile`: passed
- Runtime focused/adjacent pytest: `37 passed`
- Runtime `git diff --check`: passed

## Runtime Evidence

- Runtime source/pins sync manifest:
  `/tmp/openclaw/runtime_source_sync_gui_single_position_cap_guard_20260627T125640Z/runtime_sync_manifest.json`
  sha `62d34b7226f3a5e5a60a2db2975d09d386a66b0777bd87a0cfdf8ed2863d4678`
- Runtime source head: `a9436c8a7a32e94ef2f1bfb38651ecd40c1a4625`
- Crontab expected-head pins: old `b753f4b0...` count `0`, new `a9436c8a...`
  count `11`, line count `70`
- No service or engine restart.

Refreshed no-order review:

- Order-enable review:
  `/tmp/openclaw/current_candidate_order_enablement_review_gui_single_position_guard_20260627T130059Z/current_candidate_order_enablement_review.json`
  sha `e034e4c46ca630afd4638255ee8ccf4f32753f7dc014d583149f9c4760446d46`
- Status: `CURRENT_CANDIDATE_ORDER_ENABLEMENT_READY_FOR_E3_BB_REVIEW_NO_ORDER`
- GUI risk fields:
  - `per_trade_risk_pct_fraction=0.1`
  - `per_trade_budget_usdt=955.1369426`
  - `position_size_max_pct=25.0`
  - `single_position_budget_usdt=2387.84235651`
  - `max_order_notional_usdt=0.0`
  - `effective_single_order_cap_usdt=955.1369426`
  - local `10 USDT` authority: `false`

Refreshed E3/BB contract:

- Contract:
  `/tmp/openclaw/current_candidate_e3_bb_enablement_contract_gui_single_position_guard_20260627T130115Z/current_candidate_e3_bb_enablement_review_contract.json`
  sha `3abfa7ccc448f971ef279faff23a65b631fa0c98c0346f0cde1a646660ba56ce`
- Status: `CURRENT_CANDIDATE_E3_BB_ENABLEMENT_REVIEW_SIGNOFF_REQUIRED_NO_ORDER`
- Loss-control blockers: `[]`
- Signoff blockers: `e3_signoff_missing`, `bb_signoff_missing`
- Order-capable action allowed: `false`

Session state:

- `/tmp/openclaw/session_loop_state_20260627T130115Z_gui_single_position_cap_guard/session_loop_state.json`
  sha `1558a9e344c4250f2fa6bcfbe0e6bf9d9f595c784f99e1ce17b552f313ea3f1b`
- State transition: `DONE_WITH_CONCERNS`

## Boundary

No order, cancel, modify, Bybit call, PG query/write, Decision Lease
acquire/release, writer/adapter enablement, service/engine restart, Cost Gate
lowering, risk expansion, live/mainnet authority, execution, fill, PnL, or
profit proof occurred.

## Next

Collect explicit `current_candidate_e3_bb_enablement_signoff_v1` artifacts for
`E3` and `BB`. After valid signoffs, rerun fresh same-window bounded Demo
authorization, active Decision Lease, Guardian/Rust authority, actual BBO, GUI
cap, book-clean, auditability, and reconstructability gates before any
order-capable Demo action.
