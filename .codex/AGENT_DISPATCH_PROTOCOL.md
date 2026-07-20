# Codex Agent Dispatch Protocol

Last updated: 2026-07-20
Canonical role Interface: `.codex/agent_registry_v1.json`

## Purpose

Translate a user objective into the smallest sufficient, evidence-preserving
execution DAG. The deep design and invariants live in
`docs/agents/development-agent-governance.md`; this file is the Codex routing
Adapter.

## PM triage record

Before local work or delegation, bind:

- objective, exact scope, acceptance, hard stops
- exact `task_prompt` bytes and compiler-derived digest; objective is not a substitute
- task shape and surfaces
- risk and required `low|medium|high|unknown` uncertainty; omission fails before routing
- source/runtime/external evidence being claimed
- `claim_inputs` for every prior/evidence digest that can affect a verdict
- current head + dirty scope + any optional read-only verification scope
- expected output and side-effect class
- exact `continuation_mode`; absent means `finite`, and `operator_loop` requires
  a first control line exactly equal to `/loop` in the Operator task prompt rather than
  inference from state, filenames, generated text, or later caller input

The compiler accepts only its declared fields/surface vocabulary. Unknown fields
or surfaces fail closed so a typo cannot silently omit a hard gate. Use exact
`runtime_claim` and `end_to_end_claim` booleans. A `runtime` source surface alone
loads context; operational surfaces (`service`, `cron`, `pg`, `runtime_effect`,
`incident_rca`) or a runtime claim activate OPS.

`verification_scope` is an optional canonical, sorted/unique list of literal,
safe repository-relative paths for read-only command capture and trusted replay.
It is used only when routed verifier `path_scope` is empty, and before the
`dirty_scope` fallback. It is not writer ownership, mutation authority, or an ACL, and
cannot replace writer `dirty_scope` or whole-repository generation checks.

`side_effect_class` is part of the admitted task contract, not a comment. It must
match the task shape and surfaces (`none`, scoped repo/test/docs write, deploy,
`public_web_read`, or private external/broker effect). Source/docs/test write shapes deterministically derive
`repo_write`/`docs_write`/`local_test` and cannot silently default to `none`.
Contradictory combinations fail routing. `public_web_read` is read-only evidence
acquisition and requires an opened public URL plus citation/capture provenance;
platform tool availability is checked separately. `private_external_contact`
and broker-private effects produce a mandatory unsupported-effect node; there is
no development-agent Adapter that can turn them into PASS. Pure `task_shape=deploy`
routes through OPS/effect governance without inventing E1/E2/E4 source work;
source-plus-deploy keeps the source builder/review/regression chain.

Low-risk, low-uncertainty, effect-free `task_shape=query` with only narrow
documentation/governance surfaces routes `pm_triage -> pm_closure`. Query cannot
carry runtime/E2E claims or `operator_loop`; authority, security, broker,
private-effect, and other hard facts must use their normal task shape and gates.

Feed those facts to:

```bash
python3 helper_scripts/maintenance_scripts/agent_governance.py route @task_facts.json
python3 helper_scripts/maintenance_scripts/agent_governance.py context --role ROLE @task_facts.json
```

The output is advisory except for hard edges and hard boundaries. PM may add a
role when new evidence raises expected decision value, but it must be recorded
under closure `dispatch.admitted_role_nodes` with a unique node ID, Registry
role, exact native agent, `work|verification` class, permission, sorted
predecessor `requires`, disjoint node-owned `path_scope`, result binding, and
reason. The exact call-producing projection (including explicitly admitted
nested calls, excluding only deterministic non-call controllers) is validated
before spawn and carries one identical `dag_digest`, task inventory, edge set,
and topological-wave projection through call/manifest/wave/closure receipts.
Admission makes its coverage
mandatory; omission or verifier dissent blocks PASS. Removal of a deterministic
mandatory node is not permitted without explicit operator risk acceptance where
policy allows an exception.

## Hybrid DAG rules

