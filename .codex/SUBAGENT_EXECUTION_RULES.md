# Codex Sub-Agent Execution Rules

Last updated: 2026-06-18

## Purpose

Harden the PM-first dispatch model so Codex does not fall back to anonymous or temporary sub-agent naming when working in this repository.

## Core rule

Every Codex sub-agent dispatched in this repository must have:
- a bound repo role from `.codex/agents/INDEX.md`
- a Codex runtime type (`default`, `explorer`, or `worker`)
- explicit ownership
- an explicit deliverable

The repo role is the authoritative identity. The runtime type is only the execution substrate.

## Required dispatch record

Before or at spawn time, PM must define all of the following:
- `bound_role`: one of `A3`, `AI-E`, `BB`, `CC`, `E1`, `E1a`, `E2`, `E3`, `E4`, `E5`, `FA`, `MIT`, `PA`, `PM`, `QA`, `QC`, `R4`, `TW`
- `codex_type`: `default`, `explorer`, or `worker`
- `scope_owner`: the files, module, or responsibility owned by that role
- `task_shape`: implementation, review, audit, deploy, investigation, synthesis, or test
- `expected_output`: patch, report, verdict, RCA, verification log, or deploy result

## Naming and reporting rule

Use the following notation in planning notes, commentary, and summaries:
- `PA(default)`
- `E1(worker)`
- `E2(explorer)`

Do not use only temporary labels such as:
- `worker 1`
- `explorer B`
- `subagent-alpha`

If the runtime or UI assigns a temporary nickname, map it back to the bound repo role immediately in the next update.

## Dispatch constraints

PM must not:
- spawn a generic sub-agent without binding it to a repo role
- merge implementation and adversarial review into the same role when separation matters
- skip PM triage and jump straight into anonymous parallel work
- describe the workflow as complete unless the bound roles and chain are clear

## Cargo and atomic runtime hygiene

For any delegated task that touches Rust, Cargo, Linux `trade-core`, PG,
deploy, service restart, or runtime verification paths, PM must attach the
mandatory hygiene source:

- `hygiene_sop`: `docs/agents/sub-agent-hygiene-sop.md`
- `verification_surface`: Mac source-test/check, Linux read-only probe, or
  PM/operator-owned atomic deploy path
- `linux_write_policy`: no Linux cargo, no PG write, no sudo, no restart unless
  the task is an explicit PM-supervised deploy action

Delegated E1/E2/E4 Rust work is not complete after an edit/build-only signal.
The role must report the focused Mac `cargo test` / `cargo check` /
`cargo clippy` command that validates the atomic unit, or explicitly state why
it was skipped and what PM must run before merge.

Sub-agents must not run `cargo build`, `cargo test`, or `cargo check` on Linux
`trade-core`. If Linux empirical evidence is required, limit it to read-only
`psql SELECT`, `ls`, `cat`, `tail`, `fuser`, process inspection, or approved
healthcheck probes. If a Linux build/restart is required, stop and return that
need to PM; PM decides whether to use `helper_scripts/build_then_restart_atomic.sh`.

## Forced chain reminder

- feature / bug work: `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`
- compliance / architecture work: `PM -> CC -> FA -> PA -> PM`
- quant / ML / data work: `PM -> QC -> MIT -> AI-E -> PM`
- security / deploy / runtime work: `PM -> E3 -> BB if exchange-facing -> PM`

If a chain is shortened, PM must say which role was skipped and why.

## Completion contract (mirror)

Sub-agent final status uses the four-state contract:
`DONE` / `DONE_WITH_CONCERNS` / `NEEDS_CONTEXT` / `BLOCKED`.
On `BLOCKED`, escalate by adding context, switching model, splitting the task,
or raising to the operator — no bare same-model retry. Saying "cannot do it"
is always acceptable. Canonical: `.claude/agents/PM.md`; this section only
mirrors the pointer.

## Operator safety rule

If a delegated role discovers:
- a hard-boundary conflict
- a root-principle violation
- a dangerous deploy path
- contradictory evidence
- unclear ownership that risks collateral edits

then the delegated role should stop and return the problem to PM instead of pushing through.

## Ledger rule

Significant dispatches should be summarized in `.codex/WORKLOG.md` with:
- date
- task
- dispatch chain
- key result or blocker

When the dispatch itself is operationally important or defines a reusable pattern, also add an entry to `.codex/DISPATCH_LEDGER.md`.

## Context and TODO rule

Delegated roles should receive only the context needed for their scope, but PM
must preserve source routing:
- active state and blockers come from `TODO.md`
- stable project context comes from `README.md`
- context routing comes from `docs/agents/context-loading.md`
- TODO edits must follow `docs/agents/todo-maintenance.md`
