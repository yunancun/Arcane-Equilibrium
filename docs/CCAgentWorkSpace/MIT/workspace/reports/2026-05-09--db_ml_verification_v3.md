# MIT 對抗性核實 v3 — 5 commits + PA redesign cross-check

**Verification window**: 2026-05-09 19:00 UTC+2  
**Baseline**: v2 HEAD `1bd55689` → v3 HEAD `da2aba11`（5 commits, ~3h delta + PA redesign land）  
**Engine**: PID 246778 (uvicorn worker) active；binary started 14:07（**比 5 commits 早 4h**）  
**SSOT**: Linux PG `trading_ai` (host TCP) 直查 + crontab 實測 + V079 sqlx_migrations 直驗 + Rust feature_collector::FEATURE_NAMES 直讀 + view definition 直讀  
**對抗性原則**：commit message + Rust source ≠ runtime live；migration file 存在 ≠ apply；source-only 接線 ≠ runtime；cron script 存在 ≠ install in crontab

---

## §0 Executive Summary

**ML 基座達標率**：v2 44% → **v3 44%**（**0 改善**，原因詳 §2）

**核心發現**：
1. ❌ **V079 migration 完全未 apply**（`max(version)=78`），48227607 commit 的 schema 改動 100% 不在 PG
2. ❌ **strategy_trial_ledger table 不存在**，promotion_pipeline.demo_selection_bias_report column 不存在
3. ⚠️ **attribution_chain_ok 24h: v2 0.5041% → v3 1.0857%**（denominator artifact 持續：absolute ok_n 65→76 only +17%, total 12894→7000 -46%）
4. ✅ **attribution 失敗 root cause = `label_close_tag IS NULL` 98.9%**（6906/6983 has signal_id+context_id+label NULL）— 非 PA 寫的「writer 寫 NULL context_id」
5. ❌ **`feature_baseline writer` 34-dim 100% TA-derived**（SMA/EMA/RSI/MACD/BB/ATR/Stoch/KAMA/ADX/Hurst/Donchian）— **PA Layer 1 §1.1 alpha-source 結構性貧乏 MIT 視角全成立**
6. ❌ **ml_training_maintenance_cron.sh 未 install in crontab**（da2aba11 commit 改 source 但 cron 未 install）
7. ❌ **V073 / V074 cron 仍未 install**（W-AUDIT-4 P0 從 v1 拖到 v3 三天無動）
8. ⚠️ **lease_transitions 24h BYPASS = 11133**（v2 7955 → v3 11133，+40% steady ~33-46/min；唯一真 active component）
9. ⚠️ **decision_outcomes.live latest_backfill 仍 4/20**（19d stale 持平；demo + live_demo 18:47 fresh）
10. ❌ **5 commits 全部 0 healthcheck**（V079 trial_ledger / blocked_symbols freeze / promotion_evidence push / ml_training_maintenance / bb donchian guard）

| 5 commits | ML/data 視角影響 | Verdict |
|---|---|---|
| ad14db07 bb donchian guard | 0 ML pipeline 影響（Rust 內部 indicator guard） | N/A |
| c2ab7b1a strategist wide adjustment | 0 ML pipeline 影響（agent skill 配置） | N/A |
| **48227607 push promotion evidence from edge cycle** | **schema-side wired but V079 unapplied → 0 PG impact** | ❌ source-only |
| **c081029d freeze blocked symbols** | **lock 17 grid + 4 ma blocked symbols → existing selection bias 凍結 not 新增**；governance freeze ≠ universe shrink | ⚠️ neutral; 無新 bias |
| **da2aba11 f08 ml cron scope** | **5 legacy ML script (thompson/optuna/cpcv/dl3/weekly_report) wired into runner，但 cron not installed → 0 runtime impact** | ❌ source-only |

**PA redesign cross-check**：
- ✅ **PA Layer 1 §1.1 (alpha-source 結構性貧乏)** — MIT ML 視角**強烈 AGREE**（feature_collector 34-dim 全 TA derived；exit_features 7-dim 全 OHLCV derived；無 funding/basis/OI/orderflow/cross-asset）
- ⚠️ **PA Layer 1 §4.2 attribution_chain 0.5% root cause** — **PA 寫的 root cause 不準**：實測 root cause 是 label_close_tag NULL 98.9%，非 mlde_demo_applier filter 也非 v1 寫的 NULL context_id
- ❌ **PA Cluster B「F-08 5 ML scripts unscheduled」** — **da2aba11 commit 補了 source 但 cron 仍未 install**，所以 Cluster B 「F-08」這條 finding 文檔已 closed 但 runtime 仍 dormant

