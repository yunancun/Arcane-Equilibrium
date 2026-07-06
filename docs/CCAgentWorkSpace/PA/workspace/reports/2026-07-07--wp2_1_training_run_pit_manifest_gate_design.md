# WP2.1 Training Run PIT Manifest Gate Design

Date: 2026-07-07

PA status: `E1_READY_SOURCE_ONLY`

Task: `WP2.1-TRAINING-RUN-PIT-MANIFEST-GATE`

## Grounding

已讀必需規則與 loop context：`AGENTS.md`, `CLAUDE.md`, `.codex/MEMORY.md`, `README.md`, `docs/agents/context-loading.md`, `TODO.md`, `.codex/AGENT_DISPATCH_PROTOCOL.md`, `.codex/SUBAGENT_EXECUTION_RULES.md`, PA profile/memory，以及 PM downstream closure reports/state packet。

已讀相關 code/test：

- `program_code/ml_training/run_training_pipeline.py`
- `program_code/ml_training/pit_dataset_manifest.py`
- `program_code/ml_training/pit_dataset_manifest_builder.py`
- `program_code/ml_training/quantile_reports.py`
- `program_code/ml_training/model_registry.py`
- `program_code/ml_training/tests/test_run_training_pipeline.py`
- `program_code/ml_training/tests/test_pit_dataset_manifest.py`
- `program_code/ml_training/tests/test_pit_dataset_manifest_builder.py`
- `program_code/ml_training/tests/test_quantile_reports.py`
- `program_code/ml_training/tests/test_model_registry.py` relevant registry acceptance-report path tests

`rg` call-path result：`run_training_pipeline.py` currently writes acceptance report at lines 305-317 and calls `register_quantile_trio_from_onnx_out(...)` at lines 379-394 without PIT manifest or registry contract. `model_registry.register_quantile_trio_from_onnx_out(...)` lazily reads the acceptance report path and can attach registry-serving metadata only when explicitly supplied.

## Current State

Fact:

- `PipelineConfig` has no PIT manifest, candidate id, or side field. It only carries `strategy_type`, `symbol`, `engine_mode`, dry-run, and quantile flags.
- `_load_dataset(...)` returns only `(features, labels, timestamps, feature_names, label_composition)`. It does not return row ids, query lineage, split lineage, proof lineage, or source artifact hashes.
- `pit_dataset_manifest.py` already validates `pit_dataset_manifest_v1` source artifacts, including canonical hash, candidate scope, PIT cutoff, leakage evidence, row exclusions, authority aliases, and secret-like text.
- `pit_dataset_manifest_builder.py` can build a manifest only from caller-provided source mapping; it intentionally does not read DB/runtime/files/env.

Inference:

- Non-dry-run training cannot honestly auto-infer a valid PIT manifest from the current ETL tuple. E1 must require an explicit manifest or explicit manifest source mapping for any contract-bound run.
- Dry-run can emit a deterministic synthetic PIT manifest for testability, but it must be labelled as dry-run/synthetic source lineage and must not be treated as profit proof or runtime evidence.

## Interface Design

### `PipelineConfig`

Add source-only fields:

```python
contract_bound_run: bool = False
candidate_id: Optional[str] = None
side: Optional[str] = None
pit_dataset_manifest: Optional[Dict[str, Any]] = None
pit_dataset_manifest_path: Optional[str] = None
pit_dataset_manifest_source: Optional[Dict[str, Any]] = None
```

Rules:

- `contract_bound_run=False` preserves existing legacy and quantile behavior, but acceptance reports must explicitly say the run is not PIT-contract-bound.
- `contract_bound_run=True` requires exactly one manifest input source, except deterministic dry-run may emit a synthetic manifest when `candidate_id`, concrete `symbol`, and `side` are provided.
- `candidate_id`, `side`, concrete `symbol`, `strategy_type`, and `engine_mode` must match `manifest["candidate_scope"]`. Pooled `symbol=None` / `"ALL"` must fail closed for a candidate-bound run unless a future separate design adds a pooled-manifest contract.
- Do not infer `candidate_id` from strategy/symbol/side. Hidden derivation is a mismatch risk.

### `PipelineResult`

Add audit fields:

```python
contract_bound_run: bool = False
pit_dataset_manifest_hash: str = ""
pit_dataset_manifest_path: str = ""
pit_dataset_manifest_status: str = ""
pit_dataset_manifest_reason: str = ""
```

These are informational; the source of truth remains the acceptance report.

### Acceptance Report

Extend `generate_acceptance_report(...)` with optional metadata, defaulting to current behavior:

```python
pit_dataset_manifest: Optional[Dict[str, Any]] = None
pit_dataset_manifest_binding: Optional[Dict[str, Any]] = None
persist_required: bool = False
```

Report shape:

```json
{
  "pit_dataset_manifest": { "... canonical manifest ..." },
  "pit_dataset_manifest_binding": {
    "schema_version": "training_pit_manifest_binding_v1",
    "contract_bound_run": true,
    "manifest_hash": "<64 hex>",
    "manifest_path": ".../grid_trading_demo_ETHUSDT_pit_dataset_manifest.json",
    "validation_verdict": "dataset_ready",
    "validation_reason": "ok",
    "candidate_scope": {
      "candidate_id": "grid_trading|ETHUSDT|Buy",
      "strategy_name": "grid_trading",
      "symbol": "ETHUSDT",
      "side": "Buy",
      "engine_mode": "demo"
    },
    "not_authority": true,
    "runtime_mutation_performed": false,
    "db_write_performed": false,
    "exchange_private_read_performed": false,
    "order_or_probe_performed": false,
    "live_or_mainnet_performed": false
  }
}
```

For `contract_bound_run=False`, write:

```json
"pit_dataset_manifest_binding": {
  "schema_version": "training_pit_manifest_binding_v1",
  "contract_bound_run": false,
  "validation_verdict": "not_required",
  "validation_reason": "not_contract_bound"
}
```

Rationale: downstream WP3 can consume `manifest_hash`, and future WP1/WP6 can consume the canonical `pit_dataset_manifest` field without alias parsing.

### Helper Functions In `run_training_pipeline.py`

Add small private helpers rather than a new module:

- `_load_pit_manifest_from_config(config) -> tuple[dict | None, str]`
- `_build_dry_run_pit_manifest_source(config, features, labels, timestamps, feature_names, label_composition) -> dict`
- `_validate_training_pit_manifest_binding(config, manifest, manifest_path) -> PitBinding`
- `_write_pit_manifest_sidecar(output_dir, strategy, engine_mode, symbol_slot, manifest) -> str`

`PitBinding` can be a small dataclass in `run_training_pipeline.py`; no new package-level contract is needed for WP2.1.

Validation order:

1. Resolve `pooled, symbol_slot`.
2. If `use_quantile_predictor` and `contract_bound_run`, resolve/emit manifest before `train_quantile_trio(...)`.
3. Call `validate_pit_dataset_manifest(manifest)`.
4. Compare candidate scope to config.
5. Write sidecar only after validation passes, using canonical JSON.
6. Pass manifest and binding into `generate_acceptance_report(...)`.
7. Verify persisted report contains the same manifest hash when `persist_required=True`.

Do not add PIT gating to the legacy scorer path in this work item. If a caller sets `contract_bound_run=True` with `use_quantile_predictor=False`, fail closed with `contract_bound_quantile_path_required`.

## Call Flow

```text
run_pipeline(config)
  -> _load_dataset(config)
  -> sample-count gate
  -> _run_quantile_pipeline(...)
       -> _resolve_symbol_slot(config)
       -> _load/build PIT manifest if contract_bound_run
       -> validate_pit_dataset_manifest(...)
       -> candidate-scope match gate
       -> write PIT sidecar (dry-run/source file only)
       -> train_quantile_trio(...)
       -> CQR calibration
       -> generate_acceptance_report(... pit manifest + binding ...)
       -> assert persisted report hash matches binding when contract_bound_run
       -> ONNX export
       -> register_quantile_trio_from_onnx_out(... acceptance_report_path ...)
```

Failure path examples:

- missing manifest: stop before `quantile_train`, `success=False`, stage `pit_manifest_gate_failed`, reason `pit_dataset_manifest_missing`.
- malformed hash: stop before training, reason from validator such as `manifest_hash_mismatch`.
- candidate scope mismatch: stop before training, reason `pit_manifest_candidate_scope_symbol_mismatch` or equivalent.
- leakage-prone source: stop before training for validator reasons such as `source_query_unpinned_relative_window:*`, `row_set_max_ts_after_as_of_ts`, or `leakage_evidence_overlap_count_not_zero`.

## Dry-Run Contract

Dry-run must remain deterministic:

- Use fixed RNG already present in `_load_dataset`.
- Emit synthetic row ids `dry-run-row-000000` etc. from deterministic timestamps/features/labels.
- Use a fixed dry-run base clock, not `now()` or local timezone.
- Require explicit `candidate_id`, concrete `symbol`, and `side` for `contract_bound_run=True`.
- Sidecar filename should be deterministic: `{strategy}_{engine_mode}_{symbol_slot}_pit_dataset_manifest.json`.
- The manifest must include `dataset_role="synthetic_training_dry_run"` or equivalent visible label, while still passing `pit_dataset_manifest_v1`.

Dry-run manifest proves only the source gate and report binding. It is not ProofPacket evidence, not bounded Demo outcome evidence, and not promotion proof.

## Side Effects

Expected source-level side effects:

- Additive dataclass fields in `PipelineConfig` and `PipelineResult`.
- Additive acceptance report fields.
- Contract-bound dry-run writes one PIT sidecar JSON under `output_dir`.
- Registry JSONB will include the PIT fields when the existing registry path persists an acceptance report.

No intended side effects:

- No DB schema change.
- No new runtime read/write.
- No exchange/private read.
- No order/probe path.
- No Cost Gate change.
- No live/mainnet behavior.
- No Rust IPC schema change.
- Existing non-contract-bound tests should continue to pass.

