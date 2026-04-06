# CC 項目合規檢查報告

**生成時間：** 2026-03-31
**審查員：** CC (Compliance Checker)
**系統：** BybitOpenClaw AI 自動交易系統
**代碼基線：** Phase 0 Round 2.5 審計後（2,227 tests passed / 0 failed）

---

## 執行摘要

| 類別 | 數量 |
|------|------|
| 16 條根原則 — 完全合規 | **11 / 16** |
| 16 條根原則 — 部分合規 | **4 / 16** |
| 16 條根原則 — 未實施 | **1 / 16** |
| 發現違規項（硬違規） | **1 項** |
| 發現合規缺口（部分實施） | **9 項** |
| MODULE_NOTE 合規率 | **44/54 = 81.5%** |
| 文件命名合規率（docs/）| **部分不合規（詳見第五節）** |

**整體合規評級：** B（良好，生產前須修復 1 項硬違規 + 4 項重要缺口）

---

## 一、16 條根原則合規矩陣

| # | 原則 | 實現狀態 | 合規度 | 主要實現位置 | 問題/缺口 |
|---|------|---------|--------|------------|---------|
| 1 | 單一寫入口 | ✅ 已實施 | 90% | `pipeline_bridge.py:620`、`paper_trading_engine.py:1005` | Guardian 為 None 時不阻塞（見第二節 #1） |
| 2 | 讀寫分離 | ✅ 已實施 | 85% | `data_source_enforcer.py`、`main_legacy.py:STORE` | GUI 無直接寫入路徑；GUI Tab 不含 POST 寫操作 |
| 3 | AI 輸出 ≠ 即時命令 | ✅ 已實施 | 90% | `decision_lease_state_machine.py`、`shadow_decision_builder.py:173` | Decision Lease 9 態全實施；shadow only confirmed |
| 4 | 策略不能繞過風控 | ⚠️ 部分合規 | 75% | `pipeline_bridge.py:519` Guardian gate | Guardian 為 None 時策略可直接進入 submit_order（缺口，見第二節 #1） |
| 5 | 生存 > 利潤 | ✅ 已實施 | 95% | `risk_manager.py:977-995`、`governance_hub.py:523` | session_halted 回撤熔斷；fail-closed 雙重實施 |
| 6 | 失敗默認收縮 | ✅ 已實施 | 90% | `guardian_agent.py:177-189`、`pipeline_bridge.py:582-593`、`governance_hub.py:544-562` | 所有異常路徑 fail-closed；GovernanceMode.FROZEN 自動拒絕 |
| 7 | 學習 ≠ 改寫 Live | ✅ 已實施 | 90% | `layer2_engine.py:89,106`、`learning_tier_gate.py` | L2 engine system prompt 明確標記 read_only；LearningTier L1-L5 單向進化 |
| 8 | 交易可解釋 | ⚠️ 部分合規 | 70% | `trade_attribution.py`、`decision_lease_state_machine.py`、`change_audit_log.py` | 歸因引擎存在但 Perception Plane register_data 來源標記未完全覆蓋（見第二節 #2） |
| 9 | 交易所災難保護 | ✅ 已實施 | 90% | `protective_order_manager.py:37-39`、`risk_manager.py` | 硬止損不可禁用（MODULE_NOTE 明確）；ATR 動態距離；雙重防線 |
| 10 | 認知誠實 | ✅ 已實施 | 85% | `perception_data_plane.py:29-58`、`data_source_enforcer.py:41-64`、`multi_agent_framework.py:54-58` | DataQualityLevel / CognitiveLevel 三級標記；DataSourceEnforcer 自動分類 |
| 11 | Agent 最大自主權 | ✅ 已實施 | 80% | `scanner_rate_limiter.py`、Scout 650 符號掃描、`strategist_agent.py` | P0/P1 邊界已實施；Agent 自主選幣/策略/時機；但 alpha 驗證缺失（見第三節） |
| 12 | 持續進化 | ⚠️ 部分合規 | 40% | `learning_tier_gate.py`、`layer2_engine.py`、`trade_attribution.py` | L1/L2 學習管線存在；L3-L5 尚未實施；策略無自動優化（見第二節 #3） |
| 13 | AI 資源成本感知 | ✅ 已實施 | 85% | `risk_manager.py:960-975`、`layer2_cost_tracker.py`、`risk_manager.py:301` | cost_edge_ratio ≥ 0.8 建議關倉已實施；每日硬上限 $15；但 Ollama 成本固定 0.0（正確） |
| 14 | 零外部成本可運行 | ✅ 已實施 | 95% | `ollama_client.py:48`（DEFAULT_MODEL = qwen3.5:9b）、`layer2_types.py` | L0+L1 本地路徑已驗證；9B 1.9s / 27B 9.9s；fallback 機制完整 |
| 15 | 多 Agent 協作 | ✅ 已實施 | 80% | `multi_agent_framework.py:619-667`、`phase2_strategy_routes.py:167,211,244,505` | 5 Agent 已接入 MessageBus；Conductor 已實現 register_agent；但 Conductor 自動編排尚待完善 |
| 16 | 組合級風險意識 | ✅ 已實施 | 80% | `portfolio_risk_control.py:52-57`、`risk_manager.py` | 相關係數矩陣（0.7 閾值）；行業集中度限制；30% 保留緩衝；但 AI 內容中策略重疊分析尚缺 |

