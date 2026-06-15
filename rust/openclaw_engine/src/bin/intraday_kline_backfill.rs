//! Intraday（1m/5m/15m/1h/4h）K 線歷史回填 CLI（research-unblock 交付物 A）。
//!
//! MODULE_NOTE
//! 模塊用途：用 Bybit REST aggregated-candle 路徑（與正確的 daily 回填同源）把 intraday
//!   OHLCV 嚴格解析後寫 market.klines + research.alpha_klines_provenance，取代 live WebSocket
//!   tick-synth 路徑產生的退化單快照 bar。鏡像 daily_kline_backfill 的安全骨架：dry-run 預設、
//!   --apply / env gate、V125 preflight fail-closed、EXIT code、sequential per-symbol 防 burst。
//! 與 daily 的唯一差異：
//!   1. --interval {1|5|15|60|240} 選 Bybit kline interval，映射 period_ms 與 DB timeframe 標籤
//!      （1→1m / 5→5m / 15→15m / 60→1h / 240→4h）；可重複指定多 interval（內部 loop）。
//!   2. 預設不指定 interval 時跑全 5 個（與 daily 單一 "D" 不同）。
//!   3. dry-run 印每 symbol×interval 的估計頁數（1000-bar 分頁 rate-limit math，PA §3 要求）。
//!   4. 窗口起止：--start/--end（UTC 日界，--end 含當天）覆蓋 --lookback-days；皆缺時用 lookback。
//!   5. symbol 集：預設 toml universe；--symbol 限單一；--symbols-from-db 取本次 timeframe 集的
//!      market.klines distinct symbol（與 toml 選項互斥）。
//!   6.【本工具本次用途】apply 預設衝突策略 = vol+turnover-only（DO UPDATE SET volume,turnover），
//!      既有行的 open/high/low/close/tick_count 一律不動；--upsert-overwrite 才顯式升級到全覆蓋。
//! 依賴：openclaw_engine::backfill::{daily_kline_backfill（泛化通用版 fn）, writer}、
//!   market_data_client、database::pool、bybit_rest_client、secret_env、
//!   settings/backfill_universe.toml。
//! 硬邊界：
//!   1. 預設 dry-run（只取數 + 算 coverage + 印估計頁數，不寫 DB）；apply 需 --apply +
//!      --i-understand-this-modifies-db 或 OPENCLAW_INTRADAY_KLINE_BACKFILL_APPLY=1。
//!   2. V125 preflight：research.alpha_klines_provenance 缺表即 fail-closed 退出（EXIT_DB）。
//!   3. 純讀市場 + append-only provenance；不下單、不餵 intent、不碰 auth/lease/system_mode。
//!   4.【衝突關鍵】apply 預設走 vol+turnover-only DO UPDATE（write_klines_vol_turnover_only）：只校正
//!      live tick-synth 路徑常缺/失真的 volume+turnover，絕不改寫 OHLC（保護 outcome_backfiller 讀的
//!      close-依賴歷史歸因，root principle #8）。--upsert-overwrite 顯式升級到全 OHLCV 覆蓋
//!      （write_klines_strict_overwrite，DO UPDATE）—— 壓縮 hypertable 上仍需 operator decompress，
//!      仍在 apply gate 後。兩種 apply 模式皆 DO UPDATE（命中行 rows_affected=1），無 DO NOTHING 靜默
//!      no-op 風險。不改 live writer 的 DO NOTHING（market_writer.rs 不變）。
//! 運維前置：kline 取數走既有 signed GET（get_klines → get_checked → get，HMAC-SHA256），
//!   依賴 demo secret slot 憑證；Demo 空憑證不建構失敗，fail-closed 在首次 get() →
//!   NoCredentials → 該 symbol 記 failed coverage(observed=0)，cron 須檢 coverage 非僅看 exit。

use std::env;
use std::path::PathBuf;

use openclaw_engine::backfill::daily_kline_backfill::{
    expected_bars_for, paginate_klines, strict_filter_closed_bars_for, CoverageVerdict,
    KLINE_PAGE_LIMIT,
};
use openclaw_engine::backfill::writer::{
    distinct_symbols_for_timeframes as writer_distinct_symbols, insert_provenance_row,
    probe_provenance_table_exists, write_klines_strict_overwrite, write_klines_vol_turnover_only,
    ProvenanceRow,
};
use openclaw_engine::bybit_rest_client::{BybitEnvironment, BybitRestClient};
use openclaw_engine::database::pool::DbPool;
use openclaw_engine::database::DatabaseConfig;
use openclaw_engine::market_data_client::MarketDataClient;
use openclaw_engine::secret_env;
use serde::Deserialize;
use std::sync::Arc;

const EXIT_OK: i32 = 0;
const EXIT_ARG: i32 = 2;
const EXIT_DB: i32 = 4;
const APPLY_ENV: &str = "OPENCLAW_INTRADAY_KLINE_BACKFILL_APPLY";
/// Bybit kline 端點識別（落 provenance.endpoint_id）。
const ENDPOINT_ID: &str = "GET /v5/market/kline";
/// parser 版本標記（落 provenance.parser_version）。strict-parse 邏輯變動時遞增。
/// 與 daily 的 daily_kline_strict_v1 區分（同 strict 核心，但 intraday 週期 + 標籤）。
const PARSER_VERSION: &str = "intraday_kline_strict_v1";

