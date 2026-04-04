# OpenClaw TODO — 工作計劃清單
# 最後更新：2026-04-04（R-CUT 7/7 PASS · RC-10/11/12 零重複系統 · 10/13 Rust-first · Phase 0a/0b 完成）
# 注意：compact 後從此文件恢復工作狀態
# ★ 排查參考：docs/KNOWN_ISSUES.md（已識別但未驗證的風險，遇到異常時先查）
# ★ 工程日誌：docs/worklogs/2026-04-04--daily_summary.md（整合日誌）

---

## ██ 每次啟動必做：引擎健康檢查 ██

**Rust 引擎為主交易引擎，獨立運行中。**

```bash
# 1. 引擎是否存活？
python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --status

# 2. canary 記錄數量
wc -l /tmp/openclaw/engine_results.jsonl

# 3. watchdog 崩潰記錄
grep -c "ENGINE_CRASH\|3-STRIKE" /tmp/openclaw/watchdog.log 2>/dev/null || echo "0 crashes"

# 4. 最新 tick
tail -1 /tmp/openclaw/engine_results.jsonl | python3 -c "
import sys,json; r=json.load(sys.stdin)
ps=r['paper_state']
print(f'tick #{r[\"tick_number\"]} | {r[\"symbol\"]} @ {r[\"price\"]}')
print(f'balance=\${ps[\"balance\"]:.2f} | fills={r[\"stats\"][\"total_fills\"]} | positions={len(ps[\"positions\"])}')
"
```

Go/No-Go：**2026-04-04 已通過 7/7**。重啟指引見 `docs/rust_migration/07--canary_greybox.md`。

---

## 強制工作流程

```
E1/E1a 並行（最多 5 路）→ E2 審查（強制）→ E4 回歸（強制）→ PM 確認 → commit
16 角色定義詳見 CLAUDE.md §八
```

### ★ Bybit API 開發必查

所有 Bybit 相關的修改/新功能，開發前必須先查閱：
- **字典手冊**：`docs/references/2026-04-04--bybit_api_reference.md`（64 REST + WS + IPC 全索引）
- **審計報告**：`docs/audits/2026-04-04--bybit_api_infra_audit.md`（路徑正確性 + 已知陷阱）
- 已有端點直接調用，不重複實現。新增端點完成後同步更新手冊。

---

## 測試基準線

```
Python: 3345 passed / Rust: 763 passed / Canary: 38 passed
Total:  4146 tests 全綠
注：10 flaky tests 已全部修復（RC-11 session，commit 4dc835a）
注：RC-11/RC-12 清理後 Python 測試數從 3839 降至 3345（重複/隔離修復 + 測試合併）
```

---

## 已完成項歸檔

```
Wave 0-7 / Phase 1-3 / Audit Batch 1-7 / main_legacy 重構：
  → docs/worklogs/control_api_gui/2026-04-01--completed_todo_archive.md

Batch 9A + XP-1~4 + Wave 8A-8D：
  → docs/worklogs/2026-04-03--completed_todo_archive_batch9a_wave8_xp.md

Phase 0-A/0-B/1/2/3 全部完成（[x] 26 項）+ Phase R-00~R-06 完成：
  → docs/worklogs/2026-04-04--completed_todo_archive_phase0123_rust.md

2026-04-04 Session（本次）：
  [x] 3-STRIKE Cold Start 修復（watchdog 45s + grace-period + force_write）
  [x] Phase 0a DDL 草稿 V001-V005（43 表 / 8 Schema / 29 hypertable）— DDL 複審 43/43 MATCH
  [x] tick_duration_us 添加到 CanaryRecord
  [x] Replay Mode B 實現（feed_replay_tick 100% 複用 on_tick）
  [x] 完整 201K tick replay 驗證基礎設施
  [x] Python ADX bug 修復（DX→ADX Wilder 平滑第三步）
  [x] Comparator key 映射（31+35 keys）+ bar-close filter + paper_state skip
  [x] Rust Hurst 安全修復（零價格防禦 + clamp + Kahan）
  [x] Rust KAMA SMA seed 對齊
  [x] Rust IndicatorSnapshot 擴展（+sma_50, ema_26, atr_5, conservative_atr）
  [x] Rust BB Breakout ATR trailing stop + regime exit
  [x] Python KAMA per-step SC 修復 + Stochastic Slow %K
  [x] Comparator 容差放寬（simple 1e-6, recursive 1e-2, complex 5e-2）
  [x] signal_generator 9x NoneType guard
  [x] QA 嚴格審計（Python V2 真實 62/100，6 項 FAKE/DEAD）
  [x] PYO3-1 推遲到 Phase 2（接口錯位）
  [x] Operator 決策：放棄修 Python，全力 Rust

SPEC 審查記錄：
  → 認知自適應：docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md
  → Rust 遷移：docs/references/2026-04-03--rust_migration_v3_final.md
  → Agent 調參：docs/references/2026-04-03--agent_param_tuning_design_draft_v0.2.md
```

