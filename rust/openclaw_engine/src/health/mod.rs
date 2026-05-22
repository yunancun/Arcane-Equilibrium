//! M3 Health Monitoring — 4-state ladder + 6 health domain + amplification cap。
//!
//! MODULE_NOTE
//! 模塊用途：
//!   提供 M3 集中健康觀測層的 Rust 主入口。Sprint 1A-ζ Track B spike 期只 IMPL
//!   `engine_runtime` 1 個 domain；Sprint 2 Track A 升級為「sysinfo-backed
//!   6 metric 採樣 + V106 writer 真實接線 + event bus 預埋 cascade subscribe
//!   + observe_classified 新入口 + D3 cascade reject log emit minimal」；
//!   其餘 5 domain (pipeline_throughput / database_pool / api_latency /
//!   strategy_quality / risk_envelope) 由 Track B/C/D/E/F Wave 1/2 沿用本
//!   scaffold 各 IMPL。state machine 對齊 M3 design spec §3.3 dwell time +
//!   flap suppression 規範；amplification cap 對齊 ADR-0042 Decision 4 +
//!   ADR-0036 1-anomaly = 1-state-change/24h 規範。
//!
//! 主要類 / 函數：
//!   - `HealthState` enum (HEALTH_OK / WARN / DEGRADED / CRITICAL)
//!   - `HealthDomain` enum (engine_runtime + 5 stub)
//!   - `M3Error` 統一錯誤類型
//!   - `HealthStateMachine` 4-state ladder + dwell time + amp cap +
//!      observe_classified（Sprint 2 新 API）+ previous_state accessor
//!   - `EngineRuntimeMetric` 採樣輸入 struct（spike Track B 既有；保 backward
//!      compat）
//!   - Sprint 2 sub-module：
//!     - `metric_emitter`：DomainEmitter trait + MetricSample trait +
//!        RollingWindowAggregator + MetricEmitterScheduler + EngineRuntimeEmitter
//!     - `writer`：HealthObservationWriter trait + PgHealthObservationWriter +
//!        InMemoryHealthObservationWriter
//!     - `event_bus`：HealthStateChangeEvent + HealthEventBus（Sprint 5 cascade
//!        subscribe 預埋）
//!
//! 依賴：
//!   - std + tokio + sysinfo（Sprint 2 加）+ sqlx + chrono + uuid + parking_lot。
//!   - 不依賴 trading hot path / GovernanceHub / risk_config 既有 IMPL；emitter
//!     只觀測。
//!
//! 硬邊界：
//!   - 4-state ladder 對齊 V106 schema (state TEXT CHECK 4 值)。
//!   - amplification_loop_24h_count 計數對齊 V106 schema column。
//!   - Cascade gate cap (8 action / 1 cascade per ADR-0042 Decision 5) Sprint 2
//!     不接 cascade 執行；event bus 只發佈，subscriber 由 Sprint 5 Tier 1 接。
//!   - HEALTH_CATASTROPHIC 由 5-gate kill 觸發；M3 4-state ladder 只到
//!     CRITICAL (per ADR-0042 Decision 6 + Decision 2)。
//!   - production binary 0 mock time 滲透：`spike` feature 嚴守隔絕；Sprint 2
//!     新 module 不 carry spike feature flag。
//!   - sysinfo 跨平台原生支援 Mac+Linux（per `feedback_cross_platform` +
//!     `project_mac_deployment_target`）；不寫死 `cfg(target_os="linux")` 分支。

pub mod event_bus;
pub mod metric_emitter;
pub mod writer;

use std::collections::HashMap;
use std::time::{Duration, Instant};

/// M3 模塊統一錯誤類型。
#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum M3Error {
    /// from_str 解析到未知的 health state 字串 (對齊 V106 CHECK 4 值)。
    #[error("unknown health state literal: {0}")]
    UnknownHealthState(String),

    /// from_str 解析到未知的 health domain 字串 (對齊 V106 CHECK 6 值)。
    #[error("unknown health domain literal: {0}")]
    UnknownHealthDomain(String),

    /// spike scope 只 IMPL engine_runtime; 其餘 5 domain 走此錯誤（Track B-F
    /// IMPL 接到後 caller 不再撞此 variant）。
    #[error("domain not implemented in spike scope: {0}")]
    DomainNotImplemented(String),

    /// emitter sample 失敗（sysinfo read / pool stats query / Bybit p95 query
    /// 取值失敗）；caller 端 fail-soft 寫 V106 sample_error row，state 維持當前。
    /// per Sprint 2 spec §4.1 step 1 fail-closed default。
    #[error("sample collection failed: {0}")]
    SampleError(String),

    /// V106 INSERT writer 寫入失敗（sqlx error / connection drop / constraint
    /// violation）；caller 端 fail-soft log + continue sample loop。
    /// per Sprint 2 spec §3.1 writer trait 失敗語意。
    #[error("V106 INSERT failed: {0}")]
    WriterError(String),
}

/// 4 級健康狀態階梯 (per ADR-0042 Decision 2 + V106 schema state CHECK)。
///
/// 為什麼:
///   ADR-0042 Decision 2 規定 4 級階梯 OK < WARN < DEGRADED < CRITICAL;
///   HEALTH_CATASTROPHIC 由 5-gate kill 觸發,不在本 enum 範圍 (Decision 6)。
///
/// 為什麼 Serialize/Deserialize:
///   Sprint 2 event_bus `HealthStateChangeEvent` 跨進程廣播（Sprint 5 cascade
///   subscribe 可能跨 IPC），需 serde 序列化；對齊 V106 schema state column
///   的 `as_str()` 字串 round-trip。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
pub enum HealthState {
    /// 全 OK band; 正常 trading。
    HealthOk,
    /// 至少 1 metric 在 WARN band; alert only, 不影響 trading。
    HealthWarn,
    /// 至少 1 metric 在 DEGRADED band; 觸發 cascade (LAL Tier 降階 / Tier 1
    /// reparam halt) per ADR-0042 Decision 2。
    HealthDegraded,
    /// 至少 1 metric 在 CRITICAL band; halt new orders + drain existing per
    /// 5-gate kill 既有 mechanism (ADR-0042 Decision 6)。
    HealthCritical,
}

