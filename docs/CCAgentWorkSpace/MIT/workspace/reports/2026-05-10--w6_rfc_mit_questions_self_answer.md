# W6 RFC — MIT 預備立場（4 questions 自答）

**日期**：2026-05-10
**性質**：D+1 W6 RFC 三角（PA + QC + MIT）入場前 MIT 視角預跑；不答 PA + QC questions
**前置依據**：
- MIT W6 baseline `2026-05-10--governance_reject_baseline_w6_rfc.md`
- PA #2 W6 RFC 自答 `2026-05-10--w6_rfc_pa_questions_self_answer.md`
- MIT chain integrity replay `2026-05-10--chain_integrity_historical_replay.md`
- Sprint N+1 dispatch v3.2 `2026-05-10--sprint_n1_dispatch_draft.md`

**Source code/runtime 取證**：
- `srv/program_code/ml_training/scorer_trainer.py:90-104` — `_lgb_params` objective='regression' / metric='rmse'（**回歸非分類**）
- `srv/program_code/ml_training/label_generator.py:30-33` — `REJECT_SAMPLE_WEIGHT = 1.0/170 = 70× imbalance + 100× safety margin`
- `srv/sql/migrations/V084__decision_features_reject_negative_label.sql:25-47` — sample_weight UDF + view
- `srv/helper_scripts/cron/ml_training_maintenance_cron.sh:83-84,5` — `AUDIT_WEEKDAY=6 / 17 3 * * *` daily 03:17 cron with weekday-6 audit gate
- ssh trade-core PG 實測 (2026-05-10 14:50 UTC): demo+live_demo `learning.decision_features` labeled=9267, rejected=7038, filled_strat=615 (5 策略)，labeled_24h=7088
- 真實 close_tag distribution >100 個獨特 string（含 risk_close:phys_lock_gate4_giveback=495 / strategy_close:grid_close_short=399 / cost_edge ratio 等 sub-reason 拍平到 string，遠複雜於 RFC F1 假設）
- fills 24h: demo+live_demo=112；7d=652

---

## Q1 — 6415 negative + 10 positive = 642:1 imbalance；V084 sample_weight 1/170 修正後仍 ~4:1，LightGBM `is_unbalance=True` / `scale_pos_weight=4` / focal loss / SMOTE 中哪個合適？

### MIT 立場：**hold A — 都不適用，因為 scorer_trainer 是 regression task 不是 binary classification**

### 論據
1. **scorer_trainer.py:94-95 證據**：`objective='regression', metric='rmse'` — 預測 ATR-normalized PnL（連續變量），**不是預測「會不會被 reject」二元分類**。`is_unbalance` / `scale_pos_weight` 是 LightGBM **classification 專用** 參數（binary/multi-class objective），對 regression 完全無效（`lgb.train` 會 silently ignore）。MIT Q1 隱含假設「LightGBM 把 reject 當 negative class fill 當 positive class」是錯的。
2. **真實機制**：V084 sample_weight 走 `lgb.Dataset(weight=...)` 路徑，對 regression objective 是「L2 loss 加權」— 把 reject row label_net_edge_bps=0 的 RMSE 貢獻乘 1/170，等價降低其在 loss landscape 的 leverage。**這是「貢獻量加權」非「class balancing」**。reject:fill 4:1 weighted 後等於 reject 在 RMSE loss 占 80%×(1/170) ≈ 0.47%，fill 占 20%×1.0 = 20% — fill 已 dominate，不需要再做 imbalance handling。
3. **真要 imbalance handling 應該在 multi-task 拆分後做**：W6-3 multi-class label split (`rejected_cost_gate` / `rejected_duplicate_position` / fill) 若改 trainer 為 classification（如「預測 routing decision」），那才需 `class_weight='balanced'` 或 focal loss。當前 regression 場景談 imbalance handling 是 category error。
4. **真實 imbalance 風險在 LinUCB 不在 LightGBM**：`linucb_trainer.py:47-56` 用 `decision_outcomes` (joined) 作 reward，rejected 不進 LinUCB pool（reject 沒有 `decision_outcomes` row）。所以 LinUCB **不受 642:1 imbalance 影響**，而 scorer LightGBM regression 用 sample_weight 已正確修正。MIT Q1 的「imbalance handling 算法選擇」是錯題。