/// intraday 各 interval 預設全集（不指定 --interval 時跑全部）。
/// 順序對齊 PA §3 微結構優先：1m/5m 先（log-return），再 15m/1h，最後 4h（residual reader 讀 '4h'）。
const DEFAULT_INTERVALS: [&str; 5] = ["1", "5", "15", "60", "240"];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Mode {
    DryRun,
    Apply,
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

/// 一個 Bybit kline interval 的解析結果：週期毫秒 + DB timeframe 標籤。
///
/// 為什麼集中映射在此（單一 SSOT）：Bybit interval（"1"/"5"/"15"/"60"/"240"）、period_ms
/// （60000/300000/900000/3600000/14400000）、DB timeframe 標籤（"1m"/"5m"/"15m"/"1h"/"4h"）
/// 三者必須同步；任一 typo 都會寫錯 timeframe 或算錯 expected。映射錯誤 fail-closed（拒 arg）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct IntervalSpec {
    /// Bybit kline interval request 值（送 get_klines 的 interval 參數）。
    bybit_interval: &'static str,
    /// 一根 bar 的毫秒週期。
    period_ms: u64,
    /// market.klines / provenance 的 timeframe 標籤。
    timeframe: &'static str,
}

/// 把 CLI --interval 值映射為 IntervalSpec；未知值 fail-closed 回 None。
///
/// 註：4h（240）live 無 producer，但消費者（residual_alpha_producer_db.py）讀 timeframe='4h'，
/// 故仍可回填（PA §2 deliverable A 明列）。
fn resolve_interval(raw: &str) -> Option<IntervalSpec> {
    match raw.trim() {
        "1" => Some(IntervalSpec {
            bybit_interval: "1",
            period_ms: 60_000,
            timeframe: "1m",
        }),
        "5" => Some(IntervalSpec {
            bybit_interval: "5",
            period_ms: 300_000,
            timeframe: "5m",
        }),
        "15" => Some(IntervalSpec {
            bybit_interval: "15",
            period_ms: 900_000,
            timeframe: "15m",
        }),
        "60" => Some(IntervalSpec {
            bybit_interval: "60",
            period_ms: 3_600_000,
            timeframe: "1h",
        }),
        "240" => Some(IntervalSpec {
            bybit_interval: "240",
            period_ms: 14_400_000,
            timeframe: "4h",
        }),
        _ => None,
    }
}

/// 把 YYYY-MM-DD（UTC 日界 00:00:00）解析為 ms epoch；格式非法或溢出 fail-closed 回 None。
///
/// 為什麼 UTC 日界 + fail-closed：回填窗口語意必須與 market.klines 的 UTC ts 對齊；
/// 解析失敗不可退默認（會悄悄回填錯窗），交由 caller 拒 arg 退出。
fn parse_utc_date_ms(raw: &str) -> Option<u64> {
    let date = chrono::NaiveDate::parse_from_str(raw.trim(), "%Y-%m-%d").ok()?;
    let dt = date.and_hms_opt(0, 0, 0)?.and_utc();
    u64::try_from(dt.timestamp_millis()).ok()
}

/// settings/backfill_universe.toml 反序列化結構（與 daily 共用同一檔/結構）。
#[derive(Debug, Clone, Deserialize)]
struct UniverseFile {
    backfill_universe: UniverseConfig,
}

#[derive(Debug, Clone, Deserialize)]
struct UniverseConfig {
    category: String,
    lookback_days: u32,
    symbols: Vec<String>,
}

#[derive(Debug, Clone)]
struct Args {
    mode: Mode,
    apply_gate: ApplyGate,
    i_understand: bool,
    /// 覆蓋 universe TOML 的 lookback_days（None 用檔內值）。
    lookback_days_override: Option<u32>,
    /// 明確回填起點（--start YYYY-MM-DD 的 UTC 日界 00:00:00 ms epoch；None 用 lookback）。
    start_ms: Option<u64>,
    /// 明確回填終點（--end YYYY-MM-DD 的「當天含」UTC 日界，即隔日 00:00:00 ms epoch；None 用 now）。
    end_ms: Option<u64>,
    /// 限定單一 symbol（None 用 universe 全集）。
    symbol: Option<String>,
    /// 取目標 timeframe 的 DB distinct symbol 集（替代 toml universe；與 toml 互斥）。
    symbols_from_db: bool,
    /// 指定的 interval 集（空 = 用 DEFAULT_INTERVALS 全 5 個）。已解析去重。
    intervals: Vec<IntervalSpec>,
    /// universe TOML 路徑（None 用 <OPENCLAW_BASE_DIR>/settings/backfill_universe.toml）。
    universe_config: Option<PathBuf>,
    /// apply 模式下用 DO UPDATE 覆蓋既有行（PA Option A 替代手動 DELETE；仍 operator-gated）。
    upsert_overwrite: bool,
    /// git sha（落 provenance；caller 提供，engine 無 build.rs 嵌入）。
    git_sha: Option<String>,
    /// git dirty 旗標（落 provenance）。
    git_dirty: Option<bool>,
}

