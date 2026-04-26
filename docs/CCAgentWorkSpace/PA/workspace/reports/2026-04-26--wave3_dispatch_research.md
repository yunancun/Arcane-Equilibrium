# Wave 3 派發架構研究 — PA Report

**日期**：2026-04-26
**作用**：回答 PM 提出的 4 個 Wave 3（W20-W23）派發前研究問題
**範圍**：G8-01 / G8-02 / G8-04 RFC + Wave 3 撞檔風險矩陣
**文件指針**：
- `srv/TODO.md:275-313`（Wave 3 表）
- `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_shadow_to_live_e2e.py`（556 LOC，G3-04 baseline）
- `srv/program_code/local_model_tools/cognitive_modulator.py`（193 LOC，唯一存在的「認知自適應」實體）
- `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_agent.py:226,1101-1159`（CognitiveModulator 注入點）
- `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_config_cache.py`（G3-03 Phase B 435 LOC，parity 主目標）
- `srv/helper_scripts/db/passive_wait_healthcheck.py`（1955 LOC，17 check + Xa/Xb）

---

## 問題 1：G8-01 e2e 認知自適應 80+ coverage RFC

### 結論：**新寫獨立套件 + 必要時擴 G3-04**，不是「補擴 G3-04」

**理由**：G3-04 範圍是 ExecutorAgent shadow→live IPC chain（cache poll → flip → SubmitOrder mock），與「認知自適應」屬不同維度的 cross-cut。把兩件事擠進同檔會破壞測試 cohesion，且 G3-04 mock 邊界（`_fetch_via_ipc_blocking` / `paper_trading_routes._ipc_command`）不適合 stub StrategistAgent + CognitiveModulator 的 update loop。

### 範圍邊界（重要 scope check）

PM profile.md 第 20 行「認知自適應模組排程」的三模組中：
- **CognitiveModulator** ✅ 存在（193 LOC，5 個 _compute_* 計算 confidence_floor / qty_ceiling / stoploss_mult / scan_interval）
- **OpportunityTracker** ❌ **代碼不存在**（grep 全 program_code 0 命中）
- **DreamEngine** ❌ **代碼不存在**（strategist_agent.py:838 只引用 `cognitive_modulator.last_dream_summary` 屬性，沒對應實體類）

**派發風險（給 E1 / E4 警示）**：G8-01 若被讀為「三模組覆蓋 80%」會立刻撞 NotImplementedError。**建議重新校準完成標準**：
- (a) CognitiveModulator 五個 _compute_* + update + getters：100% 行覆蓋（193 LOC × 0.95 ≈ 184 LOC 可覆蓋）
- (b) StrategistAgent 注入點（set_cognitive_modulator + 兩處 dream summary fallback）：integration 級
- (c) OpportunityTracker / DreamEngine 列**標記 deferred**，不計入 80% 分母

### 預期 LOC + 結構

```
tests/test_cognitive_adaptation_e2e.py        ~400-500 LOC（新檔）
  ├─ TestModulatorBoundaries (5 case · pure)   每個 _compute_* 的 clamp + edge
  ├─ TestModulatorUpdate (3 case · pure)       update() 連續 call 收斂
  ├─ TestStrategistInjection (2 case · mock)   set_cognitive_modulator 後 _ai_evaluate 能讀到 cog_params
  ├─ TestFailClosed (2 case · mock)            modulator=None 時 default 不爆
  └─ TestPersistedDreamFallback (1 case)       last_dream_summary 屬性 None / dict 兩路徑
```

完成標準改為「**CognitiveModulator 模組 ≥85% line coverage** + StrategistAgent 注入點 integration 綠 + OpportunityTracker/DreamEngine 留 TODO marker」。比原 80+ 嚴格但 scope 真實。

---

## 問題 2：G8-02 Python↔Rust parity ≥95% 測試設計