### 架構影響
- **無 V### / cron schedule / pipeline schema 動**。V084 sample_weight 設計（regression weighting）正確。
- **若 W6-3 multi-class label split 落地後 trainer 也升 classification**，那才開新 sub-task：「W6-5 LightGBM imbalance handling 試行」**前置**先評估「trainer task 從 regression → multi-class classification 是否該升」。當前 dispatch v3.2 W6-5 跳過這層討論直接 `is_unbalance=True` 試行 = 套錯參數到錯模型。

### Dispatch v3.2 對齊
- ❌ **與 §3.0 W6-5 設計衝突**：dispatch 寫「試行 `is_unbalance=True` 或 `scale_pos_weight=4`」對 regression scorer 無效。
- ⚠️ **建議**：W6-5 先**確認 trainer task type**（regression vs classification）；若維持 regression → W6-5 改為「sample_weight robustness 試行」（探索不同 weight ratio 1/100 / 1/170 / 1/300 對 RMSE/Sharpe 影響），不是 LightGBM imbalance flag；若隨 W6-3 升 classification → 才走原 dispatch 設計。
- ⚠️ **建議**：W6-5 acceptance 加「trainer task type confirm document」明文記錄。

---

## Q2 — features_jsonb 17-dim 全 market state 0 reject reason — train 出來模型只學到「在這 market state 下會被拒」**不學會「為何拒」**。是否該等 V086 加 reject_reason_code 才開 ML training？

### MIT 立場：**hold B（**反 PA #2 Q3**）— 不必等 V086；當前 trainer 設計 reject row 連 features 一起進 pool 已正確學「entry-state 預測 PnL」**

### 論據
1. **scorer_trainer 的學習目標是「給 entry-state，預測 net PnL」不是「給 entry-state，預測 routing decision」**。V084 reject row label_net_edge_bps=0 對 regression 是「中性樣本」（既非利潤也非虧損），意義 = 「在這 state 下 governance 認為 EV=0」。模型學到的是 **「這 state 下歷史 outcome 期望值低」**。**reject_reason 對「預測 PnL」這個 task 是冗餘**（PA Q3 明文同意 V086 立刻做但 ML retrain enable 等 4-gate；MIT 補充「retrain enable 不必等 V086 land」是更激進立場）。
2. **真要學「為何拒」需要不同 task**：multi-task learning 或 hierarchical model（先預測 routing class，再預測 PnL given routing），這是 N+2/N+3 architecture 工作不是 N+1 schema add 能解。當前 V086 只能補 metadata 給 future ML pipeline，**不會** retroactively 改善現有 scorer。
3. **Dual-write 24h drift gate 設計**（為 V086 land 後評估 reason_code 質量）：
    - `t0`: V086 land + W-AUDIT-4b M3 producer dual-write reject_reason_code
    - `t0+24h`: 跑 healthcheck `check_reject_reason_code_dual_write_drift()` — `SELECT COUNT(*) FROM learning.decision_features WHERE label_close_tag='rejected_governance' AND reject_reason_code IS NULL AND ts > t0` → 0 == PASS / >0 == FAIL（writer 接線漏寫）
    - 同步驗 `risk_verdicts.reason` 字串匹配 `reject_reason_code` enum（cost_gate(JS-demo)→`cost_gate_negative_edge` / duplicate_position→`duplicate_position`）— sample 100 row spot-check
4. **Real ML training enable gate 是「sample maturity」非「reason_code maturity」**：當前 7038 reject + 615 fill labeled (5 策略總和)，已過 LightGBM regression 1000 row baseline。W6-5 imbalance 試行可立刻跑 baseline AUC/RMSE 對比，不需等 V086。

### 架構影響
- **無 V### 動**（與 PA Q3 hold A 不一致；PA 主張 V086 立刻做，MIT 立場「V086 是 future-proof 但對當前 scorer task 非阻塞」）。
- **新 healthcheck 設計**：`check_reject_reason_code_dual_write_drift()` 屬 V086 land 後配套，不在 W6 scope；建議併入 W6-2 acceptance（V086 land 24h 後 0 NULL drift）。

### Dispatch v3.2 對齊
- ⚠️ **與 §6 acceptance gate 第 5 條「ML retrain 4-gate」MIT 質疑**：4-gate 中第 1 條「V086 land」對當前 scorer regression task 是過度保守。應拆兩 track：
  - Track A（regression scorer 微調）：可立即跑 W6-5 sample_weight robustness（不需 V086）
  - Track B（未來 multi-task / classification）：才需 4-gate（V086 + dual-write 24h + multi-class 200 row + imbalance 試行）
