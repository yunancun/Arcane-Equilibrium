//! LinUCB state PG IO — load / upsert with feature_schema_hash fail-closed.
//! LinUCB state PG IO — load / upsert，feature_schema_hash fail-closed。
//!
//! MODULE_NOTE (EN): Reads and writes `learning.linucb_state` (V009 + V010 schema).
//!   On load, every row's `feature_schema_hash` is compared against the caller's
//!   expected hash; any mismatch raises `LinUcbIoError::SchemaMismatch` and the
//!   entire load aborts (fail-closed). A and b are serialized as little-endian
//!   f64 BYTEA blobs (length = dim*8 and dim*dim*8 respectively).
//! MODULE_NOTE (中): 讀寫 `learning.linucb_state`（V009 + V010 schema）。
//!   載入時逐 row 比對 `feature_schema_hash` 與呼叫端期望值；任何不匹配
//!   都會回傳 `LinUcbIoError::SchemaMismatch`，整個 load 中止（fail-closed）。
//!   A 與 b 以小端 f64 BYTEA blob 序列化（長度分別為 dim*dim*8 與 dim*8）。

use super::inference::ArmState;
use crate::database::pool::DbPool;

/// Errors raised by LinUCB state IO. / LinUCB state IO 錯誤。
#[derive(Debug, thiserror::Error)]
pub enum LinUcbIoError {
    #[error("PG pool unavailable / PG 連接池不可用")]
    NoPool,
    #[error("DB query failed / DB 查詢失敗: {0}")]
    Db(String),
    #[error(
        "feature_schema_hash mismatch (arm_id={arm_id}, expected={expected}, got={got}) — \
         fail-closed / 特徵 schema 雜湊不匹配，fail-closed"
    )]
    SchemaMismatch {
        arm_id: String,
        expected: String,
        got: String,
    },
    #[error("BYTEA payload size invalid (arm_id={arm_id}, expected={expected}, got={got}) / BYTEA 大小無效")]
    PayloadSize {
        arm_id: String,
        expected: usize,
        got: usize,
    },
}

/// Serialize Vec<f64> as little-endian BYTEA blob. / Vec<f64> 序列化為小端 BYTEA。
pub fn f64_vec_to_bytes(v: &[f64]) -> Vec<u8> {
    let mut out = Vec::with_capacity(v.len() * 8);
    for x in v {
        out.extend_from_slice(&x.to_le_bytes());
    }
    out
}

/// Deserialize little-endian BYTEA blob into Vec<f64>. / 小端 BYTEA 解碼為 Vec<f64>。
pub fn bytes_to_f64_vec(b: &[u8]) -> Option<Vec<f64>> {
    if b.len() % 8 != 0 {
        return None;
    }
    let mut out = Vec::with_capacity(b.len() / 8);
    for chunk in b.chunks_exact(8) {
        let arr: [u8; 8] = chunk.try_into().ok()?;
        out.push(f64::from_le_bytes(arr));
    }
    Some(out)
}

/// Pure helper: validate one row's hash against expected, fail-closed on mismatch.
/// Exposed for unit testing without a real PG pool.
/// 純函數：對單 row 驗證 hash vs expected，不匹配就 fail-closed。
/// 對外暴露以便不需真實 PG 即可測試。
pub fn validate_row_schema_hash(
    arm_id: &str,
    expected: &str,
    got: &str,
) -> Result<(), LinUcbIoError> {
    if expected == got {
        Ok(())
    } else {
        Err(LinUcbIoError::SchemaMismatch {
            arm_id: arm_id.to_string(),
            expected: expected.to_string(),
            got: got.to_string(),
        })
    }
}

/// Load all arms for the given arm_space_version, fail-closed on schema mismatch.
/// 載入指定 arm_space_version 的所有 arm，schema 不匹配時 fail-closed。
pub async fn load_arms(
    pool: &DbPool,
    arm_space_version: &str,
    expected_schema_hash: &str,
) -> Result<Vec<ArmState>, LinUcbIoError> {
    let pg = pool.get().ok_or(LinUcbIoError::NoPool)?;

    let rows = sqlx::query_as::<_, (String, Vec<u8>, Vec<u8>, i32, i64, String)>(
        "SELECT arm_id, a_matrix, b_vector, context_dim, n_pulls, feature_schema_hash \
         FROM learning.linucb_state \
         WHERE arm_space_version = $1",
    )
    .bind(arm_space_version)
    .fetch_all(pg)
    .await
    .map_err(|e| LinUcbIoError::Db(e.to_string()))?;

    let mut arms = Vec::with_capacity(rows.len());
    for (arm_id, a_bytes, b_bytes, context_dim, n_pulls, schema_hash) in rows {
        // Fail-closed schema check / fail-closed schema 檢查
        validate_row_schema_hash(&arm_id, expected_schema_hash, &schema_hash)?;

        let dim = context_dim as usize;
        let expected_a = dim * dim * 8;
        let expected_b = dim * 8;
        if a_bytes.len() != expected_a {
            return Err(LinUcbIoError::PayloadSize {
                arm_id,
                expected: expected_a,
                got: a_bytes.len(),
            });
        }
        if b_bytes.len() != expected_b {
            return Err(LinUcbIoError::PayloadSize {
                arm_id,
                expected: expected_b,
                got: b_bytes.len(),
            });
        }
        let a_matrix = bytes_to_f64_vec(&a_bytes).ok_or_else(|| LinUcbIoError::PayloadSize {
            arm_id: arm_id.clone(),
            expected: expected_a,
            got: a_bytes.len(),
        })?;
        let b_vector = bytes_to_f64_vec(&b_bytes).ok_or_else(|| LinUcbIoError::PayloadSize {
            arm_id: arm_id.clone(),
            expected: expected_b,
            got: b_bytes.len(),
        })?;
        arms.push(ArmState {
            arm_id,
            a_matrix,
            b_vector,
            n_pulls,
        });
    }
    Ok(arms)
}

