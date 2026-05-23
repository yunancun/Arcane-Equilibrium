//! Sprint 1B Earn first stake — 每日 UTC 02:00 reconciliation cron。
//!
//! MODULE_NOTE
//! 模塊用途：
//!   per dispatch packet §6.1 Daily reconciliation + earn_governance §6 +
//!   operator OP-4 caveat 2 (UTC 00:30 → UTC 02:00 避 funding settlement)：
//!   每日 UTC 02:00 對 Bybit Earn 已報餘額 vs V100 `learning.earn_movement_log`
//!   本地 net flow 做差額比對，依 3 階 cascade thresholds 路由：
//!     - abs(diff) <  $0.01      → NOTICE log only
//!     - $0.01 ≤ abs(diff) < $1.00 → HEALTH_WARN routing
//!     - 連續 3-day cumulative   → HEALTH_DEGRADED + alert
//!   並把 past 24h `reconciliation_status='pending'` 的 row UPDATE 成
//!   `matched` / `mismatch`。
//!
//! 主要類 / 函數：
//!   - `EarnReconciliationCron`         : cron 主類；持 Bybit 餘額源 + V100
//!                                        movement_log reader trait object。
//!   - `EarnReconciliationCron::run_once`: 一次性 reconcile 入口；測試與
//!                                        scheduler tick 都走它，與時間源解耦。
//!   - `EarnReconciliationCron::run_loop`: tokio task 入口；每日 UTC 02:00 fire
//!                                        一次（cancellation-aware）。
//!   - `ReconciliationOutcome`         : run_once 結果 struct（含 diff /
//!                                        severity / rows_updated / 連續天數）。
//!   - `DiffSeverity` enum             : 3 階 cascade (Notice / Warn / Degraded)。
//!   - `BybitEarnBalanceSource` trait  : `query_total_usdt_balance` 抽象；
//!                                        prod 期 Wave B B3 land 後接
//!                                        bybit_earn_client.rs；本模組
//!                                        提供 `MockBybitBalanceSource`。
//!   - `EarnMovementReader` trait      : V100 movement_log 讀寫抽象；prod 期
//!                                        Wave B B4 land 後接 EarnMovementWriter；
//!                                        本模組提供 `MockMovementReader`。
//!
//! 依賴：
//!   - tokio interval / select / cancellation_token (對齊 main_health_emitters
//!     spawn_*_scheduler 範式)
//!   - chrono UTC + NaiveDate 計算下一次 02:00 wake-up 與 day 維度連續 mismatch
//!   - async-trait (對齊 health::writer::HealthObservationWriter trait 範式)
//!   - tracing (NOTICE / WARN / DEGRADED 三階輸出走 target
//!     "cron.earn_reconciliation")
//!
//! 硬邊界：
//!   - 不接 real Bybit Earn endpoint：Wave B B3 land 後才把
//!     `BybitEarnBalanceSource` impl 從 mock 切實 client。
//!   - 不直接寫 risk_config_*.toml `earn_enabled=false`：HEALTH_DEGRADED 只發
//!     `tracing::error!` + V100 `reconciliation_status='mismatch'`，不觸動
//!     RiskEnvelope（Wave B 後續 hook）。
//!   - reconciliation 自身 fail（Bybit timeout / PG error）→ outcome=CronSelfFail
//!     不計連續 mismatch 計數（per earn_governance §6.3 避免雙重懲罰）。
//!   - 全模組 0 `unwrap()` / `panic!()` 於非 test path；caller fail-soft。
//!   - 浮點精度：USDT 餘額用 f64 + (diff_abs - threshold).abs() 嚴格邊界，
//!     對齊 health writer NUMERIC(18,8) cast 範式（precision 1e-8 內 USDT
//!     對 $0.01 / $1.00 threshold 不會邊界誤判）。

use std::sync::Arc;

use async_trait::async_trait;
use chrono::{DateTime, Duration as ChronoDuration, NaiveDate, NaiveTime, TimeZone, Utc};
use tokio::sync::Mutex;
use tokio_util::sync::CancellationToken;
use tracing::{error, info, warn};

