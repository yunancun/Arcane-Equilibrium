# v5.8 13-Module Autonomy Expansion 執行性審核 — MIT 視角

**日期**：2026-05-21
**Verdict**：GO-WITH-CONDITIONS
**One-line summary**：v5.8 thesis 對（13 module DESIGN at Sprint 1A 是正解），但 V105-V116 全 placeholder schema spec、4 個 ML 模組（M4/M6/M8/M11）無 CV/leakage/drift 方法論、M10 Tier D 用 GARCH/regime auto-classify 觸 math-model 警戒；Sprint 1A 派 PA 前必補 12 個 V### schema spec doc + 4 ML 模組 CV protocol + Guard A/B/C + PG dry-run mandatory 條款。

---

## 0. V105-V116 schema 設計完整度

| V### | 對應 M# | v5.8 描述（1-2 行）| 狀態 | 致命缺失 |
|---|---|---|---|---|
| V105 | M2 overlay | `overlay_state_transitions + counterfactual_to_state hooks` | **PLACEHOLDER** | state 5 值 enum / from_state / to_state / trigger_type / counterfactual_log FK / engine_mode 全缺；state machine 是 hypertable 還是 regular 未判 |
| V106 | M3 health | `health_observations + degradation_state` | **PLACEHOLDER** | health domain 6 項（WS latency / REST / DB backlog / disk / mem / strategy-level）column inventory 缺；高頻 metric storage 是否 hypertable + 7d chunk + compression 30d 全缺 retention policy |
| V107 | M11 replay | `replay_divergence_log` | **PLACEHOLDER** | divergence_type / divergence_pnl_usdt / divergence_threshold_basis / replay_engine_version / fill_chain_id FK 缺；nightly 1 run × 5 strategy × 5 indicator = 25 row/day = ~9k row/yr 規模規劃缺 |
| V108 | M9 A/B | `ab_tests + ab_assignments + ab_results` | **PLACEHOLDER** | preregistration FK to V103 hypotheses 未明示；assignment hash algorithm（trial_id_hash → variant_A/B）+ sample size pre-calc 算法未指定；ab_results 統計欄位（mSPRT t-stat / Bonferroni / FDR）schema 缺 |
| V109 | M8 anomaly | `anomaly_events + severity` | **PLACEHOLDER** | severity taxonomy（low/med/high/critical）需 ADR-0036 land 才知；event_taxonomy 9 子類（vol regime / corr break / funding / fill rate / order reject / slippage / lease grant / autoencoder / counterfactual）FK to event_type table 缺 |
| V110 | M6 reward | `reward_weight_history + bayesian_opt_runs` | **PLACEHOLDER** | 5 λ 值（dd / tail / turnover / slippage / decay）column 是分 5 column 還是 JSONB 未決；bayesian_opt_runs.iter_count / acquisition_function / posterior_mean 算法欄位缺 |
| V111 | M10 discovery | `discovery_tier_config + capital_triggers` | **PLACEHOLDER** | Tier A-E 5 行 config table；capital threshold（$10k/$15-20k/$20-30k/$30-50k/$50-75k/$75-150k/>$150k）7 級 trigger schema 缺；activation log 是否獨立表未明示 |
| V112 | M1 lease tier | `decision_lease_tiers + tier_eligibility_log` | **PLACEHOLDER** | Tier 0-4 5 級 lease enum；eligibility 計算（30 prior advisory / 80% yes-rate / 90d no-incident / risk envelope）是否需 materialized view 加速 query 未判；auto-approve toggle 持久化欄位缺 |
| V113 | M7 decay | `decay_signals + strategy_lifecycle` | **PLACEHOLDER** | lifecycle state machine 6 值（LIVE / DECAY_DETECTED / DEMOTE_PROPOSED / DEMOTED / RECOVER / RETIRE）enum；rolling 30d Sharpe / DD / consecutive loss / counterfactual diff 4 signal 是分 4 column 還是 array 未決 |
| V114 | M5 reserved | `online_learning_models`（reserved Y1 不用）| **interface stub 可接受** | ADR-0035 明示 Y3+ IMPL；本表只需 schema reservation 不需完整 spec；streaming_enabled BOOL default FALSE column 已預告 |
| V115 | M12 reserved | `order_routing_profiles`（reserved IMPL Sprint 6）| **interface stub 可接受** | ADR-0039；Sprint 6 才真 IMPL；Sprint 1A 只需 OrderRouter trait + 表 placeholder |
| V116 | M13 reserved | `asset_class_venue_registry`（reserved Y2）| **interface stub 可接受** | ADR-0040；AssetClass/Venue enum 即可 |

