# Alpha Discovery Runtime Killboard Activation

VERDICT: PASS_WITH_LIMITS
CONFIDENCE: high

日期：2026-06-19
角色鏈：PM local → E1/E2/E4/QA local viewpoints → PM sign-off

## 結論

1-6 alpha discovery throughput 已從 source/test scaffold 接成 artifact-only runtime killboard。新 runner 會讀既有 runtime artifacts，生成多臂 action plan，並已在 Linux `trade-core` 裝成每 15 分鐘更新的 cron。

這表示 bot 可以被確認為「正在按設計快速尋找 edge/alpha 候選」的 discovery-orchestration 層；但目前沒有產生可晉升 alpha。最新 killboard 顯示 `ready_for_probe=0` / `ready_for_aeg_chain=0`，Gate-B 仍 `WATCH_ONLY`，vol-event 已 `NO_EDGE_SURVIVES`，FlashDip/MM 仍在累積樣本。

## 改動

- 新增 `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`。
- 新增 `helper_scripts/cron/alpha_discovery_throughput_cron.sh`。
- 更新 `discovery_loop.py`：`NO_EDGE_SURVIVES` / `KILL` / `REJECTED` 進 BLOCK，reason 保留為 gate status，不誤標 source failure。
- 更新 focused tests、script index、工程計劃 addendum。

## Runtime Contract

Runner 只讀：
- Gate-B latest artifact
- FlashDip death-rate status log
- vol-event ledger
- MM verdict status log
- AEG robustness matrix summary

Runner 只寫：
- `<OPENCLAW_DATA_DIR>/alpha_discovery_throughput/alpha_discovery_latest.json`
- dated JSON
- history JSONL
- cron log / heartbeat

不連 DB、不連 Bybit、不啟 probe、不下單、不改 auth/risk/runtime state。

## 驗證

- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py` = 9 passed
- `bash -n helper_scripts/cron/alpha_discovery_throughput_cron.sh` = PASS
- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/runtime_runner.py` = PASS
- 空資料 smoke：runner 不標 `is_fast_discovery_active=true`

## Linux 驗收完成

- Source checkpoint `5f0bbecd` 已 fast-forward 到 `/home/ncyu/BybitOpenClaw/srv`。
- 2026-06-19 18:04 CEST 手動執行 `helper_scripts/cron/alpha_discovery_throughput_cron.sh` 成功；18:15 CEST natural cron 自行刷新 `/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json`，`created_at_utc=2026-06-19T16:15:01Z`。
- Latest killboard：`is_fast_discovery_active=true`，source_present=4，active_arm=4，source_ok=5，action_counts=`RUN_READ_ONLY_CAPTURE=2 / WAIT=2 / BLOCK=1`。
- Arm 狀態：FlashDip sample=0 `RUN_READ_ONLY_CAPTURE`；MM sample=3 `RUN_READ_ONLY_CAPTURE`；AEG matrix `WAIT`；Gate-B `WATCH_ONLY`；vol-event sample=4 `NO_EDGE_SURVIVES` -> `BLOCK`。
- Linux crontab 已追加：`*/15 * * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw $HOME/BybitOpenClaw/srv/helper_scripts/cron/alpha_discovery_throughput_cron.sh >> /tmp/openclaw/logs/alpha_discovery_throughput_cron.cronout.log 2>&1`。
- Watchdog read-only check：`engine_alive=true`，demo snapshot age 9.1s。

## 判定

系統現在已在 discovery-orchestration 層快速尋找 edge/alpha；當前沒有可啟 probe 或可進 AEG chain 的 alpha。本報告不構成 promotion proof，也不授權 probe/trade。
