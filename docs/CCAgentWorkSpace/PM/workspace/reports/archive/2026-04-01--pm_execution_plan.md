# PM 執行計劃：April 1 審計修復批次
# PM Execution Plan: April 1 Audit Fix Batches
# 日期：2026-04-01
# 基準：PA 複驗後 78 項去重問題（8 份審計報告交叉驗證）
# 測試基準線：3330 passed / 22 failed

---

## 一、執行摘要

### 審計輸入
8 份獨立審計報告（FA/AI-E/E3/E4/E5/CC/TW/R4），經 PA 逐項代碼級交叉驗證，去重後確認 78 項獨立問題。

### 問題分布（PA 複驗後）
| 優先級 | 數量 | 預估總工時 |
|--------|------|-----------|
| P0 | 1 | 0.5h |
| P1 | 5 | 5.8h |
| HIGH | 4 | 8.5h |
| MEDIUM | 18 | ~32h |
| LOW/P3 | ~50 | ~60h（積壓） |
| **可執行合計** | **28 項** | **~47h** |

### 誤報排除（PA 確認）
| # | 報告 | 問題 | 判定 |
|---|------|------|------|
| FP-1 | FA P1-FA-3 | EvolutionEngine 無 REST API | FALSE — `evolution_routes.py` 已存在且在 main.py 註冊 |
| FP-2 | FA DC-4 | EvolutionEngine 外部觸發缺失 | FALSE — 同 FP-1 |

### 降級決定
| 問題 | 原級別 | 新級別 | 理由 |
|------|--------|--------|------|
| FA P0-FA-2 BacktestEngine API 無數據源 | P0 | P1 | demo_only 階段非阻塞，可代碼級調用 |
| E5 NEW-P1 backtest O(n^2) | Critical | HIGH | API 不通時無法觸發；回測非即時操作 |
| E5 NEW-P2/P3 claims/hypotheses 無上限 | HIGH | MEDIUM | save 不工作意味著重啟清零；累積速率低 |

---

## 二、批次計劃（按優先級排列）

### ██ Batch 1: P0 知識閉環 + 快速 P1（~3.5h · 0.5 天）

> **目標**：激活 Phase 2 學習管線死代碼 + 確保知識跨重啟保留
> **前置**：無
> **並行度**：3 E1 同時工作

| 問題 ID | 來源 | 描述 | 檔案 | 修復方案 | 工時 | E1 |
|---------|------|------|------|---------|------|-----|
| **APR01-P0-1** | FA P0-FA-1 + AI-E §5.2 | TruthSourceRegistry 從未注入 StrategistAgent/AnalystAgent — 整個 Phase 2 知識閉環死代碼 | `app/phase2_strategy_routes.py` | 統一 `_seed_registry`（main.py）為單例，在 phase2_strategy_routes 中調用 `STRATEGIST_AGENT.set_truth_registry()` + `ANALYST_AGENT.set_truth_registry()` | 0.5h | E1-Alpha |
| **APR01-P1-1** | FA P1-FA-6 + AI-E P1-AI-1 | TruthSourceRegistry save_snapshot() 從未在運行中被自動調用 — 重啟丟失所有知識 | `app/truth_source_registry.py`, `app/phase2_strategy_routes.py` | 在 register_claim() 中 debounced auto_save（或 atexit hook + 定時 save），確保 main.py 啟動時 load_snapshot 路徑對齊 | 1h | E1-Alpha |
| **APR01-P1-2** | AI-E P1-AI-1 | ExperimentLedger 純記憶體狀態 — 重啟歸零 | `app/experiment_ledger.py` | 新增 save_snapshot()/load_snapshot() 方法 + debounced auto_save + 啟動時 load | 1.5h | E1-Beta |
| **APR01-P1-3** | FA P1-FA-4 | pipeline_bridge 仍調用已廢棄的 collect_pending_intents() — 每 tick 日誌噪音 | `app/pipeline_bridge.py` | 移除 line 482-510 的 strategist collect 調用（TD-2 已標記 DEPRECATED，返回 []） | 0.3h | E1-Gamma |