**致命**：9 個 V### (V105-V113) 完全 placeholder；只有 V103/V104（v5.7 lineage）有 spec doc（`2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`）。Sprint 1A-β 至 -ε 派 PA dispatch 時，**v5.7 同類 V055 5-round loop 風險 9 倍放大**。

## 0.5 ML pipeline maturity per ML-related module（設計階段評）

| Component | Writer 設計? | Consumer 設計? | Row 累積規劃? | Decision impact 設計? | Stage 預期 |
|---|---|---|---|---|---|
| M4 self-supervised pattern miner | §M4 Sprint 2-3 cross-correlation + event-window；Sprint 8 clustering | DRAFT → operator/Cowork review → preregister | hypothesis DRAFT ~10-20/yr Sprint 8+ | **不影響真實決策**（DRAFT only，CC operator approve required）| **Skeleton spec adequate**（discovery layer 設計 OK）|
| M5 online learning | §M5 interface stub only Sprint 1A；IMPL Y3+ | Y3+ ModelClient.get_predict_streaming() reserved | **N/A Y1**（reserved）| **N/A Y1** | **Foundation reserved** |
| M6 bayesian reward opt | §M6 reward_weight_history Sprint 7 Advisory；Y2 auto ≤30% | Allocator 月度 use new weights | per-allocation outcome row ~12-24/yr | **Y2 影響 Allocator weights**（gate 30% change rollback）| **Skeleton-ready spec needed**（bayesian opt 算法 spec 缺）|
| M7 decay detection | §M7 decay_signals Sprint 8 IMPL | demote state machine | 5 strategy × ~1 signal/day = ~1825 row/yr | **Sprint 10 Y1 末 first auto-demote via M1 Tier 1** | **Shadow-ready spec needed**（per-strategy baseline calibration 缺）|
| M8 anomaly detection | §M8 anomaly_events Sprint 3 read-only logging；Y2 active trigger | Sprint 8 Slack alert；Y2 → M3 HEALTH_DEGRADED | per-symbol × per-strategy × event_type ~5-20 row/day = ~5k-20k/yr | **Y2 active trigger → halt new positions**（重大決策影響）| **Skeleton-ready spec needed**（autoencoder retraining cadence 缺）|
| M11 continuous replay | §M11 replay_divergence_log Sprint 3 nightly job；hooks 到 M3/M7/M8 | M3 HEALTH_WARN / M7 decay input / M8 own behavior anomaly | 5 strategy × 24h replay × ~5 indicator = 25 row/day = ~9k/yr | **Sprint 5+ hookups 影響 M3/M7/M8 決策**（intermediate）| **Shadow-ready spec needed**（divergence threshold 算法缺）|

## 0.6 feature engineering leakage check per module

| Module | Look-ahead | Target leak | Survivorship | Cross-section | Time-zone | Resample boundary | 評估 |
|---|---|---|---|---|---|---|---|
| M4 pattern miner | **未明示**（rolling cross-correlation 必加 shift(1)；event-window 是 [t-N, t-1] 還是 [t-N, t] 未定）| **未明示** | **未明示**（universe 含 delisted symbol?）| **未明示** | **未明示**（FOMC UTC vs local？）| **未明示**（resample 1m→5m 用 closed bar?）| **6/6 leakage 維度全缺；高 risk** |
| M6 bayesian reward | reward function 對歷史 6mo allocation 反推；**outcome 已知未來才能評**，本質 NOT live leak | OK | OK | OK | OK | OK | **設計目的本身是 retrospective 評估，不適用 leakage**；但對 next-month weight 推薦時 IS/OOS gap 監控未提 |
| M7 decay detection | **rolling 30d Sharpe 必 .shift(1) 排除 current bar**；v5.8 未明示 | **decay signal threshold per-strategy baseline 是否用未來資料校準?** 未明示 | **OK**（per-strategy live data only）| OK | UTC OK | bar boundary 未明示 | **2/6 leakage 維度有風險** |
| M8 anomaly detection | **rolling z-score 必 expanding 算法 + shift(1)**；ARIMA residual / isolation forest 對 in-sample fit 必 chronological | OK | **autoencoder retraining：training data source 是否含 anomaly period?** 未明示 | OK | UTC OK | OK | **2/6 leakage 維度有風險；autoencoder Y2 spec 必 freeze training data window** |
| M11 continuous replay | replay engine 本身對歷史 24h 用 SAME data；**replay decided trade 必用 trade_ts 前 feature**；無 future look-ahead 設計 OK | OK | OK | OK | UTC OK | OK | **OK by design**（replay 本身就是 leak-free framework）|