impl HealthState {
    /// 對齊 V106 schema state TEXT CHECK 4 值的字串轉換。
    ///
    /// 為什麼: writer 寫 V106 row 時必用 enum 字串 (HEALTH_OK / HEALTH_WARN /
    /// HEALTH_DEGRADED / HEALTH_CRITICAL)。as_str 保證 Rust enum ↔ PG row 對齊。
    pub fn as_str(&self) -> &'static str {
        match self {
            HealthState::HealthOk => "HEALTH_OK",
            HealthState::HealthWarn => "HEALTH_WARN",
            HealthState::HealthDegraded => "HEALTH_DEGRADED",
            HealthState::HealthCritical => "HEALTH_CRITICAL",
        }
    }

    /// 從 V106 row 字串還原 Rust enum (replay / cross-language fixture 用)。
    ///
    /// 為什麼: H-18 cross-language 1e-4 fixture harness 需 Rust ↔ Python 對等;
    /// from_str 為 round-trip 保證 (M11 replay 也走此路徑)。
    pub fn from_str(s: &str) -> Result<Self, M3Error> {
        match s {
            "HEALTH_OK" => Ok(HealthState::HealthOk),
            "HEALTH_WARN" => Ok(HealthState::HealthWarn),
            "HEALTH_DEGRADED" => Ok(HealthState::HealthDegraded),
            "HEALTH_CRITICAL" => Ok(HealthState::HealthCritical),
            other => Err(M3Error::UnknownHealthState(other.to_string())),
        }
    }

    /// 嚴重度數值 (越大越嚴; 對齊 ADR-0042 Decision 2 OK < WARN < DEGRADED <
    /// CRITICAL 偏序)。aggregate 場景用 max(state) 取 system-level state。
    pub fn severity_value(&self) -> u8 {
        match self {
            HealthState::HealthOk => 0,
            HealthState::HealthWarn => 1,
            HealthState::HealthDegraded => 2,
            HealthState::HealthCritical => 3,
        }
    }
}

/// 6 health domain (per ADR-0042 Decision 3 + V106 schema domain CHECK 6 值)。
///
/// 為什麼:
///   ADR-0042 Decision 3 規定 6 domain 覆蓋 Process / Pipeline / Business 三層;
///   spike scope 只 IMPL `EngineRuntime`,其餘 5 走 `unimplemented!()` 隔絕在
///   `evaluate()` 內 (state machine struct 仍 carry 所有 6 個 domain 標籤,
///   便於未來 Sprint 2 metric emitter 擴充)。
///
/// 為什麼 Serialize/Deserialize:
///   Sprint 2 event_bus 廣播 + Sprint 5 cascade subscribe 跨進程通信時 V106
///   row 字串 round-trip 需 serde；對齊 `as_str()` / `from_str()` 既有 contract。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
pub enum HealthDomain {
    /// Process 層: engine PID alive + CPU% + RSS。spike scope IMPL 此 domain。
    EngineRuntime,
    /// Pipeline 層: WS tick rate + IPC roundtrip + heartbeat lag。stub。
    PipelineThroughput,
    /// Pipeline 層: PG writer queue depth + pool wait + disk usage。stub。
    DatabasePool,
    /// Pipeline 層: Bybit REST success rate + p95 + WS dropout count。stub。
    ApiLatency,
    /// Business 層: per-strategy fill rate + slippage + dormant minutes。stub。
    StrategyQuality,
    /// Business 層: portfolio cum loss + dd + correlation + concentration。stub。
    RiskEnvelope,
}

impl HealthDomain {
    /// 對齊 V106 schema domain TEXT CHECK 6 值字串。
    pub fn as_str(&self) -> &'static str {
        match self {
            HealthDomain::EngineRuntime => "engine_runtime",
            // 注意: spike scope 仍出字串對齊 V106 CHECK 6 值,但 evaluate 走
            // unimplemented;writer 端不會在 spike 期 emit 這 5 個 domain row。
            HealthDomain::PipelineThroughput => "pipeline_throughput",
            HealthDomain::DatabasePool => "database_pool",
            HealthDomain::ApiLatency => "api_latency",
            HealthDomain::StrategyQuality => "strategy_quality",
            HealthDomain::RiskEnvelope => "risk_envelope",
        }
    }

    /// V106 row 字串 → enum 還原。
    pub fn from_str(s: &str) -> Result<Self, M3Error> {
        match s {
            "engine_runtime" => Ok(HealthDomain::EngineRuntime),
            "pipeline_throughput" => Ok(HealthDomain::PipelineThroughput),
            "database_pool" => Ok(HealthDomain::DatabasePool),
            "api_latency" => Ok(HealthDomain::ApiLatency),
            "strategy_quality" => Ok(HealthDomain::StrategyQuality),
            "risk_envelope" => Ok(HealthDomain::RiskEnvelope),
            other => Err(M3Error::UnknownHealthDomain(other.to_string())),
        }
    }

    /// spike scope IMPL guard: 只 EngineRuntime 走真實邏輯; 其他 5 走 fail-loud。
    ///
    /// 為什麼: dispatch packet §2.7(a) 反模式禁止「多 domain 同時 IMPL」; 本
    /// guard 在 state machine evaluate 入口 fail-loud,確保 spike 期不誤啟。
    pub fn require_implemented(&self) -> Result<(), M3Error> {
        match self {
            HealthDomain::EngineRuntime => Ok(()),
            other => Err(M3Error::DomainNotImplemented(other.as_str().to_string())),
        }
    }
}

/// Engine runtime domain 採樣 metric (per ADR-0042 Decision 3 line 69 + M3 spec
/// §2.3 line 75-77 engine_runtime row)。
///
/// 為什麼這 3 個 metric: 進程級基線最小集 (CPU% / RSS / heartbeat); 30s 採樣
/// 對齊 M3 spec §2.3 sample interval。
#[derive(Debug, Clone, Copy)]
pub struct EngineRuntimeMetric {
    /// engine 進程 CPU 使用率 (0.0 - 100.0)。
    pub cpu_pct: f64,
    /// engine 進程 RSS (MB)。
    pub rss_mb: f64,
    /// engine IPC heartbeat 是否最近 30s 內看到 (true = alive, false = stale)。
    pub heartbeat_alive: bool,
}

impl EngineRuntimeMetric {
    /// 評估這個 metric 落在哪個 band。per M3 spec §2.3 engine_runtime row:
    ///   OK    : PID alive + RSS < 2GB + CPU < 50%
    ///   WARN  : RSS 2-4GB OR CPU 50-80%
    ///   DEGRADED: RSS > 4GB OR CPU > 80% 持續 5min
    ///   CRITICAL: PID dead OR engine restart loop > 3/5min
    ///
    /// 為什麼簡化: spike scope 只測 amplification cap 24h fire path; dwell
    /// time 5min DEGRADED logic 由 HealthStateMachine 集中處理,本 method 只
    /// 評估「當下 metric 屬於哪 band」(無時間維度)。
    pub fn classify_band(&self) -> HealthState {
        // heartbeat dead 立即 CRITICAL (per spec §2.3 "PID dead" 對齊)。
        if !self.heartbeat_alive {
            return HealthState::HealthCritical;
        }
        // RSS / CPU degraded band。
        if self.rss_mb > 4096.0 || self.cpu_pct > 80.0 {
            return HealthState::HealthDegraded;
        }
        // RSS / CPU warn band。
        if self.rss_mb > 2048.0 || self.cpu_pct > 50.0 {
            return HealthState::HealthWarn;
        }
        HealthState::HealthOk
    }
}

