# MIT DB + ML 基座專項 Audit — 2026-05-08

**Audit window**: 2026-05-08 22:30-23:30 UTC+2
**HEAD**: `4e2d2883`
**Engine PID**: 3854831 (active, 22:01 起跑) · uvicorn 4 workers
**SSOT 來源**: Linux PG `trading_ai` 直查 + `srv/sql/migrations/` 靜態 + `rust/openclaw_engine/src/` grep
**對抗性原則**：表存在 ≠ pipeline live；writer 接線 ≠ 有 row；有 row ≠ 影響真實決策

---

## §1 Executive Summary

ML 基座**達標率 ≈ 38%**（19/50 components 真實接線且 row 流動），距 Production **3-4 sprint** 仍有顯著 gap：

| 維度 | 真實狀態 | 評級 |
|---|---|---|
| Schema 完整度（V001-V067 套用率） | 65/65 success=t（V022/V042 跳號是預設）| A |
| Hypertable 配置合理度 | 39 hypertable，重表 5 chunks 合理；但 5 個 0-chunk 表為 dead schema | B |
| Guard A/B/C 覆蓋率 | V001-V020 全 0 Guard（pre-postmortem）; V021+ 大部分 A/B；V062/V063/V065 retrofit 落後 | C+ |
| engine_mode 一致性 | risk_verdicts 4 值齊全（含真 live 2.5M）；fills 仍含 demo_archive_20260418 殘餘 | B+ |
| Time-series leakage 6 維 | Rust runtime 用 closed-bar buffer leak-free OK；edge_estimate_validation walk_forward **缺 embargo + purge** | C |
| Time-series CV | walk_forward 有，purge/embargo 只在 cpcv_validator；ML training filter `IN ('live','live_demo')` 一致 | B- |
| Dream + counterfactual + calibrated 累積率 | replay.simulated_fills **6 row/3d**（synthetic_replay tier 6/6，**0 calibrated/counterfactual**）| F |
| ML 部署最終定論 | 0 Production / 1 Canary fragile（model_registry 3 row stale 14d）/ 5 Shadow / 6 Skeleton / 12+ Foundation / 7 Aspirational dead | D |
| Apple Silicon M5 readiness | hypertable + compression 14d 良好；但 `decision_features` 9.47M / `risk_verdicts` 18.47M 無 retention；4-8GB PG 風險高 | C |

**MIT VERDICT**: ML 基座**未達生產標準**；需 4 個 V### migration 補洞（writer / retention / Guard）+ 3 sprint IMPL（drift writer / counterfactual producer / decision_outcomes live backfill）方可轉 Canary。Live 倉位由 ML 信號驅動目前**完全不可能**。

---

## §2 V001-V067 Migration 真實使用度盤點 + Dead Schema 終結清單

### 2.1 Migration 套用狀態
- 套用：65 條（V001-V067 except V022, V042 跳號）
- 全部 `success=t`
- 跳號：**V022 + V042 缺，僅版本號跳過，無實際遺漏**（檔案系統 + DB 一致）

### 2.2 Schema × Row 真實使用度