/// 對賬差額嚴重度 — 3 階 cascade (per dispatch packet operator 指示)。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DiffSeverity {
    /// abs(diff) < $0.01 — NOTICE log only。
    Notice,
    /// $0.01 ≤ abs(diff) < $1.00 — HEALTH_WARN routing。
    Warn,
    /// 連續 ≥ 3 day cumulative mismatch — HEALTH_DEGRADED + alert。
    /// 為什麼用「累積 3 day」而非「單日 diff ≥ $1.00」: dispatch packet operator
    /// 指示明確「3-day cumulative mismatch」是 DEGRADED；single day 大額 diff
    /// 由 Wave B HEALTH_DEGRADED routing rule 上層處理，本 cron 不越權。
    Degraded,
}

impl DiffSeverity {
    pub fn as_str(self) -> &'static str {
        match self {
            DiffSeverity::Notice => "notice",
            DiffSeverity::Warn => "health_warn",
            DiffSeverity::Degraded => "health_degraded",
        }
    }
}

/// reconciliation 一次 run_once 的結果。
#[derive(Debug, Clone, PartialEq)]
pub struct ReconciliationOutcome {
    /// Bybit 端 USDT 餘額 (read-only query)。CronSelfFail 時為 0.0。
    pub bybit_balance_usdt: f64,
    /// 本地 V100 net flow (stake - redeem)。CronSelfFail 時為 0.0。
    pub local_net_usdt: f64,
    /// diff = bybit - local；正值代表 Bybit 多算 / 本地漏記。
    pub diff_usdt: f64,
    /// 3 階 cascade severity；CronSelfFail 時為 None。
    pub severity: Option<DiffSeverity>,
    /// 對 past 24h pending row 的 UPDATE 計數 (matched + mismatch 加總)。
    pub rows_updated: usize,
    /// 連續 mismatch 天數（含本日；< 3 = Warn 上限，≥ 3 = Degraded）。
    pub consecutive_mismatch_days: u32,
    /// reconciliation cron 自身是否 fail (Bybit timeout / PG error)；
    /// per earn_governance §6.3 此種 fail 不計入連續 mismatch 計數。
    pub cron_self_failed: bool,
    /// 失敗原因（cron_self_failed=true 時 Some）。
    pub failure_reason: Option<String>,
}

impl ReconciliationOutcome {
    fn cron_self_fail(reason: impl Into<String>) -> Self {
        Self {
            bybit_balance_usdt: 0.0,
            local_net_usdt: 0.0,
            diff_usdt: 0.0,
            severity: None,
            rows_updated: 0,
            consecutive_mismatch_days: 0,
            cron_self_failed: true,
            failure_reason: Some(reason.into()),
        }
    }
}

/// Bybit Earn 總 USDT 餘額查詢抽象。
///
/// 為什麼用 trait：Wave B B3 `bybit_earn_client.rs` 尚未 land；本模組透過
/// trait 解耦，B3 land 後將 `BybitEarnClient` wrapper 成 impl 即可，不需改
/// cron 主邏輯。對齊 health::writer::HealthObservationWriter trait 範式。
#[async_trait]
pub trait BybitEarnBalanceSource: Send + Sync {
    /// 查 Bybit Earn 帳上 USDT 總餘額（flexible + fixed 合計，read-only）。
    /// 失敗（HTTP timeout / retCode != 0 / parse error）返 Err 字串；caller
    /// 端 fail-closed 走 CronSelfFail。
    async fn query_total_usdt_balance(&self) -> Result<f64, String>;
}

/// V100 `learning.earn_movement_log` 讀寫抽象。
///
/// 為什麼用 trait：Wave B B4 `EarnMovementWriter` 尚未 land；本模組透過 trait
/// 與 PG SSOT 解耦，B4 land 後將 writer wrapper 成 impl 即可。
#[async_trait]
pub trait EarnMovementReader: Send + Sync {
    /// 計算自 V100 創建至今的本地 net flow：sum(amount_usdt where
    /// direction='stake') - sum(amount_usdt where direction='redeem')。
    /// 對齊 dispatch packet §5.3 line 772 `compute_local_net_flow` 語意。
    async fn compute_local_net_flow(&self) -> Result<f64, String>;

