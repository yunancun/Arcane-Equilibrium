//! BudgetTracker — core AI budget enforcement state.
//! BudgetTracker — AI 預算強制執行核心狀態。
//!
//! MODULE_NOTE (EN): Hot-reloadable BudgetConfig (5 scopes), atomic refresh stamp,
//!   per-scope month-to-date USD usage cache. Three-stage degradation thresholds
//!   are computed against the `local_total` scope (the operator-controlled monthly
//!   budget). Pricing is a placeholder const map keyed by model id (4-17 will
//!   replace with PG table).
//! MODULE_NOTE (中): 可熱重載的 BudgetConfig（5 個 scope）、原子刷新時間戳、
//!   per-scope 月內已用 USD 快取。三段降級閾值以 `local_total` scope 為基準
//!   （operator 可調月度預算）。定價為以 model id 為鍵的占位 const map（4-17
//!   會改用 PG 表）。

use crate::database::pool::DbPool;
use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{debug, info, warn};

use super::pricing::{self, PricingTable};
use super::{config_io, usage_io};

// ---------------------------------------------------------------------------
// Budget scope constants / 預算 scope 常量
// ---------------------------------------------------------------------------

/// Operator-controlled local monthly budget (default $100).
/// Operator 可調本地月度預算（預設 $100）。
pub const SCOPE_LOCAL_TOTAL: &str = "local_total";
/// Hard ceiling above which all LLM calls are blocked (default $150).
/// 平台硬上限，超過後阻斷所有 LLM 調用（預設 $150）。
pub const SCOPE_PLATFORM_HARD_CAP: &str = "platform_hard_cap";
/// Per-agent envelope: Teacher / Analyst / Reserve.
/// per-agent 預算：Teacher / Analyst / Reserve。
pub const SCOPE_AGENT_TEACHER: &str = "agent_teacher";
pub const SCOPE_AGENT_ANALYST: &str = "agent_analyst";
pub const SCOPE_AGENT_RESERVE: &str = "agent_reserve";

/// All 5 known scopes — used for default seeding and validation.
/// 全部 5 個已知 scope — 用於預設種子和驗證。
pub const KNOWN_SCOPES: &[&str] = &[
    SCOPE_LOCAL_TOTAL,
    SCOPE_PLATFORM_HARD_CAP,
    SCOPE_AGENT_TEACHER,
    SCOPE_AGENT_ANALYST,
    SCOPE_AGENT_RESERVE,
];

// ---------------------------------------------------------------------------
// Pricing — loaded from settings/ai_pricing.yaml (4-17 / FA GAP-10).
// 定價 — 從 settings/ai_pricing.yaml 載入。
// ---------------------------------------------------------------------------
//
// As of 4-17 the pricing table is YAML-loaded into a `PricingTable` and
// injected into BudgetTracker. The previous hardcoded const map is removed.
// Fail-closed: BudgetTracker::new returns Err if the YAML cannot be loaded.
// Lookups for unknown OR inactive models still return Err to upstream callers.
//
// 4-17 起，定價表透過 YAML 載入為 `PricingTable` 並注入 BudgetTracker。
// 之前的硬編碼 const map 已移除。fail-closed：YAML 載入失敗時 BudgetTracker::new
// 返回 Err。未知或 inactive 模型對 caller 仍返回 Err。

// ---------------------------------------------------------------------------
// Budget config + degrade level / 預算配置 + 降級等級
// ---------------------------------------------------------------------------

/// In-memory snapshot of `learning.ai_budget_config` (all 5 scopes).
/// `learning.ai_budget_config` 的內存快照（全 5 個 scope）。
#[derive(Debug, Clone)]
pub struct BudgetConfig {
    /// scope → monthly USD ceiling / scope → 月度美元上限
    pub limits: HashMap<String, f64>,
}

impl BudgetConfig {
    /// Default seeds matching V010 INSERT defaults.
    /// 與 V010 INSERT 預設值一致的預設種子。
    pub fn defaults() -> Self {
        let mut limits = HashMap::new();
        limits.insert(SCOPE_LOCAL_TOTAL.to_string(), 100.0);
        limits.insert(SCOPE_PLATFORM_HARD_CAP.to_string(), 150.0);
        limits.insert(SCOPE_AGENT_TEACHER.to_string(), 60.0);
        limits.insert(SCOPE_AGENT_ANALYST.to_string(), 30.0);
        limits.insert(SCOPE_AGENT_RESERVE.to_string(), 10.0);
        Self { limits }
    }

    /// Get monthly limit for a scope (0.0 if unknown — fail-closed treats as zero budget).
    /// 取得 scope 的月度上限（未知 scope 返回 0.0 — fail-closed 視為零預算）。
    pub fn limit(&self, scope: &str) -> f64 {
        self.limits.get(scope).copied().unwrap_or(0.0)
    }
}

/// Three-stage degradation level driven by `local_total` MTD usage.
/// 由 `local_total` 月內已用驅動的三段降級等級。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DegradeLevel {
    /// < $80 used — full capability / < $80 — 全能力
    None,
    /// $80–$95 — stop Analyst, Teacher only / $80–$95 — 停 Analyst，僅 Teacher
    SoftWarn,
    /// $95–$100 — only Teacher P0 calls allowed / $95–$100 — 僅 Teacher P0 調用
    HardLimit,
    /// >= $100 — all LLM calls blocked / >= $100 — 全部阻斷
    Killswitch,
}

