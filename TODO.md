# OpenClaw TODO — 工作計劃清單
# 最後更新：2026-04-04（Rust 切換決策 · 策略對齊完成 · Go/No-Go 6/7 PASS）
# 注意：compact 後從此文件恢復工作狀態
# ★ 排查參考：docs/KNOWN_ISSUES.md（已識別但未驗證的風險，遇到異常時先查）
# ★ 工程日誌：docs/worklogs/2026-04-04--session_progress_1.md（QA 審計 + 決策記錄）

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

Go/No-Go：**2026-04-10**。重啟指引見 `docs/rust_migration/07--canary_greybox.md`。

---

## 強制工作流程

```
E1/E1a 並行（最多 5 路）→ E2 審查（強制）→ E4 回歸（強制）→ PM 確認 → commit
16 角色定義詳見 CLAUDE.md §八
```

---

## 測試基準線

```
Python: 3839 passed / Rust: 569 passed / Canary: 37 passed
Total:  4445 tests 全綠（+16 Rust 新測試）
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

- [ ] RC-01：MA Crossover regime filter — Hurst regime 過濾震盪市假信號
- [ ] RC-02：MA Crossover multi-TF confirm — 簡化為 4h 單輔助時框確認
- [ ] RC-03：BB Breakout volume/Donchian 直讀 IndicatorSnapshot（避免 Python metadata 斷裂）
- [ ] RC-04：所有策略 intent rejection rollback — IntentProcessor 返回 rejection → strategy.on_rejection()
- [ ] RC-05：所有策略 on_fill() sync — FillResult 回傳 → strategy.on_fill() 更新內部狀態
- [ ] RC-06：Grid Trading geometric spacing + health check
- [ ] RC-07：BB Reversion limit order（真實實現，非 Python 的 FAKE）— Paper Engine limit matching
- [ ] RC-08：StrategyParams trait 定義 — param_ranges() / from_db() / validate()，實現留空
- [ ] RC-09：E2 審查 + E4 回歸（分 2-3 批）

### 階段 2：最小切換（4/8-4/9）

- [ ] RC-10：停止 Python tick_pipeline（移除 PIPELINE_BRIDGE.activate()，~30 行）
- [ ] RC-11：刪除分類 A dead code（187 files / 24,334 行，零測試影響）
- [ ] RC-12：重跑 201K replay 驗證 Rust 引擎完整性
- [ ] RC-13：E2 + E4

### 階段 3：Go/No-Go（4/10）

- [ ] RC-14：Go/No-Go 最終檢查（7/7 條件 + replay PASS）
- [ ] RC-15：Go/No-Go 評估報告撰寫

---

## ██ R-IPC：Rust IPC 擴展 + Python API 切換（4/11-4/14，與 Phase 0a 並行）

- [ ] IPC-01：Rust IPC 新增方法（get_klines, get_indicators, get_signals, get_strategies, get_fills）
- [ ] IPC-02：Python ipc_state_reader.py 擴展對應讀取方法
- [ ] IPC-03：Python 13+ API 路由改為 Rust 數據源
- [ ] IPC-04：PipelineBridge 降級為 IPC 中繼（保留 Agent 回調）
- [ ] IPC-05：分類 B Python 文件逐步降級（27 files / 10,508 行）
- [ ] IPC-06：E2 + E4 + 回歸測試修復

---

## ██ R-07：灰度驗證（Go/No-Go 2026-04-10）

> R07-1/2/3/5/6 代碼全部完成，R07-4 即時灰度運行中。
> 詳見 `docs/rust_migration/07--canary_greybox.md`

### Go/No-Go 清單
- [x] Watchdog 3-STRIKE 驗證 — INC-001 實戰驗證 PASS
- [x] 記憶體 < 100MB — RSS 10.9MB PASS
- [x] IPC 零丟失 — 96K+ ticks 連續無間隙 PASS
- [x] tick P50 < 50μs — benchmark 30.1μs + live tick_duration_us 已就位 PASS
- [x] 回滾演練 < 10min — 0.091s PASS
- [ ] 歷史回放 0 CRITICAL — Replay 基礎設施完備，需策略補齊後重跑
- [ ] 即時 7 天穩態 0 崩潰 — 引擎持續運行中

---

## ██ Phase 0a — PG Schema 基礎（W1，4/11-4/17）

> **DDL 草稿已完成（V001-V005），交叉複審 43/43 MATCH。**
> 存放：`sql/migrations/`
> 決策：一步到位含 TimescaleDB hypertable，Grafana 接受完全中斷。

- [ ] 0a-01~04：備份 + 執行 V001-V005 DDL + registry 文檔
- [ ] 0a-05~09：舊表 _legacy + Grafana VIEW 橋接 + market/trading/agent 表
- [ ] 0a-10~14：learning/features/observability/risk/news 表
- [ ] 0a-15~16：索引 + scorer_training_features VIEW（防 leakage）
- [ ] 0a-17~19：E2 審查 + E4 回歸 + CC/E3 安全

## ██ Phase 0b — TimescaleDB 啟用（W2-3，4/18-4/30）

- [ ] 0b-01~02：Docker image 切換（postgres:16 → timescale/timescaledb:latest-pg16）
- [ ] 0b-03~05：啟用 hypertable（market/trading/learning+obs+risk）
- [ ] 0b-06~08：壓縮 + retention + sync_commit 分層
- [ ] 0b-09~11：grafana_data_writer 改寫 + Grafana datasource + 連續聚合
- [ ] 0b-13~15：requirements-ml.txt + ML 降級策略 + OU Grid sqrt(2) 修正
- [ ] 0b-16~19：E2 + E4 + E3 + E5

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

## ██ 長期整合（非緊急）

- [ ] OC-1：OpenClaw Webhook 告警
- [ ] OC-2：Telegram 通道
- [ ] OC-3：多通道分級告警
- [ ] OC-4：MCP PostgreSQL 自然語言查詢
- [ ] OC-5：FundingArb REST 資金費率輪詢（Rust 引擎接入）
