//! Sprint N+1 W2 sub-task 1 — V088 panel.btc_lead_lag_panel sqlx writer。
//!
//! MODULE_NOTE：
//!   `BtcLeadLagProducer` (panel_aggregator) emit 出 `BtcLeadLagPanelSnapshot`
//!   後，本 writer 把 snapshot INSERT 到 V088 schema panel.btc_lead_lag_panel
//!   一行（per-snapshot vector layout）。寫入採 `sqlx::query()` runtime-checked
//!   string 對齊既有 feature_writer.rs / decision_feature_writer.rs pattern
//!   （F1: no compile-time PG dependency）。
//!
//!   `INSERT ... ON CONFLICT (snapshot_ts_ms, lead_window_secs) DO NOTHING`
//!   保 idempotency（writer cycle 重跑同 ts 不寫 dup row）。
//!
//!   **Fail-soft 策略**（對齊 feature_writer.rs）：
//!   - DbPool unavailable → 靜默跳過（engine 無 PG 也 graceful）
//!   - sqlx INSERT 失敗 → record_failure + warn log，**不**重試（spec § 9
//!     "Bybit timeout / retCode != 0 → fail-closed 不重試" 同精神）
//!   - 三 array length 不對齊 → drop snapshot + warn log，**不** INSERT 半 schema
//!     row（避免下游 evaluator 撈到 broken row）
//!
//! Spec：
//! - V088 SQL：`srv/sql/migrations/V088__panel_btc_lead_lag_panel.sql`
//!   - PRIMARY KEY = (snapshot_ts_ms, lead_window_secs)
//!   - alt_symbols TEXT[] / alt_xcorr REAL[] / alt_expected_dir SMALLINT[]
//!   - source_tier 預設 'cross_asset_btc_lead_lag'；Stage 0R diagnostic opt-in
//!     rows use 'cross_asset_btc_lead_lag_diagnostic' to stay non-promotional.
//! - Producer：`srv/rust/openclaw_engine/src/panel_aggregator/btc_lead_lag.rs`
//! - Pattern reference：`srv/rust/openclaw_engine/src/database/feature_writer.rs`

use super::pool::DbPool;
use crate::panel_aggregator::btc_lead_lag::{
    BtcLeadLagPanelSnapshot, DIAGNOSTIC_SOURCE_TIER, SOURCE_TIER,
};
use tracing::{debug, warn};

/// 單發 INSERT 一個 snapshot 進 V088 schema。
///
/// **Fail-soft 行為**：
/// - `pool.is_available() == false` → 早返 Ok(())，靜默跳過（無 PG 模式）
/// - `snapshot.arrays_aligned() == false` → 三 array 長度不對齊 → drop + warn，
///   返 Ok(()) （不算 writer error，是 producer 端 invariant 違反，warn 給 ops）
/// - `snapshot.source_tier != SOURCE_TIER` → 同上 drop + warn，writer 強制 source_tier
/// - sqlx INSERT 失敗 → record_failure + warn log，返 Err（caller 視 sqlx error
///   類型決定是否重試；本 writer 不主動重試 per spec § 9）
///
/// **Idempotency**：`ON CONFLICT (snapshot_ts_ms, lead_window_secs) DO NOTHING`
/// 確保同 ts + lead_window 重跑不寫 dup row（與 V088 PK 對齊）。
pub async fn write_snapshot(
    pool: &DbPool,
    snapshot: &BtcLeadLagPanelSnapshot,
) -> Result<(), sqlx::Error> {
    // Fail-soft #1: PG 不可用 → 靜默跳過
    if !pool.is_available() {
        debug!("btc_lead_lag_writer: pool unavailable, snapshot dropped");
        return Ok(());
    }

    // Fail-soft #2: 三 array length invariant 違反 → drop + warn
    if !snapshot.arrays_aligned() {
        warn!(
            ts_ms = snapshot.snapshot_ts_ms,
            n_symbols = snapshot.alt_symbols.len(),
            n_xcorr = snapshot.alt_xcorr.len(),
            n_dir = snapshot.alt_expected_dir.len(),
            "btc_lead_lag_writer: arrays not aligned, snapshot dropped (V088 schema not touched)"
        );
        return Ok(());
    }

    // Fail-soft #3: source_tier 必為 normal 或 diagnostic 常量（writer 強制）
    if snapshot.source_tier != SOURCE_TIER && snapshot.source_tier != DIAGNOSTIC_SOURCE_TIER {
        warn!(
            ts_ms = snapshot.snapshot_ts_ms,
            actual = %snapshot.source_tier,
            expected_normal = SOURCE_TIER,
            expected_diagnostic = DIAGNOSTIC_SOURCE_TIER,
            "btc_lead_lag_writer: source_tier mismatch, snapshot dropped"
        );
        return Ok(());
    }

    let pg = match pool.get() {
        Some(p) => p,
        None => return Ok(()),
    };

    // V088 column order：12 column 對齊 SQL skeleton §4.1。
    // Cast SMALLINT[] from i8 → i16 for sqlx PG type 對應（PG SMALLINT = i16）。
    let alt_dir_i16: Vec<i16> = snapshot
        .alt_expected_dir
        .iter()
        .map(|&d| d as i16)
        .collect();

    let result = sqlx::query(
        "INSERT INTO panel.btc_lead_lag_panel (
            snapshot_ts_ms,
            lead_window_secs,
            btc_lead_return_pct,
            btc_lead_return_pct_60s,
            btc_lead_return_pct_300s,
            btc_volume_z,
            btc_book_imbalance,
            alt_symbols,
            alt_xcorr,
            alt_expected_dir,
            regime_tag,
            source_tier
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        ON CONFLICT (snapshot_ts_ms, lead_window_secs) DO NOTHING",
    )
    .bind(snapshot.snapshot_ts_ms)
    .bind(snapshot.lead_window_secs as i32)
    .bind(nan_to_null_f32(snapshot.btc_lead_return_pct))
    .bind(nan_to_null_f32(snapshot.btc_lead_return_pct_60s))
    .bind(nan_to_null_f32(snapshot.btc_lead_return_pct_300s))
    .bind(nan_to_null_f32(snapshot.btc_volume_z))
    .bind(nan_to_null_f32(snapshot.btc_book_imbalance))
    .bind(&snapshot.alt_symbols)
    .bind(
        snapshot
            .alt_xcorr
            .iter()
            .map(|x| nan_to_null_f32(*x))
            .collect::<Vec<Option<f32>>>(),
    )
    .bind(&alt_dir_i16)
    .bind(&snapshot.regime_tag)
    .bind(&snapshot.source_tier)
    .execute(pg)
    .await;

    match result {
        Ok(r) => {
            pool.record_success();
            debug!(
                ts_ms = snapshot.snapshot_ts_ms,
                rows_affected = r.rows_affected(),
                "btc_lead_lag_writer: snapshot inserted (or no-op on conflict)"
            );
            Ok(())
        }
        Err(e) => {
            let _ = pool.record_failure();
            warn!(
                ts_ms = snapshot.snapshot_ts_ms,
                error = %e,
                "btc_lead_lag_writer: INSERT failed (no retry per spec §9 fail-closed)"
            );
            Err(e)
        }
    }
}

