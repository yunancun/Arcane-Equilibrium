# GUI Development Mode Tab

Date: 2026-05-06
Status: source implemented and targeted tests green

Implemented a GUI-only Development Mode setting:

- Settings now has `GUI Development Mode / GUI 开发模式`.
- When disabled, Overview hides `Global Mode Control`, Live hides the dev-only global-mode note, and the Development tab is hidden.
- When enabled, `/console` shows a new `开发 Dev` tab with V001-V063 migration cards.

Verification:

- Settings endpoint tests: 5 passed.
- Static console/tab tests: 38 passed.
- `settings_routes.py` py_compile passed.
- Diff whitespace check passed.

Boundary: no runtime deploy/restart/rebuild, no DB write, no trading/risk/live-auth change.
