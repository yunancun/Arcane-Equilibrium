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
- version-increment narratives (the per-version "vN 增量: …" change paragraphs) —
  these belong in `docs/CLAUDE_CHANGELOG.md`, not the TODO header (see Header /
  masthead)

## Header / masthead

The TODO header is a compact masthead, not a change log. Keep it to a few
scannable lines:

- current version number + date
- source HEAD commit + a one-line runtime pointer (runtime detail lives in the
  §0 health section, not the header)
- a one-line current-mainline/posture pointer into the active sections (which
  blocker is in §1, where the active dispatch queue is)
- links: the version-increment changelog + the latest dated archive

Version-increment narratives — the per-version "vN 增量: …" paragraphs
describing what changed — do NOT live in the TODO header. They go to
`docs/CLAUDE_CHANGELOG.md` ("TODO Version-Increment Log"; a dev-history
changelog new sessions do not need to read). When bumping the TODO version:

1. Append the new version's increment narrative to `docs/CLAUDE_CHANGELOG.md`
   (newest-first).
2. Keep the masthead to current version + pointers only — do not accumulate
   increment paragraphs.
3. Ensure the active STATE the increment describes is reflected in the
   structured sections (§1 blockers / §2 banner / §4 matrix / §6 queue). The
   increment is history; the structured sections are the source of active
   state.

Rationale: increment paragraphs crammed into the header are change-log
narrative (which TODO does not own, per Scope), grow into a dense unreadable
wall, and duplicate the structured sections. A masthead that fits in a few
lines lets the next agent orient in seconds.

## Required shape

Every active item should expose enough information for the next PM or agent to
act without rereading a full report:

| Field | Requirement |
|---|---|
| ID | Stable task id, never recycled for a different meaning |
| Status | One of `ACTIVE`, `BLOCKED`, `WAITING`, `DEFERRED`, `DONE`, or an existing emoji-equivalent with the same meaning |
| Priority | P0/P1/P2/P3 or the section that implies it |
| Owner path | Hybrid DAG 已觸發的 current owner / verifier / Adapter；不得預填固定全角色 chain |
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

1. Classify each claim: TODO owns `active_work_state`; accepted ADR/policy owns
   `normative_policy`; timestamped host evidence owns `runtime_observation`.
2. Compare freshness/strength only within the same class.
3. Across classes, preserve both claims and mark `DRIFT/CONFLICT`; runtime never
   legalizes a normative denial.
4. Repair the stale pointer inside its own class or add a cleanup TODO. Never
   average conflicting states into a vague compromise.

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
