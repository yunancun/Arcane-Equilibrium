# OpenClaw Bybit — 開發路線圖 v2（PM+FA 聯合制定）

**日期**: 2026-03-31
**基線**: Git HEAD `aa086dc` · 2,227 tests passing · 76% spec compliance
**方法**: 287 條治理規格要求 vs 實際代碼逐項比對
**目標**: Paper Trading 穩定盈利運行 → Live 授權準備

---

## 一、當前狀態總覽

### 治理合規度計分卡（16 條根原則）

| # | 原則 | 狀態 | 說明 |
|---|------|------|------|
| §5.1 | 單一寫入口 | ✅ A | Executor 唯一寫入 |
| §5.2 | 讀寫分離 | ✅ A | GUI/研究只讀 |
| §5.3 | AI≠即時命令 | ✅ A | Decision Lease 機制 |
| §5.4 | 策略不繞風控 | ✅ A | Guardian fail-closed 主門控 |
| §5.5 | 生存>利潤 | ✅ A | P0/P1 硬邊界 |
| §5.6 | 失敗默認收縮 | ✅ A | fail-closed 全鏈路 |
| §5.7 | 學習≠改寫 Live | ✅ A | 學習/執行隔離 |
| §5.8 | 交易可解釋 | ✅ A | TradeAttribution 6 因子 |
| §5.9 | 交易所災難保護 | ✅ A | 雙重止損防線 |
| §5.10 | 認知誠實 | ⚠️ B | Perception Plane 接入，但 Truth Source 未形式化 |
| §5.11 | Agent 最大自主權 | ✅ A | 5 Agent 全運行 |
| §5.12 | 持續進化 | ⚠️ C | L1-L2 運行，L3-L5 佔位符 |
| §5.13 | AI 成本感知 | ✅ A | cost_edge_ratio ≥0.8 觸發 |
| §5.14 | 零外部成本可運行 | ✅ A | Ollama + Qwen 3.5 就緒 |
| §5.15 | 多 Agent 協作 | ✅ A | 結構化消息協議 |
| §5.16 | 組合級風險 | ✅ A | 相關性 0.7 門控 + 行業集中度 |

**合規度: 14/16 = 87.5%** (2 項 Partial)

### 規格實施狀態

| 類別 | 數量 | 佔比 | 說明 |
|------|------|------|------|
| A — 已實施 | 67 | 70% | 完整實施、測試、接入運行時 |
| B — 部分 | 18 | 19% | 代碼存在但不完整或未完全接入 |
| C — 佔位符 | 8 | 8% | 結構存在但邏輯為空 |
| D — 缺失 | 2 | 2% | 無任何代碼 |

---

## 二、Gap 優先級矩陣

### 🔴 CRITICAL — Live 前必須完成

| ID | Gap | 規格 | 影響 | 工作量 |
|----|-----|------|------|--------|
| G-01 | **H0 Gate 確定性門控** | DOC-02 | 每筆交易缺乏 <1ms 首道安全閘 | 2-3 天 |
| G-02 | **Cooldown 連續虧損暫停強化** | DOC-02 R06 | risk_manager.py:632 有 cooldown 檢查，但 paper_live_gate 的 max_consecutive_losses=10 未聯動 on_tick 路徑 | 0.5 天 |

### 🟡 HIGH — Paper Trading 穩定盈利前必須完成

| ID | Gap | 規格 | 影響 | 工作量 |
|----|-----|------|------|--------|
| G-03 | **L2 模式發現自動化** | EX-05 | 系統無法從交易歷史自動學習模式 | 3-5 天 |
| G-04 | **策略回測引擎** | EX-05 R08 | 無回測 = 無法驗證策略 alpha | 5-7 天 |
| G-05 | **Truth Source Registry 形式化** | EX-07 | 數據權威來源未強制執行 | 2 天 |
| G-06 | **M-of-N 簽名驗證** | SM-01 R13 | 框架存在但實際驗證未執行 | 1 天 |
| G-07 | **策略 Alpha 驗證** | DOC-04 | 當前策略（RSI/MACD/MA）無可證明 alpha | 持續 |

### 🟢 MEDIUM — 進化能力（可後期推進）

