# GUI Development Mode Tab

Date: 2026-05-06
Role: PM local implementation
Repo root: `/Users/ncyu/Projects/TradeBot/srv`

## Result

Implemented a GUI-only Development Mode setting.

- Added authenticated `GET/POST /api/v1/settings/development-mode`.
- Added Settings toggle: `GUI Development Mode / GUI 开发模式`.
- Disabled state hides:
  - Overview `Global Mode Control` card.
  - Live page development-only global-mode note.
  - Development tab.
- Enabled state shows a new `开发 Dev` tab.
- New Development tab renders a V001-V063 migration dashboard using compact cards aligned with the existing Global Mode Control card density.

## Boundary

This is GUI visibility only:

- No trading mode change.
- No risk config change.
- No live authorization change.
- No engine runtime/restart action.
- No DB migration apply.
- No strategy parameter change.

## Dispatch

Repository-preferred feature chain is `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`.
No sub-agents were spawned because the active Codex tool rule only permits sub-agents when explicitly requested by the operator. PM performed local PA/E1/E2/E4/QA-style steps in one scoped patch.

## Verification

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_settings_paper_engine.py -q` -> 5 passed.
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/static/test_replay_subtab_static_assets.py -q` -> 38 passed.
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/settings_routes.py` -> passed.
- `git diff --check` on touched GUI/settings/test files -> clean.

## Notes

No runtime deploy, rebuild, restart, DB write, live auth mutation, or risk/strategy edit was performed.
