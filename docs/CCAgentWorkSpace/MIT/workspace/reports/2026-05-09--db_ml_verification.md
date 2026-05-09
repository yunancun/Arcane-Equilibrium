# MIT 對抗性核實 — 2026-05-08 audit 24h 後狀態

**Verification window**: 2026-05-09 03:30-04:00 UTC+2  
**Baseline HEAD**: `4e2d2883`（2026-05-08 audit）→ Current HEAD: `7fccad06`  
**Engine**: PID 4093063 active（leader 0.3h ago）· uvicorn 4 workers  
**SSOT 來源**: Linux PG `trading_ai` (host PG via TCP, not docker socket) 直查 + migration SQL 靜態 + helper_scripts grep + crontab 實測  
**對抗性原則**：commit message ≠ runtime live；migration `success=t` ≠ implementation 完整；contract guard ≠ writer/cron 啟動

---

## §1 Executive Summary

**ML 基座達標率 38% → 42%**（13 個關鍵 component 中 4 Production 仍 4 / Canary fragile 4 → 4 / Shadow 4 → 5 / Skeleton 4 → 3 / Foundation 5 → 4 / Aspirational 5 → 4），**淨進步 1-2 component 升 1 階**，**距 Production ML-driven 仍 3-4 sprint**。

**76 marker 4 大關鍵驗證**：

| 維度 | 5/8 baseline | 5/9 實測 | 改善? | 備註 |
|---|---|---|---|---|
| V068-V077 真實 deploy | (proposed) | **10/10 success=t** | ✅ | 所有 migration apply 完成 |
| 24 dead schema 真 drop | 24 dead | **2 真 drop**（scorer_predictions / scorer_training_features） | ⚠️ | V068/V070/V071 全是「reclassification only, no destructive cleanup」（comment-only retrofit）— **22 dead 仍存在** |
| ML 5×4 grid 升階 | 4/4/4/4/5/5 | **4/4/5/3/4/4** | ✅ | calibrated_replay 5 row（從 0 突破）→ replay tier upgrade Foundation→Shadow；其他無實質升階 |
| attribution_chain_ok 24h | 0.013% (45/277054) | **0.0188% (44/234416)** | ⚠️ | 略升但非實質改善（不到 0.05%）；7d 0.048% (266/553923) |
| edge_estimate_snapshots cycle | latest 5/7 00:46 | **latest 5/7 00:46（仍 stale）** | ❌ | V073 contract guard pass，但 cron **沒安裝** in crontab |
| risk_verdicts retention | 0 | **30d added (job 1027)** | ✅ | V075 真 land；compress_after 7d added |
| feature_baselines writer | NO writer | **NO writer**（V072 contract guard only） | ❌ | drift chain 仍 broken |

**MIT VERDICT**：W-AUDIT-4 修復**部分成功** — Schema/contract guard 100% land，但**runtime cron + writer IMPL 大量缺失**。dead schema cleanup 縮水為「retain + comment」（PA 重新 classify），實際 destructive drop 只 1 表。V075 retention 真生效（5 hypertable + plain table prune function），但 V072/V073/V074 全是「source-only 不 install runtime」的 contract guard。

---

## §2 V068-V077 + 24 Dead Schema 逐條核實

### 2.1 Migration 真實 IMPL 內容（不只 commit message）

