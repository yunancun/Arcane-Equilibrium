# v5.8 13-Module Autonomy Expansion 執行性審核 — E5 視角

**日期**：2026-05-21
**Verdict**：**GO-WITH-CONDITIONS**
**One-line summary**：v5.8 邏輯 + 12 月 phasing 合理，但 Sprint 1A 7 週 calendar 仍是 5-10x 規律下的**樂觀下限**，PG schema sprawl V105-V116 12 張新表對 4-8GB buffer 衝擊未量化評估，hot path SLA 對 M1 Tier 2 / M8 anomaly / M3 health probe 三個 module 必加 budget gate 才能避免 Sprint 5-7 expensive rework。

---

## 0. v5.7 60-80 hr 真實 → 12 prefix DONE calibration anchor

**Calibration source**：v5.7 60-80 hr Sprint 1A baseline 上修為 **75-105 hr**（PM 仲裁 2，2026-05-21 PM sign-off）。

**§0.5 12 條 CRITICAL prefix 實際 ship**：
- Calendar：1 天（2026-05-20 v5.7 dispatch-safe land → 2026-05-21 12 prefix DONE + PM sign-off）
- Sub-agent 並行：7 並行 + PM hands-on
- Artifacts：4 ADR (926 行) + V103/V104 spec (940 行) + Earn governance spec (460 行) + 3 BB verdict report + 2 PA verify report + 1 PM sign-off (155 行) ≈ **~3,000 行 governance/spec artifacts**

**E5 估算實際 actor-hours**：
- 假設 1 sub-agent = 4-8 hr productive work （7 sub-agent × 4-8 hr = 28-56 hr）
- 加 PM hands-on coordination ~5-10 hr
- **Total ≈ 33-66 hr actor-hours** for 12 prefix
- 對應 v5.7 60-80 hr Sprint 1A estimate **的 50-80%**（因 12 prefix 不含全部 Sprint 1A scope；只含 ADR/spec/V### dry-run 部分，sensor/Earn recorder/V099-V102 migration 尚未實作）

**5-10x 規律核驗**：
- v5.7 60-80 hr **plan** vs 33-66 hr **actual** for 12 prefix = **0.55-1.10x** （在 plan 範圍內）
- BUT 12 prefix scope ≈ Sprint 1A 50-60%（ADR + spec + dry-run 為主，sensor IMPL 沒做）
- Extrapolated full Sprint 1A：33-66 / 0.5 = **66-132 hr actor-hours** → 對應 v5.7 plan 75-105 hr 上限附近
- **結論**：5-10x 規律 **不適用 ADR/spec/dry-run-only 任務** （這類任務 plan 接近真實）；但 **適用 sensor IMPL/migration deploy/E2E** 任務（5-10x 仍會生效）

**對 v5.8 §3 Sprint 1A-α-ε 543-797 hr 推論**：
- 純 DESIGN/schema/ADR 部分（α + β + γ + δ ≈ 468-692 hr）：5-10x 規律 **基本不適用**，plan 接近實際（calibration 0.8-1.2x）
- ε 階段（integration verify + cross-ADR consistency audit）40-60 hr：calibration 0.8-1.2x
- **v5.8 Sprint 1A-α-ε 真實估算 ≈ 480-820 hr** （vs plan 543-797 hr；下限略低，上限略高）
- **7 週 calendar 在 50-60% parallel 條件下可達**

---

## 0.5 v5.8 Sprint 1A 543-797 hr 工時 sanity（5-10x 規律 calibration）

**Plan**：543-797 hr / 7 週 / Sprint 1A-α-β-γ-δ-ε 五階段

