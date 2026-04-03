# CLAUDE_CHANGELOG.md — 開發歷史歸檔

> 從 CLAUDE.md 遷出的 Wave/Sprint/Batch 歷史記錄。新 session 不需要讀此文件，僅供回顧歷史時查閱。
> 最後更新：2026-04-03

---

### Agent 認知自適應 SPEC V1.1+R1 五角色審查通過（2026-04-03）

**內容**：V3 報告補充規範，三個 L0 新模組的完整設計（零 API 成本，純本地計算）

- **CognitiveModulator**（0.5d）：根據歷史表現動態調整 confidence floor / qty ceiling / SL multiplier / scan interval
- **OpportunityTracker**（1.0d）：追蹤被 Scout/Strategist/Guardian 篩掉的機會虛擬 PnL → 遺憾歸因
- **DreamEngine**（2.0d）：閒置時用真實 K 線跑蒙特卡洛模擬 → 參數優化建議

**五角色審查（PM/PA/FA/E5/QC）+ 兩輪審計**：
- QC 數學修正 6 項：多因子取 max（防隱性停機）· 虛擬 PnL 扣 fee（防系統性高估）· 歸一化遺憾方向 · 每參數 ≥30 輪模擬 · binomial test 置信度 · EMA 平滑
- E5 代碼修正 6 項：拆分 _compute_*() · bullets_dodged 重命名 · _flush_closed · 緩存 · threading.Lock · 隨機方向
- Round 1 修正 10 項：scan 雙向 · 緩存失效 · 防重入 · asyncio.to_thread · 連虧忽略負向 · import 頂層 · 估時調整 · 最少 5 樣本 · fee 注釋 · 可選 seed
- 最終判定：5/5 APPROVE
- 開發位置：Phase 1 並行組 B（1.10/1.11/1.12），總計 3.5d，不影響關鍵路徑
- SPEC 文件：`docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md`

---

## Wave 進度總表（§十三.4 遷出）

```
Wave 0：✅ P0（5 項）全部完成 + P1（5 項）全部完成（E2+E4 通過）
Wave 1：✅ PA-4.3 DI 統一（26 Depends）+ HTTPException 穿透（E2+E4 通過）
Wave 2：✅ P0-8/P1-1/P1-2/P1-6/P1-8/P1-9/P1-13/P1-18 全部完成（E2+E4 通過）
Wave 3a：✅ P0-NEW-1/2/3 全部完成（E2+E4 通過，commit c6a8845）
Wave 3b：✅ P1-NEW-1~7 全部完成（E2+E4 通過，commit 2eda4ec）
Wave 3c：✅ P1-4/P1-10/P1-17 完成（E2+E4 通過，commit bf75254）
P1-16：✅ Day 1+2+3 全部完成，已 merge（commit 03a5b29）
Wave 4 Sprint 4a：✅ P2-NEW-1/2/6（commit a2f4c70）
Wave 4 Sprint 4b：✅ P2-NEW-3/4 + P3-TECH-1/2/3（commit 6c80bc9）
Wave 4 Sprint 4c：✅ P2-NEW-7/8（commit 448f1e7）
Wave 4 Sprint 4d：✅ FA-2/3/4（commit 9cc134a）
Wave 4 Sprint 4e：✅ P2-NEW-9 + P2-NEW-5（commit 87c2651）
Wave 5a：✅ Position Sizing 重構 — 3% risk + 動態 qty + 智能資本再分配（commit 8223eb9）
Wave 5b：✅ Paper/Demo 同步修復 — 3 CRITICAL + 2 MODERATE
Wave 5 Sprint 0：✅ G-05 acquire_lease + G-01 AI daily cap $15→$2（commit d57ed05）
Wave 5 Sprint 5a：✅ H0 blocking + H1 ThoughtGate + shadow=False + H2/H3 ModelRouter（commit ccdff73）
Wave 5 Sprint 5b：✅ H4 validate_output + H5 record_ollama_call + ScoutWorker + P14 集成測試（commit 9478c00）
Wave 6 Sprint 0：✅ TD-1 pipeline_bridge acquire_lease（原則 3 缺口）（commit aafb18b）
Wave 6 Sprint 1a：✅ FA-7 _check_stops 學習管線注入（原則 12）（commit 8f123a7）
Wave 6 Sprint 1b：✅ 1B-1~4 Cooldown + freshness + cost_tracker + LRU cap（commit 8f123a7）
Wave 6 Sprint 2：✅ P2-6/7/8 risk bounds + P2-12/15 pipeline edge（commit 43dd2f5）
Cleanup Sprint：✅ H0 stale→False + GovernanceHub API + startup integrity + MessageBus load tests（commit 973c595）
Phase 2 Batch 2A：✅ TruthSourceRegistry + Agent 集成 + 46 測試（commit cf7ef5d）
Phase 2 Batch 2B：✅ BacktestEngine MVP + 57 測試（commit cf7ef5d）
Phase 2 Batch 2C：✅ _register_pattern_claims 接通 + backtest_routes + 決策權重集成（commit 5794db1）
Demo 停止補強：✅ cancel_all_orders() + 停止序列改進（commit 2fba698）
Wave 7：✅ Demo 同步修復 — Paper 內部平倉 Demo 同步 + stop_session 自動清倉（commit ab31353）
Wave 7a：✅ Spot 品類啟用 — SPOT-1~5（commit 054d1ae）
方案 A：✅ SymbolCategoryRegistry — 啟動時 API 批量填充（commit a0f87b6）
Wave 7b：✅ Inverse 品類完善 — INV-1~5，32 個測試，動態滑點
Phase 3 Batch 3A：✅ ExperimentLedger + ExperimentRoutes + EvolutionEngine — 88 新測試，3289 passed
Phase 3 Batch 3B+3A-4：✅ TruthSourceRegistry 持久化 + auto_seed + EvolutionRoutes — 3310 passed
Phase 3 Batch 3C：✅ 排程器 daemon + GUI 實驗/進化 dashboard — 3330 passed
Governance Auth 修復：✅ get_status() + /session/reauth + startup 自動補授（commit d065453）
April 1 Audit Batch 1-6：✅ 8 份審計 + 6 批次全部完成 — 3387 passed
Batch 7 積壓清掃：✅ 8 並行 Agent — 3440 passed
main_legacy.py 重構 Wave A-D：✅ 5265→423 行（-92%），拆出 8 模塊，3005 tests 零回歸
Wave 8 PA 實況檢查：✅ 69 項審計交叉驗證 → 38/39 項修復，+148 新測試達 3637+
```

