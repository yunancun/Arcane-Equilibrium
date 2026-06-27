# Current Candidate No-Order Refresh Envelope

| Field | Value |
|---|---|
| `blocker_id` | `P0-GUI-RISK-CAP-RESOLVER-CURRENT-CANDIDATE-DRIFT-RECONCILE` |
| `state_transition` | `DONE_WITH_CONCERNS` |
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260627T0240Z_current_candidate_refresh_envelope.json` |
| `session_loop_state_sha256` | `13b70d1074f5aaf830a5b6661a76678f9b3bd6ad90cdf1523ddd123c90a9f2a3` |
| `runtime_current_envelope` | `/tmp/openclaw/current_candidate_no_order_refresh_envelope_20260627T0145Z/current_candidate_no_order_refresh_envelope.json` |
| `runtime_current_envelope_sha256` | `26868bbe1bd68b0ae0cae9bb232ef58b536ab2c990929bba1ad22e829f42340f` |

## Decision

This round added a source-only helper for the missing current-candidate refresh envelope instead of running a public quote/current-construction refresh directly. The helper makes current candidate identity, GUI-backed cap semantics, accepted Demo equity freshness, and no-authority boundaries machine-checkable before any PM -> E3 -> BB exchange-facing review.

## Source Change

Added:

- `helper_scripts/research/cost_gate_learning_lane/current_candidate_no_order_refresh_envelope.py`
- `helper_scripts/research/tests/test_cost_gate_current_candidate_no_order_refresh_envelope.py`

The new packet schema is `cost_gate_current_candidate_no_order_refresh_envelope_v1`.

READY requires:

- fresh false-negative operator review and false-negative preflight with exact candidate match
- optional bounded auth input must remain no-authority/defer-or-reject and contain no auth object
- accepted `demo_account_equity_artifact_v1`
- GUI-backed Rust RiskConfig cap resolution
- no network/Bybit/PG/runtime/order/probe/live/proof authority

It explicitly records GUI semantics: TOML `per_trade_risk_pct=0.1` is GUI `10.0%`, so the cap is `account_equity_usdt * 0.1`, not a hardcoded `10 USDT` local bounded-probe envelope.

## Runtime-Current Artifact Check

Read-only copied current runtime artifacts into `/tmp/openclaw/current_candidate_no_order_refresh_envelope_20260627T0145Z/`:

- false-negative review sha `956cf84665c6b43be9ae95a6aeb0db5cbfa9c8b7acc6c28d8e5bcc346c0529b1`, status `STANDING_DEMO_AUTHORIZATION_INVALID_FOR_PREFLIGHT_REVIEW`, decision `defer`, candidate `grid_trading|AVAXUSDT|Sell`
- false-negative preflight sha `929c5b4ff71f9e5df2ebdc8217a12ffbb34f96c360635ecef085fa2c4e5086cf`, status `STANDING_DEMO_AUTHORIZATION_INVALID_FOR_PREFLIGHT`, candidate `grid_trading|AVAXUSDT|Sell`
- bounded auth sha `9cfcb594fe8ae1dfadf50865d723d0f46b0ab714bda9f8739da0b1891b880e3a`, status `STANDING_DEMO_AUTHORIZATION_INVALID`, decision `defer`, no active probe/order authority

The helper accepted the candidate identity and no-authority boundary but fail-closed on equity freshness:

- output status: `GUI_RISK_CAP_INPUT_REQUIRED_NO_AUTHORITY`
- candidate: `grid_trading|AVAXUSDT|Sell`
- GUI P1 risk/trade display: `10.0`
- accepted artifact path: `/tmp/openclaw/gui_risk_cap_runtime_cache_reconcile_20260627T0135Z/demo_account_equity_artifact_ready.json`
- accepted artifact sha: `afea4d759ab28e7063be23c58de17c3a45007397f7121654aaa7c2e8a044485e`
- equity artifact generated at: `2026-06-27T01:12:45.039972+00:00`
- age at envelope generation: `1844.433s`
- max age: `900s`
- blocking reason: `account_equity_artifact_stale`
- `refresh_envelope`: empty
- `network_call_performed=false`
- `public_quote_capture_performed=false`
- `order_admission_ready=false`

## Verification

- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/current_candidate_no_order_refresh_envelope.py`: pass
- focused pytest: `test_cost_gate_current_candidate_no_order_refresh_envelope.py` -> `7 passed`
- adjacent cap/equity/quote suite -> `36 passed`
- `git diff --check`: pass
- runtime-current helper invocation with project Python 3.12 generated the fail-closed artifact above

## Boundary

Performed only source/test/docs updates, read-only runtime artifact copy, and local source-only artifact generation. No public quote capture, Bybit private/order/cancel/modify call, PG query/write, Control API POST, service restart, cron run, runtime source sync, Cost Gate lowering, risk expansion, adapter/writer enablement, probe/order/live authority, or profit/proof claim.

## Next

Do not run public quote/current-construction refresh on the stale equity artifact. The next safe step is a reviewed cache-only Demo fast-balance equity refresh or another accepted fresh equity artifact, then regenerate this envelope and submit the exact no-order public quote/current-construction refresh for PM -> E3 -> BB review. If the candidate rotates before that, record `ROTATED`.
