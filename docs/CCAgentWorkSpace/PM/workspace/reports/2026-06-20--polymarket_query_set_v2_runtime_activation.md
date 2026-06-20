# Polymarket Query-Set V2 Runtime Activation

2026-06-20 · PM · source + runtime checkpoint

## 結論

Polymarket 採集軸已新增 `query-set v2`，並在 Linux `trade-core` 持久啟用於 daily + hourly cron。

這不是 alpha promotion，也不是 collector-side filter。v2 只改 discovery 面：保留 `/events tag=crypto` top-N 主路，同時在 hourly v2 追加事件/監管/宏觀 keyword supplement；raw artifact 仍零過濾零截斷，價格目標市場會繼續入列，之後 lead-lag IC 必須在研究端用 `question/event_tags/discovery_queries` 分桶。

## Source 變更

- `helper_scripts/research/polymarket_axis/__init__.py`
  - 保留 v1 不動，新增 `QUERY_SET_V2_TAG` / `QUERY_SET_V2_KEYWORDS`。
- `collector.py`
  - `flatten_market_row` / `flatten_event_rows` / `collect_snapshot_sweep` 支援 `query_set_version` 參數。
  - `hourly-topn` v1 行為不變；v2 會在 top-N tag 抓取後追加 keyword supplement。
- `artifact.py`
  - manifest `query_set_version` 改為參數透傳。
- `cli.py`
  - 新增 `--query-set v1|v2`，默認 v1。
- `polymarket_axis_cron.sh`
  - 支援 `OPENCLAW_POLYMARKET_QUERY_SET=v1|v2` 透傳；非法值 fail-soft 記 log。
- `install_polymarket_axis_cron.sh`
  - 若 operator 設 `OPENCLAW_POLYMARKET_QUERY_SET`，installer 會驗證並寫入 crontab env prefix。

## Verification

Local:

```text
PYTHONPATH=helper_scripts/research python3 -m pytest -q --import-mode=importlib helper_scripts/research/tests/test_polymarket_axis.py helper_scripts/cron/tests/test_polymarket_axis_cron_static.py
65 passed, 1 skipped
```

Also passed locally:

- `python3 -m py_compile` on the four Polymarket package modules.
- `bash -n` on both Polymarket cron scripts.
- Targeted `git diff --check`.

Linux `trade-core` selective source sync:

- Same focused pytest result: `65 passed, 1 skipped`.
- Same py_compile and cron bash syntax checks passed.
- Full Linux git pull was intentionally not claimed; only target Polymarket files were rsynced because runtime checkout remains a selective-deploy workspace.

## Runtime Evidence

Manual v2 wrapper smoke:

```text
/tmp/openclaw/polymarket_axis_runs/hourly-topn-20260620T113312Z
created_at_utc = 2026-06-20T11:33:13.935023+00:00
mode = hourly-topn
lane = snapshot
point_in_time = true
query_set_version = v2
http_requests = 30
unique_events = 107
snapshot_rows = 860
keyword_terms = 24
errors = []
tracker_counts = resolved 18295 / tracking 2709 / lost 0 / unknown 0
```

Crontab backup before v2 reinstall:

```text
/tmp/openclaw/cron_backups/crontab_before_polymarket_query_set_v2_20260620T113342Z.txt
```

Active runtime crontab after reinstall:

```text
41 4 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw OPENCLAW_POLYMARKET_QUERY_SET=v2 /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/polymarket_axis_cron.sh daily >> /tmp/openclaw/logs/polymarket_axis_cron.cron.log 2>&1
7 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw OPENCLAW_POLYMARKET_QUERY_SET=v2 /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/polymarket_axis_cron.sh hourly-topn >> /tmp/openclaw/logs/polymarket_axis_cron.cron.log 2>&1
```

## Boundary

- Touched source/test/docs, selective Linux source sync, Linux user crontab, and `/tmp/openclaw` artifact/log/heartbeat only.
- No engine/API rebuild or restart.
- No PG write or schema migration.
- No Bybit private/signed/trading call.
- No credential/auth/risk/order/strategy mutation.
- No promotion proof.

## Next Trigger

Wait for enough hourly v2 points, then run leak-free Polymarket implied-probability delta vs Bybit BTC/ETH perp forward IC with:

- price-target vs event/reg bucket split,
- residualization against BTC/ETH spot/perp movement,
- regime slice,
- HAC/non-overlap controls,
- multiple-testing correction,
- QC/MIT/AI-E review before any strategy design.