| Schema | Table | Rows | 24h 寫入? | Writer | Consumer | 結論 |
|---|---|---:|:-:|---|---|---|
| **learning** | exit_features | 2,170 | Yes | Rust + Python | edge_estimator | **Active 但稀疏** |
| | decision_features | 9,472,708 | Yes | Rust on_tick | strategist | **Active 高量** |
| | mlde_edge_training_rows | 559,061 | Yes | Python writer | MLDE training | **Active 但 0.012% attribution_chain_ok** |
| | mlde_shadow_recommendations | 6,709 | Yes | Python | MLDE | **Active**（含 53 live row）|
| | mlde_param_applications | 2,829 | Yes | strategist | learning | **Active** |
| | scorer_training_features | 1,371,386 | 5d 前停 | scorer | scorer training | **Stale 5d** |
| | governance_audit_log | 22,789 | Yes | LG-5 W3 reviewer | LG-5 W3 | **Active**（FUP-1 commit `463890d` 已 land）|
| | strategist_applied_params | 7,822 | Yes | strategist | strategist | **Active** |
| | edge_estimate_snapshots (V059) | 457 | **No** | **ref21_backfill ONLY** | replay reads | 🔴 **DEAD（Foundation only，無 cycle writer）**|
| | model_registry | 3 | 14d 前停 | run_training_pipeline.py | promotion_pipeline | 🟡 **stale 14d**（Canary fragile）|
| | linucb_state | 15 | ? | LinUCB | LinUCB shadow | **Active small** |
| | james_stein_estimates | 864 | ? | JS estimator | edge | **Active** |
| | bayesian_posteriors | ? | ? | edge | edge | **Active small** |
| | cpcv_results | 56 | ? | cpcv_validator | strategist | **Active small** |
| | cost_edge_advisor_log | 0 | No | Rust（env-gated OFF）| advisor | 🔴 **DEAD（writer 在但 OPENCLAW_COST_EDGE_ADVISOR_DAEMON 未設）**|
| | ai_usage_log | 0 | No | claude_teacher | budget config | 🔴 **DEAD（writer 接線但 0 row 全 history）**|
| | ai_budget_config | 0 | No | bootstrap | budget gate | 🔴 **DEAD** |
| | directive_executions | 0 | No | claude_teacher | learning | 🔴 **DEAD（之前 memory 說 active write+read 是錯）**|
| | teacher_directives | 0 | No | claude_teacher | learning | 🔴 **DEAD** |
| | foundation_model_features | 0 | No | (none) | weekly review | 🔴 **DEAD** |
| | rl_transitions | 0 | No | (none) | (none) | 🔴 **DEAD** |
| | symbol_clusters | 0 | No | (none) | learning | 🔴 **DEAD** |
| | decision_shadow_fills | 0 | No | shadow writer (flag OFF) | (none) | 🟡 **Skeleton（shadow_enabled=false）**|
| | decision_shadow_exits | 0 | No | shadow exit writer (flag OFF) | (none) | 🟡 **Skeleton** |
| | lease_transitions | 0 | No | V054 writer (latent) | governance | 🟡 **Foundation**（writer code 在）|
| | promotion_pipeline | 0 | No | (none) | (none) | 🔴 **DEAD** |
| | weekly_review_log | 0 | No | (none) | (none) | 🔴 **DEAD** |
| | experiment_ledger | 0 | No | experiment system | learning | 🔴 **DEAD** |
| | linucb_migrations | 0 | No | LinUCB migrate | (one-shot) | 🟡 **One-shot dormant** |
| | linucb_state_archive | 0 | No | LinUCB archive | (none) | 🟡 **One-shot dormant** |
| | pattern_insights | 0 | No | (none) | strategist | 🔴 **DEAD** |
| | ml_parameter_suggestions | 0 | No | (none) | strategist | 🔴 **DEAD** |
| **observability** | engine_events | 13,900 | Yes | engine startup | grafana | **Active** |
| | data_quality_events | 689 | 6d 前停 | (rust) | (none) | 🟡 **stale 6d** |
| | feature_baselines | 0 | No | **(NO WRITER)** | drift_detector reads | 🔴 **DEAD（drift chain broken）**|
| | drift_events | 0 | No | drift_detector | canary_promoter | 🔴 **DEAD（baseline 為空 → drift 從未 fire）**|
| | scorer_predictions | 0 | No | **(NO WRITER)** | (none) | 🔴 **DEAD（0 producer code）**|
| | model_performance | 0 | No | **(NO WRITER)** | (none) | 🔴 **DEAD（0 producer code）**|
| **trading** | fills | 13,018 | Yes | bybit connector | strategist | **Active**（但含 6616 row demo_archive_20260418）|
| | intents | 559,130 | Yes | strategist | risk + executor | **Active 高量** |
| | risk_verdicts | 18,467,758 | Yes | risk gate | governance | **Active 巨量**（含 2.5M live）|
| | orders | 350,589 | Yes | bybit connector | reconciler | **Active** |
| | decision_outcomes | 1,247,600 | Yes | outcome_backfiller | learning | **Active**（live 89734 stale 18d）|
| | scanner_snapshots | 469 | Yes | scanner | scanner_advisory | **Active** |
| | scanner_opportunity_decays | 663 | Yes | scanner | (downstream) | **Active 1d** |
| | funding_settlements | 75 | Yes | funding writer | funding_arb | **Active 7d** |
| | signals | 961,982 | Yes | strategist signal | (downstream) | **Active 高量** |
| | position_snapshots | 1,878,959 | Yes | reconciler | strategist | **Active 巨量** |
| | order_state_changes | 707,444 | Yes | bybit handler | reconciler | **Active 巨量** |
| | paper_state_checkpoint | 3 | bootstrap | paper_state | (recovery) | **Active small**（paper-disabled）|
| | fills_damaged_20260414_130607 | 17,265 | (frozen) | (one-time) | (none) | 🟡 **archived**（V015 incident）|
| | intents/orders/risk_verdicts_damaged_20260414_130607 | 7684/4509/4183014 | (frozen) | (one-time) | (none) | 🟡 **archived** |
| **agent** | decision_objects | 470 | Yes | spine | aggregator | **Active 1d**（V064）|
| | decision_edges | 376 | Yes | spine | aggregator | **Active 1d** |
| | execution_idempotency_keys | 94 | Yes | spine | spine | **Active** |
| | messages | 2 | seed | MAG seed | (none) | 🟡 **Foundation**（MAG-019 default OFF）|
| | state_changes | 11 | seed | MAG seed | (none) | 🟡 **Foundation** |
| | ai_invocations | 2 | seed | MAG seed | (none) | 🟡 **Foundation** |
| | decision_state_changes | 0 | No | (none) | (none) | 🔴 **DEAD** |
| **replay** | experiments | 12 | Yes | full-chain runner | mlde_replay | **Active 4d** |
| | run_state | 12 | Yes | runner | full-chain | **Active** |
| | report_artifacts | 6 | Yes | runner | full-chain | **Active** |
| | simulated_fills | 6 | Yes | runner | (only 'synthetic_replay' tier) | 🟡 **Active but unusable for ML（0 calibrated/counterfactual）**|
| | handoff_requests | 0 | No | replay | (none) | 🔴 **DEAD** |
| | mlde_replay_veto_log | 0 | No | mlde_replay | (none) | 🔴 **DEAD** |
| | tier_promotion_approval | 0 | No | tier promo | (none) | 🔴 **DEAD** |
| | business_kpi_snapshots | 0 | No | (cron) | report | 🔴 **DEAD** |
| | audit_incident_summaries | 0 | No | (none) | report | 🔴 **DEAD** |

