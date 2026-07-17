"""Static authority-boundary checks for the public-only engine profile."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "rust/openclaw_engine/src/main.rs"
PROFILE = ROOT / "rust/openclaw_engine/src/main_runtime_profile.rs"
WS_MOD = ROOT / "rust/openclaw_engine/src/ws_client/mod.rs"
PUBLIC_WS = ROOT / "rust/openclaw_engine/src/ws_client/public_only.rs"
WS_RUN_LOOP = ROOT / "rust/openclaw_engine/src/ws_client/run_loop.rs"


def test_only_absent_profile_can_reach_full_engine_boot() -> None:
    main = MAIN.read_text(encoding="utf-8")
    assert "mod main_runtime_profile;" in main
    resolve = main.index("main_runtime_profile::resolve_runtime_profile_request")
    for marker in (
        "consume_restart_sentinel_and_clear_live_auth_if_manual",
        "ConfigManager::load(None)", "load_unified_configs()", "runtime.block_on(async_main(",
    ):
        assert resolve < main.index(marker)
    dispatch = main[main.index("match main_runtime_profile::resolve_runtime_profile_request"):
                    main.index("// 1b2. P0-1c boot")]
    for marker in (
        "RuntimeProfileRequestResolution::Absent => {}",
        "RuntimeProfileRequestResolution::ValidPublicOnly(request)",
        "main_runtime_profile::run_public_only_profile",
        "RuntimeProfileRequestResolution::PresentInvalid(error)",
    ):
        assert marker in dispatch
    assert dispatch.count("std::process::exit(1)") >= 2


def test_public_client_has_immutable_endpoint_topics_and_no_authority_injection() -> None:
    ws_mod = WS_MOD.read_text(encoding="utf-8")
    public_ws = PUBLIC_WS.read_text(encoding="utf-8")
    run_loop = WS_RUN_LOOP.read_text(encoding="utf-8")
    assert "pub mod public_only;" in ws_mod
    assert "pub struct PublicMarketDataOnlyWsClient" in public_ws
    constructor = public_ws[public_ws.index("pub fn new("):public_ws.index("pub async fn run(")]
    assert "event_tx: mpsc::Sender<PriceEvent>" in constructor
    assert "cancel: CancellationToken" in constructor
    assert "endpoint" not in constructor and "topic" not in constructor
    forbidden = (
        "ConfigManager", "main_ws", "scanner", "SymbolRegistry", "ConfigStore",
        "WsTopicChange", "reqwest", "private",
    )
    assert not any(marker in public_ws for marker in forbidden)
    assert re.search(r"(?<!PublicMarketDataOnly)WsClient::", public_ws) is None
    for value in (
        "wss://stream.bybit.com/v5/public/linear", "kline.1.BTCUSDT",
        "publicTrade.BTCUSDT", "kline.1.ETHUSDT", "publicTrade.ETHUSDT",
    ):
        assert f'"{value}"' in run_loop


def test_profile_is_fail_closed_durable_and_has_no_full_engine_constructors() -> None:
    profile = PROFILE.read_text(encoding="utf-8")
    forbidden = (
        "ConfigManager::", "load_unified_configs(", "PipelineSlot::", "IpcServer::",
        "LiveAuthWatcher::", "ScannerRunner::", "MarketDataClient::", "BybitRestClient::",
        "DecisionLease", "EngineCommandChannels::", "main_scanner_init::", "main_ws::",
        "std::env::var", "remove_file(&request.request_path)",
    )
    assert not any(marker in profile for marker in forbidden)
    for marker in (
        "PublicMarketDataOnlyWsClient::new(event_tx, cancel)",
        "tokio::signal::unix::SignalKind::terminate()",
        "tokio::signal::unix::SignalKind::interrupt()", "O_NOFOLLOW", "O_NONBLOCK",
        "metadata_snapshot", "before_path != before_read", "after_read != before_read",
        "serde(deny_unknown_fields)", "MAX_REQUEST_BYTES", "nlink != 1", "REQUEST_WRITER",
        "known_source_head", "create_new(true)", ".mode(0o600)", "file.sync_all()",
        "JoinSet", "tasks.abort_all()",
    ):
        assert marker in profile
    assert re.search(r"directory\s*\.sync_all\(\)", profile)
    for field in (
        "private_rest_active", "private_ws_active", "auth_watcher_active", "database_active",
        "ipc_active", "scanner_runner_active", "execution_pipelines_active",
        "order_channels_active", "decision_lease_authority", "trading_mutation_authority",
        "private_mutation_authority",
    ):
        assert re.search(rf"{field}: false", profile)
