# Operator Note: Bounded Probe Near-Touch Adapter Module

- New Rust Module: `openclaw_engine::bounded_probe_near_touch`.
- Source commit: `0cc749db`.
- Runtime latest: `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_authority_patch_readiness_latest.{json,md}`.
- Current status: `RUST_PATCH_REQUIRED_AUTHORITY_PATH_WIRING_MISSING`.

This does not authorize any order, probe, Cost Gate lowering, deploy, restart, cron install, or runtime mutation.

What changed:

- `post_only_near_touch_or_skip` placement math exists and is unit-tested.
- Fresh/stale/future BBO and initial passive-gap guards fail closed.
- Invalid/crossed/non-positive price cases fail closed.
- Submit decisions carry `bounded_probe_attempt` + `side_cell_key` lineage.
- Skip decisions carry `bounded_probe_touchability_block` evidence.
- The readiness scanner now requires separate tick-dispatch wiring before any operator can treat the source as patch-ready.

Next operator-reviewable engineering step: explicitly wire this Adapter into the bounded Demo authority path before any future probe order submission, then collect candidate-matched fill/fee/slippage and matched-control evidence before considering any Cost Gate change.
