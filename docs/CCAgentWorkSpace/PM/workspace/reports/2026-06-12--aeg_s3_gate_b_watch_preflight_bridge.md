# AEG-S3 Gate-B Watch → Preflight Bridge

日期：2026-06-12
角色：PM
Commit：`2b880f5d [skip ci] Bridge Gate-B watch into preflight`

## 結論

AEG-S3 Gate-B preflight 已接入 local `gate_b_watch_latest.json`。preflight summary schema 升至 v0.2，新增 `gate_watch` block，能把 watcher 的 `WATCH_ONLY` / `ACTIONABLE_START_NOW` / `ACTIONABLE_SCHEDULE` / stale / malformed 狀態轉成 operator-facing action。

這是 artifact-only bridge：不拉 Bybit、不啟 probe、不寫 DB、不碰 runtime/auth/risk/trading。

## 實作

- `helper_scripts/research/aeg_s3_gate_b_preflight/builder.py`
  - 新增 default path：`/tmp/openclaw/gate_b_watch/gate_b_watch_latest.json`
  - 新增 `gate_watch` summary block：
    - `artifact_status`
    - `candidate_counts`
    - `source_health`
    - `operator_action`
    - `probe_command_hints`
    - stale/malformed/source failure fail-closed
  - `WATCH_ONLY` → `WAIT_FOR_ACTIONABLE_WATCH`
  - `ACTIONABLE_START_NOW` → `START_ISOLATED_24H_PROBE`
  - `ACTIONABLE_SCHEDULE` → `SCHEDULE_ISOLATED_24H_PROBE`
- `helper_scripts/research/aeg_s3_gate_b_preflight/harness.py`
  - 新增 `--gate-watch-latest-json`
  - 新增 `--gate-watch-max-age-hours`
  - CLI output 顯示 `gate_watch`
- `helper_scripts/research/tests/test_aeg_s3_gate_b_preflight.py`
  - synthetic watcher fixtures
  - 覆蓋 `WATCH_ONLY`、start-now、schedule、stale、malformed

## 驗證

Mac：

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest ... -q
# 62 passed
python3 -m compileall -q helper_scripts/research/aeg_s3_gate_b_preflight helper_scripts/research/aeg_s3_gate_b_chain helper_scripts/research/aeg_s3_listing_fade
rg -n "control_api_v1|psycopg2|asyncpg|INSERT INTO|UPDATE |DELETE FROM|OPENCLAW_ALLOW_MAINNET|execution_authority|wss://stream.bybit.com|urlopen" ...
# no hits
```

Linux：

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest ... -q
# 62 passed
python3 -m compileall -q helper_scripts/research/aeg_s3_gate_b_preflight helper_scripts/research/aeg_s3_gate_b_chain helper_scripts/research/aeg_s3_listing_fade
grep -R -n -E "control_api_v1|psycopg2|asyncpg|INSERT INTO|UPDATE |DELETE FROM|OPENCLAW_ALLOW_MAINNET|execution_authority|wss://stream.bybit.com|urlopen" ...
# no hits
```

Linux true smoke：

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m aeg_s3_gate_b_preflight.harness \
  --run-id aeg_s3_gate_b_preflight_watch_bridge_smoke_allow_slow_20260612 \
  --artifact-root /tmp/openclaw/alpha_history_runs \
  --gate-watch-latest-json /tmp/openclaw/gate_b_watch/gate_b_watch_latest.json \
  --gate-watch-max-age-hours 12 \
  --allow-slow-capture
```

結果：

- artifact：`/tmp/openclaw/alpha_history_runs/aeg_s3_gate_b_preflight_watch_bridge_smoke_allow_slow_20260612`
- `gate_watch.artifact_status=WATCH_ONLY`
- `gate_watch.operator_action=WAIT_FOR_ACTIONABLE_WATCH`
- candidate_counts：total=23、alertable=0、start_now=0、schedule=0、watch_only=1
- source_health：announcements ok count=150；prelaunch ok count=1
- listing sample_count=2
- `pbo_status=produced_candidate_grid`
- readiness=`READY_BUT_SAMPLE_BELOW_GATE`
- recommended command generated

## 下一步

Gate-B 不再靠人工讀 latest JSON 判斷。標準流程：

1. 等 `[GATE-B-WATCH]` alert 或 latest artifact 變 `ACTIONABLE_*`。
2. 先跑 preflight 並讀 `gate_watch.operator_action`。
3. 只有 `START_ISOLATED_24H_PROBE` / `SCHEDULE_ISOLATED_24H_PROBE` 才按 `probe_command_hints` 手動啟動 isolated 24h probe。
4. probe 完後再跑 preflight；若 sample_count >=30，再跑 generated full-chain command。
5. 未經 E2/MIT/QC review，不得當 promotion proof。