impl DegradeLevel {
    /// Compute degrade level from current MTD usage and the local_total ceiling.
    /// 根據當前月內已用與 local_total 上限計算降級等級。
    ///
    /// Thresholds (Phase 4 Q1 spec): 80% / 95% / 100% of `local_total`.
    /// 閾值（Phase 4 Q1 規格）：local_total 的 80% / 95% / 100%。
    pub fn from_usage(usage_usd: f64, local_total_limit_usd: f64) -> Self {
        // Fail-closed: a non-positive limit means budget unconfigured → killswitch.
        // fail-closed：非正上限視為未配置 → killswitch。
        if local_total_limit_usd <= 0.0 {
            return DegradeLevel::Killswitch;
        }
        let ratio = usage_usd / local_total_limit_usd;
        if ratio >= 1.0 {
            DegradeLevel::Killswitch
        } else if ratio >= 0.95 {
            DegradeLevel::HardLimit
        } else if ratio >= 0.80 {
            DegradeLevel::SoftWarn
        } else {
            DegradeLevel::None
        }
    }

    /// Stable string label (used in IPC payloads).
    /// 穩定字串標籤（IPC payload 使用）。
    pub fn as_str(&self) -> &'static str {
        match self {
            DegradeLevel::None => "none",
            DegradeLevel::SoftWarn => "soft_warn",
            DegradeLevel::HardLimit => "hard_limit",
            DegradeLevel::Killswitch => "killswitch",
        }
    }
}

// ---------------------------------------------------------------------------
// BudgetTracker / 預算追蹤器
// ---------------------------------------------------------------------------

/// Cached month-to-date usage (scope → USD).
/// 月內已用快取（scope → 美元）。
#[derive(Debug, Default, Clone)]
struct UsageCache {
    /// Per-scope MTD spend (USD) / per-scope 月內已用（美元）
    mtd_usd: HashMap<String, f64>,
    /// Wall-clock millis when this snapshot was last refreshed from DB.
    /// 從 DB 上次刷新此快照的牆鐘毫秒。
    refreshed_at_ms: u64,
}

/// AI budget tracker — fail-closed enforcement of the $100/$150 ceilings.
/// AI 預算追蹤器 — fail-closed 強制 $100/$150 上限。
pub struct BudgetTracker {
    /// PG pool wrapper. None means DB-disabled mode (tests/cold start).
    /// PG 連接池包裝。None 表示 DB 禁用模式（測試/冷啟動）。
    pool: Arc<DbPool>,
    /// Hot-reloadable config snapshot.
    /// 可熱重載的配置快照。
    config_cache: Arc<RwLock<BudgetConfig>>,
    /// Month-to-date usage snapshot.
    /// 月內已用快照。
    usage_cache: Arc<RwLock<UsageCache>>,
    /// Pricing table loaded from settings/ai_pricing.yaml at boot (4-17).
    /// 啟動時從 settings/ai_pricing.yaml 載入的定價表（4-17）。
    pricing: Arc<PricingTable>,
    /// Last config refresh wall-clock millis (atomic for lock-free reads).
    /// 上次配置刷新的牆鐘毫秒（原子，便於無鎖讀取）。
    last_config_refresh_ms: AtomicU64,
}

impl BudgetTracker {
    /// Build a new BudgetTracker; loads config + MTD usage from PG if pool is up.
    /// Falls back to in-memory defaults when PG is unavailable (cold start safe).
    /// 構建新 BudgetTracker；若 pool 可用則從 PG 載入 config + MTD 用量。
    /// PG 不可用時回退到內存預設（冷啟動安全）。
    pub async fn new(pool: Arc<DbPool>) -> Result<Self, String> {
        // 4-17: load pricing table fail-closed.
        // 4-17：載入定價表 fail-closed。
        let pricing_table = pricing::load_default()
            .map_err(|e| format!("BudgetTracker: pricing load failed (4-17 fail-closed): {e}"))?;
        info!(
            active_models = pricing_table.active_count(),
            total_models = pricing_table.total_count(),
            "BudgetTracker pricing table loaded / 預算追蹤器定價表已載入"
        );
        let pricing = Arc::new(pricing_table);

        let config = if pool.is_available() {
            match config_io::load_all(&pool).await {
                Ok(cfg) => cfg,
                Err(e) => {
                    warn!(error = %e, "BudgetTracker: config load failed, using defaults / 配置載入失敗，使用預設");
                    BudgetConfig::defaults()
                }
            }
        } else {
            BudgetConfig::defaults()
        };

        let usage = if pool.is_available() {
            match usage_io::load_mtd_usage(&pool).await {
                Ok(map) => UsageCache {
                    mtd_usd: map,
                    refreshed_at_ms: now_ms(),
                },
                Err(e) => {
                    warn!(error = %e, "BudgetTracker: MTD usage load failed, starting at zero / MTD 用量載入失敗，從零開始");
                    UsageCache {
                        mtd_usd: HashMap::new(),
                        refreshed_at_ms: now_ms(),
                    }
                }
            }
        } else {
            UsageCache {
                mtd_usd: HashMap::new(),
                refreshed_at_ms: now_ms(),
            }
        };

        info!(
            local_total = config.limit(SCOPE_LOCAL_TOTAL),
            platform_hard_cap = config.limit(SCOPE_PLATFORM_HARD_CAP),
            agent_teacher = config.limit(SCOPE_AGENT_TEACHER),
            agent_analyst = config.limit(SCOPE_AGENT_ANALYST),
            agent_reserve = config.limit(SCOPE_AGENT_RESERVE),
            "BudgetTracker initialized / 預算追蹤器已初始化"
        );

        Ok(Self {
            pool,
            config_cache: Arc::new(RwLock::new(config)),
            usage_cache: Arc::new(RwLock::new(usage)),
            pricing,
            last_config_refresh_ms: AtomicU64::new(now_ms()),
        })
    }

