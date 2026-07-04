# MIT 數據/ML 面取證與修復 spec — P1-3 / P2-9 / P2-4 / P2-11 · 2026-07-04

**任務**:冷酷審計 R2 修復前置取證 wave。產出直接餵 E1/E1a/E4/E5 實現 wave。
**證據紀律**:Mac 源碼(git 髒樹,只讀)+ ssh trade-core runtime(PG 全程 SELECT-only、讀檔、crontab -l;0 mutation)。fact / inference / assumption 分標。
**Runtime 基準(07-04 運維窗口後新現實)**:engine PID 3159871(3a050b60 rebuild)、crontab 7 條、SSOT=/home/ncyu/BybitOpenClaw/var/openclaw、PG shared_buffers=6GB。sqlx head=145。

---

## 1. P1-3 訓練 label 污染 — 取證 + 非退化 label 方案(E1 spec)

### 1.1 污染鏈(全 FACT,親證)

| 環節 | 錨點 | 事實 |
|---|---|---|
| 合成 label 生產者 | `rust/openclaw_engine/src/intent_processor/mod.rs:1721-1776`(`emit_decision_feature_intent_rejected`) | reject path 寫 `label_close_tag="rejected_governance"`(:1770)+ `label_net_edge_bps=0.0`(:1771);caller=step_4_5_dispatch 三 reject path(:1701-1704 doc) |
| 當前流入速率 | PG 實測 | **46,650 rows/24h**(07-03→07-04,重啟後仍在流) |
| 訓練 ETL 缺陷 | `program_code/ml_training/parquet_etl.py:447-468` `_LOAD_TRAINING_DATA_SQL` | `WHERE label_net_edge_bps IS NOT NULL`(:459)**無 label_close_tag 過濾;SELECT 列根本不含 label_close_tag** → tag 在 SQL 邊界就被丟棄,下游任何加權/過濾都不可能 |
| export 雙胞胎 | `parquet_etl.py:667` | `label_filter = "AND label_net_edge_bps IS NOT NULL"` 同缺陷 |
| 兩條 lane 同源 | `run_training_pipeline.py:152-166`(quantile+scorer 都走 `load_training_data`);cpcv_validator 亦經 run_training_pipeline(`ml_training_maintenance.py:777`) | 一處修 = 兩 lane 全修 |
| M3 原設計配重孤兒化 | `program_code/ml_training/label_generator.py:105-154` `compute_class_weights`(REJECT_SAMPLE_WEIGHT=1/170);V084 UDF `learning.mlde_sample_weight` | **全 repo 0 生產 caller**(grep 親證);quantile_trainer 實際權重只有時間衰減(`quantile_trainer.py:158,613`) |

### 1.2 PG 分布實測(FACT)

30d 已標籤 rows:`rejected_governance` **2,093,162**(100% 為 0.0)vs 真實 outcome label **602** → 合成佔比 **99.97%**。

90d per-strategy(informative | synthetic):ma_crossover 921|4,690,297(5093:1)、grid_trading 2,352|643,393、funding_arb 117|30,258、bb_reversion 66|1,830、flash_dip_buy 79|182、bb_breakout 34|0。

07-04 03:17 run 實證退化(status json + acceptance report 親讀):grid_trading `n_samples_total=524,042` 全計為 "labeled";pinball skill **0.0**(q10/q50/q90);empirical_coverage **1.0**(三分位相同=常數預測器);verdict shadow_only。acceptance report **無任何 label 組成欄位**。`model_registry.training_sample_size` 記的是含合成的百萬級假象值。

**連帶(INFERENCE, med-high conf)**:`mlde_shadow_advisor` QueryCanceled(本日 status 仍 error)與 `linucb_trainer` arms=0(§4.3)的共同可信根因 = 同一 label 洪水的 join 基數(advisor/linucb 均 join `label_net_edge_bps IS NOT NULL` 池)。P1-3 修復預期同時緩解 F-8 與 linucb 空訓練。

### 1.3 E1 修復 spec(可執行)

