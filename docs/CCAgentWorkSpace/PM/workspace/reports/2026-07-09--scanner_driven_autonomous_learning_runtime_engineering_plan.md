# Scanner-Driven Autonomous Learning Runtime Engineering Plan

Date: 2026-07-09
Owner: PM
Status: `DONE_WITH_CONCERNS`
Scope: source/design/report only

## PM Verdict

本轮 subagent 链确认：AI/ML 路线应该从 scheduler/report loop 转为 scanner-driven autonomous learning，但 P0 不能直接做常驻 daemon、cron、runtime sidecar、IPC writer、PG writer 或 Bybit-facing flow。

有效工程方向是：

> Autonomous Learning Runtime 先作为 scanner-driven 的本地 active-learning artifact pipeline：scanner 只提供 LearningTarget intake evidence，arbiter 选择学习目标，proof-bound bridge 只消费 candidate-matched after-cost outcomes，RetentionGuardian 先 dry-run，不授予交易或 runtime authority。

Concern: 需要最小 AMD/ADR 固化边界，尤其是：

- 不改变 ADR-0017：scanner remains evidence, not authority。
- 不提前实现 ADR-0035 的 streaming online model update。
- P0 仅 single-shot source/artifact CLI。

## Dispatch Chain

本轮实际派发 9 个角色：

| Role | Agent id | Task | Verdict |
|---|---|---|---|
| `CC(default)` | `019f4408-eb71-7fc3-814b-59126ae0e5f4` | root-principle / ADR audit | `DONE_WITH_CONCERNS` |
| `FA(default)` | `019f4409-11f6-70b0-b734-9591ff533e78` | functional gap audit | `DONE_WITH_CONCERNS` |
| `QC(default)` | `019f4409-3d72-7290-9350-7d9a2065bba0` | quant / target objective audit | `DONE_WITH_CONCERNS` |
| `MIT(default)` | `019f4409-635e-7e92-b509-e435143ca8e4` | data / retention audit | `DONE_WITH_CONCERNS` |
| `AI-E(default)` | `019f4409-8945-71f1-a99a-b9f0fa296ba0` | AI/ML role and cost boundary | `DONE_WITH_CONCERNS` |
| `E5(explorer)` | `019f4409-b45d-7fc2-adab-e61db9972f2d` | code architecture landing points | `DONE_WITH_CONCERNS` |
| `E3(explorer)` | `019f440f-65f2-7043-a432-15d3650cef8f` | runtime/security adversarial audit | `DONE_WITH_CONCERNS` |
| `BB(default)` | `019f440f-9029-7bd3-865f-99fe1727b9a4` | Bybit/exchange-facing adversarial audit | `DONE_WITH_CONCERNS` |
| `PA(default)` | `019f4413-e3fd-7fa1-a716-9354090c2c17` | architecture synthesis | `DONE_WITH_CONCERNS` |

Implementation roles `E1/E1a`, `E2`, `E4`, and `QA` were intentionally not dispatched because this round produced an engineering arrangement only; no source patch was authorized or needed.

## Current Code Evidence

The design should reuse existing seams:

- Scanner is already a long-lived local runtime task: `rust/openclaw_engine/src/scanner/runner.rs` says `ScannerRunner` is spawned once and runs until cancellation; each cycle fetches market data, scores, updates registry, emits snapshots/decays.
- Scanner already emits candidate evidence: `rust/openclaw_engine/src/scanner/types.rs` defines `OpportunityCandidate` as not an order, risk verdict, or permission to trade.
- Scanner opportunity math is pure evidence: `rust/openclaw_engine/src/scanner/opportunity.rs` explicitly does not reject orders or mutate route scores.
- Scanner decay is advisory only: `rust/openclaw_engine/src/scanner/advisory.rs` explicitly forbids dispatching orders or converting ranking changes to close/reduce actions.
- Demo learning lane already has a pure policy seam: `rust/openclaw_engine/src/demo_learning_lane.rs` states no file IO, DB, Bybit calls, order submission, or runtime config mutation.
- Demo learning ledger records are no-authority artifacts: `rust/openclaw_engine/src/demo_learning_lane_ledger.rs` emits append-only learning records without IO or order authority.
- Existing retention is partial but not unified: `demo_learning_lane_rotation.rs`, `V056__mlde_shadow_recommendations_retention_policy.sql`, `replay_artifact_prune.py`, and `ref21_market_recorder_retention.py` provide local retention patterns, but no global proof/dispute-aware reference graph.
- ProofPacket is already a strong proof boundary: `program_code/ml_training/proof_packet_contract.py` forbids authority expansion and accepts only candidate-matched after-cost proof or no-fill blocker.

