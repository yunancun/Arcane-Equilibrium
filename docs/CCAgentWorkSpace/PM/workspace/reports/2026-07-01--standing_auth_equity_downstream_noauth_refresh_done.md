# Standing Auth + Equity Downstream No-Auth Refresh Done

- Date: 2026-07-01
- Active blocker: `P0-CURRENT-CANDIDATE-STANDING-AUTH-AND-EQUITY-INPUT-REFRESH-FOR-DOWNSTREAM-NOAUTH`
- Next blocker: `P0-CURRENT-CANDIDATE-ORDER-CAPABLE-DEMO-INVOKE-FRESH-WINDOW-RUN-GATE`
- State transition: `DONE_WITH_CONCERNS`
- Candidate: `grid_trading|ETHUSDT|Buy`

PM resumed from TODO v701, created session state, and used E3 review `019f1c15-1168-7aa0-a625-91015107dc1c` for the runtime/security scope. E3 approved local Control API fast equity capture, source-only standing-auth refresh guardrail, exact preview materialization, and downstream no-authority review/preflight/envelope artifacts under no quote/lease/order conditions.

The runtime artifacts record source head `0b95487ebf8d7f8250709b4d23f815daeeecd840`. This report/TODO sync was prepared after local `HEAD`/`origin/main` advanced to `e96e843d154f397c73723e199e09ad5b3fda8b19`; `0b95487e` is an ancestor, and the intervening commits are IBKR/static-guard docs/tests outside this cost-gate helper/runtime path.

Runtime API sanity passed before capture: `/tmp/openclaw/pipeline_snapshot_demo.json` was fresh, mode `0600`, `trading_mode=demo`, and had `paper_state.balance`. Equity capture used only `GET /api/v1/strategy/demo/balance?fast=1` against `http://100.91.109.86:8000`, producing `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY` sha `b2c59ba3bb601d07358e91e1f4baa82179edd7f3fc7af0a389a4d332aa590c56`.

Source-only guardrail review produced `STANDING_DEMO_AUTHORIZATION_REFRESH_READY_NO_RUNTIME_MUTATION` sha `50aa2ccf743816908304e87887238545e648a6167f13e778ba28ecafef613c8a`. PM extracted only its checked `envelope_preview`, sha `8c891b4e675821118d79921631ccd07c29907130e24ee4dde1483f0be20cfe4f`, verified candidate scope, no authority expansion, cap not increased, and max probe orders unchanged at `2`, then atomically materialized it to `trade-core:/tmp/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization.json`. Backup is `trade-core:/tmp/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization_backup_20260701T051753Z_before_refresh.json`.

The first no-authority review attempt intentionally failed closed because PM supplied `operator-id=codex-pm-standing-demo`, which did not match the standing envelope operator id `profit-first-fast-demo-loop`. That failed artifact is preserved for audit. PM reran the no-authority chain with the standing operator id and produced:

- Review: `trade-core:/tmp/openclaw/standing_auth_equity_input_refresh_20260701T051320Z_noauth/review_standing_operator/false_negative_operator_review.json`, sha `89fc94ea38fbb0c3bd6d658943678d61df5b70705f111fa0c8bff84e7ddd5fbc`, status `APPROVED_COST_GATE_FALSE_NEGATIVE_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT`, approval source `standing_demo_authorization`.
- Preflight: `trade-core:/tmp/openclaw/standing_auth_equity_input_refresh_20260701T051320Z_noauth/preflight_standing_operator/false_negative_bounded_probe_preflight.json`, sha `e278a01683b47261b2a84cf64a76736ec98ee3d1cc6810cda5cb7fb1d3bc4d78`, status `READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION`.
- No-order envelope: `trade-core:/tmp/openclaw/standing_auth_equity_input_refresh_20260701T051320Z_noauth/envelope_standing_operator/current_candidate_no_order_refresh_envelope_noauth_ready.json`, sha `ea35516ebad0df4d17d676edd63ebc8c7e398ab0abd28c1e5ed420849dcbd19b`, status `CURRENT_CANDIDATE_NO_ORDER_REFRESH_ENVELOPE_READY_NO_CAPTURE_NO_AUTHORITY`.

Manifest `trade-core:/tmp/openclaw/standing_auth_equity_input_refresh_20260701T051320Z_noauth/manifest/standing_auth_equity_input_refresh_manifest.json` sha `f0c78e8a716f955abd03144afd5701b3d0754af9af27ae147ad1992fe05edb63` records `DONE_WITH_CONCERNS`. Session final state `/tmp/openclaw/session_loop_state_20260701T050807Z_standing_auth_equity_input_refresh/session_loop_state_final.json` sha `193f0e0e8f15582f1cf2deb626325a8db1b2fc8be455a329e9aba61c1d3a3604`.

Closeout runtime smoke found no `openclaw` unit in `systemctl list-units/list-unit-files "*openclaw*"`, but uvicorn PID `1038429` with workers still listened on `100.91.109.86:8000`; engine PID `1538641` and cron/audit helpers were also running. PM did not restart, stop, or mutate any service.

Boundary result: no `_latest` overwrite, public quote, active Decision Lease, private/order endpoint, order/cancel/modify, PG write, service/env/risk mutation, Cost Gate lowering, live/mainnet authority, fill/PnL, or profit proof. This clears the standing-auth/equity input blocker only. It does not refresh E3/BB approval for Phase A/B or order-capable runtime action, and it does not grant bounded probe/order authority.
