//! 日線（timeframe='1d'）K 線歷史回填 CLI。
//!
//! MODULE_NOTE
//! 模塊用途：把固定流動標的集的歷史日線 OHLCV 從 Bybit 嚴格解析後寫 market.klines
//!   + research.alpha_klines_provenance。鏡像 feature_baseline_writer 的安全骨架：
//!   dry-run 預設、--apply / env gate、V125 preflight fail-closed、EXIT code、sequential
//!   per-symbol 防 burst。
//! 依賴：openclaw_engine::backfill::{daily_kline_backfill, writer}、market_data_client、
//!   database::pool、bybit_rest_client、secret_env、settings/backfill_universe.toml。
//! 硬邊界：
//!   1. 預設 dry-run（只取數 + 算 coverage，不寫 DB）；apply 需 --apply +
//!      --i-understand-this-modifies-db 或 OPENCLAW_DAILY_KLINE_BACKFILL_APPLY=1。
//!   2. V125 preflight：research.alpha_klines_provenance 缺表即 fail-closed 退出（EXIT_DB），
//!      不寫無來源帳的 OHLCV（root principle #8）。
//!   3. 純讀市場 + append-only provenance；不下單、不餵 intent、不碰 auth/lease/system_mode。
//! 運維前置：kline 取數走既有 signed GET（get_klines → get_checked → get，HMAC-SHA256），
//!   依賴 demo secret slot 憑證。Demo 路徑空憑證「不會」建構失敗（僅 warn!，建構即 Err 只對
//!   mainnet）；fail-closed 在首次 get() → NoCredentials → 全 symbol 記 failed coverage
//!   (observed=0) 退 EXIT_OK（無假值，但 cron 須檢 coverage 非僅看 exit code）。非 no-auth public。

#![allow(
    clippy::doc_lazy_continuation,
    clippy::doc_overindented_list_items,
    clippy::empty_line_after_doc_comments,
    clippy::too_many_arguments
)]

use std::env;
use std::path::PathBuf;

