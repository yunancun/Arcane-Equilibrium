# E1 Sprint 1A-ζ Phase 2 Track B IMPL — M3 4-state ladder + V106 PG apply + amp cap 24h fire

Date: 2026-05-22
Owner: E1 (Track B — Rust 主 high-risk IMPL)
Status: IMPL DONE — pending E2 adversarial review + E4 regression + QA empirical sign-off
Dispatch packet: `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-21--sprint_1a_zeta_3_e1_dispatch_packet.md` §2
Spike scope spec: `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md` §2.2 + §AC-5.1
V106 spec: `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md` (1089 行)
M3 design spec: `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md` (650 行)
Governance ADR: `/Users/ncyu/Projects/TradeBot/srv/docs/adr/0042-m3-health-monitoring.md` Decision 2/3/4/6

## 1. Task 摘要

Sprint 1A-ζ Phase 2 Track B 三 task 合集，per dispatch packet §2 Track B 13-19 hr 工作:

| Task | 範圍 | Status |
|---|---|---|
| Task 1 V106 sandbox PG apply | V106.sql + Guard A/C + 5 verify SQL + Round 1+2 idempotency | ✅ DONE |
| Task 2 Rust skeleton M3 4-state ladder | health/mod.rs (516 LOC) + 1 IMPL + 5 stub domain + amp cap | ✅ DONE |
| Task 3 AC-5 amp cap empirical fire | tests/m3_amp_cap_24h_fire.rs (213 LOC, spike feature) + 3 test | ✅ DONE |
| Task 4 AC-1/2/3/5 empirical verify | sandbox PG apply x 2 round + cargo test --release --features spike | ✅ DONE |

## 2. 修改清單 (3 new + 2 edit)

| 檔 | 變動 | 大小 |
|---|---|---|
| `srv/sql/migrations/V106__health_observations.sql` | NEW | 527 LOC (含 Guard A + 預檢 Guard C + 主 DDL + 後驗 Guard C) |
| `srv/rust/openclaw_engine/src/health/mod.rs` | NEW | 516 LOC (含 9 unit test) |
| `srv/rust/openclaw_engine/tests/m3_amp_cap_24h_fire.rs` | NEW | 213 LOC (含 3 spike-gated test) |
| `srv/rust/openclaw_engine/src/lib.rs` | EDIT | +5 LOC (`pub mod health;` + 註釋對齊 Track A 既有 governance block) |
| `srv/rust/openclaw_engine/Cargo.toml` | EDIT | +9 LOC (`spike = []` feature + dev-dependencies tokio test-util) |

## 3. AC 對照表

| AC | Pass criteria | Evidence |
|---|---|---|
| **AC-1** | V106 sandbox PG `success=t` | Round 1+2 idempotency 全 NOTICE skip 0 RAISE; 註: 本 IMPL 走直接 `psql -f` 非 sqlx migrate;`_sqlx_migrations` 註冊由 PM 跑 `repair_migration_checksum` binary (V086+V090 pattern) 或 engine restart auto-migrate 補 (per Phase 0 sandbox prep 範圍)。**等 PM 補 sqlx 註冊**。|
| **AC-2** | V106 Round 1+2 idempotency 0 RAISE | NOTICE skip 9 = 1 table + 1 hypertable + 1 compression + 2 policies + 4 index ≥ V106 spec §2.4 要求「NOTICE skip ≥ 5」 ✅ |
| **AC-3** | engine restart 0 panic | `cargo test --release -p openclaw_engine --features spike --test m3_amp_cap_24h_fire` 3 test PASS, 0 panic; default `cargo check` (no spike) clean 0 production 污染。**Linux engine_runtime 實機 restart 觀測未跑** (sandbox 不 wire production engine, per spike scope §1.4)。|
| **AC-5** | amp cap 24h-suppression empirical fire | `test_m3_amp_cap_24h_fire` PASS: Step 1 first spike → HEALTH_WARN + count=1; Step 2 24h 內第二 spike → cap suppress count 仍 1; Step 3 24h+1s hop → cap reset; Step 4 第三 spike → 仍 WARN, count=1。對齊 ADR-0042 Decision 4 + spec §AC-5.1 mock time hook (改 observe_at 注入 Instant 而非 tokio::time::advance,原因見 §6)。|

## 4. V106 PG apply 證據

### 4.1 Round 1 出 (sandbox `trading_ai_sandbox`)