---

## 二、原則違反項詳情（1 項硬違規 + 相關缺口）

### 違規 #1：原則 4 部分違反 — Guardian 為 None 時策略可繞過風控

**文件：** `pipeline_bridge.py:519`
**代碼位置：**
```python
# line 519-519
if self._guardian_agent:
    # ... Guardian 審查 ...
    # 若 verdict == REJECTED → continue
    # 若 Guardian 拋出異常 → fail-closed continue
else:
    # 無 Guardian 時：直接進入 submit_order()（line 620）
    # 無任何阻止
```

**違反描述：** 當 `self._guardian_agent is None`（未注入或未啟動）時，`process_pending_intents()` 跳過整個 Guardian gate，直接在第 620 行調用 `self._engine.submit_order()`。注釋在第 514 行聲稱"Guardian 不可用 → REJECTED（fail-closed）"，但代碼實際行為是跳過（pass-through），而不是拒絕。

**風險等級：** 高
**觸發條件：** 服務啟動時 `set_guardian_agent()` 未被調用，或 GuardianAgent 被設置為 None
**建議修復：**
```python
# 應改為：
if self._guardian_agent is None:
    logger.error("Guardian unavailable — fail-closed REJECT all intents / Guardian 不可用 — 拒絕所有 intent")
    with self._lock:
        self._stats["intents_rejected"] += 1
    continue
```

---

## 三、合規缺口（部分實施）（9 項）

### 缺口 G1：H0 Gate 確定性門控缺失（原則 1/4）
**嚴重程度：** P0（Live 前必須）
**位置：** `tab-live.html:83-84` — GUI 已標記"Phase 1 最高優先"但未實施
**描述：** DOC-02 要求 <1ms 確定性本地門控（健康度、新鮮度、風險包絡三合一）。現有 `governance_hub.is_authorized()` 有 TTL=100ms 緩存，勉強滿足，但缺少 DOC-02 指定的獨立 <1ms 本地判斷內核（`bybit_local_*` 系列腳本存在但未接入運行時）。
**根本原因：** `bybit_local_risk_envelope_gate.py`、`bybit_local_judgment_final_audit.py` 等 H0 組件以批處理腳本形式存在，未整合為實時調用的 gate。

### 缺口 G2：持續進化缺失（原則 12）
**嚴重程度：** P1
**位置：** `learning_tier_gate.py`，L3-L5 等級
**描述：** L3（假說實驗）、L4（策略進化）、L5（元學習）尚未實施。系統當前處於 L1/L2，策略參數無自動優化機制。`strategy_evolution` 在 `learning_tier_gate.py` 中定義了框架但無執行路徑。