Hard edges are triggered by facts, not by task labels alone:

- source implementation: Builder -> independent E2 -> E4; mixed GUI/backend
  work uses the fixed disjoint E1 backend -> E1a frontend shared-worktree
  sequence, then joins both before E2
- authority/live/risk/auth: CC + E3, plus E2/E4 when source changes
- runtime claim or operational change/deploy: OPS preflight; deploy then uses
  PM/operator exact intent -> Deploy Adapter contract -> independent OPS postcheck;
  the trusted local probe source exists, but generic apply remains fail closed before
  component invocation on unbound rollback and stable observation-window controls
- P0-B ALR stage/cutover selects `p0b_alr_rollforward_adapter_v1` only through
  its exact phase selector and claim inventory. Each phase is a fresh route and
  materialized Context admission; no generic deploy node or earlier phase approval
  substitutes for the current PA/E3/OPS evidence and phase-runtime bindings.
- Bybit: BB Adapter reviewer; IBKR/TWS/stock_etf_cash: IB Adapter reviewer
- quant/strategy/portfolio semantics: QC
- ML/data/schema semantics: MIT; AI-E only when model/orchestration economics matter
- end-to-end outcome: QA

PA/FA/E5/A3/R4/TW and extra independent reviewers are added when uncertainty,
cross-Interface reach, negative space, visual/docs impact, or expected rework
justifies them. Unknown risk uses the full-audit context envelope.
Unknown uncertainty does the same; omitted uncertainty is invalid rather than low.

Every omitted role records reason, residual risk, and owner. A shorter route is
good only when durable closure quality is unchanged.

## Finite execution and continuation

Dispatch decides what work is required; it does not imply another turn.
`finite` is the ordinary task contract and never authorizes `ScheduleWakeup`, a
continue prompt, or replay of a TODO row. An explicitly requested task whose
first control line is exactly `/loop` must acquire one persisted task admission,
then pass this decision before each scheduled turn:

```bash
python3 helper_scripts/maintenance_scripts/agent_governance.py \
  continuation @continuation_bundle.json
```

The admission Adapter persists the original normalized task contract, compiled
control, and preceding snapshot in Git's common directory behind a private fencing
token. The continuation bundle contains only repo/task/owner/token/work-status;
it cannot supply a replacement contract, digest, or previous snapshot. At the
boundary, the Adapter recaptures the admitted `dirty_scope` and uses its exact file
bytes as the generic progress fingerprint. Lifecycle/blocker labels,
whole-repository HEAD, caller receipts, round/time noise, and unrelated repo drift
are not progress. External-only progress needs a separate validated domain Adapter
or a reviewed task-owned artifact. Only
`CONTINUE_OPERATOR_LOOP` returns `schedule_wakeup=true`; identical progress
returns `BLOCKED_NO_DELTA`, while all terminal or finite decisions stop. Queue
selection consumes only exact ACTIVE items; IN_PROGRESS is already claimed and
cannot be selected again. WAITING/DEFERRED/CLOSED rows do not become
callable because their waiting condition or wall clock changed; PM must bind a
named delta and create a fresh ACTIVE admission.

Every writer admission also carries one exclusive linked-worktree lease. The
lease's random fencing token, task ID, owner, branch, and expiry must validate
before `git_loop_guard.py` admits start/checkpoint/publish/post-push. The guard is
read-only; collision, expiry, primary-worktree use, or foreign lease fails
closed. Read-only verification and PM-only query do not mutate the lease store.

## Admission and publication economics

Compiler-mandatory nodes are not optional, but PM must not add speculative
reviewers, duplicate investigators, or status-polling agents. Every adaptive
node records the concrete decision it may change; if that decision is already
closed by current evidence, skip the node and retain the reason. One watcher can
observe a running wave; fan-out does not make unchanged external state fresher.

