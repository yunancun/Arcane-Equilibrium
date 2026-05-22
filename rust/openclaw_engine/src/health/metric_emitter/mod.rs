//! M3 Sprint 2 Track A — Metric Emitter scaffold（trait + window + scheduler）。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md
//!   §3.1 + §4 提供 Wave 1/2 共用 scaffold：
//!     - `DomainEmitter` trait：每 domain 一個 impl，負責採樣（sysinfo / sqlx
//!       Pool stats / Bybit p95 / strategy fill rate / risk_config 聚合）。
//!     - `MetricSample` trait：sample 結果統一介面（metric_name / numeric_value /
//!       classify_band）。
//!     - `RollingWindowAggregator`：5-sample 滑窗 Bessel-corrected mean+sigma
//!       聚合器（per spec §6 Bessel n-1）。
//!     - `MetricEmitterScheduler`：tokio task 包裝（每 domain 一個 interval
//!       loop），呼 emitter.sample() → aggregator.push() → SM.observe_classified()
//!       → writer.write_observation() → event_bus.publish()（fail-soft）。
//!
//!   Track A IMPL `EngineRuntimeEmitter`（sysinfo-backed）；Track B/C/D/E/F 沿
//!   用本 scaffold 各 IMPL `PipelineThroughputEmitter` / `DatabasePoolEmitter` /
//!   `ApiLatencyEmitter` / `StrategyQualityEmitter` / `RiskEnvelopeEmitter`。
//!
//! 主要類 / 函數:
//!   - `MetricSample` trait
//!   - `DomainEmitter` trait（async_trait）
//!   - `RollingWindowAggregator`：5-sample Bessel sigma 滑窗
//!   - `MetricEmitterScheduler`：tokio task wrapper（spawn 多 domain interval）
//!   - `EngineRuntimeEmitter`：Track A 本 IMPL，sysinfo 採樣 6 metric
//!
//! 依賴:
//!   - tokio + sysinfo 0.32 + async_trait + parking_lot + chrono。
//!   - 不依賴 spike feature（per packet §2.5 反模式 (b) production binary 0 mock
//!     time 滲透）。
//!
//! 硬邊界:
//!   - 不修改 `health/mod.rs` `observe()` 既有 API（backward compat per spike
//!     Track B；新 API 走 `observe_classified()`）。
//!   - 不在本 module 引 `cfg(feature = "spike")`；time 注入走 trait 抽象（test
//!     可注入 mock clock）。
//!   - sysinfo 不寫 `cfg(target_os = "linux")` 分支（per `feedback_cross_platform`
//!     + `project_mac_deployment_target`）。
//!   - emitter 只觀測，不修復外部 state（ws_client / pool / risk_config 既有
//!     SSOT 不動）。
//!   - emit V106 row 寫 `engine_mode != 'live'`（Sprint 2 走 paper/demo/live_demo
//!     only）。

use std::collections::{HashMap, VecDeque};
use std::sync::Arc;
use std::time::{Duration, Instant};

use async_trait::async_trait;
use chrono::Utc;
use sysinfo::{Pid, ProcessRefreshKind, ProcessesToUpdate, RefreshKind, System};
use tokio::sync::Mutex;
use tokio_util::sync::CancellationToken;

use super::event_bus::{HealthEventBus, HealthStateChangeEvent};
use super::writer::{HealthObservationRow, HealthObservationWriter};
use super::{HealthDomain, HealthState, HealthStateMachine, M3Error};
use uuid::Uuid;

// ============================================================
// MetricSample trait
// ============================================================

/// 單一 sample 結果統一介面（per spec §3.1）。
///
/// 為什麼 trait 而非 enum:
///   - 6 domain × per-domain metric struct 數量靈活；trait 比 enum match 易擴。
///   - test fixture 可實作 mock sample 不需動 enum。
pub trait MetricSample: Send + Sync + 'static {
    /// 對齊 V106 row column `metric_name`（per-domain 命名規約 per spec §6.2）。
    fn metric_name(&self) -> &'static str;
    /// 數值化 metric_value（NUMERIC(18,8)）；categorical metric（如 heartbeat
    /// alive）用 0.0/1.0 cast。
    fn numeric_value(&self) -> f64;
    /// 當前 sample 立即 classify band（window aggregation 由 scheduler 處理）。
    fn classify_band(&self) -> HealthState;

    /// 採樣端額外 evidence_json payload（per Sprint 2 round 3 Track C MEDIUM-3
    /// fix）。
    ///
    /// 為什麼 trait 加此 method（default None）:
    ///   - scheduler 端 run_domain_loop 寫 V106 row 時除 reject_reason 與
    ///     sample_error 兩條既有 evidence_json 路徑外，sample 端可能也帶採樣
    ///     上下文需 audit trail（如 database_pool disconnected 標記）。
    ///   - default 返 None：不影響既有 Track A engine_runtime / spike Track B
    ///     pipeline_throughput row 寫 evidence_json 行為。
    ///   - 與既有 reject_reason / sample_error evidence_json 路徑互斥：sample
    ///     端 extra_evidence 是「採樣成功但有條件需 audit」場景（如 disconnected
    ///     fail-closed OK band），不重複 sample_error 「採樣失敗」語意。
    ///   - per M3 design spec §2.3.2 disconnected handling 「disconnected 不靜
    ///     默」evidence_json 寫入路徑。
    fn extra_evidence(&self) -> Option<serde_json::Value> {
        None
    }
}

// ============================================================
// DomainEmitter trait
// ============================================================

/// Domain emitter trait（per spec §3.1）；每 domain 一個 impl。
///
/// 為什麼 dyn-incompatible（Self::Sample = associated type）:
///   - sample 為 strong-typed 結構，避 Box<dyn Any> 通用拆裝；scheduler 端
///     monomorphize 每 emitter。
///   - 對齊 spec §3.1 trait 設計 + Track A 升級基線。
#[async_trait]
pub trait DomainEmitter: Send + Sync {
    /// 此 emitter 負責的 domain（per ADR-0042 Decision 3 6 值之一）。
    fn domain(&self) -> HealthDomain;

    /// 採樣間隔秒數（per spec §2.1：30s engine_runtime/pipeline；60s
    /// database_pool/api_latency；300s strategy_quality/risk_envelope）。
    fn sample_interval_sec(&self) -> u64;

    /// 採樣入口；失敗回 Err → caller 走 fail-closed（writer.write_sample_error
    /// + state 維持當前 + 不升級）。
    ///
    /// 為什麼 Vec<Box<dyn MetricSample>> 而非 Self::Sample:
    ///   - 單 sample tick 可能採多個 metric（如 engine_runtime 一次採 6：cpu /
    ///     rss / heartbeat / open_fd / thread / uptime）。
    ///   - 多 metric 列表化讓 scheduler 統一處理 push/classify/SM observe。
    async fn sample(&mut self) -> Result<Vec<Box<dyn MetricSample>>, M3Error>;
}

// ============================================================
// RollingWindowAggregator — 5-sample Bessel sigma
// ============================================================

