# AgentTodo MAG-080 Cutover Policy

Date: 2026-05-07
Owner: PM-local execution
Status: DONE

## Scope

Define the shadow -> canary -> primary cutover policy without changing runtime
flags or granting trading authority.

## Implementation

- Added
  `docs/architecture/multi_agent_rework_2026-05-05/2026-05-07--mag080_cutover_policy.md`.
- Defined:
  - Stage 0 baseline shadow.
  - Stage 1 shadow soak.
  - Stage 2 demo/live_demo canary.
  - Stage 3 primary candidate.
  - Stage 4 primary sign-off.
- Included exact control surfaces/flags, thresholds, rollback triggers, executor
  shadow rollback payload, and operator checklist.

## Verification

- Mac:
  - `git diff --check`
- Linux `trade-core` temp worktree:
  - same diff check

## Boundary

- Policy only.
- No runtime flag change.
- No rebuild, restart, deploy, DB write, live auth, cloud call, runtime submit
  path, or trading authority change.

## Next

M8 continues with MAG-081 runtime risk review for canary flags and rollback.