**Batch 1 工作鏈**：
```
E1-Alpha（APR01-P0-1 + APR01-P1-1）‖ E1-Beta（APR01-P1-2）‖ E1-Gamma（APR01-P1-3）
                              ↓ 全部完成
                    E2 代碼審查（重點：singleton 唯一性、auto_save 邊界）
                              ↓
                    E4 全量回歸（重點：truth_source_registry / experiment_ledger 測試）
                              ↓
                    commit: fix(learning): Batch 1 — 知識閉環激活 + 持久化 + 廢棄路徑清理
```

**驗收標準**：
- TruthSourceRegistry 在運行時被注入到 StrategistAgent 和 AnalystAgent（非 None）
- save_snapshot() 在 claim 寫入後自動觸發
- ExperimentLedger 有基本 save/load 能力
- pipeline_bridge 中 collect_pending_intents 廢棄調用已移除
- E4 全量通過 ≥ 3330

---

### ██ Batch 2: BacktestEngine 接通 + 安全加固（~3h · 0.5 天）

> **目標**：解鎖回測 API + CORS 安全校驗 + 信息洩露修復
> **前置**：Batch 1（BacktestEngine 依賴 TruthSourceRegistry 注入回測結果）
> **並行度**：3 E1 同時工作

| 問題 ID | 來源 | 描述 | 檔案 | 修復方案 | 工時 | E1 |
|---------|------|------|------|---------|------|-----|
| **APR01-P1-4** | FA P0-FA-2（降級） | BacktestEngine API 無數據源（KlineManager 未注入） | `app/backtest_routes.py` | get_backtest_engine() 注入 KlineManager（從 phase2_strategy_routes 導入或 Bybit API 直接拉取） | 1h | E1-Alpha |
| **APR01-HIGH-1** | E3 HIGH-LEGACY-1 | CORS allow_credentials=True 缺少啟動校驗 | `app/main_legacy.py` | 啟動時校驗 _cors_origins 不含 `*`；若含 `*` + allow_credentials → 拒絕啟動或 warning + 自動修正 | 0.5h | E1-Beta |
| **APR01-MEDIUM-1** | E3 MEDIUM-NEW-3 + LOW-NEW-3（合併組 4） | paper_trading_routes 5 處 + backtest_routes 1 處 detail=str(e) → 固定消息 | `app/paper_trading_routes.py`, `app/backtest_routes.py` | 全部改為 `detail="Internal server error"` + 保留 logger.error | 0.5h | E1-Gamma |
| **APR01-MEDIUM-2** | E3 MEDIUM-NEW-2 | experiment_routes ProposeHypothesisRequest 無 max_length 驗證 | `app/experiment_routes.py` | 對 title/description/conditions 加 `max_length` Field 約束 | 0.5h | E1-Gamma |

**Batch 2 工作鏈**：
```
E1-Alpha（APR01-P1-4）‖ E1-Beta（APR01-HIGH-1）‖ E1-Gamma（APR01-MEDIUM-1 + MEDIUM-2）
                              ↓ 全部完成
                    E2（重點：KlineManager 注入線程安全、CORS 校驗邏輯）
                              ↓
                    E4（重點：backtest API 端到端、auth 測試）
                              ↓
                    commit: fix(backtest+security): Batch 2 — 回測數據源 + CORS + detail 屏蔽
```

**驗收標準**：
- POST /api/v1/backtest/run 返回有效回測結果（非 "No OHLCV data" warning）
- CORS origins 含 `*` 時啟動警告
- 所有 detail=str(e) 已替換
- E4 ≥ 3330

---

### ██ Batch 3: MessageBus 路徑 + 安全響應頭（~4h · 0.5 天）

> **目標**：5-Agent MessageBus 全路徑接通 + HTTP 安全加固
> **前置**：Batch 1（Agent 需要 TruthSourceRegistry 注入完成後再改 bus 路徑）
> **並行度**：2 E1 + 1 E1a

