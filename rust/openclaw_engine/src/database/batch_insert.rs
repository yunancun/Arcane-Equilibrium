//! Unified batch / single INSERT helpers — PG 65535 parameter guard + fail-soft counter.
//! 統一批量 / 單行 INSERT 輔助 — PG 65535 參數上限防護 + 失敗軟計數。
//!
//! MODULE_NOTE (EN): PostgreSQL binds at most 65535 parameters per statement. Writers
//!   that `push_values` a large buffer risk hitting this limit silently as column
//!   counts grow (e.g. V017 added `entry_context_id` to trading.fills). This module
//!   centralizes the `chunk_rows` math (`65535 / columns_per_row`, clamped to
//!   [1, 10000]) and the QueryBuilder driver so every writer applies the same
//!   guardrail without copy-pasting the constant. Per-writer semantics (epoch-0
//!   rejection, JSONB parsing, engine_mode CHECK, HashMap dedup, 3-failure JSONL
//!   fallback) stay in the writer — `batch_insert` only sees a clean `&[T]`.
//! MODULE_NOTE (中): PG 單語句最多綁定 65535 個參數。Writer 以 `push_values` 推入
//!   大批資料時，列數增加（如 V017 為 trading.fills 加入 entry_context_id）可能靜默
//!   觸頂。本模組集中 `chunk_rows` 數學（`65535 / columns_per_row`，夾在 [1, 10000]）
//!   與 QueryBuilder 驅動，讓每個 writer 共用同一道防線。Writer 的語意（拒絕
//!   epoch-0、JSONB 解析、engine_mode CHECK、HashMap 去重、連續 3 次失敗改走 JSONL）
//!   仍保留於 writer 內 — `batch_insert` 只看乾淨的 `&[T]`。
//!
//! Risk budget (FA-2 refactor spec):
//!   1. `market_writer.rs` ticker buffer: 13 cols × 5000 rows = 65000 params — too
//!      close to the hard cap. The ticker path now calls this helper with
//!      `columns_per_row = 13`, which yields `chunk_rows = 5041` then clamps to
//!      10000 … we also impose an explicit `max_chunk_rows_override` of 4000 in
//!      `market_writer` to keep headroom.
//!   2. Per-row validation stays in the writer: epoch-0 check, JSONB parse, and
//!      engine_mode guard are heterogeneous across writers and must not be lifted.
//!   3. HashMap dedup ownership stays in the writer (context / feature / shadow
//!      writers) — this helper takes `&[T]` only.
//!   4. Error semantics preserved: fail-soft via `DbPool::record_failure()`, no
//!      retry, no panic. Market writer's 3-consecutive-failure JSONL fallback is
//!      untouched — the helper only reports whether the batch succeeded.
//!   5. No transaction wrapping: current writers do not wrap batches in
//!      BEGIN/COMMIT, so neither does this helper.
//!
//! 風險預算（FA-2 重構規格）：
//!   1. `market_writer.rs` ticker：13 欄 × 5000 行 = 65000 參數，距上限極近。
//!      ticker 路徑現呼叫本 helper 並以 `columns_per_row = 13` 計算（結果 5041
//!      再夾到 10000），同時在 market_writer 施加 `max_chunk_rows_override=4000`
//!      保留餘量。
//!   2. 每行驗證留在 writer：epoch-0 檢查、JSONB 解析、engine_mode 守衛各不相同，
//!      不得抽到共用路徑。
//!   3. HashMap 去重所有權仍在 writer（context / feature / shadow）— 本 helper
//!      僅吃 `&[T]`。
//!   4. 錯誤語意保留：失敗軟處理透過 `DbPool::record_failure()`，無重試、無 panic；
//!      market_writer 的連續 3 次失敗 JSONL 回退路徑原樣保留。
//!   5. 不包 transaction：目前各 writer 均未包 BEGIN/COMMIT，本 helper 不改變此約定。

use super::pool::DbPool;
use sqlx::{PgPool, Postgres, QueryBuilder};
use tracing::{debug, warn};

/// Hard upper limit on PostgreSQL bind parameters per statement.
/// PostgreSQL 單語句綁定參數硬上限。
pub const PG_MAX_PARAMS: usize = 65535;

/// Pragmatic per-chunk row cap — even when the math permits more, we stop here
/// to keep a single query's plan time and memory footprint bounded. Matches the
/// former `SIGNAL_BATCH_MAX` style constants (~5k range, 10k ceiling).
/// 實用的分塊行數上限 — 即使數學容許更多，也在此停止以限制單查詢規劃時間與記憶體。
pub const MAX_CHUNK_ROWS: usize = 10_000;

