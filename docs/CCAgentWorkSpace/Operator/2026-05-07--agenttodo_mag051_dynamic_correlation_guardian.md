# AgentTodo MAG-051 Dynamic Correlation Guardian Operator Report

Date: 2026-05-07
Status: DONE

Completed MAG-051.

What changed:

- Removed Guardian's static BTC/ETH-only correlation authority.
- Added dynamic correlation snapshot ingestion through provider/update API.
- Added hard reject for any active same-direction pair over the configured
  dynamic correlation threshold.
- Added safe fallback `MODIFIED` verdict for missing/stale/incomplete
  same-direction correlation evidence.
- Added soft correlation `MODIFIED` verdict with size cap.
- Persisted correlation metadata and reason codes on Guardian verdicts,
  including insufficient-data and hedge-evidence paths.
- Updated Guardian unit/integration tests.

What did not change:

- No rebuild/restart/deploy.
- No DB migration apply or DB write.
- No feature flag flip.
- No live auth or trading mode change.
- No strategy/risk runtime config mutation.

Next AgentTodo item: MAG-052 add P2 risk modification output to GuardianVerdict.

Verification passed on Mac and Linux temp worktree:

- Mac targeted Guardian pytest 69/0
- Linux targeted Guardian pytest 69/0
- Mac/Linux py_compile passed
- Mac/Linux `git diff --check` passed