---

## §三 詳細開發記錄（按時間順序）

### Round 2 冷酷功能審核（2026-03-30）

代碼完成度 ≈ 80%，業務功能真正能用 ≈ 45%

逐環節完成度：
- 自動掃描 = 90%（ScoutWorker 30min 定時掃描 + Scout→Strategist bus 鏈路已接通）
- 策略選擇 = 40%（標準技術指標，無 AI、無回測、無動態倉位）
- AI 風險評估 = 55%（H0+H1+H2+H3+H4+H5 全部接通）
- 下單 = 90%（治理 gate + OMS SM-03 + ExecutorAgent 包裝）
- 止損 = 90%（本地 3 類止損 + 交易所條件單雙重防線）
- 學習 = 25%（E1 觀察 + L2 自動觸發 + Sunday cron）
- 進化 = 30%（PaperLiveGate 已部署，無策略自動優化）

關鍵發現：
- ✅ 治理 fail-closed 一流 / P0/P1/P2 風控真實執行 / 異常處理防禦性
- ✅ 5/6 Agent 已實現 / ExecutorAgent 接入管線 / L2 自動觸發
- ❌ Perception Plane register_data() 零調用
- ❌ 策略層標準 RSI/MACD/MA，無可證明的 alpha

詳細報告：docs/governance_dev/audits/2026-03-30--round2_cold_functional_audit.md

### Phase 0 Cowork Round 2.5 審計（2026-03-31）

- P0 修復：MessageBus.subscribe() 3→2 參數 bug / layer2_engine "not worth" 文本解析 bug
- 287 條治理規格 Gap 分析：76% 已實施（67A + 18B + 8C + 2D）
- 關鍵缺失：H0 Gate / 回測引擎 / L3-L5 學習
- 詳細報告：docs/governance_dev/audits/2026-03-31--gap_analysis_287_specs.md

### 7-Agent 全系統審計（2026-03-31）

規模：71 測試文件 / 2,480 測試用例 / 53 app 模組 / 全 HTML/JS/CSS
發現：71 項問題（去重）· P0: 8 / P1: 18 / P2: 29 / P3: 16

4 個 CRITICAL 問題（全部已修復）：
1. /openclaw/{path} 反向代理添加認證
2. _require_operator_role() isinstance 類型錯誤
3. GovernanceHub=None 時 submit_order() fail-closed
4. Guardian=None 時 pipeline_bridge.py fail-closed