### 缺口 G3：Perception Plane register_data 零調用（原則 8/10）
**嚴重程度：** P1
**位置：** CLAUDE.md 已記錄："❌ Perception Plane register_data() 零調用"
**驗證：** `pipeline_bridge.py:338-348` — register_data 調用存在但被 `if self._perception_plane:` 保護，只在 `_perception_plane` 被注入時才調用。注入路徑存在（`phase2_strategy_routes.py:361`），但實際運行時是否覆蓋全部數據來源尚未確認。
**影響：** 交易決策的數據可解釋性（原則 8）和認知誠實（原則 10）的運行時記錄不完整。

### 缺口 G4：決策租約與 ExecutorAgent 未完全閉環（原則 3）
**嚴重程度：** P1
**位置：** `executor_agent.py`、`decision_lease_state_machine.py`
**描述：** ExecutorAgent 存在且接入了 APPROVED_INTENT → submit_order() → EXECUTION_REPORT 管線（Batch 11），但 Decision Lease 的 BRIDGED → CONSUMED 完整閉環（SM-02 §7.5）在運行時是否被觸發未在代碼中找到顯式連接點。`executor_agent.py` 的 submit 邏輯未見調用 `lease_sm.consume()`。

### 缺口 G5：max_retries 硬邊界未在 OllamaClient 強制（§六 硬邊界）
**嚴重程度：** P2
**位置：** `ollama_client.py:60`：`max_retries: int = 1`
**描述：** CLAUDE.md §六 硬邊界要求 `max_retries = 0`。OllamaClient 的默認值為 1（`max_retries: int = 1`，第 60 行；`range(1 + self._config.max_retries)` 即最多 2 次嘗試）。AI 調用路徑（`bybit_ai_invocation_attempt_builder.py:320`）中 `max_retries = 0` 強制正確，但本地 Ollama 路徑未應用相同限制。

### 缺口 G6：Conductor 自動編排未完成（原則 15）
**嚴重程度：** P2
**位置：** `multi_agent_framework.py:619-694`
**描述：** Conductor 的 `register_agent()`、`heartbeat()`、`set_agent_state()` 已實現，但自動化任務分配（`dispatch_to_agent()`）、健康檢查循環和衝突仲裁的完整實現尚未接入主管線。CLAUDE.md 記錄"Conductor 編排待完善"。

### 缺口 G7：OPENCLAW_GOVERNANCE_ENABLED 環境變量可繞過治理（§六）
**嚴重程度：** P1
**位置：** `governance_hub.py:167`
**代碼：**
```python
env_enabled = os.environ.get("OPENCLAW_GOVERNANCE_ENABLED", "true").lower() == "true"
self._enabled = enabled and env_enabled
```
**描述：** 設置環境變量 `OPENCLAW_GOVERNANCE_ENABLED=false` 可將治理完全禁用（`self._enabled = False`），導致 `is_authorized()` 恆返回 False（fail-closed）。此為 fail-closed 方向，不產生安全漏洞，但配置管理風險：若環境變量被意外設置為 false，整個治理鏈靜默失效（所有訂單被拒絕但無報警）。

### 缺口 G8：Guardian 注入時機依賴（原則 4）
**嚴重程度：** P1
**位置：** `phase2_strategy_routes.py`
**描述：** GuardianAgent 通過 `PIPELINE_BRIDGE.set_guardian_agent(GUARDIAN_AGENT)` 在模塊初始化時注入。若模塊導入順序或服務啟動失敗，可能出現短暫的 `_guardian_agent = None` 窗口期。結合缺口 G1（違規 #1），此窗口期內的 intent 會跳過 Guardian 直接提交。

### 缺口 G9：Daily Loss 跨天重置已知問題
**嚴重程度：** P2（已記錄，影響極小）
**位置：** `risk_manager.py:1018`：`# New day — reset daily start balance`
**描述：** CLAUDE.md 已知問題：RiskManager daily loss 跨天不重置。代碼中有重置邏輯（1018 行）但依賴 `check_order_allowed` 的每次調用觸發，若 session 沒有訂單則不會觸發跨日重置。影響極小（保守方向）。

---

## 四、架構合規評估

### 4.1 單一寫入口驗證

