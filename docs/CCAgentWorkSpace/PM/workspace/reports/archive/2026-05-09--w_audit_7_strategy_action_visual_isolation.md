# W-AUDIT-7 F-strategy-confirm Checkpoint

Date: 2026-05-09
Role: PM
Status: SOURCE/TEST PARTIAL

## Scope

This checkpoint closes the source/UI portion of F-strategy-confirm for the
Strategy, Paper, and Live tabs.

- Added shared action-risk CSS in `common.js`: warning, critical, destructive
  buttons plus risk-zone clusters.
- Extended `openConfirmModal()` to accept per-call modal metadata and confirm
  button classes.
- `tab-strategy.html` now visually separates Pause, Stop, and Delete into
  distinct risk zones.
- `tab-paper.html` now separates run, pause, stop, and Paper+Demo dual-stop
  controls; `sessionStopAll()` uses the shared custom confirm modal instead of
  native browser confirm.
- `tab-live.html` now groups Live Stop and Emergency Stop in a shutdown zone,
  marks close-all and row-close actions as destructive, and replaces native
  close-position confirms with custom modal confirms.
- Added static regression coverage for the shared CSS, modal extension, target
  tab markers, and absence of native `confirm()` in these three tabs.

## Verification

- `python3 -m pytest tests/structure/test_strategy_action_visual_isolation_static.py tests/structure/test_prompt_modal_static.py tests/structure/test_system_mode_confirm_static.py -q`
  -> 9 passed
- `node --check program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/common.js`
- `git diff --check`
- Edge headless smoke through a temporary static server with stubbed API data:
  - `tab-strategy.html`: 3 danger zones rendered, Stop/Delete buttons present.
  - `tab-paper.html`: 4 danger zones rendered, row close + dual-stop destructive controls present.
  - `tab-live.html`: shutdown zone rendered, row close + close-all + emergency controls present.
  - No page errors or console errors in the routed smoke.

The first static-server pass produced expected `/api/...` 404s before the smoke
was rerun with routed stub API payloads.

## Boundary

Source/test/static-browser only. No backend start beyond a temporary static file
server, no rebuild, restart, deploy, DB apply, live auth mutation, scanner
authority change, Executor hard authority, strategy/risk config mutation,
MAG-083/MAG-084 unlock, or true-live API action.

Dispatch note: repo PM chain was shortened locally because the operator did not
explicitly request sub-agents in this turn. PM handled implementation and E4-like
verification locally; no runtime/deploy roles were needed.

PM SIGN-OFF: APPROVED for this partial checkpoint.
