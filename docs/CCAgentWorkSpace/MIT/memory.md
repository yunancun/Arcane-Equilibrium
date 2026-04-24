# MIT Memory

_Last updated: 2026-04-24_

## 關鍵事實

- **V023 silent-noop postmortem (2026-04-23)**：V023 入 repo 後在 Linux 靜默 no-op；V004 預建 legacy stub 缺 `canary_status/verdict` 欄 → CREATE TABLE IF NOT EXISTS 跳過。修復：V023/V021 retrofit Guard A + Guard B，CLAUDE.md §七 新規範所有新 migration 強制 Guard A/B/C + idempotency 驗證
- **Outcome backfiller fix (2026-04-21 commit `5e2981d`)**：timeframe `'1'→'1m'` + engine_mode INSERT 兩 bug 修復；歷史回填 ~267k rows；`outcome_backfiller.rs::BACKFILL_SQL` const 有 regression guard comment 標註
- **Engine_mode 標籤層**：`paper/demo/live/live_demo` 四值，V021/V023/V015 CHECK 齊一；Live+LiveDemo endpoint 寫 `live_demo` 而非 `live`（2026-04-16 起）
- **edge_estimates 自動化 (P1-7 B, 2026-04-19 `23b14ef`)**：`edge_estimator_scheduler.py` daemon thread 隨 uvicorn 跑；每小時刷 `settings/edge_estimates*.json`；無 hot-reload，engine 重啟才吃
- **P1-7 C 阻塞**：`run_training_pipeline.py` 工具鏈綠但最大切片 `demo grid_trading BLURUSDT` 47/200 labels，ETA ~3-5 天自然累積過閾

## Silent-dead pattern

`helper_scripts/db/passive_wait_healthcheck.py` 已有 12 個 check；新增被動等待 TODO 必須登記 check（CLAUDE.md §七「被動等待 TODO 必附 healthcheck」）。
常見 silent-dead 指紋：24h=0 + 設計上期望 ≥1 fire → FAIL；24h 有量 + last_1h=0 → channel stall

## Writer/Consumer 矩陣（2026-04-24 盤點結論）

**Active Write + Read**：decision_features、exit_features、decision_shadow_fills、directive_executions、linucb_state、ai_usage_log、ai_budget_config、strategist_applied_params、experiment_ledger

**Write-only（無 Python/Rust reader）**：rl_transitions、symbol_clusters、foundation_model_features（weekly report 讀但不驅動決策）、pattern_insights（ai_service_feedback write + read 但 strategist consume 點待確認）、cpcv_results、bayesian_posteriors、james_stein_estimates（只有 JSON file→engine）

**Read-only（無 writer）**：observability.feature_baselines（drift_detector 讀，writer 缺）、model_registry（2026-04-23 V023 live 但 0 row，待 `run_training_pipeline.py` 跑出第一行）、decision_shadow_exits（writer spawn 但 shadow_enabled=false）、promotion_pipeline（Python 類有設計無 INSERT）

**未接線**：observability.scorer_predictions、observability.model_performance

## Runtime 已知狀態

- engine PID 884467（2026-04-24 02:06 CEST rebuild） · uvicorn 4 workers
- edge_estimator_scheduler leader lock via flock，4 worker 1 active
- Shadow Exit writer task spawn OK，shadow_enabled=false → 0 row（dormant by design）
- Executor Agent `_shadow_mode=True` default（executor_agent.py:482，設計避 Path A/B 衝突）
- Strategist `shadow=False`（live），Guardian/Analyst MessageBus subscribed

## 2026-04-24 審計產出

- `workspace/reports/2026-04-24--ml_db_foundation_audit.md` — 21+ learning schema 全表 audit + pipeline stage 接線評級
