# P1 Healthcheck FAIL Queue And Executor Fake-Live Fix

Date: 2026-05-07
Owner: PM-local implementation checkpoint
Status: source fixed, runtime deploy pending

## Scope

Operator requested inserting current healthcheck FAILs ahead of P1 Important
work, then continuing P1 closure.

## Healthcheck Queue

Linux passive healthcheck at `2026-05-07T17:09:05Z` returned `SUMMARY: FAIL`.
The following items now sit ahead of normal P1 work:

- `[Xb] pipeline_triangulation`: severe fills/labels/intents divergence.
- `[42]` / `[42b]` / `[42c]`: LG-5 reviewer and attribution chain still failing.
- `[50] replay_run_state_health`: failed rate too high plus running rows.
- `[51] scanner_opportunity_shadow_acceptance`: positive opportunity bucket is net-negative.

TODO now records these under `P1-FAIL`, and MAG-083/MAG-084 remain blocked
while these FAILs are unresolved.

## Source Fix

Closed the source side of `P1-FAKE-1`:

- `ExecutorAgent` now routes real IPC through Rust's actual
  `submit_paper_order` method instead of the stale `submit_order` name.
- The IPC payload now carries explicit `engine` so demo/live/live_demo routes
  do not silently fall back to the primary or paper pipeline.
- `ExecutorConfigCache.shadow_mode_provider()` now accepts an optional engine
  argument and maps `live_demo` to Rust's `live` channel/config label.
- Execution reports now include `metadata.execution_engine`.

## Verification

Mac:

```text
python3 -m py_compile app/executor_agent.py app/executor_config_cache.py
python3 -m pytest test_executor_config_cache.py test_executor_shadow_to_live_e2e.py test_executor_decision_parity.py -q
25 passed, 7 skipped
```

Linux `trade-core` after fast-forward to `f5bfd854`:

```text
python3 -m py_compile app/executor_agent.py app/executor_config_cache.py
python3 -m pytest test_executor_config_cache.py test_executor_shadow_to_live_e2e.py test_executor_decision_parity.py -q
30 passed, 2 skipped
```

## Boundary

No runtime deploy/restart, no live auth mutation, no risk/strategy config
change, no Decision Lease flag flip, and no OpenClaw write/proposal surface.

## Next

Pull this source checkpoint on Linux, run the same targeted tests, then deploy
only if operator wants this P1-FAKE-1 runtime fix loaded into the active API.
