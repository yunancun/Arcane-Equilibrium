//! funding rate + open interest 歷史回填 CLI。
//!
//! MODULE_NOTE
//! 模塊用途：把固定流動標的集的歷史 funding rate（GET /v5/market/funding/history）+
//!   open interest（GET /v5/market/open-interest，intervalTime=1h）從 Bybit 嚴格解析後寫
//!   research.alpha_funding_rates_history / research.alpha_open_interest_history +
//!   alpha_history_ingest_runs/pages 帳本。鏡像 daily_kline_backfill 的安全骨架：
//!   dry-run 預設、--apply / env gate、V125 preflight fail-closed、EXIT code、sequential
//!   per-symbol 防 burst。
//! 依賴：openclaw_engine::backfill::{funding_oi_backfill, funding_oi_writer}、market_data_client、
//!   database::pool、bybit_rest_client、secret_env、settings/backfill_universe.toml。
//! 硬邊界：
//!   1. 預設 dry-run（只取數 + 算 coverage，不寫 DB）；apply 需 --apply +
//!      --i-understand-this-modifies-db 或 OPENCLAW_FUNDING_OI_BACKFILL_APPLY=1。
//!   2. V125 preflight：4 張目標表（2 history + 2 ledger）任一缺即 fail-closed 退出（EXIT_DB）。
//!   3. ★ strict-parse VARIANT（funding_oi_backfill.rs）：funding/OI 讀原始 JSON，「欄位存在
//!      AND finite」而非 >0 floor — 保留真 0.0 / 負 funding，只擋 missing/non-finite/壞 ts。
//!   4.【cap 紀律】只記已實現 funding history，禁碰 cap、禁從 max(fundingRate) 反推 cap。
//!   5. 純讀市場 + append-only provenance；不下單、不餵 intent、不碰 auth/lease/system_mode。
//! 運維前置：funding/OI 取數走既有 signed GET（get_checked → get，HMAC-SHA256），依賴 demo
//!   secret slot 憑證。Demo 路徑空憑證「不會」建構失敗（僅 warn!，建構即 Err 只對 mainnet）；
//!   fail-closed 在首次 get() → NoCredentials → 該 symbol 記 failed coverage 退 EXIT_OK
//!   （無假值，但 cron 須檢 coverage 非僅看 exit code）。非 no-auth public。

#![allow(
    clippy::doc_lazy_continuation,
    clippy::doc_overindented_list_items,
    clippy::empty_line_after_doc_comments,
    clippy::too_many_arguments
)]

use std::env;
use std::path::PathBuf;
use std::sync::Arc;

use openclaw_engine::backfill::funding_oi_backfill::{
    paginate_funding_history, paginate_open_interest, strict_parse_funding_list,
    strict_parse_oi_list, CoverageVerdict, PaginatedRaw,
};
use openclaw_engine::backfill::funding_oi_writer::{
    build_page_id, insert_ingest_page, probe_table_exists, update_run_status, upsert_ingest_run,
    write_funding_points_strict, write_oi_points_strict, FundingWriteCtx, IngestPage, IngestRun,
    OiWriteCtx,
};
use openclaw_engine::bybit_rest_client::{BybitEnvironment, BybitRestClient};
use openclaw_engine::database::pool::DbPool;
use openclaw_engine::database::DatabaseConfig;
use openclaw_engine::market_data_client::MarketDataClient;
use openclaw_engine::secret_env;
use serde::Deserialize;

const EXIT_OK: i32 = 0;
const EXIT_ARG: i32 = 2;
const EXIT_DB: i32 = 4;
const APPLY_ENV: &str = "OPENCLAW_FUNDING_OI_BACKFILL_APPLY";

const FUNDING_ENDPOINT: &str = "GET /v5/market/funding/history";
const OI_ENDPOINT: &str = "GET /v5/market/open-interest";
/// parser 版本標記（落 provenance.parser_version）。strict-parse 邏輯變動時遞增。
const PARSER_VERSION: &str = "funding_oi_strict_v1";
/// run-level program 標記（落 alpha_history_ingest_runs.program）。
const PROGRAM: &str = "funding_oi_backfill";
/// OI intervalTime（BB spec §2：1h 是量/粒度甜點）。
const OI_INTERVAL: &str = "1h";
/// 一筆 funding 結算間隔（ms）= 8h（多數 linear perp 預設；僅用於 expected 粗估）。
const FUNDING_INTERVAL_MS: u64 = 8 * 3_600_000;
/// OI 1h 點間隔（ms）。
const OI_INTERVAL_MS: u64 = 3_600_000;

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

