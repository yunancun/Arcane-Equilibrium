# PM Report: Cost-Gate Learning Running-Process Preflight

Date: 2026-06-21

## Objective

Close the gap between "runtime env file is configured" and "the running Rust engine actually loaded the demo-learning writer flag." A correct env file is not enough after a restart or source drift; the active process environment must be inspectable before we conclude the learning lane can accumulate new cost-gate rejects.

## Change

- `cost_gate_learning_lane.status` can now inspect a running engine process environment via `--engine-pid` or `--runtime-proc-environ`.
- The preflight emits a new `writer_process` block with `writer_process_status`, `writer_process_enabled`, `proc_environ_path`, and resolved plan/ledger paths from the running process.
- `--require-process-writer-enabled` adds `running_engine_writer_not_enabled` to `activation_blockers` unless the inspected process has `OPENCLAW_DEMO_LEARNING_LANE_WRITER` explicitly enabled.
- `answers` now includes `runtime_writer_process_checked`, `runtime_writer_process_enabled`, `runtime_writer_process_status`, and `running_engine_writer_disabled_or_unset_drop_risk`.

## Interpretation

This separates three states:

- env file enabled, process not checked: config intent exists, runtime proof missing
- env file enabled, process disabled/unset: restart/reload did not carry the learning writer into the active engine
- process enabled: running engine has the writer flag and should append eligible rejects, subject to source/plan/ledger/loop health

## Verification

- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` = 46 passed
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` = 34 passed
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/status.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py helper_scripts/research/alpha_discovery_throughput/runtime_runner.py` passed

## Boundary

Source/test/docs only. No runtime source sync, env edit, deploy, rebuild, restart, cron install, PG write/schema migration, Bybit private/signed/trading call, order authority, main Cost Gate lowering, credential/auth/risk/order/strategy/runtime mutation, execution proof, or promotion proof.
