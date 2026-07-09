# MIT Governance Reject Baseline — W6 RFC 三角共用 raw data
**日期**：2026-05-10  
**Window**：post-V082 install (2026-05-10 09:22:59 UTC) ~3.5h；pre-V082 baseline = 2026-05-03 ~ 09:22 UTC (~7d)  
**Boundary**：純 data dive；不寫 RFC 結論，不建議 governance 閾值數值。

---

## 1. Schema discovery — reject reason metadata 真實位置

| Table | reject reason 欄位 | post-V082 row | 結論 |
|---|---|---|---|
| `learning.decision_features` | **無** reason 欄；features_jsonb 是 17-dim 市場 feature snapshot（side/atr_pct/funding_rate/orderbook_imbalance...）| 6444（reject 6415 / 99.55%）| W-AUDIT-4b M3 producer 寫 negative label 但**不寫 reject reason**（Rust source `intent_processor/mod.rs:1213`：「reject_reason 當前不入 schema (V017 鎖死)，保留參數方便未來 extend」）|
| `trading.risk_verdicts` | `reason text` + `checks_failed text[]` + `details jsonb` | 6454（Rejected 6423 / Approved 31）| **真正 reject reason SoT**；context_id 與 decision_features 1:1 對應 |
| `learning.governance_audit_log` | event_type CHECK = lease/replay/review，**不允** pre_intent_reject | post-V082 = **0**；總 22813 row 全是 LG-5 review_live_candidate | 與 W-AUDIT-4b M3 完全是兩條獨立 audit trail |
| `replay.mlde_replay_veto_log` | veto_reason CHECK 5 值 | 無關 runtime reject | replay 端用 |

**Finding F1（HIGH）**：W-AUDIT-4b M3 reject path **完整 reject reason 只活在 trace log + risk_verdicts.reason 字串**；decision_features 100% 不知道為何被 reject。LinUCB / LightGBM 拿 1/170 sample weight 訓練的負樣本是**「我被 reject 了」+ 17 維 market state**，不是「為什麼被 reject」+ counterfactual 信息。

---

## 2. Reject reason distribution（risk_verdicts SoT，post-V082）

| Reason（縮）| Count | % | 觸發策略×符號 |
|---|---|---|---|
| cost_gate(JS-demo) estimated=-13.28bps | 3568 | 55.6% | ma_crossover ETHUSDT |
| duplicate_position INXUSDT already SHORT 1810 | 2331 | 36.3% | ma_crossover INXUSDT |
| cost_gate(JS-demo) estimated=-15.99bps | 216 | 3.4% | grid ETHUSDT |
| cost_gate(JS-demo) estimated=-13.83bps | 155 | 2.4% | grid BTCUSDT |
| cost_gate(JS-demo) estimated=-13.82bps | 140 | 2.2% | grid ZECUSDT |
| cost_gate ATR unavailable (fail-closed, SEC-11) | 13 | 0.2% | 多策略雜散 |

**只有 2 大類 reject**：cost_gate(JS-demo) negative edge estimate（4092/63.7%）+ duplicate_position guard（2331/36.3%）。**沒有** scanner_advisory / volatility / DSR / position_size / margin_util reject — 這 4 條 governance gate 在 post-V082 3.5h 內 0 觸發。

---

## 3. Per-strategy × per-symbol heatmap (top 20)

| Strategy | Symbol | engine_mode | Reject count |
|---|---|---|---|
| ma_crossover | INXUSDT | live_demo | 2331 |
| ma_crossover | ETHUSDT | live_demo | 1784 |
| ma_crossover | ETHUSDT | demo | 1784 |
| grid_trading | ETHUSDT | live_demo | 107 |
| grid_trading | ETHUSDT | demo | 107 |
| grid_trading | ZECUSDT | demo | 78 |
| grid_trading | ZECUSDT | live_demo | 77 |
| grid_trading | BTCUSDT | demo | 70 |
| grid_trading | BTCUSDT | live_demo | 70 |
| grid_trading | {SOLAYER, SUI, TON, SAHARA, ONDO, INX} | demo + live_demo | 各 1-2 |

**集中度極高**：ma_crossover 占 84%（5899/6415）；4 大 grid symbol 占 14%；其餘策略 0 reject。bb_breakout / bb_reversion / funding_arb post-V082 完全沒 fire。

---

## 4. 時間趨勢

| Hour | Reject | Fill | Fill rate |
|---|---|---|---|
| 11:00 | 2542 | 6 | 0.23% |
| 12:00 | 3859 | 4 | 0.10% |
| 13:00 | 18 | 0 | 0% (n=18 太少) |

Pre-V082 baseline (7d, 2026-05-03 ~ 09:22 UTC)：88587 row, **0 reject** (label_close_tag 全 NULL — M3 producer 還沒接通)。

**Finding F2（MED）**：Reject rate 從 pre-V082 0% → post-V082 99.55% 是 W-AUDIT-4b M3 producer 切上線新行為，**非 governance 閾值收緊**。三角不應誤讀為「策略表現惡化」。

