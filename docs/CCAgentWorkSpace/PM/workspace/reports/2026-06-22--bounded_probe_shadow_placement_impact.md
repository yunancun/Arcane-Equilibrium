# Bounded Probe Shadow Placement Impact

Date: 2026-06-22
Source commit: `ff66aa25`

## Summary

v417 adds a no-authority shadow replay for the v416 near-touch-or-skip repair plan.

The new `bounded_demo_probe_shadow_placement_impact_v1` consumes:

- `bounded_demo_probe_placement_repair_plan_v1`
- `demo_order_to_fill_gap_audit_v1`

It applies the proposed near-touch formula to already-observed Demo orders and measures whether the repair would have reduced the passive gap enough to create touchable learning attempts.

It does not lower Cost Gate, grant probe/order authority, call Bybit, query/write PG, mutate runtime state, or create promotion proof.

## Engineering Change

- Added `helper_scripts/research/cost_gate_learning_lane/bounded_probe_shadow_placement_impact.py`.
- Added focused tests in `helper_scripts/research/tests/test_cost_gate_bounded_probe_shadow_placement_impact.py`.
- Wired `helper_scripts/cron/cost_gate_learning_lane_cron.sh` to refresh `bounded_probe_shadow_placement_impact_latest.{json,md}` after placement repair plan and before bounded result/execution-realism reviews.
- Added cron status fields for shadow status/reason/sample scope, submit/skip counts, candidate-matched count, max shadow gap, and max gap reduction.

## Runtime Smoke

Artifact-only Linux smoke:

- JSON: `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_shadow_placement_impact_smoke.json`
- Markdown: `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_shadow_placement_impact_smoke.md`
- JSON sha256: `28f2029119f4d2f4cace9f86fd5c2f502a4afb5af8762ad04017b64a176c735b`
- Markdown sha256: `2c13a66c77d8bfeae1798da33a0fbdd126c4c8fce6677d6b668be374a38b5bd4`

Result:

- status: `SHADOW_PLACEMENT_TOUCHABILITY_IMPROVED_SAMPLE_MISMATCH`
- candidate: `ma_crossover|BTCUSDT|Sell`
- sample scope: `current_demo_order_flow_not_candidate_matched`
- reviewed orders: `6`
- shadow submit count: `6`
- shadow skip count: `0`
- candidate-matched order count: `0`
- max original best-touch gap: `1530.6074bp`
- max shadow initial touch gap: `58.2092bp`
- avg shadow initial touch gap: `17.0489bp`
- max gap reduction: `1522.1026bp`
- future BBO would cross repaired shadow limit: `4/6`

## PM Read

This proves the proposed placement repair is mechanically meaningful: on the current no-fill Demo sample, near-touch post-only placement would reduce the initial passive gap from roughly `1156-1531bp` to `3.48-58.21bp`, under the `75bp` cap, for all six reviewed orders.

It is not alpha proof and not candidate proof. The six current orders are `flash_dip_buy` Buy orders on BNB/XRP/ETC/SUI, while the sealed Cost Gate candidate remains `ma_crossover|BTCUSDT|Sell`. The artifact explicitly marks `candidate_matched_runtime_sample_present=false`.

The next engineering step remains operator-gated: patch the existing Rust bounded Demo authority path only after review, then collect candidate-matched order-to-fill, fill/fee/slippage, matched blocked-control, result-review, and execution-realism evidence before any Cost Gate change.

## Verification

- Mac shadow placement focused suite: `6 passed`.
- Mac related bounded-probe suite: `32 passed`.
- Mac cron static suite: `13 passed`.
- Mac py_compile, bash syntax, and `git diff --check` passed.
- Linux related bounded-probe suite: `32 passed`.
- Linux cron static suite: `13 passed`.
- Linux py_compile and bash syntax passed.
- Linux source fast-forwarded clean to `ff66aa25`.
- No CI run.

## Boundary

Source/test/docs + Linux source sync + `/tmp/openclaw` artifact-only smoke only. No PG write/schema migration, no Bybit private/signed/trading call, no deploy/rebuild/restart, no crontab install/env/auth/risk/order/strategy mutation, no Cost Gate lowering, no probe/order authority, and no promotion proof.
