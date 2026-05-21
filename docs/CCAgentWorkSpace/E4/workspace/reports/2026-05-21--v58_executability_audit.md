# v5.8 13-Module Autonomy Expansion 執行性審核 — E4 視角
**日期**：2026-05-21
**Verdict**：GO-WITH-CONDITIONS
**One-line summary**：v5.8 把 v5.7 的 6 漏洞補丁延伸到 13 模組 + 12 V### migration + 4 state machine，但對「state-machine 完備性測試 / migration idempotency / regression baseline 漲幅 / cross-language 1e-4 容差」的執行性 SOP 仍然沉默；可派 Sprint 1A-β 但 PA 包必加 §STATE-MACHINE-TEST / §V-MIGRATION-DRY-RUN / §SLA-STRESS / §M9-FRAMEWORK-VALIDATION 四章

---

## 0. 13 module 測試規劃完整度

每 module 列：缺的測試類型 / 新增 test 估計 / SLA impact / 對 PA 必補項。

### M1 — Decision Lease Autonomous Loop（Tier 0-4 + auto-approval + 24h undo）
- **缺**：5 Tier × Transition matrix 完整性測試 / auto-approval gate 4 criteria 邊界 / 24h undo race / Console toggle default-OFF 失效保護
- **必有測試**：
  - Tier state machine：5 tier × {grant / revoke / escalate / demote / undo} = ≥ 25 transition test
  - auto-approval 4 criteria 各自邊界（≥30 approvals / 80% yes-rate / 90d incident-free / risk envelope）— 各 ≥3 邊界 = 12 test
  - 24h undo：concurrent execute + undo race，operator click 在 23h59m vs 24h01m 差 1 秒結果
  - Console toggle default-OFF + 失效保護（toggle 中斷 → fallback Advisory 不 paralysis）
  - **SLA：Tier 2 auto-execute path 必驗 IPC <5ms p99**（auto-execute 走 hot path）
- **估計**：60-80 new test
- **PA 必補**：派發前 ADR-0034 spec 必明列 5 state × 5 transition matrix；E1 寫測試對齊矩陣

### M2 — Overlay 5-State Machine（COUNTERFACTUAL→SHADOW→ADVISORY→PRODUCTION→DISABLED）
- **缺**：5 state transition matrix 完整性 / auto-disable 4 trigger 各自驗證 / auto-enable 4 criteria 邊界 / 60d 計時邊界
- **必有測試**：
  - 5 state × 6 transition direction = 13 valid + 17 invalid（invalid 走 rejected path）→ ≥ 30 test
  - auto-disable 4 trigger：Sharpe<0 / regime anomaly / FOMC FP>3 / operator inactive>60d — 各 ≥2 邊界 = 8 test
  - auto-enable 4 criteria：t-stat≥1.5 / sample≥30 / no regime shift / approval rate>80% — 各 ≥2 邊界 = 8 test
  - 60d 計時邊界（59d 不觸發 / 60d 觸發）+ 時間跨 DST / leap second
  - **always-on auto-disable 不受 operator opt-in 影響**（safety net 測試）
- **估計**：50-70 new test
- **PA 必補**：派發前 V105 schema 必含 state_transition log + opt-in 狀態欄位

### M3 — Health 5-Domain × 5-State（NORMAL→WARN→DEGRADED→CRITICAL→CATASTROPHIC）
- **缺**：5 state × 多 domain probe 整合測試 / degradation graduate 邏輯 / recovery / catastrophic kill 與既有 $3k loss kill 對接
- **必有測試**：
  - 5 domain probe unit test（WS latency / REST success / DB backlog / disk / engine memory + strategy-level）— 各 ≥5 邊界 = 25 test
  - 5 state transition matrix（4 forward + 4 backward recovery）= 8 transition × 邊界 = 16 test
  - DEGRADED → Tier 1 reparam halt 整合
  - CRITICAL → halt new orders + drain positions 整合
  - CATASTROPHIC → 對接既有 5-gate kill（不重複 trigger / 不互相 mask）
  - Recovery auto-restore：CRITICAL→DEGRADED→WARN→NORMAL 全鏈
  - **SLA：health probe 不能拖 hot path**（Tick path <0.3ms p99 with probe enabled）
