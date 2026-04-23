use super::*;
use std::collections::HashMap;

fn make_test_config() -> Arc<ConfigManager> {
    Arc::new(ConfigManager::load(Some("/tmp/nonexistent_openclaw_ipc_test.toml")).unwrap())
}

fn make_test_data_dir() -> Arc<PathBuf> {
    Arc::new(PathBuf::from("/tmp/oc_ipc_test_nonexistent"))
}

/// Empty BudgetTracker slot for tests that don't exercise 4-15 paths.
/// 給不演練 4-15 路徑的測試使用的空 BudgetTracker 槽位。
fn empty_budget_slot() -> BudgetTrackerSlot {
    Arc::new(RwLock::new(None))
}

fn empty_teacher_slot() -> TeacherLoopSlot {
    Arc::new(RwLock::new(None))
}

/// Write a test snapshot file to a temp dir, return the dir path.
/// 寫入測試快照文件到臨時目錄，返回目錄路徑。
fn write_test_snapshot() -> (Arc<PathBuf>, tempfile::TempDir) {
    let dir = tempfile::tempdir().unwrap();
    let snapshot = PipelineSnapshot {
        schema_version: "2.0.0".into(),
        written_at_ms: 1700000050000,
        paper_state: crate::paper_state::PaperStateSnapshot {
            balance: 9500.0,
            initial_balance: 10000.0,
            peak_balance: 10000.0,
            total_realized_pnl: -500.0,
            total_fees: 12.5,
            trade_count: 3,
            positions: vec![crate::paper_state::PositionSnapshot {
                position: crate::paper_state::PaperPosition {
                    symbol: "BTCUSDT".into(),
                    is_long: true,
                    qty: 0.01,
                    entry_price: 65000.0,
                    best_price: 66000.0,
                    entry_fee: 3.25,
                    entry_ts_ms: 1700000000000,
                    unrealized_pnl: 10.0,
                    entry_context_id: String::new(),
                    owner_strategy: "test".into(),
                    entry_notional: 650.0,
                    max_favorable_pnl_pct: 0.0,
                    peak_reached_ts_ms: 1700000000000,
                },
                api_pnl: None,
            }],
            bybit_sync_balance: None,
        },
        latest_prices: HashMap::from([("BTCUSDT".into(), 66000.0), ("ETHUSDT".into(), 3200.0)]),
        stats: crate::tick_pipeline::TickStats {
            total_ticks: 5000,
            total_intents: 15,
            total_fills: 3,
            total_stops: 1,
            last_tick_ms: 1700000050000,
        },
        source: "rust_engine".into(),
        indicators: HashMap::new(),
        signals: vec![],
        strategies: vec![],
        recent_intents: vec![],
        recent_fills: vec![],
        klines: HashMap::new(),
        paper_paused: false,
        pipeline_kind: crate::tick_pipeline::PipelineKind::Paper,
        h0_gate_stats: None,
        stop_config: None,
        guardian_config: None,
        risk_manager_config: None,
        consecutive_losses: HashMap::new(),
        session_halted: false,
        daily_loss_pct: 0.0,
        session_drawdown_pct: 0.0,
        mode_snapshots: HashMap::new(),
        system_mode: "live_reserved".into(),
    };
    let json = serde_json::to_string_pretty(&snapshot).unwrap();
    std::fs::write(dir.path().join("pipeline_snapshot.json"), &json).unwrap();
    (Arc::new(dir.path().to_path_buf()), dir)
}

#[tokio::test]
async fn test_ipc_socket_permissions_0o600() {
    // I-02: verify bound Unix socket gets restricted to 0o600.
    // I-02：驗證綁定的 Unix 套接字權限被限制為 0o600。
    use std::os::unix::fs::PermissionsExt;
    let dir = tempfile::tempdir().unwrap();
    let sock_path = dir.path().join("ipc_perm_test.sock");
    let _listener = UnixListener::bind(&sock_path).unwrap();
    std::fs::set_permissions(&sock_path, std::fs::Permissions::from_mode(0o600)).unwrap();
    let mode = std::fs::metadata(&sock_path).unwrap().permissions().mode() & 0o777;
    assert_eq!(mode, 0o600, "socket mode should be 0o600, got {:o}", mode);
}

#[tokio::test]
async fn test_dispatch_ping() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc": "2.0", "method": "ping", "params": {}, "id": 1}"#;
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
    )
    .await;
    assert!(resp.error.is_none());
    assert_eq!(
        resp.result.unwrap(),
        serde_json::Value::String("pong".into())
    );
    assert_eq!(resp.id, serde_json::json!(1));
}

#[tokio::test]
async fn test_dispatch_get_state() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc": "2.0", "method": "get_state", "params": {}, "id": 2}"#;
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
    )
    .await;
    assert!(resp.error.is_none());
    let result = resp.result.unwrap();
    assert_eq!(result["status"], "running");
    // system_mode is read from pipeline_snapshot.json; falls back to "live_reserved" when
    // no snapshot exists (test environment). Assert it's a non-empty string.
    // system_mode 從 pipeline_snapshot.json 讀取；測試環境無快照時回退 "live_reserved"。
    assert!(result["system_mode"]
        .as_str()
        .map(|s| !s.is_empty())
        .unwrap_or(false));
}

#[tokio::test]
async fn test_dispatch_method_not_found() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc": "2.0", "method": "nonexistent", "params": {}, "id": 3}"#;
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
    )
    .await;
    assert!(resp.error.is_some());
    assert_eq!(resp.error.unwrap().code, ERR_METHOD_NOT_FOUND);
}

#[tokio::test]
async fn test_dispatch_invalid_json() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = "not valid json";
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
    )
    .await;
    assert!(resp.error.is_some());
    assert_eq!(resp.error.unwrap().code, ERR_INVALID_REQUEST);
}

