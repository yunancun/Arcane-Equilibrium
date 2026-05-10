# Sprint N+1 Dispatch Draft（PA, 2026-05-10）

**Status**: DRAFT v3.2 — 3 PA 預跑 reports 整合（trait coord / W6 RFC PA-view / P1-MA-CROSSOVER audit）；P1-MA-CROSSOVER **升 P0** 為 W7（systemic strategy↔position state architectural gap）；W7 + W2 PA D+0 trait skeleton 合併 commit；W6 加 W6-7 + 加 P1-BB-REVERSION-FIRE-AUDIT + ML retrain 4-gate
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

### §0.4 【v3.2 整合】3 PA 預跑 reports 重大發現（2026-05-10 14:00 UTC）

operator 2026-05-10 拍板 A4-C fast-track 後，PA 並行 3 預跑 sub-agent 揭露：

#### §0.4.A AlphaSurface trait coord — 好消息
- W-AUDIT-8a Phase A 已 land 9/10 type，**W1 funding_curve / oi_delta_panel struct 已完整 typedef，0 新增需求**
- W2 BtcAltLeadLag 唯一新加 ~40 LOC（PA D+0 single commit）
- 5 個 E1 sub-agent 完全並行 0 file 重疊（anchor comment 隔離 + V### 編號 V085/V087/V088 預先 reserved）
- W2 paper-only fence 三層深度防禦（step_4_5_dispatch.rs engine_mode gate 主防線 + Python writer fence + Strategy if let Some guard）
- 16 原則 / DOC-08 §12 9 不變量 / 硬邊界 5 項全 0 觸碰
- Report: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--alpha_surface_trait_final_shape_w1_w2_coord.md`

#### §0.4.B 【最重大】P1-MA-CROSSOVER 升 P0 — systemic strategy↔position state gap

MIT W6 baseline 揭露 ma_crossover INXUSDT 2331 reject 不是 governance 問題，PA audit confirm **HIGH confidence** 是 architecture-level bug：

| 證據 | 細節 |
|---|---|
| **Cross-strategy desync** | ma_crossover 用 `self.positions: HashMap` 追蹤**自己策略**倉位，**不查 paper_state**；router gate 1.5 用 `paper_state.get_position(symbol)` 做 **symbol-level（不分策略）** dedup |
| **Hot loop pattern** | grid_trading 在 INXUSDT 11:29 開 SHORT 1810 後，ma_crossover 看不見，每 tick 持續發 entry intent 撞 gate 1.5；`on_rejection` rollback `strategy.positions` 到 None 形成 infinite loop |
| **Burst 證據** | **11:34:00 一分鐘內 reject 2319 次（每秒 30-50 次）** — 遠超 KAMA cross 物理頻率；INXUSDT 1m vol 正常無 abnormal cross |
| **Pollution 鏈** | W-AUDIT-4b M3 在 pre_risk reject 也寫 negative label → noise 進 production decision_features → ML training pollution |
| **Live 嚴重度** | HIGH — 真 live 下 lease/SM-02 throughput 浪費；OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1 下 lease acquire→cancel 浪費 |
| **Systemic** | bb_breakout / bb_reversion 同樣設計（用 self.positions 不查 paper_state）— W6 baseline 沒看到只是 signal 沒對齊 |

**升 P0 理由**：
- 不只是 ma_crossover bug，是**全策略 architectural gap**（5 策略都用 self.positions 不查 paper_state）
- 跟 §二 16 根原則 #16「組合級風險意識」直接相關（cross-strategy coordinator 缺 gap）
- Fix scope: TickContext 加 read-only position handle → **5 策略 signature 對齊** → 與 W2 trait extension 同窗 → **必合併 PA D+0 trait skeleton commit**

Report: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--p1_ma_crossover_duplicate_intent_audit.md`

#### §0.4.C W6 RFC PA-view 立場 + 6 條 dispatch update

PA 預備立場（D+1 W6 RFC 三角入場帶這個）：
- Q1 cost_gate **hold A** — 維持 hard rule，不引 advisory（違反根原則 #5/#4）
- Q2 duplicate_position pyramiding **hold A** — 不開；2331 reject 是 ma_crossover state sync bug（→ §0.4.B）
- Q3 V086 metadata **hold A** — 立刻做（W6-2 D+1~D+2）；ML retrain enable 等 4-gate
- Q4 bb_*/funding_arb 0 fire **depends** — funding_arb dormant by design / bb_breakout = AlphaSurface consumer gap / bb_reversion 三源因素需另查

