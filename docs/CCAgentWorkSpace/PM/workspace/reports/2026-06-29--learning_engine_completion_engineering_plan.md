# 2026-06-29 Learning Engine Completion Engineering Plan

Scope: PM integration of read-only QC / MIT / AI-E / PA subagent review after the 2026-06-29 ML runtime audit.

Dispatch chain:

- Required PM-first direction used.
- Quant/ML/data judgment: `PM -> QC -> MIT -> AI-E -> PM`.
- Architecture judgment: `PM -> PA -> PM`.
- E1/E2/E4/QA were skipped because this is a report-only engineering arrangement, with no source implementation or test patch.
- E3/BB are deferred to any future runtime installation, restart, cron change, Bybit/probe/order path, or effect-capable mutation review.

PM SIGN-OFF: **DONE_WITH_CONCERNS / ENGINEERING PLAN APPROVED, RUNTIME MUTATION BLOCKED**.

Triple adversarial audit addendum: **PASSED AFTER HARDENING**. The plan is sufficient to complete the learning-engine Module chain if every phase and hardening gate below is completed. This is an engineering-completion claim, not a guarantee that future market alpha exists or stays profitable.

## Executive Verdict

Current state is not a complete learning engine.

DreamEngine is **not stalled**, but it is only a read-only advisory producer. It emits heuristic parameter proposals into the learning/advisory lane; it does not prove effective learning by itself and must not mutate live behavior directly.

The general learning engine is **partially alive but degraded / core-loop stalled**. Fresh PG rows prove feature/advisory/statistical activity, but the scheduler, training maintenance, model registry, experiment/hypothesis ledger, and fill-backed proof loop are not green.

Effective learning is **not yet proven**. Current artifacts show useful observation and advisory work, but not a closed loop from candidate-matched evidence to non-empty Demo mutation to after-cost outcome improvement with proof exclusions cleared.

## Current Runtime Facts

Runtime facts are from the 2026-06-29 audit and subagent review:

- `openclaw_engine` was running, mainnet disabled, paper disabled, bounded demo probe adapter enabled, and learning lane artifact writer enabled.
- `learning.decision_features`, `learning.mlde_shadow_recommendations`, `learning.linucb_state`, `learning.james_stein_estimates`, `learning.cost_edge_advisor_log`, and `learning.mlde_param_applications` had fresh 2026-06-29 rows.
- Latest DreamEngine and MLDE rows were advisory/proposal rows; latest applications were mostly `skipped|dedupe` or `skipped|empty_patch`.
- Runtime `crontab -l` was empty, while demo-learning stack health artifacts claimed older 2026-06-27 state. The active scheduler SSOT is therefore untrusted.
- `ml_training_maintenance_status.json` was `error`, including quantile trainer / DB readiness issues.
- `learning.model_registry` latest row was stale at 2026-04-24, while some ONNX artifacts were newer than registry metadata.
- Cost-gate probe ledger had many records but no `allowed_to_submit_order=true` and no `promotion_evidence=true`.
- Latest probe ledger decision was blocked by stale/missing plan generation, not by successful bounded Demo outcome proof.
- `learning.ml_parameter_suggestions`, `learning.ai_usage_log`, `learning.teacher_directives`, `learning.hypotheses`, `learning.experiment_ledger`, and `learning.decision_shadow_fills` were empty.
- Weekly review, foundation model features, and Bayesian posterior tables were stale relative to active advisory rows.

## Effective Learning Definition

A complete and effective learning engine must show this minimum closed loop:

1. Candidate-matched input is captured from immutable feature snapshots and decision context.
2. Labels are fill-backed where promotion is concerned: order id, fill id, fee, slippage, entry/exit, markout window, and engine mode are attributable.
3. A statistical or model Module produces a reproducible judgment with schema hashes, source hashes, sample size, and proof tier.
4. The judgment becomes a normalized `AdvisoryProposal`, not a direct runtime action.
5. A deterministic adjudicator classifies the proposal and rejects stale, blocked-only, replay-only, or heuristic-only evidence.
6. Demo-only eligible proposals produce a non-empty, non-duplicate bounded patch under a fresh health snapshot and rollback snapshot.
7. The patch is applied only through the governed Rust/IPC path and only in the allowed Demo envelope.
8. Post-change outcomes are measured by candidate-matched fills after real fees, slippage, capacity, and execution realism.
9. Promotion review requires OOS/repeat evidence, controls, multiple-testing correction, PSR/DSR/PBO or equivalent statistical gates, and proof exclusions cleared.
10. Live applicability remains gated by GovernanceHub, Decision Lease, Guardian/Rust authority, and the five live gates.