    /// UPDATE past 24h `reconciliation_status='pending'` row 為指定 status。
    /// 對齊 dispatch packet §5.3 line 785-791 + V100 schema CHECK 3 enum
    /// (`pending` / `matched` / `mismatch`)。
    /// 返回實際更新 row 數。
    async fn update_past_24h_pending(
        &self,
        new_status: &str,
        evidence: serde_json::Value,
    ) -> Result<usize, String>;

    /// 從 V100 reconciliation_status 推算連續 mismatch 天數（含本日 status；
    /// 對齊 earn_governance §6.4 healthcheck [earn-5]）。
    /// 實作建議 SQL: `SELECT date_trunc('day', event_ts) AS d,
    ///   bool_or(reconciliation_status='mismatch') AS has_mismatch
    ///   FROM learning.earn_movement_log
    ///   WHERE event_ts > now() - INTERVAL '30 days'
    ///   GROUP BY d ORDER BY d DESC` → 從最新日往回數連續 has_mismatch=true。
    async fn count_consecutive_mismatch_days(&self) -> Result<u32, String>;
}

/// Daily Earn reconciliation cron 主類。
///
/// Wave B B3/B4 land 後生產注入：
///   - `bybit_balance_source` = `Arc<BybitEarnClient>` wrapper
///   - `movement_reader` = `Arc<EarnMovementWriter>` wrapper
pub struct EarnReconciliationCron {
    bybit_balance_source: Arc<dyn BybitEarnBalanceSource>,
    movement_reader: Arc<dyn EarnMovementReader>,
}

impl EarnReconciliationCron {
    pub fn new(
        bybit_balance_source: Arc<dyn BybitEarnBalanceSource>,
        movement_reader: Arc<dyn EarnMovementReader>,
    ) -> Self {
        Self {
            bybit_balance_source,
            movement_reader,
        }
    }

