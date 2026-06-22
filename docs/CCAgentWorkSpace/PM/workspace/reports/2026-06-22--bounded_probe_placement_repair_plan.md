# Bounded Probe Placement Repair Plan

Date: 2026-06-22
Source commit: `88d7713d`

## Summary

v416 converts the v415 touchability failure into an operator-reviewable placement repair plan.

The new `bounded_demo_probe_placement_repair_plan_v1` consumes `bounded_demo_probe_touchability_preflight_v1` and emits a no-authority near-touch-or-skip plan for bounded Demo probes.

It does not lower Cost Gate, grant probe/order authority, call Bybit, query/write PG, mutate runtime state, or create promotion proof.

## Engineering Change

- Added `helper_scripts/research/cost_gate_learning_lane/bounded_probe_placement_repair_plan.py`.
- Added focused tests in `helper_scripts/research/tests/test_cost_gate_bounded_probe_placement_repair_plan.py`.
- Wired `helper_scripts/cron/cost_gate_learning_lane_cron.sh` to refresh `bounded_probe_placement_repair_plan_latest.{json,md}` after touchability preflight and before bounded result/execution-realism reviews.
- Added cron status fields for placement repair rc/status/reason, order mode, review-ready flag, max fresh BBO age, and max initial passive gap.

## Runtime Smoke

Artifact-only Linux smoke:

- JSON: `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_placement_repair_plan_smoke.json`
- Markdown: `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_placement_repair_plan_smoke.md`
- JSON sha256: `73900d209b079b16be1c12682c698f7a487e869e3317c0f0584a3745a8cf6cb7`
- Markdown sha256: `1e0ad2403df82b17753050d448edc0ca54ccc41888482545f02bce5890c39829`

Result:

- status: `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW`
- candidate: `ma_crossover|BTCUSDT|Sell`
- source touchability status: `TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE`
- order-touchability baseline: `PASSIVE_LIMITS_TOO_DEEP_NO_TOUCH`
- reviewed orders: `6`
- fill rows: `0`
- deep passive no-touch orders: `6`
- max best-touch gap: `1530.6074bp`
- required max initial passive gap: `75bp`
- order mode: `post_only_near_touch_or_skip`
- max fresh BBO age: `1000ms`
- active: `false`
- requires separate operator authorization: `true`

Separate missing-preflight smoke produced `TOUCHABILITY_PREFLIGHT_REQUIRED`, proving the interface fails closed when the upstream gate is absent.

## PM Read

The system has enough evidence to say the current Demo path is not learning from fills: current orders sit about `1156-1531bp` from touch while the bounded probe design needs initial passive gap <= `75bp`.

The profitable path is not to globally lower Cost Gate. The next source change, after operator authorization, should patch the existing Rust authority path for bounded Demo probes only:

- require a fresh BBO snapshot before any probe order;
- compute a maker-side near-touch post-only limit;
- for Sell, use `max(best_ask, best_bid + tick_size)`;
- for Buy, use `min(best_bid, best_ask - tick_size)`;
- skip and record `bounded_probe_touchability_block` when touch gap exceeds `75bp`;
- after any repaired probe, immediately refresh order-to-fill, fill/fee/slippage lineage, matched blocked-signal controls, and execution-realism review.

This is the narrow way to cross the Cost Gate: create fill-backed edge-capture evidence, compare it to blocked controls, then let execution-realism repair explain any alpha capture gap. Broader alpha work should continue in parallel, but this artifact gives the Cost Gate lane a concrete next engineering step.

## Verification

- Mac placement repair focused suite: `5 passed`.
- Mac related Cost Gate bounded-probe suite: `26 passed`.
- Mac cron static suite: `13 passed`.
- Mac py_compile, bash syntax, and `git diff --check` passed.
- Linux related Cost Gate bounded-probe suite: `26 passed`.
- Linux cron static suite: `13 passed`.
- Linux py_compile passed.
- Linux source fast-forwarded clean to `88d7713d`.
- No CI run.

## Boundary

Source/test/docs + Linux source sync + `/tmp/openclaw` artifact-only smoke only. No PG write/schema migration, no Bybit private/signed/trading call, no deploy/rebuild/restart, no crontab install/env/auth/risk/order/strategy mutation, no Cost Gate lowering, no probe/order authority, and no promotion proof.
