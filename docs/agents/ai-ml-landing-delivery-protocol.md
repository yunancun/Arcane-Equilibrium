# AI/ML Landing Delivery Protocol

**Protocol ID**: `AIML-LANDING-DELIVERY-V1`
**Date**: 2026-07-20
**Owner**: PM
**State**: `DESIGNED_NOT_ADOPTED` until Sprint 0 exact-head merge
**Plan**: `docs/execution_plan/2026-07-19--ai_ml_long_lived_repair_and_landing_plan.md`
**Ledger**: `docs/execution_plan/ai_ml_landing/PROGRESS.md`

## 1. Purpose And Boundaries

This protocol completes the two root AI/ML TODO umbrellas through bounded,
resumable engineering work. It is not an open-ended loop, cron schedule,
`ScheduleWakeup`, daemon, Codex-head wrapper or trading runtime. Progress lives
in the repository ledger, not session memory.

One Program contains Sprints 0-8. A Sprint contains bounded Sessions. A Session
owns one coherent work package, one isolated branch/worktree, one exact file
manifest, one PM publication lane and one closure. A Wave is the ordered set of
role actions inside a Session.

Every landing state binds `platform_scope`, `policy_surface_id`, explicit
`decision_cell` coverage and evidence-environment promotion edges as defined by
the formal plan. Ledger rows are instantiated by
`(session_id, landing_scope_id, cohort_epoch, attempt)`; a generic row is only a
template and cannot receive runtime completion.

## 2. Session Intake Contract

Every Session starts by reading `AGENTS.md`, the generated PM Adapter and
`docs/agents/context-loading.md`, then the current `TODO.md`, this protocol, the
formal plan and `PROGRESS.md`. PM must:

1. fetch read-only source truth and run the branch/head/dirty guard;
2. stop on `main`, detached HEAD, wrong checkpoint, collision or unowned dirty
   state; never stash, reset, clean or absorb it;
3. select exactly one `PLANNED`/`READY` Session whose dependencies have current
   receipts;
4. bind objective, exact paths, acceptance, hard stops, source baseline,
   uncertainty, claim inputs and evidence validity class;
5. compile the hybrid role DAG with `agent_governance.py route/context`;
6. before W1, CAS-create the authoritative Report-Sink `session_attempt_v1`
   claim with owner, lease epoch/expiry/heartbeat, branch/worktree,
   baseline/checkpoint head, exact path manifest and consumed dependency
   generations;
7. mark the projection `IN_PROGRESS` only after the CAS claim succeeds; do not
   mark later Sessions complete by inference.

The immutable `session_attempt_v1` also records exact DAG node IDs/classes,
writer path ownership/predecessors, required semantic rechecks, CI classifier
digest/workflows/invocation history/fingerprints, and classifier-derived
`required_effects`, `adapter_id`, actor node, rollback and independent postcheck
node. PM input cannot downgrade a classified effect to `NONE`.

A stale/revoked dependency, head change, scope/environment mismatch or invalid
receipt returns the row to `BLOCKED_STALE_EVIDENCE`. Class-specific invalidity
recursively demotes every transitive dependent attempt. `CURRENT_STATE_TTL`
expiry does; the natural later expiry of legally consumed
`EFFECT_TIME_AUTHORITY` does not invalidate its
`IMMUTABLE_CONSUMED_EFFECT`. Only explicit retroactive compromise/revocation
does. `IMMUTABLE_LINEAGE` remains valid until hash/causality failure. A later row
never keeps `DONE` by copying an invalid verdict.

## 3. Normative Session Waves

| Wave | Work | Exit |
|---|---|---|
| W0 Intake/guard/claim | PM checks branch/head/dirty scope and dependencies, then CAS-creates the durable attempt claim and owner lease before any agent work. | Clean scope, exact checkpoint and one exclusive live claim. |
| W1 Route/context | PM compiles only fact-triggered agents and immutable Context artifacts. | Valid task/DAG/context digests. |
| W2 Build | One builder by default; maximum two writers only for disjoint paths. TW/PM metadata writers are serialized after business writers. | Owned patch and mutation receipt per writer. |
| W3 Independent review | Source implementation always receives E2 then E4. Add QC/MIT/AI-E for ML semantics; CC/E3 for authority/security; OPS for runtime/deploy; BB only for Bybit Demo; QA for acceptance. | Explicit fragments; no unresolved P0/P1 or hidden dissent. |
| W4 Fix/review | Builder fixes accepted findings; affected reviewers recheck the new generation. | Current-generation acceptance. |
| W5 Local validation | Run focused and adjacent regression, deterministic receipt/schema checks and `git diff --check`. | Reproducible local proof at exact head. |
| W6 Publication | PM alone stages exact paths, commits subject+body, runs publish guard, pushes once, requests one current-head review/CI set and exact-head merge. | Remote branch and merged head match reviewed head. |
| W7 Effect classification/gate | Closure derives the effect class from work-package/path/interface facts. `NONE` is typed and justified; otherwise OPS preflight -> exact approved intent -> admitted Adapter -> distinct OPS postcheck. Bybit Demo also requires E3/BB and current authority. | Platform/external-attested receipt or honest blocker; no self-classification bypass. |
| W8 Closure | QA verifies acceptance; PM emits immutable `closure_packet_v1`/Report Sink record and updates the ledger projection without erasing dissent. | Authoritative closure plus bounded metadata delta. |
| W9 Closure publication | Publish the post-effect metadata delta through the same exact-head PM lane, or reference an immutable authoritative Report Sink when the final no-write rule applies. | Durable cross-Session resume point; remote head/projection reconciled. |

