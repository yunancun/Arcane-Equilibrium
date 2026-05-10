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

## 2026-05-05 REF-20 Sprint C1+C2 R6/R7 capability + risk advisory (pre-DAG)

**Report**: `workspace/reports/2026-05-05--ref20_r6_r7_capability_risk.md` (509 lines)

**Boundary**: read-only schema/risk assessment for PA Sprint C task DAG; QC parallel work R6 confidence label math spec.

**8 結論**:
1. **GO**: capability probe race / cache（0 cache，每 cycle 重 probe；fail-soft OK）
2. **GO with R8 retention**: Block B cardinality（daily ~96-456 row calibrated_replay；Sprint D R8 必加 retention policy）
3. **GO + WARN-V036-INSERT-MISSING**: V036 function body INSERT (line 208-243) **未寫 4 個 metadata column**（evidence_source_tier / replay_experiment_id / manifest_hash / expires_at）— R6/R7 dispatch 前必驗，否則 producer 升級後 row body 仍 real_outcome
4. **GO**: sibling CC FUP-2 不在 flight（commit `34211ab4` 2026-05-02 已 PASS to E4）— PA report §0.6 過期
5. **GO**: trading.fills retention 365d >> 30d R6 需求；fee_rate column V008 已 land
6. **WARN**: expires_at TTL default 30d 太長 → MIT 建議 caller 傳 7d（不需改 V036）
7. **GO**: xlang byte-equal contract maintained（V051 line 367-376 manifest_hash BYTEA byte-identical）
8. PA §2C capability 描述需修正：實際 **6 個 capability key 不是 3 個**；4 個 全 true 才走 Block B 完整版（non-trivial fail-soft hierarchy）

**Key findings (新)**:
- `attribution_chain_ok` **不是** mlde_demo_attribution column 而是 `learning.mlde_edge_training_rows` SQL VIEW 計算 column（V031 line 332-336 + V034 line 306）— PA 描述方向對但 column 位置誤標
- attribution_chain_ok 4 source: signal_id / context_id / signal_context_id == context_id / label_net_edge_bps NOT NULL（全在 mlde_shadow_recommendations）
- FUP-2 真實 fix 範圍是 #4 label_net_edge_bps backfill（cron edge_label_backfill + healthcheck [43]）
- V036 比 V051 嚴 4 條（source allowlist + tier allowlist + TTL non-null + TTL future）
- producer cycle interval = 3600s（hourly）；dream_engine 3-15 row/cycle，opportunity_tracker 1 row/cycle，total daily ~96-456 row calibrated_replay（不洪水）

## 2026-05-08 DB + ML 基座專項 audit

**Report**: `workspace/reports/2026-05-08--db_ml_foundation_audit.md` (418 行)

**Engine 狀態**：PID 3854831 active 22:01-；uvicorn 4 workers；HEAD `4e2d2883`

**核心發現（推翻先前部分結論）**：

1. **Migration 套用 65/65 success=t**（V022/V042 跳號是預設）；V001-V020 + V025/V029 0 Guard pre-postmortem 接受；**V062/V063/V065 退化 0 Guard 違反 CLAUDE.md §七**
2. **21 表 DEAD**（0 row + 0 producer code 或 producer-OFF）：learning 14 / observability 4（含 feature_baselines + drift_events）/ replay 5 / agent 1
3. **engine_mode 4 值齊全**：trading.risk_verdicts.live=2.5M / trading.decision_outcomes.live=89734（stale 18d）/ learning.mlde_shadow_recommendations.live=53 — 真實 live row 寫入 SOP 工作中；trading.fills 仍含 demo_archive_20260418=6616 殘餘
4. **attribution_chain_ok 24h = 0.016%**（45/277054）— PA 之前 55% 過期；FUP-2 attribution writer 必須 land
5. **walk_forward CV 缺 purge + embargo**（edge_estimate_validation.py:113-148）；CPCV 有但用得少
6. **Rust runtime leak-free OK**（KlineManager 只回 closed_bar；indicators 用 closed buffer；feature_collector 34-dim vec leak-free）
7. **replay.simulated_fills 6 row 全 'synthetic_replay' tier**（不可餵 ML）；calibrated_replay + counterfactual_replay 0 row 0 producer code → ML training 12 個月內不可能 ready
8. **V059 edge_estimate_snapshots = Foundation only**（457 row 2026-05-07 一次性 ref21_backfill；無 cycle writer）
9. **Drift chain broken**：feature_baselines writer 不存在 → drift_events 0 row → 不能 fire
10. **risk_verdicts 18.47M row × 5 chunk = 3.7M/chunk + 無 compression 無 retention** — M5 Ultra PG 4-8GB 風險高

