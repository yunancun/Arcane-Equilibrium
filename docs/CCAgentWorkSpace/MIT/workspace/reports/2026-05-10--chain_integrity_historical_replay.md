# MIT Chain Integrity Historical Replay — 2026-05-10

## V082/V083/V084 Install 時間
- 三個 migration 同時 install: **2026-05-10 09:22:59 UTC** (engine restart auto-migrate)
- audit window: pre = 2026-05-03 → 09:22 UTC / post = 09:22 UTC → 12:50 UTC (~3.5h)

## 1. Chain Ratio per Strategy: V083 install 前 vs 後

| Phase | Strategy | engine_mode | n_fills_w_entry | match_df | orphan | chain_ok |
|-------|----------|-------------|-----------------|----------|--------|----------|
| pre_v083  | grid_trading | demo      | 131 | 131 | 0 | **100%** |
| pre_v083  | grid_trading | live_demo | 79  | 79  | 0 | **100%** |
| pre_v083  | ma_crossover | demo      | 50  | 50  | 0 | **100%** |
| pre_v083  | ma_crossover | live_demo | 31  | 31  | 0 | **100%** |
| pre_v083  | bb_breakout  | demo      | 11  | 11  | 0 | **100%** |
| pre_v083  | bb_reversion | demo+live_demo | 2 | 2 | 0 | **100%** |
| pre_v083  | funding_arb  | demo      | 8   | 8   | 0 | **100%** |
| post_v083 | grid_trading | demo      | 6   | 6   | 0 | **100%** |
| post_v083 | grid_trading | live_demo | 4   | 4   | 0 | **100%** |

**結論**：fills.entry_context_id → decision_features.context_id chain 在 V083 land 之前已 100%。V083 是新增 entry_context_id column + check constraint (NOT VALID 不對舊 row enforce)，但 producer code 早於 2026-04-15 起就在寫 decision_features (n=9.5M)，writer code 對 entry_context_id 的接線在 2026-05-03 前就部分到位。memory 「100% n=199/59/11」是 narrow window 樣本，**真實全期 chain integrity 也是 100%**。

## 2. Memory Baseline 修正
- `decision_features` 全期: bb_breakout 60 / bb_reversion 630 / funding_arb 8980 / grid 112k / ma 9.4M (V082 install 之前已大量寫)
- post-V082 W2: grid 486 / ma 5900 / **bb_breakout 0** (post-V082 沒寫過)
- bb_breakout 在 V082 land 後 sample 為 0 不是 chain broken，是策略本身在 W2 baseline 期間幾乎沒觸發

## 3. Silent Broken Pattern
**未發現 silent broken**。但發現 **W-AUDIT-4b M3 (reject negative producer) 已激活**：
- post-V082: 6361/6394 (99.5%) decision_features 標 `label_close_tag='rejected_governance'` + label_net_edge_bps=0
- 集中於 `ma_crossover (ETHUSDT 3568, INXUSDT 2331)` + `grid (ETH/BTC/ZEC 各 130-188)`
- 真正 fill 發生並關閉的只有 **9 條 grid_trading** (label_close_tag='grid_trading', avg edge 40.32 bps, min -11.94 max 200.37)

設計上正確：governance 預測 -EV 即 reject + 寫 0 bps 為 negative label，給 LinUCB / LightGBM 訓練 negative class。但需確認 **governance reject rate ~99.5%** 是否符合預期。

## 4. decision_outcomes Label Coverage (last 7d)
| engine_mode | n | pct_24h | pct_1h | pct_5m | n_backfilled |
|-------------|---|---------|--------|--------|--------------|
| demo        | 875018 | 78.64% | 95.61% | 97.23% | 100% |
| live        | 89734  | 84.88% | 98.36% | 99.79% | 100% |
| live_demo   | 371364 | 79.32% | 92.24% | 93.73% | 100% |

label backfill cron 在跑 (backfilled_ts 100% NOT NULL); 24h coverage <100% 是因 last 7d 中含 last 24h 視窗未到，**不是 broken**。

## 5. evaluation_outcome 分布
post-V082 4070/4070 全 `use_legacy_no_predictor` + entry_context_id=0/4070 NULL。**ML predictor 沒接** = expected fallback 路徑 (M3 reject negative label 走的不是 evaluations 表而是 decision_features 直寫)。**不是 broken**。

## 6. HIGH-5 Watch Metric 1 結論
**補強 evidence 充足，可 12h 提早結案**：
- chain integrity 真實 100% (pre+post V083)，0 orphan
- V082/V083/V084 land 後 3.5h 已驗 producer + reject negative + chain join 全通
- decision_outcomes label backfill 100% backfilled_ts (cron 健康)
- 唯一 gap = ML predictor 未接 → evaluations 表全 use_legacy_no_predictor，但這在 W2 baseline 設計範圍內 (W3 才接 predictor)

12h forward 觀察唯一風險 = governance reject rate 99.5% 是否藏 over-fit (拒所有正常信號)，需 W-AUDIT-4b M4 跟蹤。

## 7. W-AUDIT-4b 後續建議 (M4/M5)
- **M4 (建議)**: governance reject rate monitor — 若連續 24h >95% reject 觸 alert，避免 producer 寫純 negative class 偏訓練
- **M5 (建議)**: ML predictor 接通後 evaluations.entry_context_id 必須非空 (對 reject_add) — 加 healthcheck `check_evaluations_entry_ctx_coverage()`
- **持續驗 V083 check_constraint NOT VALID → 何時 VALIDATE** (老 fills 不過 backfill 直接 VALIDATE 會 fail 全表)