- ⚠️ **建議補**：W6-5 試行報告分 (a) 當前 regression scorer + sample_weight ratio sensitivity 對比 (b) 假設 multi-class classification 升級時的 imbalance handling 模擬，**兩 track 並行報告**。

---

## Q3 — label_close_tag = 'rejected_governance' 把所有 reject 拍平為一個類 — 是否該 split `rejected_cost_gate` / `rejected_duplicate_position` 兩 multi-class label？

### MIT 立場：**hold A — 應 split 但設計遠比 dispatch v3.2 W6-3 寫的複雜（「3 類」遠不夠）**

### 論據
1. **真實 close_tag distribution >100 unique values**（PG 實測）：除了 `rejected_governance` (7038) + 5 strategy fill (grid 374 / ma 167 / bb_breakout 27 / bb_reversion 4 / funding_arb 43)，還有：
    - `risk_close:phys_lock_gate4_giveback` 495
    - `strategy_close:grid_close_short` 399
    - `risk_close:phys_lock_gate4_stale_roc_neg` 20
    - `risk_close:fast_track_reduce_half` 12
    - `risk_close:COST EDGE: ratio 0.35 >= 0.20, pnl 0.32% >= min_profit 0.30%...` (各種 sub-reason 字串拍平到 close_tag)
    - `strategy_close:funding_arb_exit: rate=-0.001147 basis=0.500%` (40+ unique 字串)
    - `risk_close:DYNAMIC STOP: pnl -10.47% <= -10.46%...`
    - `ipc_close_all` / `regime_shift` / `abandoned`
2. **dispatch v3.2 W6-3 寫「3 類」（cost_gate / duplicate_position / other）僅覆蓋 reject 端**，**完全沒處理 fill 側 close 原因**。fill 側 strategy_close vs risk_close vs cost_edge 是不同 PnL 分布族（risk_close 通常 -SL；strategy_close 通常 +TP；cost_edge 通常 +micro profit），**這對 regression scorer 預測 PnL 是更大的 signal**。
3. **正確 multi-class label schema 設計**（MIT 提案）：
    - **Group A — reject reasons**（從 risk_verdicts.reason 提取）：`reject_cost_gate` / `reject_duplicate_position` / `reject_atr_unavailable` / `reject_scanner_advisory` / `reject_volatility` / `reject_dsr` / `reject_position_size` / `reject_margin_util`（8 類，per V086 enum）
    - **Group B — fill close reasons**（從 close_tag 字串前綴解析）：`strategy_close_*` / `risk_close_dynamic_stop` / `risk_close_trailing_stop` / `risk_close_phys_lock_*` / `risk_close_fast_track` / `cost_edge_close_profit` / `cost_edge_close_loss` / `ipc_close_all` / `regime_shift_close` / `abandoned_no_close`（10+ 類）
    - 共 18+ class，**不是 3 類**
4. **Schema migration 影響**：V086 設計需加 `reject_reason_code text` + `close_reason_code text` **兩** column（不是一個 jsonb）+ migration 對 existing 9267 row 做 backfill mapping（從 `risk_verdicts.reason` regex parse + 從 `label_close_tag` string prefix split）。對既有 label upgrade strategy = forward-only NOT VALID CHECK + backfill cron N 天後 ALTER VALIDATE CONSTRAINT。
5. **對既有 `attribution_chain_ok` view 不破**：V084 view 仍用 `label_net_edge_bps IS NOT NULL` 條件；新 column 純 additive 不改 view WHERE。但 multi-class trainer 升級需重 Phase B 改 scorer/quantile/cpcv pipeline read schema。

### 架構影響
- **V086 schema 動**（同 PA Q3 hold A）。**MIT 補充**：兩 column 設計（reject_reason_code + close_reason_code）非單一 jsonb；遵 Guard A/B/C；NOT VALID CHECK + backfill cron。
- **Trainer pipeline 升級遠超 W6 scope**：multi-class label 落地後，scorer_trainer 對 multi-class label 的處理 = ignore（regression 看 label_net_edge_bps 不看 close_tag）；若要學 close_reason_code → 多任務學習架構，N+2/N+3 spec。
- **healthcheck 新增**：`check_close_reason_code_coverage()` — fill row close_reason_code 100% 非空；reject row reject_reason_code 100% 非空（dual-write 24h drift gate）。

