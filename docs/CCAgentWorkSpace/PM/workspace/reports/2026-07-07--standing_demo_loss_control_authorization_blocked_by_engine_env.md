# 2026-07-07 Standing Demo Loss-Control Authorization Blocked By Engine Env

PM result: `BLOCKED_BY_RUNTIME_ENV`.

Scope: `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD`.
No public quote/BBO, Decision Lease, direct Bybit private/public endpoint,
order/probe/cancel/modify, bounded probe, `_latest`, PG write, service restart,
deploy, env/crontab/risk mutation, Cost Gate change, live/mainnet, proof, or
promotion action was performed.

## Source And Request

- Approved source head: `798843f23b2fda66117cf95bfe7c996f97fdf543`
- Detached approved worktree:
  `/tmp/openclaw/standing_envelope_runtime_refresh_current_head_20260706T224516Z_798843f2/src_origin_main`
- PM local head at runtime attempt: `1c2a70fc1` (`ahead 4` of `origin/main`);
  local ahead commits were not part of the runtime request.
- Final pre-runtime source check: PASS, `origin/main == 798843f23b2fda66117cf95bfe7c996f97fdf543`.

Source-stability artifacts:

- First sample:
  `/tmp/openclaw/standing_envelope_runtime_refresh_current_head_20260706T224516Z_798843f2/source_stability/source_stability_window_guard_first_sample.json`
  sha `e4ed15570475d2c0d92306a1ae8220000555c429d9ab364114b2a3be1976a022`
- READY check:
  `/tmp/openclaw/standing_envelope_runtime_refresh_current_head_20260706T224516Z_798843f2/source_stability/source_stability_window_guard_ready_check.json`
  sha `0cff421abb32d5caf5c5aa9986a362c30feee80f9214f3a29387edac66288664`

PM request artifact:

- JSON:
  `/tmp/openclaw/standing_envelope_runtime_refresh_current_head_20260706T224516Z_798843f2/review/standing_demo_loss_control_runtime_authorization_request_v1.json`
- sha `62f2a9cc9225d0c70ce7d38aa071c9d387cccca4811174a79d92e4085d4e5f7c`
- `post_approval_drift_policy`: `docs_tests_codex_exempt_v1`

## E3 / BB

E3 verdict: `APPROVE_FOR_BB_REVIEW`.

Required conditions included exact final source/drift gate, execution from
approved detached head, exactly one Control API fast-balance GET using runtime
token file with `--forbid-env-token`, redacted readiness, guardrail with
`--allow-expired-standing-auth-readiness-only`, and exact standing-envelope
materialization only if READY.

BB verdict: `APPROVE_RUNTIME_LOSS_CONTROL_REFRESH`.

BB accepted the exact one local Control API
`GET /api/v1/strategy/demo/balance?fast=1` boundary because it is not a direct
Bybit private/order/public quote endpoint and must validate
`rust_snapshot_fast`, `rust_engine`, connected pipeline, positive equity, and
no authority contamination.

## Runtime Evidence

Runtime read-only precheck:

- Path:
  `trade-core:/home/ncyu/BybitOpenClaw/var/openclaw/standing_envelope_runtime_refresh_current_head_20260706T224516Z_798843f2/runtime_precheck/runtime_readonly_precheck.json`
- sha `f068006ed61a51f3f1788de61846daa79c2db5e2714a81feed2f68a298935b51`
- Services: `openclaw-trading-api` active, `openclaw-watchdog` active.
- API bind: `100.91.109.86:8000`.
- Runtime checkout: `73e129d0e7e7e91c94982ef6a0d11254f5f3dfdd`.
- Existing standing auth sha: `8c891b4e675821118d79921631ccd07c29907130e24ee4dde1483f0be20cfe4f`, mode `0o600`.
- Bounded plan sha: `30056993b5cae70a0fcad0503221e12bd74dae4e42a29d0d2c88423c64739823`, mode `0o600`.
- Crontab active command count: `34`; stale expected-head pin still present.

Approved helper subset was staged under the runtime artifact directory from
the detached approved source. This was not a deploy and did not restart or
modify services.

Fast-balance artifact:

- Path:
  `trade-core:/home/ncyu/BybitOpenClaw/var/openclaw/standing_envelope_runtime_refresh_current_head_20260706T224516Z_798843f2/fast_balance/demo_account_equity_artifact.json`
- sha `0b1fd2abb088eb48548a43a595c35036a61e8cbe6a6c80e2ba7f286d45b38572`
- Status: `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY`
- HTTP status: `200`
- Equity: `9545.91584234`
- Read model: `rust_snapshot_fast`
- Source: `rust_engine`
- Pipeline: `connected`
- Authority contamination: none
- Token source: runtime token file, mode `0o600`; no token value/hash/prefix/suffix emitted.

Runtime readiness:

- Path:
  `trade-core:/home/ncyu/BybitOpenClaw/var/openclaw/standing_envelope_runtime_refresh_current_head_20260706T224516Z_798843f2/readiness/bounded_demo_runtime_readiness_engine3771096.json`
- sha `a81ae387037a8476c495e268cd0c4710df82c4bb522857cade4e1bad51fa96bf`
- Status: `BOUNDED_DEMO_RUNTIME_BLOCKED_BY_ENGINE_ENV`
- Blocking reasons:
  - `engine_env:engine_env_OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED_not_1`
  - `standing_authorization:standing_auth_expired`
- Observed engine env:
  - `OPENCLAW_ALLOW_MAINNET=0`
  - `OPENCLAW_ENABLE_PAPER=0`
  - `OPENCLAW_DEMO_LEARNING_LANE_WRITER=1`
  - `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=0`
  - plan path matched the bounded Demo soak plan

Because the readiness blocker is not only
`standing_authorization:standing_auth_expired`, the E3/BB-approved exception
cannot be consumed.

## Stop

State: `BLOCKED`.

Stop reason: `STOP_LOSS_CONTROL`.

No `standing_demo_authorization_refresh_guardrail.py` run was performed after
the corrected readiness blocker. No standing envelope was materialized. The
existing runtime standing auth remains expired.

Next safe action: open a separate PM->E3 runtime/deploy decision for restoring
the Demo-only engine env so `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=1` without
enabling paper/live/mainnet and without lowering Cost Gate. After that approved
env/deploy action, rerun the source gate, one fast-balance artifact, readiness,
guardrail, and only then materialize the standing envelope if readiness has no
non-expiry blocker.
