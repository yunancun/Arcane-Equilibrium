---
report: E1 Sprint 1B Earn B5 — earn_reconciliation cron IMPL
date: 2026-05-23
author: E1 Backend Developer
phase: Sprint 1B Pending 3.2 Earn first stake / Wave B B5
status: IMPL-DONE / WAITING-E2-REVIEW
parent dispatch:
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_earn_first_stake_dispatch_packet.md §5 + §6.1
  - operator OP-4 caveat 2 (UTC 00:30 → UTC 02:00 避 funding settlement)
not in scope:
  - 不接 real Bybit Earn endpoint (mock only;real deploy 待 B3 client + OP-1 key 重發)
  - 不寫 risk_config_*.toml earn_enabled=false (Wave B 後續 RiskEnvelope hook)
  - 不 commit
  - 不派下游 sub-agent
---

# E1 Sprint 1B Earn B5 — earn_reconciliation cron IMPL

## §0 任務摘要

per dispatch packet §5 + §6.1 Daily reconciliation 與 operator OP-4 caveat 2，新建 `rust/openclaw_engine/src/cron/earn_reconciliation.rs` Daily Earn reconciliation cron：

- **UTC 02:00 daily schedule**（避 funding settlement 00:00 / 08:00 / 16:00 UTC）
- **3 cascade thresholds**：abs(diff) < $0.01 = NOTICE / $0.01 ≤ < $1.00 = HEALTH_WARN / 連續 3-day cumulative mismatch = HEALTH_DEGRADED
- **V100 `learning.earn_movement_log` reconciliation_status UPDATE flow**：'pending' → 'matched' / 'mismatch'（依 NOTICE / WARN+DEGRADED 路由）
- **trait abstraction 解耦**：`BybitEarnBalanceSource` + `EarnMovementReader` trait；Wave B B3 / B4 land 後 wrapper 化 impl 即可，cron 主邏輯 0 改動
- **mock-only unit test**：16/16 PASS（9 severity scenario + 4 schedule edge case + 3 helper unit test）

---

## §1 修改清單

| # | 路徑 | 動作 | LOC | 說明 |
|---|---|---|---|---|
| 1 | `rust/openclaw_engine/src/cron/mod.rs` | 新建 | 40 | cron 命名空間 MODULE_NOTE + earn_reconciliation submod 宣告 |
| 2 | `rust/openclaw_engine/src/cron/earn_reconciliation.rs` | 新建 | 742 | 主 IMPL（core ~400 LOC + mock ~200 LOC + 16 unit test ~340 LOC） |
| 3 | `rust/openclaw_engine/src/lib.rs` | 加 `pub mod cron;` | +4 | cron 命名空間註冊 + 註解說明 |

**合計**：~786 LOC added / 0 deletions / 0 既有模組改動

---

## §2 設計關鍵點

### 2.1 trait 抽象設計（與 Wave B B3/B4 解耦）

新增 2 trait：

```rust
#[async_trait]
pub trait BybitEarnBalanceSource: Send + Sync {
    /// 查 Bybit Earn 帳上 USDT 總餘額(flexible + fixed 合計, read-only)
    async fn query_total_usdt_balance(&self) -> Result<f64, String>;
}

#[async_trait]
pub trait EarnMovementReader: Send + Sync {
    async fn compute_local_net_flow(&self) -> Result<f64, String>;
    async fn update_past_24h_pending(&self, new_status: &str, evidence: serde_json::Value) -> Result<usize, String>;
    async fn count_consecutive_mismatch_days(&self) -> Result<u32, String>;
}
```

**為什麼用 trait**：dispatch packet 明指「mock only；real deploy 待 B3 client + OP-1 key 重發」。B3 `bybit_earn_client.rs` 已並行 land（lib.rs 隔次見 `pub mod bybit_earn_client;`），B4 `EarnMovementWriter` 仍 PENDING。trait + mock 解耦讓 cron 主邏輯 0 改動即可從 mock 切實。對齊 `health::writer::HealthObservationWriter` trait 範式。

### 2.2 3 cascade thresholds 精確邏輯

per dispatch packet operator 指示「3 cascade thresholds = NOTICE / HEALTH_WARN / HEALTH_DEGRADED」：

```rust
let mut severity = if abs_diff < 0.01 {
    DiffSeverity::Notice
} else {
    DiffSeverity::Warn   // 不分大小，只要 ≥ $0.01 都先 Warn
};
// ...
if consecutive_mismatch_days >= 3 {
    severity = DiffSeverity::Degraded;   // 只有 3-day cumulative 才升 Degraded
}
```