    /// 跑一次 reconciliation。test + scheduler tick 共用入口。
    ///
    /// 流程（對齊 dispatch packet §5.3 Step 1-5）：
    /// 1. Query Bybit balance；fail → CronSelfFail
    /// 2. Compute local net flow；fail → CronSelfFail
    /// 3. diff = bybit - local；依 3 cascade threshold 分類
    /// 4. UPDATE past 24h pending row 為 matched / mismatch
    /// 5. 查連續 mismatch 天數；≥ 3 → 升 Degraded
    pub async fn run_once(&self) -> ReconciliationOutcome {
        // Step 1: Bybit balance
        let bybit_balance = match self.bybit_balance_source.query_total_usdt_balance().await {
            Ok(b) => b,
            Err(e) => {
                error!(
                    target = "cron.earn_reconciliation",
                    error = %e,
                    "Bybit Earn balance query failed; cron self-fail (per earn_governance §6.3 \
                     不計入連續 mismatch)"
                );
                return ReconciliationOutcome::cron_self_fail(format!("bybit_query_fail: {e}"));
            }
        };

        // Step 2: 本地 net flow
        let local_net = match self.movement_reader.compute_local_net_flow().await {
            Ok(n) => n,
            Err(e) => {
                error!(
                    target = "cron.earn_reconciliation",
                    error = %e,
                    "V100 local net flow query failed; cron self-fail"
                );
                return ReconciliationOutcome::cron_self_fail(format!("pg_query_fail: {e}"));
            }
        };

        // Step 3: diff + initial severity (Notice / Warn)
        let diff = bybit_balance - local_net;
        let abs_diff = diff.abs();
        let mut severity = if abs_diff < 0.01 {
            DiffSeverity::Notice
        } else {
            // $0.01 ≤ abs(diff)，先升 Warn；累積 3 day mismatch 才升 Degraded
            // （dispatch packet operator 指示明確）。
            DiffSeverity::Warn
        };

        // Step 4: UPDATE past 24h pending row
        let new_status = if matches!(severity, DiffSeverity::Notice) {
            "matched"
        } else {
            "mismatch"
        };
        let evidence = serde_json::json!({
            "cron": "earn_reconciliation",
            "bybit_balance_usdt": bybit_balance,
            "local_net_usdt": local_net,
            "diff_usdt": diff,
            "severity": severity.as_str(),
            "ts_utc": Utc::now().to_rfc3339(),
        });
        let rows_updated = match self
            .movement_reader
            .update_past_24h_pending(new_status, evidence.clone())
            .await
        {
            Ok(n) => n,
            Err(e) => {
                // UPDATE 失敗算 cron self-fail（governance integrity 破損）。
                error!(
                    target = "cron.earn_reconciliation",
                    error = %e,
                    "V100 UPDATE past 24h pending failed; cron self-fail"
                );
                return ReconciliationOutcome::cron_self_fail(format!("pg_update_fail: {e}"));
            }
        };

        // Step 5: 連續 mismatch 天數 → 升級 Degraded
        let consecutive = match self.movement_reader.count_consecutive_mismatch_days().await {
            Ok(c) => c,
            Err(e) => {
                // 連續計數查詢失敗也算 cron self-fail。
                error!(
                    target = "cron.earn_reconciliation",
                    error = %e,
                    "consecutive mismatch days query failed; cron self-fail"
                );
                return ReconciliationOutcome::cron_self_fail(format!(
                    "consecutive_query_fail: {e}"
                ));
            }
        };
        if consecutive >= 3 {
            severity = DiffSeverity::Degraded;
        }

        // 3 階 cascade tracing 路由
        match severity {
            DiffSeverity::Notice => {
                info!(
                    target = "cron.earn_reconciliation",
                    severity = "notice",
                    bybit_balance_usdt = bybit_balance,
                    local_net_usdt = local_net,
                    diff_usdt = diff,
                    rows_updated,
                    consecutive_mismatch_days = consecutive,
                    "[NOTICE] Earn reconciliation match (abs_diff < $0.01)"
                );
            }
            DiffSeverity::Warn => {
                warn!(
                    target = "cron.earn_reconciliation",
                    severity = "health_warn",
                    bybit_balance_usdt = bybit_balance,
                    local_net_usdt = local_net,
                    diff_usdt = diff,
                    rows_updated,
                    consecutive_mismatch_days = consecutive,
                    "[HEALTH_WARN] Earn reconciliation mismatch (abs_diff >= $0.01); next \
                     stake/redeem pre-check recommended"
                );
            }
            DiffSeverity::Degraded => {
                error!(
                    target = "cron.earn_reconciliation",
                    severity = "health_degraded",
                    bybit_balance_usdt = bybit_balance,
                    local_net_usdt = local_net,
                    diff_usdt = diff,
                    rows_updated,
                    consecutive_mismatch_days = consecutive,
                    "[HEALTH_DEGRADED] Earn reconciliation 3-day cumulative mismatch; manual \
                     review required (Wave B halt strategy hook pending wire-up)"
                );
            }
        }

        ReconciliationOutcome {
            bybit_balance_usdt: bybit_balance,
            local_net_usdt: local_net,
            diff_usdt: diff,
            severity: Some(severity),
            rows_updated,
            consecutive_mismatch_days: consecutive,
            cron_self_failed: false,
            failure_reason: None,
        }
    }

