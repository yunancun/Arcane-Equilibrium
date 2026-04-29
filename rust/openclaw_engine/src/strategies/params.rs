//! Strategy parameter schema glue — `ParamRange`, `StrategyParamsConfig`,
//! `StrategyParams` trait, and the TOML loader entry point.
//! 策略參數 schema 黏合層 — `ParamRange`、`StrategyParamsConfig`、
//! `StrategyParams` trait、以及 TOML 載入器入口。
//!
//! MODULE_NOTE (EN): Thin parent of `strategy_params.rs`. Owns only the shared
//!   bits: `ParamRange` descriptor, `StrategyParamsConfig` aggregate (one field per
//!   strategy), the `StrategyParams` trait, and `load_strategy_params[_from]()`
//!   TOML loader. The 5 per-strategy `*Params` structs live in
//!   `strategy_params.rs` and are re-exported here so `crate::strategies::*`
//!   paths are unchanged. Split from `mod.rs` (cluster C4c) to satisfy §九
//!   1200-line hard cap + 800-line soft warn.
//! MODULE_NOTE (中): `strategy_params.rs` 的精簡父層，只持有共用部分：`ParamRange`
//!   描述符、`StrategyParamsConfig` 聚合結構（每策略一 field）、`StrategyParams`
//!   trait、以及 `load_strategy_params[_from]()` TOML 載入器。5 個策略的
//!   `*Params` 結構放在 `strategy_params.rs`，此處 re-export 以保持
//!   `crate::strategies::*` 路徑不變。從 `mod.rs` 切出（cluster C4c），符合 §九
//!   1200 行硬上限與 800 行軟警告。

use crate::tick_pipeline::PipelineKind;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use tracing::{info, warn};

// Re-export per-strategy structs so `crate::strategies::MaCrossoverParams` etc.
// and `crate::strategies::params::MaCrossoverParams` both resolve.
// 重新導出各策略結構，保持 `crate::strategies::MaCrossoverParams` 等與
// `crate::strategies::params::MaCrossoverParams` 兩條路徑皆可用。
pub use super::strategy_params::{
    BbBreakoutParams, BbReversionParams, FundingArbParams, GridTradingParams, MaCrossoverParams,
};

// Factory fallback helpers used by `registry.rs` when TOML-supplied OI fields
// fail the mirror validator. Routed through `params::` to match the historic
// symbol path pre-C4c split.
// 工廠 fallback helper（當 TOML 提供的 OI 欄位驗證失敗時使用於 `registry.rs`），
// 透過 `params::` 路徑暴露以符合 C4c 拆分前的歷史 symbol 位置。
pub(super) use super::strategy_params::{
    default_bbb_oi_buffer_window_ms, default_bbb_oi_confluence_bonus,
};

// ═══════════════════════════════════════════════════════════════════════════════
// RC-08: StrategyParams trait — interface for DB persistence and Agent tuning.
// RC-08：策略參數 trait — 數據庫持久化和 Agent 調參的接口。
// ═══════════════════════════════════════════════════════════════════════════════

/// Parameter range descriptor for Optuna/Agent tuning (Phase 3b).
/// 參數範圍描述符，供 Optuna/Agent 調參使用（Phase 3b）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParamRange {
    /// Parameter name / 參數名稱
    pub name: String,
    /// Minimum value / 最小值
    pub min: f64,
    /// Maximum value / 最大值
    pub max: f64,
    /// Step size for grid search (None = continuous) / 網格搜索步長（None = 連續）
    pub step: Option<f64>,
    /// Can the Agent adjust this parameter at runtime?
    /// Agent 是否可以在運行時調整此參數？
    pub agent_adjustable: bool,
    /// Should this parameter be persisted to DB?
    /// 此參數是否應持久化到數據庫？
    pub db_persisted: bool,
}

// ═══════════════════════════════════════════════════════════════════════════════
// BLOCKER-8: Per-engine strategy parameter config (TOML-backed).
// BLOCKER-8：每引擎策略參數配置（TOML 支持）。
// ═══════════════════════════════════════════════════════════════════════════════