### Dispatch v3.2 對齊
- ⚠️ **與 §3.0 W6-3「拆 3 類」嚴重低估範圍**。建議 W6-3 重 scope：
  - W6-3a：**audit close_tag string distribution** 完整列出 unique value + frequency（1 day PA + MIT）— **prerequisite**
  - W6-3b：**設計 reject_reason_code enum (8 類)** + **close_reason_code enum (10+ 類)** 完整 spec
  - W6-3c：V086 schema add **兩** column + backfill cron + NOT VALID CHECK
  - W6-3d：trainer pipeline read 兩 column（regression 仍 ignore 兩 code，但 future multi-task 接口準備好）
- ⚠️ **建議**：W6-3 從 1 day extend 到 3 day（spec + IMPL + 24h dual-write drift verify）。

---

## Q4 — fill 10 條 / 3.5h ~ 70/day extrapolate；達 LightGBM 1000+ row 訓練 baseline 需 2 週純累積 — 與 cron weekly 訓練 schedule 對不對齊？

### MIT 立場：**depends — depends on (1) trainer task type (regression vs classification) (2) min_samples gate value (3) cron weekly vs daily 觸發頻率**

### 論據
1. **真實 fill rate 遠快於 baseline 假設**：
    - W6 baseline (3.5h window): 10 fills → 70/day extrapolate
    - **PG 實測 (2026-05-10 14:50 UTC)**: trading.fills demo+live_demo **24h=112，7d=652**
    - 全期 5-strategy labeled fill = 615 (n=5d window 起)
    - fills 累積速率 ~93/day actual（不是 70 extrapolate）
    - **1000-fill baseline 達成日期估算**：
      - Pure fill-only training: (1000-615)/93 ≈ 4 day → **2026-05-14**
      - 含 reject row pool (V084 weighted): 已 7038 reject + 615 fill = 7653 total，**已過 1000 baseline**
    - **MIT Q4 「2 週純累積」過度悲觀**，因 (a) fill rate 比 baseline 高 (b) reject row 也算 training pool（V084 weighted）
2. **cron schedule 真實設定**：`ml_training_maintenance_cron.sh:5,77`
    - 全 cron daily `17 3 * * *` (UTC 03:17)
    - **5 ML training jobs (linucb_trainer / scorer_trainer / quantile_trainer / mlde_shadow_advisor / mlde_demo_applier) DAILY**
    - **5 audit jobs (thompson / optuna / cpcv / dl3_foundation / weekly_report) DAILY 但 weekday-6 (Sunday) audit gate**（per memory `feedback_v_migration_pg_dry_run` `project_2026_05_09_ml_training_cron_weekly`）
    - **scorer / linucb / quantile = 真 daily retrain，不是 weekly**
    - MIT Q4 假設「cron weekly 訓練」**錯**：實際 daily retrain，sample 累積 → 訓練 → ONNX export 每天跑
3. **min_samples gate**：`ml_training_maintenance_cron.sh:84` `MIN_SAMPLES=200`（per-strategy）
    - per-strategy 5-day 累積（ma 167 row 不過 200，bb_breakout 27 不過，bb_reversion 4 不過，funding_arb 43 不過）— 4/5 策略**仍不過 200 baseline**
    - 真 alignment issue = **per-strategy sample gate**，不是 total pool size；當前 grid_trading 374 過 gate（dispatch alignment 對 grid 沒問題），其他 4 策略都 dormant 等 sample 累
4. **錯位 vs 對齊判斷**：
    - **TOTAL pool**: ✅ 對齊（已過）
    - **PER-strategy gate (200)**: ❌ 4/5 策略未達；ma_crossover 5d 167 row 推估 6d 達 200，bb_breakout 5d 27 row 推估 7w+ 達 200，funding_arb dormant by design 永不達
    - **cron daily retrain**: ✅ 對齊（不是 weekly），但 grid_trading 已每天 retrain 5 day +
    - **trainer task type**: regression scorer 用 7038 reject + 615 fill weighted = 已可訓；multi-class 升級後需各 class 200 sample → bb_breakout / bb_reversion / funding_arb 可能 N+2/N+3 都不過

### 架構影響
- **無 V### / cron 動**（cron 已 daily 對齊，min_samples=200 是 env-var 可調）。
- **新 healthcheck 設計**：`check_per_strategy_sample_gate()` — 5 策略各列 30d sample 對比 MIN_SAMPLES (200)；標 PASS/WARN/FAIL；funding_arb 排除（dormant by design）。

