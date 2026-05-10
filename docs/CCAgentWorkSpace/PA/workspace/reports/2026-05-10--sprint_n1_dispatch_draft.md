# Sprint N+1 Dispatch Draft（PA, 2026-05-10）

**Status**: DRAFT v3 — W6 RFC baseline 預跑後**結論 180° 反轉**：governance **沒有** over-fit；99.5% reject 是 cost_gate 拒 negative edge + duplicate_position guard（**正確行為**）；真正 bottleneck 仍是策略無 alpha。pending HIGH-5 forward watch metric 2/3 sign-off (~21:30 UTC，metric 1 已 MIT 提早 close)
**Authority**: PA design + PM dispatch；E1 IMPL；E2/E4 review；CC/QC/MIT/BB sign-off
**Estimated duration**: 7-10 calendar day（並行壓縮可到 5-7 day）
**Hand-off conditions**: see §6 Acceptance Gate
**Predecessor**: Sprint N+0 closure 2026-05-10 commit chain HEAD `b6ed4975`

## §0 Replay 整合 — 重大發現（2026-05-10 11:00 UTC）

兩個 replay sub-agent 完成後揭露 Sprint N+0 closure memory 的兩個重大誤讀，需在 N+1 priority 反映：

### §0.1 「attribution_chain_ok 0.5%→100%」描述是 mock baseline 誤讀（MIT verdict）
- **真實情況**：fills.entry_context_id → decision_features.context_id chain **pre+post V083 都是 100%**（0 orphan，n=312 pre + n=10 post 全期）
- decision_features producer 早 2026-04-15 起就在寫；V083 是新增 column + check_constraint，不是修 broken chain
- **N+1 影響**：HIGH-5 watch metric 1 可提早 sign-off（不需等 21:30 UTC），metric 2 + 3 仍 forward block

### §0.2 真正 bottleneck = governance reject 99.5%（**新 P0** — 升優先序）
- post-V082 W2 baseline：6361/6394 (99.5%) decision_features 標 `label_close_tag='rejected_governance'` + label_net_edge_bps=0
- **真實 close fill 只有 9 條 grid_trading**（5 strategy × 25 symbol pool 中 ML 學習 input 嚴重不足）
- 集中於：ma_crossover (ETHUSDT 3568, INXUSDT 2331) + grid (ETH/BTC/ZEC 各 130-188)
- **設計上正確**（reject 寫 0 bps 為 negative class 給 LinUCB / LightGBM 訓練），但 99.5% reject 必須驗證**是否 governance over-fit 拒所有正常信號**
- 直接後果：W-AUDIT-9 graduated canary Stage 1→2 promotion 等不到 ≥200 sample

### §0.2.B 【v3 重大反轉】W6 baseline 預跑揭露（2026-05-10 13:00 UTC）

MIT 預跑 6361 條 rejected_governance 樣本後，**§0.2 v2 推論「governance 過嚴 over-fit」被推翻**：

| 真相 | 證據 |
|---|---|
| **真實 reject reason SoT 在 `trading.risk_verdicts.{reason, checks_failed, details}`** — 不在 decision_features，不在 governance_audit_log | risk_verdicts 6454 row context_id 1:1 對應；W-AUDIT-4b M3 自承 V017 schema 鎖死不寫 reason |
| **99.8% reject 只有 2 大類**：cost_gate(JS-demo) negative edge (63.7%, 4092) + duplicate_position INXUSDT SHORT (36.3%, 2331) | risk_verdicts.reason 分群 |
| **0 條 scanner_advisory / volatility / DSR / position_size / margin_util reject**（這 4 條 governance gate 在 post-V082 3.5h 內 0 觸發） | 同上 |
| **Pre-V082 7d baseline reject rate = 0%**（M3 producer 還沒接通）；post-V082 99.55% **是 producer 切上線新行為，非 governance 收緊** | risk_verdicts pre/post 對比 |
| **INXUSDT 2331 reject 不是 over-fit**：全是 duplicate_position guard（策略想對已 SHORT 的 1810 倉位加碼） | reason 字串 "already SHORT 1810" |
| **真實 close fill 10 條全 grid_trading**（avg +33.47 / median -2.10 / hit 5/10）；INXUSDT 兩 outlier (+200/+112.91 bps) 占 grid total edge 96% | fills detail |
| **642:1 imbalance**；V084 sample_weight 1/170 修正後仍 ~4:1 long-tail | label 分布 |

