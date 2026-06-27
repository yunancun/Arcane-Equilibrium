# Same-Lineage Downstream Refresh Done

| Field | Value |
|---|---|
| `blocker_id` | `P0-CURRENT-CANDIDATE-DOWNSTREAM-BOUNDED-AUTH-ADMISSION-REFRESH` |
| `state_transition` | `DONE_WITH_CONCERNS` |
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260627T_same_lineage_downstream_refresh/session_loop_state.json` |
| `session_loop_state_sha256` | `576eebdd43334923547ff97760a9e3815216b66382c9425bfc5671cd88f8dc82` |
| `round_manifest` | `/tmp/openclaw/same_lineage_downstream_refresh_20260627T162202Z/same_lineage_downstream_refresh_manifest.json` |
| `round_manifest_sha256` | `eb2f97b0b03652ed8c1a47a018b892a22798523c163ad212b40461f92141ec97` |
| `source_head_at_review` | `93279a847e9737f2a58b52218c70cf2132d4683d` |
| `runtime_source_head_at_review` | `451be917c058a9813a5b648d3b00cadd15eef237` |

## Decision

The v654 GUI cap lineage mismatch is cleared for the downstream no-order review chain.

The regenerated artifacts now use the same GUI/Rust RiskConfig plus accepted Demo equity lineage as the current standing authorization:

- GUI P1 risk/trade: `10.0%`
- `per_trade_risk_pct_fraction`: `0.1`
- accepted Demo equity: `9549.38926928`
- resolved per-trade/effective cap: `954.93892693 USDT`
- GUI max-single-position: `25.0%`
- single-position budget: `2387.34731732 USDT`
- local `10 USDT` authority: `false`

## Refreshed Artifacts

- preflight: `/tmp/openclaw/same_lineage_downstream_refresh_20260627T162202Z/preflight/false_negative_bounded_probe_preflight_same_lineage.json`
- preflight sha: `a838783683b73ed61f0aefe6c7e6aee38712dcdd30a472c7f574486f6f1b33f2`
- preflight status: `READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION`
- preflight blocking gates: `[]`

- touchability: `/tmp/openclaw/same_lineage_downstream_refresh_20260627T162202Z/touchability/bounded_probe_touchability_preflight_same_lineage.json`
- touchability sha: `15bed8d66522d9bd8820ccda22c87d77b832e052ab20a8e486fbb7db6702b03a`
- touchability status: `FIRST_ATTEMPT_TOUCHABILITY_BOOTSTRAP_REQUIRED`
- touchability reason: `no_candidate_matched_orders_exist_for_first_touchability_attempt`

- placement: `/tmp/openclaw/same_lineage_downstream_refresh_20260627T162202Z/placement/bounded_probe_placement_repair_plan_same_lineage.json`
- placement sha: `c5a15b6124ebce40bf9577cb7973a015fe1fbc329cd723286a76a5025fe76c91`
- placement status: `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW`

- bounded auth: `/tmp/openclaw/same_lineage_downstream_refresh_20260627T162202Z/auth/bounded_probe_operator_authorization_same_lineage_authorize.json`
- bounded auth sha: `c66dd52731da87ca8eb01acc5f78f5c78960d87a68fa8227053de9133808ec66`
- bounded auth status: `BOUNDED_DEMO_PROBE_AUTHORIZED`
- bounded auth id: `standing-demo-9bd754050eb38514`
- bounded auth blocking gates: `[]`
- GUI risk notional gate: valid, with standing/preflight/placement cap all `954.93892693 USDT`
- active runtime probe/order authority: `false/false`
- writer enabled: `false`
- order submission performed: `false`

## Admission Review

- path: `/tmp/openclaw/same_lineage_downstream_refresh_20260627T162202Z/admission/current_candidate_bounded_demo_admission_envelope_review_same_lineage.json`
- sha: `69e905ad973235df1bd0f4b76cce997249dbb3857a03bb56ce5e714ba226fe35`
- status: `CURRENT_CANDIDATE_BOUNDED_DEMO_ADMISSION_BLOCKED_BY_LOSS_CONTROL`
- blocking gates: `decision_lease_valid`, `fresh_bbo_refresh_at_actual_admission`
- source blockers: `[]`
- authority contamination reasons: `[]`
- bounded authorization valid for current candidate: `true`
- Guardian gate valid for current candidate: `true`
- Rust authority path valid for current candidate review: `true`
- order/runtime admission ready: `false/false`

The current blocker is no longer GUI cap lineage or bounded auth object validity. It is the final same-window runtime admission boundary: active current-candidate Demo Decision Lease plus actual-admission BBO/gate evidence.

## Boundary

This round produced timestamped no-order review artifacts only. It did not promote `_latest`, mutate runtime configuration, acquire/release a Decision Lease, refresh actual-admission BBO, call Bybit private/order APIs, submit/cancel/modify orders, enable writer/adapter paths, lower Cost Gate, use live/mainnet, produce fills/PnL, or claim profit proof.

## Next

Rerun same-window active Demo Decision Lease plus actual-admission BBO/gate evidence without order submission. Only after lease, BBO, Guardian, Rust authority, auditability, and reconstructability gates pass in one final window may a bounded Demo order-capable invocation be considered.