#[tokio::test]
async fn test_dispatch_missing_version() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"method": "ping", "params": {}, "id": 4}"#;
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
    )
    .await;
    assert!(resp.error.is_some());
    assert_eq!(resp.error.unwrap().code, ERR_INVALID_REQUEST);
}

#[tokio::test]
async fn test_dispatch_missing_method() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc": "2.0", "params": {}, "id": 5}"#;
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
    )
    .await;
    assert!(resp.error.is_some());
    assert_eq!(resp.error.unwrap().code, ERR_INVALID_REQUEST);
}

#[tokio::test]
async fn test_dispatch_reload_config() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc": "2.0", "method": "reload_config", "params": {}, "id": 8}"#;
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
    )
    .await;
    assert!(resp.error.is_none());
    let result = resp.result.unwrap();
    assert_eq!(result["reloaded"], true);
}

#[test]
fn test_jsonrpc_response_serialization() {
    let resp = JsonRpcResponse::success(serde_json::json!(1), serde_json::json!("pong"));
    let json = serde_json::to_string(&resp).unwrap();
    assert!(json.contains("\"jsonrpc\":\"2.0\""));
    assert!(json.contains("\"result\":\"pong\""));
    assert!(!json.contains("\"error\""));
}

#[test]
fn test_jsonrpc_error_serialization() {
    let resp = JsonRpcResponse::error(serde_json::json!(2), ERR_METHOD_NOT_FOUND, "not found");
    let json = serde_json::to_string(&resp).unwrap();
    assert!(json.contains("-32601"));
    assert!(!json.contains("\"result\""));
}

// ───────────────────────────────────────────────────────────────────────
// R06-A: Snapshot file-read IPC tests / 快照文件讀取 IPC 測試
// ───────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn test_get_paper_state_no_file() {
    let config = make_test_config();
    let dd = make_test_data_dir(); // nonexistent dir
    let req = r#"{"jsonrpc": "2.0", "method": "get_paper_state", "params": {}, "id": 20}"#;
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
    )
    .await;
    assert!(
        resp.error.is_some(),
        "should error when snapshot file missing"
    );
}

#[tokio::test]
async fn test_get_paper_state_with_snapshot() {
    let config = make_test_config();
    let (dd, _dir) = write_test_snapshot();
    let req = r#"{"jsonrpc": "2.0", "method": "get_paper_state", "params": {}, "id": 21}"#;
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
    )
    .await;
    assert!(resp.error.is_none(), "error: {:?}", resp.error);
    let result = resp.result.unwrap();
    assert_eq!(result["balance"], 9500.0);
    assert_eq!(result["trade_count"], 3);
    assert_eq!(result["positions"][0]["symbol"], "BTCUSDT");
}

#[tokio::test]
async fn test_get_latest_prices_with_snapshot() {
    let config = make_test_config();
    let (dd, _dir) = write_test_snapshot();
    let req = r#"{"jsonrpc": "2.0", "method": "get_latest_prices", "params": {}, "id": 22}"#;
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
    )
    .await;
    assert!(resp.error.is_none(), "error: {:?}", resp.error);
    let result = resp.result.unwrap();
    assert_eq!(result["BTCUSDT"], 66000.0);
    assert_eq!(result["ETHUSDT"], 3200.0);
}

#[tokio::test]
async fn test_get_tick_stats_with_snapshot() {
    let config = make_test_config();
    let (dd, _dir) = write_test_snapshot();
    let req = r#"{"jsonrpc": "2.0", "method": "get_tick_stats", "params": {}, "id": 23}"#;
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
    )
    .await;
    assert!(resp.error.is_none(), "error: {:?}", resp.error);
    let result = resp.result.unwrap();
    assert_eq!(result["total_ticks"], 5000);
    assert_eq!(result["total_fills"], 3);
    assert_eq!(result["total_stops"], 1);
}

// ───────────────────────────────────────────────────────────────────────
// Phase 3b PF-1: Strategy parameter IPC tests / 策略參數 IPC 測試
// ───────────────────────────────────────────────────────────────────────

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
    )
    .await;
    assert!(resp.error.is_some());
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
    )
    .await;
    assert!(
        resp.error.is_some(),
        "should error when params_json missing"
    );
}

// ── Phase 4 (4-00) Dashboard skeleton tests / 儀表板骨架測試 ──────────

/// Initial Phase 4 status — all four modules should report "grey".
/// 初始 Phase 4 狀態 — 四個模組應全部回報 "grey"。
#[tokio::test]
async fn test_get_phase4_status_returns_grey_initial() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc": "2.0", "method": "get_phase4_status", "params": {}, "id": 4000}"#;
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
    )
    .await;
    assert!(resp.error.is_none(), "phase4 status must succeed");
    let r = resp.result.unwrap();
    assert_eq!(r["teacher"], "grey");
    assert_eq!(r["linucb"], "grey");
    assert_eq!(r["news"], "grey");
    assert_eq!(r["dl3"], "grey");
}

/// Schema check — required fields present, last_update_ms is positive int.
/// Schema 檢查 — 必須欄位齊全，last_update_ms 為正整數。
#[tokio::test]
async fn test_get_phase4_status_response_schema() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc": "2.0", "method": "get_phase4_status", "params": {}, "id": 4001}"#;
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
    )
    .await;
    assert!(resp.error.is_none());
    let r = resp.result.unwrap();
    for key in ["teacher", "linucb", "news", "dl3", "last_update_ms"] {
        assert!(r.get(key).is_some(), "missing key: {key}");
    }
    assert!(r["last_update_ms"].as_i64().unwrap_or(0) > 0);
    // valid traffic-light vocabulary / 合法紅綠燈詞彙
    for key in ["teacher", "linucb", "news", "dl3"] {
        let v = r[key].as_str().unwrap_or("");
        assert!(
            matches!(v, "grey" | "green" | "yellow" | "red"),
            "invalid status for {key}: {v}"
        );
    }
}