**新結論**：
- W6 不是「relax governance threshold」— 那會讓 cost_gate 拒掉的 negative edge 真的下單，**犯錯**
- 真正 bottleneck **仍是策略本身輸出 negative edge**（4-agent loss audit consensus 再次被驗證 — 5 textbook 策略結構性 alpha-deficient）
- ma_crossover INXUSDT 2331 duplicate_position 暗示 **entry signal 跟 position state 沒對齊**（潛在 bug，策略反復想加碼）→ 新 P1 ticket
- decision_features 不寫 reject reason → ML 訓練只學「在這 market state 下會被拒」不學「為何拒」→ V086 加 reject_reason_code metadata（per F1）

### §0.3 TONUSDT verdict C（QC verdict）
- n=10 不足以判結構性 negative（t-test power < 0.3）
- DSR mu_0 = sqrt(2 ln 79) ≈ 2.79；TONUSDT naive SR ≈ -0.34，DSR PASS 機率 0
- 但 87.5% 概率 30d 後 mean revert（17 frozen cells 多數實證）
- counterfactual freeze 後 [40] 預估 +8.75→+13.5 bps（改善 ~5bps）但 confidence 低
- **新增 selection-bias 警示**：17→18 cells freeze (53% block rate of 41-symbol grid universe) 會加劇 dormant 負反饋環路

---

---

## §1 Sprint N+1 戰略目標

Sprint N+0 是 **foundation closure**（W-AUDIT-9 graduated canary state machine + W-AUDIT-4b ML pipeline 3-fault fix + W-AUDIT-8a Phase A AlphaSurface trait 宣告層）。

Sprint N+1 是 **alpha source build-out 起步**（4-agent loss audit 共識：5 textbook 策略結構性 alpha-deficient，必須補新 alpha source 才能根治；P0-EDGE-1 root closure pending）。

不是 quick win 期。任何「縮減 frequency / disable bad symbol」回退到 lazy fix 路徑必 PA reject。

---

## §2 Wave 結構（W1-W6 — v2 加 W6 governance reject P0）

| Wave | 名稱 | 性質 | 優先 | 依賴 | 估時 | 並行性 |
|---|---|---|---|---|---|---|
| **W6** | **Governance Reject Rate Audit + M4 Monitor**（**新 P0**） | RFC + IMPL | **P0** | 無 | 3-4 day | 與 W1 並行；阻 W3 Stage 2 promotion |
| W1 | W-AUDIT-8a Phase B Tier 2 panel collector | IMPL | P1 | N+0 Phase A trait | 6 day | 不可與 W3 同 ML cron | 
| W2 | A4-C BTC→Alt Lead-Lag spec | spec only | P2 | 無 | 2 day | 完全並行 |
| W3 | W-AUDIT-9 Stage 1 cohort observation | ops + IMPL | P1 | N+0 W-AUDIT-9 land **+ W6 完成** | 5 day | 不可與 W1 同 ML cron 觸發窗 |
| W4 | W-AUDIT-3b runtime smoke | test only | P2 | N+0 W-AUDIT-3b land | 1 day | 完全並行 |
| W5 | 9 P1 tickets backlog（v2 從 7 加到 9） | mixed | P1/P2 | per-ticket | 分散 | 完全並行 |

---

## §3 Wave 詳細 spec

### §3.0 W6 — Reject Reason Metadata + ML Imbalance Handling（**v3 重寫** — 不再叫 governance relax）

**目標**：W6 baseline 預跑揭露 99.5% reject **不是 governance over-fit**（cost_gate 拒 negative edge + duplicate_position guard 都是正確行為）。W6 真正方向：(1) 補 reject reason metadata 入 schema 讓 ML 學「為何拒」；(2) 解決 642:1 imbalance long-tail bias；(3) 修 ma_crossover INXUSDT duplicate intent bug；(4) M4 monitor 監測 reject reason mix drift。

**Sub-task v3**:
- W6-1. **W6 對齊 RFC**（PA + QC + MIT 三角，1 day **縮短**因 baseline 已預跑）
  - 共用 baseline：`srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--governance_reject_baseline_w6_rfc.md`
  - 三角各回 12 個預備 questions（report §6）
  - **預期結論方向**：governance 沒問題 → reject reason metadata 是真 gap → ML imbalance 是真 gap → 策略 alpha-deficient 不可由 W6 解
  - **不**寫 conditional relax AMD（v2 設計取消，此方向會犯錯）
