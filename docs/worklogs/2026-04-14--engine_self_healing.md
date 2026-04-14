# Engineering Log — Engine Self-Healing + Zombie API Service（2026-04-14）

**Session**: 2026-04-14（PM）
**Scope**: 5 修復（Fix 1/2/3/4 引擎自癒 + zombie `openclaw-trading-api.service` 清理）
**Status**: 全部實施 + E4 baseline PASS（Rust lib 1144 + core 366 + e2e 33 = **1543** · 0 fail · watchdog 8/8 unit · shell `bash -n` clean）
**Deployment**: engine Fix 1/3/4 待 operator 執行 `bash helper_scripts/restart_all.sh --rebuild` · Fix 2 + zombie 修復已即時生效

---

## 0. 目的 / Purpose

這份是完整工程日誌，目的是 — **未來某個人（包括未來的我）在事故後打開這份文件可以獨立重建：發生了什麼、為什麼這樣修、具體改了什麼、如何驗證、如何回退**。不需要配合其他文件也讀得懂。

CLAUDE.md §三 / CLAUDE_CHANGELOG.md 是摘要視角；本日誌是**權威工程紀錄**。

---

## 1. 事故時間線 / Incident Timeline

```
2026-04-14 ~11:38 CEST    engine 最後一次活動（後推估：ws tick 停止於此時間附近）
2026-04-14 ~11:52 CEST    engine 靜默退出（無 panic log、無 shutdown 日誌、無 crash dump）
2026-04-14 ~12:10 CEST    operator 透過 GUI 發現 paper 沒交易 → 懷疑「engine 沒啟動？GUI 壞？」
2026-04-14 12:12 CEST     session 開啟，確認 engine 進程死亡、pipeline_snapshot.json 已 stale 18min
2026-04-14 12:15 CEST     operator 問：自動重啟存在嗎？為何靜默死亡？
2026-04-14 12:20 CEST     Phase 0 根因調查啟動
2026-04-14 12:40 CEST     Phase 0 完成 → 4 Fix 計劃定稿（含 PA/FA/CC 對抗性審查）
2026-04-14 14:00 CEST     operator 批 3 決策：D1 crash-only 含 Live / D2 ws stale 120s / D3 Phase 0 medium
2026-04-14 16:00~20:40    Fix 1/3/4/2 依序實施 + E4 baseline 回歸 + 文檔同步
2026-04-14 20:47 CEST     zombie `openclaw-trading-api.service` disable + stop
```

**死前關鍵事實**：
- engine 對 `ps` / healthcheck port 仍「存活」，但 ws tick 流在死前 14+ 分鐘已停 — **進程存活 ≠ 業務存活**
- engine.log 在下一次 `restart_all.sh` 時被 `>` truncate 清零 → 死因證據全滅
- operator 18 分鐘毫無察覺 → 敏感交易系統不可接受

---

## 2. Phase 0 根因調查 / Root Cause Investigation（medium 版 · ~30min）

### 2.1 排除路徑

| 假設 | 檢查方式 | 結論 |
|------|----------|------|
| OOM killer | `dmesg | grep -i 'killed process\|oom'` | 無 OOM 記錄 |
| SIGKILL 外部殺 | `journalctl --user -u openclaw-engine` + `grep -i signal` | 無 systemd 單元守護 engine，無外部信號紀錄 |
| `std::process::exit` 被誤觸 | `grep -r "std::process::exit\|process::exit" rust/openclaw_engine/` | 僅 signal handler 走此路徑且需 SIGTERM/SIGINT，無條件符合 |
| tokio runtime deadlock | 無 thread dump 無法 100% 排除 | 推斷：若 deadlock 則 ps 不會顯示退出 — 實際進程已 exit，故非 deadlock |
| panic 但被吞 | Rust 有 `catch_unwind` 機制可能吞 panic，且 tracing 預設不 flush 就退出 → panic 可能寫了但沒落盤 | **最可能根因** |

### 2.2 事故放大器發現

Phase 0 意外發現 `helper_scripts/restart_all.sh` 用 `>` redirect stdout/stderr 到 `engine.log` — 每次 restart 都 **truncate** 舊 log。

這意味著：
- 即使 engine 在死前有 panic hook / tracing 輸出，下次 restart 就抹掉證據
- 2026-04-14 事故 operator 發現時已無死因可查

**這是真正的系統性缺陷** — 沒修這個，任何其他 fix 都無法驗證自己是否有效。

### 2.3 現有自癒機制盤點

