//! M3 Health Monitoring — 4-state ladder + 6 health domain + amplification cap。
//! M3 健康監測模塊 — 4 級狀態階梯 + 6 健康 domain + 24h 放大循環封頂。
//!
//! MODULE_NOTE
//! 模塊用途：
//!   提供 M3 集中健康觀測層的 Rust 骨架，spike scope 只 IMPL `engine_runtime`
//!   1 個 domain；其餘 5 domain (pipeline_throughput / database_pool /
//!   api_latency / strategy_quality / risk_envelope) 走 `unimplemented!()`
//!   stub。state machine 對齊 M3 design spec §3.3 dwell time + flap
//!   suppression 規範；amplification cap 對齊 ADR-0042 Decision 4 +
//!   ADR-0036 1-anomaly = 1-state-change/24h 規範。
//!
//! 主要類 / 函數：
//!   - `HealthState` enum (HEALTH_OK / WARN / DEGRADED / CRITICAL)
//!   - `HealthDomain` enum (engine_runtime + 5 stub)
//!   - `M3Error` 統一錯誤類型
//!   - `HealthStateMachine` 4-state ladder + dwell time + amp cap
//!   - `EngineRuntimeMetric` 採樣輸入 struct
//!
//! 依賴：
//!   - 純 std + tokio::time (mock time hook gated by `spike` feature)。
//!   - 不依賴 trading hot path / GovernanceHub / risk_config；spike 期不接 IPC。
//!
//! 硬邊界：
//!   - 4-state ladder 對齊 V106 schema (state TEXT CHECK 4 值)。
//!   - amplification_loop_24h_count 計數對齊 V106 schema column。
//!   - Cascade gate cap (8 action / 1 cascade per ADR-0042 Decision 5) 不在
//!     spike scope；屬 Sprint 5 Tier 1 IMPL 範圍。
//!   - HEALTH_CATASTROPHIC 由 5-gate kill 觸發；M3 4-state ladder 只到
//!     CRITICAL (per ADR-0042 Decision 6 + Decision 2)。

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

    /// spike scope 只 IMPL engine_runtime; 其餘 5 domain 走此錯誤。
    #[error("domain not implemented in spike scope: {0}")]
    DomainNotImplemented(String),
}

/// 4 級健康狀態階梯 (per ADR-0042 Decision 2 + V106 schema state CHECK)。
///
/// 為什麼:
///   ADR-0042 Decision 2 規定 4 級階梯 OK < WARN < DEGRADED < CRITICAL;
///   HEALTH_CATASTROPHIC 由 5-gate kill 觸發,不在本 enum 範圍 (Decision 6)。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
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
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
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
///   - 單 domain 一個 state machine 實例 (system-level state = max severity
///     of all per-domain state, 對齊 M3 spec §3.4)。
///   - dwell time 60s OK→WARN / 5min WARN→DEGRADED (per spec §3.3 升階 dwell);
///     spike scope 只測 OK→WARN dwell 60s + WARN 維持 + amp cap fire 路徑;
///     WARN→DEGRADED 5min dwell + cascade 邏輯 Sprint 5 Tier 1 補。
///   - amp cap: 同一 anomaly_id 24h 內最多 1 次 state transition;
///     amplification_loop_24h_count 對齊 V106 schema column。
///   - flap suppression: 24h 內 WARN ↔ OK > 3 次 → lock WARN 直到 1h 全 OK
///     (per spec §3.3); spike scope 不測此 path (out-of-scope per dispatch
///     packet §2.7(c) "cascade gate cap 加進來" 反模式邊界)。
pub struct HealthStateMachine {
    domain: HealthDomain,
    /// 當前 active state。
    current_state: HealthState,
    /// 進入當前 state 的時間 (用於 dwell time 計算)。
    state_entered_at: Instant,
    /// 最近一次採樣到 WARN-band 的時間 (用於 OK→WARN 60s dwell 判斷)。
    warn_band_seen_at: Option<Instant>,
    /// amplification cap: anomaly_id → 第一次觸發時間。
    /// 24h 過期 → reset; 同 id 24h 內第 2+ 次不觸發 transition。
    amp_cap_entries: HashMap<String, AmpCapEntry>,
    /// 24h window 計數 (對齊 V106 schema amplification_loop_24h_count column);
    /// writer 端讀此值寫入新 row。
    amplification_loop_24h_count: u32,
}

