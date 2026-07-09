# W-AUDIT-7 F-30 Prompt Modal Checkpoint

Date: 2026-05-09
Role: PM
Status: SOURCE/TEST PARTIAL

## Scope

This checkpoint starts W-AUDIT-7 by removing native browser `prompt()` from the
learning and governance flows identified by F-30.

- Added shared `openPromptModal()` in `common.js`.
- Replaced learning experiment completion prompts with a textarea modal and a
  confidence-level select picker.
- Replaced governance audit approve/reject prompts with custom modal inputs.
- Replaced live-auth renewal/review prompts in the governance tab with custom
  modal inputs and tier select pickers.
- Added a static guard preventing native `prompt()` from returning in
  `app-learning.js`, `governance-tab.js`, and `tab-governance.html`.

## Verification

- `node --check .../static/common.js`
- `node --check .../static/app-learning.js`
- `node --check .../static/governance-tab.js`
- `python3 -m pytest tests/structure/test_prompt_modal_static.py -q`
  -> 2 passed
- Edge headless smoke through a temporary static server:
  - governance tier select modal rendered, defaulted to `1`, submitted `2`, and
    closed cleanly
  - learning required textarea modal showed required-field validation, accepted
    text, and closed cleanly on a 390x760 viewport
- `git diff --check`

The static-server governance page produced expected `/api/...` 404s because no
backend was started for this source-only browser smoke.

## Boundary

Source/test/static-browser only. No backend start beyond a temporary static file
server, no rebuild, restart, deploy, DB apply, live auth mutation, scanner
authority change, Executor hard authority, strategy/risk config mutation,
MAG-083/MAG-084 unlock, or true-live API action.

PM SIGN-OFF: APPROVED for this partial checkpoint.
