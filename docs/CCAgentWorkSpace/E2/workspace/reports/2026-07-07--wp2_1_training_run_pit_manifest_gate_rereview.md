# WP2.1 Training Run PIT Manifest Gate - E2 Re-review

Date: 2026-07-07

Role: `E2(explorer)`

Status: `DONE`

Verdict: `PASS_TO_E4`

Finding counts: CRITICAL 0, HIGH 0, MEDIUM 0, LOW 0, INFO 2.

## Scope

Re-reviewed E1's E2 RETURN fixes for `WP2.1-TRAINING-RUN-PIT-MANIFEST-GATE`.

In-scope files:

- `program_code/ml_training/run_training_pipeline.py`
- `program_code/ml_training/quantile_reports.py`
- `program_code/ml_training/tests/test_run_training_pipeline.py`
- `program_code/ml_training/tests/test_quantile_reports.py`
- E1 report and memory completion evidence

Dirty worktree note: repo still has unrelated dirty memory, GUI/auth, IBKR, and PM report files. I did not touch, revert, format, stage, or modify unrelated files.

## RETURN Fix Verification

### MEDIUM-1: closed

PIT sidecar now writes through same-directory temp bytes and then `Path.replace()`:

- `run_training_pipeline.py:267-285`
- temp path uses `path.with_name(...)`, so parent directory is the final artifact directory.
- final artifact is replaced only after `tmp_path.write_bytes(payload)` succeeds.
- caught exceptions attempt to unlink the temp file before re-raising.

Acceptance report persistence now writes through same-directory temp JSON and then `Path.replace()`:

- `quantile_reports.py:423-445`
- `persist_required=True` raises `RuntimeError(...)`.
- default `persist_required=False` logs warning and returns the report, preserving fail-soft legacy behavior.

Regression coverage exists and is directionally correct:

- sidecar replace failure preserves existing final and asserts `train == 0`: `test_run_training_pipeline.py:365-393`
- required report `json.dump` failure preserves existing final and raises: `test_quantile_reports.py:335-368`
- optional report persistence failure preserves existing final and remains fail-soft: `test_quantile_reports.py:371-397`

Additional manual probe: induced JSON dump failure and sidecar replace failure under a temp directory; both preserved the old final file and left `0` matching temp files after caught failure.

### LOW-1: closed

Permanent pooled-symbol fail-before-train coverage now exists:

- `test_run_training_pipeline.py:309-327`
- parameterizes `symbol=None` and `"ALL"`
- asserts `result.error == "pit_manifest_pooled_symbol_not_allowed"`
- asserts stages stop at `["etl", "labels", "pit_manifest_gate_failed"]`
- asserts `calls["train"] == 0`

## Gate Ordering / Boundary Re-check

Gate ordering remains correct:

- `_resolve_training_pit_binding(...)` runs at `run_training_pipeline.py:660-670`.
- PIT gate failure returns before importing/calling `train_quantile_trio` at `run_training_pipeline.py:680-682`.
- acceptance report persistence and hash verification happen before ONNX export and registry: report at `720-747`, ONNX at `763`, registry at `809`.
- legacy scorer with `contract_bound_run=True` still fails closed before ETL/training at `run_training_pipeline.py:920-925`.

Hard-boundary posture unchanged: no DB migration, runtime mutation, exchange/private read, credential/secret access, order/probe, Cost Gate change, deploy/restart, live/mainnet path, or bounded Demo outcome ingestion observed in the WP2.1 delta.

## Atomicity / Temp / Race Notes

No blocking issue found.

- Caught Python exceptions clean temp files and preserve final artifacts.
- A process kill or host crash could leave a hidden temp file, but the final artifact remains unmodified; this is acceptable for PA's no-partial-final-artifact requirement.
- Temp names include pid plus object id and are same-directory. Normal pipeline/report calls allocate fresh payload/report objects, so no relevant collision was found for this source-only serialized training path.
- Concurrent writers to the same final artifact still have last-writer-wins semantics, which existed before; the new implementation avoids partial final-file exposure and does not introduce a new order/proof/runtime authority surface.

## INFO

### INFO-1 - `run_training_pipeline.py` remains over the 800-line review-attention threshold

Current line count is `1005`. This is below the 2000-line hard cap and follows PA's instruction to keep small private helpers in this file for WP2.1. Not a blocker for this re-review.

### INFO-2 - Legacy scorer direct metrics write remains out of this RETURN scope

`rg` still finds `metrics_path.write_text(...)` in the legacy scorer path. This is pre-existing legacy metrics persistence, not the WP2.1 PIT sidecar or acceptance report artifact addressed by MEDIUM-1.

## Verification Run By E2

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m py_compile \
  program_code/ml_training/run_training_pipeline.py \
  program_code/ml_training/quantile_reports.py \
  program_code/ml_training/pit_dataset_manifest.py \
  program_code/ml_training/pit_dataset_manifest_builder.py \
  program_code/ml_training/model_registry.py
```

Result: passed.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q \
  program_code/ml_training/tests/test_run_training_pipeline.py \
  program_code/ml_training/tests/test_quantile_reports.py \
  program_code/ml_training/tests/test_pit_dataset_manifest.py \
  program_code/ml_training/tests/test_pit_dataset_manifest_builder.py \
  -p no:cacheprovider
```

Result: `46 passed, 1 skipped in 0.28s`.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q \
  program_code/ml_training/tests/test_model_registry.py \
  program_code/ml_training/tests/test_registry_serving_contract.py \
  -p no:cacheprovider
```

Result: `49 passed in 0.34s`.

Additional checks:

- source grep confirms PIT sidecar/report use temp+replace; remaining direct writes are tests and legacy metrics path.
- manual atomic failure probe: old final preserved and temp count `0` for report and sidecar.

## Race / Worktree Checks

- `git fetch --prune origin` run before review.
- `HEAD`: `8b99833b9e16e3b03efbc6e2198177672687b0ea`
- `origin/main`: `798843f23b2fda66117cf95bfe7c996f97fdf543`
- `origin/main` is ancestor of `HEAD`; branch is ahead 5 and not behind.
- Recent `origin/main` commits in the 2h window do not overlap the WP2.1 four-file dirty scope. One origin commit touches `model_registry.py` / registry tests, but it is already in local HEAD and was covered by the registry adjacency pytest.

## Conclusion

E1 closed both E2 RETURN findings. The atomic persistence fix protects final PIT sidecar and acceptance report artifacts, preserves fail-soft defaults, and fails visibly for required contract-bound persistence. The pooled-symbol fail-before-train case now has permanent coverage for `None` and `"ALL"`.

E2 REVIEW DONE: `PASS_TO_E4` · report path: `docs/CCAgentWorkSpace/E2/workspace/reports/2026-07-07--wp2_1_training_run_pit_manifest_gate_rereview.md`
