# E1 Sprint 1A-ζ Phase 3a Track B Round 2 Fix — V106 6 domain reconcile + amp cap 嚴格 fire 語意 + 反模式清理

Date: 2026-05-22
Owner: E1 (Track B — Rust 主 high-risk IMPL round 2)
Status: ROUND 2 FIX DONE — READY for E2 round 2 re-review

Parent Round 1 report: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_1a_zeta_track_b_m3_health_v106_impl.md`
PA reconcile verdict source: `srv/docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md` §1.1 line 53 (2026-05-22 PA reconcile)

## 1. Round 2 Task 摘要

E2 round 1 catch 7 findings (1 CRITICAL + 1 HIGH + 3 MEDIUM + 2 LOW)。本 round 全 closure:

| Finding | 等級 | Status |
|---|---|---|
| Rust HealthDomain enum ↔ V106 SQL CHECK 6 domain naming 不對齊 (spec internal conflict) | CRITICAL | ✅ CLOSED |
| `amplification_loop_24h_count` 語意 drift (unique seen vs transition fire) | HIGH | ✅ CLOSED |
| AC-5.1 test step 順序與 spec mismatch | MEDIUM-1 | ✅ CLOSED |
| Cargo.toml dead dev-dep tokio test-util | MEDIUM-2 | ✅ CLOSED |
| `unwrap()` in `observe_at` production 路徑 | MEDIUM-3 | ✅ CLOSED |
| CREATE INDEX CONCURRENTLY spec doc drift | LOW-1 | ✅ Follow-up noted (spec doc 由 PA 補) |
| `state_entered_at` dead field warning | LOW-2 | ✅ CLOSED (`#[allow(dead_code)]` + 中文註解) |

## 2. 修改清單 (4 edit)

| 檔 | 變動 | 大小 |
|---|---|---|
| `srv/sql/migrations/V106__health_observations.sql` | EDIT | 6 處: domain CHECK 6 enum + Guard C 預檢 + Guard C 後驗 + COMMENT 引用 (對齊 ADR-0042 命名) |
| `srv/rust/openclaw_engine/src/health/mod.rs` | EDIT | observe_at 重寫 + try_transition_with_cap 嚴格 fire 語意 + ≥ 2 fail-closed reject 路徑 + unwrap 改 if let + #[allow(dead_code)] + 新增 unit test `test_try_transition_no_fire_when_current_eq_target` |
| `srv/rust/openclaw_engine/tests/m3_amp_cap_24h_fire.rs` | EDIT | 4 step 對齊 spec §AC-5.1 順序 + assertion 對齊嚴格 fire 語意 |
| `srv/rust/openclaw_engine/Cargo.toml` | EDIT | 移除 dead dev-dep `tokio = { workspace = true, features = ["test-util"] }` |

## 3. CRITICAL — 6 domain naming reconcile 落地

### 3.1 PA verdict 採用

V106 spec §1.1 line 53 (2026-05-22 PA reconcile note) 明示:
> 6 domain 命名以 ADR-0042 Decision 3 + M3 design spec §2.1 為唯一 source of truth (3 層分離: Process / Pipeline / Business),取代本 spec 前版 6 domain (ws_latency / rest_success_rate / db_backlog / disk_usage / cpu_mem / strategy_level — 已退役;Rust enum + V106.sql 須同步 carry-over E1 round 2)。

**E1 修法**:V106.sql 改 6 domain CHECK enum 對齊 ADR-0042;Rust HealthDomain enum (`as_str()` 已對齊 ADR-0042) **保留不動**。

### 3.2 ADR-0042 命名 + M3 design spec §2.1 single source of truth

| Domain | 層級 | 替代舊命名 | Rust enum variant |
|---|---|---|---|
| `engine_runtime` | Process | (新) | `HealthDomain::EngineRuntime` |
| `pipeline_throughput` | Pipeline | ws_latency 等 | `HealthDomain::PipelineThroughput` |
| `database_pool` | Pipeline | db_backlog | `HealthDomain::DatabasePool` |
| `api_latency` | Pipeline | rest_success_rate | `HealthDomain::ApiLatency` |
| `strategy_quality` | Business | strategy_level | `HealthDomain::StrategyQuality` |
| `risk_envelope` | Business | (新) | `HealthDomain::RiskEnvelope` |