/// Upsert one arm's state into PG (cold-start safe; warm-start migration is 4-06).
/// 將單個 arm 的狀態 upsert 到 PG（cold-start 安全；warm-start 遷移屬於 4-06）。
pub async fn upsert_arm(
    pool: &DbPool,
    arm_space_version: &str,
    feature_schema_hash: &str,
    state: &ArmState,
) -> Result<(), LinUcbIoError> {
    let pg = pool.get().ok_or(LinUcbIoError::NoPool)?;
    let dim = state.b_vector.len() as i32;
    let a_bytes = f64_vec_to_bytes(&state.a_matrix);
    let b_bytes = f64_vec_to_bytes(&state.b_vector);

    sqlx::query(
        "INSERT INTO learning.linucb_state \
         (arm_id, arm_space_version, a_matrix, b_vector, context_dim, n_pulls, \
          feature_schema_hash, last_updated_ts) \
         VALUES ($1, $2, $3, $4, $5, $6, $7, NOW()) \
         ON CONFLICT (arm_id, arm_space_version) DO UPDATE SET \
            a_matrix = EXCLUDED.a_matrix, \
            b_vector = EXCLUDED.b_vector, \
            context_dim = EXCLUDED.context_dim, \
            n_pulls = EXCLUDED.n_pulls, \
            feature_schema_hash = EXCLUDED.feature_schema_hash, \
            last_updated_ts = NOW()",
    )
    .bind(&state.arm_id)
    .bind(arm_space_version)
    .bind(&a_bytes)
    .bind(&b_bytes)
    .bind(dim)
    .bind(state.n_pulls)
    .bind(feature_schema_hash)
    .execute(pg)
    .await
    .map_err(|e| LinUcbIoError::Db(e.to_string()))?;

    Ok(())
}

/// Read the current active arm_space_version from the most recent migration row.
/// Defaults to "v1_15" if no migration has run yet. Read-only; never writes.
/// 從 learning.linucb_migrations 最新一筆讀取當前啟用的 arm_space_version。
/// 若無任何遷移記錄，預設 "v1_15"。純讀，不寫。
///
/// Used by 4-06 Card backend route to display the active version label.
/// 4-04 inference remains hardcoded v1_15; this helper is for monitoring only.
pub async fn current_active_version(pool: &DbPool) -> Result<String, LinUcbIoError> {
    let pg = pool.get().ok_or(LinUcbIoError::NoPool)?;
    let row: Option<(String,)> = sqlx::query_as(
        "SELECT to_version \
         FROM learning.linucb_migrations \
         ORDER BY migration_id DESC \
         LIMIT 1",
    )
    .fetch_optional(pg)
    .await
    .map_err(|e| LinUcbIoError::Db(e.to_string()))?;
    Ok(row.map(|(v,)| v).unwrap_or_else(default_active_version))
}

/// Pure helper: default arm_space_version when no migration has been logged.
/// Extracted for unit testing without a PG pool.
/// 純 helper：無遷移記錄時的預設版本。分離以便無 PG 單元測試。
pub fn default_active_version() -> String {
    "v1_15".to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_current_active_version_defaults_to_v1_15_when_no_migration() {
        // Contract: with no migration row, the active version is "v1_15".
        // 契約：無遷移記錄時，預設版本為 "v1_15"。
        assert_eq!(default_active_version(), "v1_15");
    }

    #[test]
    fn test_load_arms_schema_mismatch_fail_closed() {
        // Pure validation path (no PG required) — this is the same gate
        // load_arms invokes per row, so verifying it covers the fail-closed contract.
        // 純驗證路徑（無需 PG）— 這正是 load_arms 對每個 row 呼叫的同一閘門，
        // 覆蓋 fail-closed 契約。
        let res = validate_row_schema_hash(
            "trending__ma_crossover",
            "sha256:aaaaaaaaaaaaaaaa",
            "sha256:bbbbbbbbbbbbbbbb",
        );
        match res {
            Err(LinUcbIoError::SchemaMismatch {
                arm_id,
                expected,
                got,
            }) => {
                assert_eq!(arm_id, "trending__ma_crossover");
                assert_eq!(expected, "sha256:aaaaaaaaaaaaaaaa");
                assert_eq!(got, "sha256:bbbbbbbbbbbbbbbb");
            }
            other => panic!("expected SchemaMismatch, got {:?}", other),
        }
    }

    #[test]
    fn test_validate_row_schema_hash_match_ok() {
        let res =
            validate_row_schema_hash("a", "sha256:deadbeefdeadbeef", "sha256:deadbeefdeadbeef");
        assert!(res.is_ok());
    }

    #[test]
    fn test_f64_vec_roundtrip() {
        let v = vec![1.0_f64, -2.5, 3.14159, 0.0, 1e-12];
        let bytes = f64_vec_to_bytes(&v);
        assert_eq!(bytes.len(), v.len() * 8);
        let back = bytes_to_f64_vec(&bytes).unwrap();
        assert_eq!(v, back);
    }
}