- W6-2. **V086 reject_reason_code metadata schema add**（E1 IMPL 1 day）
  - 在 `learning.decision_features` 加 `reject_reason_code text` + `reject_reason_details jsonb` columns（per F1）
  - 從 `trading.risk_verdicts.{reason, checks_failed}` join 寫入
  - W-AUDIT-4b M3 producer 同步 update（`intent_processor/mod.rs:1213` 解 V017 lock）
  - V086 加 Guard A/B/C + idempotency
- W6-3. **Multi-class label split**（PA spec + E1 IMPL 1 day）
  - 把單一 `rejected_governance` label 拆 `rejected_cost_gate` / `rejected_duplicate_position` / `rejected_other`
  - LightGBM 訓練改 multi-class（per MIT Q3）
  - 效果：模型學「在這 state 下會被 cost_gate 拒（能改 cost）」vs「會被 duplicate_position 拒（能改 entry timing）」
- W6-4. **M4 reject reason mix monitor**（E1 IMPL 1 day）
  - 加 `helper_scripts/db/passive_wait_healthcheck/checks_reject_reason_mix.py`（[59]）
  - **alert 條件**改：cost_gate ratio 24h 變化 > 20pp（暗示 producer drift）；duplicate_position ratio 突增（暗示策略 entry bug 加劇）
  - **不**用 reject rate > 95% 作 alert（這是 normal）
- W6-5. **LightGBM imbalance handling 試行**（E1 IMPL 1 day）
  - V084 sample_weight 1/170 後仍 ~4:1 long-tail
  - 試行 `is_unbalance=True` 或 `scale_pos_weight=4`（per MIT Q1）
  - 跑 train + dev set 對比 baseline AUC / precision / recall
  - **不直接 deploy** ML predictor — 等 V086 land 後 multi-class 再評估
- W6-6. **M5 evaluations.entry_context_id healthcheck**（E1 IMPL 1 day, 等 ML predictor 接通後 enable）
  - per MIT M5 建議：`check_evaluations_entry_ctx_coverage()`
  - 編號預留 [60]

**Sub-agent assignment**:
- D+0: PA + QC + MIT 三角 RFC parallel（1 day，baseline 已備）
- D+1 ~ D+2: E1 IMPL V086 schema + M3 producer update + multi-class label split（並行）
- D+3: E1 IMPL M4 + M5 healthcheck + LightGBM imbalance 試行
- D+4: E2 review + E4 regression + MIT verify
- D+5: PM sign-off

**Acceptance criteria（v3）**:
- W6-1 三角 RFC verdict 明確（預期：governance 正確 + 真 gap = metadata + imbalance）
- V086 在 Linux PG `_sqlx_migrations` success=t（auto-migrate 後驗）；W-AUDIT-4b M3 producer 寫 reject_reason_code 100% coverage（post-V086 sample）
- Multi-class label 在 decision_features 顯示 3 類分布（cost_gate / duplicate_position / other）
- M4 [59] healthcheck baseline + alert 設好；24h dry-run 0 spurious alert
- LightGBM imbalance 試行報告 land；對比 AUC / precision / recall
- 22 + invariant 23 全 PASS

**Risk**:
- V086 加 column + jsonb 對 9.5M decision_features row 是大 schema change — Linux PG dry-run mandatory
- Multi-class label 改寫 LightGBM training pipeline，可能影響 cron 5 job 穩定性（cron weekly 跑，evaluation cycle 1 週）
- LightGBM `scale_pos_weight=4` 過頭可能 over-correct → false positive 暴增 → 需 backtest counterfactual

### §3.1 W1 — W-AUDIT-8a Phase B Tier 2 Panel Collector（**降為 P1**，與 W6 並行）

**目標**：Phase A 在 Rust 宣告了 `AlphaSurface` trait 與 5 策略 `alpha_sources`，但實際 Tier 2 panel data（funding curve / OI delta panel）**沒有 producer**。Phase B 把 producer 接起來，讓 8b/8c/8d 後續 alpha 候選有真實 input。

**Sub-task**:
- B-1. **funding_curve writer**（Bybit V5 funding history → PG `panel.funding_curve` table）
  - 25-symbol aggregator（從 cohort symbol list 抽）
  - 1m / 5m / 1h grain bucketing
  - V### migration（建議 V085）+ Guard A/B/C（idempotency check + rollback）
- B-2. **oi_delta_panel writer**（Bybit V5 open interest snapshot → PG `panel.oi_delta_panel` table）
  - 同 cohort symbol scope
  - delta = current_oi - prev_oi over 1m / 5m / 15m window
  - V### migration（建議 V086）+ Guard A/B/C
