# PM Report: Cost-Gate Learning Engine PID Auto-Detect Preflight

Date: 2026-06-21

## Objective

Reduce operator error in the running-process writer check. The previous preflight could inspect `/proc/<pid>/environ`, but the operator still had to supply the correct engine PID. A loose `pgrep -af openclaw-engine` can match the shell command itself, so the preflight should discover the engine process without that false-positive path.

## Change

- `cost_gate_learning_lane.status` now supports `--auto-detect-engine-pid`.
- When `--require-process-writer-enabled` is used without `--engine-pid` or `--runtime-proc-environ`, auto-detection is enabled automatically.
- Detection scans `/proc/*/cmdline` and only accepts processes whose argv[0] basename is exactly `openclaw-engine`.
- The `writer_process` block now includes detection status, detected PID, candidate count, and recent candidates.
- If process detection cannot run or finds no engine, `writer_process_status` becomes `ENGINE_PROCESS_DETECTION_UNAVAILABLE` or `ENGINE_PROCESS_NOT_FOUND`, not a vague `NOT_CHECKED`.

## Interpretation

This makes the activation preflight harder to misuse:

- no PID supplied + active process exists: preflight can inspect it
- no PID supplied + no process: activation is blocked as unproven
- shell/pgrep command mentions `openclaw-engine`: ignored unless argv[0] is the engine binary

## Verification

- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` = 49 passed
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` = 34 passed
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/status.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py helper_scripts/research/alpha_discovery_throughput/runtime_runner.py` passed

## Boundary

Source/test/docs only. No runtime source sync, env edit, deploy, rebuild, restart, cron install, PG write/schema migration, Bybit private/signed/trading call, order authority, main Cost Gate lowering, credential/auth/risk/order/strategy/runtime mutation, execution proof, or promotion proof.