**MIT VERDICT v3**：5 commits 中**0 真 runtime IMPL**（V079 不在 PG、ml_training_maintenance cron 不在 crontab、blocked_symbols freeze 是 governance docs 加 audit helper、bb donchian + strategist skill 與 ML pipeline 無直接關係）。**3-day window v1→v2→v3 ML 基座 runtime 健康度 0 進展**。

---

## §1 5 commits 對抗性核實 — ML/data 影響

### 1.1 ad14db07 strategy: guard bb breakout donchian snapshots

**ML/data 視角**：0 直接影響。Rust strategies/bb_breakout.rs 內部 indicator NaN guard。**對 ML 學習平面、特徵管線、attribution chain 均無 wiring**。

**Verdict**：N/A for ML pipeline audit。

### 1.2 c2ab7b1a strategist: teach wide adjustment skill

**ML/data 視角**：0 直接 ML pipeline 影響。Strategist agent skill metadata 加「wide adjustment」字眼，max_param_delta_pct 30→50 已在 v2 的 F-strategist-cap 改動。**屬 PA Layer 1 §1.2 「Strategist scope = 調參器」反例（沒有 alpha-discovery 職責，只是放寬參數調整幅度）**。

**Verdict**：N/A for ML pipeline；reinforce PA Layer 1 §1.2「Strategist 是 dict[str, float] 微調器」結論。

### 1.3 48227607 learning: push promotion evidence from edge cycle ⭐ **重點**

**聲稱**：DSR/PBO + tail-risk evidence 從 edge cycle push 到 promotion_pipeline + 新增 V079 strategy_trial_ledger。

**實測**：
```
sqlx_migrations max(version) = 78  ← V079 從未 apply
strategy_trial_ledger table = does not exist  ← V079 未 apply 故無此 table
learning.promotion_pipeline schema = unchanged (no demo_selection_bias_report column)
edge_estimator_scheduler.py 改動 = +126 LOC（_run_promotion_evidence_push method + stress_exposures from env injection）
```

**對抗性 push back**：
- ❌ V079 file 在 `/home/ncyu/BybitOpenClaw/srv/sql/migrations/V079__promotion_evidence_trial_ledger.sql` ✅ exists
- ❌ V079 在 _sqlx_migrations table = ❌ NOT APPLIED
- ❌ Engine PID 246778 binary built 14:07 = **比 commit 18:03 早 4h** → 即使 OPENCLAW_AUTO_MIGRATE=1，當前 binary 也不會跑 V079 migration
- ❌ Even if applied，promotion_pipeline 仍是 v2 報告 §8.2 標的 dormant module（PromotionPipeline class 無外部 caller，`_entries: dict` 從未 populated）— **加 source 不加 caller = 加 dormant code**
- ❌ commit message 未提「needs engine restart」、「needs OPENCLAW_AUTO_MIGRATE=1」、「needs operator manual `sqlx migrate run`」

**真實 runtime impact**：0。Promotion evidence push code path 永不被執行因為：
1. V079 schema 不存在 → INSERT to strategy_trial_ledger fail
2. UPDATE promotion_pipeline SET demo_selection_bias_report fail
3. _run_promotion_evidence_push 設計為 fail-open（`return {"status": "error", ...}`）— **silently swallow error**

**Verdict**：❌ **source-only IMPL with 0 PG impact + silent fail-open hides the failure**。屬 PA Layer 2 Cluster C「Authority/Lineage drift — spec 與 runtime 漂移」教科書例證。

### 1.4 c081029d governance: freeze blocked symbol lists

**聲稱**：grid_trading + ma_crossover 的 blocked_symbols frozen + 7d counterfactual audit helper。

**實測**：
```
Frozen lists:
  grid_trading: 17 symbols (BSBUSDT/PRLUSDT/ZBTUSDT/FARTCOINUSDT/SOLUSDT/DOGEUSDT/...)
  ma_crossover: 4 symbols (NAORISUSDT/PENGUUSDT/FARTCOINUSDT/LABUSDT)

Demo runtime universe (7d unique symbols):
  grid_trading: 41 active symbols
  ma_crossover: 22 active symbols
  bb_breakout: 10
  bb_reversion: 1
  funding_arb: 5
```

