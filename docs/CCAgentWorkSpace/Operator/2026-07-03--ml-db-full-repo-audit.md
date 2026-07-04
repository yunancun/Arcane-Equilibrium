# MIT ML/DB 全倉審計 — 2026-07-03

**範圍**：srv/ 全倉（rust engine / control_api / helper_scripts / sql migrations / 治理文檔），MIT 職能視角（DB schema、ML pipeline 成熟度、feature leakage、CV 方法論、data drift）。
**證據紀律**：Mac 靜態 grep + ssh trade-core read-only（docker exec psql SELECT-only、crontab -l、log ls）。0 mutation、0 restart、0 migration apply。
**Runtime 基準**：sqlx head=145（V141-V145 已 apply 2026-06-17；V146 repo 有檔、prod 未 apply）；engine Demo-only 活著（market.l1_events 寫至 now）；DOWN 後續 regime 未重驗。

---

## 0. Verdict

**FINDINGS（無 CRITICAL；2 HIGH 級結構性缺陷 + 1 HIGH 級運維斷層）。**
ML 決策層全系統仍 ≤ Shadow（與 06-14 cold audit 一致），但本輪發現三個新的結構性問題：
(1) 量化訓練集被 99.9% 合成 0.0 reject label 淹沒 → quantile/scorer lane 結構上永遠過不了 gate；
(2) features.online_latest 凍結於 2026-05-06（feature_tx 只接 paper pipeline）→ G3 drift 偵測 lane 全鏈 no-op → canary promotion PSI gate 結構性不可滿足；
(3) 2026-06-27 crontab 置換砍掉 ~20 條 evidence/monitor lane（含 passive_wait_healthcheck 全部 90+ 檢查）→ silent-dead 偵測整體下線。

---

## 1. Migration 審計（V141-V146，since sqlx head 139）

| V### | Guard A | Guard B | Guard C | Idempotent | 狀態 |
|---|---|---|---|---|---|
| V141 kline_calibration | ✅ 完整 | ✅ 4 欄型別反射 | ✅ 後驗 PK+index | ✅ 設計到位 | applied，**0 row（cron 未裝）** |
| V142 trades/ob_top | ❌ **header 聲稱有、body 無** | ❌ 無 | ❌ 無 | ✅ IF NOT EXISTS 鏈 | applied，寫入活躍 |
| V143 l1_events | ❌ **header 聲稱有、body 無** | ❌ 無 | ❌ 無 | ✅ | applied，寫入活躍 |
| V144 strategist_promotions | ❌ **header 標 "(Guard A)"、body 無 DO-block**；index 僅 "Guard C 等價" 無 shape 驗證 | ❌ | ⚠️ | ✅ | applied，0 row（尚無 promote 事件，fail-closed 設計正常）|
| V145 fills.maker_markout_bps | ✅ 模板級（前置 V028 欄驗證 + bootstrap 斷言）| ✅ double precision 反射 | ✅ partial index | ✅ | applied，209 row 前向累積 |
| V146 comment fix | ✅ 前置欄存在驗證 | n/a | n/a | ✅ COMMENT 冪等 | **repo 有檔、prod head=145 未 apply** → V145 誤導性 COMMENT（"Positive = adverse"）仍活在 prod，等下次 engine auto-migrate |

**F-11（MED, FACT, high conf）**：V142/V143/V144 三張新表 `CREATE TABLE IF NOT EXISTS` 無 Guard A，違反 CLAUDE.md §Data 與 MIT 硬約束 #3（V023 silent-noop 防線）；且 header scope 注釋**聲稱** Guard A 存在 = 注釋不誠實，E2 review checklist 按聲稱簽核的風險。實害受限（三表當時為 greenfield 新表，legacy stub 機率低），但模板紀律破口已成先例。fix：retrofit Guard A DO-block（mirror V141 §B）+ 修正 header。

**F-12（LOW, FACT）**：V142/V143 `ALTER TABLE ... SET (timescaledb.compress)` + `add_compression_policy/add_retention_policy` 無 `pg_extension` 條件包裹，而同檔 hypertable 建立是條件式 —— 同檔內 guard 不一致；vanilla PG 上 migration 鏈會中斷（V006 已知缺陷再複製，CI 必須永遠用 timescale image）。

