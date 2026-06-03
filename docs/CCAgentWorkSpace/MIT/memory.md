# MIT Memory

## Memory Usage Contract (2026-05-16)

- 本文件保存歷史教訓與角色偏好，不是 active state、TODO 或 runtime ledger。
- 若舊條目與 `TODO.md`、`README.md`、`CLAUDE.md`、`.codex/MEMORY.md`、`docs/agents/context-loading.md`、代碼或 runtime 證據衝突，信任較新的有證據來源並顯式說明衝突。
- 不要靜默刪除舊條目；只追加可復用的 durable lesson。長報告放 `workspace/reports/`，active 進度放 `TODO.md`。

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


## 2026-05-10 W6 RFC 預跑 MIT 視角 4 questions 自答

**Trigger**: D+1 W6 RFC 三角入場前 MIT 預備立場（PA #2 已答 PA-view，QC 留三角）

**Report**: `workspace/reports/2026-05-10--w6_rfc_mit_questions_self_answer.md` (174 行)

**4 立場 + 對 dispatch v3.2 影響**:
1. **Q1 imbalance 算法** — **hold A 都不適用**：scorer_trainer.py:94-95 是 `objective='regression'/metric='rmse'`，`is_unbalance/scale_pos_weight` 是 LightGBM classification 專用，對 regression silently ignore。MIT Q1 隱含「LightGBM 把 reject 當 negative class」是錯的；V084 sample_weight 1/170 走 `lgb.Dataset(weight=...)` 是「L2 loss 加權」非 class balancing。dispatch W6-5 設計需重整
2. **Q2 V086 prerequisite** — **hold B（反 PA #2 Q3 hold A）**：當前 regression scorer 預測 net PnL，reject row label_net_edge_bps=0 是「中性樣本」，reject_reason 對 task 冗餘；V086 是 future-proof（multi-task 升級才需），不阻塞當前 retrain；建議 acceptance 4-gate 拆 Track A (regression immediate) / Track B (multi-class future)
3. **Q3 multi-class label split** — **hold A 但 3 類遠不夠**：PG 實測 close_tag distribution >100 unique values（risk_close:phys_lock_gate4_giveback 495 / strategy_close:grid_close_short 399 / cost_edge ratio 各種 sub-reason 字串拍平）；正確 schema = 兩 column（reject_reason_code 8 enum + close_reason_code 10+ enum）；W6-3 從 1d extend 3d
4. **Q4 sample rate vs cron** — **depends**：fills 24h=112 / 7d=652 / 全期 5-strat 615 fill；fill rate 93/day actual 比 baseline 70 高；cron 是 daily 03:17 不是 weekly（per project_2026_05_09_ml_training_cron_weekly memory 已修正）；TOTAL pool 已過 1000 baseline；per-strategy MIN_SAMPLES=200 gate 4/5 策略仍不過（grid 374 過，ma 167 / bb_breakout 27 / bb_reversion 4 / funding_arb 43 不過）

**7 dispatch v3.2 update 建議**：
1. W6-1 RFC 加 trainer task type confirm document
2. W6-3 重 scope 1d→3d (close_tag audit + enum spec + V086 兩 column + trainer pipeline read)
3. W6-5 重設計 (不直接套 is_unbalance；先確認 task type；regression case 改 sample_weight ratio sensitivity)
4. W6-7 補 [62] `check_per_strategy_sample_gate()` 同窗
5. §6 acceptance ML retrain 4-gate 拆 Track A / Track B
6. §6 acceptance 補 fills/day rate snapshot 健檢
7. W6-2 acceptance 補 24h dual-write drift healthcheck

**MIT vs PA #2 立場差**：
- Q3 strong agree（要 split）但 MIT 點出範圍 6× larger（18+ class vs PA 3 class）
- Q2 MIT push back（不必等 V086；當前 regression 不需要 reason_code）
- Q4 MIT 修正 PA 隱含「2 週純累積」假設（fill rate 比 baseline 快、cron 是 daily 非 weekly）

**核心**：W6 真正是 ML pipeline architecture 重 design 不是 schema add column 工作。dispatch v3.2 W6-5/W6-3 嚴重低估範圍；硬邊界觸碰 0（all read-only audit + spec change）


## 2026-05-10 W6-3a close_tag distribution audit (D+1 W6-3b PA enum baseline)

**Trigger**: W6 RFC §3 揭露 close_tag >100 unique values；給 D+1 PA W6-3b enum spec baseline 避免重抽 PG data。

**Report**: `workspace/reports/2026-05-10--w6_3a_close_tag_distribution_audit.md` (327 行)

**核心 raw data** (PG live 2026-05-10 14:53 UTC):
1. `learning.decision_features` labeled=9757 (rejected 7528 / closed 2229)；unlabeled=9.51M (pre-W-AUDIT-4b M3 era)
2. `trading.risk_verdicts` 全期 18.5M row；post-V082 (3.5h): Approved=48 / Rejected=7587
3. close_tag 68 unique row → 15 category (strategy_close_grid 689 / fill_strategy_label 615 / risk_close_phys_lock_gate4_giveback 511 + 雙前綴 16 row / strategy_close_ma 315 等)
4. risk_verdicts.reason 12 reason_head 全期；post-V082 收斂到 3 (cost_gate_js_demo_negative_edge 5239 / duplicate_position 2333 / cost_gate_other 15)

**Refined enum spec**:
- **reject_reason_code 12 enum** (PA preliminary 8 → MIT 12)：cost_gate 拆 3 (js_demo_negative_edge / atr_unavailable / other)；補進 5 歷史 reason (direction_conflict 2.77M / position_count 732k / scanner_market_gate 401k / scanner_opportunity_canary 138k / drawdown_breach 91k / symbol_blocklist 35k / risk_gate_other) + catch-all
- **close_reason_code 14 enum** (PA preliminary 10+ → MIT 14)：phys_lock 拆 2 (gate4_giveback 511 / gate4_stale 20)；新增 strategy_close_legacy_bare_name (615 row W-AUDIT-4b M2 早期約定 bare strategy name) + catch-all
- 全 26 enum + 2 catch-all (other_reject + other_close)

**Producer bug 揭露**:
- 16 row `risk_close:risk_close:phys_lock_gate4_giveback` 雙前綴 → Rust producer string concat 漏 prefix-aware；P1 ticket 修
- 615 fill 用 bare strategy name (grid_trading/ma_crossover/...) 不是 bug 是 W-AUDIT-4b M2 早期約定；backfill 收 strategy_close_legacy_bare_name 單一 enum

**5 ambiguous mapping 待 D+1 PA 拍板**:
- A1: legacy bare name 615 row 是否拆 5 sub-enum (per-strategy)？MIT 推薦不拆
- A2: 雙前綴 16 row 是否在 V086 backfill SQL 加 normalize regex (s/^risk_close:risk_close:/risk_close:/)
- A3: cost_gate_atr_unavailable 0 row post-V082 — 保留 enum slot? MIT 推薦保留 (SEC-11 fail-closed signal)
- A4: funding_arb 29 sub-reason 全合 1 enum? MIT 推薦合 (ADR-0018 退役無 future 增量)
- A5: strategy_close_regime_shift 1 row enum 值得保留? MIT 推薦保留 (R-3 hypothesis pipeline 未來可能爆量)

**Backfill cron 設計**:
- 9757 labeled row UPDATE + JOIN 18.5M risk_verdicts (indexed context_id) → 估 30-90 sec single-pass
- **不需 cron**：one-shot UPDATE 直接寫 V086 migration body
- 全 mapping deterministic (regex / exact match)；0 manual review
- producer dual-write 從 V086 land 之刻 enable

**V086 schema spec preview** (D+1 W6-3c E1 IMPL 寫實 SQL):
- ALTER TABLE ADD COLUMN reject_reason_code TEXT + close_reason_code TEXT (additive, NULL allowed pre-backfill)
- one-shot UPDATE backfill 9757 row
- ADD CONSTRAINT chk_*_enum NOT VALID (forward-only, 不破歷史 9.5M unlabeled)
- D+2 14:30 UTC: ALTER VALIDATE CONSTRAINT (lock <30 sec on 9757+ row)
- Guard A/B/C 完整 (column existence / type check / hot-path index 比對)
- 24h dual-write drift healthcheck check_reject_reason_code_dual_write_drift() 必 PASS

**對 dispatch v3.3 §3.0 W6-3b 影響**：
- enum 數量 +8 (reject 8→12, close 10+→14)
- ambiguous mapping 5 項列出 (dispatch 未列)
- backfill 機制改 "cron" → "one-shot UPDATE in V086" (不需 ongoing cron)

**邊界遵守**: read-only audit；不寫 V086 SQL (留 D+1 W6-3c E1 IMPL)；不修 dispatch v3.3 (出 spec 給 PA 拍板)；不寫業務 code


## 2026-05-10 W2 A4-C σ verify (BTCUSDT 1m forward return realized σ 7d)

**Trigger**: PA W2 spec v1.1 §7.1 acceptance prerequisite — pre-run before D+1 sign-off

**Report**: `workspace/reports/2026-05-10--w2_c3_sigma_verify_btcusdt_1m_forward_return.md` (92 行)

**核心 raw data** (PG live 2026-05-10 7d window, n=10050):
1. `market.klines` BTCUSDT 1m: 42628 row / 35d coverage; ts/symbol/timeframe('1m')/OHLC schema
2. **σ_60 = 4.5397 bps** (skew -0.18, ex_kurt 11.76)
3. **σ_120 = 6.2760 bps** (skew -0.01, ex_kurt 7.82)
4. **σ_300 = 10.0838 bps** (skew 0.03, ex_kurt 10.34)
5. **均比 PA spec preliminary σ=30 bps 低 0.15-0.34×**
6. BTCUSDT 7d decision_outcomes n=7, sigma_1m=5.27 bps 對齊 raw σ_60 (一致)

**核心發現 (語意分歧)**:
- **PA spec 30 bps 不對應任何真實層** — 既不是 raw price σ (5-10) 也不是 EDGE-DIAG-1 net edge σ (50-80)
- **dual-layer reframe 建議**: L1 raw σ_300=10 bps baseline / L2 net edge σ ≈ 50-80 bps (EDGE-DIAG-1 historical)

**Power recalc (μ=15 bps paper avg_net, N_fills=80)**:
- Raw σ 視角: t-stat 13-30 (過度樂觀 PASS)
- Net σ=50: t-stat 2.68 / p=0.0044
- Net σ=60: t-stat 2.24 / p=0.0141 (QC W2 review 警告線 σ ≥ 60 bps 命中)
- Net σ=80: t-stat 1.68 / p=0.0487 (邊緣 PASS)
- Net σ=100: t-stat 1.34 / p=0.0918 (FAIL)

**PSR(0) skew/kurt deflation**:
- Raw 視角: PSR(0) ~1.0
- Net σ=80 視角: PSR(0) ~0.94 (接近 0.95 標準下界)
- Excess kurt 7-12 ≫ 0 → JB normality 假設 FAIL → 必用 PSR(0) skew/kurt 修正而非 normal-assumed t-test

**W2 sign-off verdict**: **CONDITIONAL PASS**
1. Raw σ verify PASS (實測交付)
2. PA W2 spec v1.1 §7.1 必修 (dual-layer language)
3. Power 不需重算 dispatch (raw t-stat>>2 充分；spec 文檔需註明)
4. PSR(0) net σ deflate 至接近下界
5. 不需 D+1 MIT C-3 重跑 (本次完整交付)

**邊界**: read-only audit; 不修 PA W2 spec v1.1; 不修 dispatch v3.6; 不寫業務 code


## 2026-05-10 W6-1 RFC final verdict — MIT sign-off APPROVE-CONDITIONAL

**Trigger**: PA + QC + MIT 三角 sign-off draft cold review；W6 V086 IMPL 完成，Phase 2 dispatch fire 啟動

**Report**: `workspace/reports/2026-05-10--w6_1_rfc_mit_signoff_verdict.md` (307 行)

**Verdict**: **APPROVE-CONDITIONAL** (5 必修條件 + 2 SHOULD)

**4 Verdict 對應 MIT 立場**:
1. cost_gate hard rule 維持 → APPROVE (db-schema audit 三層設計結構正確 + 16 root principles)
2. JS shrinkage 強收縮設計預期 → APPROVE (Lehmann & Casella Ch.5 textbook signature)
3. cost_gate 放行期望 -14 bps → APPROVE (JS estimate = unbiased point estimate)
4. scorer_trainer regression task confirm + W6-5 撤回 → APPROVE FULLY (W6-5 撤回是 MIT 自己揭露的 category error 修正)

**5 必修條件 (MUST)**:
1. V086 SQL §2 spec 註解修正「lossless deterministic re-UPDATE」(D+2 14:30 UTC ALTER VALIDATE 之前)
2. V086 SQL 補互斥不變式 schema-level CHECK (NOT VALID) 防 future producer bug
3. W6-5 試行 acceptance 補 5 ML pipeline metrics (per-fold RMSE+95%CI / IS-OOS gap / cross-fold std/mean / PSI+KS / cost_gate decision distribution shift) + purge+embargo CV
4. CLAUDE.md §七 idempotency wording 修正「lossless on repeated apply」(不要求 0 row UPDATE)
5. MIT memory chain integrity replay 100% 結論補註 + 樣本擴大後 ratio 40% RCA 入 N+2

**2 SHOULD**:
6. Track B prerequisite (b) 改「核心 5 策略中 ≥3 策略各 class sample ≥ 200」+ funding_arb 排除
7. 新 healthcheck `check_chain_integrity_post_audit_4b_m3()` 入 W-AUDIT-4b 24h passive

