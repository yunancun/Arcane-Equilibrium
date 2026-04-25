---
name: ux-checklist
description: 交易系統 GUI 可用性 / 認知負荷 / 錯誤狀態 / 防誤觸 audit；A3 agent 純審查不寫代碼。
allowed-tools: Read, Grep, Glob
---

# UX Checklist（交易 GUI 可用性審查）

## 何時觸發

- A3 收到「UX 審查」「可用性審計」「Live GUI 上線前 readiness」
- 任何新 tab / 新 modal / 新表單上線前
- 既有 GUI 操作流被回報「容易誤操作」「找不到」「看不懂」

## 審查維度（5 大）

### 1. 防誤觸（Trading-Critical）

破壞性操作必過 3 道閘：
- [ ] **可達性**：按鈕**不在**主要 click flow 上（例：平倉按鈕不該緊貼「查詢」）
- [ ] **二次確認**：modal 顯示具體影響（「這會關閉 BTCUSDT 0.5 倉位，預估損益 −$X」）
- [ ] **打字確認**：高破壞性（平倉全部 / 切 Live / 改 risk）需打字短語確認

| 操作 | 防誤等級 |
|---|---|
| 查詢 / 切 tab | 0 |
| 改非交易 config | 1（modal） |
| Paper / Demo 啟停 | 2（modal + Operator role） |
| 平倉單 symbol | 3（modal + 打字 symbol） |
| 平倉全部 / 切 Live / 改 risk_config | 4（雙 actor + 打字 + cooldown ≥30s） |

### 2. 認知負荷（Information Density）

- [ ] **單頁 ≤ 7 個關注點** — 超過必拆 sub-tab 或 collapsible section
- [ ] **數字成組**：相關 metric 視覺成組（PnL/Drawdown/Sharpe 同組；不 random scatter）
- [ ] **顏色語義一致**：紅=風險上升/虧損，綠=盈利，黃=注意，藍=中性
- [ ] **表格 ≤ 10 行 default**，分頁/虛擬滾動處理長 list
- [ ] **時間區雙標**：UTC + local 同列（不只 local 不只 UTC）

### 3. 錯誤狀態（Failure Modes）

每個非 GET 操作必處理 4 種狀態：
- [ ] **網路斷**：banner「重試」+ 操作 queue（不直接吃掉用戶輸入）
- [ ] **後端拒絕**：顯示 reason（authorization 過期 / lease 不存在 / 角色不夠 / 風控拒）+ 修復連結
- [ ] **超時**：> 3s 顯 spinner + 5s 顯「仍在處理…」+ 10s 顯「請聯絡 operator」
- [ ] **fail-closed 訊息**：明確標「操作未執行」（vs 「不確定」）

### 4. 一致性（Consistency）

- [ ] 同類動作 button 在所有 tab 位置一致（如「平倉」永遠右下角紅）
- [ ] icon 全 GUI 統一（同義不換）
- [ ] keyboard shortcut 不衝突（`Esc` 永遠關 modal）
- [ ] 「Live」「Demo」「Paper」永遠在右上角醒目區，顏色固定（Live=紅金 / Demo=橙 / Paper=藍）

### 5. 可審計（Audit-Aware UX）

- [ ] 每個寫操作 UI 旁顯示「最近 5 次：actor + ts + 結果」
- [ ] 操作完成 toast 含 trace_id（用戶可帶去問 operator）
- [ ] 表格匯出 footer 含 commit sha + 採集時間
- [ ] 「角色」標識（viewer / researcher / operator）永遠可見

## OpenClaw 特定 UX 紅旗

- [ ] 顯示「成功」但 backend fail-open（fake-success）→ 拒絕通過
- [ ] paper / demo / live 控制混在同 tab → 拒絕（必拆或大色塊區隔）
- [ ] Live 操作沒有 Operator role 重認 → 拒絕
- [ ] 沒有「engine_alive」狀態橋接顯示 → 拒絕（Mac 端尤其要顯，因 watchdog 永遠回 false）
- [ ] 沒有「採集時間」footer 的 dashboard（無法判斷數據是否 fresh）

## 工作流（4 步）

1. **動手用 1 次** — Read 完代碼後實際操作所有 click flow（記錄阻力點）
2. **5 維度逐項** — 表格化打勾 + 證據（截圖 / 檔:行）
3. **對抗性測試** — 「如果 op 凌晨 3 點睡眼惺忪，會誤觸什麼？」「如果 backend 突然慢 10s 會怎樣？」
4. **產出報告** — `docs/CCAgentWorkSpace/A3/workspace/reports/YYYY-MM-DD--<feature>_ux.md`

## 評級

- **A**：5 維度全綠 + 0 紅旗
- **B**：≤2 黃 + 0 紅旗
- **C**：≥1 紅旗或 ≥3 黃，需修才能上 Live
- **F**：fake-success / paper-live 混 / Operator 缺失 → 阻 merge

## 輸出格式

```markdown
# A3 UX 審查 — <feature> · <date>

範圍：<files / URL>
評級：A / B / C / F

## 5 維度
| 維度 | 狀態 | 證據 |
|---|---|---|
| 防誤觸 | ✅/⚠️/❌ | <具體> |
| 認知負荷 | | |
| 錯誤狀態 | | |
| 一致性 | | |
| 可審計 | | |

## 紅旗（必修）
1. ...

## 建議改善
1. <具體 + file:line>

## 阻力點實錄
（操作流程中卡住 / 困惑的位置）
```
