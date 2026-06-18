//! H0 Gate — Local Deterministic Judgment Core (<1ms SLA, no I/O on hot path)
//! H0 門控 — 本地確定性判斷核心（<1ms SLA，熱路徑無 I/O）
//!
//! MODULE_NOTE (中文):
//!   本模組實現 H0 本地確定性門控，是 AI 治理層（H1-H5）的前置硬性過濾器。
//!   移植自 Python `h0_gate.py`（832 行），精簡為 ~600 行 Rust 生產代碼。
//!
//!   核心結構：
//!   - `H0Gate`：主門控結構，持有配置、健康/風控快照、價格時間戳等狀態
//!   - `GateStats`：累計統計（通過/阻擋計數、延遲追蹤）
//!   - `ShadowEntry`：影子模式日誌條目
//!
//!   5 項確定性子檢查（fail-fast 順序）：
//!     1. freshness   — Tick 數據新鮮度
//!     2. health      — 系統資源健康（CPU/記憶體/DB延遲/網絡丟包）
//!     3. eligibility — 符號與類別准入 + 系統模式門控
//!     4. risk_envelope — 風控邊界（持倉數/曝險比例/kill switch）
//!     5. cooldown    — 冷卻期
//!
//!   影子模式：執行全部檢查但不阻擋，記錄「本來會阻擋」的決策供觀察分析。
//!
//! MODULE_NOTE (English):
//!   Implements H0 local deterministic gate — the mandatory hard filter before
//!   AI governance layers (H1-H5). Ported from Python `h0_gate.py` (832 lines),
//!   condensed to ~600 lines of Rust production code.
//!
//!   Core structures:
//!   - `H0Gate`: main gate struct holding config, health/risk snapshots, price timestamps
//!   - `GateStats`: accumulated statistics (pass/block counts, latency tracking)
//!   - `ShadowEntry`: shadow mode log entry
//!
//!   5 deterministic sub-checks (fail-fast order):
//!     1. freshness   — tick data freshness
//!     2. health      — system resource health (CPU/memory/DB latency/network loss)
//!     3. eligibility — symbol/category allowlist + system mode gate
//!     4. risk_envelope — risk envelope (position count/exposure %/kill switch)
//!     5. cooldown    — cooldown period
//!
//!   Shadow mode: runs all checks but never blocks; logs would-have-blocked
//!   decisions for observational analysis.
//!
//! Governance reference:
//!   DOC-02 §3: H0 Gate deterministic gating, <1ms SLA requirement
//!   §5.4 (Principle 4): strategy cannot bypass risk control
//!   §5.5 (Principle 5): survival before profit
//!   §5.6 (Principle 6): fail to safe / conserve on uncertainty

use std::collections::{HashMap, VecDeque};
use std::sync::Arc;
use std::time::Instant;

use openclaw_types::{H0CheckResult, H0GateConfig, H0GateHealthSnapshot, H0GateRiskSnapshot};

use crate::hot_path_metrics::H0LatencyRecorder;

// ─────────────────────────────────────────────────────────────────────────────
// Gate statistics / 門控統計
// ─────────────────────────────────────────────────────────────────────────────

/// Accumulated gate statistics for observability.
/// 累計門控統計數據，供可觀測性使用。
#[derive(Debug, Clone, Default, serde::Serialize, serde::Deserialize)]
pub struct GateStats {
    pub total_checks: u64,
    pub total_allowed: u64,
    pub blocked_freshness: u64,
    pub blocked_health: u64,
    pub blocked_eligibility: u64,
    pub blocked_envelope: u64,
    pub blocked_cooldown: u64,
    pub shadow_would_block: u64,
    pub max_latency_us: u64,
    pub total_latency_us: u64,
}

impl GateStats {
    /// Compute allow rate as a percentage (0-100).
    /// 計算通過率百分比（0-100）。
    pub fn allow_rate_pct(&self) -> f64 {
        if self.total_checks == 0 {
            return 0.0;
        }
        (self.total_allowed as f64 / self.total_checks as f64) * 100.0
    }

    /// Average latency in microseconds.
    /// 平均延遲（微秒）。
    pub fn avg_latency_us(&self) -> f64 {
        if self.total_checks == 0 {
            return 0.0;
        }
        self.total_latency_us as f64 / self.total_checks as f64
    }

