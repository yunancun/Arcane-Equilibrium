# PA Sprint 2 Wave 1 M3 spec amend — 2026-05-22

E2 round 1 Track B (REJECT 2 HIGH + 2 MEDIUM) + Track C (REJECT 2 HIGH + 3 MEDIUM) 中 4 finding 需 PA spec amend / clarify。本 task PA single-thread 1-1.5 hr land。

## 1. 4 amend 拍板

### 1.1 HIGH-2「持續 2min」semantic clarify — **Path A 採納 + 補齊**

決議：spec line 102 `pipeline_throughput` WARN band literal「tick rate < 1/sec/symbol 持續 2min」是 v5.7 carry-over 直覺敘述，**真規範值 = §3.3 line 165 SM OK→WARN dwell 60s**；spike Track B IMPL hardcode 60s dwell 是對齊 SSOT。

修法：
- 不改 SM dwell 數值（保持 60s）
- M3 design spec §2.3 ladder line 102 改為「即時 classify band」語意（metric=DEGRADED 等樣本）
- 新增 §2.3.1 明示「metric classify ≠ SM band dwell；measurement window ≠ dwell time」區分
- §3.3 SM dwell 60s 不變（已是 SSOT）

E2 round 1 reject root cause = 把「metric classify 持續 2min」與「SM dwell 60s」混為一談 — clarify 後 IMPL = spec literal 對齊。

### 1.2 HIGH-1 heartbeat_lag CRITICAL band — **spec SSOT 確認**（不 amend）

spec line 102 `pipeline_throughput` CRITICAL band literal = 「WS dropout > 60s OR ipc p99 > 50ms」= **heartbeat_lag_ms > 60_000 ms 即時 fire CRITICAL classify**。

Track B IMPL `classify_pipeline_throughput_heartbeat_lag_ms` 把 60-120s 改 DEGRADED、120+s 才 CRITICAL = unilateral spec drift；E1 round 2 必 revert 對齊 60_000 ms threshold。

spec patch action：
- M3 design spec §2.3.1 加 inline 明示「heartbeat_lag_ms > 60_000 ms → metric classify=CRITICAL 即時 fire，不走 dwell 累積；SM ladder 仍走標準升階 dwell」
- Sprint 2 design spec §4.3 `classify_band_from_mean` 函數示例補 `ws_heartbeat_lag_ms` arm `> 60_000.0 → HealthCritical`

### 1.3 MEDIUM-1 B drift+signal threshold — **threshold 補 spec**（IMPL 數值合理保留）

決議：Track B IMPL 數值（drift 0/1-2/3+ = OK/WARN/DEGRADED；signal_rate ≥0.5/0.1-0.5/<0.1 = OK/WARN/DEGRADED）合理但是 unilateral spec drift（spec line 102 ladder 無此 2 metric threshold 寫死）；解決方案 = **spec amend 補進 ladder + 引用 §1.78 metric_name list**。

修法：
- M3 design spec §2.3 line 102 ladder 補 2 metric threshold：
  - `ws_subscription_drift_count`: OK = 0 / WARN = 1-2 / DEGRADED ≥ 3
  - `strategy_signal_rate_per_min`: OK ≥ 0.5 / WARN 0.1-0.5 / DEGRADED < 0.1
- Sprint 2 design spec §4.3 classify_band_from_mean 函數示例補 2 metric arm
- Sprint 2 dispatch packet §3.4 Track B AC-2.2 sub-step 明示 4 ladder

Rationale 引：5 strategy × 25 symbol 正常 signal_rate baseline ~0.1-1.0/min（per project_5agent_runtime_state）；drift 0 為設計常態，1-2 為訂閱重建期短暫，3+ 為 ws_client 結構性失敗。

### 1.4 MEDIUM-1 C `pool_max_conn` 設計 drift — **Path A 採納（5th column）**

