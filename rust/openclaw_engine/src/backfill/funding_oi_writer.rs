//! MODULE_NOTE
//! 模塊用途：funding rate / open interest 歷史回填的 DB 寫層 + V125 preflight probe。
//!   把 strict-parse 過的點寫 research.alpha_funding_rates_history /
//!   research.alpha_open_interest_history，並把 run-level + per-page provenance 寫
//!   research.alpha_history_ingest_runs / research.alpha_history_ingest_pages。
//! 主要類/函數：
//!   - probe_table_exists（V125 缺表 fail-closed，to_regclass）。
//!   - upsert_ingest_run / update_run_status（run-level 帳本）。
//!   - insert_ingest_page（per-page 帳本，append-only）。
//!   - write_funding_points_strict / write_oi_points_strict（history 表寫入，strict 值直接綁）。
//!   - utc_from_ms（ms→TIMESTAMPTZ，溢出 reject 不 epoch fallback）。
//! 依賴：DbPool（sqlx PgPool）、funding_oi_backfill::{FundingPoint, OiPoint, PageMeta, CoverageVerdict}、chrono。
//! 硬邊界：
//!   1. funding_rate / open_interest 是 V125 C-3 NOT NULL 欄；上游 strict_parse_* 已保證
//!      只傳 finite 值（含真 0.0 / 負 funding），writer 直接綁 DOUBLE PRECISION，
//!      絕不過 sanitize_f64_or_zero（不偽造 0.0）。
//!   2. INSERT ... ON CONFLICT DO NOTHING：history PK 含 run_id，重跑同 run 不產第二筆（冪等）；
//!      不同 run 保各自證據（lineage，不靜默覆蓋）。pages 帳本 append-only（PK run_id,page_id）。
//!   3. ts/funding_ts 由 ms parse；溢出 reject（不 epoch fallback，污染 PIT 窗口語義）。
//!   4. 純讀市場 + append 帳本，不下單/不餵 intent/不碰 auth/lease/cap。

use crate::backfill::funding_oi_backfill::{
    CoverageVerdict, FundingPoint, OiPoint, PageMeta,
};
use crate::database::pool::DbPool;
use chrono::{DateTime, Utc};

/// history 表一次寫入的結果統計。
#[derive(Debug, Clone, Default, PartialEq)]
pub struct WriteSummary {
    /// 嘗試綁定的點數（= strict 通過的 observed）。
    pub attempted: u64,
    /// 實際 INSERT 影響行數（ON CONFLICT DO NOTHING 後新增的；已存在不計）。
    pub inserted: u64,
}

/// run-level 帳本一筆（對映 research.alpha_history_ingest_runs）。
#[derive(Debug, Clone)]
pub struct IngestRun {
    pub run_id: String,
    pub program: String,
    pub storage_branch: Option<String>,
    pub window_start_ms: u64,
    pub window_end_ms: u64,
    pub git_sha: Option<String>,
    pub git_dirty: Option<bool>,
}

/// per-page 帳本一筆（對映 research.alpha_history_ingest_pages）。
#[derive(Debug, Clone)]
pub struct IngestPage {
    pub run_id: String,
    /// deterministic page key（endpoint+symbol+interval+window+cursor+seq）。
    pub page_id: String,
    pub endpoint_id: String,
    pub category: String,
    pub symbol: String,
    pub timeframe_or_period: String,
    pub request_start_ms: Option<u64>,
    pub request_end_ms: Option<u64>,
    pub cursor_in: Option<String>,
    pub cursor_out: Option<String>,
    pub ret_code: Option<i32>,
    pub raw_count: u64,
    pub parser_version: String,
}

/// 把毫秒時間戳轉 TIMESTAMPTZ；非法（溢出）回 None。
/// 為什麼不 unwrap_or_default：default 會落 1970 epoch，污染 PIT 窗口語意 → 必須 None。
fn utc_from_ms(ms: u64) -> Option<DateTime<Utc>> {
    DateTime::<Utc>::from_timestamp_millis(ms as i64)
}

