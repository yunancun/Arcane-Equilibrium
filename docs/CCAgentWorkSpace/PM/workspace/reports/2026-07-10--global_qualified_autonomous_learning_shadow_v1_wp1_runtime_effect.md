# PM Runtime Effect - GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1 WP1

Date: 2026-07-10
State: `WP1_DONE_RUNTIME_ACCEPTED_WP2_ACTIVE`
Exact target: `7d1c247947f0fb6c139f8a0583c5e6ed6ae62c70`

## Accepted evidence

R4 was the only accepted disposable PostgreSQL attempt.  It passed canonical
operational, outcome-feedback, and health harnesses plus explicit equivalent
DEFER/replay and DB-clock heartbeat/skew probes.  All authority values were
false/zero.  Outer cleanup removed the PostgreSQL process, socket/temp roots,
and detached worktree; an independent residue audit was clear.

Linux then fetched the moving remote only for comparison and fast-forwarded
from `dbc6a936c` to the raw target SHA, never to the newer GUI tip.  There was
no migration, role, contract, Rust, exchange, API-method, credential, or
service-template change.  The existing private user unit was proven
byte-equivalent to the reviewed template except its source pin, atomically
repinned, and only `openclaw-alr-shadow.service` restarted.  Its PID changed
`2073347 -> 2381011`; engine `2203280`, API `3771536`, and watchdog `1040386`
kept the same process identities.

The immutable database checkpoint covers `430.582201s` from
`2026-07-10T14:36:40Z`.  Exactly one new session
`bed1cba0-2a5b-45e3-8103-3243c80fdfd5` existed.  Its latest checkpoint health
metric was 5.407501 seconds old and recorded attempts/emitted/suppressed
`87/13/74`, suppression ratio `0.8505747126`.  The preceding stale hour had
`740` health rows and `1,755,280` canonical bytes.  The target session wrote
`14` rows and `48,621` bytes, normalized to `117.0508 rows/hour` and
`406,509.14 bytes/hour`: ratios `0.1581768` and `0.2315922`, each below the
required half-rate.

Decision metrics recorded six attempts, five run rows, and one equivalent
suppression.  Feedback metrics recorded five attempts/persisted, zero
duplicates, and exact `15 artifacts + 15 provenance edges + 5 events = 35`
rows.  Direct run/feedback authority mismatches, derived cache, and retention
events were `0/0/0/0`.  Scanner INSERT, health UPDATE, and training-run DELETE
remained denied.  A transient untrained row had age `0s`, ingestion lag `0`,
and starvation false.

E3 independently re-ran the read-only acceptance and returned PASS.  The ALR
service then remained on PID `2381011`, `NRestarts=0`, for more than another
hour with suppression about `0.843`, memory/tasks within `512M/64`, and zero
warning-or-higher journal entries.

## Evidence integrity and boundary

R1 stopped on head drift before action.  R2 failed before fixtures and exposed
an inner-cleanup defect; the exact disposable cluster was stopped and removed.
R3 stopped before temp creation on an over-strict interpreter-path guard.  R4
fixed only that guard and passed.  The earlier unauthorized QA local-PG probe
remains retracted and was never reused.

An initial final evaluator sampled the still-running service about 4,249
seconds after restart and incorrectly applied the 420-second `60-120 attempts`
bound to its cumulative `867` attempts.  That result is retracted as a
floating-window tooling error.  Rebinding the query to the immutable database
checkpoint yielded the PASS values above; no runtime condition failed.

No exchange/API/MCP contact, order/probe, Decision Lease, Guardian/RiskConfig,
global Cost Gate, engine/API/watchdog signal, serving, promotion, `_latest`,
parameter apply, live/mainnet action, or protected-evidence deletion occurred.
WP1 is closed.  WP2 candidate-aware arbiter contract and fixture discovery is
the next active safe work.