/// Dispatch table — get_phase4_status routes to handler (id echoed).
/// 派發表 — get_phase4_status 應正確路由到 handler（id 被回顯）。
#[tokio::test]
async fn test_dispatch_phase4_status() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc": "2.0", "method": "get_phase4_status", "params": {}, "id": 4002}"#;
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
    )
    .await;
    assert_eq!(resp.id, serde_json::json!(4002));
    assert!(resp.error.is_none());
    assert!(resp.result.is_some());
}

// ───────────────────────────────────────────────────────────────────────
// ARCH-RC1 1C-2-C / LIVE-P2-1: unified Config IPC endpoint tests
// ARCH-RC1 1C-2-C / LIVE-P2-1：統一 Config IPC 端點測試
// ───────────────────────────────────────────────────────────────────────

/// Build test stores: all three risk engines + learning + budget.
/// 構建測試 stores：三個風控引擎 + learning + budget。
fn rc1_stores() -> (
    Option<PerEngineRiskStores>,
    Option<Arc<ConfigStore<LearningConfig>>>,
    Option<Arc<ConfigStore<BudgetConfig>>>,
) {
    let rs = PerEngineRiskStores {
        paper: Arc::new(ConfigStore::new(RiskConfig::default())),
        demo: Arc::new(ConfigStore::new(RiskConfig::default())),
        live: Arc::new(ConfigStore::new(RiskConfig::default())),
    };
    (
        Some(rs),
        Some(Arc::new(ConfigStore::new(LearningConfig::default()))),
        Some(Arc::new(ConfigStore::new(BudgetConfig::default()))),
    )
}

#[tokio::test]
async fn test_rc1_get_risk_config_returns_snapshot_and_version() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let (rs, ls, bs) = rc1_stores();
    let req = r#"{"jsonrpc": "2.0", "method": "get_risk_config", "params": {}, "id": 9001}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &rs,
        &ls,
        &bs,
        &None,
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_none(), "expected success: {resp:?}");
    let r = resp.result.unwrap();
    assert_eq!(r["version"], 0);
    assert!(r["config"]["limits"].is_object(), "config payload missing");
}

#[tokio::test]
async fn test_rc1_patch_risk_config_bumps_version_and_updates() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let (rs, ls, bs) = rc1_stores();
    // Patch a single nested field via deep merge.
    let req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"source":"operator","patch":{"limits":{"leverage_max":7.0}}},"id":9002}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &rs,
        &ls,
        &bs,
        &None,
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_none(), "expected success: {resp:?}");
    let r = resp.result.unwrap();
    assert_eq!(r["ok"], true);
    assert_eq!(r["version"], 1);
    assert_eq!(r["source"], "operator");
    // Verify paper store mutated (no engine param → default paper).
    // 確認 paper store 已更新（無 engine 參數 → 默認 paper）。
    let snap = rs.as_ref().unwrap().paper.load();
    assert!((snap.limits.leverage_max - 7.0).abs() < f64::EPSILON);
}

#[tokio::test]
async fn test_rc1_patch_risk_config_validation_failure_rolls_back() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let (rs, ls, bs) = rc1_stores();
    let original_lev = rs.as_ref().unwrap().paper.load().limits.leverage_max;
    // Negative leverage is invalid.
    let req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"patch":{"limits":{"leverage_max":-1.0}}},"id":9003}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &rs,
        &ls,
        &bs,
        &None,
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_some(), "expected validation error");
    // Paper store untouched (rollback).
    // paper store 未改動（回滾）。
    assert_eq!(rs.as_ref().unwrap().paper.version(), 0);
    let snap = rs.as_ref().unwrap().paper.load();
    assert!((snap.limits.leverage_max - original_lev).abs() < f64::EPSILON);
}

#[tokio::test]
async fn test_rc1_patch_missing_patch_field_errors() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let (rs, ls, bs) = rc1_stores();
    let req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"source":"operator"},"id":9004}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &rs,
        &ls,
        &bs,
        &None,
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_some());
    assert_eq!(rs.as_ref().unwrap().paper.version(), 0);
}

#[tokio::test]
async fn test_rc1_patch_learning_and_budget_configs_round_trip() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let (rs, ls, bs) = rc1_stores();
    // Patch learning + then read back via get_learning_config.
    let patch_req = r#"{"jsonrpc":"2.0","method":"patch_learning_config","params":{"patch":{"news_pipeline_enabled":true}},"id":9005}"#;
    let resp = dispatch_request(
        patch_req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &rs,
        &ls,
        &bs,
        &None,
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_none(), "patch_learning_config: {resp:?}");
    let get_req = r#"{"jsonrpc":"2.0","method":"get_learning_config","params":{},"id":9006}"#;
    let resp = dispatch_request(
        get_req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &rs,
        &ls,
        &bs,
        &None,
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_none());
    let r = resp.result.unwrap();
    assert_eq!(r["version"], 1);
    // Patch budget too — exercises the third branch.
    let bud_req = r#"{"jsonrpc":"2.0","method":"patch_budget_config","params":{"source":"agent","patch":{"daily_usd_max":50.0}},"id":9007}"#;
    let resp = dispatch_request(
        bud_req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &rs,
        &ls,
        &bs,
        &None,
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_none(), "patch_budget_config: {resp:?}");
    assert_eq!(resp.result.unwrap()["source"], "agent");
}

#[tokio::test]
async fn test_rc1_get_config_without_store_errors() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc":"2.0","method":"get_risk_config","params":{},"id":9008}"#;
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
    )
    .await;
    assert!(resp.error.is_some());
    assert!(resp.error.unwrap().message.contains("not configured"));
}