**A(立即,一處修兩 lane)** — `parquet_etl.py`:
1. `_LOAD_TRAINING_DATA_SQL`(:447-468):SELECT 增列 `label_close_tag`;WHERE 增 `AND label_close_tag IS DISTINCT FROM 'rejected_governance'`。
2. `:667` export 分支 `label_filter` 同步加同一條件。
3. `load_training_data` 把 close_tag 陣列隨 row 帶出(或至少統計),供 acceptance report 組成統計。
4. 語義裁定(MIT):reject row 對 quantile/scorer **回歸** lane 是 non-sample(不是 0 值樣本);M3 reject-aware 語義只屬 ADPE reward view / 未來 classifier lane,後者若要用必經 `compute_class_weights`(已在庫、有測試)且 synthetic:informative 上限 **5:1**(超出即分層降採樣)——不許無權重直入。

**B(acceptance report 硬 gate)** — `quantile_reports.py:213 generate_acceptance_report`:
新增 `label_composition = {n_informative, n_synthetic_reject, synthetic_share, zeros_share, top_close_tags}`;硬 gate `label_composition`:`synthetic_share == 0`(修後期望)且 `zeros_share ≤ 0.5`(退化偵測器,fail → verdict 封頂 shadow_only)。`run_training_pipeline.py:382` 寫入 `model_registry.training_sample_size` 改為 informative count。

**C(label lineage 欄位,durable;可與 A/B 分批)** — 新 migration V147+(sqlx head 之後下一自由號):
`ALTER TABLE learning.decision_features ADD COLUMN label_source TEXT`,`CHECK (label_source IN ('realized_fill','synthetic_reject'))`(NULL=歷史未標),Guard A/B/C 全套(模板照 V145);Rust 側 `DecisionFeatureMsg` 增欄:reject path(mod.rs:1756-1776)寫 `'synthetic_reject'`,realized label 由 `edge_label_backfill` 標 `'realized_fill'`;歷史 backfill 用 `CASE WHEN label_close_tag='rejected_governance' THEN 'synthetic_reject' ELSE 'realized_fill' END` 分批 UPDATE。Linux PG double-apply dry-run 強制(memory 長期教訓)。**A/B 不依賴 C**(string-match 已可運作);C 是把 lineage 從字串慣例升級為 typed 欄位。

**D(同根連修)** — `mlde_shadow_advisor.py`(:203 附近 join)加同一 `label_close_tag` 過濾(P1-5 PG 調參只治標,基數才是根)。

### 1.4 重訓驗收判準(MIT/E4 驗)

1. acceptance report 含 `label_composition` 且 `zeros_share < 0.5`、`synthetic_share = 0`(溯源:top_close_tags 列出)。
2. 三分位 empirical_coverage 不再全等(coverage 分離 > 0);pinball skill 不再恆 0.0(**注意:gate 通過不是驗收條件** —— 真實 label 薄,誠實 fail 是合法結果;驗收的是「分布非退化 + 樣本記帳誠實」)。
3. `model_registry.training_sample_size` = informative count(grid_trading 期望 ~2.3k、ma_crossover ~0.9k @90d)。
4. 樣本不足策略(bb_breakout/bb_reversion/funding_arb/flash_dip_buy,<200 floor)必須 status=skipped "insufficient samples" —— 這是正確 fail-closed,不是回歸。
5. 附帶觀察:mlde_shadow_advisor QueryCanceled 與 linucb arms=0 在修後 3 日內是否自癒(是→根因確認;否→另查)。

---

## 2. P2-9 agent.l2_call_ledger ABSENT — 判定:**假陽性(表名誤用),非三選一**

### 2.1 取證(全 FACT)