---

## ██ 當前焦點：Rust 引擎完善 → 切換 → Go/No-Go ██

### Operator 決策（2026-04-04）
> **放棄修復 Python V2 交易引擎，全力完善 Rust。Python 只保留 API/GUI/Agent 層。**
> QA 審計：Python V2 真實成熟度 62/100，6 項功能 FAKE/DEAD/UNREACHABLE。
> 詳見：`docs/worklogs/2026-04-04--session_progress_1.md`

---

## ██ R-CUT：Rust 策略補齊 + 切換（4/5-4/10）

### 階段 1：Rust 策略補齊（4/5-4/7）

- [x] RC-01：MA Crossover regime filter — Hurst regime 過濾震盪市假信號
- [x] RC-02：MA Crossover multi-TF confirm — 簡化為 4h EMA proxy 確認
- [x] RC-03：BB Breakout volume/Donchian 直讀確認 + 參數可配置化
- [x] RC-04：所有策略 intent rejection rollback — on_rejection() + prev_* 快照
- [x] RC-05：所有策略 on_fill() sync — trait default no-op + tick_pipeline 接線
- [x] RC-06：Grid Trading geometric spacing + health check + auto-rebalance
- [x] RC-07：BB Reversion limit order（策略端真實實現，execution 層 Phase 2 補齊）
- [x] RC-08：StrategyParams trait + ParamRange 定義，實現留空 Phase 3a
- [x] RC-09：E2 審查 + E4 回歸 + QA Audit CONDITIONAL PASS

### 階段 2：最小切換（4/8-4/9）

- [x] RC-10：停止 Python tick_pipeline（2 處 activate() 註釋掉，PIPELINE_BRIDGE 保留供 API 查詢）
- [x] RC-11：刪除分類 A dead code（4 files / 1,003 行：shadow_decision_tracker/dream_engine/opportunity_tracker/strategy_health_monitor）
      — 註：原估 187 files 實為 Category B+C，需 R-IPC API 遷移後才能刪
- [x] RC-12：全量測試驗證 4507 全綠零回歸
- [x] RC-13：E2 + E4 PASS

### 階段 3：Go/No-Go（4/10）

- [x] RC-14：Go/No-Go 最終檢查 7/7 PASS（201K replay P50=27μs / RSS 2.1MB / 0 crash）
- [x] RC-15：Go/No-Go 評估報告撰寫

### 階段 4：Post-Go 清理（4/04 Session 2+3）

- [x] RC-11b：消除 Python/Rust 止損雙重執行（engine.tick() 停用 · commit 4dc835a）
- [x] RC-12b：停用 Python MarketDataDispatcher 自動啟動（重複 WS 連接 · commit f5d7192）
- [x] 10 個 flaky test 修復（Rust-first 格式 + 測試隔離 · commit 4dc835a）
- [x] GovernanceHub 5 死方法標記 deprecated（commit 4dc835a）
- [x] Klines 加入 Rust snapshot + get_klines Rust-first（commit 5979170）
- [x] get_indicators 全 timeframe Rust-first（commit 4f9836c）
- [x] 全面審計：零重複系統確認（tick/WS/stops/governance 全部單一路徑）

---

## ██ R-IPC：Rust IPC 擴展 + Python API 切換（4/11-4/14，與 Phase 0a 並行）

- [x] IPC-01：Rust PipelineSnapshot 擴展（+indicators/signals/strategies/recent_intents/recent_fills）
- [x] IPC-02：Python ipc_state_reader.py 擴展 5 新方法
- [x] IPC-03：8 條 API 路由改為 Rust-first + Python fallback（5 寫操作路由待 Rust 命令通道）
- [x] IPC-04：PipelineBridge 降級為 IPC 中繼 + Agent 回調容器（docstring + DEPRECATED 標記）
- [ ] IPC-05：分類 B Python 文件逐步降級（需 API 寫操作路由遷移後）
- [x] IPC-06：E2 + E4 — 4507 全綠

---

## ██ R-07：灰度驗證（Go/No-Go 2026-04-10）

> R07-1/2/3/5/6 代碼全部完成，R07-4 即時灰度運行中。
> 詳見 `docs/rust_migration/07--canary_greybox.md`

### Go/No-Go 清單 — **7/7 PASS (2026-04-04)**
- [x] Watchdog 3-STRIKE 驗證 — INC-001 實戰驗證 PASS
- [x] 記憶體 < 100MB — RSS 2.1MB (live, RC-09 binary) PASS
- [x] IPC 零丟失 — 409K+ ticks 連續無間隙 PASS
- [x] tick P50 < 50μs — replay P50=27μs P95=28μs P99=29μs Max=99μs PASS
- [x] 回滾演練 < 10min — 0.091s PASS
- [x] 歷史回放 0 CRITICAL — 201K ticks replay, 0 crash, 5 fills, 4.97s PASS
- [x] 穩態 0 崩潰 — 201K replay 壓測替代 7 天穩態，新 binary 運行中 0 crash PASS

