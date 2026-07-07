# WP3.1 Training Registry Contract Emission Design

Date: 2026-07-07

PA verdict: `E1_READY_SOURCE_ONLY`

Scope: `WP3.1-TRAINING-REGISTRY-CONTRACT-EMISSION`

This is a source-only architecture/design pass. It does not authorize runtime
mutation, DB write, DB read, migration, exchange/private read, MCP server/config,
secret access, order/probe, Cost Gate change, deploy, live/mainnet, model reload,
serving-slot write, symlink promotion, or proof promotion.

## Selected Roadmap Work Item

Selected item: `WP3.1-TRAINING-REGISTRY-CONTRACT-EMISSION`.

Dependency state:

- WP2.1 is complete at local commit `e84d2c249`: contract-bound quantile training
  now requires a PIT dataset manifest and writes canonical
  `pit_dataset_manifest` plus `training_pit_manifest_binding_v1` into the
  acceptance report.
- Runtime/loss-control remains `RUNTIME_LOSS_CONTROL_BLOCKED`; WP3.1 must stay
  source-only.
- Current local HEAD during this PA pass is `e84d2c249`; `origin/main` observed
  at `77f0b567`. This design does not perform git, sync, runtime, or DB actions.

Goal:

- Generate `registry_serving_contract_v1` from the training acceptance report,
  PIT manifest/binding, feature/schema hashes, and exact q10/q50/q90 ONNX
  artifact hashes.
- Pass that contract to `register_quantile_trio_from_onnx_out(...)`.
- Fail closed before registry persistence when the contract or artifact parity
  is invalid.
- Preserve advisory-only semantics: registry metadata is not serving authority,
  not promotion authority, not symlink authority, and not model reload authority.

## Current Source Interfaces

### Training pipeline

`program_code/ml_training/run_training_pipeline.py`

- `PipelineConfig` now has `contract_bound_run`, `candidate_id`, `side`,
  `pit_dataset_manifest`, `pit_dataset_manifest_path`, and
  `pit_dataset_manifest_source`.
- `_resolve_training_pit_binding(...)` validates or builds the PIT manifest
  before `train_quantile_trio`.
- `generate_acceptance_report(...)` is called with:
  - `pit_dataset_manifest=pit_binding.manifest`
  - `pit_dataset_manifest_binding=pit_binding.to_report_binding()`
  - `persist_required=pit_binding.contract_bound_run`
- After ONNX export, the registry call currently passes no
  `registry_serving_contract`.

Important existing call site:

```python
registry_ids = register_quantile_trio_from_onnx_out(
    onnx_out=onnx_out,
    strategy=config.strategy_type,
    engine_mode=config.engine_mode,
    schema_version=config.schema_version,
    verdict=result.verdict,
    acceptance_report_path=result.acceptance_report_path,
    feature_schema_hash=train_result.feature_schema_hash,
    training_sample_size=...,
    dsn=config.dsn,
)
```

### Acceptance report

`program_code/ml_training/quantile_reports.py`

The report already carries:

- `feature_schema_hash`
- `feature_definition_hash`
- `pit_dataset_manifest`
- `pit_dataset_manifest_binding`
- `label_composition`
- `gates`
- `cqr_offsets`
- `train_serve_harness`

For WP3.1, E1 should attach `registry_serving_contract` to the persisted
acceptance report through the existing model-registry path rather than invent a
second report field or alias. The canonical field is already
`registry_serving_contract`.

### PIT manifest source fields

`program_code/ml_training/pit_dataset_manifest.py`
`program_code/ml_training/pit_dataset_manifest_builder.py`

The PIT manifest already provides the required hashes for the serving contract:

- `manifest_hash`
- `feature_lineage.feature_schema_hash`
- `feature_lineage.feature_definition_hash`
- `label_lineage.label_schema_hash`
- `split_lineage.split_hash`
- `leakage_evidence.leakage_report_hash`

E1 should reuse these fields. Do not derive them from display strings or from
the training output directory.

### Registry serving contract validator

`program_code/ml_training/registry_serving_contract.py`

Already implemented:

- `REGISTRY_SERVING_CONTRACT_FIELD = "registry_serving_contract"`
- `REGISTRY_SERVING_CONTRACT_SCHEMA_VERSION = "registry_serving_contract_v1"`
- `compute_registry_serving_contract_hash(...)`
- `validate_registry_serving_contract(...)`
- `attach_registry_serving_contract(...)`

Validator requirements include:

- exact top-level field set;
- `serving_mode == "advisory_only"`;
- `not_authority is True`;
- `symlink_authority is False`;
- `promotion_serving_ready is False`;
- `dataset_manifest_schema_version == "pit_dataset_manifest_v1"`;
- stable hashes for PIT, label, feature, split, leakage, serving config;
- non-empty policy strings: `missingness_policy`, `units`, `side_handling`;
- exact ordered q10/q50/q90 trio and artifact hashes;
- no authority-expansion aliases anywhere in the nested contract.

### Model registry

`program_code/ml_training/model_registry.py`

Already implemented:

- `register_quantile_trio_from_onnx_out(..., registry_serving_contract=None)`
- When a contract is supplied, it:
  - validates and attaches the contract to acceptance report JSON;
  - requires exact written q10/q50/q90 artifacts;
  - verifies contract artifact hashes against actual file sha256 before DB
    connection;
  - writes q10/q50/q90 in one DB transaction;
  - raises `RegistryServingContractError` on incomplete trio persistence.

Gap:

- Training pipeline does not build/pass `registry_serving_contract`.

## Recommended Implementation Scope

Add one small builder surface and wire it into the quantile pipeline.

### Files E1 should edit

Primary:

- `program_code/ml_training/registry_serving_contract.py`
- `program_code/ml_training/run_training_pipeline.py`
- `program_code/ml_training/tests/test_registry_serving_contract.py`
- `program_code/ml_training/tests/test_run_training_pipeline.py`

Optional only if needed for focused registry adjacency:

- `program_code/ml_training/tests/test_model_registry.py`

Do not edit runtime services, Rust, exchange connectors, migrations, GUI,
cron, TODO, or unrelated dirty files.

### Builder API

Add a pure source-only function to `registry_serving_contract.py`:

```python
def build_registry_serving_contract_from_training_acceptance(
    *,
    acceptance_report: Mapping[str, Any],
    onnx_out: Mapping[str, Any],
    serving_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    ...
```

Required behavior:

1. Read only in-memory `acceptance_report` and caller-provided `onnx_out`.
2. Require `acceptance_report["pit_dataset_manifest"]` mapping.
3. Require `acceptance_report["pit_dataset_manifest_binding"]` with:
   - `schema_version == "training_pit_manifest_binding_v1"`
   - `contract_bound_run is True`
   - `status == "dataset_ready"`
   - `manifest_hash` present and equal to manifest `manifest_hash`
4. Pull contract hashes from canonical manifest fields:
   - `dataset_manifest_hash = manifest["manifest_hash"]`
   - `label_schema_hash = manifest["label_lineage"]["label_schema_hash"]`
   - `feature_schema_hash = acceptance_report["feature_schema_hash"]`
   - `feature_definition_hash = acceptance_report["feature_definition_hash"]`
   - `split_hash = manifest["split_lineage"]["split_hash"]`
   - `leakage_report_hash = manifest["leakage_evidence"]["leakage_report_hash"]`
5. Cross-check acceptance feature hashes against manifest feature lineage:
   - `acceptance_report["feature_schema_hash"] == manifest["feature_lineage"]["feature_schema_hash"]`
   - `acceptance_report["feature_definition_hash"] == manifest["feature_lineage"]["feature_definition_hash"]`
6. Compute q10/q50/q90 artifact hashes from `onnx_out["artifacts"][q]["path"]`.
   Use existing `_file_size_and_sha256` only from `model_registry.py` if E1
   decides import coupling is acceptable; otherwise implement a local standard
   library sha256 helper in `registry_serving_contract.py`. Either way, no DB,
   runtime, env, or exchange access.
7. Require exact artifact keys and order `("q10", "q50", "q90")`, each with
   `written=True`, non-empty `path`, and readable bytes.