/// 回填哪個 endpoint（--only 限定，預設兩者都跑）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Target {
    Both,
    Funding,
    Oi,
}

impl Target {
    fn funding(self) -> bool {
        matches!(self, Target::Both | Target::Funding)
    }
    fn oi(self) -> bool {
        matches!(self, Target::Both | Target::Oi)
    }
}

/// settings/backfill_universe.toml 反序列化（複用日線 universe 同檔）。
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
    lookback_days_override: Option<u32>,
    symbol: Option<String>,
    universe_config: Option<PathBuf>,
    target: Target,
    git_sha: Option<String>,
    git_dirty: Option<bool>,
}

impl Default for Args {
    fn default() -> Self {
        Self {
            mode: Mode::DryRun,
            apply_gate: ApplyGate::None,
            i_understand: false,
            lookback_days_override: None,
            symbol: None,
            universe_config: None,
            target: Target::Both,
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
            "--lookback-days" => {
                args.lookback_days_override = Some(parse_next_u32(&mut it, "--lookback-days")?)
            }
            "--symbol" => args.symbol = Some(parse_next_string(&mut it, "--symbol")?),
            "--universe-config" => {
                args.universe_config = Some(PathBuf::from(parse_next_string(
                    &mut it,
                    "--universe-config",
                )?))
            }
            "--only" => {
                let v = parse_next_string(&mut it, "--only")?;
                args.target = match v.as_str() {
                    "funding" => Target::Funding,
                    "oi" | "open-interest" => Target::Oi,
                    "both" => Target::Both,
                    other => {
                        return Err(format!("--only expects funding|oi|both, got {other}"))
                    }
                };
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
        "funding_oi_backfill — backfill historical funding rate + open interest to research.alpha_*\n\
         \n\
         USAGE:\n  \
           funding_oi_backfill [--dry-run] [--only funding|oi|both] [--lookback-days N] [--symbol BTCUSDT]\n  \
           funding_oi_backfill --apply --i-understand-this-modifies-db [--git-sha SHA] [--git-dirty true|false] [options]\n  \
           OPENCLAW_FUNDING_OI_BACKFILL_APPLY=1 funding_oi_backfill [options]\n\
         \n\
         WRITES (apply mode):\n  \
           research.alpha_funding_rates_history (funding_rate finite incl 0.0/negative; PK incl run_id)\n  \
           research.alpha_open_interest_history (intervalTime=1h; PK incl run_id)\n  \
           research.alpha_history_ingest_runs / alpha_history_ingest_pages (provenance ledgers)\n\
         PREFLIGHT:\n  \
           all 4 tables must exist (V125 applied); missing => fail-closed exit\n\
         STRICT-PARSE:\n  \
           funding/OI read RAW JSON; accept field-present AND finite (incl true 0.0 / negative funding);\n  \
           reject missing-field / non-finite / unparseable-ts (NO >0 floor, NO epoch fallback)\n\
         CAP DISCIPLINE:\n  \
           backfills REALIZED funding history only; never touches cap (cap SSOT = instruments-info)\n\
         CONFIG:\n  \
           <OPENCLAW_BASE_DIR>/settings/backfill_universe.toml (fixed liquid universe; QC/MIT review pending)\n\
         ENV:\n  \
           OPENCLAW_DATABASE_URL or OPENCLAW_DATABASE_URL_FILE\n  \
           OPENCLAW_BASE_DIR (settings root; defaults to .)\n  \
           OPENCLAW_FUNDING_OI_BACKFILL_APPLY=1 enables scheduled apply without CLI ack flags\n"
    );
}

fn resolve_db_url() -> Result<String, String> {
    secret_env::var_or_file("OPENCLAW_DATABASE_URL")
        .filter(|s| !s.is_empty())
        .ok_or_else(|| "OPENCLAW_DATABASE_URL or OPENCLAW_DATABASE_URL_FILE not set".to_string())
}

/// 解析 universe TOML 路徑：--universe-config 優先，否則 <OPENCLAW_BASE_DIR>/settings/...。
/// 為什麼用 OPENCLAW_BASE_DIR（預設 "."）：跨平台不硬編碼絕對路徑（CLAUDE §六）。
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

    let symbols: Vec<String> = match &args.symbol {
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
    };

    let lookback_days = args.lookback_days_override.unwrap_or(universe.lookback_days);
    let now_ms = openclaw_core::now_ms();
    // window_end 對齊「最後一個完整收盤的 UTC 1h 邊界」（floor 到 OI_INTERVAL_MS）。
    // 為什麼對齊（同 daily-kline FIX-1）：non-aligned now 下若 window_end=now，expected 粗估
    //   會把未完成的當前 interval 算進去 → observed 結構性少 1 → 假性 partial。floor 後窗口
    //   落在已完整邊界。對 funding 用更粗的 1h floor 仍安全（funding 8h 邊界 ⊇ 1h 邊界）。
    let window_end_ms = (now_ms / OI_INTERVAL_MS) * OI_INTERVAL_MS;
    let window_start_ms = window_end_ms.saturating_sub(lookback_days as u64 * 86_400_000);
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

    // V125 preflight：4 張表任一缺即 fail-closed（不寫無來源帳的歷史）。
    let required_tables = [
        "alpha_history_ingest_runs",
        "alpha_history_ingest_pages",
        "alpha_funding_rates_history",
        "alpha_open_interest_history",
    ];
    for t in required_tables {
        match probe_table_exists(&pool, t).await {
            Ok(true) => {}
            Ok(false) => {
                eprintln!(
                    "error: V125 preflight FAIL — research.{t} does not exist; \
                     apply V125 before backfill (fail-closed)"
                );
                return EXIT_DB;
            }
            Err(e) => {
                eprintln!("error: V125 preflight probe failed for {t}: {e}");
                return EXIT_DB;
            }
        }
    }

    // REST client（market-data only；Demo 端點，回填只讀公開資料，不碰主網執行路徑）。
    // funding/OI 取數走既有共用 get_checked → get，是 *signed* GET（HMAC-SHA256），
    // 非 no-auth public。Demo 空憑證「不會」建構失敗（建構即 Err 只鍵於 is_mainnet）；
    // fail-closed 在 request time（首次 get → NoCredentials → 該 symbol failed coverage）。
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
    println!("# target = {:?}", args.target);
    println!("# run_id = {run_id}");
    println!("# parser_version = {PARSER_VERSION}");
    println!("# oi_interval = {OI_INTERVAL}");
    println!("# universe_config = {}", universe_path.display());
    println!("# category = {}", universe.category);
    println!("# lookback_days = {lookback_days}");
    println!("# window_start_ms = {window_start_ms}");
    println!("# window_end_ms = {window_end_ms}");
    println!("# symbols = {}", symbols.len());
    println!("# git_sha = {}", args.git_sha.as_deref().unwrap_or("(none)"));

    // apply 模式：先建 run-level 帳本（status='running'）。
    if args.mode == Mode::Apply {
        let run = IngestRun {
            run_id: run_id.clone(),
            program: PROGRAM.to_string(),
            storage_branch: Some("funding_oi_history_research".to_string()),
            window_start_ms,
            window_end_ms,
            git_sha: args.git_sha.clone(),
            git_dirty: args.git_dirty,
        };
        if let Err(e) = upsert_ingest_run(&pool, &run).await {
            eprintln!("error: ingest run upsert failed: {e}");
            return EXIT_DB;
        }
    }

    let mut total_funding_observed: u64 = 0;
    let mut total_funding_inserted: u64 = 0;
    let mut total_oi_observed: u64 = 0;
    let mut total_oi_inserted: u64 = 0;

    // sequential per-symbol（抄 get_open_interest_batch 範式）：一次一個 symbol 的分頁迴圈，
    // 不製造 burst 驚動共享 Bybit Market rate-limit group。禁跨 symbol 並行。
    for symbol in &symbols {
        if args.target.funding() {
            match backfill_funding_for_symbol(
                &mdc,
                &pool,
                &args,
                &run_id,
                &universe.category,
                symbol,
                window_start_ms,
                window_end_ms,
            )
            .await
            {
                Ok((observed, inserted, _status)) => {
                    total_funding_observed += observed;
                    total_funding_inserted += inserted;
                }
                Err(e) => {
                    eprintln!("error: funding backfill DB failure for {symbol}: {e}");
                    let _ = update_run_status(&pool, &run_id, "failed").await;
                    return EXIT_DB;
                }
            }
        }

        if args.target.oi() {
            match backfill_oi_for_symbol(
                &mdc,
                &pool,
                &args,
                &run_id,
                &universe.category,
                symbol,
                window_start_ms,
                window_end_ms,
            )
            .await
            {
                Ok((observed, inserted, _status)) => {
                    total_oi_observed += observed;
                    total_oi_inserted += inserted;
                }
                Err(e) => {
                    eprintln!("error: OI backfill DB failure for {symbol}: {e}");
                    let _ = update_run_status(&pool, &run_id, "failed").await;
                    return EXIT_DB;
                }
            }
        }
    }

    if args.mode == Mode::Apply {
        // 全程無 DB 寫入錯誤即標 'accepted'（run 本身完成）。個別 symbol 的 coverage=failed
        // 不降 run 狀態 — 那是「資料覆蓋」層的事實，由 alpha_history_ingest_pages.coverage_status
        // 逐頁誠實記錄；run status 反映的是「採集流程是否跑完」，與 daily-kline 一致。
        // DB 寫入錯誤的路徑已在上方迴圈內 update_run_status('failed') + return EXIT_DB。
        if let Err(e) = update_run_status(&pool, &run_id, "accepted").await {
            eprintln!("warn: run status update failed: {e}");
        }
    }

    println!("# total_funding_observed = {total_funding_observed}");
    println!("# total_funding_inserted = {total_funding_inserted}");
    println!("# total_oi_observed = {total_oi_observed}");
    println!("# total_oi_inserted = {total_oi_inserted}");
    if args.mode == Mode::DryRun {
        println!("# dry-run: no rows written (history or ledger)");
    }
    EXIT_OK
}

/// 粗估窗口內期望的 funding 結算事件數（按 8h 間隔）。粗估僅用於 coverage status 分母；
/// 寧可低估（不誤標 partial）。window 長度 / 8h。
fn expected_funding(window_start_ms: u64, window_end_ms: u64) -> u64 {
    if window_end_ms <= window_start_ms {
        return 0;
    }
    (window_end_ms - window_start_ms) / FUNDING_INTERVAL_MS
}

/// 粗估窗口內期望的 OI 1h 點數。window 長度 / 1h。
fn expected_oi(window_start_ms: u64, window_end_ms: u64) -> u64 {
    if window_end_ms <= window_start_ms {
        return 0;
    }
    (window_end_ms - window_start_ms) / OI_INTERVAL_MS
}

/// 單 symbol funding 回填：分頁 → strict-parse → (apply) 寫 history + per-page 帳本。
/// 回 (observed, inserted, coverage_status)。fetch 失敗記 failed coverage（不中止整批），
/// 只有 DB 寫入錯誤回 Err（上層中止）。
#[allow(clippy::too_many_arguments)]
async fn backfill_funding_for_symbol(
    mdc: &MarketDataClient,
    pool: &DbPool,
    args: &Args,
    run_id: &str,
    category: &str,
    symbol: &str,
    window_start_ms: u64,
    window_end_ms: u64,
) -> Result<(u64, u64, String), sqlx::Error> {
    let expected = expected_funding(window_start_ms, window_end_ms);
    let raw: PaginatedRaw = match paginate_funding_history(
        mdc,
        category,
        symbol,
        window_start_ms,
        window_end_ms,
    )
    .await
    {
        Ok(r) => r,
        Err(e) => {
            eprintln!("warn: {symbol} funding fetch failed: {e}");
            // 空 strict → failed coverage（observed=0）。
            let page = strict_parse_funding_list(
                category,
                symbol,
                &[],
                window_start_ms,
                window_end_ms,
                expected,
            );
            print_funding_line(symbol, &page.verdict, 0, "(fetch_error)");
            return Ok((0, 0, page.verdict.status.as_db_str().to_string()));
        }
    };

    let page = strict_parse_funding_list(
        category,
        symbol,
        &raw.raw_items,
        window_start_ms,
        window_end_ms,
        expected,
    );

    let inserted = if args.mode == Mode::Apply {
        let ctx = FundingWriteCtx {
            run_id: run_id.to_string(),
            category: category.to_string(),
            symbol: symbol.to_string(),
            source_endpoint: FUNDING_ENDPOINT.to_string(),
            request_start_ms: Some(window_start_ms),
            request_end_ms: Some(window_end_ms),
            parser_version: PARSER_VERSION.to_string(),
            payload_sha256: page.verdict.payload_sha256.clone(),
            // funding_interval_minutes：本回填不查 instruments-info（避免碰 cap 路徑），留 None。
            // 註：fundingInterval 是「結算間隔」非 cap，但本任務範圍只記已實現費率，不主動拉。
            funding_interval_minutes: None,
        };
        let summary = write_funding_points_strict(pool, &ctx, &page.points).await?;
        write_funding_pages(pool, run_id, category, symbol, &raw, &page.verdict).await?;
        summary.inserted
    } else {
        0
    };

    print_funding_line(symbol, &page.verdict, inserted, "");
    Ok((page.verdict.observed, inserted, page.verdict.status.as_db_str().to_string()))
}

/// 單 symbol OI 回填：分頁 → strict-parse → (apply) 寫 history + per-page 帳本。
#[allow(clippy::too_many_arguments)]
async fn backfill_oi_for_symbol(
    mdc: &MarketDataClient,
    pool: &DbPool,
    args: &Args,
    run_id: &str,
    category: &str,
    symbol: &str,
    window_start_ms: u64,
    window_end_ms: u64,
) -> Result<(u64, u64, String), sqlx::Error> {
    let expected = expected_oi(window_start_ms, window_end_ms);
    let raw: PaginatedRaw = match paginate_open_interest(
        mdc,
        category,
        symbol,
        OI_INTERVAL,
        window_start_ms,
        window_end_ms,
    )
    .await
    {
        Ok(r) => r,
        Err(e) => {
            eprintln!("warn: {symbol} OI fetch failed: {e}");
            let page = strict_parse_oi_list(
                category,
                symbol,
                OI_INTERVAL,
                &[],
                window_start_ms,
                window_end_ms,
                expected,
            );
            print_oi_line(symbol, &page.verdict, 0, "(fetch_error)");
            return Ok((0, 0, page.verdict.status.as_db_str().to_string()));
        }
    };

    let page = strict_parse_oi_list(
        category,
        symbol,
        OI_INTERVAL,
        &raw.raw_items,
        window_start_ms,
        window_end_ms,
        expected,
    );

    let inserted = if args.mode == Mode::Apply {
        // cursor_lineage：nextPageCursor 鏈以 '>' 串接（缺則 None）。
        let cursor_lineage = if raw.cursor_lineage.is_empty() {
            None
        } else {
            Some(raw.cursor_lineage.join(">"))
        };
        let ctx = OiWriteCtx {
            run_id: run_id.to_string(),
            category: category.to_string(),
            symbol: symbol.to_string(),
            interval_time: OI_INTERVAL.to_string(),
            source_endpoint: OI_ENDPOINT.to_string(),
            request_start_ms: Some(window_start_ms),
            request_end_ms: Some(window_end_ms),
            parser_version: PARSER_VERSION.to_string(),
            payload_sha256: page.verdict.payload_sha256.clone(),
            cursor_lineage,
        };
        let summary = write_oi_points_strict(pool, &ctx, &page.points).await?;
        write_oi_pages(pool, run_id, category, symbol, &raw, &page.verdict).await?;
        summary.inserted
    } else {
        0
    };

    print_oi_line(symbol, &page.verdict, inserted, "");
    Ok((page.verdict.observed, inserted, page.verdict.status.as_db_str().to_string()))
}

/// 把 funding 分頁的逐頁 meta 寫 alpha_history_ingest_pages（append-only）。
/// 為什麼整段 page 共用同一 verdict：strict-parse 在「合併所有頁後」一次做（與 daily-kline
/// 同），故 coverage 是窗口級而非單頁級；page 帳本記每頁的請求參數 + raw_count 供追溯。
async fn write_funding_pages(
    pool: &DbPool,
    run_id: &str,
    category: &str,
    symbol: &str,
    raw: &PaginatedRaw,
    verdict: &CoverageVerdict,
) -> Result<(), sqlx::Error> {
    for meta in &raw.pages {
        let page_id = build_page_id(FUNDING_ENDPOINT, symbol, "funding", meta);
        let page = IngestPage {
            run_id: run_id.to_string(),
            page_id,
            endpoint_id: FUNDING_ENDPOINT.to_string(),
            category: category.to_string(),
            symbol: symbol.to_string(),
            timeframe_or_period: "funding".to_string(),
            request_start_ms: Some(meta.request_start_ms),
            request_end_ms: Some(meta.request_end_ms),
            cursor_in: meta.cursor_in.clone(),
            cursor_out: meta.cursor_out.clone(),
            ret_code: Some(meta.ret_code as i32),
            raw_count: meta.raw_count as u64,
            parser_version: PARSER_VERSION.to_string(),
        };
        insert_ingest_page(pool, &page, verdict).await?;
    }
    Ok(())
}

/// 把 OI 分頁的逐頁 meta 寫 alpha_history_ingest_pages（append-only）。
async fn write_oi_pages(
    pool: &DbPool,
    run_id: &str,
    category: &str,
    symbol: &str,
    raw: &PaginatedRaw,
    verdict: &CoverageVerdict,
) -> Result<(), sqlx::Error> {
    for meta in &raw.pages {
        let page_id = build_page_id(OI_ENDPOINT, symbol, OI_INTERVAL, meta);
        let page = IngestPage {
            run_id: run_id.to_string(),
            page_id,
            endpoint_id: OI_ENDPOINT.to_string(),
            category: category.to_string(),
            symbol: symbol.to_string(),
            timeframe_or_period: OI_INTERVAL.to_string(),
            request_start_ms: Some(meta.request_start_ms),
            request_end_ms: Some(meta.request_end_ms),
            cursor_in: meta.cursor_in.clone(),
            cursor_out: meta.cursor_out.clone(),
            ret_code: Some(meta.ret_code as i32),
            raw_count: meta.raw_count as u64,
            parser_version: PARSER_VERSION.to_string(),
        };
        insert_ingest_page(pool, &page, verdict).await?;
    }
    Ok(())
}

fn print_funding_line(symbol: &str, verdict: &CoverageVerdict, inserted: u64, note: &str) {
    println!(
        "funding\t{symbol}\tstatus={}\texpected={}\tobserved={}\trejected={}\tinserted={}\t{}",
        verdict.status.as_db_str(),
        verdict.expected,
        verdict.observed,
        verdict.rejected,
        inserted,
        note,
    );
}

fn print_oi_line(symbol: &str, verdict: &CoverageVerdict, inserted: u64, note: &str) {
    println!(
        "oi\t{symbol}\tstatus={}\texpected={}\tobserved={}\trejected={}\tinserted={}\t{}",
        verdict.status.as_db_str(),
        verdict.expected,
        verdict.observed,
        verdict.rejected,
        inserted,
        note,
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parse(argv: &[&str], env_gate: bool) -> Result<Args, String> {
        parse_args_from(argv.iter().map(|s| (*s).to_string()), env_gate)
    }

    #[test]
    fn test_default_is_dry_run() {
        let args = parse(&[], false).expect("default should parse");
        assert_eq!(args.mode, Mode::DryRun);
        assert_eq!(args.apply_gate, ApplyGate::None);
        assert_eq!(args.target, Target::Both);
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
    fn test_only_funding_parses() {
        let a = parse(&["--only", "funding"], false).expect("only funding");
        assert_eq!(a.target, Target::Funding);
        assert!(a.target.funding() && !a.target.oi());
    }

    #[test]
    fn test_only_oi_parses() {
        let a = parse(&["--only", "oi"], false).expect("only oi");
        assert_eq!(a.target, Target::Oi);
        assert!(a.target.oi() && !a.target.funding());
        // 別名 open-interest 同義。
        let b = parse(&["--only", "open-interest"], false).expect("only open-interest");
        assert_eq!(b.target, Target::Oi);
    }

    #[test]
    fn test_only_invalid_rejected() {
        let err = parse(&["--only", "klines"], false).expect_err("invalid only must fail");
        assert!(err.contains("--only"));
    }

    #[test]
    fn test_lookback_zero_rejected() {
        let err = parse(&["--lookback-days", "0"], false).expect_err("zero lookback must fail");
        assert!(err.contains("--lookback-days"));
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
    fn test_resolve_universe_path_default_uses_base_dir() {
        let args = Args::default();
        let p = resolve_universe_path(&args);
        assert!(p.ends_with("settings/backfill_universe.toml"));
    }

    #[test]
    fn test_expected_funding_and_oi() {
        // 一天 = 3 個 8h funding 結算 + 24 個 1h OI 點。
        let day = 86_400_000u64;
        assert_eq!(expected_funding(0, day), 3);
        assert_eq!(expected_oi(0, day), 24);
        // 退化窗 → 0（不誤判 partial）。
        assert_eq!(expected_funding(day, 0), 0);
        assert_eq!(expected_oi(10, 10), 0);
    }
}
