# GUI Risk Cap Runtime Cache Reconcile

| Field | Value |
|---|---|
| `blocker_id` | `P0-GUI-RISK-CAP-RESOLVER-CURRENT-CANDIDATE-DRIFT-RECONCILE` |
| `state_transition` | `DONE_WITH_CONCERNS` |
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260627T0130Z_gui_risk_cap_runtime_cache_reconcile.json` |
| `session_loop_state_sha256` | `0c086dac540d3aea41ffb95e861c019e2d6bc3525fcdbe6ce0b13f6e964ef10f` |

## Runtime Ground Truth

Read-only runtime inspection found current bounded auth latest still AVAX:

- path: `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_latest.json`
- sha: `42bdae7bb03eeb3742236c06011c4ed2255d4ccb7ba5a9570a9bb21ea4eb1d27`
- mtime: `2026-06-27T01:00:04.681604+00:00`
- status: `FALSE_NEGATIVE_PREFLIGHT_NOT_READY`
- decision: `defer`
- candidate: `grid_trading|AVAXUSDT|Sell`

Current control/construction artifacts remain missing:

- `source_only_control_identity_contract_latest.json`
- `bounded_probe_candidate_construction_preview_latest.json`
- canonical `demo_account_equity_artifact_latest.json`
- canonical `current_cap_staircase_risk_worksheet_latest.json`

Existing AVAX construction inputs are stale and must not be treated as current:

- reroute latest: `2026-06-24T17:32:41Z`
- market snapshot latest: `2026-06-24T18:13:27Z`
- construction preview latest: `2026-06-24T18:13:31Z`
- cap-feasible selection: `2026-06-25T21:51:13Z`

## Equity Capture

The Mac direct helper call against `http://100.91.109.86:8000` with local token failed `401 Unauthorized` and emitted a source-failure artifact, not accepted evidence:

- path: `/tmp/openclaw/gui_risk_cap_runtime_cache_reconcile_20260627T0135Z/demo_account_equity_artifact.json`
- sha: `2d0cdbe05bce22a020a64ac24ecbc5ad8aeeefd4411404ff0360a9dc388d32e4`
- status: `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_SOURCE_FAILURE_NO_AUTHORITY`

Runtime-local Tailscale Control API GET with the runtime `0600` token succeeded:

- raw response: `/tmp/openclaw/gui_risk_cap_runtime_cache_reconcile_20260627T0135Z/demo_fast_balance_response.json`
- raw sha: `9250972fcaf8d9cf1a779f0f4a2bd57d8e8270a2d0359116299643cb14ed70bf`
- endpoint: `/api/v1/strategy/demo/balance?fast=1`
- `action_result=success`
- `is_simulated=true`
- `data_category=paper_simulated`
- `source=rust_engine`
- `read_model=rust_snapshot_fast`
- `pipeline_status=connected`
- `equity=9552.43426257`

Accepted artifact:

- path: `/tmp/openclaw/gui_risk_cap_runtime_cache_reconcile_20260627T0135Z/demo_account_equity_artifact_ready.json`
- sha: `afea4d759ab28e7063be23c58de17c3a45007397f7121654aaa7c2e8a044485e`
- status: `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY`

## Cap Resolution

Worksheet:

- path: `/tmp/openclaw/gui_risk_cap_runtime_cache_reconcile_20260627T0135Z/current_cap_staircase_risk_worksheet_missing_current_inputs.json`
- sha: `8b03d00bf05dc8a7dbcbf3f752934c5eb90f1d0cef74ae2bdb9090c171dd18a2`
- status: `CONTROL_IDENTITY_CONTRACT_INPUT_NOT_READY`
- order admission: `false`

The worksheet accepted the runtime equity artifact and resolved the GUI-backed cap:

- GUI P1 risk/trade: `10.0%`
- account equity: `9552.43426257`
- per-trade budget: `955.24342626 USDT`
- max single position budget: `2388.10856564 USDT`
- max order notional: `0.0` disabled
- resolved per-order cap: `955.24342626 USDT`

This proves the operator correction in runtime terms: GUI `10.0%` is not `10 USDT`.

## Boundary

Performed only read-only runtime artifact inspection plus one Control API GET to the Demo fast-balance endpoint. No Control API POST, Bybit/private/order/cancel/modify call, PG query/write, service/crontab/env mutation, runtime sync, Cost Gate lowering, risk expansion, adapter/writer enablement, probe/order/live authority, or profit/proof claim.

## Next

Do not repeat equity capture while the timestamped artifact remains fresh. The next executable step is either:

- runtime source sync so `trade-core` has v605 helper support, or
- reviewed PM -> E3 -> BB no-order public quote/current-construction refresh that produces fresh current candidate control/construction inputs.

If fresh current-candidate control/construction inputs cannot be produced, mark `BLOCKED_BY_LOSS_CONTROL`. If candidate rotates again, record `ROTATED`.