**ML 基座達標率 ≈ 38%**（13 component 中 4 Production / 4 Canary fragile / 4 Shadow / 4 Skeleton / 5 Foundation / 5 Aspirational）。距 Mainnet ML-driven trading **3-4 sprint**（最早 2026-08-01 樂觀 / 2026-09-01 中位 / 2026-11-01 悲觀，**完全不在 PA 5/30 中位內**）。

**9 個 V068+ migration 提議**：4 砍 dead schema / 3 補 producer / 2 retention+Guard。

## 2026-05-09 對抗性核實 5/8 audit 24h 後（W-AUDIT-4 修復狀態）

**Report**: `workspace/reports/2026-05-09--db_ml_verification.md` (359 行)

**HEAD drift**: `4e2d2883` → `7fccad06`（28 commits 中 10 W-AUDIT-4-related migration 加上 V077 columnstore fallback patch）

**核心發現**：
1. **V068-V077 全 10 condition apply 成功**（success=t）— **commit 數 ≠ runtime live**：5 真 IMPL（V069 真 drop scorer_predictions / V075 retention 9 表 / V076 Guard retrofit / V077 trigger fallback / V073/V074 source-only contract guard），4 commit message 誤導為「add cycle/backfill」實為 source-only（cron 未 install），1 truthful narrow scope。
2. **dead schema cleanup「24→2」嚴重縮水**：V068/V070/V071 從「destructive cleanup」改為「reclassification only, COMMENT-only」— PA source audit 發現 21 表中 19 仍有 active route/cron/Rust writer/Agent Spine 引用 → MIT 接受縮水但 warns `rl_transitions / symbol_clusters / experiment_ledger / weekly_review_log / pattern_insights` 5 表實質 dead。
3. **ML 基座達標 38% → 42%**（+4 percentage points）：13 component grid 中 +1 Production（V077 CHECK constraint）/ +1 Shadow（Replay simulated_fills 從 Foundation 升，因 5 calibrated_replay row 5/7 burst 突破 0）/ Aspirational -1（calibrated_replay 突破）；其他 component **無實質升階**。
4. **attribution_chain_ok 24h: 0.013% → 0.0188%**（**未實質改善**）；7d 0.048%；NEW-ISSUE-7：5/6→5/7 mlde_edge_training_rows total 從 60/day → 22036 → 264546（denominator 4400×擴大）拖低 ratio — 需 RCA view definition 5/6 改動。
5. **edge_estimate_snapshots V059 24h=0**（仍 stale 5/7 00:46）— V073 contract guard pass 但 cron `edge_estimate_snapshots_cycle_cron.sh` **未 install in crontab**。
6. **decision_outcomes.live latest_backfill 仍 4/20**（19d stale，沒任何改善）— V074 contract guard pass 但 outcome_backfiller_live cron 未 install。
7. **feature_baselines 仍 0 row + 0 writer** — V072 verbatim「contract guard only, does not seed baselines and does not add a writer」→ **drift chain 仍 broken**。
8. **risk_verdicts retention 30d job 1027 真 active** + compress_after 7d；V075 對 5 hypertable 真效，但 plain table（learning.decision_features / trading.decision_outcomes）的 prune function 是 dry-run default，**未 schedule cron 自動 invoke**。
9. **Dream Engine** code 在（dream.rs + dream_engine.py），5/7 一次性 burst 5 calibrated_replay row 後 dormant；**Teacher-Student v0.4 仍 Aspirational 0 code**。
10. **真實 PG settings** work_mem=4MB / shared_buffers=128MB / max_connections=100 — work_mem **嚴重低**（OpenClaw 18M+ row 表大量 disk spill 風險），M5 Ultra 部署前必修。