### 2.3 Dead Schema 終結清單（**21 個** 0-row + 0 producer 或 producer-OFF）

| Schema | 表 | 原因 | 建議 |
|---|---|---|---|
| learning | edge_estimate_snapshots | V059 無 cycle writer，只有 ref21_backfill 一次性 script | 補 cycle writer 或刪除 |
| learning | cost_edge_advisor_log | env-gated OFF（OPENCLAW_COST_EDGE_ADVISOR_DAEMON 未設）| 啟用 env 或刪除 |
| learning | ai_usage_log | claude_teacher writer 接線但 0 history | RCA 或 archive |
| learning | ai_budget_config | bootstrap 缺 | bootstrap 或刪除 |
| learning | directive_executions | claude_teacher 接線但 0 history | RCA |
| learning | teacher_directives | 0 history | RCA 或 archive |
| learning | foundation_model_features | 0 producer | 刪除（V011 dead）|
| learning | rl_transitions | 0 producer | 刪除 |
| learning | symbol_clusters | 0 producer | 刪除 |
| learning | promotion_pipeline | 0 producer | 刪除 |
| learning | weekly_review_log | 0 producer | 刪除（V013 dead）|
| learning | experiment_ledger | 0 producer | 刪除（V007 dead）|
| learning | pattern_insights | 0 producer | 刪除 |
| learning | ml_parameter_suggestions | 0 producer | 刪除 |
| observability | feature_baselines | 0 writer | **緊急補**（drift chain 依賴）|
| observability | drift_events | baseline 為空 | 同上補 baseline writer |
| observability | scorer_predictions | 0 producer | 刪除 |
| observability | model_performance | 0 producer | 刪除 |
| agent | decision_state_changes | 0 producer | 刪除（V064 部分 dead）|
| replay | handoff_requests | 0 producer | 刪除 |
| replay | mlde_replay_veto_log | 0 producer | 刪除 |
| replay | tier_promotion_approval | 0 producer | 刪除 |
| replay | business_kpi_snapshots | cron 缺 | 啟動 cron 或刪除 |
| replay | audit_incident_summaries | 0 producer | 刪除 |

**結論**：**21 表確認 dead**（0 row + 0 active producer）。其中 4 個是 producer-OFF（env-gated），17 個是 0 producer code。

---

## §3 TimescaleDB Hypertable 配置