- **估計**：80-100 new test
- **PA 必補**：派發前 V106 schema 必含 health_observations + degradation_state；M3 與既有 $3k kill 接線 ADR

### M4 — Pattern Miner Self-Supervised Discovery
- **缺**：**look-ahead bias 強制檢測（per feedback_indicator_lookahead_bias）**/ cross-section leakage / DRAFT vs PROMOTE 隔離 / mock data 不掩蓋 leakage bug
- **必有測試**：
  - 每個 feature engineering 必有 leak-free shift(1) 對比測試（rolling(N).max() 含 current bar → 必須 shift(1)）
  - cross-correlation: train set 不漏 test set（時序 split 嚴格）
  - event-window: 預測 window 不含 forward bar
  - regime clustering: stratified split, 不漏 future regime label
  - DRAFT 狀態不能被 bot 自己 promote（critical constraint per ADR-0024-lite）
  - **anti-mock test**：用合成 known-leakage data 跑 miner，必須 catch leakage 不能 silent pass
- **估計**：70-90 new test（其中 look-ahead bias test 是 CRITICAL，每 feature 至少 1）
- **PA 必補**：M4 spec 必含 look-ahead bias 自動化檢測 harness；E1 寫每個 feature 必並列 leak-free 對比

### M5 — ModelClient trait interface stub
- **缺**：interface contract test / unimplemented panic! 路徑驗 / streaming_enabled FALSE 預設不可繞過
- **必有測試**：
  - trait method signature contract（`get_predict_streaming()` panic 路徑驗）
  - `streaming_enabled=FALSE` 預設不可被 caller 繞過
  - serde round-trip ModelVersion record
- **估計**：10-15 new test（interface stub 範圍）
- **PA 必補**：M5 只有 interface stub IMPL 是輕的，但測試 contract 必齊；ADR-0035 retirement criteria 必明文

### M6 — Bayesian Reward Weight Optimization
- **缺**：bounds check / 30% rollback trigger / convergence / cross-language 1e-4（Rust 算 vs Python 算）
- **必有測試**：
  - λ_dd / λ_tail / λ_turnover / λ_slippage / λ_decay 5 weight × bounds × ≥3 邊界 = 15 test
  - Bayesian opt 收斂測試（GP convergence on known function）
  - 30% rollback trigger（next-month Sharpe < baseline → revert）
  - 6 mo lookback window 邊界
  - **cross-language 1e-4 一致性**：Bayesian opt 若 Rust + Python 雙端都算，相同 fixture 結果 < 1e-4 相對誤差
  - **anti-mock test**：mock 只 stub IO 不 stub 演算法（mock realized returns 但 Bayesian opt 真跑）
- **估計**：50-70 new test
- **PA 必補**：派發前必確認 Bayesian opt 是 Rust 或 Python 算（單端則跳過 1e-4）；30% rollback 觸發鍵值閾值寫進 ADR

### M7 — Decay 5-State Machine（LIVE→DECAY_DETECTED→DEMOTE_PROPOSED→DEMOTED→RECOVER|RETIRE）
- **缺**：state transition / 14d review window 邊界 / 4 decay signal trigger / RECOVER vs RETIRE 判定 / 與 M1 Tier 1 接線
- **必有測試**：
  - 5 state × transition matrix = 6 valid + invalid path = ≥ 20 test
  - 4 decay signal：Sharpe<threshold / DD>envelope / 連虧 N>2σ / counterfactual underperform — 各 ≥3 邊界 = 12 test
  - 14d review window：13d 不觸發 / 14d 觸發 / 15d 不重複觸發
  - RECOVER vs RETIRE judgment（Sharpe recover 走 RECOVER / 持續惡化走 RETIRE）
  - DEMOTED → 50% size scaled 邏輯（與既有 risk_config 整合）
  - M1 Tier 1 auto-demote 接線整合測試
- **估計**：60-80 new test
- **PA 必補**：M7 與 M1 Tier 1 接線 ADR 明寫；E1 寫測試對齊 5 state matrix

