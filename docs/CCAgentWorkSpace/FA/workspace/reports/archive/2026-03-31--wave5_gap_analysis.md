# FA 報告：Wave 5 功能規格 Gap 分析

**日期**：2026-03-31

---

## 關鍵發現（兩個阻塞項）

### G-01【BLOCKER】每日硬上限數值衝突
- 代碼：`DEFAULT_DAILY_HARD_CAP_USD = 15.0`
- DOC-08 §4：`$2.00`
- 差距 7.5 倍，必須在 Wave 5 啟動前澄清並決策

### G-05【BLOCKER】ExecutorAgent 未通過 Decision Lease
- ExecutorAgent → submit_order() 未調用 `governance_hub.acquire_lease()`
- 違反原則 3（AI 輸出≠即時命令）
- Strategist shadow=False 之前必須修復

---

## 功能完整性核查（8 項驗收標準）

| AC | 驗收條件 | 測試方法 |
|----|---------|---------|
| AC-1 | 超日硬上限 → trigger 返回 blocked | Mock cost > hard_cap |
| AC-2 | Ollama 崩潰不中斷交易（fail-open）| Mock is_available()=False |
| AC-3 | Scout intel 可觀察地到達 Strategist | 驗證兩個 stats counter |
| AC-4 | cost_edge_ratio Grade F 可觀察 | ratio=0.85 → grade=F |
| AC-5 | L2 session Decision Lease 安全標記不可變 | decision_lease_emitted=False |
| AC-6 | data_days < 3 時 adaptive 不啟用 | Mock 2天數據 → 倍率=1.0 |
| AC-7 | API key 缺失時系統不崩潰 | ANTHROPIC_API_KEY="" |
| AC-8 | pricing 表超期 30 天告警可觀察 | Mock stale timestamp |

---

## 根原則合規風險

### 原則 3 風險
- ExecutorAgent 直接調用 submit_order()，AI 輸出未通過 Decision Lease
- **必須修復後才能啟用 Strategist shadow=False**

### 原則 10 風險（AI ROI 不誠實）
- paper_pnl 是模擬值，計算出的 ROI 不可信
- 修復：API 添加 `roi_basis: "paper_simulation_only"` 標記

### 原則 14 合規
- 降級鏈條完整（L2→L1.5→L1→L0）
- 但需要集成測試確認純 L0 模式下全流程可運行

---

## 接通後功能完整度預估

| 環節 | 當前 | Wave 5 後 |
|------|------|----------|
| AI 風險評估 | 20% | 55% |
| 策略選擇 | 40% | 50% |
| 學習 | 25% | 35% |
| **整體** | **32%** | **~45%** |

---

## FA 派發建議

**Sprint 5a 前阻塞項**：
1. PM + FA 聯合決策：每日硬上限 $2 vs $15（0.5h 會議）
2. PA 確認：ExecutorAgent Decision Lease 接入設計

**Sprint 5a**（G-01/G-05 修復 + H1-H5 核心接通）：~15h
**Sprint 5b**（Agent 落地完善 + E2E 測試）：~20h