**E5 sanity 重估**：
- α (Week 0-1)：v5.7 baseline 75-105 hr，calibration 0.8-1.0x → **75-105 hr 真實**
- β (Week 1-3)：5 CRITICAL module DESIGN 220-320 hr，schema+ADR 主，calibration 0.9-1.1x → **200-350 hr 真實**
- γ (Week 3-5)：5 ADD-per-operator module DESIGN 190-290 hr，含 M4 hypothesis miner schema（複雜度高），calibration 1.0-1.3x → **190-380 hr 真實**
- δ (Week 5-6)：3 interface stubs M5/M12/M13 58-82 hr，trait + ADR，calibration 0.8-1.0x → **50-82 hr 真實**
- ε (Week 6-7)：integration verify + cross-ADR audit 40-60 hr，calibration 1.2-1.5x → **50-90 hr 真實**（cross-ADR 衝突檢查實務 1.3x 為正常）

**E5 Sprint 1A 真實估算總計**：**565-1,007 hr**（vs plan 543-797 hr；上限延伸 +27%）

**Parallel sub-agent factor**：
- α 50-60% parallel mandate 已固化（PM 2026-05-21 仲裁）
- β-δ schema/ADR DESIGN 互相獨立 → **70-80% parallel 可行**（5-7 sub-agent 同時）
- ε 必須 single-thread （cross-ADR consistency）

**Realistic Sprint 1A wall-clock**：
- 565-1,007 hr / 70% parallel ≈ 170-300 wall-clock-hr
- 170-300 hr / 30-40 hr/週（含 review/sign-off overhead）= **5-9 週**
- **Plan 7 週在 70% parallel 下 mid-range（66%）達標**；上限 9 週若 cross-ADR collision 嚴重會 slip 2 週

---

## 0.6 v5.8 Y1 total 2,780-3,930 hr 工時 sanity

**Plan**：2,780-3,930 hr / 37-44 週 / Sprint 1A-10

**E5 sanity 重估**（按 v5.7 audit calibration 套用）：
- DESIGN-only 部分（Sprint 1A 565-1,007 hr / Sprint 2 schema work / ADR 1A-δ）：~700-1,100 hr，calibration ~1.0x
- IMPL 部分（Sprint 2-10 含 M1 Tier 1+2 / M3 auto-degradation / M4 pattern miner 80-120 hr / M11 nightly replay / M6 reward weight / M12 maker-vs-taker）：~1,500-2,200 hr，**calibration 1.5-2.5x**（5-10x 規律 partial 適用，因含 trial/E2E）
- Integration / sign-off / regression：~580-630 hr，calibration 1.2-1.5x

**E5 Y1 真實估算總計**：**3,500-5,600 hr**（vs plan 2,780-3,930 hr；下限 +26%，上限 +43%）

**Parallel sub-agent factor**：
- Sprint 1A-1B 70-80% parallel
- Sprint 2-7 IMPL 階段：parallel 降至 40-50%（依賴鏈強，5 strategy build + 4 sensor + Allocator + M3 + M11）
- Sprint 8-10：50-60% parallel

**Realistic Y1 wall-clock**：
- 3,500-5,600 hr / 50% parallel ≈ 1,750-2,800 wall-clock-hr
- 1,750-2,800 hr / 40 hr/週 = **44-70 週**
- **Plan 37-44 週在 50% parallel 下達 mid-range（44 週）的下限**；上限延伸 26 週至 70 週（Y2 Q1）
- **vs reviewer 預估 2,000-7,800 hr**：v5.8 plan 2,780-3,930 hr 落在 reviewer range lower-mid；**E5 重估 3,500-5,600 hr 落在 reviewer range mid（中位接近 4,900 hr）**

**結論**：v5.8 Y1 plan 2,780-3,930 hr **系統性偏低約 26-43%**，但 phased 結構 (DESIGN early / IMPL phased) 比 v5.7 更現實。**44 週 calendar 在 50% parallel 強制下不可達**，需 **55-65 週**（Y2 Q1 mid）。

---

## 1. Top 3 執行性風險

### Risk 1：PG 4-8GB buffer 對 V105-V116 + extension 12 張新表衝擊未量化評估