- 任務給的三種假設(從未寫 migration / 寫了未 apply / 有意留空)**全不成立**,真相是第四種:**migration 已寫且已 apply,原 finding 探錯了表名**。
- `sql/migrations/V134__l2_calls_ledger.sql`(commit `a38d9bed9`)建的表是 **`agent.l2_calls`** + **`agent.l2_consequential_marks`**(Guard A 24 欄反射 + Guard B/C 齊全,append-only REVOKE)。
- PG 親證:`_sqlx_migrations` version=134 success=t,installed_on **2026-06-10 11:48:55**;`to_regclass('agent.l2_calls')` 存在,**1 row**(`l2r:93166da5722f`, trigger=manual, model=anthropic:sonnet, created 2026-06-10 17:34);`agent.l2_consequential_marks` 0 row;`to_regclass('agent.l2_call_ledger')` NULL —— 該名字**從未是任何 migration/writer 的表名**,它是 writer 模組名(`l2_call_ledger_writer.py`,其 INSERT 目標=`agent.l2_calls`,:211)。AI-E 原 probe 把模組名當表名。

### 2.2 修法(選定)

1. **P2-9 以 resolved-invalid 關閉**,修正 AI-E finding 記錄與 fix plan 隊列(0 代碼、0 migration)。
2. 殘留的真問題不是 schema 而是**流量**:帳本全史 1 row = L2 呼叫近零(與 V11 `agent.ai_invocations` 全史=2 同構)——歸屬 P2-3/E2E-1 治理項,不在本項重複立案。
3. 可選硬化(LOW,不強求):`COMMENT ON TABLE agent.l2_calls IS '... (aka l2_call_ledger, writer module 名)'` 防未來再探錯名;若做,走正常 V14x COMMENT migration(照 V146 模式)。

---

## 3. P2-4 unattributed fills 全鏈路追蹤 — 判定:**訓練面零污染;一個結構破口在 thompson fill-returns 路徑**

### 3.1 現狀口徑(FACT + 一個對不上的數)

- `trading.fills` 全表 **385 rows**(min ts 2026-06-18,max 07-04 16:40;hypertable,retention 365d/compression 14d —— 無近期 retention 刪除可能)。30d strategy_name 分類:真策略 360、**`unattributed:bybit_auto` 12**、`risk_close:ipc_close_symbol` 11、`orphan_frozen` 2。
- ⚠️ **與 R2 報的「30d 1268 筆/unattributed 15 筆」對不上**(今日同窗實測 385/12)。R2 probe 口徑不明(NEEDS_CONTEXT,交 PM 對帳);unattributed 存在性本身確認,量級同階。
- 產生機制(by design):`rust/openclaw_engine/src/event_consumer/unattributed_emit.rs` —— 交易所 WS fill 無法匹配引擎訂單時發 audit row(fill_id=`unattrib-<uuid>`,realized_pnl=0);模組注釋明言下游應把 `unattributed:%` 視為 expected-missing。

### 3.2 全 12 筆全鏈路 trace(FACT)

對全部 12 筆(fill_id `unattrib-1f333bb3…` 至 `unattrib-552184b8…`,06-18→07-03)逐筆 join:

| 下游 | join 鍵 | 命中 |
|---|---|---|
| `learning.decision_features` | context_id | **0/12** |
| `trading.decision_outcomes` | context_id | **0/12** |
| `learning.exit_features` | context_id | **0/12** |

join 側隔離(F4-2,2026-04-26 retrofit)系統性存在:`edge_label_backfill.py`(:177,196,214,313,361,421,441)、`realized_edge_stats.py`(:257,272)、`parquet_etl.py`(:198)、`mlde_demo_applier.py`(:898)、`dl3_ab_runner.py`(:234)全部 `strategy_name NOT LIKE 'unattributed:%'`。**結論:quantile/scorer/labels/exit/MLDE 訓練面對這 12 筆零污染。**

### 3.3 發現的結構破口(FACT,含歷史前例)

`helper_scripts/cron/ml_training_maintenance.py:157-189 _fetch_recent_fill_returns`(餵 thompson_sampling posteriors,:642-652)**無任何 fill-class 過濾**,以原始 strategy_name 分組成 arm。歷史前例親證:`learning.bayesian_posteriors` 內已存在 **`risk_close:ipc_close_symbol` / `risk_close:phys_lock_gate4_giveback` 偽策略 arm**(寫於 2026-05-10,n_trials=0)。當前 unattributed per-cell ≤3 < `audit_min_fills_per_cell=5`(:1036)未觸發,但同款破口敞開。