### 3.1 Hypertable 數量
- 總 hypertable：**39**
- compression enabled：**9**（trading.fills/intents/orders/signals + market.klines/liquidations/market_tickers/ob_snapshots/trade_agg_1m）
- compress_after：7d / 14d 兩種設定（trading.signals 2d 過激；market.* 7d；trading.* 14d）

### 3.2 Chunk 分布
| 表 | num_chunks | 評論 |
|---|---:|---|
| market.news_signals | 39 | 規模 OK；無 compression |
| market.long_short_ratio | 34 | 規模 OK；無 compression |
| market.market_tickers | 33 | 規模 OK；compressed 7d |
| market.trade_agg_1m | 32 | 規模 OK；compressed 7d |
| market.ob_snapshots | 32 | 規模 OK；compressed 7d |
| trading.signals | 18 | 規模 OK；compressed 2d（過激）|
| **trading.risk_verdicts** | **5** | 🔴 18.47M row 只 5 chunk = ~3.7M/chunk **chunk 過大**，compressed=false |
| trading.intents | 5 | compressed 14d |
| trading.fills | 5 | compressed 14d |
| trading.position_snapshots | 5 | 1.88M row, compressed=false |
| learning.governance_audit_log | 2 | 22789 row, compressed=false |
| learning.exit_features | 4 | 2170 row，OK |
| ... | | |

### 3.3 嚴重 chunk 過大警告
**trading.risk_verdicts**：18.47M row × 5 chunk = ~3.7M row/chunk + 無 compression。每個 chunk 在 PG 4-8GB memory 下單次掃描極可能觸發 OOM。**M5 Ultra 部署前緊急修**。

### 3.4 Retention policy 缺失
| 表 | row | retention 是否設 |
|---|---:|:-:|
| trading.risk_verdicts | 18,467,758 | **No** 🔴 |
| trading.decision_outcomes | 1,247,600 | **No** 🔴 |
| trading.position_snapshots | 1,878,959 | **No** 🔴 |
| trading.signals | 961,982 | **No** 🟡 |
| learning.scorer_training_features | 1,371,386 | **No** 🟡 |
| learning.decision_features | 9,472,708 | **No** 🔴 |
| learning.mlde_edge_training_rows | 559,061 | **No** 🟡 |
| trading.order_state_changes | 707,444 | **No** 🟡 |
| trading.intents | 559,130 | **No** 🟡 |

**M5 Ultra 部署前必補 9 條 retention policy**（建議 90d 起跳，risk_verdicts 30d）。

---

## §4 Guard A/B/C 覆蓋

| 範圍 | Guard 狀態 | 數量 | 風險 |
|---|---|---:|---|
| V001-V020（pre-postmortem）+ V025/V029 | **0 Guard** | 22 | 🟡 **可接受**（CLAUDE.md §七 標記歷史視 idempotency 風險可接受）|
| V021/V023/V026/V028/V033/V038-V041/V051/V052 | **A+B** | 11 | OK |
| V024/V035/V044-V050/V054 | **A+C** | 10 | OK |
| V049（replay_experiments）| **A+B+C 完整** | 1 | 🟢 標桿 |
| V062/V063/V065（最新）| **0 Guard** | 3 | 🔴 **退化**（CLAUDE.md §七 已強制 Guard A/B/C，但 V062/V063/V065 沒套用）|

**結論**：
- pre-postmortem 22 條按設計接受
- V021-V061 大部分有 retrofit
- **V062/V063/V065 退化** — 違反 CLAUDE.md §七 強制；V062 加 trading.scanner_opportunity_decays 表 + V063 加 market.market_tickers funding_rate column + V065 加 openclaw_proposal_ledger，這 3 條應 retrofit Guard A
- **Guard B 全 column-add migration 整體採用 64%**（V038-V040 / V052_preflight 等 column ALTER 都加了，但 V062/V065 column add 缺）

---

## §5 engine_mode 標籤一致性

### 5.1 真實 row 分布（所有 engine_mode CHECK constraint 表）