**對抗性 push back**：
- commit message 「audit: add edge snapshot cycle wrapper」/「audit: add live outcome backfill schedule support」**誤導為 IMPL**，實為 source-only（cron 未 install）— 應寫「prepare ... cron install pending operator」更誠實。
- W-AUDIT-4 closure semantic creep：70% schema-side land / 30% writer-side scripts written but not installed → runtime 健康度未實質提升。

**P0 立即 operator action（W-AUDIT-5 提案）**：
1. install crontab `outcome_backfiller_live_cron.sh`（V074 lifecycle）
2. install crontab `edge_estimate_snapshots_cycle_cron.sh`（V059 active）
3. PG `ALTER SYSTEM SET work_mem='32MB'` + reload
4. RCA mlde_edge_training_rows 5/6 後 explosion source

**距 Mainnet ML-driven 預估**：3-4 sprint（**未變**）；最早 8/15 樂觀、9/15 中位、11/15 悲觀。

## 2026-05-09 v2 對抗性核實（v1 → v2 24h delta）

**Report**: `workspace/reports/2026-05-09--db_ml_verification_v2.md`

**HEAD drift**: `455d796e` → `1bd55689`（34 commits, ~24h）

**核心發現**：
1. **V078 lease_transitions BYPASS audit live**（唯一真升級）— 7955 BYPASS row/24h, ~33/min steady; Rust runtime 真接到（PID 298034 binary built 14:02 started 15:52）；Stage Foundation→Production
2. **feature_baseline_writer 是 CLI dry-run tool 不是 daemon writer**（commit message 嚴重誤導）— Rust binary 編譯 + 部署但 default `--dry-run`，無 cron，無自動執行；feature_baselines 表仍 0 row；drift chain 仍 broken
3. **portfolio_var.py + cvar.py + promotion_gate.py 是 dormant code**（cc6476dd + 716eb3d6）— PromotionPipeline class 無外部 caller，`_entries: dict` 從未被 populated；標 Aspirational stage
4. **attribution_chain_ok 24h 0.0188% → 0.5041% 是 denominator artifact**（不是真改善）— absolute ok_n 44→65 只 +47%，但 denominator 234416→12894 跌 94.5%；5/9 anomaly 比 5/6 anomaly 反方向；RCA mlde_edge_training_rows producer / view changes
5. **cost_edge_advisor_log 仍 0 row**（env 仍 OFF）/ **decision_outcomes.live 仍 4/20 stale**（V074 cron 未 install）/ **edge_estimate_snapshots 仍 5/7 stale**（V073 cron 未 install）— v1 P0 全部未動
6. **V078 無對應 healthcheck**（CLAUDE.md §七 違規 +1）

**v2 commits 分類**（34 total）：3 真 runtime IMPL / 12 source-only dormant / 11 docs / 5 strategy config / 3 test-only

**ML 基座達標率**：v1 42% → v2 44%（+2 pp，僅 V078 真貢獻）；距 Mainnet ML-driven 仍 3-4 sprint（樂觀 8/15 / 中位 9/15 / 悲觀 11/15，**未變**）

**對抗性 push back**：
- commit message「ml: add 34-dim feature baseline writer」誤導（應為「rebuild CLI tool, dry-run default, no scheduling」）
- commit message「learning: enforce selection bias promotion gate」誤導（應為「add gate code; no caller wires to runtime」）
- v2 的 W-AUDIT-4 closure semantic creep 持續 — schema-side 推進、runtime-side 停滯

## 2026-05-09 v3 對抗性核實（v2 → v3 5 commits + PA redesign cross-check）

**Report**: `workspace/reports/2026-05-09--db_ml_verification_v3.md`

**HEAD drift**: `1bd55689` → `da2aba11`（5 commits, ~3h delta）

