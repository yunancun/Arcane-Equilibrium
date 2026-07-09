# MIT Audit Report: ML/DB Foundation & Deployment Stage
**Date:** 2026-04-24
**Auditor:** MIT (ML & Integration Team)
**Scope:** `sql/migrations/V001-V023` + `V999` · `learning.*` consumer/writer pairing · `run_training_pipeline.py` → shadow/canary pipeline · Phase 1a/2 readiness
**Method:** 純 Mac static read（migration SQL + `grep INSERT/SELECT/UPDATE` on .rs/.py + 關鍵 module NOTES）— 無 Linux PG 活訪；row count 估計標「TODO Linux」

---

## 0. Executive summary

### 整體 ML 部署階段評級：**Foundation (偏 Skeleton)**

- **Foundation 完成度 85%**：21 張 learning schema + 5 張 observability + 3 risk 表 migration 全到位；3 postmortem 修復（V023/V021 Guard retrofit + outcome_backfiller timeframe/engine_mode 雙 bug）已 land
- **Skeleton 正在長出**：Combine Layer shadow writer spawn 了但 shadow_enabled=false dormant；Model Registry V023 hypertable + API routes + Rust resolver 到位但 0 row；edge_estimator daemon 隨 uvicorn 每小時刷 JSON 是目前唯一 ML→engine 真活管線（file-only，非 IPC hot-reload）
- **Shadow 尚未點亮**：decision_shadow_exits 0 row（flag off）; model_registry 0 row（無 training 跑過）；ExecutorAgent `_shadow_mode=True` 本來就是 shadow 態
- **Canary / Production**：0。所有 ML 組件都不 inform 真實倉位決策
- **真能 inform 決策的 ML**：僅 `edge_estimates.json` → Rust startup 一次 load → cost_gate 門檻；這是 JS estimator → 非 ML；且 P1-14 bind 未完成（grand_mean > -50 + ≥2 策略 shrunk>0 條件未滿足）

### 最大三個 blocker
1. **訓練資料不足**：P1-7 C pooled 最大切片 `demo grid_trading BLURUSDT` 47/200 labels（ETA ~3-5d）。全策略 gross edge 負，P1-10 EDGE-P2-3 PostOnly 降 fee 在觀察，P0-3 Phase 5 重評等穩定期
2. **Combine Layer shadow 未啟**：`RiskConfig.exit.shadow_enabled=false` 預設，writer/channel/mock builder 全就位但 0 fire；需 operator TOML 或 IPC flip 才開始收樣本
3. **Model Registry 空**：V023 hypertable + V021 Guard A retrofit 都好了，但無第一行 `run_training_pipeline.py` 寫入 → 5 `/api/v1/ml/*` routes 回 404，Rust `OnnxModelManager` 走 `_current` symlink fallback（symlink 也不存在）

---

## 1. SQL Migration 全表清單

### 1.1 Migration 執行順序（V001-V023）