### M8 — Anomaly Detection（z-score + ARIMA + isolation forest + autoencoder Y2）
- **缺**：3 method unit test / Y1 read-only logging vs Y2 active trigger 分離 / severity routing / M3 active trigger 整合
- **必有測試**：
  - rolling z-score: 已知 distribution（normal 5σ vs t-distribution heavy tail）驗 FPR
  - ARIMA residual: walk-forward 殘差統計
  - isolation forest: known outlier ratio 驗 recall
  - severity 分級邊界（LOW / MEDIUM / HIGH / CRITICAL）
  - Y1 read-only：anomaly_events INSERT 但不觸發任何 action（fail-closed silent log）
  - Y2 active：HIGH severity → M3 HEALTH_DEGRADED 整合
  - autoencoder Y2 IMPL 先 stub（reconstruction error 計算 contract test）
- **估計**：70-90 new test
- **PA 必補**：M8 schema (V109) 必含 severity enum + action enum 兩列獨立（Y1 silent / Y2 trigger 切換不改 schema）

### M9 — A/B Testing Framework with mSPRT
- **缺**：**mSPRT 演算法正確性（用 known distribution 驗證）**/ early stopping power 與 FDR / Bonferroni vs FDR 切換 / preregistration 與 M4 重用 / 50/25/25 size 上限
- **必有測試**：
  - **mSPRT 演算法驗證**：用 known distribution（normal μ₁=0.5 vs μ₂=0.7 σ=1）模擬 1000 次 → 計算實證 Type I error rate ≤ α / Power ≥ 1-β
  - early stopping for futility（H₀ accept boundary 觸發）邊界 ≥5
  - early stopping for efficacy（H₁ accept boundary 觸發）邊界 ≥5
  - Bonferroni vs FDR 多重比較校正切換邊界 / 邏輯
  - assignment：trial_id hash 確定性 + stratified by symbol/regime/time 不偏
  - preregistration 與 M4 hypothesis schema reuse 整合
  - **50/25/25 size 上限不被繞過**（防止 A/B test 失控 wipe main）
  - **anti-mock test**：mock 只 stub fills 不 stub mSPRT 演算法
- **估計**：80-110 new test（mSPRT validation 必 ≥30 test）
- **PA 必補**：M9 演算法測試框架最重要，PA 包必明列「known distribution simulation 驗證 ≥1000 次」

### M10 — Capital-Tier Discovery Pipeline
- **缺**：AUM 7-day moving avg 計算 / 30d sustained threshold / Tier A-E activation trigger / 90d de-activation 邏輯
- **必有測試**：
  - 7-day moving AUM 計算（含 daily snapshot 缺失情境）
  - 30d sustained > threshold（29d 不觸發 / 30d 觸發 / 31d 不重複）
  - 5 Tier (A-E) × activation threshold (10k/15k/25k/50k/75k/150k) = ≥ 18 boundary test
  - 90d de-activation：drop sustained 89d 不退階 / 90d 退階 / 91d 不重複
  - Operator Console 確認觸發
  - Tier 之間相依性（Tier C 不能跳過 Tier B 活化）
- **估計**：40-60 new test
- **PA 必補**：Tier 之間相依矩陣明寫進 V111 schema

### M11 — Nightly Counterfactual Replay
- **缺**：divergence threshold 邊界 / replay engine 與 production 1e-4 容差 / nightly job 不撞 daily ML retrain / M3+M7+M8 整合
- **必有測試**：
  - replay PnL vs production PnL divergence: $0.001 / $1 / $10 / $100 邊界
  - decision count divergence: 0 / 1 / 10 / 100 邊界
  - slippage divergence: 0 / 1 / 5 / 10 bps 邊界
  - **replay engine vs production cross-language 1e-4**：相同 24h tick replay，Python production fills vs Rust replay engine fills 浮點差 < 1e-4 相對誤差
  - nightly job 排程不撞 daily ML retrain cron（per memory project_2026_05_09_ml_training_cron）
  - High-divergence → M3 HEALTH_WARN 整合
  - replay 為 M7 decay signal 之一整合
  - replay 為 M8 own-behavior anomaly input 整合
  - **SLA：nightly replay 不耗光 daily resource budget**（24h tick replay 在 < 4h 內完成）
- **估計**：60-80 new test
- **PA 必補**：M11 ADR-0038 必明列 cross-language 1e-4 容差驗證 SOP

