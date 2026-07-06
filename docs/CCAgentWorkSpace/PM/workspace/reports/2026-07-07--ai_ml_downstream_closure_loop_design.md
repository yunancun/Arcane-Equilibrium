# AI/ML Downstream Closure Loop Design

Date: 2026-07-07

PM sign-off: `DESIGN_READY_SOURCE_FIRST_RUNTIME_GATED`

Purpose: define the next autonomous loop after WP1-WP5 source contracts. This loop closes the downstream gaps identified in:

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ai_ml_roadmap_wp1_wp5_completion_assessment.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp5_demo_mutation_envelope_contract.state_packet.json`

Answer to the operator question:

- We do not need to wait for the other session's DemoMutationEnvelope mapping or PM->E3->BB runtime/loss-control data to design this loop.
- We do need those outputs before any runtime/order/private-read/DB-write/bounded-Demo outcome branch executes.
- Therefore the loop is source-first and runtime-gated: it can implement WP2.1/WP3.1 and source contracts for WP6/WP7 now, but must auto-stop before real runtime learning if runtime/loss-control or bounded Demo outcome evidence is missing.

No runtime mutation, DB write, exchange/private read, MCP server/config, secret access, order/probe, Cost Gate change, deploy, live, mainnet, or bandit runtime action is authorized by this design.

## Scope

The loop owns only the downstream closure items after WP1-WP5:

1. `WP2.1-TRAINING-RUN-PIT-MANIFEST-GATE`
2. `WP3.1-TRAINING-REGISTRY-CONTRACT-EMISSION`
3. `WP6-REWARD-LEDGER-PROOFPACKET-BRIDGE`
4. `WP7-EFFECT-REVIEW-AND-STOP-LOOP`

It does not reopen WP1-WP5 unless a new failing test or audit finding identifies a specific defect.

It treats `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD` as an external runtime gate. It may ingest its final packet, but it must not perform the PM->E3->BB runtime refresh itself unless launched under an explicit runtime/security/exchange-facing scope.

## Input Packets

At the start of every iteration, the loop reads:

- latest WP1-WP5 reports and state packets;
- latest PM->E3->BB standing Demo/loss-control report, if present;
- `TODO.md` active blocker table;
- git `HEAD`, `origin/main`, and dirty worktree state;
- focused module tests relevant to the selected work item.

Optional neighbor outputs are classified, not assumed:

| Input | Classification | Effect |
|---|---|---|
| WP5 formalize/map report exists and passes | `WP5_MAPPING_READY` | WP6 may use DemoMutationEnvelope mapping as accepted dependency. |
| WP5 report missing or still running | `WP5_MAPPING_UNKNOWN` | WP2.1/WP3.1 can proceed; WP6 may only design contracts and must avoid overlapping WP5 files. |
| PM->E3->BB standing/loss-control READY | `RUNTIME_LOSS_CONTROL_READY` | Runtime evidence branches may be considered, but still require exact same-window gates. |
| PM->E3->BB missing/expired/source-drift/unsafe | `RUNTIME_LOSS_CONTROL_BLOCKED` | Source work may continue; runtime learning stops with `STOP_LOSS_CONTROL`. |

The loop never waits idly for the other session. If the next selected work requires a missing neighbor output, it rotates to the next source-safe item or stops with a machine-readable reason.

## Work Graph

```text
WP1-WP5 source contracts complete
  -> WP2.1 training PIT gate
  -> WP3.1 registry contract emission
  -> WP6 reward ledger ProofPacket bridge
  -> WP7 effect-review stop loop
  -> bounded Demo outcome ingestion/effect evaluation