**嚴重度**：CRITICAL（性能/容量風險）
**位置**：v5.8 §9 Schema Migration Roster（V105-V116 + V103/V104 extension）

**Detail**：
- v5.7 已 reserved V099-V104 6 張表，v5.8 增 V105-V116 **12 張新表**，總 18 張新表
- CLAUDE.md `project_hardware_constraints`：PG shared_buffers + work_mem 4-8GB 上限
- 各表 cadence + cardinality 預估（per v5.8 §2 + §9）：
  - V105 overlay_state_transitions：低頻（state 變動），24mo ~1,000 行，~1 MB
  - V106 health_observations：**高頻**（per-domain probe，1-5 min cron），24mo ~10M 行，~5-10 GB ⚠️
  - V107 replay_divergence_log：**daily**，24mo ~700 行，~10 MB
  - V108 ab_tests/assignments/results：**per-fill**（fill volume × 2 variant），24mo ~50k-200k 行，~50-200 MB
  - V109 anomaly_events：**event-driven**，24mo ~5k-20k 行，~10-50 MB
  - V110 reward_weight_history：monthly，24mo ~24 行 + bayesian_opt_runs ~500 行，~5 MB
  - V111 discovery_tier_config + capital_triggers：低頻，~100 行，~1 MB
  - V112 decision_lease_tiers + tier_eligibility_log：per-Tier-decision，24mo ~10k-50k 行，~50-200 MB
  - V113 decay_signals + strategy_lifecycle：daily per-strategy × 5 = 1,825 × 24mo ≈ 44k 行，~50 MB
  - V114-V116：interface-stub schemas（Sprint 1A reserved；無 row Y1）

**6mo PG growth 預測**：
- High-frequency table（V106 health_observations）6mo ~1.25-2.5 GB（**單表佔 4-8GB buffer 的 16-63%**）
- Mid-frequency（V107/V108/V109/V112/V113）6mo 合計 ~80-200 MB
- 既有 hot tables（trading.fills hypertable / market.kline / market.liquidations 等）已用 ~32 GB（per 2026-05-08 E5 audit）
- **6mo PG total growth 預測：+2.5-4 GB**；24mo +10-16 GB

**Critical concern**：
- V106 health_observations 高頻 cadence 在 Sprint 1B-3 IMPL 必走 **TimescaleDB hypertable + 30d chunk drop + compression policy**
- shared_buffers 4-8GB 對 18 張新表 + 既有 30+ 表的 index 命中率衝擊未做 baseline → Sprint 5+ 可能撞 swap

**Must-fix**：
1. Sprint 1A-β/γ V106 / V108 / V109 / V112 / V113 5 高頻 table 在 schema spec **明寫 hypertable + retention/compression policy**
2. Sprint 1B 前置 baseline profiling task：`pg_stat_statements` + `pg_buffercache` + `pg_total_relation_size` 全表 baseline，做 6mo growth projection
3. PA dispatch 派 MIT + E5 review V106 chunk size + compression policy（default `INTERVAL '7 days'` 還是 `INTERVAL '30 days'`？）

---

### Risk 2：hot path SLA 對 M1 Tier 2 auto-execute / M3 health probe / M8 anomaly z-score 在 production fill path 影響

**嚴重度**：HIGH
**位置**：v5.8 §2 M1 / M3 / M8 spec

