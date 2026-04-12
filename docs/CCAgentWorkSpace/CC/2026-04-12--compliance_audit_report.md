# CC 合規審計報告 — 2026-04-12

**審計員**：CC（Compliance Checker）
**審計範圍**：CLAUDE.md 16 根原則 + 代碼規範 + 工作流 + 硬邊界
**審計基準**：commit `1392006`（main branch HEAD）
**測試基線**：engine lib 939 + core 366 + e2e 18 + promotion 32 = 1355 / Python 2852 passed 0 fail

---

## 一、16 根原則合規審計

### 原則 #1：單一寫入口 — ✅ PASS

**證據**：所有交易意圖統一通過 `IntentProcessor`（`intent_processor/router.rs`）處理。`process()` 用於 Paper 模式完整執行，`process_gates_only()` 用於 Exchange 模式門禁。訂單派發通過 `order_manager.rs` 的 `place_order()` 單一入口送往 Bybit API。平倉路徑統一經 `close_position_at_symbol_market()` + `emit_close_fill()`。

**發現**：`StrategyAction::Close` 路徑繞過 Guardian/cost_gate/Kelly，但這是設計意圖（降風險不增風險），且仍經 `emit_close_fill` 留完整審計紀錄。符合原則精神。

---

### 原則 #2：讀寫分離 — ✅ PASS

**證據**：Python 層在 DEAD-PY-2 後已**完全無交易邏輯**，僅剩 API 橋接 + GUI 路由 + 輔助工具。所有交易/風控參數 GUI 直寫 Rust ConfigStore（通過 IPC），Python 僅只讀。`RiskConfig` 為純派生視圖，`GuardianConfig` 無獨立狀態（`ARCH-RC1 1C-4 E-Merge-4` 明確記載）。

---

### 原則 #3：AI 輸出 ≠ 即時命令 — ✅ PASS

**證據**：`DecisionLeaseSm` 完整實現於 `openclaw_core/src/sm/lease.rs`，9 狀態 + 20 合法遷移 + 12 禁止遷移 + 5 守衛。`GovernanceCore`（`governance_core.rs`）集成 `DecisionLeaseSm`。`IntentProcessor.process()` Gate 1 即驗 `governance.is_authorized()`，未授權直接 fail-closed 返回。

**注意**：H1-H5 AI 治理層當前全為 stub（CLAUDE.md 確認），待 W22 實現。Decision Lease 機制已就位，但實際 AI→Lease→執行的端到端路徑尚未激活。

---

### 原則 #4：策略不能繞過風控 — ✅ PASS

**證據**：
- `StrategyAction::Open` → 完整治理管線：Gate 1 Governance auth → Gate 1.5 重複檢查 → **Gate 2 Guardian 4-check** → Gate 2.5 Kelly sizing → Gate 3 cost gate → Gate 4 global cap
- `process_gates_only()`（Exchange 路徑）同樣包含 Guardian review（`router.rs:332`）
- Guardian 四項檢查：方向衝突、槓桿上限、回撤限制、持倉數量
- `StrategyAction::Close` 繞過 Guardian 但只減倉不增倉（設計文檔明確標註）

---

### 原則 #5：生存 > 利潤 — ✅ PASS

**證據**：
- fail-closed 遍布代碼：`position_risk_evaluator.rs:56` entry_price=0 → -999%（強制硬止損）
- `intent_processor/gates.rs:137` 負 edge estimate → fail-closed
- `ipc_server` 未初始化時 fail-closed（-32603）
- Session halt + CloseAll 機制（`RiskAction::HaltSession`）
- Reconciler 自動降級：MinorDrift→Cautious→Defensive→CircuitBreaker+CloseAll
- H0 Gate 硬阻斷時仍處理止損（`on_tick.rs:204`："H0 BLOCKED — stops only"）
- Paper paused 時保護性止損繼續運行（`on_tick.rs:309-325`）

---

### 原則 #6：失敗默認收縮 — ✅ PASS

