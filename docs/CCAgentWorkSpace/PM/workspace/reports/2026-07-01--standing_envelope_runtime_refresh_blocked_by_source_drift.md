# Standing Envelope Runtime Refresh Blocked By Source Drift

- Date: 2026-07-01
- Active blocker: `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD`
- State transition: `BLOCKED_BY_RUNTIME`
- Next blocker: `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-SOURCE-STABILITY-CURRENT-HEAD`
- Candidate: `grid_trading|ETHUSDT|Buy`

PM attempted the expired standing Demo loss-control envelope runtime refresh after the v732 source guardrail fix. The target scope stayed constrained: one runtime-local authenticated Demo fast-balance GET, bounded readiness, source-only guardrail with `--allow-expired-standing-auth-readiness-only`, exact envelope-preview materialization only if READY with no authority/cap/probe-order expansion, and post-refresh validation.

Runtime read-only evidence at `2026-07-01T18:05:03Z`:

- Runtime checkout: `trade-core:/home/ncyu/BybitOpenClaw/srv`.
- Runtime head: `e16d3323cb58a549262f6bfa6f1ef48ca140aea0`; runtime `origin/main`: `c5fce0c6008b783e8264ce06a3a5f781fe18c26e`; status `ahead 8, behind 164`.
- `openclaw-trading-api.service` and `openclaw-watchdog.service` were active.
- Standing auth `/tmp/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization.json` sha `8c891b4e675821118d79921631ccd07c29907130e24ee4dde1483f0be20cfe4f`, mode `0600`, candidate `grid_trading|ETHUSDT|Buy`, cap `954.18759458`, max probe orders `2`, expired at `2026-07-01T17:16:05.473618+00:00`.
- Canonical soak plan `/tmp/openclaw/cost_gate_learning_lane/bounded_demo_probe_soak_plan.json` sha `30056993b5cae70a0fcad0503221e12bd74dae4e42a29d0d2c88423c64739823`, mode `0600`, status `READY_FOR_DEMO_LEARNING_PROBE`.
- Corrected runtime snapshot path: `/tmp/openclaw/pipeline_snapshot_demo.json`.

Review sequence:

- Initial session state: `/tmp/openclaw/standing_envelope_runtime_refresh_20260701T1754Z_477b2481/state/session_loop_state_initial.json`, sha `46bdd9318dfa295b6e98cac7124cb83f4ea68ae906190981e4417986b35c04e3`.
- E3 approved with conditions at `477b24813c5ac3a72a0d7d4b85a870e1e1b27623`, but BB found source drift to `67c12fca6ca0a2385f9296f9e300052a61497174`.
- E3 approved with conditions at `67c12fca...`, but BB found source drift to `19dae0394eb75be349b34ffaed1010ff9b3cd777`.
- E3 and BB approved with conditions at `19dae039...`, but PM's mandatory pre-action source check found `HEAD == origin/main == ed2b7514a652289be6ddbb43ac9a297e9c295e7e`.

PM did not consume stale approvals. No runtime action was executed.

Boundary result:

- No Control API GET.
- No public quote, Decision Lease, private/order endpoint, order/cancel/modify, fill, PnL, or proof.
- No envelope materialization, canonical plan write, `_latest`, PG write, service/env/risk mutation, Cost Gate change, live/mainnet action, or runtime authority grant.

Conclusion: blocked by source drift, not by operator permission. The current guard is exact-source-only; even if the latest drift appears Stock/ETF-scoped, there is no reviewed machine-checkable impact exception for this standing-envelope refresh surface.

Next action: start from current `origin/main` and either obtain a quiet-window E3/BB cycle that survives the final pre-action source check, or implement/review a narrow source-impact guard that E2/E4 and E3/BB can rely on before retrying the runtime refresh.