```

Dependency rules:

- `WP2.1` is source-only and can start now.
- `WP3.1` depends on `WP2.1` because registry contract emission must bind the PIT manifest hash.
- `WP6` depends on WP1 ProofPacket and WP5 DemoMutationEnvelope. It can implement the ledger contract/source bridge now, but cannot count real rewards without candidate-matched ProofPackets and runtime outcome evidence.
- `WP7` depends on WP6 for real effect review, but can implement stop-loop/effect-review packet contracts before runtime data exists.
- Runtime/bounded Demo branches depend on `RUNTIME_LOSS_CONTROL_READY`, fresh same-window gates, and candidate-matched outcome evidence.

## Automatic Cycle Logic

Each iteration follows this state machine:

```text
LOAD_CONTEXT
  -> INGEST_NEIGHBOR_OUTPUTS
  -> BUILD_WORK_GRAPH
  -> SELECT_NEXT_WORK
  -> PRECHECK_BOUNDARY
  -> DISPATCH_OR_IMPLEMENT
  -> VERIFY_SOURCE
  -> VERIFY_EFFECT
  -> WRITE_REPORTS_AND_STATE
  -> DECIDE_CONTINUE_OR_STOP
```

Selection algorithm:

1. If tests or git state show overlapping dirty files in the selected module, stop with `STOP_DIRTY_OVERLAP`.
2. If `WP2.1` is not complete, select it.
3. Else if `WP3.1` is not complete, select it.
4. Else if `WP6` source bridge is not complete and WP5 mapping is ready or non-overlapping, select it.
5. Else if `WP7` source effect/stop loop is not complete, select it.
6. Else if runtime/loss-control is not ready, stop with `STOP_SOURCE_CLOSURE_COMPLETE_WAIT_RUNTIME`.
7. Else if no candidate-matched bounded Demo ProofPackets exist, stop with `STOP_WAIT_BOUNDED_DEMO_OUTCOMES`.
8. Else run the effect-evaluation branch.
9. If all source and runtime/effect gates pass, stop with `STOP_LOOP_COMPLETE`.

The loop must continue automatically while the selected work item is source-safe and verification passes. It must not continue into a runtime/evidence branch only because source work passed.

## Work Item Contracts

### WP2.1 - Training Run PIT Manifest Gate

Goal:

- Make `run_training_pipeline.py` require or emit a valid `pit_dataset_manifest_v1` before training can claim a contract-bound run.
- Store the manifest hash/path in the acceptance report.
- Keep dry-run behavior deterministic and testable.

Minimum implementation:

- Add a training-run contract or config field carrying PIT manifest data.
- Validate the PIT manifest before quantile training starts.
- Fail closed when a required manifest is missing, malformed, candidate-scope mismatched, or leakage-prone.
- Add focused tests proving training cannot silently proceed as contract-bound without a manifest.

Allowed actions: source edits, local tests, docs, reports.

Denied actions: DB writes, runtime reads, exchange/private reads, orders, Cost Gate changes.

Exit:

- `ADVANCED` if the acceptance report contains a valid PIT binding and tests pass.
- `STOP_TEST` on failing tests.
- `STOP_BOUNDARY` if implementation would require runtime data.

### WP3.1 - Training Registry Contract Emission

Goal:

- Generate `registry_serving_contract_v1` from the training acceptance report, PIT manifest, feature/schema hashes, and q10/q50/q90 ONNX artifact hashes.
- Pass it to `register_quantile_trio_from_onnx_out(...)`.
- Fail closed before registry persistence when contract validation fails.

Minimum implementation:

- Build deterministic artifact hashes for q10/q50/q90 outputs.
- Attach the contract to the acceptance report and registry call.
- Preserve advisory-only semantics: no promotion, no direct model reload authority, no live serving grant.
- Add tests for exact trio requirement, contract hash mismatch, artifact hash mismatch, and dry-run/no-DB behavior.

Exit:

- `ADVANCED` if the training pipeline can produce a contract-bound acceptance report and registry call under tests.
- `STOP_LOSS_CONTROL` only if the next branch tries runtime persistence without an accepted gate.

### WP6 - Reward Ledger ProofPacket Bridge

Goal:

- Define a reward ledger input that consumes only valid candidate-matched ProofPackets and valid countable DemoMutationEnvelope rows.
- Prevent no-fill, cleanup, unmatched, dry-run, dedupe, non-demo, live, or proof-excluded rewards from updating learning state.

Minimum implementation:

- Add `reward_ledger_v1` contract/validator/source bridge.
- Require ProofPacket `PROOF_READY`.
- Require DemoMutationEnvelope `STATUS_COUNTABLE` for mutation-effect learning rows.
- Produce an append-only reward record shape with candidate id, strategy, symbol, side, fills, costs, controls, PIT/registry lineage, mutation envelope hash, and effect window.
- Add tests for valid happy path and all proof-exclusion cases.

Source-only mode:

- If runtime/loss-control is not ready, implement only contracts, validators, fixtures, and offline bridges.
- Do not read live PG or runtime files.

Runtime mode:

- Only allowed if a separate PM->E3->BB report grants exact read scope.
- Still no order/probe/live/Cost Gate expansion.

Exit:

- `ADVANCED_WITH_CONCERNS` if source ledger contract is ready but no real bounded Demo outcome exists.
- `STOP_WAIT_BOUNDED_DEMO_OUTCOMES` if contract is ready and only real outcome data is missing.

### WP7 - Effect Review And Stop Loop

Goal:

- Implement an automatic effect-review controller that decides continue, rollback, rotate, or stop based on reward ledger evidence.

Minimum implementation:

- Add `learning_effect_review_v1` packet/validator.
- Inputs: reward ledger refs, ProofPacket refs, mutation envelope refs, acceptance report refs, controls, loss limits, OOS/repeat tags.
- Outputs: `continue`, `rollback`, `rotate_candidate`, `stop_loss_control`, `stop_no_edge`, `stop_evidence`, `promote_review_only`.
- Promotion remains review-only. No order/live authority is granted.
- Add tests for profitable after-cost repeat, negative EV, no matched fills, insufficient sample, missing controls, failed mutation effect, and loss-limit breach.

Exit:

- `ADVANCED_WITH_CONCERNS` if source stop-loop is ready but runtime outcomes are missing.
- `STOP_LOOP_COMPLETE` only if all source contracts, runtime outcome inputs, reward ledger, and effect review pass.

## Automatic Stop Logic

The loop must stop immediately on these codes:

| Stop code | Trigger | Continue condition |
|---|---|---|
| `STOP_DIRTY_OVERLAP` | selected files have unrelated dirty changes | user/PM resolves or isolates worktree |
| `STOP_SOURCE_DRIFT` | HEAD/origin changes outside approved drift policy | regenerate state from current head |
| `STOP_BOUNDARY` | selected work requires private read, exchange contact, order/probe, Cost Gate, live/mainnet, secret, MCP runtime, deploy, or unapproved DB write | explicit PM/operator gated scope |
| `STOP_LOSS_CONTROL` | standing Demo/loss-control envelope missing, expired, unsafe, or source-drifted | PM->E3->BB produces valid READY packet |
| `STOP_TEST` | focused tests, static guards, validators, compile, or diff-check fail | fix and rerun |
| `STOP_EVIDENCE` | effect cannot be verified with machine-checkable artifacts | implement missing artifact or rotate |
| `STOP_NO_DELTA` | two consecutive iterations produce no artifact/gate movement | rotate work item or mark blocked |
| `STOP_WAIT_NEIGHBOR` | the only unblocked next step depends on the other session's unfinished packet | wait for that packet or run a different source-safe item |
| `STOP_SOURCE_CLOSURE_COMPLETE_WAIT_RUNTIME` | WP2.1/WP3.1/WP6/WP7 source work complete, but runtime/loss-control not ready | run PM->E3->BB runtime/loss-control loop |
| `STOP_WAIT_BOUNDED_DEMO_OUTCOMES` | reward/effect contracts are ready, but no candidate-matched bounded Demo ProofPackets exist | run bounded Demo outcome collection under exact gates |
| `STOP_LOOP_COMPLETE` | all source and runtime/effect gates pass | PM final sign-off |

The loop must not sleep/poll waiting for the other session. It writes a state packet and stops.

## Effect Metrics

Every iteration writes `implementation_effect_review_v1` with these minimum fields:

```json
{
  "schema_version": "implementation_effect_review_v1",
  "work_id": "WP2.1-TRAINING-RUN-PIT-MANIFEST-GATE",
  "pre_state": {},
  "post_state": {},
  "tests": [],
  "artifact_delta": "",
  "gate_delta": "",
  "proof_delta": "",
  "runtime_delta": "none|ready|blocked",
  "risk_delta": "no_authority_expansion",
  "regressions": [],
  "concerns": [],
  "boundary_check": {
    "runtime_mutation": false,
    "db_write": false,
    "exchange_contact": false,
    "private_read": false,
    "order_or_probe": false,
    "cost_gate_change": false,
    "live_or_mainnet": false
  },
  "verdict": "EFFECTIVE|PARTIAL|NO_DELTA|REGRESSED|BLOCKED"
}
```

Every iteration writes `roadmap_loop_state_packet_v1` with:

- selected work id;
- current gate;
- next work id;
- stop reason if any;
- evidence refs;
- tests;
- denied actions;
- repo head and origin head;
- neighbor input classifications.

## Completion Definition

Source closure is complete when:

- `WP2.1`, `WP3.1`, `WP6`, and `WP7` have source contracts/integration tests;
- dry-run training acceptance reports carry PIT and registry contract bindings;
- reward ledger and effect-review packets reject invalid/no-fill/unmatched/non-demo/uncounted rows;
- all focused tests and diff checks pass;
- state packet stops with `STOP_SOURCE_CLOSURE_COMPLETE_WAIT_RUNTIME` or continues to runtime only with accepted gates.

Full trading-learning closure is complete only when:

- runtime/loss-control gate is READY;
- bounded Demo outcomes produce candidate-matched ProofPackets;
- reward ledger consumes those ProofPackets;
- effect review decides continue/rollback/rotate/stop from after-cost evidence;
- no authority boundary is expanded;
- PM signs off the final report.

## Launcher Prompt

Use this prompt after the current neighbor session finishes, or now if you only want the source-safe branch:

```text
You are PM for /Users/ncyu/Projects/TradeBot/srv. Read AGENTS.md boot rules and treat srv/ as repo root.

