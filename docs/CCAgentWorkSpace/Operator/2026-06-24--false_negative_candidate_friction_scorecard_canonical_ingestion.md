# False-Negative Candidate Friction Scorecard Canonical Ingestion

Date: 2026-06-24

## 結論

本輪沒有重跑 `P0-BOUNDED-PROBE-AUTHORIZATION`，也沒有把你的 broad Demo API authorization 當成 bounded probe/order authority。

這輪做的是 source-only canonical ingestion：把 v464 的 false-negative candidate friction scorecard 接進 recurring Cost Gate learning lane，讓它成為 cron latest artifact、learning-loop status、artifact spine、discovery loop、learning worklist 都能看見的診斷 evidence。

## 新增能力

`cost_gate_learning_lane_cron.sh` 現在會產生：

`cost_gate_learning_lane/false_negative_candidate_friction_scorecard_latest.{json,md}`

它使用同一輪已生成的：

- false-negative candidate packet
- bounded touchability preflight
- placement repair plan
- bounded operator authorization packet

因此它不是讀舊 latest 拼湊，而是同一輪 candidate/friction evidence 的 canonical view。

## 重要邊界

這個 artifact 只做排序和診斷，不會：

- 授權 bounded probe/order；
- 產生 authorization object；
- 降低 global Cost Gate；
- 開 live/mainnet；
- 呼叫 Bybit；
- 寫 PG；
- 改 crontab；
- restart service；
- 改 runtime env/risk/order/strategy；
- 啟用 Rust writer；
- 當 promotion proof。

`TYPED_CONFIRM_REQUIRED` 仍然是 blocker，不會被 scorecard 或 broad Demo API authorization 繞過。

## 審查修正

E2 抓到一個必修問題：如果 current run 跳過/禁用 friction scorecard，status summary 可能 fallback 讀舊 latest artifact，讓舊的 authority/proof flag 重新出現。

已修：

- 有 current status row 時，status row 永遠優先，即使欄位是 `None`；
- 只有完全沒有 current status row 時才 fallback artifact；
- 補了 stale latest authority/proof leak regression；
- 補了 scorecard rc failure -> loop `ERROR` regression。

E2/E4 最終都 PASS。

## 驗證

- cron static：`15 passed`
- alpha throughput：`83 passed`
- Cost Gate policy：`90 passed`
- friction scorecard + learning worklist focused：`19 passed`
- bash syntax：passed
- py_compile：passed
- git diff check：passed

## 操作狀態

Implementation commit: `909f3c86d407dfde4cbe9c6c4d030668df3e7bcb`

本 checkpoint 沒有 Linux runtime sync，沒有 runtime artifact refresh，沒有 Demo/API/order action。

下一個安全 source-only blocker：`P1-MM-CURRENT-FEE-REPEAT-WINDOW`。如果要真的進 bounded Demo probe，仍需要 candidate-specific exact typed-confirm artifact，而不是口頭 broad authorization。