| 問題 ID | 來源 | 描述 | 檔案 | 修復方案 | 工時 | E1 |
|---------|------|------|------|---------|------|-----|
| **APR01-P1-5** | FA P1-FA-2 | MessageBus Guardian→Executor APPROVED_INTENT 路徑斷裂 | `app/guardian_agent.py` 或 `app/multi_agent_framework.py` | PA 建議方案 B：讓 pipeline_bridge 調用 Conductor.process_trade_intent()；或方案 A：在 Guardian._handle_trade_intent() APPROVED 後發送 APPROVED_INTENT 到 Executor | 2h | E1-Alpha |
| **APR01-MEDIUM-3** | E3 MEDIUM-LEGACY-3 | 缺乏安全 HTTP 響應頭（CSP/X-Frame-Options/X-Content-Type-Options） | `app/main.py` 或 `app/main_legacy.py` | 添加 Starlette SecurityHeaderMiddleware 或自定義中間件 | 1h | E1-Beta |
| **APR01-MEDIUM-4** | E3 MEDIUM-NEW-1 | tab-governance.html 30+ 處 innerHTML 未轉義 | `app/static/tab-governance.html` | 動態數據來源逐一用 ocEsc() 包裹 | 1h | E1a-Alpha |

**Batch 3 工作鏈**：
```
E1-Alpha（APR01-P1-5）‖ E1-Beta（APR01-MEDIUM-3）‖ E1a-Alpha（APR01-MEDIUM-4）
                              ↓
                    E2 + E4 → commit
```

**驗收標準**：
- Guardian APPROVED → APPROVED_INTENT 消息發送到 Executor（MessageBus 端到端測試）
- HTTP 響應包含 X-Content-Type-Options: nosniff 等安全頭
- tab-governance.html 動態值有 ocEsc() 保護
- E4 ≥ 3330

---

### ██ Batch 4: 記憶體保護 + 文檔索引（~4h · 0.5 天）

> **目標**：Registry/Ledger 記憶體上限 + 文檔索引補全
> **前置**：Batch 1（持久化完成後再加上限邏輯）
> **並行度**：3 E1/R4 同時

| 問題 ID | 來源 | 描述 | 檔案 | 修復方案 | 工時 | E1 |
|---------|------|------|------|---------|------|-----|
| **APR01-MEDIUM-5** | E5 NEW-P2（降級） | TruthSourceRegistry _claims 無上限 + 過期不清理 | `app/truth_source_registry.py` | MAX_CLAIMS=5000 + register_claim() 中定期清理 is_expired() 條目 | 1h | E1-Alpha |
| **APR01-MEDIUM-6** | E5 NEW-P3（降級） | ExperimentLedger _hypotheses 無上限 | `app/experiment_ledger.py` | MAX_HYPOTHESES=2000 + 清理已結案超 TTL 條目 | 1h | E1-Beta |
| **APR01-HIGH-2** | R4 R4-01/02（合併組 6） | audit/March31/ 7 份核心報告 + README 結構圖缺 audit/ 目錄 | `docs/README.md` | 補 audit/March31/ 和 audit/April01/ 索引區塊；補 decisions/ .docx 索引 | 1h | R4 |
| **APR01-MEDIUM-7** | R4 R4-03/04 | decisions/ .docx 未索引 + governance_dev ~14 文件未索引 | `docs/README.md` | 在索引中添加 decisions/ 專區 + governance_dev 補全 | 1h | R4 |

**Batch 4 工作鏈**：
```
E1-Alpha（APR01-MEDIUM-5）‖ E1-Beta（APR01-MEDIUM-6）‖ R4（APR01-HIGH-2 + MEDIUM-7）
                              ↓
                    E2 + E4 → commit
```

**驗收標準**：
- _claims dict 不超過 MAX_CLAIMS（測試驗證）
- _hypotheses dict 不超過 MAX_HYPOTHESES
- docs/README.md 包含 audit/March31/ 全部 7 份報告索引
- E4 ≥ 3330

---

### ██ Batch 5: 性能優化 + 覆蓋率提升（~8h · 1 天）

> **目標**：BacktestEngine O(n^2) 修復 + 關鍵模塊測試覆蓋率提升
> **前置**：Batch 2（BacktestEngine API 接通後再優化性能）
> **並行度**：3 E1/E4 同時

