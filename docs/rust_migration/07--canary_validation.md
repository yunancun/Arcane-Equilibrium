# Phase R-07：灰度驗證 + 穩定觀察（Week 11-14）

**週期**：Rust 主開發 Week 11-14
**工時**：~4 週（2 週灰度 + 2 週穩定觀察）
**前置**：`06--python_ipc_integration.md` Go
**完成後**：Rust 遷移完成，進入正常運維

---

## 上下文導航

```
源文件：V3-FINAL §5（灰度驗證框架）+ §7.2（回滾計劃）
前置完成：Python 全部 IPC 改造 · 60 個集成測試 PASS · 回滾預演 SLA 達標
本階段目標：雙寫雙算 7 天零 CRITICAL → 關閉影子 → 穩定觀察 → 最終清理
```

**PM 提醒**：
- W11-12 期間 Python 確定性路徑**完全 code freeze** [V3-PM-5]
- W11 必須演練一次**完全回滾**（git checkout pre-rust-cleanup tag）[V3-PM-7]

---

## Week 11-12：灰度驗證

### [ ] R07-1：影子計算進程搭建
- Python 影子進程保留全部確定性模組（pipeline_bridge / indicator_engine / SM 等）
- 同時消費 Bybit WS 數據
- 輸出 shadow_results.jsonl

### [ ] R07-2：Rust Engine 啟動灰度模式
- 真正下單到 Paper
- 輸出 engine_results.jsonl

### [ ] R07-3：Comparator 自動化對比
- 逐 tick 對比 engine_results vs shadow_results
- 容差分級（V3 §5.4）：
  - 簡單聚合 1e-10 / 遞歸 1e-8 / Hurst 1e-6
  - 信號方向嚴格（邊界豁免 [V3-QC-1]）
  - H0 Gate / SM 嚴格
- **BOUNDARY_DIVERGENCE 自動升級** [V3-QC-5]：
  - 連續 1h > 5% → 升級 FAIL
  - 24h 累計 > 50 次 → 升級 FAIL

### [ ] R07-4：灰度 Go/No-Go（每日審閱）
- 連續 7 天 CRITICAL = 0 且 WARNING < 10 → PASS
- 任何 CRITICAL → 暫停灰度 → 診斷 → 修復 → 重啟 7 天計數器

### [ ] R07-5：W11 完全回滾演練 [V3-PM-7]
- 實際操作：git checkout pre-rust-cleanup → 重部署 → 驗證系統正常
- 計時：必須 < 10 分鐘
- 記錄回滾步驟文檔

### [ ] R07-6：W11 止損接管演練 [V3-PA-7]
- 模擬 Engine 崩潰（kill -9）
- 驗證 Python watchdog 2s 內啟動本地止損
- 驗證 Engine systemd 重啟後 Python 讓位

---

## Week 13-14：穩定觀察 + 清理

### [ ] R07-7：關閉影子進程
- 灰度 7 天 PASS 後，停止 Python 影子計算
- git tag `pre-rust-cleanup`

### [ ] R07-8：冗餘 Python 代碼標記
- 標記所有「完整刪除」文件為 `# DEPRECATED: Rust Engine handles this`
- **不立即刪除**——保留 4 週

### [ ] R07-9：穩定觀察 2 週
- 純 Rust Engine + Python AI/GUI 雙進程架構運行
- 每日監控：tick P50/P99、IPC 延遲、記憶體使用、崩潰次數
- 異常 → 啟動 runtime 回滾（watchdog 3-strike）

### [ ] R07-10：最終清理（W14 結束後 +4 週）
- 確認穩定後刪除所有 `# DEPRECATED` Python 文件
- 刪除影子計算相關代碼
- 更新 CLAUDE.md / README.md / TODO.md
- 最終 commit

---

## Go/No-Go 門控

### 灰度通過條件
- [ ] 連續 7 天 CRITICAL = 0
- [ ] 連續 7 天 WARNING < 10
- [ ] BOUNDARY_DIVERGENCE 率 < 1%
- [ ] 完全回滾演練 < 10 分鐘
- [ ] 止損接管演練 < 2 秒

### 穩定觀察通過條件
- [ ] 2 週內零崩潰
- [ ] tick P50 < 50μs（正式目標）
- [ ] 記憶體無洩漏（穩態 < 100MB）
- [ ] IPC 零丟失

---

## 進度追蹤

| 任務 | 狀態 | 完成日期 | commit |
|------|------|---------|--------|
| R07-1 影子進程 | [ ] | | |
| R07-2 灰度模式 | [ ] | | |
| R07-3 Comparator | ✅ | 2026-04-03 | Session 11 |
| R07-4 灰度 7 天 | [ ] | | |
| R07-5 完全回滾演練腳本 | ✅ | 2026-04-03 | Session 11 |
| R07-6 引擎看門狗 | ✅ | 2026-04-03 | Session 11 |
| R07-7 關閉影子 | [ ] | | |
| R07-8 冗餘標記 | [ ] | | |
| R07-9 穩定觀察 | [ ] | | |
| R07-10 最終清理 | [ ] | | |

---

## 問題與變更

1. **R07-3/5/6 提前構建**（Session 11）：灰度比較器 + 回滾腳本 + 引擎看門狗在 R-06 完成後立即構建
   - `helper_scripts/canary/canary_schema.py`：JSONL 模式合約 + 容差分級
   - `helper_scripts/canary/canary_comparator.py`：3 層容差比較 + 邊界偏差升級 + CLI
   - `helper_scripts/canary/engine_watchdog.py`：快照新鮮度監控 + 崩潰/恢復 + 3 振回滾
   - `helper_scripts/canary/rollback_drill.sh`：8 步回滾演練（SLA < 10 分鐘）
   - `helper_scripts/canary/test_canary.py`：35 個測試全 PASS
2. **E5 發現**：Rust StateWriter 應使用 atomic write（write .tmp + rename），flag 為 R07-2 修復