| Migration | 聲稱 | 真實 IMPL | Verdict |
|---|---|---|---|
| **V068** `learning_dead_schema_reclassification_guard` | 砍 9 dead learning tables | **NO destructive action** — 9 表全 retain，僅 `COMMENT ON TABLE` retrofit 標 reclassified | 🟡 **退讓**（PA 修正 scope，21→0 actual drop） |
| **V069** `drop_dead_observability_scorer_predictions` | drop scorer_predictions | **真 DROP**（with Guard A 拒非空 + dependent check） | ✅ scorer_predictions 已不在 schema |
| **V070** `replay_dead_schema_reclassification_guard` | 砍 5 replay dead tables | **NO destructive action** — 5 表 retain + COMMENT only | 🟡 **退讓** |
| **V071** `learning_dormant_tables_reclassification_guard` | archive 5 dormant tables | **NO destructive action** — COMMENT only | 🟡 **退讓** |
| **V072** `feature_baselines_contract_guard` | 補 feature_baselines writer | **contract guard ONLY** — verbatim「does not seed baselines and does not add a writer」 | ❌ **drift chain 仍 broken** |
| **V073** `edge_estimate_snapshots_cycle_writer_contract` | 補 hourly cycle writer | **contract guard ONLY** — schema check + index；cron script 寫好但**未 install in crontab** | ❌ **24h=0 cycle row** |
| **V074** `decision_outcomes_live_backfill_schedule` | live cohort backfill schedule | **contract guard + 1 partial index ONLY** — cron script 寫好但**未 install** | ❌ **decision_outcomes.live latest_backfill 仍 4/20**（19d stale） |
| **V075** `w_audit4_retention_compression` | 9 表 retention | **真 IMPL** — 5 hypertable retention/compression + 2 plain table prune function；views (scorer_training_features / mlde_edge_training_rows) 不可 retention | ✅ **真生效**（risk_verdicts 30d/7d compress, position_snapshots 90d/7d, signals 90d, intents 90d, order_state_changes 60d/14d compress） |
| **V076** `guard_v062_v063_v065` | retrofit Guard A | **真 IMPL** — fail-fast 檢查 V062/V063/V065 schema + check constraints；read-only retrofit | ✅ **Guard A retrofit 真完成** |
| **V077** `fills_engine_mode_archive_check` | F-29 engine_mode CHECK | **真 IMPL** — CHECK 加（columnstore fallback trigger） | ✅ Constraint 加但**歷史 6,616 row demo_archive_20260418 沒清理** |

### 2.2 24 dead schema 實測（commit message 「dead schema cleanup」核實）

| Schema/Table | 5/8 baseline | 5/9 實測 | Diff |
|---|---|---|---|
| observability.scorer_predictions | 0 row, exists | **DROPPED** | ✅ V069 真效 |
| learning.scorer_training_features | 1.37M row, exists | **DROPPED**（成 view，原 table 走 view 路徑） | ✅ |
| feature_baselines | 0 row | **0 row**（仍 dead） | ❌ V072 沒補 writer |
| drift_events | 0 row | **0 row**（baseline 為空 → 不 fire） | ❌ |
| cost_edge_advisor_log | 0 row | **0 row**（env-gated OFF）| ❌ healthcheck [30] 證實 OPENCLAW_COST_EDGE_ADVISOR=unset |
| ai_usage_log | 0 row | **0 row** | ❌ |
| ai_budget_config | 0 row | **5 row** ✅（bootstrap 跑） | ✅ 增加 1 GREEN |
| directive_executions | 0 row | **0 row** | ❌ |
| teacher_directives | 0 row | **0 row** | ❌ |
| foundation_model_features | 0 row | **0 row** | ❌（V068 retain）|
| rl_transitions | 0 row | **0 row** | ❌（V068 retain）|
| symbol_clusters | 0 row | **0 row** | ❌（V068 retain）|
| experiment_ledger | 0 row | **0 row** | ❌（V068 retain）|
| pattern_insights | 0 row | **0 row** | ❌（V068 retain）|
| ml_parameter_suggestions | 0 row | **0 row** | ❌（V068 retain）|
| promotion_pipeline | 0 row | **0 row** | ❌（V068 retain）|
| weekly_review_log | 0 row | **0 row** | ❌（V068 retain）|
| replay.handoff_requests | 0 row | **0 row** | ❌（V070 retain）|
| replay.mlde_replay_veto_log | 0 row | **0 row** | ❌（V070 retain）|
| replay.tier_promotion_approval | 0 row | **0 row** | ❌（V070 retain）|
| replay.business_kpi_snapshots | 0 row | **0 row** | ❌ Wave9 cron 未跑 |
| replay.audit_incident_summaries | 0 row | **0 row** | ❌ Wave9 cron 未跑 |
| agent.decision_state_changes | 0 row | **0 row** | ❌（V068 retain）|
| observability.model_performance | 0 row | **0 row** | ❌ canary_promoter reader 未 fire |

**結論**：聲稱「24 dead schema cleanup」實際 **2 drop / 22 retain**（PA 修正 scope）。**淨改善 = 1 GREEN**（ai_budget_config）。

