# Fresh Invocation-Window Source Preflight Blocked

Status: BLOCKED_BY_LOSS_CONTROL
Candidate: `grid_trading|ETHUSDT|Buy`

PM attempted only the corrected no-order dry-run for the fresh invocation-window gate. It did not acquire a lease, did not call Bybit, did not fetch a public quote, and did not submit/cancel/modify any order.

- Session loop state sha256: `e6724c79a45b187e1c020065cf6c445950bafcf01daf923e9e73e94afbad7a2d`
- Dry-run sha256: `148deaecd3e7423d1ecf207c5d8f715e48f6773e95f676500e1e05299237e6b6`
- Dry-run status: `CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW_SOURCE_NOT_READY`

The blocker is source/input freshness, not operator permission: stale current-candidate envelope plus a gate/sizing packet mismatch. E3 blocked the `--run`; BB said public market-data GET scope is acceptable in principle but also blocked `--run` until inputs are refreshed and dry-run ready.

Next blocker: `P0-CURRENT-CANDIDATE-FRESH-INVOCATION-WINDOW-SOURCE-INPUT-REFRESH-GATE`. The next step is source/input refresh and another corrected dry-run before any active lease/BBO same-window gate.
