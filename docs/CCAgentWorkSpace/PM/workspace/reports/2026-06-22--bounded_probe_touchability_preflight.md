# Bounded Probe Touchability Preflight

Date: 2026-06-22
Source commit: `029576af`

## Summary

v415 converts the v414 Demo no-fill diagnosis into a reusable, fail-closed preflight gate before any bounded Demo probe review.

Added `bounded_demo_probe_touchability_preflight_v1`, which consumes:

- `sealed_horizon_bounded_demo_probe_preflight_v1`
- `demo_order_to_fill_gap_audit_v1`

It does not lower Cost Gate, grant probe/order authority, call Bybit, query/write PG, or mutate runtime state.

## Engineering Change

- Added `helper_scripts/research/cost_gate_learning_lane/bounded_probe_touchability_preflight.py`.
- Added focused tests in `helper_scripts/research/tests/test_cost_gate_bounded_probe_touchability_preflight.py`.
- Wired `helper_scripts/cron/cost_gate_learning_lane_cron.sh` to refresh `bounded_probe_touchability_preflight_latest.{json,md}` before bounded result/execution-realism reviews.
- Added cron status fields for touchability preflight rc/status/reason, order audit status, reviewed order count, deep no-touch count, max best-touch gap, and repair-required flag.

## Runtime Smoke

Artifact-only Linux smoke:

- JSON: `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_touchability_preflight_smoke.json`
- Markdown: `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_touchability_preflight_smoke.md`
- JSON sha256: `81a6c2feb0195db242f8232c994a06d62e3f1142bd6b4a5623b1e5c8e9b25663`
- Markdown sha256: `630cdd46c33ad1aadb8ffd74397c640367d90258f2514e8aef7245af76f144e4`

Result:

- status: `TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE`
- candidate: `ma_crossover|BTCUSDT|Sell`
- order audit status: `PASSIVE_LIMITS_TOO_DEEP_NO_TOUCH`
- reviewed orders: `6`
- fill rows: `0`
- deep passive no-touch orders: `6`
- max best-touch gap: `1530.6074bp`
- min best-touch gap: `1156.7403bp`
- required max initial passive gap: `75bp`

Separate missing-audit smoke produced `ORDER_TOUCHABILITY_AUDIT_REQUIRED`, proving the interface fails closed instead of silently dropping the gate.

## PM Read

The current path to profitability is not global Cost Gate lowering. The system needs a bounded Demo placement design that creates learnable execution evidence:

- fresh BBO before any probe order,
- near-touch or skip-and-record if the passive gap is too wide,
- order-to-fill gap audit after the probe,
- fill/fee/slippage lineage after any fill,
- matched blocked-signal controls before any Cost Gate review.

Current runtime sample says the existing Demo orders are too deep to teach the system about alpha capture or fill quality.

## Verification

- Mac research related suite: `21 passed`.
- Mac db/cron related suite: `21 passed`.
- Mac py_compile, bash syntax, and `git diff --check` passed.
- Linux research related suite: `21 passed`.
- Linux db/cron related suite: `21 passed`.
- Linux py_compile passed.
- Linux source fast-forwarded clean to `029576af`.
- No CI run.

## Boundary

Source/test/docs + Linux source sync + `/tmp/openclaw` artifact-only smoke only. No PG write/schema migration, no Bybit private/signed/trading call, no deploy/rebuild/restart, no crontab install/env/auth/risk/order/strategy mutation, no Cost Gate lowering, no probe/order authority, and no promotion proof.