| ID | Gap | 規格 | 影響 | 工作量 |
|----|-----|------|------|--------|
| G-08 | **L3 假設與實驗管線** | EX-05 | 無法自動生成和驗證策略假設 | 5-7 天 |
| G-09 | **L4 策略進化** | EX-05 | 無法自動調優參數或生成新策略 | 7 天 |
| G-10 | **L5 元學習** | EX-05 | 無法自我校準和識別盲點 | 7 天 |
| G-11 | **數據品質驅動風控降級** | EX-07 §2.3 | 數據品質下降不自動觸發風控升級 | 2 天 |
| G-12 | **SM-04 延遲 SLA 驗證** | SM-04 R17 | CRITICAL→LOCKED <1ms 未實測驗證 | 1 天 |

---

## 三、開發路線圖（分 Phase）

### Phase 1: 安全閘補全 + 穩定性（預估 5 天）

**目標**: 補齊 CRITICAL 安全缺口，確保 Paper Trading 在完整治理框架下運行

```
Phase 1
├── Batch 1A: H0 Gate 實施（2 天）
│   ├── 新建 h0_gate.py（~300 行）
│   │   ├── FreshnessCheck: market_data.age < 1000ms
│   │   ├── HealthCheck: CPU<90%, mem>1GB, latency<100ms
│   │   ├── EligibilityCheck: product_family + capability_level
│   │   ├── RiskEnvelopeCheck: position/leverage/margin within P0/P1
│   │   └── CooldownCheck: consecutive_losses < threshold
│   ├── 接入 pipeline_bridge.py on_tick() 開頭（第一行檢查）
│   ├── SLA 驗證: <1ms 執行，純記憶體，零外部調用
│   └── 測試: 30+ 單元測試 + SLA benchmark
│
├── Batch 1B: Cooldown 接入主路徑（0.5 天）
│   ├── paper_live_gate.py max_consecutive_losses 已定義（=10）
│   ├── 接入: pipeline_bridge._process_pending_intents() 檢查 cooldown 狀態
│   ├── 連敗 N 次 → 自動暫停新開倉（仍允許平倉）
│   └── 測試: 10+ 測試
│
├── Batch 1C: M-of-N 簽名強化（1 天）
│   ├── authorization_state_machine.py 框架已有 AuthInitiator
│   ├── 實施: 實際簽名驗證（至少 1-of-1 baseline）
│   ├── Operator approve 時記錄簽名者身份
│   └── 測試: 15+ 測試
│
└── Batch 1D: 數據品質→風控聯動（1.5 天）
    ├── perception_data_plane.py STALE/EXPIRED 觸發
    ├── → risk_governor_state_machine.py escalation
    ├── 數據品質 < threshold → 風控升級一級
    └── 測試: 10+ 測試
```

**Phase 1 驗收**: H0 Gate <1ms · Cooldown 接入 · 全量測試 2,300+ 通過

---

### Phase 2: 學習回路閉環 + 策略驗證（預估 10 天）

**目標**: 讓系統能從交易歷史中學習，並具備策略回測驗證能力

```
Phase 2
├── Batch 2A: L2 模式發現完整接通（3 天）
│   ├── analyst_agent.py: Qwen analyze_patterns() 真正調用
│   ├── PatternInsight: winning_patterns + losing_patterns + regime_strategy_matrix
│   ├── 自動觸發: observations ≥ 200（已定義）→ 真正執行
│   ├── 結果持久化: patterns 寫入 learning_state
│   └── 測試: 20+ 測試（含 Ollama mock）
│
├── Batch 2B: 回測引擎 MVP（5 天）
│   ├── 新建 backtesting_engine.py（~500 行）
│   │   ├── 歷史 kline 數據回放
│   │   ├── 策略信號回測
│   │   ├── Sharpe / MaxDrawdown / WinRate 計算
│   │   ├── 滑點 + 手續費模擬
│   │   └── 與現有 5 策略整合
│   ├── 新建 tests/test_backtesting_engine.py（30+ 測試）
│   ├── CLI 或 API 觸發回測
│   └── 結果寫入 analyst_agent 供 L2 消費
│
└── Batch 2C: Truth Source Registry 形式化（2 天）
    ├── 新建 truth_source_registry.py（~150 行）
    │   ├── 每種數據類型的權威來源聲明
    │   ├── 衝突解決規則（exchange_ws > exchange_rest > calculated）
    │   └── 查詢介面: get_canonical_source(data_type)
    ├── 接入 perception_data_plane.py
    └── 測試: 15+ 測試
```

