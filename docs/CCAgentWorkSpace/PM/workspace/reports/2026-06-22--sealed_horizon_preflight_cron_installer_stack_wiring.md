# 2026-06-22 — Sealed Horizon Preflight Cron Installer Stack Wiring

## 結論

v405 補上一個實際會阻斷 demo 自主學習鏈的安裝缺口：v403/v404 已經要求 bounded result review / execution-realism review 依賴 fresh sealed preflight，但 full stack installer 之前沒有安裝 sealed preflight refresher。這會讓 operator 以為 demo-learning stack 已完整安裝，實際上 bounded review chain 仍可能缺輸入。

本輪把 sealed horizon preflight refresher 變成 stack 的一等子 cron，但仍是 dry-run/operator-gated；沒有安裝 runtime cron、沒有降低 Cost Gate、沒有授權 probe/order。

## Source 變更

- 新增 `helper_scripts/cron/install_sealed_horizon_probe_preflight_cron.sh`
  - Linux-only。
  - 預設 dry-run；`OPENCLAW_SEALED_HORIZON_PREFLIGHT_CRON_APPLY=1` 才 install/remove。
  - apply 時預設要求 expected head，可由 `OPENCLAW_SEALED_HORIZON_PREFLIGHT_EXPECTED_HEAD`、`OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD`、或 `OPENCLAW_EXPECTED_SOURCE_HEAD` 提供。
  - proposed schedule：`22 * * * *`。
  - 只安裝 `sealed_horizon_probe_preflight_cron.sh`，不寫 PG、不連 Bybit、不給 probe/order authority。
- 更新 `helper_scripts/cron/install_demo_learning_stack_crons.sh`
  - stack preview/install/remove 現在覆蓋四條 cron：demo evidence heartbeat、sealed horizon preflight、Cost Gate learning lane、stack healthcheck。
  - apply 前的 preinstall refresh 先跑 artifact-only sealed horizon preflight，再跑 Cost Gate learning preinstall refresh / activation preflight。
  - stack script 本身仍不直接寫 crontab，只委派各 child installer。
- 更新 cron static tests，鎖住 dry-run gate、rollback、expected-head pass-through、full-stack child wiring、以及 no trading/runtime mutation tokens。
- 同步 runtime 既有 dirty `vol-event-robust-ruling.md` 自動報告更新：事件數 `13 -> 14`，結論仍是 `NO_EDGE_SURVIVES`。這是為了保留 runtime 產生的 evidence 並讓三端 source 可清乾淨。

## 驗證

- Mac `bash -n` passed：
  - `install_sealed_horizon_probe_preflight_cron.sh`
  - `install_demo_learning_stack_crons.sh`
  - `sealed_horizon_probe_preflight_cron.sh`
- Mac py_compile passed for touched cron static tests。
- Mac focused pytest：`17 passed`。
- Mac source/test diff check passed before source commit。
- Source commit：`ad8f5ba4 Wire sealed preflight into learning stack installer [skip ci]`。
- GitHub `origin/main` 已推送到 `ad8f5ba4`。
- Linux `trade-core:/home/ncyu/BybitOpenClaw/srv` fast-forwarded to `ad8f5ba4`。
- Linux `bash -n` passed for the same cron scripts。
- Linux py_compile passed for touched cron static tests。
- Linux focused pytest：`17 passed`。
- Linux direct sealed installer dry-run produced proposed `22 * * * *` entry and exited with `DRY-RUN: not modifying crontab.`。
- Linux full stack installer dry-run, with preflight/preinstall refresh disabled, previewed all four child cron entries and exited with `DRY-RUN: not modifying crontab.`。

## 邊界

本 checkpoint 是 source/test/docs + Linux source sync/read-only/static tests + dry-run installer previews only。未執行 CI。沒有 PG write/schema migration、沒有 Bybit private/signed/trading call、沒有 deploy/rebuild/restart、沒有 crontab install、沒有 env/auth/risk/order/strategy/runtime mutation、沒有 Cost Gate lowering、沒有 probe/order authority、沒有 promotion proof。

## 對盈利路徑的含義

這一步不是直接產生 alpha，但它讓「翻越 Cost Gate 的學習證據鏈」不再靠手動補 artifact：

1. demo rejects / order-flow evidence refresh；
2. sealed horizon preflight refresh；
3. Cost Gate learning lane 生成 blocked outcome review、bounded result review、execution-realism review；
4. stack healthcheck 把缺失的 bounded review chain 變成 blocker；
5. alpha/worklist 根據實際 artifact 狀態決定下一步是收集、停止、修復 execution realism，還是進 operator review。

這支持長期目標：通過 demo 自主學習、matched-control、edge-capture、execution-realism repair 逐步找到可盈利的 side-cell/horizon/entry path，而不是用全局 Cost Gate lowering 換更多低質下單。