**核心 empirical findings (ssh trade-core PG live 20:35 UTC)**:
- total_labeled = 51113, reject_with_code = 17810 (✅ backfill PASS pre-22:00), close_with_code = 2247
- **reject_NULL_code = 31053** (🚨 22:00+1h producer 寫 36352 reject 但 backfill 只 cover 5299 → producer dual-write code 未 deploy)
- overlap_both = 0 (✅ 互斥不變式 PASS)
- close_NULL_code = 3 (邊角 case)
- **chain integrity 60% orphan**: fills_w_entry_ctx=5939, fills_in_df=2369, **orphan=3570 (60%)**；對比前次 100% (n=331) 是窄窗 artifact，全表 ratio = **40%**
- pre-5/10 reject = 0 (W-AUDIT-4b M3 producer 5/10 才接通)；no time bias
- _sqlx_migrations max=84 (V086 NOT registered, E1 SKIPPED 等 PM `repair_migration_checksum`)
- double_prefix_remain = 0 (V086 17 row UPDATE PASS)

**V086 OR-filter 缺陷 governance 推薦**: 方案 A (accept + spec annotation fix)，工程成本最低，PG empirical lossless idempotent

**W6-5 sample_weight 替代 ML pipeline sound check**:
- algorithm 正確 (LightGBM regression L2 weighted standard WLS)
- 但 100× safety margin engineering choice 沒統計依據；建議 1/15 lower bound
- evaluation metric 缺 OOS purged k-fold；MUST 補

**W6-3 兩 column TEXT vs alternatives**:
- APPROVE 兩 column TEXT (12 + 14 enum) — semantic separation + NOT VALID 不破歷史 + Track B 直讀 enum
- REJECT single column / FK enum table / PG ENUM type / jsonb (理由列出)
- Push back: overlap=0 互斥不變式缺 schema-level CHECK constraint，建議補 NOT VALID CHECK

**Track B N+2/N+3 deferred sound** (REJECT N+1 fast-track):
- (a) producer dual-write 24h 0 NULL drift: 22:00 UTC 31053 NULL 證明 producer 未 deploy
- (b) per-class 200 sample: 4/5 策略不過 → fast-track 等於 grid-only 過擬合風險
- (c) classification trainer architecture: ≥1 sprint hierarchical / multi-task spec
- (d) imbalance handling: regression 不需，classification 才適用

**Confidence**: 全 11 项 verdict + push back HIGH 以上 (8 HIGH + 1 HIGHEST + 2 MED)



## 2026-05-11 LG-3 spec v1 MIT review (Wave 2.1.5)

**Trigger**: PA LG-3 Supervised-Live State Machine spec v1 (`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v1.md`) 完成；MIT + QC + BB 並行 review。

**Report**: `workspace/reports/2026-05-11--lg3_spec_mit_review.md` (405 行)

**Verdict**: **APPROVE WITH 6 MUST + 3 SHOULD** (接近 unconditional APPROVE；0 redesign)

**核心發現**:
1. **Schema design PASS**：V094 supervised_live_audit hypertable + PK + 4 index + append-only design 對齊既有 V054 lease_transitions / V064 decision_state_changes / V035 governance_audit_log 三條 audit precedent；無新 schema pattern 引入
2. **ML data integrity VERY LOW risk**：sub-agent grep `learning.supervised_live_audit` 確認 0 Python/Rust reader 路徑 in ml/training/learning；spec §9.3 + §15.1 原則 7 明文「supervised_live_audit 不直接餵 ML pipeline」；6 維 leakage (look-ahead/target/survivorship/cross-section/time-zone/resample) 全不適用 (audit table 不在 ML pipeline)
3. **5 SoT outbox 設計 PASS**：mirror lease_transition_writer.rs 既有 pattern (bridge thread / batch / fail-soft retry / fail-closed at buffer overflow)；SoT 真值權威 = #5 supervised_live_audit；連 2 cycle 防 false-positive
4. **ML pipeline maturity categorical mismatch**：LG-3 audit 是 governance audit foundation table (與 W-AUDIT-9 governance.canary_stage_log 同類)，**不適用** ML pipeline 5 階段 Foundation/Skeleton/Shadow/Canary/Production 評級框架
5. **W-AUDIT-4b conflict = 0**：disjoint domain，可同期並行 IMPL

**6 MUST 全為 spec v2 編輯級工作 (~1-2h PA edit)**:
- MUST-1: §4.1 Guard A part 2 加 19-column allowlist check (mirror V054 §155-188)
- MUST-2: §4.1 ADD CONSTRAINT IF NOT EXISTS block 4 條 (action/result/engine_mode/ts_ms>0; mirror V054 §245-317)
- MUST-3: §13.4 Linux PG dry-run dispatch SOP (對齊 V055+V083+V084 precedent)
- MUST-4: §4.1 sqlx checksum SOP 注釋 (對齊 V028-V034 教訓)
- MUST-5: §4.1 Non-training surface invariant 注釋 + E3 grep rule (對齊 replay.simulated_fills synthetic_replay 防護 SOP)
- MUST-6: §2.2 inverse map 完整表 (17 action × 7 state, 防 Rust/Python SM mirror split-brain)

**3 SHOULD**:
- SHOULD-1: `[59]` healthcheck 補 KS test baseline (per data-drift-detection skill)
- SHOULD-2: schema +1 NULLable `strategy_alpha_score FLOAT(8)` (R-4 forward-compat)
- SHOULD-3: schema +1 NULLable `regime_tag TEXT` (R-2 配套)

**邊界遵守**: read-only spec review；不寫 V094 SQL；不修 PA spec v1；不啟 E1；不發 commit；不改 TODO/CLAUDE.md (硬約束 100% 遵守)


## 2026-05-16 W-AUDIT-8a C1 v2 schema delta pre-review

**Report**: `workspace/reports/2026-05-16--w_audit_8a_c1_v2_harness_mit_schema_pre_review.md` (445 行)

**Verdict**: **APPROVE FULLY — V09X NOT NEEDED** for v2 24h proof; current `market.liquidations` 5-column schema (ts/symbol/side/qty/price) 1:1 align Bybit V5 `allLiquidation.{symbol}.data[]` (T/s/S/v/p)

**核心 empirical findings** (ssh trade-core PG `2026-05-16T08:50Z` + v1 final JSON):
1. `market.liquidations` = 5 col, PK (symbol, ts, side), hypertable 1d chunk / 7d compress / 90d retention, **0 row** (handler removed 2026-04-06)
2. v1 5h window: topic_message_counts=15 frames, candidate_samples=5 (cap; not 15), 100% snapshot type, 100% Buy side, BTC realistic 78600 price range
3. Bybit `S` "Buy"/"Sell" semantic = short-liq/long-liq direction (Buy = short got forced-bought)
4. Rust `LiquidationSide` enum (LongLiquidated/ShortLiquidated/Mixed) translation 在 **parser 層**，schema 不需動
5. PK collision under sub-ms burst = Phase C writer **方案 A** `ON CONFLICT DO NOTHING` (no schema change)
6. ML maturity stage: **Foundation only** (Skeleton 因 2026-04-06 writer removal 倒退); Phase C revival path Foundation→Skeleton→Shadow→Canary→Production

**5 push back (none block v2 proof start)**:
- HIGH-1: V002 chunk_interval source `INTERVAL '7 days'` vs runtime `1 day` drift (commit lag)
- MED-1: `side TEXT` 無 CHECK constraint; Phase C V09X 可選加 `IN ('Buy','Sell') NOT VALID`
- MED-2: PK collision under burst → Phase C writer `ON CONFLICT DO NOTHING` 方案 A
- LOW-1: REAL precision for long-tail meme coin（BTC OK at 2dp price）
- LOW-2: V002 comment `1 year retention` vs V006 actual `90 days` doc drift

**Sign-off boundary**: MIT signs schema layer only; NOT ToS (BB scope), NOT production builder revival (PA + operator post-v2-PASS), NOT V09X (none needed)


## 2026-05-18 W-AUDIT-8c S0R-1 + S0R-2 dual review

**Trigger**: PA W-AUDIT-8c Stage 0R tooling readiness; MIT dual review (1) SQL Linux PG empirical dry-run x2, (2) `_n_eff_cluster_aware` formula + 19 PASS criteria statistical correctness.

**Report**: `workspace/reports/2026-05-18--w_audit_8c_s0r_1_2_mit_dual_review.md`

**Verdicts**:
- **S0R-1 SQL**: APPROVE-CONDITIONAL — Linux PG x2 dry-run PASS (8ms + 6ms idempotent); schema 1:1 match (V095 5-col PK validated); 3 SHOULD-FIX non-blocking + 1 MUST-LAND E1 self-report
- **S0R-2 metrics**: APPROVE-CONDITIONAL — 3-ceiling `min()` formula = Bonferroni-style intersection bound defensible; 15/19 APPROVE + 3 DRIFT WARN + 1 ACCEPT-DEFER; **1 MUST-FIX**: `_n_eff_horizon_overlap` integer-floor → math.ceil (dormant bug at horizon=6/10/14 sweep expansion)

**Linux PG empirical findings** (ssh trade-core docker exec, 5 queries):
1. market.liquidations 8574 row / 0.63d / 33 syms (forward-only accumulating since 8a revival 2026-05-17)
2. market.klines 7d 1m bars 315k rows / 58 syms (sufficient for LATERAL lookups)
3. Density floor efficacy K=3/N=10k/M=2 → 84.6% rejection (PASS ≥ 60% floor)
4. Trigger distribution: 95 long_liq buckets (1 day, 31 syms) + 27 short_liq buckets (2 days, 11 syms) — **single-day collapse risk visible at current sparsity**
5. n_clusters_60m: 56 (long), 20 (short) — bucket/cluster ratio 1.35-1.7 = 60min window absorbs ~half autocorr

**Math defensibility**:
- `min(n_eff_horizon, distinct_days, distinct_60min_clusters)` 是統計合理 conjoint independence ceiling（不用 weighted/geometric — 那會 overstate）
- 60min default 在當前 sparsity 是合理 heuristic；revisit if empirical lag-1 autocorr 測過
- Bias direction = correctly CONSERVATIVE (over-penalize); 8b INJUSDT z=1.2 case n=42→n_eff=7 三方一致 OK
- 對 8b naive 公式比較：當前 8c long_liq 95→1 (98.9% penalty) 反映 single-day collapse 真實；naive 公式會 falsely PASS

**Critical drift WARN** (E1 reconsider before E2 sign-off):
- #8 `MAX_SYMBOL_SHARE` 0.40 → MIT push back 0.30 (PA 30% stricter，8b INJUSDT 87% 教訓)
- #19 `COST_EDGE_RATIO_MAX` 0.80 → MIT push back 0.60 (PA 0.50 ↔ 0.80 妥協 0.60)
- #16 `FALSE_POSITIVE_RATE_MAX` 0.40 → 收緊 0.30 (first PASS cell 後)

**Bear-regime replication crisis warning**:
- 2026-05-11~05-18 = bear regime (per 8b MIT §3.5)
- 8c long_liq dominated (bear-regime coherent); short_liq sparse (rare in bear)
- Stage 0R 7d PASS verdict 是 **necessary but not sufficient** for AlphaSurface Tier-2 production wire
- **MUST-FIX governance**: Stage 0R verdict JSON 必含 regime annotation + 30d cross-regime sample for live promotion

**ML pipeline stage**:
- market.liquidations: **Shadow** (writer revived 8a Phase B 2026-05-17, 0.63d accumulating, no live decision)
- 8c metrics module: **Shadow** (Stage 0R replay only)
- AlphaSurface LiquidationCluster Tier 2: **Skeleton** (trait phase A, no production wire)
- Cron `stage0r_w_audit_8c_*`: **Foundation** (not installed)

**Time-series CV applicability**: Stage 0R 是 single-cell evaluation 不用 walk-forward；Stage 1 promotion 必 IMPL walk-forward + 60min embargo（cluster window 自然 embargo）+ day-block fold boundary

**6 leakage 維度**: 0/6 命中 ✅ leak-free (cross-section partition by symbol-time-series window 不是 cross-sectional 同期，semantic 正確)

**16 root principles**: 16/16 compliant；無 commit / push / TODO mutation / cron install / auth touch / runtime config change

**Sign-off boundary**: MIT signs SQL + math layer only; NOT spec v0.3 redesign (PA scope), NOT cron install (operator post-PASS), NOT AlphaSurface production wire (Sprint N+post-Stage 0R PASS)

**Cross-skill consulted**: ml-pipeline-maturity-audit + feature-engineering-protocol + time-series-cv-protocol + data-drift-detection + db-schema-design-financial-time-series

## 2026-05-18 — W-AUDIT-8c S0R-1+2 round 2 dual review

**Scope**: E1 round-2 rework verification for SQL split + Python metrics retrofit.

