# AgentTodo MAG-082 24h Canary Validation Checklist

Date: 2026-05-07
Owner: PM-local E4-style validation design
Status: DONE

Dispatch note: AgentTodo marks MAG-082 as E4-owned, but this Codex turn did
not dispatch a sub-agent; PM performed a local validation-contract pass and
kept the scope to documentation/evidence design.

## Scope

Define the 24h canary evidence checklist needed before any M8 canary can feed
MAG-083 final release audit.

## Implementation

- Added
  `docs/architecture/multi_agent_rework_2026-05-05/2026-05-07--mag082_24h_canary_validation_checklist.md`.
- Defined the required window header, entry checks, evidence files, SQL
  templates, runtime health evidence, and PASS/WARN/FAIL criteria.
- Required every executable canary decision to reconstruct:
  StrategySignal -> StrategistDecision -> GuardianVerdict -> ExecutionPlan ->
  Decision Lease / idempotency -> ExecutionReport.
- Explicitly separated checklist completion from running a 24h canary.

## Verification

- Mac:
  - `git diff --check`
- Linux `trade-core` temp worktree:
  - same diff check

## Boundary

- Checklist only.
- No canary run.
- No runtime flag change.
- No rebuild, restart, deploy, DB write, live auth, cloud call, runtime submit
  path, or trading authority change.

## Next

M8 continues with MAG-083 final release audit, but MAG-083 should wait for an
operator-approved canary window to produce evidence against the MAG-082
checklist.
