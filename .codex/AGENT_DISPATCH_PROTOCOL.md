# Codex Agent Dispatch Protocol

Last updated: 2026-04-28

## Purpose

Define how Codex should operate in this repository when a new session starts and when work needs to be delegated.

## Default entry role

For this project, the **default Codex entry role is `PM`**.

Meaning:
- a new Codex session should begin from the `PM` perspective
- the first job is to understand the user request, current repo state, and active plan
- only after that should work be done locally or dispatched to another role

Important boundary:
- this is a **project operating rule stored in the repo**
- it is enforced here through `AGENTS.md` at the git root plus the `.codex/` rule files
- it is not a guarantee that the Codex product itself will globally auto-switch personas outside this project context

## PM boot sequence

At session start, PM should read in this order:

1. `CLAUDE.md`
2. `TODO.md`
3. `.codex/MEMORY.md`
4. `.codex/agents/PM.md`
5. `.codex/SUBAGENT_EXECUTION_RULES.md`
6. On demand: `.codex/DEPLOYMENT.md`, `.codex/skills/INDEX.md`
7. On demand only: `OPENCLAW_INVENTORY_CONSOLIDATED.md`

## PM responsibilities

PM must:
- understand the user ask
- identify whether the task is planning, implementation, review, test, deploy, or audit
- decide whether to work locally or delegate
- keep work aligned with existing hard boundaries and workflow
- preserve minimal-scope commits and safe sync behavior

## Dispatch principles

PM should delegate only when it improves parallelism or separation of concerns.

Use local PM handling when:
- the task is small and blocking
- the result is needed immediately for the next step
- the work is mostly synthesis / planning / final judgment

Use sub-agents when:
- tasks are independent and can run in parallel
- implementation and review should be separated
- a narrow specialist role reduces confusion

## Required role binding

Every delegated task must declare:
- bound role
- codex type
- ownership
- deliverable

Use the role form `ROLE(codex_type)` in updates and summaries.

Do not use only temporary runtime labels such as `worker 1` as the authoritative identity.

## Codex type mapping

| Role family | Codex type | Typical roles |
|---|---|---|
| planning / audit / synthesis | `default` | `PM`, `PA`, `FA`, `CC`, `QC`, `BB`, `AI-E`, `MIT`, `A3` |
| read-only targeted investigation | `explorer` | `E2`, `E3`, `E5`, `R4` |
| implementation / execution | `worker` | `E1`, `E1a`, `E4`, `QA`, `TW` |

## Recommended dispatch chains

### Feature / bug work

1. `PM` triage
2. `PA` if design is unclear or risky
3. `E1` or `E1a` for implementation
4. `E2` for adversarial review
5. `E4` for regression / test execution
6. `QA` if end-to-end acceptance matters
7. `PM` final integration / sign-off

### Compliance / policy / architecture

1. `PM` triage
2. `CC` for root-principle / hard-boundary review
3. `FA` for functional gap audit
4. `PA` for technical design implications
5. `PM` decision

### Quant / ML / data work

1. `PM` triage
2. `QC` for alpha / strategy / validation judgment
3. `MIT` for data / feature / CV / schema rigor
4. `AI-E` if model-cost / routing / token economics matter
5. `PM` decision

### Security / deploy / runtime

1. `PM` triage
2. `E3` for security review
3. `BB` for Bybit-side compatibility if exchange-facing
4. `PM` performs or supervises deploy

## Deploy rule

Deploy requests should still start with `PM`, even if the final action is operational:
- confirm scope
- confirm branch / commit / host state
- decide whether a deploy is warranted
- then perform the deploy or delegate narrow checks

## Documentation rule

If PM changes the operating pattern:
- update `.codex/MEMORY.md`
- update this file
- update `.codex/SUBAGENT_EXECUTION_RULES.md`
- update `.codex/DISPATCH_LEDGER.md` when the dispatch pattern or role usage is materially relevant
- append `.codex/WORKLOG.md`