**Detail**：
- 現有 baseline（per E5 memory 2026-05-21 LG-1 audit）：H0 hot path p99 sub-1μs / max 346μs / SLA 1ms
- v5.8 三個 module 在 production fill path / tick path：
  - **M1 Tier 2 auto-execute**：cross-strategy reweight 觸發在 monthly cadence（per spec），不在 fill path → **0 hot path 衝擊**
  - **M3 health probe**：per-domain probe in watchdog cron / IPC path → 若 probe 寫入 V106 在 tick 路徑會 break SLA；spec 為 watchdog cron 路徑 → **0 hot path 衝擊**
  - **M8 anomaly z-score**：spec 寫 "rolling z-score in production fill path"
    - 計算量：rolling window 30-60 sample × N feature = 30-300 multiply-add per fill
    - 估算 latency：~5-20μs per fill（cache friendly）
    - SLA budget：tick <0.3ms 已用 ~24μs / fill 路徑 <1ms 較鬆
    - **Concern**：M8 spec 寫「own behavior anomaly: fill rate divergence, slippage outlier (single fill > 3σ historical)」需 maintain rolling state in hot path
    - **5-20μs / fill 路徑 1ms budget = 0.5-2% budget consumption — 邊際但需測**

**Must-fix**：
1. M8 schema 設計加 `production_path_eligible BOOL` flag，default FALSE；spec 明寫 only 「rolling z 在 background tokio task；fill path 只 sample + queue」分離
2. Sprint 1A-γ M8 ADR-0036 明寫「**hot path budget ≤ 5μs / fill；超 budget 必 reject**」
3. Sprint 3 M8 read-only logging IMPL 前 E5 review hot path budget benchmark gate
4. M3 spec 明寫「probe in cron path only；無 production tick 路徑 caller」

---

### Risk 3：v5.8 Sprint 1A 7 週 calendar 在 7 並行 sub-agent 假設下偏緊；β/γ 階段 cross-ADR collision 風險

**嚴重度**：HIGH
**位置**：v5.8 §3 Sprint 1A-α-ε 五階段

**Detail**：
- v5.8 §3 列 7 ADR (0034-0040) + 12 schema migration (V105-V116) Sprint 1A 全 land
- β/γ/δ 三階段共 13 module schema/ADR 並行 → **7 並行 sub-agent load**
- 操作員多 session 經驗（per CLAUDE.md memory `project_multi_session_memory_race`）：3-5 並行可控；7+ 並行 cross-session collision 風險 HIGH
- Cross-ADR 衝突點：
  - M1 (ADR-0034) + M7 (decay) + M6 (reward weight) **共用 Allocator state machine** → 3 ADR cross-reference 必同步
  - M2 (overlay state machine) + M8 (anomaly) + M3 (health) **共用 degradation trigger** → 3 ADR coupling
  - M4 (hypothesis discovery) + M9 (A/B framework) + M11 (replay divergence) **共用 learning.* schema namespace** → 3 schema migration cross-FK
- v5.8 §12 已標 "compress Sprint 1A-γ+δ+ε" optional shortcut 但 "high cross-ADR collision risk"

**Must-fix**：
1. **β/γ/δ 必須順序 dispatch**：β 完成 + cross-ADR collision audit → γ dispatch → γ 完成 + audit → δ dispatch（不重疊）
2. 每階段加 cross-ADR consistency gate（PA + TW 各 4-6 hr）
3. ε 階段 40-60 hr 上修為 **60-90 hr**（cross-ADR collision audit + schema FK validation + Mac CI 全模組 verify）
4. 接受 Sprint 1A 7 週 calendar 可能 slip 1-2 週至 9 週

---

## 2. hot path SLA 影響（13 module 分類）