| V | 主題 | 主要新表 | Learning 數 | Postmortem 修復 |
|---|------|---------|------------:|-----------------|
| V001 | 8 schemas | (no tables) | 0 | — |
| V002 | market tables | klines / news_signals | 0 | — |
| V003 | trading+agent | decision_context_snapshots / fills / orders / intents / ... | 0 | — |
| V004 | learning+features+obs+risk | **rl_transitions, promotion_pipeline, ml_parameter_suggestions, model_registry(legacy), bayesian_posteriors, cpcv_results, james_stein_estimates, symbol_clusters, teacher_directives, directive_executions** + features.online_latest/versions + obs 5 + risk 3 | 10 | V023 legacy stub 來源 |
| V005 | indexes+views | (index + view only) | 0 | — |
| V006 | timescale policies | (retention/compression) | 0 | — |
| V007 | experiment_ledger | **learning.experiment_ledger** | 1 | — |
| V008 | fills.fee_rate | ALTER | 0 | — |
| V009 | Phase 4 ML/News | **learning.linucb_state** + dcs 3 cols | 1 | — |
| V010 | AI budget+LinUCB ver | **ai_budget_config, ai_usage_log, linucb_state_archive, linucb_migrations** + linucb_state 4 cols | 4 | — |
| V011 | DL-3 foundation | **learning.foundation_model_features** | 1 | — |
| V012 | directive outcomes | directive_executions +7 cols | 0 | — |
| V013 | weekly review | **learning.weekly_review_log** | 1 | — |
| V014 | engine events | observability.engine_events | 0 | — |
| V015 | engine_mode separation | ALTER 7 tables +engine_mode | 0 | — |
| V016 | pattern insights | **learning.pattern_insights** | 1 | — |
| V017 | edge predictor | **decision_features, decision_shadow_fills** + dcs 7 cols + fills.entry_context_id | 2 | — |
| V018 | paper state checkpoint | paper_state_checkpoint (不在 learning.) | 0 | — |
| V019 | strategist params | **learning.strategist_applied_params** | 1 | — |
| V020 | strategist tie-break | index | 0 | FA H1 post-commit audit |
| V021 | fills.exit_source + shadow exits | fills.exit_source + **learning.decision_shadow_exits** | 1 | Guard A+B retrofit 2026-04-24 |
| V023 | model_registry rebuild | **learning.model_registry** (canary + verdict 新 schema，legacy 已手動掃) | 1 | Guard A retrofit 2026-04-24 |
| V999 | exit_features | **learning.exit_features** | 1 | filename placeholder（未重編號）|

**V022 留空、V017_rollback 為 rollback helper，不計入順序**

### 1.2 Guard A/B/C 落實

| Migration | Guard A | Guard B | Guard C | Idempotent 驗證 | 備註 |
|-----------|---------|---------|---------|-----------------|------|
| V021 | ✅ decision_shadow_exits | ✅ fills.exit_source type + shadow.ts timestamptz | — | 隱含 IF NOT EXISTS | 2026-04-24 retrofit |
| V023 | ✅ model_registry | — (純新建) | — | IF NOT EXISTS + ON CONFLICT DO UPDATE | 2026-04-24 retrofit |
| V004 | ❌ 無 guard（來源） | ❌ | — | IF NOT EXISTS | model_registry legacy stub 來源 |
| 其他 V | ❌ 多為 pre-guard-era | ❌ | — | IF NOT EXISTS | CLAUDE.md §七 新規後才開始落實 |

**Gap**：V004 建的 10 張 learning 表無 guard；若 legacy 漂移會 silent-skip。**TODO Linux 操作者**：跑 `helper_scripts/db/audit_migrations.py` + 列所有 learning 表 column 清單對帳。

### 1.3 Hypertable / Partition / Index

| 表 | Hypertable | Chunk | 關鍵 Index |
|----|-----------:|-------|-----------|
| learning.decision_features | ❌（plain PK context_id） | — | idx_strategy_mode_ts, idx_ts, idx_labeled(partial) |
| learning.exit_features | ✅ | 7d | idx_strategy_mode_ts, idx_ts, idx_symbol_ts |
| learning.decision_shadow_fills | ❌（SERIAL PK） | — | idx_strategy_ts |
| learning.decision_shadow_exits | ✅ | 1d | idx_strategy_ts, idx_disagreed(partial), idx_context_id |
| learning.rl_transitions | ✅ | 7d | (PK only) |
| learning.ai_usage_log | ✅ | 7d | idx_scope_time |
| learning.foundation_model_features | ✅ | 7d | idx_symbol_time, idx_model_time |
| learning.model_registry | ❌（BIGSERIAL PK） | — | uq_identity, idx_production_latest(partial), idx_canary_status_created, idx_train_date |
| learning.linucb_state | ❌ | — | idx_updated (composite PK arm_id + arm_space_version) |
| observability.scorer_predictions | ✅ | 1d | (PK only) |
| observability.model_performance | ✅ | 7d | (PK only) |
| observability.drift_events | ✅ | 1d | (PK only) |
| observability.data_quality_events | ✅ | 1d | (PK only) |
| risk.black_swan_votes | ✅ | 7d | (PK only) |
| risk.correlation_pairs | ✅ | 7d | (PK only) |
| trading.decision_context_snapshots | ✅ | 1d | idx_engine_mode_ts, idx_claude_directive, idx_linucb_arm, idx_dcs_predicted_q50(partial) |
| trading.fills | ✅ (pre-exists) | — | idx_engine_mode_ts, idx_fills_exit_source_non_physical(partial), idx_fills_entry_ctx(partial) |