    /// Test-only constructor with explicit config + zero usage cache.
    /// Pricing table defaults to a synthetic 1-model table covering claude-sonnet-4-5
    /// at the canonical $3/$15 rates so existing cost-calculation tests pass without
    /// touching the filesystem.
    /// 測試專用構造器：顯式 config + 零用量快取。
    /// 預設定價表為單一模型 claude-sonnet-4-5（$3/$15），讓現有 cost 測試無需動檔案系統。
    #[cfg(test)]
    pub fn new_for_test(pool: Arc<DbPool>, config: BudgetConfig) -> Self {
        let mut map = HashMap::new();
        map.insert(
            "claude-sonnet-4-5".to_string(),
            super::pricing::ModelPricing {
                input_per_mtok: 3.0,
                output_per_mtok: 15.0,
                active: true,
            },
        );
        let pricing = Arc::new(super::pricing::PricingTable::from_map_for_test(map));
        Self {
            pool,
            config_cache: Arc::new(RwLock::new(config)),
            usage_cache: Arc::new(RwLock::new(UsageCache::default())),
            pricing,
            last_config_refresh_ms: AtomicU64::new(now_ms()),
        }
    }

    /// Compute USD cost for a given model + token counts via the loaded pricing table.
    /// fail-closed: unknown OR inactive model returns Err.
    /// 透過已載入的定價表計算 USD 成本。fail-closed：未知或 inactive 模型返回 Err。
    pub fn compute_cost_usd(
        &self,
        model: &str,
        tokens_in: u32,
        tokens_out: u32,
    ) -> Result<f64, String> {
        self.pricing
            .compute_cost(model, tokens_in, tokens_out)
            .ok_or_else(|| format!("unknown model pricing: {model}"))
    }

    /// Borrow a clone of the underlying DbPool handle (used by IPC handlers
    /// that need to perform DB writes via config_io / usage_io).
    /// 借出底層 DbPool 句柄的 clone（IPC handler 透過 config_io / usage_io 寫 DB 用）。
    pub fn pool_handle(&self) -> Arc<DbPool> {
        Arc::clone(&self.pool)
    }

    /// Reload config from PG. Used by IPC `update_ai_budget_config` after a write.
    /// 從 PG 重載配置。IPC `update_ai_budget_config` 寫入後使用。
    pub async fn refresh_config(&self) -> Result<(), String> {
        if !self.pool.is_available() {
            // No PG → keep current cache; not an error in test/cold-start mode.
            // 無 PG → 保留當前快取；測試/冷啟動模式下非錯誤。
            return Ok(());
        }
        let cfg = config_io::load_all(&self.pool).await?;
        let mut guard = self.config_cache.write().await;
        *guard = cfg;
        self.last_config_refresh_ms
            .store(now_ms(), Ordering::Relaxed);
        debug!("BudgetTracker config refreshed / 配置已重載");
        Ok(())
    }

    /// Reload MTD usage from PG (called periodically or on-demand).
    /// 從 PG 重載月內已用（定期或按需）。
    pub async fn refresh_usage(&self) -> Result<(), String> {
        if !self.pool.is_available() {
            return Ok(());
        }
        let map = usage_io::load_mtd_usage(&self.pool).await?;
        let mut guard = self.usage_cache.write().await;
        guard.mtd_usd = map;
        guard.refreshed_at_ms = now_ms();
        Ok(())
    }