| Module | Hot path 影響 | SLA budget | Risk |
|---|---|---|---|
| M1 Tier 0-4 Lease | Tier 0 per-fill 已存（不變）；Tier 2 auto-execute 在 cross-strategy reweight 路徑 (monthly) | 0 影響 | LOW |
| M2 Overlay state machine | 在 GuardianVerdict 路徑加 state check ~100ns | <1% budget | LOW |
| M3 Health probe | cron / IPC path **only**；不在 tick/fill | 0 影響 | **LOW（前提：ADR-0036 明禁 production path caller）** |
| M4 Hypothesis miner | nightly / weekly cron；非 hot path | 0 影響 | LOW |
| M5 Online learning | Y3+ 不在 Y1 hot path scope | 0 影響 | LOW（已 interface stub）|
| M6 Reward weight calibration | monthly Bayesian opt run；非 hot path | 0 影響 | LOW |
| M7 Decay detection | daily rolling Sharpe；非 hot path | 0 影響 | LOW |
| **M8 Anomaly z-score** | **per-fill rolling z 風險**；spec 需明寫只 sample + queue | **5-20μs / fill = 0.5-2% budget** | **HIGH** |
| M9 A/B framework | per-fill assignment 路徑 ~200ns hash lookup | <1% budget | LOW |
| M10 Discovery pipeline | weekly cron；非 hot path | 0 影響 | LOW |
| M11 Nightly replay | nightly cron；非 hot path | 0 影響（daily resource budget）| LOW |
| M12 Adaptive order routing | per-order maker-vs-taker decision ~500ns | <1% budget | MEDIUM（依 Bybit WS rate budget）|
| M13 Multi-venue | Y2+ Bybit-only Y1；無 hot path 改動 | 0 影響 | LOW（已 interface stub）|

**結論**：13 module 中只有 **M8** 真正觸 hot path budget；**M12** 邊際；其餘 0 影響或 cron-only。

---

## 3. PG 4-8GB 容量規劃（V105-V116）

**6mo growth projection**：
| Table | Cadence | 6mo rows | 6mo size | Hypertable? | Retention |
|---|---|---|---|---|---|
| V105 overlay_state_transitions | low | ~250 | <1 MB | NO | 永久 |
| **V106 health_observations** | **high** (1-5 min × 5 domain) | **~5M-15M** | **~1.25-2.5 GB** ⚠️ | **YES**（30d chunk + compress 7d）| 90d retention |
| V107 replay_divergence_log | daily | ~180 | <5 MB | NO | 永久 |
| V108 ab_tests + assignments + results | mid (fill volume × 2) | ~25k-100k | ~50-200 MB | NO | 永久 |
| V109 anomaly_events | event | ~1k-5k | ~5-30 MB | NO | 永久 |
| V110 reward_weight + bayesian_opt | monthly | ~6 + 250 | <5 MB | NO | 永久 |
| V111 discovery_tier + capital_triggers | low | ~50 | <1 MB | NO | 永久 |
| V112 decision_lease_tiers + log | mid | ~5k-25k | ~30-100 MB | NO | 永久 |
| V113 decay_signals + strategy_lifecycle | daily × 5 | ~1k + 50 | ~30 MB | NO | 永久 |
| V114-V116 | interface-only | 0 | 0 | N/A | N/A |
| **Total 6mo** | | | **~1.4-2.9 GB** | | |

**Critical**：
- V106 health_observations **占 50-86% 新表 6mo size**
- 必須 hypertable + 30d chunk + 7d compression + 90d retention
- 4-8GB shared_buffer 在 6mo growth +1.4-2.9 GB + 既有 32 GB hot tables 下 working set 漲幅 ~5-10%；命中率衝擊 marginal

**Must-fix**：
1. Sprint 1A-β V106 spec 明寫 `CREATE TABLE ... PARTITION BY RANGE (observed_at)` + `SELECT create_hypertable(..., chunk_time_interval => INTERVAL '7 days')` + `ALTER TABLE ... SET (timescaledb.compress, ...)` + `add_compression_policy(..., INTERVAL '7 days')` + `add_retention_policy(..., INTERVAL '90 days')`
2. Sprint 1B PG buffer baseline + `pg_buffercache` 命中率 baseline + 6mo / 24mo growth projection 報告
3. V108 ab_assignments 雖然是 mid-frequency 但 cardinality 隨 AUM 線性增長；Y2+ AUM $25-50k 需 re-baseline

---

## 4. 文件大小 800/2000 limit 對新 module 代碼

**v5.8 §2 各 module 估算 LOC** + E5 拆分建議：

