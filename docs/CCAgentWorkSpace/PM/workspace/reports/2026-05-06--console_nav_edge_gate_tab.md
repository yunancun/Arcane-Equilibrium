# Console Navigation + Edge Gate Tab

Date: 2026-05-06
Role: PM local implementation
Repo root: `/Users/ncyu/Projects/TradeBot/srv`

## Result

- Reworked `/console` top navigation from a flat tab strip into grouped sections:
  `核心`, `交易`, `策略/Edge`, `治理`, `智能`, and `运维`.
- Added standalone `Pre-Live Gates` tab at `/static/tab-edge-gates.html`.
- Edge Gates tab shows:
  - Live readiness summary for [33]/[38]/[40].
  - Gate trend cards for maker fill / grid lifecycle / realized edge.
  - Strategy Gate Matrix for grid, MA, funding arb, BB breakout, BB reversion.
  - Crisis count from active negative cells.
  - Global healthcheck PASS/WARN/FAIL summary from `/api/v1/system/health`.
- Extended `/api/v1/strategy/prelive/edge-gates` with read-only
  `strategy_status` so the new tab can show per-strategy pass/warn/fail/crisis.

## Boundary

Read-only source/static/API change. No trading mode, risk config, live auth,
engine runtime, DB migration apply, strategy parameter change, rebuild, or
restart was performed.

## Verification

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_prelive_edge_gate_trends.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/static/test_replay_subtab_static_assets.py -q` -> 46 passed.
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/prelive_edge_gate_trends.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_read_routes.py` -> passed.
- Inline JS syntax check for `console.html` and `tab-edge-gates.html` -> passed.
- `git diff --check` -> clean.

## Dispatch

Repository-preferred feature chain is `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`.
No sub-agents were spawned because the active Codex tool rule only permits
sub-agents when explicitly requested by the operator. PM performed local
PA/E1/E2/E4/QA-style steps in one scoped patch.
