//! intraday kline 真值校準 / drift guardrail checker（INTRADAY-KLINES-PERMANENT-FIX R3）。
//!
//! MODULE_NOTE
//! 模塊用途：cron 觸發的旋轉採樣 truth-test —— 對 (symbol, timeframe) 旋轉採樣窗，拉 local
//!   market.klines + Bybit authoritative get_klines 對齊 ts，算 close_match/range_ratio/corr@0/
//!   corr@+1/turnover_nonzero/gap（複用 backfill::kline_calibration 純函數 SSOT），寫
//!   research.kline_calibration（V141），drift 命中走既有耐久 alert sink（alerts.jsonl，與
//!   helper_scripts/canary/alert_sink.py append_alert_sink 同 schema）。鏡像 feature_baseline_writer
//!   安全骨架：dry-run 預設 / OPENCLAW_KLINE_CALIBRATION_APPLY=1 env gate / EXIT code。
//! 兩種模式：
//!   1.【預設 R3 監測】旋轉採樣 ~N cell（cursor 從 research.kline_calibration 最舊 checked_ts
//!      取下一批 round-robin），算 metric 寫表，drift → alert sink。dry-run 印判定不寫。
//!   2.【--gate R4 驗收】對 --symbol/--timeframe/--start/--end 指定的「已 recal 窗」算 metric，
//!      套 RecalGateThresholds 嚴格驗收（corr0≈0.99 AND range_ratio≈1.0）；PASS→exit 0、
//!      FAIL→exit 5（fail-loud，供 recal runbook 在 recompress 前 gate）。--gate 純讀不寫表。
//! 依賴：backfill::{kline_calibration（truth-test SSOT）, daily_kline_backfill::{paginate_klines,
//!   expected_bars_for}}、market_data_client、database::pool、bybit_rest_client、secret_env。
//! 硬邊界：
//!   1. 唯讀 market.klines（只 SELECT）+ Bybit REST（公開 kline，無 auth/執行路徑）；
//!      只寫 research.kline_calibration（R3 模式）+ alerts.jsonl（drift）。--gate 模式零寫。
//!   2. V141 preflight：research.kline_calibration 缺表即 fail-closed 退出（EXIT_DB）。
//!   3. 不下單 / 不餵 intent / 不碰 auth / lease / system_mode / cap。
//!   4. R3 寫表需 apply gate（dry-run 預設）；alert sink 在 apply 模式 drift 時才寫。
//! 運維：cron wrapper helper_scripts/cron/kline_calibration_cron.sh（OPENCLAW_KLINE_CALIBRATION_APPLY=1）；
//!   配對 healthcheck [91]（cron heartbeat sentinel kline_calibration.last_fire）。

#![allow(
    clippy::doc_lazy_continuation,
    clippy::doc_overindented_list_items,
    clippy::empty_line_after_doc_comments,
    clippy::too_many_arguments
)]

use std::collections::BTreeMap;
use std::env;
use std::io::Write as _;
use std::path::PathBuf;
use std::sync::Arc;

use openclaw_engine::backfill::daily_kline_backfill::{expected_bars_for, paginate_klines};
use openclaw_engine::backfill::kline_calibration::{
    align_bars, compute_metrics, evaluate_drift, evaluate_recal_gate, CalibrationMetrics,
    DriftThresholds, LocalBar, RecalGateThresholds,
};
use openclaw_engine::bybit_rest_client::{BybitEnvironment, BybitRestClient};
use openclaw_engine::database::pool::DbPool;
use openclaw_engine::database::DatabaseConfig;
use openclaw_engine::market_data_client::MarketDataClient;
use openclaw_engine::secret_env;

const EXIT_OK: i32 = 0;
const EXIT_ARG: i32 = 2;
const EXIT_DB: i32 = 4;
/// --gate 模式 recal 驗收未過的退出碼（fail-loud；runbook 據此不 recompress）。
const EXIT_GATE_FAIL: i32 = 5;
const APPLY_ENV: &str = "OPENCLAW_KLINE_CALIBRATION_APPLY";
/// checker 邏輯版本（truth-test 規則變動時遞增；落 research.kline_calibration.checker_version）。
const CHECKER_VERSION: &str = "kline_calibration_v1";
/// linear perp（與 backfill 同 category；本檢查只針對 perp intraday klines）。
const CATEGORY: &str = "linear";

