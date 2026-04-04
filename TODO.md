# OpenClaw TODO — 工作計劃清單
# 最後更新：2026-04-04（融合方案 v0.5 + 執行計劃 V1 · R-07 灰度中 · 4429 tests 全綠）
# 注意：compact 後從此文件恢復工作狀態
# ★ 排查參考：docs/KNOWN_ISSUES.md（已識別但未驗證的風險，遇到異常時先查）

---

## ██ 每次啟動必做：灰度驗證檢查 ██

**Rust 引擎��度驗證正在後台運行（2026-04-03 22:47 啟動）。**

```bash
# 1. 引擎是否存活？
python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 60 --status

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

Go/No-Go：**2026-04-10**。如引擎掛了見 `docs/rust_migration/07--canary_greybox.md` 重啟指引。

---

## 強制工作流程

```
E1/E1a 並行（最多 5 路）→ E2 審查（強制）→ E4 回歸（強制）→ PM 確認 → commit
16 角色定義詳見 CLAUDE.md §八
```

---

## 測試基準線

```
Python: 3839 passed / Rust: 555 passed / Canary: 35 passed
Total:  4429 tests 全綠
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

SPEC 審查記錄：
  → 認知自適應：docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md
  → Rust 遷移：docs/references/2026-04-03--rust_migration_v3_final.md
  → Agent 調參：docs/references/2026-04-03--agent_param_tuning_design_draft_v0.2.md
```

---

## ██ 當前焦點：R-07 灰度 → 融合方案執行 ██

### [~] R-07：灰度驗證（Go/No-Go 2026-04-10）

> R07-1/2/3/5/6 代碼全部完成，R07-4 即時灰度運行中。
> 詳見 `docs/rust_migration/07--canary_greybox.md`

### 融合方案（DB + ML/DL + 新聞 Agent · 20 週 · 起算 4/11）

> **設計文件（v0.5）：** `docs/references/2026-04-04--unified_db_ml_news_workplan_draft_v0.1.md`
> **執行計劃（V1）：** `docs/references/2026-04-04--execution_plan_v1.md`
> **ML 架構（v0.4）：** `docs/references/2026-04-03--ml_dl_learning_architecture_v0.4.md`
> **DB 原始設計：** `docs/references/2026-04-03--data_storage_architecture_optimal_draft_v0.1.md`
> **DB 代碼審計：** `docs/architecture/DATA_STORAGE_ARCHITECTURE_V1.md`
> **審計歷程：** 兩輪審計 + DB 專題 + 四角色聯合驗證 = 67 項修正，全部已解決

---

## ██ Phase 0a — PG Schema 基礎（W1，4/11-4/17）

- [ ] 0a-01~04：備份 + 8 Schema DDL + 遷移框架 + registry 文檔
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

## ██ Phase 2 — 交易鏈 + Scorer + ONNX（W6-9，5/15-6/11，含 buffer）

- [ ] 2-01~05：trading 表寫入（signals/intents/verdicts/orders/fills + agent.messages）
- [ ] 2-06~10：Decision Context 混合方案 + repo 封裝 + outcome 回填（5 窗口）
- [ ] 2-11~15：LightGBM Scorer + ATR_FLOOR 動態 + isotonic + TabPFN + Echo Chamber 防護
- [ ] 2-16~19：Leakage 防護 + Ensemble + SHAP + 回測 bootstrap
- [ ] 2-20~23：ONNX PoC + Rust ml_scorer.rs(ArcSwap) + 集成測試
- [ ] 2-24~25：Parquet ETL(DuckDB COPY) + 指標重算引擎
- [ ] 2-26~28：E2(兩輪) + E4 + E5

## ██ Phase 3a — update_params() 改造 = AGT-1（W9-10，6/05-6/18）

- [ ] 3a-01~02：PA 設計接口（Python StrategyBase + Rust Strategy trait）
- [ ] 3a-03~07：Python 5 策略 update_params()
- [ ] 3a-08~12：Rust 5 策略 update_params()
- [ ] 3a-13~15：Python tests + Rust tests + 交叉一致性
- [ ] 3a-16~17：E2 + E4

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

## ██ 技術整合待辦

### [ ] PYO3-1：ContextDistiller (PyO3) 接入 Python
- `rust/openclaw_pyo3/src/context_distiller.rs` 已實現但從未被 Python import
- 功能：AI 上下文壓縮（~520 tokens），用於 L1/L2 AI 推理前的數據精煉
- 接入點：`strategist_agent.py` 在構建 AI prompt 時調用
- 前置：確認 PyO3 wheel 能在當前環境 import（`import openclaw_pyo3`）
- 優先級：低（非交易熱路徑，AI 推理前的優化）

## ██ 長期整合（非緊急）

- [ ] OC-1：OpenClaw Webhook 告警
- [ ] OC-2：Telegram 通道
- [ ] OC-3：多通道分級告警
- [ ] OC-4：MCP PostgreSQL 自然語言查詢
