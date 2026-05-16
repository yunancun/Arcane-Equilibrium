# TODO Maintenance Standard

Purpose: keep `TODO.md` as the active dispatch queue, not a historical report
or a second memory file.

## Scope

`TODO.md` owns current work state:

- active P0/P1/P2 queue
- active blockers and gates
- current runtime facts that affect work
- near-term schedule and handoff commands
- links to reports, archives, ADRs, specs, and evidence

`TODO.md` does not own:

- full completed sprint ledgers
- long RCA narratives
- copied report bodies
- stable project overview
- architecture background that belongs in README/ADR/docs
- agent personality or workflow rules that belong in memory

## Required shape

Every active item should expose enough information for the next PM or agent to
act without rereading a full report:

| Field | Requirement |
|---|---|
| ID | Stable task id, never recycled for a different meaning |
| Status | One of `ACTIVE`, `BLOCKED`, `WAITING`, `DEFERRED`, `DONE`, or an existing emoji-equivalent with the same meaning |
| Priority | P0/P1/P2/P3 or the section that implies it |
| Owner chain | PM / PA / E1 / E2 / E4 / QA / specialist roles when known |
| Acceptance | Concrete exit condition, not "looks good" |
| Latest evidence | Timestamped source, command, report, commit, or healthcheck |
| Next action | The next executable step or explicit wait condition |

Compact tables are preferred for queues. Short paragraphs are acceptable for
cross-wave gates when a table would obscure dependency logic.

## Runtime evidence

Runtime numbers must include a collection timestamp or linked report. Examples:

- good: `2026-05-16 01:00 UTC watchdog: engine_alive=true`
- good: `healthcheck [69] PASS in report <path>`
- bad: `engine is healthy`
- bad: `recently passed`

If a runtime fact is older than seven days and not automatically revalidated,
refresh it, mark it stale, or move it out of active TODO.

## Passive waits

Every passive wait must have one of:

- a runnable healthcheck
- a scheduled review date
- a named external/operator action
- an explicit reason no automation is possible

Silent waits are not allowed.

## DONE lifecycle

DONE rows can remain in `TODO.md` only while they help immediate handoff. Move
completed detail to reports/archive once it is no longer operationally useful.

When archiving:

- keep a short active marker only if the closed item affects future gates
- link the archive/report
- preserve blocker decisions and no-revive / no-reopen constraints
- do not paste the report body into TODO

## Conflict handling

If TODO conflicts with README, memory, ADR, or runtime evidence:

1. Surface the conflict explicitly.
2. Prefer the newer verified source or the accepted ADR/governance doc,
   depending on the subject.
3. Update the stale source or add a cleanup TODO.
4. Do not average conflicting states into a vague compromise.

## Agent enforcement

Any agent modifying `TODO.md` must:

- read this file first
- preserve active blockers before deleting completed detail
- avoid adding long narrative unless it is needed for immediate dispatch
- link reports/archive instead of copying them
- run a quick self-check: can the next PM identify the next action in under
  one minute?

E2/PM review should reject TODO edits that hide blockers, omit acceptance
criteria, record runtime numbers without evidence, or turn TODO into a
historical ledger.