impl HealthStateMachine {
    /// 建立新的 state machine 實例。spike scope 只 IMPL EngineRuntime;
    /// 其餘 5 domain 由 caller 在 evaluate 時撞 M3Error::DomainNotImplemented。
    pub fn new(domain: HealthDomain) -> Self {
        Self {
            domain,
            current_state: HealthState::HealthOk,
            state_entered_at: Instant::now(),
            warn_band_seen_at: None,
            amp_cap_entries: HashMap::new(),
            amplification_loop_24h_count: 0,
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

        // amplification_loop_24h_count 對齊 V106 schema; 重新計算當前 24h 內
        // 已觸發 transition 的 unique anomaly_id 數 (per ADR-0042 Decision 4)。
        self.amplification_loop_24h_count = self.amp_cap_entries.len() as u32;

        // dwell-time 邏輯 (spike scope: 只 IMPL OK → WARN 60s dwell;
        // WARN → DEGRADED 5min dwell + cascade 不在 spike scope)。
        match (self.current_state, band) {
            // OK → WARN-band 採樣到, 開始 dwell 計時。
            (HealthState::HealthOk, HealthState::HealthWarn)
            | (HealthState::HealthOk, HealthState::HealthDegraded)
            | (HealthState::HealthOk, HealthState::HealthCritical) => {
                // 第一次採樣到 WARN-band → 記時間, 不立即 transition。
                if self.warn_band_seen_at.is_none() {
                    self.warn_band_seen_at = Some(now);
                    return Ok(false);
                }
                // dwell time 60s 持續 WARN-band → 觸發 transition (受 amp cap 約束)。
                let dwell = now.duration_since(self.warn_band_seen_at.unwrap());
                if dwell >= Duration::from_secs(60) {
                    self.try_transition_with_cap(HealthState::HealthWarn, anomaly_id, now)
                } else {
                    Ok(false)
                }
            }
            // OK → 採樣回 OK-band, 清除 warn_band_seen_at。
            (HealthState::HealthOk, HealthState::HealthOk) => {
                self.warn_band_seen_at = None;
                Ok(false)
            }
            // WARN 維持 (per spike scope, WARN → DEGRADED dwell time 5min 對齊
            // M3 spec §3.3 但 spike 只測 cap suppress 不升 DEGRADED)。
            (HealthState::HealthWarn, _) => {
                // amp cap 約束下,同 anomaly_id 24h 內不重觸發; 不 transition。
                // (test_m3_amp_cap_24h_fire 反向 verify: 第二個 spike 在 24h cap
                //  窗口內 → 不升 DEGRADED 維持 WARN; 24h 後 cap reset → 第 2 次
                //  spike 算「第一次」可再次計入 cap entry。)
                self.try_transition_with_cap(HealthState::HealthWarn, anomaly_id, now)?;
                Ok(false)
            }
            // 其他 transition (DEGRADED/CRITICAL recovery / etc.) 不在 spike scope。
            _ => Ok(false),
        }
    }

    /// 受 amp cap 約束的 state transition 嘗試 (per ADR-0042 Decision 4)。
    ///
    /// 為什麼:
    ///   - 同 anomaly_id 24h 內最多觸發 1 次 state transition; cap entry 已存在
    ///     → 即使 dwell time pass 也不 transition (返回 false)。
    ///   - cap entry 新建時計入 amplification_loop_24h_count, 對齊 V106 row 寫入。
    ///   - 注意: state ≠ current → 真實 transition; 同 state 重觸 → no-op 返回 false。
    fn try_transition_with_cap(
        &mut self,
        target_state: HealthState,
        anomaly_id: &str,
        now: Instant,
    ) -> Result<bool, M3Error> {
        // 同 anomaly_id 已在 24h cap window 內觸發過 → suppress, 不 transition。
        if self.amp_cap_entries.contains_key(anomaly_id) {
            return Ok(false);
        }

        // 新 anomaly_id → 計入 cap entry。
        self.amp_cap_entries.insert(
            anomaly_id.to_string(),
            AmpCapEntry {
                first_triggered_at: now,
            },
        );
        self.amplification_loop_24h_count = self.amp_cap_entries.len() as u32;

        // 真實 transition (state 變更)。
        if self.current_state != target_state {
            self.current_state = target_state;
            self.state_entered_at = now;
            self.warn_band_seen_at = None;
            return Ok(true);
        }
        Ok(false)
    }

    /// 當前 state 查詢 (test + writer 用)。
    pub fn current_state(&self) -> HealthState {
        self.current_state
    }

    /// 當前 amplification cap 計數 (對齊 V106 row column)。
    pub fn amplification_loop_24h_count(&self) -> u32 {
        self.amplification_loop_24h_count
    }

    /// 當前 cap entry 數 (test 用)。
    #[cfg(any(test, feature = "spike"))]
    pub fn amp_cap_entry_count(&self) -> usize {
        self.amp_cap_entries.len()
    }
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
}