---

## 2. Learning Schema 表 × (Writer / Consumer / Row 估計 / 狀態 / Blocker)

> Row 估計以 CLAUDE.md/TODO.md/memory 敘述的截至日估計；**狀態分類**：live（有 row + 有讀者）/ writer_only / reader_only / dormant / stub

| 表 | Writer 位置 | Consumer 位置 | Row 估計（近 24h 或已累積）| 狀態 | Blocker |
|---|---|---|---|---|---|
| **decision_features** | Rust `decision_feature_writer.rs:116` INSERT | Python `edge_label_backfill.py:116/219/318/372`, `run_training_pipeline.py:214`, `parquet_etl.py:387`, `phase1a_c_readiness.py:43-77`, `passive_wait_healthcheck.py:92` | 1.65M cumulative (CLAUDE §P1-7) | **live** | — |
| **exit_features** | Rust `exit_feature_writer.rs:120` INSERT | Python `counterfactual_exit_replay.py:678/708`, `passive_wait_healthcheck.py:110` | 1:1 with close_fills | **live** | — |
| **decision_shadow_fills** | Rust `shadow_fill_writer.rs:145` INSERT | Python `shadow_fills_routes.py:165/212/266` (GUI API) | PAPER-DISABLE-1 預設 dormant；paper 啟才寫 | **dormant** | `OPENCLAW_ENABLE_PAPER=1` 才 spawn |
| **decision_shadow_exits** | Rust `shadow_exit_writer.rs:201` INSERT（spawn at tasks.rs:478-485） | Python `passive_wait_healthcheck.py:592/610`（check [8]） | **0**（shadow_enabled=false） | **Skeleton** | `RiskConfig.exit.shadow_enabled=true` TOML/IPC flip |
| **model_registry** (V023 new) | Python `model_registry.py:210` INSERT（from `run_training_pipeline.py` stage 5.5 hook）+ 3 integration tests | Rust `ml/registry.rs:226` SELECT（`resolve_latest_production_artifact` — 無 live caller，Phase 3+ 才 wire OnnxModelManager）· Python `ml_routes.py:225/285`（GUI API）· `passive_wait_healthcheck.py:271-288`（check [9]） | **0**（無 training 跑過） | **Skeleton** | P1-7 C labels 滿 200，`run_training_pipeline.py` 首跑 |
| **teacher_directives** | Rust `claude_teacher/writer.rs:87` INSERT | Rust `claude_teacher/outcome_tracker.rs:123` SELECT（JOIN directive_executions）| 須 Claude Teacher 調用才生成（低頻 ~0.14/day）| **dormant** | Phase 4 Teacher 路徑未啟動；G-7 W23 排期 |
| **directive_executions** | Rust `claude_teacher/writer.rs:222` INSERT | Rust `outcome_tracker.rs` SELECT + Python `weekly_report_generator.py:204`, `phase4_routes.py:343/358` | 同 directive 低頻 | **dormant** | 同上 |
| **experiment_ledger** | Rust `experiment_ledger_pg.rs:71` INSERT | Rust `experiment_ledger_pg.rs:164/175` SELECT | 結構異常（CLAUDE §P1-7 敘述 `experiment_ledger_snapshot.json` 異常）| **skeleton + bug** | `experiment_ledger_snapshot.json` 結構 bug 待修 |
| **linucb_state** | Python `linucb_trainer.py:260`, `linucb_arm_migration.py:283` INSERT | Rust `linucb/state_io.rs:94`, Python `phase4_routes.py:209`, `linucb_shadow_compare.py:270` SELECT | 訓練/migration 跑過才寫；QC-3 audit 判 shadow_compare deferred | **skeleton** | 等 Rust warm-start 實裝或 Phase 4 task 4-06 降級 |
| **linucb_state_archive** | Python `linucb_arm_migration.py:231`, `linucb_shadow_compare.py:263`, `fresh_start_reset.py:361` INSERT | Python `linucb_shadow_compare.py` 本檔 / `fresh_start_reset.py:370` SELECT | 只在 migrate/archive 時寫 | **tool** | 無；工具表，僅 migrate 時寫 |
| **linucb_migrations** | Python `linucb_arm_migration.py:329`, `linucb_shadow_compare.py:275` INSERT | Rust `linucb/state_io.rs:195`, Python `weekly_report_generator.py:228`, `phase4_routes.py:200/218` SELECT | 0（無 warm-start migration 跑過） | **stub-ready** | 同 linucb_state |
| **ai_usage_log** | Rust `ai_budget/usage_io.rs:61` INSERT | Rust `ai_budget/usage_io.rs:106`, Python `weekly_report_generator.py:300/317` SELECT | AI 調用才寫（local Ollama + Claude Teacher 走過才有） | **partial live** | 依 AI 調用頻率；未 block |
| **ai_budget_config** | Rust `ai_budget/config_io.rs:54` INSERT/ON CONFLICT, V010 seed | Rust `ai_budget/config_io.rs:22`, Python `weekly_report_generator.py:310` SELECT | V010 seed 5 scopes | **live** | — |
| **bayesian_posteriors** | Python `thompson_sampling.py:420` INSERT | Python `thompson_sampling.py:465` SELECT 本檔 | 0（Thompson sampling 未 integrated 到 runtime）| **code-complete, dormant** | Teacher/LinUCB 接通後才啟動 |
| **cpcv_results** | Python `cpcv_validator.py:341` INSERT | Python `tests/test_integration.py` 本檔 only | 0（`run_training_pipeline.py` CPCV stage 存在但 `skip_onnx=True` 預設，且 training 尚未跑）| **dormant** | P1-7 C labels |
| **james_stein_estimates** | Python `james_stein_estimator.py:361` INSERT | Python `edge_cluster_analysis.py:123` SELECT | Edge estimator daemon 改寫 JSON 檔而不寫 PG（`edge_estimator_scheduler.py` 實際不 INSERT 此表 — P1-7 B 分離設計） | **orphan — 代碼存在，daemon 走 JSON path 繞過** | 若要 PG 持久化需接 daemon INSERT 或 CI job |
| **symbol_clusters** | ❌ 無 writer | ❌ 無 consumer | 0 | **dead code** | 完全未接線，V004 設計殘留 |
| **rl_transitions** | ❌ 無 writer | ❌ 無 consumer | 0 | **dead code** | RL 方向未啟；V004 設計殘留 |
| **promotion_pipeline** | ❌ 無 INSERT/UPDATE（`promotion_pipeline.py` 是 Python 類，未 touch DB 表；V004 敘述有誤指向此表）| ❌ 無 SELECT | 0 | **dead code（DB 層）**；Python 類邏輯存在於 app/promotion_pipeline.py 使用 in-process state | Python 類與 DB 表設計不一致，需決定 (a) Python 補 DB audit INSERT (b) 放棄 DB 表 |
| **ml_parameter_suggestions** | Python `optuna_optimizer.py:405` INSERT | ❌ 無 SELECT（governance_status 設計為 operator 審閱，但 API 未接） | 0（Optuna 未跑） | **writer_only orphan** | Optuna integration + governance UI |
| **foundation_model_features** | Python `dl3_foundation.py:256` INSERT | Python `weekly_report_generator.py:278`, `phase4_routes.py:649/664/682` SELECT | 0（DL-3 foundation runner 未啟 cron） | **code-complete, dormant** | Phase 4 DL-3 cron |
| **dl3_ab_decisions** (無 migration，lazily created?) | Python `dl3_ab_runner.py:428` INSERT | Python `phase4_routes.py:694` SELECT | 0 | **orphan** | **警告：無 migration CREATE TABLE**，run time 首次 INSERT 會 crash。**TODO E2**：補 migration |
| **weekly_review_log** | Python `weekly_report_generator.py:573` INSERT | Python `phase4_routes.py:862` SELECT | 0（weekly cron 未啟） | **code-complete, dormant** | Phase 4 cron |
| **pattern_insights** | Python `ai_service_feedback.py:105` INSERT | Python `ai_service_feedback.py:151` SELECT 本檔（寫入後 Strategist 讀? memory 敘述「StrategistScheduler 在構建 Ollama prompt 時讀取」但 grep 未見 strategist file 直 SELECT） | 若 Analyst 跑 review 就寫（Analyst agent 主動）| **partial live — 需驗 Strategist consume 鏈** | 驗 Strategist/prompt_builder 實際 SELECT pattern_insights |
| **strategist_applied_params** | Rust `strategist_scheduler/persist.rs:68` INSERT | Rust `persist.rs:146`, Python `strategist_history_routes.py:152/196/237` SELECT | Strategist promote cycle 寫；V019+V020 tie-break | **live** | — |

