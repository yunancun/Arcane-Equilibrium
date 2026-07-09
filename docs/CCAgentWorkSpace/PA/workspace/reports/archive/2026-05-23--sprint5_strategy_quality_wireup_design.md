---
report: PA design — Sprint 5+ §4.3.1 StrategyQualityEmitter wire-up
date: 2026-05-23
author: PA
phase: Sprint 5+ §4.3.1 P1 design (single-thread 3-4 hr budget)
spec_artifact: srv/docs/execution_plan/2026-05-23--sprint5_strategy_quality_wireup_design.md
status: DESIGN-DONE
parent: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_first_live_carryover_pm_phase_3e_signoff.md §4.3.1
risk_grade: 中（M3 emitter 改 + main.rs caller 加 + 新 PG query；無 trading effect；無風控變更）
---

# Sprint 5+ §4.3.1 StrategyQualityEmitter wire-up — PA design report

## §1 Executive Summary

**Task**：Sprint 4+ first Live carry-over §4.3.1（per PM Phase 3e sign-off 2026-05-23）StrategyQualityEmitter wire-up — 解 Track E V106 0 row 例外。3-4 hr single-thread design only；不 IMPL；不派下游 sub-agent；不 commit。

**Deliverable**：
1. spec doc：`srv/docs/execution_plan/2026-05-23--sprint5_strategy_quality_wireup_design.md`（790 行；10 章節）
2. PA report：本檔

**Verdict**：**DISPATCH READINESS OPEN** — Sprint 5+ §4.3.1 IMPL 工作 readiness gate 開啟條件全 land；E1 IMPL phase 8-11 hr budget；Phase A scaffold 6-8 hr + Phase B production deploy 2-3 hr。

**3 反問結論**：
1. `learning.lease_transitions` schema 無 strategy_name 欄位 → 經 `context_id` JOIN `trading.signals` 反查（PG empirical bottleneck，Phase B AC-4 必驗）
2. cache 為 batch snapshot（25 pair × 5 metric 一次 PG query 整 HashMap 覆寫）而非 sliding window — 不同於 risk_envelope `PortfolioStateCache` 增量 push 語意
3. update task 5 min tick 對齊 emitter `sample_interval_sec=300` — Pareto-optimal 設計

---

## §2 5 metric source 識別

完整 SSOT 對映（per spec §2.1-§2.5）：

| Metric | SSOT 表 / column | PG query 形式 | fail-soft default |
|---|---|---|---|
| `fill_rate_intent_ratio` | `trading.signals` + `trading.fills` 24h JOIN | `COUNT(fills) / COUNT(signals) WHERE signal_type IN ('LONG', 'SHORT')` per (strategy, symbol) | 1.0 OK band |
| `slippage_bps_p95` | `trading.fills.slippage_bps` (V028 column) | `percentile_cont(0.95) WITHIN GROUP (ORDER BY ABS(slippage_bps))` 24h | 0.0 OK band |
| `decision_lease_grant_rate` | `learning.lease_transitions` (V054) | `granted_count / requested_count` per strategy；經 `context_id` JOIN `trading.signals` 反查 strategy_name | 1.0 OK band |
| `dormant_minutes` | `trading.fills.ts` MAX per (strategy, symbol) | `EXTRACT(EPOCH FROM (NOW() - MAX(ts))) / 60.0` | 0 OK band |
| `signal_count_24h` | `trading.signals` 24h count | `COUNT(*) WHERE signal_type IN ('LONG', 'SHORT')` 24h | 0（telemetry-only） |

**SSOT 整合**：Path A 推薦 — 1 個 big CTE join query 一次拿 25 pair × 5 metric snapshot；單一 round-trip 5-10 ms latency；對比 5 query parallel 25-50 ms latency。

---

## §3 RealStrategyQualitySourceProbe design

per Wave A PA-DRIFT-5 `RealRiskEnvelopeSourceProbe` + `PortfolioStateCache` pattern：

### 3.1 新 file scope（spec §3.1）

