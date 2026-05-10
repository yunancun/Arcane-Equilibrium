# W6 RFC — PA 預備立場（4 questions 自答）

**日期**：2026-05-10
**性質**：D+1 W6 RFC 三角（PA + QC + MIT）入場前 PA 視角預跑；不答 QC + MIT 視角
**前置依據**：MIT W6 baseline `2026-05-10--governance_reject_baseline_w6_rfc.md` + Sprint N+1 dispatch v3.1
**Source code 取證**：
- `srv/rust/openclaw_engine/src/intent_processor/gates.rs:14-260`（cost_gate paper / moderate / live 三層）
- `srv/rust/openclaw_engine/src/intent_processor/tests.rs:1360-1421`（duplicate_position 同方向 reject + 反方向 allow 測試）
- `srv/rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs:75-170`（on_tick + self.positions in-position guard）

---

## Q1 — cost_gate JS-demo estimate -13.28 bps 是 hard rule 還是 advisory？4079 條全 reject 是否符合設計意圖？是否該降為 advisory + LinUCB 自學？

### PA 立場：**hold A — cost_gate 維持 hard rule，4079 reject 符合設計**

### 論據
1. **`gates.rs:108-184` 三層設計就是分層：paper 探索（過 reject 只 log）/ demo moderate（n_trades < min_n 探索；n≥min_n 負估計 hard reject）/ live 嚴格（fail-closed 任何負/缺估計）**。當前 4079 條 reject 全在 demo `cost_gate_moderate_with_slippage` 第 165-173 行 `Some(cell) if shrunk_bps < 0` 分支 — n_trades 已過 min_n 統計穩健的負 JS 估計才阻擋，**設計上正確**。
2. **降為 advisory + LinUCB 自學會違反根原則 #5（生存>利潤）+ #4（策略不繞風控）**。cost_gate 拒掉 -13.28 bps 是預期 net loss，放行讓 LinUCB「自學」= 用真錢餵 ML，符合 4-agent loss audit「5 textbook 策略結構性 alpha-deficient」結論：問題不是 governance 太緊，是策略本身 alpha 為負。
3. **演進路徑該走 W6-3 multi-class label split + V086 reject_reason metadata，不是放閘**。讓 ML 學「在這 market state 會被 cost_gate 拒 → 改 cost / 改 timing」遠勝過放行虧損訓練。

### 架構影響
- **無 ARCH / ADR 需動**。維持現狀即根原則 #5/#4 達成。
- **AMD 反向確認**：v3.1 dispatch §6 已移除 v2 「conditional relax AMD」是正確；本立場補強此移除。

### Dispatch v3.1 對齊
- ✅ 與 §0.2.B「真正 bottleneck 仍是策略本身 negative edge」一致；
- ✅ 與 §6 acceptance gate 移除「reject rate 70-90% 合理區間」一致；
- ⚠️ 建議補：W6-1 RFC verdict 明文「cost_gate hard rule 維持，不引入 advisory mode」入記錄，避免 N+2 又重提。

---

## Q2 — duplicate_position guard 對 ma_crossover INXUSDT 鎖 SHORT 1810 — 是否該允許 pyramiding？2331 條 reject 是策略想加倉

### PA 立場：**hold A — 不開 pyramiding；2331 reject 是 ma_crossover bug 不是 guard 過嚴**

### 論據
1. **`tests.rs:1360-1421` test 雙證**：同方向 reject（test_duplicate_position_same_direction_rejected）+ 反方向 allow（平倉路徑）= **架構級不變式**，不是配置開關。Pyramiding **從未在設計範圍**；要開 = 動 IntentProcessor router Gate 1.5 + paper_state position model + Guardian risk envelope（極高風險改動，CLAUDE.md §四 嚴防）。
2. **`strategy_impl.rs:138-145` ma_crossover 內部已有 `match self.positions.get(ctx.symbol)` → `None` 才 entry**。被 duplicate_position 阻 2331 次意味著 **策略內部 self.positions HashMap 跟 IntentProcessor/paper_state 真實 position state 不同步** — 策略以為沒倉位反復 emit entry，被 router Gate 1.5 兜住。**這是 ma_crossover state sync bug，不是 guard 過嚴**。
3. **若 pyramiding 真有 alpha 應改走 A4-C BTC→Alt Lead-Lag (W2)**，而非 hack ma_crossover 加碼。Pyramiding = 策略級設計選擇，需 PA + QC + MIT 三角對 alpha source / sizing / drawdown 重 design，不在 W6 scope。

### 架構影響
- **無 ARCH 動**；duplicate_position guard 是不可變式守護。
- **新 P1 ticket 已在 v3.1 §3.5 列入：P1-MA-CROSSOVER-DUPLICATE-INTENT** — fix scope = 同步 ma_crossover self.positions 與 paper_state（fill 回報後 update + bootstrap 時重建）。