---

## 5. 真實 close fill 10 條分析

| Strategy | Symbol | label_close_tag | edge_bps | ts |
|---|---|---|---|---|
| grid | SOLAYERUSDT | grid_trading | -5.38 | 11:24 |
| grid | SOLAYERUSDT | grid_trading | +1.71 | 11:24 |
| grid | INXUSDT | grid_trading | **+200.37** | 11:29 |
| grid | INXUSDT | grid_trading | +15.32 | 11:29 |
| grid | SOLAYERUSDT | grid_trading | -2.50 | 11:35 |
| grid | SOLAYERUSDT | grid_trading | +54.51 | 11:49 |
| grid | INXUSDT | grid_trading | +112.91 | 12:01 |
| grid | INXUSDT | grid_trading | -11.94 | 12:01 |
| grid | SAHARAUSDT | grid_trading | -28.16 | 12:20 |
| grid | INXUSDT | grid_trading | -2.10 | 12:21 |

**全 grid_trading**；avg +33.47 bps / median -2.10 / hit 5/10。3-symbol（SOLAYER 4 / INX 4 / SAHARA 1 / ZEC 1）— 與 reject heatmap 完全分離（ma_crossover ETHUSDT/INXUSDT + 4 grid 大 cap 全 reject 0 fill）。

**Finding F3（HIGH）**：fill rate < 0.2% 的 governance pass 是極窄正類（INX 突破 +200 bps 是 outlier）；模型訓練 imbalance 6415:10 = 642:1（V084 sample_weight=1/170 修正後變 6415*(1/170):10 = ~38:10 ≈ 4:1），**仍嚴重 long-tail positive class 偏差**。需 W6 RFC PA 評估 LightGBM imbalance handling 是否能撐這個比例。

---

## 6. W6 RFC 三角預備 questions（不答，問題 only）

### PA 視角
1. cost_gate JS-demo estimate -13.28 bps 是 hard rule 還是 advisory？4079 條全 reject 是否符合 cost_gate 設計意圖？是否該降為 advisory + LinUCB 自學？
2. duplicate_position guard 對 ma_crossover INXUSDT 鎖 SHORT 1810 — 是否該允許「同方向加碼」（pyramiding）？2331 條 reject 是策略想加倉但被 guard 阻
3. W-AUDIT-4b M3 producer 寫 features_jsonb 不寫 reject reason — 是否要加 V086 補 reject_reason_code column？樣本累積到何時才需要？
4. bb_breakout / bb_reversion / funding_arb post-V082 0 fire 是「策略 dormant by design」還是「scanner 沒 surface entry」需要分開觀察？

### QC 視角
1. cost_gate JS-demo edge estimate -13.28/-15.99/-13.83/-13.82 bps 不同 symbol 都接近 -14 ± 2 是 noise floor 還是 estimator 系統性 bias？對 grid 三 symbol（ETH/BTC/ZEC）回 +0 bps 機率多少？
2. 10 真實 fill avg +33.47 bps / median -2.10 / hit 50% — 假設 cost_gate 開放更寬，model expected new fills net edge 正期望值落在哪？需要 backtest counterfactual？
3. INXUSDT +200/+112.91 bps 兩 outlier 占 grid total edge 96% — 不去 outlier 後 hit rate / Sharpe / DSR 多少？
4. duplicate_position 解鎖後 SHORT 加碼 vs reverse 信號（混合 long+short ma_crossover 在 INXUSDT trend）哪個 P[positive expected value]？

### MIT 視角
1. **6415 negative + 10 positive = 642:1 imbalance** — V084 sample_weight 1/170 修正後仍 ~4:1，LightGBM `is_unbalance=True` / `scale_pos_weight=4` / focal loss / SMOTE 中哪個合適？
2. features_jsonb 17-dim 全 market state 0 reject reason — train 出來模型只學到「在這個 market state 下會被 cost_gate / duplicate_position 拒」**不學會「為何拒」**。是否該等 V086 加 reject_reason_code 才開 ML training？
3. label_close_tag = 'rejected_governance' 把所有 reject 拍平為一個類 — 是否該 split `rejected_cost_gate` / `rejected_duplicate_position` 兩 multi-class label？
4. fill 10 條 / 3.5h ~ 70/day extrapolate；達 LightGBM 1000+ row 訓練 baseline 需 2 週純累積 — 與 cron weekly 訓練 schedule 對不對齊？

---

## 7. Findings Summary

| ID | Severity | Finding |
|---|---|---|
| F1 | HIGH | reject reason 不入 decision_features schema → W-AUDIT-4b M3 metadata gap |
| F2 | MED | reject rate 0% → 99.55% 是 producer 切上線新行為非 governance 收緊 |
| F3 | HIGH | 642:1 imbalance；V084 weight 1/170 修正後仍 4:1 long-tail bias；INX outlier dominate edge |