```
rust/openclaw_engine/src/health/domains/strategy_quality_probe_impl.rs (新 ~200 LOC)
├── StrategyQualityMetricsSnapshot (struct; 5 field + last_update_ts_ms; Copy)
├── StrategyQualityMetricsCache
│   ├── snapshots: HashMap<(String, String), StrategyQualityMetricsSnapshot>
│   ├── last_batch_update_ts_ms: u64
│   ├── update_batch(now_ms, snapshots)  // 整 HashMap 覆寫 + F-2 NaN sanitize
│   ├── snapshot_for(strategy, symbol) -> StrategyQualityMetricsSnapshot
│   ├── last_batch_update_ts_ms() telemetry
│   └── active_pair_count() telemetry
└── RealStrategyQualitySourceProbe
    ├── new(cache: Arc<Mutex<...>>)
    ├── cache_handle() audit helper
    └── impl StrategyQualitySourceProbe (5 method lookup cache)
```

### 3.2 Update task pattern（spec §3.2）

```
rust/openclaw_engine/src/main_health_emitters.rs 新增 Track E section ~80 LOC
├── build_strategy_quality_pair_list() -> Vec<(String, String)>  // 25 pair 5×5
├── build_strategy_quality_scheduler(db_pool, engine_mode, event_bus) -> Option<(scheduler, cache)>
├── spawn_strategy_quality_scheduler(db_pool, engine_mode_str, event_bus, cancel) -> Option<cache_handle>
├── spawn_strategy_quality_update_task(cache, db_pool, cancel)
├── run_strategy_quality_query_batch(cache, db_pool) -> Result<(), sqlx::Error>
└── STRATEGY_QUALITY_BATCH_QUERY const (CTE join 5 metric query)
```

### 3.3 main.rs caller 增量（spec §4.2）

main.rs Wave B wire-up block (line 1440-1457) 後加 ~10 LOC：
```rust
let strategy_quality_cache = main_health_emitters::spawn_strategy_quality_scheduler(
    &db_pool, primary_engine_mode, Arc::clone(&health_event_bus), &cancel,
);
if let Some(cache) = strategy_quality_cache {
    main_health_emitters::spawn_strategy_quality_update_task(cache, Arc::clone(&db_pool), &cancel);
}
```

---

## §4 5 AC + Sprint 5+ IMPL phase split

### 4.1 AC（6 條對齊 Sprint 2 Track E + Wave A/B 拆分契約）

| AC# | 內容 | 路徑 | Phase |
|---|---|---|---|
| **AC-1a** | `StrategyQualityMetricsCache` in-memory empirical（mock 25 pair × 5 metric snapshot → 5 trait method × 125 lookup 全對齊） | cargo test --release | Phase A scaffold |
| **AC-1b** | production V106 30 min window `strategy_quality` row count ≥ 125（25 pair × 5 metric × 1 tick）；distinct strategy ≥ 5 + distinct symbol ≥ 5 | Linux PG empirical | Phase B deploy |
| **AC-2** | 4-state ladder + per-(strategy, symbol) SM observe_classified 升 CRITICAL；對齊 Sprint 2 既有 SM 測 | cargo test --release | Phase A scaffold |
| **AC-3** | aggregate SM 0.40 ratio rule 升 DEGRADED；25 pair 中 11 pair (44%) DEGRADED → aggregate DEGRADED | cargo test --release | Phase A scaffold |
| **AC-4** | PG empirical dry-run：query string + result row parse + < 100ms latency；5 column 對齊 `StrategyQualityRow` sqlx::FromRow | ssh trade-core psql | Phase B deploy |
| **AC-5** | spike default false / production binary 0 mock 滲透；`nm release-binary \| grep -i strategy_quality.*mock` 0 hit | cargo build --release + nm | Phase A scaffold |
| **AC-6** | OBSERVE-4 replay subprocess emit forbidden（沿用既有 Sprint 2 Track E test pattern） | cargo test --release | Phase A scaffold |

### 4.2 Phase split

**Phase A — scaffold（6-8 hr）**：
- E1 IMPL：5.5 hr（strategy_quality_probe_impl.rs 3 hr + main_health_emitters.rs Track E 2 hr + main.rs 30 min + log literal 5 min）
- E1 test：2 hr（8 unit test in `tests/sprint5_wave_c_strategy_quality_wireup.rs`）
- E2 review：2 hr（round 1 expected 0-2 finding；round 2 closure）
- **Phase A AC**：AC-1a + AC-2 + AC-3 + AC-5 + AC-6 PASS

**Phase B — production deploy + real PG empirical（2-3 hr）**：
- QA AC-4 Linux PG dry-run：30 min
- operator restart_all.sh --rebuild + Track E scheduler alive log：15 min
- QA AC-1b production 30 min sample + V106 row count verify：30 min + 30 min wait
- PM Phase 3e sign-off + carry-over routing：30 min
- **Phase B AC**：AC-1b + AC-4 PASS

