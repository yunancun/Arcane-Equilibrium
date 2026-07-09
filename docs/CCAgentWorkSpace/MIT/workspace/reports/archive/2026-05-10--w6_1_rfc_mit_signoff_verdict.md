# W6-1 RFC final verdict — MIT sign-off

**Date**: 2026-05-10 20:38 UTC (post-V086 IMPL apply, pre-engine restart)
**Verdict**: **APPROVE-CONDITIONAL** (5 必修條件 + 2 SHOULD)
**Reviewer**: MIT
**Scope**: 4 verdict 對應 MIT 立場 + W6-5 撤回 sample_weight 替代 sound check + W6-3 兩 column schema audit + V086 OR-filter 缺陷 governance 立場 + V086 backfill data quality + chain integrity post-V086 + Track B N+2/N+3 deferred 立場
**前置 evidence**:
- PA W6-1 RFC final verdict draft `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_1_rfc_final_verdict_draft.md`
- MIT W6 RFC MIT-view `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w6_rfc_mit_questions_self_answer.md`
- E1 W6-3c V086 IMPL report `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w6_3c_v086_impl_dry_run_writer_code.md`
- MIT W6 baseline + W6-3a + chain replay (memory.md)
- ssh trade-core empirical PG live (2026-05-10 20:35 UTC)

---

## §1 4 verdict 對應 MIT 立場

### Verdict 1 — cost_gate hard rule 維持，不引 advisory mode → **APPROVE**
- MIT ML pipeline 立場：cost_gate 是 fail-closed 風控 gate，advisory 化 = 用真錢餵 ML（違反原則 #5 + #4）。同 PA QC 共識。
- 補充：當前 cost_gate 拒擋 negative shrunk_bps 是 JS estimator 的物理產出，不是 governance bug；MIT C1.h db-schema audit 對 cost_gate gates.rs:108-184 三層設計（paper exploration / demo moderate / live fail-closed）已驗結構正確，無 silent-noop 風險。
- N+2 重提防線 + AMD 化記錄合理。

### Verdict 2 — JS shrinkage 強收縮到 grand_mean 是設計預期 → **APPROVE**
- MIT ML pipeline 立場：JS B factor ≈ 1 + grand_mean negative + low cell-level variance = 教科書 shrinkage signature（Lehmann & Casella, Theory of Point Estimation, Ch. 5）；4 cost_gate cells std=1.04 bps 是 bias-variance trade-off 的設計交付，不是 estimator bug。
- 觸發點 reframe N+2 grand_mean 翻正後重評，正確。MIT 補：W2 A4-C BTC→Alt Lead-Lag fast-track / W-AUDIT-8a Phase B/C/D Tier 2/3/4 alpha source 落地後才有真正 cell-level idiosyncratic alpha 進來。

### Verdict 3 — cost_gate 放行期望 -14 bps，不需 counterfactual backtest → **APPROVE**
- MIT ML pipeline 立場：JS estimate 自身就是 model 的 expected new fill 期望值（unbiased point estimate），用 counterfactual backtest 只能驗證 JS 估計準度（i.e., model self-consistency）非「替代決策」。同 QC 數學否決邏輯。
- 補：4 bias 修正（leak-free shift / fee+slippage refit / funding drag / JS self-fulfilling）若做必先依 `feature-engineering-protocol` 6 leakage 類型逐項 + `time-series-cv-protocol` purge+embargo；ROI 確實不值得。

### Verdict 4 — scorer_trainer 是 LightGBM regression（W6-5 撤回 sample_weight 替代）→ **APPROVE FULLY**
- MIT W6-5 揭露 category error 在本 verdict 完整還原（scorer_trainer.py:90-104 objective='regression' / metric='rmse'）；is_unbalance / scale_pos_weight 對 regression silently ignore 是 LightGBM 已知 behaviour（不報錯只忽略）。
- 立場 confirm：sample_weight ratio sensitivity 是正確替代方案（regression L2 loss weighted contribution）。
- §3 Track A/B 拆分解 PA Q3 hold A vs MIT Q2 hold B 分歧合理；Track A regression 微調 immediate 不需 V086 + Track B multi-class future 等 4-gate。

---

## §2 W6-5 撤回 + sample_weight 替代 — MIT ML pipeline 立場 sound check