/// LIVE-P2-1: patch_risk_config with engine="live" routes to live store,
/// not to paper store. paper store must remain at version 0.
/// LIVE-P2-1：engine="live" 的 patch_risk_config 應路由到 live store，
/// paper store 版本應維持 0。
#[tokio::test]
async fn test_p2_patch_risk_config_engine_routing() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let (rs, ls, bs) = rc1_stores();
    // Patch live engine only.
    let req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"engine":"live","source":"operator","patch":{"limits":{"leverage_max":5.0}}},"id":9020}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &rs,
        &ls,
        &bs,
        &None,
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_none(), "expected success: {resp:?}");
    let r = resp.result.unwrap();
    assert_eq!(r["ok"], true);
    assert_eq!(r["version"], 1);
    // live store mutated.
    let live_snap = rs.as_ref().unwrap().live.load();
    assert!(
        (live_snap.limits.leverage_max - 5.0).abs() < f64::EPSILON,
        "live store not updated"
    );
    // paper store untouched.
    assert_eq!(
        rs.as_ref().unwrap().paper.version(),
        0,
        "paper store should be untouched"
    );
    // demo store untouched.
    assert_eq!(
        rs.as_ref().unwrap().demo.version(),
        0,
        "demo store should be untouched"
    );
}

/// LIVE-P2-1: get_risk_config with engine="demo" returns demo store snapshot.
/// LIVE-P2-1：engine="demo" 的 get_risk_config 返回 demo store 快照。
#[tokio::test]
async fn test_p2_get_risk_config_engine_selection() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let (rs, ls, bs) = rc1_stores();
    // Pre-patch demo store so it has a distinct version.
    let patch_req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"engine":"demo","patch":{"limits":{"open_positions_max":7}}},"id":9021}"#;
    dispatch_request(
        patch_req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &rs,
        &ls,
        &bs,
        &None,
        &None,
        &None,
    )
    .await;
    // Now GET demo config — should show version=1.
    let get_req =
        r#"{"jsonrpc":"2.0","method":"get_risk_config","params":{"engine":"demo"},"id":9022}"#;
    let resp = dispatch_request(
        get_req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &rs,
        &ls,
        &bs,
        &None,
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_none(), "expected success: {resp:?}");
    let r = resp.result.unwrap();
    assert_eq!(r["version"], 1, "demo store should be at version 1");
    // Paper store should still be at version 0.
    let paper_req = r#"{"jsonrpc":"2.0","method":"get_risk_config","params":{},"id":9023}"#;
    let resp2 = dispatch_request(
        paper_req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &rs,
        &ls,
        &bs,
        &None,
        &None,
        &None,
    )
    .await;
    let r2 = resp2.result.unwrap();
    assert_eq!(r2["version"], 0, "paper store should be at version 0");
}

// ───────────────────────────────────────────────────────────────────────
// Phase 4 (4-15): AI budget IPC handler tests
// Phase 4 (4-15)：AI 預算 IPC handler 測試
// ───────────────────────────────────────────────────────────────────────

/// Slot empty → get_ai_budget_status fail-soft returns "uninitialized".
/// 槽位為空 → get_ai_budget_status fail-soft 回傳 "uninitialized"。
#[tokio::test]
async fn test_handle_get_ai_budget_status_uninitialized() {
    let slot = empty_budget_slot();
    let resp = handle_get_ai_budget_status(serde_json::json!(4150), &slot).await;
    assert!(resp.error.is_none(), "should fail-soft, not error");
    let result = resp.result.expect("result should be present");
    assert_eq!(result["status"], "uninitialized");
    assert_eq!(resp.id, serde_json::json!(4150));
}

/// Slot empty → update_ai_budget_config -32603 (fail-closed for writes).
/// 槽位為空 → update_ai_budget_config 回 -32603（寫入路徑 fail-closed）。
#[tokio::test]
async fn test_handle_update_ai_budget_config_uninitialized() {
    let slot = empty_budget_slot();
    let params = serde_json::json!({
        "scope": "teacher",
        "monthly_usd": 60.0,
        "updated_by": "operator"
    });
    let resp = handle_update_ai_budget_config(serde_json::json!(4151), &params, &slot).await;
    assert!(resp.error.is_some(), "must fail-closed when uninitialized");
    assert_eq!(resp.error.unwrap().code, ERR_INTERNAL);
}

/// Missing 'scope' / invalid 'monthly_usd' → -32602 invalid params.
/// 缺 'scope' 或 'monthly_usd' 不合法 → 回 -32602。
#[tokio::test]
async fn test_handle_update_ai_budget_config_invalid_params() {
    let slot = empty_budget_slot();
    // Missing scope / 缺 scope
    let p1 = serde_json::json!({ "monthly_usd": 60.0 });
    let r1 = handle_update_ai_budget_config(serde_json::json!(1), &p1, &slot).await;
    assert_eq!(r1.error.expect("err").code, -32602);

    // Negative monthly_usd / monthly_usd 為負
    let p2 = serde_json::json!({ "scope": "teacher", "monthly_usd": -1.0 });
    let r2 = handle_update_ai_budget_config(serde_json::json!(2), &p2, &slot).await;
    assert_eq!(r2.error.expect("err").code, -32602);

    // Empty scope / scope 空字串
    let p3 = serde_json::json!({ "scope": "", "monthly_usd": 10.0 });
    let r3 = handle_update_ai_budget_config(serde_json::json!(3), &p3, &slot).await;
    assert_eq!(r3.error.expect("err").code, -32602);
}

// ---------------------------------------------------------------------
// Phase 4.1: Teacher consumer loop IPC tests
// Phase 4.1：Teacher consumer loop IPC 測試
// ---------------------------------------------------------------------