### Dispatch v3.2 對齊
- ⚠️ **§3.0 W6-5 LightGBM imbalance 試行 D+5 跑** 只能用 grid_trading sample (374 row)，**ma_crossover (167) / bb_breakout (27) / bb_reversion (4) 仍不夠**做 per-strategy 試行。建議 W6-5 acceptance 改「grid_trading-only baseline + per-strategy gap report」。
- ⚠️ **建議**：W6-7 [61] silence healthcheck（PA #2 提出）+ MIT 新提 [62] `check_per_strategy_sample_gate()` 同窗，**5 策略 per-strategy training readiness 觀測**。
- ⚠️ **建議**：W6 acceptance §6 補「fills/day rate snapshot baseline」健檢項，避免 N+2 又用 70/day stale value 作決策。

---

## §5 MIT 預備立場總結（W6 RFC D+1 入場帶這個）

| 維度 | MIT 立場 | 對 v3.2 dispatch 的影響 |
|---|---|---|
| Q1 imbalance handling 算法 | **hold A** 都不適用（scorer 是 regression）；真要做先確認 trainer task type | W6-5 重設計：sample_weight ratio sensitivity (regression) + classification 模擬（兩 track 並行）|
| Q2 V086 prerequisite | **hold B** 不必等（與 PA #2 Q3 hold A 衝突）；當前 regression task reject row label=0 已正確 | W6 acceptance 4-gate 拆 Track A (regression 微調 immediate) + Track B (multi-class future) |
| Q3 multi-class label split | **hold A** 應 split 但 3 類 → 18+ 類；reject (8) + close (10+) 兩 column 設計 | W6-3 從 1 day extend 3 day，3 階段 audit + spec + IMPL |
| Q4 sample rate vs cron | **depends** 對齊現況：fill rate 93/day 比 baseline 70 高，cron daily 非 weekly，total pool 過；per-strategy 4/5 策略仍不過 200 gate | 新 [62] check_per_strategy_sample_gate；W6-5 改 grid_trading-only baseline |

**核心整體立場**：W6 真正是 **ML pipeline architecture 重 design**，不是 schema add column 工作。當前 dispatch v3.2 W6-5 / W6-3 嚴重低估範圍，需補 trainer task type confirm + close_tag distribution audit + per-strategy sample gate 觀測。**16 根原則合規 16/16；硬邊界觸碰 0**（all read-only audit + spec change）。

PA #2 / QC 視角（cost_gate hard rule / duplicate_position / counterfactual edge / DSR）留 D+1 三角；MIT 與 PA 在 Q3 strong agree 但深度不同；MIT 與 PA 在 Q2 / Q3 enum scope / Q4 cron weekly 假設 push back。

---

## §6 Dispatch v3.2 update 建議（出建議 only，operator 拍板）

| # | 位置 | 建議 |
|---|---|---|
| 1 | §3.0 W6-1 RFC | 加入「**trainer task type (regression vs classification) confirm document**」作 RFC verdict 必含產出 |
| 2 | §3.0 W6-3 重 scope | extend 1 day → 3 day；分 W6-3a (close_tag distribution audit, 0.5d) + W6-3b (enum spec 18+ class, 0.5d) + W6-3c (V086 兩 column add + backfill, 1d) + W6-3d (trainer pipeline read schema update, 1d) |
| 3 | §3.0 W6-5 重設計 | 不直接套 LightGBM `is_unbalance=True`；先確認 trainer task type；regression case 改「sample_weight ratio sensitivity 試行」（1/100 / 1/170 / 1/300 對 RMSE 影響）；classification case 才走原 imbalance handling |
| 4 | §3.0 W6-7 補 [62] | 新增 [62] `check_per_strategy_sample_gate()` 與 W6-7 [61] 同窗；5 策略 30d sample vs MIN_SAMPLES (200) baseline；funding_arb 排除（ADR-0018 退役）|
| 5 | §6 Acceptance Gate 改 | 第 5 條 ML retrain 4-gate 拆兩 track：Track A regression 微調 (immediate, 不需 V086)；Track B multi-class future (需 V086 + dual-write 24h + per-strategy ≥200 + imbalance 試行 PASS) |
| 6 | §6 Acceptance Gate 補 | 加「**fills/day rate snapshot baseline**」健檢項（每週 grid_trading / ma_crossover / bb_breakout / bb_reversion 各 fills/day 入 healthcheck），避免 stale 70/day value 作 N+2 決策 |
| 7 | §3.0 W6-2 acceptance 補 | V086 land 後 24h healthcheck `check_reject_reason_code_dual_write_drift()` 必 PASS（0 NULL drift 對 post-V086 sample）+ 100 row spot-check `risk_verdicts.reason` 字串匹配 enum |

---

MIT AUDIT DONE: srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w6_rfc_mit_questions_self_answer.md
