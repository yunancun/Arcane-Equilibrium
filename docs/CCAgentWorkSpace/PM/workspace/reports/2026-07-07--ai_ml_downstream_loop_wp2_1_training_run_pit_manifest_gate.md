# 2026-07-07 AI/ML Downstream Loop - WP2.1 Training Run PIT Manifest Gate

PM sign-off: `ADVANCED_SOURCE_ONLY`.

Scope: `AI-ML-DOWNSTREAM-CLOSURE-LOOP`, work item `WP2.1-TRAINING-RUN-PIT-MANIFEST-GATE`.

No runtime mutation, DB read/write/migration, exchange/private read, MCP server/config, credential/secret access, order/probe, Cost Gate change, deploy/restart, live/mainnet, runtime learning, or bounded Demo outcome ingestion was performed.

## Selected Work

Selected `roadmap_work_item_v1`:

- Work id: `WP2.1-TRAINING-RUN-PIT-MANIFEST-GATE`
- Reason: first incomplete source-only downstream closure item after WP1-WP5 source contracts.
- Runtime neighbor state: `RUNTIME_LOSS_CONTROL_BLOCKED`, so runtime/bounded Demo outcome branches remain unavailable.
- Machine-readable artifact: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ai_ml_downstream_loop_wp2_1_training_run_pit_manifest_gate.work_item.json`

## Implementation

The source patch makes contract-bound quantile training fail closed unless it can bind a valid `pit_dataset_manifest_v1` before training starts.

Key changes:

- `PipelineConfig` now supports `contract_bound_run`, `candidate_id`, `side`, and explicit PIT manifest input via inline mapping, path, or source mapping.
- `PipelineResult` records PIT binding status/hash/path/reason.
- Contract-bound quantile runs reject missing manifests, invalid hashes, candidate-scope mismatches, pooled symbols, unpinned/leakage-prone source, and legacy scorer routing before `train_quantile_trio`, ONNX export, or registry calls.
- Dry-run contract-bound runs may emit deterministic synthetic PIT manifests only when candidate id, concrete symbol, and side are explicit; the manifest is labelled `synthetic_training_dry_run` and is source-gate evidence only.
- Acceptance reports carry top-level `pit_dataset_manifest` plus `training_pit_manifest_binding_v1`.
- PIT sidecar and acceptance report persistence now use same-directory temp files plus atomic `Path.replace()`.

## Dispatch Chain

The required source-feature chain was completed:

- `PM`: intake and work selection.
- `PA(default)`: design report `docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-07--wp2_1_training_run_pit_manifest_gate_design.md`.
- `E1(worker)`: implementation report `docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-07--wp2_1_training_run_pit_manifest_gate_implementation.md`.
- `E2(explorer)`: initial `RETURN_TO_E1` for atomic persistence and missing pooled-symbol permanent test.
- `E1(worker)`: fixed E2 return items.
- `E2(explorer)`: re-review `PASS_TO_E4`.
- `E4(worker)`: regression `PASS`.
- `QA(worker)`: source acceptance `PASS`.
- `PM`: this sign-off and loop state update.

## Verification

E4 ran each source matrix twice:

```text
py_compile target files
=> PASS
```

```text
focused WP2.1 pytest
=> 46 passed, 1 skipped x2
```

```text
registry adjacency pytest
=> 49 passed x2
```

```text
QA adjacency pytest
=> 90 passed, 1 skipped x2
```

```text
scoped git diff --check
=> PASS
```

QA additionally performed source/report inspection, scoped forbidden-surface grep, and scoped diff-check. No runtime/DB/exchange/secret/deploy checks were required or run.

## Effect Review

Machine-readable effect review:

`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ai_ml_downstream_loop_wp2_1_training_run_pit_manifest_gate.effect_review.json`

Verdict: `EFFECTIVE`.

Effect:

- Training can now honestly claim PIT-contract-bound lineage only when a valid `pit_dataset_manifest_v1` is attached and candidate-scoped.
- Non-contract-bound training remains explicit instead of silently masquerading as contract-bound.
- WP3.1 now has a source acceptance-report PIT binding to consume for registry contract emission.

No profit proof, reward ledger update, bounded Demo outcome, runtime mutation, or authority expansion was added.

## State

State packet:

`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ai_ml_downstream_loop_wp2_1_training_run_pit_manifest_gate.state_packet.json`

Status: `ADVANCED`.

Next work: `WP3.1-TRAINING-REGISTRY-CONTRACT-EMISSION`.

Runtime/loss-control remains blocked by the latest standing Demo state: engine env `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=0` plus expired standing authorization. That branch was not consumed.

## Residual Concerns

- `program_code/ml_training/run_training_pipeline.py` is 1005 lines, above the 800-line review-attention threshold but below the 2000-line hard cap. E2 accepted this as INFO because PA scoped the helper group into this file for WP2.1.
- Runtime/loss-control and bounded Demo outcomes remain external gates for later loop stages.

PM SIGN-OFF: `ADVANCED_SOURCE_ONLY`