| 問題 ID | 來源 | 描述 | 檔案 | 修復方案 | 工時 | E1 |
|---------|------|------|------|---------|------|-----|
| **APR01-HIGH-3** | E5 NEW-P1/P4（降級合併） | backtest_engine O(n^2) 列表切片 + EMA/RSI 從頭重算 | `program_code/local_model_tools/backtest_engine.py` | 使用索引而非切片：_compute_indicators_pure 接收 end_idx 參數；增量 EMA 計算 | 3h | E1-Alpha |
| **APR01-MEDIUM-8** | E5 NEW-S1 | backtest_engine 指標函數與 indicators/ 重複 | `program_code/local_model_tools/backtest_engine.py` | 提取純函數到 indicators/pure.py；backtest_engine 從此導入 | 1h | E1-Alpha |
| **APR01-MEDIUM-9** | AI-E P2-AI-2 | L2 後台線程結果被完全丟棄 | `app/strategist_agent.py` | L2 結果回注機制：更新 _strategy_preference_weights 或 cache 供下次決策參考 | 2h | E1-Beta |
| **APR01-MEDIUM-10** | FA P2-FA-1 | MarketScanner MAX_SYMBOLS_TO_TRADE=5 vs deployer 25 不一致 | `program_code/local_model_tools/market_scanner.py` | 統一為可配置常量，從 deployer 配置讀取 | 0.5h | E1-Gamma |
| **APR01-E4-1** | E4 2.5 | strategy_auto_deployer 0% 覆蓋率 | `tests/test_strategy_auto_deployer.py`（新建） | 至少 15 個核心測試（部署/撤回/symbol 限制/掃描回調） | 2h | E4 |

**Batch 5 工作鏈**：
```
E1-Alpha（APR01-HIGH-3 + MEDIUM-8）‖ E1-Beta（APR01-MEDIUM-9）‖ E1-Gamma（APR01-MEDIUM-10）‖ E4（APR01-E4-1）
                              ↓
                    E2 + E4 → commit
```

---

### ██ Batch 6: 技術債精選 + 文檔合規（~6h · 1 天）

> **目標**：sys.path 重複消除 + MODULE_NOTE 補全 + 鎖範圍收窄
> **前置**：無（可與 Batch 3-5 並行）
> **並行度**：3 E1/TW 同時

| 問題 ID | 來源 | 描述 | 檔案 | 修復方案 | 工時 | E1 |
|---------|------|------|------|---------|------|-----|
| **APR01-MEDIUM-11** | E5 NEW-S2 + #44（合併組 5） | 4 個路由文件重複 sys.path 5 層 dirname | `app/backtest_routes.py`, `app/evolution_routes.py`, `app/experiment_routes.py`, `app/phase2_strategy_routes.py` | 提取公共函數 `_ensure_program_code_on_path()` | 1h | E1-Alpha |
| **APR01-MEDIUM-12** | E5 NEW-P5 | _process_pending_intents 鎖持有範圍過大 | `app/pipeline_bridge.py` | 收窄鎖範圍：鎖內只讀共享狀態，解鎖後執行 I/O 操作 | 2h | E1-Beta |
| **APR01-MEDIUM-13** | E3 MEDIUM-LEGACY-2 | Token 存儲在 localStorage | `app/static/common.js` | 改用 HttpOnly secure cookie（需後端配合設置 Set-Cookie） | 2h | E1-Gamma |
| **APR01-TW-1** | TW B1/B2/B3 | main.py / multi_agent_framework / perception_data_plane 缺 MODULE_NOTE | 3 個 .py 文件 | 補充中英雙語 MODULE_NOTE | 1h | TW |

**Batch 6 工作鏈**：
```
E1-Alpha（APR01-MEDIUM-11）‖ E1-Beta（APR01-MEDIUM-12）‖ E1-Gamma（APR01-MEDIUM-13）‖ TW（APR01-TW-1）
                              ↓
                    E2 + E4 → commit
```

---

### ██ Batch 7: 延後項（Phase 4 前或積壓 · 不阻塞 Live 準備）

> 以下為中長期項目，不進入本輪修復排程。記錄供未來 Sprint 規劃。