- B-3. **Bybit V5 rate limit budget review**
  - funding history endpoint：60 req/min
  - 25-symbol × 3 grain × 4 update/h = 300 req/h（well under budget，但要 jitter）
  - 與 W-AUDIT-9 Stage 1 cohort 同窗時要協調（避免 rate burst）
- B-4. **AlphaSurface consumer 驗收**
  - `bb_breakout` 已 declare `OiDeltaPanel` 但 Phase A 無 consumer（QC P1-BB-BREAKOUT-FAIL-CLOSED-1 來源）
  - Phase B 後須驗 bb_breakout 真實 consume Tier 2 panel；fail-closed 不 consume 時 evaluation_outcome 寫 `oi_panel_unavailable`

**Sub-agent assignment**:
- D+0: PA spec finalize（1 day）
- D+1 ~ D+3: E1-α IMPL B-1（funding_curve writer + V085）；E1-β IMPL B-2（oi_delta_panel + V086）— **並行 2 sub-agent**
- D+4: MIT review（schema + leak check + time-series CV consistency）
- D+5: E2 senior code review
- D+6: E4 regression + Linux PG dry-run
- D+7: BB rate limit final check + PM sign-off

**Acceptance criteria**:
- V085 + V086 在 Linux PG `_sqlx_migrations` success=t（auto-migrate 後驗）
- 25-symbol funding_curve / oi_delta_panel 1h 內各 ≥ 100 row 入表
- bb_breakout fail-closed path 觸發時 evaluation_outcome 寫 `oi_panel_unavailable`（不再 silent fallback）
- 22 + 新 invariant 23 全 PASS

**Risk**:
- Bybit V5 funding history endpoint 在某些 mid-cap 缺數據 → fail-closed 設計必須 graceful（不可 crash）
- panel table partition / hypertable 設計（TimescaleDB）— MIT 必確認

### §3.2 W2 — A4-C BTC→Alt Lead-Lag Spec Phase（**v3 升級評估**：操作員可決定 fast-track）

**v3 update**：W6 baseline 預跑再次驗證「5 textbook 策略結構性 alpha-deficient」結論（cost_gate 拒 4079 條 negative edge）。**A4-C 是真正能解 P0-EDGE-1 的路徑**。原 spec only / N+2 IMPL 設計可能太慢，**operator 可選**：
- A. 維持原計劃（N+1 spec only / N+2 IMPL）— 安全，4-agent review 完整
- B. **Fast-track**（N+1 spec + paper IMPL 並行）— 提早 N+1 拿到 paper edge evidence

PA 推薦 B（fast-track）但需 operator 拍板。

**目標**（不變）：5 textbook 策略結構性 alpha-deficient，A 群（Track A）已開三條候選：A-1 mean-reversion / A-2 momentum-of-momentum / A-3 cross-section sector rotation；本次新增 **A4-C BTC→Alt Lead-Lag** spec 階段。

**核心假設**：BTC price/volume movement leads alt symbols 60-300s（crypto microstructure 文獻 well-documented）；構造 lead signal → 預測 alt symbol 短期 mean reversion / momentum。

**Sub-task**:
- C-1. **PA spec**：信號公式 + cohort symbol scope + leakage 防護（lead window strict shift(N) 不可含 current bar；參考 feedback `lookahead_bias`）
- C-2. **QC review**：alpha decay 估算 + DSR penalty K 量化（A4-C 加入 K → mu_0 重算）
- C-3. **MIT review**：time-series CV 設計（purged k-fold + embargo）+ leak detection + cohort sample size demand
- **三角獨立 review** — 不 sequential，2 day 內並行

**Acceptance criteria**:
- PA spec 文件 land `srv/docs/execution_plan/`
- QC review 給 expected DSR penalty + alpha decay 半衰期
- MIT review 給 CV 設計 + cohort sample demand
- **三方都 APPROVE** 後才能進 Sprint N+2 IMPL phase
- **不**在 Sprint N+1 IMPL — IMPL 留 N+2

**Cohort symbol 限制**：
- BUSDT **不可** cohort（已 demote per funding_arb 棄路徑 ADR-0018）
- BTCUSDT 必含（lead source）
- alt scope: ETHUSDT / SOLUSDT / DOGEUSDT / XRPUSDT / ADAUSDT / AVAXUSDT / DOTUSDT 等 7-10 個 mid-large cap

### §3.3 W3 — W-AUDIT-9 Stage 1 Cohort Observation Start