**ML/data selection bias 視角**：
- Freeze 是 lock current state（`status: "frozen"`，`scope: "new_entries_only"`）
- **不縮小 universe，不引入新 selection bias**
- 但**已存在的 17 grid + 4 ma blocked = 已是 selection bias source**：grid 41 active 從 ~58 universe 過濾掉 17 = 29% blocked rate
- audit helper `blocked_symbols_7d_counterfactual.py` 是 read-only，**不寫 PG row**

**Selection bias 對 ML training 影響**：
- mlde_edge_training_rows 7d demo total 268536 row from 48 unique symbols（包括 blocked symbol 的 fills 不會進 training，只有未 blocked 的 cells 進 training）
- Training 已經是「已過濾的 universe」trained → ML 模型學的是「non-blocked symbols 上 grid_trading 的 alpha」，**永遠不會嘗試 evaluate blocked symbols 是否真該 block**
- 但**這是既存 bias 不是 new bias**；c081029d 不引入新問題只是 freeze status quo

**Verdict**：⚠️ **neutral for ML pipeline**；**對 PA Layer 2 Cluster A 非新加 alpha source 不解 alpha-poverty**。governance 加 freeze 是合理 risk control 但不解結構問題。

### 1.5 da2aba11 audit: correct f08 ml cron scope ⭐ **重點**

**聲稱**：ml_training_maintenance.py 加 5 legacy F-08 ML jobs（thompson_sampling / optuna_optimizer / cpcv_validator / dl3_foundation / weekly_report_generator）+ ml_training_maintenance_cron.sh 排程 wrapper。

**實測**：
```
Source 改動：
  ml_training_maintenance.py: +511 LOC (CORE_JOBS + AUDIT_JOBS split + _weekly_audit_due gate)
  ml_training_maintenance_cron.sh: +13 LOC env binding + secret loading

Crontab 實測（ssh trade-core "crontab -l"）:
  edge_label_backfill_cron.sh: ✅ installed
  passive_wait_healthcheck_cron.sh: ✅ installed
  counterfactual_daily_cron.sh: ✅ installed
  ref21_market_microstructure: ✅ installed (every minute)
  ref21_symbol_universe_snapshot: ✅ installed (hourly)
  
  ml_training_maintenance_cron.sh: ❌ NOT INSTALLED
  outcome_backfiller_live_cron.sh: ❌ NOT INSTALLED (V074 W-AUDIT-4 P0 carry from v1)
  edge_estimate_snapshots_cycle_cron.sh: ❌ NOT INSTALLED (V073 W-AUDIT-4 P0 carry from v1)
```

**對抗性 push back**：
- ❌ Source change 補了 5 legacy script 進入 runner 但 cron 自己不會 install
- ❌ commit message 「audit: correct f08 ml cron scope」**誤導為 IMPL completion**；實為 source patch + docs 標 W-AUDIT-4 partial
- ❌ TODO.md 寫「W-AUDIT-4 partial until runtime cron installation and row evidence are verified」是真實狀態，但 commit message 不誠實
- ❌ Runner script header 寫「Suggested cron entry, installed manually by the operator」— **source 寫了不替代 install**

**真實 runtime impact**：0。Even with full source IMPL，5 legacy script 在 cron not installed 前永不 fire → model_registry 不會新 row（仍 stale 4/24，距今 15d，與 v2 16d 相同 = no train activity）。

**Verdict**：❌ **source-only IMPL；W-AUDIT-4 P0 cron 從 v1 拖到 v3 三天無動**。

---

## §2 attribution_chain_ok 24h delta 深度分析

### 2.1 v1 → v2 → v3 數據

```
v1 (5/9 03:30) 24h:  44 / 234,416   = 0.0188%
v2 (5/9 16:30) 24h:  65 /  12,894   = 0.5041%
v3 (5/9 19:00) 24h:  76 /   7,000   = 1.0857%
v3 7d:              281 / 556,793   = 0.0505%
```

### 2.2 Daily breakdown v3

