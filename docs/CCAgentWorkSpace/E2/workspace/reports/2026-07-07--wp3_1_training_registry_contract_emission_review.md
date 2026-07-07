# WP3.1 Training Registry Contract Emission Review

Date: 2026-07-07

Role: `E2(explorer/reviewer)`

Verdict: `PASS_TO_E4`

## Scope

Narrow source review for `WP3.1-TRAINING-REGISTRY-CONTRACT-EMISSION`.

Reviewed files:

- `program_code/ml_training/registry_serving_contract.py`
- `program_code/ml_training/run_training_pipeline.py`
- `program_code/ml_training/tests/test_registry_serving_contract.py`
- `program_code/ml_training/tests/test_run_training_pipeline.py`
- `program_code/ml_training/model_registry.py` call-contract only

Existing unrelated dirty files under memory, IBKR, and Bybit `control_api_v1`
were observed and ignored because they do not overlap this patch.

## Findings

No blocking findings.

### Non-blocking Review Notes

- `program_code/ml_training/registry_serving_contract.py:165` builds the
  contract from caller-provided `acceptance_report`, caller-provided `onnx_out`,
  optional `serving_config`, and local ONNX artifact bytes only. I found no DB,
  runtime, env, exchange, secret, order, Cost Gate, deploy, live/mainnet, or
  service path inside the builder.
- `program_code/ml_training/registry_serving_contract.py:190-337` requires the
  PIT manifest mapping plus `training_pit_manifest_binding_v1`, enforces
  `contract_bound_run is True`, `status == dataset_ready`, binding/manifest hash
  parity, acceptance-vs-manifest feature hash parity, canonical PIT lineage
  hashes, exact q10/q50/q90 written artifacts, deterministic artifact sha256
  hashes, authority-alias rejection from `serving_config`, contract hash
  insertion, and final `validate_registry_serving_contract(...)`.
- `program_code/ml_training/run_training_pipeline.py:796-865` builds and
  persists the `registry_serving_contract` only when
  `pit_binding.contract_bound_run` is true, after ONNX export and before
  `check_db_connectivity(...)` / registry persistence. Non-contract-bound runs
  do not synthesize or pass a registry contract.
- `program_code/ml_training/tests/test_run_training_pipeline.py:531-561` covers
  the key ordering invariant: malformed ONNX trio fails before DB connectivity
  precheck and before registry call.
- Test coverage is focused and sufficient for E4 handoff. Useful future
  hardening tests would explicitly cover binding schema/status failures,
  `written=False`, artifact key order mismatch, missing label/split/leakage
  lineage fields, and a non-v1 PIT manifest schema. The current code either
  handles these through existing validation paths or, for manifest schema, relies
  on upstream WP2.1 PIT manifest validation and the accepted PA design; I do not
  treat this as a WP3.1 blocker.
- `program_code/ml_training/run_training_pipeline.py` is 1046 lines, above the
  800-line review-attention threshold and below the 2000-line hard cap. The
  added WP3.1 code is localized; line count is review attention only, not a
  maintainability blocker for this patch.

## Verification

Commands run from `/Users/ncyu/Projects/TradeBot/srv`:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m py_compile program_code/ml_training/registry_serving_contract.py program_code/ml_training/model_registry.py program_code/ml_training/run_training_pipeline.py program_code/ml_training/quantile_reports.py
```

Result: PASS.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_registry_serving_contract.py program_code/ml_training/tests/test_model_registry.py program_code/ml_training/tests/test_run_training_pipeline.py -p no:cacheprovider
```

Result: `74 passed in 0.60s`.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_run_training_pipeline.py program_code/ml_training/tests/test_quantile_reports.py program_code/ml_training/tests/test_pit_dataset_manifest.py program_code/ml_training/tests/test_pit_dataset_manifest_builder.py program_code/ml_training/tests/test_registry_serving_contract.py program_code/ml_training/tests/test_model_registry.py -p no:cacheprovider
```

Result: `106 passed, 1 skipped in 0.68s`.

```bash
git diff --check -- program_code/ml_training/registry_serving_contract.py program_code/ml_training/run_training_pipeline.py program_code/ml_training/tests/test_registry_serving_contract.py program_code/ml_training/tests/test_model_registry.py program_code/ml_training/tests/test_run_training_pipeline.py
```

Result: PASS.

Additional checks:

```bash
wc -l program_code/ml_training/registry_serving_contract.py program_code/ml_training/run_training_pipeline.py program_code/ml_training/tests/test_registry_serving_contract.py program_code/ml_training/tests/test_run_training_pipeline.py program_code/ml_training/model_registry.py
```

Result: `registry_serving_contract.py` 740, `run_training_pipeline.py` 1046,
`test_registry_serving_contract.py` 388, `test_run_training_pipeline.py` 580,
`model_registry.py` 738.

```bash
rg -n "os\.environ|getenv|psycopg|requests|bybit|secret|OPENCLAW|DATABASE|DSN|connect|sqlite|postgres|subprocess|socket" program_code/ml_training/registry_serving_contract.py program_code/ml_training/run_training_pipeline.py program_code/ml_training/tests/test_registry_serving_contract.py program_code/ml_training/tests/test_run_training_pipeline.py
```

Result: no new builder-side DB/runtime/env/exchange/secret access; hits are
existing pipeline/default-path/registry-precheck references, tests, comments, or
authority-deny vocabulary.

## Boundary Statement

Review was source-only. I did not modify production/test code, stage, commit,
push, read/write DB, touch runtime services, restart/deploy, access exchange or
secrets, place orders/probes, change Cost Gate, symlink/promote/reload models,
or perform live/mainnet actions.