    /// Record an LLM usage event. **Fail-closed**: returns Err on DB write failure
    /// (or unknown model pricing) — caller MUST refuse to forward the LLM call.
    /// On success, returns the computed USD cost and updates the in-memory cache.
    ///
    /// 記錄一次 LLM 用量事件。**Fail-closed**：DB 寫入失敗（或模型定價未知）
    /// 時返回 Err — caller 必須拒絕該次 LLM 調用。成功時返回計算出的美元成本
    /// 並更新內存快取。
    ///
    /// E5-FN-2 (audit §七 7.2): when `insert_usage` dedupes a row by
    /// `request_id` (duplicate INSERT skipped by V018 partial UNIQUE index),
    /// the in-memory cost accumulator is **also** skipped so that retried
    /// writes do not double-bill the scope or drive `local_total` past the
    /// killswitch from the same LLM call.
    /// E5-FN-2（audit §七 7.2）：若 DB 端以 request_id 去重跳過了 INSERT，
    /// 內存累加同步跳過，避免重試把同一次 LLM 調用雙計。
    pub async fn record_usage(
        &self,
        scope: &str,
        provider: &str,
        model: &str,
        tokens_in: u32,
        tokens_out: u32,
        purpose: &str,
        request_id: &str,
    ) -> Result<f64, String> {
        // 1) Pricing — fail-closed on unknown / inactive model (4-17 PricingTable).
        //    定價 — 未知或 inactive 模型 fail-closed（4-17 PricingTable）。
        let cost_usd = self.compute_cost_usd(model, tokens_in, tokens_out)?;

        // 2) DB write — fail-closed: any error propagates to caller.
        //    `inserted=true`  → brand-new row, bill the scope.
        //    `inserted=false` → duplicate request_id deduped by V018 index,
        //                       skip the cache increment to avoid double-count.
        //    When `pool` is unavailable (tests / cold start), behave as if the
        //    write succeeded so the in-memory cache still accumulates — this
        //    preserves the pre-E5-FN-2 contract for offline scenarios.
        //
        // DB 寫入 — fail-closed：除去重外任何錯誤上拋。
        //   inserted=true  → 新行，累加 scope 計數。
        //   inserted=false → request_id 被 V018 索引去重，**不**累加快取。
        //   pool 不可用（測試 / 冷啟動）視為成功以保留原合約。
        let inserted = if self.pool.is_available() {
            usage_io::insert_usage(
                &self.pool,
                scope,
                provider,
                model,
                tokens_in as i32,
                tokens_out as i32,
                cost_usd,
                purpose,
                request_id,
            )
            .await?
        } else {
            true
        };

        // 3) Update in-memory MTD cache (after successful, non-dedupped DB write).
        //    更新內存 MTD 快取（DB 寫入成功且非去重時）。
        if inserted {
            let mut guard = self.usage_cache.write().await;
            *guard.mtd_usd.entry(scope.to_string()).or_insert(0.0) += cost_usd;
            // Also accumulate into local_total so degrade_level reflects the spend.
            // 同時累進 local_total，使 degrade_level 反映開銷。
            if scope != SCOPE_LOCAL_TOTAL {
                *guard
                    .mtd_usd
                    .entry(SCOPE_LOCAL_TOTAL.to_string())
                    .or_insert(0.0) += cost_usd;
            }
        }

        Ok(cost_usd)
    }

    /// Build a canonical request_id for BudgetTracker.record_usage (E5-FN-2).
    /// 為 BudgetTracker.record_usage 構造標準 request_id（E5-FN-2）。
    ///
    /// Format: `{scope}-{ts_ms}-{rand_hex8}` (e.g., `agent_teacher-1713474000123-a1b2c3d4`).
    /// - `scope`    — budget scope for debuggability / 便於除錯的 scope 標籤
    /// - `ts_ms`    — wall-clock ms for ordering / 牆鐘毫秒（排序用）
    /// - `rand_hex8`— 8 hex chars for intra-ms uniqueness / 同一毫秒內去撞
    ///
    /// Callers that need to **retry** a known-in-flight LLM call MUST pass the
    /// same request_id through both attempts so the V018 partial UNIQUE index
    /// can dedup the second write. Use this helper to mint the request_id once
    /// at the top of the call site, stash it, and pass it to every retry.
    /// 想重試時**必須**沿用同一 request_id；在 call site 頂端呼叫本 helper 一次、
    /// 暫存後於每次重試傳入，讓 V018 索引去重第二次寫入。
    pub fn make_request_id(scope: &str) -> String {
        use rand::Rng;
        let ts_ms = now_ms();
        let rand_suffix: u32 = rand::thread_rng().gen();
        format!("{scope}-{ts_ms}-{rand_suffix:08x}")
    }

    /// Remaining USD for a scope this month (limit − MTD usage; clamped at 0).
    /// 該 scope 本月剩餘美元（上限 − 月內已用，下限 0）。
    pub async fn get_remaining(&self, scope: &str) -> Result<f64, String> {
        let cfg = self.config_cache.read().await;
        let usage = self.usage_cache.read().await;
        let limit = cfg.limit(scope);
        let used = usage.mtd_usd.get(scope).copied().unwrap_or(0.0);
        Ok((limit - used).max(0.0))
    }

    /// Current degrade level (driven by `local_total` MTD spend).
    /// 當前降級等級（由 `local_total` 月內開銷驅動）。
    pub async fn degrade_level(&self) -> DegradeLevel {
        let cfg = self.config_cache.read().await;
        let usage = self.usage_cache.read().await;
        let limit = cfg.limit(SCOPE_LOCAL_TOTAL);
        let used = usage.mtd_usd.get(SCOPE_LOCAL_TOTAL).copied().unwrap_or(0.0);
        DegradeLevel::from_usage(used, limit)
    }

    /// AI cost-edge ratio (Principle #13): cumulative AI spend vs gross trading edge.
    /// AI 成本-收益比（原則 #13）：累積 AI 開銷 vs 毛交易收益。
    ///
    /// Until 4-17 wires real PnL, this returns the ratio of MTD `local_total` USD
    /// to the configured `local_total` ceiling — useful as a proxy "burn rate".
    /// A real PnL-based denominator will land with the cost-edge sub-task.
    /// 在 4-17 接入真實 PnL 之前，返回月內 `local_total` 已用 / `local_total`
    /// 上限的比率，作為「燒錢率」代理。真實 PnL 分母由 cost-edge 子任務接入。
    pub async fn cost_edge_ratio(&self) -> Result<f64, String> {
        let cfg = self.config_cache.read().await;
        let usage = self.usage_cache.read().await;
        let limit = cfg.limit(SCOPE_LOCAL_TOTAL);
        if limit <= 0.0 {
            return Ok(f64::INFINITY);
        }
        let used = usage.mtd_usd.get(SCOPE_LOCAL_TOTAL).copied().unwrap_or(0.0);
        Ok(used / limit)
    }