/// V125 preflight：探測 research.<table> 是否存在（缺表即 fail-closed）。
///
/// 為什麼 fail-closed：V125 尚未 apply 時 history/ledger 表不存在，若仍寫會產生「無來源帳」
/// 或寫入失敗的半截狀態（root principle #8 違反）。用 to_regclass（不存在回 NULL，不拋例外）。
pub async fn probe_table_exists(pool: &DbPool, table: &str) -> Result<bool, sqlx::Error> {
    let Some(pg) = pool.get() else {
        return Ok(false);
    };
    let qualified = format!("research.{table}");
    let row: Option<Option<String>> = sqlx::query_scalar("SELECT to_regclass($1)::text")
        .bind(&qualified)
        .fetch_optional(pg)
        .await?;
    Ok(matches!(row, Some(Some(_))))
}

/// upsert run-level 帳本（狀態 'running'）。重跑同 run_id 不覆蓋既有（ON CONFLICT DO NOTHING）。
pub async fn upsert_ingest_run(pool: &DbPool, run: &IngestRun) -> Result<u64, sqlx::Error> {
    let Some(pg) = pool.get() else {
        return Ok(0);
    };
    let window_start = utc_from_ms(run.window_start_ms);
    let window_end = utc_from_ms(run.window_end_ms);
    let result = sqlx::query(
        "INSERT INTO research.alpha_history_ingest_runs \
            (run_id, program, storage_branch, window_start, window_end, \
             git_sha, git_dirty, status) \
         VALUES ($1, $2, $3, $4, $5, $6, $7, 'running') \
         ON CONFLICT (run_id) DO NOTHING",
    )
    .bind(&run.run_id)
    .bind(&run.program)
    .bind(run.storage_branch.as_deref())
    .bind(window_start)
    .bind(window_end)
    .bind(run.git_sha.as_deref())
    .bind(run.git_dirty)
    .execute(pg)
    .await?;
    Ok(result.rows_affected())
}

/// 把 run 標為終態（'accepted' / 'failed' / ...）+ completed_at=now()。
pub async fn update_run_status(
    pool: &DbPool,
    run_id: &str,
    status: &str,
) -> Result<u64, sqlx::Error> {
    let Some(pg) = pool.get() else {
        return Ok(0);
    };
    let result = sqlx::query(
        "UPDATE research.alpha_history_ingest_runs \
         SET status = $2, completed_at = now() \
         WHERE run_id = $1",
    )
    .bind(run_id)
    .bind(status)
    .execute(pg)
    .await?;
    Ok(result.rows_affected())
}

/// 插入一筆 per-page 帳本（append-only）。coverage_status/expected/observed 由 verdict 帶。
pub async fn insert_ingest_page(
    pool: &DbPool,
    page: &IngestPage,
    verdict: &CoverageVerdict,
) -> Result<u64, sqlx::Error> {
    let Some(pg) = pool.get() else {
        return Ok(0);
    };
    let request_start = page.request_start_ms.and_then(utc_from_ms);
    let request_end = page.request_end_ms.and_then(utc_from_ms);
    let coverage_pct: Option<f64> = if verdict.expected == 0 {
        None
    } else {
        Some(verdict.observed as f64 / verdict.expected as f64)
    };
    let result = sqlx::query(
        "INSERT INTO research.alpha_history_ingest_pages \
            (run_id, page_id, endpoint_id, category, symbol, timeframe_or_period, \
             request_start, request_end, cursor_in, cursor_out, ret_code, \
             payload_sha256, expected_rows, observed_rows, coverage_pct, coverage_status, \
             fetched_at, parser_version) \
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, now(), $17) \
         ON CONFLICT (run_id, page_id) DO NOTHING",
    )
    .bind(&page.run_id)
    .bind(&page.page_id)
    .bind(&page.endpoint_id)
    .bind(&page.category)
    .bind(&page.symbol)
    .bind(&page.timeframe_or_period)
    .bind(request_start)
    .bind(request_end)
    .bind(page.cursor_in.as_deref())
    .bind(page.cursor_out.as_deref())
    .bind(page.ret_code)
    .bind(&verdict.payload_sha256)
    .bind(verdict.expected as i64)
    .bind(verdict.observed as i64)
    .bind(coverage_pct)
    .bind(verdict.status.as_db_str())
    .bind(&page.parser_version)
    .execute(pg)
    .await?;
    Ok(result.rows_affected())
}