| 組件 | 預期行為 | 實際狀態 |
|------|---------|----------|
| `engine_watchdog.py` | 偵測 engine 死亡 | ✅ 偵測 ok，但**只記錄不重啟** |
| systemd 單元守護 engine | N/A | **不存在** — engine 只有 `restart_all.sh` 手啟 |
| `openclaw-gateway.service` | 守護 node gateway | ✅ 正常，與 engine 無關 |
| `openclaw-trading-api.service` | 守護 API | ⚠️ 存在但 port 8000 衝突致 restart 循環（見 §7） |

**結論**：engine 無自動重啟。一旦死亡必須 operator 手工干預。

---

## 3. 設計決策 / Design Decisions

### D1 — 崩潰語義：全部 crash-only（含 Live）

**選項對比**：

| | A. catch_unwind + isolate 繼續 | B. crash-only 立即死 |
|---|---|---|
| paper panic 後 | demo/live 繼續運行 | 全部 cancel + exit + watchdog 拉起 |
| 三引擎共享 config 污染 | 可能帶病繼續 | 重啟乾淨狀態 |
| 事故調查難度 | 高（錯誤日誌被後續正常日誌淹沒） | 低（死前證據清楚） |
| 停機時間 | 0s | ~30-90s |

**選 B**。對敏感交易系統「帶病繼續交易」比「停機 30s」風險高 1000 倍。isolate 的 0s 停機是假象 — 實際是用未來更大的事故換當下的小停機。

Live 是否例外？operator 批示「D1 同意」= Live 也走 crash-only。

### D2 — WS tick stale 閾值：120s

**選項對比**：

| | 60s | 120s |
|---|---|---|
| 誤報頻率（深夜薄流動 / WS hiccup / Bybit 維護）| 高 | 可接受 |
| 真陽性延遲 | 60s | 120s |
| Worst case zombie + restart 時間 | ~1.5min | ~3min |

**選 120s**。60s 實測會在正常的 WS 重連過程中誤觸（Bybit 維護窗口、CDN 故障轉移都可能造成 60-90s 靜默期）。120s + ~45s watchdog grace + ~15s restart ≈ 3min worst case — 對敏感交易仍可接受，且大幅降低誤報。

詳細場景見 `docs/known_issues/2026-04-14--ws_stale_detector.md`。

### D3 — Phase 0 投資：medium

限 30min 做：
- `dmesg` + `journalctl` 排 OOM/signal
- `grep` 排 `process::exit` 路徑
- 盤點現有自癒機制

不做：
- 完整 crash dump 分析（死屍已無）
- gdb 連 core file（沒 core file）
- 逐行 flamegraph（過度）

---

## 4. Fix 1 — Panic Hook / 診斷可見性

### 變更

**File**: `rust/openclaw_engine/src/main.rs` L55-108（`tracing_subscriber::fmt()...init()` 之後立即設定）

```rust
std::panic::set_hook(Box::new(|info| {
    let backtrace = std::backtrace::Backtrace::force_capture();
    let location = info.location()
        .map(|l| format!("{}:{}:{}", l.file(), l.line(), l.column()))
        .unwrap_or_else(|| "<unknown>".to_string());
    let payload = info.payload()
        .downcast_ref::<&str>().map(|s| s.to_string())
        .or_else(|| info.payload().downcast_ref::<String>().cloned())
        .unwrap_or_else(|| "<non-string panic payload>".to_string());
    tracing::error!(
        target: "openclaw_engine::panic",
        thread = ?std::thread::current().id(),
        thread_name = std::thread::current().name().unwrap_or("<unnamed>"),
        location = %location,
        payload = %payload,
        backtrace = %backtrace,
        "PANIC captured / panic 已捕獲",
    );
    use std::io::Write;
    let _ = std::io::stdout().flush();
    let _ = std::io::stderr().flush();
}));
```

### 覆蓋範圍

- 所有 tokio worker thread 的 panic（即使被後續 `catch_unwind` 吞也先記錄）
- 所有 std::thread::spawn 的 panic
- 所有 non-async code path 的 panic

### 為何這是「診斷工具非修復」

hook 不阻止 panic — 只保證 panic 一定留下結構化日誌。**沒 hook 就沒線索**，有 hook 至少下次事故能從 backtrace + location 倒推問題。這是所有其他 fix 能驗證自己是否有效的前提。

---

## 5. Fix 3 — Crash-Only Semantics

### 變更

**File**: `rust/openclaw_engine/src/main.rs`
- L57-119: `async fn run_pipeline_crash_only<F>()` helper
- L882: paper pipeline spawn 改包裝
- L940: demo pipeline spawn 改包裝
- Live thread 既有 `catch_unwind` 後補 `live_cancel.cancel()`

