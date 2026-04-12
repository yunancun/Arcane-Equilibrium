# Completed TODO Archive — L3 整改 + Phase 0/1/2/3 + Rust 遷移

歸檔日期：2026-04-06（Session 11 後）
歸檔原因：TODO.md 清理，將已驗證完成的工作項從活動清單移出

涵蓋範圍：
- L3 12 路審計整改 R0/R1/R2 批次
- Phase 0a / 0b / 1 / 2 / 3a / 3b
- R-CUT / R-IPC / R-07 / EXT-1 / RRC-1 / PYO3-BYBIT
- 技術債務 TD-01~03

---

## L3 審計整改（Session 10 + 11）

### R0 Week 1 — 已完成（Session 10 · 2026-04-06）

- [x] **R0-1 / I-01** Gate 3 補到 `process_gates_only()`（commit `8e7685a`）
- [x] **R0-2 / I-02 + I-09** IPC 0o600 + clamp() setters（commit `8e7685a`）
- [x] **R0-3 / I-06** `market_data_client.rs` 拆分 1428→1081/216/157（commit `8e7685a`）
- [x] **R0-4 / I-07** V007 DDL 套用 prod · 6 writers idle 根因見 §11（commit `8e7685a` + `0d72309`）
- [x] **R0-5 / NEW-1** `stress_integration.rs` atr 參數編譯失敗修復（commit `8e7685a`）
- [x] **R0-X / I-08** 雙軌止損 Principle #9 wiring（commit `8e7685a`）
- [x] **R0-X / I-22** event_consumer 拆分 PARTIAL（commit `c9994c5`）

### R1 Wave 1 — 已完成（Session 10 · 2026-04-06）

- [x] **SEC-02** H0Gate shadow mode audit log（commit `5fcad61`）
- [x] **SEC-06** Login token 從 JSON body 移除（commit `5fcad61`）
- [x] **SEC-13** `latency_us` u32 saturating cast（commit `5fcad61`）
- [x] **SEC-18** paper_state 5 setters clamp + NaN reject（commit `5fcad61`）
- [x] **Idle writer #4** position_snapshots emitter +2 tests（commit `5fcad61`）
- [x] **WP-MIT P1-3** run_training_pipeline.py +3 tests（commit `de6dd82`）
- [x] **WP-MIT P1-4** scorer_trainer CPCV integration（commit `de6dd82`）
- [x] **WP-MIT P1-5** Thompson Sampling PG persistence +3 tests（commit `de6dd82`）
- [x] **WP-MIT P1-6** drift_detector PG wiring +3 tests（commit `8d5793b`）

### R2 批次 — 已完成（Session 11 · 2026-04-06）

- [x] **PF-1** IPC strategy params（已存在於 Phase 3b pre-fixes，5 IPC tests）
- [x] **Idle writers #1/#2** ob_snapshots + trade_agg_1m producer aggregators +9 tests（commit `2cf7ebf`）
- [x] **I-22 完整拆分** event_consumer mod.rs 912 → 785（commit `0519265`）
- [x] **WP-E4 P1 tests** strategies/handlers/fallback +13 Rust + 11 Py smoke（commit `957d174`）

### SEC 降級 DONE（pre-Session-9c 已完成，報告未更新）

- [x] **SEC-01/04/08** 已降級

### 已驗證 DONE（從 PA 63 中歸檔）

- [x] Session 9c `realized_pnl` 接線（`tick_pipeline.rs:737-763` + `trading_writer.rs:151-163`）
- [x] Gate 3 Cost Gate 在 `process()` 路徑完整（intent_processor.rs L317-355）
- [x] H0Gate fail-closed 硬化 + RRC-1 風控接線
- [x] PyO3 39 方法 + Bybit V5 全量端點（BB 審計確認 47/47 正確）
- [x] 風控 GUI Session 9 補齊 + IPC h0_shadow_mode 全鏈路

---

## Phase 0a — PG Schema 基礎（W1）

- [x] 0a-01~04：備份(186K) + V001-V005 DDL（修復 window 保留字）
- [x] 0a-05~09：舊表 _legacy 重命名(11/14) + Grafana VIEW 橋接(11)
- [x] 0a-10~14：43 tables across 8 schemas + 87 indexes
- [x] 0a-15~16：scorer_training_features VIEW + all indexes
- [x] 0a-17~19：E2 PASS + E4 4507 全綠 + CC/E3 PASS