No fixed-agent theater is allowed. Optional roles are admitted only when a fact
can change the decision. A builder cannot be its only verifier; an effect actor
cannot independently postcheck itself; PM cannot erase reviewer dissent.
Role strings in the ledger are route templates, not executable DAGs. Every
attempt expands them into distinct node IDs/classes/permissions/predecessors.
ML semantic reviewers inspect the post-E2/E4 current generation; `OPS preflight`
and `OPS postcheck` are distinct nodes and actors.

## 4. Retry, Stop And Resume

- Missing context: acquire the exact missing source, then recompile context.
- API/null interruption: one checkpoint-aware relay may resume completed work.
- Same finding or failure fingerprint twice: stop retries and rescope the work,
  test strategy or capability. Do not publish another unchanged head.
- Stale receipt/head/scope/window: invalidate dependent status and refresh from
  the owning Session.
- Dirty/colliding path: stop with the exact inventory; do not widen ownership.
- Hard policy, external authority or operator blocker: record owner and unblock
  condition; continue only independent no-effect Sessions whose dependencies do
  not rely on the blocker.
- Runtime failure: preserve before/after identity and rollback evidence; do not
  turn source PASS into runtime PASS.
- `OPERATOR_STOP_NOW` has highest priority. Preserve the exact checkpoint and
  handoff; perform no further design, test, publication, sync or runtime effect
  until the operator explicitly resumes.
- A terminated Session resumes from the last clean exact-head checkpoint and
  current ledger row. No narrative from an old chat is authoritative.
- Attempt lease expiry enters `RECOVERY_REQUIRED`; a new owner must CAS-adopt the
  recorded clean checkpoint and dependency generations. Only CAS finalization
  may close an attempt, preventing two Sessions from owning one instance.

## 5. CI And Publication Economics

Local focused and adjacent tests are mandatory. Hosted CI is used only for a
stable final head when the change touches:

- Rust engine/real model consumer;
- migration, PG role or ACL;
- selected OCI/fixed-runtime build and deployment boundary;
- protected workflows;
- production serving or order-policy integration.

Docs-only and narrow Python Sessions are local-first and do not trigger hosted
CI unless an existing required path classifier does so. Publish one final head;
never use CI as the edit-debug loop. Current-head review/CI becomes stale after
any head change. The attempt record stores classifier digest, selected workflows,
head, invocation count, failure fingerprint and disposition. A second identical
fingerprint cannot be hidden by a new Session or empty rerun.

## 6. Sprint And Session Map

### Sprint 0 - Adopt Authority, Plan And Ledger

- `S0.1`: review V2 plan/TODO/protocol/ledger/audit, publish exact head and emit
  only `planning_documents_published_v1`.
- `S0.2`: update or supersede ADR-0049/required AMD so ML5/ML6 do not silently
  contradict shadow/no-serving policy. Define advisory-only model authority,
  retraining boundary, fail-closed rollback and permanent denial of direct model
  broker authority; emit `serving_authority_receipt_v1`.
- `S0.3`: bootstrap scope/attempt/receipt/effect schemas, Registry/router/closure
  integration and current GitHub admin attestation for required PR/checks,
  force/delete denial and routine-bypass denial. Only this Session emits
  `program_adoption_receipt_v1`.

No ML5/ML6 source, schema, runtime or effect implementation begins before S0.3.

### Sprint 1 - Effect Seams And Runtime Choice

- `S1.1`: LR0A PG read-only identity Adapter.
- `S1.2`: LR0B typed AIML component effect/rollback/postcheck contracts and the
  external immutable `terminal_receipt_sink_v1` Adapter.
- `S1.3`: host UID/PG role/auth/socket ACL/secret lifecycle provisioning and
  negative tests.