### M12 — OrderRouter trait interface stub
- **缺**：interface contract / venue/order-type/slicing enum 完整 / bounds check（$500 max single order 不可繞過）
- **必有測試**：
  - OrderRouter trait method signature contract
  - Venue enum exhaustiveness（BybitPerp / BybitSpot / BybitOption / BinancePerp - 5+ variants）
  - OrderType enum exhaustiveness（Market / Limit / PostOnly / Conditional / FOK / IOC）
  - Slicing enum（Single / TWAP / VWAP / Iceberg / Dark）
  - max single order $500 bounds 強制驗證
- **估計**：20-30 new test（interface stub 範圍）
- **PA 必補**：Sprint 1A-δ 只 stub trait + ADR-0039 retirement criteria

### M13 — AssetClass + Venue enum
- **缺**：enum exhaustiveness（matches!() 完整覆蓋）/ DEX/Hyperliquid 不可被加入 enum（D1a hard constraint）
- **必有測試**：
  - AssetClass enum：Perp / Spot / Option / Earn / Structured 完整 match arm（rustc warning 0）
  - Venue enum：BybitPerp / BybitSpot / BybitOption / BinancePerp 等完整
  - **D1a 強制保護**：嘗試 Venue::DexHyperliquid 等 enum variant 必須 compile error
  - serde round-trip
- **估計**：15-25 new test
- **PA 必補**：D1a 保護用 enum 嚴格類型保證；ADR-0040 retirement criteria

---

## 0.5 V105-V116 migration test coverage

每個 V### 必須：(a) Guard A/B/C 對應 / (b) idempotent 雙跑 / (c) Linux PG empirical dry-run（per feedback_v_migration_pg_dry_run + V055 5-round loop 教訓）

| V### | Module | DDL 類型 | Guard | idempotent 雙跑 | Linux PG dry-run | 風險 |
|---|---|---|---|---|---|---|
| V103 (extend) | M4 | ADD COLUMN to hypotheses | B | 必驗 | 必驗 | 既有 v5.7 schema 延伸，type-sensitive |
| V104 (extend) | M4 | ADD COLUMN to preregistration | B | 必驗 | 必驗 | 同上 |
| V105 | M2 | CREATE overlay_state_transitions hypertable | A + C | 必驗 | 必驗 | hypertable + state machine 不可重複 INSERT |
| V106 | M3 | CREATE health_observations + degradation_state | A | 必驗 | 必驗 | hot-path 寫入 |
| V107 | M11 | CREATE replay_divergence_log | A + C | 必驗 | 必驗 | nightly job 寫入 |
| V108 | M9 | CREATE ab_tests + ab_assignments + ab_results | A | 必驗 | 必驗 | preregistration unique constraint 衝突風險 |
| V109 | M8 | CREATE anomaly_events + severity | A + C | 必驗 | 必驗 | severity enum PG type |
| V110 | M6 | CREATE reward_weight_history + bayesian_opt_runs | A | 必驗 | 必驗 | numeric precision check |
| V111 | M10 | CREATE discovery_tier_config + capital_triggers | A | 必驗 | 必驗 | tier 相依矩陣 constraint |
| V112 | M1 | CREATE decision_lease_tiers + tier_eligibility_log | A + C | 必驗 | 必驗 | hot-path lease check 寫入 |
| V113 | M7 | CREATE decay_signals + strategy_lifecycle | A | 必驗 | 必驗 | strategy lifecycle state PG enum |
| V114 | M5 | Reserved (no DDL Y1) | n/a | n/a | n/a | 編號預留不執行 |
| V115 | M6 (Sprint 6) | Reserved | n/a | n/a | n/a | 編號預留不執行 |
| V116 | M13 | Reserved (no DDL Y1) | n/a | n/a | n/a | 編號預留不執行 |

**CRITICAL gap**：v5.8 §9 只列 V### 編號 + 用途，**0 處明列每個 V### 的 Guard A/B/C 對應 + idempotent 雙跑 SOP + Linux PG dry-run 證據**。這正是 V055 5-round loop / a19797d sqlx hash drift incident 的教訓盲點重演。