/// Compute chunk rows for a given column count so that
/// `chunk_rows * columns_per_row ≤ 65535`, clamped to `[1, MAX_CHUNK_ROWS]`.
/// 依欄位數計算分塊行數，保證 `chunk_rows * columns_per_row ≤ 65535`，
/// 夾在 `[1, MAX_CHUNK_ROWS]`。
///
/// * `columns_per_row == 0` → treated as 1 (degenerate; caller bug, but we stay
///   fail-soft).
/// * `columns_per_row > PG_MAX_PARAMS` → returns 1 (one row at a time — the
///   schema is already over-wide and sqlx will still fail, but this keeps the
///   helper total).
/// * 一般情況：`min(PG_MAX_PARAMS / columns_per_row, MAX_CHUNK_ROWS)`。
#[inline]
pub fn chunk_rows_for_columns(columns_per_row: usize) -> usize {
    let cpr = columns_per_row.max(1);
    (PG_MAX_PARAMS / cpr).clamp(1, MAX_CHUNK_ROWS)
}

/// Apply an optional explicit cap on top of `chunk_rows_for_columns`.
/// 在 `chunk_rows_for_columns` 之上再套用一個可選的顯式上限。
///
/// Used by `market_writer.rs` for the ticker path where we want the chunk cap
/// well below the PG ceiling (4000 rows × 13 cols = 52000, leaves 13535 param
/// headroom for future column additions).
/// 市場 writer 的 ticker 路徑使用：明確把上限壓到 4000 行（× 13 欄 = 52000），
/// 保留 13535 參數裕度供未來欄位擴充。
#[inline]
pub fn chunk_rows_with_override(columns_per_row: usize, override_max: usize) -> usize {
    chunk_rows_for_columns(columns_per_row).min(override_max.max(1))
}

/// Chunked batch INSERT outcome.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BatchInsertOutcome {
    pub rows_affected: u64,
    pub failed_chunks: usize,
}

impl BatchInsertOutcome {
    pub fn all_ok(&self) -> bool {
        self.failed_chunks == 0
    }
}

/// Chunked batch INSERT driver.
/// 分塊批量 INSERT 驅動。
///
/// `build_chunk(chunk) -> QueryBuilder<'a, Postgres>` constructs a fully-built
/// `QueryBuilder` for one chunk (header + `push_values` + ON CONFLICT). Returning
/// the builder (rather than taking `&mut`) is the ergonomic shape that makes
/// borrow-checker happy: the QueryBuilder's lifetime is tied to the slice passed
/// in, which is strictly shorter than the driver's own stack frame.
///
/// The driver itself:
///   1. Picks `chunk_rows = chunk_rows_for_columns(columns_per_row)`;
///   2. Iterates `rows.chunks(chunk_rows)` and invokes `build_chunk` per chunk;
///   3. Executes each resulting query on `pg`;
///   4. Reports success / failure to `pool` via `record_success` / `record_failure`;
///   5. Returns the total `rows_affected` across all successful chunks.
///
/// Failures are logged at WARN via the supplied `table` label and are NOT
/// retried — the caller's writer observes failure through `pool.failure_count()`.
///
/// `build_chunk(chunk)` 為每段切片構造完整的 `QueryBuilder`（標頭 + push_values +
/// ON CONFLICT）。返回式（而非接受 `&mut`）避開 borrow-checker 的 QueryBuilder
/// 生命週期不變性問題。驅動本身：
///   1. 以 `chunk_rows_for_columns` 取分塊大小；
///   2. 逐段呼叫 `build_chunk`；
///   3. 在 `pg` 上執行；
///   4. 透過 `pool` 的 `record_success` / `record_failure` 回報；
///   5. 回傳所有成功段的 `rows_affected` 總和。
/// 失敗會 WARN log（帶 `table` 標籤）且**不**重試 — caller 以
/// `pool.failure_count()` 觀察健康狀態。
pub async fn batch_insert_chunked<T, F>(
    pg: &PgPool,
    pool: &DbPool,
    table: &str,
    rows: &[T],
    columns_per_row: usize,
    mut build_chunk: F,
) -> BatchInsertOutcome
where
    F: for<'a> FnMut(&'a [T]) -> QueryBuilder<'a, Postgres>,
{
    if rows.is_empty() {
        return BatchInsertOutcome {
            rows_affected: 0,
            failed_chunks: 0,
        };
    }
    let chunk_rows = chunk_rows_for_columns(columns_per_row);
    run_chunks(pg, pool, table, rows, chunk_rows, &mut build_chunk).await
}