/// 單個 anomaly_id 在 24h rolling window 的觸發紀錄 (per ADR-0042 Decision 4)。
///
/// 為什麼: amplification cap key = anomaly_id; 同 anomaly_id 24h 內最多觸發
/// 1 次 state transition; key 24h 過期 reset。
#[derive(Debug, Clone, Copy)]
struct AmpCapEntry {
    /// 該 anomaly_id 第一次觸發 state transition 的 Instant。
    first_triggered_at: Instant,
}

/// M3 4-state ladder 狀態機 (per ADR-0042 Decision 2 + M3 spec §3.3 dwell time
/// + flap suppression + Decision 4 amplification cap)。
///
/// 為什麼此設計:
///   - 單 (domain × metric_name) 一個 state machine 實例 (system-level state =
///     max severity of all per-(domain, metric_name) state, 對齊 M3 spec §3.4)。
///   - dwell time 60s OK→WARN / 5min WARN→DEGRADED (per spec §3.3 升階 dwell);
///     spike Track B IMPL OK→WARN dwell 60s + WARN 維持 + amp cap fire 路徑;
///     Sprint 2 Track A `observe_classified` 新入口補齊 WARN→DEGRADED /
///     DEGRADED→CRITICAL / recovery dwell / WARN→OK 15min 五條 transition。
///   - amp cap: 同一 anomaly_id 24h 內最多 1 次 state transition fire;
///     amplification_loop_24h_count 對齊 V106 schema column 嚴格語意 —
///     **transition 真實 fire 計數** (state_prev != target_state 才計入);
///     同 anomaly_id 反覆採樣 (current==target) 不計 fire 也不 insert entry。
///   - V106 spec §1.1 line 77 fail-closed ≥ 2 reject 規範: 同 domain 24h 內
///     transition fired count ≥ 2 後,新 fire request reject (return false +
///     count 不再增);Sprint 2 Track A D3 cascade reject log emit minimal IMPL
///     在 caller 端寫 V106 row evidence_json.reject_reason audit trail。
///   - flap suppression: 24h 內 WARN ↔ OK > 3 次 → lock WARN 直到 1h 全 OK
///     (per spec §3.3); Sprint 2 不接 flap suppression（Sprint 5 cascade 才接）。
pub struct HealthStateMachine {
    domain: HealthDomain,
    /// 當前 active state。
    current_state: HealthState,
    /// transition 前 state（previous_state accessor 用，Sprint 2 cascade reject
    /// 寫 V106 row state_prev 對齊）。
    previous_state: HealthState,
    /// 進入當前 state 的時間 (用於 dwell time 計算)。
    /// Sprint 2 `observe_classified` 用此計算升階 dwell + recovery dwell。
    state_entered_at: Instant,
    /// 最近一次採樣到 WARN-band 的時間 (用於 OK→WARN 60s dwell 判斷)。
    warn_band_seen_at: Option<Instant>,
    /// 最近一次採樣到 DEGRADED-band 的時間 (用於 WARN→DEGRADED 5min dwell)。
    degraded_band_seen_at: Option<Instant>,
    /// 最近一次採樣到 CRITICAL-band 的時間 (用於 DEGRADED→CRITICAL 5min dwell)。
    critical_band_seen_at: Option<Instant>,
    /// 最近一次採樣到 OK-band 的時間 (用於 WARN→OK 15min / DEGRADED→WARN 30min
    /// recovery dwell)。
    recovery_band_seen_at: Option<Instant>,
    /// amplification cap: anomaly_id → 第一次 fire state transition 的時間。
    /// 嚴格語意: 只在「真實 transition fire」(current_state != target_state)
    /// 時才 insert; 同 id 反覆採樣不重 insert。24h 過期 retain 清理。
    amp_cap_entries: HashMap<String, AmpCapEntry>,
    /// 24h window state transition fire 計數 (對齊 V106 schema
    /// amplification_loop_24h_count column 嚴格語意); writer 端讀此值寫入新 row。
    /// **嚴格 = transition fire 計數**,不是「unique seen anomaly_id 計數」。
    /// retain 過期 entry 同步重算 = amp_cap_entries.len()。
    amplification_loop_24h_count: u32,
    /// 最近一次 transition fire（升階或 recovery）時 prev state 的 dwell 秒數。
    ///
    /// 為什麼存此值（per Sprint 2 Wave 1 round 2 MEDIUM-2 fix）:
    ///   - V106 schema `dwell_time_sec INTEGER` 需 emitter scheduler 端在 fire 時
    ///     寫真實 dwell（OK 60s / WARN 5min 等），原 IMPL hardcode 0 違反 spec。
    ///   - SM 內部知道 prev state_entered_at + fire 時 now Instant，最自然在
    ///     fire branch 計算後緩存，emitter 端讀 accessor 寫 V106 row。
    ///   - fire 之外（reject / dwell 未達 / 同 state）此值不更新；emitter 端
    ///     `fired=false` 時不寫 dwell（with_transition 不調用）。
    last_transition_dwell_secs: u32,
}

impl HealthStateMachine {
    /// 建立新的 state machine 實例。Sprint 2 後 6 domain 全 IMPL；
    /// `observe_classified` 新入口（per spec §5.2）不再 require_implemented，
    /// `observe` 既有入口仍 fail-loud 對齊 spike Track B backward compat。
    pub fn new(domain: HealthDomain) -> Self {
        Self {
            domain,
            current_state: HealthState::HealthOk,
            previous_state: HealthState::HealthOk,
            state_entered_at: Instant::now(),
            warn_band_seen_at: None,
            degraded_band_seen_at: None,
            critical_band_seen_at: None,
            recovery_band_seen_at: None,
            amp_cap_entries: HashMap::new(),
            amplification_loop_24h_count: 0,
            last_transition_dwell_secs: 0,
        }
    }

    /// 觀察當前 metric, 評估是否觸發 state transition (使用 std::time::Instant::now)。
    ///
    /// 為什麼此入口:
    ///   - production runtime entry: 內部呼 observe_at 並餵 Instant::now()。
    ///   - dispatch packet §2.7(a) 反模式禁止多 domain 同時 IMPL; require_implemented
    ///     guard 確保 spike 期不誤啟 5 stub domain;
    ///   - anomaly_id 是 caller 提供的 cap key (per ADR-0042 Decision 4 cap key =
    ///     `(anomaly_source, anomaly_signature_hash)`); spike 期用單一 id "engine_cpu_spike"
    ///     做 24h 反向 verify。
    ///   - 返回值 bool: true = state 真的 transitioned;false = 維持當前 state
    ///     (包含 cap suppress 情境)。
    pub fn observe(
        &mut self,
        metric: EngineRuntimeMetric,
        anomaly_id: &str,
    ) -> Result<bool, M3Error> {
        self.observe_at(metric, anomaly_id, Instant::now())
    }