**結論：已實施，有條件性缺口**

所有訂單從兩條路徑進入，最終都通過 `PaperTradingEngine.submit_order()`：
1. `pipeline_bridge.py:620` → `self._engine.submit_order()`
2. `paper_trading_routes.py` 的 REST API → 同一 engine

`paper_trading_engine.py:1005` 的 `submit_order()` 內部串行：
- LearningTierGate 檢查（第 1032 行）
- GovernanceHub `is_authorized()`（第 1083 行）
- RiskManager `check_order_allowed()`（第 1104 行）
- 餘額充足性檢查（第 1125 行）

**唯一缺口：** `_guardian_agent is None` 時 pipeline_bridge 直接提交，但 `submit_order()` 內部的 GovernanceHub + RiskManager 仍會攔截，因此實際執行仍有第二道防線。

### 4.2 讀寫分離驗證

**結論：已實施**

- GUI 所有 Tab（tab-learning.html、tab-ai.html、tab-strategy.html 等）僅通過 GET API 讀取數據，未發現直接寫入調用。
- `DataSourceEnforcer`（`data_source_enforcer.py`）封裝外部數據源，標記 cognitive level 後才入管線。
- `main_legacy.py` 的 `STORE` 對象（StateStore）持有全局鎖，所有寫入通過 `STORE.mutate(mutator)` 序列化。

### 4.3 Decision Lease 流程驗證

**結論：已實施，運行時閉環待確認**

SM-02 的 9 態狀態機完整實現（`decision_lease_state_machine.py:53-63`）。禁止迁移表（`FORBIDDEN_TRANSITIONS`）包含 13 條明確禁止項（第 203-219 行）。`shadow_decision_builder.py:173` 確認 `execution_authority: "not_granted"` hardcoded。

**缺口：** `executor_agent.py` 執行完成後是否調用 `lease_sm.consume()` 完成 BRIDGED → CONSUMED 閉環未找到代碼證據（缺口 G4）。

---

## 五、代碼規範合規

### 5.1 MODULE_NOTE 合規率

- 總 Python 文件數（app/目錄）：**54**
- 已有 MODULE_NOTE：**44**（含雙語）
- 缺少 MODULE_NOTE：**10 個文件**

**缺少 MODULE_NOTE 的文件：**

| 文件 | 類型 | 嚴重度 |
|------|------|--------|
| `main.py` | 主入口包裝層 | Low（有說明注釋） |
| `multi_agent_framework.py` | 核心 Agent 框架 | **Medium**（核心文件） |
| `main_legacy.py` | 主業務邏輯 | **Medium**（核心文件） |
| `__init__.py` | 包初始化 | Low（通常不需要） |
| `data_source_enforcer.py` | 認知誠實執行層 | Medium |
| `scanner_rate_limiter.py` | 掃描限速器 | Low |
| `governance_events.py` | 治理事件定義 | Low |
| `main_snapshot_stable.py` | 快照穩定版 | Low（歷史遺留） |
| `runtime_bridge.py` | 運行時橋接 | Low |
| `perception_data_plane.py` | 感知數據平面 | **Medium**（核心文件） |

**重要發現：** `multi_agent_framework.py` 和 `main_legacy.py` 是兩個最大的核心文件，缺少 MODULE_NOTE 違反了 CLAUDE.md §十 新腳本規範。

### 5.2 文件命名規範合規率

**要求格式：** `YYYY-MM-DD--功能描述.md`

**不合規文件（選樣）：**
- `docs/governance_dev/phase3_integration/REVIEW_GOVERNANCE_GUI.md`（全大寫，無日期）
- `docs/governance_dev/phase4_acceptance/T4.04_R4_DOCUMENT_AUDIT_REPORT.md`（無日期前綴）
- `docs/governance_dev/changelogs/2026-03-29_T2.15_market_regime.md`（日期後使用單橫線而非雙橫線 `--`）
- `docs/governance_dev/SPECIFICATION_REGISTER.md`（無日期）
- `docs/handoffs/` 目錄下大量文件（`WORKLOG_2026-03-26.md`、`API_GUI_*.md` 等）使用不同命名格式