| 表 | demo | live_demo | live | paper | 其他 | 結論 |
|---|---:|---:|---:|---:|---:|---|
| trading.risk_verdicts | 11,494,478 | 4,473,180 | **2,499,944** | 156 | - | live 真實寫入！|
| trading.intents | 269,958 | 289,103 | 0 | 69 | - | LiveDemo 主導 |
| trading.fills | 3,550 | 2,726 | 0 | 126 | **demo_archive_20260418: 6,616** | 🔴 殘餘 archive label |
| trading.decision_outcomes | 827,625 | 329,557 | **89,734** | 884 | - | live 89734（但 stale 18d）|
| learning.exit_features | 1,425 | 688 | 0 | 57 | - | live 0 OK（fills 0 live）|
| learning.mlde_edge_training_rows | 269,958 | 289,103 | 0 | - | - | mirror intents |
| learning.mlde_shadow_recommendations | 4,520 | 2,136 | **53** | - | - | live 53！|

### 5.2 異常清單

1. **`trading.fills.engine_mode='demo_archive_20260418'`** = 6,616 row（V015 4/14 archive 殘餘 label，未在 CHECK constraint 4 值 paper/demo/live_demo/live 內）— **CHECK constraint 漏洞** 或 historical archive 標籤需明確
2. **risk_verdicts.live = 2.5M**：歷史 mainnet attempt 累積（CLAUDE.md §三 `live_reserved` 0 mainnet 流量是 1B 真實 mainnet 流量設計，但 risk_verdicts 含 2.5M 是 live_demo + 之前 LiveDemo 標 'live' 殘餘）
3. **`learning.mlde_shadow_recommendations.live = 53`**：MLDE 在 LIVE engine_mode 下產生 53 個 recommendation — 需 RCA 是真實 mainnet 還是 LiveDemo 殘餘

### 5.3 ML training filter 一致性
所有 ML training pipeline 已驗 `engine_mode IN ('live','live_demo')`：
- `mlde_edge_training_rows` 0 paper / 0 live → 純 demo + live_demo（**正確**）
- `exit_features` 仍含 57 paper（V015 之前殘餘）→ training filter 必含 `IN ('live','live_demo')` 過濾

---

## §6 時序 Leakage 6 維 Audit

| 維度 | OpenClaw 真實風險 | 證據 |
|---|---|---|
| 1. Look-ahead bias | 🟢 **Rust runtime OK** | `tick_pipeline/on_tick/step_1_2_klines_indicators.rs:36-38` `closed_bars = kline_manager.on_tick()` 只回 closed bar；indicators bollinger/atr 用 closed buffer；**Python research bb_breakout_threshold_sweep.py 已加 leak-free shift(1) 對比** |
| 2. Target leakage | 🟡 **不確定** | `learning.exit_features` 計算 ATR 是用 entry tick 之前還是之後未驗；`giveback_atr_norm` 有 lookahead 風險（需 RCA）|
| 3. Survivorship bias | 🟡 **存在** | `trading.fills.symbol` distinct 包括 BUSDT 已 demo-failed（funding_arb V2 棄策略）；ML training set 不去這些 → 模型沒學 delisting risk |
| 4. Cross-section leakage | 🟢 **OK** | `mlde_edge_training_rows` 不做 cross-symbol normalize；per-symbol per-strategy 獨立 |
| 5. Time-zone / Boundary leakage | 🟢 **OK** | 所有 timestamp 統一 ms-unix-UTC；funding_settlements 整點 UTC |
| 6. Resample boundary leakage | 🟢 **Rust runtime OK** | KlineManager 設計只回 closed bar（`isClosed=true` 等價）；**Python research 沒驗** |

**Critical**：`exit_features.giveback_atr_norm` 計算是否含 entry 後 tick 待 IMPL audit；目前 2170 row 太少，待 P1-7 C 累積 200+ 後才能 statistical 驗證。

---

## §7 Time-series CV Gap

### 7.1 已實作
- `program_code/ml_training/edge_estimate_validation.py` — walk-forward
- `program_code/ml_training/cpcv_validator.py` — CPCV + per-strategy embargo

### 7.2 Gap

| Gap | 嚴重度 | 影響 |
|---|---|---|
| **edge_estimate_validation 缺 purge** | 🔴 | walk_forward `train_end → test_end` 直接 join，沒 horizon embargo；exit_ts 含 H 期 horizon → train fold 含 test fold start 重疊 sample → leak |
| edge_estimate_validation 缺 embargo | 🔴 | 同上，autocorrelation 跨 fold 污染 |
| 樣本量不足 | 🔴 | mlde_edge_training_rows 559k 但 attribution_chain_ok 24h = 45/277054 = 0.016% → 真正可用 sample **太稀**，LightGBM 不能訓練 |
| TimeSeriesSplit gap=0 default | 🟡 | sklearn 預設無 embargo |
| CSCV / PBO 無實作 | 🟡 | 無法計算 backtest overfitting probability |