6 條 dispatch update 全部納入 v3.2（見下文各 §3 update）。

Report: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_rfc_pa_questions_self_answer.md`

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

## §2 Wave 結構（W1-W7 — v3.2 加 W7 P0 STRATEGY-POSITION-SYNC）

| Wave | 名稱 | 性質 | 優先 | 依賴 | 估時 | 並行性 |
|---|---|---|---|---|---|---|
| **W7** | **STRATEGY-POSITION-SYNC**（v3.2 新 P0，從 P1 升）— TickContext + 5 策略 signature 對齊 + ma_crossover state sync fix | architecture IMPL | **P0** | 無 | 4 day | **必與 W2 合併 PA D+0 trait skeleton commit**；W7 + W2 同 commit |
| **W6** | Reject Reason Metadata + ML Imbalance Handling（v3 重寫，v3.2 加 W6-7） | RFC + IMPL | **P0** | 無 | 5 day | 與 W1 並行；阻 W3 Stage 2 |
| W1 | W-AUDIT-8a Phase B Tier 2 panel collector | IMPL | P1 | PA D+0 trait skeleton（W7+W2 合併 commit） | 6 day | W1 + W7 + W2 完全並行 0 file 重疊（PA #1 確認） |
| W2 | A4-C BTC→Alt Lead-Lag spec + paper IMPL（v3.1 fast-track） | spec + IMPL | P1 | PA D+0 trait skeleton（含 W7 + W2） | 7 day | 同上 |
| W3 | W-AUDIT-9 Stage 1 cohort observation | ops + IMPL | P1 | N+0 W-AUDIT-9 land + W6 完成 + W7 完成（避 ma_crossover hot loop 干擾觀察） | 5 day | 不可與 W1 同 ML cron 觸發窗 |
| W4 | W-AUDIT-3b runtime smoke | test only | P2 | N+0 W-AUDIT-3b land | 1 day | 完全並行 |
| W5 | 11 P1/P2 tickets backlog（v3.2 從 10→11，移 ma_crossover 出 W5 升 W7） | mixed | P1/P2 | per-ticket | 分散 | 完全並行 |

---

## §3 Wave 詳細 spec

### §3.−1 W7 — STRATEGY-POSITION-SYNC（**v3.2 新 P0**，與 W6 sibling）

**目標**：解 PA #3 audit 揭露的 architecture-level gap — 5 策略用 `self.positions` 追蹤自己策略倉位，**完全不查 paper_state**；router gate 1.5 用 paper_state symbol-level dedup → cross-strategy desync 形成 infinite reject hot loop（11:34 一分鐘 2319 次）。修 ma_crossover 同時做全策略 architectural fix。

**Sub-task v3.2**:
- W7-1. **PA TickContext extension spec**（PA D+0，與 W2 trait skeleton 同次 commit）
  - `TickContext` 加 `position_state: Option<&PaperPosition>` field（read-only handle from paper_state）
  - 5 策略 `on_tick(ctx, surface)` signature 對齊：grid_trading / ma_crossover / bb_breakout / bb_reversion / funding_arb
  - **必與 W2 BtcLeadLagPanel field 合併 PA D+0 trait skeleton commit**（避免後續 5 sub-agent IMPL 撞 trait file）
  - LOC 預估：~30 (TickContext) + ~15 (tick_pipeline call site) = ~45 LOC
- W7-2. **ma_crossover entry path fix**（E1 IMPL D+1-2, 1 day）
  - `strategies/ma_crossover/strategy_impl.rs:140-234` entry path：進 entry 前查 `ctx.position_state`；如同 symbol 已有任何策略倉位 → skip entry，不發 intent
  - **不**改 `self.positions` HashMap 設計（保持 strategy-level shadow，但 entry decision 必查 paper_state）
  - 預估 LOC：~20
- W7-3. **on_rejection 識別 duplicate_position 並 sync**（E1 IMPL D+2, 0.5 day, 補 1-tick 防衛）
  - `strategy_impl.rs:44-65` on_rejection 加分支：if reason starts_with "duplicate_position" → 解析 `existing_is_long` 寫入 `self.positions`
  - 立即終結 hot loop（下 tick 進 exit path 而非 rollback to None）
  - 依賴 reason 字串格式（rejection_coding.rs:148 byte-identical 契約）— E2 必審契約鎖
- W7-4. **5 策略 systemic audit**（PA + E1 D+2-3, 1 day）
  - 對 grid_trading / bb_breakout / bb_reversion / funding_arb 各跑 same audit pattern
  - 找其他 cross-strategy desync 風險點（e.g., bb_reversion 的 `prev_position` rollback 是否同樣 bug）
  - 出 audit report；發現的 issue 開 P2 ticket（不在 N+1 fix，留 N+2 if not blocking）
- W7-5. **on_fill update + bootstrap import_positions**（E1 IMPL D+3, 0.5 day, per PA #2 Q2 建議）
  - 確認 `on_fill()` 正確 update self.positions（遠端真實 fill 後）
  - bootstrap 階段從 paper_state import_positions 重建 strategy.positions（避 cold-start desync）

**Sub-agent assignment**:
- D+0: PA spec + trait skeleton 合併 W2 commit（~85 LOC: 40 BtcLeadLagPanel + 45 TickContext.position_state）
- D+1-2: E1 IMPL W7-2 + W7-3（ma_crossover fix + on_rejection sync）
- D+2-3: PA + E1 W7-4 (5 策略 systemic audit) + W7-5 (on_fill + bootstrap)
- D+3: E2 review（必審 RC-04 prev_position rollback 邏輯刪除前 spec / TickContext signature lifetime）
- D+4: E4 regression + Linux runtime 24h 驗 ma_crossover INXUSDT reject < 10/h（從 666/h 降）+ PM sign-off

**Acceptance criteria**:
- ma_crossover INXUSDT 24h reject rate < 10/h（從 baseline 666/h 降，**60+ x 改善**）
- 全策略 cross-strategy hot loop 0（grep `risk_verdicts.reason='duplicate_position'` 24h 無 burst pattern）
- 5 策略 systemic audit report land；發現的其他 issue 開 P2 ticket
- TickContext signature 變動不 break 既有 5 策略 on_tick callsite
- on_fill / bootstrap 更新邏輯通過 E2 + E4
- 22 + invariant 23 全 PASS
- DOC-08 §12 9 條安全不變量 + 硬邊界 5 項 0 觸碰

**Risk**:
- **TickContext signature 變動是 cross-strategy 改動** — PA 必統一審 5 策略 on_tick 對齊（PA #3 audit §8 已點 E2 重點 3 點）
- on_rejection 刪除 prev_position rollback 邏輯前必 audit RC-04 spec — 為什麼一開始要 rollback？是否有 cooldown clear 副作用
- paper_state.get_position() 在 strategy on_tick 是否違反 borrow checker（paper_state 已被 step_4_5_dispatch.rs 同層 borrow）
- W3 Stage 1 cohort 觀察期必等 W7 完成（hot loop 干擾 attribution_chain 觀察）

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
- W6-7. **[61] strategy fire silence healthcheck**（v3.2 新，per PA #2 Q4 建議，E1 IMPL 0.5 day）
  - 加 `helper_scripts/db/passive_wait_healthcheck/checks_strategy_fire_silence.py`（[61]）
  - 5 策略 24h 0 fire 報 WARN（funding_arb 排除清單 hard-code 防 false WARN per ADR-0018）
  - root cause 列舉：cooldown / regime / panel_unavailable / scanner_threshold / **strategy↔position desync (W7 fix 後應消失)**
  - 與 W6-4 [59] 同窗
- W6-8. **W6-1 RFC verdict 明文化**（v3.2 新，per PA #2 Q1 建議）
  - RFC verdict 明文記「cost_gate hard rule 維持，不引 advisory mode」入 RFC report
  - 避免 N+2 又重提 advisory 路徑

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

### §3.2 W2 — A4-C BTC→Alt Lead-Lag Spec + Paper IMPL（**v3.1 Fast-track 已拍板** — operator 2026-05-10 confirm）

**目標**：5 textbook 策略結構性 alpha-deficient（W6 baseline + 4-agent loss audit 雙重確認）→ A4-C 是真正能解 P0-EDGE-1 的路徑。N+1 不只 spec，**直接派 paper IMPL** 拿 7d paper edge evidence；如 paper edge > +5 bps → N+2 promote demo IMPL；如 < +5 bps → revise spec 不浪費 N+2。

**核心假設**：BTC price/volume movement leads alt symbols 60-300s（crypto microstructure 文獻 well-documented）；構造 lead signal → 預測 alt symbol 短期 mean reversion / momentum。

**Sub-task v3.1（spec + paper IMPL 並行）**:

**Spec phase（Day 1-2，PA + QC + MIT 三角並行 review）**:
- C-1. **PA spec**：信號公式 + cohort symbol scope + leakage 防護（lead window strict `shift(N)` 不可含 current bar；參考 feedback `lookahead_bias`）；落 `srv/docs/execution_plan/2026-05-1X--a4c_btc_alt_lead_lag_spec.md`
- C-2. **QC review**：alpha decay 估算 + DSR penalty K 量化（A4-C 加入 K → mu_0 重算）+ paper edge gate threshold（≥ +5 bps 進 N+2）
- C-3. **MIT review**：time-series CV 設計（purged k-fold + embargo）+ leak detection + cohort sample size demand（paper 7d 預估能拿多少 sample）

**Paper IMPL phase（Day 3-7，spec sign-off 後啟動）**:
- C-IMPL-1. **AlphaSurface trait extension**（E1, 2 day）
  - W-AUDIT-8a Phase A 已 declare `AlphaSurface` trait；A4-C 新增 `BtcAltLeadLag` source variant
  - Rust 端 `openclaw_core/src/alpha_surface.rs` 加 enum variant + producer hook
  - 與 W1 Phase B funding_curve / oi_delta_panel writers 同 trait pattern（共用 producer interface）
- C-IMPL-2. **Lead-lag signal producer**（E1, 2 day）
  - 從 BTCUSDT 1m kline 計算 lead signal（return / volume / orderbook imbalance over N=60-300s window）
  - Per cohort alt symbol cross-correlate
  - 寫 `panel.btc_lead_lag_panel` table（V### migration 預留 V087）
- C-IMPL-3. **Strategy 接收 paper-only**（E1, 1 day）
  - ma_crossover + grid_trading 在 paper engine mode 接 `BtcAltLeadLag` 作 feature input（**不直接 trade**，先 shadow + log）
  - bb_breakout / bb_reversion / funding_arb **不接**（避免污染 5 策略 demo edge baseline）
  - paper engine 跑 7d 累積 evidence
- C-IMPL-4. **Paper edge evidence collection**（D+5 ~ D+10）
  - 每 24h 跑 [40] paper avg_net_bps + maker_pct + sample size 對比 baseline
  - 7d window 累積 paper edge evidence
  - **不**跑 demo 也**不**跑 live_demo（Phase 1 fast-track 邊界）

**Acceptance criteria（v3.1 加 paper IMPL）**:
- PA spec 文件 land `srv/docs/execution_plan/`
- QC review 給 expected DSR penalty + alpha decay 半衰期 + paper edge gate threshold
- MIT review 給 CV 設計 + cohort sample demand
- **三方都 APPROVE** 後才能進 paper IMPL（spec 是 prerequisite）
- AlphaSurface trait extension + lead-lag producer + V087 migration 在 Linux PG `_sqlx_migrations` success=t
- Paper engine 跑 7d 累積 sample n ≥ 100 fills per cohort symbol
- Paper edge evidence report land：avg_net_bps + DSR + sample size
- **如 paper edge > +5 bps**：N+2 promote demo IMPL（PA + QC + MIT 重 review）
- **如 paper edge < +5 bps**：revise spec（不浪費 N+2）

**Cohort symbol 限制**:
- BUSDT **不可** cohort（已 demote per funding_arb 棄路徑 ADR-0018）
- BTCUSDT 必含（lead source）
- alt scope: ETHUSDT / SOLUSDT / DOGEUSDT / XRPUSDT / ADAUSDT / AVAXUSDT / DOTUSDT 等 7-10 個 mid-large cap

**Risk（v3.1 fast-track 加風險）**:
- AlphaSurface trait extension 與 W1 Phase B 同窗 — 兩個 wave 都動 trait 文件，合併衝突風險高 → 派 sub-agent 前 PA 先拍板 trait final shape，W1 + W2 IMPL 用 trait 同一 commit
- Paper IMPL 在 paper engine mode 跑，**OPENCLAW_ENABLE_PAPER=1** env 必先設（per `feedback_paper_pipeline_disabled_by_default`）
- 不能讓 Lead-Lag signal 污染 5 策略 demo edge baseline — 必須 paper-only fence
- V087 是 panel table，hypertable partition 設計 MIT 必確認

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
| ~~P1-MA-CROSSOVER-DUPLICATE-INTENT~~ *(v3.2 升 P0 移到 W7)* | — | — | — | — |
| **P1-BB-REVERSION-FIRE-AUDIT** *(v3.2 新, per PA #2 Q4)* | W6 baseline + PA Q4 | PA audit | 1 day | PA |
| **P2-BB-BREAKOUT-POSITION-SYNC** *(v3.2 新, per PA #3 systemic)* | W7-4 audit 衍生 | E1 fix（如 W7-4 確認 systemic）| 1-2 day | E1 |
| **P2-BB-REVERSION-POSITION-SYNC** *(v3.2 新, per PA #3 systemic)* | W7-4 audit 衍生 | E1 fix（如 W7-4 確認 systemic）| 1-2 day | E1 |

**新加 ticket 詳情**:
- **P1-TONUSDT-CONDITIONAL-WATCH**（替代原 P1-TONUSDT-GRID-BLOCK）：QC verdict C（n=10 不足以判結構性 negative）；不立即 freeze；分階段：(1) Linux CC 跑 30d regime split SELECT 補 evidence；(2) 若 30d sample n≥30 且仍 negative → 升 freeze；(3) 若 sample 不足 → 維持 watch；(4) 復評 30d cycle
- **P1-DYNAMIC-UNBLOCK-CHECK-1**：解 QC v3 NEW-ISSUE-V3-4 — 17 frozen cells 多數現 0 fills 0 rejected_outcomes（無 counterfactual power），需 30d cycle 機制 reuse `helper_scripts/db/audit/blocked_symbols_7d_counterfactual.py` 改 30d 版；達 positive edge 條件可解封；避免 17→18→N permanent dormant 負反饋環路
- **P1-V083-CONSTRAINT-VALIDATE**：V083 加的 check_constraint NOT VALID 對舊 row 不 enforce；MIT 建議追蹤 何時 VALIDATE（老 fills 不過 backfill 直接 VALIDATE 會 fail 全表）；先寫 backfill plan + 預估 VALIDATE date
- ~~P1-MA-CROSSOVER-DUPLICATE-INTENT~~ → **v3.2 升 P0 移到 W7**（PA #3 audit confirm 是 architecture-level systemic gap，全策略 5 個都用 self.positions 不查 paper_state）
- **P1-BB-REVERSION-FIRE-AUDIT**（v3.2 新，per PA #2 Q4）：bb_reversion post-V082 0 fire 三源因素 grep — (1) entry condition 是否太嚴 (2) scanner threshold 過濾掉 (3) AlphaSurface consumer gap（同 bb_breakout）；找出 root cause 給 N+2 fix scope；不在 N+1 IMPL 修
- **P2-BB-BREAKOUT-POSITION-SYNC** + **P2-BB-REVERSION-POSITION-SYNC**（v3.2 新，per PA #3 systemic）：W7-4 全策略 audit 如確認 bb_breakout / bb_reversion 同樣 self.positions 不查 paper_state → 開 P2 fix；如 W7 fix scope 已涵蓋（TickContext.position_state 給全 5 策略） → close as duplicate

**派發策略**：分散到 N+1 Day 1-7 並行；**P1-CANARY-STAGE-CRITERIA-1** + **P1-CANARY-COHORT-FREQ-23** 與 W3 同窗（依賴）；**P1-BB-BREAKOUT-FAIL-CLOSED-1** 與 W1 同窗（依賴 Phase B consumer 驗收）；**P1-TONUSDT-CONDITIONAL-WATCH** 跟 **P1-DYNAMIC-UNBLOCK-CHECK-1** 同窗（dynamic unblock 機制是 freeze 前置）；**P1-V083-CONSTRAINT-VALIDATE** 與 W6 同窗（governance reject 整修同次）；**P1-MA-CROSSOVER-DUPLICATE-INTENT** 與 W6 同窗（同樣是 W6 baseline 衍生 finding）。

---

## §4 Schedule（Day-by-Day — v3.2 加 W7 + PA D+0 trait skeleton 合併 commit）

```
D+0 (2026-05-11 等 N+0 21:30 UTC forward watch metric 2/3 sign-off)
  PA: Sprint N+1 dispatch v3.2 finalize
  PA: 【critical 1 commit】 AlphaSurface trait skeleton 合併 commit:
       - W2 BtcLeadLagPanel struct + AlphaSurface.btc_lead_lag field + 3 constructor
       - W7 TickContext.position_state field + 5 策略 signature 對齊 + slots/dispatch anchor
       - ~85 LOC, single commit, no business logic
  PM: 派發 W7 IMPL / W6 三角 RFC / W1 spec / W2 三角 spec / W4 E4 / W5 多 P1 並行
  ⚠️ W3 Stage 1 cohort 暫不派（等 W6 verdict + W7 完成）