合規度 CC B 級 / 安全評級 0 CRITICAL / 0 HIGH / 2 MEDIUM / 3 LOW

### Wave 5a Position Sizing 重構（2026-03-31）

- risk_per_trade_pct 2%→3%（每筆最大虧損 = 總額 3%）
- max_symbols 10→25
- 動態 qty + 智能資本再分配 + risk/stop 反推名義金額

### Wave 5b Paper/Demo 同步修復（2026-03-31）

3 CRITICAL + 2 MODERATE：止損同步 / 失敗標記 / 對賬參數名 / qty 統一 / 條件止損 qty

### Wave 5 Sprint 0 BLOCKER 修復（2026-03-31 · commit d57ed05）

- G-05：executor_agent.py 插入 acquire_lease()（原則 3 硬違反修復）
- G-01：DEFAULT_DAILY_HARD_CAP_USD 15.0→2.0

### Wave 5 Sprint 5a H1-H5 核心接通（2026-03-31 · commit ccdff73）

Scout→Strategist bus 鏈路 / H0 blocking / H1 ThoughtGate MVP / shadow=False / H2 預算 / H3 ModelRouter

### Wave 5 Sprint 5b Agent 落地完善（2026-03-31 · commit 9478c00）

H4 AI 輸出驗證 / H5 CostLogger / apply_ai_consultation DEPRECATED / ScoutWorker daemon / P14 集成測試

### Wave 6 Sprint 0-2（2026-03-31）

- Sprint 0：pipeline_bridge acquire_lease（原則 3 缺口）
- Sprint 1a：_check_stops 學習管線注入（原則 12）
- Sprint 1b：Cooldown smoke test + freshness API + cost_tracker + LRU cap
- Sprint 2：RiskManager qty/price bounds + pipeline edge + collect DEPRECATED + GUI null fix

### Cleanup Sprint（2026-03-31 · commit 973c595）

H0 stale→False / GovernanceHub.is_globally_enabled() / startup integrity check / MessageBus load tests

### Phase 2 Batch 2A-2C（2026-03-31 ~ 2026-04-01）

- 2A：TruthSourceRegistry + AnalystAgent/StrategistAgent 集成 + 46 測試
- 2B：BacktestEngine MVP（純函數指標 + _BacktestKlineAdapter + 57 測試）
- 2C：_register_pattern_claims 接通 + backtest_routes API + 決策權重集成

### Demo 停止清倉補強 + Wave 7 Demo 同步（2026-04-01）

- cancel_all_orders()（普通單 + 條件單）
- Paper 內部平倉 Demo 同步：_sync_close_to_demo() / stop_session 雙遍歷清倉

### Wave 7a Spot + 方案 A SymbolCategoryRegistry + Wave 7b Inverse（2026-04-01）

- Spot 品類：SPOT-1~5 全通（634 幣對）
- SymbolCategoryRegistry：啟動時 API 批量填充 + 運行時部署更新雙層架構
- Inverse 品類：INV-1~5 全通（27 幣對）+ 動態滑點分級

### Phase 3 Batch 3A-3C（2026-04-01）

- 3A：ExperimentLedger + ExperimentRoutes + EvolutionEngine（88 新測試）
- 3B+3A-4：TruthSourceRegistry 持久化 + auto_seed + EvolutionRoutes
- 3C：EvolutionScheduler daemon（週進化 + 小時清理）+ GUI dashboard

### Governance Auth 重啟丟失修復（2026-04-01 · commit d065453）

根因：GovernanceHub 授權為純記憶體狀態，重啟後歸零
修復：get_status() auth_pending_approval + /session/reauth 端點 + startup 自動補授

### April 1 全系統審計 + 6 Batch 修復（2026-04-01）

審計：AI-E(B+) / E5(54項) / E4(3310/96files/~68%) / E3(0C/1H/5M/4L) / CC(A-,14/16) / FA(52%) / TW(82.5%) / R4(12項)
Batch 1-6 全部完成：知識閉環 / BacktestEngine 285x / L2 快取 / HttpOnly cookie / 鎖縮窄

### Batch 7 積壓清掃（2026-04-01）

pipeline_bridge 拆分 / Conductor 編排 / 194 logger %s / Pydantic 驗證 / MODULE_NOTE 補全

### main_legacy.py 重構 Wave A-D（2026-04-01）

```
Wave A：state_models + state_compiler + state_store = -1210 行（5265→4056）
Wave B：auth + state_helpers = -297 行（4099→3802）
Wave C：control_ops + pnl_ops + learning_ops = -2363 行（3802→1439）
Wave D：legacy_routes = -1016 行（1439→423）
總計：-92%，拆出 8 模塊，3005 tests 零回歸
```