```rust
async fn run_pipeline_crash_only<F>(
    kind: PipelineKind, fut: F,
    health: Arc<std::sync::atomic::AtomicU8>,
    crash_tx: tokio::sync::broadcast::Sender<EngineEvent>,
    cancel: CancellationToken,
) where F: std::future::Future<Output = ()>
{
    use futures_util::FutureExt;
    let result = std::panic::AssertUnwindSafe(fut).catch_unwind().await;
    if let Err(panic_info) = result {
        // 結構化 log panic 位置 / payload
        tracing::error!(
            target: "openclaw_engine::pipeline_crash",
            kind = ?kind,
            payload = ?panic_info.downcast_ref::<&str>().copied(),
            "Pipeline panicked — crash-only path invoked / pipeline panic，走 crash-only",
        );
        health.store(PipelineHealth::Down as u8, Ordering::SeqCst);
        let _ = crash_tx.send(EngineEvent::Crashed(kind));
        cancel.cancel();  // 全局 cancel → 所有 pipeline ordered shutdown → exit
    }
}
```

### 流程

```
任一 pipeline panic
  → panic hook 記錄 backtrace / location / payload
  → catch_unwind 捕獲
  → tracing::error! pipeline_crash event
  → AtomicU8 health → Down
  → broadcast EngineEvent::Crashed(kind)
  → CancellationToken.cancel()
  → signal_loop 感知 cancel → 退出 while
  → 依序關閉 paper / demo / live / task pool
  → 寫最後 snapshot → exit
  → watchdog 45s 內偵測死亡 → restart
```

### 與 isolate 對比

**isolate 失敗劇本**：
1. paper pipeline panic（例如 `RiskConfigStore` race 寫入）→ log + 繼續
2. 三引擎共享的 `RiskConfigStore` 已半髒
3. Guardian/Reconciler 讀半髒 config 判決 → demo 下一個 tick 出錯但不 panic → **靜默錯單**
4. operator 看 GUI 數字怪才發現 → log 已被後續正常日誌埋
5. 事故調查不知 demo 的錯是 paper 污染

**crash-only 失敗劇本**：
1. panic → hook + backtrace → cancel 全局 → ordered shutdown → exit
2. watchdog 45s 偵測 → restart_all.sh --engine-only → 拉起
3. QoL-1 `PaperState::restore_from_db()` 從 DB 還原三引擎 counters
4. 乾淨 config + 乾淨 state 重新開始
5. engine-<epoch>.log 完整保留 panic + backtrace，下次開 session 一眼看到

**最糟停機 30-90s**。換來的是每次事故都有可查的死因 + 無污染傳染。

---

## 6. Fix 4 — WS Tick Stale 自救

### 變更

**File**: `rust/openclaw_engine/src/main.rs` L1108-1155（`signal_loop(&config, &cancel).await` 之前）

```rust
const TICK_STALE_THRESHOLD_MS: u64 = 120_000;
const TICK_WATCHDOG_INTERVAL_SECS: u64 = 30;

let last_tick_ms_ref = Arc::clone(&shared_last_tick_ms);
let cancel_ref = cancel.clone();
tokio::spawn(async move {
    let mut interval = tokio::time::interval(
        tokio::time::Duration::from_secs(TICK_WATCHDOG_INTERVAL_SECS)
    );
    loop {
        interval.tick().await;
        let last = last_tick_ms_ref.load(Ordering::Relaxed);
        if last == 0 {
            // warmup — 從未見過 tick，跳過（冷啟動 / 空掃描宇宙）
            continue;
        }
        let now_ms = /* SystemTime → ms */;
        if now_ms > last && now_ms - last > TICK_STALE_THRESHOLD_MS {
            tracing::error!(
                target: "openclaw_engine::ws_stale",
                last_tick_ms = last,
                age_ms = now_ms - last,
                threshold_ms = TICK_STALE_THRESHOLD_MS,
                "WS tick stale — triggering engine cancel (Fix 4) / WS tick 過期，觸發引擎取消",
            );
            cancel_ref.cancel();
            break;  // 退出 watchdog task，signal_loop 會接手
        }
    }
});
```

### 為何 120s 而非 60s

見 §3 D2 與 `docs/known_issues/2026-04-14--ws_stale_detector.md`：60s 會在 Bybit 正常維護窗口（60-90s）/ 薄流動 tier-3 深夜 tick 間隔 / CDN 故障轉移時誤觸。

### False-positive 防禦

- `last == 0` → 冷啟動 / scanner universe 空 → 不誤觸
- 30s polling → 最糟偵測延遲 ~150s（120s stale + 30s poll 間隔）
- `break` 後退出 task → 單次 stale 只觸發一次 cancel，不會重複觸發

