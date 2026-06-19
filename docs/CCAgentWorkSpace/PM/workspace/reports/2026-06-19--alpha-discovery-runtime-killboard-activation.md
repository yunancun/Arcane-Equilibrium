# Alpha Discovery Runtime Killboard Activation

VERDICT: PASS_WITH_LIMITS
CONFIDENCE: high

日期：2026-06-19
角色鏈：PM local → E1/E2/E4/QA local viewpoints → PM sign-off

## 結論

1-6 alpha discovery throughput 已從 source/test scaffold 接成 artifact-only runtime killboard。新 runner 會讀既有 runtime artifacts，生成多臂 action plan，並可由 Linux cron 每 15 分鐘更新。

這表示 bot 可以被確認為「正在按設計快速尋找 edge/alpha 候選」的 discovery-orchestration 層；但目前沒有產生可晉升 alpha。Gate-B 仍可能 WAIT，vol-event 可能 NO_EDGE_SURVIVES，FlashDip/MM/AEG matrix 仍需各自樣本與 gate。

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

## 待 Linux 驗收

1. Mac commit/push 後 Linux fast-forward。
2. 手動跑一次 cron wrapper，確認 latest JSON。
3. 安裝 crontab `*/15 * * * * ... alpha_discovery_throughput_cron.sh`。
4. 確認 heartbeat、latest artifact、action counts。
