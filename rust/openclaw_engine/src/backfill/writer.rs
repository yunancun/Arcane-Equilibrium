//! MODULE_NOTE
//! 模塊用途：K 線回填的 DB 寫層 + V125 preflight probe。把 strict-parse 過的 bar 寫
//!   market.klines（timeframe 由 page 攜帶：daily 回填寫 '1d'，intraday 回填寫
//!   1m/5m/15m/1h/4h），並把覆蓋率判定寫 research.alpha_klines_provenance append-only 帳本。
//! 主要類/函數：probe_provenance_table_exists（V125 缺表 fail-closed）/
//!   write_daily_klines_strict（market.klines 寫入，DO NOTHING 冪等，strict 值非 sanitize）/
//!   write_klines_strict_overwrite（DO UPDATE 覆蓋變體，僅 apply gate 後使用）/
//!   insert_provenance_row（provenance 帳本）/ ProvenanceRow / WriteSummary。
//! 依賴：DbPool（sqlx PgPool）、daily_kline_backfill::{ParsedKlinePage, CoverageVerdict}、chrono。
//! 硬邊界：
//!   1. market.klines 的 open/high/low/close 用 strict 值直接綁定，絕不過
//!      sanitize_f64_or_zero（market_writer.rs:259-262 的 fake-zero 地雷）；上游
//!      strict_filter_closed_bars(_for) 已保證這四欄有限且 > 0。volume/turnover 為 nullable，
//!      走 sanitize_f64（保 None 而非 0.0），與既有 flush_klines 對 nullable 欄一致。
//!   2. INSERT ... ON CONFLICT (symbol,timeframe,ts) DO NOTHING（write_daily_klines_strict，
//!      預設）：timeframe='1d' 與 live 訂的 1m-1h 完全 disjoint，永不衝突；DO NOTHING 保冪等
//!      （重跑不覆蓋已有行）。
//!   3.【intraday 衝突關鍵】intraday 回填寫的 1m/5m/15m/1h 標籤與 live writer 已存的「壞」行
//!      共用同一 PK (symbol,timeframe,ts)。DO NOTHING 會在每一既有行靜默跳過（最陰險失敗：
//!      inserted=0、exit=0）。故 intraday in-place 覆蓋必須：(a) operator 先 decompress+DELETE
//!      被覆蓋窗的壞行（Linux 腳本，本 workflow 不執行），或 (b) 用 write_klines_strict_overwrite
//!      （DO UPDATE）——但 DO UPDATE 在壓縮 hypertable 上同樣需先 decompress，故仍 operator-gated。
//!      兩者皆不改 live writer 的 DO NOTHING。
//!   4. provenance append-only：只 INSERT，不 UPDATE/DELETE 既有 row（root principle #8）。
//!   5. 純讀市場 + append 帳本，不下單/不餵 intent/不碰 auth/lease。

use crate::backfill::daily_kline_backfill::ParsedKlinePage;
use crate::database::pool::DbPool;
use chrono::{DateTime, Utc};

/// market.klines 一次寫入的結果統計。
#[derive(Debug, Clone, Default, PartialEq)]
pub struct WriteSummary {
    /// 嘗試綁定的 bar 數（= strict 通過的 observed）。
    pub attempted: u64,
    /// 實際 INSERT 影響行數（ON CONFLICT DO NOTHING 後新增的；已存在的不計）。
    pub inserted: u64,
}

/// provenance 帳本一筆寫入所需欄位（對映 V125 research.alpha_klines_provenance）。
///
/// 為什麼把 git_sha/git_dirty 作為入參而非自動偵測：engine 無 build.rs git 嵌入，回填由
/// 運維/cron 觸發；caller（CLI）負責提供當前 git 狀態，使 provenance 可追到「哪個 build
/// 寫的、工作樹是否 dirty」。endpoint_id 固定為 Bybit kline 端點。
#[derive(Debug, Clone)]
pub struct ProvenanceRow {
    pub run_id: String,
    pub endpoint_id: String,
    pub category: String,
    pub symbol: String,
    pub timeframe: String,
    pub window_start_ms: u64,
    pub window_end_ms: u64,
    pub request_start_ms: Option<u64>,
    pub request_end_ms: Option<u64>,
    pub parser_version: String,
    pub git_sha: Option<String>,
    pub git_dirty: Option<bool>,
    pub payload_sha256: String,
    pub coverage_status: String,
    pub expected_rows: u64,
    pub observed_rows: u64,
}