Blocked-signal markout proxy, artifact refresh count, replay-only positive result, DreamEngine expected-improvement heuristic, dedupe/empty_patch skip, or stale plan refresh does **not** count as effective learning.

## Target Architecture

The required architecture is a deeper Module chain with explicit Interfaces. The current problem is not one missing script; it is shallow Depth across several Seams.

| Module | Interface | Implementation Direction |
|---|---|---|
| Scheduler Health | `LearningStackHealthSnapshot` | Aggregate cron/service firing, heartbeat age, ML maintenance status, ledger freshness, registry freshness, artifact/PG parity, and fail reason. Unknown/stale means fail-closed. |
| Learning Ledger | `LearningEvent` | First wrap existing JSONL/artifacts with hashes and proof tiers; then dual-write/diff into PG before any PG-first cutover. |
| Feature/Label Attribution | `LearningAttribution` | Link decision context, feature snapshot, order/fill ids, fees, slippage, label window, proof tier, and engine mode. |
| Advisory Producers | `AdvisoryProposal` | DreamEngine, MLDE shadow, LinUCB, James-Stein, and CostEdge become Adapters into one proposal Interface. |
| Proposal Compiler | `LearningOutputPacket` | Compile observation, lesson, hypothesis, experiment, verdict, parameter delta, patch preview, proof exclusions, and non-actionable reason. |
| Proposal Adjudicator | `ProposalDecision` | Deterministically classify `REJECT`, `RESEARCH_ONLY`, `DEMO_ELIGIBLE_PARTIAL`, `DEMO_MUTATION_PROPOSAL`, or `PROMOTION_REVIEW_REQUIRED`. No orders, no IPC, no Cost Gate lowering. |
| Demo Mutation | `DemoMutationEnvelope -> ApplicationResult` | Consume only adjudicator-approved Demo envelopes; require fresh health, bounded patch, before/after snapshot, rollback, IPC response, and recommendation lineage. |
| Training Ledger | `TrainingRunManifest` | Record dataset query/hash, time window, schema hash, split manifest, purge/embargo/CPCV, metrics, artifact hashes, and verdict. |
| Model Registry/Reloader | `ModelServingSnapshot` | Registry row, q10/q50/q90 trio completeness, feature schema hash, artifact hash, loaded runtime version, edge snapshot freshness, and fallback reason. |
| Proof/Promotion | `ProofPacket -> PromotionVerdict` | Candidate-matched fills, after-cost performance, controls, OOS/repeat, DSR/PBO, tail/capacity, and proof exclusions. |
| Contract Versioning | `LearningContractVersion` | Version every learning Interface, schema, artifact, and proposal packet so migration is explicit and old writers cannot silently keep running. |
| Contract Test Harness | `LearningContractTestSuite` | Exercise every external Seam with golden fixtures, negative authority tests, replay fixtures, schema compatibility, and fail-closed cases. |
| Operations Control | `LearningRunbookSnapshot` | Define install, rollback, restart, alert, backfill, retention, and recovery drills for the learning stack. |
| Budget/Backpressure | `LearningBudgetGuard` | Bound training, AI, scheduler, DB, disk, and runtime load; fail closed when budget or queue pressure is exceeded. |
| Legacy Retirement | `LegacyRetirementPacket` | Prove old schedulers, writers, readers, artifacts, and bypass paths are either archived read-only or deleted after the new Interface passes parity. |

This gives better Leverage and Locality: each producer can improve independently, while proposal, mutation, registry, and promotion rules remain centralized and auditable.

## Engineering Phases

### Phase 0: Baseline Audit Packet