**PA 必補**：派發前每個 V### 必有 dispatch packet 子任務含 `Linux trade-core 連 psql empirical dry-run + reflection function output + 雙跑 idempotent verification + Guard A/B/C 對應位置標出 + rollback path`。沒這證據的 V### PR 進來 E4 必退 E1。

---

## 0.6 regression baseline + new test count

**當前 baseline（最新 E4 報告為準）**：
- Python pytest（srv root）：歷史 ~2555 passed / 17 failed
- Rust engine lib：~3077 PASS / 0 fail（最近 W1 baseline，2026-05-10 Sprint N+0）
- **任何 v5.8 commit 不可降 passed / 不可增 failed**

**v5.8 13 module 新增 test 估計**：

| Module | new test 估計 |
|---|---|
| M1 | 60-80 |
| M2 | 50-70 |
| M3 | 80-100 |
| M4 | 70-90 |
| M5 | 10-15 |
| M6 | 50-70 |
| M7 | 60-80 |
| M8 | 70-90 |
| M9 | 80-110 |
| M10 | 40-60 |
| M11 | 60-80 |
| M12 | 20-30 |
| M13 | 15-25 |
| **Total** | **665-900 new test** |

加上 V### migration test（每 V### ~10 test × 10 V### + ~5 reserved-stub × 3 = ~115）→ **總 new test 780-1,015**。

**regression baseline 新目標（v5.8 IMPL 完成後）**：
- Python pytest：2555 → ≥ 2555 + 400-500（Python 端 M4/M6/M8/M9/M10 大部分）
- Rust engine lib：3077 → ≥ 3077 + 380-515（Rust 端 M1/M2/M3/M7/M11/M12/M13 + state machine）

**PA 必補**：v5.8 §4 工時表（2,780-3,930 hr）的 **測試工時被無形吞下**。780-1,015 new test × 平均 0.5h/test = 390-507 hr 純測試工時。應從工時表獨立列出，不混在 module IMPL 工時內。

---

## 1. Top 3 執行性風險（排序）

### Risk 1：4 state machine 完整性測試（M1/M2/M3/M7）共 50+ transition × 邊界 易漏邊
- **嚴重度**：CRITICAL
- **位置**：v5.7 §2 M1 + M2 + M3 + M7
- **描述**：v5.8 加 4 個 state machine（M1 Lease Tier 5 state / M2 Overlay 5 state / M3 Health 5 state / M7 Decay 5 state），合計 ≥ 50 transition × ≥ 3 邊界 = 150+ test。state machine bug 經典屬於「設計 review 看不出但 runtime explode」類；OpenClaw 既有教訓：first-detection deadlock (FIX-26-DEADLOCK-1) `is_none()` guard + 無過期 auto-clear → symbol 永久 dormant。4 個新 state machine 重覆相同 bug pattern 風險高。
- **為何屬「執行性」（非邏輯）**：state machine 設計 reviewer 已驗；缺的是 transition matrix 窮舉測試（per regression-testing-protocol §4.3 property-based test 用 proptest 窮舉狀態轉換）。
- **Must-fix 建議**：PA 包加 §STATE-MACHINE-TEST：
  1. 每 state machine 必有 proptest macro 窮舉所有 state × event 組合
  2. 每 transition 必有 invalid → rejected path 驗證
  3. dead-state 檢測（無 transition out 的 state 必須警告）
  4. 「is_none() guard 無 auto-clear → dormant」反模式自動 scan
  5. 4 state machine 各分配 ≥ 2h Round-trip review by 不同 sub-agent

### Risk 2：13 V### migration（V103-V113 active）+ 3 reserved，沒明列 dry-run + idempotent SOP
- **嚴重度**：CRITICAL
- **位置**：v5.7 §9 schema migration roster
- **描述**：v5.7 §9 列了 12 個 V### 但 0 處明列：(a) 每個必跑 Linux PG empirical dry-run；(b) Guard A（CREATE TABLE IF NOT EXISTS）/ Guard B（type-sensitive ADD COLUMN）/ Guard C（hot-path index）對應；(c) idempotent 雙跑；(d) rollback path。**這正是 V055 5-round loop + 2026-05-02 sqlx hash drift incident（a19797d）的教訓盲點重演**。
- **為何屬「執行性」（非邏輯）**：schema 設計 reviewer 過；缺的是 V### migration 落地的 PG runtime 行為驗證 SOP。
- **Must-fix 建議**：PA 包加 §V-MIGRATION-DRY-RUN：
  1. 每 V### 必有 dispatch sub-task with Linux trade-core psql empirical dry-run
  2. reflection function output 附 dispatch report
  3. 雙跑 idempotent verification
  4. Guard A/B/C 對應位置標出
  5. rollback path 明文
  6. **engine restart 實測**（不只 cargo test PASS；per 2026-05-02 incident 教訓 = audit closure SOP 漏 engine restart 實測）