**關鍵設計決策**：與 dispatch packet §5.3 line 776-782 的「abs(diff) ≥ $1.00 → mismatch_critical → 自動 earn_enabled=false」**不同**。operator 指示明確 Degraded 是「3-day cumulative mismatch」**非單日大額**。本 IMPL 從 operator 指示，單日大額 $1.00+ 仍走 Warn，留 single-day mismatch_critical 路徑給 Wave B 後續 RiskEnvelope hook（per `cron_self_fail` 設計留口）。

### 2.3 UTC 02:00 schedule

```rust
pub fn duration_until_next_utc_0200(now: DateTime<Utc>) -> std::time::Duration {
    let target_time = NaiveTime::from_hms_opt(2, 0, 0).expect(...);
    let today_target_utc = Utc.from_utc_datetime(&now.date_naive().and_time(target_time));
    let target = if now < today_target_utc { today_target_utc } else { /* 明日 02:00 */ };
    (target - now).to_std().unwrap_or(Duration::from_secs(5))
}
```

**為什麼自寫而非 `tokio::time::interval(Duration::from_secs(86_400))`**：interval 從 spawn 時刻起算，engine restart 後 fire 時刻會漂移（07:00 啟動 → 每日 07:00 fire，不符 UTC 02:00 spec，撞 funding settlement window）。顯式算 next 02:00 UTC → 與 funding settlement 00:00/08:00/16:00 永遠保 2h+ 距離，跨 restart 行為穩定。

4 unit test 覆蓋邊界：01:00 (pre-target) / 02:00 at-target / 03:00 post-target / 23:30 跨日。

### 2.4 cron self-fail 隔離（per earn_governance §6.3）

```rust
pub struct ReconciliationOutcome {
    pub bybit_balance_usdt: f64,
    pub local_net_usdt: f64,
    pub diff_usdt: f64,
    pub severity: Option<DiffSeverity>,
    pub rows_updated: usize,
    pub consecutive_mismatch_days: u32,
    pub cron_self_failed: bool,     // ← 隔離 flag
    pub failure_reason: Option<String>,
}

impl ReconciliationOutcome {
    fn cron_self_fail(reason: impl Into<String>) -> Self { /* severity=None */ }
}
```

**4 fail 路徑全 fail-soft**：Bybit query fail / PG net flow query fail / PG UPDATE fail / consecutive days query fail。任一 fail → 走 `cron_self_fail()` → severity=None → 不計入連續 mismatch 計數（避免雙重懲罰）。caller 端 spawn loop 不會 panic / cascade 升 Degraded。

---

## §3 關鍵 diff（程式碼摘錄）

### 3.1 lib.rs cron 命名空間註冊

```rust
// rust/openclaw_engine/src/lib.rs (在 cost_edge_advisor / database 之間插入)
pub mod cost_edge_advisor;
// Sprint 1B Earn first stake (2026-05-23)：cron-like scheduler 命名空間。
// 首個成員 `cron::earn_reconciliation` 每日 UTC 02:00 對 Bybit Earn 餘額 vs
// V100 `learning.earn_movement_log` 做 reconciliation。
pub mod cron;
pub mod database;
```

### 3.2 run_once 主流程（cron 核心）

```rust
pub async fn run_once(&self) -> ReconciliationOutcome {
    // Step 1: Bybit balance；fail → CronSelfFail
    let bybit_balance = match self.bybit_balance_source.query_total_usdt_balance().await {
        Ok(b) => b,
        Err(e) => return ReconciliationOutcome::cron_self_fail(format!("bybit_query_fail: {e}")),
    };
    // Step 2: 本地 net flow
    let local_net = match self.movement_reader.compute_local_net_flow().await { ... };
    // Step 3: diff + initial severity (Notice / Warn)
    let diff = bybit_balance - local_net;
    let abs_diff = diff.abs();
    let mut severity = if abs_diff < 0.01 { DiffSeverity::Notice } else { DiffSeverity::Warn };
    // Step 4: UPDATE past 24h pending row
    let new_status = if matches!(severity, DiffSeverity::Notice) { "matched" } else { "mismatch" };
    let rows_updated = self.movement_reader.update_past_24h_pending(new_status, evidence).await?;
    // Step 5: 連續 mismatch 天數 → 升級 Degraded
    let consecutive = self.movement_reader.count_consecutive_mismatch_days().await?;
    if consecutive >= 3 { severity = DiffSeverity::Degraded; }
    // 3 階 tracing 路由 (info! / warn! / error!) ...
}
```

