from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
# 直接引用的來源檔字面 rel 路徑：讓本 source-static 守衛同時滿足 rust-source-coverage
# 的「被測試引用」判定（sibling loader 從此不再逃出結構守衛掃描面）。
SOURCE_REL_PATH = "rust/openclaw_engine/src/ipc_server/handlers/stock_etf_risk_policy.rs"
RISK_POLICY_LOADER = ROOT / SOURCE_REL_PATH
MAX_LINES = 800

# denied fallback 的 fail-closed 全 false 語義（逐一斷言，防語義退化）：TOML 載入
# 失敗時顯示面必回退此 policy，絕不出現任何寬鬆 cap/flag。
REQUIRED_DENIED_FALLBACK_TOKENS = (
    "fn denied_stock_etf_risk_policy_fallback",
    "enabled: false",
    "shadow_only: true",
    "allow_margin: false",
    "allow_short: false",
    "allow_options: false",
    "allow_cfd: false",
    "allow_transfer: false",
    "allow_live: false",
    "bybit_live_execution_unchanged: true",
)
# loader 邊界：std::fs / std::path 是合法載入器的家（允許）；但網路 / 下單 / 其他
# broker runtime client 一律禁（沿用既有守衛的 FORBIDDEN_BYBIT/NET 子集）。
FORBIDDEN_NETWORK_AND_ORDER_TOKENS = (
    "std::net",
    "TcpStream",
    "UdpSocket",
    "tokio::net",
    "reqwest",
    "hyper::",
    "ureq",
    "ib_insync",
    "ibapi",
    "IBApi",
    "BybitRestClient",
    "BybitPrivateWs",
    "bybit_rest_client::",
    "bybit_private_ws::",
    "order_manager::",
    "OrderManager",
    "CreateOrderRequest",
    "OrderResponse",
    "order_router::",
    "paper_state::",
    "PlatformClient",
    "handle_submit_paper_order",
    ".place_order(",
    ".cancel_order(",
    ".submit_order(",
    ".replace_order(",
    ".modify_order(",
    ".create_order(",
)


def _source() -> str:
    return RISK_POLICY_LOADER.read_text(encoding="utf-8")


def test_stock_etf_risk_policy_loader_source_exists_and_stays_below_cap() -> None:
    assert RISK_POLICY_LOADER.exists(), f"missing sibling loader {SOURCE_REL_PATH}"
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_risk_policy_loader_keeps_pure_loader_boundary() -> None:
    source = _source()
    # 合法載入器：pure loader 簽名 + 真正的檔案/TOML 讀取路徑存在於此（而非 handler）。
    assert (
        "pub(in crate::ipc_server) fn load_stock_etf_risk_policy_from_dir(" in source
    ), "pure loader 簽名/可見性遺失"
    assert "std::fs::read_to_string" in source, "loader 應在此持有檔案讀取（合法之家）"
    assert "risk_config_stock_etf_paper.toml" in source


def test_stock_etf_risk_policy_denied_fallback_stays_fail_closed_all_false() -> None:
    source = _source()
    for token in REQUIRED_DENIED_FALLBACK_TOKENS:
        assert token in source, f"denied fallback fail-closed 語義遺失: {token!r}"


def test_stock_etf_risk_policy_loader_has_no_network_or_order_tokens() -> None:
    source = _source()
    violations = [
        f"{RISK_POLICY_LOADER}: contains forbidden network/order token {token!r}"
        for token in FORBIDDEN_NETWORK_AND_ORDER_TOKENS
        if token in source
    ]
    assert violations == []
