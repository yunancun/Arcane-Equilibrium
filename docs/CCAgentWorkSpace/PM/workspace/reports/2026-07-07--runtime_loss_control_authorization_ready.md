# 2026-07-07 Runtime Loss-Control Authorization READY

Role: `PM`

Status: `RUNTIME_LOSS_CONTROL_READY`

Active blocker: `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD`

## Result

PM completed the required `PM -> E3 -> BB -> PM` gate for the runtime/env loss-control blocker after AI/ML downstream source closure.

E3 verdict: `APPROVE_FOR_BB_REVIEW`

BB verdict: `APPROVE_EXACT_DEMO_ENV_RESTORATION`

Machine packet:

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--runtime_loss_control_authorization_ready.state_packet.json`
- `status=RUNTIME_LOSS_CONTROL_READY`

This packet grants no order/probe/test/live/mainnet/Cost Gate/direct exchange/DB-write/model-promotion authority. It only clears the runtime/loss-control prerequisite so a separate same-window bounded Demo AI/ML learning-test scope can be opened.

## Source State

Pre-runtime source confirmation:

- Mac repo: `/Users/ncyu/Projects/TradeBot/srv`
- Mac HEAD: `e655de92673e4960ceca1888a07a4843ac4ddb3e`
- Mac `origin/main`: `e655de92673e4960ceca1888a07a4843ac4ddb3e`
- GitHub `origin/main`: `e655de92673e4960ceca1888a07a4843ac4ddb3e`
- Linux repo: `trade-core:/home/ncyu/BybitOpenClaw/srv`
- Linux HEAD/origin: `e655de92673e4960ceca1888a07a4843ac4ddb3e`
- Linux status: `## main...origin/main`

Mac worktree had unrelated pre-existing dirty/untracked files. PM did not consume those as runtime source.

Source-stability artifacts:

- First sample: `trade-core:/home/ncyu/BybitOpenClaw/var/openclaw/demo_only_engine_env_restoration_20260707T133658Z_e655de9/source_stability_first_sample.json`, sha `6f7c6ffd891fbb0bfcbfd0d624cae984fe717899d81089f5ad7d0171f94ec956`
- Ready check: `trade-core:/home/ncyu/BybitOpenClaw/var/openclaw/demo_only_engine_env_restoration_20260707T133658Z_e655de9/source_stability_ready_check.json`, sha `5b76a9bd903ea89d1c6721f9b893037ff1d2a5f21be90392f23154e0133e5b63`
- Status: `SOURCE_STABILITY_WINDOW_READY_FOR_E3_BB_REVIEW`

## Authorization Chain

