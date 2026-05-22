//! M3 Sprint 2 Wave 1 Track C — database_pool domain emitter。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md
//!   §2.1 + §3.2 + §3.3：採樣 PG 連接池與寫入後端健康指標（pool 活躍連接 /
//!   pool wait p95 / writer queue depth / data dir disk usage），每 60s 一輪，
//!   產 4 個 metric row → scheduler 端走 5-sample rolling window mean +
//!   classify_band → `HealthStateMachine::observe_classified` → V106 row INSERT。
//!
//!   為什麼 60s sample interval（per spec §2.1）：
//!     PG 寫入 backlog / pool 等待是分鐘級才有意義；高頻 self-query 反而是 hot
//!     path 干擾源（per dispatch packet §4.5 反模式 (a)）。對齊 5-sample × 60s
//!     = 5min window，與 §3.3 dwell time 設計（WARN→DEGRADED 5min dwell）一致。
//!
//! 主要類 / 函數:
//!   - `DatabasePoolSample`：4 metric snapshot struct（per spec §3.2）。
//!   - `DatabasePoolMetricRow`：MetricSample 投影（與 engine_runtime 範式一致）。
//!   - `DatabasePoolEmitter`：DomainEmitter impl；注入 `DbPool` + writer queue
//!     probe + disk usage probe。
//!   - `classify_database_pool_*`：4 個 per-metric classify_band helper。
//!   - `WriterQueueProbe` / `DiskUsageProbe` typedef：caller 端注入閉包，emitter
//!     只觀測不直接修 sqlx Pool / market_writer 邏輯。
//!
//! 依賴:
//!   - tokio + sysinfo 0.32 Disks API + crate::database::pool::DbPool（既有 sqlx
//!     PgPool wrapper）。
//!   - 不依賴 spike feature；production binary 完整 include。
//!
//! 硬邊界:
//!   - emitter 只讀，不修 `crate::database::pool::DbPool` wrapping 邏輯（per
//!     dispatch packet §4.5 反模式 (a)）。
//!   - writer queue depth 走 probe 注入；不直接讀 market_writer.rs task-local
//!     `Vec<MarketDataMsg>` buffer（buffer 在 task 內無法跨 task 觀測）。
//!   - sample_interval_sec() = 60；不寫死 30s（per dispatch packet §4.5 反模式
//!     (b)）。
//!   - 不沿用 Track A scaffold 之外的設計；DomainEmitter / MetricSample /
//!     observe_classified 全來自 Track A pub API（per dispatch packet §4.5 反
//!     模式 (c)）。
//!   - disk usage 跨平台原生支援 Mac+Linux；走 sysinfo Disks 不寫死 procfs（per
//!     dispatch packet §4.5 反模式 (d)）。
//!   - 不引 V### / spike / 跨進程 IPC（per dispatch packet §4.5 反模式 (e)）。

use std::sync::Arc;

use async_trait::async_trait;
use sysinfo::Disks;

use crate::database::pool::DbPool;
use crate::health::metric_emitter::{DomainEmitter, MetricSample};
use crate::health::{HealthDomain, HealthState, M3Error};

// ============================================================
// classify_band thresholds (per spec §2.3 ladder + dispatch packet §AC-2)
// ============================================================

