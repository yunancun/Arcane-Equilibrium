# ADR-0052: GPT-5.6 Bounded Multi-Agent Execution

Status: Accepted

Date: 2026-07-30

Supersedes: none

Amends: ADR-0050 execution, Context, model-routing, Full Audit, OPS, memory, and
consumption policy

## Context

Two recent AI/ML development sessions showed a cost-amplification failure:

| Session | Elapsed | Platform total tokens | Cached input | Orchestration |
|---|---:|---:|---:|---|
| 2026-07-15..16 | 19h16m | 302.7M | 296.4M | 16 spawns, 418 waits, 72 follow-ups, 12 compactions |
| 2026-07-19 | 4h22m | 105.7M | 103.8M | 18 spawns, 191 waits, 24 follow-ups, 4 compactions |

About 98% of platform totals in each session were cached input. This does not
make the cost harmless: the dominant amplification was repeated model sampling
over a very large inherited context, plus waits/follow-ups/compactions, rather
than useful output. Most spawns inherited full history, role memories had become
task ledgers, ordinary Full Audit still ran all 13 axes, and read-only OPS work
could schedule both preflight and postcheck without an effect between them.

ADR-0050 correctly established one deep Development-Agent Governance Module,
typed evidence, conditional DAG routing, and finite/no-delta continuation. It
did not yet bind aggregate execution events, history propagation, native
surface capability, or role-specific GPT-5.6 model choice into one enforceable
receipt chain.

Current OpenAI documentation makes three relevant capabilities explicit:

- subagents increase token use; read-heavy parallelism should be bounded and
  model/effort may be pinned per role;
- GPT-5.6 Sol supports T1/high and T2/low role tiers, while Terra/medium is
  reserved for the T3 mechanical tier;
- GPT-5.6 `ultra` already coordinates subagents, so stacking an unbounded
  project fan-out underneath it compounds rather than controls orchestration;
- GPT-5.6 prompt caching is more predictable, but cache reads are discounted
  rather than free and cache writes have their own cost. Exact product/plan
  usage still needs platform telemetry;
- Codex supports `agents.max_concurrent_threads_per_session`,
  `default_subagent_model`, `default_subagent_reasoning_effort`, and
  `interrupt_message`, plus memory generation/external-context/model overrides.

The prior three months also added Codex Goal mode/remote continuation, richer
project context, ChatGPT memory sources, Work for longer-running tasks, and
workspace usage analytics. Those features make durable, resumable work easier;
they do not provide a repository-verifiable stop condition, call deadline, or
token attestation. This ADR therefore keeps outcome persistence separate from
unbounded model turns, and keeps memory retrieval separate from implicit full
history.

References:

- <https://learn.chatgpt.com/docs/agent-configuration/subagents>
- <https://learn.chatgpt.com/docs/config-file/config-reference>
- <https://learn.chatgpt.com/docs/customization/memories>
- <https://openai.com/index/gpt-5-6/>
- <https://help.openai.com/en/articles/20001354-gpt-5-6-in-chatgpt>
- <https://help.openai.com/en/articles/6825453-chatgpt-release-notes>

## Decision

Keep one Development-Agent Governance Module and add the following deep
contracts. No second orchestration framework is introduced.

### 1. Execution admission is a receipt-bound finite state machine

`execution_budget_policy_v1` is selected after the required-node DAG is known.
Route, Context, requested-agent identity, call manifest, and
`workflow_wave_record_v1` bind the same policy digest.

One watcher owns a wave. Its `execution_event_ledger_v1` validates the exact
lineage and supported event kinds attested by the selected surface. Saved
workflows currently exact-cover root plus model-call/retry records; a surface
cannot claim event kinds that its profile does not attest. Count/state caps for
model turns, calls, follow-ups, waits, no-delta wakeups, concurrency, unique
nodes, and spawn depth reject the next admitted action. Budget exhaustion is
terminal debt, never PASS.

