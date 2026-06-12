# AEG-S3 Gate-B Watch → Preflight Bridge

日期：2026-06-12
Commit：`2b880f5d`

## 結論

Gate-B preflight 現在會讀 `/tmp/openclaw/gate_b_watch/gate_b_watch_latest.json`，直接輸出 `gate_watch.operator_action`。

目前 Linux smoke 結果：

- `artifact_status=WATCH_ONLY`
- `operator_action=WAIT_FOR_ACTIONABLE_WATCH`
- 23 candidates
- 0 alertable / 0 start_now / 0 schedule
- 唯一 live watch 仍是老 `BPUSDT` ContinuousTrading
- 舊 Gate-B run sample_count=2，不足 promotion

## 操作口徑

不要乾等 Gate-B，也不要在 `WATCH_ONLY` 時啟動 probe。

下一次 fresh Bybit Pre-Market / PreLaunch / standard-conversion alert 出現後，先跑：

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m aeg_s3_gate_b_preflight.harness \
  --run-id <RUN_ID> \
  --gate-watch-latest-json /tmp/openclaw/gate_b_watch/gate_b_watch_latest.json \
  --artifact-root /tmp/openclaw/alpha_history_runs
```

如果 `gate_watch.operator_action` 是 `START_ISOLATED_24H_PROBE` 或 `SCHEDULE_ISOLATED_24H_PROBE`，再按 `probe_command_hints` 手動啟動 isolated 24h probe。

邊界：本 bridge 只讀 artifact，不自動啟 probe，不碰 DB/auth/risk/trading/runtime。

