# 2026-07-07 Demo-Only Engine Env Restoration BB Review

Role: `BB(default)` read-only Bybit technical/policy audit.

Status: `DONE`

Verdict: `APPROVE_EXACT_DEMO_ENV_RESTORATION`

Reviewed request:

- Path: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--demo_only_engine_env_restoration_request.json`
- SHA-256: `4d5ec4252bd00062cc3a804465c3fced49a443a7ff7de18190af2fc66fc14a2b`

E3 prerequisite:

- E3 report:
  `docs/CCAgentWorkSpace/E3/workspace/reports/2026-07-07--demo_only_engine_env_restoration_e3_review.md`
- E3 verdict: `APPROVE_FOR_BB_REVIEW`

## Facts

- Linux `trade-core` read-only check showed
  `HEAD == origin/main == e655de92673e4960ceca1888a07a4843ac4ddb3e` and a
  clean worktree.
- Engine PID `3771096` was running. API and watchdog user services were active.
- Allowlisted engine env currently had `OPENCLAW_ALLOW_MAINNET=0`,
  `OPENCLAW_ENABLE_PAPER=0`, `OPENCLAW_DEMO_LEARNING_LANE_WRITER=1`,
  `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=0`, and the expected bounded Demo
  learning lane plan path.
- `restart_all.sh` option parsing confirms `--rebuild` is opt-in, and
  `--engine-only` runs engine restart without `restart_api`.

## Judgment

Inference: changing only `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=0 -> 1`,
followed only by
`bash helper_scripts/restart_all.sh --engine-only --keep-auth`, is acceptable
inside the Bybit boundary because it performs no `/v5/*` call, no public
quote/BBO read, no private/account/order read, and no
order/probe/cancel/modify action.

This only restores a Demo bounded-probe adapter prerequisite so approved local
readiness/loss-control checks can rerun.

## Conditions

- Edit only
  `/home/ncyu/BybitOpenClaw/secrets/environment_files/basic_system_services.env`
  for `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=0 -> 1`.
- Preserve mainnet disabled, paper disabled, Demo writer enabled, same plan
  path, and Demo connector mode.
- No rebuild, no API restart, no Cost Gate change, no risk/config/plan
  mutation.
- Do not print or inspect secret values; re-check only allowlisted env keys.
- Stop with `STOP_BOUNDARY` on any scope drift.
- Stop with `STOP_LOSS_CONTROL` if readiness has any non-expiry blocker after
  restoration.

## Boundary

No order/probe/demo-test/direct Bybit endpoint authority is granted. No public
or private Bybit read authority is granted. No `RUNTIME_LOSS_CONTROL_READY`
claim is made by this BB review.

BB AUDIT DONE:
`docs/CCAgentWorkSpace/BB/workspace/reports/2026-07-07--demo_only_engine_env_restoration_bb_review.md`