**證據**：
- `_EXECUTION_AUTHORITY_OVERRIDE` 為記憶體內變量，進程重啟自動清零（fail-closed）
- Reconciler 漸進升級：Cautious→Defensive→CircuitBreaker，逐級收緊
- REST 失敗 ≥10 次 → Cautious
- Burst ≥5 → CircuitBreaker + CloseAll
- 冷卻期機制（H0Gate cooldown + PNL-3 boot cooldown）
- System mode gate 阻止不當模式下的交易

---

### 原則 #7：學習 ≠ 改寫 Live — ⚠️ PARTIAL

**證據**：Signal Diamond 設計將信號寫入隔離（僅 Paper 寫，`on_tick.rs:378`）。Per-engine `PerEngineRiskStores` + `StrategyFactory::create_for_engine()` 實現三引擎獨立。

**風險點**：ClaudeTeacher `applier.rs`（1257 行）可透過 IPC 修改策略參數。雖有 `strategy_ipc_impl.rs:213` 的 fail-closed 路徑（IPC timeout/cancelled），但學習平面→Live 平面的寫入隔離邊界需要更強的形式化驗證。當前 AI Agent 層全 stub，待 W22 實現後此項需重新審計。

---

### 原則 #8：交易可解釋 — ✅ PASS

**證據**：
- `emit_close_fill()` 每次平倉寫入完整 Fill 記錄（symbol、qty、price、pnl、fee、reason）到 PG trading_tx
- Guardian verdict（含拒絕）持久化到 `trading.risk_verdicts`
- Intent 記錄（strategy_name、side、qty、price）持久化到 PG
- Signal 記錄（signal_id、strategy_name、direction、confidence）持久化
- DecisionContext（LinUCB arm、新聞快照）寫入 PG
- `recent_intents` / `recent_fills` / `recent_signals` 環形緩衝供 IPC 快照
- Canary mode 全量記錄（schema_version + tick_number + indicators + signals + intents + paper_state）
- PositionSnapshot 每 1000 ticks 發射供 ML 訓練

---

### 原則 #9：交易所災難保護 — ✅ PASS

**證據**：
- **本地止損**：`paper_state.check_stops()` → `stop_manager::check_stops()` 多路徑觸發（H0 blocked / paused / normal tick）
- **交易所條件單**：`event_consumer/mod.rs:260-325` 雙軌止損通道，`server_side_stops` 配置項（default: true），`position_manager.set_trading_stop()` 發送 Bybit `set-trading-stop` API
- 測試覆蓋：`test_dual_rail_broker_sl_long_below_entry`、`test_dual_rail_broker_sl_short_above_entry`、`test_dual_rail_close_orders_no_broker_sl`
- API 失敗時 fail-closed：本地 StopManager 仍生效（`event_consumer/mod.rs:290`）
- 黑天鵝檢測器（`black_swan_detector.rs`）4 信號投票，severity 達標時 warn

---

### 原則 #10：認知誠實 — ✅ PASS

**證據**：
- Phase 5 pause 決策體現了認知誠實：發現所有策略 gross edge 為負後立即暫停（而非掩蓋）
- PNL-FIX-1/2 修復後基線重建，明確記錄「前提已作廢」
- `cost_gate` JS-live 的 fail-closed：無估計 → 阻斷開倉，不猜測

---

### 原則 #11：Agent 最大自主權 — ⚠️ PARTIAL

**證據**：策略通過 `on_tick()` 獨立決策 symbol/方向/timing，Orchestrator 多策略並行，Scanner 動態 symbol 選擇。

**不足**：AI Agent 層（H1-H5）全 stub，Strategist/Guardian/Analyst/Executor/Scout 5 Agent 尚未實現。當前 Agent 自主權僅限於確定性策略的參數範圍內，W22 G-1 計劃中。

---

### 原則 #12：持續進化 — ⚠️ PARTIAL