**目標**：N+0 W-AUDIT-9 land 了 graduated canary 5-stage state machine 但**沒有任何 cohort 真實在 Stage 1**。N+1 啟動第一個 cohort observation cycle，驗 state machine 真實效果。

**Sub-task**:
- W3-1. **PA cohort 拍板**（per AMD-2026-05-10-04 atomic patch SOP）
  - 推薦 cohort：grid_trading × 3 cohort symbol（BTCUSDT / ETHUSDT / SOLUSDT）
  - 排除：TONUSDT（P1 待決，可能 freeze）
  - 排除：bb_reversion（W-AUDIT-6d 保 6 #6 verdict pair MA pending）
- W3-2. **第一個 atomic patch IMPL**（E1, 1 day）
  - patch scope：cohort 啟用 / Stage 1 thresholds / promotion criteria
  - **必走 atomic SOP**：governance commit + canary_stage_log row + GUI graduated tab 顯示
- W3-3. **Stage 1 → Stage 2 promotion criteria 確認**（解決 QC HIGH push back 2 — sample size vs wall-clock 矛盾，**P1-CANARY-STAGE-CRITERIA-1**）
  - 推薦：sample size **n ≥ 200** OR wall-clock **≥ 72h**（whichever later，避免短時間 over-fit）
- W3-4. **3-day passive observation**（Stage 1 promotion gate 未達不前進）
- W3-5. **Stage 2 promotion 嘗試 OR Stage 1 dwell continue**

**Acceptance criteria**:
- Stage 1 cohort 第一個 atomic patch 通過 [58] healthcheck
- canary_stage_log 行數 += 1
- GUI graduated tab 顯示正確 Stage / metric
- 3-day observation 後 attribution_chain_ok ≥ 80% per cohort symbol
- promotion criteria 3.3 update doc + AMD

**Risk**:
- 同窗 ML cron 影響：W1 Phase B Tier 2 collector 上線後 ML cron 可能改動 grid_trading decision logic；W3 cohort 觀察期須鎖定 W1 land 後 ≥ 24h 再進 Stage 1（sequential dependency）

### §3.4 W4 — W-AUDIT-3b Runtime Smoke

**目標**：N+0 W-AUDIT-3b（Decision Lease + executor fail-closed）IMPL 完成但 runtime 沒有 smoke test 驗 [55] healthcheck `chains_with_lease > 0`。

**Sub-task**:
- W4-1. E4 跑 `pytest test_executor_fail_closed`（Linux runtime）
- W4-2. engine restart 後 `[55] chains_with_lease > 0` query 驗
- W4-3. 寫 `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-XX--w_audit_3b_runtime_smoke.md`

**Acceptance criteria**:
- pytest PASS（≥ 1 test case 涵蓋 fail-closed path）
- [55] chains_with_lease ≥ 1 經 restart 後 5min 內

### §3.5 W5 — 9 P1 Tickets Backlog（v2 從 7 加到 9）

| Ticket | 來源 | 性質 | 估時 | sub-agent |
|---|---|---|---|---|
| P1-WEIGHT-DYNAMIC-1 | QC suggestion | E1 IMPL | 1 day | E1 |
| P1-ALPHA-SURFACE-ENUM-2 | QC suggestion | E1 IMPL | 1 day | E1 |
| P1-CANARY-STAGE-CRITERIA-1 | QC HIGH push back 2 | PA spec + AMD | 1 day | PA |
| P1-BB-BREAKOUT-FAIL-CLOSED-1 | QC dead declare 提醒 | E1 IMPL | 1 day | E1（隨 W1 B-4 一起做） |
| P1-INVARIANT-21-THRESHOLD | TODO §11.1 | PA + CC | 1 day | PA |
| P1-CANARY-COHORT-FREQ-23 | CC 22 invariant gap | PA spec + AMD | 1 day | PA |
| **P1-TONUSDT-CONDITIONAL-WATCH** *(改名)* | QC verdict C | RFC + Linux CC SQL | 2 day（30d evidence 收滿才升 freeze） | PA + Linux CC |
| **P1-DYNAMIC-UNBLOCK-CHECK-1** *(新)* | QC v3 NEW-ISSUE-V3-4 | PA spec + IMPL | 2 day | PA + E1 |
| **P1-V083-CONSTRAINT-VALIDATE** *(新)* | MIT M5 建議 | PA + E1 + MIT | 1 day | PA + E1 |
| **P1-MA-CROSSOVER-DUPLICATE-INTENT** *(v3 新)* | W6 baseline F-bug 暗示 | PA + E1 audit | 2 day | PA + E1 |