impl Default for Args {
    fn default() -> Self {
        Self {
            mode: Mode::DryRun,
            apply_gate: ApplyGate::None,
            i_understand: false,
            lookback_days_override: None,
            start_ms: None,
            end_ms: None,
            symbol: None,
            symbols_from_db: false,
            intervals: Vec::new(),
            universe_config: None,
            upsert_overwrite: false,
            git_sha: None,
            git_dirty: None,
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
    let mut mode_set_by_cli = false;
    let mut it = iter.into_iter().peekable();

    while let Some(arg) = it.next() {
        match arg.as_str() {
            "--dry-run" | "--verify" => {
                args.mode = Mode::DryRun;
                args.apply_gate = ApplyGate::None;
                mode_set_by_cli = true;
            }
            "--apply" => {
                args.mode = Mode::Apply;
                args.apply_gate = ApplyGate::CliAck;
                mode_set_by_cli = true;
            }
            "--i-understand-this-modifies-db" => args.i_understand = true,
            "--upsert-overwrite" => args.upsert_overwrite = true,
            "--interval" => {
                let raw = parse_next_string(&mut it, "--interval")?;
                let spec = resolve_interval(&raw).ok_or_else(|| {
                    format!("--interval expects one of 1|5|15|60|240, got {raw}")
                })?;
                // 去重（同 interval 多次指定只跑一次）。
                if !args.intervals.iter().any(|s| s.timeframe == spec.timeframe) {
                    args.intervals.push(spec);
                }
            }
            "--lookback-days" => {
                args.lookback_days_override = Some(parse_next_u32(&mut it, "--lookback-days")?)
            }
            "--start" => {
                let raw = parse_next_string(&mut it, "--start")?;
                let ms = parse_utc_date_ms(&raw)
                    .ok_or_else(|| format!("--start expects YYYY-MM-DD (UTC), got {raw}"))?;
                args.start_ms = Some(ms);
            }
            "--end" => {
                let raw = parse_next_string(&mut it, "--end")?;
                // --end 含當天：把 YYYY-MM-DD 的 UTC 00:00 推進到隔日 00:00（半開區間上界）。
                let day_start = parse_utc_date_ms(&raw)
                    .ok_or_else(|| format!("--end expects YYYY-MM-DD (UTC), got {raw}"))?;
                args.end_ms = Some(day_start.saturating_add(86_400_000_u64));
            }
            "--symbols-from-db" => args.symbols_from_db = true,
            "--symbol" => args.symbol = Some(parse_next_string(&mut it, "--symbol")?),
            "--universe-config" => {
                args.universe_config = Some(PathBuf::from(parse_next_string(
                    &mut it,
                    "--universe-config",
                )?))
            }
            "--git-sha" => args.git_sha = Some(parse_next_string(&mut it, "--git-sha")?),
            "--git-dirty" => {
                let v = parse_next_string(&mut it, "--git-dirty")?;
                args.git_dirty = Some(match v.as_str() {
                    "true" | "1" | "dirty" => true,
                    "false" | "0" | "clean" => false,
                    other => return Err(format!("--git-dirty expects true/false, got {other}")),
                });
            }
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

    if apply_env && !mode_set_by_cli {
        args.mode = Mode::Apply;
        args.apply_gate = ApplyGate::Env;
    }

    if args.mode == Mode::Apply {
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
    if let Some(0) = args.lookback_days_override {
        return Err("--lookback-days must be > 0".to_string());
    }
    // --start / --end 範圍校驗：兩者皆給時 start 必須嚴格早於 end（半開區間 [start, end)）。
    if let (Some(s), Some(e)) = (args.start_ms, args.end_ms) {
        if s >= e {
            return Err("--start must be strictly before --end".to_string());
        }
    }
    // --symbols-from-db 與 toml-universe 選項互斥：避免「DB 全集」與「toml 子集」語意混淆。
    if args.symbols_from_db {
        if args.symbol.is_some() {
            return Err("--symbols-from-db is mutually exclusive with --symbol".to_string());
        }
        if args.universe_config.is_some() {
            return Err(
                "--symbols-from-db is mutually exclusive with --universe-config".to_string(),
            );
        }
    }
    // --upsert-overwrite 只在 apply 模式有意義；dry-run 下指定即拒（避免誤以為 dry-run 會覆蓋）。
    if args.upsert_overwrite && args.mode != Mode::Apply {
        return Err("--upsert-overwrite requires --apply (DO UPDATE only happens on apply)".to_string());
    }
    // 未指定 --interval：用全 5 個預設 interval。
    if args.intervals.is_empty() {
        args.intervals = DEFAULT_INTERVALS
            .iter()
            .filter_map(|s| resolve_interval(s))
            .collect();
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

fn parse_next_u32(
    it: &mut std::iter::Peekable<impl Iterator<Item = String>>,
    flag: &str,
) -> Result<u32, String> {
    parse_next_string(it, flag)?
        .parse::<u32>()
        .map_err(|e| format!("{flag} expects u32: {e}"))
}

fn print_help() {
    println!(
        "intraday_kline_backfill — backfill historical 1m/5m/15m/1h/4h klines via REST aggregated candles\n\
         \n\
         USAGE:\n  \
           intraday_kline_backfill [--dry-run] [--interval 1|5|15|60|240]... [--lookback-days N] [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--symbol BTCUSDT | --symbols-from-db] [--universe-config PATH]\n  \
           intraday_kline_backfill --apply --i-understand-this-modifies-db [--upsert-overwrite] [--git-sha SHA] [--git-dirty true|false] [options]\n  \
           OPENCLAW_INTRADAY_KLINE_BACKFILL_APPLY=1 intraday_kline_backfill [options]\n\
         \n\
         INTERVALS (omit --interval to run all five; 1m/5m first for microstructure):\n  \
           1=1m  5=5m  15=15m  60=1h  240=4h  (4h has no live producer; consumers read timeframe='4h')\n\
         DATE RANGE (UTC; overrides --lookback-days):\n  \
           --start YYYY-MM-DD  inclusive day start (UTC 00:00)\n  \
           --end   YYYY-MM-DD  inclusive of that whole day (clamped to now; floored per interval)\n\
         SYMBOL SET:\n  \
           default = toml universe (curated, reviewed subset)\n  \
           --symbol BTCUSDT     single symbol (must be in toml universe)\n  \
           --symbols-from-db    DISTINCT symbols in market.klines for the selected timeframes\n  \
                                (mutually exclusive with --symbol / --universe-config)\n\
         WRITES (apply mode):\n  \
           market.klines (timeframe in {{1m,5m,15m,1h,4h}}) — SAME PK as live rows\n  \
           research.alpha_klines_provenance (append-only coverage ledger)\n\
         CONFLICT STRATEGY (apply mode default = SAFE vol+turnover-only):\n  \
           default: ON CONFLICT DO UPDATE SET volume, turnover ONLY — never touches\n  \
             open/high/low/close/tick_count (protects close-dependent outcome_backfiller history).\n  \
           --upsert-overwrite: explicit upgrade to full OHLCV+tick_count overwrite (DO UPDATE),\n  \
             still behind the apply gate; needs operator decompress on compressed chunks.\n\
         PREFLIGHT:\n  \
           research.alpha_klines_provenance must exist (V125 applied); missing => fail-closed exit\n\
         CONFIG:\n  \
           <OPENCLAW_BASE_DIR>/settings/backfill_universe.toml (fixed liquid universe; QC/MIT review pending)\n\
         ENV:\n  \
           OPENCLAW_DATABASE_URL or OPENCLAW_DATABASE_URL_FILE\n  \
           OPENCLAW_BASE_DIR (settings root; defaults to .)\n  \
           OPENCLAW_INTRADAY_KLINE_BACKFILL_APPLY=1 enables scheduled apply without CLI ack flags\n"
    );
}

fn resolve_db_url() -> Result<String, String> {
    secret_env::var_or_file("OPENCLAW_DATABASE_URL")
        .filter(|s| !s.is_empty())
        .ok_or_else(|| "OPENCLAW_DATABASE_URL or OPENCLAW_DATABASE_URL_FILE not set".to_string())
}

/// 解析 universe TOML 路徑：--universe-config 優先，否則 <OPENCLAW_BASE_DIR>/settings/...。
/// 為什麼用 OPENCLAW_BASE_DIR（預設 "."）：跨平台不硬編碼絕對路徑（CLAUDE §六 / 跨平台準則）。
fn resolve_universe_path(args: &Args) -> PathBuf {
    if let Some(p) = &args.universe_config {
        return p.clone();
    }
    let base = env::var("OPENCLAW_BASE_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("."));
    base.join("settings").join("backfill_universe.toml")
}

fn load_universe(path: &PathBuf) -> Result<UniverseConfig, String> {
    let content = std::fs::read_to_string(path)
        .map_err(|e| format!("read universe config {}: {}", path.display(), e))?;
    let parsed: UniverseFile = toml::from_str(&content)
        .map_err(|e| format!("parse universe config {}: {}", path.display(), e))?;
    if parsed.backfill_universe.symbols.is_empty() {
        return Err(format!(
            "universe config {} has empty symbols list",
            path.display()
        ));
    }
    Ok(parsed.backfill_universe)
}

/// 估計單一 symbol×interval 窗口的 1000-bar 分頁頁數（rate-limit math，PA §3 dry-run 要求）。
///
/// expected bar 數 / KLINE_PAGE_LIMIT 向上取整 = 至少需要的頁數（每頁取滿 1000）。
/// 為什麼是估計：實際頁數受 Bybit 回傳是否取滿、游標推進影響，但「expected/1000 ceil」是
/// 可預測的下界估計，足供 operator 評估 apply 前的請求量級（1m×180d≈260 頁/symbol）。
fn estimate_pages(window_start_ms: u64, window_end_ms: u64, period_ms: u64) -> u64 {
    let bars = expected_bars_for(window_start_ms, window_end_ms, period_ms);
    if bars == 0 {
        return 0;
    }
    bars.div_ceil(KLINE_PAGE_LIMIT as u64)
}

#[tokio::main(flavor = "current_thread")]
async fn main() {
    std::process::exit(run().await);
}

async fn run() -> i32 {
    let args = match parse_args() {
        Ok(args) => args,
        Err(e) => {
            eprintln!("error: {e}");
            print_help();
            return EXIT_ARG;
        }
    };

    let universe_path = resolve_universe_path(&args);
    let universe = match load_universe(&universe_path) {
        Ok(u) => u,
        Err(e) => {
            eprintln!("error: {e}");
            return EXIT_ARG;
        }
    };

    let lookback_days = args.lookback_days_override.unwrap_or(universe.lookback_days);
    let now_ms = openclaw_core::now_ms();
    let run_id = uuid::Uuid::new_v4().to_string();

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

    // symbol 子集解析：
    //   --symbols-from-db → 取本次 timeframe 集的 DB distinct symbol（忽略 toml universe）；
    //   --symbol         → 限定單一（必須在 toml universe 內，避免回填未復核標的）；
    //   否則              → toml universe 全集。
    let symbols: Vec<String> = if args.symbols_from_db {
        let timeframes: Vec<String> =
            args.intervals.iter().map(|s| s.timeframe.to_string()).collect();
        match writer_distinct_symbols(&pool, &timeframes).await {
            Ok(s) if !s.is_empty() => s,
            Ok(_) => {
                eprintln!(
                    "error: --symbols-from-db returned 0 symbols for timeframes [{}] \
                     (market.klines empty for these timeframes?)",
                    timeframes.join(",")
                );
                return EXIT_DB;
            }
            Err(e) => {
                eprintln!("error: --symbols-from-db query failed: {e}");
                return EXIT_DB;
            }
        }
    } else {
        match &args.symbol {
            Some(s) => {
                if !universe.symbols.iter().any(|u| u == s) {
                    eprintln!(
                        "error: --symbol {s} not in universe config {}",
                        universe_path.display()
                    );
                    return EXIT_ARG;
                }
                vec![s.clone()]
            }
            None => universe.symbols.clone(),
        }
    };

    // V125 preflight：provenance 帳本缺表即 fail-closed（不寫無來源帳的 OHLCV）。
    match probe_provenance_table_exists(&pool).await {
        Ok(true) => {}
        Ok(false) => {
            eprintln!(
                "error: V125 preflight FAIL — research.alpha_klines_provenance does not exist; \
                 apply V125 before backfill (fail-closed)"
            );
            return EXIT_DB;
        }
        Err(e) => {
            eprintln!("error: V125 preflight probe failed: {e}");
            return EXIT_DB;
        }
    }

    // REST client（market-data only；Demo 端點，回填只讀公開 kline，不碰主網執行路徑）。
    // 與 daily 同：signed GET（HMAC-SHA256），Demo 空憑證不建構失敗，fail-closed 在 request time
    // （首次 get() → NoCredentials → 該 symbol 記 failed coverage(observed=0)，不中止整批）。
    let rest = match BybitRestClient::new(BybitEnvironment::Demo, None, None) {
        Ok(c) => Arc::new(c),
        Err(e) => {
            eprintln!("error: failed to construct Bybit REST client: {e}");
            return EXIT_DB;
        }
    };
    let mdc = MarketDataClient::new(rest);

    println!("# mode = {:?}", args.mode);
    println!("# apply_gate = {}", args.apply_gate.label());
    println!("# upsert_overwrite = {}", args.upsert_overwrite);
    println!("# run_id = {run_id}");
    println!("# parser_version = {PARSER_VERSION}");
    println!("# endpoint_id = {ENDPOINT_ID}");
    println!("# universe_config = {}", universe_path.display());
    println!("# symbol_source = {}", if args.symbols_from_db { "db-distinct" } else { "toml-universe" });
    println!("# category = {}", universe.category);
    println!("# lookback_days = {lookback_days}");
    println!(
        "# start = {}",
        args.start_ms
            .map(|m| m.to_string())
            .unwrap_or_else(|| "(lookback)".to_string())
    );
    println!(
        "# end = {}",
        args.end_ms
            .map(|m| m.to_string())
            .unwrap_or_else(|| "(now)".to_string())
    );
    println!(
        "# intervals = {}",
        args.intervals
            .iter()
            .map(|s| s.timeframe)
            .collect::<Vec<_>>()
            .join(",")
    );
    println!("# symbols = {}", symbols.len());
    println!("# git_sha = {}", args.git_sha.as_deref().unwrap_or("(none)"));

    let mut total_observed: u64 = 0;
    let mut total_inserted: u64 = 0;

    // 外層 interval、內層 symbol：每 (interval, symbol) 一個分頁迴圈，sequential 防 burst。
    // window_end 對齊到該 interval 的最後一個完整收盤週期界（floor 到 period_ms），
    // 與 daily 的 UTC 日界 floor 同理（FIX-1：避免未收盤殘段造成結構性假性 partial）。
    //
    // 窗口起止來源（--start/--end 覆蓋 lookback）：
    //   end_raw = --end（含當天，已轉隔日 00:00）或 now；再 min(now) 不取未來，再 floor 到 period。
    //   start   = --start（UTC 日界）或 (end - lookback_days)；start 亦 floor 到 period 對齊。
    let end_raw_ms = args.end_ms.unwrap_or(now_ms).min(now_ms);
    for spec in &args.intervals {
        let window_end_ms = (end_raw_ms / spec.period_ms) * spec.period_ms;
        let window_start_raw = args
            .start_ms
            .unwrap_or_else(|| window_end_ms.saturating_sub(lookback_days as u64 * 86_400_000_u64));
        let window_start_ms = (window_start_raw / spec.period_ms) * spec.period_ms;

        for symbol in &symbols {
            let est_pages = estimate_pages(window_start_ms, window_end_ms, spec.period_ms);
            let est_bars = expected_bars_for(window_start_ms, window_end_ms, spec.period_ms);

            if args.mode == Mode::DryRun {
                // dry-run：印估計頁數 + 估計 bar 數（rate-limit math），不取數不寫庫。
                println!(
                    "{symbol}\ttf={}\test_bars={est_bars}\test_pages={est_pages}\t(dry-run: no fetch)",
                    spec.timeframe
                );
                continue;
            }

            // apply 模式：真取數 + strict-parse + 寫庫。
            let request_start_ms = openclaw_core::now_ms();
            let raw = match paginate_klines(
                &mdc,
                &universe.category,
                symbol,
                spec.bybit_interval,
                window_start_ms,
                window_end_ms,
            )
            .await
            {
                Ok(bars) => bars,
                Err(e) => {
                    // 單 (symbol, interval) 取數失敗：記 failed coverage（observed=0），不中止整批。
                    eprintln!("warn: {symbol} {} fetch failed: {e}", spec.timeframe);
                    let request_end_ms = openclaw_core::now_ms();
                    let page = strict_filter_closed_bars_for(
                        symbol,
                        &[],
                        window_start_ms,
                        window_end_ms,
                        now_ms,
                        spec.period_ms,
                        spec.timeframe,
                    );
                    println!(
                        "{symbol}\ttf={}\tstatus={}\texpected={}\tobserved={}\tinserted=0\t(fetch_error)",
                        spec.timeframe,
                        page.verdict.status.as_db_str(),
                        page.verdict.expected,
                        page.verdict.observed,
                    );
                    let prov = build_provenance(
                        &run_id,
                        &universe.category,
                        symbol,
                        spec.timeframe,
                        window_start_ms,
                        window_end_ms,
                        Some(request_start_ms),
                        Some(request_end_ms),
                        &args,
                        &page.verdict,
                    );
                    if let Err(e) = insert_provenance_row(&pool, &prov).await {
                        eprintln!("error: provenance insert failed for {symbol} {}: {e}", spec.timeframe);
                        return EXIT_DB;
                    }
                    continue;
                }
            };
            let request_end_ms = openclaw_core::now_ms();

            let page = strict_filter_closed_bars_for(
                symbol,
                &raw,
                window_start_ms,
                window_end_ms,
                now_ms,
                spec.period_ms,
                spec.timeframe,
            );
            total_observed += page.verdict.observed;

            // 衝突策略（本工具本次用途的預設）：--upsert-overwrite → DO UPDATE 全覆蓋；
            // 否則走 vol+turnover-only（DO UPDATE SET volume,turnover），既有行的
            // open/high/low/close/tick_count 一律不動，保護 outcome_backfiller 的歷史歸因。
            let write_result = if args.upsert_overwrite {
                write_klines_strict_overwrite(&pool, &page).await
            } else {
                write_klines_vol_turnover_only(&pool, &page).await
            };
            let summary = match write_result {
                Ok(s) => s,
                Err(e) => {
                    eprintln!("error: klines write failed for {symbol} {}: {e}", spec.timeframe);
                    return EXIT_DB;
                }
            };
            total_inserted += summary.inserted;

            // 兩種 apply 模式皆走 DO UPDATE（命中行 rows_affected=1），不再有 DO NOTHING
            // 靜默 no-op 風險；故不再追蹤 blocked window（inserted==attempted 為常態）。
            println!(
                "{symbol}\ttf={}\tstatus={}\texpected={}\tobserved={}\tattempted={}\tinserted={}",
                spec.timeframe,
                page.verdict.status.as_db_str(),
                page.verdict.expected,
                page.verdict.observed,
                summary.attempted,
                summary.inserted,
            );

            let prov = build_provenance(
                &run_id,
                &universe.category,
                symbol,
                spec.timeframe,
                window_start_ms,
                window_end_ms,
                Some(request_start_ms),
                Some(request_end_ms),
                &args,
                &page.verdict,
            );
            if let Err(e) = insert_provenance_row(&pool, &prov).await {
                eprintln!("error: provenance insert failed for {symbol} {}: {e}", spec.timeframe);
                return EXIT_DB;
            }
        }
    }

    if args.mode == Mode::DryRun {
        println!("# dry-run: no rows written (klines or provenance); est_pages = pagination estimate");
        return EXIT_OK;
    }

    println!("# total_observed = {total_observed}");
    println!("# total_inserted = {total_inserted}");
    EXIT_OK
}

/// 由覆蓋率判定組裝 provenance row（純資料搬運，無副作用）。
#[allow(clippy::too_many_arguments)]
fn build_provenance(
    run_id: &str,
    category: &str,
    symbol: &str,
    timeframe: &str,
    window_start_ms: u64,
    window_end_ms: u64,
    request_start_ms: Option<u64>,
    request_end_ms: Option<u64>,
    args: &Args,
    verdict: &CoverageVerdict,
) -> ProvenanceRow {
    ProvenanceRow {
        run_id: run_id.to_string(),
        endpoint_id: ENDPOINT_ID.to_string(),
        category: category.to_string(),
        symbol: symbol.to_string(),
        timeframe: timeframe.to_string(),
        window_start_ms,
        window_end_ms,
        request_start_ms,
        request_end_ms,
        parser_version: PARSER_VERSION.to_string(),
        git_sha: args.git_sha.clone(),
        git_dirty: args.git_dirty,
        payload_sha256: verdict.payload_sha256.clone(),
        coverage_status: verdict.status.as_db_str().to_string(),
        expected_rows: verdict.expected,
        observed_rows: verdict.observed,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parse(argv: &[&str], env_gate: bool) -> Result<Args, String> {
        parse_args_from(argv.iter().map(|s| (*s).to_string()), env_gate)
    }

    #[test]
    fn test_default_is_dry_run_all_intervals() {
        let args = parse(&[], false).expect("default should parse");
        assert_eq!(args.mode, Mode::DryRun);
        assert_eq!(args.apply_gate, ApplyGate::None);
        // 未指定 --interval → 全 5 個。
        assert_eq!(args.intervals.len(), 5);
        let tfs: Vec<&str> = args.intervals.iter().map(|s| s.timeframe).collect();
        assert_eq!(tfs, vec!["1m", "5m", "15m", "1h", "4h"]);
    }

    #[test]
    fn test_env_gate_enables_apply() {
        let args = parse(&[], true).expect("env-gated apply should parse");
        assert_eq!(args.mode, Mode::Apply);
        assert_eq!(args.apply_gate, ApplyGate::Env);
        assert!(!args.i_understand);
    }

    #[test]
    fn test_dry_run_cli_overrides_env_gate() {
        let args = parse(&["--dry-run"], true).expect("dry-run should parse");
        assert_eq!(args.mode, Mode::DryRun);
        assert_eq!(args.apply_gate, ApplyGate::None);
    }

    #[test]
    fn test_apply_without_ack_or_env_rejected() {
        let err = parse(&["--apply"], false).expect_err("unguarded apply must fail");
        assert!(err.contains(APPLY_ENV));
    }

    #[test]
    fn test_manual_apply_ack_works() {
        let args = parse(&["--apply", "--i-understand-this-modifies-db"], false)
            .expect("manual apply ack should parse");
        assert_eq!(args.mode, Mode::Apply);
        assert_eq!(args.apply_gate, ApplyGate::CliAck);
    }

    #[test]
    fn test_force_flags_rejected() {
        let err = parse(&["--force"], true).expect_err("force flag must stay rejected");
        assert!(err.contains("rejected flag --force"));
    }

    #[test]
    fn test_lookback_zero_rejected() {
        let err = parse(&["--lookback-days", "0"], false).expect_err("zero lookback must fail");
        assert!(err.contains("--lookback-days"));
    }

    #[test]
    fn test_interval_single() {
        let args = parse(&["--interval", "1"], false).expect("single interval");
        assert_eq!(args.intervals.len(), 1);
        assert_eq!(args.intervals[0].timeframe, "1m");
        assert_eq!(args.intervals[0].period_ms, 60_000);
        assert_eq!(args.intervals[0].bybit_interval, "1");
    }

    #[test]
    fn test_interval_multiple_and_dedup() {
        let args = parse(&["--interval", "5", "--interval", "240", "--interval", "5"], false)
            .expect("multi interval");
        // 5 + 240，重複的 5 去重。
        assert_eq!(args.intervals.len(), 2);
        let tfs: Vec<&str> = args.intervals.iter().map(|s| s.timeframe).collect();
        assert_eq!(tfs, vec!["5m", "4h"]);
    }

    #[test]
    fn test_interval_unknown_rejected() {
        let err = parse(&["--interval", "30"], false).expect_err("unknown interval must fail");
        assert!(err.contains("--interval expects one of"));
    }

    #[test]
    fn test_interval_mapping_complete() {
        // 五個合法 interval 的 period_ms / timeframe 映射全對。
        assert_eq!(resolve_interval("1").unwrap().period_ms, 60_000);
        assert_eq!(resolve_interval("1").unwrap().timeframe, "1m");
        assert_eq!(resolve_interval("5").unwrap().period_ms, 300_000);
        assert_eq!(resolve_interval("5").unwrap().timeframe, "5m");
        assert_eq!(resolve_interval("15").unwrap().period_ms, 900_000);
        assert_eq!(resolve_interval("15").unwrap().timeframe, "15m");
        assert_eq!(resolve_interval("60").unwrap().period_ms, 3_600_000);
        assert_eq!(resolve_interval("60").unwrap().timeframe, "1h");
        assert_eq!(resolve_interval("240").unwrap().period_ms, 14_400_000);
        assert_eq!(resolve_interval("240").unwrap().timeframe, "4h");
        assert!(resolve_interval("0").is_none());
        assert!(resolve_interval("D").is_none());
    }

    #[test]
    fn test_upsert_overwrite_requires_apply() {
        // dry-run（預設）+ --upsert-overwrite → 拒。
        let err = parse(&["--upsert-overwrite"], false)
            .expect_err("overwrite in dry-run must fail");
        assert!(err.contains("--upsert-overwrite requires --apply"));
        // apply + ack + overwrite → 通過。
        let args = parse(
            &["--apply", "--i-understand-this-modifies-db", "--upsert-overwrite"],
            false,
        )
        .expect("apply + overwrite should parse");
        assert!(args.upsert_overwrite);
        assert_eq!(args.mode, Mode::Apply);
    }

    #[test]
    fn test_git_dirty_parse() {
        let a = parse(&["--git-dirty", "true"], false).expect("dirty true");
        assert_eq!(a.git_dirty, Some(true));
        let b = parse(&["--git-dirty", "clean"], false).expect("dirty clean");
        assert_eq!(b.git_dirty, Some(false));
        let err = parse(&["--git-dirty", "maybe"], false).expect_err("invalid dirty");
        assert!(err.contains("--git-dirty"));
    }

    #[test]
    fn test_universe_config_override() {
        let a = parse(&["--universe-config", "/tmp/x.toml"], false).expect("config override");
        assert_eq!(a.universe_config, Some(PathBuf::from("/tmp/x.toml")));
    }

    #[test]
    fn test_resolve_universe_path_default_uses_base_dir() {
        let args = Args::default();
        let p = resolve_universe_path(&args);
        assert!(p.ends_with("settings/backfill_universe.toml"));
    }

    #[test]
    fn test_load_universe_empty_symbols_rejected() {
        let dir = std::env::temp_dir();
        let path = dir.join(format!("intraday_universe_test_{}.toml", uuid::Uuid::new_v4()));
        std::fs::write(
            &path,
            "[backfill_universe]\ncategory = \"linear\"\nlookback_days = 30\nsymbols = []\n",
        )
        .expect("write temp toml");
        let err = load_universe(&path).expect_err("empty symbols must fail");
        assert!(err.contains("empty symbols"));
        let _ = std::fs::remove_file(&path);
    }

    /// estimate_pages：1m × 180 天 ≈ 260 頁（PA §3 rate-limit math）。
    #[test]
    fn test_estimate_pages_1m_180d() {
        let day_ms = 86_400_000_u64;
        let period_ms = 60_000_u64; // 1m
        let end = 1_700_000_000_000_u64;
        let start = end - 180 * day_ms;
        // 180 天 × 1440 bars/day = 259_200 bars → ceil(259200/1000) = 260 頁。
        let pages = estimate_pages(start, end, period_ms);
        assert_eq!(pages, 260);
    }

    /// estimate_pages：4h × 730 天 = 4380 bars → 5 頁。
    #[test]
    fn test_estimate_pages_4h_730d() {
        let day_ms = 86_400_000_u64;
        let period_ms = 14_400_000_u64; // 4h
        let end = 1_700_000_000_000_u64;
        let start = end - 730 * day_ms;
        // 730 天 × 6 bars/day = 4380 → ceil(4380/1000) = 5 頁。
        let pages = estimate_pages(start, end, period_ms);
        assert_eq!(pages, 5);
    }

    /// estimate_pages：退化窗（start>=end）→ 0 頁。
    #[test]
    fn test_estimate_pages_degenerate_window() {
        assert_eq!(estimate_pages(100, 100, 60_000), 0);
        assert_eq!(estimate_pages(200, 100, 60_000), 0);
    }

    /// parse_utc_date_ms：YYYY-MM-DD → UTC 00:00 ms epoch；格式非法回 None。
    #[test]
    fn test_parse_utc_date_ms() {
        // 2026-04-05 00:00:00 UTC = 1775347200000 ms。
        assert_eq!(parse_utc_date_ms("2026-04-05"), Some(1_775_347_200_000));
        // epoch 日。
        assert_eq!(parse_utc_date_ms("1970-01-01"), Some(0));
        // 非法格式 fail-closed。
        assert_eq!(parse_utc_date_ms("2026/04/05"), None);
        assert_eq!(parse_utc_date_ms("not-a-date"), None);
        assert_eq!(parse_utc_date_ms("2026-13-01"), None);
        assert_eq!(parse_utc_date_ms(""), None);
    }

    /// --start / --end 解析：start = 當日 UTC 00:00；end = 含當天 → 隔日 00:00（半開上界）。
    #[test]
    fn test_start_end_parse() {
        let a = parse(&["--start", "2026-04-05", "--end", "2026-06-15"], false)
            .expect("start/end should parse");
        assert_eq!(a.start_ms, Some(1_775_347_200_000));
        // 2026-06-16 00:00 UTC = 2026-06-15 含當天的半開上界。
        let jun16 = parse_utc_date_ms("2026-06-16").unwrap();
        assert_eq!(a.end_ms, Some(jun16));
        assert!(a.start_ms.unwrap() < a.end_ms.unwrap());
    }

    /// --start 非法日期 → fail-closed 拒。
    #[test]
    fn test_start_invalid_rejected() {
        let err = parse(&["--start", "2026-99-99"], false).expect_err("invalid start must fail");
        assert!(err.contains("--start expects YYYY-MM-DD"));
    }

    /// --start >= --end → 拒（半開區間需 start < end）。
    #[test]
    fn test_start_not_before_end_rejected() {
        let err = parse(&["--start", "2026-06-15", "--end", "2026-06-14"], false)
            .expect_err("start after end must fail");
        assert!(err.contains("--start must be strictly before --end"));
        // start == end（end 含當天 → 隔日上界，故同日 start<end，合法）。
        let same = parse(&["--start", "2026-06-15", "--end", "2026-06-15"], false)
            .expect("same-day start/end is valid (end is inclusive)");
        assert!(same.start_ms.unwrap() < same.end_ms.unwrap());
    }

    /// --symbols-from-db flag 解析 + 與 --symbol / --universe-config 互斥。
    #[test]
    fn test_symbols_from_db_flag_and_exclusivity() {
        let a = parse(&["--symbols-from-db"], false).expect("flag should parse");
        assert!(a.symbols_from_db);
        // 預設 false。
        let b = parse(&[], false).expect("default");
        assert!(!b.symbols_from_db);
        // 與 --symbol 互斥。
        let e1 = parse(&["--symbols-from-db", "--symbol", "BTCUSDT"], false)
            .expect_err("db + symbol must fail");
        assert!(e1.contains("mutually exclusive with --symbol"));
        // 與 --universe-config 互斥。
        let e2 = parse(&["--symbols-from-db", "--universe-config", "/tmp/x.toml"], false)
            .expect_err("db + universe-config must fail");
        assert!(e2.contains("mutually exclusive with --universe-config"));
    }
}