**Total Sprint 5+ §4.3.1 budget**：8-11 hr

### 4.3 並行可行性

- §4.3.1（本 spec）+ §4.2.1（BybitPrivateWs supervisor 改造）+ §4.2.2（PortfolioStateCache wire-up real）共用 `main_health_emitters.rs`；建議 **sequential E1** 或 **stagger 5min**；E2 round 1 必驗 3 task 不破壞彼此 wire-up entry
- §4.3.2-§4.3.6 + §4.2.3-§4.2.4 0 file scope conflict；全並行可

---

## §5 Sprint 5+ §4.3.1 dispatch readiness verdict

### 5.1 Gate status：**DISPATCH READY (OPEN)**

**已 land 前置條件**：
1. ✅ Sprint 2 Wave 2 Track E IMPL 完成（commit 6f6bbea8 + ffb7ed48 + 4d4ff99f；strategy_quality.rs 1580 LOC + tests 851 LOC + E2 APPROVE）
2. ✅ Sprint 4+ Wave A/B M3 emitter scaffold 5 active domain × 30 min × 770 row production AC-1b PASS
3. ✅ Wave A PA-DRIFT-5 `RealRiskEnvelopeSourceProbe` + `PortfolioStateCache` pattern 確立 + E2 round 1+2 APPROVE
4. ✅ M-1 Singleton Registry SSOT 建立（`docs/architecture/singleton-registry.md`）；本 wire-up 新 `StrategyQualityMetricsCache` 必登記
5. ✅ SSOT 表全 land：`trading.signals` / `trading.fills` (V003) + `slippage_bps` (V028) + `learning.lease_transitions` (V054)
6. ✅ engine_mode tag 4 值（paper/demo/live_demo/live）對齊 V106 CHECK + 既有 V### chain
7. ✅ Linux PG SSOT 表存在（`ssh trade-core psql` empirical 已驗）

**Phase A IMPL 入口條件**：全 ready；可立即派 E1。
**Phase B production deploy 入口條件**：依賴 Phase A APPROVE + production engine restart capability（既有 deploy chain 已驗 Sprint 4+ Wave B）。

### 5.2 OPEN 路徑

1. operator 確認本 spec 設計
2. PM 派 E1 開 Phase A IMPL（`feature/sprint5_track_e_wireup` 或加入既有 Sprint 5+ working branch）
3. E1 IMPL `strategy_quality_probe_impl.rs` + `main_health_emitters.rs` Track E + `main.rs` caller + 8 unit test
4. E2 round 1 review → fix → round 2 APPROVE
5. operator deploy + QA Phase B AC-4 PG dry-run + AC-1b 30 min production sample
6. PM Phase 3e sign-off

### 5.3 風險評級：**中**

per profile 「改邏輯但有完整測試覆蓋的模塊」：
- 改 `main_health_emitters.rs` Wave B already-stable wire-up（風險 中）
- 加 `strategy_quality_probe_impl.rs` 新 module；不改既有業務邏輯（風險 低）
- 加 `main.rs` ~10 LOC（風險 低）
- 新 PG batch query 5 CTE join；複雜度中（風險 中；Phase B AC-4 必驗）
- 共用 `main_health_emitters.rs` 與 §4.2.1/§4.2.2 並行需 stagger（風險 低）

### 5.4 E2 重點審查 3 點

1. **PG query string 對齊 spec §2 + §3.2**：CTE 5 metric 不漂；fail-soft default 對齊既有 trait doc line 424；engine_mode IN 4 值對齊 V106 CHECK
2. **`StrategyQualityMetricsCache` update_batch 不破 既有 strategy_quality.rs scheduler 預建 100 SM key（per spec §6 反模式 (e) 25 pair tuple 分隔 cap key）**：scheduler ctor 取 `emitter.pairs()` 預建 SM；emitter ctor 接 `RealStrategyQualitySourceProbe`；pair list 由 `build_strategy_quality_pair_list` 25 pair 注入 — chain 完整不漂
3. **log literal `main_health_emitters.rs:441` 同步 update**（per spec §4.3）；E2 round 1 grep `"Track E skip"` 必返 0 hit

---

## §6 副作用 + 硬邊界 verify

### 6.1 副作用識別