    /// Read-only snapshot of current config + usage + degrade level (IPC `get_ai_budget_status`).
    /// 當前配置 + 用量 + 降級等級的只讀快照（IPC `get_ai_budget_status`）。
    pub async fn status_json(&self) -> serde_json::Value {
        let cfg = self.config_cache.read().await;
        let usage = self.usage_cache.read().await;
        let mut config_obj = serde_json::Map::new();
        let mut usage_obj = serde_json::Map::new();
        let mut remaining_obj = serde_json::Map::new();
        for scope in KNOWN_SCOPES {
            let limit = cfg.limit(scope);
            let used = usage.mtd_usd.get(*scope).copied().unwrap_or(0.0);
            config_obj.insert((*scope).to_string(), serde_json::json!(limit));
            usage_obj.insert((*scope).to_string(), serde_json::json!(used));
            remaining_obj.insert(
                (*scope).to_string(),
                serde_json::json!((limit - used).max(0.0)),
            );
        }
        let local_used = usage.mtd_usd.get(SCOPE_LOCAL_TOTAL).copied().unwrap_or(0.0);
        let local_limit = cfg.limit(SCOPE_LOCAL_TOTAL);
        let level = DegradeLevel::from_usage(local_used, local_limit);
        serde_json::json!({
            "config": config_obj,
            "usage_mtd": usage_obj,
            "remaining": remaining_obj,
            "degrade_level": level.as_str(),
            "last_refresh_ms": usage.refreshed_at_ms,
        })
    }

    /// Apply an in-memory config override (used by IPC `update_ai_budget_config`
    /// after the DB write succeeds, so callers see the new limit immediately).
    /// 套用內存配置覆寫（IPC `update_ai_budget_config` 寫 DB 成功後使用，
    /// 讓 caller 立即看到新上限）。
    pub async fn override_limit(&self, scope: &str, monthly_usd: f64) {
        let mut guard = self.config_cache.write().await;
        guard.limits.insert(scope.to_string(), monthly_usd);
    }

    /// Test-only: directly inject MTD usage to bypass DB.
    /// 測試專用：直接注入 MTD 用量繞過 DB。
    #[cfg(test)]
    pub async fn inject_usage_for_test(&self, scope: &str, usd: f64) {
        let mut guard = self.usage_cache.write().await;
        *guard.mtd_usd.entry(scope.to_string()).or_insert(0.0) += usd;
    }
}

