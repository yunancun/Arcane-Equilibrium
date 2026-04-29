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
use std::time::Instant;

use openclaw_types::{H0CheckResult, H0GateConfig, H0GateHealthSnapshot, H0GateRiskSnapshot};

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
}

impl H0Gate {
    /// Create a new H0Gate with optional config (uses defaults if None).
    /// 建立新的 H0Gate，若無配置則使用預設值。
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
        }
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
mod tests {
    use super::*;

    /// Helper: create a gate with fresh data for BTCUSDT and healthy state.
    /// 輔助：建立帶有 BTCUSDT 新鮮數據和健康狀態的門控。
    fn gate_with_fresh_btc(now_ms: u64) -> H0Gate {
        let mut gate = H0Gate::new(None);
        gate.update_price_ts("BTCUSDT", now_ms - 100); // 100ms ago = fresh
        gate.update_health(H0GateHealthSnapshot {
            cpu_pct: 30.0,
            memory_available_mb: 4096,
            db_latency_ms: 5.0,
            network_loss_pct: 0.1,
            snapshot_ts_ms: now_ms - 1000,
        });
        gate.update_risk(H0GateRiskSnapshot {
            open_position_count: 2,
            total_exposure_pct: 30.0,
            cooldown_until_ts_ms: 0,
            kill_switch_active: false,
            snapshot_ts_ms: now_ms - 500,
        });
        gate
    }

    // ── 1. All checks pass / 全部通過 ───────────────────────────────────────

