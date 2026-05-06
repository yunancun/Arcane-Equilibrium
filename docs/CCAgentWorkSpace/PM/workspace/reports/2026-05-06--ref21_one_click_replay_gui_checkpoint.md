# REF-21 One-Click Replay GUI Checkpoint

**Date:** 2026-05-06  
**Owner:** PM  
**Status:** GUI wired to P0-REF21-6a full-chain run orchestration

## Summary

Replay's default operator path now matches the REF-21 development pain point:
after strategy/risk edits, the user can select a window and start a
multi-symbol, multi-strategy replay run from the Replay tab.

The Advanced panel remains intact for manifest, fixture, experiment, run, and
finalize workflows.

## Implemented

- Default Quick panel renamed to `One-Click Replay`.
- Default window changed from 24h to 7d.
- Single-symbol/single-strategy quick form replaced with:
  - universe preset: current scanner snapshot / pinned symbols / custom symbols
  - engine snapshot: demo / live simulation-only snapshot
  - max symbols cap
  - strategy checkboxes for the five REF-21 strategies
- One-Click button now calls `POST /api/v1/replay/full-chain/run`.
- Result summary shows symbols, strategies, event count, subprocess run ids,
  and warnings returned by the full-chain route.
- UI labels include `SIMULATION ONLY`, `S2 public market data`, and
  `scanner universe snapshot`.

## Verification

Mac:

```text
node --check \
  program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/app-paper.js
=> passed

python3 -m pytest \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/static/test_replay_subtab_static_assets.py -q
=> 43 passed

python3 -m pytest \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_bybit_public_client.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_full_chain_routes.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_full_chain_run_routes.py -q
=> 16 passed

git diff --check
=> passed
```

## Boundary

This closes the practical One-Click UI wiring over P0-REF21-6a. It does not
close P0-REF21-6b: true historical scanner timeline replay still requires
ScannerCore extraction, historical symbol universe snapshots, and edge snapshot
time gating.
