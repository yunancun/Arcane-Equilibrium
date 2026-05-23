//! 玄衡 · Arcane Equilibrium — cron 排程模組命名空間 (Sprint 1B Earn first stake)。
//!
//! MODULE_NOTE
//! 模塊用途：
//!   集中宣告引擎進程內運行的「日級 / 多日級」cron-like scheduler，
//!   與 helper_scripts/db 下的 systemd / crontab 外部 cron 區隔。
//!   首個成員 `earn_reconciliation` 每日 UTC 02:00 對 Bybit Earn 帳餘 v.s.
//!   V100 `learning.earn_movement_log` 做對賬，產 3 階 cascade alert
//!   (NOTICE / HEALTH_WARN / HEALTH_DEGRADED)。
//!
//! 主要類 / 函數：
//!   - `earn_reconciliation::EarnReconciliationCron` — 對賬主類
//!   - `earn_reconciliation::ReconciliationOutcome` — 對賬結果 enum
//!   - `earn_reconciliation::DiffSeverity` — 3 階 cascade severity
//!   - `earn_reconciliation::BybitEarnBalanceSource` — Bybit 餘額查詢 trait
//!   - `earn_reconciliation::EarnMovementReader` — V100 movement_log 讀取 trait
//!
//! 依賴：
//!   - tokio (interval / select / spawn 與既有 cron 風格一致)
//!   - chrono (UTC 02:00 schedule 計算 + day 維度連續 mismatch 計數)
//!   - async-trait (Bybit + V100 reader trait 對齊 health::writer 範式)
//!   - tracing (NOTICE / WARN / DEGRADED 三階輸出走 tracing target
//!     "cron.earn_reconciliation")
//!
//! 硬邊界：
//!   - 不直接接 real Bybit Earn endpoint：Wave B B3 `bybit_earn_client.rs`
//!     land 後，將其 wrapper 化為 `BybitEarnBalanceSource` 實作；本模組僅持
//!     trait + mock impl，符合 dispatch packet「mock only；real deploy 待
//!     B3 client + OP-1 key 重發」規格。
//!   - 不直接寫 risk_config_*.toml 切 `earn_enabled=false`：對齊 dispatch
//!     packet operator 指示「3 cascade thresholds = NOTICE / WARN / DEGRADED」
//!     僅做 audit + health routing；disable / halt strategy 留 Wave B 接
//!     RiskEnvelope hook 後再串。
//!   - UTC 02:00 schedule 對齊 dispatch packet OP-4 caveat 2（避開 funding
//!     settlement 00:00 / 08:00 / 16:00 UTC）。
//!   - reconciliation cron 自身 fail (Bybit timeout / PG error) 不計入連續
//!     mismatch 計數（per earn_governance §6.3 避免雙重懲罰）；連續 3 day cron
//!     自身 fail 留 Wave B 後續接 halt path。

pub mod earn_reconciliation;
