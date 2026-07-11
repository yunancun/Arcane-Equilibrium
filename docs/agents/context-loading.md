# Agent Context Loading

Purpose: route exact evidence without universal preload or quality-destroying
compression. Canonical packs and elastic envelopes live in
`.codex/agent_registry_v1.json`; executable compiler:
`helper_scripts/maintenance_scripts/agent_governance.py context`.

## Minimal startup

Repository entry reads only the entry shim/rule, generated PM role Adapter, and
this router. PM then binds task facts and compiles the relevant pack. Do not read
all role memories/reports, full README, TODO, CONTEXT, ADRs, inventory, and both
operating memories before knowing the task.

## Mandatory exact capsule

The following are lossless and never removed to meet a token target:

- user objective, exact scope, acceptance, hard stops
- current source head and dirty scope
- direct Interface/callers affected by a source change
- relevant Root Principle/Hard Boundary/ADR denial
- latest blocker/runtime freshness when a current-state claim is made
- previous failed check, concern, or dissent that remains relevant
- task-specific evidence contract

If one is missing, acquire it or return `NEEDS_CONTEXT/UNVERIFIED`. Generic
summary is not a substitute.

These facts are normalized into one exact `task_contract`: task shape, sorted
surfaces, risk, runtime/end-to-end claims, `side_effect_class`, objective, scope,
acceptance, hard stops, source baseline, direct interfaces, and previous failure.
Any prior/evidence digest that may determine a verdict is also admitted under
`claim_inputs`; the free-form prompt is not an authority channel for replacing
it. The canonical task-contract digest follows the Context artifact into every
role fragment and final closure. A later prompt, fragment, or summary cannot
silently widen scope, change acceptance/evidence inputs, or switch effect class.

## Source-of-truth routing

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

## Context packs

The Registry defines packs; the compiler selects and deduplicates pointers:

- `core`: relevant product/root/hard-boundary sections
- `active_state`: TODO only when current state can change the answer
- `architecture`: CONTEXT + relevant ADR
- `source_change`: diff, direct interfaces/callers, focused acceptance tests
- `runtime`: active evidence + sub-agent hygiene
- `broker_bybit` / `broker_ibkr`: correct venue review/reference sources
- `ml_data`: lineage, feature/label/CV, training/serving evidence
- `gui_visual`: browser/viewport/keyboard/accessibility/screenshot evidence
- `docs`: placement and relevant indexes
- `history_on_demand`: only the directly relevant memory/report shard

Role memory is historical judgment support, not an automatic startup dependency.

## Elastic budget

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
digests, capture TTLs, token estimate, and compiler budget authority, then embeds
the same verified plan bytes and reuses them on retry. Exact `task_prompt` and
required uncertainty are part of the normalized task contract; prompt swap or
omission fails before a call. Closure separately revalidates the PM admission
artifact and binds every fragment to its digest. Every model call is then
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
Registry budget profiles and rejects byte drift, shadow declarations, real
import/require statements, or an unused common-prefix helper. Every call begins
with the exact `canonical_plan` bytes already recorded by `artifact_digest`,
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

## Runtime and PG routing

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
   The deploy contract currently validates exact intent but apply remains
   disabled until a trusted local runtime identity probe exists. Development-
   agent broker/private/external contact has no closure-admissible Adapter and
   routes to an explicit unsupported-effect blocker; IBKR/Bybit implementation
   paths are reference surfaces, not authorization.

## Update rules

- Current state -> `TODO.md`.
- Stable architecture -> README/CONTEXT/ADR.
- Agent Interface -> Registry, renderer, this router when pack routing changes.
- Evidence -> closure/report/archive, linked rather than pasted.
- Durable new lesson -> memory promotion at PM closure only.
- Generated `.claude/agents/*.md`, `.codex/agents/*.md`, and
  `docs/CCAgentWorkSpace/*/profile.md` views are never hand-edited.
