# Agent Context Loading

Purpose: bind the smallest exact Context that can support a truthful decision.
Canonical packs and elastic envelopes live in `.codex/agent_registry_v1.json`.
The reference is manual conditional reading, not compiler auto-acquisition.

## Conditional before-action pointers

| Predicate | Read before action |
|---|---|
| dispatch, admission, delegated writer | [`Dispatch, ownership, and independent review`](bootstrap-reference.md#dispatch-ownership-and-independent-review) |
| writer, lease, checkpoint, remote, persistence | [`Git, checkpoints, generated views, and persistence`](bootstrap-reference.md#git-checkpoints-generated-views-and-persistence) |
| read-only verifier, before its first command | [`Permission model and effect Adapters`](bootstrap-reference.md#permission-model-and-effect-adapters) |
| admission, writer lease, loop or continuation | [`Finite execution, admission, continuation, and no-delta`](bootstrap-reference.md#finite-execution-admission-continuation-and-no-delta) |
| runtime, broker, PG, deploy, service, external effect | [`Permission model and effect Adapters`](bootstrap-reference.md#permission-model-and-effect-adapters), [`Runtime, broker, and external-effect boundaries`](bootstrap-reference.md#runtime-broker-and-external-effect-boundaries), plus exact norm |
| closure, command reuse, telemetry claim | [`Closure evidence, command capture, reuse, and telemetry`](bootstrap-reference.md#closure-evidence-command-capture-reuse-and-telemetry) |
| material decision, uncertain authority, or escalation | [`Operator decisions, autonomy, and escalation`](bootstrap-reference.md#operator-decisions-autonomy-and-escalation) |
| Context budget/history/saved workflow | [`Context compiler, packs, budgets, and saved-workflow parity`](bootstrap-reference.md#context-compiler-packs-budgets-and-saved-workflow-parity) |
| docs placement or TODO update | [`Documentation placement and update routing`](bootstrap-reference.md#documentation-placement-and-update-routing) |

## Startup and capsule

Entry reads `AGENTS.md`, generated PM Adapter, and this router. Do not preload
all memories, reports, README, TODO, CONTEXT, ADRs, or inventories. Every task
instead preserves its objective/scope/acceptance/hard stops, risk and uncertainty,
source baseline, dirty and optional verification scope, direct interfaces,
relevant norm/ADR denial, current blocker/runtime freshness if claimed, prior
failure/dissent, claim inputs, and evidence contract. Missing required material is
`NEEDS_CONTEXT/UNVERIFIED`, not a summary substitution.

## Authority routing

| Need | Exact source |
|---|---|
| permission/product | relevant `CLAUDE.md`, accepted ADR/AMD, Operator decision |
| role/native/permission | Registry and generated role Adapter |
| current owner/blocker | `TODO.md` |
| implementation | direct code/schema/tests/callers |
| runtime/PG/process | timestamped allowlisted read-only observation |
| external rule | official source plus `verified_at` |
| docs placement | `docs/README.md` and document index |

Do not compare authority classes as if they were one scale: runtime never
legalizes policy. A digest proves record integrity, not producer authenticity.

## Packs and state surfaces

Registry selects `core`, `active_state`, `architecture`, `source_change`,
`runtime`, venue, ML, GUI, docs, and explicit history packs. `active_state`
retains the bounded S2E projection (including its exact `EMPTY` and direct-
dependency rules). There is **no `workflow_state` pack**. Only an explicit
`current_workflow_state` selects `TODO.md` exact H2
`## Workflow optimization physical queue（source-only）`, not `WORKFLOW_TODO.md`.
An explicit `current_s2e_state` retains the existing S2E projection, including
its exact `EMPTY` and direct-dependency rules.
The independent `docs` pack selects seven exact `docs/README.md` sections,
including Document Index rules. Stable conceptual queries select neither state
surface. Missing/duplicate/malformed selected headings fail closed; bulk history
never becomes fallback.

The selected bytes, task contract, Registry generation, and routed DAG bind the
Context artifact. Prompt words, task labels, summaries, or a later fragment do
not widen it. Existing runtime and high-uncertainty triggers remain intact.

## Budget and honesty

Plans separately report UTF-8/4 planned lower bounds, exact prompt bytes,
per-call/workflow caps, reserve, nodes, attempts, and retries. Preserve required
coverage; at cap split or escalate Context. Planned size is never actual tokens,
cost, latency, or host adoption. Formal closure remains required for every task;
low risk changes routing depth, not closure truth.