/// funding history 寫入所需的 row-level 共用欄位（不隨每筆變）。
#[derive(Debug, Clone)]
pub struct FundingWriteCtx {
    pub run_id: String,
    pub category: String,
    pub symbol: String,
    pub source_endpoint: String,
    pub request_start_ms: Option<u64>,
    pub request_end_ms: Option<u64>,
    pub parser_version: String,
    pub payload_sha256: String,
    /// funding 結算間隔（分鐘，選；來自 instruments-info fundingInterval — 是 interval 非 cap）。
    pub funding_interval_minutes: Option<i32>,
}

/// 把一批 strict-parse 過的 FundingPoint 寫 research.alpha_funding_rates_history。
///
/// 不變量（由 strict_parse_funding_list 保證）：每點 funding_rate 為 finite（含真 0.0 / 負），
/// 直接綁 DOUBLE PRECISION（C-3 NOT NULL 欄），絕不過 sanitize_f64_or_zero。
pub async fn write_funding_points_strict(
    pool: &DbPool,
    ctx: &FundingWriteCtx,
    points: &[FundingPoint],
) -> Result<WriteSummary, sqlx::Error> {
    let Some(pg) = pool.get() else {
        return Ok(WriteSummary::default());
    };
    let mut summary = WriteSummary::default();
    let mut tx = pg.begin().await?;
    let request_start = ctx.request_start_ms.and_then(utc_from_ms);
    let request_end = ctx.request_end_ms.and_then(utc_from_ms);

    for p in points {
        let Some(funding_ts) = utc_from_ms(p.funding_ts_ms) else {
            // ts 溢出（理論不可達，strict 已過濾）：跳過不寫，不偽造時間。
            continue;
        };
        summary.attempted += 1;
        let result = sqlx::query(
            "INSERT INTO research.alpha_funding_rates_history \
                (run_id, category, symbol, funding_ts, funding_rate, funding_interval_minutes, \
                 source_endpoint, request_start, request_end, fetched_at, parser_version, payload_sha256) \
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now(), $10, $11) \
             ON CONFLICT (category, symbol, funding_ts, run_id) DO NOTHING",
        )
        .bind(&ctx.run_id)
        .bind(&ctx.category)
        .bind(&ctx.symbol)
        .bind(funding_ts)
        // funding_rate：strict finite 值直接綁（含 0.0 / 負）；不 sanitize。
        .bind(p.funding_rate)
        .bind(ctx.funding_interval_minutes)
        .bind(&ctx.source_endpoint)
        .bind(request_start)
        .bind(request_end)
        .bind(&ctx.parser_version)
        .bind(&ctx.payload_sha256)
        .execute(&mut *tx)
        .await?;
        summary.inserted += result.rows_affected();
    }
    tx.commit().await?;
    Ok(summary)
}

/// OI history 寫入所需的 row-level 共用欄位。
#[derive(Debug, Clone)]
pub struct OiWriteCtx {
    pub run_id: String,
    pub category: String,
    pub symbol: String,
    pub interval_time: String,
    pub source_endpoint: String,
    pub request_start_ms: Option<u64>,
    pub request_end_ms: Option<u64>,
    pub parser_version: String,
    pub payload_sha256: String,
    /// nextPageCursor 鏈（落 cursor_lineage；以 '>' 串接，缺則 None）。
    pub cursor_lineage: Option<String>,
}

