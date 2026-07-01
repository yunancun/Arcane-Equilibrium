# Order-Capable No-Order Auth Refresh Blocked By Control API 401

- Date: 2026-07-01
- Active blocker: `P0-CURRENT-CANDIDATE-ORDER-CAPABLE-DEMO-INVOKE-FRESH-WINDOW-RUN-GATE`
- Next blocker: `P0-CURRENT-CANDIDATE-CONTROL-API-AUTH-REPAIR-FOR-NOORDER-REFRESH`
- State transition: `BLOCKED_BY_RUNTIME`
- Candidate: `grid_trading|ETHUSDT|Buy`

PM revalidated the current order-capable path after source advanced to `da7cd859a993cebdab0f830d76952c0bc68154f6`. Clean source-stability READY artifact `/tmp/openclaw/source_stability_window_guard_20260701T0910Z_da7cd859_clean_detached_ready_check/source_stability_window_guard_ready_check.json` sha `04d8587736f343c61d7f4cc1137be15ef2a9874efce2d27ea99dad9577fc945e` cleared the source quiet-window check.

Runtime read-only evidence showed the standing Demo auth remained active as sha `8c891b4e675821118d79921631ccd07c29907130e24ee4dde1483f0be20cfe4f`, expiry `2026-07-01T17:16:05.473618+00:00`, but the canonical bounded Demo soak plan sha `30056993b5cae70a0fcad0503221e12bd74dae4e42a29d0d2c88423c64739823` still embedded the older bounded auth expiry `2026-07-01T09:02:17.250395+00:00`.

PM generated a cap-consistent no-order bounded-auth refresh bundle under `/tmp/openclaw/order_capable_soak_plan_auth_refresh_20260701T091824Z_da7cd859_noorder/`:

- touchability preflight sha `5e500046693c98bc43cd85cf236652482a64caeafeace54464b349a670e32447`, status `FIRST_ATTEMPT_TOUCHABILITY_BOOTSTRAP_REQUIRED`
- placement plan sha `fe32a7999ad23d12267f94667d8b4a0fde3bcaa1990984de98880cb812b5fcba`, status `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW`
- authority readiness sha `5a5cca972a515ffe7fbd639aa35a56c2f0c2f82f5ce4228c8e0948e33ac98583`, status `AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW`
- bounded auth sha `096cad3dc5f153b64d4ab638a0cc9c7513a0220203cfba9bba2869d2497c0e2e`, status `BOUNDED_DEMO_PROBE_AUTHORIZED`, auth id `standing-demo-37ba6f0e6daa6be2`, expiry `2026-07-01T17:16:05.473618+00:00`

E3 `019f1cfa-b25e-7012-8d06-66fd4dc459cf` and BB `019f1cfa-e717-7700-9087-a47b49b951ff` approved only the exact no-order refresh-chain request sha `4bdb10e459cc7f666a8d14bd0a3a831e61a9b2c1ca11d2fcbbbd5317f75acff4`: one local Control API fast-balance GET, one no-order envelope rebuild, up to three public Demo Bybit market-data GETs, and one plan-inclusion preview. They explicitly did not approve canonical plan materialization, `_latest`, Decision Lease activity, private/order endpoint use, PG write, service/env/risk mutation, Cost Gate change, live/mainnet, order, fill, PnL, or proof.

The approved chain stopped at Phase 1. Equity capture made the single approved Control API request to `http://100.91.109.86:8000/api/v1/strategy/demo/balance?fast=1` and failed closed as `/tmp/openclaw/order_capable_soak_plan_auth_refresh_20260701T091824Z_da7cd859_noorder/equity/demo_account_equity_artifact.json` sha `ff5523d6ab6635fcffc4232af91101603d04a4cc8f820a85a57001b53653e3ef`, status `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_SOURCE_FAILURE_NO_AUTHORITY`, reason `demo_fast_balance_transport_failure`, with transport error `HTTP Error 401: Unauthorized`.

No public Bybit request, current-candidate envelope rebuild, plan-inclusion preview, canonical soak plan write, `_latest` overwrite, Decision Lease acquire/release, private/order endpoint, order/cancel/modify, PG write, service/env/risk mutation, Cost Gate change, live/mainnet, fill/PnL, or proof occurred. Current source later advanced to `0442c33bac99843b139388dff998e24e1ba3db10`, so the `da7cd859` E3/BB request is also stale and non-reusable.

Next action: do not retry the consumed one-GET approval. Diagnose the Control API auth source by metadata only, without exposing token contents, then generate a fresh current-head E3/BB-reviewed no-order refresh request before any new equity capture or public quote.
