# Current Candidate Public Quote / Construction Refresh

| Field | Value |
|---|---|
| `blocker_id` | `P0-GUI-RISK-CAP-RESOLVER-CURRENT-CANDIDATE-DRIFT-RECONCILE` |
| `state_transition` | `DONE_WITH_CONCERNS` |
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260627T0213Z_current_candidate_public_quote_construction_refresh.json` |
| `session_loop_state_sha256` | `f7094faf69ed7a70da1414e9c81e58a7b50f2b52a23de6b931d2bc3b5b1b9e7c` |
| `source_head` | `8f88a713b35d16cefbd8a6864b09c2c14c324c86` |
| `runtime_head` | `665b2eef615cd1d93f0691a757f9ab4c3ade83ed` |

## Decision

This round produced fresh current-candidate no-order quote and construction artifacts for `grid_trading|AVAXUSDT|Sell`.

It preserves the operator correction: GUI `P1 Risk/Trade = 10.0%` is TOML `per_trade_risk_pct=0.1`, so the resolved per-order cap is `955.24342626 USDT` from audited Demo equity. The old `10 USDT` bounded-probe local envelope is not risk authority.

## Source/Test

Added:

- `helper_scripts/research/cost_gate_learning_lane/current_candidate_public_quote_construction_refresh.py`
- `helper_scripts/research/tests/test_current_candidate_public_quote_construction_refresh.py`

The helper consumes a READY `cost_gate_current_candidate_no_order_refresh_envelope_v1`; it does not accept caller-supplied cap override. The cap source is fixed to `current_candidate_envelope.cap_resolution.resolved_cap_usdt`.

Verification before push:

- `PYTHONPATH=helper_scripts/research python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/current_candidate_public_quote_construction_refresh.py`
- focused pytest: `test_current_candidate_public_quote_construction_refresh.py` -> `5 passed`
- adjacent pytest: current envelope + public quote capture + new helper -> `32 passed`
- `git diff --check`

Source/test commit pushed:

- `8f88a713b35d16cefbd8a6864b09c2c14c324c86`

## Runtime Equity Input

Mac-side direct fast-balance calls with the local token correctly failed closed with HTTP `401`; no naked equity number was accepted.

The accepted equity artifact came from a runtime-local Control API GET using the runtime `0600` token file, with no token output:

- path: `/tmp/openclaw/current_candidate_public_quote_construction_refresh_20260627T021157Z/demo_account_equity_artifact_ready_candidate.json`
- sha: `ae0f84f005eab4ac5e9116d68516e979c42f254f38acdeff6c63272286b886ec`
- status: `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY`
- generated: `2026-06-27T02:11:58.561769+00:00`

The regenerated current-candidate envelope:

- path: `/tmp/openclaw/current_candidate_public_quote_construction_refresh_20260627T021157Z/current_candidate_no_order_refresh_envelope.json`
- sha: `993ff2ca0c027281d81d8fb80a2357b3063c41ecbb9261b8740b7ebc02fef9eb`
- status: `CURRENT_CANDIDATE_NO_ORDER_REFRESH_ENVELOPE_READY_NO_CAPTURE_NO_AUTHORITY`
- candidate: `grid_trading|AVAXUSDT|Sell`
- resolved cap: `955.24342626 USDT`

## Public Quote / Construction

Executed exactly three public Bybit market-data GETs from the reviewed request envelope:

- `/v5/market/time`
- `/v5/market/tickers?category=linear&symbol=AVAXUSDT`
- `/v5/market/instruments-info?category=linear&symbol=AVAXUSDT`

Artifacts:

- summary: `/tmp/openclaw/current_candidate_public_quote_construction_refresh_20260627T021157Z/current_candidate_public_quote_construction_refresh.json`, sha `be96831c0aa40a8aefbc7eab343dd09060439faac39f2a2ac5c208ecc606d684`
- public quote: `/tmp/openclaw/current_candidate_public_quote_construction_refresh_20260627T021157Z/public_quote.json`, sha `43d6b98ea8ec04f4ae594b194feb2fbfc6d335587ab8eab9e3fdbf15a367a6b8`
- market snapshot: `/tmp/openclaw/current_candidate_public_quote_construction_refresh_20260627T021157Z/market_snapshot.json`, sha `09ede9ac86827643a4e4b27759d42d647186f7c6c47474551f5b76f547ff1398`
- construction preview: `/tmp/openclaw/current_candidate_public_quote_construction_refresh_20260627T021157Z/construction_preview.json`, sha `92b269f0f5e0d6510e053f1027a525c992b9056cff641573eeba8fb639267ad2`

Result:

- status: `CURRENT_CANDIDATE_PUBLIC_QUOTE_CONSTRUCTION_REFRESH_READY_NO_ORDER`
- BBO age: `497.462ms` under the `1000ms` gate
- best bid/ask: `6.551` / `6.552`
- placement mode: `sell_near_touch_post_only_at_or_above_best_ask`
- limit price: `6.552`
- rounded qty: `145.7`
- rounded notional: `954.6264 USDT`
- construction: `constructible_under_cap`
- blocking gates: none

## Boundary

Performed one runtime-local Demo fast-balance Control API GET and three public market-data GETs. No Bybit private endpoint, no order/cancel/modify, no Control API POST, no PG query/write, no runtime mutation, no service restart, no crontab/env mutation, no Cost Gate lowering, no risk expansion, no adapter/writer enablement, no probe/order/live authority, and no profit proof.

`order_admission_ready=false` remains explicit. These artifacts are construction/control evidence only; a canonical runtime admission and Decision Lease/loss-control envelope is still required before any order-capable action.

## Next

Use these artifacts as the current no-order construction/control inputs for the next PM -> E3 -> BB checkpoint. The next step must either canonicalize the current-candidate snapshot/construction handoff into the existing admission contract or create a reviewed runtime admission envelope that remains no-order until Guardian, Rust authority, Decision Lease, and bounded loss controls all pass.
