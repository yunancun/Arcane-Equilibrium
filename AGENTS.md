# 玄衡 · Arcane Equilibrium Codex Entry Rules

Scope: the repository rooted at `srv/`.

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

## Role binding and dispatch

Every delegated task declares:

- `bound_role` from the Registry
- exact pre-spawn `native_agent`, `work|verification` node class, and permission
- Codex runtime type
- owned scope
- task shape, risk, and explicit `low|medium|high|unknown` uncertainty
- task-owned `dirty_scope` and any optional read-only `verification_scope`
- expected fragment/patch
- acceptance and hard stops
- exact `claim_inputs` for any prior/evidence digest that may affect a verdict
- context digest or explicit missing context

Use `ROLE(type)` in updates. Runtime nicknames are not authoritative identities.

Routing is a hybrid risk-DAG from the Dispatch Interface, not a fixed all-role
ceremony. Hard edges are fact-triggered: source implementation needs independent
E2 then E4. Mixed GUI/backend work owns disjoint frontend/backend scopes through
the fixed E1-backend -> E1a-frontend sequence (shared-worktree writers never
run in one wave), and E2 cannot start until both builders finish; authority/security,
runtime/operations, venue, quant/ML, and E2E
claims add their true owners. Other roles are admitted only when expected
decision gain exceeds token/time/opportunity cost after preserving the quality
reserve. Missing uncertainty fails before routing; it is never silently read as
low. Every skip records reason and residual risk.

Every PM-added adaptive node is recorded in closure
`dispatch.admitted_role_nodes` with node ID, role, work/verification class, and
reason, plus sorted predecessor `requires`, node-owned `path_scope`, and whether
its result binds a top-level role fragment or a typed nested payload. Once
admitted it is mandatory; PM cannot omit it, rewrite its edge, or hide dissent.

`verification_scope` is an optional canonical, sorted/unique list of literal,
safe repository-relative paths. A read-only verifier command capture uses it
only when routed node `path_scope` is empty, and before falling back to
`dirty_scope`. It is only a capture-generation and trusted-replay boundary; it
never grants writer ownership, mutation authority, or ACL permission, and it
does not replace writer `dirty_scope` or whole-repository generation checks.

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

## Closure and evidence

One task has one `closure_packet_v1`; `work_status`, `gate_verdict`, and
`disposition` are separate. `DONE + FAIL` is valid. Missing evidence, stale
runtime proof, unresolved hard-gate dissent, exhausted budget, or skipped
coverage cannot become PASS.

Evidence trust has three explicit tiers:

- `LOCAL_REPRODUCIBLE`: exact repository/command bytes can be recaptured locally.
- `ORCHESTRATOR_BOUND`: the controller records the requested task/context/role,
  retries, and exact returned result. These packet-local call/wave receipts are
  structural lineage only; they cannot authenticate their own execution.
- `PLATFORM_OR_EXTERNAL_ATTESTED`: a platform/provider/external verifier attests
  runtime, external-policy/outcome, or actual-usage facts.

A canonical self-digest proves record integrity only; it is not a producer
signature or authenticity proof. Every role fragment therefore references a
rich call record, and every wave carries the complete call manifest plus admitted
nodes, retries, nulls, planned lower bounds, coverage debt, and an explicit
controller-overhead boundary. Records also bind native identity, node class/
permission, DAG predecessors/topological wave, and producer generation. An orchestrator structural ledger exact-covers all
waves in the closure capture index; ghost, omitted, extra, or duplicate wave
identity fails closed. Closure `PASS` additionally requires a trusted host
capability to verify the exact Context and delegated/runtime/outcome/effect
digests; the standalone validation CLI has no such capability and cannot
authenticate PASS.

Test reuse requires an exact content/environment signature and TTL. Report
`EXECUTED`, `REUSED`, `SKIPPED`, and `FAILED` honestly. Critical/flaky evidence
requires re-execution or independent recheck. `EXECUTED` and `REUSED` checks both
reference a validated command capture; reuse additionally preserves its
reuse-assessment lineage. Without a host CommandCaptureVerifier, Closure deliberately
trusted-replays captures, so one Adapter call is not a claim of one total execution.
It rejects a PASS that does not reproduce or mutates task or whole-repo generation. Repository authority
also binds value to the exact pinned Context-byte identity projection; interpreted
semantics must use typed claim evidence.

Routed verification nodes must explicitly PASS; `NOT_APPLICABLE` is only valid
for work-only write nodes. OPS/QA/effect Adapter claims require their direct
runtime/outcome/receipt evidence classes, not a generic source digest. A unit
test cannot prove E2E behavior, source capture cannot prove runtime state, and a
repository snapshot cannot prove mutation. Repo mutation needs exactly one
task/role/node/scope-bound record per admitted writer in canonical writer order.
Writer scopes are non-empty/disjoint. Every record binds its node-owned mutation
and exact task-wide generation; serialized writers form G0 -> G1 -> ... -> Gn,
with adjacent after/before generation digests equal. Gn and every owned after-
state must be current; one mixed record cannot satisfy two writer nodes.

Actual token/cache/tool/time consumption may be claimed only from
`PLATFORM_OR_EXTERNAL_ATTESTED` telemetry. An orchestrator wave ledger may report
calls, retries, nulls, fan-out, and planned input lower bounds, but never promotes
those estimates into actual usage.

Longitudinal reopen/rework/false-closure/realized-value metrics live in a separate
immutable-digest-bound `closure_quality_followup_v1`. Measured follow-up requires
caller-trusted platform/external attestation; absent telemetry stays scheduled or
unavailable and is never filled with zero.

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
- Active state belongs in `TODO.md`; stable architecture in README/CONTEXT/ADR;
  evidence in closure/report/archive; memory only receives new durable lessons.

When this operating Interface changes, update the Registry, renderer/tests,
`docs/agents/development-agent-governance.md`, and the accepted ADR. Generated
role views must not be hand-edited.