**證據**：
- LinUCB contextual bandit（`linucb/` 模組）用於策略 arm selection
- Kelly sizer（`ml/kelly_sizer.rs`）基於歷史統計動態 sizing
- ClaudeTeacher（`claude_teacher/`）接收外部 AI 教學
- Feature collector → PG → ML training pipeline 基礎設施就位

**不足**：Phase 5 揭露所有策略 gross 負 edge，學習系統正在學習虧損策略。學習→Live 自動部署（Phase 3 放權框架）尚未實現。

---

### 原則 #13：AI 資源成本感知 — ✅ PASS

**證據**：
- `ai_budget/tracker.rs`：BudgetTracker 實現 5 個 scope（local_total / platform_hard_cap / 3 agent scopes）
- `cost_edge_ratio()` 方法計算 used/limit
- 三段降級閾值基於 `local_total` scope
- `ai_budget/pricing.rs` 定價表（當前 placeholder，4-17 改 PG 表）
- IPC `update_ai_budget_config` 寫入路徑 fail-closed（未初始化 → -32603）
- `intent_processor/gates.rs` Gate 3 cost gate 實際生效

---

### 原則 #14：零外部成本可運行 — ✅ PASS

**證據**：系統設計 L0（確定性）+ L1（Ollama 本地）可完全離線運行。H1-H5 AI 層全 stub 不影響基礎交易功能。BudgetConfig 有 $0 baseline fallback。

---

### 原則 #15：多 Agent 協作 — ⚠️ PARTIAL

**證據**：`multi_agent_framework.py`（1104 行）存在框架代碼。`strategist_agent.py`（1162 行）已有基礎。

**不足**：5 Agent + Conductor 編排尚為 stub，正式對象通信未實現。W22 計劃中。

---

### 原則 #16：組合級風險意識 — ✅ PASS

**證據**：
- Guardian `max_same_direction_positions` 限制（default: 3）
- Portfolio context 傳入 Guardian review（`PortfolioContext { drawdown_pct, positions }`）
- `position_risk_evaluator.rs` 9-check 逐倉評估
- `intent_processor` daily loss tracking（`maybe_reset_daily_balance`）
- Session drawdown monitoring + halt mechanism
- Live 縮倉監控：5% 警告 / 15% 自動平倉

---

## 二、代碼規範合規

### 2.1 文件大小限制 — ❌ FAIL

**800 行警告線（⚠️）以上非測試文件（共 19 個）**：

| 行數 | 文件 | 狀態 |
|------|------|------|
| **1914** | governance_routes.py | ❌ **超硬上限 60%** |
| **1812** | governance_hub.py | ❌ **超硬上限 51%** |
| **1452** | signal_generator.py | ❌ **超硬上限 21%** |
| **1381** | risk_config.rs | ❌ **超硬上限 15%** |
| **1352** | backtest_engine.py | ❌ **超硬上限 13%** |
| **1302** | event_consumer/mod.rs | ❌ **超硬上限 9%** |
| **1257** | claude_teacher/applier.rs | ❌ **超硬上限 5%** |
| **1228** | on_tick.rs | ❌ **超硬上限 2%** |
| **1203** | live_session_routes.py | ❌ **超硬上限 0.25%** |
| 1192 | tick_pipeline/mod.rs | ⚠️ 接近硬上限 |
| 1192 | ipc_server/handlers.rs | ⚠️ 接近硬上限 |
| 1179 | legacy_routes.py | ⚠️ |
| 1164 | strategy_auto_deployer.py | ⚠️ |
| 1162 | strategist_agent.py | ⚠️ |
| 1158 | grid_trading.rs | ⚠️ |
| 1151 | order_manager.rs | ⚠️ |
| 1104 | multi_agent_framework.py | ⚠️ |
| 1086 | klines.rs | ⚠️ |
| 1067 | h0_gate.rs | ⚠️ |

**裁定**：9 個文件超過 1200 行硬上限，其中 `governance_routes.py`（1914 行）最嚴重，CLAUDE.md §三 已標注為 pre-existing 需 refactor。10+ 文件在 800-1200 警告區間。此項 FAIL。