**F-13（INFO, FACT）**：V146 restart-gated：prod 的 maker_markout_bps COMMENT 目前仍是 V145 誤導版（把 spread-capture 說成 adverse selection）。下游若有人按 prod COMMENT 讀語義會踩 QC/PA Hybrid-C 已裁決的坑。

**正面**：V141/V145/V146 是 Guard 模板的示範級實作；CI（ci.yml:103,116）已接 `schema_contract_test` + `audit_migrations.py`（06-14 P1-SCHEMA-1 HIGH 已閉環）。

---

## 2. ★ F-1（HIGH, FACT, high conf）訓練集 99.9% 合成 0.0 reject label 污染 — quantile/scorer lane 結構性死路

**鏈條（全部親證）**：
1. `intent_processor/mod.rs:1697`（W-AUDIT-4b-M3 設計）：governance/cost-gate reject path 對 `learning.decision_features` 寫 `label_close_tag='rejected_governance'` + `label_net_edge_bps=0.0`（合成 label，非真實 outcome）。
2. `parquet_etl.py:459` 標準訓練查詢 `WHERE label_net_edge_bps IS NOT NULL` **無 label_close_tag 排除、無 class weight**（`load_training_data` 逐行接受迴圈亦無過濾；`quantile_trainer.compute_sample_weights` 只有時間衰減權重，V084 sample_weight UDF 未進此路徑）。
3. **PG 實測（30d demo）**：ma_crossover reject 1,876,372 @0.0 vs 真實 fill label 81（≈23,000:1）；grid_trading 237,722:261；bb_reversion 1,800:23。`decision_features` 30d reject share = **99.91%**（14.83M rows 總量，~55k/day 增長）。
4. **後果實測（2026-07-03 acceptance report, grid_trading demo）**：pinball skill = **0.0**（q10/q50/q90 全部）、empirical coverage = **0.9988 三個分位完全相同**（= holdout 中 0.0 label 佔比，模型退化為常數 0 預測器）、全 hard gate fail → verdict shadow_only。model_registry ids 40-47（train_date 2026-07-03，training_sample_size 3,911,361 / 492,485 / 1,845）全 shadow。

**裁決**：acceptance gates fail-closed 正確擋下（無 live 危害），但這是 **evolution-blocker**：只要 reject 洪水在訓練池裡，pinball skill 恆 ≈0，quantile/scorer lane 永遠不可能從 Shadow 畢業 —— 每天燒訓練計算產出結構性註定失敗的 artifact，registry 的百萬級 sample_count 給人「資料很富」的假象（實際 informative label 只有幾十到幾百個 fill）。M3 設計的原意（reject row + V084 weight 恢復 70:1 imbalance）只在 ADPE reward view 路徑成立，quantile/scorer 路徑把它當等權真 label 用 = 設計語義跨管線洩漏。
**fix 方向**：quantile/scorer ETL 加 `AND label_close_tag IS DISTINCT FROM 'rejected_governance'`（或按 M3 原設計接 V084 weight 並將 reject 視為 censored/separate class）；acceptance report 增列 label 組成分佈（zeros_share）作硬 gate。

**F-8（MED, FACT+INFERENCE）連帶**：`mlde_shadow_advisor` 自 ≥07-01 起每日 run 全 error（`QueryCanceled` 5s statement timeout ×3 日，status log 親證；06-14 我測的「timeout 未生效」現已生效）。其查詢 `JOIN learning.decision_features df ... WHERE df.label_net_edge_bps IS NOT NULL`（advisor:203）在 label 洪水後 join 基數暴增 = 可信根因（INFERENCE）。後果：MLDE advisory lane 全死，`mlde_demo_applier` 恆 no_eligible_recommendations。**F-9（MED, FACT）**：同一 run 中 `linucb_trainer` 以 arms=0/total_pulls=0 回報 "ok" —— 空訓練標成功（fake-success 型 status 語義）。

---

## 3. ★ F-2（HIGH, FACT, high conf）G3 drift 偵測 lane 全鏈 no-op — feature_tx paper-only 接線（MARKET-KLINES-STALE-1 同款教訓未 retrofit）