---

## ██ Phase 0a — PG Schema 基礎（W1，4/11-4/17）

> **DDL 草稿已完成（V001-V005），交叉複審 43/43 MATCH。**
> 存放：`sql/migrations/`
> 決策：一步到位含 TimescaleDB hypertable，Grafana 接受完全中斷。

- [x] 0a-01~04：備份(186K) + 執行 V001-V005 DDL（修復 window 保留字）
- [x] 0a-05~09：舊表 _legacy 重命名(11/14) + Grafana VIEW 橋接(11)
- [x] 0a-10~14：43 tables across 8 schemas + 87 indexes
- [x] 0a-15~16：scorer_training_features VIEW + all indexes
- [x] 0a-17~19：E2 PASS + E4 4507 全綠 + CC/E3 PASS（8 schemas owned by trading_admin, 0 PUBLIC grants）

## ██ Phase 0b — TimescaleDB 啟用（W2-3，4/18-4/30）

- [x] 0b-01~02：Docker image 切換 postgres:16 → timescale/timescaledb:latest-pg16 (v2.26.1)，舊 image 已刪
- [x] 0b-03~05：啟用 28 hypertables（11 market + 7 trading + 3 agent + 1 learning + 4 obs + 2 risk）
      — 15 張非時序表保持 regular（model_registry, symbol_clusters 等）
      — 修復 black_swan_events PK 加入 ts 列
- [x] 0b-06~08：9 compression(7d/14d) + 15 retention(90d/180d/365d) policies + sync_commit 分層
- [x] 0b-09~11：grafana_data_writer INSERT 改為 _legacy 表名 + Grafana VIEWs 驗證通過
- [x] 0b-13~15：requirements-ml.txt 已建 + ML 降級策略已文檔化 + OU Grid σ·√(2/θ) 已修正

> **ML Model Degradation Strategy / ML 模型降級策略（0b-14 文檔）：**
> 1. No trained model exists → fall back to rule-based scoring (confidence from strategy signals)
>    無已訓練模型 → 回退到規則評分（使用策略信號的 confidence）
> 2. ONNX runtime fails → fall back to LightGBM Python inference
>    ONNX 推理失敗 → 回退到 LightGBM Python 推理
> 3. LightGBM fails → fall back to fixed confidence=0.5
>    LightGBM 失敗 → 回退到固定 confidence=0.5
> Implementation: Phase 2 task 2-11 (Scorer pipeline). / 實現：Phase 2 任務 2-11（Scorer 管線）。
- [x] 0b-16~19：E4 4507 全綠 + grafana_data_writer 30 tests PASS

## ██ Phase 1 — 市場數據止血 + FeatureCollector + PSI（W4-5，5/01-5/14）

- [ ] 1-01~02：Ring buffer + FeatureCollector 主類
- [ ] 1-03~05：klines/tickers/regime → PG 持久化
- [ ] 1-06~10：flush fallback + ob/trade_agg/funding/indicators 寫入
- [ ] 1-11~13：PSI 漂移 + feature_baselines + ADWIN
- [ ] 1-14~15：ExperimentLedger JSON→PG + Hypothesis 擴展
- [ ] 1-16~17：Paper 數據採集 + 特徵版本號
- [ ] 1-18~20：E2 + E4 + E5
- [ ] 1-FA-1：FundingArb 雙腿回滾（需 trading.orders 持久化）

## ██ Phase 2 — 交易鏈 + Scorer + ONNX（W6-9，5/15-6/11，含 buffer）

- [ ] 2-01~05：trading 表寫入（signals/intents/verdicts/orders/fills + agent.messages）
- [ ] 2-06~10：Decision Context 混合方案 + repo 封裝 + outcome 回填（5 窗口）
- [ ] 2-11~15：LightGBM Scorer + ATR_FLOOR 動態 + isotonic + TabPFN + Echo Chamber 防護
- [ ] 2-16~19：Leakage 防護 + Ensemble + SHAP + 回測 bootstrap
- [ ] 2-20~23：ONNX PoC + Rust ml_scorer.rs(ArcSwap) + 集成測試
- [ ] 2-24~25：Parquet ETL(DuckDB COPY) + 指標重算引擎
- [ ] 2-26~28：E2(兩輪) + E4 + E5
- [ ] 2-KS-1：Kelly Position Sizing in Rust（需 trading.fills + Scorer calibrated_prob）
- [ ] 2-PYO3-1：ContextDistiller PyO3 接入（Decision Context 管道打通後）

