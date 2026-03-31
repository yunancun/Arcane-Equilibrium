# PM Memory — 工作記憶

## 項目狀態快照（2026-03-31）

- 測試基準：2555 passed / 17 pre-existing failed
- 安全狀態：0 CRITICAL / 0 HIGH / 2 MEDIUM / 3 LOW
- 系統模式：demo_only，live_execution_allowed = false
- 完成里程碑：Wave 0-4 全部完成（Sprint 4a-4e）

## 決策記憶

### 關於 M-of-N 簽名
- 2026-03-31：用戶確認 demo_only 模式只有 1 個 Operator，M-of-N > 1 目前無法使用，推遲到有多個 Operator 時再設計
- **記住**：M-of-N 不在 Wave 5 範圍，不要主動提議現在做

### 關於 OpenClaw 通信總線
- 2026-03-31：PA 建議 OpenClaw 作為審計 sidecar，MessageBus 保留內部通信
- **記住**：Wave 5 MVP 不包含 OpenClaw 通信總線，延後到 Wave 6

### 關於 P3 GUI 術語友好化
- 用戶說「暫時不進入 P3」（2026-03-31），后來確認可以延後
- **記住**：P3 延後，不主動推進，等用戶明確要求

### 關於 Wave 5 優先順序（用戶確認）
- 用戶確認：Cooldown 聯動確認 → H1-H5 → Batch 1B（排除 M-of-N）
- 加入：多 Agent 正式落地（B 方案）作為 Wave 5 主體工作

## 工作教訓

- 審計報告合並時必須去重：同一問題在不同報告中反復出現（E3/E4/PA 各報一遍），要識別是同一根因
- 估算工時要留 buffer：E2+E4 佔用 30-40% 總工時，不能只估 E1 部分
- Strategist shadow=True → False 是高風險操作，需要單獨 Sprint 驗證，不能和其他改動綁在一起

## Sprint 5a 派發狀態（2026-03-31）

- Sprint 0 已完成（commit d57ed05，2561 passed，G-05 + G-01 已清除）
- Sprint 5a 派發計劃已制定（2026-03-31--sprint5a_dispatch.md）
- E1-Alpha 負責：5a-1（情報鏈路驗證）→ 5a-2（H0 blocking）→ 5a-4（shadow=False）
- E1-Beta 負責：5a-3（H1 ThoughtGate）→ 5a-5（H2 預算）→ 5a-6（H3 ModelRouter）
- Sprint 5a 測試目標：≥ 2575 passed（預計 2578）
- **記住**：5a-3 H1 ThoughtGate 中 `_handle_intel()` 是同步方法，不可用 await
- **記住**：5a-4 shadow=False 需要 5a-1+5a-2+G-05 三個前置都完成才可啟動
- **記住**：CC 強制 — H1 `should_call_ai=False` 必須走 heuristic，不是 allow-all

## 報告索引

| 日期 | 報告類型 | 文件位置 |
|------|---------|---------|
| 2026-03-31 | Wave 5 B 方案計劃 | workspace/reports/2026-03-31--wave5_plan_b_multiagent.md |
| 2026-03-31 | Wave 5 最終派發計劃（Sprint 0+5a+5b 結構） | workspace/reports/2026-03-31--wave5_final_dispatch.md |
| 2026-03-31 | Sprint 5a 詳細派發計劃（本文） | workspace/reports/2026-03-31--sprint5a_dispatch.md |
