# FA Memory — 工作記憶

## 項目功能狀態快照（2026-03-31）

```
業務功能真正可用 ≈ 32%（Round 2 冷酷審核）

逐環節：
  自動掃描 = 85%（Scout 情報無消費者）
  策略選擇 = 40%（無 AI，無回測，無動態倉位）
  AI 風險評估 = 20%（H1-H5 完全斷開）
  下單 = 90%（治理 gate + OMS 完整）
  止損 = 90%（本地 3 類 + 交易所條件單）
  學習 = 25%（Perception Plane 零調用）
  進化 = 30%（無策略自動優化）
```

## 重要發現記錄

### FA-1 端點角色矩陣（2026-03-31）
- 完成 28 個 governance 端點的角色驗證矩陣
- 發現 2 個 POST 端點缺少 Operator 驗證（已修復為 P2-NEW-7/8）
- **記住**：未來新增 governance 端點必須對照矩陣，狀態改變的 POST 端點必須有 `_require_operator_role()`

### FA-2 reconciliation 邊界值（2026-03-31）
- 發現 3 個 NaN/負數/inf 漏洞（已修復）
- **記住**：任何涉及財務數值計算的代碼，必須在 FA 審查時特別要求 math.isnan/isinf 防護

### FA-3 async/threading 混用（2026-03-31）
- scout_routes.py 5 個 async 路由阻塞 event loop（已修復）
- **記住**：FastAPI async 路由中使用 threading.Lock 的同步方法必須標記為高風險

### H1-H5 斷開（關鍵）
- H1-H5 代碼在 `ai_agents/bybit_thought_gate/` 是獨立腳本，與 app 層完全無連接
- `apply_ai_consultation()` 是純 stub，返回佔位字符串
- **記住**：這是系統最大的業務功能缺口，接通後業務可用度可從 32% 提升到 55%+

## 審計原則記憶

- 審計時不要只看代碼存在與否，要追蹤調用鏈是否真實走通
- 「功能可用」的定義：從 API 觸發，到最終業務結果，中間每一步都有數據流動

## 報告索引

| 日期 | 報告類型 | 文件位置 |
|------|---------|---------|
| 2026-03-31 | FA-1 端點角色矩陣 | ../E3/workspace/ (由 E3 存檔) |
| 2026-03-31 | FA-2/3/4 深度審計 | workspace/reports/2026-03-31--fa_deep_audit.md |
| 2026-03-31 | Wave 5 功能 Gap 分析 | workspace/reports/2026-03-31--wave5_gap_analysis.md |
