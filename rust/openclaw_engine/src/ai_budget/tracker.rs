//! BudgetTracker — core AI budget enforcement state.
//! BudgetTracker — AI 預算強制執行核心狀態。
//!
//! MODULE_NOTE (EN): Hot-reloadable BudgetConfig (5 scopes), atomic refresh stamp,
//!   per-scope month-to-date USD usage cache. Config reads use ArcSwap because
//!   the config is read-heavy and hot-reload writes replace the whole snapshot.
//!   Usage remains under an async RwLock because recording usage mutates per-scope
//!   counters. Three-stage degradation thresholds are computed against the
//!   `local_total` scope (the operator-controlled monthly budget). Pricing is a
//!   placeholder const map keyed by model id (4-17 will replace with PG table).
//! MODULE_NOTE (中): 可熱重載的 BudgetConfig（5 個 scope）、原子刷新時間戳、
//!   per-scope 月內已用 USD 快取。Config 讀取使用 ArcSwap，因為配置讀多寫少、
//!   熱重載以整體快照替換；usage 仍保留 async RwLock，因為記帳會累加 per-scope
//!   counter。三段降級閾值以 `local_total` scope 為基準（operator 可調月度預算）。
//!   定價為以 model id 為鍵的占位 const map（4-17 會改用 PG 表）。

use crate::config::{BudgetConfig as TomlBudgetConfig, ConfigStore};
use crate::database::pool::DbPool;
use arc_swap::ArcSwap;
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
    /// DOC-08 §4 每日腿：per-scope 當前 UTC 日已用（美元）。
    /// 冷審計 R2 latent 修復——daily_usd_max 此前在 Rust 端零 runtime 消費者。
    daily_usd: HashMap<String, f64>,
    /// daily_usd 對應的 UTC epoch-day；不等於「今日」時整窗清零重計。
    daily_utc_day: i64,
    /// Wall-clock millis when this snapshot was last refreshed from DB.
    /// 從 DB 上次刷新此快照的牆鐘毫秒。
    refreshed_at_ms: u64,
}

/// 把牆鐘毫秒換算為 UTC epoch-day（與 usage_io::load_daily_usage 的 UTC 日窗對齊）。
fn utc_day_from_ms(ms: i64) -> i64 {
    ms.div_euclid(86_400_000)
}

/// AI budget tracker — fail-closed enforcement of the $100/$150 ceilings.
/// AI 預算追蹤器 — fail-closed 強制 $100/$150 上限。
pub struct BudgetTracker {
    /// PG pool wrapper. None means DB-disabled mode (tests/cold start).
    /// PG 連接池包裝。None 表示 DB 禁用模式（測試/冷啟動）。
    pool: Arc<DbPool>,
    /// Hot-reloadable config snapshot.
    /// 可熱重載的配置快照。
    config_cache: Arc<ArcSwap<BudgetConfig>>,
    /// Month-to-date usage snapshot.
    /// 月內已用快照。
    usage_cache: Arc<RwLock<UsageCache>>,
    /// Pricing table loaded from settings/ai_pricing.yaml at boot (4-17).
    /// 啟動時從 settings/ai_pricing.yaml 載入的定價表（4-17）。
    pricing: Arc<PricingTable>,
    /// TOML BudgetConfig 熱重載 store —— DOC-08 §4 `caps.daily_usd_max` 的唯一來源。
    /// production 由 tasks::init_budget_and_audit 注入 Some；None 僅限測試/降級構造，
    /// 此時取 struct default 值（見 daily_usd_max()）。
    toml_budget: Option<Arc<ConfigStore<TomlBudgetConfig>>>,
    /// Last config refresh wall-clock millis (atomic for lock-free reads).
    /// 上次配置刷新的牆鐘毫秒（原子，便於無鎖讀取）。
    last_config_refresh_ms: AtomicU64,
}