/// 把一批 strict-parse 過的 OiPoint 寫 research.alpha_open_interest_history。
///
/// 不變量（由 strict_parse_oi_list 保證）：每點 open_interest 為 finite，直接綁 DOUBLE PRECISION
/// （C-3 NOT NULL 欄），絕不過 sanitize_f64_or_zero。
pub async fn write_oi_points_strict(
    pool: &DbPool,
    ctx: &OiWriteCtx,
    points: &[OiPoint],
) -> Result<WriteSummary, sqlx::Error> {
    let Some(pg) = pool.get() else {
        return Ok(WriteSummary::default());
    };
    let mut summary = WriteSummary::default();
    let mut tx = pg.begin().await?;
    let request_start = ctx.request_start_ms.and_then(utc_from_ms);
    let request_end = ctx.request_end_ms.and_then(utc_from_ms);

    for p in points {
        let Some(ts) = utc_from_ms(p.ts_ms) else {
            continue;
        };
        summary.attempted += 1;
        let result = sqlx::query(
            "INSERT INTO research.alpha_open_interest_history \
                (run_id, category, symbol, interval_time, ts, open_interest, \
                 source_endpoint, request_start, request_end, cursor_lineage, fetched_at, \
                 parser_version, payload_sha256) \
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, now(), $11, $12) \
             ON CONFLICT (category, symbol, interval_time, ts, run_id) DO NOTHING",
        )
        .bind(&ctx.run_id)
        .bind(&ctx.category)
        .bind(&ctx.symbol)
        .bind(&ctx.interval_time)
        .bind(ts)
        // open_interest：strict finite 值直接綁；不 sanitize。
        .bind(p.open_interest)
        .bind(&ctx.source_endpoint)
        .bind(request_start)
        .bind(request_end)
        .bind(ctx.cursor_lineage.as_deref())
        .bind(&ctx.parser_version)
        .bind(&ctx.payload_sha256)
        .execute(&mut *tx)
        .await?;
        summary.inserted += result.rows_affected();
    }
    tx.commit().await?;
    Ok(summary)
}

/// 由 PageMeta 組裝 page_id（deterministic：endpoint+symbol+interval+window+cursor+seq）。
/// 為什麼 deterministic：同一 run 重跑時 page_id 須穩定，ON CONFLICT DO NOTHING 才能冪等。
pub fn build_page_id(
    endpoint_id: &str,
    symbol: &str,
    timeframe_or_period: &str,
    meta: &PageMeta,
) -> String {
    format!(
        "{endpoint_id}|{symbol}|{timeframe_or_period}|end={}|seq={}|cur={}",
        meta.request_end_ms,
        meta.seq,
        meta.cursor_in.as_deref().unwrap_or("-"),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_utc_from_ms_valid_and_zero() {
        assert!(utc_from_ms(1_700_000_000_000).is_some());
        // 0 是合法 epoch（非溢出）；strict ts 層才擋 0，此處只擋溢出。
        assert!(utc_from_ms(0).is_some());
    }

    #[test]
    fn test_build_page_id_deterministic() {
        let meta = PageMeta {
            seq: 2,
            request_end_ms: 1_700_000_000_000,
            request_start_ms: 1_600_000_000_000,
            cursor_in: Some("cur1".to_string()),
            cursor_out: None,
            ret_code: 0,
            raw_count: 200,
        };
        let a = build_page_id("GET /v5/market/open-interest", "BTCUSDT", "1h", &meta);
        let b = build_page_id("GET /v5/market/open-interest", "BTCUSDT", "1h", &meta);
        assert_eq!(a, b, "同輸入 page_id 必穩定（冪等前提）");
        assert!(a.contains("BTCUSDT"));
        assert!(a.contains("seq=2"));
        assert!(a.contains("cur=cur1"));
    }

    #[test]
    fn test_build_page_id_no_cursor_uses_dash() {
        let meta = PageMeta {
            seq: 0,
            request_end_ms: 1_700_000_000_000,
            request_start_ms: 1_600_000_000_000,
            cursor_in: None,
            cursor_out: None,
            ret_code: 0,
            raw_count: 5,
        };
        let id = build_page_id("GET /v5/market/funding/history", "ETHUSDT", "funding", &meta);
        assert!(id.contains("cur=-"), "無 cursor 時用 '-' 佔位（funding 無 cursor）");
    }

    /// coverage_pct 推算分支（DB 寫入需 Linux PG，此處驗算式）。
    #[test]
    fn test_coverage_pct_branch() {
        let pct = |expected: u64, observed: u64| -> Option<f64> {
            if expected == 0 {
                None
            } else {
                Some(observed as f64 / expected as f64)
            }
        };
        assert_eq!(pct(0, 0), None);
        assert_eq!(pct(200, 100), Some(0.5));
        assert_eq!(pct(3, 3), Some(1.0));
    }
}