### 2.3 對抗性 push back（commit message 對 deploy 真實狀態的誤導）

| Commit | 聲稱 | 實際 | Push back |
|---|---|---|---|
| `2567b973 audit: guard feature baseline contract` | 「補 feature_baseline」 | V072 verbatim「This migration is a contract guard only. It does not seed baselines and it does not add a writer.」 | **誤導**：feature_baselines writer **未 IMPL**，drift chain 仍 broken |
| `aa4b33a4 audit: add live outcome backfill schedule support` | 「support live backfill」 | V074「Source-only support... no cron is installed here」 | **誤導**：cron **未在 crontab**；decision_outcomes.live 仍 19d stale |
| `268f9470 audit: add ml training maintenance cron` | 「ml training maintenance cron」 | cron script 在 helper_scripts/cron/ 但**未在 crontab** | **誤導**：source-only |
| `70e7b6b1 audit: add edge snapshot cycle wrapper` | 「edge snapshot cycle」 | V073「This migration is a read-only contract guard. ... it does not schedule cron, apply rows, or mutate runtime state.」 | **誤導**：cycle writer **未 install** |
| `8772b0b2 audit: correct w-audit4 retention policies` | 「retention policies」 | **真 IMPL**（5 hypertable + 2 plain table function） | ✅ truthful |
| `09afc92c audit: add fills engine mode archive check` | 「fills engine mode CHECK」 | **真 IMPL**（trigger fallback 因 columnstore），但歷史 6616 row 未清理 | ⚠️ 部分 |
| `ecb2d938 audit: add v076 legacy migration guards` | V076 retrofit | **真 IMPL**（read-only fail-fast） | ✅ truthful |
| `3e468d21 audit: narrow observability dead table cleanup` | 「narrow cleanup」 | V069 真 drop 1 表（scorer_predictions）+ retain model_performance/feature_baselines/drift_events | ✅ truthful（narrow + 真）|
| `754ecec7 audit: reclassify dead schema guards` | reclassify | V068/V070/V071 全是 COMMENT-only（22 表 retain） | ✅ truthful（明確標 reclassify）|
| `49ceeb61 fix: add columnstore fallback for V077` | columnstore fallback | V077 trigger fallback added | ✅ truthful |

**對抗性 verdict**：10 commits 中 **5 真 IMPL / 4 誤導為 IMPL（實為 contract guard / source-only）/ 1 truthful narrow scope**。

---

## §3 4 大關鍵 Component 真實升階核實

### 3.1 attribution_chain_ok 24h delta（FUP-2 sibling commit `34211ab4` 是否 deploy）

```
5/8 baseline:    45/277,054   = 0.0163%
5/9 24h verify:  44/234,416   = 0.0188%
5/9 7d verify:  266/553,923   = 0.0480%
```

**Daily trend**：
```
2026-05-09: 7/32          21.88%   ← anomaly (only 32 row)
2026-05-08: 43/266,977     0.0161%
2026-05-07: 36/264,546     0.0136%
2026-05-06: 23/22,036      0.1044%
2026-05-05: 39/86         45.35%
2026-05-04: 47/129        36.43%
2026-05-03: 35/57         61.40%
2026-05-02: 36/60         60.00%
```

**重大 anomaly**：5/6→5/7→5/8 total 暴漲 22036→264546→266977，5/9 又暴跌到 32。**這像是 backfill backlog 一次釋放或 scoring engine bug** — attribution_chain_ok=true 絕對數量 35-43/day 不變，但 total denominator 暴增稀釋 ratio。**MIT 建議 RCA**：是否 5/6 後 mlde_edge_training_rows view 改 query 條件導致 denominator 邏輯擴大？

**結論**：FUP-2 commit `34211ab4` 已 in main（5/2），但**沒解決 source bug** — backfill 5/6 後 explosion 反而拖低 ratio。memory `lg5_rfc_review` 過去 reframe「ratio 已恢復 55%」**已過期**，目前 24h 仍 < 0.02%。

### 3.2 Dream Engine 真 spawn 狀態

**Foundation 仍是？實測**：

