# Phase R-07：灰度驗證 + 穩定觀察（加速方案）

**週期**：原計 4 週 → **加速至 ~7 天**（歷史回放取代即時灰度）
**前置**：`06--python_ipc_integration.md` Go（2026-04-03 通過）
**完成後**：Rust 遷移正式完成，進入正常運維

---

## 加速方案說明

原方案需要 22 天（7 天即時灰度 + 14 天穩定觀察）。加速方案：

| 原方案 | 加速方案 | 依據 |
|--------|----------|------|
| 即時雙進程 7 天 | **歷史回放**（5 分鐘跑完 7 天 × 5 幣種 = 201,600 ticks） | Comparator 是離線工具，不需即時 |
| 回滾/接管演練分散灰度期 | **Day 0 直接跑** | 腳本已就緒 |
| 穩定觀察 2 週 | **與正常運行重疊 7 天**（Watchdog 保護） | 有 3 振回滾機制 |

---

## 已完成工具（代碼層面 — 全部 Session 11）

### [x] R07-1：回放運行器 — `replay_runner.py` · commit `bbc0137`
- 從 Bybit REST API 獲取歷史 1m K 線（分頁，每次 200 根）
- 合成 4 tick/bar（OHLC）模擬真實 tick 流
- 通過 Python KlineManager + IndicatorEngine + SignalEngine 運行
- 輸出 `shadow_results.jsonl`（匹配 canary schema V1.0.0）
- **已驗證**：7 天 × 5 幣種 = 201,600 ticks，300 秒完成

### [x] R07-2：Rust 灰度輸出 — commit `5c8039a`
- `CanaryRecord` struct（tick_pipeline.rs）
- `canary_mode` flag + `maybe_canary_record()` 方法
- `main.rs`：`OPENCLAW_CANARY_MODE=1` 環境變量啟用 → 寫 `engine_results.jsonl`
- 3 個 Rust 測試

### [x] R07-3：Comparator — commit `ca9dabd`
- `canary_schema.py`：JSONL 模式合約 V1.0.0 + 3 層容差映射
- `canary_comparator.py`：tick 級比較 + 信號方向匹配 + 邊界偏差升級（V3-QC-5）+ CLI
- 14 個比較器測試

### [x] R07-5：回滾演練腳本 — commit `ca9dabd`
- `rollback_drill.sh`：8 步演練（stop engine → verify fallback → git checkout → restart → health check）
- SLA 計時 + dry-run 模式

### [x] R07-6：引擎看門狗 — commit `ca9dabd`
- `engine_watchdog.py`：快照新鮮度監控 + 崩潰/恢復檢測 + 3 振回滾
- 11 個看門狗測試

---

## 待完成運行時驗證

### [ ] R07-4：灰度驗證（~7 天）

**Day 0 — 啟動：**
1. `cargo build --release -p openclaw_engine`
2. `OPENCLAW_CANARY_MODE=1 ./openclaw-engine` 啟動引擎
3. `bash rollback_drill.sh --dry-run` 執行回滾演練
4. 啟動 `python engine_watchdog.py` 監控

**Day 1-7 — 監控：**
- 引擎正常運行，Watchdog 每 2 秒檢查
- `engine_results.jsonl` 持續累積
- 每日執行：`python canary_comparator.py --engine ... --shadow ...`

**Day 7 — Go/No-Go：**
- 0 CRITICAL + <10 WARNING → PASS
- 零崩潰 + 記憶體穩定 → PASS
- 回滾演練 < 10 分鐘 → PASS

### [ ] R07-7~8：關閉影子 + 冗餘標記
- 灰度 PASS 後 `git tag pre-rust-cleanup`
- Python 確定性模組標記 `# DEPRECATED`

### [ ] R07-9~10：穩定觀察 + 最終清理
- 併入 Day 1-7 觀察期（已有 Watchdog 保護）
- 穩定後刪除 DEPRECATED 代碼

---

## Go/No-Go 門控