**核心發現**：
1. **V079 migration 完全未 apply**（_sqlx_migrations max=78）— 48227607 commit 的 strategy_trial_ledger + promotion_pipeline 新 column 0% 落地到 PG；engine binary 14:07 built 比 commit 18:03 早 4h，需 operator restart 才會跑 migration
2. **ml_training_maintenance_cron.sh 未 install in crontab**（da2aba11 加 source 補 5 legacy ML jobs but cron not fire）— W-AUDIT-4 P0 4 cron 從 v1 到 v3 三天 0 進展
3. **attribution_chain_ok 24h 0.5041% → 1.0857% 仍 denominator artifact**（absolute ok_n 65→76 only +17%，total 12894→7000 -46%）
4. **真實 attribution root cause v3 第一次定位 = `label_close_tag IS NULL` 98.9%**（6906/6983 has signal_id+context_id+label NULL）— v1 v2 報告均未挖到此層；FUP-2 cron 只 backfill label_net_edge_bps 不 backfill label_close_tag
5. **`feature_collector::FEATURE_NAMES` 34-dim 100% OHLCV-derived**（SMA/EMA/RSI/MACD/BB/ATR/Stoch/KAMA/ADX/Hurst/Donchian/regime/price）— 0 funding/basis/OI/orderflow/cross-asset → PA Layer 1 §1.1 「alpha-source 結構性貧乏」MIT 視角強烈 AGREE
6. **`exit_features` 7-dim 100% OHLCV-derived**（est_net_bps / peak_pnl_pct / atr_pct / giveback_atr_norm / time_since_peak_ms / price_roc_short / entry_age_secs）
7. **lease_transitions BYPASS 24h 7955→11133（+40%）**— 唯一 active progress（v2 V078 真 IMPL 持續生效）
8. **decision_outcomes.live 仍 4/20 stale 19d**（v3 demo + live_demo 18:47 fresh，live cohort backfiller 仍未 install）
9. **5 commits 全部 0 healthcheck**（違反 CLAUDE.md §七 強制規範 5/5）
10. **V079 SQL 無 Guard A/B/C**（沿 V062/V063/V065 退化模式；E2 應 reject）

**v3 commits 分類**（5 total）：0 真 runtime IMPL / 2 source-only ML pipeline（48227607, da2aba11）/ 1 governance docs + audit helper（c081029d）/ 2 N/A for ML pipeline（ad14db07 indicator guard, c2ab7b1a agent skill）

**ML 基座達標率**：v2 44% → v3 **44%**（0 真進步；dormant code +2 module 但 runtime 0 升階）

**PA redesign verdict**: **PARTIAL AGREE**：
- ✅ Layer 1 §1.1 alpha-source 結構性貧乏 完全 AGREE（feature_collector 34-dim 證明）
- ✅ Layer 1 §1.4 學習平面死 AGREE（attribution + drift + model_registry 三線 broken）
- ⚠️ Layer 1 §4.2 attribution root cause 描述不準（PA 歸於 hypothesis loop 缺；v3 SQL 定位真實是 label_close_tag NULL writer 缺接線）
- ❌ Layer 3 §3.5 漏列 dream_engine 在 alpha-source 升級藍圖角色（dream.rs 仍 5/7 burst dormant）
- ✅ Layer 4 R-1/R-2/R-3 路線圖 AGREE 但需加「修底層 label writer chain 是 R-3 之前 prerequisite」

**對抗性 push back**：
- commit message「audit: correct f08 ml cron scope」誤導（應為「prepare cron scope, install pending operator」）
- commit message「learning: push promotion evidence from edge cycle」加 +1275 LOC 但 V079 schema 不存在於 PG → 0 runtime impact + 加 dormant code 債務
- W-AUDIT-4 P0 4 cron 從 v1 到 v3 三天 0 進展（schema-side 推進、runtime-side 停滯 v3 加劇）

**距 Mainnet ML-driven**：仍 3-4 sprint（樂觀 8/15 / 中位 9/15 / 悲觀 11/15，**未變**）。若 PA R-1 R-2 R-3 architectural amendment 加入 = 樂觀延後到 2026-Q4 末。

## 2026-05-10 Sprint N+0 final MIT review

