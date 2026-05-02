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

## 2026-04-26 Wave 3 Data Audit

**Report**: `workspace/reports/2026-04-26--wave3_data_audit.md`

**Three key findings**:
1. **EDGE-P3 (c) gate 邏輯錯誤** — `orphan_frozen` by design 永不進 exit pipeline（DUST_FROZEN_STRATEGY 是 quarantine sink, NO close dispatched, see `dust_gate.rs:99-114`）→ healthcheck [11] criterion `orphan_rows >= 20` 永遠 0 → Wave 3 永久 stalled。建議改 `orphan_adopted ≥20` 或刪掉 (c)。
2. **EDGE-P3 解鎖最早 4/30**（修 (c) 後）/ 中位 5/02 / 悲觀 5/05。3d streak 從首次 PASS 算起。
3. **G2-06 切 5m 比硬調 1m bw 乾淨** — F1 是 timeframe-bandwidth structural mis-design（1m + squeeze_bw=0.03 100% 觸發），不是 threshold 不準；建議 1m + 5m 雙跑對比 forward-return；若 5m 也差直接 disable bb_breakout（alpha-failed）。

**EDGE-P1b 7 維 = `est_net_bps / peak_pnl_pct / atr_pct / giveback_atr_norm / time_since_peak_ms / price_roc_short / entry_age_secs`**（V999 schema）。「閾值 bind」= 對 `realized_net_bps>0` cohort 算 percentile → 寫回 `RiskConfig.exit.*` thresholds（IPC 路徑），**不是** JS estimator → cost_gate（那是 P1-14 separate bind）。bind 視窗建議 rolling 14d + 7d embargo + per-strategy stratification。

**Counterfactual rate per day fallback = 30/day static**（line 1282），實際 healthcheck 訊息推估 ~50/day（≥2 daily snapshot 已存在）。1d 達 200 可信，前提：cron 不掛 + engine 不崩（線性累積非 burst）。

**bb_breakout_threshold_sweep.py 已修 leak-free shift(1)（line 205-206 + 双 stats output）+ Bonferroni + cluster-SE + df-aware t_crit**（CLAUDE.md §三 multi-role audit 條目），G2-06 不需要重做這些方法論修齊；只需換 5m timeframe + sweep period（20 bars 在 5m = 100min 視窗，需驗證 squeeze persistence 假設）。

## 2026-05-02 LG-5 RFC review (CONDITIONAL APPROVE)

**Report**: `workspace/reports/2026-05-02--lg5_rfc_review.md` + `.claude_reports/20260502_152000_mit_lg5_rfc_review.md`

**Key findings**:
1. **Attribution chain ratio 已恢復**：實測 last 24h = 55.07%（5/2 single-day 68.97%）；PA RFC 寫的 0.154 是 7d 窗口被 4/18-4/28 全 0 段拖低的過時數字。MIT-S2-1 root-cause **already shipped 2026-04-29 evening**（commits ece31b6 / 45bbe4d / **5895579**）— 不是 future work。R-meta 0.50 binary gate 維持但**不再** effectively 凍結 promotion。
2. **`learning.governance_audit_log` 不存在**（29 個 learning 表，0 個 audit/governance 表）— 必開 V035 migration（含 Guard A/B/C，CLAUDE.md §七）；阻塞 LG-5-IMPL-2 audit emission。
3. **PA RFC §2.2 status filter 錯誤**：寫 `status='live_candidate'`，實測 CHECK constraint = `applied/skipped/failed/candidate/dry_run`；真實值 `status='candidate' AND application_type='live_promotion_candidate'`（25 條 pending，PA 寫 24 是 -1day stale）。
4. **R-meta 應 per-strategy 而非 global**（global 14.96% 7d 看似 fail，但 25 candidates 全 grid_trading + ma_crossover 兩 strategy，per-strategy 可能 ≥ 50%）。
5. **5 must-fix + 4 backlog**；MIT-S2-1 不阻塞 dispatch；只需 V035 (~3h operator) 後即可並行派 IMPL-1/3/4 → IMPL-2。

**Sign-off**: MIT ✓ APPROVE 條件成立後（PA 修 RFC + V035 land）。