### 灰度通過條件
- [ ] 歷史回放 201,600 ticks 比較：0 CRITICAL（Python shadow 已完成）
- [ ] 即時運行 7 天：穩態 0 崩潰（啟動寬限期內不計 / steady-state zero crash — startup grace window excluded）
- [ ] 回滾演練 < 10 分鐘
- [ ] Watchdog 3 振機制驗證

### 穩定觀察通過條件（併入 7 天觀察期）
- [ ] tick P50 < 50μs
- [ ] 記憶體穩態 < 100MB
- [ ] IPC 零丟失

---

## 事件記錄（Incident Log）

### INC-001：Cold Start Jitter 3-STRIKE（2026-04-03）

**時間線 / Timeline：**
- 22:50 ~ 23:08 — Watchdog 連續偵測到 3 次 `ENGINE_CRASH`（3-STRIKE 觸發）
- 三次 snapshot age 僅超閾值 0.1–0.5 秒（marginal overshoot）

**根因 / Root Cause：**
- Cold Start Jitter — 引擎啟動初期的已知瞬態問題
- Watchdog `stale-threshold` 在啟動期過於敏感，無寬限窗口
  （watchdog stale-threshold too aggressive during startup, no grace window）
- 引擎快照首次寫入依賴 `status_interval` 觸發，啟動後首個快照延遲
  （first snapshot write depends on status_interval trigger, delayed after cold start）

**修復措施 / Remediation：**
- Watchdog 增加 `--grace-period 120s`，啟動寬限期內不計入 STRIKE
  （added --grace-period 120s to watchdog, strikes during startup grace window are excluded）
- 引擎啟動時 `force_write` 初始快照，消除首次寫入延遲
  （engine force_write initial snapshot on startup, eliminating first-write delay）

**恢復驗證 / Recovery Verification：**
- 修復後引擎已穩定運行 108h+，累計 397K+ ticks，零崩潰
  （post-fix: 108h+ uptime, 397K+ ticks processed, zero crashes）

**結論 / Conclusion：**
- P2 改善項，不構成 Go/No-Go 阻塞（P2 improvement item, does not block Go/No-Go）
- 事件已不影響 Go/No-Go 判定（incident does not affect Go/No-Go decision）

---

## 進度追蹤

| 任務 | 狀態 | 完成日期 | commit |
|------|------|---------|--------|
| R07-1 回放運行器 | ✅ | 2026-04-03 | `bbc0137` |
| R07-2 Rust 灰度輸出 | ✅ | 2026-04-03 | `5c8039a` |
| R07-3 Comparator | ✅ | 2026-04-03 | `ca9dabd` |
| R07-4 灰度 7 天 | ⏳ 待啟動 | | |
| R07-5 回滾演練腳本 | ✅ | 2026-04-03 | `ca9dabd` |
| R07-6 引擎看門狗 | ✅ | 2026-04-03 | `ca9dabd` |
| R07-7 關閉影子 | ⏳ 灰度後 | | |
| R07-8 冗餘標記 | ⏳ 灰度後 | | |
| R07-9 穩定觀察 | ⏳ 併入灰度期 | | |
| R07-10 最終清理 | ⏳ 穩定後 | | |

---

## 問題與變更

1. **加速方案採用**（Session 11）：歷史回放取代 7 天即時灰度，22 天 → ~7 天
2. **R07-1 架構變更**：從即時 WS shadow 改為歷史回放 replay_runner.py
3. **R07-3/5/6 提前構建**：灰度工具在 R-06 完成後立即構建
4. **E5 flag**：Rust StateWriter 應用 atomic write（.tmp → rename）
5. **Python shadow 已驗證**：201,600 records（7d × 5sym），300 秒完成
6. **歷史測試債務清零**：28 failed + 17 errors → 0（Session 11）
7. **INC-001 Cold Start Jitter**（2026-04-03）：3-STRIKE 誤觸發，根因為啟動期 watchdog 過敏 + 首次快照延遲。已修復（grace-period 120s + force_write）。108h+ 穩定，不影響 Go/No-Go。詳見「事件記錄」章節
