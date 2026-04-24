# PM Memory — 工作記憶

## 項目狀態快照（2026-03-31）

- 測試基準：2610 passed / 18 pre-existing failed（Wave 5 全部完成後）
- 安全狀態：0 CRITICAL / 0 HIGH / 2 MEDIUM / 3 LOW
- 系統模式：demo_only，live_execution_allowed = false
- 完成里程碑：Wave 0-5 全部完成（Sprint 0+5a+5b + Wave 5a Position Sizing + Wave 5b Paper/Demo 同步）

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

## Sprint 5b 派發狀態（2026-03-31）

- 測試基準：2594 collected（Sprint 5a 後確認）
- Sprint 5b 目標：≥ 2600 passed
- 三流並行：E1-Gamma（5b-1→5b-2/6）‖ E1-Delta（5b-3→5b-4）‖ E4（5b-5）
- E1-Gamma 負責：strategist_agent.py H4 validate_output + layer2_cost_tracker.py 三個新方法
- E1-Delta 負責：main_legacy.py apply_ai_consultation 廢棄 + scout_worker.py 新建
- E4 直接：test_h_chain_integration.py 原則 14 集成測試

**關鍵決策（代碼審計確認）**：
- `_ai_evaluate()` 已有 JSON parse error 處理，H4 是在 json.loads 成功後插入的顯式驗證層
- `apply_ai_consultation` 不直接接入 _handle_intel（語義不同），改為廢棄+指向 /phase2/strategist/intel-log
- ScoutWorker 使用 `_stop_event.wait(interval)` 而非 `sleep`，支持快速 stop() 響應
- 所有三個 cost_tracker 新方法必須含 `roi_basis: "paper_simulation_only"`（CC 原則 10）

**記住**：5b-3 apply_ai_consultation 保留兼容性，不刪除函數，調用點 :5082 必須繼續通過測試

## Wave 5 完成狀態（2026-03-31 最終確認）

- **Sprint 0**：+6 tests（d57ed05）— G-05 acquire_lease + G-01 AI daily cap
- **Sprint 5a**：+33 tests（ccdff73）— H1 ThoughtGate + H0 blocking + shadow=False + H2 預算 + H3 ModelRouter
- **Sprint 5b**：+16 tests（9478c00）— H4 validate_output + H5 CostLogger + ScoutWorker + 原則14集成測試
- **Wave 5a Position Sizing**：3% risk/trade + 25 symbols + 動態 qty + Portfolio Rebalancer（8223eb9）
- **Wave 5b Paper/Demo 同步**：止損同步 + DIVERGED 標記 + 對賬引擎首次真正運行（f6ae91e 含）
- **測試基準**：2610 passed / 18 pre-existing failed

## 下一步工作安排（Wave 5 後）

**優先 1（建議下一 Sprint）**：Phase 1 Batch 1B
  - Cooldown 聯動端到端 smoke test（E4 + PA，2h）
  - H0Gate freshness 狀態 API 端點（E1，3h）
  - GUI H0 狀態卡片（E1a，2h）
  - 工作鏈：PA確認 → E1+E1a並行 → E2 → E4

**優先 2（可分批）**：P2 批次選擇性
  - P2-6/7/8 風控覆蓋補強（E1+E4，6h）
  - P2-12/15 pipeline_bridge 邊界（E1+E4，4h）

**優先 3（~10天）**：Phase 2 回測引擎 MVP
  - 前置：Batch 1B + Paper Trading ≥ 100 筆記錄

**長期**：21 天 Paper Trading 觀察期 → M 章 Live 前置條件核驗

## 主要風險記錄（Wave 5 後）

- R1 HIGH：策略無 alpha（RSI/MACD/MA 未回測），Phase 2 回測引擎是根本解
- R2 MED：Perception Plane register_data() 生產路徑仍零調用
- R3 LOW：Cooldown 聯動端到端尚未 smoke test（Batch 1B 第一項解決）
- R4 LONG：Live 距今最快 5-6 週（Phase 1+2 + 21天觀察）

## Wave 6 派發計劃摘要（2026-03-31）

### Sprint 安排
- **Sprint 0（TD-1，P1，2h）**：pipeline_bridge `_process_pending_intents()` line 695 補入 `acquire_lease()`，E1-Alpha，目標 ≥ 2615 passed
- **Sprint 1a（FA-7，3h，Sprint 0 後）**：pipeline_bridge `_check_stops()` 止損成功後補入 `register_data()`，E1-Beta，目標 ≥ 2620 passed
- **Sprint 1b（Batch 1B，5.5h，可與 1a 並行）**：E4 cooldown smoke test + E1-Gamma freshness API + TD-3/TD-4 清理，目標 ≥ 2630 passed
- **Sprint 2（P2 批次，~20h，1a+1b 後）**：P2-6/7/8 + P2-12/15 + TD-2 + FA-8，目標 ≥ 2650 passed