/// 旋轉採樣的全 timeframe 集（與 intraday_kline_backfill DEFAULT_INTERVALS 對齊）。
/// 每元素 = (DB timeframe 標籤, Bybit interval, period_ms)。
const ALL_TIMEFRAMES: [(&str, &str, u64); 5] = [
    ("1m", "1", 60_000),
    ("5m", "5", 300_000),
    ("15m", "15", 900_000),
    ("1h", "60", 3_600_000),
    ("4h", "240", 14_400_000),
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Mode {
    /// R3 旋轉監測（寫表 + drift alert）。
    Monitor,
    /// R4 recal 驗收 gate（純讀 + exit code）。
    Gate,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ApplyGate {
    None,
    Env,
    CliAck,
}

impl ApplyGate {
    fn label(self) -> &'static str {
        match self {
            ApplyGate::None => "none",
            ApplyGate::Env => APPLY_ENV,
            ApplyGate::CliAck => "--i-understand-this-modifies-db",
        }
    }
}

#[derive(Debug, Clone)]
struct Args {
    mode: Mode,
    /// Monitor 模式：true=真寫表 + drift alert；false=dry-run 印判定不寫。
    apply: bool,
    apply_gate: ApplyGate,
    i_understand: bool,
    /// 每跑採樣 cell 數（Monitor 旋轉批量）。
    sample_size: usize,
    /// 採樣窗回看小時數（足夠算 corr/range；預設 48h）。
    lookback_hours: u64,
    /// --gate 模式：限定 symbol（必填）。
    gate_symbol: Option<String>,
    /// --gate 模式：限定 timeframe（必填）。
    gate_timeframe: Option<String>,
    /// --gate 模式：窗起（ms epoch；必填）。
    gate_start_ms: Option<u64>,
    /// --gate 模式：窗止（ms epoch；必填）。
    gate_end_ms: Option<u64>,
}

impl Default for Args {
    fn default() -> Self {
        Self {
            mode: Mode::Monitor,
            apply: false,
            apply_gate: ApplyGate::None,
            i_understand: false,
            sample_size: 30,
            lookback_hours: 48,
            gate_symbol: None,
            gate_timeframe: None,
            gate_start_ms: None,
            gate_end_ms: None,
        }
    }
}

fn apply_env_enabled() -> bool {
    matches!(env::var(APPLY_ENV), Ok(v) if v.trim() == "1")
}

fn parse_args() -> Result<Args, String> {
    parse_args_from(env::args().skip(1), apply_env_enabled())
}

fn parse_args_from<I>(iter: I, apply_env: bool) -> Result<Args, String>
where
    I: IntoIterator<Item = String>,
{
    let mut args = Args::default();
    let mut mode_set_apply_by_cli = false;
    let mut it = iter.into_iter().peekable();

    while let Some(arg) = it.next() {
        match arg.as_str() {
            "--dry-run" | "--verify" => {
                args.apply = false;
                args.apply_gate = ApplyGate::None;
                mode_set_apply_by_cli = true;
            }
            "--apply" => {
                args.apply = true;
                args.apply_gate = ApplyGate::CliAck;
                mode_set_apply_by_cli = true;
            }
            "--i-understand-this-modifies-db" => args.i_understand = true,
            "--gate" => args.mode = Mode::Gate,
            "--sample-size" => args.sample_size = parse_next_usize(&mut it, "--sample-size")?,
            "--lookback-hours" => args.lookback_hours = parse_next_u64(&mut it, "--lookback-hours")?,
            "--symbol" => args.gate_symbol = Some(parse_next_string(&mut it, "--symbol")?),
            "--timeframe" => args.gate_timeframe = Some(parse_next_string(&mut it, "--timeframe")?),
            "--start-ms" => args.gate_start_ms = Some(parse_next_u64(&mut it, "--start-ms")?),
            "--end-ms" => args.gate_end_ms = Some(parse_next_u64(&mut it, "--end-ms")?),
            "--help" | "-h" => {
                print_help();
                std::process::exit(EXIT_OK);
            }
            "--yes" | "-y" | "--force" | "--auto-yes" => {
                return Err(format!(
                    "rejected flag {arg}: --apply requires the explicit acknowledgement flag"
                ));
            }
            other => return Err(format!("unknown argument: {other}")),
        }
    }

    // env gate 只在 Monitor 模式有意義（--gate 純讀不寫表，與 apply 無關）。
    if args.mode == Mode::Monitor && apply_env && !mode_set_apply_by_cli {
        args.apply = true;
        args.apply_gate = ApplyGate::Env;
    }
    if args.mode == Mode::Monitor && args.apply {
        if apply_env {
            args.apply_gate = ApplyGate::Env;
        } else if args.i_understand {
            args.apply_gate = ApplyGate::CliAck;
        } else {
            return Err(format!(
                "apply mode requires --i-understand-this-modifies-db or {APPLY_ENV}=1"
            ));
        }
    }
    if args.sample_size == 0 {
        return Err("--sample-size must be > 0".to_string());
    }
    if args.lookback_hours == 0 {
        return Err("--lookback-hours must be > 0".to_string());
    }
    // --gate 模式四參數必填（symbol/timeframe/start/end）+ timeframe 合法 + start<end。
    if args.mode == Mode::Gate {
        let sym = args.gate_symbol.as_deref();
        let tf = args.gate_timeframe.as_deref();
        if sym.is_none() || tf.is_none() || args.gate_start_ms.is_none() || args.gate_end_ms.is_none()
        {
            return Err(
                "--gate requires --symbol, --timeframe, --start-ms and --end-ms".to_string(),
            );
        }
        let tf = tf.unwrap();
        if !ALL_TIMEFRAMES.iter().any(|(t, _, _)| *t == tf) {
            return Err(format!(
                "--gate --timeframe expects one of 1m|5m|15m|1h|4h, got {tf}"
            ));
        }
        if let (Some(s), Some(e)) = (args.gate_start_ms, args.gate_end_ms) {
            if s >= e {
                return Err("--gate --start-ms must be strictly before --end-ms".to_string());
            }
        }
    }
    Ok(args)
}

fn parse_next_string(
    it: &mut std::iter::Peekable<impl Iterator<Item = String>>,
    flag: &str,
) -> Result<String, String> {
    it.next()
        .filter(|v| !v.trim().is_empty())
        .ok_or_else(|| format!("{flag} requires a value"))
}

fn parse_next_usize(
    it: &mut std::iter::Peekable<impl Iterator<Item = String>>,
    flag: &str,
) -> Result<usize, String> {
    parse_next_string(it, flag)?
        .parse::<usize>()
        .map_err(|e| format!("{flag} expects usize: {e}"))
}

fn parse_next_u64(
    it: &mut std::iter::Peekable<impl Iterator<Item = String>>,
    flag: &str,
) -> Result<u64, String> {
    parse_next_string(it, flag)?
        .parse::<u64>()
        .map_err(|e| format!("{flag} expects u64: {e}"))
}

fn print_help() {
    println!(
        "kline_calibration_checker — intraday kline 真值校準 / drift guardrail（R3 + R4 gate）\n\
         \n\
         USAGE:\n  \
           kline_calibration_checker [--dry-run] [--sample-size 30] [--lookback-hours 48]\n  \
           kline_calibration_checker --apply --i-understand-this-modifies-db [options]\n  \
           OPENCLAW_KLINE_CALIBRATION_APPLY=1 kline_calibration_checker [options]\n  \
           kline_calibration_checker --gate --symbol BTCUSDT --timeframe 1m --start-ms M --end-ms M\n\
         \n\
         MODES:\n  \
           default (Monitor): 旋轉採樣 sample-size 個 (symbol,tf) cell，算 metric 寫\n  \
             research.kline_calibration，drift → alerts.jsonl。dry-run 預設不寫。\n  \
           --gate (R4 verify): 對指定窗算 metric 套嚴格驗收（corr0≈0.99 AND range≈1.0）；\n  \
             PASS exit 0 / FAIL exit 5（fail-loud，純讀不寫表）。\n\
         WRITES (Monitor apply mode):\n  \
           research.kline_calibration (V141) + <DATA_DIR>/alerts/alerts.jsonl (drift only)\n\
         PREFLIGHT:\n  \
           research.kline_calibration must exist (V141 applied); missing => fail-closed exit\n\
         ENV:\n  \
           OPENCLAW_DATABASE_URL or OPENCLAW_DATABASE_URL_FILE\n  \
           OPENCLAW_DATA_DIR (alert sink root; default /tmp/openclaw)\n  \
           OPENCLAW_KLINE_CALIBRATION_APPLY=1 enables Monitor apply without CLI ack flags\n"
    );
}

fn resolve_db_url() -> Result<String, String> {
    secret_env::var_or_file("OPENCLAW_DATABASE_URL")
        .filter(|s| !s.is_empty())
        .ok_or_else(|| "OPENCLAW_DATABASE_URL or OPENCLAW_DATABASE_URL_FILE not set".to_string())
}

/// V141 preflight：探測 research.kline_calibration 是否存在（缺即 fail-closed）。
async fn probe_calibration_table_exists(pool: &DbPool) -> Result<bool, sqlx::Error> {
    let Some(pg) = pool.get() else {
        return Ok(false);
    };
    let row: Option<Option<String>> =
        sqlx::query_scalar("SELECT to_regclass('research.kline_calibration')::text")
            .fetch_optional(pg)
            .await?;
    Ok(matches!(row, Some(Some(_))))
}

/// 從 market.klines 讀回指定 (symbol, timeframe) 在 [start_ms, end_ms) 的 local bar。
///
/// 唯讀 SELECT；只取 truth-test 需要的欄（open_ts_ms / high / low / close / turnover）。
/// ts 用 to_timestamp(ms/1000) 範圍綁定（market.klines.ts 是 timestamptz）。
async fn fetch_local_bars(
    pool: &DbPool,
    symbol: &str,
    timeframe: &str,
    start_ms: u64,
    end_ms: u64,
) -> Result<Vec<LocalBar>, sqlx::Error> {
    let Some(pg) = pool.get() else {
        return Ok(Vec::new());
    };
    // open_ts_ms 為 BIGINT；用它做窗口範圍（半開 [start,end)）避免 timestamptz round-trip 誤差。
    let rows: Vec<(i64, f32, f32, f32, Option<f32>)> = sqlx::query_as(
        "SELECT open_ts_ms, high, low, close, turnover \
         FROM market.klines \
         WHERE symbol = $1 AND timeframe = $2 \
           AND open_ts_ms >= $3 AND open_ts_ms < $4 \
         ORDER BY open_ts_ms",
    )
    .bind(symbol)
    .bind(timeframe)
    .bind(start_ms as i64)
    .bind(end_ms as i64)
    .fetch_all(pg)
    .await?;
    Ok(rows
        .into_iter()
        .filter_map(|(open_ms, high, low, close, turnover)| {
            // open_ms 理論恆 >= 0（窗口已綁正值）；負值（不可達）跳過不偽造。
            u64::try_from(open_ms).ok().map(|ms| LocalBar {
                open_time_ms: ms,
                // high/low/close 不參與本欄但保留語義完整；open 本檢查不需故填 close 佔位。
                open: close as f64,
                high: high as f64,
                low: low as f64,
                close: close as f64,
                turnover: turnover.map(|t| t as f64),
            })
        })
        .collect())
}

/// 旋轉游標：對全 (symbol × timeframe) cell，按 research.kline_calibration 最近 checked_ts
/// 升序取下一批（從未採過的 cell checked_ts 視為最舊 → 優先）。
///
/// 為什麼這樣排：round-robin 公平覆蓋 —— 最久沒採的 cell 先採，~26 天輪一遍全 153×5 cell。
/// drift cell（last drift_flag=true）次序提前由 idx_kline_calibration_drift 支援（hot-list），
/// 但本游標的主排序鍵 = 最舊 checked_ts，已天然讓「採過很久 / 從沒採」的 cell 優先。
async fn pick_rotation_cells(
    pool: &DbPool,
    symbols: &[String],
    sample_size: usize,
) -> Result<Vec<(String, &'static str, &'static str, u64)>, sqlx::Error> {
    let Some(pg) = pool.get() else {
        return Ok(Vec::new());
    };
    // 取每 (symbol,timeframe) 的最近 checked_ts（未採過 → NULL）。
    let rows: Vec<(String, String, Option<chrono::DateTime<chrono::Utc>>)> = sqlx::query_as(
        "SELECT symbol, timeframe, MAX(checked_ts) AS last_checked \
         FROM research.kline_calibration \
         GROUP BY symbol, timeframe",
    )
    .fetch_all(pg)
    .await?;
    let mut last_checked: BTreeMap<(String, String), i64> = BTreeMap::new();
    for (sym, tf, ts) in rows {
        let epoch = ts.map(|t| t.timestamp()).unwrap_or(i64::MIN);
        last_checked.insert((sym, tf), epoch);
    }

    // 對全 cell（symbols × ALL_TIMEFRAMES）算排序鍵（last_checked，未採過 = i64::MIN 最優先）。
    let mut cells: Vec<(i64, String, &'static str, &'static str, u64)> = Vec::new();
    for sym in symbols {
        for (tf, bybit_iv, period_ms) in ALL_TIMEFRAMES.iter() {
            let key = (sym.clone(), tf.to_string());
            let epoch = last_checked.get(&key).copied().unwrap_or(i64::MIN);
            cells.push((epoch, sym.clone(), tf, bybit_iv, *period_ms));
        }
    }
    // 升序：最舊 checked（含從未採 i64::MIN）先。同 epoch 以 symbol 名穩定排序。
    cells.sort_by(|a, b| a.0.cmp(&b.0).then(a.1.cmp(&b.1)).then(a.2.cmp(b.2)));
    cells.truncate(sample_size);
    Ok(cells
        .into_iter()
        .map(|(_, sym, tf, iv, period)| (sym, tf, iv, period))
        .collect())
}

/// 取 market.klines 出現過的全 distinct symbol（旋轉採樣域）。唯讀。
async fn fetch_distinct_symbols(pool: &DbPool) -> Result<Vec<String>, sqlx::Error> {
    let Some(pg) = pool.get() else {
        return Ok(Vec::new());
    };
    let tfs: Vec<String> = ALL_TIMEFRAMES.iter().map(|(t, _, _)| t.to_string()).collect();
    let rows: Vec<(String,)> = sqlx::query_as(
        "SELECT DISTINCT symbol FROM market.klines WHERE timeframe = ANY($1) ORDER BY symbol",
    )
    .bind(&tfs)
    .fetch_all(pg)
    .await?;
    Ok(rows.into_iter().map(|(s,)| s).collect())
}

/// 把一筆校準判定寫 research.kline_calibration（append-only，ON CONFLICT DO NOTHING 冪等）。
#[allow(clippy::too_many_arguments)]
async fn insert_calibration_row(
    pool: &DbPool,
    run_id: &str,
    symbol: &str,
    timeframe: &str,
    window_start_ms: u64,
    window_end_ms: u64,
    m: &CalibrationMetrics,
    drift_flag: bool,
    drift_reasons: &str,
) -> Result<u64, sqlx::Error> {
    let Some(pg) = pool.get() else {
        return Ok(0);
    };
    let ws = chrono::DateTime::<chrono::Utc>::from_timestamp_millis(window_start_ms as i64);
    let we = chrono::DateTime::<chrono::Utc>::from_timestamp_millis(window_end_ms as i64);
    let (Some(ws), Some(we)) = (ws, we) else {
        return Ok(0);
    };
    // metric None → SQL NULL（fail-soft，不偽造 0）。f64 → REAL(f32)。
    let f = |o: Option<f64>| o.map(|v| v as f32);
    let result = sqlx::query(
        "INSERT INTO research.kline_calibration \
            (run_id, symbol, timeframe, window_start, window_end, \
             close_match_pct, range_ratio, corr_shift0, corr_shift1, \
             turnover_nonzero_pct, gap_pct, observed_rows, expected_rows, \
             drift_flag, drift_reasons, checker_version) \
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16) \
         ON CONFLICT (run_id, symbol, timeframe, window_start, window_end) DO NOTHING",
    )
    .bind(run_id)
    .bind(symbol)
    .bind(timeframe)
    .bind(ws)
    .bind(we)
    .bind(f(m.close_match_pct))
    .bind(f(m.range_ratio))
    .bind(f(m.corr_shift0))
    .bind(f(m.corr_shift1))
    .bind(f(m.turnover_nonzero_pct))
    .bind(f(m.gap_pct))
    .bind(m.observed_rows as i32)
    .bind(m.expected_rows as i32)
    .bind(drift_flag)
    .bind(drift_reasons)
    .bind(CHECKER_VERSION)
    .execute(pg)
    .await?;
    Ok(result.rows_affected())
}

/// drift alert 落 <DATA_DIR>/alerts/alerts.jsonl（與 helper_scripts/canary/alert_sink.py
/// append_alert_sink 同 schema：ts_utc/subject/severity/body/channels_attempted/channels_ok）。
///
/// 為什麼從 Rust 直寫同 schema（而非 shell out python）：保持 R3 bin 自足、無新 python 依賴；
/// 本告警是 research-plane 監測（subject/body 只含 symbol/tf/drift_reasons/metric 值，無 secret），
/// 故不需 redactor。fail-soft：sink 寫失敗只印 warning 不中止（告警是附加觀測面）。
fn append_drift_alert(
    symbol: &str,
    timeframe: &str,
    reasons: &str,
    m: &CalibrationMetrics,
) -> bool {
    let data_dir = env::var("OPENCLAW_DATA_DIR").unwrap_or_else(|_| "/tmp/openclaw".to_string());
    let sink_dir = PathBuf::from(&data_dir).join("alerts");
    if let Err(e) = std::fs::create_dir_all(&sink_dir) {
        eprintln!("warn: alert sink mkdir failed ({}): {e}", sink_dir.display());
        return false;
    }
    let path = sink_dir.join("alerts.jsonl");
    let ts_utc = chrono::Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string();
    let subject = format!("kline_calibration drift {symbol} {timeframe}: {reasons}");
    let body = format!(
        "intraday kline drift detected. reasons={reasons} \
         close_match={:?} range_ratio={:?} corr_shift0={:?} corr_shift1={:?} \
         turnover_nonzero={:?} gap={:?} observed={} expected={}",
        m.close_match_pct,
        m.range_ratio,
        m.corr_shift0,
        m.corr_shift1,
        m.turnover_nonzero_pct,
        m.gap_pct,
        m.observed_rows,
        m.expected_rows,
    );
    // 與 append_alert_sink 一致的 JSON record（channels_ok 恆 null：fire-and-forget 語義）。
    let record = serde_json::json!({
        "ts_utc": ts_utc,
        "subject": subject,
        "severity": "warning",
        "body": body,
        "channels_attempted": ["kline_calibration_checker"],
        "channels_ok": serde_json::Value::Null,
    });
    match std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
    {
        Ok(mut file) => {
            if let Err(e) = writeln!(file, "{}", record) {
                eprintln!("warn: alert sink write failed: {e}");
                return false;
            }
            true
        }
        Err(e) => {
            eprintln!("warn: alert sink open failed ({}): {e}", path.display());
            false
        }
    }
}

/// 對一個 (symbol, timeframe, window) cell 跑 truth-test：拉 local + bybit、對齊、算 metric。
/// 回 (metrics)；取數失敗回 None（caller 記為 fetch_error，不中止整批）。
async fn run_cell_truth_test(
    pool: &DbPool,
    mdc: &MarketDataClient,
    symbol: &str,
    timeframe: &str,
    bybit_interval: &str,
    period_ms: u64,
    window_start_ms: u64,
    window_end_ms: u64,
) -> Option<CalibrationMetrics> {
    let local = match fetch_local_bars(pool, symbol, timeframe, window_start_ms, window_end_ms).await
    {
        Ok(b) => b,
        Err(e) => {
            eprintln!("warn: {symbol} {timeframe} local fetch failed: {e}");
            return None;
        }
    };
    let bybit = match paginate_klines(
        mdc,
        CATEGORY,
        symbol,
        bybit_interval,
        window_start_ms,
        window_end_ms,
    )
    .await
    {
        Ok(b) => b,
        Err(e) => {
            eprintln!("warn: {symbol} {timeframe} bybit fetch failed: {e}");
            return None;
        }
    };
    // bybit bar 限窗 [start,end)（paginate 可能含邊界外）；對齊只比窗內交集。
    let bybit_in_window: Vec<_> = bybit
        .into_iter()
        .filter(|b| b.start_time >= window_start_ms && b.start_time < window_end_ms)
        .collect();
    let aligned = align_bars(&local, &bybit_in_window);
    let expected = expected_bars_for(window_start_ms, window_end_ms, period_ms);
    Some(compute_metrics(&aligned, local.len() as u64, expected))
}

#[tokio::main(flavor = "current_thread")]
async fn main() {
    std::process::exit(run().await);
}

async fn run() -> i32 {
    let args = match parse_args() {
        Ok(a) => a,
        Err(e) => {
            eprintln!("error: {e}");
            print_help();
            return EXIT_ARG;
        }
    };

    let db_url = match resolve_db_url() {
        Ok(u) => u,
        Err(e) => {
            eprintln!("error: {e}");
            return EXIT_DB;
        }
    };
    let db_cfg = DatabaseConfig {
        database_url: db_url,
        pool_max_connections: 2,
        pool_min_connections: 1,
        ..Default::default()
    };
    let pool = DbPool::connect(&db_cfg).await;
    if !pool.is_available() {
        eprintln!("error: database pool unavailable");
        return EXIT_DB;
    }

    // V141 preflight：缺表 fail-closed（不寫無 schema 的判定）。
    match probe_calibration_table_exists(&pool).await {
        Ok(true) => {}
        Ok(false) => {
            eprintln!(
                "error: V141 preflight FAIL — research.kline_calibration does not exist; \
                 apply V141 before running (fail-closed)"
            );
            return EXIT_DB;
        }
        Err(e) => {
            eprintln!("error: V141 preflight probe failed: {e}");
            return EXIT_DB;
        }
    }

    // REST client（market-data only；Demo 端點公開 kline，不碰執行路徑）。
    let rest = match BybitRestClient::new(BybitEnvironment::Demo, None, None) {
        Ok(c) => Arc::new(c),
        Err(e) => {
            eprintln!("error: failed to construct Bybit REST client: {e}");
            return EXIT_DB;
        }
    };
    let mdc = MarketDataClient::new(rest);

    match args.mode {
        Mode::Gate => run_gate(&args, &pool, &mdc).await,
        Mode::Monitor => run_monitor(&args, &pool, &mdc).await,
    }
}

/// R4 recal 驗收 gate：對指定窗算 metric 套 RecalGateThresholds；PASS exit 0 / FAIL exit 5。純讀。
async fn run_gate(args: &Args, pool: &DbPool, mdc: &MarketDataClient) -> i32 {
    let symbol = args.gate_symbol.as_deref().unwrap();
    let timeframe = args.gate_timeframe.as_deref().unwrap();
    let start_ms = args.gate_start_ms.unwrap();
    let end_ms = args.gate_end_ms.unwrap();
    let (_, bybit_iv, period_ms) = ALL_TIMEFRAMES
        .iter()
        .find(|(t, _, _)| *t == timeframe)
        .copied()
        .unwrap();

    println!("# mode = gate (R4 recal verify, read-only)");
    println!("# symbol = {symbol} timeframe = {timeframe}");
    println!("# window = [{start_ms}, {end_ms})");

    let Some(m) = run_cell_truth_test(
        pool, mdc, symbol, timeframe, bybit_iv, period_ms, start_ms, end_ms,
    )
    .await
    else {
        eprintln!("error: gate truth-test fetch failed for {symbol} {timeframe}");
        return EXIT_GATE_FAIL;
    };

    let verdict = evaluate_recal_gate(&m, &RecalGateThresholds::default());
    println!(
        "{symbol}\ttf={timeframe}\tcorr_shift0={:?}\trange_ratio={:?}\tclose_match={:?}\t\
         observed={}\texpected={}\tgate={}",
        m.corr_shift0,
        m.range_ratio,
        m.close_match_pct,
        m.observed_rows,
        m.expected_rows,
        if verdict.passed { "PASS" } else { "FAIL" },
    );
    if verdict.passed {
        println!("# gate PASS — recal window meets truth standard");
        EXIT_OK
    } else {
        eprintln!(
            "# gate FAIL ({}) — recal did not reach truth standard; runbook must NOT recompress",
            verdict.reasons
        );
        EXIT_GATE_FAIL
    }
}

/// R3 旋轉監測：採樣 cell、算 metric、（apply）寫表 + drift alert。
async fn run_monitor(args: &Args, pool: &DbPool, mdc: &MarketDataClient) -> i32 {
    let now_ms = openclaw_core::now_ms();
    let window_end_ms = now_ms;
    let window_start_ms = now_ms.saturating_sub(args.lookback_hours * 3_600_000);
    let run_id = uuid::Uuid::new_v4().to_string();

    let symbols = match fetch_distinct_symbols(pool).await {
        Ok(s) if !s.is_empty() => s,
        Ok(_) => {
            eprintln!("error: market.klines has 0 distinct symbols for intraday timeframes");
            return EXIT_DB;
        }
        Err(e) => {
            eprintln!("error: distinct symbols query failed: {e}");
            return EXIT_DB;
        }
    };

    let cells = match pick_rotation_cells(pool, &symbols, args.sample_size).await {
        Ok(c) => c,
        Err(e) => {
            eprintln!("error: rotation cursor query failed: {e}");
            return EXIT_DB;
        }
    };

    println!("# mode = monitor");
    println!("# apply = {}", args.apply);
    println!("# apply_gate = {}", args.apply_gate.label());
    println!("# run_id = {run_id}");
    println!("# checker_version = {CHECKER_VERSION}");
    println!("# symbols = {}", symbols.len());
    println!("# sample_size = {}", args.sample_size);
    println!("# lookback_hours = {}", args.lookback_hours);
    println!("# window = [{window_start_ms}, {window_end_ms})");
    println!("# cells = {}", cells.len());

    let thresholds = DriftThresholds::default();
    let mut drift_count = 0u64;
    let mut written = 0u64;

    for (symbol, timeframe, bybit_iv, period_ms) in &cells {
        // 窗口 floor 到該 tf 週期界（與 backfill 同；避免未收盤殘段假 partial）。
        let w_end = (window_end_ms / period_ms) * period_ms;
        let w_start = (window_start_ms / period_ms) * period_ms;

        let Some(m) = run_cell_truth_test(
            pool, mdc, symbol, timeframe, bybit_iv, *period_ms, w_start, w_end,
        )
        .await
        else {
            println!("{symbol}\ttf={timeframe}\tstatus=fetch_error");
            continue;
        };

        let verdict = evaluate_drift(&m, &thresholds);
        if verdict.drift_flag {
            drift_count += 1;
        }
        println!(
            "{symbol}\ttf={timeframe}\tclose_match={:?}\trange_ratio={:?}\tcorr0={:?}\t\
             corr1={:?}\tturnover_nz={:?}\tgap={:?}\tobs={}\texp={}\tdrift={}\treasons={}",
            m.close_match_pct,
            m.range_ratio,
            m.corr_shift0,
            m.corr_shift1,
            m.turnover_nonzero_pct,
            m.gap_pct,
            m.observed_rows,
            m.expected_rows,
            verdict.drift_flag,
            verdict.reasons,
        );

        if args.apply {
            match insert_calibration_row(
                pool,
                &run_id,
                symbol,
                timeframe,
                w_start,
                w_end,
                &m,
                verdict.drift_flag,
                &verdict.reasons,
            )
            .await
            {
                Ok(n) => written += n,
                Err(e) => {
                    eprintln!("error: calibration row insert failed for {symbol} {timeframe}: {e}");
                    return EXIT_DB;
                }
            }
            // drift → 既有耐久 alert sink（fail-soft）。
            if verdict.drift_flag {
                append_drift_alert(symbol, timeframe, &verdict.reasons, &m);
            }
        }
    }

    if !args.apply {
        println!("# dry-run: no rows written, no alerts emitted");
    }
    println!("# drift_cells = {drift_count}");
    println!("# rows_written = {written}");
    EXIT_OK
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parse(argv: &[&str], env_gate: bool) -> Result<Args, String> {
        parse_args_from(argv.iter().map(|s| (*s).to_string()), env_gate)
    }

    #[test]
    fn test_default_monitor_dry_run() {
        let a = parse(&[], false).expect("default should parse");
        assert_eq!(a.mode, Mode::Monitor);
        assert!(!a.apply);
        assert_eq!(a.apply_gate, ApplyGate::None);
        assert_eq!(a.sample_size, 30);
        assert_eq!(a.lookback_hours, 48);
    }

    #[test]
    fn test_env_gate_enables_monitor_apply() {
        let a = parse(&[], true).expect("env-gated apply should parse");
        assert!(a.apply);
        assert_eq!(a.apply_gate, ApplyGate::Env);
        assert!(!a.i_understand);
    }

    #[test]
    fn test_dry_run_cli_overrides_env_gate() {
        let a = parse(&["--dry-run"], true).expect("dry-run should parse");
        assert!(!a.apply);
        assert_eq!(a.apply_gate, ApplyGate::None);
    }

    #[test]
    fn test_apply_without_ack_or_env_rejected() {
        let err = parse(&["--apply"], false).expect_err("unguarded apply must fail");
        assert!(err.contains(APPLY_ENV));
    }

    #[test]
    fn test_manual_apply_ack_works() {
        let a = parse(&["--apply", "--i-understand-this-modifies-db"], false)
            .expect("manual apply ack should parse");
        assert!(a.apply);
        assert_eq!(a.apply_gate, ApplyGate::CliAck);
    }

    #[test]
    fn test_force_flags_rejected() {
        let err = parse(&["--force"], true).expect_err("force flag must stay rejected");
        assert!(err.contains("rejected flag --force"));
    }

    #[test]
    fn test_gate_requires_all_four_params() {
        // --gate 缺參數 → 拒。
        let err = parse(&["--gate", "--symbol", "BTCUSDT"], false)
            .expect_err("gate without full params must fail");
        assert!(err.contains("--gate requires"));
        // 齊全 → 通過。
        let a = parse(
            &[
                "--gate", "--symbol", "BTCUSDT", "--timeframe", "1m", "--start-ms", "1000",
                "--end-ms", "2000",
            ],
            false,
        )
        .expect("full gate params should parse");
        assert_eq!(a.mode, Mode::Gate);
        assert_eq!(a.gate_symbol.as_deref(), Some("BTCUSDT"));
        assert_eq!(a.gate_timeframe.as_deref(), Some("1m"));
        assert_eq!(a.gate_start_ms, Some(1000));
        assert_eq!(a.gate_end_ms, Some(2000));
    }

    #[test]
    fn test_gate_unknown_timeframe_rejected() {
        let err = parse(
            &[
                "--gate", "--symbol", "BTCUSDT", "--timeframe", "3m", "--start-ms", "1000",
                "--end-ms", "2000",
            ],
            false,
        )
        .expect_err("unknown timeframe must fail");
        assert!(err.contains("--gate --timeframe expects one of"));
    }

    #[test]
    fn test_gate_start_not_before_end_rejected() {
        let err = parse(
            &[
                "--gate", "--symbol", "BTCUSDT", "--timeframe", "1m", "--start-ms", "2000",
                "--end-ms", "1000",
            ],
            false,
        )
        .expect_err("start>=end must fail");
        assert!(err.contains("must be strictly before"));
    }

    #[test]
    fn test_gate_env_gate_irrelevant() {
        // --gate 純讀：即使 env gate on 也不需 apply ack（gate 不寫表）。
        let a = parse(
            &[
                "--gate", "--symbol", "BTCUSDT", "--timeframe", "1m", "--start-ms", "1000",
                "--end-ms", "2000",
            ],
            true,
        )
        .expect("gate with env on should parse without apply ack");
        assert_eq!(a.mode, Mode::Gate);
        assert!(!a.apply);
    }

    #[test]
    fn test_sample_size_and_lookback_zero_rejected() {
        assert!(parse(&["--sample-size", "0"], false).is_err());
        assert!(parse(&["--lookback-hours", "0"], false).is_err());
        let a = parse(&["--sample-size", "10", "--lookback-hours", "24"], false).unwrap();
        assert_eq!(a.sample_size, 10);
        assert_eq!(a.lookback_hours, 24);
    }
}
