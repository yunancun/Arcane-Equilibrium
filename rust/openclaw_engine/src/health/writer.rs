//! M3 Sprint 2 Track A — V106 `learning.health_observations` INSERT writer。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md
//!   §3.1 + §4.1 step 4，每次 sample 採樣 / state transition fire / D3 cascade
//!   reject 事件，writer 將 row 寫入 V106 schema `learning.health_observations`
//!   hypertable。本 module 定義 `HealthObservationWriter` trait + 兩個 impl：
//!     - `PgHealthObservationWriter`：production runtime sqlx INSERT 接 PgPool。
//!     - `InMemoryHealthObservationWriter`：test fixture in-memory 記錄。
//!
//! 主要類 / 函數:
//!   - `HealthObservationRow`：對齊 V106 schema 19 column 的 Rust struct。
//!   - `HealthObservationWriter` trait：`write_observation` + `write_sample_error`。
//!   - `PgHealthObservationWriter`：production sqlx INSERT 實作。
//!   - `InMemoryHealthObservationWriter`：test fixture，輕量保留 row + 統計。
//!
//! 依賴:
//!   - sqlx Postgres + chrono + serde_json + tokio::sync（mutex 保護 in-memory
//!     buffer）。
//!   - 不依賴 spike feature；production binary 完整 include。
//!
//! 硬邊界:
//!   - V106 schema 19 column 嚴格對齊（per sql/migrations/V106 line 219-266）；
//!     新增 column 必同步更新本 module。
//!   - INSERT 失敗時 caller 端 fail-soft（不阻 sample loop；下次 sample 仍跑）。
//!   - `engine_mode` 必 4 值之一（per V106 CHECK：paper/demo/live_demo/live）；
//!     Sprint 2 不寫 live（live 走 Sprint 4）。
//!   - 不繞 Guardian / 5-gate；只寫 audit row（per ADR-0042 Decision 1 unique
//!     authority）。

use std::sync::Arc;

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use parking_lot::Mutex;
use serde_json::Value as JsonValue;
use sqlx::PgPool;

use super::{HealthDomain, HealthState, M3Error};

/// V106 `learning.health_observations` 1 row 投影（per schema 19 column）。
///
/// 為什麼 BIGSERIAL `observation_id` 不在 Rust struct：
///   - PG BIGSERIAL 由 DB 端 nextval 取；client INSERT 走 DEFAULT 不傳 id。
///   - 對齊 V106 schema line 220 `observation_id BIGSERIAL`。
/// 為什麼 `created_at` / `created_by` / `source_version` 由 DB DEFAULT：
///   - V106 schema 已設 DEFAULT now() / 'health_monitor' / 'V106'；除非 caller
///     端覆蓋，否則 INSERT 不傳。
#[derive(Debug, Clone)]
pub struct HealthObservationRow {
    /// V106 column `observed_at TIMESTAMPTZ NOT NULL`：採樣時間（UTC）。
    pub observed_at: DateTime<Utc>,
    /// V106 column `domain` per ADR-0042 Decision 3 6 值；嚴格 CHECK 對齊。
    pub domain: HealthDomain,
    /// V106 column `metric_name`（per-domain 自定 metric_name 命名）。
    pub metric_name: String,
    /// V106 column `state HEALTH_OK/WARN/DEGRADED/CRITICAL`。
    pub state: HealthState,
    /// V106 column `state_prev`：transition 前狀態；same-state 採樣 None。
    pub state_prev: Option<HealthState>,
    /// V106 column `dwell_time_sec`：在 prev state 停留秒數；無 transition 時 None。
    pub dwell_time_sec: Option<i32>,
    /// V106 column `metric_value NUMERIC(18,8) NOT NULL`：採樣值。
    pub metric_value: f64,
    /// V106 column `metric_threshold NUMERIC(18,8)`：classify 用 threshold。
    pub metric_threshold: Option<f64>,
    /// V106 column `amplification_loop_24h_count`：寫入時 SM 當前計數。
    pub amplification_loop_24h_count: i32,
    /// V106 column `symbol`：per-symbol metric（如 strategy_quality）才填。
    pub symbol: Option<String>,
    /// V106 column `strategy_name`：per-strategy metric 才填。
    pub strategy_name: Option<String>,
    /// V106 column `evidence_json JSONB`：sample error + cascade reject reason
    /// + audit context（per D3 cascade reject log emit）。
    pub evidence_json: Option<JsonValue>,
    /// V106 column `engine_mode`：paper/demo/live_demo/live；Sprint 2 不寫 live。
    pub engine_mode: String,
    /// V106 column `created_by`：默認 "health_monitor"；caller 端可覆蓋。
    pub created_by: Option<String>,
    /// V106 column `source_version`：默認 "V106"；caller 端可覆蓋。
    pub source_version: Option<String>,
}