### Dispatch v3.1 對齊
- ✅ 與 §3.5 P1-MA-CROSSOVER-DUPLICATE-INTENT 一致（PA + E1 audit 2 day）；
- ⚠️ 建議補：audit 點明 (1) `on_fill()` 是否 update self.positions (2) bootstrap 是否從 paper_state import_positions 重建 (3) reject 是否 rollback self.positions（已有 RC-04 `prev_position` snapshot 線索 strategy_impl.rs:135-141）。

---

## Q3 — V086 reject_reason_code metadata 樣本累積到何時才需要？

### PA 立場：**hold A — V086 IMPL 立刻做（W6-2 D+1~D+2），ML 訓練 enable 等 sample n ≥ 1000 + 24h dual-write 驗證 0 dropout 才開**

### 論據
1. **V086 schema add 是 producer-side 改動，越早做越早累積**。當前 reject 6415/3.5h ≈ 1830/h，若 V086 W6-2 D+2 上線，**3 day 內可累 ~130k row 含 reason_code**，遠超 LightGBM 1000 row baseline。瓶頸不在累積速度，在 **multi-class label split (W6-3) + LightGBM imbalance handling (W6-5) 完成才 retrain**。
2. **不能等樣本「成熟」才補 schema** — V086 不上線 = 從 D+0 起繼續寫無 reason 的負樣本污染未來 ML re-train baseline。MIT F1 「decision_features 100% 不知道為何被 reject」是當前最大 ML metadata gap，立刻補。
3. **ML 訓練 enable timing 跟 V086 land 解耦**。建議 gate：(a) V086 land + W-AUDIT-4b M3 producer dual-write reason_code (b) 24h healthcheck 0 NULL drift (c) multi-class label split land + 3 類 sample 各 ≥ 200 row (d) LightGBM imbalance handling 試行報告通過 — 4 條全達才 retrain。

### 架構影響
- **無 ARCH 動**；V086 是 schema add column + jsonb，遵 Guard A/B/C 模板。
- **W-AUDIT-4b M3 producer 解 V017 lock**（intent_processor/mod.rs:1213「reject_reason 當前不入 schema」）— 屬中風險改動，E2 必查 dual-write race。
- **Sub-agent 派發**：V086 + M3 producer 改 + multi-class label 屬 E1 IMPL 串行（schema → producer → consumer label 重定義），不可並行（schema 是 prerequisite）。

### Dispatch v3.1 對齊
- ✅ 與 §3.0 W6-2 / W6-3 / W6-5 三 sub-task 一致；
- ⚠️ 建議補：W6 acceptance §6 第 5 條「LightGBM imbalance 試行報告 land」明文「**僅報告對比 AUC/precision/recall，不 deploy ML predictor 入 production cron**」— 等 multi-class label + reason_code dual-write 24h drift = 0 才 deploy；
- ⚠️ 建議補 ML retrain trigger：4 條 gate（V086 land + dual-write 24h 0 NULL + multi-class 3 類 sample ≥ 200 + imbalance 試行報告 PASS）入 P1-V083-CONSTRAINT-VALIDATE 同窗 healthcheck。

---

## Q4 — bb_breakout / bb_reversion / funding_arb post-V082 0 fire 是「dormant by design」還是「scanner 沒 surface」？

### PA 立場：**depends — funding_arb 確定 dormant by design；bb_breakout/bb_reversion 需分開觀察 (1) AlphaSurface trait declare 但 consumer 未接 vs (2) scanner threshold 過嚴**

### 論據
1. **funding_arb = dormant by design**（已決）：ADR-0018 + AMD-2026-05-09-02 確認退休；4 個 risk_config*.toml W-AUDIT-6 cleanup 完；strategy_params_*.toml `active=false`。**post-V082 0 fire 屬預期**，不需 W6 處理。
2. **bb_breakout = AlphaSurface consumer gap**（v3.1 W1 §3.1 B-4 已點明）：W-AUDIT-8a Phase A trait declare `OiDeltaPanel` 但 Phase B Tier 2 panel writer 還沒 land（W1 D+1~D+7 才做）。**bb_breakout fail-closed 應寫 `oi_panel_unavailable` evaluation_outcome 而非 silent dormant**。0 fire 是 metadata 透明度 bug，不是策略 alpha 死亡。
3. **bb_reversion = 多源因素**：(a) W-AUDIT-6d 保 6 #6 verdict pair MA pending；(b) scanner threshold 收緊（K-VOL filter）+ market regime 收斂（low-vol 期 reversion 信號稀少）；(c) 是否同 bb_breakout 有 AlphaSurface consumer gap 需另查。**需 W6 監測 N+1 期間 bb_reversion fire 條件達成率**，不在 W6-4 monitor [59] reject reason mix 範疇 — 這是 entry-side observability gap。