### True-positive 場景（事故當日）

1. ws 連線斷但重連邏輯 stuck → `shared_last_tick_ms` 不更新
2. `event_consumer` 死循環或 deadlock → 進程活但 tick 不寫
3. tokio runtime worker panic 且 `catch_unwind` 吞 → pipeline 「看起來」還在但實際已殭屍

---

## 7. Fix 2 — Watchdog Auto-Restart + 4 道保險

### 7.1 變更檔案

| File | 變更 | 行數變化 |
|------|------|----------|
| `helper_scripts/canary/engine_watchdog.py` | +helper functions + flock + 整合 on_engine_crash | +180 行 |
| `helper_scripts/stop_all.sh` | 新增（maintenance flag + SIGTERM-first 優雅停）| 新增 ~90 行 |
| `helper_scripts/restart_all.sh` | +`rotate_engine_log()` + `graceful_stop_engine()` + flag 清除 + `--rebuild` 旗標 | +50 行 |

### 7.2 四道保險詳述

#### 保險 #1 — fcntl.flock 單例

```python
lock_path = Path(args.data_dir) / WATCHDOG_LOCK_FILE  # /tmp/openclaw/watchdog.lock
lock_fd = open(lock_path, "w")
try:
    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    logger.critical("Another watchdog already holds lock — exiting")
    sys.exit(3)
lock_fd.write(f"{os.getpid()}\n")
```

**為何需要**：operator 不小心 `bash engine_watchdog.py &` 兩次 → 兩 watchdog 都觸發重啟 → 雙殺 engine。flock 保證全系統最多一個 watchdog 持有寫鎖。

#### 保險 #2 — maintenance flag

```python
# on_engine_crash → should_restart() → 檢查 MAINTENANCE_FLAG
flag_path = Path(data_dir) / MAINTENANCE_FLAG  # /tmp/openclaw/engine_maintenance.flag
if flag_path.exists():
    return False, f"maintenance flag present at {flag_path}"
```

**operator 意圖守則**：
- `stop_all.sh` 執行時**先**建立 flag **再**殺 engine → watchdog 下次 poll 看到 flag 不重啟
- `restart_all.sh` 執行時清除 flag → operator 顯式讓 engine 跑回來
- 手工解除：`rm /tmp/openclaw/engine_maintenance.flag`

**為何需要**：沒有 flag 的話 operator 執行 `stop_all.sh` → engine 死 → watchdog 誤以為事故 → 自動重啟 → operator 白停。

#### 保險 #3 — SIGTERM-first graceful kill

原 `stop_all.sh` / `restart_all.sh` 用 `pkill -f "openclaw-engine"` 直接 SIGKILL — 會在 engine 寫 `paper_state.json` atomic rename 中途殺死：

```
engine 寫 paper_state.json.tmp → rename(tmp, paper_state.json) 中途被殺
↓
留下 paper_state.json.tmp（半寫 JSON）
↓
watchdog 讀檔時 json.JSONDecodeError → 誤判「state 損毀」→ 觸發重啟
↓
restart 又在中途被殺 → 虛假重啟循環
```

修復（`stop_all.sh` / `restart_all.sh` 共用 pattern）：

```bash
graceful_stop_engine() {
    pkill -TERM -f "openclaw-engine" 2>/dev/null || true
    local waited=0
    while [[ "$waited" -lt 10 ]]; do
        if ! pgrep -f "openclaw-engine" > /dev/null 2>&1; then
            return 0  # 5s 內優雅退出
        fi
        sleep 0.5
        waited=$((waited + 1))
    done
    # 5s 後仍活 → 升級 SIGKILL
    pkill -KILL -f "openclaw-engine" 2>/dev/null || true
    sleep 1
}
```

#### 保險 #4 — 指數退避 + 熔斷

```python
RESTART_BACKOFF_SECONDS = [60.0, 120.0, 300.0, 600.0, 3600.0]  # 按 consecutive_failures 索引
MAX_CONSECUTIVE_FAILURES = 5

def should_restart(data_dir, now):
    state = load_state(data_dir)
    if state.get("circuit_broken", False):
        return False, f"circuit broken after {state.get('consecutive_failures', 0)} failures"
    if now < state.get("next_allowed_restart_ts", 0):
        return False, f"backoff window, {next_allowed - now:.0f}s remaining"
    return True, "ok"
```