### 其他 schema

- **features.online_latest** / **features.versions**：V004 設計，無 writer/reader grep match — dead 或僅 via Rust config startup（feature_writer.rs 寫 market features 不是 learning features）
- **observability.scorer_predictions** / **observability.model_performance**：**無 writer no reader** — 0 rows, 0 consumers
- **observability.feature_baselines**：Rust `drift_detector.rs:256` SELECT（READER 存在），但 **無 INSERT writer** — reader_only orphan（Mac grep 無 INSERT；可能由 SQL script 手動 seed 或尚未接）
- **observability.drift_events**：Rust `drift_detector.rs:494` INSERT（writer）；consumer 未 grep 到（可能 GUI）
- **observability.data_quality_events**：Rust `quality_writer.rs:97` INSERT（writer）；consumer GUI only
- **observability.engine_events**：Rust IPC patch handler 寫；governance/IPC audit trail
- **risk.***：writer Rust `black_swan_detector.rs`；consumer `black_swan_notifier`（runtime active）
- **market.news_signals**：Rust `news/pipeline.rs` 寫；consumer Rust `feature_collector` + Python phase4

---

## 3. ML Pipeline Stage × (接線 / 資料可得 / Blocker)

| Stage | 模組 | Code 狀態 | Runtime 狀態 | 資料可得 | Blocker |
|------|------|-----------|-------------|---------|---------|
| **0. Trade tick → feature** | Rust `tick_pipeline/*`、`feature_collector` | ✅ | ✅ live | features 每 tick 產生 | — |
| **1. Entry-time snapshot** | Rust `decision_feature_writer`、`context_writer` | ✅ | ✅ live | `decision_features` 1.65M rows | — |
| **2. Close fill → label 回填** | Rust `trading_writer` + Python `edge_label_backfill.py` | ✅ | ✅ active（手動或 cron 跑 backfill） | 24h ~40-100 rows | **warn**：P1-10 grid fee drag → close_fills 量低；P1-11 bb_breakout 0 |
| **3. Exit feature → exit_features** | Rust `exit_feature_writer` + Track P v2 `phys_lock_gate4` | ✅ | ✅ live | 1:1 with close_fills | — |
| **4. JS edge estimator → JSON** | Python `james_stein_estimator` wrap in `edge_estimator_scheduler.py` daemon | ✅ | ✅ **hourly** | `settings/edge_estimates.json` mtime < 90min | **partial**：寫檔不 INSERT `james_stein_estimates` 表（decoupled by design） |
| **5. Edge JSON → Rust cost_gate** | Rust startup `set_edge_estimates()` | ✅ | ⚠️ **no hot-reload**（engine 重啟才吃）| 當前 grand_mean < -50 bps 未達 bind 條件 | P1-14 bind 條件：grand_mean > -50 + ≥2 策略 shrunk>0 |
| **6. ONNX training pipeline** | Python `run_training_pipeline.py`（ETL→CPCV→quantile trio→CQR→acceptance→ONNX）| ✅ | ❌ **never run** | 0 artifact | **P1-7 C**：max slice `demo grid_trading BLURUSDT` 47/200 labels |
| **7. Model Registry insert** | Python `model_registry.py::register_quantile_trio_from_onnx_out` | ✅ | ❌ 0 row | — | stage 6 先跑 |
| **8. Canary state machine** | Python `model_registry.py::transition_canary_status` + `/api/v1/ml/model_promote` route | ✅ | ❌ 0 transition | — | 先 stage 6/7 + operator 審批 |
| **9. Rust OnnxModelManager consume** | Rust `ml/registry.rs` + `ml/model_manager.rs`（resolver 存在，load path 未整合）| ⚠️ 半完成 | ❌ Phase 3+ deferred | — | Phase 3 Track L live 才接 |
| **10. Combine Layer shadow** | Rust `combine_layer.rs::build_ml_inference_shadow` mock + `shadow_exit_writer` 接線 | ✅ | ❌ **shadow_enabled=false default** | 0 decision_shadow_exits row | operator TOML/IPC flip `RiskConfig.exit.shadow_enabled=true` |
| **11. ExecutorAgent shadow→live 切換** | Python `executor_agent.py:482` `_shadow_mode=True` default | ✅ | ❌ shadow 狀態 | 0 real IPC submit 從 ExecutorAgent 發出 | G-1 R-02 ExecutorConfig 加 shadow=False flag + Rust IPC SubmitOrder 接收契約 |
| **12. Teacher → Directive → Applier** | Rust `claude_teacher/*` + Python `applier.rs` | ✅ | ❌ dormant | 0 directive | G-7 W23 Phase 4 Teacher |
| **13. LinUCB arm select** | Python `linucb_trainer` + Rust `linucb/state_io` | ✅ | ❌ dormant | 0 arm pulls | `linucb_shadow_compare` deferred |
| **14. Thompson sampling / Bayesian** | Python `thompson_sampling.py` | ✅ | ❌ dormant | 0 | 無 runtime 接線 |
| **15. DL-3 Foundation Model** | Python `dl3_foundation.py` + `dl3_ab_runner.py` | ✅ | ❌ dormant | 0 | Phase 4 cron |
| **16. Weekly Review + Report** | Python `weekly_report_generator.py` | ✅ | ❌ dormant | 0 weekly review | operator cron |
| **17. Drift Detection (PSI/ADWIN)** | Rust `drift_detector.rs` | ✅ | ⚠️ **writer spawned** + reader `feature_baselines` 缺 writer | 未知（依 baseline 是否 seed） | **TODO Linux**：查 feature_baselines 是否有 row；若空 drift_detector 走不通 |
| **18. Pattern Insight → Strategist prompt** | Python `ai_service_feedback.py` + Analyst | ✅ | ⚠️ Analyst 寫但 Strategist consume 鏈未完全驗 | 若 Analyst 跑才有 | 驗 `strategist_scheduler` prompt builder 是否 SELECT pattern_insights |