```
2026-05-09:  47 /  2,948    1.5943%   ← 5/9 partial day (only 14 hours data)
2026-05-08:  43 / 266,977   0.0161%   ← 5/8 explosion peak
2026-05-07:  36 / 264,546   0.0136%   ← 5/7 explosion peak
2026-05-06:  23 /  22,036   0.1044%   ← 5/6 explosion start
2026-05-05:  39 /      86  45.3488%   ← pre-explosion baseline
2026-05-04:  47 /     129  36.4341%
2026-05-03:  35 /      57  61.4035%
2026-05-02:  42 /      67  62.6866%
```

**Hourly breakdown 6h（v3 19:00 looking back）**：
```
05-09 18:    11 row
05-09 17:    14 row
05-09 16:    13 row
05-09 15:     7 row
05-09 14:    35 row
05-09 13:     1 row
05-09 12:     1 row
```

→ Steady state ~12-14 row/hour 真實 mlde_shadow_recommendations 流速；24h 應為 ~290 base intent。view fan-out ~24x（24h 7000 row from 290 intent）。

### 2.3 真實 attribution 失敗 root cause（**v1/v2 報告均未挖到**）

```sql
SELECT signal_id IS NOT NULL as has_sid, 
       context_id IS NOT NULL as has_cid, 
       label_close_tag IS NOT NULL as has_label_close, 
       count(*) 
FROM learning.mlde_edge_training_rows 
WHERE ts > NOW() - INTERVAL '24 hours' 
GROUP BY 1,2,3 
ORDER BY 4 DESC;

  has_sid | has_cid | has_label_close | count 
  --------+---------+-----------------+-------
  t       | t       | f               |  6906   ← 98.9% 失敗在 label_close_tag NULL
  t       | t       | t               |    77   ← 1.1% pass
```

**對抗性 push back**：
- ✅ signal_id + context_id 都有（writer 接線正常，PA v1 audit 寫的「writer 寫 NULL context_id」**v3 不成立**）
- ❌ label_close_tag NULL 98.9%（exit pipeline 沒 backfill close_tag）
- ❌ 48227607 commit **沒修這條**（push promotion evidence ≠ label_close_tag backfill）
- ⚠️ FUP-2 cron `edge_label_backfill_cron.sh` 已 install 但只 backfill `label_net_edge_bps`，**不 backfill `label_close_tag`**

**結論**：
- attribution chain 0.5%-1% 不是 view definition bug，**是 label_close_tag writer 缺失**
- 修法：找出 label_close_tag 的 writer（probably exit_features writer 或 close_intent processor），驗 column 是否真寫
- v1 v2 v3 三份 audit 都未深挖此層；本 v3 第一次定位

### 2.4 PA redesign §1.4 §4.2 cross-check

PA Layer 1 §1.4「ML 學習平面 attribution_chain 0.5% = 系統不會從交易學習」結論**MIT 視角強烈 AGREE**，但 PA 把 root cause 歸於「沒 hypothesis loop」是 layer 3 解釋，**MIT layer 1 解釋更直接**：label writer 缺失 / view fan-out 雜訊 / mlde_demo_applier filter 範圍。

PA Layer 3 §3.4「Hypothesis Pipeline as First-Class Object」對 attribution 的 leverage 確實成立 — 但**只裝 hypothesis 仍不夠**，還要修底層 label writer chain。

---

## §3 PA Redesign — MIT ML 視角 cross-check

### 3.1 Layer 1 §1.1「Strategy Interface 結構性偏差」

**PA 主張**：feature_baseline writer 34-dim 仍是 OHLCV-derived；非 TA alpha source 在架構上是 second-class citizen。

**MIT 實測 cross-check**（讀 `feature_collector.rs:24-59`）：

```rust
pub const FEATURE_NAMES: [&str; 34] = [
    "sma_20", "sma_50", "ema_12", "ema_26",
    "rsi_14", "macd", "macd_signal", "macd_histogram",
    "bb_upper", "bb_middle", "bb_lower", "bb_bandwidth", "bb_percent_b",
    "atr_14", "atr_14_percent", "atr_5", "atr_5_percent",
    "stoch_k", "stoch_d", "kama", "kama_efficiency",
    "adx", "plus_di", "minus_di", "hurst",
    "regime_id", "ewma_vol", "vol_regime_id", "volume_ratio",
    "donchian_upper", "donchian_lower", "donchian_middle", "donchian_width",
    "price",
];
```

**Categorization**：
- 31 scalars: 100% OHLCV-derived TA indicators
- 2 regime enums: regime_id (trending/mean-reverting/random walk via ADX) + vol_regime_id (low/high via EWMA-vol) — **仍是 OHLCV-derived**
- 1 price scalar