/// 把毫秒時間戳轉 TIMESTAMPTZ；非法（溢出）回 None。
/// 為什麼不 unwrap_or_default：default 會落 1970 epoch，污染 provenance 窗口語意 → 必須 None。
fn utc_from_ms(ms: u64) -> Option<DateTime<Utc>> {
    DateTime::<Utc>::from_timestamp_millis(ms as i64)
}

/// V125 preflight：探測 research.alpha_klines_provenance 是否存在。
///
/// 為什麼 fail-closed（缺表即回 false 讓 CLI 退出）：V125 尚未 apply 時帳本表不存在，
/// 若仍寫 market.klines 會產生「無來源帳的 OHLCV」(root principle #8 違反：無法追溯)。
/// 用 to_regclass（PG 內建，不存在回 NULL，不拋例外）避免 information_schema 全表掃。
pub async fn probe_provenance_table_exists(pool: &DbPool) -> Result<bool, sqlx::Error> {
    let Some(pg) = pool.get() else {
        // pool 不可用：保守視為「無法確認」→ fail-closed（false）。
        return Ok(false);
    };
    // to_regclass 對不存在的物件回 NULL（型別 regclass）；存在回非 NULL。
    let row: Option<Option<String>> =
        sqlx::query_scalar("SELECT to_regclass('research.alpha_klines_provenance')::text")
            .fetch_optional(pg)
            .await?;
    // 外層 Option = 有無回 row（必有）；內層 Option = regclass 是否為 NULL。
    Ok(matches!(row, Some(Some(_))))
}

/// 取 market.klines 中、指定 timeframe 集內出現過的全部 distinct symbol（升序）。
///
/// 為什麼需要（--symbols-from-db）：curated toml universe 只含復核過的子集，但本工具的
/// vol+turnover 校正用途要覆蓋 DB 既有全部標的。對「本次要回填的 timeframe 集」取
/// distinct symbol 即為精確的回填目標域（只有這些 timeframe 真有行需校正）。唯讀查詢。
/// pool 不可用時回空 Vec（caller fail-closed 退出，不靜默回填空集）。
pub async fn distinct_symbols_for_timeframes(
    pool: &DbPool,
    timeframes: &[String],
) -> Result<Vec<String>, sqlx::Error> {
    let Some(pg) = pool.get() else {
        return Ok(Vec::new());
    };
    // ANY($1) 參數化綁定 timeframe 陣列（避免字串拼接 SQL 注入面）。
    let rows: Vec<(String,)> = sqlx::query_as(
        "SELECT DISTINCT symbol FROM market.klines \
         WHERE timeframe = ANY($1) ORDER BY symbol",
    )
    .bind(timeframes)
    .fetch_all(pg)
    .await?;
    Ok(rows.into_iter().map(|(s,)| s).collect())
}

/// market.klines 寫入時的衝突策略（針對 PK (symbol,timeframe,ts) 既有行）。
///
/// 為什麼分兩種：daily 回填寫 '1d'，與 live 1m-1h disjoint，DO NOTHING 冪等即足。
/// 但 intraday 回填寫的 1m/5m/15m/1h 與 live writer 已存的壞行同 PK，DO NOTHING 會被靜默
/// 跳過（inserted=0 假成功）。Overwrite（DO UPDATE）讓 in-place 校正可行——但 caller 必須
/// 先在 apply gate 後確認（壓縮 hypertable 仍需 operator decompress），故不作預設。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConflictMode {
    /// ON CONFLICT DO NOTHING：既有行勝出（冪等重跑；daily 預設）。
    DoNothing,
    /// ON CONFLICT DO UPDATE：以本次 strict bar 覆蓋既有行的 OHLCV+turnover+tick_count。
    /// 僅供 intraday in-place 校正，必在 apply gate 後使用。
    Overwrite,
    /// ON CONFLICT DO UPDATE SET volume / turnover only：既有行只校正成交量+成交額，
    /// 絕不碰 open/high/low/close/tick_count。
    ///
    /// 為什麼需要這第三種模式（保護 close-依賴的歷史歸因）：database/outcome_backfiller.rs
    /// 從 market.klines 讀 close/high/low 重算歷史 decision_outcomes；若用 Overwrite 改寫
    /// close 會篡改既有歸因（違 root principle #8「每筆交易必可重建/解釋」）。本模式只校正
    /// live tick-synth 路徑常缺/失真的 volume+turnover，OHLC 維持既有權威值不動。
    UpdateVolTurnoverOnly,
}