- `S1.4`: LR0C OCI versus fixed-path runtime spike and single choice.
- `S1.5`: deploy Adapter implementation for admitted component classes and
  independent remote/platform attestation.
- `S1.6`: typed isolated target-host disposable probes through S1.5, exercising
  start/stop/failure/rollback/cleanup for both candidates, then final
  single-runtime choice. No production running-runtime claim.

S1.1-S1.4 may overlap only where path manifests are disjoint. S1.5 depends on
their accepted contracts; S1.6 depends on S1.4/S1.5. `EFFECT_SEAMS_READY`
requires governance Registry/router/schema/closure wiring, bypass-negative tests
and disposable apply/rollback/postcheck, not contract prose alone.

### Sprint 2 - Runtime Stabilization And Immutable Runtime

- `S2.0`: minimal typed external-admin bootstrap of the production PG observer
  role/auth mapping/ACL, followed by independent write/role/search-path denial.
- `S2.1`: LR0 evidence/quiescence/static guards.
- `S2.2A`: LR1 scoped compatibility source implementation and source receipt.
- `S2.2B`: post-S2.5 runtime revalidation of the same immutable manifest.
- `S2.3`: LR2 sealed build and trust/identity chain; no running attestation.
- `S2.4`: typed credential/role/unit effects, one-component restore and
  independent postchecks.
- `S2.5`: running-runtime attestation, watchdog reset last, independent
  observer/dead-man gates and rollback drill.

S2.1 production PG observation depends on S2.0. S2.4 requires
`S2.2A@SOURCE_READY`; only S2.2B may issue LR1 runtime `DONE` after S2.5. An
intermediate exact-head three-side source integration checkpoint is required
immediately before S2.4 because Linux runtime evidence must bind the reviewed
head. It is not the final global sync or deploy proof. S3.1A/S3.1B use the same
split rule below; source readiness never masquerades as runtime completion.

### Sprint 3 - Controller, Scanner, Retention And Foundation

- `S3.1A`: LR3 source queue across target -> dataset -> fit -> evaluate -> export ->
  serve -> retention, with epoch/attempt/fencing/retry/DLQ/replay/double-apply/
  concurrency tests.
- `S3.1B`: post-S2.5 runtime queue/controller/worker verification and receipt.
- `S3.2`: LR4 loss-aware Scanner sequence/gap/drop-SLO handoff.
- `S3.2A`: pre-filter eligible universe, PIT inputs, reasons, choice,
  policy/RNG and honest assignment-probability persistence.
- `S3.3`: LR5 physical retention/backpressure/deleter/restore.
- `S3.4`: LR6 failure matrix, independent resident observer/external alert sink,
  dead-man SLOs, 72-hour/two-cycle soak and `FOUNDATION_READY`.

### Sprint 4 - Scope, Target, Labels And PIT Data

- `S4.1`: ML0 platform scope/policy surface/cell coverage/environment promotion,
  cohort and current-machine baseline.
- `S4.2`: ML1 full-universe/propensity/exploration target portfolio.
- `S4.3`: ML2 candidate-matched bitemporal label/proof/reward revisions.
- `S4.4`: ML2A actual-loaded-row PIT dataset, immutable selected-event feature
  vectors, backfill/replay and Python/Rust per-value golden parity.

### Sprint 5 - Trusted Fit, OOS And Registry

- `S5.1`: ML3 trusted-fit host chain and qualified-only reproducible runner.
- `S5.2`: ML4 frozen action policy/authority lattice, holdout-consumption ledger
  and adversarial OOS/economic gate.
- `S5.3`: ML5 single qualified registry writer, legacy-path fail-close and
  shadow serving foundation.

### Sprint 6 - Real Consumer And Bounded Demo Integration

- `S6.1`: ML5A registry-authorized Rust `IntentProcessor + EdgePredictorStore`,
  ORT/runtime proof, atomic canary, feature/action parity, restart recovery,
  latency fallback and rollback.
- `S6.2`: registry two-phase activation; DB promotion cannot succeed before real
  consumer ACK. Retire/fail-close cron, `_latest`, path-only/hash-null and DB-only
  model writers.
- `S6.3`: ML6 required mechanical decision-delta instrumentation plus optional
  preregistered economic estimator with portfolio/time-block interference,
  estimand, overlap, MDE/power, stopping and washout.
- `S6.4`: separately authorized bounded Demo policy integration, required
  mechanical receipt and optional economic receipt.

S6.4 requires an intermediate exact-head source sync and distinct runtime
attestation before E3/BB review. Shadow-only evidence cannot close Sprint 6.

### Sprint 7 - Generation 2, DR And Landing Certification

- `S7.1`: ML7 natural controller-triggered generation-2 evaluation using new
  post-Gen1 mature labels; `NO_CHANGE`/`REJECT_NO_PROMOTION` are valid. A policy
  activation requires a fresh effect gate.