### 已存在 baseline：`test_bybit_rest_client_parity.py`（grep 命中）
名字相似但測 PYO3-ELIMINATE 後 httpx 純 Python client vs 舊 rust signature parity，**不是** Python ExecutorConfigCache snapshot 與 Rust `RiskConfig.executor` 的決策對齊。G8-02 必須新寫。

### "Decision agree" 定義（建議精準化）

決策點 = 進入唯一寫入口前所有可分歧路徑。Wave 2 完工後 ExecutorAgent 可分歧的 **3 個 decision points**：

1. **shadow_mode 判斷**：cache.shadow_mode_provider() vs Rust `RiskConfig.executor.shadow_mode`
2. **per_symbol_position_cap 觸發**：Python ExecutorAgent guard vs Rust intent_processor on SubmitOrder（防禦深度第二道）
3. **max_position_pct envelope check**：與上同

**不算 decision point**（因不在 ExecutorConfig scope）：cost_gate / 5-gate live auth / Reconciler 自動降級 / Hurst regime — 這些屬其他 Config 子切片，G8-02 應**僅** scope 到 RiskConfig.executor 三欄。

### 測試方法選擇（建議 golden-fixture + record-replay 混合）

| 方法 | 適合場景 | 缺點 |
|---|---|---|
| **Golden fixture（推薦主力）** | 100 個 (state, intent) 元組，固定預期決策表 | 維護成本，但決策點數量少時可控 |
| **Record-replay** | 從 demo runtime IPC log 取 1d 樣本 | demo 0 真 shadow flip → 樣本偏 |
| **Synthetic property-based（hypothesis）** | 邊界、隨機 shadow_mode true/false | 過度測試，<95% 可能因 outlier 觸發 |

**派發建議**：用 50 golden fixture（手挑 + 涵蓋 shadow on/off × cap hit/clear × pct 邊界 × 異常 None）+ 20 random replay = 70 cases，目標 67/70 = 95.7% agree。

### 95% 樣本級 vs case 級

**case 級**（每 fixture 兩端 decision 必須完全相等才 PASS）。樣本級在 binary decision 沒意義（只有 0% / 100%）。case 級 95.0% = 70 中允許 ≤3 disagree，與 Rust intent_processor 防禦深度第二道對齊（Rust 守住即使 Python 漏掉 5%）。

---

## 問題 3：G8-04 healthcheck DAG 線性化

### 當前狀態（讀 1955 LOC + grep 18 個 check fn）

**結構**：18 個 `check_*` 平鋪函數，main() 順序 if-else 取 close_fills_24h，後續 ratio check 透過 close_fills 參數**手動傳遞**形成隱性依賴。已有「fan-out 依賴」實質出現於 [2]/[3]/[10] 都依賴 [1]。

### "線性化 DAG" 真實含義

PA 解讀：**將隱性 fan-out 依賴顯化** — 不是視覺化 / 拓樸排序，而是：
1. 把 close_fills_24h 改為**前置 dependency node**，下游 check 顯式 declare `depends_on=["close_fills_24h"]`
2. 提供 `--show-dag` flag 印依賴樹，operator 可看哪些 check 因前置 FAIL 被 skip
3. 提供 `--check <id>` 單跑某 check（偵錯時 17 全跑太重）

### **ROI 評估：建議降級 backlog**

理由：
- 17 check 平鋪當前可讀（每個 check 200-50 LOC，獨立可維護）
- 隱性依賴只 2 層深（[1] → ratio check group），實質 DAG 退化線性
- "real pain" 信號未出現（cron 6h 跑無故障）
- 若 G8-01/02 / G2-06 同期競爭工時，G8-04 屬 cosmetic refactor

**PM 派發建議**：標 backlog，待 ≥1 個「healthcheck 假 PASS（前置壞但下游當資料缺失 PASS）」事件觸發再啟。**不阻塞 Wave 3 收尾**。

---

## 問題 4：Wave 3 派發風險矩陣

### 三項 critical-path 派發策略

