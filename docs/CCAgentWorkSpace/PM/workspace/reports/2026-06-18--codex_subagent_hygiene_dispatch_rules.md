# Codex Sub-Agent Hygiene Dispatch Rules

Date: 2026-06-18
Role: PM
Scope: `P3-SUB-AGENT-HYGIENE-SOP-CARGO-TEST-AFTER-ATOMIC`

## Result

Closed the TODO row as a governance/docs checkpoint.

The existing `docs/agents/sub-agent-hygiene-sop.md` already defined the Linux
`trade-core` cargo race boundary. This checkpoint makes that SOP a required
Codex dispatch field instead of a passive reference.

## Changes

- `.codex/SUBAGENT_EXECUTION_RULES.md` now requires `hygiene_sop`,
  `verification_surface`, and `linux_write_policy` for delegated work touching
  Rust, Cargo, Linux `trade-core`, PG, deploy, service restart, or runtime
  verification.
- `.codex/AGENT_DISPATCH_PROTOCOL.md` mirrors the same required dispatch fields
  and restates that delegated roles must not run Linux cargo.
- `.codex/MEMORY.md` and `docs/agents/context-loading.md` now route future
  Codex sessions to the hygiene SOP before dispatching these task classes.
- `docs/agents/sub-agent-hygiene-sop.md` now records the Codex dispatch mirror.
- `TODO.md` v196 removes the completed SOP cargo-test row from §7; the separate
  `P3-OPS-4-PG-DUMP-EVENT-EXTEND` debt remains.

## Boundary

Docs/governance only.

No source code change, no CI, no deploy/rebuild/restart, no runtime or DB
mutation, no auth/risk/order/trading mutation, no credential change, and no
real Bybit call.
