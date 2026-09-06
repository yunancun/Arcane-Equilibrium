# Development-agent bootstrap reference

Canonical conditional reference for slim entry documents. Source observation:
`aee17bc01cfdf2331e6c0949d616c1a9903eaec2`. Read only the heading selected by the exact trigger table in
[`context-loading.md`](context-loading.md#conditional-before-action-pointers)
**before action**. This is manual reading, not compiler auto-acquisition, and
stable queries do not preload this file.

## Dispatch, ownership, and independent review

### Role binding and dispatch

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

### Conditional editorial-docs review

Docs writes normally route `TW → R4`. Only PM may classify a task with surfaces exactly
`docs`/`comments`, low/low, finite `docs_write`, `runtime_claim=false` and
`end_to_end_claim=false`, and one literal lowercase-ASCII safe,
unprotected `docs/*.md` path equal to `dirty_scope` as editorial; then R4 may be
skipped with reason, PM residual, and reopen on scope/class/surface drift. The
routing helper owns protected paths. Link/reference/index/structural/current-state
edits name their true surfaces and retain R4; TW and R4 native permissions do not change.

`verification_scope` is an optional canonical, sorted/unique list of literal,
safe repository-relative paths. A read-only verifier command capture uses it
only when routed node `path_scope` is empty, and before falling back to
`dirty_scope`. It is only a capture-generation and trusted-replay boundary; it
never grants writer ownership, mutation authority, or ACL permission, and it
does not replace writer `dirty_scope` or whole-repository generation checks.

## Finite execution, admission, continuation, and no-delta

### Task execution control

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

## Permission model and effect Adapters

### Permission and effects

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

## Runtime, broker, and external-effect boundaries

### L0 boundary capsule

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

### Runtime and PG routing

This context router does not embed effectful copy-paste commands. For Rust,
Cargo, Linux, PG, deploy, cron, service, or broker work:

1. Load `docs/agents/sub-agent-hygiene-sop.md`.
2. Bind OPS/E3/BB/IB/QA only when task facts trigger them.
3. Read-only roles execute argv only through Context-bound `capture-command`;
   its repository-policy receipt is not host no-contact attestation.
4. Delegated cargo stays on Mac; Linux cargo is forbidden.
5. Direct `psql` is disabled even for apparent SELECTs until a local-socket/
   read-only-identity Adapter removes ambient `psqlrc` and `PG*` routing. PG
   claims need a separately authorized, platform-attested artifact or remain
   UNVERIFIED; PG mutation additionally needs an approved migration/deploy
   Adapter.
6. Restart/deploy/contact is never a command copied from a context document.
   The deploy contract validates exact intent and independently reruns the
   local-only, non-secret, fail-closed `runtime_environment_probe_v1`, reconciling
   any supplied `runtime_environment_attestation_v1`. That seam is neither a
   platform runtime attestation nor remote SSH capture transport. Apply remains
   unconditionally disabled before component invocation until exact rollback
   binding and stable observation-window controls are separately implemented and
   verified. Development-
   agent broker/private/external contact has no closure-admissible Adapter and
   routes to an explicit unsupported-effect blocker; IBKR/Bybit implementation
   paths are reference surfaces, not authorization.

## Closure evidence, command capture, reuse, and telemetry

### Closure and evidence

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

## Operator decisions, autonomy, and escalation

### Operator interaction

Stop and report before expanding authority when there is a root-principle or
hard-boundary conflict, contradictory cross-class evidence, destructive/risky
operation, unclear ownership that risks collateral edits, or a technically
unsound requested path. Distinguish fact, inference, and assumption.

## Git, checkpoints, generated views, and persistence

### Git and persistence

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

## Context compiler, packs, budgets, and saved-workflow parity

### Mandatory exact capsule

The following are lossless and never removed to meet a token target:

- user objective, exact scope, acceptance, hard stops
- current source head, dirty scope, and any optional read-only verification scope
- direct Interface/callers affected by a source change
- relevant Root Principle/Hard Boundary/ADR denial
- latest blocker/runtime freshness when a current-state claim is made
- previous failed check, concern, or dissent that remains relevant
- task-specific evidence contract

If one is missing, acquire it or return `NEEDS_CONTEXT/UNVERIFIED`. Generic
summary is not a substitute.

These facts are normalized into one exact `task_contract`: task shape, sorted
surfaces, risk, runtime/end-to-end claims, `side_effect_class`, objective, scope,
acceptance, hard stops, source baseline, `dirty_scope`, optional
`verification_scope`, direct interfaces, previous failure, optional typed
`admission_profile`, and its exact `claim_payloads`.
`dirty_scope` is normalized to unique, safe repository-relative paths sorted by
Unicode scalar value; unpaired surrogates and Git/pathspec-like spellings fail
closed. `verification_scope` uses the same portable path ordering and safety.
Reserved documentation/frontend path tokens use ASCII-only case folding in both
Python and saved-workflow JS; Unicode confusables never acquire those ownership
classes.
Any prior/evidence digest that may determine a verdict is also admitted under
`claim_inputs`; each supplied typed payload must canonically hash to its named
digest. The free-form prompt, task ID, filename, TODO label, or summary is not an
authority channel for inferring a profile or replacing evidence. The canonical
task-contract digest follows the Context artifact into every role fragment and
final closure. A later prompt, fragment, or summary cannot silently widen scope,
change acceptance/evidence inputs, or switch effect class.

`verification_scope` is an optional canonical, sorted/unique list of literal,
safe repository-relative paths used only for read-only command-capture generation
and trusted replay. It is selected only when routed verifier `path_scope` is
empty, and before the `dirty_scope` fallback. This field is not writer ownership,
mutation authority, or an ACL, and it never replaces writer `dirty_scope` or
whole-repository generation checks.

`history_refs` is an optional list of at most four exact historical sections.
Each ref binds one allowlisted repository-relative Markdown path, one exact H2
heading, and the current section digest. The compiler rejects globs, directory
selection, path traversal, symlinks, whole-file fallbacks, duplicate refs,
sections above 16 KiB, and an aggregate above 32 KiB. Omission normalizes to an
empty list. History can inform judgment only through these pinned bytes; it
cannot silently inherit the parent task, an entire conversation, or every role
memory.

### Source-of-truth routing

| Need | Read | Authority class |
|---|---|---|
| Product/hard permission | relevant `CLAUDE.md`, accepted ADR/AMD, operator decision | `normative_policy` |
| Role/capability/permission | `.codex/agent_registry_v1.json` + generated role Adapter | Registry Interface |
| Current owner/blocker/next action | `TODO.md` | `active_work_state` |
| Stable project entry | relevant `README.md` section | stable context |
| Domain vocabulary | relevant `CONTEXT.md` / `docs/agents/domain.md` section | domain language |
| Implementation truth | direct code/schema/tests/callers | `implementation_contract` |
| Linux/process/PG/artifact truth | timestamped, allowlisted read-only observation | `runtime_observation` |
| Broker/third-party rule | official source + verified_at | `external_policy` |
| Claim proof | hash-pinned closure/test/runtime artifact | `claim_evidence` |
| Docs placement/index | `docs/README.md`, relevant `docs/_indexes/*` | docs routing |
| Deep history/RCA | relevant memory shard/report/archive/inventory | history, on demand |

Authority claims also bind subject, canonical value, source digest, scope,
strength, observed time, class-specific expiry, exact `source_ref`, and a
self-digest. Only compare freshness/strength within the same
class/subject/scope. Cross-class disagreement is DRIFT/CONFLICT; runtime cannot
legalize policy denial. A self-digest proves canonical integrity, not producer
authenticity.

Trust tier is orthogonal to authority class:

- `LOCAL_REPRODUCIBLE`: exact repository/command content can be recaptured by the
  governance producer.
- `ORCHESTRATOR_BOUND`: a controller receipt binds what it asked, when it called,
  and the exact result returned.
- `PLATFORM_OR_EXTERNAL_ATTESTED`: a platform/provider/external verifier attests
  runtime, external policy/outcome, or actual usage.

Do not upgrade one tier by adding a digest. Source/test PASS may use locally
reproducible capture plus independently call-bound verification; runtime/E2E/
external/actual-usage claims require the third tier.

### Context packs

The Registry defines packs; the compiler selects and deduplicates pointers:

- `core`: relevant product/root/hard-boundary sections
- `active_state`: the Registry uses `todo_dispatch_projection` on the exact
  `S2E 當前派發投影` section when current state can change the answer. One ACTIVE
  row projects that row plus direct dependencies and stays capped at 8 KiB. Zero
  ACTIVE rows are legal only with the exact, unique
  `S2E-DISPATCH-PROJECTION` EMPTY marker; the typed JSON content is
  `projection_state=EMPTY`, `active_rows=[]`, `active_count=0`,
  `dispatchable=false`, and `next_action=null`. Missing/renamed headings,
  malformed or mixed EMPTY+ACTIVE state, other-section rows, and more than one
  ACTIVE row fail closed without full-file fallback. The capture still records
  content digest/bytes/provenance, source bytes, and a real
  `full_file_token_estimate` from complete `TODO.md` bytes. Legacy
  `todo_active_rows` callers retain exactly-one ACTIVE semantics.
- `active_state`: an explicit `current_workflow_state` selects only `TODO.md`
  exact H2 `## Workflow optimization physical queue（source-only）`; it never
  selects `WORKFLOW_TODO.md` or a `workflow_state` pack. `current_s2e_state`
  retains the existing S2E projection. A selected `markdown_section` is one unique
  full ATX heading outside balanced fences and at most 16 KiB; missing, duplicate,
  malformed, or unselected sections fail closed, never to whole-file fallback.
  The independent `docs` pack selects seven `docs/README.md` sections including
  Document Index rules. Bulk directory history is not preloaded and core
  `AGENTS.md`/policy bytes remain exact. The compiler never infers a state surface
  from prompt words: stable conceptual queries carry none; current-state questions
  must name one. Every role, including low-uncertainty routing, receives the
  matching bounded surface; existing runtime/high-risk triggers remain intact.
  Registry-derived kind/name/selector identities are exact-checked in Python and
  saved workflow; the semantic payload need not repeat `source_kind` because the
  full plan binds it.
- `architecture`: CONTEXT + relevant ADR
- `source_change`: diff, direct interfaces/callers, focused acceptance tests
- `runtime`: active evidence + sub-agent hygiene
- `broker_bybit` / `broker_ibkr`: correct venue review/reference sources
- `ml_data`: lineage, feature/label/CV, training/serving evidence
- `gui_visual`: browser/viewport/keyboard/accessibility/screenshot evidence
- `docs`: placement and relevant indexes
- `history_on_demand`: only exact sections named by validated `history_refs`;
  empty refs mean the pack is inactive

Role memory is historical judgment support, not an automatic startup dependency.
With identical task inputs, unrelated TODO rows and unselected history must not
change selected semantic content, its digest, or planned estimates; artifact
provenance and freshness remain independently bound.

### Elastic budget

Each plan reports `target_context_tokens`, `quality_reserve_context_tokens`, an
explicit `accounting_basis=utf8_bytes_div4_planned_lower_bound_v1`, per-call
planned/UTF-8-byte caps, workflow planned cap, unique-node cap, attempt cap, and retry budget:

- within target: proceed
- above target: use reserve when it avoids hard-risk or rework
- above target+reserve but below both single-call caps: require a review rationale
- at a planned or exact-byte cap: split by Interface or escalate context
- mandatory content remains intact in all cases
- unresolved coverage at the limit cannot PASS

The planned lower bound is not actual tokenizer/cache usage; only platform-attested
telemetry may make that claim. Full Audit deliberately has a larger envelope. Stop based on diminishing
decision value after mandatory coverage, not a fixed role/finding count.

Concrete files are hashed from local bytes before caller assertions are read.
Virtual evidence must use a safe repo-relative `context_evidence_artifact_v1` whose
hashed bytes contain the exact logical source, capture kind, observed time, content,
and content digest. Arbitrary files, cross-source substitution, digest-only state,
missing files, unknown keys, sensitive paths, symlinks, and path escape remain unresolved.

`agent-wave` consumes one Python-produced `context_artifact_v1`. It hashes the
exact `canonical_plan` bytes, recomputes the task-contract digest, source bytes/
digests, capture TTLs, token estimate, compiler budget authority, and the exact
call-producing DAG binding (canonical nodes/edges, digest, node count, edge count),
then embeds
the same verified plan bytes and reuses them on retry. Exact `task_prompt` and
required uncertainty are part of the normalized task contract; prompt swap or
omission fails before a call. A generic host-executor wave that differs from
the deterministic routed DAG must be supplied to
`compile_context(..., execution_dag=...)` before materialization; the explicit
DAG must retain the exact core of every canonical routed call-producing node.
Full Audit and Profit Diagnosis accept only their fixed graphs: neither a
compiler-derived nor caller-supplied superset may extend or select a saved
workflow executor. When a specialized route has unmatched calls, compilation
returns typed `SPECIALIZED_WORKFLOW_SPLIT_REQUIRED` with the surface and sorted
node ids. It may do so only after exact Registry/artifact metadata, complete
routed obligations, canonical ASCII node ids, native bindings, and acyclic
topology pass. PM branches on `error_code` and compiles the fixed saved-workflow
phase plus a fresh non-specialized generic/host phase; it never slices,
re-signs, or retries the rejected artifact. A generic mismatch or mixed
omission/substitution is not a split signal. Omission or substitution of a
routed node still fails closed; local JS cannot self-promote a narrow artifact. Profit
Diagnosis binds 10 pre-call nodes; Full Audit binds 13 axes + seam and stages
later claim verification/fix as MAE-005 host-phase debt. Explicit `[]`,
non-arrays, malformed JSON, or unknown node fields are rejected. Only a
compiler-derived zero-delegation query may carry an empty binding; there is no
public empty override. Closure separately revalidates the PM admission
artifact and binds every fragment to its digest. Its wave validator also
exact-compares the ordered admitted-task core and `dag_digest` with the
Context `execution_dag_binding`; adding a post-Context node requires a freshly
compiled Context, even if every call/manifest/wave self-digest was recomputed.
Both saved workflows repeat the exact split discriminator before call 1, so
passing a host-phase superset or mixed tamper to the wrong executor cannot
start a partial wave. The plan also binds the canonical digest of the validated
Registry generation. Compile, materialize, independent validation, and saved
JS admission all require the same bytes; Registry injection cannot redefine a
fixed graph or reuse an artifact across generations.
Every model call is then
controller-recorded with exact task/context/role/node/native identity/class/
permission, DAG predecessors/topological wave, producer generation, dirty-scope/
focus/schema/result, and retry binding. The complete call
manifest closes into `workflow_wave_record_v1`, including admitted nodes,
calls/retries/nulls, result digests, planned input lower bounds, coverage debt,
and explicit controller-overhead exclusions. Raw `contextPath` is not an
admission mode because the saved-workflow runtime has no proven read+hash seam.
The loader evaluates one standalone `AsyncFunction` and has no stable
module-relative import contract. Therefore `agent-wave`, Full Audit, and Profit
Diagnosis embed a generated `CONTEXT_ADMISSION_V1` block from
`.claude/workflows/context-admission-v1.fragment.js`. Its checker projects
Registry budget profiles, execution surfaces, default history, and exact
saved-workflow model/role-effort policy; it rejects byte drift, shadow
declarations, real import/require statements, or an unused common-prefix helper.
The same generated block owns a rolling bounded worker pool: completion of one
call immediately refills the slot while active calls remain within the Registry
cap; first error stops new dequeue only after already-running calls settle.
Every call begins with the exact `canonical_plan` bytes already recorded by `artifact_digest`,
then adds only the node-specific suffix after one blank line. This preserves
cache reuse without truncating Context.
Inline context can still be ingested per agent; actual token/cache/tool/time
usage requires `PLATFORM_OR_EXTERNAL_ATTESTED` telemetry. Wave records provide
structural/planned lower bounds, never actual usage.

For task-owned writes, capture exact scoped repository generation before work
and again after work. Closure mutation causality comes from one
`repository_change_record_v1` bound to task contract, writer role/node, scope,
and both captures; a current snapshot, source-change summary, or diff digest
alone is insufficient. `EXECUTED` and `REUSED` checks both reference a validated
`command_capture_v2`; reuse additionally needs its TTL/signature assessment.

## Documentation placement and update routing

### Update rules

- Current state -> `TODO.md`.
- Stable architecture -> README/CONTEXT/ADR.
- Agent Interface -> Registry, renderer, this router when pack routing changes.
- Evidence -> closure/report/archive, linked rather than pasted.
- Durable new lesson -> candidate at PM closure; mutate memory only with the
  typed trusted-host promotion attestation.
- Generated `.claude/agents/*.md`, `.codex/agents/*.md`, and
  `docs/CCAgentWorkSpace/*/profile.md` views are never hand-edited.
