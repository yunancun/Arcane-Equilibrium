# PM Report: Cost-Gate Learning Writer Config Preflight

Date: 2026-06-21

## Objective

Remove another ambiguity behind "demo has not ordered / cost-gate rejects are not accumulating": distinguish no eligible signals from a disabled or miswired demo-learning writer, and make the writer env durable across normal engine restarts.

## Change

- `cost_gate_learning_lane.status` now emits a `writer_config` block.
- The preflight can inspect an optional runtime env file with `--runtime-env-file`.
- `--require-writer-enabled` adds `runtime_writer_not_enabled` to `activation_blockers` unless `OPENCLAW_DEMO_LEARNING_LANE_WRITER` is explicitly enabled in the inspected env.
- `answers` now includes `runtime_writer_enabled`, `runtime_writer_config_status`, and `writer_disabled_or_unset_drop_risk`.
- `helper_scripts/restart_all.sh` now forwards `OPENCLAW_DEMO_LEARNING_LANE_WRITER`, `OPENCLAW_DEMO_LEARNING_LANE_PLAN`, and `OPENCLAW_DEMO_LEARNING_LANE_LEDGER` from operator env first, then `basic_system_services.env`.
- The Rust writer treats blank plan/ledger path overrides as unset, so empty restart-wrapper pass-through keeps the default `$OPENCLAW_DATA_DIR/cost_gate_learning_lane/` paths.

## Interpretation

Before this patch, a missing ledger could mean no eligible rejects, writer disabled, runtime source drift, cron not installed, or plan/path failures. v323 made plan/path failures durable once the writer sees rejects. This patch adds the preflight surface and restart pass-through needed to prove the writer is actually enabled and pointing at the expected plan/ledger paths before waiting for more market data.

## Verification

- `cargo test -p openclaw_engine demo_learning_lane --lib` from `srv/rust` = 22 passed
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` = 42 passed
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` = 34 passed
- `python3 -m pytest tests/structure/test_restart_all_keep_auth_preflight_static.py -q` = 6 passed
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/status.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py helper_scripts/research/alpha_discovery_throughput/runtime_runner.py` passed
- `bash -n helper_scripts/restart_all.sh` passed
- `rustfmt --edition 2021 --check openclaw_engine/src/demo_learning_lane_writer.rs` passed

## Boundary

Source/test/docs only. No runtime env edit, source sync, deploy, rebuild, restart, cron install, PG write/schema migration, Bybit private/signed/trading call, order authority, main Cost Gate lowering, credential/auth/risk/order/strategy/runtime mutation, execution proof, or promotion proof.