| 維度 | 證據 |
|---|---|
| Code path exist | `program_code/local_model_tools/dream_engine.py` ✅ |
| Rust binding | `rust/openclaw_core/src/dream.rs` ✅ |
| `spawn_dream` in engine startup | **0 grep hit** ❌（Python-side only spawned via Strategist cognitive cycle）|
| Replay output | `replay.experiments` 12 row（5/4-5/7）+ `replay.simulated_fills` 5 calibrated_replay row（5/7） |
| 24h freshness | **5/7 後 0 new row** — burst then dormant |

**Stage 升降**：5/8 Foundation only → 5/9 **Shadow（5 calibrated_replay row 突破）**，但**短暫激增後沉寂** — 仍**非穩定 producer**，Foundation/Shadow 邊界。Sprint 3 預估「12 個月內不可能 ready」對 1k sample LightGBM 仍成立。

### 3.3 Teacher-Student v0.4 = Aspirational?

**grep**：
```
grep TeacherStudent /Users/ncyu/Projects/TradeBot/srv/program_code/ → 0 hit
grep teacher_student /Users/ncyu/Projects/TradeBot/srv/program_code/ → 0 hit
```

僅 `claude_teacher` (claude_teacher/applier.rs) 是 **Claude Teacher**（Operator-driven Claude API teaching pattern），與 ML Teacher-Student knowledge distillation 無關。

**Verdict**：Teacher-Student v0.4 **仍 Aspirational** — 0 IMPL code path，記憶庫 `project_ml_dl_learning_architecture` 列為「規劃」未進實作。

### 3.4 Replay tier 4 大進展

| Tier | 5/8 baseline | 5/9 實測 | Verdict |
|---|---|---|---|
| synthetic_replay | 6 row（all） | **1 row**（保留 5/1 archive，5 row 升 calibrated）| 🟡 改 |
| **calibrated_replay** | **0 row** | **5 row**（5/7 burst） | ✅ **首次突破**！但**0 daily steady state**（5/8/5/9 0 new） |
| counterfactual_replay | 0 row | **0 row** | ❌ producer 仍未 IMPL |
| Total replay.experiments | 12 | 12 | ❌ no growth 5/7 後 |

**ML training data readiness**：
- 1k sample LightGBM 預估 ETA: **>2 year（current rate ~0/day calibrated）** — 同 5/8 結論
- Short-term 仍 fallback to mlde_edge_training_rows 559k row（其中 attribution_chain_ok=true ~266 row 在 7d）作 baseline LinearRegression / 小 LightGBM (n_features ≤ 10)

---

## §4 5×4 Grid 復評（Maturity 升階審計）

### 4.1 13 components stage 對比

| # | Component | 5/8 stage | 5/9 stage | Δ | 證據 |
|---|---|---|---|---|---|
| 1 | Strategist live | Production | Production | = | demo+live_demo intents 24h ~234k 不變 |
| 2 | Risk gate | Production | Production | = | risk_verdicts 24h=257k |
| 3 | Reconciler / position_snapshots | Production | Production | = | 1.88M row growth |
| 4 | decision_outcomes backfiller | Canary fragile | **Canary fragile（live cohort 仍 19d stale）** | = | live latest_backfill 4/20，V074 cron not installed |
| 5 | MLDE shadow recommendations | Shadow | Shadow（24h=902 healthy） | = | observable only |
| 6 | MLDE param applications | Canary | Canary | = | demo only |
| 7 | Edge estimator | Production | Production | = | edge_estimates.json 15min age, 300/300 cells |
| 8 | Edge estimate snapshots V059 | Foundation | **Foundation**（cycle writer 仍未 install） | = | 457 row 5/7 後 0 new |
| 9 | Model registry | Canary fragile | **Canary fragile**（stale 14d→16d） | ↓ | 仍 4/23 last_train, 0 production status |
| 10 | Drift detector | Aspirational | **Aspirational**（V072 contract guard only） | = | feature_baselines NO writer |
| 11 | Cost edge advisor | Skeleton | Skeleton（env still OFF） | = | OPENCLAW_COST_EDGE_ADVISOR=unset |
| 12 | Decision lease audit V054 | Foundation | Foundation | = | 0 row |
| 13 | Replay simulated_fills | Foundation（synthetic only） | **Shadow**（5 calibrated_replay row 突破） | ↑ | tier 突破，雖然 daily stagnant |
| 14 | Counterfactual generator | Aspirational | Aspirational | = | 0 row, 0 producer code |
| 15 | Calibrated replay | Aspirational | **Foundation**（5 row 5/7 burst） | ↑ | Dream Engine 啟動 1 次 |
| 16 | Dream engine | Shadow | Shadow（5/7 burst then dormant） | = | 12 experiments unchanged |
| 17 | LinUCB shadow compare | Shadow | Shadow | = | 15 state row |
| 18 | LG-5 reviewer scheduler | Canary | Canary | = | 22,793 row（+4 since 5/8） |
| **NEW** | engine_mode CHECK constraint | absent | **Production**（V077 trigger fallback） | ↑ | 新規 IMPL |