**鏈條（全部親證）**：
1. `features.online_latest` = 43 rows，**max updated 2026-05-06（凍結 ~2 個月）**。
2. `main_pipelines.rs`：paper pipeline 拿 `feature_tx: writers.feature_tx.clone()`（:369），**demo（:493）與 live（:637）拿 `feature_tx: None`**；paper 預設關（OPENCLAW_ENABLE_PAPER）→ 唯一 producer 死。緊鄰的 `market_data_tx` 注釋就寫著 MARKET-KLINES-STALE-1（paper-only 設計曾把 klines 寫死）的教訓 —— **同款缺陷在 feature_tx 上原樣復發，未 retrofit**。
3. `run_drift_detector`（tasks.rs:790 有 spawn；`observability.feature_baselines` 2006 active）讀 `features.online_latest` 最新向量 → 凍結資料 → `observability.drift_events` = **0 row（有史以來）**；`observability.model_performance` = 0。
4. `canary_promoter._query_max_psi` 讀 drift_events（0 row → None）+ `require_promoting_quality_metrics=True` → promoting→production quality gate 結構性不可滿足；疊加 `decision_shadow_exits`=0（3 份 TOML shadow_enabled=false）+ promoter 本身 default-OFF（OPENCLAW_AUTO_PROMOTE_ENABLED）且 runner 無 cron → **promotion 四重鎖死**。

**裁決**：drift 偵測（我的 skill 第 5 軸）在本系統的實際成熟度 = **Skeleton（spawned 但食材凍結，0 產出）**。這同時是 over-gate 型 evolution-blocker：即使未來有值得晉升的 model，PSI 證據軸根本無法產生。
**fix 方向**：feature_tx 比照 MARKET-KLINES-STALE-1 改所有 pipeline 共享（writer 端 upsert 冪等已支持多 producer）；或至少接 demo pipeline。retrofit 後驗 drift_events 開始累積、check 哨兵補 freshness。

---

## 4. ★ F-3（HIGH, FACT；成因 ASSUMPTION）2026-06-27 crontab 置換 — ~20 條 evidence/monitor lane 同時死亡

**FACT**：`crontab -l` 現僅 5 條（demo_learning_evidence_audit / sealed_horizon_probe_preflight / cost_gate_learning_lane / demo_learning_stack_healthcheck / ml_training_maintenance，全 pin EXPECTED_HEAD=00a78d92）。/tmp/openclaw/logs 顯示以下 lane 全部凍結於 **06-27 17:00-18:00 CEST**：panel_aggregator_health、recorder_health、edge_label_backfill（30min 級）、adpe_runner、polymarket_axis + leadlag_ic、alpha_discovery_throughput、canary_audit_pg_writer、halt_audit_pg_writer、l2_memory_distill、recorder_mm_verdict、flash_dip 各 lane、edge_estimate_snapshots_cycle、vol_event_trigger、gate_b_watch、bybit_announcement_sentinel、ref21_symbol_universe_snapshot、wave9_replay_no_live_mutation_watch、replay_key_rotation_check。**passive_wait_healthcheck（90+ 檢查的 runner）無任何 log/heartbeat 存在、不在 crontab** —— check_91（kline calibration heartbeat）等哨兵全部停擺 = 偵測 silent-dead 的機制本身 silent-dead。

**已證實下游 staleness**：`market.symbol_universe_snapshots` max=06-27 17:20（**survivorship lifecycle 權威凍結 6d**，此後 delist/list 不可見，PIT survivorship 分析劣化）；`learning.edge_estimate_snapshots` max=06-19（審計快照 lane 停 14d）；`agent.agent_memory`=99（與 06-14 相同，L2 記憶零增長）；`research.aeg_regime_labels` max signal_ts=**2026-06-01（32d stale）**（06-14 已報的 regime feeder 死管道未修，越陳越舊）；`learning.bayesian_posteriors` max=06-21（weekday-gate 下 06-28 該跑未跑 —— cron 06-27~06-30 間離線的旁證；07-05 週日可自癒，須驗證）。

**緩解事實**：label backfill 雖失去 30min cadence，但 `max(label_filled_at)`=07-03 03:27 → 每日 ml_training_maintenance 內含路徑仍在補 label（cadence 降級非死亡；unlabeled 7d backlog 僅 12）。

**ASSUMPTION（需 operator 裁決）**：置換可能是 06-27~06-30 soak-loop 治理期的刻意精簡（5 條倖存 cron 全屬該 loop），但我找不到記錄此決策的 TODO/report 條目 —— 若非刻意，這是一次未被察覺的運維事故；**無論何者，healthcheck runner 不在倖存清單內都是缺陷**（監測不應隨 loop 治理一起下線）。
**fix 方向**：operator 確認意圖 → 至少恢復 passive_wait_healthcheck + recorder_health + ref21 universe recorder + edge_label_backfill 獨立 cadence；把「crontab 全量置換」納入變更審計（crontab 差分留痕）。