---

## 4. Phase 評級（DUAL-TRACK + INFRA-PREBUILD-1）

| 組件 | Phase 1a | Phase 2 | Phase 3 | Production |
|------|:--------:|:-------:|:-------:|:----------:|
| Track P v1 linear | ✅ retired 2026-04-22 | — | — | — |
| Track P v2 non-linear + ExitConfig | ✅ live 2026-04-22 | ✅ | ✅ | ✅ |
| EXIT-FEATURES-TABLE-1 | ✅ live | — | — | — |
| Combine Layer shadow writer | ✅ infra | ⬜ **需 flip flag** | ⬜ | ⬜ |
| build_ml_inference_shadow mock | ✅ code | ⬜ | swap real ONNX | ⬜ |
| Model Registry | ✅ infra | ⬜ **0 row** | ⬜ Rust OnnxManager wire | ⬜ |
| Canary 4-state machine | ✅ code | ⬜ 0 transition | ⬜ | ⬜ |
| ExecutorAgent shadow | ✅ default | ⬜ shadow=False flag | ⬜ | ⬜ |
| JS edge estimator daemon | ✅ live (JSON) | ⬜ hot-reload | ⬜ bind cost_gate | ⬜ |
| ONNX train pipeline | ✅ code | ⬜ **47/200 labels** | ⬜ | ⬜ |