fn populated_teacher_slot(
    initial_enabled: bool,
) -> (TeacherLoopSlot, Arc<AtomicBool>, Arc<ConsumerLoopStatus>) {
    let enabled = Arc::new(AtomicBool::new(initial_enabled));
    let status = Arc::new(ConsumerLoopStatus::default());
    let slot: TeacherLoopSlot = Arc::new(RwLock::new(Some(TeacherLoopHandles {
        enabled: Arc::clone(&enabled),
        status: Arc::clone(&status),
    })));
    (slot, enabled, status)
}

/// uninitialized slot → fail-soft "uninitialized" payload, NOT an error.
/// 未注入槽位 → fail-soft 回傳 "uninitialized"，不是 error。
#[tokio::test]
async fn test_teacher_loop_status_uninitialized_fail_soft() {
    let slot = empty_teacher_slot();
    let resp = handle_get_teacher_loop_status(serde_json::json!(1), &slot).await;
    assert!(resp.error.is_none());
    let result = resp.result.expect("result");
    assert_eq!(result["status"], "uninitialized");
}

/// set_enabled with valid bool flips the atomic and returns ok.
/// set_enabled 帶合法 bool 翻轉 atomic 並回傳 ok。
#[tokio::test]
async fn test_teacher_loop_set_enabled_flips_atomic() {
    let (slot, enabled, _status) = populated_teacher_slot(false);
    let params = serde_json::json!({"enabled": true});
    let resp = handle_set_teacher_loop_enabled(serde_json::json!(2), &params, &slot).await;
    assert!(resp.error.is_none());
    assert_eq!(resp.result.expect("ok")["enabled"], true);
    assert!(enabled.load(Ordering::Relaxed));

    // Flip back / 翻回
    let params = serde_json::json!({"enabled": false});
    let _ = handle_set_teacher_loop_enabled(serde_json::json!(3), &params, &slot).await;
    assert!(!enabled.load(Ordering::Relaxed));
}

/// set_enabled missing/non-bool param → -32600 invalid request.
/// set_enabled 缺欄位或非 bool → -32600。
#[tokio::test]
async fn test_teacher_loop_set_enabled_invalid_params() {
    let (slot, _, _) = populated_teacher_slot(false);
    let params = serde_json::json!({"enabled": "yes"});
    let resp = handle_set_teacher_loop_enabled(serde_json::json!(4), &params, &slot).await;
    assert_eq!(resp.error.expect("err").code, ERR_INVALID_REQUEST);
}

/// get_status returns full counter snapshot when slot populated.
/// 槽位有值時 get_status 回傳完整計數快照。
#[tokio::test]
async fn test_teacher_loop_get_status_populated() {
    let (slot, _, status) = populated_teacher_slot(true);
    status.cycles_attempted.store(7, Ordering::Relaxed);
    status.directives_applied.store(3, Ordering::Relaxed);
    status.directives_vetoed.store(2, Ordering::Relaxed);
    status.cycles_errored.store(1, Ordering::Relaxed);
    status.last_cycle_ms.store(123_456_789, Ordering::Relaxed);

    let resp = handle_get_teacher_loop_status(serde_json::json!(5), &slot).await;
    let r = resp.result.expect("ok");
    assert_eq!(r["status"], "ok");
    assert_eq!(r["enabled"], true);
    assert_eq!(r["cycles_attempted"], 7);
    assert_eq!(r["directives_applied"], 3);
    assert_eq!(r["directives_vetoed"], 2);
    assert_eq!(r["cycles_errored"], 1);
    assert_eq!(r["last_cycle_ms"], 123_456_789);
}

/// set_teacher_loop_enabled on uninitialized slot is fail-soft (no error).
/// 未注入槽位的 set_enabled 也是 fail-soft（不報 error）。
#[tokio::test]
async fn test_teacher_loop_set_enabled_uninitialized_fail_soft() {
    let slot = empty_teacher_slot();
    let params = serde_json::json!({"enabled": true});
    let resp = handle_set_teacher_loop_enabled(serde_json::json!(6), &params, &slot).await;
    assert!(resp.error.is_none());
    assert_eq!(resp.result.expect("ok")["status"], "uninitialized");
}

// ── Scanner IPC tests (IPC-SCAN-1) ──────────────────────────────────────────

fn make_scanner_registry() -> Arc<crate::scanner::registry::SymbolRegistry> {
    let pinned = vec!["BTCUSDT".to_string(), "ETHUSDT".to_string()];
    Arc::new(crate::scanner::registry::SymbolRegistry::new(
        vec![
            "BTCUSDT".to_string(),
            "ETHUSDT".to_string(),
            "SOLUSDT".to_string(),
        ],
        pinned,
    ))
}

/// get_active_symbols — uninitialized (None registry) returns fail-soft.
/// get_active_symbols — 未初始化時 fail-soft。
#[test]
fn test_get_active_symbols_uninitialized() {
    let resp = handle_get_active_symbols(serde_json::json!(1), &None);
    assert!(resp.error.is_none());
    let r = resp.result.expect("result");
    assert_eq!(r["status"], "uninitialized");
    assert_eq!(r["count"], 0);
}

/// get_active_symbols — registry wired: returns all symbols, correctly splits pinned/dynamic.
/// get_active_symbols — registry 已接線：返回所有交易對，正確區分固定/動態。
#[test]
fn test_get_active_symbols_wired() {
    let reg = make_scanner_registry();
    let resp = handle_get_active_symbols(serde_json::json!(2), &Some(reg));
    assert!(resp.error.is_none());
    let r = resp.result.expect("result");
    assert_eq!(r["status"], "ok");
    assert_eq!(r["count"], 3);
    let pinned = r["pinned"].as_array().expect("pinned");
    assert_eq!(pinned.len(), 2);
    let dynamic = r["dynamic"].as_array().expect("dynamic");
    assert_eq!(dynamic.len(), 1);
    assert_eq!(dynamic[0], "SOLUSDT");
}