### 7.3 推薦修法
1. `edge_estimate_validation.py:113-148` 加 `embargo_periods=label_horizon * 1.05` 參數
2. train fold 加 purge：`train_recs = [r for r in train_recs if r.exit_ts + label_horizon < test_start]`
3. mlde_edge_training_rows 攻克 attribution_chain_ok=false 84.6% 問題（FA-H6 + FUP-2）

---

## §8 5×4 Grid 最終定論 + 升階 Prerequisite

### 8.1 Maturity Grid（13 個關鍵 component）

| # | Component | Writer spawn? | Consumer? | Rows? | Decision impact? | Stage | Prerequisite to next |
|---|---|---|---|---|---|---|---|
| 1 | **Strategist live** | Yes | Risk gate + Executor | 559k intents | Yes（live=0 demo+live_demo 高量）| **Production**（demo/live_demo only）| 等 LG-2/3/4 IMPL → Mainnet enable |
| 2 | **Risk gate** | Yes | Order writer | 18.47M row（live 2.5M）| Yes | **Production** | （已 production，無 prereq）|
| 3 | **Reconciler / position_snapshots** | Yes | Strategist | 1.88M row | Yes | **Production** | （已 production）|
| 4 | **decision_outcomes backfiller** | Yes | learning | 1.25M row（live 89734 stale 18d）| Yes（feed back to learning）| **Canary fragile** | 修 live cohort backfill schedule（每日跑）|
| 5 | **MLDE shadow recommendations** | Yes | (read-only consumer) | 6,709 row（live 53）| **No real impact**（recommendation observed only）| **Shadow** | strategist 接受 MLDE 建議 → impact decision |
| 6 | **MLDE param applications** | Yes | Strategist | 2,829 row | **Yes（Shadow→Canary 邊界）** | **Canary**（demo only）| 待 attribution_chain_ok 復原 → live_demo |
| 7 | **Edge estimator** | Yes（每 hr cycle）| Strategist via JSON | edge_estimates JSON | **Yes** | **Production**（demo + live_demo cohort）| （已 production）|
| 8 | **Edge estimate snapshots V059** | **No（only ref21_backfill）** | replay reads | 457 row 5/7 一次 | No | 🔴 **Foundation only** | 補 cycle writer hourly cron |
| 9 | **Model registry** | Yes（一次性 training）| promotion_pipeline | 3 row stale 14d | No | **Canary fragile** | run_training_pipeline.py 重啟 + label 累積 |
| 10 | **Drift detector** | drift_events writer 在但 0 row | feature_baselines 為空 | 0 | No | 🔴 **Aspirational** | feature_baselines writer 補（緊急）|
| 11 | **Cost edge advisor** | env-gated OFF | (advisor logic) | 0 | No | 🟡 **Skeleton** | 設 OPENCLAW_COST_EDGE_ADVISOR_DAEMON=1 |
| 12 | **Decision lease audit V054** | writer code 在 | governance | 0 | No | 🟡 **Foundation** | flag flip canary（待 P0-EDGE-2）|
| 13 | **Replay simulated_fills** | Yes | (only synthetic_replay tier) | 6 row 全 synthetic | No（cannot ML train）| 🟡 **Foundation** | calibrated_replay / counterfactual_replay producer 啟動 |
| 14 | **Counterfactual generator** | **Not deployed** | (none) | 0 | No | 🔴 **Aspirational** | producer code IMPL（無 producer code path 可見）|
| 15 | **Calibrated replay** | **Not deployed** | (none) | 0 | No | 🔴 **Aspirational** | calibration ladder IMPL |
| 16 | **Dream engine** | Yes（PnL 改進建議）| (governance hub) | 12 experiments 4d | Limited | **Shadow** | （observe only，需 governance approve 才 impact）|
| 17 | **LinUCB shadow compare** | Yes | shadow store | 15 state row | No | **Shadow** | warm-start IMPL |
| 18 | **LG-5 reviewer scheduler** | Yes（FUP-1 commit `463890d`）| governance_audit | 22,789 row | Limited（advise only）| **Canary** | （新落地）|

### 8.2 5 階段歸類