## P0 Work Packages

### P0-A: LearningTargetIntake + Arbiter

Goal:
Convert scanner `OpportunityCandidate`, current proof/reward artifacts, and current active state into a `learning_target_runtime_v1` artifact. The arbiter selects the next learning target using after-cost expected value plus information value.

Expected write scope:

- `program_code/ml_training/learning_target_arbiter.py`
- focused tests under `program_code/ml_training/tests/`
- optional source-only intake helper

Forbidden:

- no `SymbolRegistry` overload
- no `ScannerRunner` cadence/subscription change
- no `TradingMsg` persistence
- no IPC
- no cron / daemon / sidecar
- no Bybit REST/WS
- no `_latest` overwrite
- no PG read/write unless future scope explicitly opens it
- no runtime mutation

Acceptance:

- CLI runs once and exits.
- Output contains `learn_target_id`, `strategy`, `symbol`, `side`, `horizon`, target objective, evidence refs, proof gaps, next action, and no-authority flags.
- Static grep/tests prove no DB/network/env/order imports.
- Scanner score, artifact count, and no-order evidence cannot become proof.

### P0-B: Candidate-Matched Outcome Ingestion Bridge

Goal:
Only consume `proof_packet_v1` and `reward_ledger_v1` to build candidate-level learning signal.

Expected write scope:

- source-only validator/bridge
- focused tests
- reuse existing ProofPacket and RewardLedger contracts

Forbidden:

- no PnL inference from scanner score
- no cleanup/unattributed/no-fill/no-order as reward
- no model reload
- no serving promotion
- no symlink promotion

Acceptance:

- Objective is candidate-level risk-adjusted net PnL after fee/slippage/funding plus information value.
- Missing fills, controls, fees, slippage, OOS/repeat, or proof-exclusion returns `DEFER_EVIDENCE`.

### P0-C: RetentionGuardian Dry-Run

Goal:
Build cleanup classifier, reference graph, quarantine manifest, and tombstone plan. P0 does dry-run only.

Expected write scope:

- source-only retention guardian helper/tests
- local dry-run manifest output

Forbidden:

- no physical delete
- no PG write/delete/DDL
- no Timescale policy mutation
- no proof/dispute/audit deletion
- no reuse of existing prune cron apply semantics

Acceptance:

- proof/dispute/audit/lineage/provenance artifacts classify as `NEVER_ORDINARY_DELETE`.
- ordinary scratch can only become `QUARANTINE_CANDIDATE` or `TOMBSTONE_STAGE_1_PROPOSED`.
- manifests are hash-bound, replayable, and auditable.

## P1 Work Packages

### P1-A: Explicit ALR Local Runner

Goal:
Compose P0 CLIs into an explicit foreground repeatable loop, still not a hidden scheduler.

Allowed:

- helper script
- report writer
- state packet schema

Forbidden:

- no cron
- no launchd/systemd
- no IPC listener
- no PG writer
- no runtime service

Acceptance:

- PM/operator explicitly invokes it.
- Each round reads previous artifacts and emits the next artifact.
- State machine is explainable and can stop without side effects.

### P1-B: Persistence Design Packet

Goal:
Design future PG/provenance schema without applying it.

Allowed:

- ADR/AMD/spec/report only

Forbidden:

- no migration creation
- no migration apply
- no backfill
- no retention policy mutation

Acceptance:

- Includes V### reservation check, rollback plan, Linux PG dry-run plan, and append-only provenance contract.

### P1-C: Traditional ML / Statistical Target Selector

Goal:
Add offline target selector using traditional ML/statistical methods.

Allowed:

- offline evaluator source
- tests
- deterministic/statistical ranking
- local LLM only for explanation/cluster/experiment-draft, not authority

Forbidden:

- no RL policy writer
- no streaming online update
- no live parameter mutation

Acceptance:

- Works without LLM or external services.
- Produces interpretable target ranking and uncertainty.
- Can be replayed offline.

## P2 Work Packages

### P2-A: Runtime Sidecar / ADPE / Rust Integration

Only after P0/P1 are stable.

Requires:

- new PA/E3 design
- BB if exchange-facing
- fail-closed shutdown
- audit and rollback

Forbidden in P0/P1:

- no hidden runtime hooks
- no IPC writer
- no ADPE `--apply`
- no Rust order/config/risk mutation

### P2-B: Bounded Demo Outcome Production

Future exact-scope work to create candidate-matched Demo outcomes.

Requires:

- same-window E3/BB gates
- fresh BBO/instrument/order shape
- active Decision Lease
- Guardian/Rust authority
- audit/reconstructability

If any gate fails, outcome cannot enter proof.

### P2-C: RL / ADR-0035 Online Update

Deferred.

Current ALR does not implement:

- streaming weight mutation
- online learner writes
- RL policy writer
- ModelClient hot-path execution

## Loop Contract

P0 entry is explicit single-shot CLI:

```bash
python -m program_code.ml_training.learning_target_arbiter \
  --inputs <artifact-dir> \
  --out <run-dir>
```

State machine:

```text
LOAD_INPUTS
  -> BUILD_TARGETS
  -> SCORE_INFORMATION_VALUE
  -> CHECK_PROOF_BOUNDARY
  -> RETENTION_DRY_RUN
  -> EMIT_ARTIFACT
  -> EXIT
```

Exit codes/states:

| State | Meaning |
|---|---|
| `EMIT_ARTIFACT` | Single-shot completed; no authority granted |
| `DEFER_EVIDENCE` | Missing candidate-matched proof/reward/control evidence |
| `BLOCKED_BOUNDARY` | Authority, runtime, Bybit, IPC, PG, or scheduler contamination found |
| `STOP_NO_EDGE` | No target has positive after-cost/information-value case |
| `STOP_RETENTION_RISK` | Cleanup candidate touches proof/dispute/audit/lineage risk |
| `ROTATED` | source/candidate/auth/input hash drift |

There is no autonomous background continuation in P0. Next invocation must be explicit.

## Cleanup / Retention Contract

Implementation must be layered:

1. `classifier`: classify proof/dispute/audit/lineage, candidate artifacts, scratch, duplicate, stale cache.
2. `reference_graph`: prove whether an artifact is referenced by ProofPacket, RewardLedger, report, ADR/AMD, state packet, fill/order/context id, or source hash.
3. `quarantine`: mark/move proposal only; no deletion.
4. `tombstone_stage_1`: dry-run manifest proposal with hash, reason, refs, reverse refs, rebuild recipe.
5. `tombstone_stage_2`: future reviewed apply gate.
6. `physical_delete`: P2+ separate scope; proof/dispute/audit never ordinary-delete.

Never ordinary-delete:

- orders/fills/fees/slippage
- Decision Lease / authorization / Guardian / Risk Governor / reconciliation
- proof packets / reward ledger / candidate evidence manifest
- cleanup/unattributed/proof-excluded rows as audit facts
- report-linked artifacts
- hidden OOS / control / repeat evidence
- exchange request/response fields needed for reconstruction

## AMD / ADR Minimum Direction

Minimum AMD:

> Operator accepts replacing AI/ML scheduler/report loop with scanner-driven active-learning ALR direction. P0 remains source-only, single-shot artifact CLI and grants no runtime, trading, exchange, PG, IPC, cron, daemon, or order authority.

Minimum ADR:

- ALR uses scanner evidence but does not change ADR-0017.
- ALR active-learning orchestrator is not ADR-0035 streaming online model update.
- P0 forbids cron/daemon/IPC/PG/runtime mutation/Bybit/API/order/WS.
- proof comes only from candidate-matched after-cost outcomes.
- LLM only explains, clusters, and drafts experiments.
- cleanup starts with dry-run reference graph, quarantine, and tombstone manifest.

## Next Engineering Dispatch

Recommended next chain:

1. `PM -> CC -> FA -> PA -> PM`: write AMD/ADR boundary packet.
2. `PM -> PA -> E5 -> E1/E1a -> E2 -> E4 -> QA -> PM`: implement P0-A/B/C source-only CLIs and tests.
3. `PM -> QC -> MIT -> AI-E -> PM`: validate objective, retention graph, and AI/ML boundaries.
4. `PM -> E3 -> BB -> PM`: only if future work touches runtime, PG, IPC, Bybit, Decision Lease, service/env, or order-capable Demo.

## Boundary Of This Report

This report is design/report only.

Not performed:

- no source code edit
- no runtime SSH
- no Bybit public/private/order call
- no PG read/write
- no Decision Lease
- no scanner config/cadence/subscription change
- no `_latest` overwrite
- no Cost Gate change
- no proof or promotion claim