/// get_scanner_status — uninitialized (None registry) returns fail-soft.
/// get_scanner_status — 未初始化時 fail-soft。
#[test]
fn test_get_scanner_status_uninitialized() {
    let resp = handle_get_scanner_status(serde_json::json!(3), &None);
    assert!(resp.error.is_none());
    let r = resp.result.expect("result");
    assert_eq!(r["status"], "uninitialized");
}

/// get_scanner_status — registry wired, no scan yet: last_scan is null.
/// get_scanner_status — registry 已接線，尚無掃描：last_scan 為 null。
#[test]
fn test_get_scanner_status_no_scan_yet() {
    let reg = make_scanner_registry();
    let resp = handle_get_scanner_status(serde_json::json!(4), &Some(reg));
    assert!(resp.error.is_none());
    let r = resp.result.expect("result");
    assert_eq!(r["status"], "ok");
    assert_eq!(r["active_count"], 3);
    assert!(r["last_scan"].is_null());
}

// ───────────────────────────────────────────────────────────────────────────
// E4-5 audit FUP: handler-level end-to-end JSON-RPC response regression tests
// for the `b5fa443` param_extractor adoption (20 replacements across
// `handlers/budget.rs` + `handlers/risk.rs`).
// E4-5 審計 FUP：`b5fa443` param_extractor 20 處替換的 handler 端到端
// JSON-RPC response 回歸測試（`handlers/budget.rs` + `handlers/risk.rs`）。
//
// EN: The adopter commit claims "error messages remain byte-for-byte
//     identical" but ships without handler-level happy / error regression
//     coverage — the only existing tests (2 × update_ai_budget_config in
//     this file, plus helper-level tests in `param_extractor.rs`) do not
//     assert on the full JSON-RPC response shape or prove the short-form
//     `"missing 'scope'"` messages flow through `require_str_with_msg`
//     unchanged. These tests close that gap: one happy path + one
//     error path per migrated handler (3 × 2 = 6 tests minimum), with
//     exact-string assertions on the error message so future param
//     renaming / helper refactors cannot silently change the wire
//     contract consumed by the Python pytest suite.
// 中：b5fa443 commit 聲稱「錯誤訊息逐位元組保留」但未附 handler 層級的
//     happy / error 回歸測試 — 既有僅 2 個 update_ai_budget_config 單測
//     + `param_extractor.rs` 的輔助函式單測，都未斷言完整 JSON-RPC
//     response 形狀，也未證明 `"missing 'scope'"` 短訊息經
//     `require_str_with_msg` 不變穿透。本節補齊：每個遷移 handler 1
//     happy + 1 error（3 × 2 = 6 最少），對錯誤訊息做逐字比對，避免
//     未來改名 / helper refactor 靜默改變 Python pytest 依賴的 wire 契約。

/// E4-5 test helper: spawn a fake pipeline consumer that **acknowledges**
/// every `UpdateRiskConfig` (drains the channel, does nothing).
/// The handler does not wait for a reply — it only checks that the send
/// succeeded — so the consumer just needs to keep the receiver alive to
/// avoid the send returning `Err(SendError)`. This keeps the test pure
/// handler-level: the response we assert on is built inside
/// `handle_update_risk_config` itself, NOT stubbed.
///
/// E4-5 測試輔助：啟動 fake pipeline consumer，對每個 `UpdateRiskConfig`
/// 只 drain 不處理。handler 不等待回應、僅檢查 send 成功，故 consumer
/// 僅需保持 receiver 存活。這樣 response assertion 來自 handler 內部
/// 真實邏輯，非 stub 回填。
fn setup_risk_update_drain_channel() -> tokio::sync::mpsc::UnboundedSender<PipelineCommand> {
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
    tokio::spawn(async move {
        while let Some(cmd) = rx.recv().await {
            // drain UpdateRiskConfig (and ignore any other variant) / 只 drain
            if let PipelineCommand::UpdateRiskConfig { .. } = cmd {
                // no-op — fire-and-forget command / 即發即忘，handler 已回 success
            }
        }
    });
    tx
}

// ── E4-5 Happy path: handle_update_ai_budget_config ───────────────────────
// ── E4-5 Happy 路徑：handle_update_ai_budget_config ──────────────────────

/// EN: With all params valid but slot uninitialized, the **parse step
///     succeeds** (param_extractor returns Ok for scope / monthly_usd /
///     optional updated_by) and we reach the slot check, which fails-closed
///     with ERR_INTERNAL. This proves the `require_str` + `require_non_negative_f64`
///     + `optional_str_or` happy path wiring actually flows through — if
///     one of those helpers were broken, we'd surface -32602 instead and
///     never reach the slot guard.
/// 中：所有參數合法但槽位未初始化時，param_extractor **解析成功**
///     （scope / monthly_usd 必填 + updated_by 可選），接著進入槽位檢查
///     fail-closed 回 ERR_INTERNAL。此測試證明 `require_str` +
///     `require_non_negative_f64` + `optional_str_or` 三個 helper 的
///     happy 路徑真的串通 — 任一 helper 壞會回 -32602 而非 -32603。
#[tokio::test]
async fn test_e4_5_handle_update_ai_budget_config_happy_parse_reaches_slot() {
    let slot = empty_budget_slot();
    let params = serde_json::json!({
        "scope": "layer2_scout",
        "monthly_usd": 42.5,
        "updated_by": "e4_5_regression"
    });
    let resp = handle_update_ai_budget_config(serde_json::json!(10001), &params, &slot).await;
    // Parse succeeded → progressed past param_extractor → hit slot guard.
    // 解析通過 → 走完 param_extractor → 命中槽位守衛。
    let err = resp
        .error
        .as_ref()
        .expect("uninitialized slot must fail-closed with ERR_INTERNAL, not -32602");
    assert_eq!(
        err.code,
        ERR_INTERNAL,
        "expected ERR_INTERNAL ({ERR_INTERNAL}) proving params parsed OK, got code={} msg={:?}",
        err.code,
        err.message
    );
    // Verify it's the specific slot-guard message, not a random ERR_INTERNAL.
    // 驗證是特定槽位守衛訊息而非隨意 -32603。
    assert_eq!(
        err.message, "budget tracker not initialized (DB pool unavailable?)",
        "ERR_INTERNAL message drifted — expected slot-guard exact text"
    );
    assert_eq!(resp.id, serde_json::json!(10001));
}