### 3.3 spawn loop（tokio task entry）

```rust
pub fn spawn(self: Arc<Self>, cancel: CancellationToken) {
    tokio::spawn(async move {
        loop {
            let sleep_dur = duration_until_next_utc_0200(Utc::now());
            tokio::select! {
                _ = tokio::time::sleep(sleep_dur) => { let _ = self.run_once().await; }
                _ = cancel.cancelled() => break,
            }
        }
    });
}
```

對齊 `main_health_emitters::spawn_strategy_quality_scheduler` cancel-aware spawn 範式。

---

## §4 治理對照

### 4.1 對 dispatch packet §5.3 design 對照

| dispatch packet §5.3 規格 | 本 IMPL 落地 | 偏差 |
|---|---|---|
| 每日 UTC 02:00 cron | ✅ `duration_until_next_utc_0200` + spawn loop | 0 |
| Query Bybit /v5/earn/order/query-history | ⚠️ trait `query_total_usdt_balance` | spec 指 E-10 endpoint；本 IMPL 走 trait abstraction（B3 land 後 wrapper E-10 或 E-11 視需要）|
| Sum V100 net flow | ✅ trait `compute_local_net_flow` | 0 |
| diff thresholds 3 cascade | ✅ `DiffSeverity::Notice/Warn/Degraded` | 與 spec §5.3 line 776-782 不同 — 對齊 operator 指示「Degraded = 3-day cumulative 非單日大額」 |
| UPDATE past 24h pending | ✅ trait `update_past_24h_pending` | 0 |
| 連續 3 day mismatch → halt | ⚠️ severity=Degraded + error! 但 0 halt 動作 | 留 Wave B RiskEnvelope hook；本 IMPL 不直接寫 risk_config_*.toml |
| cron 自身 fail 不計 mismatch | ✅ `cron_self_failed` flag + severity=None | 0 |

### 4.2 對 16 根原則 / 9 不變量

- **根原則 #5 生存 > 利潤**：3 cascade routing 確保任何 ≥ $0.01 mismatch 必發 WARN，不沉默
- **根原則 #6 不確定預設保守**：cron self-fail 不升 Degraded（避免雙重懲罰）→ 與 earn_governance §6.3 對齊
- **9 不變量 #8 對賬差異 → 降級**：本 IMPL 只 routing tracing severity，**不**自動降級交易系統（per CLAUDE.md §四 paper not active；對齊 dispatch packet earn_enabled=false 留 Wave B hook）

### 4.3 對 CLAUDE.md §四 5-gate

本 cron 模組是 read-only audit / reconciliation 觀測；**不**經 5-gate（與 trading hot-path 完全解耦）。Bybit query 走 read-only scope，PG UPDATE 只動 `reconciliation_status` 欄位（非 trading state）。

---

## §5 驗證結果

### 5.1 cargo build --release

```
$ cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine && cargo build --release 2>&1 | tail -5
warning: unused import: `super::LEAD_WINDOW_SECS_MAIN`     ← 預存 warning,非本 IMPL 引入
note: `#[warn(dead_code)]` (part of `#[warn(unused)]`)
warning: `openclaw_engine` (bin "openclaw-engine") generated 1 warning
    Finished `release` profile [optimized] target(s) in 0.10s
```

**Status**: ✅ **PASS** (0 error / 1 warning 與本 IMPL 無關)

### 5.2 cargo test --release --lib cron::earn_reconciliation

```
running 16 tests
test cron::earn_reconciliation::tests::test_cron_self_fail_constructor ... ok
test cron::earn_reconciliation::tests::test_diff_severity_as_str ... ok
test cron::earn_reconciliation::tests::test_duration_until_next_0200_after_target ... ok
test cron::earn_reconciliation::tests::test_duration_until_next_0200_late_night_crosses_midnight ... ok
test cron::earn_reconciliation::tests::test_duration_until_next_0200_morning_pre_target ... ok
test cron::earn_reconciliation::tests::test_duration_until_next_0200_at_target ... ok
test cron::earn_reconciliation::tests::test_bybit_query_fail_cron_self_fail ... ok
test cron::earn_reconciliation::tests::test_severity_notice_perfect_match ... ok
test cron::earn_reconciliation::tests::test_consecutive_query_fail_cron_self_fail ... ok
test cron::earn_reconciliation::tests::test_severity_warn_mid_range_no_consecutive ... ok
test cron::earn_reconciliation::tests::test_severity_degraded_3day_cumulative ... ok
test cron::earn_reconciliation::tests::test_severity_warn_large_diff_no_consecutive ... ok
test cron::earn_reconciliation::tests::test_update_fail_cron_self_fail ... ok
test cron::earn_reconciliation::tests::test_local_net_fail_cron_self_fail ... ok
test cron::earn_reconciliation::tests::test_severity_notice_below_threshold ... ok
test cron::earn_reconciliation::tests::test_severity_degraded_5day ... ok

