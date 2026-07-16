import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
IPC_TEST_ROOT = ROOT / "rust/openclaw_engine/src/ipc_server/tests"
STOCK_ETF_PARENT = IPC_TEST_ROOT / "stock_etf.rs"
STOCK_ETF_SPLIT_DIR = IPC_TEST_ROOT / "stock_etf"
MAX_LINES = 800
# 2026-07-03 同步：Codex 時代 fixture 再拆分（commit e259674fe 從父檔/尾段拆出
# core_status_fixtures.rs 與 phase5_status_fixtures.rs），本 static 治理測試當時未同步。
# 已逐一驗證新模組行數皆在 MAX_LINES 內且無 runtime material 讀取。
EXPECTED_MODULES = {
    "core_status_fixtures.rs",
    "foundation_status_fixtures.rs",
    "health_status_fixtures.rs",
    "phase5_status_fixtures.rs",
    "precontact_fixtures.rs",
    "request_contracts.rs",
    "status_fixtures.rs",
}
FORBIDDEN_RUNTIME_MATERIAL_TOKENS = (
    "std::env",
    "env::var",
    "var_os",
    "vars_os",
    "std::fs",
    "std::path::Path",
    "File::open",
    "OpenOptions",
    "read_to_string",
    "read_to_end",
    "read_exact",
    "include_str!",
    "include_bytes!",
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
)
FORBIDDEN_BYBIT_RUNTIME_TOKENS = (
    "crate::bybit_",
    "openclaw_engine::bybit_",
    "crate::bybit_rest_client",
    "crate::bybit_private_ws",
    "crate::bybit_private_ws_status_writer",
    "crate::bybit_earn_client",
    "openclaw_engine::bybit_rest_client",
    "openclaw_engine::bybit_private_ws",
    "openclaw_engine::bybit_private_ws_status_writer",
    "openclaw_engine::bybit_earn_client",
    "bybit_rest_client::",
    "bybit_private_ws::",
    "bybit_private_ws_status_writer::",
    "bybit_earn_client::",
    "BybitRestClient",
    "BybitPrivateWs",
    "BybitEnvironment",
    "BybitApiError",
    "BybitResult",
    "BybitEarn",
    "crate::order_manager",
    "openclaw_engine::order_manager",
    "order_manager::",
    "OrderManager",
    "CreateOrderRequest",
    "OrderResponse",
    "crate::order_router",
    "openclaw_engine::order_router",
    "order_router::",
    "crate::paper_state",
    "openclaw_engine::paper_state",
    "paper_state::",
    "crate::bounded_probe_active_order",
    "openclaw_engine::bounded_probe_active_order",
    "crate::platform_client",
    "openclaw_engine::platform_client",
    "platform_client::",
    "PlatformClient",
    "crate::event_consumer",
    "openclaw_engine::event_consumer",
    "event_consumer::",
    "crate::execution_listener",
    "openclaw_engine::execution_listener",
    "execution_listener::",
    "crate::database::rest_poller",
    "openclaw_engine::database::rest_poller",
    "RestPoller",
    "handle_submit_paper_order",
    ".place_order(",
    ".cancel_order(",
    ".cancel_order_by_link_id(",
    ".submit_order(",
    ".replace_order(",
    ".modify_order(",
    ".create_order(",
)
# 為什麼豁免：父檔 stock_etf.rs 的 stock_etf_ipc_status_fixture_assertions_stay_exact
# 源碼守衛（commit 631f5ce3b 引入、e259674fe/02e6e342e 擴充）以 include_str! 在
# 「編譯期」內嵌自身測試樹源碼做斷言形狀掃描，屬 source-only 自掃描，非 runtime
# material 讀取。豁免採 deny-by-default：僅限父檔內、字面引數落在 stock_etf 測試樹
# 內的 include_str!；子模組的 include_str!、任何 include_bytes!、以及 concat! 等
# 非字面變形一律不剝離，仍由 FORBIDDEN_RUNTIME_MATERIAL_TOKENS 掃描判違規。
SELF_SOURCE_INCLUDE_RE = re.compile(r'include_str!\(\s*"([^"]+)"\s*\)')
ALLOWED_SELF_SOURCE_INCLUDES = frozenset(
    {"stock_etf.rs"} | {f"stock_etf/{name}" for name in EXPECTED_MODULES}
)
FORBIDDEN_RUNTIME_SIDE_EFFECT_TOKENS = (
    "std::time",
    "SystemTime",
    "Instant",
    "chrono",
    "Utc::now",
    "Local::now",
    "std::thread",
    "thread::spawn",
    "tokio::spawn",
    "tokio::task",
    "tokio::time",
    "sleep(",
    "std::process",
    "process::Command",
    "Command::new",
    ".spawn(",
)