Create a stable read-only audit packet that records the current state: crontab empty, health artifact stale, training maintenance error, registry stale, advisory rows fresh, probe ledger blocked, and fill-backed proof insufficient.

Acceptance evidence:

- One PM-readable packet with source/runtime/artifact timestamps.
- Clear `LEARNING_STACK_DEGRADED` verdict.
- No DB write, no cron edit, no restart, no runtime mutation.

### Phase 1: Scheduler Health Interface

Implement `LearningStackHealthSnapshot` as the single health Interface for learning.

Required checks:

- Expected cron/systemd scheduler is present and unique.
- Heartbeats fresh for demo learning, sealed horizon, cost-gate lane, and ML training maintenance.
- Last two maintenance cycles are `ok`, including LinUCB, MLDE shadow advisor, DreamEngine, demo applier, scorer, and quantile/data-readiness gates.
- Healthcheck fails hard on empty crontab, stale artifact, status error, ONNX newer than registry, registry stale, artifact refreshed without PG/ledger parity, or no fill-backed evidence.

Done means current runtime is correctly classified as degraded until repaired.

### Phase 2: Learning Ledger SSOT Wrapper

Wrap the current JSONL/artifact lane into `LearningEvent` before any PG cutover.

Required work:

- Preserve source file hash, generated timestamp, event type, candidate id, proof tier, and source refs.
- Explicitly label blocked-signal markout as `blocked_markout_proxy`.
- Quarantine malformed/missing-hash events.
- Add dual-write/diff/reconstruction plan for eventual PG-first SSOT.

Done means artifact lane can be audited consistently without pretending it is fill-backed proof.

### Phase 3: Advisory Proposal Compiler

Normalize all learning producers into one `AdvisoryProposal` / `LearningOutputPacket` Interface.

Required producers:

- DreamEngine.
- MLDE shadow advisor.
- LinUCB.
- James-Stein estimates.
- CostEdge advisor.
- Future AI/hypothesis modules.

Required fields:

- Candidate identity and source refs.
- Feature schema hash and current parameter hash.
- Evidence tier and proof exclusions.
- Expected mechanism and uncertainty.
- Parameter delta and patch preview.
- `mutation_allowed=false` by default.
- Non-actionable reason when patch is empty, duplicate, stale, out of range, or proof is insufficient.

Done means empty patches are visible before the applier and cannot silently masquerade as learning progress.

### Phase 4: Proposal Adjudicator

Create a deterministic adjudicator between proposals and any Demo mutation.

Rules:

- Reject stale health, stale plan, blocked-only proxy, replay-only positive result, cleanup/unattributed fills, single-window positive result, and heuristic-only evidence.
- Research-only proposals can continue to populate review packets.
- Demo mutation proposals require fresh health, non-empty bounded patch, current parameter hash match, evidence tier, and rollback plan.
- Promotion review requires fill-backed proof and statistical gates.

Done means current runtime produces `INSUFFICIENT_FILL_BACKED_PROOF`, not promotion readiness.

### Phase 5: Demo Mutation Envelope

Re-cut `mlde_demo_applier` so it only consumes `DemoMutationEnvelope`.

Acceptance evidence:

- At least one Demo-only recommendation produces a non-empty, non-duplicate patch in a dry-run/controlled envelope.
- Applied result records recommendation id, source proposal id, before/after snapshot, patch keys, IPC response, rollback handle, and fail-closed reason if skipped.
- Dedupe/empty_patch/dry-run are excluded from effective learning counts.
- Any non-Demo, stale, out-of-envelope, or missing-health envelope is skipped.

Done means the system can prove a governed Demo behavior change without live authority.

### Phase 6: Training Ledger and Model Registry Repair

Repair the model training and registry loop.

Required work:

- Split data-readiness failures from generic trainer errors.
- Fix DB DSN/env and registry write path so artifact generation without registry row hard-fails.
- Store q10/q50/q90 quantile trio atomically.
- Require training run manifest with dataset hash, schema hash, sample size, purge/embargo/CPCV split manifest, metrics, artifact sha, and verdict.
- Registry freshness must cover shadow/canary rows, not only production rows.

Done means a model artifact can be traced to training data, validation, registry row, and runtime serving snapshot.