**新加 ticket 詳情**:
- **P1-TONUSDT-CONDITIONAL-WATCH**（替代原 P1-TONUSDT-GRID-BLOCK）：QC verdict C（n=10 不足以判結構性 negative）；不立即 freeze；分階段：(1) Linux CC 跑 30d regime split SELECT 補 evidence；(2) 若 30d sample n≥30 且仍 negative → 升 freeze；(3) 若 sample 不足 → 維持 watch；(4) 復評 30d cycle
- **P1-DYNAMIC-UNBLOCK-CHECK-1**：解 QC v3 NEW-ISSUE-V3-4 — 17 frozen cells 多數現 0 fills 0 rejected_outcomes（無 counterfactual power），需 30d cycle 機制 reuse `helper_scripts/db/audit/blocked_symbols_7d_counterfactual.py` 改 30d 版；達 positive edge 條件可解封；避免 17→18→N permanent dormant 負反饋環路
- **P1-V083-CONSTRAINT-VALIDATE**：V083 加的 check_constraint NOT VALID 對舊 row 不 enforce；MIT 建議追蹤 何時 VALIDATE（老 fills 不過 backfill 直接 VALIDATE 會 fail 全表）；先寫 backfill plan + 預估 VALIDATE date
- **P1-MA-CROSSOVER-DUPLICATE-INTENT**（v3 新）：W6 baseline 揭露 ma_crossover INXUSDT 在 post-V082 3.5h 內觸發 duplicate_position guard 2331 次（已 SHORT 1810 還反復想加碼）；暗示 entry signal 跟 position state 沒對齊（潛在 bug，非 governance 問題）；audit ma_crossover entry logic：(1) 是否每 tick 都 evaluate signal 不 dedup；(2) is_entry_eligible() 是否 cross-check exists position；(3) 若是 by-design pyramiding 為何被 duplicate guard 阻；fix scope 不超過 ma_crossover 模組

**派發策略**：分散到 N+1 Day 1-7 並行；**P1-CANARY-STAGE-CRITERIA-1** + **P1-CANARY-COHORT-FREQ-23** 與 W3 同窗（依賴）；**P1-BB-BREAKOUT-FAIL-CLOSED-1** 與 W1 同窗（依賴 Phase B consumer 驗收）；**P1-TONUSDT-CONDITIONAL-WATCH** 跟 **P1-DYNAMIC-UNBLOCK-CHECK-1** 同窗（dynamic unblock 機制是 freeze 前置）；**P1-V083-CONSTRAINT-VALIDATE** 與 W6 同窗（governance reject 整修同次）；**P1-MA-CROSSOVER-DUPLICATE-INTENT** 與 W6 同窗（同樣是 W6 baseline 衍生 finding）。

---

## §4 Schedule（Day-by-Day — v2 加 W6 critical path）

```
D+0 (2026-05-11 等 N+0 21:30 UTC forward watch metric 2/3 sign-off)
  PA: Sprint N+1 dispatch finalize v2（已吸收 replay evidence）
  PM: 派發 W6 三角 RFC / W1 spec / W2 三角 / W4 E4 / W5 多 P1 並行
  ⚠️ W3 Stage 1 cohort **暫不派**（等 W6 verdict）

D+1 ~ D+3 (3 day 並行 W6 + W1 + W2 + W4 + W5)
  W6 PA + QC + MIT 三角 RFC（governance reject root cause，2 day）
  W6 E1 IMPL M4 healthcheck [59]（D+2，1 day）
  W1 E1-α IMPL B-1 (funding_curve writer + V085, 3 day)
  W1 E1-β IMPL B-2 (oi_delta_panel + V086, 3 day)
  W2 PA + QC + MIT 三角 spec parallel（D+1-2 完）
  W4 E4 runtime smoke（D+1 完）
  W5 多 P1 並行（PA spec + E1 IMPL）

D+3 ~ D+5 (W6 verdict + W3 啟動)
  W6 RFC verdict land + AMD（如 over-fit 寫 conditional relax）
  W6 M5 evaluations.entry_context_id healthcheck IMPL（等 ML predictor 接通 enable）
  W3 PA cohort 拍板（D+3，等 W6 verdict）
  W3 atomic patch IMPL（D+4，1 day）
  W3 Stage 1 cohort 3-day passive observation 開始（D+4-D+7）
  W1 MIT review + E2 review (D+4-D+5)
  P1-TONUSDT-CONDITIONAL-WATCH Linux CC 30d regime split SELECT
  P1-DYNAMIC-UNBLOCK-CHECK-1 PA spec + E1 IMPL

D+6 ~ D+8
  W1 E4 regression + BB rate limit + PM sign-off
  W3 Stage 1 → Stage 2 promotion 嘗試（如達 criteria）
  W6 conditional governance threshold relax 試行（如 W6-3 verdict approve）
  W5 P1 closure 收尾
  ALL → CC + QC + MIT + BB final review（4-agent parallel）

D+9 ~ D+10（緩衝 buffer）
  Sprint N+1 sign-off + 22 + 新 invariant 23 全 PASS
  Memory persist + Sprint N+2 dispatch draft
```