| # | 問題 | 答案 |
|---|---|---|
| 1 | 有其他模塊 import `strategy_quality.rs`？ | grep 結果 0 hit production code import 既有 Track E（per main_health_emitters.rs line 22-23 + 413 Wave B skip 註標即唯一 reference site）；新增本 spec 不破現有 import chain |
| 2 | 改動函數在哪些測試 mock？ | 0 mock；`StrategyQualitySourceProbe` trait 既有 `StubSource` test impl（strategy_quality.rs line 1169）；本 spec 加 `RealStrategyQualitySourceProbe` 並列 impl，不影響 StubSource |
| 3 | asyncio/threading 混用邊界？ | Rust `tokio::spawn` + `parking_lot::Mutex` 對齊既有 PA-DRIFT-5 pattern；無 Python 跨語言邊界 |
| 4 | 改動 API response schema？ | NO；本 wire-up 純 PG INSERT → V106 row；GUI / IPC 端 0 變更 |
| 5 | RustEngine ↔ Python IPC schema 觸？ | NO；M3 emitter 是純 Rust internal observability layer |

### 6.2 硬邊界 verify（per CLAUDE.md §四 + 16 根原則 checklist）

| Hard Boundary | 觸碰？ |
|---|---|
| `live_execution_allowed` | ✗ 不觸碰 |
| `execution_authority` | ✗ 不觸碰 |
| `decision_lease_emitted` | ✗ 不觸碰；只觀測 lease_transitions 表 |
| `max_retries=0` | ✗ 不觸碰 |
| `OPENCLAW_ALLOW_MAINNET` | ✗ 不觸碰 |
| `live_reserved` | ✗ 不觸碰 |
| `authorization.json` 寫入 | ✗ 不觸碰 |
| Bybit retCode != 0 fail-closed | ✗ 不觸碰 |

**Verdict**：0 hard boundary 觸碰；改動屬 observability layer。

### 6.3 OBSERVE-4 invariant verify

- emitter scheduler.run 啟動 + tick boundary 均檢 engine_mode；replay subprocess fail-loud Err（既有 strategy_quality.rs line 706-708 + 728-737）
- 本 wire-up 不變更 OBSERVE-4 guard 邏輯；caller 端 main.rs `primary_engine_mode` 4 值 paper/demo/live_demo/live 全合法（Sprint 4+ Wave B 已驗）

---

## §7 16 根原則 checklist 跑（per skill `16-root-principles-checklist`）

per `srv/.claude/skills/16-root-principles-checklist/SKILL.md`：

**評級：A 級**（16/16 完全合規 + 0 硬邊界觸碰）

| # | 原則 | 證據 |
|---|---|---|
| 1 | 單一寫入口 | spec §7 — Track E 0 寫；emitter 端純讀 PG SSOT |
| 2 | 讀寫分離 | spec §7 — probe 端純讀；update task SELECT only |
| 3 | AI 輸出 ≠ 命令 | spec §7 — 0 AI inference |
| 4 | 策略不繞風控 | spec §7 — 不改策略邏輯 |
| 5 | 生存 > 利潤 | spec §7 — 不改交易行為 |
| 6 | 失敗默認收縮 | spec §3.1 fail-soft default OK band；F-2 NaN sanitize |
| 7 | 學習 ≠ 改寫 Live | spec §7 — 不寫 strategy_engine / fill_writer |
| 8 | 交易可解釋 | spec §7 — V106 row 5 metric + state + strategy + symbol |
| 9 | 災難保護 | spec §7 — DEGRADED 不降 LAL Tier |
| 10 | 認知誠實 | spec §3 + §8 反模式禁 placeholder snapshot |
| 11 | Agent 最大自主 | spec §7 — 0 agent 接點 |
| 12 | 持續進化 | spec §7 — V106 5 metric × 25 pair 為後續 strategy quality empirical SSOT |
| 13 | AI 成本感知 | spec §7 — 0 AI call |
| 14 | 零外部成本可運行 | spec §7 — PG local infra |
| 15 | 多 Agent 協作 | spec §7 — 不破 5 Agent + Conductor 通信 |
| 16 | 組合級風險 | spec §7 — aggregate 0.40 ratio 反映 portfolio-level strategy quality issue |

**9 安全不變量 verify**：M3 emitter 是 observability layer；9 不變量全保（per Wave A/B 已驗 + 本 wire-up 不改 trading 邏輯）。

---

## §8 教訓 / 反模式（4 條）

