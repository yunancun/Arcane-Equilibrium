# W-AUDIT-7 F-system-mode-confirm Operator Brief

Date: 2026-05-09
Status: SOURCE/TEST PARTIAL

## Result

`tab-system.html` now has a `live_reserved`-only confirmation guard:

- confirm button disabled for 5s;
- single click after countdown does not submit;
- operator must hold the confirm button for 1.2s to submit the existing mode
  change request.

## Verification

- Static pytest: 5 passed.
- `git diff --check` passed.
- Edge headless smoke passed on a temporary static server with stubbed backend
  calls.

No backend restart, deploy, live auth mutation, strategy/risk mutation, or
true-live API action was performed.
