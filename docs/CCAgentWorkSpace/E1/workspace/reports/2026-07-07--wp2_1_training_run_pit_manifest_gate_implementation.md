# WP2.1 Training Run PIT Manifest Gate Implementation

Date: 2026-07-07

Role: `E1(worker)`

Status: `DONE`

## 任務摘要

依 PA design 實作 `WP2.1-TRAINING-RUN-PIT-MANIFEST-GATE` 的 source-only patch。範圍限定於 ML training pipeline/report/tests；未 commit、未 push、未碰 runtime/DB/exchange/secret/deploy/Cost Gate/order/probe/live。

## 修改清單

- `program_code/ml_training/run_training_pipeline.py`
  - `PipelineConfig` 新增 `contract_bound_run`、`candidate_id`、`side`、`pit_dataset_manifest`、`pit_dataset_manifest_path`、`pit_dataset_manifest_source`。
  - `PipelineResult` 新增 PIT binding audit 欄位：`contract_bound_run`、manifest hash/path/status/reason。
  - 新增 `PitBinding` 與 private helper，支援 explicit manifest/path/source mapping、contract-bound dry-run synthetic manifest、candidate-scope match、canonical sidecar 寫入。
  - Contract-bound quantile run 在 `train_quantile_trio` 前驗證 `pit_dataset_manifest_v1` 必須 `dataset_ready`，且 candidate scope 必須匹配；pooled symbol、missing manifest、hash mismatch、unpinned/leakage source、scope mismatch 皆 fail-closed。
  - `contract_bound_run=True` 且 legacy scorer path 直接 fail-closed：`contract_bound_quantile_path_required`。
- `program_code/ml_training/quantile_reports.py`
  - `generate_acceptance_report` 新增 additive `pit_dataset_manifest`、`pit_dataset_manifest_binding`、`persist_required`。
  - Non-contract-bound caller 會得到 explicit `training_pit_manifest_binding_v1` / `not_contract_bound` binding。
  - `persist_required=True` 時 acceptance report 寫入失敗 fail-loud；舊 caller default 仍 fail-soft。
- `program_code/ml_training/tests/test_run_training_pipeline.py`
  - 新增 focused gate tests：missing manifest、invalid hash、candidate mismatch、unpinned query/leakage overlap、contract-bound dry-run sidecar/report、non-contract-bound binding、legacy scorer fail-closed。
- `program_code/ml_training/tests/test_quantile_reports.py`
  - 新增 PIT binding default 與 explicit attach/persist tests。

## 關鍵行為

- Contract-bound quantile gate 發生在 `train_quantile_trio(...)` import/call 前；測試用 call counter 驗證 failure cases `train == 0`。
- Dry-run synthetic manifest 僅在 `contract_bound_run=True`、`dry_run=True`、explicit `candidate_id`、concrete `symbol`、`side` 時生成；dataset role 是 `synthetic_training_dry_run`，sidecar filename deterministic。
- Acceptance report 會附上 canonical `pit_dataset_manifest` 和 `training_pit_manifest_binding_v1`，binding 內 runtime/DB/exchange/order/live/Cost Gate/deploy/secret authority flags 全為 false。
- Non-contract-bound quantile dry-run 保留既有訓練/export/registry flow，report 顯式標 `validation_reason=not_contract_bound`。

## 驗證

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

Result: `41 passed, 1 skipped in 0.33s`.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q \
  program_code/ml_training/tests/test_model_registry.py \
  program_code/ml_training/tests/test_registry_serving_contract.py \
  -p no:cacheprovider
```

Result: `49 passed in 0.40s`.

```bash
git diff --check -- \
  program_code/ml_training/run_training_pipeline.py \
  program_code/ml_training/quantile_reports.py \
  program_code/ml_training/tests/test_run_training_pipeline.py \
  program_code/ml_training/tests/test_quantile_reports.py
```

Result: passed.

## 治理對照

- No runtime mutation.
- No DB read/write or migration.
- No exchange/private read.
- No credential/secret access.
- No order/probe.
- No Cost Gate change.
- No deploy/restart.
- No live/mainnet behavior.
- No bounded Demo outcome ingestion.

## 不確定與偏差

- `program_code/ml_training/run_training_pipeline.py` 現為 991 行，超過 800 行 review-attention 門檻。PA design 明確要求 helper 放在 `run_training_pipeline.py` 且本 worker 不擴 scope 新增模組；我保留單檔實作，交 E2 重點審查。若 E2 要求拆分，建議另派小 scope 將 PIT gate helper 移入 ML training 內部 helper module。
- Contract-bound gate failure 不產生 acceptance report；此符合 fail-before-training/report/export/registry 的設計。成功 contract-bound run 才會持久化 PIT binding report。

## 下一步

返工後交 `E2(explorer)` 複審；PM 再決定是否進 E4/QA。不要把本報告解讀為 E2 PASS。

E1 IMPLEMENTATION DONE: 待 E2 審查。

## 2026-07-07 E2 RETURN 返工 addendum

修復 E2 findings：

- MEDIUM-1：`_write_pit_manifest_sidecar(...)` 改為同目錄 temp bytes 寫入，完整成功後才 `Path.replace()` final sidecar；`generate_acceptance_report(...)` 的 JSON persistence 改同目錄 temp JSON 寫入，完整成功後才 `Path.replace()` final report。`persist_required=True` 仍 fail-loud；default persistence 仍 fail-soft。
- MEDIUM-1 tests：新增 sidecar replace failure 保護既有 final artifact 測試；新增 required report `json.dump` failure 保護既有 final artifact 測試；新增 optional report persistence failure fail-soft 且保護既有 final artifact 測試。
- LOW-1：新增 pooled symbol `None` / `"ALL"` 永久測試，斷言 `pit_manifest_pooled_symbol_not_allowed` 且 `train == 0`。

返工驗證：

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

Result: `46 passed, 1 skipped in 0.30s`.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q \
  program_code/ml_training/tests/test_model_registry.py \
  program_code/ml_training/tests/test_registry_serving_contract.py \
  -p no:cacheprovider
```

Result: `49 passed in 0.32s`.

```bash
git diff --check -- \
  program_code/ml_training/run_training_pipeline.py \
  program_code/ml_training/quantile_reports.py \
  program_code/ml_training/tests/test_run_training_pipeline.py \
  program_code/ml_training/tests/test_quantile_reports.py \
  docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-07--wp2_1_training_run_pit_manifest_gate_implementation.md \
  docs/CCAgentWorkSpace/E1/memory.md
```

Result: passed.