**docs/README.md 更新狀態：** 未完整驗證（需人工確認最新文件是否已加入索引）。

---

## 六、硬邊界合規驗證

| 硬邊界 | 狀態 | 驗證位置 | 備注 |
|--------|------|--------|------|
| `system_mode = "read_only"` | ✅ 合規 | `main_legacy.py:1117`：初始化為 `"design_only"`；無代碼路徑改為 live | 沒有任何 POST API 可修改 system_mode_fact 為 live |
| `execution_state = "disabled"` | ✅ 合規 | `main_legacy.py:1118`：初始化為 `"execution_disabled"` | `global_execution_mode_switch` 初始 `"disabled"`，無升級路徑 |
| `execution_authority = "not_granted"` | ✅ 合規 | `shadow_decision_builder.py:173`：hardcoded `"not_granted"`；`main_legacy.py:1130` | 派生字段從 SM 計算，不可直接覆寫 |
| `decision_lease_emitted = False` | ✅ 合規 | SM-02 的 DRAFT 態為起點，只有完整 governance 鏈才能進入 ACTIVE | 無旁路 |
| `max_retries = 0`（AI 調用） | ⚠️ 部分合規 | `bybit_ai_invocation_attempt_builder.py:320`：AI 調用正確為 0 | **OllamaClient 默認為 1**（`ollama_client.py:60`）— 見缺口 G5 |

**額外安全發現：** `governance_hub.py:167` 的 `OPENCLAW_GOVERNANCE_ENABLED` 環境變量可靜默禁用治理（fail-closed 方向但缺少報警）—見缺口 G7。

---

## 七、優先級序實踐評估

### 「賬戶生存 > 利潤」具體體現

**正面案例（有代碼證據）：**

1. **回撤熔斷**（`risk_manager.py:977-995`）：drawdown ≥ max_session_drawdown_pct → `session_halted = True`，直接阻止所有新訂單。
2. **fail-closed 原則貫穿所有 Agent**（`guardian_agent.py:177-189`）：Guardian 任何異常 → REJECTED，risk_score=1.0。
3. **GovernanceMode.FROZEN 快速路徑**（`governance_hub.py:523`）：FROZEN 模式下 `is_authorized()` 無需加鎖直接返回 False。
4. **硬止損不可禁用**（`protective_order_manager.py:37`）：`HARD_STOP_LOSS can never be disabled or removed before trigger`。
5. **AI 注意力稅觸發關倉**（`risk_manager.py:960-975`）：成本/邊際比超閾值時建議關倉，先判斷生存再考慮利潤。
6. **LearningTierGate 低層級阻止開倉**（`paper_trading_engine.py:1032-1034`）：L3 以下禁止自主提交訂單。

**缺失案例（應有但未確認）：**

1. 策略連續虧損自動降低倉位（原則 6 + 12）：`_auto_deployer` 有 G1 連續虧損自動退出鉤子（`pipeline_bridge.py:137`），但觸發邏輯未在此次審查中完整確認。
2. 市場極端波動期間自動降頻（原則 6）：`scanner_rate_limiter.py` 有限速器，但是否與市場 regime 聯動未確認。

---

## 八、合規改進路線圖

### P0 — 上線前必須修復

**[P0-1] 違規修復：Guardian = None 時的 pass-through 問題**
- **文件：** `pipeline_bridge.py`，`process_pending_intents()` 方法中第 519 行 `if self._guardian_agent:` 分支
- **修復方向：** 在 `else` 分支添加 fail-closed 拒絕邏輯，與注釋保持一致
- **時間：** 1 小時

**[P0-2] H0 Gate 確定性門控整合**
- **現狀：** `bybit_local_risk_envelope_gate.py` 等 H0 組件以離線腳本形式存在，未接入實時管線
- **修復方向：** 將 H0 三項判斷（freshness/health/risk envelope）封裝為 <1ms 同步函數，在 `governance_hub.is_authorized()` 之前串聯
- **時間：** 2-3 天（CLAUDE.md §十一 Phase 1 Batch 1A）

