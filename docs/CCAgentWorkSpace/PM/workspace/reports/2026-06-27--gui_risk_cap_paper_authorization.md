# GUI Risk-Cap Paper Authorization

## Result

Status: `DONE_WITH_CONCERNS`

The operator correction is now enforced in the paper authorization display path as well: GUI/Rust RiskConfig plus account equity is the source of truth. Fixed USD fallback authorization caps are not allowed.

## Source Change

- Commit: `451be917c058a9813a5b648d3b00cadd15eef237`
- Files:
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub.py`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_routes.py`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_governance_hub.py`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_paper_authorization_risk_caps.py`

Changes:

- `GovernanceHub.grant_paper_authorization()` now requires a positive caller-supplied cap.
- `/paper/session/reauth` resolves the cap from Rust `RiskConfig` plus paper account equity.
- Startup auto-reauth fails closed instead of inventing a fixed cap.
- Regression tests cover GUI `10.0% -> 0.1` semantics and missing-cap denial.

## Runtime Evidence

Runtime source/pins:

- Head: `451be917c058a9813a5b648d3b00cadd15eef237`
- Sync manifest: `/tmp/openclaw/runtime_source_sync_gui_risk_cap_authorization_20260627T140803Z/runtime_sync_manifest.json`
- Sync manifest sha: `3982126fc9d60ff5143f4bd81b0384cc144174a374ccb0fc1be3b014e083ed75`
- Crontab expected-head occurrences: old/new `0/5` full SHA and `0/5` short SHA
- Crontab line count: `70`
- Engine/service restart: `false`

Session state:

- Path: `/tmp/openclaw/session_loop_state_20260627T140826Z_gui_risk_cap_authorization_source_runtime_sync/session_loop_state.json`
- SHA: `e1e9af5e308bb45f0d00a3f455ecd947569b44c5ead694d329b4729d6bd1447d`
- State transition: `DONE_WITH_CONCERNS`

## Risk Semantics

- GUI `10.0` is `10%`, not `10 USDT`.
- Rust `per_trade_risk_pct=0.1` is the stored fraction.
- `position_size_max_pct=25.0` remains the GUI max-single-position percentage.
- `max_order_notional_usdt=0.0` is disabled, not an implicit fixed cap.
- Local `10 USDT` authority is `false`.

## Verification

- Local `py_compile`: passed
- Local governance/paper-cap tests: `66 passed, 1 skipped`
- Local risk-view/paper-cap tests: `28 passed`
- Local E3/BB intake adjacent suite: `29 passed`
- Runtime `py_compile`: passed
- Runtime governance/paper-cap/risk-view tests: `91 passed, 1 skipped`
- Runtime E3/BB intake adjacent suite: `29 passed`
- `git diff --check`: passed locally and on runtime

## Boundary

No E3/BB approval was created or inferred. No service/engine restart, order/cancel/modify, Decision Lease acquire/release, Bybit call, PG query/write, Cost Gate lowering, risk expansion, writer/adapter enablement, live/mainnet authority, execution, fill, PnL, or profit proof occurred.

## Next

Collect actual `current_candidate_e3_bb_enablement_signoff_v1` artifacts from E3 and BB. Even after valid signoffs, rerun fresh same-window bounded Demo authorization, active Decision Lease, Guardian/Rust authority, actual BBO, GUI cap, book-clean, auditability, and reconstructability gates before any order-capable Demo invocation.