**S0R-1 SQL (3 split files, origin/feature/w-audit-8c-s0r-1-sql-query-template @ 381d89a0)**:
- 3 files independent; zero @SIBLING markers (HIGH-1 fixed)
- Linux PG round 1+2 dry-run x2 PASS idempotent (5/3/5 ms exec, identical plans)
- 7d × 32-sym extrapolation: features ~55ms, panel ~30ms, cluster_n_eff ~50ms (all under acceptance)
- CRIT-2 sibling notional_pct_floor consistency: byte-equivalent n_eff sample base (main triggers = sibling n_clusters_60m = 10 across 9 syms)
- PA verdict D verified: LATERAL `(ts, open)` narrowed; entry_mid/exit_mid open-only with field name preserved
- 6-CTE chain: raw_buckets → density_gated → trigger_with_pct → trigger_candidates → forward_returns → final_signals
- CTE 3a/3b split structurally required (percent_rank window function can't filter in WHERE)
- MIT SHOULD-2 + SHOULD-3 doc fixes landed; SHOULD-1 (pg_typeof) deferred to Python caller — acceptable
- 6/6 leakage types clean (no look-ahead via PRECEDING+CURRENT only; no resample boundary via PA verdict D open-only)
- **Verdict: APPROVE unconditional**

**S0R-2 Python metrics (1814 LOC, origin/worktree-agent-af73a5d4575815f26 @ 6cc2b7fb)**:
- MIT MUST-FIX `math.ceil` landed: `int(n / max(1, math.ceil(horizon_min / 5)))`; empirical retest horizon=6→5 (was BUG 10), horizon=14→3 (was BUG 5), canonical 1/5/15 unchanged
- 8b INJUSDT z=1.2 retest: n_eff_cluster=7 unchanged (penalty_rate 83.3%)
- CRIT-3 cluster sliding pattern verified: 10 events @30min apart with 60min window → 1 cluster (round 1 anchor pattern would give 4); `last_ts_ms = ts_ms` always advances byte-equiv with SQL `lag(bucket_end_ts) > 60min`
- 3 drift push-backs all applied: MAX_SYMBOL_SHARE 0.40→0.30 / COST_EDGE_RATIO_MAX 0.80→0.60 / FALSE_POSITIVE_RATE_MAX 0.40→0.30
- CRIT-2 fail-closed: `total_bucket_count=None` returns `passed=None` + explicit fail_reason "missing_bucket_count_denominator" (defensible alternative to ValueError)
- K_total 8-D sweep math: 4×4×3×3×3×3×3×3 = 11,664 verified (task brief 3^8=6561 assumption incorrect; K_GRID + N_USD_GRID are 4-tuples)
- regime_annotation injected in all 4 verdict paths (lines 1211/1527/1649/1768)
- **1 SHOULD-FIX (non-blocking)**: hardcoded `2026-05-11..05-18` sample period should be parameterized before AlphaSurface Tier-2 production wire (acceptable for fixed Stage 0R replay-packet)
- **Verdict: APPROVE-CONDITIONAL** (1 non-blocking SHOULD-FIX noted)

**Ready for E4 regression**: YES both scopes; no blockers.

**Linux PG verification toolchain used**: 
- `ssh trade-core 'python3 -c "psycopg2..."'` with comment stripping to dodge `%(name)s` in comments + Chinese `%` literals
- DB credential `host=127.0.0.1 dbname=trading_ai user=trading_admin` (POSTGRES_PASSWORD from container env)
- Empirical density floor: 384 raw → 94 density_gated → 10 final (75.5% / 97.4% rejection rate; well above 60% floor)
- Current panel 0.66d 8771 rows 33 sym (still accumulating to 7d acceptance threshold)

**Cross-skill consultation**:
- ml-pipeline-maturity-audit: 8c maturity = Shadow only (correct; Stage 0R replay-packet)
- feature-engineering-protocol: 6/6 leakage clean; PA verdict D open-only specifically resolves potential resample boundary
- time-series-cv-protocol: Stage 1 walk-forward CV with 60min cluster embargo deferred (non-blocking Stage 0R)
- data-drift-detection: bear-regime annotation as governance lever; 30d cross-regime required pre-live

**Report**: `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-18--w_audit_8c_s0r_1_2_mit_dual_review_round2.md` (31KB / ~550 LOC)

## 2026-05-22 V099 Autonomy Level Toggle schema spec

**Spec**: `srv/docs/execution_plan/specs/2026-05-22--v099-autonomy-level-config.md` (429 行)

**Source**: PA design spec `2026-05-22--autonomy_level_toggle_design_spec.md` §3 + AMD-2026-05-21-01 v2 §3.5。

**V### decision**: V099。Linux PG `_sqlx_migrations` max=96 ssh trade-core empirical verified；local staged unapplied = {97, 98, 106, 107, 112}；V99 free + 連續未占用。

**新 schema**: `system`（Linux PG `information_schema.schemata` verified 不存在；migration `CREATE SCHEMA IF NOT EXISTS system` 新建）。

**兩 表 design**:
- `system.autonomy_level_config` single-row PRIMARY KEY id=1 CHECK + cold start seed CONSERVATIVE default
- `system.autonomy_level_switch_audit` append-only history bigserial PK + REVOKE UPDATE/DELETE on PUBLIC + trading_ai + 三路通知 status column + emergency_override + 2FA verify result

**Schema 設計差異於 PA spec**: PA spec §3.2 寫 `current_level smallint CHECK (1, 2)`；MIT spec 改 `text CHECK ('CONSERVATIVE', 'STANDARD')` 對齊 AMD v2 §3.3 字串 enum 命名 first-class（Q1 unresolved；待 operator 拍板字面對齊 smallint vs text）。

**Guard A/B/C 完整**: Guard A 雙表 column missing array verify；Guard B current_level type=text verify；Guard C idx_autonomy_audit_switched_at column ordering DESC verify。Idempotency `CREATE SCHEMA / TABLE IF NOT EXISTS + ON CONFLICT DO NOTHING + DO NOTICE skip`。

**Linux PG dry-run 6 條** (per ADR-0011 + feedback_v_migration_pg_dry_run，每條 ssh trade-core 一行 抗貼上 one-liner):
- D1 _sqlx_migrations 版本對齊（V96 baseline + V99 absent）
- D2 第一次 apply + reflection 驗 column type / nullability / default
- D3 二次 apply NOTICE skip 不 RAISE（idempotency）
- D4 INSERT default → SELECT 反讀對齊（id=1, CONSERVATIVE）
- **D5 CHECK constraint 強制驗（最高風險）**：UPDATE current_level='INVALID' 必 reject（spec/IMPL 字面 mismatch 會 silently drift；Mac mock pytest 無法 catch）
- **D6 REVOKE + Index 雙驗（最高風險）**：trading_ai DELETE audit 必 permission denied + EXPLAIN ANALYZE show Index Scan idx_autonomy_audit_switched_at

**Pre-deploy SOP (P0 sqlx hash drift 防線)**:
- 禁本地 `psql -f`（避免 hash drift incident per project_2026_05_02_p0_sqlx_hash_drift）
- 必 commit + push → Linux engine restart `OPENCLAW_AUTO_MIGRATE=1` 觸發 sqlx 第一次 apply
- 後續任何 edit 必走 `bin/repair_migration_checksum`

**Rollback strategy**: additive schema（純 CREATE）；apply 後立即發現 bug → DROP TABLE/SCHEMA CASCADE + 刪 sqlx_migrations row + 重 land；apply 後 production row 已寫入 → 不 rollback，走 ADR-0006 forward V### patch + 資料訂正。5-gate live mainnet 期間永不 destructive rollback。

**ML / data drift implication**:
- Level 切換 = governance posture change，**不觸發** ML re-training reset（feature distribution 不變 / cost_gate 不繞 / engine_mode filter 不變 / sample weight 不繞）
- 例外：Level 2 切換後 strategy promotion rate 顯著上升 → LAL 3 immature strategy 樣本進 training set → PSI drift 監控建議
- M3 health monitor **應**接 Level switch 觀察：新增 `check_autonomy_level_switch_recent_24h()`（24h ≥ 2 切換 CRITICAL；emergency_override=true WARNING）

**Q1/Q2 unresolved for operator**:
- Q1: enum string 'CONSERVATIVE'/'STANDARD' vs smallint 1/2 — MIT 推薦 text，待 operator 拍板
- Q2: schema 命名 `system` vs 進既有 `governance` — MIT 推薦 system 對齊 PA spec，待拍板

**MIT sign-off**: spec DRAFTED；E1 IMPL + E4 Linux PG dry-run 6 條 + E2 review 後 sign-off

## 2026-05-25 W1-B M4 Pattern Miner Stage 1 Algorithm Spec (Sprint 2 Wave 1)

**Trigger**: Sprint 2 Day 0 dispatch packet §3 Stream B W1-B 任務 — 給 W1-C E1 IMPL 寫 algorithm-level dispatch packet

**Spec**: `srv/docs/execution_plan/2026-05-25--m4_pattern_miner_stage_1_algorithm_spec.md` (907 行)

**核心交付**:
1. **5 source ingestion**: market.klines (1m-4h × 25 symbol × 90d ~4M row) / trading.fills (engine_mode IN ('live','live_demo') ~65k row) / market.liquidations (含 self-fill 過濾) / market.funding_rates / token unlocks (Sprint 3+ stub)
2. **5 sub-algorithm IMPL**: Pearson + Spearman rolling cross-corr (statistical) + funding flip + liquidation cascade + large funding spike (event-window)
3. **5 hard invariant** (E2 cold review): shift(1) leak-free 強制 / HMM-Markov-GARCH 黑名單 / Bonferroni K_total=2500 α=2e-5 / N≥30 event gate / DRAFT≠live per 16#7
4. **V103 EXTEND 6 attribute writeback contract**: hypothesis_source_module='M4_AUTO' + leakage_scan_pass + bonferroni_corrected_p + replicability_score (0.3 subperiod + 0.4 cross-asset + 0.3 cross-timeframe) + decision_lease_draft_id + cowork_review_status='NONE'
5. **Rust + Python hybrid placement**: `rust/openclaw_core/src/m4_miner/` (polars + sqlx + rayon hot path) + `helper_scripts/m4/` (scipy/statsmodels orchestration + DRAFT writeback + Decision Lease)
6. **5 AC (AC-S2-B-1..5)**: 4 source freshness + 5 sub-algo IMPL DONE + leak-free regression test + 30 event gate + V103 6 attribute non-NULL
7. **5 對抗式 review grep**: shift(1) presence / Bonferroni K hard-coded / HMM-GARCH 黑名單 / engine_mode IN ('live','live_demo') / Decision Lease backref

**ML Pipeline Maturity rating**:
- 當前 Stage = **Foundation** (V100 base + V103 EXTEND land,writer 待 W1-C IMPL)
- 升 Skeleton (Sprint 2 末): W1-C IMPL DONE + dry-run pass + cron disabled
- 升 Shadow (Sprint 3): cron daily 啟動 + DRAFT row 累積但 promote 仍 operator review

**Open Q 待 W1-C IMPL 期間定**:
- Q1: K_hyp=500 empirical adjustment (第一週後 PA+MIT+QC 仲裁)
- Q2: Cross-asset feature Sprint 2 vs Sprint 3 ship cadence
- Q3: Cron freq (daily UTC 00:00 recommended baseline)
- Q4: 90d 50/50 split 對 event-based hypothesis 不適用 (跳過 subperiod check)
- Q5: Cross-language 1e-4 fixture 在 E4 regression 階段 (IMPL DONE 後) 跑

**邊界遵守**:
- Read-only audit + algorithm spec; 不寫 IMPL code (W1-C scope)
- 不修 V103 SQL (已 land); 不修 design spec 主檔 (引用)
- 不寫 ADR-0036 主檔 (PA Sprint 1A-γ dispatch);本 spec §2.3 grep invariant 即生效
- 不依賴 LinUCB / scorer / quantile / mlde (M4 是 statistical miner 不是 ML model retrain)

**Commit**: `7eab15e0` (main, [skip ci]) — pushed to origin

**W1-C E1 IMPL dispatch verdict**: **READY** — 3 自查項 (4 source freshness / GovernanceHub `M4_DRAFT_WRITEBACK` lease type 支援 / cross-lang fixture infra) 為 W1-C IMPL 內自查 + IMPL DONE 後 regression,不阻 W1-C 開工


## 2026-05-25 W1-D M10 Tier A productionize backend spec(Sprint 2 Wave 1)

**Spec**:`srv/docs/execution_plan/2026-05-25--m10_tier_a_productionize_backend_spec.md`(519 行)

**Trigger**:Sprint 2 Wave 1 W1-D sub-agent track per dispatch packet §1.2;PM #2 decision 拍 (a) V111 spec @ Sprint 1A-γ 先,Stream C Wave 1 後端不阻。

**Status**:MIT spec DRAFTED;W2-C E1 IMPL chain 接 Wave 2;依賴 Sprint 1A-γ V111 spec FINAL 才能完整接線 governance.discovery_tier_activations。

**核心設計**:
1. **V111 dependency 解耦**:Wave 1 sentinel JSON file `/tmp/openclaw/m10_tier_a_proposals/{strategy}_{symbol}_{regime}.json` writeback;Wave 2 W2-C V111 land 後接線 governance.discovery_tier_activations INSERT(dual-write with V004 ml_parameter_suggestions)
2. **Cron cadence**:weekly Sun 05:30 UTC(`30 5 * * 0`)— 不撞 ml_training_maintenance daily 17:03;Tier A Optuna trial 較重(n_trials=30 × 7 策略 × 25 symbol × 3 regime = 15,750 trial)適合 weekly
3. **7 策略 scope**:5 textbook(grid_trading/ma_crossover/bb_breakout/bb_reversion/funding_arb)+ Sprint 2 W2-B IMPL 2 新 candidate(funding_short_v2 + liquidation_cascade_fade per PM #1 decision Stream A)
4. **Walk-forward 設計**:purge_days=2 + ≥ 6 historical sub-period × ≥ 30 fills per sub-period(per CR-6 + Lopez de Prado AFML Ch.7);per-strategy embargo 走既有 quantile_trainer.get_embargo_config()(funding_arb 72h carve-out;其餘 24h)
5. **既有 IMPL reuse**:不改 optuna_optimizer.py / edge_estimate_validation.py / quantile_trainer.py / ml_training_maintenance_cron.sh;Tier A productionize 是新 surface 不污染既有 trainer scope
6. **ADR-0036 黑名單 enforce**:Tier A only Optuna TPE + Walk-Forward Rolling;HMM / Markov-switching / GARCH 任何形式永久禁用;sub-agent dispatch 三方雙 round grep gate(W1-D + W2-C 前 + IMPL DONE 後)

**Empirical findings(MIT ssh trade-core Linux PG)**:
1. `_sqlx_migrations` max=112(Linux PG main trading_ai container)— V111 unapplied(V111.sql 不存在;V112 已 land)
2. `to_regclass(\$\$learning.discovery_tier_config\$\$)` = NULL — V111 PA spec FULL-V0 改 schema 至 `governance` schema(不是 learning),per V111 spec `2026-05-21--v111_m10_discovery_tier_config_schema_spec.md` §1.1 placeholder v0 廢棄
3. 既有 Optuna IMPL(optuna_optimizer.py)用 TPE + JournalFileStorage(per E5-O4 audit 非 PG),proposal 寫入 V004 ml_parameter_suggestions
4. 既有 walk-forward IMPL(edge_estimate_validation._walk_forward_oos_values)已含 purge gap(default 0;Sprint 2 W1-D spec 改 purge_days=2)
5. quantile_trainer.get_embargo_config():funding_arb 72h embargo(3-fold + 14d holdout);其餘 24h embargo(5-fold + 7d holdout)

**10 AC for Stream C(Sprint 2 dispatch packet §4.3 5 條 + MIT 補 5 條 = 10)**:
- AC-S2-C-1: Optuna walk-forward cron skeleton IMPL DONE(Wave 1 W1-D)
- AC-S2-C-2: 7 策略 weekly run pass empirical(Sprint 2 14d 內 1-2 次 fire = 6/1 + 6/8)
- AC-S2-C-3: V111 schema 接線(Wave 2 W2-C,依賴 1A-γ V111 spec FINAL)
- AC-S2-C-4: capital tier $10k → Tier A only confirmed(本 spec §2.4 鎖 OPENCLAW_M10_TIER_LEVEL=A)
- AC-S2-C-5: capital-tier hook 留 Tier B-E(per v5.8 §2 M10 + ADR-0036)
- **AC-S2-C-6(MIT 補)**: Tier A proposal 不直接觸 trading(per 16 原則 #7 學習 ≠ live;走 V004 + governance.activations + 不繞 Decision Lease)
- **AC-S2-C-7(MIT 補)**: Walk-forward look-ahead bias 防護(purge gap 2d + per-strategy embargo + 6 leakage 維度 leak-free check;sentinel JSON `leakage_checks.shift1_applied=true` 必對)
- **AC-S2-C-8(MIT 補)**: ADR-0036 黑名單 grep gate enforce(W2-E E2 review verify)
- **AC-S2-C-9(MIT 補)**: 5 textbook 不破 demo runtime(E4 Mac cargo test --workspace --release + pytest 5 策略 demo regression)
- AC-S2-C-10(MIT 補): Optuna study journal storage 30d 自動 prune(P1 carry-forward 非 blocker)

**W2-C E1 IMPL dispatch readiness**:條件性 — 依賴 Sprint 1A-γ V111 spec FINAL(operator + MIT C9 Linux PG dry-run sign-off pending)+ V111.sql land(W2-C IMPL chain 內)+ Linux PG dry-run x 2 round(per ADR-0011 V055 5-round loop precedent)。Wave 1 Optuna walk-forward backend cron skeleton 可獨立 IMPL 不阻塞 V111。

**邊界遵守(M-4 hygiene SOP per docs/agents/sub-agent-hygiene-sop.md + Sprint 2 dispatch packet §10)**:
- ✅ read-only ssh probe(Linux PG `_sqlx_migrations` max + V111 table state)
- ✅ 不跑 cargo build/test/check --release(0 cargo invocation)
- ✅ 不寫 PG / 不 sudo / 不 restart 服務
- ✅ 不 install cron(operator scope)
- ✅ 不寫 helper_scripts/m10/*.py 實 code(W2-C E1 IMPL 接手)
- ✅ 不改 既有 IMPL(optuna_optimizer.py / edge_estimate_validation.py / quantile_trainer.py / ml_training_maintenance.py)
- ✅ Mac dev-only;ssh probe 2 query 完結

**Cross-skill consulted**:
- time-series-cv-protocol(Purge / Embargo / Rolling vs Anchored)— Walk-Forward Rolling 採用(crypto regime 切換)
- feature-engineering-protocol(6 leakage 維度 + shift(1) compliance)— sentinel JSON leakage_checks 必對
- ml-pipeline-maturity-audit(Foundation/Skeleton/Shadow/Canary/Production)— Tier A productionize Stage = Skeleton(writer cron 在,V111 接線 Wave 2 後到 Shadow)
- math-model-audit(HMM/GARCH/VPIN 黑名單 source of truth)— ADR-0036 governance promotion mirror
- walk-forward-validation-protocol(QC alpha 顯著性協議)— PSR + DSR + Bonferroni 入 sentinel JSON


## 2026-05-27 V104 supervised_live_audit Linux PG empirical dry-run (LG-3 Wave 2.4.A gate 2)

**Report**: `workspace/reports/2026-05-27--v104_supervised_live_audit_dry_run.md` (132 行)

**Verdict**: **9/9 PASS + 2 bonus PASS → LG-3 Wave 2.4.A E1 IMPL dispatch UNBLOCKED ✅**

**Trade-core PG snapshot (BEGIN/ROLLBACK transaction-safe)**:
- `_sqlx_migrations` max=112 / count=102 (V99-V103 all success=t; V104 hole FREE confirmed; V105-V112 already land 後續 spec)
- V35 governance_audit_log + V54 lease_transitions prereq met (Guard A part 1 PASS)
- learning.supervised_live_audit baseline 0 row clean
- Round 1+2 全在 BEGIN/ROLLBACK 內，0 leaked row、0 sqlx_migrations 異動

**9-Query empirical 結果**:
1. Q1 sqlx baseline → max=112 / count=102 ✓
2. Q2 CREATE+Guard A part 1 → 0 RAISE / hypertable_id=88 ✓
3. Q3 idempotency 2nd apply → `relation ... already exists, skipping` NOTICE ✓
4. Q4a 21 col allowlist → col_count=21 / ordinal 1..21 / type 全對 (TEXT[]/JSONB/FLOAT8/TIMESTAMPTZ) ✓
5. Q4b 4 CHECK constraint → conname × 4 全在 ✓
6. Q4c hypertable → num_dimensions=1 / chunk_days=7 ✓
7. Q4d 2 policy job → 1050 compression 30d + 1051 retention 90d ✓
8. Q4e 4 named idx + PK + auto created_at idx = 6 indexname ✓
9. Q4f action CHECK 17 enum 完整 (request_registered/approval_granted/approval_rejected/expired_pre_auth/auth_file_observed/auth_file_invalid/lease_acquired/lease_released/auth_recheck_fail/drawdown_breach/drawdown_close_complete/kill_api/kill_ipc/session_max_duration/reconcile_force_close/illegal_transition_attempted/session_closed) ✓

**Bonus verify**:
- Guard A part 3 forbidden column (ml_label/training_label/feature_vector/signal_id) 0 hit → non-training surface invariant 達成
- 4 boundary INSERT (bad action / bad result / paper engine_mode / ts_ms=0) 全 check_violation rejected
- 1 valid INSERT (engine_mode=live_demo, action=request_registered, result=ok) 成功

**1 push back (非阻 IMPL)**:
- `OPENCLAW_PG_URL_DRYRUN` 在 trade-core unset；spec §4.1 Step 2 「scp + psql」流程在無 sandbox DB 環境下需改寫為 BEGIN/ROLLBACK 模式。建議 PA E1 dispatch packet 註明採 transaction rollback 模式（per task brief 已指定）。
- PG WARNING `column "event_id" should be used for segmenting or ordering` — spec §2.3 選 `session_id` segmentby 是 hot-read pattern 設計正確；informational only。

**sqlx checksum drift 治理**:
- 本 dry-run 在 BEGIN/ROLLBACK 內，未寫 `_sqlx_migrations` row → 0 checksum drift hazard
- 將來 V104 真 apply 後 count 102→103, max 不變(112)
- V104 file 若 land 後再 edit → 必跑 `bin/repair_migration_checksum --target V104` per `project_2026_05_02_p0_sqlx_hash_drift`

**Gate 狀態**:
- Gate (2) MIT 4-step dry-run 9/9 PASS — **DONE**
- Gate (1) v56 P0 Layer B + 24h (~2026-05-30) — operator/PM 觀察
- 兩 gate 解後即可 PM 派 Wave 2.4.A E1 IMPL (T1 SM core + T4 V104 audit writer 並行)

**Lessons reinforced**:
1. trade-core 無獨立 sandbox DB；transaction rollback 是當前唯一安全 dry-run 模式
2. V083/V084 NOTICE-skip 模式 = idempotency gold standard；本次 Round 2 verify 一致
3. spec §3.1 Guard A part 3 forbidden column 反模式（非 ML training surface）empirical 確認生效
4. CHECK constraint 4 條全用 boundary INSERT 驗 enforce — 比靜態 SQL parse 強得多

MIT AUDIT DONE: docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-27--v104_supervised_live_audit_dry_run.md

## 2026-05-27 OPS-4 GAP-B + GAP-D PG backup drill (MIT owner, P0 first-day-live blocker)

**Trigger**: P0-OPS-4 first-day live runbook §10 — MIT-owned gaps for PG restore drill + dump cron.

**Report**: `workspace/reports/2026-05-27--ops_4_gap_b_d_pg_backup_drill.md` (183 行)
**Drafts**: `workspace/drafts/ops4_gap_b_d/{install_pg_dump_cron.sh, trading_ai_pg_dump_cron.sh, verify_pg_dump.sh}` (74+101+116 = 291 lines)

**核心 empirical findings (ssh trade-core 21:00-21:05 UTC)**:
1. **0 active pg_dump cron** (crontab 46 行，0 backup entry，only commented Ubuntu sample)
2. **唯一 backup = 53d-old 189KB schema-only pre-phase0a dump** (`/srv/backups/trading_ai_pre_phase0a_20260404_180411.dump`，118 TOC，PG custom format) — DR 無法依賴
3. **trading_ai 真實 = 226 GB** (PG 16 timescale docker container `trading_postgres` healthy 6 weeks)；host pg_dump 16.14 ↔ container 16.13 兼容已驗
4. **NAS 未掛載** trade-core (`/mnt/nas` `/nas` 不存在，nfsd 跑但無 client mount) — 與 `project_hardware_constraints` 10GbE 40TB NAS 假設 drift；spec §7.2 NAS-bound 異地 backup 與 reality drift
5. **841G free on `/`** = 3.7× DB size → 15d × ~50GB (gzip 4-6x 壓縮估計) ≈ 750GB 接近 ceiling → 必縮 retention 至 ~10d OR 接 NAS
6. **Restore path empirical 驗 OK**：sandbox DB `TEMPLATE template0` (避 template1 collation warning) + pg_restore schema-only exit 0 silent / 0.090s / 14 public tables + 14 PK + 2 CHECK 還原；sandbox drop OK 不動主庫

**Drafts 設計亮點**:
- 0 hardcoded `/home/ncyu` 路徑 — 全 env var (`OPENCLAW_BACKUP_ROOT` / `OPENCLAW_BACKUP_RETENTION_DAYS` / `OPENCLAW_BACKUP_HOUR_UTC` / `OPENCLAW_BACKUP_GRACE_HOURS`)
- install script Linux-only gate (Mac dev refuse exit 2) + idempotent (crontab 已有 pg_dump entry 即 skip) + default DRY-RUN (必 `OPENCLAW_BACKUP_CRON_APPLY=1` 才實裝)
- cron wrapper 與 `outcome_backfiller_live_cron.sh` style 一致 (lock dir / secrets env 讀法 / JSONL log + sentinel)
- verify 5-check 含 critical 路徑 (mtime < 26h + size > 1MB 任一失敗即 FAIL exit 2)，給 `passive_wait_healthcheck.sh` 加 `check_pg_dump_freshness()` consume

**Unblock verdict**: NOT CLEARED. GAP-B + GAP-D 兩列 spec §8 MIT sign-off row 仍未滿足。最早 unblock = operator hand-action T+~28 hr (≤2 hr land + dry-run + install → D+1 03:00 UTC fresh dump → D+1 full restore drill ~1 hr)。

**Lessons reinforced**:
1. spec §2.3 "daily logical dump → NAS 異地" 假設 NAS available；reality 不是 → spec 與 runtime drift；MIT audit 必 empirical 查 mount 不能信 spec 描述
2. spec 寫 15d retention 是 minimum；真實 226GB DB → 必驗 dump size 對齊 disk 容量；本 draft 留 env var 讓 operator 縮 7d 或加 NAS
3. weekly `pg_basebackup` + WAL archive 不在 GAP-D 範圍 (spec §2.3 weekly track 是 separate ticket)；本 draft scope = daily logical dump only

## 2026-05-27 OPS-4 GAP B/D PG backup/restore deepening research (post-baseline)

**Reports**:
- baseline 21:06: `workspace/reports/2026-05-27--ops_4_gap_b_d_pg_backup_drill.md` (9.3 KB; empirical + 3 draft script 291 lines)
- deepening 21:00+: `workspace/reports/2026-05-27--ops_4_gap_bd_pg_backup_restore_research.md` (460 lines)

**Empirical discoveries (post-baseline)**:
1. `learning.decision_features_evaluations` = **182 GB / 17d / 279.5M row / 無 retention / 0 SQL consumer** (Rust producer only, intent_processor emit, W-AUDIT-4b 評估痕跡) — DB total 226 GB 中 81% 來自此表
2. `trading.decision_context_snapshots` 20 GB / 46d / 5.8M row
3. `learning.decision_features` 12 GB / 41d / 11.5M row
4. WAL archive 關閉（`archive_mode=off` / `archive_command=disabled` / `max_wal_size=1GB`） → pg_basebackup 不能 PITR; Phase 3 才考慮
5. Compression tools: zstd 1.5.5 ✓ / pigz 2.8 ✓ / lz4 ✗（未裝）/ xz ✓
6. Hardware: AMD Ryzen AI MAX+ 395 / 32 threads / 124 GiB RAM / 47 GiB free / 74 GiB cache / disk 842 GB free / 10GbE confirmed
7. NAS: `/mnt/nas` 未掛載；nfsd 在 trade-core 是 server but no client mount; sudo 拒 export verify

**Design recommendations**:
1. **Dump strategy**: `pg_dump -Fc -j 4 --compress=zstd:3 --exclude-table='learning.decision_features_evaluations' --exclude-table='*_damaged_*'` → 226 GB → 44 GB raw → 6-9 GB compressed
2. **Storage placement**: option A local-only `/home/ncyu/pg_backups/` 15d Phase 1 (90-135 GB << 842 free OK); option B NAS Phase 2 deferred
3. **RTO**: ≤ 4h S1 / ≤ 30 min S2-S5
4. **RPO**: ≤ 24h Tier 0+1 / Phase 3 WAL archive → ≤ 5 min
5. **Drill cadence**: quarterly S1 full + per-event S4 migration rollback + first-day live qualifying drill 必跑

**3 hidden risks (PA OPS-4 spec gaps not listed)**:
1. PA spec §7.2 NAS path 假設不成立（reality 未掛）→ option A 必須先 default
2. PA spec §7.2 `--schema=learning` 默認 include 182 GB evaluations → 1 個月後撞 disk 紅線 → 必加 explicit EXCLUDE + NEW MIT proposal V### retention policy on evaluations
3. PA spec §10 漏列 GAP-J restore-with-sqlx-checksum-drift SOP（per memory `project_2026_05_02_p0_sqlx_hash_drift`）→ restore 後必跑 `bin/repair_migration_checksum`

**Operator confirm needed (block IMPL dispatch)**:
- A. Storage placement option A vs B
- B. `evaluations` 表 EXCLUDE 是否屬 RPO
- C. Retention 15d 或 30d
- D. NAS mount Phase 2 owner

**E1 IMPL packet**:
- Sub-agent A (GAP-D dump cron land): 3-4 hours
- Sub-agent B (GAP-B full restore drill SOP + first drill): 5-7 hours (依賴 D+1 03:00 dump fire ~30h wall-clock wait)
- Total active dev 8-11 hours / 2 parallel sub-agent / ~30h wall-clock

**Push back to PA spec (5 amendments)**:
1. §7.2 NAS → option A local Phase 1
2. §7.2 EXCLUDE evaluations
3. §10 add GAP-I (evaluations retention) + GAP-J (sqlx checksum drift)
4. §8 MIT row sub-check (dump path writable + size sanity)
5. §2.3 explicit RTO/RPO numbers

**邊界遵守**: research only / 不寫 IMPL / 不改 PG schema / 不執行 dump / sub-agent 0 派 / ssh trade-core read-only


## 2026-05-27 OPS-4 GAP-B Q3 column drift fix (MIT round 3)

**Trigger**: E4 regression `2026-05-27--ops_4_gap_bd_e4_regression.md` §3.5 BLOCKER-1 BUG — `helper_scripts/db/post_restore_validation.sql` Q3 references `learning.lease_transitions.ts` but column 不存在（only `ts_ms` bigint + `created_at` timestamptz）。`\set ON_ERROR_STOP on` 致 Q3 ERROR abort 整 9-query drill gate。

**Fix**: Line 99-110 (主 block) + Line 289 (AGGREGATE SUMMARY q3 CTE) `ts` → `created_at`。選 `created_at` 非 `to_timestamp(ts_ms/1000)`：fully-typed timestamptz 直接對齊 `NOW() - INTERVAL` 比較；避免 epoch 換算誤差；audit-trail use case 兩者語意可換用（created_at 是 row insertion time，與 ts_ms 落後 0-ms 級同一 INSERT now() default）；補 5-line column note 注釋說明。

**Verify**: SSH live test 通 2 query：
- Q3 主 block 返 68588 BYPASS transitions/68588 distinct leases (對齊 memory `2026-05-09 v2` 7955 BYPASS/24h steady pattern)
- AGGREGATE q3 CTE 返 n=1 verdict=WARN (only BYPASS to_state in 24h, runtime obs)

**其他 8 query column drift check**：Linux PG empirical `\d` 11 tables:
- Q1 system.autonomy_level_config NOT EXISTS (V099 未 land deployment gap, E4 CARRY-OVER-1 不是 BUG)
- Q2/Q4/Q5/Q6/Q7/Q8/Q9a/Q9b 全 8 query column 對齊真實 schema PASS

**Outcome**: BLOCKER-1 結案；Q1 carry-over 等 V099 / Wave 5 Packet A land；E4 14/15→15/15 GREEN 待 E4 re-verify。

**邊界**: 只改 SQL（MIT scope）；不擴 scope（未補 unit test, E4 round 3 P1 governance carry-over）；不執行 governance_audit_log INSERT。

**Report**: `workspace/reports/2026-05-27--q3_column_drift_fix.md` (本 fix 不寫獨立報告 ≤200 字 inline 即可)

## 2026-05-29 V114 notification_failsafe_events 4-step dry-run — FAIL (退 E1)

**對象**: `sql/migrations/V114__notification_failsafe_events_hypertable.sql` (commit 4ac2b7a4, E1-PC2)
**環境**: Linux trade-core / trading_ai / psql 16.14 / TimescaleDB 2.26.1 / trading_admin role

**BLOCKER (TimescaleDB runtime semantic — Mac static review 抓不到)**:
- Step 5 GRANT 在 Step 4 enable compression **之後** 跑 → `GRANT UPDATE (acked_at_utc, acked_by)` column-level grant 被 TimescaleDB 傳播到 internal `_compressed_hypertable_94`,該壓縮 twin rel 無 user column → `ERROR: column "acked_at_utc" of relation "_compressed_hypertable_94" does not exist`。
- ERROR 在 line 262 abort → GRANT USAGE ON SEQUENCE (264) + REVOKE PUBLIC (268) + Guard C 後驗全沒跑。
- table-level `GRANT SELECT, INSERT` (260) 已成功 (table-level grant 不查 column 存在性,clean propagate)。只有 **column-level** GRANT 觸發此 bug。
- V109 無此問題因 V109 無 column-level GRANT (只 CREATE+compression)。這是 V114 引入 column-level UPDATE grant 新 pattern 的首次踩雷。

**修法建議 (回 E1,不自己改)**: 把 Step 5 GRANT 移到 Step 4 compression **之前**;或 enable compression 前先做全部 GRANT/REVOKE。column-level grant 必須在 hypertable 還沒 compressed twin 時做。需 E1 改後重跑 4-step dry-run 才 sign-off。

**Schema 設計本身正確 (Step 1-4 全 PASS)**: 17 col 全對 type、chunk=604800000ms(7d)、2 hot-path index + 1 ts auto index + pkey、event_type CHECK 1 值、compression policy 30d (2592000000ms)。
**INSERT/ack 語義驗證 PASS**: audit_emitter.rs 13-binding INSERT 完美對齊 (RETURNING id=1);ack #1 UPDATE 1 / ack #2 (double-ack) UPDATE 0 idempotent / acked_by 不被覆蓋。
**audit_emitter.rs INSERT 13 col + 4 DB-controlled (id/acked_at_utc/acked_by/created_at) = 17 col 對齊正確**。

**遺留 dirty 狀態 (operator 必清)**: partial-apply 留下 `observability.notification_failsafe_events` 表 + hypertable + compression (0 row),但 V114 **未** 進 `_sqlx_migrations` (max 仍 113)。test row 已 DELETE 清掉。DROP TABLE 被 auto-mode classifier 擋 (用戶禁 trading_ai 破壞性 DROP),須 operator 手動 `DROP TABLE observability.notification_failsafe_events CASCADE` 後再 apply E1 修正版 V114。否則下次 sqlx migrate 會重撞同 GRANT error。

**Report**: 直接回 main session (本 task 不寫 report file)。

## 2026-05-29 V114 fixed dry-run — idempotency BLOCKER (NEW, 2nd-run only)

- **背景**：V114 notification_failsafe_events hypertable。上輪 (2026-05-28) BLOCKER = column-level `GRANT UPDATE (acked_at_utc, acked_by)` 在 compression 之後 → 傳播到 compressed twin (twin 無該 column) → 1st-run abort。E1 fix `faf7c06c` 把 GRANT/REVOKE 移到 compression 之前。
- **第一跑 (clean DB) PASS**：GRANT-before-compression 修好 1st-run；twin 尚未存在時 column-level grant 合法；all guards PASS，EXIT 0。schema 全對 (17 col / 7d chunk / 30d compress / 2 index / event_type CHECK 1 值)。INSERT+ack 語義對齊 audit_emitter (`WHERE acked_at_utc IS NULL` → 2nd ack UPDATE 0 不覆蓋 acked_by)。
- **第二跑 (idempotency) FAIL — NEW BLOCKER**：`ERROR: column "acked_at_utc" of relation "_compressed_hypertable_96" does not exist` at line 240。RCA：1st-run 的 compression enable 建了 persistent compressed twin；2nd-run 重抵達 column-level GRANT 時 twin 已存在 → TimescaleDB 傳播 column-level grant 到 twin → 同樣 abort。**GRANT-before-compression 的 reorder 只解 1st-run，不解 re-apply**，因為 twin 跨 run 持久存在。
- **根因類別**：V114 是全 repo 唯一同時用 column-level `GRANT UPDATE (cols)` + compressed hypertable 的 migration（V109 主 reference 無任何 GRANT）。此 pattern 前所未測；idempotency 交互未被 exercise。
- **修復方向（給 E1，非自決）**：column-level GRANT 段需 idempotent-safe。選項：(a) 把 column-level GRANT 包進 `DO $$ ... EXCEPTION WHEN undefined_column THEN NULL` swallow twin 報錯；(b) GRANT 前先查 compressed twin 是否存在，存在則 skip column-level grant（grant 已在 1st-run 落 attacl，重跑無需再執行）；(c) 用 table-level GRANT UPDATE + 改用 BEFORE UPDATE trigger 強制 acked_* only（避開 column-level grant 對 twin 的傳播）。建議 (b) 最小改動。
- **GRANT 語義副發現**：trading_admin = 表 OWNER + superuser → 隱式持全 column UPDATE（`information_schema.column_privileges` 顯示全 17 col UPDATE）。append-only column 限制只 bind 非-owner 非-super role；production GUI ack 路徑須用獨立受限 role 連線，不可用 trading_admin。當前 DB 無此受限 role（只有 replay_writer_role/sandbox_admin/trading_admin）。explicit column GRANT 仍正確落 `pg_attribute.attacl` (acked_at_utc/acked_by = w)。REVOKE PUBLIC UPDATE/DELETE 已執行 (PUBLIC 無 UPDATE/DELETE)。
- **engine sqlx 風險**：表現留在 DB 含 compressed twin → engine restart 時 sqlx migrate 跑 V114 會重演 2nd-run abort → **migration 鏈卡死，engine 起不來**。故留表 = 危險。建議 DROP 等 E1 修 idempotent 後再 sqlx 統一 apply。
- **Report**：直接回 main session（無 .md 報告檔，per 角色約束）。

## 2026-05-29 V114 idempotency-fixed Round 3 Linux PG dry-run — DEPLOY-READY (BLOCKER cleared)

**Trigger**: V114 notification_failsafe_events hypertable 第三輪 empirical dry-run。R1 抓 GRANT-after-compression blocker；R2 reorder 修 first-run 但雙跑揭露 compressed twin 跨 run 持久 → re-apply column-level GRANT 撞 twin → abort；R3 驗證 E1 第三修 (`b9648764`, nested EXCEPTION WHEN undefined_column) 是否徹底修好。

**Method**: ssh trade-core → docker exec trading_postgres (DB trading_ai, user trading_admin = OWNER + SUPERUSER)；psql -f V114 × 3 runs + reverse verify + INSERT/ack semantics。HEAD `575a0a94`。

**Verdict: PASS — V114 DEPLOY-READY (前兩輪 BLOCKER 徹底修好)**

**Step 1-7 全 PASS**:
- S1 clean start: regclass NULL / sqlx max=113 / (15 pre-existing twins 來自其他 hypertable 非 V114)
- S2 run1 EXIT 0: Guard A/B/C PASS, hypertable id 97, first-run column GRANT 成功 (twin 未建, nested EXCEPTION 不 fire), compression enable + 30d policy
- **S3 run2 EXIT 0 (關鍵 — R1/R2 都 fail 在這)**: nested EXCEPTION 捕捉 undefined_column (42703) → NOTICE「column-level GRANT UPDATE skipped — compressed twin exists on re-apply (grant already in pg_attribute.attacl from first-run; idempotent)」→ 不 abort；CREATE/hypertable/index/compression 全 skip 冪等
- S4 run3 EXIT 0: 輸出 byte-identical to run2，穩定冪等不只兩跑
- S5 reverse: 17 col / chunk 604800000 (7d ms) / compression_enabled=t / 2 explicit index (+PK +TS auto _ts_ms_idx) / event_type CHECK 1 值 / compression policy compress_after 2592000000 (30d ms)。**GRANT**: attacl `{trading_admin=w}` on acked_at_utc+acked_by 落 pg_attribute (column GRANT first-run 持久) ✓。**REVOKE PUBLIC**: public UPDATE/DELETE/SELECT 全 f ✓
- S6 INSERT 13-binding (對齊 audit_emitter.rs $1-$13) → id=1；ack UPDATE#1 → 1 row；ack UPDATE#2 → 0 row (acked_at_utc IS NULL guard 冪等, acked_by 不被覆寫) 對齊 `ack_failsafe_event` Ok(rows_affected==1)；DELETE 1 cleanup → 0 row remain
- S7 artifact: table_exists=true / sqlx_max=113 / v114_in_sqlx=false / row_count=0 / v114_twin_exists=true

**關鍵發現 (adversarial)**:
- trading_admin 是 table OWNER + SUPERUSER (rolsuper=t)。has_*_privilege 對 trading_admin 全 column UPDATE 回 t 是 superuser bypass，**不是** append-only enforcement 失效。真正 enforcement 邊界 = PUBLIC REVOKE (對非 owner/非 superuser role 生效) + column-level attacl (定義非 superuser grant floor)。append-only 對 trading_admin 本身靠 application-layer (audit_emitter 只 INSERT + ack_failsafe_event 只 UPDATE acked_*)，非 DB privilege 硬擋。**設計正確但須 PM 知此語義**。

**留表 vs DROP 建議**: **留表安全 (idempotency 修好後)**。理由：next engine restart sqlx (AUTO_MIGRATE=1) 跑 V114 = 即 S3/S4 已三證 EXIT 0 場景 (table+twin exist → CREATE/hypertable/index skip, column GRANT nested EXCEPTION skip, compression skip, Guard C PASS) → 成功 record V114 進 _sqlx_migrations。**checksum 無 drift 風險**：V114 從未經 sqlx 路徑 land (純 psql -f)，無 prior checksum 可漂 (對比 P0 sqlx hash drift incident 5/2 是「sqlx-applied 後 file 改」才漂；本案不同)。建議：留表，下次 engine deploy sqlx 統一 apply。

**Lesson**: TimescaleDB compressed twin (_compressed_hypertable_NN) 跨 migration run 持久；任何 enable compression + column-level GRANT 的 migration，column GRANT 必包 nested EXCEPTION WHEN undefined_column 才能雙跑/sqlx re-apply 冪等。V114 nested EXCEPTION pattern 應作為後續同類 migration 的 reference。

**Report**: findings 直接回 main session (本次無獨立 report file)。

## 2026-05-29 V115 basis_panel migration + Linux PG empirical dry-run (P2-BASIS-PANEL-INFRA hard-gate)

**Trigger**: P2-BASIS-PANEL-INFRA V115 migration hard-gate；PA spec `2026-05-29--basis-panel-infra-spec.md`；A1 funding_short_v2 Stage 0R 前置 basis panel 持久化層。

**Report**: `workspace/reports/2026-05-29--v115_basis_panel_dry_run.md`（同步 Operator/）

**交付**:
- V115 SQL: `/Users/ncyu/Projects/TradeBot/wt-basis/sql/migrations/V115__panel_basis_panel.sql`（430 行；worktree `wt-basis` on `feature/basis-panel-infra`，HEAD d2bbc79a）
- Schema: `panel.basis_panel` 6 col（snapshot_ts_ms BIGINT / symbol TEXT / perp_last_price f8 / index_price f8 / basis_pct f8 SIGNED / source_tier TEXT default 'bybit_v5_ws_tickers'）；PK (snapshot_ts_ms, symbol)；**無 mark_price / 無 engine_mode**（market 共享平面，對齊 sister）；NOT NULL on 3 numeric（fail-closed 在 writer 端 index≤0 不寫 row）
- mirror V085 funding_rates_panel / V087 oi_delta_panel pattern：1d chunk (86400000 ms)、panel.unix_now_ms() integer_now_func、14d retention (BIGINT 1209600000 ms)、**無 compression**（sister 皆無，surgical）、Guard A/B/C 完整

**Linux PG dry-run（ssh trade-core, trading_ai, BEGIN/ROLLBACK double-apply）逐項 PASS**:
- Guard A: CREATE TABLE IF NOT EXISTS 正確；6 col 全 NOT NULL 對齊 spec ✓
- Hypertable: is_hypertable=1, chunk_interval=86400000 (1d), snapshot_ts_ms BIGINT epoch ms 軸 ✓
- **double-apply idempotency**: APPLY 2 全 NOTICE-skip（schema/table/hypertable/retention/index 全 "already exists, skipping"），**0 RAISE**（V083/V084 gold pattern 對齊）✓
- Retention: drop_after=1209600000 (14d) policy 掛上 ✓
- integer_now_func: unix_now_ms 註冊到 dimension ✓
- index: 3 個（PK + idx_basis_panel_ts_desc_symbol (ts DESC, symbol) + basis_panel_snapshot_ts_ms_idx (ts DESC)）✓
- boundary index≤0 不寫 row: schema 用 NOT NULL on index_price 表契約底線；**MIT 裁決 schema 不需 CHECK (index_price>0)**（writer skip + NOT NULL 已 fail-closed；加 CHECK 會讓 batch flush 一條違反全 abort，反不利；對齊 sister 無 value-range CHECK）✓
- **post-rollback residue=0**：basis_panel_table=0, max_migration=114 → trading_ai pristine 未污染 ✓

**關鍵 empirical finding（非 bug）**:
- `create_hypertable` **auto-create** `<table>_<timecol>_idx` = `basis_panel_snapshot_ts_ms_idx` on (snapshot_ts_ms DESC)，與 spec §3.1 line 103-104 explicit secondary index **byte-identical** → 我的 CREATE INDEX IF NOT EXISTS 正確 no-op skip。3 sister panel 全同此 auto-index pattern（funding_rates/oi_delta/btc_lead_lag 皆有 `_snapshot_ts_ms_idx`）→ V115 follow 既有 gold pattern。secondary index 是 redundant no-op 但無害，符合 spec 意圖。Mac mock 絕對抓不到此 TimescaleDB runtime semantic — 再證 V055/V114 教訓「Linux PG empirical mandatory」。

**basis 公式 parity（E2 必驗，已 grep 對照）**: strategy live `funding_short_v2/mod.rs:155-157` compute_basis_pct(perp_price=ctx.price=last_price, ctx.index_price) = `((perp/ip)-1.0).abs()*100.0`（**取 abs**）。panel 存 **signed** `(last/index-1)*100`；consumer/Stage 0R runner 取 `ABS(basis_pct)` 比 gate。分子必 = last_price（非 mark_price）否則 Stage 0R 與 live 不可比。

**sign-off**: V115 SQL **PASS — ready for E1 writer IMPL**（E1 在同 wt-basis 接 basis.rs + panel_aggregator wire + a1 runner SQL）。

**給 E1 注意點**:
1. writer fail-closed：index≤0 / 缺失 → **skip（不發 INSERT、不寫 0、不寫 NULL row）**；NOT NULL 已是 schema 防線但 INSERT 整批會 abort，writer 必先過濾
2. basis_pct 存 **signed**（不取 abs）；source_tier 顯式寫 'bybit_v5_ws_tickers'
3. ON CONFLICT (snapshot_ts_ms, symbol) DO UPDATE（idempotent flush）
4. cohort 用 PanelAggregator 既有 cohort_symbols（單一 SSOT，避 8b round-1 RED self-imposed scarcity）
5. latest-value cache：index_price 只在 ~1/8 frame 帶 → 跨 frame 保 last-known（對齊 funding_curve）；從未收過 index 的 sym 不入 cache
6. V115 land 後 sqlx checksum：operator AUTO_MIGRATE 路徑正常 land（dry-run 未真 apply，max_migration 仍 114，無 hash drift 風險，與 V083/V084 手動 psql -f 場景不同）
7. 無 IPC slot（spec §6.4 #5）；無 healthcheck 是 CLAUDE.md §七缺口 — E1 IMPL 時補 basis_panel freshness check

## 2026-05-30 DB+ML foundation re-audit (Phase 2 PM cold audit) — frozen baseline 187704f6

**Report**: `workspace/reports/2026-05-30--MIT--db_ml_foundation_audit.md` (+ Operator copy)
**Verdict**: P0=0 / P1=0 / P2=2 (deferred-by-design) / P3=1 (mitigated). Prior v84 cold-audit remediation HELD.
**ML stage (explicit)**: SHADOW/ADVISORY + DEMO-APPLY; live ML BLOCKED — unchanged & correct.

**FRESH-CONFIRMED (direct runtime, durable facts)**:
- **e9f01569 is the engine BINARY content SHA, NOT a git commit.** Proof: `ssh trade-core readlink
  /proc/251791/exe` = `.../rust/target/release/openclaw-engine`; `sha256sum` of it = `e9f015696f795b97...`
  (prefix == e9f01569). `git cat-file -t e9f01569` = `Not a valid object name` on BOTH Mac and Linux. Real
  build commit = `ec995160`. v85 self-correction VINDICATED. **Lesson: never run git-ancestry on a /proc/exe
  SHA; binary-content-hash != git-ref is a recurring confusion — check `readlink /proc/PID/exe` + sha256sum.**
- **V104 supervised.live_audit NEVER EXISTED** (free hole). `git log --all -S supervised_live_audit --
  '*.sql' '*.rs'` EMPTY; src grep EMPTY; sql/migrations V103->V106 gap (no V104/V105 file). The 2026-05-27
  MIT v104 dry-run report (8345 bytes) reviewed a NON-EXISTENT migration = **now SUPERSEDED/VOID**. v84
  "V104 checksum frozen" = part of the same-day hallucination (commit d9128e22), reversed by 8d1890a8 + new
  Gate 2b. **Lesson: a "dry-run sign-off" report is NOT proof the migration file exists — verify file on disk +
  git-log -S before signing. This is the V023/P0-sqlx-hash-drift discipline; team self-caught it = process win.**
- **V115 panel.basis_panel source EXEMPLARY**: Guard A/B/C, idempotent, hypertable (1d chunk BIGINT
  snapshot_ts_ms) + integer_now_func + 14d retention. **basis_panel has NO engine_mode column + NO IPC slot BY
  DESIGN** — it is market-data/market-truth (not per-engine), offline-replay-only; live A1 uses in-memory
  index cache. NOT NULL fail-closed (index<=0 => no row). Writer = BasisAggregator panel_aggregator/basis.rs,
  Bybit WS->PG 60s flush. **No Binance fetcher** (SHARED FACT). **Lesson: do NOT flag panel.* market-data
  tables for missing engine_mode CHECK — the engine_mode-IN-rule governs learning/training tables only.**
- **Source-code delta baseline 187704f6 -> HEAD fe8393e2 = ZERO non-docs** (7 files, all docs/agent-reports).
  Mac HEAD == Linux HEAD == fe8393e2. TODO v85 banner `e63a00e0` is stale (minor doc-hygiene, non-load-bearing).

**INHERITED-RECORD (could NOT re-run — non-interactive SSH has EMPTY DATABASE_URL; PG in container on socket
/var/run/postgresql/.s.PGSQL.5432; env in environment_files/+secret_files/ not sourced)**: _sqlx_migrations
max=115, basis_panel 25 sym/60s/age~36s, model_performance=0. Filed as disclosed Blocker for MIT/E4 live re-run.
**Lesson: read-only psql over ssh trade-core needs the engine env sourced (systemd EnvironmentFile), not a bare
non-interactive shell — plain `psql "$DATABASE_URL"` resolves to the empty local socket and fails.**

**P2-06 (model_performance evaluator-writer) + P2-07 (Stage-B cohort replay)**: CONFIRMED HONEST design-
complete/impl-deferred — tables exist (V004), no dead table, 0-rows correctly disclosed as Foundation-only, not
claimed-live.

## 2026-05-30 V104 真檔 Gate 2b idempotency double-apply dry-run — APPROVE

**Report**: `workspace/reports/2026-05-30--v104_real_file_gate2b_dry_run.md`

**Trigger**: P0-LG-3 部署前強制 gate；E1-T4 寫出 V104 真檔（branch `feature/lg3-t4`@`45a23068`，worktree `/tmp/wt-lg3t4`，416 LOC，sha256 `afceb98e...`）。規則：真檔必重跑 dry-run，不可沿用 2026-05-27 candidate 9/9（那是手寫 candidate，repo 當時無真檔，per PA reality-check）。

**Verdict: APPROVE — V104 真檔可進部署。**

**核心結果**:
1. **double-apply 0 RAISE / 0 ERROR / 0 EXCEPTION**，兩路徑（existing-path re-apply + fresh-path drop-in-tx CREATE）各 round 全 NOTICE-skip，"all guards PASS" ×2/路徑。
2. **9-query reflection 9/9 PASS**：21 col / 4 CHECK（action 17-enum / result 3 / engine_mode (live,live_demo) 拒 paper / ts_ms>0）/ chunk 604800000000µs=7d / segmentby session_id / compress 30d / retention 90d / 4 named idx / forbidden ML col 0（non-training surface invariant 達成）/ table=learning.supervised_live_audit。
3. **drift 防護 PASS**：`git diff cc6c54d0 feature/lg3-t4 -- sql/migrations/` = 只 `A V104`，0 既有 migration 改；V104 是 V103↔V105 free hole（version-sort 補洞合法）。
4. **Guard A 三段 empirical 有效**：part1 missing-prereq RAISE / part2 column-count-drift(22≠21) RAISE / part3 forbidden-ML-col detection SQL 正確（A3_detects_forbidden=signal_id）。
5. **_sqlx_migrations max=115 count=105 未污染**（前後一致，V104 ABSENT；deploy 時 sqlx 註冊 count→106）。

**重要環境發現**: prod PG **supervised_live_audit table 已實體存在**（21col/4CHECK/hypertable/6idx/comp+ret job/0row）— 先前手動 `psql -f` apply 過但 sqlx 未註冊。故 deploy `AUTO_MIGRATE=1` 走 sqlx 會註冊 V104；因全 idempotent → NOTICE-skip 安全。**若 V104 file 再 edit 必跑 `bin/repair_migration_checksum --target V104`**（per project_2026_05_02_p0_sqlx_hash_drift）。

**2 非阻塞註記**:
- **6a dry-run 衛生事故（已自我清理）**：Guard A part1 negative test 的 psql script 漏 `\set ON_ERROR_STOP on`，`RENAME governance_audit_log` 在 V104 RAISE 前自動 commit，洩漏空表 `governance_audit_log_tmp_mit`（0row）；已用 guarded DO-block（驗 real 在 + tmp 0row 才 drop）安全清；最終 `any_mit_leak_tables=NONE` / real gov 完整（2idx/0row）。**durable lesson：負向 Guard test 若改 prod prereq 表，必包 SAVEPOINT + `\set ON_ERROR_STOP on`；更佳是純 to_regclass 邏輯測（不動真表，如 part3 isolated test）。BEGIN/ROLLBACK 不夠 — psql 無 ON_ERROR_STOP 時 DDL 可能在 RAISE 前已落地。**
- **6b cross-branch 一致性（item 3）DEFERRED**：T1 `SmAction.as_str()` 17 值源碼**不存在於任何 ref**（lg3-t1 tip==base / wt-lg3t1 無 SmAction / test sm_action_strings_match_v104 0 hit / main HEAD 0 hit）。SQL 端逐字比對無對照物。V104 canonical 17-enum baseline 已記入報告 §6b（順序 = as_str() 必輸出順序）。T1 IMPL DONE 後 MIT 須重跑 item3（T1 自帶 test 必要不充分）。

**PG empirical method 教訓再強化**: 17 command + redirect /tmp 暫存檔分次讀（SSH 輸出常 interleave/garble，憑記憶報數字危險）；ON_ERROR_STOP=0 的負向 prereq-mutation test 是 prod 污染地雷（本次親身觸發 + 清理）。

## 2026-05-31 Cost-wall escape #2 — low-turnover multi-day perp TREND (TSMOM) read-only diagnostic

**Trigger**: operator 拍板即時跑成本牆逃逸類別 #2（低 turnover 多日持倉，把 11-27bps 往返成本攤到多日 100s-1000s bps move）。read-only PG（docker exec），0 寫 0 部署。Alpha SSOT §4/§5 framing；TSMOM 不在 §3 candidate pool（這是 fresh 探路）。

**Verdict: OBSERVE_MORE（樣本嚴重不足）+ 一個 structural HINT 值得在資料變深後追**。
- **Feasibility 一句話**：dilution thesis 機械上成立（gross multi-day move 遠 >> 成本牆），但 56d 窗口最多只給 ~8 個獨立時間週期 → 任何 weekly+ 策略 effective N_independent ≈ 8，無法 robustly validate edge。**不能從稀樣本宣稱 edge**。

**核心 empirical（PG live 2026-05-31, market.klines）**:
1. **窗口 = 56 天**（2026-04-05 collector onset → 2026-05-31）。142 symbols 收 1m/5m/15m/1h；137 sym 收 4h（6262 row）。
2. **1m 有 gap**：BTCUSDT/ETHUSDT 平均 1259 bars/day（vs 1440 full），56d 內只 36 full days。daily close 取「每 UTC day 最後一根 closed 1m bar」可用但是 research-grade-with-gaps，非 pristine。
3. **TSMOM per-symbol N/M sweep（10 liquid sym, non-overlapping, leak-free）**：
   - 7/7: n=47 gross-70bps t-0.43 | 14/7: n=37 +60bps t0.31 | **14/14: n=15 +267bps t0.70 win47%**
   - 30/7: n=18 -235bps t-2.22 | 30/14: n=6 -375bps t-1.58 | 14/21: n=7 +591bps t2.67 **win100%（degenerate, n=7 紅旗非信號）**
   - **abs_move 389-1213 bps 跨全 cell** → 成本 15bps+M funding ≈ 占 gross move 3-4%。**成本攤薄假設機械成立**。但 sign 跨 N/M 不一致（real TSMOM 該有 coherent sign structure）→ 看起來是 noise 不是 signal。
4. **Cross-sectional momentum（14 sym, rank top/bottom tercile）**：14/14 → 只 **2 個 rebalance 週期** n_legs=14 gross-321bps t-0.49；7/5（最大化週期數）→ **8 個 rebalance 週期** n_legs=59 gross+54 net+34bps t0.29 win49%。**8 = 此窗口 weekly+ 策略獨立時間週期上限**（binding constraint 是時間週期數非 symbol 數）。
5. **Funding（market.funding_rates, 25 sym, 1890 row）**：avg daily drag 0.14-0.79 bps/day（signed），avg abs per-settle 0.38-0.73 bps。多日 horizon 下 funding 是 rounding error（再證攤薄）。我 sweep 用 1bp/day 近似 = 略保守（對成本側 generous）。

**Leak-free 保證（已實證, dump BTCUSDT 兩筆）**: trailing return 只用 entry day 及之前 closed bar（lookback_before_entry=t）；forward return 嚴格 entry→exit（exit_after_entry=t）；daily close = DISTINCT ON ... close_ts_ms DESC = 每日最後一根 closed 1m bar（無 partial-bar leak）；non-overlapping entry via `(rn - (N+1)) % M = 0`。6 leakage 類型全綠。

**Alpha SSOT scorecard 對照**: data_window 56d / n_events 6-59（**全 < 30 robust 線，除 7/7 cross-sect n=59 但僅 8 獨立週期**）→ **Sample gate FAIL → observe_more**。Fee gate: 機械 pass（成本 << move）但 edge 不顯著故 moot。trend 是擁擠 published anomaly（McLean-Pontiff decay）→ DSR deflate 需要，但 56d 不足以 robust validate，誠實標。

**HINT（值得追，非結論）**: 成本攤薄機制是真的（這是逃逸 #2 的核心假設驗證 PASS）；缺的是「歷史深度」不是「機制」。需 ≥ 6-12 個月日線資料（≥ 50-100 個獨立 14d 週期）才能 robust 估 TSMOM edge。短期不可行；列為「資料變深後重跑」候選。當前**不建議**進 Alpha Tournament IMPL（A1/A2 優先）。

**Report**: `workspace/reports/2026-05-31--cost_wall_escape_2_multiday_trend_diagnostic.md`（+ Operator copy）

## 2026-05-31 Historical kline backfill spec (E1-ready) — unblock cost-wall-escape #2 multi-day trend

**Trigger**: operator directive — invest data infra + fastest path to robustly test multi-day perp TREND (TSMOM/cross-sectional). R-2b (`2026-05-31--cost_wall_escape_2_multiday_trend_diagnostic.md`) validated dilution mechanism (gross 389-1213 bps, cost ~3-4% of move) but edge unverifiable because klines only 56d (~8 independent weekly periods << n>=30 gate). Bottleneck = historical depth, not mechanism.

**Spec**: `docs/execution_plan/specs/2026-05-31--historical-kline-backfill-spec.md` (209 lines). Backfill Bybit daily(`1d`)+4h >=12mo (MIT default 18mo) via public `GET /v5/market/kline`.

**Empirical klines schema (this run, `\d market.klines` + timescaledb_information on trade-core)**:
1. **PK = `(symbol, timeframe, ts)`** = dedup key. **NO source/provenance column** (12 cols, none is origin) — live-WS row and backfill row indistinguishable at row level.
2. Live writer (`market_writer.rs:268`) = `ON CONFLICT (symbol, timeframe, ts) DO NOTHING` (non-destructive, first-writer-wins). Backfill MUST reuse identical clause => idempotent + gap-fill-only + never clobbers live rows.
3. **RETENTION TRAP (HIGH/BLOCKER)**: `policy_retention drop_after=365d` runs DAILY on klines (hypertable_id=4). >12mo backfill is auto-reaped within 24h (months 13-24 already past drop boundary) — silent data loss (V023-spirit: job doesn't error, just drops chunks). MIT default fix = operator `remove_retention_policy` + `add_retention_policy(... '1095 days')` (reversible) BEFORE backfill. This blocks the run-step.
4. **`'1d'` is a NEW timeframe value** — current distinct = `1m/5m/15m/1h/4h` only, no `1d`. Bybit `D` -> store `'1d'`. Additive: `outcome_backfiller.rs:54-84` hardcodes `1m/5m/1h/4h`, won't match `1d` (no breakage). 4h already has 6262 incomplete live rows (R-2b: BTC ~91%, most far less) — backfill gap-fills via DO NOTHING.
5. chunk=7d, compress_after=14d, OHLC=`real`(float4). Chunk count NOT a blocker (~104 weekly chunks for 24mo, tiny daily/4h volume). Bybit kline endpoint has no tick_count -> set NULL (honest, not fake 0).

**API**: `GET /v5/market/kline` public/no-auth, newest-first, 1000/page, Market group 120 req/s. 18mo/25sym ~= 125 requests ~= single-digit minutes at throttled 2 req/s. retCode 10006 IpRateLimit retryable w/ backoff; all other non-zero = fail-closed loud per-symbol.

**ADR compliance**: Bybit-native read-only public market data — does NOT invoke ADR-0033/0040 cross-venue gate (that governs *Binance*; Bybit market data is baseline, never restricted). No execution, no non-Bybit venue, no auth/secrets.

**Provenance firewall (MIT key insight)**: backfill writes ONLY `1d`(new)+`4h`(gap-fill), never `1m` => the sensitive live-1m ML/decision_outcomes surface is provenance-clean BY CONSTRUCTION (timeframe namespace), no schema change needed. Optional provenance ledger table = separate MIT/E2 migration (Guard A/B/C) out of E1 scope.

**Chain**: MIT spec -> E1 backfill script (+ BB API check) -> E1 run (Linux) -> MIT data-quality verify (incl. confirm retention didn't reap post next daily job + no live-1m contamination) -> MIT re-run R-2b leak-free SQL on deep window + DSR deflation (alpha go/no-go = QC+MIT joint).

**5 open decisions to PM/operator**: 7-A retention (BLOCKER, extend to 1095d) / 7-B window (12 floor / **18 default** / 24 stretch) / 7-C symbols (25 sufficient — period-count binding not breadth) / 7-D provenance (default co-mingle-by-tf) / 7-E confirm `1d` string.

**Survivorship discipline (R-2b §5 carried forward)**: E1 must record real Bybit min(ts) per symbol (listing date); not pad missing early history; diagnostic computes n_independent from real coverage. Restricting to active symbols = mild survivorship, material if symbol listed mid-window.

**Boundary**: read-only spec; 0 code / 0 schema / 0 backfill; git fetch + NO-OP existence check passed before write.

## 2026-06-02 V125 + V126 Linux PG double-apply dry-run (authoritative gate)

**Trigger**: V125 (research.alpha_* AEG storage) + V126 (schema hygiene DROP) hard-gate before any production apply. Layered safety: V125 §A-§C in sandbox double-apply; V125 §D + V126 全 DROP = production read-only reflection + logic audit only (NO production DROP / NO retention-replace).

**Verdict**: **V125 BLOCKER (return-to-E1) / V126 PASS (logic-audit GO) / BEGIN-COMMIT 裁決 = SAFE**

**Method**: ssh trade-core → docker exec trading_postgres psql. Role = `trading_admin` (NOT openclaw/postgres — env POSTGRES_USER). DB trading_ai. Sandbox = `v125_dryrun_sandbox` created `TEMPLATE template0` (template1 collation-version mismatch blocks plain CREATE DATABASE — reusable trick). TSDB 2.26.1 both prod + sandbox. Sandbox dropped after.

**V125 §A-§C sandbox double-apply (逐斷言)**:
- 6 tables / 3 hypertable (chunk=604800s=7d all) / 3 compression segmentby=symbol(segidx=1) / 3 retention=1095d — ALL PASS
- C-3 NOT NULL: funding_rate/open_interest/buy_ratio/sell_ratio all is_nullable=NO; boundary INSERT NULL → not_null_violation at chunk level; valid insert ok; 0 leaked rows — PASS
- **Idempotency body PERFECT**: apply 1 + apply 2 both COMMIT with 0 RAISE; re-apply = schema/table/index "already exists skipping", hypertable "already a hypertable", compression "already enabled; skipping ALTER" (the ELSE branch of EXISTS-guard at line 609-611 fires — nested BEGIN/EXCEPTION twin-handler is defensive backup, primary idempotency = EXISTS guard), add_compression/retention_policy "already exists skipping" (if_not_exists works)

**V125 BLOCKER (real bug, fails production too)**:
- §E post-COMMIT Guard C lines 839-840: `SELECT segmentby INTO v_segmentby FROM timescaledb_information.compression_settings` → **ERROR: column "segmentby" does not exist** on TSDB 2.26.1. Reproduces identically on apply 1 AND 2 (deterministic, version-specific).
- TSDB 2.26.1 compression_settings cols = `hypertable_schema, hypertable_name, attname, segmentby_column_index, orderby_column_index, orderby_asc, orderby_nullsfirst`. NO `segmentby` col. Correct introspection = `attname WHERE segmentby_column_index IS NOT NULL`.
- §C EXISTS-checks (lines 593/628/662) dodge it (only `SELECT 1 ... WHERE schema/name`); only §E column-SELECT trips.
- **Production failure mode (load-bearing)**: explicit COMMIT (line 778) commits sqlx outer tx EARLY (before sqlx's own INSERT _sqlx_migrations + before §E). §A-§C DDL → durable. §E errors in autocommit → `conn.execute()` Err → `migrator.run(pool).await?` (migrations.rs:193) `?` propagates → **engine auto-migrate startup ABORTS**. sqlx never records V125 row → next restart re-applies → §A-§C idempotent skip → §E errors AGAIN → **permanent crash-loop** until E1 fixes §E. Functional intent (compression+retention) IS correct — only the verification query is broken.
- Bonus: TSDB advisory `WARNING: column "category" should be used for segmenting or ordering` (PK leading col not in segmentby/orderby) — non-fatal cosmetic.

**BEGIN/COMMIT 裁決 = SAFE (E1 flag 解除)**:
- migrations.rs:336/380: sqlx Migrator `no_tx=false`; per-migration `no_tx = sql.starts_with("-- no-transaction")`. V125/V126 不走 opt-out → sqlx wraps each in its own tx.
- Empirical (outer-BEGIN sim around V125 sandbox): inner `BEGIN` → `WARNING: there is already a transaction in progress` (NOT error); inner `COMMIT` commits outer tx; post-COMMIT SELECT runs in autocommit (proven: marker SELECT succeeded after §E error → connection NOT in aborted-tx).
- Precedent confirmed: V115/V113/V097/V092/V090 all have explicit body BEGIN/COMMIT + all applied successfully via runner (V115 commit ec995160). E1 concern was correct to flag but the precedent + empirical both say显式 BEGIN/COMMIT under sqlx wrapper = harmless WARNING. **NOT a V125/V126 blocker.** (Caveat: it's exactly the early-COMMIT behavior that makes the §E BLOCKER fail post-COMMIT in autocommit rather than rolling back — fixing §E is still mandatory.)

**V126 production read-only reflection + logic audit = PASS (GO, no apply)**:
- Packet 1: 4 damaged tables exist, exact counts fills=17265 / intents=7684 / orders=4509 / risk_verdicts=4,181,398 (903MB). pg_depend relation-dependents=0 each. Guard intentionally count-skip (故意非空), pg_depend-only — correct for evidence-backup tables.
- Packet 2: 6 legacy tables exist, all count=0, pg_depend dependents=0 each. count=0 + pg_depend guards correct.
- Packet 3: 7 target cols all exist on trading.decision_context_snapshots; column-level view-refs on the 7 = 0 (safe drop); recent_sequences view-refs=1 (referenced by `learning.scorer_training_features` — CC BLOCKER exclusion CORRECT).
- **Stale-comment finding (non-blocking)**: V126:411-415 claims decision_context_snapshots IS a hypertable (V003:96) + lists "hypertable DROP COLUMN" as must-verify. Production reflection: `dcs_is_hypertable=FALSE` (plain table now). De-risks the compressed-chunk DROP COLUMN hazard entirely; but SQL comment is factually wrong → E1 should correct comment (was it never converted, or de-converted? — V003 says create_hypertable; current state plain). DROP COLUMN on plain table is trivially safe.
- All 10 DROP-table guards will NOT RAISE (dependents=0 verified) → drops proceed clean. V126 logic correct against current production state.

**V125 §D production read-only reflection + logic audit = PASS (GO, no apply)**:
- market.klines: 1 retention job @365d + 1 compression job @14d (exactly as packet claims).
- §D: `remove_retention_policy('market.klines', if_exists)` + `add_retention_policy(1095d, if_not_exists)`. Correct: removes 365d, adds 1095d, leaves 14d compression (compression = `policy_compression` proc, retention removal can't touch it). Post-replace = exactly 1 retention @1095d. Logic sound. (Note: §D itself runs INSIDE the committed body BEFORE the broken §E guard — so on a fixed-§E V125, §D would apply correctly.)

**Zero-mutation proof (post-cleanup)**: research absent / max_migration=115 / klines 365d+14d unchanged / sandbox gone / 4 damaged + 6 legacy intact. All work read-only on prod + isolated sandbox.

**Action**: V125 → E1 fix §E lines 839-850 (`SELECT segmentby` → `attname WHERE segmentby_column_index IS NOT NULL`, or check segmentby presence via `EXISTS(... WHERE attname='symbol' AND segmentby_column_index IS NOT NULL)`). Re-run sandbox double-apply after fix (must reach `V125: all guards PASS` NOTICE with 0 ERROR). V126 + V125-§D logic GREEN, no SQL change needed (V126 optional: correct stale hypertable comment). BEGIN/COMMIT no change.

**Report**: returned inline to PM (no separate report file per task instruction).

**Lesson reinforced**: V055/V114 mandate validated AGAIN — `timescaledb_information.*` view column names are version-specific and only exist on real TSDB; Mac mock pytest cannot surface `column does not exist`. Post-COMMIT guard blocks in forward-only sqlx migrations are doubly dangerous: DDL commits, guard crashes, startup crash-loops with no rollback. Any V### Guard C that SELECTs a TSDB introspection column (not just EXISTS) MUST be Linux-empirically dry-run.

## 2026-06-02 TSMOM 正確尺度方法論確認（E1 daily-LB 尺度錯置修正核驗）— PASS / NO-GO-TREND robust

**Trigger**: E1 把上輪 MIT 指出的「daily-lag Ljung-Box 尺度錯置」改為正確尺度 TSMOM 檢定。MIT 為 HAC/leakage/CV 主責，確認方法論 + coherence gate verdict 正確性。read-only，real-PG（ssh trade-core，docker pw 建 DSN）親跑 harness + 獨立 HAC 敏感度 + 33 test。

**Verdict: 全 4 項 PASS，NO-GO-TREND 方法論 robust，背書 coherence gate 定義 + 孤立-k40 判定。**

**模組**: `helper_scripts/research/multiday_trend_diagnostic/{stats.py,harness.py}`（24 變體 A/B/C/D，daily klines 730d/20 perp）。real-PG run `mit_verify_20260602` verdict=NO-GO-TREND EXIT=0。

**1. HAC lag=k-1（item 1）PASS + bandwidth 接受**: `_newey_west_mean_tstat`（stats.py:395-427）Bartlett 權重 LRV，lag=k-1 正確處理 overlapping returns（逐日滑動 k 日前瞻 = MA(k-1) 結構，autocov 理論上 lag>k-1 消失）。親算 bandwidth 敏感度（real-PG）：k40 naive=9.646 → HAC lag=k-1(39)=**2.715** / 2(k-1)(78)=2.622 / 1.5k(60)=2.620 / Andrews短規則(13)=3.480。**關鍵**：往更長 bandwidth 幾乎不動（2.62 vs 2.72）→ 證 lag=k-1 已捕完重疊自相關，naive 9.65→2.72（3.55x 壓縮）完全合理。短 Andrews rule(13) 反而 under-correct（無視已知 k-1 overlap）→ E1 用 k-1 是對的、且偏保守。**不需改 Andrews 自動選**（k 已知時固定 k-1 比 data-driven 更穩、更可辯護）。

**2. ★ coherence gate（item 2，verdict 決定性）— 明確背書**: `_summarize_tsmom`（harness.py:372-419）gate 依據 = `coherent_positive_momentum` = (≥2 個 k 達 mean>0 且 HAC|t|≥2) **且** (無任一 k 顯著反轉 HAC t≤-2 且 mean<0)。real-PG: sig_pos=['k40'], sig_reversal=['k90'], coherent=False → NO-GO-TREND。**MIT 背書理由**：真 TSMOM（MOP 2012）相鄰尺度應 sign-coherent / plateau（單調），不是單尖峰 + 長尺度反轉。孤立 k40(t=2.72) 過 Bonferroni 5-k(2.576) 但 k60 不顯著 + k90 顯著反轉(-2.60, mean -623bps) = 在 N_eff=2.087（PC1=0.687 BTC beta，20 sym 僅 ~2 獨立流）+ 24 變體 multiple-testing 下的雜訊取樣，非結構性 momentum。**「≥2 相鄰 k 顯著正 + 無反轉」是正確、非過嚴的 coherence 定義**；單 k 過 naive-2.0 不可作 verdict。

**3. Bonferroni 雙層正確（不混淆）**: gate 內 Bonferroni 用 `len(evaluated)`=5 k-scales → t_crit=2.576（harness.py:396 查表）= 對 5 個 TSMOM 尺度的 family-wise；verdict 文字另提「K=24」= 24 個 Sharpe 變體的 DSR correction（Phase 2 用，更大、更嚴）。**兩者是不同 family、未被混為一談**——gate 對 k-scale 用 5-Bonferroni（k40 仍勉強過 2.576 故 `significant_positive_ks_bonferroni`=['k40']），但 coherence（孤立+反轉）才是攔截理由，非 Bonferroni。設計正確。

**4. per-symbol LB universe 廣度（item 3）正確植入**: `ljung_box_universe`（stats.py:548）real-PG: n_evaluated=20 / n_positive_autocorr=**0/20** / per_symbol=20 全列 / pooled present / median_rho1=0.017。我上輪代跑的 0/20 已正確植入。(n_significant=2 是 2 symbol LB 顯著但 rho 為負=mean-reversion，非正自相關，與無 trend 一致。) daily-LB 已正確降級為 data_quality 旁證（非 verdict 依據）。

**5. survivorship/PIT/regime（item 4，上輪 PASS）未被破壞**: survivorship_source=`symbol_universe_snapshots.listed_at` PIT；tsmom_significance 要求 entry t **與** forward-end t+k 都已上市（stats.py:484）；leak-free 構造 lookback=ln(C_{t-1}/C_{t-1-k}) 只用 t-1 及更早，forward=ln(C_{t+k}/C_t) 嚴格未來，feature/target 視窗不重疊。daily klines 730d 深度（min 2024-06-02，635-730 row/sym）。regime=rule_based local（禁 HMM）。6 leakage 類型全綠，未回退。

**Step 0 反轉教訓（新）**: 與 56d round 不同——daily 粒度給 1000+ trades，max_effective_n=236.67 ≥ 60 floor（15/24 變體過）→ **binding gate 不再是 sample-size（56d 時 N≈8 是 binding），而是 TSMOM coherence（gate 2）**。即 backfill 已解 power 不足問題，但揭露「即使 power 夠也無 coherent momentum」——比 observe_more 更強的 NO-GO 證據。`_power_caveat` 誠實標 N_eff=2.087 低（high BTC beta）是 binding constraint，更多 crypto history 加 cascade/mean-reversion regime 非正動量 → 建議在現證據關閉 multi-day trend，除非出現結構性更獨立的 universe/instrument。MIT AGREE。

**測試鎖定**: 33/33 pass（含 test_summarize_tsmom_isolated_single_k_is_not_coherent 直接重現 real-PG k40/k90 形態 assert coherent=False；test_tsmom_hac_tstat_below_naive_under_overlap；survivorship excludes pre-listing）。

**方法 lesson**: real-PG harness 親跑（非靜態讀碼）+ 獨立重算 HAC bandwidth 敏感度是本次背書的關鍵——若只讀碼會錯過「往長 bandwidth 不動」這個證 lag=k-1 充分的決定性證據。docker pw 建 DSN 繞過 non-interactive SSH 空 env（PW=$(docker exec trading_postgres printenv POSTGRES_PASSWORD)，不 echo pw）。

**Boundary**: read-only；0 寫 0 schema 0 deploy（psycopg2 readonly session 強制）；artifact 寫 /tmp（非 repo）。findings 直接回 PM（無獨立 report file，per task）。

## 2026-06-03 v110→v111 TODO cleanup 對抗性證偽審計（operator 不信任自我驗證）

**Trigger**: v111 cleanup 把一批項目歸檔「✅ DONE」；operator 要求假設每個 DONE 是假的，用 ground truth (PG/git/disk) 證偽。HEAD `26cd1185`（Linux 親驗一致）。

**5 claim verdict（全部親跑 PG/git/disk 證偽，攻數據品質非存在性）**:
1. **V125 alpha 儲存 = GENUINELY-RESOLVED**：sqlx applied success=t（+V126）；6 表（3 plain ledger + 3 hypertable）親驗存在；**C-3 4 data col (funding_rate/open_interest/buy_ratio/sell_ratio) is_nullable=NO 全部**；chunk=604800s(7d)×3；retention=1095d×3 research + market.klines（恰好對的 job）；compress segmentby=symbol×3。**親跑 NULL INSERT → not_null_violation REJECTED（C-3 runtime fail-closed 實證非僅 DDL 宣稱，已 rollback 0 leak）**。schema 層完全對齊 SQL 定義。
2. **daily-kline backfill = GENUINELY-RESOLVED**：14505 row（精確）/20 sym/timeframe='1d'；0 dup (symbol,ts)；0 NULL-or-zero OHLC；0 OHLC invariant 違反；range 2024-06-02→2026-06-01。**per-symbol 重算對得上：19×730 + POLUSDT 635 = 14505**；POLUSDT 635 起 2024-09-05 = 真實晚上市簽名（MATIC→POL 遷移；stub 會給 730）；所有 sym gap=0（span==count 無內部缺日）；20 sym = universe TOML 精確集合 0 extra。provenance 20 row：observed_rows vs 實際 klines **0 mismatch**（非 stub）；coverage_status 19 pass + 1 partial（=POLUSDT 0.8699，誠實標 partial 不假 pass）；payload_sha256 0 NULL。**minor gap: git_sha 20/20 NULL（provenance lineage to source commit 未捕，非 data break）**。
3. **funding/OI backfill = GENUINELY-RESOLVED**：funding 46539 / OI 348153（精確）；**distinct run_id 各=1（0 orphan/dup run 污染）**；20 sym；run `18b3c2f8` status=accepted window 2024-06-03→2026-06-03。funding 0 NULL；**真實 ± 分佈非 fake-zero（3 exact-zero / 33697 pos / 12839 neg / min -0.01 = Bybit floor / avg +0.0000323）**；OI 0 zero 0 neg。0 funding PK dup；0 large gap（BTC OI >6h / funding >2d）。**OI 重算精確：19×17521 + POLUSDT 15254 = 348153**；POLUSDT funding/OI 起 2024-09-05（晚上市）。**minor gap: funding_interval_minutes 全 NULL（writer 未填，非 data break；funding_rate 值真）**。
4. **Gate-B 24h probe = GENUINELY-RESOLVED（running, capturing）**：PID 2146070 elapsed ~7h49m/24h；ws_control.jsonl **175MB/1.39M 行 last-mod current**（live public WS 真活）；rest_phase_poll 1840 行 + ws_kline 6164 + ws_publictrade 12262 全增長中。**R-0 zero-leak 靜態證**：3 gate_b module 唯一非 stdlib import = csv；0 production import（openclaw_engine/governance/scanner/strategy/intent/decision_lease 命中全在「絕不 import」comment）；0 DB-write surface；0 auth/order surface。**空 stdout log 是預期**（entry 只在 finalize print verdict）。capture_lag 真捕 BPUSDT/SPCXUSDT 但 lag 6.78B/1.06B ms = SLOW_CAPTURE（訂到已交易 symbol，**尚未witness 真 cold PreLaunch→Trading transition** = memory 既載 INCONCLUSIVE/TRANSITION_BUT_NO_CAPTURE 一致）。**「smoke EXIT=0」原 /tmp artifact 已清無佐證，但我親跑 --dry-run 重現 EXIT=0 + INCONCLUSIVE_NO_TRANSITION（強過 stale artifact）**；committed test_gate_b_probe.py 34KB。
5. **CODE-SIMPLIFY P0-P4 = GENUINELY-RESOLVED（targeted）**：5 commit (b3f8a02c/344025f9/0dd055dd/401d7d69/9afb811a) 全 HEAD ancestor subject 對；strategy_ai_routes.py **精確 1541 行**（2552→1541，<2000 cap）；pytest_asyncio 1.3.0 venv 裝；strategy_ai_routes py_compile OK 無 breakage。

**結論：0 項 NOT-RESOLVED，0 項需 reinstate 回 active。** 攻面打不破：dup/NULL/fake-zero/OHLC-invariant/orphan-run/wrong-symbol/date-gap/PK-dup/provenance-stub/C3-runtime-reject/zero-leak-static 全過。唯二 minor provenance-completeness gap（git_sha NULL on klines provenance；funding_interval_minutes NULL）= cosmetic lineage 欠缺非 data-integrity 破口，不影響 PIT 證據可信度。POLUSDT 晚上市簽名在 klines/funding/OI 三處一致 = 最強真實性指紋（stub 不可能複製）。

**教訓（對抗性審計正面案例）**：本次 v111「DONE」聲稱經 ground-truth 全部成立——與多數 audit「代碼審計過度歸因 / commit≠runtime live」相反，此處 commit + runtime + data 三層一致。關鍵證偽手法：(a) per-symbol 重算 14505/348153 對賬而非信 aggregate；(b) POLUSDT 晚上市三表交叉驗（最難偽造）；(c) 親跑 NULL INSERT 測 C-3 runtime reject 而非只讀 DDL is_nullable；(d) 親跑 dry-run 重現 smoke EXIT=0 而非信口頭；(e) 讀 ws_control.jsonl mtime+size 證 WS 真活而非信 pgrep 存在。
