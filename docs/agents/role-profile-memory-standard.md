# Role Profile And Memory Standard

Purpose: keep every repo role sharp without turning agent files into a second
README or TODO. This standard applies to `docs/CCAgentWorkSpace/*/profile.md`
and `docs/CCAgentWorkSpace/*/memory.md`.

## Source Split

| Content type | Authority |
|---|---|
| Stable role identity, boundary, activation, deliverable standard | `profile.md` |
| Durable role lessons, recurring mistakes, operator preference | `memory.md` |
| Current active queue, blockers, runtime evidence, schedules | `TODO.md` |
| Stable project shape, architecture entry, GUI/scripts map | `README.md` |
| Detailed evidence and sign-off records | `workspace/reports/` and `Operator/` |
| Completed historical detail | `docs/archive/` |

## Profile Standard

A profile is a stable role charter. It should answer:

- What this role owns and refuses to own.
- When PM should activate or skip it.
- What inputs it must read before judging.
- What output format counts as a usable handoff.
- Which checks are mandatory and which are optional.
- When it must stop and escalate to PM/operator.

Avoid putting active project state in a profile. Examples that do not belong:

- current score, current test count, current runtime PID, current blocker
- long historical progress narrative
- sprint-specific TODOs
- stale report snapshots presented as current truth

Historical baselines are allowed only when clearly labeled as historical and
linked to the report that produced them. Active truth still comes from
`TODO.md`, latest role report, code, and runtime evidence.

## Memory Standard

A memory file is a durable lesson log, not an active ledger. Append only when
the lesson is likely to improve future judgment:

- a repeated mistake to avoid
- a proven operator preference
- a role-specific review heuristic
- a conflict-resolution decision that may recur
- a source-of-truth routing rule

Do not paste full reports, stack traces, long diffs, or daily progress. Put
those in `workspace/reports/` and link them from TODO or the relevant report.

When memory grows beyond roughly 1000 lines, new entries should be short
summary-only entries unless the operator explicitly asks for detailed memory.
Do not delete historical entries silently; if cleanup is needed, archive or
summarize with an explicit note.

## Conflict Handling

If profile or memory conflicts with newer operating memory, README, TODO, code,
or runtime evidence:

1. Trust the newer source or the source with direct evidence.
2. Say which source lost and why.
3. Keep the old memory as history unless the operator asked for cleanup.
4. Add a concise correction note if the same conflict is likely to recur.

## Startup Contract

For a role-specific task, read in this order unless the task prompt provides a
stricter route:

1. Repo operating memory: `CLAUDE.md` and, for Codex, `.codex/MEMORY.md`.
2. Stable project map: `README.md` and `docs/agents/context-loading.md`.
3. This role's `profile.md`.
4. This role's `memory.md`, interpreted as historical lessons.
5. The latest relevant `workspace/reports/` file when continuity matters.
6. `TODO.md` whenever current state, code, runtime, planning, review, or
   sign-off can affect the answer.

If in doubt, read `TODO.md`. Stale active state is more dangerous than one
extra context read in this repo.

## Update Contract

- Update `profile.md` only for stable role boundary or workflow changes.
- Update `memory.md` only for durable role lessons.
- Update `TODO.md` for active tasks, blockers, owners, evidence, and dates.
- Update `README.md` for stable project entry points and architecture map.
- Update `docs/agents/context-loading.md` when source routing changes.