---

## §5 Risk + Dependency

### §5.1 Cross-Wave Conflict
- **W1 ↔ W3**：W3 Stage 1 cohort 觀察期不可同窗 W1 ML cron 觸發；建議 W1 land 後 ≥ 24h 再進 W3 Stage 1
- **W1 ↔ W5 (BB-BREAKOUT-FAIL-CLOSED-1)**：B-4 acceptance 直接 close 此 P1
- **W3 ↔ W5 (CANARY-STAGE-CRITERIA-1, COHORT-FREQ-23)**：兩個 P1 是 W3 dependency，必先 close

### §5.2 External Dependency
- **HIGH-5 12h watch sign-off**：21:30 UTC 失敗會觸發 Sprint N+0 部分 rollback；rollback 範圍 = W-AUDIT-9 GUI graduated tab + W-AUDIT-4b M3 reject negative label（保 W-AUDIT-9 trait + V082/83 不動）
- **QC replay 結論**：TONUSDT 結構性 negative → P1-TONUSDT-GRID-BLOCK 升 P0 加入 N+1 Day 1；short-term outlier → 維持 N+1 P1 backlog
- **MIT replay 結論**：chain integrity 歷史不一致 → 影響 W3 Stage 1 promotion criteria（需追加 leak check）

### §5.3 Bybit Risk（BB review 必過）
- W1 Tier 2 panel collector rate limit
- W2 A4-C cohort symbol Bybit 支持度（BUSDT 排除已記）

---

## §6 Acceptance Gate（Sprint N+2 hand-off conditions — v3 重寫 W6 gate）

**全部** 達標才能 N+1 sign-off 進 N+2：

1. ✅ **W6 對齊 RFC verdict 明確**（預期：governance 正確、real gap = metadata + imbalance + duplicate_intent bug）
2. ✅ **V086 reject_reason_code metadata land**：sqlx success=t；M3 producer 寫 reason 100% coverage（post-V086 sample）；features_jsonb + reject_reason_code dual-write
3. ✅ **Multi-class label split**：decision_features `label_close_tag` 顯示 3 類分布（rejected_cost_gate / rejected_duplicate_position / rejected_other）
4. ✅ **M4 reject reason mix monitor [59]**：baseline + alert 設好；24h dry-run 0 spurious alert（**不**用 reject rate > 95% 作 alert，這是 normal）
5. ✅ **LightGBM imbalance handling 試行報告 land**（`is_unbalance` / `scale_pos_weight=4` AUC + precision + recall 對比）
6. ✅ W1 Phase B funding_curve + oi_delta_panel writer 上線；25-symbol 1h 內 ≥ 100 row each
7. ✅ W2 A4-C spec 三方（PA / QC / MIT）APPROVE land（如 operator 選 fast-track，paper IMPL 同時 land）
8. ✅ W3 Stage 1 cohort 第一個 atomic patch 通過 [58] healthcheck；3-day observation attribution_chain_ok ≥ 80%
9. ✅ W4 W-AUDIT-3b runtime smoke pytest PASS + [55] chains_with_lease ≥ 1
10. ✅ W5 10 P1 至少 6 closed（含 CANARY-STAGE-CRITERIA-1 + COHORT-FREQ-23 + DYNAMIC-UNBLOCK-CHECK-1 + V083-CONSTRAINT-VALIDATE plan land + MA-CROSSOVER-DUPLICATE-INTENT audit + 1）
11. ✅ 22 invariant + 新 invariant 23 全 PASS
12. ✅ CC + QC + MIT + BB 4-agent final review 全 APPROVE / APPROVE-CONDITIONAL
13. ✅ Memory persist + N+2 dispatch draft

