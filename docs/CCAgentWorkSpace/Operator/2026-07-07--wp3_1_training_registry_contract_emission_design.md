# WP3.1 Training Registry Contract Emission Design

Status: `E1_READY_SOURCE_ONLY`

PA produced the design for `WP3.1-TRAINING-REGISTRY-CONTRACT-EMISSION`.

Key decision:

- Implement a pure source-only builder for `registry_serving_contract_v1`.
- Build it from the training acceptance report, WP2.1 PIT manifest/binding,
  feature/schema hashes, and exact q10/q50/q90 ONNX artifact sha256 hashes.
- Wire `run_training_pipeline.py` to pass the contract into
  `register_quantile_trio_from_onnx_out(...)` only for contract-bound quantile
  runs.
- Fail closed before DB connection on missing PIT binding, feature hash
  mismatch, missing trio, unreadable artifact, artifact hash mismatch, or any
  authority-expansion alias.

E1 target files:

- `program_code/ml_training/registry_serving_contract.py`
- `program_code/ml_training/run_training_pipeline.py`
- `program_code/ml_training/tests/test_registry_serving_contract.py`
- `program_code/ml_training/tests/test_run_training_pipeline.py`
- optional adjacency: `program_code/ml_training/tests/test_model_registry.py`

Denied actions remain unchanged:

- no DB/runtime writes;
- no migration;
- no exchange/private read;
- no secret/MCP/runtime config;
- no order/probe;
- no Cost Gate change;
- no deploy;
- no live/mainnet;
- no model reload, symlink promotion, or serving authority.

Acceptance summary:

- contract-bound dry-run/source tests can emit a valid acceptance report with
  canonical `registry_serving_contract`;
- registry call receives that same contract;
- invalid hashes or partial q10/q50/q90 artifacts fail before DB connect;
- non-contract-bound training preserves existing behavior.

Full PA report:

- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-07--wp3_1_training_registry_contract_emission_design.md`