impl BudgetTracker {
    /// Build a new BudgetTracker; loads config + MTD/daily usage from PG if pool is up.
    /// Falls back to in-memory defaults when PG is unavailable (cold start safe).
    /// `toml_budget`：TOML BudgetConfig 熱重載 store（DOC-08 §4 daily_usd_max 來源）；
    /// production 必須傳 Some。
    /// 構建新 BudgetTracker；若 pool 可用則從 PG 載入 config + MTD/每日用量。
    /// PG 不可用時回退到內存預設（冷啟動安全）。
    pub async fn new(
        pool: Arc<DbPool>,
        toml_budget: Option<Arc<ConfigStore<TomlBudgetConfig>>>,
    ) -> Result<Self, String> {
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

        let today_utc_day = utc_day_from_ms(now_ms() as i64);
        let usage = if pool.is_available() {
            let mtd_usd = match usage_io::load_mtd_usage(&pool).await {
                Ok(map) => map,
                Err(e) => {
                    warn!(error = %e, "BudgetTracker: MTD usage load failed, starting at zero / MTD 用量載入失敗，從零開始");
                    HashMap::new()
                }
            };
            // DOC-08 §4：每日窗載入失敗時鏡像 MTD 既有語義（從零開始 + warn）。
            let daily_usd = match usage_io::load_daily_usage(&pool).await {
                Ok(map) => map,
                Err(e) => {
                    warn!(error = %e, "BudgetTracker: daily usage load failed, starting at zero / 每日用量載入失敗，從零開始");
                    HashMap::new()
                }
            };
            UsageCache {
                mtd_usd,
                daily_usd,
                daily_utc_day: today_utc_day,
                refreshed_at_ms: now_ms(),
            }
        } else {
            UsageCache {
                mtd_usd: HashMap::new(),
                daily_usd: HashMap::new(),
                daily_utc_day: today_utc_day,
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
            config_cache: Arc::new(ArcSwap::from_pointee(config)),
            usage_cache: Arc::new(RwLock::new(usage)),
            pricing,
            toml_budget,
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
            config_cache: Arc::new(ArcSwap::from_pointee(config)),
            usage_cache: Arc::new(RwLock::new(UsageCache {
                daily_utc_day: utc_day_from_ms(now_ms() as i64),
                ..UsageCache::default()
            })),
            pricing,
            toml_budget: None,
            last_config_refresh_ms: AtomicU64::new(now_ms()),
        }
    }

    /// 測試專用：注入帶指定 daily_usd_max 的 TOML BudgetConfig store，
    /// 讓 daily gate 測試不觸碰檔案系統與 env。
    #[cfg(test)]
    pub fn with_daily_cap_for_test(mut self, daily_usd_max: f64) -> Self {
        let mut cfg = TomlBudgetConfig::default();
        cfg.caps.daily_usd_max = daily_usd_max;
        self.toml_budget = Some(Arc::new(ConfigStore::new(cfg)));
        self
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
        self.config_cache.store(Arc::new(cfg));
        self.last_config_refresh_ms
            .store(now_ms(), Ordering::Relaxed);
        debug!("BudgetTracker config refreshed / 配置已重載");
        Ok(())
    }

    /// Reload MTD + daily usage from PG (called periodically or on-demand).
    /// 從 PG 重載月內已用 + 每日已用（定期或按需）。
    pub async fn refresh_usage(&self) -> Result<(), String> {
        if !self.pool.is_available() {
            return Ok(());
        }
        let map = usage_io::load_mtd_usage(&self.pool).await?;
        let daily = usage_io::load_daily_usage(&self.pool).await?;
        let mut guard = self.usage_cache.write().await;
        guard.mtd_usd = map;
        guard.daily_usd = daily;
        guard.daily_utc_day = utc_day_from_ms(now_ms() as i64);
        guard.refreshed_at_ms = now_ms();
        Ok(())
    }

    /// Record an LLM usage event. **Fail-closed**: returns Err on DB write failure
    /// (or unknown model pricing) — caller MUST refuse to forward the LLM call.
    /// On success, returns the computed USD cost and updates the in-memory cache.
    ///
    /// E5-FN-2 Plan N: callers provide a deterministic `(event_time_ms, request_id)`
    /// tuple (via [`make_request_id`]). A retry with the same tuple collapses at
    /// the hypertable PK `(time, scope, request_id)` and returns without bumping
    /// the MTD cache — preventing double-billing without any schema change.
    ///
    /// 記錄一次 LLM 用量事件。**Fail-closed**：DB 寫入失敗（或模型定價未知）
    /// 時返回 Err — caller 必須拒絕該次 LLM 調用。成功時返回計算出的美元成本
    /// 並更新內存快取。
    ///
    /// E5-FN-2 Plan N：caller 透過 [`make_request_id`] 傳入確定性
    /// `(event_time_ms, request_id)` tuple。同 tuple 重試會在 hypertable PK
    /// `(time, scope, request_id)` 合併，回傳時不累進 MTD 快取 — 零 schema
    /// 改動即達成防重複計費。
    #[allow(clippy::too_many_arguments)]
    pub async fn record_usage(
        &self,
        scope: &str,
        provider: &str,
        model: &str,
        tokens_in: u32,
        tokens_out: u32,
        purpose: &str,
        request_id: &str,
        event_time_ms: i64,
    ) -> Result<f64, String> {
        // 1) Pricing — fail-closed on unknown / inactive model (4-17 PricingTable).
        //    定價 — 未知或 inactive 模型 fail-closed（4-17 PricingTable）。
        let cost_usd = self.compute_cost_usd(model, tokens_in, tokens_out)?;

        // 2) DB write — fail-closed: any error propagates to caller.
        //    Returns `inserted=true` on fresh row, `false` on PK conflict (dedup).
        //    DB 寫入 — fail-closed：任何錯誤上拋給 caller。
        //    `inserted=true` 為新列，`false` 代表 PK 衝突（去重）。
        let inserted = if self.pool.is_available() {
            usage_io::insert_usage(
                &self.pool,
                event_time_ms,
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
            // Cold-start / tests: no DB → always treat as fresh insert so cache
            // reflects the spend as before.
            // 冷啟動/測試：無 DB → 視為新插入，快取照常累計。
            true
        };

        // 3) Update in-memory MTD cache only on fresh insert; skip on dedup so
        //    the retry doesn't double-bill the operator.
        //    僅在新插入時累進內存 MTD 快取；去重路徑跳過，避免重試雙重計費。
        if inserted {
            let today = utc_day_from_ms(now_ms() as i64);
            let mut guard = self.usage_cache.write().await;
            *guard.mtd_usd.entry(scope.to_string()).or_insert(0.0) += cost_usd;
            if scope != SCOPE_LOCAL_TOTAL {
                *guard
                    .mtd_usd
                    .entry(SCOPE_LOCAL_TOTAL.to_string())
                    .or_insert(0.0) += cost_usd;
            }
            // DOC-08 §4 每日腿：先翻日窗再累進；重試「舊日 tuple」（event_time_ms
            // 不在今日窗）不污染今日累計，與 hypertable PK 去重語義一致。
            Self::roll_daily_window(&mut guard, today);
            if utc_day_from_ms(event_time_ms) == today {
                *guard.daily_usd.entry(scope.to_string()).or_insert(0.0) += cost_usd;
                if scope != SCOPE_LOCAL_TOTAL {
                    *guard
                        .daily_usd
                        .entry(SCOPE_LOCAL_TOTAL.to_string())
                        .or_insert(0.0) += cost_usd;
                }
            }
        } else {
            debug!(
                scope,
                request_id, "record_usage: duplicate (PK dedup) — cache not bumped"
            );
        }

        Ok(cost_usd)
    }

    /// 日界翻轉：cache 標記日 != 今日 → 清空 daily 累計並改標今日。
    /// 為什麼可以直接清零：本引擎是 `learning.ai_usage_log` 唯一寫入者，翻轉
    /// 瞬間「今日」尚無任何已記帳開銷；重啟（new）與定期 refresh_usage 會從 DB
    /// 重載校正殘餘漂移。
    fn roll_daily_window(cache: &mut UsageCache, today_utc_day: i64) {
        if cache.daily_utc_day != today_utc_day {
            cache.daily_usd.clear();
            cache.daily_utc_day = today_utc_day;
        }
    }

    /// DOC-08 §4 每日硬上限值（來源：TOML BudgetConfig `caps.daily_usd_max`，
    /// 熱重載即時生效）。0 = 不設限（沿用 BudgetCaps 既有欄位契約，不在此重定義）。
    /// 無 store（測試/降級構造）→ 取 struct default；production 由 tasks 注入真實 store。
    fn daily_usd_max(&self) -> f64 {
        match &self.toml_budget {
            Some(store) => store.load().caps.daily_usd_max,
            None => TomlBudgetConfig::default().caps.daily_usd_max,
        }
    }

    /// DOC-08 §4 每日上限 gate：回傳 `Some(拒絕理由)` 代表新的付費 AI 調用必須被拒。
    ///
    /// 為什麼 fail-closed：DOC-08 §4 規定每日 $2.00 硬上限；缺這條腿時 teacher
    /// kill-switch 一開，單日可燒到月度 cap 而不觸任何 daily 邊界（冷審計 R2
    /// latent finding）。本 gate 只攔 AI 調用，不攔任何交易路徑
    /// （caller = claude_teacher pre-call gate）。
    pub async fn daily_cap_rejection(&self) -> Option<String> {
        let cap = self.daily_usd_max();
        if cap <= 0.0 {
            return None; // 0 = uncapped（BudgetCaps 既有契約）
        }
        let today = utc_day_from_ms(now_ms() as i64);
        let mut guard = self.usage_cache.write().await;
        Self::roll_daily_window(&mut guard, today);
        let used = guard
            .daily_usd
            .get(SCOPE_LOCAL_TOTAL)
            .copied()
            .unwrap_or(0.0);
        if used >= cap {
            Some(format!(
                "daily AI spend cap reached: used={used:.4} USD >= daily_usd_max={cap:.4} USD \
                 (DOC-08 §4); denying new paid AI calls until UTC day rollover / 每日 AI 開銷已達 \
                 daily_usd_max，拒絕新的付費 AI 調用直到 UTC 日界翻轉"
            ))
        } else {
            None
        }
    }

    /// Remaining USD for a scope this month (limit − MTD usage; clamped at 0).
    /// 該 scope 本月剩餘美元（上限 − 月內已用，下限 0）。
    pub async fn get_remaining(&self, scope: &str) -> Result<f64, String> {
        let cfg = self.config_cache.load_full();
        let usage = self.usage_cache.read().await;
        let limit = cfg.limit(scope);
        let used = usage.mtd_usd.get(scope).copied().unwrap_or(0.0);
        Ok((limit - used).max(0.0))
    }

    /// Current degrade level (driven by `local_total` MTD spend).
    /// 當前降級等級（由 `local_total` 月內開銷驅動）。
    pub async fn degrade_level(&self) -> DegradeLevel {
        let cfg = self.config_cache.load_full();
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
        let cfg = self.config_cache.load_full();
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
        let cfg = self.config_cache.load_full();
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
        // DOC-08 §4 每日腿觀測欄位（additive，不改既有 key）。
        let daily_used = usage
            .daily_usd
            .get(SCOPE_LOCAL_TOTAL)
            .copied()
            .unwrap_or(0.0);
        serde_json::json!({
            "config": config_obj,
            "usage_mtd": usage_obj,
            "remaining": remaining_obj,
            "degrade_level": level.as_str(),
            "daily": {
                "used_local_total": daily_used,
                "daily_usd_max": self.daily_usd_max(),
                "utc_day": usage.daily_utc_day,
            },
            "last_refresh_ms": usage.refreshed_at_ms,
        })
    }

    /// Apply an in-memory config override (used by IPC `update_ai_budget_config`
    /// after the DB write succeeds, so callers see the new limit immediately).
    /// 套用內存配置覆寫（IPC `update_ai_budget_config` 寫 DB 成功後使用，
    /// 讓 caller 立即看到新上限）。
    pub async fn override_limit(&self, scope: &str, monthly_usd: f64) {
        let mut cfg = (*self.config_cache.load_full()).clone();
        cfg.limits.insert(scope.to_string(), monthly_usd);
        self.config_cache.store(Arc::new(cfg));
        self.last_config_refresh_ms
            .store(now_ms(), Ordering::Relaxed);
    }

    /// Test-only: directly inject MTD + daily usage to bypass DB.
    /// 測試專用：直接注入 MTD + 每日用量繞過 DB（鏡像 record_usage 的雙窗累進）。
    #[cfg(test)]
    pub async fn inject_usage_for_test(&self, scope: &str, usd: f64) {
        let today = utc_day_from_ms(now_ms() as i64);
        let mut guard = self.usage_cache.write().await;
        *guard.mtd_usd.entry(scope.to_string()).or_insert(0.0) += usd;
        Self::roll_daily_window(&mut guard, today);
        *guard.daily_usd.entry(scope.to_string()).or_insert(0.0) += usd;
    }
}

// S-04: use shared now_ms() from openclaw_core instead of local copy.
// S-04：使用 openclaw_core 的共用 now_ms() 取代本地副本。
use openclaw_core::now_ms;

// ---------------------------------------------------------------------------
// E5-FN-2 Plan N: deterministic (request_id, event_time_ms) minting.
// E5-FN-2 Plan N：確定性 (request_id, event_time_ms) 鑄造。
// ---------------------------------------------------------------------------

/// Mint a request_id + event_time_ms tuple for [`BudgetTracker::record_usage`].
///
/// Format: `{scope}-{ts_ms}-{rand_hex8}`. Both values must be **captured once**
/// and reused verbatim across any retries so the hypertable PK
/// `(time, scope, request_id)` collapses duplicates. Re-minting on retry
/// defeats the dedup (fresh tuple → fresh PK → double-bill).
///
/// 為 [`BudgetTracker::record_usage`] 鑄造 request_id + event_time_ms tuple。
///
/// 格式：`{scope}-{ts_ms}-{rand_hex8}`。兩個值都必須**捕獲一次**並原樣
/// 傳回重試，hypertable PK `(time, scope, request_id)` 才能折疊重複。
/// 重試時重鑄 tuple 會破壞去重（新 tuple → 新 PK → 雙重計費）。
pub fn make_request_id(scope: &str) -> (String, i64) {
    make_request_id_with_rng(scope, &mut rand::thread_rng())
}

/// E5-FN-2-PLAN-N-FUP (b): Testable variant with caller-supplied RNG so tests
/// can seed a deterministic RNG and avoid the ~1/2^32 per-invocation collision
/// flake in `test_make_request_id_unique_within_same_ms`. Production code path
/// `make_request_id()` above forwards `rand::thread_rng()`; no behavior change.
/// E5-FN-2-PLAN-N-FUP (b)：測試友好變體，接收 caller 提供的 RNG，讓 test 可
/// 用 seeded RNG 消除 `test_make_request_id_unique_within_same_ms` 每次
/// ~1/2^32 碰撞 flake。生產路徑 `make_request_id()` 仍走 `thread_rng()` 無行為改動。
pub(crate) fn make_request_id_with_rng<R: rand::RngCore>(
    scope: &str,
    rng: &mut R,
) -> (String, i64) {
    let ts_ms = now_ms() as i64;
    let mut bytes = [0u8; 4];
    rng.fill_bytes(&mut bytes);
    let rand_hex = format!(
        "{:02x}{:02x}{:02x}{:02x}",
        bytes[0], bytes[1], bytes[2], bytes[3]
    );
    (format!("{scope}-{ts_ms}-{rand_hex}"), ts_ms)
}

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
        // 持共用鎖與所有 env-mutating lib test 串行：set_test_pricing_path() 內
        // 對 OPENCLAW_PRICING_PATH 做 process-global set_var。guard 必須在呼叫端
        // （而非 helper 內）取得，否則會在 helper return 時即釋放，無法覆蓋此處
        // 對該 env 的後續讀取臨界區。雖與 Group A env var disjoint，仍持同一把
        // 鎖以維持 lib「所有 mutate process env 的 test 都持 guard」不變式乾淨。
        let _g = crate::test_env_lock::guard();
        set_test_pricing_path();
        let pool = empty_pool().await;
        let tracker = BudgetTracker::new(pool, None).await.unwrap();
        let cfg = tracker.config_cache.load_full();
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
                1_700_000_000_000,
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
        assert_eq!(tracker.config_cache.load().limit(SCOPE_LOCAL_TOTAL), 100.0);
        tracker.override_limit(SCOPE_LOCAL_TOTAL, 200.0).await;
        assert_eq!(tracker.config_cache.load().limit(SCOPE_LOCAL_TOTAL), 200.0);
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

    // --- DOC-08 §4 daily_usd_max enforcement tests / 每日硬上限測試 ---

    // 每日窗已用 >= cap → 拒絕新的付費 AI 調用。
    #[tokio::test]
    async fn test_daily_cap_rejection_blocks_at_cap() {
        let pool = empty_pool().await;
        let tracker = BudgetTracker::new_for_test(pool, BudgetConfig::defaults())
            .with_daily_cap_for_test(2.0);
        tracker.inject_usage_for_test(SCOPE_LOCAL_TOTAL, 2.0).await;
        let rejection = tracker.daily_cap_rejection().await;
        assert!(
            rejection.is_some(),
            "daily spend at cap must be rejected (fail-closed)"
        );
        assert!(rejection.unwrap().contains("daily_usd_max"));
    }

    // 每日窗低於 cap → 放行。
    #[tokio::test]
    async fn test_daily_cap_below_cap_allows() {
        let pool = empty_pool().await;
        let tracker = BudgetTracker::new_for_test(pool, BudgetConfig::defaults())
            .with_daily_cap_for_test(2.0);
        tracker.inject_usage_for_test(SCOPE_LOCAL_TOTAL, 1.99).await;
        assert!(tracker.daily_cap_rejection().await.is_none());
    }

    // cap = 0 → 不設限（BudgetCaps 既有欄位契約）。
    #[tokio::test]
    async fn test_daily_cap_zero_uncapped() {
        let pool = empty_pool().await;
        let tracker = BudgetTracker::new_for_test(pool, BudgetConfig::defaults())
            .with_daily_cap_for_test(0.0);
        tracker
            .inject_usage_for_test(SCOPE_LOCAL_TOTAL, 10_000.0)
            .await;
        assert!(tracker.daily_cap_rejection().await.is_none());
    }

    // 日界翻轉：昨日窗滿額，翻日後 gate 必須放行（清零重計）。
    #[tokio::test]
    async fn test_daily_window_roll_clears_spend() {
        let pool = empty_pool().await;
        let tracker = BudgetTracker::new_for_test(pool, BudgetConfig::defaults())
            .with_daily_cap_for_test(2.0);
        tracker.inject_usage_for_test(SCOPE_LOCAL_TOTAL, 5.0).await;
        assert!(tracker.daily_cap_rejection().await.is_some());
        // 把窗標記改為「昨天」模擬跨日；下一次讀取應翻窗清零。
        {
            let mut guard = tracker.usage_cache.write().await;
            guard.daily_utc_day -= 1;
        }
        assert!(
            tracker.daily_cap_rejection().await.is_none(),
            "day rollover must clear the daily window"
        );
        let guard = tracker.usage_cache.read().await;
        assert!(guard.daily_usd.is_empty(), "daily map must be cleared");
        // 月度窗不受日界翻轉影響。
        assert!((guard.mtd_usd.get(SCOPE_LOCAL_TOTAL).copied().unwrap() - 5.0).abs() < 1e-9);
    }

    // record_usage 同步累進每日窗（scope + local_total 鏡像月度語義）；
    // status_json 暴露 daily 觀測欄位。
    #[tokio::test]
    async fn test_record_usage_bumps_daily_and_status_json() {
        let pool = empty_pool().await;
        let tracker = BudgetTracker::new_for_test(pool, BudgetConfig::defaults())
            .with_daily_cap_for_test(2.0);
        let (rid, ts) = make_request_id(SCOPE_AGENT_TEACHER);
        let cost = tracker
            .record_usage(
                SCOPE_AGENT_TEACHER,
                "anthropic",
                "claude-sonnet-4-5",
                1_000,
                500,
                "unit_test",
                &rid,
                ts,
            )
            .await
            .expect("record_usage OK");
        let guard = tracker.usage_cache.read().await;
        let teacher_daily = guard.daily_usd.get(SCOPE_AGENT_TEACHER).copied().unwrap();
        let local_daily = guard.daily_usd.get(SCOPE_LOCAL_TOTAL).copied().unwrap();
        assert!((teacher_daily - cost).abs() < 1e-9);
        assert!((local_daily - cost).abs() < 1e-9);
        drop(guard);
        let status = tracker.status_json().await;
        assert!((status["daily"]["used_local_total"].as_f64().unwrap() - cost).abs() < 1e-9);
        assert_eq!(status["daily"]["daily_usd_max"], 2.0);
    }

    // --- E5-FN-2 Plan N tests / E5-FN-2 Plan N 測試 ---

    // Plan N-1: make_request_id format — `{scope}-{ts_ms}-{hex8}`.
    // Plan N-1：make_request_id 格式。
    #[test]
    fn test_make_request_id_format() {
        let (rid, ts) = make_request_id("teacher");
        let parts: Vec<&str> = rid.splitn(3, '-').collect();
        assert_eq!(
            parts.len(),
            3,
            "request_id must have 3 hyphen-delimited parts: {rid}"
        );
        assert_eq!(parts[0], "teacher");
        assert_eq!(
            parts[1].parse::<i64>().unwrap(),
            ts,
            "ts in id must match returned ts"
        );
        assert_eq!(parts[2].len(), 8, "hex suffix must be 8 chars: {rid}");
        assert!(
            parts[2].chars().all(|c| c.is_ascii_hexdigit()),
            "hex suffix must be all hex: {rid}"
        );
        assert!(
            ts > 1_700_000_000_000,
            "ts_ms must look like a real epoch ms"
        );
    }

    // Plan N-2: two mints within the same ms get distinct request_ids thanks to
    // the random hex suffix (no PK collision on fast retries).
    // E5-FN-2-PLAN-N-FUP (b, 2026-04-23): swap `thread_rng()` for seeded
    // StdRng so this test is deterministic. Prior impl had ~1/2^32 per-run
    // flake probability — CI running 1000× daily would see a hit every
    // ~11 years on average, but operator-reported CI noise prompted this
    // defensive seed (zero cost, same collision-free semantic guarantee).
    // Plan N-2：同 ms 內兩次鑄造必得不同 request_id（隨機 hex 後綴，快速重試
    // 不會 PK 碰撞）。E5-FN-2-PLAN-N-FUP (b)：改用 seeded StdRng 取代
    // `thread_rng()`，消除 ~1/2^32 per-run flake；零成本、同等語意保證。
    #[test]
    fn test_make_request_id_unique_within_same_ms() {
        use rand::SeedableRng;
        let mut rng = rand::rngs::StdRng::seed_from_u64(0xDEADBEEFu64);
        let (rid_a, _) = make_request_id_with_rng("layer2", &mut rng);
        let (rid_b, _) = make_request_id_with_rng("layer2", &mut rng);
        assert_ne!(
            rid_a, rid_b,
            "two fresh mints with same seeded RNG must differ \
             (seeded StdRng never emits two identical 32-bit draws in a row \
             at this seed — deterministic, no flake)"
        );
    }

    // Plan N-3: record_usage accepts event_time_ms and the cache still bumps
    // on the first call (cold-start / no-pool path treats every call as fresh).
    // Plan N-3：record_usage 接受 event_time_ms，首次調用快取照常累進
    // （冷啟動/無 pool 路徑視每次為新插入）。
    #[tokio::test]
    async fn test_record_usage_cold_start_still_increments_cache() {
        let pool = empty_pool().await;
        let tracker = BudgetTracker::new_for_test(pool, BudgetConfig::defaults());
        let (rid, ts) = make_request_id(SCOPE_AGENT_TEACHER);
        let cost = tracker
            .record_usage(
                SCOPE_AGENT_TEACHER,
                "anthropic",
                "claude-sonnet-4-5",
                100,
                50,
                "unit_test",
                &rid,
                ts,
            )
            .await
            .expect("record_usage OK");
        assert!(cost > 0.0);
        let used = tracker
            .usage_cache
            .read()
            .await
            .mtd_usd
            .get(SCOPE_AGENT_TEACHER)
            .copied()
            .unwrap_or(0.0);
        assert!((used - cost).abs() < 1e-9);
    }

    // Plan N-4: distinct (rid, ts) tuples accumulate as separate rows
    // (cold-start path ⇒ always "inserted=true").
    // Plan N-4：不同 (rid, ts) tuple 分別累進（冷啟動路徑 ⇒ 皆 inserted=true）。
    #[tokio::test]
    async fn test_record_usage_distinct_tuples_accumulate() {
        let pool = empty_pool().await;
        let tracker = BudgetTracker::new_for_test(pool, BudgetConfig::defaults());
        for _ in 0..3 {
            let (rid, ts) = make_request_id(SCOPE_AGENT_TEACHER);
            tracker
                .record_usage(
                    SCOPE_AGENT_TEACHER,
                    "anthropic",
                    "claude-sonnet-4-5",
                    100,
                    50,
                    "unit_test",
                    &rid,
                    ts,
                )
                .await
                .expect("record_usage OK");
        }
        let used = tracker
            .usage_cache
            .read()
            .await
            .mtd_usd
            .get(SCOPE_AGENT_TEACHER)
            .copied()
            .unwrap_or(0.0);
        // 3 fresh inserts × $0.00425 per call (100in×3/1e6 + 50out×15/1e6)
        let per_call = 100.0 * 3.0 / 1e6 + 50.0 * 15.0 / 1e6;
        assert!((used - per_call * 3.0).abs() < 1e-9, "used={used}");
    }
}