## Phase 0b — TimescaleDB 啟用（W2-3）

- [x] 0b-01~02：Docker image 切換到 timescale/timescaledb:latest-pg16 (v2.26.1)
- [x] 0b-03~05：啟用 28 hypertables（+ black_swan_events PK 加 ts）
- [x] 0b-06~08：9 compression + 15 retention policies + sync_commit 分層
- [x] 0b-09~11：grafana_data_writer + Grafana VIEWs 驗證
- [x] 0b-13~15：requirements-ml.txt + ML 降級策略文檔 + OU Grid σ·√(2/θ) 修正
- [x] 0b-16~19：E4 4507 全綠 + grafana_data_writer 30 tests PASS

## Phase 1 — 市場數據止血 + FeatureCollector + PSI（W4-5）

- [x] Day 0：event_consumer.rs 提取 + database/ + sqlx 0.8 + Docker test PG（commit `8e0cccd`）
- [x] G1：FeatureCollector 34-dim + market_writer + feature_writer + pipeline channels（commits `ddbc7af` + `7aaec66`）
- [x] G2：market_writer 全 10 表 + fallback.rs + rest_poller + quality_writer（commits `bf0725a` + `adbe0a7`）
- [x] G3：PSI drift + ADWIN + feature_baselines + versioning + paper hooks（commit `86ae00e`）
- [x] G4：E2(1 P0 fix) + E4(4143 全綠) + E5 PASS（commit `13ae4ee`）
- 1-14~15：ExperimentLedger JSON→PG 延後 Phase 2（已完成）
- 1-FA-1：FundingArb 雙腿回滾 延後 Phase 2

## Phase 2 — 交易鏈 + Scorer + ONNX（W6-9）

- [x] 2a-01~04：trading_writer (signals/intents/fills/positions)（commit `41e144d`）
- [x] 2a-05~07：context_writer (15 flat + 3 JSONB)（commit `41e144d`）
- [x] 2a-08~09：ExperimentLedger PG — V007 DDL + Rust CRUD（commit `41e144d`）
- [x] 2b-infra：ml/model_manager(ArcSwap ONNX) + scorer(3-tier) + kelly_sizer（commit `e06c77c`）
- [x] 2-DE：Kelly Gate 2.5 + Python ml_training/ 6 模組（commit `7d68cfe`）
- [x] 2-FG：Parquet ETL(DuckDB) + E2/E4 final review PASS（commit `fb45c95`）
- [x] 2-KS-1：Kelly Position Sizing in Rust（commits `e06c77c` + `7d68cfe`）

殘留延後（非阻塞）：
- 2-11 actual training（需引擎運行收集 fills 後）
- 2-PYO3-1 ContextDistiller PyO3 接入
- ort crate activation（首個 ONNX 模型訓練後）

## Phase 3a — update_params() = AGT-1（W9-10）

- [x] 3a-01~07：Strategy trait +3 JSON methods + 4 策略 StrategyParams impl（commit `a212a82`）
- [x] 3a-08~12：14 new tests + E2 + E4 全綠

## Phase 3b — Optuna + Thompson Sampling + CPCV + 黑天鵝（W11-12）

- [x] PF-1：IPC update_strategy_params/get/ranges（commit `b8b4f3c`）
- [x] PF-2：scorer_trainer.py 對齊 n_folds=4, embargo 24/4/8/72h（commit `b8b4f3c`）
- [x] PF-3：V004 DDL 確認 + trading.fills=5 評估（commit `b8b4f3c`）
- [x] 3b-01~02：Optuna TPE SQLite + EV_net + IPC integration（commit `782dd03`）
- [x] 3b-03+04：CPCV 4-fold + 策略特定 embargo + power guard（commit `782dd03`）
- [x] 3b-05+06：Thompson Sampling NIG + Empirical Bayes（commit `782dd03`）
- [x] 3b-09~10：黑天鵝 4 信號投票 Rust（commit `380b38a`）
- [x] 3b-11：ETL DuckDB label generation（commit `380b38a`）
- [x] 3b-12：集成測試 test_optuna_to_ts_pipeline 3/3 pass（commit `9b0287f`）
- [x] 3b-13：PSI 基線重建 + 7 天冷卻 + block bootstrap（commit `380b38a`）
- 3b-07/08 BH-FDR + Grid Pareto 延後 Phase 4