| 項目 | 主操作檔 | Isolation 建議 | 理由 |
|---|---|---|---|
| **G2-06** bb_breakout calibrate | `helper_scripts/research/bb_breakout_threshold_sweep.py`（已存在 read-only sweep）+ `rust/.../bb_breakout/params.rs` TOML 寫值 | **isolation worktree** | 動 Rust 策略 params.rs + 3-env TOML 同 G7-03-Phase-B-FUP-grid 撞區（grid_trading WIP merge 隊列已存在） |
| **G8-01** 認知自適應 e2e | `tests/test_cognitive_adaptation_e2e.py`（新檔，純測試）| 主 work tree（**non-isolation**）| 純新測試檔，不動 production；CognitiveModulator 193 LOC 不會被改 |
| **G8-02** Python↔Rust parity | `tests/test_executor_decision_parity.py`（新檔）| 主 work tree（**non-isolation**）| 純新測試檔；Rust 端只讀 `RiskConfig.executor`，不寫 Rust 碼 |

### 並行可行性

- **G8-01 + G8-02 完全並行**（不同 test 檔，不動 Rust，主 work tree OK）
- **G2-06 隔離跑**（修 Rust params.rs + TOML，與 G7-03-Phase-B-FUP-grid / G5-01 main.rs 拆分潛在撞區）
- **G2-06 + G8-01 + G8-02 三項可並行**（一隔離 + 二主樹）

### High-risk merge conflict 預警（PM 必看）

1. **G2-06 vs G7-03-Phase-B-FUP-grid** 🔴：兩者都動 grid_trading 區（後者 5 檔 WIP；前者調 bb_breakout 但若操作過界誤改 grid 索引就撞）。**建議**：等 FUP-grid 先 merge 再啟 G2-06。
2. **G8-01 vs G3-07/G3-08** 🟡：若 Wave 3 同時推 G3-07 Layer 2 工具箱 / G3-08 H1-H5 Rust IPC，會觸 strategist_agent.py（CognitiveModulator 注入點）。**建議**：G8-01 只用 mock，**禁止**改 strategist_agent.py production 行為。
3. **G8-04（若仍上架）vs healthcheck.py G6-FUP** 🟡：1955 LOC 單檔距 §九 1200 硬上限早已超，任何重構先 split 才動 — **再加分降級理由**。
4. **EDGE-P3 vs G2-06 共享前置 healthcheck [11]/[12]** 🟢：EDGE-P3 等 [11] clean ≥200，G2-06 觸發 [12] FAIL ≥7d；兩 check 獨立資料源不撞，但 PA 注意 **若 G2-06 後 [12] 復活**會重設 G2-05 觀察計時（design-by-intent，非 bug）。

---

## PM 派發建議（結論）

**Wave 3 啟動時序（建議）**：

1. **W20 立即啟動（並行）**：G8-01（主樹 / E4+QA / 2-3d）+ G8-02（主樹 / E4+QA / 1-2d）
2. **W20 觀察**：EDGE-DIAG-1 [11] 進度 + G2-05 healthcheck [12] 7d 計時（被動）
3. **W21**：G2-01 PostOnly fee 結算（被動結束）+ G2-02 ma_crossover counterfactual
4. **W21 條件啟動**：G2-06（**僅** healthcheck [12] FAIL ≥7d 後 + 隔離 worktree）
5. **W22-W23**：EDGE-P3 部署 + G2-04 grid 決策會
6. **G8-04 → backlog**（待真 pain 出現）

**完成標準調整建議**：
- G8-01：80% → "**CognitiveModulator ≥85% line cov + 注入點 integration 綠**"，OpportunityTracker/DreamEngine deferred 不計
- G8-02：≥95% → "**70 case 中 ≥67 agree（case-level binary）**，scope 限 RiskConfig.executor 三欄"
- G8-04：標 backlog，**Wave 3 完成標準移除**

**派發批次**：W20 第一批 = E4 主任跑 G8-01 + G8-02 雙線（**非** isolation 模式，純測試新檔不會撞）。E2 兩項各看一遍即可。整 Wave 3 2 isolation worktree 上限不會超。

---

**PA DESIGN DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--wave3_dispatch_research.md**