use openclaw_engine::backfill::daily_kline_backfill::{
    paginate_daily_klines, strict_filter_closed_bars, DAILY_PERIOD_MS,
};
use openclaw_engine::backfill::writer::{
    insert_provenance_row, probe_provenance_table_exists, write_daily_klines_strict, ProvenanceRow,
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
const APPLY_ENV: &str = "OPENCLAW_DAILY_KLINE_BACKFILL_APPLY";
/// Bybit kline 端點識別（落 provenance.endpoint_id）。
const ENDPOINT_ID: &str = "GET /v5/market/kline";
/// parser 版本標記（落 provenance.parser_version）。strict-parse 邏輯變動時遞增。
const PARSER_VERSION: &str = "daily_kline_strict_v1";

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

/// settings/backfill_universe.toml 反序列化結構。
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
    /// 限定單一 symbol（None 用 universe 全集）。
    symbol: Option<String>,
    /// universe TOML 路徑（None 用 <OPENCLAW_BASE_DIR>/settings/backfill_universe.toml）。
    universe_config: Option<PathBuf>,
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
            symbol: None,
            universe_config: None,
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
        "daily_kline_backfill — backfill historical 1d klines to market.klines + provenance\n\
         \n\
         USAGE:\n  \
           daily_kline_backfill [--dry-run] [--lookback-days N] [--symbol BTCUSDT] [--universe-config PATH]\n  \
           daily_kline_backfill --apply --i-understand-this-modifies-db [--git-sha SHA] [--git-dirty true|false] [options]\n  \
           OPENCLAW_DAILY_KLINE_BACKFILL_APPLY=1 daily_kline_backfill [options]\n\
         \n\
         WRITES (apply mode):\n  \
           market.klines (timeframe='1d', ON CONFLICT DO NOTHING) — disjoint from live 1m-1h\n  \
           research.alpha_klines_provenance (append-only coverage ledger)\n\
         PREFLIGHT:\n  \
           research.alpha_klines_provenance must exist (V125 applied); missing => fail-closed exit\n\
         CONFIG:\n  \
           <OPENCLAW_BASE_DIR>/settings/backfill_universe.toml (fixed liquid universe; QC/MIT review pending)\n\
         ENV:\n  \
           OPENCLAW_DATABASE_URL or OPENCLAW_DATABASE_URL_FILE\n  \
           OPENCLAW_BASE_DIR (settings root; defaults to .)\n  \
           OPENCLAW_DAILY_KLINE_BACKFILL_APPLY=1 enables scheduled apply without CLI ack flags\n"
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

    // symbol 子集（--symbol 限定，必須在 universe 內，避免回填未復核的標的）。
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
    // window_end 對齊到「最後一個完整收盤的 UTC 日界」= 今日 00:00 UTC（floor 到 DAILY_PERIOD_MS）。
    // 為什麼必須對齊（FIX-1）：non-UTC-aligned now（如 13:47 UTC）下，若 window_end=now，
    // expected_daily_bars 用窗口長度整除週期會把「今日未收盤的殘段」算進 expected，
    // 但 strict_filter_closed_bars 的 closed-bar filter 正確濾掉該未收盤 bar
    // → observed 必少 1 → 每 symbol 每次 run 結構性標 partial（即使資料完整），
    // coverage_status 失去 pass/partial 區分力（信任 gate 失效）。
    // floor 後 window_end 落在最後一根已收盤 bar 的 close_time 邊界，
    // expected 與可得 closed bar 對齊（資料完整時 gap=0 → pass）。
    // window_start 同步對齊同一日界基準，保持窗口為整數天語義一致。
    let window_end_ms = (now_ms / DAILY_PERIOD_MS) * DAILY_PERIOD_MS;
    let window_start_ms = window_end_ms.saturating_sub(lookback_days as u64 * DAILY_PERIOD_MS);
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
    // 註解修正（先前兩版皆誤述，已親讀 bybit_rest_client.rs 校正）：kline 取數走既有共用
    //   MarketDataClient::get_klines → BybitRestClient::get_checked → get，是 *signed* GET
    //   （HMAC-SHA256），非 no-auth public 取數。傳 None 憑證時 new() 回退讀 demo secret slot。
    //   ★ Demo（非 mainnet）空憑證「不會」建構失敗：new() 的「建構即 Err」只鍵於 is_mainnet
    //   （LIVE-GUARD-1 門#3，:1093-1101），Demo 僅 warn! 後回 Ok（空憑證）。下方 match 的
    //   Err→EXIT_DB 只攔真正建構錯誤（如 HTTP client build），非空憑證。
    // fail-closed 發生在 request time：首次 get() → has_credentials()=false → NoCredentials Err
    //   （:1215-1217）→ 該 symbol 落下方 per-symbol fetch-error 分支記 failed coverage(observed=0)，
    //   不中止整批 → 跑完全部 symbol 退 EXIT_OK；apply 模式寫 failed-status provenance row。
    //   仍 fail-closed（無假值、coverage 誠實標 failed），但機制是 per-request reject + failed
    //   coverage，非建構期中止 EXIT_DB。Demo env 無 OPENCLAW_ALLOW_MAINNET，不觸主網執行路徑。
    // 運維前置：demo slot 憑證須存在；否則全 symbol failed coverage（observed=0、無實際回填，
    //   但 run 仍退 EXIT_OK，見上 — 故 cron 須另檢 coverage 而非僅看 exit code）。
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
    println!("# run_id = {run_id}");
    println!("# parser_version = {PARSER_VERSION}");
    println!("# endpoint_id = {ENDPOINT_ID}");
    println!("# universe_config = {}", universe_path.display());
    println!("# category = {}", universe.category);
    println!("# lookback_days = {lookback_days}");
    println!("# window_start_ms = {window_start_ms}");
    println!("# window_end_ms = {window_end_ms}");
    println!("# symbols = {}", symbols.len());
    println!("# git_sha = {}", args.git_sha.as_deref().unwrap_or("(none)"));

    let mut total_observed: u64 = 0;
    let mut total_inserted: u64 = 0;

    // sequential per-symbol（抄 get_open_interest_batch mod.rs:227 範式）：
    // 一次跑一個 symbol 的分頁迴圈，不製造 burst 驚動共享 Bybit Market rate-limit group。
    for symbol in &symbols {
        let request_start_ms = openclaw_core::now_ms();
        let raw = match paginate_daily_klines(
            &mdc,
            &universe.category,
            symbol,
            window_start_ms,
            window_end_ms,
        )
        .await
        {
            Ok(bars) => bars,
            Err(e) => {
                // 單 symbol 取數失敗：記 failed coverage（observed=0），不中止整批。
                eprintln!("warn: {symbol} fetch failed: {e}");
                let request_end_ms = openclaw_core::now_ms();
                let page = strict_filter_closed_bars(
                    symbol,
                    &[],
                    window_start_ms,
                    window_end_ms,
                    now_ms,
                );
                println!(
                    "{symbol}\tstatus={}\texpected={}\tobserved={}\tinserted=0\t(fetch_error)",
                    page.verdict.status.as_db_str(),
                    page.verdict.expected,
                    page.verdict.observed,
                );
                if args.mode == Mode::Apply {
                    let prov = build_provenance(
                        &run_id,
                        &universe.category,
                        symbol,
                        window_start_ms,
                        window_end_ms,
                        Some(request_start_ms),
                        Some(request_end_ms),
                        &args,
                        &page.verdict,
                    );
                    if let Err(e) = insert_provenance_row(&pool, &prov).await {
                        eprintln!("error: provenance insert failed for {symbol}: {e}");
                        return EXIT_DB;
                    }
                }
                continue;
            }
        };
        let request_end_ms = openclaw_core::now_ms();

        let page = strict_filter_closed_bars(symbol, &raw, window_start_ms, window_end_ms, now_ms);
        total_observed += page.verdict.observed;

        let inserted = if args.mode == Mode::Apply {
            match write_daily_klines_strict(&pool, &page).await {
                Ok(s) => s.inserted,
                Err(e) => {
                    eprintln!("error: klines write failed for {symbol}: {e}");
                    return EXIT_DB;
                }
            }
        } else {
            0
        };
        total_inserted += inserted;

        println!(
            "{symbol}\tstatus={}\texpected={}\tobserved={}\tinserted={}",
            page.verdict.status.as_db_str(),
            page.verdict.expected,
            page.verdict.observed,
            inserted,
        );

        if args.mode == Mode::Apply {
            let prov = build_provenance(
                &run_id,
                &universe.category,
                symbol,
                window_start_ms,
                window_end_ms,
                Some(request_start_ms),
                Some(request_end_ms),
                &args,
                &page.verdict,
            );
            if let Err(e) = insert_provenance_row(&pool, &prov).await {
                eprintln!("error: provenance insert failed for {symbol}: {e}");
                return EXIT_DB;
            }
        }
    }

    println!("# total_observed = {total_observed}");
    println!("# total_inserted = {total_inserted}");
    if args.mode == Mode::DryRun {
        println!("# dry-run: no rows written (klines or provenance)");
    }
    EXIT_OK
}