**完全沒有**：
- funding_rate（雖然 TickContext.funding_rate 已在）
- basis (mark_price - index_price)
- open_interest 變化
- orderflow（microprice / queue imbalance / large-trade tape）
- cross_asset spread
- liquidation pulse

**MIT VERDICT**：✅ **PA Layer 1 §1.1 完全成立**。即使 feature_baseline_writer 解禁開始 INSERT 34-dim baseline → drift detector 學的是 textbook TA distribution → ML 學會的也只是 textbook TA 的 mean/std drift → 模型升級空間限於「對 TA 微 fine-tune」**根本性 alpha 不會增加**。

PA 的 R-1 Alpha Surface Bundle 提案（升 funding_curve / basis_curve / oi_delta_panel / orderflow / liquidation_pulse 為一等對象）對 MIT ML 視角是**唯一能解 ML 模型結構性局限的路徑**。

### 3.2 Cluster B「Learning loop dormant」相關 finding

| PA finding | v3 實測狀態 | MIT verdict |
|---|---|---|
| F-08 5 ML scripts unscheduled | da2aba11 commit 補 source 但 cron not install → 仍 unscheduled | ❌ unchanged |
| F-10 attribution_chain 0.5% | v3 1.09% (denominator artifact)；root cause label_close_tag NULL | ❌ unchanged，PA RFC 4 wrong root cause |
| F-16 feature_baselines 0 row | feature_baseline_writer Rust CLI dry-run；無 cron；0 row 仍 | ❌ unchanged |
| F-edge-cycle (V073) cron 未 install | edge_estimate_snapshots 仍 stale 5/7 00:46 | ❌ unchanged |
| F-outcome-bf (V074) cron 未 install | decision_outcomes.live latest_backfill 仍 4/20 | ❌ unchanged |
| F-29 / F-09 sibling FUP-2 | a904e273 commit 標 verified；edge_label_backfill cron 確 install；但**不 backfill label_close_tag** | ⚠️ partial |

PA Layer 2 Cluster B 的「Learning Plane Specified But Not Wired」反 anti-pattern 在 v3 仍**100% 成立**。3 day v1→v3 0 真進度。

### 3.3 Dream Engine — PA 是否提到？

PA full report grep `dream`：
- §1.5 提「Layer 2 0 流量」，沒提 dream_engine specifically
- §3.4 hypothesis pipeline 提及 ML training data quality，沒拆 dream specific
- §結語 funding_arb V2 退役 = 治理機制存在 example

**MIT push back**：PA Layer 3 §3.5 portfolio-level aggregation 沒接續 dream_engine 在 alpha source 升級藍圖中的角色。dream_engine 程式碼 (`dream.rs` + `dream_engine.py`) 仍在但 5/7 burst 後 dormant 2 day（v3 calibrated_replay 仍 5 row）。**若 R-1 Alpha Surface Bundle 落地，dream_engine 應改寫為 alpha-source incubator**（用 replay 驗 funding-skew / orderflow imbalance 等 hypothesis），而非當前的 OHLCV pattern replay。

PA RFC 漏列此延伸；建議 R-3 Hypothesis Pipeline IMPL 階段同步 dream_engine refactor。

### 3.4 attribution_chain 0.5% catastrophic vs writer 0 INSERT 路徑 — 同問題還是不同問題？

**MIT 解構**：兩個是不同問題：

**問題 1：attribution_chain_ok 0.5%-1%**
- Root cause: label_close_tag NULL 98.9%（v3 第一次定位）
- 影響：mlde_edge_training_rows 視角無法歸因 fill 結果到原 hypothesis
- 修法：補 label_close_tag writer（exit pipeline 缺接線）

**問題 2：feature_baselines 0 row, drift_events 0 row, model_registry stale 15d**
- Root cause: 4 個 cron 未 install（W-AUDIT-4 P0 carry）+ feature_baseline writer dry-run only
- 影響：drift detector pipeline broken；ML 訓練 pipeline dormant
- 修法：install 4 cron + 觸發第一次 `--apply` baseline seed

**問題 3：PA Layer 1 §1.1 alpha-source 結構性貧乏**
- Root cause: TickContext / IndicatorSnapshot 偏向 TA；feature_collector 34-dim 全 OHLCV-derived
- 影響：即使問題 1+2 全修，ML 學的仍是 textbook TA → gross negative 結構性風險不解
- 修法：PA R-1 Alpha Surface Bundle（3-4 sprint）