/// `pg_pool_active_conn` classify：OK <80% pool / WARN 80-95% / DEGRADED >95%。
///
/// 為什麼此 threshold:
///   - pool 飽和率 80%+ 表示寫入 burst 接近上限（per `feedback_no_dead_params`
///     thread/conn leak 預警語意）；95%+ 表示飽和將觸發 acquire_timeout 退化。
///   - threshold dynamic update 走 Sprint 5 Tier 1 ArcSwap；本 Sprint 2 hardcode
///     對齊 spec §4.3 「Sprint 2 IMPL 先 hardcode threshold」決議。
pub fn classify_database_pool_active_conn(active: u32, pool_max: u32) -> HealthState {
    if pool_max == 0 {
        // pool 不可用（disconnected）；fail-closed OK band（per spec §4.1 step 4
        // 注釋：sample/source 異常時不誤升級）。
        return HealthState::HealthOk;
    }
    let pct = (active as f64) / (pool_max as f64);
    if pct > 0.95 {
        HealthState::HealthDegraded
    } else if pct >= 0.80 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// `pg_pool_wait_ms_p95` classify：OK <100ms / WARN 100-500ms / DEGRADED >500ms。
///
/// 為什麼此 threshold:
///   - pool acquire 等待 < 100ms 為正常 hot path；100ms+ 表示連接 contention；
///     500ms+ 表示 acquire_timeout 即將觸發（默認 5s 但寫入 hot path 不可等）。
///   - 對齊 spec §2.3 line 75-80 database_pool 階梯設計。
pub fn classify_database_pool_wait_ms_p95(wait_ms: u32) -> HealthState {
    if wait_ms > 500 {
        HealthState::HealthDegraded
    } else if wait_ms >= 100 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// `pg_writer_queue_depth` classify：OK <1000 / WARN 1000-5000 / DEGRADED >5000。
///
/// 為什麼此 threshold:
///   - market_writer / batch_insert 寫入 buffer 預期穩態 < 64（per
///     `crate::database::market_writer` `Vec::with_capacity(64)`）；1000+
///     表示寫入 backlog 累積；5000+ 表示 PG 寫入退化或網路斷流。
pub fn classify_database_pool_writer_queue_depth(depth: u32) -> HealthState {
    if depth > 5000 {
        HealthState::HealthDegraded
    } else if depth >= 1000 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// `disk_data_dir_used_pct` classify：OK <70% / WARN 70-85% / DEGRADED >85%。
///
/// 為什麼此 threshold:
///   - PG WAL + hypertable chunk 寫入需 free space；70%+ 表示需 archive；85%+
///     表示寫入即將失敗（hypertable INSERT errno=53100 disk full）。
///   - 對齊 spec §2.3 line 81-83 「disk 寫入空間」階梯設計。
pub fn classify_database_pool_disk_used_pct(pct: f64) -> HealthState {
    if pct > 85.0 {
        HealthState::HealthDegraded
    } else if pct >= 70.0 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

// ============================================================
// DatabasePoolSample + DatabasePoolMetricRow
// ============================================================

/// database_pool domain 採樣輸出（per spec §3.2 4 metric）。
///
/// 為什麼 4 metric:
///   - pool_active_conn：寫入 contention 偵測（per spec §2.1）。
///   - pool_wait_ms_p95：acquire latency burst（per spec §2.1）。
///   - writer_queue_depth：寫入 backlog 累積（per spec §2.1）。
///   - disk_data_dir_used_pct：PG 寫入空間耗盡（per spec §2.3）。
///
/// 為什麼用 pool_max_conn 一併採樣:
///   - pool_active_conn 單值無意義（需 active / max ratio）；採樣時一併取 max
///     讓 classify 端有完整 context；classify_band 內部計算 ratio。
#[derive(Debug, Clone, Copy)]
pub struct DatabasePoolSample {
    pub pool_active_conn: u32,
    pub pool_max_conn: u32,
    pub pool_wait_ms_p95: u32,
    pub writer_queue_depth: u32,
    pub disk_data_dir_used_pct: f64,
}

/// MetricSample wrapper：每 metric 個別投影為 row；scheduler 端列表處理。
///
/// 為什麼一 sample → 4 MetricSample row（per Track A scaffold pattern）:
///   - V106 row 是 per-metric_name 一條；4 metric → 4 row + 4 SM 各自 transition。
///   - 共用 anomaly_id space（`database_pool__<metric_name>`）但各 metric 獨立
///     累積 fire（per spec §6.2 anomaly_id 命名規約）。
#[derive(Debug, Clone, Copy)]
pub struct DatabasePoolMetricRow {
    pub metric_name: &'static str,
    pub value: f64,
    pub band: HealthState,
}

impl MetricSample for DatabasePoolMetricRow {
    fn metric_name(&self) -> &'static str {
        self.metric_name
    }

    fn numeric_value(&self) -> f64 {
        self.value
    }

    fn classify_band(&self) -> HealthState {
        self.band
    }
}

impl DatabasePoolSample {
    /// 將 sample 展為 4 個 metric row（每 metric_name 一條）。
    ///
    /// 為什麼此設計（per Track A scaffold pattern）:
    ///   - 對齊 V106 schema：1 row = 1 metric_name；不展平就無法各 metric 獨立
    ///     classify_band + SM transition。
    pub fn into_metric_rows(self) -> Vec<DatabasePoolMetricRow> {
        let active_band =
            classify_database_pool_active_conn(self.pool_active_conn, self.pool_max_conn);
        let wait_band = classify_database_pool_wait_ms_p95(self.pool_wait_ms_p95);
        let queue_band = classify_database_pool_writer_queue_depth(self.writer_queue_depth);
        let disk_band = classify_database_pool_disk_used_pct(self.disk_data_dir_used_pct);

        vec![
            DatabasePoolMetricRow {
                metric_name: "pg_pool_active_conn",
                value: self.pool_active_conn as f64,
                band: active_band,
            },
            DatabasePoolMetricRow {
                metric_name: "pg_pool_wait_ms_p95",
                value: self.pool_wait_ms_p95 as f64,
                band: wait_band,
            },
            DatabasePoolMetricRow {
                metric_name: "pg_writer_queue_depth",
                value: self.writer_queue_depth as f64,
                band: queue_band,
            },
            DatabasePoolMetricRow {
                metric_name: "disk_data_dir_used_pct",
                value: self.disk_data_dir_used_pct,
                band: disk_band,
            },
        ]
    }
}

// ============================================================
// Probe type aliases — caller 注入式 hook
// ============================================================

/// writer queue depth 採樣 closure。
///
/// 為什麼用 closure 注入而非直接讀 market_writer:
///   - market_writer 的 `Vec<MarketDataMsg>` buffer 是 task-local 變量
///     （`async fn writer_loop` 內 `let mut kline_buf = Vec::with_capacity(64)`），
///     不暴露給跨 task 採樣；強行加 Arc<Mutex<Vec>> 包裝會違 dispatch packet §4.5
///     反模式 (a) 「emitter 只讀，不修」。
///   - probe 注入式設計：main.rs 後續可接「watch event_consumer 寫入背壓 metric」
///     或「market_writer 自報的 backlog counter」；Sprint 2 不接 main.rs（per
///     Track A §7 carry-over），test 走 mock probe 返固定值。
pub type WriterQueueProbe = Arc<dyn Fn() -> u32 + Send + Sync>;

/// pool wait p95 採樣 closure。
///
/// 為什麼用 closure 注入:
///   - sqlx 0.8 Pool 沒提供原生 p95 latency；需上層觀測 acquire 耗時直方圖才能
///     算 p95。Sprint 2 emitter 不創新觀測層，走 probe 注入。
///   - test 注入固定值；production 走 Sprint 5 cascade IMPL 時補接觀測層。
pub type PoolWaitP95Probe = Arc<dyn Fn() -> u32 + Send + Sync>;

// ============================================================
// DatabasePoolEmitter
// ============================================================

/// Production runtime database_pool emitter。
///
/// 為什麼採用 Arc<DbPool> + probe 注入:
///   - per spec §3.2 + §3.3：emitter 只讀 pool stats（不修 sqlx Pool wrapping
///     邏輯），透過 `DbPool::get()` 取 `&PgPool` 後讀 `PgPool::size()` /
///     `num_idle()`；writer queue + p95 走 probe（既有 metric source 待 Sprint 5
///     cascade 補接）。
///   - disk usage 走 sysinfo Disks 跨平台原生 API；caller 端傳 PG data dir
///     mount point；emitter 找對應 disk 並計算 used%。
///
/// 為什麼 pool_max_conn caller 注入而非從 PgPoolOptions::max_connections 讀:
///   - sqlx PgPool 沒提供 max_connections accessor；DbPool wrapper 沒暴露
///     `DatabaseConfig::pool_max_connections`，強行加 accessor 會破反模式 (a)
///     「emitter 只讀，不修」。
///   - main.rs 接 scheduler 時已有 `DatabaseConfig` 在手，注入 `pool_max_conn`
///     是 cheap path；test 走固定值方便控制 classify_band 場景。
pub struct DatabasePoolEmitter {
    /// 共享 sqlx Pool 包裝；只讀，不修。
    db_pool: Arc<DbPool>,
    /// pool 最大連接數（來自 DatabaseConfig::pool_max_connections）；caller 注入。
    pool_max_conn: u32,
    /// PG data dir mount point（如 "/var/lib/postgresql/data" 或 macOS dev "/"）；
    /// emitter 在 sysinfo Disks 中找最佳匹配（mount_point prefix match）。
    data_dir_mount: String,
    /// writer queue depth probe（per WriterQueueProbe 注釋）。
    writer_queue_probe: WriterQueueProbe,
    /// pool wait p95 probe（per PoolWaitP95Probe 注釋）。
    pool_wait_p95_probe: PoolWaitP95Probe,
    /// 跨採樣共用的 Disks instance；refresh_list() 在 sample 內呼叫，避免每次重
    /// 建造成 syscall storm。
    disks: Disks,
}

impl DatabasePoolEmitter {
    /// 建立 emitter；caller 提供 pool + max_conn + data dir + 2 probe。
    ///
    /// 為什麼 caller 注入 data_dir_mount:
    ///   - 不同部署環境（Linux trade-core / Mac dev / 未來 Apple Silicon Mac）
    ///     PG data dir 位置不同；硬編碼會破 `feedback_cross_platform`。
    ///   - 預設 "/"（root 分區）在多數場景可用作 fallback；caller 端可走
    ///     `effective_engine_pg_data_dir()` helper 取真實 mount。
    pub fn new(
        db_pool: Arc<DbPool>,
        pool_max_conn: u32,
        data_dir_mount: impl Into<String>,
        writer_queue_probe: WriterQueueProbe,
        pool_wait_p95_probe: PoolWaitP95Probe,
    ) -> Self {
        // refresh_list 必先呼一次否則 list() 為空（per sysinfo 0.32 doc 強調）。
        let disks = Disks::new_with_refreshed_list();
        Self {
            db_pool,
            pool_max_conn,
            data_dir_mount: data_dir_mount.into(),
            writer_queue_probe,
            pool_wait_p95_probe,
            disks,
        }
    }

    /// 採當前 pool + writer + disk metric snapshot。
    ///
    /// 為什麼 mut self:
    ///   - sysinfo Disks refresh / refresh_list 為 mut；disk usage sample 需先
    ///     refresh 才能取最新值。
    pub fn sample_now(&mut self) -> Result<DatabasePoolSample, M3Error> {
        // Step 1: sqlx Pool stats（per dispatch packet §4 接點）。
        //
        // 為什麼 disconnected 場景 fail-closed 而非 Err:
        //   - `DbPool::connect()` 設計上 PG 不可用時返回 disconnected wrapper（per
        //     `crate::database::pool::DbPool::connect` 注釋）；emitter sample 不
        //     應因 PG 暫斷而 sample_error spam。disconnected 場景全 metric 走
        //     OK band（0 active → ratio 0 → OK；0 queue → OK）。
        //
        // 為什麼用 size() - num_idle() 算 active:
        //   - sqlx 0.8 `PgPool::size()` = pool 當前持有 connection 總數（idle +
        //     acquired），`num_idle()` = 可立即發放的閒置；差值 = 正被 hot path
        //     使用中的 connection 數，正是「active」語意。
        //   - pool_max_conn 來自 caller 注入（per struct 注釋），不依賴 sqlx
        //     提供 accessor（sqlx 沒暴露）。
        let pool_active_conn = match self.db_pool.get() {
            Some(pool) => pool.size().saturating_sub(pool.num_idle() as u32),
            None => 0u32,
        };

        // Step 2: writer queue depth probe。
        let writer_queue_depth = (self.writer_queue_probe)();

        // Step 3: pool wait p95 probe。
        let pool_wait_ms_p95 = (self.pool_wait_p95_probe)();

        // Step 4: disk usage（per sysinfo Disks 跨平台 API）。
        //
        // 為什麼 refresh() 而非 refresh_list():
        //   - refresh_list() 重建 disk 列表（hot path 略貴；Linux 走 statvfs 對
        //     NFS 可能 hang per sysinfo doc）；refresh() 只刷新已有 disk 數值。
        //   - emitter 期生命週期內 disk 列表不會變（除非 hot-plug），用 refresh
        //     即可。
        self.disks.refresh();
        let disk_data_dir_used_pct = compute_disk_used_pct(&self.disks, &self.data_dir_mount);

        Ok(DatabasePoolSample {
            pool_active_conn,
            pool_max_conn: self.pool_max_conn,
            pool_wait_ms_p95,
            writer_queue_depth,
            disk_data_dir_used_pct,
        })
    }
}

/// 在 Disks 列表中尋找最佳匹配 mount_point 並計算 used pct。
///
/// 為什麼此 helper:
///   - sysinfo Disks 列表是 OS 全部掛載點；emitter 需找與 data_dir 對應的 disk。
///   - 採「mount_point prefix match 取最長」策略：若多個 disk 符合，最長 prefix
///     對應的是該路徑實際所在分區（如 `/var/lib/postgresql/data` 屬於 `/var` 比
///     屬於 `/` 更精準）。
///   - 任一步失敗（無匹配 / total=0）→ 回 0.0（fail-closed OK band，不誤升級）。
fn compute_disk_used_pct(disks: &Disks, data_dir_mount: &str) -> f64 {
    let mut best_match: Option<&sysinfo::Disk> = None;
    let mut best_len: usize = 0;

    for disk in disks.list() {
        let mp = disk.mount_point();
        let mp_str = mp.to_string_lossy();
        if data_dir_mount.starts_with(mp_str.as_ref()) && mp_str.len() > best_len {
            best_match = Some(disk);
            best_len = mp_str.len();
        }
    }

    match best_match {
        Some(disk) => {
            let total = disk.total_space();
            if total == 0 {
                return 0.0;
            }
            let available = disk.available_space();
            let used = total.saturating_sub(available);
            (used as f64) / (total as f64) * 100.0
        }
        None => 0.0,
    }
}

#[async_trait]
impl DomainEmitter for DatabasePoolEmitter {
    fn domain(&self) -> HealthDomain {
        HealthDomain::DatabasePool
    }

    fn sample_interval_sec(&self) -> u64 {
        // per spec §2.1：database_pool 60s sample（不可寫死 30s per dispatch
        // packet §4.5 反模式 (b)）。
        60
    }

    async fn sample(&mut self) -> Result<Vec<Box<dyn MetricSample>>, M3Error> {
        let snapshot = self.sample_now()?;
        let rows = snapshot.into_metric_rows();
        Ok(rows
            .into_iter()
            .map(|r| Box::new(r) as Box<dyn MetricSample>)
            .collect())
    }
}

// ============================================================
// 測試
// ============================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_classify_active_conn_thresholds() {
        // OK <80% / WARN 80-95% / DEGRADED >95%。
        assert_eq!(
            classify_database_pool_active_conn(0, 10),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_database_pool_active_conn(7, 10),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_database_pool_active_conn(8, 10),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_database_pool_active_conn(9, 10),
            HealthState::HealthWarn
        );
        // 95% 邊界用 19/20 = 0.95 不過閾值；20/20=1.0 過閾值。
        assert_eq!(
            classify_database_pool_active_conn(19, 20),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_database_pool_active_conn(20, 20),
            HealthState::HealthDegraded
        );
        // pool_max=0 → fail-closed OK（disconnected 場景不誤升級）。
        assert_eq!(
            classify_database_pool_active_conn(0, 0),
            HealthState::HealthOk
        );
    }

    #[test]
    fn test_classify_wait_ms_p95_thresholds() {
        assert_eq!(
            classify_database_pool_wait_ms_p95(0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_database_pool_wait_ms_p95(99),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_database_pool_wait_ms_p95(100),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_database_pool_wait_ms_p95(500),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_database_pool_wait_ms_p95(501),
            HealthState::HealthDegraded
        );
    }

    #[test]
    fn test_classify_writer_queue_depth_thresholds() {
        assert_eq!(
            classify_database_pool_writer_queue_depth(0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_database_pool_writer_queue_depth(999),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_database_pool_writer_queue_depth(1000),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_database_pool_writer_queue_depth(5000),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_database_pool_writer_queue_depth(5001),
            HealthState::HealthDegraded
        );
    }

    #[test]
    fn test_classify_disk_used_pct_thresholds() {
        assert_eq!(
            classify_database_pool_disk_used_pct(0.0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_database_pool_disk_used_pct(69.9),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_database_pool_disk_used_pct(70.0),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_database_pool_disk_used_pct(85.0),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_database_pool_disk_used_pct(85.1),
            HealthState::HealthDegraded
        );
    }

    #[test]
    fn test_database_pool_sample_into_metric_rows_4_metrics() {
        let snapshot = DatabasePoolSample {
            pool_active_conn: 2,
            pool_max_conn: 10,
            pool_wait_ms_p95: 50,
            writer_queue_depth: 100,
            disk_data_dir_used_pct: 50.0,
        };
        let rows = snapshot.into_metric_rows();
        assert_eq!(rows.len(), 4);
        let names: Vec<&'static str> = rows.iter().map(|r| r.metric_name).collect();
        assert_eq!(
            names,
            vec![
                "pg_pool_active_conn",
                "pg_pool_wait_ms_p95",
                "pg_writer_queue_depth",
                "disk_data_dir_used_pct",
            ]
        );
        // 全 metric OK band。
        for r in &rows {
            assert_eq!(r.band, HealthState::HealthOk);
        }
    }

    #[test]
    fn test_database_pool_sample_into_metric_rows_warn_band() {
        let snapshot = DatabasePoolSample {
            pool_active_conn: 8,
            pool_max_conn: 10,
            pool_wait_ms_p95: 200,
            writer_queue_depth: 2000,
            disk_data_dir_used_pct: 75.0,
        };
        let rows = snapshot.into_metric_rows();
        // 全 metric WARN band。
        for r in &rows {
            assert_eq!(r.band, HealthState::HealthWarn, "{} should WARN", r.metric_name);
        }
    }

    #[test]
    fn test_database_pool_sample_into_metric_rows_degraded_band() {
        let snapshot = DatabasePoolSample {
            pool_active_conn: 20,
            pool_max_conn: 20,
            pool_wait_ms_p95: 1000,
            writer_queue_depth: 10000,
            disk_data_dir_used_pct: 90.0,
        };
        let rows = snapshot.into_metric_rows();
        for r in &rows {
            assert_eq!(
                r.band,
                HealthState::HealthDegraded,
                "{} should DEGRADED",
                r.metric_name
            );
        }
    }

    #[test]
    fn test_compute_disk_used_pct_no_match_returns_zero() {
        // 不重建 sysinfo Disks，用 default empty list 模擬無匹配場景；
        // sysinfo::Disks::new() 無 refresh_list，list() 為空。
        let disks = Disks::new();
        let pct = compute_disk_used_pct(&disks, "/var/lib/postgresql/data");
        // 無匹配 → fail-closed 0.0（不誤升級）。
        assert_eq!(pct, 0.0);
    }

    #[test]
    fn test_compute_disk_used_pct_real_disks_root_match() {
        // 真實環境一定有 "/" mount（Mac+Linux 都通）；驗 prefix match 邏輯能找到。
        let disks = Disks::new_with_refreshed_list();
        if disks.list().is_empty() {
            // sandbox / CI 環境可能無 disk 採樣（極端場景）；skip 此 case。
            return;
        }
        let pct = compute_disk_used_pct(&disks, "/");
        // 0.0 - 100.0 合理範圍。
        assert!(
            (0.0..=100.0).contains(&pct),
            "disk used pct 應在 [0, 100] 範圍，實得 {}",
            pct
        );
    }

    /// MetricSample trait 實作 sanity check。
    #[test]
    fn test_database_pool_metric_row_metric_sample_impl() {
        let row = DatabasePoolMetricRow {
            metric_name: "pg_pool_active_conn",
            value: 5.0,
            band: HealthState::HealthOk,
        };
        assert_eq!(MetricSample::metric_name(&row), "pg_pool_active_conn");
        assert_eq!(MetricSample::numeric_value(&row), 5.0);
        assert_eq!(MetricSample::classify_band(&row), HealthState::HealthOk);
    }

    /// DomainEmitter trait sanity check：sample_interval_sec=60 + domain
    /// 對齊。
    #[tokio::test]
    async fn test_database_pool_emitter_interval_60_and_domain() {
        let db_pool = Arc::new(DbPool::disconnected());
        let writer_queue_probe: WriterQueueProbe = Arc::new(|| 0);
        let pool_wait_p95_probe: PoolWaitP95Probe = Arc::new(|| 0);
        let emitter = DatabasePoolEmitter::new(
            db_pool,
            10,
            "/var/lib/postgresql/data",
            writer_queue_probe,
            pool_wait_p95_probe,
        );
        assert_eq!(emitter.domain(), HealthDomain::DatabasePool);
        assert_eq!(
            emitter.sample_interval_sec(),
            60,
            "per spec §2.1 database_pool 60s sample（不可寫死 30s）"
        );
    }

    /// 反模式 (a) 驗證：disconnected DbPool 場景 sample 不 panic 不 Err，全 OK
    /// band（fail-closed）。
    #[tokio::test]
    async fn test_database_pool_emitter_disconnected_pool_fail_closed_ok() {
        let db_pool = Arc::new(DbPool::disconnected());
        let writer_queue_probe: WriterQueueProbe = Arc::new(|| 0);
        let pool_wait_p95_probe: PoolWaitP95Probe = Arc::new(|| 0);
        // pool_max_conn=0：模擬 disconnected 場景；classify_active_conn 內部
        // 走 fail-closed OK band。
        let mut emitter = DatabasePoolEmitter::new(
            db_pool,
            0,
            "/",
            writer_queue_probe,
            pool_wait_p95_probe,
        );
        let snapshot = emitter.sample_now().expect("disconnected pool should fail-closed sample");
        // pool_active_conn / pool_max_conn 均為 0（disconnected）。
        assert_eq!(snapshot.pool_active_conn, 0);
        assert_eq!(snapshot.pool_max_conn, 0);
        // 走 classify_band 後全 OK。
        let rows = snapshot.into_metric_rows();
        let pool_row = rows
            .iter()
            .find(|r| r.metric_name == "pg_pool_active_conn")
            .unwrap();
        assert_eq!(pool_row.band, HealthState::HealthOk);
    }

    /// probe 注入回填 sample 場景：writer queue depth + pool wait p95 走 probe 值。
    #[tokio::test]
    async fn test_database_pool_emitter_probe_values_reach_sample() {
        let db_pool = Arc::new(DbPool::disconnected());
        let writer_queue_probe: WriterQueueProbe = Arc::new(|| 3000);
        let pool_wait_p95_probe: PoolWaitP95Probe = Arc::new(|| 250);
        let mut emitter = DatabasePoolEmitter::new(
            db_pool,
            10,
            "/",
            writer_queue_probe,
            pool_wait_p95_probe,
        );
        let snapshot = emitter.sample_now().unwrap();
        assert_eq!(snapshot.writer_queue_depth, 3000);
        assert_eq!(snapshot.pool_wait_ms_p95, 250);
        // classify_band：3000 → WARN（1000-5000），250 → WARN（100-500）。
        let rows = snapshot.into_metric_rows();
        let queue_row = rows
            .iter()
            .find(|r| r.metric_name == "pg_writer_queue_depth")
            .unwrap();
        assert_eq!(queue_row.band, HealthState::HealthWarn);
        let wait_row = rows
            .iter()
            .find(|r| r.metric_name == "pg_pool_wait_ms_p95")
            .unwrap();
        assert_eq!(wait_row.band, HealthState::HealthWarn);
    }
}