---

## 1. Top 3 執行性風險

### Risk 1：V105-V113 9 個 V### schema spec 全 placeholder（V055 5-round loop 9 倍放大）

- 嚴重度：**CRITICAL**
- 位置：v5.8 §9 schema migration roster line 686-711
- 描述：v5.7 1 個 V103/V104 placeholder 已迫使 MIT 補 940-line spec doc（`2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`）；v5.8 加 9 個全 placeholder（V105-V113）+ 3 interface stub（V114-V116）。即使 Sprint 1A engineering 估算到 468-692 hr，這 hr **不含 schema spec land 時間**（schema spec land = MIT 設計工作非 PA IMPL 工作）。歷史 V103/V104 spec 耗時 ~10 MIT-hr；9 個類似規模 spec ≈ 90 MIT-hr，**加上 9 個 Sprint 1A-β/γ/δ/ε 跨週串並行協調 hr 預計再 +30-50 hr** → 累積 ~120-140 MIT-hr 不在 v5.8 §3 Sprint 1A 估算內。
- Must-fix：
  1. 立即派 MIT/PA 同時並行寫 V105-V113 9 個 spec doc（仿 v103_v104 spec 範式：column inventory + Guard A/B/C + hypertable 判斷 + engine_mode CHECK + index plan + Linux PG dry-run protocol + idempotency 測試）
  2. Sprint 1A engineering hr 從 468-692 修正到 558-832（+90-140 MIT-hr buffer）
  3. v5.8 §9 增段「V105-V113 spec land 為 Sprint 1A-β/γ/δ/ε hard precondition」+ link 9 個 spec doc 路徑（即使尚未 land 也先 reserve 路徑）

### Risk 2：M4/M7/M8 ML 模組 leakage 防範 6 維度全缺；M6 bayesian opt 算法 spec 缺

- 嚴重度：**HIGH**
- 位置：v5.8 §M4/M6/M7/M8 各段
- 描述：四 ML 模組（M4/M6/M7/M8）全文未引用 `feature-engineering-protocol`（look-ahead / shift(1) / survivorship / cross-section / time-zone / resample boundary）+ `time-series-cv-protocol`（walk-forward / Purged k-fold / embargo / CSCV / sample size）+ `data-drift-detection`（PSI / KS / Wasserstein / DDM / Page-Hinkley）。v5.8 §M5 只提「KL divergence on feature distribution」一行，無閾值 + retraining cadence。歷史 OpenClaw bb_breakout F3 RETRACT 教訓（rolling(N).max() 含 current bar）正是 leakage 6 維度漏接的代價。
- Must-fix：
  1. M4 schema land 前必補：pattern miner cross-correlation 必 leak-free（shift(1) 強制 + announcement_ts UTC + isClosed=true bar boundary）
  2. M6 bayesian opt 算法 spec：Gaussian Process posterior / acquisition function（EI / UCB / PI）/ kernel 選擇 / iter budget / convergence criteria
  3. M7 per-strategy baseline calibration：rolling 30d Sharpe 必 expanding mean + std + shift(1)；threshold 是否 per-symbol 動態調整未指定
  4. M8 autoencoder retraining cadence + training data freeze window（必排除 anomaly period to avoid contamination）
  5. M11 replay divergence threshold：是 fixed bps 還是動態 statistical band（rolling mean ± k×std）未指定

### Risk 3：M10 Tier D「regime auto-classify」+ GARCH break detection 觸 math-model-audit 警戒

- 嚴重度：**MEDIUM-HIGH**
- 位置：v5.8 §M8 line 287 + §M10 Tier D line 367
- 描述：
  - §M8 line 287「Vol regime shift (Hurst exponent change, GARCH break)」明示用 GARCH。GARCH 估計需要 ≥1000 obs 且 crypto fat tail / vol clustering 對 GARCH(1,1) 不友好（well-known model misspecification）；非 math-model blacklist 但 GARCH break test 統計 power 在 crypto setting 弱（false-positive 率高）。
  - §M10 Tier D line 367「regime auto-classify」未指明算法；常用算法為 **HMM (Hidden Markov Model)** — 屬於 OpenClaw math-model-audit skill 提及「需特別審核」類；若 v5.8 IMPL 期默選 HMM，需 MIT 審視 (a) hidden state 數量先驗 (b) emission distribution 假設 (c) sample size requirement (≥10k obs typical) (d) 與 strategy allocation 的反饋耦合風險。
