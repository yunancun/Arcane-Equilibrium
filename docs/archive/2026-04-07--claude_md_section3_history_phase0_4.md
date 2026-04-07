### ★ Phase 4 準備就緒（2026-04-06 · 歷史紀錄）
- **V009 已 apply**：`learning.linucb_state` 新建 + `decision_context_snapshots` 三個 Phase 4 連結欄位（claude_directive_id / linucb_arm_id / linucb_confidence_bound）。Phase 4 規格原列 8 表，7 表已存在於 V001-V007。
- **22 子任務已拆解**：`docs/references/2026-04-06--phase4_execution_plan_v2.md`（4-00~4-21，43 person-days，5 路並行 wall-clock 15d）。TODO.md Phase 4 段已替換高階描述為可勾選清單。
- **Q1 — AI Budget**：本地 $100/月（GUI 可調），平台硬上限 $150/月（手動 console 設）；per-agent Teacher $60 / Analyst $30 / Reserve $10；fail-closed 三段降級 $80→$95→$100；tracker 在 Rust 側（4-15）；GUI Risk-tab 新增區塊（4-16）；新表 ai_budget_config + ai_usage_log 走 V010。
- **Q2 — News**：CryptoPanic free + CoinTelegraph RSS + Google News RSS + mock；NewsAPI 排除（違反原則 #14 商用成本）；dedup SHA1[:16]+24h；severity = keyword × source（不接 LLM，留 Phase 5）；triple-route Guardian/Regime/Learning。
- **Q3 — LinUCB arms**：起步 v1_15 (5 strat × 3 regime)，GUI dropdown 預留 v2_25 / v3_375；**採用 hierarchical warm-start** 無 reset 遷移：父→子 sufficient statistics 攤分 (`A_c = λI + (γ/K)(A_p−λI)`, `b_c = (γ/K)b_p`, γ≈0.5) + shadow compare 1-2 週 + 自動 regret 回滾 + `feature_schema_hash` fail-closed。V010 加 `arm_space_version`/`parent_arm_id`/`inheritance_gamma`/`feature_schema_hash` + `linucb_state_archive` + `linucb_migrations` 表。
- **Q4 — DoD**：A Sharpe ≥ +0.15 / C Scorer Tier-1 AUC ≥ 0.55 / D operator approve 週報 / E Teacher 執行率 ≥ 80% 且 7d 效果非負。Dashboard 4-00 起骨架，每組交付自身 Card，4-20 整合週報 + approval flow。
- **最高風險子任務**：4-02 Directive Parser + GovernanceHub veto（一旦漏網 Teacher 可繞過 P0/P1 硬邊界），E3 安全審計強制介入。