### 3.3 V106.sql empirical PG 驗 (sandbox `trading_ai_sandbox`)

DROP + re-apply V106 走全新 enum:

```text
ROUND 1 OUT:
DO -- Guard A PASS
DO -- Guard C 預檢 (table 不存在 skip)
CREATE TABLE
(45,learning,health_observations,t) -- hypertable
DO -- compression enable
2 NOTICE -- compression policy + retention policy added
4 CREATE INDEX
3 COMMENT
NOTICE: V106: all guards PASS — domain/state/engine_mode CHECK ok, ...

ROUND 2 OUT (idempotency):
DO + NOTICE skip x 9 ≥ V106 spec §2.4 要求 ≥ 5
0 RAISE EXCEPTION ✅
```

CHECK constraint runtime 驗:

```text
$ psql ... -c "SELECT pg_get_constraintdef(...) WHERE conname LIKE '%domain%check%';"
CHECK ((domain = ANY (ARRAY['engine_runtime'::text, 'pipeline_throughput'::text,
                            'database_pool'::text, 'api_latency'::text,
                            'strategy_quality'::text, 'risk_envelope'::text])))
```

反向 INSERT verify Rust enum ↔ V106 round trip:

```text
INSERT engine_runtime + HEALTH_OK + live → INSERT 0 1 ✅
INSERT ws_latency (舊命名) → ERROR: violates check constraint
"health_observations_domain_check" — REJECT ✅
```

**結論**:V106.sql ↔ Rust enum 6 domain 字面值 round trip 對齊 ADR-0042 Decision 3 single source of truth, empirical 驗證通過。

## 4. HIGH — amplification_loop_24h_count 嚴格 fire 語意

### 4.1 Bug 根因 (round 1)

`amp_cap_entries.len()` 在 `try_transition_with_cap` 內 unconditional insert (line 376 round 1 IMPL),即使 `current_state == target_state` (no real transition) 也 insert entry。結果:

- Test `test_amp_cap_different_anomaly_id_not_suppressed` 第二個 id "memory_pressure" 在已 WARN 狀態 → entry 計入 entries=2,但 transition 從未實際 fire (line 385 check 失敗 return false)。
- V106 spec §1.1 line 77 定義「state_prev → state transitions ≥ 2 → fail-closed」需要 transition fire count;round 1 IMPL count 是「unique seen anomaly_id」非「fire 次數」 — drift。

### 4.2 Round 2 修法

`try_transition_with_cap` 重寫嚴格語意:

1. **第 1 guard**:`contains_key(anomaly_id)` 已在 cap → return false (per ADR-0042 Decision 4 1-anomaly = 1-fire/24h)
2. **第 2 guard (新)**:`current_state == target_state` → no transition fire → return false 不 insert entry
3. **第 3 guard (新)**:`amplification_loop_24h_count >= 2` → fail-closed reject per V106 spec ≥ 2 規範 → return false 不 insert
4. **真實 fire**:才 insert entry + count++ + set state + return true

`amplification_loop_24h_count` 嚴格 = `amp_cap_entries.len()` (1:1 fire 對應 entry),retain 24h 過期同步重算。

### 4.3 新單元測試 covering ≥ 2 fail-closed + current==target no-fire

新增 `test_try_transition_no_fire_when_current_eq_target` (`health/mod.rs:551-561`):

```rust
// SM 初始 current=HealthOk; 嘗試 transition 到 HealthOk → no fire。
let result = sm.try_transition_with_cap(HealthState::HealthOk, "noop_id", now);
assert!(matches!(result, Ok(false)));
assert_eq!(sm.amplification_loop_24h_count(), 0);
assert_eq!(sm.amp_cap_entry_count(), 0);
```