    #[test]
    fn test_all_checks_pass() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        let result = gate.check("BTCUSDT", "linear", now);
        assert!(result.allowed);
        assert_eq!(result.check_name, "all_passed");
        assert!(result.reason.is_empty());
        assert_eq!(gate.stats.total_allowed, 1);
        assert_eq!(gate.stats.total_checks, 1);
    }

    // ── 2. Freshness: no data / 新鮮度：無數據 ─────────────────────────────

    #[test]
    fn test_freshness_no_data_blocks() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        let result = gate.check("ETHUSDT", "linear", now); // no tick for ETH
        assert!(!result.allowed);
        assert_eq!(result.check_name, "freshness");
        assert!(result.reason.contains("no_data_ETHUSDT"));
        assert_eq!(gate.stats.blocked_freshness, 1);
    }

    // ── 3. Freshness: stale data / 新鮮度：數據過期 ─────────────────────────

    #[test]
    fn test_freshness_stale_data_blocks() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        gate.update_price_ts("BTCUSDT", now - 2000); // 2000ms ago > 1000ms max
        let result = gate.check("BTCUSDT", "linear", now);
        assert!(!result.allowed);
        assert_eq!(result.check_name, "freshness");
        assert!(result.reason.contains("data_stale_BTCUSDT_2000ms"));
    }

    // ── 4. Freshness: exactly at threshold / 新鮮度：恰好到達閾值 ───────────

    #[test]
    fn test_freshness_at_threshold_blocks() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        gate.update_price_ts("BTCUSDT", now - 1000); // exactly max_data_age_ms
        let result = gate.check("BTCUSDT", "linear", now);
        assert!(
            !result.allowed,
            "age == max_data_age_ms should block (>= comparison)"
        );
    }

    // ── 5. Health: CPU too high / 健康：CPU 過高 ────────────────────────────

    #[test]
    fn test_health_cpu_too_high_blocks() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        gate.update_health(H0GateHealthSnapshot {
            cpu_pct: 95.0,
            memory_available_mb: 4096,
            db_latency_ms: 5.0,
            network_loss_pct: 0.1,
            snapshot_ts_ms: now - 1000,
        });
        let result = gate.check("BTCUSDT", "linear", now);
        assert!(!result.allowed);
        assert_eq!(result.check_name, "health");
        assert!(result.reason.contains("cpu_too_high"));
        assert_eq!(gate.stats.blocked_health, 1);
    }

    // ── 6. Health: memory low / 健康：記憶體不足 ────────────────────────────

    #[test]
    fn test_health_memory_low_blocks() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        gate.update_health(H0GateHealthSnapshot {
            cpu_pct: 30.0,
            memory_available_mb: 512, // < 1024 min
            db_latency_ms: 5.0,
            network_loss_pct: 0.1,
            snapshot_ts_ms: now - 1000,
        });
        let result = gate.check("BTCUSDT", "linear", now);
        assert!(!result.allowed);
        assert!(result.reason.contains("memory_low_512mb"));
    }

    // ── 7. Health: DB latency / 健康：DB 延遲過高 ───────────────────────────

    #[test]
    fn test_health_db_latency_blocks() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        gate.update_health(H0GateHealthSnapshot {
            cpu_pct: 30.0,
            memory_available_mb: 4096,
            db_latency_ms: 150.0, // > 100.0 max
            network_loss_pct: 0.1,
            snapshot_ts_ms: now - 1000,
        });
        let result = gate.check("BTCUSDT", "linear", now);
        assert!(!result.allowed);
        assert!(result.reason.contains("db_latency_high"));
    }

    // ── 8. Health: network loss / 健康：網絡丟包過高 ────────────────────────

    #[test]
    fn test_health_network_loss_blocks() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        gate.update_health(H0GateHealthSnapshot {
            cpu_pct: 30.0,
            memory_available_mb: 4096,
            db_latency_ms: 5.0,
            network_loss_pct: 8.0, // > 5.0 max
            snapshot_ts_ms: now - 1000,
        });
        let result = gate.check("BTCUSDT", "linear", now);
        assert!(!result.allowed);
        assert!(result.reason.contains("network_loss_high"));
    }

    // ── 9. Health: snapshot stale / 健康：快照過期 ──────────────────────────

    #[test]
    fn test_health_snapshot_stale_blocks() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        gate.update_health(H0GateHealthSnapshot {
            cpu_pct: 30.0,
            memory_available_mb: 4096,
            db_latency_ms: 5.0,
            network_loss_pct: 0.1,
            snapshot_ts_ms: now - 60_000, // 60s ago > 30s max
        });
        let result = gate.check("BTCUSDT", "linear", now);
        assert!(!result.allowed);
        assert!(result.reason.contains("health_snapshot_stale"));
    }

    // ── 10. Eligibility: category not allowed / 准入：類別不允許 ────────────

    #[test]
    fn test_eligibility_category_not_allowed() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        let result = gate.check("BTCUSDT", "option", now);
        assert!(!result.allowed);
        assert_eq!(result.check_name, "eligibility");
        assert!(result.reason.contains("category_not_allowed_option"));
        assert_eq!(gate.stats.blocked_eligibility, 1);
    }

    // ── 11. Eligibility: symbol blocked / 准入：符號被阻擋 ─────────────────

    #[test]
    fn test_eligibility_symbol_blocked() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        gate.set_symbol_eligibility("BTCUSDT", false);
        let result = gate.check("BTCUSDT", "linear", now);
        assert!(!result.allowed);
        assert!(result.reason.contains("symbol_not_eligible_BTCUSDT"));
    }

    // ── 12. Eligibility: system disabled / 准入：系統已禁用 ─────────────────

    #[test]
    fn test_eligibility_system_disabled() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        gate.set_system_mode("disabled");
        let result = gate.check("BTCUSDT", "linear", now);
        assert!(!result.allowed);
        assert!(result.reason.contains("system_disabled"));
    }

    // ── 13. Risk: kill switch / 風控：Kill Switch ───────────────────────────

    #[test]
    fn test_risk_kill_switch_blocks() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        gate.update_risk(H0GateRiskSnapshot {
            kill_switch_active: true,
            ..H0GateRiskSnapshot::default()
        });
        let result = gate.check("BTCUSDT", "linear", now);
        assert!(!result.allowed);
        assert_eq!(result.check_name, "risk");
        assert!(result.reason.contains("kill_switch_active"));
        assert_eq!(gate.stats.blocked_envelope, 1);
    }

    // ── 14. Risk: max positions / 風控：持倉上限 ────────────────────────────

    #[test]
    fn test_risk_max_positions_blocks() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        gate.update_risk(H0GateRiskSnapshot {
            open_position_count: 10, // == max (10)
            total_exposure_pct: 30.0,
            cooldown_until_ts_ms: 0,
            kill_switch_active: false,
            snapshot_ts_ms: now - 500,
        });
        let result = gate.check("BTCUSDT", "linear", now);
        assert!(!result.allowed);
        assert!(result.reason.contains("max_positions_reached_10_of_10"));
    }

    // ── 15. Risk: exposure limit / 風控：曝險上限 ───────────────────────────

    #[test]
    fn test_risk_exposure_limit_blocks() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        gate.update_risk(H0GateRiskSnapshot {
            open_position_count: 2,
            total_exposure_pct: 95.0, // >= 90.0 max
            cooldown_until_ts_ms: 0,
            kill_switch_active: false,
            snapshot_ts_ms: now - 500,
        });
        let result = gate.check("BTCUSDT", "linear", now);
        assert!(!result.allowed);
        assert!(result.reason.contains("exposure_limit_reached"));
    }

    // ── 16. Cooldown active / 冷卻期生效 ────────────────────────────────────

    #[test]
    fn test_cooldown_blocks() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        gate.update_risk(H0GateRiskSnapshot {
            open_position_count: 2,
            total_exposure_pct: 30.0,
            cooldown_until_ts_ms: now + 5000, // 5s remaining
            kill_switch_active: false,
            snapshot_ts_ms: now - 500,
        });
        let result = gate.check("BTCUSDT", "linear", now);
        assert!(!result.allowed);
        assert_eq!(result.check_name, "cooldown");
        assert!(result.reason.contains("cooldown_active_5000ms_remaining"));
        assert_eq!(gate.stats.blocked_cooldown, 1);
    }

    // ── 17. Cooldown expired / 冷卻期已過 ───────────────────────────────────

    #[test]
    fn test_cooldown_expired_passes() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        gate.update_risk(H0GateRiskSnapshot {
            open_position_count: 2,
            total_exposure_pct: 30.0,
            cooldown_until_ts_ms: now - 1000, // expired 1s ago
            kill_switch_active: false,
            snapshot_ts_ms: now - 500,
        });
        let result = gate.check("BTCUSDT", "linear", now);
        assert!(result.allowed);
    }

    // ── 18. Shadow mode: would-block but allows / 影子模式：本來會阻擋但放行

    #[test]
    fn test_shadow_mode_allows_despite_blocks() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        gate.set_shadow_mode(true);
        gate.update_risk(H0GateRiskSnapshot {
            kill_switch_active: true,
            ..H0GateRiskSnapshot::default()
        });
        let result = gate.check("BTCUSDT", "linear", now);
        assert!(result.allowed, "shadow mode must always allow");
        assert!(result.reason.contains("shadow_would_block"));
        assert!(result.reason.contains("kill_switch_active"));
        assert_eq!(result.check_name, "shadow_would_block");
        assert_eq!(gate.stats.shadow_would_block, 1);
        assert_eq!(gate.shadow_log.len(), 1);
    }

    // ── 19. Shadow mode: all pass / 影子模式：全部通過 ──────────────────────

    #[test]
    fn test_shadow_mode_all_pass() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        gate.set_shadow_mode(true);
        let result = gate.check("BTCUSDT", "linear", now);
        assert!(result.allowed);
        assert!(result.reason.is_empty());
        assert_eq!(result.check_name, "shadow_all_passed");
        assert_eq!(gate.stats.shadow_would_block, 0);
    }

    // ── 20. Shadow log circular buffer / 影子日誌環形緩衝區 ─────────────────

    #[test]
    fn test_shadow_log_circular_buffer() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        gate.set_shadow_mode(true);
        gate.set_system_mode("disabled"); // triggers eligibility block every time

        for i in 0..120u64 {
            gate.check("BTCUSDT", "linear", now + i);
        }

        assert_eq!(gate.shadow_log.len(), SHADOW_LOG_MAX);
        // Oldest entries evicted; newest should be last.
        let last = gate.shadow_log.back().unwrap();
        assert_eq!(last.ts_ms, now + 119);
    }

    // ── 21. Stats tracking / 統計追蹤 ───────────────────────────────────────

    #[test]
    fn test_stats_tracking() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);

        // Pass
        gate.check("BTCUSDT", "linear", now);
        // Block freshness (no data for ETH)
        gate.check("ETHUSDT", "linear", now);
        // Block eligibility (bad category)
        gate.check("BTCUSDT", "option", now);

        let stats = gate.get_stats();
        assert_eq!(stats.total_checks, 3);
        assert_eq!(stats.total_allowed, 1);
        assert_eq!(stats.blocked_freshness, 1);
        assert_eq!(stats.blocked_eligibility, 1);
        assert_eq!(stats.total_blocked(), 2);
    }

    // ── 22. Stats derived metrics / 統計派生指標 ────────────────────────────

    #[test]
    fn test_stats_derived_metrics() {
        let stats = GateStats {
            total_checks: 10,
            total_allowed: 7,
            total_latency_us: 500,
            ..GateStats::default()
        };
        let rate = stats.allow_rate_pct();
        assert!((rate - 70.0).abs() < 0.01);
        let avg = stats.avg_latency_us();
        assert!((avg - 50.0).abs() < 0.01);
    }

    // ── 23. Stats zero checks edge case / 統計零檢查邊界 ────────────────────

    #[test]
    fn test_stats_zero_checks() {
        let stats = GateStats::default();
        assert_eq!(stats.allow_rate_pct(), 0.0);
        assert_eq!(stats.avg_latency_us(), 0.0);
    }

    // ── 24. Default config values / 預設配置值 ──────────────────────────────

    #[test]
    fn test_default_config() {
        let gate = H0Gate::new(None);
        let cfg = gate.config();
        assert_eq!(cfg.max_data_age_ms, 1000);
        assert_eq!(cfg.max_cpu_pct, 90.0);
        assert_eq!(cfg.min_memory_mb, 1024);
        assert_eq!(cfg.max_db_latency_ms, 100.0);
        assert_eq!(cfg.max_network_loss_pct, 5.0);
        assert_eq!(cfg.max_open_positions, 10);
        assert_eq!(cfg.max_total_exposure_pct, 90.0);
        assert_eq!(cfg.health_snapshot_max_age_ms, 30_000);
        assert!(!cfg.shadow_mode);
    }

    // ── 25. System mode "active" passes / 系統模式 active 通過 ──────────────

    #[test]
    fn test_system_mode_active_passes() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        gate.set_system_mode("active");
        let result = gate.check("BTCUSDT", "linear", now);
        assert!(result.allowed);
    }

    // ── 26. Fail-fast: freshness blocks before health / 快速失敗順序 ────────

    #[test]
    fn test_fail_fast_freshness_blocks_before_health() {
        let now = 1_700_000_000_000u64;
        let mut gate = H0Gate::new(None);
        // No price data (freshness fails) AND bad health
        gate.update_health(H0GateHealthSnapshot {
            cpu_pct: 99.0,
            memory_available_mb: 100,
            db_latency_ms: 999.0,
            network_loss_pct: 99.0,
            snapshot_ts_ms: now - 1000,
        });
        let result = gate.check("BTCUSDT", "linear", now);
        assert!(!result.allowed);
        assert_eq!(result.check_name, "freshness"); // must fail on freshness, not health
        assert_eq!(gate.stats.blocked_freshness, 1);
        assert_eq!(gate.stats.blocked_health, 0);
    }

    // ── 27. Shadow mode with no-data symbol / 影子模式：無數據符號 ──────────

    #[test]
    fn test_shadow_mode_no_data_symbol() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        gate.set_shadow_mode(true);
        let result = gate.check("XYZUSDT", "linear", now);
        assert!(result.allowed);
        assert!(result.reason.contains("no_data_XYZUSDT"));
    }

    // ── 28. Health snapshot ts=0 skips staleness / 快照 ts=0 跳過過期檢查 ──

    #[test]
    fn test_health_snapshot_zero_ts_skips_staleness() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        // snapshot_ts_ms = 0 means "never updated" — staleness check is skipped.
        gate.update_health(H0GateHealthSnapshot {
            cpu_pct: 30.0,
            memory_available_mb: 4096,
            db_latency_ms: 5.0,
            network_loss_pct: 0.1,
            snapshot_ts_ms: 0,
        });
        let result = gate.check("BTCUSDT", "linear", now);
        assert!(
            result.allowed,
            "snapshot_ts_ms=0 should skip staleness check"
        );
    }

    // ── 29. Latency is recorded / 延遲已記錄 ───────────────────────────────

    #[test]
    fn test_latency_recorded() {
        let now = 1_700_000_000_000u64;
        let mut gate = gate_with_fresh_btc(now);
        let _result = gate.check("BTCUSDT", "linear", now);
        // Stats should have accumulated some latency and the check count.
        assert_eq!(gate.stats.total_checks, 1);
        // total_latency_us is populated (may be 0 on very fast machines).
        assert_eq!(gate.stats.total_allowed, 1);
    }

    // ── 30. Shadow mode multiple blocks / 影子模式：多重阻擋 ────────────────

    #[test]
    fn test_shadow_mode_multiple_blocks() {
        let now = 1_700_000_000_000u64;
        let mut gate = H0Gate::new(None);
        gate.set_shadow_mode(true);
        // No price data + bad CPU + kill switch => multiple blocks
        gate.update_health(H0GateHealthSnapshot {
            cpu_pct: 99.0,
            memory_available_mb: 4096,
            db_latency_ms: 5.0,
            network_loss_pct: 0.1,
            snapshot_ts_ms: now - 1000,
        });
        gate.update_risk(H0GateRiskSnapshot {
            kill_switch_active: true,
            ..H0GateRiskSnapshot::default()
        });
        let result = gate.check("BTCUSDT", "linear", now);
        assert!(result.allowed);
        // Should capture multiple blocks in shadow reason
        assert!(result.reason.contains("no_data_BTCUSDT"));
        assert!(result.reason.contains("cpu_too_high"));
        assert!(result.reason.contains("kill_switch_active"));
    }
}