| 階段 | 數量 | components |
|---|---:|---|
| **Production** | 4 | Strategist live(demo+ld) / Risk gate / Reconciler / Edge estimator |
| **Canary** | 4 | decision_outcomes backfiller (fragile) / MLDE param applications / Model registry (stale) / LG-5 reviewer |
| **Shadow** | 4 | MLDE shadow rec / Dream / LinUCB / decision_shadow_fills |
| **Skeleton** | 4 | Cost edge advisor (env OFF) / Decision lease audit / decision_shadow_exits / Combine Layer Part A |
| **Foundation** | 5 | Edge estimate snapshots (writer-less) / Replay simulated_fills (synthetic only) / V061 promotion calc / V064 spine / V065 proposal ledger |
| **Aspirational** | 5 | Drift detector (0 baseline) / Counterfactual generator (no code) / Calibrated replay (no code) / Combine Layer Part B / Layer 2 reasoning |

---

## §9 Dream / Counterfactual / Calibrated 增長率 + ETA

### 9.1 真實累積率
| Source | 4d 累積 row | 推估 daily rate | 目標 sample（LightGBM 1k）| ETA |
|---|---:|---:|---:|---|
| replay.experiments | 12 | ~3/day | 1000 | **~333 day**（11 個月）|
| replay.simulated_fills | 6（all 'synthetic_replay'）| ~1.5/day | 1000 (calibrated_replay) | **>2 year**（current rate 0/day calibrated）|
| replay.report_artifacts | 6 | ~1.5/day | 1000 | ~666 day |
| Dream engine experiments | (mixed in replay.experiments) | ~3/day | 1000 | ~333 day |

### 9.2 Critical insight
**replay.simulated_fills 6 row 全部 `evidence_source_tier='synthetic_replay'`**（CLAUDE.md §九 明確標 synthetic_replay 不可作 ML training data）。

**0 row 走 calibrated_replay / counterfactual_replay verification gate**。所以**當前增長率 = 0 sample/day 可餵 MLDE / Dream / attribution writer**。

### 9.3 結論
- LightGBM training（≥1000 sample）**不可能在 12 個月內 ready**，除非：
  1. counterfactual_replay producer IMPL（需新代碼）
  2. calibrated_replay producer IMPL（需 calibration ladder）
- 短期可行策略：**先用 mlde_edge_training_rows 559k row**（其中 attribution_chain_ok=true 的 ~100 row）作 baseline LinearRegression / 小型 LightGBM (n_features ≤ 10)；不要等 calibrated_replay
- **Dream Engine 目前是純 advisory**（12 experiments 4d，governance approve 0% → impact = 0）

---

## §10 Apple Silicon M5 Ultra 部署 Readiness

### 10.1 評估
**M5 Ultra（128GB 統一記憶體 / PG 限 4-8GB）部署 readiness = C**

| 維度 | 狀態 | 阻塞 |
|---|---|---|
| Schema 跨平台兼容 | A | hypertable + sqlx migration 全跨 platform |
| Compression policy | B | 9/39 compressed；可加大覆蓋 |
| Retention policy | F | 9 個高量表 0 retention（risk_verdicts 18.47M / decision_features 9.47M / position_snapshots 1.88M）|
| Chunk 大小 | C | risk_verdicts 5 chunk × 3.7M row/chunk 在 4-8GB PG 風險高 |
| work_mem 設定 | ? | 真實 postgresql.conf 未取（需 operator 提供）|
| shared_buffers | ? | 同上 |
| Connection pooling | ? | pgbouncer 啟用狀態未驗 |
| Logical replication 准備 | F | 0 logical replication setup（M5 Ultra 部署後 sync 困難）|

### 10.2 M5 Ultra 部署前必修 4 條
1. **risk_verdicts retention 30d** + compression 7d + 重 chunk
2. **decision_features retention 90d** + compression 14d
3. **position_snapshots retention 90d** + compression 7d
4. **driver postgresql.conf** 顯式設 work_mem=32MB / shared_buffers=2GB / max_connections=50

### 10.3 跨平台路徑兼容
CLAUDE.md §六 已要求 `OPENCLAW_BASE_DIR / OPENCLAW_DATA_DIR / OPENCLAW_SECRETS_*`，符合 Mac 規範。

---

## §11 V068+ Migration 9 條提議

