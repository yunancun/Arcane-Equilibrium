# Gate-B Autonomous Watch Implementation

Date: 2026-06-12
Owner: PM
Code checkpoint: `3675f651` (`[skip ci] Add Gate-B autonomous watch`)

## 結論

Gate-B 現在不再依賴人工刷公告或通用公告哨兵判讀。已新增專用
`gate_b_watch`，每 30 分鐘自動檢查：

- Bybit `new_crypto` 公告 page 1..3。
- Bybit live `instruments-info?category=linear&status=PreLaunch`。

它會把 Pre-Market / PreLaunch / convert-to-standard perpetual 轉成可審計候選，
輸出 latest artifact/history/state，並只在 fresh/future/actionable window 出現時發
`[GATE-B-WATCH]` 告警。它不會自動啟動 24h probe，也不碰 production
WS/scanner/strategy/DB/order/runtime。

## 接線

新增：

- `helper_scripts/canary/gate_b_watch.py`
- `helper_scripts/canary/test_gate_b_watch.py`
- `helper_scripts/cron/gate_b_watch_cron.sh`
- `helper_scripts/cron/install_gate_b_watch_cron.sh`

Runtime artifacts：

- State: `/tmp/openclaw/gate_b_watch_state.json`
- Latest: `/tmp/openclaw/gate_b_watch/gate_b_watch_latest.json`
- History: `/tmp/openclaw/gate_b_watch/gate_b_watch_history.jsonl`
- Heartbeat: `/tmp/openclaw/cron_heartbeat/gate_b_watch.last_fire`
- Log: `/tmp/openclaw/logs/gate_b_watch_cron.log`

Installed cron on Linux:

```bash
12,42 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/gate_b_watch_cron.sh >> /tmp/openclaw/logs/gate_b_watch_cron.cron.log 2>&1
```

## 判定語義

`START_GATE_B_NOW`：
fresh announcement 已在 event 前置窗口內、PreLaunch auction phase active，或 live
PreLaunch 是 fresh/near launch。

`SCHEDULE_GATE_B_WINDOW`：
公告或 PreLaunch launchTime 指向未來窗口，但尚未進入前置窗口。

`WATCH_CONVERSION`：
舊 PreLaunch ContinuousTrading，例如當前 `BPUSDT`。這會保留 artifact，不發告警。

`STALE_NO_ACTION`：
歷史 Pre-Market / conversion 公告；保留 lineage，不污染 current status，不發告警。

## Linux 現狀

2026-06-12 09:43 UTC 正式 `/tmp/openclaw` 一輪：

- `status=WATCH_ONLY`
- `candidate_counts.total=23`
- `alertable=0`
- `start_now=0`
- `schedule=0`
- `watch_only=1`
- `alerts_sent=0`

當前唯一 live watch 是老 `BPUSDT`：

- `prelaunch_active`
- `WATCH_CONVERSION`
- `launch_time_utc=2026-03-16T05:45:14Z`
- `cur_auction_phase=ContinuousTrading`

沒有 fresh/future Gate-B start window。

## 驗證

Mac：

```bash
PYTHONPATH=helper_scripts/canary python3 -m pytest \
  helper_scripts/canary/test_gate_b_watch.py \
  helper_scripts/canary/test_bybit_announcement_sentinel.py -q
```

Result: `66 passed in 0.13s`.

Linux：

```bash
PYTHONPATH=helper_scripts/canary python3 -m pytest \
  helper_scripts/canary/test_gate_b_watch.py \
  helper_scripts/canary/test_bybit_announcement_sentinel.py -q
```

Result: `66 passed in 0.12s`.

Additional checks:

- `bash -n helper_scripts/cron/gate_b_watch_cron.sh helper_scripts/cron/install_gate_b_watch_cron.sh` OK.
- `python3 -m compileall -q helper_scripts/canary/gate_b_watch.py` OK.
- Runtime wrapper manual run rc=0, heartbeat/artifact/state written.
- Static forbidden-route search: no DB/order/mainnet/runtime route hits.

No CI, no deploy, no rebuild/restart, no DB migration, no trading mutation.

## 下一步

主線 Gate-B 等 `[GATE-B-WATCH]` 告警或 latest artifact 變成
`ACTIONABLE_START_NOW` / `ACTIONABLE_SCHEDULE`。觸發後由 operator 啟動 isolated：

```bash
python3 helper_scripts/research/aeg_gate_b_probe.py --duration-seconds 86400 --run-id gate_b_<symbol>_<yyyymmdd>
```

無 transition 仍是 `INCONCLUSIVE_NO_TRANSITION`，不可當 alpha evidence。
