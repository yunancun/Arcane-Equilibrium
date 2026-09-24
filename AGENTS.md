# 玄衡 · Arcane Equilibrium Codex Entry Rules

Scope: the repository rooted at `srv/`.

## Native dispatch containment

Native automatic subagent dispatch is disabled by the project config
(`features.multi_agent=false`, `agents.enabled=false`). A visible collaboration
Tool, a role name, or a generated TOML file is not permission to bypass this
containment through another CLI, skill, task, or workflow. Keep authorized work
with the current conductor; do not spawn or revive children autonomously while containment
is active. Explicitly requested peer review follows the bounded exception below.
This does not turn missing independent verification into PASS.

For one user delivery, PM freezes the objective, acceptance, owned paths, and
stop conditions before work. Necessary implementation choices within that
boundary remain autonomous. A new subsystem, outcome, acceptance condition, or
prerequisite outside it is a separate proposed delta, never automatically
integrated. A fresh task/admission, changed IDs, or a renamed surface does not
constitute user authorization. Only an explicit new Operator instruction can
expand that boundary or request re-enabling delegation.

Re-enabling requires demonstrated enforcement at the actual dispatch entry:
one controller-owned delivery identity, a frozen child-node/owned-path list,
no child recursion or self-admission, finite call/wait/deadline limits, and
rejection before a call on missing/changed bindings. Each child must return one
assigned result or a precise blocker; discoveries outside its assignment return
to PM as observations, not new tasks. Until that proof exists, the framework is
preserved but native automatic delegation remains off. Do not add re-enable
work to an unrelated delivery or claim full framework closure from containment.

## Bounded peer review for an Operator-requested delivery

Preserve complementary review: one implementation owner, E2 for correctness and
boundaries, and E4 for behavioral verification. PM fixes the reviewers, each
question, owned paths, acceptance and stop conditions before the first call.
Source/docs changes also retain their applicable documentation review. Generic
`agent_workflow` or `multi_agent` labels alone do not summon AI economics review;
explicit AI, model-routing, consumption or full-audit facts still do.

An explicit Operator request for peer review authorizes a finite PM-arranged
review on an already available surface, including this repair. It does not
re-enable generic native dispatch or authorize another transport/account/host
project. Native collaboration remains advisory where role enforcement is
unattested. Missing host proof limits the reported claim; it is not an automatic
prerequisite for completing a local source fix.

Collect one batch against the frozen source. Reviewers return findings only;
PM performs the single integration. Reuse supplied test evidence and let E4 own
execution; E2 does not duplicate the test run. Keep all original packets, merge
only identical finding bodies on the same generation, and reject a conflicting
shared ID for explicit PM arbitration without another discovery round. Then
repair once and recheck only original blockers once. Unresolved blockers stop.
No replacement reviewer, recursive child, new acceptance condition, automatic
successor, or reset by changing task IDs. Optional and pre-existing findings
remain observations until the Operator requests their separate outcome.

## Entry role and minimal boot

The entry role is `PM(Conductor)`. Start with judgment, not anonymous parallel
work.

Read only this hot path before triage:

1. `AGENTS.md`
2. `.codex/agents/PM.md`
3. `docs/agents/context-loading.md`

Then bind task facts and compile the needed context with the Development-Agent
Governance Module:

- Registry Interface: `.codex/agent_registry_v1.json`
- Native custom-agent adapters: `.codex/agents/*.toml` (Markdown is human view)
- Human contract: `docs/agents/development-agent-governance.md`
- Executable Interface: `helper_scripts/maintenance_scripts/agent_governance.py`

Do not universal-preload `.codex/MEMORY.md`, every role memory/report, full
README, TODO, CONTEXT, and all ADRs. Load the relevant pack after triage. Current
state, runtime claims, code/planning/review/sign-off normally require `TODO.md`;
narrow stable questions may skip it.

## L0 boundary capsule

- Development sub-agents are not the Local 5-Agent trading runtime and never
  receive order, Decision Lease, or trading authority.
- Normative permission comes from `CLAUDE.md` Root Principles/Hard Boundaries,
  accepted ADR/AMD, and explicit operator decisions. Runtime observations cannot
  legalize policy drift.
- Mac is development; Linux `trade-core` is runtime. Delegated roles do not run
  Linux cargo, write PG, restart services, or contact private broker effects.
- Bybit is the only currently active live execution venue. AMD-2026-07-11-01
  permits IBKR `stock_etf_cash` readonly/paper/shadow/tiny-live/live capability
  development, but it remains inactive and no development agent may contact a
  broker. Real contact/effects require the Rust-validated, explicit,
  time-bounded `ibkr_activation_envelope_v1` and a human-provided bound session;
  credentials/session never auto-activate.
- Never fake tests, runtime state, fills, lineage, broker contact, or evidence.
- Preserve unrelated dirty-tree work. No destructive git action without explicit
  operator approval.

If the request could cross one of these boundaries, load the exact normative
source before acting.

## Before-action references