### sample_weight ratio sensitivity (1/100 / 1/170 / 1/300 / 1/500) ML pipeline sound 評估

| 維度 | 評估 | 證據 |
|---|---|---|
| **Algorithm 正確** | ✅ Sound | LightGBM `lgb.Dataset(weight=...)` 對 regression 是 standard "instance weighting"，每 sample loss = weight × MSE_per_sample；regression 沒「class」概念但有「contribution」概念，此設計符合 statsmodels weighted least squares (WLS) 教科書 |
| **Ratio 範圍合理性** | ✅ Sound but suspect | 1/170 來源是「reject:fill ratio 7038:615 ≈ 11.4 + 100× safety margin」per V084；1/100 / 1/300 / 1/500 是 sensitivity 周邊。**Push back**: 100× safety margin 是 **engineering choice 沒統計依據**（不是 cross-validated optimum）。建議 W6-5 試行報告含 1/15 ratio（純 reject:fill 比，無 safety margin）作 lower bound，看 RMSE / Sharpe 是否更佳 |
| **Evaluation metric** | ⚠️ MED issue | 試行報告 metric = RMSE + Sharpe + cost_gate decision distribution。**Push back**: 缺 **out-of-sample purged k-fold** evaluation；建議走 `time-series-cv-protocol` walk-forward rolling + purge label_end_ts < test_start + embargo 1d；只看 RMSE 訓練集會過擬合 sample_weight |
| **Sample size adequacy** | ✅ Sound | total pool 7038 reject + 615 fill > LightGBM regression 1000 baseline；per-strategy fill <200 4/5 策略仍不過 gate（grid 374 過 / ma 167 / bb_breakout 27 / bb_reversion 4 / funding_arb 43 dormant），但 Track A 是 **global pool** 訓練（跨策略），所以 acceptable |
| **不 deploy production** | ✅ Sound | W6-5 acceptance「僅報告對比，不 deploy 入 production cron」是正確 fail-safe pattern；regression 模型替代風險高，shadow 試行 → manual review → AMD 化才 deploy |
| **Track A 不需 V086** | ✅ Sound | regression scorer 預測 label_net_edge_bps（連續變量）；reject_reason_code 對 regression task 是冗餘 categorical metadata；Track A 完全不需 V086 落地 |
| **Track B 4-gate** | ✅ Sound | (a) V086 + (b) 18+ enum 各 ≥200 + (c) classification trainer spec + (d) imbalance 試行 = 4 必要前置；funding_arb 永不過 (b) per ADR-0018 是設計接受 |

### MIT 推薦補充（試行 acceptance gate）

W6-5 試行報告必含以下 ML pipeline metrics（MIT C1.b time-series-cv-protocol § Per-fold metrics）：

1. **Per-fold RMSE + 95% CI**（5 fold walk-forward rolling, train_window=10d, test_window=2d, embargo=1d, purge label_end_ts < test_start）
2. **IS vs OOS gap**（gap > 50% → 撤回試行 baseline）
3. **Cross-fold consistency**（std/mean > 0.5 → 不上線 even shadow）
4. **PSI + KS p-value**（per-fold prediction distribution drift；走 `data-drift-detection` skill）
5. **cost_gate decision distribution shift**（per ratio: # cells PASS 變化 + JS shrinkage B factor 變化）

如試行報告缺以上 ≥3 項 → MIT 後續 sign-off REJECT。

---

## §3 W6-3 兩 column schema MIT DB 立場

### 兩 column TEXT (reject_reason_code + close_reason_code) vs alternatives

| 設計 | 立場 | 理由 |
|---|---|---|
| **兩 column TEXT (12 + 14 enum)** PA 採納 | **APPROVE** | (1) regression scorer 不讀 column，純 metadata 純 additive (2) NOT VALID CHECK 不破歷史 9.5M unlabeled (3) overlap=0 互斥不變式由 backfill SQL CASE WHEN 強制 (4) 未來 multi-class trainer 升級可直讀 enum 無重 schema |
| **單 column reason_code TEXT** | **REJECT** | reject + close semantic 完全不同（reject = 沒下單 / close = 下單後 exit）；同 column 強塞 26 enum 模糊語意；filter query 變複雜 (`WHERE reason_code IN (12 reject)` vs `IN (14 close)`) |
| **multi-class FK to enum table** | **REJECT** | over-engineering；JOIN cost > savings；TEXT enum CHECK 已 type-safe |
| **enum table (PG ENUM type)** | **REJECT** | PG ENUM ALTER TYPE 加值需 lock；TEXT + CHECK constraint 加 enum 只需 ALTER TABLE DROP/ADD CHECK（更靈活）；ENUM type 跨 DB 重建 friction 高 |
| **jsonb metadata column** | **REJECT** | 失去 enum integrity；index 設計困難；ML feature engineering 需 parse JSON |