```
測試：1,075 Py + 856 Rust = 1,931 tests（全綠 · 0 failures）
路由：131+（含 8 治理 + 5 Scout + 1 Kelly 端點）
治理：GovernanceHub 4 SM，fail-closed · Rust GovernanceCore 級聯 all-or-nothing
      ARCH-4：H0 Gate + Cost Gate 已 fail-closed 硬化（2026-04-05）
品類：linear + spot + inverse（option 未來）
Agent：5/6 運行（Scout/Strategist/Guardian/Analyst/Executor，Conductor 編排待完善）
      ARCH-1：ExecutorAgent intent_id 去重已就位（MessageBus 路徑待 Phase 3a 激活）
GUI：11-Tab 專業控制台 + Kelly 資本配置卡片
L1：Ollama Qwen 3.5 9B（~1.9s）/ 27B（~9.9s）
Rust 引擎：openclaw_core 24 模組 + openclaw_engine 34 模組 + openclaw_types 10 types
  RE-2：WS supervisor 包裝完成（公共+私有 WS 自動退避重啟）
PyO3 橋接：openclaw_pyo3 暴露 39 個 Python 方法（BybitClient · 增量編譯 3.7s）
告警：TelegramAlerter + WebhookAlerter + AlertRouter 多通道扇出（OC-1/OC-2）
代碼完成度：~90%（~69,000 行 Py+Rs）· 業務功能：~95%
總工時進度：~36%（已完成 ~68d / 新總計 ~189d，含融合方案 105d 新增）
已知問題：OPEN 8 / RESOLVED 7（docs/KNOWN_ISSUES.md）
關鍵路徑：Phase 1 + Phase 2 + Phase 3a 代碼完成 → Phase 3b (Optuna/Thompson) 下一步
★★★★ Rust 遷移 — Go/No-Go 7/7 PASS + 全面清理完成（2026-04-04）：
  R-CUT 全部完成（RC-01~RC-15）· R-IPC 完成（IPC-01~06）
  RC-10 PipelineBridge 停用 · RC-11 engine.tick() 停用 · RC-12 重複 WS 停用
  Rust 為唯一 tick 處理引擎 · 唯一 Bybit WS 連接 · 零重複系統
  10/13 策略讀路由 Rust-first（含 klines/indicators/signals/strategies）
  GovernanceHub 5 死方法標記 deprecated · 10 個 flaky test 修復
★★★★ PYO3-BYBIT 完成（2026-04-05）：
  PyO3 橋接 Bybit V5 API — Python 直接調用 Rust 模組（零 IPC 開銷）
  39 方法：Account 8 + Order 6 + Position 4 + MarketData 8 + Instrument 6 + Util 7
  GUI demo/* 4 端點 Rust-first（balance/positions/orders/fills · source=rust_engine）
★★★★ RC-10 + 雙引擎架構（2026-04-05 Session 8）：
  Python PaperTradingEngine 完全禁用（ENGINE=None · 防止雙引擎）
  IPC Command Channel：pause/resume/close_all/reset via unbounded_channel
  Demo=執行引擎(Primary) · Paper=測試引擎(Testing) · Shadow orders default-on
  統一雙引擎控制：Stop 同時清 Paper+Demo 倉位/掛單
  GUI 全面遷移：所有端點 Rust-first · 零 disabled-endpoint 調用
  WS 修復：移除 3 個 broken topics（liquidation/price-limit/adl-notice 毒化連接）
  GUI-HANG 修復：IPC 3s timeout + 移除 hot path API call + 4 workers
★★★★ EXT-1 Exchange-as-Truth 實現完成（2026-04-05）：
  TradingMode enum (PaperOnly/Exchange) + config.rs trading_mode 冷參數
  on_tick 雙模式分叉：paper_only=本地模擬+影子 · exchange=送交交易所等確認
  ExchangeGateResult 門禁審批（不模擬成交）+ apply_confirmed_fill 確認成交
  PendingOrder 追蹤 + order_id→order_link_id 映射 + 5s/60s 雙重超時
  ExchangeEvent channel (Fill/OrderUpdate/DCP/Disconnected) 全路徑
  E2 審計 3P0 修復：fill匹配/zero-qty/stop無限循環 + 852 Rust tests pass
★★★★ Session 6 基礎設施清理完成（2026-04-05）：
  4 項 KNOWN_ISSUES 修復：RE-1(memory) RE-2(WS supervisor) ARCH-1(dedup) ARCH-4(fail-closed)
  OC-1 WebhookAlerter + OC-2 AlertRouter 多通道告警
  Bybit API handbook §2.3 Shadow Order Sync Channel 文檔
  OPEN 11→8 · RESOLVED 3→7
★★★★ Phase 1 Day 0 + G1 + G2 完成（2026-04-05）：
  Day 0：event_consumer.rs 提取（main.rs 1123→783）+ sqlx 0.8 + database/ 模組 + Docker test PG
  G1：FeatureCollector 34-dim + market_writer(klines/tickers) + feature_writer(UPSERT) + pipeline channels
  G2：market_writer 全 10 表 + fallback.rs(JSONL) + rest_poller(funding/OI/LSR) + quality_writer
  六角色審計 2 輪通過：G1 audit 2F→0 + G2 audit 6F→0
  Rust 790 tests（+20 new）· 0 failures · 0 warnings
  G2 audit fixes：fallback wiring + REST spawn + quality monitor + types
  G3：PSI + ADWIN drift detector（448 lines）+ feature versioning
  G4 final review：E2 1 P0 fix（feature_writer $5 bind）· E4 800 Rust + 3343 Py 全綠 · E5 PASS
  3 輪審計共 9 FAIL 全修復 · ~3,500 新代碼 · 11 new files · Rust 800 tests
★★★★ Phase 2a + 2b-infra 完成（2026-04-05）：
  2a：trading_writer(4 tables) + context_writer(15 flat+JSONB) + ExperimentLedger PG(V007 DDL)
  2b-infra：ml/model_manager(ArcSwap ONNX hot-swap) + ml/scorer(3-tier degradation)
    + ml/kelly_sizer(fractional Kelly, sample-size tiers, ATR vol-adjust)
  +23 new tests · ~1,550 new lines · MlConfig added to RuntimeConfig
  2-DE：Kelly Gate 2.5 接入 intent_processor + Python ml_training/ 6 模組
  2-FG：Parquet ETL + E2/E4 final PASS
  Phase 2 代碼完成（4 Rust commits + 2 Python commits · +38 Rust tests · +5 Python tests）
★★★★ Phase 3a 完成（2026-04-05）：
  4 策略 StrategyParams impl（MaCrossover/BbReversion/BbBreakout/GridTrading）
  Strategy trait +3 JSON methods（update_params_json/get_params_json/param_ranges_json）
  TEST-1 RESOLVED（multi_interval_ws 4 test failures fixed）
  +14 new tests · AGT-1 debt cleared
★★★★ 融合方案 v0.5（DB + ML/DL + 新聞 Agent · 20 週）：
  兩輪審計 + DB 專題 + 四角色聯合驗證 = 67 項修正
  存儲精簡 97%：5.6→0.17 GB/day · PG+TimescaleDB 確認 · 砍 PgBouncer
  ML：LightGBM Scorer + Optuna TPE + Thompson Sampling + CPCV + 黑天鵝檢測
  DL：Symbol Embedding + Regime LSTM + 時序基礎模型（3 場景）
  語言：訓練 Python / 推理 Rust ONNX / 橋接 PyO3
  設計文件：docs/references/2026-04-04--unified_db_ml_news_workplan_draft_v0.1.md
  執行計劃：docs/references/2026-04-04--execution_plan_v1.md
  ML 架構：docs/references/2026-04-03--ml_dl_learning_architecture_v0.4.md
  改善報告原文：docs/references/2026-04-03--openclaw_improvement_report_v3_final.md
★★★★ Phase 3b 核心完成（2026-04-05）：
  Pre-fixes：IPC strategy params 3 方法 + scorer_trainer n_folds=4 + embargo 24/4/8/72h
  G1：Optuna TPE (SQLite JournalStorage) + CPCV 4-fold + Thompson Sampling NIG
  G2：Black Swan 4 信號投票 (Rust) + ETL DuckDB labels + PSI baseline rebuild
  G3：Integration test (Optuna→TS→CPCV pipeline) 3/3 pass
  BH-FDR + Grid Pareto 延後至 Phase 4（無數據）
  MIT+QA+E5 審計：5 FAIL + 9 WARN 全解決
  新代碼：~570 Rust + ~2200 Python · 新測試 49（11 Rust + 35 Python + 3 integration）
  816 Rust + 40 ml_training tests pass
★★★★ Session 9 運營修復 + 風控 GUI 完善（2026-04-05）：
  3 生產 Bug 修復：signals flush overflow(batch chunking) + BTC/ETH qty=0(min_qty fallback) + timestamps=0(now_ms)
  風控 GUI 審計：1 bug(trailing stop 未保存) + 7 缺失控件全部補齊
  新增 3 個 GUI 區塊：仓位控制(P1 Risk/Single Pos/Total Exp/Same-Dir) + 亏损冷却 + H0 Gate
  API: GlobalConfigUpdate +5 fields · IPC client +h0_shadow_mode · 全鏈路驗證通過
  QA 對沖分析：暫不啟用（Bybit net-position 模式，Phase 4 考慮策略隔離）
  E5+E2+PA+FA 四角色審計通過（0P0 · 1P1 修復 · 2P2 修復）
★★★★ RRC-1 風控運行時接線完成（2026-04-05）：
  Phase A：H0Gate 5-check 接入 tick_pipeline Step 0.5（shadow mode 默認）
  Phase B：Gate 2.7 check_order_allowed 5 check 接入 IntentProcessor（P1 sizing 後）
  Phase C：check_position_on_tick 9 check 替換 check_stops + PriceHistoryTracker ATR
  Phase D：PipelineSnapshot +8 風控欄位 · Python risk_routes 全從 Rust 快照讀
  Phase E：Strategy set_active IPC · session unhalt IPC · exchange double-close fix
  3 輪審計：4 P0/P1 修復（NaN fail-open / state leak / exchange double-close）
  856 Rust tests + 4 新 rrc1_audit_tests · 0 failures
★★★★ L3 全系統審計 12 路並行（2026-04-05）：
  FA/AI-E/E5/E4/E3/CC/QC/MIT/BB/TW/R4/A3 + PA 統一整改
  63 獨立問題（7P0/21P1/25P2/10P3）→ 11 工作包 → 4 波執行
  關鍵：Exchange 缺 Cost Gate · DDL 未執行 · 47 硬編碼值 · AI 42/100 · DB/ML 52/100
★★★★ Session 13 R3 backlog 收尾（2026-04-06）：
  I-22: event_consumer/mod.rs 802 → 628（dispatch.rs + setup.rs 提取）
  FA-GAP-2: cost_ratio 接線（pnl% × 200 × fee_rate，殺 placeholder=0）
  FA-GAP-4: Kelly ATR% 接線（intent_processor 用 atr/price 取代寫死 0.02）
  Fees: per-symbol 真實費率（AccountManager Arc 保活 + 6h 刷新 + 12h staleness 監控）
        + cancel-aware refresh task + trading.fills.fee_rate 列（V008）
  SEC-11: cost gate ATR=0 改 fail-closed（cold start 由 PNL-3 cooldown 接住）
  FA-GAP-8: IPC evaluate_strategy / get_risk_check stub + Python wrapper 全刪（dead code）
  FA-GAP-9: bb_reversion use_limit 從 param_ranges 移除 + update_params 強制 false
            （paper 無 order book sim，避免 silent PnL 失真）
  Idle writer #3: liquidations dead infra 全刪（writer + Msg variant + 3 個 topic 函數
            + extended_subscription_list），市表保留 reserved-for-future
  Memory cleanup: 4 條過時記憶刪除 + 新增 feedback_pushback（主動指出 operator 錯誤）
  7 commits（e69191d..0d52577）· engine 474 → 471（-3 = stub/test 清理）· core 413
  R3 backlog 排除 WP/SEC defer/Phase4 後**全部清空**

★★★★ Session 12 PNL-1~7 + magic-number cleanup + DB-RUN-1~7（2026-04-06）：
  PNL-1 qty=0 幽靈倉拒絕 · PNL-2 H0Gate boot log + invariant
  PNL-3 啟動冷卻 60s（env + IPC 可調）· PNL-4 regime 動態化（Hurst→ADX）
  PNL-5 Cost Gate k 分檔（3.0/2.0/1.5）· PNL-6 trailing 鎖定盈利下限 RR ≥ 1:2
  PNL-7 dynamic_stop base/cap 提取到 RiskManagerConfig + IPC
  Session 12 cleanup：cost_gate min_conf / k 三檔 / ADX trending 閾值 / boot cooldown 全進 IPC
  DB-RUN-1 signals 節流（state-change + 60s heartbeat，預期 -95%）
  DB-RUN-2 decision_context piggyback DB-RUN-1（預期 -99.6%）
  DB-RUN-3 5 個 close 站點全部 emit_close_fill（風控/止損平倉的 realized_pnl 不再為 0）
  DB-RUN-4 feature history by design 文檔化（訓練走 decision_context.indicators_snapshot）
  DB-RUN-5 BlackSwanDetector 接入 TickPipeline（in-memory + log，DB write 待 schema）
  DB-RUN-6 context_writer epoch 0 guard + 已清理 5 條歷史
  DB-RUN-7 signals chunk 7d→1d / compress 14d→2d + ANALYZE（live + V006）
  ⚠️ 強制原則：後續所有風控/止損參數必須對齊 RiskManagerConfig + IPC update_risk_config，
     禁止 hot path 寫死，禁止繞過 patch_* 驗證
  15 commits（ed01bf5..6608ab7）· engine 453 → 474（+21）· core 411 → 413（+2）

★★★★ Session 11 R1 收尾 + R2 批次完成（2026-04-06）：
  R1 P1-6: drift_detector PG 接線（fetch_active_baselines + DriftMonitorState）
  R2-2: idle writers #1/#2 producer aggregators（trade_agg_1m + ob_snapshots，+9 tests）
  R2-3: I-22 完整拆分 event_consumer mod.rs 912 → 785（handlers.rs 提取）
  R2-4: WP-E4 P1 5/6 tests（strategies/mod + handlers + fallback + Py 三模組 smoke）
  測試：engine 428 → 453（+25）· control_api +11 Py smoke
  Liquidations idle writer #3 留待手動 Bybit V5 topic 驗證
  Commits：`8d5793b` `2cf7ebf` `0519265` `957d174`

★★★★ Session 10 R0 + R1 整改完成（2026-04-06）：
  414 findings → 63 tracker → 223 WP 子項補齊（`docs/audits/2026-04-06_consolidated_remediation_report.md`）
  R0：Gate3 全覆蓋 + IPC 0o600 + clamp + dual-rail SL (Principle #9) + V007 DDL + I-06 split + I-22 partial split
  R1：SEC-02/06/13/18 修復 + position_snapshots emitter + WP-MIT P1-3/4/5（CPCV integration / TS PG persist / pipeline orchestrator）
  6 idle writers 根因調查：§11 完整報告（consumer 側連線完好，producer 側從未寫入）
  測試：428 engine + 35 ml_training + 411 core · +21 new · 0 failures
★★★★ Session 9c realized_pnl Bug + Gate 3 Cost Gate（2026-04-05）：
  Bug 修復：apply_fill() 返回 realized_pnl → DB fills 正確記錄已實現損益（之前永遠 0）
  Gate 3 Cost Gate 實現：QC 公式 ATR×confidence×qty < 1.5×2×fee_rate×notional → 拒絕
  min_confidence 硬地板 0.15 · paper k=1.5 / live k=2.0 · ATR 不可用時 fail-open
  +3 新測試（低信心拒絕 / 低 EV 拒絕 / 高 EV 通過）· 379 Rust tests pass
  生產驗證：低波動市場中無效交易被正確攔截，零手續費損耗

Runtime 硬狀態（不可改）：
  system_mode          = demo_only
  execution_state      = disabled
  execution_authority  = not_granted
  live_execution_allowed = false
```

