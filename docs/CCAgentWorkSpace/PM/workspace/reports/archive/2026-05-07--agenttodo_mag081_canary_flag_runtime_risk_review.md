# AgentTodo MAG-081 Canary Flag Runtime Risk Review

Date: 2026-05-07
Owner: PM-local E3-style review
Status: DONE

Dispatch note: AgentTodo marks MAG-081 as E3-owned, but this Codex turn did
not dispatch a sub-agent; PM performed a local security/runtime-risk review and
kept the scope to documentation/evidence.

## Scope

Review whether any M8 canary flag or rollback flag can accidentally enable live
autonomy without approval.

## Implementation

- Added
  `docs/architecture/multi_agent_rework_2026-05-05/2026-05-07--mag081_canary_flag_runtime_risk_review.md`.
- Reviewed Agent event-store, Agent Spine client/mode metadata, scanner
  authority, Decision Lease router, ExecutorAgent shadow mode, Mainnet opt-in,
  signed live authorization, OpenClaw active routes, H-state, cost-edge, and
  supervisor cloud policy.
- Verdict: no reviewed single flag can enable true live autonomy without the
  required operator/live-auth/Rust/governance conjunction.
- Highest-risk surface: `executor.shadow_mode=false`; live use remains behind
  Operator role, `live_reserved`, Mainnet env when applicable, live secret
  slot, and valid signed authorization.

## Verification

- Mac:
  - `git diff --check`
- Linux `trade-core` temp worktree:
  - same diff check

## Boundary

- Risk review only.
- No runtime flag change.
- No rebuild, restart, deploy, DB write, live auth, cloud call, runtime submit
  path, or trading authority change.

## Next

M8 continues with MAG-082 24h canary validation checklist.