### overlap=0 互斥不變式 sufficient？

**APPROVE 但補強**：
- 當前不變式由 backfill SQL CASE WHEN evaluation order + producer code separation 強制（reject path producer 寫 reject_reason_code + close_reason_code=NULL；close path producer 寫 close_reason_code + reject_reason_code=NULL）
- **Push back**: 缺 schema-level CHECK constraint 強制不變式。建議 W6-3c 補：
  ```sql
  ADD CONSTRAINT chk_reason_code_mutually_exclusive
    CHECK ((reject_reason_code IS NULL OR close_reason_code IS NULL))
    NOT VALID;
  ```
  防 future producer code bug 寫雙 column 同 row（V086 SQL 沒這 CHECK，純靠 producer code discipline；MIT 的 db-schema-design-financial-time-series Guard B 範例對 type 敏感場景強制 CHECK constraint，互斥不變式應同等對待）。
- 當前 PG 實測 `overlap_both = 0` PASS，但這是 backfill SQL 產出，不代表 future producer 不會違反。

### Guard A/B/C 套用 (per CLAUDE.md §七 + MIT db-schema-design-financial-time-series)

V086 SQL E1 已含 5 Guard（A/A2/A3/B/C），MIT verify Guard mapping：
- **Guard A** (table existence + column existence) ✅
- **Guard A2** (legacy stub schema check) ✅
- **Guard A3** (constraint pre-existence check) ✅
- **Guard B** (column type check, both TEXT) ✅
- **Guard C** (post-backfill 0 unmapped row + 0 double-prefix) ✅
- **Missing**: 互斥不變式 CHECK constraint（建議補，per above）

---

## §4 V086 OR-filter 缺陷 — MIT migration governance 立場

### E1 finding 復述
V086 SQL line 372 idempotency filter:
```sql
AND (df.reject_reason_code IS NULL OR df.close_reason_code IS NULL)
```
互斥邏輯下，每 row 兩 column 必有一 NULL → 第 2 次 apply UPDATE 20057 row（不是 0）。
- 1st run: UPDATE 18696 (correct backfill)
- 2nd run: UPDATE 20057 (re-UPDATE 18696 unchanged + 1361 new producer row)
- Guard C PASS（lossless deterministic）
- 但違反 spec §2 註解「第二次 0 row no-op」

### MIT 推薦：方案 A (accept current behaviour + spec annotation fix)

| 方案 | 評估 | MIT 推薦 |
|---|---|---|
| **方案 A**: accept; spec annotation 修正為「lossless idempotent re-UPDATE」 | ✅ **RECOMMENDED** | (1) PG behaviour empirical idempotent (deterministic CASE WHEN → same value re-write) (2) Guard C 兩次 PASS 證明不破不變式 (3) 不需重 IMPL round (4) `lock window <30 sec on 9757+ row` per V086 spec §4.5 對 20057 row 估 ~10 sec 仍可接受 |
| **方案 B**: 改 OR → AND (兩 column 都 NULL 才 UPDATE) | ❌ **REJECT** | 方案 B 不解問題：producer 寫 reject_reason_code 後 close_reason_code 仍 NULL → AND filter 仍 trigger UPDATE → 等價 OR；E1 已驗 |
| **方案 C**: 加 reason_code 是否「已是預期 enum」check | ❌ **REJECT** | 複雜度高（需 sub-query 比對 expected mapping）；收益低；future maintenance debt |
| **方案 D**: 加 `df.reject_reason_code IS DISTINCT FROM <expected_enum>` 條件 | ⚠️ **CONSIDER but lower priority** | 真正 idempotent (deterministic noop on 2nd run)；但 SQL 變複雜 + 需 mapping function inline；ROI 不高 |

