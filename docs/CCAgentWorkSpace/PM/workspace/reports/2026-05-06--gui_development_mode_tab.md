# Development Support Tab

Date: 2026-05-06
Role: PM local implementation
Repo root: `/Users/ncyu/Projects/TradeBot/srv`

Correction: this report supersedes the earlier "GUI Development Mode" naming.
The intended feature is a Development Support/status surface, not a GUI mode
that changes runtime behavior.

## Result

Implemented a Development Support setting and status page.

- Settings toggle is browser-local and no longer depends on
  `/api/v1/settings/development-mode`, preventing 404s when the running API
  process has not been restarted.
- Backend `GET/POST /api/v1/settings/development-mode` remains compatibility-only
  and maps to `OPENCLAW_DEVELOPMENT_SUPPORT_MODE` with legacy fallback.
- Added Settings toggle: `开发状态支持页 / Development Support`.
- Disabled state hides:
  - Overview `Global Mode Control` card.
  - Live page development-only global-mode note.
  - Support tab.
- Enabled state shows a `开发状态 Support` tab.
- New Support tab renders a V001-V063 global development status dashboard using
  compact cards aligned with the existing Global Mode Control card density.
  Each V0xx card has a distinct icon and shows landed/reserved/future status.

## Boundary

This is support visibility only:

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
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/static/test_replay_subtab_static_assets.py -q` -> 39 passed.
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/settings_routes.py` -> passed.
- `git diff --check` on touched GUI/settings/test files -> clean.

## Notes

No runtime deploy, rebuild, restart, DB write, live auth mutation, or risk/strategy edit was performed.
