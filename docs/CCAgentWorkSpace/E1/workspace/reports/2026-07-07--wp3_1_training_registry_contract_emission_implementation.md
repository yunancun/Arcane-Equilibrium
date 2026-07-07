# WP3.1 Training Registry Contract Emission Implementation

Date: 2026-07-07

Role: `E1(worker)`

Status: `DONE`

## Scope

Implemented source-only `WP3.1-TRAINING-REGISTRY-CONTRACT-EMISSION` under the PM/PA dispatch boundary.

Changed paths:

- `program_code/ml_training/registry_serving_contract.py`
- `program_code/ml_training/run_training_pipeline.py`
- `program_code/ml_training/tests/test_registry_serving_contract.py`
- `program_code/ml_training/tests/test_run_training_pipeline.py`
- `docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-07--wp3_1_training_registry_contract_emission_implementation.md`
- `docs/CCAgentWorkSpace/E1/memory.md`

No changes were made to `test_model_registry.py`.

## Implementation

- Added `build_registry_serving_contract_from_training_acceptance(...)`.
- Builder reads only caller-provided acceptance report, `onnx_out`, optional serving config, and ONNX artifact bytes.
- Builder requires PIT manifest + `training_pit_manifest_binding_v1`, validates `contract_bound_run=True`, `status=dataset_ready`, manifest hash parity, acceptance feature hash parity, PIT lineage hashes, exact ordered q10/q50/q90 written artifacts, and artifact sha256 bytes.
- Builder computes `serving_config_hash`, `contract_hash`, validates with `validate_registry_serving_contract`, and raises `RegistryServingContractError` on invalid/missing/mismatch/authority alias inputs.
- `_run_quantile_pipeline(...)` now builds the contract after ONNX export and before registry DB connectivity precheck for `pit_binding.contract_bound_run` only.
- Contract-bound path persists the canonical `registry_serving_contract` into the acceptance report via same-directory temp + replace, then passes the same contract to `register_quantile_trio_from_onnx_out(...)`.
- Non-contract-bound path does not synthesize a contract and does not pass the `registry_serving_contract` keyword.
- `no_ship` remains no ONNX export and no registry contract emission.

## Tests

Commands run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m py_compile program_code/ml_training/registry_serving_contract.py program_code/ml_training/model_registry.py program_code/ml_training/run_training_pipeline.py program_code/ml_training/quantile_reports.py
```

Result: `PASS`

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_registry_serving_contract.py program_code/ml_training/tests/test_model_registry.py program_code/ml_training/tests/test_run_training_pipeline.py -p no:cacheprovider
```

Result: `74 passed in 0.65s`

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_run_training_pipeline.py program_code/ml_training/tests/test_quantile_reports.py program_code/ml_training/tests/test_pit_dataset_manifest.py program_code/ml_training/tests/test_pit_dataset_manifest_builder.py program_code/ml_training/tests/test_registry_serving_contract.py program_code/ml_training/tests/test_model_registry.py -p no:cacheprovider
```

Result: `106 passed, 1 skipped in 0.65s`

```bash
git diff --check -- program_code/ml_training/registry_serving_contract.py program_code/ml_training/run_training_pipeline.py program_code/ml_training/tests/test_registry_serving_contract.py program_code/ml_training/tests/test_model_registry.py program_code/ml_training/tests/test_run_training_pipeline.py
```

Result: `PASS`

## Boundary Statement

This implementation was source-only. I did not perform DB read/write, migration, runtime mutation, service restart, deploy, exchange/private read, secret access, order/probe, Cost Gate change, live/mainnet action, commit, or stage.

Existing unrelated dirty files under memory, IBKR connector, Bybit control API, and PA/operator report paths were left untouched.

## Concern

`run_training_pipeline.py` remains above the 800-line review-attention threshold. Edits were kept surgical per PA instruction; no broad extraction was attempted.