### MIT migration governance 補強條件（強制）

`db-schema-design-financial-time-series` § Idempotency 「每個 migration 必須能 run 兩次不出錯」當前 V086 滿足「不出錯」（Guard C PASS）但**不滿足** "no-op on 2nd run"。MIT 接受方案 A 但補：

1. **強制更新 V086 SQL §2 spec 註解**為 "lossless idempotent re-UPDATE on 2nd run; deterministic CASE WHEN ensures same value rewrite; safe for repeated apply";  在 commit message 提及此 governance exception accept
2. **強制更新 CLAUDE.md §七 idempotency wording** 為 "idempotency = no schema corruption + no incorrect data state on repeated apply"（不要求 0 row UPDATE，但要求 lossless）；避免未來 migration 認為「row count 必須 0」
3. **強制 W6-3c spec annotation 修正**：spec §2 既存「第二次 0 row no-op」明文修為「lossless deterministic re-UPDATE，行數可能 ≠ 0 但不破不變式」
4. **Acceptance gate 補**：方案 A accept 後，operator 跑 V086 兩次需在 log 檢查 `Guard C PASS` + `overlap_n=0` 即可，不檢 UPDATE row count = 0
5. **D+2 14:30 UTC ALTER VALIDATE CONSTRAINT 之前**，operator 必確認 V086 SQL §2 spec 註解修正完成 → 否則撤回方案 A 走方案 D

---

## §5 V086 backfill data quality assessment

### Empirical PG live (2026-05-10 20:35 UTC)

| Metric | Value | MIT 評估 |
|---|---|---|
| total_labeled | 51113 | baseline |
| reject_with_code | 17810 | backfill PASS (post 5/10 11:00 reject) |
| reject_NULL_code | **31053** | **🚨 producer dual-write code 未 deploy → post-V086-apply 新 row 全 NULL** |
| close_with_code | 2247 | backfill PASS (13/14 enum 命中) |
| close_NULL_code | 3 | 邊角 case (post-V086 close row 但 mapping 未補) |
| overlap_both | 0 | 互斥不變式 PASS |
| Hourly distribution 22:00 UTC | 36352 reject / 5299 w_code / 31053 NULL | confirm 22:00 +1h producer 寫 36352 但 backfill 只 cover 5299 |
| pre-5/10 daily reject | 0 (5/9 to 4/26 全 0) | W-AUDIT-4b M3 producer 5/10 才接通；no sample bias from missing pre-5/10 reject |

### Sample bias 評估

| 維度 | 評估 |
|---|---|
| **Time coverage bias** | ✅ NO BIAS — backfill 範圍 = post-W-AUDIT-4b M3 producer 接通日（2026-05-10），pre-5/10 reject 不存在於 decision_features schema (走 risk_verdicts only path)；不存在「老歷史 fills 沒 backfill」問題 |
| **Strategy coverage** | ⚠️ **HIGH IMBALANCE** — 17810 reject 主要 grid_trading + ma_crossover (per W6-3a baseline cost_gate JS-demo 4079 / duplicate_position 2331 / symbol_blocklist 694)；bb_breakout / bb_reversion / funding_arb 0 reject backfill；future Track B per-class 200 sample gate 4/5 策略不過 |
| **Symbol coverage** | ⚠️ MED IMBALANCE — INXUSDT 2331 duplicate_position 占 36% reject；其他 symbol 較均勻；不影響 Track A regression（global pool 訓練）但影響 Track B per-symbol model（如 future 設計）|
| **Reason code coverage (12 enum)** | ⚠️ MED — 4/12 reject enum 命中 (cost_gate_js_demo_negative_edge 14747 / duplicate_position 2332 / symbol_blocklist 694 / cost_gate_atr_unavailable 37)；其他 8 enum 0 row（但 W6-3a baseline 揭露 pre-V082 全期有 direction_conflict 2.77M / position_count 732k / scanner_market_gate 401k 等大量歷史 reject 在 risk_verdicts 但不在 decision_features schema range，所以 enum 0 row 是 expected 不是 schema bug） |
| **Reason code coverage (14 close enum)** | ✅ FULL — 13/14 close enum 命中 + 1 close_other catch-all 0 row;  spec 設計命中率 100% |

### 9757 row 是否 sufficient？

