# 2026-06-29 Learning Stack Health SSOT Source Checkpoint

PM SIGN-OFF: **DONE_WITH_CONCERNS / SOURCE CHECKPOINT COMPLETE, RUNTIME MUTATION BLOCKED**.

Scope: first implementation checkpoint from `P0-LEARN-HEALTH-SSOT` in the 2026-06-29 learning-engine completion plan.

## Dispatch

- PM boot/read requirements completed.
- Planning/quant architecture basis: 2026-06-29 PM report plus QC/MIT/AI-E/PA review.
- Implementation chain was local and source-only: `PM -> PA/QC/MIT/AI-E context -> E1-style implementation -> E2-style boundary review -> E4-style regression -> PM`.
- E3/BB skipped because no runtime install, cron mutation, service restart, Bybit path, order path, or effect-capable mutation was performed.

## Change

Source commit: `f2a827c2` (`Add learning stack health snapshot`), pushed to `origin/main`.

Added `helper_scripts/cron/learning_stack_health_snapshot.py`:

- emits `learning_stack_health_snapshot_v1`;
- aggregates source/git cleanliness, unique scheduler shape, demo-learning stack health, ML training maintenance status/history, model registry summary, ONNX/registry freshness, probe ledger freshness, artifact/PG parity summary, and fill-backed proof summary;
- fail-closes to `LEARNING_STACK_DEGRADED` on empty/duplicate scheduler, stale/missing demo health, ML maintenance error, stale registry, ONNX newer than registry, stale/missing ledger, missing artifact/PG parity, or missing fill-backed proof;
- returns `LEARNING_STACK_READY_FOR_SOURCE_ONLY_REVIEW` only when all supplied gates are fresh and coherent;
- keeps `mutation_enabled=false`, `demo_mutation_authority_granted=false`, `order_authority_granted=false`, `live_authority_granted=false`, `cost_gate_lowering_allowed=false`, `bybit_call_performed=false`, and `pg_write_performed=false`.

Added focused tests in `helper_scripts/cron/tests/test_learning_stack_health_snapshot.py` covering:

- empty crontab + missing inputs degrade and disable mutation;
- fully supplied ready fixture is ready but still grants no authority;
- ML maintenance error blocks readiness;
- ONNX artifact newer than registry fails closed;
- duplicate scheduler entries fail unique scheduler authority;
- `--json-output` and `--fail-on-degraded` contract;
- static negative scan for effect-capable IO strings.

Updated `helper_scripts/SCRIPT_INDEX.md`.

## Verification

- `python3 -m py_compile helper_scripts/cron/learning_stack_health_snapshot.py helper_scripts/cron/tests/test_learning_stack_health_snapshot.py`
- `python3 -m pytest helper_scripts/cron/tests/test_learning_stack_health_snapshot.py -q` -> `7 passed`
- `python3 -m pytest helper_scripts/cron/tests/test_learning_stack_health_snapshot.py helper_scripts/cron/tests/test_demo_learning_stack_healthcheck.py -q` -> `19 passed`
- `git diff --check` -> PASS
- Local degraded smoke with empty crontab returned `LEARNING_STACK_DEGRADED`, `mutation_enabled=false`, `order_authority_granted=false`, `bybit_call_performed=false`.

## Boundaries

No runtime source sync, no Linux execution, no crontab edit, no service restart, no PG write/migration, no Bybit call, no Decision Lease acquire/release, no writer/adapter enablement, no Cost Gate lowering, no demo mutation authority, no order authority, no live/mainnet authority, and no profit/promotion proof.

## Next

Move the ML completion loop to `P0-LEARN-LEDGER-EVENT-CONTRACT`: wrap the current JSONL/artifact lane into hashed, versioned `LearningEvent` packets with proof tier, source refs, candidate identity, `blocked_markout_proxy` classification, malformed-event quarantine, and a dual-write/diff plan for future PG-first cutover.

Do not start runtime installation, scheduler repair, Demo mutation, model serving promotion, or proof/promotion work until the earlier source contracts and hardening gates pass.