---

## 5. V023 Postmortem 狀態（CLAUDE §七 新規範）

| 項 | 狀態 |
|---|------|
| V023 `CREATE TABLE IF NOT EXISTS` silent-noop 根因 | ✅ 已釐清（V004 legacy stub）|
| V023 Guard A retrofit | ✅ `V023__model_registry.sql:63-95` |
| V021 Guard A (decision_shadow_exits) | ✅ `V021__fills_exit_source.sql:159-188` |
| V021 Guard B (fills.exit_source type + shadow.ts type) | ✅ 兩個 |
| Guard template + 9 tests | ✅ `sql/migrations/tests/test_schema_guards.sql` + `templates/schema_guard_template.sql` |
| 新 migration Guard 強制要求入 §七 | ✅ 2026-04-24 new |
| Engine OPENCLAW_AUTO_MIGRATE opt-in 自動 | ✅ Phase 2 加入（`database/migrations.rs`）— V004+ 歷史 seed 到 `_sqlx_migrations` |
| V004 10 張表的 guard retrofit | ❌ **未做**（所有 pre-V021 表無 guard，若 legacy 漂移 silent skip） |

---

## 6. Outcome_* NULL 問題驗證

| 階段 | 狀態 |
|------|------|
| RCA (2026-04-21 memory `project_decision_outcomes_not_dead.md`) | ✅ 已完成 |
| Bug 1: `timeframe '1' vs '1m'` unmatched JOIN | ✅ 修復 commit `5e2981d` 2026-04-21 |
| Bug 2: `engine_mode` INSERT 漏接線 → schema default `paper` | ✅ 修復同 commit |
| Regression guard | ✅ `outcome_backfiller.rs::BACKFILL_SQL` const + comment + tests.rs |
| 歷史回填 | ✅ ~267k rows backfilled |
| 當前 runtime | ⚠️ **TODO Linux**：psql 驗 `SELECT count(*) FROM trading.decision_outcomes WHERE backfilled_ts > now()-24h;` + `AND outcome_1m IS NOT NULL` |