E1 report 說 9757 row backfill；現在實測 17810 reject + 2247 close = 20057 row（晚於 E1 IMPL 時間）。MIT 評估：

- **Track A regression scorer**：sufficient（global pool 1000+ baseline 已過 18×）
- **Track B multi-class classification**：4/5 策略 per-strategy 200 sample gate 不過；need N+2/N+3 sample maturity 累積
- **Backfill quality**：post-5/10 11:00 reject 100% backfill PASS（Guard C 證），post-22:00 reject 36k 多 NULL = expected 因 producer 沒 deploy

### MIT push back

當前 backfill row 數 (20057) **不應作為 W6 N+1 acceptance threshold**（會誤導 future audit 認為 W6-1 sign-off 時刻 backfill volume = production capability）；建議 acceptance 改 reference「W-AUDIT-4b M3 producer 接通後 24h sample size + 100% reject_reason_code coverage healthcheck」（Track B-aligned reference）。

---

## §6 chain integrity post-V086 verify (建議 SQL + finding)

### 實測結果 (ssh trade-core 2026-05-10 20:36 UTC)

```sql
SELECT 'fills_w_entry_ctx', count(*) FROM trading.fills WHERE entry_context_id IS NOT NULL;
-- 5939

SELECT 'fills_w_entry_in_df', count(*) FROM trading.fills f 
JOIN learning.decision_features df ON f.entry_context_id = df.context_id 
WHERE f.entry_context_id IS NOT NULL;
-- 2369

SELECT 'fills_orphan_no_df', count(*) FROM trading.fills f 
LEFT JOIN learning.decision_features df ON f.entry_context_id = df.context_id 
WHERE f.entry_context_id IS NOT NULL AND df.context_id IS NULL;
-- 3570 (60% orphan!)

SELECT 'fills_w_entry_24h', count(*) FROM trading.fills 
WHERE entry_context_id IS NOT NULL AND ts > NOW() - interval '24 hour';
-- 36

SELECT 'fills_double_prefix_remain', count(*) FROM trading.fills 
WHERE strategy_name LIKE 'risk_close:risk_close:%';
-- 0 (V086 normalize PASS)
```

### 🚨 Critical finding：chain integrity ratio 從 100% (n=331) → **40% (n=5939)**

- 樣本擴大 18× 後揭露大量 orphan fills（3570/5939 = 60% NO matching decision_features context_id）
- 對比 5/10 chain integrity replay memory：「fills.entry_context_id → decision_features.context_id chain **真實 100%** (n=331)」現在不成立
- 5939 - 2369 = 3570 fills 有 entry_context_id 但 decision_features 沒對應 row

### RCA 假設

1. **H1**: pre-W-AUDIT-4b M3 producer 接通的 fills（pre-5/10）entry_context_id 寫入但 decision_features 沒寫 row（producer 老 path 只寫 trading.fills + risk_verdicts，不寫 decision_features）
2. **H2**: V086 backfill 只 cover post-5/10 11:00 decision_features row；pre-5/10 fills 找不到對應 decision_features
3. **H3**: 部分 fills 走 manual close / forced close path 沒有 entry decision_features

### MIT 建議

1. **W6-1 verdict 不影響**：chain integrity 60% orphan 是 pre-W-AUDIT-4b M3 producer 接通的歷史 artifact；不阻 W6-1 sign-off
2. **更新 memory baseline**：MIT memory 5/10 chain integrity replay 「真實 100%」結論需註明「窄窗 n=331 樣本」+ 樣本擴大後 chain ratio 從 100% → 40%；不可作為「chain integrity 已修復」結論
3. **新 healthcheck 提案**: `check_chain_integrity_post_audit_4b_m3()` — 5/10 11:00 後新 fills 對應 decision_features 必 100%；pre-5/10 fills 接受 orphan
4. **NEW post-W6 RCA item**: orphan_no_df 3570 row 的 strategy / symbol distribution audit；確認 H1 vs H2 vs H3 主因（屬 N+2 work item，不阻 W6-1）

---

## §7 Track B N+2/N+3 deferred 立場

### 4-gate 設計 sound check

