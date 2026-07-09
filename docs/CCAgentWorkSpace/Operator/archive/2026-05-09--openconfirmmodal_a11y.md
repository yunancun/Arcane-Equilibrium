# OpenConfirmModal A11y Checkpoint

Date: 2026-05-09
Scope: source/test only
Runtime impact: no rebuild, no restart, no backend change, no live auth mutation

## Summary

This checkpoint closes `P2-AUDIT-VERIFY-6` / A3 NEW-1. The shared
`openConfirmModal` implementation and the legacy console implementation now
meet the expected dialog accessibility behavior.

## Changes

- `common.js` generic confirm modal now renders `role="dialog"`,
  `aria-modal="true"`, `aria-labelledby`, and `tabindex="-1"`.
- `common.js` supports Esc cancel, Tab/Shift+Tab focus loop, initial focus on
  cancel, handler cleanup, and previous-focus restore.
- `app.js` legacy confirm modal defensively sets the same dialog attributes and
  implements the same Esc/focus-trap/focus-restore behavior.
- Added `tests/structure/test_confirm_modal_a11y_static.py` to lock both paths.

## Verification

- `python3 -m pytest -q tests/structure/test_confirm_modal_a11y_static.py tests/structure/test_strategy_action_visual_isolation_static.py tests/structure/test_prompt_modal_static.py`
- `node --check program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/common.js`
- `node --check program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/app.js`
- `git diff --check`

Browser smoke was not run in this checkpoint because the current tool session
did not expose a callable in-app browser tool and local Playwright is not
installed. The change is covered by static source checks plus JavaScript syntax
validation.