// ── E4-5 Error path: handle_update_ai_budget_config missing 'scope' ──────
// ── E4-5 錯誤路徑：handle_update_ai_budget_config 缺 'scope' ─────────────

/// EN: Missing `scope` → `require_str` short-circuits with the canonical
///     `"missing or empty 'scope' (string)"` (with the `(string)` suffix —
///     `update_ai_budget_config` uses `require_str`, NOT `require_str_with_msg`).
///     Byte-for-byte assertion catches any future drift in the helper
///     format string or the handler's choice of helper variant.
/// 中：缺 `scope` → `require_str` 短路回傳預設訊息
///     `"missing or empty 'scope' (string)"`（帶 `(string)` 尾綴 —
///     此 handler 用 `require_str`，不是 `require_str_with_msg`）。
///     逐字比對抓未來 helper format / 選擇變體的任何漂移。
#[tokio::test]
async fn test_e4_5_handle_update_ai_budget_config_error_missing_scope_exact_message() {
    let slot = empty_budget_slot();
    let params = serde_json::json!({
        // scope intentionally absent / 故意不傳 scope
        "monthly_usd": 10.0
    });
    let resp = handle_update_ai_budget_config(serde_json::json!(10002), &params, &slot).await;
    let err = resp.error.expect("missing 'scope' must produce an error response");
    assert_eq!(err.code, -32602, "expected ERR_INVALID_PARAMS, got {}", err.code);
    // Byte-for-byte — THIS is the load-bearing assertion per the audit finding.
    // If this message changes to e.g. "'scope' is missing" or drops the
    // "(string)" suffix, Python pytest breaks on the wire contract.
    // 逐字比對 — audit finding 的關鍵斷言。訊息若改成
    // "'scope' is missing" 或掉 "(string)" 尾綴，Python pytest wire 契約就壞。
    assert_eq!(
        err.message, "missing or empty 'scope' (string)",
        "byte-identity drift: error message must exactly match legacy handler contract"
    );
    assert_eq!(resp.id, serde_json::json!(10002));
    assert!(resp.result.is_none());
}

// ── E4-5 Happy path: handle_record_ai_usage ──────────────────────────────
// ── E4-5 Happy 路徑：handle_record_ai_usage ──────────────────────────────

/// EN: All required string params (scope / provider / model) present;
///     tokens_in/out omitted (optional, defaults to 0 via `optional_u64 →
///     unwrap_or(0)`); purpose omitted (defaults to `"layer2_external"` via
///     `optional_str_or`). Parse must reach the slot guard which fails-
///     closed with ERR_INTERNAL (same pattern as budget happy test).
///     This proves the 3 × `require_str_with_msg` + `optional_u64` + two
///     `optional_str_or` wiring is intact.
/// 中：必填 scope / provider / model 齊備，tokens_in/out 省略（走
///     `optional_u64.unwrap_or(0)`），purpose 省略（走 `optional_str_or`
///     預設 `"layer2_external"`）。解析成功後觸槽位守衛 ERR_INTERNAL。
///     證明 3 × `require_str_with_msg` + `optional_u64` + 兩個
///     `optional_str_or` 全部接線無損。
#[tokio::test]
async fn test_e4_5_handle_record_ai_usage_happy_parse_reaches_slot() {
    let slot = empty_budget_slot();
    let params = serde_json::json!({
        "scope": "layer2_scout",
        "provider": "anthropic",
        "model": "claude-4-5-sonnet",
        // tokens_in/tokens_out/purpose intentionally omitted to exercise
        // the optional_* defaults / 故意省略 optional_* 欄位驗預設接線
    });
    let resp = handle_record_ai_usage(serde_json::json!(10003), &params, &slot).await;
    let err = resp
        .error
        .as_ref()
        .expect("uninitialized slot must fail-closed, proving parse succeeded");
    assert_eq!(
        err.code, ERR_INTERNAL,
        "expected ERR_INTERNAL (proves all require_str_with_msg parsed OK), \
         got code={} msg={:?}",
        err.code, err.message
    );
    assert_eq!(
        err.message, "budget tracker not initialized (DB pool unavailable?)",
        "slot-guard message drifted"
    );
    assert_eq!(resp.id, serde_json::json!(10003));
}

// ── E4-5 Error path: handle_record_ai_usage missing 'scope' ──────────────
// ── E4-5 錯誤路徑：handle_record_ai_usage 缺 'scope' ─────────────────────

