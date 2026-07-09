# AgentTodo M8 Stage 2 Fast-Track NO-GO

Date: 2026-05-07
Status: NO-GO
Window: `stage2_demo_livedemo_20260507t1602z`
Role: PM local execution

## Trigger

The operator approved using replay as a fast-track diagnostic for the active
MAG-082 Stage 2 demo/live_demo canary window.

## Evidence

- Runtime decision-spine rows remain absent: `agent.decision_objects`,
  `agent.decision_edges`, and `agent.execution_idempotency_keys` are all `0`
  both within the Stage 2 window and all-time.
- Replay coverage preflight returned `promotion_allowed=false`, tier
  `S2_PLUS_LOCAL_BBO`, verdict `development_sandbox_with_local_bbo`, and
  reason `execution_samples_below_s1_limited`.
- Full-chain replay completed for `grid_trading`, `ma_crossover`, and
  `bb_reversion` on `BTCUSDT` / `ETHUSDT` / `LABUSDT`.
- The three full-chain replay reports each processed 180 events, emitted 0
  fills, had `net_pnl=0.0`, and remained `execution_confidence=none`.
- `replay.report_artifacts` registered the three `pnl_summary` artifacts, but
  `replay.simulated_fills` inserted 0 rows.
- Replay health was `wiring_status=ready`, but passive healthcheck remained
  FAIL; `[50] replay_run_state_health` reported `completed_7d=6`,
  `failed_7d=6`, `running=0`, `failed_rate=50.0%`.

## Fix Applied During Review

Replay finalize initially failed under the API worker runtime because
`run_finalize_route.py` imported `program_code...` from a process whose working
directory is `control_api_v1`. Commit `ffd9802f` fixes the production import
path to use the local `replay` package and adds a regression test.

Verification:

- `python3 -m py_compile .../replay/run_finalize_route.py`
- `python3 -m pytest .../tests/test_replay_run_finalize.py -q` -> 10 passed
- `python3 -m pytest .../tests/test_replay_full_chain_run_routes.py .../tests/replay/test_r6_calibration_e2e.py -q` -> 20 passed, 1 skipped

No engine restart, API restart, rebuild, live authorization mutation, OpenClaw
write route, scanner authority change, executor shadow unlock, or lease-router
flag change was performed for this review.

## Verdict

Replay is useful as a fast-track diagnostic, but it cannot replace the MAG-082
runtime lineage requirement. Current Stage 2 evidence is NO-GO because no
runtime StrategistDecision -> GuardianVerdict -> ExecutionPlan -> Decision
Lease / idempotency -> ExecutionReport chain exists.

MAG-083 final release audit remains BLOCKED. MAG-084 operator sign-off remains
BLOCKED. The previous 24h evidence heartbeat for this window was paused because
this fast-track review already produced a NO-GO verdict.