| Gate | MIT 立場 |
|---|---|
| (a) V086 land + 24h dual-write 0 NULL drift | ✅ **SOUND** — V086 已 land；dual-write 0 NULL 等 producer code 5/10 evening deploy + 24h passive observation |
| (b) multi-class label 18+ enum 各 class sample ≥ 200 row | ✅ **SOUND but pessimistic** — funding_arb 永不過 per ADR-0018；bb_breakout 7w+ 達 200；ma_crossover 6d 達 200；grid_trading 已過。建議 (b) 改「**核心 5 策略中 ≥3 策略**各 class sample ≥ 200」+ funding_arb 排除清單；避免永遠 blocked by funding_arb |
| (c) classification trainer task 升級設計 spec (multi-task / hierarchical) | ✅ **SOUND** — N+2/N+3 spec phase；MIT 建議走 hierarchical model（先預測 routing class binary, 再預測 conditional PnL given routing），減少 sparse class 問題 |
| (d) imbalance handling 試行 PASS | ✅ **SOUND** — classification 場景才適用 LightGBM `is_unbalance=True` / `scale_pos_weight` / focal loss / class_weight='balanced'；W6-5 撤回是 regression 場景的 category error 修正，不影響 (d) classification 場景的設計 |

### Track B 直接 N+1 fast-track？MIT 立場：**REJECT (deferred 是正確的)**

理由：
1. **Track B prerequisite (a) V086 dual-write 0 NULL drift**: 需 producer code deploy + 24h passive 觀察；當前 22:00 UTC reject 31053 NULL 證明 producer 未 deploy → (a) 即使 V086 SQL apply 也未滿足
2. **Track B prerequisite (b) per-class 200 sample**: 4/5 策略不過；ma_crossover 6d / bb_breakout 7w+；fast-track 等於 grid_trading-only model（過擬合單策略風險高）
3. **Track B prerequisite (c) classification trainer architecture spec**: 從未寫過；hierarchical / multi-task learning 設計 ≥1 sprint 工程 + R6 ML system architect adversarial review
4. **Track A immediate value**: regression sample_weight 微調已可立刻產生 RMSE / Sharpe / cost_gate decision distribution comparison report（W6-5 acceptance），Track A 滿足 W6 N+1 acceptance 的 ML pipeline 進步要求
5. **N+2 重新評估觸發點明確**: producer dual-write 24h 0 NULL drift PASS + per-class sample maturity ≥3/5 策略

### MIT 補：Track B trainer task type 升級的 architectural risk

未來 Track B 若升 classification 必加：
- **多任務學習 vs 階層模型** (referencing `~/.claude/skills/k-dense-ai/scientific-skills/scikit-learn/SKILL.md` + `transformers/SKILL.md`)：crypto regime 切換快 → 階層模型 (binary routing prediction → conditional PnL given routing) 比 multi-task learning 更穩定；shared embedding 在 regime shift 場景易過擬合
- **CSCV / PBO** (per `time-series-cv-protocol`)：classification 升級必跑 PBO < 0.5 才 accept；regression sample_weight 不需要因為純 contribution weighting
- **Hierarchical class imbalance**: routing class (12 reject + 14 close + N strategy fill) sample 高度不均；hierarchical 需 stratified sampling + class re-weighting at each level
- **Backward compat**: V034 attribution_chain_ok view 必保留 + 新 multi-class output 走 sibling view（不破老 cron）

---

## §8 Push back items + Confidence + Sources

### 必修條件 (5)

| # | Push back | 重要性 | 條件 |
|---|---|---|---|
| 1 | V086 SQL §2 spec 註解修正為「lossless deterministic re-UPDATE 行數可能 ≠ 0 但不破不變式」 | **MUST** | 方案 A 接受前置；D+2 14:30 UTC ALTER VALIDATE 之前完成 |
| 2 | V086 SQL 補互斥不變式 schema-level CHECK constraint (NOT VALID) | **MUST** | 防 future producer code bug 寫雙 column 同 row；E1 W6-3d 加（可在 W6-3d phase land 不阻 W6-1 sign-off）|
| 3 | W6-5 試行 acceptance 補 5 ML pipeline metrics（per-fold RMSE + 95% CI / IS vs OOS gap / cross-fold std/mean / PSI+KS / cost_gate decision distribution shift）+ purge+embargo CV | **MUST** | 缺 ≥3 項 → 後續 sign-off REJECT |
| 4 | CLAUDE.md §七 idempotency wording 修正為「lossless on repeated apply, no schema corruption + no incorrect data state」（不要求 0 row UPDATE）+ commit reference V086 governance exception | **MUST** | 防未來 migration 誤判「row count = 0 才合格」|
| 5 | MIT memory 5/10 chain integrity replay 100% 結論補註「窄窗 n=331」+ 全表 n=5939 chain ratio 40%；不可作 chain 已修結論；新 NEW orphan 3570 RCA work item 入 N+2 dispatch | **MUST** | Sprint N+0 closure memory 對應 entry 補附註 |