### 架構影響
- **無 ARCH 動**；funding_arb 退休架構已就位。
- **W6-4 [59] monitor scope 不變**（reject reason mix），但**建議補配套 [60] healthcheck `check_strategy_fire_silence()`** — 5 策略 24h 0 fire 報 WARN（funding_arb 排除）+ root cause 列舉（cooldown / regime / panel_unavailable / scanner_threshold）。
- bb_breakout/bb_reversion 真實 alpha 評估留 N+2（W-AUDIT-8a Phase B/C/D 上線 + AlphaSurface consumer 接通後）。

### Dispatch v3.1 對齊
- ✅ 與 §3.1 W1 B-4「bb_breakout fail-closed path 寫 `oi_panel_unavailable`」一致；
- ⚠️ 建議補新 sub-task **W6-7 [60] strategy fire silence healthcheck**（E1 IMPL 0.5 day），與 W6-4 [59] 同窗；funding_arb 排除清單 hard-code 防 false WARN；
- ⚠️ 建議補新 P1 ticket **P1-BB-REVERSION-FIRE-AUDIT**（PA audit 1 day）— grep bb_reversion entry condition + 對比 24h scanner candidates 看是 entry condition 太嚴 vs scanner 過濾掉 vs panel consumer gap。

---

## §5 PA 預備立場總結（W6 RFC D+1 入場帶這個）

| 維度 | PA 立場 | 對 v3.1 dispatch 的影響 |
|---|---|---|
| Q1 cost_gate hard vs advisory | **hold A** 維持 hard，不引 advisory | 補 RFC verdict 明文記入，避免 N+2 重提 |
| Q2 duplicate_position pyramiding | **hold A** 不開 pyramiding；reject 是 ma_crossover state sync bug | P1-MA-CROSSOVER-DUPLICATE-INTENT audit 點補 3 個 fix 候選 |
| Q3 V086 metadata 時機 | **hold A** V086 立刻做；ML retrain enable 等 4-gate | 補 ML retrain 4-gate 寫入 acceptance §6 |
| Q4 bb_*/funding_arb 0 fire | **depends** funding_arb dormant；bb_* 需分查 | 補 W6-7 [60] silence healthcheck + P1-BB-REVERSION-FIRE-AUDIT |

**核心整體立場**：W6 不是 governance 工程而是 **observability + ML metadata 工程**。三方向 — (1) 不放閘 (2) 修 ma_crossover state sync (3) 補 reason_code metadata + multi-class + imbalance handling — 都不觸碰 cost_gate / duplicate_position / DOC-08 §12 9 條安全不變式 / §四 三硬邊界。**16 根原則合規 16/16；硬邊界觸碰 0**。

QC + MIT 視角（cost_gate noise floor / counterfactual edge / DSR / imbalance 算法選擇 / multi-class CV）留 D+1 三角。

---

## §6 Dispatch v3.1 update 建議（出建議 only，不 edit dispatch — operator 拍板）

| # | 位置 | 建議 |
|---|---|---|
| 1 | §3.0 W6-1 | RFC verdict 明文記「cost_gate hard rule 維持，不引 advisory mode」入文件 |
| 2 | §3.0 W6 | 加 sub-task **W6-7 [60] strategy fire silence healthcheck**（E1 0.5 day，與 W6-4 同窗，funding_arb 排除清單 hard-code） |
| 3 | §3.5 P1-MA-CROSSOVER-DUPLICATE-INTENT | audit 點補 3 fix 候選：(a) `on_fill()` update self.positions (b) bootstrap 從 paper_state import_positions 重建 (c) reject 走 RC-04 `prev_position` rollback |
| 4 | §3.5 P1 list | 加新 ticket **P1-BB-REVERSION-FIRE-AUDIT**（PA audit 1 day）— bb_reversion entry condition + scanner 過濾 + panel consumer gap 三源因素 grep |
| 5 | §6 Acceptance Gate | 第 5 條「LightGBM imbalance 試行報告 land」明文「**僅報告對比，不 deploy 入 production cron**」 |
| 6 | §6 Acceptance Gate | 加新 ML retrain 4-gate（V086 land + dual-write 24h 0 NULL + multi-class 3 類 sample ≥ 200 + imbalance 試行報告 PASS）入 P1-V083-CONSTRAINT-VALIDATE 同窗 healthcheck |

---

PA DESIGN DONE: report path: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_rfc_pa_questions_self_answer.md`