PR publication is a single-owner effect. Sub-agents return governed fragments;
only the PM-owned publication lane updates the head, requests one current-head
review, or considers a rerun. Use local reproduction as the development loop,
then publish one stable batch. Hosted CI must use path classification and
obsolete-run cancellation where available. The second identical failure
fingerprint (`head/workflow/job/step/error family`) is a publication stop, not
permission for another blind commit-and-push cycle.

For a multi-iteration loop, PM also owns local checkpoint admission. It binds
one feature branch and full checkpoint SHA, requires a clean `start` guard at
every row boundary, runs the allowlisted bounded `checkpoint` guard before
staging, and commits each green row locally. Hosted publication remains one
stable batch, but crash recovery never spans an unbounded dirty tree.

The publication/merge/sync sequence is fixed by `.codex/SYNC.md`: `publish` ->
non-force feature-branch push -> `post-push` exact SHA -> current-head CI/review
-> merge with `--match-head-commit` -> clean ff-only Mac main -> clean ff-only
Linux main -> four-head reconciliation. No node may substitute force, reset,
clean, stash, generic pull, admin bypass, branch deletion, or destructive
worktree removal when a gate fails.

## Role and permission binding

Every dispatch declares `ROLE(codex_type)`, owned files/responsibility, expected
fragment/patch, task shape, context digest, and acceptance. Codex type is a
runtime substrate, never a model-intelligence tier.

Generated role views under `.codex/agents/` and `.claude/agents/` must match the
Registry. Native Codex execution uses `.codex/agents/*.toml`; adjacent Markdown
is a human projection only. Select the exact node-class identity from
`.codex/agents/INDEX.md`: `PA-design-writer` vs `PA-investigator`, and
`E4-writer` vs `E4-verifier`. Never spawn an ambiguous writer/verifier role.
Read-only identities keep `sandbox_mode="read-only"` even when the parent has
broader access; builders use `workspace-write` but remain task-owned and cannot
self-approve. Read-only roles execute verification only through one Adapter call:

```bash
python3 helper_scripts/maintenance_scripts/agent_governance.py capture-command \
  --native-agent NATIVE --node-id NODE \
  --context-artifact @context.json -- <argv...>
```

Identity and routed task come from the immutable Context; when the routed verifier
scope is empty, path scope uses optional `verification_scope` before `dirty_scope`.
Argv is not caller shell text. A denial becomes an Adapter intent/blocker. The receipt's
`repository_policy_only` effect boundary is not OS network/no-contact isolation.

## Context and consumption

Do not feed every agent the entire conversation or universal preload. Prefer an
independent fork plus an exact capsule containing user scope, acceptance, hard
stops, baseline, direct Interface/callers, previous concern, and relevant source
pointers/digests.

`agent-wave` admission requires one inline compiled `context_artifact_v1` containing
Python-canonical plan bytes plus their SHA-256, task-contract digest, and compiler
budget-authority binding. It hashes, parses, embeds, and retries the same captured
plan bytes without cross-language reserialization or path reopen; source bytes,
producer, freshness, token estimate, role, baseline, and authority caps are
recomputed. Verdict-relevant priors are bound under task-contract `claim_inputs`;
the free-form task prompt is not an evidence substitution channel. Raw `contextPath`,
bare legacy arrays, untyped/digest-only virtual evidence, omitted mandatory facts,
unresolved sources, or `pass_allowed!=true` are rejected before any agent call.
Admission locally recaptures Registry-selected repository/derived bytes; a
caller-rehashed artifact cannot establish provenance. Because saved workflows
run as standalone `AsyncFunction` bodies without a stable import seam, all three
use the generated `CONTEXT_ADMISSION_V1` block and begin every model prompt with
the exact `canonical_plan` bytes. Its existing artifact digest is therefore the
common-prefix digest, improving cache reuse without truncation.
Every returned fragment carries the same `task_contract_digest`; closure revalidates
the PM context artifact at adjudication and rejects objective/scope/criterion drift.