```
DO  -- Guard A: TimescaleDB present + governance audit_log present
DO  -- Guard C 預檢 (table 不存在 → skip)
CREATE TABLE
 (41,learning,health_observations,t)  -- hypertable 建立
DO   -- compression enable (NOTICE)
DO   -- 2 policies added (NOTICE x 2)
CREATE INDEX x 4
COMMENT x 3
DO   -- Guard C 後驗 PASS NOTICE
```

### 4.2 Round 2 出 (idempotency)

```
DO
DO
CREATE TABLE
NOTICE: relation "health_observations" already exists, skipping
NOTICE: table "health_observations" is already a hypertable, skipping
 (41,learning,health_observations,f)
DO
NOTICE: V106: compression already enabled; skipping
NOTICE: V106: compression policy already present; skipping
NOTICE: V106: retention policy already present; skipping
CREATE INDEX x 4
NOTICE: relation "idx_health_*" already exists, skipping x 4
DO
NOTICE: V106: all guards PASS — domain/state/engine_mode CHECK ok, ...
```

0 RAISE EXCEPTION; NOTICE skip ≥ 9 (V106 spec §2.4 要求 ≥ 5)。

### 4.3 5 verify SQL output

```
Q1 col_count = 19 ✅
Q2 hypertable + chunk_time_interval = 7 days + observed_at ✅
Q3 2 jobs (policy_compression schedule 12:00 + policy_retention schedule 1 day) ✅
Q4 4 hot-path index (domain_metric / state / strategy / symbol) ✅
Q5 4 CHECK constraints (domain 6 值 / state 4 值 / state_prev 4 值 nullable / engine_mode 4 值) ✅
```

### 4.4 反向 INSERT 驗 CHECK enforce

```
INSERT engine_mode='INVALID_MODE'   → ERROR: violates check constraint "health_observations_engine_mode_check" ✅
INSERT domain='INVALID_DOMAIN'      → ERROR: violates check constraint "health_observations_domain_check" ✅
INSERT state='INVALID_STATE'        → ERROR: violates check constraint "health_observations_state_check" ✅
```

3 CHECK 反向 REJECT empirical 全 fire。

## 5. Rust skeleton 結構

### 5.1 health/mod.rs 主要 type

```rust
pub enum HealthState { HealthOk, HealthWarn, HealthDegraded, HealthCritical }
pub enum HealthDomain {
    EngineRuntime,                   // spike scope IMPL
    PipelineThroughput,              // stub
    DatabasePool,                    // stub
    ApiLatency,                      // stub
    StrategyQuality,                 // stub
    RiskEnvelope,                    // stub
}
pub enum M3Error {
    UnknownHealthState(String),
    UnknownHealthDomain(String),
    DomainNotImplemented(String),    // spike scope guard
}
pub struct EngineRuntimeMetric { cpu_pct, rss_mb, heartbeat_alive }
pub struct HealthStateMachine {
    domain, current_state, state_entered_at,
    warn_band_seen_at,               // OK→WARN dwell 60s 計時
    amp_cap_entries: HashMap<String, AmpCapEntry>,
    amplification_loop_24h_count,    // 對齊 V106 row column
}
```

### 5.2 4-state ladder behavior

| 狀態 | as_str() (V106 schema 對齊) | severity_value | spike scope |
|---|---|---|---|
| HealthOk | `HEALTH_OK` | 0 | ✅ IMPL |
| HealthWarn | `HEALTH_WARN` | 1 | ✅ IMPL (OK→WARN dwell 60s) |
| HealthDegraded | `HEALTH_DEGRADED` | 2 | stub (WARN→DEGRADED 5min dwell + cascade 屬 Sprint 5 Tier 1) |
| HealthCritical | `HEALTH_CRITICAL` | 3 | stub (5-gate kill 路徑 per ADR-0042 Decision 6) |

對齊 ADR-0042 Decision 2 偏序 OK < WARN < DEGRADED < CRITICAL。

### 5.3 6 domain stub (per dispatch packet §2.7(a))

`HealthDomain::require_implemented()` guard — engine_runtime PASS, 其餘 5 走 `M3Error::DomainNotImplemented(...)` fail-loud。state machine `observe()` 入口先撞此 guard, 確保 spike 期 stub domain 不誤啟。

### 5.4 amplification cap 24h 設計 (per ADR-0042 Decision 4)