/// 把一個 strict-parse 過的 page 寫入 market.klines（timeframe 由 page 攜帶，DO NOTHING 冪等）。
///
/// 不變量（由上游 strict_filter_closed_bars(_for) 保證）：page.bars 內每根 open/high/low/close
/// 皆有限且 > 0 → 直接綁定為 REAL（f32），不過 sanitize_f64_or_zero。volume/turnover
/// 為 nullable，走 sanitize_f64（NaN/Inf → None，不偽造 0.0）。
///
/// 為什麼逐行 INSERT 而非 QueryBuilder 批量：回填筆數可控（sequential、非熱路徑）；逐行 +
/// ON CONFLICT DO NOTHING 最簡單且冪等。caller 在 tx 內呼叫。daily 與 intraday 皆可用此
/// 預設變體（DO NOTHING）；intraday in-place 覆蓋走 write_klines_strict_overwrite。
pub async fn write_daily_klines_strict(
    pool: &DbPool,
    page: &ParsedKlinePage,
) -> Result<WriteSummary, sqlx::Error> {
    write_klines_strict_with_mode(pool, page, ConflictMode::DoNothing).await
}

/// 把一個 strict-parse 過的 page 寫入 market.klines，衝突時 DO UPDATE 覆蓋既有行。
///
/// 為什麼需要此變體（intraday in-place 校正）：intraday 回填的 1m/5m/15m/1h 標籤與 live writer
/// 已寫入的「壞」行（tick-synth 退化 bar）共用同一 PK。預設 DO NOTHING 會在每一既有行靜默
/// 跳過 → inserted=0、exit=0 的假成功（最陰險失敗模式）。本變體以本次 strict bar 覆蓋
/// open/high/low/close/volume/turnover/tick_count + open_ts_ms/close_ts_ms。
///
/// 硬邊界：market.klines 是壓縮 TimescaleDB hypertable，DO UPDATE 在已壓縮 chunk 上需先
/// decompress（operator Linux 步驟）；故 caller 必在 apply gate 後才允許此模式，且本變體
/// 不改 live writer 的 DO NOTHING（market_writer.rs:272 維持不變）。
pub async fn write_klines_strict_overwrite(
    pool: &DbPool,
    page: &ParsedKlinePage,
) -> Result<WriteSummary, sqlx::Error> {
    write_klines_strict_with_mode(pool, page, ConflictMode::Overwrite).await
}

/// 把一個 strict-parse 過的 page 寫入 market.klines，衝突時只 DO UPDATE 校正 volume+turnover。
///
/// 為什麼需要此變體（vol+turnover-only 安全校正）：intraday 回填的 1m/5m/15m/1h/4h 標籤與
/// live writer 已寫入的行共用同一 PK。Overwrite 會連 open/high/low/close 一併覆蓋，但
/// database/outcome_backfiller.rs 從 market.klines 讀 close/high/low 重算歷史 decision_outcomes
/// —— 改寫 close 即篡改既有歸因（違 root principle #8）。本變體只把成交量+成交額校正成本次
/// strict 值（live tick-synth 路徑常缺/失真之處），既有行的 OHLC + tick_count 一律不動。
/// 新插入的行仍寫完整 authoritative bar（INSERT 列/VALUES 不變）。
///
/// 硬邊界：與 Overwrite 同，DO UPDATE 在已壓縮 hypertable chunk 上仍需 operator 先 decompress；
/// 不改 live writer 的 DO NOTHING（market_writer.rs 維持不變）。
pub async fn write_klines_vol_turnover_only(
    pool: &DbPool,
    page: &ParsedKlinePage,
) -> Result<WriteSummary, sqlx::Error> {
    write_klines_strict_with_mode(pool, page, ConflictMode::UpdateVolTurnoverOnly).await
}

/// 共用核心：依 ConflictMode 選 DO NOTHING / DO UPDATE 把 page 寫 market.klines。
///
/// 抽出私有核心避免兩變體重複 strict-bind 邏輯（單一 SSOT，改 bind 規則只改一處）。
/// inserted 在 DO NOTHING 下 = 新增行數（既有行 rows_affected=0）；在 DO UPDATE 下
/// = 受影響行數（新增 + 覆蓋皆計 1，PG ON CONFLICT DO UPDATE 對命中行回 rows_affected=1）。
/// attempted 兩者皆 = strict 通過且 ts 有效的 bar 數，供 caller 比對 inserted≪attempted。
/// 把 ConflictMode 映射為 INSERT 尾端的 ON CONFLICT 子句（純函數，便於單測）。
///
/// 為什麼抽成獨立 fn：三模式的子句是安全語意的命門（UpdateVolTurnoverOnly 絕不可含
/// open/high/low/close），抽出後可在不連 DB 的情況下對字串做斷言（mode→clause 映射正確）。
fn conflict_clause_for(mode: ConflictMode) -> &'static str {
    match mode {
        ConflictMode::DoNothing => "ON CONFLICT (symbol, timeframe, ts) DO NOTHING",
        ConflictMode::Overwrite => {
            "ON CONFLICT (symbol, timeframe, ts) DO UPDATE SET \
                open_ts_ms = EXCLUDED.open_ts_ms, \
                close_ts_ms = EXCLUDED.close_ts_ms, \
                open = EXCLUDED.open, \
                high = EXCLUDED.high, \
                low = EXCLUDED.low, \
                close = EXCLUDED.close, \
                volume = EXCLUDED.volume, \
                turnover = EXCLUDED.turnover, \
                tick_count = EXCLUDED.tick_count"
        }
        // 只校正 volume+turnover：既有行的 open/high/low/close/tick_count + open_ts_ms/close_ts_ms
        // 完全不動，保護 outcome_backfiller 讀的 close-依賴歷史歸因（見變體 doc-comment）。
        ConflictMode::UpdateVolTurnoverOnly => {
            "ON CONFLICT (symbol, timeframe, ts) DO UPDATE SET \
                volume = EXCLUDED.volume, \
                turnover = EXCLUDED.turnover"
        }
    }
}