---

## R-CUT — Rust 策略補齊 + 切換

- [x] RC-01~09：MA Crossover regime/multi-TF + BB Breakout/Reversion + Grid + on_rejection/on_fill + StrategyParams trait
- [x] RC-10~13：Python tick_pipeline 停用 + dead code 1003 行刪除 + 4507 tests 全綠
- [x] RC-14~15：Go/No-Go 7/7 PASS + 評估報告
- [x] Post-Go：engine.tick() 停用 + Python MarketDataDispatcher 停用 + 10 flaky test 修復 + GovernanceHub 死方法標記 + Klines/Indicators Rust-first

## R-IPC — Rust IPC 擴展

- [x] IPC-01~04：PipelineSnapshot 擴展 + Python ipc_state_reader + 8 路由 Rust-first + PipelineBridge 降級
- [x] IPC-06：E2 + E4 4507 全綠
- IPC-05 分類 B Python 文件降級延後（需 PYO3-BYBIT 寫操作後）

## R-07 — 灰度驗證

- [x] Go/No-Go 7/7 PASS（2026-04-04）
  - Watchdog 3-STRIKE / RSS 2.1MB / IPC 0 丟失 / tick P50=27μs / 回滾 0.091s / 201K replay 0 crash / 穩態 0 crash

## EXT-1 — 交易所即真相

- [x] EXT-1-01~10：TradingMode enum + on_tick 雙模式分叉 + ShadowOrderRequest is_primary + PendingOrder + ExchangeEvent channel + Fill confirmation + 5s/60s timeout + DCP/Disconnect + GUI trading_mode

## RRC-1 — 風控運行時接線

- [x] Phase A：H0Gate 接入 tick_pipeline Step 0.5（shadow mode）
- [x] Phase B：Gate 2.7 check_order_allowed 接入 IntentProcessor
- [x] Phase C：check_position_on_tick 9 check 替換 check_stops + PriceHistoryTracker
- [x] Phase D：PipelineSnapshot +8 風控欄位 + risk_routes Rust-first
- [x] Phase E：Strategy set_active IPC + session unhalt + exchange double-close fix
- [x] 3 輪審計：4 P0/P1 修復（NaN/state leak/double-close）

## PYO3-BYBIT — PyO3 Bybit API 橋接

- [x] PYO3-B01：Crate 準備（commit `e3c9afe`）
- [x] PYO3-B02：BybitClient + AccountManager（commit `e3c9afe`）
- [x] PYO3-B03：OrderManager + PositionManager（commit `e3c9afe`）
- [x] PYO3-B04：MarketDataClient + InstrumentInfoCache（commit `68c4713`）
- [x] PYO3-B05：Python 端接入（strategy_ai_routes.py demo/* 4 端點）
- [x] PYO3-B06：maturin 構建驗證（39 methods, 3.7s 增量）
- [x] PYO3-B07：E2 + E4 0 FAIL · 4609 tests（commit `76cb0cb`）
- [x] PYO3-B08：E5 0 OPTIMIZE · 2 DEFER

---

## 技術債務 — 全部完成

- [x] TD-01：pipeline_bridge.py 拆分（2587→55 facade + 3 mixins）
- [x] TD-02：phase2_strategy_routes.py 拆分（1838→81 facade + 4 files）
- [x] TD-03：paper_trading_routes.py 精簡（1144→857）

---

## Operator 決策

- 2026-04-04：放棄修復 Python V2 交易引擎，全力 Rust。Python 保留 API/GUI/Agent 層
- QA 審計：Python V2 真實成熟度 62/100，6 項 FAKE/DEAD/UNREACHABLE
- 詳見 `docs/worklogs/2026-04-04--session_progress_1.md`

---

## Session 11 最終測試基準線（2026-04-06）

```
openclaw_engine: 453（+25 from 428 baseline）
openclaw_core:   411
ml_training:     35
control_api smoke: 11（new in Session 11）
0 failures
```

歷史基準線（壓縮日期）：
- 2026-04-04 RC-15：4507（Python 1075 + Rust 856 + integration 2576）
- 2026-04-05 PYO3-BYBIT：4609（+102 PyO3 + retest）
- 2026-04-06 Session 10：4628（+19 R0/R1 batch）