### Wave 8 PA 實況檢查 + 並行修復（2026-04-01）

PA 交叉驗證：69 項審計結果逐一比對代碼（29 確認/10 部分/20 已修/10 誤報）
6 軌道並行 × 2 批次 = 38/39 項完成
- Wave 8A 安全+正確性（8 項）
- Wave 8B 代碼質量（12 項）
- Wave 8C 架構改進（7 項）：strategist 1152→780 行拆 4 模組
- Wave 8D 文檔清理（5 項）
- B3+B4 核心拆分：on_tick 4 子方法 + mutator 5 子函數
commits: 533a71a + 4782c96 + 6b494a6 · +148 新測試

### FA 完成度與 GAP 審核（2026-04-01）

代碼完成度 ~80%，業務功能真正能用 ~52%
7 項關鍵 GAP：
- P0-GAP-1：學習反饋閉環斷開
- P0-GAP-2：進化參數不自動重部署
- P1-GAP-3：H0 Gate warn-only
- P1-GAP-4：交易所條件單未實作
- P1-GAP-5：MarketScanner → Deployer 未接通
- P1-GAP-6：Backtest 生產環境未啟用
- P2-GAP-7：L2 觸發門檻過高
詳細報告：docs/governance_dev/audits/2026-04-01--fa_completion_gap_audit.md

### P0 ~ Wave 3c 修復記錄（2026-03-31）

- P0 修復（5 E1 並行）：governance_routes isinstance / pipeline_bridge Guardian=None / paper_engine Hub=None / openclaw_proxy 認證 / layer2_engine negation
- Wave 0 P1：ollama max_retries=0 / subprocess 分隔符 / 日誌路徑 / 憑證緩存 / 日誌注入修復
- Wave 1：DI 統一（26 Depends）+ HTTPException 穿透
- Wave 2：compile_state cache / auth 速率限制 / XSS / governance env var / 測試覆蓋補強
- Wave 3a：/reconcile 角色驗證 / detail=str(e)→固定字串
- Wave 3b：proxy header 過濾 / WeakKeyDict / asyncio.Lock / token 統一 / _OC_HOST 緩存
- Wave 3c：lease expires_at_ms / PerceptionPlane 測試 / is_authorized 鎖修復

### H0 Gate（P1-16）三天實現（2026-03-31）

- Day 1：h0_gate.py 651 行，5 個確定性 check，SLA <5μs
- Day 2：H0HealthWorker 背景線程，40 測試，SLA <0.5ms avg
- Day 3：Pipeline/Routes/Risk 集成，18 集成測試

### GUI + Ollama 優化（2026-03-31）

- Paper+Demo 合併為「測試交易」子 Tab + 「實盤交易」鎖定占位 Tab
- think=False 修復：9B 8.7s→1.9s，27B 21s→9.9s
- 模型分配：9B 快速路徑 / 27B 複雜任務 / ScoutWorker daemon
- 後台市場流常駐 / 週報雙層（Ollama + Claude L2）

---

## §十一 已完成的路線圖（歷史歸檔）

```
已完成摘要：
  ✅ A-L 全部章節 + 策略工具包 + 管線橋接 + 全系統審核
  ✅ GUI 三層架構 + 11-Tab 專業控制台
  ✅ 自主交易 Agent（市場掃描器 650 符號 + 策略自動部署）
  ✅ Phase 2 治理模組 T2.01–T2.23（21 模組 · 1,522 測試）
  ✅ Phase 3 GovernanceHub 集成（4SM 接入 + 安全審核）
  ✅ Round 2 Batch 3-12 全部完成（5 Agent + OMS + PaperLiveGate + E2E）
  ✅ L1 本地推理（Ollama + Qwen 3.5）+ 0% 勝率四根因全修復
  ✅ 7-Agent 全系統審計（71 項問題 · 4 CRITICAL · 全部修復）
  ✅ Wave 0-8 全部完成
  ✅ Phase 1-3 開發路線圖全部完成
  ✅ main_legacy.py 重構完成（-92%）

開發路線圖 v2（已完成）：
  Phase 1: H0 Gate ✅ + Cooldown 聯動 ✅
  Phase 2: TruthSourceRegistry ✅ + BacktestEngine ✅
  Phase 3: ExperimentLedger ✅ + EvolutionEngine ✅ + EvolutionScheduler ✅
```
