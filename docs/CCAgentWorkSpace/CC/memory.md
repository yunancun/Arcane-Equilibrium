# CC Memory — 工作記憶

## 合規狀態快照（2026-04-01）

- 合規評級：A- 級（14/16 完全合規，2/16 部分合規，0/16 未實施）
- 部分合規：原則 12（L5 元學習未實施，L1-L4 已完成）/ 原則 15（Conductor dispatch 未完成）
- 硬違規：0 項（3/31 的 Guardian=None pass-through 已修復）
- 硬邊界：6/6 全部合規

### 3/31 → 4/01 主要升級
- 原則 4：75%→95%（Guardian=None fail-closed + H0 Gate blocking）
- 原則 8：70%→85%（register_data 注入 + round_trip 補完）
- 原則 12：40%→70%（L3 ExperimentLedger + L4 EvolutionEngine）
- max_retries：1→0（ollama_client.py 硬邊界對齊）
- GOVERNANCE_ENABLED env var：已移除

## 重要合規事項

### 原則 3 的特殊情況（2026-03-31）
- H1-H5 斷開意味著目前每筆交易**繞過了 AI 治理層**
- 但 H0 Gate + GovernanceHub fail-closed 保持了基本安全
- Wave 5 接通 H1-H5 後，需要 CC 重新確認原則 3 真正落地

### OPENCLAW_GOVERNANCE_ENABLED 已移除（Wave 2）
- 原有環境變量可以禁用治理層，已在 Wave 2 P1-2 中移除
- **記住**：治理不可通過環境變量禁用，這是硬原則

### 原則 14 的 OpenClaw 風險
- OpenClaw Gateway 成為單點故障 = 違反原則 14
- PA 決定：OpenClaw 作為 sidecar，MessageBus 保留主通信通道
- **記住**：審查 Wave 5 計劃時，確認 OpenClaw 故障不影響交易路徑

## 審查教訓

- 合規審查不能只看「功能實現了」，要看「安全不變量是否在所有路徑下保持」
- 新功能的邊界路徑（崩潰、超時、None 注入）最容易出合規問題

## Wave 5 審查關鍵發現（2026-03-31）

### G-05 ExecutorAgent 缺 Decision Lease（原則 3 硬違反）
- executor_agent.py 第 281 行：submit_order() 前未調用 acquire_lease()
- Guardian 批准 ≠ Decision Lease（兩者是不同語義的控制機制）
- **必須在 Strategist shadow=False 之前修復**（Sprint 5a 前置條件）
- 修復方案：ExecutorAgent._execute_order() 插入 acquire_lease()，失敗 fail-closed REJECT

### G-01 每日硬上限 $15.0 vs DOC-08 §4 規定 $2.00（原則 5 + DOC-08 安全不變量違反）
- layer2_types.py 第 58 行：DEFAULT_DAILY_HARD_CAP_USD = 15.0（錯誤）
- tab-ai.html 第 335/426/441 行：預設值 15 同步錯誤
- **CC 立場：$2.00 是正確值，必須修正。Sprint 5a commit 時同步提交。**

### 原則 6 需明確 H1 timeout 行為
- Sprint 5a 實現 H1 ThoughtGate 時，Ollama 超時後的行為必須是走 _heuristic_evaluate()
- 不可 allow-all（違反失敗默認收縮原則）

### 原則 10 AI ROI 認知誠實問題
- cost_edge_ratio / AI ROI 基於 paper PnL（模擬值）
- Sprint 5b 修復：API 回應添加 roi_basis: "paper_simulation_only" 標記

### Wave 5 整體評級：條件通過
- G-01 + G-05 兩個 BLOCKER 修復後可啟動
- 預期評級改善：B → A-（Wave 5 全部完成後）

## 代碼事實修正（2026-03-31 主 Claude 代碼驗證後）

### B-MVP-1 修正：produce_intel() bus.send 已實現（CC 審查報告有誤）
- CC 報告曾說「Scout→Strategist 情報路徑是死代碼，produce_intel() 只存本地列表，未 bus.send」— **此結論錯誤**
- 實際代碼（multi_agent_framework.py:428）：`if self.bus and relevance_score >= self.config.relevance_threshold: self.bus.send(msg)`
- ScoutAgent 初始化時傳入 `message_bus=MESSAGE_BUS`，bus 不為 None
- relevance_threshold = 0.3，pipeline_bridge 調用時傳入 relevance_score 最低 0.4（vol_ratio > 2.0 時）
- Strategist 已訂閱：`MESSAGE_BUS.subscribe(AgentRole.STRATEGIST, STRATEGIST_AGENT.on_message)`
- **結論**：B-MVP-1 完整鏈路已存在。5a-1 是驗證任務，不是實現任務（約 1h，非 2h）
- **教訓**：CC 審查必須實際讀代碼驗證，不可僅憑架構圖推斷「死代碼」

## 報告索引

| 日期 | 報告類型 | 文件位置 |
|------|---------|---------|
| 2026-04-01 | 全系統合規報告（A-級） | docs/audit/April01/CC_compliance_check_2026-04-01.md |
| 2026-03-31 | 全系統合規報告（B 級） | docs/audit/March31/CC_compliance_check_2026-03-31.md |
| 2026-03-31 | Wave 5 B 方案合規審查 | workspace/reports/2026-03-31--wave5_compliance_review.md |