### P1 — 重要缺口

**[P1-1] Decision Lease 執行閉環確認**
- **文件：** `executor_agent.py`
- **確認點：** ExecutorAgent 完成訂單後是否調用 `governance_hub.acquire_lease()` / `lease_sm.consume()`
- **時間：** 半天審查 + 必要時補接

**[P1-2] GOVERNANCE_ENABLED 環境變量靜默禁用報警**
- **文件：** `governance_hub.py:167`
- **修復方向：** 若 `OPENCLAW_GOVERNANCE_ENABLED=false`，增加 WARNING 級別日誌並觸發 Telegram 報警（不改變 fail-closed 行為）
- **時間：** 2 小時

**[P1-3] OllamaClient max_retries 統一為 0**
- **文件：** `ollama_client.py:60`
- **修復方向：** 將 `max_retries: int = 1` 改為 `max_retries: int = 0`，或在 MODULE_NOTE 中明確說明本地模型允許 1 次重試的例外理由
- **時間：** 30 分鐘

**[P1-4] Perception Plane register_data 覆蓋率確認**
- **文件：** `pipeline_bridge.py`、`paper_trading_routes.py`
- **確認點：** 運行時 `_perception_plane` 是否被注入；是否覆蓋所有關鍵數據源（WebSocket tick、kline、AI output）
- **時間：** 半天

### P2 — 中期改進

**[P2-1] 補全缺少 MODULE_NOTE 的核心文件（6 個 Medium 級別文件）**
- 優先：`multi_agent_framework.py`、`main_legacy.py`、`data_source_enforcer.py`、`perception_data_plane.py`
- **時間：** 1 天

**[P2-2] 文件命名規範補齊**
- `docs/governance_dev/` 和 `docs/handoffs/` 目錄下不符合 `YYYY-MM-DD--` 格式的文件重命名
- 更新 `docs/README.md` 索引
- **時間：** 半天

**[P2-3] Conductor 自動編排完善（原則 15）**
- 詳見 CLAUDE.md §十一 Phase 3 路線圖
- **優先級：** 非 Live 前強制

**[P2-4] 學習管線 L3-L5（原則 12）**
- 詳見 CLAUDE.md §十一 Phase 2/3 路線圖
- **優先級：** 非 Live 前強制，但為長期 Alpha 驗證基礎

---

## 附錄：主要審查文件清單

| 文件 | 審查重點 |
|------|--------|
| `governance_hub.py` | 原則 1/2/3/4/5/6，硬邊界 |
| `decision_lease_state_machine.py` | 原則 3，SM-02 完整實施 |
| `authorization_state_machine.py` | 原則 3，SM-01 完整實施 |
| `guardian_agent.py` | 原則 4/5/6，fail-closed |
| `pipeline_bridge.py` | 原則 1/4，Guardian gate，單一寫入口 |
| `paper_trading_engine.py` | 原則 1/2/3，submit_order 防線 |
| `risk_manager.py` | 原則 5/6/9/13，三層 P0/P1/P2 |
| `protective_order_manager.py` | 原則 9，交易所災難保護 |
| `multi_agent_framework.py` | 原則 15，5-Agent 協作 |
| `learning_tier_gate.py` | 原則 7/12，L1-L5 單向進化 |
| `layer2_engine.py` | 原則 3/7/13，AI 不直接執行 |
| `layer2_cost_tracker.py` | 原則 13，AI 成本感知 |
| `perception_data_plane.py` | 原則 10，認知誠實 |
| `data_source_enforcer.py` | 原則 10，數據源標記執行 |
| `portfolio_risk_control.py` | 原則 16，組合級風險 |
| `ollama_client.py` | 原則 14，零成本本地運行 |
| `paper_live_gate.py` | 原則 5/6，Paper→Live 閘門 |
| `main_legacy.py` | 硬邊界，讀寫分離，狀態機 |
| `trade_attribution.py` | 原則 8，交易可解釋 |

---

*本報告基於靜態代碼審查。運行時行為（感知平面數據流、Conductor 實際調度）需結合日誌確認。*