/// Same as `batch_insert_chunked` but with an explicit chunk-row cap override.
/// Use for paths where the default ceiling is too aggressive (e.g. ticker buffer
/// in `market_writer.rs` — PG ceiling permits 5041, we want 4000).
/// 同 `batch_insert_chunked`，但額外套用顯式上限。用於想比 PG 硬上限更保守的路徑
/// （如 market_writer ticker — PG 允許 5041，我們壓到 4000）。
pub async fn batch_insert_chunked_with_override<T, F>(
    pg: &PgPool,
    pool: &DbPool,
    table: &str,
    rows: &[T],
    columns_per_row: usize,
    chunk_rows_override: usize,
    mut build_chunk: F,
) -> BatchInsertOutcome
where
    F: for<'a> FnMut(&'a [T]) -> QueryBuilder<'a, Postgres>,
{
    if rows.is_empty() {
        return BatchInsertOutcome {
            rows_affected: 0,
            failed_chunks: 0,
        };
    }
    let chunk_rows = chunk_rows_with_override(columns_per_row, chunk_rows_override);
    run_chunks(pg, pool, table, rows, chunk_rows, &mut build_chunk).await
}

/// Internal common loop — chunks, invokes builder, executes, bookkeeps.
/// 內部共用迴圈 — 分塊、叫 builder、執行、記帳。
async fn run_chunks<T, F>(
    pg: &PgPool,
    pool: &DbPool,
    table: &str,
    rows: &[T],
    chunk_rows: usize,
    build_chunk: &mut F,
) -> BatchInsertOutcome
where
    F: for<'a> FnMut(&'a [T]) -> QueryBuilder<'a, Postgres>,
{
    let mut total_affected: u64 = 0;
    let mut failed_chunks: usize = 0;
    for chunk in rows.chunks(chunk_rows) {
        let mut qb = build_chunk(chunk);
        match qb.build().execute(pg).await {
            Ok(r) => {
                pool.record_success();
                total_affected = total_affected.saturating_add(r.rows_affected());
                debug!(
                    table = table,
                    rows = r.rows_affected(),
                    chunk_size = chunk.len(),
                    "batch_insert flushed / 批量插入已刷新"
                );
            }
            Err(e) => {
                let _ = pool.record_failure();
                failed_chunks = failed_chunks.saturating_add(1);
                warn!(
                    table = table,
                    error = %e,
                    "batch_insert failed / 批量插入失敗"
                );
            }
        }
    }
    BatchInsertOutcome {
        rows_affected: total_affected,
        failed_chunks,
    }
}

/// Outcome tag for `exec_single_insert` — lets the caller decide whether to
/// log at debug / warn, emit a per-writer metric, or `continue` a loop.
/// `exec_single_insert` 的結果標籤 — 讓 caller 自行決定 log 級別、指標或 loop 流程。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SingleInsertOutcome {
    /// INSERT succeeded (rows_affected returned).
    /// INSERT 成功（附 rows_affected）。
    Ok(u64),
    /// INSERT failed (error already logged + counter already decremented).
    /// INSERT 失敗（已 log + 已減計數）。
    Failed,
    /// pool.get() returned None — PG unavailable. Writer should clear buffers.
    /// pool.get() 為 None — PG 不可用；writer 應清空緩衝。
    PoolUnavailable,
}

impl SingleInsertOutcome {
    /// `true` iff `Ok(_)`.
    pub fn is_ok(&self) -> bool {
        matches!(self, SingleInsertOutcome::Ok(_))
    }
}