### 3.4 隔離/標記 spec(E1)

1. **最小修**:`_fetch_recent_fill_returns` SQL 加 `AND strategy_name NOT LIKE 'unattributed:%' AND strategy_name NOT LIKE 'risk_close:%' AND strategy_name <> 'orphan_frozen'`(系統動作 fill 不是策略 arm)。
2. 存量 `risk_close:*` posteriors rows:n_trials=0 且 `select_next_arm` 0 consumer(F-16)→ **建議留置不刪**(無害,刪除需寫權限違本 wave 紀律);在 fix plan 標註即可。
3. **durable(可選,防第 N 個消費者再犯)**:建唯讀 view `trading.v_fills_strategy_attributed`(排除三類系統 fill),新消費者一律引 view;或 V14x 加 `fill_class` typed 欄位(generated column from strategy_name pattern)。MIT 傾向 view(零 schema 風險、無 backfill)。
4. INFO:`helper_scripts/alpha_tournament/attribution_daily.py:109-115` 引用 runtime 不存在的欄位(`attribution_chain_ok`,`filled_at`)= 死 helper,交 P2-10 精簡批。

---

## 4. P2-11 V 系遷移衛生 — 三項各給最小修

### 4.1 ① V142-144 Guard A 註釋不誠實(FACT,親讀三檔)

- `V142__tick_orderbook_recorder.sql:19-20`、`V143__l1_book_event_recorder.sql:21`、`V144__strategist_promotions.sql:29-31,41,68` header/section 注釋聲稱 Guard A,**三檔 DO-block 數 = 0**(grep `^DO \$\$` 親證;無任何 RAISE 反射)。三表已 applied(sqlx 142/143/144 success=t)且寫入活躍。
- **最小修 spec(E1,兩件事一批)**:
  a. 新 migration **V147__recorder_promotions_guard_retrofit.sql**:對 `market.trades`(5 欄)/`market.ob_top`(6 欄)/`market.l1_events`(9 欄)/`learning.strategist_promotions`(16 欄)各一個 Guard A 型 DO-block(鏡像 V141 §B:表存在→反射必要欄→缺欄 RAISE;無其他 DDL;冪等雙跑全 NOTICE-skip)。價值:fresh-DB replay(CI schema_contract_test)與異環境獲得真 fail-closed 防線。
  b. 修 V142/143/144 header 為誠實表述(「Guard A 由 V147 retrofit 提供」);已 applied 檔案改注釋**必跑 `bin/repair_migration_checksum`** + Linux double-apply dry-run(memory SOP)。
  c. E2 checklist 增一行:「header 聲稱的 Guard 必須對 body DO-block 逐一對得上」。

### 4.2 ② V141 kline truth-drift guardrail 雙盲(本體與消費者確認;cron 側歸 P0-2)

- **V141 本體無缺陷**(Guard A/B/C 齊、applied);`research.kline_calibration` **0 row / 17d**(親測)。
- 消費者鏈全在 repo:checker bin(`Cargo.toml:187-188` → `src/bin/kline_calibration_checker.rs`)、cron wrapper(`helper_scripts/cron/kline_calibration_cron.sh`,start-touch sentinel)、哨兵 `check_91_kline_calibration_cron_fires`(`checks_cron_heartbeat.py:217-240`,WARN-by-default,sentinel `kline_calibration.last_fire`,threshold 25h)、R4 recal runbook(`helper_scripts/db/kline_recalibration_runbook.sh`)。
- 新現實:07-04 窗口後 crontab 7 條**仍不含 kline_calibration_cron**(親讀 crontab);passive_wait_healthcheck 已復活(13,43)→ check_91 恢復鳴叫。**雙盲已降級為單盲**:偵測面回來了,lane 本體仍死。
- **最小修**:kline_calibration_cron.sh 入 P0-2 恢復清單(cadence `17 5 * * *`,與 check_91 docstring 對齊;env 指新 SSOT DATA_DIR)。MIT 驗收:裝回後 24h 內 `research.kline_calibration` row>0 且 check_91 PASS。本項**無代碼修改需求**。