### 關鍵技術決策
- `_governance_hub=None` 時不 fail-closed（跳過 lease 直接 submit，向後兼容）
- Sprint 0 和 1a 強制順序（同文件 pipeline_bridge.py，避免 merge 衝突）
- M-of-N、P3 GUI 術語繼續推遲

### 測試目標
| Sprint | 目標 |
|--------|------|
| Sprint 0 | ≥ 2615 |
| Sprint 1a | ≥ 2620 |
| Sprint 1b | ≥ 2630 |
| Sprint 2 | ≥ 2650 |

## 報告索引

| 日期 | 報告類型 | 文件位置 |
|------|---------|---------|
| 2026-03-31 | Wave 5 B 方案計劃 | workspace/reports/2026-03-31--wave5_plan_b_multiagent.md |
| 2026-03-31 | Wave 5 最終派發計劃（Sprint 0+5a+5b 結構） | workspace/reports/2026-03-31--wave5_final_dispatch.md |
| 2026-03-31 | Sprint 5a 詳細派發計劃 | workspace/reports/2026-03-31--sprint5a_dispatch.md |
| 2026-03-31 | Sprint 5b 詳細派發計劃 | workspace/reports/2026-03-31--sprint5b_dispatch.md |
| 2026-03-31 | Wave 5 完成進度報告 + 下一步安排 | workspace/reports/2026-03-31--wave5_completion_progress_report.md |
| 2026-03-31 | Wave 6 正式派發計劃（Sprint 0~2）| workspace/reports/2026-03-31--wave6_dispatch.md |

## 2026-04-24 TODO.md 全面 Audit（PM 視角）

### 關鍵發現

1. **edge_estimates.json 與 CLAUDE.md 嚴重不符**
   - CLAUDE.md 宣稱 162 cells，實際僅 1 cell（ORDIUSDT grid）；mtime 2026-04-20 23:50（4 天前）
   - **影響**：P0-14 / EDGE-DIAG-1 / P1-14 等 4 個 TODO 的前提認知全有誤差
   - **行動**：Linux operator 此週驗證產能原因（假說 A:僅 ORDIUSDT 跑 / B:scheduler crash / C:JSON 寫入 bug）

2. **被動等待 TODO 缺乏自動化監控**
   - P0-2 21d demo、P1-7 C 訓練資料兩項關鍵被動等待無 explicit healthcheck 引用
   - **行動**：補 healthcheck 登記；P0-2 應有 demo-alive check，P1-7 C 應有 automated trigger 判「何時達 200」

3. **counterfactual_exit_replay 失敗風險（HIGH）**
   - EDGE-DIAG-1 §3 item #3 須在 Linux 驗證「phys_lock 開了會贏嗎」
   - **影響**：若答案 NO，DUAL-TRACK Phase 1-3 整體架構需重評，Live 延遲 2-4 週
   - **行動**：此週優先運行 counterfactual_exit_replay.py，開決策會

4. **DUAL-TRACK-EXIT-1 與日常 P0/P1 混編導致視覺混亂**
   - DUAL-TRACK 本身結構優秀（Step 0 + Phase 1-4 + QA 守衛），但 50+ sub-TODO 與 P0/P1 交織
   - **建議**：應分離為「Live 路徑」+ 「當週活躍工作」+ 「主軸 DUAL-TRACK」+ 「邊界增強」四個視圖（見審計報告§六）

5. **多 Agent 協作議題散落，無統整 TODO**
   - ExecutorAgent shadow→live 切換、層 2 推理循環、Conductor 實作均無 TODO
   - **行動**：新增「G-1/R-06 多 Agent 全連接」專項 P2 TODO

### 風險優先級（此週必解）

| 優先級 | 項目 | 估時 | Owner |
|---|---|---|---|
| **P0** | 驗證 edge_estimates 產能 + RCA | 1h | Linux op |
| **P0** | 運行 counterfactual_exit_replay + 決策會 | 4h | Linux op |
| **P1** | 補 P0-2 clock healthcheck | 2h | PM/E1 |
| **P1** | 驗證 P1-7 C pooled label 改進已部署 | 1h | E1 |
| **P2** | 重構 TODO.md 視圖（新分類方案） | 2h | PM |

### TODO.md 健康度評分

- **優先級分層**：8.5/10（P0/P1/P2/P3/P4 清晰，依賴映射完整）
- **依賴關係**：7.5/10（邏輯正確，但 DUAL-TRACK 混編降低可視性）
- **被動等待監控**：6/10（healthcheck 80% 登記，但 P0-2/P1-7 缺引用）
- **4 大議題覆蓋**：Edge 85/ 頻率金額 65 / 虧損 90 / AI-ML 75（整體 78/100）

### 決策記憶

- **不改 TODO 內容**，待 operator 根據 P0 兩項風險決策後再重構
- **此週關鍵動作**：edge_estimates 產能確認 + counterfactual replay 運行 + healthcheck 補登
- **Live 時間保守估計**：若 counterfactual PASS，W24 末；若需重評，延至 W26

