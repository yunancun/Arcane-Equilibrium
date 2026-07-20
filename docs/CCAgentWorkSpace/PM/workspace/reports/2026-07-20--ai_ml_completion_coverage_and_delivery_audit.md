# AI/ML Completion Coverage And Delivery Audit

**Report ID**: `AIML-COMPLETION-COVERAGE-2026-07-20-V2`
**Baseline**: planning worktree based on `b486c0718d1c26820cdb6308cccf74c686547b22`
**Publication drift**: live read-only `git ls-remote` recheck confirmed GitHub
and local `origin/main=96d26245068cbfbc8d60e73fb8eb82c4109b0d40`;
the planning branch is seven commits behind and `TODO.md` overlaps. S0.1 must
integrate the current head, preserve the unrelated IBKR delta and rerun
current-head review.
**Mode**: planning-only source/document audit
**Runtime effects**: no successful PG query, mutation or runtime effect. During
source-pointer collection, one local shell command accidentally expanded the
literal backticked word `psql`; it attempted the default local socket and failed
with `database "ncyu" does not exist` before any audit query or data access.
This command-construction error is disclosed rather than counted as evidence.
**Formal plan**:
`docs/execution_plan/2026-07-19--ai_ml_long_lived_repair_and_landing_plan.md`
**Delivery protocol**: `docs/agents/ai-ml-landing-delivery-protocol.md`
**Progress ledger**: `docs/execution_plan/ai_ml_landing/PROGRESS.md`

## 1. PM Verdict

**`CURRENT_V1_TODO_COMPLETION_NOT_SUFFICIENT`.**

Completing V1 LR0-LR6 and ML0-ML8 would improve the system substantially but
would still permit a false closure at source/migration/shadow level. It did not
guarantee that an approved observer could query current PG state, that AIML
component effects could legally deploy and recover, that one runtime was proven,
that the exact loaded rows formed a PIT dataset, that a real consumer used a
qualified model, that the model changed the actual bounded-Demo decision path,
or that outcomes produced a second model generation.

V2 adds the missing work without adding root TODO umbrellas. A terminal trading
claim binds one `platform_scope`, exact decision-cell coverage, policy surface
and Shadow-to-Demo promotion edges. If every required V2 Session passes and the
ML10/S8.6 validator accepts the final head/runtime identity, the conclusion
`AIML_MODULE_LANDED_FOR_TRADING` is defensible. That conclusion does not promise
positive Demo economics, live activation or live profit.

## 2. Evidence Classification

### Confirmed Source Facts

1. `AGENTS.md:102-103`, `.codex/SUBAGENT_EXECUTION_RULES.md:114-115` and
   `docs/agents/development-agent-governance.md:335-337` deny direct `psql` until
   a local-socket/read-only-identity Adapter removes ambient `psqlrc` and `PG*`
   routing.
2. Repository search found policy references to that future Adapter but no
   implementation with the required local-socket, identity, query allowlist,
   scrub, TTL/hash/platform receipt and negative tests. Existing research
   `pg_readonly` flags and ALR phase observers are not this governance Adapter.
3. `helper_scripts/maintenance_scripts/deploy_intent_adapter.py:187-193`
   unconditionally returns blockers
   `DEPLOY_ROLLBACK_BINDING_UNAVAILABLE` and
   `DEPLOY_STABILITY_OBSERVATION_WINDOW_UNAVAILABLE`.
4. `docs/agents/development-agent-governance.md:358-366` states that
   `runtime_environment_probe_v1` is local-only and not platform attestation or
   remote transport, and that deploy apply fails before component invocation.
5. The existing generic deploy vocabulary is not a typed ownership/recovery
   matrix for credential rotation, PG role/migration, engine/Scanner, learning
   runtime, controller/workers and retention apply.
6. V1's terminal path could close at shadow serving. It did not require actual
   bounded-Demo action-policy integration or generation-2 consumption.
7. The V2 documents are currently dirty/untracked in an isolated feature
   worktree. They are not canonical program authority until Sprint 0 merge.
8. During final document review, GitHub `main` advanced seven commits to
   `96d262450...`; a live read-only recheck confirmed that head. Only `TODO.md`
   overlaps this planning write set. No merge or rebase was attempted in the
   dirty planning turn.

### Inferences From Confirmed Source

1. LR0.3 cannot legally produce current PG truth until LR0A is implemented or a
   separately authoritative external artifact is supplied.
2. A generic deploy receipt cannot prove recovery for every AIML component;
   typed effect ownership, exact intent, rollback/forward recovery and an
   independent stable-window postcheck are required.
3. An OCI-only design is premature. The project must prove its host/runtime seams
   and select OCI or a content-addressed fixed path, not maintain both.
4. A Scanner candidate JSON is not an immutable feature snapshot. Training must
   persist PIT feature vectors for selected events and reconstruct the matrix
   from actual loaded row IDs.
