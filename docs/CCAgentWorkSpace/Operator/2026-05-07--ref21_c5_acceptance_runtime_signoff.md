# REF-21 C5 Acceptance And Runtime Sign-Off

**Date:** 2026-05-07  
**Owner:** PM  
**Status:** Conditional sign-off for one-click full-chain replay as a
development sandbox.

REF-21 Replay is now usable for fast strategy/program iteration: choose a
historical window in the Replay tab, run the one-click full-chain replay, inspect
the preflight fidelity cells, then read fee-net bps and miss/reject counts from
the report.

Approved use:

- compressing development feedback after strategy or parameter edits,
- checking scanner-to-strategy-to-risk-to-exit behavior over a selected window,
- reading fee-aware development-sandbox metrics,
- giving ML/Dream read-only advisory ranking input.

Not approved:

- automatic demo/live/live_demo parameter mutation,
- claiming S1-calibrated quality when recorder coverage thresholds fail,
- fabricating old BBO/orderbook history for windows before local recorder data,
- treating replay alone as live promotion proof.

Current remaining S1-calibration work:

1. deterministic partial-fill modeling from orderbook depth,
2. latency q50/q90 modeling,
3. baseline-vs-candidate comparison,
4. balance-curve and bootstrap run bands,
5. recorder maturity / retention policy.

Operator runbook:

- `docs/runbooks/ref21_replay_operator_runbook.md`

C2-C4 checkpoint commits:

- `9ba6ebc6` recorder coverage preflight,
- `925d3017` replay report analytics,
- `0eda6005` read-only advisory ranking.

Verification:

- Mac targeted replay suite: 59 passed.
- Linux `trade-core` targeted replay suite at `0eda6005`: 59 passed.
- Linux API reloaded with `--api-only --keep-auth`, API parent PID `2467045`.
- Route probes:
  - `/api/v1/replay/full-chain/coverage` GET -> 405,
  - `/api/v1/replay/advisory/rank` GET -> 405,
  - `/api/v1/replay/report/example` GET -> 401.