Risk rating: medium. It touches shared training pipeline/report interfaces, but not trading authority, runtime services, or IPC.

## Degrade / Rollback

Degrade path:

- Set `contract_bound_run=False`; training behaves as current non-contract-bound training and reports `not_contract_bound`.
- If deterministic dry-run manifest generation proves too broad, E1 may degrade to "explicit manifest/source required even for dry-run" and keep only source fixtures in tests.
- If `generate_acceptance_report(..., persist_required=True)` is too invasive, pipeline may write then read back the report and fail closed on missing binding; default report behavior stays fail-soft for non-contract-bound calls.

Rollback:

- Revert only `run_training_pipeline.py`, `quantile_reports.py`, and focused tests.
- Sidecar JSON files are output artifacts only, not source/runtime state.
- Acceptance report fields are additive; consumers that ignore unknown fields continue to work.

## E1 Dispatch Plan

Bound role: `E1(worker)`

Task shape: source implementation + focused tests.

Scope owner:

- `program_code/ml_training/run_training_pipeline.py`
- `program_code/ml_training/quantile_reports.py`
- `program_code/ml_training/tests/test_run_training_pipeline.py`
- `program_code/ml_training/tests/test_quantile_reports.py`
- optionally `program_code/ml_training/tests/test_pit_dataset_manifest.py` only if a validator edge case uncovered by pipeline tests needs coverage.

Implementation steps:

1. Add config/result fields and PIT binding dataclass/helper functions.
2. Add deterministic dry-run source builder or explicit-source resolver.
3. Gate contract-bound quantile runs before `train_quantile_trio(...)`.
4. Add candidate-scope match gate.
5. Add acceptance report PIT metadata and persist-required behavior.
6. Add focused tests.

Suggested focused tests:

- `contract_bound_run=True` with no manifest/source/path fails before `quantile_train`.
- Invalid manifest hash fails before `quantile_train`.
- Manifest with candidate scope mismatch fails before `quantile_train`.
- Manifest with unpinned query / leakage overlap fails before `quantile_train`.
- Contract-bound dry-run emits deterministic sidecar and acceptance report contains matching `manifest_hash` and `manifest_path`.
- Non-contract-bound dry-run preserves current behavior and reports `not_contract_bound`.
- Legacy scorer with `contract_bound_run=True` fails closed, not silently contract-bound.

Do not split into parallel E1/E1a unless PM wants extra throughput; the files overlap enough that one E1 is lower risk.

## E2 Review Focus

1. Verify gate ordering: no contract-bound run reaches `train_quantile_trio(...)`, ONNX export, or registry call without `dataset_ready` PIT manifest and candidate-scope match.
2. Verify dry-run honesty: deterministic synthetic manifest is labelled as dry-run/source-only and cannot be misread as ProofPacket, bounded Demo outcome, or profit proof.
3. Verify report/registry propagation: persisted acceptance report contains canonical `pit_dataset_manifest`, binding hash/path, and no alias/partial-write drift; registry receives it only through existing acceptance-report JSONB flow.

## E4 / QA Verification Commands

Mac source-only focused checks:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m py_compile \
  program_code/ml_training/run_training_pipeline.py \
  program_code/ml_training/quantile_reports.py \
  program_code/ml_training/pit_dataset_manifest.py \
  program_code/ml_training/pit_dataset_manifest_builder.py \
  program_code/ml_training/model_registry.py

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q \
  program_code/ml_training/tests/test_run_training_pipeline.py \
  program_code/ml_training/tests/test_quantile_reports.py \
  program_code/ml_training/tests/test_pit_dataset_manifest.py \
  program_code/ml_training/tests/test_pit_dataset_manifest_builder.py \
  -p no:cacheprovider

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q \
  program_code/ml_training/tests/test_model_registry.py \
  program_code/ml_training/tests/test_registry_serving_contract.py \
  -p no:cacheprovider

git diff --check
```

QA adjacency, if E1 changes shared report semantics:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q \
  program_code/ml_training/tests/test_run_training_pipeline.py \
  program_code/ml_training/tests/test_quantile_trainer.py \
  program_code/ml_training/tests/test_proof_packet_contract.py \
  program_code/ml_training/tests/test_pit_dataset_manifest.py \
  program_code/ml_training/tests/test_registry_serving_contract.py \
  -p no:cacheprovider
```

No Linux runtime, PG, exchange, private-read, or deploy verification is required for WP2.1 source closure.

## Boundary Confirmation

This PA task is source/docs/tests design only.

Allowed for E1: source edits, tests, docs/reports.

Denied for E1 and this PA task:

- runtime mutation
- DB read/write or migration apply
- exchange/private read
- MCP server/config mutation
- secret access
- order/probe
- Cost Gate change
- deploy/restart
- live/mainnet
- bounded Demo outcome ingestion

PA did not implement feature code, did not run runtime commands, did not read DB, did not contact exchange, and did not commit/push.

PA DESIGN DONE: report path: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-07--wp2_1_training_run_pit_manifest_gate_design.md`
