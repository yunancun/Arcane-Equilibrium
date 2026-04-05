//! ExperimentLedger PG persistence — CRUD for hypothesis lifecycle tracking.
//! ExperimentLedger PG 持久化 — 假設生命週期追蹤的 CRUD。
//!
//! MODULE_NOTE (EN): Rust-side persistence for learning.experiment_ledger table (V007).
//!   Provides create/read/update/list operations. Clears Phase 1 debt (1-14/1-15, F7 audit).
//!   3 new fields: source_type, metadata JSONB, trigger_condition.
//! MODULE_NOTE (中): learning.experiment_ledger 表的 Rust 端持久化（V007）。
//!   提供 create/read/update/list 操作。清除 Phase 1 債務（1-14/1-15，F7 審計）。

use super::pool::DbPool;
use serde::{Deserialize, Serialize};
use tracing::{debug, warn};

/// Hypothesis record for PG persistence.
/// 假設記錄，用於 PG 持久化。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Hypothesis {
    pub hypothesis_id: String,
    pub description: String,
    pub strategy_name: String,
    pub regime: String,
    pub proposed_by: String,
    pub proposed_at_ms: u64,
    pub expires_at_ms: u64,
    pub status: String,
    pub min_observations: i32,
    pub supporting_count: i32,
    pub refuting_count: i32,
    pub concluded_at_ms: Option<u64>,
    pub claim_id: Option<String>,
    pub notes: String,
    // Phase 2a new fields / 新欄位
    pub source_type: String,
    pub metadata: serde_json::Value,
    pub trigger_condition: String,
}

impl Default for Hypothesis {
    fn default() -> Self {
        Self {
            hypothesis_id: String::new(),
            description: String::new(),
            strategy_name: String::new(),
            regime: "all".into(),
            proposed_by: String::new(),
            proposed_at_ms: 0,
            expires_at_ms: 0,
            status: "PENDING".into(),
            min_observations: 20,
            supporting_count: 0,
            refuting_count: 0,
            concluded_at_ms: None,
            claim_id: None,
            notes: String::new(),
            source_type: "rule_based".into(),
            metadata: serde_json::json!({}),
            trigger_condition: String::new(),
        }
    }
}

/// Insert a new hypothesis into learning.experiment_ledger.
/// 插入新假設到 learning.experiment_ledger。
pub async fn create_hypothesis(pool: &DbPool, h: &Hypothesis) -> bool {
    let pg = match pool.get() { Some(p) => p, None => return false };

    let result = sqlx::query(
        "INSERT INTO learning.experiment_ledger \
         (hypothesis_id, description, strategy_name, regime, proposed_by, \
          proposed_at_ms, expires_at_ms, status, min_observations, \
          supporting_count, refuting_count, notes, \
          source_type, metadata, trigger_condition) \
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15) \
         ON CONFLICT (hypothesis_id) DO NOTHING"
    )
    .bind(&h.hypothesis_id)
    .bind(&h.description)
    .bind(&h.strategy_name)
    .bind(&h.regime)
    .bind(&h.proposed_by)
    .bind(h.proposed_at_ms as i64)
    .bind(h.expires_at_ms as i64)
    .bind(&h.status)
    .bind(h.min_observations)
    .bind(h.supporting_count)
    .bind(h.refuting_count)
    .bind(&h.notes)
    .bind(&h.source_type)
    .bind(&h.metadata)
    .bind(&h.trigger_condition)
    .execute(pg)
    .await;

    match result {
        Ok(r) => { debug!(id = %h.hypothesis_id, "hypothesis created / 假設已創建"); r.rows_affected() > 0 }
        Err(e) => { warn!(id = %h.hypothesis_id, error = %e, "hypothesis create failed"); false }
    }
}

/// Update observation counts + status for a hypothesis.
/// 更新假設的觀測計數 + 狀態。
pub async fn update_hypothesis(
    pool: &DbPool,
    hypothesis_id: &str,
    supporting: i32,
    refuting: i32,
    status: &str,
    concluded_at_ms: Option<u64>,
) -> bool {
    let pg = match pool.get() { Some(p) => p, None => return false };

    let result = sqlx::query(
        "UPDATE learning.experiment_ledger \
         SET supporting_count = $2, refuting_count = $3, status = $4, \
             concluded_at_ms = $5, updated_at = NOW() \
         WHERE hypothesis_id = $1"
    )
    .bind(hypothesis_id)
    .bind(supporting)
    .bind(refuting)
    .bind(status)
    .bind(concluded_at_ms.map(|v| v as i64))
    .execute(pg)
    .await;

    match result {
        Ok(r) => { debug!(id = %hypothesis_id, status = status, "hypothesis updated"); r.rows_affected() > 0 }
        Err(e) => { warn!(id = %hypothesis_id, error = %e, "hypothesis update failed"); false }
    }
}

