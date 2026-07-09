# Development Support Tab

Date: 2026-05-06
Status: source implemented and targeted tests green

Implemented a Development Support/status setting:

- Settings now has `开发状态支持页 / Development Support`.
- The toggle is browser-local and does not call `/api/v1/settings/development-mode`, so an old running API process will not cause a 404 for this switch.
- When disabled, Overview hides `Global Mode Control`, Live hides the dev-only global-mode note, and the Support tab is hidden.
- When enabled, `/console` shows `开发状态 Support` with V001-V063 development-status cards and distinct V0xx icons.

Verification:

- Settings endpoint tests: 5 passed.
- Static console/tab tests: 39 passed.
- `settings_routes.py` py_compile passed.
- Diff whitespace check passed.

Boundary: no runtime deploy/restart/rebuild, no DB write, no trading/risk/live-auth change.