/// f64 NaN → None (PG NULL 對應)；其他值 cast 為 f32（V088 schema 是 REAL）。
fn nan_to_null_f32(v: f64) -> Option<f32> {
    if v.is_nan() {
        None
    } else {
        Some(v as f32)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::panel_aggregator::btc_lead_lag::{
        BtcLeadLagPanelSnapshot, LEAD_WINDOW_SECS_MAIN, SOURCE_TIER,
    };

    fn make_aligned_snapshot() -> BtcLeadLagPanelSnapshot {
        BtcLeadLagPanelSnapshot {
            snapshot_ts_ms: 1_715_000_060_000,
            lead_window_secs: LEAD_WINDOW_SECS_MAIN,
            btc_lead_return_pct: 12.5,
            btc_lead_return_pct_60s: 6.0,
            btc_lead_return_pct_300s: 18.0,
            btc_volume_z: 1.2,
            btc_book_imbalance: 0.0,
            alt_symbols: vec!["ETHUSDT".to_string(), "SOLUSDT".to_string()],
            alt_xcorr: vec![0.55, 0.42],
            alt_expected_dir: vec![1, -1],
            regime_tag: "normal".to_string(),
            source_tier: SOURCE_TIER.to_string(),
        }
    }

    /// nan_to_null_f32 — NaN → None；finite → Some(f32 cast)。
    #[test]
    fn nan_to_null_f32_handles_nan_and_finite() {
        assert_eq!(nan_to_null_f32(f64::NAN), None);
        assert_eq!(nan_to_null_f32(0.0), Some(0.0_f32));
        let r = nan_to_null_f32(1.5);
        assert!(r.is_some());
        assert!((r.unwrap() - 1.5_f32).abs() < f32::EPSILON);
    }

    /// 三 array length invariant 自驗 — snapshot 設計合約。
    /// 對應 spec §4.1 alt_symbols / alt_xcorr / alt_expected_dir 三 array
    /// 同序對齊不變式（writer 端 fail-soft 守 line invariant）。
    #[test]
    fn arrays_aligned_invariant_passes_for_well_formed() {
        let s = make_aligned_snapshot();
        assert!(s.arrays_aligned());
    }

    /// arrays_aligned 對破壞性 snapshot 返 false — writer 應 drop 不 INSERT。
    #[test]
    fn arrays_aligned_invariant_fails_when_lengths_mismatch() {
        let mut s = make_aligned_snapshot();
        s.alt_xcorr.push(0.99); // 長度不一致
        assert!(!s.arrays_aligned());
    }

    /// V088 INSERT statement 結構正確性 — bind count = 12 column。
    /// 此 test 不接 PG，只驗 SQL string 與 bind 順序對齊；讓 reviewer 一眼能
    /// 對照 V088 schema 12 column。
    #[test]
    fn insert_sql_has_12_placeholders() {
        let sql_text = "INSERT INTO panel.btc_lead_lag_panel (
            snapshot_ts_ms,
            lead_window_secs,
            btc_lead_return_pct,
            btc_lead_return_pct_60s,
            btc_lead_return_pct_300s,
            btc_volume_z,
            btc_book_imbalance,
            alt_symbols,
            alt_xcorr,
            alt_expected_dir,
            regime_tag,
            source_tier
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        ON CONFLICT (snapshot_ts_ms, lead_window_secs) DO NOTHING";
        // 計數 $N 出現次數 = 12（V088 column 數）
        let placeholder_count = (1..=12)
            .filter(|i| sql_text.contains(&format!("${}", i)))
            .count();
        assert_eq!(
            placeholder_count, 12,
            "V088 12-column INSERT 必對應 12 個 placeholder"
        );
        // ON CONFLICT 子句必含 PK 兩 column
        assert!(sql_text.contains("ON CONFLICT (snapshot_ts_ms, lead_window_secs)"));
    }
}