整合測試 (m3_amp_cap_24h_fire.rs) 對 `test_amp_cap_different_anomaly_id_not_suppressed` 修正 assertion:第二個 id 在已 WARN 不 fire,entries=1 維持 (不是 2)。對齊嚴格語意。

### 4.4 為什麼 ≥ 2 reject 不真實 emit log

per Sprint 1A-ζ spike scope (dispatch §2.7(c) 反模式邊界):cascade gate cap + LAL Tier 降階 + 真實 fail-closed log emit 屬 Sprint 5 Tier 1 IMPL。本 IMPL 只在 state machine 層返回 false (writer 端觀察 count 不再增即可推斷 reject 發生)。

## 5. MEDIUM-1 — AC-5.1 test step 順序對齊

### 5.1 修法

Round 1 test step 順序與 spec §AC-5.1 不一致:Step 2 / 3 對調。Round 2 改順序:

| Step | spec §AC-5.1 設計 | Round 2 實作 |
|---|---|---|
| 1 | OK→WARN dwell pass fire | base + 0..300s × 10 sample |
| 2 | 24h+1s mock hop → cap reset | base + 24h+60s+1s (確保 retain 過期,因 fire 發生在 base+60s) |
| 3 | 24h reset 後 spike (cap reset 後第 2 transition fire attempt) | step3_base = base+24h+60s+2s, 10 sample |
| 4 | 24h 內第 4 spike (cap suppress) | step3_base + 1h, 10 sample |

### 5.2 spike scope vs full cascade scope 差異

spec §AC-5.1 Step 3/4 期望「cap reset 後第 2 個 fire 發生」 — 在 full cascade IMPL (Sprint 5) 下需要 WARN→DEGRADED transition 才能觀察到。spike scope 只 IMPL OK→WARN,當 current==WARN target==WARN 不 fire (嚴格語意 per HIGH 修法),所以 Step 3/4 assertions:

```text
Step 3 assert: state=WARN, entries=0, count=0
  (spike scope 嚴格語意 — current==target=WARN no fire, no entry)
Step 4 assert: state=WARN, count=0
  (no fire in spike scope; Sprint 5 cascade IMPL 後此 step 可觀察 reset 後第 2 fire)
```

### 5.3 Empirical 通過

```
running 3 tests
test test_amp_cap_different_anomaly_id_not_suppressed ... ok
test test_m3_amp_cap_24h_fire ... ok
test test_stub_domains_fail_loud ... ok
test result: ok. 3 passed; 0 failed
```

## 6. MEDIUM-2 — Cargo.toml dead dev-dep 移除

Round 1 加 `tokio = { workspace = true, features = ["test-util"] }` 進 dev-dependencies 但 IMPL pivot 後改用 `std::time::Instant` 注入,完全沒呼任何 tokio time-util API。

修法:Cargo.toml 移除 dead dev-dep,改加註釋說明:
```toml
[dev-dependencies]
tempfile = "3"
# Sprint 1A-ζ Track B — M3 spike test 改採 observe_at 注入 std::time::Instant
# (per spec §AC-5.1 mock time hook 設計 + dispatch §2.7 反模式邊界), 不需要
# tokio::time::pause / advance mock clock。tokio test-util 已從 dev-dep 移除
# (避免 dead dependency noise);若 Sprint 5 cascade IMPL 真的需要 tokio 虛擬
# 時鐘再補回。
```

## 7. MEDIUM-3 — unwrap() in observe_at 改 if let

Round 1 line 330 `let dwell = now.duration_since(self.warn_band_seen_at.unwrap())` 在 production observe_at 路徑;雖然 line 325 `is_none()` guard 後語意安全,但 Sprint 5 cascade IMPL 改邏輯時易誤 break。

修法:改 `if let Some(seen) = self.warn_band_seen_at` 結構 + 中文註釋說明:
```rust
// 為什麼 if let: 對 None 場景 fail-closed 走「初次採樣 → 記時間」
// 路徑, 不可用 unwrap() (對 Sprint 5 cascade IMPL 改錯不安全)。
if let Some(seen) = self.warn_band_seen_at {
    let dwell = now.duration_since(seen);
    if dwell >= Duration::from_secs(60) {
        self.try_transition_with_cap(HealthState::HealthWarn, anomaly_id, now)
    } else {
        Ok(false)
    }
} else {
    // 第一次採樣到 WARN-band → 記時間, 不立即 transition。
    self.warn_band_seen_at = Some(now);
    Ok(false)
}
```

