# Role Profile, Closure, And Memory Standard

Canonical role Interface: `.codex/agent_registry_v1.json`
Design: `docs/agents/development-agent-governance.md`

## Source split

| Content | Authority |
|---|---|
| Stable role activation, capability, permission, output | Registry |
| Claude/Codex/profile role text | generated Adapter; never hand-edit |
| Domain review depth | referenced role skill/charter Implementation |
| Current queue/blocker/runtime claim | `TODO.md` + fresh evidence |
| One task's outcome/evidence/dissent | `closure_packet_v1` / Report Sink projection |
| New durable recurring lesson | role/global memory after PM promotion |
| Historical detail | reports/archive, on demand |

`docs/CCAgentWorkSpace/*/profile.md` remains for human navigation but is generated
from Registry. It is not a fourth authority. Run:

```bash
python3 helper_scripts/maintenance_scripts/agent_governance.py render --check
```

## Memory promotion

Memory is a durable lesson index, not a task ledger. Promote only when a closure
proves a lesson likely to change future judgment:

- repeated mistake and proven prevention
- stable operator preference
- recurring role heuristic
- authority/source routing rule
- conflict resolution likely to recur

Do not append daily progress, test counts, runtime PID, current blocker, full
report, diff, stack trace, or repeated boundary boilerplate. Those belong in
TODO/closure/report/archive.

Before promotion, deduplicate against the existing lesson. If superseded, record
an evolution pointer instead of copying both full narratives. Large historical
memory remains searchable but is never universal preload. New memory should use
small topical shards/indexes; hot operating memory targets roughly 300 lines.

## Report/closure behavior

Reviewers return immutable structured fragments. They do not write a report and
append memory merely because they reached a conclusion. PM may project one
durable task closure through `report_sink_v1` when future audit/handoff needs it.

The projection preserves:

- source/runtime/external evidence hashes and freshness
- facts/inferences/assumptions
- gate dissent and unresolved coverage
- checks as EXECUTED/REUSED/SKIPPED/FAILED
- skipped roles with reason/residual risk/owner
- measured consumption or unavailable reason

Identical input should produce a byte-stable projection. Operator-facing summary
is a view of the same closure, not a second authority.

## Historical files

Existing `memory.md` and per-role reports are retained as history. Their presence
does not require startup reads or continued per-task growth. When cleanup is
needed, archive mechanically with a pointer; do not silently delete evidence.

## Conflict handling

Role/profile/memory cannot override Registry permissions, normative policy,
current TODO, direct source, or fresh runtime evidence. Use the typed authority
matrix; do not apply a total-order winner across classes. Mark DRIFT/CONFLICT and
preserve both claims in closure.
