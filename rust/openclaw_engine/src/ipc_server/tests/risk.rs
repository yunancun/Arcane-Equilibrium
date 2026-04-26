//! ARCH-RC1 1C-3-B: risk runtime status + consecutive-losses + governor-tier override tests.
//! ARCH-RC1 1C-3-B：風控 runtime 狀態 + 連續虧損清除 + governor 等級覆寫測試。

use super::super::*;
use super::{empty_budget_slot, empty_h_state_cache_slot, empty_teacher_slot, make_test_config, make_test_data_dir};

/// ARCH-RC1 1C-3-B helper: spawn a fake event-consumer that answers
/// `GetRiskRuntimeStatus` with a synthetic JSON snapshot and
/// `ClearConsecutiveLosses` with a count message.
/// ARCH-RC1 1C-3-B 輔助：模擬事件消費者，回傳合成的風控狀態快照與清除計數。
fn setup_risk_runtime_channel(
    cleared_count: usize,
) -> tokio::sync::mpsc::UnboundedSender<PipelineCommand> {
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
    tokio::spawn(async move {
        while let Some(cmd) = rx.recv().await {
            match cmd {
                PipelineCommand::GetRiskRuntimeStatus { response_tx } => {
                    let snap = serde_json::json!({
                        "governor_tier": "Normal",
                        "consecutive_losses_by_symbol": {"BTCUSDT": 2u32},
                        "boot_cooldown_remaining_ms": 0u64,
                        "boot_cooldown_total_ms": 60_000u64,
                        "paper_paused": false,
                        "session_halted": false,
                    });
                    let _ = response_tx.send(Ok(snap.to_string()));
                }
                PipelineCommand::ClearConsecutiveLosses { response_tx } => {
                    let _ = response_tx.send(Ok(format!("cleared {cleared_count} symbol(s)")));
                }
                _ => {}
            }
        }
    });
    tx
}

#[tokio::test]
async fn test_rc1_get_risk_runtime_status_via_ipc() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let tx = setup_risk_runtime_channel(0);
    let req = r#"{"jsonrpc":"2.0","method":"get_risk_runtime_status","params":{},"id":40}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels {
            paper: Some(tx),
            ..Default::default()
        },
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_none(), "error: {:?}", resp.error);
    let result = resp.result.unwrap();
    assert_eq!(result["governor_tier"].as_str().unwrap(), "Normal");
    assert_eq!(result["consecutive_losses_by_symbol"]["BTCUSDT"], 2);
    assert_eq!(result["paper_paused"], false);
}

#[tokio::test]
async fn test_rc1_clear_consecutive_losses_via_ipc() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let tx = setup_risk_runtime_channel(3);
    let req = r#"{"jsonrpc":"2.0","method":"clear_consecutive_losses","params":{},"id":41}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels {
            paper: Some(tx),
            ..Default::default()
        },
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_none(), "error: {:?}", resp.error);
    let result = resp.result.unwrap();
    assert_eq!(result["result"].as_str().unwrap(), "cleared 3 symbol(s)");
}

/// 1C-3-B-2 helper: fake event consumer that processes governor override
/// commands by returning canned success/error JSON.
/// 1C-3-B-2 輔助：模擬事件消費者處理 governor override 命令。
fn setup_governor_override_channel(
    accept_tighter: bool,
    accept_looser: bool,
) -> tokio::sync::mpsc::UnboundedSender<PipelineCommand> {
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
    tokio::spawn(async move {
        while let Some(cmd) = rx.recv().await {
            match cmd {
                PipelineCommand::ForceGovernorTighter {
                    target_tier,
                    reason,
                    response_tx,
                } => {
                    let result = if accept_tighter {
                        Ok(format!(
                            "{{\"from\":\"NORMAL\",\"to\":\"{target_tier}\",\"reason\":\"{reason}\"}}"
                        ))
                    } else {
                        Err("simulated SM rejection".to_string())
                    };
                    let _ = response_tx.send(result);
                }
                PipelineCommand::ForceGovernorLooser {
                    target_tier,
                    reason_code,
                    response_tx,
                    ..
                } => {
                    let result = if accept_looser {
                        Ok(format!(
                            "{{\"from\":\"CAUTIOUS\",\"to\":\"{target_tier}\",\"reason_code\":\"{reason_code}\"}}"
                        ))
                    } else {
                        Err("24h cooldown active".to_string())
                    };
                    let _ = response_tx.send(result);
                }
                _ => {}
            }
        }
    });
    tx
}

#[tokio::test]
async fn test_rc1b2_force_governor_tighter_via_ipc() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let tx = setup_governor_override_channel(true, false);
    let req = r#"{"jsonrpc":"2.0","method":"force_governor_tier_tighter","params":{"target_tier":"CAUTIOUS","reason":"manual probe"},"id":50}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels {
            paper: Some(tx),
            ..Default::default()
        },
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_none(), "error: {:?}", resp.error);
    let result = resp.result.unwrap();
    assert_eq!(result["to"].as_str().unwrap(), "CAUTIOUS");
}

#[tokio::test]
async fn test_rc1b2_force_governor_tighter_missing_reason() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let tx = setup_governor_override_channel(true, false);
    let req = r#"{"jsonrpc":"2.0","method":"force_governor_tier_tighter","params":{"target_tier":"CAUTIOUS"},"id":51}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels {
            paper: Some(tx),
            ..Default::default()
        },
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_some());
}

#[tokio::test]
async fn test_rc1b2_force_governor_looser_cooldown_rejection() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let tx = setup_governor_override_channel(false, false);
    let req = r#"{"jsonrpc":"2.0","method":"force_governor_tier_looser","params":{"target_tier":"NORMAL","reason_code":"false_positive","notes":"test"},"id":52}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels {
            paper: Some(tx),
            ..Default::default()
        },
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_some());
    let err_msg = resp.error.unwrap().message;
    assert!(
        err_msg.contains("cooldown"),
        "expected cooldown error, got: {}",
        err_msg
    );
}

#[tokio::test]
async fn test_rc1b2_force_governor_looser_success() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let tx = setup_governor_override_channel(false, true);
    let req = r#"{"jsonrpc":"2.0","method":"force_governor_tier_looser","params":{"target_tier":"NORMAL","reason_code":"false_positive","notes":""},"id":53}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels {
            paper: Some(tx),
            ..Default::default()
        },
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_none(), "error: {:?}", resp.error);
    let result = resp.result.unwrap();
    assert_eq!(result["reason_code"].as_str().unwrap(), "false_positive");
    assert_eq!(result["to"].as_str().unwrap(), "NORMAL");
}

#[tokio::test]
async fn test_rc1_get_risk_runtime_status_no_channel() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc":"2.0","method":"get_risk_runtime_status","params":{},"id":42}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_some());
}
