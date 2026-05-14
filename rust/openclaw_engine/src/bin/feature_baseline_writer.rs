//! Rebuild `observability.feature_baselines` from decision context snapshots.
//!
//! Default mode is read-only dry-run. Runtime scheduling may opt into writes
//! only with `OPENCLAW_FEATURE_BASELINE_APPLY=1`; the old manual
//! `--apply --i-understand-this-modifies-db` path is kept for one-shot operator
//! runs.

use std::env;

use openclaw_engine::database::drift_detector::{
    build_feature_baseline_rows, fetch_historical_feature_samples_from_decision_contexts,
    write_feature_baseline_rows,
};
use openclaw_engine::database::pool::DbPool;
use openclaw_engine::database::DatabaseConfig;
use openclaw_engine::secret_env;

const EXIT_OK: i32 = 0;
const EXIT_ARG: i32 = 2;
const EXIT_DB: i32 = 4;
const FEATURE_BASELINE_APPLY_ENV: &str = "OPENCLAW_FEATURE_BASELINE_APPLY";

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
            ApplyGate::Env => FEATURE_BASELINE_APPLY_ENV,
            ApplyGate::CliAck => "--i-understand-this-modifies-db",
        }
    }
}

#[derive(Debug, Clone)]
struct Args {
    mode: Mode,
    apply_gate: ApplyGate,
    i_understand: bool,
    lookback_days: u32,
    window_days: u32,
    step_days: u32,
    bins: usize,
    symbol: Option<String>,
}

impl Default for Args {
    fn default() -> Self {
        Self {
            mode: Mode::DryRun,
            apply_gate: ApplyGate::None,
            i_understand: false,
            lookback_days: 180,
            window_days: 30,
            step_days: 7,
            bins: 10,
            symbol: None,
        }
    }
}

fn parse_args() -> Result<Args, String> {
    parse_args_from(env::args().skip(1), feature_baseline_apply_env_enabled())
}

fn feature_baseline_apply_env_enabled() -> bool {
    matches!(env::var(FEATURE_BASELINE_APPLY_ENV), Ok(v) if v.trim() == "1")
}