---

## 7. 當前真能 inform 決策的 ML 組件

**答案：0 個真正 ML，1 個 JS estimator**

唯一有連到 runtime 決策的「學習」組件：

1. **JS Edge Estimator daemon**（`edge_estimator_scheduler.py` P1-7 B, 2026-04-19 `23b14ef`）
   - 狀態：✅ 每小時刷 `settings/edge_estimates.json`
   - 消費：Rust startup 一次載入 → cost_gate 門檻（**非 hot-reload**）
   - **P1-14 bind blocker**：grand_mean > -50 bps + ≥2 策略 shrunk>0 條件未滿足 → cost_gate threshold 目前走 TOML 靜態值
   - 類型：**James-Stein shrinkage（statistical），不是 ML**

**所有其他 ML 組件都是 Foundation/Skeleton 階段**：
- Strategist 調參 via Ollama prompt engineering（Live, shadow=False）→ 寫 `strategist_applied_params`（是 LLM 不是 ML）
- Claude Teacher / LinUCB / Bayesian / DL-3 / Foundation Model：全 dormant

---

## 8. Blocker 優先級（MIT 建議）

### P0（即時阻 Phase 2）
1. **Combine Layer shadow flag flip**：operator 需 `RiskConfig.exit.shadow_enabled=true`（TOML 或 IPC）→ decision_shadow_exits 開始寫 → check [8] 從 dormant PASS 轉 live PASS + agreement% 評估
2. **訓練 labels 累積**：P1-7 C ETA ~3-5d；P1-10 EDGE-P2-3 PostOnly 1w 觀察是否提升入場量；**無 code action**，純等

### P1（阻 Phase 3）
3. **ExecutorAgent shadow→live 契約**：`ExecutorConfig` 加 `shadow_mode` flag 可配；Rust `SubmitOrder` IPC 接收 Python intent 的完整契約（包括 decision_lease 檢核 + Rust 端 reject 回傳）；G-1 R-02 排期
4. **Rust OnnxModelManager wire**：第一個 ONNX artifact 跑出後，Rust startup 呼 `resolve_latest_production_artifact` 載 model，Phase 3+ Track L 接 combine_layer
5. **`feature_baselines` writer 缺失**：drift_detector 讀但無 writer → drift 檢測走不通；需 migration seed script 或 runtime 寫入