Objective: run the AI/ML downstream closure loop defined in
docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ai_ml_downstream_closure_loop_design.md.

Inputs:
- docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ai_ml_roadmap_wp1_wp5_completion_assessment.md
- latest WP5 DemoMutationEnvelope report/state/effect artifacts
- latest PM->E3->BB standing Demo/loss-control report if present
- TODO.md active blocker table

Rules:
1. Do not assume the other session is complete. Classify neighbor outputs as WP5_MAPPING_READY/UNKNOWN/BLOCKED and RUNTIME_LOSS_CONTROL_READY/BLOCKED.
2. Run source-safe work automatically in order: WP2.1, WP3.1, WP6 source bridge, WP7 source effect/stop loop.
3. Do not perform runtime mutation, DB write, private/exchange read, MCP runtime, order/probe, Cost Gate change, deploy, live, or mainnet unless an exact PM->E3->BB packet grants that exact scope.
4. After every iteration, write implementation_effect_review_v1 and roadmap_loop_state_packet_v1.
5. Auto-stop on STOP_DIRTY_OVERLAP, STOP_SOURCE_DRIFT, STOP_BOUNDARY, STOP_LOSS_CONTROL, STOP_TEST, STOP_EVIDENCE, STOP_NO_DELTA, STOP_WAIT_NEIGHBOR, STOP_SOURCE_CLOSURE_COMPLETE_WAIT_RUNTIME, STOP_WAIT_BOUNDED_DEMO_OUTCOMES, or STOP_LOOP_COMPLETE.
6. Use required role chains for code work. If subagent dispatch is unavailable, stop as STOP_DISPATCH_BLOCKED unless operator explicitly allows single-agent source patches.
7. Preserve unrelated dirty files. Stage and commit only the current green checkpoint.

Expected output:
- PM report under docs/CCAgentWorkSpace/PM/workspace/reports/
- Operator stub under docs/CCAgentWorkSpace/Operator/
- effect review JSON
- state packet JSON
- focused tests and diff-check results
- commit SHA, and no push if local main contains unrelated ahead commits.
```

## PM Decision

The loop can be designed and launched for source-safe work now. It should not assume that PM->E3->BB completion will automatically continue it. The runtime/loss-control output is an input gate, not an auto-resume trigger.
