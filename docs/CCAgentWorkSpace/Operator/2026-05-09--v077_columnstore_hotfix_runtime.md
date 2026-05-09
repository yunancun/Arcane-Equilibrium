# V077 Columnstore Runtime Hotfix Brief

Date: 2026-05-09
Status: HOTFIX IN PROGRESS

## What Happened

The authorized rebuild/restart exposed a runtime migration issue: V077 tried to
add/validate a CHECK on `trading.fills`, but that hypertable has Timescale
columnstore enabled, and Timescale rejected that ALTER path.

V068-V076 applied. V077 did not apply.

## Fix

V077 now tries the CHECK first. If Timescale rejects that because of
columnstore, it installs a same-predicate trigger fallback for new
INSERT/UPDATE writes.

## Verification So Far

- V077 static pytest: 5 passed.
- `git diff --check`: passed.
- Linux PG `BEGIN ... ROLLBACK` dry-run: passed with the expected trigger
  fallback notice.

No live auth mutation, scanner authority change, Executor hard authority,
strategy/risk mutation, MAG-083/MAG-084 unlock, or true-live API action was
performed.