**Report**: `workspace/reports/2026-05-10--sprint_n0_final_review.md` (450 行)

**Scope**: V080+V082+V083+V084 + W-AUDIT-4b producer chain (M1+M2+M3 incl. E1-FIX-W2 retract) + W-AUDIT-9 T2 governance.canary_stage_log + AlphaSurface Phase A + invariant 21

**Verdict**: **RETURN-TO-E4 with HIGH/MED issues** (NOT unconditional APPROVE)

**核心發現**:

1. **V080 PASS APPROVE**: Guard A/B/C 完整；Linux PG empirical dry-run E1-A 已驗（manual_promote NULL lease REJECTED；stage=5 REJECTED；idempotent NOTICE-only）；MED/LOW push-back: 無 FK constraint between triggered_metric ↔ metric_registry；description column 無 length CHECK
2. **V082 PASS APPROVE**: Guard A/A2/A3/C 完整；Linux PG empirical 已驗；MED push-back: 30k/24h evaluation log 無 hypertable 無 retention（Sprint N+1 必加）；evidence_source_tier='shadow_synthetic' 可能 dead code at runtime
3. **V083 APPROVE WITH `[Linux PG VERIFY]` MUST**: NOT VALID CHECK 設計正確（不破歷史 38% NULL close fills）；Guard A/A2/B/C 完整；E1-B Linux PG dry-run **未跑**（Mac sandbox 拒絕）— 必 E4 / operator 接手；HIGH 風險：未來 ALTER VALIDATE CONSTRAINT lock 25k+ row 30s-3min；7d window opposite-side JOIN 對 funding_arb 退役後 OK
4. **V084 APPROVE WITH `[Linux PG VERIFY]` MUST + HIGH ML methodology risk**: UDF IMMUTABLE+PARALLEL SAFE 正確；view backward-compatible (V034 attribution_chain_ok formula 保留)；E1-C Linux PG dry-run **未跑**；**1/170 sample weight 4 大 issue**（hardcoded ratio 100x safety margin 無統計依據 / LightGBM 重複計數風險 / LinUCB Thompson 不直接消費 sample_weight / 無 trainer adapter Sprint N+0 內 ship）；type CHECK 太寬鬆（accepts double/real/numeric + LIKE 'timestamp%'）
5. **invariant 21 P0-MIT-LABEL-CLOSE-TAG-1 mock estimate 0.5%→90% 是 over-optimistic**: 真實 estimate 60-80%（depends on signal_id propagation in 3 reject paths）；99.2% best case / 0.6% worst case；invariant 21 ≥5% 可達；E4 third-pass 0.286% runtime 是 expected（engine 跑舊 binary）— restart_all.sh --rebuild --keep-auth 後 24h ratio 累積模型；6h 警告 healthcheck 建議
6. **W-AUDIT-4b producer chain 8 call sites 全 land**（grep emit_decision_feature_intent_rejected = 5 hits 證明 E1-FIX-W2 真補 E1-C fake-PASS）；FA invariant 5「feature_baselines first」與當前 N+0 scope 不符（feature_baselines 是 Sprint N+1 P1）— **建議 PM amend invariant 5 wording**
7. **AlphaSurface Phase A APPROVE**: 0 行為變化，trait 升級 + Tier 1-only build 設計乾淨；R-3 Hypothesis Pipeline N+5 併入路徑無新 PG schema 需求（Sprint N+5 才需 learning.hypotheses table）
8. **5 ML cron alignment**: 10 ML jobs 全讀 production decision_features view；split 對 trainer 透明 ✓；cron install pending operator (invariant 18)

**8 必要 actions before Sprint N+0 PM sign-off**:
1. **MUST**: E4 / operator V083 + V084 Linux PG dry-run × 2
2. **MUST**: operator install ml_training_maintenance_cron.sh + healthcheck PASS
3. **MUST**: operator deploy restart_all.sh --rebuild --keep-auth 激活 M3 Rust producer
4. **SHOULD**: 24h passive obs attribution_chain_ok ≥ 5%
5. **SHOULD**: PM amend invariant 5 wording
6-8. **MAY**: tighten V084 type CHECK / V082 hypertable + retention (N+1) / V080 FK or healthcheck

