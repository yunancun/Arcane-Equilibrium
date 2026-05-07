# Operator Handoff: AgentTodo MAG-080 Cutover Policy

Date: 2026-05-07
Status: DONE

## What changed

- Added the cutover policy for shadow -> soak -> demo/live_demo canary ->
  primary candidate -> primary sign-off.
- The policy lists control surfaces/flags, thresholds, rollback triggers,
  executor shadow rollback payload, and the operator checklist.

## Verification

- Mac `git diff --check` passed.
- Linux `trade-core` temp-worktree `git diff --check` passed.

## Boundary

- Policy only.
- No runtime flag, rebuild, restart, deploy, DB write, live auth, cloud call,
  runtime submit path, or trading authority change.

## AgentTodo position

- MAG-080 is closed.
- Next AgentTodo item: MAG-081 runtime risk review for canary flags and
  rollback.
