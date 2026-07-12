//! `ibkr_phase2_seal` — Rust-only, no-contact Phase2 immutable seal control.
//!
//! With no arguments (or `--dry-run`) this reads redacted local posture only.
//! A ledger append requires *both* `--apply` and literal
//! `OPENCLAW_IBKR_PHASE2_SEAL_APPLY=1`; it never opens TWS/Gateway sockets,
//! reads credentials, starts services, queries DB, activates live trading, or
//! routes an order.  G4/contact and the Rust activation envelope are separate.

use std::process::ExitCode;

use openclaw_engine::ibkr_phase2_gate_producer::{
    phase2_apply_seal_if_explicitly_requested, phase2_seal_dry_run,
};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum CliMode {
    DryRun,
    Apply,
}

fn parse_mode(args: &[String]) -> Result<CliMode, &'static str> {
    if args
        .iter()
        .any(|arg| arg != "--dry-run" && arg != "--apply")
        || args.iter().filter(|arg| arg.as_str() == "--apply").count() > 1
        || args
            .iter()
            .filter(|arg| arg.as_str() == "--dry-run")
            .count()
            > 1
    {
        return Err("only one --dry-run or one --apply is accepted");
    }
    let apply = args.iter().any(|arg| arg == "--apply");
    let dry_run = args.iter().any(|arg| arg == "--dry-run");
    if apply && dry_run {
        return Err("--dry-run and --apply are mutually exclusive");
    }
    Ok(if apply {
        CliMode::Apply
    } else {
        CliMode::DryRun
    })
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.iter().any(|arg| arg == "--help" || arg == "-h") {
        println!(
            "ibkr_phase2_seal [--dry-run | --apply]\n\
             default: read-only redacted local posture; no broker contact\n\
             apply: requires --apply plus OPENCLAW_IBKR_PHASE2_SEAL_APPLY=1\n\
             inputs: owner-only no-credential phase2_seal_inputs.json and\n\
                     phase2_seal_control_approval.json under OPENCLAW_DATA_DIR"
        );
        return ExitCode::SUCCESS;
    }
    let mode = match parse_mode(&args) {
        Ok(mode) => mode,
        Err(reason) => {
            eprintln!("ibkr_phase2_seal: {reason}");
            return ExitCode::from(2);
        }
    };
    if mode == CliMode::DryRun {
        let status = phase2_seal_dry_run();
        println!(
            "{{\"status\":{},\"no_contact\":true,\"inputs_present\":{},\"approval_present\":{},\"active_current_build\":{}}}",
            serde_json::to_string(&status.status).unwrap_or_else(|_| "\"rejected\"".to_string()),
            status.inputs_present,
            status.approval_present,
            status.active_current_build,
        );
        return ExitCode::SUCCESS;
    }
    let outcome = phase2_apply_seal_if_explicitly_requested(true);
    println!(
        "{{\"status\":{},\"no_contact\":true,\"wrote_generation\":{},\"wrote_control\":{}}}",
        serde_json::to_string(&outcome.status).unwrap_or_else(|_| "\"blocked\"".to_string()),
        outcome.wrote_generation,
        outcome.wrote_control,
    );
    if matches!(
        outcome.status.as_str(),
        "applied_no_contact" | "already_applied_no_contact"
    ) {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(3)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dry_run_and_apply_are_rejected_together() {
        assert_eq!(
            parse_mode(&["--dry-run".to_string(), "--apply".to_string()]),
            Err("--dry-run and --apply are mutually exclusive")
        );
    }

    #[test]
    fn default_and_each_single_mode_are_unambiguous() {
        assert_eq!(parse_mode(&[]), Ok(CliMode::DryRun));
        assert_eq!(parse_mode(&["--dry-run".to_string()]), Ok(CliMode::DryRun));
        assert_eq!(parse_mode(&["--apply".to_string()]), Ok(CliMode::Apply));
    }
}