| Module | 估 LOC | 800 警告？ | 2000 hard cap？ | 拆分建議 |
|---|---|---|---|---|
| M1 Lease Tier IMPL (Tier 1+2 + auto-eligibility) | ~500-700 | maybe | NO | M1 single file <800；若超 split: `tier_eligibility.rs` + `auto_approval_gate.rs` |
| M2 Overlay state machine | ~300-500 | NO | NO | single file |
| **M3 Healthcheck system** | **~600-900** | **YES** | NO | 預先拆: `health_probes/{ws,rest,db,disk,memory,strategy}.rs` 6 sibling + `degradation_state.rs` + `mod.rs` |
| **M4 Pattern miner** | **~400-800** (stage 1) **+ 600-1200** (stage 2) | YES | NO | 預先拆: `correlation_miner.rs` + `event_window.rs` + `clustering.rs` + `hypothesis_draft.rs` |
| M5 Online learning interface | <100 | NO | NO | single file |
| M6 Reward weight calibration | ~400-600 | NO | NO | single file |
| M7 Decay detector + lifecycle SM | ~400-600 | NO | NO | single file |
| **M8 Anomaly detector** | **~500-800** (stat) + **800-1500** (ML autoencoder Y2) | maybe | NO | 預先拆: `regime_detector.rs` + `behavior_anomaly.rs` + `stat_methods.rs` + `severity_router.rs` |
| **M9 A/B framework** | **~500-800** | maybe | NO | 預先拆: `ab_assignment.rs` + `mSPRT.rs` + `multiple_comparison.rs` |
| M10 Discovery tier registry | ~300-500 | NO | NO | single file |
| **M11 Nightly replay automation** | **~400-700** | maybe | NO | 預先拆: `replay_job.rs` + `divergence_detector.rs` + `daily_report.rs` |
| M12 OrderRouter trait + maker-vs-taker | ~600-900 | YES (Y1 末) | NO | 預先拆: `router_trait.rs` + `maker_taker_decision.rs` + `slicing.rs` |
| M13 AssetClass/Venue enums + registry | ~300-500 | NO | NO | single file Y1; Y2+ split |

**Must-fix**：
1. Sprint 1A-β/γ 各 module spec **必明寫 sibling file structure**（不能等 IMPL 撞 800 line 才拆）
2. M3 (healthcheck) / M4 (pattern miner) / M8 (anomaly) / M11 (replay) **預先拆 3-6 sibling** 是強烈推薦（避免 G5-09 tick_pipeline/tests.rs 3524 LOC 重蹈）
3. E5 在 Sprint 1A-ε integration verify 階段 grep `wc -l` 所有 module 新檔，> 800 強制 split

---

## 5. Apple Silicon CI (v57-C11 carry over)

**v5.7 v57-C11**：`cargo check --target aarch64-apple-darwin --release` **hard gate** + clippy 軟強制 + P2-CLIPPY-CLEANUP-1（既有 17 errors 並行清）

**v5.8 影響**：
- 13 module 新增 ~10+ new Rust crate / module（M1/M3/M4/M6/M7/M8/M9/M10/M11/M12/M13）
- 每個必過 `cargo check --target aarch64-apple-darwin`
- **新風險**：M4 pattern miner 若用 `ndarray-stats` / `linfa-clustering` Linux-only 編譯 dep → 必驗 `aarch64-apple-darwin` target
- M8 anomaly autoencoder（Y2）若用 `tch-rs` / `burn` → Apple Silicon Metal backend 不一定齊
- M11 replay automation 若用 `inotify` 或 `epoll` 直呼 → break Mac CI

**Must-fix**：
1. v5.8 §3 Sprint 1A-α 加 Apple Silicon CI tuple 強制條款（已 carry from v5.7-C11）
2. Sprint 1A-β/γ 每 module DESIGN 必標 "platform: linux + aarch64-apple-darwin cross-compile required"
3. Sprint 1A-ε integration verify 加 Mac cross-compile 全模組 batch verify（不是逐 module 驗）
4. M4 / M8 ML crate selection 必須 cross-platform（避免 `linfa-*` linux-only feature）

