# 2026-07-07 Demo-Only Engine Env Restoration E3 Review

Role: `E3(explorer)` read-only security/runtime authorization review.

Status: `DONE`

Verdict: `APPROVE_FOR_BB_REVIEW`

Reviewed request:

- Path: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--demo_only_engine_env_restoration_request.json`
- SHA-256: `4d5ec4252bd00062cc3a804465c3fced49a443a7ff7de18190af2fc66fc14a2b`

## Facts

- Mac `HEAD`, local `origin/main`, GitHub `main`, Linux `HEAD`, and Linux
  `origin/main` all equal
  `e655de92673e4960ceca1888a07a4843ac4ddb3e`.
- Linux worktree is clean. Mac worktree is dirty, but the request does not
  consume Mac dirty state as runtime source.
- Runtime engine PID `3771096` is running.
- Persisted env and process env show `OPENCLAW_ALLOW_MAINNET=0`,
  `OPENCLAW_ENABLE_PAPER=0`, `OPENCLAW_DEMO_LEARNING_LANE_WRITER=1`,
  `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=0`, and the expected Demo learning
  lane plan path.
- Prior runtime/loss-control state remains blocked for Demo testing or
  materialization. Its documented next safe action is a separate Demo-only env
  restoration decision.
- `restart_all.sh --engine-only --keep-auth` does not rebuild unless
  `--rebuild` is passed, and the `--engine-only` branch does not restart API.

## Judgment

Fact: the latest runtime/loss-control packet still blocks Demo testing,
order/probe, guardrail/materialization, and any `RUNTIME_LOSS_CONTROL_READY`
claim.

Inference: that blocker does not prevent sending this exact env-restoration
request to BB because the request only addresses the non-expiry engine-env
blocker and explicitly denies paper/live/mainnet, Cost Gate changes, direct
exchange reads, DB writes, order/probe, proof, and promotion.

## Conditions

- Edit only
  `/home/ncyu/BybitOpenClaw/secrets/environment_files/basic_system_services.env`
  line `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=0 -> 1`.
- Preserve `OPENCLAW_ALLOW_MAINNET=0`, `OPENCLAW_ENABLE_PAPER=0`,
  `OPENCLAW_DEMO_LEARNING_LANE_WRITER=1`, and the same plan path.
- Run only
  `cd /home/ncyu/BybitOpenClaw/srv && bash helper_scripts/restart_all.sh --engine-only --keep-auth`;
  no rebuild and no API restart.
- Do not print or manually inspect secret values.
- Re-check only allowlisted env keys after restart and stop on any scope drift.
- BB approval of this packet must not be interpreted as order/probe authority
  or loss-control readiness.

## Boundary

No file edit, runtime mutation, DB read/write/migration, exchange/private read,
secret value/hash/prefix/suffix output, order/probe, Cost Gate change,
deploy/rebuild, live/mainnet, model reload, symlink promotion, or serving
reload was performed by E3.