| 問題 ID | 來源 | 描述 | 工時估計 | 延後原因 |
|---------|------|------|---------|---------|
| APR01-HIGH-4 | E5 NEW-R1 | _process_pending_intents 462 行超巨方法拆分 | 4h | 高風險重構，需專門 Sprint |
| APR01-E5-R2/R3 | E5 NEW-R2/R3 | submit_order.mutator 341 行 / tick.mutator 262 行 | 3h+2h | 同上 |
| APR01-E5-LEGACY | E5 #15 | main_legacy.py 5113 行單文件 | 20h+ | 需整體重構規劃 |
| APR01-FA-P2-2 | FA P2-FA-2 | Regime-aware 策略選擇 | 8h | 功能型需求，非修復 |
| APR01-FA-P2-3 | FA P2-FA-3 | 策略優化→部署自動化循環 | 10h | 功能型需求 |
| APR01-CC-1 | CC §二 | 原則 15 Conductor 自動編排完善 | 6h | 非阻塞 |
| APR01-CC-2 | CC §二 | 原則 12 L5 元學習 | 15h+ | Phase 4+ |
| APR01-E5-LOGGER | E5 #20 | 182 處 logger f-string → %s | 4h | 低影響，可漸進修復 |
| APR01-ALL-LOW | 多報告 | ~50 項 LOW/P3 問題 | ~60h | 積壓 |

---

## 三、依賴關係圖

```
Batch 1: P0 知識閉環（0.5 天）
  │  APR01-P0-1  TruthSourceRegistry 注入
  │  APR01-P1-1  TruthSourceRegistry 持久化
  │  APR01-P1-2  ExperimentLedger 持久化
  │  APR01-P1-3  collect_pending_intents 清理
  │
  ├──────→ Batch 2: BacktestEngine + 安全（0.5 天）
  │          APR01-P1-4  BacktestEngine 數據源
  │          APR01-HIGH-1 CORS 校驗
  │          APR01-MEDIUM-1/2  detail+input validation
  │          │
  │          └──→ Batch 5: 性能 + 覆蓋率（1 天）
  │                 APR01-HIGH-3  O(n^2) 修復
  │                 APR01-MEDIUM-8/9/10
  │                 APR01-E4-1
  │
  ├──────→ Batch 3: MessageBus + 安全頭（0.5 天）
  │          APR01-P1-5  Guardian→Executor
  │          APR01-MEDIUM-3/4
  │
  └──────→ Batch 4: 記憶體保護 + 文檔（0.5 天）
             APR01-MEDIUM-5/6  上限清理
             APR01-HIGH-2 + MEDIUM-7  文檔索引

Batch 6: 技術債 + 文檔合規（1 天 · 無前置依賴，可任意並行）
  APR01-MEDIUM-11/12/13 + TW-1

Batch 7: 延後積壓（不排程）
```

**關鍵路徑**：Batch 1 → Batch 2 → Batch 5（共 2 天）
**最短完成時間**：Batch 1(0.5d) → Batch 2/3/4 並行(0.5d) → Batch 5/6 並行(1d) = **2 天**

---

## 四、並行度分析（最大化 E1 同時工作數）

### 每批次 E1 使用情況

| 批次 | E1-Alpha | E1-Beta | E1-Gamma | E1a-Alpha | R4 | TW | E4 | 並行數 |
|------|----------|---------|----------|-----------|-----|-----|-----|--------|
| Batch 1 | P0-1+P1-1 | P1-2 | P1-3 | — | — | — | — | **3** |
| Batch 2 | P1-4 | HIGH-1 | M-1+M-2 | — | — | — | — | **3** |
| Batch 3 | P1-5 | M-3 | — | M-4 | — | — | — | **3** |
| Batch 4 | M-5 | M-6 | — | — | H-2+M-7 | — | — | **3** |
| Batch 5 | H-3+M-8 | M-9 | M-10 | — | — | — | E4-1 | **4** |
| Batch 6 | M-11 | M-12 | M-13 | — | — | TW-1 | — | **4** |

**最大並行 E1 數**：4（Batch 5/6）
**平均並行 E1 數**：3.3

### Batch 間並行可能性