- Must-fix：
  1. M8 GARCH break detection 必明示替代方法（rolling realized vol percentile / Bollinger Band breakout / Markov-switching alternative）+ statistical power audit
  2. M10 Tier D regime auto-classify 在 ADR-0036 / Sprint 1A schema spec 階段必明示算法選擇（HMM / change-point detection / Markov-switching / k-means clustering）+ MIT push-back 機制（若 HMM 被選必走 math-model-audit skill 全審）
  3. v5.8 §M10 line 382「Tier D (regime auto-classify) (100-160 hr)」未含算法 sanity-check 工時 → +20-40 hr buffer

---

## 2. PG dry-run mandatory coverage check (per V###)

| V### | v5.8 明示 dry-run? | 備註 |
|---|---|---|
| V103/V104 | YES（v5.7 lineage spec doc §4 land）| MIT spec 已含 Linux PG empirical query × 2 round + sqlx checksum repair SOP |
| V105-V113 | **NO** | v5.8 §10 risk 1 line 726 僅一行「per-V dry-run requirement」泛指 CLAUDE.md §Data Migrations And Validation；無 per-V 具體 ssh PG query / round 1 round 2 protocol / sqlx repair SOP |
| V114-V116 | **N/A**（interface stub Sprint 1A 不 apply）| Y2/Y3 IMPL 期才需 dry-run；本期 reservation OK |

**致命**：v5.8 §3 + §9 全文未引用 `feedback_v_migration_pg_dry_run.md` 或 V055 5-round loop / V083+V084 incident chain 教訓。Sprint 1A-β/γ/δ/ε 各週派 PA dispatch 時，**9 個 V### 若每個都重蹈 V055 5-round 覆轍 = +9×(20-40 hr) = +180-360 hr 額外浪費**。

**Must-fix**：v5.8 §3 或 §10 增段「PG dry-run mandatory before E1 IMPL per V###」（仿 V094 / V103 spec 範式）；每 V### spec doc 必含 ssh PG query × 2 round + idempotency 測試 + sqlx checksum repair SOP。

---

## 3. Migration race-aware sequencing V097-V116

```
V097/V098 (Linux DB catch-up, in flight per v5.7)
  ↓
V099/V100 (Track v3 per PM arbitration; spec doc 2026-05-20 v101_v102)
  ↓
V101/V102 (Earn schema per PM arbitration; spec doc 2026-05-20 v101_v102)
  ↓
V103/V104 (hypotheses + preregistration; spec doc 2026-05-21 v103_v104 已 land)
  ↓
V105 (overlay - M2)         ─ Sprint 1A-γ
V106 (health - M3)          ─ Sprint 1A-β
V107 (replay div - M11)     ─ Sprint 1A-β
V108 (A/B - M9)             ─ Sprint 1A-γ
V109 (anomaly - M8)         ─ Sprint 1A-γ
V110 (reward weight - M6)   ─ Sprint 1A-β
V111 (discovery tier - M10) ─ Sprint 1A-γ
V112 (lease tier - M1)      ─ Sprint 1A-β
V113 (decay - M7)           ─ Sprint 1A-β
  ↓
V114/V115/V116 (M5/M12/M13 reserved interface stub) ─ Sprint 1A-δ
```

**Race 風險點**：
1. **V107 (M11) 依賴 V103/V104（hypotheses）+ V109 (M8) + V113 (M7)**：M11 replay log 接 M7 decay / M8 anomaly hooks；若 V107 schema land 但 V109/V113 schema 未 land，M11 nightly job IMPL 期撞 schema drift
2. **V108 (M9 A/B) 依賴 V103 hypotheses**：A/B preregistration 共用 hypothesis schema；A/B 是 hypothesis 的 subtype
3. **V109 (M8 anomaly) → V112 (M1 lease tier)**：M8 active trigger Y2 → halt new positions；lease tier eligibility 可能依賴 M8 anomaly history (no-incident in 90d criterion)
4. **V112 (M1 lease tier) → V113 (M7 decay)**：M7 auto-demote via M1 Tier 1（per §M7 Sprint 10）；V113 IMPL 前 V112 必 land
5. **V105 (M2 overlay) → V107 (M11 replay)**：M11 hookup 提供「counterfactual diverges from production」signal for M2 auto-disable trigger（per §M2 trigger #1 line 105）