PM request:

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--demo_only_engine_env_restoration_request.json`
- sha `4d5ec4252bd00062cc3a804465c3fced49a443a7ff7de18190af2fc66fc14a2b`

E3 report:

- `docs/CCAgentWorkSpace/E3/workspace/reports/2026-07-07--demo_only_engine_env_restoration_e3_review.md`
- sha `766e1a2456b21402778a289de2d504eda9fe2b015d6c47001a4564862fe31d38`
- verdict `APPROVE_FOR_BB_REVIEW`

BB report:

- `docs/CCAgentWorkSpace/BB/workspace/reports/2026-07-07--demo_only_engine_env_restoration_bb_review.md`
- sha `db10b0185c7535d8113210ab4085e96618eed52309ee1a06c6d9253a05d39c4c`
- verdict `APPROVE_EXACT_DEMO_ENV_RESTORATION`

Approved scope was exact: restore only `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=1` for Demo engine runtime, preserve mainnet/paper disabled state, run engine-only keep-auth restart, then run the reviewed local readiness/loss-control checks. BB granted no direct Bybit public/private endpoint, order/probe, or test authority.

## Runtime Action

Applied on `trade-core`:

- Environment file backup created without printing secret content.
- Changed only `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=0` to `1`.
- Preserved `OPENCLAW_ALLOW_MAINNET=0`, `OPENCLAW_ENABLE_PAPER=0`, `OPENCLAW_DEMO_LEARNING_LANE_WRITER=1`, and the bounded Demo learning-lane plan path.

Operational note: the first direct SSH invocation of `restart_all.sh --engine-only --keep-auth` inherited no systemd runtime env and briefly started the engine on default `/tmp/openclaw` data/socket paths. PM stopped before readiness, performed no order/probe/exchange/DB action, then remediated with an engine-only restart using the original approved runtime data/socket/secrets-root environment values. Final engine PID is `544751`.

Final allowlisted engine env:

- `OPENCLAW_ALLOW_MAINNET=0`
- `OPENCLAW_ENABLE_PAPER=0`
- `OPENCLAW_DEMO_LEARNING_LANE_WRITER=1`
- `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=1`
- `OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw`
- `OPENCLAW_IPC_SOCKET=/home/ncyu/BybitOpenClaw/var/openclaw/engine.sock`
- `OPENCLAW_DEMO_LEARNING_LANE_PLAN=/home/ncyu/BybitOpenClaw/var/openclaw/cost_gate_learning_lane/bounded_demo_probe_soak_plan.json`

API and watchdog user services remained active. No rebuild and no API restart were performed.

## Verification

Fast-balance local Control API artifact:

- Path: `trade-core:/home/ncyu/BybitOpenClaw/var/openclaw/demo_only_engine_env_restoration_20260707T133658Z_e655de9/fast_balance/demo_account_equity_artifact.json`
- sha `2252ff2f2770a8698cd2076d3b539a6222f52d280bf6d7b1cd55c961d4e613c4`
- status `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY`
- read model `rust_snapshot_fast`, pipeline `connected`
- equity `9544.67467679`

Readiness before materialization:

- Path: `trade-core:/home/ncyu/BybitOpenClaw/var/openclaw/demo_only_engine_env_restoration_20260707T133658Z_e655de9/readiness/bounded_demo_runtime_readiness_engine544751.json`
- sha `6e75a8020bd06ab7df8d8d6e9e8c439229df6ab8503e1198088174939754d17d`
- status `BOUNDED_DEMO_RUNTIME_BLOCKED_BY_AUTH_OR_PLAN`
- blockers only `standing_authorization:standing_auth_expired`

Guardrail:

- Path: `trade-core:/home/ncyu/BybitOpenClaw/var/openclaw/demo_only_engine_env_restoration_20260707T133658Z_e655de9/guardrail/standing_demo_authorization_refresh_guardrail.json`
- sha `6bebec7c4ce2677321831edad82ba3f52116a00ed970a2815e19256b0b2fd5b3`
- status `STANDING_DEMO_AUTHORIZATION_REFRESH_READY_NO_RUNTIME_MUTATION`
- expired-auth-readiness-only exception applied

Standing Demo loss-control envelope:

- Runtime path: `trade-core:/home/ncyu/BybitOpenClaw/var/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization.json`
- mode `0600`
- runtime sha `eabf2dab8ddbe9c680a4b047d7a338d5d34a30a28a36134ab820e83a1b174197`
- sanitized artifact sha `efa95afb0039cc83eb15ae002c4b6632eded26b36145c40198597eaae3395773`
- status `STANDING_DEMO_AUTHORIZATION_ACTIVE`
- standing id `standing-demo-refresh-20260707T135348Z-2b0d57e548c1`
- candidate `grid_trading|ETHUSDT|Buy`
- expires `2026-07-08T01:53:48.341325+00:00`
- resolved cap `954.18759458` USDT
- cap not increased from prior standing envelope

Final readiness:

- Path: `trade-core:/home/ncyu/BybitOpenClaw/var/openclaw/demo_only_engine_env_restoration_20260707T133658Z_e655de9/readiness/bounded_demo_runtime_readiness_after_materialization_engine544751.json`
- sha `b77946c0985680a2fe7ff0c332d2ce79e1c204d61e59e92295f88bd6104c05b6`
- status `BOUNDED_DEMO_RUNTIME_READY_FOR_FINAL_WINDOW_GATES`
- blockers `[]`

## Verification Commands And Results

Representative commands used:

```bash
git fetch origin
git rev-parse HEAD
git rev-parse origin/main
git ls-remote origin refs/heads/main
ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && git rev-parse HEAD origin/main && git status --short --branch'
ssh trade-core 'read allowlisted engine env from /proc/<engine_pid>/environ'
ssh trade-core 'sha256sum <source-stability> <fast-balance> <readiness> <guardrail> <materialization>'
```

Results:

- Mac/GitHub/Linux source aligned at `e655de92673e4960ceca1888a07a4843ac4ddb3e` before runtime action.
- Linux worktree was clean.
- Final engine PID `544751` had adapter enabled and mainnet/paper disabled.
- Source stability, fast-balance, readiness, guardrail, materialization, and final readiness artifact hashes matched.

## Boundary

No order/probe/demo-test was run. No live/mainnet/paper enablement occurred. No Cost Gate lowering/change occurred. No direct Bybit public/private endpoint was called. No secret value/hash/prefix/suffix was output. No DB write/migration occurred. No MCP credential/config access occurred. No model promotion, symlink promotion, serving reload, or proof claim occurred.

## Next Gate

The blocker is cleared for opening the next scope only. The bounded Demo AI/ML learning test still requires a new same-window `PM -> E3 -> BB` exact packet with active standing envelope, fresh source/runtime heads, Decision Lease, BBO/instrument/order shape, Guardian/Rust authority, auditability, and reconstructability before any order/probe-capable action.