    /// long-running tokio task：每日 UTC 02:00 fire 一次 run_once，
    /// 對齊 main_health_emitters::spawn_*_scheduler 範式。
    ///
    /// 為什麼用「下一次 02:00 wake-up」而非 `tokio::time::interval(24h)`：
    ///   - interval(24h) 從 spawn 時刻起算，engine restart 後 fire 時刻會漂移
    ///     (e.g. 07:00 啟動 → 每日 07:00 fire，不符 UTC 02:00 spec)。
    ///   - 顯式算 next 02:00 UTC → 與 funding settlement 00:00/08:00/16:00 永遠
    ///     對齊，跨 restart 行為穩定。
    pub fn spawn(self: Arc<Self>, cancel: CancellationToken) {
        tokio::spawn(async move {
            info!(
                target = "cron.earn_reconciliation",
                "EarnReconciliationCron spawned (UTC 02:00 daily; per dispatch packet OP-4 \
                 caveat 2 避 funding settlement window 00:00/08:00/16:00 UTC)"
            );

            loop {
                let now = Utc::now();
                let sleep_dur = duration_until_next_utc_0200(now);

                tokio::select! {
                    _ = tokio::time::sleep(sleep_dur) => {
                        let _ = self.run_once().await;
                    }
                    _ = cancel.cancelled() => {
                        info!(
                            target = "cron.earn_reconciliation",
                            "EarnReconciliationCron cancellation requested; exit loop"
                        );
                        break;
                    }
                }
            }
        });
    }
}

/// 計算 `now` 到「下一次 UTC 02:00」的 `std::time::Duration`。
///
/// 為什麼公開：unit test 可直接驗證調度時刻計算，無需 mock clock。
/// 為什麼用 chrono 而非自己 mod 算：跨日 / 跨年邊界由 chrono `succ_opt()` /
/// `and_hms_opt` 處理，不重造輪子。
pub fn duration_until_next_utc_0200(now: DateTime<Utc>) -> std::time::Duration {
    let target_time = NaiveTime::from_hms_opt(2, 0, 0)
        .expect("UTC 02:00:00 是合法 NaiveTime");
    let today_target_naive = now.date_naive().and_time(target_time);
    let today_target_utc = Utc.from_utc_datetime(&today_target_naive);

    // 若 now < 今日 02:00 → wake 今日 02:00；否則 wake 明日 02:00。
    let target = if now < today_target_utc {
        today_target_utc
    } else {
        let tomorrow: NaiveDate = now
            .date_naive()
            .succ_opt()
            .unwrap_or_else(|| now.date_naive()); // succ_opt None 僅在 chrono::NaiveDate::MAX；
                                                  // 退回今日避免 panic（fallback fire 即可）。
        let tomorrow_target_naive = tomorrow.and_time(target_time);
        Utc.from_utc_datetime(&tomorrow_target_naive)
    };

    let delta: ChronoDuration = target - now;
    // 安全保底：若任何邊界導致 delta < 0，fire 5 秒後（避免 sleep 0 busy loop）。
    delta
        .to_std()
        .unwrap_or(std::time::Duration::from_secs(5))
}

// ============================================================
// Mock impl — Wave B B3/B4 land 前的 cron self-contained 測試用。
// ============================================================

/// `BybitEarnBalanceSource` mock：固定回傳預設值或預設錯誤；
/// 用於 cron unit test，模擬 Bybit /v5/earn/order/query-history 返回。
pub struct MockBybitBalanceSource {
    inner: Mutex<MockBybitBalanceInner>,
}

struct MockBybitBalanceInner {
    result: Result<f64, String>,
}

impl MockBybitBalanceSource {
    pub fn with_balance(balance: f64) -> Self {
        Self {
            inner: Mutex::new(MockBybitBalanceInner {
                result: Ok(balance),
            }),
        }
    }

    pub fn with_error(reason: impl Into<String>) -> Self {
        Self {
            inner: Mutex::new(MockBybitBalanceInner {
                result: Err(reason.into()),
            }),
        }
    }
}

#[async_trait]
impl BybitEarnBalanceSource for MockBybitBalanceSource {
    async fn query_total_usdt_balance(&self) -> Result<f64, String> {
        self.inner.lock().await.result.clone()
    }
}

/// `EarnMovementReader` mock：完整模擬 V100 reader；用於 cron unit test，
/// 驗證 3 cascade threshold 與 UPDATE rows 計數。
pub struct MockMovementReader {
    inner: Mutex<MockMovementInner>,
}

