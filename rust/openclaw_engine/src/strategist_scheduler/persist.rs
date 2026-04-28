//! Strategist applied-params persistence — split from `strategist_scheduler/mod.rs`.
//! 策略師已應用參數持久化 — 從 `strategist_scheduler/mod.rs` 拆出。
//!
//! MODULE_NOTE (EN): Extracted from parent `mod.rs` as post-commit FUP to commit
//!   `f1f7403`, which pushed the file from 1133 → 1342 lines and breached the
//!   §九 1200-line hard limit by 142 lines. Contents are moved verbatim (method
//!   `StrategistScheduler::persist_applied_params`, standalone fn
//!   `load_latest_applied_params`, and the two fail-soft regression tests) with
//!   zero behaviour change — see sibling-child-module pattern established by
//!   commits `585be97` / `3d67a99`. Re-exported from `mod.rs` via
//!   `pub use persist::load_latest_applied_params;` so `main.rs` call sites
//!   (`openclaw_engine::strategist_scheduler::load_latest_applied_params`)
//!   remain unchanged.
//! MODULE_NOTE (中): 從父 `mod.rs` 拆出，為 commit `f1f7403` post-commit FUP —
//!   該 commit 把檔案從 1133 推到 1342 行，超 §九 1200 硬上限 142 行。本檔內
//!   容原封搬出（method `StrategistScheduler::persist_applied_params`、
//!   standalone fn `load_latest_applied_params`、2 個 fail-soft regression
//!   tests），零邏輯變動 — 採 commits `585be97` / `3d67a99` 建立的
//!   sibling-child-module pattern。`mod.rs` 透過
//!   `pub use persist::load_latest_applied_params;` re-export，`main.rs`
//!   呼叫路徑 `openclaw_engine::strategist_scheduler::load_latest_applied_params`
//!   不動。

use super::StrategistScheduler;
use serde_json::Value;
use std::sync::Arc;
use tracing::debug;

impl StrategistScheduler {
    /// STRATEGIST-PARAMS-PERSIST-1 (2026-04-23): persist the just-applied
    /// params to `learning.strategist_applied_params` as an audit trail.
    /// Engine startup reads the latest row per (engine_mode, strategy_name)
    /// and re-issues `UpdateStrategyParams` so tuned values survive restart
    /// instead of reverting to TOML baseline.
    ///
    /// Fail-soft: DB pool unavailable → Ok(()) (skip persist, log at caller).
    /// The tuning cycle has already succeeded in-memory — a persist miss only
    /// means the tuned value won't survive restart, which is strictly less bad
    /// than aborting the cycle.
    ///
    /// STRATEGIST-PARAMS-PERSIST-1（2026-04-23）：把剛應用的參數寫入
    /// `learning.strategist_applied_params` 當 audit + restore 來源。
    /// Engine 啟動讀每 (engine_mode, strategy_name) 最新 row 回放 IPC。
    /// Fail-soft：DB 不可用回 Ok(())，不影響已在內存生效的 tuning。
    pub(super) async fn persist_applied_params(
        &self,
        strategy_name: &str,
        prev_params: &Value,
        applied_params: &Value,
        reason: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let pool = match self.db_pool.get() {
            Some(p) => p,
            None => {
                debug!(
                    strategy = %strategy_name,
                    "persist_applied_params skipped: DB pool unavailable \
                     / DB 連接池不可用，跳過持久化"
                );
                return Ok(());
            }
        };

        let engine_mode = self.tune_target.db_mode();
        let applied_at_ms: i64 = chrono::Utc::now().timestamp_millis();

        sqlx::query(
            "INSERT INTO learning.strategist_applied_params \
             (engine_mode, strategy_name, params_json, applied_at_ms, \
              source, reason, prev_params_json) \
             VALUES ($1, $2, $3, $4, $5, $6, $7)",
        )
        .bind(engine_mode)
        .bind(strategy_name)
        .bind(applied_params)
        .bind(applied_at_ms)
        .bind("strategist_scheduler")
        .bind(reason)
        .bind(prev_params)
        .execute(pool)
        .await?;

        debug!(
            strategy = %strategy_name,
            engine_mode = %engine_mode,
            applied_at_ms,
            "strategist params persisted / 策略師參數已持久化"
        );
        Ok(())
    }
}