**Must-fix**：v5.8 §9 必增 cross-V### dependency graph + Sprint 1A-β 必先 land（V106/V107/V110/V112/V113）-γ 才能 land（V105/V108/V109/V111）的 sequencing 規範。Sprint 1A-β/γ 不能無條件並行。

---

## 4. Blacklist 方法（HMM / GARCH 等）

| Method | 位置 | 評估 | Action |
|---|---|---|---|
| **HMM (Hidden Markov Model)** | M10 Tier D（line 367，未明示但 regime auto-classify 默選）| **觸警戒**；HMM 在 crypto setting 通常 hidden state n=2-3（risk-on/risk-off/transition），sample size ≥10k obs；MIT 推薦 alt = change-point detection (PELT / BinSeg) 或 Markov-switching regression | v5.8 §M10 Tier D 必明示算法 + 邏輯 / 排除 HMM |
| **GARCH** | M8 line 287（vol regime shift）| **觸警戒**；GARCH(1,1) 在 crypto vol clustering / leverage effect / regime shift / fat tail 4 點 misspecification | 替代 = realized vol percentile / Bollinger Band 動態邊界 / Markov-switching GARCH（仍含 HMM 元素）/ rolling EWMA |
| **Hurst exponent** | M8 line 287 | **OK**（rolling R/S 或 DFA 算法成熟）；但 crypto setting Hurst 估計穩定性需 ≥500 obs window | 推薦 rolling 500-1000 obs + bootstrap CI |
| **ARIMA residual** | M8 line 297 | **OK**（statistical drift baseline）；但 ARIMA(p,d,q) 階數選擇 + residual 白噪音檢驗 缺 spec | spec 補 BIC/AIC 階數 + Ljung-Box test |
| **Isolation forest** | M8 line 297 | **OK**（成熟 sklearn 套件）；但 hyperparam（n_estimators / contamination）spec 缺 | spec 補 Hyperparam + grid search |
| **Autoencoder** | M8 line 297（Y2+）| **OK by design**（標準 anomaly detection 工具）；但 training data window + retraining cadence spec 缺 | Y2 spec 必含 |
| **Bayesian optimization** | M6 line 233 | **OK**（成熟方法 sklearn / scikit-optimize / hyperopt）；但 kernel / acquisition function / convergence criteria 缺 spec | M6 schema land 前必補 |
| **mSPRT** (M9) | line 339 | **OK**（成熟 sequential test 方法 Wald 1947 + Robbins 1970）；power analysis 缺 spec | M9 schema land 前必補 |

---

## 5. 對 PA+FA+PM 匯總必收 top 3

1. **9 個 V### schema spec doc**（V105-V113）必 land Sprint 1A-β/γ/δ/ε 之前；建議 MIT 並行寫，每 spec 仿 v103_v104 範式（~10 MIT-hr × 9 = 90 hr）
2. **4 個 ML 模組 CV / leakage / drift 方法論 protocol**（M4 / M6 / M7 / M8）必 land；引用 feature-engineering-protocol + time-series-cv-protocol + data-drift-detection skills；MIT spec ~5 hr × 4 = 20 hr
3. **PG dry-run mandatory + Guard A/B/C 規範條款**寫入 v5.8 §3 或 §10 risk section；引用 feedback_v_migration_pg_dry_run.md + V094 spec 範式 + V055/V083/V084 incident chain；治本 = 防 9 個 V### 重蹈 V055 5-round loop 覆轍

---

## 6. v5.8 派發前 must-fix

