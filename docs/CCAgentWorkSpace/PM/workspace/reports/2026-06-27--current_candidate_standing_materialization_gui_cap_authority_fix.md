# Current Candidate Standing Materialization + GUI Cap Authority Fix

| Field | Value |
|---|---|
| `blocker_id` | `P0-GUI-RISK-CAP-RESOLVER-CURRENT-CANDIDATE-DRIFT-RECONCILE` |
| `state_transition` | `DONE_WITH_CONCERNS` |
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260627T0315Z_gui_cap_bounded_probe_authority_fix_and_materialization.json` |
| `session_loop_state_sha256` | `01d8aa9612312a23db3ba1530170a15af1428a1ccf90f801e46c72d612b9a243` |
| `source_head` | `00680f2b5394a24a7382ac14e10a3f10e47a9ac0` |
| `runtime_head` | `665b2eef615cd1d93f0691a757f9ab4c3ade83ed` |

## Decision

Operator correction accepted and enforced in source/runtime review: GUI/Rust RiskConfig is the source of truth. GUI `P1 Risk/Trade = 10.0%` means `per_trade_risk_pct=0.1`; it is not a `10 USDT` per-order cap.

Runtime standing Demo envelope was materialized for current `grid_trading|AVAXUSDT|Sell`, but no order/probe authority was granted. The refreshed bounded authorization now fails closed as `GUI_RISK_CAP_INPUT_REQUIRED_FOR_AUTHORIZATION_REVIEW` because the old placement repair snapshot still carries `max_demo_notional_usdt_per_order=10.0` and no GUI cap lineage.

## Source Change

Commit pushed:

- `00680f2b5394a24a7382ac14e10a3f10e47a9ac0` - `Enforce GUI risk cap for bounded probe authority`

Key changes:

- Shared standing Demo validator now requires `risk_cap_lineage` with GUI-backed Rust RiskConfig semantics and rejects local `10 USDT` authority.
- False-negative bounded preflight derives `max_demo_notional_usdt_per_order` from `standing_demo_authorization.risk_cap_lineage.resolved_cap_usdt`.
- Touchability and placement repair artifacts preserve cap lineage downstream.
- Bounded authorization adds `gui_risk_notional_limit_valid` and blocks mismatched/stale caps before authorization review.
- Rust active bounded-probe default cap is now fail-closed `0.0`; callers must supply a reviewed GUI/RiskConfig cap.

## Runtime Materialization

Materialized runtime envelope:

- path: `trade-core:/tmp/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization.json`
- sha: `42fca4b3e4bd1143dd8550bb4f36ff85774eed7a3b8acbf3ae99243d2a49d520`
- mode: `0600`
- candidate: `grid_trading|AVAXUSDT|Sell`
- status: `STANDING_DEMO_AUTHORIZATION_ACTIVE`
- expires: `2026-06-27T14:51:58.043996+00:00`

Previous ETH envelope backup:

- `trade-core:/tmp/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization_eth_backup_20260627T025558Z.json`

No env/crontab mutation, service restart, Bybit call, PG write, adapter/writer enablement, order submission, Cost Gate change, or live authority occurred.

## Refreshed Artifacts

- Admission verification after standing materialization: sha `9d7cf29ef5692351fb64455e1f12852170553aac661b190f6a44ffd05bf23e6e`, status `CURRENT_CANDIDATE_BOUNDED_DEMO_ADMISSION_BLOCKED_BY_LOSS_CONTROL`; standing valid, remaining blockers are bounded auth object, Decision Lease, Guardian risk gate, Rust authority path, and fresh BBO at actual admission.
- False-negative operator review: sha `5237174eaa1cfde80d5474e3ced087823f02a3cb51ad52664862a52657f7b40d`, status `APPROVED_COST_GATE_FALSE_NEGATIVE_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT`.
- Refreshed preflight: sha `ff69e4b591a3edd268152c10efd2c0804d80881e207297a061d837bf4f06c532`, status `READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION`, cap `955.24342626 USDT`, max probe intents `2`.
- Refreshed bounded authorization: sha `0828051978c59ffb070d882510fa987936795a2cf0fa1997cad205134a112c71`, status `GUI_RISK_CAP_INPUT_REQUIRED_FOR_AUTHORIZATION_REVIEW`, decision `defer`, blockers `gui_risk_notional_limit_valid`, `placement_repair_plan_ready`, `authority_path_patch_readiness_ready`.

## Verification

- Python focused/adjacent suite: `255 passed`
- Standing/preflight/operator-policy focused suite: `124 passed`
- Current-candidate/placement adjacent suite: `96 passed`
- `py_compile`: pass
- Rust bounded-probe filter: `29 passed`
- touched Rust files `rustfmt --check`: pass
- `git diff --check`: pass
- Full workspace `cargo fmt --check` is not a clean signal because unrelated pre-existing Rust formatting drift exists outside touched files.

## Boundary

No bounded authorization object, Decision Lease, Guardian/Rust order authority, runtime admission, order, cancel/modify, Bybit private call, PG write, Cost Gate lowering, risk expansion, live/mainnet authority, promotion evidence, or profit proof.

## Next

Refresh touchability and placement repair artifacts from the GUI-cap preflight so placement no longer carries stale `10.0`. Then refresh authority patch readiness and bounded authorization in `defer` mode. Order-capable action remains blocked until bounded auth object, Decision Lease, Guardian risk gate, Rust authority path, fresh actual-admission BBO, auditability, and reconstructability all pass.