8. Set:
   - `schema_version = "registry_serving_contract_v1"`
   - `serving_mode = "advisory_only"`
   - `not_authority = True`
   - `symlink_authority = False`
   - `promotion_serving_ready = False`
   - `dataset_manifest_schema_version = "pit_dataset_manifest_v1"`
   - `artifact_hashes = {"q10": ..., "q50": ..., "q90": ...}`
   - `quantile_trio = ["q10", "q50", "q90"]`
9. Derive `serving_config_hash` from a canonical source-only payload. Suggested
   minimal default:
   - `schema_version`
   - `feature_schema_hash`
   - `feature_definition_hash`
   - `quantile_trio`
   - `missingness_policy`
   - `units`
   - `side_handling`
   - any explicit `serving_config` values supplied by caller.
10. Set policy strings explicitly:
   - `missingness_policy`: default to a conservative string such as
     `missing_or_nan=reject;unknown_feature=reject`
   - `units`: default to `prediction=edge_bps;artifact=onnx`
   - `side_handling`: include side source, for example
     `candidate_scope_side_required=true;side=<manifest candidate_scope.side>`
11. Compute and insert `contract_hash` using
    `compute_registry_serving_contract_hash`.
12. Validate with `validate_registry_serving_contract`; raise
    `RegistryServingContractError` if not advisory-ready.

Builder output must be deterministic for identical report and artifact bytes.

### Pipeline wiring

In `_run_quantile_pipeline(...)`, after ONNX export and before registry
connectivity precheck:

1. If `pit_binding.contract_bound_run` is true:
   - build the contract from the in-memory `report` and `onnx_out`;
   - optionally persist/replace the acceptance report with the contract attached
     before registry call, or rely on `register_quantile_trio_from_onnx_out` to
     attach before DB JSONB. PA recommends persisting it too, because WP3.1
     acceptance requires the training acceptance report itself to carry the
     contract. Use the same same-directory temp + replace pattern already used
     by `quantile_reports.py`.
   - pass `registry_serving_contract=contract` to
     `register_quantile_trio_from_onnx_out(...)`.
2. If `contract_bound_run` is false:
   - preserve current behavior and do not synthesize a registry contract.
3. If verdict is `no_ship`:
   - no ONNX export occurs today; therefore no registry contract is emitted.
     This is acceptable and should be explicit in tests if E1 touches this
     branch.

Important ordering:

- Build and validate the contract before `check_db_connectivity`.
- Artifact hash mismatch, missing trio, missing PIT binding, or authority alias
  must fail before any DB connection.

### Fail-Closed Cases

E1 must cover at least these cases:

- missing acceptance report PIT manifest;
- missing `pit_dataset_manifest_binding`;
- binding `contract_bound_run` false when contract-bound registry emission is
  requested;
- binding manifest hash mismatches manifest `manifest_hash`;
- acceptance `feature_schema_hash` mismatches manifest feature lineage;
- acceptance `feature_definition_hash` mismatches manifest feature lineage;
- missing `label_lineage.label_schema_hash`;
- missing `split_lineage.split_hash`;
- missing `leakage_evidence.leakage_report_hash`;
- ONNX output lacks exact q10/q50/q90 trio;
- artifact path missing or unreadable;
- contract artifact hash mismatch before DB connect;
- authority expansion alias in caller-supplied serving config or generated
  payload, such as `serving_authority_granted=true`, `promotion_allowed=true`,
  `order_allowed=true`, or `symlink_allowed=true`;
- non-contract-bound legacy or quantile route must not silently emit a contract;
- dry-run/no-DB mode must produce/validate the contract and then fail or skip
  according to existing registry persistence rules without performing DB work
  when tests patch the registry path.

## Out-Of-Scope Denied Actions

Denied for E1:

- no DB schema migration;
- no live PG empirical write;
- no runtime file write outside test temp dirs;
- no service restart or deploy;
- no runtime model loading or EdgePredictor reload;
- no `_current` symlink mutation;
- no canary promotion or canary status transition;
- no Cost Gate change;
- no exchange/private read;
- no order/probe/live/mainnet path;
- no changes to Rust authority, Decision Lease, Guardian, or Bybit connector;
- no broad refactor of `run_training_pipeline.py` despite the 800-line review
  attention warning.

## Tests E1 Must Add Or Run