/// List hypotheses by status (or all if status is empty).
/// 按狀態列出假設（狀態為空時列出全部）。
pub async fn list_hypotheses(pool: &DbPool, status_filter: &str, limit: u32) -> Vec<Hypothesis> {
    let pg = match pool.get() { Some(p) => p, None => return vec![] };

    let rows = if status_filter.is_empty() {
        sqlx::query_as::<_, HypothesisRow>(
            "SELECT hypothesis_id, description, strategy_name, regime, proposed_by, \
             proposed_at_ms, expires_at_ms, status, min_observations, \
             supporting_count, refuting_count, concluded_at_ms, claim_id, notes, \
             source_type, metadata, trigger_condition \
             FROM learning.experiment_ledger ORDER BY proposed_at_ms DESC LIMIT $1"
        )
        .bind(limit as i32)
        .fetch_all(pg)
        .await
    } else {
        sqlx::query_as::<_, HypothesisRow>(
            "SELECT hypothesis_id, description, strategy_name, regime, proposed_by, \
             proposed_at_ms, expires_at_ms, status, min_observations, \
             supporting_count, refuting_count, concluded_at_ms, claim_id, notes, \
             source_type, metadata, trigger_condition \
             FROM learning.experiment_ledger WHERE status = $1 ORDER BY proposed_at_ms DESC LIMIT $2"
        )
        .bind(status_filter)
        .bind(limit as i32)
        .fetch_all(pg)
        .await
    };

    match rows {
        Ok(rows) => rows.into_iter().map(|r| r.into()).collect(),
        Err(e) => { warn!(error = %e, "list hypotheses failed"); vec![] }
    }
}

/// Internal row type for sqlx FromRow (requires exact column mapping).
/// 內部行類型（sqlx FromRow 需要精確列映射）。
#[derive(sqlx::FromRow)]
struct HypothesisRow {
    hypothesis_id: String,
    description: String,
    strategy_name: String,
    regime: String,
    proposed_by: String,
    proposed_at_ms: i64,
    expires_at_ms: i64,
    status: String,
    min_observations: i32,
    supporting_count: i32,
    refuting_count: i32,
    concluded_at_ms: Option<i64>,
    claim_id: Option<String>,
    notes: String,
    source_type: String,
    metadata: serde_json::Value,
    trigger_condition: String,
}

impl From<HypothesisRow> for Hypothesis {
    fn from(r: HypothesisRow) -> Self {
        Self {
            hypothesis_id: r.hypothesis_id,
            description: r.description,
            strategy_name: r.strategy_name,
            regime: r.regime,
            proposed_by: r.proposed_by,
            proposed_at_ms: r.proposed_at_ms as u64,
            expires_at_ms: r.expires_at_ms as u64,
            status: r.status,
            min_observations: r.min_observations,
            supporting_count: r.supporting_count,
            refuting_count: r.refuting_count,
            concluded_at_ms: r.concluded_at_ms.map(|v| v as u64),
            claim_id: r.claim_id,
            notes: r.notes,
            source_type: r.source_type,
            metadata: r.metadata,
            trigger_condition: r.trigger_condition,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hypothesis_default() {
        let h = Hypothesis::default();
        assert_eq!(h.status, "PENDING");
        assert_eq!(h.regime, "all");
        assert_eq!(h.min_observations, 20);
        assert_eq!(h.source_type, "rule_based");
    }

    #[test]
    fn test_hypothesis_serialization() {
        let h = Hypothesis {
            hypothesis_id: "h-001".into(),
            description: "test".into(),
            strategy_name: "ma_crossover".into(),
            source_type: "signal".into(),
            metadata: serde_json::json!({"key": "value"}),
            trigger_condition: "adx > 25".into(),
            ..Default::default()
        };
        let json = serde_json::to_string(&h).unwrap();
        assert!(json.contains("h-001"));
        assert!(json.contains("signal"));
        assert!(json.contains("adx > 25"));
    }

    #[test]
    fn test_hypothesis_row_conversion() {
        let row = HypothesisRow {
            hypothesis_id: "h-test".into(),
            description: "desc".into(),
            strategy_name: "bb".into(),
            regime: "trending".into(),
            proposed_by: "strategist".into(),
            proposed_at_ms: 1700000000000,
            expires_at_ms: 1700604800000,
            status: "RUNNING".into(),
            min_observations: 30,
            supporting_count: 10,
            refuting_count: 5,
            concluded_at_ms: None,
            claim_id: None,
            notes: "".into(),
            source_type: "claude_directive".into(),
            metadata: serde_json::json!({}),
            trigger_condition: "".into(),
        };
        let h: Hypothesis = row.into();
        assert_eq!(h.hypothesis_id, "h-test");
        assert_eq!(h.proposed_at_ms, 1700000000000);
        assert_eq!(h.source_type, "claude_directive");
    }
}