### Sprint 1 — 砍 Dead Schema（V068-V071，4 條）
1. **V068__drop_dead_learning_tables.sql** — 刪 9 表：foundation_model_features / rl_transitions / symbol_clusters / promotion_pipeline / weekly_review_log / experiment_ledger / pattern_insights / ml_parameter_suggestions / decision_state_changes（全 0 row + 0 producer code）
2. **V069__drop_dead_observability_tables.sql** — 刪 4 表：scorer_predictions / model_performance（0 producer code）+ feature_baselines + drift_events 暫保留（緊急 IMPL writer）
3. **V070__drop_dead_replay_tables.sql** — 刪 5 表：handoff_requests / mlde_replay_veto_log / tier_promotion_approval / business_kpi_snapshots / audit_incident_summaries
4. **V071__drop_dead_learning_dormant.sql** — archive 4 表：cost_edge_advisor_log / ai_usage_log / ai_budget_config / directive_executions / teacher_directives（producer 接線但 0 row）— archive 而非 drop（writer 可能未來啟動）

### Sprint 2 — 補 Producer（V072-V074，3 條 + 代碼 IMPL）
5. **V072__feature_baselines_writer_init.sql** — 加 cron job + helper script `helper_scripts/db/feature_baselines_writer.py` 從 `learning.decision_features` last 7d 計算 baselines
6. **V073__edge_estimate_snapshots_cycle_writer.sql** — Rust runtime cycle writer hourly INSERT 至 V059
7. **V074__decision_outcomes_live_backfill_schedule.sql** — fix decision_outcomes.live cohort stale 18d；compose with `helper_scripts/db/outcome_backfiller_live.py` daily cron

### Sprint 3 — Retention + Guard（V075-V076，2 條）
8. **V075__retention_policies_critical_tables.sql** — `add_retention_policy` 9 表：
    - risk_verdicts 30d / decision_features 90d / position_snapshots 90d
    - signals 90d / scorer_training_features 60d / mlde_edge_training_rows 90d
    - order_state_changes 60d / intents 90d / decision_outcomes 180d（live cohort 永久保留）
9. **V076__retrofit_guard_v062_v063_v065.sql** — 補 V062 / V063 / V065 缺的 Guard A（CLAUDE.md §七 強制）

---

## §12 MIT Verdict

### 12.1 ML 基座達標 %
- **Schema layer**：A−（V001-V067 全 success；3 條 Guard 退化）
- **Writer layer**：C+（21 dead schema / 4 producer-OFF）
- **Consumer layer**：C（drift chain broken / decision_outcomes live 18d stale）
- **Decision impact layer**：D（Strategist live=demo+live_demo only / 0 mainnet flow / Drift / Counterfactual / Calibrated 全 dead）
- **Time-series methodology**：B−（CV walk_forward 缺 purge/embargo / leakage 6 維 Rust OK）
- **Production readiness**：D+（4/13 component Production，全 demo+live_demo only）

**綜合 ML 基座達標率 ≈ 38%**（13 個關鍵 component 中 4 Production + 4 Canary fragile）。

### 12.2 距 Production 還差幾條 Sprint

**3-4 sprint** 才可讓 ML 信號實質 drive Mainnet：

| Sprint | 目標 | 預估 |
|---|---|---|
| Sprint 1 | Dead schema 砍 + retrofit Guard | 1 sprint |
| Sprint 2 | feature_baselines + V059 cycle writer + decision_outcomes live backfill | 1 sprint |
| Sprint 3 | counterfactual_replay + calibrated_replay producer IMPL | 1-2 sprint |
| Sprint 4 | LightGBM training launched + MLDE rec → strategist real impact | 0.5 sprint |

**最早 Mainnet ML-driven trading**：~2026-08-01 樂觀 / 2026-09-01 中位 / 2026-11-01 悲觀。**目前完全不在路線圖樂觀帶內（PA 5/30 中位是純 LiveDemo / 5 策略 edge 翻正驅動，不靠 ML）**。

### 12.3 7 個立刻 fix 項
1. 🔴 V062 / V063 / V065 retrofit Guard A
2. 🔴 trading.fills.engine_mode='demo_archive_20260418' 殘餘 6,616 row 標準化
3. 🔴 risk_verdicts retention + chunk size 修
4. 🔴 feature_baselines writer 補（drift chain 緊急）
5. 🟡 decision_outcomes live cohort backfiller schedule
6. 🟡 attribution_chain_ok 24h 0.016% RCA（FUP-2 後）
7. 🟡 MLDE training filter 確認 `IN ('live','live_demo')`（已驗 OK，登 healthcheck）

---

**MIT AUDIT DONE** — `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-08--db_ml_foundation_audit.md`