---

## 5. ML Pipeline 成熟度評級表（step 0 全部本輪實測）

| Component | Writer spawn | Consumer | Row 累積 | Decision impact | Stage | Blocker |
|---|---|---|---|---|---|---|
| learning.exit_features | ✅ Rust live | offline research only | 3637 fresh 07-03（demo 2388/live_demo 1192/paper 57）| ❌ | **Shadow** | live 端無 reader（06-14 結論不變）|
| learning.decision_shadow_exits | spawn 但 3×TOML shadow_enabled=false | — | 0 | ❌ | **Skeleton** | flag off（設計 dormant）；同時卡死 canary promoting gate 的 500-obs 需求 |
| model_registry / quantile trio | ✅ daily cron 03:17（**已解凍**，train_date=07-03，ids 40-47）| resolver `resolve_latest_production_artifact` **0 caller**；live combine layer 仍 `shadow_mock_v1` mock | 8 fresh rows 全 shadow_only/0 promoted | ❌ | **Shadow（degenerate）** | F-1 label 污染 → gate 恆 fail；resolver 斷線 |
| canary promotion | promoter default-OFF、runner 無 cron | — | 0 transitions | ❌ | **Foundation** | 四重鎖死（見 F-2）|
| G3 drift detector (PSI/ADWIN) | ✅ spawned | canary_promoter 讀 drift_events | **0 events ever** | ❌ | **Skeleton/broken** | F-2 feature_tx paper-only |
| features.online_latest | spawn 但 demo/live tx=None | drift detector, parquet_etl join | 43 rows 凍結 2026-05-06 | ❌ | **dead** | F-2 |
| bayesian_posteriors / thompson | weekly（weekday gate）| `select_next_arm` **0 production consumer** | 277 rows，max 06-21 | ❌ | **Shadow** | regime 欄=engine_mode 值（06-14 HIGH 未修）；07-05 自癒待驗 |
| linucb | daily | shadow compare only | arms=0 / total_pulls=0 | ❌ | **Skeleton** | F-9 空訓練標 ok |
| MLDE advisor→applier | daily | applier 讀 recommendations | advisor **每日 error**（timeout）| ❌ | **broken** | F-8 |
| market.trades / ob_top（V142）| ✅ live | 研究待用；recorder_health cron 死 | 213M / 86.6M fresh-to-now，14GB/5.9GB，compression+retention 活 | ❌（research lane）| **Shadow** | 監測死角（F-3）|
| market.l1_events（V143）| ✅ live | recorder_mm_verdict cron 死 | 230M fresh，**28GB > PA 硬上界 ~26GB**（realistic 預估 3-7.5GB 超 4-9x）| ❌ | **Shadow** | F-14 storage 預估失準 + 監測死角 |
| fills.maker_markout_bps（V145）| ✅ loop_exchange live | mm_verdict cron 死 | 209 rows fresh | ❌ | **Shadow** | consumer 停擺 |
| research.kline_calibration（V141）| bin+cron script 存在、**cron 未裝** | R4 recal queue | **0 rows / 16d** | ❌ | **Foundation** | F-6：truth-drift guardrail 從未跑；check_91 哨兵又因 F-3 停擺 = 雙盲 |
| learning.strategist_promotions（V144）| ✅ route 內 fail-closed INSERT（:988,:1034）| demote precondition / GUI | 0（無 promote 事件）| （事件時 = live param 變更審計）| **Foundation（正常）** | 無 |
| L2 memory (V139/V140) | distill cron 死 | recall flag 狀態未重驗 | 99 rows 凍結 | ❌ | **Shadow-frozen** | F-3 |
| listing_capture / residual alpha / hidden_OOS / FDR | — | — | 全 0（不變）| ❌ | **Foundation/inert** | 與 06-13/14 審計一致 |

**整體**：Production=0、Canary=0、Shadow≈7（其中 2 條 broken、1 條 degenerate）、Skeleton=3、Foundation=4。ML 對真實決策的影響 = **0**（與 06-14 一致；本輪新增證據：訓練解凍但被 F-1 鎖死在 degenerate Shadow）。