決議：spec §3.2 加入 `pool_max_conn: u32` 為第 5 column；保留 raw `pool_active_conn` for telemetry；`classify_database_pool_active_conn(active, max)` 內部計算 ratio = active/max。

修法：
- Sprint 2 design spec §3.2 `DatabasePoolSample` struct 改 4 field → 5 field（含 `pg_pool_max_conn: u32`）
- spec 注釋明示「max_conn 由 caller 注入（DatabaseConfig::pool_max_connections）；sqlx PgPool 未暴露 max accessor，emitter 不可強行 hack」
- Sprint 2 dispatch packet §4.4 Track C AC-2.3 sub-step 明示 5th column 規範

對齊 Track C IMPL 既有設計（caller 注入 pool_max_conn / classify 計算 ratio）；不需 IMPL 改動。

### 1.5 MEDIUM-3 C disconnected fail-closed semantics — **Path A 採納（OK band + cascade catch）**

決議：spec §3.2 明確「PG disconnected = OK band fail-closed」+ rationale + cascade catch reference；對齊 V106 spec §1.1 fail-closed 設計 + Track A scaffold sample_error 一致 pattern。

修法：
- M3 design spec §2.3.2 新增 database_pool disconnected handling 段落
- 列 4 條 rationale：
  1. V106 spec §1.1 fail-closed 設計一致
  2. Track A scaffold sample_error pattern 對稱
  3. PG 真實斷線由 cascade event 接（engine_runtime PID dead / pipeline_throughput WS dropout / 既有 5-gate kill）
  4. 「失敗默認收縮」（§二 原則 6）語意是「不主動升 cascade 造成更激進副作用」
- disconnected 不靜默：evidence_json 寫 `{"pool_status": "disconnected"}` 留 audit trail
- 拒 Path B（emitter 加 `db_pool.is_available()` check + disconnected 走獨立 CRITICAL classify）：避兩 domain 重複 emit CRITICAL（per ADR-0042 反模式 + V106 amplification cap）

對齊 Track C IMPL 既有 fail-closed 邏輯（max=0 → ratio 不計算 → OK band）。

## 2. Spec patches applied

### 2.1 M3 design spec (`docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md`)

| 位置 | 變更 |
|---|---|
| §2.3 line 102 `pipeline_throughput` row | OK 補 `ws_subscription_drift_count = 0 + strategy_signal_rate_per_min ≥ 0.5`；WARN 補 `drift 1-2 OR signal_rate 0.1-0.5`；DEGRADED 補 `drift ≥ 3 OR signal_rate < 0.1`；CRITICAL 改為「heartbeat_lag_ms > 60_000 (WS dropout > 60s) OR ipc p99 > 50ms」明示 literal threshold |
| §2.3 line 103 `database_pool` row | OK 補 `active/max < 80%`；WARN 補 `active/max 80-95%`；DEGRADED 補 `active/max > 95%`；CRITICAL 改為「pool disconnected → fail-closed OK band」+ ref §2.3.2 |
| §2.3.1 新節 | 「metric classify vs SM band dwell 區分」+ measurement window vs dwell time 引 §4.3；明示「持續 2min」literal 為非規範性 v5.7 carry-over；真規範 = §3.3 line 165 60s；heartbeat_lag_ms > 60_000 即時 fire 規範 |
| §2.3.2 新節 | 「database_pool disconnected handling — fail-closed OK band」+ 4 rationale + disconnected evidence_json audit trail + 拒 Path B 理由 |

### 2.2 Sprint 2 design spec (`docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md`)

| 位置 | 變更 |
|---|---|
| §0 TL;DR | 加「2026-05-22 E2 round 1 reject 4 amend land」bullet + amend 摘要 |
| §3.2 `DatabasePoolSample` struct | 4 field → 5 field 加 `pg_pool_max_conn: u32`；補 70-word 設計理由（caller 注入 / sqlx max accessor 未暴露 / fail-closed OK band ref §2.3.2） |
| §4.3 `classify_band_from_mean` 示例 | 補 5 pipeline_throughput metric arm + heartbeat_lag_ms 即時 CRITICAL 對齊 + 補注釋區分 metric classify 與 SM dwell |
| §5.1 spike Track B 升級點「已 IMPL」 | OK→WARN dwell 60s 對齊 SSOT 註腳（指 §3.3 line 165 + 2026-05-22 HIGH-2 clarify） |