/// 5-sample 滑動窗口聚合器；對 numeric metric 計算 mean + sigma（Bessel n-1）。
///
/// 為什麼 5-sample 不 EWMA:
///   per spec §6：dwell time 設計是「持續 60s WARN-band」非「指數衰減」；EWMA
///   跟 dwell time 語意不對齊。5-sample 簡單滑窗對齊 dwell time。
///
/// 為什麼 Bessel n-1 而非 population n:
///   per spec §6：5-sample 是 sample（不是 population）；Bessel correction 是
///   sample variance 標準做法。對齊 Sprint 1B AC-7 cross-language fixture
///   `compute_window_stats` 已驗的 ddof=1 contract。
#[derive(Debug, Clone)]
pub struct RollingWindowAggregator {
    samples: VecDeque<f64>,
    metric_name: &'static str,
    capacity: usize,
}

impl RollingWindowAggregator {
    /// 建立 5-sample 滑窗（default）。
    pub fn new(metric_name: &'static str) -> Self {
        Self {
            samples: VecDeque::with_capacity(5),
            metric_name,
            capacity: 5,
        }
    }

    /// 自定容量；test 用（不影響 production 5-sample）。
    pub fn with_capacity(metric_name: &'static str, capacity: usize) -> Self {
        Self {
            samples: VecDeque::with_capacity(capacity),
            metric_name,
            capacity,
        }
    }

    /// 推入新 sample；超容量時 pop 最舊。
    pub fn push(&mut self, value: f64) {
        if self.samples.len() >= self.capacity {
            self.samples.pop_front();
        }
        self.samples.push_back(value);
    }

    /// 當前 mean；samples 為空時返回 None。
    pub fn mean(&self) -> Option<f64> {
        if self.samples.is_empty() {
            return None;
        }
        let sum: f64 = self.samples.iter().sum();
        Some(sum / self.samples.len() as f64)
    }

    /// Bessel-corrected sample sigma（n-1 denominator；n<2 returns None）。
    pub fn sigma(&self) -> Option<f64> {
        if self.samples.len() < 2 {
            return None;
        }
        let mean = self.mean().unwrap();
        let var: f64 = self
            .samples
            .iter()
            .map(|v| (v - mean).powi(2))
            .sum::<f64>()
            / (self.samples.len() - 1) as f64;
        Some(var.sqrt())
    }

    /// 當前 window 內 sample 數（最大 = capacity）。
    pub fn current_window_size(&self) -> usize {
        self.samples.len()
    }

    /// 此 aggregator 負責的 metric_name（writer 端 INSERT 用）。
    pub fn metric_name(&self) -> &'static str {
        self.metric_name
    }
}

// ============================================================
// EngineRuntimeEmitter — Track A IMPL
// ============================================================

/// engine_runtime domain 採樣輸出（per spec §3.2 Sprint 2 升級 6 metric）。
///
/// 為什麼 6 metric:
///   - cpu_pct / rss_mb：spike Track B 既有；spec §2.3 engine_runtime baseline。
///   - heartbeat_alive：spike Track B 既有；IPC heartbeat 30s 內 alive。
///   - open_fd_count / thread_count / uptime_sec：Sprint 2 新增（per spec §3.2
///     Sprint 2 EngineRuntimeSample 升級點）；fd 泄漏 / 線程暴漲 / 重啟循環
///     偵測。
#[derive(Debug, Clone, Copy)]
pub struct EngineRuntimeSample {
    pub cpu_pct: f64,
    pub rss_mb: f64,
    pub heartbeat_alive: bool,
    pub open_fd_count: u32,
    pub thread_count: u32,
    pub uptime_sec: u64,
}

/// MetricSample wrapper：每 metric 個別投影為 sample；scheduler 端列表處理。
///
/// 為什麼一 emitter sample → 多 MetricSample row:
///   - V106 row 是 per-metric_name 一條（per ADR-0042 Decision 4 anomaly_id =
///     domain × metric_name）；6 metric → 6 row + 6 SM 各自 transition。
///   - 共用 anomaly_id space 但 metric 獨立累積 fire。
#[derive(Debug, Clone, Copy)]
pub struct EngineRuntimeMetricRow {
    pub metric_name: &'static str,
    pub value: f64,
    pub band: HealthState,
}

