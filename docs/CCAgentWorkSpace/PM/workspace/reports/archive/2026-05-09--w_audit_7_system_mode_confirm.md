# W-AUDIT-7 F-system-mode-confirm Checkpoint

Date: 2026-05-09
Role: PM
Status: SOURCE/TEST PARTIAL

## Scope

This checkpoint closes the source/UI portion of F-system-mode-confirm for the
System tab.

- Added a `live_reserved`-only confirmation guard in `tab-system.html`.
- The confirm button is disabled for a 5s countdown when switching to
  `live_reserved`.
- After the countdown, a single click is rejected; the operator must hold the
  confirm button for 1.2s before the existing mode-change path runs.
- Other mode changes and Paper quick-action confirmation keep their existing
  click-to-confirm behavior.
- Added static structure coverage for countdown constants, live-only scoping,
  click rejection, pointer cancel paths, and keyboard hold/cancel support.

## Verification

- `python3 -m pytest tests/structure/test_system_mode_confirm_static.py tests/structure/test_prompt_modal_static.py -q`
  -> 5 passed
- `git diff --check`
- Edge headless smoke through a temporary static server:
  - `live_reserved` confirm initialized with the guard visible and the confirm
    button disabled for the countdown.
  - After 5s, the button entered hold-ready state.
  - A normal click left the modal open and did not call
    `/api/v1/input/config-change`.
  - A 1.2s hold submitted the existing mode-change request through a stubbed
    `/api/v1/input/config-change` and closed the modal.

The static-server page produced expected `/api/...` 404s because no backend was
started for this source-only browser smoke.

## Boundary

Source/test/static-browser only. No backend start beyond a temporary static file
server, no rebuild, restart, deploy, DB apply, live auth mutation, scanner
authority change, Executor hard authority, strategy/risk config mutation,
MAG-083/MAG-084 unlock, or true-live API action.

PM SIGN-OFF: APPROVED for this partial checkpoint.
