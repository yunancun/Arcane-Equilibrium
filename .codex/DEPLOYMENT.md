# Codex Deployment

Last updated: 2026-04-28

## Goal

Mirror the useful parts of the existing Claude Code setup inside Codex without pretending the two systems are identical.

## Source systems

- Claude agent registry: `.claude/agents/*.md`
- Claude skill corpus: `.claude/skills/*/SKILL.md`

## Current inventory

- Claude agents: 18
- Claude skills: 24

## Codex deployment model

Codex does not use the same repo-local first-class agent registry format as Claude Code. For this repository, the deployment model is:

1. Agent role specs live in `.codex/agents/*.md`
2. Shared skill SSOT stays in `.claude/skills/*/SKILL.md`
3. Skill index for Codex lives in `.codex/skills/INDEX.md`
4. Comparative inventory report lives in `.codex/reports/`

## Default project role

For this repository, the default Codex entry role is `PM`.

That means new sessions should begin in planning / orchestration mode, then dispatch to other roles as needed.

## Dispatch model

When a Codex sub-agent is needed:

1. Pick a role file from `.codex/agents/`
2. Read the linked Claude source file in `.claude/agents/`
3. Read the referenced skill files in `.claude/skills/`
4. Spawn the sub-agent with the appropriate Codex type:
   - `worker` for implementation / test-writing / doc-writing
   - `explorer` for narrow read-only codebase investigation
   - `default` for broad audits, design, synthesis, or mixed repo + web work

See also:
- `.codex/AGENT_DISPATCH_PROTOCOL.md`

## Important differences vs Claude Code

- Codex sub-agent types are runtime-level (`default` / `explorer` / `worker`), not custom permanent personas
- Shared memory should be file-backed in `.codex/`, not assumed to persist implicitly
- Skills are reused from `.claude/skills/` rather than duplicated unless divergence is intentional

## Files created by this deployment

- `.codex/agents/INDEX.md`
- `.codex/agents/*.md`
- `.codex/skills/INDEX.md`
- `.codex/reports/2026-04-28--cc_agent_skill_inventory_and_codex_deployment.md`

## Operating rule

If Claude agent definitions evolve:

1. Update the relevant `.codex/agents/*.md`
2. Update `.codex/skills/INDEX.md` if skill ownership changes
3. Append a short note to `.codex/WORKLOG.md`