Focused compile:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m py_compile \
  program_code/ml_training/registry_serving_contract.py \
  program_code/ml_training/model_registry.py \
  program_code/ml_training/run_training_pipeline.py \
  program_code/ml_training/quantile_reports.py
```

New/updated focused tests:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q \
  program_code/ml_training/tests/test_registry_serving_contract.py \
  program_code/ml_training/tests/test_model_registry.py \
  program_code/ml_training/tests/test_run_training_pipeline.py \
  -p no:cacheprovider
```

Adjacency regression:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q \
  program_code/ml_training/tests/test_run_training_pipeline.py \
  program_code/ml_training/tests/test_quantile_reports.py \
  program_code/ml_training/tests/test_pit_dataset_manifest.py \
  program_code/ml_training/tests/test_pit_dataset_manifest_builder.py \
  program_code/ml_training/tests/test_registry_serving_contract.py \
  program_code/ml_training/tests/test_model_registry.py \
  -p no:cacheprovider
```

Diff hygiene:

```bash
git -C /Users/ncyu/Projects/TradeBot/srv diff --check -- \
  program_code/ml_training/registry_serving_contract.py \
  program_code/ml_training/run_training_pipeline.py \
  program_code/ml_training/tests/test_registry_serving_contract.py \
  program_code/ml_training/tests/test_model_registry.py \
  program_code/ml_training/tests/test_run_training_pipeline.py
```

If Mac lacks optional training dependencies, E1 should keep the tests patched at
the existing unit seam (`fake_train`, `fake_export`, fake registry) rather than
requiring a real LightGBM/ONNX/PG stack.

## E1 Dispatch Packet

Bound role: `E1(worker)`

Ownership:

- `program_code/ml_training/registry_serving_contract.py`
- `program_code/ml_training/run_training_pipeline.py`
- focused tests listed above

Task shape: implementation.

Expected output:

- patch only, no commit;
- E1 report at `docs/CCAgentWorkSpace/E1/workspace/reports/`;
- exact test commands and results;
- explicit boundary statement confirming no DB/runtime/exchange/order/Cost Gate
  work.

Implementation instructions:

1. Implement a pure builder in `registry_serving_contract.py`.
2. Wire `_run_quantile_pipeline(...)` to build/pass the contract only for
   `contract_bound_run=True` after ONNX export and before DB connectivity.
3. Ensure the persisted acceptance report contains
   `registry_serving_contract` when contract-bound registry emission succeeds.
4. Preserve current non-contract-bound behavior.
5. Reuse existing validator and model-registry atomic trio path.
6. Add focused tests for builder happy path, hash mismatch, missing trio,
   authority alias rejection, pipeline pass-through to registry, and no-DB
   dry-run behavior.

E2 focus after E1:

- builder cannot read DB/runtime/env/exchange/secret;
- contract hash is deterministic and excludes only `contract_hash`;
- acceptance/PIT/manifest feature hashes are cross-checked, not blindly copied;
- artifact hash verification happens before DB connect;
- no authority aliases can be smuggled through generated or caller-supplied
  serving config;
- non-contract-bound route stays behavior-compatible.

## Acceptance Criteria

WP3.1 is acceptable when all are true:

1. Contract-bound quantile training emits a valid
   `registry_serving_contract_v1` built from the persisted acceptance report,
   PIT manifest/binding, feature/schema hashes, and q10/q50/q90 ONNX artifact
   bytes.
2. The persisted acceptance report contains canonical
   `registry_serving_contract`.
3. `register_quantile_trio_from_onnx_out(...)` receives the same contract and
   uses the existing atomic q10/q50/q90 path.
4. Missing or mismatched PIT/feature/schema/artifact data fails before DB
   connection.
5. Contract validation rejects authority expansion and preserves:
   - `not_authority=true`
   - `promotion_serving_ready=false`
   - `symlink_authority=false`
   - `serving_mode=advisory_only`
6. Non-contract-bound training keeps current behavior and emits no fake
   registry contract.
7. Focused tests and diff check pass.
8. No DB/runtime/exchange/order/Cost Gate/live/deploy action is performed.

Residual concern:

- `run_training_pipeline.py` is already above the 800-line review-attention
  threshold. E1 should keep edits minimal and avoid opportunistic extraction in
  this work item.