    /// 與 `observe` 等價但接受外部 `now: Instant`, spike test 注入虛擬時間用。
    ///
    /// 為什麼分開:
    ///   - tokio::time::pause / advance 推進 tokio 虛擬 clock; std::time::Instant
    ///     對其無感知 (real monotonic clock 不會 hop)。
    ///   - spike test 直接呼叫 observe_at 注入 mock Instant (透過 add Duration),
    ///     避免 spike feature 滲透 production observe() 路徑。
    ///   - production code path observe() 仍用 std::time::Instant::now() →
    ///     0 production code path 受 spike feature 污染。
    pub fn observe_at(
        &mut self,
        metric: EngineRuntimeMetric,
        anomaly_id: &str,
        now: Instant,
    ) -> Result<bool, M3Error> {
        // spike scope guard: 只 EngineRuntime 走真實邏輯。
        self.domain.require_implemented()?;

        let band = metric.classify_band();

        // 24h amp cap 過期清理: 移除 first_triggered_at 已超 24h 的 entry。
        let day = Duration::from_secs(24 * 3600);
        self.amp_cap_entries
            .retain(|_, entry| now.duration_since(entry.first_triggered_at) <= day);

        // 嚴格語意: amplification_loop_24h_count = transition fire 計數;
        // entry 1:1 對應 fire, retain 後 entries.len() 即為 24h window 內仍有效
        // 的 fire 數 (對齊 V106 schema column 含義 per spec §1.1 line 77)。
        self.amplification_loop_24h_count = self.amp_cap_entries.len() as u32;

        // dwell-time 邏輯 (spike scope: 只 IMPL OK → WARN 60s dwell;
        // WARN → DEGRADED 5min dwell + cascade 不在 spike scope)。
        match (self.current_state, band) {
            // OK → WARN-band 採樣到, 開始 dwell 計時。
            (HealthState::HealthOk, HealthState::HealthWarn)
            | (HealthState::HealthOk, HealthState::HealthDegraded)
            | (HealthState::HealthOk, HealthState::HealthCritical) => {
                // 為什麼 if let: 對 None 場景 fail-closed 走「初次採樣 → 記時間」
                // 路徑, 不可用 unwrap() (對 Sprint 5 cascade IMPL 改錯不安全)。
                if let Some(seen) = self.warn_band_seen_at {
                    // dwell time 60s 持續 WARN-band → 觸發 transition (受 amp
                    // cap 約束)。
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
            }
            // OK → 採樣回 OK-band, 清除 warn_band_seen_at。
            (HealthState::HealthOk, HealthState::HealthOk) => {
                self.warn_band_seen_at = None;
                Ok(false)
            }
            // WARN 維持: current 已是 WARN target 也是 WARN → 不算 transition
            // fire (per V106 spec §1.1 line 77 嚴格語意: 「state_prev → state
            // transitions」必須 state_prev != state 才算)。同 anomaly_id 在
            // 24h cap 內反覆採樣不計入 entries / count; 不同 anomaly_id 在已
            // WARN 場景也不 fire (沒新 transition, no new fire to cap)。
            // WARN → DEGRADED 5min dwell 邏輯 Sprint 5 Tier 1 IMPL 時補。
            (HealthState::HealthWarn, _) => Ok(false),
            // 其他 transition (DEGRADED/CRITICAL recovery / etc.) 不在 spike scope。
            _ => Ok(false),
        }
    }

    /// 受 amp cap 約束的 state transition fire 嘗試 (per ADR-0042 Decision 4 +
    /// V106 spec §1.1 line 77 嚴格 fail-closed ≥ 2 reject 語意)。
    ///
    /// 為什麼此語意:
    ///   - 1-anomaly = 1-state-change/24h (per ADR-0042 Decision 4): 同 anomaly_id
    ///     在 24h cap window 內最多 fire 1 次 state transition; entry 存在 →
    ///     suppress 返回 false 不 fire,不增 count。
    ///   - state_prev != target_state 才算 transition fire (per V106 spec §1.1
    ///     line 77 「state_prev → state transitions」嚴格語意); 同 state 重觸
    ///     不算 fire,**不 insert entry**,不增 count, 返回 false。
    ///   - V106 spec ≥ 2 fail-closed reject: 同 domain 24h 內 fire 數 ≥ 2 後新
    ///     fire request 走 fail-closed: 不 insert entry, 不 fire, 不 increment
    ///     count, 返回 false。實際 emit fail-closed log + WARN row 由 Sprint 5
    ///     cascade IMPL 接 (本 IMPL 只在 state machine 層回 false; writer 端
    ///     觀察 count 不增即可推斷 reject 發生)。
    ///   - 真實 fire (新 transition + 未撞 ≥ 2 cap): insert entry, count++,
    ///     set current_state, return true。
    fn try_transition_with_cap(
        &mut self,
        target_state: HealthState,
        anomaly_id: &str,
        now: Instant,
    ) -> Result<bool, M3Error> {
        // 同 anomaly_id 已在 24h cap window 內 fire 過 → suppress, 不 fire。
        if self.amp_cap_entries.contains_key(anomaly_id) {
            return Ok(false);
        }

        // current == target → 沒有 transition fire 發生 (per V106 spec §1.1
        // line 77 「state_prev → state transitions」需 state_prev != state),
        // 不 insert entry, 不增 count。
        if self.current_state == target_state {
            return Ok(false);
        }

        // V106 spec §1.1 line 77 fail-closed ≥ 2 reject: 同 domain 24h 內已
        // fire ≥ 2 次, 新 fire request reject。本 IMPL 只在 state machine 層
        // 回 false; Sprint 5 cascade IMPL 接 emit fail-closed log + HEALTH_WARN
        // row。spike scope 不真實 emit log, 僅校驗 count 不再增。
        if self.amplification_loop_24h_count >= 2 {
            return Ok(false);
        }

        // 真實 fire: insert entry + count++ + set state。
        self.amp_cap_entries.insert(
            anomaly_id.to_string(),
            AmpCapEntry {
                first_triggered_at: now,
            },
        );
        self.amplification_loop_24h_count = self.amp_cap_entries.len() as u32;
        // dwell_secs 必須在 state_entered_at 被覆寫前計算（per Sprint 2 round 2
        // MEDIUM-2 fix）：prev state 從 state_entered_at 至 now 的駐留秒數。
        let dwell_secs = now
            .saturating_duration_since(self.state_entered_at)
            .as_secs();
        self.last_transition_dwell_secs = dwell_secs.min(i32::MAX as u64) as u32;
        self.previous_state = self.current_state;
        self.current_state = target_state;
        self.state_entered_at = now;
        // 升階成功後清 dwell 計時 anchor（下次升階重新計時）。
        self.warn_band_seen_at = None;
        self.degraded_band_seen_at = None;
        self.critical_band_seen_at = None;
        self.recovery_band_seen_at = None;
        Ok(true)
    }

    /// 當前 state 查詢 (test + writer 用)。
    pub fn current_state(&self) -> HealthState {
        self.current_state
    }

    /// 當前 amplification cap 計數 (對齊 V106 row column)。
    pub fn amplification_loop_24h_count(&self) -> u32 {
        self.amplification_loop_24h_count
    }

    /// transition 前 state（Sprint 2 cascade reject log emit 寫 V106 row
    /// state_prev 對齊用）。
    pub fn previous_state(&self) -> HealthState {
        self.previous_state
    }

    /// 進入當前 state 的時間（dwell time 計算 + audit 用）。
    pub fn state_entered_at(&self) -> Instant {
        self.state_entered_at
    }

    /// 當前 domain（emitter scheduler 端 INSERT row.domain 用）。
    pub fn domain(&self) -> HealthDomain {
        self.domain
    }

    /// 最近一次 fire 時 prev state 的 dwell 秒數（per Sprint 2 round 2 MEDIUM-2
    /// fix）。
    ///
    /// 為什麼此 accessor:
    ///   - V106 schema `dwell_time_sec INTEGER` 需 emitter scheduler 在 fire 時
    ///     寫真實 dwell；SM fire branch 內部已計算並緩存，emitter 端讀此值。
    ///   - fire 之外（reject / dwell 未達 / 同 state）此值保留上次 fire 結果，
    ///     emitter 端 `fired=false` 時不調用 with_transition 寫此值。
    pub fn last_transition_dwell_secs(&self) -> u32 {
        self.last_transition_dwell_secs
    }

    /// 查詢某 anomaly_id 是否已在 24h amp cap window 內 fire 過（per Sprint 2
    /// round 2 HIGH-1 fix）。
    ///
    /// 為什麼此 accessor:
    ///   - emitter scheduler 推斷 cascade reject_reason 時，需區分 「guard 1
    ///     same-anomaly suppress」與「guard 3 ≥2 fail-closed」；原 IMPL 用
    ///     `prev_count` 推斷在 count=2 + same anomaly_id 場景會誤標 fail-closed。
    ///   - 真實準則 = 此 anomaly_id 是否已在 cap entries 內；此 accessor 直接讓
    ///     emitter 端做精確分流。
    ///   - 不暴露 entries map 本體（封裝），只暴露查詢結果。
    pub fn is_anomaly_capped(&self, anomaly_id: &str) -> bool {
        self.amp_cap_entries.contains_key(anomaly_id)
    }

    /// 當前 cap entry 數 (test 用)。
    #[cfg(any(test, feature = "spike"))]
    pub fn amp_cap_entry_count(&self) -> usize {
        self.amp_cap_entries.len()
    }

    /// Sprint 2 Track A 新 API（per spec §5.2 ladder transition matrix）。
    ///
    /// 為什麼此入口存在:
    ///   - spike Track B `observe()` API 內含 band classify（從 EngineRuntimeMetric
    ///     計算）；Sprint 2 把 classify 移到 emitter / scheduler 端（per spec
    ///     §4.1 step 2），SM 只負責 ladder transition 決策。
    ///   - 6 domain 共用 `observe_classified` 入口：caller 傳已 classify 的
    ///     band + anomaly_id + now Instant；SM 自走 ladder transition matrix。
    ///   - 不再 `require_implemented`：Track B-F 共用 SM；spike `observe()` 仍
    ///     fail-loud 對齊 spike Track B backward compat。
    ///
    /// ladder transition matrix（per spec §5.2）:
    ///   升階（with dwell time）:
    ///     - OK → WARN  : dwell 60s
    ///     - OK → DEGRADED: 過 WARN 中繼 → 先升 WARN dwell 60s（單 sample 不
    ///       跳階）
    ///     - WARN → DEGRADED: dwell 5min
    ///     - DEGRADED → CRITICAL: dwell 5min
    ///   recovery（with dwell time）:
    ///     - WARN → OK: 15min OK-band dwell
    ///     - DEGRADED → WARN: 30min OK-or-WARN-band dwell
    ///     - CRITICAL → DEGRADED: 30min + operator manual unlock（Sprint 5
    ///       才接 manual unlock；本 IMPL CRITICAL 不自動 recovery）
    ///   同 state 採樣: no fire
    ///
    /// 返回值:
    ///   Ok(true)  = transition 真實 fire（state 變化 + V106 row state_prev/
    ///                dwell_time_sec 應寫入）
    ///   Ok(false) = transition 未 fire（dwell 未到 / 同 state / cap suppress /
    ///                ≥2 fail-closed reject）
    ///   Err(_)    = SM 內部錯誤（極少；現 IMPL 不會 fire）
    pub fn observe_classified(
        &mut self,
        band: HealthState,
        anomaly_id: &str,
        now: Instant,
    ) -> Result<bool, M3Error> {
        // 24h amp cap retain 過期清理（per spike Track B 既有語意）。
        let day = Duration::from_secs(24 * 3600);
        self.amp_cap_entries
            .retain(|_, entry| now.duration_since(entry.first_triggered_at) <= day);
        self.amplification_loop_24h_count = self.amp_cap_entries.len() as u32;

        use HealthState::{HealthCritical, HealthDegraded, HealthOk, HealthWarn};
        match (self.current_state, band) {
            // 同 state 採樣：OK→OK 清升階 anchor 避過期。
            //
            // 為什麼不清 recovery_band_seen_at（per Sprint 2 round 2 LOW-2 fix）:
            //   current=OK 不存在 recovery dwell；anchor 是 None 因 fire 時清
            //   過，這裡再清屬冗餘且設計上多餘。
            (HealthOk, HealthOk) => {
                self.warn_band_seen_at = None;
                self.degraded_band_seen_at = None;
                self.critical_band_seen_at = None;
                Ok(false)
            }
            // 同 state 高 band 採樣：current 已是 WARN/DEGRADED/CRITICAL，新採樣
            // 仍在同 band。此分支須打斷 recovery dwell（per Sprint 2 round 2
            // HIGH-2 fix）：
            //   spec §5.2「持續 15min OK-band dwell」要求 recovery 期間必須
            //   全 OK，中間出現高 band 採樣立即作廢 anchor，否則 [OK, WARN, OK]
            //   序列會把首個 OK 當 recovery 起點，第二個 OK 時 t < 15min 卻
            //   錯誤 fire recovery。
            (HealthWarn, HealthWarn)
            | (HealthDegraded, HealthDegraded)
            | (HealthCritical, HealthCritical) => {
                self.recovery_band_seen_at = None;
                Ok(false)
            }

            // 升階：OK → WARN (dwell 60s)
            //
            // 為什麼 reset recovery_band_seen_at（per Sprint 2 round 2 HIGH-2 fix）:
            //   current=OK 時 recovery anchor 該為 None；但 Track B-F 沿用此
            //   scaffold 時若 SM 進入過更高 state 後回 OK，再被高 band 採樣
            //   打斷，anchor 必須清零避過期。寫成顯式 reset 對齊不對稱清理 fix。
            (HealthOk, HealthWarn) => {
                self.recovery_band_seen_at = None;
                self.try_dwell_then_transition(
                    HealthWarn,
                    anomaly_id,
                    now,
                    Duration::from_secs(60),
                    BandKind::Warn,
                )
            }
            // 升階：OK → DEGRADED/CRITICAL：先升 WARN（dwell 60s WARN 中繼），
            // 不單 sample 跳階（per spec §5.2 升階矩陣）。
            (HealthOk, HealthDegraded) | (HealthOk, HealthCritical) => {
                self.recovery_band_seen_at = None;
                self.try_dwell_then_transition(
                    HealthWarn,
                    anomaly_id,
                    now,
                    Duration::from_secs(60),
                    BandKind::Warn,
                )
            }
            // 升階：WARN → DEGRADED/CRITICAL (dwell 5min DEGRADED 中繼)
            //
            // 為什麼 reset recovery_band_seen_at:
            //   recovery dwell 是「持續 OK-band」的 anchor；升階打斷代表這段
            //   recovery 期已被破壞，下次回 OK 需重新累積 dwell。
            (HealthWarn, HealthDegraded) | (HealthWarn, HealthCritical) => {
                self.recovery_band_seen_at = None;
                self.try_dwell_then_transition(
                    HealthDegraded,
                    anomaly_id,
                    now,
                    Duration::from_secs(300),
                    BandKind::Degraded,
                )
            }
            // 升階：DEGRADED → CRITICAL (dwell 5min)
            (HealthDegraded, HealthCritical) => {
                self.recovery_band_seen_at = None;
                self.try_dwell_then_transition(
                    HealthCritical,
                    anomaly_id,
                    now,
                    Duration::from_secs(300),
                    BandKind::Critical,
                )
            }
            // recovery：WARN → OK (15min OK-band dwell)
            (HealthWarn, HealthOk) => self.try_recovery_dwell(
                HealthOk,
                now,
                Duration::from_secs(900),
            ),
            // recovery：DEGRADED → OK / DEGRADED → WARN (30min OK-or-WARN-band
            // dwell；降至 WARN 為中間步驟)。
            (HealthDegraded, HealthOk) | (HealthDegraded, HealthWarn) => {
                self.try_recovery_dwell(
                    HealthWarn,
                    now,
                    Duration::from_secs(1800),
                )
            }
            // CRITICAL → 任何更低 state：Sprint 2 不支援自動 recovery（Sprint 5
            // 才接 operator manual unlock + Console GUI）。
            (HealthCritical, HealthOk) | (HealthCritical, HealthWarn) | (HealthCritical, HealthDegraded) => {
                Ok(false)
            }
        }
    }
}

/// 內部 band 種類（dwell anchor 對應）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum BandKind {
    Warn,
    Degraded,
    Critical,
}

