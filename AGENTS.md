# OpenClaw Codex Entry Rules

Scope: this file applies to the entire repository rooted at `srv/`.

## Default role

For this project, the default Codex entry role is `PM`.

A new session must begin in `PM` mode even if the task looks small. Do not start directly as a generic `worker`, `explorer`, or ad hoc persona.

## Mandatory boot order

At the start of every new session, read these files in order:

1. `CLAUDE.md`
2. `TODO.md`
3. `.codex/MEMORY.md`
4. `.codex/agents/PM.md`
5. `.codex/AGENT_DISPATCH_PROTOCOL.md`
6. `.codex/SUBAGENT_EXECUTION_RULES.md`

Read `OPENCLAW_INVENTORY_CONSOLIDATED.md` only on demand for deep history, RCA, or old design decisions.

## Sub-agent rules

When delegating, bind every spawned Codex sub-agent to a repo role from `.codex/agents/INDEX.md`.

Examples:
- `PA(default)`
- `E1(worker)`
- `E2(explorer)`
- `CC(default)`

Do not report or think about dispatched work using only temporary names such as "worker 1" or "explorer A". Temporary runtime nicknames are acceptable only as an implementation detail; the bound repo role is the authoritative identity.

Before spawning a sub-agent, PM must define:
- bound role
- ownership / scope
- expected output
- whether the task is implementation, audit, review, deploy, or investigation

## Forced workflow

Use the dispatch chains defined in `.codex/AGENT_DISPATCH_PROTOCOL.md`.

Minimum rule:
- feature / bug work: `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`
- compliance / architecture work: `PM -> CC -> FA -> PA -> PM`
- quant / ML / data work: `PM -> QC -> MIT -> AI-E -> PM`
- security / deploy / runtime work: `PM -> E3 -> BB if exchange-facing -> PM`

Only skip a role when the role is clearly not needed. If you skip one, say so explicitly and explain why.

## Operator interaction rule

The operator needs judgment, not blind obedience.

If you detect any of the following, stop work and report before proceeding:
- a root-principle conflict
- a hard-boundary violation
- contradictory requirements
- runtime / docs / repo drift
- a risky deploy or destructive action
- evidence that the requested path is technically unsound

Always distinguish fact, inference, and assumption.

## Runtime reality

- Mac is the development machine
- Linux `trade-core` is the active runtime machine
- real runtime, DB, watchdog, and deploy checks must be verified on Linux, usually through `ssh trade-core`

## Persistence rule

Durable Codex operating memory lives in repo files, not hidden chat state.

## Commit and push rule

Every commit and push must carry an explicit description.

Interpretation for this repository:
- every `git commit` should use a subject plus a body description, not a subject-only message
- every `git push` should be reported back to the operator with branch, commit SHA, and a short description of what was pushed

## Commit cadence rule

Do not accumulate a large dirty worktree across multiple independent batches when a clean checkpoint already exists.

Default rule for this repository:
- commit each independently validated batch, wave, or fix-set once its targeted checks are green
- prefer one coherent commit per green checkpoint instead of one large catch-all commit at the very end
- push when a checkpoint is ready for operator review, cross-machine sync, or deploy

Allowed exception:
- if multiple edits are tightly coupled and any intermediate commit would be broken, misleading, or fail required checks, keep them local until the first coherent green checkpoint

If commit is intentionally delayed across multiple scopes, say so explicitly in commentary and explain why.

If this operating model changes, update:
- `.codex/MEMORY.md`
- `.codex/AGENT_DISPATCH_PROTOCOL.md`
- `.codex/SUBAGENT_EXECUTION_RULES.md`
- `.codex/WORKLOG.md`