**三問題 layer 不同**：
- 問題 1 = data layer bug（writer wiring）
- 問題 2 = ops layer gap（cron + dry-run flag）
- 問題 3 = architecture layer constraint（interface 設計）

**修問題 1+2 是 W-AUDIT-4/-5 範圍**；**修問題 3 = PA R-1**，PA RFC AGREE。

---

## §4 Components 5×4 Grid v2 → v3 復評

| # | Component | v2 stage | v3 stage | Δ | 證據 |
|---|---|---|---|---|---|
| 1 | Strategist live | Production | Production | = | 24h fills 196 (demo 116 + live_demo 80) |
| 2 | Risk gate | Production | Production | = | risk_verdicts 不變 |
| 3 | Reconciler | Production | Production | = | unchanged |
| 4 | decision_outcomes backfiller | Canary fragile | Canary fragile | = | live latest 仍 4/20；V074 cron 未 install |
| 5 | MLDE shadow recommendations | Shadow | Shadow | = | 24h 1076 row (3 mode) |
| 6 | MLDE param applications | Canary | Canary | = | unchanged |
| 7 | Edge estimator | Production | Production | = | edge_estimates.json fresh |
| 8 | Edge estimate snapshots V059 | Foundation | Foundation | = | 仍 stale 5/7 00:46；V073 cron 未 install |
| 9 | Model registry | Canary fragile | Canary fragile | = | latest_train 4/24（15d stale）；da2aba11 source 補但 cron 未 install |
| 10 | Drift detector | Aspirational | Aspirational | = | feature_baselines 0 row, drift_events 0 row |
| 11 | Cost edge advisor | Skeleton | Skeleton | = | log 0 row |
| 12 | Decision lease audit V054 | Foundation | Foundation | = | unchanged |
| 13 | Replay simulated_fills | Shadow | Shadow | = | 5 calibrated 仍 5/7 burst |
| 14 | Counterfactual generator | Aspirational | Aspirational | = | 0 row, 0 producer |
| 15 | Calibrated replay | Foundation | Foundation | = | unchanged |
| 16 | Dream engine | Shadow | Shadow | = | unchanged |
| 17 | LinUCB shadow compare | Shadow | Shadow | = | unchanged |
| 18 | LG-5 reviewer scheduler | Canary | Canary | = | unchanged |
| 19 | lease_transitions BYPASS audit | Production | Production | = | 24h 11133 (v2 7955, +40%) — 唯一活躍進步 |
| 20 | promotion_pipeline tail risk + selection bias gate | Aspirational | Aspirational | = | dormant module；48227607 補 source 但 V079 schema 不存在 → 仍 dormant |
| 21 | layer2 context distiller | Skeleton | Skeleton | = | unchanged |
| **NEW v3** | **strategy_trial_ledger (V079)** | n/a | **Aspirational** | new | V079 schema 不存在於 PG；source-only |
| **NEW v3** | **F-08 5 legacy ML jobs** | n/a | **Aspirational** | new | da2aba11 補 source 但 cron 未 install |

**5 階段歸類 v2 → v3**：
| 階段 | v2 數量 | v3 數量 | Δ |
|---|---:|---:|---:|
| Production | 6 | 6 | = |
| Canary | 4 | 4 | = |
| Shadow | 5 | 5 | = |
| Skeleton | 4 | 4 | = |
| Foundation | 3 | 3 | = |
| Aspirational | 5 | **7** | +2（strategy_trial_ledger + F-08 jobs；皆 source-only dormant） |

**MIT 真實達標率**：v2 44% → v3 **44%**（dormant code 增加但無 runtime 真升階）

---

## §5 V### Migration Guard 檢查

| V### | Status in PG | Guard A | Guard B | Guard C | runtime impact |
|---|---|---|---|---|---|
| V068-V078 | ✅ all applied | (per v2) | (per v2) | (per v2) | per v2 |
| **V079** `promotion_evidence_trial_ledger` | ❌ **NOT APPLIED** (max version=78 in _sqlx_migrations) | ⚠️ uses ALTER ... IF NOT EXISTS（弱 Guard B；無 RAISE EXCEPTION） | ⚠️ CHECK constraint inline 但無 idempotency dry-run guard | ⚠️ no Guard C for indexes（idx_strategy_trial_ledger_*） | **0**（schema 不存在於 PG） |

