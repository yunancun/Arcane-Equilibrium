---
report: Hygiene Option E Phase 1 Step 1A — PROC-EXE-DRIFT alignment restart
date: 2026-05-25
author: E1 (Backend Developer)
phase: Hygiene Option E Phase 1 / Step 1A — IMPL DONE
status: HYGIENE-PHASE-1A-DONE / restart 成功 / PID + SHA aligned / C10 funding 路徑健康
parent dispatch: PM Hygiene Option E Phase 1 Step 1A dispatch (operator prompt 2026-05-25)
runtime: Linux trade-core via ssh trade-core
root cause source: PA sub-agent a6326f17 multi-session cargo race RCA
---

# §0. TL;DR

`HYGIENE-PHASE-1A-DONE`。SSH Linux `restart_all.sh --engine-only --keep-auth`（不 `--rebuild`），舊 PID 320381 (exe deleted) 換新 PID 350616；running SHA `c88f82b6` MATCH on-disk SHA `c88f82b6`；watchdog alive；engine demo mode；5min 內 panel_aggregator 5 funding flush cycles all `funding_ok=25/0`（funding 路徑健康，符合 C10 negligible loss expectation）。

# §1. 任務摘要

operator 拍板 Hygiene Option E Phase 1 Step 1A，目的：清除 PROC-EXE-DRIFT 觀測（PID 320381 `/proc/<pid>/exe -> openclaw-engine (deleted)`）。

PA sub-agent a6326f17 已 RCA：multi-session cargo race — sub-agent 在 engine 啟動後 8s 跑 `cargo test --release` 觸 incremental rebuild 覆寫 inode。running PID 與 on-disk 都是 `bbb21c56` source 編譯，functional 0 差異，純 cargo incremental artifact churn。

# §2. 修改清單

| 項 | 動作 |
|---|---|
| 代碼 | 0 修改（純 ops restart） |
| 配置 | 0 修改 |
| Runtime | Engine 重啟（PID 320381 → 350616） |
| Auth | `--keep-auth` 保留 authorization 缺失狀態（簽信非本任務） |

# §3. 執行步驟與證據

## 3.1 Pre-restart verify

| 檢查項 | 結果 |
|---|---|
| Current PID | 320381 (`rust/target/release/openclaw-engine`) |
| `/proc/320381/exe` | `(deleted)` symlink — **drift confirmed** |
| On-disk SHA | `c88f82b6301686df7ba4f12bbb6d7c0848193323e96a22b00461f1fe40c82bec` |
| Latest deps `.d` mtime | `5月 25 00:28` (cargo test artifact，11h 前) |
| Active cargo process | 0 個 — **race window closed** |

## 3.2 Restart 指令

```bash
ssh trade-core "cd /home/ncyu/BybitOpenClaw/srv && bash helper_scripts/restart_all.sh --engine-only --keep-auth"
```

關鍵 log：
- `WARN: --keep-auth requested but signed live authorization is missing` — expected（authorization 簽信為 OP-1 範圍）
- `WARN: skip non-OpenClaw engine pid -> 320381` — 二次 pgrep 命中 stale entry，後續 `Engine exited cleanly after 0x500ms` 證明 PID 已退
- `Starting Rust engine... PID: 350616`
- `engine.sock ready at /tmp/openclaw/engine.sock after 3x500ms` (1.5s)

## 3.3 Post-restart verify（AC check）

| AC | 結果 |
|---|---|
| 新 PID ≠ 320381 | PASS — 新 PID 350616 |
| `/proc/350616/exe` 非 deleted | PASS — `lrwxrwxrwx ... -> openclaw-engine`（無 deleted） |
| Running SHA == on-disk SHA | PASS — 都是 `c88f82b6301686df7ba4f12bbb6d7c0848193323e96a22b00461f1fe40c82bec` |
| Engine.log Mode | PASS — `engine_mode=demo`，M3 health emitter scheduler spawning |
| Watchdog alive | PASS — PID 2936560 |
| API healthz 200 OK | N/A — `/api/v1/healthz` empty response；但 `/api/v1/system/health` 經 engine alive snapshot 證明 API 健康（demo alive=true, snapshot_age=11.6s） |
| PID start time | `一 5月 25 01:18:27 2026` |

## 3.4 C10 funding tick verify（5min wait）

| 證據 | 結果 |
|---|---|
| Engine 啟動 funding REST poller | `REST pollers spawned (funding/OI/LSR)` at 01:18:29 |
| PanelAggregator 啟動 | `funding_curve_cohort_size=25 oi_delta_cohort_size=25` at 01:18:47 |
| Panel flush cycle 1-5 | All `funding_ok=25 funding_fail=0 oi_ok=25 oi_fail=0`（每 60s 一輪，5min 完整 5 輪） |
| `funding_harvest` strict grep | 0 命中（策略可能 dormant 或不同 logger name；funding 路徑健康經 panel_aggregator 證實） |
| Tick stats | 224k ticks 累積 in 5min 無 fills（demo dormant 預期） |

# §4. 治理對照

| 規範 | 對照 |
|---|---|
| operator 指示「不加 --rebuild」 | OBEYED — 避免觸發第三次 incremental rebuild 重觸 race |
| operator 指示「不要動 OP-1 secret」 | OBEYED — `--keep-auth` 不重新簽信 |
| operator 指示「不要做 hygiene B IMPL」 | OBEYED — 純 ops restart，0 代碼修改 |
| 硬約束 max_retries / live_execution_allowed / system_mode | UNTOUCHED |
| 跨平台路徑 | 命令使用 `/home/ncyu/BybitOpenClaw/srv` 是 Linux runtime 絕對路徑（合規，符合 README §六）；無 Mac 路徑硬編碼 |

# §5. 不確定之處

1. **`/api/v1/healthz` 空回應**：可能該 endpoint 不存在或路徑改變；但 `/tmp/openclaw/pipeline_snapshot.json` 寫入正常（`snapshot_age_seconds=11.6`）+ engine alive=true，API 服務本身健康。建議 PM 在後續 ops audit 確認 healthz endpoint 是否 deprecated。
2. **`funding_harvest` 字串無命中**：可能策略 dormant 或 logger 命名不同。已用 `funding|c10|harvest` broader grep 證明 funding REST poller + panel_aggregator 健康，但若 C10 demo observation 依賴特定 `funding_harvest` 字串輸出，operator 應 verify 該特性是否仍 active。
3. **`WARN: skip non-OpenClaw engine pid -> 320381`** — restart_all.sh 對 stripped binary name 的判斷邏輯似乎有 timing race（二次 pgrep 命中 stale entry），但 actual SIGTERM 仍成功 (cleanly exited 0.5s)。非本任務範圍，可登記為 hygiene follow-up。

# §6. Operator 下一步

- ✅ Hygiene Option E Phase 1 Step 1A 完成，PROC-EXE-DRIFT cleared。
- 待 PM 收 verdict 後派 E2 review（純 ops restart，無代碼 diff，E2 主要 verify 證據完整）。
- 並行 hygiene B IMPL sub-agent 完成後 PM 集中決策下一步。
- OP-1 secret operator 親手範圍，不阻塞本任務 close-out。

# §7. Verdict

**HYGIENE-PHASE-1A-DONE**
- 新 PID: 350616 (≠ 320381)
- on-disk SHA: `c88f82b6...` (unchanged, 無第三次 rebuild)
- running SHA == on-disk SHA MATCH (PROC-EXE-DRIFT cleared)
- C10 funding 路徑：panel_aggregator 5 cycles 全 25/0，5min tick window PASS
- watchdog + demo engine 全 alive