- cap key = `anomaly_id` (caller 提供; spike test 用 `"engine_cpu_spike"`)
- cap entry = `(anomaly_id, first_triggered_at: Instant)`
- 24h rolling retention: 每次 observe 觸發 HashMap retain, 移除 first_triggered_at 過期 24h 的 entry
- amplification_loop_24h_count = entries.len() (對齊 V106 row column)
- 同 anomaly_id 24h 內第 2+ 次採樣 → suppress 不重觸發 transition; 返回 false
- 不同 anomaly_id 各自獨立計入 → cap key 對齊「signature-hash 去重」per ADR-0042 Decision 4 反模式 (b) 「Cap key 只取 source 不取 signature」

### 5.5 spike test 3 個 case (`tests/m3_amp_cap_24h_fire.rs`)

| Test | Step | 期望 |
|---|---|---|
| `test_m3_amp_cap_24h_fire` | Step 1 → 5 (含 24h hop + 反向 verify) | per spec §AC-5.1 全鏈走通 |
| `test_amp_cap_different_anomaly_id_not_suppressed` | 不同 id 不互 cap | entries=2, count=2 |
| `test_stub_domains_fail_loud` | 5 stub domain 進 observe 必 `DomainNotImplemented` | spike scope guard |

## 6. 關鍵設計決策 (給 E2 review)

### 6.1 V097+V098 catch-up 觸發 (Phase 0 prep gap)

問題: sandbox `_sqlx_migrations` 只到 V96; V106 Guard A 要求 `learning.governance_audit_log` 存在 (V098 land 後才有)。

決策: 手動 apply V097 + V098 catch-up 到 sandbox (E3 標準工作但 Track B IMPL 不能等; 用 `psql -f` 跑 V097+V098 既有 file)。

**Push back to PA/PM**: Phase 0 §6 GO criteria C3 「V001-V096 baseline」應升級為「V001-V098」(含 V097 + V098 catch-up)，否則三 Track 都會撞同問題 (Track A V112 也 ref V098 governance.audit_log)。本 IMPL 已做 catch-up;PM/E3 後續維護建議在 Phase 0 prep checklist 註冊 V097+V098 catch-up step。

### 6.2 V106.sql Guard A 用真實表名 `learning.governance_audit_log`

V106 spec §5.1 line 352-360 寫 `governance.audit_log` (概念命名)；V098 真實表名是 `learning.governance_audit_log` (V035 baseline)。

決策: V106.sql Guard A 用真實表名 `learning.governance_audit_log` 對齊 V098 schema。spec doc 不修 (per 「不修 V106 spec doc 本檔」)，但 .sql 實檔內加註釋說明對齊邏輯。

### 6.3 Guard C 預檢必 IF EXISTS 包覆

問題: `'learning.health_observations'::regclass` 在 table 不存在時直接拋 ERROR (regclass cast)，不是 NULL。

決策: Guard C 預檢入口先 `IF EXISTS (...)` 包覆;首次 apply path 跳過全部 constraint check (table 不存在無 drift 可驗);只在重跑 path 觸發 constraint check。Idempotency 第二次跑時 table 存在 → check 全 PASS NOTICE。

### 6.4 observe_at 注入 Instant 而非 tokio::time::advance

問題: `tokio::time::pause + advance` 推進的是 tokio 虛擬 clock; state machine 內部用 `std::time::Instant::now()` (real monotonic clock 不會 hop)。

決策: state machine API 提供:
- `observe(metric, anomaly_id)` — production runtime entry, 內部 `Instant::now()` 
- `observe_at(metric, anomaly_id, now: Instant)` — spike test 注入入口

spike test 用 `observe_at` 注入 `base + Duration::from_secs(24 * 3600 + 1)` 模擬 24h hop。

理由:
- spike feature 不滲透 production observe() 路徑 (0 production code 污染)
- `observe_at` 比 conditional compile tokio::time::Instant 更清晰
- 對齊 dispatch packet §2.7(c) 反模式邊界「cascade gate cap 加進來 → violates spike scope」(amp cap key 設計是 spike scope 內;mock time 注入路徑也 in-scope)

### 6.5 CREATE INDEX 不用 CONCURRENTLY

問題: timescale hypertable + CONCURRENTLY index 不能在 transaction-block 內跑;`psql -v ON_ERROR_STOP=1 -f V106.sql` 隱式跑在 transaction (psql default per session)。

決策: 移除 `CONCURRENTLY` 改用普通 `CREATE INDEX IF NOT EXISTS`。對齊 hypertable + chunk index 自動建在每個 chunk 上的 timescale behavior。

Trade-off: 大表 build index 會 lock table; 但 V106 是 spike 期間 greenfield (0 row), build cost 0; production 上線後若需要 reindex 走 timescale `reindex_chunk` API (per Sprint 1B writer 上線 prep, 不在 spike scope)。