impl HealthObservationRow {
    /// 建構最小必要欄位的 row（其餘走 V106 DEFAULT / None）。
    pub fn new(
        domain: HealthDomain,
        metric_name: impl Into<String>,
        state: HealthState,
        metric_value: f64,
        amplification_loop_24h_count: i32,
        engine_mode: impl Into<String>,
    ) -> Self {
        Self {
            observed_at: Utc::now(),
            domain,
            metric_name: metric_name.into(),
            state,
            state_prev: None,
            dwell_time_sec: None,
            metric_value,
            metric_threshold: None,
            amplification_loop_24h_count,
            symbol: None,
            strategy_name: None,
            evidence_json: None,
            engine_mode: engine_mode.into(),
            created_by: None,
            source_version: None,
        }
    }

    /// 帶 state_prev + dwell（transition fire 場景用）。
    pub fn with_transition(
        mut self,
        state_prev: HealthState,
        dwell_time_sec: i32,
    ) -> Self {
        self.state_prev = Some(state_prev);
        self.dwell_time_sec = Some(dwell_time_sec);
        self
    }

    /// 帶 evidence_json（sample error / cascade reject reason / context）。
    pub fn with_evidence(mut self, evidence: JsonValue) -> Self {
        self.evidence_json = Some(evidence);
        self
    }

    /// 帶 metric_threshold（classify 用 threshold）。
    pub fn with_threshold(mut self, threshold: f64) -> Self {
        self.metric_threshold = Some(threshold);
        self
    }

    /// 帶 symbol（strategy_quality / pipeline_throughput per-symbol metric 用）。
    pub fn with_symbol(mut self, symbol: impl Into<String>) -> Self {
        self.symbol = Some(symbol.into());
        self
    }

    /// 帶 strategy_name（strategy_quality per-strategy metric 用）。
    pub fn with_strategy(mut self, strategy: impl Into<String>) -> Self {
        self.strategy_name = Some(strategy.into());
        self
    }
}

/// V106 row INSERT writer trait。
///
/// 為什麼 trait + 兩 impl:
///   - production 走 sqlx 接 PgPool；test 走 in-memory mock（避 Linux PG dep）。
///   - 對齊 spec §3.1 emitter trait + writer trait 分離設計。
#[async_trait]
pub trait HealthObservationWriter: Send + Sync {
    /// 寫一 row 進 V106 hypertable。
    ///
    /// fail-soft 語意:
    ///   per spec §4.1 step 4：INSERT 失敗 caller 端 log + continue；不阻 sample
    ///   loop（避 DB 退化反殺 emitter）。
    async fn write_observation(&self, row: HealthObservationRow) -> Result<(), M3Error>;

    /// sample error fail-closed path：寫一 row state=HEALTH_OK +
    /// evidence_json.sample_error，等下次 sample。
    ///
    /// 為什麼此入口存在:
    ///   - per spec §4.1 step 1 fallback：emitter.sample() 失敗 → writer 寫 row
    ///     紀錄 sample failure，state 維持 OK 不升級（fail-closed default）。
    ///   - audit trail 保留：Sprint 5 cascade 可從 V106 backfill 推導 sample 連
    ///     續失敗模式。
    async fn write_sample_error(
        &self,
        domain: HealthDomain,
        metric_name: &str,
        error: &M3Error,
        engine_mode: &str,
    ) -> Result<(), M3Error>;
}

/// Production runtime sqlx INSERT 實作（per V106 schema 19 column）。
///
/// 為什麼 PgPool 包裝 Arc<PgPool>:
///   - PgPool::clone 已 Arc-shared；wrapper struct 對齊 spec §3.1 `PgPoolWrapper`
///     語意 + 為 Sprint 5 cascade 加 retry/timeout middleware 留接口。
pub struct PgHealthObservationWriter {
    pool: PgPool,
}