Every call attempt emits one canonical `workflow_call_record_v1` binding the
workflow contract, node/role/payload, requested model/effort/isolation, prompt,
task/context/dirty-scope/focus/schema, native identity/class/permission, DAG
predecessors/topological wave, producer generation, retry lineage, timestamps,
null state, and exact parsed-result digest. Dependencies are scheduled only after
all predecessors finish. The complete `workflow_call_manifest_v1` closes into
one `workflow_wave_record_v1` that accounts for every admitted node, call/retry/
null, result fragment, planned input lower bound, coverage debt, and controller-
overhead exclusion. A self-digest protects canonical integrity; it is not a
provider signature or producer-authenticity proof. Any orchestrator structural
ledger must reference exactly every wave in the closure capture index; omitted,
extra, or duplicate wave identity fails closed.

Budget authority separates target/reserve, reviewed single-call band, exact prompt
UTF-8 bytes, UTF8/4 planned lower bounds, workflow planned input, unique nodes,
attempts, and retry. Crossing target+reserve requires rationale; reaching a cap
triggers split/escalation, never mandatory-content deletion. Planned lower bounds
are not actual token/cache telemetry. The authenticated shared semantic capsule may
improve prefix reuse, but only platform telemetry can quantify savings.

AI-E owns quality-adjusted workflow consumption: input/output/cache tokens,
tool calls, retry, fan-out, wall time, accepted decision-changing findings,
rework, reopen, and cost per durable closure. Actual token/cache/tool/time values
require `PLATFORM_OR_EXTERNAL_ATTESTED` telemetry plus exact reference/digest;
`partial` lists every missing metric and `unavailable` carries no invented
numbers. Orchestrator wave receipts may support partial structural accounting of
calls, retries, fan-out, nulls, and planned input lower bounds, with controller
overhead explicit; they never become actual usage. Closure recomputes admissible
totals and quality-reserve use.

After closure, AI-E may join a separate `closure_quality_followup_v1` by immutable
closure digest to evaluate reopen, rework, false closure, decision-changing
findings, and realized value. Measured follow-up requires caller-trusted
platform/external attestation; missing telemetry remains scheduled/unavailable,
never zero-filled.

## Completion

Sub-agent output is a role fragment for `.codex/schemas/closure_packet_v1.schema.json`.
PM merges fragments into one closure and preserves dissent. Work completion and
gate success are independent; reviewers may return DONE+FAIL.

For closure PASS, work-only write nodes may report `NOT_APPLICABLE` as their own
gate, but every routed verification node must report PASS. OPS fragments must
reference fresh runtime evidence; QA and passed acceptance must reference direct
outcome evidence; every mandatory Effect Adapter must provide a hash-pinned
`effect_adapter_result_v1` receipt cross-bound to the intent authority, baseline,
distinct OPS preflight/postcheck, truthful side effects, and passed acceptance.
E4 must reference direct test evidence backed by an EXECUTED check or a fresh,
hash-pinned reuse receipt; a self-declared `REUSED` label is not sufficient.

Trust and evidence class are explicit:

- `LOCAL_REPRODUCIBLE`: exact repository/command bytes and locally recapturable
  source/test facts.
- `ORCHESTRATOR_BOUND`: controller-known task/context/role/result structural
  lineage; packet-local call/wave receipts cannot self-authenticate execution.
- `PLATFORM_OR_EXTERNAL_ATTESTED`: runtime, external-policy/outcome, and actual-
  usage authenticity.