The serialized ledger and its self-digest are structural evidence, not resume
authority. Post-hoc wave receipt construction uses a deterministic
structural-only assembler and may rebuild the same manifest bytes without
minting or consuming a controller. Live pre-action admission is a separate
internal seam: its non-serializable controller starts only from a pristine,
live-Registry-bound root, claims that root once for the process lifetime, and
locks head comparison through advancement. The controller privately freezes the
exact Registry policy and surface as canonical bytes; all cap and coverage
decisions reconstruct ordinary mappings from that state, never from a caller's
mutable object. One Registry-generation snapshot derives both authorities, and
each admission canonical-detaches the entire ledger and event once under the
controller lock before validation. No public facade accepts a caller-named root;
generalized minting waits for managed-host task/root authority.

Default requested history is ephemeral `none`. Bounded history requires an
exact source thread, boundary turn, and task-admitted exception digest. Missing
history, `all`, implicit parent inheritance, and recursion beyond one child
level are rejected.

### 2. Surface capability is explicit

`execution_surface_profile_v1` distinguishes Codex native collaboration,
Claude saved workflow, and generic host behavior. Native selector, history,
ephemeral fork, event coverage, concurrency, interruption, deadline, and usage
telemetry are independently represented.

Saved workflows enforce selector/history/fork/concurrency. The current Codex
native collaboration API has no repository-owned interceptor/attestation seam:
selector/history/fork are only caller-reported even though project concurrency
and `interrupt_message=false` are enforced. Codex native and generic hosts are
therefore advisory-only and cannot satisfy a mandatory PA/E4 native identity
until a host adapter attests the exact tool call/fork boundary. Unrecorded
model-visible interruption text cannot alter replay context.

Current repository/host APIs do not provide a closure-verifiable per-call/wave
cancellation deadline or provider total-token counter. These remain
machine-detectable `unavailable`/`EXTERNAL_LIMIT`; a configured duration is not
described as cancellation, and planned prompt bytes are not described as actual
tokens.

### 3. Model choice is role-specific and never inherited accidentally

Codex config defaults are the unguided fallback `gpt-5.6-terra/medium`.
Governed roles derive their provider-equivalent tier from the operator role
policy: T1 uses `gpt-5.6-sol/high`, T2 uses `gpt-5.6-sol/low`, and T3 uses
`gpt-5.6-terra/medium`.

Every generated native TOML and call receipt names model and effort explicitly.
Claude saved workflows use the separate Registry-owned
`saved_workflow_model_policy_v1`: `role_models` and `role_efforts` exact-match
the same operator role tier. Neither surface may inherit a parent/session tier
or accept a caller substitution. A future exception requires a new named
Registry policy and tests.

Common authority/context/economy/permission/effect/web/capture/output prose is
rendered once from `native_operating_contract_v1`. Persona lens, activation,
Own, Refuse, judgment, and native writer/verifier identities remain
role-specific.

### 4. Context and memory are exact bounded projections

The active-state pack selects only the unique row from the exact
`S2E 當前 ACTIVE 派發` table plus direct dependency rows, capped at 8 KiB.
Unrelated TODO changes cannot alter its bytes, digest, or planned tokens.

Historical material is unreachable unless the task contract supplies up to four
`history_refs`. Each ref binds a safe allowlisted Markdown path, exact H2
heading, and digest. A section is at most 16 KiB and the aggregate at most
32 KiB; globs, whole-file fallbacks, traversal, symlinks, and unselected
sections are rejected.

Every active role memory has exactly `Usage contract`, `Durable lessons`,
`Topical pointers`, and `Archive pointer`, at most 300 lines/48 KiB. Mechanical
compaction is prefix-preserving, append-only, byte-recoverable, digest-bound,
and idempotent.

Durable promotion cannot be authorized by a `PM_CLOSURE` string, closure
self-digest, or serialized attestation. It requires exact
`role_memory_promotion_authority_v1` bytes at
`PLATFORM_OR_EXTERNAL_ATTESTED` plus a non-serialized trusted-host verifier.
Each accepted successor archives the exact predecessor hot view and canonical
manifest bytes and reconstructs their marker, generation, self-digest, and
promotion prefix. The standalone CLI has no verifier and therefore returns a
zero-mutation `EXTERNAL_LIMIT`.