### 2.3 Sprint 2 dispatch packet (`docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md`)

| 位置 | 變更 |
|---|---|
| §0 TL;DR | 加「2026-05-22 E2 round 1 Track B+C 4 amend land」bullet |
| §3.4 Track B AC sub-step | 新增 AC-2.1 heartbeat_lag CRITICAL classify + AC-2.2 drift+signal_rate ladder（引 spec amend reference） |
| §4.4 Track C AC sub-step | 新增 AC-2.3 pool_max_conn 5th column + AC-2.4 disconnected fail-closed OK band（引 spec amend reference） |

### 2.4 ADR-0042 — **不 amend**

ADR-0042 governance authority 層面 dwell 語意未變（仍 §3.3 60s + 抽象「持續 dwell time」）；本 amend 屬 M3 design spec § level 細化（4 metric ladder 補 + measurement window vs dwell time 區分 clarify + disconnected handling 規範化），不觸 ADR governance scope。

## 3. E1 round 2 unblock 條件

4 finding 修法明確：

| Finding | E1 round 2 IMPL 修法 |
|---|---|
| HIGH-2「持續 2min」semantic | Track B IMPL **不改 dwell**（60s SSOT），但 ladder comment 引 spec §2.3.1 reference；E1 round 2 仅 doc 註釋對齊 |
| HIGH-1 heartbeat CRITICAL | Track B `classify_pipeline_throughput_heartbeat_lag_ms` revert：`> 60_000 → HealthCritical`（不是 120_000）；3 test case 對應更新（45_000/60_000=WARN；70_000=CRITICAL；120_000=CRITICAL）|
| MEDIUM-1 B drift+signal ladder | Track B IMPL **不改數值**（與 spec amend 一致）；comment 補引 spec §2.3 line 102 amend reference |
| MEDIUM-1 C pool_max_conn | Track C IMPL **不改 struct**（與 spec amend 一致）；comment 補引 spec §3.2 amend reference |
| MEDIUM-3 C disconnected | Track C IMPL **不改 fail-closed 邏輯**（與 spec amend 一致）；補 evidence_json `{"pool_status": "disconnected"}` 寫入路徑（Sprint 2 D3 cascade reject log emit minimal pattern） |

E1 round 2 並行修：Track B 1 finding（HIGH-1 revert）+ Track C 1 finding（evidence_json 補寫）；其他 finding 為 spec amend 對齊 doc/comment，不需 logic 改動。

E1 round 2 不阻：Track A scaffold 已 land；Track B+C 各自 scope 不互依；可並行修。

## 4. E2 round 2 re-review readiness

E2 round 2 reviewer 比對 E1 round 2 IMPL 與本 amend：

| 檢點 | 期望 |
|---|---|
| Track B heartbeat_lag_ms classify literal | `> 60_000 → CRITICAL` 對齊 spec §2.3 line 102 + §2.3.1 |
| Track B drift+signal_rate classify literal | 與 spec §2.3 line 102 amend ladder 1:1 對齊 |
| Track B SM OK→WARN dwell | 仍 60s（spec §3.3 line 165 SSOT）；spike Track B 既有 IMPL 不變 |
| Track C `DatabasePoolSample` field count | 5 field（含 `pool_max_conn`）|
| Track C `classify_database_pool_active_conn` signature | `(active: u32, pool_max: u32) -> HealthState`；max=0 → fail-closed OK |
| Track C disconnected sample | `evidence_json={"pool_status": "disconnected"}` 寫入路徑加 |
| spec literal 引用 | E1 round 2 IMPL comment 引 spec §2.3.1 / §2.3.2 / §2.3 line 102 reference |

