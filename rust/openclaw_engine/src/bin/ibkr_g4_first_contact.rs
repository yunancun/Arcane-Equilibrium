//! `ibkr_g4_first_contact` — IBKR B1 G4 首次接觸觸發 bin（ADR-0048 / AMD-2026-07-08-01）。
//!
//! MODULE_NOTE
//! 模塊用途：operator 顯式觸發的 G4 首次接觸 CLI。**default dry-run**（打印 gate 狀態，
//!   不接觸 socket）；唯有 `--contact` 旗標 **且** env `OPENCLAW_IBKR_G4_CONTACT_APPLY=1`
//!   才真 connect（跑 `g4_operator_triggered_first_contact`，打印 `TwsHealthProbeResult`
//!   供 QA 捕獲）。
//! 硬邊界：**無 production caller**——main.rs / boot 絕不 invoke 本 bin；`required-features
//!   = ["ibkr_g4_contact"]` 使 default `cargo build` 完全不編譯它（socket 符號不入引擎
//!   artifact）。真 connect 的 fail-closed gate 由 `g4_operator_triggered_first_contact`
//!   內部強制（env APPLY → sealed re-verify → G4 approval → structural host/port），本 bin
//!   只是薄殼觸發器 + dry-run 揭露面。
//! Owner: PA（設計）+ E3（安全鎖定）+ E1（實作）。

#![cfg(feature = "ibkr_g4_contact")]

use std::process::ExitCode;

use openclaw_engine::ibkr_readonly_tws_client as tws;

#[tokio::main]
async fn main() -> ExitCode {
    let contact = std::env::args().any(|a| a == "--contact");

    // dry-run 揭露面：不接觸 socket，只讀 gate posture。
    let status = tws::g4_first_contact_gate_status();
    println!(
        "[ibkr_g4_first_contact] gate: apply_env={} sealed_present={} approval_valid={} gate_ok={}",
        status.apply_env_set,
        status.sealed_artifact_present,
        status.contact_approval_valid,
        status.gate_ok,
    );

    if !contact {
        println!("[ibkr_g4_first_contact] dry-run (no --contact): no socket contact performed.");
        return ExitCode::SUCCESS;
    }

    // --contact：真 connect。fail-closed gate 由 g4_operator_triggered_first_contact 內部
    // 強制（env APPLY==1 → sealed re-verify → G4 approval → structural host/port → connect）。
    match tws::g4_operator_triggered_first_contact().await {
        Ok(probe) => {
            println!("[ibkr_g4_first_contact] G4 FIRST CONTACT OK: {probe:?}");
            ExitCode::SUCCESS
        }
        Err(e) => {
            // fail-closed：blocked / io / timeout 皆非 0 結束，operator CI 可依 $? 分支。
            eprintln!("[ibkr_g4_first_contact] G4 FIRST CONTACT BLOCKED/FAILED: {e:?}");
            ExitCode::FAILURE
        }
    }
}