impl HealthStateMachine {
    /// 升階 with dwell：caller 採樣到 target band；累積 dwell 時間 ≥ 要求時 fire
    /// transition（透過 try_transition_with_cap 走 amp cap）。
    fn try_dwell_then_transition(
        &mut self,
        target_state: HealthState,
        anomaly_id: &str,
        now: Instant,
        dwell: Duration,
        band_kind: BandKind,
    ) -> Result<bool, M3Error> {
        // 對應 band anchor 寫入（首次採樣 anchor None → set now）。
        let anchor = match band_kind {
            BandKind::Warn => &mut self.warn_band_seen_at,
            BandKind::Degraded => &mut self.degraded_band_seen_at,
            BandKind::Critical => &mut self.critical_band_seen_at,
        };
        let seen_at = match anchor {
            Some(t) => *t,
            None => {
                *anchor = Some(now);
                return Ok(false);
            }
        };
        let elapsed = now.duration_since(seen_at);
        if elapsed >= dwell {
            // dwell pass → 走 amp cap 嘗試 fire。
            self.try_transition_with_cap(target_state, anomaly_id, now)
        } else {
            Ok(false)
        }
    }

    /// recovery with dwell：caller 採樣到 OK / WARN band；累積 dwell 後降階。
    ///
    /// recovery 不走 amp cap（per spec §6.1 amp cap 僅約束升階；recovery 降階
    /// 不應被 cap 阻塞，否則永困高 state）。
    fn try_recovery_dwell(
        &mut self,
        target_state: HealthState,
        now: Instant,
        dwell: Duration,
    ) -> Result<bool, M3Error> {
        let seen_at = match self.recovery_band_seen_at {
            Some(t) => t,
            None => {
                self.recovery_band_seen_at = Some(now);
                return Ok(false);
            }
        };
        let elapsed = now.duration_since(seen_at);
        if elapsed < dwell {
            return Ok(false);
        }
        // 同 state 不算 fire（caller 端寫 row 時應傳 state_prev=current 沒意義；
        // recovery 真實降階 prev != target）。
        if self.current_state == target_state {
            return Ok(false);
        }
        // 真實降階。
        // dwell_secs 在 state_entered_at 被覆寫前計算（per Sprint 2 round 2
        // MEDIUM-2 fix）：recovery 降階前 prev state（高 band）的駐留秒數。
        let dwell_secs = now
            .saturating_duration_since(self.state_entered_at)
            .as_secs();
        self.last_transition_dwell_secs = dwell_secs.min(i32::MAX as u64) as u32;
        self.previous_state = self.current_state;
        self.current_state = target_state;
        self.state_entered_at = now;
        self.warn_band_seen_at = None;
        self.degraded_band_seen_at = None;
        self.critical_band_seen_at = None;
        self.recovery_band_seen_at = None;
        Ok(true)
    }
}

