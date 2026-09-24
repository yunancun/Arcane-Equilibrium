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

## Source-of-truth routing

Current-state source selection is explicit: `current_workflow_state` selects only
`TODO.md#Workflow optimization physical queue（source-only）`; `current_s2e_state`
selects the existing S2E dispatch projection. Workflow state alone at low or
medium uncertainty does not load S2E. Existing runtime/operations/claim and
high/unknown-uncertainty triggers remain intact. A stable query selects neither
current-state source. The `query` task shape still requires low risk, low
uncertainty and no direct interfaces; a medium-uncertainty read uses `review`
with its real direct interface.

Registry `markdown_section` sources bind an exact ATX heading, preserve its
section bytes and ignore headings inside fences. Missing, duplicate,
over-16-KiB selections or unclosed fences obscuring or inside the selected
section fail closed. An unclosed fence after a terminating peer/higher heading
does not invalidate the already-ended section. Selected `content_digest`
tracks selected bytes; full-file digest and baseline still track the whole
source. Unselected edits cannot be reported as an unchanged full artifact.
Python and generated saved-workflow admission recompute required source
kind/name/selector and shared/role inventory from the Registry and task facts.
Re-signing an artifact cannot authorize omitting or reclassifying a source.

Use `agent_governance.py context --role PM @task-facts.json` with the appropriate
typed surface. W3 integration and validation status live in `WORKFLOW_TODO.md`;
feature-worktree behavior does not establish daily-source adoption.

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
Unrelated TODO rows and unselected history must not change Context bytes, digest,
or planned tokens.

## Conditional detailed rules

Read the exact matching section in [bootstrap reference](bootstrap-reference.md) before action.
The pointer requires manual reading; the compiler does not automatically acquire the reference.

| Action | Required section |
|---|---|
| Handle Context budgets, evidence artifacts, saved workflows or specialized DAGs | [Elastic budget](bootstrap-reference.md#elastic-budget) |
| Make a runtime/PG claim or choose its evidence path | [Runtime and PG routing](bootstrap-reference.md#runtime-and-pg-routing) |
| Update rules, indexes or governed documentation | [Update rules](bootstrap-reference.md#update-rules) |