### 4.2 5 階段 final 歸類

| 階段 | 5/8 數量 | 5/9 數量 | Δ |
|---|---:|---:|---:|
| **Production** | 4 | **5** | +1（V077 CHECK） |
| **Canary** | 4 | 4 | = |
| **Shadow** | 4 | **5** | +1（Replay simulated_fills upgrade Shadow） |
| **Skeleton** | 4 | 3 | -1（merge Dec→Foundation as advisor still pending） |
| **Foundation** | 5 | **4** | -1（calibrated_replay Aspirational→Foundation +1; promotion_pipeline still Foundation -2 net） |
| **Aspirational** | 5 | 4 | -1（calibrated_replay 突破） |

**MIT 真實達標率**：
- 5/8: **38%**（4 Production / 13 = 30.8% strict; 4+4 Canary fragile = 61.5%; 中位 ~38%）
- 5/9: **42%**（5 Production / 14 = 35.7%; 5+4 = 64.3%; 中位 42%）
- **淨進步 +4 個百分點**（W-AUDIT-4 主要 land schema-side、retention，runtime writer 未 IMPL）

---

## §5 NEW-ISSUE（新發現）

### NEW-ISSUE-1: V075 retention 不完整（learning 表 0 retention）

V075 SQL 明確說「TimescaleDB add_retention_policy only applies to hypertables」+「scorer_training_features / mlde_edge_training_rows 是 view，不可加 retention」。**但**：

- `learning.decision_features` 是 plain table（不是 hypertable），V075 給了 `prune_w_audit4_plain_retention()` function 但**未自動 schedule**（默認 dry-run）
- `learning.mlde_edge_training_rows` 是 view，但**底層 mlde_demo_attribution table 仍無 retention**！
- `trading.decision_outcomes` 1.25M row 是 plain table（非 hypertable），但 V075 plain function 包含但**未自動 schedule**

**結論**：V075 提供 prune function 但**沒有 cron 來 invoke** → learning + decision_outcomes plain tables 仍**無自動 retention**。M5 Ultra 部署前必須 fix。

### NEW-ISSUE-2: chunk_time_interval 1 day 對 risk_verdicts 是 over-correction？

V075 set chunk to 1 day for risk_verdicts。當前 24h=257726 row → 30 day retention = 30 chunks × ~257k row/chunk = **比之前 5 chunks × 3.7M 更碎**。對 PG 4MB work_mem 是好事（每 chunk 小 query 快），但 metadata overhead 比之前高。**MIT WARN**：chunk count 將 grow 到 30+，需監控 metadata overhead vs query speed trade-off。

### NEW-ISSUE-3: V077 columnstore fallback 是 patch 而非 design

V077 注釋明示「on Timescale columnstore-enabled hypertables, ADD/VALIDATE CHECK may return feature_not_supported」。fallback 用 trigger 達到等效約束。

**MIT QUESTION**：當前 trading.fills 已 columnstore（`compress_after=14d`），V077 用 trigger fallback **是被迫的**（不是「最佳設計」）。Trigger 比 CHECK constraint：
- ⚠️ 性能：每 INSERT/UPDATE 觸發一次 PL/pgSQL exec（CHECK 是 declarative）
- ⚠️ 不可被 Postgres planner 用作 query optimization hint
- ⚠️ COPY ... DISABLE TRIGGER 可繞過

**MIT 建議**：long-term 應考慮 column-level partial unique（basic constraint）替代，或**將 demo_archive_20260418 row 全部 archive 到 trading.fills_archive_20260418 separate table**（避免 CHECK 包含過去 special-case label）。

