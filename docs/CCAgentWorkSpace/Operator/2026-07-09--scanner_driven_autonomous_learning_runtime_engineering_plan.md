# Scanner-Driven Autonomous Learning Runtime 工程安排摘要

Date: 2026-07-09
PM status: `DONE_WITH_CONCERNS`

## 結論

方向成立，但必須收窄：

> 先把 Autonomous Learning Runtime 做成 scanner-driven、single-shot、source/artifact-only 的 active-learning pipeline，而不是 scheduler、daemon、runtime sidecar、IPC writer、PG writer 或 Bybit-facing flow。

scanner 只提供 evidence/intake；arbiter 選 learning target；proof bridge 只吃 candidate-matched after-cost outcomes；RetentionGuardian 先 dry-run。

## 派發鏈

已派發並收束：

- `CC(default)`：方向合規，但要補 AMD/ADR，避免 scanner authority / ADR-0035 online update 混淆。
- `FA(default)`：目前缺真正 ALR runtime，只有合約與 artifact spine。
- `QC(default)`：目標函數必須是 after-cost candidate-level net PnL + information value。
- `MIT(default)`：cleanup 必須引用圖 + quarantine + tombstone，不能直接刪 proof/dispute/audit。
- `AI-E(default)`：P0 用傳統 ML/統計；LLM 只解釋/聚類/草擬實驗。
- `E5(explorer)`：落點是 `learning_target_arbiter.py`、scanner intake、RetentionGuardian dry-run。
- `E3(explorer)`：P0 只能 single-shot artifact CLI；常駐化後置。
- `BB(default)`：P0 不得任何 Bybit public/private/order/WS 行為。
- `PA(default)`：已收束成 P0/P1/P2 工程包。

## 工程包

P0:

- `LearningTargetIntake + learning_target_arbiter.py`
- candidate-matched outcome ingestion bridge
- `RetentionGuardian --dry-run`

P0 禁止：

- no cron / daemon / sidecar
- no IPC
- no PG write/delete/DDL
- no Bybit REST/WS/private/order
- no Decision Lease acquire
- no `ScannerRunner` cadence/subscription change
- no `_latest` overwrite
- no runtime mutation

P1:

- 顯式前台 ALR local runner
- persistence design packet, no apply
- traditional ML/stat selector

P2:

- runtime sidecar / ADPE / Rust integration
- bounded Demo outcome production
- RL / ADR-0035 online update

## Loop

P0 入口只允許顯式 single-shot CLI：

```bash
python -m program_code.ml_training.learning_target_arbiter \
  --inputs <artifact-dir> \
  --out <run-dir>
```

狀態：

```text
LOAD_INPUTS -> BUILD_TARGETS -> SCORE_INFORMATION_VALUE
-> CHECK_PROOF_BOUNDARY -> RETENTION_DRY_RUN -> EMIT_ARTIFACT -> EXIT
```

自動退出：

- `DEFER_EVIDENCE`
- `BLOCKED_BOUNDARY`
- `STOP_NO_EDGE`
- `STOP_RETENTION_RISK`
- `ROTATED`

P0 不設 hidden scheduler；下一輪必須顯式再調用。

## PM 存檔

完整 PM 報告：

`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-09--scanner_driven_autonomous_learning_runtime_engineering_plan.md`

本輪沒有改代碼、沒有 runtime/Bybit/PG/Decision Lease/order 動作。
