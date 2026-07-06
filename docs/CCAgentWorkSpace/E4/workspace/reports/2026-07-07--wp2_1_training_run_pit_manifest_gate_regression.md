# WP2.1 Training Run PIT Manifest Gate - E4 Regression

Date: 2026-07-07

Role: `E4(worker)`

Status: `DONE`

Verdict: `PASS`

Task: `WP2.1-TRAINING-RUN-PIT-MANIFEST-GATE` post-E2 PASS regression.

## Scope

Read and used:

- PA design: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-07--wp2_1_training_run_pit_manifest_gate_design.md`
- E1 updated report: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-07--wp2_1_training_run_pit_manifest_gate_implementation.md`
- E2 PASS re-review: `docs/CCAgentWorkSpace/E2/workspace/reports/2026-07-07--wp2_1_training_run_pit_manifest_gate_rereview.md`

In-scope source/test files were limited to the WP2.1 ML training pipeline/report surface. E4 did not modify business logic, tests, runtime config, DB, exchange paths, secrets, deploy state, Cost Gate, order/probe paths, live, or mainnet. E4 did not commit or push.

## Results

| Check | Run 1 | Run 2 | Verdict |
|---|---:|---:|---|
| `py_compile` for WP2.1 training/manifest/registry files | passed | N/A | PASS |
| Focused WP2.1 pytest | `46 passed, 1 skipped` | `46 passed, 1 skipped` | PASS |
| Registry adjacency pytest | `49 passed` | `49 passed` | PASS |
| QA adjacency pytest | `90 passed, 1 skipped` | `90 passed, 1 skipped` | PASS |
| `git diff --check` on requested WP2.1 paths | passed | N/A | PASS |

## Commands

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m py_compile \
  program_code/ml_training/run_training_pipeline.py \
  program_code/ml_training/quantile_reports.py \
  program_code/ml_training/pit_dataset_manifest.py \
  program_code/ml_training/pit_dataset_manifest_builder.py \
  program_code/ml_training/model_registry.py
```

Result: passed, no output.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q \
  program_code/ml_training/tests/test_run_training_pipeline.py \
  program_code/ml_training/tests/test_quantile_reports.py \
  program_code/ml_training/tests/test_pit_dataset_manifest.py \
  program_code/ml_training/tests/test_pit_dataset_manifest_builder.py \
  -p no:cacheprovider
```

Run 1: `46 passed, 1 skipped in 0.29s`.

Run 2: `46 passed, 1 skipped in 0.28s`.

This matches the E1/E2 post-fix focused baseline of `46 passed, 1 skipped`; no in-scope test count regression.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q \
  program_code/ml_training/tests/test_model_registry.py \
  program_code/ml_training/tests/test_registry_serving_contract.py \
  -p no:cacheprovider
```

Run 1: `49 passed in 0.33s`.

Run 2: `49 passed in 0.33s`.

This matches the E1/E2 registry adjacency baseline of `49 passed`; no registry adjacency count regression.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q \
  program_code/ml_training/tests/test_run_training_pipeline.py \
  program_code/ml_training/tests/test_quantile_trainer.py \
  program_code/ml_training/tests/test_proof_packet_contract.py \
  program_code/ml_training/tests/test_pit_dataset_manifest.py \
  program_code/ml_training/tests/test_registry_serving_contract.py \
  -p no:cacheprovider
```

Run 1: `90 passed, 1 skipped in 0.35s`.

Run 2: `90 passed, 1 skipped in 0.35s`.

QA adjacency exact result recorded as requested.

```bash
git diff --check -- \
  program_code/ml_training/run_training_pipeline.py \
  program_code/ml_training/quantile_reports.py \
  program_code/ml_training/tests/test_run_training_pipeline.py \
  program_code/ml_training/tests/test_quantile_reports.py \
  docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-07--wp2_1_training_run_pit_manifest_gate_implementation.md \
  docs/CCAgentWorkSpace/E2/workspace/reports/2026-07-07--wp2_1_training_run_pit_manifest_gate_review.md \
  docs/CCAgentWorkSpace/E2/workspace/reports/2026-07-07--wp2_1_training_run_pit_manifest_gate_rereview.md
```

Result: passed, no output.

## Residual Risk

- `program_code/ml_training/run_training_pipeline.py` remains over the 800-line review-attention threshold noted by E2. It is below the 2000-line hard cap and was accepted by PA/E2 for this small helper scope.
- This was Mac source-only regression. Per PA design, no Linux runtime, PG, exchange, private-read, deploy, or live verification is required for WP2.1 source closure.

## Conclusion

E4 regression is PASS. The focused WP2.1 count stayed at `46 passed, 1 skipped`, registry adjacency stayed at `49 passed`, and QA adjacency was stable at `90 passed, 1 skipped` across two runs.

E4 REGRESSION DONE: PASS.
