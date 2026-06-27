# False-Negative Packet Refresh + Standing Auth Materialized

| Field | Value |
|---|---|
| `blocker_id` | `P0-CURRENT-CANDIDATE-STANDING-AUTH-REFRESH-GUARDRAIL` |
| `state_transition` | `DONE_WITH_CONCERNS` |
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260627T_false_negative_packet_refresh_guardrail/session_loop_state.json` |
| `session_loop_state_sha256` | `a6014db26f5ee6252cb010b76a528ddbf20d05563a4a1cad8adaf0864c145a24` |
| `round_summary` | `/tmp/openclaw/false_negative_packet_refresh_guardrail_20260627T1556Z/false_negative_packet_refresh_standing_auth_materialization_round.json` |
| `round_summary_sha256` | `34e97cf49021902eba49fe639423d7f0fd090ecd2b4475c24da4decb787985f7` |
| `source_head` | `9ec3f7d8b2859da10ebcfc19c2ce397306353dd0` |
| `runtime_source_head` | `451be917c058a9813a5b648d3b00cadd15eef237` |

## Decision

The stale false-negative candidate packet blocker is cleared. Runtime already had a fresh no-order packet, so this round copied and consumed it instead of re-running the full cron stack.

- packet path: `/tmp/openclaw/false_negative_packet_refresh_guardrail_20260627T1556Z/inputs/false_negative_candidate_packet_latest_runtime.json`
- packet sha: `08c5684bdad1e6f64537317ab02a879567ef38d3f79e34d4803c53327f769426`
- status: `COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW`
- generated: `2026-06-27T15:29:22.399374+00:00`
- contains current candidate: `grid_trading|AVAXUSDT|Sell`
- no global Cost Gate lowering, no probe authority, no order authority, no promotion evidence

With the fresh packet, the current-candidate standing review became ready:

- review path: `/tmp/openclaw/false_negative_packet_refresh_guardrail_20260627T1556Z/standing_review/current_candidate_standing_demo_loss_control_envelope_review.json`
- review sha: `acff0af265443fd7332263ff63b1c44ac50b6a85e2533d5bf8883d92b7551cfc`
- status: `CURRENT_CANDIDATE_STANDING_DEMO_LOSS_CONTROL_ENVELOPE_READY_NO_RUNTIME_MUTATION`
- blocking gates: `[]`
- source blockers: `[]`
- authority contamination: `[]`

## Runtime Materialization

Only the reviewed `envelope_preview` was materialized to runtime.

- runtime path: `trade-core:/tmp/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization.json`
- runtime sha: `47757625ef41e845ecfb4818f35aa20a225bc40e7bed86ca2ebdd4f8ab7d0eb6`
- mode: `0600`
- standing id: `standing-demo-current-candidate-20260627T155731Z-d1556e7f7a16`
- candidate: `grid_trading|AVAXUSDT|Sell`
- expiry: `2026-06-28T03:57:31.409446+00:00`
- expired backup: `trade-core:/tmp/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization_expired_backup_20260627T1556Z.json`
- expired backup sha: `98766dfe06aa8bcbd86378faa7983b92b00ff8305faefba14303e62dd842f2f3`

Shared validator output:

- validation path: `/tmp/openclaw/false_negative_packet_refresh_guardrail_20260627T1556Z/materialization/standing_demo_authorization_runtime_validation.json`
- validation sha: `c710c2894c7002d7a83d8556270a3c8458a7163e52800a5bcdac34e83f61226c`
- `valid_for_candidate_scoped_authorization=true`
- `runtime_authority_granted=false`
- `live_authority_granted=false`
- `cost_gate_lowering_recommended=false`
- `promotion_evidence=false`

## GUI Risk Lineage

The refreshed standing envelope preserves GUI/Rust RiskConfig semantics:

- GUI P1 risk/trade: `10.0%`
- `per_trade_risk_pct_fraction`: `0.1`
- accepted Demo equity: `9549.38926928`
- resolved per-trade/effective cap: `954.93892693 USDT`
- GUI max-single-position: `25.0%`
- single-position budget: `2387.34731732 USDT`
- proposed no-order shape: `144.0 AVAX / 954.576 USDT`
- local `10 USDT` authority: `false`

## No-Authority Consumer Check

Defer-mode false-negative operator review consumed the fresh packet plus standing envelope:

- path: `/tmp/openclaw/false_negative_packet_refresh_guardrail_20260627T1556Z/operator_review_defer/false_negative_operator_review_defer.json`
- sha: `938bc6876cd19c5288cf49b60f3120e0fff633801e63f4e3aaad160af3ca3d83`
- status: `APPROVED_COST_GATE_FALSE_NEGATIVE_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT`
- approval source: `standing_demo_authorization`
- `bounded_demo_probe_authorized=false`
- `probe_authority_granted=false`
- `order_authority_granted=false`
- `review_grants_runtime_authority=false`

## Boundary

No Decision Lease acquire/release, actual-admission BBO, Bybit private/order call, order/cancel/modify, PG query/write, service restart, env/crontab mutation, Cost Gate lowering, risk expansion, writer/adapter enablement, live/mainnet authority, fill, PnL, promotion proof, or profit proof occurred. Runtime mutation was limited to replacing the expired standing envelope with the reviewed candidate-scoped envelope and backing up the expired file.

## Next

Refresh candidate-matched bounded preflight, touchability, placement, authority readiness, and operator authorization in no-order or explicitly reviewed mode using the fresh standing envelope. Then rerun admission and fresh same-window Decision Lease, Guardian, Rust authority, actual BBO, GUI cap, book-clean, auditability, and reconstructability gates before any order-capable Demo invocation.