D+1 ~ D+2 (spec + W7 IMPL phase 並行)
  W7 E1 IMPL W7-2 ma_crossover entry path fix + W7-3 on_rejection sync (1.5 day)
  W6 PA + QC + MIT 三角 RFC（governance reject 對齊，1 day baseline 已備）
  W2 PA + QC + MIT 三角 spec（A4-C BTC→Alt Lead-Lag，2 day）
  W1 PA spec finalize（W-AUDIT-8a Phase B Tier 2 panel）
  W4 E4 runtime smoke（D+1 完）
  W5 多 P1 並行 spec phase（含 P1-BB-REVERSION-FIRE-AUDIT）

D+2 ~ D+3 (W7 systemic audit + IMPL 大爆發)
  W7 PA + E1 W7-4 5 策略 systemic audit (1 day)
  W7 E1 W7-5 on_fill + bootstrap import_positions (0.5 day)
  W7 E2 review (D+3)
  W6 E1 IMPL V086 reject_reason_code + multi-class label split + M4 monitor [59] + [61] silence healthcheck
  W1 E1-α IMPL B-1 (funding_curve writer + V085, 3 day)
  W1 E1-β IMPL B-2 (oi_delta_panel + V087, 3 day)
  W2 E1-γ NO-OP (trait extension 已 PA D+0 commit, 範圍縮為 typedef 驗收)
  W2 E1-δ IMPL C-IMPL-2 lead-lag producer + V088 migration (2 day)
  W5 P1 IMPL