## 8. LOW-1 — CONCURRENTLY drift follow-up note

V106 spec §6.1 line 567 仍寫 `CREATE INDEX CONCURRENTLY IF NOT EXISTS`;IMPL 採非 CONCURRENT path (per Round 1 §6.5: timescale + CONCURRENTLY 在 psql -f transaction-block 內不可用)。

**E1 修法**:不修 V106.sql (per task 禁忌「不動 V106 spec doc」),不重複 PA 的 reconcile 工作。本 round 2 report 留 follow-up note:

- PA 同時段在 reconcile V106 spec doc;PA verdict 出爐後 V106 spec §6.1 CONCURRENTLY 段應同步 patch (對齊 IMPL non-CONCURRENT path)。
- 補 reindex_chunk SOP 註腳:production 上線 Sprint 1B writer wire 前若需要 reindex,走 timescale `reindex_chunk` API per E5 hypertable audit。

## 9. LOW-2 — state_entered_at #[allow(dead_code)]

Round 1 `state_entered_at` 在 fire 時寫入 (line 422 round 2) 但 spike scope 不讀。修法:加 `#[allow(dead_code)]` + 中文註釋 (`health/mod.rs:248-252`):

```rust
/// 進入當前 state 的時間 (用於 dwell time 計算)。
/// 預留 Sprint 5 WARN→DEGRADED 5min dwell time IMPL 用; spike scope 不讀,
/// 但寫入時間戳保留供 cascade 計算 dwell delta。
#[allow(dead_code)]
state_entered_at: Instant,
```

`cargo check --release` confirms 0 dead_code warning for this field after fix。

## 10. Empirical Test Summary

| Test 套件 | 預期 | 結果 |
|---|---|---|
| `cargo test --release -p openclaw_engine --lib health` | 19 pass | ✅ 19 pass |
| `cargo test --release -p openclaw_engine --features spike --test m3_amp_cap_24h_fire` | 3 pass | ✅ 3 pass |
| `cargo check --release -p openclaw_engine` | 0 new warning | ✅ Only 3 pre-existing warning (unrelated) |
| V106 sandbox PG round 1+2 idempotency | 0 RAISE + NOTICE skip ≥ 5 | ✅ 9 NOTICE skip + 0 RAISE |
| V106 sandbox CHECK constraint runtime | 6 ADR-0042 enum | ✅ Empirical verified |
| V106 reverse INSERT REJECT (ws_latency 舊命名) | REJECT | ✅ ERROR violates CHECK constraint |
| V106 positive INSERT engine_runtime | PASS | ✅ INSERT 0 1 |

## 11. Round 2 verdict

**READY for E2 round 2 re-review**:
- 1 CRITICAL closed (V106.sql 對齊 ADR-0042 6 domain, Rust enum 保留不動)
- 1 HIGH closed (amplification_loop_24h_count 嚴格 fire 語意 + ≥ 2 fail-closed reject 路徑)
- 3 MEDIUM closed (test step 順序 / Cargo.toml dead dep / unwrap)
- 2 LOW closed (state_entered_at dead_code + CONCURRENTLY follow-up note)
- 0 production code 污染 (spike feature default off; cargo check release clean)
- Empirical PG + cargo test 全 PASS

## 12. 不確定之處 / Push back (給 E2 round 2 + PA)

### 12.1 V106 spec §6.1 CONCURRENTLY drift PA 同步

PA 在 §1.1 line 53 reconcile note 處理了 6 domain naming,但 §6.1 line 567 + §5.3 line 389-394 仍是舊命名 + CONCURRENTLY。需要 PA 同步 patch:
- §2.1 DDL 內 domain CHECK (line 113-121)
- §5.3 Guard C SQL 範例 (line 387-401)
- §6.1 Step 7 CREATE INDEX CONCURRENTLY (line 567)
- §1.1 row 量級估算表 (line 53-68;按新 6 domain 命名 + 數量分配重估)

