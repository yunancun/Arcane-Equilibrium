//! RiskManager — Core hot-path risk math helpers.
//! RiskManager — 核心熱路徑風控數學輔助函數。
//!
//! MODULE_NOTE (中文):
//!   ARCH-RC1 後核心只保留與配置無關的純計算：
//!   - 動態止損（ATR 自適應 + 反聚集偏移 + 硬編碼 regime 乘數 fallback）
//!   - 價格歷史追蹤器（ATR 計算 + 尖峰偵測）
//!   權威可調風控配置見 `openclaw_engine::config::risk_config::RiskConfig`。
//!   訂單准入與 tick 級檢查（需讀取配置）已遷移至 `openclaw_engine::risk_checks`。
//!
//! MODULE_NOTE (English):
//!   Post ARCH-RC1, core retains only config-free pure computation:
//!   - Dynamic stop-loss (ATR-adaptive + anti-cluster offset + hardcoded regime fallback)
//!   - Price history tracker (ATR + spike detection)
//!   Authoritative tunable risk config lives in `openclaw_engine::config::risk_config::RiskConfig`.
//!   Order admission + tick-level checks (which read config) moved to `openclaw_engine::risk_checks`.

mod price_tracker;
mod regime;
mod stops;

pub use price_tracker::{PriceHistoryTracker, SpikeInfo};
pub use regime::{regime_multipliers, RegimeMultipliers};
pub use stops::{anti_cluster_offset, compute_dynamic_stop_pct};