**V079 source review**（讀 `sql/migrations/V079__promotion_evidence_trial_ledger.sql`）：
- ✅ ALTER TABLE IF EXISTS + ADD COLUMN IF NOT EXISTS（idempotent）
- ✅ CREATE TABLE IF NOT EXISTS（idempotent）
- ✅ CHECK constraints（engine_mode IN paper/demo/live_demo/live ✓）
- ⚠️ **缺 Guard A**：應加 `DO $$ BEGIN IF EXISTS ... AND NOT column_exists ... THEN RAISE EXCEPTION 'V079 silent-noop'`
- ⚠️ **缺 Guard B**：CHECK constraint 沒驗 column type 已存在
- ⚠️ **缺 Guard C**：index 沒驗 column order

**對抗性 push back**：V079 沿 V062/V063/V065 退化模式（v1 §6 已標）— 0 Guard 違反 CLAUDE.md §七「2026-04-24 V023 silent-noop postmortem 衍生 + 2026-05-02 V028-V034 retrofit 補完」規範。**E2 應 reject**。

---

## §6 Healthcheck 覆蓋 — 5 commits 0 新增

實測 `/home/ncyu/BybitOpenClaw/srv/helper_scripts/db/passive_wait_healthcheck/checks_*.py` grep:

| 5 commits | 應加 healthcheck | v3 實測 |
|---|---|---|
| ad14db07 bb donchian guard | check_bb_donchian_snapshot_freshness | ❌ 未加 |
| c2ab7b1a strategist wide adjust | check_strategist_param_delta_distribution | ❌ 未加 |
| 48227607 promotion evidence push | check_promotion_evidence_freshness + check_strategy_trial_ledger_writer | ❌ 未加 |
| c081029d blocked symbols freeze | check_blocked_symbols_freeze_drift | ❌ 未加 |
| da2aba11 f08 ml cron scope | check_ml_training_maintenance_cron_alive | ❌ 未加 |

**5/5 違反 CLAUDE.md §七「被動等待 TODO 必附 healthcheck」**。

---

## §7 對抗性 Push Back — v3 重點

### 7.1 「audit: correct f08 ml cron scope」commit message 仍誤導

`da2aba11` 字面暗示「audit correction completed」但實際：
- ✅ 5 legacy ML scripts 進入 ml_training_maintenance.py runner CORE_JOBS + AUDIT_JOBS split
- ❌ ml_training_maintenance_cron.sh **未 install in crontab**
- ❌ TODO.md docs 標 W-AUDIT-4 partial 是真實狀態
- ❌ commit message 不誠實 — 應為「audit: prepare f08 ml cron scope (cron install pending operator)」

### 7.2 「learning: push promotion evidence from edge cycle」是空轉 source

`48227607` 加 +1275 LOC IMPL 包含 V079 migration + edge_estimator_scheduler integration + promotion_evidence.py 558 LOC + tests，但：
- V079 schema **完全不存在於 PG**
- promotion_pipeline 仍是 dormant module（v2 §8.2 已標）
- Even if V079 apply + cron fire，PromotionPipeline class 仍無外部 caller

**這是教科書例證「在沒人走的路上加防火牆 + 加 schema」**。應同步：
1. `_sqlx_migrations` apply V079（operator 手動或 OPENCLAW_AUTO_MIGRATE=1 + restart engine）
2. wire PromotionPipeline 到 mlde_param_applications 真實路徑
3. 標明「LG-3 supervised-live 未到位前 dormant」

### 7.3 W-AUDIT-4 P0 從 v1 到 v3 三天 0 進展

| W-AUDIT-4 P0 (v1 提案) | v1 status | v2 status | v3 status |
|---|---|---|---|
| install crontab outcome_backfiller_live_cron.sh (V074) | ❌ | ❌ | ❌ |
| install crontab edge_estimate_snapshots_cycle_cron.sh (V073) | ❌ | ❌ | ❌ |
| PG ALTER SYSTEM SET work_mem='32MB' | ❌ | ❌ | ❌ |
| RCA mlde_edge_training_rows 5/6 explosion | ❌ | ❌ | ⚠️ partial（v3 第一次定位 root cause = label_close_tag NULL；source change pending） |