/// Sprint 1B AC-7 cross-language 1e-4 fixture 用 — 計算 sample window 的 mean +
/// sample stddev (ddof=1)。
///
/// 為什麼:
///   AC-7 spec §AC-7 要求 `engine_cpu_pct` 5 sample window mean / sigma Rust ↔
///   Python replay 端在 1e-4 容差內對齊。Sprint 1A-ζ Phase 3b PoC
///   (`tests/test_spike_cross_lang_fixture.py`) 已用 3 條 Python 實作互驗
///   algorithm contract 數位 fingerprint;本 helper 是 Rust 端最小 binding,
///   讓 Python test subprocess 跑 cargo test 並 parse JSON 輸出對齊 Python
///   expected 值。
///
/// 為什麼用 two-pass 而非 Welford:
///   Sprint 1A-ζ Phase 3b E4 Python fixture 已證 naive two-pass / Welford /
///   numpy 三者 1e-4 內等價; spike PoC 階段選 two-pass (簡單、易讀、與 Python
///   naive_mean_sigma 1:1 對齊)。Sprint 5+ 真實 hot-path 接 health writer 時
///   可換 Welford incremental update。
///
/// 不變量:
///   - samples.len() < 2 → return None (ddof=1 要求 N-1 > 0)
///   - 任何 NaN/Inf 輸入 → 自然 propagate (caller 端 fail-closed)
///   - mean / variance 走 f64 sum,catastrophic cancellation 風險限於本
///     fixture 用例 (5 sample 數量級 10..100); production 不用此 helper。
///
/// 硬邊界:
///   - 只在 `--features spike` 或 `cfg(test)` 編譯; 0 production code path 污染
///   - 不接 IPC / DB / GovernanceHub; 純算術
#[cfg(any(test, feature = "spike"))]
pub fn compute_window_stats(samples: &[f64]) -> Option<(f64, f64)> {
    let n = samples.len();
    if n < 2 {
        return None;
    }
    let n_f = n as f64;
    let mean = samples.iter().sum::<f64>() / n_f;
    // sample variance: sum((x - mean)^2) / (N - 1) per ddof=1。
    let variance = samples.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / (n_f - 1.0);
    Some((mean, variance.sqrt()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_health_state_as_str_round_trip() {
        // 對齊 V106 CHECK 4 值的 round-trip 不變式。
        for s in &[HealthState::HealthOk, HealthState::HealthWarn,
                   HealthState::HealthDegraded, HealthState::HealthCritical] {
            let parsed = HealthState::from_str(s.as_str()).unwrap();
            assert_eq!(parsed, *s);
        }
    }

    #[test]
    fn test_health_state_unknown_literal() {
        assert!(matches!(
            HealthState::from_str("HEALTH_INVALID"),
            Err(M3Error::UnknownHealthState(_))
        ));
    }

    #[test]
    fn test_health_domain_as_str_round_trip() {
        for d in &[
            HealthDomain::EngineRuntime, HealthDomain::PipelineThroughput,
            HealthDomain::DatabasePool, HealthDomain::ApiLatency,
            HealthDomain::StrategyQuality, HealthDomain::RiskEnvelope,
        ] {
            let parsed = HealthDomain::from_str(d.as_str()).unwrap();
            assert_eq!(parsed, *d);
        }
    }

    #[test]
    fn test_health_domain_unknown_literal() {
        assert!(matches!(
            HealthDomain::from_str("invalid_domain"),
            Err(M3Error::UnknownHealthDomain(_))
        ));
    }

    #[test]
    fn test_health_domain_require_implemented_spike_scope() {
        // EngineRuntime 通過; 其餘 5 stub 必失敗 (dispatch packet §2.7(a) 強制)。
        assert!(HealthDomain::EngineRuntime.require_implemented().is_ok());
        for d in &[
            HealthDomain::PipelineThroughput, HealthDomain::DatabasePool,
            HealthDomain::ApiLatency, HealthDomain::StrategyQuality,
            HealthDomain::RiskEnvelope,
        ] {
            let err = d.require_implemented().unwrap_err();
            assert!(matches!(err, M3Error::DomainNotImplemented(_)));
        }
    }

    #[test]
    fn test_health_state_severity_ordering() {
        // ADR-0042 Decision 2 偏序: OK < WARN < DEGRADED < CRITICAL。
        assert!(HealthState::HealthOk.severity_value()
            < HealthState::HealthWarn.severity_value());
        assert!(HealthState::HealthWarn.severity_value()
            < HealthState::HealthDegraded.severity_value());
        assert!(HealthState::HealthDegraded.severity_value()
            < HealthState::HealthCritical.severity_value());
    }

    #[test]
    fn test_engine_runtime_metric_classify_band() {
        // OK band: heartbeat alive + RSS < 2GB + CPU < 50%。
        let ok = EngineRuntimeMetric { cpu_pct: 30.0, rss_mb: 1024.0, heartbeat_alive: true };
        assert_eq!(ok.classify_band(), HealthState::HealthOk);

        // WARN band: CPU 50-80%。
        let warn = EngineRuntimeMetric { cpu_pct: 60.0, rss_mb: 1024.0, heartbeat_alive: true };
        assert_eq!(warn.classify_band(), HealthState::HealthWarn);

        // WARN band: RSS 2-4GB。
        let warn_rss = EngineRuntimeMetric { cpu_pct: 30.0, rss_mb: 3072.0, heartbeat_alive: true };
        assert_eq!(warn_rss.classify_band(), HealthState::HealthWarn);

        // DEGRADED band: CPU > 80%。
        let degraded = EngineRuntimeMetric { cpu_pct: 85.0, rss_mb: 1024.0, heartbeat_alive: true };
        assert_eq!(degraded.classify_band(), HealthState::HealthDegraded);

        // CRITICAL: heartbeat dead。
        let crit = EngineRuntimeMetric { cpu_pct: 30.0, rss_mb: 1024.0, heartbeat_alive: false };
        assert_eq!(crit.classify_band(), HealthState::HealthCritical);
    }

    #[test]
    fn test_state_machine_starts_ok() {
        let sm = HealthStateMachine::new(HealthDomain::EngineRuntime);
        assert_eq!(sm.current_state(), HealthState::HealthOk);
        assert_eq!(sm.amplification_loop_24h_count(), 0);
    }

    #[test]
    fn test_state_machine_stub_domain_rejects() {
        // 5 stub domain 走入 observe 必 fail-loud。
        let mut sm = HealthStateMachine::new(HealthDomain::ApiLatency);
        let metric = EngineRuntimeMetric { cpu_pct: 30.0, rss_mb: 1024.0, heartbeat_alive: true };
        let err = sm.observe(metric, "test").unwrap_err();
        assert!(matches!(err, M3Error::DomainNotImplemented(_)));
    }

    #[test]
    fn test_try_transition_no_fire_when_current_eq_target() {
        // 嚴格語意驗: current == target 不算 transition fire,不 insert entry,
        // 不增 count (per V106 spec §1.1 line 77 「state_prev → state」需 ≠)。
        let mut sm = HealthStateMachine::new(HealthDomain::EngineRuntime);
        let now = Instant::now();
        // SM 初始 current=HealthOk; 嘗試 transition 到 HealthOk → no fire。
        let result = sm.try_transition_with_cap(HealthState::HealthOk, "noop_id", now);
        assert!(matches!(result, Ok(false)));
        assert_eq!(sm.amplification_loop_24h_count(), 0);
        assert_eq!(sm.amp_cap_entry_count(), 0);
    }

    #[test]
    fn test_try_transition_fail_closed_reject_count_ge_2() {
        // V106 spec §1.1 line 77 嚴格 fail-closed ≥ 2 reject 路徑直接覆蓋:
        //   - 同 domain 24h 內 fire 數 ≥ 2 後, 新 fire request 走 fail-closed: 不
        //     insert entry, 不 fire, 不 increment count, 返回 false。
        //   - 為什麼直接呼 try_transition_with_cap 而非走 observe_at: spike scope
        //     observe_at 內 (HealthWarn, _) 已短路返 Ok(false) 不再進 transition
        //     fn (WARN → DEGRADED 5min dwell 在 Sprint 5 cascade IMPL 才接);
        //     要 cover ≥ 2 fail-closed reject branch 在 spike scope 階段, 直接
        //     單元測 transition fn 是唯一路徑。Sprint 5 cascade IMPL delivered
        //     後, 此 test 仍守住 transition fn 端嚴格邊界。
        let mut sm = HealthStateMachine::new(HealthDomain::EngineRuntime);
        let now = Instant::now();

        // 第 1 fire: HealthOk → HealthWarn, anomaly_id "spike_a"。
        let r1 = sm.try_transition_with_cap(HealthState::HealthWarn, "spike_a", now);
        assert!(matches!(r1, Ok(true)), "first fire OK→WARN should succeed");
        assert_eq!(sm.amplification_loop_24h_count(), 1);

        // 第 2 fire: 此時 current=WARN, target 必須 != WARN 才能再 fire 計入 count;
        // 也需要新 anomaly_id "spike_b" 避開 guard 1 cap suppress。
        // 嚴格語意: 直接走 transition fn (繞過 observe_at WARN 短路)。
        let r2 = sm.try_transition_with_cap(HealthState::HealthDegraded, "spike_b", now);
        assert!(matches!(r2, Ok(true)), "second fire WARN→DEGRADED should succeed");
        assert_eq!(sm.amplification_loop_24h_count(), 2, "count should hit 2");

        // 第 3 fire 嘗試: count == 2 → 走 fail-closed reject (guard 3); 不同
        // anomaly_id "spike_c" + target != current 確保不被 guard 1/2 短路, 唯一
        // 觸發路徑就是 guard 3。
        let r3 = sm.try_transition_with_cap(HealthState::HealthCritical, "spike_c", now);
        assert!(matches!(r3, Ok(false)), "third fire should be rejected (count >= 2)");

        // 校驗 reject 不 insert / 不增 count / 不改 state。
        assert_eq!(sm.amplification_loop_24h_count(), 2, "count must stay at 2 after reject");
        assert_eq!(sm.amp_cap_entry_count(), 2, "no new entry should be inserted on reject");
        assert_eq!(sm.current_state(), HealthState::HealthDegraded,
            "state must remain at last successful target (DEGRADED), not advance to CRITICAL");
    }

    #[test]
    fn test_try_transition_cap_suppress_same_anomaly_id_repeat() {
        // V106 spec ADR-0042 Decision 4 「1-anomaly = 1-state-change/24h」嚴格
        // 覆蓋: 同 anomaly_id 在 24h cap window 內第 2 次 fire request 走 guard 1
        // suppress, 不 insert 新 entry, 不增 count, 不改 state。
        //
        // 為什麼 spike scope 必須直接單測 guard 1:
        //   - observe_at 路徑下「同 id 反覆採樣」對 OK 起點走「初次採樣記時間
        //     → 60s dwell → fire transition」, 不會在 OK 階段重複 hit guard 1;
        //     一旦 fire 進 WARN 後, observe_at 走 (HealthWarn, _) 短路返 false
        //     (不進 transition fn), guard 1 在 spike scope 階段無路可達。
        //   - 直接單測 transition fn 是 spike scope 階段覆蓋 guard 1 的唯一辦
        //     法; Sprint 5 cascade IMPL 補 WARN→DEGRADED dwell 路徑後, observe_at
        //     可再驗 guard 1 整合路徑。
        let mut sm = HealthStateMachine::new(HealthDomain::EngineRuntime);
        let now = Instant::now();

        // 第 1 fire: OK → WARN 用 anomaly_id "engine_cpu_spike"。
        let r1 = sm.try_transition_with_cap(HealthState::HealthWarn, "engine_cpu_spike", now);
        assert!(matches!(r1, Ok(true)), "first fire should succeed");
        assert_eq!(sm.amplification_loop_24h_count(), 1);
        assert_eq!(sm.amp_cap_entry_count(), 1);

        // 第 2 fire 嘗試: 同 anomaly_id "engine_cpu_spike" + target != current,
        // 期望 hit guard 1 cap_entries.contains_key → reject 返 false。
        let r2 = sm.try_transition_with_cap(HealthState::HealthDegraded, "engine_cpu_spike", now);
        assert!(matches!(r2, Ok(false)), "repeat same anomaly_id should be suppressed");

        // 校驗 suppress 不增 entry / 不增 count / 不改 state。
        assert_eq!(sm.amplification_loop_24h_count(), 1,
            "count must stay at 1 (no new fire on same anomaly_id)");
        assert_eq!(sm.amp_cap_entry_count(), 1,
            "no new entry on guard 1 suppress");
        assert_eq!(sm.current_state(), HealthState::HealthWarn,
            "state must remain at first successful target (WARN)");
    }

    #[test]
    fn test_compute_window_stats_spec_sample() {
        // Sprint 1B AC-7 fixture sample (對齊 Phase 3b Python PoC line 40):
        //   [10.0, 20.0, 30.0, 25.0, 15.0]
        //   mean = 20.0
        //   sample_var = ((10-20)^2 + (20-20)^2 + (30-20)^2 + (25-20)^2 + (15-20)^2) / 4
        //              = (100 + 0 + 100 + 25 + 25) / 4 = 250/4 = 62.5
        //   sample_sigma = sqrt(62.5) ≈ 7.905694150420948
        let samples = [10.0_f64, 20.0, 30.0, 25.0, 15.0];
        let (mean, sigma) = compute_window_stats(&samples).expect("len 5 must return Some");
        assert!((mean - 20.0).abs() < 1e-10, "mean drift: {}", mean);
        assert!(
            (sigma - 7.905694150420948).abs() < 1e-10,
            "sigma drift: {}",
            sigma
        );
    }

    #[test]
    fn test_compute_window_stats_constant_edge_case() {
        // 所有 sample 相同 → variance 0 → sigma 0.
        let samples = [50.0_f64; 5];
        let (mean, sigma) = compute_window_stats(&samples).expect("len 5 must return Some");
        assert!((mean - 50.0).abs() < 1e-10);
        assert!(sigma.abs() < 1e-10);
    }

    #[test]
    fn test_compute_window_stats_insufficient_samples() {
        // ddof=1 要求 N >= 2,否則 None (fail-closed)。
        assert!(compute_window_stats(&[]).is_none());
        assert!(compute_window_stats(&[42.0_f64]).is_none());
        // N=2 是最小可算; variance = (x1-x2)^2 / 2 / 1 path 仍 ok。
        let (mean, sigma) =
            compute_window_stats(&[10.0_f64, 20.0]).expect("len 2 must return Some");
        // mean=15, sample_var=((10-15)^2+(20-15)^2)/1=50, sigma=sqrt(50)≈7.0710678
        assert!((mean - 15.0).abs() < 1e-10);
        assert!((sigma - 50.0_f64.sqrt()).abs() < 1e-10);
    }
}