**Phase 2 驗收**: L2 patterns 自動產出 · 回測 Sharpe 可計算 · 2,350+ 測試通過

---

### Phase 3: 策略 Alpha 提升 + 自動化進化（預估 15 天）

**目標**: 從「教科書指標」升級到「可驗證 alpha」的策略體系

```
Phase 3
├── Batch 3A: L3 假設-實驗管線（5 天）
│   ├── 從 L2 PatternInsight 自動生成可測試假設
│   ├── 假設 → 回測引擎驗證 → 統計顯著性檢定
│   ├── 通過假設 → 建議參數調整
│   └── 結果回饋 LearningTierGate
│
├── Batch 3B: L4 策略參數進化（5 天）
│   ├── 基於 L3 驗證結果自動調優策略參數
│   ├── 新策略變體 → Paper Trading 7 天 shadow
│   ├── Shadow 通過（Sharpe ≥ baseline）→ 限量部署（50%）
│   ├── 限量通過（7 天）→ 全量部署
│   └── Sharpe 下降 > 50% → 自動回滾（EX-05 R15）
│
├── Batch 3C: 策略多樣性擴展（3 天）
│   ├── 基於 regime 匹配的策略選擇 AI 化
│   ├── Strategist 用 Qwen 評估 regime-strategy 適配度
│   ├── Kelly criterion 動態倉位算法
│   └── 回測驗證新策略組合
│
└── Batch 3D: SM-04 SLA + 壓力測試（2 天）
    ├── CRITICAL→LOCKED <1ms 實測驗證
    ├── 極端市場模擬（flash crash、API timeout）
    └── 全鏈路壓力測試
```

**Phase 3 驗收**: 策略回測 Sharpe > 0.5 · 自動進化管線 shadow → limited → full · 2,500+ 測試

---

### Phase 4: Paper→Live 準備（預估 5 天）

**目標**: 滿足 PaperLiveGate 11 項準入評估，準備 Live 授權

```
Phase 4
├── Batch 4A: Paper Trading 觀察期（21 天自然時間）
│   ├── 系統連續運行，收集交易數據
│   ├── 自動日報（Telegram + cron_daily_report.sh）
│   ├── L1 觀察自動累積
│   └── PaperLiveGate 11 項持續評估
│
├── Batch 4B: PaperLiveGate 全項通過驗證（2 天工程）
│   ├── Tier gate ≥ L2
│   ├── Duration ≥ 21 天
│   ├── Win rate > 40%
│   ├── Sharpe > 0.5
│   ├── Max drawdown < 15%
│   ├── Consecutive losses < 10
│   ├── Reconciliation pass rate > 99%
│   ├── Risk incidents = 0 (last 7 days)
│   ├── Guardian approval rate > 80%
│   ├── Operator approval: manual sign-off
│   └── System health: all green
│
└── Batch 4C: L5 元學習 + 最終文檔（3 天）
    ├── 自我校準機制
    ├── 盲點識別
    ├── 最終合規審計
    └── CLAUDE.md + README.md 最終更新
```

---

## 四、時間線總覽

```
Week 1 (W14)    Phase 1: H0 Gate + Cooldown + M-of-N + 數據品質聯動
Week 2-3 (W15-16) Phase 2: L2 自動化 + 回測引擎 + Truth Source
Week 4-6 (W17-19) Phase 3: L3-L4 進化管線 + 策略 Alpha + 壓力測試
Week 7-10 (W20-23) Phase 4: Paper Trading 觀察期 + Live 準備
```

| Phase | 工程天數 | 自然天數 | 累計測試 | 功能完成度 |
|-------|---------|---------|---------|-----------|
| 當前 | — | — | 2,227 | 76% |
| Phase 1 完成 | 5 | 7 | ~2,300 | 82% |
| Phase 2 完成 | 10 | 14 | ~2,400 | 88% |
| Phase 3 完成 | 15 | 21 | ~2,550 | 95% |
| Phase 4 完成 | 5+21觀察 | 35 | ~2,600 | 98% |