⚠️ V### 編號重排（v3.2 確認 4 wave 都加 migration）:
  V085 = W1 funding_curve
  V086 = W6 reject_reason_code metadata（先級高，governance writer 改）
  V087 = W1 oi_delta_panel
  V088 = W2 panel.btc_lead_lag_panel

D+3 ~ D+4 (W7 sign-off + W3 啟動)
  W7 E4 regression + Linux runtime 24h 驗 ma_crossover INXUSDT reject < 10/h + PM sign-off
  W3 PA cohort 拍板（D+4，等 W6 + W7 完成）+ atomic patch IMPL
  W3 Stage 1 cohort 3-day passive observation 開始（D+4-D+7）

D+5 ~ D+7
  W2 C-IMPL-3 strategy paper-only 接收 (ma_crossover + grid 接 BtcAltLeadLag feature, 1 day)
  W2 C-IMPL-4 paper engine 7d evidence collection 開始（D+5 起，跑到 D+12 後 review）
  W6 LightGBM imbalance 試行（D+5）+ M5 healthcheck（D+6）
  W1 MIT review + E2 review (D+5-D+6)
  W1 E4 regression + BB rate limit final + PM sign-off (D+7)
  W3 Stage 1 → Stage 2 promotion 嘗試（如達 criteria, D+7）