**Sprint N+1 carry-forward**: feature_baselines real writer / per-trainer sample_weight adapter / V082 hypertable+retention / signal_id RCA / AlphaSurface Phase B+C

---

## 2026-05-10 V083 + V084 Linux PG dry-run verify (MIT self-executed, HIGH-2 closure)

**Trigger**: Sprint N+0 sign-off HIGH-2 closure-blocking action — operator chose option B per CLAUDE.md §七 V055 mandate.

**Method**: ssh trade-core → docker exec trading_postgres psql for empirical Linux PG dry-run of V083 + V084 × 2 rounds + boundary case verify.

**Critical pre-audit finding**:
- `_sqlx_migrations` latest = V079, but V083/V084 objects ALREADY EXIST in PG (manually applied via `psql -f`, not via OPENCLAW_AUTO_MIGRATE=1 sqlx path).
- Implies sqlx checksum drift will trigger at next engine restart with AUTO_MIGRATE=1 — operator should run `bin/repair_migration_checksum` per V028-V034 SOP precedent (`memory/project_2026_05_02_p0_sqlx_hash_drift.md`).
- Dry-run path (re-apply existing) = NOTICE skip = idempotent verified, no production breakage.

**Verdict: PASS (full APPROVE, HIGH-2 closure CLEARED)**:
- V083 round 1 + 2: idempotent verified ✓ (4 Guards PASS, 0 RAISE)
- V084 round 1 + 2: idempotent verified ✓ (2 Guards PASS, 0 RAISE)
- V083 CHECK boundary 3 cases: PASS / PASS / REJECT (Case 3 entry_context_id NULL on close fill) ✓
- V084 UDF boundary 5 inputs: rejected_governance→1/170, all else (filled/NULL/orphan_close/shadow_fill/abandoned)→1.0 ✓
- V084 UDF properties: IMMUTABLE + PARALLEL SAFE ✓
- View sample_weight column: double precision NULLABLE, 54 cols, V034 backward compat preserved ✓
- 0 leaked test rows (3 boundary INSERT all ROLLBACKed via SAVEPOINT) ✓
- 5/5 existing V083/V084 objects intact (production not broken) ✓
- Telemetry view live: demo 16.1% / live_demo 22.6% close fills NULL ctx (WARN range, expected) ✓

**Beyond scope observations**:
- V084 view 24h shows 19565 rows label_close_tag IS NULL — confirms W-AUDIT-4b-M3 root cause; V084 view+UDF infra-ready, Rust producer (a01d05ed retract chain) needs further deploy + restart to materialize 'rejected_governance' rows.
- V083 historical close fills 16-23% NULL ctx — V083 NOT VALID correctly protects; cleanup is downstream cron (`edge_label_backfill_cron.sh` M2 step).
- TimescaleDB hypertable: chk constraint reflects 6 times in pg_constraint (1 main + 5 active chunks) — expected internal behavior, NOT a Guard bug.

**Report**: `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--v083_v084_linux_pg_dry_run_verify.md` (299 lines).

**Lessons reinforced**:
1. CLAUDE.md §七 V055 mandate is correct: any V### with PG reflection / CHECK constraint / UDF semantic MUST be empirically Linux PG verified, not Mac mock pytest. Today's V083/V084 dry-run took 12 commands + 6 logs; the equivalent Mac static-parse review would have missed the sqlx checksum drift, the hypertable chunk-multiplication artifact, and the boundary case empirical reject behavior.
2. Idempotent migrations should NOTICE-skip not RAISE — V083/V084 design is correct; first/second apply identical output is the gold standard.
3. CHECK constraint NOT VALID is exactly right for forward-only enforcement when historical has known violations — confirmed empirically with Case 3 reject.

---
## 2026-05-10 — W-AUDIT-4b chain integrity historical replay

**Trigger**: HIGH-5 12h watch metric 1 補強 evidence (Sprint N+0 closure 後)

