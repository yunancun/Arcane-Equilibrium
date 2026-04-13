//! Database connection pool wrapper with health check and graceful shutdown.
//! 資料庫連接池包裝，含健康檢查和優雅關閉。
//!
//! MODULE_NOTE (EN): Wraps sqlx::PgPool with optional init (engine runs without PG).
//!   Provides connect(), health_check(), and graceful close on CancellationToken.
//!   Uses runtime sqlx::query() strings (F1: no compile-time PG dependency).
//! MODULE_NOTE (中): 包裝 sqlx::PgPool，支持可選初始化（無 PG 時引擎正常運行）。
//!   提供 connect()、health_check() 和 CancellationToken 優雅關閉。
//!   使用運行時 sqlx::query() 字符串（F1：無編譯時 PG 依賴）。

use super::DatabaseConfig;
use sqlx::postgres::{PgPool, PgPoolOptions};
use std::sync::atomic::{AtomicU32, Ordering};
use std::time::Duration;
use tracing::{info, warn};

/// Database pool wrapper with failure tracking and graceful degradation.
/// 資料庫連接池包裝，含失敗追蹤和優雅降級。
pub struct DbPool {
    pool: Option<PgPool>,
    consecutive_failures: AtomicU32,
    max_failures: u32,
}

impl DbPool {
    /// Try to connect to PostgreSQL. Returns Ok(Self) even if PG is unavailable
    /// (pool will be None, writes silently skipped).
    /// 嘗試連接 PG。即使 PG 不可用也返回 Ok（pool 為 None，寫入靜默跳過）。
    pub async fn connect(config: &DatabaseConfig) -> Self {
        if config.database_url.is_empty() {
            info!("database_url empty — DB writes disabled / 資料庫 URL 為空，DB 寫入已禁用");
            return Self {
                pool: None,
                consecutive_failures: AtomicU32::new(0),
                max_failures: config.max_flush_failures,
            };
        }

        if !config.db_writes_enabled {
            info!("db_writes_enabled=false — DB writes disabled / DB 寫入已禁用");
            return Self {
                pool: None,
                consecutive_failures: AtomicU32::new(0),
                max_failures: config.max_flush_failures,
            };
        }

        let timeout = Duration::from_millis(config.connect_timeout_ms);
        match PgPoolOptions::new()
            .max_connections(config.pool_max_connections)
            .min_connections(config.pool_min_connections)
            .acquire_timeout(timeout)
            .connect(&config.database_url)
            .await
        {
            Ok(pool) => {
                info!(
                    max_conn = config.pool_max_connections,
                    min_conn = config.pool_min_connections,
                    "PG pool connected / PG 連接池已連接"
                );
                Self {
                    pool: Some(pool),
                    consecutive_failures: AtomicU32::new(0),
                    max_failures: config.max_flush_failures,
                }
            }
            Err(e) => {
                warn!(error = %e, "PG pool connect failed — DB writes disabled / PG 連接失敗，DB 寫入已禁用");
                Self {
                    pool: None,
                    consecutive_failures: AtomicU32::new(0),
                    max_failures: config.max_flush_failures,
                }
            }
        }
    }

    /// Get the underlying pool (None if not connected).
    /// 獲取底層連接池（未連接時為 None）。
    pub fn get(&self) -> Option<&PgPool> {
        self.pool.as_ref()
    }

    /// Check if pool is available and connected.
    /// 檢查連接池是否可用。
    pub fn is_available(&self) -> bool {
        self.pool.is_some()
    }

    /// Record a successful flush (resets failure counter).
    /// 記錄成功的刷新（重置失敗計數器）。
    pub fn record_success(&self) {
        self.consecutive_failures.store(0, Ordering::Relaxed);
    }

    /// Record a failed flush. Returns true if fallback should be triggered.
    /// 記錄失敗的刷新。返回 true 表示應觸發回退。
    pub fn record_failure(&self) -> bool {
        let prev = self.consecutive_failures.fetch_add(1, Ordering::Relaxed);
        prev + 1 >= self.max_failures
    }

    /// Get current consecutive failure count.
    /// 獲取當前連續失敗次數。
    pub fn failure_count(&self) -> u32 {
        self.consecutive_failures.load(Ordering::Relaxed)
    }

    /// Create a disconnected pool (no DB). Useful for tests that don't need DB.
    /// 創建斷開的連接池（無 DB）。用於不需要 DB 的測試。
    pub fn disconnected() -> Self {
        Self {
            pool: None,
            consecutive_failures: AtomicU32::new(0),
            max_failures: 10,
        }
    }

    /// Health check: execute SELECT 1.
    /// 健康檢查：執行 SELECT 1。
    pub async fn health_check(&self) -> bool {
        if let Some(ref pool) = self.pool {
            sqlx::query("SELECT 1").execute(pool).await.is_ok()
        } else {
            false
        }
    }

    /// Graceful close: drain pool connections.
    /// 優雅關閉：排空連接池。
    pub async fn close(&self) {
        if let Some(ref pool) = self.pool {
            pool.close().await;
            info!("PG pool closed / PG 連接池已關閉");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_pool_empty_url_returns_none() {
        let cfg = DatabaseConfig {
            database_url: String::new(),
            ..Default::default()
        };
        let pool = DbPool::connect(&cfg).await;
        assert!(!pool.is_available());
        assert!(!pool.health_check().await);
    }

    #[tokio::test]
    async fn test_pool_disabled_returns_none() {
        let cfg = DatabaseConfig {
            database_url: "postgresql://localhost/test".into(),
            db_writes_enabled: false,
            ..Default::default()
        };
        let pool = DbPool::connect(&cfg).await;
        assert!(!pool.is_available());
    }

    #[test]
    fn test_failure_tracking() {
        let pool = DbPool {
            pool: None,
            consecutive_failures: AtomicU32::new(0),
            max_failures: 3,
        };
        assert!(!pool.record_failure()); // 1 < 3
        assert!(!pool.record_failure()); // 2 < 3
        assert!(pool.record_failure()); // 3 >= 3 → trigger fallback
        assert_eq!(pool.failure_count(), 3);

        pool.record_success();
        assert_eq!(pool.failure_count(), 0);
    }

    #[tokio::test]
    async fn test_pool_invalid_url_graceful() {
        let cfg = DatabaseConfig {
            database_url: "postgresql://invalid:99999/nonexistent".into(),
            connect_timeout_ms: 500,
            ..Default::default()
        };
        let pool = DbPool::connect(&cfg).await;
        // Should not panic, just return None pool
        assert!(!pool.is_available());
    }
}