fn parse_args_from<I>(iter: I, apply_env_enabled: bool) -> Result<Args, String>
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
            "--lookback-days" => args.lookback_days = parse_next_u32(&mut it, "--lookback-days")?,
            "--window-days" => args.window_days = parse_next_u32(&mut it, "--window-days")?,
            "--step-days" => args.step_days = parse_next_u32(&mut it, "--step-days")?,
            "--bins" => args.bins = parse_next_usize(&mut it, "--bins")?,
            "--symbol" => args.symbol = Some(parse_next_string(&mut it, "--symbol")?),
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

    if apply_env_enabled && !mode_set_by_cli {
        args.mode = Mode::Apply;
        args.apply_gate = ApplyGate::Env;
    }

    if args.mode == Mode::Apply {
        if apply_env_enabled {
            args.apply_gate = ApplyGate::Env;
        } else if args.i_understand {
            args.apply_gate = ApplyGate::CliAck;
        } else {
            return Err(format!(
                "apply mode requires --i-understand-this-modifies-db or {FEATURE_BASELINE_APPLY_ENV}=1"
            ));
        }
    }
    if args.lookback_days == 0 || args.window_days == 0 || args.step_days == 0 || args.bins == 0 {
        return Err("lookback/window/step/bins must be > 0".to_string());
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

fn parse_next_usize(
    it: &mut std::iter::Peekable<impl Iterator<Item = String>>,
    flag: &str,
) -> Result<usize, String> {
    parse_next_string(it, flag)?
        .parse::<usize>()
        .map_err(|e| format!("{flag} expects usize: {e}"))
}

fn print_help() {
    println!(
        "feature_baseline_writer — rebuild observability.feature_baselines\n\
         \n\
         USAGE:\n  \
           feature_baseline_writer [--dry-run] [--lookback-days 180] [--window-days 30] [--step-days 7] [--bins 10] [--symbol BTCUSDT]\n  \
           feature_baseline_writer --apply --i-understand-this-modifies-db [options]\n\
           OPENCLAW_FEATURE_BASELINE_APPLY=1 feature_baseline_writer [options]\n\
         \n\
         SOURCE:\n  \
           trading.decision_context_snapshots.indicators_snapshot + last_price\n\
         SCHEMA:\n  \
           Rust feature_collector::FEATURE_NAMES / FEATURE_DIM = 34\n\
         ENV:\n  \
           OPENCLAW_DATABASE_URL or OPENCLAW_DATABASE_URL_FILE\n  \
           OPENCLAW_FEATURE_BASELINE_APPLY=1 enables scheduled apply mode without CLI apply flags\n"
    );
}

fn resolve_db_url() -> Result<String, String> {
    secret_env::var_or_file("OPENCLAW_DATABASE_URL")
        .filter(|s| !s.is_empty())
        .ok_or_else(|| "OPENCLAW_DATABASE_URL or OPENCLAW_DATABASE_URL_FILE not set".to_string())
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

    let db_url = match resolve_db_url() {
        Ok(db_url) => db_url,
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

    let samples = match fetch_historical_feature_samples_from_decision_contexts(
        &pool,
        args.lookback_days,
        args.symbol.as_deref(),
    )
    .await
    {
        Ok(samples) => samples,
        Err(e) => {
            eprintln!("error: failed to fetch decision context samples: {e}");
            return EXIT_DB;
        }
    };

    let rows = build_feature_baseline_rows(&samples, args.window_days, args.step_days, args.bins);
    let active_rows = rows.iter().filter(|r| r.valid_until_ms.is_none()).count();

    println!("# mode = {:?}", args.mode);
    println!("# apply_gate = {}", args.apply_gate.label());
    println!("# source = trading.decision_context_snapshots.indicators_snapshot");
    println!("# schema = feature_collector::FEATURE_NAMES / FEATURE_DIM=34");
    println!("# lookback_days = {}", args.lookback_days);
    println!("# window_days = {}", args.window_days);
    println!("# step_days = {}", args.step_days);
    println!("# bins = {}", args.bins);
    println!("# symbol = {}", args.symbol.as_deref().unwrap_or("(all)"));
    println!("# samples = {}", samples.len());
    println!("# baseline_rows = {}", rows.len());
    println!("# active_rows = {}", active_rows);

    if args.mode == Mode::DryRun {
        return EXIT_OK;
    }

    match write_feature_baseline_rows(&pool, &rows).await {
        Ok(summary) => {
            println!("# active_rows_closed = {}", summary.active_rows_closed);
            println!("# rows_written = {}", summary.rows_written);
            EXIT_OK
        }
        Err(e) => {
            eprintln!("error: failed to write feature baselines: {e}");
            EXIT_DB
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parse(argv: &[&str], env_gate: bool) -> Result<Args, String> {
        parse_args_from(argv.iter().map(|s| (*s).to_string()), env_gate)
    }

    #[test]
    fn env_gate_enables_apply_without_cli_ack() {
        let args = parse(&[], true).expect("env-gated apply should parse");

        assert_eq!(args.mode, Mode::Apply);
        assert_eq!(args.apply_gate, ApplyGate::Env);
        assert!(!args.i_understand);
    }

    #[test]
    fn dry_run_cli_overrides_env_gate() {
        let args = parse(&["--dry-run"], true).expect("dry-run should parse");

        assert_eq!(args.mode, Mode::DryRun);
        assert_eq!(args.apply_gate, ApplyGate::None);
    }

    #[test]
    fn apply_without_ack_or_env_is_rejected() {
        let err = parse(&["--apply"], false).expect_err("unguarded apply must fail");

        assert!(err.contains("OPENCLAW_FEATURE_BASELINE_APPLY=1"));
    }

    #[test]
    fn manual_apply_ack_still_works() {
        let args = parse(&["--apply", "--i-understand-this-modifies-db"], false)
            .expect("manual apply ack should parse");

        assert_eq!(args.mode, Mode::Apply);
        assert_eq!(args.apply_gate, ApplyGate::CliAck);
    }

    #[test]
    fn force_flags_remain_rejected() {
        let err = parse(&["--force"], true).expect_err("force flag must stay rejected");

        assert!(err.contains("rejected flag --force"));
    }
}