**3 day operator action 0 進展**。MIT 強烈建議 W-AUDIT-5 必須包含這 4 條 + new install ml_training_maintenance_cron.sh（da2aba11 補的 source）。

### 7.4 PA RFC §4.2 attribution chain root cause 描述不準

PA Layer 1 §1.4 寫「attribution_chain 0.5% = 系統不會從交易學習」結論成立但**root cause 歸於「沒 hypothesis loop」過於 abstract**。MIT v3 第一次 SQL 定位真實 root cause：

```
98.9% 失敗 = label_close_tag NULL（exit pipeline writer 缺接線）
1.1% pass = full chain (signal_id + context_id + label_close_tag) intact
```

PA RFC §3.4 Hypothesis Pipeline 的長期 leverage 對；**短期修 = 補 label_close_tag writer**（不需 R-3 sprint，可能是 1-day fix）。建議 PA RFC §4.2 加註 short-term fix path。

---

## §8 結論 + 建議

### 8.1 對抗性核實 5 已驗事項

1. ❌ **V079 migration 完全未 apply**（48227607 commit 0 PG impact）
2. ❌ **strategy_trial_ledger + promotion_pipeline 新 column 不存在**
3. ❌ **ml_training_maintenance_cron.sh 未 install in crontab**（da2aba11 cron not fire）
4. ⚠️ **attribution_chain_ok 24h 1.09%**（**denominator artifact 持續**；ok_n 65→76 only +17%）
5. ✅ **真實 attribution root cause 定位 = label_close_tag NULL 98.9%**（v1/v2 均未挖到）

### 8.2 v3 結論

**v3 schema-side 0 進展**（V079 沒 apply）；**runtime-side 0 進展**（cron 全 carry 無動）；**dormant code-side +2 module**（strategy_trial_ledger + F-08 5 legacy ML jobs）；**Architectural insight +1**（attribution root cause 真實定位 + PA Layer 1 §1.1 alpha-poverty MIT 視角強烈 AGREE）。

**ML 基座達標率**：v2 44% → v3 **44%**（0 真進步）

**PA redesign verdict**：**PARTIAL AGREE**：
- ✅ Layer 1 §1.1 (alpha-source 結構性貧乏) 完全 AGREE — feature_collector 34-dim 100% TA-derived 證明
- ✅ Layer 1 §1.4 (學習平面死) AGREE — attribution chain 失敗 + drift chain broken + model_registry stale 三線都驗
- ⚠️ Layer 1 §4.2 attribution root cause 描述不準 — 應加「label_close_tag NULL writer 缺失」短期 fix
- ❌ Layer 3 §3.5 漏列 dream_engine 在 alpha-source 升級藍圖角色
- ✅ Layer 4 R-1/R-2/R-3 路線圖 AGREE 但需加「修底層 label writer chain 是 R-3 之前 prerequisite」

### 8.3 距 Mainnet ML-driven

仍 **3-4 sprint**（樂觀 8/15 / 中位 9/15 / 悲觀 11/15，**未變**）。
若 PA R-1 R-2 R-3 加入路線圖 = +3-4 sprint architectural amendment → 樂觀延後到 **2026-Q4 末**。但若不加 = 即使 Live 也是「站在無 alpha territory 的 5 個 TA 策略」（PA 結語結論）。

### 8.4 W-AUDIT-5 / -8 提案

**W-AUDIT-5（runtime closure）**：
1. operator install crontab：outcome_backfiller_live + edge_estimate_snapshots_cycle + ml_training_maintenance（3 cron）
2. operator manual sqlx migrate run V079（or set OPENCLAW_AUTO_MIGRATE=1 + restart engine）
3. 觸發 feature_baseline_writer 一次 `--apply --i-understand-this-modifies-db`（seed 第一批 baseline）
4. 修 label_close_tag writer 缺接線 bug（exit pipeline）
5. PG ALTER SYSTEM SET work_mem='32MB' (M5 Ultra prep)

**W-AUDIT-8（architectural amendment）**：
1. R-1 Alpha Surface Bundle spec phase（PA Layer 4 提案）
2. R-2 Strategist scope reframe spec phase（PA Layer 4 提案）
3. R-3 Hypothesis Pipeline + 修 label_close_tag writer 同步

---

**MIT VERIFICATION DONE v3** — `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-09--db_ml_verification_v3.md`