    /// Total blocked count across all categories.
    /// 所有類別的阻擋總數。
    pub fn total_blocked(&self) -> u64 {
        self.blocked_freshness
            + self.blocked_health
            + self.blocked_eligibility
            + self.blocked_envelope
            + self.blocked_cooldown
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Shadow log entry / 影子日誌條目
// ─────────────────────────────────────────────────────────────────────────────

/// Shadow mode log entry recording a would-have-blocked event.
/// 影子模式日誌條目，記錄「本來會阻擋」事件。
#[derive(Debug, Clone)]
#[allow(dead_code)] // Fields read via shadow_log access / debug; not consumed yet in public API
struct ShadowEntry {
    pub symbol: String,
    pub ts_ms: u64,
    pub would_block_reasons: Vec<String>,
}

/// Maximum number of shadow log entries retained.
/// 影子日誌最大保留條目數。
const SHADOW_LOG_MAX: usize = 100;

// ─────────────────────────────────────────────────────────────────────────────
// H0Gate — main struct / 主結構
// ─────────────────────────────────────────────────────────────────────────────

/// H0 Local Deterministic Judgment Core.
/// H0 本地確定性判斷核心。
///
/// Hot path `check()` must complete in <1ms. All state is pre-loaded into
/// memory and updated by external callers (non-hot-path).
///
/// 熱路徑 `check()` 必須在 <1ms 內完成。所有狀態預載入記憶體，
/// 由外部調用者（非熱路徑）更新。
pub struct H0Gate {
    /// Configuration / 配置
    config: H0GateConfig,
    /// System health snapshot / 系統健康快照
    health: H0GateHealthSnapshot,
    /// Risk state snapshot / 風控狀態快照
    risk: H0GateRiskSnapshot,
    /// Price tick timestamps: symbol -> last tick ts_ms / 價格 tick 時間戳
    price_ts: HashMap<String, u64>,
    /// Per-symbol eligibility override / 符號准入覆蓋
    symbol_eligibility: HashMap<String, bool>,
    /// System operating mode: "read_only" | "active" | "disabled"
    /// 系統操作模式
    system_mode: String,
    /// Accumulated statistics / 累計統計
    stats: GateStats,
    /// Shadow mode log (circular buffer) / 影子模式日誌（環形緩衝區）
    shadow_log: VecDeque<ShadowEntry>,
    /// P2-LG1-DEMO-SLO-CARVEOUT (2026-05-21)：HdrHistogram-based latency recorder。
    ///
    /// 為什麼 Option<Arc<...>>：
    ///   - None = backward compat（H0Gate::new 與既有測試/cold path 不接 recorder）。
    ///   - Some = pipeline_ctor 在 set_endpoint_env 之後注入 per-pipeline 獨立
    ///     recorder（不共用 Arc，避免 3 tokio rt 同時 record 的鎖爭用）。
    ///
    /// 為什麼 engine_mode 與 recorder 同時 inject：record() 需 `&'static str` tag
    /// 對應 5 種 effective_engine_mode 值之一；任何拼錯 silently skip（recorder 防禦）。
    metrics_recorder: Option<Arc<H0LatencyRecorder>>,
    /// P2-LG1-DEMO-SLO-CARVEOUT (2026-05-21)：metric 標籤對應的 effective_engine_mode。
    ///
    /// 預設 "paper" 對齊 H0Gate::new + with_balance 預設 PipelineKind::Paper；
    /// pipeline_ctor.set_endpoint_env 後同步更新（demo / live / live_demo / live_testnet）。
    /// `&'static str` 不可改 `String`：hot path 不可 alloc。
    engine_mode: &'static str,
}

impl H0Gate {
    /// Create a new H0Gate with optional config (uses defaults if None).
    /// 建立新的 H0Gate，若無配置則使用預設值。
    ///
    /// `metrics_recorder` 預設 None；`engine_mode` 預設 "paper"。
    /// pipeline_ctor 在 set_endpoint_env / set_h0_latency_recorder 後注入。
    pub fn new(config: Option<H0GateConfig>) -> Self {
        Self {
            config: config.unwrap_or_default(),
            health: H0GateHealthSnapshot::default(),
            risk: H0GateRiskSnapshot::default(),
            price_ts: HashMap::new(),
            symbol_eligibility: HashMap::new(),
            system_mode: "read_only".to_string(),
            stats: GateStats::default(),
            shadow_log: VecDeque::with_capacity(SHADOW_LOG_MAX),
            metrics_recorder: None,
            engine_mode: "paper",
        }
    }

    /// P2-LG1-DEMO-SLO-CARVEOUT (2026-05-21)：builder pattern 注入 latency recorder。
    ///
    /// 為什麼存在：spec §4.2 要求新增 `with_metrics` constructor 而保留 H0Gate::new
    /// backward compat（其他 caller / test 預期 None recorder fallback）。
    ///
    /// `engine_mode` 必須是 effective_engine_mode 5 種回傳值之一
    /// （"paper" / "demo" / "live" / "live_demo" / "live_testnet"）；
    /// 任何不在 ENGINE_MODES 的字串會被 recorder.record 在 hot path silently skip。
    pub fn with_metrics(
        config: Option<H0GateConfig>,
        recorder: Arc<H0LatencyRecorder>,
        engine_mode: &'static str,
    ) -> Self {
        let mut gate = Self::new(config);
        gate.metrics_recorder = Some(recorder);
        gate.engine_mode = engine_mode;
        gate
    }

    /// P2-LG1-DEMO-SLO-CARVEOUT (2026-05-21)：post-construction 注入 recorder。
    ///
    /// 為什麼存在：TickPipeline::with_balance/new/with_kind 已 land 而 EventConsumerDeps
    /// bootstrap 是 ctor 完成後才知曉 endpoint_env / effective_engine_mode。改 with_metrics
    /// 進入 ctor 需動 with_balance/with_kind 簽名，連帶 30+ 構造站；用 setter 路徑
    /// 注入是最小 footprint 接線。
    pub fn set_metrics_recorder(&mut self, recorder: Arc<H0LatencyRecorder>) {
        self.metrics_recorder = Some(recorder);
    }

    /// P2-LG1-DEMO-SLO-CARVEOUT (2026-05-21)：更新 engine_mode 標籤。
    ///
    /// pipeline_ctor.set_endpoint_env 解析 effective_engine_mode 後呼叫；
    /// 必為 ENGINE_MODES 5 個合法值之一（caller 自證）。
    pub fn set_engine_mode(&mut self, engine_mode: &'static str) {
        self.engine_mode = engine_mode;
    }

    // ── State update methods (non-hot-path) / 狀態更新方法（非熱路徑）────────

    /// Inject updated system health snapshot.
    /// 注入更新的系統健康快照。
    pub fn update_health(&mut self, snapshot: H0GateHealthSnapshot) {
        self.health = snapshot;
    }

    /// Inject updated risk state snapshot.
    /// 注入更新的風控狀態快照。
    pub fn update_risk(&mut self, snapshot: H0GateRiskSnapshot) {
        self.risk = snapshot;
    }

    /// Update the last known tick timestamp for a symbol.
    /// 更新某符號的最後 tick 時間戳。
    pub fn update_price_ts(&mut self, symbol: &str, ts_ms: u64) {
        self.price_ts
            .entry(symbol.to_string())
            .and_modify(|v| *v = ts_ms)
            .or_insert(ts_ms);
    }

    /// Set system operating mode.
    /// 設置系統操作模式。
    ///
    /// Valid values: `"read_only"`, `"active"`, `"disabled"`.
    pub fn set_system_mode(&mut self, mode: &str) {
        self.system_mode = mode.to_string();
    }

    /// Override eligibility for a specific symbol.
    /// 覆蓋特定符號的准入狀態。
    pub fn set_symbol_eligibility(&mut self, symbol: &str, eligible: bool) {
        self.symbol_eligibility.insert(symbol.to_string(), eligible);
    }

    /// ARCH-RC1 1C-2-F (E-Merge-2): Replace the full H0GateConfig at runtime.
    /// Used by TickPipeline::apply_risk_snapshot to hot-reload the risk-level
    /// fields (max_open_positions / max_total_exposure_pct / allowed_categories)
    /// from RiskConfig.limits while the caller preserves health fields +
    /// shadow_mode via read-modify-write.
    /// ARCH-RC1 1C-2-F (E-Merge-2)：運行時整體替換 H0GateConfig。
    /// 供 TickPipeline::apply_risk_snapshot 熱重載風控層欄位，呼叫端透過
    /// read-modify-write 保留健康欄位與 shadow_mode。
    pub fn update_config(&mut self, config: H0GateConfig) {
        self.config = config;
    }

    /// Toggle shadow observation mode at runtime.
    /// 運行時切換影子觀察模式。
    /// SEC-02: emit an audit log on transition so remote toggles are traceable.
    /// SEC-02：切換時寫入審計日誌，使遠程切換可追溯。
    pub fn set_shadow_mode(&mut self, enabled: bool) {
        let prev = self.config.shadow_mode;
        self.config.shadow_mode = enabled;
        if prev != enabled {
            tracing::warn!(
                target: "security_audit",
                event = "h0_gate.shadow_mode_toggle",
                previous = prev,
                new = enabled,
                "SEC-02: H0Gate shadow_mode toggled / H0Gate 影子模式切換"
            );
        }
    }

    /// Read-only access to accumulated statistics.
    /// 累計統計只讀訪問。
    pub fn get_stats(&self) -> &GateStats {
        &self.stats
    }

    /// Read-only access to configuration.
    /// 配置只讀訪問。
    pub fn config(&self) -> &H0GateConfig {
        &self.config
    }

    /// Read-only cloned risk snapshot.
    /// 取得風控快照拷貝（只讀）。
    pub fn risk_snapshot(&self) -> H0GateRiskSnapshot {
        self.risk.clone()
    }

    /// Current shadow log length.
    /// 當前影子日誌長度。
    pub fn shadow_log_len(&self) -> usize {
        self.shadow_log.len()
    }

    // ── Hot path entry point / 熱路徑入口 ────────────────────────────────────

    /// Main hot-path gate check. Must complete in <1ms (no I/O, pure arithmetic).
    /// 主熱路徑門控檢查，必須在 <1ms 內完成（無 I/O，純算術）。
    ///
    /// Executes 5 sub-checks in order. Returns immediately on first failure
    /// (fail-fast). Tracks latency for SLA monitoring.
    ///
    /// 依序執行 5 個子檢查，第一個失敗即立即返回。記錄延遲供 SLA 監控。
    pub fn check(&mut self, symbol: &str, category: &str, now_ms: u64) -> H0CheckResult {
        let start = Instant::now();
        self.stats.total_checks += 1;

        // Shadow mode: run ALL checks, collect blocks, but return allowed=True.
        // 影子模式：執行全部檢查，收集阻擋，但返回 allowed=True。
        if self.config.shadow_mode {
            return self.check_shadow(symbol, category, now_ms, start);
        }

        // ── 1. Freshness check / 數據新鮮度檢查 ─────────────────────────────
        if let Some(reason) = self.check_freshness(symbol, now_ms) {
            self.stats.blocked_freshness += 1;
            return self.finalize_blocked(reason, "freshness", start);
        }

        // ── 2. Health check / 系統健康檢查 ───────────────────────────────────
        if let Some(reason) = self.check_health(now_ms) {
            self.stats.blocked_health += 1;
            return self.finalize_blocked(reason, "health", start);
        }

        // ── 3. Eligibility check / 准入檢查 ─────────────────────────────────
        if let Some(reason) = self.check_eligibility(symbol, category) {
            self.stats.blocked_eligibility += 1;
            return self.finalize_blocked(reason, "eligibility", start);
        }

        // ── 4. Risk envelope check / 風控邊界檢查 ───────────────────────────
        if let Some(reason) = self.check_risk_envelope() {
            self.stats.blocked_envelope += 1;
            return self.finalize_blocked(reason, "risk", start);
        }

        // ── 5. Cooldown check / 冷卻期檢查 ──────────────────────────────────
        if let Some(reason) = self.check_cooldown(now_ms) {
            self.stats.blocked_cooldown += 1;
            return self.finalize_blocked(reason, "cooldown", start);
        }

        // All checks passed / 全部通過
        self.stats.total_allowed += 1;
        self.finalize_allowed(String::new(), "all_passed", start)
    }

    // ── Sub-checks / 子檢查 ────────────────────────────────────────────────
    // Each returns None on pass, Some(reason) on block.
    // 通過返回 None，阻擋返回 Some(原因)。

    /// Check tick data freshness for symbol.
    /// 檢查符號的 tick 數據新鮮度。
    ///
    /// Blocks if: symbol has no data, or data is stale beyond `max_data_age_ms`.
    /// 阻擋條件：符號無數據，或數據超過 `max_data_age_ms` 過期。
    fn check_freshness(&self, symbol: &str, now_ms: u64) -> Option<String> {
        match self.price_ts.get(symbol) {
            None => Some(format!("no_data_{symbol}")),
            Some(last_ts) => {
                let age_ms = now_ms.saturating_sub(*last_ts);
                if age_ms >= self.config.max_data_age_ms {
                    Some(format!("data_stale_{symbol}_{age_ms}ms"))
                } else {
                    None
                }
            }
        }
    }

    /// Check system resource health against configured thresholds.
    /// 檢查系統資源健康是否在配置閾值內。
    fn check_health(&self, now_ms: u64) -> Option<String> {
        let snap = &self.health;

        // Snapshot staleness / 快照是否過期
        // snapshot_ts_ms == 0 means "never updated" — skip staleness check.
        // snapshot_ts_ms == 0 表示「從未更新」— 跳過過期檢查。
        if snap.snapshot_ts_ms > 0 {
            let snap_age_ms = now_ms.saturating_sub(snap.snapshot_ts_ms);
            if snap_age_ms > self.config.health_snapshot_max_age_ms {
                return Some(format!("health_snapshot_stale_{snap_age_ms}ms"));
            }
        }

        // CPU / CPU 使用率
        if snap.cpu_pct > self.config.max_cpu_pct {
            return Some(format!("cpu_too_high_{:.1}pct", snap.cpu_pct));
        }

        // Memory / 可用記憶體
        if snap.memory_available_mb < self.config.min_memory_mb {
            return Some(format!("memory_low_{}mb", snap.memory_available_mb));
        }

        // DB latency / DB 延遲
        if snap.db_latency_ms > self.config.max_db_latency_ms {
            return Some(format!("db_latency_high_{:.1}ms", snap.db_latency_ms));
        }

        // Network loss / 網絡丟包
        if snap.network_loss_pct > self.config.max_network_loss_pct {
            return Some(format!("network_loss_high_{:.1}pct", snap.network_loss_pct));
        }

        None
    }

    /// Check symbol/category eligibility and system mode.
    /// 檢查符號/類別准入及系統模式。
    ///
    /// Blocks if: category not in whitelist, symbol explicitly blocked, or system disabled.
    /// 阻擋條件：類別不在白名單、符號被明確阻擋、系統已禁用。
    fn check_eligibility(&self, symbol: &str, category: &str) -> Option<String> {
        // Category whitelist / 類別白名單
        if !self.config.allowed_categories.iter().any(|c| c == category) {
            return Some(format!("category_not_allowed_{category}"));
        }

        // Per-symbol eligibility override / 符號准入覆蓋
        // False -> explicitly blocked; True or absent -> allowed
        if let Some(false) = self.symbol_eligibility.get(symbol) {
            return Some(format!("symbol_not_eligible_{symbol}"));
        }

        // System mode gate / 系統模式門控
        // "disabled" blocks all; "read_only" and "active" pass.
        if self.system_mode == "disabled" {
            return Some("system_disabled".to_string());
        }

        None
    }

    /// Check risk envelope: kill switch, position count, total exposure.
    /// 檢查風控邊界：Kill Switch、持倉數量、總曝險比例。
    fn check_risk_envelope(&self) -> Option<String> {
        let snap = &self.risk;

        // Kill switch highest priority / Kill Switch 最高優先
        if snap.kill_switch_active {
            return Some("kill_switch_active".to_string());
        }

        // Open position count / 持倉數量上限
        if snap.open_position_count >= self.config.max_open_positions {
            return Some(format!(
                "max_positions_reached_{}_of_{}",
                snap.open_position_count, self.config.max_open_positions
            ));
        }

        // Total exposure / 總曝險比例
        if snap.total_exposure_pct >= self.config.max_total_exposure_pct {
            return Some(format!(
                "exposure_limit_reached_{:.1}pct_of_{:.1}pct",
                snap.total_exposure_pct, self.config.max_total_exposure_pct
            ));
        }

        None
    }

    /// Check whether the system is in a cooldown period.
    /// 檢查系統是否處於冷卻期。
    fn check_cooldown(&self, now_ms: u64) -> Option<String> {
        let cooldown_until = self.risk.cooldown_until_ts_ms;
        if cooldown_until > 0 && now_ms < cooldown_until {
            let remaining_ms = cooldown_until - now_ms;
            return Some(format!("cooldown_active_{remaining_ms}ms_remaining"));
        }
        None
    }

    // ── Shadow mode / 影子模式 ──────────────────────────────────────────────

    /// Shadow check: run all 5 sub-checks, record would-have-blocked, return allowed=True.
    /// 影子檢查：執行全部 5 個子檢查，記錄「本來會阻擋」，返回 allowed=True。
    fn check_shadow(
        &mut self,
        symbol: &str,
        category: &str,
        now_ms: u64,
        start: Instant,
    ) -> H0CheckResult {
        let mut blocks: Vec<String> = Vec::new();

        if let Some(reason) = self.check_freshness(symbol, now_ms) {
            blocks.push(reason);
        }
        if let Some(reason) = self.check_health(now_ms) {
            blocks.push(reason);
        }
        if let Some(reason) = self.check_eligibility(symbol, category) {
            blocks.push(reason);
        }
        if let Some(reason) = self.check_risk_envelope() {
            blocks.push(reason);
        }
        if let Some(reason) = self.check_cooldown(now_ms) {
            blocks.push(reason);
        }

        if !blocks.is_empty() {
            self.stats.shadow_would_block += 1;
            // Circular buffer: evict oldest if at capacity.
            // 環形緩衝區：滿時移除最舊條目。
            if self.shadow_log.len() >= SHADOW_LOG_MAX {
                self.shadow_log.pop_front();
            }
            self.shadow_log.push_back(ShadowEntry {
                symbol: symbol.to_string(),
                ts_ms: now_ms,
                would_block_reasons: blocks.clone(),
            });
        }

        let reason = if blocks.is_empty() {
            String::new()
        } else {
            format!("shadow_would_block:[{}]", blocks.join(","))
        };

        let check_name = if blocks.is_empty() {
            "shadow_all_passed"
        } else {
            "shadow_would_block"
        };

        self.stats.total_allowed += 1;
        self.finalize_allowed(reason, check_name, start)
    }

    // ── Internal helpers / 內部輔助方法 ─────────────────────────────────────

    /// Finalize a blocked result with latency tracking.
    /// 完成阻擋結果並追蹤延遲。
    fn finalize_blocked(
        &mut self,
        reason: String,
        check_name: &str,
        start: Instant,
    ) -> H0CheckResult {
        // SEC-13: saturating cast to avoid u32 truncation at >~4.29s stalls.
        // SEC-13：使用飽和轉換避免 >~4.29s 停頓時 u32 截斷。
        let latency_us = start.elapsed().as_micros().min(u32::MAX as u128) as u32;
        self.stats.total_latency_us += latency_us as u64;
        if (latency_us as u64) > self.stats.max_latency_us {
            self.stats.max_latency_us = latency_us as u64;
        }
        // P2-LG1-DEMO-SLO-CARVEOUT (2026-05-21)：blocked path latency record。
        // 為什麼條件呼叫：None 路徑保 backward compat（既有 test / cold ctor），
        // 且 None 分支由 monomorphisation 與 branch predictor 處理，overhead ~1ns。
        // Some 路徑呼 record() 內部 spec AC-3 ≤ 50ns（Mutex unconstested + bucket index）。
        if let Some(ref rec) = self.metrics_recorder {
            rec.record(latency_us as u64, self.engine_mode);
        }
        H0CheckResult {
            allowed: false,
            reason,
            check_name: check_name.to_string(),
            latency_us,
        }
    }

    /// Finalize an allowed result with latency tracking.
    /// 完成通過結果並追蹤延遲。
    fn finalize_allowed(
        &mut self,
        reason: String,
        check_name: &str,
        start: Instant,
    ) -> H0CheckResult {
        // SEC-13: saturating cast to avoid u32 truncation at >~4.29s stalls.
        // SEC-13：使用飽和轉換避免 >~4.29s 停頓時 u32 截斷。
        let latency_us = start.elapsed().as_micros().min(u32::MAX as u128) as u32;
        self.stats.total_latency_us += latency_us as u64;
        if (latency_us as u64) > self.stats.max_latency_us {
            self.stats.max_latency_us = latency_us as u64;
        }
        // P2-LG1-DEMO-SLO-CARVEOUT (2026-05-21)：allowed path latency record。
        // 設計同 finalize_blocked；shadow mode 也走此路徑（finalize_allowed），
        // 因此 shadow_would_block 樣本也計入 percentile（shadow mode 是 H0 hot path
        // 完整 5 子檢查的子集，latency 觀測語意一致）。
        if let Some(ref rec) = self.metrics_recorder {
            rec.record(latency_us as u64, self.engine_mode);
        }
        H0CheckResult {
            allowed: true,
            reason,
            check_name: check_name.to_string(),
            latency_us,
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
#[path = "h0_gate/tests.rs"]
mod tests;