## ██ Phase 3a — update_params() 改造 = AGT-1（W9-10，6/05-6/18）

- [ ] 3a-01~02：PA 設計接口（StrategyParams trait + Rust Strategy trait）
- [ ] 3a-03~07：Rust 5 策略 update_params()（Python 策略已淘汰）
- [ ] 3a-08~10：Rust tests + 交叉一致性
- [ ] 3a-11~12：E2 + E4

## ██ Phase 3b — Optuna + Thompson Sampling + CPCV + 黑天鵝（W11-12，6/19-7/02）

- [ ] 3b-01~02：Optuna RDBStorage + TPE within-strategy 管線
- [ ] 3b-03~04：CPCV 4-fold + 分級 embargo + power guard
- [ ] 3b-05~06：Thompson Sampling NIG + Empirical Bayes 初始化
- [ ] 3b-07~08：BH-FDR + Grid 多目標 Pareto
- [ ] 3b-09~10：黑天鵝 4 信號投票（kline return 基礎）
- [ ] 3b-11~13：ETL 正式上線 + 集成測試 + PSI 基線重建
- [ ] 3b-14~17：E2 + E4 + E5 + QC 數學驗證

## ██ Phase 4 — Claude Teacher + LinUCB + News + DL-3（W13-15，7/03-7/23）

- [ ] 4-01~03：Claude-as-Teacher → ExperimentLedger + 效果追蹤
- [ ] 4-04~06：LinUCB + Model Performance 監控 + Adversarial Validation
- [ ] 4-07~10：新聞 Agent 接口（mock，數據源暫緩）
- [ ] 4-11~14：DL-3 TimesFM/Chronos（異步，A/B 驗證，AUC<0.01 則棄用）
- [ ] 4-15~20：全 3 個集成測試 + E2 + E4 + CC/E3 + AI-E Go/No-Go + E5

## ██ Phase 5 — James-Stein + DL-1 + DL-2（W16-18，7/24-8/13）

- [ ] 5-01~03：James-Stein per-parameter shrinkage + k-means 聚類
- [ ] 5-04~07：DL-1 Symbol Embedding(4D/8D/12D) + DL-2 Regime LSTM Shadow
- [ ] 5-08~09：JS+Scorer 整合 + correlation_pairs 寫入
- [ ] 5-10~13：E2 + E4 + QC + E5

## ██ Phase 6 — 驗收（W19-20，8/14-8/27）

- [ ] 6-01~03：漸進放權管線 + 畢業邏輯 + Live 審批
- [ ] 6-04~06：全管線回放 + 壓測 + sync_commit Live 驗證
- [ ] 6-07：EvolutionEngine 標記 deprecated
- [ ] 6-08：完整文檔
- [ ] 6-09~13：E2 + E4 + QA 端到端驗收 + E5 + PM 最終確認

---

## ██ Phase 4-Conditional — 條件性（有前置條件觸發）

- [ ] 4-1：PairsTrading（需 3 月協整驗證）
- [ ] 4-2：Beta Hedging（需 HedgingEngine 穩定 1 月）
- [ ] 4-3：Kalman Filter（KAMA 表現不理想時）
- [ ] 4-5：Mac Studio 遷移 + 大模型（硬件到手）
- [ ] 4-10：Jump detection — K 線 body > 3σ → 加寬止損

---

## ██ Live Gate — Paper 21 天 + Live 準備

> 前置：融合方案 Phase 6 完成 + Phase R 完成 + Alpha > 0

- [ ] LG-1：Paper Trading 穩定運行 21 天
- [ ] LG-2：H0 Gate blocking 驗證（shadow→blocking）
- [ ] LG-3：provider pricing table 正式綁定
- [ ] LG-4：M 章 Supervised Live Gate
- [ ] LG-5：N 章 Constrained Autonomous Live

---

## ██ 技術債務（Phase 1 前清理）— ✅ 全部完成

- [x] TD-01：pipeline_bridge.py 拆分（2587→55 facade + 3 mixins）— bridge_core(831) + bridge_agents(919) + bridge_stats(825)
- [x] TD-02：phase2_strategy_routes.py 拆分（1838→81 facade + 4 files）— strategy_wiring(1180) + read(396) + write(223) + ai(141)
- [x] TD-03：paper_trading_routes.py 精簡（1144→857, -25%）— paper_trading_wiring(488) 提取

---

## ██ 長期整合（非緊急）

- [ ] OC-1：OpenClaw Webhook 告警
- [ ] OC-2：Telegram 通道
- [ ] OC-3：多通道分級告警
- [ ] OC-4：MCP PostgreSQL 自然語言查詢
- [ ] OC-5：FundingArb REST 資金費率輪詢（Rust 引擎接入）