```
時間軸：
Day 1 AM:  Batch 1 ═══════════════╗
Day 1 PM:  Batch 2 ═══════════╗   ║  Batch 3 ═══════╗  Batch 4 ═══════╗
Day 2 AM:  Batch 5 ════════════════╗  Batch 6 ════════════════════════╗
Day 2 PM:  Batch 5 (cont'd) ══════╝  Batch 6 (cont'd) ══════════════╝
```

---

## 五、風險評估

### 高風險項目

| 問題 | 風險 | 緩解措施 |
|------|------|---------|
| APR01-P0-1 Registry 注入 | main.py 已有 _seed_registry，可能出現雙實例 | 統一為全局 singleton，phase2_strategy_routes 從 main.py import |
| APR01-P1-5 MessageBus 路徑 | 改變 Agent 消息流，可能影響現有 pipeline_bridge 直接調用路徑 | 保持 pipeline_bridge 路徑不變，MessageBus 路徑作為補充而非替代 |
| APR01-MEDIUM-12 鎖範圍收窄 | pipeline_bridge 核心方法，改動易引入並發 bug | 先寫並發測試再改代碼；E2 重點審查鎖邊界 |
| APR01-MEDIUM-13 Cookie 替代 localStorage | 前後端都需改動，可能破壞登入流程 | 分步執行：先後端 Set-Cookie，確認後再改前端 |

### Live 阻塞項（M/N 章前必須完成）

以下問題必須在進入 Phase 4 Paper Trading 觀察期前修復：

| 問題 | 阻塞原因 | 對應批次 |
|------|---------|---------|
| APR01-P0-1 Registry 注入 | 原則 12「持續進化」核心能力 | Batch 1 |
| APR01-P1-1 Registry 持久化 | 21 天觀察期必須跨重啟保留知識 | Batch 1 |
| APR01-P1-2 Ledger 持久化 | 同上 | Batch 1 |
| APR01-HIGH-1 CORS 校驗 | Live 前安全必備 | Batch 2 |
| APR01-MEDIUM-3 安全響應頭 | Live 前安全必備 | Batch 3 |
| APR01-MEDIUM-13 Token Cookie | Live 前建議完成 | Batch 6 |

---

## 六、驗收標準（E2+E4 必須通過的測試項）

### 每批次 E4 重點驗證

| 批次 | E4 驗證重點 | 最低測試新增 |
|------|-----------|------------|
| Batch 1 | TruthSourceRegistry 注入後 _truth_registry is not None；save/load round-trip；collect_pending_intents 不再被調用 | +5 tests |
| Batch 2 | POST /backtest/run 返回有效結果；CORS `*` 被攔截；detail 不含 Python traceback | +5 tests |
| Batch 3 | APPROVED_INTENT 在 MessageBus 中可觀察；HTTP 響應包含安全頭；tab-governance XSS 防護 | +3 tests |
| Batch 4 | MAX_CLAIMS 觸發清理；MAX_HYPOTHESES 觸發清理 | +4 tests |
| Batch 5 | backtest 1000 bars 性能 < 2s（vs 原 O(n^2)）；auto_deployer 基本覆蓋 | +15 tests |
| Batch 6 | sys.path 公共函數；MODULE_NOTE 覆蓋率 ≥ 85% | +3 tests |

### 全局驗收

- 每批次 commit 後 E4 全量回歸 ≥ 3330 passed
- 不引入新的 failed/error（pre-existing 除外）
- E2 確認所有改動有雙語注釋

---

## 七、完整問題-批次對照表