D+8 ~ D+10（4-agent final review）
  W6 PM sign-off + AMD land
  ALL except W2 paper IMPL → CC + QC + MIT + BB final review（4-agent parallel）
  W5 P1 closure 收尾

D+11 ~ D+12（W2 paper edge evidence review）
  W2 7d paper edge report land（QC 評估 +5 bps gate）
  Sprint N+1 sign-off + 22 + 新 invariant 23 全 PASS
  如 paper edge > +5 bps：N+2 dispatch draft 加 A4-C demo IMPL phase
  如 paper edge < +5 bps：N+2 dispatch draft 加 A4-C revise spec
  Memory persist
```

---

## §5 Risk + Dependency

### §5.1 Cross-Wave Conflict（v3.2 update）
- **W7 ↔ W2 trait coord 已被 PA D+0 合併 commit 解決**（PA #1 設計）— 5 個 E1 sub-agent 完全並行 0 file 重疊
- **W7 ↔ W3**：W3 Stage 1 cohort 觀察期必等 W7 fix（避 ma_crossover hot loop 干擾 attribution_chain 觀察）
- **W1 ↔ W3**：W3 Stage 1 cohort 觀察期不可同窗 W1 ML cron 觸發；建議 W1 land 後 ≥ 24h 再進 W3 Stage 1
- **W1 ↔ W5 (BB-BREAKOUT-FAIL-CLOSED-1)**：B-4 acceptance 直接 close 此 P1
- **W3 ↔ W5 (CANARY-STAGE-CRITERIA-1, COHORT-FREQ-23)**：兩個 P1 是 W3 dependency，必先 close
- **W7 ↔ W5 (P2-BB-BREAKOUT-POSITION-SYNC, P2-BB-REVERSION-POSITION-SYNC)**：W7-4 systemic audit 結果決定這兩 P2 是否 IMPL 或 close as duplicate

### §5.2 External Dependency
- **HIGH-5 12h watch sign-off**：21:30 UTC 失敗會觸發 Sprint N+0 部分 rollback；rollback 範圍 = W-AUDIT-9 GUI graduated tab + W-AUDIT-4b M3 reject negative label（保 W-AUDIT-9 trait + V082/83 不動）
- **QC replay 結論**：TONUSDT 結構性 negative → P1-TONUSDT-GRID-BLOCK 升 P0 加入 N+1 Day 1；short-term outlier → 維持 N+1 P1 backlog
- **MIT replay 結論**：chain integrity 歷史不一致 → 影響 W3 Stage 1 promotion criteria（需追加 leak check）

### §5.3 Bybit Risk（BB review 必過）
- W1 Tier 2 panel collector rate limit
- W2 A4-C cohort symbol Bybit 支持度（BUSDT 排除已記）

---

## §6 Acceptance Gate（Sprint N+2 hand-off conditions — v3.2 加 W7 + ML retrain 4-gate）

**全部** 達標才能 N+1 sign-off 進 N+2：

1. ✅ **W7 STRATEGY-POSITION-SYNC fix**：ma_crossover INXUSDT 24h reject rate < 10/h（從 baseline 666/h, **60+ x 改善**）；全策略 cross-strategy hot loop 0；5 策略 systemic audit report land
2. ✅ **W6 對齊 RFC verdict 明確**（預期：governance 正確、real gap = metadata + imbalance + duplicate_intent bug）+ **W6-1 verdict 明文「cost_gate hard rule 維持，不引 advisory mode」記入 RFC report**
3. ✅ **V086 reject_reason_code metadata land**：sqlx success=t；M3 producer 寫 reason 100% coverage（post-V086 sample）；features_jsonb + reject_reason_code dual-write
4. ✅ **Multi-class label split**：decision_features `label_close_tag` 顯示 3 類分布（rejected_cost_gate / rejected_duplicate_position / rejected_other）
5. ✅ **M4 reject reason mix monitor [59]**：baseline + alert 設好；24h dry-run 0 spurious alert（**不**用 reject rate > 95% 作 alert，這是 normal）
6. ✅ **[61] strategy fire silence healthcheck**（W6-7）：5 策略 24h 監控 baseline 入 console；funding_arb 排除清單 hard-code 已驗
7. ✅ **LightGBM imbalance handling 試行報告 land**（`is_unbalance` / `scale_pos_weight=4` AUC + precision + recall 對比）— **僅報告對比，不 deploy 入 production cron**（per PA #2 Q3 建議）
8. ✅ **ML retrain 4-gate 全達**（per PA #2 Q3）：(a) V086 land + dual-write 24h 0 NULL drift (b) multi-class label 3 類各 sample ≥ 200 row (c) LightGBM imbalance 試行報告 PASS (d) 全部 4 條才 enable production retrain
9. ✅ W1 Phase B funding_curve + oi_delta_panel writer 上線；25-symbol 1h 內 ≥ 100 row each
10. ✅ W2 A4-C spec 三方（PA / QC / MIT）APPROVE land + **paper IMPL fast-track**：AlphaSurface trait extension + lead-lag producer + V088 panel migration sqlx success + paper engine 7d 累積 sample n ≥ 100 fills per cohort symbol + paper edge report land（avg_net_bps + DSR + sample size）
11. ✅ W3 Stage 1 cohort 第一個 atomic patch 通過 [58] healthcheck；3-day observation attribution_chain_ok ≥ 80%
12. ✅ W4 W-AUDIT-3b runtime smoke pytest PASS + [55] chains_with_lease ≥ 1
13. ✅ W5 11 P1/P2 至少 6 closed（含 CANARY-STAGE-CRITERIA-1 + COHORT-FREQ-23 + DYNAMIC-UNBLOCK-CHECK-1 + V083-CONSTRAINT-VALIDATE plan land + BB-REVERSION-FIRE-AUDIT + 1）
14. ✅ 22 invariant + 新 invariant 23 全 PASS
15. ✅ CC + QC + MIT + BB 4-agent final review 全 APPROVE / APPROVE-CONDITIONAL
16. ✅ Memory persist + N+2 dispatch draft

**v3 移除（v2 設計取消）**：
- ❌ ~~如 W6 verdict = over-fit：conditional relax AMD land~~ — W6 baseline 預跑揭露 governance 沒 over-fit，conditional relax 會犯錯
- ❌ ~~Governance reject rate 進入 70-90% 合理區間~~ — 99.5% 是 normal（cost_gate 拒 negative edge 是正確），不應 force 降

**v3.2 新增（per PA 預跑）**：
- ✅ W7 STRATEGY-POSITION-SYNC（ma_crossover hot loop fix + 5 策略 architectural audit）
- ✅ W6-7 [61] strategy fire silence healthcheck
- ✅ W6-1 cost_gate hard rule 明文化
- ✅ ML retrain 4-gate
- ✅ LightGBM 試行不 deploy production

---

## §7 Sprint N+2 預告（不在本 dispatch 範圍）

- W-AUDIT-8a Phase C/D（Tier 3 microstructure / Tier 4 info-flow signal collectors）
- A 群 alpha 候選 IMPL（A-1 / A-2 / A-3）
- **A4-C demo IMPL**（v3.1 fast-track 後 N+1 paper edge > +5 bps 才走此路徑）OR **A4-C revise spec**（如 paper edge < +5 bps）
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

**已整合 evidence**（v3.2 update）:
- ✅ QC replay: TONUSDT 7-30d structural edge → `srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-10--tonusdt_structural_edge_replay.md`（verdict C，conditional path）
- ✅ MIT chain integrity replay → `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--chain_integrity_historical_replay.md`（chain 100%，governance reject 99.5% 提名 P0）
- ✅ MIT W6 baseline 預跑 → `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--governance_reject_baseline_w6_rfc.md`（governance 沒 over-fit，真 gap = metadata + imbalance + duplicate_intent bug）
- ✅ **PA #1 AlphaSurface trait coord** → `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--alpha_surface_trait_final_shape_w1_w2_coord.md`（W1+W2 並行 0 file 重疊，PA D+0 commit ~85 LOC 含 W7 TickContext）
- ✅ **PA #2 W6 RFC PA-view** → `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_rfc_pa_questions_self_answer.md`（4 立場 + 6 條 dispatch update）
- ✅ **PA #3 P1-MA-CROSSOVER audit** → `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--p1_ma_crossover_duplicate_intent_audit.md`（HIGH confidence cross-strategy desync hot loop，升 P0 W7）

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