struct MockMovementInner {
    local_net_result: Result<f64, String>,
    update_result: Result<usize, String>,
    consecutive_result: Result<u32, String>,
    /// 紀錄最近一次 update_past_24h_pending 的 (status, evidence)。
    pub last_update_args: Option<(String, serde_json::Value)>,
}

impl MockMovementReader {
    pub fn new() -> Self {
        Self {
            inner: Mutex::new(MockMovementInner {
                local_net_result: Ok(0.0),
                update_result: Ok(0),
                consecutive_result: Ok(0),
                last_update_args: None,
            }),
        }
    }

    pub async fn set_local_net(&self, net: f64) {
        self.inner.lock().await.local_net_result = Ok(net);
    }

    pub async fn set_local_net_error(&self, reason: impl Into<String>) {
        self.inner.lock().await.local_net_result = Err(reason.into());
    }

    pub async fn set_update_rows(&self, rows: usize) {
        self.inner.lock().await.update_result = Ok(rows);
    }

    pub async fn set_update_error(&self, reason: impl Into<String>) {
        self.inner.lock().await.update_result = Err(reason.into());
    }

    pub async fn set_consecutive_days(&self, days: u32) {
        self.inner.lock().await.consecutive_result = Ok(days);
    }

    pub async fn set_consecutive_error(&self, reason: impl Into<String>) {
        self.inner.lock().await.consecutive_result = Err(reason.into());
    }

    pub async fn last_update_status(&self) -> Option<String> {
        self.inner
            .lock()
            .await
            .last_update_args
            .as_ref()
            .map(|(s, _)| s.clone())
    }
}

impl Default for MockMovementReader {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl EarnMovementReader for MockMovementReader {
    async fn compute_local_net_flow(&self) -> Result<f64, String> {
        self.inner.lock().await.local_net_result.clone()
    }

    async fn update_past_24h_pending(
        &self,
        new_status: &str,
        evidence: serde_json::Value,
    ) -> Result<usize, String> {
        let mut guard = self.inner.lock().await;
        guard.last_update_args = Some((new_status.to_string(), evidence));
        guard.update_result.clone()
    }

    async fn count_consecutive_mismatch_days(&self) -> Result<u32, String> {
        self.inner.lock().await.consecutive_result.clone()
    }
}

// ============================================================
// Unit tests — cargo test --release --lib cron::earn_reconciliation
// ============================================================

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::TimeZone;

    fn build_cron(
        bybit_balance: f64,
        local_net: f64,
        consecutive_days: u32,
    ) -> (
        Arc<EarnReconciliationCron>,
        Arc<MockMovementReader>,
    ) {
        let bybit = Arc::new(MockBybitBalanceSource::with_balance(bybit_balance));
        let reader = Arc::new(MockMovementReader::new());
        // tokio test 直接 block_on 不能用，這裡走 sync 設定：先 spawn block
        let r2 = reader.clone();
        // SAFETY: 此 helper 僅在 test 同步 setup 期間用；await mock setter 同 thread。
        tokio::task::block_in_place(|| {
            tokio::runtime::Handle::current().block_on(async {
                r2.set_local_net(local_net).await;
                r2.set_update_rows(3).await;
                r2.set_consecutive_days(consecutive_days).await;
            });
        });
        let cron = Arc::new(EarnReconciliationCron::new(bybit, reader.clone()));
        (cron, reader)
    }

    /// 場景 A：完美對齊（diff = 0 < $0.01）→ Notice + status=matched。
    #[tokio::test(flavor = "multi_thread")]
    async fn test_severity_notice_perfect_match() {
        let (cron, reader) = build_cron(200.0, 200.0, 0);
        let outcome = cron.run_once().await;
        assert!(!outcome.cron_self_failed, "perfect match 不應 cron self-fail");
        assert_eq!(outcome.severity, Some(DiffSeverity::Notice));
        assert!(outcome.diff_usdt.abs() < 1e-9);
        assert_eq!(outcome.rows_updated, 3);
        assert_eq!(reader.last_update_status().await.as_deref(), Some("matched"));
    }