---

## 五、關鍵決策點（需 Operator 審批）

| # | 決策 | 時機 | 影響 |
|---|------|------|------|
| D-01 | H0 Gate SLA 標準（<1ms 是否可放寬到 <5ms） | Phase 1 開始前 | 影響實施複雜度 |
| D-02 | 回測數據來源（歷史 kline 本地存儲 vs API 回拉） | Phase 2 開始前 | 影響基礎設施需求 |
| D-03 | L4 自動部署策略是否需要 Operator 確認 | Phase 3 中 | 影響自主權範圍 |
| D-04 | Paper Trading 最低觀察期（21 天 vs 30 天） | Phase 4 開始前 | 影響 Live 時間表 |
| D-05 | Live 授權審批流程（M-of-N 中 M 和 N 的值） | Phase 4 結束前 | 影響安全等級 |

---

## 六、風險與緩解

| 風險 | 概率 | 影響 | 緩解 |
|------|------|------|------|
| 策略回測結果不佳（Sharpe < 0.5） | 高 | 延遲 Phase 3-4 | L3 假設管線 + 策略多樣性擴展 |
| Ollama/Qwen 推理延遲影響 H0 SLA | 中 | H0 Gate 需要調整 | H0 是純記憶體計算，不調用 AI |
| Paper Trading 觀察期數據不足 | 低 | 延長觀察期 | 21 天最低，可加速到 14 天（需 OP 批准） |
| L4 自動策略部署引入回歸 | 中 | 交易表現下降 | Shadow→Limited→Full 三階段 + auto-rollback |

---

## 七、與 22 份治理文件的完整對照

| 文件 | 狀態 | Phase |
|------|------|-------|
| DOC-01 核心風險教條 | ✅ 14/16 原則已實施 | P1 補齊 §5.10/§5.12 |
| DOC-02 掃描與監控 | ❌ H0 Gate 缺失 | **P1 Batch 1A** |
| DOC-03 市場 Regime | ✅ 已實施（market_regime.py） | — |
| DOC-04 Agent 學習進化 | ⚠️ L1-L2 部分 | P2-P3 |
| DOC-06 變更審計日誌 | ✅ 已實施（change_audit_log.py） | — |
| DOC-08 多 Agent 架構 | ✅ 5 Agent 全接線 | — |
| SM-01 授權狀態機 | ✅ 8 態完整 | P1 Batch 1C (M-of-N) |
| SM-02 決策租約 | ✅ 9 態完整 | — |
| SM-03 OMS 狀態機 | ✅ 11 態已串聯 | — |
| SM-04 風控治理者 | ✅ 6 級完整 | P3 Batch 3D (SLA 驗證) |
| EX-01 保護與反狩獵 | ✅ 雙重防線 + 組合風控 | — |
| EX-02 OMS 訂單生命周期 | ✅ 11 態 | — |
| EX-04 對賬引擎 | ✅ 5 次重試 + 升級 | — |
| EX-05 學習層級與自主權 | ⚠️ L1 運行，L2 部分，L3-L5 佔位 | **P2-P3 重點** |
| EX-06 Agent 衝突仲裁 | ✅ Guardian 否決權 | — |
| EX-07 Agent 數據存取控制 | ⚠️ 框架存在，強制執行不完整 | P1 Batch 1D + P2 Batch 2C |
| HIST-01 設計概覽 | ✅ 歷史文件，無新需求 | — |

---

## 八、立即可執行的下一步

**Phase 1 Batch 1A（H0 Gate）可立即開始。** 無外部依賴，純新文件創建 + 管線注入。

建議 Cowork Session 分配：
- **Session 1**: Batch 1A + 1B（H0 Gate + Cooldown）— 一個 Cowork Session
- **Session 2**: Batch 1C + 1D（M-of-N + 數據品質聯動）— 一個 Cowork Session
- **Session 3**: Batch 2A（L2 完整接通）— 一個 Cowork Session
- **Session 4**: Batch 2B（回測引擎 MVP）— 一個 Cowork Session（較大）

等待 Operator 確認後開始執行。
