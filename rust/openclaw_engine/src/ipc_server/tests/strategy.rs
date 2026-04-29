//! Phase 3b PF-1: Strategy parameter IPC tests.
//! Phase 3b PF-1：策略參數 IPC 測試。

use super::super::*;
use super::{
    empty_budget_slot, empty_cost_edge_advisor_slot, empty_h_state_cache_slot, empty_teacher_slot,
    make_test_config, make_test_data_dir,
};

/// Helper: create a paper_cmd channel with a consumer that handles param commands.
/// 輔助：創建帶有參數命令消費者的 paper_cmd 通道。
fn setup_strategy_param_channel() -> tokio::sync::mpsc::UnboundedSender<PipelineCommand> {
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
    tokio::spawn(async move {
        use crate::strategies::{ma_crossover::MaCrossover, Strategy};
        let mut strategy: Box<dyn Strategy> = Box::new(MaCrossover::new());
        while let Some(cmd) = rx.recv().await {
            match cmd {
                PipelineCommand::UpdateStrategyParams {
                    strategy_name,
                    params_json,
                    response_tx,
                } => {
                    let result = if strategy.name().eq_ignore_ascii_case(&strategy_name) {
                        strategy
                            .update_params_json(&params_json)
                            .map(|()| format!("params updated for {}", strategy_name))
                    } else {
                        Err(format!("strategy not found: {strategy_name}"))
                    };
                    let _ = response_tx.send(result);
                }
                PipelineCommand::GetStrategyParams {
                    strategy_name,
                    response_tx,
                } => {
                    let result = if strategy.name().eq_ignore_ascii_case(&strategy_name) {
                        Ok(strategy.get_params_json())
                    } else {
                        Err(format!("strategy not found: {strategy_name}"))
                    };
                    let _ = response_tx.send(result);
                }
                PipelineCommand::GetParamRanges {
                    strategy_name,
                    response_tx,
                } => {
                    let result = if strategy.name().eq_ignore_ascii_case(&strategy_name) {
                        Ok(strategy.param_ranges_json())
                    } else {
                        Err(format!("strategy not found: {strategy_name}"))
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
async fn test_get_param_ranges_via_ipc() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let tx = setup_strategy_param_channel();
    let req = r#"{"jsonrpc": "2.0", "method": "get_param_ranges", "params": {"strategy_name": "ma_crossover"}, "id": 30}"#;
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
        &empty_cost_edge_advisor_slot(),
    )
    .await;
    assert!(resp.error.is_none(), "error: {:?}", resp.error);
    let result = resp.result.unwrap();
    let ranges_str = result["result"].as_str().unwrap();
    let ranges: Vec<serde_json::Value> = serde_json::from_str(ranges_str).unwrap();
    assert!(!ranges.is_empty(), "param_ranges should not be empty");
}

#[tokio::test]
async fn test_get_strategy_params_via_ipc() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let tx = setup_strategy_param_channel();
    let req = r#"{"jsonrpc": "2.0", "method": "get_strategy_params", "params": {"strategy_name": "ma_crossover"}, "id": 31}"#;
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
        &empty_cost_edge_advisor_slot(),
    )
    .await;
    assert!(resp.error.is_none(), "error: {:?}", resp.error);
    let result = resp.result.unwrap();
    let params_str = result["result"].as_str().unwrap();
    let params: serde_json::Value = serde_json::from_str(params_str).unwrap();
    assert!(
        params.get("cooldown_ms").is_some(),
        "should contain cooldown_ms"
    );
}

#[tokio::test]
async fn test_update_strategy_params_via_ipc() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let tx = setup_strategy_param_channel();
    let req = r#"{"jsonrpc": "2.0", "method": "update_strategy_params", "params": {"strategy_name": "ma_crossover", "params_json": "{\"cooldown_ms\":600000,\"adx_threshold\":30.0,\"default_qty\":0.02,\"regime_filter_enabled\":true,\"higher_tf_alpha\":0.08}"}, "id": 32}"#;
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
        &empty_cost_edge_advisor_slot(),
    )
    .await;
    assert!(resp.error.is_none(), "error: {:?}", resp.error);
}

#[tokio::test]
async fn test_update_strategy_params_nonexistent() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let tx = setup_strategy_param_channel();
    let req = r#"{"jsonrpc": "2.0", "method": "update_strategy_params", "params": {"strategy_name": "nonexistent_strategy", "params_json": "{}"}, "id": 33}"#;
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
        &empty_cost_edge_advisor_slot(),
    )
    .await;
    assert!(
        resp.error.is_some(),
        "should error for nonexistent strategy"
    );
}

#[tokio::test]
async fn test_update_strategy_params_missing_params() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let tx = setup_strategy_param_channel();
    let req = r#"{"jsonrpc": "2.0", "method": "update_strategy_params", "params": {"strategy_name": "ma_crossover"}, "id": 34}"#;
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
        &empty_cost_edge_advisor_slot(),
    )
    .await;
    assert!(
        resp.error.is_some(),
        "should error when params_json missing"
    );
}