### 4.3 ③ linucb arms=0 回 "ok" 假成功(FACT,錨點 + 當日 runtime 實證)

- 錨點:`helper_scripts/cron/ml_training_maintenance.py:284-291 _run_linucb` —— `rows = train_all_arms(...)` 後**無條件** `return JobResult("linucb_trainer","ok",...)`;`train_all_arms`(`linucb_trainer.py:489-542`)對 fetch(:511)/upsert(:530)失敗都 `logger.error + continue`,15 arm 全敗 → rows=[] 仍 "ok"。
- 當日 runtime 實證(`/home/ncyu/BybitOpenClaw/var/openclaw/status/ml_training_maintenance_status.json`):`{"arms":0,"total_pulls":0,"converged_arms":0,"elapsed_ms":83666,"status":"ok"}` —— 83.7s 全敗(INFERENCE:~5.5s×15 statement timeout,與 F-8 同根,見 §1.2)。
- **最小修 spec(E1,只動 runner)**:`_run_linucb` 內 import `enumerate_v1_15_arm_ids`,`expected=len(...)`;`len(rows)==0` → status="error", error="all_arms_failed";`0<len(rows)<expected` → status="error", detail 加 `arms_failed`;`len(rows)==expected and total_pulls==0` → status="skipped", error="zero_observations"(對齊模組自述「insufficient samples as skip」)。驗收:重跑後 status≠ok 進 `_write_status`/history → overall payload 轉 error,cron log 可見;P1-3 修後若 observations 恢復,應轉回真 ok。

---

## 5. 附:本輪新增/修訂 findings 總表

| # | Sev | Class | Conf | 摘要 |
|---|---|---|---|---|
| N-1 | HIGH(承 F-1) | FACT | high | P1-3 污染鏈完整錨定;46,650/24h 仍在流;修復面=parquet_etl 一處+report 硬 gate+lineage 欄位(§1.3) |
| N-2 | MED | FACT | high | P2-9 假陽性:表=agent.l2_calls,V134 已 apply(06-10);關閉 finding,零 schema 動作(§2) |
| N-3 | LOW | FACT | high | P2-4 訓練面零污染(12/12 全鏈 0 hit + join 側 F4-2 隔離完備)(§3.2) |
| N-4 | MED | FACT | high | thompson `_fetch_recent_fill_returns` 無 fill-class 過濾;bayesian_posteriors 已有 risk_close:* 偽 arm 前例(§3.3) |
| N-5 | MED | FACT | high | R2「1268/15」與今日實測「385/12」不可調和;probe 口徑待 PM 對帳(§3.1) |
| N-6 | MED | FACT | high | V142-144 header 聲稱 Guard A、body 0 DO-block;修法=V147 retrofit+header 誠實化+checksum repair(§4.1) |
| N-7 | MED | FACT | high | V141 雙盲降單盲:check_91 隨 passive_wait 復活,kline_calibration_cron 仍缺席(§4.2) |
| N-8 | MED | FACT | high | linucb 假成功錨點+當日 status json 實證 arms=0/83.7s/"ok"(§4.3) |
| N-9 | INFO | FACT | high | 07-04 03:17 ml cron 的 acceptance_report_path 仍指 /tmp/openclaw(跑在 SSOT 遷移前);下次 run 應落新 DATA_DIR,值得次日驗證 |
| N-10 | INFO | FACT | med | attribution_daily.py 引用不存在欄位=死 helper(§3.4.4) |

**假陽性候選(不自行剔除,交 PM 裁)**:N-5 中 R2 原數字可能本身是 probe 錯誤(如錯表/錯窗);本輪已給可復現 SQL 口徑。

---
MIT AUDIT DONE: docs/CCAgentWorkSpace/MIT/workspace/reports/2026-07-04--data_ml_forensics_p13_p29_p24_p211.md