impl MetricSample for EngineRuntimeMetricRow {
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

impl EngineRuntimeSample {
    /// 將 sample 展為 6 個 metric row（每 metric_name 一條）。
    ///
    /// 為什麼此設計:
    ///   - 對齊 V106 schema：1 row = 1 metric_name；不展平就無法各 metric 獨立
    ///     classify_band + SM transition。
    pub fn into_metric_rows(self) -> Vec<EngineRuntimeMetricRow> {
        let cpu_band = classify_engine_runtime_cpu_pct(self.cpu_pct);
        let rss_band = classify_engine_runtime_rss_mb(self.rss_mb);
        // heartbeat: false → CRITICAL（per spike Track B 既有語意）；true → OK。
        let heartbeat_band = if self.heartbeat_alive {
            HealthState::HealthOk
        } else {
            HealthState::HealthCritical
        };
        let fd_band = classify_engine_runtime_open_fd_count(self.open_fd_count);
        let thread_band = classify_engine_runtime_thread_count(self.thread_count);
        // uptime 不分 band：超過 60s 視為穩定 OK；< 60s 視為 reboot 中 WARN。
        // 此 threshold 對齊 spike Track B「engine restart loop > 3/5min」CRITICAL
        // 預警上游；Sprint 5 cascade 才整合 reboot loop detection。
        let uptime_band = if self.uptime_sec < 60 {
            HealthState::HealthWarn
        } else {
            HealthState::HealthOk
        };

        vec![
            EngineRuntimeMetricRow {
                metric_name: "cpu_pct",
                value: self.cpu_pct,
                band: cpu_band,
            },
            EngineRuntimeMetricRow {
                metric_name: "rss_mb",
                value: self.rss_mb,
                band: rss_band,
            },
            EngineRuntimeMetricRow {
                metric_name: "heartbeat_alive",
                value: if self.heartbeat_alive { 1.0 } else { 0.0 },
                band: heartbeat_band,
            },
            EngineRuntimeMetricRow {
                metric_name: "open_fd_count",
                value: self.open_fd_count as f64,
                band: fd_band,
            },
            EngineRuntimeMetricRow {
                metric_name: "thread_count",
                value: self.thread_count as f64,
                band: thread_band,
            },
            EngineRuntimeMetricRow {
                metric_name: "uptime_sec",
                value: self.uptime_sec as f64,
                band: uptime_band,
            },
        ]
    }
}

/// engine_runtime classify_band threshold —— cpu_pct（per spec §4.3）。
///
/// 為什麼此 threshold:
///   - OK <50% / WARN 50-80% / DEGRADED >80%（per spec §4.3 + spike Track B
///     classify_band 邏輯沿用）。
///   - threshold dynamic update 走 Sprint 5 Tier 1 ArcSwap；本 Sprint 2 hardcode。
pub fn classify_engine_runtime_cpu_pct(value: f64) -> HealthState {
    if value >= 80.0 {
        HealthState::HealthDegraded
    } else if value >= 50.0 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// rss_mb classify（per spec §4.3）：OK <2048 / WARN 2048-4096 / DEGRADED >4096。
pub fn classify_engine_runtime_rss_mb(value: f64) -> HealthState {
    if value > 4096.0 {
        HealthState::HealthDegraded
    } else if value > 2048.0 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// open_fd_count classify：OK <1024 / WARN 1024-4096 / DEGRADED >4096。
///
/// 為什麼此 threshold:
///   - 典型 Linux 默認 ulimit 1024 為 baseline；engine 全功能含 PG/Bybit/IPC
///     正常 fd 數 < 256，> 1024 即 fd leak signal。
pub fn classify_engine_runtime_open_fd_count(value: u32) -> HealthState {
    if value > 4096 {
        HealthState::HealthDegraded
    } else if value >= 1024 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// thread_count classify：OK <256 / WARN 256-512 / DEGRADED >512。
///
/// 為什麼此 threshold:
///   - tokio runtime + sqlx pool + 各 strategy task baseline 約 64 thread；
///     > 256 表示 thread spawn 失控（per `feedback_no_dead_params` thread leak
///     反模式預警）。
pub fn classify_engine_runtime_thread_count(value: u32) -> HealthState {
    if value > 512 {
        HealthState::HealthDegraded
    } else if value >= 256 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// Production runtime engine_runtime emitter（sysinfo 0.32 backed）。
///
/// 為什麼採用 sysinfo:
///   per spec §3 D1：operator sign-off 2026-05-22 採 sysinfo crate；跨平台原生
///   支援 Mac+Linux（不寫 `cfg(target_os = "linux")` 分支）。
pub struct EngineRuntimeEmitter {
    system: System,
    pid: Pid,
    /// engine boot 時間，計算 uptime_sec 用（per sysinfo `Process::start_time`
    /// 返回 wall-clock seconds since epoch；用 now - start_time 算 uptime）。
    start_time_anchor: Option<u64>,
    /// engine heartbeat 來源（IPC heartbeat watcher 或 main loop tick）；Sprint
    /// 2 用 SystemTime::now() 注入；Sprint 5 cascade 才接 IPC heartbeat watcher。
    /// 注入函式返回 true = alive，false = stale。
    heartbeat_probe: Arc<dyn Fn() -> bool + Send + Sync>,
}

impl EngineRuntimeEmitter {
    /// 建立 emitter；caller 提供當前 engine PID + heartbeat probe。
    ///
    /// 為什麼 heartbeat_probe 注入而非內建:
    ///   - test fixture 可注入 mock probe；production 接 IPC watcher。
    ///   - 對齊 spec §3 IPC heartbeat 邊界（emitter 只觀測，不創 watcher）。
    pub fn new<F>(pid: u32, heartbeat_probe: F) -> Self
    where
        F: Fn() -> bool + Send + Sync + 'static,
    {
        let mut system = System::new_with_specifics(
            RefreshKind::new().with_processes(ProcessRefreshKind::everything()),
        );
        // 第一次 refresh 取 baseline，第二次才會有 CPU% sample（sysinfo 設計）。
        system.refresh_processes(ProcessesToUpdate::Some(&[Pid::from_u32(pid)]), true);

        Self {
            system,
            pid: Pid::from_u32(pid),
            start_time_anchor: None,
            heartbeat_probe: Arc::new(heartbeat_probe),
        }
    }

    /// 採當前 process metric snapshot（test 可直接呼此 helper）。
    ///
    /// 為什麼 mut self:
    ///   - sysinfo refresh_processes 為 mut；CPU% sample 需 2-pass refresh
    ///     pattern。
    pub fn sample_now(&mut self) -> Result<EngineRuntimeSample, M3Error> {
        // refresh PID 對應 process 的 metric。
        self.system.refresh_processes(
            ProcessesToUpdate::Some(&[self.pid]),
            true,
        );

        let process = self.system.process(self.pid).ok_or_else(|| {
            M3Error::SampleError(format!(
                "sysinfo: PID {} not found（process dead or PID mismatch）",
                self.pid
            ))
        })?;

        // CPU% 對齊「過去採樣間隔內 process CPU 使用率」per sysinfo doc；
        // 首次 refresh 時可能為 0.0（baseline）。
        let cpu_pct = process.cpu_usage() as f64;
        // RSS bytes → MB。
        let rss_mb = (process.memory() as f64) / 1024.0 / 1024.0;

        // sysinfo Process::tasks() 在 Linux 返回 thread map（per sysinfo 0.32
        // doc）。Mac 上 thread_count 走 fallback：返回 0 + WARN 在 classify 端
        // 視為 OK（threshold 起點 256）。
        let thread_count = process
            .tasks()
            .map(|tasks| tasks.len() as u32)
            .unwrap_or(0);

        // Open FD count：sysinfo 0.32 沒直接 API；走 fallback 採 procfs（Linux）
        // 或 /dev/fd（Mac）；fail 時返回 0（fail-closed：OK band 0 不誤升級）。
        let open_fd_count = read_open_fd_count(self.pid).unwrap_or(0);

        // uptime: now - process.start_time()（sysinfo 返回 epoch seconds）。
        let now_epoch = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or(0);
        let start_time = self
            .start_time_anchor
            .unwrap_or_else(|| process.start_time());
        let uptime_sec = now_epoch.saturating_sub(start_time);

        // heartbeat probe 注入 caller 端。
        let heartbeat_alive = (self.heartbeat_probe)();

        Ok(EngineRuntimeSample {
            cpu_pct,
            rss_mb,
            heartbeat_alive,
            open_fd_count,
            thread_count,
            uptime_sec,
        })
    }
}

/// Open FD count fallback helper。
///
/// 為什麼此 helper 不寫死 `cfg(target_os = "linux")`:
///   - per packet §2.5 反模式 (c)：跨平台原生支援；Mac 走 /dev/fd path（雖然
///     是 process-global view 非 per-PID 精確，但保 Mac 部署不破）。
///   - sysinfo 0.32 沒提供 cross-platform open_fd API；本 helper 為 Sprint 2
///     scaffold；Sprint 5 cascade 接 IPC heartbeat 後可走 `procfs::Process::fd`
///     升級。
fn read_open_fd_count(pid: Pid) -> Option<u32> {
    // Linux: /proc/<pid>/fd 目錄 entry count
    #[cfg(target_os = "linux")]
    {
        let path = format!("/proc/{}/fd", pid.as_u32());
        if let Ok(entries) = std::fs::read_dir(path) {
            return Some(entries.count() as u32);
        }
        return None;
    }
    // Mac / 其他：fallback 0（fail-closed：OK band 0 不誤升級）。
    #[cfg(not(target_os = "linux"))]
    {
        let _ = pid;
        Some(0)
    }
}

#[async_trait]
impl DomainEmitter for EngineRuntimeEmitter {
    fn domain(&self) -> HealthDomain {
        HealthDomain::EngineRuntime
    }

    fn sample_interval_sec(&self) -> u64 {
        // per spec §2.1：engine_runtime 30s sample。
        30
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
// MetricEmitterScheduler — tokio task wrapper
// ============================================================

/// engine_mode 採樣 closure：呼之取「當前 engine_mode 字串」（per V106 CHECK
/// 4 值）。
///
/// 為什麼 closure 注入:
///   - engine_mode 由 main runtime 決定（per `effective_engine_mode` mod main.rs:
///     1044），emitter scheduler 不應自帶 mode 邏輯。
///   - test fixture 可注入固定 "demo"/"paper"。
pub type EngineModeProvider = Arc<dyn Fn() -> String + Send + Sync>;

/// MetricEmitterScheduler：tokio task 包裝（每 domain 一個 interval loop）。
///
/// 為什麼 trait object Box<dyn DomainEmitter>:
///   - DomainEmitter 為 async_trait，運行時動態 dispatch。
///   - 多 domain 共用 scheduler 端入隊管理 + cancel token。
pub struct MetricEmitterScheduler {
    /// 各 domain emitter（Track A 此 IMPL 只接 engine_runtime）。
    emitters: Vec<Box<dyn DomainEmitter>>,
    /// 各 domain × metric_name 對應 SM（per spec §5 ladder transition matrix）。
    state_machines: Arc<Mutex<HashMap<(HealthDomain, String), HealthStateMachine>>>,
    /// 各 domain × metric_name 對應 5-sample 滑窗。
    aggregators: Arc<Mutex<HashMap<(HealthDomain, String), RollingWindowAggregator>>>,
    /// V106 INSERT writer。
    writer: Arc<dyn HealthObservationWriter>,
    /// Sprint 5 cascade subscribe 預埋 event bus。
    event_bus: Arc<HealthEventBus>,
    /// 當前 engine_mode 採樣 closure。
    engine_mode: EngineModeProvider,
}

impl MetricEmitterScheduler {
    /// 建立 scheduler；caller 端注入 emitters + writer + event bus + mode provider。
    pub fn new(
        emitters: Vec<Box<dyn DomainEmitter>>,
        writer: Arc<dyn HealthObservationWriter>,
        event_bus: Arc<HealthEventBus>,
        engine_mode: EngineModeProvider,
    ) -> Self {
        // 為每個 emitter 初始化 SM + 滑窗（per metric_name lazy 加，首次 sample
        // 時建）。
        Self {
            emitters,
            state_machines: Arc::new(Mutex::new(HashMap::new())),
            aggregators: Arc::new(Mutex::new(HashMap::new())),
            writer,
            event_bus,
            engine_mode,
        }
    }

    /// 跑 scheduler；caller 端 spawn 為 tokio task；cancel 時 graceful shutdown。
    ///
    /// 為什麼 cancel_token 而非 JoinHandle::abort:
    ///   - graceful shutdown：每 domain loop 在 tick 邊界檢查 cancel，避中斷
    ///     INSERT 寫到一半。
    ///
    /// 為什麼返 `Result<(), M3Error>`（per Sprint 2 Wave 2 round 2 OBSERVE-4 fix）:
    ///   - replay subprocess 嚴禁 emit health row（V106 line 259 engine_mode
    ///     CHECK 不含 'replay'），caller 端需立即看到 fail-loud Err 而非靜默
    ///     啟動後撞 PG CHECK。
    ///   - 對齊 spec line 199-216 OBSERVE-4 設計合約。
    pub async fn run(self, cancel_token: CancellationToken) -> Result<(), M3Error> {
        // OBSERVE-4 guard：scheduler 啟動前檢 engine_mode。replay subprocess
        // 嚴禁 emit health row（V106 CHECK 不含 'replay'）；fail-loud Err
        // 讓 caller 立即看到設計違反，不靜默走到 PG CHECK fail 才暴露。
        let startup_mode = (self.engine_mode)();
        if startup_mode == "replay" {
            return Err(M3Error::ReplaySubprocessForbidden);
        }

        let writer = Arc::clone(&self.writer);
        let event_bus = Arc::clone(&self.event_bus);
        let state_machines = Arc::clone(&self.state_machines);
        let aggregators = Arc::clone(&self.aggregators);
        let engine_mode_provider = Arc::clone(&self.engine_mode);

        let mut join_handles = Vec::new();
        for emitter in self.emitters {
            let writer = Arc::clone(&writer);
            let event_bus = Arc::clone(&event_bus);
            let state_machines = Arc::clone(&state_machines);
            let aggregators = Arc::clone(&aggregators);
            let mode_provider = Arc::clone(&engine_mode_provider);
            let token = cancel_token.clone();
            let handle = tokio::spawn(async move {
                run_domain_loop(
                    emitter,
                    state_machines,
                    aggregators,
                    writer,
                    event_bus,
                    mode_provider,
                    token,
                )
                .await;
            });
            join_handles.push(handle);
        }

        // 等所有 domain loop 結束。
        for handle in join_handles {
            let _ = handle.await;
        }
        Ok(())
    }
}

/// 推斷 SM `observe_classified` 返回 `Ok(false)` 時的 cascade reject_reason
/// （per Sprint 2 round 2 HIGH-1 fix）。
///
/// 為什麼此 helper:
///   - 原 IMPL 在 scheduler async block 內 inline 推斷，test 無法走真實
///     scheduler.run 驗（dwell 60s wall-clock）；抽 helper 後 test 構造 SM
///     state + 直接調用即可驗推斷正確性。
///   - 邏輯規約（per V106 spec §1.1 line 77 + SM guard 順序）:
///       guard 1（same anomaly suppress）優先於 guard 3（fail-closed >=2）；
///       即 cap entries 已包含 anomaly_id 時，**先**回 guard 1 reason，**不**
///       因 count >=2 誤標 fail-closed。
///       同 state 採樣（target=current）SM 視為純維持，非 reject，回 None。
///       dwell 未達等場景 SM 內部直接返 Ok(false) 但 anomaly 未進 cap，回 None。
///   - target_band 是 emitter 端 classify_band 結果（即 SM 收到的 band 參數）；
///     必須與 caller 端 observe_classified 帶入的 band 一致，否則推斷錯位。
///
/// 返回 None 場景:
///   - 同 state 採樣（target == current）
///   - dwell 未達 / 同 state 高 band（neither cap suppress nor fail-closed）
///
/// 返回 Some(reason):
///   - "amp_cap_same_anomaly_24h_suppress"：此 anomaly_id 已在 cap window 內
///   - "amp_cap_>=2_fail_closed"：count >= 2 撞上限，新 anomaly 也被擋
pub fn infer_reject_reason(
    sm: &HealthStateMachine,
    target_band: HealthState,
    anomaly_id: &str,
) -> Option<&'static str> {
    let current = sm.current_state();
    if target_band == current {
        return None;
    }
    if sm.is_anomaly_capped(anomaly_id) {
        Some("amp_cap_same_anomaly_24h_suppress")
    } else if sm.amplification_loop_24h_count() >= 2 {
        Some("amp_cap_>=2_fail_closed")
    } else {
        None
    }
}

/// SM observe_classified 一次調用的結果集合（per Sprint 2 round 2 MEDIUM-1
/// fix）。
///
/// 為什麼此 struct:
///   - 原 IMPL 在 SM lock 持有期間呼 writer.write_sample_error.await，違反
///     「async lock 跨 await」反模式；本 round 把 SM 結果先聚合到此 struct，
///     drop guard 後再走 writer，徹底避免 lock 持有 await。
///   - sample_error 為 Option<M3Error>：lock release 後 caller 端決定是否走
///     write_sample_error 路徑；Err 場景仍要寫普通 row 維持 audit 連續性。
///   - dwell_secs 來自 SM.last_transition_dwell_secs accessor（MEDIUM-2 fix），
///     fired=true 時才有意義；其餘場景 caller 端不寫入 row。
struct ObserveOutcome {
    prev_state: HealthState,
    current_state: HealthState,
    current_count: u32,
    fired: bool,
    dwell_secs: u32,
    reject_reason: Option<&'static str>,
    sample_error: Option<M3Error>,
}

/// 單一 domain 採樣 loop（per spec §4.1）。
///
/// 為什麼 7 step:
///   1. interval.tick() / cancel.cancelled() 二選一
///   2. emitter.sample() → 多 MetricSample
///   3. aggregator.push(value) per metric
///   4. classify_band on aggregated mean（>= 5 sample 時）
///   5. SM.observe_classified(band, anomaly_id, now)
///   6. writer.write_observation(row) per metric（含 sample_error / cascade
///      reject 場景）
///   7. event_bus.publish(transition) fire 時
async fn run_domain_loop(
    mut emitter: Box<dyn DomainEmitter>,
    state_machines: Arc<Mutex<HashMap<(HealthDomain, String), HealthStateMachine>>>,
    aggregators: Arc<Mutex<HashMap<(HealthDomain, String), RollingWindowAggregator>>>,
    writer: Arc<dyn HealthObservationWriter>,
    event_bus: Arc<HealthEventBus>,
    engine_mode: EngineModeProvider,
    cancel_token: CancellationToken,
) {
    let domain = emitter.domain();
    let interval_secs = emitter.sample_interval_sec();
    let mut interval = tokio::time::interval(Duration::from_secs(interval_secs));
    interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);

    loop {
        tokio::select! {
            _ = interval.tick() => {
                // ----------------------------------------
                // Step 0: OBSERVE-4 per-tick guard（per Sprint 2 Wave 2 round 2
                // fix；spec line 199-216）
                // ----------------------------------------
                //
                // 為什麼 per-tick 重檢 engine_mode（除 scheduler.run 啟動前檢）:
                //   - engine_mode 由 main runtime 動態決定（per `effective_engine_mode`
                //     main.rs:1044），運行中 caller 可能切換到 replay subprocess
                //     模式；scheduler 不能假設啟動後 mode 不變。
                //   - 撞 replay tick → 立即 break loop 避走後續 sample/writer
                //     path 撞 V106 CHECK；err 訊息走 tracing log 留 audit。
                let early_mode = (engine_mode)();
                if early_mode == "replay" {
                    tracing::error!(
                        domain = %domain.as_str(),
                        engine_mode = %early_mode,
                        "M3 emitter detected replay engine_mode at tick boundary — \
                         fail-loud break loop per spec line 199-216 OBSERVE-4 guard"
                    );
                    break;
                }

                // ----------------------------------------
                // Step 2: emitter.sample() （fail-soft）
                // ----------------------------------------
                let samples = match emitter.sample().await {
                    Ok(s) => s,
                    Err(e) => {
                        // fail-closed: 寫 V106 row state=OK + evidence_json
                        // sample_error；不升 state；continue 下次 tick。
                        let mode = (engine_mode)();
                        let _ = writer
                            .write_sample_error(domain, "(sample)", &e, &mode)
                            .await;
                        continue;
                    }
                };

                let mode = (engine_mode)();
                let observed_at = Utc::now();

                for sample in samples {
                    let metric_name = sample.metric_name();
                    let value = sample.numeric_value();
                    let _instant_band = sample.classify_band();
                    // 為什麼在 for sample loop 開頭抓 extra_evidence（per Sprint 2
                    // round 3 Track C MEDIUM-3 fix）:
                    //   - sample 在 classify / SM observe 之後仍要寫 V106 row；
                    //     extra_evidence 是 sample-time 採樣 audit；不依賴 SM 結
                    //     果。disconnected 場景 sample 採樣成功（fail-closed OK
                    //     band）但要寫 evidence_json `{"pool_status": "disconnected"}`。
                    let sample_extra_evidence = sample.extra_evidence();
                    let anomaly_id = format!("{}__{}", domain.as_str(), metric_name);

                    // ----------------------------------------
                    // Step 3-4: window push + classify on mean
                    // ----------------------------------------
                    let band_from_mean = {
                        let mut guard = aggregators.lock().await;
                        let agg = guard
                            .entry((domain, metric_name.to_string()))
                            .or_insert_with(|| RollingWindowAggregator::new(metric_name));
                        agg.push(value);
                        // 容量 < 5 時用即時 band（spike Track B 一致語意）；
                        // 容量 = 5 時用 5-sample mean classify。
                        if agg.current_window_size() < 5 {
                            sample.classify_band()
                        } else {
                            classify_aggregated(domain, metric_name, agg.mean().unwrap())
                        }
                    };

                    // ----------------------------------------
                    // Step 5-7: SM.observe_classified + writer + event publish
                    // ----------------------------------------
                    //
                    // 為什麼 SM lock 不跨 writer await（per Sprint 2 round 2
                    // MEDIUM-1 fix）：
                    //   原 IMPL 在 Err(e) 分支內 lock 仍持有時呼 writer.await，
                    //   tokio worker 可被阻塞；本 round 改為 (a) collect SM 結果
                    //   到 local + (b) drop guard + (c) 才走 writer 路徑。
                    let observe_outcome: ObserveOutcome = {
                        let mut sm_guard = state_machines.lock().await;
                        let sm = sm_guard
                            .entry((domain, metric_name.to_string()))
                            .or_insert_with(|| HealthStateMachine::new(domain));

                        let prev_state = sm.current_state();
                        let now_instant = Instant::now();

                        let observe_result = sm.observe_classified(
                            band_from_mean,
                            &anomaly_id,
                            now_instant,
                        );

                        let (fired, dwell_secs, reject_reason, sample_error): (
                            bool,
                            u32,
                            Option<&'static str>,
                            Option<M3Error>,
                        ) = match observe_result {
                            Ok(true) => (true, sm.last_transition_dwell_secs(), None, None),
                            Ok(false) => {
                                // reject_reason 推斷走集中 helper（per Sprint 2
                                // round 2 HIGH-1 fix）：infer_reject_reason 已
                                // 用 SM is_anomaly_capped 區分 guard 1 vs 3，
                                // 修原 IMPL prev_count >= 2 在 same anomaly +
                                // count=2 場景誤標 fail-closed 的 bug。
                                let reason =
                                    infer_reject_reason(sm, band_from_mean, &anomaly_id);
                                (false, 0, reason, None)
                            }
                            Err(e) => {
                                // M3Error 非 reject；走 sample_error 路徑（fail-
                                // soft 對齊 spec §4.1 step 4 注釋）；writer 寫入
                                // 在 drop(sm_guard) 之後（MEDIUM-1 fix）。
                                (false, 0, None, Some(e))
                            }
                        };

                        let current_state = sm.current_state();
                        let current_count = sm.amplification_loop_24h_count();

                        ObserveOutcome {
                            prev_state,
                            current_state,
                            current_count,
                            fired,
                            dwell_secs,
                            reject_reason,
                            sample_error,
                        }
                        // sm_guard 在此 scope 結束時自動 drop；後續 writer.await
                        // 不持有 SM lock（per MEDIUM-1 fix）。
                    };

                    // Err 分支：寫 sample_error row（drop sm_guard 之後再 await）。
                    if let Some(err) = observe_outcome.sample_error {
                        let _ = writer
                            .write_sample_error(domain, metric_name, &err, &mode)
                            .await;
                    }

                    // ----------------------------------------
                    // V106 row INSERT
                    // ----------------------------------------
                    let mut row = HealthObservationRow::new(
                        domain,
                        metric_name.to_string(),
                        observe_outcome.current_state,
                        value,
                        observe_outcome.current_count as i32,
                        mode.clone(),
                    );
                    row.observed_at = observed_at;
                    if observe_outcome.fired {
                        // dwell_secs 來自 SM 端 fire branch 計算（per Sprint 2
                        // round 2 MEDIUM-2 fix）；INTEGER cast 已在 SM 端 clamp。
                        row = row.with_transition(
                            observe_outcome.prev_state,
                            observe_outcome.dwell_secs as i32,
                        );
                    }
                    // D3 cascade reject log emit minimal IMPL：
                    //   per spec §3 D3，reject 場景 evidence_json 寫 reject_reason；
                    //   state 維持 current（不變 transition）；不 Slack / Console
                    //   badge / halt strategy / 降 LAL Tier（Sprint 5/7/8 才接）。
                    //
                    // 為什麼 reject_reason / sample-extra_evidence 互斥處理（per
                    // Sprint 2 round 3 Track C MEDIUM-3 fix）:
                    //   - reject_reason 是 SM observe 端 reject 場景；
                    //     extra_evidence 是 sample 端採樣 audit 場景。
                    //   - 兩者不同時 fire：sample 採樣成功且 extra_evidence != None
                    //     時 observe 必返 Ok(true) / Ok(false) 路徑（同 SM 邏輯），
                    //     reject_reason 由 observe 端 reject branch 才設立。
                    //   - 若同時 fire，reject_reason 優先（D3 path 更關鍵）；
                    //     extra_evidence 在 reject 場景被 reject_reason 覆蓋是
                    //     spec §2.3.2 acceptable（disconnected + reject 並列罕見）。
                    if let Some(reason) = observe_outcome.reject_reason {
                        row = row.with_evidence(serde_json::json!({
                            "reject_reason": reason,
                            "anomaly_id": anomaly_id.clone(),
                            "target_state": band_from_mean.as_str(),
                            "current_state": observe_outcome.current_state.as_str(),
                        }));
                    } else if let Some(extra) = sample_extra_evidence {
                        // sample 端 extra_evidence 寫入（如 database_pool
                        // disconnected `{"pool_status": "disconnected"}` audit
                        // trail；per M3 design spec §2.3.2 disconnected handling）。
                        row = row.with_evidence(extra);
                    }

                    let _ = writer.write_observation(row).await;

                    // ----------------------------------------
                    // event_bus publish (Sprint 5 cascade subscribe 預埋)
                    // ----------------------------------------
                    if observe_outcome.fired {
                        let event = HealthStateChangeEvent {
                            transition_id: Uuid::new_v4(),
                            domain,
                            old_state: observe_outcome.prev_state,
                            new_state: observe_outcome.current_state,
                            observed_at: observed_at.into(),
                            anomaly_id: anomaly_id.clone(),
                            amplification_loop_24h_count: observe_outcome.current_count,
                            reason_summary: format!(
                                "{} crossed band on 5-sample mean → {}",
                                metric_name,
                                observe_outcome.current_state.as_str()
                            ),
                        };
                        event_bus.publish(event);
                    }
                }
            }
            _ = cancel_token.cancelled() => break,
        }
    }
}

/// pub wrapper for integration test only — per Sprint 2 round 2 Track C HIGH-2
/// fix。
///
/// 為什麼開 pub re-export 而非 pub 主 fn:
///   - 集中 helper 仍維持 private 封裝（內部 classify routing 不洩漏給外部
///     caller）；integration test（`tests/sprint2_track_c_database_pool.rs` 等）
///     需驗 classify_aggregated 真實 dispatch 對應 domain arm 不退化，借此 pub
///     wrapper 端到端守 HIGH-1 不退化（避 `_ => HealthOk` fallback 誤接）。
///   - 命名顯式 `_for_test` 表達意圖：production code path 走 private
///     `classify_aggregated`；外部 test 走此 wrapper；兩者邏輯等價。
#[doc(hidden)]
pub fn classify_aggregated_for_test(
    domain: HealthDomain,
    metric_name: &str,
    mean: f64,
) -> HealthState {
    classify_aggregated(domain, metric_name, mean)
}

/// 5-sample mean 走 classify_band。
///
/// 為什麼集中此 helper:
///   - per-metric_name threshold 集中此處；Sprint 5 ArcSwap 熱更新時改本 fn
///     即可。
///   - Track A IMPL engine_runtime；Track B-F 各自擴此 match arm。
fn classify_aggregated(domain: HealthDomain, metric_name: &str, mean: f64) -> HealthState {
    match (domain, metric_name) {
        (HealthDomain::EngineRuntime, "cpu_pct") => classify_engine_runtime_cpu_pct(mean),
        (HealthDomain::EngineRuntime, "rss_mb") => classify_engine_runtime_rss_mb(mean),
        (HealthDomain::EngineRuntime, "heartbeat_alive") => {
            // 5-sample mean < 0.5 表示多數時刻 dead → CRITICAL。
            if mean < 0.5 {
                HealthState::HealthCritical
            } else {
                HealthState::HealthOk
            }
        }
        (HealthDomain::EngineRuntime, "open_fd_count") => {
            // 為什麼用 mean.round() 而非 mean as u32：
            //   raw `as u32` 是 truncation（mean=2.8 → 2）；對 ladder boundary
            //   附近的 sample 會錯歸 band（per Sprint 2 round 2 MEDIUM-2 fix）。
            //   round 對齊「半入」語意（mean=2.5 → 3），更貼近 5-sample mean
            //   反映的整數 count 概念。
            classify_engine_runtime_open_fd_count(mean.round() as u32)
        }
        (HealthDomain::EngineRuntime, "thread_count") => {
            // 同 open_fd_count：count 類 metric 走 round 不 truncate。
            classify_engine_runtime_thread_count(mean.round() as u32)
        }
        (HealthDomain::EngineRuntime, "uptime_sec") => {
            // 5-sample mean uptime > 60s → OK；連續 sample 都 < 60s → WARN。
            // 同樣走 round 避 boundary 上 trunctate 差 0.x 秒誤歸 band。
            if (mean.round() as u64) < 60 {
                HealthState::HealthWarn
            } else {
                HealthState::HealthOk
            }
        }
        // ----- pipeline_throughput (Track B) -----
        // 為什麼 5 metric 各自 hardcode classify：對齊 spec §4.3「先 hardcode；
        // Sprint 5 Tier 1 ArcSwap 熱更新」；threshold 來自 M3 design spec §2.3
        // line 102（per pipeline_throughput.rs classify_pipeline_throughput_*
        // 5 helper）。
        (HealthDomain::PipelineThroughput, "ws_tick_rate_per_sec") => {
            super::domains::pipeline_throughput::classify_pipeline_throughput_ws_tick_rate(mean)
        }
        (HealthDomain::PipelineThroughput, "ws_heartbeat_lag_ms") => {
            // mean.round() 避 truncate 誤歸 band（例 mean=60_000.6ms truncate
            // 為 60_000 漏 CRITICAL；round 為 60_001 正確 CRITICAL）。
            super::domains::pipeline_throughput::classify_pipeline_throughput_heartbeat_lag_ms(
                mean.round() as u32,
            )
        }
        (HealthDomain::PipelineThroughput, "ws_subscription_drift_count") => {
            // count 類 metric round 對齊：例 5-sample [3,3,3,3,2] mean=2.8
            // round=3 為 DEGRADED；truncate=2 誤歸 WARN（per Sprint 2 round 2
            // dispatch 範例）。
            super::domains::pipeline_throughput::classify_pipeline_throughput_subscription_drift(
                mean.round() as u32,
            )
        }
        (HealthDomain::PipelineThroughput, "strategy_signal_rate_per_min") => {
            super::domains::pipeline_throughput::classify_pipeline_throughput_signal_rate(mean)
        }
        (HealthDomain::PipelineThroughput, "ipc_roundtrip_ms_p99") => {
            super::domains::pipeline_throughput::classify_pipeline_throughput_ipc_roundtrip_ms_p99(
                mean,
            )
        }
        // ----- database_pool (Track C) -----
        // 為什麼 4 metric dispatch（per Sprint 2 round 3 MEDIUM-1 C fix Path A）:
        //   - pg_pool_active_conn raw 是 telemetry-only（單值無 max context 不
        //     能 classify ratio）；走 _ => HealthOk fallback 設計上正確，不誤
        //     升 SM state。
        //   - pg_pool_active_conn_ratio 是 ratio 化後的 metric（emitter 端在
        //     `into_metric_rows` 計算 active/max），單值入 classify_aggregated
        //     可用 `classify_database_pool_active_conn_ratio(ratio)` helper。
        //   - 其他 3 metric (wait/queue/disk) 已 round 2 HIGH-1 fix 接通。
        // 為什麼 pg_pool_active_conn raw 仍走 fallback 不刪:
        //   - raw 留 telemetry 觀測語意（V106 row 仍寫 active 數值）；fail-closed
        //     OK band 不會誤升 cascade，且 ratio 路徑已守住真實升階。
        (HealthDomain::DatabasePool, "pg_pool_active_conn_ratio") => {
            // mean 即 5-sample ratio mean，直接走 helper。
            super::domains::database_pool::classify_database_pool_active_conn_ratio(mean)
        }
        (HealthDomain::DatabasePool, "pg_pool_wait_ms_p95") => {
            super::domains::database_pool::classify_database_pool_wait_ms_p95(
                mean.round() as u32,
            )
        }
        (HealthDomain::DatabasePool, "pg_writer_queue_depth") => {
            super::domains::database_pool::classify_database_pool_writer_queue_depth(
                mean.round() as u32,
            )
        }
        (HealthDomain::DatabasePool, "disk_data_dir_used_pct") => {
            // f64 走 helper 不需 cast；mean 即 used pct。
            super::domains::database_pool::classify_database_pool_disk_used_pct(mean)
        }
        // ----- strategy_quality (Track E) -----
        // 為什麼 4 metric dispatch（per Sprint 2 Wave 2 Track E IMPL）:
        //   - 對齊 spec §3.2 StrategyQualitySample 5 field 中 4 個有 ladder
        //     band：fill_rate_intent_ratio / slippage_bps_p95 / decision_lease_
        //     grant_rate / dormant_minutes；signal_count_24h 為 telemetry-only
        //     量（per spec §3.2 + M3 spec line 105 「per-strategy 30d block
        //     bootstrap」threshold pending Sprint 5）走 fallback OK band 不
        //     誤升 SM state（與 database_pool::pg_pool_active_conn raw 一致
        //     fallback 範式）。
        //   - 為什麼 Track E 仍走 classify_aggregated 集中 helper（不自走 dispatch）:
        //     scheduler dispatch 對齊 Track A/B/C 範式（per spec §4.1 step 4
        //     band classify on aggregated value）；Track E `StrategyQualityScheduler`
        //     獨立 run loop 內部仍呼此 helper，保 5-sample mean classify SSOT 不
        //     分裂。
        //   - count 類 metric（dormant_minutes 是 u32 cast 自 f64 mean）走
        //     mean.round() 避 truncate（per Sprint 2 round 2 MEDIUM-2 fix）。
        (HealthDomain::StrategyQuality, "fill_rate_intent_ratio") => {
            super::domains::strategy_quality::classify_strategy_quality_fill_rate_intent_ratio(
                mean,
            )
        }
        (HealthDomain::StrategyQuality, "slippage_bps_p95") => {
            super::domains::strategy_quality::classify_strategy_quality_slippage_bps_p95(mean)
        }
        (HealthDomain::StrategyQuality, "decision_lease_grant_rate") => {
            super::domains::strategy_quality::classify_strategy_quality_decision_lease_grant_rate(
                mean,
            )
        }
        (HealthDomain::StrategyQuality, "dormant_minutes") => {
            // count 類 metric round 對齊 Track A engine_runtime open_fd_count /
            // thread_count 範式（避 truncate 誤歸 band；boundary mean=59.6 → 60
            // 正確 WARN 而非錯歸 OK）。
            super::domains::strategy_quality::classify_strategy_quality_dormant_minutes(
                mean.round() as u32,
            )
        }
        // ----- api_latency (Track D) -----
        // 為什麼 8 metric dispatch（per dispatch packet §5 + spec §3.2 amend）:
        //   - 8 metric 全經 5-sample rolling window mean classify；無「raw
        //     telemetry-only」walk-through metric（對比 database_pool 之
        //     pg_pool_active_conn raw + ratio 並存設計）。
        //   - count 類 metric（ret_code_4xx / ret_code_5xx / ws_dropout_count）
        //     走 mean.round() 避 truncate 誤歸 band（per Sprint 2 round 2
        //     MEDIUM-2 fix 範式）；latency 類（ms p50/p95/p99）也走 round 對齊
        //     ladder boundary（例 p99 mean=2000.4ms truncate=2000 仍屬 DEGRADED；
        //     round=2000 一致；mean=2000.6ms truncate=2000 仍屬 DEGRADED；round=
        //     2001 正確升 CRITICAL）。
        //   - ret_code 4xx/5xx 用 HTTP 標準語意 multi-venue 預留（per ADR-0040
        //     dispatch packet §5.5 反模式 (d)）。
        (HealthDomain::ApiLatency, "rest_p50_ms") => {
            super::domains::api_latency::classify_api_latency_rest_p50_ms(mean.round() as u32)
        }
        (HealthDomain::ApiLatency, "rest_p95_ms") => {
            super::domains::api_latency::classify_api_latency_rest_p95_ms(mean.round() as u32)
        }
        (HealthDomain::ApiLatency, "rest_p99_ms") => {
            super::domains::api_latency::classify_api_latency_rest_p99_ms(mean.round() as u32)
        }
        (HealthDomain::ApiLatency, "ws_rtt_p50_ms") => {
            super::domains::api_latency::classify_api_latency_ws_rtt_p50_ms(mean.round() as u32)
        }
        (HealthDomain::ApiLatency, "ws_rtt_p99_ms") => {
            super::domains::api_latency::classify_api_latency_ws_rtt_p99_ms(mean.round() as u32)
        }
        (HealthDomain::ApiLatency, "ret_code_4xx_count") => {
            super::domains::api_latency::classify_api_latency_ret_code_4xx_count(
                mean.round() as u32,
            )
        }
        (HealthDomain::ApiLatency, "ret_code_5xx_count") => {
            super::domains::api_latency::classify_api_latency_ret_code_5xx_count(
                mean.round() as u32,
            )
        }
        (HealthDomain::ApiLatency, "ws_dropout_count") => {
            super::domains::api_latency::classify_api_latency_ws_dropout_count(
                mean.round() as u32,
            )
        }
        // ----- risk_envelope (Track F) -----
        // 為什麼 5 metric dispatch（per Sprint 2 Wave 2 Track F IMPL + spec
        // §3.2 line 405-415）:
        //   - 5 metric 全經 5-sample rolling window mean classify（25min window）；
        //     對齊 spec §2.1 risk_envelope 300s sample × 5 = 25min 慢動指標
        //     設計（dispatch packet §7.5 反模式 (c) correlation 不可寫死高頻）。
        //   - count 類 metric（position_count_active）走 mean.round() 避 truncate
        //     誤歸 band（對齊 Track A engine_runtime open_fd_count / Track E
        //     dormant_minutes 範式）。
        //   - 浮點 metric（cum_pnl_24h_usd / max_dd_pct / correlation_avg_pairwise
        //     / concentration_top1_pct）直接走 mean，不 round（小數精度有意義）。
        //   - threshold 對齊 M3 design spec §2.3 line 106 ladder；emit DEGRADED
        //     不觸 5-gate kill（per dispatch packet §7.5 反模式 (b)；Sprint 5
        //     Tier 1 才同步 5-gate kill mechanism）。
        (HealthDomain::RiskEnvelope, "portfolio_cum_pnl_24h_usd") => {
            super::domains::risk_envelope::classify_risk_envelope_cum_pnl_24h_usd(mean)
        }
        (HealthDomain::RiskEnvelope, "portfolio_max_dd_pct") => {
            super::domains::risk_envelope::classify_risk_envelope_max_dd_pct(mean)
        }
        (HealthDomain::RiskEnvelope, "position_count_active") => {
            // count 類 metric round 對齊 Track A engine_runtime open_fd_count /
            // thread_count 範式（避 truncate 誤歸 band；boundary mean=8.6 → 9
            // 正確 WARN 而非錯歸 OK）。
            super::domains::risk_envelope::classify_risk_envelope_position_count(
                mean.round() as u32,
            )
        }
        (HealthDomain::RiskEnvelope, "correlation_avg_pairwise") => {
            super::domains::risk_envelope::classify_risk_envelope_correlation_avg(mean)
        }
        (HealthDomain::RiskEnvelope, "concentration_top1_pct") => {
            super::domains::risk_envelope::classify_risk_envelope_concentration_top1_pct(mean)
        }
        // strategy_quality::signal_count_24h raw 走 fallback OK band 屬
        // telemetry-only 設計 per spec §3.2 (Sprint 5 才接 block bootstrap)。
        // 其他 domain 不需擴此 match（Sprint 2 6 domain 全 land）。
        _ => HealthState::HealthOk,
    }
}

// ============================================================
// 測試
// ============================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rolling_window_aggregator_below_capacity_mean_only() {
        let mut agg = RollingWindowAggregator::new("cpu_pct");
        agg.push(10.0);
        agg.push(20.0);
        assert_eq!(agg.current_window_size(), 2);
        assert!((agg.mean().unwrap() - 15.0).abs() < 1e-10);
        // n=2 仍可算 Bessel sigma。
        assert!(agg.sigma().is_some());
    }

    #[test]
    fn test_rolling_window_aggregator_single_sample_no_sigma() {
        let mut agg = RollingWindowAggregator::new("cpu_pct");
        agg.push(50.0);
        assert_eq!(agg.mean(), Some(50.0));
        // n<2 不可算 sigma（fail-closed）。
        assert_eq!(agg.sigma(), None);
    }

    #[test]
    fn test_rolling_window_aggregator_5_sample_bessel_sigma_spec_sample() {
        // 對齊 health/mod.rs `compute_window_stats` 已驗 spec sample：
        //   [10, 20, 30, 25, 15] → mean=20, sample_sigma=sqrt(62.5)≈7.9056941
        let mut agg = RollingWindowAggregator::new("cpu_pct");
        for v in &[10.0, 20.0, 30.0, 25.0, 15.0] {
            agg.push(*v);
        }
        assert_eq!(agg.current_window_size(), 5);
        assert!((agg.mean().unwrap() - 20.0).abs() < 1e-10);
        assert!((agg.sigma().unwrap() - 7.905694150420948).abs() < 1e-10);
    }

    #[test]
    fn test_rolling_window_aggregator_overflow_pops_oldest() {
        let mut agg = RollingWindowAggregator::new("cpu_pct");
        for v in &[10.0, 20.0, 30.0, 40.0, 50.0, 60.0] {
            agg.push(*v);
        }
        // 第 6 個 push 後容量仍 5；最舊 10.0 已 pop；mean = (20+30+40+50+60)/5 = 40.
        assert_eq!(agg.current_window_size(), 5);
        assert!((agg.mean().unwrap() - 40.0).abs() < 1e-10);
    }

    #[test]
    fn test_engine_runtime_sample_classify_cpu_thresholds() {
        // OK <50 / WARN 50-80 / DEGRADED >=80。
        assert_eq!(classify_engine_runtime_cpu_pct(0.0), HealthState::HealthOk);
        assert_eq!(classify_engine_runtime_cpu_pct(49.9), HealthState::HealthOk);
        assert_eq!(classify_engine_runtime_cpu_pct(50.0), HealthState::HealthWarn);
        assert_eq!(
            classify_engine_runtime_cpu_pct(79.9),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_engine_runtime_cpu_pct(80.0),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_engine_runtime_cpu_pct(99.9),
            HealthState::HealthDegraded
        );
    }

    #[test]
    fn test_engine_runtime_sample_classify_rss_thresholds() {
        // OK <=2048 / WARN 2048-4096 / DEGRADED >4096。
        assert_eq!(classify_engine_runtime_rss_mb(0.0), HealthState::HealthOk);
        assert_eq!(classify_engine_runtime_rss_mb(2048.0), HealthState::HealthOk);
        assert_eq!(
            classify_engine_runtime_rss_mb(2048.1),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_engine_runtime_rss_mb(4096.0),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_engine_runtime_rss_mb(4096.1),
            HealthState::HealthDegraded
        );
    }

    #[test]
    fn test_engine_runtime_sample_into_metric_rows_6_metrics() {
        let snapshot = EngineRuntimeSample {
            cpu_pct: 30.0,
            rss_mb: 1024.0,
            heartbeat_alive: true,
            open_fd_count: 128,
            thread_count: 64,
            uptime_sec: 3600,
        };
        let rows = snapshot.into_metric_rows();
        assert_eq!(rows.len(), 6);
        let names: Vec<&'static str> = rows.iter().map(|r| r.metric_name).collect();
        assert_eq!(
            names,
            vec![
                "cpu_pct",
                "rss_mb",
                "heartbeat_alive",
                "open_fd_count",
                "thread_count",
                "uptime_sec",
            ]
        );
        // 全 metric OK band。
        for r in &rows {
            assert_eq!(r.band, HealthState::HealthOk);
        }
    }

    #[test]
    fn test_engine_runtime_sample_heartbeat_dead_critical() {
        let snapshot = EngineRuntimeSample {
            cpu_pct: 30.0,
            rss_mb: 1024.0,
            heartbeat_alive: false,
            open_fd_count: 128,
            thread_count: 64,
            uptime_sec: 3600,
        };
        let rows = snapshot.into_metric_rows();
        let hb_row = rows.iter().find(|r| r.metric_name == "heartbeat_alive").unwrap();
        assert_eq!(hb_row.band, HealthState::HealthCritical);
        assert_eq!(hb_row.value, 0.0);
    }
}