impl PgHealthObservationWriter {
    /// 建立 production writer；caller 端 share PgPool（engine main pool）。
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }
}

#[async_trait]
impl HealthObservationWriter for PgHealthObservationWriter {
    async fn write_observation(&self, row: HealthObservationRow) -> Result<(), M3Error> {
        // sqlx INSERT 對齊 V106 schema 19 column：
        //   observation_id（DB BIGSERIAL）+ created_at（DB DEFAULT now()）走 DEFAULT
        //   created_by / source_version：caller 提供時用；否則 DB DEFAULT
        //     ('health_monitor' / 'V106')
        // 14 explicit binding + 5 default = 19 column。
        let state_prev_str: Option<String> = row.state_prev.map(|s| s.as_str().to_string());
        let domain_str: String = row.domain.as_str().to_string();
        let state_str: String = row.state.as_str().to_string();

        // sqlx 0.8 NUMERIC(18,8) ↔ f64 binding 需 BigDecimal feature，但
        // workspace sqlx feature 沒開 bigdecimal；改走顯式 cast 為 PG NUMERIC：
        //   `$N::NUMERIC(18,8)` 將 f64 文字注入後 PG 端 cast；
        // 為什麼用 cast 而非 BigDecimal:
        //   - 避免引入新 dep（rust_decimal/bigdecimal）；workspace 已盡量精簡。
        //   - 5-sample window 數值範圍（CPU% / RSS_MB / ratio）精度 1e-6 內，f64
        //     cast NUMERIC(18,8) 對應 18 位整數 + 8 位小數，足以保留 metric 精度。
        let result = sqlx::query(
            r#"
            INSERT INTO learning.health_observations (
                observed_at,
                domain,
                metric_name,
                state,
                state_prev,
                dwell_time_sec,
                metric_value,
                metric_threshold,
                amplification_loop_24h_count,
                symbol,
                strategy_name,
                evidence_json,
                engine_mode,
                created_by,
                source_version
            ) VALUES (
                $1, $2, $3, $4, $5, $6,
                $7::NUMERIC(18,8), $8::NUMERIC(18,8),
                $9, $10, $11, $12, $13,
                COALESCE($14, 'health_monitor'),
                COALESCE($15, 'V106')
            )
            "#,
        )
        .bind(row.observed_at)
        .bind(domain_str)
        .bind(row.metric_name.clone())
        .bind(state_str)
        .bind(state_prev_str)
        .bind(row.dwell_time_sec)
        .bind(row.metric_value)
        .bind(row.metric_threshold)
        .bind(row.amplification_loop_24h_count)
        .bind(row.symbol.clone())
        .bind(row.strategy_name.clone())
        .bind(row.evidence_json.clone())
        .bind(row.engine_mode.clone())
        .bind(row.created_by.clone())
        .bind(row.source_version.clone())
        .execute(&self.pool)
        .await;

        match result {
            Ok(_) => Ok(()),
            Err(e) => {
                // fail-soft：log + 包裝 M3Error 後給 caller 決定是否 swallow。
                tracing::warn!(
                    target = "m3.health.writer",
                    "V106 INSERT failed: domain={} metric={} err={}",
                    row.domain.as_str(),
                    row.metric_name,
                    e
                );
                Err(M3Error::WriterError(e.to_string()))
            }
        }
    }

    async fn write_sample_error(
        &self,
        domain: HealthDomain,
        metric_name: &str,
        error: &M3Error,
        engine_mode: &str,
    ) -> Result<(), M3Error> {
        let evidence = serde_json::json!({
            "sample_error": error.to_string(),
        });
        let row = HealthObservationRow::new(
            domain,
            metric_name.to_string(),
            HealthState::HealthOk,
            0.0,
            0,
            engine_mode.to_string(),
        )
        .with_evidence(evidence);
        self.write_observation(row).await
    }
}

/// Test fixture in-memory writer；保留每筆 row 供 assert。
///
/// 為什麼 parking_lot::Mutex 而非 tokio::Mutex:
///   - test fixture 不在 hot path；parking_lot 同步 lock 更輕量。
///   - workspace 已 dep parking_lot。
pub struct InMemoryHealthObservationWriter {
    rows: Arc<Mutex<Vec<HealthObservationRow>>>,
}

impl InMemoryHealthObservationWriter {
    pub fn new() -> Self {
        Self {
            rows: Arc::new(Mutex::new(Vec::new())),
        }
    }