async fn write_klines_strict_with_mode(
    pool: &DbPool,
    page: &ParsedKlinePage,
    mode: ConflictMode,
) -> Result<WriteSummary, sqlx::Error> {
    let Some(pg) = pool.get() else {
        return Ok(WriteSummary::default());
    };
    let mut summary = WriteSummary::default();
    let mut tx = pg.begin().await?;

    // 依模式選 ON CONFLICT 子句；INSERT 欄位/VALUES 占位完全相同（單一 bind 路徑）。
    let conflict_clause = conflict_clause_for(mode);
    let sql = format!(
        "INSERT INTO market.klines \
            (ts, open_ts_ms, close_ts_ms, symbol, timeframe, \
             open, high, low, close, volume, turnover, tick_count) \
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12) \
         {conflict_clause}"
    );

    for bar in &page.bars {
        let Some(ts) = utc_from_ms(bar.open_time_ms) else {
            // open_time 溢出（理論不可達，strict 已過濾窗口）：跳過不寫，不靜默偽造時間。
            continue;
        };
        summary.attempted += 1;

        // open/high/low/close：strict 值直接綁 f32（NOT NULL 欄，已保證有限 > 0）。
        // volume/turnover：sanitize_f64 → Option（nullable 欄，NaN/Inf → NULL 不偽造 0.0）。
        let vol = crate::database::sanitize_f64(bar.volume).map(|v| v as f32);
        let turn = crate::database::sanitize_f64(bar.turnover).map(|v| v as f32);

        let result = sqlx::query(&sql)
            .bind(ts)
            .bind(bar.open_time_ms as i64)
            .bind(bar.close_time_ms as i64)
            .bind(page.symbol.as_str())
            .bind(page.timeframe.as_str())
            .bind(bar.open as f32)
            .bind(bar.high as f32)
            .bind(bar.low as f32)
            .bind(bar.close as f32)
            .bind(vol)
            .bind(turn)
            .bind(bar.tick_count as i32)
            .execute(&mut *tx)
            .await?;
        summary.inserted += result.rows_affected();
    }

    tx.commit().await?;
    Ok(summary)
}