1. **新增 9 個 V### spec doc**（V105 overlay / V106 health / V107 replay div / V108 A/B / V109 anomaly / V110 reward / V111 discovery tier / V112 lease tier / V113 decay）— 仿 `2026-05-21--v103_v104_earn_hypotheses_schema_spec.md` 範式；每 spec ≥ column inventory + Guard A/B/C + engine_mode CHECK + hypertable 判斷 + Linux PG dry-run protocol + idempotency 測試 + cross-V### FK dependency
2. **v5.8 §3 / §10 增段「PG dry-run mandatory」**：明示引用 feedback_v_migration_pg_dry_run.md + CLAUDE.md §Data Migrations And Validation + V094/V103 spec 範式；每 V### 必 ssh PG query × 2 round + sqlx checksum repair SOP
3. **v5.8 §9 增 cross-V### dependency graph**：明示 V107 → V103/V109/V113 / V108 → V103 / V109 → V112 / V112 → V113 / V105 → V107 五條依賴；Sprint 1A-β/γ 不能無條件並行
4. **M4 pattern miner schema land 前必補 leakage protocol**：cross-correlation .shift(1) 強制 + announcement_ts UTC + isClosed=true bar boundary + survivorship audit
5. **M6 bayesian opt 算法 spec**：Gaussian Process kernel + acquisition function + iter budget + convergence
6. **M7 per-strategy baseline calibration**：rolling 30d Sharpe expanding mean+std+shift(1)；threshold dynamics per-symbol
7. **M8 GARCH break replace by alternative + ADR-0036 明示算法**：避免 GARCH crypto misspec；推薦 realized vol percentile + Markov-switching （無 HMM）/ change-point detection
8. **M10 Tier D regime auto-classify 算法明示**：禁默選 HMM；推薦 change-point detection (PELT) + Markov-switching regression；MIT push-back gate
9. **M11 replay divergence threshold 算法**：fixed bps 還是 rolling mean ± k×std；spec 必明示
10. **Sprint 1A engineering hr 修正**：468-692 → 558-832（+90-140 MIT-hr for 9 spec doc）+ ML protocol +20-30 hr = 578-862 hr
11. **Sprint 1A timeline 7w → 7.5-8w**：含 spec land 後派 PA dispatch 跨週協調 buffer

## 7. Sprint 1A-β-ε 期間 should-fix

1. **M5 online learning drift detection KL threshold**：v5.8 line 200 只一行；Y3+ IMPL 期前必補 PSI/KS/Wasserstein/JS divergence 互補閾值表 + DDM/Page-Hinkley error rate monitoring
2. **M5 auto-rollback rule**：streaming model vs daily-batch baseline 比較；rollback 觸發閾值 + 30%/50%/critical 三級
3. **M8 autoencoder Y2 spec**：training data window（exclude anomaly period for clean baseline）+ retraining cadence（monthly? regime-shift-triggered?）+ reconstruction error threshold per-symbol
4. **M11 nightly run 引擎 capacity 規劃**：每 24h 重 replay 5 策略所有 fills；data volume + compute time 估算（OpenClaw fill ~hundreds/day × 5 strategy × full replay engine = compute cost）；PG read load 影響
5. **M10 Tier C-D 新 symbol screening 算法**：cross-asset correlation matrix eigendecomp / clustering / liquidity rank；MIT push-back gate
6. **M9 A/B 統計多重比較修正**：Bonferroni vs FDR vs Holm-Bonferroni；power analysis 算法 spec
7. **M4 hypothesis DRAFT writeback governance**：Bot 寫 DRAFT 但 NOT promote / NOT execute（per ADR-0024-lite）；spec land 後 IMPL 期 RACE 風險（hypothesis state machine concurrent write）

---

## 結論

**Verdict**：**GO-WITH-CONDITIONS**

v5.8 13-module autonomy expansion thesis **完全正確**（operator 直接 reject Claude push-back 是對的；13 module DESIGN at Sprint 1A 避免 Y2-Y3 retrofit 成本）。§1 roster + §2 module spec architecture + §4 Y1 timeline 規劃 + §10 risk recheck 全 sound。

**但執行性 3 個 critical/high risk 必先處理**：
1. **V105-V113 9 個 schema spec 全 placeholder**（V055 5-round loop 風險 9 倍放大）
2. **M4/M7/M8 ML 模組 leakage 6 維度 + M6 bayesian 算法 spec 全缺**（feature-engineering-protocol + time-series-cv-protocol + data-drift-detection skill 未引用）
3. **M10 Tier D regime auto-classify 暗示 HMM + M8 GARCH break 觸 math-model 警戒**（必明示替代算法）

修完上述 3 條 + 工時 +20-25% 修正後（468-692 → 578-862 hr / 7w → 7.5-8w），v5.8 Sprint 1A-β 可派 PA dispatch。

**MIT AUDIT DONE: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-21--v58_executability_audit.md**