// S-04: use shared now_ms() from openclaw_core instead of local copy.
// S-04：使用 openclaw_core 的共用 now_ms() 取代本地副本。
use openclaw_core::now_ms;

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::database::DatabaseConfig;

    async fn empty_pool() -> Arc<DbPool> {
        let cfg = DatabaseConfig {
            database_url: String::new(),
            ..Default::default()
        };
        Arc::new(DbPool::connect(&cfg).await)
    }

    fn cfg_with_local(local: f64) -> BudgetConfig {
        let mut c = BudgetConfig::defaults();
        c.limits.insert(SCOPE_LOCAL_TOTAL.to_string(), local);
        c
    }

    /// Resolve the repo-root settings/ai_pricing.yaml from CARGO_MANIFEST_DIR for tests.
    /// 從 CARGO_MANIFEST_DIR 解析 repo-root 的 settings/ai_pricing.yaml 給測試用。
    fn set_test_pricing_path() {
        // CARGO_MANIFEST_DIR = .../rust/openclaw_engine ; go up 2 to reach repo root.
        // CARGO_MANIFEST_DIR = .../rust/openclaw_engine ；上溯 2 層到 repo root。
        let manifest = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let yaml = manifest
            .parent()
            .and_then(|p| p.parent())
            .map(|p| p.join("settings").join("ai_pricing.yaml"))
            .expect("repo root resolution");
        std::env::set_var("OPENCLAW_PRICING_PATH", yaml);
    }

    // Test 1: defaults match V010 INSERT seeds.
    // 測試 1：預設值與 V010 INSERT 種子一致。
    #[tokio::test]
    async fn test_budget_config_load_default() {
        set_test_pricing_path();
        let pool = empty_pool().await;
        let tracker = BudgetTracker::new(pool).await.unwrap();
        let cfg = tracker.config_cache.read().await.clone();
        assert_eq!(cfg.limit(SCOPE_LOCAL_TOTAL), 100.0);
        assert_eq!(cfg.limit(SCOPE_PLATFORM_HARD_CAP), 150.0);
        assert_eq!(cfg.limit(SCOPE_AGENT_TEACHER), 60.0);
        assert_eq!(cfg.limit(SCOPE_AGENT_ANALYST), 30.0);
        assert_eq!(cfg.limit(SCOPE_AGENT_RESERVE), 10.0);
        assert_eq!(cfg.limits.len(), 5);
    }

    // Test 2: record_usage updates in-memory MTD cache after success.
    //         (DB write is skipped because pool is empty — covers cache-update path.)
    // 測試 2：record_usage 成功後更新內存 MTD 快取。
    #[tokio::test]
    async fn test_record_usage_writes_log() {
        let pool = empty_pool().await;
        let tracker = BudgetTracker::new_for_test(pool, BudgetConfig::defaults());
        let cost = tracker
            .record_usage(
                SCOPE_AGENT_TEACHER,
                "anthropic",
                "claude-sonnet-4-5",
                1_000,
                500,
                "directive_generation",
                "req-1",
            )
            .await
            .expect("record_usage should succeed");
        assert!(cost > 0.0);
        // Both teacher and local_total accumulators got the same increment.
        let teacher_used = tracker
            .usage_cache
            .read()
            .await
            .mtd_usd
            .get(SCOPE_AGENT_TEACHER)
            .copied()
            .unwrap_or(0.0);
        let local_used = tracker
            .usage_cache
            .read()
            .await
            .mtd_usd
            .get(SCOPE_LOCAL_TOTAL)
            .copied()
            .unwrap_or(0.0);
        assert!((teacher_used - cost).abs() < 1e-9);
        assert!((local_used - cost).abs() < 1e-9);
    }

    // Test 3: claude-sonnet-4-5 cost calc — 1000 in / 500 out.
    //         expected = 1000 * 3 / 1e6 + 500 * 15 / 1e6 = 0.003 + 0.0075 = 0.0105
    // 測試 3：claude-sonnet-4-5 成本計算。
    #[tokio::test]
    async fn test_record_usage_calculates_cost() {
        let pool = empty_pool().await;
        let tracker = BudgetTracker::new_for_test(pool, BudgetConfig::defaults());
        let cost = tracker
            .compute_cost_usd("claude-sonnet-4-5", 1_000, 500)
            .unwrap();
        assert!((cost - 0.0105).abs() < 1e-9, "cost was {cost}");
    }

    // Test 3b: unknown model fails closed.
    // 測試 3b：未知模型 fail-closed。
    #[tokio::test]
    async fn test_unknown_model_fails_closed() {
        let pool = empty_pool().await;
        let tracker = BudgetTracker::new_for_test(pool, BudgetConfig::defaults());
        let err = tracker
            .compute_cost_usd("nonexistent-model-xyz", 100, 100)
            .unwrap_err();
        assert!(err.contains("unknown model pricing"));
    }

    // Test 4: get_remaining subtracts MTD usage from limit.
    // 測試 4：get_remaining 從上限扣減月內已用。
    #[tokio::test]
    async fn test_get_remaining_subtracts_mtd_usage() {
        let pool = empty_pool().await;
        let tracker = BudgetTracker::new_for_test(pool, BudgetConfig::defaults());
        tracker
            .inject_usage_for_test(SCOPE_AGENT_TEACHER, 12.5)
            .await;
        let rem = tracker.get_remaining(SCOPE_AGENT_TEACHER).await.unwrap();
        assert!((rem - (60.0 - 12.5)).abs() < 1e-9);
        // Over-spend clamps at 0.
        tracker
            .inject_usage_for_test(SCOPE_AGENT_TEACHER, 1000.0)
            .await;
        let rem2 = tracker.get_remaining(SCOPE_AGENT_TEACHER).await.unwrap();
        assert_eq!(rem2, 0.0);
    }

    // Tests 5–8: three-stage degrade thresholds.
    // 測試 5–8：三段降級閾值。
    #[tokio::test]
    async fn test_degrade_none_below_80() {
        let pool = empty_pool().await;
        let tracker = BudgetTracker::new_for_test(pool, cfg_with_local(100.0));
        tracker
            .inject_usage_for_test(SCOPE_LOCAL_TOTAL, 79.99)
            .await;
        assert_eq!(tracker.degrade_level().await, DegradeLevel::None);
    }

    #[tokio::test]
    async fn test_degrade_soft_warn_at_80() {
        let pool = empty_pool().await;
        let tracker = BudgetTracker::new_for_test(pool, cfg_with_local(100.0));
        tracker.inject_usage_for_test(SCOPE_LOCAL_TOTAL, 80.0).await;
        assert_eq!(tracker.degrade_level().await, DegradeLevel::SoftWarn);
        // And anywhere up to (but not including) 95.
        tracker
            .inject_usage_for_test(SCOPE_LOCAL_TOTAL, 14.99)
            .await;
        assert_eq!(tracker.degrade_level().await, DegradeLevel::SoftWarn);
    }

    #[tokio::test]
    async fn test_degrade_hard_limit_at_95() {
        let pool = empty_pool().await;
        let tracker = BudgetTracker::new_for_test(pool, cfg_with_local(100.0));
        tracker.inject_usage_for_test(SCOPE_LOCAL_TOTAL, 95.0).await;
        assert_eq!(tracker.degrade_level().await, DegradeLevel::HardLimit);
    }

    #[tokio::test]
    async fn test_degrade_killswitch_at_100() {
        let pool = empty_pool().await;
        let tracker = BudgetTracker::new_for_test(pool, cfg_with_local(100.0));
        tracker
            .inject_usage_for_test(SCOPE_LOCAL_TOTAL, 100.0)
            .await;
        assert_eq!(tracker.degrade_level().await, DegradeLevel::Killswitch);
        // Zero/negative limit also triggers killswitch (fail-closed).
        let tracker2 = BudgetTracker::new_for_test(empty_pool().await, cfg_with_local(0.0));
        assert_eq!(tracker2.degrade_level().await, DegradeLevel::Killswitch);
    }

    // Test 9: cost_edge_ratio computes used/limit.
    // 測試 9：cost_edge_ratio 計算 used/limit。
    #[tokio::test]
    async fn test_cost_edge_ratio_calc() {
        let pool = empty_pool().await;
        let tracker = BudgetTracker::new_for_test(pool, cfg_with_local(100.0));
        tracker.inject_usage_for_test(SCOPE_LOCAL_TOTAL, 80.0).await;
        let ratio = tracker.cost_edge_ratio().await.unwrap();
        assert!((ratio - 0.8).abs() < 1e-9, "ratio was {ratio}");
        // Zero limit → infinity sentinel
        let tracker2 = BudgetTracker::new_for_test(empty_pool().await, cfg_with_local(0.0));
        assert_eq!(tracker2.cost_edge_ratio().await.unwrap(), f64::INFINITY);
    }

    // Test 10: override_limit hot-reload — config_cache reflects the new limit.
    // 測試 10：override_limit 熱重載 — config_cache 反映新上限。
    #[tokio::test]
    async fn test_config_hot_reload_via_ipc() {
        let pool = empty_pool().await;
        let tracker = BudgetTracker::new_for_test(pool, BudgetConfig::defaults());
        assert_eq!(
            tracker.config_cache.read().await.limit(SCOPE_LOCAL_TOTAL),
            100.0
        );
        tracker.override_limit(SCOPE_LOCAL_TOTAL, 200.0).await;
        assert_eq!(
            tracker.config_cache.read().await.limit(SCOPE_LOCAL_TOTAL),
            200.0
        );
        // status_json reflects the override too.
        let status = tracker.status_json().await;
        assert_eq!(status["config"][SCOPE_LOCAL_TOTAL], 200.0);
    }

    // Bonus test: status_json shape contains all 5 scopes + degrade_level.
    // 額外測試：status_json 形狀含全 5 個 scope + degrade_level。
    #[tokio::test]
    async fn test_status_json_shape() {
        let pool = empty_pool().await;
        let tracker = BudgetTracker::new_for_test(pool, BudgetConfig::defaults());
        let status = tracker.status_json().await;
        for scope in KNOWN_SCOPES {
            assert!(status["config"].get(*scope).is_some(), "missing {scope}");
            assert!(status["usage_mtd"].get(*scope).is_some());
            assert!(status["remaining"].get(*scope).is_some());
        }
        assert_eq!(status["degrade_level"], "none");
    }

    // Bonus: degrade level string labels are stable.
    // 額外：降級字串標籤穩定。
    #[test]
    fn test_degrade_level_labels() {
        assert_eq!(DegradeLevel::None.as_str(), "none");
        assert_eq!(DegradeLevel::SoftWarn.as_str(), "soft_warn");
        assert_eq!(DegradeLevel::HardLimit.as_str(), "hard_limit");
        assert_eq!(DegradeLevel::Killswitch.as_str(), "killswitch");
    }

    // ---------------------------------------------------------------------
    // E5-FN-2 (audit §七 7.2) — request_id dedup tests
    // E5-FN-2（audit §七 7.2）— request_id 去重測試
    // ---------------------------------------------------------------------

    // Test E5-FN-2-A: make_request_id format compliance.
    //   Format: {scope}-{ts_ms}-{rand_hex8}
    //   - starts with the supplied scope
    //   - middle segment is a decimal ms timestamp (>= 1_700_000_000_000 in 2026)
    //   - suffix is 8 lowercase hex chars
    // 測試 E5-FN-2-A：make_request_id 格式正確性。
    #[test]
    fn test_make_request_id_format() {
        let rid = BudgetTracker::make_request_id(SCOPE_AGENT_TEACHER);
        let parts: Vec<&str> = rid.rsplitn(3, '-').collect();
        // rsplitn returns in reverse order: [hex, ts, scope-prefix]
        assert_eq!(parts.len(), 3, "request_id must have 3 hyphen-separated parts, got {rid}");
        let suffix = parts[0];
        let ts_str = parts[1];
        let scope_prefix = parts[2];
        assert_eq!(suffix.len(), 8, "rand hex suffix must be 8 chars, got '{suffix}' in {rid}");
        assert!(
            suffix.chars().all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase()),
            "hex suffix must be lowercase hex, got '{suffix}'",
        );
        let ts_ms: u64 = ts_str.parse().expect("ts_ms must parse as u64");
        assert!(
            ts_ms > 1_700_000_000_000,
            "ts_ms looks bogus ({ts_ms}) — clock skew or wrong segment",
        );
        assert_eq!(
            scope_prefix, SCOPE_AGENT_TEACHER,
            "scope prefix should be {SCOPE_AGENT_TEACHER}, got '{scope_prefix}'",
        );
    }

    // Test E5-FN-2-B: make_request_id collision resistance within the same ms.
    //   Mint 1_000 request_ids back-to-back and confirm they're all distinct.
    //   With an 8-hex random suffix (2^32 space) birthday collisions at n=1000
    //   are ~1.2e-4; we pick 1000 for a deterministically stable test.
    // 測試 E5-FN-2-B：同一毫秒內 1000 次呼叫全部不撞。
    #[test]
    fn test_make_request_id_unique_within_same_ms() {
        use std::collections::HashSet;
        let n = 1_000;
        let mut seen: HashSet<String> = HashSet::with_capacity(n);
        for _ in 0..n {
            let rid = BudgetTracker::make_request_id(SCOPE_AGENT_TEACHER);
            assert!(
                seen.insert(rid.clone()),
                "duplicate request_id {rid} after {} mints — collision risk",
                seen.len(),
            );
        }
        assert_eq!(seen.len(), n);
    }

    // Test E5-FN-2-C: first-insert path is byte-identical to pre-fix behaviour.
    //   With `empty_pool()` the DB write is skipped (pool.is_available() == false)
    //   and record_usage treats the call as a successful first insert → cache is
    //   incremented exactly once. This guards the "zero behaviour change for
    //   first-insert path" invariant required by the task.
    // 測試 E5-FN-2-C：首次寫入路徑與修復前行為 byte-identical（pool 不可用時
    // 視為成功，cache 增量一次）。
    #[tokio::test]
    async fn test_record_usage_first_insert_unchanged() {
        let pool = empty_pool().await;
        let tracker = BudgetTracker::new_for_test(pool, BudgetConfig::defaults());
        let cost = tracker
            .record_usage(
                SCOPE_AGENT_TEACHER,
                "anthropic",
                "claude-sonnet-4-5",
                1_000,
                500,
                "directive_generation",
                "e5fn2-first-call",
            )
            .await
            .expect("record_usage should succeed");
        assert!(cost > 0.0);
        // Cache should reflect exactly one charge.
        let teacher_used = tracker
            .usage_cache
            .read()
            .await
            .mtd_usd
            .get(SCOPE_AGENT_TEACHER)
            .copied()
            .unwrap_or(0.0);
        assert!(
            (teacher_used - cost).abs() < 1e-9,
            "expected cache == cost ({cost}), got {teacher_used}",
        );
    }

    // Test E5-FN-2-D: insert_usage returns `Ok(true)` semantics preserved when
    //   the pool is unavailable — this exercises the record_usage branch that
    //   synthesises `inserted = true` for cold-start / test mode so the cache
    //   accumulator still runs (no regression to offline behaviour).
    // 測試 E5-FN-2-D：pool 不可用時 record_usage 仍會增量，避免離線場景退化。
    #[tokio::test]
    async fn test_record_usage_cold_start_still_increments_cache() {
        let pool = empty_pool().await;
        let tracker = BudgetTracker::new_for_test(pool, BudgetConfig::defaults());
        // Three calls — different request_ids — should all accumulate.
        // 三次呼叫、不同 request_id，應全部累加。
        for i in 0..3 {
            tracker
                .record_usage(
                    SCOPE_AGENT_ANALYST,
                    "anthropic",
                    "claude-sonnet-4-5",
                    100,
                    50,
                    "cold_start_test",
                    &format!("e5fn2-cold-{i}"),
                )
                .await
                .expect("record_usage should succeed");
        }
        let analyst_used = tracker
            .usage_cache
            .read()
            .await
            .mtd_usd
            .get(SCOPE_AGENT_ANALYST)
            .copied()
            .unwrap_or(0.0);
        // Each call: 100 * 3/1e6 + 50 * 15/1e6 = 0.0003 + 0.00075 = 0.00105.
        // 每次呼叫成本 0.00105 USD；×3 應累加到 0.00315。
        let expected = 3.0 * 0.00105;
        assert!(
            (analyst_used - expected).abs() < 1e-9,
            "expected {expected}, got {analyst_used}",
        );
    }

    // Test E5-FN-2-E: the legacy literal "py-sync" default is no longer used
    //   inside the IPC handler, so two distinct Layer2 calls that both OMIT
    //   request_id must mint distinct request_ids (not a literal "py-sync"
    //   collision that the V018 index would dedup into silent loss).
    //   We exercise the same minting path the IPC handler uses.
    // 測試 E5-FN-2-E：IPC handler 對缺失 request_id 的處理必須每次鑄造唯一值，
    // 不再用字面量 "py-sync" 互撞（否則 V018 索引會把第二筆起全部吃掉）。
    #[test]
    fn test_layer2_default_request_id_is_unique_not_literal() {
        let rid_a = BudgetTracker::make_request_id(SCOPE_AGENT_RESERVE);
        let rid_b = BudgetTracker::make_request_id(SCOPE_AGENT_RESERVE);
        assert_ne!(rid_a, rid_b, "two mints must be distinct");
        assert!(
            !rid_a.contains("py-sync") && !rid_b.contains("py-sync"),
            "must not contain the old literal 'py-sync' sentinel",
        );
        // Both must parse as `{scope}-{ts_ms}-{rand_hex8}`.
        for rid in [&rid_a, &rid_b] {
            assert!(
                rid.starts_with(&format!("{SCOPE_AGENT_RESERVE}-")),
                "rid {rid} should start with scope prefix",
            );
        }
    }
}