    /// 取得目前所有 row 的 clone；不清空 buffer。
    pub fn snapshot(&self) -> Vec<HealthObservationRow> {
        self.rows.lock().clone()
    }

    /// 清空 buffer + 取出所有 row。
    pub fn drain(&self) -> Vec<HealthObservationRow> {
        let mut guard = self.rows.lock();
        std::mem::take(&mut *guard)
    }

    /// 當前 row 數。
    pub fn len(&self) -> usize {
        self.rows.lock().len()
    }

    /// 是否為空。
    pub fn is_empty(&self) -> bool {
        self.rows.lock().is_empty()
    }
}

impl Default for InMemoryHealthObservationWriter {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl HealthObservationWriter for InMemoryHealthObservationWriter {
    async fn write_observation(&self, row: HealthObservationRow) -> Result<(), M3Error> {
        self.rows.lock().push(row);
        Ok(())
    }

    async fn write_sample_error(
        &self,
        domain: HealthDomain,
        metric_name: &str,
        error: &M3Error,
        engine_mode: &str,
    ) -> Result<(), M3Error> {
        let evidence = serde_json::json!({
            "sample_error": error.to_string(),
        });
        let row = HealthObservationRow::new(
            domain,
            metric_name.to_string(),
            HealthState::HealthOk,
            0.0,
            0,
            engine_mode.to_string(),
        )
        .with_evidence(evidence);
        self.write_observation(row).await
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_in_memory_writer_records_row() {
        let writer = InMemoryHealthObservationWriter::new();
        let row = HealthObservationRow::new(
            HealthDomain::EngineRuntime,
            "cpu_pct",
            HealthState::HealthOk,
            42.0,
            0,
            "demo",
        );
        writer.write_observation(row.clone()).await.unwrap();
        assert_eq!(writer.len(), 1);
        let snapshot = writer.snapshot();
        assert_eq!(snapshot[0].metric_name, "cpu_pct");
        assert_eq!(snapshot[0].metric_value, 42.0);
    }

    #[tokio::test]
    async fn test_with_transition_helper_records_state_prev_and_dwell() {
        let row = HealthObservationRow::new(
            HealthDomain::EngineRuntime,
            "cpu_pct",
            HealthState::HealthWarn,
            65.0,
            1,
            "demo",
        )
        .with_transition(HealthState::HealthOk, 60);
        assert_eq!(row.state_prev, Some(HealthState::HealthOk));
        assert_eq!(row.dwell_time_sec, Some(60));
    }

    #[tokio::test]
    async fn test_with_evidence_records_json() {
        let evidence = serde_json::json!({
            "reject_reason": "amp_cap_same_anomaly_24h_suppress",
        });
        let row = HealthObservationRow::new(
            HealthDomain::EngineRuntime,
            "cpu_pct",
            HealthState::HealthWarn,
            65.0,
            2,
            "demo",
        )
        .with_evidence(evidence.clone());
        assert_eq!(row.evidence_json, Some(evidence));
    }

    #[tokio::test]
    async fn test_in_memory_writer_sample_error_path() {
        let writer = InMemoryHealthObservationWriter::new();
        let err = M3Error::SampleError("sysinfo read failed".to_string());
        writer
            .write_sample_error(HealthDomain::EngineRuntime, "cpu_pct", &err, "demo")
            .await
            .unwrap();
        let snapshot = writer.snapshot();
        assert_eq!(snapshot.len(), 1);
        // sample error fail-closed：state 維持 OK，evidence_json 含 sample_error。
        assert_eq!(snapshot[0].state, HealthState::HealthOk);
        let evidence = snapshot[0].evidence_json.as_ref().unwrap();
        assert!(evidence["sample_error"]
            .as_str()
            .unwrap()
            .contains("sysinfo read failed"));
    }

    #[tokio::test]
    async fn test_drain_clears_buffer() {
        let writer = InMemoryHealthObservationWriter::new();
        let row = HealthObservationRow::new(
            HealthDomain::EngineRuntime,
            "cpu_pct",
            HealthState::HealthOk,
            10.0,
            0,
            "paper",
        );
        writer.write_observation(row).await.unwrap();
        assert_eq!(writer.len(), 1);
        let drained = writer.drain();
        assert_eq!(drained.len(), 1);
        assert!(writer.is_empty());
    }
}
