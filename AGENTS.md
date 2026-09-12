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

## Task execution control

Task execution is finite by default. The canonical task contract always carries
`continuation_mode=finite|operator_loop`; omission normalizes only to `finite`.
`operator_loop` is admitted only when the exact Operator request begins with a
first control line equal to `/loop`. Natural-language similarity, a role, TODO row,
filename, prior session, `next_action`, or generated prompt cannot infer or
inherit that authority. The compiler binds that marker to the exact task-prompt
and admitted task-contract digest; callers cannot replace a compiled finite
contract with a newly constructed loop control. Serialized prompt/digest fields
are not Operator provenance: generic CLI admission rejects `operator_loop` unless
the embedding host supplies an out-of-band trusted Operator-request verifier over
the exact normalized contract.

A finite task may perform all necessary in-turn steps, but it cannot schedule a
new turn, wakeup, or automatic continuation. Before any opt-in operator loop
schedules another turn, PM must first acquire a persisted task admission with
`agent_governance.py task-admission`. Its private fencing token binds the original
normalized task contract and preceding progress snapshot in Git's common directory.
`agent_governance.py continuation` accepts only that task/owner/token tuple and
recaptures actual repository bytes from the admitted `dirty_scope`; callers cannot
provide a replacement contract, digest, or previous snapshot. Generic continuation
counts only a task-owned source-byte change as progress. Lifecycle labels, blocker
labels, round counters, timestamps, repository HEAD changes, caller receipts, and
unrelated whole-repository drift are not progress. Domain-specific external progress
requires its own validated Adapter or a reviewed task-owned artifact. An identical
progress digest closes the run as `BLOCKED_NO_DELTA`, with
`schedule_wakeup=false` and `next_action=null`. Scope/source/Context drift in an
ordinary finite task stops the current admission and requires explicit
re-admission; it never silently creates a loop.

An ordinary task admission starts only from a clean repository and persists the
exact config-isolated native `HEAD` and tree as `task_admission_accepted_base_v1`.
While holding the admission-store lock it rechecks that clean identity before
and after progress capture, and the baseline task-source manifest must exactly
match a raw tree/blob manifest re-derived from that immutable accepted tree.
Legacy ordinary records without `accepted_base` remain readable only for exact
cleanup; they cannot be used to acquire or renew authority or to publish.

Local `agent_workflow` work uses a paired stable `work_item_id`/`lane_id` for
one user delivery. The same delivery reuses that pair across task, worktree,
and process changes; rename cannot refill scope or repair authority. Its journal
freezes objective, acceptance, hard stops, and literal roots (later scope only
narrows), retains release history, and fails `DELIVERY_STATE_AMBIGUOUS` on a
map-key mismatch. A deliberate new pair is an explicit limitation, not proof of
semantic progress or host binding.

Queue state is separate from role work status. Only the physical `ACTIVE` lane
is dispatchable. `WAITING`/`DEFERRED` requires a named new delta and PM
re-admission before returning to ACTIVE; `CLOSED` is never selected. A completed
Closure may use `next_action=null`; `BLOCKED`/`NEEDS_CONTEXT` must still name the
owner and unblock condition. Do not manufacture executable work to satisfy a
schema.

Every writable task uses one exclusive writer lease in one attached, non-main
linked worktree. The exact public `agent_governance.py writer-lease` actions are
`acquire`, `status`, `publication-status`, `renew`, and `release`.
`publication-status` is a read-only, nonrenewing, nonpersisting publication
authority check: the caller must name the explicit `publish|post-push` phase,
expected feature branch, and exact expected 40-hex SHA. The task-admission lock
and then the writer lock remain held while it verifies the exact ACTIVE
admission/lease is unexpired at trusted entry and final times. For LW2 it
performs one full admitted-generation capture plus the lightweight final native
snapshot. For an ordinary task it also requires a nonempty, strictly linear
native `accepted_base`-to-feature commit range with replace projection, rename
detection, external diff, and text conversion disabled. Every commit is
inspected, its binary patch is bound, and every touched path must be inside the
admitted `dirty_scope`; an intermediate revert, both sides of a rename, or one
mixed-scope commit therefore cannot disappear from the decision.

Before any remote-head producer callback, the final boundary purely validates
exactly one canonical `origin` fetch URL and one identical push URL as a
credential-free exact public `https://github.com/<owner>/<repo>.git` repository,
and validates the exact `refs/heads/main` and, for `post-push`, feature ref.
A private, credentialed, malformed, or local-filesystem origin causes zero
remote producer callbacks and fails closed. The boundary derives only the exact
`<expected-sha>:refs/heads/<expected-branch>` refspec, checks the final live
remote (`main`, and the feature ref for `post-push`), and finally reads the
trusted clock. Native config-isolated `git ls-remote` remains the primary live
ref read. Only when that transport is unavailable, an exact public
`https://github.com/<owner>/<repo>.git` URL may use the pinned, config-disabled,
unauthenticated GitHub REST `git/ref` read; it must return the exact requested
ref, commit type, and lowercase 40-hex SHA. This fallback adds no credential,
private-repository, or ref-mutation authority, and every URL/HTTP/JSON/ref/SHA
anomaly remains unavailable. PASS neither repairs/renews state nor authorizes
more edits, runtime, service, deployment, broker, order, funds, trading, or
activation.
`git_loop_guard.py` only validates this existing task/owner/fencing authority and
never acquires, steals, or repairs a lease. A second writer uses a different
linked worktree. Read-only query/review paths do not acquire a writer lease.
Low-risk, low-uncertainty, effect-free `task_shape=query` routes only
`PM triage -> PM closure`; hard authority/runtime/private-effect facts cannot
use that narrow path.

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

`DONE` and `DONE_WITH_CONCERNS` may end with `next_action=null` when no real
follow-up exists. `BLOCKED`/`NEEDS_CONTEXT` require an owned unblock action.
`BLOCKED_NO_DELTA` is terminal for the current admission, can never carry PASS,
and must have `next_action=null`; only a new semantic/external delta or explicit
Operator reopen can create a new ACTIVE task.

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
task/role/node/effective-scope-bound record per admitted writer in canonical
writer order. The digest-bound `repository_writer_scope_contract_v1` constrains
that effective scope; it never overrides raw dispatch authority. A literal path
from a raw canonical or adaptive scope may transfer only to a later, transitively
serialized adaptive writer with the same dispatched role and permission. The
resulting effective scopes remain non-empty/disjoint and their exact union is the
task `dirty_scope`.

The change chain has two fail-closed modes. A clean committed chain binds the
admitted baseline, pairs clean task-wide and writer-owned endpoints, requires
adjacent head and generation equality, and proves a nonempty config-isolated
native strictly-linear commit range for each writer with every commit path inside
that writer's effective scope. Only the final writer `owned_after` and final
task-wide generation must be current. A same-HEAD dirty chain instead keeps every
writer `owned_after` current. Mixing committed and dirty modes, or using one
record for two writers, fails closed. Neither mode grants LW2, runtime, service,
broker, order, funds, or trading effects.

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
- Writable feature work requires the exact active linked-worktree writer lease;
  sharing one checkout between concurrent writers is forbidden.
- Active state belongs in `TODO.md`; stable architecture in README/CONTEXT/ADR;
  evidence in closure/report/archive; memory only receives new durable lessons.

When this operating Interface changes, update the Registry, renderer/tests,
`docs/agents/development-agent-governance.md`, and the accepted ADR. Generated
role views must not be hand-edited.
