# Operator Brief - Gate-B Autonomous Watch

Date: 2026-06-12
Code checkpoint: `3675f651`

## Done

Gate-B 專用 watcher 已部署到 Linux runtime，cron 已安裝：

```bash
12,42 * * * * .../helper_scripts/cron/gate_b_watch_cron.sh
```

它每 30 分鐘檢查 Bybit `new_crypto` 公告和 live `PreLaunch` instruments，
輸出 `/tmp/openclaw/gate_b_watch/gate_b_watch_latest.json`。

## Current Status

最新正式 run：

- `status=WATCH_ONLY`
- total candidates: `23`
- alertable: `0`
- start/schedule: `0`
- alerts sent: `0`

唯一需要盯的是老 `BPUSDT`：

- `WATCH_CONVERSION`
- `launch_time_utc=2026-03-16T05:45:14Z`
- `cur_auction_phase=ContinuousTrading`

目前沒有可立即啟動 Gate-B 的新窗口。

## Alert Meaning

收到 `[GATE-B-WATCH]` 才代表新窗口值得處理：

- `START_GATE_B_NOW`: 立即準備 isolated 24h probe。
- `SCHEDULE_GATE_B_WINDOW`: 有未來窗口，按告警內 suggested time 安排 probe。
- `WATCH_CONVERSION`: 只盯 conversion，不啟動 probe。

Watcher 不會自動啟動 probe，不會交易，不會寫 DB。

## Manual Check

```bash
python3 -m json.tool /tmp/openclaw/gate_b_watch/gate_b_watch_latest.json | sed -n '1,120p'
tail -n 80 /tmp/openclaw/logs/gate_b_watch_cron.log
crontab -l | grep gate_b_watch
```

收到 start/schedule 告警後，才手動跑：

```bash
cd /home/ncyu/BybitOpenClaw/srv
python3 helper_scripts/research/aeg_gate_b_probe.py --duration-seconds 86400 --run-id gate_b_<symbol>_<yyyymmdd>
```