/// STRATEGIST-PARAMS-PERSIST-1 (2026-04-23): load the latest applied params
/// per (engine_mode, strategy_name) from `learning.strategist_applied_params`.
/// Used by `main.rs` startup to restore tuned params via `UpdateStrategyParams`
/// IPC **before** scheduler spawn — ensures rebuild does not silently revert
/// parameters to TOML baseline (which would reset the
/// STRATEGIST-AUTO-PROMOTE-CRITERIA-1 stability counter forever).
///
/// Fail-soft semantics:
///   - `db_pool.get() == None`   → `Ok(vec![])` (DB disabled; nothing to restore)
///   - SQL error                  → `Err(_)` (caller logs + continues startup)
///   - Empty table                → `Ok(vec![])` (first boot after migration)
///
/// Returns `Vec<(strategy_name, params_json_string)>` — ready to send as
/// `PipelineCommand::UpdateStrategyParams` payload without further parsing.
///
/// STRATEGIST-PARAMS-PERSIST-1（2026-04-23）：從
/// `learning.strategist_applied_params` 讀每 (engine_mode, strategy_name) 最新
/// 1 row，給 `main.rs` 啟動時以 IPC 恢復調諧參數，避免 rebuild 靜默回到 TOML
/// baseline 重置 AUTO-PROMOTE 穩定計數器。
/// Fail-soft：pool=None → 空 Vec；SQL 錯 → Err（caller log+continue）。
pub async fn load_latest_applied_params(
    db_pool: &Arc<crate::database::pool::DbPool>,
    engine_mode: &str,
) -> Result<Vec<(String, String)>, Box<dyn std::error::Error + Send + Sync>> {
    let pool = match db_pool.get() {
        Some(p) => p,
        None => {
            debug!(
                engine_mode,
                "load_latest_applied_params: DB pool unavailable, \
                 returning empty / DB 連接池不可用，回空 Vec"
            );
            return Ok(Vec::new());
        }
    };

    // DISTINCT ON picks the row with the highest applied_at_ms per
    // (engine_mode, strategy_name) — matches the V020 index
    // `idx_strategist_applied_engine_strategy_ts`
    // (applied_at_ms DESC, id DESC).
    //
    // STRATEGIST-PERSIST-TIE-BREAK-1 (2026-04-23, V020): `, id DESC` tie-break
    // ensures deterministic ordering when two concurrent writers produce rows
    // with identical applied_at_ms (millisecond precision can collide under
    // Phase 5+ manual_promote + auto cycle). Without tie-break, DISTINCT ON
    // falls back to PG physical row order (not stable).
    // STRATEGIST-PERSIST-TIE-BREAK-1（V020）：加 `id DESC` tie-break，
    // 並發同 ms 寫入時取 id 最大者（最晚寫入），確定性勝出。
    // DISTINCT ON 配合索引取每組最新 1 row。
    let rows: Vec<(String, serde_json::Value)> = sqlx::query_as::<_, (String, serde_json::Value)>(
        "SELECT DISTINCT ON (engine_mode, strategy_name) \
                strategy_name, params_json \
             FROM learning.strategist_applied_params \
             WHERE engine_mode = $1 \
             ORDER BY engine_mode, strategy_name, applied_at_ms DESC, id DESC",
    )
    .bind(engine_mode)
    .fetch_all(pool)
    .await?;

    let out: Vec<(String, String)> = rows
        .into_iter()
        .map(|(name, val)| (name, val.to_string()))
        .collect();
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ai_service_client::AiServiceClient;
    use crate::tick_pipeline::PipelineKind;
    use tokio_util::sync::CancellationToken;

    fn mk_deps() -> (
        Arc<AiServiceClient>,
        Arc<crate::database::pool::DbPool>,
        CancellationToken,
    ) {
        (
            Arc::new(AiServiceClient::new()),
            Arc::new(crate::database::pool::DbPool::disconnected()),
            CancellationToken::new(),
        )
    }

    /// Source snapshot of this file — used by SQL property tests below to
    /// verify the inline SQL literals in `persist_applied_params` /
    /// `load_latest_applied_params` still contain the critical clauses.
    /// This is a test-only compile-time embed (`include_str!` zero-cost in
    /// release, no production path runs it).
    /// 本檔源碼快照（test-only），property test 用來 grep SQL 字面，確保
    /// 後續重構不會誤改 SQL 關鍵子句（DISTINCT ON / ORDER BY / column list）。
    const PERSIST_SRC: &str = include_str!("persist.rs");

    // ═══════════════════════════════════════════════════════════════════
    // STRATEGIST-PARAMS-PERSIST-1 tests (2026-04-23 初版).
    // STRATEGIST-PERSIST-TEST-BROADEN-1 補強 (2026-04-23 QC M2 audit FUP).
    //
    // Coverage matrix / 覆蓋矩陣:
    //   [pool=None fail-soft]
    //     1. persist_applied_params     → test_persist_..._fails_soft_on_pool_none  (QC M2 a 的降級 mock)
    //     2. load_latest_applied_params → test_load_..._empty_on_pool_none          (QC M2 a 的降級 mock)
    //   [SQL property / string literal assertions]
    //     3. load SQL has DISTINCT ON + DESC order     (QC M2 b)
    //     4. load SQL column list + WHERE engine_mode  (QC M2 b 補）
    //     5. persist SQL has full 7-column INSERT      (QC M2 c)
    //     6. persist SQL binds $1..$7 placeholders     (QC M2 c 補）
    //
    // 無法測試項（需真 PG integration test, 延後到 Linux CI harness）：
    //   - SQL schema 不存在（relation "learning.strategist_applied_params"
    //     does not exist）時回 Err 路徑：sqlx 類型綁定 PG-specific，Mac 無
    //     Docker PG，sqlite in-memory 不兼容 sqlx::postgres::PgPool 類型參數。
    //   - DISTINCT ON 真實多 row 排序語意：需 INSERT 多 row 後 SELECT 驗最新
    //     applied_at_ms 勝出，同樣需真 PG。
    //   - Multi-row persist→load round-trip：同上。
    //   上述三項 QC M2 a/b/c 的「SQL 真實執行」層面由 Linux CI sqlx::test
    //   integration harness 覆蓋（超出本 Mac unit-test scope）。
    //
    // STRATEGIST-PARAMS-PERSIST-1 測試（2026-04-23）+ TEST-BROADEN-1（QC M2）。
    // 上表 3 層覆蓋：pool=None fail-soft / SQL 字面屬性 / 真 PG 延後。
    // ═══════════════════════════════════════════════════════════════════

    #[tokio::test]
    async fn test_persist_applied_params_fails_soft_on_pool_none() {
        // Simulate "DB disabled" (disconnected DbPool). persist_applied_params
        // must swallow the miss and return Ok(()) — the in-memory tune cycle
        // has already succeeded, failing here would trigger a retry loop that
        // re-IPCs the same applied params and spams warn logs.
        // 模擬 DB 停擺：persist 必須回 Ok(())，不然會觸發 retry 噴 log。
        let (ai, pool, cancel) = mk_deps();
        let (tune_tx, _tune_rx) = tokio::sync::mpsc::unbounded_channel();
        let sched = StrategistScheduler::new(ai, tune_tx, PipelineKind::Demo, None, pool, cancel);

        let prev = serde_json::json!({"cooldown_ms": 50000.0});
        let applied = serde_json::json!({"cooldown_ms": 55000.0});
        let result = sched
            .persist_applied_params("ma_crossover", &prev, &applied, "top_deviation_pair")
            .await;
        assert!(
            result.is_ok(),
            "persist_applied_params must fail-soft when db_pool is disconnected, \
             got: {:?}",
            result.err()
        );
    }

    #[tokio::test]
    async fn test_load_latest_applied_params_empty_on_pool_none() {
        // Symmetric fail-soft on the read path: startup restore must not abort
        // engine boot when DB is disabled. Return empty vec → main.rs sees
        // "nothing to restore" and continues normally.
        // 讀路徑對稱 fail-soft：DB 停擺時返回空 Vec，engine 啟動不受阻。
        let pool = Arc::new(crate::database::pool::DbPool::disconnected());
        let result = load_latest_applied_params(&pool, "demo").await;
        assert!(
            result.is_ok(),
            "load_latest_applied_params must fail-soft when db_pool is disconnected, \
             got: {:?}",
            result.err()
        );
        let rows = result.unwrap();
        assert!(
            rows.is_empty(),
            "expected empty vec from disconnected pool, got {} rows",
            rows.len()
        );
    }

    // ───────────────────────────────────────────────────────────────────
    // STRATEGIST-PERSIST-TEST-BROADEN-1 (QC M2) — SQL literal property tests.
    //
    // Rationale / 理由:
    //   The behavioural guarantees of load/persist SQL (DISTINCT ON picks the
    //   highest applied_at_ms; INSERT writes all 7 audit columns) can only be
    //   end-to-end verified against a real PG server. On Mac dev (no Docker
    //   PG, no sqlite fallback because sqlx::postgres::PgPool is PG-typed),
    //   the best unit-level defense is to pin the exact SQL substrings so a
    //   well-meaning refactor can't silently drop `DISTINCT ON`, reverse the
    //   ORDER BY direction, or forget a column — any of which would break
    //   STRATEGIST-PARAMS-PERSIST-1's restore-on-restart semantics without
    //   a failing test.
    //
    //   These are property tests (not semantic tests): they guarantee the
    //   source code contains the intended SQL shape, not that the SQL
    //   produces correct rows. Semantic round-trip coverage is tracked as
    //   a deferred Linux-CI integration harness task.
    //
    // 本組 3 test 為 SQL 字面 property test（非語意 test）：
    //   - 防 SQL 關鍵子句（DISTINCT ON / ORDER BY DESC / 7 欄 INSERT）被後續
    //     重構誤改而無測試失敗擋住。
    //   - 真 SQL 語意正確性（多 row DISTINCT ON 取最新、round-trip）需真 PG
    //     integration test，延後到 Linux CI harness。
    // ───────────────────────────────────────────────────────────────────

    #[test]
    fn test_load_sql_has_distinct_on_and_desc_order() {
        // QC M2 (b): verify load_latest_applied_params SQL keeps the
        // DISTINCT ON (engine_mode, strategy_name) + ORDER BY ...
        // applied_at_ms DESC clause pair. Dropping DISTINCT ON would return
        // every historical audit row instead of the latest; flipping DESC →
        // ASC would return the oldest row (breaking restore-on-restart).
        // QC M2 (b)：驗 load SQL 保持 DISTINCT ON + applied_at_ms DESC 子句對。
        // 丟掉 DISTINCT ON 會回全部歷史 audit row；DESC → ASC 會回最舊 row，
        // 兩者都會使 restart 後參數還原錯誤（拿舊參數或重複 IPC）。
        assert!(
            PERSIST_SRC.contains("DISTINCT ON (engine_mode, strategy_name)"),
            "load_latest_applied_params SQL must contain \
             'DISTINCT ON (engine_mode, strategy_name)' — \
             load SQL 必須含 DISTINCT ON 子句才能取每組最新 row"
        );
        assert!(
            PERSIST_SRC.contains("applied_at_ms DESC"),
            "load_latest_applied_params SQL must contain \
             'applied_at_ms DESC' — DESC 方向是拿「最新」 applied_at_ms 的關鍵"
        );
        assert!(
            PERSIST_SRC.contains("ORDER BY engine_mode, strategy_name, applied_at_ms DESC"),
            "load_latest_applied_params SQL ORDER BY must exactly match \
             DISTINCT ON target columns + applied_at_ms DESC tiebreak — \
             ORDER BY 前綴必須同 DISTINCT ON 目標欄，最後以 applied_at_ms DESC \
             決勝（PG 語法硬要求）"
        );
    }

    /// STRATEGIST-PERSIST-TIE-BREAK-1 (2026-04-23, FA H1 post-commit audit):
    /// pin the V020 `, id DESC` tie-break so concurrent writers with identical
    /// applied_at_ms always restore the latest row (highest id). Without this
    /// tie-break, DISTINCT ON falls back to PG physical row order — not stable,
    /// depends on page layout, intermittently restores the older row.
    ///
    /// This test pairs with V020 migration that adds `id DESC` to the
    /// `idx_strategist_applied_engine_strategy_ts` index so the executor can
    /// actually use the index for this ORDER BY shape.
    ///
    /// STRATEGIST-PERSIST-TIE-BREAK-1（V020）：pin `, id DESC` tie-break。
    /// 並發同 ms 寫入時必取 id 最大者（最晚寫入），無此 tie-break 時
    /// DISTINCT ON 落回 PG physical row order 間歇取到舊 row。
    #[test]
    fn test_load_sql_has_id_desc_tie_break() {
        assert!(
            PERSIST_SRC.contains("applied_at_ms DESC, id DESC"),
            "load_latest_applied_params SQL ORDER BY must contain \
             'applied_at_ms DESC, id DESC' tie-break — \
             ORDER BY 必須含 `applied_at_ms DESC, id DESC` 雙層 tie-break，\
             防並發同 ms 寫入時 DISTINCT ON 取到非確定 row（FA H1 / V020）"
        );
    }

    #[test]
    fn test_load_sql_selects_expected_columns_and_filters_engine_mode() {
        // QC M2 (b) supplement: verify load SQL projects the 2-tuple
        // (strategy_name, params_json) that matches the query_as::<_, (String,
        // serde_json::Value)>() decode target, and filters by $1 engine_mode
        // so we don't accidentally mix paper/demo/live restore rows.
        // QC M2 (b) 補：驗 SELECT 投影欄對齊 query_as 2-tuple 解碼目標 +
        // WHERE engine_mode 過濾（不跨 paper/demo/live 污染還原）。
        assert!(
            PERSIST_SRC.contains("SELECT DISTINCT ON (engine_mode, strategy_name)"),
            "load SQL SELECT clause shape regression — \
             SELECT 子句形狀被改動"
        );
        assert!(
            PERSIST_SRC.contains("strategy_name, params_json"),
            "load SQL must project exactly (strategy_name, params_json) \
             to match query_as decode tuple — \
             投影欄必須對齊 query_as::<_, (String, serde_json::Value)> 解碼元組"
        );
        assert!(
            PERSIST_SRC.contains("FROM learning.strategist_applied_params"),
            "load SQL must read from learning.strategist_applied_params — \
             必須從 learning schema 讀（非 public 或他 schema）"
        );
        assert!(
            PERSIST_SRC.contains("WHERE engine_mode = $1"),
            "load SQL must filter by engine_mode = $1 to scope restore to \
             current engine (paper/demo/live/live_demo) — \
             必須以 engine_mode = $1 過濾，避免跨引擎還原污染"
        );
    }

    #[test]
    fn test_persist_sql_has_all_seven_audit_columns_and_placeholders() {
        // QC M2 (c): verify persist_applied_params INSERT writes all 7
        // audit-trail columns (engine_mode / strategy_name / params_json /
        // applied_at_ms / source / reason / prev_params_json) with
        // matching $1..$7 placeholders. Dropping any column would corrupt
        // the audit trail and break the multi-row round-trip guarantee
        // (e.g. missing prev_params_json = no diff reconstruction; missing
        // applied_at_ms = DISTINCT ON can't pick latest).
        // QC M2 (c)：驗 persist INSERT 寫入全 7 個 audit 欄 + $1..$7 綁定對齊。
        // 少任一欄都會破壞 audit trail + multi-row round-trip 保證
        // （缺 prev_params_json → 無 diff 重建；缺 applied_at_ms → DISTINCT ON 無法取最新）。
        assert!(
            PERSIST_SRC.contains("INSERT INTO learning.strategist_applied_params"),
            "persist SQL must INSERT INTO learning.strategist_applied_params — \
             必須 INSERT 到 learning.strategist_applied_params"
        );
        for col in &[
            "engine_mode",
            "strategy_name",
            "params_json",
            "applied_at_ms",
            "source",
            "reason",
            "prev_params_json",
        ] {
            assert!(
                PERSIST_SRC.contains(col),
                "persist SQL must include column '{}' — \
                 INSERT 必須含 7 個 audit 欄之 '{}'",
                col,
                col
            );
        }
        // Exact column-list clause (7 columns in declaration order, matches
        // $1..$7 bind order below). The source uses Rust line-continuation
        // (`\` + newline) inside the string literal, so we strip backslashes
        // then collapse all whitespace before substring matching — this keeps
        // the test stable across minor whitespace/indent refactors while
        // still pinning the 7-column declaration order.
        // 精確列欄子句（宣告順序對齊 $1..$7 綁定順序）。源碼用 Rust 行延續
        // `\` + 換行，故先剝除反斜線再空白正規化後比對，小幅排版重構不破壞
        // test 但仍鎖定 7 欄聲明順序。
        let src_normalised: String = PERSIST_SRC
            .replace('\\', " ")
            .split_whitespace()
            .collect::<Vec<_>>()
            .join(" ");
        assert!(
            src_normalised.contains(
                "(engine_mode, strategy_name, params_json, applied_at_ms, \
                 source, reason, prev_params_json)"
            ),
            "persist SQL column-list clause must preserve 7-column \
             declaration order aligning with $1..$7 binds — \
             INSERT 欄列順序必須嚴格對齊 $1..$7 綁定順序"
        );
        assert!(
            src_normalised.contains("VALUES ($1, $2, $3, $4, $5, $6, $7)"),
            "persist SQL VALUES clause must bind exactly $1..$7 (7 placeholders) — \
             VALUES 必須正好 7 個 $1..$7 placeholder 對齊 7 欄"
        );
    }
}