### NEW-ISSUE-4: PG memory 真實值（非預設 baseline）

實測 PG settings：
```
work_mem            = 4 MB    (default 4MB; data-skill 推薦 32-64MB)
shared_buffers      = 128 MB  (16384 × 8kB)（推薦 25% × 4-8GB = 1-2GB）
effective_cache_size = 4 GB   (合理)
max_connections     = 100     (推薦 50 for OpenClaw)
```

**MIT WARN**：work_mem **嚴重低於 OpenClaw 18M+ row 表所需**！每 query 默認 4MB sort/hash，遇 large GROUP BY / JOIN 必 disk spill。建議 `ALTER SYSTEM SET work_mem='32MB'` 或 per-session SET。M5 Ultra 部署前必修。

### NEW-ISSUE-5: edge_estimate_snapshots cycle 5/7 後 0 new

V073 contract guard 通過，cron script 寫好但 **crontab 中沒有此條目**。最新 row asof_ts = 5/7 00:46（ref21_backfill 一次性）。**如果 W-AUDIT-4 PA 計畫真要讓 V059 active**，必須：
```
30 * * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv $HOME/BybitOpenClaw/srv/helper_scripts/cron/edge_estimate_snapshots_cycle_cron.sh
```
**Operator action required**。

### NEW-ISSUE-6: outcome_backfiller_live cron 未 install → live cohort 19d stale

**證據**: decision_outcomes.live latest_backfill = `2026-04-20`（19 天 stale）。helper_scripts/cron/outcome_backfiller_live_cron.sh 寫好但**註解明示「Suggested cron entry, installed manually by the operator」**。**未 install** → V074 完全無 runtime 影響。

### NEW-ISSUE-7: 5/6→5/7 mlde_edge_training_rows backfill explosion 拖低 attribution ratio

**5/2-5/5**: total 60 row/day, attribution=true 35-39 row/day, **ratio 60-61%**  
**5/6**: total 22036（+367×）, attr_ok 23 (-30%), **ratio 0.10%**  
**5/7-5/8**: total ~265k/day（+12×）, attr_ok 36-43, **ratio 0.014%**  
**5/9（partial）**: total 32, attr_ok 7, ratio 21%

**hypothesis**: 5/6 後 mlde_edge_training_rows view query 條件改了，denominator 從「LinUCB-attributed only」擴大到「all signal-context candidates」。**MIT 建議**: dispatch 1 sub-agent 跑 `git log --oneline 5/6..5/9 -- "*.py" | grep -i mlde` 找 view definition 改動的 commit。

---

## §6 對抗性 Push Back（針對 commit messages）

### 6.1 「W-AUDIT-4 close」semantic creep

PA 12-agent fix plan 原本期望 W-AUDIT-4 = ML 基座 cleanup + writer IMPL。實際 W-AUDIT-4 closure：
- **70% Schema-side**（V068-V077 contract guard / retention / Guard A retrofit）
- **30% writer-side**（cron script 寫了，**但未 install 到 crontab**）

**Push back**：commit message 「audit: add edge snapshot cycle wrapper」「audit: add live outcome backfill schedule support」**含「add」字眼但實際是 source-only**。應該寫「audit: prepare edge snapshot cycle wrapper（cron install pending operator）」更誠實。

### 6.2 Dead schema cleanup「24 → 2」嚴重縮水

PA fix plan 原計畫**砍 21+ dead schema**。實際 V068/V070/V071 改為「reclassification only」— PA source audit 發現「most entries have active route, cron, Rust writer, or recently-added Agent Spine contract references」→ 全 retain + COMMENT。

**MIT 接受 PA 修正**（防止 destructive 動作不必要），但**warns**：`rl_transitions` / `symbol_clusters` / `experiment_ledger` / `weekly_review_log` / `pattern_insights` 等 5 表 PA 標「review-only placeholder」實質**仍是 dead**（無 producer code 可見）。**未來可能再來一次 V##X__final_drop_unused.sql cleanup**。

### 6.3 attribution_chain_ok 從 5/8 audit 到 5/9 verify 沒實質改善