Codex memory generation excludes external-context threads and uses
`gpt-5.6-luna` for extraction/consolidation only when a strict read-only host
probe confirms the keys and bundled model. Otherwise the state is
`EXTERNAL_LIMIT`; there is no silent fallback claim.

### 5. Routing and workflows remove duplicate work without weakening gates

Envelope selection occurs after DAG construction. `narrow` permits two
in-flight model calls; other current envelopes permit three. Generated
workflows use a bounded scheduler rather than launching the full runnable set.

Context additionally binds the complete pre-call execution DAG: exact node
identity, native role, predecessors, class, permission, node/edge counts, and
digest. Profit Diagnosis has one fixed 10-node graph (3 evidence, 6 probes,
1 PA map). The saved Full Audit has one fixed 14-node graph (13 axes plus the
seam critic). Either workflow exact-compares that binding before its first
model call; it cannot append a post-call node or promote its own envelope.
Explicit caller `execution_dag=[]`, non-array/malformed values, and unknown
node fields fail closed. A zero-node binding exists only for a
compiler-derived zero-delegation query, not through a caller switch. Generic
host-executor routes may add nodes only as a faithful explicit superset of the
canonical route: omission or substitution of any routed call-producing node
core fails. Closure then exact-binds the ordered wave admitted-task core and
wave `dag_digest` to the Context binding; an internally consistent rehash of a
larger post-Context wave remains invalid until Context is freshly compiled.
Full Audit and Profit Diagnosis never accept a DAG superset, whether supplied
implicitly or explicitly. If valid route facts require another call (for
example end-to-end `business_acceptance`, or runtime `security_gate` /
`ops_observation`), compilation fails before materialization with the typed
`SPECIALIZED_WORKFLOW_SPLIT_REQUIRED`, its specialized surface, and sorted
unmatched node ids. The discriminator runs only after Registry generation,
artifact metadata, routed obligations, native bindings, canonical ASCII node
ids, and acyclic topology all match; mixed metadata, omission, substitution,
or malformed `requires` remains an ordinary DAG failure. PM branches on
`error_code`, never on the human error string, and compiles both the fixed saved workflow and the additional
non-specialized host executor as fresh Context phases. A generic DAG mismatch
is not a split signal and must not trigger automatic retry. Both saved
workflows repeat the exact discriminator before call 1, preventing mixed
tampering or a host-phase superset from becoming a partial saved wave.

Every Context plan also binds the validated Registry generation by canonical
content digest. Compile, materialize, independent validation, and the generated
saved-workflow admission block all require that exact generation; an injected
Registry cannot erase axes, redefine the fixed graph, or authorize an artifact
created under different Registry bytes.

Full Audit defaults to the complete 13-axis backstop. Reduced adaptive selection
uses `CC`, `FA`, route-required axes, and one deterministic rotating
negative-space axis only after a future independent platform/external Adapter
attests recall non-inferiority and an out-of-band host verifier authenticates
the exact typed record. A task claim, boolean, self-digest, `claim_evidence`, or
ordinary execution attestation cannot grant that authority. Until the Adapter
and verifier exist, saved-workflow and Closure paths reject adaptive,
adaptive-shadow, and any reduced axis set as
`EXTERNAL_LIMIT_RECALL_AUTHORITY` before the first model call.

Full Audit findings are staged, not verified or fixed inside that saved
workflow. Every data-dependent verifier/fix/review action requires a new
Context whose exact DAG is knowable and a supported host-native selector
attestation under existing `MAE-005 /
EXTERNAL_LIMIT_NATIVE_SELECTOR_ATTESTATION`. Until then the workflow makes zero
such calls and records coverage debt, so this phase does not create a ninth
external limit. The Registry's 44-node/46-attempt Full Audit policy remains an
authority ceiling for a future separately admitted phase, not a reservation or
usage claim for the current fixed 14-node workflow.

Read-only/source operational lanes use one `ops_observation`. Preflight and
postcheck remain separate only around an admitted effect Adapter.