/// 把一筆覆蓋率判定寫入 research.alpha_klines_provenance（append-only）。
///
/// 為什麼 ON CONFLICT DO NOTHING：PK = (run_id, endpoint_id, category, symbol, timeframe,
/// window_start, window_end)；同一 run 對同窗重跑不應產生第二筆（冪等）。不同 run_id 則保
/// 各自證據（lineage，不靜默覆蓋）。coverage_pct 由 expected/observed 推算。
pub async fn insert_provenance_row(
    pool: &DbPool,
    row: &ProvenanceRow,
) -> Result<u64, sqlx::Error> {
    let Some(pg) = pool.get() else {
        return Ok(0);
    };
    let Some(window_start) = utc_from_ms(row.window_start_ms) else {
        return Ok(0);
    };
    let Some(window_end) = utc_from_ms(row.window_end_ms) else {
        return Ok(0);
    };
    let request_start = row.request_start_ms.and_then(utc_from_ms);
    let request_end = row.request_end_ms.and_then(utc_from_ms);
    // coverage_pct：expected=0 時為 NULL（無分母），否則 observed/expected。
    let coverage_pct: Option<f64> = if row.expected_rows == 0 {
        None
    } else {
        Some(row.observed_rows as f64 / row.expected_rows as f64)
    };

    let result = sqlx::query(
        "INSERT INTO research.alpha_klines_provenance \
            (run_id, endpoint_id, category, symbol, timeframe, \
             window_start, window_end, storage_surface, \
             request_start, request_end, parser_version, git_sha, git_dirty, \
             payload_sha256, expected_rows, observed_rows, coverage_pct, coverage_status) \
         VALUES ($1, $2, $3, $4, $5, $6, $7, 'market.klines', \
                 $8, $9, $10, $11, $12, $13, $14, $15, $16, $17) \
         ON CONFLICT (run_id, endpoint_id, category, symbol, timeframe, window_start, window_end) \
            DO NOTHING",
    )
    .bind(&row.run_id)
    .bind(&row.endpoint_id)
    .bind(&row.category)
    .bind(&row.symbol)
    .bind(&row.timeframe)
    .bind(window_start)
    .bind(window_end)
    .bind(request_start)
    .bind(request_end)
    .bind(&row.parser_version)
    .bind(row.git_sha.as_deref())
    .bind(row.git_dirty)
    .bind(&row.payload_sha256)
    .bind(row.expected_rows as i64)
    .bind(row.observed_rows as i64)
    .bind(coverage_pct)
    .bind(&row.coverage_status)
    .execute(pg)
    .await?;
    Ok(result.rows_affected())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_utc_from_ms_valid() {
        let dt = utc_from_ms(1_700_000_000_000).expect("valid ms should convert");
        assert_eq!(dt.timestamp_millis(), 1_700_000_000_000);
    }

    #[test]
    fn test_utc_from_ms_zero_is_epoch_not_none() {
        // 0 ms 是合法 epoch（非溢出）；本函數只擋真正溢出，0 由上游窗口邏輯排除。
        assert!(utc_from_ms(0).is_some());
    }

    /// coverage_pct 推算：expected>0 → observed/expected；expected=0 → None。
    /// （透過 ProvenanceRow 的純計算分支驗證，無需 DB。）
    #[test]
    fn test_coverage_pct_logic() {
        // 純複刻 insert_provenance_row 內 coverage_pct 分支（DB 寫入需 Linux PG，此處驗算式）。
        let pct = |expected: u64, observed: u64| -> Option<f64> {
            if expected == 0 {
                None
            } else {
                Some(observed as f64 / expected as f64)
            }
        };
        assert_eq!(pct(0, 0), None);
        assert_eq!(pct(4, 2), Some(0.5));
        assert_eq!(pct(3, 3), Some(1.0));
    }

    /// DoNothing → DO NOTHING（既有行勝出，daily 冪等）。
    #[test]
    fn test_conflict_clause_do_nothing() {
        let c = conflict_clause_for(ConflictMode::DoNothing);
        assert_eq!(c, "ON CONFLICT (symbol, timeframe, ts) DO NOTHING");
        assert!(!c.contains("DO UPDATE"));
    }

    /// Overwrite → DO UPDATE 含全 OHLCV+tick_count（intraday in-place 全覆蓋）。
    #[test]
    fn test_conflict_clause_overwrite_covers_all_columns() {
        let c = conflict_clause_for(ConflictMode::Overwrite);
        assert!(c.contains("DO UPDATE SET"));
        for col in ["open", "high", "low", "close", "volume", "turnover", "tick_count"] {
            assert!(c.contains(&format!("{col} = EXCLUDED.{col}")), "missing {col}");
        }
    }

    /// UpdateVolTurnoverOnly → 只校正 volume+turnover；**絕不**碰 open/high/low/close/tick_count。
    /// 這是保護 outcome_backfiller close-依賴歷史歸因的安全命門，必須精確斷言。
    #[test]
    fn test_conflict_clause_vol_turnover_only_never_touches_ohlc() {
        let c = conflict_clause_for(ConflictMode::UpdateVolTurnoverOnly);
        assert_eq!(
            c,
            "ON CONFLICT (symbol, timeframe, ts) DO UPDATE SET \
                volume = EXCLUDED.volume, \
                turnover = EXCLUDED.turnover"
        );
        assert!(c.contains("volume = EXCLUDED.volume"));
        assert!(c.contains("turnover = EXCLUDED.turnover"));
        // 安全不變量：OHLC + tick_count + ts 欄位一律不得出現在 SET 子句。
        for forbidden in [
            "open = EXCLUDED",
            "high = EXCLUDED",
            "low = EXCLUDED",
            "close = EXCLUDED",
            "tick_count = EXCLUDED",
            "open_ts_ms = EXCLUDED",
            "close_ts_ms = EXCLUDED",
        ] {
            assert!(!c.contains(forbidden), "vol-only clause must not set {forbidden}");
        }
    }
}