- `S7.2`: ML8 encrypted off-host PG/artifact/registry/receipt/runtime-manifest
  backup, clean-target restore, key recovery, corrupt-backup tests and RPO/RTO.
- `S7.3`: ML8 seven unattended days with independent dead-man observation,
  alert delivery and nonzero natural workload.
- `S7.4`: ML9 independent causal-time landing-manifest verification, emitting
  only `AIML_LANDING_CANDIDATE`.
- `S7.NC`: independent no-candidate platform terminal. It requires
  `FOUNDATION_READY`, complete pre-filter universe/propensity, frozen eligibility
  policy and observed no-eligible result, retention/DR, seven unattended days
  and QC/QA verification. It emits only
  `aiml_platform_no_candidate_candidate_v1`. Candidate-instance Sessions
  S4.3-S7.1/S7.4 may be verifier-approved
  `NOT_APPLICABLE_NO_CANDIDATE`; they are never `DONE`, and P1 remains open.

Exit: the trading branch emits `AIML_LANDING_CANDIDATE`; the no-candidate branch
emits `aiml_platform_no_candidate_candidate_v1`. Neither is a terminal landing
state, and Sprint 7 issues no terminal receipt.

### Sprint 8 - Global Closure And Synchronization

- `S8.1`: stabilize one release-candidate head and integrate every known fix and
  source-side closure projection; freeze it.
- `S8.2`: run the full adversarial source/data/ML/effect audit, current-head
  review, required CI and fresh GitHub admin-policy attestation on that exact
  frozen head. Any change returns to S8.1.
- `S8.3`: exact-head merge through the PM publication lane; no source-side
  closure write remains.
- `S8.4`: clean Mac main ff-only, GitHub exact head, clean Linux main ff-only and
  four-head probe; deploy only through the already admitted typed effect seam if
  the final runtime digest changed.
- `S8.5T`: emit `aiml_final_runtime_attestation_v1` profile `TRADING`, covering
  selected runtime, engine, Scanner, controller, workers, observer,
  retention/deleter, watchdog, queue/watermark, units/env/cgroups, UIDs/PG
  roles/ACLs, migrations, registry ACK, loaded model, dead-man and DR freshness.
- `S8.5NC`: emit profile `NO_CANDIDATE` for the platform branch. It requires the
  same platform/runtime/observer/retention/DR health, but proves absence of active
  model, registry promotion, consumer and order authority instead of fabricating
  trading evidence.
- `S8.6`: final reconcile and terminal validation. Append the immutable external
  receipt through `terminal_receipt_sink_v1`; only successful typed append plus
  independent readback ACK may issue `AIML_MODULE_LANDED_FOR_TRADING`. No repo
  write is allowed afterward.
- `S8.NC`: alternate final validator after S8.5NC and S7.NC. It may append only
  `aiml_platform_no_candidate_receipt_v1` through the same WORM sink; it cannot
  close P1 or issue a trading state. The same readback and no-write rules apply.

## 7. Synchronization Rules

All source synchronization follows `.codex/SYNC.md`. Feature branches publish
without force; merges bind the reviewed exact head. Mac and Linux `main` update
ff-only after clean/divergence preflight. Dirty/diverged/wrong-head state stops;
no self-repair by reset/stash/clean.

Intermediate synchronization is used only at S2.4 and S6.4, or another explicit
runtime-evidence dependency admitted by PM. It makes exact source available to
Linux and does not imply runtime deployment. Sprint 8 performs the one final
global synchronization after all source-side implementation, audit and closure
metadata are frozen. The S8.6 terminal receipt is stored outside the repository
so it does not create a new head. Any post-S8.6 repo mutation invalidates the
final-head claim and requires another reconcile.

## 8. Completion Rule

The repo ledger is a projection of immutable attempt/closure records. The
Program's trading target closes only when every required instantiated row is
`DONE`, every dependency edge is valid, `AIML_LANDING_CANDIDATE` passed required
ML6 mechanical integration and ML7 generation-2 evaluation, Sprint 8 source
heads reconcile, and S8.6 validates fresh full runtime identity. Only then is
`AIML_MODULE_LANDED_FOR_TRADING` issued.

If no candidate qualifies, the platform may close as
`AIML_PLATFORM_LANDED_NO_ELIGIBLE_CANDIDATE`; this is correct autonomous
operation but not trading landing. `DEMO_ECONOMICALLY_QUALIFIED=false`, no live
activation or `LIVE_PROFIT_PROVEN=false` does not block a candidate's engineering
trading landing. Missing mechanical Demo integration, generation-2 evaluation,
DR restore, final runtime identity or causal scope lineage does.