`agent_governance_liveness` defines a pure adjudication contract. Every
caller-supplied collaboration/thread activity mapping, including a fresh
`RUNNING`, `WAITING`, or terminal value, is unverified and therefore adjudicates
to `UNKNOWN + CALLER_ACTIVITY_UNVERIFIED + EXTERNAL_LIMIT`; private JSONL
existence/mtime/size is diagnostic only. The repository does not currently have
a host activity-acquisition/controller Adapter with monotonic
identity/sequence/head verification, so actual controller liveness integration
remains `EXTERNAL_LIMIT`; the helper alone does not wait, cancel, or stop an
agent. Missing JSONL never declares an agent dead, and transcript size never
represents token usage.

### 6. Efficiency is quality-first and measurable

`multi_agent_efficiency_evaluation_v1` compares current, single-agent, and
bounded-role profiles for the same case. Required coverage, closure quality,
decision-changing findings, reopen/rework, and false-closure evidence are
checked before elapsed time, calls, waits, retries, compactions, or token
classes can count as improvement.

The exact quality metrics include `required_coverage_ratio`,
`closure_quality_score`, `decision_changing_findings`, `reopen_count`,
`rework_count`, `false_closure_count`, and `p0_p1_recall_ratio`. The quality
thresholds are an exact Registry policy: complete required coverage and P0/P1
recall, zero closure-quality drop, zero reopen/rework/false-closure increase,
and full decision-changing-finding retention. Missing or inferior quality
evidence blocks an efficiency claim; callers cannot relax the gate. Synthetic
fixtures validate the schema and adjudicator only. Exact policy comparison uses
`allow_nan=false` canonical JSON bytes, so a recomputed digest cannot substitute
integer zero for `0.0` or for boolean `false`.
Quality non-inferiority is necessary but not sufficient. The same Registry
policy owns `all_axes_non_worse_and_one_strictly_better_v1`: elapsed time,
input/output/cache-read tokens, calls, waits, retries, and compactions use their
raw values; every axis must be no worse than current and at least one must be
strictly better. Missing axes, equality on every axis, or one worse axis reject
both measured efficiency and synthetic benchmark candidacy.

Actual savings require a typed attestation index that binds unique immutable run
IDs, exact non-reused call-record inventories whose per-profile length equals
every reported `metrics.calls`, metrics digests, and record digests; zero calls
bind an empty inventory, an unavailable partial-profile call count also requires
an empty inventory, and `retries` cannot exceed a reported `calls`. An
out-of-band trusted-host verifier must authenticate the exact index. A free-form
reference or self-digest never unlocks a measured claim, and the standalone CLI
remains `EXTERNAL_LIMIT`.

## Consequences

Expected structural effects:

- focused/no-finding adaptive Full Audit has a synthetic 14-to-6 candidate
  (57.1%), but executable execution remains at the 14-unique-node backstop
  (13 axes plus one seam critic) until exact platform recall attestation and
  its host verifier exist; the two bounded infrastructure retries can raise
  the attempt count to 16 without creating additional DAG nodes;
- read-only OPS review falls from two calls to one (50%);
- generated native prompt bytes fall from 47,047 to 38,477 (18.22%) while
  exact-once tests retain required invariants;
- active role-memory bytes fall from 1,547,913 to 41,904 (97.29%), with every
  original payload recoverable; future durable promotion remains blocked until
  a trusted host supplies its external-attestation verifier;
- governed saved-workflow calls no longer inherit full parent history or root
  reasoning effort; native Codex mandatory closure stays blocked until the host
  can attest the exact fork boundary;
- saved-workflow call/retry caps and exact identity/history become auditable in
  one closure chain; native Codex fork/history, host liveness, deadlines, and
  cancellation remain explicit external limits.

These are structural results and engineering expectations, not a claim of
measured provider-token savings. A platform-attested A/B run is required for
that claim.

The change affects development-agent source/config/docs/tests only. It grants
no runtime, deploy, service, PostgreSQL, broker, Decision Lease, order, trading,
or secret authority.

## Rejected alternatives

- Treat cached input as free and change nothing.
- Force all work into one agent, losing independent hard-edge review.
- Lower all roles to one cheap model irrespective of judgment risk.
- Keep full-history forks and rely on prose asking agents to be concise.
- Add a second external orchestrator beside ADR-0050.
- Claim deadlines, cancellation, or actual token caps from fields the host
  cannot enforce or attest.