### Phase 7: Model Serving Snapshot

Expose `ModelServingSnapshot` from Python registry and Rust/edge loader.

Required checks:

- Registry row exists and is fresh.
- Artifact hashes match.
- Feature schema hash matches runtime feature Interface.
- Trio completeness is present where required.
- Runtime loaded version equals registry intent or explicitly falls back.
- Fallback/rule-based mode is visible, not hidden as ML inference.

Done means registry status and runtime inference status agree, even if the correct action is fail-closed fallback.

### Phase 8: Proof and Promotion Gate

Build `ProofPacket -> PromotionVerdict` as the only promotion path.

Required evidence:

- Candidate-matched Demo fills.
- Real fees, slippage, spread, capacity, execution realism, and tail risk.
- OOS/repeat sample set.
- Controls and matched baseline.
- Multiple-testing correction.
- PSR/DSR/PBO or approved equivalent.
- Proof exclusions all false.

Initial learning threshold: at least 30 candidate-matched OOS outcomes for early review. Promotion-grade evidence: materially larger, with 200 candidate-matched outcomes as the working target unless QC approves a stronger statistical design.

Done means the proof gate can say `INSUFFICIENT_FILL_BACKED_PROOF` today and only advances when real evidence exists.

### Phase 9: Runtime Installation Review

Only after Phases 1-8 pass in source and read-only checks should PM dispatch runtime installation.

Required chain:

- `PM -> E3 -> BB -> QC/MIT -> PM` for cron/service/runtime changes.
- Separate operator envelope for any effect-capable Demo mutation.
- No live applicability without GovernanceHub, Decision Lease, Guardian/Rust authority, and the five live gates.

### Phase 10: Debt Closure and Legacy Retirement

No phase is complete while an old path can still produce authority-like learning evidence outside the new Interfaces.

Required work:

- Add `LearningContractVersion` to proposal packets, ledger events, training manifests, registry rows, serving snapshots, proof packets, and application results.
- Add `LearningContractTestSuite` to CI with golden fixtures for success, stale, malformed, duplicate, empty patch, blocked proxy, replay-only, no-fill, schema mismatch, and authority-bypass cases.
- Add negative tests and static scans proving Python ML/Dream/AI code cannot submit orders, lower Cost Gate, write live params, bypass Decision Lease, or call effect-capable Bybit paths.
- Add migration/backfill/parity checks before any PG-first cutover; old JSONL/artifact paths remain read-only until parity is proven and then are archived or deleted.
- Add runbook evidence: install, rollback, restart, scheduler repair, registry rebuild, artifact rebuild, DB retention, and recovery drills.
- Add backpressure behavior for training, AI calls, scheduler queue, DB write volume, artifact size, and disk retention.
- Add explicit deletion tests for every new Module. If deleting a Module only removes pass-through code and does not reintroduce complexity at callers, it is too shallow and must be collapsed.

Acceptance evidence:

- No duplicate scheduler SSOT.
- No duplicate ledger/proof SSOT after cutover.
- No producer writes a legacy recommendation/proof shape that bypasses `AdvisoryProposal` or `ProofPacket`.
- No applier consumes raw recommendations directly after `DemoMutationEnvelope` is active.
- No model artifact is accepted without `TrainingRunManifest`, registry row, serving snapshot, and contract version.
- Contract tests run on Mac dev and Linux runtime-compatible paths.
- The old path retirement list is empty or every remaining item is explicitly archived read-only with an owner and retirement date.

Done means the learning engine is not merely working; its old shallow paths have been retired or contained.

## Triple Adversarial Audit

### Round 1: Completion Attack

Attack: If the phases are completed, does the system still have a missing link that prevents a real learning loop?

Verdict: **No known missing link remains after Phase 10 is added**. The chain covers health, immutable event capture, attribution, proposal, deterministic adjudication, governed Demo mutation, training/registry, runtime serving status, fill-backed proof, promotion verdict, runtime installation, and old-path retirement.

Residual truth: this completes the learning engine as an engineering system. It does not guarantee profitable alpha. Profit remains an empirical output of the proof/promotion gate.

### Round 2: Omission Attack

