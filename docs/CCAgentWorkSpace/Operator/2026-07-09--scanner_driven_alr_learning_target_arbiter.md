# Operator Summary: Scanner-Driven ALR Learning Target Arbiter

Date: 2026-07-09
Status: `ADVANCED`
Boundary: `SOURCE_ONLY_OFFLINE_P0_P1`

已完成 `P0-AIML-ALR-LEARNING-TARGET-ARBITER`。

新增：

- `program_code/ml_training/learning_target_arbiter.py`
- `program_code/ml_training/tests/test_learning_target_arbiter.py`

它現在提供：

- `learning_target_snapshot_manifest_v1`
- `learning_target_runtime_v1`
- explicit `--snapshot` / `--out` CLI
- hash-bound input manifest validation
- case-insensitive `_latest` path/source-ref rejection
- exact `False` latest flags
- source-tier normalization for `scanner` / `no_order` / `artifact_count`
  variants
- expected-value-of-information ranking
- proof/reward/edge/promotion and authority counters forced zero/false

Role chain:

- PA design: pass with source-only scope
- E1 implementation + reviewer rework
- E2 rereview after QA fixes: PASS
- E4 final regression: PASS, `75 passed`
- QA final gate: ACCEPT

Boundary unchanged：未觸碰 runtime、PG、IPC、Bybit、official MCP、Decision
Lease、order/probe、Cost Gate、`_latest`、serving、proof/promotion、delete/apply、
cron/daemon/scheduler、service/env、live/mainnet。

下一個 row 已變成：

`P0-AIML-ALR-OUTCOME-BRIDGE`

仍必須走：

`PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`