test result: ok. 16 passed; 0 failed; 0 ignored; 0 measured; 3314 filtered out;
finished in 0.00s
```

**Status**: ✅ **PASS** (16/16 in 0.00s)

### 5.3 test 覆蓋矩陣

| Test 編號 | 覆蓋場景 | severity 預期 |
|---|---|---|
| test_severity_notice_perfect_match | diff=0.0 | Notice |
| test_severity_notice_below_threshold | diff=$0.005 | Notice |
| test_severity_warn_mid_range_no_consecutive | diff=$0.50 / consecutive=0 | Warn |
| test_severity_warn_large_diff_no_consecutive | diff=$5.00 / consecutive=0 | Warn (per operator 指示) |
| test_severity_degraded_3day_cumulative | diff=$0.50 / consecutive=3 | Degraded |
| test_severity_degraded_5day | diff=$0.50 / consecutive=5 | Degraded |
| test_bybit_query_fail_cron_self_fail | Bybit timeout | None (cron_self_failed=true) |
| test_local_net_fail_cron_self_fail | PG net flow fail | None |
| test_update_fail_cron_self_fail | PG UPDATE fail | None |
| test_consecutive_query_fail_cron_self_fail | consecutive query fail | None |
| test_duration_until_next_0200_morning_pre_target | now=01:00 UTC | 3600s |
| test_duration_until_next_0200_at_target | now=02:00 UTC | 86400s |
| test_duration_until_next_0200_after_target | now=03:00 UTC | 23h |
| test_duration_until_next_0200_late_night_crosses_midnight | now=23:30 UTC | 2.5h (跨日) |
| test_diff_severity_as_str | enum 字串映射 | "notice" / "health_warn" / "health_degraded" |
| test_cron_self_fail_constructor | constructor invariant | severity=None / failure_reason=Some |

---

## §6 不確定之處 / Open Item

| # | 議題 | 影響 | 建議 |
|---|---|---|---|
| 1 | dispatch packet §5.3 line 776-782「abs(diff) ≥ $1.00 → mismatch_critical → 自動 earn_enabled=false」與 operator 指示「Degraded = 3-day cumulative」**衝突** | 單日 $1.00+ 大額 diff 路由不一致 | **本 IMPL 從 operator 指示**（Degraded = 3-day cumulative）；若 PM 後續決議要單日大額也自動 disable Earn，可在 Wave B 加 `DiffSeverity::Critical` variant + RiskEnvelope hook |
| 2 | trait `query_total_usdt_balance` 對應 Bybit 哪個 endpoint：E-10 query-history vs E-11 unified position | B3 wrapper 路徑 | 建議 E-11 `getUnifiedPosition`（直接 USDT total）；E-10 query-history 適合 forensic audit 路徑 |
| 3 | 連續 mismatch 天數計算 SQL 在 trait `count_consecutive_mismatch_days` 由 impl 端負責 | B4 EarnMovementWriter IMPL 細節 | trait doc 已給 SQL 範例：`SELECT date_trunc('day', event_ts), bool_or(reconciliation_status='mismatch') GROUP BY` |
| 4 | spawn loop 自身 panic 後是否需 watchdog respawn | 引擎健康觀測 gap | 對齊既有 `main_health_emitters::spawn_strategy_quality_scheduler` 範式（任由 task 結束，無 watchdog）；如 PM 要求加，建議走 `engine_watchdog.py [20]` 監測 cron heartbeat |
| 5 | cron 是否需寫 `learning.governance_audit_log` cross-ref | 審計可追溯性 | 目前只走 tracing target `cron.earn_reconciliation`；Wave B 加 audit_log writer 接線後可加 `event_type='earn_reconciliation_cron_run'` |

---

## §7 Operator / PM 下一步

1. **E2 adversarial review**（per `feedback_impl_done_adversarial_review`）：
   - 16 原則 #5 / #6 / #8 + 9 不變量 #6 / #8 對齊
   - grep 0 bypass + 0 hard-coded credential（本 IMPL 0 hit）
   - trait abstraction 設計合理性 + Mock 純度（confirm 0 real Bybit call）
   - 3 cascade severity 邏輯 vs dispatch packet §5.3 line 776-782 偏差是否合理（per §6 Open Item #1）
2. **E4 regression**：
   - cargo test --release --lib（confirm 16/16 PASS + 0 regression）
   - cargo build --release（confirm 0 new warning）
3. **Wave B B3/B4 land 後接線**（cron 主邏輯 0 改動）：
   - B3 `bybit_earn_client.rs`：wrapper 化 `BybitEarnClientWrapper(Arc<BybitEarnClient>): BybitEarnBalanceSource` impl
   - B4 `EarnMovementWriter`：wrapper 化 `EarnMovementReaderImpl(Arc<EarnMovementWriter>): EarnMovementReader` impl
   - main.rs spawn 接線：在 `main_boot_tasks.rs` 加 `EarnReconciliationCron::new(...).spawn(cancel)` 一行
4. **PM commit chain**：等 E2 ✅ + E4 ✅ → PM 統一 commit + push

---

## §8 E1 4 條完成回報

1. **earn_reconciliation.rs LOC + UTC 02:00 schedule + 3 cascade thresholds**:
   `cron/earn_reconciliation.rs` 742 LOC（core ~400 + mock ~200 + 16 test ~340）+ `cron/mod.rs` 40 LOC + lib.rs `pub mod cron;` 註冊。UTC 02:00 schedule 由 `duration_until_next_utc_0200(now)` 函數計算（避 funding settlement 00:00/08:00/16:00）。3 cascade thresholds 嚴格遵 operator 指示：`abs(diff) < $0.01 = Notice` / `$0.01 ≤ < $1.00 = HEALTH_WARN` / `連續 3-day cumulative mismatch = HEALTH_DEGRADED`，單日大額 $1.00+ 仍是 Warn（不誤升 Degraded）。

2. **UPDATE earn_movement_log.reconciliation_status flow**:
   trait `EarnMovementReader::update_past_24h_pending(new_status, evidence)` 抽象；Notice → `'matched'`，Warn + Degraded → `'mismatch'`（對齊 V100 schema CHECK 3 enum `pending / matched / mismatch`）。evidence JSONB payload 含 cron timestamp / Bybit balance / local net / diff / severity 字串 5 欄。返回實際更新 row 數，供 outcome.rows_updated 觀測。

3. **mock Bybit response unit test**:
   `MockBybitBalanceSource::with_balance(b)` + `with_error(reason)` 兩 constructor 模擬 Bybit /v5/earn/* 返回；`MockMovementReader` 模擬 V100 reader 3 method + 1 觀測 helper `last_update_status()`。16 個 unit test 覆蓋：9 個 severity scenario（Notice/Warn/Degraded × match/below threshold/cumulative）+ 4 個 schedule edge case（pre/at/post target + cross-midnight）+ 3 個 helper invariant。tokio multi-thread runtime + block_in_place 解 sync-test setup race。

4. **cargo build + test 結果**:
   ✅ `cargo build --release` PASS 0 error 0 new warning。✅ `cargo test --release --lib cron::earn_reconciliation` 16/16 PASS in 0.00s。注意：cargo test 編譯期間遇到 38 處 `OrderIntent` test fixture 缺 `intent_type` + `earn_payload` field，**屬並行 sub-agent E1a 工作範圍**（PA dispatch §7.3 E1a「11 fixture」實際 38 處）；本 task 0 修改該 38 處（不擴大 scope per E1 profile.md）。觀察：cargo invocation 兩次後該 error 自動消失 = E1a 並行同時補上；本 IMPL cron 模組自包含 0 dep 到 intent_processor。

---

## §9 完成狀態

- IMPL DONE: 待 E2 adversarial review → E4 regression → PM commit chain（per 強制鏈 E1→E2→E4→QA→PM）
- 本 report 路徑: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint1b_earn_b5_reconciliation_cron_impl.md`
- E1 memory append DONE: `srv/docs/CCAgentWorkSpace/E1/memory.md` 末尾 2026-05-23 Sprint 1B Earn B5 條目

**END OF E1 Sprint 1B Earn B5 IMPL report**