### Risk 3：M9 mSPRT 演算法正確性 + M4 look-ahead bias 自動化檢測
- **嚴重度**：HIGH
- **位置**：v5.7 §2 M4 + M9
- **描述**：M9 mSPRT（modified Sequential Probability Ratio Test）+ multiple comparison correction（Bonferroni / FDR）是 OpenClaw 0 處既有實裝的演算法。「mSPRT 演算法寫對了 vs 寫錯但 silent 過 unit test」差異需要 known distribution simulation 驗證。M4 pattern miner 是 OpenClaw 既有 feedback_indicator_lookahead_bias 教訓（rolling(N).max() 含 current bar 必 leak）的新風險表面；每 feature engineering 必並列 leak-free shift(1) 對比，但 v5.7 §2 M4 0 處提及。
- **為何屬「執行性」（非邏輯）**：演算法 spec 沒問題；缺的是演算法正確性的實證驗證 + 反模式自動掃描。
- **Must-fix 建議**：PA 包加 §M9-FRAMEWORK-VALIDATION + §M4-LEAKAGE-SCAN：
  1. M9：known distribution simulation 1000+ 次（normal μ₁=0.5 vs μ₂=0.7）驗證 Type I error rate ≤ α 與 Power ≥ 1-β
  2. M9：early stopping boundary 邊界 ≥ 10 test
  3. M9：Bonferroni vs FDR 切換邊界邏輯
  4. M4：每 feature engineering function 必有 leak-free shift(1) baseline 對比
  5. M4：anti-mock test：用合成 known-leakage data 跑 miner 必須 catch

---

## 2. SLA 壓測 v5.8 13 module 對 hot path 影響

| Module | hot path 影響 | SLA 壓測 must |
|---|---|---|
| M1 Tier 2 auto-execute | IPC + Rust engine hot path | IPC <5ms p99 必驗（auto-execute path） |
| M2 Overlay state transition | overlay enable/disable 走 hot path | state transition <1ms p99 |
| M3 health probe | **5 domain probe 並行打 hot path** | Tick path <0.3ms p99 with all probes enabled；probe 自身 <0.5ms p99 |
| M4 pattern miner | offline（daily / weekly） | no hot path impact |
| M5 ModelClient stub | offline | no hot path impact |
| M6 Bayesian opt | offline（monthly） | no hot path impact |
| M7 decay detect | offline + lifecycle state read in hot path | lifecycle read <0.1ms p99 |
| M8 anomaly | Y1 offline / Y2 active trigger 入 M3 | Y1 0 impact / Y2 同 M3 |
| M9 A/B framework | assignment 入 hot path | assignment lookup <0.1ms p99 |
| M10 capital tier | offline | no hot path impact |
| M11 nightly replay | offline | **24h tick replay <4h budget** |
| M12 OrderRouter | hot path | venue+order-type+slicing decision <1ms p99 |
| M13 AssetClass enum | hot path | enum dispatch <0.01ms p99（match arm 必 inline） |

**CRITICAL SLA**：
- **H0 Gate <1ms 不可破**：M1 Tier 2 + M12 OrderRouter 都在 hot path，新增邏輯不可累加破 1ms
- **Tick path <0.3ms 不可破**：M3 5 domain probe 並行最大威脅；probe 必異步打 IPC 不可同步阻 hot path
- **IPC roundtrip <5ms 不可破**：M1 auto-execute + M9 assignment + M11 replay job all 共用 IPC

**PA 必補**：派發前每個入 hot path 的 module 必有 cargo bench harness：`cargo bench --bench hot_path_baseline` p50 / p95 / p99 / max。Sprint 1A-β 結束前 ≥ 5 module 上線壓測。