    /// 場景 B：abs(diff) = $0.005 (< $0.01) → Notice。
    #[tokio::test(flavor = "multi_thread")]
    async fn test_severity_notice_below_threshold() {
        let (cron, _reader) = build_cron(200.005, 200.0, 0);
        let outcome = cron.run_once().await;
        assert_eq!(outcome.severity, Some(DiffSeverity::Notice));
    }

    /// 場景 C：abs(diff) = $0.50 ($0.01 ≤ diff < $1.00) + 連續 0 day → Warn。
    #[tokio::test(flavor = "multi_thread")]
    async fn test_severity_warn_mid_range_no_consecutive() {
        let (cron, reader) = build_cron(200.50, 200.0, 0);
        let outcome = cron.run_once().await;
        assert_eq!(outcome.severity, Some(DiffSeverity::Warn));
        assert!((outcome.diff_usdt - 0.50).abs() < 1e-9);
        assert_eq!(reader.last_update_status().await.as_deref(), Some("mismatch"));
    }

    /// 場景 D：abs(diff) = $5.00 (>= $1.00) 但連續 0 day → 仍 Warn（per operator
    /// 指示 Degraded 是「3-day cumulative」非單日大額；單日大額由 Wave B 路由）。
    #[tokio::test(flavor = "multi_thread")]
    async fn test_severity_warn_large_diff_no_consecutive() {
        let (cron, _reader) = build_cron(205.0, 200.0, 0);
        let outcome = cron.run_once().await;
        assert_eq!(outcome.severity, Some(DiffSeverity::Warn));
    }

    /// 場景 E：abs(diff) = $0.50 + 連續 3 day → Degraded（cascade 升級）。
    #[tokio::test(flavor = "multi_thread")]
    async fn test_severity_degraded_3day_cumulative() {
        let (cron, reader) = build_cron(200.50, 200.0, 3);
        let outcome = cron.run_once().await;
        assert_eq!(outcome.severity, Some(DiffSeverity::Degraded));
        assert_eq!(outcome.consecutive_mismatch_days, 3);
        assert_eq!(reader.last_update_status().await.as_deref(), Some("mismatch"));
    }

    /// 場景 F：連續 5 day（> 3）也是 Degraded。
    #[tokio::test(flavor = "multi_thread")]
    async fn test_severity_degraded_5day() {
        let (cron, _reader) = build_cron(200.50, 200.0, 5);
        let outcome = cron.run_once().await;
        assert_eq!(outcome.severity, Some(DiffSeverity::Degraded));
        assert_eq!(outcome.consecutive_mismatch_days, 5);
    }

    /// 場景 G：Bybit query fail → CronSelfFail，不計連續 mismatch 計數。
    #[tokio::test(flavor = "multi_thread")]
    async fn test_bybit_query_fail_cron_self_fail() {
        let bybit = Arc::new(MockBybitBalanceSource::with_error("timeout"));
        let reader = Arc::new(MockMovementReader::new());
        let cron = EarnReconciliationCron::new(bybit, reader);
        let outcome = cron.run_once().await;
        assert!(outcome.cron_self_failed);
        assert!(outcome.severity.is_none());
        assert!(outcome
            .failure_reason
            .as_deref()
            .unwrap_or("")
            .contains("bybit_query_fail"));
    }

    /// 場景 H：V100 net flow query fail → CronSelfFail。
    #[tokio::test(flavor = "multi_thread")]
    async fn test_local_net_fail_cron_self_fail() {
        let bybit = Arc::new(MockBybitBalanceSource::with_balance(200.0));
        let reader = Arc::new(MockMovementReader::new());
        reader.set_local_net_error("pg_connection_lost").await;
        let cron = EarnReconciliationCron::new(bybit, reader);
        let outcome = cron.run_once().await;
        assert!(outcome.cron_self_failed);
        assert!(outcome
            .failure_reason
            .as_deref()
            .unwrap_or("")
            .contains("pg_query_fail"));
    }