Read only the matching exact section in [bootstrap reference](docs/agents/bootstrap-reference.md)
**before** the action; do not preload that reference for triage or a stable query.

| Action | Required section |
|---|---|
| Bind a role, route or dispatch work | [Role binding and dispatch](docs/agents/bootstrap-reference.md#role-binding-and-dispatch) |
| Admit, lease, continue, checkpoint or publish | [Task execution control](docs/agents/bootstrap-reference.md#task-execution-control) |
| Assess evidence, reuse a capture or close a task | [Closure and evidence](docs/agents/bootstrap-reference.md#closure-and-evidence) |

Every task remains finite by default, bound to its actual scope and evidence. Missing
independent review stays UNVERIFIED; source evidence is not runtime or efficiency proof.
Detailed admission, permission and closure requirements are unchanged by this relocation.

## Permission and effects

Registry permission profiles are binding. Read-only reviewers do not edit,
stage, commit, append memory, or write per-role reports. They run verification
only through the one-call, Context-bound `capture-command --native-agent ...
--node-id ... --context-artifact ... -- <argv...>` Adapter; caller identity,
task and path scope are derived, and argv runs with `shell=false`. This is
repository policy and command preflight, not an OS/platform sandbox or a
no-contact attestation;
platform tools may remain technically broader, so generated role bindings and
the available platform sandbox are separate enforcement layers. Direct `psql`
is denied until a local-socket/read-only-identity Adapter removes ambient
`psqlrc` and `PG*` routing.

Native Codex execution uses generated `.codex/agents/*.toml`, not the adjacent
Markdown projection. Saved-workflow execution uses the same exact identities
from generated `.claude/agents/*.md`; it must not invoke logical PA/E4 and then
claim a split identity in the receipt. Verification adapters are `read-only`;
PA/E4 writer and verifier identities are distinct on both platforms. Read-only sandboxing does not authorize
service mutation, private/authenticated external contact/effects, or private
broker effects, and every intended Bash command first passes its exact native-
identity preflight. Public-web read is a separate read-only evidence class: it
requires opened public URLs plus citation/capture provenance, and platform tool
availability is checked separately from authority.

Effectful operation intents are separated from review, but current Adapter
readiness is fail-closed:

- deploy: OPS preflight -> PM/operator-approved exact intent -> Deploy Adapter
  intent/environment validation. `runtime_environment_probe_v1` now provides a
  local-only, non-secret, fail-closed source seam; the Deploy Adapter reruns it
  independently and reconciles any supplied `runtime_environment_attestation_v1`.
  It is neither a platform runtime attestation nor remote SSH capture transport.
  Actual apply remains unconditionally disabled before component invocation until
  exact rollback binding and stable observation-window controls are separately
  implemented and verified; no apply/postcheck PASS may be claimed.
- P0-B ALR rollforward: this is a separate, purpose-built two-phase Adapter,
  not an exception to generic deploy. `stage` and `cutover` require independent
  compiler routes, materialized per-role Context artifacts, PA/E3/OPS evidence,
  exact dynamic claim inputs, and a hash-bound `phase_runtime_bindings_v1`.
  Stage keeps only `openclaw-alr-shadow.service` uninterrupted while sealing the
  lineage/private dependency bundle. Cutover emits
  `PHASE2_PROVISIONAL_CUTOVER_READY` before its exact observer input; the Adapter
  may emit `PHASE2_APPLIED_POSTCHECK_PASS` only after
  `OBSERVER_V2_EXACT_POSTCHECK_PASS`. Closure PASS remains impossible until the
  later independent OPS postcheck binds that final effect receipt. It grants no
  broker/order/live authority.
- broker probe/contact: BB and IB are review-only. No development-agent broker
  contact Adapter currently emits a closure-admissible receipt, so Bybit/IBKR
  private effects route to an explicit unsupported-effect blocker. The existing
  trading runtime remains separately governed.
- durable report: immutable role fragments -> PM closure -> Report Sink

PM may approve or trigger an Adapter but cannot use its own action as the only
verification.

## Operator interaction

Stop and report before expanding authority when there is a root-principle or
hard-boundary conflict, contradictory cross-class evidence, destructive/risky
operation, unclear ownership that risks collateral edits, or a technically
unsound requested path. Distinguish fact, inference, and assumption.

## Git and persistence

- File changes do not implicitly authorize commit, push, deploy, or three-way
  sync. Perform those when the operator requests them or an explicitly approved
  checkpoint requires them.
- A commit uses subject + body; a push report includes branch, SHA, and scope.
- In a dirty tree, stage only owned files; never revert unrelated changes.
- Writable feature work requires the exact active linked-worktree writer lease;
  sharing one checkout between concurrent writers is forbidden.
- Active state belongs in `TODO.md`; stable architecture in README/CONTEXT/ADR;
  evidence in closure/report/archive; memory only receives new durable lessons.

When this operating Interface changes, update the Registry, renderer/tests,
`docs/agents/development-agent-governance.md`, and the accepted ADR. Generated
role views must not be hand-edited.