---

## 3. cross-language 1e-4 容差 v5.8

| Module | Rust 端 | Python 端 | 1e-4 容差驗證 |
|---|---|---|---|
| M1 Lease Tier | Rust（authoritative） | Python read-only | 不適用（無 float math） |
| M2 Overlay state | Rust state machine | Python read | 不適用 |
| M3 health probe | Rust probe + Python collector | both | **必驗（latency 統計 percentile 雙端）** |
| M4 pattern miner | Python 主（pandas / scipy） | n/a | 不適用（Python only） |
| M5 ModelClient | Rust trait | Python caller | 不適用（stub only） |
| M6 Bayesian opt | **若 Rust 算 vs Python 算雙端皆有** | both possible | **必驗（GP convergence 雙端結果）** |
| M7 decay signal | Rust signal generator | Python read | Sharpe 計算 Python vs Rust 1e-4 |
| M8 anomaly | Rust z-score + Python ARIMA + Python iForest | mixed | **z-score Python vs Rust 1e-4** |
| M9 A/B framework | Python mSPRT 主 | n/a | 不適用 |
| M10 capital tier | Python | n/a | AUM moving avg 計算 Python only |
| M11 nightly replay | **Rust replay engine vs Python production fills** | both | **CRITICAL：replay 結果 vs production fills 1e-4 相對誤差** |
| M12 OrderRouter | Rust 主 | Python config | 不適用 |
| M13 AssetClass | Rust enum | Python view | 不適用 |

**CRITICAL 1e-4**：
- **M11 replay vs production fills**：核心驗證，相同 24h tick 輸入，Rust replay engine 與 Python production 浮點 PnL / fills 差 < 1e-4 相對誤差。否則「replay vs production divergence」永遠是噪音
- **M3 latency percentile**：Rust probe 算 percentile vs Python collector 算 percentile 必 1e-4 一致（否則 anomaly trigger 不可靠）
- **M6 Bayesian opt**：若有 Rust + Python 雙端，相同 fixture 結果差 < 1e-4
- **M8 z-score**：Rust 算 vs Python 算 1e-4（同 fixture data）

**PA 必補**：每個 module 派發前必明列「是 Rust 主 / Python 主 / 雙端」；雙端則必有 cross-language fixture 對齊測試 + 1e-4 容差驗證 harness。

---

## 4. 對 PA+PM 匯總必收 top 3

1. **§STATE-MACHINE-TEST 強制章節**（M1+M2+M3+M7 4 state machine 各 ≥ 25 transition test + proptest 窮舉 + dead-state scan + is_none() reset auto-clear 反模式 scan）
2. **§V-MIGRATION-DRY-RUN 強制章節**（10 個 active V### 各自 Linux PG empirical dry-run + Guard A/B/C 對應 + idempotent 雙跑 + rollback path + engine restart 實測，per V055 + a19797d 教訓）
3. **§M9-FRAMEWORK-VALIDATION + §M4-LEAKAGE-SCAN**（M9 mSPRT 演算法 known distribution 1000+ simulation 驗 Type I + Power；M4 每 feature engineering function 必並列 leak-free shift(1) 對比 + anti-mock leakage scan）

---

## 5. v5.8 派發前 must-fix

1. **§STATE-MACHINE-TEST 寫入 PA dispatch packet** — M1/M2/M3/M7 4 state machine 各列：5 state × N transition matrix + proptest 窮舉 SOP + invalid path → rejected verification + dead-state scan
2. **§V-MIGRATION-DRY-RUN** — 10 個 active V### 各列 Linux trade-core psql empirical dry-run + reflection output + Guard A/B/C 對應 + 雙跑 idempotent + rollback + engine restart 實測（per a19797d 教訓 audit closure SOP 漏 engine restart 是治理盲點）
3. **§SLA-STRESS** — 5+ hot path module（M1/M3/M9/M11/M12）各列 cargo bench harness + p50/p95/p99 必收 + IPC <5ms / Tick <0.3ms / H0 <1ms 不破鎖點
4. **§M9-FRAMEWORK-VALIDATION + §M4-LEAKAGE-SCAN** — M9 mSPRT known distribution 1000+ simulation；M4 每 feature 並列 leak-free shift(1) 對比 + anti-mock leakage scan
5. **regression baseline 鎖點** — Sprint 1A-β/γ/δ/ε 任何 PR 進 main 前 E4 必跑：pytest tail -5 + cargo test --lib tail -5 + cargo test --workspace tail -5（per memory: W1 baseline `--lib` only 漏抓 integration cross-wave 副作用教訓）
6. **§測試工時獨立列出** — 780-1,015 new test × 平均 0.5h/test = 390-507 hr 純測試工時應從 v5.8 §4 工時表獨立列出，不混在 module IMPL 工時內（避免測試工時被無形吞）
7. **cross-language 1e-4 fixture harness 一次建多次用** — M11 replay vs production / M3 latency / M6 Bayesian / M8 z-score 共用同一 fixture 框架（per v5.7 audit Risk 1 同建議延伸到 v5.8）