    /// 場景 I：UPDATE 失敗 → CronSelfFail（governance integrity 守線）。
    #[tokio::test(flavor = "multi_thread")]
    async fn test_update_fail_cron_self_fail() {
        let bybit = Arc::new(MockBybitBalanceSource::with_balance(200.0));
        let reader = Arc::new(MockMovementReader::new());
        reader.set_local_net(200.0).await;
        reader.set_update_error("constraint_violation").await;
        let cron = EarnReconciliationCron::new(bybit, reader);
        let outcome = cron.run_once().await;
        assert!(outcome.cron_self_failed);
        assert!(outcome
            .failure_reason
            .as_deref()
            .unwrap_or("")
            .contains("pg_update_fail"));
    }

    /// 場景 J：連續 mismatch 查詢 fail → CronSelfFail。
    #[tokio::test(flavor = "multi_thread")]
    async fn test_consecutive_query_fail_cron_self_fail() {
        let bybit = Arc::new(MockBybitBalanceSource::with_balance(200.50));
        let reader = Arc::new(MockMovementReader::new());
        reader.set_local_net(200.0).await;
        reader.set_update_rows(1).await;
        reader.set_consecutive_error("query_timeout").await;
        let cron = EarnReconciliationCron::new(bybit, reader);
        let outcome = cron.run_once().await;
        assert!(outcome.cron_self_failed);
        assert!(outcome
            .failure_reason
            .as_deref()
            .unwrap_or("")
            .contains("consecutive_query_fail"));
    }

    /// schedule 計算：當前 01:00 UTC → next fire 距 1h。
    #[test]
    fn test_duration_until_next_0200_morning_pre_target() {
        let now = Utc.with_ymd_and_hms(2026, 5, 23, 1, 0, 0).unwrap();
        let d = duration_until_next_utc_0200(now);
        assert_eq!(d.as_secs(), 3_600, "01:00 → 02:00 應 3600s");
    }

    /// schedule 計算：當前 02:00 UTC（恰好等於 target）→ next 跳明日 02:00。
    #[test]
    fn test_duration_until_next_0200_at_target() {
        let now = Utc.with_ymd_and_hms(2026, 5, 23, 2, 0, 0).unwrap();
        let d = duration_until_next_utc_0200(now);
        assert_eq!(d.as_secs(), 86_400, "02:00 命中時 next 應 24h 後 02:00");
    }

    /// schedule 計算：當前 03:00 UTC → next fire 距 23h。
    #[test]
    fn test_duration_until_next_0200_after_target() {
        let now = Utc.with_ymd_and_hms(2026, 5, 23, 3, 0, 0).unwrap();
        let d = duration_until_next_utc_0200(now);
        assert_eq!(d.as_secs(), 23 * 3600, "03:00 → 明日 02:00 應 23h");
    }

    /// schedule 計算：當前 23:30 UTC → next fire 距 2.5h（跨日邊界）。
    #[test]
    fn test_duration_until_next_0200_late_night_crosses_midnight() {
        let now = Utc.with_ymd_and_hms(2026, 5, 23, 23, 30, 0).unwrap();
        let d = duration_until_next_utc_0200(now);
        assert_eq!(d.as_secs(), 2 * 3600 + 30 * 60, "23:30 → 翌日 02:00 應 2.5h");
    }

    /// DiffSeverity::as_str 字串映射。
    #[test]
    fn test_diff_severity_as_str() {
        assert_eq!(DiffSeverity::Notice.as_str(), "notice");
        assert_eq!(DiffSeverity::Warn.as_str(), "health_warn");
        assert_eq!(DiffSeverity::Degraded.as_str(), "health_degraded");
    }

    /// ReconciliationOutcome::cron_self_fail constructor。
    #[test]
    fn test_cron_self_fail_constructor() {
        let o = ReconciliationOutcome::cron_self_fail("test_reason");
        assert!(o.cron_self_failed);
        assert!(o.severity.is_none());
        assert_eq!(o.failure_reason.as_deref(), Some("test_reason"));
        assert_eq!(o.bybit_balance_usdt, 0.0);
        assert_eq!(o.local_net_usdt, 0.0);
        assert_eq!(o.rows_updated, 0);
    }
}
