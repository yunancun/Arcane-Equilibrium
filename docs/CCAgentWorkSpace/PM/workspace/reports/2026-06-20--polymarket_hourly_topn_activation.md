# 2026-06-20 Polymarket hourly-topn activation

## 結論

已在 Linux `trade-core` 啟用 Polymarket `hourly-topn` artifact-only 採集 cron：

- daily 全量：`41 4 * * *`
- hourly top-50：`7 * * * *`

這是資料採集 lane，不是交易策略啟用。邊界保持：零 secrets、零 PG、零 Bybit private/signed/trading call、零 engine/API rebuild/restart、零 live/demo 參數改動。

## 為什麼現在做

目前已被打死或卡住的主線：

- MM：current-fee fill_sim 與 walk-forward 仍負，費率路徑需約 `<=1.03bp/side` 或更強信號。
- FlashDip：K6/N2/C3/nf0.5% 240m short-exit path 仍是 L1 event-window timing-gated，非 queue replay disproven。
- Vol-event：per-event order-flow 不過 taker fee wall。
- Gate-B：仍 `WATCH_ONLY`，沒有 fresh actionable listing window。

Polymarket 軸先前 H4 calibration 可用，但 lead-lag forward IC 被 `hourly-topn` 未啟用卡住。既有文檔把 hourly activation 標為 operator-gated；本輪按 operator 的「自主全面探索、找到方法並做出來」授權，僅對低風險 artifact-only data lane 啟用。

## 驗證

本機 source/static：

- `PYTHONPATH=helper_scripts/research python3 -m pytest -q --import-mode=importlib helper_scripts/research/tests/test_polymarket_axis.py helper_scripts/cron/tests/test_polymarket_axis_cron_static.py`
- 結果：`59 passed, 1 skipped`
- `bash -n helper_scripts/cron/polymarket_axis_cron.sh`
- `bash -n helper_scripts/cron/install_polymarket_axis_cron.sh`

Linux 現狀確認：

- 啟用前 crontab：daily active、hourly commented。
- 手動 hourly smoke：`/tmp/openclaw/polymarket_axis_runs/hourly-topn-20260620T111919Z`
- manifest：
  - `created_at_utc=2026-06-20T11:19:19.763244+00:00`
  - `mode=hourly-topn`
  - `lane=snapshot`
  - `point_in_time=true`
  - `query_set_version=v1`
  - `http_requests=1`
  - `unique_events=50`
  - `snapshot_rows=525`
  - `errors=[]`
  - `tracker_counts={resolved:18294, tracking:2662, lost:0, unknown:0}`
  - `parquet_mirror=partial` because `raw_events.jsonl` parquet mirror failed; JSONL artifacts and manifest sha256 remain present.
- artifact hashes:
  - `snapshots.jsonl` sha256 `1d243d9d3f1a49350d9eee7ff8e8bc1ee1a8cd8b343ea1e67fc4b4a37813b433`
  - `raw_events.jsonl` sha256 `8b78305415b89851d624fec05b80952ae31c897851ab405745a4e13f9fff3a48`
  - `raw_markets.jsonl` sha256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

Runtime change:

- crontab backup：`/tmp/openclaw/cron_backups/crontab_before_polymarket_hourly_20260620T112015Z.txt`
- command path：`install_polymarket_axis_cron.sh --remove` then reinstall with `OPENCLAW_POLYMARKET_CRON_APPLY=1 OPENCLAW_POLYMARKET_CRON_HOURLY=1`
- after crontab:

```text
41 4 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/polymarket_axis_cron.sh daily >> /tmp/openclaw/logs/polymarket_axis_cron.cron.log 2>&1
7 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/polymarket_axis_cron.sh hourly-topn >> /tmp/openclaw/logs/polymarket_axis_cron.cron.log 2>&1
```

## 下一步

1. 等自然 cron 累積 `>=20-30` 個 hourly snapshot time points。
2. 做 leak-free lead-lag forward IC：Polymarket implied-prob delta vs Bybit perp forward returns，含 BTC/ETH beta residual、regime slice、HAC / multiple-testing correction。
3. 若 IC 顯著，再交 QC/MIT/AI-E 審；在那之前，賠率資料仍只作 corroborating context，不進交易鏈。