def _loc(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _strip_allowed_self_source_includes(source: str) -> str:
    # 只剝離字面引數落在 ALLOWED_SELF_SOURCE_INCLUDES 的 include_str!；
    # 其餘形式原樣保留於殘文，交由後續 token 掃描 fail-closed 判違規。
    def _replace(match: re.Match) -> str:
        if match.group(1) in ALLOWED_SELF_SOURCE_INCLUDES:
            return ""
        return match.group(0)

    return SELF_SOURCE_INCLUDE_RE.sub(_replace, source)


def test_stock_etf_ipc_fixture_tests_are_split_under_governance_cap() -> None:
    parent = STOCK_ETF_PARENT.read_text(encoding="utf-8")
    modules = {
        path.name: _loc(path)
        for path in STOCK_ETF_SPLIT_DIR.glob("*.rs")
    }

    # 2026-07-03 同步 e259674fe：父檔新增 core/phase5 兩個子模組宣告。
    assert "mod core_status_fixtures;" in parent
    assert "mod request_contracts;" in parent
    assert "mod status_fixtures;" in parent
    assert "mod phase5_status_fixtures;" in parent
    assert "mod precontact_fixtures;" in parent
    assert "mod foundation_status_fixtures;" in parent
    assert set(modules) == EXPECTED_MODULES
    assert _loc(STOCK_ETF_PARENT) <= MAX_LINES
    assert all(loc <= MAX_LINES for loc in modules.values())


def test_stock_etf_ipc_fixture_tests_have_no_runtime_material_readers() -> None:
    # 2026-07-03：父檔先剝離「允許的自源 include_str!」再掃描（豁免邊界見常量注釋）；
    # 子模組不享豁免，維持全 token 掃描。
    sources = {
        STOCK_ETF_PARENT: _strip_allowed_self_source_includes(
            STOCK_ETF_PARENT.read_text(encoding="utf-8")
        )
    }
    sources.update(
        {
            path: path.read_text(encoding="utf-8")
            for path in STOCK_ETF_SPLIT_DIR.glob("*.rs")
        }
    )

    violations = []
    for path, source in sources.items():
        for token in FORBIDDEN_RUNTIME_MATERIAL_TOKENS:
            if token in source:
                violations.append(f"{path}: contains forbidden runtime material token {token!r}")

    assert violations == []


def test_stock_etf_ipc_fixture_tests_do_not_import_or_call_bybit_runtime_paths() -> None:
    sources = {STOCK_ETF_PARENT: STOCK_ETF_PARENT.read_text(encoding="utf-8")}
    sources.update(
        {
            path: path.read_text(encoding="utf-8")
            for path in STOCK_ETF_SPLIT_DIR.glob("*.rs")
        }
    )

    violations = []
    for path, source in sources.items():
        for token in FORBIDDEN_BYBIT_RUNTIME_TOKENS:
            if token in source:
                violations.append(f"{path}: contains forbidden Bybit runtime token {token!r}")

    assert violations == []


def test_stock_etf_ipc_fixture_tests_have_no_clock_thread_or_process_side_effects() -> None:
    sources = {STOCK_ETF_PARENT: STOCK_ETF_PARENT.read_text(encoding="utf-8")}
    sources.update(
        {
            path: path.read_text(encoding="utf-8")
            for path in STOCK_ETF_SPLIT_DIR.glob("*.rs")
        }
    )

    violations = []
    for path, source in sources.items():
        for token in FORBIDDEN_RUNTIME_SIDE_EFFECT_TOKENS:
            if token in source:
                violations.append(f"{path}: contains forbidden runtime side-effect token {token!r}")

    assert violations == []


def test_stock_etf_request_contract_fixtures_remain_source_only_tests() -> None:
    source = (STOCK_ETF_SPLIT_DIR / "request_contracts.rs").read_text(encoding="utf-8")

    for method in (
        "stock_etf.submit_paper_order",
        "stock_etf.preview_paper_order",
        "stock_etf.cancel_paper_order",
        "stock_etf.import_paper_fills",
        "stock_etf.evaluate_shadow_signal",
        "stock_etf.preview_readonly_probe",
        "submit_paper_order",
    ):
        assert method in source

    for forbidden in (
        "ib_insync",
        "ibapi",
        "IBApi",
        "TcpStream",
        "tokio::net",
        "reqwest",
    ):
        assert forbidden not in source


def test_stock_etf_tail_status_fixtures_remain_source_only_tests() -> None:
    # 2026-07-03 同步 e259674fe：launch/release_packet/disable_cleanup 尾段 status
    # fixture 移入 phase5_status_fixtures.rs；account/reconciliation/scorecard 留在
    # status_fixtures.rs。source-only 禁令對兩檔皆維持不變。
    tail_module_methods = {
        "status_fixtures.rs": (
            "stock_etf.get_account_status",
            "stock_etf.get_reconciliation_status",
            "stock_etf.get_scorecard_status",
        ),
        "phase5_status_fixtures.rs": (
            "stock_etf.get_launch_status",
            "stock_etf.get_release_packet_status",
            "stock_etf.get_disable_cleanup_status",
        ),
    }

    for module_name, methods in tail_module_methods.items():
        source = (STOCK_ETF_SPLIT_DIR / module_name).read_text(encoding="utf-8")

        for method in methods:
            assert method in source, f"{module_name} missing {method}"

        for forbidden in (
            "ib_insync",
            "ibapi",
            "IBApi",
            "TcpStream",
            "tokio::net",
            "reqwest",
        ):
            assert forbidden not in source, f"{module_name} contains {forbidden}"


def test_stock_etf_precontact_and_foundation_fixtures_are_in_child_modules() -> None:
    parent = STOCK_ETF_PARENT.read_text(encoding="utf-8")
    precontact = (STOCK_ETF_SPLIT_DIR / "precontact_fixtures.rs").read_text(
        encoding="utf-8"
    )
    foundation = (STOCK_ETF_SPLIT_DIR / "foundation_status_fixtures.rs").read_text(
        encoding="utf-8"
    )

    assert "stock_etf_readiness_exposes_phase2_precontact_blockers" in precontact
    assert "stock_etf_data_foundation_status_is_blocked_source_fixture" in foundation
    assert "stock_etf_policy_status_is_blocked_source_fixture" in foundation
    assert "stock_etf_authorization_status_is_blocked_source_fixture" in foundation

    for moved_test in (
        "stock_etf_readiness_exposes_phase2_precontact_blockers",
        "stock_etf_data_foundation_status_is_blocked_source_fixture",
        "stock_etf_policy_status_is_blocked_source_fixture",
        "stock_etf_authorization_status_is_blocked_source_fixture",
    ):
        assert moved_test not in parent