---

### 2.2 雙語注釋 — ✅ PASS

**抽查結果**：
- `on_tick.rs`：每個步驟、分支、修復標記均有中英對照注釋 ✅
- `guardian.rs`：MODULE_NOTE + struct/function docstring 雙語 ✅
- `intent_processor/router.rs`：Gate 描述中英對照 ✅
- `bybit_rest_client.rs`：方法 docstring 雙語 ✅
- `ai_budget/tracker.rs`：MODULE_NOTE 中英完整 ✅
- `live_session_routes.py`：文件頭 MODULE_NOTE 中英 ✅
- 124 個 Rust 文件含 MODULE_NOTE（`Grep` MODULE_NOTE 結果）

---

### 2.3 跨平台兼容性 — ✅ PASS

**路徑硬編碼檢查**：
- Rust 代碼：`grep /home/ncyu` → **零匹配** ✅
- Python 代碼：僅 `bybit_path_policy.py` 存在引用，且為反硬編碼工具（`COMPAT_ROOT = REPO_ROOT # No longer hardcoded`） ✅
- `Path(__file__).parent` 相對路徑廣泛使用 ✅

---

### 2.4 模塊依賴方向 — ✅ PASS

**證據**：
- Python route 文件統一 `from . import main_legacy as base`（18 個文件確認）
- 循環依賴防護：`h1_thought_gate.py` 明確禁止同目錄 import，`governance_routes.py` 用 lazy import 避免循環
- Rust 方面：`openclaw_core` → `openclaw_types` → `openclaw_engine` 依賴方向清晰

---

### 2.5 Singleton 管理 — ⚠️ PARTIAL

**已登記 Singleton（CLAUDE.md §九）**：settings / STORE / app / limiter — 全通過 `base.*` 引用 ✅

**發現的未登記 Singleton**：
- `LeaseTTLConfigManager._instance`（`lease_ttl_config.py:403`）— 雙重鎖 singleton
- `ExperimentLedger` module-level singleton（`experiment_routes.py:66`）
- `PromotionGate._instance`（`governance_routes.py:1719`）— 函數屬性 singleton
- `strategy_ai_routes.py:38` BybitClient lazy singleton
- `strategy_wiring.py:83` 多個 module-level singletons

**裁定**：≥5 個未在 CLAUDE.md §九 singleton 表中登記的 singleton。功能正常但不符合登記規則。

---

## 三、工作流合規

### 3.1 E2+E4 強制工作鏈 — ✅ PASS

**近 30 commit 分析**：
- 修復提交（`fix(*)`）均有具體問題追蹤號（PNL-FIX-1、B-1、B-2、M-1~M-4）
- L3 審計提交存在：`b4efe49 fix(3e-arch): L3 audit — e2e tests, 21 warnings, defensive hardening`
- E2E 測試：18 個 e2e + 32 個 promotion 測試
- 測試基線持續更新：939/366/18/32/2852

---

### 3.2 文檔同步規則 — ✅ PASS

**證據**：
- `CLAUDE_CHANGELOG.md` 持續更新（grep 確認多次 commit 追加）
- CLAUDE.md §三 與實際代碼狀態一致（3E-ARCH / Multi-Symbol / Phase 5 PAUSED 等）
- Worklogs 目錄結構化管理（`docs/worklogs/`、`docs/archive/`）
- TODO.md 追蹤活躍（commit `1a4bd3a` 專門更新 TODO）

---

## 四、硬邊界合規

### 4.1 Live 安全防護 — ✅ PASS

**證據**：
- Live session start 雙重門控：(1) `_require_operator(actor)` 角色認證 + (2) `global_mode` 必須含 "live"（`live_session_routes.py:638-652`）
- `_EXECUTION_AUTHORITY_OVERRIDE` 記憶體內，重啟清零 fail-closed ✅
- System mode gate 在 `on_tick.rs:456-477` 阻止不當模式交易 ✅
- `OPENCLAW_ALLOW_MAINNET` env var 已移除（SEC-17 架構決策），API key 為唯一門控 ✅
- Live 縮倉監控：回撤 ≥5% 警告 / ≥15% 自動撤銷 + 平倉 + 凍結 ✅