---

## 6. Feature Engineering 6-leakage 逐項（quantile/scorer 訓練路徑）

| 類型 | 判定 | 證據/備註 |
|---|---|---|
| Look-ahead | 結構上 OK + 1 個 fail-open 破口 | feature=決策時刻 FeatureVectorV1（PIT by construction）；label=事後 backfill。**F-4（MED）**：`train_quantile_trio` embargo 在 `<50 樣本` 時**靜默跳過**（只 log warning，acceptance report 無 embargo_enforced 欄）→ 小樣本 slice（如 bb_reversion 23 個真 fill）恰是最可能跳 embargo 的 cohort，下游 gate 看不到 |
| Target leakage | OK | label window 在 feature ts 之後；tail holdout + embargo（enforced 時）分離 |
| Survivorship | **劣化中** | 訓練池本身無 lifecycle 過濾（decision_features 只含實際交易過的 symbol = 天然 PIT）；但 `symbol_universe_snapshots` 凍結 06-27（F-3）→ 所有依 lifecycle 的研究 lane（P3b altcap、carry universe）向前劣化 |
| Cross-section | **F-5（LOW-MED, INFERENCE）** | `label_generator.generate_labels` winsorize 分位數在**全窗口**（含未來 fold）上計算後才進 CPCV —— full-sample statistic 教科書式輕度 leak（僅 scorer 路徑；quantile 路徑 label 不經此變換）|
| Time-zone | OK | ts 全 timestamptz/ms-UTC；未見跨時區運算 |
| Resample boundary | OK + 監測盲 | R1 WS-confirmed-candle 直寫真值（step_1_2 :143 起注釋鏈完整）；但持續驗證機制（V141 calibration）0 row = 修好之後**沒有任何東西在驗證它保持修好**（F-6）|

**shift(1) compliance**：`shift1_compliance.py` / `is_oos_gap.py` producers 在庫（P3b 產物）；本輪未發現新的 rolling-含-current-bar 反例。
**訓練 filter 規則 drift（F-10, LOW, FACT）**：cron 默認 `TRAINING_ENGINE_MODES=demo`（model_registry 全 demo），與 memory/skill 的穩定規則「`IN ('live','live_demo')`」矛盾 —— Demo 自主授權時代的合理演變（demo=學習源），但規則文本未更新 = 治理文檔與 runtime 漂移，應由 PM 把新規則落 memory/skill，避免未來 agent 按舊規則「修正」回去。

## 7. CV 方法論（quantile lane 抽查）

- tail holdout（10%）+ per-strategy embargo config + purge 語義、指數時間衰減權重（holdout 不加權）、pinball skill vs 常數 baseline、linear-QR floor gate、decile lift bootstrap CI、crossing rate、deterministic=True——**設計面 sound**（對齊 AFML；比 04 月版明顯成熟）。
- 但 F-1 使所有 metric 失效於源頭（99.9% 常數 label 下 pinball skill 數學上≈0）；F-4 embargo fail-open 未入 report。cpcv_validator/thompson/optuna 走 weekday=6 週日檔，本輪未深審（見 negative space）。

---

## 8. 正面確認（防止重複派工）

1. CI 已接 `schema_contract_test`（真跑 V001-V145 migration + consumer INSERT/SELECT）+ `audit_migrations.py`（ci.yml:103,116）→ 06-14 sqlx runtime-checked seam HIGH 的 CI 側閉環。
2. V145/V146/V141 Guard 模板紀律示範級；V144 route 側 fail-closed audit INSERT（IPC-OK-but-INSERT-fail→500）正確實作 root #8。
3. 三張 recorder 表 compression（7d）+ retention（21/30/45d）policy 已活（timescaledb jobs 親證），儲存有界。
4. label backfill 韌性：cron 死後仍有日級路徑補 label（backlog 僅 12）。
5. james_stein_estimates fresh 至 07-03 12:45；market.klines 1m fresh-to-now（R1 修復存活）。
6. acceptance gates fail-closed 正確：degenerate model 全部擋在 shadow_only，0 promoted，live combine layer 未受污染。

---

## 9. Findings 清單（全量，含 LOW/INFO）