1. **PA design 強制 PG empirical 驗證 schema 假設**：本 spec §2.3 設計反問 #1 揭露 `learning.lease_transitions` 無 strategy_name 欄位 → 經 context_id JOIN 反查；若無 PG empirical 驗證 schema bottleneck 直接 spec literal 「per strategy」會在 E1 IMPL 階段才 catch（per Sprint 1A-ζ Phase 3a `learning.governance_audit_log` empirical 教訓）。
2. **Cache pattern 對齊既有 Wave A PA-DRIFT-5 確立**：本 spec §3.1 `StrategyQualityMetricsCache` 1:1 對齊 `PortfolioStateCache` API surface（new / update_batch / lookup_for / telemetry 4 method 同形）+ Arc<parking_lot::Mutex<>> sharing pattern；E1 IMPL 學習曲線 ≈ 0；E2 review 走「pattern 對齊」核查節省時間。
3. **300s tick aligned across update + sample 是 Pareto-optimal**：spec §3.3 反問 #3 顯式對抗反問「為什麼不更快 update tick」；結論 sample tick 慢於 update tick 是 wasted；sample tick 快於 update tick 走 stale；300s aligned 是唯一無 leak / 無 waste 設計。
4. **placeholder snapshot 走 OK band 對齊 既有 trait doc line 424**：本 spec §3.1 fail-soft default 全 OK band（fill=1.0 / slippage=0 / lease=1.0 / dormant=0 / signal=0）；違反 = E1 走 0.5 / 0.7 等「中間值」走 WARN / DEGRADED band 30 天連續染色 — 同 Wave B Track B placeholder round 1 IMPL 5 metric 全 0 走 DEGRADED 染色 bug（per main_health_emitters.rs line 97-115 round 2 HIGH-1 fix）。

---

## §9 完成回報（4 條）

1. **5 metric source 識別**：完成 — `fill_rate_intent_ratio` (signals+fills) / `slippage_bps_p95` (fills.slippage_bps V028) / `decision_lease_grant_rate` (lease_transitions V054 → context_id JOIN signals) / `dormant_minutes` (fills MAX) / `signal_count_24h` (signals COUNT 24h)；1 big CTE join query Path A 推薦
2. **RealStrategyQualitySourceProbe design**：完成 — 200 LOC 新 file `strategy_quality_probe_impl.rs`；`StrategyQualityMetricsCache` 25 instance HashMap + F-2 NaN sanitize + fail-soft default OK band；update task 300s tick + 對齊 emitter sample_interval；pattern 1:1 對齊 Wave A PA-DRIFT-5 `PortfolioStateCache`
3. **6 AC + Sprint 5+ IMPL phase split**：完成 — Phase A scaffold（6-8 hr E1+E2；AC-1a/2/3/5/6 PASS）+ Phase B production deploy（2-3 hr QA+operator+PM；AC-1b/4 PASS）；total 8-11 hr Sprint 5+ §4.3.1 budget
4. **Sprint 5+ §4.3.1 dispatch readiness verdict**：**OPEN** — 7 前置條件全 land；E1 IMPL 可立即派；風險 中（main_health_emitters.rs 共用區 + 新 PG batch query 複雜度）；E2 重點 3 點：(a) PG query string 對齊 spec §2 + §3.2 (b) cache update_batch 不破 100 SM key 鏈 (c) main_health_emitters.rs line 441 log literal 同步 update

---

## §10 Cross-References

- Spec：`srv/docs/execution_plan/2026-05-23--sprint5_strategy_quality_wireup_design.md`
- Parent PM sign-off：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_first_live_carryover_pm_phase_3e_signoff.md` §4.3.1
- Sprint 2 IMPL：`srv/rust/openclaw_engine/src/health/domains/strategy_quality.rs`（1580 LOC）
- Wave A pattern：`srv/rust/openclaw_engine/src/health/domains/risk_envelope_probe_impl.rs`（959 LOC）
- Wave B wire-up：`srv/rust/openclaw_engine/src/main_health_emitters.rs`（652 LOC）
- M-1 SSOT：`srv/docs/architecture/singleton-registry.md`
- 16 原則 skill：`srv/.claude/skills/16-root-principles-checklist/SKILL.md`

---

**PA DESIGN DONE**

*OpenClaw / Arcane Equilibrium — Sprint 5+ §4.3.1 P1 — 0 IMPL / 0 sub-agent / 0 commit*
