# P1 Healthcheck FAIL Queue And Executor Fake-Live Fix

Date: 2026-05-07
Owner: PM-local implementation checkpoint
Status: P1 healthcheck FAIL queue cleared to PASS/WARN; Executor source fixed

## Scope

Operator requested inserting current healthcheck FAILs ahead of P1 Important
work, then continuing P1 closure. This checkpoint covers the fail queue,
source fixes, Linux runtime validation, and the updated P1 ordering.

## Healthcheck Queue

Linux passive healthcheck at `2026-05-07T17:09:05Z` returned `SUMMARY: FAIL`.
These items were inserted ahead of normal P1 work:

- `[Xb] pipeline_triangulation`: severe fills/labels/intents divergence.
- `[42]` / `[42b]` / `[42c]`: LG-5 reviewer and attribution chain still failing.
- `[50] replay_run_state_health`: failed rate too high plus running rows.
- `[51] scanner_opportunity_shadow_acceptance`: positive opportunity bucket is net-negative.

TODO records these under `P1-FAIL`.

Linux passive healthcheck at `2026-05-07T17:51:38Z` returned `SUMMARY: WARN`.
Inserted FAIL blockers are now resolved as follows:

- `[Xb]`: PASS / not emitted. RCA was a denominator bug: raw demo intents were
  dominated by scanner opportunity shadow observations, while fills/labels are
  closed-trade anchors. Commit `4f437ea1` scopes the intent anchor to
  close-fill-linked contexts and keeps raw scanner volume as diagnostics.
- `[42]`: cleared after LG5 consumer scheduler stopped starving old unaudited
  candidates (`c8240b6a`) and API-only reload loaded the scheduler change.
- `[42b]` / `[42c]`: WARN only after settled-sample denominator alignment
  (`4654964d`); eligible strategies have attribution ratio `1.000`, while
  low settled sample strategies remain sample-maturity warnings.
- `[50]`: WARN only after superseded historical replay failures are downgraded
  (`898f4a90`); 5 newer completed runs supersede newest failure.
- `[51]`: WARN only after scanner exploration and calibrated
  `opportunity_positive` buckets were separated (`84f63706`);
  `opportunity_positive_n=0`, so scanner opportunity stays shadow-only.

MAG-083/MAG-084 remain blocked, but now by the separate MAG-082 runtime lineage
NO-GO, not by these P1-FAIL healthcheck blockers.

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

P1 healthcheck queue targeted regression, Mac:

```text
venvs/mac_dev/bin/python -m py_compile ...
venvs/mac_dev/bin/python -m pytest \
  helper_scripts/db/test_pipeline_triangulation_healthcheck.py \
  helper_scripts/db/test_lg5_healthchecks.py \
  helper_scripts/db/test_replay_maintenance_healthchecks.py \
  helper_scripts/db/test_scanner_opportunity_healthcheck.py \
  program_code/ml_training/tests/test_mlde_demo_applier.py
96 passed
```

P1 healthcheck queue targeted regression, Linux `trade-core` at `4f437ea1`:

```text
python3 -m py_compile ...
python3 -m pytest \
  helper_scripts/db/test_pipeline_triangulation_healthcheck.py \
  helper_scripts/db/test_lg5_healthchecks.py \
  helper_scripts/db/test_replay_maintenance_healthchecks.py \
  helper_scripts/db/test_scanner_opportunity_healthcheck.py \
  program_code/ml_training/tests/test_mlde_demo_applier.py
96 passed
```

Runtime healthcheck:

```text
Passive-wait healthcheck @ 2026-05-07T17:51:38+00:00 UTC
SUMMARY: WARN
```

`[Xb]` and `[42]` were not emitted. `[42b]`, `[42c]`, `[50]`, and `[51]`
were WARN with the causes listed above.

## Boundary

No engine rebuild, no live auth mutation, no risk/strategy config change, no
Decision Lease flag flip, and no OpenClaw write/proposal surface. API-only
reloads were used to load Python-side scheduler/producer/executor source.

## Next P1 Order

1. Finish `P1-FAKE-1` with an explicit fake-live runtime smoke if operator
   wants to close it beyond source/API-load status.
2. Work the remaining WARN cluster: `[14]`, `[37]`, `[40]`, `[45]`, low
   settled samples in `[42b/c]`, and scanner `[51]` shadow-only evidence.
3. Resume `P1-OPENCLAW-3` brief/latest, diagnostics, and escalations.
4. Only after that, consider `P1-OPENCLAW-6/7` proposal relay and mobile lane.