/// 由覆蓋率判定組裝 provenance row（純資料搬運，無副作用）。
#[allow(clippy::too_many_arguments)]
fn build_provenance(
    run_id: &str,
    category: &str,
    symbol: &str,
    window_start_ms: u64,
    window_end_ms: u64,
    request_start_ms: Option<u64>,
    request_end_ms: Option<u64>,
    args: &Args,
    verdict: &openclaw_engine::backfill::daily_kline_backfill::CoverageVerdict,
) -> ProvenanceRow {
    ProvenanceRow {
        run_id: run_id.to_string(),
        endpoint_id: ENDPOINT_ID.to_string(),
        category: category.to_string(),
        symbol: symbol.to_string(),
        timeframe: "1d".to_string(),
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
    fn test_default_is_dry_run() {
        let args = parse(&[], false).expect("default should parse");
        assert_eq!(args.mode, Mode::DryRun);
        assert_eq!(args.apply_gate, ApplyGate::None);
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
        // 不設 --universe-config → 用 base/settings/backfill_universe.toml（相對，跨平台）。
        let args = Args::default();
        let p = resolve_universe_path(&args);
        assert!(p.ends_with("settings/backfill_universe.toml"));
    }

    #[test]
    fn test_load_universe_empty_symbols_rejected() {
        let dir = std::env::temp_dir();
        let path = dir.join(format!("backfill_universe_test_{}.toml", uuid::Uuid::new_v4()));
        std::fs::write(
            &path,
            "[backfill_universe]\ncategory = \"linear\"\nlookback_days = 30\nsymbols = []\n",
        )
        .expect("write temp toml");
        let err = load_universe(&path).expect_err("empty symbols must fail");
        assert!(err.contains("empty symbols"));
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn test_load_universe_parses_valid() {
        let dir = std::env::temp_dir();
        let path = dir.join(format!("backfill_universe_ok_{}.toml", uuid::Uuid::new_v4()));
        std::fs::write(
            &path,
            "[backfill_universe]\ncategory = \"linear\"\nlookback_days = 365\nsymbols = [\"BTCUSDT\", \"ETHUSDT\"]\n",
        )
        .expect("write temp toml");
        let u = load_universe(&path).expect("valid toml should parse");
        assert_eq!(u.category, "linear");
        assert_eq!(u.lookback_days, 365);
        assert_eq!(u.symbols, vec!["BTCUSDT", "ETHUSDT"]);
        let _ = std::fs::remove_file(&path);
    }
}