### P2（結構修復）
6. **V004 10 張表 Guard A retrofit**：避免未來 drop+部分 re-apply 再次 silent-noop
7. **`dl3_ab_decisions` 表無 migration**：Python writer INSERT 會 crash（首次跑 DL-3 A/B 時）；需補 migration
8. **Dead code 盤點**：`rl_transitions` / `symbol_clusters` / `features.online_latest/versions` / `observability.scorer_predictions` / `observability.model_performance` — 確認是保留 schema pre-build 還是刪除
9. **`promotion_pipeline` DB 表 vs Python 類 不一致**：決定 (a) Python 補 DB audit INSERT (b) 移除 DB 表

---

## 9. 附錄：MIT 建議的 Operator 驗證 SQL（Linux）

```sql
-- 1. outcome_backfiller 健康
SELECT count(*) FILTER (WHERE outcome_1m IS NOT NULL) AS labeled,
       count(*) FILTER (WHERE outcome_1m IS NULL) AS null_outcome,
       count(*) FILTER (WHERE engine_mode = 'paper' AND backfilled_ts > now() - interval '24h') AS backfilled_paper_24h,
       count(*) FILTER (WHERE engine_mode = 'demo' AND backfilled_ts > now() - interval '24h') AS backfilled_demo_24h
FROM trading.decision_outcomes;

-- 2. learning.model_registry 空驗
SELECT count(*) FROM learning.model_registry;  -- expect 0 until first run_training_pipeline.py

-- 3. decision_shadow_exits 空驗
SELECT count(*) FROM learning.decision_shadow_exits;  -- expect 0 while shadow_enabled=false

-- 4. P1-7 C label slice — max
SELECT strategy_name, engine_mode, symbol, count(*) AS labeled
FROM learning.decision_features
WHERE label_net_edge_bps IS NOT NULL
  AND ts > now() - interval '90 days'
GROUP BY 1, 2, 3
ORDER BY labeled DESC
LIMIT 10;

-- 5. observability.feature_baselines writer 缺失
SELECT count(*) FROM observability.feature_baselines;  -- expect 0 if never seeded

-- 6. V004 legacy drift audit
\d+ learning.model_registry  -- 必含 canary_status, verdict
\d+ learning.rl_transitions  -- 必含 state_vector REAL[]
\d+ learning.symbol_clusters -- 必含 assignments JSONB

-- 7. dead-code confirm
SELECT
  (SELECT count(*) FROM learning.rl_transitions) AS rl,
  (SELECT count(*) FROM learning.symbol_clusters) AS sc,
  (SELECT count(*) FROM learning.cpcv_results) AS cpcv,
  (SELECT count(*) FROM learning.bayesian_posteriors) AS bp,
  (SELECT count(*) FROM learning.james_stein_estimates) AS js,
  (SELECT count(*) FROM learning.foundation_model_features) AS fmf,
  (SELECT count(*) FROM observability.scorer_predictions) AS sp,
  (SELECT count(*) FROM observability.model_performance) AS mp;
```

---

## 10. 結論

**ML 基座達標 85%**（schema + infra + migration guard + postmortem fix 到位），但 **實際部署於 Foundation-Skeleton 邊界**：

- Combine Layer shadow、Model Registry、ExecutorAgent shadow 全屬「代碼到位、writer spawn、但 flag off 或 0 row 累積」的 **skeleton** 階段
- 唯一真到 runtime 的「學習」是 JS edge estimator 每小時刷 JSON（非 ML）
- 從 Foundation 進 Shadow 的最小動作 = (a) operator flip `shadow_enabled=true` (b) P1-7 C 等 labels 累積過 200
- 從 Shadow 進 Canary 需 ExecutorAgent shadow→live flag + Rust OnnxManager wire；合計工作量約 ~1-2 週（屬 G-1 R-02 排期）
- 從 Canary 進 Production 需通過狀態機 4 states + Operator 審批 + 實質倉位放量，目前**無 ETA**

**MIT AUDIT DONE**: `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-04-24--ml_db_foundation_audit.md`