5. DB registry promotion before real-consumer ACK can create a model marked
   active but unused. One qualified writer/consumer path and consumer-acknowledged
   activation are required.
6. Without assignment probability, suppressed actions and same-event baseline,
   a Demo fill comparison is selection-biased and cannot establish model-caused
   incremental utility.

### Not Re-Observed In This Audit

- current Linux process/service/PG/disk/runtime state;
- current engine/Scanner/controller/worker/model-consumer identities;
- any current candidate, order, fill, fee, funding or profitability evidence;
- branch protection or external administrator settings.

The 2026-07-19 runtime facts remain prior evidence and may be stale. V2 requires
fresh platform/external-attested receipts before any runtime claim.

## 3. Gap And Correction Matrix

| Severity | V1 closure gap | V2 correction | Non-bypassable exit |
|---|---|---|---|
| P0 | Plan not canonical | LR-1 plus Sprint 0 exact-head adoption and durable ledger | `PROGRAM_ADOPTED` receipt |
| P0 | ADR-0049 shadow/no-serving authority could conflict with ML5/ML6 | Sprint 0 ADR/AMD update defining advisory authority, retraining, rollback and no direct broker authority | accepted authority source before implementation |
| P0 | Approved PG observation Adapter absent | LR0A local-socket/read-only identity, scrub, allowlisted SELECT, TTL/hash/platform receipt | independently valid PG read-only receipt |
| P0 | Deploy apply disabled and component ownership absent | LR0B per-component typed intent, effect allowlist, rollback/forward recovery, stable window and independent postcheck | `EFFECT_SEAMS_READY` |
| P0 | Identity/ACL provisioning implicit | LR0B/LR2 host UID, PG roles/auth mapping, socket ACL, secret lifecycle, negative tests and rollback | identity/ACL receipt |
| P0 | OCI assumed | LR0C bounded OCI/fixed-path proof and one selected runtime | runtime-choice receipt; no dual stack |
| P0 | Scanner loss invisible | LR4 monotonic cycle sequence, durable gap receipt, drop SLO and cohort exclusion | loss-aware handoff receipt |
| P0 | Candidate data not a materialized PIT matrix | ML2A fixed bounds/watermark, actual loaded row IDs, dataset/matrix hashes, immutable selected-event feature vectors and replay | PIT dataset receipt rechecked before fit |
| P0 | Mutable/late labels could contaminate fit | ML2A append-only maturity/revision including fills/funding corrections | revision-complete dataset admission |
| P0 | Legacy rows could serve | ML3 qualified-only V157-V160/PIT/fit trio and ML5 legacy fail-close | one qualified registry path |
| P0 | Fit trust chain incomplete | ML3 runner/attestor identity, ACL, secret rotation/revocation, trusted time/platform, reproducible env/rerun | trusted-fit receipt |
| P0 | Shadow/report may be mistaken for consumption | ML5A real registry-authorized Rust/downstream consumer with atomic canary, parity, latency fallback and rollback | independent consumer receipt |
| P0 | DB promotion could precede use | ML5/ML5A consumer-ACK activation and retirement/fail-close of cron, `_latest`, path-only/hash-null and DB-only writers | DB promotion impossible before ACK |
| P0 | Demo path lacked causal model effect | ML6 frozen action semantics, decision delta/veto, assignment probability, suppressed actions, same-event BBO and complete lifecycle | `DEMO_POLICY_INTEGRATED` |
| P0 | No autonomous generation 2 | ML7 natural outcome -> mature label -> retrain/evaluate -> either qualified new consumer ACK or verified `NO_CHANGE/REJECT_NO_PROMOTION` with Gen1 continuity | generation-2 receipt |
| P0 | Landing could mix evidence | ML9 scope/cell/environment-bound causal validity graph and independent mixed-lineage rejection | causal-time landing manifest |
| P1 | Selection bias untracked | ML1 full universe, reason, propensity and exploration budget | target-portfolio receipt |
| P1 | Python/Rust feature/action skew | ML2A per-value feature golden vectors and ML4 frozen action-policy parity | parity receipts at consumer |
| P1 | Dead-man/ModelOps response was prose | LR3/LR6 observability and ML7 SLO/action matrix | machine-enforced stale/failure actions |
| P1 | DR incomplete | ML8 PG queue, artifact, registry and receipt RPO/RTO plus isolated restore/re-hash | DR restore receipt |
| P1 | Final source sync could be called runtime closure | ML10 four-head source proof plus separate runtime identity attestation | both receipts current |

### Post-Draft Cold Review

Four independent post-draft lenses all returned `REJECT`. Their residual
findings were accepted and reworked:

| Severity | Residual defect | Final correction |
|---|---|---|
| P0 | S0.1 could issue program adoption before the serving-authority ADR/AMD. | S0.1 emits planning publication only; S0.3 alone issues adoption after S0.2 authority and governance bootstrap. |
| P0 | One coarse tuple mixed Shadow/Demo and let one candidate cover a family. | Separate platform scope, decision cell and evidence environment; landing binds explicit policy-surface coverage and promotion edges. |
| P0 | `NO_EDGE` conflicted with mandatory real-consumer/Demo/G2 evidence. | Add lawful platform-only no-candidate terminal; it is explicitly not trading landing. |
| P0 | ML9 could sign landing before final sync/runtime attestation. | ML9 emits a candidate only; S8.6 is the sole trading-landing issuer. |
| P0 | One compatible TTL window was temporally impossible. | Use a causal validity graph with effect-time authority, immutable consumed receipts and fresh terminal runtime health. |
| P0 | Effect work could self-classify as source-only and current Adapter IDs were not routable. | Session attempts bind classifier-derived effects; Registry/router/schemas/closure and bypass-negative tests gate `EFFECT_SEAMS_READY`. |
| P0 | PG observer creation and runtime selection/install had circular ordering. | Add typed external-admin observer bootstrap and offline -> host probe -> choice -> build -> install -> running-attestation order. |
| P0 | Scanner/labels/OOS/ML6/G2 could create statistical false closure. | Persist pre-filter universe, use bitemporal revisions and holdout ledger, freeze gate precedence, split mechanical/economic Demo proof and accept no-promotion G2. |
| P0 | Final closure metadata would drift the synchronized head. | Publish source-side metadata before final sync; S8.6 emits an immutable external terminal receipt and permits no later repo write. |
| P0 | Existing report sink was stdout-only and could not durably own terminal state. | S0.3/S1.2 add `terminal_receipt_sink_v1` with WORM append, typed actor/hash receipt and independent readback ACK. |
| P1 | DR/observer/admin hardening remained incomplete. | Off-host encrypted clean restore, independent observer/dead-man/alert and current GitHub admin-policy attestations are explicit Sessions. |

## 4. Delivery Design Verdict

The program is divided into Sprints 0-8 and bounded Sessions. Every Session has
one coherent work package, isolated branch/worktree, exact file manifest, one
publication lane and one closure. Its Waves are intake/guard, route/context,
bounded writers, E2 then E4 plus fact-triggered specialists, fix/review, local
validation, stable-head publication, classifier-derived governed runtime effect,
immutable closure and closure publication.

The role path is selected from facts rather than fixed theater:

- PM -> PA -> TW for authority/design/docs;
- implementation builder -> E2 -> E4;
- QC/MIT/AI-E for data/statistics/economics;
- CC/E3 for authority and security;
- OPS preflight and a different independent postcheck;
- BB only for Bybit Demo effects;
- QA then PM sign-off.

Hosted CI is stable-final-head evidence only for Rust, migration/ACL,
runtime/build, protected workflow or serving boundaries. Intermediate exact-head
source sync occurs only before Linux runtime gates. Sprint 8 performs the final
global Mac/GitHub/Linux ff-only sync and then a separate runtime identity check.

## 5. Guarantee Boundary

All required V2 Sessions and the ML10 terminal receipt permit this claim only:

> For the declared policy surface and covered cells, the engineered autonomous learning module is durably
> collecting, qualifying, fitting, evaluating, consuming, causally integrating
> into bounded Demo decisions, learning a second generation, recovering and
> reporting under the approved risk/authority boundary.

They do not ensure a profitable market opportunity exists. The following states
are deliberately distinct:

- `LEARNING_PIPELINE_FUNCTIONAL` / `AIML_PLATFORM_LANDED`;
- lawful but non-trading `AIML_PLATFORM_LANDED_NO_ELIGIBLE_CANDIDATE`;
- `CANDIDATE_SHADOW_ELIGIBLE` / `SHADOW_SERVING_READY`;
- `DEMO_POLICY_INTEGRATED` / `GENERATION_2_LOOP_PROVEN`;
- ML9 `AIML_LANDING_CANDIDATE`;
- ML10-only `AIML_MODULE_LANDED_FOR_TRADING`;
- optional `DEMO_ECONOMICALLY_QUALIFIED`;
- separately governed `LIVE_ACTIVATION_READY/ACTIVE`;
- `LIVE_PROFIT_PROVEN`, only from post-activation live fills.

## 6. Final Disposition

**`ACCEPT_V2_FOR_PROGRAM_ADOPTION`**.

After the final targeted corrections, architecture/authority,
operations/runtime, quant/statistics and failure/delivery reviewers each
returned `ACCEPT`. The two root TODO rows now cover every defect found by this
audit, and the delivery protocol is resumable without a long-running chat. This
is acceptance of the conditional plan, not a guarantee that a profitable
candidate exists.

This is not `PROGRAM_ADOPTED`, `FOUNDATION_READY` or any runtime/economic state.
No code, test, CI, commit, push, merge, source sync, SSH, successful PG query,
deploy, restart, credential, retention, broker or order effect is authorized by
this report. The failed accidental local-socket attempt disclosed in the header
returned no project data and created no runtime mutation.