Generic or self-authored digests are not direct proof. A unit command/test cannot
stand in for E2E outcome, and repository evidence cannot stand in for runtime.
`EXECUTED`/`REUSED` checks both bind a validated command capture; reuse additionally
binds the eligible historical lineage. Closure admission performs trusted local
replay of command captures under the same task/baseline/scope and rejects a
non-reproducing PASS or task/whole-repository mutation. One Adapter invocation is
not one total execution: without a host CommandCaptureVerifier, Closure deliberately
re-executes strong evidence. Repository authority also requires
the claim value to equal the deterministic identity projection of its exact
pinned Context bytes; semantic interpretation belongs in typed `claim_inputs` or
validated evidence. Repo mutation needs one task/role/node/scope-bound
`repository_change_record_v1` per admitted writer in canonical writer order.
Node-owned path scopes are non-empty/disjoint and writer nodes are transitively
serialized. Each receipt binds its owned mutation plus exact task-wide before/
after generation; adjacent receipts link G0 -> G1 -> ... -> Gn, and Gn/every
owned after-state remain current. One mixed-role record cannot cover two writers.
A snapshot or source-change summary alone proves no causality.
Stale or unresolved conflict blocks PASS.

Full Audit and profit diagnosis have controller contracts, not advisory summaries.
Both reject malformed inline Context, mismatched hard stops, task prompt, or
compiler/Registry budget authority before the first model call; caller self-signed
caps cannot spend resources and wait for Closure to reject them.
Full Audit includes E2 discovery, derives outcome state from typed verifier votes,
preserves malformed findings as canonical debt, and treats isolated fix candidates
as not integrated. Profit diagnosis binds fresh priors/baseline, Registry evidence
and probe axes, every fragment digest, bounded retries, deferred coverage debt, and
the PA map. Controller debt or missing binding prevents PASS in either workflow.
Closure `PASS` requires an out-of-band trusted-host verifier for the exact
Context plus every delegated/runtime/outcome/effect digest. The standalone CLI
has no host capability and therefore cannot authenticate PASS from packet bytes.

Bare same-model retry is forbidden. Response ladder:

- missing task facts -> acquire exact context
- capability/model mismatch -> select a stronger/different capability
- task too broad -> split along Interface boundaries
- hard/external blocker -> return BLOCKED with owner/action
- identical semantic progress -> return `BLOCKED_NO_DELTA`, no next action, no
  wakeup

No unchanged retry, no fabricated success, and no PASS when coverage or evidence
is missing.

## Runtime and deploy

Delegated roles do not run Linux cargo, PG writes, service/cron mutation, or
private broker effects. Linux evidence is read-only and timestamped. Effectful
apply is unavailable to ordinary roles; any future closure-admissible apply must
use an operator/PM-approved deterministic Adapter with exact source/build pin,
rollback, and independent postcheck. QA is added only when an end-to-end
business claim is part of completion.

Direct `psql` is currently denied, even for apparent SELECT, until a local-
socket/read-only-identity Adapter removes ambient `psqlrc` and `PG*` routing.
Without a separately authorized platform-attested PG artifact, the runtime claim
remains UNVERIFIED.

Current generic-deploy capability limit: `deploy_intent_adapter.py` validates a typed exact-SHA
intent and independently runs the local-only, non-secret, fail-closed
`runtime_environment_probe_v1`, reconciling its result with any supplied
`runtime_environment_attestation_v1`. This source seam is not a platform runtime
attestation and does not provide remote SSH capture transport. Even after exact
probe reconciliation, apply remains unconditionally disabled before component
invocation with unbound rollback-binding and stable observation-window blockers.
Registry broker paths are reference surfaces only; Bybit development contact is
unsupported and IBKR first-contact remains a gated operator/runtime path, not
this workflow's Adapter.

The sole scoped runtime-effect exception is the registered P0-B ALR rollforward
Adapter. Stage may seal lineage and private observer dependencies while retaining
the existing ALR service identity. Cutover may affect only
`openclaw-alr-shadow.service`, and emits a provisional artifact before observer
v2. `PHASE2_APPLIED_POSTCHECK_PASS` requires exact observer-v2 PASS; closure PASS
then requires a later fresh independent OPS postcheck bound to that final receipt.
It is not generic deploy, broker contact, or trading authority.

## Persistence

Significant durable decisions may update `.codex/DISPATCH_LEDGER.md` and one PM
closure projection. Do not create one report and memory append per role. Active
work remains in `TODO.md`; old reports/memory are on-demand history.
