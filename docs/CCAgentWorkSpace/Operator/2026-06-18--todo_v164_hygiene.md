# TODO v164 Hygiene

PM SIGN-OFF: APPROVED

## Scope

- `TODO.md` masthead cleanup per `docs/agents/todo-maintenance.md`.
- `docs/CLAUDE_CHANGELOG.md` v161-v164 increment backfill.
- §5 stale-row correction for cold-audit items.

## Changes

- Compressed `TODO.md` header to current version/date/source pointer, active posture, section entry points, and history links.
- Moved v161-v163 long narrative out of TODO header into `docs/CLAUDE_CHANGELOG.md`.
- Removed duplicate stale `AUDIT-2026-06-14-SCHEMA-1` confirmed row; kept the fixed row.
- Updated `AUDIT-2026-06-14-AUTH-1`, `AUDIT-2026-06-14-PROFIT-1`, and `AUDIT-2026-06-14-DIRTY-FIX` to reflect deployed/healthcheck/true-table evidence.

## Validation

- `git diff --check -- TODO.md docs/CLAUDE_CHANGELOG.md` passed.
- `rg` check confirmed no remaining stale strings: `healthcheck 待建`, `operator commit/deploy gated`, `owed Linux 真 trading.fills`.
- No code, runtime, DB, auth, risk, order, or trading mutation.

## Remaining

- §5 still contains several DONE rows with operational handoff value; continue removing only when the next action is fully represented by report links or wait conditions.