E2 round 2 verdict 條件：4 finding 全 PASS（HIGH-1 revert + drift/signal_rate ladder 對齊 + pool_max_conn 5 field + disconnected fail-closed evidence_json）+ AC-1a in-memory proxy test 不退。

## 5. ADR-0042 amend 觸發否

**不觸 ADR amend**：

- 「持續 2min」literal clarify 屬 M3 design spec §2.3 ladder 細化，非 ADR governance scope 變更
- heartbeat_lag CRITICAL > 60_000 ms 即時 fire 是 spec literal 重申，非 dwell semantic 改變
- drift+signal_rate ladder 補進 ladder 是 M3 spec §1.78 metric_name list 已預埋 metric 的 threshold 落地
- pool_max_conn 5th column 是 Sprint 2 IMPL detail design
- disconnected fail-closed OK band 是 V106 spec §1.1 fail-closed 既有設計的 Sprint 2 IMPL 細化（V106 spec §1.1 已是 SSOT）

ADR-0042 保持 v1.0（per 2026-05-21 land）；本 4 amend 全 M3 design spec § level patch。

## 6. 風險評級

- **低**：純 doc edit；不觸 Rust IMPL / 不觸 V### SQL / 不改硬邊界（live_execution_allowed / max_retries / system_mode 全未碰）
- **副作用**：E1 round 2 + E2 round 2 依本 amend 對齊；Track A scaffold + V106 schema 不受影響
- **16 根原則合規**（per `srv/docs/decisions/DOC-01_..._V2.md` §5.1-§5.16 + 16-root-principles-checklist skill）：
  - 原則 1 (single write entry V106 不變) ✅
  - 原則 4 (策略不繞風控；M3 emitter 不繞 Guardian) ✅
  - 原則 5 (生存 > 利潤；disconnected fail-closed OK 不誤升 CRITICAL 避激進 cascade 副作用) ✅
  - 原則 6 (失敗默認收縮；disconnected fail-closed OK + cascade catch separation) ✅
  - 原則 8 (audit reconstructable；disconnected evidence_json audit trail) ✅
  - 原則 13 (cost 感知；ratio classify 一 sample 一次計算不額外 hot path) ✅

DOC-08 §12 安全不變量 9 條無觸碰；硬邊界 0 觸碰。

## 7. 下一步

1. PM 收本 amend report → 確認 4 amend 路徑符合期望
2. PM 派 E1 round 2 並行修 Track B + Track C（per §3 E1 round 2 unblock 條件）
3. E1 round 2 IMPL 完成後派 E2 round 2 re-review（per §4 E2 round 2 readiness 檢點）
4. 若 E2 round 2 PASS → Wave 1 scaffold sign-off + Wave 2 Track D/E/F dispatch readiness 開閘

---

## Files touched

- `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md`（2 edits — §2.3 line 102 ladder + §2.3.1 / §2.3.2 兩新節）
- `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md`（3 edits — §0 TL;DR + §3.2 DatabasePoolSample + §4.3 classify 示例 + §5.1 spike 升級 註腳）
- `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md`（3 edits — §0 TL;DR + §3.4 Track B AC + §4.4 Track C AC）

未觸碰：
- `srv/docs/adr/0042-m3-health-monitoring.md`（不 amend，dwell semantic 不變）
- `srv/rust/openclaw_engine/src/health/domains/pipeline_throughput.rs`（E1 round 2 修；本 PA task scope 不改 Rust IMPL）
- `srv/rust/openclaw_engine/src/health/domains/database_pool.rs`（E1 round 2 補 evidence_json；本 PA task scope 不改 Rust IMPL）
- `srv/rust/openclaw_engine/src/health/mod.rs`（Track A scaffold 不受影響）
- `srv/sql/migrations/V106__health_observations.sql`（schema 不變）