## 6. Sprint 1A-β～ε 期間 should-fix

1. **proptest macro 寫一次 4 state machine 通用** — 每 state machine 寫 proptest 窮舉 N=10000 transition；Sprint 1A-β 立 4 套 harness
2. **每 V### dry-run 證據附 dispatch report** — PA / E1 / E4 三方 sign-off chain 都看得到 Linux psql 輸出
3. **Stage gate 自動化 harness（per v5.7 audit Risk 3 延伸）** — M11 nightly replay 必須過 Stage 0R harness；Sprint 3-7 各 Top-N build 都複用
4. **fixture 隔離 SOP** — 13 module × Sprint 1A-β/γ/δ/ε 並派多 sub-agent，每 module 專屬 fixture 路徑（tests/m{1-13}/）避免 flaky；regression-testing-protocol skill 「跑兩遍」必跑
5. **M3 health probe 異步 SOP** — 5 domain probe 必異步打 IPC 不可同步阻 hot path；E1 寫測試前確認 probe 邏輯不入 sync hot path
6. **M11 replay engine vs production fills 對齊測試** — 必選同一 24h 歷史 tick fixture，雙端跑出 PnL / fills 列表，1e-4 容差比對
7. **M9 mSPRT 演算法 reference implementation** — 找 scipy / statsmodels reference 對照（避免「演算法寫對 vs 寫錯 silent pass unit test」）
8. **autoencoder Y2 stub 預先寫 contract test** — 即使 IMPL Y2，stub 寫 reconstruction error contract（input/output shape + reproducibility）避免 Y2 retrofit

---

## 結論

v5.8 在 v5.7 「6 漏洞 reviewer 補丁」之上加 13 module + 12 V### + 4 state machine，**設計層 PA reviewer 16 round 收斂達成**，但：

1. **state machine 完備性測試**（M1+M2+M3+M7 4 個 × ≥ 25 transition）= 既有 OpenClaw first-detection deadlock 反模式 重演風險
2. **V### migration dry-run + idempotent + engine restart 實測**（10 個 active V### × Guard A/B/C × 雙跑）= V055 + a19797d 教訓盲點重演風險
3. **M9 mSPRT 演算法正確性 + M4 look-ahead bias 自動化掃**（新演算法 + 既有 feedback 反模式）= 演算法 silent fail 風險
4. **780-1,015 new test 工時 390-507 hr 被無形吞** = 工時 estimate 執行性 gap
5. **5+ hot path module SLA 壓測無證據** = v5.7 risk 延伸到 v5.8 規模放大

執行性 gap 都是 PA dispatch packet 補章節就能解，不需要動 v5.8 thesis。

**Verdict GO-WITH-CONDITIONS**：v5.8 設計可派 Sprint 1A-β，**但 PA dispatch packet 必加 4 章節**：
- §STATE-MACHINE-TEST
- §V-MIGRATION-DRY-RUN
- §SLA-STRESS
- §M9-FRAMEWORK-VALIDATION + §M4-LEAKAGE-SCAN

且測試工時 390-507 hr 從 module IMPL 工時表獨立列出。預期 v5.8 Y1 工時 2,780-3,930 hr 修正為 3,170-4,440 hr（含獨立測試工時）。

**E4 REGRESSION DONE: PASS (audit-only, no code changes; baseline 不被本次審計觸碰)**
