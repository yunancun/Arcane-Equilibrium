# AI/ML Downstream Loop WP3.1 Training Registry Contract Emission

Date: 2026-07-07

PM status: `ADVANCED_SOURCE_ONLY`

Work item: `WP3.1-TRAINING-REGISTRY-CONTRACT-EMISSION`

Recovered from:

- Prior state packet: `2026-07-07--ai_ml_downstream_loop_wp2_1_training_run_pit_manifest_gate.state_packet.json`
- Prior completed commit: `e84d2c24967c0fac95b2d2a3ad15b53480260d16`
- Neighbor classification: `WP5_MAPPING_READY`, `RUNTIME_LOSS_CONTROL_BLOCKED`

## Selection

WP3.1 was selected because WP2.1 already made contract-bound quantile training
PIT-manifest-bound, but the training pipeline still did not emit the
`registry_serving_contract_v1` expected by downstream registry/proof closure.
The work was source-safe and did not require runtime, DB, exchange, credential,
order, Cost Gate, deploy, live, or bounded Demo outcome access.

## Dispatch Chain

Required source feature chain was completed:

- PM -> PA: design pass `2026-07-07--wp3_1_training_registry_contract_emission_design.md`
- PA -> E1: source implementation `2026-07-07--wp3_1_training_registry_contract_emission_implementation.md`
- E1 -> E2: narrow source review `PASS_TO_E4`
- E2 -> E4: regression `PASS`
- E4 -> QA: source acceptance `PASS`
- QA -> PM: this PM effect review/state checkpoint

## Implementation Delta

Primary source changes:

- `program_code/ml_training/registry_serving_contract.py`
  - adds `build_registry_serving_contract_from_training_acceptance(...)`;
  - reads only caller-provided acceptance report, `onnx_out`, optional serving
    config, and local ONNX artifact bytes;
  - requires PIT manifest plus `training_pit_manifest_binding_v1`;
  - cross-checks manifest hash and acceptance-vs-manifest feature hashes;
  - requires exact ordered q10/q50/q90 written ONNX artifact trio;
  - computes artifact hashes, `serving_config_hash`, and `contract_hash`;
  - validates final advisory-only contract and rejects authority aliases.
- `program_code/ml_training/run_training_pipeline.py`
  - builds the contract only for `contract_bound_run=True` after ONNX export and
    before DB connectivity precheck;
  - persists canonical `registry_serving_contract` into the acceptance report
    via same-directory temp plus replace;
  - passes the same contract to `register_quantile_trio_from_onnx_out(...)`;
  - leaves non-contract-bound behavior unchanged and emits no synthetic
    registry contract.
- Focused tests cover deterministic builder output, PIT/binding mismatch,
  feature mismatch, missing artifact/trio, authority alias rejection, pipeline
  persistence/pass-through, non-contract behavior, and fail-before-DB ordering.

## Verification

PM accepted the following source evidence:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m py_compile program_code/ml_training/registry_serving_contract.py program_code/ml_training/model_registry.py program_code/ml_training/run_training_pipeline.py program_code/ml_training/quantile_reports.py
```

Result: `PASS`.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_registry_serving_contract.py program_code/ml_training/tests/test_model_registry.py program_code/ml_training/tests/test_run_training_pipeline.py -p no:cacheprovider
```

Result: `74 passed` across E1/E2/E4/QA replays.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_run_training_pipeline.py program_code/ml_training/tests/test_quantile_reports.py program_code/ml_training/tests/test_pit_dataset_manifest.py program_code/ml_training/tests/test_pit_dataset_manifest_builder.py program_code/ml_training/tests/test_registry_serving_contract.py program_code/ml_training/tests/test_model_registry.py -p no:cacheprovider
```

Result: `106 passed, 1 skipped`.

```bash
git diff --check -- WP3.1 scoped source/report paths
```

Result: `PASS`.

## Effect Review

Verdict: `EFFECTIVE`

The checkpoint closes the WP3.1 source gap: a contract-bound training acceptance
report can now carry both the PIT manifest binding and a canonical
`registry_serving_contract_v1`, and malformed lineage/artifact/authority inputs
fail before DB connectivity or registry persistence calls.

This does not prove profit, bounded Demo outcome quality, DB registry
persistence, model-serving reload, symlink promotion, Cost Gate change, or
runtime learning. Those remain gated.

## Boundary

No denied action was performed or introduced:

- no runtime mutation;
- no DB empirical read/write or migration;
- no exchange/private read;
- no MCP server/config or credential/secret access;
- no order/probe;
- no Cost Gate change;
- no deploy;
- no live/mainnet action;
- no model reload or symlink promotion;
- no bounded Demo outcome ingestion.

## State

State packet: `2026-07-07--ai_ml_downstream_loop_wp3_1_training_registry_contract_emission.state_packet.json`

Status: `ADVANCED`

Next work id: `WP6-REWARD-LEDGER-PROOFPACKET-BRIDGE`

Concerns:

- `run_training_pipeline.py` is 1046 lines, above the 800-line review-attention
  threshold and below the 2000-line hard cap; E2/E4/QA accepted this as
  non-blocking for the localized patch.
- Runtime/loss-control remains `RUNTIME_LOSS_CONTROL_BLOCKED`; no runtime branch
  was consumed.
