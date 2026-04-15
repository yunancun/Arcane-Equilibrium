# 2026-04-15 工程日誌 — ENGINE-HEAL FIX-PHASE1 FUP-A/B + E4-HYG-1
# Worklog — Canary writer warn throttling, Full-branch coverage, core test hygiene

**Session**: post-compact continuation
**Commits**: `6c73b60` (FUP-A/B) · `0762006` (E4-HYG-1)
**Branch**: `main` (本地領先 `origin/main`，未 push)

---

## 一、背景 / Context

前序 session `5d5ec13 fix(engine-heal-phase1): offload canary write off live event loop hot path` 將 canary JSONL 寫盤從 `event_consumer` 熱路徑改為專用 tokio 任務（bounded mpsc 4096 + `BufWriter` + size rotation）並把 live fan-out channel 512→1024 對稱化。E2 審查 GREEN，但記錄兩條 nit 作為 FUP，未阻塞合併：

- **FUP-A**：`try_send` 在通道滿時每次都 `warn!`，持續壓力下 warn 自身成為 log flood
- **FUP-B**：缺 `TrySendError::Full` 分支單元測試，無法斷言「滿了不阻塞 event loop」

本 session 任務：結清這兩條，外加巡查中發現的 core 測試編譯錯誤 E4-HYG-1。

---

## 二、改動 / Changes

### 1. FUP-A — 1Hz warn 節流 + 單調 drop counter

`rust/openclaw_engine/src/canary_writer.rs`

- `CanaryWriterHandle` 新增兩個 `Arc<AtomicU64>` 欄位：
  - `total_dropped`：Full 分支單調遞增的總丟棄數（跨 clone 共享）
  - `last_warn_ms`：最近一次 warn 的 epoch-ms；CAS gate 決定本次是否有資格 log
- `disabled()` / `spawn()` 兩個建構子都初始化為 `Arc::new(AtomicU64::new(0))`
- `try_send` 的 `Err(TrySendError::Full(_))` 分支改為：
  1. `total_dropped.fetch_add(1, Relaxed) + 1` — 計數器必遞增
  2. 再呼叫 `should_emit_warn()`，成功 CAS 的執行緒才 emit `warn!`
- `should_emit_warn()` 使用 `compare_exchange(last, now_ms, Relaxed, Relaxed)`，窗口 `WARN_THROTTLE_MS = 1000`。保證：多執行緒競爭同一窗口時最多一人勝出；計數器語意與 log 節奏解耦。

**設計要點**：warn 消息內嵌 `total_dropped`，運維在持續壓力下看到的是**累積丟棄數**（單調），而非單次事件，利於判斷嚴重度。

### 2. FUP-B — Full 分支單元測試

同檔 `#[cfg(test)] mod tests`：

- `try_send_full_branch_drops_and_counts` (`#[tokio::test]`)
  - 建 1-slot mpsc 的 `CanaryWriterHandle`
  - 第一次 `try_send` 把唯一 slot 填滿
  - 後續 3 次 `try_send` 應全走 Full 分支，不 block / panic
  - `total_dropped` 應達 3
  - clone handle 再 `try_send` 一次，counter 共享到 4（驗證 Arc<AtomicU64> clone 語意）
- `warn_throttle_caps_at_one_hz` (`#[test]`)
  - `disabled()` handle（免起 runtime）
  - `should_emit_warn()` 首呼 `true`（`last_warn_ms=0`）
  - 立即二呼 `false`（窗口內 CAS 失敗）

### 3. E4-HYG-1 — core 測試欄位補齊

`rust/openclaw_core/tests/golden_extreme.rs:161` `test_trailing_and_time_stop_interaction`：

```rust
let config = StopConfig {
    hard_stop_pct: 10.0,
    trailing_stop_pct: Some(2.0),
    time_stop_hours: Some(1.0),
    atr_multiplier: Some(2.0),
    take_profit_pct: None,
+   trailing_activation_pct: None,
};
```

`trailing_activation_pct: Option<f64>` 由 `51f6744 fix(pnl): trailing-stop activation gate` 引入，該測試漏更新。選 `None` 保留原語意：`stop_manager.rs:162` `activation_pct = trail_pct`（2%），best_price=110 → trail 價 107.8，price 108 > 107.8 不觸發 trailing；時間戳 4_000_000ms > 3_600_000ms → 時間停損觸發，符合測試原本斷言 `StopType::Time`。

---

## 三、驗證 / Verification

| 套件 | before | after | Δ |
|------|--------|-------|---|
| `openclaw_engine --lib` | 1262 | 1264 | +2 (FUP-B 兩測試) |
| `openclaw_core` | ❌ 編譯失敗 | 372 pass 0 fail | 恢復 |
| `cargo build --release` | ✅ | ✅ | 不受影響 |

FIX-PHASE1 部署前後綜合基準線：`engine lib 1264 + core 372 + e2e 35 = 1671`。

---

## 四、留尾 / Follow-ups

1. **FIX-PHASE1 binary 部署**（operator 動作）：運行中 binary mtime 2026-04-15 01:55（僅含 FIX-PHASE1 前修復）。需 `bash helper_scripts/restart_all.sh --rebuild` 讓 PID 577219 換成包含 5d5ec13 + 6c73b60 + 0762006 的新 binary。
2. **FUP-1 watchdog systemd 正式化**：當前 PID 592881 是 `nohup` 方式啟動，不跨重啟存活。W22 收尾前換 systemd user unit（`restart_all.sh` 整合或獨立 `openclaw-watchdog.service`）。
3. **G-2 FundingArb 驗證**（daemon PID 598572 監控中）：11:47 UTC 為 0/20 fills，純被動等待 demo funding_arb 累積出場。
4. **24h 觀察 `live pipeline lagging` WARN** 是否歸零 / canary dump 是否落在 rotation 界內（依 `OPENCLAW_CANARY_ROTATE_MB=1024` 預設）。

---

## 五、經驗提煉 / Lessons

- **Arc<AtomicU64> + CAS 是標準的「多 clone 共享 throttle 狀態」範式**：計數器與 log gate 用兩個獨立 atomic 分離關注點，避免 counter 語意被 log cadence 污染。
- **E2 nit 不阻塞合併但要有主體**：FUP-A/B 列在 TODO 作為獨立 item（`3a` / `3b`），下 session 接手有明確起點。不將 nit 累積成技術債。
- **欄位新增必須巡查所有 struct literal**：`StopConfig` 加 `trailing_activation_pct` 時漏改 `golden_extreme.rs`，release 構建不報但 test 編譯斷。日後加欄位應 `rg 'StopConfig {'` 全倉掃描再 merge。

---

**作者**：Claude (main session, PM+Conductor)
**接手指引**：下 session 第一個 `[ ]` 是 `ENGINE-HEAL-FUP-1` watchdog systemd 正式化，或等 G-2 daemon 觸發 audit 寫入。