**v3 移除（v2 設計取消）**：
- ❌ ~~如 W6 verdict = over-fit：conditional relax AMD land~~ — W6 baseline 預跑揭露 governance 沒 over-fit，conditional relax 會犯錯
- ❌ ~~Governance reject rate 進入 70-90% 合理區間~~ — 99.5% 是 normal（cost_gate 拒 negative edge 是正確），不應 force 降

---

## §7 Sprint N+2 預告（不在本 dispatch 範圍）

- W-AUDIT-8a Phase C/D（Tier 3 microstructure / Tier 4 info-flow signal collectors）
- A 群 alpha 候選 IMPL（A-1 / A-2 / A-3 + A4-C 從 spec 進 IMPL phase）
- 8b/8c/8d alpha source IMPL（基於 Phase B/C/D panel data）
- W-AUDIT-9 Stage 2 / Stage 3 promotion gate runtime 驗
- 5 textbook 策略 sunset evaluation（per AMD-2026-05-09-02）

---

## §8 Reference

- Sprint N+0 closure memory: `srv/memory/project_2026_05_10_sprint_n0_closure.md`
- W-AUDIT-8a Phase A spec: `srv/docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`
- AMD-2026-05-10-04 TOML drift SOP: `srv/docs/governance_dev/amendments/2026-05-10--AMD-2026-05-10-04-toml-drift-fix-sop.md`
- AMD-2026-05-09-03 graduated canary: `srv/docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md`
- ARCH-04: `srv/docs/architecture/2026-05-10--ARCH-04-graduated-canary-5-stage.md`
- ADR-0022 strategist-cap-wide: `srv/docs/adr/0022-strategist-cap-wide-parameter-adjustment-skill.md`
- TODO v19: `srv/TODO.md` §6 Sprint N+0 day-by-day（N+1 一節 pending update）

---

**已整合 evidence**（v3 update）:
- ✅ QC replay: TONUSDT 7-30d structural edge → `srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-10--tonusdt_structural_edge_replay.md`（verdict C，conditional path）
- ✅ MIT chain integrity replay → `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--chain_integrity_historical_replay.md`（chain 100%，governance reject 99.5% 提名 P0）
- ✅ **MIT W6 baseline 預跑** → `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--governance_reject_baseline_w6_rfc.md`（governance 沒 over-fit，真 gap 是 metadata + imbalance + duplicate_intent bug）

**Final Step**: 21:30 UTC HIGH-5 forward watch metric 2/3 sign-off 後此 draft v2 升 final（metric 1 已 MIT 提早 close），TODO v19 §6.5 加入 Sprint N+1 banner + reference link。

---

## §9 Replay 整合對 Sprint N+0 closure memory 修正建議（v3 land 後同次 commit）

`srv/memory/project_2026_05_10_sprint_n0_closure.md` 須修正以下三條描述：

1. **「attribution_chain_ok 0.5%→100%」這條改為**：
   > 「decision_features chain integrity（fills.entry_context_id → context_id）pre-V083 已 100%（n=312, 0 orphan）；V083 是新增 column + check_constraint NOT VALID 不修 broken chain；memory v1 「0.5% mock baseline → 100% prod」描述為 narrow window 樣本誤讀，**真實全期均 100%**」
2. **「governance reject 99.5% 是 ML input 不足」這條（v2 草稿）改為**：
   > 「W2 baseline 期間 reject rate 99.5%（6361/6394）是 W-AUDIT-4b M3 producer 切上線新行為（pre-V082 = 0%，producer 還沒接通）+ 99.8% 集中於 cost_gate negative edge (63.7%) + duplicate_position guard (36.3%) — **governance 沒有 over-fit，是正確行為**；真正問題是 (1) reject reason 不入 schema → ML 訓練只學 market state 不學 reject reason → V086 補 (2) 642:1 imbalance long-tail bias → multi-class label split + LightGBM imbalance handling (3) ma_crossover INXUSDT 反復 duplicate_position trigger 暗示 entry signal bug」
3. **「真實 close fill 9 條」補正**：
   > 「post-V082 3.5h 內真實 close fill 10 條（不是 9，9 是初步計數誤差）；全 grid_trading；avg +33.47 / median -2.10 / hit 5/10；INXUSDT 兩 outlier (+200/+112.91 bps) 占 grid total edge 96%，去 outlier 後 hit rate / Sharpe / DSR 需重算」

修正方式：N+1 dispatch fire 後同次 commit 帶 memory file edit；不另起 commit。