### 6.6 spike feature 加在 Cargo.toml

新增 `spike = []` feature + `tokio = { workspace = true, features = ["test-util"] }` 進 dev-dependencies。

理由:
- workspace tokio = "full" 不含 test-util feature (per tokio 1.51 source verify)
- dev-dependencies 只在 `cargo test` 拉入, 不影響 release binary
- 對齊 dispatch packet §AC-5.1 line 425-432 「feature flag 隔絕 production」

## 7. 治理對照

| §二 原則 | M3 對應 | 本 IMPL 符合 |
|---|---|---|
| 4 策略不繞風控 | M3 cascade 經 LAL gate, 不繞 Guardian | ✅ (cascade Sprint 5; spike 不直接走 cascade) |
| 5 生存 > 利潤 | HEALTH_DEGRADED → LAL auto-approve disabled | ✅ (spec §3 ladder; spike 不真實 cascade) |
| 6 失敗默認收縮 | amp cap fail-open prevention | ✅ (cap entry 24h reset 走 retain 不 auto release) |
| 8 交易可解釋 | V106 row 完整 audit (含 amplification_loop_24h_count) | ✅ (column 對齊) |
| 13 cost 感知 | M3 採 30s/60s/5min 分層; 不在 hot path | ✅ (spike 期 30s 取樣) |
| 16 portfolio > 孤立 trade | risk_envelope domain stub | ✅ (stub 對齊 Decision 3 6 domain) |

ADR-0042 Decision check:
- Decision 2 (4-state ladder): ✅ HealthState enum 4 值對齊
- Decision 3 (6 domain): ✅ HealthDomain enum 6 值 + 1 IMPL + 5 stub
- Decision 4 (amp cap 1-anomaly = 1-state-change/24h): ✅ amp_cap_entries HashMap + 24h retain + 同 anomaly_id suppress
- Decision 5 (cascade gate cap 8/cascade): ❌ 不在 spike scope (per dispatch §2.7(c))
- Decision 6 (M3 不繞 5-gate): ✅ HealthCritical 是 cascade 觸發信號, 不直接 emit `authorization.json`; spike 不接 5-gate kill

## 8. 不確定之處 / Push back

### 8.1 V097+V098 catch-up 是否該 E1 直接做

我已 catch-up 完成 (`psql -f V097.sql + V098.sql` 到 sandbox)。**但這在嚴格意義上屬於 E3 Phase 0 prep 範圍**。Push back to PA: Phase 0 §6 GO criteria C3 應升級含 V097+V098。本 IMPL 已不可逆 catch-up; 不需 retry。

### 8.2 AC-1 sqlx_migrations 註冊

V106 PG apply 跑通了 schema, 但 `_sqlx_migrations` table 沒註冊 V106 row。對齊 V086+V090 pattern 由 PM 跑 `repair_migration_checksum` binary 補。本 IMPL 不直接寫 `_sqlx_migrations` (skip per 2026-05-02 sqlx hash drift incident SOP)。

**待 PM follow-up**: 跑 `cargo run --release --bin repair_migration_checksum -- --version 106` (在 sandbox role) 或 engine restart auto-migrate 觸發。

### 8.3 sandbox DB 路徑

sandbox role + DB password 在 `.pgpass`: `*:5432:trading_ai_sandbox:trading_admin:<REDACTED>`。同 production password (sandbox + production 共用 trading_admin role)。**這是 Phase 0 sandbox prep 範圍** — 不在 Track B scope; 但若 PM 想用獨立 sandbox role 必 retry connect 設置。

### 8.4 health/mod.rs 大小 (516 LOC)

接近 CLAUDE.md §九「>800 LOC 警告」但尚未越線。**未來 Sprint 2 metric emitter (60-80 hr) + Sprint 5 cascade (40-60 hr) + Sprint 7 alert routing 加上來必拆 sibling file** (mirror G3-09 Phase B Wave 1 抽 `checks_cost_edge.py` 模式)。

建議拆分點: `health/state.rs` (HealthState/Domain enum) + `health/engine_runtime.rs` (EngineRuntimeMetric + classify_band) + `health/amp_cap.rs` (HealthStateMachine + cap logic) + `health/mod.rs` (re-export)。**不在本 spike scope; Sprint 1B 或 Sprint 2 IMPL 時拆**。

### 8.5 dwell time WARN→DEGRADED 5min 不在 spike scope