---

## 6. 對 PA+PM 匯總必收 top 3

1. **Sprint 1A-α-ε 7 週 calendar 在 70% parallel 下達 mid-range；HIGH cross-ADR collision risk**
   - β/γ/δ 必須順序 dispatch（不重疊）；每階段加 cross-ADR consistency gate（PA+TW 各 4-6 hr）
   - ε 上修 40-60 → 60-90 hr
   - 接受 Sprint 1A 可能 slip 1-2 週至 9 週

2. **V106 health_observations 必 hypertable + retention/compression policy from Sprint 1A-β**
   - 否則 6mo PG growth +1.25-2.5 GB 在 4-8GB buffer 下 16-63% 占用 → working set 命中率衝擊
   - Sprint 1A spec 必明寫 `chunk_time_interval => '7 days'` + compression after 7d + retention 90d

3. **M8 anomaly detector hot path budget hard gate**
   - ADR-0036 明寫「hot path budget ≤ 5μs / fill；超 budget 必 reject」
   - schema 加 `production_path_eligible BOOL` flag default FALSE
   - Sprint 3 read-only logging IMPL 前 E5 review benchmark gate

---

## 7. v5.8 派發前 must-fix（2026-05-22 內 land；不阻塞 v5.7 Sprint 1A-α）

| ID | 內容 | 工時 | Owner | 阻塞性 |
|---|---|---|---|---|
| **E5-V58-1** | V106 health_observations spec 加 hypertable + retention/compression policy | 1-2 hr | PA + MIT | 阻塞 Sprint 1A-β M3 schema |
| **E5-V58-2** | M8 ADR-0036 hot path budget ≤ 5μs / fill hard gate 條款 | 30 min | TW + E5 | 阻塞 Sprint 1A-γ M8 schema |
| **E5-V58-3** | Sprint 1A-β/γ/δ 順序 dispatch + cross-ADR collision gate 規則 | 1 hr | PA | 阻塞 Sprint 1A-β 派發 |
| **E5-V58-4** | M3/M4/M8/M9/M11/M12 spec 預先拆 sibling file structure 章節 | 2-3 hr | PA × 6 並行 | 阻塞 Sprint 1A-β/γ schema 完成 |
| **E5-V58-5** | Sprint 1A-ε 工時 40-60 → 60-90 hr 上修（cross-ADR + Mac CI 全模組 verify）| 30 min | PM | 不阻塞 dispatch，更新 v5.8 主檔 §3 §4 |

**Total**：5-7.5 hr，5 並行 sub-agent 在 2026-05-22 內可完成。

---

## 8. Sprint 1A-β-ε 期間 should-fix（並行 dispatch 機會）

### 8.1 V106 hypertable + retention/compression policy IMPL（β 階段）
- 派 E1 + MIT IMPL V106 migration including TimescaleDB policies
- 估時：6-8 hr（含 PG dry-run + idempotency test）

### 8.2 Sprint 1A-β 5 module DESIGN 並行（M1/M3/M6/M7/M11）
- 5 sub-agent 並行（PA × 5 或 PA + MIT + TW + E1 × 2）
- 估時：每 module 8-15 hr DESIGN + 2-4 hr cross-ADR sync = 50-95 hr/sub-agent × 5 = 220-320 hr plan / 5 並行 = 44-64 hr wall-clock = **2 週 calendar**

### 8.3 Sprint 1A-γ 5 module DESIGN 並行（M2/M4/M8/M9/M10）
- 5 sub-agent 並行
- 注意：M4 pattern miner schema 複雜度高（partition by event_window vs cross-correlation 不同 storage layout）
- 估時：plan 190-290 hr / 5 並行 ≈ 38-58 hr wall-clock = **2 週 calendar**