**流程**：
- 第 1 次重啟失敗 → 等 60s
- 第 2 次 → 120s
- 第 3 次 → 5min
- 第 4 次 → 10min
- 第 5 次 → 1hr + 熔斷
- 連續 5 次失敗 → `circuit_broken=True` + 寫 `canary_events.jsonl` `RESTART_CIRCUIT_BROKEN` event 給外部告警

**為何需要**：防止 engine 有 persistent bug 時 watchdog 無限 restart → CPU 飆升 + 磁碟 log 爆炸。熔斷後需 operator 檢查狀態 file 手動重置（`rm /tmp/openclaw/watchdog_state.json`）。

### 7.3 狀態持久化

**File**: `/tmp/openclaw/watchdog_state.json`

```json
{
  "consecutive_failures": 0,
  "next_allowed_restart_ts": 0.0,
  "circuit_broken": false,
  "last_restart_success_ts": 1712345678.0,
  "last_restart_failure_ts": 0.0,
  "last_failure_reason": ""
}
```

**原子寫入**：`tmp = path.with_suffix(".tmp"); json.dump; os.replace(tmp, path)` — 避免讀寫 race。
**corrupt 讀取**：`json.JSONDecodeError` → 退空 `{}`（全新狀態），而非崩潰。

### 7.4 Canary Events 告警

**File**: `/tmp/openclaw/canary_events.jsonl`（append-only JSON Lines）

四種 event：
- `RESTART_SUCCESS` — 重啟成功 + 清零 consecutive_failures 前的值
- `RESTART_FAILED` — 單次失敗（含 backoff_seconds）
- `RESTART_CIRCUIT_BROKEN` — 熔斷觸發
- `RESTART_SKIPPED` — 因 maintenance flag / backoff / circuit 跳過

外部監控（Grafana / PagerDuty）tail 此檔即可告警。

### 7.5 Log Rotation Bonus

`rotate_engine_log()` 在 `restart_all.sh` `restart_engine()` 之前執行：

```bash
rotate_engine_log() {
    local logs_dir="/tmp/openclaw/engine_logs"
    mkdir -p "$logs_dir"
    if [[ -f /tmp/openclaw/engine.log ]] && [[ -s /tmp/openclaw/engine.log ]]; then
        local ts=$(date +%s)
        mv /tmp/openclaw/engine.log "$logs_dir/engine-${ts}.log"
    fi
    # 只保留最新 10 份歸檔
    local count=$(ls -1 "$logs_dir"/engine-*.log 2>/dev/null | wc -l)
    if [[ "$count" -gt 10 ]]; then
        ls -1t "$logs_dir"/engine-*.log | tail -n +11 | xargs rm -f
    fi
}
```

**為何放最前面 archived 到固定路徑**：
- `>` truncate 是所有問題的根因放大器
- 一個 mv + cap 10 解決
- 10 份足夠回溯 2-3 個事故，但不會把磁碟塞滿

---

## 8. Fix 5 — Zombie `openclaw-trading-api.service` 清理

### 8.1 症狀

```
systemctl --user status openclaw-trading-api.service
Active: active (running) since 20:46:44 CEST; 3s ago  ← 剛啟動 3 秒
Main PID: 258195
```

journalctl 顯示：
```
[Errno 98] error while attempting to bind on address ('0.0.0.0', 8000): address already in use
```

配合 systemd 的 auto-restart policy → **每 3-10 秒 restart 一次，累計 1074+ 次**。

### 8.2 三個並發根因

| 根因 | 證據 |
|------|------|
| **port 8000 被手啟 uvicorn 持有** | `lsof -i :8000` 顯示 PID 28040/28078/28079/138522/138966（從 `restart_all.sh` 啟動的 uvicorn workers）| 
| **systemd 單元 cwd 錯誤** | journalctl: `Could not inject CognitiveModulator: No module named 'program_code'` — Python import 路徑不含 repo root |
| **Restart=always policy** | systemd 默認失敗即重啟，無背退 → 1074+ 次循環 |

### 8.3 決策 — 禁用而非修復

選項對比：

| A. 修復單元讓它接管 API | B. 禁用單元，`restart_all.sh` 手啟為唯一路徑 |
|---|---|
| 修 cwd + 停手啟 uvicorn + 競爭條件仍在 | 單一控制入口，無競爭 |
| systemd 守護有 auto-restart 好處 | 無 auto-restart 但 `restart_all.sh --rebuild` 也不常用 |
| 切換需額外協調工作 | 零協調 |

選 B — **服務控制集中到 `restart_all.sh`**，systemd API unit 變殘留垃圾清掉。

### 8.4 執行

```bash
systemctl --user disable --now openclaw-trading-api.service
# 輸出：Removed "/home/ncyu/.config/systemd/user/default.target.wants/openclaw-trading-api.service".
```