/// Per-strategy parameter sections loaded from `strategy_params_{paper,demo,live}.toml`.
/// 從 `strategy_params_{paper,demo,live}.toml` 加載的各策略參數段。
#[derive(Debug, Clone, Deserialize, Serialize, Default)]
pub struct StrategyParamsConfig {
    #[serde(default)]
    pub ma_crossover: MaCrossoverParams,
    #[serde(default)]
    pub bb_reversion: BbReversionParams,
    #[serde(default)]
    pub bb_breakout: BbBreakoutParams,
    #[serde(default)]
    pub grid_trading: GridTradingParams,
    #[serde(default)]
    pub funding_arb: FundingArbParams,
}

/// Resolve settings directory: `OPENCLAW_BASE_DIR/settings` or `./settings`.
/// 解析設定目錄：`OPENCLAW_BASE_DIR/settings` 或 `./settings`。
fn settings_dir() -> PathBuf {
    std::env::var("OPENCLAW_BASE_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("."))
        .join("settings")
}

/// Load per-engine strategy parameters from TOML.
/// Paper keeps default fallback (exploration fail-open). Demo/Live fail closed
/// to an all-inactive config when file is missing or unparseable.
/// 從 TOML 加載每引擎策略參數。Paper 保留默認回退（探索 fail-open）；
/// Demo/Live 在文件缺失或解析失敗時改為 all-inactive fail-closed。
pub fn load_strategy_params(kind: PipelineKind) -> StrategyParamsConfig {
    load_strategy_params_from(kind, &settings_dir())
}

/// Testable inner: load from a given settings directory.
/// 可測試內部函數：從指定設定目錄加載。
pub fn load_strategy_params_from(kind: PipelineKind, settings: &Path) -> StrategyParamsConfig {
    let filename = format!("strategy_params_{}.toml", kind.db_mode());
    let path = settings.join(&filename);
    match std::fs::read_to_string(&path) {
        Ok(contents) => match toml::from_str::<StrategyParamsConfig>(&contents) {
            Ok(cfg) => {
                info!(
                    kind = %kind, path = %path.display(),
                    "loaded strategy params from TOML / 從 TOML 加載策略參數"
                );
                cfg
            }
            Err(e) => {
                fallback_strategy_params_on_load_error(kind, &path, format!("parse error: {e}"))
            }
        },
        Err(_) => fallback_strategy_params_on_load_error(kind, &path, "file not found".to_string()),
    }
}

fn fail_closed_inactive_config() -> StrategyParamsConfig {
    let mut cfg = StrategyParamsConfig::default();
    cfg.ma_crossover.active = false;
    cfg.bb_reversion.active = false;
    cfg.bb_breakout.active = false;
    cfg.grid_trading.active = false;
    cfg.funding_arb.active = false;
    cfg
}

fn fallback_strategy_params_on_load_error(
    kind: PipelineKind,
    path: &Path,
    reason: String,
) -> StrategyParamsConfig {
    if kind.is_exchange() {
        warn!(
            kind = %kind,
            path = %path.display(),
            error = %reason,
            "strategy params load failed — using fail-closed inactive config \
             / 策略參數載入失敗，改用 fail-closed 全停用配置"
        );
        fail_closed_inactive_config()
    } else {
        info!(
            kind = %kind,
            path = %path.display(),
            error = %reason,
            "strategy params load failed in paper — using defaults \
             / Paper 策略參數載入失敗，使用默認值"
        );
        StrategyParamsConfig::default()
    }
}

/// Strategy parameters trait — interface for DB persistence and Agent tuning.
/// 策略參數 trait — 數據庫持久化和 Agent 調參的接口。
/// Phase 3a will implement this for each strategy. For now, just the trait definition.
/// Phase 3a 將為每個策略實現此 trait。目前只有 trait 定義。
// Phase 0a+3a: fn from_db(conn: &PgPool) -> Self will be added when sqlx is wired.
// Phase 0a+3a：fn from_db(conn: &PgPool) -> Self 將在 sqlx 接入後添加。
pub trait StrategyParams: Serialize + for<'de> Deserialize<'de> + Send {
    /// Describe tunable parameter ranges for Optuna/Agent (Phase 3b).
    /// 描述可調參數範圍，供 Optuna/Agent 使用。
    fn param_ranges() -> Vec<ParamRange>;

    /// Validate parameter values are within acceptable bounds.
    /// 驗證參數值在可接受範圍內。
    fn validate(&self) -> Result<(), String>;
}