**Key findings**:
1. fills.entry_context_id → decision_features.context_id chain **真實 100%** (pre+post V083, 0 orphan, n=331 fills_w_entry pre + 10 post)
2. **memory baseline 修正**: decision_features 早 V082 install (2026-05-10 09:22) 之前已大量寫 (從 2026-04-15 起, ma 9.4M / grid 112k)。Sprint N+0 memory 「100% n=199/59/11」是 narrow window 樣本不是新接線
3. V083 是 schema 加 entry_context_id column + check constraint NOT VALID (不對舊 row enforce); writer code 早於 V083 land 部分接線
4. **W-AUDIT-4b M3 reject negative producer 已激活**: post-V082 6361/6394 (99.5%) 標 `label_close_tag='rejected_governance'` + edge=0 集中於 ma_crossover ETHUSDT/INXUSDT + grid ETH/BTC/ZEC
5. 真實 fill+close 只 9 條 (grid_trading, avg edge +40.32 bps 變動 -11.94 ~ +200.37)
6. evaluations 表全 use_legacy_no_predictor + entry_context_id 100% NULL = ML predictor 未接 (W2 baseline 設計範圍, W3 才接)
7. decision_outcomes backfill 100% (backfilled_ts NOT NULL); 24h coverage 78-85% 是 last 7d 內 last 24h 視窗未到

**HIGH-5 metric 1 結論**: chain integrity 結束 watch 提早 sign-off 充足 evidence

**新風險發現**: governance reject rate 99.5% 可能 over-fit 純 negative class — 建議 W-AUDIT-4b M4 reject_rate alert; M5 ML predictor 接通後加 evaluations.entry_context_id healthcheck

**Report**: srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--chain_integrity_historical_replay.md


## 2026-05-10 Governance reject baseline W6 RFC (預跑 raw data)

**Trigger**: W-AUDIT-4b M3 reject negative producer 99.5% reject rate triage；W6 RFC 三角共用 baseline。

**Report**: `workspace/reports/2026-05-10--governance_reject_baseline_w6_rfc.md` (120 行)

**核心發現**:
1. **F1 HIGH (W-AUDIT-4b M3 schema gap)**: reject reason **不入** decision_features schema (Rust intent_processor/mod.rs:1213 source comment 「V017 鎖死，當前作為 audit trail 寫 verdict_writer trace」); 真正 reject reason SoT = `trading.risk_verdicts.{reason, checks_failed, details}` (context_id 1:1 對應 decision_features); learning.governance_audit_log 全是 LG-5 review_live_candidate (post-V082 = 0)
2. **Reject reason 只 2 大類**: cost_gate(JS-demo) negative edge (4079/63.5%, ma_crossover ETHUSDT 3568 + grid ETH/BTC/ZEC ~700) + duplicate_position INXUSDT SHORT 1810 (2331/36.3%); 0 條 scanner_advisory/volatility/DSR/position_size/margin_util reject post-V082 3.5h
3. **F2 MED**: reject rate pre-V082 0% → post-V082 99.55% 是 producer 切上線新行為**非 governance 收緊** (pre-V082 7d baseline 88587 row 全 label_close_tag NULL)
4. **F3 HIGH (severe class imbalance)**: 6415 reject : 10 fill = 642:1; V084 sample_weight 1/170 修正後仍 ~4:1 long-tail; INXUSDT 兩 outlier (+200/+112.91 bps) 占 grid total edge 96%; 真實 10 fill 全 grid_trading (3 symbol: SOLAYER/INX/SAHARA, 1 cell: ZEC); ma_crossover 100% reject 0 fill
5. **時間趨勢**: 11:00 0.23%/12:00 0.10%/13:00 n=18 太少; bb_breakout/bb_reversion/funding_arb 0 fire post-V082
6. **概念修正**: 上次 chain integrity report 暗示「INXUSDT 2331 reject 可能 over-fit」是錯的; 真實是 duplicate_position guard (策略想加倉但被 guard 阻 SHORT 1810)

**輸出邊界**: 純 data dive baseline; 不寫 RFC 結論; 不建議 governance 閾值數值; 12 個 question (PA/QC/MIT 各 4) 留給 W6 RFC