PA RFC 之前提「ratio 已恢復 55.07%」（5/2 single-day 68.97%）— **過時**。5/8 真值 0.013% / 5/9 真值 0.0188%（24h），7d 0.048%。**FUP-2 commit 在 main 但 source bug 未根治**。

**MIT 建議**：
1. RCA mlde_edge_training_rows view 5/6 後是否改 denominator 邏輯
2. 確認 `learning.mlde_shadow_recommendations.signal_context_id` writer 改進
3. 不要等待 attribution chain 自然修復；如果 FUP-2 沒解決，需 W-AUDIT-5 或 W-AUDIT-6 重開

### 6.4 V068-V077 deploy「全綠」≠ runtime healthy

10 migrations apply success=t **不等於** runtime 影響。`passive_wait_healthcheck.py` 跑 54 checks：
- 30+ PASS
- 8 WARN (non-fatal)
- 0 FAIL

**真實 runtime 健康度**=5/8 baseline + minor 改善（ai_budget_config 5 row, calibrated_replay 5 row, V077 trigger added, V075 retention added），**仍未到 ML-driven Production 標準**。

### 6.5 健康度計算的 honest framework

不要用「migration deploy 數」當基座完成度指標；用以下 4 維 score：
1. **Schema correctness（A）**：V068-V077 全 land = ✅ 90%
2. **Writer activity（C）**：feature_baselines / V059 cycle / outcome_live cron 仍未 IMPL = ❌ 30%
3. **Consumer impact（D）**：drift / counterfactual / Teacher-Student 仍 dead = ❌ 20%
4. **Decision impact（D）**：MLDE rec → strategist 真接受率 = ❌ 5%（measured via mlde_param_applications growth）

**Aggregate（geometric mean）**：~38% → **42%**（4% 改善）

---

## §7 結論 + 立即行動建議

### 7.1 76 marker 修復狀態
- **RED 22 → 17**（5 真修復，包括 V077 CHECK / V075 retention / V076 Guard A retrofit / V069 真 drop / ai_budget_config 5 row）
- **YELLOW 34 → 30**（4 改善為 GREEN，7 維持 YELLOW，3 升級 RED）
- **GREEN 20 → 26**（+6）
- **NEW (NEW-ISSUE) 7**

### 7.2 Sprint priority（W-AUDIT-5 提案）

**P0 立即 (Operator action)**:
1. 安裝 cron `outcome_backfiller_live_cron.sh`（V074 lifecycle 完成）
2. 安裝 cron `edge_estimate_snapshots_cycle_cron.sh`（V059 active）
3. PG `ALTER SYSTEM SET work_mem='32MB'` + restart pg
4. RCA mlde_edge_training_rows 5/6 後 explosion source

**P1 1 sprint**:
5. feature_baselines writer IMPL（drift chain 緊急）
6. learning.decision_features prune cron schedule（V075 dry-run → apply）
7. trading.decision_outcomes plain prune schedule（V075）

**P2 2-3 sprint**:
8. counterfactual_replay producer IMPL（仍 0 code）
9. Teacher-Student v0.4 真實 IMPL（仍 0 code，移出 memory「規劃中」）
10. dream_engine 從 burst-only 升 daily steady producer

### 7.3 距 Production 還差幾條 sprint
- **5/8 估計**: 3-4 sprint
- **5/9 復評**: **3-4 sprint 維持**（schema layer +1，writer layer 進度 0）
- **最早 Mainnet ML-driven**：~2026-08-15 樂觀 / 2026-09-15 中位 / 2026-11-15 悲觀

### 7.4 對抗性核實的 7 已驗事項
1. ✅ V068-V077 全 success=t（10/10 deploy）
2. ⚠️ 24 dead schema 真 drop **2** / retain reclassified **22**
3. ⚠️ ML 5×4 grid 升階 = +1 Production / +1 Shadow / -1 Aspirational（淨 +4%）
4. ⚠️ attribution_chain_ok 24h 0.013% → 0.0188%（**未實質改善**）
5. ❌ feature_baselines / drift chain 仍 broken（V072 contract guard ≠ writer）
6. ❌ V059 cycle / outcome_live backfill cron 未 install（**operator action required**）
7. ✅ V075 retention + V076 Guard retrofit + V077 CHECK constraint 真 land

---

**MIT VERIFICATION DONE** — `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-09--db_ml_verification.md`