### 8.5 驗證

```bash
systemctl --user status openclaw-trading-api.service
# Active: inactive (dead)
# Loaded: disabled; preset: enabled

lsof -i :8000
# 仍顯示 PID 28040/28078/28079/138522/138966（手啟 uvicorn，API 無中斷）
```

### 8.6 兄弟單元健康檢查

```bash
systemctl --user status openclaw-gateway.service
# Active: active (running) since 12:19:24 CEST; 8h ago
# Main PID: 2065 (openclaw)
```

`openclaw-gateway.service` 是獨立的 node-based gateway，與 engine/API 無關，8 小時 uptime 健康 — **不動它**。

### 8.7 恢復路徑（若未來需要）

```bash
# 1. 先解決 cwd + import path 問題（修改 .service 文件）
# 2. 停所有手啟 uvicorn workers
pkill -f 'uvicorn.*app.main:app'
# 3. 重新啟用
systemctl --user enable --now openclaw-trading-api.service
```

---

## 9. 檔案清單 / File Inventory

### Rust（engine）

| File | 變更 | 說明 |
|------|------|------|
| `rust/openclaw_engine/src/main.rs` | L55-108 panic hook · L57-119 crash_only helper · L882/940 spawn 改造 · L1108-1155 ws stale watchdog · Live thread cancel 補齊 | Fix 1/3/4 全部在此檔 |

### Python（watchdog）

| File | 變更 | 說明 |
|------|------|------|
| `helper_scripts/canary/engine_watchdog.py` | +180 行 helpers · flock · 整合 on_engine_crash | Fix 2 主體 |

### Shell（operator 腳本）

| File | 變更 | 說明 |
|------|------|------|
| `helper_scripts/stop_all.sh` | **新增** ~90 行 | maintenance flag 建立 + graceful kill |
| `helper_scripts/restart_all.sh` | +50 行 | log rotation + graceful stop + flag 清除 |

### 文檔

| File | 變更 | 說明 |
|------|------|------|
| `docs/known_issues/2026-04-14--ws_stale_detector.md` | **新增** | WS stale 閾值設計與誤報場景文檔 |
| `docs/worklogs/2026-04-14--engine_self_healing.md` | **新增**（本檔） | 工程日誌 |
| `CLAUDE.md` | §三 + §十一 補 | 一行狀態 |
| `docs/CLAUDE_CHANGELOG.md` | 頂部新增 section | Session 敘事 |
| `TODO.md` | ENGINE-HEAL / ZOMBIE-API-SVC 標記完成 + 基準線更新 | |

### Runtime 產物（/tmp/openclaw/）

| Path | 用途 | Lifecycle |
|------|------|-----------|
| `watchdog.lock` | flock 單例鎖 | watchdog 啟動建立，退出釋放 |
| `watchdog_state.json` | 重啟狀態持久化 | watchdog 維護，熔斷後 operator 可手刪重置 |
| `canary_events.jsonl` | 事件 append-only | 無限增長（需 operator 定期 rotate） |
| `engine_maintenance.flag` | operator 停機意圖 | `stop_all.sh` 建，`restart_all.sh` 清 |
| `engine_logs/engine-<epoch>.log` | 歸檔 engine log | `restart_all.sh` 歸檔，cap 10 份 |
| `engine.log` | 當前 engine stdout/stderr | 下次 restart 時歸檔 |

---

## 10. 驗證 / Verification

### 10.1 Rust E4 baseline（回歸測試）

```bash
cd rust
cargo test --release -p openclaw_engine --lib   # 1144 passed / 0 failed
cargo test --release -p openclaw_core --lib     # 366 passed / 0 failed
cargo test --release -p openclaw_engine --test '*'  # 33 passed / 0 failed
```

**總計 1543 pass / 0 fail**（與 pre-fix baseline 完全一致 — panic hook 與 crash-only 不影響正常路徑）。

### 10.2 Watchdog 單元檢查（8/8 pass）

```python
# tempfile isolate + 手造 state 驗證：
assert load_state(missing_file) == {}                    # ✓
assert load_state(corrupt_json) == {}                    # ✓
save_state(d, {"k": 1}); assert load_state(d)["k"] == 1  # ✓
assert compute_backoff(0) == 60.0                        # ✓
assert compute_backoff(5) == 3600.0                      # ✓
assert compute_backoff(99) == 3600.0                     # ✓（越界夾緊）
assert should_restart(clean_dir, now)[0] == True         # ✓
assert should_restart(with_flag, now)[0] == False        # ✓
assert should_restart(circuit_broken, now)[0] == False   # ✓
assert should_restart(backoff_active, now)[0] == False   # ✓
```

