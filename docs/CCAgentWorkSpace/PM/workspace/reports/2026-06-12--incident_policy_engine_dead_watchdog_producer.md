# P2 incident-policy external `engine_dead` watchdog producer

日期：2026-06-12
範圍：source-only；無 CI、無 deploy/rebuild/restart、無 DB/auth/order/risk/trading mutation。

## 結論

`engine_dead` planned producer 已 source-live。因 PA §2.6 已判定「引擎死時 engine 內 `outcome_tx` 不可用」，本輪只做 external watchdog notify-only：通知 operator，絕不餵 Rust C4 `AllFail`，也不新增 watchdog-side Defensive 自動化。

## 設計

- producer module：`helper_scripts/canary/engine_dead_incident.py`
- 接線點：
  - `engine_watchdog.on_engine_crash(...)`：engine-crash 分支完成 restart/skip decision 後呼叫 `maybe_emit_notify_only(...)`
  - `engine_watchdog.on_engine_recovery(...)`：re-arm restart state 後呼叫 `emit_resolved_if_active(...)`
- 觸發條件：
  - snapshot/heartbeat stale `>=30s`
  - `watchdog_state.json.consecutive_failures >= 1`（respawn failed 至少一次）
  - `circuit_broken` 尚未先發出更強 engine-down alert
  - `network_outage` 分支不會落入此 producer
- 輸出：
  - `canary_events.jsonl`: `ENGINE_DEAD_NOTIFY_ONLY`
  - 既有 engine-down alert path：Telegram/webhook/local `alerts/alerts.jsonl`
  - recovery: `ENGINE_DEAD_RESOLVED`
- 去重：
  - `watchdog_state.json.engine_dead_notify_active` per down episode
  - 復用既有 `last_engine_down_alert_key=engine_dead_notify_only`

## 硬邊界

- 不餵 `DispatchOutcome::AllFail`
- 不武裝 notification failsafe timer
- 不改 C4 owner handler / `PipelineCommand` / RiskGovernor
- 不寫 auth / DB / order / exchange / risk state
- 不改 restart policy，只在現有 watchdog state machine 後掛 notify-only producer

## 驗證

Mac focused:

```bash
python3 -m py_compile helper_scripts/canary/engine_dead_incident.py helper_scripts/canary/engine_watchdog.py helper_scripts/canary/test_canary.py
python3 -m pytest helper_scripts/canary/test_canary.py -k 'engine_dead or WatchdogAlertWiring' -q
python3 -m pytest helper_scripts/canary/test_watchdog_alert.py -q
python3 -m pytest helper_scripts/canary/test_canary.py -q
python3 -m pytest helper_scripts/canary/test_engine_watchdog.py -q
rustfmt --edition 2021 --check rust/openclaw_engine/src/main_boot_tasks.rs
git diff --check
```

結果：

- `py_compile`: PASS
- targeted watchdog wiring: `5 passed, 82 deselected`
- `test_watchdog_alert.py`: `41 passed`
- `test_canary.py`: `87 passed, 9 subtests passed`
- `test_engine_watchdog.py`: `40 passed`
- touched Rust file rustfmt check: PASS
- `git diff --check`: PASS

註：`cargo fmt --manifest-path rust/openclaw_engine/Cargo.toml --check` 會掃出大量 repo 既有 rustfmt drift，非本 slice 新增；本輪以 touched file narrow rustfmt 作驗證。

## 下一步

`P2-INCIDENT-POLICY-DISPATCH-TRIGGER` 的 planned producer source coverage 已完成：CORE/auth/Bybit/sm_halt/position_drift/engine_dead。下一步不是再接 producer，而是對新增 `sm_halt` + `position_drift` + external `engine_dead` slices 做 BB/E2 focused re-review，之後 E4/QA/full-chain。