| 問題 ID | 優先級 | 來源報告 | 描述 | 批次 | E1 |
|---------|--------|---------|------|------|-----|
| APR01-P0-1 | P0 | FA P0-FA-1, AI-E §5.2 | TruthSourceRegistry 從未注入 Agent | Batch 1 | E1-Alpha |
| APR01-P1-1 | P1 | FA P1-FA-6, AI-E P1-AI-1 | Registry save_snapshot() 未被調用 | Batch 1 | E1-Alpha |
| APR01-P1-2 | P1 | AI-E P1-AI-1 | ExperimentLedger 無持久化 | Batch 1 | E1-Beta |
| APR01-P1-3 | P1 | FA P1-FA-4 | collect_pending_intents 廢棄調用 | Batch 1 | E1-Gamma |
| APR01-P1-4 | P1 | FA P0-FA-2（降級） | BacktestEngine 無 KlineManager | Batch 2 | E1-Alpha |
| APR01-P1-5 | P1 | FA P1-FA-2 | MessageBus Guardian→Executor 斷裂 | Batch 3 | E1-Alpha |
| APR01-HIGH-1 | HIGH | E3 HIGH-LEGACY-1 | CORS 啟動校驗 | Batch 2 | E1-Beta |
| APR01-HIGH-2 | HIGH（文檔） | R4 R4-01/02 | audit/March31 未索引 | Batch 4 | R4 |
| APR01-HIGH-3 | HIGH | E5 NEW-P1/P4（降級） | backtest O(n^2) + 指標重算 | Batch 5 | E1-Alpha |
| APR01-MEDIUM-1 | MEDIUM | E3 MEDIUM-NEW-3, LOW-NEW-3 | detail=str(e) 信息洩露 | Batch 2 | E1-Gamma |
| APR01-MEDIUM-2 | MEDIUM | E3 MEDIUM-NEW-2 | experiment_routes 無 max_length | Batch 2 | E1-Gamma |
| APR01-MEDIUM-3 | MEDIUM | E3 MEDIUM-LEGACY-3 | 缺安全 HTTP 響應頭 | Batch 3 | E1-Beta |
| APR01-MEDIUM-4 | MEDIUM | E3 MEDIUM-NEW-1 | tab-governance innerHTML XSS | Batch 3 | E1a-Alpha |
| APR01-MEDIUM-5 | MEDIUM | E5 NEW-P2（降級） | _claims 無上限 | Batch 4 | E1-Alpha |
| APR01-MEDIUM-6 | MEDIUM | E5 NEW-P3（降級） | _hypotheses 無上限 | Batch 4 | E1-Beta |
| APR01-MEDIUM-7 | MEDIUM（文檔） | R4 R4-03/04 | decisions/.docx + governance_dev 未索引 | Batch 4 | R4 |
| APR01-MEDIUM-8 | MEDIUM | E5 NEW-S1 | backtest 指標函數與 indicators/ 重複 | Batch 5 | E1-Alpha |
| APR01-MEDIUM-9 | MEDIUM | AI-E P2-AI-2 | L2 結果被丟棄 | Batch 5 | E1-Beta |
| APR01-MEDIUM-10 | MEDIUM | FA P2-FA-1 | MAX_SYMBOLS 不一致 | Batch 5 | E1-Gamma |
| APR01-MEDIUM-11 | MEDIUM | E5 NEW-S2, #44 | sys.path 重複 4 處 | Batch 6 | E1-Alpha |
| APR01-MEDIUM-12 | MEDIUM | E5 NEW-P5 | 鎖持有範圍過大 | Batch 6 | E1-Beta |
| APR01-MEDIUM-13 | MEDIUM | E3 MEDIUM-LEGACY-2 | Token localStorage | Batch 6 | E1-Gamma |
| APR01-TW-1 | P2（文檔） | TW B1/B2/B3 | 3 個核心文件缺 MODULE_NOTE | Batch 6 | TW |
| APR01-E4-1 | MEDIUM | E4 2.5 | strategy_auto_deployer 0% 覆蓋率 | Batch 5 | E4 |
| APR01-HIGH-4 | HIGH | E5 NEW-R1 | _process_pending_intents 462 行 | Batch 7（延後） | — |
| APR01-CC-1 | MEDIUM | CC §二 | 原則 15 Conductor | Batch 7（延後） | — |
| APR01-CC-2 | MEDIUM | CC §二 | 原則 12 L5 元學習 | Batch 7（延後） | — |
| APR01-ALL-LOW | LOW | 多報告 | ~50 項 LOW/P3 | Batch 7（延後） | — |

---

*本報告由 PM (Project Manager) 基於 PA 交叉驗證後的 78 項去重問題清單編制。所有問題均有原始報告交叉引用。*
*最短完成時間：2 天（Batch 1-6）。延後項（Batch 7）不計入本輪排程。*