| # | Sev | Class | Conf | 摘要 |
|---|---|---|---|---|
| F-1 | HIGH | FACT | high | 訓練集 99.9% 合成 0.0 reject label → quantile/scorer 永久 degenerate（evolution-blocker + 每日算力浪費 + registry sample 假象）|
| F-2 | HIGH | FACT | high | feature_tx paper-only → online_latest 凍結 05-06 → drift lane 0 事件 → promotion PSI gate 結構性不可滿足 |
| F-3 | HIGH | FACT(現象)/ASSUMPTION(意圖) | high/low | 06-27 crontab 置換殺 ~20 lane；passive_wait_healthcheck（90+ 檢查）未倖存 = 監測自盲；universe/edge snapshot/L2 memory 凍結 |
| F-4 | MED | FACT | high | embargo fail-open（<50 樣本靜默跳過，acceptance report 無記錄）|
| F-5 | LOW-MED | INFERENCE | med | scorer label winsorize 全窗分位數（含未來 fold）輕度 cross-fold leak |
| F-6 | MED | FACT | high | V141 kline truth-drift guardrail 0 row/16d（cron 未裝）+ check_91 哨兵停擺 = 雙盲 |
| F-7 | MED | FACT | high | aeg_regime_labels stale 32d + bayesian_posteriors.regime=engine_mode 值（06-14 HIGH 未修，複發確認）|
| F-8 | MED | FACT/INFERENCE | high/med | mlde_shadow_advisor 每日 QueryCanceled（5s timeout）→ MLDE advisory lane 死；可信根因=F-1 label 洪水 join 基數 |
| F-9 | MED | FACT | high | linucb arms=0/pulls=0 標 "ok"（空訓練 fake-success 語義）|
| F-10 | LOW | FACT | high | 訓練 engine_mode 默認 demo 與穩定規則 IN('live','live_demo') 文檔漂移 |
| F-11 | MED | FACT | high | V142/V143/V144 無 Guard A 但 header 聲稱有（模板紀律破口 + 注釋不誠實）|
| F-12 | LOW | FACT | high | V142/V143 compression/retention 無 extension guard（V006 缺陷複製）|
| F-13 | INFO | FACT | high | V146 未 apply → prod 誤導性 markout COMMENT 仍活（restart-gated）|
| F-14 | INFO | FACT/INFERENCE | med | l1_events 28GB 超 PA realistic 預估 4-9x（retention 有界但監測死角下的預估失準先例）|
| F-15 | INFO | FACT | high | decision_features 14.8M rows（99.9% reject）~55k/day 增長 — 表膨脹 + 下游查詢成本源（F-8/ADPE 64min 同根）|
| F-16 | INFO | FACT | high | select_next_arm 仍 0 consumer；resolver 0 caller；combine layer 仍 mock（06-14 結論全部不變）|

## 10. Negative space（本輪未展開盲區 — 給 PA re-probe）

1. weekday=6 檔位 job（thompson/optuna/cpcv_validator/dl3/weekly report）內部方法論未深審 — 每週日才跑、本輪窗口未及；07-05 run 後驗 bayesian_posteriors 是否自癒。
2. FeatureVectorV1 指標計算是否含 forming bar（train-serve skew 向量）— 決策時刻用 forming bar 是合法 PIT，但 ETL 側對齊未逐指標驗。
3. PSI/KS 實算 drift 螢幕（feature 分佈 reference vs current）— Mac 無 venv、且 online_latest 凍結使 current window 無意義（F-2 修復前實算無效）。
4. 引擎 env flags（OPENCLAW_RECORD_TICKS 等）未直讀 /proc environ（secret 衛生迴避）— 以 row freshness 間接證。
5. scorer_trainer CPCV 內部（cpcv_validator.py 360 行）與 onnx_exporter 未逐行審。
6. V140 manual pgvector 的 prod 狀態未驗。
7. GUI 寫入面 / control_api 其餘 route 未入本輪深度（非 MIT 主域，E5/compliance 同日有平行審計）。
8. 16 個 Rust DB writer 吞錯 seam（06-14 發現）未重驗 retrofit 進度。
9. crontab 置換的意圖與決策記錄未找到 — 需 operator 確認。
10. runtime checkout（ahead 8/behind 164）與 origin/main 的 migration 檔差集未精確比對（V146 何時會被 auto-migrate 取決於 runtime checkout 更新時點）。

---
MIT AUDIT DONE: docs/CCAgentWorkSpace/MIT/workspace/reports/2026-07-03--ml-db-full-repo-audit.md
