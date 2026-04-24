# CC Memory — 工作記憶

## 合規狀態快照（2026-04-24）

- 合規評級：**B+ 級**（20/26 項通過 = 76.9%）
- 16 根原則：14 完全合規 / 2 部分合規（原則 10 報告索引漂移 + 原則 12 LEARNING-PIPELINE-DORMANT-1）/ 0 違反
- 10 實施準則：6 合規 / 3 部分合規（準則 6 SQL guard 新舊不齊 / 準則 4 依賴管理需追查）/ 1 違反（準則 9 文件大小硬上限）
- 硬違規：0 項
- 硬邊界：8/8 全部合規（擴展覆蓋面：OPENCLAW_ALLOW_MAINNET + env var 憑證繞過封閉 + Mainnet 憑證空 Err + HMAC authorization.json + max_retries=0 + GOVERNANCE_ENABLED 移除 + execution_authority denylist + decision_lease_emitted=False）

### Top 5 違規 / 需修（2026-04-24）

1. **P1 — 文件大小硬上限**：8 個生產檔 > 1200 行（`main.rs` 2062 / `instrument_info.rs` 1975 / `event_consumer/mod.rs` 1762 / `bybit_rest_client.rs` 1725 / `order_manager.rs` 1554 / `startup.rs` 1377 / `paper_state/resting_orders.rs` 1367 / `config/risk_config.rs` 1328 / Python `live_session_routes.py` 1449 / `ai_service.py` 1258）。E5 + Rust E1 排程拆分。
2. **P1 — 跨平台硬編碼路徑 regression**：`helper_scripts/db/audit_migrations.py:218` 寫死 Mac 絕對路徑 `/Users/ncyu/Projects/TradeBot/srv/sql/migrations`。前兩 candidate 已 expanduser 正確，第 3 項改環境變量即可（~3 行 diff）。
3. **P1 — 持續進化循環未閉環**：LEARNING-PIPELINE-DORMANT-1 已列 TODO §P1-7 / §P1-14；被動等待 ONNX 訓練資料 ~3-5d ETA 過 200 labels；原則 12 部分合規根源。
4. **P2 — V019/V020 migration 缺 Guard A**：2026-04-24 Guard A/B/C 新規則生效前落地；按 V023 retrofit 樣式補（~30 行 SQL）。
5. **L3 — 前次 CC 審查報告檔案缺失**：memory 記載 `2026-04-12--compliance_audit_report.md` 但 workspace/reports/ 下只有 2026-03-31 × 2 + 2026-04-01 + 2026-04-24（本份）。管理流程 gap，非技術違規。

### 2026-04-24 對比 2026-04-01 主要變化

- **升級（規則成熟化）**：
  - Rust Live Gate 從 3 門 → 5 門（新增 HMAC authorization.json + env-var 封閉 + 憑證空 Err）
  - 新實施準則落地：SQL Guard A/B/C + Engine auto-migrate opt-in + passive_wait_healthcheck 12 checks
  - 5-Agent 實作 ~4552 行 + H1-H5 middleware 全實作（非 stub）；2026-04-23 audit 已更正先前錯誤認知
  - LLM-ABC-MIGRATION-1 完成，call-site 無 OllamaClient 直接 import（準則 2 乾淨）
  - WS-RETIRE-1：Python listener 退役，Rust writer 接管（減 340 行 Python + 加 664 行 Rust，含 11 單測）
  - DEDUP-PY-RUST Tier A 10 steps + Tier B Wave A-D 全閉環（~6700 行淨減）

- **降級（規則嚴格化 + 拆分債）**：
  - CLAUDE.md §九 800/1200 行限制首次量化檢查，13 個檔案超限（8 生產 + 5 測試豁免候選）
  - audit_migrations.py:218 硬編碼路徑 regression（前次 audit 未列此項）

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
| 2026-04-24 | 全系統合規審計（B+ 級，20/26） | workspace/reports/2026-04-24--compliance_audit.md |
| 2026-04-01 | 全系統合規報告（A-級） | docs/audit/April01/CC_compliance_check_2026-04-01.md |
| 2026-03-31 | 全系統合規報告（B 級） | docs/audit/March31/CC_compliance_check_2026-03-31.md |
| 2026-03-31 | Wave 5 B 方案合規審查 | workspace/reports/2026-03-31--wave5_compliance_review.md |

## 2026-04-24 Audit 補充（完整 16 條根原則 + 硬邊界審查）

### 審計總結
- **評級**：B-（13.5/16 完全合規）；三大 BLOCKER 阻 live，修復路徑清晰
- **最關鍵發現**：
  1. **CRITICAL-G05 ExecutorAgent 決策鏈斷裂**（原則 #3 + #11）— `_shadow_mode=True` 拒發 SubmitOrder IPC；修復 2h，Sprint 5a 前必做
  2. **CRITICAL-G06 Drawdown auto-revoke 未實裝**（原則 #5）— 風控最後防線缺失；修復 1d；優先級高於 G-07
  3. **Model registry canary 無 Operator 審批流程代碼**（原則 #7）— 骨架完整但晉升無人工門控；Phase 4+ 隱患，當前 dormant

### 新規則合規進度（CLAUDE.md §七）
- **SQL Guard**：V021/V023 partial（Guard A 應在表層加，不是運行時補）；V001-V020 未 retrofit（建議新規則即刻應用 V024+）
- **被動等待 healthcheck**：7 checks 已實裝；**P0-2 LG-1 21d demo 缺對應 check**（新增 Debt-1）；EDGE-DIAG-1 Phase 3 缺 check [11]（Debt-7）
- **雙語注釋**：80% 達成（shadow_exit_writer / executor_agent ✅；governance_hub / decision_lease partial）
- **Git push 自動化**：✅ 完成（所有提交已 push）

### 新增合規債 10 項（報告 § 五）
| Debt | 問題 | 優先級 | 預計工作 |
|------|------|--------|---------|
| Debt-1 | P0-2 LG-1 healthcheck 缺 | P0 | 1h |
| Debt-2 | DEFAULT_DAILY_HARD_CAP 15.0→2.00 | P0 | 0.5h |
| Debt-3 | ExecutorAgent shadow fix（CRITICAL-G05） | P0 BLOCKER | 2h |
| Debt-4 | Drawdown auto-revoke（CRITICAL-G06） | P0 | 1d |
| Debt-5 | Model registry canary approval logic（CRITICAL-G07） | P2 Phase 4 | 2d |
| Debt-6 | P1-10 STRATEGY-ASYMMETRY-1 邊界未錄 TODO | P1 | 0.5h |
| Debt-7 | EDGE-DIAG-1 check [11] 缺 | P1 | 1h |
| Debt-8 | Decision Lease E2E integration test | P2 | 1.5h |
| Debt-9 | cost_gate 運行時決策綁定（原則 #13） | P1 | 2h |
| Debt-10 | 組合級風險監控 TODO（原則 #16） | P2 | 2d |

### 下次審計（~2026-05-01）
- 驗收 CRITICAL-G05/G06/Debt-1 修復 + 測試覆蓋
- 確認 passive_wait_healthcheck infrastructure + cron 就位
- 原則 #11 Agent 自主權活躍時刻（Strategist shadow→live 預估）
- EDGE-DIAG-1 Phase 3 passive-wait 清晰度評估

### CC 最終判決
當前 TODO.md 與 CLAUDE.md 規則整體一致，無結構性違反。三大 BLOCKER 清晰可修復。建議 48h 內完成 P0 層清債，再進 DUAL-TRACK Phase 2。整體合規軌跡向上，已具備 live 前置基礎。