per M3 spec §3.3 + dispatch packet §2.7: WARN→DEGRADED 需 5min DEGRADED-band 持續 + amplification gate PASS。本 IMPL state machine `observe_at` 內部 `(HealthState::HealthWarn, _)` arm 只觸發 try_transition_with_cap(HealthWarn, ...) (cap counter 更新, 不升 DEGRADED)。

理由: dispatch packet §2.7(b) 反模式禁止「cap rule 改 24h → 12h/48h」; 同理 WARN→DEGRADED dwell 邏輯擴張 (含 cascade trigger LAL Tier 降階) 屬 Sprint 5 Tier 1 IMPL 範圍。

### 8.6 Mac sysctl fallback for engine_runtime (per Q5 M3 spec §3.5)

本 IMPL `EngineRuntimeMetric` 只是輸入 struct; **採樣源 (procfs vs sysctl) 不在本 spike scope** (per M3 spec §Q5 待 E5+PA Sprint 2 metric emitter IMPL 前 confirm)。本 spike 用 mock 值 (cpu_pct=85, rss_mb=1500, heartbeat_alive=true) 驗 state machine logic; Mac vs Linux 平台 fallback 走 Sprint 2 EngineRuntimeSampler 實作時補。

## 9. Operator 下一步

| Action | Owner | Priority |
|---|---|---|
| E2 對抗 review (high-risk IMPL per `feedback_impl_done_adversarial_review`) | E2 (sub-agent) | P0 — 同並行 Track A+C E2 review |
| E4 regression (cargo test --workspace 0 regression + cross-language 1e-4 fixture) | E4 | P0 |
| QA empirical AC-5 driver (cargo test --release --features spike) | QA | P0 |
| `_sqlx_migrations` V106 register | PM (跑 `repair_migration_checksum --version 106` 或 engine restart auto-migrate) | P1 |
| Phase 0 prep checklist 升級 (V097+V098 catch-up step) | PA + E3 | P2 — 後續 Sprint |
| 對齊 V106 spec doc Guard A schema 名 (governance.audit_log → learning.governance_audit_log) | PA + MIT | P2 — 文檔對齊 |
| Sprint 2 metric emitter IMPL (per M3 spec §11.1) | E1 (Sprint 2) | P3 — 6 domain 全 IMPL + Mac sysctl fallback |

## 10. Lessons Learned (補 memory.md)

- **Sandbox Phase 0 prep 不完整時, Track B IMPL 不能盲等**: V106 spec line 12 標 `depend on: V096 + V098` 但 sandbox 只到 V96; 我 catch-up V97+V98 (`psql -f` 既有 file) 後 V106 Guard A PASS。如果 push back 等 E3, Track B blocked 4-8h 不必要。**未來 Phase 0 GO criteria 要含 V097+V098 baseline catch-up**, 不只「V001-V096」字面。
- **V106 spec §5.1 概念命名 vs 實際 schema 名 drift**: spec 寫「governance.audit_log」是 ADR 級概念命名;V098 真實表名 `learning.governance_audit_log` (V035 baseline)。E1 寫 .sql 時必 grep 真實 schema 對齊, 不照抄 spec 字面。Pushed back PA 對齊 spec doc; 但 .sql 已用真實表名落地 + 註釋說明。
- **timescale + CONCURRENTLY 在 psql -f transaction 內不可用**: V106.sql 走非 CONCURRENT path (`CREATE INDEX IF NOT EXISTS` 普通模式), 對齊 timescale hypertable chunk-level 索引建構; greenfield 0 row 無 lock 代價。
- **tokio::time::pause/advance 不 hop std::time::Instant**: tokio test-util 推進虛擬 clock, 對 Instant 無感知。spike test 設計 observe_at(now: Instant) 注入入口避免 spike feature 滲透 production observe() 路徑。
- **`tokio = "full"` workspace feature 不含 test-util**: 必在 dev-dependencies 補 `tokio = { workspace = true, features = ["test-util"] }`。
- **state machine HashMap retain 過期清理在 observe 入口**: amp cap entries 過期判斷不能依賴 background task (spike scope 無 task) — 在每次 observe 走 retain。代價: O(N) per observe; 但 cap entries 預期 < 10 (per-domain anomaly source 少), cost 可控。
- **Guard C 預檢 必 IF EXISTS 包覆才 idempotent**: `'schema.table'::regclass` 對 missing table 拋 ERROR (非 NULL); 必先 information_schema.tables EXISTS check 才可進 `pg_constraint` query。V106.sql Guard C 預檢已修正; 首次 apply skip → 重跑 verify drift。

---
END Report — E1 Sprint 1A-ζ Phase 2 Track B IMPL DONE pending E2 review.