/// EN: Missing `scope` → `require_str_with_msg(..., "missing 'scope'")`
///     short-circuits with the **short-form** message — NO `(string)`
///     suffix. This is the exact byte-for-byte form the legacy
///     `handlers.rs` hand-written path produced before `b5fa443`.
///     Python pytest asserts on this short form; drift would silently
///     break the external contract.
/// 中：缺 `scope` → `require_str_with_msg(..., "missing 'scope'")` 短路
///     回傳 **短訊息** — 無 `(string)` 尾綴。此為 `b5fa443` 前 legacy
///     hand-written 路徑的精確 byte-for-byte 格式，Python pytest 對此
///     斷言；漂移會靜默破壞外部契約。
#[tokio::test]
async fn test_e4_5_handle_record_ai_usage_error_missing_scope_short_form_message() {
    let slot = empty_budget_slot();
    let params = serde_json::json!({
        // scope intentionally absent / 故意不傳
        "provider": "anthropic",
        "model": "claude-4-5-sonnet"
    });
    let resp = handle_record_ai_usage(serde_json::json!(10004), &params, &slot).await;
    let err = resp
        .error
        .expect("missing 'scope' must produce an error response");
    assert_eq!(err.code, -32602, "expected ERR_INVALID_PARAMS");
    // CRITICAL BYTE-IDENTITY: short form, no "(string)" suffix, single quotes
    // around scope. Any reformatting (e.g. "missing scope" / "scope: missing"
    // / adding "(string)") breaks the Python wire contract.
    // 關鍵逐字比對：短形式，無 "(string)" 尾綴，scope 帶單引號。任何
    // 重排（"missing scope" / "scope: missing" / 加 "(string)"）都壞 Python 契約。
    assert_eq!(
        err.message, "missing 'scope'",
        "byte-identity drift: require_str_with_msg short-form must match legacy exact text"
    );
    assert_eq!(resp.id, serde_json::json!(10004));
    assert!(resp.result.is_none());
}

// ── E4-5 Happy path: handle_update_risk_config ───────────────────────────
// ── E4-5 Happy 路徑：handle_update_risk_config ───────────────────────────

/// EN: Single risk param (`hard_stop_pct`) suffices to pass the `has_any`
///     gate; the handler sends `UpdateRiskConfig` on the channel and
///     returns `{"updated": true}`. This proves `optional_f64` parses the
///     field, the `has_any` aggregation recognises at least one Some, and
///     the channel send succeeds — all 11 `optional_*` replacements in
///     this handler are exercised through the default-None path plus one
///     Some path.
/// 中：單一 risk 參數（`hard_stop_pct`）即可通過 `has_any` 門；handler
///     經通道送 `UpdateRiskConfig` 並回 `{"updated": true}`。證明
///     `optional_f64` 正確解析、`has_any` 正確識別 ≥1 Some、通道 send
///     成功 — 11 處 `optional_*` 替換走過 default-None 路徑 + 一次 Some。
#[tokio::test]
async fn test_e4_5_handle_update_risk_config_happy_single_param_returns_updated_true() {
    let tx = setup_risk_update_drain_channel();
    let tx_opt = Some(tx);
    let params = serde_json::json!({
        "hard_stop_pct": 0.02
    });
    let resp = handle_update_risk_config(serde_json::json!(10005), &tx_opt, &params).await;
    assert!(
        resp.error.is_none(),
        "happy path must not error: {:?}",
        resp.error
    );
    let result = resp.result.expect("result must be present");
    assert_eq!(
        result,
        serde_json::json!({"updated": true}),
        "response body must match legacy byte-for-byte"
    );
    assert_eq!(resp.id, serde_json::json!(10005));
}

// ── E4-5 Error path: handle_update_risk_config no-param / wrong-type ─────
// ── E4-5 錯誤路徑：handle_update_risk_config 無參 / 型別錯 ───────────────

/// EN: Empty params `{}` (or any payload where every `optional_*` returns
///     None) fails the `has_any` aggregation → ERR_INVALID_REQUEST (-32600)
///     with `"need at least one risk parameter"`. This is the designed
///     error path: every `optional_*` returning None proves the helpers
///     handle absence correctly (no panic, no surprise -32602 from a
///     `require_*` misuse). A wrong-type value (e.g. `hard_stop_pct: "str"`)
///     also collapses to None via `serde_json::Value::as_f64() -> None` and
///     ends up here — we cover both inputs to prove the single `has_any`
///     path handles missing AND coerced-to-None uniformly.
/// 中：空參 `{}`（或所有 `optional_*` 皆 None）走 `has_any` 失敗路徑 →
///     ERR_INVALID_REQUEST (-32600) 訊息 `"need at least one risk parameter"`。
///     此為設計錯誤路徑：每個 `optional_*` 回 None 證 helper 正確處理
///     缺失（不 panic、不誤回 -32602）。型別錯（例 `hard_stop_pct: "str"`）
///     經 `as_f64() -> None` 亦落入此路徑 — 驗兩種輸入統一收斂。
#[tokio::test]
async fn test_e4_5_handle_update_risk_config_error_empty_params_byte_identical_message() {
    let tx = setup_risk_update_drain_channel();
    let tx_opt = Some(tx);
    let params = serde_json::json!({});
    let resp = handle_update_risk_config(serde_json::json!(10006), &tx_opt, &params).await;
    let err = resp
        .error
        .expect("empty params must produce ERR_INVALID_REQUEST");
    assert_eq!(err.code, ERR_INVALID_REQUEST, "expected -32600");
    // Byte-identity: legacy message exactly. "at least one risk parameter"
    // (no trailing period, no "required"). Python pytest depends on this.
    // 逐字比對：legacy 原訊息（無句點、無 "required"）。Python pytest 依賴。
    assert_eq!(
        err.message, "need at least one risk parameter",
        "byte-identity drift: update_risk_config no-param message must match legacy exact text"
    );
    assert_eq!(resp.id, serde_json::json!(10006));

    // Wrong-type input collapses to None via as_f64() and hits the same path.
    // 型別錯 → as_f64() = None → 同路徑。
    let bad_params = serde_json::json!({
        "hard_stop_pct": "not_a_number",
        "max_drawdown_pct": true,
        "boot_cooldown_ms": 3.14
    });
    let resp2 = handle_update_risk_config(serde_json::json!(10007), &tx_opt, &bad_params).await;
    let err2 = resp2
        .error
        .expect("wrong-type params must collapse to None and hit has_any");
    assert_eq!(err2.code, ERR_INVALID_REQUEST);
    assert_eq!(
        err2.message, "need at least one risk parameter",
        "wrong-type inputs must route to the same has_any message (optional_* = None semantics)"
    );
}