---

### 4.2 Fail-Closed 行為 — ✅ PASS

**全系統 fail-closed 路徑確認**：
- Bybit API retCode != 0 → `BybitError::Api` 返回 Err（`bybit_rest_client.rs:37`）
- `is_retryable()` 僅標記可重試，但 **max_retries = 0**（硬邊界），不自動重試 ✅
- IPC 未初始化 → -32603 error code ✅
- entry_price = 0 → -999% 強制硬止損 ✅
- 負 edge estimate → fail-closed 阻斷 ✅
- 授權過期 → 自動拒絕 ✅

---

### 4.3 禁止行為確認 — ✅ PASS

- 繞過 Operator 角色認證直接啟動 live session → `_require_operator()` 阻止 ✅
- 自動修改 trading_mode 為 live → 需 operator 顯式配置 TOML ✅
- `should_call_ai=true` 但未發生 → H1-H5 全 stub，不會出現此矛盾 ✅
- 偽造 AI 調用/交易活動 → 無偽造路徑存在 ✅

---

## 五、綜合評分

| 類別 | 評分 | 說明 |
|------|------|------|
| 根原則 1-6 | ✅ 6/6 PASS | 核心風控架構健全 |
| 根原則 7 | ⚠️ PARTIAL | 學習→Live 隔離需形式化驗證 |
| 根原則 8-10 | ✅ 3/3 PASS | 審計/災難防護/認知誠實 |
| 根原則 11-12 | ⚠️ 2/2 PARTIAL | AI Agent 層 stub，待 W22 |
| 根原則 13-14 | ✅ 2/2 PASS | 成本感知 + 零外部成本 |
| 根原則 15 | ⚠️ PARTIAL | Multi-Agent 框架存在但未激活 |
| 根原則 16 | ✅ PASS | 組合風險監控完備 |
| 文件大小 | ❌ FAIL | 9 文件超 1200 硬上限 |
| 雙語注釋 | ✅ PASS | 覆蓋良好 |
| 跨平台 | ✅ PASS | 無硬編碼路徑 |
| 依賴方向 | ✅ PASS | 無循環 import |
| Singleton | ⚠️ PARTIAL | ≥5 個未登記 |
| E2+E4 | ✅ PASS | 工作鏈執行一致 |
| 文檔同步 | ✅ PASS | 規則遵守 |
| Live 安全 | ✅ PASS | 雙重門控 + fail-closed |
| Fail-Closed | ✅ PASS | 全系統覆蓋 |

**總體評級**：⚠️ **PARTIAL PASS** — 核心安全/風控/審計架構健全，無 P0 阻塞項。主要差距集中在：(1) 文件大小違規（pre-existing，已記錄在案）；(2) AI Agent 層 stub（W22 計劃中）；(3) Singleton 登記不完整。

---

## 六、建議行動項

| 優先級 | 項目 | 說明 |
|--------|------|------|
| P1 | 文件拆分 | `governance_routes.py`（1914行）、`governance_hub.py`（1812行）必須拆分至 1200 以下 |
| P2 | Singleton 登記 | 將 5+ 個未登記 singleton 補入 CLAUDE.md §九 表 |
| P2 | 策略重做 | G-SR-1 / Strategist Agent — 所有策略 gross 負 edge，學習系統正學習虧損 |
| P3 | 學習隔離驗證 | ClaudeTeacher 寫入路徑需形式化邊界定義 |
| P3 | AI Agent 實現 | W22 G-1 完成後重新審計原則 #11/#12/#15 |

---

*審計完成時間：2026-04-12*
*下次計劃審計：W22 末（AI Agent 層實現後）*