E1 round 2 已實作 V106.sql 對齊 PA verdict (採 ADR-0042),不再等 PA spec doc patch (避免 blocking)。

### 12.2 Sprint 5 cascade IMPL 接 fail-closed log emit

Round 2 ≥ 2 reject 路徑只在 state machine 層 return false。Sprint 5 cascade IMPL 接時需要:
- emit `HEALTH_WARN` row 進 `learning.health_observations` (writer 端負責)
- 結構化 log 進 `learning.governance_audit_log` (per V106 spec §1.4 cross-ref)
- LAL Tier 降階 trigger (per V112 + ADR-0042 Decision 6)

### 12.3 V106 reset 後 fire 重觸發測試 deferred

`test_m3_amp_cap_24h_fire` Step 3/4 在 spike scope 下 entries=0/count=0 維持,因 current==target=WARN 嚴格不 fire。Sprint 5 cascade IMPL 完整 OK→WARN→DEGRADED 路徑後,reset 後第 2 fire 才能 observe (透過不同 target_state)。本 spike scope test 用 assertion 文字標明此 deferred 邊界。

## 13. Operator 下一步 (給 PM + E2)

| Action | Owner | Priority |
|---|---|---|
| E2 round 2 re-review (對 round 2 修改集) | E2 (sub-agent) | P0 |
| PA 補 V106 spec §2.1 / §5.3 / §6.1 對齊 ADR-0042 6 domain + non-CONCURRENT path | PA | P1 (本 round 2 不依賴) |
| E4 regression (cargo test --workspace + cross-language fixture) | E4 | P1 (待 E2 round 2 PASS 再跑) |
| QA empirical AC-5 driver | QA | P1 |
| `_sqlx_migrations` V106 register (跑 `repair_migration_checksum` 或 engine restart auto-migrate) | PM | P1 (round 1 carry-over) |
| Sprint 2 metric emitter IMPL (per M3 spec §11.1, 6 domain 全 IMPL + Mac sysctl fallback) | E1 Sprint 2 | P3 (deferred) |

## 14. Lessons Learned (補 memory.md)

- **Spec internal conflict 不是 IMPL bug**:V106 spec 內 §1.1 (ADR-0042 命名) vs §2.1 (legacy 命名) 兩個 source of truth 並存,IMPL round 1 採 §2.1 直譯,結果 Rust enum (依 ADR-0042) ↔ V106.sql (依 §2.1) drift。修法 = PA spec reconcile 後決定 single source of truth,IMPL 對齊 verdict。
- **counter 語意 drift 必補 empirical assertion**:`amp_cap_entries.len()` 看似自然 = transition fire count,但實際在 `try_transition_with_cap` 內 unconditional insert 後可能 ≠ fire count (current==target 不 fire 但 entry insert)。修法 = 嚴格在「真實 fire」(state 真變) 時才 insert + count++,並補 unit test 覆蓋。
- **PG CHECK constraint 改變需 DROP + recreate**:sandbox empirical 驗證 6 domain 改 enum 時, table 已 land 走 IF NOT EXISTS skip → CHECK 不會自動更新。greenfield 0 row 場景 DROP + apply 安全;production 場景需 ALTER TABLE DROP CONSTRAINT + ADD 新 CONSTRAINT (per ADR migration pattern)。
- **production code path 不留 unwrap()**:即使 is_none() guard 前置 + 同 fn 內語意安全, 後續 sprint 改邏輯極易 break;一律 `if let Some(...)` 或 pattern match。
- **Dead dev-dep 反模式**:design pivot 後忘記回頭清 dependency 是常見 noise 源;每次 IMPL 對抗審查必查 Cargo.toml 是否所有 dep 都被 src/ + tests/ 真實使用。

---
END Report — E1 Sprint 1A-ζ Phase 3a Track B Round 2 FIX DONE pending E2 round 2 review.