### 10.3 Shell 語法

```bash
bash -n helper_scripts/stop_all.sh     # 退出 0
bash -n helper_scripts/restart_all.sh  # 退出 0
```

### 10.4 Zombie service 清理驗證

```bash
systemctl --user status openclaw-trading-api.service
# Active: inactive (dead) / disabled   ← 確認清掉

lsof -i :8000
# PID 28040/28078/28079/138522/138966 繼續 LISTEN   ← 確認 API 無中斷

systemctl --user status openclaw-gateway.service
# Active: active (running) since 12:19:24 CEST; 8h ago   ← 確認 sibling 健康
```

---

## 11. 部署步驟 / Deployment

**Fix 1/3/4**（engine binary 變更）需 operator 執行：

```bash
bash helper_scripts/restart_all.sh --rebuild
```

`--rebuild` 旗標會：
1. `helper_scripts/build_pyo3.sh` — 重建 PyO3 `.so` 雙寫兩個 venv（QoL-3）
2. `rotate_engine_log()` — 歸檔當前 engine.log 到 `/tmp/openclaw/engine_logs/engine-<epoch>.log`
3. `graceful_stop_engine()` — SIGTERM + 5s + SIGKILL fallback 停舊 engine
4. 清除 `/tmp/openclaw/engine_maintenance.flag`（operator 意圖：讓 engine 跑）
5. `cargo build --release -p openclaw_engine` → 啟動新 binary

**Fix 2**（watchdog）+ **Fix 5**（zombie）— 已即時生效，無需部署。

**部署驗證**：

```bash
# 引擎啟動後 60s
python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status
# 預期：{"engine_alive": true, "snapshot_age_seconds": <60}

# 檢查新 binary 有 panic hook
grep 'PANIC captured\|pipeline_crash\|WS tick stale' /tmp/openclaw/engine.log
# 啟動時應看到 tick-stale watchdog spawn 日誌

# 確認 watchdog 運行
ps aux | grep engine_watchdog.py
cat /tmp/openclaw/watchdog.lock  # 應有 PID
```

---

## 12. 測試 / Testing Guidance

### 12.1 合成測試（建議在 canary 環境）

**Panic 注入測試**：

```rust
// 暫時在 tick_pipeline 的 tick 處理加一行
if symbol == "CANARYTEST" { panic!("synthetic panic test"); }
```

預期：
1. `engine.log` 立即出現 `PANIC captured` 結構化 event（Fix 1）
2. `pipeline_crash` event 廣播（Fix 3）
3. Ordered shutdown log
4. Engine 退出（exit code 0，因 graceful cancel）
5. Watchdog 45s 內偵測死亡（Fix 2）
6. `restart_all.sh --engine-only` 被呼叫
7. `canary_events.jsonl` 追加 `RESTART_SUCCESS` event

**WS stale 測試**：

```bash
# 方法 A（最簡）：拉網線 130s 後插回
# 方法 B：在 event_consumer 暫時加 tokio::spawn sleep 130s 持 Mutex 阻塞 last_tick_ms.store
```

預期：
1. 120s 後 `WS tick stale — triggering engine cancel (Fix 4)` log
2. Ordered shutdown log
3. Exit code 0
4. Watchdog 拉起
5. 新 binary 重新訂閱 WS，last_tick_ms 重置為 0（warmup）→ 不誤觸

### 12.2 Maintenance flag 測試

```bash
bash helper_scripts/stop_all.sh --engine-only
# 預期：engine 停 + /tmp/openclaw/engine_maintenance.flag 建立

# Watchdog 日誌觀察
tail -f /var/log/watchdog.log  # 或 journalctl -u watchdog
# 預期：偵測到死亡 + "Auto-restart skipped: maintenance flag present" log

# 清除恢復
bash helper_scripts/restart_all.sh --engine-only
# 或手工：rm /tmp/openclaw/engine_maintenance.flag
```

### 12.3 熔斷測試（模擬 persistent failure）

```bash
# 製造重啟失敗（修 rust binary 讓它馬上 panic）
# 或讓 restart_all.sh return 非 0
# 觀察 watchdog_state.json 變化

cat /tmp/openclaw/watchdog_state.json
# 5 次失敗後：{"circuit_broken": true, "consecutive_failures": 5, ...}
# canary_events.jsonl：{"event": "RESTART_CIRCUIT_BROKEN", ...}

# 恢復
rm /tmp/openclaw/watchdog_state.json  # 清狀態
# 再修好 binary 然後手動 restart
```