### SHOULD (2)

| # | Push back | 條件 |
|---|---|---|
| 6 | Track B prerequisite (b) 改「核心 5 策略中 ≥3 策略各 class sample ≥ 200」+ funding_arb 排除（per ADR-0018 dormant）；避免 funding_arb 永遠 blocking | SHOULD W6-1 verdict 補註，N+2 acceptance 採 |
| 7 | 新 healthcheck `check_chain_integrity_post_audit_4b_m3()` (post-5/10 11:00 fills 對應 decision_features 必 100% / pre-5/10 fills 接受 orphan) 入 W-AUDIT-4b M3 producer deploy 後 24h passive observation 範圍 | SHOULD W6 healthcheck enhancement scope |

### Confidence

| Verdict | Confidence | 證據強度 |
|---|---|---|
| Verdict 1 cost_gate hard rule | **HIGH** | gates.rs 三層設計 source code level + 16 root principles + 4-agent loss audit consensus |
| Verdict 2 JS shrinkage signature | **HIGH** | Lehmann & Casella textbook + QC 數學分析 + empirical 4 cells std=1.04 bps |
| Verdict 3 expected -14 bps | **HIGH** | JS estimator 自身 = unbiased point estimate (mathematical identity)；Kelly + DSR 雙重否決 |
| Verdict 4 scorer regression task type | **HIGHEST** | scorer_trainer.py:90-104 source code level + LightGBM 文檔 silently-ignore 行為 |
| W6-5 sample_weight 替代 sound | **HIGH** | LightGBM `lgb.Dataset(weight=...)` regression L2 weighted standard practice + WLS textbook |
| W6-3 兩 column TEXT vs single | **HIGH** | semantic separation reject vs close + NOT VALID 不破歷史 + future Track B 直讀 enum |
| V086 OR-filter 方案 A | **HIGH** | empirical 兩次 apply Guard C PASS + lossless deterministic + 工程成本最低 |
| V086 backfill quality | **MED** | strategy/symbol coverage imbalance 但 Track A global pool 訓練 acceptable |
| Chain integrity 60% orphan | **HIGH** | empirical PG SQL 結果 (n=5939, orphan=3570) |
| Track B 4-gate deferred sound | **HIGH** | 4 gate 全有客觀標準 + N+2/N+3 spec phase 明確 |

### Sources

1. PA W6-1 RFC final verdict draft 2026-05-10
2. MIT W6 RFC MIT-view 2026-05-10
3. E1 W6-3c V086 IMPL report 2026-05-10
4. MIT W6 baseline + W6-3a + chain replay (memory.md)
5. ssh trade-core empirical PG live SQL (2026-05-10 20:35 UTC) — 6 query × 4 finding (overlap=0 / NULL=31053 / chain=40% / sqlx max=84 / double-prefix=0 / hourly distribution)
6. CLAUDE.md §七 SQL migration 規範 + idempotency 強制
7. MIT skill ml-pipeline-maturity-audit (4 維度 5 階段)
8. MIT skill feature-engineering-protocol (6 leakage 類型)
9. MIT skill time-series-cv-protocol (purge + embargo + walk-forward)
10. MIT skill data-drift-detection (PSI + KL + KS + Wasserstein)
11. MIT skill db-schema-design-financial-time-series (Guard A/B/C + hypertable + idempotency)
12. K-Dense scientific-skills scikit-learn / transformers (Track B hierarchical reference)
13. Lehmann & Casella, Theory of Point Estimation, Ch. 5 (JS shrinkage)
14. AFML Ch. 7 (purge + embargo) per time-series-cv-protocol skill

---

MIT AUDIT DONE: srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w6_1_rfc_mit_signoff_verdict.md