Attack: Are there omitted concerns that would later force rework or create parallel Implementation debt?

Original omissions found:

- Interface/schema versioning was implicit.
- Contract tests and negative authority tests were implicit.
- Legacy path retirement was implicit.
- Operations runbook and rollback drills were implicit.
- Cost, AI budget, scheduler pressure, DB pressure, and disk retention were implicit.

Resolution: these are now promoted into explicit Modules, Phase 10 work, acceptance gates, and backlog tickets. The plan is no longer just "add a new learning path"; it requires retiring or containing old paths before completion can be claimed.

### Round 3: Technical Debt Attack

Attack: Does the design create shallow Modules, speculative Seams, or permanent DESIGN-only debt?

Verdict: **Acceptable with hard constraints**.

- The main Seams have real Adapters: multiple advisory producers feed `AdvisoryProposal`; JSONL legacy and PG mirror/cutover paths feed `LearningEvent`; Python registry and Rust/edge loader feed `ModelServingSnapshot`.
- Any new Seam with only one Adapter must stay internal until a second Adapter or clear test seam exists.
- Every Module must pass the deletion test. If removing it reduces complexity rather than concentrating it, it must be collapsed.
- Stub or reserved Interfaces must have retirement criteria. This aligns with ADR-0035's explicit retirement discipline for online learning reservation.
- Completion is not allowed while legacy writers or readers remain able to create authority-like evidence outside the new Interface chain.

Conclusion: the plan is reasonable and effective if implemented as a deepening refactor, not as an additive layer. The "perfect" engineering standard here is no hidden bypass path, no duplicate SSOT, no unversioned packet, no untested Interface, and no legacy path left with write authority.

## Acceptance Gates

Runtime gate:

- 24 hours of unique scheduler authority.
- Last two maintenance cycles `ok`.
- No stale health, ledger, registry, or artifact/PG mismatch.

Lineage gate:

- Every proposal links to feature snapshot, source event, candidate id, schema hash, and proof tier.
- Every training artifact links to a training run manifest and registry row.

Mutation gate:

- At least one Demo-only proposal creates a non-empty, non-duplicate patch.
- Application result includes before/after snapshot, IPC response, rollback, recommendation id, and fail-closed audit.

Outcome gate:

- Candidate-matched Demo orders/fills exist.
- Fees, slippage, markout, and baseline are included.
- Cleanup/unattributed/paper-only/replay-only rows are excluded from proof.

Statistical gate:

- OOS net after cost is positive.
- PSR(0) >= 0.95 or approved equivalent.
- DSR >= 0.95 where multiple testing applies.
- PBO < 0.5 across sufficient CPCV folds.
- Sample size, breadth, regime, and concentration checks pass.

Model gate:

- Registry freshness and runtime serving snapshot agree.
- ONNX newer than registry is a hard fail.
- Placeholder/fallback inference is reported as fallback, not model success.

Governance gate:

- AI/Dream/ML Modules remain proposal-only.
- Demo mutation requires a bounded envelope.
- Live mutation/order authority requires GovernanceHub, Decision Lease, Guardian/Rust, operator review, and live gates.

Contract/debt gate:

- Every learning Interface has a contract version, golden fixtures, malformed-input fixtures, and fail-closed fixtures.
- Old artifact, recommendation, applier, registry, and proof paths are retired, archived read-only, or wrapped by the new Interface.
- No raw producer output can bypass `AdvisoryProposal`.
- No raw recommendation can bypass `DemoMutationEnvelope`.
- No proof-like artifact can bypass `ProofPacket`.

Authority/security gate:

- Static and runtime negative tests prove ML/Dream/AI cannot call order submission, cancel/replace, live parameter mutation, Cost Gate lowering, Decision Lease activation, or Bybit effect paths.
- Every fail-open condition is represented as a test fixture.

Operations gate:

- Install, rollback, restart, registry rebuild, scheduler repair, artifact rebuild, and retention drills have operator-readable evidence.
- Health, alerting, and backpressure states are visible before any effect-capable Demo mutation.

Budget/backpressure gate:

- Training, AI calls, scheduler queue, DB writes, artifact size, disk retention, and runtime inference load have hard limits.
- Budget or pressure failure disables mutation and promotion, not observation.