### 8.4 Sprint 1A-δ 3 interface stub（M5/M12/M13）
- 3 sub-agent 並行（PA + TW + E1）
- 估時：58-82 hr / 3 ≈ 19-27 hr wall-clock = **1 週 calendar**

### 8.5 Sprint 1A-ε integration verify（強制 single-thread）
- 60-90 hr / 1 = 60-90 hr / 30-40 hr/週 = **1.5-2.3 週 calendar**

### 8.6 既有 helper 復用機會（降工時）
- M3 healthcheck system → 復用既有 `helper_scripts/db/passive_wait_healthcheck.sh` + watchdog cron pattern
- M11 nightly replay → 復用既有 Stage 0R replay infra + replay/runner.rs
- M9 A/B assignment → 復用既有 trial_id hash-based partition 邏輯
- M1 Lease Tier → 復用 lease.rs HashMap state machine 既有 pattern

**估收益**：Sprint 1A-β/γ 工時可從 410-610 hr **降 15-25%** 至 310-510 hr（per module sub-agent 復用識別 1-3 hr each）。

### 8.7 hot path baseline profiling（β 階段並行）
- v5.7 audit Must-fix（不會在 v5.8 自動 carry over）：建議 v5.8 §3 補加
- E5 派遣 baseline：當前 H0/tick/IPC P50/P95/P99 + RAM/CPU peak + PG buffer 命中率
- 估時：4-6 hr
- 用於 Sprint 3+ M8 hot path budget benchmark gate

---

## 9. 附錄：5-10x 規律 calibration summary

| 維度 | 對 5-10x 規律敏感度 | E5 calibration multiplier |
|---|---|---|
| ADR draft / spec / dry-run | LOW (規律基本不適用) | 0.8-1.2x plan |
| Schema migration DESIGN（無 IMPL）| LOW | 0.9-1.3x plan |
| Cross-ADR consistency audit | MEDIUM | 1.2-1.5x plan |
| Module IMPL（Rust + trait + test）| **HIGH** | **1.5-2.5x plan**（5-10x 規律 partial 適用）|
| E2E + hot path benchmark | HIGH | 1.3-1.8x plan |
| Integration verify | MEDIUM-HIGH | 1.2-1.5x plan |
| Sub-agent parallel productivity | LOW | 取 sub-agent count × 4-8 hr productive |
| Wall-clock vs actor-hour ratio | depends | 50% parallel 強制 = 0.5x；70% parallel possible Sprint 1A = 0.3-0.4x；40-50% Sprint 2-7 IMPL = 0.5-0.6x |

**Anchor**：v5.7 12 prefix DONE actor-hour ≈ 33-66 hr vs plan 60-80 hr = **0.55-1.10x** （在 plan 範圍內或略低）— 因 12 prefix 全是 ADR/spec/dry-run，5-10x 規律不適用。

---

**END E5 v5.8 Executability Audit**

Verdict 摘要：**GO-WITH-CONDITIONS** — v5.8 邏輯 + 13-module phasing 合理，operator forgetfulness mitigation 設計紮實。但 (1) PG buffer 對 V106 health_observations 高頻表必先標 hypertable/retention/compression；(2) M8 anomaly detector hot path budget 必加 ≤ 5μs / fill hard gate；(3) Sprint 1A 7 週 calendar 在 70% parallel 下達 mid-range，β/γ/δ 必須順序 dispatch + cross-ADR collision gate；(4) 5 派發前 must-fix 5-7.5 hr 在 2026-05-22 內 land。完成 must-fix 後可 dispatch Sprint 1A-β。Y1 工時 plan 2,780-3,930 hr 系統性偏低約 26-43%（E5 重估 3,500-5,600 hr），44 週 calendar 在 50% parallel 強制下需延伸至 55-65 週（Y2 Q1 mid）。Operator 應預期此 calendar slip。