/// Execute a single pre-built `sqlx::query::Query` with fail-soft counter update.
/// 執行已構建的單行 `sqlx::query::Query`，失敗軟處理並更新計數。
///
/// Signature note: we cannot generalize via `FnOnce() -> Query<...>` without
/// tripping over `Query`'s lifetime parameter at the use-site; callers pass an
/// already-bound query and we just execute + bookkeeping.
/// 簽名註：`Query<'_>` 的生命週期參數難以穿過 `FnOnce`，所以 caller 直接傳入
/// 已 bind 的 query；本 helper 只負責執行與計數維護。
pub async fn exec_single_insert(
    pool: &DbPool,
    table: &str,
    query: sqlx::query::Query<'_, Postgres, sqlx::postgres::PgArguments>,
) -> SingleInsertOutcome {
    let pg = match pool.get() {
        Some(p) => p,
        None => return SingleInsertOutcome::PoolUnavailable,
    };
    match query.execute(pg).await {
        Ok(r) => {
            pool.record_success();
            debug!(
                table = table,
                rows = r.rows_affected(),
                "single insert ok / 單行插入成功"
            );
            SingleInsertOutcome::Ok(r.rows_affected())
        }
        Err(e) => {
            let _ = pool.record_failure();
            warn!(
                table = table,
                error = %e,
                "single insert failed / 單行插入失敗"
            );
            SingleInsertOutcome::Failed
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn chunk_math_default_13_cols() {
        // Matches market_writer ticker shape: 13 cols → 5041 rows, clamped to 5041
        // (below MAX_CHUNK_ROWS). 13 × 5041 = 65533 ≤ 65535.
        // 13 欄 → 5041 行，未觸 MAX_CHUNK_ROWS；13 × 5041 = 65533 ≤ 65535。
        let rows = chunk_rows_for_columns(13);
        assert_eq!(rows, 5041);
        assert!(rows * 13 <= PG_MAX_PARAMS);
    }

    #[test]
    fn chunk_math_empty_input_yields_zero() {
        // Empty slice is rejected up-front by batch_insert_chunked; the math
        // helper itself is input-agnostic. Still: 0-row expectations hold.
        // 空切片由 batch_insert_chunked 直接退出；數學 helper 與輸入無關。
        let rows: Vec<i32> = Vec::new();
        let chunk_size = chunk_rows_for_columns(8);
        assert!(chunk_size >= 1);
        assert_eq!(rows.chunks(chunk_size).count(), 0);
    }

    #[test]
    fn chunk_math_pg_boundary_columns_20() {
        // 20 columns: 65535/20 = 3276 (floor). 3276 × 20 = 65520 ≤ 65535.
        // 20 欄：65535/20 = 3276（向下取整）。3276 × 20 = 65520 ≤ 65535。
        let rows = chunk_rows_for_columns(20);
        assert_eq!(rows, 3276);
        assert!(rows * 20 <= PG_MAX_PARAMS);
        assert!((rows + 1) * 20 > PG_MAX_PARAMS);
    }

    #[test]
    fn chunk_math_single_column_caps_at_max() {
        // 1 column → mathematically 65535 rows allowed, capped to MAX_CHUNK_ROWS.
        // 1 欄 → 數學上允許 65535 行，被 MAX_CHUNK_ROWS 截到 10_000。
        assert_eq!(chunk_rows_for_columns(1), MAX_CHUNK_ROWS);
    }

    #[test]
    fn chunk_math_extreme_column_count() {
        // columns_per_row == 65535 → exactly one row per batch.
        // columns_per_row == 65535 → 每批恰好 1 行。
        assert_eq!(chunk_rows_for_columns(PG_MAX_PARAMS), 1);
        // columns_per_row > 65535 (degenerate) → still 1.
        // 退化情況（> 65535）→ 仍為 1。
        assert_eq!(chunk_rows_for_columns(PG_MAX_PARAMS + 100), 1);
    }

    #[test]
    fn chunk_math_zero_columns_guard() {
        // Defensive: 0 columns is a caller bug. Treat as 1 column instead of
        // panicking with divide-by-zero.
        // 防禦：0 欄是 caller bug；視為 1 欄而非除零 panic。
        assert_eq!(chunk_rows_for_columns(0), MAX_CHUNK_ROWS);
    }

    #[test]
    fn chunk_math_override_caps_below_ceiling() {
        // 13 cols, override 4000 → min(5041, 4000) = 4000.
        // 13 欄、override 4000 → min(5041, 4000) = 4000。
        assert_eq!(chunk_rows_with_override(13, 4000), 4000);
        // override > natural ceiling → natural ceiling wins.
        // override 比自然上限大 → 取自然上限。
        assert_eq!(chunk_rows_with_override(13, 9999), 5041);
        // override == 0 → treated as 1 to avoid zero-step chunking.
        // override == 0 → 視為 1 以避免零步進。
        assert_eq!(chunk_rows_with_override(13, 0), 1);
    }

    #[test]
    fn chunk_math_market_writer_ticker_4000_safety() {
        // Explicit pinning of the market_writer invariant: 4000 × 13 leaves
        // headroom above a bare 65000 constant, well below 65535.
        // 鎖定 market_writer 不變式：4000 × 13 = 52000，遠低於 65535 且比原硬編碼
        // 65000 更安全。
        let rows = chunk_rows_with_override(13, 4000);
        assert_eq!(rows * 13, 52_000);
        assert!(rows * 13 + 13_535 == PG_MAX_PARAMS);
    }

    #[test]
    fn single_insert_outcome_is_ok() {
        assert!(SingleInsertOutcome::Ok(5).is_ok());
        assert!(!SingleInsertOutcome::Failed.is_ok());
        assert!(!SingleInsertOutcome::PoolUnavailable.is_ok());
    }

    #[test]
    fn batch_insert_outcome_all_ok_tracks_failed_chunks() {
        assert!(BatchInsertOutcome {
            rows_affected: 0,
            failed_chunks: 0,
        }
        .all_ok());
        assert!(!BatchInsertOutcome {
            rows_affected: 3,
            failed_chunks: 1,
        }
        .all_ok());
    }
}