## Backlog

| Priority | Ticket | Outcome |
|---|---|---|
| P0 | `P0-LEARN-HEALTH-SSOT` | One `LearningStackHealthSnapshot` classifies current runtime as degraded and disables mutation. |
| P0 | `P0-LEARN-LEDGER-EVENT-CONTRACT` | JSONL/artifact lane is wrapped into hashed `LearningEvent` with proof tier. |
| P0 | `P0-LEARN-PROPOSAL-COMPILER` | DreamEngine/MLDE/LinUCB/JS/CostEdge emit one proposal schema with patch preview and proof exclusions. |
| P0 | `P0-LEARN-ADJUDICATOR` | Deterministic proposal decision blocks stale/proxy/replay/heuristic evidence. |
| P0 | `P0-LEARN-DEMO-MUTATION-ENVELOPE` | Applier consumes only approved Demo envelopes and records non-empty patch lineage. |
| P1 | `P1-LEARN-TRAINING-RUN-MANIFEST` | Training runs, CPCV/purge/embargo, artifacts, and registry rows are atomically traceable. |
| P1 | `P1-LEARN-MODEL-SERVING-SNAPSHOT` | Registry/Rust/edge loader expose loaded version, fallback reason, and schema/hash status. |
| P1 | `P1-LEARN-PROOF-PROMOTION-GATE` | Fill-backed proof packets produce explicit promotion verdicts. |
| P1 | `P1-LEARN-RUNTIME-INSTALL-REVIEW` | Cron/service/runtime repair is separately reviewed by E3/BB after source/read-only acceptance. |
| P0 | `P0-LEARN-CONTRACT-TEST-SUITE` | Every learning Interface has versioned fixtures, negative authority tests, and fail-closed CI coverage. |
| P0 | `P0-LEARN-LEGACY-RETIREMENT` | Old JSONL/artifact/recommendation/applier/proof paths are archived read-only, wrapped, or deleted after parity. |
| P1 | `P1-LEARN-OPERATIONS-RUNBOOK` | Install, rollback, restart, repair, rebuild, retention, alert, and recovery drills are documented and tested. |
| P1 | `P1-LEARN-BUDGET-BACKPRESSURE` | Training, AI, DB, scheduler, disk, and inference pressure fail closed for mutation/promotion. |

## Do Not Do Yet

- Do not enable direct live mutation, live candidate auto-apply, order authority, probe authority, or Cost Gate lowering.
- Do not treat blocked markout proxy as fill-backed proof.
- Do not start with PG cutover; first wrap current JSONL SSOT, then dual-write/diff/reconstruct.
- Do not enable online/streaming learning before ledger, attribution, and proof gates are complete.
- Do not expand live_demo training as promotion evidence without Stage 0R/Stage-B style data readiness and drift evidence.
- Do not count replay, paper-only, cleanup, or unattributed fills as promotion proof.
- Do not prioritize ONNX live inference before registry/reloader status and fail-closed behavior are visible.
- Do not let AI or DreamEngine validate alpha, approve proposals, or bypass deterministic gates.
- Do not leave a parallel legacy writer/reader active after the replacement Interface is accepted.
- Do not call a phase complete without contract tests, negative authority tests, rollback evidence, and a retirement decision for replaced paths.

## PM Conclusion

To complete all learning engines, the work must move from scattered advisory scripts to a governed learning pipeline:

`Health -> Contract Version -> Event -> Attribution -> Proposal -> Adjudication -> Demo Mutation -> Training/Registry -> Serving Snapshot -> Proof -> Promotion -> Legacy Retirement`.

Today, the observation/advisory side has life. The effective-learning side is not complete. The next engineering move is `P0-LEARN-HEALTH-SSOT`, followed immediately by contract versioning and contract tests, then ledger/proposal/adjudicator work. Runtime installation, cron repair, bounded Demo mutation, and any future live applicability must be separate gated dispatches.

After the triple adversarial audit, PM confirms the method is reasonable and effective for completing the learning engine without known technical-debt accumulation, provided Phase 10 is treated as mandatory rather than optional cleanup.
