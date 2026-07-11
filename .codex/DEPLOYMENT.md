# Codex Deployment

Last updated: 2026-07-11

## Goal

Expose the canonical Development-Agent Registry as native, least-privilege
Codex custom agents while keeping human and Claude projections synchronized.

## Source systems

- Canonical role registry: `.codex/agent_registry_v1.json`
- Native Codex custom agents: `.codex/agents/*.toml`
- Human role projections: `.codex/agents/*.md`
- Claude skill corpus: `.claude/skills/*/SKILL.md`

## Current inventory

- Registry roles: 20
- Native Codex identities: 22 (PA and E4 each split writer/verifier authority)

## Codex deployment model

Codex loads project custom agents from standalone TOML files. For this repository:

1. Git-root `AGENTS.md` is the Codex auto-load entry document for new sessions
2. `.codex/agents/*.toml` are the executable native custom-agent identities
3. Adjacent `.md` files are generated human views, not runtime personas
4. Shared skill SSOT stays in `.claude/skills/*/SKILL.md`
5. `.codex/agent_registry_v1.json` deterministically generates every adapter

## Default project role

For this repository, the default Codex entry role is `PM`.

That means new sessions should begin in planning / orchestration mode, then dispatch to other roles as needed.

## Dispatch model

When a Codex sub-agent is needed:

1. Require explicit uncertainty, then route to the Registry-derived exact
   `role + native_agent + node_class + permission` tuple.
2. Spawn only the linked native TOML identity from `.codex/agents/INDEX.md`.
3. Read only the admitted Context capsule and on-demand skills/evidence.
4. Preserve the TOML sandbox: verifiers are `read-only`; builders are
   `workspace-write` but remain bound by Registry permission and task ownership.
5. For conflict roles, never use an ambiguous identity: select
   `PA-design-writer` vs `PA-investigator`, or `E4-writer` vs `E4-verifier`.
6. Every read-only Bash command uses the role-exact `authorize-command` preflight;
   sandbox mode does not grant service/network/private-broker authority.

See also:
- `.codex/AGENT_DISPATCH_PROTOCOL.md`
- `.codex/SUBAGENT_EXECUTION_RULES.md`

## Important differences vs Claude Code

- Native TOML identity is executable; the Registry role remains governance SSOT
- `codex_type` is retained as a cross-platform execution hint, not intelligence
- Shared memory should be file-backed in `.codex/`, not assumed to persist implicitly
- Skills are reused from `.claude/skills/` rather than duplicated unless divergence is intentional

## Files created by this deployment

- `.codex/agents/INDEX.md`
- `.codex/config.toml`
- `.codex/agents/*.toml`
- `.codex/agents/*.md`
- `.codex/skills/INDEX.md`
- `.codex/reports/2026-04-28--cc_agent_skill_inventory_and_codex_deployment.md`

## Operating rule

If a role or permission evolves:

1. Update `.codex/agent_registry_v1.json` only.
2. Run `python3 helper_scripts/maintenance_scripts/agent_governance.py render`.
3. Require `render --check` and the governance structure tests before closure.

## Commit / push reporting rule

- Use commit messages with both a subject and a body description
- After each push, report the branch, commit SHA, and a short description to the operator
- Treat subject-only commit messages as incomplete for this repository
- Do not bundle multiple independent green checkpoints into one final catch-all commit unless there is a clear coupling reason
- Prefer committing at each validated checkpoint before cross-machine sync or deploy