---

## 13. 開放問題 / Open Questions

1. **真實事故當日的精確死因？** — log 被 truncate 已不可考。合理推論：
   - ws 連線掉 + 重連 stuck 在某個未處理狀態
   - 可能是 `event_consumer` 内某條 channel 滿了 deadlock
   - 但沒 panic hook 無 backtrace 可查
   - **Fix 1 的意義就是下次不再失去證據**

2. **為何 tokio runtime 沒 catch_unwind 自動包 spawn？** — tokio 的 `tokio::spawn` 默認會把 panic 傳播到 JoinHandle。但若 handle 被 detach（如 `let _ = tokio::spawn(...)`），panic 會被默默丟棄。事故當日的 spawn 都是顯式 detach 模式。Fix 3 `run_pipeline_crash_only` 解決的正是這個。

3. **120s 閾值是否會在真實生產環境誤報？** — 需觀察 ≥1 週。若誤報 >2 次/週 → 考慮放寬到 180s 或實作 per-tier 閾值（Phase 2）。

4. **watchdog 本身是否需 HA？** — 目前 watchdog 自己死亡 = 無人偵測 engine。可考慮：
   - 雙 watchdog（A 監 engine，B 監 A）— 過度
   - systemd user unit 守護 watchdog — 合理下一步
   - cron 檢查 watchdog 存活 — 簡單
   - 目前暫時人工（每次 session 開始檢查 `/tmp/openclaw/watchdog.lock` 是否存在）

---

## 14. Phase 2 TODO（非本次 scope）

| 項目 | 優先級 | 依賴 |
|------|--------|------|
| 真實 panic 注入測試走 canary | M | R07-6 R07 Go/No-Go 一併 |
| `OPENCLAW_TICK_STALE_THRESHOLD_MS` env 可覆蓋 | L | 無 |
| Per-tier stale threshold（BTC/ETH 嚴判 / tier-3 放寬）| M | scanner tier classification |
| Metric export `tick_stale_ms` 給 Grafana | M | 告警 pipeline |
| IPC `get_tick_stale_ms` 給 GUI | L | IPC schema |
| systemd user unit 守護 watchdog | M | 無 |
| Pre-cancel warning（60s WARN / 120s act）| L | 無 |
| `canary_events.jsonl` 自動 rotate | L | logrotate 配置 |

---

## 15. 回退路徑 / Rollback

若部署後發現 Fix 1/3/4 造成問題：

```bash
cd /home/ncyu/BybitOpenClaw/srv
git log --oneline main.rs | head -5    # 找到 pre-fix commit
git show <pre-fix-commit> -- rust/openclaw_engine/src/main.rs > /tmp/pre_fix_main.rs
# 審查後決定是否 revert 特定 fix

# 最快方法：整個 ENGINE-HEAL revert
git revert <fix-commit-hash>
bash helper_scripts/restart_all.sh --rebuild
```

若 Fix 2 watchdog 有問題：

```bash
# 完全停用 watchdog（engine 退回無自動重啟）
pkill -f engine_watchdog.py
rm /tmp/openclaw/watchdog.lock /tmp/openclaw/watchdog_state.json
```

若 zombie service 禁用造成 API 託管丟失（需 systemd 自動拉起）：

```bash
systemctl --user enable --now openclaw-trading-api.service
# 先停手啟 uvicorn：pkill -f 'uvicorn.*app.main:app'
```

---

## 16. 結論 / Conclusion

**系統狀態變化**：

| | Before 2026-04-14 | After 2026-04-14 |
|---|---|---|
| engine panic 可見性 | 靜默（無 hook + 無 flush） | 結構化 log + backtrace + location |
| pipeline panic 語義 | 不明確（可能 isolate 可能 exit） | 全部 crash-only + ordered shutdown |
| WS 殭屍偵測 | 無（進程活就算活） | 120s stale → self-cancel |
| engine 死亡後自動重啟 | 無（operator 必須手工） | watchdog + 退避 + 熔斷 |
| 死前日誌保存 | 被 `>` truncate 清零 | 歸檔 10 份到 `engine_logs/` |
| operator 意圖表達 | 無（watchdog 不知道是否 operator 主動停） | maintenance flag |
| API systemd 單元 | restart 循環 1074+ 次 | 禁用，手啟為唯一路徑 |

**未解項**：
1. 部署 Fix 1/3/4 binary（operator action）
2. 真實 canary 驗證（R07）
3. Phase 2 enhancements（env / per-tier / metric export）

**簽署**：Session 2026-04-14 PM · All 8 tasks completed · 1543 Rust / 0 fail baseline maintained.
